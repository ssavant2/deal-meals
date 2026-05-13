#!/usr/bin/env python3
"""Synthetic checks for offer/recipe delta classification and impact planning."""

from __future__ import annotations

import os
import sys


sys.path.insert(0, "/app" if os.path.exists("/app") else os.path.join(os.path.dirname(__file__), ".."))

from languages.sv.ingredient_matching import (  # noqa: E402
    classify_offer_change_sets,
    classify_recipe_change_sets,
    plan_combined_delta_recipe_impacts,
)
from languages.sv.ingredient_matching.delta_planner import (  # noqa: E402
    invert_term_postings,
    plan_offer_delta_recipe_impacts,
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


offer_summary = classify_offer_change_sets(
    current_rows_by_offer_id={
        "added": {"compiler_version": "offer-v1", "offer_match_hash": "m-added", "offer_score_hash": "s-added", "offer_display_hash": "d-added"},
        "match": {"compiler_version": "offer-v1", "offer_match_hash": "m-new", "offer_score_hash": "s-same", "offer_display_hash": "d-same"},
        "score": {"compiler_version": "offer-v1", "offer_match_hash": "m-same", "offer_score_hash": "s-new", "offer_display_hash": "d-same"},
        "display": {"compiler_version": "offer-v1", "offer_match_hash": "m-same", "offer_score_hash": "s-same", "offer_display_hash": "d-new"},
        "unchanged": {"compiler_version": "offer-v1", "offer_match_hash": "m-same", "offer_score_hash": "s-same", "offer_display_hash": "d-same"},
        "reactivated": {"compiler_version": "offer-v1", "offer_match_hash": "m-old", "offer_score_hash": "s-old", "offer_display_hash": "d-old"},
        "version": {"compiler_version": "offer-v2", "offer_match_hash": "m-old", "offer_score_hash": "s-old", "offer_display_hash": "d-old"},
    },
    persisted_rows_by_offer_id={
        "match": {"compiler_version": "offer-v1", "offer_match_hash": "m-old", "offer_score_hash": "s-same", "offer_display_hash": "d-same", "is_active": True},
        "score": {"compiler_version": "offer-v1", "offer_match_hash": "m-same", "offer_score_hash": "s-old", "offer_display_hash": "d-same", "is_active": True},
        "display": {"compiler_version": "offer-v1", "offer_match_hash": "m-same", "offer_score_hash": "s-same", "offer_display_hash": "d-old", "is_active": True},
        "unchanged": {"compiler_version": "offer-v1", "offer_match_hash": "m-same", "offer_score_hash": "s-same", "offer_display_hash": "d-same", "is_active": True},
        "removed": {"compiler_version": "offer-v1", "offer_match_hash": "m-removed", "offer_score_hash": "s-removed", "offer_display_hash": "d-removed", "is_active": True},
        "reactivated": {"compiler_version": "offer-v1", "offer_match_hash": "m-old", "offer_score_hash": "s-old", "offer_display_hash": "d-old", "is_active": False},
        "version": {"compiler_version": "offer-v1", "offer_match_hash": "m-old", "offer_score_hash": "s-old", "offer_display_hash": "d-old", "is_active": True},
        "inactive_gone": {"compiler_version": "offer-v1", "offer_match_hash": "m-ignored", "offer_score_hash": "s-ignored", "offer_display_hash": "d-ignored", "is_active": False},
    },
)
test("offer added ids", offer_summary["added_offer_ids"], ["added", "reactivated"])
test("offer removed ids", offer_summary["removed_offer_ids"], ["removed"])
test("offer match changed ids", offer_summary["match_changed_offer_ids"], ["match"])
test("offer score changed ids", offer_summary["score_changed_offer_ids"], ["score"])
test("offer display changed ids", offer_summary["display_changed_offer_ids"], ["display"])
test("offer version mismatch ids", offer_summary["version_mismatch_offer_ids"], ["version"])
test("offer unchanged ids", offer_summary["unchanged_offer_ids"], ["unchanged"])
test("offer rematch ids", offer_summary["rematch_offer_ids"], ["added", "match", "reactivated", "removed", "version"])
test("offer rescore ids", offer_summary["rescore_offer_ids"], ["score"])
test("offer display only ids", offer_summary["display_only_offer_ids"], ["display"])

recipe_summary = classify_recipe_change_sets(
    current_rows_by_recipe_id={
        "added": {"found_recipe_id": "added", "compiler_version": "recipe-v1", "recipe_source_hash": "h-added", "is_active": True},
        "changed": {"found_recipe_id": "changed", "compiler_version": "recipe-v1", "recipe_source_hash": "h-new", "is_active": True},
        "version": {"found_recipe_id": "version", "compiler_version": "recipe-v2", "recipe_source_hash": "h-same", "is_active": True},
        "unchanged": {"found_recipe_id": "unchanged", "compiler_version": "recipe-v1", "recipe_source_hash": "h-same", "is_active": True},
        "reactivated": {"found_recipe_id": "reactivated", "compiler_version": "recipe-v1", "recipe_source_hash": "h-old", "is_active": True},
        "inactive_same": {"found_recipe_id": "inactive_same", "compiler_version": "recipe-v1", "recipe_source_hash": "h-inactive", "is_active": False},
        "inactive_removed": {"found_recipe_id": "inactive_removed", "compiler_version": "recipe-v1", "recipe_source_hash": "h-old", "is_active": False},
        "rekeyed": {"found_recipe_id": "recipe-new", "compiler_version": "recipe-v1", "recipe_source_hash": "h-same", "is_active": True},
    },
    persisted_rows_by_recipe_id={
        "changed": {"found_recipe_id": "changed", "compiler_version": "recipe-v1", "recipe_source_hash": "h-old", "is_active": True},
        "version": {"found_recipe_id": "version", "compiler_version": "recipe-v1", "recipe_source_hash": "h-same", "is_active": True},
        "unchanged": {"found_recipe_id": "unchanged", "compiler_version": "recipe-v1", "recipe_source_hash": "h-same", "is_active": True},
        "removed": {"found_recipe_id": "removed", "compiler_version": "recipe-v1", "recipe_source_hash": "h-removed", "is_active": True},
        "reactivated": {"found_recipe_id": "reactivated", "compiler_version": "recipe-v1", "recipe_source_hash": "h-old", "is_active": False},
        "inactive_same": {"found_recipe_id": "inactive_same", "compiler_version": "recipe-v1", "recipe_source_hash": "h-inactive", "is_active": False},
        "inactive_removed": {"found_recipe_id": "recipe-inactive-old", "compiler_version": "recipe-v1", "recipe_source_hash": "h-old", "is_active": True},
        "rekeyed": {"found_recipe_id": "recipe-old", "compiler_version": "recipe-v1", "recipe_source_hash": "h-same", "is_active": True},
    },
)
test("recipe added ids", recipe_summary["added_recipe_ids"], ["added", "reactivated"])
test("recipe removed ids", recipe_summary["removed_recipe_ids"], ["recipe-inactive-old", "removed"])
test("recipe source changed ids", recipe_summary["source_changed_recipe_ids"], ["changed"])
test("recipe version mismatch ids", recipe_summary["version_mismatch_recipe_ids"], ["version"])
test("recipe id changed current ids", recipe_summary["id_changed_current_recipe_ids"], ["recipe-new"])
test("recipe id changed removed ids", recipe_summary["id_changed_removed_recipe_ids"], ["recipe-old"])
test("recipe unchanged ids", recipe_summary["unchanged_recipe_ids"], ["inactive_same", "unchanged"])
test("recipe rematch ids", recipe_summary["rematch_recipe_ids"], ["added", "changed", "reactivated", "recipe-new", "version"])
test("recipe remove ids", recipe_summary["remove_recipe_ids"], ["recipe-inactive-old", "recipe-old", "removed"])

current_offer_term_postings = {
    "term-a-new": {"offer-add"},
    "term-a": {"offer-match"},
    "term-b": {"offer-version"},
    "term-c": {"offer-score"},
    "term-d": {"offer-display"},
}
persisted_offer_term_postings = {
    "term-a-old": {"offer-add"},
    "term-a": {"offer-match"},
    "term-b": {"offer-version"},
    "term-c": {"offer-score"},
    "term-d": {"offer-display"},
}
current_recipe_term_postings = {
    "term-a": {"recipe-1"},
    "term-a-new": {"recipe-7"},
    "term-b": {"recipe-3"},
    "term-c": {"recipe-4"},
    "term-d": {"recipe-5"},
}
persisted_recipe_term_postings = {
    "term-a": {"recipe-1"},
    "term-a-old": {"recipe-2"},
    "term-b": {"recipe-3"},
    "term-c": {"recipe-4"},
    "term-d": {"recipe-5"},
}
persisted_offer_recipe_map = {
    "offer-score": {"recipe-4", "recipe-6"},
    "offer-display": {"recipe-5", "recipe-6"},
}
planner = plan_offer_delta_recipe_impacts(
    {
        "added_offer_ids": ["offer-add"],
        "match_changed_offer_ids": ["offer-match"],
        "forced_version_rematch_offer_ids": ["offer-version"],
        "rescore_offer_ids": ["offer-score"],
        "display_only_offer_ids": ["offer-display"],
    },
    current_offer_term_postings=current_offer_term_postings,
    persisted_offer_term_postings=persisted_offer_term_postings,
    current_recipe_term_postings=current_recipe_term_postings,
    persisted_recipe_term_postings=persisted_recipe_term_postings,
    persisted_offer_recipe_map=persisted_offer_recipe_map,
)
test("invert term postings", invert_term_postings({"x": {"a", "b"}, "y": {"b"}}), {"a": {"x"}, "b": {"x", "y"}})
test("semantic rematch recipe ids", planner["semantic_rematch_recipe_ids"], ["recipe-1", "recipe-2", "recipe-7"])
test("semantic rematch terms", planner["semantic_rematch_terms"], ["term-a", "term-a-new", "term-a-old"])
test("forced version rematch recipe ids", planner["forced_version_rematch_recipe_ids"], ["recipe-3"])
test("forced version rematch terms", planner["forced_version_rematch_terms"], ["term-b"])
test("rematch recipe ids", planner["rematch_recipe_ids"], ["recipe-1", "recipe-2", "recipe-3", "recipe-7"])
test("raw rescore recipe ids", planner["raw_rescore_recipe_ids"], ["recipe-4", "recipe-6"])
test("effective rescore recipe ids", planner["effective_rescore_recipe_ids"], ["recipe-4", "recipe-6"])
test("raw display recipe ids", planner["raw_display_only_recipe_ids"], ["recipe-5", "recipe-6"])
test("effective display recipe ids", planner["effective_display_only_recipe_ids"], ["recipe-5"])
test("all impacted recipe ids", planner["all_impacted_recipe_ids"], ["recipe-1", "recipe-2", "recipe-3", "recipe-4", "recipe-5", "recipe-6", "recipe-7"])

combined = plan_combined_delta_recipe_impacts(
    {
        "rematch_recipe_ids": ["r1", "r2"],
        "effective_rescore_recipe_ids": ["r2", "r3", "r-remove"],
        "effective_display_only_recipe_ids": ["r3", "r4", "r-remove"],
    },
    {
        "semantic_rematch_recipe_ids": ["r5"],
        "forced_version_rematch_recipe_ids": ["r6"],
        "rematch_recipe_ids": ["r5", "r6"],
        "remove_recipe_ids": ["r-remove", "r-old"],
    },
)
test("combined rematch ids", combined["rematch_recipe_ids"], ["r1", "r2", "r5", "r6"])
test("combined remove ids", combined["remove_recipe_ids"], ["r-old", "r-remove"])
test("combined effective rescore ids", combined["effective_rescore_recipe_ids"], ["r3"])
test("combined effective display ids", combined["effective_display_only_recipe_ids"], ["r4"])
test("combined all impacted ids", combined["all_impacted_recipe_ids"], ["r-old", "r-remove", "r1", "r2", "r3", "r4", "r5", "r6"])


print("\n========================================")
print(f"TOTAL: {passed}/{passed + failed} checks passed")
if failed:
    print(f"{failed} FAILED!")
    print("========================================")
    raise SystemExit(1)

print("ALL CACHE DELTA PLANNER CHECKS PASSED")
print("========================================")
