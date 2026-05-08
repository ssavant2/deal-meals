#!/usr/bin/env python3
"""Run matcher-layer fixtures across live, compiled, and routed paths."""

from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, "/app" if os.path.exists("/app") else str(APP_DIR))

from languages.sv.ingredient_matching.compiled_offers import normalize_compiled_offer_payload  # noqa: E402
from languages.sv.ingredient_matching.compiled_recipes import (  # noqa: E402
    prepare_recipe_match_runtime_data,
    serialize_prepared_recipe_match_runtime_data,
)
from languages.sv.ingredient_matching.ingredient_routing import (  # noqa: E402
    build_recipe_ingredient_term_map,
)
from languages.sv.ingredient_matching.matching import precompute_offer_data  # noqa: E402
from languages.sv.ingredient_matching.offer_identity import build_offer_identity_key  # noqa: E402
from languages.sv.ingredient_matching.term_indexes import build_offer_candidate_terms  # noqa: E402
from tests.matcher_layer_diagnostics import (  # noqa: E402
    DiagnosticCase,
    DiagnosticMatcher,
    check_cache_freshness,
    diagnose_case,
)
from tests.run_matcher_layer_fixture_cases import (  # noqa: E402
    DEFAULT_FIXTURE_FILE,
    _diagnostic_case_from_fixture,
    _load_fixture_payload,
    _validate_fixture_payload,
    evaluate_match_expectation,
    fixture_matches_filters,
    materialized_match_signature,
)
from languages.sv.recipe_matcher_backend import match_recipe_to_offers  # noqa: E402
from models import FoundRecipe, Offer  # noqa: E402


PATHS = ("live_fullscan", "compiled_fullscan", "compiled_routed", "compiled_hint_first")


def _build_recipe(case: DiagnosticCase) -> FoundRecipe:
    return FoundRecipe(
        source_name="matcher_layer_parity",
        name=case.recipe_name,
        url=f"matcher-layer-parity://recipe/{case.case_id}",
        ingredients=list(case.ingredients),
        excluded=False,
    )


def _build_offer(case: DiagnosticCase) -> Offer:
    return Offer(
        name=case.offer_name,
        category=case.offer_category,
        brand=case.offer_brand,
        price=Decimal("10.00"),
        original_price=Decimal("20.00"),
        savings=Decimal("10.00"),
        unit="st",
        product_url=f"matcher-layer-parity://offer/{case.case_id}",
        is_multi_buy=False,
    )


def _compiled_offer_payload(offer: Offer) -> dict[str, Any]:
    return normalize_compiled_offer_payload(
        precompute_offer_data(
            offer.name,
            offer.category or "",
            brand=offer.brand or "",
            weight_grams=float(offer.weight_grams) if offer.weight_grams is not None else None,
        )
    )


def _route_state(compiled_recipe_payload: dict[str, Any], compiled_offer_payload: dict[str, Any]) -> dict[str, Any]:
    offer_route_terms_typed = build_offer_candidate_terms(compiled_offer_payload)
    offer_route_terms = {term for term, _term_type in offer_route_terms_typed}
    recipe_term_map = build_recipe_ingredient_term_map(compiled_recipe_payload, offer_route_terms)
    paired_route_terms = {
        term
        for term in offer_route_terms
        if recipe_term_map.get(term)
    }
    hinted_indices = sorted({
        index
        for term in paired_route_terms
        for index in recipe_term_map.get(term, set())
    })
    return {
        "offer_route_terms": sorted(offer_route_terms),
        "paired_route_terms": sorted(paired_route_terms),
        "hinted_ingredient_indices": hinted_indices,
        "routed": bool(paired_route_terms),
    }


def _empty_path_result(path: str, route_state: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "path": path,
        "actual": 0,
        "matches": [],
        "match_signature": [],
        "routed": False if route_state is not None else None,
        "paired_route_terms": route_state.get("paired_route_terms", []) if route_state else [],
        "fullscan_fallback_count": 0,
        "fullscan_fallback_reason_counts": {},
        "hinted_no_match_count": 0,
    }


def _path_result(path: str, match_data: dict[str, Any], route_state: dict[str, Any] | None = None) -> dict[str, Any]:
    matches = []
    for offer_data in match_data.get("matched_offers", []):
        matches.append({
            "ingredient_index": offer_data.get("_matched_ing_idx"),
            "canonical": offer_data.get("matched_keyword"),
            "matched_keyword": offer_data.get("matched_keyword"),
            "offer_identity_key": offer_data.get("offer_identity_key"),
        })
    matches = sorted(
        matches,
        key=lambda item: (
            -1 if item["ingredient_index"] is None else int(item["ingredient_index"]),
            str(item["canonical"]),
            str(item["offer_identity_key"]),
        ),
    )
    signature = [
        {
            "ingredient_index": match["ingredient_index"],
            "canonical": match["canonical"],
            "matched_keyword": match["matched_keyword"],
        }
        for match in matches
    ]
    return {
        "path": path,
        "actual": 1 if matches else 0,
        "matches": matches,
        "match_signature": signature,
        "routed": route_state.get("routed") if route_state else None,
        "paired_route_terms": route_state.get("paired_route_terms", []) if route_state else [],
        "fullscan_fallback_count": int(match_data.get("fullscan_fallback_count") or 0),
        "fullscan_fallback_reason_counts": dict(
            sorted((match_data.get("fullscan_fallback_reason_counts") or {}).items())
        ),
        "hinted_no_match_count": int(match_data.get("hinted_no_match_count") or 0),
    }


def evaluate_case_paths(case: DiagnosticCase) -> dict[str, Any]:
    matcher = DiagnosticMatcher()
    recipe = _build_recipe(case)
    offer = _build_offer(case)
    offer_id = id(offer)
    offer_identity_key = build_offer_identity_key(offer)

    prepared_recipe = prepare_recipe_match_runtime_data(recipe)
    compiled_recipe_payload = serialize_prepared_recipe_match_runtime_data(prepared_recipe)
    compiled_offer_payload = _compiled_offer_payload(offer)
    offer_data_cache = {offer_id: compiled_offer_payload}
    route_state = _route_state(compiled_recipe_payload, compiled_offer_payload)

    live_fullscan = match_recipe_to_offers(
        matcher,
        recipe,
        [offer],
        preferences={},
        ingredient_routing_mode="off",
    )
    compiled_fullscan = match_recipe_to_offers(
        matcher,
        recipe,
        [offer],
        preferences={},
        offer_data_cache=offer_data_cache,
        compiled_recipe_data=compiled_recipe_payload,
        ingredient_routing_mode="off",
    )

    if route_state["routed"]:
        compiled_routed = match_recipe_to_offers(
            matcher,
            recipe,
            [offer],
            preferences={},
            offer_data_cache=offer_data_cache,
            compiled_recipe_data=compiled_recipe_payload,
            ingredient_routing_mode="off",
        )
        compiled_routed_result = _path_result("compiled_routed", compiled_routed, route_state)
        compiled_hint_first = match_recipe_to_offers(
            matcher,
            recipe,
            [offer],
            preferences={},
            offer_data_cache=offer_data_cache,
            compiled_recipe_data=compiled_recipe_payload,
            ingredient_candidate_indices_by_offer={
                offer_identity_key: set(route_state["hinted_ingredient_indices"]),
            },
            ingredient_routing_mode="hint_first",
        )
        compiled_hint_first_result = _path_result(
            "compiled_hint_first",
            compiled_hint_first,
            route_state,
        )
    else:
        compiled_routed_result = _empty_path_result("compiled_routed", route_state)
        compiled_hint_first_result = _empty_path_result("compiled_hint_first", route_state)

    path_results = {
        "live_fullscan": _path_result("live_fullscan", live_fullscan),
        "compiled_fullscan": _path_result("compiled_fullscan", compiled_fullscan),
        "compiled_routed": compiled_routed_result,
        "compiled_hint_first": compiled_hint_first_result,
    }

    return {
        "offer_identity_key": offer_identity_key,
        "route_state": route_state,
        "paths": path_results,
    }


def _signature_key(path_result: dict[str, Any]) -> str:
    return json.dumps(
        path_result["match_signature"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _case_parity_report(payload: dict[str, Any]) -> dict[str, Any]:
    _validate_fixture_payload(payload)
    case = _diagnostic_case_from_fixture(payload)
    paths = evaluate_case_paths(case)
    path_results = paths["paths"]
    expected = int(payload["expected"])
    match_expectations = {
        path_name: evaluate_match_expectation(payload, path_result["match_signature"])
        for path_name, path_result in path_results.items()
    }
    path_failure_details = {}
    for path_name, path_result in path_results.items():
        actual_failed = path_result["actual"] != expected
        match_expectation = match_expectations[path_name]
        if actual_failed or not match_expectation["passed"]:
            path_failure_details[path_name] = {
                "actual_failed": actual_failed,
                "match_expectation": match_expectation,
            }
    path_failures = set(path_failure_details)
    signature_keys = {
        path_name: _signature_key(path_result)
        for path_name, path_result in path_results.items()
    }
    parity_mismatch = len(set(signature_keys.values())) > 1
    diagnostic = diagnose_case(case, include_cache_freshness=False)
    diagnostic_match_expectation = evaluate_match_expectation(
        payload,
        materialized_match_signature(diagnostic),
    )
    signal_provenance = diagnostic.get("signal_provenance", {})
    duplicate_signal_source_count = int(
        signal_provenance.get("duplicate_signal_source", {}).get("count", 0)
    )
    ambiguous_canonical_count = int(
        signal_provenance.get("ambiguous_canonical", {}).get("count", 0)
    )
    passed = (
        not path_failures
        and not parity_mismatch
        and diagnostic["diagnosis_class"] == "pass"
        and diagnostic_match_expectation["passed"]
        and duplicate_signal_source_count == 0
        and ambiguous_canonical_count == 0
    )
    diagnosis_class = "pass"
    if not passed:
        diagnosis_class = diagnostic["diagnosis_class"]
        if diagnosis_class == "pass" and duplicate_signal_source_count:
            diagnosis_class = "duplicate_signal_source"
        if diagnosis_class == "pass" and ambiguous_canonical_count:
            diagnosis_class = "ambiguous_canonical"
        if diagnosis_class == "pass" and not diagnostic_match_expectation["passed"]:
            diagnosis_class = diagnostic_match_expectation["reason"]
        if diagnosis_class == "pass" and parity_mismatch:
            diagnosis_class = "parity_mismatch"
        elif diagnosis_class == "pass":
            diagnosis_class = "path_expectation_failed"

    return {
        "id": payload["id"],
        "policy_ref": payload["policy_ref"],
        "source_ref": payload["source_ref"],
        "expected": expected,
        "passed": passed,
        "parity_mismatch": parity_mismatch,
        "diagnosis_class": diagnosis_class,
        "path_failures": sorted(path_failures),
        "path_failure_details": path_failure_details,
        "match_expectations": match_expectations,
        "diagnostic_match_expectation": diagnostic_match_expectation,
        "signal_provenance": signal_provenance,
        "route_state": paths["route_state"],
        "paths": path_results,
    }


def run_parity(
    fixture_payloads: list[dict[str, Any]],
    *,
    case_ids: set[str] | None = None,
    policy_refs: set[str] | None = None,
    canonicals: set[str] | None = None,
    diagnosis_classes: set[str] | None = None,
) -> dict[str, Any]:
    selected = []
    for payload in fixture_payloads:
        _validate_fixture_payload(payload)
        if not fixture_matches_filters(
            payload,
            case_ids=case_ids,
            policy_refs=policy_refs,
            canonicals=canonicals,
        ):
            continue
        selected.append(payload)

    results = []
    for payload in selected:
        result = _case_parity_report(payload)
        if diagnosis_classes and result["diagnosis_class"] not in diagnosis_classes:
            continue
        results.append(result)
    failures = [result for result in results if not result["passed"]]
    diagnosis_counts = Counter(result["diagnosis_class"] for result in results)
    compiled_hint_first_fallback_reason_counts: Counter[str] = Counter()
    compiled_hint_first_fallback_policy_counts: Counter[str] = Counter()
    compiled_hint_first_fallback_source_prefix_counts: Counter[str] = Counter()
    compiled_hint_first_fallback_expected_counts: Counter[int] = Counter()
    compiled_hint_first_fallback_paired_term_counts: Counter[str] = Counter()
    compiled_hint_first_fallback_case_count = 0
    for result in results:
        hint_first_path = result["paths"]["compiled_hint_first"]
        fallback_count = int(hint_first_path.get("fullscan_fallback_count") or 0)
        compiled_hint_first_fallback_reason_counts.update(
            hint_first_path.get("fullscan_fallback_reason_counts", {})
        )
        if not fallback_count:
            continue

        compiled_hint_first_fallback_case_count += 1
        compiled_hint_first_fallback_policy_counts.update({
            str(result["policy_ref"]): fallback_count,
        })
        source_prefix = str(result["source_ref"]).split(":", 1)[0]
        compiled_hint_first_fallback_source_prefix_counts.update({
            source_prefix: fallback_count,
        })
        compiled_hint_first_fallback_expected_counts.update({
            int(result["expected"]): fallback_count,
        })
        paired_terms = result.get("route_state", {}).get("paired_route_terms") or []
        compiled_hint_first_fallback_paired_term_counts.update({
            str(term): fallback_count
            for term in paired_terms
        })
    by_path = {
        path: {
            "failed": sum(1 for result in results if path in result["path_failures"]),
        }
        for path in PATHS
    }
    return {
        "summary": {
            "cases": len(results),
            "passed": len(results) - len(failures),
            "failed": len(failures),
            "parity_mismatches": sum(1 for result in results if result["parity_mismatch"]),
            "accepted_deviations": 0,
            "canonical_equivalence_used": 0,
            "allowed_additional_matches_used": sum(
                1
                for result in results
                if any(
                    expectation["allowed_additional_matches_used"]
                    for expectation in result["match_expectations"].values()
                )
            ),
            "compiled_hint_first_fullscan_fallbacks": sum(
                int(result["paths"]["compiled_hint_first"].get("fullscan_fallback_count") or 0)
                for result in results
            ),
            "compiled_hint_first_fallback_reason_counts": dict(
                sorted(compiled_hint_first_fallback_reason_counts.items())
            ),
            "compiled_hint_first_fallback_case_count": compiled_hint_first_fallback_case_count,
            "compiled_hint_first_fallback_policy_counts": dict(
                sorted(compiled_hint_first_fallback_policy_counts.items())
            ),
            "compiled_hint_first_fallback_source_prefix_counts": dict(
                sorted(compiled_hint_first_fallback_source_prefix_counts.items())
            ),
            "compiled_hint_first_fallback_expected_counts": dict(
                sorted(compiled_hint_first_fallback_expected_counts.items())
            ),
            "compiled_hint_first_fallback_paired_term_counts": dict(
                sorted(compiled_hint_first_fallback_paired_term_counts.items())
            ),
            "duplicate_signal_source": sum(
                int(
                    result.get("signal_provenance", {})
                    .get("duplicate_signal_source", {})
                    .get("count", 0)
                )
                for result in results
            ),
            "ambiguous_canonical": sum(
                int(
                    result.get("signal_provenance", {})
                    .get("ambiguous_canonical", {})
                    .get("count", 0)
                )
                for result in results
            ),
        },
        "by_path": by_path,
        "diagnosis_counts": dict(sorted(diagnosis_counts.items())),
        "results": results,
        "failures": failures,
    }


def _format_text(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        (
            "matcher layer parity: "
            f"{summary['passed']}/{summary['cases']} passed, "
            f"{summary['failed']} failed, "
            f"parity_mismatches={summary['parity_mismatches']}"
        ),
        (
            "signal_provenance: "
            f"duplicate_signal_source={summary['duplicate_signal_source']} "
            f"ambiguous_canonical={summary['ambiguous_canonical']}"
        ),
        (
            "compiled_hint_first: "
            f"fallbacks={summary['compiled_hint_first_fullscan_fallbacks']} "
            f"fallback_reasons={summary['compiled_hint_first_fallback_reason_counts']}"
        ),
        f"by_path: {report['by_path']}",
        f"diagnosis_counts: {report['diagnosis_counts']}",
    ]
    for failure in report["failures"]:
        lines.extend([
            "",
            f"FAIL {failure['id']}",
            f"  diagnosis: {failure['diagnosis_class']}",
            f"  path_failures: {failure['path_failures'] or '-'}",
            f"  parity_mismatch: {failure['parity_mismatch']}",
            f"  paired_route_terms: {failure['route_state']['paired_route_terms'] or '-'}",
        ])
        for path_name in PATHS:
            path_result = failure["paths"][path_name]
            lines.append(
                "  "
                f"{path_name}: actual={path_result['actual']} "
                f"signature={path_result['match_signature']}"
            )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run matcher-layer fixture parity.")
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
                    "parity_mismatches": 0,
                    "accepted_deviations": 0,
                    "canonical_equivalence_used": 0,
                    "allowed_additional_matches_used": 0,
                    "compiled_hint_first_fullscan_fallbacks": 0,
                    "compiled_hint_first_fallback_reason_counts": {},
                    "duplicate_signal_source": 0,
                    "ambiguous_canonical": 0,
                },
                "by_path": {path: {"failed": 0} for path in PATHS},
                "diagnosis_counts": {"cache_freshness_blocked": 1},
                "cache_freshness": freshness,
                "failures": [{
                    "id": "cache_freshness",
                    "diagnosis_class": "cache_freshness_blocked",
                }],
            }
            if args.format == "json":
                print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                needed = ", ".join(freshness.get("needed_refreshes", [])) or "-"
                print("matcher layer parity: blocked by stale cache")
                print(f"needed refreshes: {needed}")
            return 1

    report = run_parity(
        _load_fixture_payload(Path(args.fixture_file)),
        case_ids=set(args.case_id or []) or None,
        policy_refs=set(args.policy_ref or []) or None,
        canonicals=set(args.canonical or []) or None,
        diagnosis_classes=set(args.diagnosis_class or []) or None,
    )
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_format_text(report))
    return 1 if report["summary"]["failed"] or report["summary"]["parity_mismatches"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
