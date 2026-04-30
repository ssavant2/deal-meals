#!/usr/bin/env python3
"""Run the tracked app-support check suite.

Run:
    docker compose exec -T -w /app web python tests/run_app_support_checks.py
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


CHECKS = [
    "run_sanity_checks.py",
    "run_frontend_smoke.py",
    "run_cache_doctor_checks.py",
    "run_recipe_cache_refresh_decision_checks.py",
    "run_recipe_delta_patch_checks.py",
    "run_candidate_term_detail_checks.py",
    "run_recipe_ingredient_term_map_checks.py",
    "run_recipe_url_discovery_checks.py",
    "run_shadow_candidate_selection_checks.py",
    "run_ingredient_routing_probation_checks.py",
    "run_delta_ingredient_routing_policy_checks.py",
]


def main() -> int:
    tests_dir = Path(__file__).resolve().parent
    app_dir = tests_dir.parent
    failures = []

    for check in CHECKS:
        print(f"\n=== {check} ===", flush=True)
        result = subprocess.run(
            [sys.executable, str(tests_dir / check)],
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
