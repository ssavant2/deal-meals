#!/usr/bin/env python3
"""Policy checks for matcher-layer parity runner."""

from __future__ import annotations

from pathlib import Path
import sys


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from support_checks.run_matcher_layer_fixture_cases import _load_fixture_payload  # noqa: E402
from support_checks.run_matcher_layer_parity import DEFAULT_FIXTURE_FILE, run_parity  # noqa: E402


def check(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"OK {name}")


def main() -> int:
    report = run_parity(_load_fixture_payload(Path(DEFAULT_FIXTURE_FILE)))
    summary = report["summary"]
    check("case count", summary["cases"], 1480)
    check("passed count", summary["passed"], 1480)
    check("failed count", summary["failed"], 0)
    check("parity mismatches", summary["parity_mismatches"], 0)
    check("allowed additional matches used", summary["allowed_additional_matches_used"], 0)
    check("compiled hint-first fallbacks", summary["compiled_hint_first_fullscan_fallbacks"], 0)
    check(
        "compiled hint-first fallback reasons",
        summary["compiled_hint_first_fallback_reason_counts"],
        {},
    )
    check("compiled hint-first fallback case count", summary["compiled_hint_first_fallback_case_count"], 0)
    check("compiled hint-first fallback expected counts", summary["compiled_hint_first_fallback_expected_counts"], {})
    check(
        "compiled hint-first fallback source prefixes",
        summary["compiled_hint_first_fallback_source_prefix_counts"],
        {},
    )
    check("duplicate signal source", summary["duplicate_signal_source"], 0)
    check("ambiguous canonical", summary["ambiguous_canonical"], 0)
    check("live path failures", report["by_path"]["live_fullscan"]["failed"], 0)
    check("compiled fullscan failures", report["by_path"]["compiled_fullscan"]["failed"], 0)
    check("compiled routed failures", report["by_path"]["compiled_routed"]["failed"], 0)
    check("compiled hint-first failures", report["by_path"]["compiled_hint_first"]["failed"], 0)
    check("diagnosis counts", report["diagnosis_counts"], {"pass": 1480})

    filtered_report = run_parity(
        _load_fixture_payload(Path(DEFAULT_FIXTURE_FILE)),
        policy_refs={"current_queue_matcher_regression"},
        canonicals={"alger"},
        diagnosis_classes={"pass"},
    )
    check("filtered parity case count", filtered_report["summary"]["cases"], 1)
    check("filtered parity passed count", filtered_report["summary"]["passed"], 1)
    check(
        "filtered parity result ids",
        [result["id"] for result in filtered_report["results"]],
        ["matcher_regression_alger_nori_positive"],
    )

    print("ALL MATCHER LAYER PARITY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
