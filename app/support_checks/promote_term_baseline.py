"""Promote new term-registry variants into the frozen verified-term baseline.

Run this after adding new TOML entries that produce new
hardcoded-keyword-output or mapping variants not yet in a language's
baselines/verified_matcher_terms.json.

Swedish defaults:
    language: sv
    market: SE
    baseline:
        app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json
    audit module:
        support_checks.run_verified_term_audit
    registry module:
        languages.sv.ingredient_matching.term_registry.registry

Usage:
    docker compose exec -T -w /app web python support_checks/promote_term_baseline.py
    docker compose exec -T -w /app web python support_checks/promote_term_baseline.py --dry-run
    docker compose exec -T -w /app web python support_checks/promote_term_baseline.py --allow-removals
    docker compose exec -T -w /app web python support_checks/promote_term_baseline.py --migrate-hashes
    docker compose exec -T -w /app web python support_checks/promote_term_baseline.py --language sv --market SE

The script does not require a dev-only DB table. For the current Swedish
default this means it does not need tmp_verified_term_audit_variants. It
regenerates the full variant list from the current code and TOML state, finds
the diff vs the frozen baseline, and applies the minimal update needed.

For another language, provide an audit module with build_variants(batch_size)
and _variant_row(variant), plus a registry module with load_registry_entries().

In production stacks where /app is mounted read-only, run this from a writable
checkout, CI job, or maintenance container with the application dependencies
installed, or pass --output-dir to stage changed files under a writable path
such as /tmp or /app/data. The promotion itself is file-based and does not
connect to the DB.

After the script finishes, run the full sanity check to verify:
    docker compose exec -T -w /app web python support_checks/run_sanity_checks.py
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = APP_DIR.parent
DEFAULT_LANGUAGE = "sv"
DEFAULT_MARKET = "SE"
DEFAULT_BATCH_SIZE = 60
DEFAULT_AUDIT_MODULES = {
    ("sv", "SE"): "support_checks.run_verified_term_audit",
}
DEFAULT_REGISTRY_MODULE_TEMPLATE = "languages.{language}.ingredient_matching.term_registry.registry"
DEFAULT_SWEDISH_BASELINE_PATH = (
    APP_DIR
    / "languages"
    / "sv"
    / "ingredient_matching"
    / "term_registry"
    / "baselines"
    / "verified_matcher_terms.json"
)
DEFAULT_SWEDISH_VARIANT_ID_MIGRATION_PATH = (
    DEFAULT_SWEDISH_BASELINE_PATH.parent / "variant_id_migration_v1_to_v2.json"
)
DEFAULT_SWEDISH_ADD_TERM_CHECKS_PATH = APP_DIR / "support_checks" / "run_term_registry_add_term_checks.py"
DEFAULT_SWEDISH_CONTRACT_CHECKS_PATH = APP_DIR / "support_checks" / "run_term_registry_contract_checks.py"
DEFAULT_SWEDISH_SANITY_CHECKS_PATH = APP_DIR / "support_checks" / "run_sanity_checks.py"
VARIANT_ID_MIGRATION_SCHEMA_VERSION = 1
BASELINE_VARIANT_OMIT_KEYS = {"batch_id", "batch_index"}
BASELINE_SUMMARY_OMIT_KEYS = {
    "batch_count",
    "batch_counts",
    "first_batch_id",
    "last_batch_id",
    "normal_batch_size",
    "working_table",
}
BASELINE_VERIFICATION_OMIT_KEYS = {
    "applied_batch_count",
    "batch_report_count",
    "first_batch_id",
    "last_batch_id",
}


@dataclass(frozen=True)
class PromotionConfig:
    language: str
    market: str
    baseline_path: Path
    audit_module: str
    registry_module: str
    batch_size: int = DEFAULT_BATCH_SIZE
    add_term_checks_path: Path | None = None
    contract_checks_path: Path | None = None
    sanity_checks_path: Path | None = None
    variant_id_migration_path: Path | None = None


def _language_key(language: str, market: str) -> tuple[str, str]:
    return (language.strip().lower(), market.strip().upper())


def _default_baseline_path(language: str) -> Path:
    if language == DEFAULT_LANGUAGE:
        return DEFAULT_SWEDISH_BASELINE_PATH
    return (
        APP_DIR
        / "languages"
        / language
        / "ingredient_matching"
        / "term_registry"
        / "baselines"
        / "verified_matcher_terms.json"
    )


def _resolve_app_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == "app":
        return REPO_DIR / path
    return APP_DIR / path


def _default_check_paths(language: str, market: str) -> tuple[Path | None, Path | None, Path | None]:
    if _language_key(language, market) == (DEFAULT_LANGUAGE, DEFAULT_MARKET):
        return (
            DEFAULT_SWEDISH_ADD_TERM_CHECKS_PATH,
            DEFAULT_SWEDISH_CONTRACT_CHECKS_PATH,
            DEFAULT_SWEDISH_SANITY_CHECKS_PATH,
        )
    return (None, None, None)


def _build_config(args: argparse.Namespace) -> PromotionConfig:
    language, market = _language_key(args.language, args.market)
    add_term_checks_path, contract_checks_path, sanity_checks_path = _default_check_paths(language, market)
    if args.skip_check_constant_updates:
        add_term_checks_path = None
        contract_checks_path = None
        sanity_checks_path = None
    return PromotionConfig(
        language=language,
        market=market,
        baseline_path=_resolve_app_path(args.baseline_json) or _default_baseline_path(language),
        audit_module=(
            args.audit_module
            or DEFAULT_AUDIT_MODULES.get((language, market))
            or f"support_checks.run_{language}_verified_term_audit"
        ),
        registry_module=(
            args.registry_module
            or DEFAULT_REGISTRY_MODULE_TEMPLATE.format(language=language)
        ),
        batch_size=args.batch_size,
        add_term_checks_path=_resolve_app_path(args.add_term_checks_path) or add_term_checks_path,
        contract_checks_path=_resolve_app_path(args.contract_checks_path) or contract_checks_path,
        sanity_checks_path=_resolve_app_path(args.sanity_checks_path) or sanity_checks_path,
        variant_id_migration_path=(
            DEFAULT_SWEDISH_VARIANT_ID_MIGRATION_PATH
            if (language, market) == (DEFAULT_LANGUAGE, DEFAULT_MARKET)
            else _default_baseline_path(language).parent / "variant_id_migration_v1_to_v2.json"
        ),
    )


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _repo_relative_path(path: Path) -> Path:
    resolved = path.resolve()
    try:
        return resolved.relative_to(APP_DIR)
    except ValueError:
        return resolved.relative_to(REPO_DIR)


def _target_path(path: Path, output_dir: Path | None) -> Path:
    if output_dir is None:
        return path
    return output_dir / _repo_relative_path(path)


def _write_text(path: Path, text: str, *, output_dir: Path | None = None) -> Path:
    target = _target_path(path, output_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def _write_json(path: Path, data: dict, *, output_dir: Path | None = None) -> Path:
    return _write_text(
        path,
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        output_dir=output_dir,
    )


def _generate_fresh_variants(config: PromotionConfig) -> list[dict]:
    """Build the current full verified-term variant list in memory."""
    os.environ.setdefault("TERM_REGISTRY_DISABLE_LOCAL_ENTRIES", "1")
    sys.path.insert(0, str(APP_DIR))
    audit_module = importlib.import_module(config.audit_module)
    raw = audit_module.build_variants(batch_size=config.batch_size)
    return [audit_module._variant_row(v) for v in raw]


def _baseline_variant(v: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in v.items()
        if key not in BASELINE_VARIANT_OMIT_KEYS
    }


def _normalize_baseline_payload(baseline: dict[str, Any]) -> bool:
    old_payload = json.dumps(baseline, ensure_ascii=False, sort_keys=True)
    baseline["variants"] = [
        _baseline_variant(v)
        for v in baseline.get("variants", [])
        if isinstance(v, dict)
    ]

    summary = {
        key: value
        for key, value in dict(baseline.get("summary", {})).items()
        if key not in BASELINE_SUMMARY_OMIT_KEYS
    }
    baseline["summary"] = summary

    verification = {
        key: value
        for key, value in dict(baseline.get("verification", {})).items()
        if key not in BASELINE_VERIFICATION_OMIT_KEYS
    }
    baseline["verification"] = verification

    new_payload = json.dumps(baseline, ensure_ascii=False, sort_keys=True)
    return old_payload != new_payload


def _get_unique_coverage_key_count(config: PromotionConfig) -> int:
    """Count unique registry TOML coverage keys for the frozen term gate."""
    if _language_key(config.language, config.market) == (DEFAULT_LANGUAGE, DEFAULT_MARKET):
        from languages.sv.ingredient_matching.term_registry.add_term import build_add_term_export_plan

        registry_module = importlib.import_module(config.registry_module)
        entries = registry_module.load_registry_entries(include_local=False)
        payload, issues = build_add_term_export_plan(
            entries=entries,
            language=config.language,
            market=config.market,
        )
        errors = [issue for issue in issues if issue.severity == "error"]
        if errors:
            details = "; ".join(f"{issue.code}:{issue.item_id}" for issue in errors[:5])
            raise RuntimeError(f"registry coverage has export-plan errors; refusing to promote: {details}")
        return int(payload["summary"]["unique_coverage_key_count"])
    return len(_registry_coverage_keys(config))


def _update_py_constant(
    path: Path,
    name: str,
    new_value: int,
    *,
    output_dir: Path | None = None,
) -> Path | None:
    """Replace `NAME = <old_int>` with `NAME = <new_int>` in a Python file."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    import re
    pattern = rf"^({re.escape(name)}\s*=\s*)(\d+)(\s*(?:#.*)?)$"
    new_text, count = re.subn(pattern, rf"\g<1>{new_value}\g<3>", text, flags=re.MULTILINE)
    if count == 0:
        return None
    return _write_text(path, new_text, output_dir=output_dir)


def _write_output_manifest(
    *,
    output_dir: Path | None,
    changed_files: list[tuple[Path, Path]],
    current_count: int,
    new_count: int,
    new_unique_key_count: int | None = None,
) -> None:
    if output_dir is None:
        return
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "staged_output",
        "current_variant_count": current_count,
        "new_variant_count": new_count,
        "new_unique_coverage_key_count": new_unique_key_count,
        "changed_files": [
            {
                "source_path": str(_repo_relative_path(source)),
                "staged_path": str(target),
            }
            for source, target in changed_files
        ],
    }
    manifest_path = output_dir / "promotion_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _variant_id_migration_record(
    *,
    old_id: str,
    new_id: str,
    old_variant: dict[str, Any],
    fresh_variant: dict[str, Any],
    config: PromotionConfig,
) -> dict[str, Any]:
    language, market, source_family, canonical, variant, layer_role = _coverage_key(fresh_variant, config)
    return {
        "old_variant_id": old_id,
        "new_variant_id": new_id,
        "language": language,
        "market": market,
        "source_family": source_family,
        "canonical": canonical,
        "variant": variant,
        "layer_role": layer_role,
        "source_file": str(fresh_variant.get("source_file") or old_variant.get("source_file") or ""),
        "source_id": str(fresh_variant.get("source_id") or old_variant.get("source_id") or ""),
        "source_ref": str(fresh_variant.get("source_ref") or old_variant.get("source_ref") or ""),
    }


def _write_variant_id_migration_map(
    *,
    path: Path,
    records: list[dict[str, Any]],
    output_dir: Path | None,
) -> Path:
    payload = {
        "schema_version": VARIANT_ID_MIGRATION_SCHEMA_VERSION,
        "from_hash_version": "v1_source_ref",
        "to_hash_version": "v2_stable_without_source_ref",
        "description": (
            "One-shot verified-term baseline migration. v2 variant_id hashes "
            "exclude source_ref provenance text so source_ref edits do not "
            "force future baseline hash migrations."
        ),
        "variant_count": len(records),
        "migrations": sorted(records, key=lambda item: item["old_variant_id"]),
    }
    return _write_json(path, payload, output_dir=output_dir)


def _content_key(v: dict, config: PromotionConfig) -> tuple:
    """Stable content key for matching variants across source-order hash changes."""
    return (
        _coverage_key(v, config),
        v.get("source_id", ""),
        v.get("source_file", ""),
        v.get("expected", None),
    )


def _coverage_key(v: dict, config: PromotionConfig) -> tuple[str, str, str, str, str, str]:
    return (
        str(v.get("language") or config.language),
        str(v.get("market") or config.market),
        str(v.get("source_family") or v.get("source_type") or ""),
        str(v.get("canonical") or ""),
        str(v.get("variant") or v.get("variant_text") or ""),
        str(v.get("layer_role") or v.get("variant_role") or ""),
    )


def _registry_coverage_keys(config: PromotionConfig) -> set[tuple[str, str, str, str, str, str]]:
    """Load active exact TOML coverage keys without DB/test-check dependencies."""
    os.environ.setdefault("TERM_REGISTRY_DISABLE_LOCAL_ENTRIES", "1")
    registry_module = importlib.import_module(config.registry_module)

    coverage_keys: set[tuple[str, str, str, str, str, str]] = set()
    errors: list[str] = []
    for entry in registry_module.load_registry_entries():
        if entry.status != "active":
            continue
        raw_coverage = (
            entry.language_payload.get("coverage")
            or entry.language_payload.get("legacy_coverage")
            or []
        )
        if not raw_coverage:
            continue
        if not isinstance(raw_coverage, list):
            errors.append(f"{entry.entry_id}:coverage_not_list")
            continue
        for index, raw_item in enumerate(raw_coverage):
            if not isinstance(raw_item, dict):
                errors.append(f"{entry.entry_id}:coverage_row_{index}_not_table")
                continue
            source_family = raw_item.get("source_family") or raw_item.get("source_type") or ""
            key = (
                str(raw_item.get("language") or entry.language),
                str(raw_item.get("market") or entry.market),
                str(source_family),
                str(raw_item.get("canonical") or entry.canonical),
                str(raw_item.get("variant") or raw_item.get("variant_text") or ""),
                str(raw_item.get("layer_role") or raw_item.get("variant_role") or ""),
            )
            if not all(key):
                errors.append(f"{entry.entry_id}:coverage_row_{index}_incomplete")
                continue
            if any(value.strip() in {"", "*", "all", "any"} for value in key[2:]):
                errors.append(f"{entry.entry_id}:coverage_row_{index}_too_broad")
                continue
            coverage_keys.add(key)
    if errors:
        details = "; ".join(errors[:5])
        raise RuntimeError(f"registry coverage has errors; refusing to promote baseline: {details}")
    return coverage_keys


def _promoted_classification(v: dict[str, Any]) -> str:
    if v.get("source_type") == "matcher_regression_case":
        return "synthetic_verified"
    if v.get("needs_product_text") and not v.get("product_text"):
        return "no_product_text"
    return "static_verified"


def _refresh_summary_from_variants(baseline: dict[str, Any]) -> bool:
    variants = [v for v in baseline.get("variants", []) if isinstance(v, dict)]
    old_summary = json.dumps(baseline.get("summary", {}), ensure_ascii=False, sort_keys=True)

    source_counts = Counter(str(v.get("source_type") or v.get("source_family") or "unknown") for v in variants)
    role_counts = Counter(str(v.get("variant_role") or v.get("layer_role") or "unknown") for v in variants)
    product_text_count = sum(1 for v in variants if v.get("product_text"))

    summary = {
        key: value
        for key, value in dict(baseline.get("summary", {})).items()
        if key not in BASELINE_SUMMARY_OMIT_KEYS
    }
    summary["variant_count"] = len(variants)
    summary["variants_with_product_text"] = product_text_count
    summary["variants_missing_product_text"] = len(variants) - product_text_count
    summary["source_counts"] = dict(sorted(source_counts.items()))
    summary["role_counts"] = dict(sorted(role_counts.items()))
    baseline["summary"] = summary

    new_summary = json.dumps(summary, ensure_ascii=False, sort_keys=True)
    return old_summary != new_summary


def _decrement_classification_count(classification_counts: dict[str, int], classification: str) -> None:
    if classification_counts.get(classification, 0) > 0:
        classification_counts[classification] -= 1
        return
    if classification_counts.get("static_verified", 0) > 0:
        classification_counts["static_verified"] -= 1
        return
    for existing_classification, count in classification_counts.items():
        if count > 0:
            classification_counts[existing_classification] = count - 1
            return


def _apply_verification_updates(
    baseline: dict[str, Any],
    promoted_variants: list[dict],
    removed_variants: list[dict] | None = None,
) -> None:
    variants = [v for v in baseline.get("variants", []) if isinstance(v, dict)]
    verification = {
        key: value
        for key, value in dict(baseline.get("verification", {})).items()
        if key not in BASELINE_VERIFICATION_OMIT_KEYS
    }
    verification["variant_count"] = len(variants)
    verification.setdefault("status_counts", {})["audited"] = len(variants)
    verification["source_counts"] = dict(sorted(
        Counter(str(v.get("source_type") or v.get("source_family") or "unknown") for v in variants).items()
    ))

    classification_counts = {
        str(classification): int(count)
        for classification, count in dict(verification.get("classification_counts", {})).items()
    }
    for v in removed_variants or []:
        _decrement_classification_count(classification_counts, _promoted_classification(v))
    for v in promoted_variants:
        classification = _promoted_classification(v)
        classification_counts[classification] = classification_counts.get(classification, 0) + 1
    classification_counts = {
        classification: count
        for classification, count in classification_counts.items()
        if count
    }
    if sum(classification_counts.values()) != len(variants):
        raise RuntimeError(
            "verification classification total "
            f"{sum(classification_counts.values())} != variant count {len(variants)}"
        )
    verification["classification_counts"] = classification_counts
    baseline["verification"] = verification


def promote(
    *,
    config: PromotionConfig,
    dry_run: bool = False,
    migrate_hashes: bool = False,
    allow_removals: bool = False,
    output_dir: Path | None = None,
) -> int:
    if output_dir is not None:
        output_dir = output_dir.resolve()
        print(f"Staging writes under: {output_dir}")
    if migrate_hashes:
        print("--migrate-hashes is accepted for compatibility; hash-equivalent ID migrations are automatic.")

    print(f"Language/market: {config.language}/{config.market}")
    print("Loading current baseline …")
    baseline = _load_json(config.baseline_path)
    baseline_normalized = _normalize_baseline_payload(baseline)
    current_ids = {v["variant_id"] for v in baseline["variants"] if isinstance(v, dict) and v.get("variant_id")}
    current_count = len(baseline["variants"])
    starting_count = current_count

    print("Generating fresh variant list from code + TOML …")
    fresh_variants = _generate_fresh_variants(config)
    fresh_ids = {v["variant_id"] for v in fresh_variants if v.get("variant_id")}

    all_new_variants = [v for v in fresh_variants if v.get("variant_id") and v["variant_id"] not in current_ids]
    removed_ids = current_ids - fresh_ids

    hash_migrations: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []  # old_id, new_id, old, fresh
    migrated_new_ids: set[str] = set()
    allowed_removed_ids: set[str] = set()
    removed_variants: list[dict] = []
    if removed_ids:
        baseline_by_id = {v["variant_id"]: v for v in baseline["variants"] if v.get("variant_id")}
        # Build a FIFO queue per content_key so duplicates are matched 1:1.
        # Content-equivalent ID changes are safe to migrate automatically; true
        # removals still require explicit --allow-removals approval.
        from collections import defaultdict
        fresh_queues: dict[tuple, list] = defaultdict(list)
        for v in fresh_variants:
            if v.get("variant_id") and v["variant_id"] not in current_ids:
                fresh_queues[_content_key(v, config)].append(v)

        truly_removed = []
        removed_id_order = [
            v["variant_id"]
            for v in baseline["variants"]
            if v.get("variant_id") in removed_ids
        ]
        for vid in removed_id_order:
            old_v = baseline_by_id[vid]
            queue = fresh_queues.get(_content_key(old_v, config))
            if queue:
                fresh_v = queue.pop(0)
                if fresh_v["variant_id"] != vid:
                    hash_migrations.append((vid, fresh_v["variant_id"], old_v, fresh_v))
                    migrated_new_ids.add(fresh_v["variant_id"])
            else:
                truly_removed.append(vid)

        if truly_removed:
            print(f"\n⚠️  WARNING: {len(truly_removed)} variant(s) truly removed (no content match in fresh):")
            for vid in sorted(truly_removed)[:10]:
                v = baseline_by_id[vid]
                print(f"   {vid}: {v.get('variant_text','')!r} ({v.get('source_type','')})")
            if not allow_removals:
                print("This usually means a TOML entry or extraction function was removed.")
                print("Re-run with --allow-removals only after confirming the removals are intentional.")
                print("Aborting.")
                return 1
            allowed_removed_ids.update(truly_removed)
            print("Removal approval enabled: these truly removed variants will be dropped from the baseline.")
        print(
            "\nHash migration: "
            f"{len(hash_migrations)} variant(s) will get new IDs with unchanged coverage/content."
        )

    # Truly new variants = fresh entries not in baseline AND not just hash-migrated old ones
    new_variants = [v for v in all_new_variants if v["variant_id"] not in migrated_new_ids]

    if new_variants:
        registry_coverage_keys = _registry_coverage_keys(config)
        uncovered = [
            v for v in new_variants
            if _coverage_key(v, config) not in registry_coverage_keys
        ]
        if uncovered:
            print(f"\n⚠️  ERROR: {len(uncovered)} new variant(s) lack exact active TOML coverage:")
            for v in uncovered[:10]:
                print(
                    "   "
                    f"{v.get('variant_id','?')}: "
                    f"{v.get('canonical','?')} | "
                    f"{v.get('source_type','?')} | "
                    f"{v.get('variant_role','?')} | "
                    f"{v.get('variant_text','?')!r}"
                )
            print("Add [[coverage]] to a registry TOML entry before promoting.")
            return 1
        print(f"\nNew variants to add: {len(new_variants)}")
        for v in new_variants:
            print(
                f"  row {v.get('row_index','?')}: "
                f"{v.get('canonical','?')} | "
                f"{v.get('source_type','?')} | "
                f"{v.get('variant_id','?')[:24]}"
            )

    # Apply hash migrations: replace old-hash entries with new-hash entries in-place
    hash_migration_records: list[dict[str, Any]] = []
    if hash_migrations:
        migration_map = {old_id: new_id for old_id, new_id, _old_v, _fresh_v in hash_migrations}
        fresh_by_id = {v["variant_id"]: v for v in fresh_variants}
        baseline["variants"] = [
            _baseline_variant(fresh_by_id[migration_map[v["variant_id"]]])
            if v.get("variant_id") in migration_map
            else _baseline_variant(v)
            for v in baseline["variants"]
        ]
        hash_migration_records = [
            _variant_id_migration_record(
                old_id=old_id,
                new_id=new_id,
                old_variant=old_v,
                fresh_variant=fresh_v,
                config=config,
            )
            for old_id, new_id, old_v, fresh_v in hash_migrations
        ]
        current_count = len(baseline["variants"])

    if allowed_removed_ids:
        removed_variants = [
            _baseline_variant(v)
            for v in baseline["variants"]
            if v.get("variant_id") in allowed_removed_ids
        ]
        baseline["variants"] = [
            _baseline_variant(v)
            for v in baseline["variants"]
            if v.get("variant_id") not in allowed_removed_ids
        ]
        current_count = len(baseline["variants"])

    new_count = current_count + len(new_variants)

    if not new_variants and not hash_migrations and not allowed_removed_ids:
        summary_changed = _refresh_summary_from_variants(baseline)
        if not summary_changed and not baseline_normalized:
            print(f"\nNothing to promote — baseline is up to date ({current_count} variants).")
            return 0
        if dry_run:
            print(f"\n[dry-run] Would refresh stale baseline metadata ({current_count} variants).")
            print("[dry-run] No files written.")
            return 0
        _apply_verification_updates(baseline, promoted_variants=[])
        print(f"\nRefreshing baseline metadata ({current_count} variants) …")
        target = _write_json(config.baseline_path, baseline, output_dir=output_dir)
        _write_output_manifest(
            output_dir=output_dir,
            changed_files=[(config.baseline_path, target)],
            current_count=current_count,
            new_count=current_count,
        )
        if output_dir is None:
            print("\n✓ Baseline summary refresh complete.")
        else:
            print(f"\n✓ Baseline summary refresh staged under {output_dir}.")
        return 0

    if dry_run:
        if hash_migrations or allowed_removed_ids:
            print(
                "\n[dry-run] Would update baseline: "
                f"{starting_count} → {new_count} variants "
                f"({len(hash_migrations)} hash migration(s), "
                f"{len(allowed_removed_ids)} removal(s), "
                f"{len(new_variants)} addition(s))"
            )
            if hash_migrations and config.variant_id_migration_path:
                print(
                    "[dry-run] Would write variant-id migration map: "
                    f"{config.variant_id_migration_path}"
                )
        else:
            print(f"\n[dry-run] Would update baseline: {starting_count} → {new_count} variants")
        print("[dry-run] No files written.")
        return 0

    # --- Update baseline JSON ---
    baseline["variants"] = [_baseline_variant(v) for v in baseline["variants"] + new_variants]
    _normalize_baseline_payload(baseline)
    _refresh_summary_from_variants(baseline)
    _apply_verification_updates(
        baseline,
        promoted_variants=new_variants,
        removed_variants=removed_variants,
    )

    print(f"\nWriting baseline: {config.baseline_path.name} ({new_count} variants) …")
    changed_files: list[tuple[Path, Path]] = []
    changed_files.append((config.baseline_path, _write_json(config.baseline_path, baseline, output_dir=output_dir)))
    if hash_migration_records and config.variant_id_migration_path:
        target = _write_variant_id_migration_map(
            path=config.variant_id_migration_path,
            records=hash_migration_records,
            output_dir=output_dir,
        )
        changed_files.append((config.variant_id_migration_path, target))
        print(f"Wrote variant-id migration map → {config.variant_id_migration_path.name}")

    # --- Update the frozen verified-term variant count in contract checks ---
    if config.contract_checks_path:
        target = _update_py_constant(
            config.contract_checks_path,
            "EXPECTED_VERIFIED_TERM_VARIANT_COUNT",
            new_count,
            output_dir=output_dir,
        )
        if target:
            changed_files.append((config.contract_checks_path, target))
            print(f"Updated EXPECTED_VERIFIED_TERM_VARIANT_COUNT → {new_count}")
        else:
            print(
                "WARNING: could not update EXPECTED_VERIFIED_TERM_VARIANT_COUNT in "
                f"{config.contract_checks_path.name}"
            )
    else:
        print("Skipped contract-check constant update; no language-specific check path configured.")

    # --- Update the frozen unique coverage-key count in add-term checks ---
    print("Counting registry TOML coverage keys …")
    new_unique_key_count = _get_unique_coverage_key_count(config)

    if config.add_term_checks_path:
        target = _update_py_constant(
            config.add_term_checks_path,
            "EXPECTED_VERIFIED_TERM_UNIQUE_COVERAGE_KEYS",
            new_unique_key_count,
            output_dir=output_dir,
        )
        if target:
            changed_files.append((config.add_term_checks_path, target))
            print(f"Updated EXPECTED_VERIFIED_TERM_UNIQUE_COVERAGE_KEYS → {new_unique_key_count}")
        else:
            print(
                "WARNING: could not update EXPECTED_VERIFIED_TERM_UNIQUE_COVERAGE_KEYS in "
                f"{config.add_term_checks_path.name}"
            )
    else:
        print("Skipped add-term-check constant update; no language-specific check path configured.")

    # --- Update unique_coverage_key_count in sanity checks ---
    target = None
    if config.sanity_checks_path:
        target = _update_py_constant(
            config.sanity_checks_path,
            "_EXPECTED_UNIQUE_COVERAGE_KEYS",
            new_unique_key_count,
            output_dir=output_dir,
        )
    if target:
        changed_files.append((config.sanity_checks_path, target))
        print(f"Updated _EXPECTED_UNIQUE_COVERAGE_KEYS in sanity checks → {new_unique_key_count}")
    elif config.sanity_checks_path and config.sanity_checks_path.exists():
        # The sanity check uses a literal int inline, not a named constant - patch it directly
        text = config.sanity_checks_path.read_text(encoding="utf-8")
        import re
        pattern = r'(summary\.get\("unique_coverage_key_count"\),\s*)(\d+)'
        new_text, n = re.subn(pattern, rf"\g<1>{new_unique_key_count}", text)
        if n:
            target = _write_text(config.sanity_checks_path, new_text, output_dir=output_dir)
            changed_files.append((config.sanity_checks_path, target))
            print(f"Updated unique_coverage_key_count in sanity checks → {new_unique_key_count}")
        else:
            print(f"WARNING: could not patch unique_coverage_key_count in {config.sanity_checks_path.name}")
    else:
        print("Skipped sanity-check constant update; no language-specific check path configured.")

    _write_output_manifest(
        output_dir=output_dir,
        changed_files=changed_files,
        current_count=starting_count,
        new_count=new_count,
        new_unique_key_count=new_unique_key_count,
    )

    print(f"\n✓ Promotion complete: {starting_count} → {new_count} variants")
    print(f"  Unique coverage keys: {new_unique_key_count}")
    if output_dir is not None:
        print(f"  Changed files staged under: {output_dir}")
    print("\nNow run:")
    print("  docker compose exec -T -w /app web python support_checks/run_sanity_checks.py")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="Language package code, e.g. sv")
    parser.add_argument("--market", default=DEFAULT_MARKET, help="Market code, e.g. SE")
    parser.add_argument(
        "--baseline-json",
        type=Path,
        default=None,
        help=(
            "Baseline JSON to update. Defaults to "
            "languages/<language>/ingredient_matching/term_registry/baselines/verified_matcher_terms.json"
        ),
    )
    parser.add_argument(
        "--audit-module",
        default=None,
        help=(
            "Python module that provides build_variants(batch_size) and _variant_row(variant). "
            "Defaults to the language-specific verified-term audit module."
        ),
    )
    parser.add_argument(
        "--registry-module",
        default=None,
        help=(
            "Python module that provides load_registry_entries(). Defaults to "
            "languages.<language>.ingredient_matching.term_registry.registry."
        ),
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing files")
    parser.add_argument(
        "--migrate-hashes",
        action="store_true",
        help=(
            "Backward-compatible alias. Hash-equivalent ID migrations are automatic; "
            "truly removed entries still abort unless --allow-removals is set."
        ),
    )
    parser.add_argument(
        "--allow-removals",
        action="store_true",
        help=(
            "Allow confirmed intentional baseline removals after TOML entry inactivation/deletion. "
            "Only use after checking that every removed variant is expected."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Stage changed files under this writable directory instead of writing into /app. "
            "Useful for read-only production containers."
        ),
    )
    parser.add_argument(
        "--skip-check-constant-updates",
        action="store_true",
        help="Only update/stage the baseline JSON; do not patch local check-script constants.",
    )
    parser.add_argument(
        "--add-term-checks-path",
        type=Path,
        default=None,
        help="Optional check script path whose EXPECTED_VERIFIED_TERM_UNIQUE_COVERAGE_KEYS should be patched.",
    )
    parser.add_argument(
        "--contract-checks-path",
        type=Path,
        default=None,
        help="Optional check script path whose EXPECTED_VERIFIED_TERM_VARIANT_COUNT should be patched.",
    )
    parser.add_argument(
        "--sanity-checks-path",
        type=Path,
        default=None,
        help="Optional sanity script path whose unique coverage-key expectation should be patched.",
    )
    args = parser.parse_args()
    config = _build_config(args)
    try:
        return promote(
            config=config,
            dry_run=args.dry_run,
            migrate_hashes=args.migrate_hashes,
            allow_removals=args.allow_removals,
            output_dir=args.output_dir,
        )
    except PermissionError as exc:
        if args.output_dir is not None or args.dry_run:
            raise
        fallback_dir = Path(os.environ.get("DEAL_MEALS_BASELINE_OUTPUT_DIR", "/tmp/term-baseline-promotion"))
        print(
            "\nWARNING: baseline promotion could not write to the checkout "
            f"({exc}). Staging generated files instead."
        )
        print("Tip: in dev, prefer running the wrapper with `docker compose exec -T -u appuser -w /app web ...`.")
        return promote(
            config=config,
            dry_run=args.dry_run,
            migrate_hashes=args.migrate_hashes,
            allow_removals=args.allow_removals,
            output_dir=fallback_dir,
        )


if __name__ == "__main__":
    raise SystemExit(main())
