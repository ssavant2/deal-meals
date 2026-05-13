#!/usr/bin/env python3
"""Checks for cache-delta term-index fallback helpers."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch


sys.path.insert(0, "/app" if os.path.exists("/app") else os.path.join(os.path.dirname(__file__), ".."))

from cache_delta import (  # noqa: E402
    _build_persisted_offer_term_postings_fallback,
    _build_recipe_term_postings_fallback,
    _load_or_build_delta_term_postings,
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


fake_offer_rows = {
    "offer:1": {
        "compiled_data": {
            "keywords": ["cheddar", "ost"],
            "carrier_stripped": [],
            "name_normalized": "cheddar ost 500g",
        }
    },
    "offer:2": {
        "compiled_data": {
            "keywords": ["tomat"],
            "carrier_stripped": [],
            "name_normalized": "krossad tomat 400g",
        }
    },
}
with patch("cache_delta.load_compiled_offer_match_map", return_value=fake_offer_rows):
    postings, stats = _build_persisted_offer_term_postings_fallback()

test("offer fallback source", stats["source"], "compiled_offer_match_data_fallback")
test("offer fallback cheddar posting", "offer:1" in postings["cheddar"], True)
test("offer fallback tomat posting", "offer:2" in postings["tomat"], True)
test("offer fallback ephemeral manifest", stats["term_manifest_hash"].startswith("ephemeral-"), True)

recipes = [type("Recipe", (), {"id": 1})(), type("Recipe", (), {"id": 2})()]
fake_payload_cache = {
    "1": {"ingredients_search_text": "cheddar ost pasta"},
    "2": {"ingredients_search_text": "krossad tomat basilika"},
}
fake_payload_stats = {
    "missing_recipe_ids": [],
    "stale_recipe_ids": [],
    "inactive_recipe_ids": [],
}
fake_search_texts = {
    "1": "cheddar ost pasta",
    "2": "krossad tomat basilika",
}
with patch(
    "cache_delta.load_compiled_recipe_payload_cache",
    return_value=(fake_payload_cache, fake_payload_stats),
), patch(
    "cache_delta.build_recipe_search_text_map",
    return_value=fake_search_texts,
):
    postings, stats = _build_recipe_term_postings_fallback(
        recipes,
        candidate_terms={"cheddar", "tomat", "grädde"},
    )

test("recipe fallback source", stats["source"], "compiled_recipe_payload_fallback")
test("recipe fallback cheddar posting", postings["cheddar"], {"1"})
test("recipe fallback tomat posting", postings["tomat"], {"2"})
test("recipe fallback omits absent term", "grädde" in postings, False)
test("recipe fallback ephemeral manifest", stats["term_manifest_hash"].startswith("ephemeral-"), True)

recipes = [type("Recipe", (), {"id": 1})()]
persisted_offer_term_postings = {"old-term": {"offer-old"}}
persisted_offer_term_stats = {"term_manifest_hash": "persisted-hash"}
persisted_recipe_term_postings = {"old-term": {"1"}}
persisted_recipe_term_stats = {
    "term_manifest_hash": "persisted-hash",
    "source": "compiled_recipe_term_index",
}
current_recipe_term_postings = {
    "old-term": {"1"},
    "new-term": {"1"},
}
current_recipe_term_stats = {
    "term_manifest_hash": "ephemeral-current",
    "source": "compiled_recipe_payload_fallback",
}

with patch(
    "cache_delta.load_compiled_offer_term_postings",
    return_value=(persisted_offer_term_postings, persisted_offer_term_stats),
), patch(
    "cache_delta.load_compiled_recipe_term_postings",
    return_value=(persisted_recipe_term_postings, persisted_recipe_term_stats),
), patch(
    "cache_delta._build_recipe_term_postings_fallback",
    return_value=(current_recipe_term_postings, current_recipe_term_stats),
) as fallback_builder:
    (
        _offer_postings,
        _offer_stats,
        current_recipe_postings,
        current_recipe_stats,
        persisted_recipe_postings,
        persisted_recipe_stats,
    ) = _load_or_build_delta_term_postings(
        recipes=recipes,
        current_offer_term_postings={"new-term": {"offer-new"}},
    )

test("current recipe fallback used for new terms", current_recipe_postings, current_recipe_term_postings)
test("current recipe fallback source", current_recipe_stats["source"], "compiled_recipe_payload_fallback")
test("persisted recipe postings preserved", persisted_recipe_postings, persisted_recipe_term_postings)
test("persisted recipe stats preserved", persisted_recipe_stats["source"], "compiled_recipe_term_index")
test("fallback builder called once", fallback_builder.call_count, 1)


print("\n========================================")
print(f"TOTAL: {passed}/{passed + failed} checks passed")
if failed:
    print(f"{failed} FAILED!")
    print("========================================")
    raise SystemExit(1)

print("ALL CACHE DELTA TERM FALLBACK CHECKS PASSED")
print("========================================")
