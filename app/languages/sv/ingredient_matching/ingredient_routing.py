"""Ingredient-level routing helpers for compiled recipe payloads."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .compiled_recipes import resolve_recipe_match_runtime_data
from .compound_text import _WORD_PATTERN
from .synonyms import INGREDIENT_PARENTS


_ROUTING_PARENT_TERMS = {
    # Fullscan accepts these compound recipe words through substring/family
    # matching. Expose the same family term for compiled route pairing without
    # adding reverse offer keywords to every generic product in the family.
    "kalamataoliver": "oliver",
    "svartvinbärsgele": "vinbärsgele",
    "svartvinbarsgele": "vinbarsgele",
    "rödvinbärsgele": "vinbärsgele",
    "rodvinbarsgele": "vinbarsgele",
    "oreokaka": "oreo",
    "oreokakor": "oreo",
    "kycklingschnitzel": "schnitzel",
    "prästost": "ost",
    "prastost": "ost",
    "johansvamp": "svamp",
    "skogssvamp": "svamp",
    "kycklinginnerfilé": "kyckling",
    "kycklinginnerfiléer": "kyckling",
    "kycklinginnerfile": "kyckling",
    "kycklinginnerfileer": "kyckling",
    "snabbkaffepulver": "snabbkaffe",
    "kaffepulver": "snabbkaffe",
    "pulverkaffe": "snabbkaffe",
    "baguetter": "baguette",
    "tortillabröd": "tortilla",
    "tortillabrod": "tortilla",
    "bladspenat": "spenat",
    "babyspenat": "spenat",
    "rödspättafilé": "rödspätta",
    "rodspattafile": "rödspätta",
    "ansjovisfiléer": "ansjovis",
    "ansjovisfileer": "ansjovis",
    "mandelpotatischips": "potatischips",
    "lantchips": "potatischips",
    "aprikoser": "aprikos",
    "champinjoner": "champinjon",
    "skogschampinjoner": "champinjoner",
    "lammkotletter": "lammkotlett",
}


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
            parent = INGREDIENT_PARENTS.get(keyword) or _ROUTING_PARENT_TERMS.get(keyword)
            if parent:
                keyword_terms.add(parent)

        haystack = f"{normalized_text} {prepared_text}".strip()
        haystack_words = set(_WORD_PATTERN.findall(haystack)) if haystack else set()
        for term in terms:
            if term in keyword_terms or term in haystack_words:
                term_map[term].add(expanded_idx)

    return term_map
