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
| documentation | 33 |
| generated_output_reference | 3894 |
| planning_doc | 2 |
| python_reference | 15 |
| test_reference | 44 |

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
- `ref` `documentation` `docs/TESTING.md:140` — `- `app/languages/sv/matcher_contracts/matcher_regression_cases.json``
- `ref` `documentation` `docs/TESTING.md:141` — `- `app/languages/sv/matcher_contracts/matcher_rule_inventory.json``
- `ref` `documentation` `docs/TESTING.md:217` — `- `matcher_regression_cases.json` is the main matcher parity corpus.`
- `ref` `documentation` `docs/TESTING.md:218` — `- `matcher_rule_inventory.json` is the rule/source inventory checked by`
- `ref` `planning_doc` `docs/MATCHER_REGISTRY_ARCHITECTURE.md:8` — `- `app/languages/sv/matcher_contracts/matcher_regression_cases.json` stores`
- `ref` `planning_doc` `docs/MATCHER_REGISTRY_ARCHITECTURE.md:10` — `- `app/languages/sv/matcher_contracts/matcher_rule_inventory.json` stores the`
- `ref` `documentation` `docs/MATCHER_RULE_WORKFLOW_STEP2_PLAN.md:37` — `- `app/languages/sv/matcher_contracts/matcher_regression_cases.json``
- `ref` `documentation` `docs/MATCHER_RULE_WORKFLOW_STEP2_PLAN.md:38` — `- `app/languages/sv/matcher_contracts/matcher_rule_inventory.json``
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
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:49` — `DEFAULT_FIXTURE_FILE = fixture_contract_path()`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:50` — `DEFAULT_INVENTORY_FILE = inventory_contract_path()`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:56` — `DEFAULT_FIXTURE_FILE.parents[1],`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:71` — `fixtures = load_fixture_contract(DEFAULT_FIXTURE_FILE)`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:72` — `inventory = load_inventory_contract(DEFAULT_INVENTORY_FILE)`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:101` — `fixtures = json.loads(DEFAULT_FIXTURE_FILE.read_text(encoding="utf-8"))`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:112` — `fixture_file = Path(tmp) / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:119` — `inventory_file=DEFAULT_INVENTORY_FILE,`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:135` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:167` — `all(issue["file"].endswith("matcher_regression_cases.json") for issue in fixture_issues),`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:176` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:177` — `inventory_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:215` — `"path": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:266` — `source_file="app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:343` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:344` — `inventory_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:404` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:405` — `inventory_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `ref` `python_reference` `app/languages/sv/ingredient_matching/term_registry/add_term.py:148` — `description="matcher_regression_cases.json positive fixture",`
- `ref` `python_reference` `app/languages/sv/ingredient_matching/term_registry/add_term.py:156` — `description="matcher_regression_cases.json negative fixture",`
- `ref` `python_reference` `app/languages/sv/ingredient_matching/term_registry/add_term.py:180` — `description=f"matcher_rule_inventory.json {_inventory_role}",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:118` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:139` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:286` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:454` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:475` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:496` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:517` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:559` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:580` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:664` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:685` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:832` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:853` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:874` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:937` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1021` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1084` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1168` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1231` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1336` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1357` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1378` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1399` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1441` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1483` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1525` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1546` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1567` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1630` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1777` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1924` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:1966` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2029` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2113` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2239` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2323` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2365` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2428` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2470` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2701` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2806` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2848` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2890` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2932` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:2953` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3037` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3058` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3100` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3142` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3163` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3247` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3268` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3310` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3352` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3373` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3394` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3436` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3499` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3583` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3604` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3646` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3688` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3751` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3793` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3856` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:3898` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:4024` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:4192` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:4255` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:4486` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:4738` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:4780` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:4906` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:4927` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5137` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5200` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5242` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5263` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5347` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5473` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5536` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5557` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5620` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5641` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5662` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5704` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5725` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5767` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5809` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5830` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5872` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:5977` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:6040` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:6061` — `"source_file": "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:6103` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:6145` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:6166` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:6208` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:6229` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:6271` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:6355` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:6397` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `generated_output_reference` `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json:6439` — `"source_file": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- ... 3830 additional reference(s)
