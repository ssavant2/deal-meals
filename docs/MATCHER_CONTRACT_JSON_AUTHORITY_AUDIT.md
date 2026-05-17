# Matcher Contract JSON Authority Audit

Generated: 2026-05-17

This audit is the L3-C gate for making matcher contract JSON derived
from TOML sources. If any blocking consumers exist, the JSON-as-derived
migration is vetoed until those consumers are migrated first.

Decision: PASS
Blocker count: 0

## Summary

| Classification | Count |
|---|---:|
| contract_access_api | 2 |
| documentation | 38 |
| generated_output_reference | 4125 |
| planning_doc | 2 |
| python_reference | 15 |
| reference | 3 |
| test_reference | 48 |

## All References

- `ref` `documentation` `docs/HOW_TO_ADD_COUNTRIES.md:173` — `- `matcher_regression_cases.json` — accepted positive and relevant negative`
- `ref` `documentation` `docs/HOW_TO_ADD_COUNTRIES.md:175` — `- `matcher_rule_inventory.json` — rule/source ownership, fixture refs, line refs,`
- `ref` `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:119` — `- At least one entry in `matcher_regression_cases.json` (positive + negative) for each`
- `ref` `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:121` — `- A `matcher_rule_inventory.json` entry per new mechanism.`
- `ref` `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:923` — `6. Add new regression cases in `matcher_regression_cases.json` (positive + negative per keyword).`
- `ref` `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:924` — `7. Add `matcher_rule_inventory.json` entry for `flavored_vs_plain`.`
- `ref` `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:949` — `6. Add `matcher_regression_cases.json` entries for each keyword.`
- `ref` `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:950` — `7. Add or update `matcher_rule_inventory.json` for `cooked_vs_raw`.`
- `ref` `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:970` — `6. Add or update `matcher_rule_inventory.json` for `ingredient_as_flavor`.`
- `ref` `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:1000` — `Any new regression case must be added to `matcher_regression_cases.json` BEFORE committing.`
- `ref` `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:1093` — `| `app/languages/sv/matcher_contracts/matcher_regression_cases.json` | Add positive + negative fixture for every new keyword | A, B, C |`
- `ref` `documentation` `docs/MATCHER_SYSTEMIC_FP_PLAN.md:1094` — `| `app/languages/sv/matcher_contracts/matcher_rule_inventory.json` | Add entry per new mechanism | A, B, C |`
- `ref` `documentation` `docs/MATCHER_CONTRACT_TOML_SOURCE_AUDIT.md:21` — `- `app/languages/sv/matcher_contracts/sources/matcher_regression_cases.toml` from `app/languages/sv/matcher_contracts/matcher_regression_cases.json``
- `ref` `documentation` `docs/MATCHER_CONTRACT_TOML_SOURCE_AUDIT.md:22` — `- `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml` from `app/languages/sv/matcher_contracts/matcher_rule_inventory.json``
- `ref` `documentation` `docs/TESTING.md:140` — `- `app/languages/sv/matcher_contracts/matcher_regression_cases.json``
- `ref` `documentation` `docs/TESTING.md:141` — `- `app/languages/sv/matcher_contracts/matcher_rule_inventory.json``
- `ref` `documentation` `docs/TESTING.md:217` — `- `matcher_regression_cases.json` is the main matcher parity corpus.`
- `ref` `documentation` `docs/TESTING.md:218` — `- `matcher_rule_inventory.json` is the rule/source inventory checked by`
- `ref` `planning_doc` `docs/MATCHER_REGISTRY_ARCHITECTURE.md:8` — `- `app/languages/sv/matcher_contracts/matcher_regression_cases.json` stores`
- `ref` `planning_doc` `docs/MATCHER_REGISTRY_ARCHITECTURE.md:10` — `- `app/languages/sv/matcher_contracts/matcher_rule_inventory.json` stores the`
- `ref` `documentation` `docs/MATCHER_RULE_WORKFLOW_STEP2_PLAN.md:39` — `- `app/languages/sv/matcher_contracts/matcher_regression_cases.json``
- `ref` `documentation` `docs/MATCHER_RULE_WORKFLOW_STEP2_PLAN.md:40` — `- `app/languages/sv/matcher_contracts/matcher_rule_inventory.json``
- `ref` `reference` `docs/MATCHER_CONTRACT_TOML_SOURCE_AUDIT.json:13` — `"source_json_path": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `reference` `docs/MATCHER_CONTRACT_TOML_SOURCE_AUDIT.json:25` — `"source_json_path": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `test_reference` `app/tests/batch_review_questions.md:1361` — ``app/languages/sv/matcher_contracts/matcher_regression_cases.json` and`
- `ref` `test_reference` `app/tests/batch_review_questions.md:1362` — ``app/languages/sv/matcher_contracts/matcher_rule_inventory.json`.`
- `ref` `python_reference` `app/support_checks/run_matcher_change_gates.py:197` — `"app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `python_reference` `app/support_checks/run_matcher_change_gates.py:201` — `"app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `contract_access_api` `app/support_checks/matcher_contracts.py:15` — `FIXTURE_CONTRACT_FILENAME = "matcher_regression_cases.json"`
- `ref` `contract_access_api` `app/support_checks/matcher_contracts.py:16` — `INVENTORY_CONTRACT_FILENAME = "matcher_rule_inventory.json"`
- `ref` `python_reference` `app/support_checks/generate_matcher_registry_coverage.py:35` — `"# Source: app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `python_reference` `app/support_checks/generate_matcher_registry_coverage.py:38` — `"# Registry coverage for matcher_regression_cases.json fixtures.",`
- `ref` `python_reference` `app/support_checks/generate_matcher_registry_coverage.py:45` — `"# Source: app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `python_reference` `app/support_checks/generate_matcher_registry_coverage.py:48` — `"# Registry coverage for matcher_rule_inventory.json rows.",`
- `ref` `python_reference` `app/support_checks/audit_matcher_contract_json_authority.py:23` — `"matcher_regression_cases.json",`
- `ref` `python_reference` `app/support_checks/audit_matcher_contract_json_authority.py:24` — `"matcher_rule_inventory.json",`
- `ref` `python_reference` `app/support_checks/audit_matcher_contract_json_authority.py:27` — `"DEFAULT_FIXTURE_FILE",`
- `ref` `python_reference` `app/support_checks/audit_matcher_contract_json_authority.py:28` — `"DEFAULT_INVENTORY_FILE",`
- `ref` `python_reference` `app/support_checks/audit_matcher_contract_json_authority.py:29` — `"RULE_INVENTORY_FILE",`
- `ref` `python_reference` `app/support_checks/audit_matcher_contract_json_authority.py:30` — `"REGRESSION_CASES_FILE",`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:53` — `DEFAULT_FIXTURE_FILE = fixture_contract_path()`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:54` — `DEFAULT_INVENTORY_FILE = inventory_contract_path()`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:60` — `DEFAULT_FIXTURE_FILE.parents[1],`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:75` — `fixtures = load_fixture_contract(DEFAULT_FIXTURE_FILE)`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:76` — `inventory = load_inventory_contract(DEFAULT_INVENTORY_FILE)`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:105` — `fixtures = json.loads(DEFAULT_FIXTURE_FILE.read_text(encoding="utf-8"))`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:116` — `fixture_file = Path(tmp) / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:123` — `inventory_file=DEFAULT_INVENTORY_FILE,`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:139` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:172` — `all(issue["file"].endswith("matcher_regression_cases.json") for issue in fixture_issues),`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:181` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:182` — `inventory_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:220` — `"path": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:276` — `source_file="app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:353` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:354` — `inventory_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:422` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:423` — `inventory_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:559` — `"matcher_regression_cases": len(load_fixture_contract(DEFAULT_FIXTURE_FILE)),`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:560` — `"matcher_rule_inventory": len(load_inventory_contract(DEFAULT_INVENTORY_FILE)),`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:569` — `self.assertFalse((output_dir / "matcher_regression_cases.json").exists())`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:570` — `self.assertFalse((output_dir / "matcher_rule_inventory.json").exists())`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6` — `source_json_path = "app/languages/sv/matcher_contracts/matcher_rule_inventory.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:5809` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:5909` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:5990` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6009` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6034` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6053` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6078` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6097` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6122` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6141` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6166` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6185` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6210` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6229` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6254` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6273` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6292` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6311` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6330` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6349` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6368` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6387` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6406` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6425` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6444` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6463` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6482` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6501` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6520` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6539` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6558` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6577` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6596` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6615` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6634` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6653` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6672` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6691` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6710` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6729` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6748` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6767` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6786` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6805` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6824` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6843` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6862` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6881` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6900` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6919` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6938` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6957` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6976` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6995` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7014` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7033` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7052` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7071` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7090` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7109` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7128` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7147` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7166` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7185` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7204` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7223` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7242` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7261` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7280` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7299` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7318` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7337` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7356` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7375` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7394` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7413` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7432` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7451` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7470` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7489` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7508` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7527` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7546` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7565` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7584` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7603` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7622` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7641` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7660` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7679` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7698` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7717` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7736` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7755` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7774` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7793` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7812` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- ... 4073 additional reference(s)
