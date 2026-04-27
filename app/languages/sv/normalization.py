"""
Swedish Text Normalization Utilities.

Handles common issues with Swedish text from external sources:
- Missing diacritics (å, ä, ö) - e.g., "raka" → "räka"
- Variant spellings (filé vs file)
- Compound word splitting

Used by:
- Store scrapers (Willys API returns ASCII-only names sometimes)
- Recipe matcher (for ingredient matching)
"""

import re
from typing import Dict, List

# ── Non-Swedish accent stripping ──────────────────────────────────────────────
# Strips all European diacritics EXCEPT Swedish å, ä, ö (which we keep).
# Covers French (é, è, ê, ô, ç), Spanish (ñ, á, ú), Italian (ì, ò), German (ü), etc.
# Used early in fix_swedish_chars so product names like "Le Roulé", "Jalapeño",
# "Entrecôte" normalize to "Le Roule", "Jalapeno", "Entrecote".
_NON_SWEDISH_ACCENT_TABLE = str.maketrans({
    'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
    'á': 'a', 'à': 'a', 'â': 'a', 'ã': 'a',
    'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
    'ó': 'o', 'ò': 'o', 'ô': 'o', 'õ': 'o',
    'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
    'ý': 'y', 'ÿ': 'y',
    'ñ': 'n', 'ç': 'c', 'ð': 'd', 'ß': 'ss',
    'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
    'Á': 'A', 'À': 'A', 'Â': 'A', 'Ã': 'A',
    'Í': 'I', 'Ì': 'I', 'Î': 'I', 'Ï': 'I',
    'Ó': 'O', 'Ò': 'O', 'Ô': 'O', 'Õ': 'O',
    'Ú': 'U', 'Ù': 'U', 'Û': 'U', 'Ü': 'U',
    'Ý': 'Y', 'Ÿ': 'Y',
    'Ñ': 'N', 'Ç': 'C', 'Ð': 'D',
})


# Swedish character corrections: ASCII → proper Swedish
# Pattern → Replacement (uses regex)
SWEDISH_CHAR_FIXES: Dict[str, str] = {
    # =========================================================================
    # COMPOUND WORDS (must come before individual word patterns)
    # Words where BOTH prefix AND suffix need diacritics fixing
    # =========================================================================

    # --- Meat compounds with -färs (ground meat) ---
    r'Flaskfars': 'Fläskfärs',
    r'flaskfars': 'fläskfärs',
    r'Kottfars': 'Köttfärs',
    r'kottfars': 'köttfärs',
    r'Notfars': 'Nötfärs',
    r'notfars': 'nötfärs',
    r'Algfars': 'Älgfärs',
    r'algfars': 'älgfärs',

    # --- Meat compounds with fläsk- ---
    r'Flaskfile': 'Fläskfilé',
    r'flaskfile': 'fläskfilé',
    r'Flaskkarre': 'Fläskkarré',
    r'flaskkarre': 'fläskkarré',
    r'Flaskkotlett': 'Fläskkotlett',
    r'flaskkotlett': 'fläskkotlett',
    r'Sidflask': 'Sidfläsk',
    r'sidflask': 'sidfläsk',

    # --- Meat compounds with kött- ---
    r'Kottbullar': 'Köttbullar',
    r'kottbullar': 'köttbullar',

    # --- Vegetable/fruit compounds with röd- ---
    r'Rodkal': 'Rödkål',
    r'rodkal': 'rödkål',
    r'Rodlok': 'Rödlök',
    r'rodlok': 'rödlök',
    r'Rodbeta': 'Rödbeta',
    r'rodbeta': 'rödbeta',
    r'Rodbetor': 'Rödbetor',
    r'rodbetor': 'rödbetor',

    # --- Nut compounds ---
    r'Jordnotter': 'Jordnötter',
    r'jordnotter': 'jordnötter',
    r'Hasselnotter': 'Hasselnötter',
    r'hasselnotter': 'hasselnötter',
    r'Valnotter': 'Valnötter',
    r'valnotter': 'valnötter',
    r'Cashewnotter': 'Cashewnötter',
    r'cashewnotter': 'cashewnötter',

    # --- Dairy compounds ---
    r'Kokosmjolk': 'Kokosmjölk',
    r'kokosmjolk': 'kokosmjölk',

    # =========================================================================
    # INDIVIDUAL WORD PATTERNS (existing + new)
    # =========================================================================

    # === SEAFOOD ===
    r'\bRakor\b': 'Räkor',
    r'\brakor\b': 'räkor',
    r'\bRaka\b': 'Räka',
    r'\braka\b': 'räka',
    r'Skagenrora': 'Skagenröra',
    r'skagenrora': 'skagenröra',
    r'Havskraftor': 'Havskräftor',
    r'havskraftor': 'havskräftor',
    r'Rakost': 'Räkost',
    r'rakost': 'räkost',
    r'\bSpatta\b': 'Spätta',
    r'\bspatta\b': 'spätta',

    # === FRUITS & VEGETABLES ===
    r'\bBlabar\b': 'Blåbär',
    r'\bblabar\b': 'blåbär',
    r'\bParon\b': 'Päron',
    r'\bparon\b': 'päron',
    r'\bLok\b': 'Lök',
    r'\blok\b': 'lök',
    r'Spetskal': 'Spetskål',
    r'spetskal': 'spetskål',
    r'Fankal': 'Fänkål',
    r'fankal': 'fänkål',
    r'Vitlok': 'Vitlök',
    r'vitlok': 'vitlök',
    r'Salladslok': 'Salladslök',
    r'salladslok': 'salladslök',
    r'Sotpotatis': 'Sötpotatis',
    r'sotpotatis': 'sötpotatis',
    r'Jordartskockor': 'Jordärtskockor',
    r'jordartskockor': 'jordärtskockor',
    r'Morotter': 'Morötter',
    r'morotter': 'morötter',
    r'\borter\b': 'örter',
    r'\bOrter\b': 'Örter',
    r'\bApple\b': 'Äpple',
    r'\bapple\b': 'äpple',
    r'\bArtor\b': 'Ärtor',
    r'\bartor\b': 'ärtor',
    r'\bIngefara\b': 'Ingefära',
    r'\bingefara\b': 'ingefära',

    # === MEAT & POULTRY ===
    r'Ankbrost': 'Ankbröst',
    r'ankbrost': 'ankbröst',
    r'\bKott\b': 'Kött',
    r'\bkott\b': 'kött',
    r'\bFlask\b': 'Fläsk',
    r'\bflask\b': 'fläsk',
    r'Oxfile': 'Oxfilé',
    r'oxfile': 'oxfilé',

    # === DAIRY ===
    r'Gradde': 'Grädde',
    r'gradde': 'grädde',
    r'Graddfil': 'Gräddfil',
    r'graddfil': 'gräddfil',
    r'\bSmor\b': 'Smör',
    r'\bsmor\b': 'smör',
    r'\bMjolk\b': 'Mjölk',
    r'\bmjolk\b': 'mjölk',
    r'Vasterbottens': 'Västerbottens',
    r'vasterbottens': 'västerbottens',
    r'Vasterbotten': 'Västerbotten',
    r'vasterbotten': 'västerbotten',

    # === BREAD & EGGS ===
    r'\bBrod\b': 'Bröd',
    r'\bbrod\b': 'bröd',
    r'\bAgg\b': 'Ägg',
    r'\bagg\b': 'ägg',

    # === SAUCES & CONDIMENTS ===
    r'Pizzasas': 'Pizzasås',
    r'pizzasas': 'pizzasås',
    r'Tacosas': 'Tacosås',
    r'tacosas': 'tacosås',
    r'\bSas\b': 'Sås',
    r'\bsas\b': 'sås',

    # === COMMON ADJECTIVES ===
    r'Farsk': 'Färsk',
    r'farsk': 'färsk',
    r'\bRod\b': 'Röd',
    r'\brod\b': 'röd',
    r'fardig': 'färdig',
    r'Fardig': 'Färdig',
    r'gratang': 'gratäng',
    r'Gratang': 'Gratäng',

    # === HOUSEHOLD & OTHER ===
    r'\bLask\b': 'Läsk',
    r'\blask\b': 'läsk',
    r'\bTval\b': 'Tvål',
    r'\btval\b': 'tvål',
    r'Flergangs': 'Flergångs',
    r'flergangs': 'flergångs',
    r'Harfarg': 'Hårfärg',
    r'harfarg': 'hårfärg',
    r'oppna': 'öppna',
    r'Oppna': 'Öppna',
    r'Blojor': 'Blöjor',
    r'blojor': 'blöjor',
    r'Nasdukar': 'Näsdukar',
    r'nasdukar': 'näsdukar',
    r'Karnor': 'Kärnor',
    r'karnor': 'kärnor',
    r'Tradgard': 'Trädgård',
    r'tradgard': 'trädgård',

    # =========================================================================
    # GENERIC SUFFIX PATTERNS (catch-all for remaining compound words)
    # Applied last - specific patterns above take priority
    # =========================================================================
    r'fars\b': 'färs',      # -färs: kycklingfärs, vildsvinsfärs, lammfärs, etc.
    r'file\b': 'filé',      # -filé: laxfilé, torskfilé, kycklingfilé, etc.
    r'karre\b': 'karré',    # -karré: fläskkarré, vildsvinskarré, etc.
    r'Karre\b': 'Karré',    # -Karré: Fläskkarré capitalized
    r'sas\b': 'sås',        # -sås: romsås, etc.
    r'notter\b': 'nötter',  # -nötter: any remaining nut compounds
}


# ============================================================================
# PERFORMANCE: Pre-compile regex patterns and build fast detection pattern
# ============================================================================

# Strategy: Split fixes into simple string replacements (no regex metacharacters)
# and word-boundary patterns. Simple ones use str.replace() (~10x faster than regex).
# Then build a SINGLE combined regex for all boundary patterns with a lookup dict,
# so we do ONE regex pass instead of 46 individual re.sub() calls.

_SIMPLE_CHAR_FIXES: list = []  # (pattern, replacement) - plain string replacements
_BOUNDARY_LOOKUP: dict = {}     # match text → replacement for boundary patterns

for _pat, _repl in SWEDISH_CHAR_FIXES.items():
    if '\\b' in _pat or _pat.endswith('\\b') or '\\' in _pat:
        # Extract the literal word from boundary pattern for lookup
        _literal = _pat.replace('\\b', '')
        # Handle suffix patterns like 'fars\b' (no leading \b)
        _boundary_lookup_key = _literal
        _BOUNDARY_LOOKUP[_boundary_lookup_key] = _repl
    else:
        _SIMPLE_CHAR_FIXES.append((_pat, _repl))

# Build ONE combined regex for all boundary patterns (longest first for greedy match)
# This replaces 46 individual re.sub() calls with a single pass
_boundary_patterns = sorted(SWEDISH_CHAR_FIXES.keys(), key=len, reverse=True)
_boundary_patterns = [p for p in _boundary_patterns if '\\' in p]
_COMBINED_BOUNDARY_PATTERN = re.compile(
    '|'.join(f'({p})' for p in _boundary_patterns)
) if _boundary_patterns else None

def _boundary_replacer(match: re.Match) -> str:
    """Lookup replacement for the matched boundary pattern."""
    matched_text = match.group()
    return _BOUNDARY_LOOKUP.get(matched_text, matched_text)

# Fast bailout: combined detection pattern for ANY fix
_ANY_FIX_DETECTION = re.compile('|'.join(SWEDISH_CHAR_FIXES.keys()))


# Word variants for matching (singular/plural, with/without accent)
# Used for ingredient matching - maps variants to canonical form
SWEDISH_WORD_VARIANTS: Dict[str, List[str]] = {
    'räka': ['räka', 'räkor', 'raka', 'rakor'],
    'kyckling': ['kyckling', 'kycklingfilé', 'kycklingfile', 'kycklingbröst', 'kycklingbrost'],
    'fläsk': ['fläsk', 'fläskfilé', 'fläskfile', 'flask', 'flaskfile'],
    'nöt': ['nöt', 'nötfärs', 'nötkött', 'oxfilé', 'oxfile', 'entrecôte', 'entrecote'],
    'lax': ['lax', 'laxfilé', 'laxfile'],
    'torsk': ['torsk', 'torskfilé', 'torskfile', 'torskrygg'],
    'ägg': ['ägg', 'agg'],
    'grädde': ['grädde', 'gradde', 'vispgrädde', 'matlagningsgrädde'],
    'smör': ['smör', 'smor'],
    'lök': ['lök', 'lok', 'rödlök', 'vitlök', 'salladslök'],
    'potatis': ['potatis', 'potatisen', 'färskpotatis', 'bakpotatis'],
    'morot': ['morot', 'morötter', 'morotter'],
    'bröd': ['bröd', 'brod'],
}


def fix_swedish_chars(text: str) -> str:
    """
    Fix missing Swedish diacritics in text.

    Converts ASCII approximations to proper Swedish characters:
    - raka → räka
    - blabar → blåbär
    - gradde → grädde

    Args:
        text: Text that may have missing diacritics

    Returns:
        Text with corrected Swedish characters

    Example:
        >>> fix_swedish_chars("Rakor med gradde")
        'Räkor med grädde'
    """
    # Strip all non-Swedish accents (é→e, ñ→n, ô→o, ü→u, etc.)
    # Preserves å, ä, ö which are NOT in the table.
    # Replaces the old manual ñ, ô, entrecoté rules with one general pass.
    text = text.translate(_NON_SWEDISH_ACCENT_TABLE)

    # Fast bailout: single regex check if ANY pattern could match.
    # Avoids running 99 individual regex subs on text like "salt", "peppar", "olja"
    # which have no ASCII diacritics to fix. Saves ~2500ms during cache computation.
    if not _ANY_FIX_DETECTION.search(text):
        return text

    # Phase 1: Simple string replacements (92 patterns, ~10x faster than regex each)
    # These are plain text without word boundaries, applied longest-first
    for old, new in _SIMPLE_CHAR_FIXES:
        if old in text:
            text = text.replace(old, new)

    # Phase 2: Single combined regex pass for all word-boundary patterns
    # One re.sub() with lookup dict instead of 46 individual re.sub() calls
    if _COMBINED_BOUNDARY_PATTERN:
        text = _COMBINED_BOUNDARY_PATTERN.sub(_boundary_replacer, text)

    return text


def normalize_market_text(text: str | None) -> str:
    """Normalize Swedish market text for shared language runtime callers."""
    return fix_swedish_chars(str(text) if text is not None else "")


# Brands whose names contain food keywords that interfere with matching.
# Add brands here when their name causes false context-word blocks.
# Format: lowercase, will be matched case-insensitively against product name.
_BRANDS_TO_STRIP = {
    'jokkmokks korv & rökeri',  # "korv" in brand blocks sidfläsk/karré products
    'jokkmokks korv',           # shorter variant
    'jokkmokks rökeri',         # variant without "korv" (still in product names)
}


def strip_brand_from_name(name: str, brand: str) -> str:
    """
    Remove brand/manufacturer name from product name.

    Brand names embedded in product names can contain food keywords
    (e.g., "Jokkmokks korv & rökeri" contains "korv") that interfere
    with ingredient matching context checks.

    Only strips brands listed in _BRANDS_TO_STRIP to avoid unintended
    side effects. The brand is still stored in the separate brand column.

    Args:
        name: Product name (e.g., "Sidfläsk Vedrökt i skivor ca 14g Jokkmokks korv & rökeri")
        brand: Brand/manufacturer (e.g., "JOKKMOKKS KORV & RÖKERI")

    Returns:
        Cleaned product name (e.g., "Sidfläsk Vedrökt i skivor ca 14g")
    """
    if not brand or not name:
        return name

    brand_lower = brand.lower().strip()

    # Only strip brands we know cause problems
    if brand_lower not in _BRANDS_TO_STRIP:
        return name

    # Case-insensitive removal from product name
    name_lower = name.lower()
    idx = name_lower.find(brand_lower)
    if idx >= 0:
        name = (name[:idx] + name[idx + len(brand_lower):]).strip()
        # Clean up double/trailing spaces
        while '  ' in name:
            name = name.replace('  ', ' ')

    return name


def normalize_ingredient(ingredient: str) -> str:
    """
    Normalize an ingredient name for matching.

    - Converts to lowercase
    - Fixes Swedish characters
    - Normalizes milk variants to "mjölk"
    - Removes common suffixes (färsk, fryst, etc.)

    Args:
        ingredient: Raw ingredient name

    Returns:
        Normalized ingredient name

    Example:
        >>> normalize_ingredient("Färsk Laxfilé 400g")
        'laxfilé'
    """
    name = ingredient.lower()
    name = fix_swedish_chars(name)

    # Lactose-free milk is legally "dryck" (EU rules) but is just regular milk.
    # Must run before suffix removal since that strips digits/weights.
    name = re.sub(r'\b(?:mellan|standard|lätt)mjölk(?:dryck)?\b', 'mjölk', name)

    # Remove common suffixes
    name = re.sub(r'\s+(klass|färsk|fryst|sverige|brasilien|frankrike|original).*', '', name)
    # Remove weights/amounts: only strip digits followed by a recognized unit.
    # Old pattern r'\s+\d+.*' was too aggressive — "Tipo 00 Siktat Vetemjöl" lost everything.
    name = re.sub(r'\s+\d+[\d,\.]*\s*(?:g|kg|ml|cl|dl|l|st|port|pack|p|mån|månader|%|gram|kilo|liter|cm|-pack)\b.*', '', name, flags=re.IGNORECASE)

    return name.strip()

