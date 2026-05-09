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

from .registry import load_registry_entries


PARENT_MATCH_ONLY_SOURCE_FAMILY = "parent_match_only"
PARENT_MATCH_ONLY_LAYER_ROLE = "parent_match_only_mapping"
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


def _coverage_rows(entry: RegistryEntry) -> list[dict[str, Any]]:
    rows = (
        entry.language_payload.get("coverage")
        or entry.language_payload.get("legacy_coverage")
        or []
    )
    if not isinstance(rows, list):
        raise ValueError(f"{entry.entry_id} coverage must be a list")
    return rows


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


_REGISTRY_ENTRIES = load_registry_entries()

PARENT_MATCH_ONLY: dict[str, str] = build_parent_match_only_export_from_entries(_REGISTRY_ENTRIES)
INGREDIENT_ROUTING_PARENT_TERMS: dict[str, str] = (
    build_ingredient_routing_parent_export_from_entries(_REGISTRY_ENTRIES)
)
RECIPE_ROUTING_EXTRA_ALIASES: dict[str, str] = (
    build_recipe_routing_extra_alias_export_from_entries(_REGISTRY_ENTRIES)
)


def build_exports(variants: Iterable[RegistryVariant]) -> dict[str, object]:
    return {
        "PARENT_MATCH_ONLY": build_parent_match_only_export(variants),
        "INGREDIENT_ROUTING_PARENT_TERMS": build_ingredient_routing_parent_export(variants),
        "RECIPE_ROUTING_EXTRA_ALIASES": build_recipe_routing_extra_alias_export(variants),
    }
