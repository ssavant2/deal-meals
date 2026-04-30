"""Small helpers for persisting cache-operation diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Mapping

from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

try:
    from database import get_db_session
except ModuleNotFoundError:
    from app.database import get_db_session


CACHE_NAME = "recipe_offer_matches"
MAX_TEXT_VALUE_LENGTH = 500
MAX_OPERATION_HISTORY = 50

_WARNED_LAST_OPERATION_WRITE_FAILED = False


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value)
    if len(text_value) > MAX_TEXT_VALUE_LENGTH:
        return text_value[:MAX_TEXT_VALUE_LENGTH] + "..."
    return text_value


def _derive_operation_mode(summary: Mapping[str, Any], operation_type: str | None) -> str:
    if operation_type:
        return operation_type
    run_kind = summary.get("run_kind")
    if run_kind:
        return str(run_kind)
    effective_mode = summary.get("effective_rebuild_mode")
    if effective_mode == "delta":
        return "delta"
    return "full_rebuild"


def build_cache_last_operation(
    summary: Mapping[str, Any] | None,
    *,
    operation_type: str | None = None,
    status: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Build a compact, stable cache-operation summary for cache_metadata."""
    summary = summary or {}
    op: dict[str, Any] = {
        "generated_at": _utcnow_iso(),
        "mode": _derive_operation_mode(summary, operation_type),
    }

    status_value = status or summary.get("status")
    if status_value is None:
        if summary.get("success") is False:
            status_value = "error" if summary.get("error") else "fallback"
        elif summary.get("applied") is False and summary.get("fallback_reason"):
            status_value = "fallback"
        else:
            status_value = "ready"
    op["status"] = _safe_text(status_value)

    text_fields = (
        "run_kind",
        "source",
        "fallback_reason",
        "trigger_reason",
        "error",
        "effective_rebuild_mode",
        "recipe_selection_mode",
        "recipe_delta_decision",
        "recipe_delta_reason",
        "verification_mode",
        "matcher_version",
        "recipe_compiler_version",
        "offer_compiler_version",
        "offer_data_source",
        "recipe_data_source",
        "candidate_data_source",
        "ingredient_routing_effective_mode",
        "ingredient_routing_fallback_reason",
    )
    for key in text_fields:
        value = source if key == "source" and source is not None else summary.get(key)
        safe_value = _safe_text(value)
        if safe_value is not None:
            op[key] = safe_value

    int_fields = (
        "time_ms",
        "cached",
        "total_matches",
        "total_recipes",
        "selected_recipe_count",
        "requested_recipe_count",
        "changed_recipe_count",
        "removed_recipe_count",
        "patch_recipe_count",
        "patch_preview_match_count",
        "full_preview_time_ms",
        "patch_preview_time_ms",
        "materialized_mismatched_count",
        "actual_changed_recipes",
        "affected_recipe_count",
        "active_recipe_count",
        "matched_offer_ids",
        "total_offers",
        "unmatched_offer_ids",
    )
    for key in int_fields:
        safe_value = _safe_int(summary.get(key))
        if safe_value is not None:
            op[key] = safe_value

    bool_fields = (
        "applied",
        "ready_to_apply",
        "verify_full_preview",
        "effective_verify_full_preview",
        "materialized_patch_matches_full_preview",
        "planner_covers_preview_diff",
        "probation_ready",
    )
    for key in bool_fields:
        safe_value = _safe_bool(summary.get(key))
        if safe_value is not None:
            op[key] = safe_value

    patch_result = summary.get("patch_result")
    if isinstance(patch_result, Mapping):
        for source_key, target_key in (
            ("total_matches", "total_matches"),
            ("inserted_count", "patch_inserted_count"),
            ("deleted_count", "patch_deleted_count"),
        ):
            safe_value = _safe_int(patch_result.get(source_key))
            if safe_value is not None:
                op[target_key] = safe_value

    for key in ("affected_ratio_pct", "delta_ratio_threshold_pct"):
        value = summary.get(key)
        if value is None:
            continue
        try:
            op[key] = round(float(value), 4)
        except (TypeError, ValueError):
            continue

    return op


def _normalize_operation_history(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    if not isinstance(value, list):
        return []
    return [
        dict(item)
        for item in value
        if isinstance(item, Mapping)
    ][-MAX_OPERATION_HISTORY:]


def _operation_is_fallback(operation: Mapping[str, Any]) -> bool:
    return (
        operation.get("status") == "fallback"
        or bool(operation.get("fallback_reason"))
    )


def _operation_is_error(operation: Mapping[str, Any]) -> bool:
    return operation.get("status") == "error" or bool(operation.get("error"))


def summarize_cache_operation_history(
    history: Any,
    *,
    recent_window: int = 10,
) -> dict[str, Any]:
    """Summarize rolling cache-operation history without exposing full payloads."""
    normalized = _normalize_operation_history(history)
    recent = normalized[-recent_window:]

    by_mode: dict[str, int] = {}
    fallback_reasons: dict[str, int] = {}
    fallback_count = 0
    error_count = 0
    consecutive_fallbacks = 0

    for operation in normalized:
        mode = str(operation.get("mode") or "unknown")
        by_mode[mode] = by_mode.get(mode, 0) + 1
        if _operation_is_fallback(operation):
            fallback_count += 1
            reason = str(operation.get("fallback_reason") or "fallback")
            fallback_reasons[reason] = fallback_reasons.get(reason, 0) + 1
        if _operation_is_error(operation):
            error_count += 1

    for operation in reversed(normalized):
        if not _operation_is_fallback(operation):
            break
        consecutive_fallbacks += 1

    recent_fallback_count = sum(1 for operation in recent if _operation_is_fallback(operation))
    recent_error_count = sum(1 for operation in recent if _operation_is_error(operation))
    history_count = len(normalized)

    fallback_rate_pct = (
        round((fallback_count / history_count) * 100, 1)
        if history_count
        else 0.0
    )
    recent_fallback_rate_pct = (
        round((recent_fallback_count / len(recent)) * 100, 1)
        if recent
        else 0.0
    )

    return {
        "history_size": history_count,
        "history_limit": MAX_OPERATION_HISTORY,
        "recent_window": len(recent),
        "fallback_count": fallback_count,
        "fallback_rate_pct": fallback_rate_pct,
        "recent_fallback_count": recent_fallback_count,
        "recent_fallback_rate_pct": recent_fallback_rate_pct,
        "error_count": error_count,
        "recent_error_count": recent_error_count,
        "consecutive_fallbacks": consecutive_fallbacks,
        "by_mode": dict(sorted(by_mode.items())),
        "fallback_reasons": dict(sorted(fallback_reasons.items())),
        "last_fallback_at": next(
            (
                str(operation.get("generated_at"))
                for operation in reversed(normalized)
                if _operation_is_fallback(operation)
            ),
            None,
        ),
        "last_error_at": next(
            (
                str(operation.get("generated_at"))
                for operation in reversed(normalized)
                if _operation_is_error(operation)
            ),
            None,
        ),
    }


def record_cache_last_operation(
    summary: Mapping[str, Any] | None,
    *,
    operation_type: str | None = None,
    status: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Best-effort persist of a compact cache-operation summary."""
    global _WARNED_LAST_OPERATION_WRITE_FAILED

    operation = build_cache_last_operation(
        summary,
        operation_type=operation_type,
        status=status,
        source=source,
    )
    try:
        with get_db_session() as db:
            row = db.execute(text("""
                SELECT operation_history
                FROM cache_metadata
                WHERE cache_name = :name
                FOR UPDATE
            """), {"name": CACHE_NAME}).fetchone()
            history = _normalize_operation_history(row.operation_history if row else None)
            history.append(operation)
            history = history[-MAX_OPERATION_HISTORY:]

            db.execute(text("""
                INSERT INTO cache_metadata (cache_name, last_operation, operation_history)
                VALUES (
                    :name,
                    CAST(:last_operation AS jsonb),
                    CAST(:operation_history AS jsonb)
                )
                ON CONFLICT (cache_name) DO UPDATE SET
                    last_operation = EXCLUDED.last_operation,
                    operation_history = EXCLUDED.operation_history
            """), {
                "name": CACHE_NAME,
                "last_operation": json.dumps(operation, ensure_ascii=False, sort_keys=True),
                "operation_history": json.dumps(history, ensure_ascii=False, sort_keys=True),
            })
            db.commit()
    except SQLAlchemyError as exc:
        if not _WARNED_LAST_OPERATION_WRITE_FAILED:
            logger.warning(f"Could not persist cache last_operation diagnostics: {exc}")
            _WARNED_LAST_OPERATION_WRITE_FAILED = True
    except Exception as exc:
        if not _WARNED_LAST_OPERATION_WRITE_FAILED:
            logger.warning(f"Could not persist cache last_operation diagnostics: {exc}")
            _WARNED_LAST_OPERATION_WRITE_FAILED = True

    return operation
