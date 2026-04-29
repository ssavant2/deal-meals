"""Verified delta-apply helpers for runtime cache refreshes."""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
import os
import time
from typing import Any

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
    from ingredient_routing_probation_runtime import (
        get_configured_ingredient_routing_mode,
        get_ingredient_routing_probation_gate_status,
    )
except ModuleNotFoundError:
    from app.ingredient_routing_probation_runtime import (
        get_configured_ingredient_routing_mode,
        get_ingredient_routing_probation_gate_status,
    )

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
        refresh_compiled_recipe_term_index,
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
        refresh_compiled_recipe_term_index,
    )


ACTIVE_CACHE_TABLE = "recipe_offer_cache"
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
    rebuild_max_workers = max(1, settings.cache_rebuild_max_workers)
    detected_core_workers = max(1, (os.cpu_count() or 1) - 1)
    return min(configured_max_workers, rebuild_max_workers, detected_core_workers)


VERSION_FIELDS = (
    "matcher_version",
    "recipe_compiler_version",
    "offer_compiler_version",
)
INGREDIENT_ROUTING_RESULT_FIELDS = (
    "ingredient_routing_mode",
    "ingredient_routing_effective_mode",
    "ingredient_routing_fallback_reason",
    "cache_ingredient_routing_probation_ready",
    "cache_ingredient_routing_probation_reasons",
    "cache_ingredient_routing_probation_recommendations",
    "cache_ingredient_routing_probation_current_ready_streak",
    "cache_ingredient_routing_probation_current_version_ready_run_count",
    "cache_ingredient_routing_probation_distinct_version_count",
    "estimated_fullscan_ingredient_checks",
    "estimated_hinted_ingredient_checks",
    "estimated_ingredient_check_reduction_pct",
    "ingredient_check_count",
    "hinted_check_count",
    "hinted_no_match_count",
    "fullscan_fallback_count",
    "fullscan_fallback_reason_counts",
    "actual_ingredient_check_reduction_pct",
    "shadow_pair_count",
    "shadow_candidate_change_count",
    "shadow_unexplained_miss_count",
    "shadow_fallback_reason_counts",
    "ingredient_routing_shadow_measured",
    "time_ms",
    "cached",
    "total_recipes",
)


@contextmanager
def _temporary_ingredient_routing_mode(mode: str):
    """Temporarily override ingredient routing mode inside the delta lock."""
    previous_mode = settings.cache_ingredient_routing_mode
    settings.cache_ingredient_routing_mode = mode
    try:
        yield
    finally:
        settings.cache_ingredient_routing_mode = previous_mode


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


def _set_runtime_rebuild_profile(cache_manager) -> None:
    configured = cache_manager.get_rebuild_profile()
    cache_manager._last_rebuild_profile = {
        "configured_rebuild_mode": configured["mode"],
        "effective_rebuild_mode": "delta",
        "offer_data_source": "compiled",
        "recipe_data_source": "compiled_payload",
        "candidate_data_source": "term_index",
    }


def _resolve_delta_verification_policy(*, verify_full_preview: bool) -> dict[str, Any]:
    """Decide whether this delta run should pay the cost of a full preview."""
    probation_status = get_delta_probation_gate_status()
    ingredient_routing_mode = get_configured_ingredient_routing_mode()
    ingredient_probation_status = get_ingredient_routing_probation_gate_status()
    ingredient_routing_fullscan_baseline_gate_ready = (
        probation_status["ready"] and ingredient_probation_status["ready"]
    )
    ingredient_routing_requires_fullscan_baseline = (
        ingredient_routing_mode == "hint_first"
        and not ingredient_routing_fullscan_baseline_gate_ready
    )

    effective_verify_full_preview = verify_full_preview
    verification_mode = "disabled"
    if verify_full_preview:
        verification_mode = "full_preview"
        if settings.cache_delta_skip_full_preview_after_probation:
            verification_mode = "full_preview_pending_probation"
            if probation_status["ready"]:
                effective_verify_full_preview = False
                verification_mode = "probation_skip"

    if ingredient_routing_requires_fullscan_baseline:
        effective_verify_full_preview = True
        if verification_mode in {"disabled", "probation_skip"}:
            verification_mode = "full_preview_required_for_hint_first"

    return {
        "requested_verify_full_preview": verify_full_preview,
        "effective_verify_full_preview": effective_verify_full_preview,
        "verification_mode": verification_mode,
        "probation_status": probation_status,
        "ingredient_routing_mode": ingredient_routing_mode,
        "ingredient_routing_probation_status": ingredient_probation_status,
        "ingredient_routing_fullscan_baseline_gate_ready": (
            ingredient_routing_fullscan_baseline_gate_ready
        ),
        "ingredient_routing_requires_fullscan_baseline": ingredient_routing_requires_fullscan_baseline,
    }


def _apply_verified_offer_delta_unlocked(
    *,
    apply: bool = True,
    verify_full_preview: bool = True,
) -> dict[str, Any]:
    """Apply a verified offer-driven delta patch to the active cache table."""
    from cache_manager import cache_manager

    started_at = time.perf_counter()

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
        return {
            "success": False,
            "applied": False,
            "fallback_reason": "recipe_changes_detected",
            "offer_change_counts": offer_changes.get("counts", {}),
            "recipe_change_counts": recipe_changes.get("counts", {}),
        }

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
    refresh_compiled_offer_match_data()
    refresh_compiled_recipe_match_data()
    refresh_compiled_offer_term_index()
    refresh_compiled_recipe_term_index()

    manager = cache_manager
    full_preview = None
    full_preview_snapshot: dict[str, str] | None = None
    fullscan_baseline_preview = None
    ingredient_routing_fullscan_baseline_checked = False
    ingredient_routing_fullscan_baseline_matches = True
    ingredient_routing_fullscan_baseline_diff = {
        "parity_ok": True,
        "mismatched_count": 0,
        "mismatched_sample": [],
    }
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

        if full_preview.get("ingredient_routing_effective_mode") == "hint_first":
            with _temporary_ingredient_routing_mode("off"):
                fullscan_baseline_preview = manager.refresh_cache(
                    persist=False,
                    return_entries=True,
                    run_kind="delta_fullscan_baseline_preview",
                    input_scope="live",
                    max_workers=delta_verification_max_workers,
                )
            fullscan_baseline_entries = fullscan_baseline_preview.pop("entries")
            fullscan_baseline_snapshot = _fingerprint_snapshot_from_entries(fullscan_baseline_entries)
            del fullscan_baseline_entries
            ingredient_routing_fullscan_baseline_diff = _compare_snapshots(
                fullscan_baseline_snapshot,
                full_preview_snapshot,
            )
            del fullscan_baseline_snapshot
            ingredient_routing_fullscan_baseline_checked = True
            ingredient_routing_fullscan_baseline_matches = (
                ingredient_routing_fullscan_baseline_diff["parity_ok"]
            )

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
        and ingredient_routing_fullscan_baseline_matches
    )

    fallback_reason = None
    if not planner_covers_preview_diff:
        fallback_reason = "planner_missed_preview_diff"
    elif not materialized_matches_full_preview:
        fallback_reason = "materialized_patch_mismatch"
    elif not ingredient_routing_fullscan_baseline_matches:
        fallback_reason = "ingredient_routing_fullscan_baseline_mismatch"

    applied = False
    if apply and ready_to_apply:
        manager._save_cache_to_db(list(materialized_entries.values()))
        manager.update_unmatched_offer_count(list(materialized_entries.values()))
        _set_runtime_rebuild_profile(manager)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        total_recipes = full_preview["total_recipes"] if full_preview is not None else None
        _update_cache_metadata(
            total_matches=len(materialized_entries),
            total_recipes=total_recipes,
            time_ms=elapsed_ms,
        )
        applied = True

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    return {
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
        "ingredient_routing_mode": patch_preview.get(
            "ingredient_routing_mode",
            verification_policy["ingredient_routing_mode"],
        ),
        "ingredient_routing_effective_mode": patch_preview.get("ingredient_routing_effective_mode"),
        "ingredient_routing_fallback_reason": patch_preview.get("ingredient_routing_fallback_reason"),
        "ingredient_routing_probation_ready": verification_policy[
            "ingredient_routing_probation_status"
        ]["ready"],
        "ingredient_routing_probation_reasons": verification_policy[
            "ingredient_routing_probation_status"
        ]["reasons"],
        "ingredient_routing_fullscan_baseline_required": verification_policy[
            "ingredient_routing_requires_fullscan_baseline"
        ],
        "ingredient_routing_fullscan_baseline_gate_ready": verification_policy[
            "ingredient_routing_fullscan_baseline_gate_ready"
        ],
        "ingredient_routing_fullscan_baseline_checked": ingredient_routing_fullscan_baseline_checked,
        "ingredient_routing_fullscan_baseline_matches": ingredient_routing_fullscan_baseline_matches,
        "ingredient_routing_fullscan_baseline_mismatched_count": (
            ingredient_routing_fullscan_baseline_diff.get("mismatched_count", 0)
        ),
        "ingredient_routing_fullscan_baseline_mismatched_sample": (
            ingredient_routing_fullscan_baseline_diff.get("mismatched_sample", [])
        ),
        "full_preview_ingredient_routing": _ingredient_routing_summary_from_result(full_preview),
        "patch_preview_ingredient_routing": _ingredient_routing_summary_from_result(patch_preview),
        "fullscan_baseline_ingredient_routing": _ingredient_routing_summary_from_result(
            fullscan_baseline_preview
        ),
        "offer_change_counts": offer_changes.get("counts", {}),
        "recipe_change_counts": recipe_changes.get("counts", {}),
        "combined_planner_counts": combined_planner.get("counts", {}),
        "patch_recipe_count": len(patch_recipe_ids),
        "actual_changed_recipes": len(actual_changed_recipe_ids),
        "planner_covers_preview_diff": planner_covers_preview_diff,
        "materialized_patch_matches_full_preview": materialized_matches_full_preview,
        "materialized_mismatched_sample": materialized_diff.get("mismatched_sample", []),
        "full_preview_time_ms": full_preview["time_ms"] if full_preview is not None else None,
        "fullscan_baseline_time_ms": (
            fullscan_baseline_preview["time_ms"] if fullscan_baseline_preview is not None else None
        ),
        "patch_preview_time_ms": patch_preview["time_ms"],
        "cached": len(materialized_entries),
        "total_recipes": full_preview["total_recipes"] if full_preview is not None else None,
        "time_ms": elapsed_ms,
        "effective_rebuild_mode": "delta" if applied else "compiled",
        "matcher_version": MATCHER_VERSION,
        "recipe_compiler_version": RECIPE_COMPILER_VERSION,
        "offer_compiler_version": OFFER_COMPILER_VERSION,
        "offer_data_source": "compiled",
        "recipe_data_source": "compiled_payload",
        "candidate_data_source": "term_index",
        "term_index_stats": {
            "offer": offer_term_stats,
            "current_recipe": current_recipe_term_stats,
            "persisted_recipe": persisted_recipe_term_stats,
            "recipe": current_recipe_term_stats,
        },
    }


def apply_verified_offer_delta(
    *,
    apply: bool = True,
    verify_full_preview: bool = True,
) -> dict[str, Any]:
    """Apply offer delta through the shared cache operation lock."""
    from cache_manager import run_cache_operation

    return run_cache_operation(
        "offer_delta",
        lambda: _apply_verified_offer_delta_unlocked(
            apply=apply,
            verify_full_preview=verify_full_preview,
        ),
    )
