# Matcher DM Unified Entry Point Plan

Status: Phase 0/1 implemented on 2026-05-18; Phase 2/3 remain future work.

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

After Phase 1 is green, consider a narrow cleanup that migrates existing wrapper
internals to the shared runner where it removes duplicate argv/env/cwd logic
without changing behavior. Do this only after the new wrappers are stable.

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

This phase is optional and should wait until Phase 1 wrappers are in use. Avoid
creating a second documentation source unless agents/humans still have trouble
finding the manual path from `dm matcher --help` and the runbook.

Trigger Phase 2 only when real review work shows the gap. Concrete trigger
signals:

- an agent asks Stefan how to handle a manual-only matcher rule type
- an agent invents a non-`dm matcher` workaround for a manual-only rule type
- repeated review notes show uncertainty about whether a rule type has an `add`
  command

Consider a non-writing helper:

```bash
dm matcher guide <shape>
```

Example:

```bash
dm matcher guide pnb
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

## Phase 3: Future `add` Commands

Keep the existing discipline:

- one new `add` command at a time
- choose from real frequency/repetition
- prefer deterministic append-only TOML surfaces
- defer runtime-table commands until there is either a declarative source or a
  very safe codemod surface

Current authoring commands:

- `dm matcher add keyword-synonym`
- `dm matcher add keyword-extra-parent`

Likely future candidates:

- `dm matcher add ingredient-parent`
- `dm matcher add offer-extra-keyword`
- `dm matcher add pnb` only after the runtime-table surface is made safe
- `dm matcher add fpb` only after the runtime-table surface is made safe

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

Remaining:

- Should support-check self-checks stay only under
  `dm matcher gates --include-support-self-checks`, or should Phase 1 add a
  visible alias such as `dm matcher self-checks`? Preferred direction: keep the
  existing flag. Support-check changes are rare, and a dedicated subcommand
  would add discoverability noise.
- Should `dm matcher regen --check` check both generated JSON and generated
  coverage without writing, or should it remain a write-oriented fix command
  only? Preferred direction: add `--check`. It gives a quick read-only drift
  check without paying the full pre-flight cost.

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
- Raw scripts remain documented as fallback/debug entry points.
- `./bin/dm matcher --help` exposes the common operation list from Phase 1.

## Rough Estimate

| Phase | Scope | Estimate |
| --- | --- | ---: |
| Phase 0 | Shared runner/helper and tests | 1-2h |
| Phase 1 | Thin wrappers, docs, memory updates | 3-5h |
| Phase 2 | Optional `guide` helper if triggered | 2-3h |
| Phase 3 | Future authoring commands, one at a time | 2-4h each for simple TOML shapes; runtime-table commands need a separate estimate |
