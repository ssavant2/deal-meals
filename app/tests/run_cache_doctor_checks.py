#!/usr/bin/env python3
"""Policy checks for cache doctor and cache-operation metadata helpers."""

from __future__ import annotations

from pathlib import Path
import sys


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from cache_doctor import _overall_status, _summary
from cache_operation_metadata import (
    MAX_OPERATION_HISTORY,
    build_cache_last_operation,
    summarize_cache_operation_history,
)


def check(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"OK {name}")


def main() -> int:
    operation = build_cache_last_operation(
        {
            "run_kind": "recipe_delta_patch_preview",
            "source": "recipe_scrape:koket:incremental",
            "status": "ready",
            "effective_rebuild_mode": "delta",
            "changed_recipe_count": "20",
            "removed_recipe_count": 0,
            "changed_recipe_ids": ["should-not-be-persisted"],
            "patch_result": {
                "total_matches": 1234,
                "inserted_count": 18,
                "deleted_count": 2,
                "inserted_recipe_ids": ["should-not-be-persisted"],
            },
            "error": "x" * 700,
        },
        operation_type="recipe_delta",
    )

    check("operation mode", operation["mode"], "recipe_delta")
    check("operation status", operation["status"], "ready")
    check("operation changed count coerced", operation["changed_recipe_count"], 20)
    check("operation patch total", operation["total_matches"], 1234)
    check("operation patch inserted", operation["patch_inserted_count"], 18)
    check("operation excludes id lists", "changed_recipe_ids" in operation, False)
    check("operation truncates long error", operation["error"].endswith("..."), True)
    check("operation truncates to bounded length", len(operation["error"]), 503)

    history = [
        {"mode": "full_rebuild", "status": "ready", "generated_at": "2026-04-30T01:00:00+00:00"},
        {
            "mode": "recipe_delta",
            "status": "fallback",
            "fallback_reason": "materialized_patch_mismatch",
            "generated_at": "2026-04-30T02:00:00+00:00",
        },
        {
            "mode": "full_rebuild",
            "status": "error",
            "error": "boom",
            "generated_at": "2026-04-30T03:00:00+00:00",
        },
        {
            "mode": "offer_delta",
            "status": "fallback",
            "fallback_reason": "planner_missed_preview_diff",
            "generated_at": "2026-04-30T04:00:00+00:00",
        },
        {
            "mode": "recipe_delta",
            "status": "fallback",
            "fallback_reason": "planner_missed_preview_diff",
            "generated_at": "2026-04-30T05:00:00+00:00",
        },
    ]
    history_summary = summarize_cache_operation_history(history, recent_window=3)
    check("history size", history_summary["history_size"], 5)
    check("history limit", history_summary["history_limit"], MAX_OPERATION_HISTORY)
    check("history fallback count", history_summary["fallback_count"], 3)
    check("history fallback rate", history_summary["fallback_rate_pct"], 60.0)
    check("history recent fallback count", history_summary["recent_fallback_count"], 2)
    check("history recent error count", history_summary["recent_error_count"], 1)
    check("history consecutive fallbacks", history_summary["consecutive_fallbacks"], 2)
    check("history fallback reasons", history_summary["fallback_reasons"], {
        "materialized_patch_mismatch": 1,
        "planner_missed_preview_diff": 2,
    })
    check("history by mode", history_summary["by_mode"], {
        "full_rebuild": 2,
        "offer_delta": 1,
        "recipe_delta": 2,
    })

    checks = [
        {"status": "ok"},
        {"status": "warning"},
        {"status": "ok"},
    ]
    check("overall warning", _overall_status(checks), "warning")
    check("summary counts", _summary(checks), {
        "checks": 3,
        "ok": 2,
        "warning": 1,
        "error": 0,
    })
    checks.append({"status": "error"})
    check("overall error wins", _overall_status(checks), "error")

    print("ALL CACHE DOCTOR CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
