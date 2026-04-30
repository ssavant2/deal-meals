"""Read-only diagnostics for cache and compiled matcher tables."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

try:
    from database import get_db_session
except ModuleNotFoundError:
    from app.database import get_db_session

try:
    from cache_operation_metadata import summarize_cache_operation_history
except ModuleNotFoundError:
    from app.cache_operation_metadata import summarize_cache_operation_history

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


CACHE_NAME = "recipe_offer_matches"
_SEVERITY_ORDER = {"ok": 0, "warning": 1, "error": 2}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check(name: str, status: str, message: str, **details: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "status": status,
        "message": message,
    }
    if details:
        payload["details"] = details
    return payload


def _overall_status(checks: list[dict[str, Any]]) -> str:
    if not checks:
        return "warning"
    return max(
        (str(check.get("status", "warning")) for check in checks),
        key=lambda value: _SEVERITY_ORDER.get(value, 1),
    )


def _summary(checks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "checks": len(checks),
        "ok": sum(1 for check in checks if check.get("status") == "ok"),
        "warning": sum(1 for check in checks if check.get("status") == "warning"),
        "error": sum(1 for check in checks if check.get("status") == "error"),
    }


def _scalar(db, sql: str, params: dict[str, Any] | None = None) -> Any:
    return db.execute(text(sql), params or {}).scalar()


def _row(db, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    result = db.execute(text(sql), params or {}).mappings().fetchone()
    return dict(result) if result else None


def _table_exists(db, table_name: str) -> bool:
    return bool(_scalar(db, """
        SELECT to_regclass(:table_name)
    """, {"table_name": f"public.{table_name}"}))


def _column_exists(db, table_name: str, column_name: str) -> bool:
    return bool(_scalar(db, """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :table_name
          AND column_name = :column_name
    """, {"table_name": table_name, "column_name": column_name}))


def _count_check(
    checks: list[dict[str, Any]],
    db,
    *,
    name: str,
    sql: str,
    ok_message: str,
    bad_message: str,
    bad_status: str = "warning",
    params: dict[str, Any] | None = None,
    expected: int = 0,
) -> int | None:
    try:
        count = int(_scalar(db, sql, params) or 0)
    except SQLAlchemyError as exc:
        checks.append(_check(name, "error", f"Check failed: {exc}"))
        return None

    if count == expected:
        checks.append(_check(name, "ok", ok_message, count=count))
    else:
        checks.append(_check(name, bad_status, bad_message, count=count, expected=expected))
    return count


def run_cache_doctor() -> dict[str, Any]:
    """Run read-only cache consistency diagnostics."""
    checks: list[dict[str, Any]] = []
    metadata: dict[str, Any] | None = None
    operation_history_summary: dict[str, Any] | None = None

    try:
        with get_db_session() as db:
            required_tables = (
                "cache_metadata",
                "recipe_offer_cache",
                "found_recipes",
                "offers",
                "compiled_offer_match_data",
                "compiled_recipe_match_data",
                "compiled_offer_term_index",
                "compiled_recipe_term_index",
            )
            table_status = {table: _table_exists(db, table) for table in required_tables}
            for table, exists in table_status.items():
                checks.append(_check(
                    f"table:{table}",
                    "ok" if exists else "error",
                    f"{table} exists" if exists else f"{table} is missing",
                ))

            if not all(table_status.values()):
                status = _overall_status(checks)
                return {
                    "success": status != "error",
                    "status": status,
                    "checked_at": _utcnow_iso(),
                    "versions": _versions(),
                    "metadata": metadata,
                    "summary": _summary(checks),
                    "checks": checks,
                }

            has_last_operation = _column_exists(db, "cache_metadata", "last_operation")
            has_operation_history = _column_exists(db, "cache_metadata", "operation_history")
            metadata_select = """
                SELECT
                    cache_name,
                    status,
                    total_matches,
                    total_recipes,
                    computation_time_ms,
                    last_computed_at,
                    error_message,
                    last_background_rebuild_at,
                    background_rebuild_source
                    __LAST_OPERATION_SELECT__
                    __OPERATION_HISTORY_SELECT__
                FROM cache_metadata
                WHERE cache_name = :cache_name
            """
            metadata_select = metadata_select.replace(
                "__LAST_OPERATION_SELECT__",
                ", last_operation" if has_last_operation else "",
            ).replace(
                "__OPERATION_HISTORY_SELECT__",
                ", operation_history" if has_operation_history else "",
            )
            metadata = _row(db, metadata_select, {"cache_name": CACHE_NAME})

            if not metadata:
                checks.append(_check(
                    "cache_metadata:row",
                    "error",
                    "cache_metadata row for recipe_offer_matches is missing",
                ))
            else:
                metadata = _json_ready(metadata)
                operation_history = metadata.pop("operation_history", []) if has_operation_history else []
                operation_history_summary = summarize_cache_operation_history(operation_history)
                status_value = metadata.get("status")
                if status_value == "ready":
                    checks.append(_check("cache_metadata:status", "ok", "Cache metadata status is ready"))
                elif status_value == "computing":
                    checks.append(_check("cache_metadata:status", "warning", "Cache metadata status is computing"))
                else:
                    checks.append(_check(
                        "cache_metadata:status",
                        "error",
                        "Cache metadata status is not ready",
                        metadata_status=status_value,
                        error_message=metadata.get("error_message"),
                    ))

                if has_last_operation:
                    checks.append(_check(
                        "cache_metadata:last_operation",
                        "ok" if metadata.get("last_operation") else "warning",
                        "last_operation is present" if metadata.get("last_operation") else "last_operation is empty",
                    ))
                else:
                    checks.append(_check(
                        "cache_metadata:last_operation",
                        "warning",
                        "cache_metadata.last_operation column is missing",
                    ))
                if has_operation_history:
                    checks.append(_check(
                        "cache_metadata:operation_history",
                        "ok" if operation_history_summary["history_size"] > 0 else "warning",
                        (
                            "operation_history is present"
                            if operation_history_summary["history_size"] > 0
                            else "operation_history is empty"
                        ),
                        **operation_history_summary,
                    ))
                    if operation_history_summary["consecutive_fallbacks"] >= 3:
                        checks.append(_check(
                            "cache_metadata:consecutive_fallbacks",
                            "warning",
                            "Recent cache operations are repeatedly falling back",
                            consecutive_fallbacks=operation_history_summary["consecutive_fallbacks"],
                            fallback_reasons=operation_history_summary["fallback_reasons"],
                        ))
                else:
                    checks.append(_check(
                        "cache_metadata:operation_history",
                        "warning",
                        "cache_metadata.operation_history column is missing",
                    ))

            cache_rows = int(_scalar(db, "SELECT COUNT(*) FROM recipe_offer_cache") or 0)
            metadata_matches = metadata.get("total_matches") if metadata else None
            if metadata_matches is None:
                checks.append(_check(
                    "recipe_offer_cache:metadata_total",
                    "warning",
                    "cache_metadata.total_matches is empty",
                    cache_rows=cache_rows,
                ))
            elif int(metadata_matches) == cache_rows:
                checks.append(_check(
                    "recipe_offer_cache:metadata_total",
                    "ok",
                    "cache_metadata.total_matches matches recipe_offer_cache row count",
                    cache_rows=cache_rows,
                ))
            else:
                checks.append(_check(
                    "recipe_offer_cache:metadata_total",
                    "error",
                    "cache_metadata.total_matches does not match recipe_offer_cache row count",
                    metadata_total_matches=int(metadata_matches),
                    cache_rows=cache_rows,
                ))

            _count_check(
                checks,
                db,
                name="recipe_offer_cache:orphans",
                sql="""
                    SELECT COUNT(*)
                    FROM recipe_offer_cache c
                    LEFT JOIN found_recipes r ON r.id = c.found_recipe_id
                    WHERE r.id IS NULL
                """,
                ok_message="recipe_offer_cache has no orphaned recipe rows",
                bad_message="recipe_offer_cache contains rows for missing recipes",
                bad_status="error",
            )
            _count_check(
                checks,
                db,
                name="recipe_offer_cache:excluded_recipes",
                sql="""
                    SELECT COUNT(*)
                    FROM recipe_offer_cache c
                    JOIN found_recipes r ON r.id = c.found_recipe_id
                    WHERE COALESCE(r.excluded, FALSE) = TRUE
                """,
                ok_message="recipe_offer_cache has no excluded recipes",
                bad_message="recipe_offer_cache contains excluded recipes",
                bad_status="warning",
            )

            _compiled_recipe_checks(checks, db)
            _compiled_offer_checks(checks, db)

    except Exception as exc:
        logger.exception(f"Cache doctor failed: {exc}")
        checks.append(_check("cache_doctor:unexpected_error", "error", str(exc)))

    status = _overall_status(checks)
    return {
        "success": status != "error",
        "status": status,
        "checked_at": _utcnow_iso(),
        "versions": _versions(),
        "metadata": metadata,
        "operation_history": operation_history_summary,
        "summary": _summary(checks),
        "checks": checks,
    }


def _compiled_recipe_checks(checks: list[dict[str, Any]], db) -> None:
    _count_check(
        checks,
        db,
        name="compiled_recipe_match_data:missing_rows",
        sql="""
            SELECT COUNT(*)
            FROM found_recipes r
            LEFT JOIN compiled_recipe_match_data c ON c.found_recipe_id = r.id
            WHERE c.id IS NULL
        """,
        ok_message="compiled_recipe_match_data covers all found_recipes rows",
        bad_message="compiled_recipe_match_data is missing recipe rows",
        bad_status="warning",
    )
    _count_check(
        checks,
        db,
        name="compiled_recipe_match_data:stale_version",
        sql="""
            SELECT COUNT(*)
            FROM compiled_recipe_match_data
            WHERE compiler_version <> :recipe_compiler_version
        """,
        params={"recipe_compiler_version": RECIPE_COMPILER_VERSION},
        ok_message="compiled_recipe_match_data uses the current recipe compiler version",
        bad_message="compiled_recipe_match_data contains stale compiler versions",
        bad_status="warning",
    )
    _count_check(
        checks,
        db,
        name="compiled_recipe_match_data:active_mismatch",
        sql="""
            SELECT COUNT(*)
            FROM compiled_recipe_match_data c
            JOIN found_recipes r ON r.id = c.found_recipe_id
            WHERE c.is_active IS DISTINCT FROM (NOT COALESCE(r.excluded, FALSE))
        """,
        ok_message="compiled_recipe_match_data active flags match found_recipes.excluded",
        bad_message="compiled_recipe_match_data active flags differ from found_recipes.excluded",
        bad_status="warning",
    )
    _count_check(
        checks,
        db,
        name="compiled_recipe_term_index:orphans",
        sql="""
            SELECT COUNT(*)
            FROM compiled_recipe_term_index t
            LEFT JOIN found_recipes r ON r.id = t.found_recipe_id
            WHERE r.id IS NULL
        """,
        ok_message="compiled_recipe_term_index has no orphaned recipe rows",
        bad_message="compiled_recipe_term_index contains rows for missing recipes",
        bad_status="warning",
    )
    _count_check(
        checks,
        db,
        name="compiled_recipe_term_index:stale_version",
        sql="""
            SELECT COUNT(*)
            FROM compiled_recipe_term_index
            WHERE matcher_version <> :matcher_version
               OR recipe_compiler_version <> :recipe_compiler_version
        """,
        params={
            "matcher_version": MATCHER_VERSION,
            "recipe_compiler_version": RECIPE_COMPILER_VERSION,
        },
        ok_message="compiled_recipe_term_index uses current matcher and recipe compiler versions",
        bad_message="compiled_recipe_term_index contains stale matcher/compiler versions",
        bad_status="warning",
    )


def _compiled_offer_checks(checks: list[dict[str, Any]], db) -> None:
    _count_check(
        checks,
        db,
        name="compiled_offer_match_data:missing_rows",
        sql="""
            SELECT COUNT(*)
            FROM offers o
            LEFT JOIN compiled_offer_match_data c ON c.offer_id = o.id
            WHERE c.id IS NULL
        """,
        ok_message="compiled_offer_match_data covers all offer rows",
        bad_message="compiled_offer_match_data is missing offer rows",
        bad_status="warning",
    )
    _count_check(
        checks,
        db,
        name="compiled_offer_match_data:stale_version",
        sql="""
            SELECT COUNT(*)
            FROM compiled_offer_match_data
            WHERE compiler_version <> :offer_compiler_version
        """,
        params={"offer_compiler_version": OFFER_COMPILER_VERSION},
        ok_message="compiled_offer_match_data uses the current offer compiler version",
        bad_message="compiled_offer_match_data contains stale compiler versions",
        bad_status="warning",
    )
    _count_check(
        checks,
        db,
        name="compiled_offer_term_index:orphans",
        sql="""
            SELECT COUNT(*)
            FROM compiled_offer_term_index t
            LEFT JOIN offers o ON o.id = t.offer_id
            WHERE o.id IS NULL
        """,
        ok_message="compiled_offer_term_index has no orphaned offer rows",
        bad_message="compiled_offer_term_index contains rows for missing offers",
        bad_status="warning",
    )
    _count_check(
        checks,
        db,
        name="compiled_offer_term_index:stale_version",
        sql="""
            SELECT COUNT(*)
            FROM compiled_offer_term_index
            WHERE matcher_version <> :matcher_version
               OR offer_compiler_version <> :offer_compiler_version
        """,
        params={
            "matcher_version": MATCHER_VERSION,
            "offer_compiler_version": OFFER_COMPILER_VERSION,
        },
        ok_message="compiled_offer_term_index uses current matcher and offer compiler versions",
        bad_message="compiled_offer_term_index contains stale matcher/compiler versions",
        bad_status="warning",
    )


def _versions() -> dict[str, str]:
    return {
        "matcher_version": MATCHER_VERSION,
        "recipe_compiler_version": RECIPE_COMPILER_VERSION,
        "offer_compiler_version": OFFER_COMPILER_VERSION,
    }


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value
