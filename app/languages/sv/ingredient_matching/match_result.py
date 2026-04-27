"""Canonical matcher result types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MatchResult:
    """Canonical match decision for one ingredient/offer pair."""

    matched: bool
    matched_keyword: Optional[str] = None
    canonical_family: Optional[str] = None
    match_tier: Optional[str] = None
    reason: Optional[str] = None

