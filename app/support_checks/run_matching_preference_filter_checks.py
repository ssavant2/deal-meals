#!/usr/bin/env python3
"""Checks for user-configurable matching preference filters."""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
import os
import sys
from types import SimpleNamespace


sys.path.insert(0, "/app" if os.path.exists("/app") else os.path.join(os.path.dirname(__file__), ".."))

import languages.sv.recipe_matcher_backend as backend  # noqa: E402
from languages.sv.ingredient_matching.dietary_exclusions import (  # noqa: E402
    compile_recipe_ingredient_exclusion_flags,
    ingredient_exclusion_hits_for_ingredient_text,
    ingredient_exclusion_hits_for_offer,
    selected_profiles_exclude_compiled_recipe,
    split_ingredient_exclusion_terms,
)


FOOD_CATEGORIES = {
    "meat",
    "fish",
    "poultry",
    "dairy",
    "vegetables",
    "fruit",
    "bread",
    "deli",
    "frozen",
    "spices",
    "pantry",
    "pizza",
    "other",
}


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


def offer(name: str, category: str = "pantry", brand: str = "", savings: Decimal | None = None):
    return SimpleNamespace(
        name=name,
        category=category,
        brand=brand,
        savings=Decimal("5.00") if savings is None else savings,
        price=Decimal("10.00"),
        store=None,
    )


class FakeQuery:
    def __init__(self, data):
        self._data = data

    def options(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._data)


class FakeSession:
    def __init__(self, offers):
        self._offers = offers
        self._query_calls = 0

    def query(self, model):
        self._query_calls += 1
        if self._query_calls == 1:
            data = [item for item in self._offers if item.category in FOOD_CATEGORIES]
        elif self._query_calls == 2:
            data = [item for item in self._offers if item.category == "candy"]
        else:
            data = [item for item in self._offers if item.category == "beverages"]
        return FakeQuery(data)


@contextmanager
def fake_db(offers):
    yield FakeSession(offers)


def filtered_names(offers, preferences):
    original_get_db_session = backend.get_db_session
    backend.get_db_session = lambda: fake_db(offers)
    try:
        return [item.name for item in backend.get_filtered_offers(preferences)]
    finally:
        backend.get_db_session = original_get_db_session


def unmatched_filter_reasons(offers, preferences):
    original_get_db_session = backend.get_db_session
    backend.get_db_session = lambda: fake_db(offers)
    try:
        result = backend.analyze_unmatched_offers(preferences, matched_offer_ids=set())
        return [(item["name"], item["reason"], item["detail"]) for item in result["filtered"]]
    finally:
        backend.get_db_session = original_get_db_session


BASE_PREFS = {
    "exclude_categories": [],
    "exclude_keywords": [],
    "filtered_products": [],
    "excluded_brands": [],
    "local_meat_only": False,
}


test(
    "category filters remove selected food categories",
    filtered_names(
        [
            offer("Kycklingfile svensk 500g", "poultry"),
            offer("Laxfile fryst 500g", "fish"),
            offer("Pasta 500g", "pantry"),
        ],
        {**BASE_PREFS, "exclude_categories": ["poultry", "fish"]},
    ),
    ["Pasta 500g"],
)

test(
    "dairy exclusion keeps lactose-free and naturally lactose-free dairy",
    filtered_names(
        [
            offer("Mjölk 1L Arla", "dairy"),
            offer("Mjölk Laktosfri 1L Arla", "dairy"),
            offer("Prästost 500g", "dairy"),
            offer("Crème Fraiche Parmesan 2dl", "dairy"),
        ],
        {**BASE_PREFS, "exclude_categories": ["dairy"]},
    ),
    ["Mjölk Laktosfri 1L Arla", "Prästost 500g"],
)

test(
    "local meat only removes known imported meat and allows Swedish meat",
    filtered_names(
        [
            offer("Entrecote Irland 300g", "meat"),
            offer("Entrecote Svensk 300g", "meat"),
            offer("Dry Age Beef Burger Fryst Theburgervault", "frozen"),
            offer("Entrecote Fryst", "frozen", brand="Mountain River"),
            offer("Fläskfilé ca 500g", "other", brand="Premiumbutcher"),
            offer("Pasta 500g", "pantry"),
        ],
        {**BASE_PREFS, "local_meat_only": True},
    ),
    ["Entrecote Svensk 300g", "Pasta 500g"],
)

test(
    "local meat only keeps broad imported brand without meat signal in extended category",
    filtered_names(
        [
            offer("Prime Dessert Fryst", "frozen", brand="Prime"),
            offer("Pasta 500g", "pantry"),
        ],
        {**BASE_PREFS, "local_meat_only": True},
    ),
    ["Prime Dessert Fryst", "Pasta 500g"],
)

test(
    "local meat only disabled keeps imported meat offers",
    filtered_names(
        [
            offer("Dry Age Beef Burger Fryst Theburgervault", "frozen"),
            offer("Pasta 500g", "pantry"),
        ],
        {**BASE_PREFS, "local_meat_only": False},
    ),
    ["Dry Age Beef Burger Fryst Theburgervault", "Pasta 500g"],
)

test(
    "local meat only diagnostics reports imported meat brand",
    unmatched_filter_reasons(
        [
            offer("Dry Age Beef Burger Fryst Theburgervault", "frozen"),
        ],
        {**BASE_PREFS, "local_meat_only": True},
    ),
    [("Dry Age Beef Burger Fryst Theburgervault", "local_meat", "theburgervault")],
)

test(
    "ingredient exclusions apply curated profiles plus literal leftovers",
    filtered_names(
        [
            offer("Mjölk 1L Arla"),
            offer("Ägg 12-pack"),
            offer("Gluten 500g"),
            offer("Glutenfri Pasta 500g"),
            offer("Pasta Fusilli 500g"),
            offer("Rispasta 400g"),
            offer("Glasnudlar 100g"),
            offer("Nötter Mix 200g"),
            offer("Cashewnötter 200g"),
            offer("Nötfärs 500g"),
            offer("Muskotnöt Hel 20g"),
        ],
        {**BASE_PREFS, "exclude_keywords": ["mjölk", "ägg", "gluten", "nötter"]},
    ),
    ["Glutenfri Pasta 500g", "Rispasta 400g", "Glasnudlar 100g", "Nötfärs 500g", "Muskotnöt Hel 20g"],
)

test(
    "lactose keyword reuses dairy/lactose offer policy",
    filtered_names(
        [
            offer("Mjölk 1L Arla", "dairy"),
            offer("Mjölk Laktosfri 1L Arla", "dairy"),
            offer("Prästost 500g", "dairy"),
            offer("Crème Fraiche Parmesan 2dl", "dairy"),
            offer("Mozzarella 125g", "dairy"),
            offer("Kokosmjölk 200ml", "dairy"),
            offer("TUC Original 100g", "dairy"),
        ],
        {**BASE_PREFS, "exclude_keywords": ["laktos"]},
    ),
    ["Mjölk Laktosfri 1L Arla", "Prästost 500g", "Kokosmjölk 200ml", "TUC Original 100g"],
)

test(
    "shellfish and soy profiles filter their families without filtering ordinary fish",
    filtered_names(
        [
            offer("Räkor Handskalade 300g", "fish"),
            offer("Kräftstjärtar i Lake", "fish"),
            offer("Räkost 275g Kavli", "dairy"),
            offer("Skagenröra 200g", "deli"),
            offer("Laxfilé 500g", "fish"),
            offer("Sojasås Japansk 150ml"),
            offer("Tofu Naturell 250g"),
            offer("Pasta 500g"),
        ],
        {**BASE_PREFS, "exclude_keywords": ["skaldjur", "soja"]},
    ),
    ["Laxfilé 500g", "Pasta 500g"],
)

test(
    "filtered products match whole words in offer names and brands require the brand field",
    filtered_names(
        [
            offer("Salami Milano 100g", "deli", "Zeta"),
            offer("Ölkorv Original 200g", "deli", "Scan"),
            offer("Pasta Penne 500g", "pantry", "Garant"),
            offer("Garant Pasta Penne 500g", "pantry", ""),
            offer("Pasta Fusilli 500g", "pantry", "Other"),
        ],
        {**BASE_PREFS, "filtered_products": ["salami", "ölkorv"], "excluded_brands": ["Garant"]},
    ),
    ["Garant Pasta Penne 500g", "Pasta Fusilli 500g"],
)

test(
    "profile parsing keeps unknown words literal",
    split_ingredient_exclusion_terms(["gluten", "nötter", "koriander"]),
    ({"gluten", "nuts"}, ["koriander"]),
)

test(
    "recipe ingredient flags cover profiles and respect exemptions",
    compile_recipe_ingredient_exclusion_flags([
        "2 dl vetemjöl",
        "1 dl glutenfritt mjöl",
        "100 g cashewnötter",
        "200 g nötfärs",
        "räkor",
        "lax",
        "2 ägg",
        "lägg åt sidan",
        "soja",
        "laktosfri grädde",
        "vispgrädde",
    ]),
    ["egg", "gluten", "lactose", "nuts", "shellfish", "soy"],
)

test(
    "recipe ingredient flags allow explicitly safe gluten/lactose lines",
    compile_recipe_ingredient_exclusion_flags([
        "glutenfritt mjöl",
        "risnudlar",
        "glasnudlar",
        "laktosfri grädde",
        "tomater",
    ]),
    [],
)

test(
    "offer dietary text fallback sees cues before matcher phrase compaction",
    [
        (hit.profile, hit.evidence, hit.source)
        for text in [
            "Vetemjöl Special 2kg",
            "Choklad Hasselnöt 100g",
            "Kondenserad mjölk 397g",
            "Naturell tofu 270g",
        ]
        for hit in ingredient_exclusion_hits_for_offer(text)
    ],
    [
        ("gluten", "vetemjöl", "text"),
        ("nuts", "hasselnöt", "text"),
        ("lactose", "mjölk", "text"),
        ("soy", "tofu", "text"),
    ],
)

test(
    "compiled recipe flags apply selected profiles at read time",
    selected_profiles_exclude_compiled_recipe(
        {"gluten"},
        {"ingredient_exclusion_flags": ["gluten", "nuts"]},
        fallback_ingredients=["tomater"],
    ),
    True,
)

test(
    "compiled recipe flags leave unrelated profiles visible",
    selected_profiles_exclude_compiled_recipe(
        {"soy"},
        {"ingredient_exclusion_flags": ["gluten", "nuts"]},
        fallback_ingredients=["soja"],
    ),
    False,
)

test(
    "missing compiled recipe flags fall back to ingredients",
    selected_profiles_exclude_compiled_recipe(
        {"soy"},
        {},
        fallback_ingredients=["1 msk soja"],
    ),
    True,
)

test(
    "ingredient extraction alignment reports guarded text/keyword hits",
    [
        (hit.profile, hit.evidence, hit.source)
        for text in ["Vetemjöl", "Äggnudlar", "Pasta Fusilli", "Naan bröd"]
        for hit in ingredient_exclusion_hits_for_ingredient_text(text)
        if hit.profile in {"gluten", "egg"}
    ],
    [
        ("gluten", "vetemjöl", "keyword"),
        ("gluten", "äggnudlar", "keyword"),
        ("egg", "äggnudlar", "keyword"),
        ("gluten", "pasta", "keyword"),
        ("gluten", "bröd,naan", "keyword"),
    ],
)

test(
    "unmatched diagnostics name profiled ingredient exclusions",
    unmatched_filter_reasons(
        [
            offer("Pasta Fusilli 500g"),
            offer("Koriander Färsk 20g", "vegetables"),
            offer("Tomater 500g", "vegetables"),
        ],
        {**BASE_PREFS, "exclude_keywords": ["gluten", "koriander"]},
    ),
    [
        ("Pasta Fusilli 500g", "ingredient_profile_excluded:gluten", "keyword:pasta"),
        ("Koriander Färsk 20g", "keyword_excluded", "koriander"),
    ],
)


if failed:
    print(f"\nMatching preference filter checks failed: {failed} failed, {passed} passed")
    raise SystemExit(1)

print(f"Matching preference filter checks passed ({passed} checks)")
