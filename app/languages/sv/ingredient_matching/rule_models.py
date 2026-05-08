"""Declarative matcher rule model constructors.

These classes are validation-first data containers. Runtime matching still uses
the legacy helpers until individual rule families are migrated behind the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal


SUPPORTED_RULE_SCHEMA_VERSION = 1

RuleSide = Literal["ingredient", "offer", "backend", "both"]
ExpansionSide = Literal["ingredient", "offer", "both"]
EquivalenceScope = Literal["parity_only", "canonical_merge"]


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_version(rule_schema_version: int, rule_version: int) -> None:
    if rule_schema_version != SUPPORTED_RULE_SCHEMA_VERSION:
        raise ValueError(f"unknown rule_schema_version: {rule_schema_version!r}")
    if not isinstance(rule_version, int) or rule_version < 1:
        raise ValueError("rule_version must be a positive integer")


def _text_frozenset(values, field_name: str, *, min_size: int = 0) -> frozenset[str]:
    if values is None:
        values = ()
    result = frozenset(_require_text(str(value), field_name) for value in values)
    if len(result) < min_size:
        raise ValueError(f"{field_name} requires at least {min_size} entries")
    return result


def _text_tuple(values, field_name: str, *, min_size: int = 0) -> tuple[str, ...]:
    if values is None:
        values = ()
    result = tuple(_require_text(str(value), field_name) for value in values)
    if len(result) < min_size:
        raise ValueError(f"{field_name} requires at least {min_size} entries")
    return result


def _fixture_refs(values) -> frozenset[str]:
    return _text_frozenset(values, "fixture_refs", min_size=1)


@dataclass(frozen=True)
class SignalSource:
    kind: Literal["bridge", "legacy", "expansion", "parent", "synonym", "backend"]
    rule_id: str
    rule_version: int
    policy_ref: str

    def __post_init__(self) -> None:
        _require_text(self.kind, "kind")
        _require_text(self.rule_id, "rule_id")
        _require_text(self.policy_ref, "policy_ref")
        if not isinstance(self.rule_version, int) or self.rule_version < 1:
            raise ValueError("rule_version must be a positive integer")


@dataclass(frozen=True)
class BlockerRule:
    id: str
    rule_schema_version: int
    rule_version: int
    side: RuleSide
    code: str
    reason: str
    policy_ref: str
    fixture_refs: frozenset[str]

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_version(self.rule_schema_version, self.rule_version)
        if self.side not in {"ingredient", "offer", "backend", "both"}:
            raise ValueError(f"unknown blocker side: {self.side!r}")
        _require_text(self.code, "code")
        _require_text(self.reason, "reason")
        _require_text(self.policy_ref, "policy_ref")
        object.__setattr__(self, "fixture_refs", _fixture_refs(self.fixture_refs))


@dataclass(frozen=True)
class BackendAllowance:
    id: str
    rule_schema_version: int
    rule_version: int
    code: str
    reason: str
    policy_ref: str
    fixture_refs: frozenset[str]

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_version(self.rule_schema_version, self.rule_version)
        _require_text(self.code, "code")
        _require_text(self.reason, "reason")
        _require_text(self.policy_ref, "policy_ref")
        object.__setattr__(self, "fixture_refs", _fixture_refs(self.fixture_refs))


@dataclass(frozen=True)
class RouteExpansion:
    id: str
    rule_schema_version: int
    rule_version: int
    source: str
    exposes: frozenset[str]
    side: ExpansionSide
    reason: str
    fixture_refs: frozenset[str]

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_version(self.rule_schema_version, self.rule_version)
        _require_text(self.source, "source")
        object.__setattr__(self, "exposes", _text_frozenset(self.exposes, "exposes", min_size=1))
        if self.side not in {"ingredient", "offer", "both"}:
            raise ValueError(f"unknown route expansion side: {self.side!r}")
        _require_text(self.reason, "reason")
        object.__setattr__(self, "fixture_refs", _fixture_refs(self.fixture_refs))


@dataclass(frozen=True)
class CanonicalEquivalence:
    id: str
    rule_schema_version: int
    rule_version: int
    canonicals: frozenset[str]
    scope: EquivalenceScope
    reason: str
    policy_ref: str
    fixture_refs: frozenset[str]
    expires: date | None = None
    canonical_target: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_version(self.rule_schema_version, self.rule_version)
        canonicals = _text_frozenset(self.canonicals, "canonicals", min_size=2)
        object.__setattr__(self, "canonicals", canonicals)
        if self.scope not in {"parity_only", "canonical_merge"}:
            raise ValueError(f"unknown equivalence scope: {self.scope!r}")
        _require_text(self.reason, "reason")
        _require_text(self.policy_ref, "policy_ref")
        object.__setattr__(self, "fixture_refs", _fixture_refs(self.fixture_refs))
        if self.canonical_target is not None and self.canonical_target not in canonicals:
            raise ValueError("canonical_target must be one of canonicals")


@dataclass(frozen=True)
class NoMatchPolicy:
    id: str
    rule_schema_version: int
    rule_version: int
    canonical: str
    ingredient_patterns: tuple[str, ...]
    reason: str
    policy_ref: str
    fixture_refs: frozenset[str]
    blocked_offer_keywords: frozenset[str] = field(default_factory=frozenset)
    blocked_offer_patterns: tuple[str, ...] = ()
    allowed_specifics: frozenset[str] = field(default_factory=frozenset)
    supersedes: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_version(self.rule_schema_version, self.rule_version)
        _require_text(self.canonical, "canonical")
        object.__setattr__(
            self,
            "ingredient_patterns",
            _text_tuple(self.ingredient_patterns, "ingredient_patterns", min_size=1),
        )
        _require_text(self.reason, "reason")
        _require_text(self.policy_ref, "policy_ref")
        object.__setattr__(self, "fixture_refs", _fixture_refs(self.fixture_refs))
        object.__setattr__(
            self,
            "blocked_offer_keywords",
            _text_frozenset(self.blocked_offer_keywords, "blocked_offer_keywords"),
        )
        object.__setattr__(
            self,
            "blocked_offer_patterns",
            _text_tuple(self.blocked_offer_patterns, "blocked_offer_patterns"),
        )
        object.__setattr__(
            self,
            "allowed_specifics",
            _text_frozenset(self.allowed_specifics, "allowed_specifics"),
        )
        object.__setattr__(self, "supersedes", _text_frozenset(self.supersedes, "supersedes"))
        if not self.blocked_offer_keywords and not self.blocked_offer_patterns:
            raise ValueError("NoMatchPolicy requires blocked_offer_keywords or blocked_offer_patterns")


@dataclass(frozen=True)
class MatchBridge:
    id: str
    rule_schema_version: int
    rule_version: int
    canonical: str
    ingredient_patterns: tuple[str, ...]
    offer_patterns: tuple[str, ...]
    fixture_refs: frozenset[str]
    aliases: frozenset[str] = field(default_factory=frozenset)
    negative_offer_patterns: tuple[str, ...] = ()
    precedence: int | None = None
    supersedes: frozenset[str] = field(default_factory=frozenset)
    ingredient_form_signals: frozenset[str] = field(default_factory=frozenset)
    offer_form_signals: frozenset[str] = field(default_factory=frozenset)
    required_offer_form_signals: frozenset[str] = field(default_factory=frozenset)
    forbidden_offer_form_signals: frozenset[str] = field(default_factory=frozenset)
    blockers: frozenset[BlockerRule] = field(default_factory=frozenset)
    backend_allowances: frozenset[BackendAllowance] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_version(self.rule_schema_version, self.rule_version)
        _require_text(self.canonical, "canonical")
        object.__setattr__(
            self,
            "ingredient_patterns",
            _text_tuple(self.ingredient_patterns, "ingredient_patterns", min_size=1),
        )
        object.__setattr__(self, "offer_patterns", _text_tuple(self.offer_patterns, "offer_patterns", min_size=1))
        object.__setattr__(self, "fixture_refs", _fixture_refs(self.fixture_refs))
        object.__setattr__(self, "aliases", _text_frozenset(self.aliases, "aliases"))
        object.__setattr__(
            self,
            "negative_offer_patterns",
            _text_tuple(self.negative_offer_patterns, "negative_offer_patterns"),
        )
        if self.precedence is not None and not isinstance(self.precedence, int):
            raise ValueError("precedence must be an integer or None")
        for field_name in (
            "supersedes",
            "ingredient_form_signals",
            "offer_form_signals",
            "required_offer_form_signals",
            "forbidden_offer_form_signals",
        ):
            object.__setattr__(self, field_name, _text_frozenset(getattr(self, field_name), field_name))
        if not all(isinstance(blocker, BlockerRule) for blocker in self.blockers):
            raise ValueError("blockers entries must be BlockerRule instances")
        if not all(isinstance(allowance, BackendAllowance) for allowance in self.backend_allowances):
            raise ValueError("backend_allowances entries must be BackendAllowance instances")
        object.__setattr__(self, "blockers", frozenset(self.blockers))
        object.__setattr__(self, "backend_allowances", frozenset(self.backend_allowances))
