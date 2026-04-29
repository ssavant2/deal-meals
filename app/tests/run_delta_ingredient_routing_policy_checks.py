#!/usr/bin/env python3
"""Checks for delta verification policy with ingredient-routing modes."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, '/app' if os.path.exists('/app') else os.path.join(os.path.dirname(__file__), '..'))

from cache_delta import (  # noqa: E402
    _ingredient_routing_summary_from_result,
    _resolve_delta_verification_policy,
    _resolve_recipe_delta_verification_policy,
    _temporary_ingredient_routing_mode,
)
from config import settings  # noqa: E402
from languages.matcher_runtime import (  # noqa: E402
    MATCHER_VERSION,
    OFFER_COMPILER_VERSION,
    RECIPE_COMPILER_VERSION,
)


passed = 0
failed = 0


def test(desc: str, actual, expected) -> None:
    global passed, failed
    if actual == expected:
        passed += 1
        return
    failed += 1
    print(f"FAIL: {desc}")
    print(f"  got:      {actual}")
    print(f"  expected: {expected}")


def _write_ready_delta_history(history_path: Path) -> None:
    history_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-04-26T12:00:00+00:00",
                "matcher_version": MATCHER_VERSION,
                "recipe_compiler_version": RECIPE_COMPILER_VERSION,
                "offer_compiler_version": OFFER_COMPILER_VERSION,
                "ready_for_manual_live_apply": True,
                "probation_countable": True,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_ready_ingredient_history(history_path: Path) -> None:
    history_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-04-26T12:00:00+00:00",
                "matcher_version": MATCHER_VERSION,
                "recipe_compiler_version": RECIPE_COMPILER_VERSION,
                "offer_compiler_version": OFFER_COMPILER_VERSION,
                "ready_for_hint_first": True,
                "probation_countable": True,
                "shadow_unexplained_miss_count": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


original_settings = {
    "cache_delta_probation_history_file": settings.cache_delta_probation_history_file,
    "cache_delta_probation_min_ready_streak": settings.cache_delta_probation_min_ready_streak,
    "cache_delta_probation_min_version_ready_runs": settings.cache_delta_probation_min_version_ready_runs,
    "cache_delta_skip_full_preview_after_probation": settings.cache_delta_skip_full_preview_after_probation,
    "cache_term_index_skip_fts_prefilter": settings.cache_term_index_skip_fts_prefilter,
    "cache_ingredient_routing_mode": settings.cache_ingredient_routing_mode,
    "cache_ingredient_routing_probation_history_file": (
        settings.cache_ingredient_routing_probation_history_file
    ),
    "cache_ingredient_routing_probation_min_ready_streak": (
        settings.cache_ingredient_routing_probation_min_ready_streak
    ),
    "cache_ingredient_routing_probation_min_version_ready_runs": (
        settings.cache_ingredient_routing_probation_min_version_ready_runs
    ),
}

try:
    with tempfile.TemporaryDirectory() as tmp_dir:
        delta_history_path = Path(tmp_dir) / "delta_probation.jsonl"
        ingredient_history_path = Path(tmp_dir) / "ingredient_probation.jsonl"
        _write_ready_delta_history(delta_history_path)

        settings.cache_delta_probation_history_file = str(delta_history_path)
        settings.cache_delta_probation_min_ready_streak = 1
        settings.cache_delta_probation_min_version_ready_runs = 1
        settings.cache_delta_skip_full_preview_after_probation = True
        settings.cache_term_index_skip_fts_prefilter = True
        settings.cache_ingredient_routing_probation_history_file = str(ingredient_history_path)
        settings.cache_ingredient_routing_probation_min_ready_streak = 1
        settings.cache_ingredient_routing_probation_min_version_ready_runs = 1

        settings.cache_ingredient_routing_mode = "off"
        off_policy = _resolve_delta_verification_policy(verify_full_preview=True)
        test("delta probation may skip full preview when ingredient routing is off", off_policy["verification_mode"], "probation_skip")
        test("off mode keeps effective full preview disabled after delta probation", off_policy["effective_verify_full_preview"], False)

        settings.cache_ingredient_routing_mode = "hint_first"
        hint_policy = _resolve_delta_verification_policy(verify_full_preview=True)
        test("hint_first forces full preview until ingredient routing probation is ready", hint_policy["effective_verify_full_preview"], True)
        test("hint_first reports fullscan baseline requirement before ingredient probation", hint_policy["ingredient_routing_requires_fullscan_baseline"], True)
        test("hint_first overrides probation skip mode before ingredient probation", hint_policy["verification_mode"], "full_preview_required_for_hint_first")

        no_preview_policy = _resolve_delta_verification_policy(verify_full_preview=False)
        test("hint_first forces full preview even when requested false before gates are ready", no_preview_policy["effective_verify_full_preview"], True)

        _write_ready_ingredient_history(ingredient_history_path)
        ready_hint_policy = _resolve_delta_verification_policy(verify_full_preview=True)
        test("hint_first may skip full preview when both probation gates are ready", ready_hint_policy["verification_mode"], "probation_skip")
        test("hint_first keeps effective full preview disabled after both gates are ready", ready_hint_policy["effective_verify_full_preview"], False)
        test("hint_first no longer requires a fullscan baseline after both gates are ready", ready_hint_policy["ingredient_routing_requires_fullscan_baseline"], False)

        settings.cache_term_index_skip_fts_prefilter = False
        legacy_offer_policy = _resolve_delta_verification_policy(verify_full_preview=True)
        test(
            "legacy FTS prefilter forces offer-delta full preview despite green probation",
            legacy_offer_policy["verification_mode"],
            "full_preview_required_for_legacy_fts_prefilter",
        )
        test(
            "legacy FTS prefilter keeps offer-delta full preview enabled",
            legacy_offer_policy["effective_verify_full_preview"],
            True,
        )

        legacy_recipe_policy = _resolve_recipe_delta_verification_policy(verify_full_preview=False)
        test(
            "legacy FTS prefilter forces recipe-delta full preview even when not requested",
            legacy_recipe_policy["verification_mode"],
            "full_preview_required_for_legacy_fts_prefilter",
        )
        test(
            "legacy FTS prefilter keeps recipe-delta full preview enabled",
            legacy_recipe_policy["effective_verify_full_preview"],
            True,
        )
        settings.cache_term_index_skip_fts_prefilter = True

        with _temporary_ingredient_routing_mode("off"):
            test("temporary ingredient routing override is visible", settings.cache_ingredient_routing_mode, "off")
        test("temporary ingredient routing override restores previous mode", settings.cache_ingredient_routing_mode, "hint_first")

        routing_summary = _ingredient_routing_summary_from_result({
            "ingredient_routing_mode": "hint_first",
            "ingredient_routing_effective_mode": "hint_first",
            "entries": [{"ignored": True}],
        })
        test("ingredient routing summaries omit raw cache entries", "entries" in routing_summary, False)
        test("ingredient routing summaries keep mode", routing_summary["ingredient_routing_mode"], "hint_first")
finally:
    for key, value in original_settings.items():
        setattr(settings, key, value)


print("\n========================================")
print(f"TOTAL: {passed}/{passed + failed} checks passed")
if failed:
    print(f"{failed} FAILED!")
    print("========================================")
    raise SystemExit(1)

print("ALL PASSED!")
print("========================================")
