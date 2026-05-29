# Matcher Registry Architecture

This note describes the durable Swedish matcher-registry artifacts and the
support-check contracts that keep them in sync. For the day-to-day workflow,
track choice, and command recipes, see
`docs/runbooks/MATCHER_RULE_CHANGE_RUNBOOK.md`.

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
- `app/languages/sv/ingredient_matching/runtime_rule_overlays.toml` stores
  CLI-authored Track A runtime data overlays. It is tracked production source,
  hash-covered by matcher/offer/recipe compiler versions, and loaded through
  `runtime_rule_overlays.py`.

Support checks and readers access generated JSON through
`app/support_checks/matcher_contracts.py`; the L3-C direct-reader audit in
`app/support_checks/reports/MATCHER_CONTRACT_JSON_AUTHORITY_AUDIT.md`
currently passes with zero blocking consumers.

The authoritative TOML sources live in
`app/languages/sv/matcher_contracts/sources/` and are documented in that
directory's README. The current source/generation report is
`app/support_checks/reports/MATCHER_CONTRACT_TOML_SOURCE_AUDIT.md`. Pre-flight
rejects generated JSON that no longer matches the TOML sources byte-for-byte.

## Runtime Rule Overlay TOML

`runtime_rule_overlays.toml` is the declarative authoring surface for new
runtime data rules that used to require hand-editing large Python literals.
Use `./bin/dm matcher add <shape>` rather than editing it by hand. For existing
runtime-overlay rows with an explicit `id`, use
`./bin/dm matcher modify runtime-overlay <id>` for ordinary value corrections
and `./bin/dm matcher remove <id> --reason ...` for deliberate soft-removal;
both keep generated membership sanity canaries in sync. Historical base tables
are intentionally outside that modify/remove surface.

New CLI-authored rows use v2 metadata:

- `id`: stable overlay entry id
- `status`: usually `active`; `inactive` keeps the row but removes it from the
  effective runtime overlay
- `reason`: why the rule exists
- `inactive_reason`: required context when an entry is intentionally disabled

Statusless historical overlay rows are treated as active only for backwards
compatibility. Do not add new statusless rows.

Supported sections are:

```text
product_name_blockers, false_positive_blockers,
keyword_suppressed_by_context, global_product_name_blockers,
keyword_set_updates, carrier_set_updates, space_normalizations,
carrier_context_required, context_required_words,
ingredient_requires_in_product, context_word_keyword_exemptions,
cuisine_context, compound_protection_updates, specialty_qualifiers,
qualifier_equivalents, processed_product_rules,
processed_rule_compound_exemptions, strict_processed_rules,
spice_fresh_rules, product_name_substitutions,
secondary_ingredient_patterns
```

Runtime merge order is intentionally simple:

```text
historical Python table + active overlay additions - active overlay removals
```

Most map/set sections are additive; `keyword_set_updates` and
`carrier_set_updates` carry explicit `action = "add"|"remove"`. Inactivation
removes only the overlay row from the effective overlay; it does not mutate the
historical Python base tables.

Owning runtime readers:

| Module | Overlay sections read |
| --- | --- |
| `blocker_data.py` | PNB, FPB, GPB |
| `keywords.py` | stop words, non-food keywords, flavor words, important short keywords, processed-food and qualifier-required keyword updates |
| `carrier_context.py` | carrier products, carrier/context requirements, context exemptions, ingredient-requires-product context, KSBC |
| `normalization.py` | space normalizations |
| `recipe_context.py` | cuisine context |
| `compound_text.py` | compound/subword protection updates |
| `specialty_rules.py` | specialty qualifier and qualifier-equivalent updates |
| `processed_rules.py` | processed, strict-processed, compound exemption, and spice/fresh rules |
| `match_filters.py` | product-name substitutions, secondary ingredient patterns, qualifier-required keyword exports |

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

For live TOML registry rule authoring and mechanical maintenance, prefer the
unified CLI:

```bash
./bin/dm matcher add keyword-synonym ...
./bin/dm matcher add keyword-extra-parent ...
./bin/dm matcher add ingredient-parent ...
./bin/dm matcher add offer-extra-keyword ...
./bin/dm matcher add ingredient-routing-parent ...
./bin/dm matcher add parent-match-only ... --negative-offer ... --negative-ingredient ...
./bin/dm matcher add recipe-routing-helper ...
./bin/dm matcher add no-match-policy ... --auto-fixture --auto-inventory
./bin/dm matcher add extraction-helper ...
./bin/dm matcher modify no-match-policy ...
./bin/dm matcher modify match-bridge ...
./bin/dm matcher fixture make-negative <fixture_id>
./bin/dm matcher fixture make-positive <fixture_id> --from-current-match
./bin/dm matcher fixture remove <fixture_id>
```

`parent-match-only` is a route-only parent fallback. Use the negative flags when
the rule is meant to protect a strict boundary; the command does not create that
exclusion by itself.

For `extraction_helper.toml`, the same command can rewrite a simple existing
entry with `--replace-existing` when an `extraction.py` branch is narrowed from
`both` to `product`/`ingredient` or otherwise loses a side. Complex helper
entries with extra terms still need a deliberate manual edit.

For runtime data-rule authoring, prefer the same CLI entry point. Supported
runtime shapes include `pnb`, `fpb`, `ksbc`, `gpb`, stop/non-food filters,
space-normalization, dual-keyword-normalization, flavor/carrier, context,
cuisine, compound, specialty, processed/form, substitution, and
secondary-pattern commands; all write `runtime_rule_overlays.toml`.

`dm matcher add dual-keyword-normalization` is a small authoring wrapper around
`space_normalizations` for ordered multi-keyword output: the primary keyword is
written first so canonical selection remains stable, while extra family
keywords still become available to extraction/matching.

`dm matcher add smart-blocker` is different: it scaffolds and chains a
`matching.py` helper for repeated guard logic, but the helper body is still a
manual Python edit. Use it to remove the mechanical "forgot to wire the helper"
step, not to replace the semantic implementation.

Use `./bin/dm matcher guide <shape>` to see whether a rule shape has an
authoring command or remains a manual runtime-table change. `match_bridge.toml`
is staged/declarative-only today; author live bridge behavior through the
runtime-wired TOML surfaces unless bridge runtime-wiring is explicitly being
worked on. Existing simple `match_bridge.toml` rows can be narrowed with
`dm matcher modify match-bridge`; new rows remain staged metadata unless paired
with a runtime-wired surface.

For diagnostics, use `dm matcher compare-paths` when legacy live, canonical
fast, backend, or offer-precompute keyword paths may disagree. Use
`dm matcher doctor` for a read-only source/generated/writeability summary before
slower gates, and `dm matcher trace-extraction` when the failure is earlier than
matching and a keyword was dropped, unexpectedly added, or added only by offer
precompute expansion. Use `dm matcher canonical-of "<term>"` before authoring
rules when a user-facing Swedish term may normalize to a different runtime
canonical.

New CLI-generated sanity blocks carry a `# sanity-id: <policy_ref>` metadata
comment. Use `dm matcher sanity-find` to locate them,
`dm matcher reconcile-sanity` to compare generated expectations with current
runtime behavior, and `dm matcher sanity-update` for deliberate expectation
changes instead of hand-editing a large `run_deep_matcher_sanity.py` file by
line number. Positive generated `match(...)` canaries observe the current
materialized fast-path canonical before writing the expected value, so
parent/variant cases do not encode a guessed parent canonical when the precise
variant wins.
For runtime-overlay membership canaries,
`dm matcher modify runtime-overlay <id>` rewrites the canary for the entry's
current values and `dm matcher remove <id>` removes the generated membership
assertions.

For grouped rule work, `dm matcher batch start` defers per-command gates and
`dm matcher batch finalize --dry-run` prints doctor output plus the planned
regen/promote/line-ref/preflight/gate steps without mutating files.
`dm matcher batch metrics --start/--finish` writes an ignored local JSON note
under `app/.dm/`; it is only for local friction tracking, not registry policy.
When a review reverses an old positive fixture into a negative proof, use
`dm matcher fixture make-negative` instead of hand-editing
`[[fixtures.expected_matches]]`; then finalize with `--allow-removals` if the
promote step reports reviewed true removals.
When a review reverses an old negative fixture into a positive proof, use
`dm matcher fixture make-positive --from-current-match`; it only writes the
positive `expected_matches` block when current diagnostics agree on one stable
match.

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
