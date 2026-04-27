"""
English (United Kingdom) ingredient matching scaffold.

This package is intentionally loadable but not production-complete. Runtime
matching delegates to the Swedish implementation so the app keeps working while
UK-specific rules are developed in this folder.
"""

try:
    from languages.sv.ingredient_matching import *  # noqa: F401,F403
    from languages.sv.ingredient_matching import __all__ as _SV_ALL
except ModuleNotFoundError:
    from app.languages.sv.ingredient_matching import *  # noqa: F401,F403
    from app.languages.sv.ingredient_matching import __all__ as _SV_ALL

from .skeleton_data import (
    SAMPLE_INGREDIENTS,
    SAMPLE_MARKET_TERMS,
    SAMPLE_PARENT_SYNONYMS,
)


def build_recipe_ingredient_term_map(compiled_recipe_payload, routing_terms):
    """Return no ingredient hints until the UK matcher has real rule coverage."""
    return {str(term): set() for term in routing_terms if term}


__all__ = [
    *_SV_ALL,
    'SAMPLE_INGREDIENTS',
    'SAMPLE_MARKET_TERMS',
    'SAMPLE_PARENT_SYNONYMS',
]
