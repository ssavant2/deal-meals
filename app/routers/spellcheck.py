"""
Spell Check API Routes.

Endpoints for managing ingredient spelling corrections:
- GET  /api/spell-corrections              - List corrections + global exclusions
- POST /api/spell-corrections/review       - Mark corrections as reviewed
- POST /api/spell-corrections/revert       - Revert a single correction (per-recipe)
- POST /api/spell-corrections/exclude      - Exclude a single correction (per-recipe, never again)
- POST /api/spell-corrections/exclude-word - Exclude a word pair globally (all recipes)
- POST /api/spell-corrections/reset-exclusion      - Reset per-recipe exclusion
- POST /api/spell-corrections/reset-word-exclusion  - Reset global word exclusion
- GET  /api/spell-corrections/count        - Unreviewed + total counts
"""

import json
import re
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from loguru import logger

from database import get_db_session
from models import SpellCorrection, FoundRecipe
from utils.errors import friendly_error

router = APIRouter(prefix="/api", tags=["spellcheck"])


def _revert_word_in_recipe(db, recipe_id, corrected_word, original_word):
    """Restore original word in a recipe's ingredients by searching all lines."""
    recipe = db.query(FoundRecipe).filter(FoundRecipe.id == recipe_id).first()
    if not recipe or not recipe.ingredients:
        return False

    ingredients = json.loads(recipe.ingredients) if isinstance(recipe.ingredients, str) else list(recipe.ingredients)
    pattern = re.compile(re.escape(corrected_word), re.IGNORECASE)
    changed = False

    for idx, ing in enumerate(ingredients):
        if isinstance(ing, str) and pattern.search(ing):
            ingredients[idx] = pattern.sub(original_word, ing, count=1)
            changed = True
            break  # Only revert first occurrence

    if changed:
        recipe.ingredients = ingredients
    return changed


@router.get("/spell-corrections/count")
async def get_spell_correction_count():
    """Get count of unreviewed and total active spell corrections."""
    try:
        with get_db_session() as db:
            unreviewed = db.execute(
                text("SELECT COUNT(*) FROM spell_corrections WHERE reviewed = false AND excluded = false")
            ).scalar()
            total = db.execute(
                text("SELECT COUNT(*) FROM spell_corrections WHERE excluded = false")
            ).scalar()
            return JSONResponse({"success": True, "count": unreviewed, "total": total})
    except Exception as e:
        logger.error(f"Error getting spell correction count: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.get("/spell-corrections")
async def get_spell_corrections():
    """List all spell corrections with recipe names, plus global exclusions."""
    try:
        with get_db_session() as db:
            rows = db.execute(text("""
                SELECT sc.id, sc.recipe_id, fr.name as recipe_name,
                       sc.ingredient_index, sc.original_word, sc.corrected_word,
                       sc.reviewed, sc.excluded, sc.created_at, fr.url as recipe_url
                FROM spell_corrections sc
                JOIN found_recipes fr ON fr.id = sc.recipe_id
                ORDER BY sc.excluded ASC, sc.original_word ASC, fr.name ASC
            """)).fetchall()

            corrections = []
            for row in rows:
                corrections.append({
                    "id": row[0],
                    "recipe_id": str(row[1]),
                    "recipe_name": row[2],
                    "ingredient_index": row[3],
                    "original_word": row[4],
                    "corrected_word": row[5],
                    "reviewed": row[6],
                    "excluded": row[7],
                    "created_at": row[8].isoformat() if row[8] else None,
                    "recipe_url": row[9],
                })

            unreviewed = sum(1 for c in corrections if not c["reviewed"] and not c["excluded"])

            # Load global exclusions
            global_rows = db.execute(text(
                "SELECT original_word, corrected_word, created_at FROM spell_excluded_words ORDER BY original_word"
            )).fetchall()
            global_exclusions = [
                {"original_word": r[0], "corrected_word": r[1], "created_at": r[2].isoformat() if r[2] else None}
                for r in global_rows
            ]

            return JSONResponse({
                "success": True,
                "corrections": corrections,
                "unreviewed_count": unreviewed,
                "global_exclusions": global_exclusions,
            })
    except Exception as e:
        logger.error(f"Error listing spell corrections: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.post("/spell-corrections/review")
async def review_spell_corrections():
    """Mark all unreviewed corrections as reviewed."""
    try:
        with get_db_session() as db:
            result = db.execute(
                text("UPDATE spell_corrections SET reviewed = true WHERE reviewed = false")
            )
            db.commit()
            return JSONResponse({"success": True, "reviewed": result.rowcount})
    except Exception as e:
        logger.error(f"Error reviewing spell corrections: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.post("/spell-corrections/revert")
async def revert_spell_correction(request: Request):
    """Revert a single correction — restore the original word, mark excluded for this recipe."""
    try:
        data = await request.json()
        correction_id = data.get("id")
        if not correction_id:
            return JSONResponse({"success": False, "message_key": "error.invalid_data"}, status_code=400)

        with get_db_session() as db:
            correction = db.query(SpellCorrection).filter(SpellCorrection.id == correction_id).first()
            if not correction:
                return JSONResponse({"success": False, "message_key": "error.not_found"}, status_code=404)

            # Restore original word by searching ingredient text (not relying on index)
            _revert_word_in_recipe(db, correction.recipe_id, correction.corrected_word, correction.original_word)

            # Mark as excluded so it won't be re-applied for this recipe
            correction.excluded = True
            correction.reviewed = True
            db.commit()

            return JSONResponse({"success": True})
    except Exception as e:
        logger.error(f"Error reverting spell correction: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.post("/spell-corrections/exclude-word")
async def exclude_word_globally(request: Request):
    """Exclude a word pair globally — revert ALL recipes and prevent future corrections."""
    try:
        data = await request.json()
        original_word = data.get("original_word")
        corrected_word = data.get("corrected_word")
        if not original_word or not corrected_word:
            return JSONResponse({"success": False, "message_key": "error.invalid_data"}, status_code=400)

        with get_db_session() as db:
            # Add to global exclusion table
            db.execute(
                text("INSERT INTO spell_excluded_words (original_word, corrected_word) VALUES (:orig, :corr) ON CONFLICT DO NOTHING"),
                {"orig": original_word, "corr": corrected_word}
            )

            # Find all active corrections for this word pair
            affected = db.query(SpellCorrection).filter(
                SpellCorrection.original_word == original_word,
                SpellCorrection.corrected_word == corrected_word,
                SpellCorrection.excluded == False,  # noqa: E712
            ).all()

            # Revert each one in the recipe text
            reverted = 0
            for correction in affected:
                if _revert_word_in_recipe(db, correction.recipe_id, correction.corrected_word, correction.original_word):
                    reverted += 1

            # Delete all correction records for this word pair (both active and per-recipe excluded)
            db.execute(
                text("DELETE FROM spell_corrections WHERE original_word = :orig AND corrected_word = :corr"),
                {"orig": original_word, "corr": corrected_word}
            )

            db.commit()
            return JSONResponse({"success": True, "reverted": reverted})
    except Exception as e:
        logger.error(f"Error excluding word globally: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.post("/spell-corrections/reset-exclusion")
async def reset_spell_exclusion(request: Request):
    """Reset a per-recipe exclusion — delete the record so next scrape can correct again."""
    try:
        data = await request.json()
        correction_id = data.get("id")
        if not correction_id:
            return JSONResponse({"success": False, "message_key": "error.invalid_data"}, status_code=400)

        with get_db_session() as db:
            result = db.execute(
                text("DELETE FROM spell_corrections WHERE id = :id AND excluded = true"),
                {"id": correction_id}
            )
            db.commit()
            return JSONResponse({"success": True, "deleted": result.rowcount})
    except Exception as e:
        logger.error(f"Error resetting spell exclusion: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.post("/spell-corrections/reset-word-exclusion")
async def reset_word_exclusion(request: Request):
    """Reset a global word exclusion — allow this word pair to be corrected again."""
    try:
        data = await request.json()
        original_word = data.get("original_word")
        corrected_word = data.get("corrected_word")
        if not original_word or not corrected_word:
            return JSONResponse({"success": False, "message_key": "error.invalid_data"}, status_code=400)

        with get_db_session() as db:
            db.execute(
                text("DELETE FROM spell_excluded_words WHERE original_word = :orig AND corrected_word = :corr"),
                {"orig": original_word, "corr": corrected_word}
            )
            db.commit()
            return JSONResponse({"success": True})
    except Exception as e:
        logger.error(f"Error resetting word exclusion: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)
