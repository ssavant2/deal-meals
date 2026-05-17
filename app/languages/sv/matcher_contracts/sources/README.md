# Matcher Contract TOML Sources

This directory documents the proposed B3 TOML source schema for Swedish matcher
contracts. The TOML files themselves are not authoritative or committed in B3.
Generate them into `/tmp` with:

```bash
python app/support_checks/audit_matcher_contract_toml_sources.py \
  --output-dir /tmp/deal-meals-matcher-contract-sources \
  --fail-on-diff
```

## Authority

During B3, the authored source of truth remains:

- `app/languages/sv/matcher_contracts/matcher_regression_cases.json`
- `app/languages/sv/matcher_contracts/matcher_rule_inventory.json`

The TOML source files become eligible for authority only after B4 has a
parallel generator and B5 flips the hand-edit guard.

## File Layout

The dry-run generator writes two native TOML files outside the checkout:

- `matcher_regression_cases.toml`
- `matcher_rule_inventory.toml`

Each file starts with metadata:

```toml
schema_version = 1
contract = "matcher_regression_cases"
source_json_path = "app/languages/sv/matcher_contracts/matcher_regression_cases.json"
source_json_sha256 = "..."
```

Fixture rows use `[[fixtures]]`:

```toml
[[fixtures]]
id = "example_positive"
policy_ref = "example_policy"
source_ref = "current_review:example"
recipe_name = "Example recipe"
ingredients = ["example ingredient"]
expected = 1

[fixtures.offer]
name = "Example offer"
category = "pantry"

[[fixtures.expected_matches]]
canonical = "example"
ingredient_index = 0
must_match_keyword = "example"
```

Inventory rows use `[[inventory]]`:

```toml
[[inventory]]
id = "legacy_example"
status = "wrapped_adapter"
kind = "legacy_parent"
canonical = "example"
owner = "matcher"
policy_ref = "example_policy"
source_refs = ["current_review:example"]
fixture_refs = ["example_positive"]
risk = "policy_term"
adapter_ref = "matcher_layer_diagnostics:example_policy"
notes = "Example inventory row."

[[inventory.line_refs]]
path = "app/languages/sv/ingredient_matching/example.py"
start = 1
end = 1
anchor = "example"
```

## Round-Trip Rules

- Object key order is not semantic.
- List order is semantic and must round-trip unchanged.
- Optional fields remain absent when absent in JSON.
- Canonical byte comparison uses `json.dumps(..., ensure_ascii=False,
  indent=2, sort_keys=True) + "\n"`.
- B3 must not commit generated JSON or generated TOML source files.
