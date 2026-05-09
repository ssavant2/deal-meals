"""Read-only Swedish legacy inventory adapter for R0/R1 registry checks."""

from __future__ import annotations

from collections.abc import Iterable
import re

from languages.term_registry.models import RegistryVariant


LANGUAGE = "sv"
MARKET = "SE"
DEFAULT_BATCH_SIZE = 60


SOURCE_LAYER_POLICIES = {
    "matcher_rule_inventory": ("normal",),
    "matcher_regression_case": ("normal",),
    "match_bridge": ("bridge_only",),
    "no_match_policy": ("negative_guard_only",),
    "ingredient_parent": ("ingredient_alias",),
    "keyword_synonym": ("offer_alias",),
    "parent_match_only": ("route_only",),
    "keyword_extra_parent": ("route_only",),
    "offer_extra_keyword": ("offer_alias",),
    "ingredient_routing_parent": ("route_only",),
    "extraction_helper": ("normal",),
    "recipe_routing_helper": ("route_only",),
}


def _slug(value: str, *, fallback: str = "unknown") -> str:
    normalized = value.strip().lower()
    normalized = normalized.replace("å", "a").replace("ä", "a").replace("ö", "o")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return normalized or fallback


def _entry_id(canonical: str, source_type: str) -> str:
    entry_type = "guard" if source_type == "no_match_policy" else "family"
    return f"sv-se.{entry_type}.{_slug(canonical)}"


def _source_ref(source_type: str, source_id: str, source_ref: str) -> str:
    if source_type == "matcher_rule_inventory":
        return f"inventory:matcher_rule_inventory:{source_id}"
    if source_type == "matcher_regression_case":
        return f"fixture:matcher_regression_cases:{source_id}"
    if source_type == "match_bridge":
        return f"bridge:match_bridges:{source_id}"
    if source_type == "no_match_policy":
        return f"policy:no_match_policies:{source_id}"
    if source_type in {"extraction_helper", "recipe_routing_helper"}:
        family = "extraction" if source_type == "extraction_helper" else "term_indexes"
        return f"code:{family}:{source_ref}"
    return f"code:{source_type}:{source_ref or source_id}"


def _variant_to_registry_variant(variant) -> RegistryVariant:
    canonical = (
        str(getattr(variant, "canonical", "") or "")
        or str(getattr(variant, "expected_family", "") or "")
        or str(getattr(variant, "variant_text", "") or "")
    )
    source_type = str(getattr(variant, "source_type", ""))
    layer_policy = SOURCE_LAYER_POLICIES.get(source_type, ("normal",))
    if getattr(variant, "needs_product_text", False) and not getattr(variant, "product_text", ""):
        layer_policy = tuple(sorted(set(layer_policy) | {"no_product_text"}))

    source_id = str(getattr(variant, "source_id", ""))
    source_ref = str(getattr(variant, "source_ref", ""))
    return RegistryVariant(
        language=LANGUAGE,
        market=MARKET,
        source_family=source_type,
        canonical=canonical,
        variant=str(getattr(variant, "variant_text", "")),
        layer_role=str(getattr(variant, "variant_role", "")),
        entry_id=_entry_id(canonical, source_type),
        status="active",
        source_file=str(getattr(variant, "source_file", "")),
        source_refs=(_source_ref(source_type, source_id, source_ref),),
        layer_policy=layer_policy,
        variant_id=str(getattr(variant, "variant_id", "")),
        metadata={
            "batch_id": getattr(variant, "batch_id", ""),
            "batch_index": getattr(variant, "batch_index", 0),
            "row_index": getattr(variant, "row_index", 0),
            "expected": getattr(variant, "expected", None),
            "product_text": getattr(variant, "product_text", ""),
            "ingredient_text": getattr(variant, "ingredient_text", ""),
            "notes": getattr(variant, "notes", ""),
        },
    )


def iter_legacy_variants(batch_size: int = DEFAULT_BATCH_SIZE) -> Iterable[RegistryVariant]:
    # Keep the legacy dependency test-only and lazy to avoid runtime import cycles.
    from tests.run_term_pipeline_b_track_audit import build_variants

    for variant in build_variants(batch_size):
        yield _variant_to_registry_variant(variant)


def build_legacy_registry_variants(batch_size: int = DEFAULT_BATCH_SIZE) -> list[RegistryVariant]:
    return list(iter_legacy_variants(batch_size=batch_size))

