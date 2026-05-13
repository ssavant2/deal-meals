#!/usr/bin/env python3
"""Checks for runtime delta probation gating helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile


sys.path.insert(0, "/app" if os.path.exists("/app") else os.path.join(os.path.dirname(__file__), ".."))

from delta_probation_runtime import (  # noqa: E402
    append_runtime_probation_history,
    get_delta_probation_gate_status,
    load_probation_history,
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


def test_in(desc: str, needle: str, haystack: list[str]) -> None:
    test(desc, needle in haystack, True)


def _write_entries(history_path: Path, entries: list[dict]) -> None:
    history_path.write_text(
        "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in entries),
        encoding="utf-8",
    )


with tempfile.TemporaryDirectory() as tmp_dir:
    history_path = Path(tmp_dir) / "delta_probation_history.jsonl"
    entries = [
        {
            "generated_at": f"2026-04-2{i}T12:00:00+00:00",
            "matcher_version": "matcher-x",
            "recipe_compiler_version": "recipe-x",
            "offer_compiler_version": "offer-x",
            "ready_for_manual_live_apply": True,
        }
        for i in range(1, 5)
    ]
    _write_entries(history_path, entries)
    status = get_delta_probation_gate_status(
        history_path=history_path,
        matcher_version="matcher-x",
        recipe_compiler_version="recipe-x",
        offer_compiler_version="offer-x",
        min_ready_streak=4,
        min_version_ready_runs=3,
    )
    test("gate ready when streak and version counts are green", status["ready"], True)
    test("ready current streak", status["summary"]["current_ready_streak"], 4)
    test("ready current version count", status["summary"]["current_version_ready_run_count"], 4)
    test("ready reasons empty", status["reasons"], [])

with tempfile.TemporaryDirectory() as tmp_dir:
    status = get_delta_probation_gate_status(
        history_path=Path(tmp_dir) / "missing.jsonl",
        matcher_version="matcher-x",
        recipe_compiler_version="recipe-x",
        offer_compiler_version="offer-x",
        min_ready_streak=1,
        min_version_ready_runs=1,
    )
    test("missing history blocks gate", status["ready"], False)
    test_in("missing history reason", "history_missing", status["reasons"])
    test_in("missing streak reason", "insufficient_ready_streak", status["reasons"])
    test_in("missing version reason", "insufficient_current_version_ready_runs", status["reasons"])

with tempfile.TemporaryDirectory() as tmp_dir:
    history_path = Path(tmp_dir) / "delta_probation_history.jsonl"
    _write_entries(
        history_path,
        [
            {
                "generated_at": "2026-04-20T12:00:00+00:00",
                "matcher_version": "matcher-old",
                "recipe_compiler_version": "recipe-old",
                "offer_compiler_version": "offer-old",
                "ready_for_manual_live_apply": True,
            },
            {
                "generated_at": "2026-04-21T12:00:00+00:00",
                "matcher_version": "matcher-new",
                "recipe_compiler_version": "recipe-new",
                "offer_compiler_version": "offer-new",
                "ready_for_manual_live_apply": True,
            },
        ],
    )
    status = get_delta_probation_gate_status(
        history_path=history_path,
        matcher_version="matcher-new",
        recipe_compiler_version="recipe-new",
        offer_compiler_version="offer-new",
        min_ready_streak=2,
        min_version_ready_runs=2,
    )
    test("too few current-version runs blocks gate", status["ready"], False)
    test_in("too few current-version reason", "insufficient_current_version_ready_runs", status["reasons"])
    test("too few current-version streak", status["summary"]["current_ready_streak"], 2)
    test("too few current-version count", status["summary"]["current_version_ready_run_count"], 1)

with tempfile.TemporaryDirectory() as tmp_dir:
    history_path = Path(tmp_dir) / "delta_probation_history.jsonl"
    append_runtime_probation_history(
        {
            "matcher_version": "matcher-x",
            "recipe_compiler_version": "recipe-x",
            "offer_compiler_version": "offer-x",
            "ready_to_apply": True,
            "applied": False,
            "effective_rebuild_mode": "delta",
            "effective_verify_full_preview": True,
            "verify_full_preview": True,
            "verification_mode": "full_preview",
            "materialized_patch_matches_full_preview": True,
        },
        history_path=history_path,
    )
    append_runtime_probation_history(
        {
            "matcher_version": "matcher-x",
            "recipe_compiler_version": "recipe-x",
            "offer_compiler_version": "offer-x",
            "ready_to_apply": True,
            "applied": False,
            "effective_rebuild_mode": "delta",
            "effective_verify_full_preview": False,
            "verify_full_preview": True,
            "verification_mode": "probation_skip",
            "materialized_patch_matches_full_preview": True,
        },
        history_path=history_path,
    )
    status = get_delta_probation_gate_status(
        history_path=history_path,
        matcher_version="matcher-x",
        recipe_compiler_version="recipe-x",
        offer_compiler_version="offer-x",
        min_ready_streak=1,
        min_version_ready_runs=1,
    )
    test("only full-preview verified runs count", status["ready"], True)
    test("counted ready runs", status["summary"]["ready_run_count"], 1)
    test("latest probation skip not countable", status["latest_entry"]["probation_countable"], False)

with tempfile.TemporaryDirectory() as tmp_dir:
    history_path = Path(tmp_dir) / "delta_probation_history.jsonl"
    for index in range(1005):
        append_runtime_probation_history(
            {
                "matcher_version": "matcher-x",
                "recipe_compiler_version": "recipe-x",
                "offer_compiler_version": "offer-x",
                "ready_to_apply": True,
                "applied": False,
                "effective_rebuild_mode": "delta",
                "effective_verify_full_preview": True,
                "verify_full_preview": True,
                "verification_mode": "full_preview",
                "materialized_patch_matches_full_preview": True,
            },
            history_path=history_path,
            store_name=f"store-{index}",
        )
    entries = load_probation_history(history_path)
    test("probation history keeps latest 1000 entries", len(entries), 1000)
    test("probation history drops oldest entries", entries[0]["store_name"], "store-5")
    test("probation history keeps newest entry", entries[-1]["store_name"], "store-1004")


print("\n========================================")
print(f"TOTAL: {passed}/{passed + failed} checks passed")
if failed:
    print(f"{failed} FAILED!")
    print("========================================")
    raise SystemExit(1)

print("ALL DELTA PROBATION RUNTIME CHECKS PASSED")
print("========================================")
