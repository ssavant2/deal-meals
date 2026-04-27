"""
Recipe Scraper Scheduler

Handles scheduled execution of recipe scrapers using APScheduler.
Schedules are stored in the database and persist across restarts.
"""

import json
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass
from sqlalchemy import text
from loguru import logger
import importlib
from zoneinfo import ZoneInfo

from database import get_db_session
from scrapers.recipes._common import normalize_recipe_scrape_result
from utils.scraper_history import save_run_history


@dataclass
class ScheduleInfo:
    """Information about a scheduled job."""
    id: str
    scraper_id: str
    frequency: str  # 'daily', 'weekly', 'monthly'
    day_of_week: Optional[int]  # 0-6 (Monday-Sunday)
    day_of_month: Optional[int]  # 1-28
    hour: int  # 0-23
    timezone: str
    enabled: bool
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]


class ScraperScheduler:
    """
    Manages scheduled recipe scraper jobs.

    Uses APScheduler with AsyncIO for non-blocking execution.
    Stores schedules in PostgreSQL for persistence.
    """

    RETRY_DELAY_MINUTES = 5

    # Grace period (seconds) to wait for other same-time scrapers to register
    _BATCH_GRACE_SECONDS = 3

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._started = False
        # Sequential execution lock and batch tracking for image downloads
        self._scraper_lock = None  # Created lazily (needs running event loop)
        self._scrapers_waiting = 0
        self._batch_has_new_recipes = False

    def start(self):
        """Start the scheduler and load jobs from database."""
        if self._started:
            return

        self.scheduler.start()
        self._started = True
        logger.info("Scheduler started")

        # Load existing schedules from database
        self._load_schedules_from_db()
        self._load_store_schedules_from_db()

        # Daily cleanup of old scraper run history (30 days retention)
        from utils.scraper_history import cleanup_old_history
        from utils.recipe_image_cleanup import prune_orphan_recipe_images

        self.scheduler.add_job(
            cleanup_old_history,
            CronTrigger(hour=3, minute=0),
            id="cleanup_run_history",
            replace_existing=True,
        )
        self.scheduler.add_job(
            prune_orphan_recipe_images,
            CronTrigger(day_of_week="sun", hour=4, minute=0),
            id="cleanup_orphan_recipe_images",
            kwargs={"dry_run": False, "reason": "weekly_scheduler"},
            replace_existing=True,
        )

    def shutdown(self):
        """Shutdown the scheduler."""
        if self._started:
            self.scheduler.shutdown()
            self._started = False
            logger.info("Scheduler shutdown")

    def _load_schedules_from_db(self):
        """Load all enabled schedules from database and add them to scheduler."""
        try:
            with get_db_session() as db:
                result = db.execute(text("""
                    SELECT id, scraper_id, frequency, day_of_week, day_of_month,
                           hour, timezone, enabled
                    FROM scraper_schedules
                    WHERE enabled = true
                """))
                rows = result.fetchall()  # Fetch all before closing session

            # Session is closed — safe to open new sessions inside _add_job_from_schedule
            for row in rows:
                self._add_job_from_schedule(
                    schedule_id=str(row.id),
                    scraper_id=row.scraper_id,
                    frequency=row.frequency,
                    day_of_week=row.day_of_week,
                    day_of_month=row.day_of_month,
                    hour=row.hour,
                    timezone=row.timezone
                )

        except Exception as e:
            logger.error(f"Failed to load schedules from database: {e}")

    def _add_job_from_schedule(
        self,
        schedule_id: str,
        scraper_id: str,
        frequency: str,
        day_of_week: Optional[int],
        day_of_month: Optional[int],
        hour: int,
        timezone: str
    ):
        """Add a job to the scheduler based on schedule parameters."""
        try:
            # Remove existing job if any
            job_id = f"scraper_{scraper_id}"
            try:
                self.scheduler.remove_job(job_id)
            except Exception:
                # Job might not exist, which is fine
                pass

            # Create cron trigger based on frequency
            tz = ZoneInfo(timezone)

            if frequency == 'daily':
                trigger = CronTrigger(hour=hour, minute=0, timezone=tz)
            elif frequency == 'weekly':
                # day_of_week: 0=Monday, 6=Sunday (APScheduler uses same convention)
                trigger = CronTrigger(
                    day_of_week=day_of_week,
                    hour=hour,
                    minute=0,
                    timezone=tz
                )
            elif frequency == 'monthly':
                trigger = CronTrigger(
                    day=day_of_month,
                    hour=hour,
                    minute=0,
                    timezone=tz
                )
            else:
                logger.error(f"Unknown frequency: {frequency}")
                return

            # Add the job
            self.scheduler.add_job(
                self._run_scraper,
                trigger=trigger,
                id=job_id,
                args=[scraper_id],
                replace_existing=True
            )

            # Update next_run_at in database
            job = self.scheduler.get_job(job_id)
            if job and job.next_run_time:
                self._update_next_run(scraper_id, job.next_run_time)

            logger.info(f"Scheduled scraper '{scraper_id}' - {frequency} at {hour}:00 ({timezone})")

        except Exception as e:
            logger.error(f"Failed to add job for {scraper_id}: {e}")

    async def _run_scraper(self, scraper_id: str):
        """
        Execute a scheduled scraper run.

        Uses a lock to run scrapers sequentially. When multiple scrapers
        fire at the same time, they queue up and a single image download
        runs after the last one finishes.
        """
        import asyncio as _asyncio

        # Lazy-create lock (needs running event loop)
        if self._scraper_lock is None:
            self._scraper_lock = _asyncio.Lock()

        # Increment BEFORE lock: safe in single-threaded async (no await between
        # read and write). This lets the lock holder see how many scrapers are queued,
        # so the last one in a batch can trigger a combined image download.
        self._scrapers_waiting += 1
        logger.info(f"Scheduled scraper {scraper_id} queued ({self._scrapers_waiting} waiting)")

        async with self._scraper_lock:
            self._scrapers_waiting -= 1
            await self._execute_scraper(scraper_id)

            # Grace period: let other same-time scrapers register (increment above)
            # before checking if we're the last one in the batch.
            await _asyncio.sleep(self._BATCH_GRACE_SECONDS)

            if self._scrapers_waiting == 0 and self._batch_has_new_recipes:
                # Last scraper in batch — trigger one combined image download
                self._batch_has_new_recipes = False
                try:
                    from utils.image_auto_download import trigger_auto_download_if_enabled
                    if await trigger_auto_download_if_enabled():
                        logger.info(f"Auto-download triggered after scheduled batch (last scraper: {scraper_id})")
                except Exception as e:
                    logger.warning(f"Could not trigger auto-download after batch: {e}")
            elif self._scrapers_waiting > 0:
                logger.info(f"Skipping auto-download, {self._scrapers_waiting} more scrapers queued")

    async def _execute_scraper(self, scraper_id: str):
        """Run the actual scraper logic (called under lock)."""
        import time
        start_time = time.time()
        recipes_found = 0

        logger.info(f"Running scheduled scraper: {scraper_id}")

        try:
            from recipe_scraper_manager import scraper_manager

            scraper_class = scraper_manager.get_scraper_class(scraper_id)
            if not scraper_class:
                logger.error(f"Scraper class not found for {scraper_id}")
                return

            # Run incremental scrape
            scraper = scraper_class()
            scraper_info = scraper_manager.get_scraper(scraper_id)
            db_source_name = (scraper_info.db_source_name or scraper_info.name) if scraper_info else None
            if hasattr(scraper, 'scrape_incremental'):
                scrape_result = normalize_recipe_scrape_result(
                    await scraper.scrape_incremental(),
                    mode="incremental",
                    source_name=db_source_name,
                )
                if scrape_result.status == "failed":
                    raise RuntimeError(scrape_result.reason or "recipe_scrape_failed")
                if scrape_result.status == "cancelled":
                    logger.info(f"Scheduled scrape cancelled for {scraper_id}")
                    return
                scraper_module = importlib.import_module(f"scrapers.recipes.{scraper_id}_scraper")
                save_to_database = getattr(scraper_module, 'save_to_database')
                if scrape_result.should_save:
                    result = save_to_database(scrape_result, clear_old=False)
                    recipes_found = result.get("created", 0) if isinstance(result, dict) else 0
                logger.info(f"Scheduled scrape complete for {scraper_id}: {recipes_found} new recipes")
            elif hasattr(scraper, 'scrape_and_save'):
                result = await scraper.scrape_and_save(overwrite=False)
                recipes_found = result.get("created", 0) if isinstance(result, dict) else 0
                logger.info(f"Scheduled scrape complete for {scraper_id}: {result}")
            else:
                scrape_result = normalize_recipe_scrape_result(
                    await scraper.scrape_all_recipes(),
                    mode="incremental",
                    source_name=db_source_name,
                )
                if scrape_result.status == "failed":
                    raise RuntimeError(scrape_result.reason or "recipe_scrape_failed")
                if scrape_result.status == "cancelled":
                    logger.info(f"Scheduled scrape cancelled for {scraper_id}")
                    return
                scraper_module = importlib.import_module(f"scrapers.recipes.{scraper_id}_scraper")
                save_to_database = getattr(scraper_module, 'save_to_database')
                result = save_to_database(scrape_result, clear_old=False) if scrape_result.should_save else {}
                recipes_found = result.get("created", 0) if isinstance(result, dict) else len(scrape_result)
                logger.info(f"Scheduled scrape complete for {scraper_id}: {len(scrape_result)} recipes")

            # Update last_run_at and next_run_at
            self._update_last_run(scraper_id)

            job = self.scheduler.get_job(f"scraper_{scraper_id}")
            if job and job.next_run_time:
                self._update_next_run(scraper_id, job.next_run_time)

            # Save to run history for time estimates
            duration = int(time.time() - start_time)
            save_run_history(scraper_id, "incremental", duration, recipes_found, success=True)

            # Flag for batch download (checked after lock release grace period)
            if recipes_found > 0:
                self._batch_has_new_recipes = True

        except Exception as e:
            logger.exception(f"Scheduled scraper {scraper_id} failed")
            duration = int(time.time() - start_time)
            save_run_history(scraper_id, "incremental", duration, recipes_found, success=False, error_message=str(e))

    def _update_last_run(self, scraper_id: str):
        """Update last_run_at in database."""
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
            logger.error(f"Failed to update last_run_at: {e}")

    def _update_next_run(self, scraper_id: str, next_run: datetime):
        """Update next_run_at in database."""
        try:
            with get_db_session() as db:
                db.execute(
                    text("""
                        UPDATE scraper_schedules
                        SET next_run_at = :next_run, updated_at = NOW()
                        WHERE scraper_id = :scraper_id
                    """),
                    {"scraper_id": scraper_id, "next_run": next_run}
                )
                db.commit()
        except Exception as e:
            logger.error(f"Failed to update next_run_at: {e}")

    def get_all_schedules(self) -> List[ScheduleInfo]:
        """Get all schedules from database."""
        schedules = []
        try:
            with get_db_session() as db:
                result = db.execute(text("""
                    SELECT id, scraper_id, frequency, day_of_week, day_of_month,
                           hour, timezone, enabled, last_run_at, next_run_at
                    FROM scraper_schedules
                    ORDER BY scraper_id
                """))

                for row in result:
                    schedules.append(ScheduleInfo(
                        id=str(row.id),
                        scraper_id=row.scraper_id,
                        frequency=row.frequency,
                        day_of_week=row.day_of_week,
                        day_of_month=row.day_of_month,
                        hour=row.hour,
                        timezone=row.timezone,
                        enabled=row.enabled,
                        last_run_at=row.last_run_at,
                        next_run_at=row.next_run_at
                    ))
        except Exception as e:
            logger.error(f"Failed to get schedules: {e}")

        return schedules

    def get_schedule(self, scraper_id: str) -> Optional[ScheduleInfo]:
        """Get schedule for a specific scraper."""
        try:
            with get_db_session() as db:
                result = db.execute(
                    text("""
                        SELECT id, scraper_id, frequency, day_of_week, day_of_month,
                               hour, timezone, enabled, last_run_at, next_run_at
                        FROM scraper_schedules
                        WHERE scraper_id = :scraper_id
                    """),
                    {"scraper_id": scraper_id}
                ).fetchone()

                if result:
                    return ScheduleInfo(
                        id=str(result.id),
                        scraper_id=result.scraper_id,
                        frequency=result.frequency,
                        day_of_week=result.day_of_week,
                        day_of_month=result.day_of_month,
                        hour=result.hour,
                        timezone=result.timezone,
                        enabled=result.enabled,
                        last_run_at=result.last_run_at,
                        next_run_at=result.next_run_at
                    )
        except Exception as e:
            logger.error(f"Failed to get schedule for {scraper_id}: {e}")

        return None

    def set_schedule(
        self,
        scraper_id: str,
        frequency: str,
        hour: int,
        day_of_week: Optional[int] = None,
        day_of_month: Optional[int] = None,
        timezone: str = "Europe/Stockholm",
        enabled: bool = True
    ) -> bool:
        """Create or update a schedule for a scraper."""
        try:
            with get_db_session() as db:
                # Upsert schedule
                db.execute(
                    text("""
                        INSERT INTO scraper_schedules
                            (scraper_id, frequency, day_of_week, day_of_month, hour, timezone, enabled)
                        VALUES
                            (:scraper_id, :frequency, :day_of_week, :day_of_month, :hour, :timezone, :enabled)
                        ON CONFLICT (scraper_id) DO UPDATE SET
                            frequency = :frequency,
                            day_of_week = :day_of_week,
                            day_of_month = :day_of_month,
                            hour = :hour,
                            timezone = :timezone,
                            enabled = :enabled,
                            updated_at = NOW()
                    """),
                    {
                        "scraper_id": scraper_id,
                        "frequency": frequency,
                        "day_of_week": day_of_week,
                        "day_of_month": day_of_month,
                        "hour": hour,
                        "timezone": timezone,
                        "enabled": enabled
                    }
                )
                db.commit()

            # Update scheduler
            if enabled:
                self._add_job_from_schedule(
                    schedule_id="",
                    scraper_id=scraper_id,
                    frequency=frequency,
                    day_of_week=day_of_week,
                    day_of_month=day_of_month,
                    hour=hour,
                    timezone=timezone
                )
            else:
                # Remove job if disabled
                try:
                    self.scheduler.remove_job(f"scraper_{scraper_id}")
                except Exception:
                    # Job might not exist, which is fine
                    pass

            return True

        except Exception as e:
            logger.error(f"Failed to set schedule for {scraper_id}: {e}")
            return False

    def delete_schedule(self, scraper_id: str) -> bool:
        """Delete a schedule for a scraper."""
        try:
            # Remove from scheduler
            try:
                self.scheduler.remove_job(f"scraper_{scraper_id}")
            except Exception:
                # Job might not exist, which is fine
                pass

            # Remove from database
            with get_db_session() as db:
                db.execute(
                    text("DELETE FROM scraper_schedules WHERE scraper_id = :scraper_id"),
                    {"scraper_id": scraper_id}
                )
                db.commit()

            logger.info(f"Deleted schedule for {scraper_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete schedule for {scraper_id}: {e}")
            return False

    # ==================== STORE SCHEDULING ====================

    def _get_store_schedule_hour_conflict(self, db, store_id: str, hour: int) -> Optional[Dict]:
        """Find another enabled store schedule using the same whole-hour slot."""
        row = db.execute(text("""
            SELECT
                ss.store_id,
                COALESCE(s.name, ss.store_id) AS store_name,
                ss.frequency,
                ss.day_of_week,
                ss.day_of_month,
                ss.hour
            FROM store_schedules ss
            LEFT JOIN stores s ON s.store_type = ss.store_id
            WHERE ss.enabled = true
              AND ss.hour = :hour
              AND ss.store_id != :store_id
            ORDER BY ss.store_id
            LIMIT 1
        """), {
            "store_id": store_id,
            "hour": hour,
        }).mappings().fetchone()

        if not row:
            return None

        return {
            "store_id": row["store_id"],
            "store_name": row["store_name"],
            "frequency": row["frequency"],
            "day_of_week": row["day_of_week"],
            "day_of_month": row["day_of_month"],
            "hour": row["hour"],
            "hour_label": f"{int(row['hour']):02d}:00",
        }

    def get_store_schedule_hour_conflict(self, store_id: str, hour: int) -> Optional[Dict]:
        """Public read-only conflict check for store schedules."""
        try:
            with get_db_session() as db:
                return self._get_store_schedule_hour_conflict(db, store_id, hour)
        except Exception as e:
            logger.error(f"Failed to check store schedule hour conflict for {store_id}: {e}")
            return None

    def set_store_schedule(
        self,
        store_id: str,
        frequency: str,
        hour: int,
        day_of_week: Optional[int] = None,
        day_of_month: Optional[int] = None,
        timezone: str = "Europe/Stockholm",
    ) -> Optional[datetime]:
        """Create or update a schedule for a store. Returns next_run_at, or None on failure."""
        try:
            from utils.store_scrape_config import build_store_scrape_config_context

            tz = ZoneInfo(timezone)

            if frequency == 'daily':
                trigger = CronTrigger(hour=hour, minute=0, timezone=tz)
            elif frequency == 'weekly':
                trigger = CronTrigger(day_of_week=day_of_week, hour=hour, minute=0, timezone=tz)
            elif frequency == 'monthly':
                trigger = CronTrigger(day=day_of_month, hour=hour, minute=0, timezone=tz)
            else:
                logger.error(f"Unknown frequency: {frequency}")
                return None

            next_run = trigger.get_next_fire_time(None, datetime.now(tz))

            with get_db_session() as db:
                conflict = self._get_store_schedule_hour_conflict(db, store_id, hour)
                if conflict:
                    logger.warning(
                        f"Store schedule for {store_id} at {hour:02d}:00 conflicts with "
                        f"{conflict['store_id']}"
                    )
                    return None

                config_context = build_store_scrape_config_context(db, store_id)
                if not config_context.valid:
                    logger.warning(
                        f"Store schedule for {store_id} blocked by invalid config: "
                        f"{config_context.message_key} {config_context.message_params}"
                    )
                    return None

                # Snapshot current store config so scheduled job is independent of UI changes
                store_config = {}
                store_row = db.execute(text(
                    "SELECT config FROM stores WHERE store_type = :store_type"
                ), {"store_type": store_id}).fetchone()
                if store_row and store_row.config:
                    store_config = store_row.config if isinstance(store_row.config, dict) else {}

                db.execute(text("""
                    INSERT INTO store_schedules
                        (store_id, frequency, day_of_week, day_of_month, hour, timezone, enabled, config, next_run_at)
                    VALUES
                        (:store_id, :frequency, :day_of_week, :day_of_month, :hour, :timezone, true, :config, :next_run_at)
                    ON CONFLICT (store_id) DO UPDATE SET
                        frequency = :frequency,
                        day_of_week = :day_of_week,
                        day_of_month = :day_of_month,
                        hour = :hour,
                        timezone = :timezone,
                        enabled = true,
                        config = :config,
                        next_run_at = :next_run_at,
                        updated_at = NOW()
                """), {
                    "store_id": store_id,
                    "frequency": frequency,
                    "day_of_week": day_of_week,
                    "day_of_month": day_of_month,
                    "hour": hour,
                    "timezone": timezone,
                    "config": json.dumps(store_config),
                    "next_run_at": next_run
                })
                db.commit()

            self._add_store_job(store_id, frequency, day_of_week, day_of_month, hour, timezone)
            return next_run

        except Exception as e:
            logger.error(f"Failed to set store schedule for {store_id}: {e}")
            return None

    def delete_store_schedule(self, store_id: str) -> bool:
        """Delete a schedule for a store."""
        try:
            try:
                self.scheduler.remove_job(f"store_{store_id}")
            except Exception:
                pass

            with get_db_session() as db:
                db.execute(
                    text("DELETE FROM store_schedules WHERE store_id = :store_id"),
                    {"store_id": store_id}
                )
                db.commit()

            logger.info(f"Deleted store schedule for {store_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete store schedule for {store_id}: {e}")
            return False

    def _load_store_schedules_from_db(self):
        """Load all enabled store schedules from database and add them to scheduler."""
        try:
            with get_db_session() as db:
                result = db.execute(text("""
                    SELECT id, store_id, frequency, day_of_week, day_of_month,
                           hour, timezone, enabled
                    FROM store_schedules
                    WHERE enabled = true
                """))
                rows = result.fetchall()  # Fetch all before closing session

            # Session is closed — safe to open new sessions inside _add_store_job
            for row in rows:
                self._add_store_job(
                    store_id=row.store_id,
                    frequency=row.frequency,
                    day_of_week=row.day_of_week,
                    day_of_month=row.day_of_month,
                    hour=row.hour,
                    timezone=row.timezone
                )

        except Exception as e:
            logger.error(f"Failed to load store schedules from database: {e}")

    def _add_store_job(
        self,
        store_id: str,
        frequency: str,
        day_of_week: Optional[int],
        day_of_month: Optional[int],
        hour: int,
        timezone: str
    ):
        """Add a store scraper job to the scheduler."""
        try:
            # Remove existing job if any
            job_id = f"store_{store_id}"
            try:
                self.scheduler.remove_job(job_id)
            except Exception:
                # Job might not exist, which is fine
                pass

            # Create cron trigger based on frequency
            tz = ZoneInfo(timezone)

            if frequency == 'daily':
                trigger = CronTrigger(hour=hour, minute=0, timezone=tz)
            elif frequency == 'weekly':
                trigger = CronTrigger(
                    day_of_week=day_of_week,
                    hour=hour,
                    minute=0,
                    timezone=tz
                )
            elif frequency == 'monthly':
                trigger = CronTrigger(
                    day=day_of_month,
                    hour=hour,
                    minute=0,
                    timezone=tz
                )
            else:
                logger.error(f"Unknown frequency: {frequency}")
                return

            # Add the job
            self.scheduler.add_job(
                self._run_store_scraper,
                trigger=trigger,
                id=job_id,
                args=[store_id],
                replace_existing=True
            )

            # Update next_run_at in database
            job = self.scheduler.get_job(job_id)
            if job and job.next_run_time:
                self._update_store_next_run(store_id, job.next_run_time)

            logger.info(f"Scheduled store '{store_id}' - {frequency} at {hour}:00 ({timezone})")

        except Exception as e:
            logger.error(f"Failed to add store job for {store_id}: {e}")

    async def _run_store_scraper(self, store_id: str, is_retry: bool = False):
        """Execute a scheduled store scraper run."""
        import time
        start_time = time.time()
        product_count = 0
        error_message = None
        verified_empty_success = False
        registered_active_scrape = False
        run_label = "RETRY" if is_retry else "scheduled"

        logger.info(f"Running {run_label} store scraper: {store_id}")

        try:
            # Import store plugin system (same as app.py)
            from scrapers.stores import get_store, normalize_store_scrape_result
            from state import try_start_active_scrape, update_active_scrape
            from utils.store_scrape_config import build_store_scrape_config_context

            store_plugin = get_store(store_id)
            if not store_plugin:
                logger.error(f"Store plugin not found for {store_id}")
                return

            plugin_config = store_plugin.config
            display_name = plugin_config.name
            estimated_time = getattr(store_plugin, "estimated_scrape_time", 300)
            running_sid = await try_start_active_scrape(store_id, {
                "started_at": datetime.now(ZoneInfo("UTC")),
                "est_time": estimated_time,
                "progress": 0,
                "message_key": "ws.fetching_offers",
                "message_params": {"store": display_name},
                "source": "scheduled",
                "run_label": run_label,
            })
            if running_sid:
                error_message = (
                    f"Skipped {run_label} store scrape for {store_id}; "
                    f"{running_sid} is already running"
                )
                logger.warning(error_message)
                duration = int(time.time() - start_time)
                save_run_history(
                    f"store_{store_id}",
                    "scheduled",
                    duration,
                    0,
                    success=False,
                    error_message=error_message,
                )
                job = self.scheduler.get_job(f"store_{store_id}")
                if job and job.next_run_time:
                    self._update_store_next_run(store_id, job.next_run_time)
                if not is_retry:
                    self._schedule_store_retry(store_id)
                return
            registered_active_scrape = True

            with get_db_session() as db:
                # Prefer schedule's own config snapshot (saved when schedule was created/updated)
                schedule_result = db.execute(text(
                    "SELECT config FROM store_schedules WHERE store_id = :store_id"
                ), {"store_id": store_id}).fetchone()

                config = {}
                if schedule_result and schedule_result.config:
                    config = schedule_result.config if isinstance(schedule_result.config, dict) else {}

                # Fallback to live store config if schedule has no snapshot (legacy schedules)
                if not config:
                    store_result = db.execute(text(
                        "SELECT config FROM stores WHERE store_type = :store_type"
                    ), {"store_type": store_id}).fetchone()
                    if store_result and store_result.config:
                        config = store_result.config if isinstance(store_result.config, dict) else {}

                config_context = build_store_scrape_config_context(
                    db,
                    store_id,
                    config_override=config if config else None,
                    store_name=display_name,
                )

            if not config_context.valid:
                error_message = (
                    f"Store schedule config invalid for {store_id}: "
                    f"{config_context.message_key} {config_context.message_params}"
                )
                logger.warning(error_message)
                await update_active_scrape(store_id, {
                    "progress": 0,
                    "message_key": config_context.message_key,
                    "message_params": config_context.message_params,
                })

                self._update_store_last_run(store_id)
                job = self.scheduler.get_job(f"store_{store_id}")
                if job and job.next_run_time:
                    self._update_store_next_run(store_id, job.next_run_time)

                duration = int(time.time() - start_time)
                save_run_history(
                    f"store_{store_id}",
                    "scheduled",
                    duration,
                    0,
                    success=False,
                    error_message=error_message,
                )
                return

            credentials = config_context.credentials

            await update_active_scrape(store_id, {
                "progress": 0,
                "message_key": "ws.fetching_products",
                "message_params": {"store": display_name},
            })

            # Run the store scraper
            scrape_result = normalize_store_scrape_result(
                await store_plugin.scrape_offers(credentials),
                store_name=store_id,
            )
            products = scrape_result.products

            if scrape_result.should_replace_offers:
                from db_saver import ensure_store_exists, save_offers, clear_offers_for_empty_scrape
                import asyncio

                scrape_meta = getattr(store_plugin, '_scrape_meta', None)
                if scrape_result.is_empty_success:
                    save_key = "ws.clearing_empty_offers"
                    save_params = {"store": display_name}
                elif scrape_meta and scrape_meta.get('variant_count', 0) > 0:
                    save_key = "ws.saving_products_with_variants"
                    save_params = {"base": scrape_meta['base_count'], "variants": scrape_meta['variant_count']}
                else:
                    save_key = "ws.saving_products"
                    save_params = {"count": len(products)}
                await update_active_scrape(store_id, {
                    "progress": 70,
                    "message_key": save_key,
                    "message_params": save_params,
                })

                # Ensure store exists in DB (auto-registers new stores)
                await asyncio.to_thread(ensure_store_exists, plugin_config.id, plugin_config.name, plugin_config.url)

                # Use store_id (ASCII) for save - matched via store_type column
                if scrape_result.is_empty_success:
                    result = await asyncio.to_thread(
                        clear_offers_for_empty_scrape,
                        store_id,
                        scrape_result.reason,
                    )
                else:
                    result = await asyncio.to_thread(save_offers, store_id, products)
                product_count = int(result.get('created', 0) or 0)
                verified_empty_success = bool(result.get('verified_empty'))

                if (
                    result.get('stale_existing_offers')
                    or (product_count <= 0 and not verified_empty_success)
                ):
                    error_message = (
                        f"No valid products were saved for {store_id}; "
                        "existing offers/cache kept"
                    )
                    logger.warning(f"{run_label.capitalize()} store scrape did not replace offers for {store_id}: {result}")
                    if not is_retry:
                        self._schedule_store_retry(store_id)
                else:
                    logger.info(f"{run_label.capitalize()} store scrape complete for {store_id}: {result}")
            else:
                error_message = (
                    f"Store scrape did not produce replaceable data for {store_id} "
                    f"(status={scrape_result.status}, reason={scrape_result.reason}); "
                    "existing offers/cache kept"
                )
                logger.warning(error_message)
                if not is_retry:
                    self._schedule_store_retry(store_id)

            # Update last_run_at and next_run_at
            self._update_store_last_run(store_id)

            job = self.scheduler.get_job(f"store_{store_id}")
            if job and job.next_run_time:
                self._update_store_next_run(store_id, job.next_run_time)

            # Save to run history
            duration = int(time.time() - start_time)
            save_run_history(
                f"store_{store_id}",
                "scheduled",
                duration,
                product_count,
                success=error_message is None and (product_count > 0 or verified_empty_success),
                error_message=error_message,
            )

        except Exception as e:
            logger.exception(f"{run_label.capitalize()} store scraper {store_id} failed")
            duration = int(time.time() - start_time)
            save_run_history(f"store_{store_id}", "scheduled", duration, 0, success=False, error_message=str(e))
            if not is_retry:
                self._schedule_store_retry(store_id)
        finally:
            if registered_active_scrape:
                try:
                    from state import delete_active_scrape
                    await delete_active_scrape(store_id)
                except Exception as e:
                    logger.warning(f"Failed to clear active store scrape for {store_id}: {e}")

    def _schedule_store_retry(self, store_id: str):
        """Schedule a one-time store scraper retry after RETRY_DELAY_MINUTES."""
        retry_time = datetime.now(ZoneInfo("Europe/Stockholm")) + timedelta(minutes=self.RETRY_DELAY_MINUTES)
        retry_job_id = f"store_{store_id}_retry"

        try:
            self.scheduler.add_job(
                self._run_store_scraper,
                trigger=DateTrigger(run_date=retry_time),
                id=retry_job_id,
                args=[store_id],
                kwargs={"is_retry": True},
                replace_existing=True
            )
            logger.info(f"Scheduled store retry for {store_id} at {retry_time.strftime('%H:%M')}")
        except Exception as e:
            logger.error(f"Failed to schedule store retry for {store_id}: {e}")

    def _update_store_last_run(self, store_id: str):
        """Update last_run_at in database for store."""
        try:
            with get_db_session() as db:
                db.execute(
                    text("""
                        UPDATE store_schedules
                        SET last_run_at = NOW(), updated_at = NOW()
                        WHERE store_id = :store_id
                    """),
                    {"store_id": store_id}
                )
                db.commit()
        except Exception as e:
            logger.error(f"Failed to update store last_run_at: {e}")

    def _update_store_next_run(self, store_id: str, next_run: datetime):
        """Update next_run_at in database for store."""
        try:
            with get_db_session() as db:
                db.execute(
                    text("""
                        UPDATE store_schedules
                        SET next_run_at = :next_run, updated_at = NOW()
                        WHERE store_id = :store_id
                    """),
                    {"store_id": store_id, "next_run": next_run}
                )
                db.commit()
        except Exception as e:
            logger.error(f"Failed to update store next_run_at: {e}")


# Singleton instance
scraper_scheduler = ScraperScheduler()
