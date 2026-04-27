"""Canonical offer-side matcher data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class OfferMatchData:
    """Typed wrapper around the legacy precomputed offer payload."""

    name: str
    category: str = ""
    brand: str = ""
    weight_grams: Optional[float] = None
    precomputed: Mapping[str, object] | None = None

    @property
    def keywords(self) -> tuple[str, ...]:
        if not self.precomputed:
            return ()
        return tuple(self.precomputed.get('keywords', ()))

    @property
    def normalized_name(self) -> str:
        if not self.precomputed:
            return ""
        return str(self.precomputed.get('name_normalized', ""))

