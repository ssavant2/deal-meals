from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
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
from support_checks.audit_matcher_contract_json_authority import audit as audit_json_authority
from support_checks.prefix_schema import allowed_prefixes
from support_checks.run_verified_term_audit import (
    AuditVariant,
    IDENTITY_HASH_VERSION_V1,
    IDENTITY_HASH_VERSION_V2,
    build_variants,
)
from languages.sv.ingredient_matching.term_registry.exports import (
    build_keyword_extra_parents_export_from_entries,
)
from languages.sv.ingredient_matching.term_registry.registry import load_registry_entries


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
        self.assertEqual(codes, set(), report)

    def test_phase3_hash_tolerance_ignores_source_ref(self) -> None:
        variant = AuditVariant(
            source_order=20,
            source_type="matcher_regression_case",
            source_file="app/languages/sv/matcher_contracts/matcher_regression_cases.json",
            source_ref="manual:phase3_before",
            source_id="matcher_regression_positive_phase3_source_ref_edit",
            variant_role="positive_regression",
            variant_text="matcher_regression_positive_phase3_source_ref_edit: Phase 3",
            canonical="phase3stable",
            expected_family="phase3stable",
            ingredient_text="1 dl phase3stable",
            product_text="Phase3stable",
            expected=1,
        )

        before = variant.with_identity(row_index=1, batch_size=60, hash_version=IDENTITY_HASH_VERSION_V2)
        after = replace(variant, source_ref="manual:phase3_after").with_identity(
            row_index=1,
            batch_size=60,
            hash_version=IDENTITY_HASH_VERSION_V2,
        )

        self.assertEqual(before.variant_id, after.variant_id)
        self.assertNotEqual(
            variant.variant_id_for_hash_version(IDENTITY_HASH_VERSION_V1),
            replace(variant, source_ref="manual:phase3_after").variant_id_for_hash_version(
                IDENTITY_HASH_VERSION_V1
            ),
        )

    def test_phase3_current_stable_variant_ids_are_unique(self) -> None:
        variants = build_variants(batch_size=60, hash_version=IDENTITY_HASH_VERSION_V2)
        variant_ids = [variant.variant_id for variant in variants]

        self.assertEqual(len(variant_ids), len(set(variant_ids)))

    def test_phase4_cli_e2e(self) -> None:
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

            fixture_id = "keyword_extra_parent_citrusfrukter_phasefyraapelsin_positive"
            inventory_id = "legacy_parent_citrusfrukter_phasefyraapelsin_family"
            policy_ref = "keyword_extra_parent_citrusfrukter_phasefyraapelsin_family"
            live_app_dir = Path(__file__).resolve().parents[2]
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "keyword-extra-parent",
                    "citrusfrukter",
                    "--kids",
                    "phasefyraapelsin",
                    "--recipe-name",
                    "Synthetic Phase 4",
                    "--ingredient",
                    "3-4 citrusfrukter (valfri sort)",
                    "--offer-names",
                    "Phasefyraapelsin",
                    "--offer-category",
                    "fruit",
                    "--policy-ref",
                    policy_ref,
                    "--inventory-id",
                    inventory_id,
                    "--tree-root",
                    str(tree_root),
                    "--report-root",
                    str(tree_root / "support-reports"),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"
            inventory_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"
            keyword_extra_parent_file = (
                app_dir
                / "languages"
                / "sv"
                / "ingredient_matching"
                / "term_registry"
                / "entries"
                / "keyword_extra_parent.toml"
            )
            deep_sanity_file = app_dir / "support_checks" / "run_deep_matcher_sanity.py"

            fixtures = json.loads(fixture_file.read_text(encoding="utf-8"))
            inventory = json.loads(inventory_file.read_text(encoding="utf-8"))
            self.assertTrue(any(item["id"] == fixture_id for item in fixtures))
            self.assertTrue(any(item["id"] == inventory_id for item in inventory))
            self.assertIn("phasefyraapelsin", keyword_extra_parent_file.read_text(encoding="utf-8"))
            self.assertIn(policy_ref, deep_sanity_file.read_text(encoding="utf-8"))

            generated = generate_coverage_files(tree_root=tree_root)
            self.assertFalse(any(item.changed for item in generated))
            report = run_preflight(tree_root=tree_root)
            codes = {issue["code"] for issue in report["new_issues"]}
            self.assertNotIn("fixture_missing_registry_coverage", codes, report)
            self.assertNotIn("inventory_missing_registry_coverage", codes, report)
            self.assertNotIn("generated_coverage_stale", codes, report)

            gate_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "gates",
                    "--track",
                    "B",
                    "--tree-root",
                    str(tree_root),
                    "--policy-ref",
                    policy_ref,
                    "--case-id",
                    fixture_id,
                    "--fixtures-changed",
                    "--inventory-changed",
                    "--no-registry-changed",
                    "--no-runtime-changed",
                    "--no-support-checks-changed",
                    "--dry-run",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(gate_result.returncode, 0, gate_result.stderr + gate_result.stdout)

    def test_phase5_prefix_schema_and_convention_entry(self) -> None:
        self.assertIn("current_review:", allowed_prefixes("source_ref"))
        self.assertIn("matcher_layer_diagnostics:", allowed_prefixes("adapter_ref"))

        with tempfile.TemporaryDirectory() as tmp:
            entries_dir = Path(tmp)
            (entries_dir / "keyword_extra_parent.toml").write_text(
                "\n".join([
                    "[[entries]]",
                    'language = "sv"',
                    'market = "SE"',
                    'canonical = "phasefemfrukt"',
                    'status = "active"',
                    'variants = ["phasefemapelsin"]',
                    'route_terms = ["phasefemfrukt"]',
                    'source_refs = ["manual:phase5_convention_test"]',
                    'layer_policy = ["route_only"]',
                    "",
                ]),
                encoding="utf-8",
            )

            entries = load_registry_entries(entries_dir=entries_dir)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].entry_id, "sv-se.family.phasefemfrukt.phasefemapelsin")
        self.assertEqual(
            entries[0].language_payload["coverage"],
            [
                {
                    "source_family": "keyword_extra_parent",
                    "canonical": "phasefemfrukt",
                    "variant": "phasefemapelsin",
                    "layer_role": "keyword_extra_parent_mapping",
                }
            ],
        )
        self.assertEqual(
            build_keyword_extra_parents_export_from_entries(entries),
            {"phasefemapelsin": "phasefemfrukt"},
        )

    def test_phase5_json_authority_audit_vetoes_current_tree(self) -> None:
        hits = audit_json_authority(Path(__file__).resolve().parents[2])
        blocking_paths = {
            hit.path.name
            for hit in hits
            if hit.classification == "blocking_reader"
        }
        self.assertIn("generate_matcher_registry_coverage.py", blocking_paths)
        self.assertIn("run_matcher_change_preflight.py", blocking_paths)


if __name__ == "__main__":
    unittest.main()
