"""Build export/add-term plans from registry entries.

This module is shared and intentionally language-neutral. A language package
supplies the known export layer specs; the shared logic validates registry
coverage rows against those specs and reports whether a manual entry has enough
structure to participate in the add-a-term workflow.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .models import CheckIssue, RegistryEntry


@dataclass(frozen=True)
class ExportLayerSpec:
    source_family: str
    layer_role: str
    export_name: str
    export_kind: str
    runtime: bool = True
    description: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.source_family, self.layer_role)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CoverageExportRow:
    entry_id: str
    language: str
    market: str
    source_family: str
    canonical: str
    variant: str
    layer_role: str
    export_name: str
    export_kind: str
    runtime: bool

    @property
    def coverage_key(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.language,
            self.market,
            self.source_family,
            self.canonical,
            self.variant,
            self.layer_role,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["coverage_key"] = list(self.coverage_key)
        return payload


def _issue(
    severity: str,
    code: str,
    message: str,
    *,
    item_id: str = "",
    details: dict[str, Any] | None = None,
) -> CheckIssue:
    return CheckIssue(
        severity=severity,
        code=code,
        message=message,
        item_id=item_id,
        details=details or {},
    )


def _raw_coverage(entry: RegistryEntry) -> list[Any]:
    rows = (
        entry.language_payload.get("coverage")
        or entry.language_payload.get("legacy_coverage")
        or []
    )
    if isinstance(rows, list):
        return rows
    return [rows]


def _is_manual_entry(entry: RegistryEntry) -> bool:
    return any(source_ref.startswith("manual:") for source_ref in entry.source_refs)


def _coverage_row_from_payload(
    *,
    entry: RegistryEntry,
    raw_row: dict[str, Any],
    spec: ExportLayerSpec,
) -> CoverageExportRow | None:
    source_family = str(raw_row.get("source_family") or raw_row.get("source_type") or "").strip()
    layer_role = str(raw_row.get("layer_role") or raw_row.get("variant_role") or "").strip()
    canonical = str(raw_row.get("canonical") or raw_row.get("expected_family") or entry.canonical).strip()
    variant = str(raw_row.get("variant") or raw_row.get("variant_text") or "").strip()
    if not all((source_family, canonical, variant, layer_role)):
        return None
    return CoverageExportRow(
        entry_id=entry.entry_id,
        language=str(raw_row.get("language") or entry.language).strip(),
        market=str(raw_row.get("market") or entry.market).strip(),
        source_family=source_family,
        canonical=canonical,
        variant=variant,
        layer_role=layer_role,
        export_name=spec.export_name,
        export_kind=spec.export_kind,
        runtime=spec.runtime,
    )


def build_registry_export_plan(
    entries: Iterable[RegistryEntry],
    *,
    specs: Iterable[ExportLayerSpec],
    language: str,
    market: str,
) -> tuple[dict[str, Any], list[CheckIssue]]:
    """Return an add-term/export plan for entries in one language/market."""

    spec_by_key = {spec.key: spec for spec in specs}
    issues: list[CheckIssue] = []
    rows: list[CoverageExportRow] = []
    entries_seen = 0
    manual_entries = 0
    entries_with_coverage = 0

    for entry in entries:
        if entry.language != language or entry.market != market:
            continue
        entries_seen += 1
        raw_rows = _raw_coverage(entry)
        valid_rows_for_entry = 0
        manual = _is_manual_entry(entry)
        if manual:
            manual_entries += 1

        if manual and entry.status == "active":
            if not raw_rows:
                issues.append(_issue(
                    "error",
                    "manual_entry_missing_coverage",
                    "manual active registry entries must declare exact coverage rows",
                    item_id=entry.entry_id,
                ))
            if "negative_guard_only" in entry.layer_policy:
                if not entry.negative_examples and not entry.negative_guards:
                    issues.append(_issue(
                        "error",
                        "manual_negative_entry_missing_guard_proof",
                        "manual negative guard entries need a negative example or negative_guards",
                        item_id=entry.entry_id,
                    ))
            elif not entry.positive_examples:
                issues.append(_issue(
                    "error",
                    "manual_entry_missing_positive_example",
                    "manual active registry entries need at least one positive example",
                    item_id=entry.entry_id,
                ))

        for index, raw_row in enumerate(raw_rows):
            if not isinstance(raw_row, dict):
                issues.append(_issue(
                    "error",
                    "coverage_row_invalid",
                    "coverage rows must be tables",
                    item_id=entry.entry_id,
                    details={"index": index},
                ))
                continue
            source_family = str(raw_row.get("source_family") or raw_row.get("source_type") or "").strip()
            layer_role = str(raw_row.get("layer_role") or raw_row.get("variant_role") or "").strip()
            spec = spec_by_key.get((source_family, layer_role))
            if spec is None:
                issues.append(_issue(
                    "error",
                    "coverage_export_spec_missing",
                    "coverage row does not map to a known export/add-term layer",
                    item_id=entry.entry_id,
                    details={
                        "index": index,
                        "source_family": source_family,
                        "layer_role": layer_role,
                    },
                ))
                continue
            row = _coverage_row_from_payload(entry=entry, raw_row=raw_row, spec=spec)
            if row is None:
                issues.append(_issue(
                    "error",
                    "coverage_row_incomplete",
                    "coverage rows require source_family, canonical, variant, and layer_role",
                    item_id=entry.entry_id,
                    details={"index": index, "row": raw_row},
                ))
                continue
            rows.append(row)
            valid_rows_for_entry += 1

        if valid_rows_for_entry:
            entries_with_coverage += 1

    row_counts = Counter(row.export_name for row in rows)
    runtime_row_counts = Counter(row.export_name for row in rows if row.runtime)
    audit_row_counts = Counter(row.export_name for row in rows if not row.runtime)
    unique_keys = {row.coverage_key for row in rows}
    issue_counts = Counter(issue.severity for issue in issues)
    summary = {
        "language": language,
        "market": market,
        "entry_count": entries_seen,
        "manual_entry_count": manual_entries,
        "entries_with_coverage": entries_with_coverage,
        "coverage_row_count": len(rows),
        "unique_coverage_key_count": len(unique_keys),
        "runtime_coverage_row_count": sum(runtime_row_counts.values()),
        "audit_coverage_row_count": sum(audit_row_counts.values()),
        "known_export_layer_count": len(spec_by_key),
        "export_counts": dict(sorted(row_counts.items())),
        "runtime_export_counts": dict(sorted(runtime_row_counts.items())),
        "audit_export_counts": dict(sorted(audit_row_counts.items())),
        "issue_counts": dict(sorted(issue_counts.items())),
        "passed": not any(issue.severity == "error" for issue in issues),
    }
    payload = {
        "summary": summary,
        "specs": [spec.to_dict() for spec in sorted(spec_by_key.values(), key=lambda item: item.key)],
        "coverage_rows": [row.to_dict() for row in rows],
        "findings": [issue.to_dict() for issue in issues],
    }
    return payload, issues
