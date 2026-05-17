# Matcher Contract JSON Authority Audit

Generated: 2026-05-17

This audit is the L3-C gate for making matcher contract JSON derived
from TOML sources. If any blocking consumers exist, the JSON-as-derived
migration is vetoed until those consumers are migrated first.

Decision: VETOED
Blocker baseline count: 46

## Summary

| Classification | Count |
|---|---:|
| blocking_cli_default_path | 9 |
| blocking_default_path | 19 |
| blocking_imported_default_path | 8 |
| blocking_path_resolver | 2 |
| blocking_reader | 8 |
| documentation | 33 |
| generated_output_reference | 3894 |
| planning_doc | 2 |
| python_reference | 21 |
| test_reference | 42 |

## Blocking Consumers

These Python consumers still read, resolve, or import default paths
for the JSON contracts directly. The JSON files therefore remain
authored source-of-truth for now.

- `app/support_checks/run_matcher_change_gates.py:69` — `blocking_path_resolver`; owner: `support_checks`; consumer: `path_resolver`
  - text: `return _app_dir_for_tree_root(args.tree_root) / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
  - migration: Move fixture/inventory path construction behind app/support_checks/matcher_contracts.py.
- `app/support_checks/run_matcher_change_gates.py:73` — `blocking_path_resolver`; owner: `support_checks`; consumer: `path_resolver`
  - text: `return _app_dir_for_tree_root(args.tree_root) / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
  - migration: Move fixture/inventory path construction behind app/support_checks/matcher_contracts.py.
- `app/support_checks/run_matcher_rule_inventory_checks.py:20` — `blocking_imported_default_path`; owner: `support_checks`; consumer: `imported_default_path`
  - text: `DEFAULT_FIXTURE_FILE,`
  - migration: Import contract paths/loaders from app/support_checks/matcher_contracts.py instead of another consumer module.
- `app/support_checks/run_matcher_rule_inventory_checks.py:29` — `blocking_default_path`; owner: `support_checks`; consumer: `default_path`
  - text: `DEFAULT_INVENTORY_FILE = (`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_matcher_rule_inventory_checks.py:408` — `blocking_cli_default_path`; owner: `support_checks`; consumer: `cli_default`
  - text: `parser.add_argument("--inventory-file", default=str(DEFAULT_INVENTORY_FILE))`
  - migration: Resolve CLI/parser defaults through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_matcher_rule_inventory_checks.py:409` — `blocking_cli_default_path`; owner: `support_checks`; consumer: `cli_default`
  - text: `parser.add_argument("--fixture-file", default=str(DEFAULT_FIXTURE_FILE))`
  - migration: Resolve CLI/parser defaults through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_term_registry_guard_bridge_checks.py:47` — `blocking_imported_default_path`; owner: `support_checks`; consumer: `imported_default_path`
  - text: `DEFAULT_FIXTURE_FILE,`
  - migration: Import contract paths/loaders from app/support_checks/matcher_contracts.py instead of another consumer module.
- `app/support_checks/run_term_registry_guard_bridge_checks.py:52` — `blocking_imported_default_path`; owner: `support_checks`; consumer: `imported_default_path`
  - text: `DEFAULT_INVENTORY_FILE,`
  - migration: Import contract paths/loaders from app/support_checks/matcher_contracts.py instead of another consumer module.
- `app/support_checks/run_term_registry_guard_bridge_checks.py:589` — `blocking_cli_default_path`; owner: `support_checks`; consumer: `cli_default`
  - text: `parser.add_argument("--fixture-file", default=str(DEFAULT_FIXTURE_FILE))`
  - migration: Resolve CLI/parser defaults through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_term_registry_guard_bridge_checks.py:590` — `blocking_cli_default_path`; owner: `support_checks`; consumer: `cli_default`
  - text: `parser.add_argument("--inventory-file", default=str(DEFAULT_INVENTORY_FILE))`
  - migration: Resolve CLI/parser defaults through app/support_checks/matcher_contracts.py.
- `app/support_checks/generate_matcher_registry_coverage.py:19` — `blocking_default_path`; owner: `support_checks`; consumer: `default_path`
  - text: `DEFAULT_FIXTURE_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/generate_matcher_registry_coverage.py:20` — `blocking_default_path`; owner: `support_checks`; consumer: `default_path`
  - text: `DEFAULT_INVENTORY_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/generate_matcher_registry_coverage.py:328` — `blocking_default_path`; owner: `support_checks`; consumer: `default_path`
  - text: `fixture_file = fixture_file or app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/generate_matcher_registry_coverage.py:329` — `blocking_default_path`; owner: `support_checks`; consumer: `default_path`
  - text: `inventory_file = inventory_file or app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_matcher_change_preflight.py:46` — `blocking_default_path`; owner: `support_checks`; consumer: `default_path`
  - text: `DEFAULT_FIXTURE_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_matcher_change_preflight.py:47` — `blocking_default_path`; owner: `support_checks`; consumer: `default_path`
  - text: `DEFAULT_INVENTORY_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_matcher_change_preflight.py:570` — `blocking_default_path`; owner: `support_checks`; consumer: `default_path`
  - text: `fixture_file = fixture_file or app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_matcher_change_preflight.py:571` — `blocking_default_path`; owner: `support_checks`; consumer: `default_path`
  - text: `inventory_file = inventory_file or app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_matcher_layer_parity_checks.py:14` — `blocking_imported_default_path`; owner: `support_checks`; consumer: `imported_default_path`
  - text: `from support_checks.run_matcher_layer_parity import DEFAULT_FIXTURE_FILE, run_parity  # noqa: E402`
  - migration: Import contract paths/loaders from app/support_checks/matcher_contracts.py instead of another consumer module.
- `app/support_checks/run_matcher_layer_parity_checks.py:24` — `blocking_reader`; owner: `support_checks`; consumer: `reader`
  - text: `fixture_payloads = _load_fixture_payload(Path(DEFAULT_FIXTURE_FILE))`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_matcher_rule_model_checks.py:34` — `blocking_imported_default_path`; owner: `support_checks`; consumer: `imported_default_path`
  - text: `DEFAULT_FIXTURE_FILE,`
  - migration: Import contract paths/loaders from app/support_checks/matcher_contracts.py instead of another consumer module.
- `app/support_checks/run_matcher_rule_model_checks.py:41` — `blocking_imported_default_path`; owner: `support_checks`; consumer: `imported_default_path`
  - text: `DEFAULT_INVENTORY_FILE,`
  - migration: Import contract paths/loaders from app/support_checks/matcher_contracts.py instead of another consumer module.
- `app/support_checks/run_matcher_rule_model_checks.py:64` — `blocking_cli_default_path`; owner: `support_checks`; consumer: `cli_default`
  - text: `parser.add_argument("--fixture-file", default=str(DEFAULT_FIXTURE_FILE))`
  - migration: Resolve CLI/parser defaults through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_matcher_rule_model_checks.py:65` — `blocking_cli_default_path`; owner: `support_checks`; consumer: `cli_default`
  - text: `parser.add_argument("--inventory-file", default=str(DEFAULT_INVENTORY_FILE))`
  - migration: Resolve CLI/parser defaults through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_term_registry_contract_checks.py:52` — `blocking_default_path`; owner: `support_checks`; consumer: `default_path`
  - text: `DEFAULT_FIXTURE_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_term_registry_contract_checks.py:53` — `blocking_default_path`; owner: `support_checks`; consumer: `default_path`
  - text: `DEFAULT_INVENTORY_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_term_registry_contract_checks.py:517` — `blocking_reader`; owner: `support_checks`; consumer: `reader`
  - text: `fixture_payloads = _load_json(DEFAULT_FIXTURE_FILE)`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_term_registry_contract_checks.py:518` — `blocking_reader`; owner: `support_checks`; consumer: `reader`
  - text: `inventory_payloads = _load_json(DEFAULT_INVENTORY_FILE)`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_matcher_layer_fixture_schema_checks.py:15` — `blocking_imported_default_path`; owner: `support_checks`; consumer: `imported_default_path`
  - text: `DEFAULT_FIXTURE_FILE,`
  - migration: Import contract paths/loaders from app/support_checks/matcher_contracts.py instead of another consumer module.
- `app/support_checks/run_matcher_layer_fixture_schema_checks.py:54` — `blocking_reader`; owner: `support_checks`; consumer: `reader`
  - text: `fixture_payloads = _load_fixture_payload(Path(DEFAULT_FIXTURE_FILE))`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_verified_term_audit.py:56` — `blocking_default_path`; owner: `support_checks`; consumer: `default_path`
  - text: `RULE_INVENTORY_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_verified_term_audit.py:57` — `blocking_default_path`; owner: `support_checks`; consumer: `default_path`
  - text: `REGRESSION_CASES_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_verified_term_audit.py:317` — `blocking_default_path`; owner: `support_checks`; consumer: `default_path`
  - text: `rel_path = _repo_rel(RULE_INVENTORY_FILE)`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_verified_term_audit.py:318` — `blocking_reader`; owner: `support_checks`; consumer: `reader`
  - text: `for index, entry in enumerate(_load_json_list(RULE_INVENTORY_FILE), start=1):`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_verified_term_audit.py:346` — `blocking_default_path`; owner: `support_checks`; consumer: `default_path`
  - text: `rel_path = _repo_rel(REGRESSION_CASES_FILE)`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_verified_term_audit.py:347` — `blocking_reader`; owner: `support_checks`; consumer: `reader`
  - text: `for case in _load_json_list(REGRESSION_CASES_FILE):`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_verified_term_audit.py:785` — `blocking_reader`; owner: `support_checks`; consumer: `reader`
  - text: `return {str(case["id"]) for case in _load_json_list(REGRESSION_CASES_FILE)}`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_verified_term_audit.py:789` — `blocking_reader`; owner: `support_checks`; consumer: `reader`
  - text: `return {str(case["id"]): case for case in _load_json_list(REGRESSION_CASES_FILE)}`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/refresh_matcher_rule_inventory_line_refs.py:15` — `blocking_default_path`; owner: `support_checks`; consumer: `default_path`
  - text: `DEFAULT_INVENTORY_FILE = (`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/refresh_matcher_rule_inventory_line_refs.py:146` — `blocking_cli_default_path`; owner: `support_checks`; consumer: `cli_default`
  - text: `parser.add_argument("--inventory-file", type=Path, default=DEFAULT_INVENTORY_FILE)`
  - migration: Resolve CLI/parser defaults through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_matcher_layer_parity.py:37` — `blocking_imported_default_path`; owner: `support_checks`; consumer: `imported_default_path`
  - text: `DEFAULT_FIXTURE_FILE,`
  - migration: Import contract paths/loaders from app/support_checks/matcher_contracts.py instead of another consumer module.
- `app/support_checks/run_matcher_layer_parity.py:493` — `blocking_cli_default_path`; owner: `support_checks`; consumer: `cli_default`
  - text: `parser.add_argument("--fixture-file", default=str(DEFAULT_FIXTURE_FILE))`
  - migration: Resolve CLI/parser defaults through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_matcher_layer_fixture_cases.py:30` — `blocking_default_path`; owner: `support_checks`; consumer: `default_path`
  - text: `DEFAULT_FIXTURE_FILE = (`
  - migration: Load and write matcher contract JSON through app/support_checks/matcher_contracts.py.
- `app/support_checks/run_matcher_layer_fixture_cases.py:397` — `blocking_cli_default_path`; owner: `support_checks`; consumer: `cli_default`
  - text: `parser.add_argument("--fixture-file", default=str(DEFAULT_FIXTURE_FILE))`
  - migration: Resolve CLI/parser defaults through app/support_checks/matcher_contracts.py.
- `app/cli/dm.py:25` — `blocking_default_path`; owner: `cli`; consumer: `default_path`
  - text: `DEFAULT_FIXTURE_FILE = SV_DIR / "matcher_contracts" / "matcher_regression_cases.json"`
  - migration: Use app/support_checks/matcher_contracts.py for path resolution and JSON read/write helpers.
- `app/cli/dm.py:26` — `blocking_default_path`; owner: `cli`; consumer: `default_path`
  - text: `DEFAULT_INVENTORY_FILE = SV_DIR / "matcher_contracts" / "matcher_rule_inventory.json"`
  - migration: Use app/support_checks/matcher_contracts.py for path resolution and JSON read/write helpers.

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
- `BLOCKER` `blocking_path_resolver` `app/support_checks/run_matcher_change_gates.py:69` — `return _app_dir_for_tree_root(args.tree_root) / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `BLOCKER` `blocking_path_resolver` `app/support_checks/run_matcher_change_gates.py:73` — `return _app_dir_for_tree_root(args.tree_root) / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `ref` `python_reference` `app/support_checks/run_matcher_change_gates.py:206` — `"app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `python_reference` `app/support_checks/run_matcher_change_gates.py:210` — `"app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `python_reference` `app/support_checks/run_matcher_change_gates.py:577` — `inventory_file = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `BLOCKER` `blocking_imported_default_path` `app/support_checks/run_matcher_rule_inventory_checks.py:20` — `DEFAULT_FIXTURE_FILE,`
- `BLOCKER` `blocking_default_path` `app/support_checks/run_matcher_rule_inventory_checks.py:29` — `DEFAULT_INVENTORY_FILE = (`
- `ref` `python_reference` `app/support_checks/run_matcher_rule_inventory_checks.py:30` — `APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `BLOCKER` `blocking_cli_default_path` `app/support_checks/run_matcher_rule_inventory_checks.py:408` — `parser.add_argument("--inventory-file", default=str(DEFAULT_INVENTORY_FILE))`
- `BLOCKER` `blocking_cli_default_path` `app/support_checks/run_matcher_rule_inventory_checks.py:409` — `parser.add_argument("--fixture-file", default=str(DEFAULT_FIXTURE_FILE))`
- `BLOCKER` `blocking_imported_default_path` `app/support_checks/run_term_registry_guard_bridge_checks.py:47` — `DEFAULT_FIXTURE_FILE,`
- `BLOCKER` `blocking_imported_default_path` `app/support_checks/run_term_registry_guard_bridge_checks.py:52` — `DEFAULT_INVENTORY_FILE,`
- `BLOCKER` `blocking_cli_default_path` `app/support_checks/run_term_registry_guard_bridge_checks.py:589` — `parser.add_argument("--fixture-file", default=str(DEFAULT_FIXTURE_FILE))`
- `BLOCKER` `blocking_cli_default_path` `app/support_checks/run_term_registry_guard_bridge_checks.py:590` — `parser.add_argument("--inventory-file", default=str(DEFAULT_INVENTORY_FILE))`
- `BLOCKER` `blocking_default_path` `app/support_checks/generate_matcher_registry_coverage.py:19` — `DEFAULT_FIXTURE_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `BLOCKER` `blocking_default_path` `app/support_checks/generate_matcher_registry_coverage.py:20` — `DEFAULT_INVENTORY_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `ref` `python_reference` `app/support_checks/generate_matcher_registry_coverage.py:29` — `"# Source: app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `python_reference` `app/support_checks/generate_matcher_registry_coverage.py:32` — `"# Registry coverage for matcher_regression_cases.json fixtures.",`
- `ref` `python_reference` `app/support_checks/generate_matcher_registry_coverage.py:39` — `"# Source: app/languages/sv/matcher_contracts/matcher_rule_inventory.json",`
- `ref` `python_reference` `app/support_checks/generate_matcher_registry_coverage.py:42` — `"# Registry coverage for matcher_rule_inventory.json rows.",`
- `BLOCKER` `blocking_default_path` `app/support_checks/generate_matcher_registry_coverage.py:328` — `fixture_file = fixture_file or app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `BLOCKER` `blocking_default_path` `app/support_checks/generate_matcher_registry_coverage.py:329` — `inventory_file = inventory_file or app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `BLOCKER` `blocking_default_path` `app/support_checks/run_matcher_change_preflight.py:46` — `DEFAULT_FIXTURE_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `BLOCKER` `blocking_default_path` `app/support_checks/run_matcher_change_preflight.py:47` — `DEFAULT_INVENTORY_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `BLOCKER` `blocking_default_path` `app/support_checks/run_matcher_change_preflight.py:570` — `fixture_file = fixture_file or app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `BLOCKER` `blocking_default_path` `app/support_checks/run_matcher_change_preflight.py:571` — `inventory_file = inventory_file or app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `BLOCKER` `blocking_imported_default_path` `app/support_checks/run_matcher_layer_parity_checks.py:14` — `from support_checks.run_matcher_layer_parity import DEFAULT_FIXTURE_FILE, run_parity  # noqa: E402`
- `BLOCKER` `blocking_reader` `app/support_checks/run_matcher_layer_parity_checks.py:24` — `fixture_payloads = _load_fixture_payload(Path(DEFAULT_FIXTURE_FILE))`
- `BLOCKER` `blocking_imported_default_path` `app/support_checks/run_matcher_rule_model_checks.py:34` — `DEFAULT_FIXTURE_FILE,`
- `BLOCKER` `blocking_imported_default_path` `app/support_checks/run_matcher_rule_model_checks.py:41` — `DEFAULT_INVENTORY_FILE,`
- `BLOCKER` `blocking_cli_default_path` `app/support_checks/run_matcher_rule_model_checks.py:64` — `parser.add_argument("--fixture-file", default=str(DEFAULT_FIXTURE_FILE))`
- `BLOCKER` `blocking_cli_default_path` `app/support_checks/run_matcher_rule_model_checks.py:65` — `parser.add_argument("--inventory-file", default=str(DEFAULT_INVENTORY_FILE))`
- `BLOCKER` `blocking_default_path` `app/support_checks/run_term_registry_contract_checks.py:52` — `DEFAULT_FIXTURE_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `BLOCKER` `blocking_default_path` `app/support_checks/run_term_registry_contract_checks.py:53` — `DEFAULT_INVENTORY_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `BLOCKER` `blocking_reader` `app/support_checks/run_term_registry_contract_checks.py:517` — `fixture_payloads = _load_json(DEFAULT_FIXTURE_FILE)`
- `BLOCKER` `blocking_reader` `app/support_checks/run_term_registry_contract_checks.py:518` — `inventory_payloads = _load_json(DEFAULT_INVENTORY_FILE)`
- `BLOCKER` `blocking_imported_default_path` `app/support_checks/run_matcher_layer_fixture_schema_checks.py:15` — `DEFAULT_FIXTURE_FILE,`
- `BLOCKER` `blocking_reader` `app/support_checks/run_matcher_layer_fixture_schema_checks.py:54` — `fixture_payloads = _load_fixture_payload(Path(DEFAULT_FIXTURE_FILE))`
- `BLOCKER` `blocking_default_path` `app/support_checks/run_verified_term_audit.py:56` — `RULE_INVENTORY_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `BLOCKER` `blocking_default_path` `app/support_checks/run_verified_term_audit.py:57` — `REGRESSION_CASES_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `BLOCKER` `blocking_default_path` `app/support_checks/run_verified_term_audit.py:317` — `rel_path = _repo_rel(RULE_INVENTORY_FILE)`
- `BLOCKER` `blocking_reader` `app/support_checks/run_verified_term_audit.py:318` — `for index, entry in enumerate(_load_json_list(RULE_INVENTORY_FILE), start=1):`
- `BLOCKER` `blocking_default_path` `app/support_checks/run_verified_term_audit.py:346` — `rel_path = _repo_rel(REGRESSION_CASES_FILE)`
- `BLOCKER` `blocking_reader` `app/support_checks/run_verified_term_audit.py:347` — `for case in _load_json_list(REGRESSION_CASES_FILE):`
- `BLOCKER` `blocking_reader` `app/support_checks/run_verified_term_audit.py:785` — `return {str(case["id"]) for case in _load_json_list(REGRESSION_CASES_FILE)}`
- `BLOCKER` `blocking_reader` `app/support_checks/run_verified_term_audit.py:789` — `return {str(case["id"]): case for case in _load_json_list(REGRESSION_CASES_FILE)}`
- `BLOCKER` `blocking_default_path` `app/support_checks/refresh_matcher_rule_inventory_line_refs.py:15` — `DEFAULT_INVENTORY_FILE = (`
- `ref` `python_reference` `app/support_checks/refresh_matcher_rule_inventory_line_refs.py:16` — `APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `BLOCKER` `blocking_cli_default_path` `app/support_checks/refresh_matcher_rule_inventory_line_refs.py:146` — `parser.add_argument("--inventory-file", type=Path, default=DEFAULT_INVENTORY_FILE)`
- `BLOCKER` `blocking_imported_default_path` `app/support_checks/run_matcher_layer_parity.py:37` — `DEFAULT_FIXTURE_FILE,`
- `BLOCKER` `blocking_cli_default_path` `app/support_checks/run_matcher_layer_parity.py:493` — `parser.add_argument("--fixture-file", default=str(DEFAULT_FIXTURE_FILE))`
- `BLOCKER` `blocking_default_path` `app/support_checks/run_matcher_layer_fixture_cases.py:30` — `DEFAULT_FIXTURE_FILE = (`
- `ref` `python_reference` `app/support_checks/run_matcher_layer_fixture_cases.py:31` — `APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `BLOCKER` `blocking_cli_default_path` `app/support_checks/run_matcher_layer_fixture_cases.py:397` — `parser.add_argument("--fixture-file", default=str(DEFAULT_FIXTURE_FILE))`
- `ref` `python_reference` `app/support_checks/audit_matcher_contract_json_authority.py:23` — `"matcher_regression_cases.json",`
- `ref` `python_reference` `app/support_checks/audit_matcher_contract_json_authority.py:24` — `"matcher_rule_inventory.json",`
- `ref` `python_reference` `app/support_checks/audit_matcher_contract_json_authority.py:27` — `"DEFAULT_FIXTURE_FILE",`
- `ref` `python_reference` `app/support_checks/audit_matcher_contract_json_authority.py:28` — `"DEFAULT_INVENTORY_FILE",`
- `ref` `python_reference` `app/support_checks/audit_matcher_contract_json_authority.py:29` — `"RULE_INVENTORY_FILE",`
- `ref` `python_reference` `app/support_checks/audit_matcher_contract_json_authority.py:30` — `"REGRESSION_CASES_FILE",`
- `BLOCKER` `blocking_default_path` `app/cli/dm.py:25` — `DEFAULT_FIXTURE_FILE = SV_DIR / "matcher_contracts" / "matcher_regression_cases.json"`
- `BLOCKER` `blocking_default_path` `app/cli/dm.py:26` — `DEFAULT_INVENTORY_FILE = SV_DIR / "matcher_contracts" / "matcher_rule_inventory.json"`
- `ref` `python_reference` `app/cli/dm.py:85` — `fixture_file=app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json",`
- `ref` `python_reference` `app/cli/dm.py:86` — `inventory_file=app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json",`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:15` — `DEFAULT_FIXTURE_FILE,`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:16` — `DEFAULT_INVENTORY_FILE,`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:45` — `DEFAULT_FIXTURE_FILE.parents[1],`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:67` — `fixtures = json.loads(DEFAULT_FIXTURE_FILE.read_text(encoding="utf-8"))`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:78` — `fixture_file = Path(tmp) / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:85` — `inventory_file=DEFAULT_INVENTORY_FILE,`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:101` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:133` — `all(issue["file"].endswith("matcher_regression_cases.json") for issue in fixture_issues),`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:142` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:143` — `inventory_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:181` — `"path": "app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:232` — `source_file="app/languages/sv/matcher_contracts/matcher_regression_cases.json",`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:309` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:310` — `inventory_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:370` — `fixture_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"`
- `ref` `test_reference` `app/support_checks/tests/test_rule_change_flow.py:371` — `inventory_file = app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"`
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
- ... 3878 additional reference(s)
