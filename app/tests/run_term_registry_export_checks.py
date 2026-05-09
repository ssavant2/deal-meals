#!/usr/bin/env python3
"""R1/R2 export checks for the term registry.

The script proves that narrow registry-generated exports match the frozen B2
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

from languages.term_registry.models import CheckIssue, RegistryVariant  # noqa: E402
from languages.term_registry.reports import write_json_and_markdown_report  # noqa: E402
from languages.sv.ingredient_matching.ingredient_routing import _ROUTING_PARENT_TERMS as PUBLIC_INGREDIENT_ROUTING_PARENT_TERMS  # noqa: E402
from languages.sv.ingredient_matching.parent_maps import PARENT_MATCH_ONLY as PUBLIC_PARENT_MATCH_ONLY  # noqa: E402
from languages.sv.ingredient_matching.term_registry.exports import (  # noqa: E402
    INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY,
    INGREDIENT_ROUTING_PARENT_TERMS as GENERATED_INGREDIENT_ROUTING_PARENT_TERMS,
    PARENT_MATCH_ONLY as GENERATED_PARENT_MATCH_ONLY,
    PARENT_MATCH_ONLY_SOURCE_FAMILY,
    RECIPE_ROUTING_EXTRA_ALIASES as GENERATED_RECIPE_ROUTING_EXTRA_ALIASES,
    RECIPE_ROUTING_HELPER_SOURCE_FAMILY,
    build_ingredient_routing_parent_export,
    build_parent_match_only_export,
    build_recipe_routing_extra_alias_export,
)
from languages.sv.ingredient_matching.term_registry.legacy_inventory import (  # noqa: E402
    DEFAULT_BATCH_SIZE,
    build_legacy_registry_variants,
)


DEFAULT_REPORT_ROOT = APP_DIR / "tests" / "reports" / "term_registry"
DEFAULT_B_TRACK_BASELINE_JSON = APP_DIR / "tests" / "reports" / "term_pipeline_b_track" / "term_pipeline_audit.json"
INGREDIENT_ROUTING_RUNTIME_FILE = APP_DIR / "languages" / "sv" / "ingredient_matching" / "ingredient_routing.py"
PARENT_MAPS_RUNTIME_FILE = APP_DIR / "languages" / "sv" / "ingredient_matching" / "parent_maps.py"
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


def _normalize_str_mapping(mapping: dict[str, Any]) -> dict[str, str]:
    return dict(sorted((str(key), str(value)) for key, value in mapping.items()))


def _mapping_diff(generated: dict[str, str], reference: dict[str, str]) -> dict[str, Any]:
    generated_keys = set(generated)
    reference_keys = set(reference)
    shared_keys = generated_keys & reference_keys
    changed = {
        key: {"generated": generated[key], "reference": reference[key]}
        for key in sorted(shared_keys)
        if generated[key] != reference[key]
    }
    return {
        "missing_count": len(reference_keys - generated_keys),
        "extra_count": len(generated_keys - reference_keys),
        "changed_count": len(changed),
        "missing_sample": sorted(reference_keys - generated_keys)[:20],
        "extra_sample": sorted(generated_keys - reference_keys)[:20],
        "changed_sample": dict(list(changed.items())[:20]),
    }


def _load_b2_mapping_baseline(
    path: Path,
    *,
    source_family: str,
) -> tuple[dict[str, str], list[CheckIssue]]:
    if not path.exists():
        return {}, [_issue(
            "error",
            "missing_b2_baseline_json",
            "B2 baseline JSON is required for export drift checks",
            item_id=str(path),
        )]
    payload = json.loads(path.read_text(encoding="utf-8"))
    variants = payload.get("variants") or []
    if not isinstance(variants, list):
        return {}, [_issue(
            "error",
            "invalid_b2_baseline_json",
            "B2 baseline variants payload must be a list",
            item_id=str(path),
        )]

    baseline: dict[str, str] = {}
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
                f"B2 {source_family} rows must include variant_text and canonical",
                item_id=str(variant.get("variant_id") or ""),
            ))
            continue
        previous = baseline.get(source)
        if previous is not None and previous != target:
            issues.append(_issue(
                "error",
                "conflicting_mapping_baseline_row",
                f"B2 {source_family} baseline maps one source to multiple targets",
                item_id=source,
                details={"previous": previous, "target": target},
            ))
        baseline[source] = target
    if not baseline:
        issues.append(_issue(
            "error",
            "missing_mapping_baseline_rows",
            f"B2 baseline contains no {source_family} rows",
            item_id=str(path),
        ))
    return dict(sorted(baseline.items())), issues


def _compare_mapping_export(
    *,
    generated: dict[str, str],
    baseline: dict[str, str],
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
    if len(generated) != len(selected_variants):
        issues.append(_issue(
            "error",
            "export_variant_count_mismatch",
            "generated export count does not match selected registry variant count",
            item_id=item_id,
            details={"generated": len(generated), "selected_variants": len(selected_variants)},
        ))
    if generated != baseline:
        issues.append(_issue(
            "error",
            "export_b2_baseline_mismatch",
            f"generated {item_id} export differs from the frozen B2 baseline",
            item_id=item_id,
            details=_mapping_diff(generated, baseline),
        ))
    return issues


def _run_required_layer_failure_probe(
    *,
    variants: list[RegistryVariant],
    baseline: dict[str, str],
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
    parent_imports = _imported_modules(PARENT_MAPS_RUNTIME_FILE)
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
    if ".term_registry.exports" not in parent_imports:
        issues.append(_issue(
            "error",
            "runtime_export_import_missing",
            "parent_maps.py must import the selected mapping from term_registry.exports",
            item_id=str(PARENT_MAPS_RUNTIME_FILE.relative_to(REPO_DIR)),
            details={"imports": parent_imports},
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
        "run_term_pipeline_b_track_audit",
        "ingredient_matching.ingredient_routing",
        ".ingredient_routing",
        "ingredient_matching.parent_maps",
        ".parent_maps",
        "ingredient_matching.term_indexes",
        ".term_indexes",
    )
    for path, imports in (
        (INGREDIENT_ROUTING_RUNTIME_FILE, ingredient_routing_imports),
        (PARENT_MAPS_RUNTIME_FILE, parent_imports),
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
    parent_b2_baseline, parent_baseline_issues = _load_b2_mapping_baseline(
        args.baseline_json,
        source_family=PARENT_MATCH_ONLY_SOURCE_FAMILY,
    )
    routing_b2_baseline, routing_baseline_issues = _load_b2_mapping_baseline(
        args.baseline_json,
        source_family=INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY,
    )
    recipe_routing_b2_baseline, recipe_routing_baseline_issues = _load_b2_mapping_baseline(
        args.baseline_json,
        source_family=RECIPE_ROUTING_HELPER_SOURCE_FAMILY,
    )
    issues.extend(parent_baseline_issues)
    issues.extend(routing_baseline_issues)
    issues.extend(recipe_routing_baseline_issues)
    variants = _load_language_variants(args.language, args.batch_size)
    selected_parent_variants = [
        variant
        for variant in variants
        if variant.source_family == PARENT_MATCH_ONLY_SOURCE_FAMILY
    ]
    selected_routing_variants = [
        variant
        for variant in variants
        if variant.source_family == INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY
    ]
    selected_recipe_routing_variants = [
        variant
        for variant in variants
        if variant.source_family == RECIPE_ROUTING_HELPER_SOURCE_FAMILY
    ]
    generated_parent_from_variants = build_parent_match_only_export(variants)
    generated_parent_static = _normalize_str_mapping(GENERATED_PARENT_MATCH_ONLY)
    public_parent_runtime = _normalize_str_mapping(PUBLIC_PARENT_MATCH_ONLY)
    generated_routing_from_variants = build_ingredient_routing_parent_export(variants)
    generated_routing_static = _normalize_str_mapping(GENERATED_INGREDIENT_ROUTING_PARENT_TERMS)
    public_routing_runtime = _normalize_str_mapping(PUBLIC_INGREDIENT_ROUTING_PARENT_TERMS)
    generated_recipe_routing_from_variants = build_recipe_routing_extra_alias_export(variants)
    generated_recipe_routing_static = _normalize_str_mapping(GENERATED_RECIPE_ROUTING_EXTRA_ALIASES)

    issues.extend(_compare_mapping_export(
        generated=generated_parent_static,
        baseline=parent_b2_baseline,
        selected_variants=selected_parent_variants,
        item_id="PARENT_MATCH_ONLY",
        source_family=PARENT_MATCH_ONLY_SOURCE_FAMILY,
    ))
    if generated_parent_from_variants != generated_parent_static:
        issues.append(_issue(
            "error",
            "generated_export_builder_mismatch",
            "builder output from current registry view differs from the static runtime export",
            item_id="PARENT_MATCH_ONLY",
            details=_mapping_diff(generated_parent_from_variants, generated_parent_static),
        ))
    if public_parent_runtime != generated_parent_static:
        issues.append(_issue(
            "error",
            "public_runtime_export_mismatch",
            "parent_maps.PARENT_MATCH_ONLY differs from the generated registry export",
            item_id="PARENT_MATCH_ONLY",
            details=_mapping_diff(public_parent_runtime, generated_parent_static),
        ))

    issues.extend(_compare_mapping_export(
        generated=generated_routing_static,
        baseline=routing_b2_baseline,
        selected_variants=selected_routing_variants,
        item_id="INGREDIENT_ROUTING_PARENT_TERMS",
        source_family=INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY,
    ))
    if generated_routing_from_variants != generated_routing_static:
        issues.append(_issue(
            "error",
            "generated_export_builder_mismatch",
            "builder output from current registry view differs from the static runtime export",
            item_id="INGREDIENT_ROUTING_PARENT_TERMS",
            details=_mapping_diff(generated_routing_from_variants, generated_routing_static),
        ))
    if public_routing_runtime != generated_routing_static:
        issues.append(_issue(
            "error",
            "public_runtime_export_mismatch",
            "ingredient_routing._ROUTING_PARENT_TERMS differs from the generated registry export",
            item_id="INGREDIENT_ROUTING_PARENT_TERMS",
            details=_mapping_diff(public_routing_runtime, generated_routing_static),
        ))

    issues.extend(_compare_mapping_export(
        generated=generated_recipe_routing_static,
        baseline=recipe_routing_b2_baseline,
        selected_variants=selected_recipe_routing_variants,
        item_id="RECIPE_ROUTING_EXTRA_ALIASES",
        source_family=RECIPE_ROUTING_HELPER_SOURCE_FAMILY,
    ))
    if generated_recipe_routing_from_variants != generated_recipe_routing_static:
        issues.append(_issue(
            "error",
            "generated_export_builder_mismatch",
            "builder output from current registry view differs from the static runtime export",
            item_id="RECIPE_ROUTING_EXTRA_ALIASES",
            details=_mapping_diff(generated_recipe_routing_from_variants, generated_recipe_routing_static),
        ))

    parent_failure_probe_passed, parent_failure_probe_error_codes = _run_required_layer_failure_probe(
        variants=variants,
        baseline=parent_b2_baseline,
        source_family=PARENT_MATCH_ONLY_SOURCE_FAMILY,
        item_id="PARENT_MATCH_ONLY",
        build_export=build_parent_match_only_export,
    )
    routing_failure_probe_passed, routing_failure_probe_error_codes = _run_required_layer_failure_probe(
        variants=variants,
        baseline=routing_b2_baseline,
        source_family=INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY,
        item_id="INGREDIENT_ROUTING_PARENT_TERMS",
        build_export=build_ingredient_routing_parent_export,
    )
    recipe_routing_failure_probe_passed, recipe_routing_failure_probe_error_codes = (
        _run_required_layer_failure_probe(
            variants=variants,
            baseline=recipe_routing_b2_baseline,
            source_family=RECIPE_ROUTING_HELPER_SOURCE_FAMILY,
            item_id="RECIPE_ROUTING_EXTRA_ALIASES",
            build_export=build_recipe_routing_extra_alias_export,
        )
    )
    for item_id, passed in (
        ("PARENT_MATCH_ONLY", parent_failure_probe_passed),
        ("INGREDIENT_ROUTING_PARENT_TERMS", routing_failure_probe_passed),
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
            "INGREDIENT_ROUTING_PARENT_TERMS",
            "RECIPE_ROUTING_EXTRA_ALIASES",
        ],
        "selected_source_families": [
            PARENT_MATCH_ONLY_SOURCE_FAMILY,
            INGREDIENT_ROUTING_PARENT_SOURCE_FAMILY,
            RECIPE_ROUTING_HELPER_SOURCE_FAMILY,
        ],
        "b2_baseline_file": str(args.baseline_json.relative_to(REPO_DIR)),
        "registry_variant_count": len(variants),
        "selected_variant_counts": {
            "PARENT_MATCH_ONLY": len(selected_parent_variants),
            "INGREDIENT_ROUTING_PARENT_TERMS": len(selected_routing_variants),
            "RECIPE_ROUTING_EXTRA_ALIASES": len(selected_recipe_routing_variants),
        },
        "generated_export_counts": {
            "PARENT_MATCH_ONLY": len(generated_parent_static),
            "INGREDIENT_ROUTING_PARENT_TERMS": len(generated_routing_static),
            "RECIPE_ROUTING_EXTRA_ALIASES": len(generated_recipe_routing_static),
        },
        "b2_baseline_export_counts": {
            "PARENT_MATCH_ONLY": len(parent_b2_baseline),
            "INGREDIENT_ROUTING_PARENT_TERMS": len(routing_b2_baseline),
            "RECIPE_ROUTING_EXTRA_ALIASES": len(recipe_routing_b2_baseline),
        },
        "public_runtime_export_counts": {
            "PARENT_MATCH_ONLY": len(public_parent_runtime),
            "INGREDIENT_ROUTING_PARENT_TERMS": len(public_routing_runtime),
            "RECIPE_ROUTING_EXTRA_ALIASES": len(generated_recipe_routing_static),
        },
        "failure_probe_passed": {
            "PARENT_MATCH_ONLY": parent_failure_probe_passed,
            "INGREDIENT_ROUTING_PARENT_TERMS": routing_failure_probe_passed,
            "RECIPE_ROUTING_EXTRA_ALIASES": recipe_routing_failure_probe_passed,
        },
        "failure_probe_error_codes": {
            "PARENT_MATCH_ONLY": parent_failure_probe_error_codes,
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
            "INGREDIENT_ROUTING_PARENT_TERMS": generated_routing_static,
            "RECIPE_ROUTING_EXTRA_ALIASES": generated_recipe_routing_static,
        },
        "b2_baseline_exports": {
            "PARENT_MATCH_ONLY": parent_b2_baseline,
            "INGREDIENT_ROUTING_PARENT_TERMS": routing_b2_baseline,
            "RECIPE_ROUTING_EXTRA_ALIASES": recipe_routing_b2_baseline,
        },
        "public_runtime_exports": {
            "PARENT_MATCH_ONLY": public_parent_runtime,
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
    parser.add_argument("--baseline-json", type=Path, default=DEFAULT_B_TRACK_BASELINE_JSON)
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
