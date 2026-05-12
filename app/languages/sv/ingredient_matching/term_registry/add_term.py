"""Swedish add-a-term/export planning helpers.

The functions here keep the add-a-term workflow centered on registry TOML:
they do not edit matcher files or rebuild cache. They validate that explicit
coverage rows map to known Swedish matcher layers and summarize which runtime
exports a registry entry will affect.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from languages.term_registry.export_plan import ExportLayerSpec, build_registry_export_plan
from languages.term_registry.models import CheckIssue, RegistryEntry

from .exports import (
    INGREDIENT_PARENT_LAYER_ROLE,
    INGREDIENT_PARENT_SOURCE_FAMILY,
    INGREDIENT_ROUTING_PARENT_LAYER_ROLE,
    INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY,
    KEYWORD_EXTRA_PARENT_LAYER_ROLE,
    KEYWORD_EXTRA_PARENT_SOURCE_FAMILY,
    KEYWORD_SYNONYM_LAYER_ROLE,
    KEYWORD_SYNONYM_SOURCE_FAMILY,
    MATCH_BRIDGE_NEGATIVE_LAYER_ROLE,
    MATCH_BRIDGE_POSITIVE_LAYER_ROLE,
    MATCH_BRIDGE_SOURCE_FAMILY,
    NO_MATCH_POLICY_KEYWORD_LAYER_ROLE,
    NO_MATCH_POLICY_PATTERN_LAYER_ROLE,
    NO_MATCH_POLICY_SOURCE_FAMILY,
    OFFER_EXTRA_KEYWORD_LAYER_ROLE,
    OFFER_EXTRA_KEYWORD_SOURCE_FAMILY,
    PARENT_MATCH_ONLY_LAYER_ROLE,
    PARENT_MATCH_ONLY_SOURCE_FAMILY,
    RECIPE_ROUTING_EXTRA_ALIAS_LAYER_ROLE,
    RECIPE_ROUTING_HELPER_SOURCE_FAMILY,
    build_runtime_exports_from_entries,
)
from .registry import load_registry_entries


SV_EXPORT_LAYER_SPECS: tuple[ExportLayerSpec, ...] = (
    ExportLayerSpec(
        source_family=PARENT_MATCH_ONLY_SOURCE_FAMILY,
        layer_role=PARENT_MATCH_ONLY_LAYER_ROLE,
        export_name="PARENT_MATCH_ONLY",
        export_kind="mapping",
        description="parent_maps.PARENT_MATCH_ONLY",
    ),
    ExportLayerSpec(
        source_family=KEYWORD_SYNONYM_SOURCE_FAMILY,
        layer_role=KEYWORD_SYNONYM_LAYER_ROLE,
        export_name="KEYWORD_SYNONYMS",
        export_kind="mapping",
        description="synonyms.KEYWORD_SYNONYMS",
    ),
    ExportLayerSpec(
        source_family=INGREDIENT_PARENT_SOURCE_FAMILY,
        layer_role=INGREDIENT_PARENT_LAYER_ROLE,
        export_name="INGREDIENT_PARENTS",
        export_kind="mapping",
        description="synonyms.INGREDIENT_PARENTS",
    ),
    ExportLayerSpec(
        source_family=KEYWORD_EXTRA_PARENT_SOURCE_FAMILY,
        layer_role=KEYWORD_EXTRA_PARENT_LAYER_ROLE,
        export_name="KEYWORD_EXTRA_PARENTS",
        export_kind="multi_mapping",
        description="parent_maps.KEYWORD_EXTRA_PARENTS",
    ),
    ExportLayerSpec(
        source_family=OFFER_EXTRA_KEYWORD_SOURCE_FAMILY,
        layer_role=OFFER_EXTRA_KEYWORD_LAYER_ROLE,
        export_name="OFFER_EXTRA_KEYWORDS",
        export_kind="list_mapping",
        description="keywords.OFFER_EXTRA_KEYWORDS",
    ),
    ExportLayerSpec(
        source_family=INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY,
        layer_role=INGREDIENT_ROUTING_PARENT_LAYER_ROLE,
        export_name="INGREDIENT_ROUTING_PARENT_TERMS",
        export_kind="mapping",
        description="ingredient_routing._ROUTING_PARENT_TERMS",
    ),
    ExportLayerSpec(
        source_family=RECIPE_ROUTING_HELPER_SOURCE_FAMILY,
        layer_role=RECIPE_ROUTING_EXTRA_ALIAS_LAYER_ROLE,
        export_name="RECIPE_ROUTING_EXTRA_ALIASES",
        export_kind="mapping",
        description="term_indexes._recipe_routing_extra_aliases",
    ),
    ExportLayerSpec(
        source_family=NO_MATCH_POLICY_SOURCE_FAMILY,
        layer_role=NO_MATCH_POLICY_KEYWORD_LAYER_ROLE,
        export_name="NO_MATCH_POLICIES",
        export_kind="guard_payload",
        description="no_match_policies.NO_MATCH_POLICIES keyword guard",
    ),
    ExportLayerSpec(
        source_family=NO_MATCH_POLICY_SOURCE_FAMILY,
        layer_role=NO_MATCH_POLICY_PATTERN_LAYER_ROLE,
        export_name="NO_MATCH_POLICIES",
        export_kind="guard_payload",
        description="no_match_policies.NO_MATCH_POLICIES regex guard",
    ),
    ExportLayerSpec(
        source_family=MATCH_BRIDGE_SOURCE_FAMILY,
        layer_role=MATCH_BRIDGE_POSITIVE_LAYER_ROLE,
        export_name="MATCH_BRIDGES",
        export_kind="bridge_payload",
        description="match_bridges.MATCH_BRIDGES positive bridge",
    ),
    ExportLayerSpec(
        source_family=MATCH_BRIDGE_SOURCE_FAMILY,
        layer_role=MATCH_BRIDGE_NEGATIVE_LAYER_ROLE,
        export_name="MATCH_BRIDGES",
        export_kind="bridge_payload",
        description="match_bridges.MATCH_BRIDGES negative guard",
    ),
    ExportLayerSpec(
        source_family="extraction_helper",
        layer_role="hardcoded_keyword_output:extract_keywords_from_ingredient",
        export_name="EXTRACTION_HELPER",
        export_kind="code_helper",
        runtime=False,
        description="extraction.extract_keywords_from_ingredient literal output",
    ),
    ExportLayerSpec(
        source_family="extraction_helper",
        layer_role="hardcoded_keyword_output:extract_keywords_from_product",
        export_name="EXTRACTION_HELPER",
        export_kind="code_helper",
        runtime=False,
        description="extraction.extract_keywords_from_product literal output",
    ),
    ExportLayerSpec(
        source_family="matcher_regression_case",
        layer_role="positive_regression",
        export_name="MATCHER_REGRESSION_CASES",
        export_kind="fixture",
        runtime=False,
        description="matcher_regression_cases.json positive fixture",
    ),
    ExportLayerSpec(
        source_family="matcher_regression_case",
        layer_role="negative_regression",
        export_name="MATCHER_REGRESSION_CASES",
        export_kind="fixture",
        runtime=False,
        description="matcher_regression_cases.json negative fixture",
    ),
)


for _inventory_role in (
    "legacy_backend_allowance",
    "legacy_backend_validator",
    "legacy_extra_keyword",
    "legacy_extraction",
    "legacy_no_match_policy",
    "legacy_normalization",
    "legacy_parent",
    "legacy_prepared_text_expansion",
    "legacy_synonym",
    "legacy_validator",
):
    SV_EXPORT_LAYER_SPECS += (
        ExportLayerSpec(
            source_family="matcher_rule_inventory",
            layer_role=_inventory_role,
            export_name="MATCHER_RULE_INVENTORY",
            export_kind="inventory_contract",
            runtime=False,
            description=f"matcher_rule_inventory.json {_inventory_role}",
        ),
    )


def build_add_term_export_plan(
    entries: Iterable[RegistryEntry] | None = None,
    *,
    language: str = "sv",
    market: str = "SE",
) -> tuple[dict[str, Any], list[CheckIssue]]:
    if language != "sv" or market != "SE":
        raise ValueError("Swedish add-term export planning currently supports sv-SE only")
    if entries is None:
        entries = load_registry_entries()
    entries = list(entries)
    payload, issues = build_registry_export_plan(
        entries,
        specs=SV_EXPORT_LAYER_SPECS,
        language=language,
        market=market,
    )
    runtime_exports = build_runtime_exports_from_entries(entries)
    payload["summary"]["runtime_export_object_counts"] = {
        name: len(value) if hasattr(value, "__len__") else 0
        for name, value in sorted(runtime_exports.items())
    }
    return payload, issues
