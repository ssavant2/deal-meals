# Term Registry Step 2 Plan

Created: 2026-05-09

Purpose: prevent future matcher vocabulary drift after the Track A/B audit.
New matcher terms should be declared once, then checked or generated into
ingredient extraction, offer extraction, route terms, final matching, negative
guards, and regression fixtures.

This is a follow-up to the completed term-pipeline audit baseline:

- Track A Batch 4-15 carry-over is resolved.
- Track B static baseline is complete with 5,472 audited variants and
  `needs_fix=0`.
- The remaining risk is process drift: future words being added to one matcher
  layer but not the others.

## Recommendation

Build this as a staged registry/check system, not as a one-shot rewrite.

The first implementation wave should be `no behavior change`: create a typed
registry view and invariant checks that reproduce the current audited baseline.
Only after the checks are stable should matcher modules start importing
generated registry exports.

Use human-editable data files as the authoring surface. Python typed records are
the internal normalized representation for validation, reports, and exports; they
should not be the only way a non-developer can add a term.

## Non-Goals

- Do not re-audit the full B baseline by hand.
- Do not require a current live catalog item for every historical term.
- Do not force every term into every matcher file. Some terms are intentionally
  route-only, offer-only, ingredient-only, bridge-only, or negative guards.
- Do not full-rebuild the recipe cache after every registry edit. Use synthetic
  and static checks first; rebuild only for materialization waves.
- Do not remove existing matcher modules in the first wave.
- Do not hard-code the registry model to Swedish. The first inventory is Swedish
  because that is the only audited matcher vocabulary today, but the mechanism
  must support other language/market matchers.

## Language And Market Scope

The registry architecture should be language-neutral with language-specific
adapters.

The shared layer should define:

- data models and enum-like policies
- source refs and proof examples
- invariant/check framework
- export comparison helpers
- report schema

Each language/market implementation should define:

- normalization/tokenization profile
- category/profile mappings used by that matcher
- source inventory adapters
- generated exports for that language's matcher modules
- fixture/report namespace

The Swedish registry is the first implementation and baseline. It should not
become the implicit global schema. Future language packages, for example
`en_gb`, should be able to add their own registry entries without inheriting
Swedish canonicals, Swedish spelling variants, or Swedish category assumptions.

Canonical terms are scoped per language/market. A Swedish canonical such as
`basilikapesto` and a future English canonical such as `basil pesto` may point
to the same conceptual food family, but they should not share one raw term id
unless an explicit cross-language mapping is introduced later.

## Target Outcome

Adding a new matcher word should normally mean:

1. Add or edit one registry entry.
2. Add product/ingredient proof text when the term is not self-evident.
3. Run registry checks and targeted matcher tests.
4. Let generated exports or invariant checks ensure the term is represented in
   all required layers.

If a term is intentionally missing from a layer, that omission must be declared
in the registry with an explicit reason.

## Authoring Surface

The registry should have two layers:

- authoring files that are easy to edit and review
- Python typed records built from those files and from legacy inventory adapters

Preferred authoring format: TOML files under each language registry package.
TOML is readable, supports comments, and can be parsed with Python's standard
library. YAML is intentionally out of scope. JSON is acceptable for generated
reports but too noisy as the main manual editing format.

Example Swedish authoring path:

- `app/languages/sv/ingredient_matching/term_registry/entries/*.toml`

Default file organization:

- one TOML file per canonical family, e.g. `entries/tomkha.toml`
- keep simple aliases, guards, and examples for that canonical in the same file
- split only when a family becomes too large to review comfortably
- generated/imported inventory reports stay under `app/tests/reports/`, not in
  hand-maintained `entries/*.toml`

The add-a-term workflow should therefore be usable in two ways:

- Stefan can describe or edit a small TOML entry with examples/source refs.
- Codex/Claude can convert that TOML entry into validated Python records and
  generated exports.

The internal Python model should reject malformed data early, but it should not
force routine vocabulary edits to be Python-code edits.

### Minimal Manual Entry

For a simple product-text alias to an existing canonical, the authoring entry
should be small enough to write by hand:

```toml
entry_id = "sv-se.alias.<existing_canonical>.<short_alias_name>"
language = "sv"
market = "SE"
canonical = "<existing_canonical>"
status = "active"

variants = ["<new product wording>"]
ingredient_terms = ["<existing_canonical>"]
offer_terms = ["<existing_canonical>"]
route_terms = ["<existing_canonical>"]
final_match_terms = ["<existing_canonical>"]

layer_policy = ["offer_alias", "existing_canonical"]
source_refs = ["manual:stefan:<yyyy-mm-dd>"]

notes = "Short reason this product wording belongs to the canonical family."

[[positive_examples]]
ingredient = "<ingredient text that should match>"
offer_name = "<new product wording as it appears in a store>"
offer_category = "<category>"
expected = 1

[[negative_examples]]
ingredient = "<same or nearby ingredient text>"
offer_name = "<nearby product wording that must not match>"
offer_category = "<category>"
expected = 0
```

If the canonical does not already exist, the entry is not a simple alias. The
check should ask for a fuller family definition with route/final-match policy
and at least one positive and one negative proof example.

## Proposed File Layout

Start with a shared registry core plus a Swedish inventory package:

- `app/languages/term_registry/__init__.py`
- `app/languages/term_registry/models.py`
- `app/languages/term_registry/checks.py`
- `app/languages/term_registry/reports.py`
- `app/languages/sv/ingredient_matching/term_registry/__init__.py`
- `app/languages/sv/ingredient_matching/term_registry/entries/*.toml`
- `app/languages/sv/ingredient_matching/term_registry/migration_exceptions.toml`
- `app/languages/sv/ingredient_matching/term_registry/legacy_inventory.py`
- `app/languages/sv/ingredient_matching/term_registry/registry.py`
- `app/languages/sv/ingredient_matching/term_registry/exports.py`

Add test/report tooling:

- `app/tests/run_term_registry_contract_checks.py`
- `app/tests/run_term_registry_export_checks.py`
- `app/tests/run_term_registry_guard_bridge_checks.py`
- `app/tests/reports/term_registry/sv/`

Test scripts should accept a language/market argument, defaulting to `sv` while
only the Swedish matcher has registry coverage. Example:

- `python3 tests/run_term_registry_contract_checks.py --language sv`
- `python3 tests/run_term_registry_export_checks.py --language sv`
- `python3 tests/run_term_registry_guard_bridge_checks.py --language sv`

Do not generate over existing matcher modules until the export checks can prove
that generated output is byte-for-byte or behavior-equivalent to the current
static structures.

## Registry Entry Shape

Each registry entry should be a typed record with at least:

- `entry_id`: globally stable id, e.g. `sv-se.family.basilikapesto`
- `language`: language code, e.g. `sv`
- `market`: market/country code when relevant, e.g. `SE`
- `canonical`: canonical matcher term
- `variants`: accepted spellings/forms
- `positive_examples`: ingredient/product pairs that should match
- `negative_examples`: ingredient/product pairs that must not match
- `ingredient_terms`: terms emitted from recipe/ingredient text
- `offer_terms`: terms emitted from product text
- `route_terms`: terms allowed to create candidate pairs
- `final_match_terms`: terms allowed to pass final validation
- `negative_guards`: blockers, no-match policies, or forbidden sibling families
- `source_refs`: fixture ids, inventory ids, batch notes, or code refs
- `layer_policy`: explicit declarations for route-only, offer-only,
  ingredient-only, bridge-only, accepted filter, or no-product-text cases
- `status`: active, deprecated, watchlist, or planned
- `notes`: short rationale for non-obvious matching behavior

Use exact enum-like strings for `layer_policy`, not free prose, so checks can
reason over it.

`entry_id` format:

- `<language>-<market>.<entry_type>.<canonical>[.<short_name>]`
- lowercase ASCII slugs only
- `language` and `market` fields must match the `entry_id` prefix
- recommended `entry_type` values: `family`, `alias`, `guard`, `bridge`,
  `policy`, `watchlist`

Initial `layer_policy` values:

- `normal`: full ordinary coverage is expected
- `existing_canonical`: entry extends a canonical that already exists
- `new_canonical`: entry creates a new canonical family
- `offer_alias`: product wording should emit an existing canonical
- `ingredient_alias`: ingredient wording should emit an existing canonical
- `route_only`: term is only intended to create candidate routes
- `offer_only`: term is offer-side only
- `ingredient_only`: term is ingredient-side only
- `bridge_only`: term exists only through a declared bridge
- `accepted_filter`: product is accepted as filtered by category/preferences
- `no_product_text`: no product text proof exists yet
- `negative_guard_only`: entry exists only to block false positives

Additional policy values can be added, but they must be documented here before
they appear in TOML entries.

Language-specific entry fields should be kept in a structured extension field,
for example `language_payload`, rather than leaking Swedish-only assumptions
into the shared model.

## Source Ref Format

Use typed, parseable source refs. Do not use loose prose as the only source link.

Recommended forms:

- `batch:batch_review_questions:batch_7_15`
- `batch_report:batch_review_term_pipeline_audit_batch_7_15:term:basilikapesto`
- `fixture:matcher_regression_cases:<fixture_id>`
- `inventory:matcher_rule_inventory:<entry_id>`
- `bridge:match_bridges:<bridge_id_or_canonical>`
- `policy:no_match_policies:<policy_id_or_canonical>`
- `code:ingredient_routing:<symbol_or_line_ref>`
- `code:term_indexes:<symbol_or_line_ref>`
- `manual:<owner>:<yyyy-mm-dd>`

Each source ref should have a known prefix and should be validated when the
target file/schema makes validation practical. Free-text notes can still explain
why a decision exists, but checks should not depend on parsing those notes.

## Status Semantics

Registry entry statuses:

- `active`: included in exports and full invariant checks.
- `planned`: not exported; may be incomplete; cannot satisfy R4 coverage for a
  live legacy term.
- `watchlist`: not exported unless an explicit `export_enabled` flag is set;
  used for accepted terms waiting on product text or policy confirmation.
- `deprecated`: not exported by default; kept for historical source refs,
  old fixtures, or migration cleanup.

Deprecated entries need explicit semantics:

- If a deprecated term still exists in a legacy matcher source, it must have a
  `migration_exception` or a cleanup task.
- If a deprecated term remains in regression fixtures, the fixture must declare
  whether it preserves old behavior or proves the term is blocked.
- Deprecated entries do not count as active coverage for new add-a-term work.
- Deprecated entries may be counted in historical reports, but separate from
  the active baseline counters.

## Migration Exception Format

`migration_exceptions.toml` is a temporary bridge for new legacy-only terms, not
a second registry. Each exception must be narrow enough that it can be removed
when a single exact coverage key is registry-covered.

Required fields:

- `id`: stable exception id
- `owner`: person or agent responsible for removing it
- `language`
- `market`
- `source_family`: one legacy source family only
- `canonical`
- `variant`
- `layer_role`: exact B-track/legacy layer role, for example
  `bridge_positive`, `negative_guard_pattern`, or `parent_match_only_mapping`
- `reason`
- `created_at`
- `expires_when`: concrete condition, not just a date

Example:

```toml
[[exceptions]]
id = "sv-se.kryddmix.example_until_r1"
owner = "codex"
language = "sv"
market = "SE"
source_family = "match_bridge"
canonical = "example"
variant = "example variant"
layer_role = "bridge_positive"
reason = "Temporary legacy-only bridge until registry coverage handles this exact key."
created_at = "2026-05-09"
expires_when = "Remove when registry coverage includes this exact key."
expires_on = "2026-06-30"
```

## Required Invariants

The registry checks should fail when:

- a positive term has ingredient exposure but no offer exposure or route bridge,
  unless explicitly declared as `ingredient_only` or `no_product_text`
- an offer term exists without any recipe-side route path, unless explicitly
  declared as `offer_only`
- a route term can create candidates but no final validation path exists
- a negative guard lacks a fixture, no-match policy, blocker, or bridge reason
- two canonicals compete for the same product/ingredient text without a declared
  equivalence or precedence rule
- a source ref points to a missing fixture, inventory row, or test case
- a term is added to legacy matcher structures without a registry entry or a
  temporary migration exception
- generated exports differ from legacy exports in a no-behavior-change wave
- a migration exception has expired, points to a term no longer present in
  legacy inventory, or lacks an owner/reason

The checks should also report weak but accepted cases:

- `synthetic_verified`
- `no_product_text`
- `accepted_filter`
- `route_only`
- `offer_only`
- `ingredient_only`
- `negative_guard_only`

These are not failures when explicitly declared.

## Swedish Source Inventory To Cover

The Swedish registry should cover the same source families that Track B audited:

- `matcher_rule_inventory.json`
- `matcher_regression_cases.json`
- `match_bridges.py`
- `no_match_policies.py`
- `ingredient_routing.py`
- `synonyms.py`
- `parent_maps.py`
- `keywords.py`
- targeted helper logic in `extraction.py`
- targeted helper logic in `term_indexes.py`
- accepted Track A policy decisions from `batch_review_questions.md` and the
  Batch 4-15 audit reports

Initial coverage can be read-only: the registry tool imports these sources and
normalizes them into registry-shaped entries. Later waves can move selected
families from legacy static structures into first-class registry declarations.

Do not import every raw batch-review question as a registry rule. Only accepted
policy decisions and final fix/watchlist outcomes should become registry
entries or source refs.

Future language inventories should follow the same adapter contract, but they do
not need to match the Swedish source-file layout. A language without an
`ingredient_matching` package yet can still implement the shared registry
interfaces when its matcher is introduced.

## Import Boundaries

Avoid registry/legacy import cycles by separating runtime registry exports from
audit-only legacy adapters.

Rules:

- shared `app/languages/term_registry/*` must not import language-specific
  matcher modules
- per-language `registry.py` loads authored registry entries only
- per-language `exports.py` builds runtime exports from registry entries only
- per-language `legacy_inventory.py` may import old matcher modules, but only
  test/report scripts should import it
- export comparison scripts may import both `exports.py` and `legacy_inventory.py`
- runtime matcher modules must never import a module that imports them back

Before R2, confirm the selected runtime import path is registry-only. If a
legacy module starts importing registry-generated exports while the registry
still imports that legacy module for its source view, that wave must stop until
the source view is split.

## Rollout Waves

### R0 - Registry View And Checks

Status: implemented locally; contract check passed 2026-05-09.

Build read-only inventory normalization from current sources. Produce a report
with one row per registry-like entry and one row per concrete variant.

Precondition:

- machine-readable B2 output exists. In this dev environment it currently
  exists at:
  `app/tests/reports/term_pipeline_b_track/term_pipeline_audit.json`
  with the final applied batch confirmed by
  `app/tests/reports/term_pipeline_b_track/b092_static_audit.json`

If the B2 JSON is missing in another checkout/environment, recreate or recover
the B2 machine-readable report before starting R0. Do not use Markdown counters
as the automated baseline. If necessary, rerun the B-track initializer/audit
workflow through `B092`, capture the JSON report, and only then start R0.

Done when:

- shared registry models/check helpers do not import Swedish matcher modules
- the script enumerates the same 5,472 baseline variants as B2, or records an
  intentional delta with source explanation
- all existing B2 `needs_fix=0` outcomes remain non-failing
- the report can identify layer policies and source refs deterministically
- report paths are language-scoped, initially `term_registry/sv/`
- no matcher runtime behavior changes

### R1 - No-Behavior Export Check

Status: implemented locally for `PARENT_MATCH_ONLY`; export check passed
2026-05-09.

Create export builders that can produce dictionaries/sets equivalent to selected
low-risk legacy structures. Start with one narrow source family, not the whole
matcher.

Recommended first target:

- small alias/parent families with no negative guards and existing fixtures

Batch size:

- 25 registry entries per migration wave, or one tightly related source family,
  whichever is smaller

Done when:

- generated export equals the current legacy structure for the selected family
- contract checks fail if the registry omits a required layer
- targeted sanity tests pass
- no cache rebuild required

### R2 - Import Generated Exports In One Low-Risk Layer

Status: implemented locally for `parent_maps.PARENT_MATCH_ONLY`; checks passed
2026-05-09.

Switch one low-risk matcher module to import registry-generated exports while
keeping its public constants/functions stable.

Candidate module:

- a narrow subset of `synonyms.py`, `parent_maps.py`, or `keywords.py`

Done when:

- public API remains stable
- existing tests pass
- rule inventory and fixture schema checks pass
- generated export check proves no semantic drift
- import-boundary check proves the selected runtime import path does not import
  `legacy_inventory.py` or any module that imports the selected legacy module

### R3 - Negative Guards And Bridge Families

Status: implemented locally as guard/bridge contract checks; checks passed
2026-05-09.

Move families with blockers/no-match policies only after R1/R2 are stable.
Negative families need stronger checks because they can silently reduce valid
matches or admit false positives.

Done when:

- every negative guard has at least one executable negative fixture or policy ref
- each bridge family declares positive and negative sides explicitly
- matcher diagnostics show expected route/final-match behavior for sample cases

### R4 - New-Term Gate

Status: implemented locally in `run_term_registry_contract_checks.py`; gate
and failure probe passed 2026-05-09.

Make registry checks part of the normal matcher test bundle. From this point,
adding a term only in legacy structures should fail unless a migration exception
is declared.

Gate mechanism:

1. Normalize current legacy matcher sources through `legacy_inventory.py`.
2. Normalize authored registry entries through `registry.py`.
3. Compare stable coverage keys, not line numbers. Suggested key:
   `(language, market, source_family, canonical, variant, layer_role)`.
4. Load `migration_exceptions.toml`.
5. Fail when a legacy key is not covered by an active registry entry and has no
   valid migration exception.
6. Fail when a registry key claims a source ref that no longer exists.
7. Fail when an exception is stale, expired, ownerless, or broader than one
   source family.

This is a diff-based gate in addition to invariant checks. It must answer:
"what is present in legacy today that registry does not know about?"

Done when:

- `run_term_registry_contract_checks.py` is included in the local sanity command
- CI/local test docs mention the registry gate
- adding a new unmatched term to a legacy source causes a clear actionable error

### R5 - Cleanup Legacy Side Lists

Status: three cleanup waves implemented locally for `parent_match_only`,
`ingredient_routing_parent`, and `recipe_routing_helper`; broader cleanup waits
until more source families are registry-owned.

Remove or shrink legacy-only side lists after enough families are registry-owned.
This is cleanup, not a prerequisite for the safety gate.

Trigger:

- R4 is active
- at least three source families or at least 100 active entries are registry-owned
- those migrated families have no migration exceptions for two consecutive
  registry check runs

Done when:

- legacy structures are either generated or explicitly marked as hand-maintained
  exceptions
- no duplicate source of truth remains for migrated families
- docs describe the add-a-term workflow

## Interim Add-A-Term Workflow Before R4

Historical note: this applied before R4 was active. In this checkout, R4 is
active locally and new broad vocabulary should not silently land only in legacy
structures.

For R0-R3:

1. Add the required legacy matcher edit to solve the immediate bug.
2. Add a draft TOML registry entry when the touched source family is already
   supported by R0/R1.
3. If the family is not supported yet, add a narrow `migration_exception` with:
   - owner
   - source family
   - canonical/variant
   - reason
   - expiry condition, usually "remove after R0/R1 covers this source family"
4. Add or update targeted fixtures for positive/negative examples.
5. Avoid large vocabulary expansions until the source family has registry
   coverage.

Do not block urgent bug fixes only because R4 is not live yet; do make every new
term visible to the future registry gate.

## Add-A-Term Workflow

After R4, the preferred workflow should be:

1. Add or update a TOML registry entry with canonical, variants, source refs,
   layer policy, and exact legacy `[[coverage]]` rows when a legacy source is
   touched.
2. Add at least one positive example.
3. Add negative examples for close siblings when the term is specific.
4. Run:
   - `python3 tests/run_term_registry_contract_checks.py --language sv`
   - `python3 tests/run_term_registry_export_checks.py --language sv`
   - `python3 tests/run_term_registry_guard_bridge_checks.py --language sv`
   - `python3 tests/run_matcher_rule_inventory_checks.py`
   - `python3 tests/run_matcher_layer_fixture_schema_checks.py`
   - targeted fixture/sanity tests for the changed family
5. Rebuild cache only when validating compiled index/materialized cache behavior.

Minimal coverage row shape:

```toml
[[coverage]]
source_family = "parent_match_only"
canonical = "salami"
variant = "pepparsalami"
layer_role = "parent_match_only_mapping"
```

## Rollback Policy

Before switching any runtime module to generated exports:

- keep the legacy structure available in the diff
- run export equivalence checks
- keep migration waves small enough to revert as one normal patch

If an export check fails after a migration:

- do not rebuild cache from the failed state
- revert only the migration patch for that wave
- keep registry report output for diagnosis
- re-run contract checks before trying the wave again

## Completion Definition

Step 2 is complete when:

- registry contract checks cover the full B2 source inventory
- at least one runtime layer consumes registry-generated exports
- new terms cannot be added to audited legacy sources without registry coverage
  or an explicit migration exception
- shared registry models and check runners can target a language/market without
  Swedish imports in the shared layer
- docs include the add-a-term workflow
- the registry report shows 0 unclassified active terms

Full removal of all legacy structures is not required for Step 2 completion.

## Current Status

| Field | Value |
| --- | --- |
| Overall status | R5 three cleanup waves complete locally; broader cleanup waits for more migrated families |
| Baseline | B2 static audit, 5,472 variants, 0 `needs_fix` |
| First implementation wave | R0 registry view and checks complete |
| First export wave | R1 `PARENT_MATCH_ONLY` no-behavior export check complete |
| First runtime import wave | R2 `parent_maps.PARENT_MATCH_ONLY` imports registry export |
| First guard/bridge wave | R3 checks cover 114 no-match policies and 282 match bridges |
| New-term gate | R4 active in `run_term_registry_contract_checks.py` and `run_sanity_checks.py`; failure probe passes |
| First cleanup wave | R5 `parent_match_only` is TOML-owned with 2 active entries and 17 coverage keys |
| Second cleanup wave | R5 `ingredient_routing_parent` is TOML-owned with 19 active entries and 34 coverage keys |
| Third cleanup wave | R5 `recipe_routing_helper` is TOML-owned with 9 active entries and 9 coverage keys |
| First language/market | `sv-SE` |
| Multi-language status | architecture required; only Swedish inventory exists today |
| Generated reports | `app/tests/reports/term_registry/sv/term_registry_contract_report.{json,md}`, `app/tests/reports/term_registry/sv/term_registry_export_report.{json,md}`, and `app/tests/reports/term_registry/sv/term_registry_guard_bridge_report.{json,md}` |
| Cache rebuild required | no |

## Open Decisions

| Decision | Default |
| --- | --- |
| Registry representation | TOML authoring files plus Python typed records for internal validation, reports, and exports. |
| Authoring format | TOML files first. Python typed records are not the primary manual edit surface. |
| Shared core location | `app/languages/term_registry/`, with per-language adapters under each matcher package. |
| First migrated source family | Small alias/parent family with existing fixtures and no negative guards. |
| Migration batch size | 25 registry entries per wave, or one source family, whichever is smaller. |
| CI/local gate timing | After R0 and R1 are stable. |
