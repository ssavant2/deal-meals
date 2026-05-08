#!/usr/bin/env python3
"""Schema checks for matcher-layer decision fixtures."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from tests.run_matcher_layer_fixture_cases import (  # noqa: E402
    DEFAULT_FIXTURE_FILE,
    _load_fixture_payload,
    _validate_fixture_payload,
    evaluate_match_expectation,
    fixture_canonical_refs,
    fixture_matches_filters,
)


def check(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"OK {name}")


def check_raises(name: str, payload: dict, expected_fragment: str) -> None:
    try:
        _validate_fixture_payload(payload)
    except ValueError as exc:
        check(name, expected_fragment in str(exc))
        return
    raise AssertionError(f"{name}: expected ValueError")


def _minimal_fixture() -> dict:
    return {
        "id": "schema_check_valid_negative",
        "policy_ref": "schema_check",
        "source_ref": "current_review:schema_check_valid_negative",
        "ingredients": ["1 test"],
        "offer": {
            "name": "Schema Check Offer",
            "category": "pantry",
        },
        "expected": 0,
    }


def main() -> int:
    fixture_payloads = _load_fixture_payload(Path(DEFAULT_FIXTURE_FILE))
    for payload in fixture_payloads:
        _validate_fixture_payload(payload)
    check("default fixture file schema", True)

    salsa_fixture = next(
        payload
        for payload in fixture_payloads
        if payload["id"] == "matcher_regression_chunky_salsa_product_positive"
    )
    check("fixture canonical refs include expected canonical", "salsa" in fixture_canonical_refs(salsa_fixture))
    check(
        "fixture prefilters match policy and canonical",
        fixture_matches_filters(
            salsa_fixture,
            policy_refs={"current_queue_matcher_regression"},
            canonicals={"salsa"},
        ),
    )
    check(
        "fixture prefilters reject wrong policy",
        not fixture_matches_filters(
            salsa_fixture,
            policy_refs={"legacy_import_auto_regression"},
            canonicals={"salsa"},
        ),
    )

    valid_fixture = _minimal_fixture()
    _validate_fixture_payload(valid_fixture)
    check("minimal valid fixture", True)

    invalid_source = deepcopy(valid_fixture)
    invalid_source["source_ref"] = "unknown:source"
    check_raises("unknown source_ref prefix rejected", invalid_source, "source_ref")

    temporary_source = deepcopy(valid_fixture)
    temporary_source["source_ref"] = "current_queue:batch99:schema_check"
    check_raises("temporary source_ref rejected", temporary_source, "source_ref must be stable")

    temporary_fixture_id = deepcopy(valid_fixture)
    temporary_fixture_id["id"] = "batch99_schema_check"
    check_raises("temporary fixture id rejected", temporary_fixture_id, "id must be stable")

    temporary_policy_ref = deepcopy(valid_fixture)
    temporary_policy_ref["policy_ref"] = "batch99"
    check_raises("temporary policy_ref rejected", temporary_policy_ref, "policy_ref")

    old_review_policy_ref = deepcopy(valid_fixture)
    old_review_policy_ref["policy_ref"] = "legacy_questions_old_auto_promoted"
    check_raises("old temporary policy_ref rejected", old_review_policy_ref, "policy_ref")

    missing_reason = deepcopy(valid_fixture)
    missing_reason.update({
        "expected": 1,
        "expected_matches": [{"ingredient_index": 0, "canonical": "schema"}],
        "allowed_additional_matches": {
            "max_extra_matches": 1,
            "allowed_canonicals": ["schema_extra"],
        },
    })
    check_raises("allowed additional reason required", missing_reason, "reason")

    missing_deviation_expiry = deepcopy(missing_reason)
    missing_deviation_expiry["allowed_additional_matches"].update({
        "reason": "schema check",
        "require_same_across_paths": False,
        "accepted_deviation_ref": "schema_check",
    })
    check_raises(
        "allowed additional cross-path deviation requires expiry",
        missing_deviation_expiry,
        "expires_on",
    )

    valid_additional = deepcopy(missing_reason)
    valid_additional["allowed_additional_matches"]["reason"] = "schema check"
    _validate_fixture_payload(valid_additional)
    check("valid allowed_additional_matches schema", True)

    allowed_extra = evaluate_match_expectation(
        valid_additional,
        [
            {
                "ingredient_index": 0,
                "canonical": "schema",
                "matched_keyword": "schema",
            },
            {
                "ingredient_index": 1,
                "canonical": "schema_extra",
                "matched_keyword": "schema_extra",
            },
        ],
    )
    check("allowed additional match can pass", allowed_extra["passed"])
    check("allowed additional match is visible", allowed_extra["allowed_additional_matches_used"])

    forbidden_extra = evaluate_match_expectation(
        valid_additional,
        [
            {
                "ingredient_index": 0,
                "canonical": "schema",
                "matched_keyword": "schema",
            },
            {
                "ingredient_index": 1,
                "canonical": "schema_forbidden",
                "matched_keyword": "schema_forbidden",
            },
        ],
    )
    check("forbidden additional match fails", not forbidden_extra["passed"])
    check(
        "forbidden additional match reason",
        forbidden_extra["reason"] == "unexpected_additional_matches",
    )

    print("ALL MATCHER LAYER FIXTURE SCHEMA CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
