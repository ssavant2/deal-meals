# Cache Fallback Runbook

This runbook is for cases where recipe-delta or offer-delta often falls back to
a full rebuild, or where cache computation feels unexpectedly slow.

The goal is to quickly decide whether the fallback is expected, temporary, or a
sign that cache/IR/index state needs cleanup or a rebuild.

## Quick Triage

1. Look for the short summary lines first:

   ```bash
   docker compose logs --since=30m web \
     | rg "CACHE_RECIPE_DELTA|CACHE_REBUILD|cache decision|fallback|ERROR|WARNING"
   ```

2. Run cache doctor:

   ```bash
   curl -ks https://localhost:${APP_PORT:-20080}/api/cache/doctor | jq
   ```

   In dev the port may be `20070` instead:

   ```bash
   curl -ks https://localhost:20070/api/cache/doctor | jq
   ```

3. Check three things in the doctor response:

   - `status`: should preferably be `ok`.
   - `metadata.last_operation`: the latest cache operation.
   - `cache_metadata:operation_history`: fallback rate, recent fallbacks, and
     `delta_ratio_threshold_pct`.

4. If `cache_metadata:consecutive_fallbacks` warns, start with
   `fallback_reasons`. Three fallbacks in a row is not automatically a disaster,
   but it is a signal to look closer.

## When It Is Not A Problem

These cases are normal:

- `recipe_delta_decision=full` with `recipe_delta_reason=ratio_above_threshold`
  means too many recipes were affected compared with the active recipe base.
  The system intentionally chose a full rebuild.
- The first run after a larger deploy, compiler/matcher version change, or empty
  cache may need a full rebuild.
- A single `cache_operation_in_progress` usually only means another cache
  operation already holds the lock.
- During probation, total time may be higher because full-preview verifies that
  delta and full rebuild would produce the same result.

## Common Recipe-Delta Reasons

| Reason | Meaning | Practical action |
| --- | --- | --- |
| `ratio_above_threshold` | The change is larger than the delta threshold. | Normal. Let the full rebuild finish. |
| `delta_ids_missing` | The scrape changed recipes but did not return ID lists for delta. | Inspect the scraper save result. Run support checks if this appears after a code change. |
| `recipe_delta_disabled` | `CACHE_RECIPE_DELTA_ENABLED` is off. | Enable it again unless this was intentional. |
| `cache_not_ready` | Cache metadata was not `ready` when delta was about to start. | Wait for the active job. If status is stuck, run doctor and then a manual full rebuild. |
| `active_cache_empty` | The active cache is empty even though offers exist. | Run a full rebuild. If it becomes empty again, inspect offers, filters, and sources. |
| `cache_operation_in_progress` | Another cache operation held the lock. | Wait. If frequent, inspect scheduled jobs and run-all timing. |
| `recipe_ir_refresh_failed` | Incremental recipe-IR refresh failed. | Run doctor. Suspect corrupt recipe data, stale schema, or migration issues. |
| `recipe_term_index_refresh_failed` | Incremental term-index refresh failed. | Run doctor. If the term index is broken, run a full rebuild after fixing the cause. |
| `recipe_delta_full_preview_failed` | Full-preview could not be computed. | Read nearby ERROR/WARNING logs. Full rebuild is the correct fallback. |
| `recipe_delta_patch_preview_failed` | Patch-preview for changed recipes could not be computed. | Inspect recipe IDs, compiled recipe payload, and term index. |
| `recipe_delta_scope_missed_preview_diff` | Full-preview changed recipes that were not in the delta list. | The delta list is incomplete. Run a full rebuild and inspect ID capture in scraper/UI flows. |
| `materialized_patch_mismatch` | The materialized patch result does not match full-preview. | Run a full rebuild. If repeated, suspect a planner, term-index, or scope bug. |
| `recipe_cache_patch_failed` | The DELETE/INSERT patch against `recipe_offer_cache` failed. | Run doctor. Inspect DB errors in logs. Full rebuild restores the baseline. |
| `recipe_delta_exception` / `recipe_delta_unexpected_error` | Unexpected exception in the delta chain. | Read the traceback, run doctor, and run a full rebuild after fixing the issue. |

## Common Offer-Delta Reasons

| Reason | Meaning | Practical action |
| --- | --- | --- |
| `recipe_changes_detected` | Offer-delta refuses to run when recipe-IR does not match recipes. | Run recipe/full rebuild first. This prevents offer-delta from using the wrong recipe baseline. |
| `planner_missed_preview_diff` | The offer-delta planner did not cover the full-preview diff. | Let fallback/full rebuild run. Repeated failures need planner analysis. |
| `materialized_patch_mismatch` | The materialized offer-delta does not match full-preview. | Run a full rebuild. Repeated failures indicate a delta planning or materialization bug. |
| `ingredient_routing_fullscan_baseline_mismatch` | Hint routing and fullscan baseline produced different results during verification. | Keep fallback. Inspect ingredient-routing probation before trusting hint-first. |
| `delta_exception:*` | Offer-delta threw an exception. | Read logs around the error and let fallback/full rebuild establish a new baseline. |

## Practical Playbooks

### Single Fallback

1. Let the job finish.
2. Run `GET /api/cache/doctor`.
3. If doctor is `ok` and the next run uses delta again, no action is needed.

### Several Fallbacks In A Row

1. Run doctor and note `fallback_reasons`.
2. Run a manual full rebuild to establish a clean baseline.
3. Run a small incremental recipe scrape.
4. If the same fallback returns immediately, it is likely code/data related,
   not just a stale baseline.

### Cache Stuck In `computing`

1. Check whether a cache job is still running:

   ```bash
   docker compose logs --since=15m web | rg "Starting cache operation|Cache computed|CACHE_"
   ```

2. If no job is running but doctor still shows `computing`, run a manual full
   rebuild.
3. If it returns, look for an exception between "status computing" and
   fallback/full rebuild in the logs.

### Full Rebuild Is Slow

Look at the `CACHE_REBUILD` line:

```text
CACHE_REBUILD run=full status=ready mode=compiled cached=... time=... compile=... route=... score=... write=...
```

- High `compile`: compiled IR or term-index build/load is slow.
- High `route`: candidate routing or term-index scope is expensive.
- High `score`: matching itself dominates.
- High `write`: DB/COPY or disk is the bottleneck.

If you need `CACHE_REBUILD_SUMMARY`, use `jq` or filter only the fields you
need. It is intentionally detailed but hard to read as a normal log line.

## Useful Commands

Primary log without old lines:

```bash
docker compose logs -f --tail=0 web
```

Recent cache events:

```bash
docker compose logs --since=1h web \
  | rg "CACHE_RECIPE_DELTA|CACHE_REBUILD|CACHE_REBUILD_SUMMARY|CACHE_RECIPE_DELTA_SUMMARY"
```

Warnings and errors:

```bash
docker compose logs --since=1h web | rg "WARNING|ERROR|CRITICAL|fallback"
```

Access log if you need HTTP noise separately:

```bash
docker compose exec web tail -f /app/logs/access.log
```

Support checks in dev:

```bash
docker compose exec -T -w /app web python tests/run_app_support_checks.py
```

## Safe Fallback

If you are unsure and cache state looks inconsistent:

1. Run doctor.
2. Run a full rebuild.
3. Run doctor again.
4. Run a small incremental scrape and verify that delta either applies or falls
   back with an understandable reason.

Full rebuild is slower, but it is the safe baseline path.
