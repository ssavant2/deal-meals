# Matcher DM Unified Entry Point Plan

Status: Phase 0/1, post-Phase-1 cleanup, Phase 2 guide, and Phase 3 TOML
surface authoring implemented on 2026-05-18. Runtime-table CLI remains a
separate future workstream.

## Goal

Make `./bin/dm matcher` the obvious first stop for matcher work.

The goal is not to automate every matcher edit. The goal is to remove the
current mental split between:

- `dm matcher add ...` for supported generated rule shapes
- `dm matcher gates ...` after manual edits
- raw `python support_checks/...` commands for single operations

The intended end state:

```text
Start with ./bin/dm matcher.

dm matcher add <shape>    creates supported deterministic rule shapes
dm matcher guide <shape>  explains supported and manual-only rule paths
dm matcher gates ...      validates manual or generated changes
dm matcher dev-watch      gives live pre-flight feedback while editing
dm matcher <tool>         wraps common support-check operations

Raw support_checks scripts remain callable as fallback/debug tools.
```

## Principle

`dm matcher` is the entry point. `dm matcher add` is only the automated
authoring subset.

Unsupported rule shapes should not become separate workflows. They should still
be described as:

1. edit the files manually according to the runbook
2. use `dm matcher preflight` / `dev-watch` while iterating
3. use `dm matcher gates --track A|B ...` for final proof

## Why

The current setup is much better than before, but still asks agents and humans
to remember three categories:

- generated rule authoring commands
- gate wrapper commands
- individual raw support-check scripts

That is workable, but it is easy to drift back into "which path does this rule
type use?" thinking. A unified CLI keeps the mental model stable:

```text
Is there an add command? Use it.
No add command? Edit manually, but still use dm matcher to check it.
Need one specific maintenance operation? Use dm matcher for that too.
```

## Non-Goals

- Do not force every matcher rule type into `dm matcher add`.
- Do not hide raw scripts or remove direct script access.
- Do not build large authoring commands before a real repeated need exists.
- Do not add wrappers that change semantics compared with the underlying
  support check.
- Do not create standalone `add` commands for generated TOML mirrors or
  temporary coverage/contract support artifacts.

## Proposed Thin Wrappers

Add small `dm matcher` subcommands for common raw operations:

```bash
./bin/dm matcher preflight
./bin/dm matcher sanity
./bin/dm matcher promote
./bin/dm matcher regen
./bin/dm matcher refresh-line-refs
./bin/dm matcher diagnose   # later; diagnostics has more flags/UX questions
```

Each wrapper should:

- preserve the underlying script exit code
- expose stable/common flags explicitly for discoverability
- allow raw advanced flags after `--` for wrappers where the underlying script
  has useful uncommon options
- support `--tree-root` where the underlying tool supports it
- support `--dry-run` where the underlying tool supports it
- use the same report-root/env handling style as existing `dm matcher gates`
- keep raw script names visible in help text for debugging

Decision: use both stable flags and pass-through. Common flags such as
`--tree-root`, `--dry-run`, `--allow-removals`, `--format`, and `--report-root`
should be first-class Typer options. Less common raw-script flags should be
accepted after `--` and passed through unchanged.

Maintenance commands named `regen` or `refresh-*` are fix commands. They should
write by default when the wrapped operation has a write mode, because their name
already communicates intent. Provide `--check` or `--dry-run` where the
underlying tool supports read-only inspection.

CLI help should remain readable as the command count grows. Prefer command help
text that naturally groups commands by role:

- Authoring: `add`
- Validate/iterate: `gates`, `preflight`, `sanity`, `dev-watch`
- Maintain: `promote`, `regen`, `refresh-line-refs`

If Typer command grouping becomes ergonomic later, use it, but do not block
Phase 1 on help-layout polish.

## Phase 0: Shared Wrapper Runner

Before adding several thin wrappers, add a small internal runner helper in
`app/cli/dm.py` so wrapper behavior stays consistent.

Expected responsibilities:

- build support-check script argv deterministically from stable flags plus
  optional raw pass-through args
- apply `--tree-root` and `--report-root` consistently where relevant
- preserve cwd choices used by existing wrappers
- print the command before running, matching existing `dm matcher gates` style
- preserve the underlying exit code

Sketch:

```text
_run_support_check(script_name, args, tree_root=None, report_root=None, cwd=None)
```

Do not change existing `add`, `gates`, or `dev-watch` behavior while introducing
this helper.

Post-Phase-1 cleanup: migrate existing wrapper internals to the shared runner
where it removes duplicate argv/env/cwd logic without changing behavior.

## Phase 1: Wrapper Basics

Implement the low-risk wrappers first:

```bash
dm matcher preflight
dm matcher sanity
dm matcher promote
dm matcher regen
dm matcher refresh-line-refs
```

Suggested mappings:

| Command | Wraps | Notes |
| --- | --- | --- |
| `preflight` | `support_checks/run_matcher_change_preflight.py` | Support `--tree-root`, `--format`, `--refresh-snapshot`. |
| `sanity` | `support_checks/run_deep_matcher_sanity.py` | No new behavior; mainly discoverability. |
| `promote` | `support_checks/promote_term_baseline.py` | Support `--dry-run`, `--allow-removals`, `--migrate-hashes`, `--output-dir`. |
| `regen` | `generate_matcher_contract_json_from_toml_sources.py --write` then `generate_matcher_registry_coverage.py --write` | Support `--tree-root`; default `--what all`; allow `--what json`, `--what coverage`, or `--what all`. |
| `refresh-line-refs` | `support_checks/refresh_matcher_rule_inventory_line_refs.py --write` | Host/tree-root oriented maintenance. |

Acceptance:

- `./bin/dm matcher --help` exposes all common matcher operations.
- Help output lists `add`, `gates`, `dev-watch`, `preflight`, `sanity`,
  `promote`, `regen`, and `refresh-line-refs`.
- Wrappers are covered by focused CLI tests for argv construction/exit code.
- Existing raw-script workflows still work unchanged.
- Runbook uses wrapper commands first and labels raw script commands as
  fallback/debug.
- `CLAUDE.md` and
  `/home/stefan/.claude/projects/-docker-apps-deal-meals-dev/memory/feedback_matcher_runbook.md`
  are updated so future agents treat raw support-check scripts as fallback/debug
  paths, not defaults.

## Phase 2: Discoverability For Manual Rule Shapes

Implemented as a non-writing helper:

```bash
dm matcher guide pnb
dm matcher guide keyword-synonym
dm matcher guide --list
```

Output should say whether a generated `add` command exists. If not, it should
name the expected files and the normal gate command, e.g.:

```text
pnb is not supported by dm matcher add yet.
Edit blocker_data.py / PRODUCT_NAME_BLOCKERS.
Add a focused run_deep_matcher_sanity.py regression.
Run: ./bin/dm matcher gates --track A
```

This may be enough to avoid prematurely adding risky `add` commands for runtime
tables.

## Phase 3: Complete TOML-Surface Authoring

Phase 3 should finish the simple mental model:

```text
TOML registry rule surface -> dm matcher add should exist.
Python runtime table       -> manual edit + dm matcher gates.
```

This is a clearer boundary than choosing future `add` commands one at a time
from a mixed TOML/Python candidate list. It makes `dm matcher add --help` the
expected place to look for registry-TOML authoring, while keeping runtime-table
codemods as a separate workstream.

"TOML registry rule surface" means the term-registry entry files that define
live matcher behavior. It does not mean every TOML file in the matcher tree.
Generated mirrors, fixture/inventory contract sources, and temporary coverage
exceptions remain support artifacts that are updated by `regen`, `refresh-*`,
or by an `add` command as proof data; they are not standalone rule shapes.

Supported after Phase 3:

- `dm matcher add keyword-synonym`
- `dm matcher add keyword-extra-parent`
- `dm matcher add ingredient-parent`
- `dm matcher add offer-extra-keyword`
- `dm matcher add ingredient-routing-parent`
- `dm matcher add parent-match-only`
- `dm matcher add recipe-routing-helper`
- `dm matcher add no-match-policy`
- `dm matcher add extraction-helper`

### Phase 3A: Simple TOML Mappings

Implemented the remaining deterministic mapping-like TOML surfaces with a shared
internal helper where practical:

- `dm matcher add ingredient-parent`
- `dm matcher add offer-extra-keyword`
- `dm matcher add ingredient-routing-parent`
- `dm matcher add parent-match-only`
- `dm matcher add recipe-routing-helper`

Expected default pattern:

- append the relevant registry TOML entry
- add or update a focused `run_deep_matcher_sanity.py` regression when the
  surface affects runtime behavior
- use convention-derived coverage when the registry loader supports it
- run baseline promotion plus light registry/export/sanity gates
- support `--dry-run`, `--tree-root`, duplicate guards, stable refs, and focused
  sanity proof
- keep fixture/inventory generation explicit to the commands that own it;
  structured commands require existing durable refs when runtime models need
  them

### Phase 3B: Structured TOML Policies

Implemented commands for TOML surfaces that need more schema/design care:

- `dm matcher add no-match-policy`
- `dm matcher add extraction-helper`

These are not treated as lightweight mapping aliases. `no-match-policy`
requires existing fixture refs before it writes, and `extraction-helper` is
explicit that it covers a code-owned extraction output rather than replacing
the extraction.py change itself.

### Explicitly Out Of Scope

- `match_bridge.toml`: staged/declarative-only; new bridge rows are not
  runtime-wired by themselves and often require dual-write behavior.
- Generated/contract support TOMLs: `matcher_regression_case.toml`,
  `matcher_rule_inventory.toml`, `matcher_contracts/sources/*.toml`, and
  `coverage_exceptions.toml`. They may be written as supporting proof, but
  should not get standalone `dm matcher add` commands.
- Python runtime tables and code surfaces: PNB, FPB, GPB, KSBC, BDPK,
  `STOP_WORDS`, specialty rules, form/processed rules, and backend-only guards.

Python runtime surfaces may deserve future CLI help, but that should be a
separate plan around declarative migration or AST/codemod editing with strong
format tests.

Phase 3 implementation discipline still applies inside this clearer boundary:

- shared helper built where it reduced duplication
- small commands implemented in sensible batches, with each surface
  independently tested
- `no-match-policy` and `extraction-helper` did not force complexity into the
  simple mapping helper
- runbook, `CLAUDE.md`, memory, and `dm matcher guide` updated for supported
  surfaces

## Open Questions

Settled before Phase 0:

- Wrappers use explicit stable flags plus `--` pass-through where useful.
- `dm matcher sanity` stays a plain wrapper for now. Add filtering only after a
  repeated real need appears.
- `dm matcher diagnose` waits. Diagnostics has a richer interactive UX and
  should not be wrapped until the desired CLI shape is stable.
- `dm matcher regen` replaces separate `regen-json` / `regen-coverage`
  subcommands. It runs both by default, with `--what json|coverage|all` for
  targeted maintenance.

Settled during implementation:

- Support-check self-checks stay under
  `dm matcher gates --include-support-self-checks`. Support-check changes are
  rare, and a dedicated subcommand would add discoverability noise.
- `dm matcher regen --check` checks both generated JSON and generated coverage
  without writing. It gives a quick read-only drift check without paying the
  full pre-flight cost.

Governance: deviations from the settled choices above should be noted in this
plan before implementation continues. Larger behavior changes or new authoring
commands should get Stefan sign-off first.

## Risk And Rollback

The wrappers must not become a second implementation of the support checks.

Risk controls:

- raw scripts remain unchanged and callable
- wrappers only build argv/env/cwd and preserve exit codes
- tests cover command construction, exit-code propagation, and help output
- existing `add`, `gates`, and `dev-watch` behavior stays unchanged

Rollback:

- remove or disable a broken wrapper without touching matcher runtime logic
- fall back to the raw support-check script named in the wrapper help text
- keep runbook fallback/debug commands available until wrapper usage is proven

## Done Criteria

- The runbook can say: "Start with `./bin/dm matcher --help`" without caveats.
- Common operations no longer require memorizing raw support-check script names.
- Unsupported authoring shapes still feel like part of the same `dm matcher`
  workflow.
- Manual-only rule shapes are discoverable through `dm matcher guide <shape>`.
- Raw scripts remain documented as fallback/debug entry points.
- `./bin/dm matcher --help` exposes the common operation list from Phase 1.
- When Phase 3 is implemented, all live TOML registry rule surfaces except
  `match_bridge.toml` have an `add` command and corresponding `guide` entry.

## Rough Estimate

| Phase | Scope | Estimate |
| --- | --- | ---: |
| Phase 0 | Shared runner/helper and tests | 1-2h |
| Phase 1 | Thin wrappers, docs, memory updates | 3-5h |
| Phase 2 | `guide` helper | implemented |
| Phase 3A | Complete simple TOML mapping commands | implemented |
| Phase 3B | Structured TOML policy/scaffold commands | implemented |
| Runtime-table CLI | Separate future workstream, not Phase 3 | requires separate design/estimate |
