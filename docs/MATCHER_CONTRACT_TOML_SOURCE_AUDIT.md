# Matcher Contract TOML Source Audit

Generated: 2026-05-17

This audit checks the native TOML source schema for the matcher
contract JSON files. In B4 the TOML files are committed as parallel
sources, parsed back, and compared with the current JSON contracts.

Decision: PASS
Generated JSON committed: no

## Results

| Contract | Rows | Semantic Equal | Canonical Byte Equal | TOML Bytes |
|---|---:|---|---|---:|
| matcher_regression_cases | 1488 | yes | yes | 896746 |
| matcher_rule_inventory | 457 | yes | yes | 519560 |

## Source Files

- `app/languages/sv/matcher_contracts/sources/matcher_regression_cases.toml` from `app/languages/sv/matcher_contracts/matcher_regression_cases.json`
- `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml` from `app/languages/sv/matcher_contracts/matcher_rule_inventory.json`
