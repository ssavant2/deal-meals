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
    _enforce_recipe_delta_preview_size_gate,
    _ingredient_routing_summary_from_result,
    _resolve_delta_verification_policy,
    _resolve_recipe_delta_verification_policy,
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


original_settings = {
    "cache_delta_probation_history_file": settings.cache_delta_probation_history_file,
    "cache_delta_probation_min_ready_streak": settings.cache_delta_probation_min_ready_streak,
    "cache_delta_probation_min_version_ready_runs": settings.cache_delta_probation_min_version_ready_runs,
    "cache_delta_skip_full_preview_after_probation": settings.cache_delta_skip_full_preview_after_probation,
    "cache_recipe_delta_probation_history_file": settings.cache_recipe_delta_probation_history_file,
    "cache_recipe_delta_probation_min_ready_streak": settings.cache_recipe_delta_probation_min_ready_streak,
    "cache_recipe_delta_probation_min_version_ready_runs": settings.cache_recipe_delta_probation_min_version_ready_runs,
    "cache_recipe_delta_skip_full_preview_after_probation": settings.cache_recipe_delta_skip_full_preview_after_probation,
    "cache_recipe_delta_skip_full_preview_max_affected_ratio": (
        settings.cache_recipe_delta_skip_full_preview_max_affected_ratio
    ),
    "cache_ingredient_routing_mode": settings.cache_ingredient_routing_mode,
}

try:
    with tempfile.TemporaryDirectory() as tmp_dir:
        delta_history_path = Path(tmp_dir) / "delta_probation.jsonl"
        recipe_delta_history_path = Path(tmp_dir) / "recipe_delta_probation.jsonl"
        _write_ready_delta_history(delta_history_path)
        _write_ready_delta_history(recipe_delta_history_path)

        settings.cache_delta_probation_history_file = str(delta_history_path)
        settings.cache_delta_probation_min_ready_streak = 1
        settings.cache_delta_probation_min_version_ready_runs = 1
        settings.cache_delta_skip_full_preview_after_probation = True
        settings.cache_recipe_delta_probation_history_file = str(recipe_delta_history_path)
        settings.cache_recipe_delta_probation_min_ready_streak = 1
        settings.cache_recipe_delta_probation_min_version_ready_runs = 1
        settings.cache_recipe_delta_skip_full_preview_after_probation = True
        settings.cache_recipe_delta_skip_full_preview_max_affected_ratio = 0.025

        settings.cache_ingredient_routing_mode = "off"
        off_policy = _resolve_delta_verification_policy(verify_full_preview=True)
        test("delta probation may skip full preview when ingredient routing is off", off_policy["verification_mode"], "probation_skip")
        test("off mode keeps effective full preview disabled after delta probation", off_policy["effective_verify_full_preview"], False)

        recipe_policy = _resolve_recipe_delta_verification_policy(verify_full_preview=True)
        test("recipe-delta may skip full preview after one ready current-version run", recipe_policy["verification_mode"], "probation_skip")
        test("recipe-delta keeps effective full preview disabled after one ready run", recipe_policy["effective_verify_full_preview"], False)
        small_recipe_policy = _enforce_recipe_delta_preview_size_gate(
            recipe_policy,
            affected_recipe_count=1000,
            active_recipe_count=40000,
        )
        test("small recipe-delta keeps probation skip after size gate", small_recipe_policy["verification_mode"], "probation_skip")
        large_recipe_policy = _enforce_recipe_delta_preview_size_gate(
            recipe_policy,
            affected_recipe_count=1100,
            active_recipe_count=40000,
        )
        test("larger recipe-delta keeps full preview despite probation", large_recipe_policy["verification_mode"], "full_preview_required_for_large_recipe_delta")
        test("larger recipe-delta re-enables effective full preview", large_recipe_policy["effective_verify_full_preview"], True)

        settings.cache_ingredient_routing_mode = "hint_first"
        hint_policy = _resolve_delta_verification_policy(verify_full_preview=True)
        test("hint_first may skip full preview after delta probation is ready", hint_policy["effective_verify_full_preview"], False)
        test("hint_first uses the normal delta probation skip mode", hint_policy["verification_mode"], "probation_skip")

        no_preview_policy = _resolve_delta_verification_policy(verify_full_preview=False)
        test("hint_first respects a disabled full-preview request", no_preview_policy["effective_verify_full_preview"], False)

        settings.cache_delta_probation_min_version_ready_runs = 2
        delta_pending_policy = _resolve_delta_verification_policy(verify_full_preview=True)
        test(
            "hint_first still uses full preview while delta probation is pending",
            delta_pending_policy["effective_verify_full_preview"],
            True,
        )
        test("hint_first pending mode comes from delta probation", delta_pending_policy["verification_mode"], "full_preview_pending_probation")

        settings.cache_delta_probation_min_version_ready_runs = 1
        ready_hint_policy = _resolve_delta_verification_policy(verify_full_preview=True)
        test("hint_first may skip full preview when delta probation is ready", ready_hint_policy["verification_mode"], "probation_skip")
        test("hint_first keeps effective full preview disabled after delta probation", ready_hint_policy["effective_verify_full_preview"], False)

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
