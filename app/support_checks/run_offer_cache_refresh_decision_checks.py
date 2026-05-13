#!/usr/bin/env python3
"""Tracked checks for stable offer-refresh cache decisions.

Run:
    docker compose exec -T -w /app web python support_checks/run_offer_cache_refresh_decision_checks.py
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys

sys.path.insert(0, '/app' if os.path.exists('/app') else os.path.join(os.path.dirname(__file__), '..'))

from languages.matcher_runtime import (  # noqa: E402
    MATCHER_VERSION,
    OFFER_COMPILER_VERSION,
    RECIPE_COMPILER_VERSION,
    plan_offer_delta_recipe_impacts,
)
from config import settings  # noqa: E402
from offer_cache_refresh_decision import (  # noqa: E402
    OfferCacheStatusSnapshot,
    OfferRefreshMetrics,
    decide_offer_cache_refresh_strategy,
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


def snapshot(**overrides):
    data = {
        "status": "ready",
        "metadata_total_matches": 1000,
        "metadata_total_recipes": 1000,
        "cache_rows": 1000,
        "offer_rows": 100,
        "compiled_offer_baseline_committed": True,
        "last_operation": {
            "matcher_version": MATCHER_VERSION,
            "recipe_compiler_version": RECIPE_COMPILER_VERSION,
            "offer_compiler_version": OFFER_COMPILER_VERSION,
            "offer_data_source": "compiled",
            "recipe_data_source": "compiled_payload",
            "candidate_data_source": settings.cache_rebuild_candidate_data_source,
        },
        "baseline_column_available": True,
    }
    data.update(overrides)
    return OfferCacheStatusSnapshot(**data)


def metrics(**overrides):
    data = {
        "store_name": "Willys",
        "offer_replaces_all": True,
        "current_offer_count": 100,
        "persisted_offer_count": 100,
        "changed_offer_count": 0,
        "changed_offer_ratio_pct": 0.0,
        "impacted_recipe_count": 0,
        "active_recipe_count": 1000,
        "impacted_recipe_ratio_pct": 0.0,
        "early_full_triggered": False,
        "offer_changes": {"counts": {}},
        "recipe_changes": {"counts": {}},
        "combined_planner_counts": {},
        "planner_time_ms": 1,
    }
    data.update(overrides)
    return OfferRefreshMetrics(**data)


def run_policy_checks() -> None:
    decision = decide_offer_cache_refresh_strategy(
        store_name="Willys",
        cache_status_snapshot=snapshot(),
        metrics=metrics(),
    )
    test("identical offers skip", (decision.strategy, decision.reason), ("skip", "offer_set_unchanged"))

    decision = decide_offer_cache_refresh_strategy(
        store_name="Willys",
        cache_status_snapshot=snapshot(compiled_offer_baseline_committed=False),
        metrics=metrics(),
    )
    test("incoherent baseline full", (decision.strategy, decision.reason), ("full", "offer_baseline_incoherent"))

    decision = decide_offer_cache_refresh_strategy(
        store_name="Willys",
        cache_status_snapshot=snapshot(),
        metrics=metrics(
            changed_offer_count=60,
            changed_offer_ratio_pct=60.0,
            impacted_recipe_count=None,
            impacted_recipe_ratio_pct=None,
            early_full_triggered=True,
        ),
    )
    test(
        "early full by offer ratio only when impact is unknown",
        (decision.strategy, decision.reason),
        ("full", "changed_offer_ratio_above_threshold"),
    )

    decision = decide_offer_cache_refresh_strategy(
        store_name="Small Store",
        cache_status_snapshot=snapshot(),
        metrics=metrics(
            current_offer_count=15,
            persisted_offer_count=15,
            changed_offer_count=8,
            changed_offer_ratio_pct=53.3333,
            impacted_recipe_count=50,
            impacted_recipe_ratio_pct=5.0,
            early_full_triggered=False,
        ),
    )
    test(
        "high changed-offer ratio still deltas when recipe impact is small",
        (decision.strategy, decision.reason),
        ("delta", "impact_within_threshold"),
    )

    decision = decide_offer_cache_refresh_strategy(
        store_name="Willys",
        cache_status_snapshot=snapshot(),
        metrics=metrics(
            changed_offer_count=2,
            changed_offer_ratio_pct=2.0,
            impacted_recipe_count=0,
            impacted_recipe_ratio_pct=0.0,
            changed_offer_sample=[{"kind": "removed", "name": "Schampo"}],
            offer_change_counts={"removed": 2},
            combined_planner_counts={"impact_mode": "fast_sql", "all_impacted_recipes": 0},
            impact_mode="fast_sql",
        ),
    )
    test(
        "changed offers with no cache impact skip recipe cache work",
        (decision.strategy, decision.reason),
        ("skip", "offer_changes_no_cache_impact"),
    )

    decision = decide_offer_cache_refresh_strategy(
        store_name="Willys",
        cache_status_snapshot=snapshot(),
        metrics=metrics(
            changed_offer_count=10,
            changed_offer_ratio_pct=10.0,
            impacted_recipe_count=100,
            impacted_recipe_ratio_pct=10.0,
            changed_offer_sample=[{"kind": "score_changed", "name": "Mjölk", "price": "12.00"}],
            offer_change_counts={"score_changed": 10},
            combined_planner_counts={"impact_mode": "fast_sql", "all_impacted_recipes": 100},
            impact_mode="fast_sql",
        ),
    )
    test("small impact delta", (decision.strategy, decision.reason), ("delta", "impact_within_threshold"))
    context = decision.to_operation_context()
    test("operation context keeps changed offer sample", context["changed_offer_sample"][0]["name"], "Mjölk")
    test("operation context keeps offer change counts", context["offer_change_counts"]["score_changed"], 10)
    test("operation context keeps impact mode", context["offer_delta_impact_mode"], "fast_sql")

    decision = decide_offer_cache_refresh_strategy(
        store_name="Willys",
        cache_status_snapshot=snapshot(),
        metrics=metrics(
            changed_offer_count=10,
            changed_offer_ratio_pct=10.0,
            impacted_recipe_count=200,
            impacted_recipe_ratio_pct=20.0,
        ),
    )
    test("large impact full", (decision.strategy, decision.reason), ("full", "impact_above_threshold"))

    decision = decide_offer_cache_refresh_strategy(
        store_name="Willys",
        cache_status_snapshot=snapshot(last_operation={}),
        metrics=metrics(),
    )
    test(
        "identical offers with missing profile full",
        (decision.strategy, decision.reason),
        ("full", "offer_set_unchanged_cache_profile_mismatch"),
    )

    decision = decide_offer_cache_refresh_strategy(
        store_name="Willys",
        cache_status_snapshot=snapshot(),
        metrics=metrics(
            changed_offer_count=0,
            changed_offer_ratio_pct=0.0,
            impacted_recipe_count=1,
            impacted_recipe_ratio_pct=0.1,
            recipe_changes={"all_impacted_recipe_ids": ["recipe-1"], "counts": {"all_impacted": 1}},
        ),
    )
    test(
        "recipe changes block no-op skip",
        (decision.strategy, decision.reason),
        ("full", "recipe_changes_detected"),
    )


def run_stale_id_audit() -> None:
    root = Path('/app' if os.path.exists('/app') else Path(__file__).resolve().parents[1])
    search_roots = [root / "static", root / "templates"]
    patterns = [
        re.compile(r"matched_offers\s*(?:\[[^\]]+\])?\s*\.\s*id"),
        re.compile(r"\boffer\s*\.\s*id\b"),
        re.compile(r"\bofferId\b"),
        re.compile(r"\boffer_id\b"),
    ]

    matches: list[str] = []
    for search_root in search_roots:
        if not search_root.exists():
            continue
        for path in search_root.rglob("*"):
            if not path.is_file() or path.suffix not in {".html", ".js", ".css"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except PermissionError:
                print(f"Skipping unreadable file for stale-ID audit: {path.relative_to(root)}")
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if any(pattern.search(line) for pattern in patterns):
                    matches.append(f"{path.relative_to(root)}:{lineno}: {line.strip()}")

    test("frontend/template stale offer UUID audit", matches, [])


run_policy_checks()

planner = plan_offer_delta_recipe_impacts(
    {
        "added_offer_ids": [],
        "removed_offer_ids": ["removed-milk"],
        "match_changed_offer_ids": [],
        "forced_version_rematch_offer_ids": [],
        "rescore_offer_ids": [],
        "display_only_offer_ids": [],
    },
    current_offer_term_postings={},
    persisted_offer_term_postings={"naturell": {"removed-milk"}},
    current_recipe_term_postings={"naturell": {"cached-recipe", "unmatched-recipe"}},
    persisted_recipe_term_postings={"naturell": {"cached-recipe", "unmatched-recipe"}},
    persisted_offer_recipe_map={"removed-milk": {"cached-recipe"}},
)
test(
    "removed offers rematch cached recipes only",
    planner["rematch_recipe_ids"],
    ["cached-recipe"],
)
test(
    "removed offers still report removed-offer recipe count",
    planner["counts"]["removed_offer_recipes"],
    1,
)

run_stale_id_audit()

print("\n========================================")
print(f"TOTAL: {passed}/{passed + failed} checks passed")
if failed:
    print(f"{failed} FAILED!")
    print("========================================")
    raise SystemExit(1)

print("ALL PASSED!")
print("========================================")
