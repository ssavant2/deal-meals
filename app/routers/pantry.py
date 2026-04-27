"""
Pantry Match API Route.

This router handles pantry-based recipe matching:
- /api/pantry-match - Find recipes matching user-provided ingredients
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from loguru import logger

from database import get_db_session
from utils.errors import friendly_error
from utils.rate_limit import limiter
from config import settings

try:
    from languages.market_runtime import (
        extract_keywords_from_ingredient_backend,
        get_pantry_ignore_words,
        is_boring_recipe,
        normalize_market_text,
    )
except ModuleNotFoundError:
    from app.languages.market_runtime import (
        extract_keywords_from_ingredient_backend,
        get_pantry_ignore_words,
        is_boring_recipe,
        normalize_market_text,
    )


# Limits and thresholds
MIN_COVERAGE_THRESHOLD = 0.5      # Minimum ingredient coverage (50%) for partial matches
MAX_FULL_MATCHES = 100            # Max full-match recipes returned
MAX_PARTIAL_MATCHES = 200         # Max partial-match recipes returned

router = APIRouter(prefix="/api", tags=["pantry"])


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

        # Parse comma-separated ingredients and extract keywords
        user_keywords = set()
        for ingredient in raw_ingredients.split(','):
            ingredient = ingredient.strip().lower()
            if ingredient:
                ingredient = normalize_market_text(ingredient)
                # Add the ingredient itself as a keyword
                user_keywords.add(ingredient)
                # Also extract more specific keywords (with lower min_length for user input)
                extracted = extract_keywords_from_ingredient_backend(ingredient, min_length=3)
                for kw in extracted:
                    user_keywords.add(kw)

        if not user_keywords:
            return JSONResponse({
                "success": False,
                "message_key": "pantry.extract_failed"
            })

        user_keywords_list = list(user_keywords)

        # Query recipes with ingredients (excluding hidden recipes)
        with get_db_session() as db:
            recipes = db.execute(text("""
                SELECT id, name, url, source_name, image_url, local_image_path,
                       ingredients, prep_time_minutes, servings
                FROM found_recipes
                WHERE ingredients IS NOT NULL
                AND jsonb_array_length(ingredients) > 0
                AND (excluded = FALSE OR excluded IS NULL)
            """)).fetchall()

        full_match = []
        partial_match = []

        ignore_words = get_pantry_ignore_words()

        for recipe in recipes:
            recipe_ingredients = recipe.ingredients or []
            if not recipe_ingredients:
                continue

            # Skip boring "how to cook X" recipes
            if is_boring_recipe(recipe.name):
                continue

            # Extract keywords from each recipe ingredient
            recipe_keywords = set()
            for ing in recipe_ingredients:
                ing_lower = normalize_market_text(str(ing).lower())
                # Remove punctuation
                ing_clean = ''.join(c if c.isalnum() or c.isspace() else ' ' for c in ing_lower)
                # Add words from ingredient
                words = ing_clean.split()
                for word in words:
                    # Skip short words, numbers, and ignore words
                    if len(word) < 3:
                        continue
                    if word.replace(',', '').replace('.', '').isdigit():
                        continue
                    if word in ignore_words:
                        continue
                    recipe_keywords.add(word)

            if not recipe_keywords:
                continue

            # Calculate how many recipe keywords are covered by user keywords
            matched = 0
            missing = []
            for rk in recipe_keywords:
                found = False
                for uk in user_keywords_list:
                    # Check substring match both ways
                    if uk in rk or rk in uk:
                        found = True
                        break
                    # Fuzzy prefix match (language-agnostic plural handling)
                    min_len = min(len(uk), len(rk))
                    if min_len > 3:
                        prefix_len = sum(1 for a, b in zip(uk, rk) if a == b)
                        if prefix_len >= min_len * 0.75:
                            found = True
                            break
                if found:
                    matched += 1
                else:
                    missing.append(rk)

            coverage = matched / len(recipe_keywords) if recipe_keywords else 0
            missing_count = len(missing)

            # Only include if at least 50% coverage
            if coverage < MIN_COVERAGE_THRESHOLD:
                continue

            recipe_data = {
                "id": str(recipe.id),
                "name": recipe.name,
                "url": recipe.url,
                "source": recipe.source_name,
                "image_url": recipe.local_image_path or recipe.image_url,  # Prefer local image
                "prep_time_minutes": recipe.prep_time_minutes,
                "servings": recipe.servings,
                "ingredients": recipe.ingredients or [],
                "total_ingredients": len(recipe_keywords),
                "matched_ingredients": matched,
                "missing_count": missing_count,
                "missing_preview": missing[:3],
                "coverage_pct": round(coverage * 100, 1)
            }

            if missing_count == 0:
                full_match.append(recipe_data)
            elif missing_count <= 3:
                partial_match.append(recipe_data)

        # Sort: full_match by most matched, partial by fewest missing then most matched
        full_match.sort(key=lambda x: (-x['coverage_pct'], -x['matched_ingredients']))
        partial_match.sort(key=lambda x: (x['missing_count'], -x['coverage_pct']))

        # Enrich with offer cache data (savings, matched offers)
        all_results = full_match[:MAX_FULL_MATCHES] + partial_match[:MAX_PARTIAL_MATCHES]
        if all_results:
            result_ids = [r["id"] for r in all_results]
            with get_db_session() as db:
                cache_rows = db.execute(text("""
                    SELECT found_recipe_id, total_savings, num_matches, match_data
                    FROM recipe_offer_cache
                    WHERE found_recipe_id::text = ANY(:ids)
                """), {"ids": result_ids}).fetchall()
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
            for r in all_results:
                cd = cache_map.get(r["id"], {})
                r["total_savings"] = cd.get("total_savings", 0)
                r["num_matches"] = cd.get("num_matches", 0)
                r["matched_offers"] = cd.get("matched_offers", [])
                r["ingredient_groups"] = cd.get("ingredient_groups", [])
                r["avg_savings_pct"] = cd.get("avg_savings_pct", 0)

        return JSONResponse({
            "success": True,
            "full_match": full_match[:MAX_FULL_MATCHES],
            "partial_match": partial_match[:MAX_PARTIAL_MATCHES],
            "user_keywords": user_keywords_list,
            "total_searched": len(recipes)
        })

    except Exception as e:
        logger.error(f"Error in pantry match: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        })
