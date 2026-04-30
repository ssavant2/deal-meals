"""
Pantry Match API Route.

This router handles pantry-based recipe matching:
- /api/pantry-match - Find recipes matching user-provided ingredients
"""

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from loguru import logger

from database import get_db_session
from utils.errors import friendly_error
from utils.rate_limit import limiter
from config import settings

try:
    from pantry_search_index import (
        build_pantry_query,
        load_legacy_pantry_recipes,
        log_pantry_index_selection,
        refresh_compiled_recipe_search_term_index,
        score_pantry_recipes,
        select_pantry_index_matches,
    )
except ModuleNotFoundError:
    from app.pantry_search_index import (
        build_pantry_query,
        load_legacy_pantry_recipes,
        log_pantry_index_selection,
        refresh_compiled_recipe_search_term_index,
        score_pantry_recipes,
        select_pantry_index_matches,
    )


# Limits
MAX_FULL_MATCHES = 100            # Max full-match recipes returned
MAX_PARTIAL_MATCHES = 200         # Max partial-match recipes returned

router = APIRouter(prefix="/api", tags=["pantry"])


def _enrich_with_offer_cache(full_match: list[dict], partial_match: list[dict]) -> None:
    all_results = full_match[:MAX_FULL_MATCHES] + partial_match[:MAX_PARTIAL_MATCHES]
    if not all_results:
        return

    result_ids = [result["id"] for result in all_results]
    with get_db_session() as db:
        cache_rows = db.execute(text("""
            SELECT found_recipe_id, total_savings, num_matches, match_data
            FROM recipe_offer_cache
            WHERE found_recipe_id::text = ANY(:ids)
        """), {"ids": result_ids}).fetchall()

    cache_map = {}
    for cache_row in cache_rows:
        match_data = cache_row.match_data or {}
        cache_map[str(cache_row.found_recipe_id)] = {
            "total_savings": float(cache_row.total_savings or 0),
            "num_matches": cache_row.num_matches or 0,
            "matched_offers": match_data.get("matched_offers", []),
            "ingredient_groups": match_data.get("ingredient_groups", []),
            "avg_savings_pct": match_data.get("total_savings_pct", 0),
        }

    for result in all_results:
        cache_data = cache_map.get(result["id"], {})
        result["total_savings"] = cache_data.get("total_savings", 0)
        result["num_matches"] = cache_data.get("num_matches", 0)
        result["matched_offers"] = cache_data.get("matched_offers", [])
        result["ingredient_groups"] = cache_data.get("ingredient_groups", [])
        result["avg_savings_pct"] = cache_data.get("avg_savings_pct", 0)


def _legacy_pantry_match(query):
    recipes = load_legacy_pantry_recipes()
    full_match, partial_match = score_pantry_recipes(recipes, query)
    return full_match, partial_match, len(recipes)


@router.post("/pantry-match")
@limiter.limit(settings.rate_limit_pantry)
async def pantry_match(request: Request):
    """
    Find recipes that can be made with user-provided ingredients.

    Request body:
        {"ingredients": "bacon, grädde, pasta, kyckling"}

    Response:
        {
            "success": True,
            "full_match": [...],  # Recipes where user has ALL ingredients
            "partial_match": [...],  # Recipes needing 1-2 more items
            "user_keywords": ["bacon", "grädde", "pasta", "kyckling"]
        }
    """
    try:
        data = await request.json()
        raw_ingredients = data.get('ingredients', '')

        if not raw_ingredients.strip():
            return JSONResponse({
                "success": False,
                "message_key": "pantry.no_ingredients"
            })

        query = build_pantry_query(raw_ingredients)
        if not query.user_keywords:
            return JSONResponse({
                "success": False,
                "message_key": "pantry.extract_failed"
            })

        used_index = False
        if settings.pantry_search_term_index_enabled:
            started = time.perf_counter()
            selection = select_pantry_index_matches(
                query,
                max_candidates=settings.pantry_search_term_index_max_candidates,
                full_limit=MAX_FULL_MATCHES,
                partial_limit=MAX_PARTIAL_MATCHES,
            )
            log_pantry_index_selection(
                "PANTRY_SEARCH_INDEX",
                selection,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
            if selection.use_index:
                full_match, partial_match = selection.full_match, selection.partial_match
                total_searched = selection.total_scope
                used_index = True
            else:
                full_match, partial_match, total_searched = _legacy_pantry_match(query)
        else:
            full_match, partial_match, total_searched = _legacy_pantry_match(query)
            if settings.pantry_search_term_index_shadow_logging_enabled:
                started = time.perf_counter()
                selection = select_pantry_index_matches(
                    query,
                    max_candidates=settings.pantry_search_term_index_max_candidates,
                    full_limit=MAX_FULL_MATCHES,
                    partial_limit=MAX_PARTIAL_MATCHES,
                )
                log_pantry_index_selection(
                    "PANTRY_SEARCH_INDEX_SHADOW",
                    selection,
                    elapsed_ms=int((time.perf_counter() - started) * 1000),
                )

        _enrich_with_offer_cache(full_match, partial_match)

        response = {
            "success": True,
            "full_match": full_match[:MAX_FULL_MATCHES],
            "partial_match": partial_match[:MAX_PARTIAL_MATCHES],
            "user_keywords": list(query.user_keywords),
            "total_searched": total_searched
        }
        if settings.debug:
            response["candidate_source"] = "search_term_index" if used_index else "legacy"

        return JSONResponse(response)

    except Exception as e:
        logger.error(f"Error in pantry match: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        })


@router.post("/pantry-search-index/refresh")
@limiter.limit(settings.rate_limit_heavy_compute)
async def refresh_pantry_search_index(request: Request):
    """Refresh the optional pantry search-term index."""
    try:
        result = refresh_compiled_recipe_search_term_index()
        return JSONResponse({
            "success": True,
            **result,
        })
    except Exception as e:
        logger.error(f"Error refreshing pantry search-term index: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e),
        }, status_code=500)
