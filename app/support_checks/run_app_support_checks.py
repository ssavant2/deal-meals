#!/usr/bin/env python3
"""Run the tracked app-support check suite.

Run:
    docker compose exec -T -w /app web python support_checks/run_app_support_checks.py
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


CHECKS = [
    "run_sanity_checks.py",
    "run_frontend_smoke.py",
    "run_cache_doctor_checks.py",
    "run_cache_reconciliation_checks.py",
    "run_recipe_cache_refresh_decision_checks.py",
    "run_offer_cache_refresh_decision_checks.py",
    "run_cache_delta_planner_checks.py",
    "run_cache_delta_term_fallback_checks.py",
    "run_recipe_delta_patch_checks.py",
    "run_delta_probation_runtime_checks.py",
    "run_pantry_search_index_checks.py",
    "run_cache_worker_cpu_checks.py",
    "run_matcher_version_checks.py",
    "run_database_session_defaults_checks.py",
    "run_candidate_term_detail_checks.py",
    "run_candidate_refresh_guard_checks.py",
    "run_recipe_ingredient_term_map_checks.py",
    "run_matching_preference_filter_checks.py",
    "audit_dietary_exclusion_profiles.py",
    "run_recipe_url_discovery_checks.py",
    "run_recipe_source_profile_checks.py",
    "run_scraper_p0_checks.py",
    "run_scraper_history_checks.py",
    "run_mathem_store_ssr_checks.py",
    "run_scraper_health_checks.py",
    "run_ingredient_routing_mode_checks.py",
    "run_delta_ingredient_routing_policy_checks.py",
]

CHECK_ARGS = {
    "audit_dietary_exclusion_profiles.py": [
        "--check",
        "--offer-scan-limit",
        "5000",
        "--recipe-scan-limit",
        "3000",
    ],
}


def main() -> int:
    support_checks_dir = Path(__file__).resolve().parent
    app_dir = support_checks_dir.parent
    failures = []

    for check in CHECKS:
        print(f"\n=== {check} ===", flush=True)
        result = subprocess.run(
            [sys.executable, str(support_checks_dir / check), *CHECK_ARGS.get(check, [])],
            cwd=app_dir,
            check=False,
        )
        if result.returncode != 0:
            failures.append((check, result.returncode))

    print("\n========================================", flush=True)
    if failures:
        print("FAILED SUPPORT CHECKS:", flush=True)
        for check, returncode in failures:
            print(f"  {check}: exit {returncode}", flush=True)
        print("========================================", flush=True)
        return 1

    print(f"ALL SUPPORT CHECKS PASSED ({len(CHECKS)} scripts)", flush=True)
    print("========================================", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
