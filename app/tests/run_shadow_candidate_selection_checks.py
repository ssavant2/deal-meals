#!/usr/bin/env python3
"""Checks for Phase 2 shadow candidate-selection helpers."""

from __future__ import annotations

import os
from types import SimpleNamespace
import sys

sys.path.insert(0, '/app' if os.path.exists('/app') else os.path.join(os.path.dirname(__file__), '..'))

from languages import matcher_runtime as runtime  # noqa: E402
from languages.sv.ingredient_matching import build_prepared_ingredient_match_data  # noqa: E402


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


def _ingredient_data(raw_text: str, normalized_text: str, keywords: set[str], idx: int):
    return build_prepared_ingredient_match_data(
        normalized_text,
        raw_text=raw_text,
        extracted_keywords=frozenset(keywords),
        source_index=idx,
        expanded_index=idx,
        prepared_fast_text=True,
    )


offer = SimpleNamespace(
    id=1001,
    name="Morot",
    category="vegetables",
    brand="",
    weight_grams=None,
    price=10,
    original_price=15,
    savings=5,
    store=SimpleNamespace(name="Testbutik"),
    product_url="https://example.test/morot",
    is_multi_buy=False,
    multi_buy_quantity=None,
)
offer_precomputed = runtime.precompute_offer_data(
    offer.name,
    offer.category,
    brand=offer.brand,
    weight_grams=offer.weight_grams,
)
offer_data_cache = {id(offer): offer_precomputed}
offer_keywords = {id(offer): list(offer_precomputed.get("keywords", ()))}
ingredient_match_data = [
    _ingredient_data("riven morot", "riven morot", {"morot", "riven"}, 0),
    _ingredient_data("morot", "morot", {"morot"}, 1),
    _ingredient_data("salt", "salt", {"salt"}, 2),
]

context = runtime.build_offer_match_context_backend(
    offer,
    id(offer),
    offer_keywords,
    offer_data_cache,
)
full_candidates = runtime.collect_offer_match_candidates_backend(
    ingredient_match_data,
    context["offer_match_data"],
)
full_selection = runtime.select_offer_match_candidate_backend(
    full_candidates,
    ingredient_match_data,
)

test("fullscan sees the two matching carrot ingredients", [idx for idx, _ in full_candidates], [0, 1])
test("fewer-keyword preference chooses the simpler carrot line", full_selection["selected_ing_idx"], 1)
test("fewer-keyword preference is flagged", full_selection["selected_by_fewer_keywords"], True)

hinted_candidates = runtime.collect_offer_match_candidates_backend(
    ingredient_match_data,
    context["offer_match_data"],
    {0},
)
hinted_selection = runtime.select_offer_match_candidate_backend(
    hinted_candidates,
    ingredient_match_data,
)
test("hinted collection only scans requested indices", [idx for idx, _ in hinted_candidates], [0])
test("hinted selection preserves production selection rules within hint set", hinted_selection["selected_ing_idx"], 0)

shadow = runtime.analyze_ingredient_routing_shadow_backend(
    offer,
    id(offer),
    offer_keywords,
    offer_data_cache,
    ingredient_match_data,
    {0},
    ["riven morot", "morot", "salt"],
    ["riven morot", "morot", "salt"],
    [0, 1, 2],
    ["riven morot", "morot", "salt"],
    "testrecept riven morot salt",
)
classes = set(shadow["mismatch_classes"])
test("shadow keeps production fullscan signature", shadow["fullscan_validated_signature"], ("morot", 1))
test("shadow validates hinted signature independently", shadow["hinted_validated_signature"], ("morot", 0))
test("shadow classifies missing fullscan winner", "fullscan_initial_winner_outside_hint" in classes, True)
test("shadow classifies same-keyword different-line risk", "hinted_same_keyword_different_ingredient_line" in classes, True)
test("shadow classifies fewer-keyword dependency", "fullscan_fewer_keyword_preference_winner" in classes, True)
test("shadow marks changed validated output", shadow["parity"], False)

no_hint_shadow = runtime.analyze_ingredient_routing_shadow_backend(
    offer,
    id(offer),
    offer_keywords,
    offer_data_cache,
    ingredient_match_data,
    set(),
    ["riven morot", "morot", "salt"],
    ["riven morot", "morot", "salt"],
    [0, 1, 2],
    ["riven morot", "morot", "salt"],
    "testrecept riven morot salt",
)
test("shadow classifies routed pairs without hints", "no_hint_for_routed_pair" in set(no_hint_shadow["mismatch_classes"]), True)

prepared_recipe_data = {
    "merged_ingredients": ["riven morot", "morot", "salt"],
    "ingredient_source_texts": ["riven morot", "morot", "salt"],
    "ingredient_source_indices": [0, 1, 2],
    "ingredients_normalized": ["riven morot", "morot", "salt"],
    "full_recipe_text": "vegetarisk morot salt",
    "ingredient_match_data_per_ing": ingredient_match_data,
}
hinted_no_match_result = runtime.match_recipe_to_offers_backend(
    None,
    SimpleNamespace(name="Vegetarisk morotstest"),
    [offer],
    {},
    offer_keywords,
    offer_data_cache,
    prepared_recipe_data=prepared_recipe_data,
    ingredient_candidate_indices_by_offer={runtime.build_offer_identity_key(offer): {2}},
    ingredient_routing_mode="hint_first",
)
test("hint_first treats ordinary hinted no-match pairs as no match", hinted_no_match_result["num_matches"], 0)
test("hint_first records ordinary hinted no-match pairs", hinted_no_match_result["hinted_no_match_count"], 1)
test(
    "hint_first does not fullscan ordinary hinted no-match pairs",
    hinted_no_match_result["fullscan_fallback_reason_counts"],
    {},
)

no_hint_fallback_result = runtime.match_recipe_to_offers_backend(
    None,
    SimpleNamespace(name="Vegetarisk morotstest"),
    [offer],
    {},
    offer_keywords,
    offer_data_cache,
    prepared_recipe_data=prepared_recipe_data,
    ingredient_candidate_indices_by_offer={runtime.build_offer_identity_key(offer): set()},
    ingredient_routing_mode="hint_first",
)
test("hint_first still falls back when no hint exists for a routed pair", no_hint_fallback_result["num_matches"], 1)
test(
    "hint_first records no-hint fullscan fallback",
    no_hint_fallback_result["fullscan_fallback_reason_counts"],
    {"no_hint_for_routed_pair": 1},
)

lindosalami_offer = SimpleNamespace(
    id=1002,
    name="Lindösalami Peppar 90g Lönneberga",
    category="meat",
    brand="LÖNNEBERGA",
    weight_grams=90,
)
lindosalami_data = runtime.precompute_offer_data(
    lindosalami_offer.name,
    lindosalami_offer.category,
    brand=lindosalami_offer.brand,
    weight_grams=lindosalami_offer.weight_grams,
)
test(
    "offer routing terms include PARENT_MATCH_ONLY parent keywords",
    ("salami", "parent_keyword") in runtime.build_offer_candidate_terms(lindosalami_data),
    True,
)

print("\n========================================")
print(f"TOTAL: {passed}/{passed + failed} checks passed")
if failed:
    print(f"{failed} FAILED!")
    print("========================================")
    raise SystemExit(1)

print("ALL PASSED!")
print("========================================")
