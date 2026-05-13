"""Swedish add-a-term/export planning helpers.

The functions here keep the add-a-term workflow centered on registry TOML:
they do not edit matcher files or rebuild cache. They validate that explicit
coverage rows map to known Swedish matcher layers and summarize which runtime
exports a registry entry will affect.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
import json
from pathlib import Path
import re
from typing import Any
import unicodedata

from languages.term_registry.export_plan import ExportLayerSpec, build_registry_export_plan
from languages.term_registry.models import CheckIssue, RegistryEntry, RegistryExample

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
from .registry import DEFAULT_LOCAL_ENTRIES_DIR, load_registry_entries, local_registry_entries_dirs


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


LOCAL_TERMS_FILE_NAME = "local_user_terms.toml"

LOCAL_ALIAS_KINDS: dict[str, dict[str, str]] = {
    "offer-extra": {
        "source_family": OFFER_EXTRA_KEYWORD_SOURCE_FAMILY,
        "layer_role": OFFER_EXTRA_KEYWORD_LAYER_ROLE,
        "layer_policy": "offer_alias",
        "term_field": "offer_terms",
        "description": "product/offer word that should also match an existing ingredient",
    },
    "keyword-synonym": {
        "source_family": KEYWORD_SYNONYM_SOURCE_FAMILY,
        "layer_role": KEYWORD_SYNONYM_LAYER_ROLE,
        "layer_policy": "offer_alias",
        "term_field": "offer_terms",
        "description": "spelling/plural synonym normalized on both product and ingredient side",
    },
    "ingredient-parent": {
        "source_family": INGREDIENT_PARENT_SOURCE_FAMILY,
        "layer_role": INGREDIENT_PARENT_LAYER_ROLE,
        "layer_policy": "ingredient_alias",
        "term_field": "ingredient_terms",
        "description": "recipe/ingredient word that should roll up to an existing parent ingredient",
    },
}


def _normalized_term(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _entry_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")
    return slug or "term"


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_array(values: Iterable[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _coverage_keys(entries: Iterable[RegistryEntry]) -> set[tuple[str, str, str, str, str, str]]:
    keys: set[tuple[str, str, str, str, str, str]] = set()
    for entry in entries:
        raw_rows = (
            entry.language_payload.get("coverage")
            or entry.language_payload.get("legacy_coverage")
            or []
        )
        if not isinstance(raw_rows, list):
            continue
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            keys.add((
                str(row.get("language") or entry.language),
                str(row.get("market") or entry.market),
                str(row.get("source_family") or row.get("source_type") or ""),
                str(row.get("canonical") or entry.canonical),
                str(row.get("variant") or row.get("variant_text") or ""),
                str(row.get("layer_role") or row.get("variant_role") or ""),
            ))
    return keys


def _next_entry_id(*, canonical: str, variant: str, existing_entries: Iterable[RegistryEntry]) -> str:
    existing_ids = {entry.entry_id for entry in existing_entries}
    canonical_slug = _entry_slug(canonical)
    variant_slug = _entry_slug(variant)
    base = f"sv-se.alias.{canonical_slug}.{variant_slug}"
    if base not in existing_ids:
        return base
    index = 2
    while f"{base}_{index}" in existing_ids:
        index += 1
    return f"{base}_{index}"


def _entry_payload(
    *,
    entry_id: str,
    canonical: str,
    variant: str,
    kind: str,
    local_file: Path,
) -> tuple[RegistryEntry, dict[str, Any]]:
    spec = LOCAL_ALIAS_KINDS[kind]
    coverage = {
        "source_family": spec["source_family"],
        "canonical": canonical,
        "variant": variant,
        "layer_role": spec["layer_role"],
    }
    source_ref = f"local:{local_file}"
    term_field = spec["term_field"]
    field_values = {
        "ingredient_terms": (),
        "offer_terms": (),
        "route_terms": (),
        "final_match_terms": (),
    }
    field_values[term_field] = (canonical,)
    example = (
        RegistryExample(ingredient=canonical, offer_name=variant, expected=1)
        if kind != "ingredient-parent"
        else RegistryExample(ingredient=variant, offer_name=canonical, expected=1)
    )
    entry = RegistryEntry(
        entry_id=entry_id,
        language="sv",
        market="SE",
        canonical=canonical,
        status="active",
        variants=(variant,),
        ingredient_terms=field_values["ingredient_terms"],
        offer_terms=field_values["offer_terms"],
        route_terms=field_values["route_terms"],
        final_match_terms=field_values["final_match_terms"],
        source_refs=(source_ref,),
        layer_policy=(spec["layer_policy"],),
        positive_examples=(example,),
        notes=f"Local user alias added with add_term.py ({kind}).",
        language_payload={"coverage": [coverage]},
    )
    payload = {
        "entry_id": entry.entry_id,
        "language": entry.language,
        "market": entry.market,
        "canonical": entry.canonical,
        "status": entry.status,
        "variants": list(entry.variants),
        "ingredient_terms": list(entry.ingredient_terms),
        "offer_terms": list(entry.offer_terms),
        "route_terms": list(entry.route_terms),
        "final_match_terms": list(entry.final_match_terms),
        "source_refs": list(entry.source_refs),
        "layer_policy": list(entry.layer_policy),
        "notes": entry.notes,
        "coverage": [coverage],
        "positive_examples": [example.to_dict()],
    }
    return entry, payload


def _entry_toml(payload: dict[str, Any]) -> str:
    lines = [
        "[[entries]]",
        f"entry_id = {_toml_string(payload['entry_id'])}",
        f"language = {_toml_string(payload['language'])}",
        f"market = {_toml_string(payload['market'])}",
        f"canonical = {_toml_string(payload['canonical'])}",
        f"status = {_toml_string(payload['status'])}",
        f"variants = {_toml_array(payload['variants'])}",
    ]
    for key in ("ingredient_terms", "offer_terms", "route_terms", "final_match_terms"):
        if payload[key]:
            lines.append(f"{key} = {_toml_array(payload[key])}")
    lines.extend([
        f"source_refs = {_toml_array(payload['source_refs'])}",
        f"layer_policy = {_toml_array(payload['layer_policy'])}",
        f"notes = {_toml_string(payload['notes'])}",
        "",
    ])
    for row in payload["coverage"]:
        lines.extend([
            "[[entries.coverage]]",
            f"source_family = {_toml_string(row['source_family'])}",
            f"canonical = {_toml_string(row['canonical'])}",
            f"variant = {_toml_string(row['variant'])}",
            f"layer_role = {_toml_string(row['layer_role'])}",
            "",
        ])
    for example in payload["positive_examples"]:
        lines.extend([
            "[[entries.positive_examples]]",
            f"ingredient = {_toml_string(example['ingredient'])}",
            f"offer_name = {_toml_string(example['offer_name'])}",
            f"expected = {int(example['expected'])}",
        ])
    return "\n".join(lines).rstrip() + "\n"


def _append_toml_block(path: Path, block: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8").strip():
        existing = path.read_text(encoding="utf-8").rstrip()
        path.write_text(existing + "\n\n" + block, encoding="utf-8")
        return
    header = (
        "# Local user-added Swedish term registry entries.\n"
        "# This file is stored on the writable /app/data volume and survives image upgrades.\n"
        "# Restart the web container after editing so runtime matcher exports are reloaded.\n\n"
    )
    path.write_text(header + block, encoding="utf-8")


def _default_local_entries_dir() -> Path:
    dirs = local_registry_entries_dirs()
    return dirs[0] if dirs else DEFAULT_LOCAL_ENTRIES_DIR


def add_local_alias(
    *,
    canonical: str,
    variant: str,
    kind: str,
    entries_dir: Path | None = None,
    dry_run: bool = False,
) -> int:
    entries_dir = entries_dir or _default_local_entries_dir()
    canonical = _normalized_term(canonical)
    variant = _normalized_term(variant)
    if not canonical or not variant:
        print("ERROR: --canonical and --variant are required.")
        return 1
    if canonical == variant:
        print("ERROR: canonical and variant are identical; nothing useful would be added.")
        return 1
    if kind not in LOCAL_ALIAS_KINDS:
        print(f"ERROR: unknown kind {kind!r}. Choose one of: {', '.join(sorted(LOCAL_ALIAS_KINDS))}")
        return 1
    if re.search(r"\s", canonical) or re.search(r"\s", variant):
        print("ERROR: local simple aliases support one token only. Multi-word phrases need a matcher rule.")
        return 1

    local_file = entries_dir / LOCAL_TERMS_FILE_NAME
    existing_entries = load_registry_entries(include_local=True)
    local_dirs = {path.resolve() for path in local_registry_entries_dirs()}
    if entries_dir.resolve() not in local_dirs:
        existing_entries.extend(load_registry_entries(entries_dir=entries_dir, include_local=False))
    spec = LOCAL_ALIAS_KINDS[kind]
    coverage_key = (
        "sv",
        "SE",
        spec["source_family"],
        canonical,
        variant,
        spec["layer_role"],
    )
    if coverage_key in _coverage_keys(existing_entries):
        print("Nothing added: this exact coverage key already exists.")
        print(f"  {coverage_key}")
        return 0

    entry_id = _next_entry_id(
        canonical=canonical,
        variant=variant,
        existing_entries=existing_entries,
    )
    entry, payload = _entry_payload(
        entry_id=entry_id,
        canonical=canonical,
        variant=variant,
        kind=kind,
        local_file=local_file,
    )
    plan, issues = build_add_term_export_plan([*existing_entries, entry])
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        print("ERROR: the local term did not pass add-term validation:")
        for issue in errors[:10]:
            print(f"  - {issue.code}: {issue.message} ({issue.item_id})")
        return 1

    block = _entry_toml(payload)
    if dry_run:
        print(block)
        print("Dry run only; no file written.")
        return 0

    _append_toml_block(local_file, block)
    print(f"Added local term entry: {entry_id}")
    print(f"  file: {local_file}")
    print(f"  kind: {kind} ({spec['description']})")
    print(f"  coverage rows after add: {plan['summary']['coverage_row_count']}")
    print("\nNext steps:")
    print("  1. Restart the web container so matcher exports and versions reload.")
    print("  2. Refresh recipe suggestions/cache from the app.")
    return 0


def list_local_terms(*, entries_dir: Path | None = None) -> int:
    entries_dir = entries_dir or _default_local_entries_dir()
    entries = load_registry_entries(entries_dir=entries_dir, include_local=False)
    if not entries:
        print(f"No local terms found in {entries_dir}.")
        return 0
    for entry in entries:
        variants = ", ".join(entry.variants)
        policies = ", ".join(entry.layer_policy)
        print(f"{entry.entry_id}: {variants} -> {entry.canonical} ({policies})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage local Swedish term-registry aliases.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser(
        "add-local-alias",
        help="Add one local single-token alias under /app/data/term_registry/sv/entries.",
    )
    add_parser.add_argument("--canonical", required=True, help="Existing canonical ingredient keyword.")
    add_parser.add_argument("--variant", required=True, help="New product/ingredient word to map.")
    add_parser.add_argument(
        "--kind",
        choices=sorted(LOCAL_ALIAS_KINDS),
        default="offer-extra",
        help="Alias behavior. Default: offer-extra.",
    )
    add_parser.add_argument(
        "--entries-dir",
        type=Path,
        default=None,
        help="Writable local registry entries directory.",
    )
    add_parser.add_argument("--dry-run", action="store_true", help="Print the TOML entry without writing it.")

    list_parser = subparsers.add_parser("list-local", help="List local user-added terms.")
    list_parser.add_argument(
        "--entries-dir",
        type=Path,
        default=None,
        help="Writable local registry entries directory.",
    )

    args = parser.parse_args(argv)
    if args.command == "add-local-alias":
        return add_local_alias(
            canonical=args.canonical,
            variant=args.variant,
            kind=args.kind,
            entries_dir=args.entries_dir,
            dry_run=args.dry_run,
        )
    if args.command == "list-local":
        return list_local_terms(entries_dir=args.entries_dir)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
