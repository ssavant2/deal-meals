# Matcher Contract TOML Sources

This directory contains the authoritative TOML sources for Swedish matcher
contracts.

After editing TOML sources, re-canonicalize them and refresh derived registry
coverage with:

```bash
./bin/dm matcher regen --what all
```

Check for drift without writing with:

```bash
./bin/dm matcher regen --what all --check
```

## Authority

The authored source of truth is:

- `app/languages/sv/matcher_contracts/sources/matcher_regression_cases.toml`
- `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml`

## File Layout

The source set contains two native TOML files:

- `matcher_regression_cases.toml`
- `matcher_rule_inventory.toml`

Each file starts with metadata:

```toml
schema_version = 1
contract = "matcher_regression_cases"
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
- Optional fields remain absent when absent in source TOML.
- Canonical byte comparison uses `json.dumps(..., ensure_ascii=False,
  indent=2, sort_keys=True) + "\n"`.
- TOML sources must parse, re-emit, and round-trip through the canonical
  emitter without semantic drift.
