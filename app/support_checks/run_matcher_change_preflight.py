#!/usr/bin/env python3
"""Pre-flight infrastructure checks for matcher rule changes."""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = APP_DIR.parent
sys.path.insert(0, str(APP_DIR))

from languages.sv.ingredient_matching.term_registry.add_term import (  # noqa: E402
    build_add_term_export_plan,
)
from languages.sv.ingredient_matching.term_registry.registry import load_registry_entries  # noqa: E402
from support_checks.generate_matcher_registry_coverage import (  # noqa: E402
    generate_coverage_files,
)
from support_checks.matcher_contracts import (  # noqa: E402
    _payload_from_source_toml,
    _source_toml,
    canonical_json,
    app_dir_for_tree_root,
    contract_spec_by_name,
    contract_paths,
    load_contract_source,
    load_fixture_contract,
    load_inventory_contract,
)
from support_checks.prefix_schema import allowed_prefixes, prefix_hint  # noqa: E402
from support_checks.run_matcher_layer_fixture_cases import (  # noqa: E402
    ALLOWED_SOURCE_REF_PREFIXES,
    _validate_fixture_payload,
    has_temporary_policy_ref,
    has_temporary_source_ref,
    source_ref_prefix_hint,
)
from support_checks.run_matcher_rule_inventory_checks import (  # noqa: E402
    validate_inventory,
)
from support_checks.run_term_registry_add_term_checks import (  # noqa: E402
    EXPECTED_VERIFIED_TERM_UNIQUE_COVERAGE_KEYS,
)
from support_checks.run_term_registry_contract_checks import (  # noqa: E402
    EXPECTED_VERIFIED_TERM_VARIANT_COUNT,
)
from support_checks.run_term_registry_guard_bridge_checks import (  # noqa: E402
    find_match_bridge_positive_fixture_misses,
)


DEFAULT_REGISTRY_ENTRIES_DIR = (
    APP_DIR / "languages" / "sv" / "ingredient_matching" / "term_registry" / "entries"
)
DEFAULT_BASELINE_FILE = (
    APP_DIR
    / "languages"
    / "sv"
    / "ingredient_matching"
    / "term_registry"
    / "baselines"
    / "verified_matcher_terms.json"
)
DEFAULT_SNAPSHOT_FILE = APP_DIR / "support_checks" / "baselines" / "known_infrastructure_issues.json"

ALLOWED_ADAPTER_REF_PREFIXES = allowed_prefixes("adapter_ref")
CoverageKey = tuple[str, str, str, str, str, str]
_SPACE_NORM_PRIVATE_NAMES = frozenset({"_SPACE_NORM_PATTERN", "_SPACE_NORM_LOOKUP"})
_KEYWORD_SYNONYM_FILE_NAME = "keyword_synonym.toml"


@dataclass(frozen=True)
class PreflightIssue:
    severity: str
    code: str
    message: str
    file: str
    item_id: str
    line: int | None = None
    details: dict[str, Any] | None = None

    @property
    def fingerprint(self) -> str:
        return "|".join((self.file, self.code, self.item_id))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["fingerprint"] = self.fingerprint
        if payload["details"] is None:
            payload["details"] = {}
        return payload


def _rel(path: Path, *, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _line_for_id(path: Path, item_id: str) -> int | None:
    needle = json.dumps(item_id, ensure_ascii=False)
    try:
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if needle in line:
                return index
    except OSError:
        return None
    return None


def _load_known_fingerprints(snapshot_file: Path) -> set[str]:
    if not snapshot_file.exists():
        return set()
    payload = json.loads(snapshot_file.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        entries = payload
    else:
        entries = payload.get("issues", []) if isinstance(payload, dict) else []
    fingerprints = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        fingerprint = entry.get("fingerprint")
        if fingerprint:
            fingerprints.add(str(fingerprint))
            continue
        file_name = str(entry.get("file") or "")
        code = str(entry.get("code") or "")
        item_id = str(entry.get("item_id") or "")
        if file_name and code and item_id:
            fingerprints.add("|".join((file_name, code, item_id)))
    return fingerprints


def _write_snapshot(snapshot_file: Path, issues: list[PreflightIssue]) -> None:
    snapshot_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "doctrine": "main should have an empty snapshot; entries are temporary tolerances only",
        "issues": [
            {
                "fingerprint": issue.fingerprint,
                "file": issue.file,
                "code": issue.code,
                "item_id": issue.item_id,
                "comment": "TODO: add justification and cleanup date before committing",
            }
            for issue in sorted(issues, key=lambda item: item.fingerprint)
        ],
    }
    snapshot_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _check_space_norm_private_usage(app_dir: Path, *, repo_root: Path) -> list[PreflightIssue]:
    root = app_dir / "languages" / "sv" / "ingredient_matching"
    issues: list[PreflightIssue] = []
    if not root.exists():
        return issues

    for path in sorted(root.rglob("*.py")):
        if path.name == "normalization.py":
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(PreflightIssue(
                "error",
                "space_norm_source_unreadable",
                f"Could not read source file: {exc}",
                _rel(path, repo_root=repo_root),
                path.name,
            ))
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            issues.append(PreflightIssue(
                "error",
                "space_norm_source_unparseable",
                f"Could not parse source file: {exc.msg}",
                _rel(path, repo_root=repo_root),
                path.name,
                line=exc.lineno,
            ))
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported = sorted(
                    alias.name
                    for alias in node.names
                    if alias.name in _SPACE_NORM_PRIVATE_NAMES
                )
                if imported:
                    issues.append(PreflightIssue(
                        "error",
                        "space_norm_private_import",
                        (
                            "Use _apply_space_normalizations() instead of importing compiled "
                            f"space-normalization internals: {', '.join(imported)}"
                        ),
                        _rel(path, repo_root=repo_root),
                        ",".join(imported),
                        line=node.lineno,
                    ))
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "sub"
                and isinstance(node.value, ast.Name)
                and node.value.id == "_SPACE_NORM_PATTERN"
            ):
                issues.append(PreflightIssue(
                    "error",
                    "space_norm_direct_pattern_sub",
                    "Use _apply_space_normalizations() instead of _SPACE_NORM_PATTERN.sub(...).",
                    _rel(path, repo_root=repo_root),
                    "_SPACE_NORM_PATTERN.sub",
                    line=node.lineno,
                ))
    return issues


def _literal_strings(node: ast.AST | None) -> set[str]:
    if node is None:
        return set()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        values: set[str] = set()
        for child in node.elts:
            values.update(_literal_strings(child))
        return values
    if isinstance(node, ast.Call) and node.args:
        return _literal_strings(node.args[0])
    return set()


def _module_constant_int(path: Path, name: str) -> int | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        target = None
        value = None
        if isinstance(node, ast.Assign):
            target = node.targets[0] if node.targets else None
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        if isinstance(target, ast.Name) and target.id == name:
            if isinstance(value, ast.Constant) and isinstance(value.value, int):
                return value.value
    return None


def _important_short_keywords_from_tree(app_dir: Path) -> tuple[set[str], list[PreflightIssue]]:
    root = app_dir / "languages" / "sv" / "ingredient_matching"
    keywords_file = root / "keywords.py"
    overlay_file = root / "runtime_rule_overlays.toml"
    issues: list[PreflightIssue] = []
    terms: set[str] = set()
    try:
        tree = ast.parse(keywords_file.read_text(encoding="utf-8"), filename=str(keywords_file))
    except (OSError, SyntaxError) as exc:
        issues.append(PreflightIssue(
            "error",
            "important_short_keywords_unreadable",
            f"could not read IMPORTANT_SHORT_KEYWORDS from keywords.py: {exc}",
            str(keywords_file),
            "IMPORTANT_SHORT_KEYWORDS",
        ))
        return terms, issues

    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "IMPORTANT_SHORT_KEYWORDS"
        ):
            terms.update(value.strip().lower() for value in _literal_strings(node.value) if value.strip())
            break

    if overlay_file.exists():
        try:
            payload = tomllib.loads(overlay_file.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            issues.append(PreflightIssue(
                "error",
                "runtime_overlay_unreadable",
                f"could not read runtime important-short updates: {exc}",
                str(overlay_file),
                "important_short_keywords",
            ))
            return terms, issues
        for entry in payload.get("keyword_set_updates", []):
            if not isinstance(entry, dict):
                continue
            if str(entry.get("status") or "active") != "active":
                continue
            if str(entry.get("surface") or "") != "important_short_keywords":
                continue
            action = str(entry.get("action") or "").lower()
            update_terms = {
                str(term).strip().lower()
                for term in entry.get("terms", [])
                if str(term).strip()
            }
            if action == "add":
                terms.update(update_terms)
            elif action == "remove":
                terms.difference_update(update_terms)
    return terms, issues


def _keyword_synonym_entries_from_text(text: str) -> dict[str, dict[str, Any]]:
    payload = tomllib.loads(text)
    entries: dict[str, dict[str, Any]] = {}
    for raw_entry in payload.get("entries", []):
        if not isinstance(raw_entry, dict):
            continue
        entry_id = str(raw_entry.get("entry_id") or "").strip()
        if not entry_id:
            canonical = str(raw_entry.get("canonical") or "canonical").strip()
            variants = raw_entry.get("variants") or []
            first_variant = str(variants[0]) if variants else "variant"
            entry_id = f"{canonical}:{first_variant}"
        entries[entry_id] = {
            "entry_id": entry_id,
            "canonical": str(raw_entry.get("canonical") or "").strip(),
            "status": str(raw_entry.get("status") or "active"),
            "variants": tuple(
                str(variant).strip().lower()
                for variant in raw_entry.get("variants", [])
                if str(variant).strip()
            ),
        }
    return entries


def _git_head_file_text(repo_root: Path, rel_path: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{rel_path}"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _changed_keyword_synonym_entries(
    keyword_synonym_file: Path,
    *,
    repo_root: Path,
) -> tuple[dict[str, dict[str, Any]], list[PreflightIssue]]:
    if not keyword_synonym_file.exists():
        return {}, []
    file_name = _rel(keyword_synonym_file, repo_root=repo_root)
    try:
        current_entries = _keyword_synonym_entries_from_text(
            keyword_synonym_file.read_text(encoding="utf-8")
        )
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {}, [PreflightIssue(
            "error",
            "keyword_synonym_toml_unreadable",
            f"could not read keyword_synonym.toml: {exc}",
            file_name,
            _KEYWORD_SYNONYM_FILE_NAME,
        )]

    old_text = _git_head_file_text(repo_root, file_name)
    if old_text is None:
        return {}, []
    try:
        old_entries = _keyword_synonym_entries_from_text(old_text)
    except tomllib.TOMLDecodeError:
        return {}, []

    changed: dict[str, dict[str, Any]] = {}
    for entry_id, entry in current_entries.items():
        if entry["status"] != "active":
            continue
        previous = old_entries.get(entry_id)
        if previous is None or previous.get("status") != "active":
            changed[entry_id] = {**entry, "new_variants": entry["variants"]}
            continue
        old_variants = set(previous.get("variants", ()))
        new_variants = tuple(variant for variant in entry["variants"] if variant not in old_variants)
        if new_variants:
            changed[entry_id] = {**entry, "new_variants": new_variants}
    return changed, []


def _check_short_keyword_synonym_variants(
    *,
    app_dir: Path,
    registry_entries_dir: Path,
    repo_root: Path,
) -> list[PreflightIssue]:
    keyword_synonym_file = registry_entries_dir / _KEYWORD_SYNONYM_FILE_NAME
    changed_entries, issues = _changed_keyword_synonym_entries(
        keyword_synonym_file,
        repo_root=repo_root,
    )
    if not changed_entries:
        return issues

    min_length = _module_constant_int(
        app_dir / "languages" / "sv" / "ingredient_matching" / "extraction_patterns.py",
        "MIN_KEYWORD_LENGTH_STRICT",
    )
    if min_length is None:
        return [*issues, PreflightIssue(
            "error",
            "strict_keyword_length_unreadable",
            "could not read MIN_KEYWORD_LENGTH_STRICT from extraction_patterns.py",
            _rel(app_dir / "languages" / "sv" / "ingredient_matching" / "extraction_patterns.py", repo_root=repo_root),
            "MIN_KEYWORD_LENGTH_STRICT",
        )]

    important_short, important_issues = _important_short_keywords_from_tree(app_dir)
    issues.extend(important_issues)
    if important_issues:
        return issues

    file_name = _rel(keyword_synonym_file, repo_root=repo_root)
    for entry_id, entry in sorted(changed_entries.items()):
        for variant in entry.get("new_variants", ()):
            if re.search(r"\s", variant):
                continue
            if len(variant) >= min_length or variant in important_short:
                continue
            issues.append(PreflightIssue(
                "error",
                "keyword_synonym_short_variant_missing_important_short",
                (
                    f"new keyword-synonym variant {variant!r} is shorter than "
                    f"MIN_KEYWORD_LENGTH_STRICT={min_length} and will be dropped before "
                    "synonym mapping unless it is also an important-short keyword"
                ),
                file_name,
                entry_id,
                _line_for_id(keyword_synonym_file, entry_id),
                {
                    "variant": variant,
                    "canonical": entry.get("canonical", ""),
                    "min_length": min_length,
                    "fix": (
                        f"./bin/dm matcher add important-short-keyword --terms {variant} "
                        "--reason \"<why this short synonym source must extract>\""
                    ),
                },
            ))
    return issues


def _fixture_expected_canonicals(payload: dict[str, Any]) -> list[str]:
    canonicals = []
    for item in payload.get("expected_matches") or []:
        if isinstance(item, dict) and item.get("canonical"):
            canonicals.append(str(item["canonical"]))
    return sorted(set(canonicals))


def _fixture_audit_canonicals(payload: dict[str, Any]) -> list[str]:
    canonicals = _fixture_expected_canonicals(payload)
    allowed = payload.get("allowed_additional_matches") or {}
    if isinstance(allowed, dict):
        for key in ("allowed_canonicals", "forbidden_canonicals"):
            canonicals.extend(str(value) for value in allowed.get(key, []) if value)
    return sorted(set(canonicals))


def _check_fixtures(path: Path, fixtures: list[dict[str, Any]], *, repo_root: Path) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    file_name = _rel(path, repo_root=repo_root)
    seen_ids: set[str] = set()
    for payload in fixtures:
        item_id = str(payload.get("id") or "<missing-id>")
        line = _line_for_id(path, item_id)
        if item_id in seen_ids:
            issues.append(PreflightIssue(
                "error",
                "fixture_duplicate_id",
                f"fixture id is duplicated: {item_id}",
                file_name,
                item_id,
                line,
            ))
        seen_ids.add(item_id)
        try:
            _validate_fixture_payload(payload)
        except ValueError as exc:
            issues.append(PreflightIssue(
                "error",
                "fixture_schema_invalid",
                str(exc),
                file_name,
                item_id,
                line,
            ))
        source_ref = payload.get("source_ref")
        if isinstance(source_ref, str):
            if not source_ref.startswith(ALLOWED_SOURCE_REF_PREFIXES):
                issues.append(PreflightIssue(
                    "error",
                    "fixture_source_ref_unknown_prefix",
                    f"source_ref has unknown prefix: {source_ref}. {source_ref_prefix_hint()}",
                    file_name,
                    item_id,
                    line,
                ))
            if has_temporary_source_ref(source_ref):
                issues.append(PreflightIssue(
                    "error",
                    "fixture_source_ref_temporary",
                    f"source_ref must be stable: {source_ref}",
                    file_name,
                    item_id,
                    line,
                ))
        policy_ref = payload.get("policy_ref")
        if isinstance(policy_ref, str) and has_temporary_policy_ref(policy_ref):
            issues.append(PreflightIssue(
                "error",
                "fixture_policy_ref_temporary",
                f"policy_ref must be stable: {policy_ref}",
                file_name,
                item_id,
                line,
            ))
        if payload.get("expected") == 1 and not _fixture_expected_canonicals(payload):
            issues.append(PreflightIssue(
                "error",
                "fixture_positive_missing_expected_matches",
                (
                    "fixture has expected=1 but no top-level expected_matches.canonical field; "
                    "registry coverage will fail to match"
                ),
                file_name,
                item_id,
                line,
                {"fix": "Add expected_matches with ingredient_index and canonical at fixture top level."},
            ))
    return issues


def _check_inventory(
    path: Path,
    inventory: list[dict[str, Any]],
    fixtures: list[dict[str, Any]],
    *,
    repo_root: Path,
) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    file_name = _rel(path, repo_root=repo_root)
    report = validate_inventory(inventory, fixtures, repo_root=repo_root)
    for failure in report["failures"]:
        item_id = str(failure).split(":", 1)[0] or "<unknown>"
        issues.append(PreflightIssue(
            "error",
            "inventory_contract_invalid",
            str(failure),
            file_name,
            item_id,
            _line_for_id(path, item_id),
        ))

    for entry in inventory:
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("id") or "<missing-id>")
        line = _line_for_id(path, item_id)
        adapter_refs = []
        adapter_ref = entry.get("adapter_ref")
        if isinstance(adapter_ref, str):
            adapter_refs.append(adapter_ref)
        if isinstance(entry.get("adapter_refs"), list):
            adapter_refs.extend(ref for ref in entry["adapter_refs"] if isinstance(ref, str))
        for ref in adapter_refs:
            if not ref.startswith(ALLOWED_ADAPTER_REF_PREFIXES):
                issues.append(PreflightIssue(
                    "error",
                    "inventory_adapter_ref_unknown_prefix",
                    (
                        f"adapter_ref has unknown prefix: {ref}. "
                        f"{prefix_hint('adapter_ref')}"
                    ),
                    file_name,
                    item_id,
                    line,
                ))
    return issues


def _raw_coverage_rows(entry: Any) -> list[Any]:
    rows = (
        entry.language_payload.get("coverage")
        or entry.language_payload.get("legacy_coverage")
        or []
    )
    if isinstance(rows, list):
        return rows
    return [rows]


def _coverage_key_from_row(entry: Any, raw_row: dict[str, Any]) -> CoverageKey | None:
    source_family = str(raw_row.get("source_family") or raw_row.get("source_type") or "").strip()
    canonical = str(raw_row.get("canonical") or raw_row.get("expected_family") or entry.canonical).strip()
    variant = str(raw_row.get("variant") or raw_row.get("variant_text") or "").strip()
    layer_role = str(raw_row.get("layer_role") or raw_row.get("variant_role") or "").strip()
    if not all((source_family, canonical, variant, layer_role)):
        return None
    return (
        str(raw_row.get("language") or entry.language).strip(),
        str(raw_row.get("market") or entry.market).strip(),
        source_family,
        canonical,
        variant,
        layer_role,
    )


def _coverage_key_to_dict(key: CoverageKey) -> dict[str, str]:
    language, market, source_family, canonical, variant, layer_role = key
    return {
        "language": language,
        "market": market,
        "source_family": source_family,
        "canonical": canonical,
        "variant": variant,
        "layer_role": layer_role,
    }


def _coverage_by_source_ref(entries_dir: Path) -> tuple[dict[str, set[CoverageKey]], list[PreflightIssue]]:
    issues: list[PreflightIssue] = []
    try:
        entries = load_registry_entries(entries_dir=entries_dir, include_local=False)
    except Exception as exc:  # noqa: BLE001 - preflight should report all context it can.
        return set(), [PreflightIssue(
            "error",
            "registry_entries_load_failed",
            f"could not load registry TOML entries: {exc}",
            str(entries_dir),
            str(entries_dir),
        )]

    payload, plan_issues = build_add_term_export_plan(entries=entries)
    for issue in plan_issues:
        if issue.severity == "error":
            issues.append(PreflightIssue(
                "error",
                f"registry_{issue.code}",
                issue.message,
                "term_registry/entries",
                issue.item_id or issue.code,
                details=issue.details,
            ))

    coverage_by_ref: dict[str, set[CoverageKey]] = {}
    for entry in entries:
        if entry.status != "active":
            continue
        coverage_keys = {
            key
            for raw_row in _raw_coverage_rows(entry)
            if isinstance(raw_row, dict)
            for key in [_coverage_key_from_row(entry, raw_row)]
            if key is not None
        }
        if not coverage_keys:
            continue
        for source_ref in entry.source_refs:
            coverage_by_ref.setdefault(source_ref, set()).update(coverage_keys)
    return coverage_by_ref, issues


def _fixture_coverage_key(payload: dict[str, Any]) -> CoverageKey:
    item_id = str(payload.get("id") or "<missing-id>")
    offer = payload.get("offer") or {}
    expected = int(payload.get("expected") or 0)
    canonical = ", ".join(_fixture_audit_canonicals(payload)) or str(payload.get("policy_ref") or "")
    return (
        "sv",
        "SE",
        "matcher_regression_case",
        canonical,
        f"{item_id}: {offer.get('name', '')}",
        "positive_regression" if expected else "negative_regression",
    )


def _inventory_coverage_key(entry: dict[str, Any]) -> CoverageKey:
    item_id = str(entry.get("id") or "<missing-id>")
    canonical = str(entry.get("canonical") or item_id)
    return (
        "sv",
        "SE",
        "matcher_rule_inventory",
        canonical,
        canonical,
        str(entry.get("kind") or "inventory_rule"),
    )


def _check_source_coverage(
    *,
    fixture_file: Path,
    inventory_file: Path,
    registry_entries_dir: Path,
    fixtures: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    repo_root: Path,
) -> list[PreflightIssue]:
    coverage_by_ref, issues = _coverage_by_source_ref(registry_entries_dir)
    fixture_file_name = _rel(fixture_file, repo_root=repo_root)
    inventory_file_name = _rel(inventory_file, repo_root=repo_root)
    for payload in fixtures:
        item_id = str(payload.get("id") or "<missing-id>")
        ref = f"fixture:matcher_regression_cases:{item_id}"
        expected_key = _fixture_coverage_key(payload)
        available_keys = coverage_by_ref.get(ref, set())
        if expected_key not in available_keys:
            issues.append(PreflightIssue(
                "error",
                "fixture_missing_registry_coverage",
                f"fixture is missing exact registry coverage for source_ref: {ref}",
                fixture_file_name,
                item_id,
                _line_for_id(fixture_file, item_id),
                {
                    "expected_coverage_key": _coverage_key_to_dict(expected_key),
                    "available_coverage_keys": [
                        _coverage_key_to_dict(key)
                        for key in sorted(available_keys)
                    ],
                },
            ))
    for entry in inventory:
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("id") or "<missing-id>")
        ref = f"inventory:matcher_rule_inventory:{item_id}"
        expected_key = _inventory_coverage_key(entry)
        available_keys = coverage_by_ref.get(ref, set())
        if expected_key not in available_keys:
            issues.append(PreflightIssue(
                "error",
                "inventory_missing_registry_coverage",
                f"inventory entry is missing exact registry coverage for source_ref: {ref}",
                inventory_file_name,
                item_id,
                _line_for_id(inventory_file, item_id),
                {
                    "expected_coverage_key": _coverage_key_to_dict(expected_key),
                    "available_coverage_keys": [
                        _coverage_key_to_dict(key)
                        for key in sorted(available_keys)
                    ],
                },
            ))
    return issues


def _check_generated_coverage(
    *,
    tree_root: Path | None,
    fixture_file: Path,
    inventory_file: Path,
    registry_entries_dir: Path,
    repo_root: Path,
) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    for generated_file in generate_coverage_files(
        tree_root=tree_root,
        fixture_file=fixture_file,
        inventory_file=inventory_file,
        entries_dir=registry_entries_dir,
    ):
        if not generated_file.changed:
            continue
        issues.append(PreflightIssue(
            "error",
            "generated_coverage_stale",
            (
                "generated registry coverage TOML is stale; run "
                "python support_checks/generate_matcher_registry_coverage.py --write"
            ),
            _rel(generated_file.path, repo_root=repo_root),
            generated_file.path.name,
            details={
                "generated_entry_count": generated_file.generated_entry_count,
                "manual_block_count": generated_file.manual_block_count,
            },
        ))
    return issues


def _check_contract_sources(
    *,
    tree_root: Path | None,
    fixture_file: Path,
    inventory_file: Path,
    repo_root: Path,
) -> list[PreflightIssue]:
    paths = contract_paths(tree_root)
    if fixture_file.resolve() != paths.fixture_file.resolve() or inventory_file.resolve() != paths.inventory_file.resolve():
        return []

    issues: list[PreflightIssue] = []
    for contract in ("matcher_regression_cases", "matcher_rule_inventory"):
        try:
            spec = contract_spec_by_name(contract, tree_root=tree_root)
            payload = load_contract_source(spec)
            emitted_text = _source_toml(spec, payload)
            round_trip_payload = _payload_from_source_toml(spec, emitted_text)
        except Exception as exc:  # noqa: BLE001
            issues.append(PreflightIssue(
                "error",
                "matcher_contract_toml_source_check_failed",
                f"could not parse matcher contract TOML source: {exc}",
                _rel(paths.source_dir, repo_root=repo_root),
                contract,
            ))
            continue
        semantic_equal = payload == round_trip_payload
        canonical_byte_equal = canonical_json(payload) == canonical_json(round_trip_payload)
        canonical_source_equal = spec.source_toml_path.read_text(encoding="utf-8") == emitted_text
        if semantic_equal and canonical_byte_equal and canonical_source_equal:
            continue
        issues.append(PreflightIssue(
            "error",
            "matcher_contract_toml_source_drift",
            (
                "matcher contract TOML source is not canonical; "
                "run `./bin/dm matcher regen --what contracts` before gates"
            ),
            _rel(spec.source_toml_path, repo_root=repo_root),
            contract,
            details={
                "semantic_equal": semantic_equal,
                "canonical_byte_equal": canonical_byte_equal,
                "canonical_source_equal": canonical_source_equal,
            },
        ))
    return issues


def _check_match_bridge_positive_fixture_hits(
    fixture_file: Path,
    fixtures: list[dict[str, Any]],
    *,
    repo_root: Path,
) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    fixture_by_id = {
        str(item.get("id") or ""): item
        for item in fixtures
        if isinstance(item, dict)
    }
    file_name = _rel(fixture_file, repo_root=repo_root)
    for miss in find_match_bridge_positive_fixture_misses(fixture_by_id):
        bridge_id = str(miss["bridge_id"])
        fixture_ref = str(miss["fixture_ref"])
        issues.append(PreflightIssue(
            "error",
            "match_bridge_positive_fixture_miss",
            (
                "match bridge helper did not hit its positive fixture; adjust the "
                "bridge ingredient/offer patterns or the fixture text before running full gates"
            ),
            file_name,
            f"{bridge_id}:{fixture_ref}",
            _line_for_id(fixture_file, fixture_ref),
            {
                "bridge_id": bridge_id,
                "fixture_ref": fixture_ref,
                "hit_ids": miss["hit_ids"],
            },
        ))
    return issues


def _check_expected_counts(baseline_file: Path, registry_entries_dir: Path, *, repo_root: Path) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    file_name = _rel(baseline_file, repo_root=repo_root)
    try:
        baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [PreflightIssue(
            "error",
            "verified_terms_baseline_load_failed",
            f"could not load verified-term baseline: {exc}",
            file_name,
            str(baseline_file),
        )]
    variants = baseline.get("variants") or []
    variant_count = len(variants) if isinstance(variants, list) else 0
    if variant_count != EXPECTED_VERIFIED_TERM_VARIANT_COUNT:
        issues.append(PreflightIssue(
            "error",
            "expected_verified_term_variant_count_stale",
            "EXPECTED_VERIFIED_TERM_VARIANT_COUNT does not match baseline variants",
            "app/support_checks/run_term_registry_contract_checks.py",
            "EXPECTED_VERIFIED_TERM_VARIANT_COUNT",
            details={"expected_constant": EXPECTED_VERIFIED_TERM_VARIANT_COUNT, "actual": variant_count},
        ))

    try:
        entries = load_registry_entries(entries_dir=registry_entries_dir, include_local=False)
        payload, _ = build_add_term_export_plan(entries=entries)
        unique_coverage_key_count = int(payload["summary"]["unique_coverage_key_count"])
    except Exception as exc:  # noqa: BLE001
        issues.append(PreflightIssue(
            "error",
            "registry_coverage_count_failed",
            f"could not count registry coverage keys: {exc}",
            str(registry_entries_dir),
            str(registry_entries_dir),
        ))
    else:
        if unique_coverage_key_count != EXPECTED_VERIFIED_TERM_UNIQUE_COVERAGE_KEYS:
            issues.append(PreflightIssue(
                "error",
                "expected_verified_term_unique_coverage_keys_stale",
                "EXPECTED_VERIFIED_TERM_UNIQUE_COVERAGE_KEYS does not match live registry coverage",
                "app/support_checks/run_term_registry_add_term_checks.py",
                "EXPECTED_VERIFIED_TERM_UNIQUE_COVERAGE_KEYS",
                details={
                    "expected_constant": EXPECTED_VERIFIED_TERM_UNIQUE_COVERAGE_KEYS,
                    "actual": unique_coverage_key_count,
                },
            ))
    return issues


def run_preflight(
    *,
    tree_root: Path | None = None,
    fixture_file: Path | None = None,
    inventory_file: Path | None = None,
    registry_entries_dir: Path | None = None,
    baseline_file: Path | None = None,
    snapshot_file: Path | None = None,
) -> dict[str, Any]:
    paths = contract_paths(tree_root)
    app_dir = paths.app_dir
    repo_root = paths.repo_root
    fixture_file = fixture_file or paths.fixture_file
    inventory_file = inventory_file or paths.inventory_file
    registry_entries_dir = (
        registry_entries_dir
        or app_dir / "languages" / "sv" / "ingredient_matching" / "term_registry" / "entries"
    )
    baseline_file = (
        baseline_file
        or app_dir / "languages" / "sv" / "ingredient_matching" / "term_registry" / "baselines" / "verified_matcher_terms.json"
    )
    snapshot_file = snapshot_file or app_dir / "support_checks" / "baselines" / "known_infrastructure_issues.json"

    fixtures = load_fixture_contract(fixture_file)
    inventory = load_inventory_contract(inventory_file)
    issues = []
    issues.extend(_check_space_norm_private_usage(app_dir, repo_root=repo_root))
    issues.extend(_check_short_keyword_synonym_variants(
        app_dir=app_dir,
        registry_entries_dir=registry_entries_dir,
        repo_root=repo_root,
    ))
    issues.extend(_check_fixtures(fixture_file, fixtures, repo_root=repo_root))
    issues.extend(_check_inventory(inventory_file, inventory, fixtures, repo_root=repo_root))
    issues.extend(_check_source_coverage(
        fixture_file=fixture_file,
        inventory_file=inventory_file,
        registry_entries_dir=registry_entries_dir,
        fixtures=fixtures,
        inventory=inventory,
        repo_root=repo_root,
    ))
    issues.extend(_check_generated_coverage(
        tree_root=tree_root,
        fixture_file=fixture_file,
        inventory_file=inventory_file,
        registry_entries_dir=registry_entries_dir,
        repo_root=repo_root,
    ))
    issues.extend(_check_contract_sources(
        tree_root=tree_root,
        fixture_file=fixture_file,
        inventory_file=inventory_file,
        repo_root=repo_root,
    ))
    # Promote-owned EXPECTED_* constants describe the live checkout. Synthetic
    # tree-root tests intentionally mutate copied registries without promoting.
    if app_dir.resolve() == APP_DIR.resolve():
        issues.extend(_check_match_bridge_positive_fixture_hits(
            fixture_file,
            fixtures,
            repo_root=repo_root,
        ))
        issues.extend(_check_expected_counts(baseline_file, registry_entries_dir, repo_root=repo_root))

    known = _load_known_fingerprints(snapshot_file)
    new_issues = [issue for issue in issues if issue.fingerprint not in known]
    known_issues = [issue for issue in issues if issue.fingerprint in known]
    fixed_fingerprints = sorted(known - {issue.fingerprint for issue in issues})
    return {
        "summary": {
            "passed": not new_issues,
            "issue_count": len(issues),
            "new_issue_count": len(new_issues),
            "known_issue_count": len(known_issues),
            "fixed_known_issue_count": len(fixed_fingerprints),
            "snapshot_file": str(snapshot_file),
        },
        "new_issues": [issue.to_dict() for issue in sorted(new_issues, key=lambda item: item.fingerprint)],
        "known_issues": [issue.to_dict() for issue in sorted(known_issues, key=lambda item: item.fingerprint)],
        "fixed_known_fingerprints": fixed_fingerprints,
    }


def _format_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "Matcher change pre-flight",
        (
            f"NEW={summary['new_issue_count']} "
            f"KNOWN={summary['known_issue_count']} "
            f"FIXED={summary['fixed_known_issue_count']}"
        ),
    ]
    if report["new_issues"]:
        lines.append("")
        lines.append("# NEW infrastructure issues")
        for issue in report["new_issues"]:
            location = issue["file"]
            if issue.get("line"):
                location += f":{issue['line']}"
            lines.append(f"- [{issue['code']}] {location} {issue['item_id']}: {issue['message']}")
    if report["known_issues"]:
        lines.append("")
        lines.append("# Tolerated pre-existing issues")
        for issue in report["known_issues"]:
            lines.append(f"- [{issue['code']}] {issue['file']} {issue['item_id']}: {issue['message']}")
    if report["fixed_known_fingerprints"]:
        lines.append("")
        lines.append("# Fixed known issues")
        for fingerprint in report["fixed_known_fingerprints"]:
            lines.append(f"- {fingerprint}")
    if summary["passed"]:
        lines.append("")
        lines.append("Pre-flight passed.")
    else:
        lines.append("")
        lines.append("Pre-flight failed. Fix NEW issues before running the full matcher gates.")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree-root", type=Path, default=None)
    parser.add_argument("--fixture-file", type=Path, default=None)
    parser.add_argument("--inventory-file", type=Path, default=None)
    parser.add_argument("--registry-entries-dir", type=Path, default=None)
    parser.add_argument("--baseline-file", type=Path, default=None)
    parser.add_argument("--snapshot-file", type=Path, default=None)
    parser.add_argument("--refresh-snapshot", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_preflight(
        tree_root=args.tree_root,
        fixture_file=args.fixture_file,
        inventory_file=args.inventory_file,
        registry_entries_dir=args.registry_entries_dir,
        baseline_file=args.baseline_file,
        snapshot_file=args.snapshot_file,
    )
    if args.refresh_snapshot:
        issues = [
            PreflightIssue(
                severity=str(item["severity"]),
                code=str(item["code"]),
                message=str(item["message"]),
                file=str(item["file"]),
                item_id=str(item["item_id"]),
                line=item.get("line"),
                details=item.get("details"),
            )
            for item in [*report["new_issues"], *report["known_issues"]]
        ]
        snapshot_file = args.snapshot_file or (
            app_dir_for_tree_root(args.tree_root) / "support_checks" / "baselines" / "known_infrastructure_issues.json"
        )
        _write_snapshot(snapshot_file, issues)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_format_report(report))
    return 0 if report["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
