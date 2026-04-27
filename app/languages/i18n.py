"""
Internationalization (i18n) framework for Deal Meals.

Usage in Jinja2 templates:
    {{ t('nav.home') }}
    {{ t('button.save') }}

Usage in Python:
    from languages.i18n import get_translator
    t = get_translator('sv')
    text = t('nav.home')

Adding a new language/locale:
    1. Create folder: app/languages/xx/ (e.g., "de" for German)
       or app/languages/ll_cc/ for a country-specific locale (e.g., "en_gb").
    2. Create an empty __init__.py in the folder
    3. Copy app/languages/en_gb/ui.py to app/languages/xx/ui.py
    4. Translate all strings in the UI dict
    5. If the language code is not in LANGUAGE_INFO below, add it
       with 'name' (native name) and 'flag_code' (ISO 3166-1 alpha-2)
    6. Restart the app - new language auto-discovered!

Language folders must contain:
    - __init__.py (can be empty)
    - ui.py with UI = { ... } dict containing translations
"""

import os
import importlib
from typing import Dict, List, Optional, Callable
from functools import lru_cache
from loguru import logger

# Directory containing language folders
LANGUAGES_DIR = os.path.dirname(os.path.abspath(__file__))

# Default language and fallback
DEFAULT_LANGUAGE = 'sv'
FALLBACK_LANGUAGE = 'en_gb'

LANGUAGE_ALIASES = {
    'sv-se': 'sv',
    'en': 'en_gb',
    'en-gb': 'en_gb',
    'en_gb': 'en_gb',
}

# Human-readable language names and flag country codes (ISO 3166-1 alpha-2)
# Used with flag-icons CSS library: https://github.com/lipis/flag-icons
LANGUAGE_INFO = {
    'sv': {'name': 'Svenska', 'flag_code': 'se', 'locale': 'sv-SE', 'display_code': 'SV'},
    'en_gb': {'name': 'English (United Kingdom)', 'flag_code': 'gb', 'locale': 'en-GB', 'display_code': 'EN-GB'},
    'de': {'name': 'Deutsch', 'flag_code': 'de'},
    'no': {'name': 'Norsk', 'flag_code': 'no'},
    'da': {'name': 'Dansk', 'flag_code': 'dk'},
    'fi': {'name': 'Suomi', 'flag_code': 'fi'},
    'fr': {'name': 'Français', 'flag_code': 'fr'},
    'es': {'name': 'Español', 'flag_code': 'es'},
    'nl': {'name': 'Nederlands', 'flag_code': 'nl'},
    'pl': {'name': 'Polski', 'flag_code': 'pl'},
}


def normalize_language_code(lang: str | None) -> str:
    """Normalize user-facing locale values to internal package names."""
    if not lang:
        return DEFAULT_LANGUAGE
    code = lang.strip().lower().replace('_', '-')
    return LANGUAGE_ALIASES.get(code, code.replace('-', '_'))


@lru_cache(maxsize=1)
def get_available_languages() -> List[str]:
    """
    Auto-discover available language folders.

    Returns list of language codes (e.g., ['sv', 'en_gb', 'de']).
    A valid language folder must contain ui.py with a UI dict.
    Sorted alphabetically by language name.
    """
    languages = []

    for item in os.listdir(LANGUAGES_DIR):
        lang_path = os.path.join(LANGUAGES_DIR, item)
        ui_path = os.path.join(lang_path, 'ui.py')

        # Must be a directory with ui.py file
        if os.path.isdir(lang_path) and os.path.exists(ui_path):
            # Skip __pycache__ and similar
            if not item.startswith('_'):
                languages.append(item)

    # Sort alphabetically by language name (not code)
    languages.sort(key=lambda x: get_language_name(x).lower())
    return languages


@lru_cache(maxsize=10)
def _load_translations(lang: str) -> Dict[str, str]:
    """
    Load UI translations for a specific language.

    Returns empty dict if language not found.
    """
    lang = normalize_language_code(lang)
    try:
        module = importlib.import_module(f'languages.{lang}.ui')
        return getattr(module, 'UI', {})
    except (ImportError, AttributeError) as e:
        logger.warning(f"Could not load translations for '{lang}': {e}")
        return {}


def get_translations(lang: str) -> Dict[str, str]:
    """Get all translations for a language."""
    return _load_translations(normalize_language_code(lang))


def translate(key: str, lang: str = DEFAULT_LANGUAGE) -> str:
    """
    Translate a key to the specified language.

    Fallback chain:
    1. Try requested language
    2. Try fallback language (English)
    3. Return the key itself (for debugging)

    Args:
        key: Translation key (e.g., 'nav.home', 'button.save')
        lang: Language code (e.g., 'sv', 'en')

    Returns:
        Translated string or the key if not found
    """
    lang = normalize_language_code(lang)

    # Try requested language
    translations = _load_translations(lang)
    if key in translations:
        return translations[key]

    # Try fallback language (if different)
    if lang != FALLBACK_LANGUAGE:
        fallback_translations = _load_translations(FALLBACK_LANGUAGE)
        if key in fallback_translations:
            return fallback_translations[key]

    # Return key itself (makes it easy to spot missing translations)
    return f"[{key}]"


def get_translator(lang: str = DEFAULT_LANGUAGE) -> Callable[[str], str]:
    """
    Get a translator function bound to a specific language.

    This is useful for creating a `t()` function for templates.

    Usage:
        t = get_translator('sv')
        text = t('nav.home')
    """
    normalized_lang = normalize_language_code(lang)

    def t(key: str) -> str:
        return translate(key, normalized_lang)
    return t


def get_language_name(lang: str) -> str:
    """Get human-readable name for a language code."""
    lang = normalize_language_code(lang)
    info = LANGUAGE_INFO.get(lang, {})
    return info.get('name', lang.upper())


def get_language_flag(lang: str) -> str:
    """Get flag country code (ISO 3166-1 alpha-2) for a language.

    Used with flag-icons CSS: <span class="fi fi-{code}"></span>
    """
    lang = normalize_language_code(lang)
    info = LANGUAGE_INFO.get(lang, {})
    return info.get('flag_code', lang[:2])


def get_language_locale(lang: str) -> str:
    """Get browser/HTML locale for an internal language code."""
    lang = normalize_language_code(lang)
    info = LANGUAGE_INFO.get(lang, {})
    return info.get('locale', lang.replace('_', '-'))


def get_language_display_code(lang: str) -> str:
    """Get compact label for the language selector."""
    lang = normalize_language_code(lang)
    info = LANGUAGE_INFO.get(lang, {})
    return info.get('display_code', lang.upper().replace('_', '-'))


def get_language_info() -> List[Dict[str, str]]:
    """
    Get info about all available languages.

    Returns list of dicts with 'code', 'name', 'flag', 'locale', and
    'display_code' keys.
    Useful for building language selector dropdowns.
    Sorted alphabetically by language name.
    """
    return [
        {
            'code': lang,
            'name': get_language_name(lang),
            'flag': get_language_flag(lang),
            'locale': get_language_locale(lang),
            'display_code': get_language_display_code(lang),
        }
        for lang in get_available_languages()
    ]
