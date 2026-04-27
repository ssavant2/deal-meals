"""
Request Helper Functions.

Shared utilities for extracting user preferences from HTTP requests.
Used by both app.py and routers/pages.py to avoid circular imports.
"""

from fastapi import Request

from languages.i18n import (
    get_translator, get_available_languages, DEFAULT_LANGUAGE,
    get_language_locale, get_language_display_code, normalize_language_code
)


def get_theme(request: Request) -> str:
    """Get theme from cookie, defaults to 'light'."""
    return request.cookies.get('theme', 'light')


def get_font_size(request: Request) -> int:
    """Get font size from cookie, defaults to 16 (px)."""
    try:
        size = int(request.cookies.get('fontSize', '16'))
        return max(12, min(24, size))  # Clamp to safe range
    except (ValueError, TypeError):
        return 16


def get_high_contrast(request: Request) -> bool:
    """Get high contrast setting from cookie."""
    return request.cookies.get('highContrast', 'false') == 'true'


def get_language(request: Request) -> str:
    """Get language from cookie, defaults to the configured app language."""
    lang = normalize_language_code(request.cookies.get('language', DEFAULT_LANGUAGE))
    # Validate that the language is available
    if lang not in get_available_languages():
        lang = DEFAULT_LANGUAGE
    return lang


def get_i18n_context(request: Request) -> dict:
    """Get i18n context variables for templates.

    Returns dict with:
        - t: Translation function bound to current language
        - current_language: Current language code
        - current_locale: Browser/HTML locale code
        - theme: Current theme
    """
    lang = get_language(request)
    return {
        "t": get_translator(lang),
        "current_language": lang,
        "current_locale": get_language_locale(lang),
        "current_language_display": get_language_display_code(lang),
        "theme": get_theme(request),
        "font_size": get_font_size(request),
        "high_contrast": get_high_contrast(request),
        "csp_nonce": getattr(request.state, 'csp_nonce', ''),
    }
