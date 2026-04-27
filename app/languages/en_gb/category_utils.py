"""
English (United Kingdom) product category utilities scaffold.

This file is a starting point for UK store plugins. It intentionally covers only
common grocery words and should be expanded from real Tesco/Sainsbury's/Asda/etc.
data before being treated as production-quality categorisation.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Set


IMPORTED_COUNTRIES: List[str] = [
    'argentina', 'australia', 'brazil', 'denmark', 'france', 'germany',
    'ireland', 'italy', 'new zealand', 'poland', 'spain', 'usa',
]

IMPORTED_MEAT_BRANDS: List[str] = []

IMPORTED_SPECIALTY_EXCEPTIONS: List[str] = [
    'chorizo', 'prosciutto', 'serrano', 'salami', 'nduja', 'pancetta',
]

MEAT_NAME_KEYWORDS: List[str] = [
    'beef', 'pork', 'lamb', 'chicken', 'turkey', 'duck', 'bacon', 'ham',
    'sausage', 'mince', 'steak', 'joint', 'gammon',
]

MEAT_CATEGORIES: Set[str] = {'meat', 'poultry', 'deli'}
MEAT_EXTENDED_CATEGORIES: Set[str] = {'other', 'frozen'}

_EXPLICIT_LACTOSE_FREE: List[str] = [
    'lactose free', 'lactose-free',
]

_NATURALLY_LACTOSE_FREE: List[str] = [
    'cheddar', 'parmesan', 'gouda', 'edam', 'emmental', 'pecorino',
    'manchego', 'butter',
]

_LACTOSE_CONTAINING_BASES: List[str] = [
    'milk', 'cream', 'yoghurt', 'yogurt', 'creme fraiche', 'ice cream',
]

_CATEGORY_KEYWORDS = {
    'poultry': {'chicken', 'turkey', 'duck'},
    'meat': {'beef', 'pork', 'lamb', 'steak', 'mince', 'gammon'},
    'fish': {'salmon', 'cod', 'haddock', 'tuna', 'prawn', 'prawns', 'shrimp'},
    'dairy': {'milk', 'cheese', 'cream', 'yoghurt', 'yogurt', 'butter'},
    'vegetables': {'potato', 'potatoes', 'onion', 'carrot', 'tomato', 'pepper'},
    'fruit': {'apple', 'banana', 'orange', 'berries', 'strawberry'},
    'bread': {'bread', 'rolls', 'baguette', 'brioche'},
    'pantry': {'pasta', 'rice', 'flour', 'beans', 'lentils', 'oil'},
    'spices': {'salt', 'pepper', 'spice', 'herbs', 'sauce', 'stock'},
    'beverages': {'juice', 'water', 'tea', 'coffee', 'cola'},
    'candy': {'sweets', 'crisps', 'chocolate', 'biscuits'},
    'household': {'detergent', 'washing up', 'toilet roll', 'cleaner'},
    'hygiene': {'shampoo', 'soap', 'toothpaste', 'deodorant'},
}


def _contains_any(value: str, words: Iterable[str]) -> bool:
    return any(re.search(rf'\b{re.escape(word)}\b', value) for word in words)


def normalize_api_category(category: str | None) -> str:
    """Map common UK store category labels to internal category keys."""
    value = (category or '').strip().lower()
    if not value:
        return 'other'

    for internal, words in _CATEGORY_KEYWORDS.items():
        if _contains_any(value, words):
            return internal
    return 'other'


def guess_category(product_name: str, api_category: str | None = None) -> str:
    """Guess an internal category from a UK product name and optional API label."""
    category = normalize_api_category(api_category)
    if category != 'other':
        return category

    name = (product_name or '').lower()
    for internal, words in _CATEGORY_KEYWORDS.items():
        if _contains_any(name, words):
            return internal
    return 'other'


def is_lactose_free(product_name: str) -> bool:
    """Basic UK lactose-free detection for future store plugins."""
    name = (product_name or '').lower()
    if _contains_any(name, _EXPLICIT_LACTOSE_FREE):
        return True
    if _contains_any(name, _LACTOSE_CONTAINING_BASES):
        return False
    return _contains_any(name, _NATURALLY_LACTOSE_FREE)
