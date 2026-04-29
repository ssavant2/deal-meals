"""Runtime helpers for reading and evaluating delta probation history."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from config import settings
except ModuleNotFoundError:
    from app.config import settings

try:
    from languages.matcher_runtime import (
        MATCHER_VERSION,
        OFFER_COMPILER_VERSION,
        RECIPE_COMPILER_VERSION,
    )
except ModuleNotFoundError:
    from app.languages.matcher_runtime import (
        MATCHER_VERSION,
        OFFER_COMPILER_VERSION,
        RECIPE_COMPILER_VERSION,
    )

MAX_PROBATION_HISTORY_ENTRIES = 1000


def get_default_probation_history_path() -> Path:
    """Return the default probation history JSONL path."""
    configured = settings.cache_delta_probation_history_file
    if configured:
        return Path(configured)
    if Path("/app").exists():
        return Path("/app/data/delta_probation_history.jsonl")
    return Path(__file__).resolve().parents[1] / "data" / "delta_probation_history.jsonl"


def load_probation_history(history_path: Path) -> list[dict[str, Any]]:
    """Load probation history entries from disk, ignoring broken lines."""
    if not history_path.exists():
        return []

    entries: list[dict[str, Any]] = []
    with history_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                entries.append(parsed)
    return entries


def _write_probation_history(history_path: Path, entries: list[dict[str, Any]]) -> None:
    """Rewrite the probation history file with the provided entries."""
    history_path.write_text(
        "".join(
            json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
            for entry in entries
        ),
        encoding="utf-8",
    )


def _trim_probation_history(history_path: Path) -> None:
    """Keep only the most recent probation history entries on disk."""
    entries = load_probation_history(history_path)
    if len(entries) <= MAX_PROBATION_HISTORY_ENTRIES:
        return
    _write_probation_history(history_path, entries[-MAX_PROBATION_HISTORY_ENTRIES:])


def _is_countable_ready_entry(entry: dict[str, Any]) -> bool:
    """Return whether an entry should count toward probation readiness."""
    return (
        entry.get("ready_for_manual_live_apply") is True
        and entry.get("probation_countable", True) is True
    )


def _is_neutral_ready_entry(entry: dict[str, Any]) -> bool:
    """Return whether an entry is green but should not change the readiness streak."""
    return (
        entry.get("ready_for_manual_live_apply") is True
        and entry.get("probation_countable", True) is False
    )


def summarize_probation_history(
    entries: list[dict[str, Any]],
    *,
    matcher_version: str,
    recipe_compiler_version: str,
    offer_compiler_version: str,
) -> dict[str, Any]:
    """Build a small summary focused on the current version triple."""
    current_ready_streak = 0
    for entry in reversed(entries):
        if _is_neutral_ready_entry(entry):
            continue
        if _is_countable_ready_entry(entry):
            current_ready_streak += 1
            continue
        break

    current_version_entries = [
        entry for entry in entries
        if entry.get("matcher_version") == matcher_version
        and entry.get("recipe_compiler_version") == recipe_compiler_version
        and entry.get("offer_compiler_version") == offer_compiler_version
    ]

    last_ready_at = next(
        (
            entry.get("generated_at")
            for entry in reversed(entries)
            if entry.get("ready_for_manual_live_apply") is True
        ),
        None,
    )
    last_failure_at = next(
        (
            entry.get("generated_at")
            for entry in reversed(entries)
            if entry.get("ready_for_manual_live_apply") is not True
        ),
        None,
    )

    return {
        "entry_count": len(entries),
        "ready_run_count": sum(1 for entry in entries if _is_countable_ready_entry(entry)),
        "current_ready_streak": current_ready_streak,
        "last_ready_at": last_ready_at,
        "last_failure_at": last_failure_at,
        "current_version_run_count": len(current_version_entries),
        "current_version_ready_run_count": sum(
            1 for entry in current_version_entries if _is_countable_ready_entry(entry)
        ),
        "current_version_last_run_at": (
            current_version_entries[-1].get("generated_at") if current_version_entries else None
        ),
        "recent_runs": [
            {
                "generated_at": entry.get("generated_at"),
                "ready_for_manual_live_apply": entry.get("ready_for_manual_live_apply"),
                "probation_countable": entry.get("probation_countable", True),
                "matcher_version": entry.get("matcher_version"),
                "recipe_compiler_version": entry.get("recipe_compiler_version"),
                "offer_compiler_version": entry.get("offer_compiler_version"),
                "live_baseline_drift": entry.get("live_baseline_drift"),
                "effective_rebuild_mode": entry.get("effective_rebuild_mode"),
                "verification_mode": entry.get("verification_mode"),
                "ingredient_routing_mode": entry.get("ingredient_routing_mode"),
                "ingredient_routing_effective_mode": entry.get("ingredient_routing_effective_mode"),
                "ingredient_routing_fullscan_baseline_checked": (
                    entry.get("ingredient_routing_fullscan_baseline_checked")
                ),
            }
            for entry in entries[-5:]
        ],
    }


def build_runtime_probation_history_entry(
    result: dict[str, Any],
    *,
    store_name: str | None = None,
    trigger: str = "offer_refresh",
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build an app-runtime probation history row from a real delta attempt."""
    effective_verify_full_preview = result.get("effective_verify_full_preview")
    verification_mode = result.get("verification_mode")
    ready = result.get("ready_to_apply") is True or result.get("applied") is True
    probation_countable = (
        ready
        and effective_verify_full_preview is True
        and result.get("materialized_patch_matches_full_preview") is True
    )
    fallback_reason = result.get("fallback_reason")
    if not ready and not fallback_reason:
        fallback_reason = "delta_not_ready"

    return {
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "matcher_version": result.get("matcher_version", MATCHER_VERSION),
        "recipe_compiler_version": result.get("recipe_compiler_version", RECIPE_COMPILER_VERSION),
        "offer_compiler_version": result.get("offer_compiler_version", OFFER_COMPILER_VERSION),
        "ready_for_manual_live_apply": ready,
        "probation_countable": probation_countable,
        "live_baseline_drift": (
            0 if probation_countable else None
        ),
        "effective_rebuild_mode": result.get("effective_rebuild_mode"),
        "verification_mode": verification_mode,
        "verify_full_preview": result.get("verify_full_preview"),
        "effective_verify_full_preview": effective_verify_full_preview,
        "term_index_skip_fts_prefilter": result.get("term_index_skip_fts_prefilter"),
        "fallback_reason": fallback_reason,
        "patch_recipe_count": result.get("patch_recipe_count"),
        "actual_changed_recipes": result.get("actual_changed_recipes"),
        "planner_covers_preview_diff": result.get("planner_covers_preview_diff"),
        "materialized_patch_matches_full_preview": result.get("materialized_patch_matches_full_preview"),
        "ingredient_routing_mode": result.get("ingredient_routing_mode"),
        "ingredient_routing_effective_mode": result.get("ingredient_routing_effective_mode"),
        "ingredient_routing_fallback_reason": result.get("ingredient_routing_fallback_reason"),
        "ingredient_routing_fullscan_baseline_checked": (
            result.get("ingredient_routing_fullscan_baseline_checked")
        ),
        "ingredient_routing_fullscan_baseline_matches": (
            result.get("ingredient_routing_fullscan_baseline_matches")
        ),
        "ingredient_routing_fullscan_baseline_mismatched_count": (
            result.get("ingredient_routing_fullscan_baseline_mismatched_count")
        ),
        "cached": result.get("cached"),
        "total_recipes": result.get("total_recipes"),
        "time_ms": result.get("time_ms"),
        "store_name": store_name,
        "trigger": trigger,
    }


def append_runtime_probation_history(
    result: dict[str, Any],
    *,
    history_path: Path | None = None,
    store_name: str | None = None,
    trigger: str = "offer_refresh",
) -> dict[str, Any]:
    """Append a runtime delta attempt to the shared probation history log."""
    resolved_path = history_path or get_default_probation_history_path()
    entry = build_runtime_probation_history_entry(
        result,
        store_name=store_name,
        trigger=trigger,
    )
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    with resolved_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True))
        handle.write("\n")
    _trim_probation_history(resolved_path)
    return entry


def get_delta_probation_gate_status(
    *,
    history_path: Path | None = None,
    matcher_version: str = MATCHER_VERSION,
    recipe_compiler_version: str = RECIPE_COMPILER_VERSION,
    offer_compiler_version: str = OFFER_COMPILER_VERSION,
    min_ready_streak: int | None = None,
    min_version_ready_runs: int | None = None,
) -> dict[str, Any]:
    """Return whether runtime delta may skip full preview based on probation history."""
    resolved_path = history_path or get_default_probation_history_path()
    min_ready_streak = (
        settings.cache_delta_probation_min_ready_streak
        if min_ready_streak is None
        else min_ready_streak
    )
    min_version_ready_runs = (
        settings.cache_delta_probation_min_version_ready_runs
        if min_version_ready_runs is None
        else min_version_ready_runs
    )

    entries = load_probation_history(resolved_path)
    summary = summarize_probation_history(
        entries,
        matcher_version=matcher_version,
        recipe_compiler_version=recipe_compiler_version,
        offer_compiler_version=offer_compiler_version,
    )

    latest_entry = entries[-1] if entries else None

    ready = (
        summary["current_ready_streak"] >= min_ready_streak
        and summary["current_version_ready_run_count"] >= min_version_ready_runs
    )

    reasons: list[str] = []
    if not resolved_path.exists():
        reasons.append("history_missing")
    if summary["current_ready_streak"] < min_ready_streak:
        reasons.append("insufficient_ready_streak")
    if summary["current_version_ready_run_count"] < min_version_ready_runs:
        reasons.append("insufficient_current_version_ready_runs")

    return {
        "ready": ready,
        "history_file": str(resolved_path),
        "history_exists": resolved_path.exists(),
        "latest_entry": latest_entry,
        "min_ready_streak": min_ready_streak,
        "min_version_ready_runs": min_version_ready_runs,
        "reasons": reasons,
        "summary": summary,
    }
