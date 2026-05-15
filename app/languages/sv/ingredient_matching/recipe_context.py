"""Recipe-context rules for Swedish ingredient matching."""

import re
from typing import Dict, FrozenSet, Set

try:
    from languages.sv.normalization import fix_swedish_chars
except ModuleNotFoundError:
    from app.languages.sv.normalization import fix_swedish_chars


_DESCRIPTOR_PHRASE_MARKERS = re.compile(
    r'(?:'
    r'gärna med\b'
    r'|garnamåen med\b'
    r'|fylld(?:a)? med\b'
    r'|med\s+\w*fyllning'
    r'|smaksatt(?:a)? med\b'
    r'|med smak av\b'
    r'|med\s+smak\s+av\b'
    r'|\bmed\b'
    r')',
    re.IGNORECASE
)


DESCRIPTOR_SUPPRESSION_PRIMARIES: FrozenSet[str] = frozenset({
    fix_swedish_chars(w).lower() for w in {
        'köttbullar', 'köttbulle',
        'tortellini', 'tortelloni', 'ravioli', 'cannelloni',
        'dumplings', 'wontons', 'gyoza',
        'falafel',
        'proteinpudding',
    }
})


# CUISINE_CONTEXT: products with very cuisine-specific seasoning in their name
# are only allowed to match recipes that contain the corresponding context words.
# This preserves pre-seasoned raw products as valid suggestions in matching recipes
# while preventing e.g. "Thaikryddad kycklingfilé" from appearing in French recipes.
#
# When to add a new entry:
#   A product trigger word is so cuisine-specific that it would be wrong in 95%+
#   of recipes. Examples of future candidates: 'tikka masala', 'tandoori', 'shawarma'.
#   Use this instead of PNB so the product remains visible in matching cuisine recipes.
#
# How it works: if product name contains the trigger, full_recipe_text must contain
# at least one of the context words, otherwise the match is rejected (recipe_matcher_backend.py).
CUISINE_CONTEXT: Dict[str, Set[str]] = {
    'taco': {
        'taco', 'tacos', 'texmex', 'tex mex', 'tex-mex',
        'mexikansk', 'burrito', 'fajita', 'enchilada',
        'quesadilla', 'nacho', 'nachos', 'wrap',
    },
    'texmex': {
        'taco', 'tacos', 'texmex', 'tex mex', 'tex-mex',
        'mexikansk', 'burrito', 'fajita', 'enchilada',
        'quesadilla', 'nacho', 'nachos', 'wrap',
    },
    'tex mex': {
        'taco', 'tacos', 'texmex', 'tex mex', 'tex-mex',
        'mexikansk', 'burrito', 'fajita', 'enchilada',
        'quesadilla', 'nacho', 'nachos', 'wrap',
    },
    'gyros': {
        'gyros', 'souvlaki', 'grekisk', 'pita',
        'tzatziki', 'medelhav',
    },
    # Thaikryddad products require a Thai/Asian recipe context.
    # Without thai context (wok, pad thai, curry, kokosmjölk, etc.) a
    # thaikryddad kycklingfilé would appear in French or Italian recipes
    # where the seasoning profile is completely wrong.
    'thaikryddad': {
        'thai', 'thaikryddad', 'wok', 'pad', 'asiatisk', 'asian',
        'kokosmjölk', 'lemongrass', 'citrongräs',
        'fisksås', 'röd curry', 'grön curry', 'panang', 'massaman',
        'sriracha', 'koriander', 'lime',
        # 'ingefära' removed — too generic, also used in Persian/Moroccan/Mediterranean
        # recipes and should not alone trigger thai product context.
    },
}
