# Matcher Contract TOML Source Audit

Generated: 2026-05-17

This audit checks the native TOML source schema for the matcher
contract JSON files. In B5 the TOML files are the authored sources;
the JSON contracts are generated from these TOML sources.

Decision: PASS
Generated JSON committed: yes

## Results

| Contract | Rows | Semantic Equal | Canonical Byte Equal | TOML Bytes |
|---|---:|---|---|---:|
| matcher_regression_cases | 1488 | yes | yes | 896643 |
| matcher_rule_inventory | 457 | yes | yes | 519457 |

## Source Files

- `app/languages/sv/matcher_contracts/sources/matcher_regression_cases.toml` generates `app/languages/sv/matcher_contracts/matcher_regression_cases.json`
- `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml` generates `app/languages/sv/matcher_contracts/matcher_rule_inventory.json`
