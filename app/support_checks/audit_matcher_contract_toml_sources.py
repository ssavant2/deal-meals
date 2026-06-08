#!/usr/bin/env python3
"""Audit TOML source schema for matcher contracts."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date
import difflib
import json
from pathlib import Path
import sys
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = (
    APP_DIR.parent
    if APP_DIR.parent != Path(APP_DIR.anchor) and (APP_DIR.parent / "docs").is_dir()
    else APP_DIR
)
sys.path.insert(0, str(APP_DIR))

from support_checks.matcher_contracts import (  # noqa: E402
    _payload_from_source_toml,
    _repo_rel,
    _source_toml,
    canonical_json,
    contract_paths,
    contract_spec_by_name,
    contract_specs,
    load_contract_source,
    source_dir_for_tree_root,
)


DEFAULT_OUTPUT_DIR = Path("/tmp/deal-meals-matcher-contract-sources")
REPORTS_DIR = APP_DIR / "support_checks" / "reports"
DEFAULT_REPORT_OUTPUT = REPORTS_DIR / "MATCHER_CONTRACT_TOML_SOURCE_AUDIT.md"
DEFAULT_JSON_REPORT_OUTPUT = REPORTS_DIR / "MATCHER_CONTRACT_TOML_SOURCE_AUDIT.json"
SCHEMA_README = APP_DIR / "languages" / "sv" / "matcher_contracts" / "sources" / "README.md"


@dataclass(frozen=True)
class ContractAuditResult:
    contract: str
    source_toml_path: str
    row_count: int
    source_toml_bytes: int
    semantic_equal: bool
    canonical_byte_equal: bool
    canonical_diff_line_count: int
    canonical_diff_preview: list[str]


CONTRACT_SPECS = contract_specs()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


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
        source_spec = contract_spec_by_name(spec.contract, tree_root=tree_root)
        payload = load_contract_source(source_spec)
        toml_text = _source_toml(spec, payload)
        source_toml_path = spec.source_toml_path
        source_toml_path.write_text(toml_text, encoding="utf-8")
        round_trip_payload = _payload_from_source_toml(spec, toml_text)
        before = canonical_json(payload)
        after = canonical_json(round_trip_payload)
        diff = _diff_lines(before, after) if before != after else []
        results.append(ContractAuditResult(
            contract=spec.contract,
            source_toml_path=str(source_toml_path),
            row_count=len(payload),
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
        "contracts. The TOML files are the authored sources.",
        "",
        f"Decision: {'PASS' if passed else 'FAIL'}",
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
        lines.append(f"- `{result.source_toml_path}`")
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
