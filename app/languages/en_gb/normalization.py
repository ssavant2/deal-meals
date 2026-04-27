"""
English (United Kingdom) text normalization scaffold.

This module is deliberately small. It exists so the UK country profile has the
same public hooks as the Swedish implementation while future work fills in real
UK grocery/recipe rules.

The historical adapter name `fix_swedish_chars()` is kept for compatibility
with the shared matcher runtime. For en_gb it simply performs generic Unicode
and spacing normalization.
"""

from __future__ import annotations

import re
import unicodedata


_WHITESPACE_RE = re.compile(r'\s+')
_TYPOGRAPHIC_TRANSLATION = str.maketrans({
    '\u2018': "'",
    '\u2019': "'",
    '\u201c': '"',
    '\u201d': '"',
    '\u2013': '-',
    '\u2014': '-',
    '\u00a0': ' ',
})


def normalize_text(text: str | None) -> str:
    """Return a conservative UK text-normalized string."""
    if not text:
        return ''

    value = str(text).translate(_TYPOGRAPHIC_TRANSLATION)
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(ch for ch in value if not unicodedata.combining(ch))
    return _WHITESPACE_RE.sub(' ', value).strip()


def normalize_market_text(text: str | None) -> str:
    """Compatibility hook used by the shared language runtime."""
    return normalize_text(text)


def fix_swedish_chars(text: str | None) -> str:
    """Compatibility hook used by the shared matcher runtime."""
    return normalize_text(text)


def normalize_ingredient(ingredient: str | None) -> str:
    """Normalize an ingredient phrase for future UK matching rules."""
    return normalize_text(ingredient).lower()
