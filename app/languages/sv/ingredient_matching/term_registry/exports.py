"""Generated Swedish registry exports.

Runtime matcher modules may import narrowly migrated exports from this module
after the R2 equivalence checks pass. The builders operate on a registry
variant view supplied by checks/tests so they do not import legacy matcher
sources themselves.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from languages.term_registry.models import RegistryEntry, RegistryVariant

from ..rule_models import BackendAllowance, BlockerRule, MatchBridge, NoMatchPolicy
from .registry import load_registry_entries


MappingValue = str | list[str]

PARENT_MATCH_ONLY_SOURCE_FAMILY = "parent_match_only"
PARENT_MATCH_ONLY_LAYER_ROLE = "parent_match_only_mapping"
KEYWORD_SYNONYM_SOURCE_FAMILY = "keyword_synonym"
KEYWORD_SYNONYM_LAYER_ROLE = "keyword_synonym_mapping"
KEYWORD_EXTRA_PARENT_SOURCE_FAMILY = "keyword_extra_parent"
KEYWORD_EXTRA_PARENT_LAYER_ROLE = "keyword_extra_parent_mapping"
OFFER_EXTRA_KEYWORD_SOURCE_FAMILY = "offer_extra_keyword"
OFFER_EXTRA_KEYWORD_LAYER_ROLE = "offer_extra_keyword_mapping"
INGREDIENT_PARENT_SOURCE_FAMILY = "ingredient_parent"
INGREDIENT_PARENT_LAYER_ROLE = "ingredient_parent_mapping"
NO_MATCH_POLICY_SOURCE_FAMILY = "no_match_policy"
NO_MATCH_POLICY_KEYWORD_LAYER_ROLE = "negative_guard_keyword"
NO_MATCH_POLICY_PATTERN_LAYER_ROLE = "negative_guard_pattern"
MATCH_BRIDGE_SOURCE_FAMILY = "match_bridge"
MATCH_BRIDGE_POSITIVE_LAYER_ROLE = "bridge_positive"
MATCH_BRIDGE_NEGATIVE_LAYER_ROLE = "bridge_negative_guard"
INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY = "ingredient_routing_parent"
INGREDIENT_ROUTING_PARENT_LAYER_ROLE = "ingredient_routing_parent_mapping"
RECIPE_ROUTING_HELPER_SOURCE_FAMILY = "recipe_routing_helper"
RECIPE_ROUTING_EXTRA_ALIAS_LAYER_ROLE = "recipe_routing_extra_alias"


def _build_mapping_export_from_variants(
    variants: Iterable[RegistryVariant],
    *,
    source_family: str,
    layer_role: str,
    label: str,
) -> dict[str, str]:
    exported: dict[str, str] = {}
    for variant in variants:
        if variant.source_family != source_family:
            continue
        if variant.layer_role != layer_role:
            continue
        if not variant.variant or not variant.canonical:
            raise ValueError(
                f"{label} variant {variant.variant_id or variant.entry_id} "
                "must include both variant and canonical text"
            )
        previous = exported.get(variant.variant)
        if previous is not None and previous != variant.canonical:
            raise ValueError(
                f"{label} variant {variant.variant!r} maps to both "
                f"{previous!r} and {variant.canonical!r}"
            )
        exported[variant.variant] = variant.canonical
    return dict(sorted(exported.items()))


def build_parent_match_only_export(variants: Iterable[RegistryVariant]) -> dict[str, str]:
    """Build the registry equivalent of ``parent_maps.PARENT_MATCH_ONLY``."""

    return _build_mapping_export_from_variants(
        variants,
        source_family=PARENT_MATCH_ONLY_SOURCE_FAMILY,
        layer_role=PARENT_MATCH_ONLY_LAYER_ROLE,
        label=PARENT_MATCH_ONLY_SOURCE_FAMILY,
    )


def build_keyword_synonyms_export(variants: Iterable[RegistryVariant]) -> dict[str, str]:
    """Build the registry equivalent of ``synonyms.KEYWORD_SYNONYMS``."""

    return _build_mapping_export_from_variants(
        variants,
        source_family=KEYWORD_SYNONYM_SOURCE_FAMILY,
        layer_role=KEYWORD_SYNONYM_LAYER_ROLE,
        label=KEYWORD_SYNONYM_SOURCE_FAMILY,
    )


def build_ingredient_parents_export(variants: Iterable[RegistryVariant]) -> dict[str, str]:
    """Build the registry equivalent of ``synonyms.INGREDIENT_PARENTS``."""

    return _build_mapping_export_from_variants(
        variants,
        source_family=INGREDIENT_PARENT_SOURCE_FAMILY,
        layer_role=INGREDIENT_PARENT_LAYER_ROLE,
        label=INGREDIENT_PARENT_SOURCE_FAMILY,
    )


def build_ingredient_routing_parent_export(variants: Iterable[RegistryVariant]) -> dict[str, str]:
    """Build the registry equivalent of ``ingredient_routing._ROUTING_PARENT_TERMS``."""

    return _build_mapping_export_from_variants(
        variants,
        source_family=INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY,
        layer_role=INGREDIENT_ROUTING_PARENT_LAYER_ROLE,
        label=INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY,
    )


def build_recipe_routing_extra_alias_export(variants: Iterable[RegistryVariant]) -> dict[str, str]:
    """Build the registry equivalent of ``term_indexes._recipe_routing_extra_aliases`` outputs."""

    return _build_mapping_export_from_variants(
        variants,
        source_family=RECIPE_ROUTING_HELPER_SOURCE_FAMILY,
        layer_role=RECIPE_ROUTING_EXTRA_ALIAS_LAYER_ROLE,
        label=RECIPE_ROUTING_HELPER_SOURCE_FAMILY,
    )


def _append_multi_target(
    exported: dict[str, list[str]],
    *,
    variant: str,
    canonical: str,
    label: str,
) -> None:
    if not variant or not canonical:
        raise ValueError(f"{label} coverage requires variant and canonical")
    targets = exported.setdefault(variant, [])
    if canonical not in targets:
        targets.append(canonical)


def _finalize_multi_target_export(exported: dict[str, list[str]]) -> dict[str, MappingValue]:
    finalized: dict[str, MappingValue] = {}
    for variant, targets in sorted(exported.items()):
        if len(targets) == 1:
            finalized[variant] = targets[0]
        else:
            finalized[variant] = list(targets)
    return finalized


def _finalize_list_target_export(exported: dict[str, list[str]]) -> dict[str, list[str]]:
    return {
        variant: list(targets)
        for variant, targets in sorted(exported.items())
    }


def _build_multi_mapping_export_from_variants(
    variants: Iterable[RegistryVariant],
    *,
    source_family: str,
    layer_role: str,
    label: str,
) -> dict[str, MappingValue]:
    exported: dict[str, list[str]] = {}
    for variant in variants:
        if variant.source_family != source_family:
            continue
        if variant.layer_role != layer_role:
            continue
        _append_multi_target(
            exported,
            variant=variant.variant,
            canonical=variant.canonical,
            label=label,
        )
    return _finalize_multi_target_export(exported)


def _build_list_mapping_export_from_variants(
    variants: Iterable[RegistryVariant],
    *,
    source_family: str,
    layer_role: str,
    label: str,
) -> dict[str, list[str]]:
    exported: dict[str, list[str]] = {}
    for variant in variants:
        if variant.source_family != source_family:
            continue
        if variant.layer_role != layer_role:
            continue
        _append_multi_target(
            exported,
            variant=variant.variant,
            canonical=variant.canonical,
            label=label,
        )
    return _finalize_list_target_export(exported)


def build_keyword_extra_parents_export(
    variants: Iterable[RegistryVariant],
) -> dict[str, MappingValue]:
    """Build the registry equivalent of ``parent_maps.KEYWORD_EXTRA_PARENTS``."""

    return _build_multi_mapping_export_from_variants(
        variants,
        source_family=KEYWORD_EXTRA_PARENT_SOURCE_FAMILY,
        layer_role=KEYWORD_EXTRA_PARENT_LAYER_ROLE,
        label=KEYWORD_EXTRA_PARENT_SOURCE_FAMILY,
    )


def build_offer_extra_keywords_export(
    variants: Iterable[RegistryVariant],
) -> dict[str, list[str]]:
    """Build the registry equivalent of ``keywords.OFFER_EXTRA_KEYWORDS``."""

    return _build_list_mapping_export_from_variants(
        variants,
        source_family=OFFER_EXTRA_KEYWORD_SOURCE_FAMILY,
        layer_role=OFFER_EXTRA_KEYWORD_LAYER_ROLE,
        label=OFFER_EXTRA_KEYWORD_SOURCE_FAMILY,
    )


def _coverage_rows(entry: RegistryEntry) -> list[dict[str, Any]]:
    rows = (
        entry.language_payload.get("coverage")
        or entry.language_payload.get("legacy_coverage")
        or []
    )
    if not isinstance(rows, list):
        raise ValueError(f"{entry.entry_id} coverage must be a list")
    return rows


def _text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def _text_frozenset(value: Any) -> frozenset[str]:
    return frozenset(_text_tuple(value))


def _build_mapping_export_from_entries(
    entries: Iterable[RegistryEntry],
    *,
    source_family: str,
    layer_role: str,
    label: str,
) -> dict[str, str]:
    exported: dict[str, str] = {}
    for entry in entries:
        if entry.status != "active":
            continue
        for row in _coverage_rows(entry):
            if not isinstance(row, dict):
                raise ValueError(f"{entry.entry_id} coverage rows must be tables")
            if row.get("source_family") != source_family:
                continue
            if row.get("layer_role") != layer_role:
                continue
            variant = str(row.get("variant") or "")
            canonical = str(row.get("canonical") or entry.canonical or "")
            if not variant or not canonical:
                raise ValueError(f"{entry.entry_id} {label} coverage requires variant and canonical")
            previous = exported.get(variant)
            if previous is not None and previous != canonical:
                raise ValueError(
                    f"{label} variant {variant!r} maps to both "
                    f"{previous!r} and {canonical!r}"
                )
            exported[variant] = canonical
    return dict(sorted(exported.items()))


def build_parent_match_only_export_from_entries(entries: Iterable[RegistryEntry]) -> dict[str, str]:
    return _build_mapping_export_from_entries(
        entries,
        source_family=PARENT_MATCH_ONLY_SOURCE_FAMILY,
        layer_role=PARENT_MATCH_ONLY_LAYER_ROLE,
        label=PARENT_MATCH_ONLY_SOURCE_FAMILY,
    )


def build_keyword_synonyms_export_from_entries(entries: Iterable[RegistryEntry]) -> dict[str, str]:
    return _build_mapping_export_from_entries(
        entries,
        source_family=KEYWORD_SYNONYM_SOURCE_FAMILY,
        layer_role=KEYWORD_SYNONYM_LAYER_ROLE,
        label=KEYWORD_SYNONYM_SOURCE_FAMILY,
    )


def build_ingredient_parents_export_from_entries(entries: Iterable[RegistryEntry]) -> dict[str, str]:
    return _build_mapping_export_from_entries(
        entries,
        source_family=INGREDIENT_PARENT_SOURCE_FAMILY,
        layer_role=INGREDIENT_PARENT_LAYER_ROLE,
        label=INGREDIENT_PARENT_SOURCE_FAMILY,
    )


def build_ingredient_routing_parent_export_from_entries(
    entries: Iterable[RegistryEntry],
) -> dict[str, str]:
    return _build_mapping_export_from_entries(
        entries,
        source_family=INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY,
        layer_role=INGREDIENT_ROUTING_PARENT_LAYER_ROLE,
        label=INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY,
    )


def build_recipe_routing_extra_alias_export_from_entries(
    entries: Iterable[RegistryEntry],
) -> dict[str, str]:
    return _build_mapping_export_from_entries(
        entries,
        source_family=RECIPE_ROUTING_HELPER_SOURCE_FAMILY,
        layer_role=RECIPE_ROUTING_EXTRA_ALIAS_LAYER_ROLE,
        label=RECIPE_ROUTING_HELPER_SOURCE_FAMILY,
    )


def _build_multi_mapping_export_from_entries(
    entries: Iterable[RegistryEntry],
    *,
    source_family: str,
    layer_role: str,
    label: str,
) -> dict[str, MappingValue]:
    exported: dict[str, list[str]] = {}
    for entry in entries:
        if entry.status != "active":
            continue
        for row in _coverage_rows(entry):
            if not isinstance(row, dict):
                raise ValueError(f"{entry.entry_id} coverage rows must be tables")
            if row.get("source_family") != source_family:
                continue
            if row.get("layer_role") != layer_role:
                continue
            _append_multi_target(
                exported,
                variant=str(row.get("variant") or ""),
                canonical=str(row.get("canonical") or entry.canonical or ""),
                label=label,
            )
    return _finalize_multi_target_export(exported)


def _build_list_mapping_export_from_entries(
    entries: Iterable[RegistryEntry],
    *,
    source_family: str,
    layer_role: str,
    label: str,
) -> dict[str, list[str]]:
    exported: dict[str, list[str]] = {}
    for entry in entries:
        if entry.status != "active":
            continue
        for row in _coverage_rows(entry):
            if not isinstance(row, dict):
                raise ValueError(f"{entry.entry_id} coverage rows must be tables")
            if row.get("source_family") != source_family:
                continue
            if row.get("layer_role") != layer_role:
                continue
            _append_multi_target(
                exported,
                variant=str(row.get("variant") or ""),
                canonical=str(row.get("canonical") or entry.canonical or ""),
                label=label,
            )
    return _finalize_list_target_export(exported)


def build_keyword_extra_parents_export_from_entries(
    entries: Iterable[RegistryEntry],
) -> dict[str, MappingValue]:
    return _build_multi_mapping_export_from_entries(
        entries,
        source_family=KEYWORD_EXTRA_PARENT_SOURCE_FAMILY,
        layer_role=KEYWORD_EXTRA_PARENT_LAYER_ROLE,
        label=KEYWORD_EXTRA_PARENT_SOURCE_FAMILY,
    )


def build_offer_extra_keywords_export_from_entries(
    entries: Iterable[RegistryEntry],
) -> dict[str, list[str]]:
    return _build_list_mapping_export_from_entries(
        entries,
        source_family=OFFER_EXTRA_KEYWORD_SOURCE_FAMILY,
        layer_role=OFFER_EXTRA_KEYWORD_LAYER_ROLE,
        label=OFFER_EXTRA_KEYWORD_SOURCE_FAMILY,
    )


def build_no_match_policies_export_from_entries(
    entries: Iterable[RegistryEntry],
) -> tuple[NoMatchPolicy, ...]:
    policies: list[NoMatchPolicy] = []
    for entry in entries:
        if entry.status != "active":
            continue
        payload = entry.language_payload.get(NO_MATCH_POLICY_SOURCE_FAMILY)
        if not payload:
            continue
        if not isinstance(payload, dict):
            raise ValueError(f"{entry.entry_id} no_match_policy payload must be a table")
        policies.append(NoMatchPolicy(
            id=str(payload.get("id") or ""),
            rule_schema_version=int(payload.get("rule_schema_version") or 1),
            rule_version=int(payload.get("rule_version") or 1),
            canonical=str(payload.get("canonical") or entry.canonical or ""),
            ingredient_patterns=_text_tuple(payload.get("ingredient_patterns")),
            blocked_offer_keywords=_text_frozenset(payload.get("blocked_offer_keywords")),
            blocked_offer_patterns=_text_tuple(payload.get("blocked_offer_patterns")),
            allowed_specifics=_text_frozenset(payload.get("allowed_specifics")),
            reason=str(payload.get("reason") or entry.notes or ""),
            policy_ref=str(payload.get("policy_ref") or ""),
            fixture_refs=_text_frozenset(payload.get("fixture_refs")),
            supersedes=_text_frozenset(payload.get("supersedes")),
        ))
    return tuple(policies)


def _build_blocker_rule(payload: dict[str, Any]) -> BlockerRule:
    return BlockerRule(
        id=str(payload.get("id") or ""),
        rule_schema_version=int(payload.get("rule_schema_version") or 1),
        rule_version=int(payload.get("rule_version") or 1),
        side=str(payload.get("side") or ""),
        code=str(payload.get("code") or ""),
        reason=str(payload.get("reason") or ""),
        policy_ref=str(payload.get("policy_ref") or ""),
        fixture_refs=_text_frozenset(payload.get("fixture_refs")),
    )


def _build_backend_allowance(payload: dict[str, Any]) -> BackendAllowance:
    return BackendAllowance(
        id=str(payload.get("id") or ""),
        rule_schema_version=int(payload.get("rule_schema_version") or 1),
        rule_version=int(payload.get("rule_version") or 1),
        code=str(payload.get("code") or ""),
        reason=str(payload.get("reason") or ""),
        policy_ref=str(payload.get("policy_ref") or ""),
        fixture_refs=_text_frozenset(payload.get("fixture_refs")),
    )


def build_match_bridges_export_from_entries(
    entries: Iterable[RegistryEntry],
) -> tuple[MatchBridge, ...]:
    bridges: list[MatchBridge] = []
    for entry in entries:
        if entry.status != "active":
            continue
        payload = entry.language_payload.get(MATCH_BRIDGE_SOURCE_FAMILY)
        if not payload:
            continue
        if not isinstance(payload, dict):
            raise ValueError(f"{entry.entry_id} match_bridge payload must be a table")
        precedence = payload.get("precedence")
        bridges.append(MatchBridge(
            id=str(payload.get("id") or ""),
            rule_schema_version=int(payload.get("rule_schema_version") or 1),
            rule_version=int(payload.get("rule_version") or 1),
            canonical=str(payload.get("canonical") or entry.canonical or ""),
            ingredient_patterns=_text_tuple(payload.get("ingredient_patterns")),
            offer_patterns=_text_tuple(payload.get("offer_patterns")),
            negative_offer_patterns=_text_tuple(payload.get("negative_offer_patterns")),
            aliases=_text_frozenset(payload.get("aliases")),
            fixture_refs=_text_frozenset(payload.get("fixture_refs")),
            precedence=None if precedence is None else int(precedence),
            supersedes=_text_frozenset(payload.get("supersedes")),
            ingredient_form_signals=_text_frozenset(payload.get("ingredient_form_signals")),
            offer_form_signals=_text_frozenset(payload.get("offer_form_signals")),
            required_offer_form_signals=_text_frozenset(payload.get("required_offer_form_signals")),
            forbidden_offer_form_signals=_text_frozenset(payload.get("forbidden_offer_form_signals")),
            blockers=frozenset(
                _build_blocker_rule(blocker)
                for blocker in payload.get("blockers") or []
                if isinstance(blocker, dict)
            ),
            backend_allowances=frozenset(
                _build_backend_allowance(allowance)
                for allowance in payload.get("backend_allowances") or []
                if isinstance(allowance, dict)
            ),
        ))
    return tuple(bridges)


def build_runtime_exports_from_entries(entries: Iterable[RegistryEntry]) -> dict[str, object]:
    entries = list(entries)
    return {
        "PARENT_MATCH_ONLY": build_parent_match_only_export_from_entries(entries),
        "KEYWORD_SYNONYMS": build_keyword_synonyms_export_from_entries(entries),
        "INGREDIENT_PARENTS": build_ingredient_parents_export_from_entries(entries),
        "KEYWORD_EXTRA_PARENTS": build_keyword_extra_parents_export_from_entries(entries),
        "OFFER_EXTRA_KEYWORDS": build_offer_extra_keywords_export_from_entries(entries),
        "NO_MATCH_POLICIES": build_no_match_policies_export_from_entries(entries),
        "MATCH_BRIDGES": build_match_bridges_export_from_entries(entries),
        "INGREDIENT_ROUTING_PARENT_TERMS": build_ingredient_routing_parent_export_from_entries(entries),
        "RECIPE_ROUTING_EXTRA_ALIASES": build_recipe_routing_extra_alias_export_from_entries(entries),
    }


_REGISTRY_ENTRIES = load_registry_entries(include_local=True)

PARENT_MATCH_ONLY: dict[str, str] = build_parent_match_only_export_from_entries(_REGISTRY_ENTRIES)
KEYWORD_SYNONYMS: dict[str, str] = build_keyword_synonyms_export_from_entries(_REGISTRY_ENTRIES)
INGREDIENT_PARENTS: dict[str, str] = build_ingredient_parents_export_from_entries(_REGISTRY_ENTRIES)
KEYWORD_EXTRA_PARENTS: dict[str, MappingValue] = (
    build_keyword_extra_parents_export_from_entries(_REGISTRY_ENTRIES)
)
OFFER_EXTRA_KEYWORDS: dict[str, list[str]] = (
    build_offer_extra_keywords_export_from_entries(_REGISTRY_ENTRIES)
)
NO_MATCH_POLICIES: tuple[NoMatchPolicy, ...] = (
    build_no_match_policies_export_from_entries(_REGISTRY_ENTRIES)
)
MATCH_BRIDGES: tuple[MatchBridge, ...] = build_match_bridges_export_from_entries(_REGISTRY_ENTRIES)
INGREDIENT_ROUTING_PARENT_TERMS: dict[str, str] = (
    build_ingredient_routing_parent_export_from_entries(_REGISTRY_ENTRIES)
)
RECIPE_ROUTING_EXTRA_ALIASES: dict[str, str] = (
    build_recipe_routing_extra_alias_export_from_entries(_REGISTRY_ENTRIES)
)


def build_exports(variants: Iterable[RegistryVariant]) -> dict[str, object]:
    return {
        "PARENT_MATCH_ONLY": build_parent_match_only_export(variants),
        "KEYWORD_SYNONYMS": build_keyword_synonyms_export(variants),
        "INGREDIENT_PARENTS": build_ingredient_parents_export(variants),
        "KEYWORD_EXTRA_PARENTS": build_keyword_extra_parents_export(variants),
        "OFFER_EXTRA_KEYWORDS": build_offer_extra_keywords_export(variants),
        "INGREDIENT_ROUTING_PARENT_TERMS": build_ingredient_routing_parent_export(variants),
        "RECIPE_ROUTING_EXTRA_ALIASES": build_recipe_routing_extra_alias_export(variants),
    }
