# Matcher Contract TOML Source Audit

Generated: 2026-05-17

This B3 audit dry-runs a native TOML source schema for the matcher
contract JSON files. It writes TOML sources outside the checkout,
parses them back, and compares the round-trip payload with the current
JSON contracts.

Decision: PASS
Generated JSON committed: no

## Results

| Contract | Rows | Semantic Equal | Canonical Byte Equal | TOML Bytes |
|---|---:|---|---|---:|
| matcher_regression_cases | 1488 | yes | yes | 896739 |
| matcher_rule_inventory | 457 | yes | yes | 519553 |

## Source Files

- `/tmp/deal-meals-matcher-contract-sources/matcher_regression_cases.toml` from `app/languages/sv/matcher_contracts/matcher_regression_cases.json`
- `/tmp/deal-meals-matcher-contract-sources/matcher_rule_inventory.toml` from `app/languages/sv/matcher_contracts/matcher_rule_inventory.json`
