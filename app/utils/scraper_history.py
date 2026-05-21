"""Shared scraper run history utilities.

Used by both routers/recipes.py (manual runs) and scheduler.py (scheduled runs).
"""

import json

from sqlalchemy import text
from database import get_db_session
from loguru import logger


RUN_HISTORY_RETENTION_PER_SCRAPER_MODE = 30


def _first_present(mapping: dict, *keys):
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def scrape_result_history_kwargs(scrape_result, *, source_kind: str = None) -> dict:
    """Build optional save_run_history kwargs from a scraper result object."""
    diagnostics = dict(getattr(scrape_result, "diagnostics", None) or {})
    return {
        "source_kind": source_kind,
        "status": getattr(scrape_result, "status", None),
        "reason_code": getattr(scrape_result, "reason", None),
        "candidate_count": _first_present(
            diagnostics,
            "candidate_count",
            "candidate_urls",
            "candidate_url_count",
            "raw_product_count",
            "raw_offer_count",
        ),
        "selected_count": _first_present(
            diagnostics,
            "selected_count",
            "selected_urls",
            "selected_url_count",
            "product_count",
            "parsed_product_count",
        ),
        "parsed_count": _first_present(
            diagnostics,
            "parsed_count",
            "parsed_recipes",
            "parsed_recipe_count",
            "parsed_product_count",
            "product_count",
        ),
        "filtered_count": _first_present(
            diagnostics,
            "filtered_count",
            "filtered_urls",
            "filtered_non_recipe_count",
            "skipped_product_count",
        ),
        "parse_rate": diagnostics.get("parse_rate"),
        "data_path": _first_present(
            diagnostics,
            "data_path",
            "parser_method",
            "discovery_method",
        ),
        "diagnostics": diagnostics,
    }


def _scraper_run_history_columns(db) -> set[str]:
    """Return available scraper_run_history columns for additive deployments."""
    rows = db.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'scraper_run_history'
    """)).fetchall()
    return {str(row[0]) for row in rows}


def _cleanup_run_history_for_scraper_mode(
    db,
    *,
    scraper_id: str,
    mode: str,
    keep_latest: int = RUN_HISTORY_RETENTION_PER_SCRAPER_MODE,
) -> int:
    """Keep only the latest compact run-history rows for one scraper/mode."""
    keep_latest = max(1, int(keep_latest))
    result = db.execute(
        text("""
            DELETE FROM scraper_run_history
            WHERE id IN (
                SELECT id
                FROM scraper_run_history
                WHERE scraper_id = :scraper_id
                  AND mode = :mode
                ORDER BY run_at DESC, id DESC
                OFFSET :keep_latest
            )
        """),
        {
            "scraper_id": scraper_id,
            "mode": mode,
            "keep_latest": keep_latest,
        },
    )
    return int(result.rowcount or 0)


def save_run_history(
    scraper_id: str,
    mode: str,
    duration_seconds: int,
    recipes_found: int = 0,
    attempted_count: int = None,
    success: bool = True,
    error_message: str = None,
    update_schedule: bool = False,
    keep_latest_per_mode: int = RUN_HISTORY_RETENTION_PER_SCRAPER_MODE,
    source_kind: str = None,
    status: str = None,
    reason_code: str = None,
    candidate_count: int = None,
    selected_count: int = None,
    parsed_count: int = None,
    filtered_count: int = None,
    parse_rate: float = None,
    data_path: str = None,
    diagnostics: dict = None,
):
    """Save a scraper run to history for time estimates.

    Args:
        update_schedule: If True, also update last_run_at in scraper_schedules.
                        Used by manual runs (recipes.py) but not scheduled runs
                        (scheduler handles this separately).
        keep_latest_per_mode: Retain the latest N rows per scraper_id/mode after
                        saving this run. This keeps history persistent but
                        bounded; both success and failure rows are retained.
    """
    try:
        with get_db_session() as db:
            available_columns = _scraper_run_history_columns(db)
            params = {
                "scraper_id": scraper_id,
                "mode": mode,
                "duration_seconds": duration_seconds,
                "recipes_found": recipes_found,
                "success": success,
                "error_message": error_message
            }
            insert_columns = [
                "scraper_id",
                "mode",
                "duration_seconds",
                "recipes_found",
                "success",
                "error_message",
            ]
            value_expressions = {
                column: f":{column}"
                for column in insert_columns
            }

            optional_values = {
                "attempted_count": attempted_count,
                "source_kind": source_kind,
                "status": status or ("success" if success else "failed"),
                "reason_code": reason_code or (error_message if not success else None),
                "candidate_count": candidate_count,
                "selected_count": selected_count,
                "parsed_count": parsed_count,
                "filtered_count": filtered_count,
                "parse_rate": parse_rate,
                "data_path": data_path,
                "diagnostics": json.dumps(diagnostics or {}, ensure_ascii=False, sort_keys=True),
            }
            for column, value in optional_values.items():
                if column not in available_columns:
                    continue
                insert_columns.append(column)
                params[column] = value
                value_expressions[column] = (
                    f"CAST(:{column} AS jsonb)"
                    if column == "diagnostics"
                    else f":{column}"
                )

            db.execute(
                text(f"""
                    INSERT INTO scraper_run_history (
                        {", ".join(insert_columns)}
                    )
                    VALUES (
                        {", ".join(value_expressions[column] for column in insert_columns)}
                    )
                """),
                params,
            )
            removed_rows = _cleanup_run_history_for_scraper_mode(
                db,
                scraper_id=scraper_id,
                mode=mode,
                keep_latest=keep_latest_per_mode,
            )
            db.commit()
            if removed_rows > 0:
                logger.debug(
                    f"Trimmed {removed_rows} scraper_run_history rows for "
                    f"{scraper_id}/{mode}"
                )

            if update_schedule and success:
                _update_schedule_last_run(scraper_id)
    except Exception as e:
        logger.error(f"Failed to save run history: {e}")


def cleanup_old_history(days: int = 30):
    """Delete scraper run history older than N days."""
    try:
        with get_db_session() as db:
            result = db.execute(
                text("DELETE FROM scraper_run_history WHERE run_at < NOW() - make_interval(days => :days)"),
                {"days": int(days)}
            )
            db.commit()
            if result.rowcount > 0:
                logger.info(f"Cleaned up {result.rowcount} scraper_run_history rows older than {days} days")
    except Exception as e:
        logger.error(f"Failed to clean up run history: {e}")


def _update_schedule_last_run(scraper_id: str):
    """Update last_run_at in scraper_schedules table."""
    try:
        with get_db_session() as db:
            db.execute(
                text("""
                    UPDATE scraper_schedules
                    SET last_run_at = NOW(), updated_at = NOW()
                    WHERE scraper_id = :scraper_id
                """),
                {"scraper_id": scraper_id}
            )
            db.commit()
    except Exception as e:
        logger.warning(f"Could not update schedule last_run_at for {scraper_id}: {e}")
