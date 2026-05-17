#!/usr/bin/env python3
"""Generate/check matcher contract JSON from authoritative TOML sources."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from support_checks.audit_matcher_contract_toml_sources import (  # noqa: E402
    ContractSpec,
    _diff_lines,
    _payload_from_source_toml,
    _repo_rel,
    canonical_json,
    contract_specs,
    source_dir_for_tree_root,
)
from support_checks.matcher_contracts import (  # noqa: E402
    load_fixture_contract,
    load_inventory_contract,
)


@dataclass(frozen=True)
class GeneratedContractResult:
    contract: str
    source_toml_path: str
    target_json_path: str
    row_count: int
    semantic_equal: bool
    canonical_byte_equal: bool
    raw_byte_equal: bool
    canonical_diff_line_count: int
    canonical_diff_preview: list[str]

    @property
    def drifted(self) -> bool:
        return not self.semantic_equal or not self.canonical_byte_equal or not self.raw_byte_equal


def _current_payload(spec: ContractSpec) -> list[dict[str, Any]]:
    if spec.contract == "matcher_regression_cases":
        return load_fixture_contract(spec.source_json_path)
    if spec.contract == "matcher_rule_inventory":
        return load_inventory_contract(spec.source_json_path)
    raise ValueError(f"unknown contract: {spec.contract}")


def _generated_payload(spec: ContractSpec) -> list[dict[str, Any]]:
    return _payload_from_source_toml(spec, spec.source_toml_path.read_text(encoding="utf-8"))


def check_generated_contract_json(
    *,
    tree_root: Path | None = None,
    source_dir: Path | None = None,
    write: bool = False,
) -> list[GeneratedContractResult]:
    results: list[GeneratedContractResult] = []
    for spec in contract_specs(tree_root, source_dir=source_dir):
        generated_payload = _generated_payload(spec)
        generated_canonical = canonical_json(generated_payload)
        if write:
            spec.source_json_path.write_text(generated_canonical, encoding="utf-8")
        current_payload = _current_payload(spec)
        current_canonical = canonical_json(current_payload)
        diff = _diff_lines(current_canonical, generated_canonical) if current_canonical != generated_canonical else []
        raw_json = spec.source_json_path.read_text(encoding="utf-8") if spec.source_json_path.exists() else ""
        results.append(GeneratedContractResult(
            contract=spec.contract,
            source_toml_path=_repo_rel(spec.source_toml_path, repo_root=spec.repo_root),
            target_json_path=_repo_rel(spec.source_json_path, repo_root=spec.repo_root),
            row_count=len(generated_payload),
            semantic_equal=current_payload == generated_payload,
            canonical_byte_equal=current_canonical == generated_canonical,
            raw_byte_equal=raw_json == generated_canonical,
            canonical_diff_line_count=len(diff),
            canonical_diff_preview=diff[:80],
        ))
    return results


def report_payload(results: list[GeneratedContractResult]) -> dict[str, Any]:
    drifted = [result for result in results if result.drifted]
    return {
        "decision": "PASS" if not drifted else "FAIL",
        "results": [asdict(result) for result in results],
    }


def format_text(results: list[GeneratedContractResult]) -> str:
    payload = report_payload(results)
    lines = [
        "Matcher contract TOML source check",
        f"Decision: {payload['decision']}",
        "",
        "| Contract | Rows | Semantic Equal | Canonical Equal | Raw Byte Equal |",
        "|---|---:|---|---|---|",
    ]
    for result in results:
        lines.append(
            "| "
            f"{result.contract} | "
            f"{result.row_count} | "
            f"{'yes' if result.semantic_equal else 'no'} | "
            f"{'yes' if result.canonical_byte_equal else 'no'} | "
            f"{'yes' if result.raw_byte_equal else 'no'} |"
        )
    for result in results:
        if not result.canonical_diff_preview:
            continue
        lines.extend(["", f"## {result.contract} Canonical Diff Preview"])
        lines.extend(f"    {line}" for line in result.canonical_diff_preview)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree-root", type=Path, default=None)
    parser.add_argument("--source-dir", type=Path, default=None)
    parser.add_argument("--write", action="store_true", help="Write canonical generated JSON from TOML sources.")
    parser.add_argument("--check", action="store_true", help="Fail if generated JSON bytes drift from TOML sources.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    source_dir = args.source_dir or source_dir_for_tree_root(args.tree_root)
    try:
        results = check_generated_contract_json(
            tree_root=args.tree_root,
            source_dir=source_dir,
            write=args.write,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    payload = report_payload(results)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text(results))
    if args.check and payload["decision"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
