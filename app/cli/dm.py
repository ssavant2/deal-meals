"""Deal Meals developer CLI."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tomllib
from typing import Annotated
import unicodedata

import typer

from support_checks.audit_matcher_contract_toml_sources import (
    contract_spec_by_name,
    load_contract_source,
    write_contract_source,
)
from support_checks.generate_matcher_contract_json_from_toml_sources import check_generated_contract_json
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


app = typer.Typer(help="Deal Meals developer tools.")
matcher_app = typer.Typer(help="Matcher rule-change workflows.")
matcher_add_app = typer.Typer(help="Generate matcher rule-change artifacts.")
matcher_app.add_typer(matcher_add_app, name="add")
app.add_typer(matcher_app, name="matcher")


@dataclass(frozen=True)
class MatcherPaths:
    tree_root: Path
    app_dir: Path
    repo_root: Path
    fixture_file: Path
    inventory_file: Path
    fixture_source_file: Path
    inventory_source_file: Path
    keyword_extra_parent_file: Path
    keyword_synonym_file: Path
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
        deep_sanity_file=app_dir / "support_checks" / "run_deep_matcher_sanity.py",
    )


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


def _split_csv(value: str, *, label: str, lowercase: bool = True) -> tuple[str, ...]:
    items = tuple(
        item.strip().lower() if lowercase else item.strip()
        for item in value.split(",")
        if item.strip()
    )
    if not items:
        raise typer.BadParameter(f"{label} must contain at least one value")
    duplicates = sorted({item for item in items if items.count(item) > 1})
    if duplicates:
        raise typer.BadParameter(f"{label} contains duplicates: {', '.join(duplicates)}")
    return items


def _titleish(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split())


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_array(values: tuple[str, ...] | list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


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
    if trim_existing:
        path.write_text(existing_text.rstrip() + "\n" + block, encoding="utf-8")
        return
    separator = "" if existing_text.endswith("\n\n") else "\n"
    path.write_text(existing_text + separator + block, encoding="utf-8")


def _existing_entry_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(re.findall(r'^entry_id = "([^"]+)"', path.read_text(encoding="utf-8"), flags=re.MULTILINE))


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
    dry_run: bool,
) -> str:
    lines = [
        "",
        f"# {policy_ref}: generated by dm matcher add keyword-extra-parent",
    ]
    for kid, offer_name in zip(kids, offer_names, strict=True):
        lines.extend([
            f"test({_toml_string(_titleish(canonical) + ' recipe matches ' + kid)},",
            f"     match({_toml_string(offer_name)}, {_toml_string(ingredient)}, {_toml_string(offer_category)}), {_toml_string(canonical)})",
        ])
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
    dry_run: bool,
) -> str:
    lines = [
        "",
        f"# {policy_ref}: generated by dm matcher add keyword-synonym",
    ]
    for variant in variants:
        ingredient = ingredient_override or variant
        lines.extend([
            f"test({_toml_string('Keyword synonym ' + variant + ' matches ' + canonical)},",
            f"     match({_toml_string(sanity_offer)}, {_toml_string(ingredient)}, {_toml_string(offer_category)}), {_toml_string(canonical)})",
        ])
    block = "\n".join(lines) + "\n"
    _append_text_block(paths.deep_sanity_file, block, dry_run=dry_run, trim_existing=True)
    return block


def _run(argv: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> int:
    print("+ " + " ".join(str(part) for part in argv), flush=True)
    return subprocess.run(argv, cwd=cwd, env=env, check=False).returncode


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
    env = _gate_env(paths, report_root, None)
    commands = [
        [sys.executable, str(SUPPORT_CHECKS_DIR / "promote_term_baseline.py")],
        [sys.executable, str(SUPPORT_CHECKS_DIR / "run_matcher_change_preflight.py")],
        [sys.executable, str(SUPPORT_CHECKS_DIR / "run_term_registry_contract_checks.py"), "--language", "sv"],
        [sys.executable, str(SUPPORT_CHECKS_DIR / "run_term_registry_add_term_checks.py"), "--language", "sv"],
        [sys.executable, str(SUPPORT_CHECKS_DIR / "run_term_registry_export_checks.py"), "--language", "sv"],
        [sys.executable, str(SUPPORT_CHECKS_DIR / "run_deep_matcher_sanity.py")],
    ]
    for argv in commands:
        status = _run(argv, cwd=APP_DIR, env=env)
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
    if change.sanity_preview:
        typer.echo(change.sanity_preview)
    typer.echo("Dry run only; no files written.")


def _run_preflight(paths: MatcherPaths, report_root: Path | None) -> int:
    argv = [sys.executable, str(SUPPORT_CHECKS_DIR / "run_matcher_change_preflight.py")]
    if paths.app_dir != APP_DIR:
        argv.extend(["--tree-root", str(paths.repo_root)])
    return _run(argv, cwd=APP_DIR, env=_gate_env(paths, report_root, None))


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

    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return

    if fixture_requested:
        gate_status = _run_track_b_change_plan(paths=paths, change=change, report_root=report_root)
    else:
        gate_status = _run_keyword_synonym_light_gates(paths=paths, report_root=report_root)
    raise typer.Exit(gate_status)


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
    env = os.environ.copy()
    env.setdefault("DEAL_MEALS_SUPPORT_REPORT_ROOT", "/tmp/deal-meals-support-checks-dm")
    if report_root is not None:
        env["DEAL_MEALS_SUPPORT_REPORT_ROOT"] = str(report_root)
    status = _run(
        [sys.executable, str(SUPPORT_CHECKS_DIR / "run_matcher_change_gates.py"), *ctx.args],
        cwd=APP_DIR,
        env=env,
    )
    raise typer.Exit(status)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
