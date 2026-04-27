"""Runtime helpers for ingredient-routing probation history and gating."""

from __future__ import annotations

from datetime import datetime, timezone
import json
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


MAX_INGREDIENT_ROUTING_PROBATION_HISTORY_ENTRIES = 1000
INGREDIENT_ROUTING_MODES = frozenset({"off", "shadow", "probation", "hint_first"})


def normalize_ingredient_routing_mode(mode: str | None) -> str:
    """Return a supported ingredient-routing mode, defaulting safely to off."""
    normalized = (mode or "off").strip().lower()
    if normalized in INGREDIENT_ROUTING_MODES:
        return normalized
    return "off"


def get_configured_ingredient_routing_mode() -> str:
    """Return the configured runtime mode for ingredient routing."""
    return normalize_ingredient_routing_mode(settings.cache_ingredient_routing_mode)


def get_default_ingredient_routing_probation_history_path() -> Path:
    """Return the default JSONL path for ingredient-routing probation history."""
    configured = settings.cache_ingredient_routing_probation_history_file
    if configured:
        return Path(configured)
    if Path("/app").exists():
        return Path("/app/data/ingredient_routing_probation_history.jsonl")
    return Path(__file__).resolve().parents[1] / "data" / "ingredient_routing_probation_history.jsonl"


def load_ingredient_routing_probation_history(history_path: Path) -> list[dict[str, Any]]:
    """Load ingredient-routing probation entries from disk, ignoring bad lines."""
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


def _write_ingredient_routing_probation_history(
    history_path: Path,
    entries: list[dict[str, Any]],
) -> None:
    history_path.write_text(
        "".join(
            json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
            for entry in entries
        ),
        encoding="utf-8",
    )


def _trim_ingredient_routing_probation_history(history_path: Path) -> None:
    entries = load_ingredient_routing_probation_history(history_path)
    if len(entries) <= MAX_INGREDIENT_ROUTING_PROBATION_HISTORY_ENTRIES:
        return
    _write_ingredient_routing_probation_history(
        history_path,
        entries[-MAX_INGREDIENT_ROUTING_PROBATION_HISTORY_ENTRIES:],
    )


def _is_countable_ready_entry(entry: dict[str, Any]) -> bool:
    return (
        entry.get("ready_for_hint_first") is True
        and entry.get("probation_countable", True) is True
    )


def _is_neutral_ready_entry(entry: dict[str, Any]) -> bool:
    return (
        entry.get("ready_for_hint_first") is True
        and entry.get("probation_countable", True) is False
    )


def summarize_ingredient_routing_probation_history(
    entries: list[dict[str, Any]],
    *,
    matcher_version: str,
    recipe_compiler_version: str,
    offer_compiler_version: str,
) -> dict[str, Any]:
    """Build a readiness summary for the current matcher/compiler version tuple."""
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
    ready_entries = [entry for entry in entries if _is_countable_ready_entry(entry)]
    distinct_ready_version_tuples = {
        (
            entry.get("matcher_version"),
            entry.get("recipe_compiler_version"),
            entry.get("offer_compiler_version"),
        )
        for entry in ready_entries
    }

    last_ready_at = next(
        (
            entry.get("generated_at")
            for entry in reversed(entries)
            if entry.get("ready_for_hint_first") is True
        ),
        None,
    )
    last_failure_at = next(
        (
            entry.get("generated_at")
            for entry in reversed(entries)
            if entry.get("ready_for_hint_first") is not True
        ),
        None,
    )

    return {
        "entry_count": len(entries),
        "ready_run_count": len(ready_entries),
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
        "distinct_version_count": len(distinct_ready_version_tuples),
        "recent_runs": [
            {
                "generated_at": entry.get("generated_at"),
                "ready_for_hint_first": entry.get("ready_for_hint_first"),
                "probation_countable": entry.get("probation_countable", True),
                "matcher_version": entry.get("matcher_version"),
                "recipe_compiler_version": entry.get("recipe_compiler_version"),
                "offer_compiler_version": entry.get("offer_compiler_version"),
                "ingredient_routing_mode": entry.get("ingredient_routing_mode"),
                "shadow_candidate_change_count": entry.get("shadow_candidate_change_count"),
                "shadow_unexplained_miss_count": entry.get("shadow_unexplained_miss_count"),
            }
            for entry in entries[-5:]
        ],
    }


def _shadow_fallback_reason_counts(result: dict[str, Any]) -> dict[str, int]:
    counts = result.get("shadow_fallback_reason_counts", {})
    if not isinstance(counts, dict):
        return {}
    return {
        str(key): int(value)
        for key, value in counts.items()
        if isinstance(value, int)
    }


def build_ingredient_routing_probation_history_entry(
    result: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a compact append-only history row from one shadow/probation run."""
    fallback_reason_counts = _shadow_fallback_reason_counts(result)
    unexplained_count = int(result.get("shadow_unexplained_miss_count") or 0)
    ready = (
        result.get("ingredient_routing_shadow_measured") is True
        and unexplained_count == 0
    )
    return {
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "matcher_version": result.get("matcher_version", MATCHER_VERSION),
        "recipe_compiler_version": result.get("recipe_compiler_version", RECIPE_COMPILER_VERSION),
        "offer_compiler_version": result.get("offer_compiler_version", OFFER_COMPILER_VERSION),
        "ingredient_routing_mode": result.get("ingredient_routing_mode"),
        "ingredient_routing_effective_mode": result.get("ingredient_routing_effective_mode"),
        "ready_for_hint_first": ready,
        "probation_countable": result.get("ingredient_routing_effective_mode") == "probation",
        "shadow_pair_count": result.get("shadow_pair_count", 0),
        "shadow_candidate_change_count": result.get("shadow_candidate_change_count", 0),
        "shadow_unexplained_miss_count": unexplained_count,
        "shadow_fallback_reason_counts": fallback_reason_counts,
        "estimated_fullscan_ingredient_checks": result.get("estimated_fullscan_ingredient_checks", 0),
        "estimated_hinted_ingredient_checks": result.get("estimated_hinted_ingredient_checks", 0),
        "total_recipes": result.get("total_recipes"),
        "cached": result.get("cached"),
        "time_ms": result.get("time_ms"),
        "run_kind": result.get("run_kind"),
    }


def append_ingredient_routing_probation_history(
    result: dict[str, Any],
    *,
    history_path: Path | None = None,
) -> dict[str, Any]:
    """Append one ingredient-routing probation history entry."""
    resolved_path = history_path or get_default_ingredient_routing_probation_history_path()
    entry = build_ingredient_routing_probation_history_entry(result)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    with resolved_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True))
        handle.write("\n")
    _trim_ingredient_routing_probation_history(resolved_path)
    return entry


def get_ingredient_routing_probation_gate_status(
    *,
    history_path: Path | None = None,
    matcher_version: str = MATCHER_VERSION,
    recipe_compiler_version: str = RECIPE_COMPILER_VERSION,
    offer_compiler_version: str = OFFER_COMPILER_VERSION,
    min_ready_streak: int | None = None,
    min_version_ready_runs: int | None = None,
    recommended_distinct_versions: int | None = None,
) -> dict[str, Any]:
    """Return whether ingredient routing has enough clean probation to use hint-first."""
    resolved_path = history_path or get_default_ingredient_routing_probation_history_path()
    min_ready_streak = (
        settings.cache_ingredient_routing_probation_min_ready_streak
        if min_ready_streak is None
        else min_ready_streak
    )
    min_version_ready_runs = (
        settings.cache_ingredient_routing_probation_min_version_ready_runs
        if min_version_ready_runs is None
        else min_version_ready_runs
    )
    recommended_distinct_versions = (
        settings.cache_ingredient_routing_probation_recommended_distinct_versions
        if recommended_distinct_versions is None
        else recommended_distinct_versions
    )

    entries = load_ingredient_routing_probation_history(resolved_path)
    summary = summarize_ingredient_routing_probation_history(
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
    if latest_entry and int(latest_entry.get("shadow_unexplained_miss_count") or 0) > 0:
        reasons.append("latest_unexplained_mismatch")

    recommendations: list[str] = []
    if summary["distinct_version_count"] < recommended_distinct_versions:
        recommendations.append("fewer_than_recommended_distinct_versions")

    return {
        "ready": ready,
        "history_file": str(resolved_path),
        "history_exists": resolved_path.exists(),
        "latest_entry": latest_entry,
        "min_ready_streak": min_ready_streak,
        "min_version_ready_runs": min_version_ready_runs,
        "recommended_distinct_versions": recommended_distinct_versions,
        "reasons": reasons,
        "recommendations": recommendations,
        "summary": summary,
    }
