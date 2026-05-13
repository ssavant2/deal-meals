#!/usr/bin/env python3
"""R3 guard/bridge contract checks for the term registry.

The script validates the declarative negative guards and match bridges before
they are migrated further into registry-owned exports. It does not rebuild
cache or touch the database.
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

from languages.term_registry.models import CheckIssue  # noqa: E402
from languages.term_registry.reports import write_json_and_markdown_report  # noqa: E402
from languages.sv.ingredient_matching import build_offer_match_data  # noqa: E402
from languages.sv.ingredient_matching.match_bridges import (  # noqa: E402
    MATCH_BRIDGES,
    find_match_bridge_hits,
)
from languages.sv.ingredient_matching.no_match_policies import (  # noqa: E402
    NO_MATCH_POLICIES,
    find_no_match_policy_hits,
)
from tests.run_matcher_layer_fixture_cases import (  # noqa: E402
    DEFAULT_FIXTURE_FILE,
    _load_fixture_payload,
    run_fixtures,
)
from tests.run_matcher_rule_inventory_checks import (  # noqa: E402
    DEFAULT_INVENTORY_FILE,
    load_inventory,
)


DEFAULT_REPORT_ROOT = APP_DIR / "tests" / "reports" / "term_registry"
DEFAULT_DIAGNOSTIC_SAMPLE_SIZE = 75


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


def _offer_text(offer: dict[str, Any]) -> str:
    return " ".join(
        str(value)
        for value in (offer.get("name"), offer.get("category"), offer.get("brand"))
        if value
    )


def _offer_keywords(offer: dict[str, Any]) -> tuple[str, ...]:
    offer_data = build_offer_match_data(
        str(offer.get("name") or ""),
        str(offer.get("category") or ""),
        brand=str(offer.get("brand") or ""),
        weight_grams=offer.get("weight_grams"),
    )
    return tuple(offer_data.keywords)


def _fixture_expected(payload: dict[str, Any] | None) -> int | None:
    if not payload:
        return None
    expected = payload.get("expected")
    return int(expected) if expected in (0, 1) else None


def _superseded_fixture_refs(rule, inventory_by_id: dict[str, dict[str, Any]]) -> set[str]:
    refs: set[str] = set()
    for legacy_id in rule.supersedes:
        refs.update(str(ref) for ref in inventory_by_id.get(legacy_id, {}).get("fixture_refs", ()))
    return refs


def _superseded_policy_refs(rule, inventory_by_id: dict[str, dict[str, Any]]) -> set[str]:
    return {
        str(inventory_by_id[legacy_id].get("policy_ref") or "")
        for legacy_id in rule.supersedes
        if legacy_id in inventory_by_id and inventory_by_id[legacy_id].get("policy_ref")
    }


def _check_no_match_policies(
    *,
    fixture_by_id: dict[str, dict[str, Any]],
) -> tuple[list[CheckIssue], dict[str, Any], set[str]]:
    issues: list[CheckIssue] = []
    diagnostic_refs: set[str] = set()
    blocked_fixture_refs = 0
    helper_hits = 0

    for policy in NO_MATCH_POLICIES:
        missing = sorted(ref for ref in policy.fixture_refs if ref not in fixture_by_id)
        if missing:
            issues.append(_issue(
                "error",
                "no_match_policy_fixture_missing",
                "no-match policy references unknown fixtures",
                item_id=policy.id,
                details={"missing": missing},
            ))

        negative_refs = sorted(
            ref
            for ref in policy.fixture_refs
            if _fixture_expected(fixture_by_id.get(ref)) == 0
        )
        if not negative_refs and not policy.policy_ref:
            issues.append(_issue(
                "error",
                "no_match_policy_negative_contract_missing",
                "no-match policy must have an executable negative fixture or policy_ref",
                item_id=policy.id,
            ))
        blocked_fixture_refs += len(negative_refs)
        diagnostic_refs.update(negative_refs)

        for fixture_ref in negative_refs:
            payload = fixture_by_id[fixture_ref]
            offer = payload["offer"]
            hits = find_no_match_policy_hits(
                ingredient_texts=payload["ingredients"],
                offer_keywords=_offer_keywords(offer),
                offer_text=_offer_text(offer),
            )
            if policy.id not in {str(hit["id"]) for hit in hits}:
                issues.append(_issue(
                    "error",
                    "no_match_policy_fixture_miss",
                    "no-match policy helper did not hit its negative fixture",
                    item_id=policy.id,
                    details={"fixture_ref": fixture_ref, "hit_ids": [hit["id"] for hit in hits]},
                ))
            else:
                helper_hits += 1

        for fixture_ref in policy.fixture_refs:
            if _fixture_expected(fixture_by_id.get(fixture_ref)) != 1:
                continue
            payload = fixture_by_id[fixture_ref]
            offer = payload["offer"]
            hits = find_no_match_policy_hits(
                ingredient_texts=payload["ingredients"],
                offer_keywords=_offer_keywords(offer),
                offer_text=_offer_text(offer),
            )
            if policy.id in {str(hit["id"]) for hit in hits}:
                issues.append(_issue(
                    "error",
                    "no_match_policy_positive_fixture_hit",
                    "no-match policy hit a fixture that should remain allowed",
                    item_id=policy.id,
                    details={"fixture_ref": fixture_ref},
                ))

    summary = {
        "policy_count": len(NO_MATCH_POLICIES),
        "negative_fixture_refs": blocked_fixture_refs,
        "helper_hits": helper_hits,
    }
    return issues, summary, diagnostic_refs


def _check_match_bridges(
    *,
    fixture_by_id: dict[str, dict[str, Any]],
    inventory_by_id: dict[str, dict[str, Any]],
) -> tuple[list[CheckIssue], dict[str, Any], set[str]]:
    issues: list[CheckIssue] = []
    diagnostic_refs: set[str] = set()
    positive_fixture_refs = 0
    negative_fixture_refs = 0
    helper_positive_hits = 0
    policy_ref_only_negative_contracts: list[dict[str, Any]] = []
    bridges_with_negative_declarations = 0

    for bridge in MATCH_BRIDGES:
        missing = sorted(ref for ref in bridge.fixture_refs if ref not in fixture_by_id)
        if missing:
            issues.append(_issue(
                "error",
                "match_bridge_fixture_missing",
                "match bridge references unknown fixtures",
                item_id=bridge.id,
                details={"missing": missing},
            ))

        if not bridge.ingredient_patterns or not bridge.offer_patterns:
            issues.append(_issue(
                "error",
                "match_bridge_positive_side_missing",
                "match bridge must declare ingredient and offer positive sides",
                item_id=bridge.id,
            ))

        positive_refs = sorted(
            ref
            for ref in bridge.fixture_refs
            if _fixture_expected(fixture_by_id.get(ref)) == 1
        )
        if not positive_refs:
            issues.append(_issue(
                "error",
                "match_bridge_positive_fixture_missing",
                "match bridge must have at least one executable positive fixture",
                item_id=bridge.id,
            ))
        positive_fixture_refs += len(positive_refs)
        diagnostic_refs.update(positive_refs)

        for fixture_ref in positive_refs:
            payload = fixture_by_id[fixture_ref]
            offer = payload["offer"]
            hits = find_match_bridge_hits(
                ingredient_texts=payload["ingredients"],
                offer_keywords=_offer_keywords(offer),
                offer_text=_offer_text(offer),
            )
            if bridge.id not in {str(hit["id"]) for hit in hits}:
                issues.append(_issue(
                    "error",
                    "match_bridge_positive_fixture_miss",
                    "match bridge helper did not hit its positive fixture",
                    item_id=bridge.id,
                    details={"fixture_ref": fixture_ref, "hit_ids": [hit["id"] for hit in hits]},
                ))
            else:
                helper_positive_hits += 1

        declared_negative_side = bool(
            bridge.negative_offer_patterns
            or bridge.blockers
            or bridge.forbidden_offer_form_signals
        )
        if declared_negative_side:
            bridges_with_negative_declarations += 1

        inherited_negative_refs = sorted(
            ref
            for ref in (_superseded_fixture_refs(bridge, inventory_by_id) - set(bridge.fixture_refs))
            if _fixture_expected(fixture_by_id.get(ref)) == 0
        )
        negative_fixture_refs += len(inherited_negative_refs)
        diagnostic_refs.update(inherited_negative_refs)

        if declared_negative_side and not inherited_negative_refs:
            policy_refs = sorted(_superseded_policy_refs(bridge, inventory_by_id))
            if not policy_refs:
                issues.append(_issue(
                    "error",
                    "match_bridge_negative_contract_missing",
                    "bridge with a negative side needs an executable negative fixture or policy_ref",
                    item_id=bridge.id,
                ))
            else:
                policy_ref_only_negative_contracts.append({
                    "bridge_id": bridge.id,
                    "canonical": bridge.canonical,
                    "policy_refs": policy_refs,
                })

        for fixture_ref in inherited_negative_refs:
            payload = fixture_by_id[fixture_ref]
            offer = payload["offer"]
            hits = find_match_bridge_hits(
                ingredient_texts=payload["ingredients"],
                offer_keywords=_offer_keywords(offer),
                offer_text=_offer_text(offer),
            )
            if bridge.id in {str(hit["id"]) for hit in hits}:
                issues.append(_issue(
                    "error",
                    "match_bridge_negative_fixture_hit",
                    "match bridge hit an inherited negative fixture",
                    item_id=bridge.id,
                    details={"fixture_ref": fixture_ref},
                ))

        for blocker in bridge.blockers:
            missing_blocker_refs = sorted(ref for ref in blocker.fixture_refs if ref not in fixture_by_id)
            if missing_blocker_refs:
                issues.append(_issue(
                    "error",
                    "match_bridge_blocker_fixture_missing",
                    "bridge blocker references unknown fixtures",
                    item_id=blocker.id,
                    details={"bridge_id": bridge.id, "missing": missing_blocker_refs},
                ))
            blocker_negative_refs = [
                ref
                for ref in blocker.fixture_refs
                if _fixture_expected(fixture_by_id.get(ref)) == 0
            ]
            if not blocker_negative_refs and not blocker.policy_ref:
                issues.append(_issue(
                    "error",
                    "match_bridge_blocker_negative_contract_missing",
                    "bridge blocker needs an executable negative fixture or policy_ref",
                    item_id=blocker.id,
                    details={"bridge_id": bridge.id},
                ))

    summary = {
        "bridge_count": len(MATCH_BRIDGES),
        "bridges_with_negative_declarations": bridges_with_negative_declarations,
        "positive_fixture_refs": positive_fixture_refs,
        "inherited_negative_fixture_refs": negative_fixture_refs,
        "helper_positive_hits": helper_positive_hits,
        "policy_ref_only_negative_contract_count": len(policy_ref_only_negative_contracts),
        "policy_ref_only_negative_contracts": policy_ref_only_negative_contracts[:20],
    }
    return issues, summary, diagnostic_refs


def _sample_refs(refs: set[str], max_cases: int) -> list[str]:
    return sorted(refs)[:max_cases]


def run_checks(args: argparse.Namespace) -> tuple[dict[str, Any], list[CheckIssue]]:
    fixture_payloads = _load_fixture_payload(Path(args.fixture_file))
    fixture_by_id = {str(payload["id"]): payload for payload in fixture_payloads}
    inventory_entries = load_inventory(Path(args.inventory_file))
    inventory_by_id = {str(entry["id"]): entry for entry in inventory_entries}

    issues: list[CheckIssue] = []
    policy_issues, policy_summary, policy_diagnostic_refs = _check_no_match_policies(
        fixture_by_id=fixture_by_id,
    )
    bridge_issues, bridge_summary, bridge_diagnostic_refs = _check_match_bridges(
        fixture_by_id=fixture_by_id,
        inventory_by_id=inventory_by_id,
    )
    issues.extend(policy_issues)
    issues.extend(bridge_issues)

    diagnostic_refs = _sample_refs(
        policy_diagnostic_refs | bridge_diagnostic_refs,
        args.max_diagnostic_cases,
    )
    diagnostic_report = run_fixtures(
        fixture_payloads,
        case_ids=set(diagnostic_refs),
    )
    for failure in diagnostic_report["failures"]:
        issues.append(_issue(
            "error",
            "guard_bridge_diagnostic_failure",
            "matcher diagnostics did not match expected route/final-match behavior",
            item_id=str(failure["id"]),
            details={
                "expected": failure["expected"],
                "actual": failure["actual"],
                "diagnosis_class": failure["diagnosis_class"],
                "expected_diagnosis": failure["expected_diagnosis"],
                "first_action": failure["first_action"],
            },
        ))

    issue_counts = Counter(issue.severity for issue in issues)
    summary = {
        "language": args.language,
        "market": args.market,
        "fixture_count": len(fixture_payloads),
        "inventory_entry_count": len(inventory_entries),
        "no_match_policies": policy_summary,
        "match_bridges": bridge_summary,
        "diagnostic_sample_cases": len(diagnostic_refs),
        "diagnostic_sample_passed": diagnostic_report["summary"]["passed"],
        "diagnostic_sample_failed": diagnostic_report["summary"]["failed"],
        "issue_counts": dict(sorted(issue_counts.items())),
        "passed": not any(issue.severity == "error" for issue in issues),
    }
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "findings": [issue.to_dict() for issue in issues],
        "diagnostic_sample_refs": diagnostic_refs,
        "diagnostic_sample_summary": diagnostic_report["summary"],
    }
    return payload, issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", default="sv")
    parser.add_argument("--market", default="SE")
    parser.add_argument("--fixture-file", default=str(DEFAULT_FIXTURE_FILE))
    parser.add_argument("--inventory-file", default=str(DEFAULT_INVENTORY_FILE))
    parser.add_argument("--max-diagnostic-cases", type=int, default=DEFAULT_DIAGNOSTIC_SAMPLE_SIZE)
    parser.add_argument("--report-dir", type=Path, default=None)
    args = parser.parse_args()

    if args.language != "sv":
        raise ValueError("R3 currently supports --language sv only")
    if args.max_diagnostic_cases <= 0:
        raise ValueError("--max-diagnostic-cases must be positive")
    if args.report_dir is None:
        args.report_dir = DEFAULT_REPORT_ROOT / args.language

    payload, issues = run_checks(args)
    json_report_path = args.report_dir / "term_registry_guard_bridge_report.json"
    md_report_path = args.report_dir / "term_registry_guard_bridge_report.md"
    payload["summary"]["reports"] = [
        str(json_report_path.relative_to(REPO_DIR)),
        str(md_report_path.relative_to(REPO_DIR)),
    ]
    json_path, md_path = write_json_and_markdown_report(
        report_dir=args.report_dir,
        stem="term_registry_guard_bridge_report",
        payload=payload,
        title="Term Registry Guard/Bridge Report",
    )
    assert json_path == json_report_path and md_path == md_report_path

    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if any(issue.severity == "error" for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
