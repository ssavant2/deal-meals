#!/usr/bin/env python3
"""Checks for full candidate-refresh completeness guards."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from cache_manager import _select_indexable_offer_identity_keys  # noqa: E402
from languages.matcher_runtime import build_offer_identity_key  # noqa: E402
from languages.sv.ingredient_matching.term_indexes import (  # noqa: E402
    MATCHER_VERSION,
    RECIPE_COMPILER_VERSION,
    _candidate_offer_scope_hash,
    _validate_full_candidate_recipe_scope,
)


def check_true(label: str, value: bool) -> None:
    if not value:
        raise AssertionError(f"{label}: expected truthy value")
    print(f"OK {label}")


def test_full_refresh_rejects_partial_recipe_term_index() -> None:
    try:
        _validate_full_candidate_recipe_scope(
            indexed_recipe_count=1,
            active_recipe_count=13371,
        )
    except RuntimeError as exc:
        message = str(exc)
        check_true("partial guard mentions incomplete term index", "incomplete" in message)
        check_true("partial guard includes indexed count", "indexed_recipes=1" in message)
        check_true("partial guard includes active count", "active_recipes=13371" in message)
        return
    raise AssertionError("partial recipe-term index was accepted for full candidate refresh")


def test_full_refresh_accepts_complete_recipe_term_index() -> None:
    _validate_full_candidate_recipe_scope(
        indexed_recipe_count=13371,
        active_recipe_count=13371,
    )
    _validate_full_candidate_recipe_scope(
        indexed_recipe_count=13380,
        active_recipe_count=13371,
    )
    print("OK complete recipe-term index accepted")


def test_full_refresh_accepts_termless_recipes_with_complete_metadata() -> None:
    _validate_full_candidate_recipe_scope(
        indexed_recipe_count=10474,
        active_recipe_count=11326,
        recipe_term_metadata={
            "complete": True,
            "matcher_version": MATCHER_VERSION,
            "recipe_compiler_version": RECIPE_COMPILER_VERSION,
            "term_manifest_hash": "term-hash",
            "indexed_recipes": 11326,
            "active_recipe_count": 11326,
        },
        term_manifest_hash="term-hash",
    )
    print("OK termless recipes accepted with complete recipe-term metadata")


def test_offer_scope_hash_is_stable() -> None:
    first = _candidate_offer_scope_hash(["offer-b", "offer-a", "offer-a"])
    second = _candidate_offer_scope_hash(["offer-a", "offer-b"])
    check_true("offer scope hash is order-insensitive", first == second)


class FakeOffer:
    def __init__(
        self,
        *,
        offer_id: str,
        product_url: str,
        name: str,
        brand: str,
        category: str = "other",
        unit: str = "st",
        weight_grams: Decimal | None = None,
        store_id: str = "store-1",
    ) -> None:
        self.id = offer_id
        self.product_url = product_url
        self.name = name
        self.brand = brand
        self.category = category
        self.unit = unit
        self.weight_grams = weight_grams
        self.store_id = store_id


def test_offer_term_coverage_selects_only_indexable_offers() -> None:
    empty_term_offer = FakeOffer(
        offer_id="offer-empty",
        product_url="https://example.com/empty",
        name="Bbq oil CAJ P.",
        brand="CAJ P.",
        weight_grams=Decimal("250"),
    )
    indexable_offer = FakeOffer(
        offer_id="offer-indexable",
        product_url="https://example.com/indexable",
        name="Kycklingfile Kronfagel",
        brand="Kronfagel",
        category="poultry",
        weight_grams=Decimal("1000"),
    )

    selected = _select_indexable_offer_identity_keys(
        [empty_term_offer, indexable_offer],
        {
            id(empty_term_offer): {
                "keywords": [],
                "name_normalized": "bbq oil caj p.",
                "carrier_stripped": [],
            },
            id(indexable_offer): {
                "keywords": ["kycklingfile"],
                "name_normalized": "kycklingfile kronfagel",
                "carrier_stripped": [],
            },
        },
    )

    expected = {build_offer_identity_key(indexable_offer)}
    if selected != expected:
        raise AssertionError(f"indexable offer selection: expected {expected!r}, got {selected!r}")
    print("OK only offers with candidate terms require term-index coverage")


def main() -> int:
    test_full_refresh_rejects_partial_recipe_term_index()
    test_full_refresh_accepts_complete_recipe_term_index()
    test_full_refresh_accepts_termless_recipes_with_complete_metadata()
    test_offer_scope_hash_is_stable()
    test_offer_term_coverage_selects_only_indexable_offers()
    print("ALL CANDIDATE REFRESH GUARD CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
