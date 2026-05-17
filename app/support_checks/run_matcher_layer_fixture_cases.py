#!/usr/bin/env python3
"""Run matcher-layer decision fixtures through read-only diagnostics."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import sys
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, "/app" if os.path.exists("/app") else str(APP_DIR))

from support_checks.matcher_layer_diagnostics import (  # noqa: E402
    DiagnosticCase,
    check_cache_freshness,
    diagnose_case,
)


DEFAULT_FIXTURE_FILE = (
    APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"
)

ALLOWED_SOURCE_REF_PREFIXES = (
    "current_review:",
    "legacy_review:",
    "manual:",
    "plan_initial:",
    "sanity:",
)
ALLOWED_SOURCE_REF_PREFIXES_TEXT = ", ".join(ALLOWED_SOURCE_REF_PREFIXES)
TEMPORARY_POLICY_REF_RE = re.compile(r"^(?:batch\d+(?:_\d+)?|legacy_questions_old(?:_|:).*)$")
TEMPORARY_FIXTURE_ID_RE = re.compile(r"^(?:batch\d+(?:_\d+)?_|legacy_old_batch)")
TEMPORARY_SOURCE_REF_RE = re.compile(
    r"^(?:current_queue:batch|legacy_import:old_review:|legacy_questions_old:|sanity:batch)"
)


def has_temporary_policy_ref(policy_ref: str) -> bool:
    return bool(TEMPORARY_POLICY_REF_RE.fullmatch(policy_ref))


def has_temporary_fixture_id(fixture_id: str) -> bool:
    return bool(TEMPORARY_FIXTURE_ID_RE.match(fixture_id))


def has_temporary_source_ref(source_ref: str) -> bool:
    return bool(TEMPORARY_SOURCE_REF_RE.match(source_ref))


def source_ref_prefix_hint() -> str:
    return f"Allowed: {ALLOWED_SOURCE_REF_PREFIXES_TEXT}"


def _load_fixture_payload(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError(f"fixture file must contain a list: {path}")
    return payload


def _diagnostic_case_from_fixture(payload: dict[str, Any]) -> DiagnosticCase:
    offer_payload = payload.get("offer") or {}
    ingredients = payload.get("ingredients") or []
    return DiagnosticCase(
        case_id=str(payload["id"]),
        recipe_name=str(payload.get("recipe_name") or "Sanity Recipe"),
        ingredients=tuple(str(ingredient) for ingredient in ingredients),
        offer_name=str(offer_payload["name"]),
        offer_category=str(offer_payload.get("category") or ""),
        offer_brand=str(offer_payload.get("brand") or ""),
        expected=int(payload["expected"]),
    )


def _validate_fixture_payload(payload: dict[str, Any]) -> None:
    required = ("id", "policy_ref", "source_ref", "ingredients", "offer", "expected")
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"fixture {payload.get('id', '<unknown>')} missing fields: {', '.join(missing)}")
    for text_field in ("id", "policy_ref", "source_ref"):
        if not isinstance(payload[text_field], str) or not payload[text_field].strip():
            raise ValueError(f"fixture {payload.get('id', '<unknown>')} {text_field} must be a non-empty string")
    if has_temporary_fixture_id(payload["id"]):
        raise ValueError(f"fixture {payload['id']} id must be stable")
    if has_temporary_policy_ref(payload["policy_ref"]):
        raise ValueError(f"fixture {payload['id']} policy_ref must be stable: {payload['policy_ref']}")
    if has_temporary_source_ref(payload["source_ref"]):
        raise ValueError(f"fixture {payload['id']} source_ref must be stable: {payload['source_ref']}")
    if not payload["source_ref"].startswith(ALLOWED_SOURCE_REF_PREFIXES):
        raise ValueError(
            f"fixture {payload['id']} source_ref has unknown prefix: "
            f"{payload['source_ref']}. {source_ref_prefix_hint()}"
        )
    if not isinstance(payload["ingredients"], list) or not payload["ingredients"]:
        raise ValueError(f"fixture {payload['id']} requires a non-empty ingredients list")
    if payload["expected"] not in (0, 1):
        raise ValueError(f"fixture {payload['id']} expected must be 0 or 1")
    offer_payload = payload["offer"]
    if not isinstance(offer_payload, dict) or not offer_payload.get("name"):
        raise ValueError(f"fixture {payload['id']} requires offer.name")
    expected_matches = payload.get("expected_matches")
    if expected_matches is not None:
        if payload["expected"] == 0 and expected_matches:
            raise ValueError(f"fixture {payload['id']} cannot define expected_matches for expected=0")
        if not isinstance(expected_matches, list):
            raise ValueError(f"fixture {payload['id']} expected_matches must be a list")
        for expected_match in expected_matches:
            if not isinstance(expected_match, dict):
                raise ValueError(f"fixture {payload['id']} expected_matches entries must be objects")
            if "ingredient_index" not in expected_match or "canonical" not in expected_match:
                raise ValueError(
                    f"fixture {payload['id']} expected_matches require ingredient_index and canonical"
                )
    allowed_additional = payload.get("allowed_additional_matches")
    if allowed_additional is not None:
        if not isinstance(allowed_additional, dict):
            raise ValueError(f"fixture {payload['id']} allowed_additional_matches must be structured")
        if "max_extra_matches" not in allowed_additional:
            raise ValueError(f"fixture {payload['id']} allowed_additional_matches requires max_extra_matches")
        if int(allowed_additional["max_extra_matches"]) < 0:
            raise ValueError(f"fixture {payload['id']} max_extra_matches must be non-negative")
        if not isinstance(allowed_additional.get("reason"), str) or not allowed_additional["reason"].strip():
            raise ValueError(f"fixture {payload['id']} allowed_additional_matches requires reason")
        allowed_canonicals = allowed_additional.get("allowed_canonicals")
        if not isinstance(allowed_canonicals, list) or not allowed_canonicals:
            raise ValueError(f"fixture {payload['id']} allowed_additional_matches requires allowed_canonicals")
        for canonical in allowed_canonicals:
            if not isinstance(canonical, str) or not canonical.strip():
                raise ValueError(f"fixture {payload['id']} allowed_canonicals entries must be non-empty strings")
        forbidden_canonicals = allowed_additional.get("forbidden_canonicals", [])
        if not isinstance(forbidden_canonicals, list):
            raise ValueError(f"fixture {payload['id']} forbidden_canonicals must be a list")
        for canonical in forbidden_canonicals:
            if not isinstance(canonical, str) or not canonical.strip():
                raise ValueError(f"fixture {payload['id']} forbidden_canonicals entries must be non-empty strings")
        require_same = allowed_additional.get("require_same_across_paths", True)
        if not isinstance(require_same, bool):
            raise ValueError(f"fixture {payload['id']} require_same_across_paths must be a boolean")
        if not require_same:
            for field in ("accepted_deviation_ref", "expires_on"):
                if not isinstance(allowed_additional.get(field), str) or not allowed_additional[field].strip():
                    raise ValueError(f"fixture {payload['id']} require_same_across_paths=false requires {field}")


def fixture_canonical_refs(payload: dict[str, Any]) -> set[str]:
    canonicals = {
        str(expected_match["canonical"])
        for expected_match in payload.get("expected_matches") or []
        if isinstance(expected_match, dict)
        and expected_match.get("canonical") is not None
    }
    allowed_additional = payload.get("allowed_additional_matches") or {}
    if isinstance(allowed_additional, dict):
        for field in ("allowed_canonicals", "forbidden_canonicals"):
            canonicals.update(
                str(canonical)
                for canonical in allowed_additional.get(field, [])
                if canonical is not None
            )
    return canonicals


def fixture_matches_filters(
    payload: dict[str, Any],
    *,
    case_ids: set[str] | None = None,
    policy_refs: set[str] | None = None,
    canonicals: set[str] | None = None,
) -> bool:
    if case_ids and payload["id"] not in case_ids:
        return False
    if policy_refs and payload["policy_ref"] not in policy_refs:
        return False
    if canonicals and not (fixture_canonical_refs(payload) & canonicals):
        return False
    return True


def expected_match_constraints(payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    expected_matches = payload.get("expected_matches")
    if expected_matches is None:
        return None
    constraints = []
    for item in expected_matches:
        constraint = {
            "ingredient_index": int(item["ingredient_index"]),
            "canonical": str(item["canonical"]),
        }
        if item.get("must_match_keyword") is not None:
            constraint["must_match_keyword"] = str(item["must_match_keyword"])
        constraints.append(constraint)
    return sorted(
        constraints,
        key=lambda item: (
            item["ingredient_index"],
            item["canonical"],
            item.get("must_match_keyword", ""),
        ),
    )


def materialized_match_signature(diagnostic: dict[str, Any]) -> list[dict[str, Any]]:
    matches = []
    for match in diagnostic.get("materialization", {}).get("matched_offers", []):
        matched_keyword = match.get("matched_keyword")
        matches.append({
            "ingredient_index": match.get("matched_ingredient_index"),
            "canonical": matched_keyword,
            "matched_keyword": matched_keyword,
        })
    return sorted(
        matches,
        key=lambda item: (
            -1 if item["ingredient_index"] is None else int(item["ingredient_index"]),
            str(item["canonical"]),
            str(item["matched_keyword"]),
        ),
    )


def _match_satisfies_constraint(match: dict[str, Any], constraint: dict[str, Any]) -> bool:
    if match.get("ingredient_index") != constraint["ingredient_index"]:
        return False
    if match.get("canonical") != constraint["canonical"]:
        return False
    must_match_keyword = constraint.get("must_match_keyword")
    return must_match_keyword is None or match.get("matched_keyword") == must_match_keyword


def evaluate_match_expectation(
    payload: dict[str, Any],
    observed_signature: list[dict[str, Any]],
) -> dict[str, Any]:
    constraints = expected_match_constraints(payload)
    if constraints is None:
        return {
            "passed": True,
            "reason": "no_expected_matches",
            "expected_match_constraints": None,
            "observed_match_signature": observed_signature,
            "allowed_additional_matches_used": False,
        }

    unmatched_observed = list(observed_signature)
    missing_constraints = []
    for constraint in constraints:
        match_index = next(
            (
                index
                for index, match in enumerate(unmatched_observed)
                if _match_satisfies_constraint(match, constraint)
            ),
            None,
        )
        if match_index is None:
            missing_constraints.append(constraint)
            continue
        unmatched_observed.pop(match_index)

    allowed_additional = payload.get("allowed_additional_matches")
    extra_matches = unmatched_observed
    allowed_extra_used = bool(extra_matches)
    extra_matches_allowed = not extra_matches
    if extra_matches and isinstance(allowed_additional, dict):
        max_extra_matches = int(allowed_additional.get("max_extra_matches", 0))
        allowed_canonicals = set(allowed_additional.get("allowed_canonicals", []))
        forbidden_canonicals = set(allowed_additional.get("forbidden_canonicals", []))
        extra_canonicals = {str(match.get("canonical")) for match in extra_matches}
        extra_matches_allowed = (
            len(extra_matches) <= max_extra_matches
            and not (extra_canonicals & forbidden_canonicals)
            and extra_canonicals <= allowed_canonicals
        )

    passed = not missing_constraints and extra_matches_allowed
    if missing_constraints:
        reason = "missing_expected_matches"
    elif not extra_matches_allowed:
        reason = "unexpected_additional_matches"
    elif allowed_extra_used:
        reason = "allowed_additional_matches_used"
    else:
        reason = "expected_matches_pass"

    return {
        "passed": passed,
        "reason": reason,
        "expected_match_constraints": constraints,
        "observed_match_signature": observed_signature,
        "missing_expected_matches": missing_constraints,
        "unexpected_additional_matches": [] if extra_matches_allowed else extra_matches,
        "allowed_additional_matches_used": allowed_extra_used and extra_matches_allowed,
    }


def run_fixtures(
    fixture_payloads: list[dict[str, Any]],
    *,
    case_ids: set[str] | None = None,
    policy_refs: set[str] | None = None,
    canonicals: set[str] | None = None,
    diagnosis_classes: set[str] | None = None,
) -> dict[str, Any]:
    selected_payloads = []
    for payload in fixture_payloads:
        _validate_fixture_payload(payload)
        if not fixture_matches_filters(
            payload,
            case_ids=case_ids,
            policy_refs=policy_refs,
            canonicals=canonicals,
        ):
            continue
        selected_payloads.append(payload)

    results = []
    for payload in selected_payloads:
        diagnostic = diagnose_case(
            _diagnostic_case_from_fixture(payload),
            include_cache_freshness=False,
        )
        expected_diagnosis = str(payload.get("expected_diagnosis") or "pass")
        match_expectation = evaluate_match_expectation(
            payload,
            materialized_match_signature(diagnostic),
        )
        passed = (
            diagnostic["actual"] == payload["expected"]
            and diagnostic["diagnosis_class"] == expected_diagnosis
            and match_expectation["passed"]
        )
        result = {
            "id": payload["id"],
            "policy_ref": payload["policy_ref"],
            "source_ref": payload["source_ref"],
            "expected": payload["expected"],
            "actual": diagnostic["actual"],
            "expected_diagnosis": expected_diagnosis,
            "diagnosis_class": diagnostic["diagnosis_class"],
            "passed": passed,
            "first_action": diagnostic["first_action"],
            "paired_route_terms": diagnostic.get("candidate_routing", {}).get("paired_route_terms", []),
            "fast_match_keyword": diagnostic.get("fast_match", {}).get("matched_keyword"),
            "backend_accepted": diagnostic.get("backend_validation", {}).get("accepted"),
            "materialized": diagnostic.get("materialization", {}).get("matched"),
            "match_expectation": match_expectation,
        }
        if diagnosis_classes and result["diagnosis_class"] not in diagnosis_classes:
            continue
        results.append(result)

    diagnosis_counts = Counter(result["diagnosis_class"] for result in results)
    failures = [result for result in results if not result["passed"]]
    return {
        "summary": {
            "cases": len(results),
            "passed": len(results) - len(failures),
            "failed": len(failures),
            "diagnosis_counts": dict(sorted(diagnosis_counts.items())),
        },
        "results": results,
        "failures": failures,
    }


def _format_text(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        (
            "matcher layer fixtures: "
            f"{summary['passed']}/{summary['cases']} passed, "
            f"{summary['failed']} failed"
        ),
        f"diagnosis counts: {summary['diagnosis_counts']}",
    ]
    for failure in report["failures"]:
        lines.extend([
            "",
            f"FAIL {failure['id']}",
            f"  expected/actual: {failure['expected']} / {failure['actual']}",
            f"  diagnosis: {failure['diagnosis_class']} (expected {failure['expected_diagnosis']})",
            f"  paired route terms: {failure['paired_route_terms'] or '-'}",
            f"  fastmatch: {failure['fast_match_keyword']}",
            f"  backend accepted: {failure['backend_accepted']}",
            f"  materialized: {failure['materialized']}",
            f"  match expectation: {failure['match_expectation']['reason']}",
            f"  first action: {failure['first_action']}",
        ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run matcher-layer decision fixtures.")
    parser.add_argument("--fixture-file", default=str(DEFAULT_FIXTURE_FILE))
    parser.add_argument("--case-id", action="append", help="Run only this fixture id. Can be repeated.")
    parser.add_argument("--policy-ref", action="append", help="Run only fixtures with this policy_ref. Can be repeated.")
    parser.add_argument("--canonical", action="append", help="Run only fixtures expecting this canonical. Can be repeated.")
    parser.add_argument(
        "--diagnosis-class",
        action="append",
        help="Report only fixtures with this observed diagnosis class. Can be repeated.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--skip-cache-freshness",
        action="store_true",
        help="Skip the default freshness preflight.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.skip_cache_freshness:
        freshness = check_cache_freshness()
        if freshness.get("blocked"):
            report = {
                "summary": {
                    "cases": 0,
                    "passed": 0,
                    "failed": 1,
                    "diagnosis_counts": {"cache_freshness_blocked": 1},
                },
                "cache_freshness": freshness,
                "failures": [{
                    "id": "cache_freshness",
                    "diagnosis_class": "cache_freshness_blocked",
                    "first_action": "Refresh stale compiled data/term indexes before fixture diagnostics.",
                }],
            }
            if args.format == "json":
                print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                needed = ", ".join(freshness.get("needed_refreshes", [])) or "-"
                print("matcher layer fixtures: blocked by stale cache")
                print(f"needed refreshes: {needed}")
            return 1

    fixture_payloads = _load_fixture_payload(Path(args.fixture_file))
    report = run_fixtures(
        fixture_payloads,
        case_ids=set(args.case_id or []) or None,
        policy_refs=set(args.policy_ref or []) or None,
        canonicals=set(args.canonical or []) or None,
        diagnosis_classes=set(args.diagnosis_class or []) or None,
    )
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_format_text(report))
    return 1 if report["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
