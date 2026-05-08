"""Opportunistic full-cache reconciliation after scheduled background work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Mapping

from loguru import logger
from sqlalchemy import text

from activity_tracker import get_last_user_activity
from config import settings
from database import get_db_session


CACHE_NAME = "recipe_offer_matches"
BASELINE_MODES = {"full_rebuild", "empty_cache"}
INCREMENTAL_MODES = {"recipe_delta", "offer_delta", "offer_refresh_skip"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return _as_aware_utc(parsed)


def _normalize_history(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


@dataclass(frozen=True)
class CacheReconciliationSnapshot:
    status: str | None
    last_computed_at: datetime | None
    operation_history: list[dict[str, Any]]
    cache_rows: int = 0


@dataclass(frozen=True)
class CacheReconciliationDecision:
    should_run: bool
    reason: str
    trigger: str
    cache_status: str | None
    last_full_at: datetime | None
    last_full_age_hours: float | None
    incremental_operations_since_full: int
    idle_seconds: int | None
    min_age_hours: int
    max_incremental_operations: int

    def to_operation_context(self) -> dict[str, Any]:
        context: dict[str, Any] = {
            "cache_reconciliation_trigger": self.trigger,
            "cache_reconciliation_reason": self.reason,
            "cache_reconciliation_incremental_operations_since_full": (
                self.incremental_operations_since_full
            ),
            "cache_reconciliation_min_age_hours": self.min_age_hours,
            "cache_reconciliation_max_incremental_operations": (
                self.max_incremental_operations
            ),
        }
        if self.last_full_age_hours is not None:
            context["cache_reconciliation_last_full_age_hours"] = round(
                self.last_full_age_hours,
                3,
            )
        if self.idle_seconds is not None:
            context["cache_reconciliation_idle_seconds"] = self.idle_seconds
        return context

    def log_summary(self) -> str:
        age = (
            "unknown"
            if self.last_full_age_hours is None
            else f"{self.last_full_age_hours:.1f}h"
        )
        idle = "unknown" if self.idle_seconds is None else f"{self.idle_seconds}s"
        action = "run" if self.should_run else "skip"
        return (
            "Cache reconciliation decision: "
            f"{action} reason={self.reason} trigger={self.trigger} "
            f"status={self.cache_status} last_full_age={age} "
            f"incremental_ops={self.incremental_operations_since_full} idle={idle}"
        )


def load_cache_reconciliation_snapshot() -> CacheReconciliationSnapshot:
    """Load the tiny DB snapshot needed for the reconciliation policy."""
    with get_db_session() as db:
        row = db.execute(text("""
            SELECT status, last_computed_at, operation_history
            FROM cache_metadata
            WHERE cache_name = :name
        """), {"name": CACHE_NAME}).fetchone()
        cache_rows = int(db.execute(text("SELECT COUNT(*) FROM recipe_offer_cache")).scalar() or 0)

    if not row:
        return CacheReconciliationSnapshot(
            status=None,
            last_computed_at=None,
            operation_history=[],
            cache_rows=cache_rows,
        )

    return CacheReconciliationSnapshot(
        status=row.status,
        last_computed_at=_as_aware_utc(row.last_computed_at),
        operation_history=_normalize_history(row.operation_history),
        cache_rows=cache_rows,
    )


def _last_baseline_index_and_time(
    history: list[dict[str, Any]],
) -> tuple[int | None, datetime | None]:
    for index in range(len(history) - 1, -1, -1):
        operation = history[index]
        mode = str(operation.get("mode") or "")
        run_kind = str(operation.get("run_kind") or "")
        if mode in BASELINE_MODES or "full_rebuild" in run_kind:
            generated_at = _parse_iso_datetime(operation.get("generated_at"))
            return index, generated_at
    return None, None


def _incremental_operations_after(
    history: list[dict[str, Any]],
    baseline_index: int | None,
) -> int:
    start_index = 0 if baseline_index is None else baseline_index + 1
    count = 0
    for operation in history[start_index:]:
        mode = str(operation.get("mode") or "")
        if mode not in INCREMENTAL_MODES:
            continue
        if operation.get("status") != "ready":
            continue
        count += 1
    return count


def decide_cache_reconciliation(
    snapshot: CacheReconciliationSnapshot,
    *,
    trigger: str,
    now: datetime | None = None,
    last_user_activity_at: datetime | None = None,
    enabled: bool | None = None,
    inactive_minutes: int | None = None,
    min_age_days: int | None = None,
    max_incremental_operations: int | None = None,
) -> CacheReconciliationDecision:
    """Decide whether a scheduled job should opportunistically run a full rebuild."""
    now = _as_aware_utc(now) or _utcnow()
    enabled = settings.cache_reconciliation_enabled if enabled is None else enabled
    inactive_minutes = (
        settings.cache_reconciliation_inactive_minutes
        if inactive_minutes is None
        else inactive_minutes
    )
    min_age_days = (
        settings.cache_reconciliation_min_age_days
        if min_age_days is None
        else min_age_days
    )
    max_incremental_operations = (
        settings.cache_reconciliation_max_incremental_operations
        if max_incremental_operations is None
        else max_incremental_operations
    )
    min_age_hours = max(0, int(min_age_days)) * 24

    baseline_index, last_full_at = _last_baseline_index_and_time(snapshot.operation_history)
    if last_full_at is None and not snapshot.operation_history:
        last_full_at = snapshot.last_computed_at
    last_full_at = _as_aware_utc(last_full_at)
    incremental_operations = _incremental_operations_after(
        snapshot.operation_history,
        baseline_index,
    )

    last_full_age_hours: float | None = None
    if last_full_at is not None:
        last_full_age_hours = max(0.0, (now - last_full_at).total_seconds() / 3600)

    idle_seconds: int | None = None
    last_user_activity_at = _as_aware_utc(last_user_activity_at)
    if last_user_activity_at is not None:
        idle_seconds = max(0, int((now - last_user_activity_at).total_seconds()))

    def decision(should_run: bool, reason: str) -> CacheReconciliationDecision:
        return CacheReconciliationDecision(
            should_run=should_run,
            reason=reason,
            trigger=trigger,
            cache_status=snapshot.status,
            last_full_at=last_full_at,
            last_full_age_hours=last_full_age_hours,
            incremental_operations_since_full=incremental_operations,
            idle_seconds=idle_seconds,
            min_age_hours=min_age_hours,
            max_incremental_operations=max_incremental_operations,
        )

    if not enabled:
        return decision(False, "disabled")
    if snapshot.status != "ready":
        return decision(False, "cache_not_ready")
    if snapshot.cache_rows <= 0:
        return decision(False, "cache_empty")
    if idle_seconds is not None and idle_seconds < max(0, inactive_minutes) * 60:
        return decision(False, "user_active")
    if last_full_at is None:
        return decision(True, "no_full_rebuild_recorded")
    if min_age_hours > 0 and last_full_age_hours is not None:
        if last_full_age_hours >= min_age_hours:
            return decision(True, "full_rebuild_age_due")
    if (
        max_incremental_operations > 0
        and incremental_operations >= max_incremental_operations
    ):
        return decision(True, "incremental_operation_count_due")
    return decision(False, "not_due")


async def maybe_run_scheduled_cache_reconciliation(trigger: str) -> dict[str, Any]:
    """Run a full rebuild after scheduled work when the policy says it is due."""
    try:
        snapshot = load_cache_reconciliation_snapshot()
        last_activity_at, _ = get_last_user_activity()
        decision = decide_cache_reconciliation(
            snapshot,
            trigger=trigger,
            last_user_activity_at=last_activity_at,
        )
        logger.info(decision.log_summary())
        if not decision.should_run:
            return {"success": True, "skipped": True, "reason": decision.reason}

        from cache_manager import compute_cache_async

        result = await compute_cache_async(
            skip_if_busy=True,
            run_kind="scheduled_reconciliation_full_rebuild",
            source=f"scheduled_reconciliation:{trigger}",
            operation_context=decision.to_operation_context(),
        )
        if result.get("skipped"):
            logger.info(
                "Scheduled cache reconciliation skipped by cache lock: "
                f"{result.get('reason')}"
            )
        elif result.get("success", True):
            logger.success(
                "Scheduled cache reconciliation complete: "
                f"{result.get('cached', 0)} recipes in {result.get('time_ms', 0)}ms"
            )
        return result
    except Exception as exc:
        logger.warning(f"Scheduled cache reconciliation failed: {exc}")
        return {"success": False, "skipped": True, "reason": "exception", "error": str(exc)}
