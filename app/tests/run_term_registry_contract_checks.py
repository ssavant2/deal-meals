#!/usr/bin/env python3
"""R0 read-only contract checks for the term registry.

This script does not change matcher runtime behavior, rebuild cache, or touch
the database. It verifies that the Swedish registry view can reproduce the
completed B-track baseline and writes a language-scoped report.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sys
import tomllib
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = APP_DIR.parent
sys.path.insert(0, "/app" if os.path.exists("/app") else str(APP_DIR))

from languages.term_registry.checks import (  # noqa: E402
    check_shared_core_import_boundaries,
    compare_variants_to_baseline,
    summarize_variants,
    validate_entries,
)
from languages.term_registry.models import CheckIssue, RegistryEntry, RegistryVariant  # noqa: E402
from languages.term_registry.reports import write_json_and_markdown_report  # noqa: E402


DEFAULT_VERIFIED_TERMS_BASELINE_JSON = (
    APP_DIR
    / "languages"
    / "sv"
    / "ingredient_matching"
    / "term_registry"
    / "baselines"
    / "verified_matcher_terms.json"
)
DEFAULT_BASELINE_JSON = DEFAULT_VERIFIED_TERMS_BASELINE_JSON
DEFAULT_REPORT_ROOT = APP_DIR / "tests" / "reports" / "term_registry"
DEFAULT_SHARED_REGISTRY_DIR = APP_DIR / "languages" / "term_registry"
DEFAULT_FIXTURE_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"
DEFAULT_INVENTORY_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"
EXPECTED_B2_VARIANT_COUNT = 5475  # updated by tests/promote_term_baseline.py
EXPECTED_B2_LAST_BATCH = "B092"
EXPECTED_B2_BATCH_COUNT = 92
CoverageKey = tuple[str, str, str, str, str, str]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _coverage_key_from_dict(
    payload: dict[str, Any],
    *,
    default_language: str,
    default_market: str,
    default_canonical: str = "",
) -> CoverageKey | None:
    source_family = str(payload.get("source_family") or payload.get("source_type") or "").strip()
    canonical = str(payload.get("canonical") or payload.get("expected_family") or default_canonical).strip()
    variant = str(payload.get("variant") or payload.get("variant_text") or "").strip()
    layer_role = str(payload.get("layer_role") or payload.get("variant_role") or "").strip()
    if not all((source_family, canonical, variant, layer_role)):
        return None
    return (
        str(payload.get("language") or default_language).strip(),
        str(payload.get("market") or default_market).strip(),
        source_family,
        canonical,
        variant,
        layer_role,
    )


def _has_broad_coverage_value(value: str) -> bool:
    return value.strip() in {"", "*", "all", "any"}


def _load_b2_baseline(
    path: Path,
    *,
    language: str,
    market: str,
) -> tuple[dict[str, Any], set[str], set[CoverageKey], list[CheckIssue]]:
    issues: list[CheckIssue] = []
    if not path.exists():
        return {}, set(), set(), [_issue(
            "error",
            "missing_b2_baseline_json",
            "B2 baseline JSON is required before R0 can run",
            item_id=str(path),
            details={
                "hint": (
                    "Recover or regenerate app/languages/sv/ingredient_matching/"
                    "term_registry/baselines/verified_matcher_terms.json "
                    "before running R0."
                )
            },
        )]

    payload = _load_json(path)
    summary = payload.get("summary") or {}
    variants = payload.get("variants") or []
    if not isinstance(variants, list):
        issues.append(_issue(
            "error",
            "invalid_b2_baseline_json",
            "B2 baseline variants payload must be a list",
            item_id=str(path),
        ))
        variants = []

    baseline_ids = {
        str(variant.get("variant_id"))
        for variant in variants
        if isinstance(variant, dict) and variant.get("variant_id")
    }
    baseline_coverage_keys: set[CoverageKey] = set()
    invalid_coverage_rows = []
    for index, variant in enumerate(variants):
        if not isinstance(variant, dict):
            continue
        key = _coverage_key_from_dict(
            variant,
            default_language=language,
            default_market=market,
        )
        if key is None:
            invalid_coverage_rows.append(index)
            continue
        baseline_coverage_keys.add(key)

    variant_count = int(summary.get("variant_count") or 0)
    last_batch_id = str(summary.get("last_batch_id") or "")
    if variant_count != EXPECTED_B2_VARIANT_COUNT:
        issues.append(_issue(
            "error",
            "unexpected_b2_variant_count",
            "B2 baseline variant count does not match the frozen status file",
            item_id=str(path),
            details={"expected": EXPECTED_B2_VARIANT_COUNT, "actual": variant_count},
        ))
    if last_batch_id != EXPECTED_B2_LAST_BATCH:
        issues.append(_issue(
            "error",
            "unexpected_b2_last_batch",
            "B2 baseline last batch does not match the frozen status file",
            item_id=str(path),
            details={"expected": EXPECTED_B2_LAST_BATCH, "actual": last_batch_id},
        ))
    if len(baseline_ids) != variant_count:
        issues.append(_issue(
            "error",
            "b2_baseline_id_count_mismatch",
            "B2 baseline variant ids are missing or duplicated",
            item_id=str(path),
            details={"summary_count": variant_count, "unique_variant_ids": len(baseline_ids)},
        ))
    if invalid_coverage_rows:
        issues.append(_issue(
            "error",
            "b2_baseline_coverage_keys_invalid",
            "B2 baseline rows must provide complete coverage keys",
            item_id=str(path),
            details={
                "unique_coverage_keys": len(baseline_coverage_keys),
                "invalid_row_sample": invalid_coverage_rows[:20],
            },
        ))

    return payload, baseline_ids, baseline_coverage_keys, issues


def _load_verification_summary(
    payload: dict[str, Any],
    *,
    baseline_path: Path,
) -> tuple[dict[str, Any], list[CheckIssue]]:
    issues: list[CheckIssue] = []
    verification = payload.get("verification")
    if not isinstance(verification, dict):
        return {}, [_issue(
            "error",
            "missing_verified_terms_verification_summary",
            "Verified matcher terms baseline must include the final audit summary",
            item_id=str(baseline_path),
        )]

    classification_counts = Counter(verification.get("classification_counts") or {})
    problem_counts = Counter(verification.get("problem_counts") or {})
    status_counts = Counter(verification.get("status_counts") or {})
    source_counts = Counter(verification.get("source_counts") or {})
    variant_count = int(verification.get("variant_count") or 0)
    applied_batch_count = int(verification.get("applied_batch_count") or 0)
    batch_report_count = int(verification.get("batch_report_count") or 0)

    if variant_count != EXPECTED_B2_VARIANT_COUNT:
        issues.append(_issue(
            "error",
            "verified_terms_variant_count_mismatch",
            "Verified matcher terms summary does not cover the frozen baseline",
            item_id=str(baseline_path),
            details={"expected": EXPECTED_B2_VARIANT_COUNT, "actual": variant_count},
        ))
    if batch_report_count != EXPECTED_B2_BATCH_COUNT:
        issues.append(_issue(
            "error",
            "verified_terms_batch_count_mismatch",
            "Verified matcher terms summary does not include every final audit batch",
            item_id=str(baseline_path),
            details={"expected": EXPECTED_B2_BATCH_COUNT, "actual": batch_report_count},
        ))
    if applied_batch_count != EXPECTED_B2_BATCH_COUNT:
        issues.append(_issue(
            "error",
            "verified_terms_applied_batch_count_mismatch",
            "Verified matcher terms summary was not applied for every final audit batch",
            item_id=str(baseline_path),
            details={"expected": EXPECTED_B2_BATCH_COUNT, "actual": applied_batch_count},
        ))
    if str(verification.get("last_batch_id") or "") != EXPECTED_B2_LAST_BATCH:
        issues.append(_issue(
            "error",
            "verified_terms_last_batch_mismatch",
            "Verified matcher terms summary does not end at the frozen final batch",
            item_id=str(baseline_path),
            details={
                "expected": EXPECTED_B2_LAST_BATCH,
                "actual": verification.get("last_batch_id"),
            },
        ))
    if int(status_counts.get("audited") or 0) != EXPECTED_B2_VARIANT_COUNT:
        issues.append(_issue(
            "error",
            "verified_terms_audited_count_mismatch",
            "Verified matcher terms summary does not mark every baseline variant as audited",
            item_id=str(baseline_path),
            details={
                "expected": EXPECTED_B2_VARIANT_COUNT,
                "actual": int(status_counts.get("audited") or 0),
            },
        ))
    if problem_counts:
        issues.append(_issue(
            "error",
            "verified_terms_problem_counts_present",
            "Verified matcher terms summary still contains problem counts",
            item_id=str(baseline_path),
            details={"problem_counts": dict(sorted(problem_counts.items()))},
        ))
    if classification_counts.get("needs_fix", 0):
        issues.append(_issue(
            "error",
            "verified_terms_needs_fix_present",
            "Verified matcher terms summary still contains needs_fix variants",
            item_id=str(baseline_path),
            details={"needs_fix": classification_counts["needs_fix"]},
        ))

    return {
        "method": verification.get("method"),
        "batch_report_count": batch_report_count,
        "applied_batch_count": applied_batch_count,
        "variant_count": variant_count,
        "classification_counts": dict(sorted(classification_counts.items())),
        "problem_counts": dict(sorted(problem_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "first_batch_id": verification.get("first_batch_id"),
        "last_batch_id": verification.get("last_batch_id"),
    }, issues


def _coverage_keys_from_registry_entries(entries: list[RegistryEntry]) -> tuple[set[CoverageKey], list[CheckIssue]]:
    issues: list[CheckIssue] = []
    coverage_keys: set[CoverageKey] = set()
    for entry in entries:
        raw_coverage = (
            entry.language_payload.get("coverage")
            or entry.language_payload.get("legacy_coverage")
            or []
        )
        if not raw_coverage:
            continue
        if not isinstance(raw_coverage, list):
            issues.append(_issue(
                "error",
                "registry_coverage_payload_invalid",
                "registry coverage must be a list of tables",
                item_id=entry.entry_id,
            ))
            continue
        if entry.status != "active":
            continue

        for index, raw_item in enumerate(raw_coverage):
            if not isinstance(raw_item, dict):
                issues.append(_issue(
                    "error",
                    "registry_coverage_row_invalid",
                    "registry coverage rows must be tables",
                    item_id=entry.entry_id,
                    details={"index": index},
                ))
                continue
            key = _coverage_key_from_dict(
                raw_item,
                default_language=entry.language,
                default_market=entry.market,
                default_canonical=entry.canonical,
            )
            if key is None:
                issues.append(_issue(
                    "error",
                    "registry_coverage_key_incomplete",
                    "registry coverage rows require source_family, variant, and layer_role",
                    item_id=entry.entry_id,
                    details={"index": index, "row": raw_item},
                ))
                continue
            if any(_has_broad_coverage_value(value) for value in key[2:]):
                issues.append(_issue(
                    "error",
                    "registry_coverage_key_too_broad",
                    "registry coverage keys must be exact and may not use broad wildcards",
                    item_id=entry.entry_id,
                    details={"index": index, "coverage_key": _coverage_key_to_dict(key)},
                ))
                continue
            coverage_keys.add(key)
    return coverage_keys, issues


def _migration_exception_path(language: str) -> Path:
    if language != "sv":
        raise ValueError("R4 currently supports --language sv only")
    return (
        APP_DIR
        / "languages"
        / "sv"
        / "ingredient_matching"
        / "term_registry"
        / "migration_exceptions.toml"
    )


def _load_migration_exceptions(path: Path, *, language: str, market: str) -> tuple[set[CoverageKey], list[CheckIssue], list[dict[str, Any]]]:
    issues: list[CheckIssue] = []
    if not path.exists():
        return set(), [_issue(
            "error",
            "migration_exceptions_file_missing",
            "R4 requires an explicit migration_exceptions.toml file",
            item_id=str(path),
        )], []

    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    raw_exceptions = payload.get("exceptions", [])
    if raw_exceptions is None:
        raw_exceptions = []
    if not isinstance(raw_exceptions, list):
        return set(), [_issue(
            "error",
            "migration_exceptions_payload_invalid",
            "migration exceptions must be an array of tables",
            item_id=str(path),
        )], []

    today = datetime.now(timezone.utc).date()
    seen_ids: set[str] = set()
    coverage_keys: set[CoverageKey] = set()
    exceptions: list[dict[str, Any]] = []
    required = (
        "id",
        "owner",
        "source_family",
        "canonical",
        "variant",
        "layer_role",
        "reason",
        "created_at",
        "expires_when",
    )

    for index, raw_item in enumerate(raw_exceptions):
        if not isinstance(raw_item, dict):
            issues.append(_issue(
                "error",
                "migration_exception_row_invalid",
                "migration exception rows must be tables",
                item_id=str(path),
                details={"index": index},
            ))
            continue

        exception_id = str(raw_item.get("id") or "").strip()
        item_id = exception_id or f"{path}#{index}"
        missing = [field for field in required if not str(raw_item.get(field) or "").strip()]
        if missing:
            issues.append(_issue(
                "error",
                "migration_exception_missing_fields",
                "migration exceptions require exact ownership, coverage, reason, and expiry fields",
                item_id=item_id,
                details={"missing": missing},
            ))
            continue
        if exception_id in seen_ids:
            issues.append(_issue(
                "error",
                "migration_exception_duplicate_id",
                "migration exception id is duplicated",
                item_id=item_id,
            ))
        seen_ids.add(exception_id)

        key = _coverage_key_from_dict(
            raw_item,
            default_language=language,
            default_market=market,
        )
        if key is None:
            issues.append(_issue(
                "error",
                "migration_exception_coverage_key_incomplete",
                "migration exception coverage key is incomplete",
                item_id=item_id,
            ))
            continue
        if any(_has_broad_coverage_value(value) for value in key[2:]):
            issues.append(_issue(
                "error",
                "migration_exception_too_broad",
                "migration exceptions must cover exactly one source family/variant/layer",
                item_id=item_id,
                details={"coverage_key": _coverage_key_to_dict(key)},
            ))
            continue

        expires_on = raw_item.get("expires_on")
        if expires_on:
            if isinstance(expires_on, date):
                expires_on_date = expires_on
            else:
                try:
                    expires_on_date = date.fromisoformat(str(expires_on))
                except ValueError:
                    issues.append(_issue(
                        "error",
                        "migration_exception_invalid_expires_on",
                        "expires_on must use YYYY-MM-DD when present",
                        item_id=item_id,
                        details={"expires_on": str(expires_on)},
                    ))
                    continue
            if expires_on_date < today:
                issues.append(_issue(
                    "error",
                    "migration_exception_expired",
                    "migration exception has passed its expires_on date",
                    item_id=item_id,
                    details={"expires_on": expires_on_date.isoformat(), "today": today.isoformat()},
                ))

        coverage_keys.add(key)
        exceptions.append({"id": exception_id, "coverage_key": key, "raw": raw_item})

    return coverage_keys, issues, exceptions


def _load_registry_source_ref_indexes(language: str) -> dict[str, set[str]]:
    if language != "sv":
        return {}
    fixture_payloads = _load_json(DEFAULT_FIXTURE_FILE)
    inventory_payloads = _load_json(DEFAULT_INVENTORY_FILE)
    from languages.sv.ingredient_matching.match_bridges import MATCH_BRIDGES  # noqa: PLC0415
    from languages.sv.ingredient_matching.no_match_policies import NO_MATCH_POLICIES  # noqa: PLC0415

    return {
        "fixture:matcher_regression_cases": {
            str(payload.get("id"))
            for payload in fixture_payloads
            if isinstance(payload, dict) and payload.get("id")
        },
        "inventory:matcher_rule_inventory": {
            str(payload.get("id"))
            for payload in inventory_payloads
            if isinstance(payload, dict) and payload.get("id")
        },
        "bridge:match_bridges": {bridge.id for bridge in MATCH_BRIDGES},
        "policy:no_match_policies": {policy.id for policy in NO_MATCH_POLICIES},
    }


def _check_registry_source_refs(entries: list[RegistryEntry], *, language: str) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    if not entries:
        return issues
    indexes = _load_registry_source_ref_indexes(language)
    for entry in entries:
        for source_ref in entry.source_refs:
            parts = source_ref.split(":", 2)
            if len(parts) < 3:
                continue
            collection_key = f"{parts[0]}:{parts[1]}"
            if collection_key not in indexes:
                continue
            item_id = parts[2]
            if item_id not in indexes[collection_key]:
                issues.append(_issue(
                    "error",
                    "registry_source_ref_missing",
                    "registry entry source_ref points to a source that no longer exists",
                    item_id=entry.entry_id,
                    details={"source_ref": source_ref},
                ))
    return issues


def _run_new_term_gate(
    *,
    variants: list[RegistryVariant],
    baseline_coverage_keys: set[CoverageKey],
    registry_coverage_keys: set[CoverageKey],
    exception_coverage_keys: set[CoverageKey],
    migration_exceptions: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[CheckIssue]]:
    issues: list[CheckIssue] = []
    current_keys = {variant.coverage_key for variant in variants}
    current_variant_by_key = {variant.coverage_key: variant for variant in variants}
    new_keys = current_keys - baseline_coverage_keys
    covered_by_registry = new_keys & registry_coverage_keys
    covered_by_exception = new_keys & exception_coverage_keys
    uncovered = sorted(new_keys - registry_coverage_keys - exception_coverage_keys)

    if uncovered:
        sample = []
        for key in uncovered[:20]:
            variant = current_variant_by_key[key]
            sample.append({
                **_coverage_key_to_dict(key),
                "source_file": variant.source_file,
                "source_refs": list(variant.source_refs),
            })
        issues.append(_issue(
            "error",
            "new_legacy_term_missing_registry",
            "new legacy matcher terms must be added to TOML registry coverage or migration_exceptions.toml",
            details={
                "count": len(uncovered),
                "sample": sample,
                "hint": (
                    "Add an exact [[coverage]] row to a registry TOML entry, or add one narrow "
                    "[[exceptions]] row with owner/reason/expires_when."
                ),
            },
        ))

    probe_language = variants[0].language if variants else "sv"
    probe_market = variants[0].market if variants else "SE"
    probe_key: CoverageKey = (
        probe_language,
        probe_market,
        "r4_failure_probe",
        "r4_failure_probe",
        "r4 failure probe",
        "r4_failure_probe_layer",
    )
    probe_uncovered = (
        (current_keys | {probe_key})
        - baseline_coverage_keys
        - registry_coverage_keys
        - exception_coverage_keys
    )
    failure_probe_passed = probe_key in probe_uncovered
    if not failure_probe_passed:
        issues.append(_issue(
            "error",
            "new_term_gate_failure_probe_failed",
            "R4 failure probe did not detect an uncovered synthetic legacy key",
            details={"coverage_key": _coverage_key_to_dict(probe_key)},
        ))

    stale_registry_keys = sorted(registry_coverage_keys - current_keys)
    if stale_registry_keys:
        issues.append(_issue(
            "error",
            "registry_coverage_key_not_in_current_legacy",
            "active registry coverage claims legacy keys that do not exist in current matcher sources",
            details={
                "count": len(stale_registry_keys),
                "sample": [_coverage_key_to_dict(key) for key in stale_registry_keys[:20]],
            },
        ))

    exception_ids_by_key = {
        item["coverage_key"]: item["id"]
        for item in migration_exceptions
        if item.get("coverage_key")
    }
    for key in sorted(exception_coverage_keys - current_keys):
        issues.append(_issue(
            "error",
            "migration_exception_stale",
            "migration exception covers a legacy key that no longer exists",
            item_id=exception_ids_by_key.get(key, ""),
            details={"coverage_key": _coverage_key_to_dict(key)},
        ))
    for key in sorted(exception_coverage_keys & baseline_coverage_keys):
        issues.append(_issue(
            "error",
            "migration_exception_covers_b2_baseline",
            "migration exception is unnecessary because this key is already in the B2 baseline",
            item_id=exception_ids_by_key.get(key, ""),
            details={"coverage_key": _coverage_key_to_dict(key)},
        ))
    for key in sorted(exception_coverage_keys & registry_coverage_keys):
        issues.append(_issue(
            "error",
            "migration_exception_covers_registry_key",
            "migration exception is stale because an active registry entry covers the same key",
            item_id=exception_ids_by_key.get(key, ""),
            details={"coverage_key": _coverage_key_to_dict(key)},
        ))

    summary = {
        "enabled": True,
        "current_legacy_coverage_keys": len(current_keys),
        "b2_grandfathered_coverage_keys": len(baseline_coverage_keys & current_keys),
        "new_legacy_coverage_keys": len(new_keys),
        "new_keys_covered_by_registry": len(covered_by_registry),
        "new_keys_covered_by_migration_exception": len(covered_by_exception),
        "new_keys_uncovered": len(uncovered),
        "active_registry_coverage_keys": len(registry_coverage_keys),
        "migration_exception_coverage_keys": len(exception_coverage_keys),
        "failure_probe_passed": failure_probe_passed,
        "failure_probe_error_code": "new_legacy_term_missing_registry",
    }
    return summary, issues


def _load_language(language: str):
    if language != "sv":
        raise ValueError("R0/R4 currently supports --language sv only")
    from languages.sv.ingredient_matching.term_registry.legacy_inventory import (  # noqa: PLC0415
        build_legacy_registry_variants,
    )
    from languages.sv.ingredient_matching.term_registry.registry import (  # noqa: PLC0415
        load_registry_entries,
    )

    return build_legacy_registry_variants, load_registry_entries


def run_checks(args: argparse.Namespace) -> tuple[dict[str, Any], list[CheckIssue]]:
    issues: list[CheckIssue] = []
    build_legacy_registry_variants, load_registry_entries = _load_language(args.language)

    entries = load_registry_entries()
    issues.extend(validate_entries(entries))
    registry_coverage_keys, registry_coverage_issues = _coverage_keys_from_registry_entries(entries)
    issues.extend(registry_coverage_issues)
    issues.extend(_check_registry_source_refs(entries, language=args.language))

    variants = build_legacy_registry_variants(batch_size=args.batch_size)
    baseline_payload, baseline_ids, baseline_coverage_keys, baseline_issues = _load_b2_baseline(
        args.baseline_json,
        language=args.language,
        market=args.market,
    )
    issues.extend(baseline_issues)
    if baseline_ids:
        issues.extend(compare_variants_to_baseline(variants, baseline_ids))
    exception_path = _migration_exception_path(args.language)
    exception_coverage_keys, exception_issues, migration_exceptions = _load_migration_exceptions(
        exception_path,
        language=args.language,
        market=args.market,
    )
    issues.extend(exception_issues)
    if baseline_coverage_keys:
        new_term_gate_summary, new_term_gate_issues = _run_new_term_gate(
            variants=variants,
            baseline_coverage_keys=baseline_coverage_keys,
            registry_coverage_keys=registry_coverage_keys,
            exception_coverage_keys=exception_coverage_keys,
            migration_exceptions=migration_exceptions,
        )
        issues.extend(new_term_gate_issues)
    else:
        new_term_gate_summary = {"enabled": False, "reason": "missing B2 baseline coverage keys"}

    verification_summary, verification_issues = _load_verification_summary(
        baseline_payload,
        baseline_path=args.baseline_json,
    )
    issues.extend(verification_issues)
    issues.extend(check_shared_core_import_boundaries(args.shared_registry_dir))

    issue_counts = Counter(issue.severity for issue in issues)
    summary = {
        "language": args.language,
        "market": args.market,
        "authored_entry_count": len(entries),
        "active_registry_coverage_key_count": len(registry_coverage_keys),
        "legacy_registry_view": summarize_variants(variants),
        "baseline_variant_count": len(baseline_ids),
        "baseline_coverage_key_count": len(baseline_coverage_keys),
        "b2_expected_variant_count": EXPECTED_B2_VARIANT_COUNT,
        "b2_baseline_file": str(args.baseline_json.relative_to(REPO_DIR)),
        "verified_terms_summary": verification_summary,
        "new_term_gate": new_term_gate_summary,
        "migration_exceptions_file": str(exception_path.relative_to(REPO_DIR)),
        "issue_counts": dict(sorted(issue_counts.items())),
        "passed": not any(issue.severity == "error" for issue in issues),
    }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "findings": [issue.to_dict() for issue in issues],
        "baseline_summary": baseline_payload.get("summary", {}),
        "sample_variants": [variant.to_dict() for variant in variants[:20]],
    }
    return payload, issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", default="sv")
    parser.add_argument("--market", default="SE")
    parser.add_argument("--batch-size", type=int, default=60)
    parser.add_argument("--baseline-json", type=Path, default=DEFAULT_BASELINE_JSON)
    parser.add_argument("--shared-registry-dir", type=Path, default=DEFAULT_SHARED_REGISTRY_DIR)
    parser.add_argument("--report-dir", type=Path, default=None)
    args = parser.parse_args()

    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")

    if args.report_dir is None:
        args.report_dir = DEFAULT_REPORT_ROOT / args.language

    payload, issues = run_checks(args)
    json_report_path = args.report_dir / "term_registry_contract_report.json"
    md_report_path = args.report_dir / "term_registry_contract_report.md"
    payload["summary"]["reports"] = [
        str(json_report_path.relative_to(REPO_DIR)),
        str(md_report_path.relative_to(REPO_DIR)),
    ]
    json_path, md_path = write_json_and_markdown_report(
        report_dir=args.report_dir,
        stem="term_registry_contract_report",
        payload=payload,
        title="Term Registry Contract Report",
    )
    assert json_path == json_report_path and md_path == md_report_path

    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if any(issue.severity == "error" for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
