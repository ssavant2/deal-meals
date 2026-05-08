"""
SSL/TLS API Routes.

This router handles SSL certificate management:
- /api/ssl/status - Get SSL status
- /api/ssl/upload - Upload certificates
- /api/ssl/enable - Enable/disable SSL
- /api/ssl/certificates - Delete certificates
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger

from utils.errors import friendly_error

# Import SSL configuration (optional component)
try:
    from ssl_config import ssl_manager
    SSL_AVAILABLE = True
except ImportError:
    SSL_AVAILABLE = False
    ssl_manager = None


router = APIRouter(prefix="/api/ssl", tags=["ssl"])


def _content_length_over_limit(value: str | None, limit_bytes: int) -> bool:
    if not value:
        return False
    try:
        return int(value) > limit_bytes
    except ValueError:
        return False


def _extract_ssl_upload_payload(data) -> tuple[bytes | None, bytes | None, str | None]:
    """Validate SSL upload JSON and return PEM data as bytes."""
    if not isinstance(data, dict):
        return None, None, "error.invalid_data"

    cert_content = data.get("cert")
    key_content = data.get("key")

    if cert_content is None or key_content is None:
        return None, None, "ssl.cert_and_key_required"
    if not isinstance(cert_content, str) or not isinstance(key_content, str):
        return None, None, "error.invalid_data"
    if not cert_content or not key_content:
        return None, None, "ssl.cert_and_key_required"

    return cert_content.encode('utf-8'), key_content.encode('utf-8'), None


def _extract_ssl_enabled_payload(data) -> tuple[bool | None, str | None]:
    """Validate SSL enable JSON."""
    if not isinstance(data, dict):
        return None, "error.invalid_data"

    enabled = data.get("enabled", False)
    if not isinstance(enabled, bool):
        return None, "error.invalid_data"

    return enabled, None


@router.get("/status")
def get_ssl_status():
    """Get SSL/TLS configuration status."""
    if not SSL_AVAILABLE:
        return JSONResponse({
            "success": False,
            "message_key": "ssl.not_available"
        }, status_code=500)

    try:
        status = ssl_manager.get_status()
        return JSONResponse({
            "success": True,
            "status": status
        })
    except Exception as e:
        logger.error(f"Failed to get SSL status: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        }, status_code=500)


@router.post("/upload")
async def upload_ssl_certificates(request: Request):
    """
    Upload SSL certificate and private key.

    Accepts JSON with:
    - cert: Certificate content (PEM format string)
    - key: Private key content (PEM format string)
    """
    if not SSL_AVAILABLE:
        return JSONResponse({
            "success": False,
            "message_key": "ssl.not_available"
        }, status_code=500)

    try:
        # Reject oversized payloads before parsing (normal cert+key is ~5 KB)
        content_length = request.headers.get("content-length")
        if _content_length_over_limit(content_length, 102_400):  # 100 KB
            return JSONResponse({
                "success": False,
                "message_key": "ssl.payload_too_large"
            }, status_code=413)

        data = await request.json()
        cert_data, key_data, message_key = _extract_ssl_upload_payload(data)
        if message_key:
            status_code = 400
            return JSONResponse({
                "success": False,
                "message_key": message_key
            }, status_code=status_code)

        # Save and validate
        success, message = ssl_manager.save_certificates(cert_data, key_data)

        if success:
            # Get updated cert info
            cert_info = ssl_manager.get_cert_info()
            return JSONResponse({
                "success": True,
                "message_key": message,
                "certificate": cert_info
            })
        else:
            return JSONResponse({
                "success": False,
                "message_key": message
            }, status_code=400)

    except Exception as e:
        logger.error(f"Failed to upload SSL certificates: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        }, status_code=500)


@router.post("/enable")
async def enable_ssl(request: Request):
    """Enable or disable SSL."""
    if not SSL_AVAILABLE:
        return JSONResponse({
            "success": False,
            "message_key": "ssl.not_available"
        }, status_code=500)

    try:
        data = await request.json()
        enabled, message_key = _extract_ssl_enabled_payload(data)
        if message_key:
            return JSONResponse({
                "success": False,
                "message_key": message_key
            }, status_code=400)

        success, message = ssl_manager.set_ssl_enabled(enabled)

        return JSONResponse({
            "success": success,
            "message_key": message,
            "ssl_enabled": ssl_manager.is_ssl_enabled() if success else None
        }, status_code=200 if success else 400)

    except Exception as e:
        logger.error(f"Failed to toggle SSL: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        }, status_code=500)


@router.delete("/certificates")
def delete_ssl_certificates():
    """Delete SSL certificates and disable SSL."""
    if not SSL_AVAILABLE:
        return JSONResponse({
            "success": False,
            "message_key": "ssl.not_available"
        }, status_code=500)

    try:
        success, message = ssl_manager.delete_certificates()

        return JSONResponse({
            "success": success,
            "message_key": message
        }, status_code=200 if success else 500)

    except Exception as e:
        logger.error(f"Failed to delete SSL certificates: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        }, status_code=500)
