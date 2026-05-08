"""Stable offer-diff decisions for store-triggered cache refreshes."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Literal

from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

try:
    from config import settings
except ModuleNotFoundError:
    from app.config import settings

try:
    from database import get_db_session
except ModuleNotFoundError:
    from app.database import get_db_session

try:
    from models import FoundRecipe, Offer
except ModuleNotFoundError:
    from app.models import FoundRecipe, Offer

try:
    from languages.matcher_runtime import (
        MATCHER_VERSION,
        OFFER_COMPILER_VERSION,
        RECIPE_COMPILER_VERSION,
        classify_current_offer_changes,
        classify_current_recipe_changes,
        load_persisted_offer_recipe_map,
        build_offer_candidate_terms,
        build_offer_identity_key,
        load_compiled_offer_match_map,
        plan_combined_delta_recipe_impacts,
        plan_offer_delta_recipe_impacts,
        precompute_offer_data,
    )
except ModuleNotFoundError:
    from app.languages.matcher_runtime import (
        MATCHER_VERSION,
        OFFER_COMPILER_VERSION,
        RECIPE_COMPILER_VERSION,
        classify_current_offer_changes,
        classify_current_recipe_changes,
        load_persisted_offer_recipe_map,
        build_offer_candidate_terms,
        build_offer_identity_key,
        load_compiled_offer_match_map,
        plan_combined_delta_recipe_impacts,
        plan_offer_delta_recipe_impacts,
        precompute_offer_data,
    )


Strategy = Literal["skip", "delta", "full"]


@dataclass(frozen=True)
class OfferCacheStatusSnapshot:
    status: str | None
    metadata_total_matches: int | None
    metadata_total_recipes: int | None
    cache_rows: int
    offer_rows: int
    compiled_offer_baseline_committed: bool
    last_operation: dict[str, Any] = field(default_factory=dict)
    baseline_column_available: bool = True


@dataclass(frozen=True)
class OfferRefreshMetrics:
    store_name: str | None
    offer_replaces_all: bool
    current_offer_count: int
    persisted_offer_count: int
    changed_offer_count: int
    changed_offer_ratio_pct: float
    impacted_recipe_count: int | None
    active_recipe_count: int
    impacted_recipe_ratio_pct: float | None
    early_full_triggered: bool
    offer_changes: dict[str, Any] = field(default_factory=dict)
    recipe_changes: dict[str, Any] = field(default_factory=dict)
    combined_planner_counts: dict[str, Any] = field(default_factory=dict)
    changed_offer_sample: list[dict[str, Any]] = field(default_factory=list)
    offer_change_counts: dict[str, Any] = field(default_factory=dict)
    impact_mode: str | None = None
    planner_time_ms: int | None = None


@dataclass(frozen=True)
class OfferCacheRefreshDecision:
    strategy: Strategy
    reason: str
    store_name: str | None
    offer_replaces_all: bool
    current_offer_count: int
    persisted_offer_count: int
    changed_offer_count: int
    changed_offer_ratio_pct: float
    impacted_recipe_count: int | None
    active_recipe_count: int
    impacted_recipe_ratio_pct: float | None
    offer_delta_impacted_recipe_ratio_full_threshold_pct: float
    offer_delta_changed_offer_ratio_early_full_threshold_pct: float
    early_full_triggered: bool = False
    cache_status: str | None = None
    cache_rows: int | None = None
    metadata_total_matches: int | None = None
    compiled_offer_baseline_committed: bool = True
    planner_time_ms: int | None = None
    recipe_change_counts: dict[str, Any] = field(default_factory=dict)
    combined_planner_counts: dict[str, Any] = field(default_factory=dict)
    changed_offer_sample: list[dict[str, Any]] = field(default_factory=list)
    offer_change_counts: dict[str, Any] = field(default_factory=dict)
    impact_mode: str | None = None

    def to_operation_context(self) -> dict[str, Any]:
        """Return compact fields for cache operation history."""
        context: dict[str, Any] = {
            "offer_refresh_strategy": self.strategy,
            "offer_refresh_reason": self.reason,
            "offer_replaces_all": self.offer_replaces_all,
            "current_offer_count": self.current_offer_count,
            "persisted_offer_count": self.persisted_offer_count,
            "changed_offer_count": self.changed_offer_count,
            "changed_offer_ratio_pct": self.changed_offer_ratio_pct,
            "active_recipe_count": self.active_recipe_count,
            "offer_delta_impacted_recipe_ratio_full_threshold_pct": (
                self.offer_delta_impacted_recipe_ratio_full_threshold_pct
            ),
            "offer_delta_changed_offer_ratio_early_full_threshold_pct": (
                self.offer_delta_changed_offer_ratio_early_full_threshold_pct
            ),
            "offer_refresh_early_full_triggered": self.early_full_triggered,
            "compiled_offer_baseline_committed": self.compiled_offer_baseline_committed,
        }
        if self.impacted_recipe_count is not None:
            context["impacted_recipe_count"] = self.impacted_recipe_count
        if self.impacted_recipe_ratio_pct is not None:
            context["impacted_recipe_ratio_pct"] = self.impacted_recipe_ratio_pct
        if self.planner_time_ms is not None:
            context["offer_delta_planner_time_ms"] = self.planner_time_ms
        if self.impact_mode:
            context["offer_delta_impact_mode"] = self.impact_mode
        if self.offer_change_counts:
            context["offer_change_counts"] = self.offer_change_counts
        if self.combined_planner_counts:
            context["combined_planner_counts"] = self.combined_planner_counts
        if self.changed_offer_sample:
            context["changed_offer_sample"] = self.changed_offer_sample
        return context

    def log(self) -> None:
        impact = (
            f"{self.impacted_recipe_count}/{self.active_recipe_count}"
            if self.impacted_recipe_count is not None
            else f"?/{self.active_recipe_count}"
        )
        impact_ratio = (
            f"{self.impacted_recipe_ratio_pct:.2f}%"
            if self.impacted_recipe_ratio_pct is not None
            else "n/a"
        )
        logger.info(
            "Offer cache decision ({store}): {strategy} reason={reason} "
            "changed_offers={changed}/{denom} changed_ratio={changed_ratio:.2f}% "
            "impacted_recipes={impact} impact_ratio={impact_ratio}",
            store=self.store_name or "unknown",
            strategy=self.strategy,
            reason=self.reason,
            changed=self.changed_offer_count,
            denom=max(self.current_offer_count, self.persisted_offer_count),
            changed_ratio=self.changed_offer_ratio_pct,
            impact=impact,
            impact_ratio=impact_ratio,
        )


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 4)


def _changed_offer_ids(offer_changes: dict[str, Any]) -> set[str]:
    keys = (
        "added_offer_ids",
        "removed_offer_ids",
        "match_changed_offer_ids",
        "score_changed_offer_ids",
        "display_changed_offer_ids",
        "version_mismatch_offer_ids",
    )
    result: set[str] = set()
    for key in keys:
        result.update(str(value) for value in offer_changes.get(key, ()) if value is not None)
    return result


def _as_display_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _compact_identity(value: str) -> str:
    return value if len(value) <= 80 else value[:77] + "..."


def _current_offer_details(offer: Offer | None) -> dict[str, Any]:
    if offer is None:
        return {}
    return {
        "name": offer.name,
        "brand": offer.brand,
        "category": offer.category,
        "price": _as_display_value(offer.price),
        "original_price": _as_display_value(offer.original_price),
        "product_url": offer.product_url,
    }


def _persisted_offer_details(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "name": row.get("source_name"),
        "brand": row.get("source_brand"),
        "category": row.get("source_category"),
        "price": _as_display_value(row.get("source_price")),
        "original_price": _as_display_value(row.get("source_original_price")),
        "product_url": row.get("source_product_url"),
    }


def _build_changed_offer_sample(
    offer_changes: dict[str, Any],
    offers: list[Offer],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return a compact human-readable sample of changed stable offers."""
    if not _changed_offer_ids(offer_changes):
        return []

    current_by_key = {build_offer_identity_key(offer): offer for offer in offers}
    persisted_by_key = load_compiled_offer_match_map()
    buckets = (
        ("added", "added_offer_ids"),
        ("removed", "removed_offer_ids"),
        ("match_changed", "match_changed_offer_ids"),
        ("score_changed", "score_changed_offer_ids"),
        ("display_changed", "display_changed_offer_ids"),
        ("version_mismatch", "version_mismatch_offer_ids"),
    )

    sample: list[dict[str, Any]] = []
    for kind, key in buckets:
        for offer_identity_key in sorted(str(value) for value in offer_changes.get(key, ())):
            current = _current_offer_details(current_by_key.get(offer_identity_key))
            previous = _persisted_offer_details(persisted_by_key.get(offer_identity_key))
            details = current or previous
            item: dict[str, Any] = {
                "kind": kind,
                "identity_key": _compact_identity(offer_identity_key),
                "name": details.get("name"),
                "brand": details.get("brand"),
                "category": details.get("category"),
            }
            if current.get("price") or previous.get("price"):
                item["price"] = current.get("price")
                item["previous_price"] = previous.get("price")
            if current.get("product_url") or previous.get("product_url"):
                item["product_url"] = current.get("product_url") or previous.get("product_url")
            sample.append({k: v for k, v in item.items() if v is not None})
            if len(sample) >= limit:
                return sample
    return sample


def load_offer_cache_status_snapshot() -> OfferCacheStatusSnapshot:
    """Read the small cache status snapshot needed before offer decisions."""
    baseline_column_available = True
    with get_db_session() as db:
        try:
            metadata = db.execute(text("""
                SELECT
                    status,
                    total_matches,
                    total_recipes,
                    last_operation,
                    compiled_offer_baseline_committed
                FROM cache_metadata
                WHERE cache_name = 'recipe_offer_matches'
            """)).mappings().fetchone()
        except SQLAlchemyError:
            baseline_column_available = False
            metadata = db.execute(text("""
                SELECT status, total_matches, total_recipes, last_operation
                FROM cache_metadata
                WHERE cache_name = 'recipe_offer_matches'
            """)).mappings().fetchone()
        cache_rows = db.execute(text("SELECT COUNT(*) FROM recipe_offer_cache")).scalar() or 0
        offer_rows = db.execute(text("SELECT COUNT(*) FROM offers")).scalar() or 0

    last_operation = metadata["last_operation"] if metadata else {}
    if not isinstance(last_operation, dict):
        last_operation = {}
    committed = True
    if metadata and baseline_column_available:
        committed = bool(metadata["compiled_offer_baseline_committed"])
    elif not baseline_column_available:
        committed = False
    return OfferCacheStatusSnapshot(
        status=metadata["status"] if metadata else None,
        metadata_total_matches=metadata["total_matches"] if metadata else None,
        metadata_total_recipes=metadata["total_recipes"] if metadata else None,
        cache_rows=int(cache_rows),
        offer_rows=int(offer_rows),
        compiled_offer_baseline_committed=committed,
        last_operation=last_operation,
        baseline_column_available=baseline_column_available,
    )


def active_recipe_count_from_db() -> int:
    with get_db_session() as db:
        return db.execute(text("""
            SELECT COUNT(*)
            FROM found_recipes
            WHERE excluded = FALSE OR excluded IS NULL
        """)).scalar() or 0


def _load_current_offers() -> list[Offer]:
    with get_db_session() as db:
        return db.query(Offer).order_by(Offer.id).all()


def _load_active_recipes() -> list[FoundRecipe]:
    with get_db_session() as db:
        active_recipe_filter = (
            (FoundRecipe.excluded == False) | (FoundRecipe.excluded.is_(None))  # noqa: E712
        )
        return db.query(FoundRecipe).filter(active_recipe_filter).order_by(FoundRecipe.id).all()


def _offer_terms_for_current_offers(offers_by_key: dict[str, Offer], offer_ids: set[str]) -> set[str]:
    terms: set[str] = set()
    for offer_identity_key in offer_ids:
        offer = offers_by_key.get(offer_identity_key)
        if offer is None:
            continue
        compiled_offer_data = precompute_offer_data(
            offer.name,
            offer.category or "",
            brand=offer.brand or "",
            weight_grams=float(offer.weight_grams) if offer.weight_grams is not None else None,
        )
        terms.update(term for term, _term_type in build_offer_candidate_terms(compiled_offer_data))
    return terms


def _persisted_offer_terms_for_ids(offer_ids: set[str]) -> set[str]:
    if not offer_ids:
        return set()
    with get_db_session() as db:
        rows = db.execute(
            text("""
                SELECT DISTINCT term
                FROM compiled_offer_term_index
                WHERE matcher_version = :matcher_version
                  AND offer_compiler_version = :offer_compiler_version
                  AND offer_identity_key = ANY(CAST(:offer_ids AS text[]))
            """),
            {
                "matcher_version": MATCHER_VERSION,
                "offer_compiler_version": OFFER_COMPILER_VERSION,
                "offer_ids": sorted(offer_ids),
            },
        ).fetchall()
    return {str(row.term) for row in rows if row.term}


def _persisted_offer_index_terms_for_terms(terms: set[str]) -> set[str]:
    if not terms:
        return set()
    with get_db_session() as db:
        rows = db.execute(
            text("""
                SELECT DISTINCT term
                FROM compiled_offer_term_index
                WHERE matcher_version = :matcher_version
                  AND offer_compiler_version = :offer_compiler_version
                  AND term = ANY(CAST(:terms AS text[]))
            """),
            {
                "matcher_version": MATCHER_VERSION,
                "offer_compiler_version": OFFER_COMPILER_VERSION,
                "terms": sorted(terms),
            },
        ).fetchall()
    return {str(row.term) for row in rows if row.term}


def _recipe_ids_for_terms(terms: set[str]) -> set[str]:
    if not terms:
        return set()
    with get_db_session() as db:
        rows = db.execute(
            text("""
                SELECT DISTINCT found_recipe_id::text AS found_recipe_id
                FROM compiled_recipe_term_index
                WHERE matcher_version = :matcher_version
                  AND recipe_compiler_version = :recipe_compiler_version
                  AND term = ANY(CAST(:terms AS text[]))
            """),
            {
                "matcher_version": MATCHER_VERSION,
                "recipe_compiler_version": RECIPE_COMPILER_VERSION,
                "terms": sorted(terms),
            },
        ).fetchall()
    return {str(row.found_recipe_id) for row in rows}


def _recipe_ids_for_cached_offer_ids(offer_ids: set[str]) -> set[str]:
    if not offer_ids:
        return set()
    with get_db_session() as db:
        rows = db.execute(
            text("""
                SELECT DISTINCT roc.found_recipe_id::text AS found_recipe_id
                FROM recipe_offer_cache roc
                WHERE EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(roc.match_data->'matched_offers') AS offer_data
                    WHERE offer_data->>'offer_identity_key' = ANY(CAST(:offer_ids AS text[]))
                )
            """),
            {"offer_ids": sorted(offer_ids)},
        ).fetchall()
    return {str(row.found_recipe_id) for row in rows}


def _estimate_offer_impact_fast(
    offer_changes: dict[str, Any],
    offers: list[Offer],
    *,
    active_recipe_count: int,
) -> tuple[int, float, dict[str, Any], str]:
    """Estimate offer impact using targeted SQL instead of full planner materialization."""
    offers_by_key = {build_offer_identity_key(offer): offer for offer in offers}
    added_offer_ids = set(str(value) for value in offer_changes.get("added_offer_ids", ()))
    removed_offer_ids = set(str(value) for value in offer_changes.get("removed_offer_ids", ()))
    match_changed_offer_ids = set(str(value) for value in offer_changes.get("match_changed_offer_ids", ()))
    semantic_offer_ids = added_offer_ids | match_changed_offer_ids
    forced_version_offer_ids = set(str(value) for value in offer_changes.get("forced_version_rematch_offer_ids", ()))
    rematch_offer_ids = semantic_offer_ids | forced_version_offer_ids
    rescore_offer_ids = set(str(value) for value in offer_changes.get("rescore_offer_ids", ()))
    display_offer_ids = set(str(value) for value in offer_changes.get("display_only_offer_ids", ()))

    current_rematch_terms = _offer_terms_for_current_offers(offers_by_key, rematch_offer_ids)
    persisted_rematch_terms = _persisted_offer_terms_for_ids(rematch_offer_ids)
    indexed_current_terms = _persisted_offer_index_terms_for_terms(current_rematch_terms)
    unknown_current_terms = current_rematch_terms - indexed_current_terms

    if unknown_current_terms:
        counts = {
            "impact_mode": "fast_unknown_current_terms_full",
            "unknown_current_terms": len(unknown_current_terms),
            "unknown_current_terms_sample": sorted(unknown_current_terms)[:10],
            "rematch_offer_ids": len(rematch_offer_ids),
            "removed_offer_ids": len(removed_offer_ids),
            "rescore_offer_ids": len(rescore_offer_ids),
            "display_only_offer_ids": len(display_offer_ids),
            "all_impacted_recipes": active_recipe_count,
        }
        return active_recipe_count, 100.0 if active_recipe_count else 0.0, counts, "fast_unknown_current_terms_full"

    rematch_recipe_ids = _recipe_ids_for_terms(current_rematch_terms | persisted_rematch_terms)
    removed_recipe_ids = _recipe_ids_for_cached_offer_ids(removed_offer_ids)
    cached_recipe_ids = _recipe_ids_for_cached_offer_ids(rescore_offer_ids | display_offer_ids)
    impacted_recipe_ids = rematch_recipe_ids | removed_recipe_ids | cached_recipe_ids
    impacted_recipe_count = len(impacted_recipe_ids)
    counts = {
        "impact_mode": "fast_sql",
        "rematch_offer_ids": len(rematch_offer_ids),
        "removed_offer_ids": len(removed_offer_ids),
        "rescore_offer_ids": len(rescore_offer_ids),
        "display_only_offer_ids": len(display_offer_ids),
        "rematch_terms": len(current_rematch_terms | persisted_rematch_terms),
        "rematch_recipes": len(rematch_recipe_ids),
        "removed_offer_recipes": len(removed_recipe_ids),
        "cached_offer_recipes": len(cached_recipe_ids),
        "all_impacted_recipes": impacted_recipe_count,
    }
    return impacted_recipe_count, _pct(impacted_recipe_count, active_recipe_count), counts, "fast_sql"


def _estimate_offer_impact_with_full_planner(
    offer_changes: dict[str, Any],
    offers: list[Offer],
    recipes: list[FoundRecipe],
    recipe_changes: dict[str, Any],
    *,
    active_recipe_count: int,
) -> tuple[int, float, dict[str, Any], str]:
    """Fallback to the exact planner if the fast path cannot be used."""
    # Import private cache-delta helpers lazily to avoid a module-level cycle.
    try:
        from cache_delta import (
            _build_current_offer_term_postings,
            _load_or_build_delta_term_postings,
            _plan_delta_patch_recipe_ids,
        )
    except ModuleNotFoundError:
        from app.cache_delta import (
            _build_current_offer_term_postings,
            _load_or_build_delta_term_postings,
            _plan_delta_patch_recipe_ids,
        )

    current_offer_term_postings = _build_current_offer_term_postings(offers)
    (
        persisted_offer_term_postings,
        _offer_term_stats,
        current_recipe_term_postings,
        _current_recipe_term_stats,
        persisted_recipe_term_postings,
        _persisted_recipe_term_stats,
    ) = _load_or_build_delta_term_postings(
        recipes=recipes,
        current_offer_term_postings=current_offer_term_postings,
    )
    persisted_offer_recipe_map = load_persisted_offer_recipe_map()
    offer_planner = plan_offer_delta_recipe_impacts(
        offer_changes,
        current_offer_term_postings=current_offer_term_postings,
        persisted_offer_term_postings=persisted_offer_term_postings,
        current_recipe_term_postings=current_recipe_term_postings,
        persisted_recipe_term_postings=persisted_recipe_term_postings,
        persisted_offer_recipe_map=persisted_offer_recipe_map,
    )
    combined_planner = plan_combined_delta_recipe_impacts(offer_planner, recipe_changes)
    patch_recipe_ids = sorted(
        set(combined_planner.get("rematch_recipe_ids", ()))
        | set(combined_planner.get("effective_rescore_recipe_ids", ()))
        | set(combined_planner.get("effective_display_only_recipe_ids", ()))
    )
    counts = dict(combined_planner.get("counts", {}))
    counts["impact_mode"] = "exact_planner"
    return len(patch_recipe_ids), _pct(len(patch_recipe_ids), active_recipe_count), counts, "exact_planner"


def build_offer_refresh_metrics(
    *,
    store_name: str | None = None,
    offer_replaces_all: bool = True,
) -> OfferRefreshMetrics:
    """Build stable offer-diff and, when useful, recipe-impact metrics."""
    started_at = time.perf_counter()
    offers = _load_current_offers()
    active_recipe_count = active_recipe_count_from_db()

    offer_changes = classify_current_offer_changes(offers)
    changed_offer_sample = _build_changed_offer_sample(offer_changes, offers)
    recipe_changes: dict[str, Any] = {"counts": {}}
    current_offer_count = int(offer_changes.get("current_offer_count") or len(offers))
    persisted_offer_count = int(offer_changes.get("persisted_offer_count") or 0)
    changed_offer_count = len(_changed_offer_ids(offer_changes))
    changed_offer_ratio_pct = _pct(
        changed_offer_count,
        max(current_offer_count, persisted_offer_count),
    )

    early_threshold = float(settings.offer_delta_changed_offer_ratio_early_full_threshold_pct)
    offer_ratio_above_threshold = (
        changed_offer_count > 0
        and changed_offer_ratio_pct > early_threshold
    )
    early_full_triggered = False

    impacted_recipe_count: int | None = None
    impacted_recipe_ratio_pct: float | None = None
    combined_planner_counts: dict[str, Any] = {}
    impact_mode: str | None = None

    if changed_offer_count:
        try:
            (
                impacted_recipe_count,
                impacted_recipe_ratio_pct,
                combined_planner_counts,
                impact_mode,
            ) = _estimate_offer_impact_fast(
                offer_changes,
                offers,
                active_recipe_count=active_recipe_count,
            )
        except Exception as exc:
            if offer_ratio_above_threshold:
                logger.warning(
                    "Fast offer-impact estimate failed ({}) and changed-offer ratio is "
                    "above threshold; choosing full rebuild without exact planner",
                    exc,
                )
                impacted_recipe_count = active_recipe_count
                impacted_recipe_ratio_pct = 100.0 if active_recipe_count else 0.0
                impact_mode = "fast_estimate_failed_ratio_full"
                early_full_triggered = True
                combined_planner_counts = {
                    "impact_mode": impact_mode,
                    "fast_estimate_error": str(exc),
                    "all_impacted_recipes": impacted_recipe_count,
                }
            else:
                logger.warning(
                    "Fast offer-impact estimate failed ({}); falling back to exact planner",
                    exc,
                )
                recipes = _load_active_recipes()
                recipe_changes = classify_current_recipe_changes(recipes)
                if recipe_changes.get("all_impacted_recipe_ids"):
                    impacted_recipe_count = len(set(recipe_changes.get("all_impacted_recipe_ids") or []))
                    impacted_recipe_ratio_pct = _pct(impacted_recipe_count, active_recipe_count)
                    impact_mode = "recipe_changes_detected"
                else:
                    (
                        impacted_recipe_count,
                        impacted_recipe_ratio_pct,
                        combined_planner_counts,
                        impact_mode,
                    ) = _estimate_offer_impact_with_full_planner(
                        offer_changes,
                        offers,
                        recipes,
                        recipe_changes,
                        active_recipe_count=active_recipe_count,
                    )
    elif changed_offer_count == 0:
        impacted_recipe_count = 0
        impacted_recipe_ratio_pct = 0.0
        impact_mode = "unchanged"

    return OfferRefreshMetrics(
        store_name=store_name,
        offer_replaces_all=offer_replaces_all,
        current_offer_count=current_offer_count,
        persisted_offer_count=persisted_offer_count,
        changed_offer_count=changed_offer_count,
        changed_offer_ratio_pct=changed_offer_ratio_pct,
        impacted_recipe_count=impacted_recipe_count,
        active_recipe_count=active_recipe_count,
        impacted_recipe_ratio_pct=impacted_recipe_ratio_pct,
        early_full_triggered=early_full_triggered,
        offer_changes=offer_changes,
        recipe_changes=recipe_changes,
        combined_planner_counts=combined_planner_counts,
        changed_offer_sample=changed_offer_sample,
        offer_change_counts=dict(offer_changes.get("counts", {})),
        impact_mode=impact_mode,
        planner_time_ms=int((time.perf_counter() - started_at) * 1000),
    )


def _cache_profile_mismatch_reason(snapshot: OfferCacheStatusSnapshot) -> str | None:
    operation = snapshot.last_operation or {}
    expected = {
        "matcher_version": MATCHER_VERSION,
        "recipe_compiler_version": RECIPE_COMPILER_VERSION,
        "offer_compiler_version": OFFER_COMPILER_VERSION,
    }
    for key, expected_value in expected.items():
        actual_value = operation.get(key)
        if actual_value != expected_value:
            return "cache_profile_mismatch"

    if operation.get("candidate_data_source") not in (None, "term_index"):
        return "cache_profile_mismatch"
    if operation.get("recipe_data_source") not in (None, "compiled_payload"):
        return "cache_profile_mismatch"
    if operation.get("offer_data_source") not in (None, "compiled"):
        return "cache_profile_mismatch"
    return None


def decide_offer_cache_refresh_strategy(
    *,
    store_name: str | None = None,
    cache_status_snapshot: OfferCacheStatusSnapshot | None = None,
    metrics: OfferRefreshMetrics | None = None,
) -> OfferCacheRefreshDecision:
    """Choose skip/delta/full before expensive offer-delta previews start."""
    snapshot = cache_status_snapshot or load_offer_cache_status_snapshot()
    metrics = metrics or build_offer_refresh_metrics(store_name=store_name)
    impacted_threshold = float(settings.offer_delta_impacted_recipe_ratio_full_threshold_pct)
    early_threshold = float(settings.offer_delta_changed_offer_ratio_early_full_threshold_pct)

    strategy: Strategy = "full"
    reason = "impact_above_threshold"

    profile_reason = _cache_profile_mismatch_reason(snapshot)
    recipe_changes_detected = bool(metrics.recipe_changes.get("all_impacted_recipe_ids"))

    if not snapshot.baseline_column_available:
        reason = "compiled_offer_baseline_column_missing"
    elif snapshot.status != "ready":
        reason = "cache_not_ready"
    elif snapshot.cache_rows == 0 and metrics.current_offer_count > 0:
        reason = "active_cache_empty"
    elif not snapshot.compiled_offer_baseline_committed:
        reason = "offer_baseline_incoherent"
    elif metrics.current_offer_count > 0 and metrics.persisted_offer_count == 0:
        reason = "compiled_offer_baseline_missing"
    elif profile_reason and metrics.changed_offer_count == 0:
        reason = "offer_set_unchanged_cache_profile_mismatch"
    elif recipe_changes_detected:
        reason = "recipe_changes_detected"
    elif metrics.changed_offer_count == 0:
        strategy = "skip"
        reason = "offer_set_unchanged"
    elif metrics.impacted_recipe_count == 0:
        strategy = "skip"
        reason = "offer_changes_no_cache_impact"
    elif metrics.impacted_recipe_ratio_pct is not None and metrics.impacted_recipe_ratio_pct <= impacted_threshold:
        strategy = "delta"
        reason = "impact_within_threshold"
    elif metrics.impacted_recipe_ratio_pct is not None:
        reason = "impact_above_threshold"
    elif metrics.early_full_triggered:
        reason = "changed_offer_ratio_above_threshold"
    else:
        reason = "impact_unknown"

    decision = OfferCacheRefreshDecision(
        strategy=strategy,
        reason=reason,
        store_name=store_name,
        offer_replaces_all=metrics.offer_replaces_all,
        current_offer_count=metrics.current_offer_count,
        persisted_offer_count=metrics.persisted_offer_count,
        changed_offer_count=metrics.changed_offer_count,
        changed_offer_ratio_pct=metrics.changed_offer_ratio_pct,
        impacted_recipe_count=metrics.impacted_recipe_count,
        active_recipe_count=metrics.active_recipe_count,
        impacted_recipe_ratio_pct=metrics.impacted_recipe_ratio_pct,
        offer_delta_impacted_recipe_ratio_full_threshold_pct=impacted_threshold,
        offer_delta_changed_offer_ratio_early_full_threshold_pct=early_threshold,
        early_full_triggered=metrics.early_full_triggered,
        cache_status=snapshot.status,
        cache_rows=snapshot.cache_rows,
        metadata_total_matches=snapshot.metadata_total_matches,
        compiled_offer_baseline_committed=snapshot.compiled_offer_baseline_committed,
        planner_time_ms=metrics.planner_time_ms,
        offer_change_counts=metrics.offer_change_counts,
        recipe_change_counts=dict(metrics.recipe_changes.get("counts", {})),
        combined_planner_counts=metrics.combined_planner_counts,
        changed_offer_sample=metrics.changed_offer_sample,
        impact_mode=metrics.impact_mode,
    )
    decision.log()
    return decision


def set_compiled_offer_baseline_committed(committed: bool) -> None:
    """Mark whether compiled offer IR is committed to the persisted cache baseline."""
    try:
        with get_db_session() as db:
            db.execute(text("""
                INSERT INTO cache_metadata (cache_name, compiled_offer_baseline_committed)
                VALUES ('recipe_offer_matches', :committed)
                ON CONFLICT (cache_name) DO UPDATE SET
                    compiled_offer_baseline_committed = :committed
            """), {"committed": bool(committed)})
            db.commit()
    except SQLAlchemyError as exc:
        logger.warning(f"Could not update compiled offer baseline flag: {exc}")
