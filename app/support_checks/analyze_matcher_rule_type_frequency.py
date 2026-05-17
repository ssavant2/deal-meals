#!/usr/bin/env python3
"""Summarize matcher rule-type frequency from the local batch review log."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
import re


APP_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = APP_DIR.parent
DEFAULT_SOURCE = APP_DIR / "tests" / "batch_review_questions.md"
DEFAULT_OUTPUT = REPO_DIR / "docs" / "MATCHER_RULE_TYPE_FREQUENCY.md"

PATTERNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("pnb", "PNB add", ("pnb",)),
    ("fpb", "FPB add", ("fpb",)),
    ("ksbc", "KSBC add", ("ksbc",)),
    ("bdpk", "BDPK add", ("bdpk",)),
    ("keyword_extra_parent", "keyword_extra_parent fan-out", ("keyword_extra_parent", "keyword extra parent")),
    ("no_match_policy", "no_match_policy add", ("no_match_policy", "no-match policy")),
    ("specialty", "specialty qualifier", ("specialty", "specialty_qualifier", "specialty qualifier")),
    ("stop_word", "STOP_WORDS extension", ("stop_word", "stop_words", "stop words", "stop_word:")),
)


def _interesting_lines(text: str) -> list[tuple[int, str]]:
    lines = []
    in_fix_section = False
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        lower = stripped.lower()
        token_hit = any(token in lower for _key, _label, tokens in PATTERNS for token in tokens)
        fixish_line = any(
            marker in lower
            for marker in (
                "fix",
                "löst",
                "lost",
                "implementation",
                "tillagd",
                "tillagt",
                "added",
            )
        )
        if re.search(r"fix(ar|ar tillämpade|ar —|ar -)", lower):
            in_fix_section = True
        if in_fix_section and stripped.startswith("### ") and "fix" not in lower:
            in_fix_section = False
        if stripped.startswith("-") and (in_fix_section or token_hit):
            lines.append((number, stripped))
        elif token_hit and fixish_line:
            lines.append((number, stripped))
    return lines


def analyze(source: Path) -> tuple[Counter[str], dict[str, list[tuple[int, str]]], int]:
    text = source.read_text(encoding="utf-8")
    lines = _interesting_lines(text)
    counts: Counter[str] = Counter()
    examples: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for number, line in lines:
        lower = line.lower()
        matched = False
        for key, _label, tokens in PATTERNS:
            if any(token in lower for token in tokens):
                counts[key] += 1
                matched = True
                if len(examples[key]) < 3:
                    examples[key].append((number, line))
        if not matched:
            counts["other"] += 1
            if len(examples["other"]) < 3:
                examples["other"].append((number, line))
    return counts, examples, len(lines)


def _markdown(source: Path, counts: Counter[str], examples: dict[str, list[tuple[int, str]]], total: int) -> str:
    rows = []
    ordered_keys = [key for key, _label, _tokens in PATTERNS] + ["other"]
    labels = {key: label for key, label, _tokens in PATTERNS}
    labels["other"] = "Other/manual"
    commands = {
        "pnb": "`dm matcher add pnb <keyword>` (future)",
        "fpb": "`dm matcher add fpb <keyword>` (future)",
        "ksbc": "`dm matcher add ksbc <keyword>` (future)",
        "bdpk": "`dm matcher add bdpk <keyword>` (future)",
        "keyword_extra_parent": "`dm matcher add keyword-extra-parent <canonical>`",
        "no_match_policy": "`dm matcher add no-match-policy <policy>` (future)",
        "specialty": "`dm matcher add specialty <keyword>` (future)",
        "stop_word": "`dm matcher add stop-word <word>` (future)",
        "other": "Manual",
    }
    for key in ordered_keys:
        count = counts.get(key, 0)
        share = (count / total * 100) if total else 0
        rows.append(f"| {labels[key]} | {count} | {share:.1f}% | {commands[key]} |")

    example_lines = []
    for key in ordered_keys:
        if not examples.get(key):
            continue
        example_lines.append(f"### {labels[key]}")
        for number, line in examples[key]:
            example_lines.append(f"- line {number}: {line}")
        example_lines.append("")

    return "\n".join([
        "# Matcher Rule Type Frequency",
        "",
        f"Generated: {date.today().isoformat()}",
        f"Source: `{source.relative_to(REPO_DIR) if source.is_relative_to(REPO_DIR) else source}`",
        "",
        "This is a heuristic scan of local batch-review fix notes. It is used to",
        "choose which `dm matcher add ...` subcommands are worth building first.",
        "",
        f"Classified fix-note lines: {total}",
        "",
        "| Pattern | Count | Share | CLI status |",
        "|---|---:|---:|---|",
        *rows,
        "",
        "## Decision",
        "",
        "Phase 4 ships only `keyword-extra-parent`. The PNB/FPB-like patterns are",
        "more frequent, but they encode more policy-specific blocker semantics.",
        "`keyword_extra_parent` is lower risk and already has a uniform registry,",
        "fixture, inventory, and sanity-test shape.",
        "",
        "## Examples",
        "",
        *example_lines,
    ]).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--write", action="store_true", help="Write the markdown report.")
    args = parser.parse_args()

    if not args.source.exists():
        raise FileNotFoundError(f"batch review source not found: {args.source}")
    counts, examples, total = analyze(args.source)
    markdown = _markdown(args.source, counts, examples, total)
    if args.write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
