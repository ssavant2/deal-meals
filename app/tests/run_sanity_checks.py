#!/usr/bin/env python3
"""Quick app support sanity checks.

This is the small, tracked "must not be broken" suite. It intentionally avoids
pytest, the database, live scraping, and benchmark fixtures so it can run in the
normal web container.

Run:
    docker compose exec -T -w /app web python tests/run_sanity_checks.py
"""

from __future__ import annotations

from contextlib import contextmanager
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, '/app' if os.path.exists('/app') else os.path.join(os.path.dirname(__file__), '..'))

from loguru import logger  # noqa: E402
from languages.sv.ingredient_matching import (  # noqa: E402
    build_ingredient_match_data,
    build_offer_match_data,
    match_offer_to_ingredient,
    precompute_offer_data,
)
from recipe_matcher import RecipeMatcher  # noqa: E402
from scrapers.stores import get_all_stores, get_store_discovery_errors  # noqa: E402


for noisy_module in ("app", "recipe_scraper_manager", "scrapers.stores"):
    logger.disable(noisy_module)

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


def _offer_obj(offer: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id='sanity-offer',
        name=offer['name'],
        category=offer.get('category', ''),
        brand=offer.get('brand', ''),
        price=offer.get('price', 0),
        original_price=offer.get('original_price'),
        savings=offer.get('savings', 0),
        store=None,
        product_url=None,
        is_multi_buy=False,
        multi_buy_quantity=None,
        weight_grams=offer.get('weight_grams'),
    )


def _audit_match_num(ingredient: str, offer: dict) -> int:
    ingredient_data = build_ingredient_match_data(ingredient)
    offer_data = build_offer_match_data(
        offer['name'],
        offer.get('category', ''),
        brand=offer.get('brand', ''),
        weight_grams=offer.get('weight_grams'),
    )
    return 1 if match_offer_to_ingredient(ingredient_data, offer_data).matched else 0


def _recipe_match_num(
    ingredients: list[str],
    offer: dict,
    *,
    cached: bool,
    recipe_name: str = "Sanity Recipe",
) -> int:
    matcher = RecipeMatcher()
    recipe = SimpleNamespace(
        id='sanity-recipe',
        name=recipe_name,
        ingredients=ingredients,
    )
    offer_obj = _offer_obj(offer)

    kwargs = {}
    if cached:
        offer_key = id(offer_obj)
        offer_data = precompute_offer_data(
            offer_obj.name,
            offer_obj.category,
            brand=offer_obj.brand,
            weight_grams=offer_obj.weight_grams,
        )
        kwargs["offer_keywords"] = {offer_key: tuple(offer_data.get("keywords", ()))}
        kwargs["offer_data_cache"] = {offer_key: offer_data}

    return matcher._match_recipe_to_offers(
        recipe,
        [offer_obj],
        preferences={},
        **kwargs,
    )["num_matches"]


def _run_matching_sanity_checks() -> None:
    cases = [
        {
            "name": "fiberhusk exact product stays aligned",
            "ingredients": ["0.5 dl Fiberhusk"],
            "offer": {
                "name": "Fiberhusk Glutenfri 300g Husk",
                "category": "pantry",
                "brand": "FIBERHUSK",
            },
            "expected": 1,
        },
        {
            "name": "dark chocolate bars stay aligned",
            "ingredients": ["100 g Mörk chokladkaka"],
            "offer": {
                "name": "Chokladkaka EXCELLENCE 70% Kakao Mörk Choklad 100g Lindt",
                "category": "candy",
            },
            "expected": 1,
        },
        {
            "name": "porter still does not widen to light beer",
            "ingredients": ["33 cl porter eller annan mörk öl"],
            "offer": {
                "name": "Lättöl 2,1% 33cl Grängesberg",
                "category": "beverages",
                "brand": "GRÄNGESBERG",
            },
            "expected": 0,
        },
        {
            "name": "fresh oregano blocks household seed packets",
            "ingredients": ["1/2 kruka färsk oregano, plockade blad"],
            "offer": {
                "name": "Oregano Grekisk 1-p Nelson Garden",
                "category": "household",
            },
            "expected": 0,
        },
        {
            "name": "fresh oregano matches a fresh herb offer",
            "ingredients": ["1/2 kruka färsk oregano, plockade blad"],
            "offer": {
                "name": "Oregano i kruka Klass 1 Test",
                "category": "vegetables",
            },
            "expected": 1,
        },
    ]

    print("\n--- matching sanity: audit/full/cached parity ---", flush=True)
    for case in cases:
        ingredient_text = case["ingredients"][0]
        expected = case["expected"]
        audit_val = _audit_match_num(ingredient_text, case["offer"])
        full_val = _recipe_match_num(case["ingredients"], case["offer"], cached=False)
        cached_val = _recipe_match_num(case["ingredients"], case["offer"], cached=True)

        test(f"{case['name']} audit", audit_val, expected)
        test(f"{case['name']} full", full_val, expected)
        test(f"{case['name']} cached", cached_val, expected)
        test(f"{case['name']} audit/full parity", audit_val, full_val)
        test(f"{case['name']} audit/cached parity", audit_val, cached_val)


def _run_store_discovery_sanity_checks() -> None:
    print("\n--- store plugin discovery ---", flush=True)
    stores = get_all_stores()
    discovery_errors = get_store_discovery_errors()
    store_ids = [store.config.id for store in stores]

    test("store plugin discovery has no import/init errors", discovery_errors, [])
    test("store plugin IDs are unique", len(store_ids), len(set(store_ids)))


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.deleted = []
        self.executed = []
        self.committed = False

    def query(self, _model):
        return FakeQuery(self.rows)

    def add(self, _row):
        raise AssertionError("unexpected add")

    def delete(self, row):
        self.deleted.append(row)

    def execute(self, statement, params):
        self.executed.append((str(statement), params))
        return SimpleNamespace(rowcount=1)

    def commit(self):
        self.committed = True


def _run_store_registry_sanity_checks() -> None:
    print("\n--- store registry startup cleanup ---", flush=True)
    import app as deal_app  # noqa: E402

    def run_with_fake_session(session: FakeSession, discovery_errors: list[dict]) -> None:
        @contextmanager
        def fake_db_session():
            yield session

        original_get_db_session = deal_app.get_db_session
        deal_app.get_db_session = fake_db_session
        try:
            deal_app._sync_store_registry([], discovery_errors=discovery_errors)
        finally:
            deal_app.get_db_session = original_get_db_session

    skipped = FakeSession([SimpleNamespace(store_type="removed_store")])
    run_with_fake_session(
        skipped,
        [{"module": "broken_store", "phase": "import", "error": "ImportError('boom')"}],
    )
    test("discovery errors skip store deletion", skipped.deleted, [])
    test("discovery errors skip schedule cleanup", skipped.executed, [])
    test("discovery errors do not commit destructive cleanup", skipped.committed, False)

    clean = FakeSession([SimpleNamespace(store_type="removed_store")])
    run_with_fake_session(clean, [])
    test("clean discovery deletes removed store row", [row.store_type for row in clean.deleted], ["removed_store"])
    test(
        "clean discovery deletes removed store schedule",
        clean.executed,
        [
            (
                "DELETE FROM store_schedules WHERE store_id = :store_id",
                {"store_id": "removed_store"},
            )
        ],
    )
    test("clean discovery commits cleanup", clean.committed, True)


_run_matching_sanity_checks()
_run_store_discovery_sanity_checks()
_run_store_registry_sanity_checks()

print("\n========================================", flush=True)
print(f"TOTAL: {passed}/{passed + failed} checks passed", flush=True)
if failed:
    print(f"{failed} FAILED!", flush=True)
    print("========================================", flush=True)
    raise SystemExit(1)

print("ALL PASSED!", flush=True)
print("========================================", flush=True)
