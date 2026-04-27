"""
Store API Routes.

This router handles all store-related API endpoints:
- /api/stores - List stores
- /api/store-config - Store configuration (location info)
- /api/stores/{store_id}/config-fields - Config field definitions
- /api/stores/{store_id}/config - Store configuration (GET/POST)
- /api/stores/{store_id}/locations - Location search
- /api/stores/{store_id}/ehandel-stores - E-handel stores
- /api/scrape-status/{store_id} - Scrape status
"""

import json
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text, func
from loguru import logger

from database import get_db_session
from models import Store
from utils.errors import friendly_error
from state import (
    get_active_scrape, get_running_scrape, update_active_scrape,
    delete_active_scrape, get_scrape_task
)

# Import plugin system
try:
    from scrapers.stores import get_enabled_stores, get_all_stores, get_store
    PLUGIN_SYSTEM_AVAILABLE = True
except ImportError:
    PLUGIN_SYSTEM_AVAILABLE = False


router = APIRouter(prefix="/api", tags=["stores"])


# ==================== HELPER FUNCTIONS ====================

def get_store_status(store_name: str = 'Willys'):
    """Fetch store config/location info."""
    with get_db_session() as db:
        store = db.query(Store).filter(func.lower(Store.name) == store_name.lower()).first()

        if not store:
            return {"success": False, "message_key": "stores.not_found"}

        config = store.config if store.config else {}

        return {
            "success": True,
            "configured": True,  # Always true — config always exists
            "location_type": config.get("location_type") if isinstance(config, dict) else None,
            "location_id": config.get("location_id") if isinstance(config, dict) else None,
            "location_name": config.get("location_name") if isinstance(config, dict) else None,
            "ehandel_store_name": config.get("ehandel_store_name") if isinstance(config, dict) else None
        }


def _get_or_create_store_record(db, store_id: str):
    """Fetch a store row, auto-registering plugin-backed stores when missing."""
    store_record = db.query(Store).filter(Store.name.ilike(store_id)).first()

    if not store_record:
        store_record = db.query(Store).filter(Store.store_type == store_id).first()

    if store_record:
        return store_record

    if not PLUGIN_SYSTEM_AVAILABLE:
        return None

    try:
        plugin = get_store(store_id)
    except Exception:
        return None

    store_record = Store(
        name=plugin.config.name,
        store_type=plugin.config.id,
        url=plugin.config.url,
        config={},
    )
    db.add(store_record)
    db.flush()
    logger.info(
        f"Auto-registered missing store row for {plugin.config.name} "
        f"({plugin.config.id}) during config save"
    )
    return store_record


def _active_scrape_response(scrape: dict, store_id: str | None = None) -> dict:
    """Build the public response for an active store scrape."""
    started_at = scrape.get("started_at")
    est_time = max(1, int(scrape.get("est_time", 300) or 300))
    saved_progress = float(scrape.get("progress", 0) or 0)

    if isinstance(started_at, datetime):
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        time_progress = min(95, (elapsed / est_time) * 95)
        progress = max(saved_progress, time_progress)
    else:
        progress = saved_progress

    response = {
        "active": True,
        "completed": False,
        "progress": int(progress),
        "est_time": est_time,
        "source": scrape.get("source"),
        "message_key": scrape.get("message_key", "stores.fetching_offers"),
        "message_params": scrape.get("message_params", {}),
    }
    if store_id:
        response["store_id"] = store_id
    return response


# ==================== API ROUTES ====================

@router.get("/store-config")
def store_config(store: str):
    """API endpoint to fetch store configuration (location info)."""
    # Store IDs in the frontend are ASCII-only; DB display names may contain
    # market-specific characters.
    store_name_map = {
        'hemkop': 'Hemköp',
    }
    store_name = store_name_map.get(store.lower(), store.capitalize())
    return JSONResponse(get_store_status(store_name))


@router.get("/stores")
def list_stores():
    """API endpoint - list all stores from plugin system."""
    if not PLUGIN_SYSTEM_AVAILABLE:
        return JSONResponse({"message_key": "stores.plugin_not_available", "stores": []})

    try:
        stores = get_enabled_stores()
        return JSONResponse({"success": True, "stores": [
            {
                "id": s.config.id,
                "name": s.config.name,
                "logo": s.config.logo,
                "color": s.config.color,
                "url": s.config.url,
                "enabled": s.config.enabled,
                "has_credentials": s.config.has_credentials,
                "description": s.config.description
            }
            for s in stores
        ]})
    except Exception as e:
        return JSONResponse({"success": False, "message_key": friendly_error(e), "stores": []})


@router.get("/stores/{store_id}/config-fields")
def get_store_config_fields(store_id: str):
    """Get configuration field definitions for a store plugin."""
    try:
        store = get_store(store_id)
        if not store:
            return JSONResponse({"success": False, "message_key": "stores.not_found"}, status_code=404)

        fields = store.get_config_fields()
        return JSONResponse({
            "success": True,
            "store_id": store_id,
            "fields": [f.to_dict() for f in fields]
        })
    except Exception as e:
        logger.error(f"Error getting config fields for {store_id}: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.get("/stores/{store_id}/config")
def get_store_config(store_id: str):
    """Get saved configuration for a store."""
    try:
        with get_db_session() as db:
            store_record = _get_or_create_store_record(db, store_id)

            if not store_record:
                return JSONResponse({"success": True, "config": {}})

            config = store_record.config if store_record.config else {}
            return JSONResponse({"success": True, "config": config})

    except Exception as e:
        logger.error(f"Error getting config for {store_id}: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.post("/stores/{store_id}/config")
async def save_store_config(store_id: str, request: Request):
    """Save configuration for a store."""
    try:
        data = await request.json()
        config = data.get('config', data)

        with get_db_session() as db:
            store_record = _get_or_create_store_record(db, store_id)

            if not store_record:
                return JSONResponse({"success": False, "message_key": "stores.not_found"}, status_code=404)

            db.execute(text("""
                UPDATE stores
                SET config = :config,
                    updated_at = NOW()
                WHERE id = :store_id
            """), {
                "config": json.dumps(config),
                "store_id": str(store_record.id)
            })
            db.commit()

        return JSONResponse({"success": True, "message_key": "stores.config_saved"})

    except Exception as e:
        logger.error(f"Error saving config for {store_id}: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)


@router.get("/stores/{store_id}/locations")
async def search_store_locations(store_id: str, q: str = "", location_type: str = ""):
    """Search for store locations using plugin's search_locations method."""
    try:
        store = get_store(store_id)
        if not store:
            return JSONResponse({"success": False, "message_key": "stores.not_found"}, status_code=404)

        if not q or len(q) < 2:
            return JSONResponse({"success": True, "locations": [], "message_key": "stores.query_too_short"})

        postal_code = None
        if location_type == "ehandel":
            with get_db_session() as db:
                result = db.execute(text(
                    "SELECT delivery_postal_code FROM user_preferences LIMIT 1"
                )).mappings().fetchone()
                if result and result['delivery_postal_code']:
                    postal_code = result['delivery_postal_code']
                else:
                    return JSONResponse({
                        "success": False,
                        "message_key": "stores.no_delivery_address",
                        "locations": []
                    })

        if postal_code:
            locations = await store.search_locations(q, postal_code=postal_code)
        else:
            locations = await store.search_locations(q)

        mapped = [
            {
                "storeId": loc.get("id"),
                "displayName": loc.get("name"),
                "address": loc.get("address", ""),
                "type": loc.get("type", "butik")
            }
            for loc in locations
        ]

        return JSONResponse({
            "success": True,
            "stores": mapped,
            "locations": mapped,
            "count": len(mapped)
        })

    except Exception as e:
        logger.error(f"Error searching locations for {store_id}: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e), "locations": []}, status_code=500)


@router.get("/stores/{store_id}/ehandel-stores")
async def get_ehandel_stores(store_id: str):
    """Get e-commerce stores that deliver to user's postal code."""
    try:
        store = get_store(store_id)
        if not store:
            return JSONResponse({"success": False, "message_key": "stores.not_found"}, status_code=404)

        if not hasattr(store, '_search_ehandel_stores'):
            return JSONResponse({"success": False, "message_key": "stores.ehandel_not_supported"}, status_code=400)

        with get_db_session() as db:
            result = db.execute(text(
                "SELECT delivery_postal_code FROM user_preferences LIMIT 1"
            )).mappings().fetchone()

            if not result or not result['delivery_postal_code']:
                return JSONResponse({
                    "success": False,
                    "message_key": "stores.no_delivery_address",
                    "stores": []
                })

            postal_code = result['delivery_postal_code']

        stores = await store._search_ehandel_stores(postal_code, "")

        mapped = [
            {"id": s.get("id"), "name": s.get("name"), "address": s.get("address", "")}
            for s in stores
        ]

        return JSONResponse({
            "success": True,
            "stores": mapped,
            "postal_code": postal_code,
            "count": len(mapped)
        })

    except Exception as e:
        logger.error(f"Error getting e-handel stores for {store_id}: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e), "stores": []}, status_code=500)


@router.get("/scrape-status")
async def get_global_scrape_status():
    """Check if any store scrape is currently running."""
    scrape = await get_running_scrape()
    if not scrape:
        return JSONResponse({"active": False, "completed": False})

    return JSONResponse(_active_scrape_response(
        scrape,
        store_id=scrape.get("store_id"),
    ))


@router.get("/scrape-status/{store_id}")
async def get_scrape_status(store_id: str):
    """Check if a store scrape is currently running or recently completed."""
    store_id = store_id.lower()
    scrape = await get_active_scrape(store_id)
    if scrape:
        if scrape.get("completed"):
            count = scrape.get("count", 0)
            result = {
                "active": False,
                "completed": True,
                "progress": 100,
                "message_key": scrape.get("message_key"),
                "message_params": scrape.get("message_params", {}),
                "count": count
            }
            if not scrape.get("read_at"):
                await update_active_scrape(store_id, {"read_at": datetime.now(timezone.utc)})
            elif (datetime.now(timezone.utc) - scrape["read_at"]).total_seconds() > 60:
                await delete_active_scrape(store_id)
            return JSONResponse(result)

        return JSONResponse(_active_scrape_response(scrape, store_id=store_id))

    return JSONResponse({"active": False, "completed": False})


@router.post("/scrape/{store_id}/cancel")
async def cancel_scrape(store_id: str):
    """Cancel a running store scrape."""
    store_id = store_id.lower()

    task = await get_scrape_task(store_id)
    if not task:
        return JSONResponse(
            {"success": False, "message_key": "stores.no_active_scrape"},
            status_code=404
        )

    if task.done():
        return JSONResponse(
            {"success": False, "message_key": "stores.no_active_scrape"},
            status_code=404
        )

    task.cancel()
    logger.info(f"Cancellation requested for store scrape: {store_id}")
    return JSONResponse({"success": True, "message_key": "stores.scrape_cancelling"})
