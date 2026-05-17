#!/usr/bin/env python3
"""Audit whether matcher contract JSON files can stop being authoritative."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date
import json
from pathlib import Path
import re


APP_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = (
    APP_DIR.parent
    if APP_DIR.parent != Path(APP_DIR.anchor) and (APP_DIR.parent / "docs").is_dir()
    else APP_DIR
)
DEFAULT_OUTPUT = REPO_DIR / "docs" / "MATCHER_CONTRACT_JSON_AUTHORITY_AUDIT.md"
DEFAULT_JSON_OUTPUT = REPO_DIR / "docs" / "MATCHER_CONTRACT_JSON_AUTHORITY_AUDIT.json"
CONTRACT_FILES = (
    "matcher_regression_cases.json",
    "matcher_rule_inventory.json",
)
DEFAULT_PATH_SYMBOLS = (
    "DEFAULT_FIXTURE_FILE",
    "DEFAULT_INVENTORY_FILE",
    "RULE_INVENTORY_FILE",
    "REGRESSION_CASES_FILE",
)
BLOCKING_CLASSIFICATIONS = {
    "blocking_cli_default_path",
    "blocking_default_path",
    "blocking_imported_default_path",
    "blocking_path_resolver",
    "blocking_reader",
}
SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "postgres",
}


@dataclass(frozen=True)
class Hit:
    path: Path
    line: int
    text: str
    classification: str
    consumer_type: str
    owner: str
    migration_path: str
    is_blocker: bool


def _iter_text_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.name in CONTRACT_FILES:
            continue
        if path.name in {DEFAULT_OUTPUT.name, DEFAULT_JSON_OUTPUT.name}:
            continue
        if path.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".db"}:
            continue
        files.append(path)
    return files


def _is_test_path(path: Path) -> bool:
    return "tests" in path.parts


def _is_generated_reference_path(path: Path) -> bool:
    return (
        "baselines" in path.parts
        or path.name in {"matcher_regression_case.toml", "matcher_rule_inventory.toml"}
    )


def _owner(path: Path) -> str:
    rel = _rel(path)
    if rel.startswith("app/cli/"):
        return "cli"
    if rel.startswith("app/support_checks/"):
        return "support_checks"
    if rel.startswith("app/languages/"):
        return "language_contract"
    if rel.startswith("docs/"):
        return "docs"
    return "repo"


def _migration_path(classification: str, owner: str) -> str:
    if classification not in BLOCKING_CLASSIFICATIONS:
        return ""
    if owner == "cli":
        return "Use app/support_checks/matcher_contracts.py for path resolution and JSON read/write helpers."
    if classification == "blocking_path_resolver":
        return "Move fixture/inventory path construction behind app/support_checks/matcher_contracts.py."
    if classification == "blocking_cli_default_path":
        return "Resolve CLI/parser defaults through app/support_checks/matcher_contracts.py."
    if classification == "blocking_imported_default_path":
        return "Import contract paths/loaders from app/support_checks/matcher_contracts.py instead of another consumer module."
    return "Load and write matcher contract JSON through app/support_checks/matcher_contracts.py."


def _classify(path: Path, line: str) -> tuple[str, str]:
    suffix = path.suffix.lower()
    lower = line.lower()
    stripped = line.strip()
    if _is_test_path(path):
        return "test_reference", "test"
    if _is_generated_reference_path(path):
        return "generated_output_reference", "generated_output"
    if suffix == ".py":
        has_contract_file = any(name in line for name in CONTRACT_FILES)
        has_default_symbol = any(symbol in line for symbol in DEFAULT_PATH_SYMBOLS)
        if "parser.add_argument" in line and has_default_symbol:
            return "blocking_cli_default_path", "cli_default"
        if has_contract_file and "return _app_dir_for_tree_root" in line:
            return "blocking_path_resolver", "path_resolver"
        if has_default_symbol and any(
            token in line
            for token in ("_load_json", "_load_fixture_payload", "load_inventory", "json.load", "read_text", "open(")
        ):
            return "blocking_reader", "reader"
        if has_default_symbol and "=" in line:
            return "blocking_default_path", "default_path"
        if has_contract_file and re.search(r"\b(DEFAULT_|RULE_|REGRESSION_).*=.*matcher_contracts", line):
            return "blocking_default_path", "default_path"
        if has_contract_file and re.search(r"\b(fixture_file|inventory_file)\s*=.*or.*matcher_contracts", line):
            return "blocking_default_path", "default_path"
        if has_default_symbol and (
            stripped.startswith("from ")
            or stripped in DEFAULT_PATH_SYMBOLS
            or stripped.rstrip(",") in DEFAULT_PATH_SYMBOLS
        ):
            return "blocking_imported_default_path", "imported_default_path"
        if has_contract_file and any(token in lower for token in ("json.load", "read_text", "open(", "_load_json")):
            return "blocking_reader", "reader"
        if has_contract_file or has_default_symbol:
            return "python_reference", "python_reference"
        return "python_reference", "python_reference"
    if path.name == "MATCHER_REGISTRY_ARCHITECTURE.md":
        return "planning_doc", "planning_doc"
    if suffix == ".md":
        return "documentation", "documentation"
    return "reference", "reference"


def audit(root: Path = REPO_DIR) -> list[Hit]:
    hits: list[Hit] = []
    pattern = re.compile("|".join(re.escape(name) for name in (*CONTRACT_FILES, *DEFAULT_PATH_SYMBOLS)))
    for path in _iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (PermissionError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                classification, consumer_type = _classify(path, line)
                owner = _owner(path)
                hits.append(Hit(
                    path=path,
                    line=number,
                    text=line.strip(),
                    classification=classification,
                    consumer_type=consumer_type,
                    owner=owner,
                    migration_path=_migration_path(classification, owner),
                    is_blocker=classification in BLOCKING_CLASSIFICATIONS,
                ))
    return hits


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_DIR))
    except ValueError:
        return str(path)


def markdown(hits: list[Hit]) -> str:
    blocking = [hit for hit in hits if hit.is_blocker]
    counts: dict[str, int] = {}
    for hit in hits:
        counts[hit.classification] = counts.get(hit.classification, 0) + 1

    lines = [
        "# Matcher Contract JSON Authority Audit",
        "",
        f"Generated: {date.today().isoformat()}",
        "",
        "This audit is the L3-C gate for making matcher contract JSON derived",
        "from TOML sources. If any blocking consumers exist, the JSON-as-derived",
        "migration is vetoed until those consumers are migrated first.",
        "",
        f"Decision: {'VETOED' if blocking else 'PASS'}",
        f"Blocker baseline count: {len(blocking)}",
        "",
        "## Summary",
        "",
        "| Classification | Count |",
        "|---|---:|",
    ]
    for key in sorted(counts):
        lines.append(f"| {key} | {counts[key]} |")

    if blocking:
        lines.extend([
            "",
            "## Blocking Consumers",
            "",
            "These Python consumers still read, resolve, or import default paths",
            "for the JSON contracts directly. The JSON files therefore remain",
            "authored source-of-truth for now.",
            "",
        ])
        for hit in blocking[:80]:
            lines.append(
                f"- `{_rel(hit.path)}:{hit.line}` — `{hit.classification}`; "
                f"owner: `{hit.owner}`; consumer: `{hit.consumer_type}`"
            )
            lines.append(f"  - text: `{hit.text}`")
            lines.append(f"  - migration: {hit.migration_path}")
        if len(blocking) > 80:
            lines.append(f"- ... {len(blocking) - 80} additional blocking consumer(s)")

    lines.extend([
        "",
        "## All References",
        "",
    ])
    for hit in hits[:160]:
        marker = "BLOCKER" if hit.is_blocker else "ref"
        lines.append(
            f"- `{marker}` `{hit.classification}` `{_rel(hit.path)}:{hit.line}` — `{hit.text}`"
        )
    if len(hits) > 160:
        lines.append(f"- ... {len(hits) - 160} additional reference(s)")
    return "\n".join(lines).rstrip() + "\n"


def _hit_payload(hit: Hit) -> dict[str, object]:
    payload = asdict(hit)
    payload["path"] = _rel(hit.path)
    return payload


def json_report(hits: list[Hit]) -> str:
    blocking = [hit for hit in hits if hit.is_blocker]
    included_findings = [
        hit
        for hit in hits
        if hit.is_blocker or hit.classification != "generated_output_reference"
    ]
    omitted_counts: dict[str, int] = {}
    for hit in hits:
        if not hit.is_blocker and hit.classification == "generated_output_reference":
            omitted_counts[hit.classification] = omitted_counts.get(hit.classification, 0) + 1
    counts: dict[str, int] = {}
    for hit in hits:
        counts[hit.classification] = counts.get(hit.classification, 0) + 1
    payload = {
        "generated": date.today().isoformat(),
        "decision": "VETOED" if blocking else "PASS",
        "blocker_baseline_count": len(blocking),
        "summary": dict(sorted(counts.items())),
        "omitted_findings": dict(sorted(omitted_counts.items())),
        "blockers": [_hit_payload(hit) for hit in blocking],
        "findings": [_hit_payload(hit) for hit in included_findings],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--fail-on-veto", action="store_true")
    args = parser.parse_args()

    hits = audit(args.root)
    output = markdown(hits)
    json_output = json_report(hits)
    if args.write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json_output, encoding="utf-8")
        print(f"wrote {args.output}")
        print(f"wrote {args.json_output}")
    else:
        print(output)
    if args.fail_on_veto and any(hit.is_blocker for hit in hits):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
