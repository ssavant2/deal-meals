# Matcher Contract JSON Authority Audit

Generated: 2026-05-17

This audit is the L3-C gate for making matcher contract JSON derived
from TOML sources. If any blocking readers exist, the JSON-as-derived
migration is vetoed until those consumers are migrated first.

Decision: VETOED

## Summary

| Classification | Count |
|---|---:|
| blocking_reader | 8 |
| documentation | 35 |
| planning_doc | 11 |
| python_reference | 37 |
| reference | 3894 |

## Blocking Readers

These Python consumers still read the JSON contracts directly. The
JSON files therefore remain authored source-of-truth for now.

- `app/support_checks/generate_matcher_registry_coverage.py:19` — `DEFAULT_FIXTURE_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `app/support_checks/generate_matcher_registry_coverage.py:20` — `DEFAULT_INVENTORY_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `app/support_checks/run_matcher_change_preflight.py:46` — `DEFAULT_FIXTURE_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `app/support_checks/run_matcher_change_preflight.py:47` — `DEFAULT_INVENTORY_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `app/support_checks/run_term_registry_contract_checks.py:52` — `DEFAULT_FIXTURE_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `app/support_checks/run_term_registry_contract_checks.py:53` — `DEFAULT_INVENTORY_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `app/cli/dm.py:25` — `DEFAULT_FIXTURE_FILE = SV_DIR / "matcher_contracts" / "matcher_regression_cases.json"`
- `app/cli/dm.py:26` — `DEFAULT_INVENTORY_FILE = SV_DIR / "matcher_contracts" / "matcher_rule_inventory.json"`

## All References

- `documentation` `docs/HOW_TO_ADD_COUNTRIES.md:173` — `- `matcher_regression_cases.json` — accepted positive and relevant negative`
- `documentation` `docs/HOW_TO_ADD_COUNTRIES.md:175` — `- `matcher_rule_inventory.json` — rule/source ownership, fixture refs, line refs,`
- `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:119` — `- At least one entry in `matcher_regression_cases.json` (positive + negative) for each`
- `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:121` — `- A `matcher_rule_inventory.json` entry per new mechanism.`
- `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:923` — `6. Add new regression cases in `matcher_regression_cases.json` (positive + negative per keyword).`
- `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:924` — `7. Add `matcher_rule_inventory.json` entry for `flavored_vs_plain`.`
- `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:949` — `6. Add `matcher_regression_cases.json` entries for each keyword.`
- `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:950` — `7. Add or update `matcher_rule_inventory.json` for `cooked_vs_raw`.`
- `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:970` — `6. Add or update `matcher_rule_inventory.json` for `ingredient_as_flavor`.`
- `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:1000` — `Any new regression case must be added to `matcher_regression_cases.json` BEFORE committing.`
- `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:1093` — `| `app/languages/sv/matcher_contracts/matcher_regression_cases.json` | Add positive + negative fixture for every new keyword | A, B, C |`
- `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:1094` — `| `app/languages/sv/matcher_contracts/matcher_rule_inventory.json` | Add entry per new mechanism | A, B, C |`
- `planning_doc` `docs/MATCHER_RULE_CHANGE_FLOW_IMPROVEMENTS.md:58` — `2. Adding a new fixture to `matcher_regression_cases.json` does not require`
- `planning_doc` `docs/MATCHER_RULE_CHANGE_FLOW_IMPROVEMENTS.md:207` — ``matcher_regression_cases.json` and `matcher_rule_inventory.json` and`
- `planning_doc` `docs/MATCHER_RULE_CHANGE_FLOW_IMPROVEMENTS.md:339` — `Currently `matcher_regression_cases.json` and `matcher_rule_inventory.json``
- `planning_doc` `docs/MATCHER_RULE_CHANGE_FLOW_IMPROVEMENTS.md:585` — `**What changes:** `matcher_regression_cases.json` and`
- `planning_doc` `docs/MATCHER_RULE_CHANGE_FLOW_IMPROVEMENTS.md:586` — ``matcher_rule_inventory.json` become generated from TOML source files.`
- `planning_doc` `docs/MATCHER_RULE_CHANGE_FLOW_IMPROVEMENTS.md:715` — `- L2-A auto-emit coverage TOML from `matcher_regression_cases.json` and`
- `planning_doc` `docs/MATCHER_RULE_CHANGE_FLOW_IMPROVEMENTS.md:716` — ``matcher_rule_inventory.json`.`
- `planning_doc` `docs/MATCHER_RULE_CHANGE_FLOW_IMPROVEMENTS.md:879` — `3. Inject a corresponding fixture in `matcher_regression_cases.json`, one`
- `planning_doc` `docs/MATCHER_RULE_CHANGE_FLOW_IMPROVEMENTS.md:880` — `inventory entry in `matcher_rule_inventory.json`, and the current`
- `documentation` `docs/TESTING.md:140` — `- `app/languages/sv/matcher_contracts/matcher_regression_cases.json``
- `documentation` `docs/TESTING.md:141` — `- `app/languages/sv/matcher_contracts/matcher_rule_inventory.json``
- `documentation` `docs/TESTING.md:217` — `- `matcher_regression_cases.json` is the main matcher parity corpus.`
- `documentation` `docs/TESTING.md:218` — `- `matcher_rule_inventory.json` is the rule/source inventory checked by`
- `planning_doc` `docs/MATCHER_REGISTRY_ARCHITECTURE.md:8` — `- `app/languages/sv/matcher_contracts/matcher_regression_cases.json` stores`
- `planning_doc` `docs/MATCHER_REGISTRY_ARCHITECTURE.md:10` — `- `app/languages/sv/matcher_contracts/matcher_rule_inventory.json` stores the`
- `documentation` `app/tests/batch_review_questions.md:1361` — ``app/languages/sv/matcher_contracts/matcher_regression_cases.json` and`
- `documentation` `app/tests/batch_review_questions.md:1362` — ``app/languages/sv/matcher_contracts/matcher_rule_inventory.json`.`
- `python_reference` `app/support_checks/run_matcher_change_gates.py:69` — `return _app_dir_for_tree_root(args.tree_root) / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `python_reference` `app/support_checks/run_matcher_change_gates.py:73` — `return _app_dir_for_tree_root(args.tree_root) / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `python_reference` `app/support_checks/run_matcher_change_gates.py:206` — `"app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `python_reference` `app/support_checks/run_matcher_change_gates.py:210` — `"app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `python_reference` `app/support_checks/run_matcher_change_gates.py:577` — `inventory_file = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `python_reference` `app/support_checks/run_matcher_rule_inventory_checks.py:30` — `APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `blocking_reader` `app/support_checks/generate_matcher_registry_coverage.py:19` — `DEFAULT_FIXTURE_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `blocking_reader` `app/support_checks/generate_matcher_registry_coverage.py:20` — `DEFAULT_INVENTORY_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `python_reference` `app/support_checks/generate_matcher_registry_coverage.py:29` — `"# Source: app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `python_reference` `app/support_checks/generate_matcher_registry_coverage.py:32` — `"# Registry coverage for matcher_regression_cases.json fixtures.",`
- `python_reference` `app/support_checks/generate_matcher_registry_coverage.py:39` — `"# Source: app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `python_reference` `app/support_checks/generate_matcher_registry_coverage.py:42` — `"# Registry coverage for matcher_rule_inventory.json rows.",`
- `python_reference` `app/support_checks/generate_matcher_registry_coverage.py:328` — `fixture_file = fixture_file or app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `python_reference` `app/support_checks/generate_matcher_registry_coverage.py:329` — `inventory_file = inventory_file or app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `blocking_reader` `app/support_checks/run_matcher_change_preflight.py:46` — `DEFAULT_FIXTURE_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `blocking_reader` `app/support_checks/run_matcher_change_preflight.py:47` — `DEFAULT_INVENTORY_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `python_reference` `app/support_checks/run_matcher_change_preflight.py:570` — `fixture_file = fixture_file or app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `python_reference` `app/support_checks/run_matcher_change_preflight.py:571` — `inventory_file = inventory_file or app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `blocking_reader` `app/support_checks/run_term_registry_contract_checks.py:52` — `DEFAULT_FIXTURE_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `blocking_reader` `app/support_checks/run_term_registry_contract_checks.py:53` — `DEFAULT_INVENTORY_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `python_reference` `app/support_checks/run_verified_term_audit.py:56` — `RULE_INVENTORY_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `python_reference` `app/support_checks/run_verified_term_audit.py:57` — `REGRESSION_CASES_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `python_reference` `app/support_checks/refresh_matcher_rule_inventory_line_refs.py:16` — `APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `python_reference` `app/support_checks/run_matcher_layer_fixture_cases.py:31` — `APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `python_reference` `app/support_checks/audit_matcher_contract_json_authority.py:21` — `"matcher_regression_cases.json",`
- `python_reference` `app/support_checks/audit_matcher_contract_json_authority.py:22` — `"matcher_rule_inventory.json",`
- `blocking_reader` `app/cli/dm.py:25` — `DEFAULT_FIXTURE_FILE = SV_DIR / "matcher_contracts" / "matcher_regression_cases.json"`
- `blocking_reader` `app/cli/dm.py:26` — `DEFAULT_INVENTORY_FILE = SV_DIR / "matcher_contracts" / "matcher_rule_inventory.json"`
- `python_reference` `app/cli/dm.py:83` — `fixture_file=app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json",`
- `python_reference` `app/cli/dm.py:84` — `inventory_file=app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json",`
- `python_reference` `app/support_checks/tests/test_rule_change_flow.py:59` — `fixture_file = Path(tmp) / "matcher_regression_cases.json"`
- `python_reference` `app/support_checks/tests/test_rule_change_flow.py:93` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `python_reference` `app/support_checks/tests/test_rule_change_flow.py:125` — `all(issue["file"].endswith("matcher_regression_cases.json") for issue in fixture_issues),`
- `python_reference` `app/support_checks/tests/test_rule_change_flow.py:145` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `python_reference` `app/support_checks/tests/test_rule_change_flow.py:146` — `inventory_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `python_reference` `app/support_checks/tests/test_rule_change_flow.py:184` — `"path": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `python_reference` `app/support_checks/tests/test_rule_change_flow.py:235` — `source_file="app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `python_reference` `app/support_checks/tests/test_rule_change_flow.py:323` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `python_reference` `app/support_checks/tests/test_rule_change_flow.py:324` — `inventory_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `python_reference` `app/languages/sv/ingredient_matching/term_registry/add_term.py:148` — `description="matcher_regression_cases.json positive fixture",`
- `python_reference` `app/languages/sv/ingredient_matching/term_registry/add_term.py:156` — `description="matcher_regression_cases.json negative fixture",`
- `python_reference` `app/languages/sv/ingredient_matching/term_registry/add_term.py:180` — `description=f"matcher_rule_inventory.json {_inventory_role}",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:118` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:139` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:286` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:454` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:475` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:496` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:517` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:559` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:580` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:664` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:685` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:832` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:853` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:874` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:937` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1021` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1084` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1168` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1231` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1336` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1357` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1378` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1399` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1441` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1483` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1525` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1546` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1567` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1630` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1777` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1924` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1966` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2029` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2113` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2239` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2323` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2365` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2428` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2470` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2701` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2806` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2848` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2890` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2932` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2953` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3037` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3058` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3100` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3142` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3163` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3247` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3268` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3310` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3352` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3373` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3394` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3436` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3499` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3583` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3604` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3646` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3688` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3751` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3793` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3856` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3898` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:4024` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:4192` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:4255` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:4486` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:4738` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:4780` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:4906` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:4927` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5137` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5200` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5242` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5263` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5347` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5473` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5536` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5557` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5620` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5641` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5662` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5704` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5725` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5767` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5809` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- ... 3825 additional reference(s)
