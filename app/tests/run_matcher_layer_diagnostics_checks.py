#!/usr/bin/env python3
"""Policy checks for matcher_layer_diagnostics."""

from __future__ import annotations

from pathlib import Path
import sys


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from tests.matcher_layer_diagnostics import DiagnosticCase, diagnose_case  # noqa: E402


def check(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"OK {name}")


def main() -> int:
    positive = diagnose_case(
        DiagnosticCase(
            case_id="check_jordgubbssaft_positive",
            recipe_name="Sanity Recipe",
            ingredients=("2 dl jordgubbssaft",),
            offer_name="Blandsaft Jordgubb Bob",
            offer_category="beverages",
            expected=1,
        ),
        include_cache_freshness=False,
    )
    check("positive actual", positive["actual"], 1)
    check("positive passed", positive["passed"], True)
    check("positive diagnosis", positive["diagnosis_class"], "pass")
    check("positive routed", positive["candidate_routing"]["offer_recipe_routed"], True)
    check("positive fastmatch keyword", positive["fast_match"]["matched_keyword"], "jordgubbssaft")
    check("positive backend accepted", positive["backend_validation"]["accepted"], True)
    check("positive materialized", positive["materialization"]["matched"], True)
    check("positive hint-first scope", positive["hint_first"]["probe_scope"], "routed_pair")
    check("positive hint-first fallbacks", positive["hint_first"]["fullscan_fallback_count"], 0)
    check("positive duplicate signals", positive["signal_provenance"]["duplicate_signal_source"]["count"], 0)
    check("positive ambiguous canonicals", positive["signal_provenance"]["ambiguous_canonical"]["count"], 0)

    negative = diagnose_case(
        DiagnosticCase(
            case_id="check_jordgubbssaft_marmelad_negative",
            recipe_name="Sanity Recipe",
            ingredients=("2 dl jordgubbssaft",),
            offer_name="Jordgubbsmarmelad Bob",
            offer_category="pantry",
            expected=0,
        ),
        include_cache_freshness=False,
    )
    check("negative actual", negative["actual"], 0)
    check("negative passed", negative["passed"], True)
    check("negative diagnosis", negative["diagnosis_class"], "pass")
    check("negative routed", negative["candidate_routing"]["offer_recipe_routed"], False)
    check("negative hint-first scope", negative["hint_first"]["probe_scope"], "unrouted_diagnostic_probe")
    check("negative recipe signal", negative["recipe_signals"]["route_terms"], ["jordgubbssaft"])

    generic_oil = diagnose_case(
        DiagnosticCase(
            case_id="check_declarative_generic_oil_no_match_policy",
            recipe_name="Sanity Recipe",
            ingredients=("1 msk olja till stekning",),
            offer_name="Rapsolja Eldorado",
            offer_category="pantry",
            expected=0,
        ),
        include_cache_freshness=False,
    )
    check("declarative no-match actual", generic_oil["actual"], 0)
    check(
        "declarative no-match policy ids",
        [policy["id"] for policy in generic_oil["declarative_rules"]["no_match_policies"]],
        ["policy_generic_oil"],
    )

    dill_bridge = diagnose_case(
        DiagnosticCase(
            case_id="check_declarative_dillfro_bridge",
            recipe_name="Sanity Recipe",
            ingredients=("1 tsk Dillfrö",),
            offer_name="Dillfrön Burk Kockens",
            offer_category="spices",
            expected=1,
        ),
        include_cache_freshness=False,
    )
    check("declarative bridge actual", dill_bridge["actual"], 1)
    check(
        "declarative bridge ids",
        [bridge["id"] for bridge in dill_bridge["declarative_rules"]["match_bridges"]],
        ["bridge_dillfro_plural"],
    )

    missing_route = diagnose_case(
        DiagnosticCase(
            case_id="check_route_pair_missing",
            recipe_name="Sanity Recipe",
            ingredients=("2 dl jordgubbssaft",),
            offer_name="Jordgubbsmarmelad Bob",
            offer_category="pantry",
            expected=1,
        ),
        include_cache_freshness=False,
    )
    check("route missing actual", missing_route["actual"], 0)
    check("route missing passed", missing_route["passed"], False)
    check("route missing diagnosis", missing_route["diagnosis_class"], "route_pair_missing")

    hinted_validation_rejected = diagnose_case(
        DiagnosticCase(
            case_id="check_hint_first_hinted_validation_rejected",
            recipe_name="Vegansk burger",
            ingredients=("1 st Burgare",),
            offer_name="Burgare Nöt Sverige",
            offer_category="meat",
            expected=0,
        ),
        include_cache_freshness=False,
    )
    check("hinted validation rejected diagnosis", hinted_validation_rejected["diagnosis_class"], "pass")
    check("hinted validation rejected scope", hinted_validation_rejected["hint_first"]["probe_scope"], "routed_pair")
    check("hinted validation rejected fallbacks", hinted_validation_rejected["hint_first"]["fullscan_fallback_count"], 0)
    check(
        "hinted validation rejected fallback reasons",
        hinted_validation_rejected["hint_first"]["fullscan_fallback_reason_counts"],
        {},
    )

    cider_parent = diagnose_case(
        DiagnosticCase(
            case_id="check_cider_parent_precedence",
            recipe_name="Sanity Recipe",
            ingredients=("Cider Äpple",),
            offer_name="Äppelcider Herrljunga",
            offer_category="beverages",
            expected=1,
        ),
        include_cache_freshness=False,
    )
    check("cider parent actual", cider_parent["actual"], 1)
    check("cider parent diagnosis", cider_parent["diagnosis_class"], "pass")
    check("cider parent ambiguous canonicals", cider_parent["signal_provenance"]["ambiguous_canonical"]["count"], 0)

    folk_beer_parent = diagnose_case(
        DiagnosticCase(
            case_id="check_folk_beer_parent_precedence",
            recipe_name="Sanity Recipe",
            ingredients=("1 flaska folköl",),
            offer_name="Folköl Pripps",
            offer_category="beverages",
            expected=1,
        ),
        include_cache_freshness=False,
    )
    check("folk beer parent actual", folk_beer_parent["actual"], 1)
    check("folk beer parent diagnosis", folk_beer_parent["diagnosis_class"], "pass")
    check(
        "folk beer parent ambiguous canonicals",
        folk_beer_parent["signal_provenance"]["ambiguous_canonical"]["count"],
        0,
    )

    print("ALL MATCHER LAYER DIAGNOSTIC CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
