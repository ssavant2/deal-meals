"""
Image auto-download utility.

Extracted from routers/images.py to avoid cross-router coupling.
Called by routers/recipes.py and routers/websockets.py after scraping.
"""

import asyncio
from sqlalchemy import text
from loguru import logger

from database import get_db_session
from state import image_download_state


async def trigger_auto_download_if_enabled() -> bool:
    """
    Check if auto-download is enabled and start image download if so.

    Call this after recipe scraping completes to automatically download
    images for newly scraped recipes.

    Returns:
        True if auto-download was triggered, False otherwise
    """
    try:
        with get_db_session() as db:
            prefs = db.execute(text(
                "SELECT auto_download FROM image_preferences LIMIT 1"
            )).fetchone()

            if prefs and prefs.auto_download:
                # Check if download is already running
                if image_download_state.get("running"):
                    logger.info("Auto-download: skipped, download already in progress")
                    return False

                logger.info("Auto-download enabled, starting image download task")

                # Lazy import to avoid circular dependency
                from routers.images import _download_images_task, IMAGE_BATCH_PAUSE_AUTO

                # Set state before creating task (same as start_image_download endpoint)
                image_download_state.clear()
                image_download_state.update({
                    "running": True,
                    "total": 0,
                    "processed": 0,
                    "downloaded": 0,
                    "skipped": 0,
                    "errors": 0,
                    "status": "running",
                    "message_key": "config.images_starting",
                    "message_params": {},
                    "batch_pause": IMAGE_BATCH_PAUSE_AUTO
                })

                asyncio.create_task(_download_images_task(batch_pause=IMAGE_BATCH_PAUSE_AUTO))
                return True
    except Exception as e:
        logger.warning(f"Could not check/start auto-download: {e}")

    return False
