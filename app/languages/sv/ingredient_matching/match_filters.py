"""Match filtering helpers for Swedish ingredient matching.

Related data:
- blocker_data.py — FALSE_POSITIVE_BLOCKERS, PRODUCT_NAME_BLOCKERS
- extraction.py — PRODUCT_NAME_SUBSTITUTIONS is used during keyword extraction
- recipe_matcher.py — per-ingredient validation uses these helpers and tables
"""

from typing import Dict, FrozenSet, List, Set

try:
    from languages.sv.normalization import fix_swedish_chars
except ModuleNotFoundError:
    from app.languages.sv.normalization import fix_swedish_chars

from .blocker_data import FALSE_POSITIVE_BLOCKERS
from .compound_text import _WORD_PATTERN


_SECONDARY_INGREDIENT_PATTERNS_RAW: Dict[str, tuple] = {
    'rapsolja': ({'smör', 'smor', 'butter'}, set()),
    'olja': ({'smör', 'smor', 'butter'}, {'margarin'}),
    'solrosolja': (
        {'lax', 'laxfilé', 'sill', 'makrill', 'sardiner', 'tonfisk', 'ansjovis', 'fisk'},
        set()
    ),
    'smör': ({'rapsolja'}, set()),
    'ost': (
        {'paj', 'korv', 'pizza', 'burgare', 'burger', 'baguette', 'baguett',
         'macka', 'smörgås', 'wrap', 'panini', 'toast', 'quesadilla',
         'gratin', 'gratäng', 'lasagne', 'cannelloni', 'makaroner', 'pasta',
         'soppa', 'sås', 'dipp', 'chips', 'snacks', 'kex', 'bröd'},
        {'riven', 'skivor', 'skivad', 'block', 'bit', 'tärnad', 'gratängost'}
    ),
    'vitlök': (
        {'majo', 'majonäs', 'majonnäs', 'dressing', 'aioli', 'sås', 'sauce',
         'dipp', 'kryddsmör', 'smör', 'bröd', 'chips', 'croutonger'},
        {'klyft', 'klyftor', 'hel', 'hela', 'färsk', 'färska', 'pressad', 'hackad', 'finhackad'}
    ),
    'ägg': ({'kaviar'}, set()),
    'grillkrydda': (
        {'kyckling', 'fläsk', 'nöt', 'lax', 'korv', 'biff', 'torsk', 'bog',
         'karré', 'kotlett', 'entrecôte', 'entrecote', 'revben', 'rygg',
         'schnitzel', 'burgare', 'färs', 'fisk'},
        set()
    ),
    'oliver': ({'salttorkade', 'salttorkad', 'pimento'}, set()),
}


RECIPE_INGREDIENT_BLOCKERS: Dict[str, Set[str]] = {
    fix_swedish_chars(k).lower(): {fix_swedish_chars(w).lower() for w in v}
    for k, v in {
        'mango': {'balsamico', 'vinäger'},
        'vinbär': {'gelé'},
        'pasta': {'cannelloni'},
        'vitlök': {'färskost', 'farskost'},
        'kakao': {'granola'},
        'hallon': {'granola'},
        'chili': {'pesto', 'sweet', 'olivolja', 'grillolja', 'rapsolja', 'olja'},
        'citron': {'olivolja', 'grillolja', 'rapsolja', 'olja', 'tångpärlor', 'tangparlor'},
        'mandel': {'potatis'},
        'sparris': {'parmaskinka', 'skinka'},
        'ost': {'tortellini', 'tortelloni', 'ravioli'},
        'chicken': {'sås', 'sas', 'sauce', 'butter'},
        'basilika': {'pastasås', 'pastasas', 'tomatsås', 'tomatsas'},
        'koriander': {'dressing'},
        'äpple': {'balsamico', 'balsamvinäger'},
        'lime': {'tångpärlor', 'tangparlor'},
        'soja': {'tångpärlor', 'tangparlor'},
        # Mixed mince products like "Färs Nötkött och Linser" should not fall
        # through to plain lentil bags via the generic lentil keyword alone.
        'linser': {'nötkött', 'notkott'},
        'marinad': {'soltorkade', 'soltorkad'},
        # "vinägermarinad från löken" is leftover pickling liquid, not a prompt
        # to buy fresh onions or bottled vinegar again.
        'lök': {'vinägermarinad', 'vinagermarinad'},
        'lok': {'vinägermarinad', 'vinagermarinad'},
        'vinäger': {'vinägermarinad', 'vinagermarinad'},
        'vinager': {'vinägermarinad', 'vinagermarinad'},
        'balsamvinäger': {'vinägermarinad', 'vinagermarinad'},
        'balsamvinager': {'vinägermarinad', 'vinagermarinad'},
    }.items()
}


def _is_false_positive_blocked(keyword: str, ingredient_lower: str) -> bool:
    """Check if a keyword match is a false positive based on blocker words."""
    # Stjärnanis is a special case: the plain-anis blocker is meant to stop
    # regular anis products, not genuine stjärnanis products like "Stjärnanis Hel".
    if keyword in {'stjärnanis', 'stjarnanis'} and 'stjärn' in ingredient_lower:
        return False
    if keyword not in FALSE_POSITIVE_BLOCKERS:
        return False
    blockers = FALSE_POSITIVE_BLOCKERS[keyword]
    if not any(b in ingredient_lower for b in blockers):
        return False
    words_in_text = _WORD_PATTERN.findall(ingredient_lower)
    for w in words_in_text:
        if keyword not in w:
            continue
        if w == keyword:
            return False
        if w.startswith(keyword):
            if not any(w.startswith(b) for b in blockers):
                return False
        elif w.endswith(keyword) or keyword in w:
            if not any(b in w for b in blockers):
                return False
    return True


_QUALIFIER_REQUIRED_KEYWORDS: FrozenSet[str] = frozenset({
    fix_swedish_chars(w).lower() for w in {
        'dressing',
        'inlagd', 'inlagda',
    }
})


PRODUCT_NAME_SUBSTITUTIONS: List[tuple] = [
    ({'apelsin', 'röd'}, 'apelsin', 'blodapelsin'),
    ({'apelsin', 'rod'}, 'apelsin', 'blodapelsin'),
    ({'fuet'}, 'salami', 'fuet'),
    ({'lök', 'röd'}, 'lök', 'rödlök'),
    ({'lok', 'röd'}, 'lok', 'rödlök'),
    ({'lök', 'rod'}, 'lök', 'rödlök'),
    ({'lok', 'rod'}, 'lok', 'rödlök'),
    ({'lök', 'vit'}, 'lök', 'vitlök'),
    ({'lok', 'vit'}, 'lok', 'vitlök'),
    ({'smörgåsmargarin'}, 'smörgåsmargarin', 'margarin'),
    ({'smorgasmargarin'}, 'smorgasmargarin', 'margarin'),
    ({'bordsmargarin'}, 'bordsmargarin', 'margarin'),
    ({'peppar', 'röd'}, 'peppar', 'chili'),
    ({'peppar', 'rod'}, 'peppar', 'chili'),
    ({'peppar', 'grön'}, 'peppar', 'chili'),
    ({'peppar', 'gron'}, 'peppar', 'chili'),
    ({'bbq', 'sås'}, 'sås', 'bbqsås'),
    ({'bbq', 'sauce'}, 'sauce', 'bbqsås'),
    ({'bbq', 'glaze'}, 'glaze', 'bbqsås'),
]


SECONDARY_INGREDIENT_PATTERNS: Dict[str, tuple] = {
    fix_swedish_chars(k).lower(): (
        {fix_swedish_chars(b).lower() for b in blockers},
        {fix_swedish_chars(e).lower() for e in exceptions}
    )
    for k, (blockers, exceptions) in _SECONDARY_INGREDIENT_PATTERNS_RAW.items()
}


def check_secondary_ingredient_patterns(product_lower: str, ingredient_lower: str,
                                        matched_keyword: str = "") -> bool:
    """Check if a match passes secondary ingredient pattern filters."""
    if matched_keyword:
        entry = SECONDARY_INGREDIENT_PATTERNS.get(matched_keyword)
        if entry:
            blockers, exceptions = entry
            for blocker in blockers:
                if blocker in product_lower:
                    if not any(exc in product_lower for exc in exceptions):
                        return False
        return True

    for search_word, (blockers, exceptions) in SECONDARY_INGREDIENT_PATTERNS.items():
        if search_word in ingredient_lower:
            for blocker in blockers:
                if blocker in product_lower:
                    if not any(exc in product_lower for exc in exceptions):
                        return False
    return True
