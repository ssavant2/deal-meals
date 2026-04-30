"""
Recipe API Routes.

This router handles all recipe-related API endpoints:
- /api/recipe-search - Recipe search
- /api/matching/preferences - Matching preferences (GET/POST)
- /api/matching/preview - Recipe matching preview
- /api/cache/status - Cache status
- /api/cache/reset - Cache reset
- /api/recipe-scrapers/* - Recipe scraper management
"""

import json
import asyncio
import threading
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from utils.rate_limit import limiter
from config import settings
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse
from sqlalchemy import text
from loguru import logger

from database import get_db_session
from recipe_cache_refresh_decision import (
    RecipeCacheRefreshDecision,
    RecipeCacheStatusSnapshot,
    decide_recipe_cache_refresh_strategy,
    load_recipe_cache_status_snapshot,
)
from scrapers.recipes._common import normalize_recipe_scrape_result
from utils.errors import friendly_error, is_valid_uuid
from utils.recipe_image_cleanup import (
    delete_unreferenced_recipe_image_file,
    delete_unreferenced_recipe_image_files,
)
from utils.scraper_history import save_run_history
from state import (
    running_scrapers, scraper_tasks, event_bus,
    update_running_scraper, get_running_scraper, get_scraper_lock,
    set_run_all_queue, update_run_all_queue, get_run_all_queue, clear_run_all_queue,
    claim_run_all_queue_finish,
    get_image_state,
)

# Import category constants
from languages.categories import (
    MEAT, FISH, VEGETARIAN,
    POULTRY, DELI
)

# Import recipe scraper manager
try:
    from recipe_scraper_manager import scraper_manager
    RECIPE_SCRAPERS_AVAILABLE = True
except ImportError:
    RECIPE_SCRAPERS_AVAILABLE = False
    scraper_manager = None


router = APIRouter(prefix="/api", tags=["recipes"])


# ==================== HELPER FUNCTIONS ====================

# Prevent fire-and-forget tasks from being garbage collected or losing exceptions
_background_tasks: set[asyncio.Task] = set()


def _task_done(task: asyncio.Task) -> None:
    _background_tasks.discard(task)
    if not task.cancelled() and task.exception():
        logger.error(f"Background task {task.get_name()!r} failed: {task.exception()}")


def create_background_task(coro, *, name: str = None) -> asyncio.Task:
    """Create a background task with proper reference tracking and error logging."""
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_task_done)
    return task



def _median(values: list[float]) -> float:
    """Return median value for a non-empty numeric list."""
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _has_scraper_history_attempted_count(db) -> bool:
    """Return True if the optional scalable-estimate column exists."""
    return bool(db.execute(text("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'scraper_run_history'
              AND column_name = 'attempted_count'
        )
    """)).scalar())


def _get_time_estimates(scraper_id: str, target_attempts: dict | None = None) -> dict:
    """Get time estimates for all modes based on history and current limits."""
    estimates = {}
    target_attempts = target_attempts or {}
    try:
        with get_db_session() as db:
            attempted_count_expr = (
                "attempted_count"
                if _has_scraper_history_attempted_count(db)
                else "NULL::integer AS attempted_count"
            )
            for mode in ['test', 'incremental', 'full']:
                rows = db.execute(
                    text(f"""
                        SELECT duration_seconds, {attempted_count_expr}, recipes_found
                        FROM scraper_run_history
                        WHERE scraper_id = :scraper_id
                          AND mode = :mode
                          AND success = true
                        ORDER BY run_at DESC
                        LIMIT 5
                    """),
                    {"scraper_id": scraper_id, "mode": mode}
                ).fetchall()

                if rows:
                    durations = [int(row.duration_seconds) for row in rows if row.duration_seconds]
                    if not durations:
                        continue
                    estimate_seconds = int(sum(durations) / len(durations))
                    target_count = target_attempts.get(mode)
                    scalable_rows = [
                        row for row in rows
                        if row.attempted_count and row.attempted_count > 0 and row.duration_seconds
                    ]

                    if target_count and len(scalable_rows) >= 3:
                        seconds_per_attempt = [
                            row.duration_seconds / row.attempted_count
                            for row in scalable_rows
                        ]
                        estimate_seconds = max(1, int(round(_median(seconds_per_attempt) * target_count)))

                    estimates[mode] = {
                        "avg_seconds": estimate_seconds,
                        "last_seconds": durations[0],
                        "scaled": bool(target_count and len(scalable_rows) >= 3)
                    }
    except Exception as e:
        logger.error(f"Failed to get time estimates: {e}")

    return estimates


DEFAULT_MAX_RECIPES = 50        # Default fetch limit for new/unconfigured scrapers
UNLIMITED_SCRAPERS = {'myrecipes'}  # These scrapers default to "all" (no limit)
SCRAPER_INACTIVITY_TIMEOUT_SECONDS = 5 * 60

# Sentinel: scraper has a config row → respect its values (even if NULL = "all")
_HAS_CONFIG = object()


def _get_scraper_configs() -> dict:
    """Get all scraper configs from DB. Returns {scraper_id: {max_recipes_full, max_recipes_incremental}}."""
    try:
        with get_db_session() as db:
            result = db.execute(text("SELECT scraper_id, max_recipes_full, max_recipes_incremental FROM scraper_config"))
            return {
                row.scraper_id: {
                    "max_recipes_full": row.max_recipes_full,
                    "max_recipes_incremental": row.max_recipes_incremental,
                    "_has_config": True,
                }
                for row in result
            }
    except Exception as e:
        # Table might not exist yet — silently return empty
        logger.debug(f"Could not fetch scraper configs (table may not exist): {e}")
        return {}


def _get_effective_config(scraper_id: str, configs: dict) -> tuple:
    """Return (max_full, max_incr) applying defaults for unconfigured scrapers."""
    config = configs.get(scraper_id, {})
    if config.get("_has_config"):
        # Explicit config row exists — use its values (NULL = user chose "all")
        return config.get("max_recipes_full"), config.get("max_recipes_incremental")
    if scraper_id in UNLIMITED_SCRAPERS:
        return None, None
    return DEFAULT_MAX_RECIPES, DEFAULT_MAX_RECIPES


def _format_duration(seconds: int) -> str:
    """Format duration in seconds to human-readable string (language-neutral)."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} min"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if minutes > 0:
            return f"{hours}h {minutes} min"
        return f"{hours}h"


def _get_cache_generation() -> str | None:
    """Return current cache generation timestamp for client-side invalidation."""
    try:
        with get_db_session() as db:
            result = db.execute(text("""
                SELECT last_computed_at FROM cache_metadata
                WHERE cache_name = 'recipe_offer_matches'
            """)).fetchone()
            if result and result.last_computed_at:
                return result.last_computed_at.isoformat()
    except Exception:
        pass  # Don't fail preview requests if metadata is temporarily unavailable.
    return None


def _build_matching_preview_payload(max_results: int, parsed_exclude: list[str]) -> dict:
    """Run sync DB/cache/matching work outside the async request handler."""
    from recipe_matcher import RecipeMatcher, get_effective_matching_preferences

    prefs = get_effective_matching_preferences()
    matcher = RecipeMatcher()
    recipes = matcher.match_all_recipes(
        prefs,
        max_results=max_results,
        exclude_ids=parsed_exclude,
    )

    balance = prefs.get('balance', {
        MEAT: 3,
        FISH: 3,
        VEGETARIAN: 3,
        'smart_buy': 3
    }).copy()

    # Zero out excluded categories so frontend hides their tabs.
    exclude_cats = prefs.get('exclude_categories', [])
    if any(cat in exclude_cats for cat in [MEAT, POULTRY, DELI]):
        balance[MEAT] = 0
    if FISH in exclude_cats:
        balance[FISH] = 0

    return {
        "success": True,
        "recipes": recipes,
        "count": len(recipes),
        "balance": balance,
        "cache_generation": _get_cache_generation()
    }


# ==================== RECIPE SEARCH ====================

@router.get("/recipe-search")
@limiter.limit(settings.rate_limit_search)
def recipe_search(request: Request, q: str = "", limit: int = 50, offset: int = 0, source: str = ""):
    """Search recipes by name or ingredient using PostgreSQL Full-Text Search."""
    try:
        from languages.matcher_runtime import get_recipe_fts_config_backend, normalize_market_text
        from recipe_matcher import get_enabled_recipe_sources

        raw_query = normalize_market_text(q.strip().lower())
        fts_config = get_recipe_fts_config_backend()
        source_filter = source.strip() if source else ""

        # Allow empty query if source filter is set (browse all from source)
        if (not raw_query or len(raw_query) < 2) and not source_filter:
            return JSONResponse({
                "success": False,
                "message_key": "recipes.search_min_2_chars"
            }, status_code=422)

        # Parse search terms with boolean operators (AND, OR, -)
        # Examples: "glass choklad" = AND, "glass OR choklad" = OR,
        #           "glass -choklad" = glass AND NOT choklad
        tsquery = None
        search_terms = []

        if raw_query:
            tokens = raw_query.replace(',', ' ').split()
            tsquery_parts = []
            next_op = '&'  # Default operator between terms

            for token in tokens:
                token = token.strip()
                if not token:
                    continue

                # Boolean operators
                upper = token.upper()
                if upper in ('OR', 'ELLER'):
                    next_op = '|'
                    continue
                if upper in ('AND', 'OCH'):
                    next_op = '&'
                    continue

                # NOT prefix
                negate = False
                if token.startswith('-') and len(token) > 1:
                    negate = True
                    token = token[1:]

                clean_term = ''.join(c for c in token if c.isalpha())
                if len(clean_term) < 2:
                    continue

                search_terms.append(('-' if negate else '') + clean_term)
                # Use :* suffix for prefix matching — "lch" matches "lchf", "lchfpizza" etc.
                term_expr = f'!{clean_term}:*' if negate else f'{clean_term}:*'
                if tsquery_parts:
                    tsquery_parts.append(next_op)
                tsquery_parts.append(term_expr)
                next_op = '&'  # Reset to AND

            if tsquery_parts:
                tsquery = ' '.join(tsquery_parts)

        if not tsquery and not source_filter:
            return JSONResponse({
                "success": False,
                "message_key": "recipes.no_valid_search_terms"
            }, status_code=422)

        limit = min(max(1, limit), 100)
        offset = max(0, offset)

        enabled_sources = get_enabled_recipe_sources()

        # If source filter is set, restrict to that single source (if enabled)
        if source_filter:
            if enabled_sources and source_filter not in enabled_sources:
                return JSONResponse({
                    "success": True,
                    "query": raw_query,
                    "search_terms": search_terms,
                    "recipes": [],
                    "total": 0,
                    "has_more": False,
                    "offset": offset
                })
            query_sources = [source_filter]
        else:
            query_sources = list(enabled_sources) if enabled_sources else None

        with get_db_session() as db:
            fetch_limit = limit + 1

            if tsquery:
                # FTS search, optionally filtered by source
                if query_sources:
                    sql = text("""
                        WITH parsed AS (
                            SELECT to_tsquery(CAST(:fts_config AS regconfig), :query) AS q
                        )
                        SELECT id, name, url, source_name, image_url, local_image_path,
                               prep_time_minutes, servings, ingredients
                        FROM found_recipes, parsed
                        WHERE search_vector @@ parsed.q
                        AND source_name = ANY(:sources)
                        AND (excluded = FALSE OR excluded IS NULL)
                        ORDER BY ts_rank(search_vector, parsed.q) DESC
                        LIMIT :limit OFFSET :offset
                    """)
                    rows = db.execute(sql, {
                        "query": tsquery,
                        "fts_config": fts_config,
                        "sources": query_sources,
                        "limit": fetch_limit,
                        "offset": offset
                    }).fetchall()
                else:
                    sql = text("""
                        WITH parsed AS (
                            SELECT to_tsquery(CAST(:fts_config AS regconfig), :query) AS q
                        )
                        SELECT id, name, url, source_name, image_url, local_image_path,
                               prep_time_minutes, servings, ingredients
                        FROM found_recipes, parsed
                        WHERE search_vector @@ parsed.q
                        AND (excluded = FALSE OR excluded IS NULL)
                        ORDER BY ts_rank(search_vector, parsed.q) DESC
                        LIMIT :limit OFFSET :offset
                    """)
                    rows = db.execute(sql, {
                        "query": tsquery,
                        "fts_config": fts_config,
                        "limit": fetch_limit,
                        "offset": offset
                    }).fetchall()
            else:
                # No search query — browse all recipes from source, sorted by name
                sql = text("""
                    SELECT id, name, url, source_name, image_url, local_image_path,
                           prep_time_minutes, servings, ingredients
                    FROM found_recipes
                    WHERE source_name = ANY(:sources)
                    AND (excluded = FALSE OR excluded IS NULL)
                    ORDER BY name
                    LIMIT :limit OFFSET :offset
                """)
                rows = db.execute(sql, {
                    "sources": query_sources,
                    "limit": fetch_limit,
                    "offset": offset
                }).fetchall()

            has_more = len(rows) > limit
            if has_more:
                rows = rows[:limit]

            recipes = []
            recipe_ids = []
            for row in rows:
                rid = str(row.id)
                recipes.append({
                    "id": rid,
                    "name": row.name,
                    "url": row.url,
                    "source": row.source_name,
                    "image_url": row.local_image_path or row.image_url,
                    "prep_time_minutes": row.prep_time_minutes,
                    "servings": row.servings,
                    "ingredients": row.ingredients or []
                })
                recipe_ids.append(rid)

            # Enrich with offer cache data (savings, matched offers)
            if recipe_ids:
                cache_rows = db.execute(text("""
                    SELECT found_recipe_id, total_savings, num_matches, match_data
                    FROM recipe_offer_cache
                    WHERE found_recipe_id = ANY(CAST(:ids AS uuid[]))
                """), {"ids": recipe_ids}).fetchall()
                cache_map = {}
                for crow in cache_rows:
                    md = crow.match_data or {}
                    cache_map[str(crow.found_recipe_id)] = {
                        "total_savings": float(crow.total_savings or 0),
                        "num_matches": crow.num_matches or 0,
                        "matched_offers": md.get("matched_offers", []),
                        "ingredient_groups": md.get("ingredient_groups", []),
                        "avg_savings_pct": md.get("total_savings_pct", 0),
                    }

                for r in recipes:
                    cd = cache_map.get(r["id"], {})
                    r["total_savings"] = cd.get("total_savings", 0)
                    r["num_matches"] = cd.get("num_matches", 0)
                    r["matched_offers"] = cd.get("matched_offers", [])
                    r["ingredient_groups"] = cd.get("ingredient_groups", [])
                    r["avg_savings_pct"] = cd.get("avg_savings_pct", 0)

            return JSONResponse({
                "success": True,
                "query": raw_query,
                "search_terms": search_terms,
                "recipes": recipes,
                "total": len(recipes),
                "has_more": has_more,
                "offset": offset
            })

    except Exception as e:
        logger.error(f"Error in recipe search: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        })


# ==================== MATCHING PREFERENCES ====================

@router.get("/matching/preferences")
def get_matching_preferences():
    """API endpoint to get matching preferences."""
    try:
        with get_db_session() as db:
            row = db.execute(text("""
                SELECT
                    exclude_meat, exclude_fish, exclude_dairy,
                    exclude_keywords, filtered_products, local_meat_only,
                    balance_meat, balance_fish, balance_veg, balance_budget,
                    excluded_brands,
                    ranking_mode, min_ingredients, max_ingredients
                FROM matching_preferences
                LIMIT 1
            """)).mappings().fetchone()

            if row:
                return JSONResponse({
                    "success": True,
                    "preferences": {
                        "exclude_meat": row['exclude_meat'] or False,
                        "exclude_fish": row['exclude_fish'] or False,
                        "exclude_dairy": row['exclude_dairy'] or False,
                        "exclude_keywords": row['exclude_keywords'] or [],
                        "filtered_products": row['filtered_products'] or [],
                        "local_meat_only": row['local_meat_only'] if row['local_meat_only'] is not None else True,
                        "balance_meat": float(row['balance_meat']) if row['balance_meat'] is not None else 3.0,
                        "balance_fish": float(row['balance_fish']) if row['balance_fish'] is not None else 3.0,
                        "balance_veg": float(row['balance_veg']) if row['balance_veg'] is not None else 3.0,
                        "balance_budget": float(row['balance_budget']) if row['balance_budget'] is not None else 3.0,
                        "excluded_brands": row['excluded_brands'] or [],
                        "ranking_mode": row['ranking_mode'] or 'absolute',
                        "min_ingredients": int(row['min_ingredients'] or 0),
                        "max_ingredients": int(row['max_ingredients'] or 0)
                    }
                })
            else:
                return JSONResponse({
                    "success": True,
                    "preferences": {
                        "exclude_meat": False,
                        "exclude_fish": False,
                        "exclude_dairy": False,
                        "exclude_keywords": [],
                        "filtered_products": [],
                        "local_meat_only": True,
                        "balance_meat": 3.0,
                        "balance_fish": 3.0,
                        "balance_veg": 3.0,
                        "balance_budget": 3.0,
                        "excluded_brands": [],
                        "ranking_mode": "absolute",
                        "min_ingredients": 0,
                        "max_ingredients": 0
                    }
                })

    except Exception as e:
        logger.error(f"Error fetching matching preferences: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        })


@router.post("/matching/preferences")
async def save_matching_preferences(request: Request):
    """API endpoint to save matching preferences."""
    try:
        data = await request.json()

        exclude_meat = bool(data.get('exclude_meat', False))
        exclude_fish = bool(data.get('exclude_fish', False))
        exclude_dairy = bool(data.get('exclude_dairy', False))
        exclude_keywords = data.get('exclude_keywords', [])
        filtered_products = data.get('filtered_products', [])
        excluded_brands = data.get('excluded_brands', [])
        local_meat_only = bool(data.get('local_meat_only', True))

        balance_meat = max(0.0, min(4.0, float(data.get('balance_meat', 3.0))))
        balance_fish = max(0.0, min(4.0, float(data.get('balance_fish', 3.0))))
        balance_veg = max(0.0, min(4.0, float(data.get('balance_veg', 3.0))))
        balance_budget = max(0.0, min(4.0, float(data.get('balance_budget', 3.0))))

        ranking_mode = data.get('ranking_mode', 'absolute')
        if ranking_mode not in ('absolute', 'percentage'):
            ranking_mode = 'absolute'

        min_ingredients = max(0, min(30, int(data.get('min_ingredients', 0))))
        max_ingredients = max(0, min(30, int(data.get('max_ingredients', 0))))

        if not isinstance(exclude_keywords, list):
            exclude_keywords = []
        if not isinstance(filtered_products, list):
            filtered_products = []
        if not isinstance(excluded_brands, list):
            excluded_brands = []
        # Keep original case - comparison is done case-insensitively in filtering code
        excluded_brands = [b.strip() for b in excluded_brands if isinstance(b, str) and b.strip()]

        with get_db_session() as db:
            db.execute(text("""
                INSERT INTO matching_preferences (
                    exclude_meat, exclude_fish, exclude_dairy,
                    exclude_keywords, filtered_products, excluded_brands, local_meat_only,
                    balance_meat, balance_fish, balance_veg, balance_budget,
                    ranking_mode, min_ingredients, max_ingredients
                ) VALUES (
                    :exclude_meat, :exclude_fish, :exclude_dairy,
                    :exclude_keywords, :filtered_products, :excluded_brands, :local_meat_only,
                    :balance_meat, :balance_fish, :balance_veg, :balance_budget,
                    :ranking_mode, :min_ingredients, :max_ingredients
                )
                ON CONFLICT (singleton_key) DO UPDATE SET
                    exclude_meat = EXCLUDED.exclude_meat,
                    exclude_fish = EXCLUDED.exclude_fish,
                    exclude_dairy = EXCLUDED.exclude_dairy,
                    exclude_keywords = EXCLUDED.exclude_keywords,
                    filtered_products = EXCLUDED.filtered_products,
                    excluded_brands = EXCLUDED.excluded_brands,
                    local_meat_only = EXCLUDED.local_meat_only,
                    balance_meat = EXCLUDED.balance_meat,
                    balance_fish = EXCLUDED.balance_fish,
                    balance_veg = EXCLUDED.balance_veg,
                    balance_budget = EXCLUDED.balance_budget,
                    ranking_mode = EXCLUDED.ranking_mode,
                    min_ingredients = EXCLUDED.min_ingredients,
                    max_ingredients = EXCLUDED.max_ingredients,
                    updated_at = NOW()
            """), {
                "exclude_meat": exclude_meat,
                "exclude_fish": exclude_fish,
                "exclude_dairy": exclude_dairy,
                "exclude_keywords": json.dumps(exclude_keywords),
                "filtered_products": json.dumps(filtered_products),
                "excluded_brands": json.dumps(excluded_brands),
                "local_meat_only": local_meat_only,
                "balance_meat": balance_meat,
                "balance_fish": balance_fish,
                "balance_veg": balance_veg,
                "balance_budget": balance_budget,
                "ranking_mode": ranking_mode,
                "min_ingredients": min_ingredients,
                "max_ingredients": max_ingredients
            })

            db.commit()

        return JSONResponse({
            "success": True,
            "message_key": "preferences.saved"
        })

    except Exception as e:
        logger.error(f"Error saving matching preferences: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        })


@router.api_route("/matching/preview", methods=["GET", "POST"])
@limiter.limit(settings.rate_limit_global)
async def get_matching_preview(request: Request, max_results: int = 12, exclude_ids: str = ""):
    """API endpoint to preview matched recipes with pagination.
    Supports both GET (query params) and POST (JSON body) for large exclude lists.
    """
    try:
        # POST: read exclude_ids from JSON body (avoids URL length limits)
        if request.method == "POST":
            body = await request.json()
            parsed_exclude = body.get("exclude_ids", [])
            max_results = body.get("max_results", max_results)
        else:
            # GET: parse comma-separated exclude IDs from query string
            parsed_exclude = [id.strip() for id in exclude_ids.split(",") if id.strip()] if exclude_ids else []

        payload = await run_in_threadpool(
            _build_matching_preview_payload,
            max_results,
            parsed_exclude,
        )
        return JSONResponse(payload)

    except Exception as e:
        logger.error(f"Error getting matching preview: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e),
            "recipes": [],
            "balance": {}
        })


# ==================== CACHE MANAGEMENT ====================

@router.get("/cache/status")
def get_cache_status():
    """Get current cache status (for polling during rebuild)."""
    try:
        from cache_manager import cache_manager

        runtime_status = cache_manager.get_runtime_rebuild_status()
        with get_db_session() as db:
            result = db.execute(text("""
                SELECT status, total_matches, computation_time_ms,
                       last_background_rebuild_at, background_rebuild_source
                FROM cache_metadata
                WHERE cache_name = 'recipe_offer_matches'
            """)).fetchone()

            if result:
                return JSONResponse({
                    "success": True,
                    "status": result.status,
                    "ready": result.status == 'ready',
                    "total_matches": result.total_matches,
                    "time_ms": result.computation_time_ms,
                    "last_background_rebuild_at": result.last_background_rebuild_at.isoformat() if result.last_background_rebuild_at else None,
                    "background_rebuild_source": result.background_rebuild_source,
                    **runtime_status,
                })
            else:
                return JSONResponse({
                    "success": True,
                    "status": "unknown",
                    "ready": False,
                    **runtime_status,
                })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "status": "error",
            "ready": False,
            "message_key": friendly_error(e)
        })


@router.get("/cache/doctor")
def get_cache_doctor():
    """Run read-only cache consistency diagnostics."""
    try:
        from cache_doctor import run_cache_doctor

        return JSONResponse({
            "success": True,
            **run_cache_doctor(),
        })
    except Exception as e:
        logger.error(f"Error running cache doctor: {e}")
        return JSONResponse({
            "success": False,
            "status": "error",
            "message_key": friendly_error(e),
        }, status_code=500)


MAX_SSE_SUBSCRIBERS = 10

@router.get("/events/cache")
async def cache_events():
    """SSE stream for cache rebuild notifications.

    Replaces 30s polling. Clients connect with EventSource and receive
    events instantly when a background scrape completes and the cache rebuilds.
    """
    if event_bus.subscriber_count() >= MAX_SSE_SUBSCRIBERS:
        return JSONResponse(
            {"success": False, "message_key": "error.rate_limited"},
            status_code=429
        )

    async def generate():
        q = event_bus.subscribe()
        try:
            while True:
                event = await q.get()
                yield f"data: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(q)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/cache/reset")
@limiter.limit(settings.rate_limit_heavy_compute)
async def reset_recipe_cache(request: Request):
    """Reset the recipe-offer cache by rebuilding it from scratch."""
    try:
        from cache_manager import compute_cache_async

        logger.info("Cache reset requested - starting rebuild...")
        # Set status to 'computing' BEFORE starting background task
        # to prevent race condition where first poll sees old 'ready' status
        with get_db_session() as db:
            db.execute(text("""
                UPDATE cache_metadata SET status = 'computing'
                WHERE cache_name = 'recipe_offer_matches'
            """))
            db.commit()
        create_background_task(compute_cache_async(), name="cache-reset")

        return JSONResponse({
            "success": True,
            "message_key": "recipes.cache_rebuild_started"
        })

    except Exception as e:
        logger.error(f"Error resetting cache: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        })


# ==================== RECIPE SCRAPERS ====================

@router.get("/recipe-scrapers")
def get_recipe_scrapers():
    """Get all available recipe scrapers with their status."""
    if not RECIPE_SCRAPERS_AVAILABLE:
        return JSONResponse({
            "success": False,
            "message_key": "recipes.not_available"
        }, status_code=500)

    scrapers = scraper_manager.get_all_scrapers()

    # Fetch starred status for all sources
    starred_sources = {}
    try:
        with get_db_session() as db:
            result = db.execute(text("SELECT name, is_starred FROM recipe_sources"))
            for row in result:
                starred_sources[row.name] = row.is_starred or False
    except Exception as e:
        logger.warning(f"Could not fetch starred sources: {e}")

    # Fetch per-scraper config (fetch limits)
    scraper_configs = _get_scraper_configs()

    scraper_list = []
    for s in scrapers:
        # Use db_source_name for database lookup (may differ from display name)
        db_name = s.db_source_name or s.name
        max_full, max_incr = _get_effective_config(s.id, scraper_configs)
        estimate_targets = {
            "test": 20,
            "incremental": max_incr,
            "full": max_full or s.expected_recipe_count,
        }
        estimates = _get_time_estimates(s.id, estimate_targets)
        scraper_data = {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "expected_recipe_count": s.expected_recipe_count,
            "source_url": s.source_url,
            "enabled": s.enabled,
            "is_starred": starred_sources.get(db_name, False),
            "recipe_count": s.recipe_count,
            "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
            "database_size_kb": round(s.database_size_kb, 1),
            "warning": s.warning if hasattr(s, 'warning') else "",
            "max_recipes_full": max_full,
            "max_recipes_incremental": max_incr,
            "time_estimates": {}
        }

        for mode in ['test', 'incremental', 'full']:
            if mode in estimates:
                est = estimates[mode]
                scraper_data["time_estimates"][mode] = {
                    "avg_seconds": est["avg_seconds"],
                    "formatted": _format_duration(est["avg_seconds"]),
                    "last_seconds": est.get("last_seconds")
                }

        scraper_list.append(scraper_data)

    return JSONResponse({
        "success": True,
        "scrapers": scraper_list
    })


@router.post("/recipe-scrapers/{scraper_id}/enable")
async def enable_recipe_scraper(scraper_id: str):
    """Enable a recipe scraper."""
    if not RECIPE_SCRAPERS_AVAILABLE:
        return JSONResponse({"success": False, "message_key": "error.not_available"}, status_code=500)

    success = scraper_manager.set_scraper_enabled(scraper_id, True)
    if success:
        try:
            from cache_manager import compute_cache_async
            create_background_task(compute_cache_async(), name=f"cache-rebuild-enable-{scraper_id}")
            logger.info(f"Started cache rebuild after enabling {scraper_id}")
        except Exception as e:
            logger.warning(f"Could not start cache rebuild: {e}")
        return JSONResponse({"success": True, "message_key": "recipes.scraper_enabled", "message_params": {"id": scraper_id}})
    return JSONResponse({"success": False, "message_key": "recipes.scraper_not_found"}, status_code=404)


@router.post("/recipe-scrapers/{scraper_id}/disable")
async def disable_recipe_scraper(scraper_id: str):
    """Disable a recipe scraper."""
    if not RECIPE_SCRAPERS_AVAILABLE:
        return JSONResponse({"success": False, "message_key": "error.not_available"}, status_code=500)

    success = scraper_manager.set_scraper_enabled(scraper_id, False)
    if success:
        try:
            from cache_manager import compute_cache_async
            create_background_task(compute_cache_async(), name=f"cache-rebuild-disable-{scraper_id}")
            logger.info(f"Started cache rebuild after disabling {scraper_id}")
        except Exception as e:
            logger.warning(f"Could not start cache rebuild: {e}")
        return JSONResponse({"success": True, "message_key": "recipes.scraper_disabled", "message_params": {"id": scraper_id}})
    return JSONResponse({"success": False, "message_key": "recipes.scraper_not_found"}, status_code=404)


@router.post("/recipe-scrapers/{scraper_id}/star")
async def toggle_recipe_scraper_star(scraper_id: str):
    """Toggle starred (favorite) status for a recipe scraper."""
    if not RECIPE_SCRAPERS_AVAILABLE:
        return JSONResponse({"success": False, "message_key": "error.not_available"}, status_code=500)

    scraper_info = scraper_manager.get_scraper(scraper_id)
    if not scraper_info:
        return JSONResponse({"success": False, "message_key": "recipes.scraper_not_found"}, status_code=404)

    # Use db_source_name for database lookup (may differ from display name)
    db_name = scraper_info.db_source_name or scraper_info.name

    try:
        scraper_manager.ensure_scraper_registered(scraper_id, enabled=scraper_info.enabled)

        with get_db_session() as db:
            # Get current starred status
            result = db.execute(text("""
                SELECT is_starred FROM recipe_sources WHERE name = :name
            """), {"name": db_name}).fetchone()

            if result is None:
                return JSONResponse({"success": False, "message_key": "recipes.source_not_found"}, status_code=404)

            # Toggle the status
            new_status = not (result.is_starred or False)

            db.execute(text("""
                UPDATE recipe_sources SET is_starred = :starred, updated_at = NOW()
                WHERE name = :name
            """), {"starred": new_status, "name": db_name})
            db.commit()

            # Rebuild cache to reflect new starred status in ranking
            try:
                from cache_manager import compute_cache_async
                create_background_task(compute_cache_async(), name=f"cache-rebuild-star-{scraper_id}")
                logger.info(f"Started cache rebuild after toggling star for {scraper_id}")
            except Exception as e:
                logger.warning(f"Could not start cache rebuild: {e}")

            return JSONResponse({
                "success": True,
                "is_starred": new_status,
                "message_key": "recipes.star_toggled" if new_status else "recipes.star_removed",
                "message_params": {"name": scraper_info.name}
            })

    except Exception as e:
        logger.error(f"Error toggling star for {scraper_id}: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.post("/recipe-scrapers/{scraper_id}/config")
async def update_scraper_config(scraper_id: str, request: Request):
    """Update per-scraper recipe fetch limits."""
    if not RECIPE_SCRAPERS_AVAILABLE:
        return JSONResponse({"success": False, "message_key": "error.not_available"}, status_code=500)

    scraper_info = scraper_manager.get_scraper(scraper_id)
    if not scraper_info:
        return JSONResponse({"success": False, "message_key": "recipes.scraper_not_found"}, status_code=404)

    body = await request.json()
    max_full = body.get("max_recipes_full")
    max_incr = body.get("max_recipes_incremental")

    # Validate: must be None or int 1-9999
    for val, label in [(max_full, "full"), (max_incr, "incremental")]:
        if val is not None:
            try:
                val_int = int(val)
                if val_int < 1 or val_int > 9999:
                    return JSONResponse({"success": False, "message_key": "recipes.config_invalid"}, status_code=400)
            except (TypeError, ValueError):
                return JSONResponse({"success": False, "message_key": "recipes.config_invalid"}, status_code=400)

    max_full = int(max_full) if max_full is not None else None
    max_incr = int(max_incr) if max_incr is not None else None

    try:
        with get_db_session() as db:
            db.execute(text("""
                INSERT INTO scraper_config (scraper_id, max_recipes_full, max_recipes_incremental, updated_at)
                VALUES (:sid, :full, :incr, NOW())
                ON CONFLICT (scraper_id)
                DO UPDATE SET max_recipes_full = :full, max_recipes_incremental = :incr, updated_at = NOW()
            """), {"sid": scraper_id, "full": max_full, "incr": max_incr})
            db.commit()

        return JSONResponse({
            "success": True,
            "message_key": "recipes.config_saved",
            "max_recipes_full": max_full,
            "max_recipes_incremental": max_incr,
        })
    except Exception as e:
        logger.error(f"Error saving scraper config for {scraper_id}: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


# ========== CUSTOM RECIPE URLS (Mina Recept) ==========

@router.get("/recipe-scrapers/custom/urls")
def get_custom_urls():
    """Get all custom recipe URLs."""
    try:
        with get_db_session() as db:
            result = db.execute(text(
                "SELECT id, url, label, status, retry_count, last_error, created_at FROM custom_recipe_urls ORDER BY id"
            ))
            urls = [{
                "id": row.id,
                "url": row.url,
                "label": row.label,
                "status": row.status,
                "retry_count": row.retry_count,
                "last_error": row.last_error,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            } for row in result]

        return JSONResponse({"success": True, "urls": urls})
    except Exception as e:
        logger.error(f"Error fetching custom URLs: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.post("/recipe-scrapers/custom/urls")
async def add_custom_url(request: Request):
    """Add a new custom recipe URL."""
    body = await request.json()
    url = (body.get("url") or "").strip()

    if not url:
        return JSONResponse({"success": False, "message_key": "myrecipes.url_required"}, status_code=400)

    # Basic URL validation
    if not url.startswith(("http://", "https://")):
        return JSONResponse({"success": False, "message_key": "myrecipes.url_invalid"}, status_code=400)

    # Extract domain for per-domain limit
    from urllib.parse import urlparse
    try:
        domain = urlparse(url).hostname or ""
    except Exception:
        return JSONResponse({"success": False, "message_key": "myrecipes.url_invalid"}, status_code=400)

    MAX_PENDING_URLS = 500
    MAX_PER_DOMAIN = 200

    try:
        with get_db_session() as db:
            # Check for duplicate
            existing = db.execute(
                text("SELECT id FROM custom_recipe_urls WHERE url = :url"),
                {"url": url}
            ).fetchone()

            if existing:
                return JSONResponse({"success": False, "message_key": "myrecipes.url_duplicate"}, status_code=409)

            # Limit total pending URLs (prevents bulk abuse as outbound proxy)
            pending_count = db.execute(
                text("SELECT COUNT(*) FROM custom_recipe_urls WHERE status = 'pending'")
            ).scalar()
            if pending_count >= MAX_PENDING_URLS:
                return JSONResponse({"success": False, "message_key": "myrecipes.too_many_pending"}, status_code=429)

            # Limit per domain (prevents concentrated attack on one target)
            domain_count = db.execute(
                text("SELECT COUNT(*) FROM custom_recipe_urls WHERE url LIKE :pattern AND status = 'pending'"),
                {"pattern": f"%://{domain}/%"}
            ).scalar()
            if domain_count >= MAX_PER_DOMAIN:
                return JSONResponse({"success": False, "message_key": "myrecipes.too_many_same_domain"}, status_code=429)

            db.execute(
                text("INSERT INTO custom_recipe_urls (url) VALUES (:url)"),
                {"url": url}
            )
            db.commit()

            # Get the inserted row
            row = db.execute(
                text("SELECT id, url, label, status, retry_count, last_error, created_at FROM custom_recipe_urls WHERE url = :url"),
                {"url": url}
            ).fetchone()

        return JSONResponse({
            "success": True,
            "url_entry": {
                "id": row.id,
                "url": row.url,
                "label": row.label,
                "status": row.status,
                "retry_count": row.retry_count,
                "last_error": row.last_error,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        })
    except Exception as e:
        logger.error(f"Error adding custom URL: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.delete("/recipe-scrapers/custom/urls/{url_id}")
def delete_custom_url(url_id: int):
    """Delete a custom recipe URL and its associated recipe."""
    try:
        with get_db_session() as db:
            result = db.execute(
                text("DELETE FROM custom_recipe_urls WHERE id = :id RETURNING url"),
                {"id": url_id}
            )
            deleted = result.fetchone()
            if not deleted:
                db.commit()
                return JSONResponse({"success": False, "message_key": "myrecipes.url_not_found"}, status_code=404)

            deleted_url = deleted.url
            image_paths = db.execute(
                text("""
                    SELECT local_image_path
                    FROM found_recipes
                    WHERE url = :url
                      AND source_name = 'My Recipes'
                      AND local_image_path IS NOT NULL
                      AND local_image_path != ''
                """),
                {"url": deleted_url}
            ).scalars().all()

            # Also remove the recipe from found_recipes (if it was scraped by this scraper)
            db.execute(
                text("DELETE FROM found_recipes WHERE url = :url AND source_name = 'My Recipes'"),
                {"url": deleted_url}
            )
            db.commit()

        image_cleanup = delete_unreferenced_recipe_image_files(
            image_paths,
            reason="custom_recipe_url_delete",
        )

        return JSONResponse({
            "success": True,
            "deleted_url": deleted_url,
            "images_deleted": image_cleanup["deleted_count"],
        })
    except Exception as e:
        logger.error(f"Error deleting custom URL {url_id}: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.delete("/recipe-scrapers/{scraper_id}/recipes")
def clear_scraper_recipes(scraper_id: str):
    """Delete all recipes from a specific scraper (only if disabled)."""
    if not RECIPE_SCRAPERS_AVAILABLE:
        return JSONResponse({"success": False, "message_key": "error.not_available"}, status_code=500)

    scraper_info = scraper_manager.get_scraper(scraper_id)
    if not scraper_info:
        return JSONResponse({"success": False, "message_key": "recipes.scraper_not_found"}, status_code=404)

    if scraper_info.enabled:
        return JSONResponse({
            "success": False,
            "message_key": "recipes.clear_inactive_only"
        }, status_code=400)

    db_name = scraper_info.db_source_name or scraper_info.name

    try:
        with get_db_session() as db:
            image_paths = db.execute(
                text("""
                    SELECT local_image_path
                    FROM found_recipes
                    WHERE source_name = :source_name
                      AND local_image_path IS NOT NULL
                      AND local_image_path != ''
                """),
                {"source_name": db_name}
            ).scalars().all()

            del_result = db.execute(
                text("DELETE FROM found_recipes WHERE source_name = :source_name"),
                {"source_name": db_name}
            )
            deleted_count = del_result.rowcount
            db.commit()

        image_cleanup = delete_unreferenced_recipe_image_files(
            image_paths,
            reason=f"clear_scraper_recipes:{scraper_id}",
        )
        images_deleted = image_cleanup["deleted_count"]
        try:
            from scrapers.recipes.url_discovery_cache import clear_source_discovery_cache

            discovery_deleted = clear_source_discovery_cache(db_name)
        except Exception as e:
            discovery_deleted = 0
            logger.debug(f"Could not clear URL discovery cache for {scraper_id}: {e}")

        logger.info(
            f"Cleared {deleted_count} recipes, {images_deleted} local images, "
            f"and {discovery_deleted} URL discovery rows for {scraper_id}"
        )

        return JSONResponse({
            "success": True,
            "message_key": "recipes.deleted_count",
            "message_params": {"recipes": deleted_count, "images": images_deleted, "name": scraper_info.name},
            "deleted_count": deleted_count,
            "images_deleted": images_deleted,
            "discovery_deleted": discovery_deleted,
        })
    except Exception as e:
        logger.error(f"Error clearing recipes for {scraper_id}: {e}")
        return JSONResponse({
            "success": False,
            "message_key": "recipes.delete_error",
            "message_params": {"error": friendly_error(e)}
        }, status_code=500)


@router.get("/recipe-scrapers/running")
async def get_running_recipe_scraper():
    """Check if any recipe scraper is currently running."""
    # Snapshot the dict to avoid iteration issues
    for scraper_id, status in list(running_scrapers.items()):
        state = await get_running_scraper(scraper_id)
        if state and state.get("running"):
            return JSONResponse({
                "success": True,
                "running": True,
                "scraper_id": scraper_id,
                **state
            })

    return JSONResponse({
        "success": True,
        "running": False,
        "scraper_id": None
    })


@router.get("/recipe-scrapers/queue")
async def get_recipe_scraper_queue():
    """Get current run-all queue state."""
    state = await get_run_all_queue()
    if state.get("active"):
        public_fields = {"active", "scraper_ids", "index", "total_new"}
        return JSONResponse({
            "success": True,
            **{key: value for key, value in state.items() if key in public_fields},
        })
    return JSONResponse({"success": True, "active": False})


def _coerce_nonnegative_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _iso_timestamp_at_or_after(value: str | None, threshold: str | None) -> bool:
    if not value or not threshold:
        return False
    try:
        parsed_value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        parsed_threshold = datetime.fromisoformat(threshold.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return parsed_value >= parsed_threshold


def _dedupe_recipe_id_list(values) -> list[str]:
    recipe_ids: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        if value is None:
            continue
        recipe_id = str(value)
        if recipe_id in seen:
            continue
        recipe_ids.append(recipe_id)
        seen.add(recipe_id)
    return recipe_ids


def _extract_recipe_delta_ids(save_result: dict | None) -> tuple[list[str], list[str]]:
    if not isinstance(save_result, dict):
        return [], []
    removed_ids = _dedupe_recipe_id_list(save_result.get("removed_recipe_ids"))
    removed_set = set(removed_ids)
    changed_ids = _dedupe_recipe_id_list(
        save_result.get("changed_recipe_ids")
        or (
            list(save_result.get("created_recipe_ids") or [])
            + list(save_result.get("updated_recipe_ids") or [])
        )
    )
    changed_ids = [recipe_id for recipe_id in changed_ids if recipe_id not in removed_set]
    return changed_ids, removed_ids


def _save_result_has_cache_changes(save_result: dict | None) -> bool:
    if not isinstance(save_result, dict):
        return False
    changed_ids, removed_ids = _extract_recipe_delta_ids(save_result)
    if changed_ids or removed_ids:
        return True
    return any(
        _coerce_nonnegative_int(save_result.get(key)) > 0
        for key in ("created", "updated", "saved", "deleted")
    )


def _merge_recipe_delta_ids(
    existing_changed_ids,
    existing_removed_ids,
    new_changed_ids,
    new_removed_ids,
) -> tuple[list[str], list[str]]:
    removed_ids = _dedupe_recipe_id_list(
        list(existing_removed_ids or []) + list(new_removed_ids or [])
    )
    removed_set = set(removed_ids)
    changed_ids = [
        recipe_id
        for recipe_id in _dedupe_recipe_id_list(
            list(existing_changed_ids or []) + list(new_changed_ids or [])
        )
        if recipe_id not in removed_set
    ]
    return changed_ids, removed_ids


def _recipe_delta_ids_missing(save_result: dict | None, changed_ids: list[str], removed_ids: list[str]) -> bool:
    return _save_result_has_cache_changes(save_result) and not changed_ids and not removed_ids


def _cache_metadata_status_from_snapshot(snapshot: RecipeCacheStatusSnapshot) -> dict:
    return snapshot.to_cache_state()


def _set_cache_metadata_status(status: str, error_message: str | None = None) -> None:
    with get_db_session() as db:
        db.execute(text("""
            INSERT INTO cache_metadata (cache_name, status, error_message)
            VALUES ('recipe_offer_matches', :status, :error_message)
            ON CONFLICT (cache_name) DO UPDATE SET
                status = :status,
                error_message = :error_message
        """), {"status": status, "error_message": error_message})
        db.commit()


def _scheduled_recipe_batch_active() -> bool:
    try:
        from scheduler import scraper_scheduler

        return bool(scraper_scheduler.recipe_batch_active())
    except Exception as e:
        logger.debug(f"Could not inspect scheduled recipe batch state: {e}")
        return False


async def _refresh_cache_after_recipe_scrape(
    *,
    scraper_id: str,
    mode: str,
    save_result: dict | None,
    recipes_found: int,
) -> dict:
    from cache_manager import compute_cache_async

    changed_ids, removed_ids = _extract_recipe_delta_ids(save_result)
    ids_missing = _recipe_delta_ids_missing(save_result, changed_ids, removed_ids)
    cache_snapshot = load_recipe_cache_status_snapshot()
    decision = decide_recipe_cache_refresh_strategy(
        changed_ids,
        removed_ids,
        ids_missing,
        source_kind="recipe_scrape",
        mode=mode,
        cache_status_snapshot=cache_snapshot,
    )
    source = f"recipe_scrape:{scraper_id}:{mode}"
    operation_context = decision.to_operation_context()
    logger.info(decision.log_summary(label=f"Recipe scrape cache decision ({scraper_id})"))

    delta_result = None
    result = None
    if decision.uses_delta:
        try:
            from cache_delta import apply_recipe_delta, _recipe_delta_probation_history_path
            from delta_probation_runtime import append_runtime_probation_history

            logger.info(
                "Starting recipe-delta cache refresh after {scraper} scrape "
                "({changed} changed, {removed} removed, reason={reason})".format(
                    scraper=scraper_id,
                    changed=len(changed_ids),
                    removed=len(removed_ids),
                    reason=decision.reason,
                )
            )
            loop = asyncio.get_running_loop()
            delta_result = await loop.run_in_executor(
                None,
                lambda: apply_recipe_delta(
                    changed_recipe_ids=changed_ids,
                    removed_recipe_ids=removed_ids,
                    source=source,
                    apply=True,
                    verify_full_preview=settings.cache_recipe_delta_verify_full_preview,
                    skip_if_busy=False,
                    operation_context=operation_context,
                ),
            )
            try:
                append_runtime_probation_history(
                    delta_result,
                    history_path=_recipe_delta_probation_history_path(),
                    store_name=scraper_id,
                    trigger="recipe_scrape",
                )
            except Exception as history_error:
                logger.warning(f"Could not append recipe-delta probation history: {history_error}")
            result = delta_result
        except Exception as e:
            logger.warning(
                f"Recipe-delta cache refresh failed after {scraper_id} scrape ({e}); "
                "falling back to full rebuild"
            )
            delta_result = {
                "success": False,
                "applied": False,
                "fallback_reason": "recipe_delta_exception",
                "error": str(e),
            }

        if not delta_result.get("applied"):
            fallback_reason = delta_result.get("fallback_reason") or "recipe_delta_not_applied"
            logger.warning(
                f"Recipe-delta was not applied after {scraper_id} scrape "
                f"({fallback_reason}); falling back to full rebuild"
            )
            result = await compute_cache_async(
                skip_if_busy=False,
                run_kind="recipe_delta_fallback_full_rebuild",
                source=source,
                operation_context={
                    **operation_context,
                    "trigger_reason": f"delta_apply_failed:{fallback_reason}",
                },
            )
    elif decision.strategy == "full":
        logger.info(
            f"Starting full cache rebuild after {scraper_id} scrape "
            f"({recipes_found} new recipes, delta_reason={decision.reason})"
        )
        result = await compute_cache_async(
            skip_if_busy=False,
            run_kind="recipe_scrape_full_rebuild",
            source=source,
            operation_context=operation_context,
        )
    else:
        result = {
            "success": True,
            "skipped": True,
            "reason": decision.reason,
            "effective_rebuild_mode": "noop",
            "cached": 0,
            "time_ms": 0,
        }

    if result.get("skipped"):
        logger.info(f"Recipe scrape cache refresh skipped: {result.get('reason')}")
    else:
        logger.success(
            "Recipe scrape cache refresh complete ({mode}): {cached} recipes in {time_ms}ms".format(
                mode=result.get("effective_rebuild_mode", "unknown"),
                cached=result.get("cached", 0),
                time_ms=result.get("time_ms", 0),
            )
        )
    return result


async def _refresh_cache_after_run_all_queue(
    *,
    queue_state: dict,
    decision: RecipeCacheRefreshDecision,
    cache_snapshot: RecipeCacheStatusSnapshot,
) -> dict:
    from cache_manager import compute_cache_async

    changed_ids = _dedupe_recipe_id_list(queue_state.get("changed_recipe_ids"))
    removed_ids = _dedupe_recipe_id_list(queue_state.get("removed_recipe_ids"))
    source = "recipe_run_all"
    operation_context = decision.to_operation_context()
    result = None

    try:
        logger.info(decision.log_summary(label="Run-all cache decision"))
        if decision.uses_delta:
            from cache_delta import apply_recipe_delta, _recipe_delta_probation_history_path
            from delta_probation_runtime import append_runtime_probation_history

            delta_result = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: apply_recipe_delta(
                    changed_recipe_ids=changed_ids,
                    removed_recipe_ids=removed_ids,
                    source=source,
                    apply=True,
                    verify_full_preview=settings.cache_recipe_delta_verify_full_preview,
                    skip_if_busy=False,
                    cache_status_snapshot=_cache_metadata_status_from_snapshot(cache_snapshot),
                    operation_context=operation_context,
                ),
            )
            try:
                append_runtime_probation_history(
                    delta_result,
                    history_path=_recipe_delta_probation_history_path(),
                    store_name="run_all",
                    trigger="recipe_run_all",
                )
            except Exception as history_error:
                logger.warning(f"Could not append run-all recipe-delta history: {history_error}")

            if delta_result.get("applied"):
                result = delta_result
            else:
                fallback_reason = delta_result.get("fallback_reason") or "recipe_delta_not_applied"
                logger.warning(
                    f"Run-all recipe-delta was not applied ({fallback_reason}); "
                    "falling back to full rebuild"
                )
                result = await compute_cache_async(
                    skip_if_busy=False,
                    run_kind="recipe_delta_fallback_full_rebuild",
                    source=source,
                    operation_context={
                        **operation_context,
                        "trigger_reason": f"delta_apply_failed:{fallback_reason}",
                    },
                )
        elif decision.strategy == "full":
            result = await compute_cache_async(
                skip_if_busy=False,
                run_kind="recipe_run_all_full_rebuild",
                source=source,
                operation_context=operation_context,
            )
        else:
            _set_cache_metadata_status("ready")
            result = {
                "success": True,
                "skipped": True,
                "reason": decision.reason,
                "effective_rebuild_mode": "noop",
                "cached": 0,
                "time_ms": 0,
            }

        if result.get("skipped"):
            logger.info(f"Run-all cache refresh skipped: {result.get('reason')}")
        else:
            logger.success(
                "Run-all cache refresh complete ({mode}): {cached} recipes in {time_ms}ms".format(
                    mode=result.get("effective_rebuild_mode", "unknown"),
                    cached=result.get("cached", result.get("patch_result", {}).get("total_matches", 0)),
                    time_ms=result.get("time_ms", 0),
                )
            )
        return result
    except Exception as exc:
        try:
            _set_cache_metadata_status("error", str(exc))
        except Exception as status_error:
            logger.warning(f"Could not mark run-all cache refresh error: {status_error}")
        logger.warning(f"Run-all cache refresh failed: {exc}")
        raise


async def _finish_run_all_queue(total_new: int) -> dict:
    """Finish the run-all queue and start once-per-queue follow-up jobs."""
    total_new = _coerce_nonnegative_int(total_new)
    for scraper_id in list(running_scrapers.keys()):
        state = await get_running_scraper(scraper_id)
        if state and state.get("running"):
            logger.info(
                f"Run-all finish deferred because scraper {scraper_id} is still running"
            )
            return {
                "cache_rebuild_started": False,
                "cache_rebuild_kind": "noop",
                "auto_image_download_started": False,
                "finish_deferred": True,
                "running_scraper_id": scraper_id,
            }

    queue_state = await claim_run_all_queue_finish()
    if not queue_state.get("active"):
        cache_rebuild_started = False
        try:
            with get_db_session() as db:
                row = db.execute(text("""
                    SELECT status
                    FROM cache_metadata
                    WHERE cache_name = 'recipe_offer_matches'
                """)).fetchone()
                cache_rebuild_started = bool(row and row.status == "computing")
        except Exception as e:
            logger.debug(f"Could not inspect cache status for duplicate run-all finish: {e}")

        logger.info("Run-all finish ignored because the queue is already inactive")
        return {
            "cache_rebuild_started": cache_rebuild_started,
            "cache_rebuild_kind": "unknown" if cache_rebuild_started else "noop",
            "auto_image_download_started": False,
            "already_finished": True,
        }

    changed_ids = _dedupe_recipe_id_list(queue_state.get("changed_recipe_ids"))
    removed_ids = _dedupe_recipe_id_list(queue_state.get("removed_recipe_ids"))
    ids_missing = bool(queue_state.get("cache_delta_ids_missing"))
    total_cache_changes = (
        len(set(changed_ids) | set(removed_ids))
        if not ids_missing
        else max(1, _coerce_nonnegative_int(queue_state.get("total_cache_changes")))
    )

    cache_rebuild_started = False
    cache_rebuild_kind = "noop"
    auto_image_download_started = False
    if total_cache_changes > 0 or ids_missing:
        try:
            cache_snapshot = load_recipe_cache_status_snapshot()
            decision = decide_recipe_cache_refresh_strategy(
                changed_ids,
                removed_ids,
                ids_missing,
                source_kind="recipe_run_all",
                mode="incremental",
                cache_status_snapshot=cache_snapshot,
            )

            if decision.requires_cache_refresh:
                _set_cache_metadata_status("computing")

                create_background_task(
                    _refresh_cache_after_run_all_queue(
                        queue_state={
                            **queue_state,
                            "changed_recipe_ids": changed_ids,
                            "removed_recipe_ids": removed_ids,
                        },
                        decision=decision,
                        cache_snapshot=cache_snapshot,
                    ),
                    name="cache-refresh-run-all-recipes",
                )
                event_bus.publish({
                    "type": "cache_invalidated",
                    "source": "recipes-run-all",
                })
                cache_rebuild_started = True
                cache_rebuild_kind = decision.strategy
                logger.info(
                    "Started final cache refresh after run-all recipe scrape "
                    f"({total_new} new recipes, {total_cache_changes} cache-affecting changes, "
                    f"strategy={decision.strategy}, reason={decision.reason})"
                )
            else:
                logger.info(f"Run-all cache refresh not needed ({decision.reason})")
        except Exception as e:
            logger.warning(f"Could not start final run-all cache rebuild: {e}")
            try:
                _set_cache_metadata_status("error", str(e))
            except Exception as status_error:
                logger.warning(f"Could not mark failed run-all cache start: {status_error}")

        try:
            from utils.image_auto_download import trigger_auto_download_if_enabled

            auto_image_download_started = await trigger_auto_download_if_enabled()
            if auto_image_download_started:
                logger.info("Started auto image download after run-all recipe scrape finished")
        except Exception as e:
            logger.warning(f"Could not start final run-all image download: {e}")

    return {
        "cache_rebuild_started": cache_rebuild_started,
        "cache_rebuild_kind": cache_rebuild_kind,
        "auto_image_download_started": auto_image_download_started,
    }


async def _start_recipe_scraper_background(scraper_id: str, mode: str, scraper_info=None):
    """Start a scraper background task after caller has done validation/locking."""
    scraper_info = scraper_info or scraper_manager.get_scraper(scraper_id)
    if not scraper_info:
        return None

    await update_running_scraper(scraper_id, {
        "running": True,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "status": "starting",
        "message_key": "recipes.starting_fetch"
    }, replace=True)

    task = asyncio.create_task(_run_scraper_task(scraper_id, mode))
    scraper_tasks[scraper_id] = task

    def _scraper_task_done(t: asyncio.Task, sid=scraper_id):
        scraper_tasks.pop(sid, None)
        if not t.cancelled() and t.exception():
            logger.error(f"Scraper task {sid!r} failed: {t.exception()}")

    task.add_done_callback(_scraper_task_done)
    return scraper_info


async def _resume_run_all_queue_if_stalled(completed_scraper_id: str, completed_new_recipes: int) -> None:
    """Resume run-all if the browser did not advance the queue after completion."""
    await asyncio.sleep(10)

    queue_state = await get_run_all_queue()
    if not queue_state.get("active"):
        return

    scraper_ids = queue_state.get("scraper_ids") or []
    index = _coerce_nonnegative_int(queue_state.get("index"))
    if index >= len(scraper_ids) or scraper_ids[index] != completed_scraper_id:
        return

    next_index = index + 1
    total_new = _coerce_nonnegative_int(queue_state.get("total_new")) + _coerce_nonnegative_int(completed_new_recipes)

    if next_index >= len(scraper_ids):
        logger.info("Run-all queue was not finalized by client; finishing from backend")
        await _finish_run_all_queue(total_new)
        return

    next_scraper_id = scraper_ids[next_index]
    await update_run_all_queue(index=next_index, total_new=total_new)

    # If the client woke up and started something while we were waiting, leave it alone.
    for sid in list(running_scrapers.keys()):
        state = await get_running_scraper(sid)
        if state and state.get("running"):
            return

    lock = get_scraper_lock(next_scraper_id)
    async with lock:
        state = await get_running_scraper(next_scraper_id)
        if state and state.get("running"):
            return

        scraper_info = scraper_manager.get_scraper(next_scraper_id)
        if not scraper_info:
            logger.warning(f"Run-all backend resume skipped missing scraper: {next_scraper_id}")
            return

        await _start_recipe_scraper_background(next_scraper_id, "incremental", scraper_info)
        logger.info(
            f"Run-all queue resumed by backend: {completed_scraper_id} -> {next_scraper_id} "
            f"({next_index + 1}/{len(scraper_ids)})"
        )


@router.post("/recipe-scrapers/queue")
async def manage_recipe_scraper_queue(request: Request):
    """Manage the run-all queue. Actions: start, advance, finish, cancel."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"success": False, "message": "Invalid JSON"}, status_code=400)

    action = body.get("action")

    if action == "start":
        scraper_ids = body.get("scraper_ids", [])
        if not scraper_ids:
            return JSONResponse({"success": False, "message": "No scrapers provided"}, status_code=400)
        if _scheduled_recipe_batch_active():
            return JSONResponse({
                "success": False,
                "message_key": "recipes.scheduled_scraper_running",
            }, status_code=409)
        existing = await get_run_all_queue()
        if existing.get("active"):
            return JSONResponse({"success": False, "message": "Queue already active"}, status_code=409)
        await set_run_all_queue({
            "active": True,
            "scraper_ids": scraper_ids,
            "index": 0,
            "total_new": 0,
            "total_cache_changes": 0,
            "changed_recipe_ids": [],
            "removed_recipe_ids": [],
            "cache_delta_ids_missing": False,
            "started_at": datetime.now(timezone.utc).isoformat(),
        })
        return JSONResponse({"success": True})

    elif action == "advance":
        requested_index = body.get("index")
        requested_total_new = _coerce_nonnegative_int(body.get("total_new", 0))
        if requested_index is None:
            return JSONResponse({"success": False, "message": "index required"}, status_code=400)
        requested_index = _coerce_nonnegative_int(requested_index)

        queue_state = await get_run_all_queue()
        if not queue_state.get("active"):
            return JSONResponse({"success": True, "active": False})

        current_index = _coerce_nonnegative_int(queue_state.get("index"))
        current_total_new = _coerce_nonnegative_int(queue_state.get("total_new"))
        stale_advance = requested_index <= current_index
        next_index = max(current_index, requested_index)
        total_new = current_total_new if stale_advance else max(current_total_new, requested_total_new)

        await update_run_all_queue(index=next_index, total_new=total_new)
        return JSONResponse({
            "success": True,
            "active": True,
            "index": next_index,
            "total_new": total_new,
            "stale_advance": stale_advance,
        })

    elif action == "finish":
        total_new = _coerce_nonnegative_int(body.get("total_new", 0))
        finish_state = await _finish_run_all_queue(total_new)

        return JSONResponse({
            "success": True,
            **finish_state,
        })

    elif action == "cancel":
        await clear_run_all_queue()
        return JSONResponse({"success": True})

    return JSONResponse({"success": False, "message": "Unknown action"}, status_code=400)


@router.post("/recipe-scrapers/{scraper_id}/run")
@limiter.limit(settings.rate_limit_scraper_run)
async def run_recipe_scraper(scraper_id: str, request: Request):
    """Run a recipe scraper."""
    if not RECIPE_SCRAPERS_AVAILABLE:
        return JSONResponse({"success": False, "message_key": "error.not_available"}, status_code=500)

    if _scheduled_recipe_batch_active():
        return JSONResponse({
            "success": False,
            "message_key": "recipes.scheduled_scraper_running",
        }, status_code=409)

    lock = get_scraper_lock(scraper_id)

    async with lock:
        state = await get_running_scraper(scraper_id)
        if state and state.get("running"):
            return JSONResponse({
                "success": False,
                "message_key": "recipes.scraper_already_running",
                "message_params": {"id": scraper_id}
            }, status_code=409)

        scraper_info = scraper_manager.get_scraper(scraper_id)
        if not scraper_info:
            return JSONResponse({"success": False, "message_key": "recipes.scraper_not_found"}, status_code=404)

        try:
            body = await request.json()
            mode = body.get("mode", "incremental")
        except (json.JSONDecodeError, ValueError):
            mode = "incremental"

        if mode not in ("test", "incremental", "full"):
            return JSONResponse({
                "success": False,
                "message_key": "recipes.invalid_mode",
                "message_params": {"mode": mode}
            }, status_code=400)

        queue_state = await get_run_all_queue()
        queue_ids = queue_state.get("scraper_ids") or []
        queue_index = _coerce_nonnegative_int(queue_state.get("index"))
        queue_current_id = queue_ids[queue_index] if queue_index < len(queue_ids) else None
        if (
            queue_state.get("active")
            and mode == "incremental"
            and scraper_id == queue_current_id
            and state
            and state.get("running") is False
            and state.get("status") == "complete"
            and _iso_timestamp_at_or_after(state.get("started_at"), queue_state.get("started_at"))
        ):
            logger.info(
                f"Run-all ignored duplicate start for already-complete scraper {scraper_id} "
                f"at queue index {queue_index}"
            )
            return JSONResponse({
                "success": True,
                "already_complete": True,
                "message_key": "recipes.fetch_complete",
                "mode": mode,
            })

        image_state = await get_image_state()
        if image_state.get("running"):
            return JSONResponse({
                "success": False,
                "message_key": "recipes.wait_for_image_download"
            }, status_code=409)

        await update_running_scraper(scraper_id, {
            "running": True,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "status": "starting",
            "message_key": "recipes.starting_fetch"
        }, replace=True)

        task = asyncio.create_task(_run_scraper_task(scraper_id, mode))
        scraper_tasks[scraper_id] = task

        def _scraper_task_done(t: asyncio.Task, sid=scraper_id):
            scraper_tasks.pop(sid, None)
            if not t.cancelled() and t.exception():
                logger.error(f"Scraper task {sid!r} failed: {t.exception()}")

        task.add_done_callback(_scraper_task_done)

    return JSONResponse({
        "success": True,
        "message_key": "recipes.scraper_started",
        "message_params": {"name": scraper_info.name, "mode": mode},
        "mode": mode
    })


async def _run_scraper_task(scraper_id: str, mode: str):
    """Background task that runs the scraper."""
    start_time = time.time()
    last_progress_at = time.monotonic()
    recipes_found = 0
    attempted_count = 0
    save_result_for_cache = {}

    try:
        scraper_class = scraper_manager.get_scraper_class(scraper_id)
        scraper_info = scraper_manager.get_scraper(scraper_id)
        if not scraper_class:
            await update_running_scraper(scraper_id, {
                "running": False,
                "status": "error",
                "message_key": "recipes.could_not_find_scraper"
            })
            return

        scraper = scraper_class()
        await update_running_scraper(scraper_id, {
            "status": "running",
            "message_key": "recipes.fetching_recipes"
        })

        expected_total = scraper_info.expected_recipe_count if scraper_info else 1000
        scraper_configs = _get_scraper_configs()
        max_full, max_incr = _get_effective_config(scraper_id, scraper_configs)

        # Mode labels are now i18n keys
        mode_label_keys = {"test": "recipes.mode_test", "incremental": "recipes.mode_incremental", "full": "recipes.mode_full"}
        mode_label_key = mode_label_keys.get(mode, mode)
        db_source_name = (scraper_info.db_source_name or scraper_info.name) if scraper_info else None

        def mark_scraper_activity() -> None:
            nonlocal last_progress_at
            last_progress_at = time.monotonic()

        async def await_with_inactivity_timeout(coro, phase: str):
            task = asyncio.create_task(coro)
            try:
                while True:
                    done, _ = await asyncio.wait({task}, timeout=10)
                    if task in done:
                        return await task

                    inactive_seconds = time.monotonic() - last_progress_at
                    if inactive_seconds >= SCRAPER_INACTIVITY_TIMEOUT_SECONDS:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                        raise TimeoutError(
                            f"Recipe scraper timed out after {int(inactive_seconds)}s "
                            f"inactive during {phase}"
                        )
            finally:
                if not task.done():
                    task.cancel()

        async def progress_callback(data: dict):
            nonlocal attempted_count
            mark_scraper_activity()
            if data.get("activity_only"):
                return

            current = data.get("current", 0)
            total = data.get("total", expected_total)
            found = _coerce_nonnegative_int(data.get("success", 0))
            attempted_count = max(attempted_count, _coerce_nonnegative_int(current))

            display_current = current
            display_total = total
            if mode == "incremental" and max_incr and "success" in data:
                display_total = max(1, _coerce_nonnegative_int(max_incr))
                display_current = min(display_total, found)

            percent = round((display_current / display_total) * 100) if display_total > 0 else 0

            await update_running_scraper(scraper_id, {
                "message_key": "recipes.fetching_progress",
                "message_params": {"current": display_current, "total": display_total, "percent": percent},
                "current": display_current,
                "total": display_total,
                "recipes_found": found,
                "percent": percent
            })

        if hasattr(scraper, 'set_progress_callback'):
            scraper.set_progress_callback(progress_callback)

        def get_final_attempted_count() -> int | None:
            progress = getattr(scraper, "_progress", None)
            current = 0
            if isinstance(progress, dict):
                current = _coerce_nonnegative_int(progress.get("current"))
            final_count = max(attempted_count, current)
            return final_count if final_count > 0 else None

        def get_total_recipe_count():
            try:
                db_name = (scraper_info.db_source_name or scraper_info.name) if scraper_info else None
                if not db_name:
                    return 0
                with get_db_session() as db:
                    result = db.execute(
                        text("SELECT COUNT(*) FROM found_recipes WHERE source_name = :source"),
                        {"source": db_name}
                    ).scalar()
                    return result or 0
            except Exception:
                return 0

        def normalize_result(raw_result, run_mode: str):
            return normalize_recipe_scrape_result(
                raw_result,
                mode=run_mode,
                source_name=db_source_name,
            )

        def normalize_saved_result(save_result, run_mode: str):
            if not isinstance(save_result, dict):
                return normalize_result([], run_mode)
            status = save_result.get("scrape_status")
            if not status:
                saved_count = (
                    _coerce_nonnegative_int(save_result.get("saved"))
                    + _coerce_nonnegative_int(save_result.get("created"))
                    + _coerce_nonnegative_int(save_result.get("updated"))
                )
                status = "success" if saved_count > 0 else "success_empty"
            return normalize_result({
                "status": status,
                "recipes": [],
                "reason": save_result.get("scrape_reason"),
                "message_key": save_result.get("message_key"),
                "message_params": save_result.get("message_params") or {},
            }, run_mode)

        async def handle_terminal_scrape_result(scrape_result) -> bool:
            if scrape_result.status == "cancelled":
                await update_running_scraper(scraper_id, {
                    "running": False,
                    "status": "cancelled",
                    "message_key": "recipes.fetch_cancelled",
                    "mode": mode,
                    "mode_label_key": mode_label_key,
                }, replace=True)
                return True
            if scrape_result.status == "failed":
                raise RuntimeError(scrape_result.reason or "recipe_scrape_failed")
            return False

        def note_for_result(scrape_result, run_mode: str) -> str:
            if run_mode == "test":
                return "recipes.test_not_saved" if len(scrape_result) else "recipes.test_empty_not_saved"
            if scrape_result.status == "no_new_recipes":
                return "recipes.no_new_recipes"
            if scrape_result.status == "success_empty" and run_mode == "full":
                return "recipes.full_empty_kept"
            if scrape_result.status == "success_empty" and run_mode == "incremental":
                return "recipes.no_saveable_recipes_found"
            if scrape_result.status == "success_empty":
                return "recipes.no_recipes_found"
            if scrape_result.status == "partial":
                return "recipes.partial_result"
            return scrape_result.message_key

        if mode == "test":
            scrape_result = normalize_result(
                await await_with_inactivity_timeout(
                    scraper.scrape_all_recipes(max_recipes=20),
                    "test scrape",
                ),
                "test",
            )
            if await handle_terminal_scrape_result(scrape_result):
                return
            recipes_found = len(scrape_result)
            total_in_db = get_total_recipe_count()
            await update_running_scraper(scraper_id, {
                "running": False,
                "status": "complete",
                "message_key": "recipes.fetch_complete",
                "message_params": {"mode": mode_label_key},
                "mode": mode,
                "mode_label_key": mode_label_key,
                "new_recipes": len(scrape_result),
                "total_in_db": total_in_db,
                "note_key": note_for_result(scrape_result, "test")
            }, replace=True)
        elif mode == "full":
            await update_running_scraper(scraper_id, {"message_key": "recipes.fetching_all"})
            result = {}
            scrape_result = None
            if hasattr(scraper, 'scrape_and_save'):
                result = await await_with_inactivity_timeout(
                    scraper.scrape_and_save(overwrite=True, max_recipes=max_full),
                    "full scrape",
                )
                scrape_result = normalize_saved_result(result, "full")
                if await handle_terminal_scrape_result(scrape_result):
                    return
            else:
                scrape_result = normalize_result(
                    await await_with_inactivity_timeout(
                        scraper.scrape_all_recipes(force_all=True, max_recipes=max_full),
                        "full scrape",
                    ),
                    "full",
                )
                if await handle_terminal_scrape_result(scrape_result):
                    return
                scraper_module = scraper_manager.get_module(scraper_id)
                save_to_database = getattr(scraper_module, 'save_to_database')
                if scrape_result.should_save or scrape_result.is_empty:
                    result = save_to_database(scrape_result, clear_old=True)

            new_count = (
                result.get("saved", result.get("created", 0))
                if isinstance(result, dict) else 0
            )
            save_result_for_cache = result if isinstance(result, dict) else {}
            spell_count = result.get("spell_corrections", 0) if isinstance(result, dict) else 0
            recipes_found = new_count
            total_in_db = get_total_recipe_count()
            state = {
                "running": False,
                "status": "complete",
                "message_key": "recipes.fetch_complete",
                "message_params": {"mode": mode_label_key},
                "mode": mode,
                "mode_label_key": mode_label_key,
                "new_recipes": new_count,
                "total_in_db": total_in_db,
            }
            note_key = note_for_result(scrape_result, "full") if scrape_result else None
            if note_key:
                state["note_key"] = note_key
            if spell_count > 0:
                state["spell_corrections"] = spell_count
            await update_running_scraper(scraper_id, state, replace=True)
        else:
            result = {}
            if hasattr(scraper, 'scrape_and_save'):
                result = await await_with_inactivity_timeout(
                    scraper.scrape_and_save(overwrite=False, max_recipes=max_incr),
                    "incremental scrape",
                )
                scrape_result = normalize_saved_result(result, "incremental")
                if await handle_terminal_scrape_result(scrape_result):
                    return
                new_count = result.get("created", 0) if isinstance(result, dict) else 0
            elif max_incr and hasattr(scraper, 'scrape_all_recipes'):
                # User-configured incremental limit — use scrape_all_recipes with max_recipes
                scrape_result = normalize_result(
                    await await_with_inactivity_timeout(
                        scraper.scrape_all_recipes(max_recipes=max_incr),
                        "incremental scrape",
                    ),
                    "incremental",
                )
                scraper_module = scraper_manager.get_module(scraper_id)
                save_to_database = getattr(scraper_module, 'save_to_database')
                if await handle_terminal_scrape_result(scrape_result):
                    return
                if scrape_result.should_save:
                    result = save_to_database(scrape_result, clear_old=False)
                    new_count = result.get("created", 0) if isinstance(result, dict) else 0
                else:
                    new_count = 0
            elif hasattr(scraper, 'scrape_incremental'):
                scrape_result = normalize_result(
                    await await_with_inactivity_timeout(
                        scraper.scrape_incremental(),
                        "incremental scrape",
                    ),
                    "incremental",
                )
                scraper_module = scraper_manager.get_module(scraper_id)
                save_to_database = getattr(scraper_module, 'save_to_database')
                if await handle_terminal_scrape_result(scrape_result):
                    return
                if scrape_result.should_save:
                    result = save_to_database(scrape_result, clear_old=False)
                    new_count = result.get("created", 0) if isinstance(result, dict) else 0
                else:
                    new_count = 0
            else:
                scrape_result = normalize_result(
                    await await_with_inactivity_timeout(
                        scraper.scrape_all_recipes(),
                        "incremental scrape",
                    ),
                    "incremental",
                )
                scraper_module = scraper_manager.get_module(scraper_id)
                save_to_database = getattr(scraper_module, 'save_to_database')
                if await handle_terminal_scrape_result(scrape_result):
                    return
                result = save_to_database(scrape_result, clear_old=False) if scrape_result.should_save else {}
                new_count = result.get("created", 0) if isinstance(result, dict) else 0

            spell_count = result.get("spell_corrections", 0) if isinstance(result, dict) else 0
            save_result_for_cache = result if isinstance(result, dict) else {}
            recipes_found = new_count
            total_in_db = get_total_recipe_count()
            state = {
                "running": False,
                "status": "complete",
                "message_key": "recipes.fetch_complete",
                "message_params": {"mode": mode_label_key},
                "mode": mode,
                "mode_label_key": mode_label_key,
                "new_recipes": new_count,
                "total_in_db": total_in_db,
            }
            note_key = note_for_result(scrape_result, "incremental")
            if note_key:
                state["note_key"] = note_key
            if spell_count > 0:
                state["spell_corrections"] = spell_count
            await update_running_scraper(scraper_id, state, replace=True)

        duration = int(time.time() - start_time)
        save_run_history(
            scraper_id,
            mode,
            duration,
            recipes_found,
            attempted_count=get_final_attempted_count(),
            success=True,
            update_schedule=True,
        )

        # Trigger cache refresh + image auto-download (only for non-test modes with DB changes).
        # During "run all", defer both until the queue is finished so the
        # recipe scrapers do not compete with image downloads.
        if mode != "test" and _save_result_has_cache_changes(save_result_for_cache):
            queue_state = await get_run_all_queue()
            if queue_state.get("active"):
                changed_ids, removed_ids = _extract_recipe_delta_ids(save_result_for_cache)
                merged_changed_ids, merged_removed_ids = _merge_recipe_delta_ids(
                    queue_state.get("changed_recipe_ids"),
                    queue_state.get("removed_recipe_ids"),
                    changed_ids,
                    removed_ids,
                )
                ids_missing = bool(queue_state.get("cache_delta_ids_missing")) or (
                    _save_result_has_cache_changes(save_result_for_cache)
                    and not changed_ids
                    and not removed_ids
                )
                total_cache_changes = (
                    len(set(merged_changed_ids) | set(merged_removed_ids))
                    if not ids_missing
                    else max(1, _coerce_nonnegative_int(queue_state.get("total_cache_changes")))
                )
                await update_run_all_queue(
                    changed_recipe_ids=merged_changed_ids,
                    removed_recipe_ids=merged_removed_ids,
                    cache_delta_ids_missing=ids_missing,
                    total_cache_changes=total_cache_changes,
                )
                logger.info(
                    f"Deferred cache rebuild and image auto-download after {scraper_id} scrape because "
                    f"run-all queue is active ({recipes_found} new recipes)"
                )
            else:
                create_background_task(
                    _refresh_cache_after_recipe_scrape(
                        scraper_id=scraper_id,
                        mode=mode,
                        save_result=save_result_for_cache,
                        recipes_found=recipes_found,
                    ),
                    name=f"cache-refresh-scraper-{scraper_id}",
                )
                logger.info(f"Started cache refresh after {scraper_id} scrape ({recipes_found} new recipes)")

                from utils.image_auto_download import trigger_auto_download_if_enabled
                await trigger_auto_download_if_enabled()

        if mode == "incremental":
            queue_state = await get_run_all_queue()
            if queue_state.get("active"):
                create_background_task(
                    _resume_run_all_queue_if_stalled(scraper_id, recipes_found),
                    name=f"run-all-resume-{scraper_id}",
                )

    except asyncio.CancelledError:
        logger.info(f"Scraper {scraper_id} was cancelled")
        raise
    except Exception as e:
        logger.error(f"Scraper {scraper_id} failed: {e}")
        await update_running_scraper(scraper_id, {
            "running": False,
            "status": "error",
            "message_key": "recipes.error_prefix",
            "message_params": {"error": friendly_error(e)}
        }, replace=True)
        duration = int(time.time() - start_time)
        save_run_history(
            scraper_id,
            mode,
            duration,
            recipes_found,
            attempted_count=attempted_count if attempted_count > 0 else None,
            success=False,
            error_message=str(e),
        )

        if mode == "incremental":
            queue_state = await get_run_all_queue()
            if queue_state.get("active"):
                create_background_task(
                    _resume_run_all_queue_if_stalled(scraper_id, 0),
                    name=f"run-all-resume-after-error-{scraper_id}",
                )


@router.get("/recipe-scrapers/{scraper_id}/status")
async def get_recipe_scraper_status(scraper_id: str):
    """Get the current status of a scraper."""
    state = await get_running_scraper(scraper_id)
    if state:
        return JSONResponse({
            "success": True,
            **state
        })

    scraper_info = scraper_manager.get_scraper(scraper_id)
    if not scraper_info:
        return JSONResponse({"success": False, "message_key": "recipes.scraper_not_found"}, status_code=404)

    return JSONResponse({
        "success": True,
        "running": False,
        "status": "idle",
        "message_key": "recipes.ready_to_run",
        "last_run_at": scraper_info.last_run_at.isoformat() if scraper_info.last_run_at else None,
        "recipe_count": scraper_info.recipe_count
    })


@router.post("/recipe-scrapers/{scraper_id}/cancel")
async def cancel_recipe_scraper(scraper_id: str):
    """Cancel a running scraper task."""
    state = await get_running_scraper(scraper_id)
    if not state or not state.get("running"):
        return JSONResponse({
            "success": False,
            "message_key": "recipes.no_active_fetch"
        }, status_code=404)

    if scraper_id in scraper_tasks:
        task = scraper_tasks[scraper_id]
        if not task.done():
            task.cancel()
            try:
                await task
            except BaseException:
                pass
        scraper_tasks.pop(scraper_id, None)

    await update_running_scraper(scraper_id, {
        "running": False,
        "status": "cancelled",
        "message_key": "recipes.fetch_cancelled"
    }, replace=True)

    logger.info(f"Scraper {scraper_id} cancelled by user")

    return JSONResponse({
        "success": True,
        "message_key": "recipes.fetch_cancelled"
    })


# ============================================================================
# RECIPE EXCLUSION (hide/restore)
# ============================================================================

def _run_recipe_visibility_cache_refresh(recipe_ids: list[str], *, excluded: bool, source: str) -> None:
    if not recipe_ids:
        logger.debug(f"Skipping recipe visibility cache refresh without recipe ids ({source})")
        return

    try:
        from cache_delta import apply_recipe_delta, _recipe_delta_probation_history_path
        from delta_probation_runtime import append_runtime_probation_history

        delta_result = apply_recipe_delta(
            changed_recipe_ids=[] if excluded else recipe_ids,
            removed_recipe_ids=recipe_ids if excluded else [],
            source=source,
            apply=True,
            verify_full_preview=settings.cache_recipe_delta_verify_full_preview,
            skip_if_busy=False,
        )
        try:
            append_runtime_probation_history(
                delta_result,
                history_path=_recipe_delta_probation_history_path(),
                store_name="recipes-ui",
                trigger=source,
            )
        except Exception as history_error:
            logger.warning(f"Could not append recipe-delta probation history: {history_error}")
        if delta_result.get("applied"):
            logger.info(
                f"Recipe visibility cache delta applied ({source}, {len(recipe_ids)} recipes)"
            )
            return
        logger.warning(
            "Recipe visibility cache delta was not applied "
            f"({delta_result.get('fallback_reason')}); falling back to full rebuild"
        )

        from cache_manager import refresh_cache_locked

        result = refresh_cache_locked(skip_if_busy=False)
        if result.get("skipped"):
            logger.info(f"Recipe visibility cache rebuild skipped: {result.get('reason')}")
        else:
            logger.info(
                "Recipe visibility cache rebuild complete: "
                f"{result.get('cached', 0)} recipes in {result.get('time_ms', 0)}ms"
            )
    except Exception as e:
        logger.warning(f"Recipe visibility cache refresh failed ({source}): {e}")


def _notify_recipe_visibility_changed(recipe_id=None, excluded: bool = True, recipe_ids=None) -> None:
    """Refresh cache/index state after hide, restore, or hard-delete actions."""
    ids = _dedupe_recipe_id_list(recipe_ids if recipe_ids is not None else ([recipe_id] if recipe_id else []))
    source = "ui_exclude_or_delete" if excluded else "ui_restore"
    thread = threading.Thread(
        target=_run_recipe_visibility_cache_refresh,
        kwargs={"recipe_ids": ids, "excluded": excluded, "source": source},
        name=f"recipe-visibility-cache-{source}",
        daemon=True,
    )
    thread.start()


@router.patch("/recipes/{recipe_id}/exclude")
def exclude_recipe(recipe_id: str):
    """
    Mark a recipe as excluded (hidden).
    The recipe won't show in searches and won't be re-scraped.
    """
    if not is_valid_uuid(recipe_id):
        return JSONResponse({"success": False, "message_key": "error.invalid_data"}, status_code=400)
    try:
        with get_db_session() as db:
            from models import FoundRecipe
            recipe = db.query(FoundRecipe).filter(FoundRecipe.id == recipe_id).first()
            if not recipe:
                return JSONResponse({"success": False, "message_key": "recipes.recipe_not_found"}, status_code=404)

            recipe.excluded = True
            db.commit()
            _notify_recipe_visibility_changed(recipe_id, excluded=True)

            logger.info(f"Recipe excluded: {recipe.name} (ID: {recipe_id})")

            return JSONResponse({
                "success": True,
                "message_key": "recipes.recipe_hidden",
                "recipe_id": recipe_id,
                "recipe_name": recipe.name
            })
    except Exception as e:
        logger.error(f"Error excluding recipe {recipe_id}: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.patch("/recipes/{recipe_id}/restore")
def restore_recipe(recipe_id: str):
    """
    Restore a previously excluded recipe (un-hide it).
    """
    if not is_valid_uuid(recipe_id):
        return JSONResponse({"success": False, "message_key": "error.invalid_data"}, status_code=400)
    try:
        with get_db_session() as db:
            from models import FoundRecipe
            recipe = db.query(FoundRecipe).filter(FoundRecipe.id == recipe_id).first()
            if not recipe:
                return JSONResponse({"success": False, "message_key": "recipes.recipe_not_found"}, status_code=404)

            recipe.excluded = False
            db.commit()
            _notify_recipe_visibility_changed(recipe_id, excluded=False)

            logger.info(f"Recipe restored: {recipe.name} (ID: {recipe_id})")

            return JSONResponse({
                "success": True,
                "message_key": "recipes.recipe_restored",
                "recipe_id": recipe_id,
                "recipe_name": recipe.name
            })
    except Exception as e:
        logger.error(f"Error restoring recipe {recipe_id}: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.get("/recipes/excluded")
def get_excluded_recipes(source_name: str = None):
    """
    Get all excluded (hidden) recipes, optionally filtered by source.
    """
    try:
        with get_db_session() as db:
            from models import FoundRecipe
            query = db.query(FoundRecipe).filter(FoundRecipe.excluded == True)  # noqa: E712 — SQLAlchemy requires == for SQL generation

            if source_name:
                query = query.filter(FoundRecipe.source_name == source_name)

            recipes = query.order_by(FoundRecipe.name).all()

            return JSONResponse({
                "success": True,
                "count": len(recipes),
                "recipes": [
                    {
                        "id": str(r.id),
                        "name": r.name,
                        "source_name": r.source_name,
                        "url": r.url,
                        "image_url": r.local_image_path or r.image_url,
                        "prep_time_minutes": r.prep_time_minutes,
                        "servings": r.servings
                    }
                    for r in recipes
                ]
            })
    except Exception as e:
        logger.error(f"Error getting excluded recipes: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


# ============================================================================
# RECIPE DEDUPLICATION & PERMANENT EXCLUSION
# ============================================================================

@router.get("/recipes/duplicates/count")
def count_duplicate_recipes():
    """Fast count of duplicate recipe pairs (for button badge)."""
    try:
        with get_db_session() as db:
            count = db.execute(text("""
                WITH sorted_ingredients AS (
                    SELECT
                           (SELECT array_agg(elem ORDER BY elem)
                            FROM jsonb_array_elements_text(ingredients) AS elem
                           ) AS sorted_ing
                    FROM found_recipes
                    WHERE ingredients IS NOT NULL
                      AND jsonb_array_length(ingredients) > 2
                      AND (excluded = FALSE OR excluded IS NULL)
                )
                SELECT COALESCE(SUM(group_size * (group_size - 1) / 2), 0)
                FROM (
                    SELECT COUNT(*) AS group_size
                    FROM sorted_ingredients
                    GROUP BY sorted_ing
                    HAVING COUNT(*) > 1
                ) duplicate_groups
            """)).scalar()
            return JSONResponse({"success": True, "count": int(count or 0)})
    except Exception as e:
        logger.error(f"Error counting duplicates: {e}")
        return JSONResponse(
            {"success": False, "message_key": friendly_error(e)},
            status_code=500,
        )


@router.get("/recipes/duplicates")
def find_duplicate_recipes():
    """
    Find recipes with identical ingredients but different names/URLs.
    Returns pairs of duplicates for user review.
    """
    try:
        with get_db_session() as db:
            rows = db.execute(text("""
                WITH sorted_ingredients AS (
                    SELECT id, name, url, source_name, image_url,
                           local_image_path, ingredients,
                           (SELECT array_agg(elem ORDER BY elem)
                            FROM jsonb_array_elements_text(ingredients) AS elem
                           ) AS sorted_ing
                    FROM found_recipes
                    WHERE ingredients IS NOT NULL
                      AND jsonb_array_length(ingredients) > 2
                      AND (excluded = FALSE OR excluded IS NULL)
                ),
                duplicate_groups AS (
                    SELECT sorted_ing
                    FROM sorted_ingredients
                    GROUP BY sorted_ing
                    HAVING COUNT(*) > 1
                )
                SELECT
                    a.id AS id_a, a.name AS name_a, a.url AS url_a,
                    a.source_name AS src_a, a.image_url AS img_a,
                    a.local_image_path AS local_img_a, a.ingredients AS ing_a,
                    b.id AS id_b, b.name AS name_b, b.url AS url_b,
                    b.source_name AS src_b, b.image_url AS img_b,
                    b.local_image_path AS local_img_b, b.ingredients AS ing_b
                FROM sorted_ingredients a
                JOIN duplicate_groups g ON a.sorted_ing = g.sorted_ing
                JOIN sorted_ingredients b ON a.id < b.id
                    AND a.sorted_ing = b.sorted_ing
                ORDER BY a.name
            """)).fetchall()

            pairs = []
            for r in rows:
                pairs.append({
                    "recipe_a": {
                        "id": str(r.id_a), "name": r.name_a, "url": r.url_a,
                        "source_name": r.src_a,
                        "image_url": r.local_img_a or r.img_a,
                        "ingredients": r.ing_a
                    },
                    "recipe_b": {
                        "id": str(r.id_b), "name": r.name_b, "url": r.url_b,
                        "source_name": r.src_b,
                        "image_url": r.local_img_b or r.img_b,
                        "ingredients": r.ing_b
                    }
                })

            return JSONResponse({"success": True, "count": len(pairs), "pairs": pairs})
    except Exception as e:
        logger.error(f"Error finding duplicate recipes: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.delete("/recipes/{recipe_id}/permanent")
def delete_recipe_permanent(recipe_id: str):
    """
    Permanently delete a recipe and add its URL to the exclusion list
    so it won't be re-scraped in the future.
    """
    if not is_valid_uuid(recipe_id):
        return JSONResponse({"success": False, "message_key": "error.invalid_data"}, status_code=400)
    try:
        with get_db_session() as db:
            from models import FoundRecipe
            recipe = db.query(FoundRecipe).filter(FoundRecipe.id == recipe_id).first()
            if not recipe:
                return JSONResponse({"success": False, "message_key": "recipes.recipe_not_found"}, status_code=404)

            recipe_name = recipe.name
            recipe_url = recipe.url
            recipe_source = recipe.source_name
            local_image = recipe.local_image_path

            # Add URL to exclusion list
            db.execute(text("""
                INSERT INTO excluded_recipe_urls (url, source_name, recipe_name)
                VALUES (:url, :source_name, :recipe_name)
                ON CONFLICT (url) DO NOTHING
            """), {"url": recipe_url, "source_name": recipe_source, "recipe_name": recipe_name})

            # Delete the recipe (cascades to recipe_offer_cache, image_download_failures)
            db.delete(recipe)
            db.commit()
            _notify_recipe_visibility_changed(recipe_id, excluded=True)

            image_cleanup = delete_unreferenced_recipe_image_file(
                local_image,
                reason="permanent_recipe_delete",
            )

            logger.info(f"Recipe permanently deleted: {recipe_name} (URL added to exclusion list)")

            return JSONResponse({
                "success": True,
                "recipe_name": recipe_name,
                "url": recipe_url,
                "image_deleted": image_cleanup["deleted_count"] > 0,
            })
    except Exception as e:
        logger.error(f"Error permanently deleting recipe {recipe_id}: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.get("/recipes/excluded-urls")
def get_excluded_urls():
    """Get permanently blocked URLs and currently hidden recipes."""
    try:
        with get_db_session() as db:
            url_rows = db.execute(text("""
                SELECT id, url, source_name, recipe_name, excluded_at
                FROM excluded_recipe_urls
                ORDER BY excluded_at DESC
            """)).fetchall()

            hidden_rows = db.execute(text("""
                SELECT id, url, source_name, name AS recipe_name
                FROM found_recipes
                WHERE excluded = TRUE
                ORDER BY name
            """)).fetchall()

            urls = [
                {
                    "id": r.id,
                    "kind": "url",
                    "url": r.url,
                    "source_name": r.source_name,
                    "recipe_name": r.recipe_name,
                    "excluded_at": r.excluded_at.isoformat() if r.excluded_at else None
                }
                for r in url_rows
            ]
            urls.extend([
                {
                    "id": str(r.id),
                    "kind": "recipe",
                    "url": r.url,
                    "source_name": r.source_name,
                    "recipe_name": r.recipe_name,
                    "excluded_at": None
                }
                for r in hidden_rows
            ])

            return JSONResponse({
                "success": True,
                "count": len(urls),
                "permanent_count": len(url_rows),
                "hidden_count": len(hidden_rows),
                "urls": urls
            })
    except Exception as e:
        logger.error(f"Error getting excluded URLs: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.delete("/recipes/excluded-urls/{url_id}")
def remove_excluded_url(url_id: int):
    """Remove a single URL from the exclusion list."""
    try:
        with get_db_session() as db:
            result = db.execute(text(
                "DELETE FROM excluded_recipe_urls WHERE id = :id RETURNING recipe_name"
            ), {"id": url_id}).fetchone()
            db.commit()

            if not result:
                return JSONResponse({"success": False, "message_key": "error.not_found"}, status_code=404)

            logger.info(f"Removed URL exclusion for: {result.recipe_name}")
            return JSONResponse({"success": True})
    except Exception as e:
        logger.error(f"Error removing excluded URL {url_id}: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.delete("/recipes/excluded-urls")
def remove_all_excluded_urls():
    """Remove all URL exclusions and restore all hidden recipes."""
    try:
        with get_db_session() as db:
            url_result = db.execute(text("DELETE FROM excluded_recipe_urls"))
            hidden_result = db.execute(text("""
                UPDATE found_recipes
                SET excluded = FALSE
                WHERE excluded = TRUE
                RETURNING id
            """))
            url_deleted = url_result.rowcount
            restored_recipe_ids = [str(row.id) for row in hidden_result.fetchall()]
            hidden_restored = len(restored_recipe_ids)
            db.commit()
            if hidden_restored:
                _notify_recipe_visibility_changed(recipe_ids=restored_recipe_ids, excluded=False)

            logger.info(
                f"Removed all exclusions ({url_deleted} URL entries, "
                f"{hidden_restored} hidden recipes restored)"
            )
            return JSONResponse({
                "success": True,
                "deleted": url_deleted + hidden_restored,
                "url_deleted": url_deleted,
                "hidden_restored": hidden_restored
            })
    except Exception as e:
        logger.error(f"Error removing all excluded URLs: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


# ============================================================================
# UNMATCHED OFFERS ANALYSIS
# ============================================================================

@router.get("/matching/unmatched-offers/count")
def count_unmatched_offers():
    """Fast count of unmatched offers (for button badge).

    Uses cached count from last cache rebuild (instant).
    Falls back to DB query if cache hasn't been rebuilt yet.
    """
    try:
        # Use cached count from cache_manager (set at rebuild, ~0ms)
        from cache_manager import cache_manager
        if cache_manager._unmatched_count is not None:
            return JSONResponse({"success": True, "count": cache_manager._unmatched_count})

        # Fallback: simple DB count (only before first cache rebuild)
        with get_db_session() as db:
            total = db.execute(text("SELECT COUNT(*) FROM offers")).scalar() or 0
            matched = db.execute(text("""
                SELECT COUNT(DISTINCT COALESCE(mo->>'offer_identity_key', mo->>'id'))
                FROM recipe_offer_cache c, jsonb_array_elements(c.match_data->'matched_offers') mo
            """)).scalar() or 0
            return JSONResponse({"success": True, "count": max(0, total - matched)})
    except Exception as e:
        logger.error(f"Error counting unmatched offers: {e}")
        return JSONResponse(
            {"success": False, "message_key": friendly_error(e)},
            status_code=500,
        )


@router.get("/matching/unmatched-offers")
async def get_unmatched_offers():
    """Analyze which offers are not used in recipe matching and why."""
    try:
        from recipe_matcher import analyze_unmatched_offers
        result = await asyncio.to_thread(analyze_unmatched_offers)
        return JSONResponse({"success": True, **result})
    except Exception as e:
        logger.error(f"Error analyzing unmatched offers: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)
