"""Extraction thresholds and regex patterns for Swedish ingredient matching.

Used by:
- extraction.py — keyword extraction thresholds and regex helpers
- matching.py — reverse parent lookups and parenthetical handling
"""

import re
from typing import Dict, Set

from .keywords import SKIP_IF_FLAVORED
from .synonyms import INGREDIENT_PARENTS


MIN_KEYWORD_LENGTH = 6
MIN_KEYWORD_LENGTH_STRICT = 7


_INGREDIENT_PARENTS_REVERSE: Dict[str, Set[str]] = {}
for _child, _parent in INGREDIENT_PARENTS.items():
    _INGREDIENT_PARENTS_REVERSE.setdefault(_parent, set()).add(_child)


_SKIP_IF_FLAVORED_PATTERN = re.compile(
    r'(?:^|\s)(' +
    '|'.join(re.escape(c) for c in sorted(SKIP_IF_FLAVORED, key=len, reverse=True)) +
    r')(?:\s|$)'
)


_BABY_FOOD_PATTERN = re.compile(r'\bfrån\s+\d+\s*(?:månader?|mån|m)\b', re.IGNORECASE)
_PUNCTUATION_PATTERN = re.compile(r'[,;:()•®™©]')
_WHITESPACE_PATTERN = re.compile(r'\s+')
_PORTION_PATTERN = re.compile(r'\d+\s*port')


_OPTIONAL_PREF_GARNA = re.compile(r'\(gärna[^)]*\)')
_OPTIONAL_PREF_HELST = re.compile(r'\(helst[^)]*\)')
_OPTIONAL_PREF_TEX = re.compile(r'\(t\.?ex\.?[^)]*\)')
_NUMBERS_PATTERN = re.compile(r'\b\d+[\-,.]?\d*\b')
_MEASUREMENTS_PATTERN = re.compile(r'\b(ca|cirka|st|kg|g|mg|dl|cl|ml|msk|tsk|krm)\b')
_PUNCT_SPLIT_PATTERN = re.compile(r'[,;:()]')
_PARENS_PATTERN = re.compile(r'\([^)]*\)')
_DIGITS_PATTERN = re.compile(r'\d+')
