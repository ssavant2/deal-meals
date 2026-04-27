"""
Language and localization module.

Structure:
- categories.py       - Internal category constants (English keys)
- i18n.py             - Internationalization framework
- sv/ui.py            - GUI translations for sv
- sv/categories.py    - Category display metadata for sv
- en_gb/ui.py         - English (United Kingdom) GUI translations
- en_gb/              - UK scaffold: UI, address/profile text, store helpers,
                        and loadable matcher wrappers

Ingredient matching and normalization:
- market_runtime.py            - Runtime hooks for active market rules
- sv/normalization.py          - Market text normalization for sv
- sv/ingredient_matching/      - Ingredient matching rules for sv

Usage:
    from languages.categories import MEAT, FISH, VEGETARIAN
    from languages.i18n import translate, get_translator
"""

from __future__ import annotations

import importlib

from .categories import (
    MEAT, FISH, VEGETARIAN, SMART_BUY,
    POULTRY, DELI, DAIRY,
    PRIMARY_CATEGORIES, ALL_CATEGORIES, MEAT_RELATED,
    DEFAULT_BALANCE, DEFAULT_BALANCE_PCT,
    is_meat_category
)

from .i18n import DEFAULT_LANGUAGE, normalize_language_code


def _load_category_metadata(language: str | None = None):
    """Load category labels/icons without pinning package import to one locale."""
    requested = normalize_language_code(language or DEFAULT_LANGUAGE)
    seen: set[str] = set()
    for candidate in (requested, DEFAULT_LANGUAGE, 'sv'):
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            return importlib.import_module(f"{__package__}.{candidate}.categories")
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("No category metadata module found")


_CATEGORY_METADATA = _load_category_metadata()
DISPLAY_NAMES = _CATEGORY_METADATA.DISPLAY_NAMES
CATEGORY_ICONS = _CATEGORY_METADATA.CATEGORY_ICONS
CATEGORY_COLORS = _CATEGORY_METADATA.CATEGORY_COLORS
