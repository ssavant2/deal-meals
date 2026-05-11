"""Declarative match bridges staged for matcher migration."""

from __future__ import annotations

from collections.abc import Iterable
import re

from .term_registry.exports import MATCH_BRIDGES as _REGISTRY_MATCH_BRIDGES


MATCH_BRIDGES = _REGISTRY_MATCH_BRIDGES

MATCH_BRIDGES_BY_ID = {bridge.id: bridge for bridge in MATCH_BRIDGES}


def _matches_any(patterns: Iterable[str], text: str) -> list[str]:
    return sorted(pattern for pattern in patterns if re.search(pattern, text))


def find_match_bridge_hits(
    *,
    ingredient_texts: Iterable[str],
    offer_keywords: Iterable[str],
    offer_text: str = "",
) -> tuple[dict[str, object], ...]:
    """Return declarative match bridges visible for one offer/recipe pair."""

    normalized_ingredients = [str(text or "").lower() for text in ingredient_texts]
    normalized_offer_keywords = " ".join(str(keyword or "").lower() for keyword in offer_keywords if keyword)
    normalized_offer_text = f"{str(offer_text or '').lower()} {normalized_offer_keywords}".strip()
    hits: list[dict[str, object]] = []

    for bridge in MATCH_BRIDGES:
        matched_ingredient_indices = [
            index
            for index, ingredient_text in enumerate(normalized_ingredients)
            if _matches_any(bridge.ingredient_patterns, ingredient_text)
        ]
        if not matched_ingredient_indices:
            continue

        matched_offer_patterns = _matches_any(bridge.offer_patterns, normalized_offer_text)
        if not matched_offer_patterns:
            continue
        if _matches_any(bridge.negative_offer_patterns, normalized_offer_text):
            continue

        hits.append({
            "id": bridge.id,
            "canonical": bridge.canonical,
            "matched_ingredient_indices": matched_ingredient_indices,
            "matched_offer_patterns": matched_offer_patterns,
            "aliases": sorted(bridge.aliases),
        })

    return tuple(hits)
