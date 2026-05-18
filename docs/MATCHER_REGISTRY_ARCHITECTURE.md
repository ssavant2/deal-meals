# Matcher Registry Architecture

This note describes the durable Swedish matcher-registry artifacts and the
support-check contracts that keep them in sync.

## Source Layers

- `app/languages/sv/matcher_contracts/sources/matcher_regression_cases.toml`
  stores authored durable positive/negative fixture cases.
- `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml`
  stores authored rule owner, risk, adapter, fixture refs, and source
  provenance.
- `app/languages/sv/matcher_contracts/matcher_regression_cases.json` and
  `app/languages/sv/matcher_contracts/matcher_rule_inventory.json` are
  generated from the TOML sources and committed for existing readers/reports.
- `app/languages/sv/ingredient_matching/term_registry/entries/*.toml` stores
  authored registry entries. Simple mapping families may omit `entry_id` and
  `[[entries.coverage]]`; the registry loader derives them from language,
  market, canonical, first variant, filename, and the family convention.
- `matcher_regression_case.toml` and `matcher_rule_inventory.toml` are generated
  from the JSON contracts by
  `app/support_checks/generate_matcher_registry_coverage.py`.
- `app/languages/sv/ingredient_matching/term_registry/baselines/verified_matcher_terms.json`
  is the frozen verified-term baseline used by registry contract checks.
- `app/languages/sv/ingredient_matching/term_registry/baselines/known_infrastructure_issues.json`
  is the pre-flight safety-valve snapshot for tolerated infrastructure issues.
  Normally empty on `main`; growth requires an explicit reason and tracking ref.
- `app/languages/sv/ingredient_matching/term_registry/baselines/match_bridge_runtime_wiring.json`
  records grandfathered unwired `match_bridge.toml` entries so the runtime-
  wiring check only fails on new unwired bridges.
- `app/support_checks/schemas/prefixes.yml` is the single prefix schema for
  permanent `source_ref`, temporary fixture/policy/source refs, and inventory
  `adapter_ref` prefixes.

Support checks and readers access generated JSON through
`app/support_checks/matcher_contracts.py`; the L3-C direct-reader audit in
`app/support_checks/reports/MATCHER_CONTRACT_JSON_AUTHORITY_AUDIT.md`
currently passes with zero blocking consumers.

The authoritative TOML sources live in
`app/languages/sv/matcher_contracts/sources/` and are documented in that
directory's README. The current source/generation report is
`app/support_checks/reports/MATCHER_CONTRACT_TOML_SOURCE_AUDIT.md`. Pre-flight
rejects generated JSON that no longer matches the TOML sources byte-for-byte.

### Pre-flight as the consistency gate

`app/support_checks/run_matcher_change_preflight.py` is the gate that keeps
all source layers consistent. Pre-flight rejects, among other things:

- generated JSON drift from the TOML sources
- generated registry coverage drift from the JSON contracts
- stale `EXPECTED_*` constants (variant count, unique coverage keys)
- unknown `source_ref` / `policy_ref` / `adapter_ref` prefixes
- broken positive match-bridge fixture refs
- new unwired `match_bridge.toml` entries (vs the wiring baseline)

It runs as the first validation step inside `./bin/dm matcher gates` so cheap
schema problems surface before slow fixture/parity gates. Pre-flight failures
are categorised as `NEW`, `KNOWN`, or `FIXED` relative to
`known_infrastructure_issues.json`; only `NEW` blocks the wrapper.

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

The historical v1 to v2 migration is recorded in
`app/languages/sv/ingredient_matching/term_registry/baselines/verified_term_variant_id_migrations.json`.
It maps every old baseline ID to the new stable ID and is kept as a permanent
provenance/audit map, not as runtime matcher input. Before migration, the v2
payload was checked for collisions across the current 5517 verified variants.

`promote_term_baseline.py` automatically applies content-equivalent ID
migrations. True removals still require explicit `--allow-removals`.

## Standard Maintenance

For live TOML registry rule authoring, prefer the unified CLI:

```bash
./bin/dm matcher add keyword-synonym ...
./bin/dm matcher add keyword-extra-parent ...
./bin/dm matcher add ingredient-parent ...
./bin/dm matcher add offer-extra-keyword ...
./bin/dm matcher add ingredient-routing-parent ...
./bin/dm matcher add parent-match-only ...
./bin/dm matcher add recipe-routing-helper ...
./bin/dm matcher add no-match-policy ...
./bin/dm matcher add extraction-helper ...
```

Use `./bin/dm matcher guide <shape>` to see whether a rule shape has an
authoring command or remains a manual runtime-table change. `match_bridge.toml`
is staged/declarative-only today; author live bridge behavior through the
runtime-wired TOML surfaces unless bridge runtime-wiring is explicitly being
worked on.

For Track B matcher-rule work, prefer the wrapper:

```bash
./bin/dm matcher gates --track B
```

The wrapper refreshes generated coverage when fixture or inventory contracts
change, runs pre-flight checks before slower gates, and promotes the
verified-term baseline when registry changes require it.

During authoring, `./bin/dm matcher dev-watch` polls the matcher source layers
listed above and reruns pre-flight after saves. Watched paths (per
`_watch_files` in `app/cli/dm.py`):

- `app/languages/sv/matcher_contracts/sources/*.toml` (fixture/inventory TOML
  sources and any additional source TOMLs in the same directory)
- `app/languages/sv/matcher_contracts/*.json` (generated JSON contracts, so
  drift is detected the moment they are written)
- `app/languages/sv/ingredient_matching/term_registry/entries/*.toml`
  (registry entries for every rule shape)
- `app/support_checks/run_deep_matcher_sanity.py` (focused regression script)

The default interval is one second, so infrastructure issues should surface
within five seconds on normal dev machines.
