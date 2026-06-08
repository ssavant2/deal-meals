from __future__ import annotations

import contextlib
from copy import deepcopy
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

from cli import dm as dm_cli
from support_checks.run_matcher_change_preflight import (
    DEFAULT_BASELINE_FILE,
    DEFAULT_REGISTRY_ENTRIES_DIR,
    DEFAULT_SNAPSHOT_FILE,
    _check_match_bridge_positive_fixture_hits,
    _check_space_norm_private_usage,
    run_preflight,
)
from support_checks import run_term_registry_guard_bridge_checks as guard_bridge_checks
from support_checks.refresh_matcher_rule_inventory_line_refs import (
    refresh_inventory_line_refs_from_contract_source,
)
from support_checks.matcher_contracts import (
    contract_spec_by_name,
    contract_paths,
    fixture_contract_path,
    inventory_contract_path,
    load_fixture_contract,
    load_inventory_contract,
    load_contract_source,
    write_contract_source,
    write_fixture_contract,
    write_inventory_contract,
)
from support_checks.generate_matcher_registry_coverage import (
    generate_coverage_files,
    write_coverage_files,
)
from support_checks.audit_matcher_contract_toml_sources import (
    audit_contract_sources,
    json_report as toml_source_json_report,
)
from support_checks.prefix_schema import allowed_prefixes, non_registered_prefixes
from support_checks.run_verified_term_audit import (
    AuditVariant,
    IDENTITY_HASH_VERSION_V1,
    IDENTITY_HASH_VERSION_V2,
    build_variants,
)
from support_checks.promote_term_baseline import (
    PromotionConfig,
    promote,
    _content_key,
    _coverage_key,
    _expected_count_constants_are_stale,
    _matcher_regression_case_identity,
    _update_expected_count_constants,
    _write_variant_id_migration_map,
)
from languages.sv.ingredient_matching.rule_models import MatchBridge
from languages.sv.ingredient_matching.runtime_rule_overlays import (
    RuntimeRuleOverlayError,
    load_runtime_rule_overlays,
)
from languages.sv.ingredient_matching.term_registry.exports import (
    build_ingredient_parents_export_from_entries,
    build_ingredient_routing_parent_export_from_entries,
    build_keyword_extra_parents_export_from_entries,
    build_no_match_policies_export_from_entries,
    build_offer_extra_keywords_export_from_entries,
    build_parent_match_only_export_from_entries,
    build_recipe_routing_extra_alias_export_from_entries,
)
from languages.sv.ingredient_matching.term_registry.registry import load_registry_entries


DEFAULT_FIXTURE_FILE = fixture_contract_path()
DEFAULT_INVENTORY_FILE = inventory_contract_path()


def _copy_matcher_tree(tree_root: Path) -> Path:
    app_dir = tree_root / "app"
    live_app_dir = Path(__file__).resolve().parents[2]
    shutil.copytree(
        live_app_dir / "languages" / "sv",
        app_dir / "languages" / "sv",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    live_languages_dir = live_app_dir / "languages"
    shutil.copytree(
        live_languages_dir / "term_registry",
        app_dir / "languages" / "term_registry",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    support_checks_dir = Path(__file__).resolve().parents[1]
    shutil.copytree(
        support_checks_dir,
        app_dir / "support_checks",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return app_dir


def _runtime_overlay_probe(app_dir: Path, expression: str) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(app_dir)
    script = f"""
import json
import sys
import types
from pathlib import Path

app_dir = Path({str(app_dir)!r})
for name, path in (
    ("languages", app_dir / "languages"),
    ("languages.sv", app_dir / "languages" / "sv"),
    (
        "languages.sv.ingredient_matching",
        app_dir / "languages" / "sv" / "ingredient_matching",
    ),
):
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module

from languages.sv.ingredient_matching.blocker_data import FALSE_POSITIVE_BLOCKERS, GLOBAL_PRODUCT_NAME_BLOCKERS, PRODUCT_NAME_BLOCKERS
from languages.sv.ingredient_matching.carrier_context import (
    CARRIER_CONTEXT_REQUIRED,
    CARRIER_PRODUCTS,
    CONTEXT_REQUIRED_WORDS,
    CONTEXT_WORD_KEYWORD_EXEMPTIONS,
    INGREDIENT_REQUIRES_IN_PRODUCT,
    KEYWORD_SUPPRESSED_BY_CONTEXT,
)
from languages.sv.ingredient_matching.extraction import extract_keywords_from_product
from languages.sv.ingredient_matching.keywords import (
    FLAVOR_WORDS,
    IMPORTANT_SHORT_KEYWORDS,
    NON_FOOD_KEYWORDS,
    PROCESSED_FOODS,
    STOP_WORDS,
)
from languages.sv.ingredient_matching.match_filters import (
    PRODUCT_NAME_SUBSTITUTIONS,
    _QUALIFIER_REQUIRED_KEYWORDS,
    SECONDARY_INGREDIENT_PATTERNS,
    check_secondary_ingredient_patterns,
)
from languages.sv.ingredient_matching.normalization import _apply_space_normalizations
from languages.sv.ingredient_matching.processed_rules import (
    PROCESSED_PRODUCT_RULES,
    PROCESSED_RULES_COMPOUND_EXEMPTIONS,
    SPICE_VS_FRESH_RULES,
    STRICT_PROCESSED_RULES,
)
from languages.sv.ingredient_matching.recipe_context import CUISINE_CONTEXT
from languages.sv.ingredient_matching.compound_text import _COMPOUND_STRICT_PREFIX_KEYWORDS
from languages.sv.ingredient_matching.specialty_rules import (
    BIDIRECTIONAL_PER_KEYWORD,
    QUALIFIER_EQUIVALENTS,
    SPECIALTY_QUALIFIERS,
)
print(json.dumps({expression}, ensure_ascii=False, sort_keys=True))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=app_dir,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr + result.stdout)
    return json.loads(result.stdout)


class MatcherRuleChangePreflightTests(unittest.TestCase):
    def test_contract_api_round_trip_preserves_payloads(self) -> None:
        fixtures = load_fixture_contract(DEFAULT_FIXTURE_FILE)
        inventory = load_inventory_contract(DEFAULT_INVENTORY_FILE)
        with tempfile.TemporaryDirectory() as tmp:
            fixture_copy = Path(tmp) / "matcher_regression_cases.toml"
            inventory_copy = Path(tmp) / "matcher_rule_inventory.toml"

            write_fixture_contract(fixtures, fixture_copy)
            write_inventory_contract(inventory, inventory_copy)

            self.assertEqual(load_fixture_contract(fixture_copy), fixtures)
            self.assertEqual(load_inventory_contract(inventory_copy), inventory)

        with tempfile.TemporaryDirectory() as tmp:
            app_dir = _copy_matcher_tree(Path(tmp))
            paths = contract_paths(Path(tmp))

            self.assertEqual(paths.app_dir, app_dir)
            self.assertTrue(paths.fixture_file.exists())
            self.assertTrue(paths.inventory_file.exists())
            self.assertEqual(len(load_fixture_contract(tree_root=Path(tmp))), len(fixtures))
            self.assertEqual(len(load_inventory_contract(tree_root=Path(tmp))), len(inventory))

    def test_current_tree_preflight_is_clean(self) -> None:
        report = run_preflight()

        self.assertTrue(report["summary"]["passed"], report)
        self.assertEqual(report["summary"]["new_issue_count"], 0)
        self.assertEqual(report["summary"]["known_issue_count"], 0)

    def test_runtime_overlay_loader_validates_schema_and_merges_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            overlay_file = Path(tmp) / "runtime_rule_overlays.toml"
            overlay_file.write_text(
                """
[[product_name_blockers]]
keyword = "Färskost"
blockers = ["Chips"]
reason = "Synthetic merge test."

[[product_name_blockers]]
keyword = "farskost"
blockers = ["Snacks"]
reason = "Synthetic normalized-key merge test."

[[false_positive_blockers]]
keyword = "Ost"
blockers = ["Ostron"]
reason = "Synthetic FPB test."

[[keyword_suppressed_by_context]]
keyword = "Ris"
context = ["Glas, ris"]
reason = "Synthetic KSBC test."

[[processed_product_rules]]
keyword = "Phase Processed"
blocked_product_words = ["Phase Blocked"]
reason = "Synthetic processed rule."

[[processed_rule_compound_exemptions]]
keyword = "Phase Processed"
compounds = ["Phase Compound"]
reason = "Synthetic processed exemption."

[[global_product_name_blockers]]
terms = ["Phase Pet Brand"]
reason = "Synthetic global blocker test."

[[strict_processed_rules]]
terms = ["Phase Processed"]
reason = "Synthetic strict processed rule."

[[spice_fresh_rules]]
keyword = "Phase Spice"
blocked_product_words = ["Phase Fresh"]
spice_indicators = ["Phase Spice Indicator"]
fresh_product_words = ["Phase Fresh Product"]
dried_indicators = ["Phase Dried Indicator"]
reason = "Synthetic spice/fresh rule."

[[carrier_context_required]]
terms = ["Phase Carrier Context"]
reason = "Synthetic carrier-context-required test."

[[context_required_words]]
terms = ["Phase Context Required"]
reason = "Synthetic context-required test."

[[ingredient_requires_in_product]]
terms = ["Phase Ingredient Context"]
reason = "Synthetic ingredient-requires-product test."

[[space_normalizations]]
source = "Phase Space"
target = "PhaseSpace"
reason = "Synthetic legacy space-normalization entry."

[[keyword_set_updates]]
surface = "flavor_words"
action = "add"
terms = ["Phase Flavor"]
reason = "Synthetic flavor update."

[[keyword_set_updates]]
surface = "stop_words"
action = "add"
terms = ["Phase Stop"]
reason = "Synthetic stop-word update."

[[keyword_set_updates]]
surface = "non_food_keywords"
action = "add"
terms = ["Phase Nonfood"]
reason = "Synthetic non-food update."

[[keyword_set_updates]]
surface = "qualifier_required_keywords"
action = "add"
terms = ["Phase Qualifier Required"]
reason = "Synthetic qualifier-required update."

[[carrier_set_updates]]
surface = "carrier_products"
action = "add"
terms = ["Phase Carrier"]
reason = "Synthetic carrier update."

[[context_word_keyword_exemptions]]
keyword = "Phase Keyword"
context_words = ["Phase Context"]
reason = "Synthetic context-word exemption."

[[product_name_substitutions]]
required_words = ["Phase Required"]
old_keyword = "Phase Old"
new_keyword = "Phase New"
reason = "Synthetic product substitution."

[[secondary_ingredient_patterns]]
keyword = "Phase Secondary"
blockers = ["Phase Blocker"]
exceptions = ["Phase Exception"]
reason = "Synthetic secondary pattern."
""",
                encoding="utf-8",
            )

            overlays = load_runtime_rule_overlays(overlay_file)
            self.assertEqual(overlays.product_name_blockers["färskost"], {"chips", "snacks"})
            self.assertEqual(overlays.false_positive_blockers["ost"], {"ostron"})
            self.assertEqual(overlays.keyword_suppressed_by_context["ris"], {"glas, ris"})
            self.assertEqual(overlays.processed_product_rules["phase processed"], {"phase blocked"})
            self.assertEqual(
                overlays.processed_rule_compound_exemptions["phase processed"],
                {"phase compound"},
            )
            self.assertEqual(overlays.global_product_name_blockers, {"phase pet brand"})
            self.assertEqual(overlays.strict_processed_rules, {"phase processed"})
            self.assertEqual(
                overlays.spice_fresh_rules["phase spice"]["blocked_product_words"],
                {"phase fresh"},
            )
            self.assertEqual(
                overlays.spice_fresh_rules["phase spice"]["spice_indicators"],
                {"phase spice indicator"},
            )
            self.assertEqual(
                overlays.spice_fresh_rules["phase spice"]["fresh_product_words"],
                {"phase fresh product"},
            )
            self.assertEqual(
                overlays.spice_fresh_rules["phase spice"]["dried_indicators"],
                {"phase dried indicator"},
            )
            self.assertEqual(overlays.carrier_context_required, {"phase carrier context"})
            self.assertEqual(overlays.context_required_words, {"phase context required"})
            self.assertEqual(overlays.ingredient_requires_in_product, {"phase ingredient context"})
            self.assertEqual(overlays.space_normalizations, (("phase space", "phasespace"),))
            self.assertEqual(overlays.keyword_set_updates["flavor_words"]["add"], {"phase flavor"})
            self.assertEqual(overlays.keyword_set_updates["stop_words"]["add"], {"phase stop"})
            self.assertEqual(overlays.keyword_set_updates["non_food_keywords"]["add"], {"phase nonfood"})
            self.assertEqual(
                overlays.keyword_set_updates["qualifier_required_keywords"]["add"],
                {"phase qualifier required"},
            )
            self.assertEqual(overlays.carrier_set_updates["carrier_products"]["add"], {"phase carrier"})
            self.assertEqual(overlays.context_word_keyword_exemptions["phase keyword"], {"phase context"})
            self.assertEqual(
                overlays.product_name_substitutions,
                ((frozenset({"phase required"}), "phase old", "phase new"),),
            )
            self.assertEqual(
                overlays.secondary_ingredient_patterns["phase secondary"],
                ({"phase blocker"}, {"phase exception"}),
            )

            overlay_file.write_text(
                """
[[product_name_blockers]]
id = "runtime_pnb_phasev2"
status = "active"
keyword = "phasev2"
blockers = ["Phase Active"]
reason = "Synthetic active v2 entry."

[[product_name_blockers]]
id = "runtime_pnb_phasev2_inactive"
status = "inactive"
keyword = "phasev2"
blockers = ["Phase Inactive"]
reason = "Synthetic inactive v2 entry."
inactive_reason = "Synthetic inactivation."

[[space_normalizations]]
id = "runtime_space_normalization_phase_v2_phasev2"
status = "active"
source = "phase v2"
target = "phasev2"
reason = "Synthetic active pair entry."

[[space_normalizations]]
id = "runtime_space_normalization_phase_v2_ignored"
status = "inactive"
source = "phase v2 ignored"
target = "ignored"
reason = "Synthetic inactive pair entry."
inactive_reason = "Synthetic inactivation."
""",
                encoding="utf-8",
            )
            overlays = load_runtime_rule_overlays(overlay_file)
            self.assertEqual(overlays.product_name_blockers["phasev2"], {"phase active"})
            self.assertEqual(overlays.space_normalizations, (("phase v2", "phasev2"),))

            overlay_file.write_text(
                """
[[product_name_blockers]]
id = "runtime_pnb_duplicate"
status = "active"
keyword = "phaseone"
blockers = ["x"]
reason = "Synthetic duplicate id one."

[[false_positive_blockers]]
id = "runtime_pnb_duplicate"
status = "active"
keyword = "phasetwo"
blockers = ["y"]
reason = "Synthetic duplicate id two."
""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeRuleOverlayError, "duplicate id"):
                load_runtime_rule_overlays(overlay_file)

            overlay_file.write_text(
                """
[[product_name_blockers]]
id = "runtime_pnb_phasebad_a"
status = "active"
keyword = "phasebad"
blockers = ["x"]
reason = "Synthetic duplicate value one."

[[product_name_blockers]]
id = "runtime_pnb_phasebad_b"
status = "active"
keyword = "phasebad"
blockers = ["x"]
reason = "Synthetic duplicate value two."
""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeRuleOverlayError, "duplicates active"):
                load_runtime_rule_overlays(overlay_file)

            overlay_file.write_text(
                """
[[product_name_blockers]]
keyword = "phasebad"
blockers = ["x"]
reason = "Synthetic bad key."
unexpected = true
""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeRuleOverlayError, "unknown keys"):
                load_runtime_rule_overlays(overlay_file)

            overlay_file.write_text(
                """
[[false_positive_blockers]]
keyword = "phasebad"
blockers = []
reason = "Synthetic empty list."
""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeRuleOverlayError, "must not be empty"):
                load_runtime_rule_overlays(overlay_file)

    def test_runtime_overlay_preserves_pnb_merge_order_in_temp_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            overlay_file = app_dir / "languages" / "sv" / "ingredient_matching" / "runtime_rule_overlays.toml"
            blocker_data_file = app_dir / "languages" / "sv" / "ingredient_matching" / "blocker_data.py"

            probe_expression = """
{
    "havregryn": sorted(PRODUCT_NAME_BLOCKERS.get("havregryn", [])),
}
"""
            baseline = _runtime_overlay_probe(app_dir, probe_expression)

            overlay_file.write_text(
                """
[[product_name_blockers]]
keyword = "havregryn"
blockers = ["phaseoverlay"]
reason = "Synthetic CLI-overlay merge-order canary."
""",
                encoding="utf-8",
            )
            merged = _runtime_overlay_probe(app_dir, probe_expression)
            self.assertIn("phaseoverlay", merged["havregryn"])
            self.assertIn("wasa", merged["havregryn"])
            self.assertTrue(set(baseline["havregryn"]).issubset(set(merged["havregryn"])))

            blocker_data_text = blocker_data_file.read_text(encoding="utf-8")
            historical_havregryn_match = re.search(
                r"    'havregryn': \{'knäcke', 'knacke', 'knäckebröd', 'knackebrod', 'wasa', 'kex',\n"
                r"                  'quinoa'\},  # \"Gröt Havregryn & quinoa\" = blend (?:≠|!=) plain rolled oats for smulpaj[^\n]*\n",
                blocker_data_text,
            )
            self.assertIsNotNone(historical_havregryn_match)
            historical_havregryn = historical_havregryn_match.group(0)
            self.assertIn(historical_havregryn, blocker_data_text)
            blocker_data_file.write_text(
                blocker_data_text.replace(historical_havregryn, ""),
                encoding="utf-8",
            )
            overlay_file.write_text(
                """
[[product_name_blockers]]
keyword = "havregryn"
blockers = ["knäcke", "knacke", "knäckebröd", "knackebrod", "wasa", "kex", "quinoa"]
reason = "Synthetic temp-tree move of the historical havregryn overlay entry."
""",
                encoding="utf-8",
            )
            moved = _runtime_overlay_probe(app_dir, probe_expression)
            self.assertEqual(moved["havregryn"], baseline["havregryn"])

    def test_preflight_flags_direct_space_norm_private_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            probe_file = (
                app_dir
                / "languages"
                / "sv"
                / "ingredient_matching"
                / "space_norm_private_probe.py"
            )
            probe_file.write_text(
                """
from .normalization import _SPACE_NORM_LOOKUP, _SPACE_NORM_PATTERN


def normalize_probe(text: str) -> str:
    return _SPACE_NORM_PATTERN.sub(lambda match: _SPACE_NORM_LOOKUP[match.group()], text)
""",
                encoding="utf-8",
            )

            issues = _check_space_norm_private_usage(app_dir, repo_root=tree_root)
            codes = {issue.code for issue in issues}
            self.assertIn("space_norm_private_import", codes)
            self.assertIn("space_norm_direct_pattern_sub", codes)

    def test_preflight_flags_new_short_keyword_synonym_without_important_short(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            subprocess.run(["git", "init"], cwd=tree_root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=tree_root, check=True, capture_output=True, text=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=DM Test",
                    "-c",
                    "user.email=dm-test@example.invalid",
                    "commit",
                    "-m",
                    "baseline",
                ],
                cwd=tree_root,
                check=True,
                capture_output=True,
                text=True,
            )
            keyword_synonym = (
                app_dir
                / "languages"
                / "sv"
                / "ingredient_matching"
                / "term_registry"
                / "entries"
                / "keyword_synonym.toml"
            )
            keyword_synonym.write_text(
                keyword_synonym.read_text(encoding="utf-8")
                + """

[[entries]]
entry_id = "sv-se.alias.phasefood.phasef"
language = "sv"
market = "SE"
canonical = "phasefood"
status = "active"
variants = ["phasef"]
offer_terms = ["phasefood"]
source_refs = ["manual:phase_short_synonym"]
layer_policy = ["offer_alias"]
notes = "Synthetic short synonym source term."

[[entries.coverage]]
source_family = "keyword_synonym"
canonical = "phasefood"
variant = "phasef"
layer_role = "keyword_synonym_mapping"

[[entries.positive_examples]]
ingredient = "phasefood"
offer_name = "Phasef"
expected = 1
""",
                encoding="utf-8",
            )

            report = run_preflight(tree_root=tree_root)

        short_issues = [
            item
            for item in report["new_issues"]
            if item["code"] == "keyword_synonym_short_variant_missing_important_short"
        ]
        self.assertEqual(len(short_issues), 1)
        self.assertEqual(short_issues[0]["item_id"], "sv-se.alias.phasefood.phasef")
        self.assertEqual(short_issues[0]["details"]["variant"], "phasef")
        self.assertIn("important-short-keyword", short_issues[0]["details"]["fix"])

    def test_preflight_allows_new_short_keyword_synonym_with_important_short(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            subprocess.run(["git", "init"], cwd=tree_root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=tree_root, check=True, capture_output=True, text=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=DM Test",
                    "-c",
                    "user.email=dm-test@example.invalid",
                    "commit",
                    "-m",
                    "baseline",
                ],
                cwd=tree_root,
                check=True,
                capture_output=True,
                text=True,
            )
            matcher_root = app_dir / "languages" / "sv" / "ingredient_matching"
            keyword_synonym = matcher_root / "term_registry" / "entries" / "keyword_synonym.toml"
            keyword_synonym.write_text(
                keyword_synonym.read_text(encoding="utf-8")
                + """

[[entries]]
entry_id = "sv-se.alias.phasefood.phasef"
language = "sv"
market = "SE"
canonical = "phasefood"
status = "active"
variants = ["phasef"]
offer_terms = ["phasefood"]
source_refs = ["manual:phase_short_synonym"]
layer_policy = ["offer_alias"]
notes = "Synthetic short synonym source term."

[[entries.coverage]]
source_family = "keyword_synonym"
canonical = "phasefood"
variant = "phasef"
layer_role = "keyword_synonym_mapping"

[[entries.positive_examples]]
ingredient = "phasefood"
offer_name = "Phasef"
expected = 1
""",
                encoding="utf-8",
            )
            runtime_overlays = matcher_root / "runtime_rule_overlays.toml"
            runtime_overlays.write_text(
                runtime_overlays.read_text(encoding="utf-8")
                + """

[[keyword_set_updates]]
id = "runtime_important_short_keyword_add_phasef"
status = "active"
surface = "important_short_keywords"
action = "add"
terms = ["phasef"]
reason = "Synthetic short synonym source term must survive strict extraction before synonym mapping."
""",
                encoding="utf-8",
            )

            report = run_preflight(tree_root=tree_root)

        self.assertFalse(any(
            item["code"] == "keyword_synonym_short_variant_missing_important_short"
            for item in report["new_issues"]
        ))

    def test_positive_fixture_missing_expected_matches_is_actionable(self) -> None:
        fixtures = load_fixture_contract(DEFAULT_FIXTURE_FILE)
        fixture = next(
            item
            for item in fixtures
            if item["id"] == "matcher_regression_positive_havssalt_250g_maldon"
        )
        broken_fixture = deepcopy(fixture)
        broken_fixture.pop("expected_matches", None)
        fixtures[fixtures.index(fixture)] = broken_fixture

        with tempfile.TemporaryDirectory() as tmp:
            fixture_file = Path(tmp) / "matcher_regression_cases.toml"
            write_fixture_contract(fixtures, fixture_file)
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
            app_dir = _copy_matcher_tree(tree_root)

            fixture_spec = contract_spec_by_name("matcher_regression_cases", tree_root=tree_root)
            fixture_file = fixture_spec.source_toml_path
            fixtures = load_contract_source(fixture_spec)
            fixture = next(
                item
                for item in fixtures
                if item["id"] == "matcher_regression_positive_havssalt_250g_maldon"
            )
            fixture.pop("expected_matches", None)
            write_contract_source(fixture_spec, fixtures)

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
            all(issue["file"].endswith("matcher_regression_cases.toml") for issue in fixture_issues),
            report,
        )

    def test_coverage_generation_allows_fixture_inventory_and_synced_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)

            fixture_file = (
                app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_regression_cases.toml"
            )
            fixture_id = "matcher_regression_positive_phase2_generated_coverage"
            inventory_id = "legacy_synonym_phase2_generated_coverage"

            fixture_spec = contract_spec_by_name("matcher_regression_cases", tree_root=tree_root)
            fixtures = load_contract_source(fixture_spec)
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
            write_contract_source(fixture_spec, fixtures)

            line_count = len(fixture_file.read_text(encoding="utf-8").splitlines())
            inventory_spec = contract_spec_by_name("matcher_rule_inventory", tree_root=tree_root)
            inventory = load_contract_source(inventory_spec)
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
                        "path": "app/languages/sv/matcher_contracts/sources/matcher_regression_cases.toml",
                        "start": 1,
                        "end": line_count,
                        "anchor": fixture_id,
                    }
                ],
                "notes": "Synthetic Phase 2 generated coverage row.",
            })
            write_contract_source(inventory_spec, inventory)

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

    def test_hash_tolerance_ignores_source_ref(self) -> None:
        variant = AuditVariant(
            source_order=20,
            source_type="matcher_regression_case",
            source_file="app/languages/sv/matcher_contracts/sources/matcher_regression_cases.toml",
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

    def test_current_stable_variant_ids_are_unique(self) -> None:
        variants = build_variants(batch_size=60, hash_version=IDENTITY_HASH_VERSION_V2)
        variant_ids = [variant.variant_id for variant in variants]

        self.assertEqual(len(variant_ids), len(set(variant_ids)))

    def test_promote_content_key_tolerates_fixture_canonical_revision_only(self) -> None:
        config = PromotionConfig(
            language="sv",
            market="SE",
            baseline_path=Path("verified_matcher_terms.json"),
            audit_module="support_checks.run_verified_term_audit",
            registry_module="languages.sv.ingredient_matching.term_registry.registry",
        )
        fixture_variant = {
            "language": "sv",
            "market": "SE",
            "source_type": "matcher_regression_case",
            "source_file": "app/languages/sv/matcher_contracts/sources/matcher_regression_cases.toml",
            "source_id": "matcher_regression_positive_phase6_canonical_revision",
            "variant_role": "positive_regression",
            "variant_text": "matcher_regression_positive_phase6_canonical_revision: Phase 6 offer",
            "canonical": "phase6old",
            "expected_family": "phase6old",
            "expected": 1,
        }
        canonical_revision = {**fixture_variant, "canonical": "phase6new", "expected_family": "phase6new"}
        source_rewrite = {**canonical_revision, "source_id": "matcher_regression_positive_phase6_other"}
        registry_variant = {
            **fixture_variant,
            "source_type": "keyword_synonym",
            "source_family": "keyword_synonym",
            "source_id": "sv-se.alias.phase6.phase6alias",
            "variant": "phase6alias",
            "layer_role": "keyword_synonym_mapping",
        }
        registry_canonical_revision = {
            **registry_variant,
            "canonical": "phase6new",
            "expected_family": "phase6new",
        }

        self.assertEqual(_content_key(fixture_variant, config), _content_key(canonical_revision, config))
        self.assertNotEqual(_content_key(fixture_variant, config), _content_key(source_rewrite, config))
        self.assertNotEqual(_content_key(registry_variant, config), _content_key(registry_canonical_revision, config))

    def test_promote_reports_matcher_regression_assertion_flips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline_path = tmp_path / "verified_matcher_terms.json"
            old_variant = {
                "variant_id": "vterm-old-positive",
                "language": "sv",
                "market": "SE",
                "source_type": "matcher_regression_case",
                "source_file": "app/languages/sv/matcher_contracts/sources/matcher_regression_cases.toml",
                "source_id": "matcher_regression_positive_phase6_assertion_flip",
                "variant_role": "positive_regression",
                "variant_text": (
                    "matcher_regression_positive_phase6_assertion_flip: Phase 6 offer"
                ),
                "canonical": "phase6old",
                "expected_family": "phase6old",
                "expected": 1,
            }
            fresh_variant = {
                **old_variant,
                "variant_id": "vterm-new-negative",
                "variant_role": "negative_regression",
                "canonical": None,
                "expected_family": "phase6new_policy",
                "expected": 0,
            }
            baseline_path.write_text(
                json.dumps({"variants": [old_variant], "summary": {}, "verification": {}}, ensure_ascii=False),
                encoding="utf-8",
            )
            config = PromotionConfig(
                language="sv",
                market="SE",
                baseline_path=baseline_path,
                audit_module="support_checks.run_verified_term_audit",
                registry_module="languages.sv.ingredient_matching.term_registry.registry",
            )

            self.assertEqual(
                _matcher_regression_case_identity(old_variant, config),
                _matcher_regression_case_identity(fresh_variant, config),
            )
            stdout = io.StringIO()
            with mock.patch(
                "support_checks.promote_term_baseline._generate_fresh_variants",
                return_value=[fresh_variant],
            ), contextlib.redirect_stdout(stdout):
                result = promote(config=config, dry_run=True)

        output = stdout.getvalue()
        self.assertEqual(result, 1, output)
        self.assertIn("matcher-regression assertion(s) changed since the baseline", output)
        self.assertIn("baseline: expected=1, role=positive_regression, canonical=phase6old", output)
        self.assertIn("current:  vterm-new-negative: expected=0, role=negative_regression", output)
        self.assertIn("--allow-removals", output)

    def test_promote_coverage_key_uses_expected_family_for_negative_fixtures(self) -> None:
        config = PromotionConfig(
            language="sv",
            market="SE",
            baseline_path=Path("verified_matcher_terms.json"),
            audit_module="support_checks.run_verified_term_audit",
            registry_module="languages.sv.ingredient_matching.term_registry.registry",
        )
        variant = {
            "language": "sv",
            "market": "SE",
            "source_type": "matcher_regression_case",
            "source_file": "app/languages/sv/matcher_contracts/sources/matcher_regression_cases.toml",
            "source_id": "matcher_regression_negative_policy_family",
            "variant_role": "negative_regression",
            "variant_text": "matcher_regression_negative_policy_family: Blocked Offer",
            "canonical": "",
            "expected_family": "current_review_matcher_regression",
            "expected": 0,
        }

        self.assertEqual(
            _coverage_key(variant, config),
            (
                "sv",
                "SE",
                "matcher_regression_case",
                "current_review_matcher_regression",
                "matcher_regression_negative_policy_family: Blocked Offer",
                "negative_regression",
            ),
        )

    def test_promote_variant_id_migration_map_preserves_existing_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "verified_term_variant_id_migrations.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "from_hash_version": "v1_source_ref",
                        "to_hash_version": "v2_stable_without_source_ref",
                        "variant_count": 1,
                        "migrations": [
                            {
                                "old_variant_id": "vterm-old-existing",
                                "new_variant_id": "vterm-new-existing",
                                "language": "sv",
                                "market": "SE",
                                "source_family": "keyword_synonym",
                                "canonical": "existing",
                                "variant": "existing",
                                "layer_role": "keyword_synonym_mapping",
                                "source_file": "existing.toml",
                                "source_id": "existing",
                                "source_ref": "manual:existing",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            _write_variant_id_migration_map(
                path=path,
                output_dir=None,
                records=[
                    {
                        "old_variant_id": "vterm-old-new",
                        "new_variant_id": "vterm-new-new",
                        "language": "sv",
                        "market": "SE",
                        "source_family": "matcher_regression_case",
                        "canonical": "new",
                        "variant": "new fixture",
                        "layer_role": "positive_regression",
                        "source_file": "new.json",
                        "source_id": "new",
                        "source_ref": "manual:new",
                    }
                ],
            )

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["variant_count"], 2)
            self.assertEqual(
                {(record["old_variant_id"], record["new_variant_id"]) for record in payload["migrations"]},
                {
                    ("vterm-old-existing", "vterm-new-existing"),
                    ("vterm-old-new", "vterm-new-new"),
                },
            )

    def test_promote_can_refresh_stale_expected_constants_without_variant_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            add_term_checks = tmp_path / "run_term_registry_add_term_checks.py"
            contract_checks = tmp_path / "run_term_registry_contract_checks.py"
            sanity_checks = tmp_path / "run_sanity_checks.py"
            add_term_checks.write_text("EXPECTED_VERIFIED_TERM_UNIQUE_COVERAGE_KEYS = 1\n", encoding="utf-8")
            contract_checks.write_text("EXPECTED_VERIFIED_TERM_VARIANT_COUNT = 2\n", encoding="utf-8")
            sanity_checks.write_text(
                'self.assertEqual(summary.get("unique_coverage_key_count"), 1)\n',
                encoding="utf-8",
            )
            config = PromotionConfig(
                language="sv",
                market="SE",
                baseline_path=tmp_path / "verified_matcher_terms.json",
                audit_module="support_checks.run_verified_term_audit",
                registry_module="languages.sv.ingredient_matching.term_registry.registry",
                add_term_checks_path=add_term_checks,
                contract_checks_path=contract_checks,
                sanity_checks_path=sanity_checks,
            )

            self.assertTrue(
                _expected_count_constants_are_stale(
                    config,
                    variant_count=5,
                    unique_coverage_key_count=8,
                )
            )
            with contextlib.redirect_stdout(io.StringIO()):
                changed = _update_expected_count_constants(
                    config,
                    variant_count=5,
                    unique_coverage_key_count=8,
                    output_dir=None,
                )

            self.assertEqual({source.name for source, _target in changed}, {
                "run_term_registry_add_term_checks.py",
                "run_term_registry_contract_checks.py",
                "run_sanity_checks.py",
            })
            self.assertIn("EXPECTED_VERIFIED_TERM_UNIQUE_COVERAGE_KEYS = 8", add_term_checks.read_text(encoding="utf-8"))
            self.assertIn("EXPECTED_VERIFIED_TERM_VARIANT_COUNT = 5", contract_checks.read_text(encoding="utf-8"))
            self.assertIn(
                'summary.get("unique_coverage_key_count"), 8',
                sanity_checks.read_text(encoding="utf-8"),
            )
            self.assertFalse(
                _expected_count_constants_are_stale(
                    config,
                    variant_count=5,
                    unique_coverage_key_count=8,
                )
            )
            with contextlib.redirect_stdout(io.StringIO()):
                unchanged = _update_expected_count_constants(
                    config,
                    variant_count=5,
                    unique_coverage_key_count=8,
                    output_dir=None,
                )
            self.assertEqual(unchanged, [])

    def test_preflight_flags_match_bridge_positive_fixture_miss(self) -> None:
        fixture_id = "matcher_regression_positive_phase6_bridge_miss"
        fixtures = [
            {
                "id": fixture_id,
                "policy_ref": "phase6_bridge_miss",
                "source_ref": "manual:phase6_bridge_miss",
                "recipe_name": "Synthetic Phase 6",
                "ingredients": ["1 dl phase6 ingredient"],
                "offer": {"name": "Phase6 Bridge Offer", "category": "pantry"},
                "expected": 1,
                "expected_matches": [{"ingredient_index": 0, "canonical": "phase6bridge"}],
            }
        ]
        bridge = MatchBridge(
            id="phase6_bridge_miss",
            rule_schema_version=1,
            rule_version=1,
            canonical="phase6bridge",
            ingredient_patterns=(r"\bdoesnotmatchphase6\b",),
            offer_patterns=(r"\bphase6 bridge offer\b",),
            fixture_refs=frozenset({fixture_id}),
        )

        with tempfile.TemporaryDirectory() as tmp:
            fixture_file = Path(tmp) / "matcher_regression_cases.toml"
            write_fixture_contract(fixtures, fixture_file)
            original_bridges = guard_bridge_checks.MATCH_BRIDGES
            guard_bridge_checks.MATCH_BRIDGES = (bridge,)
            try:
                issues = _check_match_bridge_positive_fixture_hits(
                    fixture_file,
                    fixtures,
                    repo_root=Path(tmp),
                )
            finally:
                guard_bridge_checks.MATCH_BRIDGES = original_bridges

        self.assertEqual([issue.code for issue in issues], ["match_bridge_positive_fixture_miss"])
        self.assertEqual(issues[0].line, 8)
        self.assertEqual(issues[0].details["bridge_id"], "phase6_bridge_miss")
        self.assertEqual(issues[0].details["fixture_ref"], fixture_id)

    def test_cli_e2e(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)

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
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

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
            fixture_source_file = (
                app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_regression_cases.toml"
            )
            inventory_source_file = (
                app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_rule_inventory.toml"
            )

            fixtures = load_contract_source(contract_spec_by_name("matcher_regression_cases", tree_root=tree_root))
            inventory = load_contract_source(contract_spec_by_name("matcher_rule_inventory", tree_root=tree_root))
            self.assertTrue(any(item["id"] == fixture_id for item in fixtures))
            self.assertTrue(any(item["id"] == inventory_id for item in inventory))
            self.assertIn("phasefyraapelsin", keyword_extra_parent_file.read_text(encoding="utf-8"))
            self.assertIn(policy_ref, deep_sanity_file.read_text(encoding="utf-8"))
            self.assertIn(fixture_id, fixture_source_file.read_text(encoding="utf-8"))
            self.assertIn(inventory_id, inventory_source_file.read_text(encoding="utf-8"))

            write_coverage_files(generate_coverage_files(tree_root=tree_root))
            self.assertFalse(any(item.changed for item in generate_coverage_files(tree_root=tree_root)))
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
                    "--baseline-output-dir",
                    str(tree_root / "promotion-output"),
                    "--dry-run",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(gate_result.returncode, 0, gate_result.stderr + gate_result.stdout)
            self.assertIn("generate_matcher_registry_coverage.py", gate_result.stdout)

    def test_cli_fixture_remove_cascades_fixture_refs_and_regen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            fixture_id = "matcher_regression_riven_cheddarost_spread_negative"
            live_app_dir = Path(__file__).resolve().parents[2]

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "fixture",
                    "remove",
                    fixture_id,
                    "--tree-root",
                    str(tree_root),
                    "--drop-empty-inventory",
                    "--drop-empty-registry-entries",
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            fixture_source = (
                app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_regression_cases.toml"
            ).read_text(encoding="utf-8")
            inventory_source = (
                app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_rule_inventory.toml"
            ).read_text(encoding="utf-8")
            no_match_policy = (
                app_dir
                / "languages"
                / "sv"
                / "ingredient_matching"
                / "term_registry"
                / "entries"
                / "no_match_policy.toml"
            ).read_text(encoding="utf-8")
            generated_fixture_coverage = (
                app_dir
                / "languages"
                / "sv"
                / "ingredient_matching"
                / "term_registry"
                / "entries"
                / "matcher_regression_case.toml"
            ).read_text(encoding="utf-8")

            self.assertNotIn(fixture_id, fixture_source)
            self.assertNotIn(fixture_id, inventory_source)
            self.assertNotIn(fixture_id, no_match_policy)
            self.assertNotIn(fixture_id, generated_fixture_coverage)

    def test_cli_modify_keyword_extra_parent_remove_kid_cascades_and_reanchors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]
            policy_ref = "keyword_extra_parent_phaseparentdrink_family"
            inventory_id = "legacy_parent_phaseparentdrink_family"
            almond_fixture_id = "keyword_extra_parent_phaseparentdrink_phasealmonddrink_positive"
            hazel_fixture_id = "keyword_extra_parent_phaseparentdrink_phasehazeldrink_positive"
            oat_fixture_id = "keyword_extra_parent_phaseparentdrink_phaseoatdrink_positive"

            add_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "keyword-extra-parent",
                    "phaseparentdrink",
                    "--kids",
                    "phasealmonddrink,phasehazeldrink,phaseoatdrink",
                    "--recipe-name",
                    "Synthetic Parent Drink",
                    "--ingredient",
                    "2 dl phaseparentdrink",
                    "--offer-names",
                    "Phase Almond Drink,Phase Hazel Drink,Phase Oat Drink",
                    "--offer-category",
                    "pantry",
                    "--policy-ref",
                    policy_ref,
                    "--inventory-id",
                    inventory_id,
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(add_result.returncode, 0, add_result.stderr + add_result.stdout)

            modify_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "modify",
                    "keyword-extra-parent",
                    "phaseparentdrink",
                    "--remove-kids",
                    "phasealmonddrink,phasehazeldrink",
                    "--reason",
                    "Synthetic child no longer belongs in this family.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(modify_result.returncode, 0, modify_result.stderr + modify_result.stdout)

            keyword_extra_parent_text = (
                app_dir
                / "languages"
                / "sv"
                / "ingredient_matching"
                / "term_registry"
                / "entries"
                / "keyword_extra_parent.toml"
            ).read_text(encoding="utf-8")
            self.assertNotIn("phasealmonddrink", keyword_extra_parent_text)
            self.assertNotIn("phasehazeldrink", keyword_extra_parent_text)
            self.assertIn("phaseoatdrink", keyword_extra_parent_text)
            oat_entry_match = re.search(
                r'entry_id = "(sv-se\.family\.phaseparentdrink\.phaseoatdrink_\d+)"',
                keyword_extra_parent_text,
            )
            self.assertIsNotNone(oat_entry_match)
            oat_entry_id = oat_entry_match.group(1)

            fixture_source = (
                app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_regression_cases.toml"
            ).read_text(encoding="utf-8")
            self.assertNotIn(almond_fixture_id, fixture_source)
            self.assertNotIn(hazel_fixture_id, fixture_source)
            self.assertIn(oat_fixture_id, fixture_source)

            inventory_source = (
                app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_rule_inventory.toml"
            ).read_text(encoding="utf-8")
            self.assertNotIn(almond_fixture_id, inventory_source)
            self.assertNotIn(hazel_fixture_id, inventory_source)
            self.assertIn(oat_fixture_id, inventory_source)
            self.assertIn(f'anchor = "entry_id = \\"{oat_entry_id}\\""', inventory_source)
            self.assertIn("Synthetic child no longer belongs in this family.", inventory_source)

            deep_sanity_text = (app_dir / "support_checks" / "run_deep_matcher_sanity.py").read_text(encoding="utf-8")
            self.assertNotIn("Phaseparentdrink recipe matches phasealmonddrink", deep_sanity_text)
            self.assertNotIn("Phaseparentdrink recipe matches phasehazeldrink", deep_sanity_text)
            self.assertIn("Phaseparentdrink recipe matches phaseoatdrink", deep_sanity_text)
            self.assertIn("Phasealmonddrink no longer matches phaseparentdrink parent", deep_sanity_text)
            self.assertIn("Phasehazeldrink no longer matches phaseparentdrink parent", deep_sanity_text)

    def test_cli_modify_no_match_policy_rewrites_synced_guard_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]
            no_match_policy_file = (
                app_dir
                / "languages"
                / "sv"
                / "ingredient_matching"
                / "term_registry"
                / "entries"
                / "no_match_policy.toml"
            )
            original_rule_version = None
            blocks = re.split(r"(?m)^(?=\[\[entries\]\]\s*$)", no_match_policy_file.read_text(encoding="utf-8"))
            for block in blocks:
                if 'id = "policy_generic_oil"' not in block:
                    continue
                payload = tomllib.loads(block)
                original_rule_version = payload["entries"][0]["language_payload"]["no_match_policy"]["rule_version"]
                break
            self.assertIsNotNone(original_rule_version)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "modify",
                    "no-match-policy",
                    "policy_generic_oil",
                    "--set-ingredient-patterns",
                    r"\bolja\b",
                    "--set-blocked-offer-keywords",
                    "",
                    "--set-blocked-offer-patterns",
                    r"\brapsolja\b",
                    "--no-run-gates",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            blocks = re.split(r"(?m)^(?=\[\[entries\]\]\s*$)", no_match_policy_file.read_text(encoding="utf-8"))
            policy_entry = None
            for block in blocks:
                if 'id = "policy_generic_oil"' not in block:
                    continue
                payload = tomllib.loads(block)
                policy_entry = payload["entries"][0]
                break

            self.assertIsNotNone(policy_entry)
            assert policy_entry is not None
            payload = policy_entry["language_payload"]["no_match_policy"]
            self.assertEqual(policy_entry["variants"], [r"generic_oil_no_match ! \brapsolja\b"])
            self.assertEqual(policy_entry["negative_guards"], [r"generic_oil_no_match ! \brapsolja\b"])
            self.assertEqual(payload["ingredient_patterns"], [r"\bolja\b"])
            self.assertEqual(payload["blocked_offer_keywords"], [])
            self.assertEqual(payload["blocked_offer_patterns"], [r"\brapsolja\b"])
            self.assertEqual(payload["rule_version"], original_rule_version + 1)
            self.assertEqual(policy_entry["coverage"][0]["variant"], r"generic_oil_no_match ! \brapsolja\b")
            self.assertEqual(policy_entry["negative_examples"][0]["offer_name"], r"generic_oil_no_match ! \brapsolja\b")

    def test_cli_modify_match_bridge_rewrites_synced_offer_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "modify",
                    "match-bridge",
                    "bridge_alger_nori",
                    "--remove-offer-patterns",
                    r"\bseeweed\b",
                    "--no-run-gates",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            match_bridge_file = (
                app_dir
                / "languages"
                / "sv"
                / "ingredient_matching"
                / "term_registry"
                / "entries"
                / "match_bridge.toml"
            )
            blocks = re.split(r"(?m)^(?=\[\[entries\]\]\s*$)", match_bridge_file.read_text(encoding="utf-8"))
            bridge_entry = None
            for block in blocks:
                if 'id = "bridge_alger_nori"' not in block:
                    continue
                payload = tomllib.loads(block)
                bridge_entry = payload["entries"][0]
                break

            self.assertIsNotNone(bridge_entry)
            assert bridge_entry is not None
            payload = bridge_entry["language_payload"]["match_bridge"]
            self.assertEqual(payload["rule_version"], 2)
            self.assertEqual(payload["offer_patterns"], [r"\bnori\b", r"\bseaweed\b"])
            self.assertNotIn(r"\bseeweed\b", bridge_entry["offer_terms"])
            self.assertNotIn(r"\balger\b -> \bseeweed\b", bridge_entry["variants"])
            self.assertTrue(
                all(row["variant"] != r"\balger\b -> \bseeweed\b" for row in bridge_entry["coverage"])
            )

    def test_cli_promote_apply_staged_manifest_copies_changed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = tree_root / "app"
            app_dir.mkdir(parents=True)
            target = app_dir / "languages" / "sv" / "ingredient_matching" / "term_registry" / "baselines"
            target.mkdir(parents=True)
            target_file = target / "verified_matcher_terms.json"
            target_file.write_text('{"old": true}\n', encoding="utf-8")

            output_dir = tree_root / "promotion-output"
            staged_file = output_dir / "languages" / "sv" / "ingredient_matching" / "term_registry" / "baselines" / "verified_matcher_terms.json"
            staged_file.parent.mkdir(parents=True)
            staged_file.write_text('{"new": true}\n', encoding="utf-8")
            (output_dir / "promotion_manifest.json").write_text(
                json.dumps({
                    "changed_files": [
                        {
                            "source_path": "languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json",
                            "staged_path": str(staged_file),
                        }
                    ]
                }),
                encoding="utf-8",
            )

            paths = dm_cli.MatcherPaths(
                tree_root=tree_root,
                app_dir=app_dir,
                repo_root=tree_root,
                fixture_file=app_dir / "matcher_regression_cases.toml",
                inventory_file=app_dir / "matcher_rule_inventory.toml",
                fixture_source_file=app_dir / "fixture.toml",
                inventory_source_file=app_dir / "inventory.toml",
                registry_entries_dir=app_dir / "entries",
                keyword_extra_parent_file=app_dir / "keyword_extra_parent.toml",
                keyword_synonym_file=app_dir / "keyword_synonym.toml",
                runtime_overlay_file=app_dir / "runtime_rule_overlays.toml",
                deep_sanity_file=app_dir / "run_deep_matcher_sanity.py",
            )

            dm_cli._apply_promote_staged_output(paths=paths, output_dir=output_dir, dry_run=False)
            self.assertEqual(target_file.read_text(encoding="utf-8"), '{"new": true}\n')

    def test_cli_add_smart_blocker_scaffolds_function_and_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "smart-blocker",
                    "phase4 sample blocker",
                    "--description",
                    "Synthetic smart-blocker scaffold for CLI coverage.",
                    "--no-run-gates",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            matching_py = (
                app_dir / "languages" / "sv" / "ingredient_matching" / "matching.py"
            ).read_text(encoding="utf-8")
            self.assertIn("def _phase4_sample_blocker_requirement_allows_product(", matching_py)
            self.assertIn(
                "and _phase4_sample_blocker_requirement_allows_product(product_lower, ingredient_lower, matched_keyword)",
                matching_py,
            )
            self.assertIn("return True", matching_py)

    def test_cli_dry_run_canary_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            fixture_file = (
                app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_regression_cases.toml"
            )
            inventory_file = (
                app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_rule_inventory.toml"
            )
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
            fixture_source_file = (
                app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_regression_cases.toml"
            )
            inventory_source_file = (
                app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_rule_inventory.toml"
            )
            watched_files = (
                fixture_file,
                inventory_file,
                keyword_extra_parent_file,
                deep_sanity_file,
                fixture_source_file,
                inventory_source_file,
            )
            before = {path: path.read_text(encoding="utf-8") for path in watched_files}

            policy_ref = "keyword_extra_parent_citrusfrukter_dry_run_canary"
            inventory_id = "legacy_parent_citrusfrukter_dry_run_canary"
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
                    "dryrunklementin",
                    "--recipe-name",
                    "Synthetic Dry Run",
                    "--ingredient",
                    "3-4 citrusfrukter (valfri sort)",
                    "--offer-names",
                    "Dryrunklementin",
                    "--offer-category",
                    "fruit",
                    "--policy-ref",
                    policy_ref,
                    "--inventory-id",
                    inventory_id,
                    "--tree-root",
                    str(tree_root),
                    "--dry-run",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            after = {path: path.read_text(encoding="utf-8") for path in watched_files}
            self.assertEqual(after, before)
            self.assertIn('canonical = "citrusfrukter"', result.stdout)
            self.assertIn('variants = ["dryrunklementin"]', result.stdout)
            self.assertIn(f"# {policy_ref}: generated by dm matcher add keyword-extra-parent", result.stdout)
            self.assertIn("Dry run only; no files written.", result.stdout)

    def test_keyword_synonym_cli_dry_run_canary_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            keyword_synonym_file = (
                app_dir
                / "languages"
                / "sv"
                / "ingredient_matching"
                / "term_registry"
                / "entries"
                / "keyword_synonym.toml"
            )
            deep_sanity_file = app_dir / "support_checks" / "run_deep_matcher_sanity.py"
            before = {
                keyword_synonym_file: keyword_synonym_file.read_text(encoding="utf-8"),
                deep_sanity_file: deep_sanity_file.read_text(encoding="utf-8"),
            }

            policy_ref = "keyword_synonym_phasealias_dryrunalias"
            live_app_dir = Path(__file__).resolve().parents[2]
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "keyword-synonym",
                    "phasealias",
                    "--variants",
                    "dryrunalias",
                    "--sanity-offer",
                    "Phasealias",
                    "--policy-ref",
                    policy_ref,
                    "--tree-root",
                    str(tree_root),
                    "--dry-run",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            after = {
                keyword_synonym_file: keyword_synonym_file.read_text(encoding="utf-8"),
                deep_sanity_file: deep_sanity_file.read_text(encoding="utf-8"),
            }
            self.assertEqual(after, before)
            self.assertIn('canonical = "phasealias"', result.stdout)
            self.assertIn('variants = ["dryrunalias"]', result.stdout)
            self.assertNotIn("offer_category =", result.stdout)
            self.assertIn('match("Phasealias", "dryrunalias", "")', result.stdout)
            self.assertNotIn("[[entries.coverage]]", result.stdout)
            self.assertIn(f"# {policy_ref}: generated by dm matcher add keyword-synonym", result.stdout)
            self.assertIn("Dry run only; no files written.", result.stdout)

    def test_generated_registry_entry_remove_undo_deletes_entry_and_canary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            keyword_synonym_file = (
                app_dir
                / "languages"
                / "sv"
                / "ingredient_matching"
                / "term_registry"
                / "entries"
                / "keyword_synonym.toml"
            )
            deep_sanity_file = app_dir / "support_checks" / "run_deep_matcher_sanity.py"
            live_app_dir = Path(__file__).resolve().parents[2]

            add = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "keyword-synonym",
                    "phaseundo",
                    "--variants",
                    "undoalias",
                    "--sanity-offer",
                    "Phaseundo",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(add.returncode, 0, add.stderr + add.stdout)
            entry_match = re.search(r"entry:\s+(\S+)", add.stdout)
            self.assertIsNotNone(entry_match, add.stdout)
            entry_id = entry_match.group(1)
            policy_ref = "keyword_synonym_phaseundo_undoalias"
            self.assertIn(entry_id, keyword_synonym_file.read_text(encoding="utf-8"))
            self.assertIn(policy_ref, deep_sanity_file.read_text(encoding="utf-8"))

            remove = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "remove",
                    entry_id,
                    "--reason",
                    "Synthetic undo of a just-added registry rule.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(remove.returncode, 0, remove.stderr + remove.stdout)
            self.assertIn("Removed generated registry entry", remove.stdout)
            self.assertNotIn(entry_id, keyword_synonym_file.read_text(encoding="utf-8"))
            sanity_text = deep_sanity_file.read_text(encoding="utf-8")
            self.assertNotIn(policy_ref, sanity_text)
            self.assertNotIn("Keyword synonym undoalias matches phaseundo", sanity_text)

    def test_keyword_synonym_rejects_spaced_variants_but_accepts_single_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            keyword_synonym_file = (
                app_dir
                / "languages"
                / "sv"
                / "ingredient_matching"
                / "term_registry"
                / "entries"
                / "keyword_synonym.toml"
            )
            deep_sanity_file = app_dir / "support_checks" / "run_deep_matcher_sanity.py"
            before = {
                keyword_synonym_file: keyword_synonym_file.read_text(encoding="utf-8"),
                deep_sanity_file: deep_sanity_file.read_text(encoding="utf-8"),
            }
            live_app_dir = Path(__file__).resolve().parents[2]

            spaced = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "keyword-synonym",
                    "pakchoi",
                    "--variants",
                    "pak choy",
                    "--sanity-offer",
                    "Pak Choi 250g klass 1 ICA",
                    "--tree-root",
                    str(tree_root),
                    "--dry-run",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(spaced.returncode, 2, spaced.stderr + spaced.stdout)
            self.assertIn("must be single extracted keyword", spaced.stderr + spaced.stdout)
            self.assertIn("space-normalization", spaced.stderr + spaced.stdout)
            self.assertIn("hardcoded", spaced.stderr + spaced.stdout)
            self.assertIn("extraction helper first", spaced.stderr + spaced.stdout)

            single_token = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "keyword-synonym",
                    "phasealias",
                    "--variants",
                    "phasealiasvariant",
                    "--sanity-offer",
                    "Phasealias",
                    "--tree-root",
                    str(tree_root),
                    "--dry-run",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(single_token.returncode, 0, single_token.stderr + single_token.stdout)
            self.assertNotIn("space-normalizes", single_token.stderr)
            after = {
                keyword_synonym_file: keyword_synonym_file.read_text(encoding="utf-8"),
                deep_sanity_file: deep_sanity_file.read_text(encoding="utf-8"),
            }
            self.assertEqual(after, before)

    def test_keyword_synonym_cli_tree_root_and_duplicate_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            keyword_synonym_file = (
                app_dir
                / "languages"
                / "sv"
                / "ingredient_matching"
                / "term_registry"
                / "entries"
                / "keyword_synonym.toml"
            )
            fixture_source_file = (
                app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_regression_cases.toml"
            )
            inventory_source_file = (
                app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_rule_inventory.toml"
            )
            before_fixture_source = fixture_source_file.read_text(encoding="utf-8")
            before_inventory_source = inventory_source_file.read_text(encoding="utf-8")

            live_app_dir = Path(__file__).resolve().parents[2]
            command = [
                sys.executable,
                "-m",
                "cli.dm",
                "matcher",
                "add",
                "keyword-synonym",
                "phasealias",
                "--variants",
                "phasewritealias",
                "--sanity-offer",
                "Phasealias",
                "--offer-category",
                "pantry",
                "--policy-ref",
                "keyword_synonym_phasealias_phasewritealias",
                "--tree-root",
                str(tree_root),
                "--no-run-gates",
            ]
            result = subprocess.run(
                command,
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            keyword_synonym_text = keyword_synonym_file.read_text(encoding="utf-8")
            appended_block = keyword_synonym_text[
                keyword_synonym_text.rfind('entry_id = "sv-se.alias.phasealias.phasewritealias_') :
            ]
            self.assertIn('variants = ["phasewritealias"]', appended_block)
            self.assertNotIn("[[entries.coverage]]", appended_block)
            self.assertIn(
                "# keyword_synonym_phasealias_phasewritealias: generated by dm matcher add keyword-synonym",
                (app_dir / "support_checks" / "run_deep_matcher_sanity.py").read_text(encoding="utf-8"),
            )
            self.assertEqual(fixture_source_file.read_text(encoding="utf-8"), before_fixture_source)
            self.assertEqual(inventory_source_file.read_text(encoding="utf-8"), before_inventory_source)

            duplicate = subprocess.run(
                command,
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(duplicate.returncode, 0, duplicate.stderr + duplicate.stdout)
            duplicate_output = duplicate.stderr + duplicate.stdout
            self.assertIn("keyword_synonym mapping already exists", duplicate_output)
            self.assertIn("phasewritealias ->", duplicate_output)
            self.assertIn("phasealias", duplicate_output)

    def test_runtime_overlay_add_commands_write_expected_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            overlay_file = app_dir / "languages" / "sv" / "ingredient_matching" / "runtime_rule_overlays.toml"
            deep_sanity_file = app_dir / "support_checks" / "run_deep_matcher_sanity.py"
            before = {
                overlay_file: overlay_file.read_text(encoding="utf-8"),
                deep_sanity_file: deep_sanity_file.read_text(encoding="utf-8"),
            }
            live_app_dir = Path(__file__).resolve().parents[2]

            dry_run = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "pnb",
                    "phasedrypnb",
                    "--blockers",
                    "phasedryblocker",
                    "--reason",
                    "Synthetic dry-run runtime overlay.",
                    "--tree-root",
                    str(tree_root),
                    "--dry-run",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(dry_run.returncode, 0, dry_run.stderr + dry_run.stdout)
            self.assertIn("[[product_name_blockers]]", dry_run.stdout)
            self.assertEqual(overlay_file.read_text(encoding="utf-8"), before[overlay_file])
            self.assertEqual(deep_sanity_file.read_text(encoding="utf-8"), before[deep_sanity_file])

            commands = [
                [
                    "pnb",
                    "phasepnb",
                    "--blockers",
                    "phaseproductblocker",
                    "--reason",
                    "Synthetic product blocker.",
                    "--policy-ref",
                    "runtime_pnb_phasepnb_phaseproductblocker",
                ],
                [
                    "fpb",
                    "phasefpb",
                    "--blockers",
                    "phaseingredientblocker",
                    "--reason",
                    "Synthetic ingredient blocker.",
                    "--policy-ref",
                    "runtime_fpb_phasefpb_phaseingredientblocker",
                ],
                [
                    "ksbc",
                    "phaseksbc",
                    "--context",
                    "phasecontext",
                    "--reason",
                    "Synthetic context suppressor.",
                    "--policy-ref",
                    "runtime_ksbc_phaseksbc_phasecontext",
                ],
            ]
            for command in commands:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "cli.dm",
                        "matcher",
                        "add",
                        *command,
                        "--tree-root",
                        str(tree_root),
                        "--no-run-gates",
                    ],
                    cwd=live_app_dir,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            merge = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "pnb",
                    "phasepnb",
                    "--blockers",
                    "phaseproductblocker2",
                    "--reason",
                    "Synthetic second product blocker.",
                    "--policy-ref",
                    "runtime_pnb_phasepnb_phaseproductblocker2",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(merge.returncode, 0, merge.stderr + merge.stdout)

            runtime = _runtime_overlay_probe(
                app_dir,
                """
{
    "pnb": sorted(PRODUCT_NAME_BLOCKERS.get("phasepnb", [])),
    "fpb": sorted(FALSE_POSITIVE_BLOCKERS.get("phasefpb", [])),
    "ksbc": sorted(KEYWORD_SUPPRESSED_BY_CONTEXT.get("phaseksbc", [])),
}
""",
            )
            self.assertEqual(runtime["pnb"], ["phaseproductblocker", "phaseproductblocker2"])
            self.assertEqual(runtime["fpb"], ["phaseingredientblocker"])
            self.assertEqual(runtime["ksbc"], ["phasecontext"])

            overlay_text = overlay_file.read_text(encoding="utf-8")
            self.assertEqual(overlay_text.count('keyword = "phasepnb"'), 1)
            self.assertIn('id = "runtime_pnb_phasepnb"', overlay_text)
            self.assertIn('status = "active"', overlay_text)
            self.assertIn('blockers = ["phaseproductblocker", "phaseproductblocker2"]', overlay_text)

            sanity_text = deep_sanity_file.read_text(encoding="utf-8")
            self.assertIn("# runtime_pnb_phasepnb_phaseproductblocker: generated by dm matcher add pnb", sanity_text)
            self.assertIn("# runtime_pnb_phasepnb_phaseproductblocker2: generated by dm matcher add pnb", sanity_text)
            self.assertIn("# runtime_fpb_phasefpb_phaseingredientblocker: generated by dm matcher add fpb", sanity_text)
            self.assertIn("# runtime_ksbc_phaseksbc_phasecontext: generated by dm matcher add ksbc", sanity_text)

            duplicate = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "pnb",
                    "phasepnb",
                    "--blockers",
                    "phaseproductblocker",
                    "--reason",
                    "Synthetic duplicate.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(duplicate.returncode, 0, duplicate.stderr + duplicate.stdout)
            self.assertIn("pnb already contains phaseproductblocker", duplicate.stderr + duplicate.stdout)

            listed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "list",
                    "pnb",
                    "--term",
                    "phasepnb",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr + listed.stdout)
            self.assertIn("runtime_pnb_phasepnb", listed.stdout)

            inactivate = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "inactivate",
                    "pnb",
                    "runtime_pnb_phasepnb",
                    "--reason",
                    "Synthetic inactivation.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(inactivate.returncode, 0, inactivate.stderr + inactivate.stdout)
            after_inactivate = _runtime_overlay_probe(
                app_dir,
                """
{
    "pnb": sorted(PRODUCT_NAME_BLOCKERS.get("phasepnb", [])),
}
""",
            )
            self.assertEqual(after_inactivate["pnb"], [])
            overlay_text = overlay_file.read_text(encoding="utf-8")
            self.assertIn('status = "inactive"', overlay_text)
            self.assertIn('inactive_reason = "Synthetic inactivation."', overlay_text)

    def test_runtime_overlay_modify_and_remove_keep_membership_canaries_in_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            overlay_file = app_dir / "languages" / "sv" / "ingredient_matching" / "runtime_rule_overlays.toml"
            deep_sanity_file = app_dir / "support_checks" / "run_deep_matcher_sanity.py"
            live_app_dir = Path(__file__).resolve().parents[2]

            add = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "pnb",
                    "phaseedit",
                    "--blockers",
                    "phaseold,phasekeep",
                    "--reason",
                    "Synthetic editable overlay.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(add.returncode, 0, add.stderr + add.stdout)
            self.assertIn('"phaseold" in PRODUCT_NAME_BLOCKERS.get("phaseedit", set())', deep_sanity_file.read_text(
                encoding="utf-8"
            ))

            modify = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "modify",
                    "runtime-overlay",
                    "runtime_pnb_phaseedit",
                    "--remove-blocker",
                    "phaseold",
                    "--add-blocker",
                    "phasenew",
                    "--reason",
                    "Synthetic correction.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(modify.returncode, 0, modify.stderr + modify.stdout)
            runtime = _runtime_overlay_probe(
                app_dir,
                """
{
    "pnb": sorted(PRODUCT_NAME_BLOCKERS.get("phaseedit", [])),
}
""",
            )
            self.assertEqual(runtime["pnb"], ["phasekeep", "phasenew"])
            overlay_text = overlay_file.read_text(encoding="utf-8")
            self.assertIn('id = "runtime_pnb_phaseedit"', overlay_text)
            self.assertIn('blockers = ["phasekeep", "phasenew"]', overlay_text)
            sanity_text = deep_sanity_file.read_text(encoding="utf-8")
            self.assertNotIn('"phaseold" in PRODUCT_NAME_BLOCKERS.get("phaseedit", set())', sanity_text)
            self.assertIn("# runtime_pnb_phaseedit: generated by dm matcher add pnb", sanity_text)
            self.assertIn('"phasekeep" in PRODUCT_NAME_BLOCKERS.get("phaseedit", set())', sanity_text)
            self.assertIn('"phasenew" in PRODUCT_NAME_BLOCKERS.get("phaseedit", set())', sanity_text)

            empty_modify = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "modify",
                    "runtime-overlay",
                    "runtime_pnb_phaseedit",
                    "--remove-blocker",
                    "phasekeep,phasenew",
                    "--reason",
                    "Synthetic empty correction.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(empty_modify.returncode, 0)
            self.assertIn("modify would empty runtime_pnb_phaseedit", empty_modify.stderr + empty_modify.stdout)

            no_reason_remove = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "remove",
                    "runtime_pnb_phaseedit",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(no_reason_remove.returncode, 0)
            self.assertIn("--reason", no_reason_remove.stderr + no_reason_remove.stdout)

            remove = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "remove",
                    "runtime_pnb_phaseedit",
                    "--reason",
                    "Synthetic policy removal.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(remove.returncode, 0, remove.stderr + remove.stdout)
            after_remove = _runtime_overlay_probe(
                app_dir,
                """
{
    "pnb": sorted(PRODUCT_NAME_BLOCKERS.get("phaseedit", [])),
}
""",
            )
            self.assertEqual(after_remove["pnb"], [])
            overlay_text = overlay_file.read_text(encoding="utf-8")
            self.assertIn('status = "inactive"', overlay_text)
            self.assertIn('inactive_reason = "Synthetic policy removal."', overlay_text)
            sanity_text = deep_sanity_file.read_text(encoding="utf-8")
            self.assertNotIn('PRODUCT_NAME_BLOCKERS.get("phaseedit", set())', sanity_text)

    def test_runtime_overlay_surface_modify_aliases_accept_keyword_selectors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]

            add = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "ksbc",
                    "phaseksbcedit",
                    "--context",
                    "phaseoldcontext,phasekeepcontext",
                    "--reason",
                    "Synthetic editable KSBC overlay.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(add.returncode, 0, add.stderr + add.stdout)

            modify = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "modify",
                    "ksbc",
                    "phaseksbcedit",
                    "--remove-context",
                    "phaseoldcontext",
                    "--add-context",
                    "phasenewcontext",
                    "--reason",
                    "Synthetic KSBC correction.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(modify.returncode, 0, modify.stderr + modify.stdout)
            runtime = _runtime_overlay_probe(
                app_dir,
                """
{
    "ksbc": sorted(KEYWORD_SUPPRESSED_BY_CONTEXT.get("phaseksbcedit", [])),
}
""",
            )
            self.assertEqual(runtime["ksbc"], ["phasekeepcontext", "phasenewcontext"])
            overlay_text = (
                app_dir / "languages" / "sv" / "ingredient_matching" / "runtime_rule_overlays.toml"
            ).read_text(encoding="utf-8")
            self.assertIn('id = "runtime_ksbc_phaseksbcedit"', overlay_text)
            self.assertIn('context = ["phasekeepcontext", "phasenewcontext"]', overlay_text)
            sanity_text = (app_dir / "support_checks" / "run_deep_matcher_sanity.py").read_text(encoding="utf-8")
            self.assertNotIn(
                '"phaseoldcontext" in KEYWORD_SUPPRESSED_BY_CONTEXT.get("phaseksbcedit", set())',
                sanity_text,
            )
            self.assertIn(
                '"phasenewcontext" in KEYWORD_SUPPRESSED_BY_CONTEXT.get("phaseksbcedit", set())',
                sanity_text,
            )

    def test_gpb_cli_writes_runtime_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            overlay_file = app_dir / "languages" / "sv" / "ingredient_matching" / "runtime_rule_overlays.toml"
            deep_sanity_file = app_dir / "support_checks" / "run_deep_matcher_sanity.py"
            live_app_dir = Path(__file__).resolve().parents[2]

            broad = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "gpb",
                    "--terms",
                    "abc",
                    "--reason",
                    "Synthetic broad blocker.",
                    "--tree-root",
                    str(tree_root),
                    "--dry-run",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(broad.returncode, 0, broad.stderr + broad.stdout)
            self.assertIn("--allow-broad", broad.stderr + broad.stdout)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "gpb",
                    "--terms",
                    "phasepetbrand",
                    "--reason",
                    "Synthetic pet products are globally out of scope.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            overlay_text = overlay_file.read_text(encoding="utf-8")
            self.assertIn("[[global_product_name_blockers]]", overlay_text)
            self.assertIn('id = "runtime_gpb_phasepetbrand"', overlay_text)
            self.assertIn('terms = ["phasepetbrand"]', overlay_text)
            runtime = _runtime_overlay_probe(
                app_dir,
                """
{
    "gpb": sorted(GLOBAL_PRODUCT_NAME_BLOCKERS & {"phasepetbrand"}),
}
""",
            )
            self.assertEqual(runtime["gpb"], ["phasepetbrand"])

            sanity_text = deep_sanity_file.read_text(encoding="utf-8")
            self.assertIn("# runtime_gpb_phasepetbrand: generated by dm matcher add gpb", sanity_text)
            self.assertIn("gpb blocks backend match phasepetbrand", sanity_text)

            listed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "list",
                    "gpb",
                    "--term",
                    "phasepetbrand",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr + listed.stdout)
            self.assertIn("runtime_gpb_phasepetbrand", listed.stdout)

            inactivate = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "inactivate",
                    "gpb",
                    "phasepetbrand",
                    "--reason",
                    "Synthetic GPB inactivation.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(inactivate.returncode, 0, inactivate.stderr + inactivate.stdout)
            after_inactivate = _runtime_overlay_probe(
                app_dir,
                """
{
    "gpb": sorted(GLOBAL_PRODUCT_NAME_BLOCKERS & {"phasepetbrand"}),
}
""",
            )
            self.assertEqual(after_inactivate["gpb"], [])

    def test_space_normalization_cli_writes_runtime_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            overlay_file = app_dir / "languages" / "sv" / "ingredient_matching" / "runtime_rule_overlays.toml"
            live_app_dir = Path(__file__).resolve().parents[2]

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "space-normalization",
                    "phase space",
                    "--target",
                    "phasespace",
                    "--reason",
                    "Synthetic space normalization.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            overlay_text = overlay_file.read_text(encoding="utf-8")
            self.assertIn("[[space_normalizations]]", overlay_text)
            self.assertIn('id = "runtime_space_normalization_phase_space_phasespace"', overlay_text)
            self.assertIn('source = "phase space"', overlay_text)
            self.assertIn('target = "phasespace"', overlay_text)
            runtime = _runtime_overlay_probe(
                app_dir,
                """
{
    "normalized": _apply_space_normalizations("phase space"),
}
""",
            )
            self.assertEqual(runtime["normalized"], "phasespace")

            collision_source_one = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "space-normalization",
                    "phase14-dash term",
                    "--target",
                    "phase14dashterm",
                    "--reason",
                    "Synthetic punctuation collision setup.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                    "--no-sanity",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                collision_source_one.returncode,
                0,
                collision_source_one.stderr + collision_source_one.stdout,
            )

            collision_source_two = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "space-normalization",
                    "phase14 dash-term",
                    "--target",
                    "phase14dashterm",
                    "--reason",
                    "Synthetic punctuation collision variant.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                    "--no-sanity",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                collision_source_two.returncode,
                0,
                collision_source_two.stderr + collision_source_two.stdout,
            )

            base_id = "runtime_space_normalization_phase14_dash_term_phase14dashterm"
            overlay_text = overlay_file.read_text(encoding="utf-8")
            ids = re.findall(r'id = "([^"]+)"', overlay_text)
            collision_ids = [entry_id for entry_id in ids if entry_id.startswith(base_id)]
            self.assertEqual(len(collision_ids), 2)
            self.assertEqual(len(set(collision_ids)), 2)
            self.assertIn(base_id, collision_ids)
            self.assertTrue(any(entry_id.startswith(f"{base_id}_") for entry_id in collision_ids))

            listed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "list",
                    "space-normalization",
                    "--term",
                    "phase space",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr + listed.stdout)
            self.assertIn("runtime_space_normalization_phase_space_phasespace", listed.stdout)

            duplicate = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "space-normalization",
                    "phase space",
                    "--target",
                    "phaseother",
                    "--reason",
                    "Synthetic duplicate source.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(duplicate.returncode, 0, duplicate.stderr + duplicate.stdout)
            self.assertIn("space-normalization already contains phase space", duplicate.stderr + duplicate.stdout)

            inactivate = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "inactivate",
                    "space-normalization",
                    "runtime_space_normalization_phase_space_phasespace",
                    "--reason",
                    "Synthetic space-normalization inactivation.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(inactivate.returncode, 0, inactivate.stderr + inactivate.stdout)
            after_inactivate = _runtime_overlay_probe(
                app_dir,
                """
{
    "normalized": _apply_space_normalizations("phase space"),
}
""",
            )
            self.assertEqual(after_inactivate["normalized"], "phase space")

    def test_dual_keyword_normalization_cli_writes_ordered_runtime_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            overlay_file = app_dir / "languages" / "sv" / "ingredient_matching" / "runtime_rule_overlays.toml"
            sanity_file = app_dir / "support_checks" / "run_deep_matcher_sanity.py"
            live_app_dir = Path(__file__).resolve().parents[2]

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "dual-keyword-normalization",
                    "phase pickles",
                    "--primary",
                    "phasepickles",
                    "--extra-keywords",
                    "phasefamily",
                    "--reason",
                    "Synthetic dual-keyword normalization.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            overlay_text = overlay_file.read_text(encoding="utf-8")
            self.assertIn('id = "runtime_space_normalization_phase_pickles_phasepickles_phasefamily"', overlay_text)
            self.assertIn('source = "phase pickles"', overlay_text)
            self.assertIn('target = "phasepickles phasefamily"', overlay_text)
            self.assertIn("Canonical order: phasepickles is first", result.stdout)

            runtime = _runtime_overlay_probe(
                app_dir,
                """
{
    "normalized": _apply_space_normalizations("phase pickles"),
}
""",
            )
            self.assertEqual(runtime["normalized"], "phasepickles phasefamily")

            sanity_text = sanity_file.read_text(encoding="utf-8")
            self.assertIn("generated by dm matcher add dual-keyword-normalization", sanity_text)
            self.assertIn("# sanity-id: runtime_dual_keyword_normalization_phase_pickles_phasepickles", sanity_text)
            self.assertIn('"dual-keyword-normalization phase pickles -> phasepickles phasefamily"', sanity_text)

    def test_runtime_blocker_warns_for_space_normalized_compound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]

            space_norm = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "space-normalization",
                    "phase blocker",
                    "--target",
                    "phaseblocker",
                    "--reason",
                    "Synthetic joined compound warning setup.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(space_norm.returncode, 0, space_norm.stderr + space_norm.stdout)

            warning = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "fpb",
                    "blocker",
                    "--blockers",
                    "phase",
                    "--reason",
                    "Synthetic missing joined blocker warning.",
                    "--tree-root",
                    str(tree_root),
                    "--dry-run",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(warning.returncode, 0, warning.stderr + warning.stdout)
            warning_output = warning.stderr + warning.stdout
            self.assertIn(
                "space-normalization joins 'phase blocker' -> 'phaseblocker'",
                warning_output,
            )
            self.assertIn("Add 'phaseblocker' too", warning_output)

            covered = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "fpb",
                    "blocker",
                    "--blockers",
                    "phase,phaseblocker",
                    "--reason",
                    "Synthetic joined blocker covered.",
                    "--tree-root",
                    str(tree_root),
                    "--dry-run",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(covered.returncode, 0, covered.stderr + covered.stdout)
            self.assertNotIn("may not fire on the joined form", covered.stderr + covered.stdout)

    def test_runtime_set_update_cli_writes_keyword_and_carrier_overlays(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            deep_sanity_file = app_dir / "support_checks" / "run_deep_matcher_sanity.py"
            live_app_dir = Path(__file__).resolve().parents[2]

            broad = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "stop-word",
                    "--terms",
                    "abc",
                    "--reason",
                    "Synthetic broad stop-word.",
                    "--tree-root",
                    str(tree_root),
                    "--dry-run",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(broad.returncode, 0, broad.stderr + broad.stdout)
            self.assertIn("--allow-broad", broad.stderr + broad.stdout)

            commands = [
                [
                    "stop-word",
                    "--terms",
                    "phasefilterword",
                    "--reason",
                    "Synthetic stop-word.",
                ],
                [
                    "non-food-keyword",
                    "--terms",
                    "phasenonfood",
                    "--reason",
                    "Synthetic non-food keyword.",
                ],
                [
                    "flavor-word",
                    "--terms",
                    "phaseflavor",
                    "--reason",
                    "Synthetic flavor word.",
                ],
                [
                    "carrier-product",
                    "--terms",
                    "phasecarrier",
                    "--reason",
                    "Synthetic carrier product.",
                ],
                [
                    "important-short-keyword",
                    "--terms",
                    "px",
                    "--reason",
                    "Synthetic important short keyword.",
                ],
                [
                    "processed-food",
                    "--terms",
                    "snabbnudlar",
                    "--action",
                    "remove",
                    "--reason",
                    "Synthetic processed-food removal.",
                ],
            ]
            for command in commands:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "cli.dm",
                        "matcher",
                        "add",
                        *command,
                        "--tree-root",
                        str(tree_root),
                        "--no-run-gates",
                    ],
                    cwd=live_app_dir,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            runtime = _runtime_overlay_probe(
                app_dir,
                """
{
    "stop": "phasefilterword" in STOP_WORDS,
    "stop_extracted": extract_keywords_from_product("phasefilterword"),
    "non_food": "phasenonfood" in NON_FOOD_KEYWORDS,
    "non_food_extracted": extract_keywords_from_product("phasenonfood"),
    "flavor": "phaseflavor" in FLAVOR_WORDS,
    "carrier": "phasecarrier" in CARRIER_PRODUCTS,
    "short": "px" in IMPORTANT_SHORT_KEYWORDS,
    "processed_removed": "snabbnudlar" in PROCESSED_FOODS,
}
""",
            )
            self.assertEqual(runtime["stop"], True)
            self.assertEqual(runtime["stop_extracted"], [])
            self.assertEqual(runtime["non_food"], True)
            self.assertEqual(runtime["non_food_extracted"], [])
            self.assertEqual(runtime["flavor"], True)
            self.assertEqual(runtime["carrier"], True)
            self.assertEqual(runtime["short"], True)
            self.assertEqual(runtime["processed_removed"], False)

            sanity_text = deep_sanity_file.read_text(encoding="utf-8")
            self.assertIn("stop-word filters extraction phasefilterword", sanity_text)
            self.assertIn("non-food-keyword filters product phasenonfood", sanity_text)

            listed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "list",
                    "stop-word",
                    "--term",
                    "phasefilterword",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr + listed.stdout)
            self.assertIn("runtime_stop_word_add_phasefilterword", listed.stdout)

            inactivate = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "inactivate",
                    "stop-word",
                    "phasefilterword",
                    "--reason",
                    "Synthetic stop-word inactivation.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(inactivate.returncode, 0, inactivate.stderr + inactivate.stdout)
            after_inactivate = _runtime_overlay_probe(
                app_dir,
                """
{
    "stop": "phasefilterword" in STOP_WORDS,
}
""",
            )
            self.assertEqual(after_inactivate["stop"], False)

    def test_cuisine_context_cli_writes_runtime_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]

            commands = [
                [
                    "carrier-context-required",
                    "--terms",
                    "phasecarriercontext",
                    "--reason",
                    "Synthetic carrier context requirement.",
                ],
                [
                    "context-required-word",
                    "--terms",
                    "phasecontextrequired",
                    "--reason",
                    "Synthetic product context requirement.",
                ],
                [
                    "ingredient-requires-product-context",
                    "--terms",
                    "phaseingredientcontext",
                    "--reason",
                    "Synthetic ingredient context requirement.",
                ],
            ]
            for command in commands:
                added = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "cli.dm",
                        "matcher",
                        "add",
                        *command,
                        "--tree-root",
                        str(tree_root),
                        "--no-run-gates",
                    ],
                    cwd=live_app_dir,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(added.returncode, 0, added.stderr + added.stdout)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "cuisine-context",
                    "phasecuisine",
                    "--contexts",
                    "phase recipe, phase dish",
                    "--reason",
                    "Synthetic cuisine context.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            exemption = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "context-word-exemption",
                    "phasekeyword",
                    "--context-words",
                    "phasecontextrequired",
                    "--reason",
                    "Synthetic context-word exemption.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(exemption.returncode, 0, exemption.stderr + exemption.stdout)

            runtime = _runtime_overlay_probe(
                app_dir,
                """
{
    "carrier_context_required": sorted(CARRIER_CONTEXT_REQUIRED & {"phasecarriercontext"}),
    "context_required": sorted(CONTEXT_REQUIRED_WORDS & {"phasecontextrequired"}),
    "ingredient_requires": sorted(INGREDIENT_REQUIRES_IN_PRODUCT & {"phaseingredientcontext"}),
    "exemptions": sorted(CONTEXT_WORD_KEYWORD_EXEMPTIONS.get("phasekeyword", [])),
    "contexts": sorted(CUISINE_CONTEXT.get("phasecuisine", [])),
}
""",
            )
            self.assertEqual(runtime["carrier_context_required"], ["phasecarriercontext"])
            self.assertEqual(runtime["context_required"], ["phasecontextrequired"])
            self.assertEqual(runtime["ingredient_requires"], ["phaseingredientcontext"])
            self.assertEqual(runtime["exemptions"], ["phasecontextrequired"])
            self.assertEqual(runtime["contexts"], ["phase dish", "phase recipe"])

            listed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "list",
                    "cuisine-context",
                    "--term",
                    "phasecuisine",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr + listed.stdout)
            self.assertIn("runtime_cuisine_context_phasecuisine", listed.stdout)

            context_listed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "list",
                    "context-required-word",
                    "--term",
                    "phasecontextrequired",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(context_listed.returncode, 0, context_listed.stderr + context_listed.stdout)
            self.assertIn("runtime_context_required_word_phasecontextrequired", context_listed.stdout)

    def test_match_filter_cli_writes_runtime_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]

            substitution = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "product-name-substitution",
                    "--required-words",
                    "phase required",
                    "--old-keyword",
                    "phaseold",
                    "--new-keyword",
                    "phasenew",
                    "--reason",
                    "Synthetic product substitution.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(substitution.returncode, 0, substitution.stderr + substitution.stdout)

            secondary = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "secondary-ingredient-pattern",
                    "phasesecondary",
                    "--blockers",
                    "phaseblocker",
                    "--exceptions",
                    "phaseexception",
                    "--reason",
                    "Synthetic secondary ingredient pattern.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(secondary.returncode, 0, secondary.stderr + secondary.stdout)

            runtime = _runtime_overlay_probe(
                app_dir,
                """
{
    "substitution": any(
        set(required_words) == {"phase required"}
        and old_keyword == "phaseold"
        and new_keyword == "phasenew"
        for required_words, old_keyword, new_keyword in PRODUCT_NAME_SUBSTITUTIONS
    ),
    "secondary_blockers": sorted(SECONDARY_INGREDIENT_PATTERNS["phasesecondary"][0]),
    "secondary_exceptions": sorted(SECONDARY_INGREDIENT_PATTERNS["phasesecondary"][1]),
    "secondary_blocks": check_secondary_ingredient_patterns("phaseblocker", "phasesecondary", "phasesecondary"),
    "secondary_allows": check_secondary_ingredient_patterns("phaseblocker phaseexception", "phasesecondary", "phasesecondary"),
}
""",
            )
            self.assertEqual(runtime["substitution"], True)
            self.assertEqual(runtime["secondary_blockers"], ["phaseblocker"])
            self.assertEqual(runtime["secondary_exceptions"], ["phaseexception"])
            self.assertEqual(runtime["secondary_blocks"], False)
            self.assertEqual(runtime["secondary_allows"], True)

            listed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "list",
                    "secondary-ingredient-pattern",
                    "--term",
                    "phasesecondary",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr + listed.stdout)
            self.assertIn("runtime_secondary_ingredient_pattern_phasesecondary", listed.stdout)

    def test_qualifier_required_keyword_cli_writes_runtime_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "qualifier-required-keyword",
                    "--terms",
                    "phasequalifier",
                    "--reason",
                    "Synthetic qualifier-required keyword.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            runtime = _runtime_overlay_probe(
                app_dir,
                """
{
    "qualifier_required": "phasequalifier" in _QUALIFIER_REQUIRED_KEYWORDS,
}
""",
            )
            self.assertEqual(runtime["qualifier_required"], True)

            listed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "list",
                    "qualifier-required-keyword",
                    "--term",
                    "phasequalifier",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr + listed.stdout)
            self.assertIn("runtime_qualifier_required_keyword_add_phasequalifier", listed.stdout)

    def test_processed_rule_cli_writes_runtime_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]

            commands = [
                [
                    "processed-rule",
                    "phaseprocessed",
                    "--blocked-product-words",
                    "phaseblocked",
                    "--reason",
                    "Synthetic processed rule.",
                ],
                [
                    "processed-exemption",
                    "phaseprocessed",
                    "--compounds",
                    "phasecompound",
                    "--reason",
                    "Synthetic processed exemption.",
                ],
                [
                    "strict-processed-rule",
                    "--terms",
                    "phaseprocessed",
                    "--reason",
                    "Synthetic strict processed rule.",
                ],
            ]
            for command in commands:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "cli.dm",
                        "matcher",
                        "add",
                        *command,
                        "--tree-root",
                        str(tree_root),
                        "--no-run-gates",
                    ],
                    cwd=live_app_dir,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            runtime = _runtime_overlay_probe(
                app_dir,
                """
{
    "processed_rule": sorted(PROCESSED_PRODUCT_RULES.get("phaseprocessed", set())),
    "processed_exemption": sorted(PROCESSED_RULES_COMPOUND_EXEMPTIONS.get("phaseprocessed", set())),
    "strict": "phaseprocessed" in STRICT_PROCESSED_RULES,
}
""",
            )
            self.assertEqual(runtime["processed_rule"], ["phaseblocked"])
            self.assertEqual(runtime["processed_exemption"], ["phasecompound"])
            self.assertEqual(runtime["strict"], True)

            listed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "list",
                    "processed-rule",
                    "--term",
                    "phaseprocessed",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr + listed.stdout)
            self.assertIn("runtime_processed_rule_phaseprocessed", listed.stdout)

    def test_spice_fresh_rule_cli_writes_runtime_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "spice-fresh-rule",
                    "phasespice",
                    "--blocked-product-words",
                    "phasefresh",
                    "--spice-indicators",
                    "phaseindicator",
                    "--fresh-product-words",
                    "phasefreshproduct",
                    "--dried-indicators",
                    "phasedried",
                    "--reason",
                    "Synthetic spice/fresh rule.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            runtime = _runtime_overlay_probe(
                app_dir,
                """
{
    "blocked": sorted(SPICE_VS_FRESH_RULES["phasespice"]["blocked_product_words"]),
    "spice": sorted(SPICE_VS_FRESH_RULES["phasespice"]["spice_indicators"]),
    "fresh": sorted(SPICE_VS_FRESH_RULES["phasespice"]["fresh_product_words"]),
    "dried": sorted(SPICE_VS_FRESH_RULES["phasespice"]["dried_indicators"]),
}
""",
            )
            self.assertEqual(runtime["blocked"], ["phasefresh"])
            self.assertEqual(runtime["spice"], ["phaseindicator"])
            self.assertEqual(runtime["fresh"], ["phasefreshproduct"])
            self.assertEqual(runtime["dried"], ["phasedried"])

            listed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "list",
                    "spice-fresh-rule",
                    "--term",
                    "phasespice",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr + listed.stdout)
            self.assertIn("runtime_spice_fresh_rule_phasespice", listed.stdout)

    def test_compound_protection_cli_writes_runtime_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "compound-protection",
                    "--mode",
                    "prefix-strict",
                    "--keywords",
                    "phasecompound",
                    "--reason",
                    "Synthetic compound protection.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            runtime = _runtime_overlay_probe(
                app_dir,
                """
{
    "prefix": "phasecompound" in _COMPOUND_STRICT_PREFIX_KEYWORDS,
}
""",
            )
            self.assertEqual(runtime["prefix"], True)

            listed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "list",
                    "compound-protection",
                    "--term",
                    "phasecompound",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr + listed.stdout)
            self.assertIn("runtime_compound_protection_prefix_strict_phasecompound", listed.stdout)

    def test_specialty_cli_writes_runtime_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]

            commands = [
                [
                    "specialty-qualifier",
                    "phasebase",
                    "--qualifiers",
                    "phasequal",
                    "--bidirectional",
                    "--reason",
                    "Synthetic specialty qualifier.",
                    "--sanity-ingredient",
                    "phasequal phasebase",
                    "--sanity-offer",
                    "Phasequal Phasebase",
                ],
                [
                    "qualifier-equivalent",
                    "phasequal",
                    "--equivalents",
                    "phaseequiv",
                    "--reason",
                    "Synthetic qualifier equivalent.",
                ],
            ]
            for command in commands:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "cli.dm",
                        "matcher",
                        "add",
                        *command,
                        "--tree-root",
                        str(tree_root),
                        "--no-run-gates",
                    ],
                    cwd=live_app_dir,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            runtime = _runtime_overlay_probe(
                app_dir,
                """
{
    "specialty": "phasequal" in SPECIALTY_QUALIFIERS.get("phasebase", []),
    "bidirectional": "phasequal" in BIDIRECTIONAL_PER_KEYWORD.get("phasebase", set()),
    "equivalent": "phaseequiv" in QUALIFIER_EQUIVALENTS.get("phasequal", set()),
}
""",
            )
            self.assertEqual(runtime["specialty"], True)
            self.assertEqual(runtime["bidirectional"], True)
            self.assertEqual(runtime["equivalent"], True)
            deep_sanity_text = (app_dir / "support_checks" / "run_deep_matcher_sanity.py").read_text(encoding="utf-8")
            self.assertIn("specialty-qualifier Phasequal Phasebase match phasequal phasebase (backend)", deep_sanity_text)
            self.assertIn("recipe_match_num_named", deep_sanity_text)

    def test_registry_inactivation_cli_marks_entries_inactive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            ingredient_parent_file = (
                app_dir
                / "languages"
                / "sv"
                / "ingredient_matching"
                / "term_registry"
                / "entries"
                / "ingredient_parent.toml"
            )
            live_app_dir = Path(__file__).resolve().parents[2]

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "inactivate",
                    "ingredient-parent",
                    "sv-se.alias.jasminris_001",
                    "--reason",
                    "Synthetic registry inactivation.",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            text = ingredient_parent_file.read_text(encoding="utf-8")
            block_start = text.index('entry_id = "sv-se.alias.jasminris_001"')
            block_end = text.index("[[entries]]", block_start + 1)
            block = text[block_start:block_end]
            self.assertIn("# inactive_reason: Synthetic registry inactivation.", block)
            self.assertIn('status = "inactive"', block)

            listed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "list",
                    "ingredient-parent",
                    "--term",
                    "sv-se.alias.jasminris_001",
                    "--include-inactive",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr + listed.stdout)
            self.assertIn("sv-se.alias.jasminris_001\tinactive\tingredient-parent", listed.stdout)

    def test_support_check_runner_preserves_exit_code_and_env(self) -> None:
        calls = []
        original_run = dm_cli._run

        def fake_run(argv, *, cwd, env=None):
            calls.append({"argv": argv, "cwd": cwd, "env": env})
            return 42

        dm_cli._run = fake_run
        try:
            status = dm_cli._run_support_check(
                "run_deep_matcher_sanity.py",
                ["--synthetic-flag"],
                tree_root=Path("/tmp/dm-matcher-tree"),
                report_root=Path("/tmp/dm-matcher-reports"),
                cwd=Path("/tmp/dm-matcher-cwd"),
            )
        finally:
            dm_cli._run = original_run

        self.assertEqual(status, 42)
        self.assertEqual(len(calls), 1)
        self.assertTrue(str(calls[0]["argv"][1]).endswith("support_checks/run_deep_matcher_sanity.py"))
        self.assertIn("--synthetic-flag", calls[0]["argv"])
        self.assertEqual(calls[0]["cwd"], Path("/tmp/dm-matcher-cwd"))
        self.assertEqual(calls[0]["env"]["DEAL_MEALS_SUPPORT_REPORT_ROOT"], "/tmp/dm-matcher-reports")

    def test_deep_sanity_generator_has_fast_and_backend_modes(self) -> None:
        fast_lines = dm_cli._deep_sanity_match_assertion(
            description="Synthetic fast sanity",
            offer_name="Phase Offer",
            ingredient="phase ingredient",
            offer_category="pantry",
            expected_canonical="phase",
            mode="fast-match",
        )
        backend_lines = dm_cli._deep_sanity_match_assertion(
            description="Synthetic backend sanity",
            offer_name="Phase Offer",
            ingredient="phase ingredient",
            offer_category="pantry",
            expected_canonical=None,
            mode="backend-match",
            recipe_name="Phase Recipe",
        )

        self.assertIn("match(", "\n".join(fast_lines))
        self.assertIn('"phase"', "\n".join(fast_lines))
        self.assertIn("recipe_match_num_named", "\n".join(backend_lines))
        self.assertIn('"Phase Recipe"', "\n".join(backend_lines))
        self.assertTrue("\n".join(backend_lines).rstrip().endswith(", 0)"))

    def test_split_csv_preserves_regex_commas(self) -> None:
        self.assertEqual(
            dm_cli._split_csv(
                r"(?=.*\bphase9.{0,40}blocked\b)(?=.*\d{2}\b).*",
                label="--blocked-offer-patterns",
                lowercase=False,
            ),
            (r"(?=.*\bphase9.{0,40}blocked\b)(?=.*\d{2}\b).*",),
        )
        self.assertEqual(
            dm_cli._split_csv(r"phase9\,literal,phase9next", label="--terms", lowercase=False),
            ("phase9,literal", "phase9next"),
        )

    def test_dm_matcher_help_lists_unified_entry_points(self) -> None:
        live_app_dir = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [sys.executable, "-m", "cli.dm", "matcher", "--help"],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        for command in (
            "add",
            "session",
            "batch",
            "gates",
            "dev-watch",
            "guide",
            "doctor",
            "trace-extraction",
            "preflight",
            "sanity",
            "promote",
            "regen",
            "refresh-line-refs",
            "list",
            "inactivate",
            "explain",
            "why",
            "compare-paths",
            "canonical-of",
            "sanity-find",
            "sanity-update",
            "reconcile-sanity",
        ):
            self.assertIn(command, result.stdout)

    def test_dm_matcher_session_start_status_abort_uses_tree_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            state_path = dm_cli._matcher_session_fallback_path(dm_cli._paths(tree_root))
            live_app_dir = Path(__file__).resolve().parents[2]

            start = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "session",
                    "start",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(start.returncode, 0, start.stderr + start.stdout)
            self.assertIn("Started matcher session", start.stdout)
            self.assertTrue(state_path.exists())

            status = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "session",
                    "status",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
            self.assertIn("Active matcher session", status.stdout)

            abort = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "session",
                    "abort",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(abort.returncode, 0, abort.stderr + abort.stdout)
            self.assertFalse(state_path.exists())

    def test_active_matcher_session_defers_gates_unless_forced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = dm_cli._paths(Path(tmp))
            dm_cli._write_matcher_session_state(
                paths,
                {"version": dm_cli.MATCHER_SESSION_VERSION, "started_at": "test"},
            )
            calls = []
            original_argv = sys.argv
            original_run_support_check = dm_cli._run_support_check

            def fake_run_support_check(script_name, args, *, tree_root=None, report_root=None, cwd=None):
                calls.append((script_name, args, tree_root, report_root, cwd))
                return 17

            dm_cli._run_support_check = fake_run_support_check
            try:
                sys.argv = ["dm", "matcher", "add", "pnb"]
                self.assertEqual(dm_cli._run_track_a_runtime_gates(paths, None), 0)
                self.assertEqual(calls, [])

                sys.argv = ["dm", "matcher", "add", "pnb", "--run-gates"]
                self.assertEqual(dm_cli._run_track_a_runtime_gates(paths, None), 17)
                self.assertEqual(len(calls), 1)
            finally:
                sys.argv = original_argv
                dm_cli._run_support_check = original_run_support_check

    def test_active_matcher_session_allows_tree_root_runtime_set_add(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            paths = dm_cli._paths(tree_root)
            dm_cli._write_matcher_session_state(
                paths,
                {"version": dm_cli.MATCHER_SESSION_VERSION, "started_at": "test"},
            )
            live_app_dir = Path(__file__).resolve().parents[2]

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "important-short-keyword",
                    "--terms",
                    "phx",
                    "--reason",
                    "Synthetic short keyword for active-session gate deferral.",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("Matcher session active; deferred gates", result.stdout)
            overlay_text = (
                app_dir / "languages" / "sv" / "ingredient_matching" / "runtime_rule_overlays.toml"
            ).read_text(encoding="utf-8")
            self.assertIn("phx", overlay_text)

    def test_dm_matcher_explain_wraps_matcher_audit(self) -> None:
        live_app_dir = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "cli.dm",
                "matcher",
                "explain",
                "--offer",
                "Ost 500g",
                "--ingredient",
                "ostronsås",
                "--format",
                "json",
            ],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["offer"], "Ost 500g")
        self.assertEqual(payload["ingredient"], "ostronsås")
        self.assertIn("Product keywords:", payload["trace"])
        self.assertIn("Fast matcher result: NO MATCH", payload["trace"])
        self.assertIn("false-positive blockers", payload["trace"])

    def test_dm_matcher_compare_paths_reports_processed_checks(self) -> None:
        live_app_dir = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "cli.dm",
                "matcher",
                "compare-paths",
                "--offer",
                "Färskkorv Chorizo Kryddad Med Rökt Paprika 280g Köttkultur",
                "--ingredient",
                "200 g chorizo",
                "--offer-category",
                "meat",
                "--format",
                "json",
            ],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["fast_keyword"], "chorizo")
        self.assertTrue(payload["backend_matched"])
        self.assertFalse(payload["fast_backend_diverged"])
        self.assertIn("offer_keyword_diff", payload)
        paprika_checks = [row for row in payload["processed_checks"] if row.get("base") == "paprika"]
        self.assertEqual(len(paprika_checks), 1, payload)
        self.assertEqual(paprika_checks[0]["status"], "skipped_not_matched_keyword_family")

    def test_dm_matcher_probe_reports_recipe_name_context(self) -> None:
        live_app_dir = Path(__file__).resolve().parents[2]
        default_name = subprocess.run(
            [
                sys.executable,
                "-m",
                "cli.dm",
                "matcher",
                "probe",
                "--offer",
                "Ost 500g",
                "--ingredient",
                "ost",
            ],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        explicit_name = subprocess.run(
            [
                sys.executable,
                "-m",
                "cli.dm",
                "matcher",
                "probe",
                "--offer",
                "Ost 500g",
                "--ingredient",
                "ost",
                "--recipe-name",
                "Vegansk lasagne",
            ],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(default_name.returncode, 0, default_name.stderr + default_name.stdout)
        self.assertIn("Recipe: DM Matcher Probe", default_name.stdout)
        self.assertIn("default recipe name was used", default_name.stderr)
        self.assertEqual(explicit_name.returncode, 0, explicit_name.stderr + explicit_name.stdout)
        self.assertIn("Recipe: Vegansk lasagne", explicit_name.stdout)
        self.assertNotIn("default recipe name was used", explicit_name.stderr)

    def test_dm_matcher_why_reports_backend_validation_reject_rule(self) -> None:
        live_app_dir = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "cli.dm",
                "matcher",
                "why",
                "--offer",
                "Kryddsmör Vitlök 100g",
                "--ingredient",
                "1 klyfta vitlök",
                "--offer-category",
                "dairy",
                "--format",
                "json",
            ],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["diagnosis_class"], "backend_validation_rejected")
        self.assertEqual(payload["backend_validation"]["reject_rule"], "secondary_ingredient_pattern")
        self.assertEqual(payload["fast_match"]["matched_keyword"], "vitlök")
        self.assertFalse(payload["backend_validation"]["accepted"])
        self.assertIn(
            "secondary_ingredient_pattern",
            [event.get("rule") for event in payload["backend_validation"]["events"]],
        )

    def test_dm_matcher_why_reports_fast_path_shadow_trace(self) -> None:
        live_app_dir = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "cli.dm",
                "matcher",
                "why",
                "--offer",
                "Grädde 40% 5dl",
                "--ingredient",
                "havregrädde",
                "--offer-category",
                "dairy",
                "--format",
                "json",
            ],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["diagnosis_class"], "fast_match_missing")
        shadow = payload["fast_path_shadow_trace"]
        self.assertEqual(shadow["status"], "ok")
        self.assertEqual(shadow["scope"], "observe_only")
        self.assertTrue(
            any(
                row.get("rule") == "keyword_suppressed_by_context"
                and row.get("keyword") == "grädde"
                for row in shadow["likely_rejects"]
            ),
            shadow,
        )

    def test_dm_matcher_trace_extraction_reports_offer_precompute_diff(self) -> None:
        live_app_dir = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "cli.dm",
                "matcher",
                "trace-extraction",
                "--offer",
                "Block Mörk 200g",
                "--offer-category",
                "pantry",
                "--format",
                "json",
            ],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["keywords"], [])
        self.assertEqual(payload["precomputed_keywords"], ["blockchoklad", "bakchoklad"])
        self.assertEqual(payload["keyword_diff"]["precomputed_only"], ["blockchoklad", "bakchoklad"])
        self.assertTrue(payload["precomputed_keyword_explanations"])

    def test_dm_matcher_sanity_update_rewrites_expected_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            sanity_file = app_dir / "support_checks" / "run_deep_matcher_sanity.py"
            live_app_dir = Path(__file__).resolve().parents[2]
            sanity_file.write_text(
                """
def test(description, actual, expected):
    pass

def match(*args):
    return None

# phase_sanity_policy: generated by dm matcher add pnb
# sanity-id: phase_sanity_policy
test("Phase åäö stale canonical expectation", match("Påse räkor", "räka"), "oldcanonical")
""".lstrip(),
                encoding="utf-8",
            )

            found = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "sanity-find",
                    "phase_sanity_policy",
                    "--tree-root",
                    str(tree_root),
                    "--format",
                    "json",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(found.returncode, 0, found.stderr + found.stdout)
            found_payload = json.loads(found.stdout)
            self.assertEqual(found_payload["count"], 1)
            self.assertEqual(found_payload["cases"][0]["sanity_id"], "phase_sanity_policy")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "sanity-update",
                    "phase_sanity_policy",
                    "--expected",
                    "newcanonical",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            sanity_text = sanity_file.read_text(encoding="utf-8")
            self.assertIn('"newcanonical"', sanity_text)
            self.assertNotIn('"oldcanonical"', sanity_text)

    def test_dm_matcher_reconcile_sanity_reports_and_applies_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            sanity_file = app_dir / "support_checks" / "run_deep_matcher_sanity.py"
            live_app_dir = Path(__file__).resolve().parents[2]
            sanity_file.write_text(
                """
def test(description, actual, expected):
    pass

def match(*args):
    return None

# phase_reconcile_policy: generated by dm matcher add pnb
# sanity-id: phase_reconcile_policy
test("Phase reconcile stale canonical expectation", match("Phase Product", "zzzzzz", "pantry"), "oldcanonical")

# phase_reconcile_string: generated by dm matcher add keyword-synonym
# sanity-id: phase_reconcile_string
test("Phase reconcile stale string expectation", match("Pak Choi 250g klass 1 ICA", "pakchoy", "vegetables"), "oldcanonical")
""".lstrip(),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "reconcile-sanity",
                    "phase_reconcile_policy",
                    "--tree-root",
                    str(tree_root),
                    "--format",
                    "json",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["drift_count"], 1)
            self.assertIsNone(payload["cases"][0]["actual_value"])

            apply_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "reconcile-sanity",
                    "phase_reconcile_policy",
                    "--tree-root",
                    str(tree_root),
                    "--apply",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(apply_result.returncode, 0, apply_result.stderr + apply_result.stdout)
            sanity_text = sanity_file.read_text(encoding="utf-8")
            self.assertIn("), None)", sanity_text)

            string_apply_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "reconcile-sanity",
                    "phase_reconcile_string",
                    "--tree-root",
                    str(tree_root),
                    "--apply",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                string_apply_result.returncode,
                0,
                string_apply_result.stderr + string_apply_result.stdout,
            )
            sanity_text = sanity_file.read_text(encoding="utf-8")
            self.assertIn('"pakchoi"', sanity_text)
            self.assertNotIn('"\\"pakchoi\\""', sanity_text)
            self.assertNotIn('"oldcanonical"', sanity_text)

    def test_generated_sanity_uses_observed_positive_materialization(self) -> None:
        paths = dm_cli._paths(dm_cli.REPO_DIR)
        original_compare = dm_cli._compare_matcher_paths

        def fake_compare(**_kwargs):
            return {"fast_matched": True, "fast_keyword": "phasevariant"}

        dm_cli._compare_matcher_paths = fake_compare
        try:
            observed = dm_cli._runtime_observed_expected_canonical(
                paths=paths,
                requested_expected="phaseparent",
                offer_name="Phase offer",
                ingredient="phase ingredient",
                offer_category="pantry",
                sanity_mode="fast-match",
                dry_run=False,
            )
            self.assertEqual(observed, "phasevariant")
            negative_expected = dm_cli._runtime_observed_expected_canonical(
                paths=paths,
                requested_expected=None,
                offer_name="Phase offer",
                ingredient="phase ingredient",
                offer_category="pantry",
                sanity_mode="fast-match",
                dry_run=False,
            )
            self.assertIsNone(negative_expected)
            dry_run_expected = dm_cli._runtime_observed_expected_canonical(
                paths=paths,
                requested_expected="phaseparent",
                offer_name="Phase offer",
                ingredient="phase ingredient",
                offer_category="pantry",
                sanity_mode="fast-match",
                dry_run=True,
            )
            self.assertEqual(dry_run_expected, "phaseparent")
        finally:
            dm_cli._compare_matcher_paths = original_compare

    def test_dm_matcher_guide_routes_manual_and_supported_shapes(self) -> None:
        live_app_dir = Path(__file__).resolve().parents[2]
        pnb = subprocess.run(
            [sys.executable, "-m", "cli.dm", "matcher", "guide", "pnb"],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        synonym = subprocess.run(
            [sys.executable, "-m", "cli.dm", "matcher", "guide", "keyword_synonym"],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        dual_normalization = subprocess.run(
            [sys.executable, "-m", "cli.dm", "matcher", "guide", "dual-keyword-normalization"],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        compare_paths = subprocess.run(
            [sys.executable, "-m", "cli.dm", "matcher", "guide", "compare-paths"],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        why = subprocess.run(
            [sys.executable, "-m", "cli.dm", "matcher", "guide", "why-no-match"],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        canonical_of = subprocess.run(
            [sys.executable, "-m", "cli.dm", "matcher", "guide", "canonical-of"],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        sanity_update = subprocess.run(
            [sys.executable, "-m", "cli.dm", "matcher", "guide", "sanity-update"],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        sanity_find = subprocess.run(
            [sys.executable, "-m", "cli.dm", "matcher", "guide", "sanity-find"],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        reconcile_sanity = subprocess.run(
            [sys.executable, "-m", "cli.dm", "matcher", "guide", "reconcile-sanity"],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(pnb.returncode, 0, pnb.stderr + pnb.stdout)
        self.assertIn("pnb: supported by dm matcher add", pnb.stdout)
        self.assertIn("./bin/dm matcher add pnb", pnb.stdout)
        self.assertIn("./bin/dm matcher explain", pnb.stdout)
        self.assertIn("--no-run-gates", pnb.stdout)
        self.assertEqual(synonym.returncode, 0, synonym.stderr + synonym.stdout)
        self.assertIn("keyword-synonym: supported by dm matcher add", synonym.stdout)
        self.assertIn("./bin/dm matcher add keyword-synonym", synonym.stdout)
        self.assertEqual(dual_normalization.returncode, 0, dual_normalization.stderr + dual_normalization.stdout)
        self.assertIn("dual-keyword-normalization: supported by dm matcher add", dual_normalization.stdout)
        self.assertIn("./bin/dm matcher add dual-keyword-normalization", dual_normalization.stdout)
        self.assertEqual(compare_paths.returncode, 0, compare_paths.stderr + compare_paths.stdout)
        self.assertIn("compare-paths: supported by dm matcher", compare_paths.stdout)
        self.assertIn("./bin/dm matcher compare-paths", compare_paths.stdout)
        self.assertEqual(why.returncode, 0, why.stderr + why.stdout)
        self.assertIn("why: supported by dm matcher", why.stdout)
        self.assertIn("./bin/dm matcher why", why.stdout)
        self.assertEqual(canonical_of.returncode, 0, canonical_of.stderr + canonical_of.stdout)
        self.assertIn("canonical-of: supported by dm matcher", canonical_of.stdout)
        self.assertIn("./bin/dm matcher canonical-of", canonical_of.stdout)
        self.assertEqual(sanity_update.returncode, 0, sanity_update.stderr + sanity_update.stdout)
        self.assertIn("sanity-update: supported by dm matcher", sanity_update.stdout)
        self.assertIn("./bin/dm matcher sanity-update", sanity_update.stdout)
        self.assertEqual(sanity_find.returncode, 0, sanity_find.stderr + sanity_find.stdout)
        self.assertIn("sanity-find: supported by dm matcher", sanity_find.stdout)
        self.assertIn("./bin/dm matcher sanity-find", sanity_find.stdout)
        self.assertEqual(reconcile_sanity.returncode, 0, reconcile_sanity.stderr + reconcile_sanity.stdout)
        self.assertIn("reconcile-sanity: supported by dm matcher", reconcile_sanity.stdout)
        self.assertIn("./bin/dm matcher reconcile-sanity", reconcile_sanity.stdout)

    def test_dm_matcher_list_effective_blocker_origins(self) -> None:
        live_app_dir = Path(__file__).resolve().parents[2]
        pnb = subprocess.run(
            [
                sys.executable,
                "-m",
                "cli.dm",
                "matcher",
                "list",
                "pnb",
                "--effective",
                "--term",
                "havregryn",
            ],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        fpb = subprocess.run(
            [
                sys.executable,
                "-m",
                "cli.dm",
                "matcher",
                "list",
                "fpb",
                "--effective",
                "--term",
                "ostron",
            ],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        overlay = subprocess.run(
            [
                sys.executable,
                "-m",
                "cli.dm",
                "matcher",
                "list",
                "pnb",
                "--effective",
                "--term",
                "sikrom",
            ],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(pnb.returncode, 0, pnb.stderr + pnb.stdout)
        self.assertIn("historical_update:_PRODUCT_NAME_BLOCKER_UPDATES", pnb.stdout)
        self.assertEqual(fpb.returncode, 0, fpb.stderr + fpb.stdout)
        self.assertIn("historical_base:_FALSE_POSITIVE_BLOCKERS_RAW", fpb.stdout)
        self.assertEqual(overlay.returncode, 0, overlay.stderr + overlay.stdout)
        self.assertIn("runtime_overlay:runtime_rule_overlays.toml", overlay.stdout)

    def test_dm_matcher_guide_rejects_unknown_shape(self) -> None:
        live_app_dir = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [sys.executable, "-m", "cli.dm", "matcher", "guide", "phase8-unknown-shape"],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
        self.assertIn("Unknown matcher rule shape: phase8-unknown-shape", result.stderr + result.stdout)
        self.assertIn("./bin/dm matcher preflight and gates", result.stderr + result.stdout)

    def test_dm_matcher_guide_goal_routes_product_phrase_canonical(self) -> None:
        live_app_dir = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [sys.executable, "-m", "cli.dm", "matcher", "guide-goal", "phrase-product-canonical"],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("product-phrase-canonical: goal-oriented guide", result.stdout)
        self.assertIn("single token", result.stdout)
        self.assertIn("offer-extra-keyword", result.stdout)
        self.assertIn("multiword phrase", result.stdout)
        self.assertIn("space-normalization", result.stdout)
        self.assertIn("extraction-helper", result.stdout)
        self.assertIn("raw precompute_offer_data() is not the authority", result.stdout)

    def test_dm_matcher_guide_goal_lists_and_rejects_unknown_goal(self) -> None:
        live_app_dir = Path(__file__).resolve().parents[2]
        listed = subprocess.run(
            [sys.executable, "-m", "cli.dm", "matcher", "guide-goal", "--list"],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        unknown = subprocess.run(
            [sys.executable, "-m", "cli.dm", "matcher", "guide-goal", "cook-the-moon"],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(listed.returncode, 0, listed.stderr + listed.stdout)
        self.assertIn("product-phrase-canonical: goal-oriented guide", listed.stdout)
        self.assertIn("interchangeable-family: goal-oriented guide", listed.stdout)
        self.assertEqual(unknown.returncode, 2, unknown.stderr + unknown.stdout)
        self.assertIn("Unknown matcher goal: cook-the-moon", unknown.stderr + unknown.stdout)

    def test_dm_matcher_regen_check_runs_contracts_before_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "regen",
                    "--tree-root",
                    str(tree_root),
                    "--check",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("Matcher contract TOML sources are canonical.", result.stdout)
        self.assertIn("generate_matcher_registry_coverage.py", result.stdout)
        self.assertLess(
            result.stdout.find("Matcher contract TOML sources are canonical."),
            result.stdout.find("generate_matcher_registry_coverage.py"),
        )

    def test_dm_matcher_regen_rejects_all_with_raw_passthrough(self) -> None:
        live_app_dir = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "cli.dm",
                "matcher",
                "regen",
                "--what",
                "all",
                "--",
                "--format",
                "json",
            ],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("raw pass-through args are only supported", result.stderr + result.stdout)

    def test_dm_matcher_doctor_reports_contract_source_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "doctor",
                    "--tree-root",
                    str(tree_root),
                    "--report-root",
                    str(tree_root / "reports"),
                    "--format",
                    "json",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        checks = {check["id"]: check for check in report["checks"]}
        self.assertIn(report["status"], {"ok", "needs_action"})
        self.assertEqual(checks["contract_sources"]["status"], "ok")
        self.assertEqual(checks["generated_registry_coverage"]["status"], "ok")
        self.assertEqual(checks["extraction_helper_coverage"]["status"], "ok")
        self.assertEqual(checks["extraction_matching_drift_watchlist"]["status"], "ok")
        self.assertIn(checks["line_refs"]["status"], {"ok", "warning"})

    def test_dm_matcher_doctor_reports_missing_extraction_helper_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            extraction_file = app_dir / "languages" / "sv" / "ingredient_matching" / "extraction.py"
            text = extraction_file.read_text(encoding="utf-8")
            needle = "    if re.search(r'\\bpuffat\\s+ris\\b|\\bris\\s+puffat\\b', original_name_lower):"
            self.assertIn(needle, text)
            extraction_file.write_text(
                text.replace(
                    needle,
                    "    if original_name_lower == 'phase missing helper':\n"
                    "        return ['phase_missing_helper']\n\n"
                    f"{needle}",
                    1,
                ),
                encoding="utf-8",
            )
            live_app_dir = Path(__file__).resolve().parents[2]
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "doctor",
                    "--tree-root",
                    str(tree_root),
                    "--report-root",
                    str(tree_root / "reports"),
                    "--format",
                    "json",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        checks = {check["id"]: check for check in report["checks"]}
        coverage = checks["extraction_helper_coverage"]
        self.assertEqual(coverage["status"], "needs_action")
        self.assertEqual(coverage["details"]["missing_count"], 1)
        missing = coverage["details"]["missing"][0]
        self.assertEqual(missing["canonical"], "phase_missing_helper")
        self.assertEqual(missing["side"], "product")
        self.assertIn("dm matcher add extraction-helper phase_missing_helper", missing["suggested_command"])

    def test_dm_matcher_doctor_reports_extraction_matching_drift_watchlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            matching_file = app_dir / "languages" / "sv" / "ingredient_matching" / "matching.py"
            text = matching_file.read_text(encoding="utf-8")
            matching_file.write_text(
                text.replace(
                    r"\bpuffat(?:\s+\w+)?\s+ris\b|\bris\s+puffat\b",
                    r"\bpuffat\s+ris\b|\bris\s+puffat\b",
                    1,
                ),
                encoding="utf-8",
            )
            live_app_dir = Path(__file__).resolve().parents[2]
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "doctor",
                    "--tree-root",
                    str(tree_root),
                    "--report-root",
                    str(tree_root / "reports"),
                    "--format",
                    "json",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        checks = {check["id"]: check for check in report["checks"]}
        drift = checks["extraction_matching_drift_watchlist"]
        self.assertEqual(drift["status"], "warning")
        self.assertEqual(drift["details"]["missing"][0]["watch_id"], "puffat_ris_extraction_matching")
        self.assertEqual(
            drift["details"]["missing"][0]["path"],
            "app/languages/sv/ingredient_matching/matching.py",
        )

    def test_dm_matcher_doctor_warns_on_one_sided_mirrored_surface_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]

            subprocess.run(["git", "init"], cwd=tree_root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=tree_root, check=True, capture_output=True, text=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=DM Test",
                    "-c",
                    "user.email=dm-test@example.invalid",
                    "commit",
                    "-m",
                    "baseline",
                ],
                cwd=tree_root,
                check=True,
                capture_output=True,
                text=True,
            )

            matching_file = app_dir / "languages" / "sv" / "ingredient_matching" / "matching.py"
            matching_file.write_text(
                matching_file.read_text(encoding="utf-8") + "\n# synthetic one-sided mirror change\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "doctor",
                    "--tree-root",
                    str(tree_root),
                    "--report-root",
                    str(tree_root / "reports"),
                    "--format",
                    "json",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        checks = {check["id"]: check for check in report["checks"]}
        mirrored = checks["mirrored_manual_surfaces"]
        self.assertEqual(mirrored["status"], "warning")
        warning = mirrored["details"]["warnings"][0]
        self.assertEqual(warning["watch_id"], "specialty_fast_backend")
        self.assertIn("app/languages/sv/ingredient_matching/matching.py", warning["changed"])
        self.assertIn("app/languages/sv/ingredient_matching/validators.py", warning["missing_peer_changes"])

    def test_dm_matcher_doctor_reports_stale_contract_source_next_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            fixture_source = (
                app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_regression_cases.toml"
            )
            fixture_source.write_text(fixture_source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            live_app_dir = Path(__file__).resolve().parents[2]
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "doctor",
                    "--tree-root",
                    str(tree_root),
                    "--report-root",
                    str(tree_root / "reports"),
                    "--format",
                    "json",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        checks = {check["id"]: check for check in report["checks"]}
        self.assertEqual(report["status"], "needs_action")
        self.assertEqual(checks["contract_sources"]["status"], "needs_action")
        self.assertEqual(report["next_action"]["command"], "./bin/dm matcher regen --what contracts")

    def test_dm_matcher_batch_finalize_dry_run_reports_doctor_and_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "batch",
                    "finalize",
                    "--dry-run",
                    "--track",
                    "B",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("matcher batch finalize dry-run", result.stdout)
        self.assertIn("active batch: none", result.stdout)
        self.assertIn("matcher doctor", result.stdout)
        self.assertIn("planned finalize steps:", result.stdout)
        self.assertIn("regen --check", result.stdout)
        self.assertIn("gates --track B", result.stdout)

    def test_dm_matcher_fixture_make_negative_rewrites_source_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]
            fixture_spec = contract_spec_by_name("matcher_regression_cases", tree_root=tree_root)
            fixtures = load_contract_source(fixture_spec)
            fixtures.append({
                "id": "phase_fixture_to_negative_positive",
                "policy_ref": "policy_phase_fixture_old",
                "source_ref": "manual:policy_phase_fixture_old",
                "recipe_name": "Synthetic Positive Fixture",
                "ingredients": ["1 dl phasefixture"],
                "offer": {"name": "Phasefixture", "category": "pantry"},
                "expected": 1,
                "expected_matches": [{
                    "canonical": "phasefixture",
                    "ingredient_index": 0,
                    "must_match_keyword": "phasefixture",
                }],
            })
            write_contract_source(fixture_spec, fixtures)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "fixture",
                    "make-negative",
                    "phase_fixture_to_negative_positive",
                    "--policy-ref",
                    "policy_phase_fixture_new_negative",
                    "--source-ref",
                    "manual:policy_phase_fixture_new_negative",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("Converted fixture to negative: phase_fixture_to_negative_positive", result.stdout)
            self.assertIn("removed expected_matches: 1", result.stdout)
            self.assertIn("Rewrote canonical matcher contract TOML.", result.stdout)
            self.assertIn("--allow-removals", result.stdout)

            updated_fixtures = load_contract_source(fixture_spec)
            updated_fixture = next(
                row for row in updated_fixtures
                if row["id"] == "phase_fixture_to_negative_positive"
            )
            self.assertEqual(updated_fixture["expected"], 0)
            self.assertNotIn("expected_matches", updated_fixture)
            self.assertEqual(updated_fixture["policy_ref"], "policy_phase_fixture_new_negative")
            self.assertEqual(updated_fixture["source_ref"], "manual:policy_phase_fixture_new_negative")

    def test_dm_matcher_fixture_make_positive_from_current_match_rewrites_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]
            fixture_spec = contract_spec_by_name("matcher_regression_cases", tree_root=tree_root)
            fixtures = load_contract_source(fixture_spec)
            fixtures.append({
                "id": "phase_fixture_to_positive_negative",
                "policy_ref": "policy_phase_fixture_old_negative",
                "source_ref": "manual:policy_phase_fixture_old_negative",
                "recipe_name": "Synthetic Positive Fixture",
                "ingredients": ["2 dl jordgubbssaft"],
                "offer": {"name": "Blandsaft Jordgubb Bob", "category": "beverages"},
                "expected": 0,
            })
            fixtures.append({
                "id": "phase_fixture_to_positive_no_match",
                "policy_ref": "policy_phase_fixture_no_match",
                "source_ref": "manual:policy_phase_fixture_no_match",
                "recipe_name": "Synthetic No Match Fixture",
                "ingredients": ["2 dl jordgubbssaft"],
                "offer": {"name": "Jordgubbsmarmelad Bob", "category": "pantry"},
                "expected": 0,
            })
            write_contract_source(fixture_spec, fixtures)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "fixture",
                    "make-positive",
                    "phase_fixture_to_positive_negative",
                    "--from-current-match",
                    "--policy-ref",
                    "policy_phase_fixture_new_positive",
                    "--source-ref",
                    "manual:policy_phase_fixture_new_positive",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("Current matcher result:", result.stdout)
            self.assertIn("canonical: jordgubbssaft", result.stdout)
            self.assertIn("paths: live/fast/backend/materialized agree", result.stdout)
            self.assertIn("Converted fixture to positive: phase_fixture_to_positive_negative", result.stdout)
            self.assertIn("Rewrote canonical matcher contract TOML.", result.stdout)

            updated_fixtures = load_contract_source(fixture_spec)
            updated_fixture = next(
                row for row in updated_fixtures
                if row["id"] == "phase_fixture_to_positive_negative"
            )
            self.assertEqual(updated_fixture["expected"], 1)
            self.assertEqual(updated_fixture["policy_ref"], "policy_phase_fixture_new_positive")
            self.assertEqual(updated_fixture["source_ref"], "manual:policy_phase_fixture_new_positive")
            self.assertEqual(
                updated_fixture["expected_matches"],
                [{
                    "ingredient_index": 0,
                    "canonical": "jordgubbssaft",
                    "must_match_keyword": "jordgubbssaft",
                }],
            )

            no_match = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "fixture",
                    "make-positive",
                    "phase_fixture_to_positive_no_match",
                    "--from-current-match",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(no_match.returncode, 0, no_match.stderr + no_match.stdout)
            self.assertIn("cannot infer positive expected_matches", no_match.stderr + no_match.stdout)

    def test_dm_matcher_batch_metrics_start_finish_writes_local_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            metrics_path = app_dir / ".dm" / "matcher_batch_metrics.json"
            live_app_dir = Path(__file__).resolve().parents[2]
            start = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "batch",
                    "metrics",
                    "--start",
                    "--tree-root",
                    str(tree_root),
                    "--note",
                    "phase metrics start",
                    "--format",
                    "json",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(start.returncode, 0, start.stderr + start.stdout)
            self.assertTrue(metrics_path.exists())
            started = json.loads(start.stdout)
            self.assertEqual(started["metrics"]["note"], "phase metrics start")

            finish = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "batch",
                    "metrics",
                    "--finish",
                    "--tree-root",
                    str(tree_root),
                    "--note",
                    "phase metrics finish",
                    "--format",
                    "json",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(finish.returncode, 0, finish.stderr + finish.stdout)
            payload = json.loads(finish.stdout)["metrics"]
            self.assertEqual(payload["finished_note"], "phase metrics finish")
            self.assertIn(payload["doctor_status"], {"ok", "needs_action", "blocking_error"})
            self.assertIsInstance(payload["elapsed_seconds"], int)

    def test_dm_matcher_trace_extraction_explains_short_ingredient_drop(self) -> None:
        live_app_dir = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "cli.dm",
                "matcher",
                "trace-extraction",
                "--ingredient",
                "zzzzzz",
                "--format",
                "json",
            ],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["keywords"], [])
        short_token = next(row for row in report["tokens"] if row["token"] == "zzzzzz")
        self.assertEqual(short_token["status"], "dropped_too_short")
        self.assertEqual(short_token["length"], 6)
        self.assertEqual(short_token["min_length"], 7)
        self.assertFalse(short_token["sets"]["important_short_keyword"])

    def test_dm_matcher_canonical_of_shows_runtime_canonical(self) -> None:
        live_app_dir = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "cli.dm",
                "matcher",
                "canonical-of",
                "dragon",
                "--format",
                "json",
            ],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["normalized"], "estragon")
        self.assertEqual(payload["direct_canonical"], "estragon")
        self.assertEqual(payload["ingredient_keywords"], ["estragon"])
        self.assertIn("estragon", payload["likely_canonicals"])

    def test_dm_matcher_preflight_tree_root_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "preflight",
                    "--tree-root",
                    str(tree_root),
                    "--format",
                    "json",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        json_start = result.stdout.find("{")
        self.assertGreaterEqual(json_start, 0, result.stdout)
        report = json.loads(result.stdout[json_start:])
        self.assertTrue(report["summary"]["passed"], report)

    def test_prefix_schema_and_convention_entry(self) -> None:
        self.assertIn("current_review:", allowed_prefixes("source_ref"))
        self.assertIn("matcher_layer_diagnostics:", allowed_prefixes("adapter_ref"))
        self.assertIn("keyword_synonyms:", allowed_prefixes("adapter_ref"))
        self.assertIn("keyword_synonyms:", non_registered_prefixes("adapter_ref"))

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

    def test_dm_matcher_regen_contracts_refreshes_toml_source_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            fixture_source_file = (
                app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_regression_cases.toml"
            )
            fixture_source_file.write_text(
                fixture_source_file.read_text(encoding="utf-8").replace(
                    'id = "plan_initial_jordgubbssaft_positive"',
                    'id = "plan_initial_jordgubbssaft_positive_gate_json"',
                    1,
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "regen",
                    "--what",
                    "contracts",
                    "--tree-root",
                    str(tree_root),
                ],
                cwd=Path(__file__).resolve().parents[2],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("Rewrote canonical matcher contract TOML.", result.stdout)
            self.assertEqual(
                fixture_source_file.read_text(encoding="utf-8").count(
                    'id = "plan_initial_jordgubbssaft_positive_gate_json"'
                ),
                1,
            )

    def test_toml_source_round_trip_is_lossless(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            results = audit_contract_sources(output_dir)

            report = json.loads(toml_source_json_report(results))
            self.assertEqual(report["decision"], "PASS")
            self.assertEqual(
                {result.contract: result.row_count for result in results},
                {
                    "matcher_regression_cases": len(load_fixture_contract(DEFAULT_FIXTURE_FILE)),
                    "matcher_rule_inventory": len(load_inventory_contract(DEFAULT_INVENTORY_FILE)),
                },
            )
            for result in results:
                self.assertTrue(result.semantic_equal)
                self.assertTrue(result.canonical_byte_equal)
                self.assertEqual(result.canonical_diff_line_count, 0)
                self.assertTrue(Path(result.source_toml_path).exists())

            self.assertTrue((output_dir / "matcher_regression_cases.toml").exists())
            self.assertTrue((output_dir / "matcher_rule_inventory.toml").exists())

    def test_preflight_rejects_noncanonical_contract_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            fixture_file = (
                app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_regression_cases.toml"
            )
            fixture_file.write_text(
                fixture_file.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )

            report = run_preflight(tree_root=tree_root)

        codes = {issue["code"] for issue in report["new_issues"]}
        self.assertEqual(codes, {"matcher_contract_toml_source_drift"}, report)

    def test_preflight_rejects_stale_toml_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            fixture_source_file = (
                app_dir / "languages" / "sv" / "matcher_contracts" / "sources" / "matcher_regression_cases.toml"
            )
            fixture_source_file.write_text(
                fixture_source_file.read_text(encoding="utf-8").replace(
                    'id = "plan_initial_jordgubbssaft_positive"',
                    'id = "plan_initial_jordgubbssaft_positive_drift"',
                    1,
                ),
                encoding="utf-8",
            )

            report = run_preflight(tree_root=tree_root)

        codes = {issue["code"] for issue in report["new_issues"]}
        self.assertIn("generated_coverage_stale", codes, report)

    def test_line_ref_refresh_updates_toml_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            _copy_matcher_tree(tree_root)
            inventory_spec = contract_spec_by_name("matcher_rule_inventory", tree_root=tree_root)
            inventory = load_contract_source(inventory_spec)
            target_entry = next(
                entry
                for entry in inventory
                if any(
                    isinstance(line_ref, dict)
                    and int(line_ref.get("start") or 0) != 1
                    for line_ref in entry.get("line_refs") or []
                )
            )
            target_id = target_entry["id"]
            target_ref = next(
                line_ref
                for line_ref in target_entry["line_refs"]
                if int(line_ref.get("start") or 0) != 1
            )
            expected_start = target_ref["start"]
            expected_end = target_ref["end"]
            target_ref["start"] = 1
            target_ref["end"] = 1
            write_contract_source(inventory_spec, inventory)

            summary = refresh_inventory_line_refs_from_contract_source(
                tree_root=tree_root,
                repo_root=tree_root,
                write=True,
            )

            refreshed_inventory = load_contract_source(inventory_spec)
            refreshed_entry = next(entry for entry in refreshed_inventory if entry["id"] == target_id)
            refreshed_ref = next(
                line_ref
                for line_ref in refreshed_entry["line_refs"]
                if line_ref["anchor"] == target_ref["anchor"]
            )
            self.assertGreaterEqual(summary["updated"], 1)
            self.assertEqual(refreshed_ref["start"], expected_start)
            self.assertEqual(refreshed_ref["end"], expected_end)

    def test_line_ref_refresh_text_output_lists_missing_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            source_file = tree_root / "source.toml"
            inventory_file = tree_root / "matcher_rule_inventory.toml"
            source_file.write_text('entry_id = "present"\n', encoding="utf-8")
            write_inventory_contract(
                [
                    {
                        "id": "phase_missing_anchor",
                        "line_refs": [
                            {
                                "path": "source.toml",
                                "start": 1,
                                "end": 1,
                                "anchor": 'entry_id = "missing"',
                            }
                        ],
                    }
                ],
                inventory_file,
            )
            live_app_dir = Path(__file__).resolve().parents[2]

            result = subprocess.run(
                [
                    sys.executable,
                    str(live_app_dir / "support_checks" / "refresh_matcher_rule_inventory_line_refs.py"),
                    "--repo-root",
                    str(tree_root),
                    "--inventory-file",
                    str(inventory_file),
                    "--format",
                    "text",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("1 missing anchors", result.stdout)
            self.assertIn("id=phase_missing_anchor", result.stdout)
            self.assertIn("path=source.toml", result.stdout)
            self.assertIn('anchor="entry_id = \\"missing\\""', result.stdout)

    def test_simple_toml_add_commands_write_expected_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]
            commands = [
                [
                    "ingredient-parent",
                    "phase9ris",
                    "--variants",
                    "phase9jasminris",
                    "--sanity-offer",
                    "Phase9ris",
                ],
                [
                    "offer-extra-keyword",
                    "phase9potatis",
                    "--variants",
                    "phase9bakpotatis",
                    "--sanity-ingredient",
                    "phase9potatis",
                ],
                [
                    "ingredient-routing-parent",
                    "phase9svamp",
                    "--variants",
                    "phase9skogssvamp",
                    "--sanity-offer",
                    "Phase9skogssvamp",
                ],
                [
                    "parent-match-only",
                    "phase9kalkon",
                    "--variants",
                    "phase9kalkonbrost",
                    "--sanity-offer",
                    "Phase9kalkonbrost",
                    "--negative-offer",
                    "Phase9kycklingbrost",
                    "--negative-ingredient",
                    "phase9kalkon",
                ],
                [
                    "recipe-routing-helper",
                    "phase9ost",
                    "--variants",
                    "phase9ost",
                    "--sanity-ingredient",
                    "phase9prastost",
                    "--sanity-offer",
                    "Phase9ost",
                ],
            ]

            for command in commands:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "cli.dm",
                        "matcher",
                        "add",
                        *command,
                        "--tree-root",
                        str(tree_root),
                        "--no-run-gates",
                    ],
                    cwd=live_app_dir,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertIn("Next: run", result.stdout)

            entries_dir = app_dir / "languages" / "sv" / "ingredient_matching" / "term_registry" / "entries"
            entries = load_registry_entries(entries_dir=entries_dir, include_local=False)

            self.assertEqual(
                build_ingredient_parents_export_from_entries(entries)["phase9jasminris"],
                "phase9ris",
            )
            self.assertEqual(
                build_offer_extra_keywords_export_from_entries(entries)["phase9bakpotatis"],
                ["phase9potatis"],
            )
            self.assertEqual(
                build_ingredient_routing_parent_export_from_entries(entries)["phase9skogssvamp"],
                "phase9svamp",
            )
            self.assertEqual(
                build_parent_match_only_export_from_entries(entries)["phase9kalkonbrost"],
                "phase9kalkon",
            )
            self.assertEqual(
                build_recipe_routing_extra_alias_export_from_entries(entries)["phase9ost"],
                "phase9ost",
            )
            sanity_text = (app_dir / "support_checks" / "run_deep_matcher_sanity.py").read_text(
                encoding="utf-8"
            )
            self.assertIn("generated by dm matcher add recipe-routing-helper", sanity_text)
            self.assertIn("Phase9kycklingbrost\", \"phase9kalkon\", \"\"), None)", sanity_text)

    def test_parent_match_only_negative_canary_requires_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "parent-match-only",
                    "phase9korv",
                    "--variants",
                    "phase9ringkorv",
                    "--negative-offer",
                    "Phase9annan korv",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--negative-ingredient and --negative-offer", result.stderr + result.stdout)

    def test_ingredient_parent_warns_when_parent_pnb_is_not_mirrored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]
            overlay_file = app_dir / "languages" / "sv" / "ingredient_matching" / "runtime_rule_overlays.toml"
            overlay_file.write_text(
                overlay_file.read_text(encoding="utf-8")
                + """

[[product_name_blockers]]
id = "runtime_pnb_phase9parent"
status = "active"
keyword = "phase9parent"
blockers = ["phase9blocker"]
reason = "Synthetic parent PNB mirror warning canary."
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "ingredient-parent",
                    "phase9parent",
                    "--variants",
                    "phase9child",
                    "--sanity-offer",
                    "Phase9parent",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("PNB lookup does not inherit parent blockers", result.stderr)
            self.assertIn("phase9child --blockers phase9blocker", result.stderr)

    def test_structured_toml_add_commands_write_expected_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree_root = Path(tmp)
            app_dir = _copy_matcher_tree(tree_root)
            live_app_dir = Path(__file__).resolve().parents[2]
            fixture_spec = contract_spec_by_name("matcher_regression_cases", tree_root=tree_root)
            fixtures = load_contract_source(fixture_spec)
            fixtures.append({
                "id": "phase9guard_negative",
                "policy_ref": "policy_phase9guard_guard",
                "source_ref": "manual:policy_phase9guard_phase9blocked",
                "recipe_name": "Synthetic Phase 9 Guard",
                "ingredients": ["1 dl phase9guard"],
                "offer": {"name": "Phase9blocked", "category": "pantry"},
                "expected": 0,
                "expected_matches": [],
            })
            write_contract_source(fixture_spec, fixtures)
            model_checks_file = app_dir / "support_checks" / "run_matcher_rule_model_checks.py"
            model_checks_before = model_checks_file.read_text(encoding="utf-8")
            count_before_match = re.search(
                r'check\("registered no-match policy count", len\(NO_MATCH_POLICIES\) == (\d+)\)',
                model_checks_before,
            )
            self.assertIsNotNone(count_before_match)
            count_before = int(count_before_match.group(1))

            no_match = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "no-match-policy",
                    "phase9guard",
                    "--ingredient-patterns",
                    r"\bphase9guard\b",
                    "--blocked-offer-patterns",
                    r"\bphase9blocked\b",
                    "--reason",
                    "Synthetic Phase 9 guard.",
                    "--fixture-refs",
                    "phase9guard_negative",
                    "--negative-ingredient",
                    "1 dl phase9guard",
                    "--negative-offer",
                    "Phase9blocked",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(no_match.returncode, 0, no_match.stderr + no_match.stdout)
            self.assertIn("policy id: policy_phase9guard_guard", no_match.stdout)
            self.assertIn("model guard synced", no_match.stdout)
            self.assertIn("generated match() sanity is fast-path/canonical smoke proof", no_match.stderr)
            self.assertIn("regen alone is not enough", no_match.stderr)

            auto_no_match = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "no-match-policy",
                    "phase9auto",
                    "--ingredient-patterns",
                    r"\bphase9auto\b",
                    "--blocked-offer-keywords",
                    "phase9blocked",
                    "--reason",
                    "Synthetic Phase 9 auto guard.",
                    "--negative-ingredient",
                    "1 dl phase9auto",
                    "--negative-offer",
                    "Phase9blocked",
                    "--policy-id",
                    "policy_phase9auto_not_blocked",
                    "--auto-fixture",
                    "--auto-inventory",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(auto_no_match.returncode, 0, auto_no_match.stderr + auto_no_match.stdout)
            self.assertIn("auto fixture created: phase9auto_not_blocked_negative", auto_no_match.stdout)
            self.assertIn("auto inventory: policy_phase9auto_not_blocked", auto_no_match.stdout)
            self.assertIn("model guard synced", auto_no_match.stdout)

            updated_fixtures = load_contract_source(fixture_spec)
            auto_fixture = next(
                row for row in updated_fixtures
                if row["id"] == "phase9auto_not_blocked_negative"
            )
            self.assertEqual(auto_fixture["expected"], 0)
            self.assertEqual(auto_fixture["ingredients"], ["1 dl phase9auto"])
            self.assertEqual(auto_fixture["offer"]["name"], "Phase9blocked")

            inventory_spec = contract_spec_by_name("matcher_rule_inventory", tree_root=tree_root)
            updated_inventory = load_contract_source(inventory_spec)
            auto_inventory = next(
                row for row in updated_inventory
                if row["id"] == "policy_phase9auto_not_blocked"
            )
            self.assertEqual(auto_inventory["kind"], "legacy_no_match_policy")
            self.assertEqual(auto_inventory["fixture_refs"], ["phase9auto_not_blocked_negative"])
            self.assertEqual(
                auto_inventory["adapter_ref"],
                "no_match_policies:policy_phase9auto_not_blocked",
            )

            no_match_policy_file = (
                app_dir
                / "languages"
                / "sv"
                / "ingredient_matching"
                / "term_registry"
                / "entries"
                / "no_match_policy.toml"
            )
            self.assertIn(
                'fixture_refs = ["phase9auto_not_blocked_negative"]',
                no_match_policy_file.read_text(encoding="utf-8"),
            )
            no_match_policy_text = no_match_policy_file.read_text(encoding="utf-8")
            self.assertIn('id = "policy_phase9guard_guard"', no_match_policy_text)
            self.assertNotIn("policy_phase9guard_bphase9blockedb", no_match_policy_text)
            model_checks_after = model_checks_file.read_text(encoding="utf-8")
            self.assertIn('"policy_phase9guard_guard"', model_checks_after)
            self.assertIn('"policy_phase9auto_not_blocked"', model_checks_after)
            self.assertIn(
                f'check("registered no-match policy count", len(NO_MATCH_POLICIES) == {count_before + 2})',
                model_checks_after,
            )

            extraction = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "extraction-helper",
                    "phase9extract",
                    "--side",
                    "product",
                    "--input",
                    "Phase9extract",
                    "--source-refs",
                    "code:extraction:synthetic:1",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(extraction.returncode, 0, extraction.stderr + extraction.stdout)

            entries_dir = app_dir / "languages" / "sv" / "ingredient_matching" / "term_registry" / "entries"
            entries = load_registry_entries(entries_dir=entries_dir, include_local=False)
            policies = build_no_match_policies_export_from_entries(entries)
            self.assertTrue(any(policy.id == "policy_phase9guard_guard" for policy in policies))

            extraction_entry = next(entry for entry in entries if entry.entry_id == "sv-se.family.phase9extract")
            coverage_rows = extraction_entry.language_payload["coverage"]
            self.assertEqual(
                {row["layer_role"] for row in coverage_rows},
                {"hardcoded_keyword_output:extract_keywords_from_product"},
            )
            merge_ingredient = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "extraction-helper",
                    "phase9extract",
                    "--side",
                    "ingredient",
                    "--input",
                    "Phase9extract",
                    "--source-refs",
                    "code:extraction:synthetic:2",
                    "--tree-root",
                    str(tree_root),
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(merge_ingredient.returncode, 0, merge_ingredient.stderr + merge_ingredient.stdout)

            entries = load_registry_entries(entries_dir=entries_dir, include_local=False)
            extraction_entry = next(entry for entry in entries if entry.entry_id == "sv-se.family.phase9extract")
            helper_text = (entries_dir / "extraction_helper.toml").read_text(encoding="utf-8")
            helper_block = helper_text[helper_text.find('entry_id = "sv-se.family.phase9extract"') :]
            helper_block = helper_block[: helper_block.find("[[entries]]", 1)]
            self.assertIn('ingredient_terms = ["phase9extract"]', helper_block)
            self.assertIn('offer_terms = ["phase9extract"]', helper_block)
            self.assertEqual(
                {row["layer_role"] for row in extraction_entry.language_payload["coverage"]},
                {
                    "hardcoded_keyword_output:extract_keywords_from_ingredient",
                    "hardcoded_keyword_output:extract_keywords_from_product",
                },
            )
            refresh_product = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cli.dm",
                    "matcher",
                    "add",
                    "extraction-helper",
                    "phase9extract",
                    "--side",
                    "product",
                    "--input",
                    "Phase9extract",
                    "--source-refs",
                    "code:extraction:synthetic:3",
                    "--tree-root",
                    str(tree_root),
                    "--replace-existing",
                    "--no-run-gates",
                ],
                cwd=live_app_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(refresh_product.returncode, 0, refresh_product.stderr + refresh_product.stdout)
            entries = load_registry_entries(entries_dir=entries_dir, include_local=False)
            extraction_entry = next(entry for entry in entries if entry.entry_id == "sv-se.family.phase9extract")
            self.assertEqual(
                {row["layer_role"] for row in extraction_entry.language_payload["coverage"]},
                {
                    "hardcoded_keyword_output:extract_keywords_from_ingredient",
                    "hardcoded_keyword_output:extract_keywords_from_product",
                },
            )

    def test_dm_matcher_guide_lists_all_toml_add_surfaces(self) -> None:
        live_app_dir = Path(__file__).resolve().parents[2]
        help_result = subprocess.run(
            [sys.executable, "-m", "cli.dm", "matcher", "add", "--help"],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        guide_result = subprocess.run(
            [sys.executable, "-m", "cli.dm", "matcher", "guide", "--list"],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(help_result.returncode, 0, help_result.stderr + help_result.stdout)
        self.assertEqual(guide_result.returncode, 0, guide_result.stderr + guide_result.stdout)
        family_result = subprocess.run(
            [sys.executable, "-m", "cli.dm", "matcher", "guide", "family"],
            cwd=live_app_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(family_result.returncode, 0, family_result.stderr + family_result.stdout)
        self.assertIn("Mutually interchangeable family members", family_result.stdout)
        self.assertIn("use ingredient-parent", family_result.stdout)
        for command in (
            "ingredient-parent",
            "offer-extra-keyword",
            "ingredient-routing-parent",
            "parent-match-only",
            "recipe-routing-helper",
            "no-match-policy",
            "extraction-helper",
        ):
            self.assertIn(command, help_result.stdout)
            self.assertIn(f"{command}: supported by dm matcher add", guide_result.stdout)


if __name__ == "__main__":
    unittest.main()
