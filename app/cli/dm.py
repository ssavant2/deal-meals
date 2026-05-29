"""Deal Meals developer CLI."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import tomllib
from typing import Annotated, Any, Iterable, Literal, Mapping
import unicodedata

import typer

from support_checks.audit_matcher_contract_toml_sources import (
    contract_spec_by_name,
    load_contract_source,
    write_contract_source,
)
from support_checks.generate_matcher_contract_json_from_toml_sources import check_generated_contract_json
from support_checks.generate_matcher_registry_coverage import generate_coverage_files
from support_checks.matcher_contracts import (
    contract_paths,
)


APP_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = APP_DIR.parent
SUPPORT_CHECKS_DIR = APP_DIR / "support_checks"
SV_DIR = APP_DIR / "languages" / "sv"

DEFAULT_KEYWORD_EXTRA_PARENT_FILE = (
    SV_DIR / "ingredient_matching" / "term_registry" / "entries" / "keyword_extra_parent.toml"
)
DEFAULT_DEEP_SANITY_FILE = SUPPORT_CHECKS_DIR / "run_deep_matcher_sanity.py"
DEEP_SANITY_FINAL_SUMMARY_MARKER = "# FINAL SUMMARY - keep at EOF"


app = typer.Typer(help="Deal Meals developer tools.")
matcher_app = typer.Typer(help="Matcher rule-change workflows.")
matcher_add_app = typer.Typer(help="Generate matcher rule-change artifacts.")
matcher_fixture_app = typer.Typer(help="Maintain matcher regression fixtures.")
matcher_modify_app = typer.Typer(help="Modify existing matcher rule artifacts.")
matcher_session_app = typer.Typer(help="Group matcher edits and run one final validation sequence.")
matcher_batch_app = typer.Typer(help="Batch matcher edits and run one final validation sequence.")
matcher_app.add_typer(matcher_add_app, name="add")
matcher_app.add_typer(matcher_fixture_app, name="fixture")
matcher_app.add_typer(matcher_modify_app, name="modify")
matcher_app.add_typer(matcher_session_app, name="session")
matcher_app.add_typer(matcher_batch_app, name="batch")
app.add_typer(matcher_app, name="matcher")


MATCHER_SESSION_VERSION = 1
MATCHER_SESSION_DIR = "deal-meals"
MATCHER_SESSION_FILE = "matcher-session.json"
MATCHER_SESSION_FALLBACK_DIR = ".dm"
MATCHER_SESSION_RELEVANT_PREFIXES = (
    "app/languages/sv/ingredient_matching/",
    "app/languages/sv/matcher_contracts/",
    "app/support_checks/",
    "docs/runbooks/MATCHER_RULE_CHANGE_RUNBOOK.md",
    "docs/MATCHER_REGISTRY_ARCHITECTURE.md",
    "docs/TESTING.md",
)


@dataclass(frozen=True)
class MatcherPaths:
    tree_root: Path
    app_dir: Path
    repo_root: Path
    fixture_file: Path
    inventory_file: Path
    fixture_source_file: Path
    inventory_source_file: Path
    registry_entries_dir: Path
    keyword_extra_parent_file: Path
    keyword_synonym_file: Path
    runtime_overlay_file: Path
    deep_sanity_file: Path


@dataclass(frozen=True)
class MatcherChangePlan:
    command: str
    policy_ref: str
    entry_ids: tuple[str, ...]
    fixture_ids: tuple[str, ...]
    inventory_id: str | None
    toml_preview: str
    sanity_preview: str
    runtime_delta_filename: str | None = None

    @property
    def first_fixture_id(self) -> str:
        if not self.fixture_ids:
            raise typer.BadParameter(f"{self.command} generated no fixture ids")
        return self.fixture_ids[0]


@dataclass(frozen=True)
class RegistryFixtureRefRemovalPlan:
    path: Path
    new_text: str
    changed_entries: tuple[str, ...]
    dropped_entries: tuple[str, ...]


@dataclass(frozen=True)
class MatcherGuide:
    label: str
    status: str
    summary: str
    steps: tuple[str, ...]


@dataclass(frozen=True)
class MatcherDoctorCheck:
    check_id: str
    status: Literal["ok", "needs_action", "warning", "blocking_error"]
    summary: str
    details: Mapping[str, Any]
    next_command: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.check_id,
            "status": self.status,
            "summary": self.summary,
            "details": dict(self.details),
        }
        if self.next_command:
            payload["next_command"] = self.next_command
        return payload


@dataclass(frozen=True)
class SimpleTomlSurface:
    command: str
    file_stem: str
    entry_type: Literal["alias", "family"]
    term_field: Literal["ingredient_terms", "offer_terms", "route_terms"]
    layer_policy: str
    layer_role: str
    notes: str
    default_sanity_ingredient: Literal["canonical", "variant"]
    default_sanity_offer: Literal["canonical", "variant"]


@dataclass(frozen=True)
class RuntimeOverlaySurface:
    command: str
    section: str
    value_field: str
    mapping_name: str
    guide_label: str


@dataclass(frozen=True)
class RuntimePairSurface:
    command: str
    section: str
    source_field: str
    target_field: str
    guide_label: str


@dataclass(frozen=True)
class RuntimeSetUpdateSurface:
    command: str
    section: str
    surface: str
    default_action: Literal["add", "remove"]
    guide_label: str


@dataclass(frozen=True)
class RuntimeTermSetSurface:
    command: str
    section: str
    value_field: str
    mapping_name: str
    guide_label: str
    broad_guard_min_chars: int | None = None


@dataclass(frozen=True)
class RuntimeContextSurface:
    command: str
    section: str
    key_field: str
    values_field: str
    mapping_name: str
    guide_label: str


@dataclass(frozen=True)
class RuntimeCompoundSurface:
    command: str
    section: str
    guide_label: str


@dataclass(frozen=True)
class RuntimeSpecialtySurface:
    command: str
    section: str
    key_field: str
    values_field: str
    guide_label: str


@dataclass(frozen=True)
class RegistryEntryRecord:
    surface: str
    entry_id: str
    status: str
    canonical: str
    terms: tuple[str, ...]
    start: int
    end: int
    block: str


SIMPLE_TOML_SURFACES: dict[str, SimpleTomlSurface] = {
    "ingredient-parent": SimpleTomlSurface(
        command="ingredient-parent",
        file_stem="ingredient_parent",
        entry_type="alias",
        term_field="ingredient_terms",
        layer_policy="ingredient_alias",
        layer_role="ingredient_parent_mapping",
        notes="Generated by dm matcher add ingredient-parent.",
        default_sanity_ingredient="variant",
        default_sanity_offer="canonical",
    ),
    "offer-extra-keyword": SimpleTomlSurface(
        command="offer-extra-keyword",
        file_stem="offer_extra_keyword",
        entry_type="alias",
        term_field="offer_terms",
        layer_policy="offer_alias",
        layer_role="offer_extra_keyword_mapping",
        notes="Generated by dm matcher add offer-extra-keyword.",
        default_sanity_ingredient="canonical",
        default_sanity_offer="variant",
    ),
    "ingredient-routing-parent": SimpleTomlSurface(
        command="ingredient-routing-parent",
        file_stem="ingredient_routing_parent",
        entry_type="family",
        term_field="route_terms",
        layer_policy="route_only",
        layer_role="ingredient_routing_parent_mapping",
        notes="Generated by dm matcher add ingredient-routing-parent.",
        default_sanity_ingredient="canonical",
        default_sanity_offer="variant",
    ),
    "parent-match-only": SimpleTomlSurface(
        command="parent-match-only",
        file_stem="parent_match_only",
        entry_type="family",
        term_field="route_terms",
        layer_policy="route_only",
        layer_role="parent_match_only_mapping",
        notes="Generated by dm matcher add parent-match-only. Route-only parent fallback; strict exclusions need negative proof.",
        default_sanity_ingredient="canonical",
        default_sanity_offer="variant",
    ),
    "recipe-routing-helper": SimpleTomlSurface(
        command="recipe-routing-helper",
        file_stem="recipe_routing_helper",
        entry_type="family",
        term_field="route_terms",
        layer_policy="route_only",
        layer_role="recipe_routing_extra_alias",
        notes="Generated by dm matcher add recipe-routing-helper.",
        default_sanity_ingredient="variant",
        default_sanity_offer="variant",
    ),
}

RUNTIME_OVERLAY_SURFACES: dict[str, RuntimeOverlaySurface] = {
    "pnb": RuntimeOverlaySurface(
        command="pnb",
        section="product_name_blockers",
        value_field="blockers",
        mapping_name="PRODUCT_NAME_BLOCKERS",
        guide_label="Product-name blocker",
    ),
    "fpb": RuntimeOverlaySurface(
        command="fpb",
        section="false_positive_blockers",
        value_field="blockers",
        mapping_name="FALSE_POSITIVE_BLOCKERS",
        guide_label="Ingredient false-positive blocker",
    ),
    "ksbc": RuntimeOverlaySurface(
        command="ksbc",
        section="keyword_suppressed_by_context",
        value_field="context",
        mapping_name="KEYWORD_SUPPRESSED_BY_CONTEXT",
        guide_label="Keyword suppressed by context",
    ),
    "processed-rule": RuntimeOverlaySurface(
        command="processed-rule",
        section="processed_product_rules",
        value_field="blocked_product_words",
        mapping_name="PROCESSED_PRODUCT_RULES",
        guide_label="Processed product rule",
    ),
    "processed-exemption": RuntimeOverlaySurface(
        command="processed-exemption",
        section="processed_rule_compound_exemptions",
        value_field="compounds",
        mapping_name="PROCESSED_RULES_COMPOUND_EXEMPTIONS",
        guide_label="Processed compound exemption",
    ),
}
RUNTIME_PAIR_SURFACES: dict[str, RuntimePairSurface] = {
    "space-normalization": RuntimePairSurface(
        command="space-normalization",
        section="space_normalizations",
        source_field="source",
        target_field="target",
        guide_label="Space normalization",
    ),
}
RUNTIME_SET_UPDATE_SURFACES: dict[str, RuntimeSetUpdateSurface] = {
    "stop-word": RuntimeSetUpdateSurface(
        command="stop-word",
        section="keyword_set_updates",
        surface="stop_words",
        default_action="add",
        guide_label="Stop word",
    ),
    "non-food-keyword": RuntimeSetUpdateSurface(
        command="non-food-keyword",
        section="keyword_set_updates",
        surface="non_food_keywords",
        default_action="add",
        guide_label="Non-food keyword",
    ),
    "flavor-word": RuntimeSetUpdateSurface(
        command="flavor-word",
        section="keyword_set_updates",
        surface="flavor_words",
        default_action="add",
        guide_label="Flavor word",
    ),
    "important-short-keyword": RuntimeSetUpdateSurface(
        command="important-short-keyword",
        section="keyword_set_updates",
        surface="important_short_keywords",
        default_action="add",
        guide_label="Important short keyword",
    ),
    "processed-food": RuntimeSetUpdateSurface(
        command="processed-food",
        section="keyword_set_updates",
        surface="processed_foods",
        default_action="remove",
        guide_label="Processed-food set update",
    ),
    "qualifier-required-keyword": RuntimeSetUpdateSurface(
        command="qualifier-required-keyword",
        section="keyword_set_updates",
        surface="qualifier_required_keywords",
        default_action="add",
        guide_label="Qualifier-required keyword",
    ),
    "carrier-product": RuntimeSetUpdateSurface(
        command="carrier-product",
        section="carrier_set_updates",
        surface="carrier_products",
        default_action="add",
        guide_label="Carrier product",
    ),
}
RUNTIME_TERM_SET_SURFACES: dict[str, RuntimeTermSetSurface] = {
    "gpb": RuntimeTermSetSurface(
        command="gpb",
        section="global_product_name_blockers",
        value_field="terms",
        mapping_name="GLOBAL_PRODUCT_NAME_BLOCKERS",
        guide_label="Global product-name blocker",
        broad_guard_min_chars=4,
    ),
    "strict-processed-rule": RuntimeTermSetSurface(
        command="strict-processed-rule",
        section="strict_processed_rules",
        value_field="terms",
        mapping_name="STRICT_PROCESSED_RULES",
        guide_label="Strict processed rule keyword",
    ),
    "carrier-context-required": RuntimeTermSetSurface(
        command="carrier-context-required",
        section="carrier_context_required",
        value_field="terms",
        mapping_name="CARRIER_CONTEXT_REQUIRED",
        guide_label="Carrier context required",
    ),
    "context-required-word": RuntimeTermSetSurface(
        command="context-required-word",
        section="context_required_words",
        value_field="terms",
        mapping_name="CONTEXT_REQUIRED_WORDS",
        guide_label="Context required word",
    ),
    "ingredient-requires-product-context": RuntimeTermSetSurface(
        command="ingredient-requires-product-context",
        section="ingredient_requires_in_product",
        value_field="terms",
        mapping_name="INGREDIENT_REQUIRES_IN_PRODUCT",
        guide_label="Ingredient requires product context",
    ),
}
RUNTIME_CONTEXT_SURFACES: dict[str, RuntimeContextSurface] = {
    "cuisine-context": RuntimeContextSurface(
        command="cuisine-context",
        section="cuisine_context",
        key_field="trigger",
        values_field="contexts",
        mapping_name="CUISINE_CONTEXT",
        guide_label="Cuisine context",
    ),
    "context-word-exemption": RuntimeContextSurface(
        command="context-word-exemption",
        section="context_word_keyword_exemptions",
        key_field="keyword",
        values_field="context_words",
        mapping_name="CONTEXT_WORD_KEYWORD_EXEMPTIONS",
        guide_label="Context-word keyword exemption",
    ),
}
RUNTIME_COMPOUND_SURFACES: dict[str, RuntimeCompoundSurface] = {
    "compound-protection": RuntimeCompoundSurface(
        command="compound-protection",
        section="compound_protection_updates",
        guide_label="Compound protection",
    ),
}
RUNTIME_SPECIALTY_SURFACES: dict[str, RuntimeSpecialtySurface] = {
    "specialty-qualifier": RuntimeSpecialtySurface(
        command="specialty-qualifier",
        section="specialty_qualifiers",
        key_field="keyword",
        values_field="qualifiers",
        guide_label="Specialty qualifier",
    ),
    "qualifier-equivalent": RuntimeSpecialtySurface(
        command="qualifier-equivalent",
        section="qualifier_equivalents",
        key_field="qualifier",
        values_field="equivalents",
        guide_label="Qualifier equivalent",
    ),
}
_RUNTIME_OVERLAY_SECTION_ORDER = (
    *(surface.section for surface in RUNTIME_OVERLAY_SURFACES.values()),
    *(surface.section for surface in RUNTIME_TERM_SET_SURFACES.values()),
    *(surface.section for surface in RUNTIME_PAIR_SURFACES.values()),
    "keyword_set_updates",
    "carrier_set_updates",
    *(surface.section for surface in RUNTIME_CONTEXT_SURFACES.values()),
    *(surface.section for surface in RUNTIME_COMPOUND_SURFACES.values()),
    *(surface.section for surface in RUNTIME_SPECIALTY_SURFACES.values()),
    "spice_fresh_rules",
    "product_name_substitutions",
    "secondary_ingredient_patterns",
)

_SPICE_FRESH_RULE_FIELDS = (
    "allowed_indicators",
    "blocked_product_words",
    "blocked_whole_product_words",
    "dried_indicators",
    "fresh_product_words",
    "ground_indicators",
    "pickled_indicators",
    "pickled_product_words",
    "required_ground_product_words",
    "required_whole_product_words",
    "spice_indicators",
)


GUIDE_SHAPES: dict[str, MatcherGuide] = {
    "keyword-synonym": MatcherGuide(
        label="keyword-synonym",
        status="supported by dm matcher add",
        summary="Plain spelling/plural/compound aliases on the keyword_synonym registry surface.",
        steps=(
            "Run: ./bin/dm matcher add keyword-synonym <canonical> --variants <variant> --sanity-offer \"<offer>\" --offer-category <category>",
            "Use --with-fixture/--with-inventory only when the alias changes routing/parity/product-policy semantics.",
        ),
    ),
    "keyword-extra-parent": MatcherGuide(
        label="keyword-extra-parent",
        status="supported by dm matcher add",
        summary="Offer-side child/product terms that should roll up to a parent ingredient family.",
        steps=(
            "Run: ./bin/dm matcher add keyword-extra-parent <canonical> --kids <child1,child2> --recipe-name \"<recipe>\" --ingredient \"<ingredient>\"",
            "The command writes registry, fixture/inventory, generated JSON/coverage, sanity, and Track B gates by default.",
        ),
    ),
    "ingredient-parent": MatcherGuide(
        label="ingredient-parent",
        status="supported by dm matcher add",
        summary="Recipe-side variant should expose a known parent ingredient.",
        steps=(
            "Run: ./bin/dm matcher add ingredient-parent <canonical> --variants <variant> --sanity-offer \"<offer>\"",
            "Use --sanity-ingredient when the default variant ingredient is not the proof you want.",
        ),
    ),
    "offer-extra-keyword": MatcherGuide(
        label="offer-extra-keyword",
        status="supported by dm matcher add",
        summary="Product wording should expose an additional canonical offer keyword.",
        steps=(
            "Run: ./bin/dm matcher add offer-extra-keyword <canonical> --variants <product-term> --sanity-ingredient \"<ingredient>\"",
            "Use --offer-terms for multi-target offer aliases.",
        ),
    ),
    "ingredient-routing-parent": MatcherGuide(
        label="ingredient-routing-parent",
        status="supported by dm matcher add",
        summary="Ingredient-side compound or plural should route to a parent family term.",
        steps=(
            "Run: ./bin/dm matcher add ingredient-routing-parent <canonical> --variants <variant> --sanity-offer \"<offer>\"",
            "Use --sanity-ingredient when the recipe proof needs a broader parent phrase.",
        ),
    ),
    "parent-match-only": MatcherGuide(
        label="parent-match-only",
        status="supported by dm matcher add",
        summary="Product compound should expose a parent fallback. This is route-only; it does not enforce strict sibling exclusion.",
        steps=(
            "Run: ./bin/dm matcher add parent-match-only <canonical> --variants <product-term> --sanity-offer \"<offer>\"",
            "When the policy is strict, also pass --negative-offer and --negative-ingredient so the generated sanity proves the forbidden pair.",
            "Use --offer-category when category-sensitive matching is part of the proof.",
        ),
    ),
    "recipe-routing-helper": MatcherGuide(
        label="recipe-routing-helper",
        status="supported by dm matcher add",
        summary="Extra route alias used to connect recipe compounds to an existing family route.",
        steps=(
            "Run: ./bin/dm matcher add recipe-routing-helper <canonical> --variants <route-alias> --sanity-ingredient \"<compound ingredient>\"",
            "Prefer this only for known recipe-routing gaps; Python runtime tables remain manual.",
        ),
    ),
    "pnb": MatcherGuide(
        label="pnb",
        status="supported by dm matcher add",
        summary="PRODUCT_NAME_BLOCKERS: product text blocks a matched keyword unless the ingredient asks for it.",
        steps=(
            "When the mechanism is unclear, run: ./bin/dm matcher explain --offer \"<offer>\" --ingredient \"<ingredient>\"",
            "Run: ./bin/dm matcher add pnb <keyword> --blockers <word1,word2,...> --reason \"<why>\"",
            "PNB is product-side proof; do not treat matches_ingredient() alone as sufficient behavior evidence.",
            "If active space-normalization joins the product phrase into a compound, also cover the joined blocker form when warned.",
            "The command writes runtime_rule_overlays.toml, appends a focused sanity canary, and runs Track A gates by default.",
        ),
    ),
    "fpb": MatcherGuide(
        label="fpb",
        status="supported by dm matcher add",
        summary="FALSE_POSITIVE_BLOCKERS: ingredient context suppresses a keyword.",
        steps=(
            "When the mechanism is unclear, run: ./bin/dm matcher explain --offer \"<offer>\" --ingredient \"<ingredient>\"",
            "Run: ./bin/dm matcher add fpb <keyword> --blockers <word1,word2,...> --reason \"<why>\"",
            "If active space-normalization joins the ingredient phrase into a compound, also cover the joined blocker form when warned.",
            "If the recipe ingredient contains the keyword as a standalone word, verify with dm matcher probe; KSBC may be the right surface.",
            "The command writes runtime_rule_overlays.toml, appends a focused sanity canary, and runs Track A gates by default.",
        ),
    ),
    "gpb": MatcherGuide(
        label="gpb",
        status="supported by dm matcher add",
        summary="GLOBAL_PRODUCT_NAME_BLOCKERS: product text is globally out of matcher scope.",
        steps=(
            "When the mechanism is unclear, run: ./bin/dm matcher explain --offer \"<offer>\" --ingredient \"<ingredient>\"",
            "Run: ./bin/dm matcher add gpb --terms <term1,term2,...> --reason \"<why>\"",
            "Use GPB only when the whole product is out of recipe-matching scope regardless of keyword.",
            "Terms shorter than four normalized characters require --allow-broad.",
        ),
    ),
    "ksbc": MatcherGuide(
        label="ksbc",
        status="supported by dm matcher add",
        summary="KEYWORD_SUPPRESSED_BY_CONTEXT: ingredient context makes a generic keyword irrelevant.",
        steps=(
            "When the mechanism is unclear, run: ./bin/dm matcher explain --offer \"<offer>\" --ingredient \"<ingredient>\"",
            "Run: ./bin/dm matcher add ksbc <keyword> --context <word1,word2,...> --reason \"<why>\"",
            "If active space-normalization joins the context phrase into a compound, also cover the joined context form when warned.",
            "Use this carefully: KSBC is semantic and can suppress useful generic fallbacks.",
        ),
    ),
    "space-normalization": MatcherGuide(
        label="space-normalization",
        status="supported by dm matcher add",
        summary="Normalize a spaced/accent/plural surface form before extraction.",
        steps=(
            "Run: ./bin/dm matcher add space-normalization \"<source>\" --target \"<target>\" --reason \"<why>\"",
            "Use when extraction should see a joined or canonicalized token before matching.",
        ),
    ),
    "dual-keyword-normalization": MatcherGuide(
        label="dual-keyword-normalization",
        status="supported by dm matcher add",
        summary="Normalize one surface form into an ordered keyword phrase, e.g. specific canonical first plus a broader family keyword.",
        steps=(
            "Run: ./bin/dm matcher add dual-keyword-normalization \"<source>\" --primary <specific> --extra-keywords <family> --reason \"<why>\"",
            "The first target keyword wins canonical selection in fast-path matches, so put the concrete variety first.",
            "Use this when a source term must expose both an exact keyword and a broad guard/bridge keyword.",
        ),
    ),
    "stop-word": MatcherGuide(
        label="stop-word",
        status="supported by dm matcher add",
        summary="Add or remove STOP_WORDS extraction filters.",
        steps=(
            "Run: ./bin/dm matcher add stop-word --terms <word1,word2,...> --reason \"<why>\"",
            "Use when a product/ingredient descriptor should not become a matcher keyword at all.",
            "Removal requires --allow-removal because it can reopen broad matching behavior.",
        ),
    ),
    "non-food-keyword": MatcherGuide(
        label="non-food-keyword",
        status="supported by dm matcher add",
        summary="Add or remove NON_FOOD_KEYWORDS filters.",
        steps=(
            "Run: ./bin/dm matcher add non-food-keyword --terms <word1,word2,...> --reason \"<why>\"",
            "Use when a keyword means the product is non-food/tool/household scope, not a recipe ingredient.",
            "Removal requires --allow-removal because it can reopen broad matching behavior.",
        ),
    ),
    "flavor-word": MatcherGuide(
        label="flavor-word",
        status="supported by dm matcher add",
        summary="Add product flavor words stripped from carrier products.",
        steps=(
            "Run: ./bin/dm matcher add flavor-word --terms <word1,word2,...> --reason \"<why>\"",
            "Pair with carrier-product when the product family is also new.",
        ),
    ),
    "carrier-product": MatcherGuide(
        label="carrier-product",
        status="supported by dm matcher add",
        summary="Add carrier products whose flavor words should not become ingredient keywords.",
        steps=(
            "Run: ./bin/dm matcher add carrier-product --terms <carrier1,carrier2,...> --reason \"<why>\"",
            "Use for product families where flavor/filling words are variants, toppings, or mix-ins.",
        ),
    ),
    "important-short-keyword": MatcherGuide(
        label="important-short-keyword",
        status="supported by dm matcher add",
        summary="Force a short but meaningful food word through extraction.",
        steps=(
            "Run: ./bin/dm matcher add important-short-keyword --terms <word1,word2,...> --reason \"<why>\"",
            "Use narrowly; short words are high collision risk.",
        ),
    ),
    "processed-food": MatcherGuide(
        label="processed-food",
        status="supported by dm matcher add",
        summary="Add or remove simple PROCESSED_FOODS set entries.",
        steps=(
            "Run: ./bin/dm matcher add processed-food --terms <word1,word2,...> --action add|remove --reason \"<why>\"",
            "Use only for simple set membership; processed/form logic still belongs in code.",
        ),
    ),
    "processed-rule": MatcherGuide(
        label="processed-rule",
        status="supported by dm matcher add",
        summary="Add product-side processed/form indicators for a matched keyword.",
        steps=(
            "Run: ./bin/dm matcher add processed-rule <keyword> --blocked-product-words <w1,w2,...> --reason \"<why>\"",
            "Use when processed product wording should block a plain/fresh ingredient unless the ingredient asks for that form.",
            "Add strict-processed-rule separately when the product indicator must match exactly.",
        ),
    ),
    "processed-exemption": MatcherGuide(
        label="processed-exemption",
        status="supported by dm matcher add",
        summary="Exempt compound words from a processed-product rule.",
        steps=(
            "Run: ./bin/dm matcher add processed-exemption <keyword> --compounds <c1,c2,...> --reason \"<why>\"",
            "Use when a compound contains the base keyword but should not inherit its processed/form guard.",
        ),
    ),
    "strict-processed-rule": MatcherGuide(
        label="strict-processed-rule",
        status="supported by dm matcher add",
        summary="Require exact indicator agreement for processed-product rules on selected keywords.",
        steps=(
            "Run: ./bin/dm matcher add strict-processed-rule --terms <word1,word2,...> --reason \"<why>\"",
            "Use after a processed-rule exists when different product forms are not interchangeable.",
        ),
    ),
    "spice-fresh-rule": MatcherGuide(
        label="spice-fresh-rule",
        status="supported by dm matcher add",
        summary="Add bidirectional spice/fresh form guards for herbs, spices, and vegetables.",
        steps=(
            "Run: ./bin/dm matcher add spice-fresh-rule <keyword> --blocked-product-words <w1,...> --spice-indicators <w2,...> --reason \"<why>\"",
            "Use allowed/fresh/dried/ground options only for the exact runtime check they model.",
            "Prefer processed-rule when the rule is a simpler product-form blocker.",
        ),
    ),
    "qualifier-required-keyword": MatcherGuide(
        label="qualifier-required-keyword",
        status="supported by dm matcher add",
        summary="Require product qualifier words to also appear in ingredient text for selected keywords.",
        steps=(
            "Run: ./bin/dm matcher add qualifier-required-keyword --terms <word1,word2,...> --reason \"<why>\"",
            "Use for small keyword families where product flavor/type qualifiers must not match plain ingredient wording.",
            "Removal requires --allow-removal because it relaxes product qualifier validation.",
        ),
    ),
    "carrier-context-required": MatcherGuide(
        label="carrier-context-required",
        status="supported by dm matcher add",
        summary="Carrier products whose carrier word must also appear in the ingredient.",
        steps=(
            "Run: ./bin/dm matcher add carrier-context-required --terms <carrier1,carrier2,...> --reason \"<why>\"",
            "Use when stripped flavor words should only match within the same carrier family.",
        ),
    ),
    "context-required-word": MatcherGuide(
        label="context-required-word",
        status="supported by dm matcher add",
        summary="Product context words that the ingredient must repeat.",
        steps=(
            "Run: ./bin/dm matcher add context-required-word --terms <word1,word2,...> --reason \"<why>\"",
            "Use when a product subtype/form word makes a generic keyword unsafe without ingredient-side context.",
        ),
    ),
    "context-word-exemption": MatcherGuide(
        label="context-word-exemption",
        status="supported by dm matcher add",
        summary="A keyword that already implies one or more context-required words.",
        steps=(
            "Run: ./bin/dm matcher add context-word-exemption <keyword> --context-words <word1,...> --reason \"<why>\"",
            "Use after confirming the keyword itself is specific enough to satisfy the context word.",
        ),
    ),
    "ingredient-requires-product-context": MatcherGuide(
        label="ingredient-requires-product-context",
        status="supported by dm matcher add",
        summary="Ingredient words that require the product to repeat the same context.",
        steps=(
            "Run: ./bin/dm matcher add ingredient-requires-product-context --terms <word1,...> --reason \"<why>\"",
            "Use when ingredient wording names a form/carrier that should not match a plain product.",
        ),
    ),
    "product-name-substitution": MatcherGuide(
        label="product-name-substitution",
        status="supported by dm matcher add",
        summary="Rewrite an extracted product keyword when required product words are present.",
        steps=(
            "Run: ./bin/dm matcher add product-name-substitution --required-words <w1,w2> --old-keyword <old> --new-keyword <new> --reason \"<why>\"",
            "Use when product naming implies a more specific canonical keyword than extraction would otherwise keep.",
        ),
    ),
    "secondary-ingredient-pattern": MatcherGuide(
        label="secondary-ingredient-pattern",
        status="supported by dm matcher add",
        summary="Block a matched keyword when product text contains secondary-ingredient blockers.",
        steps=(
            "Run: ./bin/dm matcher add secondary-ingredient-pattern <keyword> --blockers <w1,w2> [--exceptions <w3>] --reason \"<why>\"",
            "Use when the product is primarily something else and the matched keyword is only a secondary ingredient.",
        ),
    ),
    "cuisine-context": MatcherGuide(
        label="cuisine-context",
        status="supported by dm matcher add",
        summary="Keep cuisine-seasoned products valid only in matching recipe contexts.",
        steps=(
            "Run: ./bin/dm matcher add cuisine-context <trigger> --contexts <term1,term2,...> --reason \"<why>\"",
            "Prefer this over PNB when the product is legitimate in the right cuisine.",
        ),
    ),
    "compound-protection": MatcherGuide(
        label="compound-protection",
        status="supported by dm matcher add",
        summary="Protect keywords from compound/prefix/suffix substring bleed.",
        steps=(
            "Run: ./bin/dm matcher add compound-protection --mode prefix-strict|suffix-strict|suffix-protected|embedded-protected --keywords <word1,...> --reason \"<why>\"",
            "Use before PNB/FPB when the real issue is token shape rather than semantic context.",
        ),
    ),
    "specialty-qualifier": MatcherGuide(
        label="specialty-qualifier",
        status="supported by dm matcher add",
        summary="Require product/ingredient qualifier agreement for a keyword family.",
        steps=(
            "Run: ./bin/dm matcher add specialty-qualifier <keyword> --qualifiers <q1,q2,...> [--bidirectional] --reason \"<why>\"",
            "Use --bidirectional when product qualifiers should also constrain plain ingredient recipes.",
            "Prefer ordinary specialty qualifiers for recipe-specific requirements; prefer KSBC when the ingredient context should suppress a broader keyword entirely.",
        ),
    ),
    "qualifier-equivalent": MatcherGuide(
        label="qualifier-equivalent",
        status="supported by dm matcher add",
        summary="Declare qualifier spellings/forms as equivalent for specialty checks.",
        steps=(
            "Run: ./bin/dm matcher add qualifier-equivalent <qualifier> --equivalents <q1,q2,...> --reason \"<why>\"",
            "Use for adjective forms and known cross-language/product-label equivalents.",
        ),
    ),
    "no-match-policy": MatcherGuide(
        label="no-match-policy",
        status="supported by dm matcher add/modify",
        summary="Declarative ingredient pattern plus blocked offer keyword/pattern should never match.",
        steps=(
            "Run: ./bin/dm matcher add no-match-policy <canonical> --ingredient-patterns \"<regex>\" --blocked-offer-keywords <keyword> --negative-ingredient \"<ingredient>\" --negative-offer \"<offer>\" --auto-fixture --auto-inventory --reason \"<why>\"",
            "Use --fixture-refs <fixture_id> when the durable fixture already exists, and --auto-inventory when the new policy needs inventory coverage.",
            "For an existing simple policy, run: ./bin/dm matcher modify no-match-policy <policy_ref> --set-ingredient-patterns \"<regex>\" --set-blocked-offer-patterns \"<regex>\"",
            "The auto flags create mechanical fixture/inventory bookkeeping only; you still choose the semantic patterns, blocker, examples, and reason.",
        ),
    ),
    "extraction-helper": MatcherGuide(
        label="extraction-helper",
        status="supported by dm matcher add",
        summary="Registry coverage and sanity proof for a hardcoded extraction.py keyword output; it does not write Python code.",
        steps=(
            "First edit extraction.py when new extraction behavior is needed, then verify with dm matcher trace-extraction.",
            "Run: ./bin/dm matcher add extraction-helper <canonical> --side product|ingredient|both --input \"<text>\" --source-refs <code-ref>",
            "When an existing simple extraction helper loses or changes a side, rerun with --replace-existing and the remaining --side.",
            "This covers an extraction.py code change; it does not replace the code change itself.",
        ),
    ),
    "match-bridge": MatcherGuide(
        label="match-bridge",
        status="modify supported; new rows remain staged Track B",
        summary="Declarative bridge diagnostics/guards; new bridge rows are not runtime-wired by themselves.",
        steps=(
            "Read the match_bridge callout in the matcher runbook before editing.",
            "For an existing simple bridge, run: ./bin/dm matcher modify match-bridge <policy_ref> --remove-offer-patterns \"<regex>\" or --set-offer-patterns \"<regex>\"",
            "Dual-write the runtime-wired keyword_extra_parent/ingredient_parent/keyword_synonym/offer_extra_keyword row when needed.",
            "Add fixture/inventory proof for durable behavior.",
            "Run: ./bin/dm matcher gates --track B --policy-ref <policy_ref>",
        ),
    ),
    "smart-blocker": MatcherGuide(
        label="smart-blocker",
        status="scaffold supported by dm matcher add",
        summary="Create and chain a matching.py smart-blocker stub; the rule logic remains a manual Python edit.",
        steps=(
            "Run: ./bin/dm matcher add smart-blocker <name> --description \"<why>\" [--sanity-ingredient \"<ingredient>\" --sanity-offer \"<offer>\" --expect no-match]",
            "Fill in the generated helper body in matching.py, then run Track A or Track B gates for the behavioral change.",
            "Use this only when existing declarative/runtime overlay surfaces cannot express the rule.",
        ),
    ),
    "modify": MatcherGuide(
        label="modify",
        status="supported by dm matcher",
        summary="Correct an existing runtime-overlay rule by exact id and rewrite its generated membership canary.",
        steps=(
            "Run: ./bin/dm matcher modify runtime-overlay <rule-id> --add-blocker <term> --remove-blocker <term> --reason \"<why>\"",
            "For KSBC, use --add-context/--remove-context instead of blocker options.",
            "Only runtime_rule_overlays.toml entries with explicit id are supported; historical base tables stay manual/out of scope.",
        ),
    ),
    "remove": MatcherGuide(
        label="remove",
        status="supported by dm matcher",
        summary="Soft-disable one runtime-overlay rule by exact id; requires a reason and removes generated membership canaries.",
        steps=(
            "Run: ./bin/dm matcher remove <rule-id> --reason \"<why>\"",
            "The entry is kept in runtime_rule_overlays.toml with status=inactive and inactive_reason for audit history.",
            "Use this for deliberate policy removal; use modify for ordinary blocker/context corrections.",
        ),
    ),
    "sanity-update": MatcherGuide(
        label="sanity-update",
        status="supported by dm matcher",
        summary="Update the expected canonical in one existing run_deep_matcher_sanity.py test.",
        steps=(
            "Run: ./bin/dm matcher sanity-update \"<test description substring>\" --expected <canonical-or-None>",
            "The selector may match the test description, policy ref, command, or generated sanity-id.",
            "Use when a deliberate rule change makes an older generated sanity expectation stale; ambiguous selectors fail.",
        ),
    ),
    "sanity-find": MatcherGuide(
        label="sanity-find",
        status="supported by dm matcher",
        summary="Find existing run_deep_matcher_sanity.py tests by description or generated metadata.",
        steps=(
            "Run: ./bin/dm matcher sanity-find \"<description-or-policy-or-id>\"",
            "Use --command <dm-add-command> or --generated-only to narrow noisy searches.",
            "Use --format json when scripting a follow-up sanity-update.",
        ),
    ),
    "reconcile-sanity": MatcherGuide(
        label="reconcile-sanity",
        status="supported by dm matcher",
        summary="Compare generated sanity expectations with current matcher behavior.",
        steps=(
            "Run: ./bin/dm matcher reconcile-sanity \"<description-or-policy-or-id>\"",
            "Use --all-generated for an audit pass, and --format json when scripting.",
            "Use --apply only for simple generated match(...) rows where the current matcher behavior is the intended expectation.",
        ),
    ),
    "compare-paths": MatcherGuide(
        label="compare-paths",
        status="supported by dm matcher",
        summary="Compare legacy live, canonical fast, backend, and offer precompute keyword paths for one pair.",
        steps=(
            "Run: ./bin/dm matcher compare-paths --offer \"<offer>\" --ingredient \"<ingredient>\"",
            "Use this when live/fast/backend disagree or when precomputed keywords/checks such as offer expansions or processed-product rules look suspicious.",
            "For a broader rule-family trace, follow up with: ./bin/dm matcher explain --offer \"<offer>\" --ingredient \"<ingredient>\"",
        ),
    ),
    "canonical-of": MatcherGuide(
        label="canonical-of",
        status="supported by dm matcher",
        summary="Show what canonical keyword(s) a term or phrase becomes in runtime extraction.",
        steps=(
            "Run: ./bin/dm matcher canonical-of \"<term-or-phrase>\"",
            "Use this before adding rules when Swedish terminology and runtime canonical names may differ, e.g. dragon -> estragon.",
            "Pass --offer-category/--brand when product extraction depends on them.",
        ),
    ),
}

GUIDE_ALIASES = {
    "keyword_synonym": "keyword-synonym",
    "keyword-synonyms": "keyword-synonym",
    "keyword_synonyms": "keyword-synonym",
    "synonym": "keyword-synonym",
    "keyword_extra_parent": "keyword-extra-parent",
    "keyword-extra-parents": "keyword-extra-parent",
    "keyword_extra_parents": "keyword-extra-parent",
    "extra-parent": "keyword-extra-parent",
    "ingredient_parent": "ingredient-parent",
    "ingredient-parents": "ingredient-parent",
    "ingredient_parents": "ingredient-parent",
    "offer_extra_keyword": "offer-extra-keyword",
    "offer-extra-keywords": "offer-extra-keyword",
    "offer_extra_keywords": "offer-extra-keyword",
    "ingredient_routing_parent": "ingredient-routing-parent",
    "routing-parent": "ingredient-routing-parent",
    "parent_match_only": "parent-match-only",
    "recipe_routing_helper": "recipe-routing-helper",
    "recipe-routing": "recipe-routing-helper",
    "no_match_policy": "no-match-policy",
    "no-match-policies": "no-match-policy",
    "no_match_policies": "no-match-policy",
    "no-match": "no-match-policy",
    "extraction_helper": "extraction-helper",
    "extraction-helpers": "extraction-helper",
    "extraction_helpers": "extraction-helper",
    "match_bridge": "match-bridge",
    "match-bridges": "match-bridge",
    "match_bridges": "match-bridge",
    "bridge": "match-bridge",
    "smart_blocker": "smart-blocker",
    "smart-blockers": "smart-blocker",
    "smart_blockers": "smart-blocker",
    "product-name-blocker": "pnb",
    "product_name_blocker": "pnb",
    "false-positive-blocker": "fpb",
    "false_positive_blocker": "fpb",
    "global-product-name-blocker": "gpb",
    "global_product_name_blocker": "gpb",
    "space_norm": "space-normalization",
    "space-normalisation": "space-normalization",
    "dual_keyword_normalization": "dual-keyword-normalization",
    "dual-keyword-normalisation": "dual-keyword-normalization",
    "dual_keyword_normalisation": "dual-keyword-normalization",
    "dual-normalization": "dual-keyword-normalization",
    "dual-normalisation": "dual-keyword-normalization",
    "flavor_words": "flavor-word",
    "flavour-word": "flavor-word",
    "carrier_products": "carrier-product",
    "important_short_keyword": "important-short-keyword",
    "processed_food": "processed-food",
    "processed_product_rule": "processed-rule",
    "processed-product-rule": "processed-rule",
    "processed_exemption": "processed-exemption",
    "processed-compound-exemption": "processed-exemption",
    "strict_processed_rule": "strict-processed-rule",
    "spice_fresh_rule": "spice-fresh-rule",
    "spice-vs-fresh-rule": "spice-fresh-rule",
    "qualifier_required_keyword": "qualifier-required-keyword",
    "qualifier-required": "qualifier-required-keyword",
    "cuisine_context": "cuisine-context",
    "carrier_context_required": "carrier-context-required",
    "context_required_word": "context-required-word",
    "context_required_words": "context-required-word",
    "context_word_exemption": "context-word-exemption",
    "context_word_keyword_exemptions": "context-word-exemption",
    "ingredient_requires_product_context": "ingredient-requires-product-context",
    "keyword_suppressed_by_context": "ksbc",
    "keyword-suppressed-by-context": "ksbc",
    "product_name_substitution": "product-name-substitution",
    "secondary_ingredient_pattern": "secondary-ingredient-pattern",
    "compound_strict": "compound-protection",
    "compound_protection": "compound-protection",
    "specialty": "specialty-qualifier",
    "specialty_qualifier": "specialty-qualifier",
    "specialty-qualifiers": "specialty-qualifier",
    "specialty_qualifiers": "specialty-qualifier",
    "qualifier_equivalent": "qualifier-equivalent",
    "qualifier-equivalents": "qualifier-equivalent",
    "qualifier_equivalents": "qualifier-equivalent",
    "sanity_update": "sanity-update",
    "update-sanity": "sanity-update",
    "sanity_find": "sanity-find",
    "find-sanity": "sanity-find",
    "reconcile_sanity": "reconcile-sanity",
    "sanity-reconcile": "reconcile-sanity",
    "runtime-modify": "modify",
    "runtime_modify": "modify",
    "runtime-remove": "remove",
    "runtime_remove": "remove",
    "compare_paths": "compare-paths",
    "path-compare": "compare-paths",
    "canonical_of": "canonical-of",
    "canonical": "canonical-of",
    "canonicalof": "canonical-of",
}


def _paths(tree_root: Path | None) -> MatcherPaths:
    contracts = contract_paths(tree_root)
    app_dir = contracts.app_dir
    repo_root = contracts.repo_root
    return MatcherPaths(
        tree_root=repo_root,
        app_dir=app_dir,
        repo_root=repo_root,
        fixture_file=contracts.fixture_file,
        inventory_file=contracts.inventory_file,
        fixture_source_file=(
            app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_regression_cases.toml"
        ),
        inventory_source_file=(
            app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_rule_inventory.toml"
        ),
        registry_entries_dir=(
            app_dir / "languages" / "sv" / "ingredient_matching" / "term_registry" / "entries"
        ),
        keyword_extra_parent_file=(
            app_dir
            / "languages"
            / "sv"
            / "ingredient_matching"
            / "term_registry"
            / "entries"
            / "keyword_extra_parent.toml"
        ),
        keyword_synonym_file=(
            app_dir
            / "languages"
            / "sv"
            / "ingredient_matching"
            / "term_registry"
            / "entries"
            / "keyword_synonym.toml"
        ),
        runtime_overlay_file=(
            app_dir / "languages" / "sv" / "ingredient_matching" / "runtime_rule_overlays.toml"
        ),
        deep_sanity_file=app_dir / "support_checks" / "run_deep_matcher_sanity.py",
    )


def _utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _git_output(paths: MatcherPaths, args: list[str]) -> tuple[str | None, str | None]:
    git = shutil.which("git")
    if git is None:
        return None, "git executable not found"
    for cwd in (paths.repo_root, paths.app_dir):
        try:
            result = subprocess.run(
                [git, *args],
                cwd=cwd,
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            return None, str(exc)
        if result.returncode == 0:
            return result.stdout.strip(), None
    error = (result.stderr or result.stdout or "git command failed").strip()
    return None, error


def _git_session_state_path(paths: MatcherPaths) -> Path | None:
    git_dir_text, _error = _git_output(paths, ["rev-parse", "--git-dir"])
    if not git_dir_text:
        return None
    git_dir = Path(git_dir_text)
    if not git_dir.is_absolute():
        git_dir = paths.repo_root / git_dir
    return git_dir / MATCHER_SESSION_DIR / MATCHER_SESSION_FILE


def _matcher_session_fallback_path(paths: MatcherPaths) -> Path:
    return paths.app_dir / MATCHER_SESSION_FALLBACK_DIR / MATCHER_SESSION_FILE


def _matcher_batch_metrics_path(paths: MatcherPaths) -> Path:
    return paths.app_dir / MATCHER_SESSION_FALLBACK_DIR / "matcher_batch_metrics.json"


def _matcher_session_state_paths(paths: MatcherPaths) -> tuple[Path, ...]:
    fallback_path = _matcher_session_fallback_path(paths)
    git_path = _git_session_state_path(paths)
    if git_path is None:
        return (fallback_path,)
    return (git_path, fallback_path)


def _matcher_session_state_path(paths: MatcherPaths) -> Path:
    state_paths = _matcher_session_state_paths(paths)
    for state_path in state_paths:
        if state_path.exists():
            return state_path
    return state_paths[0]


def _read_matcher_session_state(paths: MatcherPaths) -> tuple[Path, dict[str, Any]] | None:
    for state_path in _matcher_session_state_paths(paths):
        if not state_path.exists():
            continue
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(f"invalid matcher session state file {state_path}: {exc}") from exc
        if not isinstance(state, dict):
            raise typer.BadParameter(f"invalid matcher session state file {state_path}: expected object")
        return state_path, state
    return None


def _write_matcher_session_state(paths: MatcherPaths, state: Mapping[str, Any]) -> Path:
    last_error: OSError | None = None
    for state_path in _matcher_session_state_paths(paths):
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            last_error = exc
            continue
        return state_path
    if last_error is not None:
        raise typer.BadParameter(f"could not write matcher session state: {last_error}") from last_error
    raise typer.BadParameter("could not resolve matcher session state path")


def _matcher_session_is_active(paths: MatcherPaths) -> bool:
    return _read_matcher_session_state(paths) is not None


def _argv_has_option(option: str) -> bool:
    return any(arg == option or arg.startswith(f"{option}=") for arg in sys.argv[1:])


def _matcher_session_gates_forced() -> bool:
    return _argv_has_option("--run-gates")


def _matcher_session_should_defer_gates(paths: MatcherPaths) -> bool:
    return _matcher_session_is_active(paths) and not _matcher_session_gates_forced()


def _echo_session_deferred_gates(label: str = "gates") -> None:
    typer.echo(f"Matcher session active; deferred {label} (use --run-gates to force now).")


def _git_status_paths(paths: MatcherPaths) -> tuple[tuple[str, ...], str | None]:
    git = shutil.which("git")
    if git is None:
        return (), "git executable not found"
    try:
        result = subprocess.run(
            [git, "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=paths.repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return (), str(exc)
    if result.returncode != 0:
        error = (result.stderr or result.stdout or "git status failed").strip()
        return (), error

    changed_paths: list[str] = []
    entries = result.stdout.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        if not entry:
            index += 1
            continue
        status = entry[:2]
        path = entry[3:].replace("\\", "/")
        if status[0] in {"R", "C"} or status[1] in {"R", "C"}:
            index += 1
            if index < len(entries) and entries[index]:
                path = entries[index].replace("\\", "/")
        if path:
            changed_paths.append(path)
        index += 1
    return tuple(sorted(set(changed_paths))), None


def _matcher_relevant_path(path: str) -> bool:
    normalized = path.strip("/")
    forms = {normalized}
    if normalized.startswith("app/"):
        forms.add(normalized[4:])
    else:
        forms.add(f"app/{normalized}")
    return any(
        form == prefix.strip("/") or form.startswith(prefix.strip("/"))
        for form in forms
        for prefix in MATCHER_SESSION_RELEVANT_PREFIXES
    )


def _matcher_relevant_changed_paths(paths: MatcherPaths) -> tuple[tuple[str, ...], str | None]:
    changed_paths, error = _git_status_paths(paths)
    if error is not None:
        return (), error
    return tuple(path for path in changed_paths if _matcher_relevant_path(path)), None


def _repo_rel(path: Path, *, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _matcher_changed_paths_since(paths: MatcherPaths, since: str | None) -> tuple[tuple[str, ...], str | None]:
    if since is None:
        return _matcher_relevant_changed_paths(paths)
    output, error = _git_output(paths, ["diff", "--name-only", since, "--"])
    if error is not None:
        return (), error
    changed = tuple(
        path.strip()
        for path in output.splitlines()
        if path.strip() and _matcher_relevant_path(path.strip())
    )
    return tuple(sorted(set(changed))), None


def _doctor_status(checks: Iterable[MatcherDoctorCheck]) -> Literal["ok", "needs_action", "blocking_error"]:
    statuses = [check.status for check in checks]
    if "blocking_error" in statuses:
        return "blocking_error"
    if "needs_action" in statuses:
        return "needs_action"
    return "ok"


def _doctor_next_action(checks: Iterable[MatcherDoctorCheck]) -> dict[str, str] | None:
    for check in checks:
        if check.status in {"blocking_error", "needs_action"} and check.next_command:
            return {"command": check.next_command, "reason": check.summary}
    return None


def _doctor_guided_corrections(checks: Iterable[MatcherDoctorCheck]) -> list[dict[str, str]]:
    by_id = {check.check_id: check for check in checks}
    corrections: list[dict[str, str]] = []
    if any(
        by_id.get(check_id) and by_id[check_id].status == "needs_action"
        for check_id in ("generated_contract_json", "generated_registry_coverage")
    ):
        corrections.append({
            "id": "generated_artifacts_stale",
            "summary": "Source TOML and generated matcher artifacts are out of sync.",
            "command": "./bin/dm matcher regen --what all",
        })
    line_refs = by_id.get("line_refs")
    if line_refs and line_refs.status in {"warning", "blocking_error"}:
        corrections.append({
            "id": "line_refs_need_refresh",
            "summary": line_refs.summary,
            "command": "./bin/dm matcher refresh-line-refs --fix",
        })
    writeability = by_id.get("writeability")
    if writeability and writeability.status == "blocking_error":
        corrections.append({
            "id": "writeability_or_appuser",
            "summary": "Current user cannot write one or more generated/baseline paths.",
            "command": "rerun as appuser or fix checkout/report-root permissions",
        })
    git_changes = by_id.get("git_changes")
    if git_changes and git_changes.status == "needs_action":
        corrections.append({
            "id": "matcher_changes_need_gate",
            "summary": "Matcher-relevant files changed; run preflight/gates before handoff.",
            "command": "./bin/dm matcher preflight",
        })
    return corrections


def _path_is_writable_for_current_user(path: Path) -> bool:
    target = path if path.exists() else path.parent
    try:
        return os.access(target, os.W_OK)
    except OSError:
        return False


def _doctor_git_check(paths: MatcherPaths, since: str | None) -> MatcherDoctorCheck:
    changed_paths, error = _matcher_changed_paths_since(paths, since)
    if error is not None:
        return MatcherDoctorCheck(
            "git_changes",
            "warning",
            f"Git change listing unavailable: {error}",
            {"error": error, "since": since},
        )
    if not changed_paths:
        return MatcherDoctorCheck(
            "git_changes",
            "ok",
            "No matcher-relevant git changes detected.",
            {"changed_paths": [], "since": since},
        )
    return MatcherDoctorCheck(
        "git_changes",
        "needs_action",
        f"{len(changed_paths)} matcher-relevant changed path(s).",
        {"changed_paths": list(changed_paths), "since": since},
        "./bin/dm matcher preflight",
    )


def _doctor_generated_contract_check(paths: MatcherPaths) -> MatcherDoctorCheck:
    results = check_generated_contract_json(tree_root=paths.repo_root, write=False)
    stale = [result for result in results if result.drifted]
    details = {
        "contracts": [
            {
                "contract": result.contract,
                "source_toml_path": result.source_toml_path,
                "target_json_path": result.target_json_path,
                "row_count": result.row_count,
                "semantic_equal": result.semantic_equal,
                "canonical_byte_equal": result.canonical_byte_equal,
                "raw_byte_equal": result.raw_byte_equal,
            }
            for result in results
        ],
    }
    if not stale:
        return MatcherDoctorCheck(
            "generated_contract_json",
            "ok",
            "Generated matcher contract JSON is current.",
            details,
        )
    return MatcherDoctorCheck(
        "generated_contract_json",
        "needs_action",
        f"{len(stale)} generated matcher contract JSON file(s) are stale.",
        details,
        "./bin/dm matcher regen --what all",
    )


def _doctor_generated_coverage_check(paths: MatcherPaths) -> MatcherDoctorCheck:
    files = generate_coverage_files(tree_root=paths.repo_root)
    stale = [item for item in files if item.changed]
    details = {
        "files": [
            {
                "path": _repo_rel(item.path, repo_root=paths.repo_root),
                "changed": item.changed,
                "generated_entry_count": item.generated_entry_count,
                "manual_block_count": item.manual_block_count,
            }
            for item in files
        ],
    }
    if not stale:
        return MatcherDoctorCheck(
            "generated_registry_coverage",
            "ok",
            "Generated matcher registry coverage is current.",
            details,
        )
    return MatcherDoctorCheck(
        "generated_registry_coverage",
        "needs_action",
        f"{len(stale)} generated matcher registry coverage file(s) are stale.",
        details,
        "./bin/dm matcher regen --what all",
    )


def _doctor_line_refs_check(paths: MatcherPaths) -> MatcherDoctorCheck:
    from support_checks.refresh_matcher_rule_inventory_line_refs import (
        refresh_inventory_line_refs_from_contract_source,
    )

    summary = refresh_inventory_line_refs_from_contract_source(
        tree_root=paths.repo_root,
        repo_root=paths.repo_root,
        write=False,
    )
    if summary["missing_anchor"] or summary["missing_path"]:
        return MatcherDoctorCheck(
            "line_refs",
            "blocking_error",
            (
                "Matcher inventory line refs have missing anchors or paths "
                f"({summary['missing_anchor']} missing anchors, {summary['missing_path']} missing paths)."
            ),
            summary,
            "./bin/dm matcher refresh-line-refs --dry-run",
        )
    if summary["updated"]:
        return MatcherDoctorCheck(
            "line_refs",
            "warning",
            (
                f"{summary['updated']} matcher inventory line-ref range(s) would move; "
                "anchors are still valid."
            ),
            summary,
        )
    return MatcherDoctorCheck(
        "line_refs",
        "ok",
        "Matcher inventory line refs are current.",
        summary,
    )


def _doctor_writeability_check(paths: MatcherPaths, report_root: Path | None) -> MatcherDoctorCheck:
    baseline_file = (
        paths.app_dir
        / "languages"
        / "sv"
        / "ingredient_matching"
        / "term_registry"
        / "baselines"
        / "verified_matcher_terms.json"
    )
    targets = {
        "fixture_json": paths.fixture_file,
        "inventory_json": paths.inventory_file,
        "fixture_toml": paths.fixture_source_file,
        "inventory_toml": paths.inventory_source_file,
        "registry_entries_dir": paths.registry_entries_dir,
        "baseline": baseline_file,
        "deep_sanity": paths.deep_sanity_file,
        "support_report_root": report_root or Path(os.environ.get("DEAL_MEALS_SUPPORT_REPORT_ROOT", "/tmp/deal-meals-support-checks-dm")),
    }
    checks = {
        label: {
            "path": _repo_rel(path, repo_root=paths.repo_root),
            "writable": _path_is_writable_for_current_user(path),
            "exists": path.exists(),
        }
        for label, path in targets.items()
    }
    blocked = [label for label, payload in checks.items() if not payload["writable"]]
    details = {
        "current_uid": os.geteuid() if hasattr(os, "geteuid") else None,
        "targets": checks,
    }
    if blocked:
        return MatcherDoctorCheck(
            "writeability",
            "blocking_error",
            "Current user cannot write required matcher generated/baseline paths: " + ", ".join(blocked),
            details,
            "run the matcher command as the checkout owner/appuser or fix file permissions",
        )
    return MatcherDoctorCheck(
        "writeability",
        "ok",
        "Current user can write matcher generated/baseline paths.",
        details,
    )


def _matcher_doctor_report(
    *,
    paths: MatcherPaths,
    since: str | None,
    report_root: Path | None,
) -> dict[str, Any]:
    checks: list[MatcherDoctorCheck] = []
    for builder in (
        lambda: _doctor_git_check(paths, since),
        lambda: _doctor_generated_contract_check(paths),
        lambda: _doctor_generated_coverage_check(paths),
        lambda: _doctor_line_refs_check(paths),
        lambda: _doctor_writeability_check(paths, report_root),
    ):
        try:
            checks.append(builder())
        except Exception as exc:  # noqa: BLE001 - doctor reports diagnostics rather than hiding later checks.
            checks.append(MatcherDoctorCheck(
                "doctor_internal_error",
                "blocking_error",
                f"Doctor check failed: {exc}",
                {"error": str(exc), "type": type(exc).__name__},
            ))
    status = _doctor_status(checks)
    return {
        "schema_version": 1,
        "status": status,
        "checks": [check.to_dict() for check in checks],
        "next_action": _doctor_next_action(checks),
        "guided_corrections": _doctor_guided_corrections(checks),
    }


def _format_matcher_doctor_text(report: Mapping[str, Any]) -> str:
    lines = ["matcher doctor", f"  status: {report['status']}"]
    for check in report["checks"]:
        lines.append(f"  {check['id']}: {check['status']} - {check['summary']}")
    next_action = report.get("next_action")
    if next_action:
        lines.extend([
            "next:",
            f"  {next_action['command']}",
            f"  reason: {next_action['reason']}",
        ])
    else:
        lines.extend(["next:", "  none"])
    corrections = report.get("guided_corrections") or []
    if corrections:
        lines.append("guided corrections:")
        for correction in corrections:
            lines.append(f"  - {correction['id']}: {correction['command']}")
            lines.append(f"    {correction['summary']}")
    return "\n".join(lines)


def _slug(value: str, *, fallback: str = "term") -> str:
    cleaned = value.strip().lower()
    cleaned = (
        cleaned.replace("å", "a")
        .replace("ä", "a")
        .replace("ö", "o")
        .replace("é", "e")
    )
    normalized = unicodedata.normalize("NFKD", cleaned)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
    return slug or fallback


def _split_csv_tokens(value: str) -> tuple[str, ...]:
    items: list[str] = []
    buffer: list[str] = []
    escaped = False
    brace_depth = 0
    bracket_depth = 0
    paren_depth = 0

    for char in value:
        if escaped:
            if char == ",":
                buffer.append(",")
            else:
                buffer.append("\\")
                buffer.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth = max(0, brace_depth - 1)
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth = max(0, bracket_depth - 1)
        elif char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth = max(0, paren_depth - 1)
        if char == "," and brace_depth == 0 and bracket_depth == 0 and paren_depth == 0:
            items.append("".join(buffer))
            buffer = []
            continue
        buffer.append(char)

    if escaped:
        buffer.append("\\")
    items.append("".join(buffer))
    return tuple(items)


def _split_csv(value: str, *, label: str, lowercase: bool = True) -> tuple[str, ...]:
    items = tuple(
        item.strip().lower() if lowercase else item.strip()
        for item in _split_csv_tokens(value)
        if item.strip()
    )
    if not items:
        raise typer.BadParameter(f"{label} must contain at least one value")
    duplicates = sorted({item for item in items if items.count(item) > 1})
    if duplicates:
        raise typer.BadParameter(f"{label} contains duplicates: {', '.join(duplicates)}")
    return items


def _split_optional_csv(value: str | None, *, label: str) -> tuple[str, ...]:
    return _split_csv(value, label=label) if value else ()


def _titleish(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split())


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _generated_sanity_header(policy_ref: str, command_name: str) -> list[str]:
    return [
        f"# {policy_ref}: generated by dm matcher add {command_name}",
        f"# sanity-id: {policy_ref}",
    ]


def _toml_array(values: tuple[str, ...] | list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _deep_sanity_offer_dict(name: str, category: str) -> str:
    fields = [f'"name": {_toml_string(name)}']
    if category:
        fields.append(f'"category": {_toml_string(category)}')
    return "{" + ", ".join(fields) + "}"


def _deep_sanity_match_assertion(
    *,
    description: str,
    offer_name: str,
    ingredient: str,
    offer_category: str,
    expected_canonical: str | None,
    mode: Literal["fast-match", "backend-match"],
    recipe_name: str = "Sanity Recipe",
) -> list[str]:
    if mode == "fast-match":
        expected = "None" if expected_canonical is None else _toml_string(expected_canonical)
        return [
            f"test({_toml_string(description)},",
            f"     match({_toml_string(offer_name)}, {_toml_string(ingredient)}, {_toml_string(offer_category)}), {expected})",
        ]
    expected_count = 0 if expected_canonical is None else 1
    return [
        f"test({_toml_string(description + ' (backend)')},",
        f"     recipe_match_num_named({_toml_string(recipe_name)}, [{_toml_string(ingredient)}], "
        f"{_deep_sanity_offer_dict(offer_name, offer_category)}), {expected_count})",
    ]


def _runtime_observed_expected_canonical(
    *,
    paths: MatcherPaths,
    requested_expected: str | None,
    offer_name: str,
    ingredient: str,
    offer_category: str,
    sanity_mode: Literal["fast-match", "backend-match"],
    dry_run: bool,
) -> str | None:
    if dry_run or paths.app_dir != APP_DIR or sanity_mode != "fast-match" or requested_expected is None:
        return requested_expected
    try:
        payload = _compare_matcher_paths(
            offer=offer_name,
            ingredient=ingredient,
            offer_category=offer_category,
            brand="",
            weight_grams=None,
            recipe_name="DM Matcher Generated Sanity",
        )
    except Exception as exc:  # noqa: BLE001 - generated canary should not hide the actual add error path.
        typer.secho(
            f"WARNING: could not observe generated sanity runtime result: {exc}",
            fg=typer.colors.YELLOW,
            err=True,
        )
        return requested_expected
    actual = payload["fast_keyword"] if payload["fast_matched"] else None
    if actual and actual != requested_expected:
        typer.secho(
            f"INFO: generated sanity expected observed runtime canonical {actual!r} "
            f"instead of requested {requested_expected!r}.",
            fg=typer.colors.CYAN,
            err=True,
        )
    return actual or requested_expected


def _print_generated_sanity_probe(paths: MatcherPaths, policy_ref: str) -> None:
    if paths.app_dir != APP_DIR:
        return
    try:
        rows = [
            _reconcile_deep_sanity_case(case)
            for case in _filter_sanity_reconcile_cases(
                _deep_sanity_reconcile_cases(paths),
                selector=policy_ref,
                command_name=None,
                all_generated=False,
            )
        ]
    except Exception as exc:  # noqa: BLE001 - probe output is advisory; gates remain authoritative.
        typer.secho(f"WARNING: sanity probe skipped: {exc}", fg=typer.colors.YELLOW, err=True)
        return
    if not rows:
        return
    typer.echo("Sanity probe:")
    for row in rows:
        status = "OK" if row.get("matches_expected") is True else (
            "DRIFT" if row.get("matches_expected") is False else "SKIP"
        )
        actual = row.get("actual_literal") or row.get("classification") or "unknown"
        typer.echo(f"  {status}: {row.get('description')} expected {row.get('expected')} actual {actual}")


def _source_spec(paths: MatcherPaths, contract: str):
    return contract_spec_by_name(contract, tree_root=paths.repo_root)


def _append_contract_source_items(
    *,
    paths: MatcherPaths,
    contract: str,
    items: tuple[dict, ...],
    dry_run: bool,
) -> None:
    if dry_run:
        return
    spec = _source_spec(paths, contract)
    payload = load_contract_source(spec)
    payload.extend(items)
    write_contract_source(spec, payload)


def _append_text_block(path: Path, block: str, *, dry_run: bool, trim_existing: bool = False) -> None:
    if dry_run:
        return
    existing_text = path.read_text(encoding="utf-8")
    if path.name == DEFAULT_DEEP_SANITY_FILE.name and DEEP_SANITY_FINAL_SUMMARY_MARKER in existing_text:
        marker_index = existing_text.index(DEEP_SANITY_FINAL_SUMMARY_MARKER)
        summary_start = existing_text.rfind("\n", 0, marker_index) + 1
        prefix = existing_text[:summary_start].rstrip()
        suffix = existing_text[summary_start:].lstrip("\n")
        path.write_text(f"{prefix}\n{block.strip()}\n\n{suffix}", encoding="utf-8")
        return
    if trim_existing:
        path.write_text(existing_text.rstrip() + "\n" + block, encoding="utf-8")
        return
    separator = "" if existing_text.endswith("\n\n") else "\n"
    path.write_text(existing_text + separator + block, encoding="utf-8")


def _existing_entry_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(re.findall(r'^entry_id = "([^"]+)"', path.read_text(encoding="utf-8"), flags=re.MULTILINE))


def _registry_entry_file(paths: MatcherPaths, file_stem: str) -> Path:
    return paths.registry_entries_dir / f"{file_stem}.toml"


def _entry_id_for_surface(
    *,
    existing_ids: set[str],
    surface: SimpleTomlSurface,
    canonical: str,
    variants: tuple[str, ...],
) -> str:
    canonical_slug = _slug(canonical)
    short_name = surface.file_stem if surface.entry_type == "family" else _slug(variants[0])
    base = f"sv-se.{surface.entry_type}.{canonical_slug}.{short_name}"
    if base not in existing_ids:
        return base
    suffix = 2
    while f"{base}_{suffix}" in existing_ids:
        suffix += 1
    return f"{base}_{suffix}"


def _coverage_rows_from_payload(payload: dict, *, path: Path) -> list[dict[str, str]]:
    rows = payload.get("coverage") or payload.get("legacy_coverage")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    source_family = path.stem
    spec = SIMPLE_TOML_SURFACES.get(source_family.replace("_", "-"))
    if spec is None:
        return []
    canonical = str(payload.get("canonical") or "").strip()
    variants = tuple(str(value) for value in payload.get("variants") or [] if str(value).strip())
    if not canonical or not variants:
        return []
    return [
        {
            "source_family": source_family,
            "canonical": canonical,
            "variant": variant,
            "layer_role": spec.layer_role,
        }
        for variant in variants
    ]


def _existing_coverage_keys(paths: MatcherPaths) -> set[tuple[str, str, str, str]]:
    keys: set[tuple[str, str, str, str]] = set()
    for path in sorted(paths.registry_entries_dir.glob("*.toml")):
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        entries = payload.get("entries")
        raw_entries = entries if isinstance(entries, list) else [payload]
        for entry in raw_entries:
            if not isinstance(entry, dict):
                continue
            for row in _coverage_rows_from_payload(entry, path=path):
                source_family = str(row.get("source_family") or row.get("source_type") or "")
                canonical = str(row.get("canonical") or entry.get("canonical") or "")
                variant = str(row.get("variant") or row.get("variant_text") or "")
                layer_role = str(row.get("layer_role") or row.get("variant_role") or "")
                if source_family and canonical and variant and layer_role:
                    keys.add((source_family, canonical.lower(), variant.lower(), layer_role))
    return keys


def _ensure_can_add_surface_mapping(
    *,
    paths: MatcherPaths,
    surface: SimpleTomlSurface,
    canonical_targets: tuple[str, ...],
    variants: tuple[str, ...],
) -> None:
    existing_keys = _existing_coverage_keys(paths)
    duplicates = sorted(
        f"{variant} -> {target}"
        for target in canonical_targets
        for variant in variants
        if (surface.file_stem, target.lower(), variant.lower(), surface.layer_role) in existing_keys
    )
    if duplicates:
        raise typer.BadParameter(
            f"{surface.file_stem} coverage already exists: {', '.join(duplicates)}"
        )


def _ensure_fixture_refs_exist(paths: MatcherPaths, fixture_refs: tuple[str, ...]) -> None:
    fixtures = load_contract_source(_source_spec(paths, "matcher_regression_cases"))
    existing_fixture_ids = {str(item.get("id") or "") for item in fixtures if isinstance(item, dict)}
    missing = sorted(ref for ref in fixture_refs if ref not in existing_fixture_ids)
    if missing:
        raise typer.BadParameter(f"fixture_ref does not exist: {', '.join(missing)}")


def _split_fixture_ids(value: str) -> tuple[str, ...]:
    return _split_csv(value, label="fixture id", lowercase=False)


def _remove_fixture_rows(
    *,
    paths: MatcherPaths,
    fixture_ids: tuple[str, ...],
) -> tuple[list[dict], tuple[str, ...]]:
    fixture_id_set = set(fixture_ids)
    fixtures = load_contract_source(_source_spec(paths, "matcher_regression_cases"))
    kept: list[dict] = []
    removed: list[str] = []
    for row in fixtures:
        row_id = str(row.get("id") or "")
        if row_id in fixture_id_set:
            removed.append(row_id)
            continue
        kept.append(row)
    missing = tuple(fixture_id for fixture_id in fixture_ids if fixture_id not in set(removed))
    if missing:
        raise typer.BadParameter(f"fixture id not found: {', '.join(missing)}")
    return kept, tuple(removed)


def _load_fixture_row(paths: MatcherPaths, fixture_id: str) -> dict[str, Any]:
    fixtures = load_contract_source(_source_spec(paths, "matcher_regression_cases"))
    matches = [row for row in fixtures if str(row.get("id") or "") == fixture_id]
    if not matches:
        raise typer.BadParameter(f"fixture id not found: {fixture_id}")
    if len(matches) > 1:
        raise typer.BadParameter(f"fixture id is not unique: {fixture_id}")
    return dict(matches[0])


def _make_fixture_negative_rows(
    *,
    paths: MatcherPaths,
    fixture_id: str,
    policy_ref: str | None,
    source_ref: str | None,
) -> tuple[list[dict], dict[str, Any]]:
    fixtures = load_contract_source(_source_spec(paths, "matcher_regression_cases"))
    matches = [index for index, row in enumerate(fixtures) if str(row.get("id") or "") == fixture_id]
    if not matches:
        raise typer.BadParameter(f"fixture id not found: {fixture_id}")
    if len(matches) > 1:
        raise typer.BadParameter(f"fixture id is not unique: {fixture_id}")

    index = matches[0]
    original = fixtures[index]
    row = dict(original)
    previous_expected = row.get("expected")
    if previous_expected not in (0, 1):
        raise typer.BadParameter(
            f"fixture {fixture_id} has unsupported expected value {previous_expected!r}; "
            "only positive/negative fixtures can be converted"
        )

    expected_matches = row.pop("expected_matches", None)
    removed_expected_matches = len(expected_matches) if isinstance(expected_matches, list) else 0
    previous_policy_ref = str(row.get("policy_ref") or "")
    previous_source_ref = str(row.get("source_ref") or "")

    row["expected"] = 0
    if policy_ref is not None:
        row["policy_ref"] = policy_ref
    if source_ref is not None:
        row["source_ref"] = source_ref

    fixtures[index] = row
    return fixtures, {
        "fixture_id": fixture_id,
        "changed": row != original,
        "previous_expected": previous_expected,
        "removed_expected_matches": removed_expected_matches,
        "previous_policy_ref": previous_policy_ref,
        "new_policy_ref": str(row.get("policy_ref") or ""),
        "previous_source_ref": previous_source_ref,
        "new_source_ref": str(row.get("source_ref") or ""),
    }


def _fixture_offer_payload(row: Mapping[str, Any]) -> Mapping[str, Any]:
    offer = row.get("offer") or {}
    if not isinstance(offer, Mapping):
        raise typer.BadParameter(f"fixture {row.get('id', '<unknown>')} offer must be an object")
    return offer


def _fixture_ingredients(row: Mapping[str, Any]) -> tuple[str, ...]:
    ingredients = row.get("ingredients") or []
    if not isinstance(ingredients, list) or not ingredients:
        raise typer.BadParameter(f"fixture {row.get('id', '<unknown>')} requires ingredients")
    return tuple(str(ingredient) for ingredient in ingredients)


def _fixture_offer_weight_grams(offer: Mapping[str, Any]) -> float | None:
    weight = offer.get("weight_grams")
    if weight is None:
        return None
    if isinstance(weight, (int, float)):
        return float(weight)
    try:
        return float(str(weight))
    except ValueError:
        return None


def _infer_positive_expected_match_from_current_match(row: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        from support_checks.matcher_layer_diagnostics import DiagnosticCase, diagnose_case
    except ModuleNotFoundError as exc:
        raise typer.BadParameter(
            "cannot infer current match because support-check dependencies are unavailable; "
            "run inside the dev container or pass --canonical/--ingredient-index explicitly"
        ) from exc

    fixture_id = str(row.get("id") or "<unknown>")
    offer = _fixture_offer_payload(row)
    ingredients = _fixture_ingredients(row)
    offer_name = str(offer.get("name") or "")
    offer_category = str(offer.get("category") or "")
    offer_brand = str(offer.get("brand") or "")
    weight_grams = _fixture_offer_weight_grams(offer)

    diagnostic = diagnose_case(
        DiagnosticCase(
            case_id=fixture_id,
            recipe_name=str(row.get("recipe_name") or "Sanity Recipe"),
            ingredients=ingredients,
            offer_name=offer_name,
            offer_category=offer_category,
            offer_brand=offer_brand,
            expected=1,
        ),
        include_cache_freshness=False,
    )

    failures: list[str] = []
    if diagnostic.get("actual") != 1:
        failures.append(f"actual={diagnostic.get('actual')} (expected one current match)")
    if diagnostic.get("diagnosis_class") != "pass":
        failures.append(f"diagnosis_class={diagnostic.get('diagnosis_class')}")

    materialized_matches = diagnostic.get("materialization", {}).get("matched_offers", [])
    if len(materialized_matches) != 1:
        failures.append(f"materialized_matches={len(materialized_matches)} (expected exactly one)")

    match = materialized_matches[0] if len(materialized_matches) == 1 else {}
    canonical = str(match.get("matched_keyword") or "")
    ingredient_index = match.get("matched_ingredient_index")
    if not canonical:
        failures.append("materialized match has no matched_keyword")
    if ingredient_index is None:
        failures.append("materialized match has no matched_ingredient_index")
    try:
        ingredient_index_int = int(ingredient_index)
    except (TypeError, ValueError):
        failures.append(f"invalid matched_ingredient_index={ingredient_index!r}")
        ingredient_index_int = -1
    if ingredient_index_int < 0 or ingredient_index_int >= len(ingredients):
        failures.append(f"matched_ingredient_index={ingredient_index!r} is outside fixture ingredients")

    fast_match = diagnostic.get("fast_match", {})
    if not fast_match.get("matched"):
        failures.append("fast_match did not match")
    if canonical and fast_match.get("matched_keyword") != canonical:
        failures.append(
            f"fast_match keyword {fast_match.get('matched_keyword')!r} != materialized keyword {canonical!r}"
        )
    if ingredient_index_int >= 0 and fast_match.get("matched_ingredient_index") != ingredient_index_int:
        failures.append(
            "fast_match ingredient_index "
            f"{fast_match.get('matched_ingredient_index')!r} != {ingredient_index_int}"
        )

    backend_validation = diagnostic.get("backend_validation", {})
    if not backend_validation.get("accepted"):
        failures.append("backend validation did not accept the match")
    if canonical and backend_validation.get("matched_keyword") != canonical:
        failures.append(
            "backend validation keyword "
            f"{backend_validation.get('matched_keyword')!r} != materialized keyword {canonical!r}"
        )
    if ingredient_index_int >= 0 and backend_validation.get("matched_ingredient_index") != ingredient_index_int:
        failures.append(
            "backend validation ingredient_index "
            f"{backend_validation.get('matched_ingredient_index')!r} != {ingredient_index_int}"
        )

    signal_provenance = diagnostic.get("signal_provenance", {})
    duplicate_count = int(signal_provenance.get("duplicate_signal_source", {}).get("count") or 0)
    ambiguous_count = int(signal_provenance.get("ambiguous_canonical", {}).get("count") or 0)
    if duplicate_count:
        failures.append(f"duplicate_signal_source={duplicate_count}")
    if ambiguous_count:
        failures.append(f"ambiguous_canonical={ambiguous_count}")

    if ingredient_index_int >= 0 and canonical:
        path_compare = _compare_matcher_paths(
            offer=offer_name,
            ingredient=ingredients[ingredient_index_int],
            offer_category=offer_category,
            brand=offer_brand,
            weight_grams=weight_grams,
            recipe_name=str(row.get("recipe_name") or "DM Matcher Fixture Make Positive"),
        )
        if path_compare["live_fast_diverged"] or path_compare["fast_backend_diverged"]:
            failures.append("single-ingredient compare-paths diverged")
        if path_compare["legacy_live_keyword"] != canonical:
            failures.append(
                f"legacy live keyword {path_compare['legacy_live_keyword']!r} != {canonical!r}"
            )
        if path_compare["fast_keyword"] != canonical:
            failures.append(f"canonical fast keyword {path_compare['fast_keyword']!r} != {canonical!r}")
        if not path_compare["backend_matched"] or int(path_compare["backend_num_matches"]) != 1:
            failures.append(
                "single-ingredient backend produced "
                f"{path_compare['backend_num_matches']} match(es)"
            )

    if failures:
        raise typer.BadParameter(
            "cannot infer positive expected_matches from current matcher for "
            f"{fixture_id}: " + "; ".join(failures)
        )

    expected_match = {
        "ingredient_index": ingredient_index_int,
        "canonical": canonical,
        "must_match_keyword": canonical,
    }
    return expected_match, {
        "canonical": canonical,
        "ingredient_index": ingredient_index_int,
        "must_match_keyword": canonical,
        "diagnosis_class": diagnostic.get("diagnosis_class"),
        "paths": "live/fast/backend/materialized agree",
    }


def _make_fixture_positive_rows(
    *,
    paths: MatcherPaths,
    fixture_id: str,
    expected_match: Mapping[str, Any],
    policy_ref: str | None,
    source_ref: str | None,
    inference: Mapping[str, Any] | None,
) -> tuple[list[dict], dict[str, Any]]:
    fixtures = load_contract_source(_source_spec(paths, "matcher_regression_cases"))
    matches = [index for index, row in enumerate(fixtures) if str(row.get("id") or "") == fixture_id]
    if not matches:
        raise typer.BadParameter(f"fixture id not found: {fixture_id}")
    if len(matches) > 1:
        raise typer.BadParameter(f"fixture id is not unique: {fixture_id}")

    index = matches[0]
    original = fixtures[index]
    row = dict(original)
    previous_expected = row.get("expected")
    if previous_expected not in (0, 1):
        raise typer.BadParameter(
            f"fixture {fixture_id} has unsupported expected value {previous_expected!r}; "
            "only positive/negative fixtures can be converted"
        )

    previous_expected_matches = row.get("expected_matches")
    row["expected"] = 1
    row["expected_matches"] = [dict(expected_match)]
    previous_policy_ref = str(row.get("policy_ref") or "")
    previous_source_ref = str(row.get("source_ref") or "")
    if policy_ref is not None:
        row["policy_ref"] = policy_ref
    if source_ref is not None:
        row["source_ref"] = source_ref

    fixtures[index] = row
    return fixtures, {
        "fixture_id": fixture_id,
        "changed": row != original,
        "previous_expected": previous_expected,
        "previous_expected_matches": len(previous_expected_matches)
        if isinstance(previous_expected_matches, list)
        else 0,
        "expected_match": dict(expected_match),
        "previous_policy_ref": previous_policy_ref,
        "new_policy_ref": str(row.get("policy_ref") or ""),
        "previous_source_ref": previous_source_ref,
        "new_source_ref": str(row.get("source_ref") or ""),
        "inference": dict(inference or {}),
    }


def _remove_fixture_refs_from_contract_rows(
    rows: list[dict],
    *,
    fixture_ids: tuple[str, ...],
    id_field: str,
    drop_empty_rows: bool,
    row_label: str,
) -> tuple[list[dict], tuple[str, ...], tuple[str, ...]]:
    fixture_id_set = set(fixture_ids)
    changed: list[str] = []
    dropped: list[str] = []
    blocked_empty: list[str] = []
    updated_rows: list[dict] = []

    for row in rows:
        refs = row.get("fixture_refs")
        if not isinstance(refs, list) or not any(ref in fixture_id_set for ref in refs):
            updated_rows.append(row)
            continue

        row_id = str(row.get(id_field) or row.get("id") or "<unknown>")
        new_refs = [ref for ref in refs if ref not in fixture_id_set]
        if not new_refs:
            if drop_empty_rows:
                dropped.append(row_id)
                continue
            blocked_empty.append(row_id)
            updated_rows.append(row)
            continue

        row = dict(row)
        row["fixture_refs"] = new_refs
        changed.append(row_id)
        updated_rows.append(row)

    if blocked_empty:
        raise typer.BadParameter(
            f"removing fixture refs would leave {row_label} rows without fixture_refs: "
            f"{', '.join(blocked_empty)}. Re-run with --drop-empty-{row_label} if those rows "
            "should be removed too."
        )
    return updated_rows, tuple(changed), tuple(dropped)


def _fixture_ref_line_update(
    line: str,
    *,
    fixture_ids: set[str],
) -> tuple[str, bool, bool]:
    match = re.match(r"^(\s*)fixture_refs\s*=\s*(\[.*\])\s*$", line)
    if not match:
        return line, False, False
    try:
        payload = tomllib.loads(f"fixture_refs = {match.group(2)}")
    except tomllib.TOMLDecodeError as exc:
        raise typer.BadParameter(f"invalid fixture_refs line in registry entry: {line!r}: {exc}") from exc
    refs = payload.get("fixture_refs")
    if not isinstance(refs, list) or not any(ref in fixture_ids for ref in refs):
        return line, False, False
    new_refs = [str(ref) for ref in refs if ref not in fixture_ids]
    if not new_refs:
        return line, True, True
    return f"{match.group(1)}fixture_refs = {_toml_array(new_refs)}", True, False


def _registry_block_without_fixture_refs(
    record: RegistryEntryRecord,
    *,
    fixture_ids: set[str],
) -> tuple[str, bool, bool]:
    changed = False
    emptied = False
    lines: list[str] = []
    for line in record.block.splitlines():
        new_line, line_changed, line_emptied = _fixture_ref_line_update(line, fixture_ids=fixture_ids)
        changed = changed or line_changed
        emptied = emptied or line_emptied
        lines.append(new_line)
    if not changed:
        return record.block, False, False
    suffix = "\n" if record.block.endswith("\n") else ""
    return "\n".join(lines) + suffix, True, emptied


def _plan_registry_fixture_ref_removal(
    *,
    paths: MatcherPaths,
    fixture_ids: tuple[str, ...],
    drop_empty_registry_entries: bool,
) -> tuple[RegistryFixtureRefRemovalPlan, ...]:
    fixture_id_set = set(fixture_ids)
    plans: list[RegistryFixtureRefRemovalPlan] = []
    blocked_empty: list[str] = []

    for path in sorted(paths.registry_entries_dir.glob("*.toml")):
        text = path.read_text(encoding="utf-8")
        records = _registry_entry_records(path.stem.replace("_", "-"), path)
        replacements: list[tuple[int, int, str, str, bool]] = []
        for record in records:
            new_block, changed, emptied = _registry_block_without_fixture_refs(
                record,
                fixture_ids=fixture_id_set,
            )
            if not changed:
                continue
            if emptied and not drop_empty_registry_entries:
                blocked_empty.append(record.entry_id)
                continue
            replacements.append((
                record.start,
                record.end,
                "" if emptied else new_block,
                record.entry_id,
                emptied,
            ))

        if not replacements:
            continue

        new_text = text
        changed_entries: list[str] = []
        dropped_entries: list[str] = []
        for start, end, replacement, entry_id, dropped in sorted(replacements, reverse=True):
            new_text = new_text[:start] + replacement + new_text[end:]
            (dropped_entries if dropped else changed_entries).append(entry_id)
        plans.append(RegistryFixtureRefRemovalPlan(
            path=path,
            new_text=new_text,
            changed_entries=tuple(reversed(changed_entries)),
            dropped_entries=tuple(reversed(dropped_entries)),
        ))

    if blocked_empty:
        raise typer.BadParameter(
            "removing fixture refs would leave registry entries without fixture_refs: "
            f"{', '.join(blocked_empty)}. Re-run with --drop-empty-registry-entries if those "
            "entries should be removed too."
        )
    return tuple(plans)


def _write_registry_fixture_ref_removal_plans(plans: tuple[RegistryFixtureRefRemovalPlan, ...]) -> None:
    for plan in plans:
        plan.path.write_text(plan.new_text, encoding="utf-8")


def _print_fixture_remove_summary(
    *,
    fixture_ids: tuple[str, ...],
    inventory_changed: tuple[str, ...],
    inventory_dropped: tuple[str, ...],
    registry_plans: tuple[RegistryFixtureRefRemovalPlan, ...],
    dry_run: bool,
) -> None:
    prefix = "Would remove" if dry_run else "Removed"
    typer.echo(f"{prefix} fixture(s): {', '.join(fixture_ids)}")
    if inventory_changed:
        typer.echo(f"  inventory refs updated: {', '.join(inventory_changed)}")
    if inventory_dropped:
        typer.echo(f"  inventory rows dropped: {', '.join(inventory_dropped)}")
    for plan in registry_plans:
        rel_path = plan.path
        if plan.changed_entries:
            typer.echo(f"  registry refs updated in {rel_path}: {', '.join(plan.changed_entries)}")
        if plan.dropped_entries:
            typer.echo(f"  registry entries dropped from {rel_path}: {', '.join(plan.dropped_entries)}")


def _simple_surface_block(
    *,
    surface: SimpleTomlSurface,
    entry_id: str,
    canonical: str,
    variants: tuple[str, ...],
    term_values: tuple[str, ...],
    source_ref: str,
    sanity_ingredient: str,
    sanity_offer: str,
    offer_category: str,
) -> str:
    lines = [
        "[[entries]]",
        f"entry_id = {_toml_string(entry_id)}",
        'language = "sv"',
        'market = "SE"',
        f"canonical = {_toml_string(canonical)}",
        'status = "active"',
        f"variants = {_toml_array(variants)}",
        f"{surface.term_field} = {_toml_array(term_values)}",
        f"source_refs = {_toml_array((source_ref,))}",
        f"layer_policy = {_toml_array((surface.layer_policy,))}",
        f"notes = {_toml_string(surface.notes)}",
        "",
    ]
    for target in term_values:
        for variant in variants:
            lines.extend([
                "[[entries.coverage]]",
                f"source_family = {_toml_string(surface.file_stem)}",
                f"canonical = {_toml_string(target)}",
                f"variant = {_toml_string(variant)}",
                f"layer_role = {_toml_string(surface.layer_role)}",
                "",
            ])
    lines.extend([
        "[[entries.positive_examples]]",
        f"ingredient = {_toml_string(sanity_ingredient)}",
        f"offer_name = {_toml_string(sanity_offer)}",
    ])
    if offer_category:
        lines.append(f"offer_category = {_toml_string(offer_category)}")
    lines.extend([
        "expected = 1",
        "",
    ])
    return "\n".join(lines)


def _append_simple_surface_entry(
    *,
    paths: MatcherPaths,
    surface: SimpleTomlSurface,
    canonical: str,
    variants: tuple[str, ...],
    term_values: tuple[str, ...],
    source_ref: str,
    sanity_ingredient: str,
    sanity_offer: str,
    offer_category: str,
    dry_run: bool,
) -> tuple[str, int, str]:
    target_file = _registry_entry_file(paths, surface.file_stem)
    existing_ids = _existing_entry_ids(target_file)
    entry_id = _entry_id_for_surface(
        existing_ids=existing_ids,
        surface=surface,
        canonical=canonical,
        variants=variants,
    )
    block = _simple_surface_block(
        surface=surface,
        entry_id=entry_id,
        canonical=canonical,
        variants=variants,
        term_values=term_values,
        source_ref=source_ref,
        sanity_ingredient=sanity_ingredient,
        sanity_offer=sanity_offer,
        offer_category=offer_category,
    )
    existing_text = target_file.read_text(encoding="utf-8")
    start_line = len(existing_text.splitlines()) + 1
    _append_text_block(target_file, block, dry_run=dry_run)
    return entry_id, start_line, block


def _append_simple_surface_deep_sanity_stub(
    *,
    paths: MatcherPaths,
    surface: SimpleTomlSurface,
    canonical: str,
    sanity_ingredient: str,
    sanity_offer: str,
    offer_category: str,
    negative_sanity_ingredient: str | None,
    negative_sanity_offer: str | None,
    negative_offer_category: str | None,
    policy_ref: str,
    sanity_mode: Literal["fast-match", "backend-match"],
    dry_run: bool,
) -> str:
    expected_canonical = _runtime_observed_expected_canonical(
        paths=paths,
        requested_expected=canonical,
        offer_name=sanity_offer,
        ingredient=sanity_ingredient,
        offer_category=offer_category,
        sanity_mode=sanity_mode,
        dry_run=dry_run,
    )
    lines = [
        "",
        *_generated_sanity_header(policy_ref, surface.command),
        *_deep_sanity_match_assertion(
            description=surface.command + " " + sanity_offer + " matches " + canonical,
            offer_name=sanity_offer,
            ingredient=sanity_ingredient,
            offer_category=offer_category,
            expected_canonical=expected_canonical,
            mode=sanity_mode,
        ),
    ]
    if negative_sanity_ingredient is not None and negative_sanity_offer is not None:
        lines.extend(_deep_sanity_match_assertion(
            description=surface.command + " " + negative_sanity_offer + " does not match " + negative_sanity_ingredient,
            offer_name=negative_sanity_offer,
            ingredient=negative_sanity_ingredient,
            offer_category=negative_offer_category if negative_offer_category is not None else offer_category,
            expected_canonical=None,
            mode=sanity_mode,
        ))
    block = "\n".join(lines) + "\n"
    _append_text_block(paths.deep_sanity_file, block, dry_run=dry_run, trim_existing=True)
    return block


def _default_sanity_text(
    mode: Literal["canonical", "variant"],
    *,
    canonical: str,
    variants: tuple[str, ...],
) -> str:
    value = canonical if mode == "canonical" else variants[0]
    return _titleish(value)


def _add_simple_toml_surface(
    *,
    surface: SimpleTomlSurface,
    canonical: str,
    variants_csv: str,
    term_values_csv: str | None,
    sanity_ingredient: str | None,
    sanity_offer: str | None,
    offer_category: str,
    negative_sanity_ingredient: str | None = None,
    negative_sanity_offer: str | None = None,
    negative_offer_category: str | None = None,
    sanity_mode: Literal["fast-match", "backend-match"],
    policy_ref: str | None,
    source_ref: str | None,
    tree_root: Path | None,
    run_gates: bool,
    report_root: Path | None,
    dry_run: bool,
) -> None:
    variants = _split_csv(variants_csv, label="--variants")
    canonical = canonical.strip().lower()
    if not canonical:
        raise typer.BadParameter("canonical must not be empty")
    if any(variant == canonical and surface.command in {"ingredient-parent", "offer-extra-keyword"} for variant in variants):
        raise typer.BadParameter("--variants must differ from canonical for alias surfaces")
    term_values = (
        _split_csv(term_values_csv, label="--terms")
        if term_values_csv
        else (canonical,)
    )
    paths = _paths(tree_root)
    canonical_slug = _slug(canonical)
    variant_slug = _slug(variants[0])
    policy_ref = policy_ref or f"{surface.file_stem}_{canonical_slug}_{variant_slug}"
    source_ref = source_ref or f"manual:{policy_ref}"
    sanity_ingredient = (
        sanity_ingredient.strip()
        if sanity_ingredient is not None
        else _default_sanity_text(surface.default_sanity_ingredient, canonical=canonical, variants=variants)
    )
    sanity_offer = (
        sanity_offer.strip()
        if sanity_offer is not None
        else _default_sanity_text(surface.default_sanity_offer, canonical=canonical, variants=variants)
    )
    if not sanity_ingredient:
        raise typer.BadParameter("--sanity-ingredient must not be empty")
    if not sanity_offer:
        raise typer.BadParameter("--sanity-offer must not be empty")
    has_negative_ingredient = negative_sanity_ingredient is not None
    has_negative_offer = negative_sanity_offer is not None
    if has_negative_ingredient != has_negative_offer:
        raise typer.BadParameter("--negative-ingredient and --negative-offer must be supplied together")
    if has_negative_ingredient and has_negative_offer:
        negative_sanity_ingredient = negative_sanity_ingredient.strip()
        negative_sanity_offer = negative_sanity_offer.strip()
        if not negative_sanity_ingredient:
            raise typer.BadParameter("--negative-ingredient must not be empty")
        if not negative_sanity_offer:
            raise typer.BadParameter("--negative-offer must not be empty")
        if negative_offer_category is not None:
            negative_offer_category = negative_offer_category.strip()
    elif surface.command == "parent-match-only":
        typer.secho(
            "WARNING: parent-match-only is route-only; it does not prove strict exclusions. "
            "Pass --negative-offer and --negative-ingredient for sibling/strictness proof.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root light gates are not available; use --no-run-gates")

    _ensure_can_add_surface_mapping(
        paths=paths,
        surface=surface,
        canonical_targets=term_values,
        variants=variants,
    )
    if surface.command == "ingredient-parent":
        _emit_runtime_authoring_warnings(
            _ingredient_parent_pnb_mirror_warnings(
                paths=paths,
                canonical_targets=term_values,
                variants=variants,
            )
        )
    entry_id, _entry_line, toml_preview = _append_simple_surface_entry(
        paths=paths,
        surface=surface,
        canonical=canonical,
        variants=variants,
        term_values=term_values,
        source_ref=source_ref,
        sanity_ingredient=sanity_ingredient,
        sanity_offer=sanity_offer,
        offer_category=offer_category,
        dry_run=dry_run,
    )
    sanity_preview = _append_simple_surface_deep_sanity_stub(
        paths=paths,
        surface=surface,
        canonical=canonical,
        sanity_ingredient=sanity_ingredient,
        sanity_offer=sanity_offer,
        offer_category=offer_category,
        negative_sanity_ingredient=negative_sanity_ingredient,
        negative_sanity_offer=negative_sanity_offer,
        negative_offer_category=negative_offer_category,
        policy_ref=policy_ref,
        sanity_mode=sanity_mode,
        dry_run=dry_run,
    )
    change = MatcherChangePlan(
        command=surface.command,
        policy_ref=policy_ref,
        entry_ids=(entry_id,),
        fixture_ids=(),
        inventory_id=None,
        toml_preview=toml_preview,
        sanity_preview=sanity_preview,
        runtime_delta_filename=f"{surface.file_stem}.toml",
    )
    if dry_run:
        _print_dry_run_preview(change)
        return

    typer.echo(f"Generated {surface.file_stem} rule: {change.policy_ref}")
    typer.echo(f"  entry: {entry_id}")
    _print_generated_sanity_probe(paths, change.policy_ref)
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        typer.echo(
            "Next: run `./bin/dm matcher batch finalize --track B`, or run "
            "`./bin/dm matcher regen` + `./bin/dm matcher promote` before registry gates."
        )
        return
    gate_status = _run_keyword_synonym_light_gates(paths=paths, report_root=report_root)
    raise typer.Exit(gate_status)


def _no_match_policy_block(
    *,
    entry_id: str,
    policy_id: str,
    rule_schema_version: int = 1,
    rule_version: int = 1,
    canonical: str,
    ingredient_patterns: tuple[str, ...],
    blocked_offer_keywords: tuple[str, ...],
    blocked_offer_patterns: tuple[str, ...],
    allowed_specifics: tuple[str, ...],
    reason: str,
    policy_ref: str,
    fixture_refs: tuple[str, ...],
    supersedes: tuple[str, ...],
    negative_ingredient: str,
    negative_offer: str,
    offer_category: str,
) -> str:
    guard_variants = tuple(
        f"{canonical} ! {guard}"
        for guard in (*blocked_offer_keywords, *blocked_offer_patterns)
    )
    lines = [
        "[[entries]]",
        f"entry_id = {_toml_string(entry_id)}",
        'language = "sv"',
        'market = "SE"',
        f"canonical = {_toml_string(canonical)}",
        'status = "active"',
        f"variants = {_toml_array(guard_variants)}",
        f"negative_guards = {_toml_array(guard_variants)}",
        f"source_refs = {_toml_array((f'policy:no_match_policies:{policy_id}',))}",
        'layer_policy = ["negative_guard_only"]',
        f"notes = {_toml_string(reason)}",
        "",
        "[entries.language_payload.no_match_policy]",
        f"id = {_toml_string(policy_id)}",
        f"rule_schema_version = {rule_schema_version}",
        f"rule_version = {rule_version}",
        f"canonical = {_toml_string(canonical)}",
        f"ingredient_patterns = {_toml_array(ingredient_patterns)}",
        f"blocked_offer_keywords = {_toml_array(blocked_offer_keywords)}",
        f"blocked_offer_patterns = {_toml_array(blocked_offer_patterns)}",
        f"allowed_specifics = {_toml_array(allowed_specifics)}",
        f"reason = {_toml_string(reason)}",
        f"policy_ref = {_toml_string(policy_ref)}",
        f"fixture_refs = {_toml_array(fixture_refs)}",
        f"supersedes = {_toml_array(supersedes)}",
        "",
    ]
    for keyword in blocked_offer_keywords:
        lines.extend([
            "[[entries.coverage]]",
            'source_family = "no_match_policy"',
            f"canonical = {_toml_string(canonical)}",
            f"variant = {_toml_string(f'{canonical} ! {keyword}')}",
            'layer_role = "negative_guard_keyword"',
            "",
        ])
    for pattern in blocked_offer_patterns:
        lines.extend([
            "[[entries.coverage]]",
            'source_family = "no_match_policy"',
            f"canonical = {_toml_string(canonical)}",
            f"variant = {_toml_string(f'{canonical} ! {pattern}')}",
            'layer_role = "negative_guard_pattern"',
            "",
        ])
    lines.extend([
        "[[entries.negative_examples]]",
        f"ingredient = {_toml_string(negative_ingredient)}",
        f"offer_name = {_toml_string(negative_offer)}",
    ])
    if offer_category:
        lines.append(f"offer_category = {_toml_string(offer_category)}")
    lines.extend([
        "expected = 0",
        "",
    ])
    return "\n".join(lines)


def _append_no_match_policy_entry(
    *,
    paths: MatcherPaths,
    policy_id: str,
    canonical: str,
    ingredient_patterns: tuple[str, ...],
    blocked_offer_keywords: tuple[str, ...],
    blocked_offer_patterns: tuple[str, ...],
    allowed_specifics: tuple[str, ...],
    reason: str,
    policy_ref: str,
    fixture_refs: tuple[str, ...],
    supersedes: tuple[str, ...],
    negative_ingredient: str,
    negative_offer: str,
    offer_category: str,
    dry_run: bool,
) -> tuple[str, int, str]:
    target_file = _registry_entry_file(paths, "no_match_policy")
    existing_ids = _existing_entry_ids(target_file)
    entry_id = f"sv-se.guard.{_slug(policy_id)}"
    if entry_id in existing_ids:
        raise typer.BadParameter(f"no_match_policy entry already exists: {entry_id}")
    existing_keys = _existing_coverage_keys(paths)
    guard_variants = tuple(f"{canonical} ! {guard}" for guard in (*blocked_offer_keywords, *blocked_offer_patterns))
    duplicate_guards = [
        variant
        for variant in guard_variants
        if (
            "no_match_policy",
            canonical.lower(),
            variant.lower(),
            "negative_guard_keyword",
        ) in existing_keys
        or (
            "no_match_policy",
            canonical.lower(),
            variant.lower(),
            "negative_guard_pattern",
        ) in existing_keys
    ]
    if duplicate_guards:
        raise typer.BadParameter(f"no_match_policy coverage already exists: {', '.join(duplicate_guards)}")
    block = _no_match_policy_block(
        entry_id=entry_id,
        policy_id=policy_id,
        canonical=canonical,
        ingredient_patterns=ingredient_patterns,
        blocked_offer_keywords=blocked_offer_keywords,
        blocked_offer_patterns=blocked_offer_patterns,
        allowed_specifics=allowed_specifics,
        reason=reason,
        policy_ref=policy_ref,
        fixture_refs=fixture_refs,
        supersedes=supersedes,
        negative_ingredient=negative_ingredient,
        negative_offer=negative_offer,
        offer_category=offer_category,
    )
    existing_text = target_file.read_text(encoding="utf-8")
    start_line = len(existing_text.splitlines()) + 1
    _append_text_block(target_file, block, dry_run=dry_run)
    return entry_id, start_line, block


def _append_no_match_deep_sanity_stub(
    *,
    paths: MatcherPaths,
    policy_ref: str,
    negative_ingredient: str,
    negative_offer: str,
    offer_category: str,
    sanity_mode: Literal["fast-match", "backend-match"],
    dry_run: bool,
) -> str:
    lines = [
        "",
        *_generated_sanity_header(policy_ref, "no-match-policy"),
        *_deep_sanity_match_assertion(
            description="no-match-policy blocks " + negative_offer,
            offer_name=negative_offer,
            ingredient=negative_ingredient,
            offer_category=offer_category,
            expected_canonical=None,
            mode=sanity_mode,
        ),
    ]
    block = "\n".join(lines) + "\n"
    _append_text_block(paths.deep_sanity_file, block, dry_run=dry_run, trim_existing=True)
    return block


def _no_match_auto_fixture_id(policy_id: str) -> str:
    base = _slug(policy_id.removeprefix("policy_"))
    return f"{base}_negative"


def _no_match_auto_inventory_id(policy_id: str) -> str:
    return policy_id if policy_id.startswith("policy_") else f"policy_{_slug(policy_id)}"


def _no_match_fixture_row(
    *,
    fixture_id: str,
    policy_ref: str,
    source_ref: str,
    negative_ingredient: str,
    negative_offer: str,
    offer_category: str,
) -> dict[str, Any]:
    return {
        "id": fixture_id,
        "policy_ref": policy_ref,
        "source_ref": source_ref,
        "recipe_name": "No-match policy regression",
        "ingredients": [negative_ingredient],
        "offer": {
            "name": negative_offer,
            "category": offer_category,
        },
        "expected": 0,
    }


def _no_match_fixture_rows_equivalent(existing: Mapping[str, Any], planned: Mapping[str, Any]) -> bool:
    existing_offer = existing.get("offer") if isinstance(existing.get("offer"), dict) else {}
    planned_offer = planned.get("offer") if isinstance(planned.get("offer"), dict) else {}
    return (
        existing.get("expected") == planned.get("expected")
        and existing.get("ingredients") == planned.get("ingredients")
        and existing_offer.get("name") == planned_offer.get("name")
        and existing_offer.get("category") == planned_offer.get("category")
        and str(existing.get("policy_ref") or "") == str(planned.get("policy_ref") or "")
    )


def _append_or_reuse_no_match_fixture(
    *,
    paths: MatcherPaths,
    fixture_id: str,
    policy_ref: str,
    source_ref: str,
    negative_ingredient: str,
    negative_offer: str,
    offer_category: str,
    dry_run: bool,
) -> tuple[str, bool]:
    fixture_row = _no_match_fixture_row(
        fixture_id=fixture_id,
        policy_ref=policy_ref,
        source_ref=source_ref,
        negative_ingredient=negative_ingredient,
        negative_offer=negative_offer,
        offer_category=offer_category,
    )
    fixtures = load_contract_source(_source_spec(paths, "matcher_regression_cases"))
    for existing in fixtures:
        if not isinstance(existing, dict) or str(existing.get("id") or "") != fixture_id:
            continue
        if _no_match_fixture_rows_equivalent(existing, fixture_row):
            return fixture_id, False
        raise typer.BadParameter(
            f"auto fixture id already exists with different content: {fixture_id}; "
            "pass --fixture-refs explicitly or choose --policy-id"
        )
    _append_contract_source_items(
        paths=paths,
        contract="matcher_regression_cases",
        items=(fixture_row,),
        dry_run=dry_run,
    )
    return fixture_id, True


def _ensure_no_match_inventory_id_available(paths: MatcherPaths, inventory_id: str) -> None:
    inventory = load_contract_source(_source_spec(paths, "matcher_rule_inventory"))
    existing_inventory_ids = {str(item.get("id") or "") for item in inventory if isinstance(item, dict)}
    if inventory_id in existing_inventory_ids:
        raise typer.BadParameter(f"inventory entry already exists: {inventory_id}")


def _append_no_match_inventory(
    *,
    paths: MatcherPaths,
    inventory_id: str,
    policy_id: str,
    policy_ref: str,
    canonical: str,
    fixture_refs: tuple[str, ...],
    source_ref: str,
    reason: str,
    entry_id: str,
    entry_line: int,
    dry_run: bool,
) -> None:
    inventory_row = {
        "id": inventory_id,
        "status": "wrapped_adapter",
        "kind": "legacy_no_match_policy",
        "canonical": canonical,
        "owner": "matcher",
        "policy_ref": policy_ref,
        "source_refs": [source_ref],
        "fixture_refs": list(fixture_refs),
        "risk": "no_match_policy",
        "adapter_ref": f"no_match_policies:{policy_id}",
        "line_refs": [
            {
                "path": "app/languages/sv/ingredient_matching/term_registry/entries/no_match_policy.toml",
                "start": entry_line,
                "end": entry_line,
                "anchor": f"entry_id = \"{entry_id}\"",
            }
        ],
        "notes": reason,
    }
    _append_contract_source_items(
        paths=paths,
        contract="matcher_rule_inventory",
        items=(inventory_row,),
        dry_run=dry_run,
    )


def _split_set_csv(value: str | None, *, label: str, lowercase: bool = True) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not value.strip():
        return ()
    return _split_csv(value, label=label, lowercase=lowercase)


def _no_match_policy_payload_from_record(record: RegistryEntryRecord) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = tomllib.loads(record.block)
    entries = payload.get("entries", [])
    entry = entries[0] if isinstance(entries, list) and entries else {}
    if not isinstance(entry, dict):
        raise typer.BadParameter(f"{record.entry_id}: invalid no_match_policy entry block")
    language_payload = entry.get("language_payload", {})
    policy = language_payload.get("no_match_policy") if isinstance(language_payload, dict) else None
    if not isinstance(policy, dict):
        raise typer.BadParameter(f"{record.entry_id}: missing entries.language_payload.no_match_policy")
    return entry, policy


def _find_no_match_policy_record(paths: MatcherPaths, selector: str) -> tuple[Path, RegistryEntryRecord, dict[str, Any], dict[str, Any]]:
    target_file = _registry_entry_file(paths, "no_match_policy")
    matches: list[tuple[RegistryEntryRecord, dict[str, Any], dict[str, Any]]] = []
    selector_norm = _runtime_rule_normalize_text(selector)
    for record in _registry_entry_records("no-match-policy", target_file):
        entry, policy = _no_match_policy_payload_from_record(record)
        searchable = {
            record.entry_id,
            str(policy.get("id") or ""),
            str(policy.get("policy_ref") or ""),
            str(policy.get("canonical") or record.canonical),
        }
        normalized_searchable = {_runtime_rule_normalize_text(value) for value in searchable if value}
        if selector in searchable or selector_norm in normalized_searchable:
            matches.append((record, entry, policy))
    if len(matches) != 1:
        labels = "\n".join(_registry_entry_label(match[0]) for match in matches[:20])
        detail = f"\n{labels}" if labels else ""
        raise typer.BadParameter(f"selector must match exactly one no-match-policy entry; got {len(matches)}{detail}")
    record, entry, policy = matches[0]
    return target_file, record, entry, policy


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _int_value(value: Any, *, default: int) -> int:
    return value if isinstance(value, int) else default


def _first_no_match_negative_example(entry: dict[str, Any]) -> dict[str, Any]:
    examples = entry.get("negative_examples")
    if isinstance(examples, list) and examples and isinstance(examples[0], dict):
        return examples[0]
    return {}


def _guard_variants(
    canonical: str,
    blocked_offer_keywords: tuple[str, ...],
    blocked_offer_patterns: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(f"{canonical} ! {guard}" for guard in (*blocked_offer_keywords, *blocked_offer_patterns))


def _match_bridge_positive_variants(
    ingredient_patterns: tuple[str, ...],
    offer_patterns: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        f"{ingredient_pattern} -> {offer_pattern}"
        for ingredient_pattern in ingredient_patterns
        for offer_pattern in offer_patterns
    )


def _match_bridge_negative_variants(canonical: str, negative_offer_patterns: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"{canonical} ! {pattern}" for pattern in negative_offer_patterns)


def _match_bridge_block(
    *,
    entry_id: str,
    language: str,
    market: str,
    status: str,
    canonical: str,
    source_refs: tuple[str, ...],
    layer_policy: tuple[str, ...],
    notes: str,
    bridge_id: str,
    rule_schema_version: int,
    rule_version: int,
    ingredient_patterns: tuple[str, ...],
    offer_patterns: tuple[str, ...],
    negative_offer_patterns: tuple[str, ...],
    aliases: tuple[str, ...],
    fixture_refs: tuple[str, ...],
    supersedes: tuple[str, ...],
    ingredient_form_signals: tuple[str, ...],
    offer_form_signals: tuple[str, ...],
    required_offer_form_signals: tuple[str, ...],
    forbidden_offer_form_signals: tuple[str, ...],
    precedence: int | None,
    positive_ingredient: str,
    positive_offer: str,
    negative_ingredient: str,
    negative_offer: str | None,
) -> str:
    positive_variants = _match_bridge_positive_variants(ingredient_patterns, offer_patterns)
    negative_variants = _match_bridge_negative_variants(canonical, negative_offer_patterns)
    lines = [
        "[[entries]]",
        f"entry_id = {_toml_string(entry_id)}",
        f"language = {_toml_string(language)}",
        f"market = {_toml_string(market)}",
        f"canonical = {_toml_string(canonical)}",
        f"status = {_toml_string(status)}",
        f"variants = {_toml_array([*positive_variants, *negative_variants])}",
        f"ingredient_terms = {_toml_array(ingredient_patterns)}",
        f"offer_terms = {_toml_array(offer_patterns)}",
        f"negative_guards = {_toml_array(negative_variants)}",
        f"source_refs = {_toml_array(source_refs)}",
        f"layer_policy = {_toml_array(layer_policy)}",
        f"notes = {_toml_string(notes)}",
        "",
        "[entries.language_payload.match_bridge]",
        f"id = {_toml_string(bridge_id)}",
        f"rule_schema_version = {rule_schema_version}",
        f"rule_version = {rule_version}",
        f"canonical = {_toml_string(canonical)}",
        f"ingredient_patterns = {_toml_array(ingredient_patterns)}",
        f"offer_patterns = {_toml_array(offer_patterns)}",
        f"negative_offer_patterns = {_toml_array(negative_offer_patterns)}",
        f"aliases = {_toml_array(aliases)}",
        f"fixture_refs = {_toml_array(fixture_refs)}",
        f"supersedes = {_toml_array(supersedes)}",
        f"ingredient_form_signals = {_toml_array(ingredient_form_signals)}",
        f"offer_form_signals = {_toml_array(offer_form_signals)}",
        f"required_offer_form_signals = {_toml_array(required_offer_form_signals)}",
        f"forbidden_offer_form_signals = {_toml_array(forbidden_offer_form_signals)}",
    ]
    if precedence is not None:
        lines.append(f"precedence = {precedence}")
    lines.append("")

    for variant in positive_variants:
        lines.extend([
            "[[entries.coverage]]",
            'source_family = "match_bridge"',
            f"canonical = {_toml_string(canonical)}",
            f"variant = {_toml_string(variant)}",
            'layer_role = "bridge_positive"',
            "",
        ])
    for variant in negative_variants:
        lines.extend([
            "[[entries.coverage]]",
            'source_family = "match_bridge"',
            f"canonical = {_toml_string(canonical)}",
            f"variant = {_toml_string(variant)}",
            'layer_role = "bridge_negative_guard"',
            "",
        ])

    lines.extend([
        "[[entries.positive_examples]]",
        f"ingredient = {_toml_string(positive_ingredient)}",
        f"offer_name = {_toml_string(positive_offer)}",
        "expected = 1",
        "",
    ])
    if negative_offer is not None:
        lines.extend([
            "[[entries.negative_examples]]",
            f"ingredient = {_toml_string(negative_ingredient)}",
            f"offer_name = {_toml_string(negative_offer)}",
            "expected = 0",
            "",
        ])
    return "\n".join(lines)


def _match_bridge_payload_from_record(record: RegistryEntryRecord) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = tomllib.loads(record.block)
    entries = payload.get("entries", [])
    entry = entries[0] if isinstance(entries, list) and entries else {}
    if not isinstance(entry, dict):
        raise typer.BadParameter(f"{record.entry_id}: invalid match_bridge entry block")
    language_payload = entry.get("language_payload", {})
    bridge = language_payload.get("match_bridge") if isinstance(language_payload, dict) else None
    if not isinstance(bridge, dict):
        raise typer.BadParameter(f"{record.entry_id}: missing entries.language_payload.match_bridge")
    if bridge.get("blockers") or bridge.get("backend_allowances"):
        raise typer.BadParameter(
            f"{record.entry_id}: match_bridge contains nested blockers/backend_allowances; manual edit required"
        )
    return entry, bridge


def _find_match_bridge_record(paths: MatcherPaths, selector: str) -> tuple[Path, RegistryEntryRecord, dict[str, Any], dict[str, Any]]:
    target_file = _registry_entry_file(paths, "match_bridge")
    matches: list[tuple[RegistryEntryRecord, dict[str, Any], dict[str, Any]]] = []
    selector_norm = _runtime_rule_normalize_text(selector)
    for record in _registry_entry_records("match-bridge", target_file):
        entry, bridge = _match_bridge_payload_from_record(record)
        searchable = {
            record.entry_id,
            str(bridge.get("id") or ""),
            str(bridge.get("canonical") or record.canonical),
            *[str(alias) for alias in bridge.get("aliases") or []],
        }
        normalized_searchable = {_runtime_rule_normalize_text(value) for value in searchable if value}
        if selector in searchable or selector_norm in normalized_searchable:
            matches.append((record, entry, bridge))
    if len(matches) != 1:
        labels = "\n".join(_registry_entry_label(match[0]) for match in matches[:20])
        detail = f"\n{labels}" if labels else ""
        raise typer.BadParameter(f"selector must match exactly one match-bridge entry; got {len(matches)}{detail}")
    record, entry, bridge = matches[0]
    return target_file, record, entry, bridge


def _remove_values(values: tuple[str, ...], removals: tuple[str, ...], *, label: str) -> tuple[str, ...]:
    if not removals:
        return values
    missing = tuple(value for value in removals if value not in values)
    if missing:
        raise typer.BadParameter(f"{label} not present: {', '.join(missing)}")
    removal_set = set(removals)
    return tuple(value for value in values if value not in removal_set)


def _first_example(entry: dict[str, Any], field: str) -> dict[str, Any]:
    examples = entry.get(field)
    if isinstance(examples, list) and examples and isinstance(examples[0], dict):
        return examples[0]
    return {}


def _extraction_layer_roles(side: Literal["product", "ingredient", "both"]) -> tuple[str, ...]:
    roles: list[str] = []
    if side in {"ingredient", "both"}:
        roles.append("hardcoded_keyword_output:extract_keywords_from_ingredient")
    if side in {"product", "both"}:
        roles.append("hardcoded_keyword_output:extract_keywords_from_product")
    return tuple(roles)


def _extraction_helper_block(
    *,
    entry_id: str,
    canonical: str,
    side: Literal["product", "ingredient", "both"],
    source_refs: tuple[str, ...],
) -> str:
    ingredient_terms = (canonical,) if side in {"ingredient", "both"} else ()
    offer_terms = (canonical,) if side in {"product", "both"} else ()
    lines = [
        "[[entries]]",
        f"entry_id = {_toml_string(entry_id)}",
        'language = "sv"',
        'market = "SE"',
        f"canonical = {_toml_string(canonical)}",
        'status = "active"',
        f"variants = {_toml_array((canonical,))}",
    ]
    if ingredient_terms:
        lines.append(f"ingredient_terms = {_toml_array(ingredient_terms)}")
    if offer_terms:
        lines.append(f"offer_terms = {_toml_array(offer_terms)}")
    lines.extend([
        "negative_guards = []",
        f"source_refs = {_toml_array(source_refs)}",
        'layer_policy = ["normal"]',
        f"notes = {_toml_string('Generated by dm matcher add extraction-helper for hardcoded extraction.py output.')}",
        "",
    ])
    for role in _extraction_layer_roles(side):
        lines.extend([
            "[[entries.coverage]]",
            'source_family = "extraction_helper"',
            f"canonical = {_toml_string(canonical)}",
            f"variant = {_toml_string(canonical)}",
            f"layer_role = {_toml_string(role)}",
            "",
        ])
    return "\n".join(lines)


def _append_extraction_helper_entry(
    *,
    paths: MatcherPaths,
    canonical: str,
    side: Literal["product", "ingredient", "both"],
    source_refs: tuple[str, ...],
    replace_existing: bool,
    dry_run: bool,
) -> tuple[str, int, str, bool]:
    target_file = _registry_entry_file(paths, "extraction_helper")
    existing_ids = _existing_entry_ids(target_file)
    entry_id = f"sv-se.family.{_slug(canonical)}"
    if entry_id in existing_ids:
        if not replace_existing:
            raise typer.BadParameter(
                f"extraction_helper entry already exists: {entry_id}. "
                "Use --replace-existing to rewrite its covered side/source refs."
            )
        records = _registry_entry_records("extraction-helper", target_file)
        matches = [record for record in records if record.entry_id == entry_id]
        if len(matches) != 1:
            raise typer.BadParameter(f"expected exactly one extraction_helper entry for {entry_id}; got {len(matches)}")
        record = matches[0]
        payload = tomllib.loads(record.block)
        entry = payload.get("entries", [{}])[0]
        terms = set(_registry_entry_terms(entry))
        if terms - {canonical}:
            raise typer.BadParameter(
                f"{entry_id} has extra terms ({', '.join(sorted(terms - {canonical}))}); "
                "manual edit required so extra product/ingredient terms are not lost."
            )
        for coverage in entry.get("coverage", []):
            if coverage.get("canonical") != canonical or coverage.get("variant") != canonical:
                raise typer.BadParameter(
                    f"{entry_id} has non-canonical coverage rows; manual edit required."
                )
        block = _extraction_helper_block(
            entry_id=entry_id,
            canonical=canonical,
            side=side,
            source_refs=source_refs,
        )
        if not dry_run:
            _write_registry_entry_block(target_file, record, block, dry_run=False)
        return entry_id, record.start, block, True
    existing_keys = _existing_coverage_keys(paths)
    duplicate_roles = [
        role
        for role in _extraction_layer_roles(side)
        if ("extraction_helper", canonical.lower(), canonical.lower(), role) in existing_keys
    ]
    if duplicate_roles:
        raise typer.BadParameter(
            f"extraction_helper coverage already exists for {canonical}: {', '.join(duplicate_roles)}"
        )
    block = _extraction_helper_block(
        entry_id=entry_id,
        canonical=canonical,
        side=side,
        source_refs=source_refs,
    )
    existing_text = target_file.read_text(encoding="utf-8")
    start_line = len(existing_text.splitlines()) + 1
    _append_text_block(target_file, block, dry_run=dry_run)
    return entry_id, start_line, block, False


def _append_extraction_helper_deep_sanity_stub(
    *,
    paths: MatcherPaths,
    policy_ref: str,
    canonical: str,
    side: Literal["product", "ingredient", "both"],
    input_text: str,
    offer_category: str,
    dry_run: bool,
) -> str:
    lines = [
        "",
        *_generated_sanity_header(policy_ref, "extraction-helper"),
    ]
    if side in {"ingredient", "both"}:
        lines.append(
            f"test({_toml_string('KW ' + input_text + ' ingredient -> ' + canonical)}, "
            f"extract_keywords_from_ingredient({_toml_string(input_text)}), [{_toml_string(canonical)}])"
        )
    if side in {"product", "both"}:
        lines.append(
            f"test({_toml_string('KW ' + input_text + ' product -> ' + canonical)}, "
            f"extract_keywords_from_product({_toml_string(input_text)}, {_toml_string(offer_category)}), [{_toml_string(canonical)}])"
        )
    block = "\n".join(lines) + "\n"
    _append_text_block(paths.deep_sanity_file, block, dry_run=dry_run, trim_existing=True)
    return block


def _ensure_can_add_keyword_extra_parent(
    *,
    paths: MatcherPaths,
    canonical: str,
    kids: tuple[str, ...],
    fixture_ids: tuple[str, ...],
    inventory_id: str,
) -> None:
    fixtures = load_contract_source(_source_spec(paths, "matcher_regression_cases"))
    existing_fixture_ids = {str(item.get("id") or "") for item in fixtures if isinstance(item, dict)}
    duplicate_fixtures = sorted(set(fixture_ids) & existing_fixture_ids)
    if duplicate_fixtures:
        raise typer.BadParameter(f"fixture already exists: {', '.join(duplicate_fixtures)}")

    inventory = load_contract_source(_source_spec(paths, "matcher_rule_inventory"))
    existing_inventory_ids = {str(item.get("id") or "") for item in inventory if isinstance(item, dict)}
    if inventory_id in existing_inventory_ids:
        raise typer.BadParameter(f"inventory entry already exists: {inventory_id}")

    toml_payload = tomllib.loads(paths.keyword_extra_parent_file.read_text(encoding="utf-8"))
    entries = toml_payload.get("entries", [])
    if not isinstance(entries, list):
        raise typer.BadParameter(f"{paths.keyword_extra_parent_file} must contain TOML [[entries]]")
    for kid in kids:
        has_mapping = any(
            isinstance(entry, dict)
            and str(entry.get("canonical") or "").lower() == canonical
            and kid in {str(variant).lower() for variant in entry.get("variants", [])}
            for entry in entries
        )
        if has_mapping:
            raise typer.BadParameter(f"keyword_extra_parent coverage already exists: {kid} -> {canonical}")


def _ensure_can_add_keyword_synonym(
    *,
    paths: MatcherPaths,
    canonical: str,
    variants: tuple[str, ...],
    fixture_ids: tuple[str, ...],
    inventory_id: str | None,
) -> None:
    toml_payload = tomllib.loads(paths.keyword_synonym_file.read_text(encoding="utf-8"))
    entries = toml_payload.get("entries", [])
    if not isinstance(entries, list):
        raise typer.BadParameter(f"{paths.keyword_synonym_file} must contain TOML [[entries]]")
    for variant in variants:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_variants = {str(item).lower() for item in entry.get("variants", [])}
            if variant in entry_variants:
                target = str(entry.get("canonical") or "<unknown>")
                raise typer.BadParameter(f"keyword_synonym mapping already exists: {variant} -> {target}")

    if fixture_ids:
        fixtures = load_contract_source(_source_spec(paths, "matcher_regression_cases"))
        existing_fixture_ids = {str(item.get("id") or "") for item in fixtures if isinstance(item, dict)}
        duplicate_fixtures = sorted(set(fixture_ids) & existing_fixture_ids)
        if duplicate_fixtures:
            raise typer.BadParameter(f"fixture already exists: {', '.join(duplicate_fixtures)}")

    if inventory_id:
        inventory = load_contract_source(_source_spec(paths, "matcher_rule_inventory"))
        existing_inventory_ids = {str(item.get("id") or "") for item in inventory if isinstance(item, dict)}
        if inventory_id in existing_inventory_ids:
            raise typer.BadParameter(f"inventory entry already exists: {inventory_id}")


def _next_numeric_suffix(entry_ids: set[str]) -> int:
    suffixes = []
    for entry_id in entry_ids:
        match = re.search(r"_(\d+)$", entry_id)
        if match:
            suffixes.append(int(match.group(1)))
    return (max(suffixes) + 1) if suffixes else 1


def _keyword_extra_parent_block(
    *,
    entry_id: str,
    canonical: str,
    kid: str,
    source_ref: str,
    ingredient: str,
    offer_name: str,
) -> str:
    return "\n".join([
        "[[entries]]",
        f"entry_id = {_toml_string(entry_id)}",
        'language = "sv"',
        'market = "SE"',
        f"canonical = {_toml_string(canonical)}",
        'status = "active"',
        f"variants = {_toml_array((kid,))}",
        f"route_terms = {_toml_array((canonical,))}",
        f"source_refs = {_toml_array((source_ref,))}",
        'layer_policy = ["route_only"]',
        f"notes = {_toml_string('Generated by dm matcher add keyword-extra-parent.')}",
        "",
        "[[entries.coverage]]",
        'source_family = "keyword_extra_parent"',
        f"canonical = {_toml_string(canonical)}",
        f"variant = {_toml_string(kid)}",
        'layer_role = "keyword_extra_parent_mapping"',
        "",
        "[[entries.positive_examples]]",
        f"ingredient = {_toml_string(ingredient)}",
        f"offer_name = {_toml_string(offer_name)}",
        "expected = 1",
        "",
    ])


def _append_keyword_extra_parent_entries(
    *,
    paths: MatcherPaths,
    canonical: str,
    kids: tuple[str, ...],
    offer_names: tuple[str, ...],
    source_ref: str,
    ingredient: str,
    dry_run: bool,
) -> tuple[tuple[str, ...], int, str]:
    existing_ids = _existing_entry_ids(paths.keyword_extra_parent_file)
    suffix = _next_numeric_suffix(existing_ids)
    canonical_slug = _slug(canonical)
    entry_ids: list[str] = []
    blocks: list[str] = []
    for kid, offer_name in zip(kids, offer_names, strict=True):
        base = f"sv-se.family.{canonical_slug}.{_slug(kid)}"
        entry_id = f"{base}_{suffix:03d}"
        while entry_id in existing_ids:
            suffix += 1
            entry_id = f"{base}_{suffix:03d}"
        suffix += 1
        existing_ids.add(entry_id)
        entry_ids.append(entry_id)
        blocks.append(_keyword_extra_parent_block(
            entry_id=entry_id,
            canonical=canonical,
            kid=kid,
            source_ref=source_ref,
            ingredient=ingredient,
            offer_name=offer_name,
        ))

    existing_text = paths.keyword_extra_parent_file.read_text(encoding="utf-8")
    start_line = len(existing_text.splitlines()) + 1
    append_text = "\n".join(blocks)
    _append_text_block(paths.keyword_extra_parent_file, append_text, dry_run=dry_run)
    return tuple(entry_ids), start_line, append_text


def _keyword_synonym_block(
    *,
    entry_id: str,
    canonical: str,
    variants: tuple[str, ...],
    source_ref: str,
    sanity_offer: str,
    offer_category: str,
    ingredient_override: str | None,
) -> str:
    lines = [
        "[[entries]]",
        f"entry_id = {_toml_string(entry_id)}",
        'language = "sv"',
        'market = "SE"',
        f"canonical = {_toml_string(canonical)}",
        'status = "active"',
        f"variants = {_toml_array(variants)}",
        f"offer_terms = {_toml_array((canonical,))}",
        f"source_refs = {_toml_array((source_ref,))}",
        'layer_policy = ["offer_alias"]',
        f"notes = {_toml_string('Generated by dm matcher add keyword-synonym; coverage is registry-convention derived.')}",
        "",
    ]
    for variant in variants:
        lines.extend([
            "[[entries.positive_examples]]",
            f"ingredient = {_toml_string(ingredient_override or variant)}",
            f"offer_name = {_toml_string(sanity_offer)}",
            f"offer_category = {_toml_string(offer_category)}",
            "expected = 1",
            "",
        ])
    return "\n".join(lines)


def _append_keyword_synonym_entry(
    *,
    paths: MatcherPaths,
    canonical: str,
    variants: tuple[str, ...],
    source_ref: str,
    sanity_offer: str,
    offer_category: str,
    ingredient_override: str | None,
    dry_run: bool,
) -> tuple[str, int, str]:
    existing_ids = _existing_entry_ids(paths.keyword_synonym_file)
    suffix = _next_numeric_suffix(existing_ids)
    base = f"sv-se.alias.{_slug(canonical)}.{_slug(variants[0])}"
    entry_id = f"{base}_{suffix:03d}"
    while entry_id in existing_ids:
        suffix += 1
        entry_id = f"{base}_{suffix:03d}"

    existing_text = paths.keyword_synonym_file.read_text(encoding="utf-8")
    start_line = len(existing_text.splitlines()) + 1
    block = _keyword_synonym_block(
        entry_id=entry_id,
        canonical=canonical,
        variants=variants,
        source_ref=source_ref,
        sanity_offer=sanity_offer,
        offer_category=offer_category,
        ingredient_override=ingredient_override,
    )
    _append_text_block(paths.keyword_synonym_file, block, dry_run=dry_run)
    return entry_id, start_line, block


def _append_keyword_synonym_fixtures(
    *,
    paths: MatcherPaths,
    canonical: str,
    variants: tuple[str, ...],
    sanity_offer: str,
    offer_category: str,
    ingredient_override: str | None,
    policy_ref: str,
    source_ref: str,
    dry_run: bool,
) -> tuple[str, ...]:
    canonical_slug = _slug(canonical)
    fixture_rows: list[dict] = []
    fixture_ids: list[str] = []
    for variant in variants:
        fixture_id = f"keyword_synonym_{canonical_slug}_{_slug(variant)}_positive"
        fixture_ids.append(fixture_id)
        ingredient = ingredient_override or variant
        fixture_rows.append({
            "id": fixture_id,
            "policy_ref": policy_ref,
            "source_ref": source_ref,
            "recipe_name": "Keyword synonym regression",
            "ingredients": [ingredient],
            "expected_matches": [
                {
                    "canonical": canonical,
                    "ingredient_index": 0,
                    "must_match_keyword": canonical,
                }
            ],
            "offer": {
                "name": sanity_offer,
                "category": offer_category,
            },
            "expected": 1,
        })
    _append_contract_source_items(
        paths=paths,
        contract="matcher_regression_cases",
        items=tuple(fixture_rows),
        dry_run=dry_run,
    )
    return tuple(fixture_ids)


def _append_keyword_synonym_inventory(
    *,
    paths: MatcherPaths,
    canonical: str,
    variants: tuple[str, ...],
    fixture_ids: tuple[str, ...],
    policy_ref: str,
    source_ref: str,
    inventory_id: str,
    entry_id: str,
    entry_line: int,
    dry_run: bool,
) -> None:
    inventory_row = {
        "id": inventory_id,
        "status": "wrapped_adapter",
        "kind": "legacy_synonym",
        "canonical": canonical,
        "owner": "matcher",
        "policy_ref": policy_ref,
        "source_refs": [source_ref],
        "fixture_refs": list(fixture_ids),
        "risk": "spelling_alias",
        "adapter_ref": f"keyword_synonyms:{entry_id}",
        "line_refs": [
            {
                "path": "app/languages/sv/ingredient_matching/term_registry/entries/keyword_synonym.toml",
                "start": entry_line,
                "end": entry_line,
                "anchor": f"entry_id = \"{entry_id}\"",
            }
        ],
        "notes": (
            f"{', '.join(variants)} normalize to {canonical}. "
            "Generated by dm matcher add keyword-synonym."
        ),
    }
    _append_contract_source_items(
        paths=paths,
        contract="matcher_rule_inventory",
        items=(inventory_row,),
        dry_run=dry_run,
    )


def _append_fixtures(
    *,
    paths: MatcherPaths,
    canonical: str,
    kids: tuple[str, ...],
    offer_names: tuple[str, ...],
    recipe_name: str,
    ingredient: str,
    offer_category: str,
    policy_ref: str,
    source_ref: str,
    dry_run: bool,
) -> tuple[str, ...]:
    fixture_ids = []
    fixture_rows: list[dict] = []
    canonical_slug = _slug(canonical)
    for kid, offer_name in zip(kids, offer_names, strict=True):
        fixture_id = f"keyword_extra_parent_{canonical_slug}_{_slug(kid)}_positive"
        fixture_ids.append(fixture_id)
        fixture_rows.append({
            "id": fixture_id,
            "policy_ref": policy_ref,
            "source_ref": source_ref,
            "recipe_name": recipe_name,
            "ingredients": [ingredient],
            "expected_matches": [
                {
                    "canonical": canonical,
                    "ingredient_index": 0,
                    "must_match_keyword": canonical,
                }
            ],
            "offer": {
                "name": offer_name,
                "category": offer_category,
            },
            "expected": 1,
        })
    _append_contract_source_items(
        paths=paths,
        contract="matcher_regression_cases",
        items=tuple(fixture_rows),
        dry_run=dry_run,
    )
    return tuple(fixture_ids)


def _append_inventory(
    *,
    paths: MatcherPaths,
    canonical: str,
    kids: tuple[str, ...],
    fixture_ids: tuple[str, ...],
    policy_ref: str,
    source_ref: str,
    inventory_id: str,
    first_entry_id: str,
    first_entry_line: int,
    dry_run: bool,
) -> None:
    kids_text = ", ".join(kids)
    inventory_row = {
        "id": inventory_id,
        "status": "wrapped_adapter",
        "kind": "legacy_parent",
        "canonical": canonical,
        "owner": "matcher",
        "policy_ref": policy_ref,
        "source_refs": [source_ref],
        "fixture_refs": list(fixture_ids),
        "risk": "policy_term",
        "adapter_ref": f"matcher_layer_diagnostics:{policy_ref}",
        "line_refs": [
            {
                "path": "app/languages/sv/ingredient_matching/term_registry/entries/keyword_extra_parent.toml",
                "start": first_entry_line,
                "end": first_entry_line,
                "anchor": f"entry_id = \"{first_entry_id}\"",
            }
        ],
        "notes": (
            f"{kids_text} roll up to generic {canonical} for recipes that ask for "
            "the parent family. Generated by dm matcher add keyword-extra-parent."
        ),
    }
    _append_contract_source_items(
        paths=paths,
        contract="matcher_rule_inventory",
        items=(inventory_row,),
        dry_run=dry_run,
    )


def _append_deep_sanity_stub(
    *,
    paths: MatcherPaths,
    canonical: str,
    kids: tuple[str, ...],
    offer_names: tuple[str, ...],
    ingredient: str,
    offer_category: str,
    policy_ref: str,
    sanity_mode: Literal["fast-match", "backend-match"],
    dry_run: bool,
) -> str:
    lines = [
        "",
        *_generated_sanity_header(policy_ref, "keyword-extra-parent"),
    ]
    for kid, offer_name in zip(kids, offer_names, strict=True):
        expected_canonical = _runtime_observed_expected_canonical(
            paths=paths,
            requested_expected=canonical,
            offer_name=offer_name,
            ingredient=ingredient,
            offer_category=offer_category,
            sanity_mode=sanity_mode,
            dry_run=dry_run,
        )
        lines.extend(_deep_sanity_match_assertion(
            description=_titleish(canonical) + " recipe matches " + kid,
            offer_name=offer_name,
            ingredient=ingredient,
            offer_category=offer_category,
            expected_canonical=expected_canonical,
            mode=sanity_mode,
            recipe_name=_titleish(canonical) + " recipe",
        ))
    block = "\n".join(lines) + "\n"
    _append_text_block(paths.deep_sanity_file, block, dry_run=dry_run, trim_existing=True)
    return block


def _append_keyword_synonym_deep_sanity_stub(
    *,
    paths: MatcherPaths,
    canonical: str,
    variants: tuple[str, ...],
    sanity_offer: str,
    offer_category: str,
    ingredient_override: str | None,
    policy_ref: str,
    sanity_mode: Literal["fast-match", "backend-match"],
    dry_run: bool,
) -> str:
    lines = [
        "",
        *_generated_sanity_header(policy_ref, "keyword-synonym"),
    ]
    for variant in variants:
        ingredient = ingredient_override or variant
        expected_canonical = _runtime_observed_expected_canonical(
            paths=paths,
            requested_expected=canonical,
            offer_name=sanity_offer,
            ingredient=ingredient,
            offer_category=offer_category,
            sanity_mode=sanity_mode,
            dry_run=dry_run,
        )
        lines.extend(_deep_sanity_match_assertion(
            description="Keyword synonym " + variant + " matches " + canonical,
            offer_name=sanity_offer,
            ingredient=ingredient,
            offer_category=offer_category,
            expected_canonical=expected_canonical,
            mode=sanity_mode,
        ))
    block = "\n".join(lines) + "\n"
    _append_text_block(paths.deep_sanity_file, block, dry_run=dry_run, trim_existing=True)
    return block


def _run(argv: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> int:
    print("+ " + " ".join(str(part) for part in argv), flush=True)
    return subprocess.run(argv, cwd=cwd, env=env, check=False).returncode


def _run_support_check(
    script_name: str,
    args: list[str],
    *,
    tree_root: Path | None = None,
    report_root: Path | None = None,
    cwd: Path | None = None,
) -> int:
    paths = _paths(tree_root)
    env = _gate_env(paths, report_root, None)
    return _run(
        [sys.executable, str(SUPPORT_CHECKS_DIR / script_name), *args],
        cwd=cwd or APP_DIR,
        env=env,
    )


def _run_coverage_generator(paths: MatcherPaths) -> int:
    argv = [
        sys.executable,
        str(SUPPORT_CHECKS_DIR / "generate_matcher_registry_coverage.py"),
        "--tree-root",
        str(paths.repo_root),
        "--write",
    ]
    return _run(argv, cwd=paths.repo_root)


def _write_runtime_delta_entries(paths: MatcherPaths, filename: str, toml_text: str) -> Path:
    runtime_entries_dir = paths.repo_root / ".dm_matcher_runtime_entries"
    runtime_entries_dir.mkdir(parents=True, exist_ok=True)
    (runtime_entries_dir / filename).write_text(toml_text, encoding="utf-8")
    return runtime_entries_dir


def _gate_env(
    paths: MatcherPaths,
    report_root: Path | None,
    runtime_entries_dir: Path | None,
) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("DEAL_MEALS_SUPPORT_REPORT_ROOT", "/tmp/deal-meals-support-checks-dm")
    if report_root is not None:
        env["DEAL_MEALS_SUPPORT_REPORT_ROOT"] = str(report_root)
    if runtime_entries_dir is not None:
        env["TERM_REGISTRY_EXTRA_ENTRIES_DIRS"] = str(runtime_entries_dir)
        env.pop("TERM_REGISTRY_DISABLE_LOCAL_ENTRIES", None)
    return env


def _run_track_b_gates(
    *,
    paths: MatcherPaths,
    policy_ref: str,
    first_fixture_id: str,
    report_root: Path | None,
    runtime_entries_dir: Path | None,
) -> int:
    argv = [
        sys.executable,
        str(SUPPORT_CHECKS_DIR / "run_matcher_change_gates.py"),
        "--track",
        "B",
        "--policy-ref",
        policy_ref,
        "--case-id",
        first_fixture_id,
        "--fixtures-changed",
        "--inventory-changed",
    ]
    if paths.app_dir == APP_DIR:
        argv.extend(["--registry-changed", "--runtime-changed"])
    else:
        argv.extend([
            "--tree-root",
            str(paths.repo_root),
            "--no-registry-changed",
            "--no-runtime-changed",
            "--no-support-checks-changed",
        ])
    return _run(argv, cwd=APP_DIR, env=_gate_env(paths, report_root, runtime_entries_dir))


def _run_track_b_change_plan(
    *,
    paths: MatcherPaths,
    change: MatcherChangePlan,
    report_root: Path | None,
) -> int:
    if _matcher_session_should_defer_gates(paths):
        _echo_session_deferred_gates()
        return 0

    coverage_status = _run_coverage_generator(paths)
    if coverage_status != 0:
        return coverage_status

    runtime_entries_dir = (
        _write_runtime_delta_entries(paths, change.runtime_delta_filename, change.toml_preview)
        if paths.app_dir != APP_DIR and change.runtime_delta_filename is not None
        else None
    )
    return _run_track_b_gates(
        paths=paths,
        policy_ref=change.policy_ref,
        first_fixture_id=change.first_fixture_id,
        report_root=report_root,
        runtime_entries_dir=runtime_entries_dir,
    )


def _run_keyword_synonym_light_gates(
    *,
    paths: MatcherPaths,
    report_root: Path | None,
) -> int:
    if _matcher_session_should_defer_gates(paths):
        _echo_session_deferred_gates()
        return 0

    commands = [
        ("promote_term_baseline.py", []),
        ("run_matcher_change_preflight.py", []),
        ("run_term_registry_contract_checks.py", ["--language", "sv"]),
        ("run_term_registry_add_term_checks.py", ["--language", "sv"]),
        ("run_term_registry_export_checks.py", ["--language", "sv"]),
        ("run_deep_matcher_sanity.py", []),
    ]
    for script_name, args in commands:
        status = _run_support_check(
            script_name,
            args,
            tree_root=paths.repo_root if paths.app_dir != APP_DIR else None,
            report_root=report_root,
            cwd=APP_DIR,
        )
        if status != 0:
            return status
    return 0


def _regenerate_contract_json(paths: MatcherPaths) -> None:
    drifted = [
        result.contract
        for result in check_generated_contract_json(tree_root=paths.repo_root, write=True)
        if result.drifted
    ]
    if drifted:
        raise typer.BadParameter(f"generated matcher contract JSON still drifts: {', '.join(drifted)}")


def _print_dry_run_preview(change: MatcherChangePlan) -> None:
    if change.toml_preview:
        typer.echo(change.toml_preview)
    if change.fixture_ids:
        typer.echo(f"# fixture_refs: {', '.join(change.fixture_ids)}")
    if change.inventory_id:
        typer.echo(f"# inventory: {change.inventory_id}")
    if change.sanity_preview:
        typer.echo(change.sanity_preview)
    typer.echo("Dry run only; no files written.")


def _print_fixture_make_negative_summary(
    summary: Mapping[str, Any],
    *,
    dry_run: bool,
) -> None:
    fixture_id = str(summary["fixture_id"])
    if summary["changed"]:
        action = "Would convert" if dry_run else "Converted"
        typer.echo(f"{action} fixture to negative: {fixture_id}")
    else:
        typer.echo(f"Fixture already negative: {fixture_id}")
    typer.echo(f"  expected: {summary['previous_expected']} -> 0")
    typer.echo(f"  removed expected_matches: {summary['removed_expected_matches']}")
    if summary["previous_policy_ref"] != summary["new_policy_ref"]:
        typer.echo(f"  policy_ref: {summary['previous_policy_ref']} -> {summary['new_policy_ref']}")
    if summary["previous_source_ref"] != summary["new_source_ref"]:
        typer.echo(f"  source_ref: {summary['previous_source_ref']} -> {summary['new_source_ref']}")
    if dry_run:
        typer.echo("Dry run only; no files written.")


def _print_fixture_make_positive_summary(
    summary: Mapping[str, Any],
    *,
    dry_run: bool,
) -> None:
    fixture_id = str(summary["fixture_id"])
    inference = summary.get("inference") or {}
    if inference:
        typer.echo("Current matcher result:")
        typer.echo(f"  canonical: {inference.get('canonical')}")
        typer.echo(f"  ingredient_index: {inference.get('ingredient_index')}")
        typer.echo(f"  must_match_keyword: {inference.get('must_match_keyword')}")
        typer.echo(f"  paths: {inference.get('paths')}")
    if summary["changed"]:
        action = "Would convert" if dry_run else "Converted"
        typer.echo(f"{action} fixture to positive: {fixture_id}")
    else:
        typer.echo(f"Fixture already positive with same expected_matches: {fixture_id}")
    expected_match = summary["expected_match"]
    typer.echo(f"  expected: {summary['previous_expected']} -> 1")
    typer.echo(f"  previous expected_matches: {summary['previous_expected_matches']}")
    typer.echo(
        "  expected_match: "
        f"ingredient_index={expected_match['ingredient_index']} "
        f"canonical={expected_match['canonical']} "
        f"must_match_keyword={expected_match.get('must_match_keyword', '-')}"
    )
    if summary["previous_policy_ref"] != summary["new_policy_ref"]:
        typer.echo(f"  policy_ref: {summary['previous_policy_ref']} -> {summary['new_policy_ref']}")
    if summary["previous_source_ref"] != summary["new_source_ref"]:
        typer.echo(f"  source_ref: {summary['previous_source_ref']} -> {summary['new_source_ref']}")
    if dry_run:
        typer.echo("Dry run only; no files written.")


def _run_preflight(paths: MatcherPaths, report_root: Path | None) -> int:
    tree_root = paths.repo_root if paths.app_dir != APP_DIR else None
    return _run_support_check(
        "run_matcher_change_preflight.py",
        _tree_root_args(tree_root),
        tree_root=tree_root,
        report_root=report_root,
        cwd=APP_DIR,
    )


def _resolve_staged_source_path(paths: MatcherPaths, source_path: str) -> Path:
    raw = Path(source_path)
    if raw.is_absolute():
        return raw
    if raw.parts and raw.parts[0] == "app":
        return paths.repo_root / raw
    return paths.app_dir / raw


def _apply_promote_staged_output(
    *,
    paths: MatcherPaths,
    output_dir: Path,
    dry_run: bool,
) -> None:
    manifest_path = output_dir / "promotion_manifest.json"
    if not manifest_path.exists():
        raise typer.BadParameter(f"promotion manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed_files = manifest.get("changed_files")
    if not isinstance(changed_files, list) or not changed_files:
        raise typer.BadParameter(f"promotion manifest has no changed_files: {manifest_path}")

    applied = 0
    for item in changed_files:
        if not isinstance(item, dict):
            continue
        source_path = str(item.get("source_path") or "")
        staged_path = Path(str(item.get("staged_path") or ""))
        if not source_path or not staged_path:
            raise typer.BadParameter(f"invalid changed_files entry in {manifest_path}: {item!r}")
        if not staged_path.is_absolute():
            staged_path = output_dir / staged_path
        target_path = _resolve_staged_source_path(paths, source_path)
        if not staged_path.exists():
            raise typer.BadParameter(f"staged file missing: {staged_path}")
        typer.echo(f"{'Would apply' if dry_run else 'Applying'} {staged_path} -> {target_path}")
        if not dry_run:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(staged_path, target_path)
        applied += 1
    typer.echo(f"{'Would apply' if dry_run else 'Applied'} {applied} staged promotion file(s).")


def _watch_files(paths: MatcherPaths) -> tuple[Path, ...]:
    entries_dir = paths.app_dir / "languages" / "sv" / "ingredient_matching" / "term_registry" / "entries"
    contract_sources_dir = paths.app_dir / "languages" / "sv" / "matcher_contracts" / "sources"
    primary_contract_sources = {paths.fixture_source_file, paths.inventory_source_file}
    files = [
        paths.fixture_file,
        paths.inventory_file,
        paths.fixture_source_file,
        paths.inventory_source_file,
        paths.deep_sanity_file,
        *sorted(entries_dir.glob("*.toml")),
        *sorted(path for path in contract_sources_dir.glob("*.toml") if path not in primary_contract_sources),
    ]
    return tuple(path for path in files if path.exists())


def _mtime_snapshot(files: tuple[Path, ...]) -> dict[Path, int]:
    return {path: path.stat().st_mtime_ns for path in files if path.exists()}


def _validate_keyword_extra_parent_args(canonical: str, kids: tuple[str, ...]) -> None:
    if not canonical.strip():
        raise typer.BadParameter("canonical must not be empty")
    if any(kid == canonical for kid in kids):
        raise typer.BadParameter("kids must differ from canonical")
    if any(re.search(r"\s", kid) for kid in kids):
        raise typer.BadParameter("keyword-extra-parent currently supports single-token kids only")


def _matching_py_path(paths: MatcherPaths) -> Path:
    return paths.app_dir / "languages" / "sv" / "ingredient_matching" / "matching.py"


def _python_identifier_slug(value: str) -> str:
    slug = _slug(value, fallback="smart_blocker")
    if slug[0].isdigit():
        slug = f"rule_{slug}"
    return slug


def _smart_blocker_function_name(name: str) -> str:
    return f"_{_python_identifier_slug(name)}_requirement_allows_product"


def _smart_blocker_stub(
    *,
    function_name: str,
    description: str,
    uses_product_keywords: bool,
) -> str:
    signature = [
        f"def {function_name}(",
        "    product_lower: str,",
        "    ingredient_lower: str,",
        "    matched_keyword: Optional[str],",
    ]
    if uses_product_keywords:
        signature.append("    product_keywords: Iterable[str],")
    signature.extend([
        ") -> bool:",
        f"    \"\"\"{description.strip()}\"\"\"",
        "",
        "    # TODO: replace this no-op scaffold with the actual product/ingredient guard.",
        "    # Return False only for the specific false-positive shape this blocker owns.",
        "    return True",
        "",
        "",
    ])
    return "\n".join(signature)


def _smart_blocker_call(function_name: str, *, uses_product_keywords: bool) -> str:
    if uses_product_keywords:
        return f"{function_name}(product_lower, ingredient_lower, matched_keyword, product_keywords)"
    return f"{function_name}(product_lower, ingredient_lower, matched_keyword)"


def _insert_smart_blocker_scaffold(
    *,
    paths: MatcherPaths,
    name: str,
    description: str,
    uses_product_keywords: bool,
    dry_run: bool,
) -> tuple[str, str]:
    target = _matching_py_path(paths)
    text = target.read_text(encoding="utf-8")
    function_name = _smart_blocker_function_name(name)
    if re.search(rf"(?m)^def {re.escape(function_name)}\(", text):
        raise typer.BadParameter(f"smart-blocker function already exists: {function_name}")

    guard_marker = "\ndef _product_requirement_guards_allow_product("
    guard_index = text.find(guard_marker)
    if guard_index < 0:
        raise typer.BadParameter("could not find _product_requirement_guards_allow_product insertion point")

    stub = _smart_blocker_stub(
        function_name=function_name,
        description=description,
        uses_product_keywords=uses_product_keywords,
    )
    call = _smart_blocker_call(function_name, uses_product_keywords=uses_product_keywords)
    if call in text:
        raise typer.BadParameter(f"smart-blocker call already exists: {call}")
    chain_marker = "        and _raw_sill_requirement_allows_product(product_lower, ingredient_lower, matched_keyword)\n"
    if chain_marker not in text:
        raise typer.BadParameter("could not find product requirement guard chain insertion point")

    new_text = text[:guard_index + 1] + stub + text[guard_index + 1:]
    new_text = new_text.replace(chain_marker, chain_marker + f"        and {call}\n", 1)
    if not dry_run:
        target.write_text(new_text, encoding="utf-8")
    return function_name, call


def _runtime_rule_normalize_text(value: str) -> str:
    try:
        from languages.sv.normalization import fix_swedish_chars
    except ModuleNotFoundError:
        from app.languages.sv.normalization import fix_swedish_chars

    return fix_swedish_chars(value).lower()


def _space_normalized_keyword_text(value: str) -> str:
    try:
        from languages.sv.normalization import fix_swedish_chars
        from languages.sv.ingredient_matching.normalization import _apply_space_normalizations
    except ModuleNotFoundError:
        from app.languages.sv.normalization import fix_swedish_chars
        from app.languages.sv.ingredient_matching.normalization import _apply_space_normalizations

    return _apply_space_normalizations(fix_swedish_chars(value).lower())


def _keyword_synonym_space_norm_warnings(canonical: str, variants: tuple[str, ...]) -> tuple[str, ...]:
    canonical_norm = _space_normalized_keyword_text(canonical)
    entered_variant_terms = {
        _space_normalized_keyword_text(variant) if not re.search(r"[\s-]", variant) else variant.strip().lower()
        for variant in variants
    }
    warnings: list[str] = []
    for variant in variants:
        variant_text = variant.strip().lower()
        if not re.search(r"[\s-]", variant_text):
            continue
        normalized = _space_normalized_keyword_text(variant_text)
        if normalized == variant_text or normalized == canonical_norm or normalized in entered_variant_terms:
            continue
        warnings.append(
            f"variant {variant!r} space-normalizes to {normalized!r}; add {normalized!r} "
            "as a synonym variant too if extraction produces that token."
        )
    return tuple(warnings)


def _text_contains_runtime_term(text: str, term: str) -> bool:
    if not text or not term:
        return False
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) is not None


def _space_normalization_pairs_for_tree(paths: MatcherPaths) -> tuple[tuple[str, str], ...]:
    try:
        from languages.sv.ingredient_matching.normalization import _SPACE_NORMALIZATIONS
    except ModuleNotFoundError:
        from app.languages.sv.ingredient_matching.normalization import _SPACE_NORMALIZATIONS

    pairs: list[tuple[str, str]] = [
        (_runtime_rule_normalize_text(source), _runtime_rule_normalize_text(target))
        for source, target in _SPACE_NORMALIZATIONS
    ]

    sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
    for entry in sections.get("space_normalizations", []):
        if not _runtime_overlay_entry_is_active(entry):
            continue
        source = _runtime_rule_normalize_text(str(entry.get("source", "")))
        target = _runtime_rule_normalize_text(str(entry.get("target", "")))
        if source and target:
            pairs.append((source, target))

    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for source, target in pairs:
        key = (source, target)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return tuple(deduped)


def _runtime_space_norm_compound_warnings(
    *,
    paths: MatcherPaths,
    surface: RuntimeOverlaySurface,
    keyword: str,
    values: tuple[str, ...],
) -> tuple[str, ...]:
    if surface.command not in {"pnb", "fpb", "ksbc"}:
        return ()

    normalized_keyword = _runtime_rule_normalize_text(keyword)
    normalized_values = tuple(_runtime_rule_normalize_text(value) for value in values)
    value_set = set(normalized_values)
    sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
    existing_values = (
        _runtime_overlay_existing_values(sections, surface, keyword)
        | _live_runtime_mapping_values(surface, keyword, paths)
        | value_set
    )

    warnings: list[str] = []
    for source, target in _space_normalization_pairs_for_tree(paths):
        if source == target or not source or not target:
            continue
        if re.search(r"[\s-]", target):
            continue
        if target in existing_values:
            continue
        if not _text_contains_runtime_term(source, normalized_keyword):
            continue
        matched_values = [
            value for value in normalized_values
            if value != target and _text_contains_runtime_term(source, value)
        ]
        if not matched_values:
            continue
        warnings.append(
            "space-normalization joins "
            f"{source!r} -> {target!r}; {surface.command} {surface.value_field} "
            f"{', '.join(repr(value) for value in matched_values)} may not fire on the joined form. "
            f"Add {target!r} too if this rule must block that compound."
        )
    return tuple(warnings)


def _runtime_fpb_smart_blocker_warning(surface: RuntimeOverlaySurface, keyword: str) -> tuple[str, ...]:
    if surface.command != "fpb":
        return ()
    normalized_keyword = _runtime_rule_normalize_text(keyword)
    if not normalized_keyword:
        return ()
    return (
        "FPB can be bypassed when the recipe ingredient contains "
        f"{normalized_keyword!r} as its own word; use "
        f"`dm matcher probe --expect no-match ...` after authoring, and prefer KSBC "
        "when recipe-side context should suppress a generic standalone keyword.",
    )


def _emit_runtime_authoring_warnings(warnings: tuple[str, ...]) -> None:
    for warning in warnings:
        typer.secho(f"Warning: {warning}", fg=typer.colors.YELLOW, err=True)


def _runtime_mapping_effective_values(
    *,
    paths: MatcherPaths,
    surface: RuntimeOverlaySurface,
    keyword: str,
) -> set[str]:
    sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
    return (
        _runtime_overlay_existing_values(sections, surface, keyword)
        | _live_runtime_mapping_values(surface, keyword, paths)
    )


def _format_warning_values(values: Iterable[str], *, limit: int = 10) -> str:
    sorted_values = sorted({_runtime_rule_normalize_text(value) for value in values if str(value).strip()})
    shown = sorted_values[:limit]
    suffix = f", ... (+{len(sorted_values) - limit})" if len(sorted_values) > limit else ""
    return ", ".join(shown) + suffix


def _ingredient_parent_pnb_mirror_warnings(
    *,
    paths: MatcherPaths,
    canonical_targets: tuple[str, ...],
    variants: tuple[str, ...],
) -> tuple[str, ...]:
    pnb_surface = RUNTIME_OVERLAY_SURFACES["pnb"]
    warnings: list[str] = []
    for parent in canonical_targets:
        parent_blockers = _runtime_mapping_effective_values(
            paths=paths,
            surface=pnb_surface,
            keyword=parent,
        )
        if not parent_blockers:
            continue
        for variant in variants:
            variant_blockers = _runtime_mapping_effective_values(
                paths=paths,
                surface=pnb_surface,
                keyword=variant,
            )
            missing_blockers = parent_blockers - variant_blockers
            if not missing_blockers:
                continue
            blockers_preview = _format_warning_values(missing_blockers)
            blockers_csv = ",".join(sorted(missing_blockers))
            warnings.append(
                f"ingredient-parent maps {variant!r} -> {parent!r}, but PNB lookup does not "
                f"inherit parent blockers. Missing child blockers: {blockers_preview}. "
                f"Consider: ./bin/dm matcher add pnb {variant} --blockers {blockers_csv} "
                '--reason "<why>"'
            )
    return tuple(warnings)


def _runtime_overlay_value_field(section: str) -> str:
    for surface in RUNTIME_OVERLAY_SURFACES.values():
        if surface.section == section:
            return surface.value_field
    raise typer.BadParameter(f"unknown runtime overlay section: {section}")


def _read_runtime_overlay_sections(path: Path) -> dict[str, list[dict[str, Any]]]:
    try:
        from languages.sv.ingredient_matching.runtime_rule_overlays import load_runtime_rule_overlays
    except ModuleNotFoundError:
        from app.languages.sv.ingredient_matching.runtime_rule_overlays import load_runtime_rule_overlays

    try:
        load_runtime_rule_overlays(path)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if not path.exists():
        return {section: [] for section in _RUNTIME_OVERLAY_SECTION_ORDER}
    with path.open("rb") as handle:
        payload = tomllib.load(handle)
    return {
        section: [dict(entry) for entry in payload.get(section, [])]
        for section in _RUNTIME_OVERLAY_SECTION_ORDER
    }


def _runtime_overlay_entry_values(entry: dict[str, Any], value_field: str) -> tuple[str, ...]:
    raw_values = entry.get(value_field, [])
    return tuple(_runtime_rule_normalize_text(str(value)) for value in raw_values)


def _runtime_overlay_entry_is_active(entry: dict[str, Any]) -> bool:
    return str(entry.get("status", "active")).strip().lower() != "inactive"


def _runtime_overlay_entry_id(surface: RuntimeOverlaySurface, keyword: str) -> str:
    return f"runtime_{surface.command.replace('-', '_')}_{_slug(keyword)}"


def _runtime_pair_entry_id(surface: RuntimePairSurface, source: str, target: str) -> str:
    command_slug = surface.command.replace("-", "_")
    return f"runtime_{command_slug}_{_slug(source)}_{_slug(target)}"


def _runtime_pair_entry_id_with_collision_suffix(
    surface: RuntimePairSurface,
    source: str,
    target: str,
    sections: dict[str, list[dict[str, Any]]],
) -> str:
    entry_id = _runtime_pair_entry_id(surface, source, target)
    existing_ids = {
        str(entry.get("id") or "").strip()
        for entry in sections.get(surface.section, [])
        if str(entry.get("id") or "").strip()
    }
    if entry_id not in existing_ids:
        return entry_id
    digest = hashlib.sha256(f"{surface.command}\0{source}\0{target}".encode("utf-8")).hexdigest()[:10]
    disambiguated = f"{entry_id}_{digest}"
    if disambiguated not in existing_ids:
        return disambiguated
    suffix = 2
    while f"{disambiguated}_{suffix}" in existing_ids:
        suffix += 1
    return f"{disambiguated}_{suffix}"


def _runtime_overlay_existing_values(
    sections: dict[str, list[dict[str, Any]]],
    surface: RuntimeOverlaySurface,
    keyword: str,
) -> set[str]:
    normalized_keyword = _runtime_rule_normalize_text(keyword)
    values: set[str] = set()
    for entry in sections.get(surface.section, []):
        if not _runtime_overlay_entry_is_active(entry):
            continue
        entry_keyword = str(entry.get("keyword", "")).strip()
        if _runtime_rule_normalize_text(entry_keyword) != normalized_keyword:
            continue
        values.update(
            _runtime_rule_normalize_text(value)
            for value in _runtime_overlay_entry_values(entry, surface.value_field)
        )
    return values


def _live_runtime_mapping_values(surface: RuntimeOverlaySurface, keyword: str, paths: MatcherPaths) -> set[str]:
    if paths.app_dir != APP_DIR:
        return set()
    normalized_keyword = _runtime_rule_normalize_text(keyword)
    if surface.command == "pnb":
        from languages.sv.ingredient_matching.blocker_data import PRODUCT_NAME_BLOCKERS

        return set(PRODUCT_NAME_BLOCKERS.get(normalized_keyword, set()))
    if surface.command == "fpb":
        from languages.sv.ingredient_matching.blocker_data import FALSE_POSITIVE_BLOCKERS

        return set(FALSE_POSITIVE_BLOCKERS.get(normalized_keyword, set()))
    if surface.command == "ksbc":
        from languages.sv.ingredient_matching.carrier_context import KEYWORD_SUPPRESSED_BY_CONTEXT

        return set(KEYWORD_SUPPRESSED_BY_CONTEXT.get(normalized_keyword, set()))
    if surface.command == "processed-rule":
        from languages.sv.ingredient_matching.processed_rules import PROCESSED_PRODUCT_RULES

        return set(PROCESSED_PRODUCT_RULES.get(normalized_keyword, set()))
    if surface.command == "processed-exemption":
        from languages.sv.ingredient_matching.processed_rules import PROCESSED_RULES_COMPOUND_EXEMPTIONS

        return set(PROCESSED_RULES_COMPOUND_EXEMPTIONS.get(normalized_keyword, set()))
    return set()


def _runtime_overlay_entry_block(surface: RuntimeOverlaySurface, entry: dict[str, Any]) -> str:
    lines = [f"[[{surface.section}]]"]
    if "id" in entry:
        lines.append(f"id = {_toml_string(str(entry['id']))}")
    if "status" in entry:
        lines.append(f"status = {_toml_string(str(entry['status']))}")
    lines.extend([
        f"keyword = {_toml_string(str(entry['keyword']))}",
        f"{surface.value_field} = {_toml_array(list(entry[surface.value_field]))}",
        f"reason = {_toml_string(str(entry['reason']))}",
    ])
    if "inactive_reason" in entry:
        lines.append(f"inactive_reason = {_toml_string(str(entry['inactive_reason']))}")
    lines.append("")
    return "\n".join(lines)


def _runtime_pair_entry_block(surface: RuntimePairSurface, entry: dict[str, Any]) -> str:
    lines = [f"[[{surface.section}]]"]
    if "id" in entry:
        lines.append(f"id = {_toml_string(str(entry['id']))}")
    if "status" in entry:
        lines.append(f"status = {_toml_string(str(entry['status']))}")
    lines.extend([
        f"{surface.source_field} = {_toml_string(str(entry[surface.source_field]))}",
        f"{surface.target_field} = {_toml_string(str(entry[surface.target_field]))}",
        f"reason = {_toml_string(str(entry['reason']))}",
    ])
    if "inactive_reason" in entry:
        lines.append(f"inactive_reason = {_toml_string(str(entry['inactive_reason']))}")
    lines.append("")
    return "\n".join(lines)


def _runtime_set_update_entry_block(entry: dict[str, Any]) -> str:
    lines = [f"[[{entry['section']}]]"]
    if "id" in entry:
        lines.append(f"id = {_toml_string(str(entry['id']))}")
    if "status" in entry:
        lines.append(f"status = {_toml_string(str(entry['status']))}")
    lines.extend([
        f"surface = {_toml_string(str(entry['surface']))}",
        f"action = {_toml_string(str(entry['action']))}",
        f"terms = {_toml_array(list(entry['terms']))}",
        f"reason = {_toml_string(str(entry['reason']))}",
    ])
    if "inactive_reason" in entry:
        lines.append(f"inactive_reason = {_toml_string(str(entry['inactive_reason']))}")
    lines.append("")
    return "\n".join(lines)


def _runtime_term_set_entry_block(surface: RuntimeTermSetSurface, entry: dict[str, Any]) -> str:
    lines = [f"[[{surface.section}]]"]
    if "id" in entry:
        lines.append(f"id = {_toml_string(str(entry['id']))}")
    if "status" in entry:
        lines.append(f"status = {_toml_string(str(entry['status']))}")
    lines.extend([
        f"{surface.value_field} = {_toml_array(list(entry[surface.value_field]))}",
        f"reason = {_toml_string(str(entry['reason']))}",
    ])
    if "inactive_reason" in entry:
        lines.append(f"inactive_reason = {_toml_string(str(entry['inactive_reason']))}")
    lines.append("")
    return "\n".join(lines)


def _runtime_context_entry_block(surface: RuntimeContextSurface, entry: dict[str, Any]) -> str:
    lines = [f"[[{surface.section}]]"]
    if "id" in entry:
        lines.append(f"id = {_toml_string(str(entry['id']))}")
    if "status" in entry:
        lines.append(f"status = {_toml_string(str(entry['status']))}")
    lines.extend([
        f"{surface.key_field} = {_toml_string(str(entry[surface.key_field]))}",
        f"{surface.values_field} = {_toml_array(list(entry[surface.values_field]))}",
        f"reason = {_toml_string(str(entry['reason']))}",
    ])
    if "inactive_reason" in entry:
        lines.append(f"inactive_reason = {_toml_string(str(entry['inactive_reason']))}")
    lines.append("")
    return "\n".join(lines)


def _runtime_compound_entry_block(surface: RuntimeCompoundSurface, entry: dict[str, Any]) -> str:
    lines = [f"[[{surface.section}]]"]
    if "id" in entry:
        lines.append(f"id = {_toml_string(str(entry['id']))}")
    if "status" in entry:
        lines.append(f"status = {_toml_string(str(entry['status']))}")
    lines.extend([
        f"mode = {_toml_string(str(entry['mode']))}",
        f"keywords = {_toml_array(list(entry['keywords']))}",
        f"reason = {_toml_string(str(entry['reason']))}",
    ])
    if "inactive_reason" in entry:
        lines.append(f"inactive_reason = {_toml_string(str(entry['inactive_reason']))}")
    lines.append("")
    return "\n".join(lines)


def _runtime_specialty_entry_block(surface: RuntimeSpecialtySurface, entry: dict[str, Any]) -> str:
    lines = [f"[[{surface.section}]]"]
    if "id" in entry:
        lines.append(f"id = {_toml_string(str(entry['id']))}")
    if "status" in entry:
        lines.append(f"status = {_toml_string(str(entry['status']))}")
    lines.append(f"{surface.key_field} = {_toml_string(str(entry[surface.key_field]))}")
    lines.append(f"{surface.values_field} = {_toml_array(list(entry[surface.values_field]))}")
    if surface.section == "specialty_qualifiers":
        lines.append(f"bidirectional = {'true' if bool(entry.get('bidirectional', False)) else 'false'}")
    lines.append(f"reason = {_toml_string(str(entry['reason']))}")
    if "inactive_reason" in entry:
        lines.append(f"inactive_reason = {_toml_string(str(entry['inactive_reason']))}")
    lines.append("")
    return "\n".join(lines)


def _runtime_product_substitution_entry_block(entry: dict[str, Any]) -> str:
    lines = ["[[product_name_substitutions]]"]
    if "id" in entry:
        lines.append(f"id = {_toml_string(str(entry['id']))}")
    if "status" in entry:
        lines.append(f"status = {_toml_string(str(entry['status']))}")
    lines.extend([
        f"required_words = {_toml_array(list(entry['required_words']))}",
        f"old_keyword = {_toml_string(str(entry['old_keyword']))}",
        f"new_keyword = {_toml_string(str(entry['new_keyword']))}",
        f"reason = {_toml_string(str(entry['reason']))}",
    ])
    if "inactive_reason" in entry:
        lines.append(f"inactive_reason = {_toml_string(str(entry['inactive_reason']))}")
    lines.append("")
    return "\n".join(lines)


def _runtime_secondary_pattern_entry_block(entry: dict[str, Any]) -> str:
    lines = ["[[secondary_ingredient_patterns]]"]
    if "id" in entry:
        lines.append(f"id = {_toml_string(str(entry['id']))}")
    if "status" in entry:
        lines.append(f"status = {_toml_string(str(entry['status']))}")
    lines.extend([
        f"keyword = {_toml_string(str(entry['keyword']))}",
        f"blockers = {_toml_array(list(entry['blockers']))}",
    ])
    if entry.get("exceptions"):
        lines.append(f"exceptions = {_toml_array(list(entry['exceptions']))}")
    lines.append(f"reason = {_toml_string(str(entry['reason']))}")
    if "inactive_reason" in entry:
        lines.append(f"inactive_reason = {_toml_string(str(entry['inactive_reason']))}")
    lines.append("")
    return "\n".join(lines)


def _runtime_spice_fresh_entry_block(entry: dict[str, Any]) -> str:
    lines = ["[[spice_fresh_rules]]"]
    if "id" in entry:
        lines.append(f"id = {_toml_string(str(entry['id']))}")
    if "status" in entry:
        lines.append(f"status = {_toml_string(str(entry['status']))}")
    lines.append(f"keyword = {_toml_string(str(entry['keyword']))}")
    for field in _SPICE_FRESH_RULE_FIELDS:
        if entry.get(field):
            lines.append(f"{field} = {_toml_array(list(entry[field]))}")
    lines.append(f"reason = {_toml_string(str(entry['reason']))}")
    if "inactive_reason" in entry:
        lines.append(f"inactive_reason = {_toml_string(str(entry['inactive_reason']))}")
    lines.append("")
    return "\n".join(lines)


def _runtime_overlay_file_text(sections: dict[str, list[dict[str, Any]]]) -> str:
    lines = [
        "# CLI-managed Track A runtime-rule overlays.",
        "#",
        "# This file is tracked production source. Add entries through:",
        "#   ./bin/dm matcher add pnb|fpb|ksbc ...",
        "#",
        "# New CLI entries use id/status metadata. Statusless entries are treated as active",
        "# only for backwards compatibility; do not append statusless rows manually.",
        "#",
        "# Supported sections:",
        "#   [[product_name_blockers]]",
        "#   [[false_positive_blockers]]",
        "#   [[keyword_suppressed_by_context]]",
        "#   [[processed_product_rules]]",
        "#   [[processed_rule_compound_exemptions]]",
        "#   [[global_product_name_blockers]]",
        "#   [[strict_processed_rules]]",
        "#   [[carrier_context_required]]",
        "#   [[context_required_words]]",
        "#   [[ingredient_requires_in_product]]",
        "#   [[space_normalizations]]",
        "#   [[keyword_set_updates]]",
        "#   [[carrier_set_updates]]",
        "#   [[cuisine_context]]",
        "#   [[context_word_keyword_exemptions]]",
        "#   [[compound_protection_updates]]",
        "#   [[specialty_qualifiers]]",
        "#   [[qualifier_equivalents]]",
        "#   [[spice_fresh_rules]]",
        "#   [[product_name_substitutions]]",
        "#   [[secondary_ingredient_patterns]]",
        "",
    ]
    mapping_by_section = {surface.section: surface for surface in RUNTIME_OVERLAY_SURFACES.values()}
    term_set_by_section = {surface.section: surface for surface in RUNTIME_TERM_SET_SURFACES.values()}
    pair_by_section = {surface.section: surface for surface in RUNTIME_PAIR_SURFACES.values()}
    context_by_section = {surface.section: surface for surface in RUNTIME_CONTEXT_SURFACES.values()}
    compound_by_section = {surface.section: surface for surface in RUNTIME_COMPOUND_SURFACES.values()}
    specialty_by_section = {surface.section: surface for surface in RUNTIME_SPECIALTY_SURFACES.values()}
    for section in _RUNTIME_OVERLAY_SECTION_ORDER:
        for entry in sections.get(section, []):
            if section in mapping_by_section:
                lines.append(_runtime_overlay_entry_block(mapping_by_section[section], entry).rstrip())
            elif section in term_set_by_section:
                lines.append(_runtime_term_set_entry_block(term_set_by_section[section], entry).rstrip())
            elif section in pair_by_section:
                lines.append(_runtime_pair_entry_block(pair_by_section[section], entry).rstrip())
            elif section in {"keyword_set_updates", "carrier_set_updates"}:
                lines.append(_runtime_set_update_entry_block({"section": section, **entry}).rstrip())
            elif section in context_by_section:
                lines.append(_runtime_context_entry_block(context_by_section[section], entry).rstrip())
            elif section in compound_by_section:
                lines.append(_runtime_compound_entry_block(compound_by_section[section], entry).rstrip())
            elif section in specialty_by_section:
                lines.append(_runtime_specialty_entry_block(specialty_by_section[section], entry).rstrip())
            elif section == "spice_fresh_rules":
                lines.append(_runtime_spice_fresh_entry_block(entry).rstrip())
            elif section == "product_name_substitutions":
                lines.append(_runtime_product_substitution_entry_block(entry).rstrip())
            elif section == "secondary_ingredient_patterns":
                lines.append(_runtime_secondary_pattern_entry_block(entry).rstrip())
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _runtime_overlay_surface_from_arg(surface_name: str) -> RuntimeOverlaySurface:
    key = surface_name.strip().lower().replace("_", "-")
    if key not in RUNTIME_OVERLAY_SURFACES:
        known = ", ".join(sorted(RUNTIME_OVERLAY_SURFACES))
        raise typer.BadParameter(f"unknown runtime overlay surface {surface_name!r}; known: {known}")
    return RUNTIME_OVERLAY_SURFACES[key]


def _runtime_overlay_entry_label(surface: RuntimeOverlaySurface, entry: dict[str, Any]) -> str:
    entry_id = str(entry.get("id") or _runtime_overlay_entry_id(surface, str(entry.get("keyword", ""))))
    status = str(entry.get("status", "active"))
    values = ", ".join(str(value) for value in entry.get(surface.value_field, []))
    return f"{entry_id}\t{status}\t{surface.command}\t{entry.get('keyword', '')} -> {values}"


def _runtime_overlay_matching_entries(
    sections: dict[str, list[dict[str, Any]]],
    surface: RuntimeOverlaySurface,
    selector: str | None,
    *,
    include_inactive: bool,
) -> list[dict[str, Any]]:
    selector_norm = _runtime_rule_normalize_text(selector) if selector is not None else None
    matches: list[dict[str, Any]] = []
    for entry in sections.get(surface.section, []):
        if not include_inactive and not _runtime_overlay_entry_is_active(entry):
            continue
        entry_id = str(entry.get("id") or _runtime_overlay_entry_id(surface, str(entry.get("keyword", ""))))
        keyword = str(entry.get("keyword", ""))
        values = tuple(str(value) for value in entry.get(surface.value_field, []))
        if selector_norm is None:
            matches.append(entry)
            continue
        if selector == entry_id or selector_norm == _runtime_rule_normalize_text(keyword):
            matches.append(entry)
            continue
        if selector_norm in {_runtime_rule_normalize_text(value) for value in values}:
            matches.append(entry)
    return matches


def _find_runtime_overlay_entry_by_id(
    sections: dict[str, list[dict[str, Any]]],
    rule_id: str,
) -> tuple[RuntimeOverlaySurface, dict[str, Any]]:
    rule_id = rule_id.strip()
    if not rule_id:
        raise typer.BadParameter("rule-id must not be empty")
    matches: list[tuple[RuntimeOverlaySurface, dict[str, Any]]] = []
    for surface in RUNTIME_OVERLAY_SURFACES.values():
        for entry in sections.get(surface.section, []):
            if str(entry.get("id") or "").strip() == rule_id:
                matches.append((surface, entry))
    if not matches:
        raise typer.BadParameter(
            f"no runtime-overlay rule with id {rule_id!r}. "
            "Only runtime_rule_overlays.toml entries with an explicit id are supported; "
            "historical base tables are intentionally out of scope."
        )
    if len(matches) > 1:
        labels = "\n".join(_runtime_overlay_entry_label(surface, entry) for surface, entry in matches[:20])
        raise typer.BadParameter(f"rule id {rule_id!r} is ambiguous:\n{labels}")
    return matches[0]


def _runtime_overlay_requested_value_changes(
    *,
    surface: RuntimeOverlaySurface,
    add_value_csv: str | None,
    remove_value_csv: str | None,
    add_blocker_csv: str | None,
    remove_blocker_csv: str | None,
    add_context_csv: str | None,
    remove_context_csv: str | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    add_by_field = {
        "blockers": add_blocker_csv,
        "context": add_context_csv,
    }
    remove_by_field = {
        "blockers": remove_blocker_csv,
        "context": remove_context_csv,
    }
    unsupported_add = [
        field
        for field, value in add_by_field.items()
        if value is not None and field != surface.value_field
    ]
    unsupported_remove = [
        field
        for field, value in remove_by_field.items()
        if value is not None and field != surface.value_field
    ]
    if unsupported_add or unsupported_remove:
        expected = {
            "blockers": "--add-blocker/--remove-blocker",
            "context": "--add-context/--remove-context",
            "blocked_product_words": "--add-value/--remove-value",
            "compounds": "--add-value/--remove-value",
        }.get(surface.value_field, "--add-value/--remove-value")
        wrong = ", ".join(f for f in (*unsupported_add, *unsupported_remove))
        raise typer.BadParameter(
            f"{surface.command} uses {surface.value_field}; {wrong} options do not apply. "
            f"Use {expected}."
        )
    add_values = [
        *_split_optional_csv(add_value_csv, label="--add-value"),
        *_split_optional_csv(add_by_field.get(surface.value_field), label=f"--add-{surface.value_field}"),
    ]
    remove_values = [
        *_split_optional_csv(remove_value_csv, label="--remove-value"),
        *_split_optional_csv(remove_by_field.get(surface.value_field), label=f"--remove-{surface.value_field}"),
    ]
    return (
        tuple(dict.fromkeys(_runtime_rule_normalize_text(value) for value in add_values)),
        tuple(dict.fromkeys(_runtime_rule_normalize_text(value) for value in remove_values)),
    )


def _runtime_overlay_membership_test_matches(
    actual_node: ast.AST,
    *,
    surface: RuntimeOverlaySurface,
    keyword: str,
    values: set[str],
) -> bool:
    if not isinstance(actual_node, ast.Compare):
        return False
    if len(actual_node.ops) != 1 or not isinstance(actual_node.ops[0], ast.In):
        return False
    if len(actual_node.comparators) != 1:
        return False
    value = _literal_string(actual_node.left)
    if value is None or _runtime_rule_normalize_text(value) not in values:
        return False
    comparator = actual_node.comparators[0]
    if not isinstance(comparator, ast.Call):
        return False
    func = comparator.func
    if not isinstance(func, ast.Attribute) or func.attr != "get":
        return False
    if not isinstance(func.value, ast.Name) or func.value.id != surface.mapping_name:
        return False
    if not comparator.args:
        return False
    mapped_keyword = _literal_string(comparator.args[0])
    return mapped_keyword is not None and _runtime_rule_normalize_text(mapped_keyword) == keyword


def _remove_empty_generated_sanity_blocks(text: str) -> tuple[str, int]:
    lines = text.splitlines(keepends=True)
    starts = [
        index
        for index, line in enumerate(lines)
        if _GENERATED_SANITY_COMMENT_RE.match(line.strip())
    ]
    if not starts:
        return text, 0
    final_summary = next(
        (index for index, line in enumerate(lines) if line.startswith(DEEP_SANITY_FINAL_SUMMARY_MARKER)),
        len(lines),
    )
    ranges: list[tuple[int, int]] = []
    for position, start in enumerate(starts):
        next_start = starts[position + 1] if position + 1 < len(starts) else len(lines)
        end = min(next_start, final_summary if final_summary > start else next_start)
        has_test = any(line.lstrip().startswith("test(") for line in lines[start:end])
        if not has_test:
            remove_start = start
            if remove_start > 0 and not lines[remove_start - 1].strip():
                remove_start -= 1
            while end < len(lines) and not lines[end].strip() and end < final_summary:
                end += 1
            ranges.append((remove_start, end))
    if not ranges:
        return text, 0
    keep = [True] * len(lines)
    for start, end in ranges:
        for index in range(start, end):
            keep[index] = False
    return "".join(line for index, line in enumerate(lines) if keep[index]), len(ranges)


def _remove_runtime_overlay_sanity_membership_tests(
    *,
    paths: MatcherPaths,
    surface: RuntimeOverlaySurface,
    keyword: str,
    values: tuple[str, ...],
    dry_run: bool,
) -> int:
    if not values or not paths.deep_sanity_file.exists():
        return 0
    keyword = _runtime_rule_normalize_text(keyword)
    value_set = {_runtime_rule_normalize_text(value) for value in values}
    text = paths.deep_sanity_file.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(paths.deep_sanity_file))
    metadata_by_line = _deep_sanity_metadata_by_line(text)
    remove_lines: set[int] = set()
    removed_tests = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "test":
            continue
        if len(node.args) < 3 or not metadata_by_line.get(node.lineno, {}).get("policy_ref"):
            continue
        expected = node.args[2]
        if not isinstance(expected, ast.Constant) or expected.value is not True:
            continue
        if not _runtime_overlay_membership_test_matches(
            node.args[1],
            surface=surface,
            keyword=keyword,
            values=value_set,
        ):
            continue
        end_lineno = getattr(node, "end_lineno", node.lineno)
        remove_lines.update(range(node.lineno, end_lineno + 1))
        removed_tests += 1

    if not remove_lines:
        return 0
    lines = text.splitlines(keepends=True)
    new_text = "".join(
        line
        for line_number, line in enumerate(lines, start=1)
        if line_number not in remove_lines
    )
    new_text, _removed_blocks = _remove_empty_generated_sanity_blocks(new_text)
    if not dry_run:
        paths.deep_sanity_file.write_text(new_text, encoding="utf-8")
    return removed_tests


def _runtime_pair_entry_label(surface: RuntimePairSurface, entry: dict[str, Any]) -> str:
    source = str(entry.get(surface.source_field, ""))
    target = str(entry.get(surface.target_field, ""))
    entry_id = str(entry.get("id") or _runtime_pair_entry_id(surface, source, target))
    status = str(entry.get("status", "active"))
    return f"{entry_id}\t{status}\t{surface.command}\t{source} -> {target}"


def _runtime_pair_matching_entries(
    sections: dict[str, list[dict[str, Any]]],
    surface: RuntimePairSurface,
    selector: str | None,
    *,
    include_inactive: bool,
) -> list[dict[str, Any]]:
    selector_norm = _runtime_rule_normalize_text(selector) if selector is not None else None
    matches: list[dict[str, Any]] = []
    for entry in sections.get(surface.section, []):
        if not include_inactive and not _runtime_overlay_entry_is_active(entry):
            continue
        source = str(entry.get(surface.source_field, ""))
        target = str(entry.get(surface.target_field, ""))
        entry_id = str(entry.get("id") or _runtime_pair_entry_id(surface, source, target))
        if selector_norm is None:
            matches.append(entry)
            continue
        if selector == entry_id:
            matches.append(entry)
            continue
        if selector_norm in {
            _runtime_rule_normalize_text(source),
            _runtime_rule_normalize_text(target),
        }:
            matches.append(entry)
    return matches


def _runtime_set_update_entry_id(surface: RuntimeSetUpdateSurface, action: str, terms: tuple[str, ...]) -> str:
    term_slug = "_".join(_slug(term) for term in terms[:3])
    return f"runtime_{surface.command.replace('-', '_')}_{action}_{term_slug}"


def _runtime_set_update_entry_label(surface: RuntimeSetUpdateSurface, entry: dict[str, Any]) -> str:
    action = str(entry.get("action", surface.default_action))
    terms = tuple(str(term) for term in entry.get("terms", []))
    entry_id = str(entry.get("id") or _runtime_set_update_entry_id(surface, action, terms))
    status = str(entry.get("status", "active"))
    return f"{entry_id}\t{status}\t{surface.command}\t{action}\t{', '.join(terms)}"


def _runtime_set_update_matching_entries(
    sections: dict[str, list[dict[str, Any]]],
    surface: RuntimeSetUpdateSurface,
    selector: str | None,
    *,
    include_inactive: bool,
) -> list[dict[str, Any]]:
    selector_norm = _runtime_rule_normalize_text(selector) if selector is not None else None
    matches: list[dict[str, Any]] = []
    for entry in sections.get(surface.section, []):
        if str(entry.get("surface", "")).replace("-", "_") != surface.surface:
            continue
        if not include_inactive and not _runtime_overlay_entry_is_active(entry):
            continue
        action = str(entry.get("action", surface.default_action))
        terms = tuple(str(term) for term in entry.get("terms", []))
        entry_id = str(entry.get("id") or _runtime_set_update_entry_id(surface, action, terms))
        if selector_norm is None:
            matches.append(entry)
            continue
        if selector == entry_id:
            matches.append(entry)
            continue
        if selector_norm in {_runtime_rule_normalize_text(term) for term in terms}:
            matches.append(entry)
    return matches


def _runtime_term_set_entry_id(surface: RuntimeTermSetSurface, terms: tuple[str, ...]) -> str:
    term_slug = "_".join(_slug(term) for term in terms[:3])
    return f"runtime_{surface.command.replace('-', '_')}_{term_slug}"


def _runtime_term_set_entry_label(surface: RuntimeTermSetSurface, entry: dict[str, Any]) -> str:
    terms = tuple(str(term) for term in entry.get(surface.value_field, []))
    entry_id = str(entry.get("id") or _runtime_term_set_entry_id(surface, terms))
    status = str(entry.get("status", "active"))
    return f"{entry_id}\t{status}\t{surface.command}\t{', '.join(terms)}"


def _runtime_term_set_matching_entries(
    sections: dict[str, list[dict[str, Any]]],
    surface: RuntimeTermSetSurface,
    selector: str | None,
    *,
    include_inactive: bool,
) -> list[dict[str, Any]]:
    selector_norm = _runtime_rule_normalize_text(selector) if selector is not None else None
    matches: list[dict[str, Any]] = []
    for entry in sections.get(surface.section, []):
        if not include_inactive and not _runtime_overlay_entry_is_active(entry):
            continue
        terms = tuple(str(term) for term in entry.get(surface.value_field, []))
        entry_id = str(entry.get("id") or _runtime_term_set_entry_id(surface, terms))
        if selector_norm is None:
            matches.append(entry)
            continue
        if selector == entry_id:
            matches.append(entry)
            continue
        if selector_norm in {_runtime_rule_normalize_text(term) for term in terms}:
            matches.append(entry)
    return matches


def _runtime_context_entry_id(surface: RuntimeContextSurface, key: str) -> str:
    return f"runtime_{surface.command.replace('-', '_')}_{_slug(key)}"


def _runtime_context_entry_label(surface: RuntimeContextSurface, entry: dict[str, Any]) -> str:
    key = str(entry.get(surface.key_field, ""))
    entry_id = str(entry.get("id") or _runtime_context_entry_id(surface, key))
    status = str(entry.get("status", "active"))
    values = ", ".join(str(value) for value in entry.get(surface.values_field, []))
    return f"{entry_id}\t{status}\t{surface.command}\t{key} -> {values}"


def _runtime_context_matching_entries(
    sections: dict[str, list[dict[str, Any]]],
    surface: RuntimeContextSurface,
    selector: str | None,
    *,
    include_inactive: bool,
) -> list[dict[str, Any]]:
    selector_norm = _runtime_rule_normalize_text(selector) if selector is not None else None
    matches: list[dict[str, Any]] = []
    for entry in sections.get(surface.section, []):
        if not include_inactive and not _runtime_overlay_entry_is_active(entry):
            continue
        key = str(entry.get(surface.key_field, ""))
        values = tuple(str(value) for value in entry.get(surface.values_field, []))
        entry_id = str(entry.get("id") or _runtime_context_entry_id(surface, key))
        if selector_norm is None:
            matches.append(entry)
            continue
        if selector == entry_id or selector_norm == _runtime_rule_normalize_text(key):
            matches.append(entry)
            continue
        if selector_norm in {_runtime_rule_normalize_text(value) for value in values}:
            matches.append(entry)
    return matches


def _runtime_compound_entry_id(surface: RuntimeCompoundSurface, mode: str, keywords: tuple[str, ...]) -> str:
    keyword_slug = "_".join(_slug(keyword) for keyword in keywords[:3])
    return f"runtime_{surface.command.replace('-', '_')}_{mode}_{keyword_slug}"


def _runtime_compound_entry_label(surface: RuntimeCompoundSurface, entry: dict[str, Any]) -> str:
    mode = str(entry.get("mode", ""))
    keywords = tuple(str(keyword) for keyword in entry.get("keywords", []))
    entry_id = str(entry.get("id") or _runtime_compound_entry_id(surface, mode, keywords))
    status = str(entry.get("status", "active"))
    return f"{entry_id}\t{status}\t{surface.command}\t{mode}\t{', '.join(keywords)}"


def _runtime_compound_matching_entries(
    sections: dict[str, list[dict[str, Any]]],
    surface: RuntimeCompoundSurface,
    selector: str | None,
    *,
    include_inactive: bool,
) -> list[dict[str, Any]]:
    selector_norm = _runtime_rule_normalize_text(selector) if selector is not None else None
    matches: list[dict[str, Any]] = []
    for entry in sections.get(surface.section, []):
        if not include_inactive and not _runtime_overlay_entry_is_active(entry):
            continue
        mode = str(entry.get("mode", ""))
        keywords = tuple(str(keyword) for keyword in entry.get("keywords", []))
        entry_id = str(entry.get("id") or _runtime_compound_entry_id(surface, mode, keywords))
        if selector_norm is None:
            matches.append(entry)
            continue
        if selector == entry_id or selector_norm == mode:
            matches.append(entry)
            continue
        if selector_norm in {_runtime_rule_normalize_text(keyword) for keyword in keywords}:
            matches.append(entry)
    return matches


def _runtime_specialty_entry_id(surface: RuntimeSpecialtySurface, key: str, values: tuple[str, ...]) -> str:
    value_slug = "_".join(_slug(value) for value in values[:2])
    return f"runtime_{surface.command.replace('-', '_')}_{_slug(key)}_{value_slug}"


def _runtime_specialty_entry_label(surface: RuntimeSpecialtySurface, entry: dict[str, Any]) -> str:
    key = str(entry.get(surface.key_field, ""))
    values = tuple(str(value) for value in entry.get(surface.values_field, []))
    entry_id = str(entry.get("id") or _runtime_specialty_entry_id(surface, key, values))
    status = str(entry.get("status", "active"))
    suffix = "\tbidirectional" if entry.get("bidirectional") else ""
    return f"{entry_id}\t{status}\t{surface.command}\t{key} -> {', '.join(values)}{suffix}"


def _runtime_specialty_matching_entries(
    sections: dict[str, list[dict[str, Any]]],
    surface: RuntimeSpecialtySurface,
    selector: str | None,
    *,
    include_inactive: bool,
) -> list[dict[str, Any]]:
    selector_norm = _runtime_rule_normalize_text(selector) if selector is not None else None
    matches: list[dict[str, Any]] = []
    for entry in sections.get(surface.section, []):
        if not include_inactive and not _runtime_overlay_entry_is_active(entry):
            continue
        key = str(entry.get(surface.key_field, ""))
        values = tuple(str(value) for value in entry.get(surface.values_field, []))
        entry_id = str(entry.get("id") or _runtime_specialty_entry_id(surface, key, values))
        if selector_norm is None:
            matches.append(entry)
            continue
        if selector == entry_id or selector_norm == _runtime_rule_normalize_text(key):
            matches.append(entry)
            continue
        if selector_norm in {_runtime_rule_normalize_text(value) for value in values}:
            matches.append(entry)
    return matches


def _runtime_product_substitution_entry_id(required_words: tuple[str, ...], old_keyword: str, new_keyword: str) -> str:
    required_slug = "_".join(_slug(word) for word in required_words[:3])
    return f"runtime_product_name_substitution_{_slug(old_keyword)}_{_slug(new_keyword)}_{required_slug}"


def _runtime_product_substitution_entry_label(entry: dict[str, Any]) -> str:
    required_words = tuple(str(word) for word in entry.get("required_words", []))
    old_keyword = str(entry.get("old_keyword", ""))
    new_keyword = str(entry.get("new_keyword", ""))
    entry_id = str(entry.get("id") or _runtime_product_substitution_entry_id(required_words, old_keyword, new_keyword))
    status = str(entry.get("status", "active"))
    return f"{entry_id}\t{status}\tproduct-name-substitution\t{sorted(required_words)}\t{old_keyword} -> {new_keyword}"


def _runtime_product_substitution_matching_entries(
    sections: dict[str, list[dict[str, Any]]],
    selector: str | None,
    *,
    include_inactive: bool,
) -> list[dict[str, Any]]:
    selector_norm = _runtime_rule_normalize_text(selector) if selector is not None else None
    matches: list[dict[str, Any]] = []
    for entry in sections.get("product_name_substitutions", []):
        if not include_inactive and not _runtime_overlay_entry_is_active(entry):
            continue
        required_words = tuple(str(word) for word in entry.get("required_words", []))
        old_keyword = str(entry.get("old_keyword", ""))
        new_keyword = str(entry.get("new_keyword", ""))
        entry_id = str(entry.get("id") or _runtime_product_substitution_entry_id(required_words, old_keyword, new_keyword))
        if selector_norm is None:
            matches.append(entry)
            continue
        if selector == entry_id:
            matches.append(entry)
            continue
        searchable = {
            _runtime_rule_normalize_text(old_keyword),
            _runtime_rule_normalize_text(new_keyword),
            *(_runtime_rule_normalize_text(word) for word in required_words),
        }
        if selector_norm in searchable:
            matches.append(entry)
    return matches


def _runtime_secondary_pattern_entry_id(keyword: str) -> str:
    return f"runtime_secondary_ingredient_pattern_{_slug(keyword)}"


def _runtime_secondary_pattern_entry_label(entry: dict[str, Any]) -> str:
    keyword = str(entry.get("keyword", ""))
    blockers = ", ".join(str(value) for value in entry.get("blockers", []))
    exceptions = ", ".join(str(value) for value in entry.get("exceptions", []))
    entry_id = str(entry.get("id") or _runtime_secondary_pattern_entry_id(keyword))
    status = str(entry.get("status", "active"))
    suffix = f"\texcept {exceptions}" if exceptions else ""
    return f"{entry_id}\t{status}\tsecondary-ingredient-pattern\t{keyword} blocks {blockers}{suffix}"


def _runtime_secondary_pattern_matching_entries(
    sections: dict[str, list[dict[str, Any]]],
    selector: str | None,
    *,
    include_inactive: bool,
) -> list[dict[str, Any]]:
    selector_norm = _runtime_rule_normalize_text(selector) if selector is not None else None
    matches: list[dict[str, Any]] = []
    for entry in sections.get("secondary_ingredient_patterns", []):
        if not include_inactive and not _runtime_overlay_entry_is_active(entry):
            continue
        keyword = str(entry.get("keyword", ""))
        blockers = tuple(str(value) for value in entry.get("blockers", []))
        exceptions = tuple(str(value) for value in entry.get("exceptions", []))
        entry_id = str(entry.get("id") or _runtime_secondary_pattern_entry_id(keyword))
        if selector_norm is None:
            matches.append(entry)
            continue
        if selector == entry_id:
            matches.append(entry)
            continue
        searchable = {
            _runtime_rule_normalize_text(keyword),
            *(_runtime_rule_normalize_text(value) for value in blockers),
            *(_runtime_rule_normalize_text(value) for value in exceptions),
        }
        if selector_norm in searchable:
            matches.append(entry)
    return matches


def _runtime_spice_fresh_entry_id(keyword: str) -> str:
    return f"runtime_spice_fresh_rule_{_slug(keyword)}"


def _runtime_spice_fresh_entry_label(entry: dict[str, Any]) -> str:
    keyword = str(entry.get("keyword", ""))
    entry_id = str(entry.get("id") or _runtime_spice_fresh_entry_id(keyword))
    status = str(entry.get("status", "active"))
    parts = []
    for field in _SPICE_FRESH_RULE_FIELDS:
        values = tuple(str(value) for value in entry.get(field, []))
        if values:
            parts.append(f"{field}={','.join(values)}")
    return f"{entry_id}\t{status}\tspice-fresh-rule\t{keyword}\t{'; '.join(parts)}"


def _runtime_spice_fresh_matching_entries(
    sections: dict[str, list[dict[str, Any]]],
    selector: str | None,
    *,
    include_inactive: bool,
) -> list[dict[str, Any]]:
    selector_norm = _runtime_rule_normalize_text(selector) if selector is not None else None
    matches: list[dict[str, Any]] = []
    for entry in sections.get("spice_fresh_rules", []):
        if not include_inactive and not _runtime_overlay_entry_is_active(entry):
            continue
        keyword = str(entry.get("keyword", ""))
        entry_id = str(entry.get("id") or _runtime_spice_fresh_entry_id(keyword))
        if selector_norm is None:
            matches.append(entry)
            continue
        if selector == entry_id:
            matches.append(entry)
            continue
        searchable = {_runtime_rule_normalize_text(keyword)}
        for field in _SPICE_FRESH_RULE_FIELDS:
            searchable.update(_runtime_rule_normalize_text(str(value)) for value in entry.get(field, []))
        if selector_norm in searchable:
            matches.append(entry)
    return matches


def _registry_surface_file(paths: MatcherPaths, surface_name: str) -> tuple[str, Path]:
    file_stem = surface_name.strip().lower().replace("-", "_")
    target = paths.registry_entries_dir / f"{file_stem}.toml"
    if not target.exists():
        known = ", ".join(sorted(path.stem.replace("_", "-") for path in paths.registry_entries_dir.glob("*.toml")))
        raise typer.BadParameter(f"unknown registry surface {surface_name!r}; known: {known}")
    return file_stem.replace("_", "-"), target


def _registry_entry_terms(entry: dict[str, Any]) -> tuple[str, ...]:
    terms: list[str] = []
    for field in (
        "canonical",
        "variants",
        "ingredient_terms",
        "offer_terms",
        "route_terms",
        "blocked_offer_keywords",
        "allowed_specifics",
    ):
        raw = entry.get(field)
        if isinstance(raw, str):
            terms.append(raw)
        elif isinstance(raw, list):
            terms.extend(str(item) for item in raw if isinstance(item, str))
    return tuple(dict.fromkeys(term for term in terms if term.strip()))


def _registry_entry_records(surface: str, path: Path) -> list[RegistryEntryRecord]:
    text = path.read_text(encoding="utf-8")
    starts = [match.start() for match in re.finditer(r"(?m)^\[\[entries\]\]\s*$", text)]
    records: list[RegistryEntryRecord] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        block = text[start:end]
        try:
            payload = tomllib.loads(block)
            entries = payload.get("entries", [])
            entry = entries[0] if isinstance(entries, list) and entries else {}
        except tomllib.TOMLDecodeError as exc:
            raise typer.BadParameter(f"{path}: invalid TOML near entry block {index + 1}: {exc}") from exc
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("entry_id") or "").strip()
        if not entry_id:
            continue
        terms = _registry_entry_terms(entry)
        records.append(RegistryEntryRecord(
            surface=surface,
            entry_id=entry_id,
            status=str(entry.get("status") or "active").strip() or "active",
            canonical=str(entry.get("canonical") or "").strip(),
            terms=terms,
            start=start,
            end=end,
            block=block,
        ))
    return records


def _registry_matching_records(
    records: list[RegistryEntryRecord],
    selector: str | None,
    *,
    include_inactive: bool,
) -> list[RegistryEntryRecord]:
    selector_norm = _runtime_rule_normalize_text(selector) if selector is not None else None
    matches: list[RegistryEntryRecord] = []
    for record in records:
        if not include_inactive and record.status == "inactive":
            continue
        if selector_norm is None:
            matches.append(record)
            continue
        if selector == record.entry_id:
            matches.append(record)
            continue
        if selector_norm in {_runtime_rule_normalize_text(term) for term in record.terms}:
            matches.append(record)
    return matches


def _registry_entry_label(record: RegistryEntryRecord) -> str:
    term_text = ", ".join(record.terms[:6])
    if len(record.terms) > 6:
        term_text += f", ... (+{len(record.terms) - 6})"
    return f"{record.entry_id}\t{record.status}\t{record.surface}\t{record.canonical}\t{term_text}"


def _normalized_mapping_origin_rows(
    *,
    surface: str,
    mapping: Mapping[str, Iterable[str]],
    origin: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for keyword, values in mapping.items():
        normalized_keyword = _runtime_rule_normalize_text(str(keyword))
        for value in values:
            rows.append({
                "surface": surface,
                "keyword": normalized_keyword,
                "value": _runtime_rule_normalize_text(str(value)),
                "origin": origin,
            })
    return rows


def _filter_origin_rows(rows: list[dict[str, str]], selector: str | None) -> list[dict[str, str]]:
    if selector is None:
        return rows
    selector_norm = _runtime_rule_normalize_text(selector)
    return [
        row for row in rows
        if selector_norm in {row["keyword"], row["value"], row["origin"]}
    ]


def _runtime_effective_origin_rows(surface_key: str, selector: str | None) -> list[dict[str, str]] | None:
    rows: list[dict[str, str]] = []
    if surface_key == "pnb":
        from languages.sv.ingredient_matching.blocker_data import (
            PRODUCT_NAME_BLOCKER_CLI_UPDATES,
            _PRODUCT_NAME_BLOCKER_UPDATES,
            _PRODUCT_NAME_BLOCKERS_RAW,
        )

        rows.extend(_normalized_mapping_origin_rows(
            surface="pnb",
            mapping=_PRODUCT_NAME_BLOCKERS_RAW,
            origin="historical_base:_PRODUCT_NAME_BLOCKERS_RAW",
        ))
        rows.extend(_normalized_mapping_origin_rows(
            surface="pnb",
            mapping=_PRODUCT_NAME_BLOCKER_UPDATES,
            origin="historical_update:_PRODUCT_NAME_BLOCKER_UPDATES",
        ))
        rows.extend(_normalized_mapping_origin_rows(
            surface="pnb",
            mapping=PRODUCT_NAME_BLOCKER_CLI_UPDATES,
            origin="runtime_overlay:runtime_rule_overlays.toml",
        ))
        return _filter_origin_rows(rows, selector)
    if surface_key == "fpb":
        from languages.sv.ingredient_matching.blocker_data import (
            FALSE_POSITIVE_BLOCKER_CLI_UPDATES,
            _FALSE_POSITIVE_BLOCKERS_RAW,
        )

        rows.extend(_normalized_mapping_origin_rows(
            surface="fpb",
            mapping=_FALSE_POSITIVE_BLOCKERS_RAW,
            origin="historical_base:_FALSE_POSITIVE_BLOCKERS_RAW",
        ))
        rows.extend(_normalized_mapping_origin_rows(
            surface="fpb",
            mapping=FALSE_POSITIVE_BLOCKER_CLI_UPDATES,
            origin="runtime_overlay:runtime_rule_overlays.toml",
        ))
        return _filter_origin_rows(rows, selector)
    if surface_key == "ksbc":
        from languages.sv.ingredient_matching.carrier_context import KEYWORD_SUPPRESSED_BY_CONTEXT
        from languages.sv.ingredient_matching.runtime_rule_overlays import KEYWORD_SUPPRESSED_BY_CONTEXT_CLI_UPDATES

        overlay_values = {
            (keyword, value)
            for keyword, values in KEYWORD_SUPPRESSED_BY_CONTEXT_CLI_UPDATES.items()
            for value in values
        }
        for row in _normalized_mapping_origin_rows(
            surface="ksbc",
            mapping=KEYWORD_SUPPRESSED_BY_CONTEXT,
            origin="historical_base:KEYWORD_SUPPRESSED_BY_CONTEXT",
        ):
            if (row["keyword"], row["value"]) not in overlay_values:
                rows.append(row)
        rows.extend(_normalized_mapping_origin_rows(
            surface="ksbc",
            mapping=KEYWORD_SUPPRESSED_BY_CONTEXT_CLI_UPDATES,
            origin="runtime_overlay:runtime_rule_overlays.toml",
        ))
        return _filter_origin_rows(rows, selector)
    return None


def _inactive_reason_comment(reason: str) -> str:
    return "# inactive_reason: " + re.sub(r"\s+", " ", reason.strip())


def _registry_entry_block_with_status(block: str, *, status: str, reason: str) -> str:
    cleaned = re.sub(r"(?m)^# inactive_reason: .*\n(?=status\s*=)", "", block)
    status_line = f'status = "{status}"'
    if status == "inactive":
        status_line = f"{_inactive_reason_comment(reason)}\n{status_line}"
    if re.search(r'(?m)^status\s*=\s*"[^"]+"\s*$', cleaned):
        return re.sub(r'(?m)^status\s*=\s*"[^"]+"\s*$', status_line, cleaned, count=1)
    return re.sub(r'(?m)^(canonical\s*=\s*".*"\s*)$', r"\1\n" + status_line, cleaned, count=1)


def _write_registry_entry_block(path: Path, record: RegistryEntryRecord, new_block: str, *, dry_run: bool) -> None:
    if dry_run:
        typer.echo(new_block)
        return
    text = path.read_text(encoding="utf-8")
    path.write_text(text[:record.start] + new_block + text[record.end:], encoding="utf-8")


def _run_track_b_inactivation_gates(paths: MatcherPaths, report_root: Path | None) -> int:
    if _matcher_session_should_defer_gates(paths):
        _echo_session_deferred_gates()
        return 0

    if paths.app_dir != APP_DIR:
        raise typer.BadParameter("tree-root inactivation gates are not available; use --no-run-gates")
    return _run_support_check(
        "run_matcher_change_gates.py",
        [
            "--track",
            "B",
            "--registry-changed",
            "--no-runtime-changed",
            "--no-fixtures-changed",
            "--no-inventory-changed",
            "--no-support-checks-changed",
            "--allow-removals",
        ],
        report_root=report_root,
        cwd=APP_DIR,
    )


def _append_runtime_overlay_entry(
    *,
    paths: MatcherPaths,
    surface: RuntimeOverlaySurface,
    keyword: str,
    values: tuple[str, ...],
    reason: str,
    dry_run: bool,
) -> str:
    sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
    normalized_keyword = _runtime_rule_normalize_text(keyword)
    normalized_values = tuple(_runtime_rule_normalize_text(value) for value in values)
    entry_id = _runtime_overlay_entry_id(surface, normalized_keyword)
    duplicate_values = sorted(
        set(normalized_values)
        & (
            _runtime_overlay_existing_values(sections, surface, keyword)
            | _live_runtime_mapping_values(surface, keyword, paths)
        )
    )
    if duplicate_values:
        raise typer.BadParameter(
            f"{surface.command} already contains {', '.join(duplicate_values)} for {keyword}"
        )

    entry: dict[str, Any] | None = None
    for candidate in sections.get(surface.section, []):
        if _runtime_rule_normalize_text(str(candidate.get("keyword", ""))) == normalized_keyword:
            entry = candidate
            break
    if entry is None:
        entry = {
            "id": entry_id,
            "status": "active",
            "keyword": normalized_keyword,
            surface.value_field: list(normalized_values),
            "reason": reason.strip(),
        }
    else:
        entry["id"] = str(entry.get("id") or entry_id)
        entry["status"] = "active"
        entry.pop("inactive_reason", None)
        existing_values = list(_runtime_overlay_entry_values(entry, surface.value_field))
        existing_value_set = set(existing_values)
        for value in normalized_values:
            if value not in existing_value_set:
                existing_values.append(value)
                existing_value_set.add(value)
        entry["keyword"] = normalized_keyword
        entry[surface.value_field] = existing_values
        existing_reason = str(entry.get("reason", "")).strip()
        if reason.strip() and reason.strip() not in existing_reason:
            entry["reason"] = f"{existing_reason}; {reason.strip()}" if existing_reason else reason.strip()

    preview = _runtime_overlay_entry_block(surface, entry)
    if dry_run:
        return preview

    if entry not in sections.setdefault(surface.section, []):
        sections[surface.section].append(entry)
    paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
    return preview


def _append_runtime_pair_entry(
    *,
    paths: MatcherPaths,
    surface: RuntimePairSurface,
    source: str,
    target: str,
    reason: str,
    dry_run: bool,
) -> tuple[str, str]:
    sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
    normalized_source = _runtime_rule_normalize_text(source)
    normalized_target = _runtime_rule_normalize_text(target)
    entry_id = _runtime_pair_entry_id_with_collision_suffix(
        surface,
        normalized_source,
        normalized_target,
        sections,
    )
    for entry in sections.get(surface.section, []):
        if not _runtime_overlay_entry_is_active(entry):
            continue
        entry_source = _runtime_rule_normalize_text(str(entry.get(surface.source_field, "")))
        entry_target = _runtime_rule_normalize_text(str(entry.get(surface.target_field, "")))
        if entry_source == normalized_source:
            raise typer.BadParameter(
                f"{surface.command} already contains {normalized_source} -> {entry_target}"
            )

    entry = {
        "id": entry_id,
        "status": "active",
        surface.source_field: normalized_source,
        surface.target_field: normalized_target,
        "reason": reason.strip(),
    }
    preview = _runtime_pair_entry_block(surface, entry)
    if dry_run:
        return preview, entry_id

    sections.setdefault(surface.section, []).append(entry)
    paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
    return preview, entry_id


def _append_space_normalization_sanity_stub(
    *,
    paths: MatcherPaths,
    source: str,
    target: str,
    policy_ref: str,
    dry_run: bool,
    command_name: str = "space-normalization",
) -> str:
    normalized_source = _runtime_rule_normalize_text(source)
    normalized_target = _runtime_rule_normalize_text(target)
    lines = [
        "",
        *_generated_sanity_header(policy_ref, command_name),
        f"test({_toml_string(command_name + ' ' + normalized_source + ' -> ' + normalized_target)},",
        f"     _apply_space_normalizations({_toml_string(normalized_source)}), {_toml_string(normalized_target)})",
    ]
    block = "\n".join(lines) + "\n"
    _append_text_block(paths.deep_sanity_file, block, dry_run=dry_run, trim_existing=True)
    return block


def _append_runtime_set_update_entry(
    *,
    paths: MatcherPaths,
    surface: RuntimeSetUpdateSurface,
    terms: tuple[str, ...],
    action: Literal["add", "remove"],
    reason: str,
    dry_run: bool,
) -> str:
    sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
    normalized_terms = tuple(_runtime_rule_normalize_text(term) for term in terms)
    entry_id = _runtime_set_update_entry_id(surface, action, normalized_terms)
    existing_terms: set[str] = set()
    for entry in sections.get(surface.section, []):
        if str(entry.get("surface", "")).replace("-", "_") != surface.surface:
            continue
        if str(entry.get("action", surface.default_action)) != action:
            continue
        if not _runtime_overlay_entry_is_active(entry):
            continue
        existing_terms.update(_runtime_rule_normalize_text(str(term)) for term in entry.get("terms", []))
    if action == "add":
        existing_terms.update(_live_runtime_set_update_values(surface, paths))
    duplicates = sorted(set(normalized_terms) & existing_terms)
    if duplicates:
        raise typer.BadParameter(
            f"{surface.command} already contains {', '.join(duplicates)} for action {action}"
        )

    entry = {
        "id": entry_id,
        "status": "active",
        "surface": surface.surface,
        "action": action,
        "terms": list(normalized_terms),
        "reason": reason.strip(),
    }
    preview = _runtime_set_update_entry_block({"section": surface.section, **entry})
    if dry_run:
        return preview

    sections.setdefault(surface.section, []).append(entry)
    paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
    return preview


def _live_runtime_set_update_values(surface: RuntimeSetUpdateSurface, paths: MatcherPaths) -> set[str]:
    if paths.app_dir != APP_DIR:
        return set()
    if surface.surface == "carrier_products":
        from languages.sv.ingredient_matching.carrier_context import CARRIER_PRODUCTS

        return set(CARRIER_PRODUCTS)
    if surface.surface == "qualifier_required_keywords":
        from languages.sv.ingredient_matching.match_filters import _QUALIFIER_REQUIRED_KEYWORDS

        return set(_QUALIFIER_REQUIRED_KEYWORDS)
    from languages.sv.ingredient_matching.keywords import (
        FLAVOR_WORDS,
        IMPORTANT_SHORT_KEYWORDS,
        NON_FOOD_KEYWORDS,
        PROCESSED_FOODS,
        STOP_WORDS,
    )

    live_sets = {
        "flavor_words": FLAVOR_WORDS,
        "important_short_keywords": IMPORTANT_SHORT_KEYWORDS,
        "non_food_keywords": NON_FOOD_KEYWORDS,
        "processed_foods": PROCESSED_FOODS,
        "stop_words": STOP_WORDS,
    }
    return set(live_sets.get(surface.surface, frozenset()))


def _append_runtime_set_update_sanity_stub(
    *,
    paths: MatcherPaths,
    surface: RuntimeSetUpdateSurface,
    terms: tuple[str, ...],
    action: Literal["add", "remove"],
    policy_ref: str,
    dry_run: bool,
) -> str:
    mapping_name = {
        "flavor_words": "FLAVOR_WORDS",
        "important_short_keywords": "IMPORTANT_SHORT_KEYWORDS",
        "non_food_keywords": "NON_FOOD_KEYWORDS",
        "processed_foods": "PROCESSED_FOODS",
        "qualifier_required_keywords": "_QUALIFIER_REQUIRED_KEYWORDS",
        "stop_words": "STOP_WORDS",
        "carrier_products": "CARRIER_PRODUCTS",
    }[surface.surface]
    import_module = {
        "carrier_products": "languages.sv.ingredient_matching.carrier_context",
        "qualifier_required_keywords": "languages.sv.ingredient_matching.match_filters",
    }.get(surface.surface, "languages.sv.ingredient_matching.keywords")
    expected = "True" if action == "add" else "False"
    lines = [
        "",
        *_generated_sanity_header(policy_ref, surface.command),
        f"from {import_module} import {mapping_name}",
    ]
    for term in terms:
        normalized_term = _runtime_rule_normalize_text(term)
        lines.extend([
            f"test({_toml_string(surface.command + ' ' + action + ' ' + normalized_term)},",
            f"     {_toml_string(normalized_term)} in {mapping_name}, {expected})",
        ])
        if action == "add" and surface.surface == "stop_words":
            lines.extend([
                f"test({_toml_string(surface.command + ' filters extraction ' + normalized_term)},",
                f"     {_toml_string(normalized_term)} in kw({_toml_string(normalized_term)}), False)",
            ])
        if action == "add" and surface.surface == "non_food_keywords":
            lines.extend([
                f"test({_toml_string(surface.command + ' filters product ' + normalized_term)},",
                f"     kw({_toml_string(normalized_term)}), [])",
            ])
    block = "\n".join(lines) + "\n"
    _append_text_block(paths.deep_sanity_file, block, dry_run=dry_run, trim_existing=True)
    return block


def _live_runtime_term_set_values(surface: RuntimeTermSetSurface, paths: MatcherPaths) -> set[str]:
    if paths.app_dir != APP_DIR:
        return set()
    if surface.command == "gpb":
        from languages.sv.ingredient_matching.blocker_data import GLOBAL_PRODUCT_NAME_BLOCKERS

        return set(GLOBAL_PRODUCT_NAME_BLOCKERS)
    if surface.command == "strict-processed-rule":
        from languages.sv.ingredient_matching.processed_rules import STRICT_PROCESSED_RULES

        return set(STRICT_PROCESSED_RULES)
    from languages.sv.ingredient_matching.carrier_context import (
        CARRIER_CONTEXT_REQUIRED,
        CONTEXT_REQUIRED_WORDS,
        INGREDIENT_REQUIRES_IN_PRODUCT,
    )

    live_sets = {
        "carrier-context-required": CARRIER_CONTEXT_REQUIRED,
        "context-required-word": CONTEXT_REQUIRED_WORDS,
        "ingredient-requires-product-context": INGREDIENT_REQUIRES_IN_PRODUCT,
    }
    return set(live_sets.get(surface.command, frozenset()))


def _append_runtime_term_set_entry(
    *,
    paths: MatcherPaths,
    surface: RuntimeTermSetSurface,
    terms: tuple[str, ...],
    reason: str,
    dry_run: bool,
) -> str:
    sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
    normalized_terms = tuple(_runtime_rule_normalize_text(term) for term in terms)
    entry_id = _runtime_term_set_entry_id(surface, normalized_terms)
    existing_terms: set[str] = set()
    for entry in sections.get(surface.section, []):
        if not _runtime_overlay_entry_is_active(entry):
            continue
        existing_terms.update(
            _runtime_rule_normalize_text(str(term))
            for term in entry.get(surface.value_field, [])
        )
    existing_terms.update(_live_runtime_term_set_values(surface, paths))
    duplicates = sorted(set(normalized_terms) & existing_terms)
    if duplicates:
        raise typer.BadParameter(f"{surface.command} already contains {', '.join(duplicates)}")

    entry = {
        "id": entry_id,
        "status": "active",
        surface.value_field: list(normalized_terms),
        "reason": reason.strip(),
    }
    preview = _runtime_term_set_entry_block(surface, entry)
    if dry_run:
        return preview

    sections.setdefault(surface.section, []).append(entry)
    paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
    return preview


def _append_runtime_term_set_sanity_stub(
    *,
    paths: MatcherPaths,
    surface: RuntimeTermSetSurface,
    terms: tuple[str, ...],
    policy_ref: str,
    dry_run: bool,
) -> str:
    lines = ["", *_generated_sanity_header(policy_ref, surface.command)]
    if surface.command == "gpb":
        lines.append("from languages.sv.ingredient_matching.blocker_data import GLOBAL_PRODUCT_NAME_BLOCKERS")
    elif surface.command == "strict-processed-rule":
        lines.append("from languages.sv.ingredient_matching.processed_rules import STRICT_PROCESSED_RULES")
    else:
        lines.append(f"from languages.sv.ingredient_matching.carrier_context import {surface.mapping_name}")
    for term in terms:
        normalized_term = _runtime_rule_normalize_text(term)
        lines.extend([
            f"test({_toml_string(surface.command + ' overlay contains ' + normalized_term)},",
            f"     {_toml_string(normalized_term)} in {surface.mapping_name}, True)",
        ])
        if surface.command == "gpb":
            lines.extend([
                f"test({_toml_string(surface.command + ' blocks backend match ' + normalized_term)},",
                f"     recipe_match_num(['ost'], {_deep_sanity_offer_dict(normalized_term + ' Ost', 'dairy')}), 0)",
            ])
    block = "\n".join(lines) + "\n"
    _append_text_block(paths.deep_sanity_file, block, dry_run=dry_run, trim_existing=True)
    return block


def _append_runtime_context_entry(
    *,
    paths: MatcherPaths,
    surface: RuntimeContextSurface,
    trigger: str,
    contexts: tuple[str, ...],
    reason: str,
    dry_run: bool,
) -> str:
    sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
    normalized_trigger = _runtime_rule_normalize_text(trigger)
    normalized_contexts = tuple(_runtime_rule_normalize_text(context) for context in contexts)
    entry_id = _runtime_context_entry_id(surface, normalized_trigger)
    duplicate_contexts: set[str] = set()
    entry: dict[str, Any] | None = None
    for candidate in sections.get(surface.section, []):
        if _runtime_rule_normalize_text(str(candidate.get(surface.key_field, ""))) != normalized_trigger:
            continue
        if _runtime_overlay_entry_is_active(candidate):
            duplicate_contexts.update(
                _runtime_rule_normalize_text(str(context))
                for context in candidate.get(surface.values_field, [])
            )
        if entry is None:
            entry = candidate
    duplicates = sorted(set(normalized_contexts) & duplicate_contexts)
    if duplicates:
        raise typer.BadParameter(f"{surface.command} already contains contexts for {trigger}: {', '.join(duplicates)}")

    if entry is None:
        entry = {
            "id": entry_id,
            "status": "active",
            surface.key_field: normalized_trigger,
            surface.values_field: list(normalized_contexts),
            "reason": reason.strip(),
        }
    else:
        existing_values = list(_runtime_overlay_entry_values(entry, surface.values_field))
        existing_value_set = set(existing_values)
        for value in normalized_contexts:
            if value not in existing_value_set:
                existing_values.append(value)
                existing_value_set.add(value)
        entry["id"] = str(entry.get("id") or entry_id)
        entry["status"] = "active"
        entry.pop("inactive_reason", None)
        entry[surface.key_field] = normalized_trigger
        entry[surface.values_field] = existing_values
        existing_reason = str(entry.get("reason", "")).strip()
        if reason.strip() and reason.strip() not in existing_reason:
            entry["reason"] = f"{existing_reason}; {reason.strip()}" if existing_reason else reason.strip()

    preview = _runtime_context_entry_block(surface, entry)
    if dry_run:
        return preview
    if entry not in sections.setdefault(surface.section, []):
        sections[surface.section].append(entry)
    paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
    return preview


def _append_runtime_context_sanity_stub(
    *,
    paths: MatcherPaths,
    surface: RuntimeContextSurface,
    trigger: str,
    contexts: tuple[str, ...],
    policy_ref: str,
    dry_run: bool,
) -> str:
    normalized_trigger = _runtime_rule_normalize_text(trigger)
    module = (
        "languages.sv.ingredient_matching.recipe_context"
        if surface.command == "cuisine-context"
        else "languages.sv.ingredient_matching.carrier_context"
    )
    mapping_import = f"from {module} import {surface.mapping_name}"
    lines = [
        "",
        *_generated_sanity_header(policy_ref, surface.command),
        mapping_import,
    ]
    for context in contexts:
        normalized_context = _runtime_rule_normalize_text(context)
        lines.extend([
            f"test({_toml_string(surface.command + ' ' + normalized_trigger + ' has ' + normalized_context)},",
            f"     {_toml_string(normalized_context)} in {surface.mapping_name}.get({_toml_string(normalized_trigger)}, set()), True)",
        ])
    block = "\n".join(lines) + "\n"
    _append_text_block(paths.deep_sanity_file, block, dry_run=dry_run, trim_existing=True)
    return block


_COMPOUND_MODE_EXPORTS = {
    "suffix_strict": "_COMPOUND_STRICT_KEYWORDS",
    "prefix_strict": "_COMPOUND_STRICT_PREFIX_KEYWORDS",
    "suffix_protected": "_SUFFIX_PROTECTED_KEYWORDS",
    "embedded_protected": "_EMBEDDED_PROTECTED_KEYWORDS",
}


def _append_runtime_compound_entry(
    *,
    paths: MatcherPaths,
    surface: RuntimeCompoundSurface,
    mode: Literal["suffix-strict", "prefix-strict", "suffix-protected", "embedded-protected"],
    keywords: tuple[str, ...],
    reason: str,
    dry_run: bool,
) -> str:
    sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
    normalized_mode = mode.replace("-", "_")
    normalized_keywords = tuple(_runtime_rule_normalize_text(keyword) for keyword in keywords)
    entry_id = _runtime_compound_entry_id(surface, normalized_mode, normalized_keywords)
    existing_keywords: set[str] = set()
    for entry in sections.get(surface.section, []):
        if str(entry.get("mode", "")).replace("-", "_") != normalized_mode:
            continue
        if not _runtime_overlay_entry_is_active(entry):
            continue
        existing_keywords.update(_runtime_rule_normalize_text(str(keyword)) for keyword in entry.get("keywords", []))
    duplicates = sorted(set(normalized_keywords) & existing_keywords)
    if duplicates:
        raise typer.BadParameter(f"{surface.command} already contains {normalized_mode}: {', '.join(duplicates)}")

    entry = {
        "id": entry_id,
        "status": "active",
        "mode": normalized_mode,
        "keywords": list(normalized_keywords),
        "reason": reason.strip(),
    }
    preview = _runtime_compound_entry_block(surface, entry)
    if dry_run:
        return preview
    sections.setdefault(surface.section, []).append(entry)
    paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
    return preview


def _append_runtime_compound_sanity_stub(
    *,
    paths: MatcherPaths,
    mode: str,
    keywords: tuple[str, ...],
    policy_ref: str,
    dry_run: bool,
) -> str:
    normalized_mode = mode.replace("-", "_")
    export_name = _COMPOUND_MODE_EXPORTS[normalized_mode]
    lines = [
        "",
        *_generated_sanity_header(policy_ref, "compound-protection"),
        f"from languages.sv.ingredient_matching.compound_text import {export_name}",
    ]
    for keyword in keywords:
        normalized_keyword = _runtime_rule_normalize_text(keyword)
        lines.extend([
            f"test({_toml_string('compound-protection ' + normalized_mode + ' ' + normalized_keyword)},",
            f"     {_toml_string(normalized_keyword)} in {export_name}, True)",
        ])
    block = "\n".join(lines) + "\n"
    _append_text_block(paths.deep_sanity_file, block, dry_run=dry_run, trim_existing=True)
    return block


def _append_runtime_specialty_entry(
    *,
    paths: MatcherPaths,
    surface: RuntimeSpecialtySurface,
    key: str,
    values: tuple[str, ...],
    reason: str,
    bidirectional: bool,
    dry_run: bool,
) -> str:
    sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
    normalized_key = _runtime_rule_normalize_text(key)
    normalized_values = tuple(_runtime_rule_normalize_text(value) for value in values)
    entry_id = _runtime_specialty_entry_id(surface, normalized_key, normalized_values)
    existing_values: set[str] = set()
    for entry in sections.get(surface.section, []):
        if _runtime_rule_normalize_text(str(entry.get(surface.key_field, ""))) != normalized_key:
            continue
        if not _runtime_overlay_entry_is_active(entry):
            continue
        existing_values.update(_runtime_rule_normalize_text(str(value)) for value in entry.get(surface.values_field, []))
    duplicates = sorted(set(normalized_values) & existing_values)
    if duplicates:
        raise typer.BadParameter(f"{surface.command} already contains {normalized_key}: {', '.join(duplicates)}")

    entry = {
        "id": entry_id,
        "status": "active",
        surface.key_field: normalized_key,
        surface.values_field: list(normalized_values),
        "reason": reason.strip(),
    }
    if surface.section == "specialty_qualifiers":
        entry["bidirectional"] = bidirectional
    preview = _runtime_specialty_entry_block(surface, entry)
    if dry_run:
        return preview
    sections.setdefault(surface.section, []).append(entry)
    paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
    return preview


def _append_runtime_specialty_sanity_stub(
    *,
    paths: MatcherPaths,
    surface: RuntimeSpecialtySurface,
    key: str,
    values: tuple[str, ...],
    policy_ref: str,
    bidirectional: bool,
    dry_run: bool,
) -> str:
    normalized_key = _runtime_rule_normalize_text(key)
    mapping_name = "QUALIFIER_EQUIVALENTS" if surface.section == "qualifier_equivalents" else "SPECIALTY_QUALIFIERS"
    import_line = f"from languages.sv.ingredient_matching.specialty_rules import {mapping_name}"
    lines = ["", *_generated_sanity_header(policy_ref, surface.command), import_line]
    for value in values:
        normalized_value = _runtime_rule_normalize_text(value)
        if surface.section == "qualifier_equivalents":
            expression = f"{_toml_string(normalized_value)} in {mapping_name}.get({_toml_string(normalized_key)}, set())"
        else:
            expression = f"{_toml_string(normalized_value)} in {mapping_name}.get({_toml_string(normalized_key)}, [])"
        lines.extend([
            f"test({_toml_string(surface.command + ' ' + normalized_key + ' has ' + normalized_value)},",
            f"     {expression}, True)",
        ])
    if bidirectional:
        lines.append("from languages.sv.ingredient_matching.specialty_rules import BIDIRECTIONAL_PER_KEYWORD")
        for value in values:
            normalized_value = _runtime_rule_normalize_text(value)
            lines.extend([
                f"test({_toml_string('specialty bidirectional ' + normalized_key + ' has ' + normalized_value)},",
                f"     {_toml_string(normalized_value)} in BIDIRECTIONAL_PER_KEYWORD.get({_toml_string(normalized_key)}, set()), True)",
            ])
    block = "\n".join(lines) + "\n"
    _append_text_block(paths.deep_sanity_file, block, dry_run=dry_run, trim_existing=True)
    return block


def _append_product_substitution_entry(
    *,
    paths: MatcherPaths,
    required_words: tuple[str, ...],
    old_keyword: str,
    new_keyword: str,
    reason: str,
    dry_run: bool,
) -> str:
    sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
    normalized_required = tuple(_runtime_rule_normalize_text(word) for word in required_words)
    normalized_old = _runtime_rule_normalize_text(old_keyword)
    normalized_new = _runtime_rule_normalize_text(new_keyword)
    required_set = set(normalized_required)
    for entry in sections.get("product_name_substitutions", []):
        if not _runtime_overlay_entry_is_active(entry):
            continue
        if (
            {_runtime_rule_normalize_text(str(word)) for word in entry.get("required_words", [])} == required_set
            and _runtime_rule_normalize_text(str(entry.get("old_keyword", ""))) == normalized_old
            and _runtime_rule_normalize_text(str(entry.get("new_keyword", ""))) == normalized_new
        ):
            raise typer.BadParameter("product-name-substitution already contains this active rule")
    entry = {
        "id": _runtime_product_substitution_entry_id(normalized_required, normalized_old, normalized_new),
        "status": "active",
        "required_words": list(normalized_required),
        "old_keyword": normalized_old,
        "new_keyword": normalized_new,
        "reason": reason.strip(),
    }
    preview = _runtime_product_substitution_entry_block(entry)
    if dry_run:
        return preview
    sections.setdefault("product_name_substitutions", []).append(entry)
    paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
    return preview


def _append_product_substitution_sanity_stub(
    *,
    paths: MatcherPaths,
    required_words: tuple[str, ...],
    old_keyword: str,
    new_keyword: str,
    policy_ref: str,
    dry_run: bool,
) -> str:
    normalized_required = tuple(_runtime_rule_normalize_text(word) for word in required_words)
    normalized_old = _runtime_rule_normalize_text(old_keyword)
    normalized_new = _runtime_rule_normalize_text(new_keyword)
    lines = [
        "",
        *_generated_sanity_header(policy_ref, "product-name-substitution"),
        "from languages.sv.ingredient_matching.match_filters import PRODUCT_NAME_SUBSTITUTIONS",
        f"test({_toml_string('product-name-substitution ' + normalized_old + ' -> ' + normalized_new)},",
        "     any(",
        f"         set(required_words) == set({_toml_array(list(normalized_required))})",
        f"         and old_keyword == {_toml_string(normalized_old)}",
        f"         and new_keyword == {_toml_string(normalized_new)}",
        "         for required_words, old_keyword, new_keyword in PRODUCT_NAME_SUBSTITUTIONS",
        "     ), True)",
    ]
    block = "\n".join(lines) + "\n"
    _append_text_block(paths.deep_sanity_file, block, dry_run=dry_run, trim_existing=True)
    return block


def _append_secondary_pattern_entry(
    *,
    paths: MatcherPaths,
    keyword: str,
    blockers: tuple[str, ...],
    exceptions: tuple[str, ...],
    reason: str,
    dry_run: bool,
) -> str:
    sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
    normalized_keyword = _runtime_rule_normalize_text(keyword)
    normalized_blockers = tuple(_runtime_rule_normalize_text(blocker) for blocker in blockers)
    normalized_exceptions = tuple(_runtime_rule_normalize_text(exception) for exception in exceptions)
    entry: dict[str, Any] | None = None
    existing_blockers: set[str] = set()
    for candidate in sections.get("secondary_ingredient_patterns", []):
        if _runtime_rule_normalize_text(str(candidate.get("keyword", ""))) != normalized_keyword:
            continue
        if _runtime_overlay_entry_is_active(candidate):
            existing_blockers.update(_runtime_rule_normalize_text(str(blocker)) for blocker in candidate.get("blockers", []))
        if entry is None:
            entry = candidate
    duplicates = sorted(set(normalized_blockers) & existing_blockers)
    if duplicates:
        raise typer.BadParameter(f"secondary-ingredient-pattern already contains blockers for {keyword}: {', '.join(duplicates)}")
    if entry is None:
        entry = {
            "id": _runtime_secondary_pattern_entry_id(normalized_keyword),
            "status": "active",
            "keyword": normalized_keyword,
            "blockers": list(normalized_blockers),
            "exceptions": list(normalized_exceptions),
            "reason": reason.strip(),
        }
    else:
        entry["id"] = str(entry.get("id") or _runtime_secondary_pattern_entry_id(normalized_keyword))
        entry["status"] = "active"
        entry.pop("inactive_reason", None)
        entry["keyword"] = normalized_keyword
        entry["blockers"] = list(dict.fromkeys([*entry.get("blockers", []), *normalized_blockers]))
        entry["exceptions"] = list(dict.fromkeys([*entry.get("exceptions", []), *normalized_exceptions]))
        existing_reason = str(entry.get("reason", "")).strip()
        if reason.strip() and reason.strip() not in existing_reason:
            entry["reason"] = f"{existing_reason}; {reason.strip()}" if existing_reason else reason.strip()
    preview = _runtime_secondary_pattern_entry_block(entry)
    if dry_run:
        return preview
    if entry not in sections.setdefault("secondary_ingredient_patterns", []):
        sections["secondary_ingredient_patterns"].append(entry)
    paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
    return preview


def _append_secondary_pattern_sanity_stub(
    *,
    paths: MatcherPaths,
    keyword: str,
    blockers: tuple[str, ...],
    exceptions: tuple[str, ...],
    policy_ref: str,
    dry_run: bool,
) -> str:
    normalized_keyword = _runtime_rule_normalize_text(keyword)
    lines = [
        "",
        *_generated_sanity_header(policy_ref, "secondary-ingredient-pattern"),
        "from languages.sv.ingredient_matching.match_filters import check_secondary_ingredient_patterns",
    ]
    for blocker in blockers:
        normalized_blocker = _runtime_rule_normalize_text(blocker)
        lines.extend([
            f"test({_toml_string('secondary pattern blocks ' + normalized_keyword + ' via ' + normalized_blocker)},",
            f"     check_secondary_ingredient_patterns({_toml_string(normalized_blocker)}, {_toml_string(normalized_keyword)}, {_toml_string(normalized_keyword)}), False)",
        ])
        for exception in exceptions:
            normalized_exception = _runtime_rule_normalize_text(exception)
            lines.extend([
                f"test({_toml_string('secondary pattern allows ' + normalized_keyword + ' via ' + normalized_exception)},",
                f"     check_secondary_ingredient_patterns({_toml_string(normalized_blocker + ' ' + normalized_exception)}, {_toml_string(normalized_keyword)}, {_toml_string(normalized_keyword)}), True)",
            ])
    block = "\n".join(lines) + "\n"
    _append_text_block(paths.deep_sanity_file, block, dry_run=dry_run, trim_existing=True)
    return block


def _validate_spice_fresh_rule_fields(fields: dict[str, tuple[str, ...]]) -> None:
    present = {field for field, values in fields.items() if values}
    if not present:
        raise typer.BadParameter("spice-fresh-rule must include at least one rule field")
    if "fresh_product_words" in present and "dried_indicators" not in present:
        raise typer.BadParameter("--fresh-product-words requires --dried-indicators")
    if "pickled_indicators" in present and "pickled_product_words" not in present:
        raise typer.BadParameter("--pickled-indicators requires --pickled-product-words")
    if "pickled_product_words" in present and "pickled_indicators" not in present:
        raise typer.BadParameter("--pickled-product-words requires --pickled-indicators")
    if "required_ground_product_words" in present and "ground_indicators" not in present:
        raise typer.BadParameter("--required-ground-product-words requires --ground-indicators")
    if "required_whole_product_words" in present and "spice_indicators" not in present:
        raise typer.BadParameter("--required-whole-product-words requires --spice-indicators")
    if (
        "blocked_product_words" in present
        and "allowed_indicators" not in present
        and "spice_indicators" not in present
    ):
        raise typer.BadParameter("--blocked-product-words requires --spice-indicators or --allowed-indicators")


def _append_spice_fresh_rule_entry(
    *,
    paths: MatcherPaths,
    keyword: str,
    fields: dict[str, tuple[str, ...]],
    reason: str,
    dry_run: bool,
) -> str:
    _validate_spice_fresh_rule_fields(fields)
    sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
    normalized_keyword = _runtime_rule_normalize_text(keyword)
    normalized_fields = {
        field: tuple(_runtime_rule_normalize_text(value) for value in values)
        for field, values in fields.items()
        if values
    }
    entry: dict[str, Any] | None = None
    existing_by_field: dict[str, set[str]] = {field: set() for field in _SPICE_FRESH_RULE_FIELDS}
    for candidate in sections.get("spice_fresh_rules", []):
        if _runtime_rule_normalize_text(str(candidate.get("keyword", ""))) != normalized_keyword:
            continue
        if _runtime_overlay_entry_is_active(candidate):
            for field in _SPICE_FRESH_RULE_FIELDS:
                existing_by_field[field].update(_runtime_rule_normalize_text(str(value)) for value in candidate.get(field, []))
        if entry is None:
            entry = candidate
    if paths.app_dir == APP_DIR:
        from languages.sv.ingredient_matching.processed_rules import SPICE_VS_FRESH_RULES

        live_rule = SPICE_VS_FRESH_RULES.get(normalized_keyword, {})
        for field in _SPICE_FRESH_RULE_FIELDS:
            existing_by_field[field].update(str(value) for value in live_rule.get(field, set()))
    duplicate_messages = []
    for field, values in normalized_fields.items():
        duplicates = sorted(set(values) & existing_by_field[field])
        if duplicates:
            duplicate_messages.append(f"{field}: {', '.join(duplicates)}")
    if duplicate_messages:
        raise typer.BadParameter(f"spice-fresh-rule already contains {'; '.join(duplicate_messages)}")
    if entry is None:
        entry = {
            "id": _runtime_spice_fresh_entry_id(normalized_keyword),
            "status": "active",
            "keyword": normalized_keyword,
            "reason": reason.strip(),
        }
    else:
        entry["id"] = str(entry.get("id") or _runtime_spice_fresh_entry_id(normalized_keyword))
        entry["status"] = "active"
        entry.pop("inactive_reason", None)
        entry["keyword"] = normalized_keyword
        existing_reason = str(entry.get("reason", "")).strip()
        if reason.strip() and reason.strip() not in existing_reason:
            entry["reason"] = f"{existing_reason}; {reason.strip()}" if existing_reason else reason.strip()
    for field, values in normalized_fields.items():
        entry[field] = list(dict.fromkeys([*entry.get(field, []), *values]))
    preview = _runtime_spice_fresh_entry_block(entry)
    if dry_run:
        return preview
    if entry not in sections.setdefault("spice_fresh_rules", []):
        sections["spice_fresh_rules"].append(entry)
    paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
    return preview


def _append_spice_fresh_rule_sanity_stub(
    *,
    paths: MatcherPaths,
    keyword: str,
    fields: dict[str, tuple[str, ...]],
    policy_ref: str,
    dry_run: bool,
) -> str:
    normalized_keyword = _runtime_rule_normalize_text(keyword)
    lines = [
        "",
        *_generated_sanity_header(policy_ref, "spice-fresh-rule"),
        "from languages.sv.ingredient_matching.processed_rules import SPICE_VS_FRESH_RULES",
    ]
    for field, values in fields.items():
        for value in values:
            normalized_value = _runtime_rule_normalize_text(value)
            lines.extend([
                f"test({_toml_string('spice-fresh-rule ' + normalized_keyword + ' ' + field + ' ' + normalized_value)},",
                f"     {_toml_string(normalized_value)} in SPICE_VS_FRESH_RULES.get({_toml_string(normalized_keyword)}, {{}}).get({_toml_string(field)}, set()), True)",
            ])
    block = "\n".join(lines) + "\n"
    _append_text_block(paths.deep_sanity_file, block, dry_run=dry_run, trim_existing=True)
    return block


def _append_runtime_overlay_deep_sanity_stub(
    *,
    paths: MatcherPaths,
    surface: RuntimeOverlaySurface,
    keyword: str,
    values: tuple[str, ...],
    policy_ref: str,
    dry_run: bool,
) -> str:
    normalized_keyword = _runtime_rule_normalize_text(keyword)
    mapping_import = f"from languages.sv.ingredient_matching import {surface.mapping_name}"
    lines = [
        "",
        *_generated_sanity_header(policy_ref, surface.command),
        mapping_import,
    ]
    for value in values:
        normalized_value = _runtime_rule_normalize_text(value)
        lines.extend([
            f"test({_toml_string(surface.command.upper() + ' ' + normalized_keyword + ' has ' + normalized_value)},",
            f"     {_toml_string(normalized_value)} in {surface.mapping_name}.get({_toml_string(normalized_keyword)}, set()), True)",
        ])
    block = "\n".join(lines) + "\n"
    _append_text_block(paths.deep_sanity_file, block, dry_run=dry_run, trim_existing=True)
    return block


def _run_track_a_runtime_gates(paths: MatcherPaths, report_root: Path | None) -> int:
    if _matcher_session_should_defer_gates(paths):
        _echo_session_deferred_gates()
        return 0

    args = [
        "--track",
        "A",
        "--runtime-changed",
        "--no-registry-changed",
        "--no-fixtures-changed",
        "--no-inventory-changed",
        "--no-support-checks-changed",
    ]
    return _run_support_check(
        "run_matcher_change_gates.py",
        args,
        report_root=report_root,
        cwd=APP_DIR,
    )


def _raw_args(ctx: typer.Context) -> list[str]:
    return [str(arg) for arg in ctx.args]


def _tree_root_args(tree_root: Path | None) -> list[str]:
    return ["--tree-root", str(tree_root)] if tree_root is not None else []


def _run_session_regen(
    *,
    tree_root: Path | None,
    report_root: Path | None,
    check: bool,
) -> int:
    mode_arg = "--check" if check else "--write"
    common_args = _tree_root_args(tree_root)
    for script_name in (
        "generate_matcher_contract_json_from_toml_sources.py",
        "generate_matcher_registry_coverage.py",
    ):
        status = _run_support_check(
            script_name,
            [*common_args, mode_arg],
            tree_root=tree_root,
            report_root=report_root,
            cwd=APP_DIR,
        )
        if status != 0:
            return status
    return 0


def _run_session_promote(
    *,
    allow_removals: bool,
    confirm_large_removals: bool,
    report_root: Path | None,
) -> int:
    args = ["--language", "sv", "--market", "SE"]
    if allow_removals:
        args.append("--allow-removals")
    if confirm_large_removals:
        args.append("--confirm-large-removals")
    return _run_support_check(
        "promote_term_baseline.py",
        args,
        report_root=report_root,
        cwd=APP_DIR,
    )


def _run_session_refresh_line_refs(
    *,
    paths: MatcherPaths,
    tree_root: Path | None,
    report_root: Path | None,
) -> int:
    return _run_support_check(
        "refresh_matcher_rule_inventory_line_refs.py",
        [
            *_tree_root_args(tree_root),
            "--repo-root",
            str(paths.repo_root),
            "--format",
            "text",
            "--write",
        ],
        tree_root=tree_root,
        report_root=report_root,
        cwd=paths.repo_root,
    )


def _run_session_preflight(
    *,
    tree_root: Path | None,
    report_root: Path | None,
) -> int:
    return _run_support_check(
        "run_matcher_change_preflight.py",
        [*_tree_root_args(tree_root), "--format", "text"],
        tree_root=tree_root,
        report_root=report_root,
        cwd=APP_DIR,
    )


def _session_default_gate_args(track: Literal["A", "B"]) -> list[str]:
    if track == "A":
        return [
            "--track",
            "A",
            "--runtime-changed",
            "--no-registry-changed",
            "--no-fixtures-changed",
            "--no-inventory-changed",
            "--no-support-checks-changed",
        ]
    return [
        "--track",
        "B",
        "--registry-changed",
        "--runtime-changed",
        "--fixtures-changed",
        "--inventory-changed",
        "--no-support-checks-changed",
        "--skip-baseline-promotion",
    ]


def _run_session_gates(
    *,
    track: Literal["A", "B"],
    tree_root: Path | None,
    report_root: Path | None,
    raw_args: list[str],
) -> int:
    if "--track" in raw_args:
        raise typer.BadParameter("pass session --track on finalize, not through raw gate args")
    return _run_support_check(
        "run_matcher_change_gates.py",
        [
            *_session_default_gate_args(track),
            *_tree_root_args(tree_root),
            *raw_args,
        ],
        tree_root=tree_root,
        report_root=report_root,
        cwd=APP_DIR,
    )


def _guide_key(shape: str) -> str:
    normalized = shape.strip().lower().replace("_", "-")
    return GUIDE_ALIASES.get(shape.strip().lower(), GUIDE_ALIASES.get(normalized, normalized))


def _matcher_surface_key(surface_name: str) -> str:
    return _guide_key(surface_name)


def _print_guide(guide: MatcherGuide) -> None:
    typer.echo(f"{guide.label}: {guide.status}")
    typer.echo(guide.summary)
    typer.echo("")
    for index, step in enumerate(guide.steps, start=1):
        typer.echo(f"{index}. {step}")
    if guide.status == "supported by dm matcher add":
        typer.echo("")
        typer.echo(
            "Batch review: add --no-run-gates to each add command, then run one final "
            "./bin/dm matcher gates command before handoff."
        )


@matcher_add_app.command("keyword-extra-parent")
def add_keyword_extra_parent(
    canonical: Annotated[str, typer.Argument(help="Existing parent canonical, e.g. citrusfrukter.")],
    kids_csv: Annotated[
        str,
        typer.Option(
            "--kids",
            help="Comma-separated child/product terms that should roll up to the parent canonical.",
        ),
    ],
    recipe_name: Annotated[str, typer.Option("--recipe-name", help="Recipe name for generated positive fixtures.")],
    ingredient: Annotated[str, typer.Option("--ingredient", help="Ingredient text for generated fixtures.")],
    offer_names_csv: Annotated[
        str | None,
        typer.Option("--offer-names", help="Optional comma-separated offer names matching --kids order."),
    ] = None,
    offer_category: Annotated[str, typer.Option("--offer-category", help="Offer category used in fixtures.")] = "pantry",
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable policy ref override.")] = None,
    source_ref: Annotated[str | None, typer.Option("--source-ref", help="Stable source ref override.")] = None,
    inventory_id_override: Annotated[
        str | None,
        typer.Option("--inventory-id", help="Stable inventory id override."),
    ] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run generated coverage and Track B gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
) -> None:
    kids = _split_csv(kids_csv, label="--kids")
    offer_names = (
        _split_csv(offer_names_csv, label="--offer-names", lowercase=False)
        if offer_names_csv
        else tuple(_titleish(kid) for kid in kids)
    )
    if len(offer_names) != len(kids):
        raise typer.BadParameter("--offer-names must have the same item count as --kids")
    canonical = canonical.strip().lower()
    _validate_keyword_extra_parent_args(canonical, kids)

    canonical_slug = _slug(canonical)
    policy_ref = policy_ref or f"keyword_extra_parent_{canonical_slug}_family"
    source_ref = source_ref or f"current_review:keyword_extra_parent_{canonical_slug}_routing"
    inventory_id = (
        inventory_id_override.strip()
        if inventory_id_override is not None
        else f"legacy_parent_{canonical_slug}_family"
    )
    if not inventory_id:
        raise typer.BadParameter("--inventory-id must not be empty")
    paths = _paths(tree_root)
    planned_fixture_ids = tuple(
        f"keyword_extra_parent_{canonical_slug}_{_slug(kid)}_positive"
        for kid in kids
    )
    _ensure_can_add_keyword_extra_parent(
        paths=paths,
        canonical=canonical,
        kids=kids,
        fixture_ids=planned_fixture_ids,
        inventory_id=inventory_id,
    )

    entry_ids, first_entry_line, toml_preview = _append_keyword_extra_parent_entries(
        paths=paths,
        canonical=canonical,
        kids=kids,
        offer_names=offer_names,
        source_ref=f"registry:keyword_extra_parent_entries:{policy_ref}",
        ingredient=ingredient,
        dry_run=dry_run,
    )
    fixture_ids = _append_fixtures(
        paths=paths,
        canonical=canonical,
        kids=kids,
        offer_names=offer_names,
        recipe_name=recipe_name,
        ingredient=ingredient,
        offer_category=offer_category,
        policy_ref=policy_ref,
        source_ref=source_ref,
        dry_run=dry_run,
    )
    _append_inventory(
        paths=paths,
        canonical=canonical,
        kids=kids,
        fixture_ids=fixture_ids,
        policy_ref=policy_ref,
        source_ref=source_ref,
        inventory_id=inventory_id,
        first_entry_id=entry_ids[0],
        first_entry_line=first_entry_line,
        dry_run=dry_run,
    )
    sanity_preview = _append_deep_sanity_stub(
        paths=paths,
        canonical=canonical,
        kids=kids,
        offer_names=offer_names,
        ingredient=ingredient,
        offer_category=offer_category,
        policy_ref=policy_ref,
        sanity_mode="fast-match",
        dry_run=dry_run,
    )

    change = MatcherChangePlan(
        command="keyword-extra-parent",
        policy_ref=policy_ref,
        entry_ids=entry_ids,
        fixture_ids=fixture_ids,
        inventory_id=inventory_id,
        toml_preview=toml_preview,
        sanity_preview=sanity_preview,
        runtime_delta_filename="keyword_extra_parent.toml",
    )

    if dry_run:
        _print_dry_run_preview(change)
        return

    _regenerate_contract_json(paths)

    typer.echo(f"Generated keyword_extra_parent rule: {change.policy_ref}")
    typer.echo(f"  entries: {', '.join(change.entry_ids)}")
    typer.echo(f"  fixtures: {', '.join(change.fixture_ids)}")
    typer.echo(f"  inventory: {change.inventory_id}")
    _print_generated_sanity_probe(paths, change.policy_ref)

    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return

    gate_status = _run_track_b_change_plan(paths=paths, change=change, report_root=report_root)
    raise typer.Exit(gate_status)


@matcher_add_app.command("keyword-synonym")
def add_keyword_synonym(
    canonical: Annotated[str, typer.Argument(help="Canonical keyword, e.g. isbergssallat.")],
    variants_csv: Annotated[
        str,
        typer.Option(
            "--variants",
            help="Comma-separated spelling/compound variants that should normalize to the canonical.",
        ),
    ],
    sanity_offer: Annotated[
        str,
        typer.Option("--sanity-offer", help="Offer name used by the generated deep-sanity regression."),
    ],
    offer_category: Annotated[str, typer.Option("--offer-category", help="Offer category for sanity/fixtures.")] = "pantry",
    ingredient_override: Annotated[
        str | None,
        typer.Option("--ingredient", help="Ingredient text override. Best used with a single variant."),
    ] = None,
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable policy ref override.")] = None,
    source_ref: Annotated[str | None, typer.Option("--source-ref", help="Stable source ref override.")] = None,
    with_fixture: Annotated[
        bool,
        typer.Option("--with-fixture", help="Also add generated matcher fixture TOML/JSON."),
    ] = False,
    with_inventory: Annotated[
        bool,
        typer.Option("--with-inventory", help="Also add matcher rule inventory TOML/JSON; implies --with-fixture."),
    ] = False,
    inventory_id_override: Annotated[
        str | None,
        typer.Option("--inventory-id", help="Stable inventory id override when --with-inventory is used."),
    ] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run light registry/sanity gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
) -> None:
    variants = _split_csv(variants_csv, label="--variants")
    canonical = canonical.strip().lower()
    if not canonical:
        raise typer.BadParameter("canonical must not be empty")
    if any(variant == canonical for variant in variants):
        raise typer.BadParameter("--variants must differ from canonical")
    if ingredient_override is not None and not ingredient_override.strip():
        raise typer.BadParameter("--ingredient must not be empty")
    for warning in _keyword_synonym_space_norm_warnings(canonical, variants):
        typer.secho(f"WARNING: {warning}", fg=typer.colors.YELLOW, err=True)

    paths = _paths(tree_root)
    canonical_slug = _slug(canonical)
    variant_slug = _slug(variants[0])
    policy_ref = policy_ref or f"keyword_synonym_{canonical_slug}_{variant_slug}"
    source_ref = source_ref or f"manual:{policy_ref}"
    fixture_requested = with_fixture or with_inventory
    inventory_id = None
    if with_inventory:
        inventory_id = (
            inventory_id_override.strip()
            if inventory_id_override is not None
            else f"legacy_synonym_{canonical_slug}_{variant_slug}"
        )
        if not inventory_id:
            raise typer.BadParameter("--inventory-id must not be empty")
    elif inventory_id_override is not None:
        raise typer.BadParameter("--inventory-id requires --with-inventory")
    if paths.app_dir != APP_DIR and run_gates and not fixture_requested and not dry_run:
        raise typer.BadParameter(
            "tree-root keyword-synonym light gates are not available; use --no-run-gates "
            "or add --with-fixture for Track B gates"
        )

    planned_fixture_ids = (
        tuple(f"keyword_synonym_{canonical_slug}_{_slug(variant)}_positive" for variant in variants)
        if fixture_requested
        else ()
    )
    _ensure_can_add_keyword_synonym(
        paths=paths,
        canonical=canonical,
        variants=variants,
        fixture_ids=planned_fixture_ids,
        inventory_id=inventory_id,
    )

    entry_id, entry_line, toml_preview = _append_keyword_synonym_entry(
        paths=paths,
        canonical=canonical,
        variants=variants,
        source_ref=source_ref,
        sanity_offer=sanity_offer,
        offer_category=offer_category,
        ingredient_override=ingredient_override,
        dry_run=dry_run,
    )
    fixture_ids = ()
    if fixture_requested:
        fixture_ids = _append_keyword_synonym_fixtures(
            paths=paths,
            canonical=canonical,
            variants=variants,
            sanity_offer=sanity_offer,
            offer_category=offer_category,
            ingredient_override=ingredient_override,
            policy_ref=policy_ref,
            source_ref=source_ref,
            dry_run=dry_run,
        )
    if with_inventory and inventory_id is not None:
        _append_keyword_synonym_inventory(
            paths=paths,
            canonical=canonical,
            variants=variants,
            fixture_ids=fixture_ids,
            policy_ref=policy_ref,
            source_ref=source_ref,
            inventory_id=inventory_id,
            entry_id=entry_id,
            entry_line=entry_line,
            dry_run=dry_run,
        )
    sanity_preview = _append_keyword_synonym_deep_sanity_stub(
        paths=paths,
        canonical=canonical,
        variants=variants,
        sanity_offer=sanity_offer,
        offer_category=offer_category,
        ingredient_override=ingredient_override,
        policy_ref=policy_ref,
        sanity_mode="fast-match",
        dry_run=dry_run,
    )

    change = MatcherChangePlan(
        command="keyword-synonym",
        policy_ref=policy_ref,
        entry_ids=(entry_id,),
        fixture_ids=fixture_ids,
        inventory_id=inventory_id,
        toml_preview=toml_preview,
        sanity_preview=sanity_preview,
        runtime_delta_filename="keyword_synonym.toml",
    )

    if dry_run:
        _print_dry_run_preview(change)
        return

    if fixture_requested:
        _regenerate_contract_json(paths)

    typer.echo(f"Generated keyword_synonym rule: {change.policy_ref}")
    typer.echo(f"  entry: {entry_id}")
    if fixture_ids:
        typer.echo(f"  fixtures: {', '.join(fixture_ids)}")
    if inventory_id:
        typer.echo(f"  inventory: {inventory_id}")
    _print_generated_sanity_probe(paths, change.policy_ref)

    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return

    if fixture_requested:
        gate_status = _run_track_b_change_plan(paths=paths, change=change, report_root=report_root)
    else:
        gate_status = _run_keyword_synonym_light_gates(paths=paths, report_root=report_root)
    raise typer.Exit(gate_status)


def _add_runtime_overlay_rule(
    *,
    surface: RuntimeOverlaySurface,
    keyword: str,
    values_csv: str,
    reason: str,
    policy_ref: str | None,
    tree_root: Path | None,
    run_gates: bool,
    report_root: Path | None,
    dry_run: bool,
    write_sanity: bool,
) -> None:
    keyword = keyword.strip().lower()
    if not keyword:
        raise typer.BadParameter("keyword must not be empty")
    values = _split_csv(values_csv, label=f"--{surface.value_field}")
    reason = reason.strip()
    if not reason:
        raise typer.BadParameter("--reason must not be empty")

    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root runtime add gates are not available; use --no-run-gates")

    _emit_runtime_authoring_warnings(
        (
            *_runtime_space_norm_compound_warnings(
                paths=paths,
                surface=surface,
                keyword=keyword,
                values=values,
            ),
            *_runtime_fpb_smart_blocker_warning(surface, keyword),
        )
    )

    policy_ref = policy_ref or f"runtime_{surface.command}_{_slug(keyword)}_{_slug(values[0])}"
    overlay_preview = _append_runtime_overlay_entry(
        paths=paths,
        surface=surface,
        keyword=keyword,
        values=values,
        reason=reason,
        dry_run=dry_run,
    )
    sanity_preview = ""
    if write_sanity:
        sanity_preview = _append_runtime_overlay_deep_sanity_stub(
            paths=paths,
            surface=surface,
            keyword=keyword,
            values=values,
            policy_ref=policy_ref,
            dry_run=dry_run,
        )

    if dry_run:
        typer.echo(overlay_preview)
        if sanity_preview:
            typer.echo(sanity_preview)
        typer.echo("Dry run only; no files written.")
        return

    typer.echo(f"Generated runtime {surface.command} rule: {policy_ref}")
    typer.echo(f"  keyword: {keyword}")
    typer.echo(f"  {surface.value_field}: {', '.join(values)}")
    if write_sanity:
        typer.echo("  sanity: appended")
    else:
        typer.echo("  sanity: skipped")

    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return

    gate_status = _run_track_a_runtime_gates(paths=paths, report_root=report_root)
    raise typer.Exit(gate_status)


@matcher_add_app.command("pnb")
def add_pnb(
    keyword: Annotated[str, typer.Argument(help="Keyword whose product matches should be blocked.")],
    blockers_csv: Annotated[
        str,
        typer.Option("--blockers", help="Comma-separated product-name blockers for this keyword."),
    ],
    reason: Annotated[str, typer.Option("--reason", help="Why this runtime blocker is needed.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_runtime_overlay_rule(
        surface=RUNTIME_OVERLAY_SURFACES["pnb"],
        keyword=keyword,
        values_csv=blockers_csv,
        reason=reason,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("fpb")
def add_fpb(
    keyword: Annotated[str, typer.Argument(help="Keyword to suppress in ingredient blocker contexts.")],
    blockers_csv: Annotated[
        str,
        typer.Option("--blockers", help="Comma-separated ingredient-side blockers for this keyword."),
    ],
    reason: Annotated[str, typer.Option("--reason", help="Why this runtime blocker is needed.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_runtime_overlay_rule(
        surface=RUNTIME_OVERLAY_SURFACES["fpb"],
        keyword=keyword,
        values_csv=blockers_csv,
        reason=reason,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("keyword-suppressed-by-context")
@matcher_add_app.command("ksbc")
def add_ksbc(
    keyword: Annotated[str, typer.Argument(help="Generic keyword to suppress in specific ingredient contexts.")],
    context_csv: Annotated[
        str,
        typer.Option("--context", help="Comma-separated ingredient context terms that suppress this keyword."),
    ],
    reason: Annotated[str, typer.Option("--reason", help="Why this semantic suppression is needed.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_runtime_overlay_rule(
        surface=RUNTIME_OVERLAY_SURFACES["ksbc"],
        keyword=keyword,
        values_csv=context_csv,
        reason=reason,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("space-normalization")
def add_space_normalization(
    source: Annotated[str, typer.Argument(help="Source phrase/token to normalize before extraction.")],
    target: Annotated[str, typer.Option("--target", help="Replacement text after normalization.")],
    reason: Annotated[str, typer.Option("--reason", help="Why this normalization is needed.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    source = source.strip()
    target = target.strip()
    if not source:
        raise typer.BadParameter("source must not be empty")
    if not target:
        raise typer.BadParameter("--target must not be empty")
    if not reason.strip():
        raise typer.BadParameter("--reason must not be empty")
    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root runtime add gates are not available; use --no-run-gates")

    normalized_source = _runtime_rule_normalize_text(source)
    normalized_target = _runtime_rule_normalize_text(target)
    policy_ref = policy_ref or f"runtime_space_normalization_{_slug(normalized_source)}_{_slug(normalized_target)}"
    surface = RUNTIME_PAIR_SURFACES["space-normalization"]
    overlay_preview, entry_id = _append_runtime_pair_entry(
        paths=paths,
        surface=surface,
        source=source,
        target=target,
        reason=reason,
        dry_run=dry_run,
    )
    sanity_preview = ""
    if write_sanity:
        sanity_preview = _append_space_normalization_sanity_stub(
            paths=paths,
            source=source,
            target=target,
            policy_ref=policy_ref,
            dry_run=dry_run,
        )

    if dry_run:
        typer.echo(overlay_preview)
        if sanity_preview:
            typer.echo(sanity_preview)
        typer.echo("Dry run only; no files written.")
        return

    typer.echo(f"Generated space_normalization rule: {policy_ref}")
    typer.echo(f"  entry: {entry_id}")
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))


@matcher_add_app.command("dual-keyword-normalization")
def add_dual_keyword_normalization(
    source: Annotated[str, typer.Argument(help="Source phrase/token to normalize before extraction.")],
    primary: Annotated[str, typer.Option("--primary", help="First target keyword; this wins canonical selection.")],
    extra_keywords_csv: Annotated[
        str,
        typer.Option("--extra-keywords", help="Comma-separated additional target keywords exposed after the primary."),
    ],
    reason: Annotated[str, typer.Option("--reason", help="Why this ordered multi-keyword normalization is needed.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    source = source.strip()
    primary = primary.strip()
    extra_keywords = _split_csv(extra_keywords_csv, label="--extra-keywords")
    if not source:
        raise typer.BadParameter("source must not be empty")
    if not primary:
        raise typer.BadParameter("--primary must not be empty")
    if not reason.strip():
        raise typer.BadParameter("--reason must not be empty")
    normalized_primary = _runtime_rule_normalize_text(primary)
    normalized_extras = tuple(_runtime_rule_normalize_text(keyword) for keyword in extra_keywords)
    duplicate_targets = sorted({normalized_primary} & set(normalized_extras))
    if duplicate_targets:
        raise typer.BadParameter("--primary must not also appear in --extra-keywords: " + ", ".join(duplicate_targets))

    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root runtime add gates are not available; use --no-run-gates")

    normalized_source = _runtime_rule_normalize_text(source)
    target = " ".join((normalized_primary, *normalized_extras))
    policy_ref = policy_ref or f"runtime_dual_keyword_normalization_{_slug(normalized_source)}_{_slug(normalized_primary)}"
    surface = RUNTIME_PAIR_SURFACES["space-normalization"]
    overlay_preview, entry_id = _append_runtime_pair_entry(
        paths=paths,
        surface=surface,
        source=source,
        target=target,
        reason=reason,
        dry_run=dry_run,
    )
    sanity_preview = ""
    if write_sanity:
        sanity_preview = _append_space_normalization_sanity_stub(
            paths=paths,
            source=source,
            target=target,
            policy_ref=policy_ref,
            dry_run=dry_run,
            command_name="dual-keyword-normalization",
        )

    canonical_note = (
        f"Canonical order: {normalized_primary} is first; extra keyword(s) after it: "
        + ", ".join(normalized_extras)
    )
    if dry_run:
        typer.echo(overlay_preview)
        if sanity_preview:
            typer.echo(sanity_preview)
        typer.echo(canonical_note)
        typer.echo("Dry run only; no files written.")
        return

    typer.echo(f"Generated dual-keyword space_normalization rule: {policy_ref}")
    typer.echo(f"  entry: {entry_id}")
    typer.echo(f"  {canonical_note}")
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))


def _add_runtime_set_update_rule(
    *,
    surface: RuntimeSetUpdateSurface,
    terms_csv: str,
    action: Literal["add", "remove"],
    reason: str,
    policy_ref: str | None,
    tree_root: Path | None,
    run_gates: bool,
    report_root: Path | None,
    dry_run: bool,
    write_sanity: bool,
) -> None:
    terms = _split_csv(terms_csv, label="--terms")
    if not reason.strip():
        raise typer.BadParameter("--reason must not be empty")
    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root runtime add gates are not available; use --no-run-gates")
    first_slug = _slug(terms[0])
    policy_ref = policy_ref or f"runtime_{surface.command.replace('-', '_')}_{action}_{first_slug}"
    overlay_preview = _append_runtime_set_update_entry(
        paths=paths,
        surface=surface,
        terms=terms,
        action=action,
        reason=reason,
        dry_run=dry_run,
    )
    sanity_preview = ""
    if write_sanity:
        sanity_preview = _append_runtime_set_update_sanity_stub(
            paths=paths,
            surface=surface,
            terms=terms,
            action=action,
            policy_ref=policy_ref,
            dry_run=dry_run,
        )

    if dry_run:
        typer.echo(overlay_preview)
        if sanity_preview:
            typer.echo(sanity_preview)
        typer.echo("Dry run only; no files written.")
        return

    typer.echo(f"Generated {surface.surface} {action} rule: {policy_ref}")
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))


def _add_runtime_term_set_rule(
    *,
    surface: RuntimeTermSetSurface,
    terms_csv: str,
    reason: str,
    allow_broad: bool,
    policy_ref: str | None,
    tree_root: Path | None,
    run_gates: bool,
    report_root: Path | None,
    dry_run: bool,
    write_sanity: bool,
) -> None:
    terms = _split_csv(terms_csv, label="--terms")
    if not reason.strip():
        raise typer.BadParameter("--reason must not be empty")
    broad_terms = []
    if surface.broad_guard_min_chars is not None:
        broad_terms = [
            term for term in terms
            if len(_runtime_rule_normalize_text(term).replace(" ", "")) < surface.broad_guard_min_chars
        ]
    if broad_terms and not allow_broad:
        raise typer.BadParameter(
            f"{surface.command} terms shorter than {surface.broad_guard_min_chars} characters require --allow-broad: "
            + ", ".join(broad_terms)
        )
    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root runtime add gates are not available; use --no-run-gates")
    policy_ref = policy_ref or f"runtime_{surface.command.replace('-', '_')}_{_slug(terms[0])}"
    overlay_preview = _append_runtime_term_set_entry(
        paths=paths,
        surface=surface,
        terms=terms,
        reason=reason,
        dry_run=dry_run,
    )
    sanity_preview = ""
    if write_sanity:
        sanity_preview = _append_runtime_term_set_sanity_stub(
            paths=paths,
            surface=surface,
            terms=terms,
            policy_ref=policy_ref,
            dry_run=dry_run,
        )

    if dry_run:
        typer.echo(overlay_preview)
        if sanity_preview:
            typer.echo(sanity_preview)
        typer.echo("Dry run only; no files written.")
        return

    typer.echo(f"Generated {surface.section} rule: {policy_ref}")
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))


def _add_keyword_filter_set_rule(
    *,
    surface: RuntimeSetUpdateSurface,
    terms_csv: str,
    action: Literal["add", "remove"],
    reason: str,
    allow_broad: bool,
    allow_removal: bool,
    policy_ref: str | None,
    tree_root: Path | None,
    run_gates: bool,
    report_root: Path | None,
    dry_run: bool,
    write_sanity: bool,
) -> None:
    terms = _split_csv(terms_csv, label="--terms")
    broad_terms = [
        term for term in terms
        if len(_runtime_rule_normalize_text(term).replace(" ", "")) < 4
    ]
    if broad_terms and not allow_broad:
        raise typer.BadParameter(
            f"{surface.command} terms shorter than four characters require --allow-broad: "
            + ", ".join(broad_terms)
        )
    if action == "remove" and not allow_removal:
        raise typer.BadParameter(f"{surface.command} removals require --allow-removal")
    _add_runtime_set_update_rule(
        surface=surface,
        terms_csv=",".join(terms),
        action=action,
        reason=reason,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("stop-word")
def add_stop_word(
    terms_csv: Annotated[str, typer.Option("--terms", help="Comma-separated STOP_WORDS terms to add/remove.")],
    reason: Annotated[str, typer.Option("--reason", help="Why these terms should change stop-word extraction.")],
    action: Annotated[
        Literal["add", "remove"],
        typer.Option("--action", help="Whether to add to or remove from STOP_WORDS."),
    ] = "add",
    allow_broad: Annotated[
        bool,
        typer.Option("--allow-broad", help="Allow terms shorter than four normalized characters."),
    ] = False,
    allow_removal: Annotated[
        bool,
        typer.Option("--allow-removal", help="Allow removing terms from this broad extraction filter."),
    ] = False,
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_keyword_filter_set_rule(
        surface=RUNTIME_SET_UPDATE_SURFACES["stop-word"],
        terms_csv=terms_csv,
        action=action,
        reason=reason,
        allow_broad=allow_broad,
        allow_removal=allow_removal,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("non-food-keyword")
def add_non_food_keyword(
    terms_csv: Annotated[str, typer.Option("--terms", help="Comma-separated NON_FOOD_KEYWORDS terms to add/remove.")],
    reason: Annotated[str, typer.Option("--reason", help="Why these terms should change non-food filtering.")],
    action: Annotated[
        Literal["add", "remove"],
        typer.Option("--action", help="Whether to add to or remove from NON_FOOD_KEYWORDS."),
    ] = "add",
    allow_broad: Annotated[
        bool,
        typer.Option("--allow-broad", help="Allow terms shorter than four normalized characters."),
    ] = False,
    allow_removal: Annotated[
        bool,
        typer.Option("--allow-removal", help="Allow removing terms from this broad product filter."),
    ] = False,
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_keyword_filter_set_rule(
        surface=RUNTIME_SET_UPDATE_SURFACES["non-food-keyword"],
        terms_csv=terms_csv,
        action=action,
        reason=reason,
        allow_broad=allow_broad,
        allow_removal=allow_removal,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("gpb")
def add_gpb(
    terms_csv: Annotated[
        str,
        typer.Option("--terms", help="Comma-separated global product-name blocker terms to add."),
    ],
    reason: Annotated[str, typer.Option("--reason", help="Why these products are globally out of scope.")],
    allow_broad: Annotated[
        bool,
        typer.Option("--allow-broad", help="Allow terms shorter than four normalized characters."),
    ] = False,
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_runtime_term_set_rule(
        surface=RUNTIME_TERM_SET_SURFACES["gpb"],
        terms_csv=terms_csv,
        reason=reason,
        allow_broad=allow_broad,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("flavor-word")
def add_flavor_word(
    terms_csv: Annotated[str, typer.Option("--terms", help="Comma-separated flavor words to add.")],
    reason: Annotated[str, typer.Option("--reason", help="Why these words are product flavors, not ingredients.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_runtime_set_update_rule(
        surface=RUNTIME_SET_UPDATE_SURFACES["flavor-word"],
        terms_csv=terms_csv,
        action="add",
        reason=reason,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("carrier-product")
def add_carrier_product(
    terms_csv: Annotated[str, typer.Option("--terms", help="Comma-separated carrier product terms to add.")],
    reason: Annotated[str, typer.Option("--reason", help="Why these carriers should strip flavor words.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_runtime_set_update_rule(
        surface=RUNTIME_SET_UPDATE_SURFACES["carrier-product"],
        terms_csv=terms_csv,
        action="add",
        reason=reason,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("important-short-keyword")
def add_important_short_keyword(
    terms_csv: Annotated[str, typer.Option("--terms", help="Comma-separated short keywords to force-keep.")],
    reason: Annotated[str, typer.Option("--reason", help="Why these short words are meaningful food keywords.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_runtime_set_update_rule(
        surface=RUNTIME_SET_UPDATE_SURFACES["important-short-keyword"],
        terms_csv=terms_csv,
        action="add",
        reason=reason,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("processed-food")
def add_processed_food_update(
    terms_csv: Annotated[str, typer.Option("--terms", help="Comma-separated processed-food terms to add/remove.")],
    reason: Annotated[str, typer.Option("--reason", help="Why these terms should change processed-food handling.")],
    action: Annotated[
        Literal["add", "remove"],
        typer.Option("--action", help="Whether to add to or remove from PROCESSED_FOODS."),
    ] = "remove",
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_runtime_set_update_rule(
        surface=RUNTIME_SET_UPDATE_SURFACES["processed-food"],
        terms_csv=terms_csv,
        action=action,
        reason=reason,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("processed-rule")
def add_processed_rule(
    keyword: Annotated[str, typer.Argument(help="Keyword whose processed product forms should be guarded.")],
    blocked_product_words_csv: Annotated[
        str,
        typer.Option("--blocked-product-words", help="Comma-separated product words that mark processed/form variants."),
    ],
    reason: Annotated[str, typer.Option("--reason", help="Why this processed/form guard is needed.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_runtime_overlay_rule(
        surface=RUNTIME_OVERLAY_SURFACES["processed-rule"],
        keyword=keyword,
        values_csv=blocked_product_words_csv,
        reason=reason,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("processed-exemption")
def add_processed_exemption(
    keyword: Annotated[str, typer.Argument(help="Processed-rule base keyword to exempt compounds from.")],
    compounds_csv: Annotated[
        str,
        typer.Option("--compounds", help="Comma-separated compound words exempt from the processed rule."),
    ],
    reason: Annotated[str, typer.Option("--reason", help="Why these compounds should bypass the processed rule.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_runtime_overlay_rule(
        surface=RUNTIME_OVERLAY_SURFACES["processed-exemption"],
        keyword=keyword,
        values_csv=compounds_csv,
        reason=reason,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("strict-processed-rule")
def add_strict_processed_rule(
    terms_csv: Annotated[str, typer.Option("--terms", help="Comma-separated processed-rule keywords to make strict.")],
    reason: Annotated[str, typer.Option("--reason", help="Why these processed rules require exact indicator agreement.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_runtime_term_set_rule(
        surface=RUNTIME_TERM_SET_SURFACES["strict-processed-rule"],
        terms_csv=terms_csv,
        reason=reason,
        allow_broad=False,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("spice-fresh-rule")
def add_spice_fresh_rule(
    keyword: Annotated[str, typer.Argument(help="Keyword whose spice/fresh product forms should be guarded.")],
    reason: Annotated[str, typer.Option("--reason", help="Why this spice/fresh guard is needed.")],
    blocked_product_words_csv: Annotated[
        str | None,
        typer.Option("--blocked-product-words", help="Product words blocked unless ingredient has matching indicators."),
    ] = None,
    spice_indicators_csv: Annotated[
        str | None,
        typer.Option("--spice-indicators", help="Ingredient words/units indicating spice/dried/whole form."),
    ] = None,
    allowed_indicators_csv: Annotated[
        str | None,
        typer.Option("--allowed-indicators", help="Ingredient words that allow blocked product words."),
    ] = None,
    fresh_product_words_csv: Annotated[
        str | None,
        typer.Option("--fresh-product-words", help="Fresh-product words blocked by dried ingredient indicators."),
    ] = None,
    dried_indicators_csv: Annotated[
        str | None,
        typer.Option("--dried-indicators", help="Ingredient words/units indicating dried/ground form."),
    ] = None,
    ground_indicators_csv: Annotated[
        str | None,
        typer.Option("--ground-indicators", help="Ingredient words indicating ground form."),
    ] = None,
    blocked_whole_product_words_csv: Annotated[
        str | None,
        typer.Option("--blocked-whole-product-words", help="Whole-product words blocked by ground indicators."),
    ] = None,
    required_ground_product_words_csv: Annotated[
        str | None,
        typer.Option("--required-ground-product-words", help="Product words required when ingredient asks for ground form."),
    ] = None,
    required_whole_product_words_csv: Annotated[
        str | None,
        typer.Option("--required-whole-product-words", help="Product words required when ingredient asks for whole form."),
    ] = None,
    pickled_indicators_csv: Annotated[
        str | None,
        typer.Option("--pickled-indicators", help="Ingredient words indicating pickled/preserved form."),
    ] = None,
    pickled_product_words_csv: Annotated[
        str | None,
        typer.Option("--pickled-product-words", help="Product words that prove pickled/preserved form."),
    ] = None,
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    keyword = keyword.strip()
    if not keyword:
        raise typer.BadParameter("keyword must not be empty")
    if not reason.strip():
        raise typer.BadParameter("--reason must not be empty")
    fields = {
        "allowed_indicators": _split_optional_csv(allowed_indicators_csv, label="--allowed-indicators"),
        "blocked_product_words": _split_optional_csv(blocked_product_words_csv, label="--blocked-product-words"),
        "blocked_whole_product_words": _split_optional_csv(
            blocked_whole_product_words_csv,
            label="--blocked-whole-product-words",
        ),
        "dried_indicators": _split_optional_csv(dried_indicators_csv, label="--dried-indicators"),
        "fresh_product_words": _split_optional_csv(fresh_product_words_csv, label="--fresh-product-words"),
        "ground_indicators": _split_optional_csv(ground_indicators_csv, label="--ground-indicators"),
        "pickled_indicators": _split_optional_csv(pickled_indicators_csv, label="--pickled-indicators"),
        "pickled_product_words": _split_optional_csv(pickled_product_words_csv, label="--pickled-product-words"),
        "required_ground_product_words": _split_optional_csv(
            required_ground_product_words_csv,
            label="--required-ground-product-words",
        ),
        "required_whole_product_words": _split_optional_csv(
            required_whole_product_words_csv,
            label="--required-whole-product-words",
        ),
        "spice_indicators": _split_optional_csv(spice_indicators_csv, label="--spice-indicators"),
    }
    _validate_spice_fresh_rule_fields(fields)
    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root runtime add gates are not available; use --no-run-gates")
    normalized_keyword = _runtime_rule_normalize_text(keyword)
    policy_ref = policy_ref or f"runtime_spice_fresh_rule_{_slug(normalized_keyword)}"
    overlay_preview = _append_spice_fresh_rule_entry(
        paths=paths,
        keyword=keyword,
        fields=fields,
        reason=reason,
        dry_run=dry_run,
    )
    sanity_preview = ""
    if write_sanity:
        sanity_preview = _append_spice_fresh_rule_sanity_stub(
            paths=paths,
            keyword=keyword,
            fields=fields,
            policy_ref=policy_ref,
            dry_run=dry_run,
        )
    if dry_run:
        typer.echo(overlay_preview)
        if sanity_preview:
            typer.echo(sanity_preview)
        typer.echo("Dry run only; no files written.")
        return
    typer.echo(f"Generated spice_fresh_rule: {policy_ref}")
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))


@matcher_add_app.command("qualifier-required-keyword")
def add_qualifier_required_keyword(
    terms_csv: Annotated[str, typer.Option("--terms", help="Comma-separated keywords requiring product qualifiers.")],
    reason: Annotated[str, typer.Option("--reason", help="Why these keywords require qualifier agreement.")],
    action: Annotated[
        Literal["add", "remove"],
        typer.Option("--action", help="Whether to add to or remove from qualifier-required keywords."),
    ] = "add",
    allow_removal: Annotated[
        bool,
        typer.Option("--allow-removal", help="Allow removing terms from this qualifier requirement set."),
    ] = False,
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    if action == "remove" and not allow_removal:
        raise typer.BadParameter("qualifier-required-keyword removals require --allow-removal")
    _add_runtime_set_update_rule(
        surface=RUNTIME_SET_UPDATE_SURFACES["qualifier-required-keyword"],
        terms_csv=terms_csv,
        action=action,
        reason=reason,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


def _add_runtime_term_set_command(
    *,
    surface: RuntimeTermSetSurface,
    terms_csv: str,
    reason: str,
    policy_ref: str | None,
    tree_root: Path | None,
    run_gates: bool,
    report_root: Path | None,
    dry_run: bool,
    write_sanity: bool,
) -> None:
    _add_runtime_term_set_rule(
        surface=surface,
        terms_csv=terms_csv,
        reason=reason,
        allow_broad=False,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("carrier-context-required")
def add_carrier_context_required(
    terms_csv: Annotated[str, typer.Option("--terms", help="Comma-separated carriers that require ingredient context.")],
    reason: Annotated[str, typer.Option("--reason", help="Why these carriers require recipe-side context.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_runtime_term_set_command(
        surface=RUNTIME_TERM_SET_SURFACES["carrier-context-required"],
        terms_csv=terms_csv,
        reason=reason,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("context-required-word")
def add_context_required_word(
    terms_csv: Annotated[str, typer.Option("--terms", help="Comma-separated product context words required in ingredients.")],
    reason: Annotated[str, typer.Option("--reason", help="Why these product words require ingredient context.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_runtime_term_set_command(
        surface=RUNTIME_TERM_SET_SURFACES["context-required-word"],
        terms_csv=terms_csv,
        reason=reason,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("ingredient-requires-product-context")
def add_ingredient_requires_product_context(
    terms_csv: Annotated[str, typer.Option("--terms", help="Comma-separated ingredient words that products must repeat.")],
    reason: Annotated[str, typer.Option("--reason", help="Why these ingredient words must also appear in the product.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_runtime_term_set_command(
        surface=RUNTIME_TERM_SET_SURFACES["ingredient-requires-product-context"],
        terms_csv=terms_csv,
        reason=reason,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("cuisine-context")
def add_cuisine_context(
    trigger: Annotated[str, typer.Argument(help="Product trigger term/phrase, e.g. thaikryddad.")],
    contexts_csv: Annotated[
        str,
        typer.Option("--contexts", help="Comma-separated recipe context terms that allow this trigger."),
    ],
    reason: Annotated[str, typer.Option("--reason", help="Why this trigger needs cuisine context.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    trigger = trigger.strip()
    contexts = _split_csv(contexts_csv, label="--contexts")
    if not trigger:
        raise typer.BadParameter("trigger must not be empty")
    if not reason.strip():
        raise typer.BadParameter("--reason must not be empty")
    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root runtime add gates are not available; use --no-run-gates")
    normalized_trigger = _runtime_rule_normalize_text(trigger)
    policy_ref = policy_ref or f"runtime_cuisine_context_{_slug(normalized_trigger)}"
    surface = RUNTIME_CONTEXT_SURFACES["cuisine-context"]
    overlay_preview = _append_runtime_context_entry(
        paths=paths,
        surface=surface,
        trigger=trigger,
        contexts=contexts,
        reason=reason,
        dry_run=dry_run,
    )
    sanity_preview = ""
    if write_sanity:
        sanity_preview = _append_runtime_context_sanity_stub(
            paths=paths,
            surface=surface,
            trigger=trigger,
            contexts=contexts,
            policy_ref=policy_ref,
            dry_run=dry_run,
        )
    if dry_run:
        typer.echo(overlay_preview)
        if sanity_preview:
            typer.echo(sanity_preview)
        typer.echo("Dry run only; no files written.")
        return
    typer.echo(f"Generated cuisine_context rule: {policy_ref}")
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))


@matcher_add_app.command("context-word-exemption")
def add_context_word_exemption(
    keyword: Annotated[str, typer.Argument(help="Keyword exempted from one or more context-required words.")],
    context_words_csv: Annotated[
        str,
        typer.Option("--context-words", help="Comma-separated context words this keyword already implies."),
    ],
    reason: Annotated[str, typer.Option("--reason", help="Why this keyword should ignore these context words.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    keyword = keyword.strip()
    context_words = _split_csv(context_words_csv, label="--context-words")
    if not keyword:
        raise typer.BadParameter("keyword must not be empty")
    if not reason.strip():
        raise typer.BadParameter("--reason must not be empty")
    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root runtime add gates are not available; use --no-run-gates")
    normalized_keyword = _runtime_rule_normalize_text(keyword)
    policy_ref = policy_ref or f"runtime_context_word_exemption_{_slug(normalized_keyword)}"
    surface = RUNTIME_CONTEXT_SURFACES["context-word-exemption"]
    overlay_preview = _append_runtime_context_entry(
        paths=paths,
        surface=surface,
        trigger=keyword,
        contexts=context_words,
        reason=reason,
        dry_run=dry_run,
    )
    sanity_preview = ""
    if write_sanity:
        sanity_preview = _append_runtime_context_sanity_stub(
            paths=paths,
            surface=surface,
            trigger=keyword,
            contexts=context_words,
            policy_ref=policy_ref,
            dry_run=dry_run,
        )
    if dry_run:
        typer.echo(overlay_preview)
        if sanity_preview:
            typer.echo(sanity_preview)
        typer.echo("Dry run only; no files written.")
        return
    typer.echo(f"Generated {surface.section} rule: {policy_ref}")
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))


@matcher_add_app.command("product-name-substitution")
def add_product_name_substitution(
    required_words_csv: Annotated[
        str,
        typer.Option("--required-words", help="Comma-separated words that must appear in the product name."),
    ],
    old_keyword: Annotated[str, typer.Option("--old-keyword", help="Keyword to replace when required words match.")],
    new_keyword: Annotated[str, typer.Option("--new-keyword", help="Replacement keyword.")],
    reason: Annotated[str, typer.Option("--reason", help="Why this product-name substitution is needed.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    required_words = _split_csv(required_words_csv, label="--required-words")
    if not old_keyword.strip():
        raise typer.BadParameter("--old-keyword must not be empty")
    if not new_keyword.strip():
        raise typer.BadParameter("--new-keyword must not be empty")
    if not reason.strip():
        raise typer.BadParameter("--reason must not be empty")
    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root runtime add gates are not available; use --no-run-gates")
    normalized_old = _runtime_rule_normalize_text(old_keyword)
    normalized_new = _runtime_rule_normalize_text(new_keyword)
    policy_ref = policy_ref or f"runtime_product_name_substitution_{_slug(normalized_old)}_{_slug(normalized_new)}"
    overlay_preview = _append_product_substitution_entry(
        paths=paths,
        required_words=required_words,
        old_keyword=old_keyword,
        new_keyword=new_keyword,
        reason=reason,
        dry_run=dry_run,
    )
    sanity_preview = ""
    if write_sanity:
        sanity_preview = _append_product_substitution_sanity_stub(
            paths=paths,
            required_words=required_words,
            old_keyword=old_keyword,
            new_keyword=new_keyword,
            policy_ref=policy_ref,
            dry_run=dry_run,
        )
    if dry_run:
        typer.echo(overlay_preview)
        if sanity_preview:
            typer.echo(sanity_preview)
        typer.echo("Dry run only; no files written.")
        return
    typer.echo(f"Generated product_name_substitution rule: {policy_ref}")
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))


@matcher_add_app.command("secondary-ingredient-pattern")
def add_secondary_ingredient_pattern(
    keyword: Annotated[str, typer.Argument(help="Matched keyword to block when product contains blockers.")],
    blockers_csv: Annotated[str, typer.Option("--blockers", help="Comma-separated product-side blockers.")],
    reason: Annotated[str, typer.Option("--reason", help="Why this secondary pattern is needed.")],
    exceptions_csv: Annotated[
        str | None,
        typer.Option("--exceptions", help="Comma-separated product-side exceptions that keep the match allowed."),
    ] = None,
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    keyword = keyword.strip()
    blockers = _split_csv(blockers_csv, label="--blockers")
    exceptions = _split_csv(exceptions_csv, label="--exceptions") if exceptions_csv else ()
    if not keyword:
        raise typer.BadParameter("keyword must not be empty")
    if not reason.strip():
        raise typer.BadParameter("--reason must not be empty")
    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root runtime add gates are not available; use --no-run-gates")
    normalized_keyword = _runtime_rule_normalize_text(keyword)
    policy_ref = policy_ref or f"runtime_secondary_ingredient_pattern_{_slug(normalized_keyword)}"
    overlay_preview = _append_secondary_pattern_entry(
        paths=paths,
        keyword=keyword,
        blockers=blockers,
        exceptions=exceptions,
        reason=reason,
        dry_run=dry_run,
    )
    sanity_preview = ""
    if write_sanity:
        sanity_preview = _append_secondary_pattern_sanity_stub(
            paths=paths,
            keyword=keyword,
            blockers=blockers,
            exceptions=exceptions,
            policy_ref=policy_ref,
            dry_run=dry_run,
        )
    if dry_run:
        typer.echo(overlay_preview)
        if sanity_preview:
            typer.echo(sanity_preview)
        typer.echo("Dry run only; no files written.")
        return
    typer.echo(f"Generated secondary_ingredient_pattern rule: {policy_ref}")
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))


@matcher_add_app.command("compound-protection")
def add_compound_protection(
    keywords_csv: Annotated[str, typer.Option("--keywords", help="Comma-separated keywords to protect.")],
    mode: Annotated[
        Literal["suffix-strict", "prefix-strict", "suffix-protected", "embedded-protected"],
        typer.Option("--mode", help="Compound protection mode."),
    ],
    reason: Annotated[str, typer.Option("--reason", help="Why this compound protection is needed.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    keywords = _split_csv(keywords_csv, label="--keywords")
    if not reason.strip():
        raise typer.BadParameter("--reason must not be empty")
    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root runtime add gates are not available; use --no-run-gates")
    normalized_mode = mode.replace("-", "_")
    policy_ref = policy_ref or f"runtime_compound_protection_{normalized_mode}_{_slug(keywords[0])}"
    surface = RUNTIME_COMPOUND_SURFACES["compound-protection"]
    overlay_preview = _append_runtime_compound_entry(
        paths=paths,
        surface=surface,
        mode=mode,
        keywords=keywords,
        reason=reason,
        dry_run=dry_run,
    )
    sanity_preview = ""
    if write_sanity:
        sanity_preview = _append_runtime_compound_sanity_stub(
            paths=paths,
            mode=mode,
            keywords=keywords,
            policy_ref=policy_ref,
            dry_run=dry_run,
        )
    if dry_run:
        typer.echo(overlay_preview)
        if sanity_preview:
            typer.echo(sanity_preview)
        typer.echo("Dry run only; no files written.")
        return
    typer.echo(f"Generated compound_protection rule: {policy_ref}")
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))


def _add_runtime_specialty_rule(
    *,
    surface: RuntimeSpecialtySurface,
    key: str,
    values_csv: str,
    reason: str,
    bidirectional: bool,
    policy_ref: str | None,
    tree_root: Path | None,
    run_gates: bool,
    report_root: Path | None,
    dry_run: bool,
    write_sanity: bool,
) -> None:
    key = key.strip()
    values = _split_csv(values_csv, label=f"--{surface.values_field.replace('_', '-')}")
    if not key:
        raise typer.BadParameter(f"{surface.key_field} must not be empty")
    if not reason.strip():
        raise typer.BadParameter("--reason must not be empty")
    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root runtime add gates are not available; use --no-run-gates")
    normalized_key = _runtime_rule_normalize_text(key)
    policy_ref = policy_ref or f"runtime_{surface.command.replace('-', '_')}_{_slug(normalized_key)}"
    overlay_preview = _append_runtime_specialty_entry(
        paths=paths,
        surface=surface,
        key=key,
        values=values,
        reason=reason,
        bidirectional=bidirectional,
        dry_run=dry_run,
    )
    sanity_preview = ""
    if write_sanity:
        sanity_preview = _append_runtime_specialty_sanity_stub(
            paths=paths,
            surface=surface,
            key=key,
            values=values,
            policy_ref=policy_ref,
            bidirectional=bidirectional,
            dry_run=dry_run,
        )
    if dry_run:
        typer.echo(overlay_preview)
        if sanity_preview:
            typer.echo(sanity_preview)
        typer.echo("Dry run only; no files written.")
        return
    typer.echo(f"Generated {surface.section} rule: {policy_ref}")
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))


@matcher_add_app.command("specialty-qualifier")
def add_specialty_qualifier(
    keyword: Annotated[str, typer.Argument(help="Base keyword whose variants need qualifiers.")],
    qualifiers_csv: Annotated[str, typer.Option("--qualifiers", help="Comma-separated qualifiers.")],
    reason: Annotated[str, typer.Option("--reason", help="Why these qualifiers are required.")],
    bidirectional: Annotated[
        bool,
        typer.Option("--bidirectional", help="Also require the qualifier from product to ingredient."),
    ] = False,
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_runtime_specialty_rule(
        surface=RUNTIME_SPECIALTY_SURFACES["specialty-qualifier"],
        key=keyword,
        values_csv=qualifiers_csv,
        reason=reason,
        bidirectional=bidirectional,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("qualifier-equivalent")
def add_qualifier_equivalent(
    qualifier: Annotated[str, typer.Argument(help="Qualifier key.")],
    equivalents_csv: Annotated[str, typer.Option("--equivalents", help="Comma-separated equivalent terms.")],
    reason: Annotated[str, typer.Option("--reason", help="Why these qualifiers are equivalent.")],
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Append a focused deep-sanity canary."),
    ] = True,
) -> None:
    _add_runtime_specialty_rule(
        surface=RUNTIME_SPECIALTY_SURFACES["qualifier-equivalent"],
        key=qualifier,
        values_csv=equivalents_csv,
        reason=reason,
        bidirectional=False,
        policy_ref=policy_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_add_app.command("ingredient-parent")
def add_ingredient_parent(
    canonical: Annotated[str, typer.Argument(help="Existing parent canonical, e.g. ris.")],
    variants_csv: Annotated[str, typer.Option("--variants", help="Comma-separated recipe-side variants.")],
    sanity_offer: Annotated[
        str | None,
        typer.Option("--sanity-offer", help="Offer name for the generated deep-sanity regression."),
    ] = None,
    sanity_ingredient: Annotated[
        str | None,
        typer.Option("--sanity-ingredient", help="Ingredient text for the generated deep-sanity regression."),
    ] = None,
    offer_category: Annotated[str, typer.Option("--offer-category", help="Offer category for sanity.")] = "pantry",
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable policy ref override.")] = None,
    source_ref: Annotated[str | None, typer.Option("--source-ref", help="Stable source ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run light registry/sanity gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
) -> None:
    _add_simple_toml_surface(
        surface=SIMPLE_TOML_SURFACES["ingredient-parent"],
        canonical=canonical,
        variants_csv=variants_csv,
        term_values_csv=None,
        sanity_ingredient=sanity_ingredient,
        sanity_offer=sanity_offer,
        offer_category=offer_category,
        sanity_mode="fast-match",
        policy_ref=policy_ref,
        source_ref=source_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
    )


@matcher_add_app.command("offer-extra-keyword")
def add_offer_extra_keyword(
    canonical: Annotated[str, typer.Argument(help="Primary canonical offer keyword exposed by the product term.")],
    variants_csv: Annotated[str, typer.Option("--variants", help="Comma-separated product terms.")],
    offer_terms_csv: Annotated[
        str | None,
        typer.Option("--offer-terms", help="Comma-separated canonical offer keywords; defaults to canonical."),
    ] = None,
    sanity_ingredient: Annotated[
        str | None,
        typer.Option("--sanity-ingredient", help="Ingredient text for the generated deep-sanity regression."),
    ] = None,
    sanity_offer: Annotated[
        str | None,
        typer.Option("--sanity-offer", help="Offer name for the generated deep-sanity regression."),
    ] = None,
    offer_category: Annotated[str, typer.Option("--offer-category", help="Offer category for sanity.")] = "pantry",
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable policy ref override.")] = None,
    source_ref: Annotated[str | None, typer.Option("--source-ref", help="Stable source ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run light registry/sanity gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
) -> None:
    _add_simple_toml_surface(
        surface=SIMPLE_TOML_SURFACES["offer-extra-keyword"],
        canonical=canonical,
        variants_csv=variants_csv,
        term_values_csv=offer_terms_csv,
        sanity_ingredient=sanity_ingredient,
        sanity_offer=sanity_offer,
        offer_category=offer_category,
        sanity_mode="fast-match",
        policy_ref=policy_ref,
        source_ref=source_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
    )


@matcher_add_app.command("ingredient-routing-parent")
def add_ingredient_routing_parent(
    canonical: Annotated[str, typer.Argument(help="Parent canonical route term.")],
    variants_csv: Annotated[str, typer.Option("--variants", help="Comma-separated ingredient/product variants.")],
    sanity_offer: Annotated[
        str | None,
        typer.Option("--sanity-offer", help="Offer name for the generated deep-sanity regression."),
    ] = None,
    sanity_ingredient: Annotated[
        str | None,
        typer.Option("--sanity-ingredient", help="Ingredient text for the generated deep-sanity regression."),
    ] = None,
    offer_category: Annotated[str, typer.Option("--offer-category", help="Offer category for sanity.")] = "pantry",
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable policy ref override.")] = None,
    source_ref: Annotated[str | None, typer.Option("--source-ref", help="Stable source ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run light registry/sanity gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
) -> None:
    _add_simple_toml_surface(
        surface=SIMPLE_TOML_SURFACES["ingredient-routing-parent"],
        canonical=canonical,
        variants_csv=variants_csv,
        term_values_csv=None,
        sanity_ingredient=sanity_ingredient,
        sanity_offer=sanity_offer,
        offer_category=offer_category,
        sanity_mode="fast-match",
        policy_ref=policy_ref,
        source_ref=source_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
    )


@matcher_add_app.command("parent-match-only")
def add_parent_match_only(
    canonical: Annotated[str, typer.Argument(help="Parent canonical route term.")],
    variants_csv: Annotated[str, typer.Option("--variants", help="Comma-separated product compounds.")],
    sanity_offer: Annotated[
        str | None,
        typer.Option("--sanity-offer", help="Offer name for the generated deep-sanity regression."),
    ] = None,
    sanity_ingredient: Annotated[
        str | None,
        typer.Option("--sanity-ingredient", help="Ingredient text for the generated deep-sanity regression."),
    ] = None,
    negative_ingredient: Annotated[
        str | None,
        typer.Option("--negative-ingredient", help="Ingredient text for generated strictness/no-match sanity proof."),
    ] = None,
    negative_offer: Annotated[
        str | None,
        typer.Option("--negative-offer", help="Offer name for generated strictness/no-match sanity proof."),
    ] = None,
    offer_category: Annotated[str, typer.Option("--offer-category", help="Offer category for sanity.")] = "pantry",
    negative_offer_category: Annotated[
        str | None,
        typer.Option("--negative-offer-category", help="Offer category for the generated negative sanity proof."),
    ] = None,
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable policy ref override.")] = None,
    source_ref: Annotated[str | None, typer.Option("--source-ref", help="Stable source ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run light registry/sanity gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
) -> None:
    _add_simple_toml_surface(
        surface=SIMPLE_TOML_SURFACES["parent-match-only"],
        canonical=canonical,
        variants_csv=variants_csv,
        term_values_csv=None,
        sanity_ingredient=sanity_ingredient,
        sanity_offer=sanity_offer,
        offer_category=offer_category,
        negative_sanity_ingredient=negative_ingredient,
        negative_sanity_offer=negative_offer,
        negative_offer_category=negative_offer_category,
        sanity_mode="fast-match",
        policy_ref=policy_ref,
        source_ref=source_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
    )


@matcher_add_app.command("recipe-routing-helper")
def add_recipe_routing_helper(
    canonical: Annotated[str, typer.Argument(help="Parent canonical route term.")],
    variants_csv: Annotated[str, typer.Option("--variants", help="Comma-separated recipe-routing aliases.")],
    sanity_ingredient: Annotated[
        str | None,
        typer.Option("--sanity-ingredient", help="Ingredient text for the generated deep-sanity regression."),
    ] = None,
    sanity_offer: Annotated[
        str | None,
        typer.Option("--sanity-offer", help="Offer name for the generated deep-sanity regression."),
    ] = None,
    offer_category: Annotated[str, typer.Option("--offer-category", help="Offer category for sanity.")] = "pantry",
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable policy ref override.")] = None,
    source_ref: Annotated[str | None, typer.Option("--source-ref", help="Stable source ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run light registry/sanity gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
) -> None:
    _add_simple_toml_surface(
        surface=SIMPLE_TOML_SURFACES["recipe-routing-helper"],
        canonical=canonical,
        variants_csv=variants_csv,
        term_values_csv=None,
        sanity_ingredient=sanity_ingredient,
        sanity_offer=sanity_offer,
        offer_category=offer_category,
        sanity_mode="fast-match",
        policy_ref=policy_ref,
        source_ref=source_ref,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
    )


@matcher_add_app.command("smart-blocker")
def add_smart_blocker(
    name: Annotated[str, typer.Argument(help="Stable blocker name, used for the generated function name.")],
    description: Annotated[str, typer.Option("--description", help="Docstring/TODO description for the blocker.")],
    uses_product_keywords: Annotated[
        bool,
        typer.Option("--uses-product-keywords", help="Pass product_keywords into the generated blocker call."),
    ] = False,
    sanity_ingredient: Annotated[
        str | None,
        typer.Option("--sanity-ingredient", help="Optional sanity ingredient for a focused canary."),
    ] = None,
    sanity_offer: Annotated[
        str | None,
        typer.Option("--sanity-offer", help="Optional sanity offer for a focused canary."),
    ] = None,
    expect: Annotated[
        Literal["match", "no-match"],
        typer.Option("--expect", help="Expected result for optional sanity canary."),
    ] = "no-match",
    offer_category: Annotated[str, typer.Option("--offer-category", help="Offer category for optional sanity.")] = "pantry",
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable sanity policy ref override.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run light sanity/preflight gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the scaffold without writing files.")] = False,
) -> None:
    if not name.strip():
        raise typer.BadParameter("name must not be empty")
    if not description.strip():
        raise typer.BadParameter("--description must not be empty")
    if (sanity_ingredient is None) != (sanity_offer is None):
        raise typer.BadParameter("--sanity-ingredient and --sanity-offer must be provided together")

    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root smart-blocker gates are not available; use --no-run-gates")

    function_name, call = _insert_smart_blocker_scaffold(
        paths=paths,
        name=name,
        description=description,
        uses_product_keywords=uses_product_keywords,
        dry_run=dry_run,
    )
    policy_ref = policy_ref or f"smart_blocker_{_python_identifier_slug(name)}"
    sanity_preview = ""
    if sanity_ingredient is not None and sanity_offer is not None:
        sanity_preview = "\n".join([
            "",
            *_generated_sanity_header(policy_ref, "smart-blocker"),
            *_deep_sanity_match_assertion(
                description=f"smart-blocker {name}",
                offer_name=sanity_offer.strip(),
                ingredient=sanity_ingredient.strip(),
                offer_category=offer_category,
                expected_canonical=None if expect == "no-match" else name.strip().lower(),
                mode="fast-match",
            ),
        ]) + "\n"
        _append_text_block(paths.deep_sanity_file, sanity_preview, dry_run=dry_run, trim_existing=True)

    if dry_run:
        typer.echo(_smart_blocker_stub(
            function_name=function_name,
            description=description,
            uses_product_keywords=uses_product_keywords,
        ))
        typer.echo(f"Product requirement guard chain call: and {call}")
        if sanity_preview:
            typer.echo(sanity_preview)
        typer.echo("Dry run only; no files written.")
        return

    typer.echo(f"Generated smart-blocker scaffold: {function_name}")
    typer.echo(f"  chained call: {call}")
    typer.echo("  TODO: implement the function body; scaffold returns True until filled in.")
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    gate_status = _run_keyword_synonym_light_gates(paths=paths, report_root=report_root)
    raise typer.Exit(gate_status)


@matcher_add_app.command("no-match-policy")
def add_no_match_policy(
    canonical: Annotated[str, typer.Argument(help="Canonical/policy family to guard, e.g. cheddarost.")],
    ingredient_patterns_csv: Annotated[
        str,
        typer.Option("--ingredient-patterns", help="Comma-separated regex patterns for recipe ingredient text."),
    ],
    blocked_offer_keywords_csv: Annotated[
        str | None,
        typer.Option("--blocked-offer-keywords", help="Comma-separated offer keywords to block."),
    ] = None,
    blocked_offer_patterns_csv: Annotated[
        str | None,
        typer.Option("--blocked-offer-patterns", help="Comma-separated offer regex patterns to block."),
    ] = None,
    reason: Annotated[str, typer.Option("--reason", help="Human policy reason stored with the rule.")] = "",
    negative_ingredient: Annotated[
        str | None,
        typer.Option("--negative-ingredient", help="Ingredient text for generated negative sanity proof."),
    ] = None,
    negative_offer: Annotated[
        str | None,
        typer.Option("--negative-offer", help="Offer name for generated negative sanity proof."),
    ] = None,
    allowed_specifics_csv: Annotated[
        str | None,
        typer.Option("--allowed-specifics", help="Comma-separated specific terms that are allowed."),
    ] = None,
    fixture_refs_csv: Annotated[
        str,
        typer.Option("--fixture-refs", help="Comma-separated existing fixture refs covered by this policy."),
    ] = "",
    auto_fixture: Annotated[
        bool,
        typer.Option("--auto-fixture", help="Create or reuse one negative matcher fixture from --negative-* fields."),
    ] = False,
    auto_inventory: Annotated[
        bool,
        typer.Option("--auto-inventory", help="Create one matcher inventory row covering this no-match policy."),
    ] = False,
    inventory_id_override: Annotated[
        str | None,
        typer.Option("--inventory-id", help="Stable inventory id when --auto-inventory is used."),
    ] = None,
    source_ref: Annotated[
        str | None,
        typer.Option("--source-ref", help="Stable source ref for auto-created fixture/inventory rows."),
    ] = None,
    supersedes_csv: Annotated[
        str | None,
        typer.Option("--supersedes", help="Comma-separated legacy refs superseded by this policy."),
    ] = None,
    policy_id: Annotated[str | None, typer.Option("--policy-id", help="Stable no-match policy id.")] = None,
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable policy ref override.")] = None,
    offer_category: Annotated[str, typer.Option("--offer-category", help="Offer category for sanity.")] = "pantry",
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run light registry/sanity gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
) -> None:
    canonical = canonical.strip().lower()
    if not canonical:
        raise typer.BadParameter("canonical must not be empty")
    ingredient_patterns = _split_csv(ingredient_patterns_csv, label="--ingredient-patterns", lowercase=False)
    blocked_offer_keywords = (
        _split_csv(blocked_offer_keywords_csv, label="--blocked-offer-keywords")
        if blocked_offer_keywords_csv
        else ()
    )
    blocked_offer_patterns = (
        _split_csv(blocked_offer_patterns_csv, label="--blocked-offer-patterns", lowercase=False)
        if blocked_offer_patterns_csv
        else ()
    )
    if not blocked_offer_keywords and not blocked_offer_patterns:
        raise typer.BadParameter("provide --blocked-offer-keywords, --blocked-offer-patterns, or both")
    if not reason.strip():
        raise typer.BadParameter("--reason must not be empty")
    if negative_ingredient is None or not negative_ingredient.strip():
        raise typer.BadParameter("--negative-ingredient is required")
    if negative_offer is None or not negative_offer.strip():
        raise typer.BadParameter("--negative-offer is required")
    allowed_specifics = (
        _split_csv(allowed_specifics_csv, label="--allowed-specifics")
        if allowed_specifics_csv
        else ()
    )
    supersedes = (
        _split_csv(supersedes_csv, label="--supersedes", lowercase=False)
        if supersedes_csv
        else ()
    )
    canonical_slug = _slug(canonical)
    first_guard_slug = _slug((blocked_offer_keywords or blocked_offer_patterns)[0])
    policy_id = policy_id.strip() if policy_id is not None else f"policy_{canonical_slug}_{first_guard_slug}"
    if not policy_id:
        raise typer.BadParameter("--policy-id must not be empty")
    policy_ref = policy_ref or policy_id
    source_ref = source_ref.strip() if source_ref is not None else f"manual:{policy_ref}"
    if not source_ref:
        raise typer.BadParameter("--source-ref must not be empty")
    explicit_fixture_refs = (
        _split_csv(fixture_refs_csv, label="--fixture-refs", lowercase=False)
        if fixture_refs_csv.strip()
        else ()
    )
    if not explicit_fixture_refs and not auto_fixture:
        raise typer.BadParameter("provide --fixture-refs or pass --auto-fixture")
    if inventory_id_override is not None and not auto_inventory:
        raise typer.BadParameter("--inventory-id requires --auto-inventory")
    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root light gates are not available; use --no-run-gates")
    if explicit_fixture_refs:
        _ensure_fixture_refs_exist(paths, explicit_fixture_refs)
    auto_fixture_id = _no_match_auto_fixture_id(policy_id) if auto_fixture else None
    inventory_id = None
    if auto_inventory:
        inventory_id = (
            inventory_id_override.strip()
            if inventory_id_override is not None
            else _no_match_auto_inventory_id(policy_id)
        )
        if not inventory_id:
            raise typer.BadParameter("--inventory-id must not be empty")
        _ensure_no_match_inventory_id_available(paths, inventory_id)
    auto_fixture_refs: tuple[str, ...] = ()
    auto_fixture_created = False
    if auto_fixture_id is not None:
        _append_or_reuse_no_match_fixture(
            paths=paths,
            fixture_id=auto_fixture_id,
            policy_ref=policy_ref,
            source_ref=source_ref,
            negative_ingredient=negative_ingredient.strip(),
            negative_offer=negative_offer.strip(),
            offer_category=offer_category,
            dry_run=True,
        )
        auto_fixture_refs = (auto_fixture_id,)
    fixture_refs = tuple(dict.fromkeys((*explicit_fixture_refs, *auto_fixture_refs)))

    entry_id, entry_line, toml_preview = _append_no_match_policy_entry(
        paths=paths,
        policy_id=policy_id,
        canonical=canonical,
        ingredient_patterns=ingredient_patterns,
        blocked_offer_keywords=blocked_offer_keywords,
        blocked_offer_patterns=blocked_offer_patterns,
        allowed_specifics=allowed_specifics,
        reason=reason.strip(),
        policy_ref=policy_ref,
        fixture_refs=fixture_refs,
        supersedes=supersedes,
        negative_ingredient=negative_ingredient.strip(),
        negative_offer=negative_offer.strip(),
        offer_category=offer_category,
        dry_run=dry_run,
    )
    if auto_fixture_id is not None:
        _fixture_id, auto_fixture_created = _append_or_reuse_no_match_fixture(
            paths=paths,
            fixture_id=auto_fixture_id,
            policy_ref=policy_ref,
            source_ref=source_ref,
            negative_ingredient=negative_ingredient.strip(),
            negative_offer=negative_offer.strip(),
            offer_category=offer_category,
            dry_run=dry_run,
        )
    if auto_inventory:
        assert inventory_id is not None
        _append_no_match_inventory(
            paths=paths,
            inventory_id=inventory_id,
            policy_id=policy_id,
            policy_ref=policy_ref,
            canonical=canonical,
            fixture_refs=fixture_refs,
            source_ref=source_ref,
            reason=reason.strip(),
            entry_id=entry_id,
            entry_line=entry_line,
            dry_run=dry_run,
        )
    sanity_preview = _append_no_match_deep_sanity_stub(
        paths=paths,
        policy_ref=policy_ref,
        negative_ingredient=negative_ingredient.strip(),
        negative_offer=negative_offer.strip(),
        offer_category=offer_category,
        sanity_mode="fast-match",
        dry_run=dry_run,
    )
    change = MatcherChangePlan(
        command="no-match-policy",
        policy_ref=policy_ref,
        entry_ids=(entry_id,),
        fixture_ids=fixture_refs,
        inventory_id=inventory_id,
        toml_preview=toml_preview,
        sanity_preview=sanity_preview,
        runtime_delta_filename="no_match_policy.toml",
    )
    if dry_run:
        _print_dry_run_preview(change)
        return

    typer.echo(f"Generated no_match_policy rule: {change.policy_ref}")
    typer.echo(f"  entry: {entry_id}")
    if auto_fixture_id is not None:
        verb = "created" if auto_fixture_created else "reused"
        typer.echo(f"  auto fixture {verb}: {auto_fixture_id}")
    if inventory_id is not None:
        typer.echo(f"  auto inventory: {inventory_id}")
    if auto_fixture or auto_inventory:
        _regenerate_contract_json(paths)
    _print_generated_sanity_probe(paths, change.policy_ref)
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    if auto_fixture or auto_inventory:
        gate_status = _run_track_b_change_plan(paths=paths, change=change, report_root=report_root)
    else:
        gate_status = _run_keyword_synonym_light_gates(paths=paths, report_root=report_root)
    raise typer.Exit(gate_status)


def _modify_runtime_overlay_rule_by_id(
    *,
    rule_id: str,
    add_value_csv: str | None,
    remove_value_csv: str | None,
    add_blocker_csv: str | None,
    remove_blocker_csv: str | None,
    add_context_csv: str | None,
    remove_context_csv: str | None,
    reason: str,
    tree_root: Path | None,
    run_gates: bool,
    report_root: Path | None,
    dry_run: bool,
    write_sanity: bool,
) -> None:
    reason = reason.strip()
    if not reason:
        raise typer.BadParameter("--reason is required for runtime overlay modifications")
    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root runtime modify gates are not available; use --no-run-gates")
    sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
    surface, entry = _find_runtime_overlay_entry_by_id(sections, rule_id)
    if not _runtime_overlay_entry_is_active(entry):
        raise typer.BadParameter(f"{rule_id} is inactive; reactivate or add a new rule instead")
    add_values, remove_values = _runtime_overlay_requested_value_changes(
        surface=surface,
        add_value_csv=add_value_csv,
        remove_value_csv=remove_value_csv,
        add_blocker_csv=add_blocker_csv,
        remove_blocker_csv=remove_blocker_csv,
        add_context_csv=add_context_csv,
        remove_context_csv=remove_context_csv,
    )
    if not add_values and not remove_values:
        raise typer.BadParameter("provide at least one add/remove value option")

    field = surface.value_field
    keyword = _runtime_rule_normalize_text(str(entry.get("keyword", "")))
    old_values = tuple(_runtime_overlay_entry_values(entry, field))
    old_value_set = set(old_values)
    missing = sorted(value for value in remove_values if value not in old_value_set)
    if missing:
        raise typer.BadParameter(f"{rule_id} does not contain {', '.join(missing)}")
    base_values = _live_runtime_mapping_values(surface, keyword, paths) - old_value_set
    duplicates = sorted(value for value in add_values if value in old_value_set or value in base_values)
    if duplicates:
        raise typer.BadParameter(f"{rule_id} already has effective {field}: {', '.join(duplicates)}")
    new_values = [
        value
        for value in old_values
        if value not in set(remove_values)
    ]
    for value in add_values:
        if value not in new_values:
            new_values.append(value)
    if not new_values:
        raise typer.BadParameter(
            f"modify would empty {rule_id}; use `dm matcher remove {rule_id} --reason \"...\"` instead"
        )

    entry["id"] = str(entry.get("id") or rule_id)
    entry["status"] = "active"
    entry["keyword"] = keyword
    entry[field] = new_values
    entry.pop("inactive_reason", None)
    existing_reason = str(entry.get("reason", "")).strip()
    if reason not in existing_reason:
        entry["reason"] = f"{existing_reason}; {reason}" if existing_reason else reason
    preview = _runtime_overlay_entry_block(surface, entry)
    if dry_run:
        typer.echo(preview)
        if write_sanity:
            removed = _remove_runtime_overlay_sanity_membership_tests(
                paths=paths,
                surface=surface,
                keyword=keyword,
                values=old_values,
                dry_run=True,
            )
            typer.echo(f"Would remove {removed} generated sanity membership test(s).")
            typer.echo(_append_runtime_overlay_deep_sanity_stub(
                paths=paths,
                surface=surface,
                keyword=keyword,
                values=tuple(new_values),
                policy_ref=rule_id,
                dry_run=True,
            ))
        typer.echo("Dry run only; no files written.")
        return

    paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
    removed = 0
    if write_sanity:
        removed = _remove_runtime_overlay_sanity_membership_tests(
            paths=paths,
            surface=surface,
            keyword=keyword,
            values=old_values,
            dry_run=False,
        )
        _append_runtime_overlay_deep_sanity_stub(
            paths=paths,
            surface=surface,
            keyword=keyword,
            values=tuple(new_values),
            policy_ref=rule_id,
            dry_run=False,
        )
    typer.echo(f"Modified runtime overlay rule: {rule_id}")
    typer.echo(f"  surface: {surface.command}")
    typer.echo(f"  keyword: {keyword}")
    typer.echo(f"  {field}: {', '.join(new_values)}")
    if write_sanity:
        typer.echo(f"  sanity: rewrote membership canary ({removed} old test(s) removed)")
    else:
        typer.echo("  sanity: skipped")
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))


def _remove_runtime_overlay_rule_by_id(
    *,
    rule_id: str,
    reason: str,
    tree_root: Path | None,
    run_gates: bool,
    report_root: Path | None,
    dry_run: bool,
    write_sanity: bool,
) -> None:
    reason = reason.strip()
    if not reason:
        raise typer.BadParameter("--reason is required; runtime overlay removal is a deliberate policy change")
    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root runtime remove gates are not available; use --no-run-gates")
    sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
    surface, entry = _find_runtime_overlay_entry_by_id(sections, rule_id)
    field = surface.value_field
    keyword = _runtime_rule_normalize_text(str(entry.get("keyword", "")))
    old_values = tuple(_runtime_overlay_entry_values(entry, field))
    entry["id"] = str(entry.get("id") or rule_id)
    entry["status"] = "inactive"
    entry["inactive_reason"] = reason
    preview = _runtime_overlay_entry_block(surface, entry)
    if dry_run:
        typer.echo(preview)
        if write_sanity:
            removed = _remove_runtime_overlay_sanity_membership_tests(
                paths=paths,
                surface=surface,
                keyword=keyword,
                values=old_values,
                dry_run=True,
            )
            typer.echo(f"Would remove {removed} generated sanity membership test(s).")
        typer.echo("Dry run only; no files written.")
        return

    paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
    removed = 0
    if write_sanity:
        removed = _remove_runtime_overlay_sanity_membership_tests(
            paths=paths,
            surface=surface,
            keyword=keyword,
            values=old_values,
            dry_run=False,
        )
    typer.echo(f"Removed runtime overlay rule: {rule_id}")
    typer.echo("  mode: soft-disable (status=inactive)")
    typer.echo(f"  surface: {surface.command}")
    typer.echo(f"  keyword: {keyword}")
    if write_sanity:
        typer.echo(f"  sanity: removed {removed} generated membership test(s)")
    else:
        typer.echo("  sanity: skipped")
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))


@matcher_modify_app.command("overlay")
@matcher_modify_app.command("runtime-overlay")
def modify_runtime_overlay(
    rule_id: Annotated[
        str,
        typer.Argument(help="Runtime overlay rule id to modify, e.g. runtime_pnb_gradde."),
    ],
    add_value_csv: Annotated[
        str | None,
        typer.Option("--add-value", help="Comma-separated value(s) to add to the rule's value field."),
    ] = None,
    remove_value_csv: Annotated[
        str | None,
        typer.Option("--remove-value", help="Comma-separated value(s) to remove from the rule's value field."),
    ] = None,
    add_blocker_csv: Annotated[
        str | None,
        typer.Option("--add-blocker", help="Comma-separated blocker(s) to add to a PNB/FPB rule."),
    ] = None,
    remove_blocker_csv: Annotated[
        str | None,
        typer.Option("--remove-blocker", help="Comma-separated blocker(s) to remove from a PNB/FPB rule."),
    ] = None,
    add_context_csv: Annotated[
        str | None,
        typer.Option("--add-context", help="Comma-separated context term(s) to add to a KSBC rule."),
    ] = None,
    remove_context_csv: Annotated[
        str | None,
        typer.Option("--remove-context", help="Comma-separated context term(s) to remove from a KSBC rule."),
    ] = None,
    reason: Annotated[str, typer.Option("--reason", help="Why the overlay rule is being corrected.")] = "",
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the change without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Rewrite generated membership canaries for this rule."),
    ] = True,
) -> None:
    _modify_runtime_overlay_rule_by_id(
        rule_id=rule_id,
        add_value_csv=add_value_csv,
        remove_value_csv=remove_value_csv,
        add_blocker_csv=add_blocker_csv,
        remove_blocker_csv=remove_blocker_csv,
        add_context_csv=add_context_csv,
        remove_context_csv=remove_context_csv,
        reason=reason,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_modify_app.command("no-match-policy")
def modify_no_match_policy(
    selector: Annotated[str, typer.Argument(help="Policy id, policy ref, entry id, or unique canonical.")],
    set_ingredient_patterns_csv: Annotated[
        str | None,
        typer.Option("--set-ingredient-patterns", help="Comma-separated replacement ingredient regex patterns."),
    ] = None,
    set_blocked_offer_keywords_csv: Annotated[
        str | None,
        typer.Option("--set-blocked-offer-keywords", help="Comma-separated replacement blocked offer keywords."),
    ] = None,
    set_blocked_offer_patterns_csv: Annotated[
        str | None,
        typer.Option("--set-blocked-offer-patterns", help="Comma-separated replacement blocked offer regex patterns."),
    ] = None,
    set_allowed_specifics_csv: Annotated[
        str | None,
        typer.Option("--set-allowed-specifics", help="Comma-separated replacement allowed specific keywords."),
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Replacement human policy reason.")] = None,
    negative_ingredient: Annotated[
        str | None,
        typer.Option("--negative-ingredient", help="Replacement negative example ingredient."),
    ] = None,
    negative_offer: Annotated[
        str | None,
        typer.Option("--negative-offer", help="Replacement negative example offer name."),
    ] = None,
    offer_category: Annotated[
        str | None,
        typer.Option("--offer-category", help="Replacement negative example offer category."),
    ] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run light registry/sanity gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the rewritten entry without writing files.")] = False,
) -> None:
    if not any(
        value is not None
        for value in (
            set_ingredient_patterns_csv,
            set_blocked_offer_keywords_csv,
            set_blocked_offer_patterns_csv,
            set_allowed_specifics_csv,
            reason,
            negative_ingredient,
            negative_offer,
            offer_category,
        )
    ):
        raise typer.BadParameter("provide at least one --set-* or replacement option")

    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root light gates are not available; use --no-run-gates")

    target_file, record, entry, policy = _find_no_match_policy_record(paths, selector)
    canonical = str(policy.get("canonical") or entry.get("canonical") or record.canonical).strip()
    if not canonical:
        raise typer.BadParameter(f"{record.entry_id}: no_match_policy canonical must not be empty")

    old_keywords = _string_tuple(policy.get("blocked_offer_keywords"))
    old_patterns = _string_tuple(policy.get("blocked_offer_patterns"))
    ingredient_patterns = (
        _split_set_csv(set_ingredient_patterns_csv, label="--set-ingredient-patterns", lowercase=False)
        if set_ingredient_patterns_csv is not None
        else _string_tuple(policy.get("ingredient_patterns"))
    )
    blocked_offer_keywords = (
        _split_set_csv(set_blocked_offer_keywords_csv, label="--set-blocked-offer-keywords")
        if set_blocked_offer_keywords_csv is not None
        else old_keywords
    )
    blocked_offer_patterns = (
        _split_set_csv(set_blocked_offer_patterns_csv, label="--set-blocked-offer-patterns", lowercase=False)
        if set_blocked_offer_patterns_csv is not None
        else old_patterns
    )
    allowed_specifics = (
        _split_set_csv(set_allowed_specifics_csv, label="--set-allowed-specifics")
        if set_allowed_specifics_csv is not None
        else _string_tuple(policy.get("allowed_specifics"))
    )
    if (
        ingredient_patterns is None
        or blocked_offer_keywords is None
        or blocked_offer_patterns is None
        or allowed_specifics is None
    ):
        raise typer.BadParameter("internal no-match-policy option parsing error")

    if not ingredient_patterns:
        raise typer.BadParameter("no-match-policy requires at least one ingredient pattern")
    if not blocked_offer_keywords and not blocked_offer_patterns:
        raise typer.BadParameter("no-match-policy requires blocked offer keywords, patterns, or both")

    negative_example = _first_no_match_negative_example(entry)
    old_guard_variants = set(_guard_variants(canonical, old_keywords, old_patterns))
    new_guard_variants = _guard_variants(canonical, blocked_offer_keywords, blocked_offer_patterns)
    existing_negative_offer = str(negative_example.get("offer_name") or "")
    if negative_offer is not None:
        next_negative_offer = negative_offer.strip()
    elif existing_negative_offer in old_guard_variants or existing_negative_offer.startswith(f"{canonical} ! "):
        next_negative_offer = new_guard_variants[0]
    else:
        next_negative_offer = existing_negative_offer or new_guard_variants[0]
    if not next_negative_offer:
        raise typer.BadParameter("--negative-offer must not be empty")

    next_negative_ingredient = (
        negative_ingredient.strip()
        if negative_ingredient is not None
        else str(negative_example.get("ingredient") or canonical)
    )
    if not next_negative_ingredient:
        raise typer.BadParameter("--negative-ingredient must not be empty")

    next_offer_category = (
        offer_category.strip()
        if offer_category is not None
        else str(negative_example.get("offer_category") or "")
    )
    next_reason = reason.strip() if reason is not None else str(policy.get("reason") or entry.get("notes") or "")
    if not next_reason:
        raise typer.BadParameter("--reason must not be empty")

    block = _no_match_policy_block(
        entry_id=record.entry_id,
        policy_id=str(policy.get("id") or selector),
        rule_schema_version=_int_value(policy.get("rule_schema_version"), default=1),
        rule_version=_int_value(policy.get("rule_version"), default=1) + 1,
        canonical=canonical,
        ingredient_patterns=ingredient_patterns,
        blocked_offer_keywords=blocked_offer_keywords,
        blocked_offer_patterns=blocked_offer_patterns,
        allowed_specifics=allowed_specifics,
        reason=next_reason,
        policy_ref=str(policy.get("policy_ref") or selector),
        fixture_refs=_string_tuple(policy.get("fixture_refs")),
        supersedes=_string_tuple(policy.get("supersedes")),
        negative_ingredient=next_negative_ingredient,
        negative_offer=next_negative_offer,
        offer_category=next_offer_category,
    )
    if dry_run:
        typer.echo(block)
        typer.echo("Dry run only; no files written.")
        return

    _write_registry_entry_block(target_file, record, block, dry_run=False)
    typer.echo(f"Updated no_match_policy: {policy.get('id') or selector}")
    typer.echo(f"  entry: {record.entry_id}")
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    gate_status = _run_keyword_synonym_light_gates(paths=paths, report_root=report_root)
    raise typer.Exit(gate_status)


@matcher_modify_app.command("match-bridge")
def modify_match_bridge(
    selector: Annotated[str, typer.Argument(help="Bridge id, entry id, unique canonical, or alias.")],
    set_ingredient_patterns_csv: Annotated[
        str | None,
        typer.Option("--set-ingredient-patterns", help="Comma-separated replacement ingredient regex patterns."),
    ] = None,
    set_offer_patterns_csv: Annotated[
        str | None,
        typer.Option("--set-offer-patterns", help="Comma-separated replacement offer regex patterns."),
    ] = None,
    remove_offer_patterns_csv: Annotated[
        str | None,
        typer.Option("--remove-offer-patterns", help="Comma-separated offer regex patterns to remove."),
    ] = None,
    set_negative_offer_patterns_csv: Annotated[
        str | None,
        typer.Option("--set-negative-offer-patterns", help="Comma-separated replacement negative offer regex patterns."),
    ] = None,
    remove_negative_offer_patterns_csv: Annotated[
        str | None,
        typer.Option("--remove-negative-offer-patterns", help="Comma-separated negative offer regex patterns to remove."),
    ] = None,
    set_aliases_csv: Annotated[
        str | None,
        typer.Option("--set-aliases", help="Comma-separated replacement aliases."),
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Replacement notes text.")] = None,
    positive_ingredient: Annotated[
        str | None,
        typer.Option("--positive-ingredient", help="Replacement positive example ingredient."),
    ] = None,
    positive_offer: Annotated[
        str | None,
        typer.Option("--positive-offer", help="Replacement positive example offer name."),
    ] = None,
    negative_ingredient: Annotated[
        str | None,
        typer.Option("--negative-ingredient", help="Replacement negative example ingredient."),
    ] = None,
    negative_offer: Annotated[
        str | None,
        typer.Option("--negative-offer", help="Replacement negative example offer name."),
    ] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run light registry/sanity gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the rewritten entry without writing files.")] = False,
) -> None:
    if set_offer_patterns_csv is not None and remove_offer_patterns_csv is not None:
        raise typer.BadParameter("--set-offer-patterns conflicts with --remove-offer-patterns")
    if set_negative_offer_patterns_csv is not None and remove_negative_offer_patterns_csv is not None:
        raise typer.BadParameter("--set-negative-offer-patterns conflicts with --remove-negative-offer-patterns")
    if not any(
        value is not None
        for value in (
            set_ingredient_patterns_csv,
            set_offer_patterns_csv,
            remove_offer_patterns_csv,
            set_negative_offer_patterns_csv,
            remove_negative_offer_patterns_csv,
            set_aliases_csv,
            reason,
            positive_ingredient,
            positive_offer,
            negative_ingredient,
            negative_offer,
        )
    ):
        raise typer.BadParameter("provide at least one pattern/example replacement option")

    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root light gates are not available; use --no-run-gates")

    target_file, record, entry, bridge = _find_match_bridge_record(paths, selector)
    canonical = str(bridge.get("canonical") or entry.get("canonical") or record.canonical).strip()
    if not canonical:
        raise typer.BadParameter(f"{record.entry_id}: match_bridge canonical must not be empty")

    ingredient_patterns = (
        _split_set_csv(set_ingredient_patterns_csv, label="--set-ingredient-patterns", lowercase=False)
        if set_ingredient_patterns_csv is not None
        else _string_tuple(bridge.get("ingredient_patterns"))
    )
    offer_patterns = (
        _split_set_csv(set_offer_patterns_csv, label="--set-offer-patterns", lowercase=False)
        if set_offer_patterns_csv is not None
        else _string_tuple(bridge.get("offer_patterns"))
    )
    negative_offer_patterns = (
        _split_set_csv(set_negative_offer_patterns_csv, label="--set-negative-offer-patterns", lowercase=False)
        if set_negative_offer_patterns_csv is not None
        else _string_tuple(bridge.get("negative_offer_patterns"))
    )
    aliases = (
        _split_set_csv(set_aliases_csv, label="--set-aliases")
        if set_aliases_csv is not None
        else _string_tuple(bridge.get("aliases"))
    )
    if (
        ingredient_patterns is None
        or offer_patterns is None
        or negative_offer_patterns is None
        or aliases is None
    ):
        raise typer.BadParameter("internal match-bridge option parsing error")
    offer_patterns = _remove_values(
        offer_patterns,
        _split_set_csv(remove_offer_patterns_csv, label="--remove-offer-patterns", lowercase=False) or (),
        label="offer pattern",
    )
    negative_offer_patterns = _remove_values(
        negative_offer_patterns,
        _split_set_csv(remove_negative_offer_patterns_csv, label="--remove-negative-offer-patterns", lowercase=False) or (),
        label="negative offer pattern",
    )
    if not ingredient_patterns:
        raise typer.BadParameter("match-bridge requires at least one ingredient pattern")
    if not offer_patterns:
        raise typer.BadParameter("match-bridge requires at least one offer pattern")

    positive_example = _first_example(entry, "positive_examples")
    existing_positive_ingredient = str(positive_example.get("ingredient") or "")
    existing_positive_offer = str(positive_example.get("offer_name") or "")
    next_positive_ingredient = (
        positive_ingredient.strip()
        if positive_ingredient is not None
        else (existing_positive_ingredient if existing_positive_ingredient in ingredient_patterns else ingredient_patterns[0])
    )
    next_positive_offer = (
        positive_offer.strip()
        if positive_offer is not None
        else (existing_positive_offer if existing_positive_offer in offer_patterns else offer_patterns[0])
    )
    if not next_positive_ingredient:
        raise typer.BadParameter("--positive-ingredient must not be empty")
    if not next_positive_offer:
        raise typer.BadParameter("--positive-offer must not be empty")

    negative_example = _first_example(entry, "negative_examples")
    next_negative_ingredient = (
        negative_ingredient.strip()
        if negative_ingredient is not None
        else str(negative_example.get("ingredient") or canonical)
    )
    next_negative_offer: str | None
    if negative_offer is not None:
        next_negative_offer = negative_offer.strip()
    elif negative_offer_patterns:
        existing_negative_offer = str(negative_example.get("offer_name") or "")
        next_negative_offer = (
            existing_negative_offer
            if existing_negative_offer in negative_offer_patterns
            else negative_offer_patterns[0]
        )
    else:
        next_negative_offer = None
    if next_negative_offer is not None and not next_negative_offer:
        raise typer.BadParameter("--negative-offer must not be empty")
    if negative_offer_patterns and not next_negative_ingredient:
        raise typer.BadParameter("--negative-ingredient must not be empty")

    block = _match_bridge_block(
        entry_id=record.entry_id,
        language=str(entry.get("language") or "sv"),
        market=str(entry.get("market") or "SE"),
        status=str(entry.get("status") or "active"),
        canonical=canonical,
        source_refs=_string_tuple(entry.get("source_refs")),
        layer_policy=_string_tuple(entry.get("layer_policy")) or ("bridge_only",),
        notes=reason.strip() if reason is not None else str(entry.get("notes") or f"Registry-owned match bridge: {bridge.get('id') or selector}."),
        bridge_id=str(bridge.get("id") or selector),
        rule_schema_version=_int_value(bridge.get("rule_schema_version"), default=1),
        rule_version=_int_value(bridge.get("rule_version"), default=1) + 1,
        ingredient_patterns=ingredient_patterns,
        offer_patterns=offer_patterns,
        negative_offer_patterns=negative_offer_patterns,
        aliases=aliases,
        fixture_refs=_string_tuple(bridge.get("fixture_refs")),
        supersedes=_string_tuple(bridge.get("supersedes")),
        ingredient_form_signals=_string_tuple(bridge.get("ingredient_form_signals")),
        offer_form_signals=_string_tuple(bridge.get("offer_form_signals")),
        required_offer_form_signals=_string_tuple(bridge.get("required_offer_form_signals")),
        forbidden_offer_form_signals=_string_tuple(bridge.get("forbidden_offer_form_signals")),
        precedence=bridge.get("precedence") if isinstance(bridge.get("precedence"), int) else None,
        positive_ingredient=next_positive_ingredient,
        positive_offer=next_positive_offer,
        negative_ingredient=next_negative_ingredient,
        negative_offer=next_negative_offer,
    )
    if dry_run:
        typer.echo(block)
        typer.echo("Dry run only; no files written.")
        return

    _write_registry_entry_block(target_file, record, block, dry_run=False)
    typer.echo(f"Updated match_bridge: {bridge.get('id') or selector}")
    typer.echo(f"  entry: {record.entry_id}")
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    gate_status = _run_keyword_synonym_light_gates(paths=paths, report_root=report_root)
    raise typer.Exit(gate_status)


@matcher_add_app.command("extraction-helper")
def add_extraction_helper(
    canonical: Annotated[str, typer.Argument(help="Canonical keyword produced by extraction.py.")],
    side: Annotated[
        Literal["product", "ingredient", "both"],
        typer.Option("--side", help="Extraction side covered by the hardcoded output."),
    ],
    input_text: Annotated[str, typer.Option("--input", help="Text used by the generated extraction sanity proof.")],
    source_refs_csv: Annotated[
        str,
        typer.Option("--source-refs", help="Comma-separated code refs for the extraction.py output."),
    ],
    offer_category: Annotated[str, typer.Option("--offer-category", help="Product category for product-side sanity.")] = "",
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable policy ref override for comments.")] = None,
    replace_existing: Annotated[
        bool,
        typer.Option(
            "--replace-existing",
            help="Rewrite an existing simple extraction_helper entry, useful when a hardcoded extraction side was removed.",
        ),
    ] = False,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run light registry/sanity gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
) -> None:
    canonical = canonical.strip().lower()
    if not canonical:
        raise typer.BadParameter("canonical must not be empty")
    if not input_text.strip():
        raise typer.BadParameter("--input must not be empty")
    source_refs = _split_csv(source_refs_csv, label="--source-refs", lowercase=False)
    paths = _paths(tree_root)
    if paths.app_dir != APP_DIR and run_gates and not dry_run:
        raise typer.BadParameter("tree-root light gates are not available; use --no-run-gates")
    policy_ref = policy_ref or f"extraction_helper_{_slug(canonical)}"
    entry_id, _entry_line, toml_preview, replaced = _append_extraction_helper_entry(
        paths=paths,
        canonical=canonical,
        side=side,
        source_refs=source_refs,
        replace_existing=replace_existing,
        dry_run=dry_run,
    )
    sanity_preview = _append_extraction_helper_deep_sanity_stub(
        paths=paths,
        policy_ref=policy_ref,
        canonical=canonical,
        side=side,
        input_text=input_text.strip(),
        offer_category=offer_category,
        dry_run=dry_run,
    )
    change = MatcherChangePlan(
        command="extraction-helper",
        policy_ref=policy_ref,
        entry_ids=(entry_id,),
        fixture_ids=(),
        inventory_id=None,
        toml_preview=toml_preview,
        sanity_preview=sanity_preview,
        runtime_delta_filename="extraction_helper.toml",
    )
    if dry_run:
        _print_dry_run_preview(change)
        return

    action = "Updated" if replaced else "Generated"
    typer.echo(f"{action} extraction_helper coverage: {change.policy_ref}")
    typer.echo(f"  entry: {entry_id}")
    typer.echo(
        "NOTE: extraction-helper is registry coverage for hardcoded extraction.py output; "
        "it does not write the extraction.py branch. "
        "If the code change alters existing matcher behavior, update fixtures/inventory/bridges "
        "and finish with Track B gates.",
        err=True,
    )
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    gate_status = _run_keyword_synonym_light_gates(paths=paths, report_root=report_root)
    raise typer.Exit(gate_status)


@matcher_fixture_app.command("make-negative")
def matcher_fixture_make_negative(
    fixture_id: Annotated[str, typer.Argument(help="Existing fixture id to convert from expected=1 to expected=0.")],
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    policy_ref: Annotated[
        str | None,
        typer.Option("--policy-ref", help="Replace the fixture policy_ref after conversion."),
    ] = None,
    source_ref: Annotated[
        str | None,
        typer.Option("--source-ref", help="Replace the fixture source_ref after conversion."),
    ] = None,
    regen: Annotated[
        bool,
        typer.Option("--regen/--no-regen", help="Regenerate matcher contract JSON after writing."),
    ] = True,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run matcher preflight after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the fixture rewrite without writing files.")] = False,
) -> None:
    paths = _paths(tree_root)
    fixture_rows, summary = _make_fixture_negative_rows(
        paths=paths,
        fixture_id=fixture_id,
        policy_ref=policy_ref,
        source_ref=source_ref,
    )

    _print_fixture_make_negative_summary(summary, dry_run=dry_run)
    if dry_run:
        return

    if summary["changed"]:
        write_contract_source(_source_spec(paths, "matcher_regression_cases"), fixture_rows)
    if regen:
        _regenerate_contract_json(paths)
        typer.echo("Regenerated matcher contract JSON.")
    else:
        typer.echo("Skipped regen (--no-regen).")

    typer.echo(
        "If verified-term promotion reports intentional removals, finish the batch with "
        "`dm matcher batch finalize --track B --allow-removals` after reviewing them."
    )

    if not run_gates:
        typer.echo("Skipped preflight (--no-run-gates).")
        return
    if _matcher_session_should_defer_gates(paths):
        _echo_session_deferred_gates("preflight")
        return
    raise typer.Exit(_run_preflight(paths, report_root))


@matcher_fixture_app.command("make-positive")
def matcher_fixture_make_positive(
    fixture_id: Annotated[str, typer.Argument(help="Existing fixture id to convert to expected=1.")],
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    from_current_match: Annotated[
        bool,
        typer.Option(
            "--from-current-match",
            help="Infer expected_matches from the current matcher when all paths agree on exactly one match.",
        ),
    ] = False,
    canonical: Annotated[
        str | None,
        typer.Option("--canonical", help="Explicit expected canonical when not using --from-current-match."),
    ] = None,
    ingredient_index: Annotated[
        int | None,
        typer.Option("--ingredient-index", help="Explicit ingredient index when not using --from-current-match."),
    ] = None,
    must_match_keyword: Annotated[
        str | None,
        typer.Option(
            "--must-match-keyword",
            help="Explicit must_match_keyword; defaults to --canonical in explicit mode.",
        ),
    ] = None,
    policy_ref: Annotated[
        str | None,
        typer.Option("--policy-ref", help="Replace the fixture policy_ref after conversion."),
    ] = None,
    source_ref: Annotated[
        str | None,
        typer.Option("--source-ref", help="Replace the fixture source_ref after conversion."),
    ] = None,
    regen: Annotated[
        bool,
        typer.Option("--regen/--no-regen", help="Regenerate matcher contract JSON after writing."),
    ] = True,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run matcher preflight after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the fixture rewrite without writing files.")] = False,
) -> None:
    paths = _paths(tree_root)
    fixture_row = _load_fixture_row(paths, fixture_id)
    inference: Mapping[str, Any] | None = None

    if from_current_match:
        explicit_options = [
            option
            for option, value in (
                ("--canonical", canonical),
                ("--ingredient-index", ingredient_index),
                ("--must-match-keyword", must_match_keyword),
            )
            if value is not None
        ]
        if explicit_options:
            raise typer.BadParameter(
                "--from-current-match cannot be combined with explicit match fields: "
                + ", ".join(explicit_options)
            )
        expected_match, inference = _infer_positive_expected_match_from_current_match(fixture_row)
    else:
        if not canonical or ingredient_index is None:
            raise typer.BadParameter(
                "pass --from-current-match, or pass both --canonical and --ingredient-index"
            )
        canonical_value = canonical.strip()
        if not canonical_value:
            raise typer.BadParameter("--canonical must not be empty")
        if ingredient_index < 0:
            raise typer.BadParameter("--ingredient-index must be >= 0")
        ingredients = _fixture_ingredients(fixture_row)
        if ingredient_index >= len(ingredients):
            raise typer.BadParameter(
                f"--ingredient-index {ingredient_index} is outside fixture ingredients "
                f"(0..{len(ingredients) - 1})"
            )
        must_match_value = must_match_keyword.strip() if must_match_keyword else canonical_value
        expected_match = {
            "ingredient_index": ingredient_index,
            "canonical": canonical_value,
        }
        if must_match_value:
            expected_match["must_match_keyword"] = must_match_value

    fixture_rows, summary = _make_fixture_positive_rows(
        paths=paths,
        fixture_id=fixture_id,
        expected_match=expected_match,
        policy_ref=policy_ref,
        source_ref=source_ref,
        inference=inference,
    )

    _print_fixture_make_positive_summary(summary, dry_run=dry_run)
    if dry_run:
        return

    if summary["changed"]:
        write_contract_source(_source_spec(paths, "matcher_regression_cases"), fixture_rows)
    if regen:
        _regenerate_contract_json(paths)
        typer.echo("Regenerated matcher contract JSON.")
    else:
        typer.echo("Skipped regen (--no-regen).")

    if not run_gates:
        typer.echo("Skipped preflight (--no-run-gates).")
        return
    if _matcher_session_should_defer_gates(paths):
        _echo_session_deferred_gates("preflight")
        return
    raise typer.Exit(_run_preflight(paths, report_root))


@matcher_fixture_app.command("remove")
def matcher_fixture_remove(
    fixture_ids_csv: Annotated[str, typer.Argument(help="Fixture id, or comma-separated fixture ids, to remove.")],
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    drop_empty_inventory: Annotated[
        bool,
        typer.Option(
            "--drop-empty-inventory/--keep-empty-inventory",
            help="Drop inventory rows that would otherwise be left with no fixture_refs.",
        ),
    ] = False,
    drop_empty_registry_entries: Annotated[
        bool,
        typer.Option(
            "--drop-empty-registry-entries/--keep-empty-registry-entries",
            help="Drop registry entries that would otherwise be left with no fixture_refs.",
        ),
    ] = False,
    regen: Annotated[
        bool,
        typer.Option("--regen/--no-regen", help="Regenerate matcher contract JSON and registry coverage after writing."),
    ] = True,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run matcher preflight after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the cascade without writing files.")] = False,
) -> None:
    fixture_ids = _split_fixture_ids(fixture_ids_csv)
    paths = _paths(tree_root)

    fixture_rows, removed_fixture_ids = _remove_fixture_rows(paths=paths, fixture_ids=fixture_ids)
    inventory_rows = load_contract_source(_source_spec(paths, "matcher_rule_inventory"))
    inventory_rows, inventory_changed, inventory_dropped = _remove_fixture_refs_from_contract_rows(
        inventory_rows,
        fixture_ids=fixture_ids,
        id_field="id",
        drop_empty_rows=drop_empty_inventory,
        row_label="inventory",
    )
    registry_plans = _plan_registry_fixture_ref_removal(
        paths=paths,
        fixture_ids=fixture_ids,
        drop_empty_registry_entries=drop_empty_registry_entries,
    )

    if dry_run:
        _print_fixture_remove_summary(
            fixture_ids=removed_fixture_ids,
            inventory_changed=inventory_changed,
            inventory_dropped=inventory_dropped,
            registry_plans=registry_plans,
            dry_run=True,
        )
        typer.echo("Dry run only; no files written.")
        return

    write_contract_source(_source_spec(paths, "matcher_regression_cases"), fixture_rows)
    write_contract_source(_source_spec(paths, "matcher_rule_inventory"), inventory_rows)
    _write_registry_fixture_ref_removal_plans(registry_plans)
    _print_fixture_remove_summary(
        fixture_ids=removed_fixture_ids,
        inventory_changed=inventory_changed,
        inventory_dropped=inventory_dropped,
        registry_plans=registry_plans,
        dry_run=False,
    )

    if regen:
        _regenerate_contract_json(paths)
        coverage_status = _run_coverage_generator(paths)
        if coverage_status != 0:
            raise typer.Exit(coverage_status)
    else:
        typer.echo("Skipped regen (--no-regen).")

    if not run_gates:
        typer.echo("Skipped preflight (--no-run-gates).")
        return
    if _matcher_session_should_defer_gates(paths):
        _echo_session_deferred_gates("preflight")
        return
    raise typer.Exit(_run_preflight(paths, report_root))


@matcher_app.command("dev-watch")
def matcher_dev_watch(
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to watch instead of /app.")] = None,
    interval: Annotated[
        float,
        typer.Option("--interval", min=0.25, help="Polling interval in seconds; default reports within 5 seconds."),
    ] = 1.0,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    once: Annotated[bool, typer.Option("--once", help="Run pre-flight once and exit.")] = False,
) -> None:
    paths = _paths(tree_root)
    files = _watch_files(paths)
    typer.echo(f"Watching {len(files)} matcher file(s); press Ctrl-C to stop.")
    status = _run_preflight(paths, report_root)
    if once:
        raise typer.Exit(status)

    snapshot = _mtime_snapshot(files)
    try:
        while True:
            time.sleep(interval)
            current_files = _watch_files(paths)
            current = _mtime_snapshot(current_files)
            if current != snapshot:
                changed = sorted(
                    str(path.relative_to(paths.repo_root) if path.is_relative_to(paths.repo_root) else path)
                    for path in set(current) | set(snapshot)
                    if current.get(path) != snapshot.get(path)
                )
                typer.echo("")
                typer.echo(f"Change detected: {', '.join(changed[:6])}")
                if len(changed) > 6:
                    typer.echo(f"... and {len(changed) - 6} more")
                status = _run_preflight(paths, report_root)
                snapshot = current
    except KeyboardInterrupt:
        typer.echo("")
        typer.echo("Stopped matcher dev-watch.")
        raise typer.Exit(status)


def _keyword_diff_payload(
    *,
    extracted_keywords: Iterable[str],
    precomputed_keywords: Iterable[str],
) -> dict[str, list[str]]:
    extracted = list(dict.fromkeys(str(value) for value in extracted_keywords if value))
    precomputed = list(dict.fromkeys(str(value) for value in precomputed_keywords if value))
    extracted_set = set(extracted)
    precomputed_set = set(precomputed)
    return {
        "common": [keyword for keyword in precomputed if keyword in extracted_set],
        "extraction_only": [keyword for keyword in extracted if keyword not in precomputed_set],
        "precomputed_only": [keyword for keyword in precomputed if keyword not in extracted_set],
    }


def _precomputed_keyword_explanations(
    *,
    extracted_keywords: Iterable[str],
    precomputed_only: Iterable[str],
    normalized_offer_text: str,
    offer_extra_keywords: Mapping[str, Iterable[str]],
    ingredient_parents_reverse: Mapping[str, Iterable[str]],
) -> list[dict[str, Any]]:
    extracted = tuple(dict.fromkeys(str(value) for value in extracted_keywords if value))
    rows: list[dict[str, Any]] = []
    for keyword in precomputed_only:
        keyword = str(keyword)
        sources: list[str] = []
        for base in extracted:
            offer_extras = {str(value) for value in offer_extra_keywords.get(base, ())}
            reverse_children = {str(value) for value in ingredient_parents_reverse.get(base, ())}
            if keyword in offer_extras:
                sources.append(f"OFFER_EXTRA_KEYWORDS from {base}")
            if keyword in reverse_children:
                sources.append(f"INGREDIENT_PARENTS reverse child of {base}")
        if re.search(r"\b" + re.escape(keyword) + r"\b", normalized_offer_text):
            sources.append("literal product word or name-conditional precompute helper")
        if not sources:
            sources.append("precompute expansion: reverse parent, offer-extra keyword, carrier re-add, or name-conditional helper")
        rows.append({"keyword": keyword, "sources": sources})
    return rows


def _trace_extraction(
    *,
    mode: Literal["ingredient", "offer"],
    text: str,
    offer_category: str = "",
    brand: str = "",
) -> dict[str, Any]:
    try:
        from languages.sv.normalization import fix_swedish_chars
        from languages.sv.ingredient_matching.extraction import (
            extract_keywords_from_ingredient,
            extract_keywords_from_product,
        )
        from languages.sv.ingredient_matching.engine import build_offer_match_data
        from languages.sv.ingredient_matching.extraction_patterns import (
            MIN_KEYWORD_LENGTH,
            MIN_KEYWORD_LENGTH_STRICT,
            _INGREDIENT_PARENTS_REVERSE,
        )
        from languages.sv.ingredient_matching.keywords import (
            FLAVOR_WORDS,
            IMPORTANT_SHORT_KEYWORDS,
            OFFER_EXTRA_KEYWORDS,
            STOP_WORDS,
        )
        from languages.sv.ingredient_matching.normalization import _apply_space_normalizations
        from languages.sv.ingredient_matching.synonyms import INGREDIENT_PARENTS, KEYWORD_SYNONYMS
    except ModuleNotFoundError:
        from app.languages.sv.normalization import fix_swedish_chars
        from app.languages.sv.ingredient_matching.extraction import (
            extract_keywords_from_ingredient,
            extract_keywords_from_product,
        )
        from app.languages.sv.ingredient_matching.engine import build_offer_match_data
        from app.languages.sv.ingredient_matching.extraction_patterns import (
            MIN_KEYWORD_LENGTH,
            MIN_KEYWORD_LENGTH_STRICT,
            _INGREDIENT_PARENTS_REVERSE,
        )
        from app.languages.sv.ingredient_matching.keywords import (
            FLAVOR_WORDS,
            IMPORTANT_SHORT_KEYWORDS,
            OFFER_EXTRA_KEYWORDS,
            STOP_WORDS,
        )
        from app.languages.sv.ingredient_matching.normalization import _apply_space_normalizations
        from app.languages.sv.ingredient_matching.synonyms import INGREDIENT_PARENTS, KEYWORD_SYNONYMS

    normalized = _apply_space_normalizations(fix_swedish_chars(text).lower())
    tokens = re.findall(r"\b[\wåäöéèü]+\b", normalized)
    if mode == "ingredient":
        keywords = extract_keywords_from_ingredient(text)
        min_length = MIN_KEYWORD_LENGTH_STRICT
    else:
        keywords = extract_keywords_from_product(text, offer_category, brand=brand)
        min_length = MIN_KEYWORD_LENGTH
    precomputed_keywords: list[str] = []
    keyword_diff = {"common": [], "extraction_only": [], "precomputed_only": []}
    precomputed_explanations: list[dict[str, Any]] = []
    if mode == "offer":
        offer_match_data = build_offer_match_data(text, offer_category, brand=brand)
        precomputed_keywords = list(offer_match_data.precomputed.get("keywords") or ())
        keyword_diff = _keyword_diff_payload(
            extracted_keywords=keywords,
            precomputed_keywords=precomputed_keywords,
        )
        precomputed_explanations = _precomputed_keyword_explanations(
            extracted_keywords=keywords,
            precomputed_only=keyword_diff["precomputed_only"],
            normalized_offer_text=normalized,
            offer_extra_keywords=OFFER_EXTRA_KEYWORDS,
            ingredient_parents_reverse=_INGREDIENT_PARENTS_REVERSE,
        )
    keyword_set = set(keywords)
    token_rows: list[dict[str, Any]] = []
    for token in tokens:
        synonym = KEYWORD_SYNONYMS.get(token)
        parent = INGREDIENT_PARENTS.get(synonym or token)
        mapped = parent or synonym or token
        sets = {
            "stop_word": token in STOP_WORDS,
            "flavor_word": token in FLAVOR_WORDS,
            "important_short_keyword": token in IMPORTANT_SHORT_KEYWORDS,
        }
        if token in STOP_WORDS:
            status = "dropped_stop_word"
            reason = "token is in STOP_WORDS"
        elif token.isdigit():
            status = "dropped_number"
            reason = "token is numeric"
        elif len(token) < min_length and token not in IMPORTANT_SHORT_KEYWORDS:
            status = "dropped_too_short"
            reason = f"len={len(token)} < min_length={min_length} and not IMPORTANT_SHORT_KEYWORDS"
        elif mapped in keyword_set or token in keyword_set:
            status = "kept"
            reason = "token or mapped token appears in extracted keywords"
        else:
            status = "candidate_not_in_final_keywords"
            reason = "token passed simple filters but was removed by later extraction logic"
        token_rows.append({
            "token": token,
            "status": status,
            "reason": reason,
            "length": len(token),
            "min_length": min_length,
            "mapped_keyword": mapped,
            "sets": sets,
        })
    suggestions: list[str] = []
    if mode == "ingredient" and not keywords:
        short_candidates = [
            row["token"]
            for row in token_rows
            if row["status"] == "dropped_too_short" and not row["sets"]["stop_word"]
        ]
        if short_candidates:
            terms = ",".join(dict.fromkeys(short_candidates))
            suggestions.append(
                f"if standalone food terms are intended, add: ./bin/dm matcher add important-short-keyword --terms {terms} --reason \"<why>\""
            )
    return {
        "mode": mode,
        "input": text,
        "normalized": normalized,
        "offer_category": offer_category,
        "brand": brand,
        "keywords": list(keywords),
        "precomputed_keywords": precomputed_keywords,
        "keyword_diff": keyword_diff,
        "precomputed_keyword_explanations": precomputed_explanations,
        "tokens": token_rows,
        "suggestions": suggestions,
    }


def _format_extraction_trace_text(payload: Mapping[str, Any]) -> str:
    lines = [
        f"extraction trace: {payload['mode']}",
        f"input: {payload['input']}",
        f"normalized: {payload['normalized']}",
        "keywords: " + (", ".join(payload["keywords"]) if payload["keywords"] else "none"),
    ]
    if payload["mode"] == "offer":
        lines.append(
            "precomputed keywords: "
            + (", ".join(payload["precomputed_keywords"]) if payload["precomputed_keywords"] else "none")
        )
        diff = payload["keyword_diff"]
        if diff["extraction_only"] or diff["precomputed_only"]:
            lines.append("offer keyword diff:")
            lines.append("  extraction-only: " + (", ".join(diff["extraction_only"]) if diff["extraction_only"] else "none"))
            lines.append("  precomputed-only: " + (", ".join(diff["precomputed_only"]) if diff["precomputed_only"] else "none"))
            if payload["precomputed_keyword_explanations"]:
                lines.append("precomputed-only explanations:")
                for row in payload["precomputed_keyword_explanations"]:
                    lines.append(f"  - {row['keyword']}: {'; '.join(row['sources'])}")
    lines.append("tokens:")
    for row in payload["tokens"]:
        sets = row["sets"]
        flags = []
        if sets["stop_word"]:
            flags.append("STOP_WORDS")
        if sets["flavor_word"]:
            flags.append("FLAVOR_WORDS")
        if sets["important_short_keyword"]:
            flags.append("IMPORTANT_SHORT_KEYWORDS")
        flag_text = f" [{', '.join(flags)}]" if flags else ""
        mapped = f" -> {row['mapped_keyword']}" if row["mapped_keyword"] != row["token"] else ""
        lines.append(f"  - {row['token']}{mapped}: {row['status']}{flag_text} ({row['reason']})")
    if payload["suggestions"]:
        lines.append("suggestions:")
        lines.extend(f"  - {suggestion}" for suggestion in payload["suggestions"])
    return "\n".join(lines)


def _canonical_of_payload(
    *,
    text: str,
    offer_category: str,
    brand: str,
) -> dict[str, Any]:
    try:
        from languages.sv.normalization import fix_swedish_chars
        from languages.sv.ingredient_matching.engine import build_offer_match_data
        from languages.sv.ingredient_matching.extraction import (
            extract_keywords_from_ingredient,
            extract_keywords_from_product,
        )
        from languages.sv.ingredient_matching.normalization import _apply_space_normalizations
        from languages.sv.ingredient_matching.synonyms import INGREDIENT_PARENTS, KEYWORD_SYNONYMS
    except ModuleNotFoundError:
        from app.languages.sv.normalization import fix_swedish_chars
        from app.languages.sv.ingredient_matching.engine import build_offer_match_data
        from app.languages.sv.ingredient_matching.extraction import (
            extract_keywords_from_ingredient,
            extract_keywords_from_product,
        )
        from app.languages.sv.ingredient_matching.normalization import _apply_space_normalizations
        from app.languages.sv.ingredient_matching.synonyms import INGREDIENT_PARENTS, KEYWORD_SYNONYMS

    normalized = _apply_space_normalizations(fix_swedish_chars(text).lower()).strip()
    synonym = KEYWORD_SYNONYMS.get(normalized)
    after_synonym = synonym or normalized
    parent = INGREDIENT_PARENTS.get(after_synonym)
    direct_canonical = parent or after_synonym
    ingredient_keywords = list(extract_keywords_from_ingredient(text))
    product_keywords = list(extract_keywords_from_product(text, offer_category, brand=brand))
    precomputed_keywords = list(
        build_offer_match_data(
            text,
            offer_category,
            brand=brand,
        ).precomputed.get("keywords") or ()
    )
    likely_canonicals = list(dict.fromkeys([
        *ingredient_keywords,
        *product_keywords,
        *precomputed_keywords,
    ]))
    notes: list[str] = []
    if likely_canonicals and direct_canonical not in likely_canonicals:
        notes.append(
            "direct synonym/parent mapping differs from extractor output; "
            "the runtime extractor has an additional normalization or hardcoded branch"
        )
    if not likely_canonicals:
        notes.append("no runtime extractor keywords found")
    return {
        "input": text,
        "normalized": normalized,
        "direct_synonym": synonym or "",
        "direct_parent": parent or "",
        "direct_canonical": direct_canonical,
        "ingredient_keywords": ingredient_keywords,
        "product_keywords": product_keywords,
        "precomputed_offer_keywords": precomputed_keywords,
        "likely_canonicals": likely_canonicals,
        "offer_category": offer_category,
        "brand": brand,
        "notes": notes,
    }


def _format_canonical_of_text(payload: Mapping[str, Any]) -> str:
    synonym = payload["direct_synonym"] or "none"
    parent = payload["direct_parent"] or "none"
    lines = [
        f"input: {payload['input']}",
        f"normalized: {payload['normalized']}",
        f"direct synonym: {synonym}",
        f"direct parent: {parent}",
        f"direct canonical: {payload['direct_canonical']}",
        "ingredient extraction: "
        + (", ".join(payload["ingredient_keywords"]) if payload["ingredient_keywords"] else "none"),
        "product extraction: "
        + (", ".join(payload["product_keywords"]) if payload["product_keywords"] else "none"),
        "offer precompute: "
        + (", ".join(payload["precomputed_offer_keywords"]) if payload["precomputed_offer_keywords"] else "none"),
        "likely canonical(s): "
        + (", ".join(payload["likely_canonicals"]) if payload["likely_canonicals"] else "none"),
    ]
    if payload["notes"]:
        lines.append("notes:")
        lines.extend(f"  - {note}" for note in payload["notes"])
    return "\n".join(lines)


@matcher_app.command("canonical-of", help="Show runtime canonical keyword(s) for one term or phrase.")
def matcher_canonical_of(
    text: Annotated[str, typer.Argument(help="Term or phrase to inspect.")],
    offer_category: Annotated[
        str,
        typer.Option("--offer-category", "--category", help="Optional category for product extraction."),
    ] = "",
    brand: Annotated[str, typer.Option("--brand", help="Optional brand for product extraction.")] = "",
    output_format: Annotated[
        Literal["text", "json"],
        typer.Option("--format", help="Output format."),
    ] = "text",
) -> None:
    if not text.strip():
        raise typer.BadParameter("text must not be empty")
    payload = _canonical_of_payload(
        text=text.strip(),
        offer_category=offer_category.strip(),
        brand=brand.strip(),
    )
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    typer.echo(_format_canonical_of_text(payload))


@matcher_app.command("trace-extraction", help="Trace ingredient or offer keyword extraction.")
def matcher_trace_extraction(
    ingredient: Annotated[str | None, typer.Option("--ingredient", help="Recipe ingredient text to trace.")] = None,
    offer: Annotated[str | None, typer.Option("--offer", "--product", help="Offer/product name to trace.")] = None,
    offer_category: Annotated[
        str,
        typer.Option("--offer-category", "--category", help="Optional offer category for product extraction."),
    ] = "",
    brand: Annotated[str, typer.Option("--brand", help="Optional offer/product brand.")] = "",
    output_format: Annotated[
        Literal["text", "json"],
        typer.Option("--format", help="Output format."),
    ] = "text",
) -> None:
    if bool(ingredient and ingredient.strip()) == bool(offer and offer.strip()):
        raise typer.BadParameter("provide exactly one of --ingredient or --offer")
    if ingredient and ingredient.strip():
        payload = _trace_extraction(mode="ingredient", text=ingredient.strip())
    else:
        payload = _trace_extraction(
            mode="offer",
            text=(offer or "").strip(),
            offer_category=offer_category.strip(),
            brand=brand.strip(),
        )
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    typer.echo(_format_extraction_trace_text(payload))


@matcher_app.command("explain", help="Explain one offer/ingredient matcher decision.")
def matcher_explain(
    offer: Annotated[
        str,
        typer.Option("--offer", "--product", help="Offer/product name to inspect."),
    ],
    ingredient: Annotated[str, typer.Option("--ingredient", help="Recipe ingredient text to inspect.")],
    offer_category: Annotated[
        str,
        typer.Option("--offer-category", "--category", help="Optional offer category."),
    ] = "",
    brand: Annotated[str, typer.Option("--brand", help="Optional offer/product brand.")] = "",
    weight_grams: Annotated[
        float | None,
        typer.Option("--weight-grams", help="Optional offer/product weight in grams."),
    ] = None,
    recipe_name: Annotated[
        str | None,
        typer.Option("--recipe-name", help="Optional recipe name for batch-review trace context."),
    ] = None,
    output_format: Annotated[
        Literal["text", "json"],
        typer.Option("--format", help="Output format."),
    ] = "text",
) -> None:
    if not offer.strip():
        raise typer.BadParameter("--offer must not be empty")
    if not ingredient.strip():
        raise typer.BadParameter("--ingredient must not be empty")

    try:
        from languages.sv.ingredient_matching_audit import _explain_pair
    except ModuleNotFoundError:
        from app.languages.sv.ingredient_matching_audit import _explain_pair

    trace = _explain_pair(
        ingredient.strip(),
        offer.strip(),
        category=offer_category.strip(),
        brand=brand.strip(),
        weight_grams=weight_grams,
    )
    if recipe_name:
        trace = f"Recipe: {recipe_name.strip()}\n\n{trace}"

    if output_format == "json":
        payload = {
            "offer": offer.strip(),
            "ingredient": ingredient.strip(),
            "offer_category": offer_category.strip(),
            "brand": brand.strip(),
            "weight_grams": weight_grams,
            "recipe_name": recipe_name.strip() if recipe_name else "",
            "trace": trace,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return

    typer.echo(trace)


def _normalize_probe_expectation(value: str | None, *, option_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower().replace("_", "-")
    if normalized not in {"match", "no-match"}:
        raise typer.BadParameter(f"{option_name} must be 'match' or 'no-match'")
    return normalized


def _probe_matcher_pair(
    *,
    offer: str,
    ingredient: str,
    offer_category: str,
    brand: str,
    weight_grams: float | None,
    recipe_name: str,
) -> dict[str, Any]:
    from types import SimpleNamespace

    try:
        from languages.sv.ingredient_matching import (
            build_ingredient_match_data,
            build_offer_match_data,
            match_offer_to_ingredient,
        )
        from recipe_matcher import RecipeMatcher
    except ModuleNotFoundError:
        from app.languages.sv.ingredient_matching import (
            build_ingredient_match_data,
            build_offer_match_data,
            match_offer_to_ingredient,
        )
        from app.recipe_matcher import RecipeMatcher

    ingredient_data = build_ingredient_match_data(ingredient)
    offer_data = build_offer_match_data(
        offer,
        offer_category,
        brand=brand,
        weight_grams=weight_grams,
    )
    fast_result = match_offer_to_ingredient(ingredient_data, offer_data)

    matcher = RecipeMatcher()
    recipe = SimpleNamespace(
        id="dm-probe-recipe",
        name=recipe_name or "DM Matcher Probe",
        ingredients=[ingredient],
    )
    offer_obj = SimpleNamespace(
        id="dm-probe-offer",
        name=offer,
        category=offer_category,
        brand=brand,
        price=0,
        original_price=None,
        savings=0,
        store=None,
        product_url=None,
        is_multi_buy=False,
        multi_buy_quantity=None,
        weight_grams=weight_grams,
    )
    backend_result = matcher._match_recipe_to_offers(recipe, [offer_obj], preferences={})
    backend_num_matches = int(backend_result.get("num_matches") or 0)
    return {
        "offer": offer,
        "ingredient": ingredient,
        "offer_category": offer_category,
        "brand": brand,
        "weight_grams": weight_grams,
        "recipe_name": recipe_name,
        "fast_matched": bool(fast_result.matched),
        "fast_keyword": fast_result.matched_keyword or "",
        "fast_reason": fast_result.reason or "",
        "backend_matched": backend_num_matches > 0,
        "backend_num_matches": backend_num_matches,
    }


def _processed_check_applies_to_match(
    *,
    check_base: str,
    matched_keyword: str,
    offer_keywords: set[str],
    specialty_keyword_aliases: Mapping[str, str],
) -> bool:
    if not matched_keyword:
        return True
    if check_base == matched_keyword:
        return True
    if check_base == specialty_keyword_aliases.get(matched_keyword):
        return True
    return check_base in offer_keywords


def _processed_check_diagnostics(
    *,
    processed_checks: Iterable[tuple[Any, ...]],
    matched_keyword: str,
    offer_keywords: Iterable[str],
    ingredient_lower: str,
    product_lower: str,
    specialty_keyword_aliases: Mapping[str, str],
) -> list[dict[str, Any]]:
    try:
        from languages.sv.ingredient_matching.processed_rules import (
            generic_canned_small_tomato_allows_processed_check,
            generic_canned_whole_tomato_allows_strict_check,
        )
    except ModuleNotFoundError:
        from app.languages.sv.ingredient_matching.processed_rules import (
            generic_canned_small_tomato_allows_processed_check,
            generic_canned_whole_tomato_allows_strict_check,
        )

    offer_keyword_set = set(offer_keywords)
    diagnostics: list[dict[str, Any]] = []
    for raw_check in processed_checks:
        if len(raw_check) < 2:
            diagnostics.append({
                "raw": repr(raw_check),
                "status": "unknown_shape",
            })
            continue
        check_base = str(raw_check[0])
        mode = str(raw_check[1])
        applies = _processed_check_applies_to_match(
            check_base=check_base,
            matched_keyword=matched_keyword,
            offer_keywords=offer_keyword_set,
            specialty_keyword_aliases=specialty_keyword_aliases,
        )
        row: dict[str, Any] = {
            "base": check_base,
            "mode": mode,
            "applies_to_matched_keyword": applies,
        }
        if not applies:
            row["status"] = "skipped_not_matched_keyword_family"
            diagnostics.append(row)
            continue
        if mode == "strict" and len(raw_check) >= 3:
            indicators = tuple(str(indicator) for indicator in raw_check[2])
            allowance = generic_canned_whole_tomato_allows_strict_check(
                check_base,
                product_lower,
                ingredient_lower,
            )
            row["indicators"] = list(indicators)
            row["ingredient_has_indicator"] = any(indicator in ingredient_lower for indicator in indicators)
            if allowance:
                row["allowance"] = "generic_canned_whole_tomato"
            row["status"] = "passes" if row["ingredient_has_indicator"] or allowance else "would_block"
            diagnostics.append(row)
            continue
        if mode == "relaxed" and len(raw_check) >= 4:
            indicator = str(raw_check[2])
            indicators = tuple(str(candidate) for candidate in raw_check[3])
            allowance = generic_canned_small_tomato_allows_processed_check(
                check_base,
                indicator,
                ingredient_lower,
            )
            row["product_indicator"] = indicator
            row["all_indicators"] = list(indicators)
            row["ingredient_has_product_indicator"] = indicator in ingredient_lower
            row["ingredient_has_any_indicator"] = any(candidate in ingredient_lower for candidate in indicators)
            if allowance:
                row["allowance"] = "generic_canned_small_tomato"
            row["status"] = "passes" if row["ingredient_has_any_indicator"] or allowance else "would_block"
            diagnostics.append(row)
            continue
        row["raw"] = repr(raw_check)
        row["status"] = "unknown_shape"
        diagnostics.append(row)
    return diagnostics


def _compare_matcher_paths(
    *,
    offer: str,
    ingredient: str,
    offer_category: str,
    brand: str,
    weight_grams: float | None,
    recipe_name: str,
) -> dict[str, Any]:
    try:
        from languages.sv.ingredient_matching import (
            build_ingredient_match_data,
            build_offer_match_data,
            match_offer_to_ingredient,
        )
        from languages.sv.ingredient_matching.extraction_patterns import _INGREDIENT_PARENTS_REVERSE
        from languages.sv.ingredient_matching.extraction import extract_keywords_from_product
        from languages.sv.ingredient_matching.keywords import OFFER_EXTRA_KEYWORDS
        from languages.sv.ingredient_matching.matching import _SPECIALTY_KEYWORD_ALIASES, matches_ingredient
    except ModuleNotFoundError:
        from app.languages.sv.ingredient_matching import (
            build_ingredient_match_data,
            build_offer_match_data,
            match_offer_to_ingredient,
        )
        from app.languages.sv.ingredient_matching.extraction_patterns import _INGREDIENT_PARENTS_REVERSE
        from app.languages.sv.ingredient_matching.extraction import extract_keywords_from_product
        from app.languages.sv.ingredient_matching.keywords import OFFER_EXTRA_KEYWORDS
        from app.languages.sv.ingredient_matching.matching import _SPECIALTY_KEYWORD_ALIASES, matches_ingredient

    ingredient_data = build_ingredient_match_data(ingredient)
    offer_match_data = build_offer_match_data(
        offer,
        offer_category,
        brand=brand,
        weight_grams=weight_grams,
    )
    offer_data = dict(offer_match_data.precomputed)
    product_keywords = tuple(
        extract_keywords_from_product(
            offer,
            offer_category,
            brand=brand,
        )
    )
    precomputed_offer_keywords = list(offer_data.get("keywords") or ())
    offer_keyword_diff = _keyword_diff_payload(
        extracted_keywords=product_keywords,
        precomputed_keywords=precomputed_offer_keywords,
    )
    live_keyword = matches_ingredient(product_keywords, ingredient, offer)
    fast_result = match_offer_to_ingredient(ingredient_data, offer_match_data)
    probe = _probe_matcher_pair(
        offer=offer,
        ingredient=ingredient,
        offer_category=offer_category,
        brand=brand,
        weight_grams=weight_grams,
        recipe_name=recipe_name,
    )
    fast_keyword = fast_result.matched_keyword or ""
    processed_checks = tuple(offer_data.get("processed_checks") or ())
    diagnostic_ingredient_lower = ingredient_data.normalized_text
    if fast_keyword:
        for arm in getattr(ingredient_data, "eller_arms_prepared", ()) or ():
            if fast_keyword in arm:
                diagnostic_ingredient_lower = arm
                break
    processed_check_rows = _processed_check_diagnostics(
        processed_checks=processed_checks,
        matched_keyword=fast_keyword or str(live_keyword or ""),
        offer_keywords=offer_data.get("keywords") or (),
        ingredient_lower=diagnostic_ingredient_lower,
        product_lower=offer_data.get("name_normalized") or "",
        specialty_keyword_aliases=_SPECIALTY_KEYWORD_ALIASES,
    )
    return {
        "offer": offer,
        "ingredient": ingredient,
        "offer_category": offer_category,
        "brand": brand,
        "weight_grams": weight_grams,
        "recipe_name": recipe_name,
        "ingredient_normalized": ingredient_data.normalized_text,
        "product_keywords": list(product_keywords),
        "precomputed_offer_keywords": precomputed_offer_keywords,
        "offer_keyword_diff": offer_keyword_diff,
        "precomputed_keyword_explanations": _precomputed_keyword_explanations(
            extracted_keywords=product_keywords,
            precomputed_only=offer_keyword_diff["precomputed_only"],
            normalized_offer_text=str(offer_data.get("name_normalized") or ""),
            offer_extra_keywords=OFFER_EXTRA_KEYWORDS,
            ingredient_parents_reverse=_INGREDIENT_PARENTS_REVERSE,
        ),
        "offer_specialty_qualifiers": {
            str(key): sorted(str(value) for value in values)
            for key, values in (offer_data.get("specialty_qualifiers") or {}).items()
        },
        "processed_checks": processed_check_rows,
        "legacy_live_matched": live_keyword is not None,
        "legacy_live_keyword": live_keyword or "",
        "fast_matched": bool(fast_result.matched),
        "fast_keyword": fast_keyword,
        "fast_reason": fast_result.reason or "",
        "backend_matched": probe["backend_matched"],
        "backend_num_matches": probe["backend_num_matches"],
        "live_fast_diverged": (live_keyword is not None) != bool(fast_result.matched)
        or (live_keyword or "") != fast_keyword,
        "fast_backend_diverged": bool(fast_result.matched) != probe["backend_matched"],
    }


@matcher_app.command("probe", help="Probe one offer/ingredient pair across fast and backend matcher paths.")
def matcher_probe(
    offer: Annotated[
        str,
        typer.Option("--offer", "--product", help="Offer/product name to inspect."),
    ],
    ingredient: Annotated[str, typer.Option("--ingredient", help="Recipe ingredient text to inspect.")],
    offer_category: Annotated[
        str,
        typer.Option("--offer-category", "--category", help="Optional offer category."),
    ] = "",
    brand: Annotated[str, typer.Option("--brand", help="Optional offer/product brand.")] = "",
    weight_grams: Annotated[
        float | None,
        typer.Option("--weight-grams", help="Optional offer/product weight in grams."),
    ] = None,
    recipe_name: Annotated[
        str,
        typer.Option("--recipe-name", help="Optional recipe name for backend context."),
    ] = "DM Matcher Probe",
    expect: Annotated[
        str | None,
        typer.Option("--expect", help="Expected backend result: match or no-match."),
    ] = None,
    expect_fast: Annotated[
        str | None,
        typer.Option("--expect-fast", help="Expected fast matcher result: match or no-match."),
    ] = None,
    output_format: Annotated[
        Literal["text", "json"],
        typer.Option("--format", help="Output format."),
    ] = "text",
) -> None:
    if not offer.strip():
        raise typer.BadParameter("--offer must not be empty")
    if not ingredient.strip():
        raise typer.BadParameter("--ingredient must not be empty")

    expected_backend = _normalize_probe_expectation(expect, option_name="--expect")
    expected_fast = _normalize_probe_expectation(expect_fast, option_name="--expect-fast")
    probe = _probe_matcher_pair(
        offer=offer.strip(),
        ingredient=ingredient.strip(),
        offer_category=offer_category.strip(),
        brand=brand.strip(),
        weight_grams=weight_grams,
        recipe_name=recipe_name.strip(),
    )

    failures: list[str] = []
    if expected_backend is not None:
        actual_backend = "match" if probe["backend_matched"] else "no-match"
        if actual_backend != expected_backend:
            failures.append(f"backend expected {expected_backend}, got {actual_backend}")
    if expected_fast is not None:
        actual_fast = "match" if probe["fast_matched"] else "no-match"
        if actual_fast != expected_fast:
            failures.append(f"fast expected {expected_fast}, got {actual_fast}")

    diverged = probe["fast_matched"] != probe["backend_matched"]
    payload = {
        **probe,
        "fast_backend_diverged": diverged,
        "passed": not failures,
        "failures": failures,
    }
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        if failures:
            raise typer.Exit(1)
        return

    fast_status = (
        f"MATCH ({probe['fast_keyword']})"
        if probe["fast_matched"]
        else f"NO MATCH ({probe['fast_reason'] or 'no reason'})"
    )
    backend_status = (
        f"MATCH (num_matches={probe['backend_num_matches']})"
        if probe["backend_matched"]
        else "NO MATCH (num_matches=0)"
    )
    typer.echo(f"Offer: {probe['offer']}")
    typer.echo(f"Ingredient: {probe['ingredient']}")
    typer.echo(f"Fast matcher: {fast_status}")
    typer.echo(f"Backend matcher: {backend_status}")
    if diverged:
        typer.secho(
            "Warning: fast/backend results diverge; run `dm matcher compare-paths` for path diagnostics.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    if failures:
        typer.secho("FAIL: " + "; ".join(failures), fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if expected_backend is not None or expected_fast is not None:
        typer.secho("PASS", fg=typer.colors.GREEN)


@matcher_app.command("compare-paths", help="Compare live, fast, and backend matcher paths for one pair.")
def matcher_compare_paths(
    offer: Annotated[
        str,
        typer.Option("--offer", "--product", help="Offer/product name to inspect."),
    ],
    ingredient: Annotated[str, typer.Option("--ingredient", help="Recipe ingredient text to inspect.")],
    offer_category: Annotated[
        str,
        typer.Option("--offer-category", "--category", help="Optional offer category."),
    ] = "",
    brand: Annotated[str, typer.Option("--brand", help="Optional offer/product brand.")] = "",
    weight_grams: Annotated[
        float | None,
        typer.Option("--weight-grams", help="Optional offer/product weight in grams."),
    ] = None,
    recipe_name: Annotated[
        str,
        typer.Option("--recipe-name", help="Optional recipe name for backend context."),
    ] = "DM Matcher Path Compare",
    output_format: Annotated[
        Literal["text", "json"],
        typer.Option("--format", help="Output format."),
    ] = "text",
) -> None:
    if not offer.strip():
        raise typer.BadParameter("--offer must not be empty")
    if not ingredient.strip():
        raise typer.BadParameter("--ingredient must not be empty")

    payload = _compare_matcher_paths(
        offer=offer.strip(),
        ingredient=ingredient.strip(),
        offer_category=offer_category.strip(),
        brand=brand.strip(),
        weight_grams=weight_grams,
        recipe_name=recipe_name.strip(),
    )
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return

    live_status = (
        f"MATCH ({payload['legacy_live_keyword']})"
        if payload["legacy_live_matched"]
        else "NO MATCH"
    )
    fast_status = (
        f"MATCH ({payload['fast_keyword']})"
        if payload["fast_matched"]
        else f"NO MATCH ({payload['fast_reason'] or 'no reason'})"
    )
    backend_status = (
        f"MATCH (num_matches={payload['backend_num_matches']})"
        if payload["backend_matched"]
        else "NO MATCH (num_matches=0)"
    )
    typer.echo(f"Offer: {payload['offer']}")
    typer.echo(f"Ingredient: {payload['ingredient']}")
    typer.echo(f"Ingredient normalized: {payload['ingredient_normalized']}")
    typer.echo(f"Legacy live matcher: {live_status}")
    typer.echo(f"Canonical fast matcher: {fast_status}")
    typer.echo(f"Backend matcher: {backend_status}")
    typer.echo("Product keywords: " + ", ".join(payload["product_keywords"]))
    typer.echo("Precomputed offer keywords: " + ", ".join(payload["precomputed_offer_keywords"]))
    keyword_diff = payload["offer_keyword_diff"]
    if keyword_diff["extraction_only"] or keyword_diff["precomputed_only"]:
        typer.echo("Offer keyword diff:")
        typer.echo(
            "  extraction-only: "
            + (", ".join(keyword_diff["extraction_only"]) if keyword_diff["extraction_only"] else "none")
        )
        typer.echo(
            "  precomputed-only: "
            + (", ".join(keyword_diff["precomputed_only"]) if keyword_diff["precomputed_only"] else "none")
        )
        if payload["precomputed_keyword_explanations"]:
            typer.echo("Precomputed-only explanations:")
            for row in payload["precomputed_keyword_explanations"]:
                typer.echo(f"  - {row['keyword']}: {'; '.join(row['sources'])}")
    if payload["offer_specialty_qualifiers"]:
        qualifier_text = "; ".join(
            f"{key}: {', '.join(values)}"
            for key, values in payload["offer_specialty_qualifiers"].items()
        )
        typer.echo(f"Offer specialty qualifiers: {qualifier_text}")
    if payload["processed_checks"]:
        typer.echo("Processed checks:")
        for row in payload["processed_checks"]:
            prefix = f"  - {row.get('base', '?')} {row.get('mode', '?')}: {row['status']}"
            if row.get("indicators"):
                prefix += " [" + ", ".join(row["indicators"]) + "]"
            if row.get("product_indicator"):
                prefix += f" [product={row['product_indicator']}]"
            typer.echo(prefix)
    else:
        typer.echo("Processed checks: none")
    if payload["live_fast_diverged"] or payload["fast_backend_diverged"]:
        typer.secho("Warning: matcher paths diverge.", fg=typer.colors.YELLOW, err=True)


def _sanity_expected_literal(expected: str) -> str:
    value = expected.strip()
    if not value:
        raise typer.BadParameter("--expected must not be empty")
    if value.lower() in {"none", "null"}:
        return "None"
    return _toml_string(value)


_GENERATED_SANITY_COMMENT_RE = re.compile(
    r"^# (?P<policy_ref>[^:]+): generated by dm matcher add (?P<command>\S+)"
)
_SANITY_ID_COMMENT_RE = re.compile(r"^# sanity-id:\s*(?P<sanity_id>\S+)")


def _deep_sanity_metadata_by_line(text: str) -> dict[int, dict[str, str]]:
    metadata_by_line: dict[int, dict[str, str]] = {}
    current: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        generated_match = _GENERATED_SANITY_COMMENT_RE.match(stripped)
        if generated_match:
            current = {
                "policy_ref": generated_match.group("policy_ref"),
                "command": generated_match.group("command"),
            }
            metadata_by_line[line_number] = dict(current)
            continue
        sanity_id_match = _SANITY_ID_COMMENT_RE.match(stripped)
        if sanity_id_match:
            if current:
                current["sanity_id"] = sanity_id_match.group("sanity_id")
            metadata_by_line[line_number] = dict(current)
            continue
        if not stripped:
            current = {}
            metadata_by_line[line_number] = {}
            continue
        metadata_by_line[line_number] = dict(current)
    return metadata_by_line


def _deep_sanity_cases(
    *,
    paths: MatcherPaths,
) -> list[dict[str, Any]]:
    text = paths.deep_sanity_file.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(paths.deep_sanity_file))
    metadata_by_line = _deep_sanity_metadata_by_line(text)
    cases: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "test":
            continue
        if len(node.args) < 3:
            continue
        description_node = node.args[0]
        if not isinstance(description_node, ast.Constant) or not isinstance(description_node.value, str):
            continue
        metadata = metadata_by_line.get(node.lineno, {})
        expected = ast.get_source_segment(text, node.args[2]) or ""
        policy_ref = metadata.get("policy_ref", "")
        cases.append({
            "path": str(paths.deep_sanity_file),
            "line": node.lineno,
            "description": description_node.value,
            "expected": expected,
            "generated": bool(policy_ref),
            "policy_ref": policy_ref,
            "sanity_id": metadata.get("sanity_id", policy_ref),
            "command": metadata.get("command", ""),
        })
    return sorted(cases, key=lambda case: int(case["line"]))


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _literal_expected_value(node: ast.AST) -> str | int | None:
    if isinstance(node, ast.Constant):
        if node.value is None or isinstance(node.value, (str, int)):
            return node.value
    return None


def _literal_string_list(node: ast.AST) -> list[str] | None:
    if not isinstance(node, ast.List):
        return None
    values: list[str] = []
    for item in node.elts:
        value = _literal_string(item)
        if value is None:
            return None
        values.append(value)
    return values


def _literal_offer_dict(node: ast.AST) -> dict[str, str] | None:
    if not isinstance(node, ast.Dict):
        return None
    payload: dict[str, str] = {}
    for key_node, value_node in zip(node.keys, node.values, strict=False):
        if key_node is None:
            return None
        key = _literal_string(key_node)
        value = _literal_string(value_node)
        if key is None or value is None:
            return None
        payload[key] = value
    return payload


def _sanity_reconcile_case_from_node(
    *,
    text: str,
    node: ast.Call,
    metadata: Mapping[str, str],
    path: Path,
) -> dict[str, Any] | None:
    if len(node.args) < 3:
        return None
    description = _literal_string(node.args[0])
    if description is None:
        return None
    actual_node = node.args[1]
    expected_node = node.args[2]
    expected_value = _literal_expected_value(expected_node)
    expected_literal = ast.get_source_segment(text, expected_node) or ""
    case: dict[str, Any] = {
        "path": str(path),
        "line": node.lineno,
        "description": description,
        "expected": expected_literal,
        "expected_value": expected_value,
        "generated": bool(metadata.get("policy_ref", "")),
        "policy_ref": metadata.get("policy_ref", ""),
        "sanity_id": metadata.get("sanity_id", metadata.get("policy_ref", "")),
        "command": metadata.get("command", ""),
    }
    if isinstance(actual_node, ast.Call) and isinstance(actual_node.func, ast.Name):
        if actual_node.func.id == "match" and len(actual_node.args) >= 2:
            offer = _literal_string(actual_node.args[0])
            ingredient = _literal_string(actual_node.args[1])
            offer_category = _literal_string(actual_node.args[2]) if len(actual_node.args) >= 3 else ""
            if offer is None or ingredient is None or offer_category is None:
                case.update({"kind": "unsupported", "reason": "match() arguments are not string literals"})
                return case
            case.update({
                "kind": "fast-match",
                "offer": offer,
                "ingredient": ingredient,
                "offer_category": offer_category,
            })
            return case
        if actual_node.func.id == "recipe_match_num_named" and len(actual_node.args) >= 3:
            recipe_name = _literal_string(actual_node.args[0]) or "Sanity Recipe"
            ingredients = _literal_string_list(actual_node.args[1])
            offer_dict = _literal_offer_dict(actual_node.args[2])
            if not ingredients or offer_dict is None or not offer_dict.get("name"):
                case.update({"kind": "unsupported", "reason": "recipe_match_num_named() arguments are not literal/simple"})
                return case
            case.update({
                "kind": "backend-match",
                "recipe_name": recipe_name,
                "ingredient": ingredients[0],
                "offer": offer_dict["name"],
                "offer_category": offer_dict.get("category", ""),
            })
            return case
    case.update({"kind": "unsupported", "reason": "actual expression is not supported by reconcile-sanity"})
    return case


def _deep_sanity_reconcile_cases(paths: MatcherPaths) -> list[dict[str, Any]]:
    text = paths.deep_sanity_file.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(paths.deep_sanity_file))
    metadata_by_line = _deep_sanity_metadata_by_line(text)
    cases: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "test":
            continue
        case = _sanity_reconcile_case_from_node(
            text=text,
            node=node,
            metadata=metadata_by_line.get(node.lineno, {}),
            path=paths.deep_sanity_file,
        )
        if case is not None:
            cases.append(case)
    return sorted(cases, key=lambda case: int(case["line"]))


def _normalize_sanity_value_for_json(value: str | int | None) -> str | int | None:
    return value


def _sanity_expected_literal_from_value(value: str | int | None) -> str:
    if value is None:
        return "None"
    if isinstance(value, int):
        return str(value)
    return _toml_string(value)


def _reconcile_deep_sanity_case(case: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(case)
    kind = str(case.get("kind") or "")
    if kind == "fast-match":
        payload = _compare_matcher_paths(
            offer=str(case["offer"]),
            ingredient=str(case["ingredient"]),
            offer_category=str(case.get("offer_category") or ""),
            brand="",
            weight_grams=None,
            recipe_name="DM Matcher Sanity Reconcile",
        )
        actual_value = payload["fast_keyword"] if payload["fast_matched"] else None
        row.update({
            "actual_value": actual_value,
            "actual_literal": _sanity_expected_literal_from_value(actual_value),
            "classification": (
                "ok"
                if actual_value == case.get("expected_value")
                else "expected_parent_or_stale_canonical"
            ),
            "matches_expected": actual_value == case.get("expected_value"),
            "fast_reason": payload["fast_reason"],
        })
        return row
    if kind == "backend-match":
        probe = _probe_matcher_pair(
            offer=str(case["offer"]),
            ingredient=str(case["ingredient"]),
            offer_category=str(case.get("offer_category") or ""),
            brand="",
            weight_grams=None,
            recipe_name=str(case.get("recipe_name") or "DM Matcher Sanity Reconcile"),
        )
        actual_value = int(probe["backend_num_matches"])
        row.update({
            "actual_value": actual_value,
            "actual_literal": str(actual_value),
            "classification": "ok" if actual_value == case.get("expected_value") else "backend_count_drift",
            "matches_expected": actual_value == case.get("expected_value"),
        })
        return row
    row.update({
        "actual_value": None,
        "actual_literal": "",
        "classification": "unsupported",
        "matches_expected": None,
    })
    return row


def _filter_sanity_reconcile_cases(
    cases: Iterable[dict[str, Any]],
    *,
    selector: str | None,
    command_name: str | None,
    all_generated: bool,
) -> list[dict[str, Any]]:
    normalized_command = command_name.strip() if command_name else None
    return [
        case for case in cases
        if _sanity_case_matches(
            case,
            selector=selector,
            command_name=normalized_command,
            generated_only=all_generated,
        )
    ]


def _sanity_case_matches(
    case: Mapping[str, Any],
    *,
    selector: str | None,
    command_name: str | None,
    generated_only: bool,
) -> bool:
    if generated_only and not case.get("generated"):
        return False
    if command_name and str(case.get("command", "")) != command_name:
        return False
    if selector is None or not selector.strip():
        return True
    needle = selector.strip().lower()
    haystack = (
        str(case.get("description", "")),
        str(case.get("expected", "")),
        str(case.get("policy_ref", "")),
        str(case.get("sanity_id", "")),
        str(case.get("command", "")),
    )
    return any(needle in value.lower() for value in haystack)


def _replace_ast_segment(text: str, node: ast.AST, replacement: str) -> str:
    if (
        not hasattr(node, "lineno")
        or not hasattr(node, "col_offset")
        or not hasattr(node, "end_lineno")
        or not hasattr(node, "end_col_offset")
    ):
        raise typer.BadParameter("Cannot locate expected-value source span")
    lines = text.splitlines(keepends=True)

    def utf8_byte_col_to_index(line: str, byte_col: int) -> int:
        return len(line.encode("utf-8")[:byte_col].decode("utf-8"))

    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    start = offsets[node.lineno - 1] + utf8_byte_col_to_index(lines[node.lineno - 1], node.col_offset)
    end = offsets[node.end_lineno - 1] + utf8_byte_col_to_index(lines[node.end_lineno - 1], node.end_col_offset)
    return text[:start] + replacement + text[end:]


def _update_deep_sanity_expected(
    *,
    paths: MatcherPaths,
    selector: str,
    expected: str,
    dry_run: bool,
) -> dict[str, Any]:
    selector = selector.strip()
    if not selector:
        raise typer.BadParameter("selector must not be empty")
    expected_literal = _sanity_expected_literal(expected)
    text = paths.deep_sanity_file.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(paths.deep_sanity_file))
    metadata_by_line = _deep_sanity_metadata_by_line(text)
    matches: list[tuple[str, ast.AST, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "test":
            continue
        if len(node.args) < 3:
            continue
        description_node = node.args[0]
        if not isinstance(description_node, ast.Constant) or not isinstance(description_node.value, str):
            continue
        description = description_node.value
        metadata = metadata_by_line.get(node.lineno, {})
        haystack = (
            description,
            metadata.get("policy_ref", ""),
            metadata.get("sanity_id", ""),
            metadata.get("command", ""),
        )
        if any(selector.lower() in value.lower() for value in haystack):
            matches.append((description, node.args[2], node.lineno))
    if not matches:
        raise typer.BadParameter(f"No run_deep_matcher_sanity.py test matched selector: {selector}")
    if len(matches) > 1:
        descriptions = "\n".join(f"  line {line}: {description}" for description, _, line in matches[:10])
        raise typer.BadParameter(
            f"Selector matched {len(matches)} sanity tests; make it more specific:\n{descriptions}"
        )
    description, expected_node, line = matches[0]
    old_literal = ast.get_source_segment(text, expected_node) or ""
    new_text = _replace_ast_segment(text, expected_node, expected_literal)
    changed = new_text != text
    if changed and not dry_run:
        paths.deep_sanity_file.write_text(new_text, encoding="utf-8")
    return {
        "description": description,
        "line": line,
        "old": old_literal,
        "new": expected_literal,
        "changed": changed,
        "path": str(paths.deep_sanity_file),
    }


@matcher_app.command("sanity-find", help="Find run_deep_matcher_sanity.py tests by text or generated metadata.")
def matcher_sanity_find(
    selector: Annotated[
        str | None,
        typer.Argument(help="Description, expected literal, policy ref, sanity-id, or command substring."),
    ] = None,
    command_name: Annotated[
        str | None,
        typer.Option("--command", help="Restrict to tests generated by one dm matcher add command."),
    ] = None,
    generated_only: Annotated[
        bool,
        typer.Option("--generated-only", help="Only show tests inside generated sanity blocks."),
    ] = False,
    limit: Annotated[int, typer.Option("--limit", help="Maximum text rows to print.")] = 50,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to read instead of /app.")] = None,
    output_format: Annotated[
        Literal["text", "json"],
        typer.Option("--format", help="Output format."),
    ] = "text",
) -> None:
    if limit < 1:
        raise typer.BadParameter("--limit must be at least 1")
    paths = _paths(tree_root)
    normalized_command = command_name.strip() if command_name else None
    cases = [
        case for case in _deep_sanity_cases(paths=paths)
        if _sanity_case_matches(
            case,
            selector=selector,
            command_name=normalized_command,
            generated_only=generated_only,
        )
    ]
    payload = {
        "path": str(paths.deep_sanity_file),
        "selector": selector or "",
        "command": normalized_command or "",
        "generated_only": generated_only,
        "count": len(cases),
        "cases": cases,
    }
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        if not cases:
            raise typer.Exit(1)
        return
    if not cases:
        typer.echo("No matching deep sanity tests found.", err=True)
        raise typer.Exit(1)
    for case in cases[:limit]:
        typer.echo(f"{case['path']}:{case['line']}: {case['description']}")
        typer.echo(f"  expected: {case['expected']}")
        if case["generated"]:
            typer.echo(
                f"  generated: {case['command']} policy_ref={case['policy_ref']} sanity_id={case['sanity_id']}"
            )
    if len(cases) > limit:
        typer.echo(f"... {len(cases) - limit} more match(es); rerun with --limit {len(cases)} or --format json.")


@matcher_app.command("sanity-update", help="Update one expected value in run_deep_matcher_sanity.py.")
def matcher_sanity_update(
    selector: Annotated[
        str,
        typer.Argument(help="Unique substring of the sanity test description."),
    ],
    expected: Annotated[
        str,
        typer.Option("--expected", help="New expected canonical, or None/null for no match."),
    ],
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the change without writing.")] = False,
) -> None:
    paths = _paths(tree_root)
    result = _update_deep_sanity_expected(
        paths=paths,
        selector=selector,
        expected=expected,
        dry_run=dry_run,
    )
    prefix = "Would update" if dry_run else "Updated"
    if not result["changed"]:
        prefix = "Already up to date"
    typer.echo(f"{prefix} {result['path']}:{result['line']}")
    typer.echo(f"  test: {result['description']}")
    typer.echo(f"  expected: {result['old']} -> {result['new']}")


@matcher_app.command("reconcile-sanity", help="Compare generated sanity expectations with current matcher behavior.")
def matcher_reconcile_sanity(
    selector: Annotated[
        str | None,
        typer.Argument(help="Description, policy ref, sanity-id, or command substring."),
    ] = None,
    command_name: Annotated[
        str | None,
        typer.Option("--command", help="Restrict to tests generated by one dm matcher add command."),
    ] = None,
    all_generated: Annotated[
        bool,
        typer.Option("--all-generated", help="Scan all generated sanity rows. Required when no selector is given."),
    ] = False,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Update simple generated sanity expected values that differ."),
    ] = False,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to read/edit instead of /app.")] = None,
    output_format: Annotated[
        Literal["text", "json"],
        typer.Option("--format", help="Output format."),
    ] = "text",
) -> None:
    if not selector and not all_generated:
        raise typer.BadParameter("pass a selector or --all-generated")
    paths = _paths(tree_root)
    cases = _filter_sanity_reconcile_cases(
        _deep_sanity_reconcile_cases(paths),
        selector=selector,
        command_name=command_name,
        all_generated=all_generated,
    )
    rows = [_reconcile_deep_sanity_case(case) for case in cases]
    drifted = [row for row in rows if row.get("matches_expected") is False]
    unsupported = [row for row in rows if row.get("classification") == "unsupported"]
    applied: list[dict[str, Any]] = []
    if apply:
        for row in drifted:
            if not row.get("generated"):
                continue
            if row.get("kind") != "fast-match":
                continue
            selector_id = str(row.get("description") or row.get("sanity_id") or row.get("policy_ref"))
            actual_value = row.get("actual_value")
            result = _update_deep_sanity_expected(
                paths=paths,
                selector=selector_id,
                expected="None" if actual_value is None else str(actual_value),
                dry_run=False,
            )
            applied.append(result)
    payload = {
        "path": str(paths.deep_sanity_file),
        "selector": selector or "",
        "command": command_name or "",
        "all_generated": all_generated,
        "count": len(rows),
        "drift_count": len(drifted),
        "unsupported_count": len(unsupported),
        "applied_count": len(applied),
        "cases": [
            {
                **row,
                "expected_value": _normalize_sanity_value_for_json(row.get("expected_value")),
                "actual_value": _normalize_sanity_value_for_json(row.get("actual_value")),
            }
            for row in rows
        ],
        "applied": applied,
    }
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        if not rows:
            raise typer.Exit(1)
        return
    if not rows:
        typer.echo("No matching deep sanity tests found.", err=True)
        raise typer.Exit(1)
    typer.echo(
        f"reconcile-sanity: {len(rows)} checked, {len(drifted)} drifted, "
        f"{len(unsupported)} unsupported"
    )
    for row in rows:
        status = "OK" if row.get("matches_expected") is True else (
            "DRIFT" if row.get("matches_expected") is False else "SKIP"
        )
        typer.echo(f"{status} {row['path']}:{row['line']}: {row['description']}")
        typer.echo(f"  expected: {row.get('expected')}  actual: {row.get('actual_literal') or row.get('classification')}")
        if row.get("classification") not in {"ok", "unsupported"}:
            typer.echo(f"  classification: {row['classification']}")
    if applied:
        typer.echo(f"Applied {len(applied)} sanity expected update(s).")


@matcher_app.command("guide", help="Show the recommended matcher workflow for a rule shape.")
def matcher_guide(
    shape: Annotated[str | None, typer.Argument(help="Rule shape, e.g. pnb, keyword-synonym, no-match-policy.")] = None,
    list_shapes: Annotated[bool, typer.Option("--list", help="List known rule shapes.")] = False,
) -> None:
    if list_shapes:
        for key in sorted(GUIDE_SHAPES):
            guide = GUIDE_SHAPES[key]
            typer.echo(f"{guide.label}: {guide.status}")
        return
    if shape is None:
        typer.echo("Pass a rule shape, or use --list to see known shapes.")
        raise typer.Exit(2)

    key = _guide_key(shape)
    guide = GUIDE_SHAPES.get(key)
    if guide is None:
        known = ", ".join(sorted(GUIDE_SHAPES))
        typer.echo(f"Unknown matcher rule shape: {shape}", err=True)
        typer.echo(f"Known shapes: {known}", err=True)
        typer.echo("Fallback: edit according to the runbook, then run ./bin/dm matcher preflight and gates.", err=True)
        raise typer.Exit(2)
    _print_guide(guide)


@matcher_app.command("list", help="List matcher entries on a registry or runtime-overlay surface.")
def matcher_list(
    surface_name: Annotated[
        str,
        typer.Argument(help="Surface to list, e.g. keyword-synonym, ingredient-parent, specialty-qualifier, match-bridge, pnb, fpb, ksbc."),
    ],
    term: Annotated[str | None, typer.Option("--term", help="Filter by entry id, canonical, variant, keyword, or value.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to read instead of /app.")] = None,
    include_inactive: Annotated[
        bool,
        typer.Option("--include-inactive", help="Include entries with status = inactive."),
    ] = False,
    effective: Annotated[
        bool,
        typer.Option("--effective", help="List effective runtime values with base/update/overlay origin where supported."),
    ] = False,
    output_format: Annotated[
        Literal["text", "json"],
        typer.Option("--format", help="Output format."),
    ] = "text",
) -> None:
    paths = _paths(tree_root)
    surface_key = _matcher_surface_key(surface_name)
    if effective:
        rows = _runtime_effective_origin_rows(surface_key, term)
        if rows is None:
            raise typer.BadParameter(f"--effective is only supported for pnb, fpb, and ksbc; got {surface_name}")
        if output_format == "json":
            typer.echo(json.dumps(rows, ensure_ascii=False, indent=2))
            return
        for row in rows:
            typer.echo(f"{row['surface']}\t{row['keyword']}\t{row['value']}\t{row['origin']}")
        if not rows:
            typer.echo("No entries found.")
        return
    if surface_key in RUNTIME_OVERLAY_SURFACES:
        surface = RUNTIME_OVERLAY_SURFACES[surface_key]
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_overlay_matching_entries(
            sections,
            surface,
            term,
            include_inactive=include_inactive,
        )
        if output_format == "json":
            payload = [
                {
                    "id": str(entry.get("id") or _runtime_overlay_entry_id(surface, str(entry.get("keyword", "")))),
                    "status": str(entry.get("status", "active")),
                    "surface": surface.command,
                    "keyword": str(entry.get("keyword", "")),
                    surface.value_field: list(entry.get(surface.value_field, [])),
                    "reason": str(entry.get("reason", "")),
                }
                for entry in matches
            ]
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        for entry in matches:
            typer.echo(_runtime_overlay_entry_label(surface, entry))
        if not matches:
            typer.echo("No entries found.")
        return

    if surface_key in RUNTIME_PAIR_SURFACES:
        surface = RUNTIME_PAIR_SURFACES[surface_key]
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_pair_matching_entries(
            sections,
            surface,
            term,
            include_inactive=include_inactive,
        )
        if output_format == "json":
            payload = [
                {
                    "id": str(
                        entry.get("id")
                        or _runtime_pair_entry_id(
                            surface,
                            str(entry.get(surface.source_field, "")),
                            str(entry.get(surface.target_field, "")),
                        )
                    ),
                    "status": str(entry.get("status", "active")),
                    "surface": surface.command,
                    surface.source_field: str(entry.get(surface.source_field, "")),
                    surface.target_field: str(entry.get(surface.target_field, "")),
                    "reason": str(entry.get("reason", "")),
                }
                for entry in matches
            ]
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        for entry in matches:
            typer.echo(_runtime_pair_entry_label(surface, entry))
        if not matches:
            typer.echo("No entries found.")
        return

    if surface_key in RUNTIME_TERM_SET_SURFACES:
        surface = RUNTIME_TERM_SET_SURFACES[surface_key]
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_term_set_matching_entries(
            sections,
            surface,
            term,
            include_inactive=include_inactive,
        )
        if output_format == "json":
            payload = [
                {
                    "id": str(
                        entry.get("id")
                        or _runtime_term_set_entry_id(
                            surface,
                            tuple(str(term) for term in entry.get(surface.value_field, [])),
                        )
                    ),
                    "status": str(entry.get("status", "active")),
                    "surface": surface.command,
                    surface.value_field: list(entry.get(surface.value_field, [])),
                    "reason": str(entry.get("reason", "")),
                }
                for entry in matches
            ]
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        for entry in matches:
            typer.echo(_runtime_term_set_entry_label(surface, entry))
        if not matches:
            typer.echo("No entries found.")
        return

    if surface_key in RUNTIME_SET_UPDATE_SURFACES:
        surface = RUNTIME_SET_UPDATE_SURFACES[surface_key]
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_set_update_matching_entries(
            sections,
            surface,
            term,
            include_inactive=include_inactive,
        )
        if output_format == "json":
            payload = [
                {
                    "id": str(
                        entry.get("id")
                        or _runtime_set_update_entry_id(
                            surface,
                            str(entry.get("action", surface.default_action)),
                            tuple(str(term) for term in entry.get("terms", [])),
                        )
                    ),
                    "status": str(entry.get("status", "active")),
                    "surface": surface.command,
                    "action": str(entry.get("action", surface.default_action)),
                    "terms": list(entry.get("terms", [])),
                    "reason": str(entry.get("reason", "")),
                }
                for entry in matches
            ]
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        for entry in matches:
            typer.echo(_runtime_set_update_entry_label(surface, entry))
        if not matches:
            typer.echo("No entries found.")
        return

    if surface_key in RUNTIME_CONTEXT_SURFACES:
        surface = RUNTIME_CONTEXT_SURFACES[surface_key]
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_context_matching_entries(
            sections,
            surface,
            term,
            include_inactive=include_inactive,
        )
        if output_format == "json":
            payload = [
                {
                    "id": str(entry.get("id") or _runtime_context_entry_id(surface, str(entry.get(surface.key_field, "")))),
                    "status": str(entry.get("status", "active")),
                    "surface": surface.command,
                    surface.key_field: str(entry.get(surface.key_field, "")),
                    surface.values_field: list(entry.get(surface.values_field, [])),
                    "reason": str(entry.get("reason", "")),
                }
                for entry in matches
            ]
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        for entry in matches:
            typer.echo(_runtime_context_entry_label(surface, entry))
        if not matches:
            typer.echo("No entries found.")
        return

    if surface_key in RUNTIME_COMPOUND_SURFACES:
        surface = RUNTIME_COMPOUND_SURFACES[surface_key]
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_compound_matching_entries(
            sections,
            surface,
            term,
            include_inactive=include_inactive,
        )
        if output_format == "json":
            payload = [
                {
                    "id": str(
                        entry.get("id")
                        or _runtime_compound_entry_id(
                            surface,
                            str(entry.get("mode", "")),
                            tuple(str(keyword) for keyword in entry.get("keywords", [])),
                        )
                    ),
                    "status": str(entry.get("status", "active")),
                    "surface": surface.command,
                    "mode": str(entry.get("mode", "")),
                    "keywords": list(entry.get("keywords", [])),
                    "reason": str(entry.get("reason", "")),
                }
                for entry in matches
            ]
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        for entry in matches:
            typer.echo(_runtime_compound_entry_label(surface, entry))
        if not matches:
            typer.echo("No entries found.")
        return

    if surface_key in RUNTIME_SPECIALTY_SURFACES:
        surface = RUNTIME_SPECIALTY_SURFACES[surface_key]
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_specialty_matching_entries(
            sections,
            surface,
            term,
            include_inactive=include_inactive,
        )
        if output_format == "json":
            payload = [
                {
                    "id": str(
                        entry.get("id")
                        or _runtime_specialty_entry_id(
                            surface,
                            str(entry.get(surface.key_field, "")),
                            tuple(str(value) for value in entry.get(surface.values_field, [])),
                        )
                    ),
                    "status": str(entry.get("status", "active")),
                    "surface": surface.command,
                    surface.key_field: str(entry.get(surface.key_field, "")),
                    surface.values_field: list(entry.get(surface.values_field, [])),
                    "bidirectional": bool(entry.get("bidirectional", False)),
                    "reason": str(entry.get("reason", "")),
                }
                for entry in matches
            ]
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        for entry in matches:
            typer.echo(_runtime_specialty_entry_label(surface, entry))
        if not matches:
            typer.echo("No entries found.")
        return

    if surface_key == "spice-fresh-rule":
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_spice_fresh_matching_entries(
            sections,
            term,
            include_inactive=include_inactive,
        )
        if output_format == "json":
            payload = [
                {
                    "id": str(entry.get("id") or _runtime_spice_fresh_entry_id(str(entry.get("keyword", "")))),
                    "status": str(entry.get("status", "active")),
                    "surface": "spice-fresh-rule",
                    "keyword": str(entry.get("keyword", "")),
                    **{field: list(entry.get(field, [])) for field in _SPICE_FRESH_RULE_FIELDS},
                    "reason": str(entry.get("reason", "")),
                }
                for entry in matches
            ]
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        for entry in matches:
            typer.echo(_runtime_spice_fresh_entry_label(entry))
        if not matches:
            typer.echo("No entries found.")
        return

    if surface_key == "product-name-substitution":
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_product_substitution_matching_entries(
            sections,
            term,
            include_inactive=include_inactive,
        )
        if output_format == "json":
            payload = [
                {
                    "id": str(
                        entry.get("id")
                        or _runtime_product_substitution_entry_id(
                            tuple(str(word) for word in entry.get("required_words", [])),
                            str(entry.get("old_keyword", "")),
                            str(entry.get("new_keyword", "")),
                        )
                    ),
                    "status": str(entry.get("status", "active")),
                    "surface": "product-name-substitution",
                    "required_words": list(entry.get("required_words", [])),
                    "old_keyword": str(entry.get("old_keyword", "")),
                    "new_keyword": str(entry.get("new_keyword", "")),
                    "reason": str(entry.get("reason", "")),
                }
                for entry in matches
            ]
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        for entry in matches:
            typer.echo(_runtime_product_substitution_entry_label(entry))
        if not matches:
            typer.echo("No entries found.")
        return

    if surface_key == "secondary-ingredient-pattern":
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_secondary_pattern_matching_entries(
            sections,
            term,
            include_inactive=include_inactive,
        )
        if output_format == "json":
            payload = [
                {
                    "id": str(entry.get("id") or _runtime_secondary_pattern_entry_id(str(entry.get("keyword", "")))),
                    "status": str(entry.get("status", "active")),
                    "surface": "secondary-ingredient-pattern",
                    "keyword": str(entry.get("keyword", "")),
                    "blockers": list(entry.get("blockers", [])),
                    "exceptions": list(entry.get("exceptions", [])),
                    "reason": str(entry.get("reason", "")),
                }
                for entry in matches
            ]
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        for entry in matches:
            typer.echo(_runtime_secondary_pattern_entry_label(entry))
        if not matches:
            typer.echo("No entries found.")
        return

    surface, path = _registry_surface_file(paths, surface_key)
    matches = _registry_matching_records(
        _registry_entry_records(surface, path),
        term,
        include_inactive=include_inactive,
    )
    if output_format == "json":
        payload = [
            {
                "entry_id": record.entry_id,
                "status": record.status,
                "surface": record.surface,
                "canonical": record.canonical,
                "terms": list(record.terms),
            }
            for record in matches
        ]
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for record in matches:
        typer.echo(_registry_entry_label(record))
    if not matches:
        typer.echo("No entries found.")


@matcher_app.command("remove", help="Soft-disable one runtime-overlay rule by exact id and remove its generated canary.")
def matcher_remove(
    rule_id: Annotated[str, typer.Argument(help="Runtime overlay rule id, e.g. runtime_pnb_gradde.")],
    reason: Annotated[str, typer.Option("--reason", help="Why this rule is being removed.")],
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run Track A gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the change without writing files.")] = False,
    write_sanity: Annotated[
        bool,
        typer.Option("--sanity/--no-sanity", help="Remove generated membership canaries for this rule."),
    ] = True,
) -> None:
    _remove_runtime_overlay_rule_by_id(
        rule_id=rule_id,
        reason=reason,
        tree_root=tree_root,
        run_gates=run_gates,
        report_root=report_root,
        dry_run=dry_run,
        write_sanity=write_sanity,
    )


@matcher_app.command("inactivate", help="Set a matcher registry or runtime-overlay entry to inactive.")
def matcher_inactivate(
    surface_name: Annotated[
        str,
        typer.Argument(help="Surface, e.g. keyword-synonym, ingredient-parent, pnb, fpb, ksbc."),
    ],
    selector: Annotated[str, typer.Argument(help="Entry id or unique term/keyword to inactivate.")],
    reason: Annotated[str, typer.Option("--reason", help="Why this entry is being inactivated.")],
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run the relevant gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the change without writing files.")] = False,
) -> None:
    if not reason.strip():
        raise typer.BadParameter("--reason must not be empty")
    paths = _paths(tree_root)
    surface_key = _matcher_surface_key(surface_name)
    if surface_key in RUNTIME_OVERLAY_SURFACES:
        surface = _runtime_overlay_surface_from_arg(surface_key)
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_overlay_matching_entries(
            sections,
            surface,
            selector,
            include_inactive=True,
        )
        if len(matches) != 1:
            labels = "\n".join(_runtime_overlay_entry_label(surface, entry) for entry in matches[:20])
            detail = f"\n{labels}" if labels else ""
            raise typer.BadParameter(f"selector must match exactly one {surface.command} entry; got {len(matches)}{detail}")
        entry = matches[0]
        entry["id"] = str(entry.get("id") or _runtime_overlay_entry_id(surface, str(entry.get("keyword", ""))))
        entry["status"] = "inactive"
        entry["inactive_reason"] = reason.strip()
        preview = _runtime_overlay_entry_block(surface, entry)
        if dry_run:
            typer.echo(preview)
            return
        paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
        typer.echo(f"Inactivated runtime overlay entry: {entry['id']}")
        if not run_gates:
            typer.echo("Skipped gates (--no-run-gates).")
            return
        raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))

    if surface_key in RUNTIME_PAIR_SURFACES:
        surface = RUNTIME_PAIR_SURFACES[surface_key]
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_pair_matching_entries(
            sections,
            surface,
            selector,
            include_inactive=True,
        )
        if len(matches) != 1:
            labels = "\n".join(_runtime_pair_entry_label(surface, entry) for entry in matches[:20])
            detail = f"\n{labels}" if labels else ""
            raise typer.BadParameter(f"selector must match exactly one {surface.command} entry; got {len(matches)}{detail}")
        entry = matches[0]
        entry["id"] = str(
            entry.get("id")
            or _runtime_pair_entry_id(
                surface,
                str(entry.get(surface.source_field, "")),
                str(entry.get(surface.target_field, "")),
            )
        )
        entry["status"] = "inactive"
        entry["inactive_reason"] = reason.strip()
        preview = _runtime_pair_entry_block(surface, entry)
        if dry_run:
            typer.echo(preview)
            return
        paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
        typer.echo(f"Inactivated runtime overlay entry: {entry['id']}")
        if not run_gates:
            typer.echo("Skipped gates (--no-run-gates).")
            return
        raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))

    if surface_key in RUNTIME_TERM_SET_SURFACES:
        surface = RUNTIME_TERM_SET_SURFACES[surface_key]
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_term_set_matching_entries(
            sections,
            surface,
            selector,
            include_inactive=True,
        )
        if len(matches) != 1:
            labels = "\n".join(_runtime_term_set_entry_label(surface, entry) for entry in matches[:20])
            detail = f"\n{labels}" if labels else ""
            raise typer.BadParameter(f"selector must match exactly one {surface.command} entry; got {len(matches)}{detail}")
        entry = matches[0]
        terms = tuple(str(term) for term in entry.get(surface.value_field, []))
        entry["id"] = str(entry.get("id") or _runtime_term_set_entry_id(surface, terms))
        entry["status"] = "inactive"
        entry["inactive_reason"] = reason.strip()
        preview = _runtime_term_set_entry_block(surface, entry)
        if dry_run:
            typer.echo(preview)
            return
        paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
        typer.echo(f"Inactivated runtime overlay entry: {entry['id']}")
        if not run_gates:
            typer.echo("Skipped gates (--no-run-gates).")
            return
        raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))

    if surface_key in RUNTIME_SET_UPDATE_SURFACES:
        surface = RUNTIME_SET_UPDATE_SURFACES[surface_key]
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_set_update_matching_entries(
            sections,
            surface,
            selector,
            include_inactive=True,
        )
        if len(matches) != 1:
            labels = "\n".join(_runtime_set_update_entry_label(surface, entry) for entry in matches[:20])
            detail = f"\n{labels}" if labels else ""
            raise typer.BadParameter(f"selector must match exactly one {surface.command} entry; got {len(matches)}{detail}")
        entry = matches[0]
        action = str(entry.get("action", surface.default_action))
        terms = tuple(str(term) for term in entry.get("terms", []))
        entry["id"] = str(entry.get("id") or _runtime_set_update_entry_id(surface, action, terms))
        entry["status"] = "inactive"
        entry["inactive_reason"] = reason.strip()
        preview = _runtime_set_update_entry_block({"section": surface.section, **entry})
        if dry_run:
            typer.echo(preview)
            return
        paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
        typer.echo(f"Inactivated runtime overlay entry: {entry['id']}")
        if not run_gates:
            typer.echo("Skipped gates (--no-run-gates).")
            return
        raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))

    if surface_key in RUNTIME_CONTEXT_SURFACES:
        surface = RUNTIME_CONTEXT_SURFACES[surface_key]
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_context_matching_entries(
            sections,
            surface,
            selector,
            include_inactive=True,
        )
        if len(matches) != 1:
            labels = "\n".join(_runtime_context_entry_label(surface, entry) for entry in matches[:20])
            detail = f"\n{labels}" if labels else ""
            raise typer.BadParameter(f"selector must match exactly one {surface.command} entry; got {len(matches)}{detail}")
        entry = matches[0]
        entry["id"] = str(entry.get("id") or _runtime_context_entry_id(surface, str(entry.get(surface.key_field, ""))))
        entry["status"] = "inactive"
        entry["inactive_reason"] = reason.strip()
        preview = _runtime_context_entry_block(surface, entry)
        if dry_run:
            typer.echo(preview)
            return
        paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
        typer.echo(f"Inactivated runtime overlay entry: {entry['id']}")
        if not run_gates:
            typer.echo("Skipped gates (--no-run-gates).")
            return
        raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))

    if surface_key in RUNTIME_COMPOUND_SURFACES:
        surface = RUNTIME_COMPOUND_SURFACES[surface_key]
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_compound_matching_entries(
            sections,
            surface,
            selector,
            include_inactive=True,
        )
        if len(matches) != 1:
            labels = "\n".join(_runtime_compound_entry_label(surface, entry) for entry in matches[:20])
            detail = f"\n{labels}" if labels else ""
            raise typer.BadParameter(f"selector must match exactly one {surface.command} entry; got {len(matches)}{detail}")
        entry = matches[0]
        mode = str(entry.get("mode", ""))
        keywords = tuple(str(keyword) for keyword in entry.get("keywords", []))
        entry["id"] = str(entry.get("id") or _runtime_compound_entry_id(surface, mode, keywords))
        entry["status"] = "inactive"
        entry["inactive_reason"] = reason.strip()
        preview = _runtime_compound_entry_block(surface, entry)
        if dry_run:
            typer.echo(preview)
            return
        paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
        typer.echo(f"Inactivated runtime overlay entry: {entry['id']}")
        if not run_gates:
            typer.echo("Skipped gates (--no-run-gates).")
            return
        raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))

    if surface_key in RUNTIME_SPECIALTY_SURFACES:
        surface = RUNTIME_SPECIALTY_SURFACES[surface_key]
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_specialty_matching_entries(
            sections,
            surface,
            selector,
            include_inactive=True,
        )
        if len(matches) != 1:
            labels = "\n".join(_runtime_specialty_entry_label(surface, entry) for entry in matches[:20])
            detail = f"\n{labels}" if labels else ""
            raise typer.BadParameter(f"selector must match exactly one {surface.command} entry; got {len(matches)}{detail}")
        entry = matches[0]
        key = str(entry.get(surface.key_field, ""))
        values = tuple(str(value) for value in entry.get(surface.values_field, []))
        entry["id"] = str(entry.get("id") or _runtime_specialty_entry_id(surface, key, values))
        entry["status"] = "inactive"
        entry["inactive_reason"] = reason.strip()
        preview = _runtime_specialty_entry_block(surface, entry)
        if dry_run:
            typer.echo(preview)
            return
        paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
        typer.echo(f"Inactivated runtime overlay entry: {entry['id']}")
        if not run_gates:
            typer.echo("Skipped gates (--no-run-gates).")
            return
        raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))

    if surface_key == "spice-fresh-rule":
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_spice_fresh_matching_entries(
            sections,
            selector,
            include_inactive=True,
        )
        if len(matches) != 1:
            labels = "\n".join(_runtime_spice_fresh_entry_label(entry) for entry in matches[:20])
            detail = f"\n{labels}" if labels else ""
            raise typer.BadParameter(f"selector must match exactly one spice-fresh-rule entry; got {len(matches)}{detail}")
        entry = matches[0]
        entry["id"] = str(entry.get("id") or _runtime_spice_fresh_entry_id(str(entry.get("keyword", ""))))
        entry["status"] = "inactive"
        entry["inactive_reason"] = reason.strip()
        preview = _runtime_spice_fresh_entry_block(entry)
        if dry_run:
            typer.echo(preview)
            return
        paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
        typer.echo(f"Inactivated runtime overlay entry: {entry['id']}")
        if not run_gates:
            typer.echo("Skipped gates (--no-run-gates).")
            return
        raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))

    if surface_key == "product-name-substitution":
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_product_substitution_matching_entries(
            sections,
            selector,
            include_inactive=True,
        )
        if len(matches) != 1:
            labels = "\n".join(_runtime_product_substitution_entry_label(entry) for entry in matches[:20])
            detail = f"\n{labels}" if labels else ""
            raise typer.BadParameter(f"selector must match exactly one product-name-substitution entry; got {len(matches)}{detail}")
        entry = matches[0]
        required_words = tuple(str(word) for word in entry.get("required_words", []))
        entry["id"] = str(
            entry.get("id")
            or _runtime_product_substitution_entry_id(
                required_words,
                str(entry.get("old_keyword", "")),
                str(entry.get("new_keyword", "")),
            )
        )
        entry["status"] = "inactive"
        entry["inactive_reason"] = reason.strip()
        preview = _runtime_product_substitution_entry_block(entry)
        if dry_run:
            typer.echo(preview)
            return
        paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
        typer.echo(f"Inactivated runtime overlay entry: {entry['id']}")
        if not run_gates:
            typer.echo("Skipped gates (--no-run-gates).")
            return
        raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))

    if surface_key == "secondary-ingredient-pattern":
        sections = _read_runtime_overlay_sections(paths.runtime_overlay_file)
        matches = _runtime_secondary_pattern_matching_entries(
            sections,
            selector,
            include_inactive=True,
        )
        if len(matches) != 1:
            labels = "\n".join(_runtime_secondary_pattern_entry_label(entry) for entry in matches[:20])
            detail = f"\n{labels}" if labels else ""
            raise typer.BadParameter(f"selector must match exactly one secondary-ingredient-pattern entry; got {len(matches)}{detail}")
        entry = matches[0]
        entry["id"] = str(entry.get("id") or _runtime_secondary_pattern_entry_id(str(entry.get("keyword", ""))))
        entry["status"] = "inactive"
        entry["inactive_reason"] = reason.strip()
        preview = _runtime_secondary_pattern_entry_block(entry)
        if dry_run:
            typer.echo(preview)
            return
        paths.runtime_overlay_file.write_text(_runtime_overlay_file_text(sections), encoding="utf-8")
        typer.echo(f"Inactivated runtime overlay entry: {entry['id']}")
        if not run_gates:
            typer.echo("Skipped gates (--no-run-gates).")
            return
        raise typer.Exit(_run_track_a_runtime_gates(paths, report_root))

    surface, path = _registry_surface_file(paths, surface_key)
    records = _registry_entry_records(surface, path)
    matches = _registry_matching_records(records, selector, include_inactive=True)
    if len(matches) != 1:
        labels = "\n".join(_registry_entry_label(record) for record in matches[:20])
        detail = f"\n{labels}" if labels else ""
        raise typer.BadParameter(f"selector must match exactly one {surface} entry; got {len(matches)}{detail}")
    record = matches[0]
    new_block = _registry_entry_block_with_status(record.block, status="inactive", reason=reason)
    _write_registry_entry_block(path, record, new_block, dry_run=dry_run)
    if dry_run:
        return
    typer.echo(f"Inactivated registry entry: {record.entry_id}")
    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return
    raise typer.Exit(_run_track_b_inactivation_gates(paths, report_root))


def _timestamp_elapsed_seconds(started_at: str, finished_at: str) -> int | None:
    try:
        started = time.mktime(time.strptime(started_at, "%Y-%m-%dT%H:%M:%SZ"))
        finished = time.mktime(time.strptime(finished_at, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None
    return max(0, int(finished - started))


def _write_batch_metrics(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@matcher_batch_app.command("metrics", help="Start or finish a local matcher batch metrics note.")
def matcher_batch_metrics(
    start: Annotated[bool, typer.Option("--start", help="Start a local metrics note.")] = False,
    finish: Annotated[bool, typer.Option("--finish", help="Finish the current local metrics note.")] = False,
    note: Annotated[str | None, typer.Option("--note", help="Optional free-text note stored locally.")] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to use instead of /app.")] = None,
    output_format: Annotated[Literal["text", "json"], typer.Option("--format", help="Output format.")] = "text",
) -> None:
    if start == finish:
        raise typer.BadParameter("pass exactly one of --start or --finish")
    paths = _paths(tree_root)
    metrics_path = _matcher_batch_metrics_path(paths)
    if start:
        head, head_error = _git_output(paths, ["rev-parse", "HEAD"])
        changed_paths, status_error = _matcher_relevant_changed_paths(paths)
        payload: dict[str, Any] = {
            "schema_version": 1,
            "started_at": _utc_timestamp(),
            "start_head": head,
            "start_head_error": head_error,
            "start_dirty_matcher_paths": list(changed_paths),
            "git_status_error": status_error,
            "note": note or "",
        }
        _write_batch_metrics(metrics_path, payload)
    else:
        if not metrics_path.exists():
            raise typer.BadParameter(f"no local batch metrics file found: {metrics_path}")
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        finished_at = _utc_timestamp()
        report = _matcher_doctor_report(paths=paths, since=None, report_root=None)
        checks = report.get("checks") or []
        changed_paths, status_error = _matcher_relevant_changed_paths(paths)
        payload.update({
            "finished_at": finished_at,
            "elapsed_seconds": _timestamp_elapsed_seconds(str(payload.get("started_at") or ""), finished_at),
            "finish_dirty_matcher_paths": list(changed_paths),
            "finish_git_status_error": status_error,
            "doctor_status": report.get("status"),
            "doctor_blocking_error_count": sum(1 for check in checks if check.get("status") == "blocking_error"),
            "doctor_needs_action_count": sum(1 for check in checks if check.get("status") == "needs_action"),
            "finished_note": note or "",
        })
        _write_batch_metrics(metrics_path, payload)

    if output_format == "json":
        typer.echo(json.dumps({"path": str(metrics_path), "metrics": payload}, ensure_ascii=False, indent=2, sort_keys=True))
        return
    action = "Started" if start else "Finished"
    typer.echo(f"{action} matcher batch metrics: {metrics_path}")
    if finish:
        typer.echo(f"  elapsed_seconds: {payload.get('elapsed_seconds')}")
        typer.echo(f"  doctor_status: {payload.get('doctor_status')}")
        typer.echo(f"  doctor_needs_action_count: {payload.get('doctor_needs_action_count')}")
        typer.echo(f"  doctor_blocking_error_count: {payload.get('doctor_blocking_error_count')}")


@matcher_session_app.command("start", help="Start a matcher edit session and defer per-command gates.")
@matcher_batch_app.command("start", help="Start a matcher edit batch and defer per-command gates.")
def matcher_session_start(
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to use instead of /app.")] = None,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing session marker.")] = False,
) -> None:
    paths = _paths(tree_root)
    existing = _read_matcher_session_state(paths)
    if existing is not None and not force:
        state_path, state = existing
        started_at = state.get("started_at", "unknown")
        raise typer.BadParameter(f"matcher session already active since {started_at}: {state_path}")

    start_head, head_error = _git_output(paths, ["rev-parse", "HEAD"])
    changed_paths, status_error = _matcher_relevant_changed_paths(paths)
    state: dict[str, Any] = {
        "version": MATCHER_SESSION_VERSION,
        "started_at": _utc_timestamp(),
        "start_head": start_head,
        "start_head_error": head_error,
        "repo_root": str(paths.repo_root),
        "app_dir": str(paths.app_dir),
        "tree_root": str(paths.tree_root),
        "start_dirty_matcher_paths": list(changed_paths),
        "git_status_error": status_error,
    }
    state_path = _write_matcher_session_state(paths, state)

    typer.echo(f"Started matcher session: {state_path}")
    if head_error is not None:
        typer.echo(f"Git metadata unavailable: {head_error}")
    if status_error is not None:
        typer.echo(f"Git change listing unavailable: {status_error}")
    elif changed_paths:
        typer.echo("Matcher-relevant files were already dirty at session start:")
        for path in changed_paths:
            typer.echo(f"  {path}")
    typer.echo("Per-command matcher gates will be deferred until session finalize unless --run-gates is passed.")


@matcher_session_app.command("status", help="Show the active matcher session and matcher-relevant git changes.")
@matcher_batch_app.command("status", help="Show the active matcher batch and matcher-relevant git changes.")
def matcher_session_status(
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to use instead of /app.")] = None,
) -> None:
    paths = _paths(tree_root)
    existing = _read_matcher_session_state(paths)
    if existing is None:
        typer.echo("No active matcher session.")
        return

    state_path, state = existing
    typer.echo(f"Active matcher session: {state_path}")
    typer.echo(f"  started_at: {state.get('started_at', 'unknown')}")
    typer.echo(f"  start_head: {state.get('start_head') or 'unknown'}")

    changed_paths, status_error = _matcher_relevant_changed_paths(paths)
    if status_error is not None:
        typer.echo(f"Git change listing unavailable: {status_error}")
        return
    if not changed_paths:
        typer.echo("No matcher-relevant git changes detected.")
        return
    typer.echo("Matcher-relevant git changes:")
    for path in changed_paths:
        typer.echo(f"  {path}")


@matcher_session_app.command(
    "finalize",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Regenerate/promote/refresh once, then run one final matcher gate.",
)
@matcher_batch_app.command(
    "finalize",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Regenerate/promote/refresh once, then run one final matcher gate.",
)
def matcher_session_finalize(
    ctx: typer.Context,
    track: Annotated[Literal["A", "B"], typer.Option("--track", help="Final matcher gate track.")] = "B",
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to use instead of /app.")] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show doctor output and planned finalize steps without writing or running gates."),
    ] = False,
    allow_removals: Annotated[
        bool,
        typer.Option("--allow-removals", help="Pass confirmed removal allowance to baseline promotion."),
    ] = False,
    confirm_large_removals: Annotated[
        bool,
        typer.Option("--confirm-large-removals", help="Confirm more than five baseline removals."),
    ] = False,
    skip_promote: Annotated[
        bool,
        typer.Option("--skip-promote", help="Skip verified-term baseline promotion."),
    ] = False,
    skip_line_refs: Annotated[
        bool,
        typer.Option("--skip-line-refs", help="Skip inventory line-ref refresh."),
    ] = False,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
) -> None:
    paths = _paths(tree_root)
    existing = _read_matcher_session_state(paths)
    if existing is None and not dry_run:
        raise typer.BadParameter("no active matcher session; run dm matcher session start first")
    state_path: Path | None = None
    if existing is not None:
        state_path, _state = existing
    raw_args = _raw_args(ctx)

    steps: list[tuple[str, Any]] = [
        (
            "regen",
            lambda: _run_session_regen(tree_root=tree_root, report_root=report_root, check=False),
        ),
    ]
    if not skip_promote:
        steps.append((
            "promote",
            lambda: _run_session_promote(
                allow_removals=allow_removals,
                confirm_large_removals=confirm_large_removals,
                report_root=report_root,
            ),
        ))
    if not skip_line_refs:
        steps.append((
            "refresh-line-refs",
            lambda: _run_session_refresh_line_refs(paths=paths, tree_root=tree_root, report_root=report_root),
        ))
    steps.extend([
        (
            "regen --check",
            lambda: _run_session_regen(tree_root=tree_root, report_root=report_root, check=True),
        ),
        (
            "preflight",
            lambda: _run_session_preflight(tree_root=tree_root, report_root=report_root),
        ),
        (
            f"gates --track {track}",
            lambda: _run_session_gates(
                track=track,
                tree_root=tree_root,
                report_root=report_root,
                raw_args=raw_args,
            ),
        ),
    ])

    if dry_run:
        report = _matcher_doctor_report(paths=paths, since=None, report_root=report_root)
        typer.echo("matcher batch finalize dry-run")
        if state_path is None:
            typer.echo("  active batch: none")
        else:
            typer.echo(f"  active batch: {state_path}")
        typer.echo("")
        typer.echo(_format_matcher_doctor_text(report))
        typer.echo("")
        typer.echo("planned finalize steps:")
        for label, _run_step in steps:
            typer.echo(f"  - {label}")
        if raw_args:
            typer.echo("raw gate args:")
            typer.echo("  " + " ".join(raw_args))
        typer.echo("Dry run only; no files written and no gates run.")
        return

    assert state_path is not None
    for label, run_step in steps:
        typer.echo(f"\n=== session finalize: {label} ===")
        status = run_step()
        if status != 0:
            typer.echo(f"Session finalize failed at {label}; session remains active: {state_path}", err=True)
            raise typer.Exit(status)

    state_path.unlink(missing_ok=True)
    typer.echo(f"\nMatcher session finalized; cleared {state_path}")


@matcher_session_app.command("abort", help="Clear the matcher session marker without changing files.")
@matcher_batch_app.command("abort", help="Clear the matcher batch marker without changing files.")
def matcher_session_abort(
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to use instead of /app.")] = None,
) -> None:
    paths = _paths(tree_root)
    existing = _read_matcher_session_state(paths)
    if existing is None:
        typer.echo("No active matcher session.")
        return
    state_path, _state = existing
    state_path.unlink(missing_ok=True)
    typer.echo(f"Aborted matcher session: {state_path}")


@matcher_app.command(
    "doctor",
    help="Read-only matcher rule-change diagnostics and next-step hints.",
)
def matcher_doctor(
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to inspect instead of /app.")] = None,
    since: Annotated[str | None, typer.Option("--since", help="Compare matcher-relevant git changes since this ref.")] = None,
    output_format: Annotated[
        Literal["text", "json"],
        typer.Option("--format", help="Report format."),
    ] = "text",
    json_output: Annotated[bool, typer.Option("--json", help="Alias for --format json.")] = False,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
) -> None:
    paths = _paths(tree_root)
    report = _matcher_doctor_report(paths=paths, since=since, report_root=report_root)
    if json_output or output_format == "json":
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(_format_matcher_doctor_text(report))
    if report["status"] == "blocking_error":
        raise typer.Exit(1)


@matcher_app.command(
    "preflight",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Run matcher change pre-flight only. Wraps support_checks/run_matcher_change_preflight.py.",
)
def matcher_preflight(
    ctx: typer.Context,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to check instead of /app.")] = None,
    output_format: Annotated[
        Literal["text", "json"],
        typer.Option("--format", help="Report format."),
    ] = "text",
    refresh_snapshot: Annotated[
        bool,
        typer.Option("--refresh-snapshot", help="Refresh the known-issues snapshot."),
    ] = False,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
) -> None:
    args = [
        *_tree_root_args(tree_root),
        "--format",
        output_format,
    ]
    if refresh_snapshot:
        args.append("--refresh-snapshot")
    args.extend(_raw_args(ctx))
    status = _run_support_check(
        "run_matcher_change_preflight.py",
        args,
        tree_root=tree_root,
        report_root=report_root,
        cwd=APP_DIR,
    )
    raise typer.Exit(status)


@matcher_app.command("sanity", help="Run deep matcher sanity only. Wraps support_checks/run_deep_matcher_sanity.py.")
def matcher_sanity(
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
) -> None:
    status = _run_support_check(
        "run_deep_matcher_sanity.py",
        [],
        report_root=report_root,
        cwd=APP_DIR,
    )
    raise typer.Exit(status)


@matcher_app.command(
    "promote",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Promote verified-term baseline. Wraps support_checks/promote_term_baseline.py.",
)
def matcher_promote(
    ctx: typer.Context,
    language: Annotated[str, typer.Option("--language", help="Language package code.")] = "sv",
    market: Annotated[str, typer.Option("--market", help="Market code.")] = "SE",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would change without writing files.")] = False,
    apply_staged: Annotated[
        Path | None,
        typer.Option("--apply-staged", help="Apply files from a promote --output-dir promotion_manifest.json."),
    ] = None,
    migrate_hashes: Annotated[
        bool,
        typer.Option("--migrate-hashes", help="Backward-compatible no-op alias for promote."),
    ] = False,
    allow_removals: Annotated[
        bool,
        typer.Option("--allow-removals", help="Allow confirmed intentional baseline removals."),
    ] = False,
    confirm_large_removals: Annotated[
        bool,
        typer.Option("--confirm-large-removals", help="Confirm more than five truly removed baseline variants."),
    ] = False,
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", help="Stage changed files under this writable directory."),
    ] = None,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
) -> None:
    if apply_staged is not None:
        if _raw_args(ctx):
            raise typer.BadParameter("--apply-staged cannot be combined with raw pass-through args")
        paths = _paths(None)
        _apply_promote_staged_output(paths=paths, output_dir=apply_staged, dry_run=dry_run)
        return

    args = ["--language", language, "--market", market]
    if dry_run:
        args.append("--dry-run")
    if migrate_hashes:
        args.append("--migrate-hashes")
    if allow_removals:
        args.append("--allow-removals")
    if confirm_large_removals:
        args.append("--confirm-large-removals")
    if output_dir is not None:
        args.extend(["--output-dir", str(output_dir)])
    args.extend(_raw_args(ctx))
    status = _run_support_check(
        "promote_term_baseline.py",
        args,
        report_root=report_root,
        cwd=APP_DIR,
    )
    raise typer.Exit(status)


@matcher_app.command(
    "regen",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Regenerate matcher generated artifacts. Wraps generated JSON and registry coverage scripts.",
)
def matcher_regen(
    ctx: typer.Context,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to update instead of /app.")] = None,
    what: Annotated[
        Literal["all", "json", "coverage"],
        typer.Option("--what", help="Generated artifacts to refresh/check."),
    ] = "all",
    check: Annotated[
        bool,
        typer.Option("--check", help="Check for drift without writing."),
    ] = False,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
) -> None:
    raw_args = _raw_args(ctx)
    if what == "all" and raw_args:
        raise typer.BadParameter("raw pass-through args are only supported with --what json or --what coverage")

    common_args = _tree_root_args(tree_root)
    mode_arg = "--check" if check else "--write"
    steps: list[tuple[str, list[str]]] = []
    if what in {"all", "json"}:
        steps.append((
            "generate_matcher_contract_json_from_toml_sources.py",
            [*common_args, mode_arg, *(raw_args if what == "json" else [])],
        ))
    if what in {"all", "coverage"}:
        steps.append((
            "generate_matcher_registry_coverage.py",
            [*common_args, mode_arg, *(raw_args if what == "coverage" else [])],
        ))

    failed = False
    for script_name, args in steps:
        status = _run_support_check(
            script_name,
            args,
            tree_root=tree_root,
            report_root=report_root,
            cwd=APP_DIR,
        )
        if status != 0:
            failed = True
            if not check:
                raise typer.Exit(status)
    raise typer.Exit(1 if failed else 0)


@matcher_app.command(
    "refresh-line-refs",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Refresh matcher rule inventory line refs. Wraps support_checks/refresh_matcher_rule_inventory_line_refs.py.",
)
def matcher_refresh_line_refs(
    ctx: typer.Context,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to update instead of /app.")] = None,
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Explicit alias for the default write mode; conflicts with --dry-run."),
    ] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show refreshed line refs without writing.")] = False,
    output_format: Annotated[
        Literal["text", "json"],
        typer.Option("--format", help="Report format."),
    ] = "text",
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
) -> None:
    if fix and dry_run:
        raise typer.BadParameter("--fix conflicts with --dry-run")
    paths = _paths(tree_root)
    args = [
        *_tree_root_args(tree_root),
        "--repo-root",
        str(paths.repo_root),
        "--format",
        output_format,
    ]
    if not dry_run:
        args.append("--write")
    args.extend(_raw_args(ctx))
    status = _run_support_check(
        "refresh_matcher_rule_inventory_line_refs.py",
        args,
        tree_root=tree_root,
        report_root=report_root,
        cwd=paths.repo_root,
    )
    raise typer.Exit(status)


@matcher_app.command(
    "gates",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def matcher_gates(
    ctx: typer.Context,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
) -> None:
    status = _run_support_check(
        "run_matcher_change_gates.py",
        _raw_args(ctx),
        report_root=report_root,
        cwd=APP_DIR,
    )
    raise typer.Exit(status)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
