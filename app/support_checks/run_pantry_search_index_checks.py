#!/usr/bin/env python3
"""Policy checks for the optional pantry search-term index helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import uuid


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from pantry_search_index import (  # noqa: E402
    PANTRY_SEARCH_INDEX_VERSION_HASH,
    build_pantry_query,
    build_recipe_scoring_keywords,
    build_recipe_search_terms,
    resolve_pantry_candidate_limit,
    score_pantry_recipes,
)


@dataclass
class FakeRecipe:
    id: uuid.UUID
    name: str
    url: str
    source_name: str
    image_url: str | None
    local_image_path: str | None
    ingredients: list[str]
    prep_time_minutes: int | None = None
    servings: int | None = None
    excluded: bool = False


def check(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"OK {name}")


def check_true(name: str, value) -> None:
    if not value:
        raise AssertionError(f"{name}: expected truthy value, got {value!r}")
    print(f"OK {name}")


def test_query_parser() -> None:
    query = build_pantry_query("kyckling, grädde, pasta")
    check("query input parts", query.input_parts, ("kyckling", "grädde", "pasta"))
    check_true("query user keywords include kyckling", "kyckling" in query.user_keywords)
    check_true("query user keywords include grädde", "grädde" in query.user_keywords)
    check_true("query user keywords include pasta", "pasta" in query.user_keywords)
    check("query terms per input", len(query.terms_by_input), 3)

    tomato_query = build_pantry_query("körsbärstomat")
    tomato_terms = set(tomato_query.terms_by_input[0])
    check_true("query singular includes plural variant", "körsbärstomater" in tomato_terms)


def test_recipe_terms_and_scoring_keywords() -> None:
    recipe = FakeRecipe(
        id=uuid.uuid4(),
        name="Pasta med tomat och ost",
        url="https://example.invalid/pasta",
        source_name="Support",
        image_url=None,
        local_image_path=None,
        ingredients=["2 dl pasta", "1 burk tomater", "100 g riven ost", "salt"],
    )
    terms = build_recipe_search_terms(recipe)
    term_values = {term for term, _term_type in terms}
    check_true("search terms include pasta", "pasta" in term_values)
    check_true("search terms include ost", "ost" in term_values)
    check_true("search terms exclude salt", "salt" not in term_values)

    compound_recipe = FakeRecipe(
        id=uuid.uuid4(),
        name="Compound pantry terms",
        url="https://example.invalid/compound",
        source_name="Support",
        image_url=None,
        local_image_path=None,
        ingredients=["fetaost", "basmatiris", "körsbärstomater", "rostas"],
    )
    compound_terms = build_recipe_search_terms(compound_recipe)
    compound_values = {term for term, _term_type in compound_terms}
    check_true("compound terms include ost", "ost" in compound_values)
    check_true("compound terms include ris", "ris" in compound_values)
    check_true("compound terms include tomat", "tomat" in compound_values)

    scoring_terms = build_recipe_scoring_keywords(recipe.ingredients)
    check_true("scoring terms include pasta", "pasta" in scoring_terms)
    check_true("scoring terms include ost", "ost" in scoring_terms)
    check_true("scoring terms exclude salt", "salt" not in scoring_terms)


def test_score_pantry_recipes() -> None:
    query = build_pantry_query("pasta,tomat,ost")
    full_recipe = FakeRecipe(
        id=uuid.uuid4(),
        name="Pasta med tomat och ost",
        url="https://example.invalid/full",
        source_name="Support",
        image_url=None,
        local_image_path=None,
        ingredients=["pasta", "tomat", "ost"],
    )
    partial_recipe = FakeRecipe(
        id=uuid.uuid4(),
        name="Pasta med tomat och svamp",
        url="https://example.invalid/partial",
        source_name="Support",
        image_url=None,
        local_image_path=None,
        ingredients=["pasta", "tomat", "svamp"],
    )
    full, partial = score_pantry_recipes([partial_recipe, full_recipe], query)
    check("full match count", len(full), 1)
    check("partial match count", len(partial), 1)
    check("full match missing count", full[0]["missing_count"], 0)
    check("partial missing preview", partial[0]["missing_preview"], ["svamp"])


def test_candidate_safety_limit() -> None:
    query = build_pantry_query("pasta,tomat,ost")
    check("default candidate limit uses active scope", resolve_pantry_candidate_limit(query, total_scope=13311), 13311)
    check("candidate limit respects empty scope", resolve_pantry_candidate_limit(query, total_scope=0), 0)
    check("candidate safety cap", resolve_pantry_candidate_limit(query, total_scope=50000, candidate_hard_cap=10000), 10000)


def test_index_version_hash_present() -> None:
    check("index hash length", len(PANTRY_SEARCH_INDEX_VERSION_HASH), 64)


def main() -> int:
    test_query_parser()
    test_recipe_terms_and_scoring_keywords()
    test_score_pantry_recipes()
    test_candidate_safety_limit()
    test_index_version_hash_present()
    print("ALL PANTRY SEARCH INDEX CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
