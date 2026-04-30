"""Compiled pantry search-term index helpers.

The index is an optional candidate selector for /api/pantry-match. It never
changes the public response contract by itself; callers can fall back to the
legacy all-recipes path whenever the index is missing, stale, or insufficiently
covering a query.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
import json
import re
from typing import Any, Iterable

from loguru import logger
from sqlalchemy import text

try:
    from database import get_db_session
    from models import (
        CompiledRecipeMatchData,
        CompiledRecipeSearchTermIndex,
        FoundRecipe,
    )
except ModuleNotFoundError:
    from app.database import get_db_session
    from app.models import (
        CompiledRecipeMatchData,
        CompiledRecipeSearchTermIndex,
        FoundRecipe,
    )

try:
    from config import settings
except ModuleNotFoundError:
    from app.config import settings

try:
    from languages.matcher_runtime import (
        INGREDIENT_PARENTS,
        MATCHER_VERSION,
        RECIPE_COMPILER_VERSION,
        build_recipe_identity_key,
    )
except ModuleNotFoundError:
    from app.languages.matcher_runtime import (
        INGREDIENT_PARENTS,
        MATCHER_VERSION,
        RECIPE_COMPILER_VERSION,
        build_recipe_identity_key,
    )

try:
    from languages.market_runtime import (
        extract_keywords_from_ingredient_backend,
        get_pantry_ignore_words,
        get_unit_aliases,
        is_boring_recipe,
        normalize_market_text,
    )
except ModuleNotFoundError:
    from app.languages.market_runtime import (
        extract_keywords_from_ingredient_backend,
        get_pantry_ignore_words,
        get_unit_aliases,
        is_boring_recipe,
        normalize_market_text,
    )


PANTRY_SEARCH_STATUS_KEY = "pantry_search"
PANTRY_SEARCH_REFRESH_LOCK = 82005
PANTRY_QUERY_INDEX_COVERAGE_THRESHOLD = 0.5

_INDEX_SEMANTICS = {
    "name": "compiled_recipe_search_term_index",
    "version": 3,
    "term_types": ("ingredient_keyword", "legacy_subterm", "parent_keyword", "normalized_word"),
    "normalized_words": {
        "min_length": 3,
        "skip_numeric": True,
        "skip_pantry_ignore_words": True,
        "skip_unit_aliases": True,
    },
    "query_coverage": {
        "mode": "input_parts_with_any_indexed_term",
        "threshold": PANTRY_QUERY_INDEX_COVERAGE_THRESHOLD,
    },
    "query_inflections": {
        "singular_suffixes": ("er", "ar", "or", "r"),
        "plural_suffixes": ("er", "ar", "or"),
    },
    "scoring": {
        "mode": "sql_recipe_term_exact_substring_coverage",
        "term_type": "normalized_word",
        "coverage_threshold": 0.5,
        "partial_missing_limit": 3,
    },
    "candidate_limit": {
        "mode": "safety_only",
        "default": "active_scope",
    },
}
PANTRY_SEARCH_INDEX_VERSION_HASH = sha256(
    json.dumps(_INDEX_SEMANTICS, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()

_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)
_LEGACY_SUBTERM_SUFFIXES = (
    "grädde",
    "kyckling",
    "pasta",
    "ris",
    "lök",
    "ägg",
    "ost",
)
_LEGACY_SUBTERM_CONTAINS = ("tomat",)
_LEGACY_SUBTERM_DENY_WORDS = {
    "frukost",
    "gris",
    "kris",
    "kost",
    "rost",
    "rostas",
}


@dataclass(frozen=True)
class PantryQuery:
    raw_ingredients: str
    input_parts: tuple[str, ...]
    terms_by_input: tuple[frozenset[str], ...]
    user_keywords: tuple[str, ...]


@dataclass(frozen=True)
class PantryIndexSelection:
    use_index: bool
    fallback_reason: str | None
    full_match: list[dict[str, Any]]
    partial_match: list[dict[str, Any]]
    total_scope: int
    candidate_limit: int
    candidate_count: int
    scored_candidate_count: int
    query_index_coverage_pct: float
    query_keyword_index_coverage_pct: float
    matched_index_terms: tuple[str, ...]


def _stable_json_hash(payload: Any) -> str:
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _recipe_source_hash(recipe: FoundRecipe) -> str:
    return _stable_json_hash({
        "name": recipe.name,
        "ingredients": list(recipe.ingredients or []),
    })


@lru_cache(maxsize=1)
def _cached_pantry_ignore_words() -> frozenset[str]:
    return get_pantry_ignore_words()


@lru_cache(maxsize=1)
def _unit_words() -> frozenset[str]:
    aliases = get_unit_aliases()
    words = set()
    for key, value in aliases.items():
        if key:
            words.add(str(key).lower())
        if value:
            words.add(str(value).lower())
    return frozenset(words)


def _is_numeric(value: str) -> bool:
    return value.replace(",", "").replace(".", "").isdigit()


def _clean_normalized_text(value: str) -> str:
    normalized = normalize_market_text(str(value or "").lower())
    return _NON_WORD_RE.sub(" ", normalized)


def _is_indexable_term(term: str, *, ignore_words: frozenset[str], unit_words: set[str]) -> bool:
    value = str(term or "").strip().lower()
    if not value:
        return False
    if len(value) < 3:
        return False
    if _is_numeric(value):
        return False
    if value in ignore_words:
        return False
    if value in unit_words:
        return False
    return True


def _legacy_compatible_subterms(word: str) -> set[str]:
    """Add narrowly-scoped terms for legacy pantry substring behavior.

    The old pantry path can match user input against compounds such as
    ``fetaost`` or ``basmatiris`` through substring checks. Candidate selection
    needs a few equivalent postings so the index path can still score those
    recipes, but the rules stay suffix/known-substring based to avoid broad
    false positives like ``rostas`` matching ``ost``.
    """
    value = str(word or "").strip().lower()
    if not value or value in _LEGACY_SUBTERM_DENY_WORDS:
        return set()

    terms = set()
    for suffix in _LEGACY_SUBTERM_SUFFIXES:
        if value != suffix and value.endswith(suffix):
            terms.add(suffix)
    for substring in _LEGACY_SUBTERM_CONTAINS:
        if value != substring and substring in value:
            terms.add(substring)
    return terms


def _query_inflection_terms(term: str) -> set[str]:
    """Generate conservative singular/plural variants for pantry user input."""
    value = str(term or "").strip().lower()
    if len(value) < 4:
        return set()

    variants: set[str] = set()
    matched_plural_suffix = False
    for suffix in ("er", "ar", "or"):
        if value.endswith(suffix) and len(value) > len(suffix) + 2:
            variants.add(value[: -len(suffix)])
            matched_plural_suffix = True
    if not matched_plural_suffix and value.endswith("r") and len(value) > 4:
        variants.add(value[:-1])

    # Add common Swedish plural endings for singular-looking terms. Keep this
    # query-side only so the persisted index does not balloon unnecessarily.
    if not value.endswith(("er", "ar", "or")):
        variants.add(f"{value}er")
        variants.add(f"{value}ar")
        variants.add(f"{value}or")

    variants.discard(value)
    return variants


def build_pantry_query(raw_ingredients: str) -> PantryQuery:
    """Parse pantry input into stable input parts and searchable terms."""
    input_parts: list[str] = []
    terms_by_input: list[frozenset[str]] = []
    user_keywords: set[str] = set()
    ignore_words = _cached_pantry_ignore_words()
    units = _unit_words()

    for raw_part in str(raw_ingredients or "").split(","):
        clean_part = normalize_market_text(raw_part.strip().lower())
        if not clean_part:
            continue

        terms = {clean_part}
        terms.update(extract_keywords_from_ingredient_backend(clean_part, min_length=3))
        for term in list(terms):
            terms.update(_query_inflection_terms(term))
            terms.update(_legacy_compatible_subterms(term))
        filtered_terms = {
            term
            for term in terms
            if _is_indexable_term(term, ignore_words=ignore_words, unit_words=units)
        }
        if not filtered_terms:
            continue

        input_parts.append(clean_part)
        terms_by_input.append(frozenset(sorted(filtered_terms)))
        user_keywords.update(filtered_terms)

    return PantryQuery(
        raw_ingredients=raw_ingredients,
        input_parts=tuple(input_parts),
        terms_by_input=tuple(terms_by_input),
        user_keywords=tuple(sorted(user_keywords)),
    )


def build_recipe_scoring_keywords(
    ingredients: Iterable[Any],
    *,
    ignore_words: frozenset[str] | None = None,
    unit_words: frozenset[str] | None = None,
) -> set[str]:
    """Build the legacy pantry keyword set for a recipe."""
    ignore_words = ignore_words if ignore_words is not None else _cached_pantry_ignore_words()
    units = unit_words if unit_words is not None else _unit_words()
    recipe_keywords: set[str] = set()
    for ingredient in ingredients or ():
        ing_clean = _clean_normalized_text(str(ingredient))
        for word in ing_clean.split():
            if _is_indexable_term(word, ignore_words=ignore_words, unit_words=units):
                recipe_keywords.add(word)
    return recipe_keywords


def build_recipe_search_terms(recipe: FoundRecipe) -> set[tuple[str, str]]:
    """Build broad recipe-owned terms for pantry candidate selection."""
    ignore_words = _cached_pantry_ignore_words()
    units = _unit_words()
    terms: set[tuple[str, str]] = set()

    for ingredient in recipe.ingredients or ():
        clean_text = _clean_normalized_text(str(ingredient))
        for word in clean_text.split():
            if _is_indexable_term(word, ignore_words=ignore_words, unit_words=units):
                terms.add((word, "normalized_word"))
                for subterm in _legacy_compatible_subterms(word):
                    if _is_indexable_term(subterm, ignore_words=ignore_words, unit_words=units):
                        terms.add((subterm, "legacy_subterm"))

        for keyword in extract_keywords_from_ingredient_backend(clean_text, min_length=3):
            keyword = str(keyword or "").strip().lower()
            if not _is_indexable_term(keyword, ignore_words=ignore_words, unit_words=units):
                continue
            terms.add((keyword, "ingredient_keyword"))
            for subterm in _legacy_compatible_subterms(keyword):
                if _is_indexable_term(subterm, ignore_words=ignore_words, unit_words=units):
                    terms.add((subterm, "legacy_subterm"))
            parent = INGREDIENT_PARENTS.get(keyword)
            if parent and _is_indexable_term(parent, ignore_words=ignore_words, unit_words=units):
                terms.add((parent, "parent_keyword"))

    return terms


def ensure_compiled_recipe_search_term_index_table() -> None:
    with get_db_session() as db:
        index_exists = db.execute(text(
            "SELECT to_regclass('public.compiled_recipe_search_term_index')"
        )).scalar()
        status_exists = db.execute(text(
            "SELECT to_regclass('public.compiled_recipe_search_term_index_status')"
        )).scalar()
    if not index_exists or not status_exists:
        raise RuntimeError(
            "compiled_recipe_search_term_index tables are missing. Apply the "
            "schema change from database/init.sql before enabling pantry search indexing."
        )


def _acquire_refresh_lock(db) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": PANTRY_SEARCH_REFRESH_LOCK})


def _active_scope_count(db) -> int:
    return int(db.execute(text("""
        SELECT COUNT(*)
        FROM found_recipes
        WHERE ingredients IS NOT NULL
          AND jsonb_array_length(ingredients) > 0
          AND (excluded = FALSE OR excluded IS NULL)
    """)).scalar() or 0)


def _active_recipe_query(db, recipe_ids: list[str] | None = None):
    query = db.query(FoundRecipe).filter(
        FoundRecipe.ingredients.isnot(None),
        text("jsonb_array_length(ingredients) > 0"),
        (FoundRecipe.excluded == False) | (FoundRecipe.excluded.is_(None)),  # noqa: E712
    )
    if recipe_ids:
        query = query.filter(FoundRecipe.id.in_(recipe_ids))
    return query.order_by(FoundRecipe.id).all()


def _load_source_hash_map(db, recipe_ids: list[str]) -> dict[str, str]:
    if not recipe_ids:
        return {}
    rows = db.query(
        CompiledRecipeMatchData.found_recipe_id,
        CompiledRecipeMatchData.recipe_source_hash,
    ).filter(
        CompiledRecipeMatchData.found_recipe_id.in_(recipe_ids),
        CompiledRecipeMatchData.compiler_version == RECIPE_COMPILER_VERSION,
    ).all()
    return {str(row.found_recipe_id): row.recipe_source_hash for row in rows}


def _build_index_rows(recipes: list[FoundRecipe], source_hash_map: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    indexed_at = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    empty_recipe_ids: list[str] = []
    for recipe in recipes:
        if is_boring_recipe(recipe.name):
            empty_recipe_ids.append(str(recipe.id))
            continue
        terms = build_recipe_search_terms(recipe)
        if not terms:
            empty_recipe_ids.append(str(recipe.id))
            continue
        recipe_id = str(recipe.id)
        source_hash = source_hash_map.get(recipe_id) or _recipe_source_hash(recipe)
        identity_key = build_recipe_identity_key(recipe)
        for term, term_type in sorted(terms):
            rows.append({
                "found_recipe_id": recipe.id,
                "recipe_identity_key": identity_key,
                "recipe_source_hash": source_hash,
                "matcher_version": MATCHER_VERSION,
                "recipe_compiler_version": RECIPE_COMPILER_VERSION,
                "index_version_hash": PANTRY_SEARCH_INDEX_VERSION_HASH,
                "term": term,
                "term_type": term_type,
                "indexed_at": indexed_at,
            })
    return rows, empty_recipe_ids


def _upsert_status(
    db,
    *,
    status: str,
    active_scope_count: int,
    indexed_recipe_count: int,
    empty_term_recipe_count: int,
    last_error: str | None,
    full_refresh: bool,
    incremental_refresh: bool,
) -> None:
    timestamp_field = ""
    if full_refresh:
        timestamp_field += ", last_full_refresh_at = NOW()"
    if incremental_refresh:
        timestamp_field += ", last_incremental_refresh_at = NOW()"

    db.execute(text(f"""
        INSERT INTO compiled_recipe_search_term_index_status (
            status_key,
            status,
            matcher_version,
            recipe_compiler_version,
            index_version_hash,
            active_scope_count,
            indexed_recipe_count,
            empty_term_recipe_count,
            last_error,
            updated_at
        ) VALUES (
            :status_key,
            :status,
            :matcher_version,
            :recipe_compiler_version,
            :index_version_hash,
            :active_scope_count,
            :indexed_recipe_count,
            :empty_term_recipe_count,
            :last_error,
            NOW()
        )
        ON CONFLICT (status_key) DO UPDATE SET
            status = EXCLUDED.status,
            matcher_version = EXCLUDED.matcher_version,
            recipe_compiler_version = EXCLUDED.recipe_compiler_version,
            index_version_hash = EXCLUDED.index_version_hash,
            active_scope_count = EXCLUDED.active_scope_count,
            indexed_recipe_count = EXCLUDED.indexed_recipe_count,
            empty_term_recipe_count = EXCLUDED.empty_term_recipe_count,
            last_error = EXCLUDED.last_error,
            updated_at = NOW()
            {timestamp_field}
    """), {
        "status_key": PANTRY_SEARCH_STATUS_KEY,
        "status": status,
        "matcher_version": MATCHER_VERSION,
        "recipe_compiler_version": RECIPE_COMPILER_VERSION,
        "index_version_hash": PANTRY_SEARCH_INDEX_VERSION_HASH,
        "active_scope_count": active_scope_count,
        "indexed_recipe_count": indexed_recipe_count,
        "empty_term_recipe_count": empty_term_recipe_count,
        "last_error": last_error,
    })


def mark_compiled_recipe_search_term_index_degraded(error: str) -> None:
    try:
        ensure_compiled_recipe_search_term_index_table()
        with get_db_session() as db:
            _upsert_status(
                db,
                status="degraded",
                active_scope_count=0,
                indexed_recipe_count=0,
                empty_term_recipe_count=0,
                last_error=str(error)[:1000],
                full_refresh=False,
                incremental_refresh=False,
            )
            db.commit()
    except Exception as exc:  # pragma: no cover - best-effort diagnostic path
        logger.warning(f"Failed marking pantry search-term index degraded: {exc}")


def refresh_compiled_recipe_search_term_index() -> dict[str, Any]:
    """Rebuild the pantry search-term index for all active recipes."""
    try:
        ensure_compiled_recipe_search_term_index_table()
        with get_db_session() as db:
            recipes = _active_recipe_query(db)
            source_hash_map = _load_source_hash_map(db, [str(recipe.id) for recipe in recipes])
        rows, empty_recipe_ids = _build_index_rows(recipes, source_hash_map)

        with get_db_session() as db:
            _acquire_refresh_lock(db)
            db.execute(CompiledRecipeSearchTermIndex.__table__.delete())
            if rows:
                db.bulk_insert_mappings(CompiledRecipeSearchTermIndex, rows)
            _upsert_status(
                db,
                status="ready",
                active_scope_count=len(recipes),
                indexed_recipe_count=len({str(row["found_recipe_id"]) for row in rows}),
                empty_term_recipe_count=len(empty_recipe_ids),
                last_error=None,
                full_refresh=True,
                incremental_refresh=False,
            )
            db.commit()

        return {
            "matcher_version": MATCHER_VERSION,
            "recipe_compiler_version": RECIPE_COMPILER_VERSION,
            "index_version_hash": PANTRY_SEARCH_INDEX_VERSION_HASH,
            "active_scope_count": len(recipes),
            "indexed_recipe_count": len({str(row["found_recipe_id"]) for row in rows}),
            "empty_term_recipe_count": len(empty_recipe_ids),
            "index_rows": len(rows),
            "distinct_terms": len({row["term"] for row in rows}),
            "refresh_mode": "full",
        }
    except Exception as exc:
        mark_compiled_recipe_search_term_index_degraded(str(exc))
        raise


def _dedupe_ids(*id_lists: list[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for id_list in id_lists:
        for value in id_list or []:
            if value is None:
                continue
            str_value = str(value)
            if str_value in seen:
                continue
            seen.add(str_value)
            result.append(str_value)
    return result


def refresh_compiled_recipe_search_term_index_for_recipe_ids(
    recipe_ids: list[str],
    remove_recipe_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Refresh pantry search-term index rows for selected recipes."""
    affected_ids = _dedupe_ids(recipe_ids, remove_recipe_ids)
    if not affected_ids:
        return {
            "matcher_version": MATCHER_VERSION,
            "recipe_compiler_version": RECIPE_COMPILER_VERSION,
            "index_version_hash": PANTRY_SEARCH_INDEX_VERSION_HASH,
            "active_scope_count": None,
            "indexed_recipe_count": 0,
            "empty_term_recipe_count": 0,
            "index_rows": 0,
            "missing_recipe_ids": [],
            "inactive_recipe_ids": [],
            "refresh_mode": "incremental",
        }

    try:
        ensure_compiled_recipe_search_term_index_table()
        with get_db_session() as db:
            status = _status_row(db)
            if (
                not status
                or status.get("status") != "ready"
                or status.get("matcher_version") != MATCHER_VERSION
                or status.get("recipe_compiler_version") != RECIPE_COMPILER_VERSION
                or status.get("index_version_hash") != PANTRY_SEARCH_INDEX_VERSION_HASH
            ):
                return {
                    "success": False,
                    "skipped": True,
                    "reason": "full_refresh_required_before_incremental",
                    "matcher_version": MATCHER_VERSION,
                    "recipe_compiler_version": RECIPE_COMPILER_VERSION,
                    "index_version_hash": PANTRY_SEARCH_INDEX_VERSION_HASH,
                    "active_scope_count": None,
                    "indexed_recipe_count": 0,
                    "empty_term_recipe_count": 0,
                    "index_rows": 0,
                    "missing_recipe_ids": [],
                    "inactive_recipe_ids": [],
                    "refresh_mode": "incremental",
                }
            recipes = _active_recipe_query(db, affected_ids)
            source_hash_map = _load_source_hash_map(db, [str(recipe.id) for recipe in recipes])
            found_rows = db.query(FoundRecipe.id, FoundRecipe.excluded).filter(
                FoundRecipe.id.in_(affected_ids)
            ).all()

        found_ids = {str(row.id) for row in found_rows}
        active_ids = {str(recipe.id) for recipe in recipes}
        missing_ids = [recipe_id for recipe_id in affected_ids if recipe_id not in found_ids]
        inactive_ids = [
            recipe_id for recipe_id in affected_ids
            if recipe_id in found_ids and recipe_id not in active_ids
        ]
        rows, empty_recipe_ids = _build_index_rows(recipes, source_hash_map)

        with get_db_session() as db:
            _acquire_refresh_lock(db)
            db.query(CompiledRecipeSearchTermIndex).filter(
                CompiledRecipeSearchTermIndex.found_recipe_id.in_(affected_ids)
            ).delete(synchronize_session=False)
            if rows:
                db.bulk_insert_mappings(CompiledRecipeSearchTermIndex, rows)
            active_scope_count = _active_scope_count(db)
            indexed_recipe_count = int(db.execute(text("""
                SELECT COUNT(DISTINCT found_recipe_id)
                FROM compiled_recipe_search_term_index
                WHERE matcher_version = :matcher_version
                  AND recipe_compiler_version = :recipe_compiler_version
                  AND index_version_hash = :index_version_hash
            """), {
                "matcher_version": MATCHER_VERSION,
                "recipe_compiler_version": RECIPE_COMPILER_VERSION,
                "index_version_hash": PANTRY_SEARCH_INDEX_VERSION_HASH,
            }).scalar() or 0)
            empty_term_recipe_count = max(active_scope_count - indexed_recipe_count, 0)
            _upsert_status(
                db,
                status="ready",
                active_scope_count=active_scope_count,
                indexed_recipe_count=indexed_recipe_count,
                empty_term_recipe_count=empty_term_recipe_count,
                last_error=None,
                full_refresh=False,
                incremental_refresh=True,
            )
            db.commit()

        return {
            "matcher_version": MATCHER_VERSION,
            "recipe_compiler_version": RECIPE_COMPILER_VERSION,
            "index_version_hash": PANTRY_SEARCH_INDEX_VERSION_HASH,
            "active_scope_count": active_scope_count,
            "indexed_recipe_count": indexed_recipe_count,
            "empty_term_recipe_count": empty_term_recipe_count,
            "index_rows": len(rows),
            "distinct_terms": len({row["term"] for row in rows}),
            "missing_recipe_ids": missing_ids,
            "inactive_recipe_ids": inactive_ids,
            "refresh_mode": "incremental",
        }
    except Exception as exc:
        mark_compiled_recipe_search_term_index_degraded(str(exc))
        raise


def _status_row(db) -> dict[str, Any] | None:
    row = db.execute(text("""
        SELECT status,
               matcher_version,
               recipe_compiler_version,
               index_version_hash,
               active_scope_count,
               indexed_recipe_count,
               empty_term_recipe_count,
               last_error
        FROM compiled_recipe_search_term_index_status
        WHERE status_key = :status_key
    """), {"status_key": PANTRY_SEARCH_STATUS_KEY}).mappings().fetchone()
    return dict(row) if row else None


def compiled_recipe_search_term_index_needs_refresh() -> tuple[bool, str]:
    """Return whether the pantry search-term index should be refreshed."""
    try:
        ensure_compiled_recipe_search_term_index_table()
        with get_db_session() as db:
            status = _status_row(db)
            if not status:
                return True, "status_missing"
            total_scope = _active_scope_count(db)
            if status.get("status") != "ready":
                return True, f"status_{status.get('status') or 'unknown'}"
            expected_versions = {
                "matcher_version": MATCHER_VERSION,
                "recipe_compiler_version": RECIPE_COMPILER_VERSION,
                "index_version_hash": PANTRY_SEARCH_INDEX_VERSION_HASH,
            }
            for field, expected in expected_versions.items():
                if status.get(field) != expected:
                    return True, f"{field}_mismatch"
            if int(status.get("active_scope_count") or 0) != total_scope:
                return True, "active_scope_count_mismatch"
            return False, "ready"
    except Exception as exc:
        return True, f"check_failed:{exc}"


def _indexed_terms(db, terms: set[str]) -> set[str]:
    if not terms:
        return set()
    rows = db.execute(text("""
        SELECT DISTINCT term
        FROM compiled_recipe_search_term_index
        WHERE matcher_version = :matcher_version
          AND recipe_compiler_version = :recipe_compiler_version
          AND index_version_hash = :index_version_hash
          AND term = ANY(CAST(:terms AS text[]))
    """), {
        "matcher_version": MATCHER_VERSION,
        "recipe_compiler_version": RECIPE_COMPILER_VERSION,
        "index_version_hash": PANTRY_SEARCH_INDEX_VERSION_HASH,
        "terms": sorted(terms),
    }).fetchall()
    return {row.term for row in rows}


def _coverage_for_query(db, query: PantryQuery) -> tuple[float, float, set[str]]:
    all_terms = {term for terms in query.terms_by_input for term in terms}
    indexed = _indexed_terms(db, all_terms)
    if not query.terms_by_input:
        return 0.0, 0.0, indexed

    input_hits = sum(1 for terms in query.terms_by_input if set(terms) & indexed)
    keyword_hits = sum(1 for term in all_terms if term in indexed)
    query_index_coverage_pct = round((input_hits / len(query.terms_by_input)) * 100, 4)
    query_keyword_index_coverage_pct = round((keyword_hits / len(all_terms)) * 100, 4) if all_terms else 0.0
    return query_index_coverage_pct, query_keyword_index_coverage_pct, indexed


def _fallback_selection(
    reason: str,
    *,
    total_scope: int = 0,
    candidate_limit: int = 0,
    query_index_coverage_pct: float = 0.0,
    query_keyword_index_coverage_pct: float = 0.0,
    matched_index_terms: Iterable[str] = (),
) -> PantryIndexSelection:
    return PantryIndexSelection(
        use_index=False,
        fallback_reason=reason,
        full_match=[],
        partial_match=[],
        total_scope=total_scope,
        candidate_limit=candidate_limit,
        candidate_count=0,
        scored_candidate_count=0,
        query_index_coverage_pct=query_index_coverage_pct,
        query_keyword_index_coverage_pct=query_keyword_index_coverage_pct,
        matched_index_terms=tuple(sorted(matched_index_terms)),
    )


def _query_pairs(query: PantryQuery) -> list[tuple[str, int]]:
    pairs: list[tuple[str, int]] = []
    for input_index, terms in enumerate(query.terms_by_input):
        for term in terms:
            pairs.append((term, input_index))
    return pairs


def _query_terms_cte_params(query: PantryQuery) -> tuple[list[str], dict[str, Any]]:
    values_sql: list[str] = []
    params: dict[str, Any] = {}
    for index, (term, input_index) in enumerate(_query_pairs(query)):
        term_param = f"term_{index}"
        input_param = f"input_{index}"
        values_sql.append(f"(:{term_param}, :{input_param})")
        params[term_param] = term
        params[input_param] = input_index
    return values_sql, params


def resolve_pantry_candidate_limit(
    query: PantryQuery,
    *,
    total_scope: int,
    candidate_hard_cap: int = 0,
) -> int:
    """Resolve the optional safety cap before loading recipe payloads.

    The normal value is the active pantry scope, meaning "do not cap". A
    positive hard cap is only an experiment/safety valve; it should not be the
    relevance strategy.
    """
    del query
    total_scope = max(0, int(total_scope or 0))
    if total_scope == 0:
        return 0
    if candidate_hard_cap and candidate_hard_cap > 0:
        return max(1, min(total_scope, int(candidate_hard_cap)))
    return total_scope


def _row_to_recipe_data(row: Any) -> dict[str, Any]:
    missing_preview = list(row.missing_preview or [])
    return {
        "id": str(row.id),
        "name": row.name,
        "url": row.url,
        "source": row.source_name,
        "image_url": row.local_image_path or row.image_url,
        "prep_time_minutes": row.prep_time_minutes,
        "servings": row.servings,
        "ingredients": row.ingredients or [],
        "total_ingredients": int(row.total_ingredients or 0),
        "matched_ingredients": int(row.matched_ingredients or 0),
        "missing_count": int(row.missing_count or 0),
        "missing_preview": missing_preview[:3],
        "coverage_pct": float(row.coverage_pct or 0),
    }


def _score_index_candidates(
    db,
    query: PantryQuery,
    *,
    candidate_limit: int,
    full_limit: int,
    partial_limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int]:
    values_sql, query_params = _query_terms_cte_params(query)
    if not values_sql:
        return [], [], 0, 0

    params: dict[str, Any] = {
        "matcher_version": MATCHER_VERSION,
        "recipe_compiler_version": RECIPE_COMPILER_VERSION,
        "index_version_hash": PANTRY_SEARCH_INDEX_VERSION_HASH,
        "candidate_limit": candidate_limit,
        "full_limit": full_limit,
        "partial_limit": partial_limit,
        "coverage_threshold": 0.5,
        "partial_missing_limit": 3,
    }
    params.update(query_params)

    rows = db.execute(text(f"""
        WITH query_terms(term, input_index) AS (
            VALUES {", ".join(values_sql)}
        ),
        candidate_recipes AS (
            SELECT t.found_recipe_id,
                   COUNT(DISTINCT q.input_index) AS candidate_matched_inputs,
                   COUNT(DISTINCT t.term) AS candidate_matched_terms
            FROM compiled_recipe_search_term_index t
            JOIN query_terms q ON q.term = t.term
            WHERE t.matcher_version = :matcher_version
              AND t.recipe_compiler_version = :recipe_compiler_version
              AND t.index_version_hash = :index_version_hash
            GROUP BY t.found_recipe_id
        ),
        ranked_candidates AS (
            SELECT found_recipe_id,
                   ROW_NUMBER() OVER (
                       ORDER BY candidate_matched_inputs DESC,
                                candidate_matched_terms DESC,
                                found_recipe_id ASC
                   ) AS candidate_rank
            FROM candidate_recipes
        ),
        candidate_pool AS (
            SELECT found_recipe_id
            FROM ranked_candidates
            WHERE candidate_rank <= :candidate_limit
        ),
        recipe_terms AS (
            SELECT t.found_recipe_id, t.term
            FROM compiled_recipe_search_term_index t
            JOIN candidate_pool c ON c.found_recipe_id = t.found_recipe_id
            WHERE t.matcher_version = :matcher_version
              AND t.recipe_compiler_version = :recipe_compiler_version
              AND t.index_version_hash = :index_version_hash
              AND t.term_type = 'normalized_word'
        ),
        term_matches AS (
            SELECT rt.found_recipe_id,
                   rt.term,
                   EXISTS (
                       SELECT 1
                       FROM query_terms q
                       WHERE q.term = rt.term
                          OR POSITION(q.term IN rt.term) > 0
                          OR POSITION(rt.term IN q.term) > 0
                   ) AS matched
            FROM recipe_terms rt
        ),
        recipe_scores AS (
            SELECT found_recipe_id,
                   COUNT(*) AS total_ingredients,
                   COUNT(*) FILTER (WHERE matched) AS matched_ingredients,
                   ARRAY_AGG(term ORDER BY term) FILTER (WHERE NOT matched) AS missing_terms
            FROM term_matches
            GROUP BY found_recipe_id
        ),
        eligible AS (
            SELECT found_recipe_id,
                   total_ingredients,
                   matched_ingredients,
                   COALESCE(CARDINALITY(missing_terms), 0) AS missing_count,
                   COALESCE(missing_terms, ARRAY[]::text[]) AS missing_terms,
                   ROUND(
                       ((matched_ingredients::numeric / NULLIF(total_ingredients, 0)) * 100),
                       1
                   ) AS coverage_pct
            FROM recipe_scores
            WHERE total_ingredients > 0
              AND (matched_ingredients::numeric / total_ingredients) >= :coverage_threshold
              AND COALESCE(CARDINALITY(missing_terms), 0) <= :partial_missing_limit
        ),
        ranked_results AS (
            SELECT r.id,
                   r.name,
                   r.url,
                   r.source_name,
                   r.image_url,
                   r.local_image_path,
                   r.ingredients,
                   r.prep_time_minutes,
                   r.servings,
                   e.total_ingredients,
                   e.matched_ingredients,
                   e.missing_count,
                   e.missing_terms[1:3] AS missing_preview,
                   e.coverage_pct,
                   (e.missing_count = 0) AS is_full_match,
                   ROW_NUMBER() OVER (
                       PARTITION BY (e.missing_count = 0)
                       ORDER BY
                           CASE WHEN e.missing_count = 0 THEN e.coverage_pct END DESC,
                           CASE WHEN e.missing_count = 0 THEN e.matched_ingredients END DESC,
                           CASE WHEN e.missing_count <> 0 THEN e.missing_count END ASC,
                           CASE WHEN e.missing_count <> 0 THEN e.coverage_pct END DESC,
                           r.name ASC,
                           r.id ASC
                   ) AS result_rank,
                   (SELECT COUNT(*) FROM candidate_recipes) AS candidate_count,
                   (SELECT COUNT(*) FROM candidate_pool) AS scored_candidate_count
            FROM eligible e
            JOIN found_recipes r ON r.id = e.found_recipe_id
            WHERE r.ingredients IS NOT NULL
              AND jsonb_array_length(r.ingredients) > 0
              AND (r.excluded = FALSE OR r.excluded IS NULL)
        )
        SELECT *
        FROM ranked_results
        WHERE (is_full_match AND result_rank <= :full_limit)
           OR ((NOT is_full_match) AND result_rank <= :partial_limit)
        ORDER BY is_full_match DESC,
                 missing_count ASC,
                 coverage_pct DESC,
                 matched_ingredients DESC,
                 name ASC,
                 id ASC
    """), params).fetchall()

    if rows:
        candidate_count = int(rows[0].candidate_count or 0)
        scored_candidate_count = int(rows[0].scored_candidate_count or 0)
    else:
        candidate_count, scored_candidate_count = _score_index_candidate_counts(
            db,
            query,
            candidate_limit=candidate_limit,
        )

    full_match = [_row_to_recipe_data(row) for row in rows if row.is_full_match]
    partial_match = [_row_to_recipe_data(row) for row in rows if not row.is_full_match]
    return full_match, partial_match, candidate_count, scored_candidate_count


def _score_index_candidate_counts(
    db,
    query: PantryQuery,
    *,
    candidate_limit: int,
) -> tuple[int, int]:
    values_sql, query_params = _query_terms_cte_params(query)
    if not values_sql:
        return 0, 0
    params: dict[str, Any] = {
        "matcher_version": MATCHER_VERSION,
        "recipe_compiler_version": RECIPE_COMPILER_VERSION,
        "index_version_hash": PANTRY_SEARCH_INDEX_VERSION_HASH,
        "candidate_limit": candidate_limit,
    }
    params.update(query_params)
    row = db.execute(text(f"""
        WITH query_terms(term, input_index) AS (
            VALUES {", ".join(values_sql)}
        ),
        candidate_recipes AS (
            SELECT t.found_recipe_id,
                   COUNT(DISTINCT q.input_index) AS candidate_matched_inputs,
                   COUNT(DISTINCT t.term) AS candidate_matched_terms
            FROM compiled_recipe_search_term_index t
            JOIN query_terms q ON q.term = t.term
            WHERE t.matcher_version = :matcher_version
              AND t.recipe_compiler_version = :recipe_compiler_version
              AND t.index_version_hash = :index_version_hash
            GROUP BY t.found_recipe_id
        ),
        ranked_candidates AS (
            SELECT found_recipe_id,
                   ROW_NUMBER() OVER (
                       ORDER BY candidate_matched_inputs DESC,
                                candidate_matched_terms DESC,
                                found_recipe_id ASC
                   ) AS candidate_rank
            FROM candidate_recipes
        )
        SELECT
            (SELECT COUNT(*) FROM candidate_recipes) AS candidate_count,
            (SELECT COUNT(*) FROM ranked_candidates WHERE candidate_rank <= :candidate_limit)
                AS scored_candidate_count
    """), params).fetchone()
    if not row:
        return 0, 0
    return int(row.candidate_count or 0), int(row.scored_candidate_count or 0)


def select_pantry_index_matches(
    query: PantryQuery,
    *,
    max_candidates: int = 0,
    full_limit: int = 100,
    partial_limit: int = 200,
) -> PantryIndexSelection:
    """Return pantry matches scored in SQL from the compiled index, or fallback."""
    try:
        ensure_compiled_recipe_search_term_index_table()
    except Exception as exc:
        return _fallback_selection(f"index_table_unavailable:{exc}")

    with get_db_session() as db:
        status = _status_row(db)
        if not status:
            return _fallback_selection("index_status_missing")
        total_scope = _active_scope_count(db)

        if status.get("status") != "ready":
            return _fallback_selection(
                "index_not_ready",
                total_scope=total_scope,
            )
        expected_versions = {
            "matcher_version": MATCHER_VERSION,
            "recipe_compiler_version": RECIPE_COMPILER_VERSION,
            "index_version_hash": PANTRY_SEARCH_INDEX_VERSION_HASH,
        }
        for field, expected in expected_versions.items():
            if status.get(field) != expected:
                return _fallback_selection(
                    f"{field}_mismatch",
                    total_scope=total_scope,
                )
        if int(status.get("active_scope_count") or 0) != total_scope:
            return _fallback_selection(
                "active_scope_count_mismatch",
                total_scope=total_scope,
            )
        candidate_limit = resolve_pantry_candidate_limit(
            query,
            total_scope=total_scope,
            candidate_hard_cap=max_candidates,
        )

        query_coverage, keyword_coverage, matched_terms = _coverage_for_query(db, query)
        if query_coverage < PANTRY_QUERY_INDEX_COVERAGE_THRESHOLD * 100:
            return _fallback_selection(
                "query_index_coverage_below_threshold",
                total_scope=total_scope,
                candidate_limit=candidate_limit,
                query_index_coverage_pct=query_coverage,
                query_keyword_index_coverage_pct=keyword_coverage,
                matched_index_terms=matched_terms,
            )

        full_match, partial_match, candidate_count, scored_candidate_count = _score_index_candidates(
            db,
            query,
            candidate_limit=candidate_limit,
            full_limit=full_limit,
            partial_limit=partial_limit,
        )

    if not full_match and not partial_match:
        return _fallback_selection(
            "no_index_matches",
            total_scope=total_scope,
            candidate_limit=candidate_limit,
            query_index_coverage_pct=query_coverage,
            query_keyword_index_coverage_pct=keyword_coverage,
            matched_index_terms=matched_terms,
        )

    return PantryIndexSelection(
        use_index=True,
        fallback_reason=None,
        full_match=full_match,
        partial_match=partial_match,
        total_scope=total_scope,
        candidate_limit=candidate_limit,
        candidate_count=candidate_count,
        scored_candidate_count=scored_candidate_count,
        query_index_coverage_pct=query_coverage,
        query_keyword_index_coverage_pct=keyword_coverage,
        matched_index_terms=tuple(sorted(matched_terms)),
    )


def load_legacy_pantry_recipes() -> list[Any]:
    with get_db_session() as db:
        return db.execute(text("""
            SELECT id, name, url, source_name, image_url, local_image_path,
                   ingredients, prep_time_minutes, servings
            FROM found_recipes
            WHERE ingredients IS NOT NULL
            AND jsonb_array_length(ingredients) > 0
            AND (excluded = FALSE OR excluded IS NULL)
        """)).fetchall()


def score_pantry_recipes(recipes: list[Any], query: PantryQuery) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    full_match: list[dict[str, Any]] = []
    partial_match: list[dict[str, Any]] = []
    user_keywords = list(query.user_keywords)
    ignore_words = _cached_pantry_ignore_words()
    unit_words = _unit_words()

    for recipe in recipes:
        recipe_ingredients = recipe.ingredients or []
        if not recipe_ingredients:
            continue
        if is_boring_recipe(recipe.name):
            continue

        recipe_keywords = build_recipe_scoring_keywords(
            recipe_ingredients,
            ignore_words=ignore_words,
            unit_words=unit_words,
        )
        if not recipe_keywords:
            continue

        matched = 0
        missing: list[str] = []
        for recipe_keyword in recipe_keywords:
            found = False
            for user_keyword in user_keywords:
                if user_keyword in recipe_keyword or recipe_keyword in user_keyword:
                    found = True
                    break
                min_len = min(len(user_keyword), len(recipe_keyword))
                if min_len > 3:
                    prefix_len = sum(1 for a, b in zip(user_keyword, recipe_keyword) if a == b)
                    if prefix_len >= min_len * 0.75:
                        found = True
                        break
            if found:
                matched += 1
            else:
                missing.append(recipe_keyword)

        coverage = matched / len(recipe_keywords) if recipe_keywords else 0
        if coverage < 0.5:
            continue

        recipe_data = {
            "id": str(recipe.id),
            "name": recipe.name,
            "url": recipe.url,
            "source": recipe.source_name,
            "image_url": recipe.local_image_path or recipe.image_url,
            "prep_time_minutes": recipe.prep_time_minutes,
            "servings": recipe.servings,
            "ingredients": recipe.ingredients or [],
            "total_ingredients": len(recipe_keywords),
            "matched_ingredients": matched,
            "missing_count": len(missing),
            "missing_preview": missing[:3],
            "coverage_pct": round(coverage * 100, 1),
        }
        if not missing:
            full_match.append(recipe_data)
        elif len(missing) <= 3:
            partial_match.append(recipe_data)

    full_match.sort(key=lambda item: (-item["coverage_pct"], -item["matched_ingredients"], item["name"], item["id"]))
    partial_match.sort(key=lambda item: (item["missing_count"], -item["coverage_pct"], item["name"], item["id"]))
    return full_match, partial_match


def log_pantry_index_selection(prefix: str, selection: PantryIndexSelection, *, elapsed_ms: int | None = None) -> None:
    logger.info(
        "{} candidate_source={} fallback={} candidates={} scored={} total_scope={} "
        "candidate_limit={} query_index_coverage_pct={} "
        "query_keyword_index_coverage_pct={} elapsed_ms={}",
        prefix,
        "search_term_index" if selection.use_index else "fallback",
        selection.fallback_reason,
        selection.candidate_count,
        selection.scored_candidate_count,
        selection.total_scope,
        selection.candidate_limit,
        selection.query_index_coverage_pct,
        selection.query_keyword_index_coverage_pct,
        elapsed_ms,
    )
