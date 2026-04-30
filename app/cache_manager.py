"""
Cache Manager - Pre-compute recipe-offer matches for fast page loads.

This module computes matches between all recipes and current offers,
storing results in the recipe_offer_cache table. Called when:
1. Offers are updated (after scraper completes)
2. User preferences change significantly
3. Manually via CLI

PERFORMANCE / SIZING:
- Rebuild time depends on recipe count, offer count, routing mode, database
  speed and the configured worker cap.
- Process-pool workers are capped by CACHE_REBUILD_MAX_WORKERS and detected
  cores; delta verification is capped by CACHE_DELTA_VERIFICATION_MAX_WORKERS
  and never exceeds the rebuild cap.
- Large recipe libraries need more web-container memory when rebuilds run in
  parallel. See README for install sizing guidance.
"""

from loguru import logger
from typing import Any, Callable, Dict, Optional, List
from database import get_db_session, engine
from models import FoundRecipe
from sqlalchemy import text
import json
import time
import asyncio
import os
from threading import Lock
from concurrent.futures import ProcessPoolExecutor

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
        append_ingredient_routing_probation_history,
        get_configured_ingredient_routing_mode,
        get_ingredient_routing_probation_gate_status,
    )
except ModuleNotFoundError:
    from app.ingredient_routing_probation_runtime import (
        append_ingredient_routing_probation_history,
        get_configured_ingredient_routing_mode,
        get_ingredient_routing_probation_gate_status,
    )

try:
    from cache_operation_metadata import record_cache_last_operation
except ModuleNotFoundError:
    from app.cache_operation_metadata import record_cache_last_operation

# Import matching logic
try:
    from recipe_matcher import RecipeMatcher, get_effective_matching_preferences, get_enabled_recipe_sources
    from languages.matcher_runtime import (
        MATCHER_VERSION,
        OFFER_COMPILER_VERSION,
        RECIPE_COMPILER_VERSION,
        build_candidate_map_from_term_postings,
        build_candidate_term_detail_from_term_postings,
        build_fts_keyword_set,
        build_recipe_ingredient_term_map,
        build_offer_candidate_terms,
        is_boring_recipe,
        is_buffet_or_party_recipe,
        is_off_season_recipe,
        load_compiled_offer_runtime_cache,
        load_compiled_offer_term_postings,
        load_compiled_recipe_payload_cache,
        load_compiled_recipe_term_postings,
        build_offer_identity_key,
        refresh_compiled_offer_match_data,
        refresh_compiled_offer_term_index,
        refresh_compiled_recipe_match_data,
        refresh_compiled_recipe_term_index,
        analyze_ingredient_routing_shadow_backend,
        resolve_recipe_match_runtime_data,
    )
    from languages.categories import (
        MEAT, FISH, VEGETARIAN,
        POULTRY, DELI,
    )
except ModuleNotFoundError:
    from app.recipe_matcher import RecipeMatcher, get_effective_matching_preferences, get_enabled_recipe_sources
    from app.languages.matcher_runtime import (
        MATCHER_VERSION,
        OFFER_COMPILER_VERSION,
        RECIPE_COMPILER_VERSION,
        build_candidate_map_from_term_postings,
        build_candidate_term_detail_from_term_postings,
        build_fts_keyword_set,
        build_recipe_ingredient_term_map,
        build_offer_candidate_terms,
        is_boring_recipe,
        is_buffet_or_party_recipe,
        is_off_season_recipe,
        load_compiled_offer_runtime_cache,
        load_compiled_offer_term_postings,
        load_compiled_recipe_payload_cache,
        load_compiled_recipe_term_postings,
        build_offer_identity_key,
        refresh_compiled_offer_match_data,
        refresh_compiled_offer_term_index,
        refresh_compiled_recipe_match_data,
        refresh_compiled_recipe_term_index,
        analyze_ingredient_routing_shadow_backend,
        resolve_recipe_match_runtime_data,
    )
    from app.languages.categories import (
        MEAT, FISH, VEGETARIAN,
        POULTRY, DELI,
    )


def _extract_stable_matched_offer_key(offer_data: Dict[str, Any]) -> str | None:
    """Prefer stable offer identities over row ids inside cached payloads."""
    value = offer_data.get("offer_identity_key") or offer_data.get("id")
    if value is None:
        return None
    return str(value)


def _select_indexable_offer_identity_keys(
    offers: List[Any],
    offer_data_cache: Dict[int, Dict[str, Any]],
) -> set[str]:
    """Return stable offer ids for offers that produce at least one routing term."""
    indexable_keys = set()
    for offer in offers:
        compiled_offer_data = offer_data_cache.get(id(offer))
        if not compiled_offer_data:
            continue
        if build_offer_candidate_terms(compiled_offer_data):
            indexable_keys.add(build_offer_identity_key(offer))
    return indexable_keys


def _ingredient_routing_probation_summary_fields(probation_status: Dict[str, Any]) -> Dict[str, Any]:
    summary = probation_status["summary"]
    latest_entry = probation_status["latest_entry"]
    return {
        "cache_ingredient_routing_probation_history_file": probation_status["history_file"],
        "cache_ingredient_routing_probation_ready": probation_status["ready"],
        "cache_ingredient_routing_probation_reasons": probation_status["reasons"],
        "cache_ingredient_routing_probation_recommendations": probation_status["recommendations"],
        "cache_ingredient_routing_probation_current_ready_streak": summary["current_ready_streak"],
        "cache_ingredient_routing_probation_current_version_ready_run_count": (
            summary["current_version_ready_run_count"]
        ),
        "cache_ingredient_routing_probation_distinct_version_count": summary["distinct_version_count"],
        "cache_ingredient_routing_probation_last_run_at": (
            latest_entry.get("generated_at") if latest_entry else None
        ),
        "cache_ingredient_routing_probation_last_run_ready": (
            latest_entry.get("ready_for_hint_first") if latest_entry else None
        ),
        "cache_ingredient_routing_probation_last_verification_mode": (
            latest_entry.get("ingredient_routing_effective_mode") if latest_entry else None
        ),
    }


def _resolve_ingredient_routing_mode() -> tuple[str, str, str | None, Dict[str, Any]]:
    configured_mode = get_configured_ingredient_routing_mode()
    probation_status = get_ingredient_routing_probation_gate_status()
    if configured_mode == "hint_first":
        if probation_status["ready"]:
            return configured_mode, "hint_first", None, probation_status
        return (
            configured_mode,
            "probation",
            "probation_gate_not_ready",
            probation_status,
        )
    return configured_mode, configured_mode, None, probation_status


def _add_shadow_sample(
    samples_by_class: Dict[str, list[Dict[str, Any]]],
    mismatch_class: str,
    *,
    recipe,
    offer,
    shadow: Dict[str, Any],
) -> None:
    samples = samples_by_class.setdefault(mismatch_class, [])
    if len(samples) >= 3:
        return
    samples.append({
        "recipe_id": str(recipe.id),
        "recipe_name": recipe.name,
        "offer_identity_key": build_offer_identity_key(offer),
        "offer_name": offer.name,
        "hinted_indices": shadow["hinted_indices"],
        "fullscan_selection": {
            "selected_ing_idx": shadow["fullscan_selection"]["selected_ing_idx"],
            "selected_keyword": shadow["fullscan_selection"]["selected_keyword"],
            "selected_by_fewer_keywords": shadow["fullscan_selection"]["selected_by_fewer_keywords"],
        },
        "hinted_selection": {
            "selected_ing_idx": shadow["hinted_selection"]["selected_ing_idx"],
            "selected_keyword": shadow["hinted_selection"]["selected_keyword"],
            "selected_by_fewer_keywords": shadow["hinted_selection"]["selected_by_fewer_keywords"],
        },
        "fullscan_validated_signature": shadow["fullscan_validated_signature"],
        "hinted_validated_signature": shadow["hinted_validated_signature"],
    })


def _measure_ingredient_routing_shadow(
    *,
    recipes: List[FoundRecipe],
    candidate_term_detail_by_recipe: Dict[str, Dict[str, set[str]]],
    offer_lookup: Dict[str, Any],
    offer_keywords: Dict[int, List[str]],
    offer_data_cache: Dict[int, Dict[str, Any]],
    compiled_recipe_payload_cache: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Measure ingredient-routing hints beside fullscan without changing output."""
    from collections import Counter

    start = time.perf_counter()
    recipe_by_id = {str(recipe.id): recipe for recipe in recipes}
    runtime_recipe_data_by_id: Dict[str, Dict[str, Any]] = {}
    routing_terms_by_recipe_id: Dict[str, set[str]] = {}

    for recipe_id, offer_terms in candidate_term_detail_by_recipe.items():
        recipe = recipe_by_id.get(str(recipe_id))
        if recipe is None:
            continue
        runtime_recipe_data_by_id[str(recipe_id)] = resolve_recipe_match_runtime_data(
            recipe,
            compiled_recipe_data=compiled_recipe_payload_cache.get(str(recipe_id)),
        )
        routing_terms_by_recipe_id[str(recipe_id)] = {
            term
            for terms in offer_terms.values()
            for term in terms
        }

    map_start = time.perf_counter()
    ingredient_term_maps: Dict[str, Dict[str, set[int]]] = {}
    for recipe_id, runtime_recipe_data in runtime_recipe_data_by_id.items():
        ingredient_term_maps[recipe_id] = build_recipe_ingredient_term_map(
            compiled_recipe_payload_cache.get(recipe_id, runtime_recipe_data),
            routing_terms_by_recipe_id[recipe_id],
        )
    ingredient_term_map_ms = int((time.perf_counter() - map_start) * 1000)

    stats: Counter[str] = Counter()
    fallback_reason_counts: Counter[str] = Counter()
    fullscan_fallback_reason_counts: Counter[str] = Counter()
    samples_by_class: Dict[str, list[Dict[str, Any]]] = {}
    fallback_required_classes = {
        "no_hint_for_routed_pair",
        "fullscan_initial_winner_outside_hint",
        "hinted_initial_no_match",
        "hinted_different_matched_keyword",
        "hinted_same_keyword_different_ingredient_line",
        "validated_candidate_change",
        "validation_retry_moved_match_outside_hint",
        "specialty_retry_moved_match_outside_hint",
        "spice_fresh_retry_moved_match_outside_hint",
        "carrier_flavor_context_retry_moved_match_outside_hint",
        "unexplained_validated_mismatch",
    }

    fullscan_checks = 0
    hinted_checks = 0
    hint_or_fullscan_checks = 0
    no_hint_pair_count = 0

    for recipe_id, offer_terms_by_id in candidate_term_detail_by_recipe.items():
        recipe = recipe_by_id.get(str(recipe_id))
        runtime_recipe_data = runtime_recipe_data_by_id.get(str(recipe_id))
        if recipe is None or runtime_recipe_data is None:
            continue

        num_ingredients = len(recipe.ingredients) if recipe.ingredients else 0
        if is_buffet_or_party_recipe(recipe.name, num_ingredients):
            continue
        if is_boring_recipe(recipe.name):
            continue

        ingredient_match_data = runtime_recipe_data["ingredient_match_data_per_ing"]
        ingredient_count = len(ingredient_match_data)
        ingredient_term_map = ingredient_term_maps.get(str(recipe_id), {})

        for offer_identity_key, routing_terms in offer_terms_by_id.items():
            offer = offer_lookup.get(offer_identity_key)
            if offer is None:
                continue

            hinted_indices: set[int] = set()
            for term in routing_terms:
                hinted_indices.update(ingredient_term_map.get(term, set()))

            hint_size = len(hinted_indices)
            fullscan_checks += ingredient_count
            hinted_checks += hint_size
            if hint_size:
                hint_or_fullscan_checks += hint_size
            else:
                no_hint_pair_count += 1
                hint_or_fullscan_checks += ingredient_count

            shadow = analyze_ingredient_routing_shadow_backend(
                offer,
                id(offer),
                offer_keywords,
                offer_data_cache,
                ingredient_match_data,
                hinted_indices,
                runtime_recipe_data["ingredients_normalized"],
                runtime_recipe_data["ingredient_source_texts"],
                runtime_recipe_data["ingredient_source_indices"],
                runtime_recipe_data["merged_ingredients"],
                runtime_recipe_data["full_recipe_text"],
            )
            stats["shadow_pair_count"] += 1
            if not shadow["parity"]:
                stats["shadow_candidate_change_count"] += 1

            mismatch_classes = set(shadow["mismatch_classes"])
            if mismatch_classes & {
                "fullscan_initial_winner_outside_hint",
                "hinted_initial_no_match",
            }:
                stats["shadow_initial_miss_count"] += 1
            if "validation_retry_moved_match_outside_hint" in mismatch_classes:
                stats["shadow_retry_miss_count"] += 1
            if "specialty_retry_moved_match_outside_hint" in mismatch_classes:
                stats["shadow_specialty_retry_miss_count"] += 1
            if "spice_fresh_retry_moved_match_outside_hint" in mismatch_classes:
                stats["shadow_spice_fresh_retry_miss_count"] += 1
            if "processed_rule_rejected_hinted_match_fullscan_avoided" in mismatch_classes:
                stats["shadow_processed_rule_miss_count"] += 1
            if mismatch_classes & {
                "carrier_flavor_context_rejected_hinted_match_fullscan_avoided",
                "carrier_flavor_context_retry_moved_match_outside_hint",
            }:
                stats["shadow_carrier_flavor_context_miss_count"] += 1
            if "product_name_blocker_rejected_hinted_match_fullscan_avoided" in mismatch_classes:
                stats["shadow_product_name_blocker_miss_count"] += 1
            if "unexplained_validated_mismatch" in mismatch_classes:
                stats["shadow_unexplained_miss_count"] += 1

            fallback_classes = mismatch_classes & fallback_required_classes
            if fallback_classes:
                stats["fullscan_fallback_count"] += 1
                for mismatch_class in sorted(fallback_classes):
                    fullscan_fallback_reason_counts[mismatch_class] += 1
            for mismatch_class in shadow["mismatch_classes"]:
                fallback_reason_counts[mismatch_class] += 1
                _add_shadow_sample(
                    samples_by_class,
                    mismatch_class,
                    recipe=recipe,
                    offer=offer,
                    shadow=shadow,
                )

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    default_stats = {
        "shadow_pair_count": 0,
        "shadow_initial_miss_count": 0,
        "shadow_retry_miss_count": 0,
        "shadow_specialty_retry_miss_count": 0,
        "shadow_spice_fresh_retry_miss_count": 0,
        "shadow_processed_rule_miss_count": 0,
        "shadow_carrier_flavor_context_miss_count": 0,
        "shadow_product_name_blocker_miss_count": 0,
        "shadow_candidate_change_count": 0,
        "shadow_unexplained_miss_count": 0,
        "fullscan_fallback_count": 0,
    }
    default_stats.update(dict(stats))
    return {
        "ingredient_routing_shadow_measured": True,
        "ingredient_routing_measurement_ms": elapsed_ms,
        "ingredient_term_map_ms": ingredient_term_map_ms,
        "ingredient_term_map_recipe_count": len(ingredient_term_maps),
        "ingredient_term_map_term_count": sum(len(term_map) for term_map in ingredient_term_maps.values()),
        "ingredient_term_map_nonempty_term_count": sum(
            1
            for term_map in ingredient_term_maps.values()
            for indices in term_map.values()
            if indices
        ),
        "estimated_fullscan_ingredient_checks": fullscan_checks,
        "estimated_hinted_ingredient_checks": hinted_checks,
        "estimated_hint_or_fullscan_if_no_hint_checks": hint_or_fullscan_checks,
        "estimated_hinted_ingredient_reduction_pct": (
            round((1 - (hinted_checks / fullscan_checks)) * 100, 2)
            if fullscan_checks else 0
        ),
        "no_hint_pair_count": no_hint_pair_count,
        "hinted_check_count": hinted_checks,
        "fullscan_fallback_reason_counts": dict(sorted(fullscan_fallback_reason_counts.items())),
        "shadow_fallback_reason_counts": dict(sorted(fallback_reason_counts.items())),
        "shadow_samples_by_class": {
            mismatch_class: samples
            for mismatch_class, samples in sorted(samples_by_class.items())
        },
        **default_stats,
    }


def _build_ingredient_candidate_indices_by_recipe(
    *,
    recipes: List[FoundRecipe],
    candidate_term_detail_by_recipe: Dict[str, Dict[str, set[str]]],
    compiled_recipe_payload_cache: Dict[str, Dict[str, Any]],
    recipe_index_by_id: Dict[str, int],
) -> tuple[Dict[int, Dict[str, set[int]]], Dict[str, Any]]:
    """Build per-recipe, per-offer ingredient hint sets for hint-first scoring."""
    start = time.perf_counter()
    recipe_by_id = {str(recipe.id): recipe for recipe in recipes}
    routing_terms_by_recipe_id = {
        str(recipe_id): {
            term
            for terms in offer_terms.values()
            for term in terms
        }
        for recipe_id, offer_terms in candidate_term_detail_by_recipe.items()
    }

    map_start = time.perf_counter()
    ingredient_term_maps: Dict[str, Dict[str, set[int]]] = {}
    for recipe_id, routing_terms in routing_terms_by_recipe_id.items():
        payload = compiled_recipe_payload_cache.get(recipe_id)
        if not payload:
            continue
        ingredient_term_maps[recipe_id] = build_recipe_ingredient_term_map(payload, routing_terms)
    ingredient_term_map_ms = int((time.perf_counter() - map_start) * 1000)

    ingredient_candidate_indices_by_recipe: Dict[int, Dict[str, set[int]]] = {}
    fullscan_checks = 0
    hinted_checks = 0
    hint_or_fullscan_checks = 0
    no_hint_pair_count = 0

    for recipe_id, offer_terms_by_id in candidate_term_detail_by_recipe.items():
        recipe_id = str(recipe_id)
        recipe = recipe_by_id.get(recipe_id)
        recipe_index = recipe_index_by_id.get(recipe_id)
        payload = compiled_recipe_payload_cache.get(recipe_id)
        if recipe is None or recipe_index is None or not payload:
            continue

        num_ingredients = len(recipe.ingredients) if recipe.ingredients else 0
        if is_buffet_or_party_recipe(recipe.name, num_ingredients):
            continue
        if is_boring_recipe(recipe.name):
            continue

        ingredient_count = len(payload.get("ingredient_match_data", ()))
        term_map = ingredient_term_maps.get(recipe_id, {})
        per_offer_hints: Dict[str, set[int]] = {}
        for offer_identity_key, routing_terms in offer_terms_by_id.items():
            hinted_indices: set[int] = set()
            for term in routing_terms:
                hinted_indices.update(term_map.get(term, set()))
            per_offer_hints[offer_identity_key] = hinted_indices

            hint_size = len(hinted_indices)
            fullscan_checks += ingredient_count
            hinted_checks += hint_size
            if hint_size:
                hint_or_fullscan_checks += hint_size
            else:
                no_hint_pair_count += 1
                hint_or_fullscan_checks += ingredient_count

        if per_offer_hints:
            ingredient_candidate_indices_by_recipe[recipe_index] = per_offer_hints

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return ingredient_candidate_indices_by_recipe, {
        "ingredient_routing_hint_map_ms": elapsed_ms,
        "ingredient_term_map_ms": ingredient_term_map_ms,
        "ingredient_term_map_recipe_count": len(ingredient_term_maps),
        "ingredient_term_map_term_count": sum(len(term_map) for term_map in ingredient_term_maps.values()),
        "ingredient_term_map_nonempty_term_count": sum(
            1
            for term_map in ingredient_term_maps.values()
            for indices in term_map.values()
            if indices
        ),
        "estimated_fullscan_ingredient_checks": fullscan_checks,
        "estimated_hinted_ingredient_checks": hinted_checks,
        "estimated_hint_or_fullscan_if_no_hint_checks": hint_or_fullscan_checks,
        "estimated_hinted_ingredient_reduction_pct": (
            round((1 - (hinted_checks / fullscan_checks)) * 100, 2)
            if fullscan_checks else 0
        ),
        "no_hint_pair_count": no_hint_pair_count,
    }


# === Parallel cache computation ===
# Uses fork-based ProcessPoolExecutor for CPU-bound matching.
# Shared data is set before forking and inherited via copy-on-write.
# When free-threaded Python (no-GIL) is available, this can be
# switched to ThreadPoolExecutor with zero code changes.
_shared = {}  # Set before fork, read by workers via copy-on-write

# Minimum recipes to justify process pool overhead
MIN_RECIPES_FOR_PARALLEL = 500
OFFICIAL_REBUILD_PROFILE = {
    "mode": "compiled",
    "offer_data_source": "compiled",
    "recipe_data_source": "compiled_payload",
    "candidate_data_source": "term_index",
}


def _summary_ms(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{int(value)}ms"
    except (TypeError, ValueError):
        return "n/a"


def _format_rebuild_summary_line(summary: Dict) -> str:
    phase_timings = summary.get("phase_timings_ms") or {}
    phases = " ".join(
        f"{label}={_summary_ms(phase_timings.get(key))}"
        for key, label in (
            ("compile_ms", "compile"),
            ("route_ms", "route"),
            ("score_ms", "score"),
            ("write_ms", "write"),
        )
        if key in phase_timings
    )
    if not phases:
        phases = "phases=n/a"

    requested_count = summary.get("requested_recipe_count")
    selected_count = summary.get("selected_recipe_count")
    total_recipes = summary.get("total_recipes")
    recipe_scope = requested_count or selected_count or total_recipes or "n/a"

    matched_offers = summary.get("matched_offer_ids")
    total_offers = summary.get("total_offers")
    offer_scope = (
        f"{matched_offers}/{total_offers}"
        if matched_offers is not None and total_offers is not None
        else "n/a"
    )

    fallback_count = summary.get("fullscan_fallback_count")
    fallback_part = (
        f" fullscan_fallbacks={fallback_count}"
        if fallback_count is not None
        else ""
    )
    routing_mode = (
        summary.get("ingredient_routing_effective_mode")
        or summary.get("ingredient_routing_mode")
        or "n/a"
    )
    selection_mode = summary.get("recipe_selection_mode")
    selection_part = f" selection={selection_mode}" if selection_mode else ""

    return (
        "CACHE_REBUILD "
        f"run={summary.get('run_kind', 'full')} "
        f"status={summary.get('status', 'unknown')} "
        f"mode={summary.get('effective_rebuild_mode', summary.get('configured_rebuild_mode', 'unknown'))} "
        f"cached={summary.get('cached', 'n/a')} "
        f"recipes={recipe_scope} "
        f"offers={offer_scope} "
        f"time={_summary_ms(summary.get('time_ms'))} "
        f"{phases} "
        f"routing={routing_mode}"
        f"{selection_part}"
        f"{fallback_part}"
    )


def _emit_rebuild_summary(summary: Dict, *, level: str = "info") -> None:
    """Emit one structured rebuild summary log line."""
    payload = json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    log = getattr(logger, level, logger.info)
    log(_format_rebuild_summary_line(summary))
    log(f"CACHE_REBUILD_SUMMARY {payload}")


def _build_cache_entry(recipe, match_result, is_starred):
    """Build a cache entry dict from a match result. Single source of truth."""
    ingredients = recipe.ingredients or []
    return {
        'found_recipe_id': str(recipe.id),
        'recipe_category': match_result['recipe_category'],
        'budget_score': match_result['budget_score'],
        'total_savings': match_result['total_savings'],
        'coverage_pct': match_result['coverage_pct'],
        'num_matches': match_result['num_matches'],
        'is_starred': is_starred,
        'match_data': {
            'matcher_version': match_result.get('matcher_version', MATCHER_VERSION),
            'recipe_compiler_version': match_result.get('recipe_compiler_version', RECIPE_COMPILER_VERSION),
            'offer_compiler_version': match_result.get('offer_compiler_version', OFFER_COMPILER_VERSION),
            'matched_offers': match_result['matched_offers'],
            'match_score': match_result['match_score'],
            'num_offers': match_result.get('num_offers', len(match_result['matched_offers'])),
            'ingredient_groups': match_result.get('ingredient_groups', []),
            'total_savings_pct': match_result.get('total_savings_pct', 0),
            'avg_savings_pct': match_result.get('avg_savings_pct', 0),
        },
        'name': recipe.name,
        'url': recipe.url,
        'source_name': recipe.source_name,
        'image_url': getattr(recipe, 'local_image_path', None) or recipe.image_url,
        'prep_time_minutes': recipe.prep_time_minutes,
        'ingredients': ingredients,
        'ingredient_count': len(ingredients),
        'is_off_season': is_off_season_recipe(recipe.name),
        'servings': recipe.servings,
    }


def _empty_worker_match_stats() -> Dict[str, Any]:
    return {
        "ingredient_check_count": 0,
        "hinted_check_count": 0,
        "hinted_no_match_count": 0,
        "fullscan_fallback_count": 0,
        "fullscan_fallback_reason_counts": {},
    }


def _merge_worker_match_stats(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    target["ingredient_check_count"] += int(source.get("ingredient_check_count") or 0)
    target["hinted_check_count"] += int(source.get("hinted_check_count") or 0)
    target["hinted_no_match_count"] += int(source.get("hinted_no_match_count") or 0)
    target["fullscan_fallback_count"] += int(source.get("fullscan_fallback_count") or 0)
    target_reasons = target.setdefault("fullscan_fallback_reason_counts", {})
    for reason, count in (source.get("fullscan_fallback_reason_counts") or {}).items():
        target_reasons[reason] = target_reasons.get(reason, 0) + int(count or 0)


def _match_recipe_batch(recipe_indices):
    """
    Worker function for parallel cache computation.

    Processes a batch of recipe indices using shared data inherited
    via fork copy-on-write. Returns (cache_entries, buffet_count, seasonal_count).
    """
    s = _shared
    entries = []
    buffet_count = 0
    seasonal_count = 0
    match_stats = _empty_worker_match_stats()

    for i in recipe_indices:
        recipe = s['all_recipes'][i]

        num_ingredients = len(recipe.ingredients) if recipe.ingredients else 0
        if is_buffet_or_party_recipe(recipe.name, num_ingredients):
            buffet_count += 1
            continue
        if is_boring_recipe(recipe.name):
            continue
        if is_off_season_recipe(recipe.name):
            seasonal_count += 1

        relevant_offers = s['recipe_relevant_offers'].get(i)
        if not relevant_offers:
            continue

        result = s['matcher']._match_recipe_to_offers(
            recipe, relevant_offers, s['preferences'],
            s['offer_keywords'], s['offer_data_cache'],
            compiled_recipe_data=(
                s.get('compiled_recipe_payload_cache', {}).get(str(recipe.id))
                if s.get('compiled_recipe_payload_cache')
                else None
            ),
            ingredient_candidate_indices_by_offer=(
                s.get('ingredient_candidate_indices_by_recipe', {}).get(i)
                if s.get('ingredient_candidate_indices_by_recipe')
                else None
            ),
            ingredient_routing_mode=s.get('ingredient_routing_effective_mode', 'off'),
        )
        _merge_worker_match_stats(match_stats, result)

        if result['num_matches'] > 0:
            starred = is_source_starred(recipe.source_name, s['starred_sources'])
            entries.append(_build_cache_entry(recipe, result, starred))

    return entries, buffet_count, seasonal_count, match_stats


def get_starred_source_names() -> set:
    """
    Get the names of starred (favorite) recipe sources.

    Returns a set of source names that are starred in recipe_sources.
    Uses fuzzy matching to handle variations like "ICA" vs "ICA.se".
    """
    starred = set()
    try:
        with get_db_session() as db:
            result = db.execute(text("""
                SELECT name FROM recipe_sources WHERE is_starred = true
            """))
            for row in result:
                # Store lowercase for case-insensitive matching
                starred.add(row.name.lower())
    except Exception as e:
        logger.warning(f"Could not fetch starred sources: {e}")
    return starred


def is_source_starred(source_name: str, starred_sources: set) -> bool:
    """
    Check if a recipe's source is starred.

    Uses fuzzy matching to handle variations like "ICA" vs "ICA.se".
    """
    if not source_name or not starred_sources:
        return False

    source_lower = source_name.lower()

    # Direct match
    if source_lower in starred_sources:
        return True

    # Fuzzy match: check if source contains or is contained by any starred source
    for starred in starred_sources:
        if starred in source_lower or source_lower in starred:
            return True

    return False


class CacheManager:
    """
    Manages the recipe-offer match cache.

    Pre-computes all matches and stores them in the database for fast retrieval.
    """

    CACHE_NAME = 'recipe_offer_matches'

    def __init__(self):
        self.matcher = RecipeMatcher()
        # Cached unmatched offer count (set at cache rebuild, avoids slow JSONB query)
        self._unmatched_count = None
        self._total_offers = None
        self._last_rebuild_profile = {
            "configured_rebuild_mode": OFFICIAL_REBUILD_PROFILE["mode"],
            "effective_rebuild_mode": OFFICIAL_REBUILD_PROFILE["mode"],
            "offer_data_source": OFFICIAL_REBUILD_PROFILE["offer_data_source"],
            "recipe_data_source": OFFICIAL_REBUILD_PROFILE["recipe_data_source"],
            "candidate_data_source": OFFICIAL_REBUILD_PROFILE["candidate_data_source"],
        }

    def get_rebuild_profile(self) -> Dict[str, str]:
        """Return the single supported full-rebuild profile."""
        return dict(OFFICIAL_REBUILD_PROFILE)

    def get_runtime_rebuild_status(self) -> Dict[str, Any]:
        """Return current configured/effective rebuild mode for status endpoints."""
        configured = self.get_rebuild_profile()
        last = self._last_rebuild_profile or configured
        probation_status = get_delta_probation_gate_status()
        ingredient_mode, ingredient_effective_mode, ingredient_fallback_reason, ingredient_probation_status = (
            _resolve_ingredient_routing_mode()
        )
        return {
            "configured_rebuild_mode": configured["mode"],
            "effective_rebuild_mode": last.get("effective_rebuild_mode", configured["mode"]),
            "offer_data_source": last.get("offer_data_source", configured["offer_data_source"]),
            "recipe_data_source": last.get("recipe_data_source", configured["recipe_data_source"]),
            "candidate_data_source": last.get("candidate_data_source", configured["candidate_data_source"]),
            "ingredient_routing_mode": ingredient_mode,
            "ingredient_routing_effective_mode": ingredient_effective_mode,
            "ingredient_routing_fallback_reason": ingredient_fallback_reason,
            **_ingredient_routing_probation_summary_fields(ingredient_probation_status),
            "cache_delta_enabled": settings.cache_delta_enabled,
            "cache_delta_verify_full_preview": settings.cache_delta_verify_full_preview,
            "cache_delta_skip_full_preview_after_probation": settings.cache_delta_skip_full_preview_after_probation,
            "cache_delta_probation_history_file": probation_status["history_file"],
            "cache_delta_probation_ready": probation_status["ready"],
            "cache_delta_probation_reasons": probation_status["reasons"],
            "cache_delta_probation_current_ready_streak": probation_status["summary"]["current_ready_streak"],
            "cache_delta_probation_current_version_ready_run_count": probation_status["summary"]["current_version_ready_run_count"],
            "cache_delta_probation_last_run_at": (
                probation_status["latest_entry"].get("generated_at")
                if probation_status["latest_entry"]
                else None
            ),
            "cache_delta_probation_last_run_ready": (
                probation_status["latest_entry"].get("ready_for_manual_live_apply")
                if probation_status["latest_entry"]
                else None
            ),
            "cache_delta_probation_last_effective_rebuild_mode": (
                probation_status["latest_entry"].get("effective_rebuild_mode")
                if probation_status["latest_entry"]
                else None
            ),
            "cache_delta_probation_last_verification_mode": (
                probation_status["latest_entry"].get("verification_mode")
                if probation_status["latest_entry"]
                else None
            ),
        }

    def update_unmatched_offer_count(self, entries: List[Dict]) -> None:
        """Refresh cached unmatched-offer counters from a set of cache entries."""
        matched_offer_ids = set()
        for entry in entries:
            for offer in entry.get('match_data', {}).get('matched_offers', []):
                oid = _extract_stable_matched_offer_key(offer)
                if oid:
                    matched_offer_ids.add(oid)

        with get_db_session() as db:
            self._total_offers = db.execute(text("SELECT COUNT(*) FROM offers")).scalar() or 0

        self._unmatched_count = max(0, self._total_offers - len(matched_offer_ids))

    def _update_status(self, status: str, error_message: str = None):
        """Update cache metadata status (upserts row if missing)."""
        try:
            with get_db_session() as db:
                db.execute(text("""
                    INSERT INTO cache_metadata (cache_name, status, error_message)
                    VALUES (:name, :status, :error)
                    ON CONFLICT (cache_name) DO UPDATE
                    SET status = :status, error_message = :error
                """), {"status": status, "error": error_message, "name": self.CACHE_NAME})
                db.commit()
        except Exception as e:
            logger.error(f"Failed to update cache status: {e}")

    def _clear_cache_entries(self) -> None:
        """Remove all active cache entries from the DB cache table."""
        try:
            with get_db_session() as db:
                db.execute(text("TRUNCATE recipe_offer_cache"))
                db.commit()
        except Exception as e:
            logger.error(f"Failed to clear recipe cache entries: {e}")
            raise

    def _mark_cache_ready_empty(
        self,
        *,
        time_ms: int = 0,
        total_recipes: int = 0,
        error_message: str = None,
    ) -> None:
        """Persist an intentionally empty but ready cache state."""
        self._clear_cache_entries()
        self._total_offers = 0
        self._unmatched_count = 0

        with get_db_session() as db:
            db.execute(text("""
                INSERT INTO cache_metadata (cache_name, last_computed_at, computation_time_ms,
                    total_recipes, total_matches, status, error_message)
                VALUES (:name, NOW(), :time_ms, :total, 0, 'ready', :error)
                ON CONFLICT (cache_name) DO UPDATE SET
                    last_computed_at = NOW(),
                    computation_time_ms = :time_ms,
                    total_recipes = :total,
                    total_matches = 0,
                    status = 'ready',
                    error_message = :error
            """), {
                "name": self.CACHE_NAME,
                "time_ms": time_ms,
                "total": total_recipes,
                "error": error_message,
            })
            db.commit()
        record_cache_last_operation(
            {
                "cached": 0,
                "total_matches": 0,
                "total_recipes": total_recipes,
                "time_ms": time_ms,
                "status": "ready",
                "error": error_message,
            },
            operation_type="empty_cache",
            status="ready",
        )

    def clear_to_empty(
        self,
        *,
        time_ms: int = 0,
        total_recipes: int = 0,
        error_message: str = None,
    ) -> None:
        """Public entry point for an intentionally empty offer/cache state."""
        logger.info("Clearing recipe cache to an intentionally empty state")
        self._mark_cache_ready_empty(
            time_ms=time_ms,
            total_recipes=total_recipes,
            error_message=error_message,
        )

    def compute_cache(
        self,
        preferences: Optional[Dict] = None,
        *,
        persist: bool = True,
        return_entries: bool = False,
        recipe_ids: Optional[List[str]] = None,
        run_kind: Optional[str] = None,
        input_scope: str = "live",
        fixture_hash: Optional[str] = None,
        max_workers: Optional[int] = None,
        source: Optional[str] = None,
        operation_context: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        """
        Compute recipe-offer matches for all recipes.

        This is the main function called after offers are updated.

        Args:
            preferences: User preferences dict. If None, loads from database.
            persist: When False, compute a preview/parity result without writing
                cache rows or cache metadata back to the database.
            return_entries: Include computed cache entries in the returned payload.
            recipe_ids: Optional subset of recipe ids to rebuild. Used by
                shadow delta tooling to recompute only impacted recipes.
            run_kind: Structured observability label. Defaults to "full" when
                persisting and "shadow_full" in preview mode.
            input_scope: "live" or "fixture" for structured rebuild summaries.
            fixture_hash: Optional frozen fixture hash to attach to rebuild logs.
            max_workers: Optional cap for process-pool workers. Delta verification
                previews use this to reduce peak memory while holding snapshots.
            source: Optional operation source for cache-operation diagnostics.
            operation_context: Optional compact diagnostic fields to attach to
                rebuild summaries and cache-operation history.

        Returns:
            Stats dict: {'total_recipes': N, 'cached': M, 'time_ms': T}
        """
        start_time = time.perf_counter()
        run_kind = run_kind or ("full" if persist else "shadow_full")
        operation_context = dict(operation_context or {})
        configured_rebuild_profile = self.get_rebuild_profile()
        offer_data_source = configured_rebuild_profile["offer_data_source"]
        recipe_data_source = configured_rebuild_profile["recipe_data_source"]
        candidate_data_source = configured_rebuild_profile["candidate_data_source"]
        effective_rebuild_mode = configured_rebuild_profile["mode"]
        ingredient_routing_mode, ingredient_routing_effective_mode, ingredient_routing_fallback_reason, ingredient_probation_status = (
            _resolve_ingredient_routing_mode()
        )
        ingredient_routing_fields = {
            "ingredient_routing_mode": ingredient_routing_mode,
            "ingredient_routing_effective_mode": ingredient_routing_effective_mode,
            "ingredient_routing_fallback_reason": ingredient_routing_fallback_reason,
            **_ingredient_routing_probation_summary_fields(ingredient_probation_status),
        }
        self._last_rebuild_profile = {
            "configured_rebuild_mode": configured_rebuild_profile["mode"],
            "effective_rebuild_mode": effective_rebuild_mode,
            "offer_data_source": offer_data_source,
            "recipe_data_source": recipe_data_source,
            "candidate_data_source": candidate_data_source,
        }
        phase_timings = {
            "compile_ms": 0,
            "route_ms": 0,
            "score_ms": 0,
            "write_ms": 0,
            "ingredient_routing_ms": 0,
        }
        compiled_offer_stats = None
        compiled_recipe_stats = None
        worker_fields = {}
        requested_recipe_ids = {str(recipe_id) for recipe_id in recipe_ids} if recipe_ids is not None else None
        recipe_selection_mode = "not_selected"
        recipe_selection_scope_count = 0
        fts_filtered_count: Optional[int] = None
        logger.info(
            "🔄 Starting cache computation... "
            f"(mode {effective_rebuild_mode}, matcher {MATCHER_VERSION}, "
            f"recipe {RECIPE_COMPILER_VERSION}, offer {OFFER_COMPILER_VERSION})"
        )
        logger.info(
            "  Rebuild profile: "
            f"configured={configured_rebuild_profile['mode']}, "
            f"offer={offer_data_source}, recipe={recipe_data_source}, "
            f"candidates={candidate_data_source}"
        )
        if not persist:
            logger.info("  Running in preview/parity mode (no DB writes)")
        else:
            self._update_status('computing')

        try:
            # Load preferences
            if not preferences:
                preferences = get_effective_matching_preferences()

            # Get enabled recipe sources
            enabled_sources = get_enabled_recipe_sources()

            # Get starred (favorite) recipe sources for ranking boost
            starred_sources = get_starred_source_names()
            if starred_sources:
                logger.info(f"  ⭐ Starred sources: {starred_sources}")

            # Get filtered offers
            offers = self.matcher._get_filtered_offers(preferences)
            logger.info(f"  Found {len(offers)} matching offers")

            if not offers:
                logger.warning("⚠️  No offers found - cache will be empty")
                if persist:
                    self._mark_cache_ready_empty()
                result = {
                    'total_recipes': 0,
                    'cached': 0,
                    'time_ms': 0,
                    'requested_recipe_count': len(requested_recipe_ids or ()),
                    'selected_recipe_count': 0,
                    'recipe_selection_mode': recipe_selection_mode,
                    'recipe_selection_scope_count': recipe_selection_scope_count,
                    'configured_rebuild_mode': configured_rebuild_profile['mode'],
                    'effective_rebuild_mode': effective_rebuild_mode,
                    'matcher_version': MATCHER_VERSION,
                    'recipe_compiler_version': RECIPE_COMPILER_VERSION,
                    'offer_compiler_version': OFFER_COMPILER_VERSION,
                    'offer_data_source': offer_data_source,
                    'recipe_data_source': recipe_data_source,
                    'candidate_data_source': candidate_data_source,
                    'run_kind': run_kind,
                    'source': source,
                    'input_scope': input_scope,
                    'fixture_hash': fixture_hash,
                    'phase_timings_ms': phase_timings,
                    **operation_context,
                    **ingredient_routing_fields,
                }
                _emit_rebuild_summary({
                    'run_kind': run_kind,
                    'source': source,
                    'input_scope': input_scope,
                    'fixture_hash': fixture_hash,
                    'requested_recipe_count': len(requested_recipe_ids or ()),
                    'selected_recipe_count': 0,
                    'recipe_selection_mode': recipe_selection_mode,
                    'recipe_selection_scope_count': recipe_selection_scope_count,
                    'configured_rebuild_mode': configured_rebuild_profile['mode'],
                    'effective_rebuild_mode': effective_rebuild_mode,
                    'matcher_version': MATCHER_VERSION,
                    'recipe_compiler_version': RECIPE_COMPILER_VERSION,
                    'offer_compiler_version': OFFER_COMPILER_VERSION,
                    'offer_data_source': offer_data_source,
                    'recipe_data_source': recipe_data_source,
                    'candidate_data_source': candidate_data_source,
                    **operation_context,
                    **ingredient_routing_fields,
                    'phase_timings_ms': phase_timings,
                    'total_recipes': 0,
                    'cached': 0,
                    'total_offers': 0,
                    'matched_offer_ids': 0,
                    'unmatched_offer_ids': 0,
                    'buffet_filtered': 0,
                    'seasonal_filtered': 0,
                    'status': 'ready',
                    'time_ms': 0,
                })
                if return_entries:
                    result['entries'] = []
                return result

            def _load_compiled_offer_cache_with_refresh():
                try:
                    return load_compiled_offer_runtime_cache(offers)
                except RuntimeError as exc:
                    logger.warning(f"  Compiled offer IR unavailable ({exc}); refreshing and retrying...")
                    refresh_result = refresh_compiled_offer_match_data()
                    cache, stats = load_compiled_offer_runtime_cache(offers)
                    stats = dict(stats)
                    stats["refreshed"] = True
                    stats["refresh_result"] = refresh_result
                    return cache, stats

            def _load_compiled_recipe_payload_with_refresh():
                try:
                    return load_compiled_recipe_payload_cache(all_recipes)
                except RuntimeError as exc:
                    logger.warning(f"  Compiled recipe payload IR unavailable ({exc}); refreshing and retrying...")
                    refresh_result = refresh_compiled_recipe_match_data()
                    cache, stats = load_compiled_recipe_payload_cache(all_recipes)
                    stats = dict(stats)
                    stats["refreshed"] = True
                    stats["refresh_result"] = refresh_result
                    return cache, stats

            def _load_compiled_term_postings_with_refresh():
                current_offer_identity_keys = _select_indexable_offer_identity_keys(
                    offers,
                    offer_data_cache,
                )
                current_recipe_ids = {str(recipe.id) for recipe in all_recipes}

                def _offer_cache_ready() -> bool:
                    if not isinstance(compiled_offer_stats, dict):
                        return False
                    return (
                        not compiled_offer_stats.get("missing_offer_ids")
                        and not compiled_offer_stats.get("stale_offer_ids")
                    )

                def _recipe_cache_ready() -> bool:
                    if not isinstance(compiled_recipe_stats, dict):
                        return False
                    return (
                        not compiled_recipe_stats.get("missing_recipe_ids")
                        and not compiled_recipe_stats.get("stale_recipe_ids")
                        and not compiled_recipe_stats.get("inactive_recipe_ids")
                    )

                def _load_postings():
                    offer_postings, offer_stats = load_compiled_offer_term_postings()
                    term_manifest_hash = offer_stats.get("term_manifest_hash")
                    if not offer_stats.get("loaded_rows") or not term_manifest_hash:
                        raise RuntimeError("compiled_offer_term_index is empty or missing manifest hash")

                    recipe_postings, recipe_stats = load_compiled_recipe_term_postings(
                        term_manifest_hash=term_manifest_hash,
                    )
                    if not recipe_stats.get("loaded_rows"):
                        raise RuntimeError("compiled_recipe_term_index is empty for current term manifest")

                    filtered_offer_postings = {}
                    indexed_offer_keys = set()
                    for term, indexed_offer_ids in offer_postings.items():
                        keep = indexed_offer_ids & current_offer_identity_keys
                        if keep:
                            filtered_offer_postings[term] = keep
                            indexed_offer_keys.update(keep)

                    missing_offer_keys = current_offer_identity_keys - indexed_offer_keys
                    if current_offer_identity_keys and missing_offer_keys:
                        raise RuntimeError(
                            "compiled_offer_term_index is stale for current offers: "
                            f"missing={len(missing_offer_keys)}"
                        )

                    filtered_recipe_postings = {}
                    for term, indexed_recipe_ids in recipe_postings.items():
                        keep = indexed_recipe_ids & current_recipe_ids
                        if keep:
                            filtered_recipe_postings[term] = keep

                    return filtered_offer_postings, filtered_recipe_postings, offer_stats, recipe_stats

                try:
                    return _load_postings()
                except RuntimeError as exc:
                    logger.warning(f"  Compiled term index unavailable ({exc}); refreshing and retrying...")
                    compiled_offer_refresh = None
                    compiled_recipe_refresh = None

                    if not _offer_cache_ready():
                        compiled_offer_refresh = refresh_compiled_offer_match_data()
                    if not _recipe_cache_ready():
                        compiled_recipe_refresh = refresh_compiled_recipe_match_data()

                    offer_term_refresh = refresh_compiled_offer_term_index()
                    recipe_term_refresh = refresh_compiled_recipe_term_index()
                    filtered_offer_postings, filtered_recipe_postings, offer_stats, recipe_stats = _load_postings()
                    offer_stats = dict(offer_stats)
                    recipe_stats = dict(recipe_stats)
                    offer_stats["refreshed"] = True
                    offer_stats["refresh_result"] = {
                        "compiled_offer_refresh": compiled_offer_refresh,
                        "offer_term_refresh": offer_term_refresh,
                    }
                    recipe_stats["refreshed"] = True
                    recipe_stats["refresh_result"] = {
                        "compiled_recipe_refresh": compiled_recipe_refresh,
                        "recipe_term_refresh": recipe_term_refresh,
                    }
                    return filtered_offer_postings, filtered_recipe_postings, offer_stats, recipe_stats

            compile_phase_start = time.perf_counter()
            offer_data_cache, compiled_offer_stats = _load_compiled_offer_cache_with_refresh()
            phase_timings["compile_ms"] += int((time.perf_counter() - compile_phase_start) * 1000)
            logger.info(
                "  Loaded compiled offer IR "
                f"({compiled_offer_stats['loaded']}/{len(offers)} offers, "
                f"version {compiled_offer_stats['compiler_version']})"
            )
            # Matcher-compatible keyword map used by the hot matching path.
            offer_keywords = {
                oid: data['keywords'] for oid, data in offer_data_cache.items()
            }

            # Get total recipe counts first (for stats) — non-excluded only.
            with get_db_session() as db:
                base_filter = (FoundRecipe.excluded == False) | (FoundRecipe.excluded.is_(None))  # noqa: E712
                total_in_db = db.query(FoundRecipe).filter(
                    base_filter
                ).count()
                eligible_query = db.query(FoundRecipe).filter(base_filter)
                if enabled_sources:
                    eligible_query = eligible_query.filter(FoundRecipe.source_name.in_(enabled_sources))
                total_eligible_in_db = eligible_query.count()

            def _load_active_recipe_scope() -> list[FoundRecipe]:
                with get_db_session() as db:
                    base_filter = (FoundRecipe.excluded == False) | (FoundRecipe.excluded.is_(None))  # noqa: E712
                    query = db.query(FoundRecipe).filter(base_filter)
                    if enabled_sources:
                        query = query.filter(FoundRecipe.source_name.in_(enabled_sources))
                    return query.all()

            # Get recipes. Explicit recipe IDs use a direct DB path. The
            # term-index cache profile deliberately uses the full active recipe
            # scope and lets persisted term postings decide the routed pairs.
            # Always exclude hidden recipes.
            if requested_recipe_ids is not None:
                if requested_recipe_ids:
                    with get_db_session() as db:
                        base_filter = (FoundRecipe.excluded == False) | (FoundRecipe.excluded.is_(None))  # noqa: E712
                        filters = [
                            FoundRecipe.id.in_(list(requested_recipe_ids)),
                            base_filter,
                        ]
                        if enabled_sources:
                            filters.append(FoundRecipe.source_name.in_(enabled_sources))
                        all_recipes = db.query(FoundRecipe).filter(*filters).all()
                else:
                    all_recipes = []
                logger.info(
                    "  Direct recipe subset: "
                    f"{len(all_recipes)}/{len(requested_recipe_ids)} requested ids selected"
                )
                recipe_selection_mode = "direct_subset"
                recipe_selection_scope_count = len(requested_recipe_ids)
            elif candidate_data_source == "term_index":
                all_recipes = _load_active_recipe_scope()
                recipe_selection_mode = "term_index_full_scope"
                recipe_selection_scope_count = total_eligible_in_db
                logger.info(
                    "  Loaded active recipe scope for term-index routing: "
                    f"{len(all_recipes)}/{total_eligible_in_db} recipes selected"
                )
            elif self.matcher.USE_FTS:
                all_keywords = build_fts_keyword_set(offer_data_cache)
                if all_keywords:
                    all_recipes = self.matcher._get_recipes_by_fts(list(all_keywords), enabled_sources)
                    recipe_selection_mode = "fts_prefilter"
                    recipe_selection_scope_count = total_eligible_in_db
                    fts_filtered_count = max(0, total_eligible_in_db - len(all_recipes))
                    logger.info(
                        "  FTS pre-filter: "
                        f"{len(all_recipes)}/{total_eligible_in_db} recipes match offer keywords"
                    )
                else:
                    all_recipes = _load_active_recipe_scope()
                    recipe_selection_mode = "full_scope_no_fts"
                    recipe_selection_scope_count = total_eligible_in_db
                    logger.info(f"  Loaded {len(all_recipes)} recipes (no FTS keywords)")
            else:
                all_recipes = _load_active_recipe_scope()
                recipe_selection_mode = "full_scope_no_fts"
                recipe_selection_scope_count = total_eligible_in_db
                logger.info(f"  Loaded {len(all_recipes)} recipes (no FTS)")

            logger.info(
                "  Recipe selection: "
                f"mode={recipe_selection_mode}, scope={len(all_recipes)}/"
                f"{recipe_selection_scope_count}"
            )
            logger.info(f"  Processing {len(all_recipes)} candidate recipes...")

            compile_phase_start = time.perf_counter()
            compiled_recipe_payload_cache, compiled_recipe_stats = _load_compiled_recipe_payload_with_refresh()
            phase_timings["compile_ms"] += int((time.perf_counter() - compile_phase_start) * 1000)
            logger.info(
                "  Loaded compiled recipe payload IR "
                f"({compiled_recipe_stats['loaded']}/{len(all_recipes)} recipes, "
                f"version {compiled_recipe_stats['compiler_version']})"
            )

            route_phase_start = time.perf_counter()
            offer_term_postings, recipe_term_postings, offer_term_stats, recipe_term_stats = (
                _load_compiled_term_postings_with_refresh()
            )
            relevant_offer_ids_by_recipe = build_candidate_map_from_term_postings(
                recipe_term_postings,
                offer_term_postings,
            )
            candidate_term_detail_by_recipe = build_candidate_term_detail_from_term_postings(
                recipe_term_postings,
                offer_term_postings,
            )
            collapsed_candidate_term_detail = {
                recipe_id: set(offer_terms)
                for recipe_id, offer_terms in candidate_term_detail_by_recipe.items()
            }
            if collapsed_candidate_term_detail != relevant_offer_ids_by_recipe:
                raise RuntimeError(
                    "candidate term detail does not collapse to current candidate map"
                )
            offer_lookup = {build_offer_identity_key(offer): offer for offer in offers}
            route_details = {
                "compiled_offer_term_stats": offer_term_stats,
                "compiled_recipe_term_stats": recipe_term_stats,
                "route_keyword_count": len(offer_term_postings),
                "offer_recipe_term_pair_count": sum(
                    len(terms)
                    for offer_terms in candidate_term_detail_by_recipe.values()
                    for terms in offer_terms.values()
                ),
            }

            # Pre-build filtered offer lists per recipe (avoids iterating all offers)
            recipe_index_by_id = {str(recipe.id): idx for idx, recipe in enumerate(all_recipes)}
            recipe_relevant_offers = {}
            for recipe_id, relevant_ids in relevant_offer_ids_by_recipe.items():
                recipe_index = recipe_index_by_id.get(str(recipe_id))
                if recipe_index is None:
                    continue
                filtered_offers = [
                    offer_lookup[offer_id]
                    for offer_id in sorted(relevant_ids)
                    if offer_id in offer_lookup
                ]
                if filtered_offers:
                    recipe_relevant_offers[recipe_index] = filtered_offers

            total_pairs = sum(len(v) for v in recipe_relevant_offers.values())
            route_details["offer_recipe_pair_count"] = total_pairs
            phase_timings["route_ms"] = int((time.perf_counter() - route_phase_start) * 1000)
            logger.info(
                f"  Candidate routing ({candidate_data_source}): "
                f"{route_details.get('route_keyword_count', 0)} terms, "
                f"{total_pairs} offer-recipe pairs "
                f"(vs {len(all_recipes) * len(offers):,} brute force)"
            )

            ingredient_candidate_indices_by_recipe: Dict[int, Dict[str, set[int]]] = {}
            if ingredient_routing_effective_mode == "hint_first":
                logger.info("  Ingredient routing hint_first mode: building ingredient hint maps")
                ingredient_routing_start = time.perf_counter()
                ingredient_candidate_indices_by_recipe, hint_map_details = (
                    _build_ingredient_candidate_indices_by_recipe(
                        recipes=all_recipes,
                        candidate_term_detail_by_recipe=candidate_term_detail_by_recipe,
                        compiled_recipe_payload_cache=compiled_recipe_payload_cache,
                        recipe_index_by_id=recipe_index_by_id,
                    )
                )
                phase_timings["ingredient_routing_ms"] = int(
                    (time.perf_counter() - ingredient_routing_start) * 1000
                )
                ingredient_routing_fields.update(hint_map_details)
                logger.info(
                    "  Ingredient routing hint maps: "
                    f"{hint_map_details.get('estimated_hinted_ingredient_checks', 0)} "
                    "hinted checks vs "
                    f"{hint_map_details.get('estimated_fullscan_ingredient_checks', 0)} "
                    "fullscan checks"
                )

            if ingredient_routing_effective_mode in {"shadow", "probation"}:
                logger.info(
                    f"  Ingredient routing {ingredient_routing_effective_mode} mode: "
                    "measuring hints beside fullscan"
                )
                ingredient_routing_start = time.perf_counter()
                ingredient_routing_details = _measure_ingredient_routing_shadow(
                    recipes=all_recipes,
                    candidate_term_detail_by_recipe=candidate_term_detail_by_recipe,
                    offer_lookup=offer_lookup,
                    offer_keywords=offer_keywords,
                    offer_data_cache=offer_data_cache,
                    compiled_recipe_payload_cache=compiled_recipe_payload_cache,
                )
                phase_timings["ingredient_routing_ms"] = int(
                    (time.perf_counter() - ingredient_routing_start) * 1000
                )
                ingredient_routing_fields.update(ingredient_routing_details)
                logger.info(
                    "  Ingredient routing shadow: "
                    f"{ingredient_routing_details.get('shadow_pair_count', 0)} pairs, "
                    f"{ingredient_routing_details.get('shadow_candidate_change_count', 0)} "
                    "candidate changes, "
                    f"{ingredient_routing_details.get('shadow_unexplained_miss_count', 0)} "
                    "unexplained"
                )

            # Compute matches for each recipe
            num_cores = os.cpu_count() or 1
            num_workers = max(1, num_cores - 1)
            configured_max_workers = max(1, settings.cache_rebuild_max_workers)
            num_workers = min(num_workers, configured_max_workers)
            if max_workers is not None:
                num_workers = max(1, min(num_workers, max_workers))
            use_parallel = num_workers > 1 and len(all_recipes) >= MIN_RECIPES_FOR_PARALLEL
            worker_fields = {
                "cache_rebuild_detected_cores": num_cores,
                "cache_rebuild_max_workers": configured_max_workers,
                "cache_rebuild_call_max_workers": max_workers,
                "cache_rebuild_worker_count": num_workers,
            }

            cache_entries = []
            total_matches = 0
            buffet_filtered = 0
            seasonal_filtered = 0
            match_stats = _empty_worker_match_stats()

            # Split recipe indices into chunks for workers
            recipe_indices = list(range(len(all_recipes)))
            chunk_size = max(1, (len(recipe_indices) + num_workers - 1) // num_workers)
            chunks = [recipe_indices[j:j + chunk_size] for j in range(0, len(recipe_indices), chunk_size)]

            if use_parallel:
                logger.info(f"  Using {num_workers} worker processes ({num_cores} cores detected)")

                # Set shared data (inherited via fork copy-on-write)
                global _shared
                _shared = {
                    'matcher': self.matcher,
                    'all_recipes': all_recipes,
                    'recipe_relevant_offers': recipe_relevant_offers,
                    'preferences': preferences,
                    'offer_keywords': offer_keywords,
                    'offer_data_cache': offer_data_cache,
                    'compiled_recipe_payload_cache': compiled_recipe_payload_cache,
                    'starred_sources': starred_sources,
                    'ingredient_candidate_indices_by_recipe': ingredient_candidate_indices_by_recipe,
                    'ingredient_routing_effective_mode': ingredient_routing_effective_mode,
                }

                try:
                    score_phase_start = time.perf_counter()
                    import multiprocessing
                    ctx = multiprocessing.get_context('fork')
                    with ProcessPoolExecutor(max_workers=num_workers, mp_context=ctx) as executor:
                        results = list(executor.map(_match_recipe_batch, chunks))

                    for entries, buffet_count, seasonal_count, worker_match_stats in results:
                        cache_entries.extend(entries)
                        total_matches += len(entries)
                        buffet_filtered += buffet_count
                        seasonal_filtered += seasonal_count
                        _merge_worker_match_stats(match_stats, worker_match_stats)
                    phase_timings["score_ms"] = int((time.perf_counter() - score_phase_start) * 1000)

                except Exception as e:
                    logger.warning(f"  Parallel matching failed ({e}), falling back to single-threaded")
                    use_parallel = False
                    cache_entries = []
                    total_matches = 0
                    buffet_filtered = 0
                    seasonal_filtered = 0
                    match_stats = _empty_worker_match_stats()
                finally:
                    _shared = {}

            if not use_parallel:
                # Single-threaded fallback (1 core or parallel failed)
                logger.info(f"  Single-threaded mode ({num_cores} core{'s' if num_cores > 1 else ''} detected)")

                # Set shared data for the worker function (same struct, no fork)
                _shared.update({
                    'matcher': self.matcher,
                    'all_recipes': all_recipes,
                    'recipe_relevant_offers': recipe_relevant_offers,
                    'preferences': preferences,
                    'offer_keywords': offer_keywords,
                    'offer_data_cache': offer_data_cache,
                    'compiled_recipe_payload_cache': compiled_recipe_payload_cache,
                    'starred_sources': starred_sources,
                    'ingredient_candidate_indices_by_recipe': ingredient_candidate_indices_by_recipe,
                    'ingredient_routing_effective_mode': ingredient_routing_effective_mode,
                })
                try:
                    score_phase_start = time.perf_counter()
                    entries, buffet_filtered, seasonal_filtered, match_stats = _match_recipe_batch(recipe_indices)
                    cache_entries = entries
                    total_matches = len(entries)
                    phase_timings["score_ms"] = int((time.perf_counter() - score_phase_start) * 1000)
                finally:
                    _shared.clear()

            if ingredient_routing_effective_mode == "hint_first":
                fullscan_check_baseline = ingredient_routing_fields.get(
                    "estimated_fullscan_ingredient_checks",
                    0,
                )
                actual_check_count = match_stats.get("ingredient_check_count", 0)
                ingredient_routing_fields.update({
                    "ingredient_check_count": actual_check_count,
                    "hinted_check_count": match_stats.get("hinted_check_count", 0),
                    "hinted_no_match_count": match_stats.get("hinted_no_match_count", 0),
                    "fullscan_fallback_count": match_stats.get("fullscan_fallback_count", 0),
                    "fullscan_fallback_reason_counts": dict(sorted(
                        (match_stats.get("fullscan_fallback_reason_counts") or {}).items()
                    )),
                    "actual_ingredient_check_reduction_pct": (
                        round((1 - (actual_check_count / fullscan_check_baseline)) * 100, 2)
                        if fullscan_check_baseline else 0
                    ),
                })

            # Calculate stats
            candidates = len(all_recipes) - buffet_filtered
            no_match_count = candidates - total_matches
            match_pct = (total_matches / candidates * 100) if candidates > 0 else 0

            logger.info("  📊 Cache stats:")
            logger.info(f"     Total recipes in DB: {total_in_db} (non-excluded)")
            logger.info(
                "     Recipe selection: "
                f"{recipe_selection_mode} ({len(all_recipes)}/{recipe_selection_scope_count})"
            )
            if recipe_selection_mode == "fts_prefilter":
                logger.info(
                    f"     FTS pre-filtered: {fts_filtered_count} "
                    "(no matching offer keywords)"
                )
            logger.info(f"     Buffet/party filtered: {buffet_filtered}")
            logger.info(f"     Seasonal cached: {seasonal_filtered}")
            logger.info(f"     Candidates: {candidates}")
            logger.info(f"     Matched offers: {total_matches} ({match_pct:.0f}%)")
            logger.info(f"     No matches: {no_match_count}")

            # Count unique matched offer IDs (for fast unmatched count endpoint)
            matched_offer_ids = set()
            for entry in cache_entries:
                for offer in entry['match_data'].get('matched_offers', []):
                    oid = _extract_stable_matched_offer_key(offer)
                    if oid:
                        matched_offer_ids.add(oid)

            with get_db_session() as db:
                self._total_offers = db.execute(text("SELECT COUNT(*) FROM offers")).scalar() or 0
            self._unmatched_count = max(0, self._total_offers - len(matched_offer_ids))
            logger.info(f"     Matched offer IDs: {len(matched_offer_ids)}/{self._total_offers} (unmatched: {self._unmatched_count})")

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            if persist:
                # Bulk insert into cache
                write_phase_start = time.perf_counter()
                self._save_cache(cache_entries)
                phase_timings["write_ms"] += int((time.perf_counter() - write_phase_start) * 1000)

                # Update metadata
                write_phase_start = time.perf_counter()
                with get_db_session() as db:
                    db.execute(text("""
                        INSERT INTO cache_metadata (cache_name, last_computed_at, computation_time_ms,
                            total_recipes, total_matches, status, error_message)
                        VALUES (:name, NOW(), :time_ms, :total, :matches, 'ready', NULL)
                        ON CONFLICT (cache_name) DO UPDATE SET
                            last_computed_at = NOW(),
                            computation_time_ms = :time_ms,
                            total_recipes = :total,
                            total_matches = :matches,
                            status = 'ready',
                            error_message = NULL
                    """), {
                        "time_ms": elapsed_ms,
                        "total": len(all_recipes),
                        "matches": total_matches,
                        "name": self.CACHE_NAME
                    })
                    db.commit()
                phase_timings["write_ms"] += int((time.perf_counter() - write_phase_start) * 1000)

                logger.success(f"✅ Cache computed: {total_matches} recipes in {elapsed_ms}ms")
            else:
                logger.success(f"✅ Cache preview computed: {total_matches} recipes in {elapsed_ms}ms")

            result = {
                'total_recipes': len(all_recipes),
                'cached': total_matches,
                'time_ms': elapsed_ms,
                'requested_recipe_count': len(requested_recipe_ids or ()),
                'selected_recipe_count': len(all_recipes),
                'recipe_selection_mode': recipe_selection_mode,
                'recipe_selection_scope_count': recipe_selection_scope_count,
                'fts_filtered_count': fts_filtered_count,
                'configured_rebuild_mode': configured_rebuild_profile['mode'],
                'effective_rebuild_mode': effective_rebuild_mode,
                'matcher_version': MATCHER_VERSION,
                'recipe_compiler_version': RECIPE_COMPILER_VERSION,
                'offer_compiler_version': OFFER_COMPILER_VERSION,
                'offer_data_source': offer_data_source,
                'recipe_data_source': recipe_data_source,
                'candidate_data_source': candidate_data_source,
                'run_kind': run_kind,
                'source': source,
                'input_scope': input_scope,
                'fixture_hash': fixture_hash,
                'phase_timings_ms': phase_timings,
                **operation_context,
                **worker_fields,
                **ingredient_routing_fields,
            }
            if compiled_offer_stats is not None:
                result['compiled_offer_stats'] = compiled_offer_stats
            if compiled_recipe_stats is not None:
                result['compiled_recipe_stats'] = compiled_recipe_stats
            if route_details:
                result.update(route_details)
            if return_entries:
                result['entries'] = cache_entries
            if (
                ingredient_routing_effective_mode == "probation"
                and ingredient_routing_fields.get("ingredient_routing_shadow_measured") is True
            ):
                append_ingredient_routing_probation_history(result)
                ingredient_probation_status = get_ingredient_routing_probation_gate_status()
                ingredient_routing_fields.update(
                    _ingredient_routing_probation_summary_fields(ingredient_probation_status)
                )
                ingredient_routing_fields["cache_ingredient_routing_probation_appended"] = True
                result.update(ingredient_routing_fields)
            ingredient_routing_summary_fields = {
                key: value
                for key, value in ingredient_routing_fields.items()
                if key != "shadow_samples_by_class"
            }
            if persist:
                record_cache_last_operation(
                    {
                        **result,
                        "total_matches": total_matches,
                        "matched_offer_ids": len(matched_offer_ids),
                        "total_offers": len(offers),
                        "unmatched_offer_ids": self._unmatched_count,
                        "status": "ready",
                    },
                    operation_type="full_rebuild",
                    status="ready",
                    source=source,
                )
            _emit_rebuild_summary({
                'run_kind': run_kind,
                'source': source,
                'input_scope': input_scope,
                'fixture_hash': fixture_hash,
                'requested_recipe_count': len(requested_recipe_ids or ()),
                'selected_recipe_count': len(all_recipes),
                'recipe_selection_mode': recipe_selection_mode,
                'recipe_selection_scope_count': recipe_selection_scope_count,
                'fts_filtered_count': fts_filtered_count,
                'configured_rebuild_mode': configured_rebuild_profile['mode'],
                'effective_rebuild_mode': effective_rebuild_mode,
                'matcher_version': MATCHER_VERSION,
                'recipe_compiler_version': RECIPE_COMPILER_VERSION,
                'offer_compiler_version': OFFER_COMPILER_VERSION,
                'offer_data_source': offer_data_source,
                'recipe_data_source': recipe_data_source,
                'candidate_data_source': candidate_data_source,
                **operation_context,
                **ingredient_routing_summary_fields,
                **worker_fields,
                'phase_timings_ms': phase_timings,
                'total_recipes': len(all_recipes),
                'cached': total_matches,
                'total_offers': len(offers),
                'matched_offer_ids': len(matched_offer_ids),
                'unmatched_offer_ids': self._unmatched_count,
                'buffet_filtered': buffet_filtered,
                'seasonal_filtered': seasonal_filtered,
                **route_details,
                'status': 'ready',
                'time_ms': elapsed_ms,
            })
            return result

        except Exception as e:
            logger.error(f"❌ Cache computation failed: {e}")
            _emit_rebuild_summary({
                'run_kind': run_kind,
                'source': source,
                'input_scope': input_scope,
                'fixture_hash': fixture_hash,
                'requested_recipe_count': len(requested_recipe_ids or ()),
                'recipe_selection_mode': recipe_selection_mode,
                'recipe_selection_scope_count': recipe_selection_scope_count,
                'fts_filtered_count': fts_filtered_count,
                'configured_rebuild_mode': configured_rebuild_profile['mode'],
                'effective_rebuild_mode': effective_rebuild_mode,
                'matcher_version': MATCHER_VERSION,
                'recipe_compiler_version': RECIPE_COMPILER_VERSION,
                'offer_compiler_version': OFFER_COMPILER_VERSION,
                'offer_data_source': offer_data_source,
                'recipe_data_source': recipe_data_source,
                'candidate_data_source': candidate_data_source,
                **operation_context,
                **ingredient_routing_fields,
                **worker_fields,
                'phase_timings_ms': phase_timings,
                'status': 'error',
                'error': str(e),
                'time_ms': int((time.perf_counter() - start_time) * 1000),
            }, level="error")
            if persist:
                self._update_status('error', str(e))
                record_cache_last_operation(
                    {
                        "run_kind": run_kind,
                        "source": source,
                        "input_scope": input_scope,
                        "fixture_hash": fixture_hash,
                        "requested_recipe_count": len(requested_recipe_ids or ()),
                        "recipe_selection_mode": recipe_selection_mode,
                        "recipe_selection_scope_count": recipe_selection_scope_count,
                        "fts_filtered_count": fts_filtered_count,
                        "configured_rebuild_mode": configured_rebuild_profile['mode'],
                        "effective_rebuild_mode": effective_rebuild_mode,
                        "matcher_version": MATCHER_VERSION,
                        "recipe_compiler_version": RECIPE_COMPILER_VERSION,
                        "offer_compiler_version": OFFER_COMPILER_VERSION,
                        "offer_data_source": offer_data_source,
                        "recipe_data_source": recipe_data_source,
                        "candidate_data_source": candidate_data_source,
                        **ingredient_routing_fields,
                        **worker_fields,
                        **operation_context,
                        "status": "error",
                        "error": str(e),
                        "time_ms": int((time.perf_counter() - start_time) * 1000),
                    },
                    operation_type="full_rebuild",
                    status="error",
                    source=source,
                )
            raise

    def _save_cache(self, entries: List[Dict]):
        """Save cache entries to the database."""
        if not entries:
            self._clear_cache_entries()
            return

        self._save_cache_to_db(entries)

    def _save_cache_to_db(self, entries: List[Dict]):
        """Save cache entries to the database.

        Uses COPY in batches for bulk insert (~3-5x faster than execute_values).
        Batching keeps memory usage bounded even with 13k+ entries.
        """
        from io import StringIO
        from datetime import datetime, timezone

        BATCH_SIZE = 2000
        logger.info(f"  Saving {len(entries)} cache entries to DB (COPY)...")
        now = datetime.now(timezone.utc).isoformat()

        copy_sql = (
            "COPY recipe_offer_cache "
            "(found_recipe_id, recipe_category, budget_score, "
            "total_savings, coverage_pct, num_matches, "
            "is_starred, match_data, computed_at) "
            "FROM STDIN WITH (FORMAT text)"
        )

        raw_conn = engine.raw_connection()
        try:
            cursor = raw_conn.cursor()
            # TRUNCATE + COPY in same transaction — if COPY fails,
            # old data is preserved (rollback restores the TRUNCATE).
            # TRUNCATE is faster than DELETE and prevents TOAST bloat
            # from accumulating across weekly rebuilds.
            cursor.execute("TRUNCATE recipe_offer_cache")

            for i in range(0, len(entries), BATCH_SIZE):
                batch = entries[i:i + BATCH_SIZE]
                buf = StringIO()
                for e in batch:
                    row = '\t'.join([
                        e['found_recipe_id'],
                        e['recipe_category'],
                        str(e['budget_score']),
                        str(e['total_savings']),
                        str(e['coverage_pct']),
                        str(e['num_matches']),
                        't' if e['is_starred'] else 'f',
                        json.dumps(e['match_data']).replace('\\', '\\\\'),
                        now,
                    ])
                    buf.write(row)
                    buf.write('\n')
                buf.seek(0)
                cursor.copy_expert(copy_sql, buf)
                del buf, batch

            # Commit everything at once — DELETE + all COPYs
            raw_conn.commit()
        except Exception:
            raw_conn.rollback()
            raise
        finally:
            raw_conn.close()

        logger.info(f"  ✓ Saved {len(entries)} cache entries to DB")

    def get_cached_recipes(
        self,
        preferences: Optional[Dict] = None,
        max_results: int = 20,
        exclude_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Get recipes from cache using non-destructive pagination.

        Client sends exclude_ids (already shown recipes) to avoid duplicates.
        """
        if not preferences:
            preferences = get_effective_matching_preferences()

        # Check cache status (metadata always in DB)
        with get_db_session() as db:
            status = db.execute(text(
                "SELECT status FROM cache_metadata WHERE cache_name = :name"
            ), {"name": self.CACHE_NAME}).scalar()
            if not status or status not in ('ready', 'computing'):
                logger.warning("Cache not ready - falling back to live computation")
                return None

        exclude_set = set(exclude_ids) if exclude_ids else set()

        return self._get_from_db(preferences, max_results, exclude_set)

    def _db_cache_row_to_frontend(self, row, fetch_category: str, display_category: Optional[str] = None) -> Dict:
        """Convert a joined recipe_offer_cache/found_recipes row to frontend-ready dict."""
        match_data = row.match_data if isinstance(row.match_data, dict) else json.loads(row.match_data)
        return {
            'id': str(row.found_recipe_id),
            'name': row.name,
            'url': row.url,
            'source': row.source_name,
            'image_url': row.local_image_path or row.image_url,
            'prep_time_minutes': row.prep_time_minutes,
            'ingredients': row.ingredients or [],
            'servings': row.servings,
            'category': display_category or row.recipe_category,
            'match_score': match_data.get('match_score', 0),
            'total_savings': float(row.total_savings or 0),
            'num_matches': row.num_matches,
            'num_offers': match_data.get('num_offers', 0),
            'matched_offers': match_data.get('matched_offers', []),
            'coverage_pct': float(row.coverage_pct or 0),
            'budget_score': float(row.budget_score or 0),
            'ingredient_groups': match_data.get('ingredient_groups', []),
            'total_savings_pct': match_data.get('total_savings_pct', 0),
            'avg_savings_pct': match_data.get('avg_savings_pct', 0),
            '_fetch_cat': fetch_category
        }

    def _get_from_db(self, preferences: Dict, max_results: int, exclude_set: set) -> List[Dict]:
        """Serve recipes from the DB cache."""
        balance = preferences.get('balance', {
            MEAT: 0.25, FISH: 0.25, VEGETARIAN: 0.25, 'smart_buy': 0.25
        })
        exclude_categories = preferences.get('exclude_categories', [])
        exclude_cats_sql = []
        if any(cat in exclude_categories for cat in [MEAT, POULTRY, DELI]):
            exclude_cats_sql.append(MEAT)
        if FISH in exclude_categories:
            exclude_cats_sql.append(FISH)

        exclude_ids_list = list(exclude_set) if exclude_set else []

        # Build base WHERE clause for exclude_ids and ingredient count.
        # The count query and fetch queries must agree so the fetch plan is
        # based on the same eligible recipe set that the DB fallback can return.
        exclude_clause = ""
        base_params = {}
        if exclude_ids_list:
            exclude_clause = " AND c.found_recipe_id != ALL(CAST(:exclude_ids AS uuid[]))"
            base_params["exclude_ids"] = exclude_ids_list

        min_ing = preferences.get('min_ingredients', 0)
        max_ing = preferences.get('max_ingredients', 0)
        ing_clause = ""
        if min_ing > 0:
            ing_clause += " AND jsonb_array_length(r.ingredients) >= :min_ing"
            base_params["min_ing"] = min_ing
        if max_ing > 0:
            ing_clause += " AND jsonb_array_length(r.ingredients) <= :max_ing"
            base_params["max_ing"] = max_ing

        with get_db_session() as db:
            count_categories = [cat for cat in [MEAT, FISH, VEGETARIAN] if cat not in exclude_cats_sql]
            cat_counts = {cat: 0 for cat in count_categories}
            if count_categories:
                category_params = {
                    f"count_cat_{i}": cat
                    for i, cat in enumerate(count_categories)
                }
                category_placeholders = ", ".join(f":count_cat_{i}" for i in range(len(count_categories)))
                count_params = {**base_params, **category_params}
                rows = db.execute(text(f"""
                    SELECT c.recipe_category, COUNT(*) AS recipe_count
                    FROM recipe_offer_cache c
                    JOIN found_recipes r ON c.found_recipe_id = r.id
                    WHERE c.recipe_category IN ({category_placeholders})
                      AND (r.excluded = FALSE OR r.excluded IS NULL){exclude_clause}{ing_clause}
                    GROUP BY c.recipe_category
                """), count_params).fetchall()
                for row in rows:
                    cat_counts[row.recipe_category] = row.recipe_count or 0

            fetch_plan = self._calculate_fetch_plan(balance, cat_counts, max_results, exclude_cats_sql)
            all_recipes = []

            # smart_buy
            num_budget = fetch_plan.get('smart_buy', 0)
            if num_budget > 0:
                cat_clause = ""
                overfetch_limit = max(num_budget * 4, num_budget + 24)
                params = {**base_params, "limit": overfetch_limit}
                if exclude_cats_sql:
                    cat_clause = " AND c.recipe_category != ALL(:exclude_cats)"
                    params["exclude_cats"] = list(exclude_cats_sql)

                rows = db.execute(text(f"""
                    SELECT c.*, r.name, r.url, r.source_name,
                           r.image_url, r.local_image_path, r.prep_time_minutes, r.ingredients, r.servings
                    FROM recipe_offer_cache c JOIN found_recipes r ON c.found_recipe_id = r.id
                    WHERE (r.excluded = FALSE OR r.excluded IS NULL){cat_clause}{exclude_clause}{ing_clause}
                    ORDER BY c.budget_score DESC, c.is_starred DESC LIMIT :limit
                """), params).fetchall()

                added = 0
                for row in rows:
                    if is_off_season_recipe(row.name):
                        continue
                    all_recipes.append(self._db_cache_row_to_frontend(row, 'smart_buy', 'smart_buy'))
                    added += 1
                    if added >= num_budget:
                        break

            picked_ids = set(r['id'] for r in all_recipes)
            ranking_mode = preferences.get('ranking_mode', 'absolute')
            for cat in [MEAT, FISH, VEGETARIAN]:
                num_to_fetch = fetch_plan.get(cat, 0)
                if num_to_fetch <= 0 or cat in exclude_cats_sql:
                    continue

                all_exclude = list(exclude_set | picked_ids)
                overfetch_limit = max(num_to_fetch * 4, num_to_fetch + 24)
                params = {"cat": cat, "limit": overfetch_limit}
                if min_ing > 0:
                    params["min_ing"] = min_ing
                if max_ing > 0:
                    params["max_ing"] = max_ing
                picked_clause = ""
                if all_exclude:
                    picked_clause = " AND c.found_recipe_id != ALL(CAST(:all_exclude AS uuid[]))"
                    params["all_exclude"] = all_exclude

                if ranking_mode == 'percentage':
                    order_clause = "ORDER BY (c.match_data->>'total_savings_pct')::numeric DESC NULLS LAST, c.is_starred DESC"
                else:
                    order_clause = "ORDER BY c.total_savings DESC, c.is_starred DESC"
                rows = db.execute(text(f"""
                    SELECT c.*, r.name, r.url, r.source_name,
                           r.image_url, r.local_image_path, r.prep_time_minutes, r.ingredients, r.servings
                    FROM recipe_offer_cache c JOIN found_recipes r ON c.found_recipe_id = r.id
                    WHERE c.recipe_category = :cat
                      AND (r.excluded = FALSE OR r.excluded IS NULL){picked_clause}{ing_clause}
                    {order_clause} LIMIT :limit
                """), params).fetchall()

                added = 0
                for row in rows:
                    if is_off_season_recipe(row.name):
                        continue
                    recipe = self._db_cache_row_to_frontend(row, cat)
                    all_recipes.append(recipe)
                    recipe_id = recipe['id']
                    picked_ids.add(recipe_id)
                    added += 1
                    if added >= num_to_fetch:
                        break

            result = self._interleave_categories(all_recipes, fetch_plan)
            actual_counts = {}
            for r in result:
                cat = r.get('_fetch_cat', r['category'])
                actual_counts[cat] = actual_counts.get(cat, 0) + 1
            logger.info(f"✅ Returned {len(result)} recipes from DB cache (excluded {len(exclude_set)})")
            logger.info(f"   Counts: {actual_counts}")
            return result

    def _calculate_fetch_plan(
        self,
        balance: Dict,
        cat_counts: Dict,
        total_needed: int,
        exclude_cats: List[str]
    ) -> Dict[str, int]:
        """
        Calculate how many recipes to fetch from each category.
        """
        # Get active categories (weight > 0)
        active_cats = []
        for cat in [MEAT, FISH, VEGETARIAN, 'smart_buy']:
            if cat in exclude_cats:
                continue
            weight = balance.get(cat, 0.25)
            if weight >= 0.01:  # At least 1%
                active_cats.append((cat, weight))

        if not active_cats:
            # Fallback to all categories
            active_cats = [(MEAT, 0.25), (FISH, 0.25), (VEGETARIAN, 0.25), ('smart_buy', 0.25)]

        # Normalize weights
        total_weight = sum(w for _, w in active_cats)
        normalized = [(cat, w / total_weight) for cat, w in active_cats]

        # Calculate fetch counts
        fetch_plan = {}
        remaining = total_needed

        for cat, weight in normalized:
            count = int(total_needed * weight)
            fetch_plan[cat] = count
            remaining -= count

        # Distribute remainder using largest fractional part
        # Tie-break: prefer category with higher original weight
        if remaining > 0 and normalized:
            fractional = [(cat, (total_needed * w) - int(total_needed * w), w) for cat, w in normalized]
            fractional.sort(key=lambda x: (x[1], x[2]), reverse=True)
            for i in range(remaining):
                cat = fractional[i % len(fractional)][0]
                fetch_plan[cat] = fetch_plan.get(cat, 0) + 1

        # Fairness fix: equal-weight categories should get equal counts.
        # If 3+ categories share the same weight but got unequal counts,
        # move the excess to the highest-weight category instead.
        weight_groups = {}
        for cat, w in active_cats:
            weight_groups.setdefault(w, []).append(cat)

        for w, group in weight_groups.items():
            if len(group) < 3:
                continue
            min_count = min(fetch_plan.get(c, 0) for c in group)
            excess = 0
            for c in group:
                excess += fetch_plan[c] - min_count
                fetch_plan[c] = min_count
            if excess > 0:
                highest_cat = max(normalized, key=lambda x: x[1])[0]
                fetch_plan[highest_cat] += excess

        return fetch_plan

    def _interleave_categories(self, recipes: List[Dict], fetch_plan: Dict) -> List[Dict]:
        """
        Interleave recipes from different categories for nicer display.
        """
        # Group by fetch category
        by_cat = {cat: [] for cat in fetch_plan.keys()}
        for recipe in recipes:
            cat = recipe.get('_fetch_cat', recipe['category'])
            if cat in by_cat:
                by_cat[cat].append(recipe)

        # Interleave: take 1 from each category in rotation
        result = []
        indices = {cat: 0 for cat in by_cat}

        while len(result) < len(recipes):
            added = False
            for cat in [MEAT, FISH, VEGETARIAN, 'smart_buy']:
                if cat not in by_cat:
                    continue
                idx = indices[cat]
                if idx < len(by_cat[cat]):
                    result.append(by_cat[cat][idx])
                    indices[cat] += 1
                    added = True
            if not added:
                break

        return result

    def is_cache_valid(self) -> bool:
        """
        Check if cache is ready and valid.

        Uses stale-while-revalidate: returns True if status is 'ready' OR 'computing'.
        This allows requests to use old cache data while a new cache is being built.
        """
        try:
            with get_db_session() as db:
                status = db.execute(text("""
                    SELECT status FROM cache_metadata
                    WHERE cache_name = :name
                """), {"name": self.CACHE_NAME}).scalar()
                # Stale-while-revalidate: use old cache during rebuild
                return status in ('ready', 'computing')
        except Exception as e:
            logger.debug(f"Cache validity check failed: {e}")
            return False

    def invalidate(self):
        """
        Invalidate the cache.

        Call this when recipe sources are enabled/disabled to force
        recomputation with the correct sources on next request.
        """
        logger.info("Invalidating recipe cache...")
        self._update_status('pending')

    def refresh_cache(
        self,
        preferences: Optional[Dict] = None,
        *,
        persist: bool = True,
        return_entries: bool = False,
        recipe_ids: Optional[List[str]] = None,
        run_kind: Optional[str] = None,
        input_scope: str = "live",
        fixture_hash: Optional[str] = None,
        max_workers: Optional[int] = None,
        source: Optional[str] = None,
        operation_context: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        """Run cache rebuild using the single supported compiled profile."""
        return self.compute_cache(
            preferences,
            persist=persist,
            return_entries=return_entries,
            recipe_ids=recipe_ids,
            run_kind=run_kind,
            input_scope=input_scope,
            fixture_hash=fixture_hash,
            max_workers=max_workers,
            source=source,
            operation_context=operation_context,
        )

    def reset_cache(self) -> Dict:
        """
        Reset the cache by recomputing all matches.

        Use this when:
        - User wants to start over (go back to page 1)
        - Cache has been depleted by destructive pagination

        Returns:
            Stats dict from compute_cache()
        """
        logger.info("🔄 Resetting recipe cache (rebuilding from scratch)...")
        return self.refresh_cache()

    def update_starred_for_source(self, source_name: str, is_starred: bool) -> int:
        """
        Update is_starred flag for all cache entries from a specific source.
        """
        try:
            with get_db_session() as db:
                result = db.execute(text("""
                    UPDATE recipe_offer_cache c
                    SET is_starred = :starred
                    FROM found_recipes r
                    WHERE c.found_recipe_id = r.id
                      AND (
                          LOWER(r.source_name) = LOWER(:source_name)
                          OR LOWER(r.source_name) LIKE '%' || LOWER(:source_name) || '%'
                          OR LOWER(:source_name) LIKE '%' || LOWER(r.source_name) || '%'
                      )
                """), {"starred": is_starred, "source_name": source_name})
                db.commit()
                updated_count = result.rowcount
        except Exception as e:
            logger.error(f"Failed to update starred status for '{source_name}': {e}")
            return 0

        logger.info(f"⭐ Updated is_starred={is_starred} for {updated_count} entries from '{source_name}'")
        return updated_count

    def get_matched_offer_ids(self) -> set:
        """Get all unique stable offer identifiers from the cache."""
        with get_db_session() as db:
            result = db.execute(text("""
                SELECT DISTINCT offer_key::text FROM (
                    SELECT COALESCE(mo->>'offer_identity_key', mo->>'id') AS offer_key
                    FROM recipe_offer_cache c,
                         jsonb_array_elements(c.match_data->'matched_offers') mo
                ) sub
            """))
            return {row[0] for row in result}


# Lock to prevent concurrent cache writers/previews inside this process.
_cache_operation_lock = Lock()
_cache_rebuild_in_progress = False
_cache_operation_name: Optional[str] = None


def run_cache_operation(
    operation_name: str,
    operation: Callable[[], Dict[str, Any]],
    *,
    skip_if_busy: bool = True,
) -> Dict[str, Any]:
    """Run one cache operation at a time inside this Python process."""
    global _cache_rebuild_in_progress, _cache_operation_name

    acquired = _cache_operation_lock.acquire(blocking=not skip_if_busy)
    if not acquired:
        active = _cache_operation_name or "unknown"
        logger.info(
            f"Cache operation '{active}' already in progress, "
            f"skipping '{operation_name}'"
        )
        return {
            "skipped": True,
            "success": False,
            "applied": False,
            "reason": "already_computing",
            "fallback_reason": "cache_operation_in_progress",
            "active_operation": active,
        }

    _cache_rebuild_in_progress = True
    _cache_operation_name = operation_name
    try:
        logger.info(f"Starting cache operation '{operation_name}'")
        return operation()
    finally:
        _cache_operation_name = None
        _cache_rebuild_in_progress = False
        _cache_operation_lock.release()


def refresh_cache_locked(
    preferences: Optional[Dict] = None,
    *,
    skip_if_busy: bool = True,
    run_kind: Optional[str] = None,
    source: Optional[str] = None,
    operation_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Refresh the global cache through the shared cache operation lock."""
    return run_cache_operation(
        "full_rebuild",
        lambda: cache_manager.refresh_cache(
            preferences,
            run_kind=run_kind,
            source=source,
            operation_context=operation_context,
        ),
        skip_if_busy=skip_if_busy,
    )


async def compute_cache_async(
    preferences: Optional[Dict] = None,
    *,
    skip_if_busy: bool = True,
    run_kind: Optional[str] = None,
    source: Optional[str] = None,
    operation_context: Optional[Dict[str, Any]] = None,
) -> Dict:
    """
    Async wrapper for cache computation.

    Use this after offers are updated to refresh the cache.
    Only one cache operation can run at a time. Concurrent calls are skipped by
    default, but callers can opt to wait for the active operation to finish.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: refresh_cache_locked(
            preferences,
            skip_if_busy=skip_if_busy,
            run_kind=run_kind,
            source=source,
            operation_context=operation_context,
        ),
    )


# Global instance for convenience
cache_manager = CacheManager()


# ============================================================================
# CLI INTERFACE
# ============================================================================

if __name__ == "__main__":
    import argparse
    from rich.console import Console

    console = Console()

    parser = argparse.ArgumentParser(description='Recipe Cache Manager')
    parser.add_argument('--compute', action='store_true', help='Compute/refresh cache')
    parser.add_argument('--status', action='store_true', help='Show cache status')
    parser.add_argument('--test', action='store_true', help='Test cache retrieval')

    args = parser.parse_args()

    if args.status:
        runtime_status = cache_manager.get_runtime_rebuild_status()
        with get_db_session() as db:
            result = db.execute(text("""
                SELECT * FROM cache_metadata WHERE cache_name = 'recipe_offer_matches'
            """)).fetchone()

            if result:
                console.print("\n[bold blue]📦 Cache Status[/bold blue]\n")
                console.print(f"  Status: {result.status}")
                console.print(
                    "  Rebuild mode: "
                    f"{runtime_status['effective_rebuild_mode']} "
                    f"(configured: {runtime_status['configured_rebuild_mode']})"
                )
                console.print(
                    "  Sources: "
                    f"{runtime_status['offer_data_source']} / "
                    f"{runtime_status['recipe_data_source']} / "
                    f"{runtime_status['candidate_data_source']}"
                )
                console.print(f"  Last computed: {result.last_computed_at}")
                console.print(f"  Computation time: {result.computation_time_ms}ms")
                console.print(f"  Total recipes: {result.total_recipes}")
                console.print(f"  Cached matches: {result.total_matches}")
                if result.error_message:
                    console.print(f"  [red]Error: {result.error_message}[/red]")
            else:
                console.print("[yellow]Cache metadata not found[/yellow]")

    elif args.compute:
        console.print("\n[bold blue]🔄 Computing cache...[/bold blue]\n")

        manager = CacheManager()
        result = manager.refresh_cache()

        console.print("\n[green]✅ Done![/green]")
        console.print(f"  Total recipes: {result['total_recipes']}")
        console.print(f"  Cached: {result['cached']}")
        console.print(f"  Time: {result['time_ms']}ms")

    elif args.test:
        console.print("\n[bold blue]🧪 Testing cache retrieval...[/bold blue]\n")

        import time
        manager = CacheManager()

        start = time.perf_counter()
        recipes = manager.get_cached_recipes(max_results=20)
        elapsed = time.perf_counter() - start

        if recipes:
            console.print(f"[green]✅ Got {len(recipes)} recipes in {elapsed*1000:.0f}ms[/green]\n")

            for i, r in enumerate(recipes[:5]):
                console.print(f"  {i+1}. [{r['category']}] {r['name'][:50]}...")
                console.print(f"     Savings: {r['total_savings']:.0f} kr, Matches: {r['num_matches']}")
        else:
            console.print("[yellow]Cache not ready - run with --compute first[/yellow]")

    else:
        parser.print_help()
