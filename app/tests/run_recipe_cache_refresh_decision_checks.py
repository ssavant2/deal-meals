#!/usr/bin/env python3
"""Policy checks for recipe scrape cache refresh decisions."""

from __future__ import annotations

from pathlib import Path
import sys


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from config import settings
from recipe_cache_refresh_decision import (  # noqa: E402
    RecipeCacheStatusSnapshot,
    decide_recipe_cache_refresh_strategy,
)


def check(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"OK {name}")


def ready_snapshot(active_recipe_count: int = 13_000) -> RecipeCacheStatusSnapshot:
    return RecipeCacheStatusSnapshot(
        status="ready",
        cache_rows=8_000,
        offer_rows=135,
        active_recipe_count=active_recipe_count,
        metadata_total_matches=8_000,
        metadata_total_recipes=active_recipe_count,
    )


def decide(
    changed_ids: list[str] | None,
    removed_ids: list[str] | None = None,
    *,
    ids_missing: bool = False,
    mode: str = "incremental",
    snapshot: RecipeCacheStatusSnapshot | None = None,
):
    return decide_recipe_cache_refresh_strategy(
        changed_ids,
        removed_ids or [],
        ids_missing,
        source_kind="test",
        mode=mode,
        cache_status_snapshot=snapshot or ready_snapshot(),
    )


def main() -> int:
    original_enabled = settings.cache_recipe_delta_enabled
    original_ratio = settings.cache_recipe_delta_max_affected_ratio
    try:
        settings.cache_recipe_delta_enabled = True
        settings.cache_recipe_delta_max_affected_ratio = 0.05

        small = decide([str(i) for i in range(20)])
        check("small incremental uses delta", small.strategy, "delta")
        check("small incremental reason", small.reason, "ratio_within_threshold")
        check("small affected count", small.affected_recipe_count, 20)
        check("small threshold pct", small.delta_ratio_threshold_pct, 5.0)

        medium = decide([str(i) for i in range(500)], mode="incremental")
        check("medium incremental uses delta", medium.strategy, "delta")
        check("medium incremental reason", medium.reason, "ratio_within_threshold")

        large = decide([str(i) for i in range(800)], mode="incremental")
        check("large incremental uses full", large.strategy, "full")
        check("large incremental reason", large.reason, "ratio_above_threshold")

        full_mode_large = decide([str(i) for i in range(800)], mode="full")
        check("large full uses same policy", full_mode_large.strategy, "full")
        check("full mode uses same reason", full_mode_large.reason, "ratio_above_threshold")

        missing = decide([], ids_missing=True)
        check("missing ids uses full", missing.strategy, "full")
        check("missing ids reason", missing.reason, "delta_ids_missing")

        overlap = decide(["a", "b"], ["b"])
        check("removed wins over changed affected count", overlap.affected_recipe_count, 2)
        check("overlap still within threshold", overlap.strategy, "delta")

        noop = decide([])
        check("no changes noop", noop.strategy, "noop")
        check("no changes reason", noop.reason, "no_cache_changes")

        settings.cache_recipe_delta_enabled = False
        disabled = decide(["a"])
        check("disabled uses full", disabled.strategy, "full")
        check("disabled reason", disabled.reason, "recipe_delta_disabled")
        settings.cache_recipe_delta_enabled = True

        not_ready = decide(["a"], snapshot=RecipeCacheStatusSnapshot(
            status="computing",
            cache_rows=8_000,
            offer_rows=135,
            active_recipe_count=13_000,
        ))
        check("cache not ready uses full", not_ready.strategy, "full")
        check("cache not ready reason", not_ready.reason, "cache_not_ready")

        empty_active = decide(["a"], snapshot=ready_snapshot(active_recipe_count=0))
        check("empty active uses full", empty_active.strategy, "full")
        check("empty active reason", empty_active.reason, "active_recipe_count_empty")

        empty_cache = decide(["a"], snapshot=RecipeCacheStatusSnapshot(
            status="ready",
            cache_rows=0,
            offer_rows=135,
            active_recipe_count=13_000,
        ))
        check("empty cache uses full", empty_cache.strategy, "full")
        check("empty cache reason", empty_cache.reason, "active_cache_empty")

        context = small.to_operation_context()
        check("context decision", context["recipe_delta_decision"], "delta")
        check("context reason", context["recipe_delta_reason"], "ratio_within_threshold")
        check("context affected ratio", context["affected_ratio_pct"], small.affected_ratio_pct)

    finally:
        settings.cache_recipe_delta_enabled = original_enabled
        settings.cache_recipe_delta_max_affected_ratio = original_ratio

    print("ALL RECIPE CACHE REFRESH DECISION CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
