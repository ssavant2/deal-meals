#!/usr/bin/env python3
"""Audit whether matcher contract JSON files can stop being authoritative."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re


APP_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = (
    APP_DIR.parent
    if APP_DIR.parent != Path(APP_DIR.anchor) and (APP_DIR.parent / "docs").is_dir()
    else APP_DIR
)
DEFAULT_OUTPUT = REPO_DIR / "docs" / "MATCHER_CONTRACT_JSON_AUTHORITY_AUDIT.md"
CONTRACT_FILES = (
    "matcher_regression_cases.json",
    "matcher_rule_inventory.json",
)
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


def _iter_text_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.name in CONTRACT_FILES:
            continue
        if path.name == DEFAULT_OUTPUT.name:
            continue
        if path.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".db"}:
            continue
        files.append(path)
    return files


def _classify(path: Path, line: str) -> str:
    suffix = path.suffix.lower()
    lower = line.lower()
    if suffix == ".py" and any(token in lower for token in ("json.load", "read_text", "open(", "default_")):
        return "blocking_reader"
    if suffix == ".py":
        return "python_reference"
    if path.name in {"MATCHER_RULE_CHANGE_FLOW_IMPROVEMENTS.md", "MATCHER_REGISTRY_ARCHITECTURE.md"}:
        return "planning_doc"
    if suffix == ".md":
        return "documentation"
    return "reference"


def audit(root: Path = REPO_DIR) -> list[Hit]:
    hits: list[Hit] = []
    pattern = re.compile("|".join(re.escape(name) for name in CONTRACT_FILES))
    for path in _iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (PermissionError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                hits.append(Hit(
                    path=path,
                    line=number,
                    text=line.strip(),
                    classification=_classify(path, line),
                ))
    return hits


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_DIR))
    except ValueError:
        return str(path)


def markdown(hits: list[Hit]) -> str:
    blocking = [hit for hit in hits if hit.classification == "blocking_reader"]
    counts: dict[str, int] = {}
    for hit in hits:
        counts[hit.classification] = counts.get(hit.classification, 0) + 1

    lines = [
        "# Matcher Contract JSON Authority Audit",
        "",
        f"Generated: {date.today().isoformat()}",
        "",
        "This audit is the L3-C gate for making matcher contract JSON derived",
        "from TOML sources. If any blocking readers exist, the JSON-as-derived",
        "migration is vetoed until those consumers are migrated first.",
        "",
        f"Decision: {'VETOED' if blocking else 'PASS'}",
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
            "## Blocking Readers",
            "",
            "These Python consumers still read the JSON contracts directly. The",
            "JSON files therefore remain authored source-of-truth for now.",
            "",
        ])
        for hit in blocking[:80]:
            lines.append(f"- `{_rel(hit.path)}:{hit.line}` — `{hit.text}`")
        if len(blocking) > 80:
            lines.append(f"- ... {len(blocking) - 80} additional blocking reader(s)")

    lines.extend([
        "",
        "## All References",
        "",
    ])
    for hit in hits[:160]:
        lines.append(f"- `{hit.classification}` `{_rel(hit.path)}:{hit.line}` — `{hit.text}`")
    if len(hits) > 160:
        lines.append(f"- ... {len(hits) - 160} additional reference(s)")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--fail-on-veto", action="store_true")
    args = parser.parse_args()

    hits = audit(args.root)
    output = markdown(hits)
    if args.write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(output)
    if args.fail_on_veto and any(hit.classification == "blocking_reader" for hit in hits):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
