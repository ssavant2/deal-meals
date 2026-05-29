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
            offer("Pasta 500g", "pantry"),
        ],
        {**BASE_PREFS, "local_meat_only": True},
    ),
    ["Entrecote Svensk 300g", "Pasta 500g"],
)

test(
    "ingredient exclusions match whole words in offer names",
    filtered_names(
        [
            offer("Mjölk 1L Arla"),
            offer("Ägg 12-pack"),
            offer("Gluten 500g"),
            offer("Glutenfri Pasta 500g"),
            offer("Nötter Mix 200g"),
            offer("Cashewnötter 200g"),
        ],
        {**BASE_PREFS, "exclude_keywords": ["mjölk", "ägg", "gluten", "nötter"]},
    ),
    ["Glutenfri Pasta 500g", "Cashewnötter 200g"],
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


if failed:
    print(f"\nMatching preference filter checks failed: {failed} failed, {passed} passed")
    raise SystemExit(1)

print(f"Matching preference filter checks passed ({passed} checks)")
