"""Canonical engine wrapper for ingredient/offer matching.

Phase 1 intentionally keeps semantic behavior identical to the current fast
matcher. The value in this module is that callers can now share typed builder
functions and a single match entry point before we route more of the system
through it.
"""

from __future__ import annotations

from .compound_text import _WORD_PATTERN
from .extraction import extract_keywords_from_ingredient
from .ingredient_data import IngredientMatchData
from .match_result import MatchResult
from .matching import _prepare_fast_ingredient_text, matches_ingredient_fast, precompute_offer_data
from .offer_data import OfferMatchData
from .versioning import (
    MATCHER_VERSION,
    OFFER_COMPILER_VERSION,
    RECIPE_COMPILER_VERSION,
)


def build_ingredient_match_data(
    ingredient_text: str,
    *,
    source_index: int = 0,
    expanded_index: int = 0,
) -> IngredientMatchData:
    """Build canonical ingredient-side matcher data.

    ``normalized_text`` intentionally mirrors the exact normalization used by
    ``matches_ingredient_fast()`` so parity tests can compare old and new paths
    directly.
    """
    normalized_text = _prepare_fast_ingredient_text(ingredient_text, _prenormalized=False)
    words = tuple(_WORD_PATTERN.findall(normalized_text))
    extracted_keywords = frozenset(extract_keywords_from_ingredient(ingredient_text))
    return IngredientMatchData(
        raw_text=ingredient_text,
        normalized_text=normalized_text,
        words=words,
        extracted_keywords=extracted_keywords,
        prepared_fast_text=True,
        source_index=source_index,
        expanded_index=expanded_index,
    )


def build_prepared_ingredient_match_data(
    normalized_text: str,
    *,
    raw_text: str | None = None,
    words: tuple[str, ...] | None = None,
    extracted_keywords: frozenset[str] | None = None,
    prepared_fast_text: bool = False,
    source_index: int = 0,
    expanded_index: int = 0,
) -> IngredientMatchData:
    """Wrap already-prepared recipe-matcher ingredient text as canonical data.

    ``RecipeMatcher`` performs additional recipe-level cleanup before calling
    the semantic matcher. This helper lets that path share the canonical engine
    without re-normalizing or changing behavior.
    """
    if words is None:
        words = tuple(_WORD_PATTERN.findall(normalized_text))
    if extracted_keywords is None:
        extracted_keywords = frozenset()
    return IngredientMatchData(
        raw_text=raw_text or normalized_text,
        normalized_text=normalized_text,
        words=words,
        extracted_keywords=extracted_keywords,
        prepared_fast_text=prepared_fast_text,
        source_index=source_index,
        expanded_index=expanded_index,
    )


def build_offer_match_data(
    offer_name: str,
    category: str = "",
    *,
    brand: str = "",
    weight_grams: float | None = None,
) -> OfferMatchData:
    """Build canonical offer-side matcher data from the existing precompute step."""
    precomputed = precompute_offer_data(
        offer_name,
        category,
        brand=brand,
        weight_grams=weight_grams,
    )
    return OfferMatchData(
        name=offer_name,
        category=category,
        brand=brand,
        weight_grams=weight_grams,
        precomputed=precomputed,
    )


def build_precomputed_offer_match_data(
    offer_name: str,
    *,
    category: str = "",
    brand: str = "",
    weight_grams: float | None = None,
    precomputed: dict | None = None,
) -> OfferMatchData:
    """Wrap existing precomputed offer payload as canonical data."""
    if precomputed is None:
        return build_offer_match_data(
            offer_name,
            category,
            brand=brand,
            weight_grams=weight_grams,
        )
    return OfferMatchData(
        name=offer_name,
        category=category,
        brand=brand,
        weight_grams=weight_grams,
        precomputed=precomputed,
    )


def match_offer_to_ingredient(
    ingredient: IngredientMatchData,
    offer: OfferMatchData,
) -> MatchResult:
    """Run the canonical match decision for one ingredient/offer pair."""
    if not offer.precomputed:
        return MatchResult(matched=False, reason="missing_precomputed_offer_data")

    matched_keyword = matches_ingredient_fast(
        offer.precomputed,
        ingredient.normalized_text,
        _prenormalized=True,
        _prepared_fast_text=ingredient.prepared_fast_text,
        _ingredient_words=ingredient.words,
    )
    if not matched_keyword:
        return MatchResult(matched=False, reason="fast_match_no_match")

    return MatchResult(
        matched=True,
        matched_keyword=matched_keyword,
        canonical_family=matched_keyword,
        match_tier="fast_match",
    )
