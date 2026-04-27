"""
Preferences API Routes.

This router handles user preference endpoints:
- /api/preferences/delivery-address - Delivery address (GET/POST)
- /api/ui-preferences - UI preferences like sort settings (GET/POST)
"""

import json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from loguru import logger

from database import get_db_session
from utils.errors import friendly_error


router = APIRouter(prefix="/api", tags=["preferences"])


# ==================== DELIVERY ADDRESS ====================

@router.get("/preferences/delivery-address")
def get_delivery_address():
    """API endpoint to fetch delivery address."""

    try:
        with get_db_session() as db:
            row = db.execute(text("""
                SELECT delivery_street_address, delivery_postal_code, delivery_city
                FROM user_preferences LIMIT 1
            """)).mappings().fetchone()

            if row:
                return JSONResponse({
                    "success": True,
                    "street_address": row['delivery_street_address'] or "",
                    "postal_code": row['delivery_postal_code'] or "",
                    "city": row['delivery_city'] or ""
                })
            else:
                return JSONResponse({
                    "success": True,
                    "street_address": "",
                    "postal_code": "",
                    "city": ""
                })

    except Exception as e:
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e),
            "street_address": "",
            "postal_code": "",
            "city": ""
        })


@router.post("/preferences/delivery-address")
async def save_delivery_address(request: Request):
    """API endpoint to save delivery address."""

    try:
        data = await request.json()

        street_address = data.get('street_address', '').strip()
        postal_code = data.get('postal_code', '').strip()
        city = data.get('city', '').strip()

        # Basic validation
        if not street_address:
            return JSONResponse({
                "success": False,
                "message_key": "preferences.street_required"
            }, status_code=422)

        if not postal_code:
            return JSONResponse({
                "success": False,
                "message_key": "preferences.postal_required"
            }, status_code=422)

        if not city:
            return JSONResponse({
                "success": False,
                "message_key": "preferences.city_required"
            }, status_code=422)

        # Update in database
        with get_db_session() as db:
            db.execute(text("""
                INSERT INTO user_preferences (delivery_street_address, delivery_postal_code, delivery_city)
                VALUES (:street_address, :postal_code, :city)
                ON CONFLICT (singleton_key) DO UPDATE SET
                    delivery_street_address = EXCLUDED.delivery_street_address,
                    delivery_postal_code = EXCLUDED.delivery_postal_code,
                    delivery_city = EXCLUDED.delivery_city,
                    updated_at = NOW()
            """), {
                "street_address": street_address,
                "postal_code": postal_code,
                "city": city
            })

            db.commit()

        return JSONResponse({
            "success": True,
            "message_key": "preferences.address_saved",
            "message_params": {"address": f"{street_address}, {postal_code} {city}"}
        })

    except Exception as e:
        logger.error(f"Failed to save delivery address: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        }, status_code=500)


# ==================== UI PREFERENCES ====================

@router.get("/ui-preferences")
def get_ui_preferences():
    """Get UI preferences (sort settings, etc.)."""
    try:
        with get_db_session() as db:
            row = db.execute(text("""
                SELECT ui_preferences FROM user_preferences LIMIT 1
            """)).mappings().fetchone()

            prefs = row['ui_preferences'] if row and row['ui_preferences'] else {}
            return JSONResponse({"success": True, "preferences": prefs})
    except Exception as e:
        logger.warning(f"Could not load UI preferences: {e}")
        return JSONResponse({"success": True, "preferences": {}})


@router.post("/ui-preferences")
async def save_ui_preferences(request: Request):
    """Save UI preferences (partial update - merges with existing)."""
    try:
        data = await request.json()

        with get_db_session() as db:
            # Get existing preferences
            row = db.execute(text("""
                SELECT ui_preferences FROM user_preferences LIMIT 1
            """)).mappings().fetchone()

            existing = row['ui_preferences'] if row and row['ui_preferences'] else {}

            # Merge with new data
            existing.update(data)

            db.execute(text("""
                INSERT INTO user_preferences (ui_preferences)
                VALUES (:prefs)
                ON CONFLICT (singleton_key) DO UPDATE SET
                    ui_preferences = EXCLUDED.ui_preferences,
                    updated_at = NOW()
            """), {"prefs": json.dumps(existing)})

            db.commit()

        return JSONResponse({"success": True})
    except Exception as e:
        logger.error(f"Failed to save UI preferences: {e}")
        return JSONResponse({"success": False, "message_key": friendly_error(e)}, status_code=500)
