"""
Status API Routes.

This router handles status and health check endpoints:
- /api/status/offers - Offer fetch status per store
- /api/status/recipes - Recipe source status summary
- /api/setup/status - Setup guide completion status
- /health - Health check for Docker
"""

import os
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from loguru import logger

from database import get_db_session
from utils.errors import friendly_error
from utils.rate_limit import limiter


# Check component availability (same pattern as other routers)
try:
    from scrapers.stores import get_enabled_stores
    PLUGIN_SYSTEM_AVAILABLE = True
except ImportError:
    PLUGIN_SYSTEM_AVAILABLE = False

try:
    from recipe_scraper_manager import scraper_manager
    RECIPE_SCRAPERS_AVAILABLE = True
except ImportError:
    RECIPE_SCRAPERS_AVAILABLE = False

try:
    from scheduler import scraper_scheduler
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False


router = APIRouter(tags=["status"])


# ==================== STATUS ENDPOINTS ====================

@router.get("/api/status/offers")
def get_offer_status():
    """API endpoint to get offer fetch status per store."""
    try:
        with get_db_session() as db:
            result = db.execute(text("""
                SELECT
                    s.name as store_name,
                    s.config as store_config,
                    o.location_type,
                    o.location_name,
                    COUNT(o.id) as offer_count,
                    MAX(o.scraped_at) as last_scraped_at
                FROM stores s
                LEFT JOIN offers o ON s.id = o.store_id
                GROUP BY s.id, s.name, o.location_type, o.location_name
                ORDER BY s.name, o.location_type
            """))

            stores = []
            for row in result:
                config = row.store_config or {}
                display_count = row.offer_count or 0
                if row.location_type == "butik":
                    display_count = config.get("last_display_count_butik", display_count)
                elif row.location_type == "ehandel":
                    display_count = config.get("last_display_count_ehandel", display_count)
                stores.append({
                    "store_name": row.store_name,
                    "location_type": row.location_type or "okänd",
                    "location_name": row.location_name,
                    "offer_count": display_count,
                    "actual_offer_count": row.offer_count or 0,
                    "last_scraped_at": row.last_scraped_at.isoformat() if row.last_scraped_at else None
                })

            return JSONResponse({
                "success": True,
                "stores": stores
            })
    except Exception as e:
        logger.error(f"Error fetching offer status: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e),
            "stores": []
        })


@router.get("/api/status/recipes")
def get_recipe_status():
    """API endpoint to get recipe source status summary."""
    try:
        with get_db_session() as db:
            # Get actual source names from found_recipes
            actual_sources = db.execute(text("""
                SELECT DISTINCT source_name FROM found_recipes
            """)).fetchall()
            actual_source_names = {row.source_name for row in actual_sources}

            # Get enabled/total counts from scraper manager (same logic as recipes page)
            if RECIPE_SCRAPERS_AVAILABLE:
                all_scrapers = scraper_manager.get_all_scrapers()
                total_source_count = len(all_scrapers)
                enabled_scrapers = [s for s in all_scrapers if s.enabled]
                active_source_count = len(enabled_scrapers)
                # Build set of enabled source names for recipe queries
                active_sources = set()
                for s in enabled_scrapers:
                    db_name = s.db_source_name or s.name
                    if db_name in actual_source_names:
                        active_sources.add(db_name)
            else:
                enabled_sources = db.execute(text("""
                    SELECT name FROM recipe_sources WHERE enabled = true
                """)).fetchall()
                enabled_source_names = {row.name for row in enabled_sources}
                total_source_count = len(enabled_source_names) if enabled_source_names else len(actual_source_names)
                active_sources = actual_source_names & enabled_source_names
                active_source_count = len(active_sources)

            # Get recipe count from ACTIVE sources only
            if active_sources:
                placeholders = ', '.join([f':s{i}' for i in range(len(active_sources))])
                params = {f's{i}': s for i, s in enumerate(active_sources)}
                active_recipes = db.execute(text(f"""
                    SELECT COUNT(*) FROM found_recipes
                    WHERE source_name IN ({placeholders})
                """), params).scalar() or 0
            else:
                active_recipes = 0

            # Get total recipe count (for reference)
            total_recipes = db.execute(text("""
                SELECT COUNT(*) FROM found_recipes
            """)).scalar() or 0

            # Count how many active sources have been synced in last 30 days
            if active_sources:
                placeholders = ', '.join([f':s{i}' for i in range(len(active_sources))])
                params = {f's{i}': s for i, s in enumerate(active_sources)}
                synced_sources = db.execute(text(f"""
                    SELECT COUNT(DISTINCT source_name)
                    FROM found_recipes
                    WHERE source_name IN ({placeholders})
                    AND scraped_at > NOW() - INTERVAL '30 days'
                """), params).scalar() or 0
            else:
                synced_sources = 0

            # Get last sync timestamp
            last_sync = db.execute(text("""
                SELECT MAX(scraped_at)
                FROM found_recipes
                WHERE scraped_at > NOW() - INTERVAL '30 days'
            """)).scalar()

            return JSONResponse({
                "success": True,
                "source_count": f"{active_source_count}/{total_source_count}",
                "active_source_count": active_source_count,
                "total_source_count": total_source_count,
                "total_recipes": active_recipes,
                "all_recipes": total_recipes,
                "synced_sources": synced_sources,
                "synced_last_month": synced_sources == active_source_count and active_source_count > 0,
                "last_sync_at": last_sync.isoformat() if last_sync else None
            })
    except Exception as e:
        logger.error(f"Error fetching recipe status: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e),
            "source_count": "0/0",
            "active_source_count": 0,
            "total_source_count": 0,
            "total_recipes": 0,
            "all_recipes": 0,
            "synced_sources": 0,
            "synced_last_month": False
        })


# ==================== SETUP GUIDE ====================

@router.get("/api/setup/status")
def get_setup_status(request: Request):
    """Check which setup steps are complete for the getting started guide."""
    try:
        # Check if the hostname the user is connecting via is in ALLOWED_HOSTS
        hosts = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1')
        configured_hosts = {h.strip() for h in hosts.split(',') if h.strip()}

        # Detect the hostname the user is connecting via (from Host header)
        request_host = request.headers.get("host", "")
        # Strip port if present (e.g. "docker1:20080" -> "docker1")
        detected_host = request_host.split(":")[0] if request_host else ""

        # Step is complete only if the current hostname is already allowed
        hosts_configured = detected_host in configured_hosts

        with get_db_session() as db:
            # Check delivery address and guide dismissed state
            prefs = db.execute(text(
                "SELECT delivery_street_address, ui_preferences FROM user_preferences LIMIT 1"
            )).fetchone()
            has_address = bool(prefs and prefs[0])
            ui_prefs = prefs[1] if prefs and prefs[1] else {}
            dismissed = ui_prefs.get('setup_guide_dismissed', False)

            # Check if any recipes exist
            has_recipes = db.execute(text(
                "SELECT 1 FROM found_recipes LIMIT 1"
            )).fetchone() is not None

            # Check if any offers exist
            has_offers = db.execute(text(
                "SELECT 1 FROM offers LIMIT 1"
            )).fetchone() is not None

        response = {
            "success": True,
            "steps": {
                "allowed_hosts": hosts_configured,
                "delivery_address": has_address,
                "recipes": has_recipes,
                "offers": has_offers
            },
            "guide_dismissed": dismissed
        }

        # Include detected hostname if ALLOWED_HOSTS step is incomplete
        if not hosts_configured and detected_host:
            response["detected_host"] = detected_host

        return JSONResponse(response)
    except Exception as e:
        logger.error(f"Error checking setup status: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)})


# ==================== HEALTH CHECK ====================

@router.get("/health")
@limiter.exempt
def health_check():
    """Health check endpoint for Docker and external monitoring (Uptime Kuma)."""
    # Check critical components
    components = {
        "plugin_system": PLUGIN_SYSTEM_AVAILABLE,
        "scheduler": SCHEDULER_AVAILABLE,
        "recipe_scrapers": RECIPE_SCRAPERS_AVAILABLE,
    }

    # Check database connectivity
    try:
        with get_db_session() as db:
            db.execute(text("SELECT 1")).fetchone()
            components["database"] = True
    except Exception as e:
        logger.warning(f"Health check: database unreachable: {e}")
        components["database"] = False

    all_healthy = all(components.values())

    response = {
        "status": "healthy" if all_healthy else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0",
        "components": components
    }

    # Return 503 if unhealthy so Docker/Uptime Kuma marks as unhealthy
    status_code = 200 if all_healthy else 503
    return JSONResponse(response, status_code=status_code)
