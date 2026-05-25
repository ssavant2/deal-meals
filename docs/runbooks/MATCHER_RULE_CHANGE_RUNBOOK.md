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

For discovery, run `./bin/dm matcher --help` and `./bin/dm matcher guide --list`
first to see what is supported before reading further.

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
- **Lightweight registry alias** is "add a low-risk spelling/plural/compound
  synonym to an existing matcher surface." Example: `isbergssalladshuvud` should
  normalize to `isbergssallat`. Use the CLI, prove it with focused sanity plus
  registry/baseline/export checks, and skip fixture/inventory unless the alias
  changes routing/parity semantics or carries product-policy risk.

Do not memorize every command. Discover support and exact flags with:

```bash
./bin/dm matcher guide <shape>
./bin/dm matcher guide --list
```

Typical authoring families are:

- aliases/parents/routing: `keyword-synonym`, `keyword-extra-parent`,
  `ingredient-parent`, `offer-extra-keyword`, `ingredient-routing-parent`,
  `parent-match-only`, `recipe-routing-helper`
- declarative policies: `no-match-policy`, `extraction-helper`
- runtime blockers/filters/context/form data: `pnb`, `fpb`, `ksbc`, `gpb`,
  `stop-word`, `non-food-keyword`, `space-normalization`,
  `dual-keyword-normalization`, flavor/carrier, context, cuisine, compound,
  specialty, processed/form, substitution, and secondary-pattern commands
- mechanical maintenance: `dm matcher fixture remove`, `dm matcher modify
  no-match-policy`, `dm matcher modify match-bridge`, `dm matcher promote
  --apply-staged`, `dm matcher refresh-line-refs --fix`,
  `dm matcher sanity-find`, `dm matcher sanity-update`,
  `dm matcher reconcile-sanity`, and
  `dm matcher compare-paths`
- diagnostics: `dm matcher doctor` for read-only source/generated/writeability
  state, and `dm matcher trace-extraction` for token-level extraction drops
- smart-blocker scaffolding: `dm matcher add smart-blocker` creates and chains a
  Python stub; the actual matcher logic is still a manual code edit

Manual Track A, when no `dm matcher add` command fits:

```bash
# edit narrow Python runtime rule + focused run_deep_matcher_sanity.py case
./bin/dm matcher gates --track A
```

Manual Track B:

```bash
# edit TOML sources + focused run_deep_matcher_sanity.py case
./bin/dm matcher gates --track B --policy-ref <policy_ref>
```

Inactivate or remove a registry rule/fixture:

```bash
./bin/dm matcher inactivate <surface> <id-or-term> --reason "<why>"
./bin/dm matcher fixture remove <fixture_id>
```

`inactivate` updates a registry or runtime-overlay entry and runs the relevant
gate by default. Manual `status = "inactive"` edits are still valid fallback for
awkward cases; finish those with Track B gates and `--allow-removals`.

`fixture remove` cascades the fixture deletion through the authoritative fixture
TOML source, inventory fixture refs, registry fixture refs, regenerated JSON, and
pre-flight. It refuses to leave empty inventory or registry rows unless you pass
the explicit `--drop-empty-inventory` or `--drop-empty-registry-entries` flags.

Iterate with live pre-flight feedback:

```bash
./bin/dm matcher dev-watch
```

For batch work, use `dm matcher batch` instead of remembering `--no-run-gates`
on every command:

```bash
./bin/dm matcher batch start
# run dm matcher add/modify/fixture commands, plus any manual TOML/Python edits
./bin/dm matcher batch status
./bin/dm matcher batch finalize --track B
```

`dm matcher session` remains as a compatibility alias. While a batch is active,
per-command matcher gates are deferred by default; pass `--run-gates` on a
command to force an immediate check. `finalize` runs
generated JSON/coverage regen, verified-term baseline promotion, line-ref
refresh, drift check, pre-flight, and one final gate. If a finalize step fails,
the marker stays active so the batch can be fixed and finalized again.
Track B `finalize` requires a writable checkout as `appuser` for baseline
promotion. It does not bypass baseline write-permission checks: when run through
`./bin/dm`, it uses the normal appuser container path; if the promote step is run
as the wrong user or in a read-only checkout, it should fail there and leave the
batch active for a rerun after the permission issue is fixed.

Explain one product/ingredient decision before hand-reading large matcher tables:

```bash
./bin/dm matcher explain --offer "<offer name>" --ingredient "<ingredient text>"
```

Single maintenance/check operations:

```bash
./bin/dm matcher doctor
./bin/dm matcher preflight
./bin/dm matcher sanity
./bin/dm matcher promote
./bin/dm matcher promote --apply-staged /tmp/term-baseline-promotion
./bin/dm matcher regen --check
./bin/dm matcher refresh-line-refs --dry-run
./bin/dm matcher refresh-line-refs --fix
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
the web container and exposes authoring, validation, and maintenance commands
under one entry point. Raw `python support_checks/...` commands remain
fallback/debug forms when a wrapper is unclear or a support-check script itself
is being debugged.

`dm matcher gates` runs generated JSON/coverage refresh and baseline promotion
maintenance before validation when Track B inputs require it. Its first
validation gate is pre-flight; you can run that alone with
`./bin/dm matcher preflight`. Fix any `NEW` pre-flight issue before spending
time on slower fixture/parity gates.

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
- `--confirm-large-removals` only after reviewing a non-interactive promotion
  with more than five true verified-term removals.
- `--refresh-line-refs` when inventory anchors moved; run from a writable host
  checkout or write-enabled dev container.
- `--baseline-output-dir /tmp/term-baseline-promotion` only when the checkout is
  genuinely read-only; the wrapper stages generated files and stops so you can
  apply them with `./bin/dm matcher promote --apply-staged <dir>` before
  rerunning gates. If promote is accidentally run as a user that cannot write
  the checkout (e.g. root in the dev container instead of appuser), the wrapper
  now fails fast with a message pointing at the right invocation; there is no
  silent staging fallback.
- `--reload-cache --fresh-cache-gates` when cache/UI/cache-backed validation is
  part of the handoff.
- `--include-support-self-checks` when support-check code or schemas changed.
- `--dry-run` to print the exact gate list before running it.

If the host worktree is clean enough for git auto-detection, the wrapper can
select many flags itself. If the worktree contains unrelated edits, pass the
explicit flags above so the gate set reflects only your change.

Common single-operation wrappers:

```bash
./bin/dm matcher doctor                 # read-only generated/writeability/line-ref state
./bin/dm matcher preflight              # pre-flight only
./bin/dm matcher sanity                 # deep matcher sanity only
./bin/dm matcher promote                # verified-term baseline promotion
./bin/dm matcher promote --apply-staged /tmp/term-baseline-promotion
./bin/dm matcher regen                  # generated JSON then coverage
./bin/dm matcher regen --check          # read-only generated-artifact drift check
./bin/dm matcher refresh-line-refs      # refresh inventory anchors + generated JSON
./bin/dm matcher refresh-line-refs --fix  # explicit write-mode alias
./bin/dm matcher guide <shape>          # show the recommended path for a rule type
./bin/dm matcher trace-extraction --ingredient "<text>"
./bin/dm matcher sanity-find "<selector>"
./bin/dm matcher sanity-update "<selector>" --expected <canonical-or-None>
./bin/dm matcher reconcile-sanity "<selector>"
```

Raw scripts are still valid fallback/debug entry points. Prefer the wrapper
forms above for normal work.

**Commands NOT covered by `dm matcher`** (run these separately when needed):

- `dev_reload.py` — cache rebuild; use `dev_reload_high_resources.py` for
  end-of-batch review reloads on the dev machine. Use
  `--reload-cache --fresh-cache-gates` on the wrapper if the gates themselves
  should also run on the refreshed cache, but ad-hoc rebuilds remain separate
  commands.
- `matcher_layer_diagnostics.py` — interactive reproduction tool used in
  triage, not a gate.
- `run_matcher_full_db_diff.py` — heavy read-only DB diff for release work, not
  routine.

## Common CLI Workflows

Use the CLI for supported rule shapes. It writes the right artifacts for the
shape: small aliases stay lightweight by default, while contract-worthy fan-out
rules generate fixture/inventory proof and run Track B gates.

Keyword synonym / spelling alias:

```bash
./bin/dm matcher add keyword-synonym isbergssallat \
  --variants isbergssalladshuvud \
  --sanity-offer "Isbergssallat ca 440g Klass 1 ICA" \
  --offer-category vegetables
```

Default behavior: append `keyword_synonym.toml`, add a focused
`run_deep_matcher_sanity.py` row, promote the verified-term baseline, and run
the light registry/export/sanity gates. It intentionally does **not** create
fixture/inventory rows for routine spelling/plural/compound aliases. Add
`--with-fixture` or `--with-inventory` only when the alias changes
routing/parity semantics, documents a product-policy decision, or needs durable
contract evidence beyond the sanity regression.

Keyword extra parent fan-out:

```bash
./bin/dm matcher add keyword-extra-parent citrusfrukter \
  --kids citron,lime,apelsin \
  --recipe-name "Citrusrecept" \
  --ingredient "3-4 citrusfrukter (valfri sort)" \
  --offer-names "Citron,Lime,Apelsin" \
  --offer-category fruit
```

Use `--dry-run` to preview generated TOML/sanity text. During batch-review fix
phases, pass `--no-run-gates` on each `dm matcher add ...` command and run one
final `./bin/dm matcher gates --track A` or Track B gate after the grouped
changes. Outside batch mode, leave the default gates on. Use `--inventory-id`
only when deliberately adding a separate inventory row for a canonical that
already has one.

Other TOML registry rule surfaces follow the same pattern:
`ingredient-parent`, `offer-extra-keyword`, `ingredient-routing-parent`,
`parent-match-only`, and `recipe-routing-helper`. Use
`./bin/dm matcher guide <shape>` for the exact flags and proof expectations.

For structured TOML policies, create/choose durable proof first, then let the
CLI write the registry row and focused sanity stub:

```bash
./bin/dm matcher add no-match-policy cheddarost \
  --ingredient-patterns "\briven\b.*\bcheddarost\b" \
  --blocked-offer-patterns "(?=.*\bcheddarost\b)(?=.*\bkavli\b).*" \
  --auto-fixture \
  --auto-inventory \
  --reason "Riven cheddarost requires grated cheese, not spread." \
  --negative-ingredient "100 g riven cheddarost" \
  --negative-offer "Kavli Cheddarost"

./bin/dm matcher add extraction-helper apelsinskal \
  --side product \
  --input "Apelsinskal 100g" \
  --source-refs code:extraction:app/languages/sv/ingredient_matching/extraction.py:extract_keywords_from_product:402
```

`--auto-fixture` creates or reuses one negative fixture from
`--negative-ingredient`, `--negative-offer`, and `--offer-category`.
`--auto-inventory` creates the matching inventory row and line ref for the new
registry entry. Use explicit `--fixture-refs` instead when a richer fixture
already exists or when the policy needs several sibling fixtures. The auto flags
only handle bookkeeping; they do not choose policy wording, regexes, blockers,
or whether a positive sibling is needed.

For an existing simple `no-match-policy`, use the modifier instead of hand
keeping `variants`, guards, coverage, and negative-example payloads in sync:

```bash
./bin/dm matcher modify no-match-policy policy_generic_oil \
  --set-ingredient-patterns "\bolja\b" \
  --set-blocked-offer-patterns "\bolja\b" \
  --negative-ingredient "1 dl neutral olja" \
  --negative-offer "Olivolja Extra Virgin"
```

The modifier rewrites the synchronized fields in one pass, bumps the
`rule_version`, and runs pre-flight by default. Use `--dry-run` first when the
existing policy has broad fixture coverage.

If a hardcoded extraction helper is narrowed after an `extraction.py` edit, do
not hand-delete coverage rows. For a simple one-canonical entry, rewrite the
covered side/source refs instead:

```bash
./bin/dm matcher add extraction-helper margarin \
  --side product \
  --input "Lätta 39%" \
  --source-refs code:extraction:app/languages/sv/ingredient_matching/extraction.py:extract_keywords_from_product:829 \
  --replace-existing
```

If the entry has extra offer/ingredient terms or non-canonical coverage rows,
`--replace-existing` refuses the rewrite; edit manually and run Track B gates.
Extraction helper changes are Track B registry work even when the behavior
change itself is a small Python branch.

Common Python runtime data surfaces now have CLI-backed overlay coverage:

```bash
./bin/dm matcher add pnb citron --blockers lemonad --reason "Lemonade is a drink product, not lemon."
./bin/dm matcher add fpb ost --blockers ostronsås --reason "Oyster sauce contains ost as a substring but is not cheese."
./bin/dm matcher add ksbc ris --context risotto --reason "Risotto context should not fall back to plain rice."
./bin/dm matcher add gpb --terms kattsnack --reason "Pet snacks should never match cooking recipes."
./bin/dm matcher add stop-word --terms portionsstorlek --reason "Package-size wording should not become a recipe keyword."
./bin/dm matcher add non-food-keyword --terms skurborste --reason "Cleaning tools are not recipe ingredients."
```

Batch-review grouped fix phase:

```bash
./bin/dm matcher add pnb citron --blockers lemonad --reason "Lemonade is a drink product, not lemon." --no-run-gates
./bin/dm matcher add fpb ost --blockers ostronsås --reason "Oyster sauce contains ost as a substring but is not cheese." --no-run-gates
./bin/dm matcher add stop-word --terms portionsstorlek --reason "Package-size wording should not become a recipe keyword." --no-run-gates
./bin/dm matcher gates --track A
```

Watch for space-normalized compound blockers. If a space-normalization joins the
problem phrase, for example `balsamico ingefära` -> `balsamicoingefära`, a plain
FPB/PNB/KSBC blocker such as `balsamico` may not fire on the joined runtime
token. `dm matcher add pnb|fpb|ksbc` warns when it sees this shape; include the
suggested joined blocker as well when the rule is meant to block that compound.

Watch for FPB smart-blocker bypass. FPB is best when the keyword appears only
inside the blocker context. If the recipe-side ingredient also contains the
keyword as a standalone word, smart-blocker can allow the match and the FPB will
look present-but-ineffective. In that shape, verify the pair with
`dm matcher probe --expect no-match ...` and prefer KSBC when the specific
recipe-side context should suppress the generic keyword fallback.

PNB and GPB are product/backend proof surfaces. Do not treat a passing or
failing `matches_ingredient()` check alone as enough evidence for a product-name
blocker; use backend/product diagnostics or a focused behavior sanity when the
generated table canary is not enough.

For repeated backend-only product/ingredient guard patterns that cannot be
expressed as existing overlays, scaffold the function and chain with:

```bash
./bin/dm matcher add smart-blocker raw_sill \
  --description "Block raw sill products unless the ingredient asks for raw sill." \
  --sanity-ingredient "sill" \
  --sanity-offer "Rå sillfilé" \
  --expect no-match
```

This only creates the `matching.py` helper stub, inserts the call into
`_product_requirement_guards_allow_product`, and optionally adds a sanity
placeholder. The rule body remains a manual Python edit because the semantic
logic is the important part.

When the failure mode is unclear, run `dm matcher explain` before digging
through large Python tables. The first version is read-only and intentionally
narrow: it shows extraction, precomputed product keywords, likely PNB/FPB/KSBC
blockers, and the current fast/recipe-style result for that pair.

Before hand-reading `blocker_data.py`, ask the CLI where an effective blocker
comes from:

```bash
./bin/dm matcher list pnb --effective --term <keyword-or-blocker>
./bin/dm matcher list fpb --effective --term <keyword-or-blocker>
./bin/dm matcher list ksbc --effective --term <keyword-or-context>
```

The output distinguishes historical base tables, historical update tables, and
`runtime_rule_overlays.toml`, which avoids the "nearby dict section" trap in
large Python files.

Use the same list command for registry and specialty surfaces before hand
editing TOML or Python:

```bash
./bin/dm matcher list keyword-synonym --term <term>
./bin/dm matcher list ingredient-parent --term <term>
./bin/dm matcher list specialty-qualifier --term <term>
./bin/dm matcher list specialty-qualifiers --term <term>  # accepted alias
./bin/dm matcher list match-bridge --term <term>
```

Remember that `match-bridge` entries are diagnostics/migration metadata unless
the corresponding runtime-wired parent/synonym/offer-keyword row exists too.
For narrowing a simple existing bridge, prefer the modifier over editing the
same offer-pattern fields in several TOML payloads:

```bash
./bin/dm matcher modify match-bridge bridge_alger_nori \
  --remove-offer-patterns "\bseaweed\b" \
  --reason "Narrow bridge to nori-specific products."
```

The modifier rewrites the bridge variants, offer terms, coverage, and example
payloads together. It refuses nested bridge blockers/backend allowances so those
still get an explicit manual review.

The same overlay file also backs stop/non-food filters, space-normalization,
dual-keyword-normalization, flavor/carrier, processed-food, cuisine-context, compound-protection,
specialty-qualifier, qualifier-equivalent, product-name-substitution, and
secondary-ingredient-pattern commands. Qualifier-required keywords are also
CLI-backed for the small product-qualifier validation set in `match_filters.py`;
use `dm matcher guide <shape>` for exact flags. These commands generate
table-level or deterministic sanity canaries. Add a richer manual behavior case
beside the generated one when backend-only proof is needed. Local backend guards
still use manual editing plus `./bin/dm matcher gates --track A|B`.

Use `./bin/dm matcher add dual-keyword-normalization` for the
smörgåsgurka-style shape where one surface form should normalize to a specific
canonical first and still expose a broader family keyword after it. It writes a
normal `space_normalizations` overlay row, but the command makes the canonical
order explicit.

Use a **directional canonical override** when a modifier changes the requested
family and the base canonical must *not* remain available. Example:
`pepparrot på tub` means prepared `pepparrotsvisp`/cream-style products, not
plain fresh `pepparrot`; plain `pepparrot` should still mean the fresh root. This
is different from dual-keyword normalization, which intentionally emits both the
specific canonical and the broader family.

Checklist for this shape:

1. Prove both directions first: modified ingredient -> modified product; modified
   ingredient -> plain product is no-match; plain ingredient keeps matching the
   plain product family.
2. Make sure the target canonical exists on the product side. If products already
   extract it, no new registration is needed. If not, add the narrow product
   exposure through the primary keyword/extraction surface or a scoped
   `offer-extra-keyword`/product extraction helper.
3. Rewrite the ingredient-side modifier to the target canonical only. Prefer
   `space-normalization` for exact vocabulary such as `pepparrot på tub` ->
   `pepparrotsvisp`; use an ingredient-side extraction helper when the wording is
   regex/context dependent.
4. Add KSBC or a backend guard only if the base canonical still leaks after the
   rewrite or the modifier cannot be represented as a clean one-way rewrite. Do
   not use `dual-keyword-normalization` here, because exposing the base canonical
   is precisely what this pattern is trying to avoid.

### Ingredient Parser Troubleshooting

Use this section when the words look right, but an ingredient phrase is parsed
in the wrong shape before matching: alternatives, truncated compounds,
parenthetical notes, or brand/product names with flavor words.

Important parser surfaces:

- `recipe_text.py` owns recipe-text rewrites before extraction. Look here for
  `parse_eller_alternatives`, parenthetical preservation helpers, and
  `_TRUNCATED_ELLER_SUFFIXES` such as `yuzu- eller citronsaft` ->
  `yuzusaft eller citronsaft`.
- `engine.py` builds `IngredientMatchData`, including `eller_arms_prepared`.
  Routed/cache paths should use this prepared metadata instead of reparsing the
  raw string differently.
- `extraction.py` owns ingredient keyword extraction, including exact helpers
  for cases where the ingredient line is really a named purchasable product.
- `matching.py` owns live/fast keyword checks and local candidate guards.
- `recipe_matcher_backend.py` owns backend candidate validation after a fast
  keyword has been found.

For `A eller B` failures:

1. Compare the full phrase and each arm separately with `dm matcher compare-paths`.
   If `A` alone matches but `A eller B` does not, the bug is usually parser or
   per-arm validation, not missing vocabulary.
2. Check whether `A` is a substring of `B` (`potatis` inside `sötpotatis`,
   `kål` inside `spetskål`, etc.). Guards that do `keyword in ingredient_lower`
   may accidentally apply `B`'s context to `A`.
3. Inspect `eller_arms_prepared`. Context suppression, compound-strict checks,
   and exact-compound-only checks should ask "does this arm mention the plain
   keyword?" rather than "does the whole ingredient contain a suppressor?"
4. Prove both arms with focused canaries: `A` product matches the full phrase,
   `B` product matches the full phrase, and an unrelated product still does not
   match.

For truncated alternatives (`X- eller Ysuffix`), add the suffix to
`_TRUNCATED_ELLER_SUFFIXES` only when the expanded form is normal Swedish
vocabulary. Then prove the expanded left arm, not just the right arm.

For parenthetical notes, first decide whether the parenthetical is a preference,
an exclusion, or pure instruction text. Do not strip a parenthetical until a
negative canary proves the excluded product is actually rejected.

### Form-Rule Relaxation

Use this when wording such as `färsk`, `färskpressad`, `torkad`, `fryst`,
`rökt`, `kokt`, or `pulver` changes product eligibility. The important question
is whether the form word is a hard culinary requirement or only recipe wording.

Start here:

1. Run `dm matcher compare-paths --format json` on the exact pair with real
   category/brand. Look for `processed_checks`, spice/fresh/herb checks, product
   requirement guards, or backend validation rejects.
2. Check `processed_rules.py`, `form_rules.py`, `match_filters.py`, and the
   requirement/processed helpers in `matching.py` before adding aliases. If the
   canonical is already present but rejected, this is a form validator.
3. Prefer CLI-backed form surfaces for simple rules:
   `processed-rule`, `processed-exemption`, `strict-processed-rule`,
   `spice-fresh-rule`, or `processed-food`.
4. Use a narrow Python guard or extraction helper only when the rule depends on
   full recipe context or on an exception that the declarative surfaces cannot
   express.

Relaxation pattern:

1. Prove the strict negative that should remain strict. Example: plain
   fresh-pressed citrus should not automatically accept concentrate if that is
   the current policy.
2. Prove the exception. Example: rare/imported `yuzu` can accept bottled
   `yuzu juice` despite `färskpressad`, especially when the recipe gives a juice
   alternative.
3. Add the narrow vocabulary or parser fix needed for the exception, e.g.
   keyword synonym `yuzusaft/yuzujuice` plus the truncated-`eller` expansion.
4. Add regression canaries for both the accepted exception and at least one
   non-exception form that should stay blocked.

If the relaxation would apply to a whole high-traffic family (`citron`, `lime`,
`apelsin`, `mjölk`, `grädde`, `kött`, etc.), stop and ask. That is a product
policy decision, not a mechanical parser fix.

### Brand-Product Ingredients

Use this when an ingredient line is a named purchasable product, and words after
the brand/product name are flavor or variant descriptors rather than separate
recipe ingredients. Example: `Zeta Aperitivokex Ost & lök` should buy the named
kex product; `ost` and `lök` are flavors and must not match cheese or onion
offers.

Preferred pattern:

1. Confirm the ingredient is product-like: brand/name/package wording, a known
   product line, or a surface that users would buy as one SKU.
2. Add a narrow ingredient extraction helper in `extraction.py` or through
   `dm matcher add extraction-helper` so the ingredient emits the product-line
   canonical only.
3. If flavor words can still leak through backend validation, add a narrow
   guard in `_recipe_specific_product_guards_allow_product` requiring the offer
   name/keywords to contain the product-line canonical.
4. Prove three cases: exact product matches, first flavor word does not match as
   a standalone ingredient, second flavor word does not match as a standalone
   ingredient.

Avoid making the brand/product-line term a global stop word unless it is never a
purchasable food keyword. A stop word removes information; brand-product
handling should usually preserve one precise canonical and suppress only the
flavor bleed.

### Canonical Conflict And Ambiguity

Use this when diagnostics or parity reports `duplicate_signal_source` or
`ambiguous_canonical`, especially after adding `keyword-extra-parent`,
`ingredient-parent`, `parent-match-only`, `offer-extra-keyword`, or a routing
helper.

First classify the conflict:

1. If a fixture expected the old canonical but the new broader canonical is the
   intended behavior, update the fixture expectation with `sanity-update` or the
   matcher contract source, then run parity.
2. If the product should expose both a precision canonical and a broad parent,
   declare the relationship. Prefer a runtime-wired parent surface
   (`ingredient-parent`, `parent-match-only`, or `keyword-extra-parent`) when the
   relationship is real matcher behavior.
3. If runtime behavior is already correct and only diagnostics cannot see the
   family relationship, add a diagnostic-only relation in
   `_DECLARED_DIAGNOSTIC_CANONICAL_PARENTS` or
   `_DECLARED_DIAGNOSTIC_CANONICAL_GROUPS` in
   `support_checks/matcher_layer_diagnostics.py`, with a comment and a focused
   diagnostic/parity canary.
4. If the broader parent erases a meaningful form/subtype distinction, do not
   declare precedence. Narrow the bridge, use `offer-extra-keyword` only for the
   recipe-side parent case, or add a guard/no-match policy for the negative
   subtype.

Concrete example shape:

```text
Product: Vitkål Färsk
Old signal: vitkål
New parent signal: kål
Question: should generic "kål" recipes match vitkål, and should "kålhuvud"
still prefer whole white cabbage rather than every cabbage family member?
```

If yes, expose `kål` for generic recipes and add an asymmetric guard for
`kålhuvud` instead of changing all old `vitkål` fixtures to pretend that the
precision canonical disappeared. If no, remove or narrow the parent mapping.

Note that `match_bridge.toml` has a `precedence` field in its exported model,
but `match_bridge` is staged/declarative-only for runtime today. Do not expect a
`match_bridge` precedence value by itself to fix live matching or routed-cache
ambiguity.

### Read-Only Explain Trace

Use `dm matcher explain` when a pair surprises you, especially before reading
large blocker tables by hand:

```bash
./bin/dm matcher explain \
  --offer "Crema di Balsamico Ingefära" \
  --ingredient "ingefära"
```

Typical output is intentionally narrow:

```text
Ingredient: ingefära
Product: Crema di Balsamico Ingefära
Normalized product: crema di balsamicoingefära
Ingredient keywords:
  - ingefära
Product keywords:
  - balsamicoingefära
Fast matcher result: NO MATCH
Recipe-style validator result: BLOCKED / NO MATCH
```

When a blocker fires, the trace also includes lines like:

```text
Likely blocking reasons in fast matcher:
  - ost: false-positive blockers present -> ostron, ostronsås
Post-match validator notes:
  - blocked by false-positive blockers in fast matcher: ost
```

Read `explain` as a trace of the high-friction path: normalization, extracted
product and ingredient keywords, relevant blocker context, and the current
fast/backend-style result. It is an audit helper, not a second matcher
implementation.

Use `dm matcher trace-extraction` when the problem is earlier than matching:
the ingredient or offer produced no keywords, or an unexpected token vanished.

```bash
./bin/dm matcher trace-extraction --ingredient "nougat"
./bin/dm matcher trace-extraction --offer "Nougat 250g Odense" --offer-category pantry
```

The trace prints the normalized text, final extracted keywords, and token-level
drop reasons such as `STOP_WORDS`, `FLAVOR_WORDS`, too-short tokens below
`MIN_KEYWORD_LENGTH_STRICT`, or words that passed simple filters but were later
removed by extraction logic. Treat it as a first-pass diagnostic; if it says a
token was removed by later extraction logic, inspect the named extractor branch
or use `compare-paths` on the full pair.

Use `dm matcher compare-paths` when the actual mismatch is between matcher
entry points rather than rule intent. It compares the legacy live matcher,
canonical fast matcher, and backend matcher for one pair and prints precomputed
details such as `processed_checks` so product-side form rules can be diagnosed
without opening `matching.py` first.

If both sides clearly expose the same keyword but the result is still
`NO MATCH`, stop treating it as an extraction/canonical-registration problem.
That shape means the keyword loop found a candidate and a later guard probably
rejected it. Work through this checklist:

1. Re-run with the real category and brand:
   `dm matcher compare-paths --offer ... --ingredient ... --offer-category ... --brand ... --format json`.
   Category and brand feed product extraction, form checks, fresh/spice rules,
   and plant-based/product-label validation.
2. If `Product keywords` or `Precomputed offer keywords` are empty or missing the
   expected term, debug extraction first: non-food filters, processed-food
   filters, product-name substitutions, offer-extra keywords, brand stripping,
   or stale generated/runtime overlay data.
3. If `Ingredient keywords` is empty, debug the ingredient extractor before
   adding parents or offer-side synonyms. Check the normalized ingredient words
   against `MIN_KEYWORD_LENGTH_STRICT` in `extraction_patterns.py`,
   `IMPORTANT_SHORT_KEYWORDS`, `STOP_WORDS`, and `FLAVOR_WORDS` in
   `keywords.py`. Short real ingredients such as `nougat` can be filtered only
   because they are below the strict length threshold unless they are promoted to
   `IMPORTANT_SHORT_KEYWORDS`; flavor words may need carrier context and should
   not be assumed to extract as standalone ingredients. Also check early
   name-conditional branches in `extraction.py` that can return before the
   generic word loop.
4. If the keyword is present on both sides, inspect validators before adding more
   aliases: no-match policies, PNB/FPB/KSBC/GPB blockers, specialty qualifiers
   including bidirectional product qualifiers, product-form validators,
   `processed_checks`, spice/fresh/herb rules, recipe/product requirement
   guards, and explicit labels such as vegan/vegetarian/lactose/gluten-free.
5. If direct `compare-paths` passes but batch output or UI/cache output still
   misses, treat it as materialized-cache drift: check cache freshness and run
   the relevant reload before changing matcher semantics.
6. If direct `compare-paths` still fails, add a focused sanity row that captures
   the failing pair, then patch the narrow validator that rejects it. Avoid
   piling on synonyms or parents when the trace already proves both sides have
   the canonical keyword.

Use `dm matcher sanity-find "<description-or-policy-or-id>"` before editing a
large sanity file by hand. New CLI-generated sanity blocks include a stable
`# sanity-id: <policy_ref>` comment, and `sanity-find` can search by
description, expected literal, policy ref, sanity id, or generating command.

Use `dm matcher sanity-update "<description-or-policy-or-id>" --expected <canonical-or-None>`
when a deliberate rule change makes exactly one older sanity expectation stale.
The command edits one matching `test(...)` call in `run_deep_matcher_sanity.py`
and fails if the selector is ambiguous.

Use `dm matcher reconcile-sanity "<description-or-policy-or-id>"` when a
CLI-generated sanity row may have guessed the wrong canonical or become stale
after a parent/variant decision. It runs the current matcher for supported
generated `match(...)` and simple `recipe_match_num_named(...)` rows and reports
the expected value next to the actual value. Add `--all-generated` for an audit
pass. Add `--apply` only when the reported current behavior is the intended
result; v1 writes only simple generated `match(...)` expected values.

### Behavior Probe

Use `dm matcher probe` when the question is "does this new rule actually bite?"
rather than "does the dict contain my new value?"

```bash
./bin/dm matcher probe \
  --offer "Kex med choklad" \
  --ingredient "kex" \
  --expect no-match
```

The probe is read-only. It prints the fast matcher result and the full
`RecipeMatcher` backend result side by side, and exits non-zero when
`--expect` or `--expect-fast` is not met. If fast and backend diverge, run
`dm matcher explain` next to see which rule family is involved.

## Cold-Start Details

Read this section first if you have never seen this runbook before. Also return
here when you need repo orientation, when a gate fails in a layer you did not
expect, or when you are deciding whether a one-off diagnostic is enough.

For the underlying schema/layer model — what is authored, what is generated,
where baselines and prefix schemas live, and how pre-flight enforces
consistency — see `docs/MATCHER_REGISTRY_ARCHITECTURE.md`. This runbook
documents the workflow; the architecture file documents the data model.

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

Short pipeline sketch for rule placement:

```text
ingredient text -> extraction/parents/synonyms -> routing terms
offer text -> extraction/precompute/context/specialty/form data
routing candidate -> matches_ingredient_fast
fast keyword -> FPB/KSBC/PNB/specialty/form/backend validators
validated pair -> cache materialization -> UI/API result
```

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

Dietary/vegan context is intentionally spread by responsibility:

| Module | Owns |
| --- | --- |
| `specialty_rules.py` | Specialty qualifiers and bidirectional qualifier families. |
| `validators.py` | Runtime specialty/form validators called after a candidate exists. |
| `blocker_data.py` | FPB/PNB/KSBC blocker dictionaries and overlay merges. |
| `matching.py` / `engine.py` | Fast ingredient-offer candidate generation. |
| `recipe_matcher_backend.py` | Backend-only validation and recipe-context decisions. |
| `extraction.py` / `keywords.py` | Which words become ingredient/product keywords at all. |

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
| Track A: tactical runtime fix | A concrete FP/FN or known local semantic gap, usually narrow and local. This is the normal path for small PNB/FPB/KSBC/GPB additions, cuisine-context restrictions, compound/subword protection, and tiny runtime guards. | `dm matcher add pnb|fpb|ksbc|gpb`, `runtime_rule_overlays.toml`, `dm matcher add smart-blocker` scaffolds, `recipe_context.py` for `CUISINE_CONTEXT`, `compound_text.py`, `specialty_rules.py`, `processed_rules.py`, `form_rules.py`, small backend guards beside an existing local pattern. | Code change, corresponding `run_deep_matcher_sanity.py` regression, targeted re-check of the affected examples, and `dev_reload.py` before cache/UI validation. Do not add fixture/inventory unless escalating to Track B. |
| Track B: durable registry/contract rule | Registry-owned vocabulary/rules, broad or systemic semantics, routing/bridge/no-match policy, release hardening, or anything that should become permanent contract proof. | TOML under `term_registry/entries/`, TOML under `matcher_contracts/sources/`, generated matcher contract JSON, bridge/no-match/routing exports, support-check contracts. Use `dm matcher modify no-match-policy`, `dm matcher modify match-bridge`, and `dm matcher fixture remove` for supported mechanical rewrites/removals. | Fixture(s), inventory, registry/model checks, targeted/full fixture and parity gates, and cache freshness when cache-backed validation or release matters. |

There is one deliberately small path between those two: **lightweight registry
alias**. Use it for exact spelling/plural/compound aliases on already-wired
registry surfaces such as `keyword_synonym`. It is still registry-owned TOML,
but it does not need fixture/inventory proof unless it changes routing/parity
behavior or encodes a product-policy decision. For a plain alias, expect one CLI
command, one sanity regression, baseline/export checks, done.

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
| effective rule | The merged runtime rule after historical Python data and active overlay TOML entries have been combined. `dm matcher list --effective` shows this view and its origins. |
| post-normalized compound | A joined runtime token created by space-normalization, such as `balsamico ingefära` becoming `balsamicoingefära`; blockers may need to cover this joined form. |
| proof mode | The behavior layer a command or sanity row proves: `table`, `extraction`, `fast-match`, or `backend-match`. Product-side blockers usually need backend/product proof, not only `matches_ingredient()`. |
| parity | Agreement between live/fullscan, compiled/fullscan, compiled/routed, and compiled/hint-first paths. |
| freshness | Whether compiled recipe/offer data, term indexes, and active cache use current matcher/compiler versions. |

For false positives caused by newly launched product variants, prefer a family
rule over enumerating future products. Example: "plain recipe requires plain
product" for a plain-sensitive base such as `filmjölk` is better than adding one
blocker for every new flavor.

## Similar Mechanics: Which One Fits?

There is no perfect rule here; several matcher mechanisms can block the same
bad pair. Choose the surface that describes the *reason* the pair is wrong, not
only the first surface that can make the test pass.

Start by locating the bad signal:

1. If the ingredient text does **not really contain the keyword**, use `FPB`.
   Example: `ost` inside `ostronsås`, `dill` inside `quesadilla`. The blocker
   belongs on the ingredient side because the recipe wording created the false
   keyword.
2. If the ingredient text contains the keyword, but another recipe-side context
   makes the generic fallback wrong, use `KSBC`. Example: the ingredient names a
   specific form/context and the broad keyword should not also satisfy plain
   products. Use this for semantic ingredient context, not for product flavor or
   subtype words.
3. If the product text is the thing that makes the match wrong, use `PNB` or a
   product-side context/form rule. Example: a product is flavored, ready-made,
   mixed, preserved, a drink, or a carrier product while the recipe asks for a
   plain ingredient. Use `GPB` only when the whole product family is globally out
   of recipe scope regardless of matched keyword.
4. If both sides name the same base ingredient but a qualifier/subtype must
   agree, use `specialty-qualifier`. Use ordinary specialty qualifiers when a
   recipe-side qualifier must be present in the product. Add `--bidirectional`
   when a product-side qualifier should also block plain ingredients. Example:
   `datterini tomater` should not satisfy plain `tomater` if the subtype is
   intentionally narrower.
5. If the problem is that the text should become a better token before matching,
   use normalization. Use `space-normalization` for a joined/canonical token, and
   `dual-keyword-normalization` when a surface must expose a specific canonical
   first and a broader family keyword second. Do not use normalization to hide a
   semantic false positive; normalize only when the transformed text is the
   intended vocabulary.

Useful smell tests:

- `FPB`: "the ingredient contains misleading letters/words around the keyword."
- `KSBC`: "the recipe says the keyword, but this nearby recipe context should
  suppress the generic fallback."
- `PNB`: "the product is a wrong variant/carrier/flavor/form of an otherwise
  plausible keyword."
- `bidirectional specialty`: "plain ingredient should not match this product
  subtype, but subtype-aware recipes should."
- `normalization`: "this surface form should be read as these token(s) before
  extraction/matching even when there is no failure case."

When two mechanisms fit, prefer the narrowest reusable semantic statement:
`FPB` before `KSBC` for substring/context noise, `PNB` before `KSBC` for
product-only variants, `specialty-qualifier --bidirectional` before a long PNB
list for reusable named subtypes, and normalization only when the rewrite is
true vocabulary rather than a blocker in disguise. Use `dm matcher explain`,
`dm matcher compare-paths`, and one focused `dm matcher probe --expect ...`
before choosing if the failing side is unclear.

If the mechanism is still unclear after that, stop and ask. The wrong matcher
surface can silently encode a broader product/ingredient policy than intended,
so an explicit "is this FPB, KSBC, PNB, bidirectional specialty, or
normalization?" question is better than guessing.

## Pick The Change Surface

Prefer the highest-level surface that fits the chosen track. For Track B, favor
durable registry/contract surfaces. For Track A, a narrow legacy runtime dict
can be the correct surface.

If you do not yet know which matcher layer is failing, start with the Layer
Decision Tree below or run `dm matcher explain` before choosing a row in this
table.

| Change type | Prefer | Use when | Avoid |
| --- | --- | --- | --- |
| Exact synonym or spelling alias | `./bin/dm matcher add keyword-synonym ...` for `keyword_synonym`; otherwise the matching parent/routing registry entry | One term is the same ingredient family as another. Default to the lightweight alias path for spelling/plural/compound aliases; escalate to Track B only for routing/parity/product-policy implications. | Ad-hoc extraction code or full fixture/inventory ceremony for a plain alias. |
| Ingredient/offer bridge (recipe wording differs from product wording) | `./bin/dm matcher add keyword-extra-parent ...` (preferred for fan-out) or `./bin/dm matcher add ingredient-parent ...` | Recipe term and product term differ but should match (e.g. `nori` → `alger`, `citrusfrukter` → `citron`/`lime`/`apelsin`). These surfaces are wired into the runtime matcher today. | Adding only to `match_bridge.toml`. That surface is **declarative-only / staged for migration** — it does not affect runtime routing on its own. See the match_bridge note below the table. |
| No-match/blocking policy | `./bin/dm matcher add no-match-policy ...` after a durable negative fixture exists; `./bin/dm matcher modify no-match-policy ...` for simple existing policies | Ingredient pattern plus offer keyword/pattern should never match. | One-off Python if a declarative policy can express it, or manual TOML rewrites when the modifier supports the shape. |
| Offer keyword extraction | `./bin/dm matcher add offer-extra-keyword ...` or `extraction.py` + `./bin/dm matcher add extraction-helper ...` | Product wording should expose an additional canonical offer keyword. | Adding recipe synonyms when only offer extraction is missing. |
| Recipe extraction helper | `extraction.py` + `./bin/dm matcher add extraction-helper ...` | Ingredient text needs a hardcoded extraction output that cannot be expressed as a plain synonym. | Broad helper output without route/parity fixtures. |
| Parent/canonical fallback | `./bin/dm matcher add ingredient-parent ...`, `parent-match-only ...`, or `keyword-extra-parent ...` | A child term should expose a broader canonical, sometimes only for matching. | Parent mappings that erase meaningful product-form differences. |
| Ingredient-context blocker | `./bin/dm matcher add fpb ...` | Ingredient wording contains a keyword only inside a context that should suppress it. Common Track A tactical fix. | Offer/product variant blocking; use a product-side blocker or form/specialty rule after confirming the issue is product-side. If the keyword is standalone in the recipe ingredient, verify with `dm matcher probe`; KSBC is usually the right suppressor for that shape. |
| Product-name blocker | `./bin/dm matcher add pnb ...` | Offer/product wording contains a per-keyword variant, carrier, product type, or flavor that should block the matched keyword. Common Track A tactical fix. | Large flavor/form families that should be modeled declaratively. |
| Generic keyword suppressed by specific context | `./bin/dm matcher add ksbc ...` | Ingredient text names a more specific context and the generic keyword should not fall back. Use narrowly; this is semantic. | Broad high-traffic suppressions without a focused sanity canary. |
| Global product-name blocker | `./bin/dm matcher add gpb ...` | The product is globally non-food or globally out of matcher scope regardless of which keyword matched. Common for supplements, pet food, tools, tobacco, cleaning, and similar products. | Food products that can be legitimate for some recipe wording; use scoped PNB/no-match policy instead. |
| Stop word / extraction noise | `./bin/dm matcher add stop-word ...` | A descriptor, package/form word, diet label, or preparation word should not become a matcher keyword at all. | Terms that are real ingredients in some recipe context; use context/form rules instead. |
| Non-food keyword | `./bin/dm matcher add non-food-keyword ...` | The keyword means the product is non-food/tool/household scope and should filter out of product extraction. | Food terms that merely need scoped blocking; use GPB/PNB/no-match policy depending on breadth. |
| Carrier requires ingredient context | `./bin/dm matcher add carrier-context-required ...` | Product carrier/flavor handling should only match when the ingredient line names the same carrier family. | Plain keyword blockers when the issue is reusable carrier semantics. |
| Product context word requires ingredient context | `./bin/dm matcher add context-required-word ...` | A product subtype/form/context word makes a generic keyword unsafe unless the ingredient repeats that word. | FPB/PNB when the problem is the product's reusable context requirement. |
| Keyword already implies context word | `./bin/dm matcher add context-word-exemption ...` | A specific keyword should not be blocked by a context-required word because the keyword already implies it. | Broad exemptions without a focused sanity canary. |
| Ingredient requires product context | `./bin/dm matcher add ingredient-requires-product-context ...` | Ingredient text contains a form/carrier word and should only match products that also name it. | Product-only context rules when the asymmetry is ingredient-side. |
| Cuisine-specific seasoned product | `./bin/dm matcher add cuisine-context ...` | A product trigger such as `thaikryddad`, `taco`, or `texmex` should remain valid only when the recipe text contains matching cuisine context. This is better than a blanket PNB because the product stays visible for the right cuisine. | Using PNB for cuisine-seasoning products that are legitimate in matching cuisine recipes. |
| Compound/subword bleed | `./bin/dm matcher add compound-protection ...` | A keyword is matching as an unwanted substring or compound suffix/prefix, e.g. a compound word carries another ingredient name but should require stricter word/prefix proof. | FPB/PNB when the real problem is token/compound shape rather than a semantic product or ingredient context. |
| Multi-keyword normalization | `./bin/dm matcher add dual-keyword-normalization ...` | A surface form needs to emit both a specific canonical and a broader family keyword, with the specific canonical first. | Hand-editing `normalization.py` for ordinary dual-keyword overlays. |
| Directional canonical override | `space-normalization` or ingredient-side extraction helper plus narrow product exposure | A modifier changes the requested canonical and the base canonical must not remain available, e.g. `pepparrot på tub` -> `pepparrotsvisp` only. | `dual-keyword-normalization`; it emits the broader family too. |
| Form or processed-state rule | `./bin/dm matcher add processed-rule ...`, `spice-fresh-rule ...`, `processed-exemption ...`, `strict-processed-rule ...`, or `processed-food ...` for simple set add/remove; otherwise `form_rules.py` or a dedicated declarative form engine | Fresh/dried/frozen/cooked/plain semantics are the actual decision. See "Form-Rule Relaxation" for `färskpressad`/juice-style exceptions. | Listing every future flavor or cooked variant by hand. |
| Qualifier or bidirectional variant | `./bin/dm matcher add specialty-qualifier ... [--bidirectional]` or `qualifier-equivalent ...` | Product qualifier must also appear in the ingredient, or ingredient qualifier must appear in product. Prefer ordinary specialty qualifiers when only ingredient qualifiers must be honored; prefer `--bidirectional` when a product-side subtype should not satisfy a plain ingredient. | Raw substring checks without word-boundary handling. |
| Product qualifier required for a keyword | `./bin/dm matcher add qualifier-required-keyword ...` | A keyword should match product variants only when product qualifier words also appear in the ingredient line. | Specialty qualifier rules when the qualifier belongs to a specific product family rather than every product-side word. |
| Product keyword substitution | `./bin/dm matcher add product-name-substitution ...` | Product extraction should rewrite one extracted keyword to a more specific canonical only when required product words are also present. | Synonym/parent rules when the terms are always equivalent, regardless of product wording. |
| Secondary ingredient pattern | `./bin/dm matcher add secondary-ingredient-pattern ...` | A product is mainly another food and only contains the matched keyword as a secondary ingredient, with optional product-side exceptions. | Broad ingredient-family policy that belongs in PNB/FPB/processed/form logic. |
| Smart backend blocker | `./bin/dm matcher add smart-blocker ...` for scaffold/chain only, then manual `matching.py` logic | A repeated backend-only guard shape needs a named helper and the existing declarative/runtime overlays cannot express it. | Letting the generated stub pass as a finished rule; it intentionally contains no domain logic. |
| Declarative bridge guard | `match_bridge.toml` nested `blockers` / `backend_allowances` | A bridge needs scoped negative guards or backend allowance metadata with fixture refs. | Hiding broad bridge behavior in unrelated backend code. |
| Backend-only validation | `recipe_matcher_backend.py` | The rule needs recipe context, retry behavior, or materialization-time validation. | Fixing only backend when fast/fullscan/routing also need the rule. |
| Routing-only gap | `./bin/dm matcher add ingredient-routing-parent ...`, `recipe-routing-helper ...`, or `term_indexes.py` helper | Fullscan matches but routed cache never sees the pair. | Backend allowances that hide missing route terms. |
| Canonical conflict | Runtime-wired parent relation, diagnostic-only family declaration, or a narrower bridge | Diagnostics reports duplicate signal source or ambiguous canonical. See "Canonical Conflict And Ambiguity"; `match_bridge.precedence` alone is not live runtime wiring. | Accepting duplicate canonicals without a declared relationship. |

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
| Roll an offer keyword up to a parent ingredient (e.g. `nori` → `alger`, `citron` → `citrusfrukter`) | `./bin/dm matcher add keyword-extra-parent ...` |
| Treat a recipe-side variant as a known parent ingredient (e.g. `noriblad` → `nori`) | `./bin/dm matcher add ingredient-parent ...` |
| Add a spelling/plural alias normalized on both sides | `./bin/dm matcher add keyword-synonym ...` |
| Add a product-side keyword that maps to an existing ingredient | `./bin/dm matcher add offer-extra-keyword ...` |

If you really need to add a `match_bridge.toml` entry (e.g. you are continuing
the staged migration), dual-write the corresponding `keyword_extra_parent.toml`
/ `ingredient_parent.toml` rows in the same change, otherwise the wiring check
will fail.

### Flavor-Family Isolation Pattern

When a flavored/specialty product family keeps matching a plain ingredient,
check this repeatable shape before adding one-off blockers:

1. Protect compound or substring bleed first when the plain keyword is only a
   token-shape accident.
2. Add the ingredient-side bridge/parent/synonym only if recipes genuinely use
   another wording for the same family.
3. Add the canonical synonym/parent row needed for routing and extraction.
4. Add the offer-side bridge/extra keyword only if product wording is missing
   the canonical family.
5. Add the reverse bridge/parent only when the broader family should also find
   the specific product.
6. Add KSBC, specialty qualifier, no-match policy, or a backend guard for the
   negative/plain case, then prove it with `dm matcher probe --expect no-match`.

Typical examples are flavored cheese, sauces, vinegar, syrup, and vegan variants
where one word is a real ingredient in some recipes but a product flavor/type in
others.

## Layer Decision Tree

After choosing Track A or Track B, use the failing layer to pick the
implementation point:

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
2. Patch the narrow existing mechanism. Prefer the CLI-backed runtime overlay
   whenever `dm matcher guide <shape>` says the surface has an `add` command.
   The "Pick The Change Surface" table above lists the normal shape names.

   The CLI writes `runtime_rule_overlays.toml`; do not append new manual PNB,
   FPB, KSBC, GPB, stop/non-food, cuisine, compound, specialty,
   qualifier-required, flavor/carrier, processed-food, product substitution,
   secondary-pattern, or space-normalization data to historical Python tables
   unless no CLI surface fits.

   If the CLI warns that a blocker/context is hidden by a joined
   space-normalized compound, add the suggested joined form too. This is common
   when a visible product phrase becomes one runtime token before FPB/PNB/KSBC
   checks.

   If `dm matcher add ingredient-parent` warns that parent PNB blockers are not
   inherited, add the suggested explicit child PNB when the child should share
   the parent's product-side exclusions. Do not assume blocker inheritance
   through parent resolution.

   For form rules or local backend guards, edit the owning Python surface beside
   the existing local pattern.

   For PNB/FPB/KSBC/GPB-style fixes, remember that the generated sanity canary
   may prove table membership before it proves behavior. Run
   `dm matcher probe --offer "<offer>" --ingredient "<ingredient>" --expect no-match`
   (or `--expect match`) on the concrete pair before calling the rule done.
3. Add or adjust a focused regression inside `run_deep_matcher_sanity.py` for
   every new rule. If a nearby case already asserts the exact same behavior,
   keep or extend that case rather than duplicating it. This script is the
   primary Track A sanity gate and should grow over time with new matcher rules.
4. Run the standard Track A gate wrapper:

   ```bash
   ./bin/dm matcher gates --track A
   ```

   This runs the primary deep matcher sanity gate and the full matcher parity
   gate with cache freshness skipped.

   During batch reviews, this should be the single final gate for the grouped
   fix phase. Use `--no-run-gates` on each individual `dm matcher add ...`
   command in that batch so the same Track A gate suite is not repeated for
   every small rule.

5. If you run manually instead of using the wrapper, run the fixture parity check
   to confirm no existing fixture contracts were broken by the change. This is
   mandatory even for Track A — you are responsible for leaving parity clean,
   not the next agent:

   ```bash
   ./bin/dm matcher sanity

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
./bin/dm matcher refresh-line-refs
```

The refresh updates the authoritative inventory TOML source and regenerates the
generated inventory JSON. Use `--dry-run` to inspect changes without writing.
The raw `refresh_matcher_rule_inventory_line_refs.py --write` script remains a
fallback/debug form.

### Registry Entries

If the change uses a live term-registry rule surface, prefer the matching
`dm matcher add` or `dm matcher modify` command. Use
`./bin/dm matcher guide <shape>` when unsure. Manual TOML editing is still valid
for careful fallback/debug work, inactivation/removal, or changes outside the
supported authoring shapes. Those files live under:

```text
app/languages/sv/ingredient_matching/term_registry/entries/
```

Common files and their normal authoring path:

- `extraction_helper.toml` — `dm matcher add extraction-helper`
- `ingredient_parent.toml` — `dm matcher add ingredient-parent`
- `ingredient_routing_parent.toml` — `dm matcher add ingredient-routing-parent`
- `keyword_extra_parent.toml` — `dm matcher add keyword-extra-parent`
- `keyword_synonym.toml` — `dm matcher add keyword-synonym`
- `match_bridge.toml` — staged/declarative-only; `dm matcher modify match-bridge`
  can narrow simple existing rows; see the match_bridge callout
- `no_match_policy.toml` — `dm matcher add no-match-policy` or
  `dm matcher modify no-match-policy`
- `offer_extra_keyword.toml` — `dm matcher add offer-extra-keyword`
- `parent_match_only.toml` — `dm matcher add parent-match-only`
- `recipe_routing_helper.toml` — `dm matcher add recipe-routing-helper`

Registry entries should include coverage rows and examples that describe the
same decision as the fixture. For registry-owned `MatchBridge` and
`NoMatchPolicy`, keep `fixture_refs` inside the language payload in sync with
the fixture file.

Do not hand-edit these two coverage files for ordinary fixture/inventory work:

- `matcher_regression_case.toml`
- `matcher_rule_inventory.toml`

They are generated from the generated JSON contracts by:

```bash
./bin/dm matcher regen --what coverage
```

The Track B wrapper automatically regenerates the JSON contracts first and
then runs the coverage generator when fixture or inventory changes are selected.
The JSON contracts themselves are generated from the TOML sources by:

```bash
./bin/dm matcher regen --what json
```

Pre-flight fails with `matcher_contract_generated_json_drift` if generated JSON
does not match the TOML sources, and with `generated_coverage_stale` if the
checked-in registry coverage TOML no longer matches the generated JSON-derived
output. Intentional manual coverage is allowed only as a narrow exception: put
`# manual-coverage` directly before the manual `[[entries]]` block so the
generator preserves it.

Use `./bin/dm matcher regen --check` for a fast read-only drift check of both
generated JSON and registry coverage.

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
5. Run `./bin/dm matcher promote`.

If `promote_term_baseline.py` aborts with "truly removed" variants, treat that
as a semantic deletion until proven otherwise. Content-equivalent verified-term
ID changes are migrated automatically; only true removals need approval.

The accepted intentional-removal flow is:

1. Confirm each removed variant ID corresponds to the TOML entry you just
   inactivated or removed. If any removed variant is unexpected, stop.
2. Re-run promotion with explicit removal approval:

   ```bash
   ./bin/dm matcher promote --allow-removals
   ```

   When more than five variants are truly removed, the promote script asks for
   `yes` interactively before writing. In non-interactive gates, pass
   `--confirm-large-removals` only after reviewing the listed removals.

3. Run the registry contract checks and full Track B gates.

`promote_term_baseline.py` (with or without `--allow-removals`) auto-updates the
relevant baseline JSON fields (`variant_count`, `source_counts`, `role_counts`,
`status_counts`, `classification_counts`) and the `EXPECTED_VERIFIED_TERM_VARIANT_COUNT`
constant in `run_term_registry_contract_checks.py`, plus the frozen unique
coverage-key constants used by add-term/sanity checks. It also refreshes stale
constants when the baseline variant list itself is already up to date. Do not
patch these by hand.

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

- `runtime_rule_overlays.toml` for new FPB, PNB, KSBC, and GPB runtime blockers;
  `blocker_data.py` still owns historical blocker tables and rare manual guards
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

### Batch-Review Registry Sequence

When batch review produces several registry/routing changes, keep authoring fast
but finish with the same deterministic maintenance order:

1. Add or modify rules with `dm matcher add ... --no-run-gates` while you are
   still collecting the batch.
2. Regenerate derived matcher artifacts before promotion:

   ```bash
   ./bin/dm matcher regen --what all
   ```

3. Promote the verified-term baseline from a writable checkout/container user:

   ```bash
   ./bin/dm matcher promote
   ```

   Use `--allow-removals` only after reviewing intentional inactivations or
   deletions.
4. Run pre-flight or the Track B wrapper. The wrapper normally performs the
   regen/promote steps for standard Track B work, but the explicit sequence is
   useful during long batch review because it tells you exactly which derived
   layer is stale.

If pre-flight reports a stale unique coverage-key constant, prefer rerunning the
promotion/wrapper first because `promote_term_baseline.py` is supposed to refresh
the constant. To inspect the live count directly:

```bash
docker compose exec -T -w /app web \
  python support_checks/run_term_registry_add_term_checks.py \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["unique_coverage_key_count"])'
```

Patch `EXPECTED_VERIFIED_TERM_UNIQUE_COVERAGE_KEYS` only as a last resort when
promotion cannot write the intended files; mention that in the handoff.

When `ingredient-parent` and `keyword-extra-parent` both touch the same family,
offers may expose both a precision variant and a broad parent in
`precomputed_keywords`. The fast matcher will materialize the first valid
canonical, which can make a generated sanity canary expect the parent while the
real result is the variant. In that case:

- inspect `dm matcher compare-paths --format json` for the actual materialized
  keyword;
- update the generated sanity expectation and the authoritative
  `matcher_regression_cases.toml` fixture expectation to the intended canonical;
- do not force the parent canonical unless the product should genuinely stop
  materializing as the precision variant.

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
cache-facing changes. For a plain Track A PNB/FPB/KSBC/GPB fix, use the Track A
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

Pre-flight also enforces matcher runtime guardrails. In particular, direct
imports or calls of `_SPACE_NORM_PATTERN` / `_SPACE_NORM_LOOKUP` outside
`ingredient_matching/normalization.py` are blockers; use
`_apply_space_normalizations()` so space-normalization behavior stays
single-sourced.

Useful wrapper options:

- `--registry-changed`, `--runtime-changed`, `--fixtures-changed`, and
  `--inventory-changed` override git auto-detection when the worktree contains
  unrelated edits.
- `--allow-removals` is passed to `promote_term_baseline.py` after confirmed
  intentional TOML inactivation/removal.
- `--confirm-large-removals` is required for non-interactive baseline promotion
  when more than five verified-term variants are truly removed.
- `--parallel-readonly` is enabled by default and runs independent read-only
  gate steps in parallel using available CPU cores minus one. Use
  `--no-parallel-readonly` when debugging interleaved gate behavior.
- `--parallel-readonly-jobs N` overrides the read-only worker count when the
  default CPU-core-minus-one budget is not appropriate.
- `--refresh-line-refs` runs the host-only inventory line-ref refresher.
- `--no-generate-coverage` disables the automatic derived coverage refresh
  when you intentionally want pre-flight to report stale coverage.
- `--baseline-output-dir` stages baseline promotion output and stops; apply the
  staged files with `./bin/dm matcher promote --apply-staged <dir>`, then rerun
  the wrapper without that flag.
- `--reload-cache --fresh-cache-gates` adds `dev_reload.py` and final
  cache-fresh fixture/parity gates.
- `--dry-run` prints the exact script list without running it.

Do not run every script reflexively when running manually. Use this matrix to
choose the smallest complete gate set for the change.

| Gate | Run when |
| --- | --- |
| `dm matcher sanity` | Every Track A fix and every Track B runtime semantic change. Raw fallback: `run_deep_matcher_sanity.py`. |
| targeted `run_matcher_layer_fixture_cases.py` | Track B fixture/rule work for the affected `--policy-ref`, `--canonical`, or `--case-id`. |
| targeted `run_matcher_layer_parity.py` | Track B route, bridge, no-match, canonical, cache-facing, or fixture behavior work. |
| `dm matcher regen --what json` | Fixture or inventory TOML source changed. `dm matcher gates` runs this automatically before coverage. |
| `dm matcher regen --what coverage` | Fixture or inventory contract changed. `dm matcher gates` runs this by default after JSON generation. |
| full `run_matcher_layer_fixture_cases.py --skip-cache-freshness` | Every Track B behavior change before handoff. |
| full `run_matcher_layer_parity.py --skip-cache-freshness` | Every Track A/Track B matcher behavior change before handoff. |
| `dm matcher promote` | Any tracked registry TOML change. Use the plain command unless confirmed TOML inactivation/removal requires `--allow-removals`. |
| term-registry checks | Any tracked registry TOML or baseline change. |
| `run_matcher_rule_model_checks.py` | Track B rule-model, bridge, no-match, inventory, or registry-owned rule changes. |
| `run_matcher_rule_inventory_checks.py` | Any inventory change or Track B rule that should be inventory-owned. |
| `run_matcher_version_checks.py` | After final generated/contract state for matcher behavior changes. |
| `run_sanity_checks.py` | Runtime Python changes with broader app-support risk, or after baseline promotion if the promotion script updates support-check expectations. |
| support-check self-checks | Support-check code/schema/diagnostics/parity tooling changes only. |
| `dev_reload.py` | Cache/UI/cache-gated validation, or when handing off a change that must be visible in active dev cache. Use `dev_reload_high_resources.py` for end-of-batch review reloads on the dev machine. |

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
./bin/dm matcher promote

# OR, when TOML inactivation/removal intentionally removed verified variants:
./bin/dm matcher promote --allow-removals
```

If more than five verified variants are truly removed, the command asks for
`yes` before writing. For reviewed non-interactive runs, add
`--confirm-large-removals`.

If the checkout is read-only, stage the generated files under a writable
directory, again choosing either the plain or removal-approved variant as
appropriate, and then apply the staged changes to the real checkout:

```bash
# Choose exactly one:
./bin/dm matcher promote --output-dir /tmp/term-baseline-promotion

# OR, when TOML inactivation/removal intentionally removed verified variants:
./bin/dm matcher promote \
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

./bin/dm matcher sanity
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

During batch reviews on the dev machine, prefer the high-resource variant for
the end-of-batch reload:

```bash
docker compose exec -T -w /app web python support_checks/dev_reload_high_resources.py
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

If `run_deep_matcher_sanity.py` fails with a non-empty `Got` canonical and a
different non-empty `Expected` canonical, treat it as a canonical-drift review
before changing runtime code. Synonym, parent, or canonical-rule changes can
make an older sanity row expect the pre-change spelling even though the matcher
now resolves the intended family. Update the assertion only after confirming
the new canonical is the desired one.

## Common Pitfalls

- Track A: forcing narrow PNB/FPB/KSBC/GPB runtime fixes through
  fixture/inventory, or calling them durable without escalating to Track B.
- Track A: adding a matcher rule without a focused
  `run_deep_matcher_sanity.py` regression.
- Track A: skipping full parity with cache freshness skipped; even tactical
  fixes must leave existing fixtures clean before commit.
- Track A: running heavy support-check/model self-checks as routine gates; those
  are Track B/tooling checks.
- Track B: adding runtime behavior without a fixture, or a fixture without
  inventory coverage.
- Track B: hand-editing TOML when `dm matcher add` supports the surface; use
  `dm matcher guide <shape>` / `--list` before falling back to manual edits.
- Track B: editing generated JSON or generated coverage TOML instead of the
  authoritative TOML source plus `dm matcher regen`.
- Track B: changing registry TOML without baseline promotion and registry
  checks.
- Track B: treating TOML inactivation/removal or a "truly removed" promotion
  warning as harmless. Behavior-changing removals need fixture/inventory proof,
  and true verified-term removals need explicit approval.
- Track B: using raw substring checks where word boundaries are needed.
- Track B: fixing backend validation but forgetting `matches_ingredient_fast`,
  or broadening route/bridge/extraction behavior without parity and routed-cache
  proof.
- Track B: broadening a bridge without a negative sibling, using a broad parent
  where a scoped bridge is safer, or forgetting nested `blockers` /
  `backend_allowances`.
- Track B: adding one product-name blocker per flavor when a family-level
  plain-sensitive rule is the actual model.
- General: letting stale cache explain away a semantic fixture failure; run
  `dev_reload.py` before cache-backed validation after matcher runtime changes.
- General: using FPB for a product-side problem. Check `dm matcher explain` and
  `dm matcher list pnb|gpb --effective --term <term>` before choosing FPB.
- General: assuming FPB should fire just because the visible blocker word is in
  the product/ingredient text. Space-normalization may have joined the words
  into a post-normalized compound before the blocker check.
- General: using FPB when the recipe ingredient contains the keyword as a
  standalone word and the context should suppress a generic fallback. The
  smart-blocker may allow that match; use `dm matcher probe` and consider KSBC.
- General: adding a new PNB key without first checking
  `dm matcher list pnb --effective --term <term>`; an effective rule may already
  exist in the historical base, historical updates, or overlay TOML.
- General: assuming ingredient-parent mappings inherit parent PNB blockers. PNB
  lookup can run before parent resolution; use the CLI warning and suggested
  `dm matcher add pnb ...` command to mirror needed product-side blockers
  explicitly.
- General: using direct `_SPACE_NORM_PATTERN.sub(...)` or importing
  `_SPACE_NORM_LOOKUP` outside `ingredient_matching/normalization.py`; pre-flight
  flags this because `_apply_space_normalizations()` is the supported entry
  point.
- General: appending new PNB rows to `_PRODUCT_NAME_BLOCKER_UPDATES` instead of
  using `dm matcher add pnb`.
- General: using PNB for cuisine-seasoned products that should remain valid in
  matching recipes; use `CUISINE_CONTEXT` for recipe-cuisine context.
- General: treating `app/tests/`, `/app/data/term_registry/`, or regenerated
  support reports from `/tmp/deal-meals-support-checks/` as permanent artifacts.
- General: forgetting inventory line-ref refresh after moving anchors.
- General: patching hard-coded support-check expectations when the real issue is
  stale generated/check data, or vice versa.

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
