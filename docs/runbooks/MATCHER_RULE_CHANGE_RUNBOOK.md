# Matcher Rule Change Runbook

This runbook is the standard workflow for Swedish matcher semantic changes:
new aliases, bridges, blockers, no-match policies, routing terms, and
product-form rules.

The goal is not to make every matcher change non-technical. The goal is to make
AI/LLM agents and humans choose the same level of proof for the same kind of
change, so tactical runtime fixes stay fast while durable registry rules land
with fixtures, inventory, parity coverage, and cache expectations.

## TL;DR Cheat Sheet

Track A is a narrow runtime fix. Track B is durable registry/contract work.
Start with the CLI wrapper; use raw support-check commands only when debugging.

Plain-language rule:

- **Track A** is "fix the small bug where the matcher already has the right kind
  of runtime mechanism." Example: add one PNB/FPB blocker so a supplement,
  baby-formula product, flavor, carrier, or product form stops matching one
  ingredient by accident. Proof is a focused `run_deep_matcher_sanity.py`
  regression plus parity.
- **Track B** is "add or change a rule that should become permanent matcher
  contract knowledge." Example: add `citron`, `lime`, and `apelsin` as
  `keyword-extra-parent` children of `citrusfrukter`, or add a no-match/plain
  policy that needs positive and negative fixtures. Proof is TOML source,
  fixtures, inventory, generated coverage, baseline promotion when registry
  entries changed, and Track B gates.

Known CLI rule shape:

```bash
./bin/dm matcher add keyword-extra-parent <canonical> --kids <kid1,kid2,...> ...
```

Manual Track A:

```bash
# edit narrow Python runtime rule + focused run_deep_matcher_sanity.py case
./bin/dm matcher gates --track A
```

Manual Track B:

```bash
# edit TOML sources + focused run_deep_matcher_sanity.py case
./bin/dm matcher gates --track B --policy-ref <policy_ref>
```

Inactivate/remove a registry rule:

```text
status = "inactive"
./bin/dm matcher gates --track B --registry-changed --allow-removals
```

Iterate with live pre-flight feedback:

```bash
./bin/dm matcher dev-watch
```

Generated-file rule: edit the authoritative TOML sources, not generated JSON or
generated registry coverage TOML. In particular, do not hand-edit
`matcher_regression_case.toml` or `matcher_rule_inventory.toml`. The wrapper
regenerates these files and pre-flight rejects drift.

If something fails, read pre-flight `NEW` issues first. `KNOWN` is tracked
pre-existing noise; `FIXED` means a tolerated issue disappeared and the baseline
snapshot should be refreshed.

Before editing, run:

```bash
git status --short --untracked-files=all
```

Do not revert unrelated edits. If the working tree is already dirty, keep your
change scoped and mention relevant pre-existing files in your handoff.

## Command First

For most changes, start here and only read the longer sections when the wrapper
flags or a failing gate are unclear.

Use `./bin/dm matcher ...` from the host checkout when available. It forwards to
the web container and keeps the old support-check wrapper available as
`dm matcher gates ...`. The raw `python support_checks/run_matcher_change_gates.py`
commands below are the fallback/debug form.

The wrapper runs generated-coverage refresh and baseline promotion maintenance
before validation when Track B inputs require it. Its first validation gate is
`run_matcher_change_preflight.py`; fix any `NEW` pre-flight issue before
spending time on slower fixture/parity gates.

For live feedback while editing matcher contracts or registry TOML, keep this
running in another terminal:

```bash
./bin/dm matcher dev-watch
```

It polls matcher files and reruns pre-flight after saves. Use
`--interval <seconds>` to tune polling, or `--once` for a single pre-flight run
through the CLI entry point.

**Where to run from:**

- **Wrapper commands:** run `./bin/dm matcher ...` from the host checkout.
- **Raw Track A fallback:** run inside the container
  (`docker compose exec -T -w /app web ...`). Track A gates are read-only and
  tolerate the default `/app` read-only mount.
- **Raw Track B/write maintenance:** run from a writable host checkout or the
  dev container as `appuser`. Track B may need to write baseline files, refresh
  inventory line refs, or stage promotion output.

Track A runtime blocker/guard fix:

```bash
./bin/dm matcher gates --track A
```

Fallback:

```bash
docker compose exec -T -w /app web \
  python support_checks/run_matcher_change_gates.py --track A
```

Track B durable registry/fixture/inventory rule, from the host checkout or a
writable dev container:

```bash
./bin/dm matcher gates --track B --policy-ref <policy_ref>
```

Fallback:

```bash
docker compose exec -T -u appuser -w /app web \
  python support_checks/run_matcher_change_gates.py --track B \
    --policy-ref <policy_ref>
```

Track B with registry TOML changes:

```bash
./bin/dm matcher gates --track B --policy-ref <policy_ref> --registry-changed
```

Add only the flags that match the change:

- `--runtime-changed` when matcher Python changed.
- `--fixtures-changed` when the regression-case TOML source or generated JSON changed.
- `--inventory-changed` when the rule-inventory TOML source or generated JSON changed.
- `--allow-removals` only after confirming intentional TOML inactivation or
  removal.
- `--refresh-line-refs` when inventory anchors moved; run from a writable host
  checkout or write-enabled dev container.
- `--baseline-output-dir /tmp/term-baseline-promotion` only when the checkout is
  read-only; the wrapper stages generated files and stops so you can apply them
  before rerunning gates. If promote is accidentally run as a user that cannot
  write the checkout, it falls back to this staged-output mode automatically.
- `--reload-cache --fresh-cache-gates` when cache/UI/cache-backed validation is
  part of the handoff.
- `--include-support-self-checks` when support-check code or schemas changed.
- `--dry-run` to print the exact gate list before running it.

If the host worktree is clean enough for git auto-detection, the wrapper can
select many flags itself. If the worktree contains unrelated edits, pass the
explicit flags above so the gate set reflects only your change.

**Commands NOT covered by the wrapper** (run these separately when needed):

- `dev_reload.py` — cache rebuild; use `--reload-cache --fresh-cache-gates` on
  the wrapper if the gates themselves should also run on the refreshed cache,
  but the rebuild itself is its own command for ad-hoc cache work.
- `refresh_matcher_rule_inventory_line_refs.py` — host-only; the wrapper accepts
  `--refresh-line-refs` to trigger it.
- `matcher_layer_diagnostics.py` — interactive reproduction tool used in
  triage, not a gate.
- `run_matcher_full_db_diff.py` — heavy read-only DB diff for release work, not
  routine.

## Common CLI Workflows

Use the CLI for supported rule shapes. It writes the registry TOML,
fixture/inventory TOML sources, generated JSON, focused deep-sanity regression,
generated coverage TOML, and then runs Track B gates by default.

Keyword extra parent fan-out:

```bash
./bin/dm matcher add keyword-extra-parent citrusfrukter \
  --kids citron,lime,apelsin \
  --recipe-name "Citrusrecept" \
  --ingredient "3-4 citrusfrukter (valfri sort)" \
  --offer-names "Citron,Lime,Apelsin" \
  --offer-category fruit
```

Use `--dry-run` to preview generated TOML/sanity text, `--no-run-gates` only for
isolated test trees, and `--inventory-id` only when deliberately adding a
separate inventory row for a canonical that already has one. For all other rule
types, follow the manual Track A or Track B workflow until a dedicated
`dm matcher add ...` subcommand exists.

## Cold-Start Details

Read this section first if you have never seen this runbook before. Also return
here when you need repo orientation, when a gate fails in a layer you did not
expect, or when you are deciding whether a one-off diagnostic is enough.

The Swedish matcher is deliberately layered. A pair can appear correct in a
single live check but still fail in routed cache, compiled data, backend
validation, or materialization. For durable rules, the permanent answer to "is
this rule done?" is therefore not "the one example matches now"; it is "the
fixture/inventory contract passes across all matcher paths."

The important layers are:

1. recipe normalization and ingredient extraction
2. compiled recipe runtime data
3. offer extraction and offer precompute
4. compiled offer runtime data
5. term indexes and candidate routing
6. `matches_ingredient_fast`
7. backend validation in `validate_offer_match_candidate`
8. cache materialization and grouping

When a change affects semantics, think in terms of all eight layers. If you fix
only the layer where you first noticed the bug, you may create a live/cache
split.

The main repo map:

| Area | What it is |
| --- | --- |
| `app/languages/sv/ingredient_matching/` | Swedish matcher runtime rules, registry exports, extraction, routing, validators, and versioning. |
| `app/languages/sv/matcher_contracts/sources/` | Authoritative matcher fixture and inventory TOML contracts. |
| `app/languages/sv/matcher_contracts/*.json` | Generated matcher fixture and inventory JSON contracts used by existing readers/reports. |
| `app/languages/sv/ingredient_matching/term_registry/entries/` | Tracked TOML registry entries for vocabulary/rule surfaces. |
| `app/support_checks/` | Deterministic support checks and matcher diagnostics. |
| `app/tests/` | Ignored local workbench/review material. Useful for investigation, not permanent proof. |
| `docs/TESTING.md` | High-level testing policy and current durable matcher/cache gates. |

The production-style compose service mounts `/app` read-only. The dev overlay is
writable in the current setup, but baseline writes belong to the file-owning
`appuser`; a plain `docker compose exec web ...` may run as root and hit
`PermissionError`. Use the host checkout or `docker compose exec -T -u appuser`
for write-maintenance commands.

## Two Work Tracks

Every matcher change starts by choosing a track. This is the most important
decision in the runbook.

| Track | Use for | Typical files | Required proof |
| --- | --- | --- | --- |
| Track A: tactical runtime fix | A concrete FP/FN or known local semantic gap, usually narrow and local. This is the normal path for small PNB/FPB/GPB additions and tiny runtime guards. | `blocker_data.py`, `specialty_rules.py`, `processed_rules.py`, `form_rules.py`, small backend guards beside an existing local pattern. | Code change, corresponding `run_deep_matcher_sanity.py` regression, targeted re-check of the affected examples, and `dev_reload.py` before cache/UI validation. Do not add fixture/inventory unless escalating to Track B. |
| Track B: durable registry/contract rule | Registry-owned vocabulary/rules, broad or systemic semantics, routing/bridge/no-match policy, release hardening, or anything that should become permanent contract proof. | TOML under `term_registry/entries/`, TOML under `matcher_contracts/sources/`, generated matcher contract JSON, bridge/no-match/routing exports, support-check contracts. | Fixture(s), inventory, registry/model checks, targeted/full fixture and parity gates, and cache freshness when cache-backed validation or release matters. |

Escalate Track A to Track B when the fix is broad, semantic, cross-canonical,
registry-owned, route-affecting, cache/release-facing, or likely to be useful as
future regression documentation. Do not escalate routine narrow
dictionary/runtime hygiene just because the matcher has a durable contract
system.

## Golden Rule

A matcher rule is done only when its semantic decision has the right proof for
its track.

For Track A, "done" means:

- the runtime fix is narrow and placed beside the existing local mechanism
- a corresponding focused regression exists in `run_deep_matcher_sanity.py`
- `run_deep_matcher_sanity.py` passes
- the affected examples were re-checked
- cache-backed validation was refreshed with `dev_reload.py` when the cache/UI is
  part of the decision

For Track B, the semantic decision and the regression proof land together:

- runtime rule or registry entry
- focused `run_deep_matcher_sanity.py` regression
- positive fixture when the rule creates or preserves a match
- negative sibling fixture when the rule blocks or broadens a family
- rule inventory entry connected to those fixtures
- targeted fixture/parity checks
- full fixture/parity checks
- inventory/model checks

Do not treat a live diagnostic, an ad hoc note, or a one-off sanity test as the
durable source of truth for Track B. The durable contract is:

- `app/languages/sv/matcher_contracts/sources/matcher_regression_cases.toml`
- `app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml`

The corresponding JSON files are generated artifacts and must match those TOML
sources byte-for-byte. Pre-flight rejects generated JSON drift.

The term registry is the durable vocabulary surface. Runtime modules such as
`synonyms.py`, `parent_maps.py`, `keywords.py`, `match_bridges.py`, and
`no_match_policies.py` import selected registry exports. If a change is a
vocabulary or declarative-rule change, prefer tracked registry TOML over editing
runtime exports directly.

## First Triage

Before editing, answer these questions in the work notes:

1. Did this start as an observed FP/FN, an existing fixture failure, a
   diagnostic/parity failure, or stale cache?
2. Is this Track A tactical hygiene or Track B durable contract work?
3. Which canonical term should own the rule?
4. Is the change exact and narrow, or can it affect a broader product family?
5. What positive case must keep working?
6. What negative case proves the bug is fixed?
7. Does this belong in the term registry, a declarative rule, or legacy runtime
   Python?

If cache freshness is stale, separate that from semantic correctness. Use
`--skip-cache-freshness` only to isolate fixture semantics. The final cache-based
gate must pass without skipping freshness after rebuild.

## Matcher Vocabulary

These terms are used throughout the matcher and this runbook:

| Term | Meaning |
| --- | --- |
| canonical | The normalized ingredient family the matcher materializes, such as `filmjölk` or `kalkon`. |
| fixture | A durable recipe/offer case in the matcher contract TOML source, proving expected match or no-match behavior. |
| inventory | The durable TOML rule/source inventory explaining which rule/source owns each fixture. |
| policy_ref | Stable semantic family name for a rule decision. |
| source_ref | Stable provenance/reference for why a fixture or inventory entry exists. |
| route term | Term-index vocabulary used to decide whether an offer should be considered for an ingredient. |
| bridge | Declarative ingredient-pattern to offer-pattern match rule. |
| no-match policy | Declarative ingredient-pattern plus blocked offer keyword/pattern rule. |
| PNB | `PRODUCT_NAME_BLOCKERS`: product text blocks a matched keyword unless ingredient also asks for it. |
| FPB | `FALSE_POSITIVE_BLOCKERS`: ingredient text suppresses a keyword when it only appears inside a blocker context. |
| GPB | `GLOBAL_PRODUCT_NAME_BLOCKERS`: product text blocks all recipe matches for globally excluded non-food, supplement, pet-food, tool, or similar product families. |
| BDPK | `BIDIRECTIONAL_PER_KEYWORD`: product and ingredient qualifiers must agree for a keyword. |
| KSBC | `KEYWORD_SUPPRESSED_BY_CONTEXT`: suppresses a generic keyword when ingredient context makes it irrelevant. |
| parity | Agreement between live/fullscan, compiled/fullscan, compiled/routed, and compiled/hint-first paths. |
| freshness | Whether compiled recipe/offer data, term indexes, and active cache use current matcher/compiler versions. |

For false positives caused by newly launched product variants, prefer a family
rule over enumerating future products. Example: "plain recipe requires plain
product" for a plain-sensitive base such as `filmjölk` is better than adding one
blocker for every new flavor.

## Pick The Change Surface

Prefer the highest-level surface that fits the chosen track. For Track B, favor
durable registry/contract surfaces. For Track A, a narrow legacy runtime dict
can be the correct surface.

| Change type | Prefer | Use when | Avoid |
| --- | --- | --- | --- |
| Exact synonym or spelling alias | `term_registry/entries/keyword_synonym.toml` or parent/routing registry entry | One term is the same ingredient family as another. | Ad-hoc extraction code for a plain alias. |
| Ingredient/offer bridge (recipe wording differs from product wording) | `term_registry/entries/keyword_extra_parent.toml` (preferred) or `ingredient_parent.toml` | Recipe term and product term differ but should match (e.g. `nori` → `alger`, `citrusfrukter` → `citron`/`lime`/`apelsin`). These TWO surfaces are wired into the runtime matcher today. | Adding only to `match_bridge.toml`. That surface is **declarative-only / staged for migration** — it does not affect runtime routing on its own. See the match_bridge note below the table. |
| No-match/blocking policy | `term_registry/entries/no_match_policy.toml` | Ingredient pattern plus offer keyword/pattern should never match. | One-off Python if a declarative policy can express it. |
| Offer keyword extraction | `term_registry/entries/offer_extra_keyword.toml` or `extraction.py` | Product wording should expose an additional canonical offer keyword. | Adding recipe synonyms when only offer extraction is missing. |
| Recipe extraction helper | `term_registry/entries/extraction_helper.toml` or `extraction.py` | Ingredient text needs a hardcoded extraction output that cannot be expressed as a plain synonym. | Broad helper output without route/parity fixtures. |
| Parent/canonical fallback | `ingredient_parent.toml`, `parent_match_only.toml`, or `keyword_extra_parent.toml` | A child term should expose a broader canonical, sometimes only for matching. | Parent mappings that erase meaningful product-form differences. |
| Ingredient-context blocker | `blocker_data.py` / `FALSE_POSITIVE_BLOCKERS` | Ingredient wording contains a keyword only inside a context that should suppress it. Common Track A tactical fix. | Offer/product variant blocking; use a product-side blocker or form/specialty rule after confirming the issue is product-side. |
| Product-name blocker | `blocker_data.py` / `PRODUCT_NAME_BLOCKERS` | Offer/product wording contains a per-keyword variant, carrier, product type, or flavor that should block the matched keyword. Common Track A tactical fix. | Large flavor/form families that should be modeled declaratively. |
| Global product-name blocker | `blocker_data.py` / `GLOBAL_PRODUCT_NAME_BLOCKERS` | The product is globally non-food or globally out of matcher scope regardless of which keyword matched. Common for supplements, pet food, tools, tobacco, cleaning, and similar products. | Food products that can be legitimate for some recipe wording; use scoped PNB/no-match policy instead. |
| Form or processed-state rule | `form_rules.py`, `processed_rules.py`, or a dedicated declarative form engine | Fresh/dried/frozen/cooked/plain semantics are the actual decision. | Listing every future flavor or cooked variant by hand. |
| Qualifier or bidirectional variant | `specialty_rules.py` | Product qualifier must also appear in the ingredient, or ingredient qualifier must appear in product. | Raw substring checks without word-boundary handling. |
| Declarative bridge guard | `match_bridge.toml` nested `blockers` / `backend_allowances` | A bridge needs scoped negative guards or backend allowance metadata with fixture refs. | Hiding broad bridge behavior in unrelated backend code. |
| Backend-only validation | `recipe_matcher_backend.py` | The rule needs recipe context, retry behavior, or materialization-time validation. | Fixing only backend when fast/fullscan/routing also need the rule. |
| Routing-only gap | `ingredient_routing_parent.toml`, `recipe_routing_helper.toml`, or `term_indexes.py` helper | Fullscan matches but routed cache never sees the pair. | Backend allowances that hide missing route terms. |
| Canonical conflict | parent/equivalence/precedence metadata, or a narrower bridge | Diagnostics reports duplicate signal source or ambiguous canonical. | Accepting duplicate canonicals without a declared relationship. |

If the right surface is unclear, write the fixture first and run diagnostics.
Let the failing layer choose the implementation point.

### Important: `match_bridge.toml` is declarative-only today

`app/languages/sv/ingredient_matching/match_bridges.py` is staged for matcher
migration. Adding a new entry to `match_bridge.toml` does **not** affect the
production matcher — `find_match_bridge_hits` is only called from support_checks
(diagnostics, audit), never from `recipe_matcher_backend.py` or the runtime
matcher. The script `run_term_registry_guard_bridge_checks.py` enforces this:
any active bridge whose `(canonical, plain offer_pattern)` pair is not covered
by `KEYWORD_EXTRA_PARENTS`, `INGREDIENT_PARENTS`, `KEYWORD_SYNONYMS`, or
`OFFER_EXTRA_KEYWORDS` fails with `match_bridge_not_runtime_wired` and tells you
which dual-write TOML row to add.

For new routing/aliasing work today, write to one of these wired surfaces
instead:

| You want to … | Write to |
| --- | --- |
| Roll an offer keyword up to a parent ingredient (e.g. `nori` → `alger`, `citron` → `citrusfrukter`) | `term_registry/entries/keyword_extra_parent.toml` |
| Treat a recipe-side variant as a known parent ingredient (e.g. `noriblad` → `nori`) | `term_registry/entries/ingredient_parent.toml` |
| Add a spelling/plural alias normalized on both sides | `term_registry/entries/keyword_synonym.toml` |
| Add a product-side keyword that maps to an existing ingredient | `term_registry/entries/offer_extra_keyword.toml` |

If you really need to add a `match_bridge.toml` entry (e.g. you are continuing
the staged migration), dual-write the corresponding `keyword_extra_parent.toml`
/ `ingredient_parent.toml` rows in the same change, otherwise the wiring check
will fail.

## How To Decide Quickly

Make two decisions: first choose the work track, then choose the matcher layer.

### Choose The Track

Use the TL;DR Track A/Track B rule at the top of this file, then check the
reference table in Two Work Tracks when the decision is ambiguous. If the case
is only stale cache, refresh cache before judging semantics.

### Choose The Layer

Use this layer decision tree after choosing Track A or Track B:

1. Does the ingredient and offer already match in fullscan but not routed cache?
   Start with routing terms, parent/routing registry entries, or term-index
   helpers.
2. Does routing reach the pair but `matches_ingredient_fast` returns no keyword?
   Start with synonym/bridge/parent/extraction rules.
3. Does fast match return a keyword but backend validation rejects it?
   Start with validator, product-name blocker, specialty, or scoped backend
   allowance.
4. Does a negative case still match everywhere?
   Start with `NoMatchPolicy`, PNB, form/processed rule, or a family-level
   blocker.
5. Does the case pass but diagnostics reports duplicate or ambiguous signals?
   Start with precedence, parent/equivalence, narrower bridge, or removing a
   duplicate signal.
6. Are checks blocked by cache freshness before any semantic result?
   Rebuild/refresh cache. Do not call a semantic failure fixed or broken based
   only on stale compiled/cache data.

## Track A Runtime Workflow

Use this path for the common case: a concrete false positive or false negative
where the fix is a narrow runtime dictionary/guard.

1. Reproduce the example enough to identify the keyword/canonical, offer name,
   and ingredient text. A small inline diagnostic is fine.
2. Patch the narrow existing mechanism: usually `FALSE_POSITIVE_BLOCKERS`,
   `PRODUCT_NAME_BLOCKERS`, `GLOBAL_PRODUCT_NAME_BLOCKERS`,
   specialty/form/processed rules, or a local backend guard that already owns
   the pattern.
3. Add or adjust a focused regression inside `run_deep_matcher_sanity.py` for
   every new rule. If a nearby case already asserts the exact same behavior,
   keep or extend that case rather than duplicating it. This script is the
   primary Track A sanity gate and should grow over time with new matcher rules.
4. Run the standard Track A gate wrapper:

   ```bash
   docker compose exec -T -w /app web \
     python support_checks/run_matcher_change_gates.py --track A
   ```

   This runs the primary deep matcher sanity gate and the full matcher parity
   gate with cache freshness skipped.

5. If you run manually instead of using the wrapper, run the fixture parity check
   to confirm no existing fixture contracts were broken by the change. This is
   mandatory even for Track A — you are responsible for leaving parity clean,
   not the next agent:

   ```bash
   docker compose exec -T -w /app web \
     python support_checks/run_deep_matcher_sanity.py

   docker compose exec -T -w /app web \
     python support_checks/run_matcher_layer_parity.py --skip-cache-freshness
   ```

   If any fixture fails, fix the code when the new behavior is wrong. If the
   fixture expectation should intentionally change, stop treating the work as
   Track A and escalate to Track B before updating fixture/inventory contracts.
   Do not commit with known parity failures.

6. If any cache-backed validation, UI check, or cache-gated support check will be
   used after the edit, run the wrapper with cache refresh:

   ```bash
   docker compose exec -T -w /app web \
     python support_checks/run_matcher_change_gates.py --track A \
       --reload-cache --fresh-cache-gates
   ```

7. Re-check the affected examples against the refreshed runtime/cache.

Do not add matcher contract fixture or inventory entries for Track A fixes by
default. Escalate to Track B first if the rule becomes broad, registry-owned,
route-affecting, release-facing, or valuable permanent regression
documentation.

## Track B Required Artifacts

This section is mandatory for Track B durable changes. It is optional for Track
A tactical fixes unless you explicitly escalate them.

### Fixtures

Add or update cases in:

```text
app/languages/sv/matcher_contracts/sources/matcher_regression_cases.toml
```

Use stable IDs. Do not use temporary import/review IDs for permanent fixtures.
Do not use batch numbers, question numbers, local queue names, or other
ephemeral review coordinates in `id`, `policy_ref`, `source_ref`, TOML
`entry_id`, `source_refs`, `supersedes`, or generated baseline metadata. Those
coordinates are not persisted as durable context. Translate them to stable
semantic names before committing, for example
`current_review:plain_sensitive_filmjolk`,
`legacy_review:fresh_champinjoner_preserved_products_guard`, or
`manual:mozzarella_bufala_guard`.

When migrating older review material, prefer "migrated legacy review" wording
and `legacy_review:<semantic_case>` references. Do not introduce new
`legacy_auto_promoted_*`, `batch*_q*`, `questions_q*`, or similar process-based
names; they describe how data moved, not what behavior the rule protects.

Common fields:

```toml
[[fixtures]]
id = "matcher_regression_example_positive"
policy_ref = "plain_sensitive_filmjolk"
source_ref = "current_review:plain_sensitive_filmjolk"
recipe_name = "Sanity Recipe"
ingredients = ["3 dl filmjölk"]
expected = 1

[fixtures.offer]
name = "Filmjölk Naturell Arla"
category = "dairy"

[[fixtures.expected_matches]]
ingredient_index = 0
canonical = "filmjölk"
must_match_keyword = "filmjölk"
```

For negative cases, omit `expected_matches` and set `expected` to `0`.

Allowed permanent `source_ref` prefixes are:

| Prefix | Use when | Example |
| --- | --- | --- |
| `current_review:` | The fixture comes from the active matcher review/triage work. | `current_review:plain_sensitive_filmjolk` |
| `legacy_review:` | The fixture preserves behavior discovered in older review notes or migrated historical cases. | `legacy_review:cache_build_path_divergence` |
| `manual:` | A human or agent added a standalone rule from direct domain reasoning, not from a named plan or imported review set. | `manual:mozzarella_bufala_guard` |
| `plan_initial:` | The fixture implements an initial case named by a planning document. | `plan_initial:systemic_fp_plain_dairy` |
| `sanity:` | The fixture is a small invariant used as a sanity/regression anchor. | `sanity:pnb_plain_positive_guard` |

The machine-readable allow-list lives in
`app/support_checks/schemas/prefixes.yml`. Update that schema first when a new
permanent prefix is genuinely needed; pre-flight, fixture schema checks,
inventory checks, and audit checks read from it.

### Inventory

Update:

```text
app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml
```

Every fixture should be connected to at least one inventory rule. Inventory
entries should include:

- stable `id`
- `canonical`
- `policy_ref`
- `source_refs`
- `fixture_refs`
- `status`
- `kind`
- `risk`
- `line_refs` when the rule lives in Python/TOML code
- `adapter_ref` when a registry-backed adapter owns the behavior

After changing anchors or moving code, refresh line refs:

```bash
# Host checkout only. Do NOT run this via docker compose exec.
python3 app/support_checks/refresh_matcher_rule_inventory_line_refs.py --write
```

This is the deliberate exception to the mostly-containerized commands in this
runbook. Use the host command above because the normal compose web service
mounts `/app` read-only. If you run this inside a container, make sure that
container has a writeable checkout mounted. The refresh updates the authoritative
inventory TOML source and regenerates the generated inventory JSON.

### Registry Entries

If the change uses the term registry, edit the relevant TOML file under:

```text
app/languages/sv/ingredient_matching/term_registry/entries/
```

Common files:

- `extraction_helper.toml`
- `ingredient_parent.toml`
- `ingredient_routing_parent.toml`
- `keyword_extra_parent.toml`
- `keyword_synonym.toml`
- `match_bridge.toml`
- `no_match_policy.toml`
- `offer_extra_keyword.toml`
- `parent_match_only.toml`
- `recipe_routing_helper.toml`

Registry entries should include coverage rows and examples that describe the
same decision as the fixture. For registry-owned `MatchBridge` and
`NoMatchPolicy`, keep `fixture_refs` inside the language payload in sync with
the fixture file.

Do not hand-edit these two coverage files for ordinary fixture/inventory work:

- `matcher_regression_case.toml`
- `matcher_rule_inventory.toml`

They are generated from the generated JSON contracts by:

```bash
python3 app/support_checks/generate_matcher_registry_coverage.py --write
```

The Track B wrapper automatically regenerates the JSON contracts first and
then runs the coverage generator when fixture or inventory changes are selected.
The JSON contracts themselves are generated from the TOML sources by:

```bash
python3 app/support_checks/generate_matcher_contract_json_from_toml_sources.py --write
```

Pre-flight fails with `matcher_contract_generated_json_drift` if generated JSON
does not match the TOML sources, and with `generated_coverage_stale` if the
checked-in registry coverage TOML no longer matches the generated JSON-derived
output. Intentional manual coverage is allowed only as a narrow exception: put
`# manual-coverage` directly before the manual `[[entries]]` block so the
generator preserves it.

The registry also supports local dev entry directories under
`/app/data/term_registry/sv/entries` via `TERM_REGISTRY_LOCAL_ENTRIES_DIR`.
Those are useful for experiments, but durable matcher rules should be promoted
to tracked TOML under `app/languages/sv/ingredient_matching/term_registry/entries/`.

### Inactivating Or Removing Registry Entries

Inactivating TOML entries is Track B when it changes matcher behavior. Treat it
as a semantic removal, not as harmless cleanup.

Use this path for cases such as "generic `potatis` should no longer inherit
specific varieties from inactive `färskpotatis`/`bakpotatis` registry rows."

1. Prefer `status = "inactive"` over deleting the TOML row. Keep enough
   context in comments/notes to explain why the entry is inactive.
   (Allowed status values: `active`, `deprecated`, `planned`, `watchlist`,
   `inactive`.)
2. Add or confirm the runtime/sanity proof:
   - positive guard for the generic behavior that should remain
   - negative case proving the inactive/specific behavior is gone
3. Add or update Track B fixtures when the behavior change should be durable.
   Inactivation that changes matching should have fixture/inventory proof just
   like adding a rule.
4. Update inventory to explain the owner and reason for the inactivation.
5. Run `promote_term_baseline.py`.

If `promote_term_baseline.py` aborts with "truly removed" variants, treat that
as a semantic deletion until proven otherwise. Content-equivalent verified-term
ID changes are migrated automatically; only true removals need approval.

The accepted intentional-removal flow is:

1. Confirm each removed variant ID corresponds to the TOML entry you just
   inactivated or removed. If any removed variant is unexpected, stop.
2. Re-run promotion with explicit removal approval:

   ```bash
   docker compose exec -T -w /app web \
     python support_checks/promote_term_baseline.py --allow-removals
   ```

3. Run the registry contract checks and full Track B gates.

`promote_term_baseline.py` (with or without `--allow-removals`) auto-updates the
relevant baseline JSON fields (`variant_count`, `source_counts`, `role_counts`,
`status_counts`, `classification_counts`) and the `EXPECTED_VERIFIED_TERM_VARIANT_COUNT`
constant in `run_term_registry_contract_checks.py`. Do not patch these by hand.

Manual baseline JSON edits are a last resort. Use them only if the promotion
script cannot write/stage the intended files, and record that clearly in the
handoff.

Nested declarative bridge payloads can include:

- `blockers` as `BlockerRule`
- `backend_allowances` as `BackendAllowance`
- `ingredient_form_signals`
- `offer_form_signals`
- `required_offer_form_signals`
- `forbidden_offer_form_signals`

These nested rules still need `fixture_refs` and should be represented in the
main fixture/inventory contract.

The validation-first model types in `rule_models.py` are:

- `MatchBridge`
- `NoMatchPolicy`
- `BlockerRule`
- `BackendAllowance`
- `RouteExpansion`
- `CanonicalEquivalence`
- `SignalSource`

Not every model type has a first-class registry export today. If a change uses
one directly, document the ownership in inventory and add fixture refs just as
strictly as for registry-owned bridges and no-match policies.

### Runtime Code

If runtime Python is changed, keep the change narrow and place it beside the
existing local mechanism. Examples:

- `blocker_data.py` for FPB, PNB, and GPB runtime blockers
- `carrier_context.py` for carrier products, context-required carriers, and
  context suppression
- `specialty_rules.py` for qualifier/bidirectional rules
- `processed_rules.py` for processed-state product rules
- `form_rules.py` for fresh/dried/frozen form rules
- `dairy_types.py` for dairy-family type checks
- `recipe_text.py` or `recipe_context.py` for recipe-title/context-sensitive
  requirements
- `offer_data.py` for precomputed offer payload changes
- `recipe_matcher_backend.py` for backend validation/retry logic
- `matching.py` only when fast path or direct ingredient matching also needs the
  behavior

When a backend validator changes, check whether `matches_ingredient_fast`,
diagnostics, and routed parity need the same semantic check. Backend-only fixes
can make live diagnostics look right while cache/routing still diverges.

## Track B Standard Workflow

Use this workflow for durable registry/contract changes and for any Track A fix
you intentionally escalated.

### 1. Reproduce

Run the smallest diagnostic or fixture case that proves the current behavior.
Inline diagnostics are useful before a fixture exists:

```bash
docker compose exec -T -w /app web \
  python support_checks/matcher_layer_diagnostics.py \
  --ingredient "3 dl filmjölk" \
  --offer-name "Filmjölk Lemonad Arla" \
  --offer-category "dairy"
```

For existing fixtures:

```bash
docker compose exec -T -w /app web \
  python support_checks/run_matcher_layer_fixture_cases.py \
  --case-id matcher_regression_example_positive \
  --skip-cache-freshness
```

Use `--skip-cache-freshness` only during semantic isolation.

### 2. Implement The Smallest Rule

Make the runtime or registry change.

For broad false-positive families, do not add one blocker per newly launched
product flavor if the real rule is "plain recipe requires plain product".
Create or extend a family-level rule instead.

For broad false-negative families, avoid making a parent term too permissive.
Add a positive fixture and a nearby negative sibling before widening a route or
bridge.

### 3. Add Fixtures

Add the minimum durable cases:

- Positive case for a new/kept match.
- Negative case for a blocker or any broadening rule.
- Positive sibling for any new blocker that could over-block a legitimate
  product.

If a rule is intentionally broad, add more than one negative case and at least
one positive guard.

### 4. Update Inventory

Add or update inventory entries and line refs. The inventory should explain why
the rule exists, not just where the code lives.

If the runtime rule is registry-owned, prefer `adapter_ref` to point at the
exported adapter. If it is legacy Python, use stable `line_refs.anchor` strings.

### 5. Run Targeted Gates

Target the policy, canonical, or case IDs first:

```bash
docker compose exec -T -w /app web \
  python support_checks/run_matcher_layer_fixture_cases.py \
  --policy-ref plain_sensitive_filmjolk \
  --skip-cache-freshness

docker compose exec -T -w /app web \
  python support_checks/run_matcher_layer_parity.py \
  --policy-ref plain_sensitive_filmjolk \
  --skip-cache-freshness
```

Use `--canonical` when several policies share the same canonical:

```bash
docker compose exec -T -w /app web \
  python support_checks/run_matcher_layer_parity.py \
  --canonical filmjölk \
  --skip-cache-freshness
```

Targeted parity is required for Track B route, bridge, no-match, canonical, and
cache-facing changes. For a plain Track A PNB/FPB/GPB fix, use the Track A
workflow instead. Track A still runs the full fixture parity gate, but it should
not use Track B fixture/inventory edits unless the work is escalated.

### 6. Run Contract Gates

Prefer the gate wrapper for standard Track B work:

```bash
docker compose exec -T -u appuser -w /app web \
  python support_checks/run_matcher_change_gates.py --track B \
    --policy-ref plain_sensitive_filmjolk
```

For fixture/inventory Track B changes, the wrapper first refreshes generated
coverage TOML. For registry changes, it then promotes the verified-term
baseline unless you pass `--skip-baseline-promotion`. The first validation gate
after those maintenance steps is matcher change pre-flight, which aggregates
schema, prefix, line-ref, coverage, and expected-count problems before the
slower matcher gates run:

```text
Matcher change pre-flight
NEW=0 KNOWN=0 FIXED=0
```

`NEW` issues block the wrapper. `KNOWN` issues come only from the safety-valve
snapshot at `app/support_checks/baselines/known_infrastructure_issues.json`.
That snapshot should normally be empty on `main`; do not add to it unless there
is a short-lived tracked cleanup reason. `FIXED` means a previously tolerated
issue disappeared and the snapshot should be refreshed.

Useful wrapper options:

- `--registry-changed`, `--runtime-changed`, `--fixtures-changed`, and
  `--inventory-changed` override git auto-detection when the worktree contains
  unrelated edits.
- `--allow-removals` is passed to `promote_term_baseline.py` after confirmed
  intentional TOML inactivation/removal.
- `--refresh-line-refs` runs the host-only inventory line-ref refresher.
- `--no-generate-coverage` disables the automatic derived coverage refresh
  when you intentionally want pre-flight to report stale coverage.
- `--baseline-output-dir` stages baseline promotion output and stops; apply the
  staged files, then rerun the wrapper without that flag.
- `--reload-cache --fresh-cache-gates` adds `dev_reload.py` and final
  cache-fresh fixture/parity gates.
- `--dry-run` prints the exact script list without running it.

Do not run every script reflexively when running manually. Use this matrix to
choose the smallest complete gate set for the change.

| Gate | Run when |
| --- | --- |
| `run_deep_matcher_sanity.py` | Every Track A fix and every Track B runtime semantic change. |
| targeted `run_matcher_layer_fixture_cases.py` | Track B fixture/rule work for the affected `--policy-ref`, `--canonical`, or `--case-id`. |
| targeted `run_matcher_layer_parity.py` | Track B route, bridge, no-match, canonical, cache-facing, or fixture behavior work. |
| `generate_matcher_contract_json_from_toml_sources.py --write` | Fixture or inventory TOML source changed. The wrapper runs this automatically before coverage. |
| `generate_matcher_registry_coverage.py --write` | Fixture or inventory contract changed. The wrapper runs this by default after JSON generation. |
| full `run_matcher_layer_fixture_cases.py --skip-cache-freshness` | Every Track B behavior change before handoff. |
| full `run_matcher_layer_parity.py --skip-cache-freshness` | Every Track A/Track B matcher behavior change before handoff. |
| `promote_term_baseline.py` | Any tracked registry TOML change. Use the plain command unless confirmed TOML inactivation/removal requires `--allow-removals`. |
| term-registry checks | Any tracked registry TOML or baseline change. |
| `run_matcher_rule_model_checks.py` | Track B rule-model, bridge, no-match, inventory, or registry-owned rule changes. |
| `run_matcher_rule_inventory_checks.py` | Any inventory change or Track B rule that should be inventory-owned. |
| `run_matcher_version_checks.py` | After final generated/contract state for matcher behavior changes. |
| `run_sanity_checks.py` | Runtime Python changes with broader app-support risk, or after baseline promotion if the promotion script updates support-check expectations. |
| support-check self-checks | Support-check code/schema/diagnostics/parity tooling changes only. |
| `dev_reload.py` | Cache/UI/cache-gated validation, or when handing off a change that must be visible in active dev cache. |

Full Track B fixture and inventory gates:

```bash
docker compose exec -T -w /app web \
  python support_checks/run_matcher_layer_fixture_cases.py --skip-cache-freshness

docker compose exec -T -w /app web \
  python support_checks/run_matcher_layer_parity.py --skip-cache-freshness

docker compose exec -T -w /app web \
  python support_checks/run_matcher_rule_model_checks.py

docker compose exec -T -w /app web \
  python support_checks/run_matcher_rule_inventory_checks.py
```

If the term registry TOML changed, run the verified-term baseline promotion
before final registry gates. It may report no changes, but it is still the
standard gate after TOML edits. Verified-term IDs are stable across `source_ref`
provenance edits; content-equivalent ID migrations are automatic.

In a writable checkout/container, use the plain command as `appuser` unless
intentional TOML inactivation/removal requires removal approval:

```bash
# Choose exactly one:
docker compose exec -T -u appuser -w /app web \
  python support_checks/promote_term_baseline.py

# OR, when TOML inactivation/removal intentionally removed verified variants:
docker compose exec -T -u appuser -w /app web \
  python support_checks/promote_term_baseline.py --allow-removals
```

If the checkout is read-only, stage the generated files under a writable
directory, again choosing either the plain or removal-approved variant as
appropriate, and then apply the staged changes to the real checkout:

```bash
# Choose exactly one:
docker compose exec -T -w /app web \
  python support_checks/promote_term_baseline.py \
  --output-dir /tmp/term-baseline-promotion

# OR, when TOML inactivation/removal intentionally removed verified variants:
docker compose exec -T -w /app web \
  python support_checks/promote_term_baseline.py \
  --allow-removals \
  --output-dir /tmp/term-baseline-promotion
```

Then run the registry checks:

```bash
docker compose exec -T -w /app web \
  python support_checks/run_term_registry_contract_checks.py --language sv

docker compose exec -T -w /app web \
  python support_checks/run_term_registry_add_term_checks.py --language sv

docker compose exec -T -w /app web \
  python support_checks/run_term_registry_export_checks.py --language sv

docker compose exec -T -w /app web \
  python support_checks/run_term_registry_guard_bridge_checks.py --language sv
```

After any baseline promotion and registry checks, run matcher version checks.
This ordering keeps the version gate pointed at the final generated/current
contract state:

```bash
docker compose exec -T -w /app web \
  python support_checks/run_matcher_version_checks.py
```

Run sanity checks when runtime code changed. Every new matcher rule must have
a corresponding focused regression in `run_deep_matcher_sanity.py`, whether the
rule is Track A or Track B. For Track A, the deep matcher sanity script is the
primary gate and should already have been run. For Track B runtime changes, run
both the broad sanity suite and the deep matcher suite:

```bash
docker compose exec -T -w /app web \
  python support_checks/run_sanity_checks.py

docker compose exec -T -w /app web \
  python support_checks/run_deep_matcher_sanity.py
```

The parity self-check suite below is for support-check code, fixture schema
code, diagnostics code, parity tooling, or hard-coded support-check expectation
changes. It is not a routine tactical rule gate:

```bash
docker compose exec -T -w /app web \
  python support_checks/run_matcher_layer_fixture_schema_checks.py

docker compose exec -T -w /app web \
  python support_checks/run_matcher_layer_diagnostics_checks.py

docker compose exec -T -w /app web \
  python support_checks/run_matcher_layer_parity_checks.py
```

Run a whitespace check before handing off:

```bash
git diff --check
```

### 7. Check Cache Freshness Separately

Semantic fixture/parity can be checked without cache freshness, but release or
cache-backed validation cannot. Any cache-gated check or UI validation after
matcher code changes must run against a refreshed cache.

Inspect cache freshness:

```bash
docker compose exec -T -w /app web python - <<'PY'
from support_checks.matcher_layer_diagnostics import check_cache_freshness
import json
print(json.dumps(check_cache_freshness(), ensure_ascii=False, indent=2, sort_keys=True))
PY
```

If stale, or if matcher runtime code changed since the current cache was built,
hot-reload matcher modules and rebuild the dev cache:

```bash
docker compose exec -T -w /app web python support_checks/dev_reload.py
```

Then rerun freshness diagnostics. Do not treat cache-backed validation as final
until cache freshness is clean.

Then run the fixture/parity gates without `--skip-cache-freshness`:

```bash
docker compose exec -T -w /app web \
  python support_checks/run_matcher_layer_fixture_cases.py

docker compose exec -T -w /app web \
  python support_checks/run_matcher_layer_parity.py
```

For large matcher/cache releases or suspected active-cache drift, run the heavy
read-only DB diff:

```bash
docker compose exec -T -w /app web \
  python support_checks/run_matcher_full_db_diff.py --sample-limit 25
```

Do not run full DB diff as a routine quick check.

## Failure Interpretation

Use the diagnosis class to choose the next move:

| Diagnosis | Meaning | Usual next action |
| --- | --- | --- |
| `route_pair_missing` | Routing never sends the offer to the ingredient. | Add route/term-index exposure, then parity. |
| `fast_match_missing` | Routing reaches the pair but fast match rejects it. | Add bridge/synonym/fast-path rule, with negative sibling. |
| `backend_validation_rejected` | Initial match exists but backend validator blocks it. | Review validator or add scoped allowance. |
| `unexpected_positive` | A negative fixture still materializes. | Add/tighten no-match policy or blocker. |
| `duplicate_signal_source` | Same canonical comes from competing signal sources. | Declare precedence/equivalence or retire duplicate source. |
| `ambiguous_canonical` | One case exposes competing canonicals. | Add parent/equivalence/precedence or narrow the rule. |
| `cache_freshness_blocked` | DB cache/compiled data is stale. | Rebuild/refresh cache, then rerun without skipping freshness. |

`parity_mismatches=0` means the live/fullscan/compiled/routed paths agree with
each other. It does not mean fixture expectations are satisfied.

## Common Pitfalls

- Track A: forcing every PNB/FPB/GPB runtime fix through fixture/inventory before
  it can land.
- Track A: calling a tactical fix durable without escalating it to Track B and
  adding contract proof.
- Track A: adding a new matcher rule without a corresponding focused
  `run_deep_matcher_sanity.py` regression.
- Track A: skipping `run_matcher_layer_parity.py --skip-cache-freshness`. Track A
  fixes can break existing parity fixtures; leave parity clean before committing.
- Track A: running heavy support-check self-check/model suites
  (`run_matcher_layer_parity_checks.py`, `run_matcher_rule_model_checks.py`) as
  routine Track A gates. These are Track B/tooling checks.
- Track B: adding a runtime rule without a fixture.
- Track B: adding a fixture without inventory coverage.
- Track B: hand-editing generated JSON or generated registry coverage TOML
  instead of editing the authoritative TOML source and regenerating.
- Track B: updating registry TOML without running `promote_term_baseline.py` and
  the registry checks.
- Track B: treating TOML inactivation/removal as pure cleanup when it changes
  matcher behavior. It needs fixture/inventory proof, and intentional
  verified-term removals need the explicit removal workflow.
- Track B: treating a "truly removed" promotion warning as harmless.
  Content-preserving verified-term ID changes are automatic; true removals need
  explicit approval.
- Track B: using raw substring checks for words that need word boundaries.
- Track B: fixing backend validation but forgetting `matches_ingredient_fast`.
- Track B: broadening a bridge without a negative sibling.
- Track B: adding `OFFER_EXTRA_KEYWORDS` or extraction output without making sure
  routed cache sees the same term family.
- Track B: adding parent mappings where a scoped `MatchBridge` would be safer.
- Track B: forgetting nested `blockers` or `backend_allowances` when a bridge is
  mostly right but has known guarded exceptions.
- Track B: adding product-name blockers for every flavor when a plain-sensitive
  family rule is the real model.
- Track B: skipping parity for route/bridge/release work.
- General: letting stale cache explain away a semantic fixture failure.
- General: forgetting `dev_reload.py` before cache-backed validation after
  matcher runtime changes.
- General: treating `app/tests/` workbench files as permanent regression
  contracts.
- General: leaving experimental local registry files under
  `/app/data/term_registry/` instead of promoting durable entries to tracked
  TOML.
- General: promoting regenerated support reports from `/tmp/deal-meals-support-checks/`
  to Git.
- General: forgetting to refresh inventory line refs after moving anchors.
- General: updating hard-coded support-check expectations when the real issue is
  stale generated/check data, or vice versa. Read the failure before patching
  counts.

## Minimal Done Checklist

Before calling a Track A runtime fix done:

- The fix is narrow enough to stay Track A.
- The change uses the existing local runtime mechanism, such as PNB, FPB, GPB,
  specialty/form/processed rule, or a local backend guard.
- A corresponding focused regression was added or confirmed in
  `run_deep_matcher_sanity.py`.
- No matcher contract fixture/inventory entry was added unless the fix was
  escalated to Track B.
- `run_deep_matcher_sanity.py` passes.
- `run_matcher_layer_parity.py --skip-cache-freshness` passes. You are
  responsible for leaving parity clean. If a fixture fails, fix the code; if the
  fixture expectation should intentionally change, escalate to Track B before
  updating fixture/inventory. Do not delegate parity verification to the next
  agent.
- The affected examples or diagnostics were re-checked.
- `dev_reload.py` was run before cache-backed/UI validation when cache state
  matters.
- You escalated to Track B if the rule became broad, registry-owned,
  route-affecting, release-facing, or useful as permanent regression proof.

Before calling a Track B matcher rule change done:

- The chosen rule surface is the narrowest correct one.
- Fixtures cover the positive and negative behavior.
- Inventory covers every new or changed fixture.
- Registry entries, if any, include coverage and examples.
- A corresponding focused regression was added or confirmed in
  `run_deep_matcher_sanity.py`.
- `promote_term_baseline.py` was run after registry TOML changes, using
  `--allow-removals` only for confirmed intentional TOML inactivation/removal.
- Intentional TOML inactivation/removal followed the removal workflow if
  `promote_term_baseline.py` reported truly removed variants.
- Targeted fixture/parity passes.
- Full fixture/parity passes with `--skip-cache-freshness`.
- Rule model and inventory checks pass.
- Matcher version checks pass.
- Registry checks pass if registry TOML changed.
- Sanity/deep sanity pass if runtime Python changed.
- Support-check self-checks pass if support-check code or hard-coded support
  expectations changed.
- `git diff --check` passes.
- Cache freshness is understood; final cache-backed gates pass after rebuild
  when the change is being released or reviewed against active cache.
