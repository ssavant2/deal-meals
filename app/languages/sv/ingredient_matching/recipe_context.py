"""Recipe-context rules for Swedish ingredient matching."""

import re
from typing import Dict, FrozenSet, Set

try:
    from languages.sv.normalization import fix_swedish_chars
except ModuleNotFoundError:
    from app.languages.sv.normalization import fix_swedish_chars

from .runtime_rule_overlays import CUISINE_CONTEXT_CLI_UPDATES


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
        'tortillabröd',
    },
    'texmex': {
        'taco', 'tacos', 'texmex', 'tex mex', 'tex-mex',
        'mexikansk', 'burrito', 'fajita', 'enchilada',
        'quesadilla', 'nacho', 'nachos', 'wrap',
        'tortillabröd',
    },
    'tex mex': {
        'taco', 'tacos', 'texmex', 'tex mex', 'tex-mex',
        'mexikansk', 'burrito', 'fajita', 'enchilada',
        'quesadilla', 'nacho', 'nachos', 'wrap',
        'tortillabröd',
    },
    # Gyros / Greek-marinated chicken products require a Greek recipe context.
    # 'pita' removed — pita is shared across Greek/Middle-Eastern/Turkish
    # cuisines (shawarma, kebab, dürüm all use it). 'grekisk' removed because
    # it leaks into Indian/Mediterranean recipes via "grekisk yoghurt" (a
    # generic dairy term used worldwide, not a Greek-cuisine marker). Genuine
    # Greek recipes still trigger via gyros/souvlaki/tzatziki/kalamata or
    # named dish words (moussaka, pastitsio, spanakopita, dolmades).
    'gyros': {
        'gyros', 'souvlaki', 'medelhav',
        'tzatziki', 'kalamata',
        'moussaka', 'pastitsio',
        'dolma', 'dolmades',
        'spanakopita', 'tiropita',
        'taramosalata',
    },
    # Thaikryddad products require a Thai/Asian recipe context.
    # Without thai context (wok, pad thai, curry markers, etc.) a thaikryddad
    # kycklingfilé would appear in French or Italian recipes where the
    # seasoning profile is completely wrong.
    # Korean-cuisine products (Korean Style kyckling, Bulgogi etc.) should only
    # appear in Korean-context recipes. Without these cues a Korean Style
    # marinated kycklingfilé would show up in Italian or Indian recipes where
    # the seasoning is completely wrong.
    'koreansk': {
        'koreansk', 'korean', 'korean style', 'kbbq', 'korean bbq',
        # Korean dish names — strong signal that the recipe is Korean
        'bulgogi', 'bibimbap', 'tteokbokki', 'japchae', 'galbi',
        'samgyeopsal', 'kimbap', 'mandu',
        # Korean pantry ingredients distinctive to Korean cooking
        'kimchi', 'gochujang', 'gochugaru', 'ssamjang', 'doenjang',
        'koreansk chilipasta', 'koreansk chiliflakes',
    },
    'thaikryddad': {
        # General cuisine/cooking-style cues.
        # 'wok' removed (Q79-5): wok is too generic — teriyaki, sukiyaki, kinesisk wok all use the
        # word but are NOT thai. Thaikryddad products must require explicit thai markers
        # (thai/pad/asiatisk) rather than the wok cooking method.
        'thai', 'thaikryddad', 'pad', 'asiatisk', 'asian',
        # Thai pantry ingredients that are distinctive to thai/southeast-asian cooking
        'lemongrass', 'citrongräs', 'fisksås',
        'kaffirlime', 'kaffirlimeblad', 'palmsocker',
        'thaibasilika', 'thai basilika',
        # Thai curry names — recipe wording rather than just ingredient
        'röd curry', 'grön curry', 'gul curry', 'panang', 'massaman', 'gaeng',
        # Thai dish-name fragments — these phrases almost always indicate a thai recipe
        'pad thai', 'pad krapow', 'pad see ew', 'pad kee mao',
        'tom yum', 'tom kha',
        'khao pad', 'khao soi', 'khao man gai',
        'som tam', 'krapow',
        # Thai chili sauce
        'sriracha',
        # 'kokosmjölk' removed — too generic (Indian/Caribbean/African recipes
        #   also use coconut milk extensively, e.g. tikka masala, korma).
        # 'koriander' removed — too generic (Mexican/Indian/Middle-Eastern/American also use it)
        # 'ingefära' removed — too generic, also used in Persian/Moroccan/Mediterranean
        # 'lime' removed — too generic, also used in Mexican/Caribbean/Mediterranean cuisines
    },
}


def _merge_normalized_context_updates(
    target: Dict[str, Set[str]],
    updates: Dict[str, Set[str]],
) -> None:
    for trigger, contexts in updates.items():
        target.setdefault(fix_swedish_chars(trigger).lower(), set()).update(
            {fix_swedish_chars(context).lower() for context in contexts}
        )


_merge_normalized_context_updates(CUISINE_CONTEXT, CUISINE_CONTEXT_CLI_UPDATES)
