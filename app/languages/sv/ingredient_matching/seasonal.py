"""Seasonal and buffet recipe helpers for Swedish recipe filtering."""

import re
from datetime import date, timedelta
from typing import FrozenSet

try:
    from languages.sv.normalization import fix_swedish_chars
except ModuleNotFoundError:
    from app.languages.sv.normalization import fix_swedish_chars


_DIGITS_PATTERN = re.compile(r'\d+')


_BUFFET_PATTERNS: FrozenSet[str] = frozenset({
    # Buffet indicators
    'buffé', 'buffe', 'buffémat', 'buffemat',
    # Multi-course meals
    'trerätters', 'tre rätters', 'fyrarätters', 'fyra rätters',
    'femrätters', 'fem rätters', 'meny för',
    # Party/event food - both "meny" and "bord" variants
    'festmeny', 'fest meny', 'julmeny', 'jul meny', 'julbord', 'jul bord',
    'påskmeny', 'påsk meny', 'påskbord', 'påsk bord',
    'midsommarmeny', 'midsommar meny', 'midsommarbord', 'midsommar bord',
    'nyårsmeny', 'nyårs meny', 'nyårsbord', 'nyårs bord',
    'kräftskiva', 'surströmmingsskiva',
    # Large gatherings
    'kalas', 'mingel', 'mingelbord',
    # Catering-style
    'dukning', 'festdukning',
})

_BUFFET_REGEX_PATTERNS = [
    r'mat\s+till\s+\w*festen',      # "mat till sommarfesten"
    r'mat\s+för\s+\d+\s+personer',  # "mat för 12 personer" (we'll check the number)
    r'meny\s+för\s+\d+',            # "meny för 8 personer"
    r'buffé\s+för',                 # "buffé för 10 personer"
    r'till\s+\d+\s+personer',       # generic "till 10 personer"
    r'för\s+\d+\s+personer',        # generic "för 8 personer" (catches julbord etc)
]

_BUFFET_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _BUFFET_REGEX_PATTERNS]

def is_buffet_or_party_recipe(recipe_name: str, num_ingredients: int = 0) -> bool:
    """
    Detect if a recipe is a buffet, party menu, or multi-course meal.

    These recipes typically have 30-50+ ingredients and dominate rankings
    due to sheer volume, but are rarely useful for everyday cooking.

    Args:
        recipe_name: Name of the recipe
        num_ingredients: Optional - number of ingredients (used as secondary signal)

    Returns:
        True if recipe appears to be buffet/party type

    Examples:
        >>> is_buffet_or_party_recipe("Mathems italienska buffé för 8 personer")
        True
        >>> is_buffet_or_party_recipe("Trerätters meny med kött")
        True
        >>> is_buffet_or_party_recipe("Mat till sommarfesten")
        True
        >>> is_buffet_or_party_recipe("Kycklinggryta med ris")
        False
    """
    name_lower = recipe_name.lower()

    # Check simple patterns
    for pattern in _BUFFET_PATTERNS:
        if pattern in name_lower:
            return True

    # Check regex patterns
    for compiled_pattern in _BUFFET_COMPILED_PATTERNS:
        match = compiled_pattern.search(name_lower)
        if match:
            # For "för X personer" patterns, check if X >= 8
            # (normal recipes might say "för 4 personer")
            matched_text = match.group()
            numbers = _DIGITS_PATTERN.findall(matched_text)
            if numbers:
                num_persons = int(numbers[0])
                if num_persons >= 8:
                    return True
            else:
                # Pattern matched but no number - still likely a party recipe
                return True

    # Secondary signal: extremely high ingredient count (30+)
    # Only use as tiebreaker if name is somewhat suspicious
    if num_ingredients >= 30:
        suspicious_words = ['meny', 'mat till', 'mat för', 'recept för']
        if any(word in name_lower for word in suspicious_words):
            return True

    return False

def _easter_date(year: int) -> date:
    """Compute Easter Sunday using the Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month, day = divmod(h + el - 7 * m + 114, 31)
    return date(year, month, day + 1)

def _midsommar_date(year: int) -> date:
    """Midsommarafton: the Friday between June 19-25."""
    for day in range(19, 26):
        d = date(year, 6, day)
        if d.weekday() == 4:  # Friday
            return d
    return date(year, 6, 21)

def _jul_range(today: date):
    """Dec 1 - Jan 6, handling year boundary."""
    if today.month >= 11:
        return date(today.year, 12, 1), date(today.year + 1, 1, 6)
    elif today.month == 1 and today.day <= 6:
        return date(today.year - 1, 12, 1), date(today.year, 1, 6)
    else:
        # Outside season entirely — return a past range
        return date(today.year - 1, 12, 1), date(today.year - 1, 12, 1)

def _nyar_range(today: date):
    """Dec 27 - Jan 2, handling year boundary."""
    if today.month == 12 and today.day >= 27:
        return date(today.year, 12, 27), date(today.year + 1, 1, 2)
    elif today.month == 1 and today.day <= 2:
        return date(today.year - 1, 12, 27), date(today.year, 1, 2)
    else:
        return date(today.year - 1, 12, 27), date(today.year - 1, 12, 27)

_SEASONAL_HOLIDAY_RULES = [
    # Jul (Christmas): Dec 1 - Jan 6
    ({'jul', 'pepparkak', 'pepparkakor', 'glogg', 'glögg', 'julskinka',
      'lussebulle', 'lussekatt', 'lucia', 'julbak', 'julgodis', 'advent'},
     _jul_range),
    # Nyår (New Year): Dec 27 - Jan 2
    ({'nyår', 'nyårs', 'nyar'},
     _nyar_range),
    # Semla/Fettisdag: ~2 weeks around fettisdagen (47 days before Easter)
    ({'semla', 'semlor', 'fettisdag'},
     lambda t: (_easter_date(t.year) - timedelta(days=54),
                _easter_date(t.year) - timedelta(days=40))),
    # Påsk (Easter): 2 weeks before - 1 week after
    ({'påsk', 'pask', 'påsklamm', 'pasklamm'},
     lambda t: (_easter_date(t.year) - timedelta(days=14),
                _easter_date(t.year) + timedelta(days=7))),
    # Midsommar: 1 week before - day after
    ({'midsommar'},
     lambda t: (_midsommar_date(t.year) - timedelta(days=7),
                _midsommar_date(t.year) + timedelta(days=1))),
    # Kräftskiva: August
    ({'kräftskiva', 'kraftskiva', 'kräftkalas', 'kraftkalas',
      'surströmmingsskiva', 'surstromming'},
     lambda t: (date(t.year, 8, 1), date(t.year, 8, 31))),
    # Halloween: ~Oct 24 - Nov 3
    ({'halloween'},
     lambda t: (date(t.year, 10, 24), date(t.year, 11, 3))),
]

_SEASONAL_PREFIX_RULES = [
    ('sommar', 6, 1, 8, 31),    # Summer: Jun - Aug
    ('höst', 9, 1, 11, 30),     # Autumn: Sep - Nov
    ('host', 9, 1, 11, 30),     # Normalized form of höst
    ('vinter', 12, 1, 2, 28),   # Winter: Dec - Feb
]

_ALL_SEASONAL_WORDS = set()

_SEASONAL_QUICK_CHECK = re.compile(
    '(' + '|'.join(re.escape(w) for w in sorted(_ALL_SEASONAL_WORDS, key=len, reverse=True)) + ')',
    re.IGNORECASE
)

def is_off_season_recipe(recipe_name: str, today: date = None) -> bool:
    """
    Check if a recipe is seasonal and currently out of season.

    Returns True if the recipe should be HIDDEN (seasonal keyword found,
    but today is outside that season's window).

    Only used for homepage cache filtering. Recipe search is unaffected.
    """
    if not recipe_name:
        return False

    if today is None:
        today = date.today()

    name_lower = recipe_name.lower()

    # Fast bail-out: no seasonal keyword at all
    if not _SEASONAL_QUICK_CHECK.search(name_lower):
        return False

    name_normalized = fix_swedish_chars(name_lower)

    # Check holiday rules (substring matching)
    for keywords, get_range in _SEASONAL_HOLIDAY_RULES:
        for kw in keywords:
            if kw in name_lower or kw in name_normalized:
                start, end = get_range(today)
                if start <= today <= end:
                    return False  # In season — show it
                return True  # Out of season — hide it

    # Check season prefix rules (compound words only)
    for prefix, sm, sd, em, ed in _SEASONAL_PREFIX_RULES:
        for name_variant in (name_lower, name_normalized):
            pos = name_variant.find(prefix)
            if pos >= 0:
                after = pos + len(prefix)
                # Must be prefix of a compound word (next char is a letter)
                if after < len(name_variant) and name_variant[after].isalpha():
                    # Check if in season
                    if em >= sm:
                        in_season = date(today.year, sm, sd) <= today <= date(today.year, em, ed)
                    else:
                        # Wrapping range (Dec-Feb for vinter)
                        in_season = (today >= date(today.year, sm, sd) or
                                     today <= date(today.year, em, ed))
                    return not in_season

    return False
