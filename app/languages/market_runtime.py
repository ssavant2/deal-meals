"""Lightweight market/language adapter for shared ingestion utilities.

The matcher runtime owns the heavy recipe-offer matching backend. This module
keeps smaller shared surfaces (store saving, pantry matching, spell checking,
and store food filters) from importing a specific language package directly.
"""

from __future__ import annotations

import importlib
import os
import re
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Iterable

from .i18n import DEFAULT_LANGUAGE, normalize_language_code


MARKET_LANGUAGE_ENV = "MATCHER_LANGUAGE"
FALLBACK_MARKET_LANGUAGE = "sv"


@dataclass(frozen=True)
class FoodFilterProfile:
    food_categories: frozenset[str]
    non_food_categories: frozenset[str]
    food_indicators: tuple[str, ...]
    certification_logos: frozenset[str]
    non_food_strong: tuple[str, ...]
    non_food_indicators: tuple[str, ...]


@dataclass(frozen=True)
class SpellCheckProfile:
    known_words: frozenset[str]
    correction_targets: frozenset[str]
    safe_non_food_words: frozenset[str]
    inflection_suffixes: tuple[str, ...]
    default_excluded_words: frozenset[tuple[str, str]]


def _import_bases() -> tuple[str, ...]:
    own_base = __package__ or "languages"
    fallback_base = "languages" if own_base == "app.languages" else "app.languages"
    return (own_base, fallback_base)


def _candidate_languages() -> tuple[str, ...]:
    requested = normalize_language_code(os.getenv(MARKET_LANGUAGE_ENV) or DEFAULT_LANGUAGE)
    seen: set[str] = set()
    candidates: list[str] = []
    for language in (requested, DEFAULT_LANGUAGE, FALLBACK_MARKET_LANGUAGE):
        if language and language not in seen:
            candidates.append(language)
            seen.add(language)
    return tuple(candidates)


def _load_language_module(suffix: str, *, required: bool = True) -> ModuleType | None:
    errors: list[Exception] = []
    for language in _candidate_languages():
        for base in _import_bases():
            try:
                return importlib.import_module(f"{base}.{language}.{suffix}")
            except ModuleNotFoundError as exc:
                errors.append(exc)

    if required:
        raise ModuleNotFoundError(
            f"Could not import market module suffix '{suffix}' for any configured language"
        ) from (errors[-1] if errors else None)
    return None


def _lower_words(values: Iterable[Any]) -> set[str]:
    return {str(value).lower() for value in values if value is not None and str(value)}


def _mapping_keys_and_values(mapping: Any) -> set[str]:
    if not isinstance(mapping, dict):
        return set()

    values: set[str] = set()
    for key, value in mapping.items():
        if key:
            values.add(str(key).lower())
        if isinstance(value, (set, frozenset, list, tuple)):
            values.update(_lower_words(value))
        elif value:
            values.add(str(value).lower())
    return values


def _get_callable(module: ModuleType | None, *names: str):
    if module is None:
        return None
    for name in names:
        func = getattr(module, name, None)
        if callable(func):
            return func
    return None


def normalize_market_text(text: str | None) -> str:
    """Normalize offer/recipe text through the active market profile."""
    if text is None:
        return ""

    module = _load_language_module("normalization", required=False)
    normalizer = _get_callable(
        module,
        "normalize_market_text",
        "normalize_text",
    )
    value = str(text)
    return normalizer(value) if normalizer else re.sub(r"\s+", " ", value).strip()


def normalize_ingredient_text(ingredient: str | None) -> str:
    if ingredient is None:
        return ""
    module = _load_language_module("normalization", required=False)
    normalizer = _get_callable(module, "normalize_ingredient")
    if normalizer:
        return normalizer(ingredient)
    return normalize_market_text(ingredient).lower()


def strip_brand_from_name(name: str, brand: str | None) -> str:
    module = _load_language_module("normalization", required=False)
    strip_func = _get_callable(module, "strip_brand_from_name")
    if strip_func:
        return strip_func(name, brand or "")
    return name


def override_category_by_brand(category: str, brand: str | None) -> str:
    module = _load_language_module("category_utils", required=False)
    override_func = _get_callable(module, "override_category_by_brand")
    if override_func:
        return override_func(category, brand)
    return category


def extract_keywords_from_ingredient_backend(ingredient: str, *args, **kwargs) -> list[str]:
    module = _load_language_module("ingredient_matching.extraction", required=False)
    extract_func = _get_callable(module, "extract_keywords_from_ingredient")
    if extract_func:
        return list(extract_func(ingredient, *args, **kwargs))

    min_length = kwargs.get("min_length", 3)
    text = normalize_ingredient_text(ingredient)
    return [word for word in re.findall(r"\w+", text) if len(word) >= min_length]


def is_boring_recipe(recipe_name: str) -> bool:
    module = _load_language_module("recipe_filters", required=False)
    checker = _get_callable(module, "is_boring_recipe")
    return bool(checker(recipe_name)) if checker else False


def get_pantry_ignore_words() -> frozenset[str]:
    module = _load_language_module("pantry", required=False)
    return frozenset(getattr(module, "IGNORE_WORDS", frozenset()) or frozenset())


def get_food_filter_profile() -> FoodFilterProfile:
    module = _load_language_module("food_filters", required=False)
    return FoodFilterProfile(
        food_categories=frozenset(getattr(module, "FOOD_CATEGORIES", frozenset()) or frozenset()),
        non_food_categories=frozenset(getattr(module, "NON_FOOD_CATEGORIES", frozenset()) or frozenset()),
        food_indicators=tuple(getattr(module, "FOOD_INDICATORS", ()) or ()),
        certification_logos=frozenset(getattr(module, "CERTIFICATION_LOGOS", frozenset()) or frozenset()),
        non_food_strong=tuple(getattr(module, "NON_FOOD_STRONG", ()) or ()),
        non_food_indicators=tuple(getattr(module, "NON_FOOD_INDICATORS", ()) or ()),
    )


def get_unit_aliases() -> dict[str, str]:
    module = _load_language_module("store_units", required=False)
    return dict(getattr(module, "UNIT_ALIASES", {}) or {})


def get_default_unit() -> str:
    module = _load_language_module("store_units", required=False)
    return str(getattr(module, "DEFAULT_UNIT", "unit") or "unit")


def get_default_spell_excluded_words() -> frozenset[tuple[str, str]]:
    module = _load_language_module("spell_check", required=False)
    pairs = getattr(module, "DEFAULT_SPELL_EXCLUDED_WORDS", frozenset()) or frozenset()
    return frozenset((str(original), str(corrected)) for original, corrected in pairs)


def build_spell_check_profile(min_word_length: int) -> SpellCheckProfile:
    synonyms = _load_language_module("ingredient_matching.synonyms", required=False)
    keywords = _load_language_module("ingredient_matching.keywords", required=False)
    carrier_context = _load_language_module("ingredient_matching.carrier_context", required=False)
    specialty_rules = _load_language_module("ingredient_matching.specialty_rules", required=False)
    spell_check = _load_language_module("spell_check", required=False)

    known: set[str] = set()
    correction_targets: set[str] = set()

    keyword_sets = (
        "STOP_WORDS",
        "FLAVOR_WORDS",
        "NON_FOOD_KEYWORDS",
        "PROCESSED_FOODS",
        "IMPORTANT_SHORT_KEYWORDS",
    )
    for name in keyword_sets:
        known.update(_lower_words(getattr(keywords, name, ()) or ()))

    ingredient_parents = getattr(synonyms, "INGREDIENT_PARENTS", {}) or {}
    keyword_synonyms = getattr(synonyms, "KEYWORD_SYNONYMS", {}) or {}
    specialty_qualifiers = getattr(specialty_rules, "SPECIALTY_QUALIFIERS", {}) or {}
    carrier_products = getattr(carrier_context, "CARRIER_PRODUCTS", ()) or ()
    important_short = getattr(keywords, "IMPORTANT_SHORT_KEYWORDS", ()) or ()

    known.update(_mapping_keys_and_values(ingredient_parents))
    known.update(_mapping_keys_and_values(keyword_synonyms))
    known.update(str(key).lower() for key in specialty_qualifiers if key)
    for carrier in carrier_products:
        known.update(_lower_words(str(carrier).split()))

    correction_targets.update(_mapping_keys_and_values(ingredient_parents))
    correction_targets.update(_mapping_keys_and_values(keyword_synonyms))
    correction_targets.update(str(key).lower() for key in specialty_qualifiers if key)
    correction_targets.update(_lower_words(important_short))
    for carrier in carrier_products:
        correction_targets.update(_lower_words(str(carrier).split()))

    return SpellCheckProfile(
        known_words=frozenset(known),
        correction_targets=frozenset(
            word for word in correction_targets if len(word) >= min_word_length
        ),
        safe_non_food_words=frozenset(
            getattr(spell_check, "SAFE_NON_FOOD_WORDS", frozenset()) or frozenset()
        ),
        inflection_suffixes=tuple(
            getattr(spell_check, "INFLECTION_SUFFIXES", ()) or ()
        ),
        default_excluded_words=get_default_spell_excluded_words(),
    )
