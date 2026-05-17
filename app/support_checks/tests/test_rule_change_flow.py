from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from support_checks.run_matcher_change_preflight import (
    DEFAULT_BASELINE_FILE,
    DEFAULT_FIXTURE_FILE,
    DEFAULT_INVENTORY_FILE,
    DEFAULT_REGISTRY_ENTRIES_DIR,
    DEFAULT_SNAPSHOT_FILE,
    run_preflight,
)


class MatcherRuleChangePreflightTests(unittest.TestCase):
    def test_current_tree_preflight_is_clean(self) -> None:
        report = run_preflight()

        self.assertTrue(report["summary"]["passed"], report)
        self.assertEqual(report["summary"]["new_issue_count"], 0)
        self.assertEqual(report["summary"]["known_issue_count"], 0)

    def test_positive_fixture_missing_expected_matches_is_actionable(self) -> None:
        fixtures = json.loads(DEFAULT_FIXTURE_FILE.read_text(encoding="utf-8"))
        fixture = next(
            item
            for item in fixtures
            if item["id"] == "matcher_regression_positive_havssalt_250g_maldon"
        )
        broken_fixture = deepcopy(fixture)
        broken_fixture.pop("expected_matches", None)
        fixtures[fixtures.index(fixture)] = broken_fixture

        with tempfile.TemporaryDirectory() as tmp:
            fixture_file = Path(tmp) / "matcher_regression_cases.json"
            fixture_file.write_text(
                json.dumps(fixtures, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            report = run_preflight(
                fixture_file=fixture_file,
                inventory_file=DEFAULT_INVENTORY_FILE,
                registry_entries_dir=DEFAULT_REGISTRY_ENTRIES_DIR,
                baseline_file=DEFAULT_BASELINE_FILE,
                snapshot_file=DEFAULT_SNAPSHOT_FILE,
            )

        codes = {issue["code"] for issue in report["new_issues"]}
        self.assertIn("fixture_positive_missing_expected_matches", codes)
        messages = "\n".join(issue["message"] for issue in report["new_issues"])
        self.assertIn("top-level expected_matches.canonical", messages)

    def test_tree_root_preflight_reads_temporary_contract_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = tree_root / "app"
            shutil.copytree(
                DEFAULT_FIXTURE_FILE.parents[1],
                app_dir / "languages" / "sv",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            support_checks_dir = Path(__file__).resolve().parents[1]
            shutil.copytree(
                support_checks_dir,
                app_dir / "support_checks",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )

            fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"
            fixtures = json.loads(fixture_file.read_text(encoding="utf-8"))
            fixture = next(
                item
                for item in fixtures
                if item["id"] == "matcher_regression_positive_havssalt_250g_maldon"
            )
            fixture.pop("expected_matches", None)
            fixture_file.write_text(
                json.dumps(fixtures, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            report = run_preflight(tree_root=tree_root)

        self.assertFalse(report["summary"]["passed"], report)
        self.assertEqual(report["summary"]["new_issue_count"], 2, report)
        codes = {issue["code"] for issue in report["new_issues"]}
        self.assertEqual(
            codes,
            {
                "fixture_missing_registry_coverage",
                "fixture_positive_missing_expected_matches",
            },
        )
        self.assertTrue(
            all(issue["file"].endswith("matcher_regression_cases.json") for issue in report["new_issues"]),
            report,
        )


if __name__ == "__main__":
    unittest.main()
