"""Matching engine for Swedish ingredient matching.

Related data:
- blocker_data.py — FALSE_POSITIVE_BLOCKERS
- carrier_context.py — carrier/context requirements and suppressors
- processed_rules.py — processed-product and spice/fresh rule data
- specialty_rules.py — specialty qualifier data
- validators.py — per-ingredient validation helpers used by recipe_matcher.py
"""

import re
from typing import Dict, Iterable, List, Optional

try:
    from languages.sv.normalization import fix_swedish_chars
except ModuleNotFoundError:
    from app.languages.sv.normalization import fix_swedish_chars

from .blocker_data import FALSE_POSITIVE_BLOCKERS
from .carrier_context import (
    _CARRIER_MULTI_WORDS,
    _CARRIER_SINGLE_WORDS,
    CARRIER_CONTEXT_REQUIRED,
    CONTEXT_REQUIRED_WORDS,
    _EMPTY_FROZENSET,
    CONTEXT_WORD_KEYWORD_EXEMPTIONS,
    INGREDIENT_REQUIRES_IN_PRODUCT,
    KEYWORD_SUPPRESSED_BY_CONTEXT,
)
from .compound_text import (
    _SUFFIX_PROTECTED_KEYWORDS,
    _EMBEDDED_PROTECTED_KEYWORDS,
    _COMPOUND_STRICT_KEYWORDS,
    _COMPOUND_STRICT_PREFIX_KEYWORDS,
    _check_compound_strict,
    _has_word_boundary_match,
    _has_word_edge_match,
    _WORD_PATTERN,
    _WORD_PATTERN_4PLUS,
    _RE_SPICE_AMOUNT,
)
from .extraction import extract_keywords_from_product
from .extraction_patterns import _INGREDIENT_PARENTS_REVERSE, _PARENS_PATTERN
from .form_rules import (
    FRESH_HERB_KEYWORDS,
    FRESH_PRODUCT_INDICATORS,
    DRIED_PRODUCT_INDICATORS,
    FROZEN_PRODUCT_INDICATORS,
    RECIPE_FRESH_INDICATORS,
    RECIPE_FRESH_VOLUME_INDICATORS,
    RECIPE_DRIED_INDICATORS,
    RECIPE_FROZEN_INDICATORS,
    JUICE_PRODUCT_INDICATORS,
    JUICE_INGREDIENT_INDICATORS,
    JUICE_RULE_KEYWORDS,
)
from .keywords import FLAVOR_WORDS, IMPORTANT_SHORT_KEYWORDS, OFFER_EXTRA_KEYWORDS
from .match_filters import (
    _QUALIFIER_REQUIRED_KEYWORDS,
    SECONDARY_INGREDIENT_PATTERNS,
)
from .normalization import (
    _SPACE_NORM_LOOKUP,
    _SPACE_NORM_PATTERN,
    _apply_space_normalizations,
    normalize_measured_durumvete_flour,
    normalize_measured_risotto_rice,
)
from .parent_maps import PARENT_MATCH_ONLY
from .processed_rules import (
    PROCESSED_RULES_COMPOUND_EXEMPTIONS,
    PROCESSED_PRODUCT_RULES,
    STRICT_PROCESSED_RULES,
    _PROCESSED_INDICATOR_EQUIVALENTS,
    SPICE_VS_FRESH_RULES,
)
from .recipe_context import CUISINE_CONTEXT
from .recipe_text import (
    is_subrecipe_reference_text,
    preserve_cheese_preference_parentheticals,
    preserve_fresh_pasta_parenthetical,
    preserve_parenthetical_chili_alias,
    preserve_parenthetical_grouped_herb_leaves,
    preserve_non_concentrate_parenthetical,
    preserve_parenthetical_shiso_alternatives,
    strip_biff_portion_prep_phrase,
    rewrite_mince_of_alternatives,
    rewrite_truncated_eller_compounds,
)
from .specialty_rules import (
    SPECIALTY_QUALIFIERS,
    BIDIRECTIONAL_SPECIALTY_QUALIFIERS,
    BIDIRECTIONAL_PER_KEYWORD,
    QUALIFIER_EQUIVALENTS,
)
from .validators import check_specialty_qualifiers, ingredient_has_spice_indicator
from .synonyms import INGREDIENT_PARENTS, KEYWORD_SYNONYMS

_RE_CHILI_COUNT_FRESH = re.compile(
    r'\b\d+\s*(?:st\s+)?(?:chili|chilipeppar|chilifrukt|chilifrukter)\b'
)
_SWEET_CHILI_QUALIFIERS = frozenset({'sweet', 'söt', 'sota'})
_UNSWEETENED_CHILI_QUALIFIERS = frozenset({'osötad', 'osotad', 'osötat', 'osotat'})
_RE_ANIS_WORD = re.compile(r'\banis\b')
_RE_KUMMIN_WORD = re.compile(r'\bkummin\b')
_COOKED_KYCKLINGKLUBBA_INGREDIENT_CUES = frozenset({
    'färdiggrillad', 'fardiggrillad',
    'grillad', 'grillade', 'grillat',
    'färdigstekt', 'fardigstekt',
    'stekt', 'stekta',
    'tillagad', 'tillagade',
    'färdiglagad', 'fardiglagad',
    'kokt', 'kokta',
    'rökt', 'rokt',
})
_PALAGG_DELI_KEYWORD_EXEMPTIONS = frozenset({'salami', 'salame'})
_COOKED_KYCKLING_PRODUCT_CUES = frozenset({
    'färdigkyckling',
    'färdiggrillad', 'fardiggrillad',
    'grillad', 'grillade', 'grillat',
    'färdigstekt', 'fardigstekt',
    'stekt', 'stekta',
    'tillagad', 'tillagade',
    'färdiglagad', 'fardiglagad',
    'kokt', 'kokta',
    'rökt', 'rokt',
    'sous vide',
    'ätklar', 'atklar',
})
_NON_CONCENTRATE_INGREDIENT_CUES = frozenset({
    'ej koncentrerat', 'ej koncentrerad',
    'inte koncentrerat', 'inte koncentrerad',
    'okoncentrerad', 'okoncentrerat',
})
_LONG_PASTA_INGREDIENT_CUES = frozenset({
    'långpasta', 'langpasta',
    'spaghetti', 'spagetti',
    'linguine',
    'tagliatelle',
    'fettuccine', 'fettuccini', 'fettucine',
    'pappardelle',
    'tagliolini',
    'bucatini',
    'capellini',
})
_NON_PASTA_LONG_PASTA_COMPOUND_CUES = frozenset({
    'kålrotsspaghetti', 'kalrotsspaghetti',
})
_ROE_FAMILY_INGREDIENT_CUES = {
    'stenbitsrom': frozenset({'stenbitsrom', 'storkornskaviar'}),
    'löjrom': frozenset({'löjrom', 'lojrom'}),
    'forellrom': frozenset({'forellrom'}),
    # Treat rainbow-trout roe as part of the salmon-roe family when recipes
    # use the shorter "regnbågsrom" wording.
    'laxrom': frozenset({'laxrom', 'regnbågsrom', 'regnbagsrom', 'regnbågslaxrom', 'regnbagslaxrom'}),
    'sikrom': frozenset({'sikrom'}),
}
_CONTEXT_WORD_INGREDIENT_ALIASES = {
    # "Pastasås Tomatsås ..." products are still tomato sauce in everyday
    # recipe language, even when the product carrier is the broader pastasås.
    # Keep this narrow: the ingredient alias only satisfies the context check
    # if the product itself also contains the alias.
    'pastasås': frozenset({'tomatsås', 'tomatsas'}),
}
_SPECIALTY_KEYWORD_ALIASES = {
    # Fresh chili family has several recipe-side surface forms that should all
    # use the same color qualifier logic ("röd" != "grön").
    'chilipeppar': 'chili',
    'chilifrukt': 'chili',
    'chilifrukter': 'chili',
    # Smoked paprika qualifiers are stored on the base paprika family even when
    # the ingredient/product keyword itself is "paprikapulver".
    'paprikapulver': 'paprika',
    'paprikakrydda': 'paprika',
}
_INGREDIENT_PARENT_TEXT_ALIASES = {
    # Ordinary short pasta shapes should behave like generic "pasta" in recipe
    # wording. Keep this one-way on the ingredient side so a shape ingredient
    # can match plain dry pasta, without making every pasta product pretend to
    # be every individual shape in cached/product precompute.
    'fusilli': 'pasta',
    'penne': 'pasta',
    'rigatoni': 'pasta',
    'farfalle': 'pasta',
    'conchiglie': 'pasta',
    'conchigle': 'pasta',
    'gemelli': 'pasta',
    'radiatori': 'pasta',
    'tortiglioni': 'pasta',
    'caserecce': 'pasta',
    'girandole': 'pasta',
    'strozzapreti': 'pasta',
    'strozzapretti': 'pasta',
    'orecchiette': 'pasta',
    'mafalda': 'pasta',
    'maniche': 'pasta',
    'ziti': 'pasta',
    'makaroner': 'pasta',
    'maccaronetti': 'pasta',
}
_ROM_SPIRIT_INGREDIENT_CUES = frozenset({
    'ljus rom', 'mörk rom', 'mork rom',
    'vit rom', 'white rum', 'dark rum',
})
_SWEET_DOUGH_YEAST_INGREDIENT_CUES = frozenset({'söt', 'sota', 'söta', 'sota'})
_CHICKPEA_KEYWORDS = frozenset({'kikärtor', 'kikartor', 'kikärter', 'kikarter'})
_READY_PACKAGED_CHICKPEA_INGREDIENT_CUES = frozenset({
    'spad', 'aquafaba',
    'kokt', 'kokta',
    'förkokt', 'förkokta',
    'färdigkokt', 'fardigkokt',
    'färdigkokta', 'fardigkokta',
    'burk', 'tetra',
    'frp', 'förp', 'forp',
    'fpk', 'pkt',
    'förpackning', 'forpackning',
    'avrunnen', 'avrunna',
    'sköljd', 'skoljd', 'sköljda', 'skoljda',
    'zeta',
})
_NON_READY_CHICKPEA_INGREDIENT_CUES = frozenset({
    'torr', 'torra',
    'torkad', 'torkade',
    'fryst', 'frysta',
    'rostad', 'rostade',
})
_READY_PACKAGED_CHICKPEA_MEASURE_RE = re.compile(r'\b\d+(?:[.,]\d+)?\s*(?:g|kg|ml)\b')
_BLOCKED_READY_CHICKPEA_PRODUCT_CUES = frozenset({
    'torr', 'torra',
    'fryst', 'frysta',
    'rostad', 'rostade',
})
_READY_PACKAGED_BEET_MEASURE_RE = re.compile(r'\b\d+(?:[.,]\d+)?\s*(?:g|kg|ml)\b')
_LENTIL_KEYWORDS = frozenset({'linser'})
_READY_PACKAGED_LENTIL_INGREDIENT_CUES = frozenset({
    'kokt', 'kokta',
    'förkokt', 'förkokta',
    'färdigkokt', 'fardigkokt',
    'färdigkokta', 'fardigkokta',
    'burk', 'tetra',
    'frp', 'förp', 'forp',
    'fpk', 'pkt',
    'förpackning', 'forpackning',
    'avrunnen', 'avrunna',
    'sköljd', 'skoljd', 'sköljda', 'skoljda',
})
_BLOCKED_READY_LENTIL_PRODUCT_CUES = frozenset({
    'torr', 'torra',
    'torkad', 'torkade',
    'delad', 'delade',
    'fryst', 'frysta',
})
_READY_PACKAGED_LENTIL_PRODUCT_CUES = frozenset({
    'kokt', 'kokta',
    'förkokt', 'förkokta',
    'färdigkokt', 'fardigkokt',
    'färdigkokta', 'fardigkokta',
    'burk', 'tetra',
})
_RIVEN_CHEDDAR_KEYWORDS = frozenset({'cheddar', 'cheddarost'})
_CHEDDAR_SPREAD_PRODUCT_CUES = frozenset({
    'mjukost',
    'bredbar',
    'tub',
    'tube',
    'kavli',
    'slice',
    'slices',
    'burger',
    'burgers',
    'burgar',
})
_GENERIC_FROZEN_FISH_INGREDIENT_CUES = frozenset({
    'fryst', 'frysta', 'djupfryst', 'djupfrysta',
})
_EXACT_COMPOUND_ONLY_INGREDIENTS = {
    'glutenfrihavregryn': frozenset({'havregryn'}),
    'vegetariskhamburgare': frozenset({'hamburgare'}),
    'sojamajonnäs': frozenset({'soja', 'majonnäs'}),
    'sojamajonnas': frozenset({'soja', 'majonnäs'}),
    'srirachamajonnäs': frozenset({'sriracha', 'majonnäs'}),
    'srirachamajonnas': frozenset({'sriracha', 'majonnäs'}),
    'kantarellpesto': frozenset({'pesto', 'kantarell', 'kantareller', 'svamp'}),
    'kronärtskockspesto': frozenset({'pesto', 'kronärtskocka', 'kronartskocka'}),
    'kronartskockspesto': frozenset({'pesto', 'kronärtskocka', 'kronartskocka'}),
    'syltadingefära': frozenset({'ingefära', 'ingefara'}),
    'syltadingefara': frozenset({'ingefära', 'ingefara'}),
    'kålrotsgari': frozenset({'kålrot'}),
    'kalrotsgari': frozenset({'kålrot'}),
    'romsås': frozenset({'rom'}),
    'romsas': frozenset({'rom'}),
    'skinkschnitzel': frozenset({'schnitzel'}),
    'fläskschnitzel': frozenset({'schnitzel'}),
    'flaskschnitzel': frozenset({'schnitzel'}),
    'matbrödsjäst': frozenset({'jäst', 'matbröd', 'matbrod'}),
    'matbrodsjast': frozenset({'jäst', 'matbröd', 'matbrod'}),
    'steambuns': frozenset({'bröd', 'brod'}),
    'vetesurdegsgrund': frozenset({'vetesurdeg', 'rågsurdeg', 'ragsurdeg', 'surdeg'}),
    'kardemummayoghurt': frozenset({
        'yoghurt', 'yogurt',
        'matlagningsyoghurt', 'matyoghurt',
        'mayo',
        'kardemumma', 'kardemummakapslar', 'kardemummakapsel',
    }),
    'mousserandevin': frozenset({'mousserande'}),
    'rimmatfläsk': frozenset({'fläsk', 'flask', 'fläskkött', 'flaskkott'}),
    'trattkantarell': frozenset({'kantarell', 'kantareller', 'svamp'}),
    'torkadsvamp': frozenset({'svamp'}),
    'flytandesmör': frozenset({'smör', 'smor'}),
    'flytandesmor': frozenset({'smör', 'smor'}),
    'fitnessflingor': frozenset({'fitness'}),
    'durumvetemjöl': frozenset({'vetemjöl'}),
    'durumvetemjol': frozenset({'vetemjöl'}),
    'vetemjölspecial': frozenset({'vetemjöl'}),
    'vetemjölfullkorn': frozenset({'vetemjöl'}),
    'kålrotsspaghetti': frozenset({'pasta', 'långpasta', 'langpasta', 'spaghetti', 'spagetti'}),
    'kalrotsspaghetti': frozenset({'pasta', 'långpasta', 'langpasta', 'spaghetti', 'spagetti'}),
    'morotsspaghetti': frozenset({
        'morotsspaghetti',
        'morot', 'morötter', 'morotter', 'julienne',
        'pasta', 'långpasta', 'langpasta', 'spaghetti', 'spagetti',
    }),
}


def _append_canonical_keyword_synonyms(text: str) -> str:
    """Expose canonical keyword synonyms present in ingredient text.

    The raw matcher primarily works on substring checks against the ingredient
    text. Recipe extraction, however, canonicalizes token variants such as
    "cantucci" -> "cantuccini" and "bjäst" -> "näringsjäst". Append those
    canonical forms here so fast matching stays aligned with ingredient
    extraction without broadening through parent mappings like "prästost" -> "ost".
    """

    extras = []
    for word in _WORD_PATTERN.findall(text):
        canonical = KEYWORD_SYNONYMS.get(word)
        if not canonical or canonical == word:
            canonical = None
        if canonical and canonical not in text and canonical not in extras:
            extras.append(canonical)
        parent_alias = _INGREDIENT_PARENT_TEXT_ALIASES.get(word)
        if parent_alias and parent_alias not in text and parent_alias not in extras:
            extras.append(parent_alias)
    # Explicit sparkling-wine recipe wording should still keep the long-standing
    # cooking-wine fallback, while exact `mousserandevin` products rank naturally
    # through the dedicated compound keyword.
    if 'mousserandevin' in text and 'matlagningsvin' not in text and 'matlagningsvin' not in extras:
        extras.append('matlagningsvin')
    # Long pasta shapes should also expose the umbrella family so linguine,
    # spaghetti, tagliatelle etc. can match each other without widening to all
    # ordinary pasta shapes.
    if (
        any(cue in text for cue in _LONG_PASTA_INGREDIENT_CUES)
        and 'långpasta' not in text
        and 'langpasta' not in text
        and 'långpasta' not in extras
    ):
        extras.append('långpasta')
    # Fresh-sausage recipe wording needs the generic sausage umbrella exposed in
    # raw matcher text as well; the later färskkorv gate keeps that umbrella on
    # the narrow fresh-sausage subset (färskkorv/salsiccia/chorizo).
    if (
        any(cue in text for cue in (
            'färskkorv', 'farskkorv',
            'färskkorvar', 'farskkorvar',
            'färsk korv', 'farsk korv',
            'färska korvar', 'farska korvar',
        ))
        and 'korv' not in extras
    ):
        extras.append('korv')
    if not extras:
        return text
    return text + ' ' + ' '.join(extras)


def _blocked_by_exact_compound_only(ingredient_lower: str, matched_keyword: str) -> bool:
    """Keep exact ingredient compounds from degrading into broad fallback families."""
    for compound, blocked_keywords in _EXACT_COMPOUND_ONLY_INGREDIENTS.items():
        if compound in ingredient_lower and matched_keyword in blocked_keywords:
            return True
    return False


def _offer_is_roe_family(keywords: List[str]) -> bool:
    """Return True for fish-roe products that should satisfy generic `rom`."""

    return any(keyword != 'rom' and keyword.endswith('rom') for keyword in keywords)


def _ingredient_requested_specific_roe_family(ingredient_lower: str) -> Optional[str]:
    """Return the explicit roe family requested by the ingredient, if any."""

    for family, cues in _ROE_FAMILY_INGREDIENT_CUES.items():
        if any(cue in ingredient_lower for cue in cues):
            return family
    return None


def _product_matches_roe_family(product_keywords: List[str], roe_family: str) -> bool:
    """Check whether product keywords satisfy a specific roe-family request."""

    if roe_family in product_keywords:
        return True
    return any(cue in product_keywords for cue in _ROE_FAMILY_INGREDIENT_CUES.get(roe_family, frozenset()))


def _ingredient_wants_spirit_rom(ingredient_lower: str) -> bool:
    """Explicit `ljus/mörk/vit rom` lines are spirit, not fish roe."""

    return any(cue in ingredient_lower for cue in _ROM_SPIRIT_INGREDIENT_CUES)


def _ingredient_requests_long_pasta(ingredient_lower: str) -> bool:
    """Return True when the ingredient explicitly names a long pasta family."""

    if any(cue in ingredient_lower for cue in _NON_PASTA_LONG_PASTA_COMPOUND_CUES):
        return False
    return any(cue in ingredient_lower for cue in _LONG_PASTA_INGREDIENT_CUES)


def _ingredient_requests_ready_packaged_chickpeas(ingredient_lower: str) -> bool:
    """Return True when a chickpea ingredient clearly points to a ready package."""

    if any(cue in ingredient_lower for cue in _NON_READY_CHICKPEA_INGREDIENT_CUES):
        return False
    if any(cue in ingredient_lower for cue in _READY_PACKAGED_CHICKPEA_INGREDIENT_CUES):
        return True
    return bool(_READY_PACKAGED_CHICKPEA_MEASURE_RE.search(ingredient_lower))


def _ready_packaged_chickpea_allows_product(
    product_lower: str,
    ingredient_lower: str,
    matched_keyword: Optional[str],
) -> bool:
    """Ready packaged chickpea lines should not accept dry/frozen/snack products."""

    if matched_keyword not in _CHICKPEA_KEYWORDS:
        return True
    if not _ingredient_requests_ready_packaged_chickpeas(ingredient_lower):
        return True
    if any(cue in product_lower for cue in _BLOCKED_READY_CHICKPEA_PRODUCT_CUES):
        return False
    return True


def _ingredient_requests_ready_packaged_lentils(ingredient_lower: str) -> bool:
    """Return True when a lentil ingredient clearly asks for cooked/ready lentils."""

    return any(cue in ingredient_lower for cue in _READY_PACKAGED_LENTIL_INGREDIENT_CUES)


def _ready_packaged_lentil_allows_product(
    product_lower: str,
    ingredient_lower: str,
    matched_keyword: Optional[str],
) -> bool:
    """Cooked/pre-cooked lentil lines should not accept dry or split lentils."""

    if matched_keyword not in _LENTIL_KEYWORDS:
        return True
    if not _ingredient_requests_ready_packaged_lentils(ingredient_lower):
        return True
    if any(cue in product_lower for cue in _BLOCKED_READY_LENTIL_PRODUCT_CUES):
        return False
    return any(cue in product_lower for cue in _READY_PACKAGED_LENTIL_PRODUCT_CUES)


def _ingredient_requests_preserved_whole_beets(ingredient_lower: str) -> bool:
    """Return True for packaged/product-like 'hela rödbetor' ingredients."""

    if not any(
        phrase in ingredient_lower
        for phrase in ('hela rödbeta', 'hela rödbetor', 'hela rodbeta', 'hela rodbetor')
    ):
        return False
    if any(cue in ingredient_lower for cue in (
        'burk', 'konserv', 'konserverad', 'konserverade',
        'avrunnen', 'avrunna',
        'felix',
    )):
        return True
    return bool(_READY_PACKAGED_BEET_MEASURE_RE.search(ingredient_lower))


def _riven_cheddar_allows_product(
    product_lower: str,
    ingredient_lower: str,
    matched_keyword: Optional[str],
) -> bool:
    """Riven cheddar should not accept spreadable cheddar products."""

    if matched_keyword not in _RIVEN_CHEDDAR_KEYWORDS:
        return True
    if 'riven' not in ingredient_lower:
        return True
    return not any(cue in product_lower for cue in _CHEDDAR_SPREAD_PRODUCT_CUES)


def _ingredient_requests_generic_frozen_fish_fillet(ingredient_lower: str) -> bool:
    """Generic frozen fish wording should use frozen fish fillets as store fallback."""

    return (
        'fisk' in ingredient_lower
        and 'fiskfilé' not in ingredient_lower
        and 'fiskfile' not in ingredient_lower
        and any(cue in ingredient_lower for cue in _GENERIC_FROZEN_FISH_INGREDIENT_CUES)
    )


def _ingredient_satisfies_context_word(context_word: str, ingredient_lower: str, offer_text: str) -> bool:
    if context_word in ingredient_lower:
        return True
    aliases = _CONTEXT_WORD_INGREDIENT_ALIASES.get(context_word, _EMPTY_FROZENSET)
    return any(alias in ingredient_lower and alias in offer_text for alias in aliases)


def _ingredient_wants_fennel_spice(ingredient_lower: str) -> bool:
    if any(
        ind in ingredient_lower for ind in (
            'krydda', 'frö', 'fänkålsfrö', 'fankalsfro',
            'pollen', 'tsk', 'tesked', 'krm',
            'malen', 'mald', 'malda',
        )
    ):
        return True
    # Alternative spice lists like "anis, fänkål eller kummin" mean fennel seeds,
    # not a fresh fennel bulb. Keep this narrow so plain "1 msk fänkål" stays
    # on the existing fresh-vs-spice behavior for now.
    if 'eller' in ingredient_lower and ('fänkål' in ingredient_lower or 'fankal' in ingredient_lower):
        if _RE_ANIS_WORD.search(ingredient_lower) or _RE_KUMMIN_WORD.search(ingredient_lower):
            return True
    return False


_PLAIN_YEAST_WORD_RE = re.compile(r'(?<![A-Za-zÅÄÖåäö])jäst(?![A-Za-zÅÄÖåäö])')


def _ingredient_requests_generic_bread_yeast(ingredient_lower: str) -> bool:
    has_plain_yeast_word = bool(_PLAIN_YEAST_WORD_RE.search(ingredient_lower))
    return (
        has_plain_yeast_word
        and not any(cue in ingredient_lower for cue in _SWEET_DOUGH_YEAST_INGREDIENT_CUES)
    )


def _pimiento_product_allowed(
    product_lower: str,
    ingredient_lower: str,
    matched_keyword: Optional[str],
) -> bool:
    """Keep preserved piquillo peppers separate from fresh padrón peppers."""
    if matched_keyword not in {'pimiento', 'pimientos'}:
        return True
    if 'piquillo' in ingredient_lower and 'piquillo' not in product_lower:
        return False
    if any(cue in ingredient_lower for cue in (
        'rostad', 'rostade', 'rostad', 'skalad', 'skalade',
        'burk', 'konserverad', 'konserverade', 'inlagd', 'inlagda',
    )):
        if any(cue in product_lower for cue in ('klass', 'färsk', 'farsk')):
            return False
    return True


def _ingredient_wants_cooked_kycklingklubba(ingredient_lower: str) -> bool:
    return (
        'kycklingklubba' in ingredient_lower
        and any(cue in ingredient_lower for cue in _COOKED_KYCKLINGKLUBBA_INGREDIENT_CUES)
    )


def _product_has_cooked_kyckling_cue(product_lower: str) -> bool:
    return any(cue in product_lower for cue in _COOKED_KYCKLING_PRODUCT_CUES)


def _steak_style_tuna_product_allowed(
    product_lower: str,
    ingredient_lower: str,
    matched_keyword: Optional[str],
) -> bool:
    """Piece/steak tuna recipes should route to fresh/frozen tuna, not canned tuna."""
    if matched_keyword != 'tonfisk':
        return False
    if not any(cue in ingredient_lower for cue in (' bit ', ' bitar ', 'biff', 'steak')):
        return False
    if any(cue in product_lower for cue in ('vatten', 'olja', 'solrosolja', 'buljong', 'burk', 'konserv')):
        return False
    return any(cue in product_lower for cue in ('färsk', 'farsk', 'fryst', 'frysta', 'filé', 'file'))


def _ingredient_implies_whole_kyckling(ingredient_lower: str) -> bool:
    return (
        'kyckling' in ingredient_lower
        and all(cut not in ingredient_lower for cut in (
            'filé', 'file', 'innerfil', 'lårfil', 'larfil', 'bröst', 'brost',
            'ving', 'klubba', 'ben', 'strimlad',
        ))
        and (
            'hel kyckling' in ingredient_lower
            or 'helkyckling' in ingredient_lower
            or 'stor kyckling' in ingredient_lower
        )
    )


def _product_is_whole_kyckling_offer(
    product_keywords: Iterable[str],
    product_name: str = "",
    specialty_qualifiers: Optional[Dict[str, set]] = None,
) -> bool:
    if 'hel' in (specialty_qualifiers or {}).get('kyckling', set()):
        return True
    product_kw_set = set(product_keywords)
    if 'helkyckling' in product_kw_set:
        return True
    product_lower = fix_swedish_chars(product_name).lower() if product_name else ""
    return 'majskyckling' in product_kw_set and 'hel' in product_lower


_WHOLE_CRAYFISH_KEYWORDS = frozenset({
    'kräftor', 'kraftor',
    'signalkräfta', 'signalkrafta',
    'signalkräftor', 'signalkraftor',
    'havskräfta', 'havskrafta',
    'havskräftor', 'havskraftor',
})
_WHOLE_CRAYFISH_BLOCKED_PRODUCT_WORDS = frozenset({
    'i lag', 'lake',
    'kräftstjärt', 'kraftstjart', 'kräftstjärtar', 'kraftstjartar',
})
_WHOLE_CRAYFISH_FROZEN_PRODUCT_WORDS = frozenset({
    'fryst', 'frysta',
})


def _ingredient_wants_whole_crayfish(ingredient_lower: str) -> bool:
    return (
        any(word in ingredient_lower for word in (
            'kräftor', 'kraftor',
            'signalkräfta', 'signalkrafta',
            'signalkräftor', 'signalkraftor',
            'havskräfta', 'havskrafta',
            'havskräftor', 'havskraftor',
        ))
        and 'kräftstjärt' not in ingredient_lower
        and 'kraftstjart' not in ingredient_lower
    )


def _whole_crayfish_product_allowed(product_lower: str, ingredient_lower: str, matched_keyword: str) -> bool:
    if matched_keyword not in _WHOLE_CRAYFISH_KEYWORDS:
        return True
    if not _ingredient_wants_whole_crayfish(ingredient_lower):
        return True
    if 'levande' in ingredient_lower:
        return 'levande' in product_lower
    if any(word in product_lower for word in _WHOLE_CRAYFISH_BLOCKED_PRODUCT_WORDS):
        return False
    if (
        ('havskräft' in ingredient_lower or 'havskraft' in ingredient_lower)
        and ('havskräft' in product_lower or 'havskraft' in product_lower)
    ):
        return True
    return any(word in product_lower for word in _WHOLE_CRAYFISH_FROZEN_PRODUCT_WORDS)


_COLORED_CURRY_RULES = (
    (frozenset({'röd', 'rod', 'red'}), 'rödcurry', 'rödcurrypasta'),
    (frozenset({'grön', 'gron', 'green'}), 'gröncurry', 'gröncurrypasta'),
    (frozenset({'gul', 'yellow'}), 'gulcurry', 'gulcurrypasta'),
)


def _expand_offer_keywords_for_matching(product_keywords: List[str], product_name: str = "") -> List[str]:
    """Mirror the small offer-side keyword bridges that uncached matching needs."""
    if not product_keywords:
        return product_keywords

    expanded = list(product_keywords)
    seen = set(product_keywords)
    for kw in product_keywords:
        for extra in OFFER_EXTRA_KEYWORDS.get(kw, ()):
            if extra not in seen:
                expanded.append(extra)
                seen.add(extra)
        # Generic recipe "sylt" should reach ordinary jam variants without
        # broadening across marmelad/gelé. Keep this as a matching-time bridge
        # so products still retain their specific flavor identity elsewhere.
        if kw != 'sylt' and kw.endswith('sylt') and 'sylt' not in seen:
            expanded.append('sylt')
            seen.add('sylt')
        if kw in {'signalkräftor', 'signalkraftor'}:
            for extra in (
                'signalkräfta', 'signalkrafta',
                'kräftor', 'kraftor',
                'havskräfta', 'havskrafta',
                'havskräftor', 'havskraftor',
            ):
                if extra not in seen:
                    expanded.append(extra)
                    seen.add(extra)
        if kw in {'havskräftor', 'havskraftor'}:
            for extra in ('havskräfta', 'havskrafta'):
                if extra not in seen:
                    expanded.append(extra)
                    seen.add(extra)

    offer_words = set(fix_swedish_chars(product_name).lower().split()) if product_name else set()
    has_curry_paste_family = (
        'currypasta' in seen
        or any(paste_kw in seen for _, _, paste_kw in _COLORED_CURRY_RULES)
        or ('curry' in offer_words and ('paste' in offer_words or 'pasta' in offer_words))
    )
    if has_curry_paste_family:
        for color_words, curry_keyword, paste_keyword in _COLORED_CURRY_RULES:
            if offer_words & color_words:
                if paste_keyword not in seen:
                    expanded.append(paste_keyword)
                    seen.add(paste_keyword)
                if curry_keyword not in seen:
                    expanded.append(curry_keyword)
                    seen.add(curry_keyword)
                break

    return expanded


def matches_ingredient(
    product_keywords: List[str],
    ingredient_text: str,
    product_name: str = "",
    _prenormalized: bool = False
) -> Optional[str]:
    """
    Check if any product keyword matches the ingredient text.

    Args:
        product_keywords: Keywords extracted from product
        ingredient_text: Full ingredient text (normalized)
        product_name: Original product name (for context checks)
        _prenormalized: If True, skip fix_swedish_chars on ingredient_text (performance)

    Returns:
        The matched keyword, or None if no match

    Example:
        >>> matches_ingredient(['vispgrädde'], 'vispgrädde 3 dl')
        'vispgrädde'
        >>> matches_ingredient(['kyckling'], 'kyckling', 'Köttbullar Kyckling')
        None  # Product has 'köttbullar' but ingredient doesn't
        >>> matches_ingredient(['kyckling', 'köttbullar'], 'kycklingköttbullar', 'Köttbullar Kyckling')
        'kyckling'  # Both words present, OK to match
    """
    # Quick exit if no keywords
    if not product_keywords:
        return None

    product_keywords = _expand_offer_keywords_for_matching(product_keywords, product_name)

    # Skip normalization if caller already did it (big perf win in hot loops)
    ingredient_lower = ingredient_text if _prenormalized else fix_swedish_chars(ingredient_text).lower()

    # Normalize space variants (e.g., "corn flakes" -> "cornflakes")
    # Skip if caller already applied these (recipe_matcher pre-normalizes once per recipe)
    if not _prenormalized:
        ingredient_lower = _apply_space_normalizations(ingredient_lower)
        ingredient_lower = re.sub(r'\btandori\b', 'tandoori', ingredient_lower)
        ingredient_lower = preserve_cheese_preference_parentheticals(ingredient_lower)
        ingredient_lower = preserve_fresh_pasta_parenthetical(ingredient_lower)
        ingredient_lower = preserve_parenthetical_grouped_herb_leaves(ingredient_lower)
        ingredient_lower = preserve_parenthetical_shiso_alternatives(ingredient_lower)
        ingredient_lower = preserve_non_concentrate_parenthetical(ingredient_lower)
    ingredient_lower = normalize_measured_durumvete_flour(ingredient_lower)
    ingredient_lower = normalize_measured_risotto_rice(ingredient_lower)
    ingredient_lower = rewrite_truncated_eller_compounds(ingredient_lower)
    ingredient_lower = rewrite_mince_of_alternatives(ingredient_lower)
    # Preserve the plant-based shorthand while also exposing the base dairy term
    # used by offer keywords and yoghurt-specific validators.
    ingredient_lower = re.sub(r'\bgurt\b', 'gurt yoghurt', ingredient_lower)
    if _ingredient_requests_generic_frozen_fish_fillet(ingredient_lower):
        ingredient_lower += ' fiskfilé'
    ingredient_lower = _append_canonical_keyword_synonyms(ingredient_lower)

    # STEP 1: Fast keyword matching first (most products won't match at all)
    matched_keyword = None
    for keyword in product_keywords:
        # Simple 'in' check first (faster than regex)
        if keyword in ingredient_lower:
            # Block compound word suffix matches (e.g., "köttbullar" in "fiskköttbullar")
            if keyword in _SUFFIX_PROTECTED_KEYWORDS:
                if not _has_word_boundary_match(keyword, ingredient_lower):
                    continue
            # Block embedded matches (e.g., "ris" in "grissini" but allow "basmatiris")
            if keyword in _EMBEDDED_PROTECTED_KEYWORDS:
                if not _has_word_edge_match(keyword, ingredient_lower):
                    continue
            # Check for false positives (e.g., "ost" in "ostronsås")
            if keyword in FALSE_POSITIVE_BLOCKERS:
                # Smart blocker: only block if keyword appears EXCLUSIVELY
                # inside blocker words. If keyword also appears standalone
                # or at word-start of a non-blocker compound, allow the match.
                # e.g., "ost" in "rostade mandlar, 100g riven ost" → NOT blocked
                #        "ost" in "rostade mandlar" or "ostronsås" → blocked
                blockers = FALSE_POSITIVE_BLOCKERS[keyword]
                has_blocker = any(b in ingredient_lower for b in blockers)
                if has_blocker:
                    # Check each word: does keyword appear in a valid context?
                    words_in_text = _WORD_PATTERN.findall(ingredient_lower)
                    has_valid = False
                    for w in words_in_text:
                        if keyword not in w:
                            continue
                        if w == keyword:
                            has_valid = True  # exact standalone match
                            break
                        if w.startswith(keyword):
                            # Compound word - valid unless it starts with a blocker
                            # "ostsås" → valid, "ostronsås" → starts with "ostron" → blocked
                            if not any(w.startswith(b) for b in blockers):
                                has_valid = True
                                break
                    if not has_valid:
                        continue  # keyword ONLY inside blocker words → skip
            # Compound strictness: if keyword is part of a compound word in recipe,
            # product must contain the qualifier (prefix or suffix)
            if keyword in _COMPOUND_STRICT_KEYWORDS or keyword in _COMPOUND_STRICT_PREFIX_KEYWORDS:
                product_lower_name = fix_swedish_chars(product_name).lower() if product_name else ""
                if keyword in _COMPOUND_STRICT_KEYWORDS:
                    if _check_compound_strict(keyword, ingredient_lower, product_lower_name):
                        continue
                if keyword in _COMPOUND_STRICT_PREFIX_KEYWORDS:
                    if _check_compound_strict(keyword, ingredient_lower, product_lower_name,
                                              check_prefix=True):
                        continue
            if _blocked_by_exact_compound_only(ingredient_lower, keyword):
                continue
            # Product-name blockers are validated later per ingredient in recipe_matcher.py.
            matched_keyword = keyword
            break

    # Qualifier check: "dressing" requires a flavor/type qualifier from the product
    # name to also appear in the ingredient. Uses product NAME (not keywords) since
    # extraction may strip qualifier words like "curry" or "lime".
    if matched_keyword and matched_keyword in _QUALIFIER_REQUIRED_KEYWORDS:
        if product_name:
            name_lower = fix_swedish_chars(product_name).lower()
        else:
            name_lower = ' '.join(product_keywords)
        qualifier_words = [w for w in _WORD_PATTERN.findall(name_lower)
                           if len(w) >= 4 and w != matched_keyword]
        if qualifier_words and not any(w in ingredient_lower for w in qualifier_words):
            matched_keyword = None

    # No direct match? Try parent mapping (e.g., "jasminris" → "ris")
    if not matched_keyword:
        for keyword in product_keywords:
            parent = INGREDIENT_PARENTS.get(keyword) or PARENT_MATCH_ONLY.get(keyword)
            if parent and parent in ingredient_lower:
                # Apply suffix protection to parent keyword (e.g., "ris" in "grissini")
                if parent in _SUFFIX_PROTECTED_KEYWORDS:
                    if not _has_word_boundary_match(parent, ingredient_lower):
                        continue
                if parent in _EMBEDDED_PROTECTED_KEYWORDS:
                    if not _has_word_edge_match(parent, ingredient_lower):
                        continue
                # FP-blocker check for parent path: use same smart logic as
                # STEP 1 — check per-word whether the parent keyword appears in
                # a valid context (standalone or valid compound start).
                # "pasta" in "pastasås" → blocked (pastasås is a blocker)
                # "pasta" in "400 g pasta" → allowed (standalone word)
                blockers = FALSE_POSITIVE_BLOCKERS.get(parent, set())
                if blockers:
                    has_blocker = any(b in ingredient_lower for b in blockers)
                    if has_blocker:
                        words_in_text = _WORD_PATTERN.findall(ingredient_lower)
                        has_valid = False
                        for w in words_in_text:
                            if parent not in w:
                                continue
                            if w == parent:
                                has_valid = True
                                break
                            if w.startswith(parent):
                                if not any(w.startswith(b) for b in blockers):
                                    has_valid = True
                                    break
                        if not has_valid:
                            continue
                # Compound strictness for parent path too
                product_lower_name = fix_swedish_chars(product_name).lower() if product_name else ""
                if parent in _COMPOUND_STRICT_KEYWORDS or parent in _COMPOUND_STRICT_PREFIX_KEYWORDS:
                    if parent in _COMPOUND_STRICT_KEYWORDS:
                        if _check_compound_strict(parent, ingredient_lower, product_lower_name):
                            continue
                    if parent in _COMPOUND_STRICT_PREFIX_KEYWORDS:
                        if _check_compound_strict(parent, ingredient_lower, product_lower_name,
                                                  check_prefix=True):
                            continue
                # Also check compound-strict for the ORIGINAL product keyword
                if keyword in _COMPOUND_STRICT_KEYWORDS:
                    if _check_compound_strict(keyword, ingredient_lower, product_lower_name):
                        continue
                if keyword in _COMPOUND_STRICT_PREFIX_KEYWORDS:
                    if _check_compound_strict(keyword, ingredient_lower, product_lower_name,
                                              check_prefix=True):
                        continue
                if _blocked_by_exact_compound_only(ingredient_lower, parent):
                    continue
                # Product-name blockers for parent matches are also validated
                # later per ingredient in recipe_matcher.py.
                matched_keyword = parent
                break

    if (
        not matched_keyword
        and _ingredient_implies_whole_kyckling(ingredient_lower)
        and _product_is_whole_kyckling_offer(product_keywords, product_name)
    ):
        matched_keyword = 'kyckling'
    if (
        not matched_keyword
        and any(kw in product_keywords for kw in ('matbrödsjäst', 'matbrodsjast'))
        and _ingredient_requests_generic_bread_yeast(ingredient_lower)
    ):
        matched_keyword = 'matbrödsjäst'

    # Still no match? Exit early (skip expensive context checks)
    if not matched_keyword:
        return None

    if (
        matched_keyword == 'helkyckling'
        and _ingredient_implies_whole_kyckling(ingredient_lower)
        and 'helkyckling' not in ingredient_lower
    ):
        matched_keyword = 'kyckling'

    # Generic "rom" defaults to fish roe. Spirit products should only match
    # when the ingredient explicitly says light/dark/white rum, while roe
    # products should stay blocked for those spirit-specific lines.
    if matched_keyword == 'pasta' and _ingredient_requests_long_pasta(ingredient_lower):
        if any(kw in product_keywords for kw in ('långpasta', 'langpasta')):
            matched_keyword = 'långpasta'
        else:
            return None
    if matched_keyword == 'fiskfilé' and 'vit fiskfilé' in ingredient_lower:
        if 'laxfilé' in product_keywords or 'laxfile' in product_keywords:
            return None
    if matched_keyword == 'rom':
        product_is_roe = _offer_is_roe_family(product_keywords)
        requested_roe_family = _ingredient_requested_specific_roe_family(ingredient_lower)
        if requested_roe_family and not _product_matches_roe_family(product_keywords, requested_roe_family):
            return None
        ingredient_wants_spirit = _ingredient_wants_spirit_rom(ingredient_lower)
        if ingredient_wants_spirit and product_is_roe:
            return None
        if not ingredient_wants_spirit and not product_is_roe:
            return None
    product_name_normalized = fix_swedish_chars(product_name).lower() if product_name else ' '.join(product_keywords)
    if matched_keyword in {'jäst', 'matbrödsjäst'} and _ingredient_requests_generic_bread_yeast(ingredient_lower):
        if any(cue in product_name_normalized for cue in ('söta degar', 'sota degar', 'söt deg', 'sot deg')):
            return None
    if (
        matched_keyword == 'lingondryck'
        and 'koncentrat' in product_name_normalized
        and any(cue in ingredient_lower for cue in _NON_CONCENTRATE_INGREDIENT_CUES)
    ):
        return None
    if not _ready_packaged_chickpea_allows_product(
        product_name_normalized,
        ingredient_lower,
        matched_keyword,
    ):
        return None
    if not _ready_packaged_lentil_allows_product(
        product_name_normalized,
        ingredient_lower,
        matched_keyword,
    ):
        return None
    if not _riven_cheddar_allows_product(
        product_name_normalized,
        ingredient_lower,
        matched_keyword,
    ):
        return None
    if not _pimiento_product_allowed(
        product_name_normalized,
        ingredient_lower,
        matched_keyword,
    ):
        return None

    # STEP 1b: Keyword suppressed by context — if ingredient text contains a context
    # word that makes this keyword irrelevant, suppress it.
    # e.g., 'chilisås' suppressed when ingredient contains 'cream cheese' (flavored cream cheese).
    if matched_keyword in KEYWORD_SUPPRESSED_BY_CONTEXT:
        suppressors = KEYWORD_SUPPRESSED_BY_CONTEXT[matched_keyword]
        if any(s in ingredient_lower for s in suppressors):
            return None

    # STEP 2: Only normalize product_name if we have a potential match
    product_lower = _apply_space_normalizations(fix_swedish_chars(product_name).lower()) if product_name else ""

    if _steak_style_tuna_product_allowed(product_lower, ingredient_lower, matched_keyword):
        return matched_keyword

    # STEP 2a: Carrier-required products (e.g., 'mjukost') only match ingredients
    # that actually mention the same carrier.
    if product_lower:
        for carrier in CARRIER_CONTEXT_REQUIRED:
            if carrier in product_lower and not _ingredient_satisfies_context_word(carrier, ingredient_lower, product_lower):
                return None

    # STEP 2b: Juice product check — if product is juice (contains "juice"/"pressad")
    # and keyword is citron/lime, require ingredient to mention saft/juice/pressad.
    # Prevents "Citronjuice 200ml" matching "1 citron" (whole fruit).
    # Exception: if ingredient mentions "skal" (zest), whole fruit is needed — block juice.
    if matched_keyword in JUICE_RULE_KEYWORDS and product_lower:
        if any(ind in product_lower for ind in JUICE_PRODUCT_INDICATORS):
            if 'skal' in ingredient_lower:
                return None  # "saft och skal" = needs whole fruit, not bottled juice
            if 'koncentrat' in product_lower and any(
                q in ingredient_lower for q in ('råpressad', 'rapressad', 'färskpressad', 'farskpressad')
            ):
                return None  # raw/fresh-pressed juice should not match concentrate products
            if 'koncentrat' in product_lower and any(
                cue in ingredient_lower for cue in _NON_CONCENTRATE_INGREDIENT_CUES
            ):
                return None
            if not any(ind in ingredient_lower for ind in JUICE_INGREDIENT_INDICATORS):
                return None

    # STEP 2c: Whole crayfish recipes map to the frozen signalkräftor family,
    # not to shelf-stable "i lag"/tail products.
    if product_lower and not _whole_crayfish_product_allowed(product_lower, ingredient_lower, matched_keyword):
        return None

    # STEP 3: Context-required words check
    # If product contains a context word (e.g., "köttbullar"), the ingredient
    # must ALSO contain that word for a match to occur
    if product_lower:
        kw_exemptions = CONTEXT_WORD_KEYWORD_EXEMPTIONS.get(matched_keyword, _EMPTY_FROZENSET)
        for context_word in CONTEXT_REQUIRED_WORDS:
            if _has_word_boundary_match(context_word, product_lower):
                if context_word in kw_exemptions:
                    continue
                if not _ingredient_satisfies_context_word(context_word, ingredient_lower, product_lower):
                    # e.g., "kyckling" ingredient vs "Köttbullar Kyckling" product
                    return None

        # STEP 3b: Inverse context check — if ingredient contains a qualifying
        # word (e.g., "kryddmix") and match is on a different keyword, product
        # must also contain that qualifying word.
        for req_word in INGREDIENT_REQUIRES_IN_PRODUCT:
            if req_word in ingredient_lower and matched_keyword != req_word:
                if req_word not in product_lower:
                    return None

        # STEP 3c: Carrier-flavor specificity
        # Explicit flavored carrier ingredients like "mjukost hot jalapeno" should
        # only match products that carry the same flavor signal in the product name.
        if matched_keyword in CARRIER_CONTEXT_REQUIRED:
            ing_words = ingredient_lower.split()
            ing_flavors = [
                w for w in ing_words
                if (len(w) >= 4 or w in IMPORTANT_SHORT_KEYWORDS)
                and w in FLAVOR_WORDS
                and w not in CARRIER_CONTEXT_REQUIRED
            ]
            if ing_flavors and not any(f in product_lower for f in ing_flavors):
                return None

        # STEP 4: Secondary ingredient patterns check
        # REMOVED from here — handled per-ingredient in recipe_matcher.py
        # to avoid cross-ingredient contamination (e.g., "ost" from cheese
        # ingredient blocking all "Pasta ..." products).

        # STEP 5: Specialty qualifier check (inverse of context-required)
        # Keep the uncached matcher aligned with recipe_matcher/validators so
        # "eller" alternatives like "färska eller krossade tomater" are judged
        # per alternative rather than as one combined qualifier bundle.
        specialty_keyword = _SPECIALTY_KEYWORD_ALIASES.get(matched_keyword, matched_keyword)
        if specialty_keyword in SPECIALTY_QUALIFIERS:
            offer_specialty_qualifiers = {}
            found_qualifiers = {
                qualifier
                for qualifier in SPECIALTY_QUALIFIERS[specialty_keyword]
                if qualifier in product_lower
            }
            if found_qualifiers:
                offer_specialty_qualifiers[specialty_keyword] = found_qualifiers
            if not check_specialty_qualifiers(offer_specialty_qualifiers, specialty_keyword, ingredient_lower):
                return None

        # STEP 6: Processed product check (INVERSE logic)
        # If PRODUCT has processed indicator (finhackad, pressad, etc.),
        # INGREDIENT must also have it - otherwise no match.
        # This prevents "1 st Vitlök" from matching "Vitlök Finhackad"
        # IMPORTANT: Only check if base_word is the matched keyword.
        # Otherwise "Grillkorv Rökt Paprika" blocked by paprika rule
        # even though it matched on "grillkorv", not "paprika".
        for base_word, processed_indicators in PROCESSED_PRODUCT_RULES.items():
            if base_word != matched_keyword:
                continue
            if base_word in product_lower:
                # Skip if base_word only appears inside an exempt compound word
                # e.g., "tomater" in "körsbärstomater" - canned/fresh are interchangeable
                exemptions = PROCESSED_RULES_COMPOUND_EXEMPTIONS.get(base_word)
                if exemptions and any(ex in product_lower for ex in exemptions):
                    continue
                if base_word in STRICT_PROCESSED_RULES:
                    # Strict: find ALL indicators in product, require at least one in ingredient
                    # "Kryddmix Paneng Röd Curry" has {paneng, curry} → ingredient needs paneng OR curry
                    product_indicators = [ind for ind in processed_indicators if ind in product_lower]
                    # Expand with equivalents: "malen" also matches "mald"/"malet"
                    expanded_indicators = set(product_indicators)
                    for ind in product_indicators:
                        expanded_indicators.update(_PROCESSED_INDICATOR_EQUIVALENTS.get(ind, ()))
                    if product_indicators and not any(ind in ingredient_lower for ind in expanded_indicators):
                        # Spice-amount heuristic: "1 tsk ingefära" (no qualifier) = ground/dried.
                        # Small spice amounts (tsk/krm) without fresh indicators imply dried/ground.
                        _SPICE_AMOUNT_IMPLICIT_GROUND = frozenset({
                            'ingefära', 'ingefara',
                            'gurkmeja', 'kurkuma',
                            'paprika',
                        })
                        _GROUND_PRODUCT_INDICATORS = frozenset({'malen', 'malna', 'mald', 'malet', 'pulver', 'torkad', 'torkade'})
                        _FRESH_INDICATORS = frozenset({'färsk', 'farsk', 'riven', 'hackad', 'pressad'})
                        if (base_word in _SPICE_AMOUNT_IMPLICIT_GROUND
                                and any(ind in _GROUND_PRODUCT_INDICATORS for ind in expanded_indicators)
                                and not any(fi in ingredient_lower for fi in _FRESH_INDICATORS)
                                and re.search(r'\b(?:tsk|krm)\b', ingredient_lower)):
                            pass  # Allow: spice amount implies ground/dried
                        else:
                            return None
                else:
                    # Relaxed: check first indicator found, allow any indicator in ingredient
                    for indicator in processed_indicators:
                        if indicator in product_lower:
                            if indicator not in ingredient_lower:
                                has_any_indicator = any(ind in ingredient_lower for ind in processed_indicators)
                                if not has_any_indicator:
                                    return None
                            break

        # STEP 7: Spice vs Fresh vegetable check
        # REMOVED from here — handled per-ingredient in recipe_matcher.py
        # to avoid cross-contamination from concatenated ingredient text
        # (e.g., "torkad" from "torkad oregano" falsely allowing "Torkad Lime Påse",
        # or "klass" from "Lime Klass 1" falsely blocking via paprika rules).

    # STEP 8: Buljong context check
    # If ingredient is a stock cube/powder (contains "buljong") and the matched
    # keyword only appears as a flavor descriptor (in parentheses), block non-buljong
    # products. E.g., "buljongtärning (kyckling)" → "kyckling" is flavor, not chicken.
    if 'buljong' in ingredient_lower and 'buljong' not in product_lower:
            # Check if keyword appears ONLY inside parentheses
            # Remove parenthetical content and see if keyword is still present
            text_no_parens = _PARENS_PATTERN.sub('', ingredient_lower)
            if matched_keyword not in text_no_parens:
                # Keyword only in parentheses — it's a flavor descriptor
                return None

    # STEP 9: Explicit frozen spinach should not degrade to fresh bagged spinach.
    # Keep this asymmetric: generic/fresh spinach recipes may still accept frozen
    # products as a fallback, but a recipe that explicitly asks for frozen spinach
    # should not surface fresh baby/blad/storpack offers.
    _SPINACH_KEYWORDS = frozenset({'spenat', 'babyspenat', 'bladspenat'})
    if (
        matched_keyword in _SPINACH_KEYWORDS
        and any(fi in ingredient_lower for fi in RECIPE_FROZEN_INDICATORS)
        and not any(fi in product_lower for fi in FROZEN_PRODUCT_INDICATORS)
    ):
        return None

    # Keep spice-list fennel alternatives separate from fresh fennel bulbs.
    if matched_keyword == 'fänkål':
        wants_fennel_spice = _ingredient_wants_fennel_spice(ingredient_lower)
        is_fresh_fennel_product = 'klass' in product_lower
        is_fennel_spice_product = any(
            ind in product_lower for ind in (
                'fänkålsfrö', 'fankalsfro', 'fänkålsfrön', 'fankalsfron',
                'malen', 'hel',
            )
        )
        if wants_fennel_spice and is_fresh_fennel_product:
            return None
        if not wants_fennel_spice and is_fennel_spice_product:
            return None

    # Explicitly cooked chicken drumsticks should not fall back to raw/frozen
    # drumstick products. Keep this part-specific so plain kycklingklubba lines
    # remain broad.
    if (
        matched_keyword == 'kycklingklubba'
        and _ingredient_wants_cooked_kycklingklubba(ingredient_lower)
        and not _product_has_cooked_kyckling_cue(product_lower)
    ):
        return None

    return matched_keyword


# ============================================================================
# "ELLER" (OR) PATTERN PARSING - Detect alternative ingredients
# ============================================================================





# ============================================================================
# RECIPE TYPE DETECTION - Filter out buffet/party/multi-course recipes
# ============================================================================

# Patterns that indicate buffet/party/multi-course recipes
# These are rarely useful for everyday cooking and dominate rankings due to many ingredients

# Regex patterns for more complex detection

# Pre-compile regex patterns




# ============================================================================
# PERFORMANCE OPTIMIZATION: Pre-compute offer data for fast matching
# ============================================================================

def precompute_offer_data(offer_name: str, offer_category: str = "", brand: str = "", weight_grams: float = None) -> Dict:
    """
    Pre-compute all matching-relevant data for an offer.

    Called ONCE per offer during cache build, then reused for all recipes.
    This avoids repeated string normalization and set lookups in hot loops.

    Args:
        offer_name: Original product name
        offer_category: Product category
        brand: Product brand (e.g., "Philadelphia" → adds "färskost" keyword)

    Returns:
        Dict with pre-computed data:
        - keywords: List[str] - extracted keywords
        - name_normalized: str - lowercase, fix_swedish_chars applied
        - context_words: Set[str] - which CONTEXT_REQUIRED_WORDS this offer contains
        - specialty_qualifiers: Dict[str, Set[str]] - base_word -> found qualifiers
    """
    # Extract keywords (this was already being cached)
    keywords = extract_keywords_from_product(offer_name, offer_category, brand=brand)
    keywords = _expand_offer_keywords_for_matching(keywords, offer_name)

    # Detect carrier-stripped flavor words: words in the product name that were
    # removed by carrier detection (e.g., "citron" stripped from "Messmör Citron").
    # These must NOT be re-indexed in cache_manager's name-word inverted index,
    # otherwise they bypass the carrier mechanism entirely.
    name_lower_simple = fix_swedish_chars(offer_name).lower()
    name_words_all = set(name_lower_simple.split())
    kw_set_check = set(keywords)
    # Words from the name that are potential food keywords (≥4 chars) but not in keywords
    carrier_stripped = set()
    # Only compute if product has a carrier (carrier strips flavor words)
    if name_words_all & _CARRIER_SINGLE_WORDS or any(c in name_lower_simple for c in _CARRIER_MULTI_WORDS):
        carrier_stripped = {w for w in name_words_all
                           if (len(w) >= 4 or w in IMPORTANT_SHORT_KEYWORDS)
                           and w not in kw_set_check and w in FLAVOR_WORDS}

    # Is this product a carrier that requires its carrier word in ingredient text?
    _carrier_ctx_hits = name_words_all & CARRIER_CONTEXT_REQUIRED

    # Add reverse parent forms: if offer keyword maps FROM a recipe form via
    # INGREDIENT_PARENTS, include that form too so it matches in recipe text.
    # e.g., offer keyword 'havskräftor' → also add 'kräftor' (recipe form)
    # e.g., offer keyword 'brie' → also add 'brieost' (recipe form)
    # Put reverse forms FIRST — they are more specific (recipe-text forms) and
    # avoid false context-word blocks (e.g., 'brieost' passes context check
    # while 'brie' requires standalone word boundary)
    # Reverse parent forms that should NOT be re-added to product keywords.
    # 'nöt' → 'nötkött' in INGREDIENT_PARENTS replaces the ambiguous 'nöt' (nut/cattle)
    # with specific 'nötkött'. Reverse lookup would add 'nöt' back, defeating the fix.
    _REVERSE_PARENT_EXCLUSIONS = frozenset({
        'nöt', 'not',
        # Fresh-chili recipe forms map to generic "chili" on the ingredient side.
        # Do NOT add them back to every chili product during precompute, or cached
        # matching becomes broader than uncached matching ("röd chilifrukt" starts
        # accepting green/plain chili offers through synthetic reverse keywords).
        'chilifrukt', 'chilifrukter',
        # Glass: prevent reverse-parent from re-adding all glass flavor variants
        # when product has 'vaniljglass' keyword. Each product should only have
        # its own flavor keyword, not all flavors.
        'glass', 'gräddglass', 'graddglass', 'isglass',
        'chokladglass', 'jordgubbsglass', 'kanelglass',
        'sojaglass', 'lakritsglass',
        # skånsksenap: only added to products whose name actually contains "skånsk"
        # (via name-conditional rule below). Reverse-parent would add it to ALL
        # senap products, which is exactly what we don't want.
        'skånsksenap',
        # Pasta shape recipe forms map to the generic pasta families on the
        # ingredient side. Do NOT add them back to every plain pasta product
        # during precompute, or generic/fylld/färdig pasta starts pretending to
        # be every individual shape such as maccaronetti, tortiglioni or
        # spaghetti.
        'fusilli', 'penne', 'rigatoni', 'farfalle',
        'conchiglie', 'conchigle', 'gemelli', 'radiatori',
        'tortiglioni', 'caserecce', 'girandole',
        'strozzapreti', 'strozzapretti', 'mafalda',
        'maniche', 'ziti', 'makaroner', 'maccaronetti',
        'spaghetti', 'spagetti', 'linguine', 'tagliatelle',
        'fettuccine', 'fettuccini', 'fettucine', 'pappardelle',
        'tagliolini', 'bucatini', 'capellini',
    })
    extra_keywords = []

    def _append_extra_keyword(keyword: str) -> None:
        if keyword not in keywords and keyword not in extra_keywords:
            extra_keywords.append(keyword)

    for kw in keywords:
        for child in _INGREDIENT_PARENTS_REVERSE.get(kw, ()):
            if child not in keywords and child not in _REVERSE_PARENT_EXCLUSIONS:
                extra_keywords.append(child)
        # One-way offer-side additions (e.g., färskpotatis → potatis)
        for extra in OFFER_EXTRA_KEYWORDS.get(kw, ()):
            if extra not in keywords and extra not in extra_keywords:
                extra_keywords.append(extra)
    # Name-conditional: "Senap Skånsk ..." products get 'skånsksenap' keyword so they
    # match "senap skånsk" ingredient text (normalized to "skånsksenap"). Other senap
    # products (Dijon, Amerikansk etc.) do NOT get this keyword, so they are blocked
    # by suffix-protection on 'senap' when ingredient is "skånsksenap".
    if 'senap' in keywords and 'skånsk' in offer_name.lower():
        _append_extra_keyword('skånsksenap')
    # Flour-style durum products appear both as the compound "Durumvetemjöl" and
    # the spaced form "Mjöl Durumvete". Give the spaced form the same compound
    # keyword so measured recipe lines can match both without broadening generic
    # durumvete products.
    if 'durumvete' in keywords and 'mjöl' in keywords:
        _append_extra_keyword('durumvetemjöl')
    # Name-conditional: "Laxfilé Färsk Back Loin" / "Mid Loin" are sushi-grade salmon
    if 'laxfilé' in keywords and 'loin' in offer_name.lower():
        _append_extra_keyword('sushilax')
    # Name-conditional: "Buljong Mörk Oxe" — 'mörk' blocks space normalization
    if 'buljong' in keywords and 'oxe' in offer_name.lower().split():
        _append_extra_keyword('oxbuljong')
    # Name-conditional: "Rosta" (Pågen bread brand) — 'rosta' is a STOP_WORD (cooking method),
    # so it extracts no keywords. Add 'formbröd' directly for this bread product.
    if offer_category == 'bread' and not keywords and offer_name.lower().startswith('rosta'):
        _append_extra_keyword('formbröd')
    # Name-conditional: Quorn mince products should expose the specific mince form
    # without broadening other Quorn-branded filets/skivor/pepperoni items.
    if brand and brand.lower() == 'quorn' and 'mince/färs' in keywords:
        _append_extra_keyword('quornfärs')
        _append_extra_keyword('quornfars')
    # Name-conditional: Quorn pieces/bitar should satisfy explicit Quorn-piece requests
    # without widening other vegobitar products from unrelated brands.
    if brand and brand.lower() == 'quorn' and 'vegobitar' in keywords:
        _append_extra_keyword('quornbitar')
    # Name-conditional: "5-minuters sillfilé" = inläggningssill product
    # The "5-minuter" prefix identifies it as pickling-ready herring fillet.
    # keyword 'sillfilé' alone is too broad, so we only add 'inläggningssill'
    # when the product name explicitly says '5-minuter'.
    _offer_lower_pre = offer_name.lower()
    _offer_words_pre = set(name_lower_simple.split())
    if 'sillfilé' in keywords and '5-minuter' in _offer_lower_pre:
        _append_extra_keyword('inläggningssill')
        _append_extra_keyword('5-minuterssill')
    # Name-conditional: teriyaki sauce bottles often use English "sauce" or
    # adjacent sauce/marinade naming instead of the exact Swedish compound.
    # Keep the bridge narrow so jerky, tempeh and wok dishes do not gain the
    # dedicated sauce keyword just because they mention the teriyaki flavor.
    _teriyaki_sauce_cues = frozenset({'sauce', 'sojasås', 'sojasas', 'marinad'})
    if 'teriyaki' in keywords and (_offer_words_pre & _teriyaki_sauce_cues):
        _append_extra_keyword('teriyakisås')
    if 'teriyakimarinad' in keywords:
        _append_extra_keyword('teriyakisås')
    # Name-conditional: satay sauce bottles often use English "satay" + "sauce"
    # instead of the Swedish recipe compound "sataysås". Keep the bridge narrow
    # so ready meals and satay skewers do not gain the dedicated sauce keyword.
    _satay_sauce_cues = frozenset({'sauce', 'sås', 'sas'})
    if 'satay' in _offer_words_pre and (_offer_words_pre & _satay_sauce_cues):
        _append_extra_keyword('sataysås')
    # Name-conditional: korma sauce jars/bases often sell as plain "Korma"
    # or "Grytbas Korma" without the exact Swedish compound "kormasås".
    # Keep the bridge narrow so spice mixes and ready meals do not gain the
    # dedicated sauce keyword just because they mention the korma flavor.
    _korma_sauce_cues = frozenset({'sauce', 'sås', 'sas', 'grytbas'})
    _korma_disallowed_cues = frozenset({
        'krydda', 'krydda', 'kryddmix', 'mix', 'paste', 'pasta',
        'färdigmat', 'fardigmat', 'ready', 'meal', 'kyckling', 'chicken',
        'tempeh', 'tofu', 'wok', 'burgare',
    })
    if (
        'korma' in _offer_words_pre
        and not (_offer_words_pre & _korma_disallowed_cues)
        and (
            (_offer_words_pre & _korma_sauce_cues)
            or len(_offer_words_pre) <= 3
        )
    ):
        _append_extra_keyword('kormasås')
    # Name-conditional: explicit "Chipotle Paste" products should satisfy the
    # exact recipe compound "chipotlepasta" without reopening the generic dry
    # chipotle spice family or nearby sauce/mayo products.
    if 'chipotle' in _offer_words_pre and ('paste' in _offer_words_pre or 'pasta' in _offer_words_pre):
        _append_extra_keyword('chipotlepasta')
    # Name-conditional: pure Parma ham products sold as "Prosciutto di Parma"
    # should match recipe ingredients saying "parmaskinka". Keep this narrow:
    # add the bridge only for deli-style prosciutto products, not for prepared
    # foods like tortellini or pinsa that merely contain prosciutto as a filling/topping.
    _parma_prepared_keywords = frozenset({'tortellini', 'tortelloni', 'ravioli', 'pinsa', 'pizza'})
    if (
        'prosciutto' in keywords
        and 'parma' in _offer_lower_pre
        and not any(kw in keywords for kw in _parma_prepared_keywords)
    ):
        _append_extra_keyword('parmaskinka')
    # Name-conditional: color-specific curry pastes should match recipe wording
    # like "röd curry" without broadening all curry-flavored convenience products.
    _has_curry_paste_family = (
        'currypasta' in keywords
        or any(kw in keywords for _, _, kw in _COLORED_CURRY_RULES)
        or ('curry' in _offer_words_pre and ('paste' in _offer_words_pre or 'pasta' in _offer_words_pre))
    )
    for color_words, curry_keyword, paste_keyword in _COLORED_CURRY_RULES:
        has_color = bool(_offer_words_pre & color_words)
        if not has_color:
            continue
        if _has_curry_paste_family:
            _append_extra_keyword(paste_keyword)
            _append_extra_keyword(curry_keyword)
            break
    # Name-conditional: fish roe "rom" → add "stenbitsrom" alongside "rom"
    # "Finkornig Rom Röd" / "Röd Rom Finkornig" should match BOTH "stenbitsrom" AND "rom" recipes
    # Keep 'rom' so recipes saying "80 g rom (valfri sort)" also match
    if offer_category == 'fish' and 'rom' in keywords:
        if 'stenbitsrom' not in keywords:
            extra_keywords.append('stenbitsrom')
    # Generic fish-roe recipe lines often just say "rom" while products are sold
    # as specific roe families such as löjrom, forellrom or stenbitsrom.
    # Add the generic roe keyword on the product side so plain "rom" reaches them.
    if _offer_is_roe_family(keywords):
        _append_extra_keyword('rom')

    # Name-conditional: "Kryddsmör Vitlök" / "Kryddsmör Roasted Garlic" = vitlökssmör
    # ICA sells garlic compound butter as "Kryddsmör Vitlök" — same product as "Vitlökssmör".
    # Only trigger when vitlök/garlic is present so other kryddsmör variants (dill etc.) are unaffected.
    if 'kryddsmör' in keywords and any(w in _offer_lower_pre for w in ('vitlök', 'garlic')):
        if 'vitlökssmör' not in keywords and 'vitlökssmör' not in extra_keywords:
            extra_keywords.append('vitlökssmör')
    # Name-conditional: "Block Ljus" / "Block Mörk" / "Vit Block" = blockchoklad (Willys naming)
    _offer_lower = offer_name.lower()
    if _offer_lower.startswith('block ') and any(w in _offer_lower for w in ('ljus', 'mörk', 'vit')):
        if 'bakchoklad' not in keywords and 'bakchoklad' not in extra_keywords:
            extra_keywords.append('bakchoklad')
        # Also add 'blockchoklad' (recipe compound form) — INGREDIENT_PARENTS reverse
        # lookup runs before this name-conditional, so we must add it explicitly.
        if 'blockchoklad' not in keywords and 'blockchoklad' not in extra_keywords:
            extra_keywords.append('blockchoklad')
    # CARRIER_CONTEXT_REQUIRED: re-add stripped flavor words as keywords
    # so "Pastasås Basilika" can match "pastasås basilika" ingredient via 'basilika'.
    # Also apply OFFER_EXTRA_KEYWORDS for re-added flavors (e.g., 'ostar' → 'ost').
    if _carrier_ctx_hits and carrier_stripped:
        _ek_set = set(extra_keywords)
        for fw in carrier_stripped:
            if fw not in kw_set_check and fw not in _ek_set:
                extra_keywords.append(fw)
                _ek_set.add(fw)
                for oek in OFFER_EXTRA_KEYWORDS.get(fw, ()):
                    if oek not in kw_set_check and oek not in _ek_set:
                        extra_keywords.append(oek)
                        _ek_set.add(oek)

    extra_kw_set = set(extra_keywords)
    if extra_keywords:
        keywords = extra_keywords + keywords

    # Pre-normalize the offer name (was being done per-recipe before!)
    # Apply space normalizations too — fixes "Körsbärs- Tomater" → "Körsbärstomater"
    # so PPR can find compound words like "körsbärstomat" in the name.
    name_normalized = _apply_space_normalizations(fix_swedish_chars(offer_name).lower())

    # Pre-compute which context words this offer contains
    # (avoid looping through 30+ words per recipe match)
    # NOTE: Brand names with food keywords (e.g., "Jokkmokks korv & rökeri")
    # are stripped from product names in db_saver.py via strip_brand_from_name(),
    # so they won't interfere with context checks here.
    context_words = set()
    _is_glass_product = 'glass' in name_words_all or any(w.endswith('glass') for w in name_words_all)
    if not _is_glass_product:
        for context_word in CONTEXT_REQUIRED_WORDS:
            if _has_word_boundary_match(context_word, name_normalized):
                context_words.add(context_word)
    # Glass products: glass normalization already handles flavor matching
    # via flavor-specific keywords. Context words like 'vanilj' would block
    # standalone "glass" recipes from matching vanilla products.

    # CARRIER_CONTEXT_REQUIRED: all products with these carriers require the
    # carrier word in ingredient text. Prevents pastasås products from matching
    # non-pastasås ingredients (e.g., "2 kvistar basilika").
    if _carrier_ctx_hits:
        context_words.update(_carrier_ctx_hits)

    # NOTE: Context word exemptions (CONTEXT_WORD_KEYWORD_EXEMPTIONS) are now
    # checked per-keyword at match time in matches_ingredient_fast(), not here.
    # This prevents a keyword's exemption from removing context for ALL keywords.
    # e.g., 'hamburgare' exempts 'burgare' but 'grillost' still requires it.

    # Pre-compute specialty qualifiers found in this offer
    # e.g., {'skinka': {'serrano'}} if offer is "Serrano Skinka"
    # Also check keywords list: "Curry Paste Red" has keyword 'currypasta'
    # but name_normalized is "curry paste red" (no compound match)
    found_qualifiers = {}
    keywords_set = set(keywords)
    for base_word, qualifiers in SPECIALTY_QUALIFIERS.items():
        if base_word in name_normalized or base_word in keywords_set:
            # "Steklök röd" is sold as a specific onion variety, not as generic
            # colored onion. Keep the exact steklök family matchable without
            # letting the incidental "röd" label participate in lök qualifier
            # blocking/ranking.
            if (
                base_word == 'lök'
                and any(kw in keywords_set for kw in ('steklök', 'steklok', 'steklökar', 'steklokar'))
            ):
                continue
            found_in_offer = set()
            for qualifier in qualifiers:
                if qualifier in name_normalized:
                    found_in_offer.add(qualifier)
            if found_in_offer:
                found_qualifiers[base_word] = found_in_offer

    # Pre-compute whether this product needs per-ingredient PROCESSED_PRODUCT_RULES check
    # Avoids looping through all rules per recipe match
    needs_processed_check = False
    for base_word, indicators in PROCESSED_PRODUCT_RULES.items():
        if base_word in name_normalized:
            if any(ind in name_normalized for ind in indicators):
                needs_processed_check = True
                break

    # Pre-compute whether this product is a juice product (for JUICE_RULE_KEYWORDS check)
    is_juice_product = any(ind in name_normalized for ind in JUICE_PRODUCT_INDICATORS)

    # Pre-compute cuisine context triggers for this product
    cuisine_triggers = {}
    for trigger, contexts in CUISINE_CONTEXT.items():
        if trigger in name_normalized:
            cuisine_triggers[trigger] = contexts
            break  # Only one trigger per product

    # Pre-compute qualifier words for _QUALIFIER_REQUIRED_KEYWORDS (avoids regex per match)
    qualifier_words = ()
    for kw in keywords:
        if kw in _QUALIFIER_REQUIRED_KEYWORDS:
            qualifier_words = tuple(w for w in _WORD_PATTERN_4PLUS.findall(name_normalized) if w != kw)
            break

    # Pre-compute SECONDARY_INGREDIENT_PATTERNS: which search_words this product blocks
    # Moves product-side blocker checks from fast path (~34K calls) to precompute (~210 calls)
    secondary_blocks = set()
    for search_word, (blockers, exceptions) in SECONDARY_INGREDIENT_PATTERNS.items():
        for blocker in blockers:
            if blocker in name_normalized:
                if not any(exc in name_normalized for exc in exceptions):
                    secondary_blocks.add(search_word)
                break

    # Pre-compute PROCESSED_PRODUCT_RULES: product-side evaluation done once
    # Each entry: (base_word, 'strict', matching_indicators) or (base_word, 'relaxed', first_indicator, all_indicators)
    # base_word included so fast path can skip rules not relevant to matched_keyword
    processed_checks = []
    for base_word, indicators in PROCESSED_PRODUCT_RULES.items():
        if base_word in name_normalized:
            if (
                base_word == 'lök'
                and any(kw in keywords_set for kw in ('steklök', 'steklok', 'steklökar', 'steklokar'))
            ):
                continue
            exemptions = PROCESSED_RULES_COMPOUND_EXEMPTIONS.get(base_word)
            if exemptions and any(ex in name_normalized for ex in exemptions):
                continue
            if base_word in STRICT_PROCESSED_RULES:
                product_indicators = tuple(ind for ind in indicators if ind in name_normalized)
                if product_indicators:
                    # Expand with equivalents for matching: "malen" ↔ "mald"/"malet"
                    expanded = set(product_indicators)
                    for ind in product_indicators:
                        expanded.update(_PROCESSED_INDICATOR_EQUIVALENTS.get(ind, ()))
                    processed_checks.append((base_word, 'strict', tuple(expanded)))
            else:
                for indicator in indicators:
                    if indicator in name_normalized:
                        processed_checks.append((base_word, 'relaxed', indicator, indicators))
                        break

    # Pre-compute SPICE_VS_FRESH_RULES: which base_words have matching product blockers
    # Maps base_word -> dict with 'mode' ('block' or 'require') and indicators
    # Only check rules for base_words that are in the product's own keywords,
    # otherwise coincidental word matches (e.g., "röd" in "Paprika Röd") trigger
    # unrelated rules (e.g., chili's blocked_product_words includes "röd").
    keywords_set = set(keywords)
    spice_fresh_blocks = {}
    for base_word, rules in SPICE_VS_FRESH_RULES.items():
        if base_word not in keywords_set:
            continue
        # Jalapeño products outside produce categories are effectively jarred/
        # processed in current store data, even when the product name is sparse
        # ("Jalapenos 225g"). But some fresh produce offers are miscategorized,
        # e.g. "Grön jalapeno ... Klass 1" stored as meat. Keep sparse non-produce
        # names as jarred fallback while still blocking obvious fresh produce cues.
        if base_word in {'jalapeno', 'jalapenos'} and offer_category not in {'fruit', 'vegetables'}:
            _pickled_name_words = rules.get('blocked_product_words', set())
            if any(word in name_normalized for word in _pickled_name_words):
                spice_fresh_blocks[base_word] = {
                    'mode': 'require',
                    'indicators': rules['allowed_indicators'],
                }
                continue
            _jalapeno_fresh_cues = frozenset({
                'klass', 'kl1',
                'färsk', 'farsk',
                'grön', 'gron',
                'röd', 'rod',
                'mörk', 'mork',
            })
            if any(cue in name_normalized for cue in _jalapeno_fresh_cues):
                spice_fresh_blocks[base_word] = {
                    'mode': 'block',
                    'indicators': rules['pickled_indicators'],
                }
            else:
                spice_fresh_blocks[base_word] = {
                    'mode': 'require',
                    'indicators': rules['allowed_indicators'],
                }
            continue
        # Check preserved/processed product words first
        for blocked in rules['blocked_product_words']:
            if blocked in name_normalized:
                if 'allowed_indicators' in rules:
                    spice_fresh_blocks[base_word] = {
                        'mode': 'require',
                        'indicators': rules['allowed_indicators'],
                    }
                else:
                    spice_fresh_blocks[base_word] = {
                        'mode': 'block',
                        'indicators': rules['spice_indicators'],
                    }
                break
        else:
            # No processed match — check if it's a fresh product
            if 'fresh_product_words' in rules:
                for fresh_word in rules['fresh_product_words']:
                    if fresh_word in name_normalized:
                        spice_fresh_blocks[base_word] = {
                            'mode': 'block',
                            'indicators': rules['dried_indicators'],
                        }
                        break

    # Pre-compute INGREDIENT_REQUIRES_IN_PRODUCT: words that, if found in the
    # ingredient but NOT in the product, block the match (when matched on a different keyword)
    ingredient_context_missing = set()
    for req_word in INGREDIENT_REQUIRES_IN_PRODUCT:
        if req_word not in name_normalized:
            ingredient_context_missing.add(req_word)

    return {
        # Sort original product keywords first (longest-first), then derived
        # keywords (longest-first).  This ensures matches_ingredient_fast returns
        # the real product keyword (e.g. 'timjan') before a parent-derived form
        # (e.g. 'timjankvistar') that only matches specific recipe wordings.
        'keywords': sorted(keywords, key=lambda k: (k in extra_kw_set, -len(k))),
        'name_normalized': name_normalized,
        'context_words': context_words,
        'specialty_qualifiers': found_qualifiers,
        'needs_processed_check': needs_processed_check,
        'is_juice_product': is_juice_product,
        'cuisine_triggers': cuisine_triggers,
        'qualifier_words': qualifier_words,
        'secondary_blocks': secondary_blocks,
        'processed_checks': processed_checks,
        'spice_fresh_blocks': spice_fresh_blocks,
        'ingredient_context_missing': ingredient_context_missing,
        'weight_grams': weight_grams,
        'carrier_stripped': carrier_stripped,
        'category': (offer_category or '').lower(),
    }


def _prepare_fast_ingredient_text(
    ingredient_text: str,
    _prenormalized: bool = False,
) -> str:
    """Normalize ingredient text exactly as the fast matcher expects it.

    This helper is intentionally behavior-preserving: it extracts the existing
    ingredient-side preprocessing from ``matches_ingredient_fast()`` so other
    call sites can reuse the same canonical text representation without
    copy/pasting matcher logic.
    """
    ingredient_lower = ingredient_text if _prenormalized else fix_swedish_chars(ingredient_text).lower()

    # Apply space normalization so compound keywords match spaced ingredient text
    # e.g., keyword "rödcurrypasta" matches ingredient "röd currypasta"
    ingredient_lower = _SPACE_NORM_PATTERN.sub(lambda m: _SPACE_NORM_LOOKUP[m.group()], ingredient_lower)
    ingredient_lower = preserve_cheese_preference_parentheticals(ingredient_lower)
    ingredient_lower = preserve_parenthetical_chili_alias(ingredient_lower)
    ingredient_lower = preserve_fresh_pasta_parenthetical(ingredient_lower)
    ingredient_lower = preserve_parenthetical_grouped_herb_leaves(ingredient_lower)
    ingredient_lower = preserve_non_concentrate_parenthetical(ingredient_lower)
    ingredient_lower = preserve_parenthetical_shiso_alternatives(ingredient_lower)
    if is_subrecipe_reference_text(ingredient_lower):
        return ''
    ingredient_lower = strip_biff_portion_prep_phrase(ingredient_lower)
    ingredient_lower = normalize_measured_durumvete_flour(ingredient_lower)
    ingredient_lower = normalize_measured_risotto_rice(ingredient_lower)
    ingredient_lower = rewrite_truncated_eller_compounds(ingredient_lower)
    ingredient_lower = rewrite_mince_of_alternatives(ingredient_lower)
    # Parenthetical "eller" segments are real ingredient alternatives and must
    # survive the later generic paren stripping.
    ingredient_lower = re.sub(r'\(\s*eller\s+([^)]*)\)', r' eller \1', ingredient_lower, flags=re.IGNORECASE)
    ingredient_lower = _PARENS_PATTERN.sub(' ', ingredient_lower)
    ingredient_lower = re.sub(r'\btandori\b', 'tandoori', ingredient_lower)
    # "gurt" is plant-based shorthand for yoghurt. Keep the original token so
    # vego-only yoghurt matching still applies, but also expose "yoghurt" for
    # the normal keyword path.
    ingredient_lower = re.sub(r'\bgurt\b', 'gurt yoghurt', ingredient_lower)
    ingredient_lower = re.sub(
        r'\b([a-zåäöé]+?)(sylt|marmelad)\s+eller\s+-(sylt|marmelad)\b',
        r'\1\2 eller \1\3',
        ingredient_lower,
    )
    if _ingredient_requests_generic_frozen_fish_fillet(ingredient_lower):
        ingredient_lower += ' fiskfilé'
    ingredient_lower = _append_canonical_keyword_synonyms(ingredient_lower)

    # Plant-based "matlagning" is recipe shorthand for cooking-cream products.
    # Mirror the ingredient extraction aliases here because the fast matcher works
    # on raw ingredient text, not extracted ingredient keywords.
    if 'havrebaserad matlagning' in ingredient_lower:
        ingredient_lower += ' havregrädde grädde'
    if 'soyabaserad matlagning' in ingredient_lower or 'sojabaserad matlagning' in ingredient_lower:
        # Append 'grädde' only — NOT 'soja', which would match soy sauce products (FP).
        # Soy-based cream products (Alpro matlagningsgrädde etc.) already use 'grädde' keyword.
        ingredient_lower += ' grädde'
    if any(phrase in ingredient_lower for phrase in (
        'vegansk matlagning',
        'växtbaserad matlagning',
        'vaxtbaserad matlagning',
        'vegetabilisk matlagning',
    )):
        ingredient_lower += ' grädde'
    if re.search(r'\b(?:blandade\s+)?färska?\s+bär\b', ingredient_lower):
        ingredient_lower += ' hallon blåbär jordgubbar björnbär vinbär krusbär smultron'
    if 'teriyakisås' in ingredient_lower and 'teriyaki' not in ingredient_lower:
        ingredient_lower += ' teriyaki'
    if (
        'paprika' in ingredient_lower
        and 'paprikapulver' not in ingredient_lower
        and not any(fi in ingredient_lower for fi in ('färsk', 'farsk'))
        and re.search(r'\b(?:tsk|tesked|krm)\b', ingredient_lower)
    ):
        ingredient_lower += ' paprikapulver'

    # Normalize singular → plural for cherry tomatoes so offers with keyword
    # "körsbärstomater" match ingredient text with singular "körsbärstomat".
    # Swedish pluralization: körsbärstomat → körsbärstomater (longer plural).
    if 'körsbärstomat' in ingredient_lower and 'körsbärstomater' not in ingredient_lower:
        ingredient_lower = ingredient_lower.replace('körsbärstomat', 'körsbärstomater')

    return ingredient_lower


def _spice_vs_fresh_key_for_match(matched_keyword: str) -> Optional[str]:
    """Return the spice/fresh rule key that applies to a matched keyword."""
    if matched_keyword in SPICE_VS_FRESH_RULES:
        return matched_keyword
    for base_word in SPICE_VS_FRESH_RULES:
        if matched_keyword.startswith(base_word) and len(matched_keyword) > len(base_word):
            return base_word
    return None


def _passes_precomputed_spice_fresh_rule(
    offer_data: Dict,
    ingredient_lower: str,
    matched_keyword: str,
) -> bool:
    """Apply product-side SPICE_VS_FRESH_RULES cached in precompute_offer_data()."""
    svf_key = _spice_vs_fresh_key_for_match(matched_keyword)
    if not svf_key:
        return True

    svf_rule = offer_data.get('spice_fresh_blocks', {}).get(svf_key)
    if not svf_rule:
        return True

    if svf_rule['mode'] == 'require':
        return any(ind in ingredient_lower for ind in svf_rule['indicators'])

    return not ingredient_has_spice_indicator(
        set(svf_rule['indicators']),
        ingredient_lower,
        svf_key,
    )


def matches_ingredient_fast(
    offer_data: Dict,
    ingredient_text: str,
    _prenormalized: bool = False,
    _prepared_fast_text: bool = False,
    _ingredient_words: list = None
) -> Optional[str]:
    """
    Fast version of matches_ingredient using pre-computed offer data.

    Args:
        offer_data: Pre-computed dict from precompute_offer_data()
        ingredient_text: Full ingredient text (normalized if _prenormalized=True)
        _prenormalized: If True, skip fix_swedish_chars on ingredient_text
        _prepared_fast_text: If True, ingredient_text already matches the exact
            output of _prepare_fast_ingredient_text() and can be used as-is.
        _ingredient_words: Pre-computed word list from ingredient text (avoids
            re-parsing with regex on every FP blocker check)

    Returns:
        The matched keyword, or None if no match
    """
    keywords = offer_data['keywords']

    # Quick exit if no keywords
    if not keywords:
        return None

    ingredient_lower = (
        ingredient_text
        if _prepared_fast_text
        else _prepare_fast_ingredient_text(
            ingredient_text,
            _prenormalized=_prenormalized,
        )
    )

    # STEP 1: Fast keyword matching (most products won't match)
    matched_keyword = None
    for keyword in keywords:
        if keyword in ingredient_lower:
            # Block compound word suffix matches (e.g., "köttbullar" in "fiskköttbullar")
            if keyword in _SUFFIX_PROTECTED_KEYWORDS:
                if not _has_word_boundary_match(keyword, ingredient_lower):
                    continue
            # Block embedded matches (e.g., "ris" in "grissini" but allow "basmatiris")
            if keyword in _EMBEDDED_PROTECTED_KEYWORDS:
                if not _has_word_edge_match(keyword, ingredient_lower):
                    continue
            # Check for false positives (e.g., "ost" in "ostronsås")
            # Smart blocker: only block if keyword appears EXCLUSIVELY
            # inside blocker words. If keyword also appears standalone
            # or at word-start of a non-blocker compound, allow the match.
            if keyword in FALSE_POSITIVE_BLOCKERS:
                blockers = FALSE_POSITIVE_BLOCKERS[keyword]
                has_blocker = any(b in ingredient_lower for b in blockers)
                if has_blocker:
                    words_in_text = _ingredient_words if _ingredient_words is not None else _WORD_PATTERN.findall(ingredient_lower)
                    has_valid = False
                    for w in words_in_text:
                        if keyword not in w:
                            continue
                        if w == keyword:
                            has_valid = True
                            break
                        if w.startswith(keyword):
                            if not any(w.startswith(b) for b in blockers):
                                has_valid = True
                                break
                    if not has_valid:
                        continue  # keyword ONLY inside blocker words → skip
            # Compound strictness: if keyword is part of a compound word in recipe,
            # product must contain the qualifier (prefix or suffix)
            if keyword in _COMPOUND_STRICT_KEYWORDS or keyword in _COMPOUND_STRICT_PREFIX_KEYWORDS:
                pname = offer_data['name_normalized']
                if keyword in _COMPOUND_STRICT_KEYWORDS:
                    if _check_compound_strict(keyword, ingredient_lower, pname,
                                              _ingredient_words):
                        continue
                if keyword in _COMPOUND_STRICT_PREFIX_KEYWORDS:
                    if _check_compound_strict(keyword, ingredient_lower, pname,
                                              _ingredient_words, check_prefix=True):
                        continue
            if _blocked_by_exact_compound_only(ingredient_lower, keyword):
                continue
            # Product-name blockers are validated later per ingredient in
            # recipe_matcher.py, which avoids cross-ingredient leakage such as
            # "röd" from one ingredient unblocking "Red Curry Thai" for another.
            matched_keyword = keyword
            break

    # Qualifier check: "dressing" requires a flavor/type qualifier from the product
    # name to also appear in the ingredient. (qualifier_words pre-computed per offer)
    if matched_keyword and matched_keyword in _QUALIFIER_REQUIRED_KEYWORDS:
        qualifier_words = offer_data['qualifier_words']
        if qualifier_words and not any(w in ingredient_lower for w in qualifier_words):
            matched_keyword = None

    # No direct match? Try parent mapping (e.g., "jasminris" → "ris")
    if not matched_keyword:
        for keyword in keywords:
            parent = INGREDIENT_PARENTS.get(keyword) or PARENT_MATCH_ONLY.get(keyword)
            if parent and parent in ingredient_lower:
                # Apply suffix protection to parent keyword (e.g., "ris" in "grissini")
                if parent in _SUFFIX_PROTECTED_KEYWORDS:
                    if not _has_word_boundary_match(parent, ingredient_lower):
                        continue
                if parent in _EMBEDDED_PROTECTED_KEYWORDS:
                    if not _has_word_edge_match(parent, ingredient_lower):
                        continue
                # FP-blocker check for parent path: use same smart logic as
                # STEP 1 — check per-word whether the parent keyword appears in
                # a valid context (standalone or valid compound start).
                # "pasta" in "pastasås" → blocked (pastasås is a blocker)
                # "pasta" in "400 g pasta" → allowed (standalone word)
                blockers = FALSE_POSITIVE_BLOCKERS.get(parent, set())
                if blockers:
                    has_blocker = any(b in ingredient_lower for b in blockers)
                    if has_blocker:
                        words_in_text = _WORD_PATTERN.findall(ingredient_lower)
                        has_valid = False
                        for w in words_in_text:
                            if parent not in w:
                                continue
                            if w == parent:
                                has_valid = True
                                break
                            if w.startswith(parent):
                                if not any(w.startswith(b) for b in blockers):
                                    has_valid = True
                                    break
                        if not has_valid:
                            continue
                # Compound strictness for parent path too
                pname = offer_data['name_normalized']
                if parent in _COMPOUND_STRICT_KEYWORDS or parent in _COMPOUND_STRICT_PREFIX_KEYWORDS:
                    if parent in _COMPOUND_STRICT_KEYWORDS:
                        if _check_compound_strict(parent, ingredient_lower, pname):
                            continue
                    if parent in _COMPOUND_STRICT_PREFIX_KEYWORDS:
                        if _check_compound_strict(parent, ingredient_lower, pname,
                                                  check_prefix=True):
                            continue
                # Also check compound-strict for the ORIGINAL product keyword,
                # not just the parent. Handles: product keyword 'glass' →
                # parent 'vaniljglass', but 'glass' in compound-strict requires
                # prefix 'vanilj' in product name to match 'vaniljglass' recipe.
                if keyword in _COMPOUND_STRICT_KEYWORDS:
                    if _check_compound_strict(keyword, ingredient_lower, pname):
                        continue
                if keyword in _COMPOUND_STRICT_PREFIX_KEYWORDS:
                    if _check_compound_strict(keyword, ingredient_lower, pname,
                                              check_prefix=True):
                        continue
                if _blocked_by_exact_compound_only(ingredient_lower, parent):
                    continue
                # NOTE: PRODUCT_NAME_BLOCKERS for parent path also in recipe_matcher.py
                matched_keyword = parent
                break

    if (
        not matched_keyword
        and _ingredient_implies_whole_kyckling(ingredient_lower)
        and _product_is_whole_kyckling_offer(
            keywords,
            offer_data.get('name_normalized', ''),
            offer_data.get('specialty_qualifiers'),
        )
    ):
        matched_keyword = 'kyckling'
    if (
        not matched_keyword
        and any(kw in keywords for kw in ('matbrödsjäst', 'matbrodsjast'))
        and _ingredient_requests_generic_bread_yeast(ingredient_lower)
    ):
        matched_keyword = 'matbrödsjäst'

    if not matched_keyword:
        return None

    if (
        matched_keyword == 'helkyckling'
        and _ingredient_implies_whole_kyckling(ingredient_lower)
        and 'helkyckling' not in ingredient_lower
    ):
        matched_keyword = 'kyckling'

    # STEP 1b: Keyword suppressed by context — if ingredient text contains a context
    # word that makes this keyword irrelevant, suppress it.
    # e.g., 'bittermandel' should suppress generic 'mandel' matches.
    if matched_keyword == 'fiskfilé' and 'vit fiskfilé' in ingredient_lower:
        if 'laxfilé' in keywords or 'laxfile' in keywords:
            return None
    if matched_keyword in KEYWORD_SUPPRESSED_BY_CONTEXT:
        suppressors = KEYWORD_SUPPRESSED_BY_CONTEXT[matched_keyword]
        if any(s in ingredient_lower for s in suppressors):
            return None
    if not _pimiento_product_allowed(
        offer_data['name_normalized'],
        ingredient_lower,
        matched_keyword,
    ):
        return None
    if _steak_style_tuna_product_allowed(
        offer_data['name_normalized'],
        ingredient_lower,
        matched_keyword,
    ):
        return matched_keyword

    # STEP 1c: Preserved-vs-fresh beet check.
    # "inlagda rödbetor" / "Rödbetor Konserverade" = pickled beets, NOT fresh produce.
    # If ingredient signals preserved, block products that lack any preservation indicator
    # in their name (i.e. fresh Rödbeta Klass 1).
    #
    # "skivade rödbetor" is ambiguous: it can mean jarred sliced beets, but in fresh-produce
    # recipe lines it often only describes prep ("2 tunt skivade medelstora rödbetor").
    # Treat sliced wording as preserved only when the ingredient does not also look like
    # a fresh-root prep line.
    #
    # NOTE: check_processed_product_rules in recipe_matcher.py handles the PRODUCT-has-indicator
    # direction (blocks pickled products from fresh recipes) but only fires when the PRODUCT
    # has an indicator — fresh products (no indicator) bypass that check entirely.
    _BEET_KW = frozenset({'rödbeta', 'rödbetor', 'rodbetor'})
    _BEET_STRONG_PRESERVED = frozenset({
        'inlagd', 'inlagda',
        'konserverad', 'konserverade',
        'gammaldags', 'gammeldags',
        'förkokt', 'förkokta',
        'forkokt', 'forkokta',
    })
    _BEET_SLICED_WORDS = frozenset({'skivad', 'skivade', 'skivor'})
    _BEET_WHOLE_PRESERVED_PRODUCT = frozenset({'hela'})
    _BEET_PRESERVED = frozenset({
        *_BEET_STRONG_PRESERVED,
        *_BEET_SLICED_WORDS,
        *_BEET_WHOLE_PRESERVED_PRODUCT,
    })
    _BEET_FRESH_PREP_CUES = frozenset({
        'medelstor', 'medelstora',
        'stor', 'stora',
        'liten', 'litet', 'lilla', 'små', 'sma',
        'tunt', 'tunna', 'tunt skivade', 'tunt skivad',
        'rå', 'råa', 'ra', 'raa',
        'färsk', 'färska', 'farsk', 'farska',
    })
    if matched_keyword in _BEET_KW:
        has_strong_preserved = any(ind in ingredient_lower for ind in _BEET_STRONG_PRESERVED)
        has_sliced_wording = any(ind in ingredient_lower for ind in _BEET_SLICED_WORDS)
        has_packaged_whole_beet_wording = _ingredient_requests_preserved_whole_beets(ingredient_lower)
        fresh_beet_prep = any(cue in ingredient_lower for cue in _BEET_FRESH_PREP_CUES)
        ingredient_wants_preserved = (
            has_strong_preserved
            or has_packaged_whole_beet_wording
            or (has_sliced_wording and not fresh_beet_prep)
        )
        name_norm = offer_data['name_normalized']
        if has_sliced_wording and fresh_beet_prep and not has_strong_preserved:
            if any(ind in name_norm for ind in _BEET_PRESERVED):
                return None  # fresh beets that will be sliced in the recipe, not preserved slices
        if ingredient_wants_preserved:
            if not any(ind in name_norm for ind in _BEET_PRESERVED):
                return None  # ingredient wants preserved beets, product is fresh

    # Explicit canned cherry tomatoes should not surface obvious fresh produce
    # offers just because the fresh item shares the same base tomato words.
    _CHERRY_TOMATO_KW = frozenset({
        'körsbärstomat', 'körsbärstomater',
        'korsbarstomat', 'korsbarstomater',
    })
    _CHERRY_TOMATO_PRESERVED_INGREDIENT = frozenset({
        'burk', 'konserv', 'konserverad', 'konserverade',
    })
    _CHERRY_TOMATO_FRESH_PRODUCT_CUES = frozenset({
        'klass', 'färsk', 'farsk',
        'fryst', 'frysta',
    })
    if matched_keyword in _CHERRY_TOMATO_KW:
        if any(ind in ingredient_lower for ind in _CHERRY_TOMATO_PRESERVED_INGREDIENT):
            name_norm = offer_data['name_normalized']
            if any(ind in name_norm for ind in _CHERRY_TOMATO_FRESH_PRODUCT_CUES):
                return None

    # STEP 1c2: Preserved chanterelle check.
    # "kantareller, på burk, avrunna" should only surface preserved chanterelle
    # products like "Kantareller i vatten", not fresh, dried, or creme variants.
    _CHANTERELLE_KW = frozenset({'kantarell', 'kantareller'})
    _CHANTERELLE_PRESERVED_INGREDIENT = frozenset({
        'burk', 'konserv', 'konserverad', 'konserverade',
        'avrunnen', 'avrunna',
    })
    _CHANTERELLE_PRESERVED_PRODUCT = frozenset({
        'burk', 'konserv', 'konserverad', 'konserverade',
        'vatten',
    })
    if matched_keyword in _CHANTERELLE_KW:
        if any(ind in ingredient_lower for ind in _CHANTERELLE_PRESERVED_INGREDIENT):
            name_norm = offer_data['name_normalized']
            if not any(ind in name_norm for ind in _CHANTERELLE_PRESERVED_PRODUCT):
                return None
        # Prep cues like "rengjorda"/"rensade" imply ordinary fresh chanterelles,
        # not canned/dried products.
        if any(ind in ingredient_lower for ind in ('rengjord', 'rengjorda', 'rensad', 'rensade')):
            name_norm = offer_data['name_normalized']
            if any(ind in name_norm for ind in (
                'torkad', 'torkade',
                'fryst', 'frysta',
                'burk', 'konserv', 'konserverad', 'konserverade',
                'vatten',
            )):
                return None

    if matched_keyword == 'kyckling' and _ingredient_implies_whole_kyckling(ingredient_lower):
        if 'hel' not in offer_data.get('specialty_qualifiers', {}).get('kyckling', set()):
            return None

    # Plain makrillfilé/-filéer should mean raw/fresh/frozen fish fillets, not
    # shelf-stable pantry fillets with sauces or prepared flavorings. Pantry
    # mackerel fillets stay available when the ingredient itself signals a
    # preserved/beredda form.
    _MAKRILL_FILLET_KW = frozenset({'makrillfileer', 'makrillfilé', 'makrillfile'})
    _MAKRILL_PRESERVED_INGREDIENT = frozenset({
        'burk', 'konserv', 'konserverad', 'konserverade',
        'tomatsås', 'tomatssås', 'sås', 'sas',
        'portugisisk', 'portugisiskt',
        'citrontimjan',
        'inlagd', 'inlagda',
        'marinerad', 'marinerade',
        'i olja', 'olja',
    })
    if matched_keyword in _MAKRILL_FILLET_KW:
        if offer_data.get('category') == 'pantry':
            if not any(ind in ingredient_lower for ind in _MAKRILL_PRESERVED_INGREDIENT):
                return None

    # Explicit preserved champignons should not surface fresh produce.
    # Ordinary champignon lines, including prep cues like "skivade", should stay
    # on fresh/frozen mushrooms and not fall through to preserved jar products.
    _CHAMPIGNON_KW = frozenset({'champinjon', 'champinjoner'})
    _CHAMPIGNON_PRESERVED_INGREDIENT = frozenset({
        'burk', 'konserv', 'konserverad', 'konserverade',
        'i vatten',
        'i lag',
    })
    _CHAMPIGNON_PRESERVED_PRODUCT = frozenset({
        'burk', 'konserv', 'konserverad', 'konserverade',
        'tetra',
        'vatten',
        'skivad', 'skivade',
        'hela',
        'inlagd', 'inlagda',
    })
    if matched_keyword in _CHAMPIGNON_KW:
        name_norm = offer_data['name_normalized']
        if any(ind in ingredient_lower for ind in _CHAMPIGNON_PRESERVED_INGREDIENT):
            if not any(ind in name_norm for ind in _CHAMPIGNON_PRESERVED_PRODUCT):
                return None
        else:
            if (
                'torkadsvamp' in offer_data.get('keywords', ())
                or any(ind in name_norm for ind in _CHAMPIGNON_PRESERVED_PRODUCT)
                or any(ind in name_norm for ind in ('torkad', 'torkade'))
            ):
                return None

    # "tandoori matlagningssås" should stay in the sauce/paste family and not
    # surface dry spice jars just because both share the same cuisine word.
    if matched_keyword == 'tandoori':
        if any(ind in ingredient_lower for ind in ('matlagningssås', 'matlagningssas', 'sås', 'sas')):
            if offer_data.get('category') == 'spices':
                return None

    # "Mandariner i fruktkonserver" means canned mandarin segments, not fresh
    # whole mandarins. Accept preserved segment products like "Mandarinklyftor i
    # sockerlag" and block fresh produce in this explicit preserved-fruit form.
    _MANDARIN_KW = frozenset({'mandarin', 'mandariner'})
    _MANDARIN_PRESERVED_INGREDIENT = frozenset({'fruktkonserver', 'fruktkonserv'})
    _MANDARIN_PRESERVED_PRODUCT = frozenset({
        'klyftor',
        'sockerlag',
        'juice',
        'burk',
        'konserv', 'konserverad', 'konserverade',
    })
    _MANDARIN_FRESH_PRODUCT_CUES = frozenset({'klass', 'färsk', 'farsk', 'fryst', 'frysta'})
    if matched_keyword in _MANDARIN_KW:
        if any(ind in ingredient_lower for ind in _MANDARIN_PRESERVED_INGREDIENT):
            name_norm = offer_data['name_normalized']
            if any(ind in name_norm for ind in _MANDARIN_FRESH_PRODUCT_CUES):
                return None
            if not any(ind in name_norm for ind in _MANDARIN_PRESERVED_PRODUCT):
                return None

    # Explicit fresh trumpet chanterelles should not collapse to canned, dried,
    # frozen, or generic yellow-chanterelle products.
    if matched_keyword == 'trattkantarell':
        name_norm = offer_data['name_normalized']
        if any(ind in ingredient_lower for ind in ('färsk', 'farsk', 'färska', 'farska')):
            if any(ind in name_norm for ind in (
                'torkad', 'torkade',
                'fryst', 'frysta',
                'burk', 'konserv', 'konserverad', 'konserverade',
                'vatten',
            )):
                return None

    if matched_keyword == 'svamp':
        name_norm = offer_data['name_normalized']
        if any(ind in ingredient_lower for ind in ('färsk', 'farsk', 'färska', 'farska')):
            if (
                'torkadsvamp' in offer_data.get('keywords', ())
                or any(ind in name_norm for ind in (
                    'torkad', 'torkade',
                    'vatten',
                    'burk',
                    'konserv', 'konserverad', 'konserverade',
                    'inlagd', 'inlagda',
                ))
            ):
                return None

    # "kålhuvud" should mean a whole fresh white-cabbage head, not red cabbage,
    # pointed cabbage, or pre-cut white cabbage products.
    if matched_keyword in {'vitkål', 'kålhuvud', 'kalhuvud'}:
        name_norm = offer_data['name_normalized']
        if any(ind in ingredient_lower for ind in ('kålhuvud', 'kalhuvud')):
            if any(ind in offer_data.get('keywords', ()) for ind in ('rödkål', 'rodkål', 'spetskål', 'spetskal')):
                return None
            if any(ind in name_norm for ind in ('strimlad', 'delad', 'fryst', 'frysta')):
                return None

    # "350 g (avrunnen vikt) ananas" is canned/drained pineapple, not fresh,
    # frozen, or dried fruit.
    _DRAINED_PINEAPPLE_PRODUCT_CUES = frozenset({
        'juice', 'krossad', 'krossade',
        'skivor', 'skiva',
        'ringar', 'ringar', 'ring',
        'bitar', 'bitar i',
    })
    _NON_CANNED_PINEAPPLE_CUES = frozenset({
        'fryst', 'frysta',
        'torkad', 'torkade',
        'klass', 'färsk', 'farsk',
        'smoothie',
    })
    if matched_keyword == 'ananas' and any(
        ind in ingredient_lower
        for ind in ('avrunnen', 'avrunna', 'fruktkonserver', 'fruktkonserv')
    ):
        name_norm = offer_data['name_normalized']
        if any(ind in name_norm for ind in _NON_CANNED_PINEAPPLE_CUES):
            return None
        if not any(ind in name_norm for ind in _DRAINED_PINEAPPLE_PRODUCT_CUES):
            return None

    # "Ananas Krossad" can reasonably fall back to frozen pineapple, but not
    # to plain fresh/whole pineapple products.
    _CRUSHED_PINEAPPLE_CUES = frozenset({
        'krossad', 'krossade',
        'finkrossad', 'finkrossade',
    })
    _FROZEN_PINEAPPLE_CUES = frozenset({'fryst', 'frysta'})
    _PRESERVED_PINEAPPLE_CUES = frozenset({
        'juice',
        'krossad', 'krossade',
        'finkrossad', 'finkrossade',
        'skivor', 'skiva',
        'ringar', 'ring',
        'fryst', 'frysta',
        'torkad', 'torkade',
        'smoothie',
    })
    if matched_keyword == 'ananas' and any(
        ind in ingredient_lower for ind in _CRUSHED_PINEAPPLE_CUES
    ):
        name_norm = offer_data['name_normalized']
        if not any(ind in name_norm for ind in _CRUSHED_PINEAPPLE_CUES | _FROZEN_PINEAPPLE_CUES):
            return None
    if matched_keyword == 'ananas' and any(
        ind in ingredient_lower for ind in ('färsk', 'farsk')
    ):
        name_norm = offer_data['name_normalized']
        if any(ind in name_norm for ind in _PRESERVED_PINEAPPLE_CUES):
            return None

    # STEP 1c3: Whole crayfish recipes map to frozen signalkräftor, not to
    # shelf-stable "i lag"/tail products.
    if not _whole_crayfish_product_allowed(offer_data['name_normalized'], ingredient_lower, matched_keyword):
        return None

    # "korvar, gärna lamm" should keep to sausage products. The optional lamb
    # note can allow lammkorv, but should not surface raw lamb cuts such as
    # lammracks or lammstek.
    if matched_keyword in {'lamm', 'lammkött', 'lammkott'}:
        if 'korv' in ingredient_lower or 'korvar' in ingredient_lower:
            product_keywords = set(keywords)
            sausage_like = (
                'korv' in product_keywords
                or any(kw.endswith('korv') for kw in product_keywords)
                or 'chorizo' in product_keywords
                or 'salsiccia' in product_keywords
            )
            if not sausage_like:
                return None

    # Explicit fresh-sausage lines should stay within fresh-sausage-like
    # families, not widen to every generic sausage product.
    _FRESH_SAUSAGE_INGREDIENT_CUES = (
        'färskkorv', 'farskkorv',
        'färskkorvar', 'farskkorvar',
        'färsk korv', 'farsk korv',
        'färska korvar', 'farska korvar',
    )
    if any(cue in ingredient_lower for cue in _FRESH_SAUSAGE_INGREDIENT_CUES):
        product_keywords = set(keywords)
        name_norm = offer_data['name_normalized']
        fresh_sausage_like = (
            'färskkorv' in product_keywords
            or 'farskkorv' in product_keywords
            or 'salsiccia' in product_keywords
            or 'chorizo' in product_keywords
            or 'färsk korv' in name_norm
            or 'farsk korv' in name_norm
        )
        if not fresh_sausage_like:
            return None

    # STEP 1d: Juice product check — if product is juice and keyword is citron/lime,
    # require ingredient to mention saft/juice/pressad (not whole fruit).
    # Exception: if ingredient mentions "skal" (zest), whole fruit is needed — block juice.
    if matched_keyword in JUICE_RULE_KEYWORDS:
        if offer_data['is_juice_product']:
            if 'skal' in ingredient_lower:
                return None  # "saft och skal" = needs whole fruit, not bottled juice
            if 'koncentrat' in offer_data['name_normalized'] and any(
                q in ingredient_lower for q in ('råpressad', 'rapressad', 'färskpressad', 'farskpressad')
            ):
                return None  # raw/fresh-pressed juice should not match concentrate products
            if 'koncentrat' in offer_data['name_normalized'] and any(
                cue in ingredient_lower for cue in _NON_CONCENTRATE_INGREDIENT_CUES
            ):
                return None
            if not any(ind in ingredient_lower for ind in JUICE_INGREDIENT_INDICATORS):
                return None

    # STEP 2: Context-required words check (using pre-computed set)
    # If offer contains "köttbullar", ingredient must too
    #
    # Special case: when the matched keyword is ITSELF a context-required word
    # (e.g., "burrata" or "mozzarella"), skip other context words that are also
    # keywords. This lets "Burrata Mozzarella" match either "burrata" OR "mozzarella"
    # recipes. But "Riven Ost Mozzarella" matched on "ost" (not a context word)
    # still requires "mozzarella" in the ingredient.
    context_words = offer_data['context_words']
    if context_words:
        matched_is_context = matched_keyword in context_words
        offer_keywords_set = set(keywords) if matched_is_context else None
        offer_text_for_context = f"{offer_data.get('name_normalized', '')} {' '.join(keywords)}"
        # Per-keyword exemptions: e.g., 'hamburgare' exempts 'burgare' context
        # but 'grillost' in the same product still requires 'burgare'
        kw_exemptions = CONTEXT_WORD_KEYWORD_EXEMPTIONS.get(matched_keyword, _EMPTY_FROZENSET)
        for context_word in context_words:
            if matched_is_context and context_word in offer_keywords_set:
                continue
            if context_word in kw_exemptions:
                continue
            if not _ingredient_satisfies_context_word(context_word, ingredient_lower, offer_text_for_context):
                return None

    # STEP 2b: Ingredient carrier restriction
    # When ingredient contains a carrier from CARRIER_CONTEXT_REQUIRED (e.g., 'pastasas')
    # and the matched keyword is NOT the carrier itself, the product name must also
    # contain the carrier. Prevents "Kvisttomater" from matching "pastasås tomat".
    if matched_keyword not in CARRIER_CONTEXT_REQUIRED:
        name_norm = offer_data.get('name_normalized', '')
        for _cc in CARRIER_CONTEXT_REQUIRED:
            if _cc in ingredient_lower and _cc not in name_norm:
                if _cc in {'pålägg', 'palagg'} and matched_keyword in _PALAGG_DELI_KEYWORD_EXEMPTIONS:
                    continue
                # 'eller' alternative: "tomatsås eller pinsasås" — the carrier is in
                # a different alternative segment than the matched keyword → not a
                # compound requirement, skip restriction.
                if 'eller' in ingredient_lower:
                    _segs = ingredient_lower.split(' eller ')
                    _cc_seg = next((s for s in _segs if _cc in s), None)
                    _kw_seg = next((s for s in _segs if matched_keyword in s), None)
                    if _cc_seg is not None and _kw_seg is not None and _cc_seg != _kw_seg:
                        continue
                return None

    # STEP 2c: Carrier-flavor specificity check
    # When ingredient has a carrier (e.g., 'pastasas') AND flavor words alongside it,
    # a product matching on ONLY the carrier keyword must also have at least one of
    # the ingredient's flavor words as a keyword.
    # "pastasås basilika" ingredient + product with only 'pastasas' → BLOCKED
    # "pastasås basilika" ingredient + product with 'pastasas'+'basilika' → ALLOWED
    # "pastasås" ingredient (generic, no flavor) → all pastasåser match
    if matched_keyword in CARRIER_CONTEXT_REQUIRED:
        offer_kw_set = set(keywords)
        product_name_norm = offer_data.get('name_normalized', '')
        # Find flavor words in ingredient that aren't the carrier itself
        ing_words = ingredient_lower.split()
        ing_flavors = [w for w in ing_words
                       if (len(w) >= 4 or w in IMPORTANT_SHORT_KEYWORDS)
                       and w in FLAVOR_WORDS
                       and w not in CARRIER_CONTEXT_REQUIRED]
        if ing_flavors and 'eller' in ingredient_lower:
            # "tomatsås eller pinsasås" — flavor words from a different 'eller' segment
            # are alternatives, not flavor modifiers. Only keep flavor words from the
            # segment that also contains the matched carrier.
            segments = ingredient_lower.split(' eller ')
            carrier_segment = next((s for s in segments if matched_keyword in s), None)
            if carrier_segment is not None:
                ing_flavors = [f for f in ing_flavors if f in carrier_segment]
        if ing_flavors:
            # Ingredient has carrier + flavor → product must have at least one flavor
            if not any(f in offer_kw_set or f in product_name_norm for f in ing_flavors):
                return None

    # STEP 2d: Inverse context check
    # If the ingredient contains a qualifying word like "kryddmix" and the
    # match is on a different keyword, the product must also contain that word.
    if matched_keyword:
        if matched_keyword == 'pasta' and _ingredient_requests_long_pasta(ingredient_lower):
            if any(kw in keywords for kw in ('långpasta', 'langpasta')):
                matched_keyword = 'långpasta'
            else:
                return None
        if matched_keyword == 'rom':
            product_is_roe = _offer_is_roe_family(keywords)
            requested_roe_family = _ingredient_requested_specific_roe_family(ingredient_lower)
            if requested_roe_family and not _product_matches_roe_family(keywords, requested_roe_family):
                return None
            ingredient_wants_spirit = _ingredient_wants_spirit_rom(ingredient_lower)
            if ingredient_wants_spirit and product_is_roe:
                return None
            if not ingredient_wants_spirit and not product_is_roe:
                return None
        if matched_keyword in {'jäst', 'matbrödsjäst'} and _ingredient_requests_generic_bread_yeast(ingredient_lower):
            if any(cue in offer_data['name_normalized'] for cue in ('söta degar', 'sota degar', 'söt deg', 'sot deg')):
                return None
        if (
            matched_keyword == 'lingondryck'
            and 'koncentrat' in offer_data['name_normalized']
            and any(cue in ingredient_lower for cue in _NON_CONCENTRATE_INGREDIENT_CUES)
        ):
            return None
        if (
            matched_keyword == 'chilipasta'
            and 'gochujang' in ingredient_lower
            and 'gochujang' not in keywords
            and 'gochujang' not in offer_data['name_normalized']
        ):
            return None
        if not _ready_packaged_chickpea_allows_product(
            offer_data.get('name_normalized', ''),
            ingredient_lower,
            matched_keyword,
        ):
            return None
        if not _ready_packaged_lentil_allows_product(
            offer_data.get('name_normalized', ''),
            ingredient_lower,
            matched_keyword,
        ):
            return None
        if not _riven_cheddar_allows_product(
            offer_data.get('name_normalized', ''),
            ingredient_lower,
            matched_keyword,
        ):
            return None
        ingredient_context_missing = offer_data.get('ingredient_context_missing', _EMPTY_FROZENSET)
        for req_word in INGREDIENT_REQUIRES_IN_PRODUCT:
            if req_word in ingredient_lower and matched_keyword != req_word:
                if req_word in ingredient_context_missing:
                    return None

    # STEP 2d: Inverse context check — MOVED to per-ingredient validation
    # in recipe_matcher.py to avoid cross-ingredient contamination.
    # E.g., "kryddmix" from "shichimi togarashi kryddmix" ingredient was
    # blocking ALL other products (ryggbiff, olivolja, etc.) from matching.

    # STEP 3: Secondary ingredient patterns check
    # NOT done here — handled per-ingredient in recipe_matcher.py
    # to avoid cross-ingredient contamination (e.g., "ost" from cheese
    # ingredient blocking all "Pasta ..." products).

    # STEP 4: Specialty qualifier check
    # Direction A: skipped here and handled per ingredient in recipe_matcher.py
    # to avoid cross-ingredient contamination.
    # E.g., "gul" from "gul lök" falsely requiring "Paprika Burk" to have "gul".
    #
    # Direction B: if PRODUCT has a BIDIRECTIONAL qualifier, ingredient must have it
    #   e.g., product "Soltorkade Tomater" → ingredient must mention "soltorkade"
    # Non-bidirectional product qualifiers (e.g., "gul" in "Gul Lök") do NOT block:
    #   "Gul Lök" should still match generic "lök" recipes.
    specialty_keyword = _SPECIALTY_KEYWORD_ALIASES.get(matched_keyword, matched_keyword)
    offer_qualifiers = offer_data['specialty_qualifiers'].get(specialty_keyword, set())

    if (
        specialty_keyword == 'chilisås'
        and any(qual in ingredient_lower for qual in _SWEET_CHILI_QUALIFIERS)
        and any(qual in offer_qualifiers for qual in _UNSWEETENED_CHILI_QUALIFIERS)
    ):
        return None

    # Direction B: bidirectional qualifiers on product must be in ingredient
    if offer_qualifiers:
        per_kw_bidir = BIDIRECTIONAL_PER_KEYWORD.get(specialty_keyword, _EMPTY_FROZENSET)
        generic_matches_all = {'choklad', 'bakchoklad', 'blockchoklad'}
        ingredient_has_qualifier = any(
            q in ingredient_lower for q in SPECIALTY_QUALIFIERS.get(specialty_keyword, ())
        )
        for q in offer_qualifiers:
            if q in BIDIRECTIONAL_SPECIALTY_QUALIFIERS or q in per_kw_bidir:
                if (
                    not ingredient_has_qualifier
                    and q not in BIDIRECTIONAL_SPECIALTY_QUALIFIERS
                    and specialty_keyword in generic_matches_all
                ):
                    continue
                if (
                    specialty_keyword == 'kyckling'
                    and q == 'hel'
                    and _ingredient_implies_whole_kyckling(ingredient_lower)
                ):
                    continue
                equivalents = QUALIFIER_EQUIVALENTS.get(q, {q})
                if not any(eq in ingredient_lower for eq in equivalents):
                    return None

    # STEP 5: Processed product check (product-side pre-computed)
    # Run all relevant product-side checks, not just the matched keyword.
    # This keeps fast-path behavior aligned with the full per-ingredient validator
    # when a preserved/specialized product reaches the recipe through a broader
    # fallback keyword (e.g. champinjoner -> svamp).
    processed_checks = offer_data['processed_checks']
    if processed_checks:
        _SPICE_AMOUNT_IMPLICIT_GROUND = frozenset({
            'ingefära', 'ingefara',
            'gurkmeja', 'kurkuma',
            'paprika',
        })
        _GROUND_PRODUCT_INDICATORS = frozenset({'malen', 'malna', 'mald', 'malet', 'pulver', 'torkad', 'torkade'})
        _FRESH_INDICATORS_SVF = frozenset({'färsk', 'farsk', 'riven', 'hackad', 'pressad'})
        for check in processed_checks:
            if check[1] == 'strict':
                if not any(ind in ingredient_lower for ind in check[2]):
                    # Spice-amount heuristic: "1 tsk ingefära" = ground/dried
                    if (check[0] in _SPICE_AMOUNT_IMPLICIT_GROUND
                            and any(ind in _GROUND_PRODUCT_INDICATORS for ind in check[2])
                            and not any(fi in ingredient_lower for fi in _FRESH_INDICATORS_SVF)
                            and _RE_SPICE_AMOUNT.search(ingredient_lower)):
                        continue  # Allow: spice amount implies ground/dried
                    return None
            else:
                if check[2] not in ingredient_lower:
                    if not any(ind in ingredient_lower for ind in check[3]):
                        return None

    # STEP 6: Spice vs Fresh vegetable check
    # Apply the product-side rules precomputed for this offer. RecipeMatcher also
    # validates these per ingredient, but matches_ingredient_fast() is a public
    # direct path in tests and tooling, so it must not allow jarred/spice products
    # such as "Vitlök Finhackad" to match fresh ingredient lines.
    if not _passes_precomputed_spice_fresh_rule(offer_data, ingredient_lower, matched_keyword):
        return None

    # STEP 7: Herb/spice form mismatch check (färsk↔torkad↔fryst)
    # Uses unified indicator sets. Fast-path: combined ingredient_lower text.
    # Per-ingredient refinement happens in recipe_matcher.py.
    if matched_keyword in FRESH_HERB_KEYWORDS:
        product_name = offer_data['name_normalized']
        prod_is_fresh = any(ind in product_name for ind in FRESH_PRODUCT_INDICATORS)
        prod_is_dried = any(ind in product_name for ind in DRIED_PRODUCT_INDICATORS)
        prod_is_frozen = any(ind in product_name for ind in FROZEN_PRODUCT_INDICATORS)
        # For herbs: default to DRIED if no indicator present.
        # Fresh herbs always have explicit indicators (kruka/bunt/kvist/färsk)
        # or are heavy (whole roots: ingefära 100g+, gurkmeja 100g+).
        if not prod_is_fresh and not prod_is_dried and not prod_is_frozen:
            w = offer_data.get('weight_grams')
            if w and w > 80:
                prod_is_fresh = True   # heavy without indicator = fresh root/bunch
            else:
                prod_is_dried = True   # light or no weight without indicator = dried jar
        recipe_wants_fresh = (
            any(fi in ingredient_lower for fi in RECIPE_FRESH_INDICATORS)
            or any(vi in ingredient_lower for vi in RECIPE_FRESH_VOLUME_INDICATORS)
        )
        recipe_wants_dried = any(di in ingredient_lower for di in RECIPE_DRIED_INDICATORS)
        recipe_wants_frozen = any(zi in ingredient_lower for zi in RECIPE_FROZEN_INDICATORS)
        _fresh_prep_cues = (
            'finskuren', 'finskurna',
            'fint skuren', 'fint skurna',
            'finhackad', 'finhackade',
            'hackad', 'hackade',
            'klippt', 'klippta',
        )
        if any(cue in ingredient_lower for cue in _fresh_prep_cues):
            recipe_wants_fresh = True
        if (
            matched_keyword in {'chili', 'chilipeppar', 'chilifrukt', 'chilifrukter'}
            and _RE_CHILI_COUNT_FRESH.search(ingredient_lower)
        ):
            recipe_wants_fresh = True
        # For herbs: "1 tsk oregano" / "2 krm timjan" = small spice measurements = wants dried
        if not recipe_wants_fresh and not recipe_wants_dried:
            if any(m in ingredient_lower for m in ('tsk ', 'krm ', ' tsk ', ' krm ')):
                recipe_wants_dried = True
        # Only block on clear single-direction mismatches.
        # If recipe text has BOTH "färsk" and "torkad" (two ingredients),
        # skip — per-ingredient check in recipe_matcher handles it.
        recipe_form_count = sum([recipe_wants_fresh, recipe_wants_dried, recipe_wants_frozen])
        if recipe_form_count == 1:
            # Frozen herbs ≈ fresh herbs (just frozen). Compatible with "färsk".
            if prod_is_frozen:
                # Block only if recipe wants dried
                if recipe_wants_dried:
                    return None
            elif prod_is_dried and not prod_is_fresh:
                # Dried — block if recipe wants fresh/frozen
                if recipe_wants_fresh or recipe_wants_frozen:
                    return None
            elif prod_is_fresh and not prod_is_dried:
                # Fresh — block only if recipe wants dried
                if recipe_wants_dried:
                    return None
        # recipe_form_count == 0: no remaining qualifier in the fast-path text.
        # Do NOT apply the plain-herb default here. RecipeMatcher re-checks herb
        # form per ingredient using the original source text, while the fast-path
        # input may already have stripped instruction tails such as
        # ", till garnering" / ", till servering". Blocking fresh herbs here
        # makes cached matching narrower than uncached matching for those lines.
        #
        # Keep the fast path focused on explicit one-way mismatches only; let the
        # later per-ingredient pass decide whether a plain herb line really means
        # dried or fresh.

    # STEP 8: Fresh vs Processed check
    # NOTE: Skipped here — handled per-ingredient in recipe_matcher.py
    # to avoid cross-ingredient contamination. E.g., "färsk" from
    # "färsk basilika" would block "Krossade Tomater" for a different ingredient.
    #
    # Narrow single-ingredient mirror for asparagus pieces:
    # explicit "färsk/färska sparris" should not match products like
    # "Sparris Bitar", but generic "sparris" may still do so.
    if matched_keyword == 'sparris' and 'bitar' in offer_data['name_normalized']:
        if any(
            phrase in ingredient_lower for phrase in (
                'färsk sparris', 'farsk sparris',
                'färska sparris', 'farska sparris',
                'sparris färsk', 'sparris farsk',
                'sparris färska', 'sparris farska',
            )
        ):
            return None

    # Explicit frozen spinach should not degrade to fresh spinach products.
    # Keep this asymmetric: plain/fresh spinach may still accept frozen fallback,
    # but "fryst spenat" should require an actually frozen product.
    _SPINACH_KEYWORDS = frozenset({'spenat', 'babyspenat', 'bladspenat'})
    if (
        matched_keyword in _SPINACH_KEYWORDS
        and any(fi in ingredient_lower for fi in RECIPE_FROZEN_INDICATORS)
        and not any(fi in offer_data['name_normalized'] for fi in FROZEN_PRODUCT_INDICATORS)
    ):
        return None

    # Generic frozen-fish wording should use ordinary frozen fish fillets as
    # store fallback, but still require the product itself to actually be frozen.
    if (
        matched_keyword == 'fiskfilé'
        and _ingredient_requests_generic_frozen_fish_fillet(ingredient_lower)
        and not any(fi in offer_data['name_normalized'] for fi in FROZEN_PRODUCT_INDICATORS)
    ):
        return None

    # Narrow single-ingredient mirror for fennel spice vs fresh fennel:
    # keep "Fänkål Krydda"/seed-style ingredients separate from fresh fennel bulbs.
    if matched_keyword == 'fänkål':
        name_norm = offer_data['name_normalized']
        wants_fennel_spice = _ingredient_wants_fennel_spice(ingredient_lower)
        is_fresh_fennel_product = 'klass' in name_norm
        is_fennel_spice_product = any(
            ind in name_norm for ind in (
                'fänkålsfrö', 'fankalsfro', 'fänkålsfrön', 'fankalsfron',
                'malen', 'hel',
            )
        )
        if wants_fennel_spice and is_fresh_fennel_product:
            return None
        if not wants_fennel_spice and is_fennel_spice_product:
            return None

    if (
        matched_keyword == 'kycklingklubba'
        and _ingredient_wants_cooked_kycklingklubba(ingredient_lower)
        and not _product_has_cooked_kyckling_cue(name_norm)
    ):
        return None

    # "hel kalkon" should only match whole-turkey products, not generic deli or
    # cut turkey items that still carry the base keyword "kalkon".
    if matched_keyword == 'kalkon':
        if 'helkalkon' in ingredient_lower:
            return None

    # Generic poultry-cut matches should not override an explicit bird species
    # in the same ingredient line. "bröstfilé av kyckling" should not surface
    # turkey breast fillet, and vice versa.
    _GENERIC_POULTRY_CUT_MATCHES = frozenset({
        'filé', 'file', 'fil',
        'bröst', 'brost',
        'bröstfil', 'bröstfilé', 'brostfil', 'brostfile',
        'lårfil', 'lårfilé', 'larfil', 'larfile',
    })
    if matched_keyword in _GENERIC_POULTRY_CUT_MATCHES:
        offer_keywords_set = set(offer_data.get('keywords', ()))
        ingredient_wants_kyckling = 'kyckling' in ingredient_lower and 'kalkon' not in ingredient_lower
        ingredient_wants_kalkon = 'kalkon' in ingredient_lower and 'kyckling' not in ingredient_lower
        if ingredient_wants_kyckling and 'kalkon' in offer_keywords_set:
            return None
        if ingredient_wants_kalkon and 'kyckling' in offer_keywords_set:
            return None

    return matched_keyword
