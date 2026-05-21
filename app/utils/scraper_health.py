"""Compact scraper health and quality-gate readiness helpers."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
import os
from typing import Any, Mapping

from loguru import logger
from sqlalchemy import bindparam, text

from database import get_db_session


QUALITY_GATE_DEFAULT_ENV = "SCRAPER_QUALITY_GATES"
QUALITY_GATE_OVERRIDES_ENV = "SCRAPER_QUALITY_GATE_OVERRIDES"
HISTORY_READY_SUCCESS_COUNT = 5
HISTORY_READY_STABLE_COUNT = 3
HISTORY_STABILITY_TOLERANCE = 0.10
HISTORY_RECENT_LIMIT = 30
DISCOVERY_HISTORY_THRESHOLD = 0.70
EXPECTED_MIN_CANARY_RATIO = 0.50
QUALITY_GATE_MODES = {"auto", "off", "observe", "enforce"}
SUCCESS_STATUSES = {"success", "success_empty", "no_new_recipes"}


@dataclass(frozen=True)
class ScraperHealthRow:
    scraper_id: str
    mode: str | None = None
    success: bool | None = None
    status: str | None = None
    reason_code: str | None = None
    candidate_count: int | None = None
    selected_count: int | None = None
    parsed_count: int | None = None
    filtered_count: int | None = None
    parse_rate: float | None = None
    data_path: str | None = None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def _row_succeeded(row: ScraperHealthRow) -> bool:
    if row.status:
        return row.status in SUCCESS_STATUSES
    return row.success is True


def _quality_mode_from_value(value: str | None) -> str | None:
    mode = (value or "").strip().lower()
    return mode if mode in QUALITY_GATE_MODES else None


def _parse_quality_gate_overrides(raw: str | None) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for part in (raw or "").split(","):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        mode = _quality_mode_from_value(value)
        key = key.strip().lower()
        if key and mode:
            overrides[key] = mode
    return overrides


def configured_quality_gate_mode(
    source_id: str,
    *,
    source_kind: str = "recipe",
    env: Mapping[str, str] | None = None,
) -> str:
    """Return the configured gate mode for a source.

    Environment:
    - SCRAPER_QUALITY_GATES=auto|off|observe|enforce
    - SCRAPER_QUALITY_GATE_OVERRIDES=mathem=off,recipe:arla=enforce,*=observe
    """
    env = env or os.environ
    default_mode = _quality_mode_from_value(env.get(QUALITY_GATE_DEFAULT_ENV)) or "auto"
    overrides = _parse_quality_gate_overrides(env.get(QUALITY_GATE_OVERRIDES_ENV))
    source_key = (source_id or "").strip().lower()
    kind_key = (source_kind or "").strip().lower()
    return (
        overrides.get(f"{kind_key}:{source_key}")
        or overrides.get(source_key)
        or overrides.get("*")
        or default_mode
    )


def _candidate_counts(rows: list[ScraperHealthRow]) -> list[int]:
    return [
        int(row.candidate_count)
        for row in rows
        if _row_succeeded(row) and row.candidate_count is not None
    ]


def _counts_are_stable(counts: list[int]) -> bool:
    if len(counts) < HISTORY_READY_STABLE_COUNT:
        return False
    recent = counts[:HISTORY_READY_STABLE_COUNT]
    baseline = median(recent)
    if baseline <= 0:
        return all(count == 0 for count in recent)
    return (max(recent) - min(recent)) <= baseline * HISTORY_STABILITY_TOLERANCE


def summarize_scraper_health(
    source_id: str,
    rows: list[ScraperHealthRow],
    *,
    source_kind: str = "recipe",
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Summarize recent run history into a small UI/API-safe status object."""
    configured_mode = configured_quality_gate_mode(source_id, source_kind=source_kind, env=env)

    if not rows:
        effective_mode = "observe" if configured_mode == "auto" else configured_mode
        return {
            "status": "no_history",
            "label_key": "recipes.health_no_history",
            "message_params": {},
            "history_ready": False,
            "ready_for_enforcing": False,
            "configured_gate_mode": configured_mode,
            "effective_gate_mode": effective_mode,
            "successful_metric_runs": 0,
        }

    latest = rows[0]
    counts = _candidate_counts(rows)
    history_ready = (
        len(counts) >= HISTORY_READY_SUCCESS_COUNT
        or _counts_are_stable(counts)
    )
    ready_for_enforcing = history_ready
    effective_mode = (
        "enforce"
        if configured_mode == "auto" and ready_for_enforcing
        else "observe"
        if configured_mode == "auto"
        else configured_mode
    )

    status = "ready" if ready_for_enforcing else "burn_in"
    label_key = "recipes.health_ready" if ready_for_enforcing else "recipes.health_burn_in"
    if not _row_succeeded(latest):
        status = "latest_failed"
        label_key = "recipes.health_latest_failed"

    recent_count = latest.candidate_count
    parse_rate = latest.parse_rate
    return {
        "status": status,
        "label_key": label_key,
        "message_params": {
            "count": min(len(counts), HISTORY_READY_SUCCESS_COUNT),
            "needed": HISTORY_READY_SUCCESS_COUNT,
        },
        "history_ready": history_ready,
        "ready_for_enforcing": ready_for_enforcing,
        "configured_gate_mode": configured_mode,
        "effective_gate_mode": effective_mode,
        "successful_metric_runs": len(counts),
        "latest_status": latest.status or ("success" if latest.success else "failed"),
        "latest_reason_code": latest.reason_code,
        "latest_candidate_count": recent_count,
        "latest_parse_rate": parse_rate,
        "latest_data_path": latest.data_path,
    }


def evaluate_recipe_quality_gate(
    source_id: str,
    current: ScraperHealthRow,
    history_rows: list[ScraperHealthRow],
    *,
    expected_min_urls: int | None = None,
    expected_min_parse_rate: float | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Evaluate a recipe scraper result against canary and history thresholds."""
    health = summarize_scraper_health(source_id, history_rows, source_kind="recipe", env=env)
    configured_mode = health["configured_gate_mode"]
    effective_mode = health["effective_gate_mode"]

    decision: dict[str, Any] = {
        "configured_mode": configured_mode,
        "effective_mode": effective_mode,
        "history_ready": health["history_ready"],
        "ready_for_enforcing": health["ready_for_enforcing"],
        "would_block": False,
        "should_block": False,
        "reason_code": None,
    }

    candidate_count = current.candidate_count
    if candidate_count is not None and expected_min_urls:
        canary_floor = int(max(1, expected_min_urls) * EXPECTED_MIN_CANARY_RATIO)
        decision["expected_min_urls"] = expected_min_urls
        decision["expected_min_canary_floor"] = canary_floor
        if candidate_count < canary_floor:
            decision.update({
                "would_block": True,
                "reason_code": "recipe_discovery_expected_min_canary",
                "candidate_count": candidate_count,
            })

    counts = _candidate_counts(history_rows)
    if not decision["would_block"] and candidate_count is not None and health["history_ready"] and counts:
        baseline = median(counts)
        threshold = baseline * DISCOVERY_HISTORY_THRESHOLD
        decision["candidate_count"] = candidate_count
        decision["candidate_count_median"] = baseline
        decision["candidate_count_threshold"] = threshold
        if candidate_count < threshold:
            decision.update({
                "would_block": True,
                "reason_code": "recipe_discovery_count_too_low",
            })

    if (
        not decision["would_block"]
        and expected_min_parse_rate is not None
        and current.parse_rate is not None
        and current.parse_rate < expected_min_parse_rate
    ):
        decision.update({
            "would_block": True,
            "reason_code": "recipe_parse_rate_too_low",
            "parse_rate": current.parse_rate,
            "expected_min_parse_rate": expected_min_parse_rate,
        })

    decision["should_block"] = bool(decision["would_block"] and effective_mode == "enforce")
    return decision


def _health_row_from_result(source_id: str, scrape_result) -> ScraperHealthRow:
    diagnostics = dict(getattr(scrape_result, "diagnostics", None) or {})
    return ScraperHealthRow(
        scraper_id=source_id,
        status=getattr(scrape_result, "status", None),
        reason_code=getattr(scrape_result, "reason", None),
        candidate_count=_coerce_int(_first_present(
            diagnostics,
            "candidate_count",
            "candidate_url_count",
            "candidate_urls",
        )),
        selected_count=_coerce_int(_first_present(
            diagnostics,
            "selected_count",
            "selected_url_count",
            "selected_urls",
        )),
        parsed_count=_coerce_int(_first_present(
            diagnostics,
            "parsed_count",
            "parsed_recipe_count",
            "parsed_recipes",
        )),
        filtered_count=_coerce_int(_first_present(
            diagnostics,
            "filtered_count",
            "filtered_non_recipe_count",
            "filtered_urls",
        )),
        parse_rate=_coerce_float(diagnostics.get("parse_rate")),
        data_path=_first_present(
            diagnostics,
            "data_path",
            "parser_method",
            "discovery_method",
        ),
    )


def annotate_recipe_quality_gate_decision(
    source_id: str,
    scrape_result,
    *,
    expected_min_urls: int | None = None,
    expected_min_parse_rate: float | None = None,
) -> dict[str, Any]:
    """Attach the current observe/enforce decision to scrape_result.diagnostics."""
    current = _health_row_from_result(source_id, scrape_result)
    history_rows = _fetch_recipe_health_rows([source_id]).get(source_id, [])
    decision = evaluate_recipe_quality_gate(
        source_id,
        current,
        history_rows,
        expected_min_urls=expected_min_urls,
        expected_min_parse_rate=expected_min_parse_rate,
    )
    diagnostics = dict(getattr(scrape_result, "diagnostics", None) or {})
    diagnostics["quality_gate"] = decision
    scrape_result.diagnostics = diagnostics
    return decision


def _row_from_db(row) -> ScraperHealthRow:
    return ScraperHealthRow(
        scraper_id=str(row.scraper_id),
        mode=row.mode,
        success=row.success,
        status=row.status,
        reason_code=row.reason_code,
        candidate_count=_coerce_int(row.candidate_count),
        selected_count=_coerce_int(row.selected_count),
        parsed_count=_coerce_int(row.parsed_count),
        filtered_count=_coerce_int(row.filtered_count),
        parse_rate=_coerce_float(row.parse_rate),
        data_path=row.data_path,
    )


def _fetch_recipe_health_rows(scraper_ids: list[str]) -> dict[str, list[ScraperHealthRow]]:
    clean_ids = sorted({str(scraper_id) for scraper_id in scraper_ids if scraper_id})
    if not clean_ids:
        return {}

    grouped: dict[str, list[ScraperHealthRow]] = {scraper_id: [] for scraper_id in clean_ids}
    try:
        with get_db_session() as db:
            statement = text("""
                SELECT *
                FROM (
                    SELECT
                        scraper_id,
                        mode,
                        run_at,
                        id,
                        success,
                        status,
                        reason_code,
                        candidate_count,
                        selected_count,
                        parsed_count,
                        filtered_count,
                        parse_rate,
                        data_path,
                        ROW_NUMBER() OVER (
                            PARTITION BY scraper_id
                            ORDER BY run_at DESC, id DESC
                        ) AS rn
                    FROM scraper_run_history
                    WHERE scraper_id IN :scraper_ids
                      AND (source_kind = 'recipe' OR source_kind IS NULL)
                ) recent
                WHERE rn <= :limit
                ORDER BY scraper_id, run_at DESC, id DESC
            """).bindparams(bindparam("scraper_ids", expanding=True))
            rows = db.execute(
                statement,
                {"scraper_ids": clean_ids, "limit": HISTORY_RECENT_LIMIT},
            ).fetchall()
    except Exception as exc:
        logger.debug(f"Could not fetch recipe scraper health: {exc}")
        return grouped

    for row in rows:
        health_row = _row_from_db(row)
        grouped.setdefault(health_row.scraper_id, []).append(health_row)
    return grouped


def get_recipe_scraper_health(scraper_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch and summarize recent recipe scraper health for a set of IDs."""
    grouped = _fetch_recipe_health_rows(scraper_ids)
    return {
        scraper_id: summarize_scraper_health(scraper_id, grouped.get(scraper_id, []), source_kind="recipe")
        for scraper_id in grouped
    }
