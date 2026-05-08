"""Verified delta-apply helpers for runtime cache refreshes."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import threading
import time
from typing import Any

from loguru import logger
from sqlalchemy import text

try:
    from database import get_db_session
except ModuleNotFoundError:
    from app.database import get_db_session

try:
    from config import settings
except ModuleNotFoundError:
    from app.config import settings

try:
    from delta_probation_runtime import get_delta_probation_gate_status
except ModuleNotFoundError:
    from app.delta_probation_runtime import get_delta_probation_gate_status

try:
    from ingredient_routing_runtime import get_configured_ingredient_routing_mode
except ModuleNotFoundError:
    from app.ingredient_routing_runtime import get_configured_ingredient_routing_mode

try:
    from cache_operation_metadata import record_cache_last_operation
except ModuleNotFoundError:
    from app.cache_operation_metadata import record_cache_last_operation

try:
    from offer_cache_refresh_decision import set_compiled_offer_baseline_committed
except ModuleNotFoundError:
    from app.offer_cache_refresh_decision import set_compiled_offer_baseline_committed

try:
    from models import FoundRecipe, Offer
except ModuleNotFoundError:
    from app.models import FoundRecipe, Offer

try:
    from languages.matcher_runtime import (
        MATCHER_VERSION,
        OFFER_COMPILER_VERSION,
        RECIPE_COMPILER_VERSION,
        build_offer_candidate_terms,
        build_offer_identity_key,
        build_recipe_search_text_map,
        classify_current_offer_changes,
        classify_current_recipe_changes,
        load_compiled_offer_match_map,
        load_compiled_offer_term_manifest,
        load_compiled_recipe_payload_cache,
        load_compiled_offer_term_postings,
        load_compiled_recipe_term_postings,
        load_persisted_offer_recipe_map,
        plan_combined_delta_recipe_impacts,
        plan_offer_delta_recipe_impacts,
        precompute_offer_data,
        refresh_compiled_offer_match_data,
        refresh_compiled_offer_term_index,
        refresh_compiled_recipe_match_data,
        refresh_compiled_recipe_match_data_for_recipe_ids,
        refresh_compiled_recipe_offer_candidates,
        refresh_compiled_recipe_term_index,
        refresh_compiled_recipe_term_index_for_recipe_ids,
    )
except ModuleNotFoundError:
    from app.languages.matcher_runtime import (
        MATCHER_VERSION,
        OFFER_COMPILER_VERSION,
        RECIPE_COMPILER_VERSION,
        build_offer_candidate_terms,
        build_offer_identity_key,
        build_recipe_search_text_map,
        classify_current_offer_changes,
        classify_current_recipe_changes,
        load_compiled_offer_match_map,
        load_compiled_offer_term_manifest,
        load_compiled_recipe_payload_cache,
        load_compiled_offer_term_postings,
        load_compiled_recipe_term_postings,
        load_persisted_offer_recipe_map,
        plan_combined_delta_recipe_impacts,
        plan_offer_delta_recipe_impacts,
        precompute_offer_data,
        refresh_compiled_offer_match_data,
        refresh_compiled_offer_term_index,
        refresh_compiled_recipe_match_data,
        refresh_compiled_recipe_match_data_for_recipe_ids,
        refresh_compiled_recipe_offer_candidates,
        refresh_compiled_recipe_term_index,
        refresh_compiled_recipe_term_index_for_recipe_ids,
    )

try:
    from pantry_search_index import (
        refresh_compiled_recipe_search_term_index,
        refresh_compiled_recipe_search_term_index_for_recipe_ids,
    )
except ModuleNotFoundError:
    from app.pantry_search_index import (
        refresh_compiled_recipe_search_term_index,
        refresh_compiled_recipe_search_term_index_for_recipe_ids,
    )


ACTIVE_CACHE_TABLE = "recipe_offer_cache"
_unmatched_offer_count_refresh_lock = threading.Lock()
_unmatched_offer_count_refresh_in_progress = False
PERSISTED_ENTRY_FIELDS = (
    "found_recipe_id",
    "recipe_category",
    "budget_score",
    "total_savings",
    "coverage_pct",
    "num_matches",
    "is_starred",
    "match_data",
)


def _delta_verification_max_workers() -> int:
    configured_max_workers = max(1, settings.cache_delta_verification_max_workers)
    detected_core_workers = max(1, (os.cpu_count() or 1) - 1)
    return min(configured_max_workers, 3, detected_core_workers)


VERSION_FIELDS = (
    "matcher_version",
    "recipe_compiler_version",
    "offer_compiler_version",
)
INGREDIENT_ROUTING_RESULT_FIELDS = (
    "ingredient_routing_mode",
    "ingredient_routing_effective_mode",
    "ingredient_routing_fallback_reason",
    "estimated_fullscan_ingredient_checks",
    "estimated_hinted_ingredient_checks",
    "estimated_ingredient_check_reduction_pct",
    "ingredient_check_count",
    "hinted_check_count",
    "hinted_no_match_count",
    "fullscan_fallback_count",
    "fullscan_fallback_reason_counts",
    "actual_ingredient_check_reduction_pct",
    "time_ms",
    "cached",
    "total_recipes",
)


def _normalize_alternative_string(value: str) -> str:
    parts = [part.strip() for part in value.split(" / ") if part.strip()]
    if len(parts) <= 1:
        return value
    return " / ".join(sorted(parts))


def _normalize_number(value: Any) -> str:
    decimal = Decimal(str(value))
    normalized = decimal.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _normalize_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            return value
        return _normalize_value(parsed)
    if isinstance(value, (int, float, Decimal)):
        return _normalize_number(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        normalized_dict = {}
        has_stable_offer_identity = isinstance(value.get("offer_identity_key"), str)
        for key in sorted(value):
            # Offer row UUIDs are ephemeral across scrape refreshes.
            # When a stable identity key exists, parity should ignore the row id.
            if has_stable_offer_identity and key == "id":
                continue
            item = value[key]
            if key == "matched_keyword" and isinstance(item, str):
                normalized_dict[key] = _normalize_alternative_string(item)
            else:
                normalized_dict[key] = _normalize_value(item)
        return normalized_dict
    if isinstance(value, list):
        normalized = [_normalize_value(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
    return value


def _canonicalize_cache_entry(
    entry: dict[str, Any],
    *,
    include_version_fields: bool = False,
) -> dict[str, Any]:
    canonical = {}
    for field in PERSISTED_ENTRY_FIELDS:
        if field not in entry:
            continue
        canonical[field] = _normalize_value(entry[field])
    if not include_version_fields and isinstance(canonical.get("match_data"), dict):
        canonical["match_data"] = {
            key: value
            for key, value in canonical["match_data"].items()
            if key not in VERSION_FIELDS
        }
    if "found_recipe_id" in canonical:
        canonical["found_recipe_id"] = str(canonical["found_recipe_id"])
    return canonical


def _snapshot_from_entries(
    entries: list[dict[str, Any]],
    *,
    include_version_fields: bool = False,
) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for raw_entry in entries:
        entry = _canonicalize_cache_entry(raw_entry, include_version_fields=include_version_fields)
        recipe_id = entry.get("found_recipe_id")
        if not recipe_id:
            raise ValueError(f"Cache entry missing found_recipe_id: {raw_entry}")
        snapshot[str(recipe_id)] = entry
    return snapshot


def _fingerprint_snapshot_from_entries(
    entries: list[dict[str, Any]],
    *,
    include_version_fields: bool = False,
) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for raw_entry in entries:
        entry = _canonicalize_cache_entry(raw_entry, include_version_fields=include_version_fields)
        recipe_id = entry.get("found_recipe_id")
        if not recipe_id:
            raise ValueError(f"Cache entry missing found_recipe_id: {raw_entry}")
        snapshot[str(recipe_id)] = _stable_json_hash(entry)
    return snapshot


def _compare_snapshots(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    sample_limit: int = 10,
) -> dict[str, Any]:
    baseline_ids = set(baseline)
    candidate_ids = set(candidate)

    baseline_only = sorted(baseline_ids - candidate_ids)
    candidate_only = sorted(candidate_ids - baseline_ids)

    mismatched = []
    for recipe_id in sorted(baseline_ids & candidate_ids):
        if baseline[recipe_id] != candidate[recipe_id]:
            mismatched.append(recipe_id)

    return {
        "parity_ok": not baseline_only and not candidate_only and not mismatched,
        "baseline_only": baseline_only,
        "candidate_only": candidate_only,
        "mismatched": mismatched,
        "mismatched_count": len(baseline_only) + len(candidate_only) + len(mismatched),
        "mismatched_sample": (
            baseline_only[:sample_limit]
            + candidate_only[:sample_limit]
            + mismatched[:sample_limit]
        )[:sample_limit],
    }


def _ingredient_routing_summary_from_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        key: result.get(key)
        for key in INGREDIENT_ROUTING_RESULT_FIELDS
        if key in result
    }


def _raw_entry_map_from_entries(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    entry_map: dict[str, dict[str, Any]] = {}
    for raw_entry in entries:
        recipe_id = raw_entry.get("found_recipe_id")
        if not recipe_id:
            raise ValueError(f"Cache entry missing found_recipe_id: {raw_entry}")
        entry_map[str(recipe_id)] = dict(raw_entry)
    return entry_map


def _raw_entries_from_table(table_name: str = ACTIVE_CACHE_TABLE) -> list[dict[str, Any]]:
    with get_db_session() as db:
        rows = db.execute(text("""
            SELECT
                found_recipe_id::text AS found_recipe_id,
                recipe_category,
                budget_score,
                total_savings,
                coverage_pct,
                num_matches,
                is_starred,
                match_data
            FROM __TABLE_NAME__
            ORDER BY found_recipe_id
        """.replace("__TABLE_NAME__", table_name))).fetchall()
    return [dict(row._mapping) for row in rows]


def _compute_actual_changed_recipe_ids(
    baseline_snapshot: dict[str, Any],
    candidate_snapshot: dict[str, Any],
) -> list[str]:
    return sorted(
        (set(baseline_snapshot) - set(candidate_snapshot))
        | (set(candidate_snapshot) - set(baseline_snapshot))
        | {
            recipe_id
            for recipe_id in (set(baseline_snapshot) & set(candidate_snapshot))
            if baseline_snapshot[recipe_id] != candidate_snapshot[recipe_id]
        }
    )


def _stable_json_hash(payload: Any) -> str:
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _plan_delta_patch_recipe_ids(combined_planner: dict[str, Any]) -> list[str]:
    return sorted(
        set(combined_planner.get("rematch_recipe_ids", ()))
        | set(combined_planner.get("effective_rescore_recipe_ids", ()))
        | set(combined_planner.get("effective_display_only_recipe_ids", ()))
    )


def _materialize_delta_entries(
    baseline_entries: dict[str, dict[str, Any]],
    patch_entries: dict[str, dict[str, Any]],
    *,
    patch_recipe_ids: list[str] | set[str],
    remove_recipe_ids: list[str] | set[str],
) -> dict[str, dict[str, Any]]:
    materialized = {str(recipe_id): dict(entry) for recipe_id, entry in baseline_entries.items()}
    for recipe_id in set(str(value) for value in patch_recipe_ids) | set(str(value) for value in remove_recipe_ids):
        materialized.pop(recipe_id, None)
    materialized.update({
        str(recipe_id): dict(entry)
        for recipe_id, entry in patch_entries.items()
    })
    return materialized


def patch_recipe_offer_cache_entries(
    patch_entries: list[dict[str, Any]],
    changed_recipe_ids: list[str],
    removed_recipe_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Patch active recipe cache rows for selected recipe IDs."""
    normalized_removed_ids = set(_dedupe_recipe_delta_ids(removed_recipe_ids))
    normalized_changed_ids = [
        recipe_id
        for recipe_id in _dedupe_recipe_delta_ids(changed_recipe_ids)
        if recipe_id not in normalized_removed_ids
    ]
    touched_recipe_ids = _dedupe_recipe_delta_ids(normalized_changed_ids, list(normalized_removed_ids))
    patch_entry_map = _raw_entry_map_from_entries(patch_entries)
    unexpected_patch_ids = set(patch_entry_map) - set(normalized_changed_ids)
    if unexpected_patch_ids:
        raise ValueError(
            "Recipe cache patch contains entries outside changed_recipe_ids: "
            f"{sorted(unexpected_patch_ids)[:10]}"
        )

    with get_db_session() as db:
        deleted_count = 0
        if touched_recipe_ids:
            delete_result = db.execute(
                text("""
                    DELETE FROM recipe_offer_cache
                    WHERE found_recipe_id = ANY(CAST(:recipe_ids AS uuid[]))
                """),
                {"recipe_ids": touched_recipe_ids},
            )
            deleted_count = delete_result.rowcount or 0

        insert_sql = text("""
            INSERT INTO recipe_offer_cache (
                found_recipe_id,
                recipe_category,
                budget_score,
                total_savings,
                coverage_pct,
                num_matches,
                is_starred,
                match_data,
                computed_at
            ) VALUES (
                CAST(:found_recipe_id AS uuid),
                :recipe_category,
                :budget_score,
                :total_savings,
                :coverage_pct,
                :num_matches,
                :is_starred,
                CAST(:match_data AS jsonb),
                NOW()
            )
        """)
        for entry in patch_entry_map.values():
            db.execute(insert_sql, {
                "found_recipe_id": entry["found_recipe_id"],
                "recipe_category": entry["recipe_category"],
                "budget_score": entry["budget_score"],
                "total_savings": entry["total_savings"],
                "coverage_pct": entry["coverage_pct"],
                "num_matches": entry["num_matches"],
                "is_starred": entry["is_starred"],
                "match_data": json.dumps(entry["match_data"]),
            })

        total_matches = db.execute(text("SELECT COUNT(*) FROM recipe_offer_cache")).scalar() or 0
        db.commit()

    return {
        "deleted_recipe_ids": touched_recipe_ids,
        "deleted_count": deleted_count,
        "inserted_recipe_ids": sorted(patch_entry_map),
        "inserted_count": len(patch_entry_map),
        "total_matches": total_matches,
    }


def _build_current_offer_term_postings(offers: list[Offer]) -> dict[str, set[str]]:
    postings: dict[str, set[str]] = defaultdict(set)
    for offer in offers:
        compiled_offer_data = precompute_offer_data(
            offer.name,
            offer.category or "",
            brand=offer.brand or "",
            weight_grams=float(offer.weight_grams) if offer.weight_grams is not None else None,
        )
        offer_identity_key = build_offer_identity_key(offer)
        for term, _term_type in build_offer_candidate_terms(compiled_offer_data):
            postings[term].add(offer_identity_key)
    return dict(postings)


def _build_persisted_offer_term_postings_fallback() -> tuple[dict[str, set[str]], dict[str, Any]]:
    persisted_offer_rows = load_compiled_offer_match_map()
    postings: dict[str, set[str]] = defaultdict(set)
    term_pairs: set[tuple[str, str]] = set()

    for offer_identity_key, row in persisted_offer_rows.items():
        compiled_offer_data = row.get("compiled_data") or {}
        for term, term_type in build_offer_candidate_terms(compiled_offer_data):
            postings[term].add(str(offer_identity_key))
            term_pairs.add((term, term_type))

    manifest_payload = [
        {"term": term, "term_type": term_type}
        for term, term_type in sorted(term_pairs)
    ]
    return dict(postings), {
        "matcher_version": MATCHER_VERSION,
        "offer_compiler_version": OFFER_COMPILER_VERSION,
        "loaded_rows": sum(len(values) for values in postings.values()),
        "distinct_terms": len(postings),
        "offer_count": len(persisted_offer_rows),
        "term_manifest_hash": (
            f"ephemeral-{_stable_json_hash(manifest_payload)}" if manifest_payload else None
        ),
        "source": "compiled_offer_match_data_fallback",
    }


def _build_recipe_term_postings_fallback(
    recipes: list[FoundRecipe],
    *,
    candidate_terms: set[str],
) -> tuple[dict[str, set[str]], dict[str, Any]]:
    payload_cache, payload_stats = load_compiled_recipe_payload_cache(recipes, strict=False)
    missing = payload_stats.get("missing_recipe_ids", ())
    stale = payload_stats.get("stale_recipe_ids", ())
    inactive = payload_stats.get("inactive_recipe_ids", ())
    if missing or stale or inactive:
        raise RuntimeError(
            "compiled_recipe_match_data is missing, stale, or inactive for recipe term fallback: "
            f"missing={len(missing)}, stale={len(stale)}, inactive={len(inactive)}"
        )

    search_texts = build_recipe_search_text_map(
        recipes,
        compiled_recipe_payload_cache=payload_cache,
    )
    postings: dict[str, set[str]] = defaultdict(set)
    for recipe_id, search_text in search_texts.items():
        for term in candidate_terms:
            if term in search_text:
                postings[term].add(str(recipe_id))

    return dict(postings), {
        "matcher_version": MATCHER_VERSION,
        "recipe_compiler_version": RECIPE_COMPILER_VERSION,
        "loaded_rows": sum(len(values) for values in postings.values()),
        "distinct_terms": len(postings),
        "recipe_count": len(search_texts),
        "term_manifest_hash": (
            f"ephemeral-{_stable_json_hash(sorted(candidate_terms))}" if candidate_terms else None
        ),
        "key_field": "found_recipe_id",
        "source": "compiled_recipe_payload_fallback",
    }


def _load_or_build_delta_term_postings(
    *,
    recipes: list[FoundRecipe],
    current_offer_term_postings: dict[str, set[str]],
) -> tuple[
    dict[str, set[str]],
    dict[str, Any],
    dict[str, set[str]],
    dict[str, Any],
    dict[str, set[str]],
    dict[str, Any],
]:
    offer_term_postings, offer_term_stats = load_compiled_offer_term_postings()
    if not offer_term_stats.get("term_manifest_hash"):
        offer_term_postings, offer_term_stats = _build_persisted_offer_term_postings_fallback()

    current_terms = set(current_offer_term_postings)
    persisted_terms = set(offer_term_postings)
    candidate_terms = current_terms | persisted_terms

    persisted_recipe_term_postings, persisted_recipe_term_stats = load_compiled_recipe_term_postings(
        term_manifest_hash=offer_term_stats["term_manifest_hash"],
    )
    if not persisted_recipe_term_stats.get("term_manifest_hash"):
        persisted_recipe_term_postings, persisted_recipe_term_stats = _build_recipe_term_postings_fallback(
            recipes,
            candidate_terms=persisted_terms or candidate_terms,
        )

    if current_terms.issubset(persisted_terms):
        current_recipe_term_postings = persisted_recipe_term_postings
        current_recipe_term_stats = dict(persisted_recipe_term_stats)
        current_recipe_term_stats["source"] = current_recipe_term_stats.get("source", "compiled_recipe_term_index")
    else:
        current_recipe_term_postings, current_recipe_term_stats = _build_recipe_term_postings_fallback(
            recipes,
            candidate_terms=candidate_terms,
        )

    return (
        offer_term_postings,
        offer_term_stats,
        current_recipe_term_postings,
        current_recipe_term_stats,
        persisted_recipe_term_postings,
        persisted_recipe_term_stats,
    )


def _update_cache_metadata(*, total_matches: int, time_ms: int, total_recipes: int | None = None) -> None:
    with get_db_session() as db:
        existing_total_recipes = db.execute(text("""
            SELECT total_recipes
            FROM cache_metadata
            WHERE cache_name = 'recipe_offer_matches'
        """)).scalar()
        db.execute(text("""
            INSERT INTO cache_metadata (
                cache_name, last_computed_at, computation_time_ms,
                total_recipes, total_matches, status, error_message
            )
            VALUES (
                :name, NOW(), :time_ms, :total_recipes, :total_matches, 'ready', NULL
            )
            ON CONFLICT (cache_name) DO UPDATE SET
                last_computed_at = NOW(),
                computation_time_ms = :time_ms,
                total_recipes = :total_recipes,
                total_matches = :total_matches,
                status = 'ready',
                error_message = NULL
        """), {
            "name": "recipe_offer_matches",
            "time_ms": time_ms,
            "total_recipes": total_recipes if total_recipes is not None else existing_total_recipes,
            "total_matches": total_matches,
        })
        db.commit()


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


def _active_recipe_count_from_db() -> int:
    with get_db_session() as db:
        return db.execute(text("""
            SELECT COUNT(*)
            FROM found_recipes
            WHERE excluded = FALSE OR excluded IS NULL
        """)).scalar() or 0


def _active_cache_state() -> dict[str, Any]:
    with get_db_session() as db:
        metadata = db.execute(text("""
            SELECT status, total_matches, total_recipes
            FROM cache_metadata
            WHERE cache_name = 'recipe_offer_matches'
        """)).mappings().fetchone()
        cache_rows = db.execute(text("SELECT COUNT(*) FROM recipe_offer_cache")).scalar() or 0
        offer_rows = db.execute(text("SELECT COUNT(*) FROM offers")).scalar() or 0
    return {
        "status": metadata["status"] if metadata else None,
        "metadata_total_matches": metadata["total_matches"] if metadata else None,
        "metadata_total_recipes": metadata["total_recipes"] if metadata else None,
        "cache_rows": cache_rows,
        "offer_rows": offer_rows,
    }


def _ensure_compiled_offer_term_index_ready() -> dict[str, Any]:
    """Refresh offer term index when matcher/offer versions moved."""
    try:
        _term_pairs, stats = load_compiled_offer_term_manifest()
        if stats.get("loaded_rows") and stats.get("term_manifest_hash"):
            return {"skipped": True, **stats}
    except Exception as exc:
        logger.warning(f"Could not inspect compiled offer term index; refreshing: {exc}")

    compiled_offer_refresh = None
    try:
        offer_term_refresh = refresh_compiled_offer_term_index()
    except RuntimeError as exc:
        if "compiled_offer_match_data is missing or stale" not in str(exc):
            raise
        compiled_offer_refresh = refresh_compiled_offer_match_data()
        offer_term_refresh = refresh_compiled_offer_term_index()

    return {
        "skipped": False,
        "compiled_offer_refresh": compiled_offer_refresh,
        "offer_term_refresh": offer_term_refresh,
    }


def _recipe_delta_total_recipes(
    full_preview: dict[str, Any] | None,
    cache_state: dict[str, Any],
    *,
    active_recipe_count: int | None = None,
) -> int:
    if full_preview is not None and full_preview.get("total_recipes") is not None:
        return int(full_preview["total_recipes"])
    if active_recipe_count is not None:
        return int(active_recipe_count)
    if cache_state.get("metadata_total_recipes") is not None:
        return int(cache_state["metadata_total_recipes"])
    return _active_recipe_count_from_db()


def _refresh_unmatched_offer_count_from_db(cache_manager) -> dict[str, int]:
    with get_db_session() as db:
        total_offers = db.execute(text("SELECT COUNT(*) FROM offers")).scalar() or 0
        matched_offer_count = db.execute(text("""
            SELECT COUNT(DISTINCT offer_key)
            FROM recipe_offer_cache c,
                 jsonb_array_elements_text(
                     jsonb_path_query_array(c.match_data, '$.matched_offers[*].offer_identity_key')
                 ) AS offer_key
        """)).scalar() or 0
    cache_manager._total_offers = total_offers
    cache_manager._unmatched_count = max(0, total_offers - matched_offer_count)
    return {
        "total_offers": total_offers,
        "matched_offer_ids": matched_offer_count,
        "unmatched_offer_ids": cache_manager._unmatched_count,
    }


def _cached_unmatched_offer_counts(cache_manager) -> dict[str, Any]:
    with get_db_session() as db:
        total_offers = db.execute(text("SELECT COUNT(*) FROM offers")).scalar() or 0

    unmatched_count = cache_manager._unmatched_count
    matched_offer_count = None
    if unmatched_count is not None:
        matched_offer_count = max(0, total_offers - int(unmatched_count))

    return {
        "total_offers": total_offers,
        "matched_offer_ids": matched_offer_count,
        "unmatched_offer_ids": unmatched_count,
        "refresh_mode": "cached",
    }


def _schedule_unmatched_offer_count_refresh(cache_manager) -> dict[str, Any]:
    global _unmatched_offer_count_refresh_in_progress

    with _unmatched_offer_count_refresh_lock:
        if _unmatched_offer_count_refresh_in_progress:
            return {
                "refresh_scheduled": False,
                "refresh_skip_reason": "already_running",
            }
        _unmatched_offer_count_refresh_in_progress = True

    def _worker() -> None:
        global _unmatched_offer_count_refresh_in_progress
        try:
            result = _refresh_unmatched_offer_count_from_db(cache_manager)
            logger.info(
                "Delta unmatched-offer count refreshed in background: "
                f"matched={result['matched_offer_ids']} total={result['total_offers']}"
            )
        except Exception as exc:
            logger.warning(f"Delta unmatched-offer background refresh failed: {exc}")
        finally:
            with _unmatched_offer_count_refresh_lock:
                _unmatched_offer_count_refresh_in_progress = False

    threading.Thread(
        target=_worker,
        name="recipe-delta-unmatched-offer-refresh",
        daemon=True,
    ).start()
    return {
        "refresh_scheduled": True,
        "refresh_mode": "background",
    }


def _dedupe_recipe_delta_ids(*id_lists: list[str] | None) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for id_list in id_lists:
        for value in id_list or []:
            if value is None:
                continue
            str_value = str(value)
            if str_value in seen:
                continue
            ids.append(str_value)
            seen.add(str_value)
    return ids


def _recipe_delta_probation_history_path() -> Path | None:
    configured = settings.cache_recipe_delta_probation_history_file
    if configured:
        return Path(configured)
    if Path("/app").exists():
        return Path("/app/data/recipe_delta_probation_history.jsonl")
    return Path(__file__).resolve().parents[1] / "data" / "recipe_delta_probation_history.jsonl"


def _resolve_recipe_delta_verification_policy(*, verify_full_preview: bool) -> dict[str, Any]:
    history_path = _recipe_delta_probation_history_path()
    probation_status = get_delta_probation_gate_status(
        history_path=history_path,
        min_ready_streak=settings.cache_recipe_delta_probation_min_ready_streak,
        min_version_ready_runs=settings.cache_recipe_delta_probation_min_version_ready_runs,
    )
    effective_verify_full_preview = verify_full_preview
    verification_mode = "disabled"
    if verify_full_preview:
        verification_mode = "full_preview"
        if settings.cache_recipe_delta_skip_full_preview_after_probation:
            verification_mode = "full_preview_pending_probation"
            if probation_status["ready"]:
                effective_verify_full_preview = False
                verification_mode = "probation_skip"
    return {
        "requested_verify_full_preview": verify_full_preview,
        "effective_verify_full_preview": effective_verify_full_preview,
        "verification_mode": verification_mode,
        "probation_status": probation_status,
        "probation_history_path": history_path,
        "skip_full_preview_max_affected_ratio": (
            settings.cache_recipe_delta_skip_full_preview_max_affected_ratio
        ),
    }


def _enforce_recipe_delta_preview_size_gate(
    verification_policy: dict[str, Any],
    *,
    affected_recipe_count: int,
    active_recipe_count: int | None,
) -> dict[str, Any]:
    """Keep full-preview for larger recipe-deltas even after probation is green."""
    result = dict(verification_policy)
    max_ratio = float(settings.cache_recipe_delta_skip_full_preview_max_affected_ratio)
    result["skip_full_preview_affected_recipe_count"] = affected_recipe_count
    result["skip_full_preview_active_recipe_count"] = active_recipe_count
    result["skip_full_preview_affected_ratio"] = None

    if not result.get("requested_verify_full_preview"):
        return result
    if result.get("verification_mode") != "probation_skip":
        return result
    if max_ratio <= 0:
        return result
    if not active_recipe_count or active_recipe_count <= 0:
        result["effective_verify_full_preview"] = True
        result["verification_mode"] = "full_preview_required_for_unknown_recipe_delta_size"
        return result

    affected_ratio = affected_recipe_count / active_recipe_count
    result["skip_full_preview_affected_ratio"] = affected_ratio
    if affected_ratio > max_ratio:
        result["effective_verify_full_preview"] = True
        result["verification_mode"] = "full_preview_required_for_large_recipe_delta"
    return result


def _summary_ms(value: Any) -> str:
    if value is None:
        return "skipped"
    try:
        return f"{int(value)}ms"
    except (TypeError, ValueError):
        return "n/a"


def _recipe_delta_count(summary: dict[str, Any], count_key: str, ids_key: str) -> int:
    value = summary.get(count_key)
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    ids = summary.get(ids_key)
    return len(ids) if isinstance(ids, list) else 0


def _format_recipe_delta_summary_line(summary: dict[str, Any]) -> str:
    patch_result = summary.get("patch_result") or {}
    fallback_reason = summary.get("fallback_reason")
    if summary.get("applied"):
        outcome = "applied"
    elif fallback_reason:
        outcome = "fallback"
    elif summary.get("success"):
        outcome = "preview"
    else:
        outcome = "not_applied"

    inserted_count = patch_result.get("inserted_count")
    if inserted_count is None:
        inserted_count = summary.get("patch_preview_match_count")

    deleted_count = patch_result.get("deleted_count")
    total_matches = patch_result.get("total_matches")
    if total_matches is None:
        total_matches = summary.get("cached")

    fallback_part = f" fallback={fallback_reason}" if fallback_reason else ""
    source_part = f" source={summary.get('source')}" if summary.get("source") else ""

    return (
        "CACHE_RECIPE_DELTA "
        f"{outcome}: "
        f"changed={_recipe_delta_count(summary, 'changed_recipe_count', 'changed_recipe_ids')} "
        f"removed={_recipe_delta_count(summary, 'removed_recipe_count', 'removed_recipe_ids')} "
        f"inserted={inserted_count if inserted_count is not None else 'n/a'} "
        f"deleted={deleted_count if deleted_count is not None else 'n/a'} "
        f"cache_rows={total_matches if total_matches is not None else 'n/a'} "
        f"preview={_summary_ms(summary.get('patch_preview_time_ms'))} "
        f"full_preview={_summary_ms(summary.get('full_preview_time_ms'))} "
        f"total={_summary_ms(summary.get('time_ms'))} "
        f"verification={summary.get('verification_mode', 'n/a')}"
        f"{fallback_part}"
        f"{source_part}"
    )


def _emit_recipe_delta_summary(summary: dict[str, Any], *, level: str = "info") -> None:
    log_fn = logger.error if level == "error" else logger.warning if level == "warning" else logger.info
    log_fn(_format_recipe_delta_summary_line(summary))
    patch_result = summary.get("patch_result") or {}
    candidate_refresh = summary.get("recipe_offer_candidate_refresh") or {}
    compact_summary = {
        "success": summary.get("success"),
        "applied": summary.get("applied"),
        "source": summary.get("source"),
        "mode": summary.get("effective_rebuild_mode"),
        "verification": summary.get("verification_mode"),
        "changed": _recipe_delta_count(summary, "changed_recipe_count", "changed_recipe_ids"),
        "removed": _recipe_delta_count(summary, "removed_recipe_count", "removed_recipe_ids"),
        "affected": summary.get("affected_recipe_count"),
        "affected_pct": summary.get("affected_ratio_pct"),
        "inserted": patch_result.get("inserted_count"),
        "deleted": patch_result.get("deleted_count"),
        "cache_rows": patch_result.get("total_matches", summary.get("cached")),
        "candidate_rows": candidate_refresh.get("candidate_rows"),
        "candidate_source": summary.get("candidate_data_source"),
        "preview_ms": summary.get("patch_preview_time_ms"),
        "full_preview_ms": summary.get("full_preview_time_ms"),
        "total_ms": summary.get("time_ms"),
        "fallback": summary.get("fallback_reason"),
    }
    payload = json.dumps(
        compact_summary,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    log_fn(f"CACHE_RECIPE_DELTA_SUMMARY {payload}")
    debug_payload = json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    logger.debug(f"CACHE_RECIPE_DELTA_DEBUG {debug_payload}")


def _set_runtime_rebuild_profile(cache_manager) -> None:
    configured = cache_manager.get_rebuild_profile()
    cache_manager._last_rebuild_profile = {
        "configured_rebuild_mode": configured["mode"],
        "effective_rebuild_mode": "delta",
        "offer_data_source": "compiled",
        "recipe_data_source": "compiled_payload",
        "candidate_data_source": "term_index",
    }


def _recipe_delta_fallback_result(
    *,
    changed_recipe_ids: list[str],
    removed_recipe_ids: list[str],
    source: str | None,
    fallback_reason: str,
    started_at: float,
    error: Exception | str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    result = {
        "success": False,
        "applied": False,
        "ready_to_apply": False,
        "fallback_reason": fallback_reason,
        "error": str(error) if error is not None else None,
        "source": source,
        "changed_recipe_count": len(changed_recipe_ids),
        "removed_recipe_count": len(removed_recipe_ids),
        "patch_recipe_count": len(changed_recipe_ids),
        "actual_changed_recipes": None,
        "planner_covers_preview_diff": None,
        "materialized_patch_matches_full_preview": None,
        "cached": None,
        "total_recipes": None,
        "time_ms": elapsed_ms,
        "effective_rebuild_mode": "compiled",
        "matcher_version": MATCHER_VERSION,
        "recipe_compiler_version": RECIPE_COMPILER_VERSION,
        "offer_compiler_version": OFFER_COMPILER_VERSION,
    }
    if extra:
        result.update(extra)
    return result


def _apply_recipe_delta_unlocked(
    *,
    changed_recipe_ids: list[str],
    removed_recipe_ids: list[str] | None = None,
    source: str | None = None,
    apply: bool = True,
    verify_full_preview: bool = True,
    cache_status_snapshot: dict[str, Any] | None = None,
    operation_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply a recipe-driven delta patch to the active cache table."""
    try:
        from cache_manager import cache_manager
    except ModuleNotFoundError:
        from app.cache_manager import cache_manager

    started_at = time.perf_counter()
    removed_ids = _dedupe_recipe_delta_ids(removed_recipe_ids)
    removed_set = set(removed_ids)
    changed_ids = [
        recipe_id
        for recipe_id in _dedupe_recipe_delta_ids(changed_recipe_ids)
        if recipe_id not in removed_set
    ]
    status_was_set = False
    operation_context = dict(operation_context or {})

    verification_policy = _resolve_recipe_delta_verification_policy(
        verify_full_preview=verify_full_preview,
    )
    delta_verification_max_workers = _delta_verification_max_workers()

    def _fallback(
        reason: str,
        *,
        error: Exception | str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status_was_set:
            try:
                _set_cache_metadata_status("ready")
            except Exception as status_error:
                logger.warning(f"Could not restore cache metadata after recipe delta fallback: {status_error}")
        result = _recipe_delta_fallback_result(
            changed_recipe_ids=changed_ids,
            removed_recipe_ids=removed_ids,
            source=source,
            fallback_reason=reason,
            started_at=started_at,
            error=error,
            extra={
                "verify_full_preview": verification_policy["requested_verify_full_preview"],
                "effective_verify_full_preview": verification_policy["effective_verify_full_preview"],
                "verification_mode": verification_policy["verification_mode"],
                "skip_full_preview_max_affected_ratio": verification_policy.get(
                    "skip_full_preview_max_affected_ratio"
                ),
                "skip_full_preview_affected_recipe_count": verification_policy.get(
                    "skip_full_preview_affected_recipe_count"
                ),
                "skip_full_preview_active_recipe_count": verification_policy.get(
                    "skip_full_preview_active_recipe_count"
                ),
                "skip_full_preview_affected_ratio": verification_policy.get(
                    "skip_full_preview_affected_ratio"
                ),
                "delta_verification_max_workers": delta_verification_max_workers,
                "probation_ready": verification_policy["probation_status"]["ready"],
                "probation_history_file": verification_policy["probation_status"]["history_file"],
                "probation_reasons": verification_policy["probation_status"]["reasons"],
                "probation_summary": verification_policy["probation_status"]["summary"],
                **operation_context,
                **(extra or {}),
            },
        )
        if apply:
            record_cache_last_operation(
                result,
                operation_type="recipe_delta",
                status="fallback",
                source=source,
            )
        _emit_recipe_delta_summary(result, level="warning")
        return result

    cache_state = dict(cache_status_snapshot or _active_cache_state())
    if cache_state["status"] != "ready":
        return _fallback("cache_not_ready", extra={"cache_state": cache_state})
    if cache_state["cache_rows"] == 0 and cache_state["offer_rows"] > 0:
        return _fallback("active_cache_empty", extra={"cache_state": cache_state})
    active_recipe_count = operation_context.get("active_recipe_count")
    if active_recipe_count is None:
        active_recipe_count = cache_state.get("metadata_total_recipes")
    if active_recipe_count is None:
        active_recipe_count = _active_recipe_count_from_db()
    verification_policy = _enforce_recipe_delta_preview_size_gate(
        verification_policy,
        affected_recipe_count=len(changed_ids) + len(removed_ids),
        active_recipe_count=int(active_recipe_count or 0),
    )

    if apply:
        _set_cache_metadata_status("computing")
        status_was_set = True

    ir_stats = None
    offer_term_stats = None
    term_stats = None
    candidate_stats = None
    pantry_search_term_stats = None
    full_preview = None
    patch_preview = None
    full_preview_snapshot: dict[str, str] | None = None
    actual_changed_recipe_ids: list[str] = []
    materialized_diff = {
        "parity_ok": True,
        "mismatched_count": 0,
        "mismatched_sample": [],
    }

    try:
        baseline_entry_map: dict[str, dict[str, Any]] = {}
        baseline_snapshot: dict[str, str] = {}
        if verification_policy["effective_verify_full_preview"]:
            baseline_entries_list = _raw_entries_from_table(ACTIVE_CACHE_TABLE)
            baseline_entry_map = _raw_entry_map_from_entries(baseline_entries_list)
            baseline_snapshot = _fingerprint_snapshot_from_entries(baseline_entries_list)
            del baseline_entries_list

        try:
            ir_stats = refresh_compiled_recipe_match_data_for_recipe_ids(
                changed_ids,
                remove_recipe_ids=removed_ids,
            )
        except Exception as exc:
            return _fallback(
                "recipe_ir_refresh_failed",
                error=exc,
                extra={
                    "compiled_recipe_refresh": ir_stats,
                    "offer_term_refresh": offer_term_stats,
                    "recipe_term_refresh": term_stats,
                    "pantry_search_term_refresh": pantry_search_term_stats,
                },
            )
        try:
            offer_term_stats = _ensure_compiled_offer_term_index_ready()
        except Exception as exc:
            return _fallback(
                "offer_term_index_refresh_failed",
                error=exc,
                extra={
                    "compiled_recipe_refresh": ir_stats,
                    "offer_term_refresh": offer_term_stats,
                    "recipe_term_refresh": term_stats,
                    "pantry_search_term_refresh": pantry_search_term_stats,
                },
            )
        try:
            term_stats = refresh_compiled_recipe_term_index_for_recipe_ids(
                changed_ids,
                remove_recipe_ids=removed_ids,
            )
        except Exception as exc:
            return _fallback(
                "recipe_term_index_refresh_failed",
                error=exc,
                extra={
                    "compiled_recipe_refresh": ir_stats,
                    "offer_term_refresh": offer_term_stats,
                    "recipe_term_refresh": term_stats,
                    "pantry_search_term_refresh": pantry_search_term_stats,
                },
            )
        try:
            candidate_stats = refresh_compiled_recipe_offer_candidates(
                term_manifest_hash=term_stats.get("term_manifest_hash"),
                cleanup_stale=False,
                recipe_ids=_dedupe_recipe_delta_ids(changed_ids, removed_ids),
            )
        except Exception as exc:
            return _fallback(
                "recipe_offer_candidate_refresh_failed",
                error=exc,
                extra={
                    "compiled_recipe_refresh": ir_stats,
                    "offer_term_refresh": offer_term_stats,
                    "recipe_term_refresh": term_stats,
                    "recipe_offer_candidate_refresh": candidate_stats,
                    "pantry_search_term_refresh": pantry_search_term_stats,
                },
            )
        try:
            pantry_search_term_stats = refresh_compiled_recipe_search_term_index_for_recipe_ids(
                changed_ids,
                remove_recipe_ids=removed_ids,
            )
        except Exception as exc:
            pantry_search_term_stats = {
                "success": False,
                "error": str(exc),
            }
            logger.warning(
                "Pantry search-term index refresh failed during recipe delta; "
                "pantry will fall back to legacy until the index is refreshed: {}",
                exc,
            )

        if verification_policy["effective_verify_full_preview"]:
            try:
                full_preview = cache_manager.refresh_cache(
                    persist=False,
                    return_entries=True,
                    run_kind="recipe_delta_full_preview",
                    input_scope="live",
                    max_workers=delta_verification_max_workers,
                )
                full_preview_entries = full_preview.pop("entries")
                full_preview_snapshot = _fingerprint_snapshot_from_entries(full_preview_entries)
                del full_preview_entries
            except Exception as exc:
                return _fallback(
                    "recipe_delta_full_preview_failed",
                    error=exc,
                    extra={
                        "compiled_recipe_refresh": ir_stats,
                        "offer_term_refresh": offer_term_stats,
                        "recipe_term_refresh": term_stats,
                        "pantry_search_term_refresh": pantry_search_term_stats,
                    },
                )

        patch_entries: dict[str, dict[str, Any]]
        if changed_ids:
            try:
                patch_preview = cache_manager.refresh_cache(
                    persist=False,
                    return_entries=True,
                    recipe_ids=changed_ids,
                    run_kind="recipe_delta_patch_preview",
                    input_scope="live",
                    max_workers=delta_verification_max_workers,
                )
                patch_preview_entries = patch_preview.pop("entries")
                patch_entries = _raw_entry_map_from_entries(patch_preview_entries)
                del patch_preview_entries
            except Exception as exc:
                return _fallback(
                    "recipe_delta_patch_preview_failed",
                    error=exc,
                    extra={
                        "compiled_recipe_refresh": ir_stats,
                        "offer_term_refresh": offer_term_stats,
                        "recipe_term_refresh": term_stats,
                        "pantry_search_term_refresh": pantry_search_term_stats,
                        "full_preview_time_ms": full_preview["time_ms"] if full_preview else None,
                    },
                )
        else:
            patch_preview = {
                "time_ms": 0,
                "total_recipes": 0,
                "cached": 0,
                "requested_recipe_count": 0,
                "selected_recipe_count": 0,
                "recipe_selection_mode": "direct_subset",
            }
            patch_entries = {}

        scope_covers_preview_diff = True
        materialized_matches_full_preview = True
        if full_preview_snapshot is not None:
            materialized_entries = _materialize_delta_entries(
                baseline_entry_map,
                patch_entries,
                patch_recipe_ids=changed_ids,
                remove_recipe_ids=removed_ids,
            )
            materialized_snapshot = _fingerprint_snapshot_from_entries(
                list(materialized_entries.values())
            )
            del materialized_entries
            materialized_diff = _compare_snapshots(materialized_snapshot, full_preview_snapshot)
            actual_changed_recipe_ids = _compute_actual_changed_recipe_ids(
                baseline_snapshot,
                full_preview_snapshot,
            )
            scope_covers_preview_diff = set(actual_changed_recipe_ids).issubset(
                set(changed_ids) | set(removed_ids)
            )
            materialized_matches_full_preview = materialized_diff["parity_ok"]

        ready_to_apply = scope_covers_preview_diff and materialized_matches_full_preview
        fallback_reason = None
        if not scope_covers_preview_diff:
            fallback_reason = "recipe_delta_scope_missed_preview_diff"
        elif not materialized_matches_full_preview:
            fallback_reason = "materialized_patch_mismatch"

        patch_result = None
        unmatched_offer_counts = None
        applied = False
        if apply and ready_to_apply:
            try:
                patch_result = patch_recipe_offer_cache_entries(
                    list(patch_entries.values()),
                    changed_ids,
                    removed_recipe_ids=removed_ids,
                )
                unmatched_offer_counts = _cached_unmatched_offer_counts(cache_manager)
                unmatched_offer_counts.update(_schedule_unmatched_offer_count_refresh(cache_manager))
                _set_runtime_rebuild_profile(cache_manager)
                elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                _update_cache_metadata(
                    total_matches=patch_result["total_matches"],
                    total_recipes=_recipe_delta_total_recipes(
                        full_preview,
                        cache_state,
                        active_recipe_count=int(active_recipe_count or 0) or None,
                    ),
                    time_ms=elapsed_ms,
                )
                status_was_set = False
                applied = True
            except Exception as exc:
                return _fallback(
                    "recipe_cache_patch_failed",
                    error=exc,
                    extra={
                        "compiled_recipe_refresh": ir_stats,
                        "offer_term_refresh": offer_term_stats,
                        "recipe_term_refresh": term_stats,
                        "pantry_search_term_refresh": pantry_search_term_stats,
                        "full_preview_time_ms": full_preview["time_ms"] if full_preview else None,
                        "patch_preview_time_ms": patch_preview["time_ms"] if patch_preview else None,
                    },
                )
        elif apply:
            _set_cache_metadata_status("ready")
            status_was_set = False

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        result = {
            "success": ready_to_apply,
            "applied": applied,
            "ready_to_apply": ready_to_apply,
            "fallback_reason": fallback_reason,
            "source": source,
            "changed_recipe_count": len(changed_ids),
            "removed_recipe_count": len(removed_ids),
            "changed_recipe_ids": changed_ids,
            "removed_recipe_ids": removed_ids,
            "verify_full_preview": verification_policy["requested_verify_full_preview"],
            "effective_verify_full_preview": verification_policy["effective_verify_full_preview"],
            "verification_mode": verification_policy["verification_mode"],
            "skip_full_preview_max_affected_ratio": verification_policy.get(
                "skip_full_preview_max_affected_ratio"
            ),
            "skip_full_preview_affected_recipe_count": verification_policy.get(
                "skip_full_preview_affected_recipe_count"
            ),
            "skip_full_preview_active_recipe_count": verification_policy.get(
                "skip_full_preview_active_recipe_count"
            ),
            "skip_full_preview_affected_ratio": verification_policy.get(
                "skip_full_preview_affected_ratio"
            ),
            "delta_verification_max_workers": delta_verification_max_workers,
            "probation_ready": verification_policy["probation_status"]["ready"],
            "probation_history_file": verification_policy["probation_status"]["history_file"],
            "probation_reasons": verification_policy["probation_status"]["reasons"],
            "probation_summary": verification_policy["probation_status"]["summary"],
            "compiled_recipe_refresh": ir_stats,
            "offer_term_refresh": offer_term_stats,
            "recipe_term_refresh": term_stats,
            "recipe_offer_candidate_refresh": candidate_stats,
            "pantry_search_term_refresh": pantry_search_term_stats,
            "patch_result": patch_result,
            "unmatched_offer_counts": unmatched_offer_counts,
            "patch_recipe_count": len(changed_ids),
            "patch_preview_match_count": len(patch_entries),
            "actual_changed_recipes": len(actual_changed_recipe_ids),
            "actual_changed_recipe_ids_sample": actual_changed_recipe_ids[:10],
            "planner_covers_preview_diff": scope_covers_preview_diff,
            "materialized_patch_matches_full_preview": materialized_matches_full_preview,
            "materialized_mismatched_count": materialized_diff.get("mismatched_count", 0),
            "materialized_mismatched_sample": materialized_diff.get("mismatched_sample", []),
            "full_preview_time_ms": full_preview["time_ms"] if full_preview is not None else None,
            "patch_preview_time_ms": patch_preview["time_ms"] if patch_preview is not None else None,
            "full_preview_recipe_selection_mode": (
                full_preview.get("recipe_selection_mode") if full_preview is not None else None
            ),
            "patch_preview_recipe_selection_mode": (
                patch_preview.get("recipe_selection_mode") if patch_preview is not None else None
            ),
            "cached": (
                patch_result["total_matches"]
                if patch_result
                else cache_state["cache_rows"]
            ),
            "total_recipes": _recipe_delta_total_recipes(
                full_preview,
                cache_state,
                active_recipe_count=int(active_recipe_count or 0) or None,
            ),
            "time_ms": elapsed_ms,
            "effective_rebuild_mode": "delta" if applied else "compiled",
            "matcher_version": MATCHER_VERSION,
            "recipe_compiler_version": RECIPE_COMPILER_VERSION,
            "offer_compiler_version": OFFER_COMPILER_VERSION,
            "offer_data_source": "compiled",
            "recipe_data_source": "compiled_payload",
            "candidate_data_source": (
                patch_preview.get("candidate_data_source", "db_candidates")
                if patch_preview is not None
                else "db_candidates"
            ),
            **operation_context,
        }
        if apply:
            record_cache_last_operation(
                result,
                operation_type="recipe_delta",
                status="ready" if applied else "fallback",
                source=source,
            )
        _emit_recipe_delta_summary(result, level="info" if ready_to_apply else "warning")
        return result
    except Exception as exc:
        return _fallback(
            "recipe_delta_unexpected_error",
            error=exc,
            extra={
                "compiled_recipe_refresh": ir_stats,
                "offer_term_refresh": offer_term_stats,
                "recipe_term_refresh": term_stats,
                "recipe_offer_candidate_refresh": candidate_stats,
                "pantry_search_term_refresh": pantry_search_term_stats,
                "full_preview_time_ms": full_preview["time_ms"] if full_preview else None,
                "patch_preview_time_ms": patch_preview["time_ms"] if patch_preview else None,
            },
        )


def _resolve_delta_verification_policy(*, verify_full_preview: bool) -> dict[str, Any]:
    """Decide whether this delta run should pay the cost of a full preview."""
    probation_status = get_delta_probation_gate_status()
    ingredient_routing_mode = get_configured_ingredient_routing_mode()

    effective_verify_full_preview = verify_full_preview
    verification_mode = "disabled"
    if verify_full_preview:
        verification_mode = "full_preview"
        if settings.cache_delta_skip_full_preview_after_probation:
            verification_mode = "full_preview_pending_probation"
            if probation_status["ready"]:
                effective_verify_full_preview = False
                verification_mode = "probation_skip"

    return {
        "requested_verify_full_preview": verify_full_preview,
        "effective_verify_full_preview": effective_verify_full_preview,
        "verification_mode": verification_mode,
        "probation_status": probation_status,
        "ingredient_routing_mode": ingredient_routing_mode,
    }


def _apply_verified_offer_delta_unlocked(
    *,
    apply: bool = True,
    verify_full_preview: bool = True,
    operation_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply a verified offer-driven delta patch to the active cache table."""
    from cache_manager import cache_manager

    started_at = time.perf_counter()
    operation_context = dict(operation_context or {})

    verification_policy = _resolve_delta_verification_policy(
        verify_full_preview=verify_full_preview,
    )

    with get_db_session() as db:
        offers = db.query(Offer).order_by(Offer.id).all()
        active_recipe_filter = (
            (FoundRecipe.excluded == False) | (FoundRecipe.excluded.is_(None))  # noqa: E712
        )
        recipes = db.query(FoundRecipe).filter(active_recipe_filter).order_by(FoundRecipe.id).all()

    offer_changes = classify_current_offer_changes(offers)
    recipe_changes = classify_current_recipe_changes(recipes)
    if recipe_changes.get("all_impacted_recipe_ids"):
        result = {
            "success": False,
            "applied": False,
            "fallback_reason": "recipe_changes_detected",
            "verify_full_preview": verification_policy["requested_verify_full_preview"],
            "effective_verify_full_preview": verification_policy["effective_verify_full_preview"],
            "verification_mode": verification_policy["verification_mode"],
            "offer_change_counts": offer_changes.get("counts", {}),
            "recipe_change_counts": recipe_changes.get("counts", {}),
            **operation_context,
        }
        if apply:
            record_cache_last_operation(
                result,
                operation_type="offer_delta",
                status="fallback",
            )
        return result

    current_offer_term_postings = _build_current_offer_term_postings(offers)
    (
        offer_term_postings,
        offer_term_stats,
        current_recipe_term_postings,
        current_recipe_term_stats,
        persisted_recipe_term_postings,
        persisted_recipe_term_stats,
    ) = _load_or_build_delta_term_postings(
        recipes=recipes,
        current_offer_term_postings=current_offer_term_postings,
    )
    persisted_offer_recipe_map = load_persisted_offer_recipe_map()

    offer_planner = plan_offer_delta_recipe_impacts(
        offer_changes,
        current_offer_term_postings=current_offer_term_postings,
        persisted_offer_term_postings=offer_term_postings,
        current_recipe_term_postings=current_recipe_term_postings,
        persisted_recipe_term_postings=persisted_recipe_term_postings,
        persisted_offer_recipe_map=persisted_offer_recipe_map,
    )
    combined_planner = plan_combined_delta_recipe_impacts(offer_planner, recipe_changes)
    patch_recipe_ids = _plan_delta_patch_recipe_ids(combined_planner)
    remove_recipe_ids = combined_planner.get("remove_recipe_ids", [])

    baseline_entries_list = _raw_entries_from_table(ACTIVE_CACHE_TABLE)
    baseline_entry_map = _raw_entry_map_from_entries(baseline_entries_list)
    baseline_snapshot = _fingerprint_snapshot_from_entries(baseline_entries_list)
    del baseline_entries_list

    # Move the compiled baseline to current before preview/apply.
    set_compiled_offer_baseline_committed(False)
    refresh_compiled_offer_match_data()
    refresh_compiled_recipe_match_data()
    refreshed_offer_term_stats = refresh_compiled_offer_term_index()
    refreshed_recipe_term_stats = refresh_compiled_recipe_term_index()
    changed_candidate_offer_ids = sorted(set(offer_changes.get("rematch_offer_ids", ())))
    candidate_stats = None
    if changed_candidate_offer_ids:
        candidate_stats = refresh_compiled_recipe_offer_candidates(
            term_manifest_hash=refreshed_recipe_term_stats.get("term_manifest_hash"),
            cleanup_stale=False,
            offer_identity_keys=changed_candidate_offer_ids,
        )
    try:
        refresh_compiled_recipe_search_term_index()
    except Exception as exc:
        logger.warning(
            "Pantry search-term index refresh failed during offer delta setup; "
            "pantry will fall back to legacy until the index is refreshed: {}",
            exc,
        )

    manager = cache_manager
    full_preview = None
    full_preview_snapshot: dict[str, str] | None = None
    delta_verification_max_workers = _delta_verification_max_workers()
    if verification_policy["effective_verify_full_preview"]:
        full_preview = manager.refresh_cache(
            persist=False,
            return_entries=True,
            run_kind="delta_full_preview",
            input_scope="live",
            max_workers=delta_verification_max_workers,
        )
        full_preview_entries = full_preview.pop("entries")
        full_preview_snapshot = _fingerprint_snapshot_from_entries(full_preview_entries)
        del full_preview_entries

    patch_preview = manager.refresh_cache(
        persist=False,
        return_entries=True,
        recipe_ids=patch_recipe_ids,
        run_kind="delta_patch_preview",
        input_scope="live",
        max_workers=delta_verification_max_workers,
    )
    patch_preview_entries = patch_preview.pop("entries")
    patch_entries = _raw_entry_map_from_entries(patch_preview_entries)
    del patch_preview_entries

    if not patch_recipe_ids and not remove_recipe_ids:
        materialized_entries = baseline_entry_map
        materialized_snapshot = baseline_snapshot
    else:
        materialized_entries = _materialize_delta_entries(
            baseline_entry_map,
            patch_entries,
            patch_recipe_ids=patch_recipe_ids,
            remove_recipe_ids=remove_recipe_ids,
        )
        materialized_snapshot = _fingerprint_snapshot_from_entries(list(materialized_entries.values()))

    planner_covers_preview_diff = True
    materialized_matches_full_preview = True
    actual_changed_recipe_ids: list[str] = []
    materialized_diff = {
        "parity_ok": True,
        "mismatched_sample": [],
    }
    if full_preview_snapshot is not None:
        materialized_diff = _compare_snapshots(materialized_snapshot, full_preview_snapshot)
        actual_changed_recipe_ids = _compute_actual_changed_recipe_ids(
            baseline_snapshot,
            full_preview_snapshot,
        )
        planner_covers_preview_diff = set(actual_changed_recipe_ids).issubset(
            set(combined_planner["all_impacted_recipe_ids"])
        )
        materialized_matches_full_preview = materialized_diff["parity_ok"]

    ready_to_apply = (
        planner_covers_preview_diff
        and materialized_matches_full_preview
    )

    fallback_reason = None
    if not planner_covers_preview_diff:
        fallback_reason = "planner_missed_preview_diff"
    elif not materialized_matches_full_preview:
        fallback_reason = "materialized_patch_mismatch"

    applied = False
    unmatched_offer_counts = None
    if apply and ready_to_apply:
        manager._save_cache_to_db(list(materialized_entries.values()))
        unmatched_offer_counts = _cached_unmatched_offer_counts(manager)
        unmatched_offer_counts.update(_schedule_unmatched_offer_count_refresh(manager))
        _set_runtime_rebuild_profile(manager)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        total_recipes = (
            full_preview["total_recipes"]
            if full_preview is not None
            else len(recipes)
        )
        _update_cache_metadata(
            total_matches=len(materialized_entries),
            total_recipes=total_recipes,
            time_ms=elapsed_ms,
        )
        set_compiled_offer_baseline_committed(True)
        applied = True

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    result = {
        "success": ready_to_apply,
        "applied": applied,
        "ready_to_apply": ready_to_apply,
        "fallback_reason": fallback_reason,
        "verify_full_preview": verification_policy["requested_verify_full_preview"],
        "effective_verify_full_preview": verification_policy["effective_verify_full_preview"],
        "verification_mode": verification_policy["verification_mode"],
        "delta_verification_max_workers": delta_verification_max_workers,
        "probation_ready": verification_policy["probation_status"]["ready"],
        "probation_history_file": verification_policy["probation_status"]["history_file"],
        "probation_reasons": verification_policy["probation_status"]["reasons"],
        "probation_summary": verification_policy["probation_status"]["summary"],
        "full_preview_recipe_selection_mode": (
            full_preview.get("recipe_selection_mode") if full_preview is not None else None
        ),
        "patch_preview_recipe_selection_mode": patch_preview.get("recipe_selection_mode"),
        "ingredient_routing_mode": patch_preview.get(
            "ingredient_routing_mode",
            verification_policy["ingredient_routing_mode"],
        ),
        "ingredient_routing_effective_mode": patch_preview.get("ingredient_routing_effective_mode"),
        "ingredient_routing_fallback_reason": patch_preview.get("ingredient_routing_fallback_reason"),
        "full_preview_ingredient_routing": _ingredient_routing_summary_from_result(full_preview),
        "patch_preview_ingredient_routing": _ingredient_routing_summary_from_result(patch_preview),
        "offer_change_counts": offer_changes.get("counts", {}),
        "recipe_change_counts": recipe_changes.get("counts", {}),
        "combined_planner_counts": combined_planner.get("counts", {}),
        "unmatched_offer_counts": unmatched_offer_counts,
        "patch_recipe_count": len(patch_recipe_ids),
        "actual_changed_recipes": len(actual_changed_recipe_ids),
        "planner_covers_preview_diff": planner_covers_preview_diff,
        "materialized_patch_matches_full_preview": materialized_matches_full_preview,
        "materialized_mismatched_sample": materialized_diff.get("mismatched_sample", []),
        "full_preview_time_ms": full_preview["time_ms"] if full_preview is not None else None,
        "patch_preview_time_ms": patch_preview["time_ms"],
        "cached": len(materialized_entries),
        "total_recipes": (
            full_preview["total_recipes"]
            if full_preview is not None
            else len(recipes)
        ),
        "time_ms": elapsed_ms,
        "effective_rebuild_mode": "delta" if applied else "compiled",
        "matcher_version": MATCHER_VERSION,
        "recipe_compiler_version": RECIPE_COMPILER_VERSION,
        "offer_compiler_version": OFFER_COMPILER_VERSION,
        "offer_data_source": "compiled",
        "recipe_data_source": "compiled_payload",
        "candidate_data_source": patch_preview.get("candidate_data_source", "db_candidates"),
        "term_index_stats": {
            "offer": offer_term_stats,
            "current_recipe": current_recipe_term_stats,
            "persisted_recipe": persisted_recipe_term_stats,
            "recipe": current_recipe_term_stats,
            "refreshed_offer": refreshed_offer_term_stats,
            "refreshed_recipe": refreshed_recipe_term_stats,
            "recipe_offer_candidates": candidate_stats,
        },
        **operation_context,
    }
    if apply:
        record_cache_last_operation(
            result,
            operation_type="offer_delta",
            status="ready" if applied else "fallback",
        )
    return result


def apply_verified_offer_delta(
    *,
    apply: bool = True,
    verify_full_preview: bool = True,
    operation_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply offer delta through the shared cache operation lock."""
    from cache_manager import run_cache_operation

    return run_cache_operation(
        "offer_delta",
        lambda: _apply_verified_offer_delta_unlocked(
            apply=apply,
            verify_full_preview=verify_full_preview,
            operation_context=operation_context,
        ),
    )


def apply_recipe_delta(
    *,
    changed_recipe_ids: list[str] | None = None,
    removed_recipe_ids: list[str] | None = None,
    source: str | None = None,
    apply: bool = True,
    verify_full_preview: bool | None = None,
    skip_if_busy: bool = True,
    cache_status_snapshot: dict[str, Any] | None = None,
    operation_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply recipe delta through the shared cache operation lock."""
    started_at = time.perf_counter()
    removed_ids = _dedupe_recipe_delta_ids(removed_recipe_ids)
    removed_set = set(removed_ids)
    changed_ids = [
        recipe_id
        for recipe_id in _dedupe_recipe_delta_ids(changed_recipe_ids)
        if recipe_id not in removed_set
    ]
    operation_context = dict(operation_context or {})

    if not changed_ids and not removed_ids:
        return {
            "success": True,
            "applied": False,
            "ready_to_apply": True,
            "noop": True,
            "fallback_reason": None,
            "source": source,
            "changed_recipe_count": 0,
            "removed_recipe_count": 0,
            "patch_recipe_count": 0,
            "time_ms": int((time.perf_counter() - started_at) * 1000),
            "effective_rebuild_mode": "delta",
            "matcher_version": MATCHER_VERSION,
            "recipe_compiler_version": RECIPE_COMPILER_VERSION,
            "offer_compiler_version": OFFER_COMPILER_VERSION,
            **operation_context,
        }

    if not settings.cache_recipe_delta_enabled:
        result = _recipe_delta_fallback_result(
            changed_recipe_ids=changed_ids,
            removed_recipe_ids=removed_ids,
            source=source,
            fallback_reason="recipe_delta_disabled",
            started_at=started_at,
        )
        result.update(operation_context)
        _emit_recipe_delta_summary(result, level="warning")
        return result

    from cache_manager import run_cache_operation

    effective_verify_full_preview = (
        settings.cache_recipe_delta_verify_full_preview
        if verify_full_preview is None
        else verify_full_preview
    )
    return run_cache_operation(
        "recipe_delta",
        lambda: _apply_recipe_delta_unlocked(
            changed_recipe_ids=changed_ids,
            removed_recipe_ids=removed_ids,
            source=source,
            apply=apply,
            verify_full_preview=effective_verify_full_preview,
            cache_status_snapshot=cache_status_snapshot,
            operation_context=operation_context,
        ),
        skip_if_busy=skip_if_busy,
    )
