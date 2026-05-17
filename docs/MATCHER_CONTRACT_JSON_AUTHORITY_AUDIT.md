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
| documentation | 14 |
| generated_output_reference | 4125 |
| planning_doc | 2 |
| python_reference | 15 |
| reference | 3 |
| test_reference | 49 |

## All References

- `ref` `documentation` `docs/HOW_TO_ADD_COUNTRIES.md:177` — `- `matcher_regression_cases.json` and `matcher_rule_inventory.json` — generated`
- `ref` `documentation` `docs/MATCHER_CONTRACT_TOML_SOURCE_AUDIT.md:21` — `- `app/languages/sv/matcher_contracts/sources/matcher_regression_cases.toml` generates `app/languages/sv/matcher_contracts/matcher_regression_cases.json``
- `ref` `documentation` `docs/MATCHER_CONTRACT_TOML_SOURCE_AUDIT.md:22` — `- `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml` generates `app/languages/sv/matcher_contracts/matcher_rule_inventory.json``
- `ref` `planning_doc` `docs/MATCHER_REGISTRY_ARCHITECTURE.md:13` — `- `app/languages/sv/matcher_contracts/matcher_regression_cases.json` and`
- `ref` `planning_doc` `docs/MATCHER_REGISTRY_ARCHITECTURE.md:14` — ``app/languages/sv/matcher_contracts/matcher_rule_inventory.json` are`
- `ref` `documentation` `docs/MATCHER_RULE_WORKFLOW_STEP2_PLAN.md:45` — `- `app/languages/sv/matcher_contracts/matcher_regression_cases.json``
- `ref` `documentation` `docs/MATCHER_RULE_WORKFLOW_STEP2_PLAN.md:46` — `- `app/languages/sv/matcher_contracts/matcher_rule_inventory.json``
- `ref` `reference` `docs/MATCHER_CONTRACT_TOML_SOURCE_AUDIT.json:13` — `"source_json_path": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `reference` `docs/MATCHER_CONTRACT_TOML_SOURCE_AUDIT.json:25` — `"source_json_path": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `test_reference` `app/tests/batch_review_questions.md:1361` — ``app/languages/sv/matcher_contracts/matcher_regression_cases.json` and`
- `ref` `test_reference` `app/tests/batch_review_questions.md:1362` — ``app/languages/sv/matcher_contracts/matcher_rule_inventory.json`.`
- `ref` `python_reference` `app/support_checks/run_matcher_change_gates.py:198` — `"app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `python_reference` `app/support_checks/run_matcher_change_gates.py:203` — `"app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
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
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:60` — `DEFAULT_FIXTURE_FILE = fixture_contract_path()`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:61` — `DEFAULT_INVENTORY_FILE = inventory_contract_path()`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:67` — `DEFAULT_FIXTURE_FILE.parents[1],`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:82` — `fixtures = load_fixture_contract(DEFAULT_FIXTURE_FILE)`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:83` — `inventory = load_inventory_contract(DEFAULT_INVENTORY_FILE)`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:112` — `fixtures = json.loads(DEFAULT_FIXTURE_FILE.read_text(encoding="utf-8"))`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:123` — `fixture_file = Path(tmp) / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:130` — `inventory_file=DEFAULT_INVENTORY_FILE,`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:146` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:179` — `all(issue["file"].endswith("matcher_regression_cases.json") for issue in fixture_issues),`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:188` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:189` — `inventory_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:230` — `"path": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:282` — `source_file="app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:359` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:360` — `inventory_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:428` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:429` — `inventory_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:565` — `"matcher_regression_cases": len(load_fixture_contract(DEFAULT_FIXTURE_FILE)),`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:566` — `"matcher_rule_inventory": len(load_inventory_contract(DEFAULT_INVENTORY_FILE)),`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:575` — `self.assertFalse((output_dir / "matcher_regression_cases.json").exists())`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:576` — `self.assertFalse((output_dir / "matcher_rule_inventory.json").exists())`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:582` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6` — `source_json_path = "app/languages/sv/matcher_contracts/matcher_rule_inventory.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:5808` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:5908` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:5989` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6008` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6033` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6052` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6077` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6096` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6121` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6140` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6165` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6184` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6209` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6228` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6253` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6272` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6291` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6310` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6329` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6348` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6367` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6386` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6405` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6424` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6443` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6462` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6481` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6500` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6519` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6538` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6557` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6576` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6595` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6614` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6633` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6652` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6671` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6690` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6709` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6728` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6747` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6766` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6785` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6804` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6823` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6842` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6861` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6880` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6899` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6918` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6937` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6956` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6975` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:6994` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7013` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7032` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7051` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7070` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7089` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7108` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7127` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7146` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7165` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7184` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7203` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7222` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7241` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7260` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7279` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7298` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7317` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7336` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7355` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7374` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7393` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7412` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7431` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7450` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7469` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7488` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7507` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7526` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7545` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7564` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7583` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7602` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7621` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7640` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7659` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7678` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7697` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7716` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7735` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7754` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7773` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7792` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7811` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7830` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7849` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7868` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7887` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7906` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7925` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7944` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7963` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:7982` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:8001` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:8020` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:8039` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:8058` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- `ref` `generated_output_reference` `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml:8077` — `path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"`
- ... 4050 additional reference(s)
