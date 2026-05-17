#!/usr/bin/env python3
"""Validate registry add-a-term/export planning.

The check does not edit matcher files, rebuild cache, or touch the database.
It proves that every authored coverage row maps to a known language/market
export layer and that manual add-term entries get actionable errors when they
omit coverage or examples.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = APP_DIR.parent
sys.path.insert(0, "/app" if os.path.exists("/app") else str(APP_DIR))
os.environ.setdefault("TERM_REGISTRY_DISABLE_LOCAL_ENTRIES", "1")

from languages.term_registry.models import CheckIssue, RegistryEntry, RegistryExample  # noqa: E402
from languages.term_registry.reports import write_json_and_markdown_report  # noqa: E402
from languages.sv.ingredient_matching.term_registry.add_term import (  # noqa: E402
    SV_EXPORT_LAYER_SPECS,
    build_add_term_export_plan,
)


DEFAULT_REPORT_ROOT = (
    Path(os.environ.get("DEAL_MEALS_SUPPORT_REPORT_ROOT", "/tmp/deal-meals-support-checks"))
    / "term_registry"
)
EXPECTED_VERIFIED_TERM_UNIQUE_COVERAGE_KEYS = 5382
EXPECTED_SV_EXPORT_LAYER_COUNT = len(SV_EXPORT_LAYER_SPECS)


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


def _manual_entry(
    *,
    entry_id: str = "sv-se.alias.tomkha.tom_gai_soup",
    coverage: list[dict[str, Any]] | None = None,
    positive_examples: tuple[RegistryExample, ...] = (),
    negative_examples: tuple[RegistryExample, ...] = (),
    negative_guards: tuple[str, ...] = (),
    layer_policy: tuple[str, ...] = ("offer_alias", "existing_canonical"),
) -> RegistryEntry:
    return RegistryEntry(
        entry_id=entry_id,
        language="sv",
        market="SE",
        canonical="tomkha",
        status="active",
        variants=("tom gai soup",),
        ingredient_terms=("tomkha",),
        offer_terms=("tom gai soup",),
        route_terms=("tomkha",),
        final_match_terms=("tomkha",),
        negative_guards=negative_guards,
        source_refs=("manual:test:2026-05-12",),
        layer_policy=layer_policy,
        positive_examples=positive_examples,
        negative_examples=negative_examples,
        notes="Synthetic add-term check entry.",
        language_payload={"coverage": coverage or []},
    )


def _positive_example() -> RegistryExample:
    return RegistryExample(
        ingredient="1 påse tom kha kryddmix",
        offer_name="Tom Gai Soup",
        offer_category="pantry",
        expected=1,
    )


def _run_failure_probes() -> list[CheckIssue]:
    issues: list[CheckIssue] = []

    missing_coverage_entry = _manual_entry(positive_examples=(_positive_example(),))
    _, missing_coverage_issues = build_add_term_export_plan(entries=[missing_coverage_entry])
    missing_coverage_codes = {issue.code for issue in missing_coverage_issues}
    if "manual_entry_missing_coverage" not in missing_coverage_codes:
        issues.append(_issue(
            "error",
            "add_term_missing_coverage_probe_failed",
            "manual entry without coverage did not fail with manual_entry_missing_coverage",
            details={"codes": sorted(missing_coverage_codes)},
        ))

    unknown_layer_entry = _manual_entry(
        coverage=[{
            "source_family": "unknown_family",
            "canonical": "tomkha",
            "variant": "tom gai soup",
            "layer_role": "unknown_layer",
        }],
        positive_examples=(_positive_example(),),
    )
    _, unknown_layer_issues = build_add_term_export_plan(entries=[unknown_layer_entry])
    unknown_layer_codes = {issue.code for issue in unknown_layer_issues}
    if "coverage_export_spec_missing" not in unknown_layer_codes:
        issues.append(_issue(
            "error",
            "add_term_unknown_layer_probe_failed",
            "unknown coverage layer did not fail with coverage_export_spec_missing",
            details={"codes": sorted(unknown_layer_codes)},
        ))

    missing_example_entry = _manual_entry(
        coverage=[{
            "source_family": "keyword_synonym",
            "canonical": "tomkha",
            "variant": "tom gai soup",
            "layer_role": "keyword_synonym_mapping",
        }],
    )
    _, missing_example_issues = build_add_term_export_plan(entries=[missing_example_entry])
    missing_example_codes = {issue.code for issue in missing_example_issues}
    if "manual_entry_missing_positive_example" not in missing_example_codes:
        issues.append(_issue(
            "error",
            "add_term_missing_example_probe_failed",
            "manual entry without a positive example did not fail clearly",
            details={"codes": sorted(missing_example_codes)},
        ))

    valid_entry = _manual_entry(
        coverage=[{
            "source_family": "keyword_synonym",
            "canonical": "tomkha",
            "variant": "tom gai soup",
            "layer_role": "keyword_synonym_mapping",
        }],
        positive_examples=(_positive_example(),),
    )
    valid_payload, valid_issues = build_add_term_export_plan(entries=[valid_entry])
    valid_error_codes = [issue.code for issue in valid_issues if issue.severity == "error"]
    if valid_error_codes:
        issues.append(_issue(
            "error",
            "add_term_valid_entry_probe_failed",
            "valid manual add-term entry failed export planning",
            details={"codes": valid_error_codes},
        ))
    export_counts = valid_payload["summary"].get("runtime_export_counts", {})
    if export_counts.get("KEYWORD_SYNONYMS") != 1:
        issues.append(_issue(
            "error",
            "add_term_valid_entry_export_probe_failed",
            "valid manual add-term entry did not produce the expected export preview",
            details={"runtime_export_counts": export_counts},
        ))

    return issues


def run_checks(args: argparse.Namespace) -> tuple[dict[str, Any], list[CheckIssue]]:
    if args.language != "sv" or args.market != "SE":
        raise ValueError("add-term checks currently support --language sv --market SE")

    payload, issues = build_add_term_export_plan(language=args.language, market=args.market)
    issues.extend(_run_failure_probes())

    summary = dict(payload["summary"])
    if summary.get("unique_coverage_key_count") != EXPECTED_VERIFIED_TERM_UNIQUE_COVERAGE_KEYS:
        issues.append(_issue(
            "error",
            "add_term_coverage_key_count_mismatch",
            "registry add-term coverage should cover the full verified-term unique key surface",
            details={
                "expected": EXPECTED_VERIFIED_TERM_UNIQUE_COVERAGE_KEYS,
                "actual": summary.get("unique_coverage_key_count"),
            },
        ))
    if summary.get("known_export_layer_count") != EXPECTED_SV_EXPORT_LAYER_COUNT:
        issues.append(_issue(
            "error",
            "add_term_export_layer_count_mismatch",
            "Swedish export/add-term spec count changed unexpectedly",
            details={
                "expected": EXPECTED_SV_EXPORT_LAYER_COUNT,
                "actual": summary.get("known_export_layer_count"),
            },
        ))

    issue_counts = Counter(issue.severity for issue in issues)
    summary["issue_counts"] = dict(sorted(issue_counts.items()))
    summary["passed"] = not any(issue.severity == "error" for issue in issues)
    payload = {
        **payload,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "findings": [issue.to_dict() for issue in issues],
    }
    return payload, issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", default="sv")
    parser.add_argument("--market", default="SE")
    parser.add_argument("--report-dir", type=Path, default=None)
    args = parser.parse_args()

    if args.report_dir is None:
        args.report_dir = DEFAULT_REPORT_ROOT / args.language

    payload, issues = run_checks(args)
    json_report_path = args.report_dir / "term_registry_add_term_report.json"
    md_report_path = args.report_dir / "term_registry_add_term_report.md"
    payload["summary"]["reports"] = [
        str(json_report_path.relative_to(REPO_DIR)),
        str(md_report_path.relative_to(REPO_DIR)),
    ]
    json_path, md_path = write_json_and_markdown_report(
        report_dir=args.report_dir,
        stem="term_registry_add_term_report",
        payload=payload,
        title="Term Registry Add-Term Export Report",
    )
    assert json_path == json_report_path and md_path == md_report_path

    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if any(issue.severity == "error" for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
