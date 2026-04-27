"""Persistent term indexes for candidate routing."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError

try:
    from database import get_db_session
    from models import (
        CompiledOfferTermIndex,
        CompiledRecipeTermIndex,
        FoundRecipe,
        Offer,
    )
except ModuleNotFoundError:
    from app.database import get_db_session
    from app.models import (
        CompiledOfferTermIndex,
        CompiledRecipeTermIndex,
        FoundRecipe,
        Offer,
    )

from ..normalization import fix_swedish_chars
from .compiled_offers import load_compiled_offer_runtime_cache
from .offer_identity import build_offer_identity_key
from .recipe_identity import build_recipe_identity_key
from .compiled_recipes import ensure_compiled_recipe_match_table, load_compiled_recipe_payload_cache
from .normalization import _SPACE_NORMALIZATIONS, _apply_space_normalizations
from .parent_maps import PARENT_MATCH_ONLY
from .recipe_text import expand_grouped_ingredient_text, rewrite_buljong_eller_fond
from .synonyms import INGREDIENT_PARENTS
from .versioning import MATCHER_VERSION, OFFER_COMPILER_VERSION, RECIPE_COMPILER_VERSION

_COMPILED_OFFER_TERM_REFRESH_LOCK = 82003
_COMPILED_RECIPE_TERM_REFRESH_LOCK = 82004
_TERM_TYPE_PRIORITY = {
    "keyword": 0,
    "parent_keyword": 1,
    "name_word": 2,
}


_HALFTEN_TILL_RE = re.compile(r'hälften till \w+')


def _stable_json_hash(payload: Any) -> str:
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def ensure_compiled_offer_term_index_table() -> None:
    with get_db_session() as db:
        exists = db.execute(text(
            "SELECT to_regclass('public.compiled_offer_term_index')"
        )).scalar()
    if not exists:
        raise RuntimeError(
            "compiled_offer_term_index table is missing. Apply the schema change "
            "from database/init.sql before running candidate-routing tools."
        )


def ensure_compiled_recipe_term_index_table() -> None:
    with get_db_session() as db:
        exists = db.execute(text(
            "SELECT to_regclass('public.compiled_recipe_term_index')"
        )).scalar()
    if not exists:
        raise RuntimeError(
            "compiled_recipe_term_index table is missing. Apply the schema change "
            "from database/init.sql before running candidate-routing tools."
        )


def _acquire_refresh_lock(db, lock_key: int) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": lock_key},
    )


def _replace_compiled_term_rows(db, *, table_name: str, model, rows: list[dict[str, Any]], lock_key: int) -> str:
    _acquire_refresh_lock(db, lock_key)
    replace_mode = "truncate"
    try:
        db.execute(text(f"TRUNCATE {table_name}"))
    except ProgrammingError as exc:
        if getattr(exc.orig, "pgcode", None) != "42501":
            raise
        db.rollback()
        replace_mode = "delete_fallback_no_truncate_privilege"
        _acquire_refresh_lock(db, lock_key)
        db.execute(model.__table__.delete())

    if rows:
        db.bulk_insert_mappings(model, rows)
    db.commit()
    return replace_mode


def build_offer_candidate_terms(compiled_offer_data: dict[str, Any]) -> set[tuple[str, str]]:
    """Build the exact term set used by today's candidate-routing loop."""
    terms: set[tuple[str, str]] = set()
    keywords = {str(value) for value in compiled_offer_data.get("keywords", ()) if value}
    carrier_stripped = {str(value) for value in compiled_offer_data.get("carrier_stripped", ()) if value}

    for keyword in keywords:
        terms.add((keyword, "keyword"))
        parent = INGREDIENT_PARENTS.get(keyword) or PARENT_MATCH_ONLY.get(keyword)
        if parent:
            terms.add((parent, "parent_keyword"))

    for word in str(compiled_offer_data.get("name_normalized", "")).split():
        if len(word) >= 4 and word not in keywords and word not in carrier_stripped:
            terms.add((word, "name_word"))

    return terms


def build_offer_candidate_term_map(
    offer_data_cache: dict[int, dict[str, Any]],
) -> dict[str, set[int]]:
    term_to_offer_ids: dict[str, set[int]] = defaultdict(set)
    for offer_object_id, compiled_offer_data in offer_data_cache.items():
        for term, _term_type in build_offer_candidate_terms(compiled_offer_data):
            term_to_offer_ids[term].add(offer_object_id)
    return term_to_offer_ids


def build_fts_keyword_set(
    offer_data_cache: dict[int, dict[str, Any]],
) -> set[str]:
    """Match the current FTS pre-filter term expansion in cache_manager.py."""
    all_keywords: set[str] = set()
    for compiled_offer_data in offer_data_cache.values():
        keywords = set(compiled_offer_data.get("keywords", ()))
        all_keywords.update(keywords)
        for keyword in keywords:
            parent = INGREDIENT_PARENTS.get(keyword)
            if parent:
                all_keywords.add(parent)

    reverse_space_normalizations: dict[str, set[str]] = {}
    for source, destination in _SPACE_NORMALIZATIONS:
        reverse_space_normalizations.setdefault(destination, set()).add(source)

    for keyword in list(all_keywords):
        all_keywords.update(reverse_space_normalizations.get(keyword, ()))

    return all_keywords


def build_recipe_search_text(recipe: FoundRecipe) -> str:
    expanded_ingredients: list[str] = []
    for ingredient in recipe.ingredients or ():
        expanded = expand_grouped_ingredient_text(str(ingredient))
        if expanded:
            expanded_ingredients.extend(expanded)

    if not expanded_ingredients:
        return ""

    search_text = fix_swedish_chars(
        " ".join(str(ingredient).lower() for ingredient in expanded_ingredients)
    ).lower()
    search_text = _apply_space_normalizations(search_text)
    search_text = rewrite_buljong_eller_fond(search_text)
    search_text = _HALFTEN_TILL_RE.sub("", search_text)
    return search_text


def build_recipe_search_text_map(
    recipes: list[FoundRecipe],
    *,
    compiled_recipe_payload_cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, str]:
    search_texts: dict[str, str] = {}
    for recipe in recipes:
        recipe_id = str(recipe.id)
        if compiled_recipe_payload_cache is not None:
            payload = compiled_recipe_payload_cache.get(recipe_id, {})
            search_text = str(payload.get("ingredients_search_text", "")).strip()
        else:
            search_text = build_recipe_search_text(recipe).strip()
        if search_text:
            search_texts[recipe_id] = search_text
    return search_texts


def build_relevant_offer_map_from_search_texts(
    recipe_search_texts: dict[str, str],
    term_to_offer_ids: dict[str, set[str] | set[int]],
) -> dict[str, set[str] | set[int]]:
    relevant_offer_map: dict[str, set[str] | set[int]] = {}
    for recipe_id, search_text in recipe_search_texts.items():
        relevant: set[str] | set[int] = set()
        for term, offer_ids in term_to_offer_ids.items():
            if term in search_text:
                relevant.update(offer_ids)
        if relevant:
            relevant_offer_map[recipe_id] = relevant
    return relevant_offer_map


def build_candidate_map_from_term_postings(
    recipe_term_postings: dict[str, set[str]],
    offer_term_postings: dict[str, set[str]],
) -> dict[str, set[str]]:
    candidate_map: dict[str, set[str]] = defaultdict(set)
    for term, recipe_ids in recipe_term_postings.items():
        offer_ids = offer_term_postings.get(term)
        if not offer_ids:
            continue
        for recipe_id in recipe_ids:
            candidate_map[recipe_id].update(offer_ids)
    return {recipe_id: set(offer_ids) for recipe_id, offer_ids in candidate_map.items()}


def build_candidate_term_detail_from_term_postings(
    recipe_term_postings: dict[str, set[str]],
    offer_term_postings: dict[str, set[str]],
) -> dict[str, dict[str, set[str]]]:
    """Build recipe -> offer -> routing terms without changing candidate routing."""
    candidate_detail: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for term, recipe_ids in recipe_term_postings.items():
        offer_ids = offer_term_postings.get(term)
        if not offer_ids:
            continue
        for recipe_id in recipe_ids:
            recipe_detail = candidate_detail[recipe_id]
            for offer_id in offer_ids:
                recipe_detail[offer_id].add(term)
    return {
        recipe_id: {
            offer_id: set(terms)
            for offer_id, terms in offer_terms.items()
        }
        for recipe_id, offer_terms in candidate_detail.items()
    }


def _build_term_manifest(term_pairs: set[tuple[str, str]]) -> tuple[list[dict[str, str]], str]:
    payload = [
        {"term": term, "term_type": term_type}
        for term, term_type in sorted(term_pairs)
    ]
    return payload, _stable_json_hash(payload)


def _term_type_sort_key(term_type: str) -> tuple[int, str]:
    return (_TERM_TYPE_PRIORITY.get(term_type, 99), term_type)


def _select_routing_term_types(term_pairs: set[tuple[str, str]]) -> dict[str, str]:
    selected: dict[str, str] = {}
    for term, term_type in sorted(term_pairs):
        current = selected.get(term)
        if current is None or _term_type_sort_key(term_type) < _term_type_sort_key(current):
            selected[term] = term_type
    return selected


def refresh_compiled_offer_term_index() -> dict[str, Any]:
    ensure_compiled_offer_term_index_table()
    with get_db_session() as db:
        _acquire_refresh_lock(db, _COMPILED_OFFER_TERM_REFRESH_LOCK)
        offers = db.query(Offer).order_by(Offer.id).all()

    offer_data_cache, _stats = load_compiled_offer_runtime_cache(offers)

    term_pairs_by_offer: dict[str, set[tuple[str, str]]] = {}
    manifest_terms: set[tuple[str, str]] = set()
    for offer in offers:
        terms = build_offer_candidate_terms(offer_data_cache[id(offer)])
        term_pairs_by_offer[str(offer.id)] = terms
        manifest_terms.update(terms)

    manifest_payload, term_manifest_hash = _build_term_manifest(manifest_terms)
    indexed_at = datetime.now(timezone.utc)
    rows = []
    for offer in offers:
        for term, term_type in sorted(term_pairs_by_offer[str(offer.id)]):
            rows.append({
                "offer_id": offer.id,
                "offer_identity_key": build_offer_identity_key(offer),
                "store_id": offer.store_id,
                "matcher_version": MATCHER_VERSION,
                "offer_compiler_version": OFFER_COMPILER_VERSION,
                "term_manifest_hash": term_manifest_hash,
                "term": term,
                "term_type": term_type,
                "indexed_at": indexed_at,
            })

    with get_db_session() as db:
        replace_mode = _replace_compiled_term_rows(
            db,
            table_name="compiled_offer_term_index",
            model=CompiledOfferTermIndex,
            rows=rows,
            lock_key=_COMPILED_OFFER_TERM_REFRESH_LOCK,
        )

    return {
        "matcher_version": MATCHER_VERSION,
        "offer_compiler_version": OFFER_COMPILER_VERSION,
        "indexed_offers": len(offers),
        "index_rows": len(rows),
        "distinct_terms": len(manifest_terms),
        "term_manifest_hash": term_manifest_hash,
        "replace_mode": replace_mode,
        "term_manifest_sample": manifest_payload[:20],
    }


def _load_offer_term_rows(
    *,
    matcher_version: str = MATCHER_VERSION,
    offer_compiler_version: str = OFFER_COMPILER_VERSION,
) -> list[CompiledOfferTermIndex]:
    ensure_compiled_offer_term_index_table()
    with get_db_session() as db:
        return db.query(CompiledOfferTermIndex).filter(
            CompiledOfferTermIndex.matcher_version == matcher_version,
            CompiledOfferTermIndex.offer_compiler_version == offer_compiler_version,
        ).all()


def load_compiled_offer_term_manifest(
    *,
    matcher_version: str = MATCHER_VERSION,
    offer_compiler_version: str = OFFER_COMPILER_VERSION,
) -> tuple[set[tuple[str, str]], dict[str, Any]]:
    rows = _load_offer_term_rows(
        matcher_version=matcher_version,
        offer_compiler_version=offer_compiler_version,
    )
    term_pairs = {(row.term, row.term_type) for row in rows}
    manifest_hashes = {row.term_manifest_hash for row in rows}
    if rows and len(manifest_hashes) != 1:
        raise RuntimeError(
            "compiled_offer_term_index contains multiple manifest hashes for the "
            "same matcher/offer compiler version"
        )
    stats = {
        "matcher_version": matcher_version,
        "offer_compiler_version": offer_compiler_version,
        "loaded_rows": len(rows),
        "distinct_terms": len(term_pairs),
        "term_manifest_hash": next(iter(manifest_hashes), None),
    }
    return term_pairs, stats


def load_compiled_offer_term_postings(
    *,
    matcher_version: str = MATCHER_VERSION,
    offer_compiler_version: str = OFFER_COMPILER_VERSION,
    key_field: str = "offer_identity_key",
) -> tuple[dict[str, set[str]], dict[str, Any]]:
    key_columns = {
        "offer_id": CompiledOfferTermIndex.offer_id,
        "offer_identity_key": CompiledOfferTermIndex.offer_identity_key,
        "store_id": CompiledOfferTermIndex.store_id,
    }
    key_column = key_columns.get(key_field)
    if key_column is None:
        raise ValueError(f"Unsupported offer term posting key_field: {key_field}")

    ensure_compiled_offer_term_index_table()
    stmt = (
        select(
            CompiledOfferTermIndex.term,
            key_column.label("posting_key"),
            CompiledOfferTermIndex.offer_identity_key,
            CompiledOfferTermIndex.term_manifest_hash,
        )
        .where(
            CompiledOfferTermIndex.matcher_version == matcher_version,
            CompiledOfferTermIndex.offer_compiler_version == offer_compiler_version,
        )
    )
    with get_db_session() as db:
        rows = db.execute(stmt).mappings().all()

    postings: dict[str, set[str]] = defaultdict(set)
    manifest_hashes = {row["term_manifest_hash"] for row in rows}
    for row in rows:
        postings[row["term"]].add(str(row["posting_key"]))
    stats = {
        "matcher_version": matcher_version,
        "offer_compiler_version": offer_compiler_version,
        "loaded_rows": len(rows),
        "distinct_terms": len(postings),
        "offer_count": len({row["offer_identity_key"] for row in rows}),
        "term_manifest_hash": next(iter(manifest_hashes), None),
    }
    return dict(postings), stats


def refresh_compiled_recipe_term_index() -> dict[str, Any]:
    ensure_compiled_recipe_term_index_table()
    ensure_compiled_recipe_match_table()
    term_pairs, offer_term_stats = load_compiled_offer_term_manifest()
    term_manifest_hash = offer_term_stats["term_manifest_hash"]
    if not term_manifest_hash:
        raise RuntimeError("compiled_offer_term_index is empty; refresh offer term index first")
    routing_term_types = _select_routing_term_types(term_pairs)

    with get_db_session() as db:
        _acquire_refresh_lock(db, _COMPILED_RECIPE_TERM_REFRESH_LOCK)
        recipes = db.query(FoundRecipe).filter(
            (FoundRecipe.excluded == False) | (FoundRecipe.excluded.is_(None))  # noqa: E712
        ).order_by(FoundRecipe.id).all()

    payload_cache, _stats = load_compiled_recipe_payload_cache(recipes)
    search_texts = build_recipe_search_text_map(
        recipes,
        compiled_recipe_payload_cache=payload_cache,
    )

    indexed_at = datetime.now(timezone.utc)
    rows = []
    for recipe in recipes:
        recipe_id = str(recipe.id)
        search_text = search_texts.get(recipe_id)
        if not search_text:
            continue
        recipe_identity_key = build_recipe_identity_key(recipe)
        for term, term_type in sorted(routing_term_types.items()):
            if term in search_text:
                rows.append({
                    "found_recipe_id": recipe.id,
                    "recipe_identity_key": recipe_identity_key,
                    "matcher_version": MATCHER_VERSION,
                    "recipe_compiler_version": RECIPE_COMPILER_VERSION,
                    "term_manifest_hash": term_manifest_hash,
                    "term": term,
                    "term_type": term_type,
                    "indexed_at": indexed_at,
                })

    with get_db_session() as db:
        replace_mode = _replace_compiled_term_rows(
            db,
            table_name="compiled_recipe_term_index",
            model=CompiledRecipeTermIndex,
            rows=rows,
            lock_key=_COMPILED_RECIPE_TERM_REFRESH_LOCK,
        )

    return {
        "matcher_version": MATCHER_VERSION,
        "recipe_compiler_version": RECIPE_COMPILER_VERSION,
        "indexed_recipes": len(recipes),
        "index_rows": len(rows),
        "distinct_terms": len(term_pairs),
        "distinct_routing_terms": len(routing_term_types),
        "term_manifest_hash": term_manifest_hash,
        "replace_mode": replace_mode,
    }


def load_compiled_recipe_term_postings(
    *,
    matcher_version: str = MATCHER_VERSION,
    recipe_compiler_version: str = RECIPE_COMPILER_VERSION,
    term_manifest_hash: str | None = None,
    key_field: str = "found_recipe_id",
) -> tuple[dict[str, set[str]], dict[str, Any]]:
    key_columns = {
        "found_recipe_id": CompiledRecipeTermIndex.found_recipe_id,
        "recipe_identity_key": CompiledRecipeTermIndex.recipe_identity_key,
    }
    key_column = key_columns.get(key_field)
    if key_column is None:
        raise ValueError(f"Unsupported recipe term posting key_field: {key_field}")

    ensure_compiled_recipe_term_index_table()
    stmt = (
        select(
            CompiledRecipeTermIndex.term,
            key_column.label("posting_key"),
            CompiledRecipeTermIndex.term_manifest_hash,
        )
        .where(
            CompiledRecipeTermIndex.matcher_version == matcher_version,
            CompiledRecipeTermIndex.recipe_compiler_version == recipe_compiler_version,
        )
    )
    if term_manifest_hash:
        stmt = stmt.where(CompiledRecipeTermIndex.term_manifest_hash == term_manifest_hash)

    with get_db_session() as db:
        rows = db.execute(stmt).mappings().all()

    postings: dict[str, set[str]] = defaultdict(set)
    manifest_hashes = {row["term_manifest_hash"] for row in rows}
    for row in rows:
        postings[row["term"]].add(str(row["posting_key"]))
    stats = {
        "matcher_version": matcher_version,
        "recipe_compiler_version": recipe_compiler_version,
        "loaded_rows": len(rows),
        "distinct_terms": len(postings),
        "recipe_count": len({row["posting_key"] for row in rows}),
        "term_manifest_hash": next(iter(manifest_hashes), None),
        "key_field": key_field,
    }
    return dict(postings), stats
