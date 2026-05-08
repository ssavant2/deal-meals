#!/usr/bin/env python3
"""Focused checks for term-index helper functions used by matcher routing."""

from __future__ import annotations

import os
import sys
from uuid import uuid4


sys.path.insert(0, "/app" if os.path.exists("/app") else os.path.join(os.path.dirname(__file__), ".."))

from languages.sv.ingredient_matching import (  # noqa: E402
    build_candidate_map_from_term_postings,
    build_offer_candidate_terms,
    build_recipe_ingredient_term_map,
    build_recipe_search_text_map,
    extract_keywords_from_product,
    prepare_recipe_match_runtime_data,
    serialize_prepared_recipe_match_runtime_data,
)
from models import FoundRecipe  # noqa: E402


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


offer_payload = {
    "keywords": ["hushållsost", "ost"],
    "name_normalized": "hushållsost arla",
    "carrier_stripped": [],
}
terms = build_offer_candidate_terms(offer_payload)

test("offer terms keep keywords", ("hushållsost", "keyword") in terms, True)
test("offer terms add parent keyword", ("ost", "keyword") in terms, True)
test("offer terms include significant name words", ("arla", "name_word") in terms, True)

candidate_map = build_candidate_map_from_term_postings(
    {
        "ost": {"recipe-1"},
        "arla": {"recipe-1", "recipe-2"},
        "smör": {"recipe-3"},
    },
    {
        "ost": {"offer-1"},
        "arla": {"offer-1", "offer-2"},
        "grädde": {"offer-3"},
    },
)

test(
    "candidate map unions multiple term hits per recipe",
    candidate_map,
    {
        "recipe-1": {"offer-1", "offer-2"},
        "recipe-2": {"offer-1", "offer-2"},
    },
)

snabbkaffe_recipe = FoundRecipe(
    source_name="term_index_helpers",
    name="Term Index Helper Recipe",
    url="term-index-helper://snabbkaffe",
    ingredients=["3 msk snabbkaffepulver"],
    excluded=False,
)
snabbkaffe_recipe.id = uuid4()
snabbkaffe_payload = serialize_prepared_recipe_match_runtime_data(
    prepare_recipe_match_runtime_data(snabbkaffe_recipe)
)
snabbkaffe_term_map = build_recipe_ingredient_term_map(snabbkaffe_payload, {"snabbkaffe"})
test(
    "ingredient routing exposes snabbkaffe alias for snabbkaffepulver",
    snabbkaffe_term_map,
    {"snabbkaffe": {0}},
)

snabbkaffe_search_text = build_recipe_search_text_map(
    [snabbkaffe_recipe],
    compiled_recipe_payload_cache={str(snabbkaffe_recipe.id): snabbkaffe_payload},
)
test(
    "persistent recipe routing text exposes snabbkaffe alias",
    "snabbkaffe" in snabbkaffe_search_text[str(snabbkaffe_recipe.id)].split(),
    True,
)

slider_keywords = extract_keywords_from_product("Brioche Sliders 6p Garant", "bread")
test(
    "slider bread offers expose hamburgerbröd route keyword",
    "hamburgerbröd" in slider_keywords,
    True,
)

frofralla_keywords = extract_keywords_from_product("Fröfralla Fryst/6p Garant", "bread")
test(
    "bread roll offers expose styckbröd route keyword",
    frofralla_keywords,
    ["styckbröd"],
)

beyond_keywords = extract_keywords_from_product("Beyond Burger Plant-Based 2-pack", "frozen")
test(
    "Beyond Burger offers expose beyondburgare exact keyword",
    "beyondburgare" in beyond_keywords,
    True,
)

sourdough_baguette_keywords = extract_keywords_from_product("Baguette Surdeg Cereal Dafgårds", "bread")
test(
    "sourdough baguette bread offers expose baguette keyword",
    sourdough_baguette_keywords,
    ["baguette"],
)

baguette_recipe = FoundRecipe(
    source_name="term_index_helpers",
    name="Term Index Helper Recipe",
    url="term-index-helper://baguette",
    ingredients=['2 st "halva" baugetter'],
    excluded=False,
)
baguette_recipe.id = uuid4()
baguette_payload = serialize_prepared_recipe_match_runtime_data(
    prepare_recipe_match_runtime_data(baguette_recipe)
)
baguette_term_map = build_recipe_ingredient_term_map(baguette_payload, {"baguette"})
test(
    "ingredient routing exposes baguette alias for plural baguetter",
    baguette_term_map,
    {"baguette": {0}},
)

baguette_search_text = build_recipe_search_text_map(
    [baguette_recipe],
    compiled_recipe_payload_cache={str(baguette_recipe.id): baguette_payload},
)
test(
    "persistent recipe routing text exposes baguette alias",
    "baguette" in baguette_search_text[str(baguette_recipe.id)].split(),
    True,
)

tortilla_recipe = FoundRecipe(
    source_name="term_index_helpers",
    name="Term Index Helper Recipe",
    url="term-index-helper://tortilla",
    ingredients=["4 st tortillabröd"],
    excluded=False,
)
tortilla_recipe.id = uuid4()
tortilla_payload = serialize_prepared_recipe_match_runtime_data(
    prepare_recipe_match_runtime_data(tortilla_recipe)
)
tortilla_term_map = build_recipe_ingredient_term_map(tortilla_payload, {"tortilla"})
test(
    "ingredient routing exposes tortilla alias for tortillabröd",
    tortilla_term_map,
    {"tortilla": {0}},
)

tortilla_search_text = build_recipe_search_text_map(
    [tortilla_recipe],
    compiled_recipe_payload_cache={str(tortilla_recipe.id): tortilla_payload},
)
test(
    "persistent recipe routing text exposes tortilla alias",
    "tortilla" in tortilla_search_text[str(tortilla_recipe.id)].split(),
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
