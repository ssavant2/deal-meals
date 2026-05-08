"""Lightweight in-process user activity tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock


_LOCK = Lock()
_last_user_activity_at: datetime | None = None
_last_user_activity_path: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def should_count_request_as_user_activity(path: str, method: str) -> bool:
    """Return True for requests that indicate active user interaction."""
    if not path or path == "/health":
        return False
    if path.startswith("/static/"):
        return False
    if path.startswith("/scrapers/stores/"):
        return False

    # Polling/status endpoints should not keep the app artificially "active".
    if method.upper() == "GET":
        if path == "/api/cache/status":
            return False
        if path == "/api/images/download/status":
            return False
        if path == "/api/images/preferences":
            return False
        if path == "/api/recipe-scrapers/queue":
            return False
        if path.startswith("/api/recipe-scrapers/") and path.endswith("/status"):
            return False
        if path.startswith("/api/scraper-schedules/"):
            return False
        if path.startswith("/api/store-schedules/"):
            return False

    return True


def record_user_activity(path: str, method: str) -> None:
    """Remember the latest likely user-driven request."""
    global _last_user_activity_at, _last_user_activity_path
    if not should_count_request_as_user_activity(path, method):
        return
    with _LOCK:
        _last_user_activity_at = _utcnow()
        _last_user_activity_path = path


def get_last_user_activity() -> tuple[datetime | None, str | None]:
    """Return the latest tracked user activity timestamp and request path."""
    with _LOCK:
        return _last_user_activity_at, _last_user_activity_path
