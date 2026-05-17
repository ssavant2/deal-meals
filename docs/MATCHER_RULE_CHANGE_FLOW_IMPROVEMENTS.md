# Matcher Rule Change Flow — Friction Reduction Plan

> **Revision note (2026-05-17):** This plan was course-corrected after a code
> review by Codex. The original draft overstated the work needed for
> EXPECTED_* constants (promote already auto-updates the common promote-owned
> counts), mis-diagnosed the docker mount as read-only (the dev mount is
> writable for `appuser`; root exec is not), and listed seven pre-existing
> issue instances that have since been fixed on `main`. The phase order was also
> revised so the highest-ROI improvement (coverage TOML generator) lands
> early instead of being bundled inside the CLI work. See **Revision
> History** at the bottom for the full diff.

## Background

A single Track B matcher rule change (Q54-2: `keyword_extra_parent.toml`
fan-out for `citrusfrukter`) required **11 wrapper iterations** before the gate
script passed. Each iteration surfaced one failure, which had to be fixed
before the next failure became visible. The matcher logic itself was correct
on iteration 1 — every subsequent iteration was infrastructure friction.

The Q54-2 implementation was conceptually small: 8 TOML entries that map
citrus child keywords to a `citrusfrukter` parent. But landing it required
edits in 10 files (TOML registry entries, JSON fixtures, JSON inventory, TOML
coverage rows in two separate files, a coupled `match_bridge.toml` entry,
support_check constants in three places, a regression test, and a baseline
file). Most of the edits were mechanical boilerplate derivable from the
8 source entries.

This document is the plan to reduce that friction so the **next** Q54-2-shaped
change passes the wrapper on the first or second attempt.

## Root Causes from Q54-2

The 11 iterations grouped into seven distinct root causes:

| Group | Iterations | Root cause |
|---|---|---|
| **A. Late, narrow error reports** | 5, 8, 11 | Each gate fails on one prefix mismatch and aborts. The wrapper does not collect all prefix problems upfront. |
| **B. Stale `EXPECTED_*` constants** | 7, 9 | `promote_term_baseline.py` **already** auto-updates three constants (`EXPECTED_VERIFIED_TERM_VARIANT_COUNT`, `EXPECTED_VERIFIED_TERM_UNIQUE_COVERAGE_KEYS`, `_EXPECTED_UNIQUE_COVERAGE_KEYS`). The friction I hit in Q54-2 was user error — I bumped constants by hand instead of re-running promote after a new bridge changed the count. What is *genuinely* still hardcoded: `seed match bridge count` and the `expected_bridge_ids` set in `run_matcher_rule_model_checks.py:340/624`, plus `EXPECTED_SV_EXPORT_LAYER_COUNT = 25` in `run_term_registry_add_term_checks.py:39` (drifts when a new `ExportLayerSpec` is added). |
| **C. Hardcoded lists of registry contents** | 10 | `expected_bridge_ids` is a large hand-maintained set in `run_matcher_rule_model_checks.py`. Adding any bridge requires bumping the list manually. |
| **D. Hash-shift sensitivity** | 4, 6 | Before Phase 3, `variant_id` was derived from `source_ref` content. Any text change to `source_ref` shifted the hash and required explicit hash migration. Phase 3 moves identity to a stable v2 payload that excludes `source_ref`; content-equivalent ID migrations are automatic. |
| **E. Coverage TOML is boilerplate** | 2 | For every new fixture and inventory entry in JSON, a separate registry coverage row must be hand-authored in `matcher_regression_case.toml` and `matcher_rule_inventory.toml`. The content is fully derivable from the source JSON. |
| **F. Audit derivation has silent failure modes** | 3 | When a positive fixture forgets the top-level `expected_matches` field (or puts it under `metadata`), audit derives `canonical=None` and coverage matching fails with a generic "lacks coverage" error that does not point at the underlying problem. |
| **G. Baseline write fails on execution-user mismatch** | (every promote) | The `./app:/app` bind-mount **is already writable** in `docker-compose.dev.yml`, but only for the file-owning `appuser` in the current dev setup. `docker compose exec` defaults to `root`; on this bind-mounted checkout, root is not writable while `appuser` is. Writes fail with `PermissionError`. The workaround that Q54-2 used (`--baseline-output-dir /tmp/...` then four `docker cp`) is fixable by running the wrapper/promote with `-u appuser` instead. |

## Goal & Success Criteria

**Goal**: a Track B change of Q54-2 shape (one or more new registry entries
plus matching fixtures/inventory) passes the wrapper on the first attempt with
no manual constant bumps, no manual coverage TOML authoring, no
`--migrate-hashes` invocation, and no `docker cp` shuffle.

**Success criteria, measurable on a synthetic test case:**

1. Adding one new `keyword_extra_parent.toml` entry plus its sanity test
   requires editing one or two files. The wrapper produces a green run in a
   single execution.
2. Adding a new fixture to `matcher_regression_cases.json` does not require
   editing `matcher_regression_case.toml`.
3. Bumping the seed bridge count in `run_matcher_rule_model_checks.py` is no
   longer needed when a new bridge is added.
4. Changing a `source_ref` string on an existing fixture does not produce a
   `--migrate-hashes` requirement.
5. Pre-flight reports all known infrastructure problems together as a single
   diff-style report, not one at a time.

## Improvement Catalogue

Improvements are grouped by ambition level. Higher levels build on lower ones.

### Level 1 — Friction reduction (additive, low risk, ~2-3 hours)

**L1-A. Pre-flight validation gate** *(addresses A, E partial, F)*
A new wrapper step that runs **first**, before baseline promotion, and
collects every infrastructure problem into one report:
- Every fixture source_ref/policy_ref prefix checked against the allow-list
- Every inventory adapter_ref prefix checked against the allow-list
- Every inventory entry checked for line_ref anchor existence
- Every `EXPECTED_*` constant compared against the live count it audits
- Every active fixture/inventory entry checked for matching registry coverage
- Every fixture with `expected=1` checked for top-level `expected_matches`

Output format: one section per problem class, each with the exact file, line,
and a copy-paste-ready fix snippet.

**Pre-existing vs new failure discrimination** *(safety valve, not a default state)*

The seven pre-existing issue instances I originally documented (four
`line_ref` anchor mismatches and three missing löjrom fixture coverages)
**have since been fixed**. Inventory checks are green on `main` as of
plan-revision time:
1488/1488 fixtures covered, 789/789 anchors current. So the snapshot
mechanism is built as a **safety valve**, not as something we expect to
contain content under normal operation.

Doctrine: **`main` should always produce an empty snapshot.** Growth in the
snapshot is a smell, not a feature. The snapshot exists for two reasons:

1. A genuine emergency where main has acquired a known-broken state we
   cannot fix immediately (e.g. an external dependency change) and we need
   to keep landing unrelated work in the meantime.
2. Transitional periods during Phase 3 migrations where the parallel-running
   flag is active.

Mechanism (kept lightweight precisely because we expect it to stay mostly
empty):
- A snapshot file `app/support_checks/baselines/known_infrastructure_issues.json`
  records the fingerprint (file path + issue code + entity id) of every
  pre-flight failure that is intentionally tolerated on `main`.
- Pre-flight compares its current findings against the snapshot:
  - **NEW** (in current run, not in snapshot) → reported as `ERROR`, blocks
    the wrapper. This is the normal case.
  - **KNOWN** (in both) → reported under `# Tolerated pre-existing issues`
    as `INFO`. Should be empty under normal operation.
  - **FIXED** (in snapshot, not in current run) → reported as `SUCCESS` and
    the snapshot is suggested for refresh.
- Adding an entry to the snapshot requires:
  - An explicit comment in the file justifying the tolerance
  - A linked tracking issue or scheduled cleanup date
- CI fails if the snapshot grows in a PR without the comment + tracking
  link.

**L1-B. Close the remaining hardcoded gap** *(addresses B — narrowed scope)*

Promote already auto-updates three constants. The remaining hardcoded items
in support_checks that drift when the registry grows are:

In `run_matcher_rule_model_checks.py`:
- the `seed match bridge count` integer check (line 624)
- the large `expected_bridge_ids` set (line 340)

In `run_term_registry_add_term_checks.py`:
- `EXPECTED_SV_EXPORT_LAYER_COUNT = 25` (line 39) — bumps every time an
  `ExportLayerSpec` is added in `add_term.py`. Rare but real friction.

Replace the bridge checks with derivations from `MATCH_BRIDGES`:
```python
expected_bridge_ids = {b.id for b in MATCH_BRIDGES}
# Or, with regression protection on a small seed set:
SEED_BRIDGE_IDS = {"bridge_alger_nori", "bridge_dill_fresh_herb", ...}
check("seed bridge IDs always present", SEED_BRIDGE_IDS <= expected_bridge_ids)
```

Same treatment for `EXPECTED_SV_EXPORT_LAYER_COUNT`: derive from
`len(SV_EXPORT_LAYER_SPECS)` directly. Either drop the check entirely (it
guards against accidental removal of an export layer, which is rare and
also covered by export tests) or compute it at runtime.

This eliminates the count-bump and ID-list-bump in iterations 10 of Q54-2,
plus the future bump that would have happened on the next export-layer
addition.

(The original L1-B proposed a generalized `_expected_counts.py` module. That
is overkill given promote already handles the bulk of these constants.
Single-source is still a valid future direction; logged under L3-E-ish
schema-driven validation, not Phase 1.)

**L1-C. Merged into L1-B** *(addresses C)*
The original draft split hardcoded bridge IDs into a separate L1-C item.
That is now folded into L1-B so Phase 1 has one narrow "hardcoded support
check cleanup" task instead of two overlapping tasks.

**L1-D. Better error messages on prefix failures** *(addresses A)*
Every "unknown prefix" error includes the allow-list inline:
`unknown prefix 'registry:'. Allowed: current_review:, legacy_review:, manual:, plan_initial:, sanity:`

**L1-E. Audit warning on missing expected_matches** *(addresses F)*
The audit step (or the new pre-flight) warns explicitly:
`fixture X has expected=1 but no top-level expected_matches.canonical field — registry coverage will fail to match.`

**L1-F. Fix promote execution-user mismatch in dev** *(addresses G — re-scoped)*

The dev mount is already writable (`./app:/app` in `docker-compose.dev.yml`).
The friction is that `docker compose exec web` defaults to running as `root`.
On the dev bind mount, the checkout files are writable by `appuser` but not
by root, so baseline writes fail with `PermissionError`.

Fixes (pick one or both):

1. **Host invocation default**: run the whole wrapper/promote command as
   the file-owning user, and have any future `bin/dm` wrapper do the same:
   ```bash
   docker compose exec -T -u appuser -w /app web python support_checks/run_matcher_change_gates.py --track B
   ```
   For direct promotion, use the same `-u appuser` prefix with
   `support_checks/promote_term_baseline.py`.

2. **Promote falls back to staged-output automatically**: if
   `promote_term_baseline.py` detects `PermissionError` on its first write
   attempt, it auto-falls-back to `--baseline-output-dir /tmp/...` and
   prints a one-line warning telling the user how to apply the staged
   files. This keeps the script tolerant if anyone runs it as the wrong
   user.

**Security impact — dev only, prod unchanged.**
Both fixes are dev-workflow changes. Prod-base `docker-compose.yml` mounts
`./app` read-only; that is unchanged. Verification step: after the fix, run
`docker compose -f docker-compose.yml config` (without the dev overlay) and
grep for `:ro` on `./app` to confirm prod behavior is unchanged. This goes
into the L1-F acceptance test.

### Level 2 — Generated coverage + authoring workflow (~4-6 hours, on top of Level 1)

**L2-A. Auto-emit coverage TOML from JSON** *(addresses E)*
Instead of hand-authoring `matcher_regression_case.toml` and
`matcher_rule_inventory.toml`, a support-check generator reads
`matcher_regression_cases.json` and `matcher_rule_inventory.json` and
generates the corresponding coverage TOML entries automatically.

The two coverage TOML files become **derived artifacts**: they are still
checked in (for audit reproducibility) but bear a `# AUTO-GENERATED — DO NOT
EDIT BY HAND` header, and CI fails if they diverge from what the generator
produces.

This eliminates ~180 of the ~250 lines I wrote for Q54-2.

**Files that stay manual (do not pull into the generator):**

- `app/languages/sv/ingredient_matching/term_registry/coverage_exceptions.toml`
  is the narrow-exception mechanism for source-derived terms that need to
  be accepted before their registry entry exists. It is empty today (only
  the example header). Preserve it as a hand-edited file; the generator
  does not touch it.
- Any registry TOML entry under
  `app/languages/sv/ingredient_matching/term_registry/entries/` that
  carries the `# manual-coverage` marker comment immediately before a
  manual `[[entries]]` block. The marker exempts that block from generator
  overwrite. Pre-flight warns when a marker is present so authors know the
  coverage is intentionally hand-curated.

**L2-B. `dm matcher` CLI with per-pattern subcommands**
A wizard-style CLI for the 4-5 most common patterns. Examples:

```bash
dm matcher add keyword-extra-parent citrusfrukter \
  --kids citron,lime,apelsin,mandarin,clementin,klementin,grapefrukt,blodapelsin \
  --recipe-name "Citrussallad" \
  --ingredient "3-4 citrusfrukter (valfri sort)"

dm matcher add pnb estragon \
  --variants "twin dragon,kafe baby" \
  --reason "dragon→estragon synonym misses these flavored products"

dm matcher add ksbc chili \
  --variants "chiligele,chiligelé,chilijam,chilimarmelad" \
  --reason "sweet chili-jam ≠ dried chili spice"
```

Each subcommand:
- Generates the registry TOML entries with conventional `entry_id` format
- Generates positive (and where applicable, negative) fixtures in JSON
- Adds the inventory entry with the correct adapter_ref
- Invokes the Level 2-A coverage generator instead of hand-editing derived
  coverage TOML
- Adds a regression test stub in `run_deep_matcher_sanity.py`
- Runs pre-flight and reports any remaining issues
- Optionally runs the Track B wrapper at the end

This is the "**one command = one rule change**" target. The CLI is a thin
generator on top of the existing schemas; nothing in the runtime matcher
changes.

**Host/container UX**

The CLI must work as a single command from the host. Today every wrapper run
is `docker compose exec -T -w /app web python support_checks/...`, which is
verbose and hard to remember. The CLI handles the wrapping itself.

Placement and invocation:
- Python module lives at `app/cli/dm.py` (Typer-based, as per design decision
  3 below).
- Phase 4 adds `typer` to `app/requirements.txt` if it is not already
  installed in the runtime image. If adding a dependency is rejected in the
  design-decision step, fall back to raw `argparse`.
- A thin shell wrapper at `bin/dm` (committed, executable) detects whether
  it is running on the host or inside the container:
  - On host: forwards the call as
    `docker compose exec -T -u appuser -w /app web python -m cli.dm "$@"`
  - In container: runs `python -m cli.dm "$@"` directly
- Stefan's `.bashrc` / `.zshrc` already has the project dir on PATH (or we
  add `bin/` to PATH in `direnv`/`.envrc`); after that, `dm matcher ...`
  works from any subdirectory of the project.

UX expectations:
- Stdout of the underlying script is streamed live, not buffered.
- Exit code propagates from the container to the host.
- `dm matcher --help` lists subcommands. `dm matcher <subcommand> --help`
  documents each pattern with examples.
- `dm matcher gates --track A|B` is a thin alias for the current
  `run_matcher_change_gates.py` wrapper so the old workflow keeps working
  during the transition.

**L2-C. Manifest mode** *(alternative to L2-B, complementary)*
For complex changes that don't fit a single CLI subcommand, support a
manifest. The final file format is decided in Design Decision 5; YAML is
shown here only as an illustrative shape:

```yaml
# changes/2026-05-17-citrusfrukter.yml
kind: keyword_extra_parent_fanout
canonical: citrusfrukter
children: [citron, lime, apelsin, mandarin, clementin, klementin, grapefrukt, blodapelsin]
recipe_name: Citrussallad
ingredient: "3-4 citrusfrukter (valfri sort)"
regression_tests:
  - "Citrusfrukter recipe matches citron"
  - "Specific citron recipe does NOT broaden to lime"
```

Run `dm matcher apply changes/2026-05-17-citrusfrukter.yml` to generate
everything. Manifest is checked in alongside the generated code as the
"why this change exists" reference.

### Level 3 — Architectural cleanup (~6-10 hours, on top of Level 2)

**L3-A. Hash-tolerance refactor** *(addresses D)*
Today `variant_id` is derived from a hash that includes `source_ref` text.
Change to derive `variant_id` from a semantically stable identity payload
that excludes `source_ref` but keeps enough disambiguators to remain unique.
The first candidate should be the current `AuditVariant.identity_payload()`
minus `source_ref`; at minimum the v2 key must include `source_id` as well
as canonical/source type/variant text/layer role. `source_ref` becomes
free-form metadata that can be edited without baseline migration.

Risk: requires rebuilding the baseline once with the new hash function. The
old `variant_id` values become invalid. Done as a one-time migration with
clear documentation. A pre-migration uniqueness check is mandatory; if the
v2 identity payload collides for any current variant, the migration is
blocked until the key includes another stable field.

**L3-B. Convention over configuration for entry_id and coverage**
Today `entry_id` is hand-written with a numeric suffix (`citron_083`). The
matching coverage rows are also hand-written and must agree exactly. With a
clear convention (`sv-se.family.{canonical}.{variant}` derived from the
TOML's `canonical` + `variants[0]`), the `entry_id` becomes optional/auto-
generated and the coverage rows become fully derivable.

**L3-C. JSON files as derived artifacts**
Currently `matcher_regression_cases.json` and `matcher_rule_inventory.json`
are hand-edited. After Level 2-A they become semi-derived (coverage TOML is
generated from them, but the JSONs themselves are still authored manually).

Final state: a single source-of-truth schema (probably TOML-only) for
fixtures and inventory. JSON files are generated from TOML and checked in
purely for tool compatibility. This collapses ~3 file types into 1.

**L3-D. File watcher / dev daemon**
`dm matcher dev-watch` starts a background process that runs pre-flight
checks on every file save. The author sees infrastructure errors within
seconds of typing, not at wrapper-run time.

Implementation: Python `watchdog` library, runs the L1-A pre-flight on debounced
file change events.

**L3-E. Schema-driven prefix validation**
Replace the hardcoded allow-lists for `source_ref`, `policy_ref`, `adapter_ref`
in scattered files with a single `app/support_checks/schemas/prefixes.yml`.
All checks read from it. Adding a new prefix is one schema edit.

## Handover to Implementer

This plan is intended to be implemented by an agent (likely Codex) that did
not write it. The following rules apply during implementation.

**Before starting any code:**

1. Read the entire plan once, including the Revision History at the bottom.
   Do not skim — several non-obvious corrections live in the revision notes.
2. Surface the five Design Decisions (next section) to Stefan and get an
   explicit answer on each before writing code. Do not assume the
   "Recommendation:" lines are decisions; they are starting points.
3. Confirm the chosen phase scope with Stefan. Phases 1-2 alone are
   shippable and may be all that is wanted right now. Do not start Phase 3
   without explicit go-ahead.

**During implementation of each phase:**

4. Ship phase-by-phase, not all-at-once. Each phase has its own synthetic
   acceptance test that must pass before the phase is declared complete.
5. After each phase passes its synthetic test, **stop** and confirm with
   Stefan that the phase is accepted before moving to the next. The
   confirmation can be brief ("Phase 1 done, synthetic test green, ready
   for Phase 2?") but it must happen.
6. If a phase reveals a gap or contradiction in the plan, **stop and
   report**. Do not silently expand scope. Stefan decides whether to:
   - Address the gap inside the current phase (small)
   - Defer to a later phase (medium)
   - Update the plan first (large)

**Budget and scope guidance:**

7. Stefan has budget pressure. Prefer narrow, working fixes over ambitious
   refactors when the difference is borderline. If you find yourself
   inventing scope that is not in the plan, log it as a candidate for
   Phase 5+ instead of pulling it forward.
8. The plan's time estimates are upper bounds. If a phase finishes faster
   than estimated, that is success, not "time to expand the scope".
9. Do not refactor unrelated code in the same commits. Every commit should
   map cleanly to one improvement in this plan.

**When the implementation diverges from the plan:**

10. Any deviation from the documented design needs Stefan's sign-off.
    Examples that require sign-off:
    - Picking a different CLI framework than the agreed choice
    - Reordering phases
    - Adding a new improvement that is not in the catalogue
    - Skipping a documented step (e.g. "I think we don't need L1-E")
11. After Stefan signs off on a deviation, update this plan document
    (Revision History at the bottom) in the same commit. The plan is the
    durable record; conversations are not.

**What success looks like:**

12. The synthetic test for each phase is green on a fresh checkout.
13. The runbook (`docs/runbooks/MATCHER_RULE_CHANGE_RUNBOOK.md`) and the
    memory file (`feedback_matcher_runbook.md`) reflect the new flow at
    the end of each phase that touches author-facing behavior.
14. Next time someone does a Q54-2-shaped change, they hit none of the 11
    iterations originally documented. Measure this on a real change, not
    only on the synthetic test.

## Pattern Discovery — Empirical Backing for Phase 4 CLI

The CLI section claims "4-5 most common patterns" without showing the data.
Before the CLI is implemented, a one-time analysis of recent batch reviews
(batches 30-54 or so, ~25 batches) confirms which subcommands are actually
worth building. This is a Phase 4 prerequisite, not extra work.

**Method:**
Scan `app/tests/batch_review_questions.md` for entries marked `fixar
gjorda:` (applied fixes) and count occurrences of each rule type. The
batches are organized chronologically with consistent labels.

**Expected distribution (rough estimate before formal scan):**

| Pattern | Estimated share | Subcommand |
|---|---|---|
| PNB add | ~30 % | `dm matcher add pnb <keyword>` |
| FPB add | ~15 % | `dm matcher add fpb <keyword>` |
| KSBC add | ~15 % | `dm matcher add ksbc <keyword>` |
| BDPK add | ~10 % | `dm matcher add bdpk <keyword>` |
| keyword_extra_parent fan-out | ~8 % | `dm matcher add keyword-extra-parent <canonical>` |
| no_match_policy add | ~8 % | `dm matcher add no-match-policy <policy>` |
| specialty_qualifier (Direction A) | ~6 % | `dm matcher add specialty <keyword>` |
| STOP_WORDS extension | ~4 % | `dm matcher add stop-word <word>` |
| All other / one-off | ~4 % | (no CLI; manual edits) |

**Concrete deliverable for Phase 4:**
A short report `docs/MATCHER_RULE_TYPE_FREQUENCY.md` produced by a
one-shot script that scans batches 30-54 and emits the actual numbers. The
report is updated once before Phase 4 starts and committed.

If the actual distribution diverges materially from estimates, the
subcommand list in L2-B is adjusted accordingly. The cutoff for "worth a
subcommand" is around 5 % share or 5 distinct uses in the analyzed window.

Patterns below the cutoff stay manual — the CLI is an accelerator for the
common case, not a gate that forces every change through it.

## Design Decisions to Make Before Implementation

These choices affect Level 2 and Level 3 scope and should be settled first:

1. **Should `--migrate-hashes` become default?**
   - Pro: removes the most common false-alarm in baseline promotion.
   - Con: hides genuine removals when source_order shifts dropped a real
     entry.
   - Recommendation: keep the flag, but only for one transitional phase, then
     proceed with L3-A which removes the underlying need.

2. **Coverage TOML — auto-emit only, or fail-on-mismatch?**
   - Auto-emit: generator writes, hand-edits are overwritten next promote.
   - Fail-on-mismatch: hand-written coverage TOML rejected if it could have
     been auto-generated; forces the author to use the generator.
   - Recommendation: auto-emit with explicit header. Manual coverage TOML
     becomes a deliberate exception with a comment explaining why.

3. **CLI stack for `dm matcher`**
   - Click vs Typer vs raw argparse. All are fine.
   - Recommendation: Typer (modern, type-hint based, auto-completion).

4. **JSON-as-derived versus TOML-as-derived**
   - L3-C assumes TOML becomes the source. But existing tooling (some
     external consumers? CI?) may depend on JSON being authoritative.
   - Recommendation: investigate before committing to this direction.

5. **Manifest format**
   - YAML (human-friendly) vs TOML (consistent with the rest of the registry)
     vs JSON (consistent with fixtures).
   - Recommendation: TOML, for consistency with the dominant format in the
     registry.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| L3-A baseline rebuild produces a regression that masks a real change | Medium | Run full Track B wrapper before and after the rebuild and diff the test results. |
| L2-B CLI gets stuck on edge cases not covered by the chosen patterns | Medium | Always allow manual fallback to direct file editing. CLI is an accelerator, not a gate. |
| L2-A auto-emit overwrites a hand-authored coverage row that was intentional | Low | Use a `# manual-coverage` marker comment that the generator respects. Pre-flight warns about marked manual rows. |
| L1-B refactor breaks some support_check that uses the constants in non-standard ways | Low | Grep for every `EXPECTED_*` usage before refactoring. |
| L3-C breaks an external tool that reads the JSON | Unknown | Audit first. May veto this improvement. |

## Migration & Rollback Strategy

Each Phase 3 improvement is a refactor that touches existing artifacts. None
of them can ship without a deliberate migration plan and a rollback story.
The Level 1 and Level 2 improvements are additive (new files, new flags) and
do not need migration plans.

### L3-A: Hash-tolerance refactor

**What changes:** `variant_id` is currently a hash derived from a tuple that
includes `source_ref`. New scheme drops `source_ref` from the hash input
while preserving uniqueness through stable fields such as `source_id`,
`source_file`, expected value, and the semantic coverage fields.

**Affected artifacts:**
- `verified_matcher_terms.json` baseline (~5500 variants get new `variant_id`)
- Any external reference to a `variant_id` string (none known, but audit
  first)

**Migration steps:**
1. Add the new hash function in parallel, behind a flag
   (`--use-stable-hash-v2`).
2. Run a dry-run uniqueness audit over all current variants. The v2 identity
   key must produce exactly one unique ID per current variant. If it collides,
   stop and widen the key with another stable field before continuing.
3. Run a one-shot migration script that rebuilds the baseline with the new
   hash function and writes a mapping file `baselines/variant_id_migration_v1_to_v2.json`
   recording every `(old_id, new_id)` pair.
4. Pre-flight gate (L1-A) runs a one-time check: every variant_id in baseline
   appears in either the v1 set (legacy) or v2 set (post-migration). Mixed
   states are flagged.
5. Promote-script reads only v2 once the migration commit is in.
6. The mapping file stays in repo for 30 days after migration as a safety
   net, then deleted.

**Rollback:** revert the migration commit. Old baseline is preserved in git
history. The mapping file enables programmatic reversal if needed (rare).

**Acceptance:** `--migrate-hashes` flag becomes a no-op (kept as alias for
backward compat one release cycle, then removed); editing a `source_ref`
string on any existing fixture does not produce baseline diffs.

### L3-B: Convention over configuration for `entry_id` and coverage

**What changes:** `entry_id` becomes optional and is auto-derived from
`canonical` + first variant when omitted; coverage TOML rows are fully
generated from the registry entry.

**Affected artifacts:**
- All registry TOML entries that use the numeric-suffix convention
  (`citron_083` etc.) — ~3500 entries
- All hand-written coverage rows in `matcher_regression_case.toml` and
  `matcher_rule_inventory.toml` — ~5400 rows

**Migration steps:**
1. The new generator runs in **dry-run + diff mode** first: it writes what
   it would produce to `/tmp` and a diff against the checked-in files is
   reported.
2. The diff is reviewed (likely large but mechanical). Manual exceptions
   are marked with `# manual-coverage` comments where needed.
3. A single migration commit replaces the hand-written content with the
   generated content (the diff from step 1 minus exceptions).
4. From then on, the generator runs as part of promote and rewrites the
   files automatically. Hand-edits without the marker comment are
   overwritten on next promote.
5. Lint rule (or pre-flight check) forbids hand-edits to generated files
   without the marker.

**Rollback:** revert the migration commit. Generator is disabled by
removing it from the promote-script. Hand-editing resumes.

**Acceptance:** authoring one new registry TOML entry requires zero edits
to coverage TOML; the generator produces identical output to what a manual
author would write.

### L3-C: JSON files as derived artifacts

**Prerequisite:** an audit confirms no external consumer depends on JSON
being authoritative. The audit is the first deliverable of L3-C and may
**veto** the rest of the improvement.

**What changes:** `matcher_regression_cases.json` and
`matcher_rule_inventory.json` become generated from TOML source files.

**Affected artifacts:**
- The two JSON files themselves
- Anything that imports/reads these JSONs (audit will enumerate)

**Migration steps:**
1. Audit (grep + manual inspection) — enumerate every reader of the two
   JSON files. Both internal (Python imports, support_checks reads) and any
   external (CI scripts, dashboards, exports). If any reader requires JSON
   as a source of truth, **stop here** and skip L3-C.
2. If audit passes: define TOML schema for fixtures and inventory in
   `app/languages/sv/matcher_contracts/sources/`.
3. Migration script reads existing JSON, emits equivalent TOML. Round-trip
   tested (JSON → TOML → regenerated JSON should equal the original).
4. Single migration commit replaces hand-edited JSONs with generated ones.
   JSON files must remain strict valid JSON, so the generated-file marker
   lives in an adjacent README/manifest or in a checked-in generator metadata
   file, not as a `//` comment inside the JSON.
5. Promote runs the generator. Pre-flight rejects hand-edits to the JSONs.

**Rollback:** revert migration commit. Generator disabled. Hand-editing
resumes.

**Acceptance:** the two JSONs are byte-identical to their generated
versions; modifying a TOML source updates the JSON on next promote.

### L3-D and L3-E

Both are additive (new daemon, new schema file). No migration plan needed
beyond standard "add files, switch over, remove old behavior" pattern.

### Compatibility shims and parallel-running

For all three of L3-A/B/C, the implementation supports a **parallel-running
phase** where old and new behavior coexist behind a flag for at least one
working week. This lets us catch regressions in real use before flipping the
default. The flag is removed in a follow-up commit once the parallel phase
expires without incident.

## Implementation Order

Reordered after a code review of the current support_checks landscape.
The new ordering follows "highest ROI first, riskiest changes last", and
treats Level 3 as the **target end-state** rather than a final big-bang
phase. Each phase is shippable on its own and produces measurable friction
reduction.

### Dependency graph (revised)

```
Phase 1 (low-risk wins — foundation):
   L1-A  pre-flight (empty snapshot doctrine)
   L1-B  narrow constants cleanup (bridge count/list)
   L1-D  inline allow-lists in error messages
   L1-E  audit warning on missing expected_matches
   L1-F  execution-user fix for promote
   (no internal dependencies; can be done in parallel)

         ▼
Phase 2 (biggest ROI — coverage generator):
   L2-A  auto-emit coverage TOML from JSON
         depends on: L1-A (pre-flight validates generator output)

         ▼
Phase 3 (the real fix — stable identity):
   L3-A  hash-tolerance refactor (variant_id excludes source_ref)
         depends on: nothing technical, but easier to validate after L2-A
                     because coverage no longer drifts during the migration

         ▼
Phase 4 (CLI surface — focused, narrow start):
   L2-B  dm matcher CLI, **one** subcommand to start
         depends on: L2-A (generator handles coverage automatically)
   L2-C  manifest mode (decided after L2-B is in production use)

         ▼
Phase 5 (riskier consolidations):
   L3-B  convention-based entry_id + coverage
         depends on: L2-A
   L3-C  JSON-as-derived (audit-gated; may be vetoed)
         depends on: L3-B + audit pass

Independent (any time after Phase 1):
   L3-D  file watcher (re-runs L1-A pre-flight on save)
   L3-E  schema-driven prefix validation
   L1-C  was rolled into L1-B (narrow scope)
```

### Per-phase deliverables (code + docs)

**Phase 1** (target: 2-3 hours, **must-have**, low risk):

*Code:*
- L1-A pre-flight gate with **empty** snapshot. Snapshot mechanism exists
  as a safety valve; `main` should produce an empty snapshot.
- L1-B remove hardcoded `seed match bridge count` and `expected_bridge_ids`
  list in `run_matcher_rule_model_checks.py`. Derive both from
  `MATCH_BRIDGES`.
- L1-D inline allow-lists in every "unknown prefix" error.
- L1-E audit emits explicit warning when a positive fixture is missing
  top-level `expected_matches`.
- L1-F either run promote as `-u appuser` from the wrapper, or have promote
  auto-fallback to staged output on `PermissionError`.
- Add `--tree-root` (or equivalent repo-root/path override) to the wrapper
  and the support checks it invokes, so synthetic flow tests can run against
  a temporary checkout without mutating the working tree.
- `test_phase1_e2e` synthetic acceptance test.

*Documentation:*
- Update `docs/runbooks/MATCHER_RULE_CHANGE_RUNBOOK.md`:
  - Replace "wrapper runs gates sequentially" with the new pre-flight-first
    flow.
  - Document the snapshot file as a safety valve only (not a normal
    state).
  - Document the `-u appuser` (or auto-fallback) for promote.
- Update `~/.claude/projects/.../memory/feedback_matcher_runbook.md`:
  - Replace wrapper invocation examples with the new flow.
  - Remove the "manual constant bump" pattern (re-run promote instead).

After Phase 1: Q54-2-shaped change passes in roughly 2-3 wrapper
iterations instead of 11. Stale-info errors and `docker cp` dance are gone.

**Phase 2** (target: 3-5 hours, **highest ROI**, low risk):

The single highest-leverage change in the whole plan. Eliminates the bulk
of the boilerplate I wrote in Q54-2 (~180 of ~250 lines).

*Code:*
- L2-A auto-emit coverage TOML from `matcher_regression_cases.json` and
  `matcher_rule_inventory.json`.
- `# manual-coverage` marker comment that the generator preserves for
  intentional manual rows.
- Pre-flight (L1-A) reports if coverage TOML diverges from generated
  output.
- `test_phase2_coverage_gen` synthetic acceptance test.

*Documentation:*
- Update `MATCHER_RULE_CHANGE_RUNBOOK.md`:
  - Author writes JSON only. Coverage TOML is generated.
  - The two coverage TOML files now bear an auto-generated header.
- Update [`docs/HOW_TO_ADD_SCRAPERS.md`](HOW_TO_ADD_SCRAPERS.md):
  - The "When a scraper change requires a matcher rule change …" paragraph
    (around line 1020) currently says "promote the accepted X and run the
    matcher parity/inventory checks". After Phase 2, coverage rows are no
    longer hand-authored. Update the paragraph to point at JSON-only
    authoring and the runbook.

After Phase 2: adding a fixture or inventory entry requires zero edits to
coverage TOML.

**Phase 3** (target: 4-6 hours, **the real fix**, medium risk):

Status 2026-05-17: implemented. `variant_id` now uses the stable v2 identity
payload by default, the v1→v2 baseline migration file is committed, and
`--migrate-hashes` is retained only as a backward-compatible no-op alias.

*Code:*
- L3-A `variant_id` hash refactor — derive identity from
  the current audit identity payload minus `source_ref` (or an explicitly
  documented equivalent) and assert that the v2 key has no collisions before
  migration.
- Parallel-running flag (`--use-stable-hash-v2`) is accepted; v2 is the default
  after the one-shot migration, with `--legacy-hash-v1` available for debugging.
- One-shot migration script writes `baselines/variant_id_migration_v1_to_v2.json`
  mapping every old → new ID.
- `--migrate-hashes` becomes a no-op alias for backward compat, then
  removed in a follow-up commit.
- `test_phase3_hash_tolerance` synthetic acceptance test.

*Documentation:*
- Update `MATCHER_RULE_CHANGE_RUNBOOK.md`:
  - Remove `--migrate-hashes` references.
- Add a short "Hash migration v1 → v2" note in
  `docs/MATCHER_REGISTRY_ARCHITECTURE.md` (created in this phase).

After Phase 3: editing a `source_ref` string never produces a baseline diff.

**Phase 4** (target: 3-4 hours per subcommand, **focused CLI**, low risk):

Codex's point: start with one verified-valuable subcommand. Don't build a
full CLI surface up front; let actual use shape it.

*Code:*
- Pattern discovery script + `docs/MATCHER_RULE_TYPE_FREQUENCY.md`.
- `app/cli/dm.py` (Typer-based) with **one** subcommand:
  `dm matcher add keyword-extra-parent`. Selected because it is one of the
  most uniform patterns (per pattern discovery) and has the cleanest schema.
- `bin/dm` shell wrapper for host/container transparency.
- `dm matcher gates --track A|B` as an alias for the existing wrapper so
  the old workflow keeps working.
- `test_phase4_cli_e2e` synthetic acceptance test.

Subsequent subcommands are added only after the first is in production use
for at least a week and the next pattern's frequency in the analysis
justifies it.

*Documentation:*
- Update `MATCHER_RULE_CHANGE_RUNBOOK.md`:
  - Add "common workflows" section with the CLI subcommand as the default
    authoring flow for the keyword_extra_parent pattern.
  - Keep manual editing as the documented path for everything else.
- Update `feedback_matcher_runbook.md` with the new entry point.
- Update [`README.md`](../README.md):
  - "Development / Contributing" section (around line 186) currently links
    to `INSTALL.md` and the HOW_TO guides. Add a one-line pointer:
    *"For matcher rule changes, see [docs/runbooks/MATCHER_RULE_CHANGE_RUNBOOK.md]
    or run `dm matcher --help`."*
- Update [`CLAUDE.md`](../CLAUDE.md):
  - The "Matcher Rule Runbook (MANDATORY)" section currently shows
    `docker compose exec ... run_matcher_change_gates.py`. Add the
    `dm matcher` CLI as the new default and demote the raw wrapper
    invocation to "fallback".
- Update [`INSTALL.md`](../INSTALL.md) only if the L1-F user-permission fix
  changes the developer install steps. Likely a single note: *"if you run
  registry promote operations, prefix with `-u appuser` or use `dm matcher`
  which handles this transparently."*
- Update [`docs/HOW_TO_ADD_SCRAPERS.md`](HOW_TO_ADD_SCRAPERS.md):
  - The paragraph updated in Phase 2 now also points at `dm matcher` as
    the default flow for the matcher rule changes that accompany a scraper
    change.

L2-C (manifest mode): decided after Phase 4 ships. If the single
subcommand covers the common case, manifest mode may be unnecessary.

**Phase 5** (target: 6-10 hours, **end-state consolidation**, medium-high risk):

*Code:*
- L3-B convention-based `entry_id` and coverage generation.
- L3-C JSON-as-derived (audit first; may be vetoed).
- L3-D file watcher / dev daemon.
- L3-E schema-driven prefix validation.

*Documentation:*
- Update `MATCHER_REGISTRY_ARCHITECTURE.md` to describe the final data
  model (single TOML source of truth).

After Phase 5: the registry has one source of truth, infrastructure errors
surface live in the editor, prefix changes are a single schema edit.

### Total time estimate (revised)

| Phase | Time | Cumulative |
|---|---|---|
| Phase 1 | 2-3 h | 2-3 h |
| Phase 2 | 3-5 h | 5-8 h |
| Phase 3 | 4-6 h | 9-14 h |
| Phase 4 (one subcommand) | 3-4 h | 12-18 h |
| Phase 5 | 6-10 h | 18-28 h |

The plan is shippable in any prefix. Phases 1-2 alone (5-8 hours) eliminate
the largest mechanical boilerplate. Phases 1-3 (9-14 hours) also remove the
hash-migration footgun. Phase 4 onwards is the polish layer.

## Acceptance Test Infrastructure

The acceptance criteria below are only meaningful if they can be measured
automatically. Each phase ships with a synthetic end-to-end test that
exercises the entire flow.

**Location:** `app/support_checks/tests/test_rule_change_flow.py` (new file).

The directory `app/support_checks/tests/` does **not** exist today. Phase 1
creates it with:
- `app/support_checks/tests/__init__.py` (empty, marks as package)
- `app/support_checks/tests/test_rule_change_flow.py` (the synthetic tests)
- A short README in the directory explaining that these are infrastructure
  acceptance tests, distinct from `app/tests/` (which is gitignored and
  used for batch review work).

The directory is **git-tracked** (unlike `app/tests/`). The wrapper already
has `--include-support-self-checks`; Phase 1 extends that mode to run these
infrastructure flow tests.

**Test harness prerequisite:** Phase 1 adds a `--tree-root` option (or an
equivalent repo-root/path override) to `run_matcher_change_gates.py` and the
support checks it invokes. The synthetic tests must operate on a temporary
copy of the matcher contract/registry tree, not the developer's live working
tree.

**Phase 1 synthetic test — `test_phase1_e2e`:**

1. Set up: create a temporary copy of the registry tree under `/tmp/dm-test-tree`.
2. Inject a synthetic `keyword_extra_parent.toml` entry for a fake canonical
   `test-citrus` with one child variant `test-orange`.
3. Inject a corresponding fixture in `matcher_regression_cases.json`, one
   inventory entry in `matcher_rule_inventory.json`, and the current
   manually-authored coverage rows in `matcher_regression_case.toml` and
   `matcher_rule_inventory.toml`.
4. Run the wrapper:
   `python support_checks/run_matcher_change_gates.py --track B --tree-root /tmp/dm-test-tree`.
5. Assert:
   - Exit code 0 on the first run.
   - No `--migrate-hashes` was needed.
   - No `EXPECTED_*` constant was manually bumped during the run.
   - Pre-flight reported zero NEW issues.
6. Tear down: delete `/tmp/dm-test-tree`.

**Phase 2 synthetic test — `test_phase2_coverage_gen`:**

1. Set up: temporary registry tree as above.
2. Inject one positive fixture and one inventory entry in JSON without
   adding hand-written coverage TOML rows.
3. Run the coverage generator/pre-flight on the temporary tree.
4. Assert:
   - Exit code 0.
   - The generated `matcher_regression_case.toml` and
     `matcher_rule_inventory.toml` contain the expected coverage rows.
   - Re-running the generator produces no diff.
   - Track B wrapper returns green against the generated coverage.
5. Tear down.

**Phase 3 synthetic test — `test_phase3_hash_tolerance`:**

1. Set up: snapshot baseline `variant_id` set.
2. Run the v2 identity uniqueness audit and assert no collisions.
3. Modify the `source_ref` string on an arbitrary existing fixture.
4. Run pre-flight and promote.
5. Assert:
   - No "MISSING from fresh scan" warnings.
   - No `--migrate-hashes` flag required.
   - Baseline `variant_id` set unchanged.

**Phase 4 synthetic test — `test_phase4_cli_e2e`:**

1. Set up: temporary registry tree as above.
2. Invoke `dm matcher add keyword-extra-parent test-citrus --kids test-orange --tree-root /tmp/dm-test-tree`.
3. Assert:
   - Exit code 0.
   - `keyword_extra_parent.toml`, fixture JSON, inventory JSON, and
     regression test stub all exist with expected content.
   - Track B wrapper invoked by the CLI returned green.
4. Tear down.

These tests are runnable in CI and locally. They are the **definition of
done** for each phase; phases are not declared complete without a green run
of their synthetic test on a fresh checkout.

## Acceptance Criteria per Phase

**Phase 1 acceptance:**
- Adding a synthetic new `keyword_extra_parent` family (1 entry, 1 fixture,
  1 inventory entry, with today's required manual coverage rows) and running
  `python support_checks/run_matcher_change_gates.py --track B --tree-root ...`
  passes in a single execution with no constant bumps and no
  `--migrate-hashes`.
- Adding a bridge does not require hand-editing the seed bridge count or the
  bulk `expected_bridge_ids` list. Promote-owned constants remain updated by
  promotion.
- Pre-flight reports all known infrastructure problems together. No single
  issue is reported in isolation.

**Phase 2 acceptance:**
- Adding a new fixture or inventory entry in JSON requires zero hand edits to
  `matcher_regression_case.toml` or `matcher_rule_inventory.toml`.
- `matcher_regression_case.toml` and `matcher_rule_inventory.toml` are
  marked as generated; any hand-edit fails CI unless explicitly marked as
  manual.
- The coverage generator is idempotent: generate once, rerun, diff is clean.

**Phase 3 acceptance:**
- Editing a `source_ref` string on an existing fixture does not require
  `--migrate-hashes`.
- The v2 `variant_id` identity payload is collision-free on the current
  variant set before migration.
- Baseline migration produces a committed old→new mapping file and a green
  Track B run before and after the migration.

**Phase 4 acceptance:**
- `dm matcher add keyword-extra-parent citrusfrukter --kids X,Y,Z ...`
  completes successfully and generates a green Track B run with no further
  manual edits.
- `dm matcher gates --track A|B` is a thin, working alias for the existing
  wrapper.

**Phase 5 acceptance:**
- `dm matcher dev-watch` reports pre-flight problems within 5 seconds of
  a file save.
- Prefix allow-lists live in one schema file.
- L3-C only proceeds if the JSON-authority audit passes; otherwise it is
  explicitly vetoed and documented.

## Out of Scope for This Plan

This plan does **not** fix the following. Each is either tracked elsewhere
or genuinely separate concerns.

- Cleaning up the 158 grandfathered unwired `match_bridge` entries. That
  is registry hygiene, not flow friction; it can be done as a separate task
  once the Phase 4 CLI is available (the CLI can auto-emit the dual-write).
- Migrating away from `match_bridge.toml` to a runtime-wired implementation.
  That is the original "matcher migration" still listed as pending in
  `match_bridges.py:1`; it is significantly larger than this plan.
- Performance optimization of pre-flight if it becomes too slow on large
  repos. Expected runtime is under 30 seconds at current registry size;
  revisit if it grows beyond 2 minutes.
- Internationalization of error messages. All output stays in English to
  match the rest of the matcher infrastructure.
- IDE/LSP integration. L3-D file watcher provides equivalent feedback
  without needing IDE-specific plugins.
- A GUI or web interface for rule changes. The CLI plus the runbook are
  the supported authoring surfaces.

(The plan originally listed four line_ref anchor failures and three löjrom
fixture coverage gaps as known pre-existing issue instances. Those have
since been fixed on `main` and are no longer tracked here.)

**End-user documentation is not affected.** This plan only changes
developer-facing flows. The Swedish and English user manuals
(`docs/USER_MANUAL_SVENSKA.md`, `docs/USER_MANUAL_ENGLISH.md`), the security
doc, the cache fallback runbook, and the testing doc all describe runtime
or UI behavior that is unchanged by these refactors. Do not update them as
part of this plan. Developer-facing docs (`README.md` § Development,
`CLAUDE.md`, `INSTALL.md`, `docs/HOW_TO_ADD_SCRAPERS.md`) are addressed in
the relevant phase deliverables above.

## Revision History

**2026-05-17 — Phase 3 implementation**

Implemented L3-A. Verified the v2 identity payload is collision-free on the
current 5517 variants, migrated the verified-term baseline to v2 IDs, and
committed `variant_id_migration_v1_to_v2.json` as the old→new mapping. The
runbook now omits hash-migration instructions; true removals still require
`--allow-removals`.

**2026-05-17 — Codex code-review pass**

Codex grepped the actual support_checks code and surfaced facts the original
draft had wrong or imprecise. Changes applied:

| Original draft claim | Reality (per Codex + verified) | Plan change |
|---|---|---|
| `promote_term_baseline.py` only updates one `EXPECTED_*` constant. Need a generalized single-source module. | Promote already auto-updates three: `EXPECTED_VERIFIED_TERM_VARIANT_COUNT`, `EXPECTED_VERIFIED_TERM_UNIQUE_COVERAGE_KEYS`, `_EXPECTED_UNIQUE_COVERAGE_KEYS`. The Q54-2 manual bumps were user error — should have re-run promote. | L1-B narrowed to the two genuinely hardcoded items: `seed match bridge count` and `expected_bridge_ids` in `run_matcher_rule_model_checks.py`. The generalized `_expected_counts.py` module proposal dropped. |
| `--migrate-hashes` is a workaround for a problem the codebase doesn't address. | The `_content_key` helper in `promote_term_baseline.py:302` already detects content-equivalent variants; `--migrate-hashes` activates that path. The friction is that the flag must be remembered. | Root Cause D rewritten to acknowledge the existing mechanism. L3-A still removes the underlying need by changing `variant_id` derivation. |
| `/app` is read-only in container; need writable mount in `docker-compose.dev.yml`. | The dev mount is already writable (`./app:/app` in dev compose) for `appuser`; `docker compose exec` defaults to root, which is not writable on this bind-mounted checkout. | L1-F rewritten as execution-user fix (`-u appuser` or auto-fallback), not a mount change. Security analysis still applies. |
| Seven pre-existing infrastructure issue instances (4 line_ref anchors, 3 löjrom coverage gaps) will be tracked in the snapshot at Phase 1 start. | Those have since been fixed on `main`. Verified: 1488/1488 fixtures covered, 789/789 anchors current. | Out-of-scope list cleaned. Snapshot doctrine reframed: `main` should produce an empty snapshot; growth is a smell. |
| Implementation order: coverage TOML generator + CLI bundled in Phase 2. | Codex's recommendation: coverage generator is the biggest ROI on its own and should ship before CLI. CLI should start with one verified subcommand. | Phases re-split: Phase 2 = coverage generator only; Phase 4 = CLI with one subcommand. Hash refactor (L3-A) moved up to Phase 3, before CLI, so the "real fix" is in place before the polish layer. |
| `seed match bridge count` is "in a third file" without specifics. | Found at `run_matcher_rule_model_checks.py:340` (the set) and `:624` (the count check). | Source locations recorded in Root Cause B. |

Codex's principle that the plan honors: **single source of truth + generated
artifacts + stable semantic identity, delivered incrementally**, not as a
big-bang Level 3 migration. Phase 1-2 are stepping stones; Phase 3-5 are the
end state.
