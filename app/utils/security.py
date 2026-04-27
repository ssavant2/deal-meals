"""
Security Utilities.

Shared origin/CSRF helpers used by both HTTP middleware and WebSocket endpoints.
SSRF protection for outgoing HTTP requests.
"""

import ipaddress
import os
import socket
from urllib.parse import urlparse

import httpx


def get_allowed_origins() -> set:
    """Build set of allowed origins from ALLOWED_HOSTS env var."""
    hosts = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    port = os.environ.get('APP_PORT', '20080')
    origins = set()
    for host in hosts:
        host = host.strip()
        if host:
            # Add both http and https variants
            origins.add(f"http://{host}")
            origins.add(f"https://{host}")
            # Also allow with configured port
            origins.add(f"http://{host}:{port}")
            origins.add(f"https://{host}:{port}")
    return origins


ALLOWED_ORIGINS = get_allowed_origins()


def is_safe_url(url: str) -> bool:
    """Check that a URL points to a public internet host, not internal/private networks."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        if not results:
            return False
        for result in results:
            ip = ipaddress.ip_address(result[4][0])
            if not ip.is_global:
                return False
        return True
    except (socket.gaierror, ValueError, OSError):
        return False


async def ssrf_safe_event_hook(request: httpx.Request):
    """httpx event hook that blocks requests to private/internal IP ranges.

    Must be async for use with httpx.AsyncClient.

    Usage:
        async with httpx.AsyncClient(
            event_hooks={"request": [ssrf_safe_event_hook]}
        ) as client:
            ...
    """
    if not is_safe_url(str(request.url)):
        raise httpx.ConnectError(f"SSRF blocked: {request.url.host} resolves to a private IP")
