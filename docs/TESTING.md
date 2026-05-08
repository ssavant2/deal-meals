# Testing

Deal Meals keeps two different kinds of local checks:

- **Tracked app-support checks** live in `app/tests/run_*_checks.py`. These are
  small, deterministic scripts that support the app itself and can be run in the
  normal web container without pytest.
- **Private/dev workbench tests** live in ignored files such as
  `app/tests/test_*.py`, live scraper scripts, cache benchmark fixtures, and
  batch-review notes. These are useful during local development but are not part
  of the public support surface.

## Sanity Check

Run this first after touching matching, store plugin discovery, or startup
registry cleanup:

```bash
docker compose exec -T -w /app web python tests/run_sanity_checks.py
```

The sanity check covers:

- a few high-value Swedish ingredient matching false-positive/true-positive
  cases
- parity between pair-level audit matching, full recipe matching, and cached
  recipe matching
- store plugin discovery import/initialization errors
- fail-safe store registry startup cleanup when plugin discovery fails

It does not scrape websites, use live product data, or require a database.

## App Support Checks

Run the tracked support suite with:

```bash
docker compose exec -T -w /app web python tests/run_app_support_checks.py
```

This runs the sanity check plus the tracked helper checks for cache doctor
metadata, recipe cache refresh decisions, offer-refresh cache decisions,
scheduled cache reconciliation decisions, recipe-delta patch rollback behavior,
pantry search-term index policy,
candidate routing, ingredient term maps, ingredient-routing mode normalization,
delta verification policy, and the minimal
frontend smoke.

The frontend smoke can also be run directly:

```bash
docker compose exec -T -w /app web python tests/run_frontend_smoke.py
```

It opens the four main pages in Chromium at desktop and mobile viewport sizes,
captures `pageerror`/`console.error`, and performs a few safe UI interactions. It
uses Python Playwright from the web image; no Node toolchain is required.

## Cache And Recipe Scraper Smoke

After touching cache refresh logic or recipe scraper fetch limits, also verify
the live app behavior:

- Run syntax/import checks for the touched modules, for example
  `PYTHONPYCACHEPREFIX=/tmp/deal-meals-pycache python3 -m py_compile ...`.
- Run `git diff --check`.
- For recipe-cache delta changes, perform a small incremental recipe scrape and
  inspect the web logs for `CACHE_RECIPE_DELTA_SUMMARY`. A clean small scrape
  should apply recipe-delta, normally with `verification=probation_skip` so the
  web process does not run a full-cache preview. Stale indexes, large full
  imports, missing changed IDs, or failed verification should fall back to a
  full rebuild.
- The support suite also includes `run_recipe_delta_patch_checks.py`, which uses
  temporary recipe rows to verify recipe-delta no-op handling, changed/removed
  patching, rejected patch scopes, and rollback if an insert fails after the
  cache rows have been deleted inside the patch transaction.
- For cache diagnostics changes, call `GET /api/cache/doctor`. A healthy cache
  should return `status=ok`, matching `cache_metadata.total_matches` and
  `recipe_offer_cache` row count, a compact `cache_metadata.last_operation`
  summary, and rolling fallback-frequency stats from
  `cache_metadata.operation_history`.
- For scheduled cache reconciliation changes, run
  `docker compose exec -T -w /app web python tests/run_cache_reconciliation_checks.py`.
  Reconciliation is opportunistic: after scheduled recipe/store jobs it should
  run only when the cache is ready, the app has been idle long enough, and the
  last full rebuild is old or enough delta/skip operations have accumulated.
- For store-offer cache refresh changes, run the same store twice in dev. The
  first run may choose `offer_refresh_strategy=full` to establish a compatible
  baseline; the second identical run should choose `offer_refresh_strategy=skip`
  without `delta_full_preview`/`delta_patch_preview`. Cache doctor should expose
  `offer_refresh_strategy`, `offer_refresh_reason`, and
  `compiled_offer_baseline_committed=true`. If changed offers are detected,
  `last_operation` should include `changed_offer_sample`,
  `offer_change_counts`, and `offer_delta_impact_mode`. Offer-delta runs that
  choose the delta path should normally log `verification=probation_skip`, so
  the web process does not run a full-cache preview. Small-store scenarios
  should be judged by impacted recipe ratio, not by changed-offer percentage
  alone; a high changed-offer percentage may still choose delta when
  `impacted_recipe_ratio_pct` is below the configured threshold. Changed offers
  with `impacted_recipe_count=0` should choose `offer_refresh_strategy=skip` with
  `offer_refresh_reason=offer_changes_no_cache_impact`, refreshing offer
  baselines without patching the recipe cache.
- For cache candidate-selection changes, inspect `CACHE_REBUILD` and
  `CACHE_REBUILD_SUMMARY` for `recipe_selection_mode`. The default term-index
  cache path should use `recipe_selection_mode=term_index_full_scope`; FTS is
  kept for recipe search and legacy matcher paths, not as a pre-filter for the
  term-index recipe cache.
- For matcher/cache parity changes that need a live full-DB check, see
  [Matcher/Cache Full DB Diff](#matchercache-full-db-diff).
- For configured recipe counts, remember that the number is a target for
  successfully parsed recipes. The scraper may try a bounded hidden buffer of
  extra URLs, while UI progress should show found recipes against the configured
  target rather than raw URL attempts.
- For recipe URL discovery-cache changes, run the same small incremental scrape
  twice for a sitemap/list source. The first run may log
  `URL discovery: recorded_non_recipe=...`; the second should log
  `URL discovery prefilter: ... skipped_discovery=...` when reusable misses are
  present. Clearing or deleting a recipe source should also clear its discovery
  rows.
- For pantry search-term index changes, refresh the index in dev with
  `POST /api/pantry-search-index/refresh`, keep
  `PANTRY_SEARCH_TERM_INDEX_MAX_CANDIDATES=0` so normal queries are not capped,
  then compare pantry latency, fallback reasons, and top results against the
  legacy path. The index path is enabled by default, but falls back to legacy if
  the index is missing or stale. Positive candidate caps are only for explicit
  safety-ceiling experiments.

## Matcher Rule Changes

For matcher semantic changes, the durable regression source of truth is the
tracked fixture and rule inventory pair:

- `app/languages/sv/matcher_contracts/matcher_regression_cases.json`
- `app/languages/sv/matcher_contracts/matcher_rule_inventory.json`

A matcher rule is not done just because a local diagnostic, batch-review note,
or live-data check looks right. Promote accepted positive and relevant negative
cases into the main fixture, connect the rule/source in the inventory, and run
the matcher parity/inventory checks. Generated batch-question files and local
`test_*.py` workbench tests are staging/debugging surfaces, not the permanent
regression contract.

These JSON files are read-only contract inputs in production-style environments.
Runtime code does not update them. The only writer is the manual dev maintenance
script `tests/refresh_matcher_rule_inventory_line_refs.py --write`, which should
not be run against a read-only production filesystem.

## Matcher/Cache Full DB Diff

Use the full DB diff as an expensive live parity gate for matcher/cache changes,
not as a routine sanity check. Run it before larger matcher or cache-engine
releases, after broad matcher semantic changes, after a large scrape/offer
refresh when the active cache needs to be compared with a fresh full preview, or
when cache doctor/reconciliation indicates possible drift.

```bash
docker compose exec -T -w /app web python tests/run_matcher_full_db_diff.py --sample-limit 25
```

The script computes a fresh full preview with `persist=False`, compares it to
the active `recipe_offer_cache`, and prints samples for baseline-only,
candidate-only, and mismatched rows. It is read-only with respect to
`recipe_offer_cache`; a clean run has `parity_ok=true`, zero baseline-only rows,
zero candidate-only rows, zero mismatches, and an empty `field_diff_counts`.

The 2026-05-07 dev run compared `13279` active cache rows with `13279` fresh
preview rows and found no diffs. That run took about 7.5 minutes, which is why
this check should stay outside quick local sanity and normal support suites.

The old persistent shadow/apply workbench that used `recipe_offer_cache_shadow`
has been retired. The read-only full DB diff does not need that table.

## Matcher Fixture Files

The tracked matcher JSON contracts under `app/languages/sv/matcher_contracts/`
are part of the regression surface, not temporary batch-question output:

- `matcher_regression_cases.json` is the main matcher parity corpus.
- `matcher_rule_inventory.json` is the rule/source inventory checked by
  the inventory support scripts.

Do not keep generated review-import staging files in the production tree once
their pass-clean decisions have been promoted into the main fixture and
inventory. The active `app/tests/batch_review_questions.md` file is separate
from those generated staging files: keep it as the current review queue, but do
not treat it as a matcher regression gate until a decision has been promoted
into the main fixture and inventory.

Generated cache benchmark fixtures are local workbench data. Keep them out of
Git and do not treat them as part of the matcher regression surface.

## Local Workbench Tests

Files matching `app/tests/test_*.py` are intentionally ignored. Keep using them
for broader local regression work, pytest experiments, live-data investigations,
and one-off review fixtures. If a check becomes part of the app's public support
surface, move or copy the small deterministic part into a `run_*_checks.py`
script instead of publishing the whole workbench test.
