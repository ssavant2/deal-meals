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
from support_checks.generate_matcher_registry_coverage import (
    generate_coverage_files,
    write_coverage_files,
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
        self.assertEqual(report["summary"]["new_issue_count"], 3, report)
        codes = {issue["code"] for issue in report["new_issues"]}
        self.assertEqual(
            codes,
            {
                "fixture_missing_registry_coverage",
                "fixture_positive_missing_expected_matches",
                "generated_coverage_stale",
            },
        )
        fixture_issues = [
            issue
            for issue in report["new_issues"]
            if issue["code"].startswith("fixture_")
        ]
        self.assertTrue(
            all(issue["file"].endswith("matcher_regression_cases.json") for issue in fixture_issues),
            report,
        )

    def test_phase2_coverage_generation_allows_json_only_fixture_and_inventory(self) -> None:
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
            inventory_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"
            fixture_id = "matcher_regression_positive_phase2_generated_coverage"
            inventory_id = "legacy_synonym_phase2_generated_coverage"

            fixtures = json.loads(fixture_file.read_text(encoding="utf-8"))
            fixtures.append({
                "id": fixture_id,
                "policy_ref": "phase2_generated_coverage",
                "source_ref": "manual:phase2_generated_coverage",
                "recipe_name": "Synthetic Phase 2",
                "ingredients": ["1 dl phase2gron"],
                "offer": {"name": "Phase2gron", "category": "pantry"},
                "expected": 1,
                "expected_matches": [
                    {
                        "ingredient_index": 0,
                        "canonical": "phase2gron",
                        "must_match_keyword": "phase2gron",
                    }
                ],
            })
            fixture_file.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            line_count = len(fixture_file.read_text(encoding="utf-8").splitlines())
            inventory = json.loads(inventory_file.read_text(encoding="utf-8"))
            inventory.append({
                "id": inventory_id,
                "status": "wrapped_adapter",
                "kind": "legacy_synonym",
                "canonical": "phase2gron",
                "owner": "matcher",
                "policy_ref": "phase2_generated_coverage",
                "source_refs": ["manual:phase2_generated_coverage"],
                "fixture_refs": [fixture_id],
                "risk": "spelling_alias",
                "adapter_ref": "matcher_layer_diagnostics:phase2_generated_coverage",
                "line_refs": [
                    {
                        "path": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",
                        "start": 1,
                        "end": line_count,
                        "anchor": fixture_id,
                    }
                ],
                "notes": "Synthetic Phase 2 generated coverage row.",
            })
            inventory_file.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            generated = generate_coverage_files(tree_root=tree_root)
            changed_paths = {path.name for path in write_coverage_files(generated)}
            self.assertEqual(
                changed_paths,
                {"matcher_regression_case.toml", "matcher_rule_inventory.toml"},
            )

            regression_toml = (
                app_dir
                / "languages"
                / "sv"
                / "ingredient_matching"
                / "term_registry"
                / "entries"
                / "matcher_regression_case.toml"
            ).read_text(encoding="utf-8")
            inventory_toml = (
                app_dir
                / "languages"
                / "sv"
                / "ingredient_matching"
                / "term_registry"
                / "entries"
                / "matcher_rule_inventory.toml"
            ).read_text(encoding="utf-8")
            self.assertIn(f"fixture:matcher_regression_cases:{fixture_id}", regression_toml)
            self.assertIn(f"inventory:matcher_rule_inventory:{inventory_id}", inventory_toml)
            self.assertFalse(any(item.changed for item in generate_coverage_files(tree_root=tree_root)))

            report = run_preflight(tree_root=tree_root)

        codes = {issue["code"] for issue in report["new_issues"]}
        self.assertNotIn("fixture_missing_registry_coverage", codes, report)
        self.assertNotIn("inventory_missing_registry_coverage", codes, report)
        self.assertNotIn("generated_coverage_stale", codes, report)
        self.assertEqual(codes, {"expected_verified_term_unique_coverage_keys_stale"})


if __name__ == "__main__":
    unittest.main()
