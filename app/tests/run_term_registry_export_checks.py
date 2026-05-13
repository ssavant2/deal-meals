#!/usr/bin/env python3
"""R1/R2 export checks for the term registry.

The script proves that narrow registry-generated exports match the frozen verified-term
baseline and, once R2 starts, that public runtime constants import generated
exports. It does not rebuild cache or touch the database.
"""

from __future__ import annotations

import argparse
import ast
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

from languages.term_registry.models import CheckIssue, RegistryVariant  # noqa: E402
from languages.term_registry.reports import write_json_and_markdown_report  # noqa: E402
from languages.sv.ingredient_matching.ingredient_routing import _ROUTING_PARENT_TERMS as PUBLIC_INGREDIENT_ROUTING_PARENT_TERMS  # noqa: E402
from languages.sv.ingredient_matching.keywords import OFFER_EXTRA_KEYWORDS as PUBLIC_OFFER_EXTRA_KEYWORDS  # noqa: E402
from languages.sv.ingredient_matching.match_bridges import MATCH_BRIDGES as PUBLIC_MATCH_BRIDGES  # noqa: E402
from languages.sv.ingredient_matching.no_match_policies import NO_MATCH_POLICIES as PUBLIC_NO_MATCH_POLICIES  # noqa: E402
from languages.sv.ingredient_matching.parent_maps import (  # noqa: E402
    KEYWORD_EXTRA_PARENTS as PUBLIC_KEYWORD_EXTRA_PARENTS,
    PARENT_MATCH_ONLY as PUBLIC_PARENT_MATCH_ONLY,
)
from languages.sv.ingredient_matching.synonyms import (  # noqa: E402
    INGREDIENT_PARENTS as PUBLIC_INGREDIENT_PARENTS,
    KEYWORD_SYNONYMS as PUBLIC_KEYWORD_SYNONYMS,
)
from languages.sv.ingredient_matching.term_registry.exports import (  # noqa: E402
    INGREDIENT_PARENT_SOURCE_FAMILY,
    INGREDIENT_PARENTS as GENERATED_INGREDIENT_PARENTS,
    INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY,
    INGREDIENT_ROUTING_PARENT_TERMS as GENERATED_INGREDIENT_ROUTING_PARENT_TERMS,
    KEYWORD_EXTRA_PARENT_SOURCE_FAMILY,
    KEYWORD_EXTRA_PARENTS as GENERATED_KEYWORD_EXTRA_PARENTS,
    KEYWORD_SYNONYM_SOURCE_FAMILY,
    KEYWORD_SYNONYMS as GENERATED_KEYWORD_SYNONYMS,
    MATCH_BRIDGES as GENERATED_MATCH_BRIDGES,
    MATCH_BRIDGE_SOURCE_FAMILY,
    NO_MATCH_POLICIES as GENERATED_NO_MATCH_POLICIES,
    NO_MATCH_POLICY_SOURCE_FAMILY,
    OFFER_EXTRA_KEYWORD_SOURCE_FAMILY,
    OFFER_EXTRA_KEYWORDS as GENERATED_OFFER_EXTRA_KEYWORDS,
    PARENT_MATCH_ONLY as GENERATED_PARENT_MATCH_ONLY,
    PARENT_MATCH_ONLY_SOURCE_FAMILY,
    RECIPE_ROUTING_EXTRA_ALIASES as GENERATED_RECIPE_ROUTING_EXTRA_ALIASES,
    RECIPE_ROUTING_HELPER_SOURCE_FAMILY,
    build_ingredient_parents_export,
    build_ingredient_routing_parent_export,
    build_keyword_extra_parents_export,
    build_keyword_synonyms_export,
    build_offer_extra_keywords_export,
    build_parent_match_only_export,
    build_recipe_routing_extra_alias_export,
)
from languages.sv.ingredient_matching.term_registry.legacy_inventory import (  # noqa: E402
    DEFAULT_BATCH_SIZE,
    build_legacy_registry_variants,
)


DEFAULT_REPORT_ROOT = APP_DIR / "tests" / "reports" / "term_registry"
DEFAULT_VERIFIED_TERMS_BASELINE_JSON = (
    APP_DIR
    / "languages"
    / "sv"
    / "ingredient_matching"
    / "term_registry"
    / "baselines"
    / "verified_matcher_terms.json"
)
INGREDIENT_ROUTING_RUNTIME_FILE = APP_DIR / "languages" / "sv" / "ingredient_matching" / "ingredient_routing.py"
KEYWORDS_RUNTIME_FILE = APP_DIR / "languages" / "sv" / "ingredient_matching" / "keywords.py"
MATCH_BRIDGES_RUNTIME_FILE = APP_DIR / "languages" / "sv" / "ingredient_matching" / "match_bridges.py"
NO_MATCH_POLICIES_RUNTIME_FILE = APP_DIR / "languages" / "sv" / "ingredient_matching" / "no_match_policies.py"
PARENT_MAPS_RUNTIME_FILE = APP_DIR / "languages" / "sv" / "ingredient_matching" / "parent_maps.py"
SYNONYMS_RUNTIME_FILE = APP_DIR / "languages" / "sv" / "ingredient_matching" / "synonyms.py"
TERM_INDEXES_RUNTIME_FILE = APP_DIR / "languages" / "sv" / "ingredient_matching" / "term_indexes.py"
EXPORTS_RUNTIME_FILE = APP_DIR / "languages" / "sv" / "ingredient_matching" / "term_registry" / "exports.py"


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


def _normalize_mapping(mapping: dict[str, Any]) -> dict[str, str | list[str]]:
    normalized: dict[str, str | list[str]] = {}
    for key, value in mapping.items():
        if isinstance(value, (list, tuple, set, frozenset)):
            normalized[str(key)] = [str(item) for item in value]
        else:
            normalized[str(key)] = str(value)
    return dict(sorted(normalized.items()))


def _mapping_targets(value: str | list[str]) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def _mapping_target_set(value: str | list[str]) -> tuple[str, ...]:
    return tuple(sorted(_mapping_targets(value)))


def _expanded_mapping_count(mapping: dict[str, str | list[str]]) -> int:
    return sum(len(_mapping_targets(value)) for value in mapping.values())


def _unique_variant_target_count(variants: list[RegistryVariant]) -> int:
    return len({
        (variant.variant, variant.canonical)
        for variant in variants
    })


def _mapping_from_pairs(pairs) -> dict[str, str | list[str]]:
    grouped: dict[str, list[str]] = {}
    for source, target in pairs:
        targets = grouped.setdefault(source, [])
        if target not in targets:
            targets.append(target)
    return {
        source: targets[0] if len(targets) == 1 else sorted(targets)
        for source, targets in sorted(grouped.items())
    }


def _mapping_diff(
    generated: dict[str, str | list[str]],
    reference: dict[str, str | list[str]],
) -> dict[str, Any]:
    generated_keys = set(generated)
    reference_keys = set(reference)
    shared_keys = generated_keys & reference_keys
    changed = {
        key: {"generated": generated[key], "reference": reference[key]}
        for key in sorted(shared_keys)
        if _mapping_target_set(generated[key]) != _mapping_target_set(reference[key])
    }
    return {
        "missing_count": len(reference_keys - generated_keys),
        "extra_count": len(generated_keys - reference_keys),
        "changed_count": len(changed),
        "missing_sample": sorted(reference_keys - generated_keys)[:20],
        "extra_sample": sorted(generated_keys - reference_keys)[:20],
        "changed_sample": dict(list(changed.items())[:20]),
    }


def _mappings_semantically_equal(
    generated: dict[str, str | list[str]],
    reference: dict[str, str | list[str]],
) -> bool:
    if set(generated) != set(reference):
        return False
    return all(
        _mapping_target_set(generated[key]) == _mapping_target_set(reference[key])
        for key in generated
    )


def _build_no_match_policy_coverage_from_policies(policies) -> dict[str, str]:
    exported: dict[str, str] = {}
    for policy in policies:
        for keyword in sorted(policy.blocked_offer_keywords):
            exported[f"{policy.canonical} ! {keyword}"] = policy.canonical
        for pattern in policy.blocked_offer_patterns:
            exported[f"{policy.canonical} ! {pattern}"] = policy.canonical
    return dict(sorted(exported.items()))


def _build_no_match_policy_coverage_from_variants(
    variants: list[RegistryVariant],
) -> dict[str, str]:
    return dict(sorted(
        (variant.variant, variant.canonical)
        for variant in variants
        if variant.source_family == NO_MATCH_POLICY_SOURCE_FAMILY
    ))


def _build_match_bridge_coverage_from_bridges(bridges) -> dict[str, str | list[str]]:
    pairs: list[tuple[str, str]] = []
    for bridge in bridges:
        for ingredient_pattern in bridge.ingredient_patterns:
            for offer_pattern in bridge.offer_patterns:
                pairs.append((f"{ingredient_pattern} -> {offer_pattern}", bridge.canonical))
        for negative_pattern in bridge.negative_offer_patterns:
            pairs.append((f"{bridge.canonical} ! {negative_pattern}", bridge.canonical))
    return _mapping_from_pairs(pairs)


def _build_match_bridge_coverage_from_variants(
    variants: list[RegistryVariant],
) -> dict[str, str | list[str]]:
    return _mapping_from_pairs(
        (variant.variant, variant.canonical)
        for variant in variants
        if variant.source_family == MATCH_BRIDGE_SOURCE_FAMILY
    )


def _policy_signature(policy) -> dict[str, Any]:
    return {
        "id": policy.id,
        "rule_schema_version": policy.rule_schema_version,
        "rule_version": policy.rule_version,
        "canonical": policy.canonical,
        "ingredient_patterns": list(policy.ingredient_patterns),
        "blocked_offer_keywords": sorted(policy.blocked_offer_keywords),
        "blocked_offer_patterns": list(policy.blocked_offer_patterns),
        "allowed_specifics": sorted(policy.allowed_specifics),
        "reason": policy.reason,
        "policy_ref": policy.policy_ref,
        "fixture_refs": sorted(policy.fixture_refs),
        "supersedes": sorted(policy.supersedes),
    }


def _blocker_signature(blocker) -> dict[str, Any]:
    return {
        "id": blocker.id,
        "rule_schema_version": blocker.rule_schema_version,
        "rule_version": blocker.rule_version,
        "side": blocker.side,
        "code": blocker.code,
        "reason": blocker.reason,
        "policy_ref": blocker.policy_ref,
        "fixture_refs": sorted(blocker.fixture_refs),
    }


def _backend_allowance_signature(allowance) -> dict[str, Any]:
    return {
        "id": allowance.id,
        "rule_schema_version": allowance.rule_schema_version,
        "rule_version": allowance.rule_version,
        "code": allowance.code,
        "reason": allowance.reason,
        "policy_ref": allowance.policy_ref,
        "fixture_refs": sorted(allowance.fixture_refs),
    }


def _bridge_signature(bridge) -> dict[str, Any]:
    return {
        "id": bridge.id,
        "rule_schema_version": bridge.rule_schema_version,
        "rule_version": bridge.rule_version,
        "canonical": bridge.canonical,
        "ingredient_patterns": list(bridge.ingredient_patterns),
        "offer_patterns": list(bridge.offer_patterns),
        "negative_offer_patterns": list(bridge.negative_offer_patterns),
        "aliases": sorted(bridge.aliases),
        "fixture_refs": sorted(bridge.fixture_refs),
        "precedence": bridge.precedence,
        "supersedes": sorted(bridge.supersedes),
        "ingredient_form_signals": sorted(bridge.ingredient_form_signals),
        "offer_form_signals": sorted(bridge.offer_form_signals),
        "required_offer_form_signals": sorted(bridge.required_offer_form_signals),
        "forbidden_offer_form_signals": sorted(bridge.forbidden_offer_form_signals),
        "blockers": sorted(
            (_blocker_signature(blocker) for blocker in bridge.blockers),
            key=lambda item: item["id"],
        ),
        "backend_allowances": sorted(
            (_backend_allowance_signature(allowance) for allowance in bridge.backend_allowances),
            key=lambda item: item["id"],
        ),
    }


def _load_verified_terms_mapping_baseline(
    path: Path,
    *,
    source_family: str,
) -> tuple[dict[str, str | list[str]], list[CheckIssue]]:
    if not path.exists():
        return {}, [_issue(
            "error",
            "missing_verified_terms_baseline_json",
            "verified-term baseline JSON is required for export drift checks",
            item_id=str(path),
        )]
    payload = json.loads(path.read_text(encoding="utf-8"))
    variants = payload.get("variants") or []
    if not isinstance(variants, list):
        return {}, [_issue(
            "error",
            "invalid_verified_terms_baseline_json",
            "verified-term baseline variants payload must be a list",
            item_id=str(path),
        )]

    baseline_targets: dict[str, list[str]] = {}
    issues: list[CheckIssue] = []
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        if variant.get("source_type") != source_family:
            continue
        source = str(variant.get("variant_text") or "")
        target = str(variant.get("canonical") or "")
        if not source or not target:
            issues.append(_issue(
                "error",
                "invalid_mapping_baseline_row",
                f"verified-term {source_family} rows must include variant_text and canonical",
                item_id=str(variant.get("variant_id") or ""),
            ))
            continue
        targets = baseline_targets.setdefault(source, [])
        if target not in targets:
            targets.append(target)
    if not baseline_targets:
        issues.append(_issue(
            "error",
            "missing_mapping_baseline_rows",
            f"verified-term baseline contains no {source_family} rows",
            item_id=str(path),
        ))
    baseline = {
        source: targets[0] if len(targets) == 1 else targets
        for source, targets in sorted(baseline_targets.items())
    }
    return baseline, issues


def _compare_mapping_export(
    *,
    generated: dict[str, str | list[str]],
    baseline: dict[str, str | list[str]],
    selected_variants: list[RegistryVariant],
    item_id: str,
    source_family: str,
) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    if not selected_variants:
        issues.append(_issue(
            "error",
            "required_export_layer_missing",
            "registry view has no variants for the selected export source family",
            item_id=item_id,
            details={"source_family": source_family},
        ))
    generated_variant_count = _expanded_mapping_count(generated)
    selected_variant_count = _unique_variant_target_count(selected_variants)
    if generated_variant_count != selected_variant_count:
        issues.append(_issue(
            "error",
            "export_variant_count_mismatch",
            "generated export count does not match selected registry variant-target count",
            item_id=item_id,
            details={
                "generated": generated_variant_count,
                "selected_variant_targets": selected_variant_count,
                "selected_variant_rows": len(selected_variants),
            },
        ))
    if not _mappings_semantically_equal(generated, baseline):
        issues.append(_issue(
            "error",
            "export_verified_terms_baseline_mismatch",
            f"generated {item_id} export differs from the frozen verified-term baseline",
            item_id=item_id,
            details=_mapping_diff(generated, baseline),
        ))
    return issues


def _run_required_layer_failure_probe(
    *,
    variants: list[RegistryVariant],
    baseline: dict[str, str | list[str]],
    source_family: str,
    item_id: str,
    build_export,
) -> tuple[bool, list[str]]:
    probe_variants = [
        variant
        for variant in variants
        if variant.source_family != source_family
    ]
    probe_export = build_export(probe_variants)
    probe_issues = _compare_mapping_export(
        generated=probe_export,
        baseline=baseline,
        selected_variants=[],
        item_id=f"failure_probe:{item_id}_removed",
        source_family=source_family,
    )
    error_codes = [issue.code for issue in probe_issues if issue.severity == "error"]
    return bool(error_codes), error_codes


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = "." * node.level + module
            modules.append(module)
    return modules


def _run_runtime_import_boundary_check() -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    ingredient_routing_imports = _imported_modules(INGREDIENT_ROUTING_RUNTIME_FILE)
    keywords_imports = _imported_modules(KEYWORDS_RUNTIME_FILE)
    match_bridge_imports = _imported_modules(MATCH_BRIDGES_RUNTIME_FILE)
    no_match_policy_imports = _imported_modules(NO_MATCH_POLICIES_RUNTIME_FILE)
    parent_imports = _imported_modules(PARENT_MAPS_RUNTIME_FILE)
    synonyms_imports = _imported_modules(SYNONYMS_RUNTIME_FILE)
    term_indexes_imports = _imported_modules(TERM_INDEXES_RUNTIME_FILE)
    export_imports = _imported_modules(EXPORTS_RUNTIME_FILE)
    if ".term_registry.exports" not in ingredient_routing_imports:
        issues.append(_issue(
            "error",
            "runtime_export_import_missing",
            "ingredient_routing.py must import the selected mapping from term_registry.exports",
            item_id=str(INGREDIENT_ROUTING_RUNTIME_FILE.relative_to(REPO_DIR)),
            details={"imports": ingredient_routing_imports},
        ))
    if ".term_registry.exports" not in keywords_imports:
        issues.append(_issue(
            "error",
            "runtime_export_import_missing",
            "keywords.py must import the selected mapping from term_registry.exports",
            item_id=str(KEYWORDS_RUNTIME_FILE.relative_to(REPO_DIR)),
            details={"imports": keywords_imports},
        ))
    if ".term_registry.exports" not in match_bridge_imports:
        issues.append(_issue(
            "error",
            "runtime_export_import_missing",
            "match_bridges.py must import the selected rules from term_registry.exports",
            item_id=str(MATCH_BRIDGES_RUNTIME_FILE.relative_to(REPO_DIR)),
            details={"imports": match_bridge_imports},
        ))
    if ".term_registry.exports" not in no_match_policy_imports:
        issues.append(_issue(
            "error",
            "runtime_export_import_missing",
            "no_match_policies.py must import the selected rules from term_registry.exports",
            item_id=str(NO_MATCH_POLICIES_RUNTIME_FILE.relative_to(REPO_DIR)),
            details={"imports": no_match_policy_imports},
        ))
    if ".term_registry.exports" not in parent_imports:
        issues.append(_issue(
            "error",
            "runtime_export_import_missing",
            "parent_maps.py must import the selected mapping from term_registry.exports",
            item_id=str(PARENT_MAPS_RUNTIME_FILE.relative_to(REPO_DIR)),
            details={"imports": parent_imports},
        ))
    if ".term_registry.exports" not in synonyms_imports:
        issues.append(_issue(
            "error",
            "runtime_export_import_missing",
            "synonyms.py must import the selected mapping from term_registry.exports",
            item_id=str(SYNONYMS_RUNTIME_FILE.relative_to(REPO_DIR)),
            details={"imports": synonyms_imports},
        ))
    if ".term_registry.exports" not in term_indexes_imports:
        issues.append(_issue(
            "error",
            "runtime_export_import_missing",
            "term_indexes.py must import the selected mapping from term_registry.exports",
            item_id=str(TERM_INDEXES_RUNTIME_FILE.relative_to(REPO_DIR)),
            details={"imports": term_indexes_imports},
        ))

    forbidden_markers = (
        "legacy_inventory",
        "run_verified_term_audit",
        "ingredient_matching.ingredient_routing",
        ".ingredient_routing",
        "ingredient_matching.parent_maps",
        ".parent_maps",
        "ingredient_matching.term_indexes",
        ".term_indexes",
    )
    for path, imports in (
        (INGREDIENT_ROUTING_RUNTIME_FILE, ingredient_routing_imports),
        (KEYWORDS_RUNTIME_FILE, keywords_imports),
        (MATCH_BRIDGES_RUNTIME_FILE, match_bridge_imports),
        (NO_MATCH_POLICIES_RUNTIME_FILE, no_match_policy_imports),
        (PARENT_MAPS_RUNTIME_FILE, parent_imports),
        (SYNONYMS_RUNTIME_FILE, synonyms_imports),
        (EXPORTS_RUNTIME_FILE, export_imports),
    ):
        forbidden = [
            module
            for module in imports
            if any(marker in module for marker in forbidden_markers)
        ]
        if forbidden:
            issues.append(_issue(
                "error",
                "runtime_import_boundary_violation",
                "selected runtime import path must not import legacy inventory or its legacy source module",
                item_id=str(path.relative_to(REPO_DIR)),
                details={"imports": forbidden},
            ))
    export_forbidden_markers = (
        "ingredient_matching.keywords",
        ".keywords",
        "ingredient_matching.match_bridges",
        ".match_bridges",
        "ingredient_matching.no_match_policies",
        ".no_match_policies",
        "ingredient_matching.synonyms",
        ".synonyms",
    )
    export_forbidden = [
        module
        for module in export_imports
        if any(marker in module for marker in export_forbidden_markers)
    ]
    if export_forbidden:
        issues.append(_issue(
            "error",
            "runtime_import_boundary_violation",
            "registry exports must not import the synonyms runtime source module",
            item_id=str(EXPORTS_RUNTIME_FILE.relative_to(REPO_DIR)),
            details={"imports": export_forbidden},
        ))
    return issues


def _run_targeted_runtime_sanity() -> list[CheckIssue]:
    from languages.sv.ingredient_matching.matching import matches_ingredient  # noqa: PLC0415
    from languages.sv.ingredient_matching.term_indexes import _recipe_routing_extra_aliases  # noqa: PLC0415

    sanity_cases = [
        ("pepparsalami routes to salami", ["pepparsalami"], "salami", "salami"),
        ("kalkonbröst routes to kalkon", ["kalkonbröst"], "kalkon", "kalkon"),
    ]
    issues: list[CheckIssue] = []
    for name, product_keywords, ingredient_text, expected in sanity_cases:
        actual = matches_ingredient(product_keywords, ingredient_text)
        if actual != expected:
            issues.append(_issue(
                "error",
                "targeted_runtime_sanity_failed",
                "selected legacy mapping no longer behaves as expected in runtime matcher",
                item_id=name,
                details={
                    "product_keywords": product_keywords,
                    "ingredient_text": ingredient_text,
                    "expected": expected,
                    "actual": actual,
                },
            ))
    keyword_extra_cases = [
        ("matbrödsjäst routes to jäst", "matbrödsjäst", "jäst"),
        ("lammracks keeps lamb and lamb meat routes", "lammracks", ["lamm", "lammkött"]),
    ]
    for name, variant, expected in keyword_extra_cases:
        actual = PUBLIC_KEYWORD_EXTRA_PARENTS.get(variant)
        if actual != expected:
            issues.append(_issue(
                "error",
                "targeted_runtime_sanity_failed",
                "selected keyword extra parent mapping no longer exposes the expected parent",
                item_id=name,
                details={"variant": variant, "expected": expected, "actual": actual},
            ))
    offer_extra_cases = [
        ("bryggkaffe exposes bryggkaffe/kokkaffe", "bryggkaffe", ["bryggkaffe", "kokkaffe"]),
        ("körsbärstomater exposes singular tomato", "körsbärstomater", ["körsbärstomater", "körsbärstomat"]),
    ]
    for name, variant, expected in offer_extra_cases:
        actual = PUBLIC_OFFER_EXTRA_KEYWORDS.get(variant)
        if actual != expected:
            issues.append(_issue(
                "error",
                "targeted_runtime_sanity_failed",
                "selected offer extra keyword mapping no longer exposes the expected extra keywords",
                item_id=name,
                details={"variant": variant, "expected": expected, "actual": actual},
            ))
    ingredient_parent_cases = [
        ("körsbärstomat maps to småtomat", "körsbärstomat", "småtomat"),
        ("blockchoklad maps to bakchoklad", "blockchoklad", "bakchoklad"),
    ]
    for name, variant, expected in ingredient_parent_cases:
        actual = PUBLIC_INGREDIENT_PARENTS.get(variant)
        if actual != expected:
            issues.append(_issue(
                "error",
                "targeted_runtime_sanity_failed",
                "selected ingredient parent mapping no longer exposes the expected parent",
                item_id=name,
                details={"variant": variant, "expected": expected, "actual": actual},
            ))
    keyword_synonym_cases = [
        ("fries normalizes to pommes", "fries", "pommes"),
        ("tzaybitar normalizes to vegobitar", "tzaybitar", "vegobitar"),
    ]
    for name, variant, expected in keyword_synonym_cases:
        actual = PUBLIC_KEYWORD_SYNONYMS.get(variant)
        if actual != expected:
            issues.append(_issue(
                "error",
                "targeted_runtime_sanity_failed",
                "selected keyword synonym mapping no longer exposes the expected canonical",
                item_id=name,
                details={"variant": variant, "expected": expected, "actual": actual},
            ))
    routing_cases = [
        ("snabbkaffepulver routes to snabbkaffe", "snabbkaffepulver", "snabbkaffe"),
        ("rödvinbärsgele routes to vinbärsgele", "rödvinbärsgele", "vinbärsgele"),
    ]
    for name, variant, expected in routing_cases:
        actual = PUBLIC_INGREDIENT_ROUTING_PARENT_TERMS.get(variant)
        if actual != expected:
            issues.append(_issue(
                "error",
                "targeted_runtime_sanity_failed",
                "selected ingredient routing parent mapping no longer exposes the expected route term",
                item_id=name,
                details={"variant": variant, "expected": expected, "actual": actual},
            ))
    recipe_routing_cases = [
        ("hel kyckling exposes helkyckling", "hel kyckling", "helkyckling"),
        ("snabbkaffepulver exposes snabbkaffe", "snabbkaffepulver", "snabbkaffe"),
        ("tortillabröd exposes tortilla", "tortillabröd", "tortilla"),
    ]
    for name, normalized_text, expected in recipe_routing_cases:
        actual = _recipe_routing_extra_aliases(normalized_text)
        if expected not in actual:
            issues.append(_issue(
                "error",
                "targeted_runtime_sanity_failed",
                "selected recipe routing helper no longer exposes the expected registry alias",
                item_id=name,
                details={"normalized_text": normalized_text, "expected": expected, "actual": list(actual)},
            ))
    return issues


def _load_language_variants(language: str, batch_size: int) -> list[RegistryVariant]:
    if language != "sv":
        raise ValueError("R1 currently supports --language sv only")
    return build_legacy_registry_variants(batch_size=batch_size)


def run_checks(args: argparse.Namespace) -> tuple[dict[str, Any], list[CheckIssue]]:
    issues: list[CheckIssue] = []
    parent_verified_terms_baseline, parent_baseline_issues = _load_verified_terms_mapping_baseline(
        args.baseline_json,
        source_family=PARENT_MATCH_ONLY_SOURCE_FAMILY,
    )
    keyword_synonym_verified_terms_baseline, keyword_synonym_baseline_issues = _load_verified_terms_mapping_baseline(
        args.baseline_json,
        source_family=KEYWORD_SYNONYM_SOURCE_FAMILY,
    )
    ingredient_parent_verified_terms_baseline, ingredient_parent_baseline_issues = _load_verified_terms_mapping_baseline(
        args.baseline_json,
        source_family=INGREDIENT_PARENT_SOURCE_FAMILY,
    )
    routing_verified_terms_baseline, routing_baseline_issues = _load_verified_terms_mapping_baseline(
        args.baseline_json,
        source_family=INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY,
    )
    keyword_extra_verified_terms_baseline, keyword_extra_baseline_issues = _load_verified_terms_mapping_baseline(
        args.baseline_json,
        source_family=KEYWORD_EXTRA_PARENT_SOURCE_FAMILY,
    )
    offer_extra_verified_terms_baseline, offer_extra_baseline_issues = _load_verified_terms_mapping_baseline(
        args.baseline_json,
        source_family=OFFER_EXTRA_KEYWORD_SOURCE_FAMILY,
    )
    no_match_policy_verified_terms_baseline, no_match_policy_baseline_issues = _load_verified_terms_mapping_baseline(
        args.baseline_json,
        source_family=NO_MATCH_POLICY_SOURCE_FAMILY,
    )
    match_bridge_verified_terms_baseline, match_bridge_baseline_issues = _load_verified_terms_mapping_baseline(
        args.baseline_json,
        source_family=MATCH_BRIDGE_SOURCE_FAMILY,
    )
    recipe_routing_verified_terms_baseline, recipe_routing_baseline_issues = _load_verified_terms_mapping_baseline(
        args.baseline_json,
        source_family=RECIPE_ROUTING_HELPER_SOURCE_FAMILY,
    )
    issues.extend(parent_baseline_issues)
    issues.extend(keyword_synonym_baseline_issues)
    issues.extend(ingredient_parent_baseline_issues)
    issues.extend(routing_baseline_issues)
    issues.extend(keyword_extra_baseline_issues)
    issues.extend(offer_extra_baseline_issues)
    issues.extend(no_match_policy_baseline_issues)
    issues.extend(match_bridge_baseline_issues)
    issues.extend(recipe_routing_baseline_issues)
    variants = _load_language_variants(args.language, args.batch_size)
    selected_parent_variants = [
        variant
        for variant in variants
        if variant.source_family == PARENT_MATCH_ONLY_SOURCE_FAMILY
    ]
    selected_keyword_synonym_variants = [
        variant
        for variant in variants
        if variant.source_family == KEYWORD_SYNONYM_SOURCE_FAMILY
    ]
    selected_ingredient_parent_variants = [
        variant
        for variant in variants
        if variant.source_family == INGREDIENT_PARENT_SOURCE_FAMILY
    ]
    selected_routing_variants = [
        variant
        for variant in variants
        if variant.source_family == INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY
    ]
    selected_keyword_extra_variants = [
        variant
        for variant in variants
        if variant.source_family == KEYWORD_EXTRA_PARENT_SOURCE_FAMILY
    ]
    selected_offer_extra_variants = [
        variant
        for variant in variants
        if variant.source_family == OFFER_EXTRA_KEYWORD_SOURCE_FAMILY
    ]
    selected_no_match_policy_variants = [
        variant
        for variant in variants
        if variant.source_family == NO_MATCH_POLICY_SOURCE_FAMILY
    ]
    selected_match_bridge_variants = [
        variant
        for variant in variants
        if variant.source_family == MATCH_BRIDGE_SOURCE_FAMILY
    ]
    selected_recipe_routing_variants = [
        variant
        for variant in variants
        if variant.source_family == RECIPE_ROUTING_HELPER_SOURCE_FAMILY
    ]
    generated_parent_from_variants = build_parent_match_only_export(variants)
    generated_parent_static = _normalize_mapping(GENERATED_PARENT_MATCH_ONLY)
    public_parent_runtime = _normalize_mapping(PUBLIC_PARENT_MATCH_ONLY)
    generated_keyword_synonym_from_variants = build_keyword_synonyms_export(variants)
    generated_keyword_synonym_static = _normalize_mapping(GENERATED_KEYWORD_SYNONYMS)
    public_keyword_synonym_runtime = _normalize_mapping(PUBLIC_KEYWORD_SYNONYMS)
    generated_ingredient_parent_from_variants = build_ingredient_parents_export(variants)
    generated_ingredient_parent_static = _normalize_mapping(GENERATED_INGREDIENT_PARENTS)
    public_ingredient_parent_runtime = _normalize_mapping(PUBLIC_INGREDIENT_PARENTS)
    generated_routing_from_variants = build_ingredient_routing_parent_export(variants)
    generated_routing_static = _normalize_mapping(GENERATED_INGREDIENT_ROUTING_PARENT_TERMS)
    public_routing_runtime = _normalize_mapping(PUBLIC_INGREDIENT_ROUTING_PARENT_TERMS)
    generated_keyword_extra_from_variants = build_keyword_extra_parents_export(variants)
    generated_keyword_extra_static = _normalize_mapping(GENERATED_KEYWORD_EXTRA_PARENTS)
    public_keyword_extra_runtime = _normalize_mapping(PUBLIC_KEYWORD_EXTRA_PARENTS)
    generated_offer_extra_from_variants = build_offer_extra_keywords_export(variants)
    generated_offer_extra_static = _normalize_mapping(GENERATED_OFFER_EXTRA_KEYWORDS)
    public_offer_extra_runtime = _normalize_mapping(PUBLIC_OFFER_EXTRA_KEYWORDS)
    generated_no_match_policy_static = _build_no_match_policy_coverage_from_policies(
        GENERATED_NO_MATCH_POLICIES
    )
    public_no_match_policy_runtime = _build_no_match_policy_coverage_from_policies(
        PUBLIC_NO_MATCH_POLICIES
    )
    generated_match_bridge_static = _build_match_bridge_coverage_from_bridges(
        GENERATED_MATCH_BRIDGES
    )
    public_match_bridge_runtime = _build_match_bridge_coverage_from_bridges(
        PUBLIC_MATCH_BRIDGES
    )
    generated_recipe_routing_from_variants = build_recipe_routing_extra_alias_export(variants)
    generated_recipe_routing_static = _normalize_mapping(GENERATED_RECIPE_ROUTING_EXTRA_ALIASES)

    issues.extend(_compare_mapping_export(
        generated=generated_parent_static,
        baseline=parent_verified_terms_baseline,
        selected_variants=selected_parent_variants,
        item_id="PARENT_MATCH_ONLY",
        source_family=PARENT_MATCH_ONLY_SOURCE_FAMILY,
    ))
    if not _mappings_semantically_equal(generated_parent_from_variants, generated_parent_static):
        issues.append(_issue(
            "error",
            "generated_export_builder_mismatch",
            "builder output from current registry view differs from the static runtime export",
            item_id="PARENT_MATCH_ONLY",
            details=_mapping_diff(generated_parent_from_variants, generated_parent_static),
        ))
    if not _mappings_semantically_equal(public_parent_runtime, generated_parent_static):
        issues.append(_issue(
            "error",
            "public_runtime_export_mismatch",
            "parent_maps.PARENT_MATCH_ONLY differs from the generated registry export",
            item_id="PARENT_MATCH_ONLY",
            details=_mapping_diff(public_parent_runtime, generated_parent_static),
        ))

    issues.extend(_compare_mapping_export(
        generated=generated_keyword_synonym_static,
        baseline=keyword_synonym_verified_terms_baseline,
        selected_variants=selected_keyword_synonym_variants,
        item_id="KEYWORD_SYNONYMS",
        source_family=KEYWORD_SYNONYM_SOURCE_FAMILY,
    ))
    if not _mappings_semantically_equal(generated_keyword_synonym_from_variants, generated_keyword_synonym_static):
        issues.append(_issue(
            "error",
            "generated_export_builder_mismatch",
            "builder output from current registry view differs from the static runtime export",
            item_id="KEYWORD_SYNONYMS",
            details=_mapping_diff(generated_keyword_synonym_from_variants, generated_keyword_synonym_static),
        ))
    if not _mappings_semantically_equal(public_keyword_synonym_runtime, generated_keyword_synonym_static):
        issues.append(_issue(
            "error",
            "public_runtime_export_mismatch",
            "synonyms.KEYWORD_SYNONYMS differs from the generated registry export",
            item_id="KEYWORD_SYNONYMS",
            details=_mapping_diff(public_keyword_synonym_runtime, generated_keyword_synonym_static),
        ))

    issues.extend(_compare_mapping_export(
        generated=generated_ingredient_parent_static,
        baseline=ingredient_parent_verified_terms_baseline,
        selected_variants=selected_ingredient_parent_variants,
        item_id="INGREDIENT_PARENTS",
        source_family=INGREDIENT_PARENT_SOURCE_FAMILY,
    ))
    if not _mappings_semantically_equal(
        generated_ingredient_parent_from_variants,
        generated_ingredient_parent_static,
    ):
        issues.append(_issue(
            "error",
            "generated_export_builder_mismatch",
            "builder output from current registry view differs from the static runtime export",
            item_id="INGREDIENT_PARENTS",
            details=_mapping_diff(
                generated_ingredient_parent_from_variants,
                generated_ingredient_parent_static,
            ),
        ))
    if not _mappings_semantically_equal(public_ingredient_parent_runtime, generated_ingredient_parent_static):
        issues.append(_issue(
            "error",
            "public_runtime_export_mismatch",
            "synonyms.INGREDIENT_PARENTS differs from the generated registry export",
            item_id="INGREDIENT_PARENTS",
            details=_mapping_diff(public_ingredient_parent_runtime, generated_ingredient_parent_static),
        ))

    issues.extend(_compare_mapping_export(
        generated=generated_routing_static,
        baseline=routing_verified_terms_baseline,
        selected_variants=selected_routing_variants,
        item_id="INGREDIENT_ROUTING_PARENT_TERMS",
        source_family=INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY,
    ))
    if not _mappings_semantically_equal(generated_routing_from_variants, generated_routing_static):
        issues.append(_issue(
            "error",
            "generated_export_builder_mismatch",
            "builder output from current registry view differs from the static runtime export",
            item_id="INGREDIENT_ROUTING_PARENT_TERMS",
            details=_mapping_diff(generated_routing_from_variants, generated_routing_static),
        ))
    if not _mappings_semantically_equal(public_routing_runtime, generated_routing_static):
        issues.append(_issue(
            "error",
            "public_runtime_export_mismatch",
            "ingredient_routing._ROUTING_PARENT_TERMS differs from the generated registry export",
            item_id="INGREDIENT_ROUTING_PARENT_TERMS",
            details=_mapping_diff(public_routing_runtime, generated_routing_static),
        ))

    issues.extend(_compare_mapping_export(
        generated=generated_keyword_extra_static,
        baseline=keyword_extra_verified_terms_baseline,
        selected_variants=selected_keyword_extra_variants,
        item_id="KEYWORD_EXTRA_PARENTS",
        source_family=KEYWORD_EXTRA_PARENT_SOURCE_FAMILY,
    ))
    if not _mappings_semantically_equal(generated_keyword_extra_from_variants, generated_keyword_extra_static):
        issues.append(_issue(
            "error",
            "generated_export_builder_mismatch",
            "builder output from current registry view differs from the static runtime export",
            item_id="KEYWORD_EXTRA_PARENTS",
            details=_mapping_diff(generated_keyword_extra_from_variants, generated_keyword_extra_static),
        ))
    if not _mappings_semantically_equal(public_keyword_extra_runtime, generated_keyword_extra_static):
        issues.append(_issue(
            "error",
            "public_runtime_export_mismatch",
            "parent_maps.KEYWORD_EXTRA_PARENTS differs from the generated registry export",
            item_id="KEYWORD_EXTRA_PARENTS",
            details=_mapping_diff(public_keyword_extra_runtime, generated_keyword_extra_static),
        ))

    issues.extend(_compare_mapping_export(
        generated=generated_offer_extra_static,
        baseline=offer_extra_verified_terms_baseline,
        selected_variants=selected_offer_extra_variants,
        item_id="OFFER_EXTRA_KEYWORDS",
        source_family=OFFER_EXTRA_KEYWORD_SOURCE_FAMILY,
    ))
    if not _mappings_semantically_equal(generated_offer_extra_from_variants, generated_offer_extra_static):
        issues.append(_issue(
            "error",
            "generated_export_builder_mismatch",
            "builder output from current registry view differs from the static runtime export",
            item_id="OFFER_EXTRA_KEYWORDS",
            details=_mapping_diff(generated_offer_extra_from_variants, generated_offer_extra_static),
        ))
    if not _mappings_semantically_equal(public_offer_extra_runtime, generated_offer_extra_static):
        issues.append(_issue(
            "error",
            "public_runtime_export_mismatch",
            "keywords.OFFER_EXTRA_KEYWORDS differs from the generated registry export",
            item_id="OFFER_EXTRA_KEYWORDS",
            details=_mapping_diff(public_offer_extra_runtime, generated_offer_extra_static),
        ))

    issues.extend(_compare_mapping_export(
        generated=generated_no_match_policy_static,
        baseline=no_match_policy_verified_terms_baseline,
        selected_variants=selected_no_match_policy_variants,
        item_id="NO_MATCH_POLICIES",
        source_family=NO_MATCH_POLICY_SOURCE_FAMILY,
    ))
    if not _mappings_semantically_equal(public_no_match_policy_runtime, generated_no_match_policy_static):
        issues.append(_issue(
            "error",
            "public_runtime_export_mismatch",
            "no_match_policies.NO_MATCH_POLICIES differs from the generated registry export",
            item_id="NO_MATCH_POLICIES",
            details=_mapping_diff(public_no_match_policy_runtime, generated_no_match_policy_static),
        ))
    generated_policy_signatures = [_policy_signature(policy) for policy in GENERATED_NO_MATCH_POLICIES]
    public_policy_signatures = [_policy_signature(policy) for policy in PUBLIC_NO_MATCH_POLICIES]
    if public_policy_signatures != generated_policy_signatures:
        issues.append(_issue(
            "error",
            "public_runtime_export_mismatch",
            "no_match_policies.NO_MATCH_POLICIES object payload differs from the generated registry export",
            item_id="NO_MATCH_POLICIES",
            details={
                "generated_count": len(generated_policy_signatures),
                "public_count": len(public_policy_signatures),
            },
        ))

    issues.extend(_compare_mapping_export(
        generated=generated_match_bridge_static,
        baseline=match_bridge_verified_terms_baseline,
        selected_variants=selected_match_bridge_variants,
        item_id="MATCH_BRIDGES",
        source_family=MATCH_BRIDGE_SOURCE_FAMILY,
    ))
    if not _mappings_semantically_equal(public_match_bridge_runtime, generated_match_bridge_static):
        issues.append(_issue(
            "error",
            "public_runtime_export_mismatch",
            "match_bridges.MATCH_BRIDGES coverage differs from the generated registry export",
            item_id="MATCH_BRIDGES",
            details=_mapping_diff(public_match_bridge_runtime, generated_match_bridge_static),
        ))
    generated_bridge_signatures = [_bridge_signature(bridge) for bridge in GENERATED_MATCH_BRIDGES]
    public_bridge_signatures = [_bridge_signature(bridge) for bridge in PUBLIC_MATCH_BRIDGES]
    if public_bridge_signatures != generated_bridge_signatures:
        issues.append(_issue(
            "error",
            "public_runtime_export_mismatch",
            "match_bridges.MATCH_BRIDGES object payload differs from the generated registry export",
            item_id="MATCH_BRIDGES",
            details={
                "generated_count": len(generated_bridge_signatures),
                "public_count": len(public_bridge_signatures),
            },
        ))

    issues.extend(_compare_mapping_export(
        generated=generated_recipe_routing_static,
        baseline=recipe_routing_verified_terms_baseline,
        selected_variants=selected_recipe_routing_variants,
        item_id="RECIPE_ROUTING_EXTRA_ALIASES",
        source_family=RECIPE_ROUTING_HELPER_SOURCE_FAMILY,
    ))
    if not _mappings_semantically_equal(generated_recipe_routing_from_variants, generated_recipe_routing_static):
        issues.append(_issue(
            "error",
            "generated_export_builder_mismatch",
            "builder output from current registry view differs from the static runtime export",
            item_id="RECIPE_ROUTING_EXTRA_ALIASES",
            details=_mapping_diff(generated_recipe_routing_from_variants, generated_recipe_routing_static),
        ))

    parent_failure_probe_passed, parent_failure_probe_error_codes = _run_required_layer_failure_probe(
        variants=variants,
        baseline=parent_verified_terms_baseline,
        source_family=PARENT_MATCH_ONLY_SOURCE_FAMILY,
        item_id="PARENT_MATCH_ONLY",
        build_export=build_parent_match_only_export,
    )
    keyword_synonym_failure_probe_passed, keyword_synonym_failure_probe_error_codes = (
        _run_required_layer_failure_probe(
            variants=variants,
            baseline=keyword_synonym_verified_terms_baseline,
            source_family=KEYWORD_SYNONYM_SOURCE_FAMILY,
            item_id="KEYWORD_SYNONYMS",
            build_export=build_keyword_synonyms_export,
        )
    )
    ingredient_parent_failure_probe_passed, ingredient_parent_failure_probe_error_codes = (
        _run_required_layer_failure_probe(
            variants=variants,
            baseline=ingredient_parent_verified_terms_baseline,
            source_family=INGREDIENT_PARENT_SOURCE_FAMILY,
            item_id="INGREDIENT_PARENTS",
            build_export=build_ingredient_parents_export,
        )
    )
    routing_failure_probe_passed, routing_failure_probe_error_codes = _run_required_layer_failure_probe(
        variants=variants,
        baseline=routing_verified_terms_baseline,
        source_family=INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY,
        item_id="INGREDIENT_ROUTING_PARENT_TERMS",
        build_export=build_ingredient_routing_parent_export,
    )
    keyword_extra_failure_probe_passed, keyword_extra_failure_probe_error_codes = (
        _run_required_layer_failure_probe(
            variants=variants,
            baseline=keyword_extra_verified_terms_baseline,
            source_family=KEYWORD_EXTRA_PARENT_SOURCE_FAMILY,
            item_id="KEYWORD_EXTRA_PARENTS",
            build_export=build_keyword_extra_parents_export,
        )
    )
    offer_extra_failure_probe_passed, offer_extra_failure_probe_error_codes = (
        _run_required_layer_failure_probe(
            variants=variants,
            baseline=offer_extra_verified_terms_baseline,
            source_family=OFFER_EXTRA_KEYWORD_SOURCE_FAMILY,
            item_id="OFFER_EXTRA_KEYWORDS",
            build_export=build_offer_extra_keywords_export,
        )
    )
    no_match_policy_failure_probe_passed, no_match_policy_failure_probe_error_codes = (
        _run_required_layer_failure_probe(
            variants=variants,
            baseline=no_match_policy_verified_terms_baseline,
            source_family=NO_MATCH_POLICY_SOURCE_FAMILY,
            item_id="NO_MATCH_POLICIES",
            build_export=_build_no_match_policy_coverage_from_variants,
        )
    )
    match_bridge_failure_probe_passed, match_bridge_failure_probe_error_codes = (
        _run_required_layer_failure_probe(
            variants=variants,
            baseline=match_bridge_verified_terms_baseline,
            source_family=MATCH_BRIDGE_SOURCE_FAMILY,
            item_id="MATCH_BRIDGES",
            build_export=_build_match_bridge_coverage_from_variants,
        )
    )
    recipe_routing_failure_probe_passed, recipe_routing_failure_probe_error_codes = (
        _run_required_layer_failure_probe(
            variants=variants,
            baseline=recipe_routing_verified_terms_baseline,
            source_family=RECIPE_ROUTING_HELPER_SOURCE_FAMILY,
            item_id="RECIPE_ROUTING_EXTRA_ALIASES",
            build_export=build_recipe_routing_extra_alias_export,
        )
    )
    for item_id, passed in (
        ("PARENT_MATCH_ONLY", parent_failure_probe_passed),
        ("KEYWORD_SYNONYMS", keyword_synonym_failure_probe_passed),
        ("INGREDIENT_PARENTS", ingredient_parent_failure_probe_passed),
        ("INGREDIENT_ROUTING_PARENT_TERMS", routing_failure_probe_passed),
        ("KEYWORD_EXTRA_PARENTS", keyword_extra_failure_probe_passed),
        ("OFFER_EXTRA_KEYWORDS", offer_extra_failure_probe_passed),
        ("NO_MATCH_POLICIES", no_match_policy_failure_probe_passed),
        ("MATCH_BRIDGES", match_bridge_failure_probe_passed),
        ("RECIPE_ROUTING_EXTRA_ALIASES", recipe_routing_failure_probe_passed),
    ):
        if not passed:
            issues.append(_issue(
                "error",
                "required_layer_failure_probe_failed",
                "export check did not fail when the selected registry layer was removed",
                item_id=item_id,
            ))

    boundary_issues = _run_runtime_import_boundary_check()
    issues.extend(boundary_issues)
    if not args.skip_runtime_sanity:
        issues.extend(_run_targeted_runtime_sanity())

    issue_counts = Counter(issue.severity for issue in issues)
    source_counts = Counter(variant.source_family for variant in variants)
    summary = {
        "language": args.language,
        "market": args.market,
        "selected_exports": [
            "PARENT_MATCH_ONLY",
            "KEYWORD_SYNONYMS",
            "INGREDIENT_PARENTS",
            "KEYWORD_EXTRA_PARENTS",
            "OFFER_EXTRA_KEYWORDS",
            "NO_MATCH_POLICIES",
            "MATCH_BRIDGES",
            "INGREDIENT_ROUTING_PARENT_TERMS",
            "RECIPE_ROUTING_EXTRA_ALIASES",
        ],
        "selected_source_families": [
            PARENT_MATCH_ONLY_SOURCE_FAMILY,
            KEYWORD_SYNONYM_SOURCE_FAMILY,
            INGREDIENT_PARENT_SOURCE_FAMILY,
            KEYWORD_EXTRA_PARENT_SOURCE_FAMILY,
            OFFER_EXTRA_KEYWORD_SOURCE_FAMILY,
            NO_MATCH_POLICY_SOURCE_FAMILY,
            MATCH_BRIDGE_SOURCE_FAMILY,
            INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY,
            RECIPE_ROUTING_HELPER_SOURCE_FAMILY,
        ],
        "verified_terms_baseline_file": str(args.baseline_json.relative_to(REPO_DIR)),
        "registry_variant_count": len(variants),
        "selected_variant_counts": {
            "PARENT_MATCH_ONLY": len(selected_parent_variants),
            "KEYWORD_SYNONYMS": len(selected_keyword_synonym_variants),
            "INGREDIENT_PARENTS": len(selected_ingredient_parent_variants),
            "KEYWORD_EXTRA_PARENTS": len(selected_keyword_extra_variants),
            "OFFER_EXTRA_KEYWORDS": len(selected_offer_extra_variants),
            "NO_MATCH_POLICIES": len(selected_no_match_policy_variants),
            "MATCH_BRIDGES": len(selected_match_bridge_variants),
            "INGREDIENT_ROUTING_PARENT_TERMS": len(selected_routing_variants),
            "RECIPE_ROUTING_EXTRA_ALIASES": len(selected_recipe_routing_variants),
        },
        "generated_export_counts": {
            "PARENT_MATCH_ONLY": _expanded_mapping_count(generated_parent_static),
            "KEYWORD_SYNONYMS": _expanded_mapping_count(generated_keyword_synonym_static),
            "INGREDIENT_PARENTS": _expanded_mapping_count(generated_ingredient_parent_static),
            "KEYWORD_EXTRA_PARENTS": _expanded_mapping_count(generated_keyword_extra_static),
            "OFFER_EXTRA_KEYWORDS": _expanded_mapping_count(generated_offer_extra_static),
            "NO_MATCH_POLICIES": _expanded_mapping_count(generated_no_match_policy_static),
            "MATCH_BRIDGES": _expanded_mapping_count(generated_match_bridge_static),
            "INGREDIENT_ROUTING_PARENT_TERMS": _expanded_mapping_count(generated_routing_static),
            "RECIPE_ROUTING_EXTRA_ALIASES": _expanded_mapping_count(generated_recipe_routing_static),
        },
        "verified_terms_baseline_export_counts": {
            "PARENT_MATCH_ONLY": _expanded_mapping_count(parent_verified_terms_baseline),
            "KEYWORD_SYNONYMS": _expanded_mapping_count(keyword_synonym_verified_terms_baseline),
            "INGREDIENT_PARENTS": _expanded_mapping_count(ingredient_parent_verified_terms_baseline),
            "KEYWORD_EXTRA_PARENTS": _expanded_mapping_count(keyword_extra_verified_terms_baseline),
            "OFFER_EXTRA_KEYWORDS": _expanded_mapping_count(offer_extra_verified_terms_baseline),
            "NO_MATCH_POLICIES": _expanded_mapping_count(no_match_policy_verified_terms_baseline),
            "MATCH_BRIDGES": _expanded_mapping_count(match_bridge_verified_terms_baseline),
            "INGREDIENT_ROUTING_PARENT_TERMS": _expanded_mapping_count(routing_verified_terms_baseline),
            "RECIPE_ROUTING_EXTRA_ALIASES": _expanded_mapping_count(recipe_routing_verified_terms_baseline),
        },
        "public_runtime_export_counts": {
            "PARENT_MATCH_ONLY": _expanded_mapping_count(public_parent_runtime),
            "KEYWORD_SYNONYMS": _expanded_mapping_count(public_keyword_synonym_runtime),
            "INGREDIENT_PARENTS": _expanded_mapping_count(public_ingredient_parent_runtime),
            "KEYWORD_EXTRA_PARENTS": _expanded_mapping_count(public_keyword_extra_runtime),
            "OFFER_EXTRA_KEYWORDS": _expanded_mapping_count(public_offer_extra_runtime),
            "NO_MATCH_POLICIES": _expanded_mapping_count(public_no_match_policy_runtime),
            "MATCH_BRIDGES": _expanded_mapping_count(public_match_bridge_runtime),
            "INGREDIENT_ROUTING_PARENT_TERMS": _expanded_mapping_count(public_routing_runtime),
            "RECIPE_ROUTING_EXTRA_ALIASES": _expanded_mapping_count(generated_recipe_routing_static),
        },
        "failure_probe_passed": {
            "PARENT_MATCH_ONLY": parent_failure_probe_passed,
            "KEYWORD_SYNONYMS": keyword_synonym_failure_probe_passed,
            "INGREDIENT_PARENTS": ingredient_parent_failure_probe_passed,
            "KEYWORD_EXTRA_PARENTS": keyword_extra_failure_probe_passed,
            "OFFER_EXTRA_KEYWORDS": offer_extra_failure_probe_passed,
            "NO_MATCH_POLICIES": no_match_policy_failure_probe_passed,
            "MATCH_BRIDGES": match_bridge_failure_probe_passed,
            "INGREDIENT_ROUTING_PARENT_TERMS": routing_failure_probe_passed,
            "RECIPE_ROUTING_EXTRA_ALIASES": recipe_routing_failure_probe_passed,
        },
        "failure_probe_error_codes": {
            "PARENT_MATCH_ONLY": parent_failure_probe_error_codes,
            "KEYWORD_SYNONYMS": keyword_synonym_failure_probe_error_codes,
            "INGREDIENT_PARENTS": ingredient_parent_failure_probe_error_codes,
            "KEYWORD_EXTRA_PARENTS": keyword_extra_failure_probe_error_codes,
            "OFFER_EXTRA_KEYWORDS": offer_extra_failure_probe_error_codes,
            "NO_MATCH_POLICIES": no_match_policy_failure_probe_error_codes,
            "MATCH_BRIDGES": match_bridge_failure_probe_error_codes,
            "INGREDIENT_ROUTING_PARENT_TERMS": routing_failure_probe_error_codes,
            "RECIPE_ROUTING_EXTRA_ALIASES": recipe_routing_failure_probe_error_codes,
        },
        "runtime_import_boundary": "failed" if boundary_issues else "passed",
        "runtime_sanity": "skipped" if args.skip_runtime_sanity else "passed",
        "issue_counts": dict(sorted(issue_counts.items())),
        "passed": not any(issue.severity == "error" for issue in issues),
    }
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "findings": [issue.to_dict() for issue in issues],
        "source_counts": dict(sorted(source_counts.items())),
        "generated_exports": {
            "PARENT_MATCH_ONLY": generated_parent_static,
            "KEYWORD_SYNONYMS": generated_keyword_synonym_static,
            "INGREDIENT_PARENTS": generated_ingredient_parent_static,
            "KEYWORD_EXTRA_PARENTS": generated_keyword_extra_static,
            "OFFER_EXTRA_KEYWORDS": generated_offer_extra_static,
            "NO_MATCH_POLICIES": generated_no_match_policy_static,
            "MATCH_BRIDGES": generated_match_bridge_static,
            "INGREDIENT_ROUTING_PARENT_TERMS": generated_routing_static,
            "RECIPE_ROUTING_EXTRA_ALIASES": generated_recipe_routing_static,
        },
        "verified_terms_baseline_exports": {
            "PARENT_MATCH_ONLY": parent_verified_terms_baseline,
            "KEYWORD_SYNONYMS": keyword_synonym_verified_terms_baseline,
            "INGREDIENT_PARENTS": ingredient_parent_verified_terms_baseline,
            "KEYWORD_EXTRA_PARENTS": keyword_extra_verified_terms_baseline,
            "OFFER_EXTRA_KEYWORDS": offer_extra_verified_terms_baseline,
            "NO_MATCH_POLICIES": no_match_policy_verified_terms_baseline,
            "MATCH_BRIDGES": match_bridge_verified_terms_baseline,
            "INGREDIENT_ROUTING_PARENT_TERMS": routing_verified_terms_baseline,
            "RECIPE_ROUTING_EXTRA_ALIASES": recipe_routing_verified_terms_baseline,
        },
        "public_runtime_exports": {
            "PARENT_MATCH_ONLY": public_parent_runtime,
            "KEYWORD_SYNONYMS": public_keyword_synonym_runtime,
            "INGREDIENT_PARENTS": public_ingredient_parent_runtime,
            "KEYWORD_EXTRA_PARENTS": public_keyword_extra_runtime,
            "OFFER_EXTRA_KEYWORDS": public_offer_extra_runtime,
            "NO_MATCH_POLICIES": public_no_match_policy_runtime,
            "MATCH_BRIDGES": public_match_bridge_runtime,
            "INGREDIENT_ROUTING_PARENT_TERMS": public_routing_runtime,
            "RECIPE_ROUTING_EXTRA_ALIASES": generated_recipe_routing_static,
        },
    }
    return payload, issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", default="sv")
    parser.add_argument("--market", default="SE")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--baseline-json", type=Path, default=DEFAULT_VERIFIED_TERMS_BASELINE_JSON)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--skip-runtime-sanity", action="store_true")
    args = parser.parse_args()

    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")
    if args.report_dir is None:
        args.report_dir = DEFAULT_REPORT_ROOT / args.language

    payload, issues = run_checks(args)
    json_report_path = args.report_dir / "term_registry_export_report.json"
    md_report_path = args.report_dir / "term_registry_export_report.md"
    payload["summary"]["reports"] = [
        str(json_report_path.relative_to(REPO_DIR)),
        str(md_report_path.relative_to(REPO_DIR)),
    ]
    json_path, md_path = write_json_and_markdown_report(
        report_dir=args.report_dir,
        stem="term_registry_export_report",
        payload=payload,
        title="Term Registry Export Report",
    )
    assert json_path == json_report_path and md_path == md_report_path

    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if any(issue.severity == "error" for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
