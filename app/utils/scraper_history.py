"""Shared scraper run history utilities.

Used by both routers/recipes.py (manual runs) and scheduler.py (scheduled runs).
"""

from sqlalchemy import text
from database import get_db_session
from loguru import logger


RUN_HISTORY_RETENTION_PER_SCRAPER_MODE = 30


def _has_attempted_count_column(db) -> bool:
    """Return True when this database has the newer scalable estimate column."""
    return bool(db.execute(text("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'scraper_run_history'
              AND column_name = 'attempted_count'
        )
    """)).scalar())


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
            params = {
                "scraper_id": scraper_id,
                "mode": mode,
                "duration_seconds": duration_seconds,
                "recipes_found": recipes_found,
                "success": success,
                "error_message": error_message
            }
            if _has_attempted_count_column(db):
                params["attempted_count"] = attempted_count
                db.execute(
                    text("""
                        INSERT INTO scraper_run_history (
                            scraper_id, mode, duration_seconds, recipes_found,
                            attempted_count, success, error_message
                        )
                        VALUES (
                            :scraper_id, :mode, :duration_seconds, :recipes_found,
                            :attempted_count, :success, :error_message
                        )
                    """),
                    params,
                )
            else:
                db.execute(
                    text("""
                        INSERT INTO scraper_run_history (
                            scraper_id, mode, duration_seconds, recipes_found,
                            success, error_message
                        )
                        VALUES (
                            :scraper_id, :mode, :duration_seconds, :recipes_found,
                            :success, :error_message
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
