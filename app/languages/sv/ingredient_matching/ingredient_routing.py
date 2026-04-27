"""Ingredient-level routing helpers for compiled recipe payloads."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .compiled_recipes import resolve_recipe_match_runtime_data
from .synonyms import INGREDIENT_PARENTS


def build_recipe_ingredient_term_map(
    compiled_recipe_payload: dict[str, Any],
    routing_terms: Iterable[str],
) -> dict[str, set[int]]:
    """Map routing terms to expanded ingredient indices for one compiled recipe."""
    terms = {str(term) for term in routing_terms if term}
    term_map: dict[str, set[int]] = {term: set() for term in terms}
    if not terms or not compiled_recipe_payload:
        return term_map

    runtime_recipe_data = resolve_recipe_match_runtime_data(
        compiled_recipe_data=compiled_recipe_payload,
    )
    ingredients_normalized = runtime_recipe_data.get("ingredients_normalized", [])
    ingredient_match_data_per_ing = runtime_recipe_data.get("ingredient_match_data_per_ing", [])

    for expanded_idx, ingredient_data in enumerate(ingredient_match_data_per_ing):
        normalized_text = str(
            ingredients_normalized[expanded_idx]
            if expanded_idx < len(ingredients_normalized)
            else getattr(ingredient_data, "normalized_text", "")
        )
        prepared_text = str(getattr(ingredient_data, "normalized_text", ""))
        extracted_keywords = {
            str(keyword)
            for keyword in getattr(ingredient_data, "extracted_keywords", ())
            if keyword
        }
        keyword_terms = set(extracted_keywords)
        for keyword in extracted_keywords:
            parent = INGREDIENT_PARENTS.get(keyword)
            if parent:
                keyword_terms.add(parent)

        haystack = f"{normalized_text} {prepared_text}".strip()
        for term in terms:
            if term in keyword_terms or (haystack and term in haystack):
                term_map[term].add(expanded_idx)

    return term_map
