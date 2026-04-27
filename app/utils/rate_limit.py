"""
Rate limiting for the Deal Meals API.

Uses slowapi with in-memory storage. Client IP is extracted from the
direct TCP connection by default. If running behind a reverse proxy,
set TRUSTED_PROXY in .env to trust X-Forwarded-For from that IP.
"""

import os
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse
from loguru import logger

from config import settings

# Only trust X-Forwarded-For from this IP (e.g. your Nginx Proxy Manager)
# Leave empty/unset for direct exposure (safe default)
TRUSTED_PROXY = os.environ.get("TRUSTED_PROXY", "").strip()


def get_client_ip(request: Request) -> str:
    """Extract real client IP. Only trusts X-Forwarded-For from TRUSTED_PROXY."""
    if TRUSTED_PROXY:
        direct_ip = get_remote_address(request)
        if direct_ip == TRUSTED_PROXY:
            forwarded_for = request.headers.get("x-forwarded-for")
            if forwarded_for:
                return forwarded_for.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(
    key_func=get_client_ip,
    default_limits=[settings.rate_limit_global] if settings.rate_limit_enabled else [],
    storage_uri="memory://",
    swallow_errors=True,
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return 429 JSON response consistent with the app's error format."""
    client_ip = get_client_ip(request)
    logger.warning(f"Rate limit hit: {exc.detail} | IP: {client_ip} | {request.method} {request.url.path}")
    return JSONResponse(
        {
            "success": False,
            "error": "Rate limit exceeded",
            "message_key": "error.rate_limited",
            "detail": str(exc.detail),
        },
        status_code=429,
    )
