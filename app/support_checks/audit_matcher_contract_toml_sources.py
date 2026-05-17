#!/usr/bin/env python3
"""Audit TOML source schema and generated JSON for matcher contracts."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date
import difflib
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import tomllib
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = (
    APP_DIR.parent
    if APP_DIR.parent != Path(APP_DIR.anchor) and (APP_DIR.parent / "docs").is_dir()
    else APP_DIR
)
sys.path.insert(0, str(APP_DIR))

from support_checks.matcher_contracts import (  # noqa: E402
    contract_paths,
    load_fixture_contract,
    load_inventory_contract,
)


DEFAULT_OUTPUT_DIR = Path("/tmp/deal-meals-matcher-contract-sources")
REPORTS_DIR = APP_DIR / "support_checks" / "reports"
DEFAULT_REPORT_OUTPUT = REPORTS_DIR / "MATCHER_CONTRACT_TOML_SOURCE_AUDIT.md"
DEFAULT_JSON_REPORT_OUTPUT = REPORTS_DIR / "MATCHER_CONTRACT_TOML_SOURCE_AUDIT.json"
SCHEMA_README = APP_DIR / "languages" / "sv" / "matcher_contracts" / "sources" / "README.md"


@dataclass(frozen=True)
class ContractSpec:
    contract: str
    table_name: str
    repo_root: Path
    source_json_path: Path
    source_toml_path: Path


@dataclass(frozen=True)
class ContractAuditResult:
    contract: str
    source_json_path: str
    source_toml_path: str
    row_count: int
    source_json_sha256: str
    source_toml_bytes: int
    semantic_equal: bool
    canonical_byte_equal: bool
    canonical_diff_line_count: int
    canonical_diff_preview: list[str]


def source_dir_for_tree_root(tree_root: Path | None = None) -> Path:
    return contract_paths(tree_root).app_dir / "languages" / "sv" / "matcher_contracts" / "sources"


def contract_specs(
    tree_root: Path | None = None,
    *,
    source_dir: Path | None = None,
) -> tuple[ContractSpec, ...]:
    paths = contract_paths(tree_root)
    source_root = source_dir or source_dir_for_tree_root(tree_root)
    return (
        ContractSpec(
            contract="matcher_regression_cases",
            table_name="fixtures",
            repo_root=paths.repo_root,
            source_json_path=paths.fixture_file,
            source_toml_path=source_root / "matcher_regression_cases.toml",
        ),
        ContractSpec(
            contract="matcher_rule_inventory",
            table_name="inventory",
            repo_root=paths.repo_root,
            source_json_path=paths.inventory_file,
            source_toml_path=source_root / "matcher_rule_inventory.toml",
        ),
    )


CONTRACT_SPECS = contract_specs()


def contract_spec_by_name(
    contract: str,
    *,
    tree_root: Path | None = None,
    source_dir: Path | None = None,
) -> ContractSpec:
    for spec in contract_specs(tree_root, source_dir=source_dir):
        if spec.contract == contract:
            return spec
    raise ValueError(f"unknown contract: {contract}")


def _repo_rel(path: Path, *, repo_root: Path = REPO_DIR) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _toml_key(key: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return json.dumps(key, ensure_ascii=False)


def _toml_path(parts: tuple[str, ...]) -> str:
    return ".".join(_toml_key(part) for part in parts)


def _toml_scalar(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    raise TypeError(f"unsupported TOML scalar type: {type(value).__name__}")


def _toml_array(values: list[Any]) -> str:
    if not all(not isinstance(value, (dict, list)) for value in values):
        raise TypeError("TOML inline arrays only support scalar values in this audit schema")
    return "[" + ", ".join(_toml_scalar(value) for value in values) + "]"


def _is_table_array(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, dict) for item in value)


def _emit_mapping(lines: list[str], mapping: dict[str, Any], table_path: tuple[str, ...]) -> None:
    scalar_items: list[tuple[str, Any]] = []
    dict_items: list[tuple[str, dict[str, Any]]] = []
    table_array_items: list[tuple[str, list[dict[str, Any]]]] = []

    for key, value in mapping.items():
        if isinstance(value, dict):
            dict_items.append((key, value))
        elif _is_table_array(value):
            table_array_items.append((key, value))
        else:
            scalar_items.append((key, value))

    for key, value in scalar_items:
        if isinstance(value, list):
            lines.append(f"{_toml_key(key)} = {_toml_array(value)}")
        else:
            lines.append(f"{_toml_key(key)} = {_toml_scalar(value)}")

    for key, value in dict_items:
        lines.append("")
        lines.append(f"[{_toml_path((*table_path, key))}]")
        _emit_mapping(lines, value, (*table_path, key))

    for key, values in table_array_items:
        for item in values:
            lines.append("")
            lines.append(f"[[{_toml_path((*table_path, key))}]]")
            _emit_mapping(lines, item, (*table_path, key))


def _contract_payload(spec: ContractSpec) -> list[dict[str, Any]]:
    if spec.contract == "matcher_regression_cases":
        return load_fixture_contract(spec.source_json_path)
    if spec.contract == "matcher_rule_inventory":
        return load_inventory_contract(spec.source_json_path)
    raise ValueError(f"unknown contract: {spec.contract}")


def _source_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _source_toml(spec: ContractSpec, payload: list[dict[str, Any]]) -> str:
    lines = [
        "# AUTHORITATIVE TOML SOURCE - JSON IS GENERATED.",
        "# Generated by support_checks/audit_matcher_contract_toml_sources.py.",
        "# Edit this source, then regenerate matcher contract JSON from TOML.",
        "schema_version = 1",
        f"contract = {_toml_scalar(spec.contract)}",
        f"source_json_path = {_toml_scalar(_repo_rel(spec.source_json_path, repo_root=spec.repo_root))}",
    ]
    for row in payload:
        lines.append("")
        lines.append(f"[[{_toml_key(spec.table_name)}]]")
        _emit_mapping(lines, row, (spec.table_name,))
    return "\n".join(lines).rstrip() + "\n"


def _payload_from_source_toml(spec: ContractSpec, toml_text: str) -> list[dict[str, Any]]:
    parsed = tomllib.loads(toml_text)
    payload = parsed.get(spec.table_name)
    if not isinstance(payload, list):
        raise ValueError(f"{spec.source_toml_path.name} must contain [[{spec.table_name}]]")
    if not all(isinstance(row, dict) for row in payload):
        raise ValueError(f"{spec.source_toml_path.name} rows must be TOML tables")
    return payload


def load_contract_source(spec: ContractSpec) -> list[dict[str, Any]]:
    return _payload_from_source_toml(spec, spec.source_toml_path.read_text(encoding="utf-8"))


def write_contract_source(spec: ContractSpec, payload: list[dict[str, Any]]) -> None:
    spec.source_toml_path.parent.mkdir(parents=True, exist_ok=True)
    spec.source_toml_path.write_text(_source_toml(spec, payload), encoding="utf-8")


def canonical_json(payload: list[dict[str, Any]]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _diff_lines(before: str, after: str) -> list[str]:
    return list(difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile="source-json.canonical.json",
        tofile="round-trip.canonical.json",
        lineterm="",
    ))


def _diff_preview(diff: list[str], *, limit: int = 80) -> list[str]:
    return diff[:limit]


def audit_contract_sources(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    tree_root: Path | None = None,
    allow_checkout_output: bool = False,
) -> list[ContractAuditResult]:
    repo_root = contract_paths(tree_root).repo_root if tree_root is not None else REPO_DIR
    if not allow_checkout_output and _is_relative_to(output_dir, repo_root):
        raise ValueError(
            "TOML source import output must stay outside the checkout unless explicitly allowed; "
            f"got {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[ContractAuditResult] = []
    for spec in contract_specs(tree_root, source_dir=output_dir):
        payload = _contract_payload(spec)
        toml_text = _source_toml(spec, payload)
        source_toml_path = spec.source_toml_path
        source_toml_path.write_text(toml_text, encoding="utf-8")
        round_trip_payload = _payload_from_source_toml(spec, toml_text)
        before = canonical_json(payload)
        after = canonical_json(round_trip_payload)
        diff = _diff_lines(before, after) if before != after else []
        results.append(ContractAuditResult(
            contract=spec.contract,
            source_json_path=_repo_rel(spec.source_json_path, repo_root=spec.repo_root),
            source_toml_path=str(source_toml_path),
            row_count=len(payload),
            source_json_sha256=_source_sha256(spec.source_json_path),
            source_toml_bytes=len(toml_text.encode("utf-8")),
            semantic_equal=payload == round_trip_payload,
            canonical_byte_equal=before == after,
            canonical_diff_line_count=len(diff),
            canonical_diff_preview=_diff_preview(diff),
        ))
    return results


def markdown_report(results: list[ContractAuditResult]) -> str:
    passed = all(result.semantic_equal and result.canonical_byte_equal for result in results)
    lines = [
        "# Matcher Contract TOML Source Audit",
        "",
        f"Generated: {date.today().isoformat()}",
        "",
        "This audit checks the native TOML source schema for the matcher",
        "contract JSON files. In B5 the TOML files are the authored sources;",
        "the JSON contracts are generated from these TOML sources.",
        "",
        f"Decision: {'PASS' if passed else 'FAIL'}",
        "Generated JSON committed: yes",
        "",
        "## Results",
        "",
        "| Contract | Rows | Semantic Equal | Canonical Byte Equal | TOML Bytes |",
        "|---|---:|---|---|---:|",
    ]
    for result in results:
        lines.append(
            "| "
            f"{result.contract} | "
            f"{result.row_count} | "
            f"{'yes' if result.semantic_equal else 'no'} | "
            f"{'yes' if result.canonical_byte_equal else 'no'} | "
            f"{result.source_toml_bytes} |"
        )
    lines.extend([
        "",
        "## Source Files",
        "",
    ])
    for result in results:
        lines.append(f"- `{result.source_toml_path}` generates `{result.source_json_path}`")
    if any(result.canonical_diff_preview for result in results):
        lines.extend(["", "## Canonical Diff Preview", ""])
        for result in results:
            if not result.canonical_diff_preview:
                continue
            lines.append(f"### {result.contract}")
            lines.extend(f"    {line}" for line in result.canonical_diff_preview)
    return "\n".join(lines).rstrip() + "\n"


def json_report(results: list[ContractAuditResult]) -> str:
    passed = all(result.semantic_equal and result.canonical_byte_equal for result in results)
    payload = {
        "generated": date.today().isoformat(),
        "decision": "PASS" if passed else "FAIL",
        "generated_json_committed": True,
        "schema_readme": _repo_rel(SCHEMA_README),
        "results": [asdict(result) for result in results],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT_OUTPUT)
    parser.add_argument("--json-report-output", type=Path, default=DEFAULT_JSON_REPORT_OUTPUT)
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument(
        "--allow-checkout-output",
        action="store_true",
        help="Allow writing TOML sources inside the checkout for import/maintenance.",
    )
    parser.add_argument("--fail-on-diff", action="store_true")
    args = parser.parse_args()

    try:
        results = audit_contract_sources(
            args.output_dir,
            allow_checkout_output=args.allow_checkout_output,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    markdown = markdown_report(results)
    json_payload = json_report(results)
    if args.write_report:
        args.report_output.parent.mkdir(parents=True, exist_ok=True)
        args.report_output.write_text(markdown, encoding="utf-8")
        args.json_report_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_report_output.write_text(json_payload, encoding="utf-8")
        print(f"wrote {args.report_output}")
        print(f"wrote {args.json_report_output}")
    else:
        print(markdown)

    failed = any(not result.semantic_equal or not result.canonical_byte_equal for result in results)
    if args.fail_on_diff and failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
