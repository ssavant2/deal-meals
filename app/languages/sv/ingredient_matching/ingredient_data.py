"""Canonical ingredient-side matcher data.

The first phase of the canonical pipeline keeps the existing semantic matcher
behavior intact while giving callers a typed, reusable representation of the
ingredient-side preprocessing that the fast matcher already depends on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Tuple


@dataclass(frozen=True)
class IngredientMatchData:
    """Normalized ingredient input for canonical match evaluation."""

    raw_text: str
    normalized_text: str
    words: Tuple[str, ...]
    extracted_keywords: FrozenSet[str]
    prepared_fast_text: bool = False
    source_index: int = 0
    expanded_index: int = 0
