"""Recipe-text utilities shared by Swedish ingredient matching flows."""

import re
from typing import FrozenSet, List

from .specialty_rules import SPECIALTY_QUALIFIERS


_STOCK_PREFIX_MAP = {'höns': 'kyckling', 'hons': 'kyckling'}

_STOCK_PREFIXES = r'kyckling|höns|hons|grönsaks|gronsaks|fisk|kött|kott|kalv|svamp|skaldjurs|hummer|ox'

_BULJONG_ELLER_FOND_RE = re.compile(
    rf'({_STOCK_PREFIXES})buljong\w*(.*?)\beller\s+fond\b', re.IGNORECASE
)

_FOND_ELLER_BULJONG_RE = re.compile(
    rf'({_STOCK_PREFIXES})fond\w*(.*?)\beller\s+(buljong\w*)', re.IGNORECASE
)

_CHEESE_PREFERENCE_PAREN_RE = re.compile(r'\((?:gärna|garnaå?|helst)\s+(?:med\s+)?([^)]*)\)', re.IGNORECASE)
_CHILI_ALIAS_PAREN_RE = re.compile(
    r'\b((?:röd|rod|grön|gron|gul)\s+)?peppar\s*\(\s*chili(?:peppar)?\s*\)',
    re.IGNORECASE,
)
_NON_CONCENTRATE_PAREN_RE = re.compile(
    r'\(\s*((?:ej|inte)\s+(?:koncentrerad|koncentrerat|koncentrerade)|(?:okoncentrerad|okoncentrerat|okoncentrerade))\s*\)',
    re.IGNORECASE,
)
_FRESH_PASTA_PAREN_RE = re.compile(
    r'\b('
    r'pasta|långpasta|langpasta|spaghetti|spagetti|linguine|tagliatelle|'
    r'fettuccine|fettuccini|fettucine|pappardelle|tagliolini|bucatini|capellini'
    r')\s*\(\s*färsk\s*\)',
    re.IGNORECASE,
)
_SHISO_HERB_ALT_PAREN_RE = re.compile(
    r'\bshisoblad\s*\(([^)]*?\beller\b[^)]*)\)',
    re.IGNORECASE,
)
_GROUPED_HERB_LEAF_PAREN_RE = re.compile(
    r'\b(örtblad|ortblad)\s*\(([^)]*)\)',
    re.IGNORECASE,
)
_BIFF_PORTION_PREP_RE = re.compile(
    r',\s*delad(?:e|t)?\s+i\s+\d+\s+biffar?\b.*$',
    re.IGNORECASE,
)
_SUBRECIPE_REFERENCE_RE = re.compile(
    r'\bgrundrecept\b|\bse\s+länk\s+i\s+ingress\b',
    re.IGNORECASE,
)
_CHEESE_PREFERENCE_QUALIFIERS: FrozenSet[str] = frozenset(
    q.lower() for q in SPECIALTY_QUALIFIERS.get('ost', set())
)
_PAREN_ALT_RE = re.compile(r'^(.*?)\(([^)]*?\beller\b[^)]*)\)\s*$', re.IGNORECASE)
_LEAF_ALT_SPLIT_RE = re.compile(r'\s*,\s*|\s+eller\s+', re.IGNORECASE)
_PLUS_SPLIT_RE = re.compile(r'\s+\+\s+')
_HERB_LIST_SPLIT_RE = re.compile(r'\s*,\s*|\s+och\s+', re.IGNORECASE)
_EXAMPLE_SIGNAL_RE = re.compile(r'(?:t\.?\s*ex\.?|exempelvis|till\s+exempel)\s+(.+)', re.IGNORECASE)
_EXAMPLE_BASE_RE = re.compile(r'(.+?)\s*(?:t\.?\s*ex\.?|exempelvis|till\s+exempel)\s', re.IGNORECASE)
_PAREN_EXAMPLE_RE = re.compile(
    r'^(.*?)\(\s*(?:t\.?\s*ex\.?|exempelvis|till\s+exempel)\s+([^)]*)\)\s*$',
    re.IGNORECASE,
)
_MEASURE_PREFIX_ALT_RE = re.compile(
    r'^\s*((?:ca\s+)?\d+(?:[.,]\d+)?(?:\s*-\s*\d+(?:[.,]\d+)?)?\s*'
    r'(?:msk|tsk|krm|ml|cl|dl|l|g|kg|st))\s+([^\s,]+)\s*$',
    re.IGNORECASE,
)
_LEADING_MEASURE_PREFIX_RE = re.compile(
    r'^\s*(?:ca\s+)?\d+(?:[.,]\d+)?(?:\s*-\s*\d+(?:[.,]\d+)?)?\s*'
    r'(?:msk|tsk|krm|ml|cl|dl|l|g|kg|st)\b',
    re.IGNORECASE,
)
_TRUNCATED_ELLER_SUFFIXES = tuple(sorted((
    'buljongtärningar', 'buljongtarningar',
    'buljongtärning', 'buljongtarning',
    'buljong', 'fond',
    'filéer', 'fileer', 'filé', 'file',
    'färs', 'fars',
    'olja',
    'peppar',
    'kål', 'kal',
), key=len, reverse=True))
_TRUNCATED_ELLER_COMPOUND_RE = re.compile(
    rf'\b([a-zåäöé]+)-\s+eller\s+([a-zåäöé]+?)({"|".join(re.escape(s) for s in _TRUNCATED_ELLER_SUFFIXES)})\b',
    re.IGNORECASE,
)
_MINCE_OF_ALT_RE = re.compile(
    r'\bfärs\s+av\s+([a-zåäöé]+(?:\s*,\s*[a-zåäöé]+)*)\s+eller\s+([a-zåäöé]+)\b',
    re.IGNORECASE,
)
_ANIMAL_PART_OR_MINCE_RE = re.compile(
    r'\b('
    r'kyckling[a-zåäöé]*|'
    r'kalkon[a-zåäöé]*|'
    r'lamm[a-zåäöé]*|'
    r'kalv[a-zåäöé]*|'
    r'nöt[a-zåäöé]*|not[a-zåäöé]*|'
    r'fläsk[a-zåäöé]*|flask[a-zåäöé]*|'
    r'hjort[a-zåäöé]*|'
    r'får[a-zåäöé]*|far[a-zåäöé]*|'
    r'vildsvin[a-zåäöé]*|'
    r'älg[a-zåäöé]*|alg[a-zåäöé]*'
    r')\s+eller\s+färs\b',
    re.IGNORECASE,
)
_MINCE_ANIMAL_TO_COMPOUND = {
    'nöt': 'nötfärs',
    'not': 'nötfärs',
    'kalv': 'kalvfärs',
    'lamm': 'lammfärs',
    'fläsk': 'fläskfärs',
    'flask': 'fläskfärs',
    'kyckling': 'kycklingfärs',
    'kalkon': 'kalkonfärs',
    'hjort': 'hjortfärs',
    'får': 'fårfärs',
    'far': 'fårfärs',
    'vildsvin': 'vildsvinsfärs',
    'älg': 'älgfärs',
    'alg': 'älgfärs',
}
_HERB_WORDS = (
    'timjan', 'rosmarin', 'persilja', 'dill', 'koriander',
    'gräslök', 'graslok', 'basilika', 'oregano', 'dragon', 'mynta',
)
_SHORT_LEAF_ALTS = frozenset({
    'vit', 'vita', 'röd', 'rod', 'röda', 'roda',
    'grön', 'gron', 'gröna', 'grona', 'spets',
})

def rewrite_buljong_eller_fond(text: str) -> str:
    """Rewrite generic stock alternatives to specific ones in both directions.

    'kycklingbuljong eller fond' → 'kycklingbuljong eller kycklingfond'
    'kycklingfond eller buljong' → 'kycklingfond eller kycklingbuljong'
    """
    # Direction 1: buljong → fond
    text = _BULJONG_ELLER_FOND_RE.sub(
        lambda m: m.group(0).replace(
            'eller fond',
            f'eller {_STOCK_PREFIX_MAP.get(m.group(1).lower(), m.group(1).lower())}fond'
        ),
        text
    )
    # Direction 2: fond → buljong
    def _rewrite_fond_to_buljong(m):
        prefix = _STOCK_PREFIX_MAP.get(m.group(1).lower(), m.group(1).lower())
        buljong_word = m.group(3)  # "buljong" or "buljongtärning" etc
        return m.group(0).replace(f'eller {buljong_word}', f'eller {prefix}{buljong_word}')
    text = _FOND_ELLER_BULJONG_RE.sub(_rewrite_fond_to_buljong, text)
    return text


def preserve_cheese_preference_parentheticals(text: str) -> str:
    """Keep named cheese preferences from '(helst X)' while stripping the parens.

    This is intentionally narrow: only cheese preference parentheticals attached
    to an ost-ingredient are preserved, and only when they mention a specific
    cheese qualifier such as "gruyère" or "parmesan".
    """
    lowered = text.lower()
    if 'ost' not in lowered:
        return text

    def _replace(match):
        content = match.group(1).strip().lower()
        words = re.findall(r'[a-zåäöéèü]+', content)
        kept = [word for word in words if word in _CHEESE_PREFERENCE_QUALIFIERS]
        if not kept:
            return ''
        return ' ' + ' '.join(dict.fromkeys(kept))

    return _CHEESE_PREFERENCE_PAREN_RE.sub(_replace, text)


def preserve_parenthetical_chili_alias(text: str) -> str:
    """Keep parenthetical chili clarifiers from fresh-pepper wording.

    Examples:
    - "röd peppar (chili)" -> "röd chilipeppar"
    - "grön peppar (chilipeppar)" -> "grön chilipeppar"
    - "peppar (chili)" -> "chilipeppar"
    """

    def _replace(match):
        color = match.group(1) or ''
        return f"{color}chilipeppar"

    return _CHILI_ALIAS_PAREN_RE.sub(_replace, text)


def preserve_non_concentrate_parenthetical(text: str) -> str:
    """Keep explicit non-concentrate cues before generic parenthetical stripping.

    Example:
    - "lingondryck (ej koncentrerat)" -> "lingondryck ej koncentrerat"
    """

    return _NON_CONCENTRATE_PAREN_RE.sub(lambda m: f" {m.group(1).strip()} ", text)


def preserve_fresh_pasta_parenthetical(text: str) -> str:
    """Keep explicit fresh-pasta cues before generic parenthetical stripping.

    Examples:
    - "fettuccine (färsk)" -> "fettuccine färsk"
    - "pasta (färsk)" -> "pasta färsk"
    """

    return _FRESH_PASTA_PAREN_RE.sub(lambda m: f"{m.group(1)} färsk", text)


def preserve_parenthetical_shiso_alternatives(text: str) -> str:
    """Lift stated herb fallbacks out of shiso parentheticals.

    Example:
    - "shisoblad (mynta, thaibasilika eller koriander)"
      -> "shisoblad eller mynta eller thaibasilika eller koriander"
    """

    if 'shisoblad' not in text.lower():
        return text

    def _replace(match):
        raw = match.group(1).strip().lower()
        items = [
            item.strip().strip('() ')
            for item in re.split(r'\s*,\s*|\s+och\s+|\s+eller\s+', raw)
            if item.strip()
        ]
        allowed = []
        for item in items:
            if item in {'mynta', 'thaibasilika', 'koriander'} and item not in allowed:
                allowed.append(item)
        if len(allowed) < 2:
            return match.group(0)
        return 'shisoblad eller ' + ' eller '.join(allowed)

    return _SHISO_HERB_ALT_PAREN_RE.sub(_replace, text)


def preserve_parenthetical_grouped_herb_leaves(text: str) -> str:
    """Keep named herb leaves from grouped örtblad parentheticals.

    Example:
    - "plockade örtblad (mynta koriander , dill)"
      -> "plockade örtblad mynta koriander dill"

    Keep this narrow to grouped herb-leaf wording so we do not start lifting
    arbitrary parenthetical descriptions into ingredient text.
    """

    lowered = text.lower()
    if 'örtblad' not in lowered and 'ortblad' not in lowered:
        return text

    def _replace(match):
        carrier = match.group(1)
        raw = match.group(2).strip().lower()
        found = []
        for token in re.findall(r'[a-zåäöéèü]+', raw):
            if token in _HERB_WORDS and token not in found:
                found.append(token)
        if len(found) < 2:
            return match.group(0)
        return f"{carrier} {' '.join(found)}"

    return _GROUPED_HERB_LEAF_PAREN_RE.sub(_replace, text)


def strip_biff_portion_prep_phrase(text: str) -> str:
    """Strip prep-only steak-shaping phrases from larger meat cuts.

    Example:
    - "800 g högrev, delad i 4 biffar" -> "800 g högrev"

    Keep this narrow to the explicit ", delad i X biffar" wording so real
    steak/biff ingredients continue to match as before.
    """

    return _BIFF_PORTION_PREP_RE.sub('', text)


def is_subrecipe_reference_text(text: str) -> bool:
    """Return True for non-buyable references to a separate subrecipe.

    Examples:
    - "2 portioner Glass LCHF - Grundrecept"
    - "surdegsstart (se grundrecept)"
    - "1 sats pastadeg (se länk i ingress)"
    """

    return bool(_SUBRECIPE_REFERENCE_RE.search(text))


def rewrite_truncated_eller_compounds(text: str) -> str:
    """Expand shorthand alternatives where the first option omits a shared suffix.

    Examples:
    - "sill- eller strömmingsfiléer" -> "sillfiléer eller strömmingsfiléer"
    - "sej- eller torskfilé" -> "sejfilé eller torskfilé"
    - "röd- eller vitkål" -> "rödkål eller vitkål"
    """
    return _TRUNCATED_ELLER_COMPOUND_RE.sub(
        lambda m: f"{m.group(1)}{m.group(3)} eller {m.group(2)}{m.group(3)}",
        text,
    )


def rewrite_mince_of_alternatives(text: str) -> str:
    """Expand animal-mince alternatives into explicit mince compounds.

    Examples:
    - "färs av kalv eller nöt" -> "kalvfärs eller nötfärs"
    - "färs av lamm, kalv eller nöt" -> "lammfärs, kalvfärs eller nötfärs"
    - "kycklingbröstfilé eller färs" -> "kycklingbröstfilé eller kycklingfärs"
    """

    def _replace(match):
        left_animals = [part.strip().lower() for part in match.group(1).split(',') if part.strip()]
        animals = left_animals + [match.group(2).strip().lower()]
        compounds = [_MINCE_ANIMAL_TO_COMPOUND.get(animal) for animal in animals]
        if not all(compounds):
            return match.group(0)
        if len(compounds) == 2:
            return f"{compounds[0]} eller {compounds[1]}"
        return f"{', '.join(compounds[:-1])} eller {compounds[-1]}"

    text = _MINCE_OF_ALT_RE.sub(_replace, text)

    def _replace_same_animal_minced(match):
        animal_part = match.group(1)
        lowered = animal_part.lower()
        animal = None
        for prefix in _MINCE_ANIMAL_TO_COMPOUND:
            if lowered.startswith(prefix):
                animal = prefix
                break
        if not animal:
            return match.group(0)
        return f"{animal_part} eller {_MINCE_ANIMAL_TO_COMPOUND[animal]}"

    return _ANIMAL_PART_OR_MINCE_RE.sub(_replace_same_animal_minced, text)


def expand_grouped_ingredient_text(ingredient_text: str) -> List[str]:
    """Expand a raw ingredient line into logical ingredient/group rows.

    Rules:
    - `X + Y + Z` becomes multiple separate ingredient rows
    - parenthetical leaf-cabbage alternatives become one `eller` row
    - generic fresh-herb bundle lines become one row per named herb
    - everything else stays as a single row
    """
    text = ingredient_text.strip()
    if not text:
        return []

    if _PLUS_SPLIT_RE.search(text):
        parts = [part.strip() for part in _PLUS_SPLIT_RE.split(text) if part.strip()]
        if len(parts) >= 2:
            return parts

    paren_match = _PAREN_ALT_RE.match(text)
    if paren_match:
        inside = paren_match.group(2).strip().lower()
        items = [item.strip().strip('() ') for item in _LEAF_ALT_SPLIT_RE.split(inside) if item.strip()]
        if len(items) >= 2 and items[-1].endswith('kål'):
            suffix = 'kål'
            expanded = []
            for item in items:
                if item.endswith(suffix):
                    expanded.append(item)
                elif item in _SHORT_LEAF_ALTS:
                    expanded.append(item + suffix)
            if len(expanded) == len(items):
                return [' eller '.join(expanded)]

    lowered = ingredient_text.lower()
    if (
        'örter' in lowered or 'orter' in lowered
        or 'örtblad' in lowered or 'ortblad' in lowered
    ):
        found = []
        for herb in _HERB_WORDS:
            pattern = r'\b' + re.escape(herb) + r'\b'
            if re.search(pattern, lowered):
                if herb not in found:
                    found.append(herb)
        if len(found) >= 2:
            wants_fresh = any(word in lowered for word in ('färsk', 'farsk', 'färska', 'farska'))
            expanded = []
            for herb in found:
                herb_text = herb.replace('graslok', 'gräslök')
                if wants_fresh and not herb_text.startswith('färsk '):
                    herb_text = f"färsk {herb_text}"
                expanded.append(herb_text)
            return expanded

    return [text]

def parse_eller_alternatives(ingredient_text: str) -> List[str]:
    """
    Parse "eller" (or) and example-list patterns in Swedish ingredient text.

    Detects patterns like:
    - "X eller Y" → ['X', 'Y']
    - "blandade frukter t.ex. ananas, druvor, kiwi" → ['blandade frukter', 'ananas', 'druvor', 'kiwi']

    Args:
        ingredient_text: Raw ingredient text

    Returns:
        List of alternative ingredients
    """
    text = preserve_parenthetical_shiso_alternatives(ingredient_text.strip())
    text = rewrite_truncated_eller_compounds(text)
    text = rewrite_mince_of_alternatives(text)
    text_lower = text.lower()

    # --- Check for example-list patterns FIRST ---
    # Signal words: "t.ex.", "t ex", "t. ex.", "tex", "exempelvis"
    # These introduce comma-separated lists of alternatives.
    #
    # Two supported forms:
    # - outside parens: "blandade frukter t.ex. ananas, druvor, kiwi"
    # - whole parenthetical example list: "grönsaker (t.ex. morötter, majs)"
    #
    # But descriptive brand/example parentheticals such as
    # "(med ingefära och rödbeta t.ex. God Morgon drakfrukt, Ingefära)"
    # should NOT expand into shopping alternatives.
    paren_example_match = _PAREN_EXAMPLE_RE.match(text)
    if paren_example_match:
        base = paren_example_match.group(1).strip().rstrip(',').strip()
        items = re.split(r'\s*,\s*|\s+och\s+', paren_example_match.group(2))
        items = [item.strip().rstrip('.').strip('()') for item in items if item.strip()]
        if len(items) >= 2:
            alternatives = []
            if base:
                alternatives.append(base)
            alternatives.extend(items)
            return alternatives

    text_outside_parens = re.sub(r'\([^)]*\)', '', text)
    example_match = _EXAMPLE_SIGNAL_RE.search(text_outside_parens)
    if example_match:
        examples_part = example_match.group(1)
        # Split on comma and "och"/"and"
        items = re.split(r'\s*,\s*|\s+och\s+', examples_part)
        items = [item.strip().rstrip('.').strip('()') for item in items if item.strip()]
        if len(items) >= 2:
            # Include the base ingredient (part before signal word) + all examples
            base_match = _EXAMPLE_BASE_RE.match(text_outside_parens)
            alternatives = []
            if base_match:
                base = base_match.group(1).strip().rstrip(',').strip().rstrip('(').strip()
                if base:
                    alternatives.append(base)
            alternatives.extend(items)
            return alternatives

    # Quick check - if no "eller" present, return as-is
    # Also check "(eller" for parenthetical alternatives like "olivolja (eller smör)"
    text_lower_check = text_lower
    if ' eller ' not in text_lower_check and '(eller' not in text_lower_check:
        return [text]

    # Narrow list form: "1 msk anis, fänkål eller kummin" should become three
    # measured alternatives, not ["1 msk anis, fänkål", "kummin"].
    # Keep this strict so adjective/suffix patterns like
    # "choklad, mjölk-, mörk eller vit" continue down the normal parser path.
    if ',' in text and ' eller ' in text_lower_check:
        left, right = re.split(r'\s+eller\s+', text, maxsplit=1, flags=re.IGNORECASE)
        left_items = [item.strip() for item in left.split(',') if item.strip()]
        right_item = right.strip().rstrip(')')
        if len(left_items) >= 2 and right_item and ' ' not in right_item and right_item.lower() not in _SHORT_LEAF_ALTS:
            prefix_match = _MEASURE_PREFIX_ALT_RE.match(left_items[0])
            if prefix_match:
                prefix = prefix_match.group(1).strip()
                first_leaf = prefix_match.group(2).strip()
                sibling_leaves = left_items[1:] + [right_item]
                if all(' ' not in leaf and leaf.lower() not in _SHORT_LEAF_ALTS for leaf in sibling_leaves):
                    return [f"{prefix} {leaf}" for leaf in [first_leaf] + sibling_leaves]

    # Normalize text (lowercase for splitting, keep original case for return)
    text_lower = text.lower()

    # Split on " eller " (with spaces to avoid splitting "mellersta")
    # Also handle parenthetical: "olivolja (eller smör)" → split on "(eller "
    # Pattern: "X eller Y" or "X eller Y eller Z"
    parts = re.split(r'[\s(]+eller\s+', text, flags=re.IGNORECASE)

    if len(parts) <= 1:
        return [text]

    # Clean up each alternative (strip whitespace and trailing parentheses)
    alternatives = []
    for part in parts:
        part = part.strip().rstrip(')')
        part = part.strip()
        if part:
            alternatives.append(part)

    # Shared trailing usage phrases belong to all alternatives, not just the
    # last one. Example:
    # "Parmigiano Reggiano eller Grana Padano att toppa med"
    # should become
    # ["Parmigiano Reggiano att toppa med", "Grana Padano att toppa med"]
    # before the generic shared-suffix logic runs.
    if len(alternatives) >= 2:
        usage_match = re.search(r'\batt\s+[a-zåäöéèü0-9][a-zåäöéèü0-9\s-]*$', alternatives[-1], re.IGNORECASE)
        if usage_match:
            usage_tail = usage_match.group(0).strip()
            if not any(usage_tail in alt for alt in alternatives[:-1]):
                alternatives = [f"{alt} {usage_tail}".strip() for alt in alternatives[:-1]] + [alternatives[-1]]

    # Measured alternatives often omit the repeated quantity on later branches:
    # "1 dl vatten eller mjölk" should mean ["1 dl vatten", "1 dl mjölk"].
    # Keep this narrow to branches that do not already start with their own
    # explicit quantity.
    if len(alternatives) >= 2:
        prefix_match = _MEASURE_PREFIX_ALT_RE.match(alternatives[0])
        if prefix_match:
            prefix = prefix_match.group(1).strip()
            expanded = [alternatives[0]]
            for alt in alternatives[1:]:
                if _LEADING_MEASURE_PREFIX_RE.match(alt):
                    expanded.append(alt)
                else:
                    expanded.append(f"{prefix} {alt}".strip())
            alternatives = expanded

    # Handle shared prefix/suffix patterns
    # E.g., "frysta eller färska hallon" → "frysta hallon", "färska hallon"
    # Detect if last part has more words than first part
    if len(alternatives) >= 2:
        first_words = alternatives[0].split()
        last_words = alternatives[-1].split()

        # Check if last alternative has extra words (suffix)
        # "frysta" vs "färska hallon" → suffix = "hallon"
        if len(last_words) > len(first_words):
            # Potential shared suffix
            # Check how many words differ at the start
            # "färska hallon" - if "hallon" is common to all, it's the suffix
            suffix_words = last_words[1:]  # Everything after first word
            suffix = ' '.join(suffix_words)

            # Skip if suffix contains measurement words — indicates a separate
            # ingredient with its own quantity, not a shared suffix.
            # E.g., "köttbuljongtärning eller 1,5 msk kalvfond" → "msk" = measurement
            _MEASURE_WORDS = {'msk', 'tsk', 'dl', 'cl', 'ml', 'l', 'g', 'kg', 'st',
                              'krm', 'nypa', 'port', 'bit', 'bitar', 'skiva', 'skivor'}
            suffix_has_measure = any(w.lower() in _MEASURE_WORDS for w in suffix_words)
            head_looks_like_quantity = bool(re.match(r'^\d', last_words[0])) or (
                last_words[0].lower() in _MEASURE_WORDS
            )

            # Only apply suffix if first alt doesn't already have these words
            if (
                suffix
                and suffix not in alternatives[0]
                and not suffix_has_measure
                and not head_looks_like_quantity
            ):
                # Add suffix to all alternatives except the last one
                expanded = []
                for i, alt in enumerate(alternatives[:-1]):
                    # Only add suffix if alt is short (just the descriptor)
                    if len(alt.split()) < len(last_words):
                        expanded.append(f"{alt} {suffix}")
                    else:
                        expanded.append(alt)
                expanded.append(alternatives[-1])  # Last one already has suffix
                alternatives = expanded

    return alternatives if alternatives else [text]

def has_eller_pattern(ingredient_text: str) -> bool:
    """
    Quick check if ingredient text contains "eller" pattern.

    Args:
        ingredient_text: Raw ingredient text

    Returns:
        True if "eller" pattern detected
    """
    return ' eller ' in ingredient_text.lower()
