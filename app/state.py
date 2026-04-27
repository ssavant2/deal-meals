"""
Shared application state.

This module contains global state that needs to be shared across routers.
Import from here rather than creating local state to avoid duplication issues.

Thread-safety: All state modifications should use the helper functions
which handle locking automatically.
"""

import asyncio
from typing import Optional, Any
from datetime import datetime


# ==================== LOCKS ====================
# Module-level locks for thread-safe access to global state
_active_scrapes_lock = asyncio.Lock()
_scrape_tasks_lock = asyncio.Lock()
_image_state_lock = asyncio.Lock()
_running_scrapers_lock = asyncio.Lock()


# ==================== ACTIVE SCRAPE TRACKING ====================
# Tracks currently running store scrapes for status API
# Format: { "store_id": { "started_at": timestamp, "progress": int, "message": str } }
active_scrapes: dict = {}


# ==================== STORE SCRAPE TASKS ====================
# Stores asyncio.Task references for store scrapes (enables cancellation)
# Format: { "store_id": asyncio.Task }
scrape_tasks: dict = {}


# ==================== IMAGE DOWNLOAD STATE ====================
# Tracks image download progress
image_download_state: dict = {
    "running": False,
    "status": "idle",  # idle, running, complete, cancelled, error
    "processed": 0,
    "total": 0,
    "downloaded": 0,
    "skipped": 0,
    "errors": 0,
    "permanently_failed": 0,
    "message_key": None,
    "message_params": {},
    "batch_pause": 15,
}


# ==================== RECIPE SCRAPER STATE ====================
# Tracks running recipe scrapers for status API
# Format: { "scraper_id": { "running": bool, "status": str, "message": str, ... } }
running_scrapers: dict = {}

# Stores asyncio tasks for cancellation
scraper_tasks: dict = {}

# Locks to prevent race conditions when starting scrapers (per-scraper locks)
scraper_locks: dict = {}


# ==================== RUN-ALL QUEUE STATE ====================
# Persists the "run all active" queue so it survives page reloads.
# Format when active: {
#   "active": True,
#   "scraper_ids": ["arla", "ica", ...],   # ordered list to run
#   "index": 2,                             # next scraper to run
#   "total_new": 47,                        # accumulated new recipes so far
#   "started_at": "2026-04-23T..."
# }
_run_all_queue_lock = asyncio.Lock()
run_all_queue: dict = {}


async def set_run_all_queue(data: dict) -> None:
    async with _run_all_queue_lock:
        run_all_queue.clear()
        run_all_queue.update(data)


async def update_run_all_queue(**kwargs) -> None:
    async with _run_all_queue_lock:
        run_all_queue.update(kwargs)


async def get_run_all_queue() -> dict:
    async with _run_all_queue_lock:
        return run_all_queue.copy()


async def clear_run_all_queue() -> None:
    async with _run_all_queue_lock:
        run_all_queue.clear()


# ==================== HELPER FUNCTIONS ====================
# These provide thread-safe access to global state.
# Use these instead of directly modifying the dicts when possible.

async def update_active_scrape(store_id: str, data: dict) -> None:
    """Thread-safe update of active scrape status."""
    async with _active_scrapes_lock:
        if store_id in active_scrapes:
            active_scrapes[store_id].update(data)
        else:
            active_scrapes[store_id] = data


async def try_start_active_scrape(store_id: str, data: dict) -> Optional[str]:
    """
    Register a store scrape only if no other store scrape is running.

    Returns the already-running store_id when busy, otherwise None.
    """
    async with _active_scrapes_lock:
        for sid, scrape in active_scrapes.items():
            if not scrape.get("completed"):
                return sid
        active_scrapes[store_id] = data
        return None


async def get_active_scrape(store_id: str) -> Optional[dict]:
    """Thread-safe read of active scrape status."""
    async with _active_scrapes_lock:
        return active_scrapes.get(store_id, {}).copy() if store_id in active_scrapes else None


async def get_running_scrape() -> Optional[dict]:
    """Return the first active non-completed scrape with its store_id."""
    async with _active_scrapes_lock:
        for sid, scrape in active_scrapes.items():
            if not scrape.get("completed"):
                result = scrape.copy()
                result["store_id"] = sid
                return result
    return None


async def find_running_scrape() -> Optional[str]:
    """Thread-safe check for any active (non-completed) scrape. Returns store_id or None."""
    async with _active_scrapes_lock:
        for sid, scrape in active_scrapes.items():
            if not scrape.get("completed"):
                return sid
    return None


async def delete_active_scrape(store_id: str) -> None:
    """Thread-safe deletion of active scrape."""
    async with _active_scrapes_lock:
        if store_id in active_scrapes:
            del active_scrapes[store_id]


async def set_scrape_task(store_id: str, task: asyncio.Task) -> None:
    """Thread-safe store of a scrape asyncio.Task for cancellation."""
    async with _scrape_tasks_lock:
        scrape_tasks[store_id] = task


async def get_scrape_task(store_id: str) -> Optional[asyncio.Task]:
    """Thread-safe read of a scrape asyncio.Task."""
    async with _scrape_tasks_lock:
        return scrape_tasks.get(store_id)


async def delete_scrape_task(store_id: str) -> None:
    """Thread-safe deletion of a scrape asyncio.Task."""
    async with _scrape_tasks_lock:
        scrape_tasks.pop(store_id, None)


async def update_running_scraper(scraper_id: str, data: dict, replace: bool = False) -> None:
    """Thread-safe update of running scraper status.

    Args:
        replace: If True, replaces entire dict. If False (default), merges with existing.
    """
    async with _running_scrapers_lock:
        if replace or scraper_id not in running_scrapers:
            running_scrapers[scraper_id] = data
        else:
            running_scrapers[scraper_id].update(data)


async def get_running_scraper(scraper_id: str) -> Optional[dict]:
    """Thread-safe read of running scraper status."""
    async with _running_scrapers_lock:
        return running_scrapers.get(scraper_id, {}).copy() if scraper_id in running_scrapers else None


async def update_image_state(**kwargs) -> None:
    """Thread-safe update of image download state."""
    async with _image_state_lock:
        image_download_state.update(kwargs)


async def reset_image_state(data: dict) -> None:
    """Thread-safe clear-and-reset of image download state."""
    async with _image_state_lock:
        image_download_state.clear()
        image_download_state.update(data)


async def try_start_image_download(data: dict) -> bool:
    """Atomically check if download is idle and start it. Returns True if started."""
    async with _image_state_lock:
        if image_download_state.get("running"):
            return False
        image_download_state.clear()
        image_download_state.update(data)
        return True


async def get_image_state() -> dict:
    """Thread-safe read of image download state."""
    async with _image_state_lock:
        return image_download_state.copy()


def get_scraper_lock(scraper_id: str) -> asyncio.Lock:
    """Get or create a lock for a specific scraper (thread-safe)."""
    # setdefault is atomic in CPython - prevents race condition
    return scraper_locks.setdefault(scraper_id, asyncio.Lock())


# ==================== SSE EVENT BUS ====================
# Simple pub/sub for Server-Sent Events. Subscribers are asyncio.Queue instances.
# Only use from async context (the main event loop).

class EventBus:
    """Broadcast events to SSE subscribers."""

    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()

    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, event: dict) -> None:
        # Safe without lock: no awaits in loop body, runs atomically in event loop.
        # Do NOT add await inside this loop — it would allow subscribe/unsubscribe
        # to modify _subscribers mid-iteration.
        for q in self._subscribers:
            q.put_nowait(event)


event_bus = EventBus()
