#!/usr/bin/env python3
"""Policy checks for scheduled cache reconciliation decisions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from cache_reconciliation import (  # noqa: E402
    CacheReconciliationSnapshot,
    decide_cache_reconciliation,
)


NOW = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)


def check(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"OK {name}")


def op(mode: str, hours_ago: int, *, status: str = "ready", run_kind: str | None = None):
    result = {
        "mode": mode,
        "status": status,
        "generated_at": (NOW - timedelta(hours=hours_ago)).isoformat(),
    }
    if run_kind:
        result["run_kind"] = run_kind
    return result


def snapshot(
    *,
    status: str | None = "ready",
    last_computed_hours_ago: int | None = 10,
    history: list[dict] | None = None,
    cache_rows: int = 5000,
) -> CacheReconciliationSnapshot:
    last_computed_at = (
        NOW - timedelta(hours=last_computed_hours_ago)
        if last_computed_hours_ago is not None
        else None
    )
    return CacheReconciliationSnapshot(
        status=status,
        last_computed_at=last_computed_at,
        operation_history=history or [],
        cache_rows=cache_rows,
    )


def decide(
    sample: CacheReconciliationSnapshot,
    *,
    last_activity_minutes_ago: int | None = None,
    enabled: bool = True,
    min_age_days: int = 7,
    max_incremental_operations: int = 25,
):
    last_activity = (
        NOW - timedelta(minutes=last_activity_minutes_ago)
        if last_activity_minutes_ago is not None
        else None
    )
    return decide_cache_reconciliation(
        sample,
        trigger="test",
        now=NOW,
        last_user_activity_at=last_activity,
        enabled=enabled,
        inactive_minutes=15,
        min_age_days=min_age_days,
        max_incremental_operations=max_incremental_operations,
    )


def main() -> int:
    disabled = decide(snapshot(history=[op("full_rebuild", 200)]), enabled=False)
    check("disabled skips", disabled.should_run, False)
    check("disabled reason", disabled.reason, "disabled")

    active = decide(
        snapshot(history=[op("full_rebuild", 200)]),
        last_activity_minutes_ago=5,
    )
    check("recent user activity skips", active.should_run, False)
    check("recent user activity reason", active.reason, "user_active")

    not_ready = decide(snapshot(status="computing", history=[op("full_rebuild", 200)]))
    check("non-ready cache skips", not_ready.should_run, False)
    check("non-ready reason", not_ready.reason, "cache_not_ready")

    empty = decide(snapshot(cache_rows=0, history=[op("full_rebuild", 200)]))
    check("empty cache skips", empty.should_run, False)
    check("empty cache reason", empty.reason, "cache_empty")

    old_full = decide(snapshot(history=[op("full_rebuild", 200)]))
    check("old full runs", old_full.should_run, True)
    check("old full reason", old_full.reason, "full_rebuild_age_due")
    check("old full age rounded", round(old_full.last_full_age_hours or 0, 1), 200.0)

    recent_full_many_deltas = decide(snapshot(history=[
        op("full_rebuild", 24),
        *[op("recipe_delta", 20) for _ in range(20)],
        *[op("offer_refresh_skip", 2) for _ in range(5)],
    ]))
    check("many incremental ops runs", recent_full_many_deltas.should_run, True)
    check("many incremental ops reason", recent_full_many_deltas.reason, "incremental_operation_count_due")
    check("incremental op count", recent_full_many_deltas.incremental_operations_since_full, 25)

    fresh = decide(snapshot(history=[
        op("full_rebuild", 24),
        op("recipe_delta", 20),
        op("offer_delta", 12),
    ]))
    check("fresh low-op baseline skips", fresh.should_run, False)
    check("fresh low-op reason", fresh.reason, "not_due")

    no_history = decide(snapshot(last_computed_hours_ago=None, history=[]))
    check("no baseline record runs", no_history.should_run, True)
    check("no baseline reason", no_history.reason, "no_full_rebuild_recorded")

    only_incrementals = decide(snapshot(last_computed_hours_ago=1, history=[
        op("recipe_delta", 2),
        op("offer_refresh_skip", 1),
    ]))
    check("history without full runs", only_incrementals.should_run, True)
    check("history without full reason", only_incrementals.reason, "no_full_rebuild_recorded")

    run_kind_baseline = decide(snapshot(history=[
        op("unknown", 2, run_kind="manual_full_rebuild"),
        op("recipe_delta", 1),
    ]))
    check("run_kind full baseline skips", run_kind_baseline.should_run, False)
    check("run_kind full incremental count", run_kind_baseline.incremental_operations_since_full, 1)

    context = old_full.to_operation_context()
    check("context reason", context["cache_reconciliation_reason"], "full_rebuild_age_due")
    check("context trigger", context["cache_reconciliation_trigger"], "test")

    print("Cache reconciliation policy checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
