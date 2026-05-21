#!/usr/bin/env python3
"""Policy checks for scraper health and quality-gate readiness helpers."""

from __future__ import annotations

from pathlib import Path
import sys


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from utils.scraper_health import (  # noqa: E402
    ScraperHealthRow,
    configured_quality_gate_mode,
    evaluate_recipe_quality_gate,
    summarize_scraper_health,
)


def check(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"OK {name}")


def _row(candidate_count: int, *, status: str = "success") -> ScraperHealthRow:
    return ScraperHealthRow(
        scraper_id="mathem",
        mode="incremental",
        success=status == "success",
        status=status,
        candidate_count=candidate_count,
        parsed_count=max(0, candidate_count - 2),
        parse_rate=0.90,
        data_path="robots_sitemap",
    )


def main() -> int:
    env = {
        "SCRAPER_QUALITY_GATES": "auto",
        "SCRAPER_QUALITY_GATE_OVERRIDES": "mathem=off,recipe:arla=enforce,*=observe",
    }
    check("quality override exact source", configured_quality_gate_mode("mathem", env=env), "off")
    check("quality override kind/source", configured_quality_gate_mode("arla", env=env), "enforce")
    check("quality override wildcard", configured_quality_gate_mode("coop", env=env), "observe")
    check(
        "quality default auto",
        configured_quality_gate_mode("coop", env={"SCRAPER_QUALITY_GATES": "auto"}),
        "auto",
    )
    check(
        "quality invalid default falls back to auto",
        configured_quality_gate_mode("coop", env={"SCRAPER_QUALITY_GATES": "banana"}),
        "auto",
    )

    empty = summarize_scraper_health("mathem", [], env={"SCRAPER_QUALITY_GATES": "auto"})
    check("empty history status", empty["status"], "no_history")
    check("empty history effective auto mode", empty["effective_gate_mode"], "observe")

    five_runs = [_row(count) for count in [102, 100, 98, 101, 99]]
    ready = summarize_scraper_health("mathem", five_runs, env={"SCRAPER_QUALITY_GATES": "auto"})
    check("five successful metric runs ready", ready["ready_for_enforcing"], True)
    check("auto mode enforces when ready", ready["effective_gate_mode"], "enforce")
    check("ready label", ready["label_key"], "recipes.health_ready")

    stable_three = [_row(count) for count in [102, 100, 98]]
    stable = summarize_scraper_health("mathem", stable_three, env={"SCRAPER_QUALITY_GATES": "auto"})
    check("three stable runs ready", stable["ready_for_enforcing"], True)

    unstable_three = [_row(count) for count in [150, 100, 80]]
    burn_in = summarize_scraper_health("mathem", unstable_three, env={"SCRAPER_QUALITY_GATES": "auto"})
    check("three unstable runs stay burn-in", burn_in["ready_for_enforcing"], False)
    check("burn-in effective mode", burn_in["effective_gate_mode"], "observe")
    check("burn-in label", burn_in["label_key"], "recipes.health_burn_in")

    failed_latest = [_row(100, status="failed"), _row(100), _row(101), _row(99), _row(100), _row(100)]
    failed = summarize_scraper_health("mathem", failed_latest, env={"SCRAPER_QUALITY_GATES": "auto"})
    check("latest failed status wins", failed["status"], "latest_failed")
    check("latest failed keeps readiness", failed["ready_for_enforcing"], True)
    check("latest failed label", failed["label_key"], "recipes.health_latest_failed")

    forced_off = summarize_scraper_health("mathem", five_runs, env={"SCRAPER_QUALITY_GATES": "off"})
    check("forced off mode", forced_off["effective_gate_mode"], "off")

    current_low_canary = _row(400)
    canary_decision = evaluate_recipe_quality_gate(
        "mathem",
        current_low_canary,
        five_runs,
        expected_min_urls=1000,
        env={"SCRAPER_QUALITY_GATES": "observe"},
    )
    check("expected-min canary would block", canary_decision["would_block"], True)
    check(
        "expected-min canary reason",
        canary_decision["reason_code"],
        "recipe_discovery_expected_min_canary",
    )
    check("observe canary does not enforce", canary_decision["should_block"], False)

    current_low_history = _row(65)
    history_decision = evaluate_recipe_quality_gate(
        "mathem",
        current_low_history,
        five_runs,
        env={"SCRAPER_QUALITY_GATES": "enforce"},
    )
    check("history low count would block", history_decision["would_block"], True)
    check("history low count enforces", history_decision["should_block"], True)
    check("history low count reason", history_decision["reason_code"], "recipe_discovery_count_too_low")

    no_candidate_decision = evaluate_recipe_quality_gate(
        "mathem",
        ScraperHealthRow(scraper_id="mathem", status="success"),
        five_runs,
        expected_min_urls=1000,
        env={"SCRAPER_QUALITY_GATES": "enforce"},
    )
    check("missing candidate count does not block", no_candidate_decision["would_block"], False)

    print("ALL SCRAPER HEALTH CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
