"""Promote new term-registry variants into the frozen B-track baseline.

Run this after adding new TOML entries to
app/languages/sv/ingredient_matching/term_registry/entries/*.toml that produce
new hardcoded-keyword-output or mapping variants not yet in
baselines/verified_matcher_terms.json.

Usage:
    docker compose exec -T -w /app web python tests/promote_term_baseline.py
    docker compose exec -T -w /app web python tests/promote_term_baseline.py --dry-run

The script does not require the dev-only DB table
(tmp_term_pipeline_b_audit_variants). It regenerates the full variant list
from the current code and TOML state, finds the diff vs the frozen baseline,
and applies the minimal update needed.

After the script finishes, run the full sanity check to verify:
    docker compose exec -T -w /app web python tests/run_sanity_checks.py
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
BASELINE_PATH = (
    APP_DIR
    / "languages"
    / "sv"
    / "ingredient_matching"
    / "term_registry"
    / "baselines"
    / "verified_matcher_terms.json"
)
ADD_TERM_CHECKS_PATH = APP_DIR / "tests" / "run_term_registry_add_term_checks.py"
CONTRACT_CHECKS_PATH = APP_DIR / "tests" / "run_term_registry_contract_checks.py"
SANITY_CHECKS_PATH = APP_DIR / "tests" / "run_sanity_checks.py"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _generate_fresh_variants() -> list[dict]:
    """Run the B-track audit script in memory to get the current full variant list."""
    sys.path.insert(0, str(APP_DIR))
    from tests.run_term_pipeline_b_track_audit import build_variants, _variant_row
    raw = build_variants(batch_size=60)
    return [_variant_row(v) for v in raw]


def _get_unique_coverage_key_count() -> int:
    """Count unique registry TOML coverage keys (for EXPECTED_B2_UNIQUE_COVERAGE_KEYS)."""
    from tests.run_term_registry_add_term_checks import run_checks
    from types import SimpleNamespace
    payload, _ = run_checks(SimpleNamespace(
        language="sv",
        market="SE",
        report_dir=Path(tempfile.mkdtemp()),
    ))
    return int(payload["summary"].get("unique_coverage_key_count") or 0)


def _update_py_constant(path: Path, name: str, new_value: int) -> bool:
    """Replace `NAME = <old_int>` with `NAME = <new_int>` in a Python file."""
    text = path.read_text(encoding="utf-8")
    import re
    pattern = rf"^({re.escape(name)}\s*=\s*)(\d+)$"
    new_text, count = re.subn(pattern, rf"\g<1>{new_value}", text, flags=re.MULTILINE)
    if count == 0:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def promote(*, dry_run: bool = False) -> int:
    print("Loading current baseline …")
    baseline = _load_json(BASELINE_PATH)
    current_ids = {v["variant_id"] for v in baseline["variants"] if isinstance(v, dict) and v.get("variant_id")}
    current_count = len(baseline["variants"])

    print("Generating fresh variant list from code + TOML …")
    fresh_variants = _generate_fresh_variants()
    fresh_ids = {v["variant_id"] for v in fresh_variants if v.get("variant_id")}

    new_variants = [v for v in fresh_variants if v.get("variant_id") and v["variant_id"] not in current_ids]
    removed_ids = current_ids - fresh_ids

    if removed_ids:
        print(f"\n⚠️  WARNING: {len(removed_ids)} variant(s) in baseline are MISSING from fresh scan:")
        for vid in sorted(removed_ids)[:10]:
            print(f"   {vid}")
        print("This usually means a TOML entry or extraction function was removed.")
        print("Investigate before promoting. Aborting.")
        return 1

    if not new_variants:
        print(f"\nNothing to promote — baseline is up to date ({current_count} variants).")
        return 0

    print(f"\nNew variants to add: {len(new_variants)}")
    for v in new_variants:
        print(f"  [{v.get('batch_id','?')}] {v.get('canonical','?')} | {v.get('source_type','?')} | {v.get('variant_id','?')[:24]}")

    new_count = current_count + len(new_variants)
    if dry_run:
        print(f"\n[dry-run] Would update baseline: {current_count} → {new_count} variants")
        print("[dry-run] No files written.")
        return 0

    # --- Update baseline JSON ---
    updated_variants = baseline["variants"] + new_variants
    v_section = baseline.get("verification", {})

    # Update summary
    baseline["summary"]["variant_count"] = new_count

    # Update verification counts
    v_section["variant_count"] = new_count
    v_section.setdefault("status_counts", {})["audited"] = new_count

    # Update source_counts: tally source_type of new variants
    source_counts = dict(v_section.get("source_counts", {}))
    for v in new_variants:
        src = v.get("source_type", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1
    v_section["source_counts"] = source_counts

    # Update classification_counts: new extraction_helper/mapping variants have
    # no product_text unless explicitly audited, so count them as no_product_text
    classification_counts = dict(v_section.get("classification_counts", {}))
    classification_counts["no_product_text"] = (
        classification_counts.get("no_product_text", 0) + len(new_variants)
    )
    v_section["classification_counts"] = classification_counts

    assert sum(classification_counts.values()) == new_count, \
        f"classification total {sum(classification_counts.values())} != new_count {new_count}"

    baseline["variants"] = updated_variants
    baseline["verification"] = v_section

    print(f"\nWriting baseline: {BASELINE_PATH.name} ({new_count} variants) …")
    _write_json(BASELINE_PATH, baseline)

    # --- Update EXPECTED_B2_VARIANT_COUNT in contract checks ---
    if _update_py_constant(CONTRACT_CHECKS_PATH, "EXPECTED_B2_VARIANT_COUNT", new_count):
        print(f"Updated EXPECTED_B2_VARIANT_COUNT → {new_count}")
    else:
        print(f"WARNING: could not update EXPECTED_B2_VARIANT_COUNT in {CONTRACT_CHECKS_PATH.name}")

    # --- Update EXPECTED_B2_UNIQUE_COVERAGE_KEYS in add_term_checks ---
    print("Counting registry TOML coverage keys …")
    new_unique_key_count = _get_unique_coverage_key_count()

    if _update_py_constant(ADD_TERM_CHECKS_PATH, "EXPECTED_B2_UNIQUE_COVERAGE_KEYS", new_unique_key_count):
        print(f"Updated EXPECTED_B2_UNIQUE_COVERAGE_KEYS → {new_unique_key_count}")
    else:
        print(f"WARNING: could not update EXPECTED_B2_UNIQUE_COVERAGE_KEYS in {ADD_TERM_CHECKS_PATH.name}")

    # --- Update unique_coverage_key_count in sanity checks ---
    if _update_py_constant(SANITY_CHECKS_PATH, "_EXPECTED_UNIQUE_COVERAGE_KEYS", new_unique_key_count):
        print(f"Updated _EXPECTED_UNIQUE_COVERAGE_KEYS in sanity checks → {new_unique_key_count}")
    else:
        # The sanity check uses a literal int inline, not a named constant - patch it directly
        text = SANITY_CHECKS_PATH.read_text(encoding="utf-8")
        import re
        pattern = r'(summary\.get\("unique_coverage_key_count"\),\s*)(\d+)'
        new_text, n = re.subn(pattern, rf"\g<1>{new_unique_key_count}", text)
        if n:
            SANITY_CHECKS_PATH.write_text(new_text, encoding="utf-8")
            print(f"Updated unique_coverage_key_count in sanity checks → {new_unique_key_count}")
        else:
            print(f"WARNING: could not patch unique_coverage_key_count in {SANITY_CHECKS_PATH.name}")

    print(f"\n✓ Promotion complete: {current_count} → {new_count} variants")
    print(f"  Unique coverage keys: {new_unique_key_count}")
    print(f"\nNow run:")
    print(f"  docker compose exec -T -w /app web python tests/run_sanity_checks.py")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing files")
    args = parser.parse_args()
    return promote(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
