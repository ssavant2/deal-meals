"""Persistent recipe-side compiler for cache rebuilds."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
import json
import re
from typing import Any

from sqlalchemy import text

try:
    from database import get_db_session
    from models import CompiledRecipeMatchData, FoundRecipe
except ModuleNotFoundError:
    from app.database import get_db_session
    from app.models import CompiledRecipeMatchData, FoundRecipe

from ..normalization import fix_swedish_chars
from ..recipe_filters import KITCHEN_TOOLS, LEFTOVER_PREFIX
from .compound_text import _WORD_PATTERN
from .engine import build_prepared_ingredient_match_data
from .extraction import extract_keywords_from_ingredient
from .ingredient_data import IngredientMatchData
from .matching import _prepare_fast_ingredient_text
from .normalization import _apply_space_normalizations
from .recipe_matcher_support import (
    CITRUS_FRUITS,
    COOKING_INSTRUCTION_WORDS,
    ELLER_WORD,
    EXPLANATORY_PAREN_WORDS,
    NEGATION_WORDS,
    PAREN_INSTRUCTION_WORDS,
    PREFERENCE_PAREN_WORDS,
    PURPOSE_PHRASE_WORDS,
    TEXTURE_DESCRIPTOR_WORDS,
)
from .recipe_text import (
    expand_grouped_ingredient_text,
    is_subrecipe_reference_text,
    preserve_cheese_preference_parentheticals,
    preserve_fresh_pasta_parenthetical,
    preserve_non_concentrate_parenthetical,
    preserve_parenthetical_chili_alias,
    preserve_parenthetical_grouped_herb_leaves,
    preserve_parenthetical_shiso_alternatives,
    rewrite_buljong_eller_fond,
    rewrite_mince_of_alternatives,
    rewrite_truncated_eller_compounds,
    strip_biff_portion_prep_phrase,
)
from .recipe_identity import build_recipe_identity_key
from .versioning import RECIPE_COMPILER_VERSION

_COMPILED_RECIPE_REFRESH_LOCK = 82002


_TRUNCATED_COMPOUND_RE = re.compile(r"\b([a-zåäöéèü]+)-[,\s]")
_PREFERENCE_PAREN_RE = re.compile(r"\((?:" + PREFERENCE_PAREN_WORDS + r")[^)]*\)", re.IGNORECASE)
_EXAMPLE_PAREN_RE = re.compile(
    r"\([^)]*\b(?:t\.?\s*ex\.?|exempelvis|till\s+exempel)\b[^)]*\)",
    re.IGNORECASE,
)
_EXPLANATORY_PAREN_RE = re.compile(
    r"\((?:" + EXPLANATORY_PAREN_WORDS + r")\)",
    re.IGNORECASE,
)
_TEXTURE_DESCRIPTOR_RE = re.compile(
    r"\b(?:" + TEXTURE_DESCRIPTOR_WORDS + r")\b",
    re.IGNORECASE,
)
_NEGATION_RE = re.compile(r"\b(?:" + NEGATION_WORDS + r")\s+\w+", re.IGNORECASE)
_COOKING_INSTRUCTION_RE = re.compile(
    r",\s*(?:" + COOKING_INSTRUCTION_WORDS + r")\s+.*$",
    re.IGNORECASE,
)
_PURPOSE_PHRASE_RE = re.compile(
    r"\s+till\s+(?:" + PURPOSE_PHRASE_WORDS + r")\b.*$",
    re.IGNORECASE,
)
_DEFINITE_TARGET_PURPOSE_RE = re.compile(
    r"\s+till\s+(?:[a-zåäöéèü]+\s+){0,2}[a-zåäöéèü]+(?:en|et|na|arna|erna|orna)\b.*$",
    re.IGNORECASE,
)
_PAREN_INSTRUCTION_RE = re.compile(
    r"\((?:" + PAREN_INSTRUCTION_WORDS + r")\s+[^)]+\)",
    re.IGNORECASE,
)
_MEASURED_PLAIN_RICE_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:dl|l|g|kg)\s+ris\b")
_CITRUS_FRUITS = r"(?:" + CITRUS_FRUITS + r")"
_CITRUS_USAGE_PAREN_RE = re.compile(
    rf"({_CITRUS_FRUITS}[^(]*?)\([^)]*\b(?:skal|saft|juice|zest)\b[^)]*\)",
    re.IGNORECASE,
)
_CITRUS_USAGE_COMMA_RE = re.compile(
    rf"({_CITRUS_FRUITS}[^,]*?),\s*(?:(?:pressad|finrivet|rivet|färsk)\s+)?(?:juice|saft|zest|skal)\b.*$",
    re.IGNORECASE,
)
_CITRUS_USAGE_PREFIX_RE = re.compile(
    rf"^(?=.*\b(?:skal|zest)\b)(?=.*\b(?:saft|juice|juicen)\b).*?\b({_CITRUS_FRUITS})\b.*$",
    re.IGNORECASE,
)


@lru_cache(maxsize=50000)
def _cached_prepare_fast_ingredient_text(ingredient_text: str) -> str:
    return _prepare_fast_ingredient_text(ingredient_text, _prenormalized=True)


@lru_cache(maxsize=50000)
def _cached_ingredient_words(ingredient_text: str) -> tuple[str, ...]:
    return tuple(_WORD_PATTERN.findall(ingredient_text))


@lru_cache(maxsize=50000)
def _cached_extracted_ingredient_keywords(raw_text: str) -> frozenset[str]:
    return frozenset(extract_keywords_from_ingredient(raw_text))


def _stable_json_hash(payload: dict[str, Any]) -> str:
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def serialize_ingredient_match_data(item: IngredientMatchData) -> dict[str, Any]:
    return {
        "raw_text": item.raw_text,
        "normalized_text": item.normalized_text,
        "words": list(item.words),
        "extracted_keywords": sorted(item.extracted_keywords),
        "prepared_fast_text": bool(item.prepared_fast_text),
        "source_index": int(item.source_index),
        "expanded_index": int(item.expanded_index),
    }


def deserialize_ingredient_match_data(payload: dict[str, Any]) -> IngredientMatchData:
    return IngredientMatchData(
        raw_text=payload["raw_text"],
        normalized_text=payload["normalized_text"],
        words=tuple(payload.get("words", ())),
        extracted_keywords=frozenset(payload.get("extracted_keywords", ())),
        prepared_fast_text=bool(payload.get("prepared_fast_text", False)),
        source_index=int(payload.get("source_index", 0)),
        expanded_index=int(payload.get("expanded_index", 0)),
    )


def prepare_recipe_match_runtime_data(recipe: FoundRecipe) -> dict[str, Any]:
    """Build the current recipe-side matcher inputs in one reusable place."""
    merged_ingredients = list(recipe.ingredients or [])
    merged_source_indices = list(range(len(merged_ingredients)))
    idx = 0
    while idx < len(merged_ingredients) - 1:
        line = str(merged_ingredients[idx]).strip()
        next_line = str(merged_ingredients[idx + 1]).strip()
        if line.lower().endswith(" " + ELLER_WORD) or line.lower().endswith(" " + ELLER_WORD + " "):
            merged_ingredients[idx] = f"{line} {next_line}"
            merged_ingredients.pop(idx + 1)
            merged_source_indices.pop(idx + 1)
            continue
        if next_line.lower().startswith(ELLER_WORD + " ") or next_line.lower() == ELLER_WORD:
            if next_line.lower() == ELLER_WORD and idx + 2 < len(merged_ingredients):
                third = str(merged_ingredients[idx + 2]).strip()
                merged_ingredients[idx] = f"{line} {ELLER_WORD} {third}"
                merged_ingredients.pop(idx + 2)
                merged_ingredients.pop(idx + 1)
                merged_source_indices.pop(idx + 2)
                merged_source_indices.pop(idx + 1)
            else:
                merged_ingredients[idx] = f"{line} {next_line}"
                merged_ingredients.pop(idx + 1)
                merged_source_indices.pop(idx + 1)
            continue
        idx += 1

    expanded_ingredients: list[str] = []
    ingredient_source_texts: list[str] = []
    ingredient_source_indices: list[int] = []
    for source_ing_idx, ingredient in zip(merged_source_indices, merged_ingredients):
        ingredient_text = str(ingredient)
        expanded = expand_grouped_ingredient_text(ingredient_text)
        if expanded:
            expanded_ingredients.extend(expanded)
            ingredient_source_texts.extend([ingredient_text] * len(expanded))
            ingredient_source_indices.extend([source_ing_idx] * len(expanded))
    merged_ingredients = expanded_ingredients

    recipe_name_norm = fix_swedish_chars(recipe.name or "").lower()
    recipe_is_rice_porridge = "risgrynsgröt" in recipe_name_norm or "risgrynsgrot" in recipe_name_norm

    ingredients_normalized: list[str] = []
    for ingredient in merged_ingredients:
        ingredient_norm = _apply_space_normalizations(
            fix_swedish_chars(str(ingredient)).lower()
        )
        ingredient_norm = rewrite_truncated_eller_compounds(ingredient_norm)
        ingredient_norm = rewrite_mince_of_alternatives(ingredient_norm)
        ingredient_norm = _TRUNCATED_COMPOUND_RE.sub(r" ", ingredient_norm)
        ingredient_norm = preserve_cheese_preference_parentheticals(ingredient_norm)
        ingredient_norm = preserve_fresh_pasta_parenthetical(ingredient_norm)
        ingredient_norm = preserve_parenthetical_chili_alias(ingredient_norm)
        ingredient_norm = preserve_non_concentrate_parenthetical(ingredient_norm)
        ingredient_norm = preserve_parenthetical_grouped_herb_leaves(ingredient_norm)
        ingredient_norm = preserve_parenthetical_shiso_alternatives(ingredient_norm)
        ingredient_norm = strip_biff_portion_prep_phrase(ingredient_norm)
        ingredient_norm = _PREFERENCE_PAREN_RE.sub("", ingredient_norm)
        ingredient_norm = _EXAMPLE_PAREN_RE.sub("", ingredient_norm)
        ingredient_norm = _EXPLANATORY_PAREN_RE.sub("", ingredient_norm)
        ingredient_norm = _CITRUS_USAGE_PAREN_RE.sub(r"\1", ingredient_norm)
        ingredient_norm = _CITRUS_USAGE_COMMA_RE.sub(r"\1", ingredient_norm)
        ingredient_norm = _CITRUS_USAGE_PREFIX_RE.sub(r"\1", ingredient_norm)
        ingredient_norm = _TEXTURE_DESCRIPTOR_RE.sub("", ingredient_norm)
        ingredient_norm = _COOKING_INSTRUCTION_RE.sub("", ingredient_norm)
        ingredient_norm = _PURPOSE_PHRASE_RE.sub("", ingredient_norm)
        ingredient_norm = _DEFINITE_TARGET_PURPOSE_RE.sub("", ingredient_norm)
        ingredient_norm = _PAREN_INSTRUCTION_RE.sub("", ingredient_norm)
        ingredient_norm = re.sub(r"\s+smaksatt\s+med\s+.*", "", ingredient_norm)
        ingredient_norm = _NEGATION_RE.sub("", ingredient_norm)
        ingredient_norm = rewrite_buljong_eller_fond(ingredient_norm)

        if (
            not any(cue in ingredient_norm for cue in ("kålrotsspaghetti", "kalrotsspaghetti"))
            and any(
                cue in ingredient_norm for cue in (
                    "långpasta", "langpasta",
                    "spaghetti", "spagetti",
                    "linguine",
                    "tagliatelle",
                    "fettuccine", "fettuccini", "fettucine",
                    "pappardelle",
                    "tagliolini",
                    "bucatini",
                    "capellini",
                )
            )
            and "långpasta" not in ingredient_norm
            and "langpasta" not in ingredient_norm
        ):
            ingredient_norm += " långpasta"

        if recipe_is_rice_porridge and _MEASURED_PLAIN_RICE_RE.search(ingredient_norm):
            ingredient_norm = _MEASURED_PLAIN_RICE_RE.sub(
                lambda match: match.group(0).replace("ris", "grötris"),
                ingredient_norm,
            )

        if is_subrecipe_reference_text(ingredient_norm):
            ingredient_norm = ""
        elif ingredient_norm.lstrip().startswith(LEFTOVER_PREFIX):
            ingredient_norm = ""
        elif any(word in ingredient_norm for word in KITCHEN_TOOLS):
            ingredient_norm = ""

        ingredients_normalized.append(ingredient_norm)

    ingredients_search_text = " ".join(ingredients_normalized)
    full_recipe_text = (recipe.name or "").lower() + " " + ingredients_search_text

    ingredient_match_data_per_ing = []
    for idx, ingredient_norm in enumerate(ingredients_normalized):
        raw_text = (
            str(ingredient_source_texts[idx])
            if idx < len(ingredient_source_texts)
            else ingredient_norm
        )
        ingredient_match_data_per_ing.append(
            build_prepared_ingredient_match_data(
                _cached_prepare_fast_ingredient_text(ingredient_norm),
                raw_text=raw_text,
                words=_cached_ingredient_words(ingredient_norm),
                extracted_keywords=_cached_extracted_ingredient_keywords(raw_text),
                source_index=(
                    ingredient_source_indices[idx]
                    if idx < len(ingredient_source_indices)
                    else idx
                ),
                expanded_index=idx,
                prepared_fast_text=True,
            )
        )

    return {
        "merged_ingredients": merged_ingredients,
        "ingredient_source_texts": ingredient_source_texts,
        "ingredient_source_indices": ingredient_source_indices,
        "ingredients_normalized": ingredients_normalized,
        "ingredients_search_text": ingredients_search_text,
        "full_recipe_text": full_recipe_text,
        "ingredient_match_data_per_ing": ingredient_match_data_per_ing,
    }


def serialize_prepared_recipe_match_runtime_data(prepared: dict[str, Any]) -> dict[str, Any]:
    return {
        "merged_ingredients": list(prepared["merged_ingredients"]),
        "ingredient_source_texts": list(prepared["ingredient_source_texts"]),
        "ingredient_source_indices": list(prepared["ingredient_source_indices"]),
        "ingredients_normalized": list(prepared["ingredients_normalized"]),
        "ingredients_search_text": prepared["ingredients_search_text"],
        "full_recipe_text": prepared["full_recipe_text"],
        "ingredient_match_data": [
            serialize_ingredient_match_data(item)
            for item in prepared["ingredient_match_data_per_ing"]
        ],
    }


def deserialize_compiled_recipe_payload(compiled_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "merged_ingredients": list(compiled_data.get("merged_ingredients", [])),
        "ingredient_source_texts": list(compiled_data.get("ingredient_source_texts", [])),
        "ingredient_source_indices": [int(value) for value in compiled_data.get("ingredient_source_indices", [])],
        "ingredients_normalized": list(compiled_data.get("ingredients_normalized", [])),
        "ingredients_search_text": compiled_data.get("ingredients_search_text", ""),
        "full_recipe_text": compiled_data.get("full_recipe_text", ""),
        "ingredient_match_data_per_ing": [
            deserialize_ingredient_match_data(item)
            for item in compiled_data.get("ingredient_match_data", [])
        ],
    }


def resolve_recipe_match_runtime_data(
    recipe: FoundRecipe | None = None,
    *,
    prepared_recipe_data: dict[str, Any] | None = None,
    compiled_recipe_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve any supported recipe-side matcher input into runtime data.

    Matcher semantics stay identical while this helper accepts multiple
    recipe-side input shapes:
    - raw ``FoundRecipe`` rows
    - already prepared runtime dicts
    - serialized compiled payloads from ``compiled_recipe_match_data``
    - compiled row mappings that wrap the payload under ``compiled_data``
    """
    if prepared_recipe_data is not None:
        if "ingredient_match_data_per_ing" in prepared_recipe_data:
            return prepared_recipe_data
        if "ingredient_match_data" in prepared_recipe_data:
            return deserialize_compiled_recipe_payload(prepared_recipe_data)
        if "compiled_data" in prepared_recipe_data:
            return deserialize_compiled_recipe_payload(prepared_recipe_data["compiled_data"])
        raise ValueError("prepared_recipe_data has unsupported shape")

    if compiled_recipe_data is not None:
        if "ingredient_match_data_per_ing" in compiled_recipe_data:
            return compiled_recipe_data
        if "ingredient_match_data" in compiled_recipe_data:
            return deserialize_compiled_recipe_payload(compiled_recipe_data)
        if "compiled_data" in compiled_recipe_data:
            return deserialize_compiled_recipe_payload(compiled_recipe_data["compiled_data"])
        raise ValueError("compiled_recipe_data has unsupported shape")

    if recipe is None:
        raise ValueError("recipe is required when no prepared or compiled recipe data is provided")

    return prepare_recipe_match_runtime_data(recipe)


def ensure_compiled_recipe_match_table() -> None:
    with get_db_session() as db:
        exists = db.execute(text(
            "SELECT to_regclass('public.compiled_recipe_match_data')"
        )).scalar()
    if not exists:
        raise RuntimeError(
            "compiled_recipe_match_data table is missing. Apply the schema change "
            "from database/init.sql to this database before running recipe-IR tools."
        )


def _acquire_refresh_lock(db) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": _COMPILED_RECIPE_REFRESH_LOCK},
    )


def build_compiled_recipe_match_row(
    recipe: FoundRecipe,
    *,
    compiler_version: str = RECIPE_COMPILER_VERSION,
) -> dict[str, Any]:
    prepared = prepare_recipe_match_runtime_data(recipe)
    compiled_data = serialize_prepared_recipe_match_runtime_data(prepared)
    recipe_identity_key = build_recipe_identity_key(recipe)

    source_hash_payload = {
        "name": recipe.name,
        "ingredients": list(recipe.ingredients or []),
    }

    return {
        "found_recipe_id": recipe.id,
        "recipe_identity_key": recipe_identity_key,
        "source_name": recipe.source_name,
        "source_url": recipe.url,
        "recipe_name": recipe.name,
        "compiler_version": compiler_version,
        "recipe_source_hash": _stable_json_hash(source_hash_payload),
        "is_active": not bool(recipe.excluded),
        "compiled_data": compiled_data,
        "compiled_at": datetime.now(timezone.utc),
    }


def refresh_compiled_recipe_match_data() -> dict[str, Any]:
    ensure_compiled_recipe_match_table()

    with get_db_session() as db:
        _acquire_refresh_lock(db)
        recipes = db.query(FoundRecipe).order_by(FoundRecipe.id).all()
        rows = [build_compiled_recipe_match_row(recipe) for recipe in recipes]

        db.execute(CompiledRecipeMatchData.__table__.delete())
        if rows:
            db.bulk_insert_mappings(CompiledRecipeMatchData, rows)
        db.commit()

    return {
        "compiler_version": RECIPE_COMPILER_VERSION,
        "compiled_recipes": len(rows),
    }


def load_compiled_recipe_match_map(*, key_field: str = "recipe_identity_key") -> dict[str, dict[str, Any]]:
    ensure_compiled_recipe_match_table()

    with get_db_session() as db:
        rows = db.query(CompiledRecipeMatchData).order_by(CompiledRecipeMatchData.found_recipe_id).all()

    result = {}
    for row in rows:
        key_value = getattr(row, key_field)
        result[str(key_value)] = {
            "found_recipe_id": str(row.found_recipe_id),
            "recipe_identity_key": row.recipe_identity_key,
            "compiler_version": row.compiler_version,
            "recipe_source_hash": row.recipe_source_hash,
            "source_name": row.source_name,
            "source_url": row.source_url,
            "recipe_name": row.recipe_name,
            "is_active": row.is_active,
            "compiled_data": row.compiled_data,
        }
    return result


def classify_recipe_change_sets(
    current_rows_by_recipe_id: dict[str, dict[str, Any]],
    persisted_rows_by_recipe_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Classify recipe deltas using stable identity and source hashes."""
    added: list[str] = []
    removed: list[str] = []
    source_changed: list[str] = []
    version_mismatch: list[str] = []
    id_changed_current: list[str] = []
    id_changed_removed: list[str] = []
    unchanged: list[str] = []

    current_active_ids = set()

    for recipe_id, current_row in current_rows_by_recipe_id.items():
        current_is_active = bool(current_row.get("is_active", True))
        persisted_row = persisted_rows_by_recipe_id.get(recipe_id)
        persisted_is_active = bool(persisted_row.get("is_active", True)) if persisted_row else False
        current_found_recipe_id = str(current_row.get("found_recipe_id"))
        persisted_found_recipe_id = (
            str(persisted_row.get("found_recipe_id"))
            if persisted_row and persisted_row.get("found_recipe_id") is not None
            else None
        )

        if current_is_active:
            current_active_ids.add(current_found_recipe_id)

        if not current_is_active:
            if persisted_row is not None and persisted_is_active:
                removed.append(persisted_found_recipe_id or recipe_id)
            else:
                unchanged.append(current_found_recipe_id)
            continue

        if persisted_row is None or not persisted_is_active:
            added.append(current_found_recipe_id)
            continue
        id_changed = bool(persisted_found_recipe_id and persisted_found_recipe_id != current_found_recipe_id)
        if id_changed:
            id_changed_current.append(current_found_recipe_id)
            id_changed_removed.append(persisted_found_recipe_id)
        if persisted_row.get("compiler_version") != current_row.get("compiler_version"):
            version_mismatch.append(current_found_recipe_id)
            continue
        if persisted_row.get("recipe_source_hash") != current_row.get("recipe_source_hash"):
            source_changed.append(current_found_recipe_id)
            continue
        if id_changed:
            continue
        unchanged.append(current_found_recipe_id)

    for recipe_id, persisted_row in persisted_rows_by_recipe_id.items():
        persisted_found_recipe_id = str(persisted_row.get("found_recipe_id"))
        if recipe_id in current_rows_by_recipe_id:
            continue
        if persisted_found_recipe_id not in current_active_ids and bool(persisted_row.get("is_active", True)):
            removed.append(persisted_found_recipe_id)

    def _sorted(values: list[str]) -> list[str]:
        return sorted(set(values))

    added = _sorted(added)
    removed = _sorted(removed)
    source_changed = _sorted(source_changed)
    version_mismatch = _sorted(version_mismatch)
    id_changed_current = _sorted(id_changed_current)
    id_changed_removed = _sorted(id_changed_removed)
    unchanged = _sorted(unchanged)
    semantic_rematch_recipe_ids = _sorted(added + source_changed + id_changed_current)
    forced_version_rematch_recipe_ids = _sorted(version_mismatch)
    rematch_recipe_ids = _sorted(added + source_changed + id_changed_current + version_mismatch)
    remove_recipe_ids = _sorted(removed + id_changed_removed)
    all_impacted_recipe_ids = _sorted(rematch_recipe_ids + remove_recipe_ids)

    return {
        "added_recipe_ids": added,
        "removed_recipe_ids": removed,
        "source_changed_recipe_ids": source_changed,
        "version_mismatch_recipe_ids": version_mismatch,
        "id_changed_current_recipe_ids": id_changed_current,
        "id_changed_removed_recipe_ids": id_changed_removed,
        "unchanged_recipe_ids": unchanged,
        "semantic_rematch_recipe_ids": semantic_rematch_recipe_ids,
        "forced_version_rematch_recipe_ids": forced_version_rematch_recipe_ids,
        "rematch_recipe_ids": rematch_recipe_ids,
        "remove_recipe_ids": remove_recipe_ids,
        "all_impacted_recipe_ids": all_impacted_recipe_ids,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "source_changed": len(source_changed),
            "version_mismatch": len(version_mismatch),
            "id_changed": len(id_changed_current),
            "unchanged": len(unchanged),
            "semantic_rematch": len(semantic_rematch_recipe_ids),
            "forced_version_rematch": len(forced_version_rematch_recipe_ids),
            "rematch": len(rematch_recipe_ids),
            "remove": len(remove_recipe_ids),
            "all_impacted": len(all_impacted_recipe_ids),
        },
    }


def classify_current_recipe_changes(
    recipes: list[FoundRecipe],
    *,
    compiler_version: str = RECIPE_COMPILER_VERSION,
) -> dict[str, Any]:
    """Compare current recipes against persisted compiled recipe IR for delta prep."""
    current_rows_by_recipe_id = {
        build_recipe_identity_key(recipe): build_compiled_recipe_match_row(recipe, compiler_version=compiler_version)
        for recipe in recipes
    }
    persisted_rows_by_recipe_id = load_compiled_recipe_match_map()
    summary = classify_recipe_change_sets(current_rows_by_recipe_id, persisted_rows_by_recipe_id)
    summary.update({
        "compiler_version": compiler_version,
        "current_recipe_count": len(current_rows_by_recipe_id),
        "persisted_recipe_count": len(persisted_rows_by_recipe_id),
    })
    return summary


def load_compiled_recipe_runtime_cache(
    recipes: list[FoundRecipe],
    *,
    compiler_version: str = RECIPE_COMPILER_VERSION,
    strict: bool = True,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Load compiled recipe payloads for current FoundRecipe rows."""
    ensure_compiled_recipe_match_table()

    recipe_ids = [recipe.id for recipe in recipes]
    if not recipe_ids:
        return {}, {
            "compiler_version": compiler_version,
            "loaded": 0,
            "missing_recipe_ids": [],
            "stale_recipe_ids": [],
            "inactive_recipe_ids": [],
        }

    with get_db_session() as db:
        rows = db.query(CompiledRecipeMatchData).filter(
            CompiledRecipeMatchData.found_recipe_id.in_(recipe_ids)
        ).all()

    row_by_recipe_id = {row.found_recipe_id: row for row in rows}
    runtime_cache: dict[str, dict[str, Any]] = {}
    missing_recipe_ids = []
    stale_recipe_ids = []
    inactive_recipe_ids = []

    for recipe in recipes:
        row = row_by_recipe_id.get(recipe.id)
        if row is None:
            missing_recipe_ids.append(str(recipe.id))
            continue
        if row.compiler_version != compiler_version:
            stale_recipe_ids.append(str(recipe.id))
            continue
        if not row.is_active:
            inactive_recipe_ids.append(str(recipe.id))
            continue
        runtime_cache[str(recipe.id)] = deserialize_compiled_recipe_payload(row.compiled_data)

    stats = {
        "compiler_version": compiler_version,
        "loaded": len(runtime_cache),
        "missing_recipe_ids": missing_recipe_ids,
        "stale_recipe_ids": stale_recipe_ids,
        "inactive_recipe_ids": inactive_recipe_ids,
    }

    if strict and (missing_recipe_ids or stale_recipe_ids or inactive_recipe_ids):
        raise RuntimeError(
            "compiled_recipe_match_data is missing, stale, or inactive for current recipes: "
            f"missing={len(missing_recipe_ids)}, stale={len(stale_recipe_ids)}, "
            f"inactive={len(inactive_recipe_ids)}"
        )

    return runtime_cache, stats


def load_compiled_recipe_payload_cache(
    recipes: list[FoundRecipe],
    *,
    compiler_version: str = RECIPE_COMPILER_VERSION,
    strict: bool = True,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Load serialized compiled recipe payloads for current FoundRecipe rows."""
    ensure_compiled_recipe_match_table()

    recipe_ids = [recipe.id for recipe in recipes]
    if not recipe_ids:
        return {}, {
            "compiler_version": compiler_version,
            "loaded": 0,
            "missing_recipe_ids": [],
            "stale_recipe_ids": [],
            "inactive_recipe_ids": [],
        }

    with get_db_session() as db:
        rows = db.query(CompiledRecipeMatchData).filter(
            CompiledRecipeMatchData.found_recipe_id.in_(recipe_ids)
        ).all()

    row_by_recipe_id = {row.found_recipe_id: row for row in rows}
    payload_cache: dict[str, dict[str, Any]] = {}
    missing_recipe_ids = []
    stale_recipe_ids = []
    inactive_recipe_ids = []

    for recipe in recipes:
        row = row_by_recipe_id.get(recipe.id)
        if row is None:
            missing_recipe_ids.append(str(recipe.id))
            continue
        if row.compiler_version != compiler_version:
            stale_recipe_ids.append(str(recipe.id))
            continue
        if not row.is_active:
            inactive_recipe_ids.append(str(recipe.id))
            continue
        payload_cache[str(recipe.id)] = row.compiled_data

    stats = {
        "compiler_version": compiler_version,
        "loaded": len(payload_cache),
        "missing_recipe_ids": missing_recipe_ids,
        "stale_recipe_ids": stale_recipe_ids,
        "inactive_recipe_ids": inactive_recipe_ids,
    }

    if strict and (missing_recipe_ids or stale_recipe_ids or inactive_recipe_ids):
        raise RuntimeError(
            "compiled_recipe_match_data is missing, stale, or inactive for current recipes: "
            f"missing={len(missing_recipe_ids)}, stale={len(stale_recipe_ids)}, "
            f"inactive={len(inactive_recipe_ids)}"
        )

    return payload_cache, stats
