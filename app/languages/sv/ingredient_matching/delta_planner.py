"""Delta-impact planning helpers for offer-driven cache rebuilds."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import text

try:
    from database import get_db_session
except ModuleNotFoundError:
    from app.database import get_db_session

from .offer_identity import build_offer_identity_key_from_fields


def invert_term_postings(term_postings: dict[str, set[str]]) -> dict[str, set[str]]:
    """Invert a term→ids posting map into id→terms."""
    id_to_terms: dict[str, set[str]] = defaultdict(set)
    for term, ids in term_postings.items():
        for value in ids:
            id_to_terms[str(value)].add(term)
    return {key: set(values) for key, values in id_to_terms.items()}


def load_persisted_offer_recipe_map() -> dict[str, set[str]]:
    """Load exact stable-offer-identity→recipe relationships from the persisted cache."""
    with get_db_session() as db:
        rows = db.execute(text("""
            SELECT
                found_recipe_id::text AS found_recipe_id,
                jsonb_array_elements(match_data->'matched_offers') AS offer_data
            FROM recipe_offer_cache
            WHERE jsonb_typeof(match_data->'matched_offers') = 'array'
        """)).fetchall()

    result: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        found_recipe_id = str(row.found_recipe_id)
        offer_data = row.offer_data or {}
        offer_identity_key = offer_data.get("offer_identity_key")
        if not offer_identity_key:
            offer_identity_key = build_offer_identity_key_from_fields(
                product_url=offer_data.get("product_url"),
                store_name=offer_data.get("store_name"),
                name=offer_data.get("name"),
                category=offer_data.get("category"),
                weight_grams=offer_data.get("weight_grams"),
            )
        if offer_identity_key:
            result[str(offer_identity_key)].add(found_recipe_id)
    return {offer_identity_key: set(recipe_ids) for offer_identity_key, recipe_ids in result.items()}


def _sorted(values: set[str] | list[str]) -> list[str]:
    return sorted(str(value) for value in values)


def _recipe_ids_for_offer_ids_via_terms(
    offer_ids: list[str],
    *,
    offer_to_terms_maps: list[dict[str, set[str]]],
    recipe_term_postings_maps: list[dict[str, set[str]]],
) -> tuple[list[str], list[str]]:
    terms: set[str] = set()
    recipe_ids: set[str] = set()
    for offer_id in offer_ids:
        for offer_to_terms in offer_to_terms_maps:
            terms.update(offer_to_terms.get(str(offer_id), ()))
    for term in terms:
        for recipe_term_postings in recipe_term_postings_maps:
            recipe_ids.update(recipe_term_postings.get(term, ()))
    return _sorted(recipe_ids), _sorted(terms)


def _recipe_ids_for_offer_ids_via_cache(
    offer_ids: list[str],
    *,
    persisted_offer_recipe_map: dict[str, set[str]],
) -> list[str]:
    recipe_ids: set[str] = set()
    for offer_id in offer_ids:
        recipe_ids.update(persisted_offer_recipe_map.get(str(offer_id), ()))
    return _sorted(recipe_ids)


def plan_offer_delta_recipe_impacts(
    offer_change_summary: dict[str, Any],
    *,
    current_offer_term_postings: dict[str, set[str]],
    persisted_offer_term_postings: dict[str, set[str]],
    current_recipe_term_postings: dict[str, set[str]],
    persisted_recipe_term_postings: dict[str, set[str]],
    persisted_offer_recipe_map: dict[str, set[str]],
) -> dict[str, Any]:
    """Plan which recipe ids would be affected by the current offer delta."""
    current_offer_to_terms = invert_term_postings(current_offer_term_postings)
    persisted_offer_to_terms = invert_term_postings(persisted_offer_term_postings)

    semantic_rematch_offer_ids = list(offer_change_summary.get("semantic_rematch_offer_ids", ()))
    forced_version_rematch_offer_ids = list(offer_change_summary.get("forced_version_rematch_offer_ids", ()))
    rescore_offer_ids = list(offer_change_summary.get("rescore_offer_ids", ()))
    display_only_offer_ids = list(offer_change_summary.get("display_only_offer_ids", ()))

    semantic_rematch_recipe_ids, semantic_terms = _recipe_ids_for_offer_ids_via_terms(
        semantic_rematch_offer_ids,
        offer_to_terms_maps=[current_offer_to_terms, persisted_offer_to_terms],
        recipe_term_postings_maps=[current_recipe_term_postings, persisted_recipe_term_postings],
    )
    forced_version_recipe_ids, forced_terms = _recipe_ids_for_offer_ids_via_terms(
        forced_version_rematch_offer_ids,
        offer_to_terms_maps=[current_offer_to_terms, persisted_offer_to_terms],
        recipe_term_postings_maps=[current_recipe_term_postings, persisted_recipe_term_postings],
    )
    rematch_recipe_ids = _sorted(set(semantic_rematch_recipe_ids) | set(forced_version_recipe_ids))

    raw_rescore_recipe_ids = _recipe_ids_for_offer_ids_via_cache(
        rescore_offer_ids,
        persisted_offer_recipe_map=persisted_offer_recipe_map,
    )
    effective_rescore_recipe_ids = _sorted(set(raw_rescore_recipe_ids) - set(rematch_recipe_ids))

    raw_display_recipe_ids = _recipe_ids_for_offer_ids_via_cache(
        display_only_offer_ids,
        persisted_offer_recipe_map=persisted_offer_recipe_map,
    )
    effective_display_recipe_ids = _sorted(
        set(raw_display_recipe_ids)
        - set(rematch_recipe_ids)
        - set(effective_rescore_recipe_ids)
    )

    all_impacted_recipe_ids = _sorted(
        set(rematch_recipe_ids)
        | set(effective_rescore_recipe_ids)
        | set(effective_display_recipe_ids)
    )

    return {
        "semantic_rematch_recipe_ids": semantic_rematch_recipe_ids,
        "semantic_rematch_terms": semantic_terms,
        "forced_version_rematch_recipe_ids": forced_version_recipe_ids,
        "forced_version_rematch_terms": forced_terms,
        "rematch_recipe_ids": rematch_recipe_ids,
        "raw_rescore_recipe_ids": raw_rescore_recipe_ids,
        "effective_rescore_recipe_ids": effective_rescore_recipe_ids,
        "raw_display_only_recipe_ids": raw_display_recipe_ids,
        "effective_display_only_recipe_ids": effective_display_recipe_ids,
        "all_impacted_recipe_ids": all_impacted_recipe_ids,
        "counts": {
            "semantic_rematch_recipes": len(semantic_rematch_recipe_ids),
            "forced_version_rematch_recipes": len(forced_version_recipe_ids),
            "rematch_recipes": len(rematch_recipe_ids),
            "raw_rescore_recipes": len(raw_rescore_recipe_ids),
            "effective_rescore_recipes": len(effective_rescore_recipe_ids),
            "raw_display_only_recipes": len(raw_display_recipe_ids),
            "effective_display_only_recipes": len(effective_display_recipe_ids),
            "all_impacted_recipes": len(all_impacted_recipe_ids),
        },
    }


def plan_combined_delta_recipe_impacts(
    offer_planner_summary: dict[str, Any],
    recipe_change_summary: dict[str, Any],
) -> dict[str, Any]:
    """Combine offer- and recipe-side delta signals into one cache impact plan."""
    offer_rematch_recipe_ids = set(offer_planner_summary.get("rematch_recipe_ids", ()))
    offer_rescore_recipe_ids = set(offer_planner_summary.get("effective_rescore_recipe_ids", ()))
    offer_display_recipe_ids = set(offer_planner_summary.get("effective_display_only_recipe_ids", ()))

    recipe_semantic_rematch_recipe_ids = set(recipe_change_summary.get("semantic_rematch_recipe_ids", ()))
    recipe_forced_version_recipe_ids = set(recipe_change_summary.get("forced_version_rematch_recipe_ids", ()))
    recipe_rematch_recipe_ids = set(recipe_change_summary.get("rematch_recipe_ids", ()))
    recipe_remove_recipe_ids = set(recipe_change_summary.get("remove_recipe_ids", ()))

    rematch_recipe_ids = _sorted(offer_rematch_recipe_ids | recipe_rematch_recipe_ids)
    remove_recipe_ids = _sorted(recipe_remove_recipe_ids)
    effective_rescore_recipe_ids = _sorted(
        offer_rescore_recipe_ids - set(rematch_recipe_ids) - set(remove_recipe_ids)
    )
    effective_display_recipe_ids = _sorted(
        offer_display_recipe_ids
        - set(rematch_recipe_ids)
        - set(remove_recipe_ids)
        - set(effective_rescore_recipe_ids)
    )
    all_impacted_recipe_ids = _sorted(
        set(rematch_recipe_ids)
        | set(remove_recipe_ids)
        | set(effective_rescore_recipe_ids)
        | set(effective_display_recipe_ids)
    )

    return {
        "offer_rematch_recipe_ids": _sorted(offer_rematch_recipe_ids),
        "recipe_semantic_rematch_recipe_ids": _sorted(recipe_semantic_rematch_recipe_ids),
        "recipe_forced_version_rematch_recipe_ids": _sorted(recipe_forced_version_recipe_ids),
        "recipe_rematch_recipe_ids": _sorted(recipe_rematch_recipe_ids),
        "remove_recipe_ids": remove_recipe_ids,
        "rematch_recipe_ids": rematch_recipe_ids,
        "effective_rescore_recipe_ids": effective_rescore_recipe_ids,
        "effective_display_only_recipe_ids": effective_display_recipe_ids,
        "all_impacted_recipe_ids": all_impacted_recipe_ids,
        "counts": {
            "offer_rematch_recipes": len(offer_rematch_recipe_ids),
            "recipe_semantic_rematch_recipes": len(recipe_semantic_rematch_recipe_ids),
            "recipe_forced_version_rematch_recipes": len(recipe_forced_version_recipe_ids),
            "recipe_rematch_recipes": len(recipe_rematch_recipe_ids),
            "remove_recipes": len(remove_recipe_ids),
            "rematch_recipes": len(rematch_recipe_ids),
            "effective_rescore_recipes": len(effective_rescore_recipe_ids),
            "effective_display_only_recipes": len(effective_display_recipe_ids),
            "all_impacted_recipes": len(all_impacted_recipe_ids),
        },
    }
