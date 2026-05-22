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
    # Per-arm prepared texts for "X eller Y" ingredients. Empty tuple when the
    # ingredient has no eller-alternatives. Each entry is already prepared by
    # _prepare_fast_ingredient_text so it can be passed directly to
    # matches_ingredient_fast as a fallback when the full-text match returns
    # None due to cross-arm carrier-context leakage (e.g. 'fraiche' carrier in
    # 'crème fraîche eller tjock yoghurt' blocking yoghurt products on the
    # yoghurt arm).
    eller_arms_prepared: Tuple[str, ...] = ()
