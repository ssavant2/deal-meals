"""Shared term-registry data models.

The models intentionally avoid importing any language-specific matcher code.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import re


ENTRY_STATUSES = frozenset({"active", "planned", "watchlist", "deprecated", "inactive"})
ENTRY_TYPES = frozenset({"family", "alias", "guard", "bridge", "policy", "watchlist"})
LAYER_POLICIES = frozenset({
    "normal",
    "existing_canonical",
    "new_canonical",
    "offer_alias",
    "ingredient_alias",
    "route_only",
    "offer_only",
    "ingredient_only",
    "bridge_only",
    "accepted_filter",
    "no_product_text",
    "negative_guard_only",
})

_ENTRY_ID_RE = re.compile(
    r"^(?P<language>[a-z]{2,3})-(?P<market>[a-z]{2})\."
    r"(?P<entry_type>[a-z][a-z0-9_]*)\."
    r"(?P<canonical>[a-z0-9_]+)(?:\.(?P<short_name>[a-z0-9_]+))?$"
)


@dataclass(frozen=True)
class RegistryExample:
    ingredient: str
    offer_name: str
    offer_category: str = ""
    offer_brand: str = ""
    expected: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegistryEntry:
    entry_id: str
    language: str
    market: str
    canonical: str
    status: str = "active"
    variants: tuple[str, ...] = ()
    ingredient_terms: tuple[str, ...] = ()
    offer_terms: tuple[str, ...] = ()
    route_terms: tuple[str, ...] = ()
    final_match_terms: tuple[str, ...] = ()
    negative_guards: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    layer_policy: tuple[str, ...] = ("normal",)
    positive_examples: tuple[RegistryExample, ...] = ()
    negative_examples: tuple[RegistryExample, ...] = ()
    notes: str = ""
    language_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["positive_examples"] = [example.to_dict() for example in self.positive_examples]
        payload["negative_examples"] = [example.to_dict() for example in self.negative_examples]
        return payload


@dataclass(frozen=True)
class RegistryVariant:
    language: str
    market: str
    source_family: str
    canonical: str
    variant: str
    layer_role: str
    entry_id: str
    status: str = "active"
    source_file: str = ""
    source_refs: tuple[str, ...] = ()
    layer_policy: tuple[str, ...] = ("normal",)
    variant_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def coverage_key(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.language,
            self.market,
            self.source_family,
            self.canonical,
            self.variant,
            self.layer_role,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["coverage_key"] = list(self.coverage_key)
        return payload


@dataclass(frozen=True)
class CheckIssue:
    severity: str
    code: str
    message: str
    item_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_entry_id(entry_id: str) -> dict[str, str] | None:
    match = _ENTRY_ID_RE.fullmatch(entry_id)
    if not match:
        return None
    return {key: (value or "") for key, value in match.groupdict().items()}


def validate_registry_entry(entry: RegistryEntry) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    parsed = parse_entry_id(entry.entry_id)
    if not parsed:
        issues.append(CheckIssue(
            severity="error",
            code="invalid_entry_id",
            message="entry_id must match <language>-<market>.<entry_type>.<canonical>[.<short_name>]",
            item_id=entry.entry_id,
        ))
    else:
        if parsed["language"] != entry.language.lower():
            issues.append(CheckIssue(
                severity="error",
                code="entry_id_language_mismatch",
                message="entry_id language prefix does not match language field",
                item_id=entry.entry_id,
                details={"entry_id_language": parsed["language"], "language": entry.language},
            ))
        if parsed["market"] != entry.market.lower():
            issues.append(CheckIssue(
                severity="error",
                code="entry_id_market_mismatch",
                message="entry_id market prefix does not match market field",
                item_id=entry.entry_id,
                details={"entry_id_market": parsed["market"], "market": entry.market},
            ))
        if parsed["entry_type"] not in ENTRY_TYPES:
            issues.append(CheckIssue(
                severity="error",
                code="unknown_entry_type",
                message="entry_id uses an unknown entry type",
                item_id=entry.entry_id,
                details={"entry_type": parsed["entry_type"], "allowed": sorted(ENTRY_TYPES)},
            ))

    if entry.status not in ENTRY_STATUSES:
        issues.append(CheckIssue(
            severity="error",
            code="unknown_status",
            message="entry status is not recognized",
            item_id=entry.entry_id,
            details={"status": entry.status, "allowed": sorted(ENTRY_STATUSES)},
        ))

    unknown_policies = sorted(set(entry.layer_policy) - LAYER_POLICIES)
    if unknown_policies:
        issues.append(CheckIssue(
            severity="error",
            code="unknown_layer_policy",
            message="entry uses undocumented layer_policy values",
            item_id=entry.entry_id,
            details={"unknown": unknown_policies, "allowed": sorted(LAYER_POLICIES)},
        ))

    if not entry.canonical:
        issues.append(CheckIssue(
            severity="error",
            code="missing_canonical",
            message="entry canonical is required",
            item_id=entry.entry_id,
        ))

    return issues

