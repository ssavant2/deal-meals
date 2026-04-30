"""Shared recipe-scrape cache refresh decision helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy import text

try:
    from config import settings
    from database import get_db_session
except ModuleNotFoundError:
    from app.config import settings
    from app.database import get_db_session


CACHE_NAME = "recipe_offer_matches"


@dataclass(frozen=True)
class RecipeCacheStatusSnapshot:
    """Small DB snapshot used before a caller may pre-mark cache as computing."""

    status: str | None
    cache_rows: int
    offer_rows: int
    active_recipe_count: int
    metadata_total_matches: int | None = None
    metadata_total_recipes: int | None = None

    def to_cache_state(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "cache_rows": self.cache_rows,
            "offer_rows": self.offer_rows,
            "metadata_total_matches": self.metadata_total_matches,
            "metadata_total_recipes": self.metadata_total_recipes,
        }


@dataclass(frozen=True)
class RecipeCacheRefreshDecision:
    """Structured decision for recipe-scrape cache updates."""

    strategy: str
    reason: str
    source_kind: str
    mode: str
    affected_recipe_count: int
    active_recipe_count: int
    affected_ratio: float | None
    delta_ratio_threshold: float
    cache_status: str | None
    cache_rows: int
    offer_rows: int
    ids_missing: bool = False

    @property
    def affected_ratio_pct(self) -> float:
        return round((self.affected_ratio or 0.0) * 100, 4)

    @property
    def delta_ratio_threshold_pct(self) -> float:
        return round(self.delta_ratio_threshold * 100, 4)

    @property
    def requires_cache_refresh(self) -> bool:
        return self.strategy in {"delta", "full"}

    @property
    def uses_delta(self) -> bool:
        return self.strategy == "delta"

    def to_operation_context(self) -> dict[str, Any]:
        return {
            "recipe_delta_decision": self.strategy,
            "recipe_delta_reason": self.reason,
            "affected_recipe_count": self.affected_recipe_count,
            "active_recipe_count": self.active_recipe_count,
            "affected_ratio_pct": self.affected_ratio_pct,
            "delta_ratio_threshold_pct": self.delta_ratio_threshold_pct,
        }

    def log_summary(self, *, label: str) -> str:
        return (
            f"{label}: {self.strategy} affected={self.affected_recipe_count} "
            f"active={self.active_recipe_count} ratio={self.affected_ratio_pct:.2f}% "
            f"threshold={self.delta_ratio_threshold_pct:.2f}% reason={self.reason}"
        )


def _coerce_id_set(values: list[str] | None) -> set[str]:
    return {str(value) for value in values or [] if value is not None}


def _coerce_snapshot(value: RecipeCacheStatusSnapshot | Mapping[str, Any]) -> RecipeCacheStatusSnapshot:
    if isinstance(value, RecipeCacheStatusSnapshot):
        return value
    return RecipeCacheStatusSnapshot(
        status=value.get("status"),
        cache_rows=int(value.get("cache_rows") or 0),
        offer_rows=int(value.get("offer_rows") or 0),
        active_recipe_count=int(value.get("active_recipe_count") or 0),
        metadata_total_matches=value.get("metadata_total_matches"),
        metadata_total_recipes=value.get("metadata_total_recipes"),
    )


def load_recipe_cache_status_snapshot() -> RecipeCacheStatusSnapshot:
    """Read cache state and active recipe count used by the shared decision policy."""
    with get_db_session() as db:
        metadata = db.execute(text("""
            SELECT status, total_matches, total_recipes
            FROM cache_metadata
            WHERE cache_name = :cache_name
        """), {"cache_name": CACHE_NAME}).mappings().fetchone()
        cache_rows = db.execute(text("SELECT COUNT(*) FROM recipe_offer_cache")).scalar() or 0
        offer_rows = db.execute(text("SELECT COUNT(*) FROM offers")).scalar() or 0
        active_recipe_count = db.execute(text("""
            SELECT COUNT(*)
            FROM found_recipes
            WHERE excluded = FALSE OR excluded IS NULL
        """)).scalar() or 0

    return RecipeCacheStatusSnapshot(
        status=metadata["status"] if metadata else None,
        cache_rows=int(cache_rows),
        offer_rows=int(offer_rows),
        active_recipe_count=int(active_recipe_count),
        metadata_total_matches=metadata["total_matches"] if metadata else None,
        metadata_total_recipes=metadata["total_recipes"] if metadata else None,
    )


def decide_recipe_cache_refresh_strategy(
    changed_ids: list[str] | None,
    removed_ids: list[str] | None,
    ids_missing: bool,
    source_kind: str,
    mode: str,
    cache_status_snapshot: RecipeCacheStatusSnapshot | Mapping[str, Any],
) -> RecipeCacheRefreshDecision:
    """Return delta/full/noop decision for any recipe-scrape trigger."""
    snapshot = _coerce_snapshot(cache_status_snapshot)
    removed_set = _coerce_id_set(removed_ids)
    changed_set = _coerce_id_set(changed_ids) - removed_set
    affected_count = len(changed_set | removed_set)
    active_count = max(0, snapshot.active_recipe_count)
    threshold = max(0.0, float(settings.cache_recipe_delta_max_affected_ratio))
    ratio = (affected_count / active_count) if active_count > 0 else None

    def decision(strategy: str, reason: str) -> RecipeCacheRefreshDecision:
        return RecipeCacheRefreshDecision(
            strategy=strategy,
            reason=reason,
            source_kind=source_kind,
            mode=mode,
            affected_recipe_count=affected_count,
            active_recipe_count=active_count,
            affected_ratio=ratio,
            delta_ratio_threshold=threshold,
            cache_status=snapshot.status,
            cache_rows=snapshot.cache_rows,
            offer_rows=snapshot.offer_rows,
            ids_missing=ids_missing,
        )

    if affected_count == 0 and not ids_missing:
        return decision("noop", "no_cache_changes")
    if not settings.cache_recipe_delta_enabled:
        return decision("full", "recipe_delta_disabled")
    if ids_missing:
        return decision("full", "delta_ids_missing")
    if snapshot.status != "ready":
        return decision("full", "cache_not_ready")
    if active_count <= 0:
        return decision("full", "active_recipe_count_empty")
    if snapshot.cache_rows <= 0:
        return decision("full", "active_cache_empty")
    if ratio is not None and ratio <= threshold:
        return decision("delta", "ratio_within_threshold")
    return decision("full", "ratio_above_threshold")
