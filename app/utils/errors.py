"""
User-friendly error messages.

Maps technical exceptions to i18n translation keys.
The actual text lives in each language package's ui.py module.
"""

from uuid import UUID
from loguru import logger


def is_valid_uuid(value: str) -> bool:
    """Check if a string is a valid UUID."""
    try:
        UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def friendly_error(e: Exception) -> str:
    """
    Convert a technical exception to a user-friendly i18n key.

    The technical error is logged for debugging.
    Returns a translation key that the frontend can translate.

    Args:
        e: The exception to convert

    Returns:
        Translation key (e.g., 'error.connection')
    """
    error_str = str(e).lower()

    # Log the technical error for debugging
    logger.debug(f"Converting error to user-friendly message: {e}")

    # Connection errors
    if any(x in error_str for x in ['connection', 'connect', 'refused', 'unreachable']):
        return 'error.connection'

    # Timeout errors
    if 'timeout' in error_str or 'timed out' in error_str:
        return 'error.timeout'

    # Not found errors
    if '404' in error_str or 'not found' in error_str:
        return 'error.not_found'

    # Database constraint errors
    if any(x in error_str for x in ['unique constraint', 'duplicate', 'already exists']):
        return 'error.already_exists'

    # Database errors
    if any(x in error_str for x in ['database', 'sql', 'postgres', 'integrity']):
        return 'error.database'

    # Rate limiting
    if any(x in error_str for x in ['rate limit', '429', 'too many']):
        return 'error.rate_limited'

    # Auth errors
    if any(x in error_str for x in ['unauthorized', '401', '403', 'forbidden', 'permission']):
        return 'error.unauthorized'

    # Invalid data
    if isinstance(e, ValueError) and 'expecting value' in error_str:
        return 'error.invalid_data'
    if any(x in error_str for x in ['invalid', 'validation', 'parse', 'decode', 'json']):
        return 'error.invalid_data'

    # File errors
    if any(x in error_str for x in ['file not found', 'no such file', 'filenotfound']):
        return 'error.file_not_found'

    # Generic fallback — log at warning so unmatched errors are visible
    logger.warning(f"Unmatched error type (returning generic): {type(e).__name__}: {e}")
    return 'error.generic'
