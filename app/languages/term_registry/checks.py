"""Shared checks for term registry reports."""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from .models import CheckIssue, RegistryEntry, RegistryVariant, validate_registry_entry


def validate_entries(entries: list[RegistryEntry]) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if entry.entry_id in seen_ids:
            issues.append(CheckIssue(
                severity="error",
                code="duplicate_entry_id",
                message="entry_id is duplicated",
                item_id=entry.entry_id,
            ))
        seen_ids.add(entry.entry_id)
        issues.extend(validate_registry_entry(entry))
    return issues


def compare_variants_to_baseline(
    variants: list[RegistryVariant],
    baseline_variant_ids: set[str],
) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    current_ids = {variant.variant_id for variant in variants if variant.variant_id}
    missing = sorted(baseline_variant_ids - current_ids)
    extra = sorted(current_ids - baseline_variant_ids)

    if missing:
        issues.append(CheckIssue(
            severity="warning",
            code="baseline_variants_missing",
            message=(
                "current registry view is missing verified-term baseline variant ids; "
                "coverage-key checks remain authoritative for lost terms"
            ),
            details={"count": len(missing), "sample": missing[:20]},
        ))
    if extra:
        issues.append(CheckIssue(
            severity="warning",
            code="baseline_variants_extra",
            message="current registry view has variants not present in the verified-term baseline",
            details={"count": len(extra), "sample": extra[:20]},
        ))
    return issues


def summarize_variants(variants: list[RegistryVariant]) -> dict[str, object]:
    return {
        "variant_count": len(variants),
        "source_counts": dict(sorted(Counter(variant.source_family for variant in variants).items())),
        "layer_role_counts": dict(sorted(Counter(variant.layer_role for variant in variants).items())),
        "layer_policy_counts": dict(sorted(
            Counter(policy for variant in variants for policy in variant.layer_policy).items()
        )),
        "status_counts": dict(sorted(Counter(variant.status for variant in variants).items())),
    }


def check_shared_core_import_boundaries(shared_dir: Path) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    for path in sorted(shared_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            issues.append(CheckIssue(
                severity="error",
                code="shared_core_syntax_error",
                message="shared term registry core file could not be parsed",
                item_id=str(path),
                details={"line": exc.lineno or 0, "offset": exc.offset or 0, "text": exc.text or ""},
            ))
            continue

        forbidden_imports = []
        for node in ast.walk(tree):
            imported_modules: list[str] = []
            if isinstance(node, ast.Import):
                imported_modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules = [node.module]

            for module in imported_modules:
                parts = module.split(".")
                if (
                    (
                        module.startswith("languages.")
                        and not module.startswith("languages.term_registry")
                    )
                    or "ingredient_matching" in parts
                ):
                    forbidden_imports.append(module)

        if forbidden_imports:
            issues.append(CheckIssue(
                severity="error",
                code="shared_core_language_import",
                message="shared term registry core must not import language-specific matcher modules",
                item_id=str(path),
                details={"imports": sorted(set(forbidden_imports))},
            ))
    return issues
