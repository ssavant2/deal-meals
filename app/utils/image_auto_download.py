"""
Image auto-download utility.

Extracted from routers/images.py to avoid cross-router coupling.
Called by routers/recipes.py and routers/websockets.py after scraping.
"""

import asyncio
from typing import Iterable

from sqlalchemy import text
from loguru import logger

from database import get_db_session
from state import image_download_state, try_start_image_download


def _normalize_text_values(values: Iterable[object] | None) -> list[str] | None:
    if values is None:
        return None

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text_value = str(value).strip()
        if not text_value or text_value in seen:
            continue
        normalized.append(text_value)
        seen.add(text_value)
    return normalized


async def trigger_auto_download_if_enabled(
    *,
    recipe_ids: Iterable[object] | None = None,
    source_names: Iterable[object] | None = None,
) -> bool:
    """
    Check if auto-download is enabled and start image download if so.

    Call this after recipe scraping completes to automatically download
    images for newly scraped recipes. When source_names is provided, the
    source backlog is included too; manual image downloads remain global.

    Returns:
        True if auto-download was triggered, False otherwise
    """
    scoped_recipe_ids = _normalize_text_values(recipe_ids)
    scoped_source_names = _normalize_text_values(source_names)
    scoped = recipe_ids is not None or source_names is not None
    if scoped and not scoped_recipe_ids and not scoped_source_names:
        logger.info("Auto-download: skipped, no recipe ids or source names")
        return False

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

                if not scoped:
                    logger.info("Auto-download enabled, starting global image download task")
                else:
                    parts = []
                    if scoped_source_names:
                        parts.append(f"{len(scoped_source_names)} sources")
                    if scoped_recipe_ids:
                        parts.append(f"{len(scoped_recipe_ids)} recipes")
                    logger.info(
                        "Auto-download enabled, starting scoped image download task "
                        f"({', '.join(parts)})"
                    )

                # Lazy import to avoid circular dependency
                from routers.images import _download_images_task, IMAGE_BATCH_PAUSE_AUTO

                # Set state before creating task (same as start_image_download endpoint)
                started = await try_start_image_download({
                    "running": True,
                    "total": 0,
                    "processed": 0,
                    "downloaded": 0,
                    "skipped": 0,
                    "errors": 0,
                    "status": "running",
                    "message_key": "config.images_starting",
                    "message_params": {},
                    "batch_pause": IMAGE_BATCH_PAUSE_AUTO,
                    "recipe_scope_count": len(scoped_recipe_ids or []),
                    "source_scope_count": len(scoped_source_names or []),
                })
                if not started:
                    logger.info("Auto-download: skipped, download already in progress")
                    return False

                asyncio.create_task(
                    _download_images_task(
                        batch_pause=IMAGE_BATCH_PAUSE_AUTO,
                        recipe_ids=scoped_recipe_ids,
                        source_names=scoped_source_names,
                    )
                )
                return True
    except Exception as e:
        logger.warning(f"Could not check/start auto-download: {e}")

    return False
