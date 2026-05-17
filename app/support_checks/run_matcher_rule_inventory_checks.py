#!/usr/bin/env python3
"""Validate matcher rule inventory coverage."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = APP_DIR.parent
sys.path.insert(0, str(APP_DIR))

from support_checks.matcher_contracts import (  # noqa: E402
    fixture_contract_path,
    inventory_contract_path,
    load_fixture_contract,
    load_inventory_contract,
)
from support_checks.run_matcher_layer_fixture_cases import (  # noqa: E402
    ALLOWED_SOURCE_REF_PREFIXES,
    has_temporary_fixture_id,
    has_temporary_policy_ref,
    has_temporary_source_ref,
    source_ref_prefix_hint,
)


REQUIRED_FIELDS = frozenset({
    "id",
    "status",
    "kind",
    "canonical",
    "owner",
    "policy_ref",
    "source_refs",
    "fixture_refs",
    "risk",
    "line_refs",
    "notes",
})

ALLOWED_STATUSES = frozenset({
    "observed_legacy",
    "wrapped_adapter",
    "migrate_bridge",
    "migrate_expansion",
    "migrate_no_match_policy",
    "deprecated",
})
MIGRATION_CANDIDATE_STATUSES = frozenset({
    "migrate_bridge",
    "migrate_expansion",
    "migrate_no_match_policy",
})

ALLOWED_KINDS = frozenset({
    "legacy_backend_allowance",
    "legacy_backend_validator",
    "legacy_extraction",
    "legacy_extra_keyword",
    "legacy_no_match_policy",
    "legacy_normalization",
    "legacy_parent",
    "legacy_prepared_text_expansion",
    "legacy_synonym",
    "legacy_validator",
})

ALLOWED_RISKS = frozenset({
    "backend_guard",
    "flavor_guard",
    "form_guard",
    "no_match_policy",
    "policy_term",
    "prepared_state",
    "processed_allowance",
    "route_gap_guard",
    "spelling_alias",
})


def _entry_adapter_refs(entry: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    adapter_ref = entry.get("adapter_ref")
    if isinstance(adapter_ref, str) and adapter_ref.strip():
        refs.append(adapter_ref)
    adapter_refs = entry.get("adapter_refs")
    if isinstance(adapter_refs, list):
        refs.extend(ref for ref in adapter_refs if isinstance(ref, str) and ref.strip())
    return refs


def load_inventory(path: Path) -> list[dict[str, Any]]:
    return load_inventory_contract(path)


def _validate_line_ref(entry_id: str, line_ref: Any, *, repo_root: Path = REPO_DIR) -> list[str]:
    failures = []
    if not isinstance(line_ref, dict):
        return [f"{entry_id}: line_refs entries must be objects"]

    missing = [field for field in ("path", "start", "end", "anchor") if field not in line_ref]
    if missing:
        failures.append(f"{entry_id}: line_ref missing fields: {', '.join(missing)}")
        return failures

    path = str(line_ref["path"])
    if Path(path).is_absolute():
        failures.append(f"{entry_id}: line_ref path must be repo-relative: {path}")
        return failures

    try:
        start = int(line_ref["start"])
        end = int(line_ref["end"])
    except (TypeError, ValueError):
        failures.append(f"{entry_id}: line_ref start/end must be integers")
        return failures

    if start < 1 or end < start:
        failures.append(f"{entry_id}: invalid line range {start}-{end}")
        return failures

    anchor = line_ref["anchor"]
    if not isinstance(anchor, str) or not anchor.strip():
        failures.append(f"{entry_id}: line_ref anchor must be a non-empty string")
        return failures

    target = repo_root / path
    if not target.exists():
        failures.append(f"{entry_id}: line_ref path does not exist: {path}")
        return failures

    source_text = target.read_text(encoding="utf-8")
    if anchor not in source_text:
        failures.append(f"{entry_id}: line_ref anchor not found in {path}: {anchor}")

    line_count = len(source_text.splitlines())
    if end > line_count:
        failures.append(f"{entry_id}: line_ref {path}:{end} exceeds file length {line_count}")
    return failures


def _line_ref_anchor_in_recorded_range(line_ref: Any, *, repo_root: Path = REPO_DIR) -> bool:
    if not isinstance(line_ref, dict):
        return False
    try:
        path = str(line_ref["path"])
        start = int(line_ref["start"])
        end = int(line_ref["end"])
    except (KeyError, TypeError, ValueError):
        return False
    anchor = line_ref.get("anchor")
    if not isinstance(anchor, str) or not anchor.strip():
        return False
    target = repo_root / path
    if not target.exists() or start < 1 or end < start:
        return False
    lines = target.read_text(encoding="utf-8").splitlines()
    if end > len(lines):
        return False
    return anchor in "\n".join(lines[start - 1:end])


def _validate_entry(
    entry: Any,
    fixture_ids: set[str],
    seen_ids: set[str],
    *,
    repo_root: Path = REPO_DIR,
) -> list[str]:
    failures = []
    if not isinstance(entry, dict):
        return ["inventory entries must be objects"]

    entry_id = str(entry.get("id") or "<missing-id>")
    missing = sorted(REQUIRED_FIELDS - set(entry))
    if missing:
        failures.append(f"{entry_id}: missing fields: {', '.join(missing)}")

    if entry_id in seen_ids:
        failures.append(f"{entry_id}: duplicate inventory id")
    seen_ids.add(entry_id)

    if entry.get("status") not in ALLOWED_STATUSES:
        failures.append(f"{entry_id}: unknown status {entry.get('status')!r}")
    if entry.get("kind") not in ALLOWED_KINDS:
        failures.append(f"{entry_id}: unknown kind {entry.get('kind')!r}")
    if entry.get("risk") not in ALLOWED_RISKS:
        failures.append(f"{entry_id}: unknown risk {entry.get('risk')!r}")
    if entry.get("owner") != "matcher":
        failures.append(f"{entry_id}: owner must be matcher")

    for text_field in ("canonical", "policy_ref", "notes"):
        if not isinstance(entry.get(text_field), str) or not entry[text_field].strip():
            failures.append(f"{entry_id}: {text_field} must be a non-empty string")
    if isinstance(entry.get("policy_ref"), str) and has_temporary_policy_ref(entry["policy_ref"]):
        failures.append(f"{entry_id}: policy_ref must be stable: {entry['policy_ref']}")

    source_refs = entry.get("source_refs")
    if not isinstance(source_refs, list) or not source_refs:
        failures.append(f"{entry_id}: source_refs must be a non-empty list")
    else:
        duplicate_source_refs = sorted({ref for ref in source_refs if source_refs.count(ref) > 1})
        if duplicate_source_refs:
            failures.append(f"{entry_id}: duplicate source_refs: {', '.join(duplicate_source_refs)}")
        for source_ref in source_refs:
            if not isinstance(source_ref, str) or not source_ref.strip():
                failures.append(f"{entry_id}: source_refs entries must be non-empty strings")
                continue
            if not source_ref.startswith(ALLOWED_SOURCE_REF_PREFIXES):
                failures.append(
                    f"{entry_id}: unknown source_ref prefix: {source_ref}. "
                    f"{source_ref_prefix_hint()}"
                )
            if has_temporary_source_ref(source_ref):
                failures.append(f"{entry_id}: source_ref must be stable: {source_ref}")

    fixture_refs = entry.get("fixture_refs")
    if not isinstance(fixture_refs, list) or not fixture_refs:
        failures.append(f"{entry_id}: fixture_refs must be a non-empty list")
    else:
        duplicate_refs = sorted({ref for ref in fixture_refs if fixture_refs.count(ref) > 1})
        if duplicate_refs:
            failures.append(f"{entry_id}: duplicate fixture_refs: {', '.join(duplicate_refs)}")
        unknown_refs = sorted(set(fixture_refs) - fixture_ids)
        if unknown_refs:
            failures.append(f"{entry_id}: unknown fixture_refs: {', '.join(unknown_refs)}")
        temporary_refs = sorted(ref for ref in fixture_refs if has_temporary_fixture_id(str(ref)))
        if temporary_refs:
            failures.append(f"{entry_id}: fixture_refs must be stable: {', '.join(temporary_refs)}")

    line_refs = entry.get("line_refs")
    if not isinstance(line_refs, list) or not line_refs:
        failures.append(f"{entry_id}: line_refs must be a non-empty list")
    else:
        for line_ref in line_refs:
            failures.extend(_validate_line_ref(entry_id, line_ref, repo_root=repo_root))

    if entry.get("status") == "wrapped_adapter":
        adapter_ref = entry.get("adapter_ref")
        adapter_refs = entry.get("adapter_refs")
        has_single_ref = isinstance(adapter_ref, str) and adapter_ref.strip()
        has_ref_list = (
            isinstance(adapter_refs, list)
            and bool(adapter_refs)
            and all(isinstance(ref, str) and ref.strip() for ref in adapter_refs)
        )
        if not has_single_ref and not has_ref_list:
            failures.append(f"{entry_id}: wrapped_adapter requires adapter_ref or adapter_refs")
        if has_single_ref and has_ref_list:
            failures.append(f"{entry_id}: use adapter_ref or adapter_refs, not both")
        if isinstance(adapter_refs, list):
            duplicate_adapter_refs = sorted({ref for ref in adapter_refs if adapter_refs.count(ref) > 1})
            if duplicate_adapter_refs:
                failures.append(f"{entry_id}: duplicate adapter_refs: {', '.join(duplicate_adapter_refs)}")

    return failures


def validate_inventory(
    inventory_payload: list[dict[str, Any]],
    fixture_payloads: list[dict[str, Any]],
    *,
    repo_root: Path = REPO_DIR,
) -> dict[str, Any]:
    fixture_ids = {str(payload["id"]) for payload in fixture_payloads}
    seen_ids: set[str] = set()
    failures = []

    for entry in inventory_payload:
        failures.extend(_validate_entry(entry, fixture_ids, seen_ids, repo_root=repo_root))

    covered_fixture_ids = {
        str(fixture_ref)
        for entry in inventory_payload
        if isinstance(entry, dict)
        for fixture_ref in entry.get("fixture_refs", [])
        if str(fixture_ref) in fixture_ids
    }
    missing_fixture_coverage = sorted(fixture_ids - covered_fixture_ids)
    if missing_fixture_coverage:
        failures.append(
            "missing fixture coverage: "
            + ", ".join(missing_fixture_coverage)
        )

    status_counts = Counter(str(entry.get("status")) for entry in inventory_payload if isinstance(entry, dict))
    kind_counts = Counter(str(entry.get("kind")) for entry in inventory_payload if isinstance(entry, dict))
    risk_counts = Counter(str(entry.get("risk")) for entry in inventory_payload if isinstance(entry, dict))
    source_ref_prefix_counts = Counter(
        str(source_ref).split(":", maxsplit=1)[0]
        for entry in inventory_payload
        if isinstance(entry, dict)
        for source_ref in entry.get("source_refs", [])
        if isinstance(source_ref, str) and ":" in source_ref
    )
    line_refs_total = sum(
        len(entry.get("line_refs", []))
        for entry in inventory_payload
        if isinstance(entry, dict)
        and isinstance(entry.get("line_refs"), list)
    )
    line_ref_anchors_total = sum(
        1
        for entry in inventory_payload
        if isinstance(entry, dict)
        for line_ref in entry.get("line_refs", [])
        if isinstance(line_ref, dict)
        and isinstance(line_ref.get("anchor"), str)
        and line_ref["anchor"].strip()
    )
    line_ref_anchors_in_recorded_range = sum(
        1
        for entry in inventory_payload
        if isinstance(entry, dict)
        for line_ref in entry.get("line_refs", [])
        if _line_ref_anchor_in_recorded_range(line_ref, repo_root=repo_root)
    )
    legacy_rules_total = len(inventory_payload)
    legacy_rules_with_fixture = sum(
        1
        for entry in inventory_payload
        if isinstance(entry, dict)
        and isinstance(entry.get("fixture_refs"), list)
        and bool(entry["fixture_refs"])
    )
    legacy_rules_wrapped_by_match_signals = status_counts.get("wrapped_adapter", 0)
    legacy_rules_marked_for_migration = sum(
        status_counts.get(status, 0)
        for status in MIGRATION_CANDIDATE_STATUSES
    )
    legacy_rules_covered_pct = (
        round((legacy_rules_with_fixture / legacy_rules_total) * 100, 2)
        if legacy_rules_total
        else 0.0
    )

    return {
        "summary": {
            "legacy_rules_total": legacy_rules_total,
            "legacy_rules_with_fixture": legacy_rules_with_fixture,
            "legacy_rules_wrapped_by_match_signals": legacy_rules_wrapped_by_match_signals,
            "legacy_rules_marked_for_migration": legacy_rules_marked_for_migration,
            "legacy_rules_deprecated": status_counts.get("deprecated", 0),
            "legacy_rules_covered_pct": legacy_rules_covered_pct,
            "line_refs_total": line_refs_total,
            "line_ref_anchors_total": line_ref_anchors_total,
            "line_ref_anchors_in_recorded_range": line_ref_anchors_in_recorded_range,
            "line_ref_anchors_outside_recorded_range": (
                line_ref_anchors_total - line_ref_anchors_in_recorded_range
            ),
            "fixtures_total": len(fixture_ids),
            "fixture_refs_covered": len(covered_fixture_ids),
            "fixture_refs_missing": len(missing_fixture_coverage),
            "status_counts": dict(sorted(status_counts.items())),
            "kind_counts": dict(sorted(kind_counts.items())),
            "risk_counts": dict(sorted(risk_counts.items())),
            "source_ref_prefix_counts": dict(sorted(source_ref_prefix_counts.items())),
        },
        "missing_fixture_coverage": missing_fixture_coverage,
        "failures": failures,
    }


def _format_text(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        (
            "matcher rule inventory: "
            f"{summary['legacy_rules_total']} rules, "
            f"{summary['fixture_refs_covered']}/{summary['fixtures_total']} fixtures covered"
        ),
        (
            "legacy rule coverage: "
            f"{summary['legacy_rules_with_fixture']}/{summary['legacy_rules_total']} "
            f"({summary['legacy_rules_covered_pct']}%), "
            f"wrapped={summary['legacy_rules_wrapped_by_match_signals']}, "
            f"marked_for_migration={summary['legacy_rules_marked_for_migration']}, "
            f"deprecated={summary['legacy_rules_deprecated']}"
        ),
        (
            "line ref anchors: "
            f"{summary['line_ref_anchors_total']}/{summary['line_refs_total']}, "
            "recorded range current="
            f"{summary['line_ref_anchors_in_recorded_range']}/{summary['line_refs_total']}"
        ),
        f"status counts: {summary['status_counts']}",
        f"kind counts: {summary['kind_counts']}",
        f"risk counts: {summary['risk_counts']}",
        f"source ref prefixes: {summary['source_ref_prefix_counts']}",
    ]
    for failure in report["failures"]:
        lines.append(f"FAIL {failure}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate matcher rule inventory.")
    parser.add_argument("--inventory-file", default=str(inventory_contract_path()))
    parser.add_argument("--fixture-file", default=str(fixture_contract_path()))
    parser.add_argument("--repo-root", type=Path, default=REPO_DIR)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_inventory(
        load_inventory(Path(args.inventory_file)),
        load_fixture_contract(Path(args.fixture_file)),
        repo_root=args.repo_root,
    )
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_format_text(report))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
