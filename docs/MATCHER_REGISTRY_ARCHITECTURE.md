# Matcher Registry Architecture

This note describes the durable Swedish matcher-registry artifacts and the
support-check contracts that keep them in sync.

## Source Layers

- `app/languages/sv/matcher_contracts/matcher_regression_cases.json` stores
  durable positive/negative fixture cases.
- `app/languages/sv/matcher_contracts/matcher_rule_inventory.json` stores the
  rule owner, risk, adapter, fixture refs, and source provenance.
- `app/languages/sv/ingredient_matching/term_registry/entries/*.toml` stores
  authored registry entries and exact verified-term coverage rows.
- `matcher_regression_case.toml` and `matcher_rule_inventory.toml` are generated
  from the JSON contracts by
  `app/support_checks/generate_matcher_registry_coverage.py`.
- `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json`
  is the frozen verified-term baseline used by registry contract checks.

## Verified-Term Variant IDs

Verified-term `variant_id` values are generated in
`app/support_checks/run_verified_term_audit.py`.

The original v1 hash payload included `source_ref`. That made provenance edits
look like semantic changes, so moving a fixture reference or source comment
forced baseline rehash work.

The current v2 payload excludes `source_ref` and hashes the stable semantic
identity instead: source type/file/id, variant role/text, canonical,
expected-family, ingredient/product text, and expected value. `source_ref`
remains stored as provenance metadata, but it is not identity.

The one-shot v1 to v2 migration is recorded in
`app/languages/sv/ingredient_matching/term_registry/baselines/variant_id_migration_v1_to_v2.json`.
It maps every old baseline ID to the new stable ID. Before migration, the v2
payload was checked for collisions across the current 5517 verified variants.

`promote_term_baseline.py` automatically applies content-equivalent ID
migrations. True removals still require explicit `--allow-removals`.

## Standard Maintenance

For Track B matcher-rule work, prefer the wrapper:

```bash
docker compose exec -T -u appuser -w /app web \
  python support_checks/run_matcher_change_gates.py --track B
```

The wrapper refreshes generated coverage when fixture or inventory JSON changes,
runs pre-flight checks before slower gates, and promotes the verified-term
baseline when registry changes require it.
