"""
Scheduler API Routes.

This router handles recipe scraper and store scheduling:
- /api/schedules/* - Recipe scraper schedules
- /api/store-schedules/* - Store scraper schedules
"""

import json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from loguru import logger

from database import get_db_session
from utils.errors import friendly_error
from utils.store_scrape_config import build_store_scrape_config_context

# Import scheduler (optional component)
try:
    from scheduler import scraper_scheduler
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False


router = APIRouter(prefix="/api", tags=["schedules"])


# ==================== RECIPE SCRAPER SCHEDULES ====================

@router.get("/schedules")
def get_all_schedules():
    """Get all scraper schedules with last run recipe counts."""
    if not SCHEDULER_AVAILABLE:
        return JSONResponse({"success": False, "message_key": "scheduler.not_available"}, status_code=500)

    schedules = scraper_scheduler.get_all_schedules()

    # Get last run recipe counts and status from scraper_run_history
    last_run_recipes = {}
    last_run_status = {}
    try:
        with get_db_session() as db:
            # Get the most recent successful run for each scraper
            result = db.execute(text("""
                SELECT DISTINCT ON (scraper_id)
                    scraper_id, recipes_found, run_at
                FROM scraper_run_history
                WHERE success = TRUE
                ORDER BY scraper_id, run_at DESC
            """))
            for row in result:
                last_run_recipes[row.scraper_id] = row.recipes_found or 0

            # Get the most recent run (regardless of success) for failure detection
            status_result = db.execute(text("""
                SELECT DISTINCT ON (scraper_id)
                    scraper_id, success
                FROM scraper_run_history
                WHERE scraper_id NOT LIKE 'store_%'
                ORDER BY scraper_id, run_at DESC
            """))
            for sr in status_result:
                last_run_status[sr.scraper_id] = sr.success
    except Exception as e:
        logger.warning(f"Could not fetch last run recipes: {e}")

    return JSONResponse({
        "success": True,
        "schedules": [
            {
                "scraper_id": s.scraper_id,
                "frequency": s.frequency,
                "day_of_week": s.day_of_week,
                "day_of_month": s.day_of_month,
                "hour": s.hour,
                "timezone": s.timezone,
                "enabled": s.enabled,
                "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
                "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
                "last_run_recipes": last_run_recipes.get(s.scraper_id, 0),
                "last_run_failed": last_run_status.get(s.scraper_id) is False
            }
            for s in schedules
        ]
    })


@router.get("/schedules/{scraper_id}")
def get_schedule(scraper_id: str):
    """Get schedule for a specific scraper."""
    if not SCHEDULER_AVAILABLE:
        return JSONResponse({"success": False, "message_key": "scheduler.not_available"}, status_code=500)

    schedule = scraper_scheduler.get_schedule(scraper_id)

    if not schedule:
        return JSONResponse({
            "success": True,
            "schedule": None
        })

    return JSONResponse({
        "success": True,
        "schedule": {
            "scraper_id": schedule.scraper_id,
            "frequency": schedule.frequency,
            "day_of_week": schedule.day_of_week,
            "day_of_month": schedule.day_of_month,
            "hour": schedule.hour,
            "timezone": schedule.timezone,
            "enabled": schedule.enabled,
            "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
            "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None
        }
    })


@router.post("/schedules/{scraper_id}")
async def set_schedule(scraper_id: str, request: Request):
    """Create or update a schedule for a scraper."""
    if not SCHEDULER_AVAILABLE:
        return JSONResponse({"success": False, "message_key": "scheduler.not_available"}, status_code=500)

    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"success": False, "message_key": "scheduler.invalid_json"}, status_code=400)

    frequency = body.get("frequency")
    hour = body.get("hour")
    day_of_week = body.get("day_of_week")
    day_of_month = body.get("day_of_month")
    timezone = body.get("timezone", "Europe/Stockholm")
    enabled = body.get("enabled", True)

    # Validate
    if frequency not in ("daily", "weekly", "monthly"):
        return JSONResponse({
            "success": False,
            "message_key": "scheduler.invalid_frequency"
        }, status_code=400)

    if hour is None or not (0 <= hour <= 23):
        return JSONResponse({
            "success": False,
            "message_key": "scheduler.invalid_hour"
        }, status_code=400)

    if frequency == "weekly" and (day_of_week is None or not (0 <= day_of_week <= 6)):
        return JSONResponse({
            "success": False,
            "message_key": "scheduler.invalid_day_of_week"
        }, status_code=400)

    # Max 28: dag 29-31 finns inte i alla månader (februari har 28),
    # så jobbet skulle tyst skippa de månaderna.
    if frequency == "monthly" and (day_of_month is None or not (1 <= day_of_month <= 28)):
        return JSONResponse({
            "success": False,
            "message_key": "scheduler.invalid_day_of_month"
        }, status_code=400)

    success = scraper_scheduler.set_schedule(
        scraper_id=scraper_id,
        frequency=frequency,
        hour=hour,
        day_of_week=day_of_week if frequency == "weekly" else None,
        day_of_month=day_of_month if frequency == "monthly" else None,
        timezone=timezone,
        enabled=enabled
    )

    if success:
        # Get updated schedule to return next_run_at
        schedule = scraper_scheduler.get_schedule(scraper_id)
        return JSONResponse({
            "success": True,
            "message_key": "scheduler.saved",
            "next_run_at": schedule.next_run_at.isoformat() if schedule and schedule.next_run_at else None
        })

    return JSONResponse({"success": False, "message_key": "scheduler.save_failed"}, status_code=500)


@router.delete("/schedules/{scraper_id}")
def delete_schedule(scraper_id: str):
    """Delete a schedule for a scraper."""
    if not SCHEDULER_AVAILABLE:
        return JSONResponse({"success": False, "message_key": "scheduler.not_available"}, status_code=500)

    success = scraper_scheduler.delete_schedule(scraper_id)

    if success:
        return JSONResponse({"success": True, "message_key": "scheduler.deleted"})

    return JSONResponse({"success": False, "message_key": "scheduler.delete_failed"}, status_code=500)


# ==================== STORE SCHEDULES ====================

@router.get("/store-schedules")
def get_all_store_schedules():
    """Get all store schedules with location info."""
    try:
        with get_db_session() as db:
            # Use schedule's own config snapshot (not live stores.config)
            result = db.execute(text("""
                SELECT id, store_id, frequency, day_of_week, day_of_month,
                       hour, timezone, enabled, last_run_at, next_run_at,
                       config
                FROM store_schedules
                ORDER BY store_id
            """))

            # Get last run status for each store scraper
            last_run_status = {}
            status_result = db.execute(text("""
                SELECT DISTINCT ON (scraper_id)
                    scraper_id, success, error_message
                FROM scraper_run_history
                WHERE scraper_id LIKE 'store_%'
                ORDER BY scraper_id, run_at DESC
            """))
            for sr in status_result:
                last_run_status[sr.scraper_id] = {
                    "success": sr.success,
                    "error_message": sr.error_message
                }

            schedules = []
            for row in result:
                config = row.config if row.config else {}
                ehandel_store_name = config.get("ehandel_store_name") if isinstance(config, dict) else None
                run_status = last_run_status.get(f"store_{row.store_id}", {})

                schedules.append({
                    "id": str(row.id),
                    "store_id": row.store_id,
                    "frequency": row.frequency,
                    "day_of_week": row.day_of_week,
                    "day_of_month": row.day_of_month,
                    "hour": row.hour,
                    "timezone": row.timezone,
                    "enabled": row.enabled,
                    "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
                    "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
                    "last_run_failed": run_status.get("success") is False,
                    "location_type": config.get("location_type") if isinstance(config, dict) else None,
                    "location_name": config.get("location_name") if isinstance(config, dict) else None,
                    "ehandel_store_name": ehandel_store_name
                })

            return JSONResponse({"success": True, "schedules": schedules})

    except Exception as e:
        logger.error(f"Failed to get store schedules: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.get("/store-schedules/{store_id}")
def get_store_schedule(store_id: str):
    """Get schedule for a specific store."""
    try:
        with get_db_session() as db:
            result = db.execute(
                text("""
                    SELECT id, store_id, frequency, day_of_week, day_of_month,
                           hour, timezone, enabled, last_run_at, next_run_at
                    FROM store_schedules
                    WHERE store_id = :store_id
                """),
                {"store_id": store_id}
            ).fetchone()

            if result:
                # Check if last run failed
                last_run_failed = False
                run_check = db.execute(text("""
                    SELECT success FROM scraper_run_history
                    WHERE scraper_id = :sid
                    ORDER BY run_at DESC LIMIT 1
                """), {"sid": f"store_{store_id}"}).fetchone()
                if run_check and run_check.success is False:
                    last_run_failed = True

                return JSONResponse({
                    "success": True,
                    "schedule": {
                        "id": str(result.id),
                        "store_id": result.store_id,
                        "frequency": result.frequency,
                        "day_of_week": result.day_of_week,
                        "day_of_month": result.day_of_month,
                        "hour": result.hour,
                        "timezone": result.timezone,
                        "enabled": result.enabled,
                        "last_run_at": result.last_run_at.isoformat() if result.last_run_at else None,
                        "next_run_at": result.next_run_at.isoformat() if result.next_run_at else None,
                        "last_run_failed": last_run_failed
                    }
                })
            else:
                return JSONResponse({"success": True, "schedule": None})

    except Exception as e:
        logger.error(f"Failed to get store schedule: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.post("/store-schedules/{store_id}")
async def set_store_schedule(store_id: str, request: Request):
    """Create or update a schedule for a store."""
    if not SCHEDULER_AVAILABLE:
        return JSONResponse({"success": False, "message_key": "scheduler.not_available"}, status_code=500)

    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"success": False, "message_key": "scheduler.invalid_json"}, status_code=400)

    frequency = body.get("frequency")
    hour = body.get("hour", 6)
    day_of_week = body.get("day_of_week")
    day_of_month = body.get("day_of_month")
    timezone = body.get("timezone", "Europe/Stockholm")

    if not frequency or frequency not in ["daily", "weekly", "monthly"]:
        return JSONResponse({"success": False, "message_key": "scheduler.invalid_frequency"}, status_code=400)

    if not (0 <= hour <= 23):
        return JSONResponse({"success": False, "message_key": "scheduler.invalid_hour"}, status_code=400)

    if frequency == "weekly" and (day_of_week is None or not (0 <= day_of_week <= 6)):
        return JSONResponse({"success": False, "message_key": "scheduler.invalid_day_of_week"}, status_code=400)

    if frequency == "monthly" and (day_of_month is None or not (1 <= day_of_month <= 28)):
        return JSONResponse({"success": False, "message_key": "scheduler.invalid_day_of_month"}, status_code=400)

    conflict = scraper_scheduler.get_store_schedule_hour_conflict(store_id, hour)
    if conflict:
        return JSONResponse({
            "success": False,
            "message_key": "scheduler.store_hour_conflict",
            "message_params": {
                "store": conflict["store_name"],
                "hour": conflict["hour_label"],
            }
        }, status_code=409)

    try:
        with get_db_session() as db:
            config_context = build_store_scrape_config_context(db, store_id)
    except Exception as e:
        logger.error(f"Failed to validate store schedule config for {store_id}: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)

    if not config_context.valid:
        return JSONResponse(config_context.error_response(), status_code=400)

    next_run = scraper_scheduler.set_store_schedule(
        store_id=store_id,
        frequency=frequency,
        hour=hour,
        day_of_week=day_of_week if frequency == "weekly" else None,
        day_of_month=day_of_month if frequency == "monthly" else None,
        timezone=timezone,
    )

    if next_run is not None:
        return JSONResponse({
            "success": True,
            "message_key": "scheduler.saved",
            "next_run_at": next_run.isoformat()
        })

    conflict = scraper_scheduler.get_store_schedule_hour_conflict(store_id, hour)
    if conflict:
        return JSONResponse({
            "success": False,
            "message_key": "scheduler.store_hour_conflict",
            "message_params": {
                "store": conflict["store_name"],
                "hour": conflict["hour_label"],
            }
        }, status_code=409)

    return JSONResponse({"success": False, "message_key": "scheduler.save_failed"}, status_code=500)


@router.delete("/store-schedules/{store_id}")
def delete_store_schedule(store_id: str):
    """Delete a schedule for a store."""
    if not SCHEDULER_AVAILABLE:
        return JSONResponse({"success": False, "message_key": "scheduler.not_available"}, status_code=500)

    if scraper_scheduler.delete_store_schedule(store_id):
        return JSONResponse({"success": True, "message_key": "scheduler.deleted"})

    return JSONResponse({"success": False, "message_key": "scheduler.delete_failed"}, status_code=500)
