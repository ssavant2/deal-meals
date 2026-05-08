#!/usr/bin/env python3
"""Checks for full candidate-refresh completeness guards."""

from __future__ import annotations

from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from languages.sv.ingredient_matching.term_indexes import (  # noqa: E402
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


def test_offer_scope_hash_is_stable() -> None:
    first = _candidate_offer_scope_hash(["offer-b", "offer-a", "offer-a"])
    second = _candidate_offer_scope_hash(["offer-a", "offer-b"])
    check_true("offer scope hash is order-insensitive", first == second)


def main() -> int:
    test_full_refresh_rejects_partial_recipe_term_index()
    test_full_refresh_accepts_complete_recipe_term_index()
    test_offer_scope_hash_is_stable()
    print("ALL CANDIDATE REFRESH GUARD CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
