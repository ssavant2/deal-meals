#!/usr/bin/env python3
"""Checks for ingredient-routing probation runtime helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, '/app' if os.path.exists('/app') else os.path.join(os.path.dirname(__file__), '..'))

from ingredient_routing_probation_runtime import (  # noqa: E402
    append_ingredient_routing_probation_history,
    get_ingredient_routing_probation_gate_status,
    load_ingredient_routing_probation_history,
    normalize_ingredient_routing_mode,
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


def _write_entries(history_path: Path, entries: list[dict]) -> None:
    history_path.write_text(
        "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in entries),
        encoding="utf-8",
    )


test("valid mode is preserved", normalize_ingredient_routing_mode("shadow"), "shadow")
test("invalid mode falls back to off", normalize_ingredient_routing_mode("turbo"), "off")

with tempfile.TemporaryDirectory() as tmp_dir:
    history_path = Path(tmp_dir) / "ingredient_routing_probation.jsonl"
    entries = [
        {
            "generated_at": f"2026-04-2{i}T12:00:00+00:00",
            "matcher_version": "matcher-x",
            "recipe_compiler_version": "recipe-x",
            "offer_compiler_version": "offer-x",
            "ready_for_hint_first": True,
            "probation_countable": True,
            "shadow_unexplained_miss_count": 0,
        }
        for i in range(1, 5)
    ]
    _write_entries(history_path, entries)

    status = get_ingredient_routing_probation_gate_status(
        history_path=history_path,
        matcher_version="matcher-x",
        recipe_compiler_version="recipe-x",
        offer_compiler_version="offer-x",
        min_ready_streak=4,
        min_version_ready_runs=4,
        recommended_distinct_versions=1,
    )
    test("gate opens when streak and version counts are green", status["ready"], True)
    test("ready gate has no hard reasons", status["reasons"], [])
    test("ready streak is counted", status["summary"]["current_ready_streak"], 4)

with tempfile.TemporaryDirectory() as tmp_dir:
    history_path = Path(tmp_dir) / "ingredient_routing_probation.jsonl"
    status = get_ingredient_routing_probation_gate_status(
        history_path=history_path,
        matcher_version="matcher-x",
        recipe_compiler_version="recipe-x",
        offer_compiler_version="offer-x",
        min_ready_streak=1,
        min_version_ready_runs=1,
        recommended_distinct_versions=1,
    )
    test("missing history blocks gate", status["ready"], False)
    test("missing history reason is reported", "history_missing" in status["reasons"], True)

with tempfile.TemporaryDirectory() as tmp_dir:
    history_path = Path(tmp_dir) / "ingredient_routing_probation.jsonl"
    append_ingredient_routing_probation_history(
        {
            "matcher_version": "matcher-x",
            "recipe_compiler_version": "recipe-x",
            "offer_compiler_version": "offer-x",
            "ingredient_routing_mode": "probation",
            "ingredient_routing_effective_mode": "probation",
            "ingredient_routing_shadow_measured": True,
            "shadow_unexplained_miss_count": 0,
            "shadow_candidate_change_count": 3,
            "shadow_fallback_reason_counts": {"validated_candidate_change": 3},
        },
        history_path=history_path,
    )
    append_ingredient_routing_probation_history(
        {
            "matcher_version": "matcher-x",
            "recipe_compiler_version": "recipe-x",
            "offer_compiler_version": "offer-x",
            "ingredient_routing_mode": "shadow",
            "ingredient_routing_effective_mode": "shadow",
            "ingredient_routing_shadow_measured": True,
            "shadow_unexplained_miss_count": 0,
            "shadow_candidate_change_count": 0,
        },
        history_path=history_path,
    )
    entries = load_ingredient_routing_probation_history(history_path)
    status = get_ingredient_routing_probation_gate_status(
        history_path=history_path,
        matcher_version="matcher-x",
        recipe_compiler_version="recipe-x",
        offer_compiler_version="offer-x",
        min_ready_streak=1,
        min_version_ready_runs=1,
        recommended_distinct_versions=1,
    )
    test("history append writes entries", len(entries), 2)
    test("shadow entries are neutral and not counted", entries[-1]["probation_countable"], False)
    test("neutral ready entries do not break streak", status["summary"]["current_ready_streak"], 1)

with tempfile.TemporaryDirectory() as tmp_dir:
    history_path = Path(tmp_dir) / "ingredient_routing_probation.jsonl"
    append_ingredient_routing_probation_history(
        {
            "matcher_version": "matcher-x",
            "recipe_compiler_version": "recipe-x",
            "offer_compiler_version": "offer-x",
            "ingredient_routing_mode": "hint_first",
            "ingredient_routing_effective_mode": "probation",
            "ingredient_routing_shadow_measured": True,
            "shadow_unexplained_miss_count": 0,
        },
        history_path=history_path,
    )
    entries = load_ingredient_routing_probation_history(history_path)
    status = get_ingredient_routing_probation_gate_status(
        history_path=history_path,
        matcher_version="matcher-x",
        recipe_compiler_version="recipe-x",
        offer_compiler_version="offer-x",
        min_ready_streak=1,
        min_version_ready_runs=1,
        recommended_distinct_versions=1,
    )
    test("hint_first fallback probation entries are countable", entries[-1]["probation_countable"], True)
    test("hint_first fallback probation can open gate", status["ready"], True)

with tempfile.TemporaryDirectory() as tmp_dir:
    history_path = Path(tmp_dir) / "ingredient_routing_probation.jsonl"
    append_ingredient_routing_probation_history(
        {
            "matcher_version": "matcher-x",
            "recipe_compiler_version": "recipe-x",
            "offer_compiler_version": "offer-x",
            "ingredient_routing_mode": "probation",
            "ingredient_routing_effective_mode": "probation",
            "ingredient_routing_shadow_measured": True,
            "shadow_unexplained_miss_count": 1,
        },
        history_path=history_path,
    )
    status = get_ingredient_routing_probation_gate_status(
        history_path=history_path,
        matcher_version="matcher-x",
        recipe_compiler_version="recipe-x",
        offer_compiler_version="offer-x",
        min_ready_streak=1,
        min_version_ready_runs=1,
        recommended_distinct_versions=1,
    )
    test("unexplained mismatch blocks readiness", status["ready"], False)
    test("unexplained mismatch reason is reported", "latest_unexplained_mismatch" in status["reasons"], True)


print("\n========================================")
print(f"TOTAL: {passed}/{passed + failed} checks passed")
if failed:
    print(f"{failed} FAILED!")
    print("========================================")
    raise SystemExit(1)

print("ALL PASSED!")
print("========================================")
