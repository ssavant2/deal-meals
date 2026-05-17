#!/usr/bin/env python3
"""One-shot verified-term variant_id migration from v1 to v2.

v1 IDs included source_ref provenance text in the hash input. v2 IDs use the
stable semantic payload from support_checks.run_verified_term_audit and ignore
source_ref so provenance edits do not force baseline hash migrations.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from support_checks.promote_term_baseline import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_SWEDISH_ADD_TERM_CHECKS_PATH,
    DEFAULT_SWEDISH_BASELINE_PATH,
    DEFAULT_SWEDISH_CONTRACT_CHECKS_PATH,
    DEFAULT_SWEDISH_SANITY_CHECKS_PATH,
    DEFAULT_SWEDISH_VARIANT_ID_MIGRATION_PATH,
    PromotionConfig,
    promote,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--dry-run", action="store_true", help="Show the migration without writing files.")
    parser.add_argument(
        "--allow-removals",
        action="store_true",
        help="Allow true removals if any are found; not expected for the v1→v2 migration.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Stage changed files under this directory instead of writing into the checkout.",
    )
    args = parser.parse_args()

    config = PromotionConfig(
        language="sv",
        market="SE",
        baseline_path=DEFAULT_SWEDISH_BASELINE_PATH,
        audit_module="support_checks.run_verified_term_audit",
        registry_module="languages.sv.ingredient_matching.term_registry.registry",
        batch_size=args.batch_size,
        add_term_checks_path=DEFAULT_SWEDISH_ADD_TERM_CHECKS_PATH,
        contract_checks_path=DEFAULT_SWEDISH_CONTRACT_CHECKS_PATH,
        sanity_checks_path=DEFAULT_SWEDISH_SANITY_CHECKS_PATH,
        variant_id_migration_path=DEFAULT_SWEDISH_VARIANT_ID_MIGRATION_PATH,
    )
    return promote(
        config=config,
        dry_run=args.dry_run,
        migrate_hashes=True,
        allow_removals=args.allow_removals,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
