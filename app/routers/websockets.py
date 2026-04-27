"""
WebSocket Routes.

This router handles all WebSocket connections:
- /ws/scrape/{store} - Store offer scraping with progress
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime, timezone
import asyncio
from sqlalchemy import text
from loguru import logger

from database import get_db_session
from utils.errors import friendly_error
from utils.security import ALLOWED_ORIGINS
from utils.store_scrape_config import build_store_scrape_config_context

# Import shared state helpers (async-safe, with locking)
from state import (
    update_active_scrape, get_active_scrape,
    delete_active_scrape, try_start_active_scrape,
    set_scrape_task, get_scrape_task, delete_scrape_task
)

# Import plugin system
try:
    from scrapers.stores import get_store, normalize_store_scrape_result
    PLUGIN_SYSTEM_AVAILABLE = True
except ImportError:
    PLUGIN_SYSTEM_AVAILABLE = False


router = APIRouter(tags=["websockets"])

# Global WebSocket connection limit (prevents memory exhaustion)
MAX_WS_CONNECTIONS = 3
_active_ws_connections = 0


# ==================== HELPER FUNCTIONS ====================

async def scrape_store_offers(websocket: WebSocket, store_name: str, owner_id: str):
    """Scrape offers from a store."""
    store_id = store_name.lower()

    running_sid = await try_start_active_scrape(store_id, {
        "started_at": datetime.now(timezone.utc),
        "est_time": 300,
        "progress": 0,
        "message_key": "ws.fetching_offers",
        "message_params": {"store": store_name},
        "source": "manual",
        "owner_id": owner_id,
    })
    if running_sid:
        running_store = running_sid.capitalize()
        await websocket.send_json({
            "status": "error",
            "message_key": "ws.store_busy",
            "message_params": {"store": running_store}
        })
        return False

    # Helper to update active scrape tracking (async-safe)
    async def update_scrape_status(progress: int, message_key: str, message_params: dict = None, est_time: int = None):
        existing = await get_active_scrape(store_id) or {}
        await update_active_scrape(store_id, {
            "started_at": existing.get("started_at") or datetime.now(timezone.utc),
            "est_time": est_time or existing.get("est_time", 300),  # Default 5 min
            "progress": progress,
            "message_key": message_key,
            "message_params": message_params or {}
        })

    await websocket.send_json({
        "status": "starting",
        "message_key": "ws.fetching_offers",
        "message_params": {"store": store_name},
        "progress": 0
    })

    # Track scrape start time for duration measurement
    scrape_start_time = datetime.now(timezone.utc)
    db_store_id = None  # Will be set when we query the DB

    try:
        # NEW: Try using plugin first
        if PLUGIN_SYSTEM_AVAILABLE:
            try:
                store_plugin = get_store(store_id)

                # Default estimated time (5 min) - will be overridden by stored duration if available
                est_time = 300  # 5 minutes default
                plugin_est_time = getattr(store_plugin, 'estimated_scrape_time', 300)

                with get_db_session() as db:
                    config_context = build_store_scrape_config_context(
                        db,
                        store_id,
                        store_name=store_plugin.config.name,
                    )

                    if not config_context.valid:
                        logger.warning(
                            f"Store scrape blocked for {store_name}: "
                            f"{config_context.message_key} {config_context.message_params}"
                        )
                        await websocket.send_json({
                            "status": "error",
                            "message_key": config_context.message_key,
                            "message_params": config_context.message_params,
                        })
                        await delete_active_scrape(store_id)
                        return False

                    credentials = config_context.credentials
                    db_store_id = config_context.db_store_id
                    location_type = config_context.location_type

                    if credentials.get('postal_code'):
                        logger.debug(
                            f"Using delivery address for e-handel: {credentials.get('delivery_street')}, "
                            f"{credentials['postal_code']} {credentials.get('delivery_city')}"
                        )

                    # Use stored duration for current location_type, otherwise plugin default
                    if location_type == 'butik':
                        stored_duration = config_context.last_scrape_duration_butik
                    else:
                        stored_duration = config_context.last_scrape_duration_ehandel

                    logger.debug(
                        f"Duration lookup for {store_name}: location_type={location_type}, "
                        f"ehandel_dur={config_context.last_scrape_duration_ehandel}, "
                        f"butik_dur={config_context.last_scrape_duration_butik}, using={stored_duration}"
                    )

                    # Use stored duration if available (check for None, not just falsy)
                    if stored_duration is not None and stored_duration > 0:
                        est_time = stored_duration
                        logger.info(f"Using stored duration for {store_name} ({location_type}): {est_time}s")
                    else:
                        est_time = plugin_est_time
                        logger.info(f"No stored duration for {store_name} ({location_type}), using default: {est_time}s")

                await update_scrape_status(0, "ws.fetching_products", est_time=est_time)

                await websocket.send_json({
                    "status": "scraping",
                    "message_key": "ws.fetching_products",
                    "progress": 0,
                    "simulate_progress": True,
                    "max_time": est_time
                })

                # Scrape with plugin (wrapped in task for cancellation support)
                scrape_task = asyncio.create_task(
                    store_plugin.scrape_offers(credentials)
                )
                await set_scrape_task(store_id, scrape_task)
                try:
                    raw_scrape_result = await scrape_task
                except asyncio.CancelledError:
                    logger.info(f"Scrape cancelled by user: {store_name}")
                    await delete_active_scrape(store_id)
                    try:
                        await websocket.send_json({
                            "status": "cancelled",
                            "message_key": "stores.scrape_cancelled",
                            "progress": 0
                        })
                    except Exception:
                        pass
                    return False
                finally:
                    await delete_scrape_task(store_id)

                scrape_result = normalize_store_scrape_result(
                    raw_scrape_result,
                    store_name=store_name,
                )
                products = scrape_result.products

                if not scrape_result.should_replace_offers:
                    logger.warning(
                        f"Store scrape for {store_name} did not produce replaceable data "
                        f"(status={scrape_result.status}, reason={scrape_result.reason}); "
                        "keeping existing offers and cache"
                    )
                    await delete_active_scrape(store_id)
                    try:
                        message_params = {"store": store_name}
                        message_params.update(scrape_result.message_params or {})
                        await websocket.send_json({
                            "status": "error",
                            "message_key": scrape_result.message_key or "ws.fetch_no_products_stale",
                            "message_params": message_params,
                            "progress": 100
                        })
                    except Exception:
                        logger.debug(f"WebSocket closed before empty-result notice for {store_id}")
                    return False

                scrape_meta = getattr(store_plugin, '_scrape_meta', None)
                if scrape_result.is_empty_success:
                    save_key = "ws.clearing_empty_offers"
                    save_params = {"store": store_name}
                elif scrape_meta and scrape_meta.get('variant_count', 0) > 0:
                    save_key = "ws.saving_products_with_variants"
                    save_params = {"base": scrape_meta['base_count'], "variants": scrape_meta['variant_count']}
                else:
                    save_key = "ws.saving_products"
                    save_params = {"count": len(products)}
                await update_scrape_status(70, save_key, save_params)

                # Try to notify client, but continue even if WebSocket is closed
                try:
                    await websocket.send_json({
                        "status": "saving",
                        "message_key": save_key,
                        "message_params": save_params,
                        "progress": 70
                    })
                except Exception:
                    # WebSocket closed - continue with save anyway
                    logger.debug(f"WebSocket closed during save notification for {store_id}")

                # Ensure store exists in DB (auto-registers new stores)
                from db_saver import ensure_store_exists, save_offers, clear_offers_for_empty_scrape
                plugin_config = store_plugin.config
                await asyncio.to_thread(ensure_store_exists, plugin_config.id, plugin_config.name, plugin_config.url)

                # Save to DB using store_id (ASCII lowercase, matched via store_type column)
                # This avoids issues with non-ASCII display names like "Hemköp"
                if scrape_result.is_empty_success:
                    stats = await asyncio.to_thread(
                        clear_offers_for_empty_scrape,
                        store_id,
                        scrape_result.reason,
                    )
                else:
                    stats = await asyncio.to_thread(save_offers, store_id, products)

                if stats.get('stale_existing_offers') or stats.get('created', 0) <= 0:
                    if scrape_result.is_empty_success and stats.get('verified_empty'):
                        pass
                    else:
                        logger.warning(
                            f"No valid products were saved for {store_name}; "
                            "keeping existing offers and cache"
                        )
                        await delete_active_scrape(store_id)
                        try:
                            await websocket.send_json({
                                "status": "error",
                                "message_key": "ws.fetch_no_products_stale",
                                "message_params": {"store": store_name},
                                "progress": 100
                            })
                        except Exception:
                            logger.debug(f"WebSocket closed before stale-result notice for {store_id}")
                        return False

                # Calculate and save actual scrape duration for future progress estimation
                # Use max(1, ...) to ensure at least 1 second (very fast scrapes shouldn't be 0)
                scrape_duration = max(1, int((datetime.now(timezone.utc) - scrape_start_time).total_seconds()))
                location_type = credentials.get('location_type', 'ehandel')
                display_count = stats['created']
                if scrape_meta and scrape_meta.get('variant_count', 0) > 0:
                    display_count = int(scrape_meta.get('base_count') or display_count)
                try:
                    with get_db_session() as db:
                        # Get or create db_store_id if not already set
                        if not db_store_id:
                            store_result = db.execute(text(
                                "SELECT id FROM stores WHERE store_type = :store_type"
                            ), {"store_type": store_id}).mappings().fetchone()
                            if store_result:
                                db_store_id = store_result['id']

                        if db_store_id:
                            # Update scrape duration on stores table
                            # Uses CASE to avoid f-string column interpolation
                            db.execute(text("""
                                UPDATE stores SET
                                    last_scrape_duration_butik = CASE WHEN :loc = 'butik' THEN :duration ELSE last_scrape_duration_butik END,
                                    last_scrape_duration_ehandel = CASE WHEN :loc != 'butik' THEN :duration ELSE last_scrape_duration_ehandel END,
                                    config = jsonb_set(
                                        COALESCE(config, '{}'::jsonb),
                                        CASE WHEN :loc = 'butik'
                                             THEN ARRAY['last_display_count_butik']
                                             ELSE ARRAY['last_display_count_ehandel']
                                        END,
                                        to_jsonb(CAST(:display_count AS int)),
                                        true
                                    ),
                                    last_scrape_at = NOW()
                                WHERE id = :store_id
                            """), {
                                "store_id": db_store_id,
                                "duration": scrape_duration,
                                "loc": location_type,
                                "display_count": int(display_count),
                            })
                            db.commit()
                            logger.info(f"Saved scrape duration for {store_name} ({location_type}): {scrape_duration}s (store_id={db_store_id})")
                except Exception as e:
                    logger.warning(f"Failed to save scrape duration for {store_name}: {e}")

                # Build location display name for success message
                location_type = credentials.get('location_type', 'ehandel')
                if location_type == 'ehandel':
                    location_display = credentials.get('ehandel_store_name') or 'E-handel'
                else:
                    location_display = credentials.get('location_name') or 'Butik'

                # Notify SSE subscribers (home page) that cache was rebuilt
                from state import event_bus
                event_bus.publish({
                    "type": "cache_rebuilt",
                    "source": location_display,
                    "count": stats['created'],
                })

                # Try to send completion via WebSocket
                if scrape_result.is_empty_success:
                    complete_key = "ws.fetch_empty_success"
                    complete_params = {"store": store_name}
                elif scrape_meta and scrape_meta.get('variant_count', 0) > 0:
                    complete_key = "ws.fetch_complete_with_variants"
                    complete_params = {"base": scrape_meta['base_count'], "variants": scrape_meta['variant_count']}
                else:
                    complete_key = "ws.fetch_complete"
                    complete_params = {"count": stats['created']}
                try:
                    completion_msg = {
                        "status": "complete",
                        "message_key": complete_key,
                        "message_params": complete_params,
                        "progress": 100,
                        "count": stats['created'],
                        "location_name": location_display
                    }
                    if scrape_meta and scrape_meta.get('variant_count', 0) > 0:
                        completion_msg["base"] = scrape_meta['base_count']
                        completion_msg["variants"] = scrape_meta['variant_count']
                    await websocket.send_json(completion_msg)
                    # WebSocket successfully sent - clear from active_scrapes
                    await delete_active_scrape(store_id)
                except Exception as _ws_err:
                    # WebSocket closed (user switched tabs/changed theme)
                    # Keep completed state for polling clients
                    logger.info(f"WebSocket closed for {store_id}, saving completed state for polling (count={stats['created']})")
                    polling_state = {
                        "active": False,
                        "completed": True,
                        "progress": 100,
                        "message_key": complete_key,
                        "message_params": complete_params,
                        "count": stats['created'],
                        "location_name": location_display,
                        "completed_at": datetime.now(timezone.utc)
                    }
                    if scrape_meta and scrape_meta.get('variant_count', 0) > 0:
                        polling_state["base"] = scrape_meta['base_count']
                        polling_state["variants"] = scrape_meta['variant_count']
                    await update_active_scrape(store_id, polling_state)
                    completed = await get_active_scrape(store_id)
                    logger.debug(f"Saved completed state: {completed}")

                return True

            except KeyError:
                # Plugin not found - clear tracking
                await delete_active_scrape(store_id)
                await websocket.send_json({
                    "status": "error",
                    "message_key": "ws.plugin_not_found",
                    "message_params": {"name": store_name}
                })
                return False

        # Plugin system not available - clear tracking
        await delete_active_scrape(store_id)
        await websocket.send_json({
            "status": "error",
            "message_key": "ws.plugin_not_available"
        })
        return False

    except Exception as e:
        # Clear tracking on exception
        await delete_active_scrape(store_id)
        await websocket.send_json({
            "status": "error",
            "message_key": friendly_error(e)
        })
        logger.error(f"Fetch error: {e}")
        return False


# ==================== WEBSOCKET ROUTES ====================

@router.websocket("/ws/scrape/{store}")
async def websocket_scrape(websocket: WebSocket, store: str):
    """WebSocket endpoint to fetch offers."""
    global _active_ws_connections
    scrape_owner_id = f"manual:{store.lower()}:{id(websocket)}"

    # Validate Origin header before accepting connection
    origin = websocket.headers.get("origin", "")
    if not origin or origin not in ALLOWED_ORIGINS:
        logger.warning(f"WebSocket rejected: Origin '{origin}' not allowed for /ws/scrape/{store}")
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    if _active_ws_connections >= MAX_WS_CONNECTIONS:
        logger.warning(f"WebSocket rejected: {_active_ws_connections} active connections (max {MAX_WS_CONNECTIONS})")
        await websocket.accept()
        await websocket.send_json({"status": "error", "message_key": "error.rate_limited"})
        await websocket.close()
        return

    _active_ws_connections += 1
    await websocket.accept()

    try:
        store_name = store.capitalize()
        success = await scrape_store_offers(websocket, store_name, scrape_owner_id)

        if success:
            try:
                await websocket.send_json({
                    "status": "done",
                    "message_key": "ws.fetch_done"
                })
            except Exception:
                pass  # Client already closed connection

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket scrape error: {e}")
        try:
            await websocket.send_json({
                "status": "error",
                "message_key": friendly_error(e)
            })
        except Exception as exc:
            logger.debug(f"WebSocket already closed: {exc}")
    finally:
        _active_ws_connections -= 1
        # Always clean up scrape state — prevents "stuck" scrapes
        # when WebSocket disconnects unexpectedly (closed tab, network drop).
        # If scrape completed successfully, keep state briefly so polling
        # clients (tab switch/theme change) can read the result.
        store_id = store.lower()
        scrape = await get_active_scrape(store_id)
        owns_active_scrape = bool(scrape and scrape.get("owner_id") == scrape_owner_id)
        task = await get_scrape_task(store_id) if owns_active_scrape else None
        if task and not task.done():
            task.cancel()
            logger.info(f"Cancelled running scrape task for {store_id} (WebSocket closed)")
            await delete_active_scrape(store_id)
        else:
            # Scrape finished (or never started) — only delete if not completed
            if owns_active_scrape and scrape and not scrape.get("completed"):
                await delete_active_scrape(store_id)
            # Completed scrapes are cleaned up by get_scrape_status() after 60s
        if owns_active_scrape:
            await delete_scrape_task(store_id)
        try:
            await websocket.close()
        except Exception as exc:
            logger.debug(f"WebSocket already closed: {exc}")
