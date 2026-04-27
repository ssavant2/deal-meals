#!/usr/bin/env python3
"""Checks for candidate routing term-detail helpers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, '/app' if os.path.exists('/app') else os.path.join(os.path.dirname(__file__), '..'))

from languages.matcher_runtime import (  # noqa: E402
    build_candidate_map_from_term_postings,
    build_candidate_term_detail_from_term_postings,
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


recipe_term_postings = {
    "ost": {"recipe-1", "recipe-2"},
    "arla": {"recipe-1"},
    "grädde": {"recipe-2"},
    "smör": {"recipe-3"},
}
offer_term_postings = {
    "ost": {"offer-1", "offer-2"},
    "arla": {"offer-1"},
    "grädde": {"offer-2", "offer-3"},
    "ris": {"offer-4"},
}

candidate_map = build_candidate_map_from_term_postings(
    recipe_term_postings,
    offer_term_postings,
)
candidate_term_detail = build_candidate_term_detail_from_term_postings(
    recipe_term_postings,
    offer_term_postings,
)
collapsed_term_detail = {
    recipe_id: set(offer_terms)
    for recipe_id, offer_terms in candidate_term_detail.items()
}
offer_recipe_term_pair_count = sum(
    len(terms)
    for offer_terms in candidate_term_detail.values()
    for terms in offer_terms.values()
)

test(
    "candidate term detail keeps every routing term per offer-recipe pair",
    candidate_term_detail,
    {
        "recipe-1": {
            "offer-1": {"ost", "arla"},
            "offer-2": {"ost"},
        },
        "recipe-2": {
            "offer-1": {"ost"},
            "offer-2": {"ost", "grädde"},
            "offer-3": {"grädde"},
        },
    },
)
test("candidate term detail collapses to current candidate map", collapsed_term_detail, candidate_map)
test("candidate term detail ignores terms without both sides", "recipe-3" in candidate_term_detail, False)
test("offer-recipe term-pair count keeps overlapping terms", offer_recipe_term_pair_count, 7)


print("\n========================================")
print(f"TOTAL: {passed}/{passed + failed} checks passed")
if failed:
    print(f"{failed} FAILED!")
    print("========================================")
    raise SystemExit(1)

print("ALL PASSED!")
print("========================================")
