#!/usr/bin/env python3
"""Refresh matcher rule inventory line_ref ranges from their stable anchors."""

from __future__ import annotations

import argparse
from bisect import bisect_right
import json
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parent
import sys

sys.path.insert(0, str(APP_DIR))

from support_checks.matcher_contracts import (  # noqa: E402
    inventory_contract_path,
    load_inventory_contract,
    write_inventory_contract,
)


def _load_inventory(path: Path) -> list[dict[str, Any]]:
    return load_inventory_contract(path)


def _write_inventory(path: Path, payload: list[dict[str, Any]]) -> None:
    write_inventory_contract(payload, path, sort_keys=True)


def _line_start_offsets(source_text: str) -> list[int]:
    offsets = [0]
    for index, char in enumerate(source_text):
        if char == "\n":
            offsets.append(index + 1)
    return offsets


def _line_no_for_offset(offsets: list[int], offset: int) -> int:
    return bisect_right(offsets, offset)


def _anchor_ranges(source_text: str, anchor: str) -> list[tuple[int, int]]:
    offsets = _line_start_offsets(source_text)
    ranges = []
    start = source_text.find(anchor)
    while start != -1:
        end = start + len(anchor)
        ranges.append((
            _line_no_for_offset(offsets, start),
            _line_no_for_offset(offsets, max(start, end - 1)),
        ))
        start = source_text.find(anchor, start + 1)
    return ranges


def _choose_range(
    ranges: list[tuple[int, int]],
    *,
    recorded_start: int,
    recorded_end: int,
) -> tuple[int, int]:
    recorded_midpoint = (recorded_start + recorded_end) / 2
    return min(
        ranges,
        key=lambda item: (
            abs(((item[0] + item[1]) / 2) - recorded_midpoint),
            item[0],
            item[1],
        ),
    )


def refresh_line_refs(
    inventory: list[dict[str, Any]],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    source_cache: dict[str, str] = {}
    summary = {
        "line_refs": 0,
        "updated": 0,
        "unchanged": 0,
        "missing_anchor": 0,
        "ambiguous_anchor": 0,
        "missing_path": 0,
    }
    missing: list[dict[str, str]] = []

    for entry in inventory:
        entry_id = str(entry.get("id") or "<unknown>")
        for line_ref in entry.get("line_refs") or []:
            if not isinstance(line_ref, dict):
                continue
            summary["line_refs"] += 1
            path = str(line_ref.get("path") or "")
            anchor = str(line_ref.get("anchor") or "")
            if not path or not anchor:
                summary["missing_anchor"] += 1
                missing.append({"id": entry_id, "path": path, "anchor": anchor})
                continue

            absolute_path = repo_root / path
            if not absolute_path.is_file():
                summary["missing_path"] += 1
                missing.append({"id": entry_id, "path": path, "anchor": anchor})
                continue

            source_text = source_cache.setdefault(
                path,
                absolute_path.read_text(encoding="utf-8"),
            )
            ranges = _anchor_ranges(source_text, anchor)
            if not ranges:
                summary["missing_anchor"] += 1
                missing.append({"id": entry_id, "path": path, "anchor": anchor})
                continue
            if len(ranges) > 1:
                summary["ambiguous_anchor"] += 1

            recorded_start = int(line_ref.get("start") or 0)
            recorded_end = int(line_ref.get("end") or recorded_start)
            new_start, new_end = _choose_range(
                ranges,
                recorded_start=recorded_start,
                recorded_end=recorded_end,
            )
            if recorded_start == new_start and recorded_end == new_end:
                summary["unchanged"] += 1
                continue

            line_ref["start"] = new_start
            line_ref["end"] = new_end
            summary["updated"] += 1

    summary["missing"] = missing[:20]
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-file", type=Path, default=inventory_contract_path())
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--write", action="store_true", help="write refreshed line refs")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = _load_inventory(args.inventory_file)
    summary = refresh_line_refs(inventory, repo_root=args.repo_root)

    if args.write:
        _write_inventory(args.inventory_file, inventory)

    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        mode = "write" if args.write else "dry-run"
        print(
            f"matcher rule inventory line-ref refresh {mode}: "
            f"{summary['updated']} updated, {summary['unchanged']} unchanged, "
            f"{summary['missing_anchor']} missing anchors, {summary['missing_path']} missing paths, "
            f"{summary['ambiguous_anchor']} ambiguous anchors"
        )

    if summary["missing_anchor"] or summary["missing_path"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
