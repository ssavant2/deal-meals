"""Synonym and parent mappings for Swedish ingredient matching."""

from typing import Dict

from .term_registry.exports import (
    INGREDIENT_PARENTS as _REGISTRY_INGREDIENT_PARENTS,
    KEYWORD_SYNONYMS as _REGISTRY_KEYWORD_SYNONYMS,
)


INGREDIENT_PARENTS: Dict[str, str] = _REGISTRY_INGREDIENT_PARENTS

KEYWORD_SYNONYMS: Dict[str, str] = _REGISTRY_KEYWORD_SYNONYMS
