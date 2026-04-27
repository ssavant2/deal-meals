"""Keyword extraction helpers for Swedish ingredient matching.

Related data:
- extraction_patterns.py — regex helpers and keyword-length thresholds
- carrier_context.py — carrier products and context-stripping behavior
- match_filters.py — product-name substitutions used during extraction
"""

import re
from typing import Dict, FrozenSet, List, Optional

try:
    from languages.sv.normalization import normalize_ingredient, fix_swedish_chars
except ModuleNotFoundError:
    from app.languages.sv.normalization import normalize_ingredient, fix_swedish_chars

from .keywords import (
    STOP_WORDS,
    PROCESSED_FOOD_SUFFIXES,
    PROCESSED_FOODS_EXEMPTIONS,
    FLAVOR_WORDS,
    COOKING_FLAVORS,
    IMPLICIT_KEYWORDS,
    IMPORTANT_SHORT_KEYWORDS,
    OFFER_EXTRA_KEYWORDS,
)
from .synonyms import INGREDIENT_PARENTS, KEYWORD_SYNONYMS
from .recipe_text import (
    is_subrecipe_reference_text,
    preserve_cheese_preference_parentheticals,
    preserve_fresh_pasta_parenthetical,
    preserve_parenthetical_chili_alias,
    preserve_parenthetical_grouped_herb_leaves,
    preserve_non_concentrate_parenthetical,
    preserve_parenthetical_shiso_alternatives,
    rewrite_buljong_eller_fond,
    rewrite_mince_of_alternatives,
    rewrite_truncated_eller_compounds,
)
from .normalization import (
    _apply_space_normalizations,
    normalize_measured_durumvete_flour,
    normalize_measured_risotto_rice,
)
from .compound_text import (
    _COMPOUND_WORD_INDEX,
    COMPOUND_BASE_KEYWORDS,
    _NON_FOOD_PATTERN,
    _PROCESSED_FOODS_PATTERN,
)
from .carrier_context import (
    _CARRIER_MULTI_WORDS,
    _CARRIER_SINGLE_WORDS,
    _CARRIER_SUFFIX_CANDIDATES,
    _FLAVOR_DOMINANT_CARRIERS,
)
from .dairy_types import ALLOWED_YOGURT_TYPES
from .form_rules import NON_FOOD_CATEGORIES
from .parent_maps import KEYWORD_EXTRA_PARENTS
from .match_filters import PRODUCT_NAME_SUBSTITUTIONS
from .extraction_patterns import (
    MIN_KEYWORD_LENGTH,
    MIN_KEYWORD_LENGTH_STRICT,
    _SKIP_IF_FLAVORED_PATTERN,
    _BABY_FOOD_PATTERN,
    _PUNCTUATION_PATTERN,
    _WHITESPACE_PATTERN,
    _PORTION_PATTERN,
    _NUMBERS_PATTERN,
    _MEASUREMENTS_PATTERN,
    _PUNCT_SPLIT_PATTERN,
)

# Keywords that are too generic on their own — products where this is the ONLY
# keyword get blocked. Requires at least one other qualifying keyword.
# Example: "Kryddmix Classic" → ['kryddmix'] → blocked (classic filtered as too short)
#          "Kryddmix Fajita" → ['kryddmix', 'fajita'] → allowed
SOLO_KEYWORD_BLOCK: FrozenSet[str] = frozenset({
    'kryddmix',  # too generic alone — must have a type qualifier (fajita, tandoori, etc.)
    # NOTE: 'sylt' removed — promotion logic merges it with 'jordgubbssylt' etc.
    #        when they match the same ingredient line, so no UI duplication
    # Bare noodle carriers: instant noodles with flavor stripped → only 'nudlar' left.
    # Real cooking noodles have specific type keywords (udonnudlar, risnudlar, etc.)
    'nudlar', 'noodles', 'noodle',
})

_SHORT_PASTA_CARRIERS: FrozenSet[str] = frozenset({
    'fusilli', 'penne', 'rigatoni', 'farfalle',
    'conchiglie', 'conchigle', 'gemelli', 'radiatori',
    'tortiglioni', 'caserecce', 'girandole',
    'strozzapreti', 'strozzapretti', 'mafalda',
    'maniche', 'ziti',
})

_WHITE_FISH_FAMILY_KEYWORDS: FrozenSet[str] = frozenset({
    'torsk', 'kolja', 'sej',
    'rödspätta', 'rodspatta',
    'vitling', 'kummel',
    'stillahavstorsk',
    'pangasiusmal', 'havskatt',
    'torskfilé', 'torskfile', 'torskrygg',
    'koljafilé', 'koljafile',
    'sejfilé', 'sejfile',
    'rödspättafilé', 'rodspattafile',
    'vitlingfilé',
    'pangasiusmalfilé', 'havskattfilé',
})

_WHITE_FISH_FILLET_MARKERS: FrozenSet[str] = frozenset({
    'filé', 'file',
    'ryggfilé', 'ryggfile', 'rygg',
})


def is_non_food_product(product_name: str, category: Optional[str] = None) -> bool:
    """
    Check if a product is non-food (hygiene, cleaning, etc).

    Args:
        product_name: The product name to check
        category: Optional category from database

    Returns:
        True if product is non-food

    Example:
        >>> is_non_food_product("Nappy Care Cream Zinksalva")
        True
        >>> is_non_food_product("Kokosmjölk Extra Creamy")
        False
    """
    # Check category first (fastest)
    if category and category.lower() in NON_FOOD_CATEGORIES:
        return True

    # Normalize Swedish characters (tvattmedel → tvättmedel)
    name_normalized = fix_swedish_chars(product_name).lower()

    # Check against non-food keywords using pre-compiled combined pattern
    # This is ~50x faster than looping through each keyword
    if _NON_FOOD_PATTERN and _NON_FOOD_PATTERN.search(name_normalized):
        return True

    return False


# Brand-based product name completions.
# Some stores strip the product type from the name (e.g., Willys strips
# "Färskost" from Philadelphia products). This dict maps brand names to
# the product type word that should be prepended if missing from the name.
_BRAND_NAME_COMPLETIONS: Dict[str, str] = {
    'philadelphia': 'färskost',
}


def extract_keywords_from_product(
    product_name: str,
    category: Optional[str] = None,
    min_length: int = MIN_KEYWORD_LENGTH,
    brand: Optional[str] = None
) -> List[str]:
    """
    Extract searchable keywords from a product/offer name.

    More permissive than ingredient extraction (allows shorter words).

    Args:
        product_name: The product name
        category: Optional category (for filtering)
        min_length: Minimum keyword length
        brand: Optional brand name (for completing stripped product names)

    Returns:
        List of keywords suitable for matching

    Example:
        >>> extract_keywords_from_product("Vispgrädde Laktosfri 40%")
        ['vispgrädde', 'laktosfri']
    """
    # Save original name before any brand manipulation (used for carrier detection later)
    pre_strip_name = product_name

    # Brand-based name completion: some stores strip product type from name
    if brand:
        brand_lower = brand.lower()
        completion = _BRAND_NAME_COMPLETIONS.get(brand_lower)
        if completion and completion not in product_name.lower():
            product_name = f"{completion} {product_name}"

        # Block ice cream brands — carrier detection may pick a non-glass carrier
        # (e.g. "kaka" from "kladdkaka") before "glass", bypassing glass normalization.
        # Must check BEFORE brand stripping, since stripping removes "Glass" from the name.
        _GLASS_BRANDS = frozenset({'triumf glass', 'sia glass', 'lejonet & björnen',
                                    'lejonet och björnen', 'järnaglass', '3 vänners glass'})
        if brand_lower in _GLASS_BRANDS:
            # Delegate to full glass normalization by ensuring "glass" stays in name
            # and is detected as carrier. We do this by returning [] for non-base-flavor
            # products, and letting properly-detected glass products through normally.
            # Quick check: is this a recognized base-flavor glass?
            _name_low = product_name.lower()
            _QUICK_GLASS_FLAVORS = {'vanilj', 'jordgubb', 'hallon', 'blåbär', 'mango',
                                     'päron', 'citron', 'lakrits', 'kanel', 'pistage',
                                     'kaffe', 'nougat', 'choklad', 'smultron'}
            _has_base_flavor = any(f in _name_low for f in _QUICK_GLASS_FLAVORS)
            _QUICK_EXOTIC = {'brynt', 'kladdkaka', 'oreo', 'daim', 'snickers', 'twix',
                              'cookie', 'fudge', 'caramel', 'karamell', 'toffee', 'kola',
                              'popcorn', 'cheesecake', 'brownie', 'saltkola', 'saltlakrits'}
            _has_exotic = any(e in _name_low for e in _QUICK_EXOTIC)
            if _has_exotic or not _has_base_flavor:
                return []
            # Base-flavor glass from glass brand — let through for normal glass normalization

        # Block drink/non-food brands entirely — these products should never match recipes.
        # Must check BEFORE brand stripping, since stripping removes the brand evidence.
        _DRINK_BRANDS = frozenset({'jarritos', 'sodastream', 'nocco', 'celsius', 'lohilo',
                                    'joluca', 'festis', 'zeroh', 'zeroh!', 'fun light',
                                    'bravo', 'bob', 'proviva', 'sprite', 'pepsi',
                                    'coca-cola', 'fanta', 'trocadero', 'zingo',
                                    'kopparbergs', 'somersby', 'mixtales'})
        if brand_lower == 'mixtales':
            _mixtales_name = product_name.lower()
            # Grenadine is a real cocktail ingredient, not just a flavored drink.
            # Keep the exception narrow so other Mixtales drink mixes stay blocked.
            if re.search(r'\bgrenadine\b', _mixtales_name):
                return ['grenadine']
        if brand_lower in _DRINK_BRANDS:
            return []

        # Strip brand name from product name to prevent brand words leaking as keywords.
        # "Majonnäs QP Japan 355ml Kewpie" with brand "KEWPIE" → strip "Kewpie" from name
        # so compound splitting doesn't produce false keywords like "pie" from "Kewpie".
        # Uses word boundary \b to avoid stripping brand substrings from food words.
        #
        # Keep the original name if brand stripping removes the only extractable food
        # identity. The old "3+ letter words remain" heuristic was too weak for
        # products like "Fiberhusk Glutenfri 300g Husk": stripping the brand leaves
        # generic residue words, but no real matcher keyword. Check the stripped name
        # with brand-less extraction and only keep it if it still yields keywords.
        import re as _re
        brand_pattern = _re.compile(r'\b' + _re.escape(brand_lower) + r'\b', _re.IGNORECASE)
        stripped_name = brand_pattern.sub('', product_name).strip()
        if stripped_name and stripped_name != product_name:
            stripped_keywords = extract_keywords_from_product(
                stripped_name,
                category,
                min_length=min_length,
                brand=None,
            )
            if stripped_keywords:
                product_name = stripped_name

    # Filter out non-food products
    if is_non_food_product(product_name, category):
        return []

    # Use ORIGINAL name (lowercased, BEFORE brand stripping) for carrier/yogurt detection.
    # Brand stripping removes e.g. "SIA Glass" / "Triumf Glass", which deletes the "glass"
    # carrier word and breaks ice cream normalization. Use pre_strip_name instead.
    original_name_lower = fix_swedish_chars(pre_strip_name).lower()

    # Exact cocktail-ingredient exception: "Drinkmix Grenadine" is the real
    # cooking/drink ingredient grenadine, not just a flavored beverage.
    # Keep this narrow so other drink mixes stay blocked by the processed-food
    # and drink-brand paths below.
    if 'drinkmix' in original_name_lower and re.search(r'\bgrenadine\b', original_name_lower):
        return ['grenadine']

    # Cooking recipes occasionally call for porter specifically. Keep that beer
    # family searchable as an exact ingredient without opening generic beer or
    # other beverage matching.
    if (category or '').lower() == 'beverages' and re.search(r'\bporter\b', original_name_lower):
        return ['porter']

    # Specific savory spread/dip products should keep their own identity instead
    # of collapsing into the raw ingredient family. This keeps "Creme av
    # soltorkade tomater" distinct from plain jars of sun-dried tomatoes.
    _sun_dried_tomato_creme = (
        any(token in original_name_lower for token in ('creme', 'crème', 'kräm', 'kram'))
        and ('soltorkad tomat' in original_name_lower or 'soltorkade tomater' in original_name_lower)
    )
    if _sun_dried_tomato_creme:
        return ['soltorkadetomatcreme']

    # Candied/pickled ginger should keep its own exact family instead of being
    # treated as fresh ginger root.
    if (
        'ingefära' in original_name_lower or 'ingefara' in original_name_lower
    ) and any(token in original_name_lower for token in (
        'syltad', 'picklad', 'gari', 'sushi',
    )):
        return ['syltadingefära']

    # Trumpet chanterelles are a distinct mushroom family in recipes. Keep the
    # exact species visible instead of collapsing immediately into generic
    # chanterelles.
    if 'trattkantarell' in original_name_lower:
        keywords = ['trattkantarell', 'kantareller']
        if 'torkad' in original_name_lower or 'torkade' in original_name_lower:
            keywords.append('torkadsvamp')
        return keywords

    # Salt-cured pork for Pitepalt-style recipes should keep its own exact
    # family instead of degrading to plain fresh pork cuts.
    if (
        ('rimmad' in original_name_lower or 'rimmat' in original_name_lower)
        and any(token in original_name_lower for token in (
            'stekfläsk', 'stekflask',
            'sidfläsk', 'sidflask',
            'fläsklägg', 'flasklagg', 'fläsklagg',
        ))
    ):
        product_keywords = ['rimmatfläsk']
        if 'stekfläsk' in original_name_lower or 'stekflask' in original_name_lower:
            product_keywords.append('stekfläsk')
        if 'sidfläsk' in original_name_lower or 'sidflask' in original_name_lower:
            product_keywords.append('sidfläsk')
        if any(token in original_name_lower for token in ('fläsklägg', 'flasklagg', 'fläsklagg')):
            product_keywords.append('fläsklägg')
        return product_keywords

    # Explicit candy ingredient: keep chocolate eggs as their own exact family
    # instead of treating them as generic candy or plain chocolate.
    if 'chokladägg' in original_name_lower or 'chokladagg' in original_name_lower:
        return ['chokladägg']

    # Dessert-sauce exact ingredient: keep vanilla sauce visible instead of
    # treating it as a generic processed sauce or dairy flavor descriptor.
    if 'vaniljsås' in original_name_lower or 'vaniljsas' in original_name_lower:
        return ['vaniljsås']

    # Plain sea-salt products are real pantry ingredients. Keep them searchable
    # as `havssalt`, while herb salts and crackers that merely mention sea salt
    # stay outside the family.
    if (
        re.search(r'\b(?:havssalt|sea salt)\b', original_name_lower)
        and (category or '').lower() in {'spices', 'pantry'}
        and not any(token in original_name_lower for token in (
            'herbamare', 'örtsalt', 'ortsalt',
            'knäcke', 'knacke', 'knackebrod',
        ))
    ):
        return ['havssalt']

    # Yeast for bread is a specific product family and should not collapse to
    # generic yeast or the sweet-dough yeast line.
    if re.search(
        r'\b(?:jäst\s+för\s+matbröd|jast\s+for\s+matbrod|torrjäst(?:\s+för)?\s+matbröd|torrjast(?:\s+for)?\s+matbrod|matbrödsjäst|matbrodsjast)\b',
        original_name_lower,
    ):
        return ['matbrödsjäst']

    # Bao / steam buns are a buyable bread family of their own and should not
    # disappear into generic bread matching.
    if re.search(r'\b(?:steam\s+buns|bao\s+buns?|steambuns)\b', original_name_lower):
        return ['steambuns']

    # Wheat sourdough starter wording in recipes should accept starter products,
    # but not finished sourdough bread that merely mentions vetesurdeg.
    if 'surdegsstart' in original_name_lower and 'vete' in original_name_lower:
        return ['vetesurdegsgrund']

    # Oat-based cooking bases are sold under "matlagningsbas" branding but are
    # functionally the same family as oat cooking cream in recipes.
    if 'matlagningsbas' in original_name_lower and 'havre' in original_name_lower:
        return ['matlagningsbas', 'havregrädde', 'grädde']

    # Qualified wheat flour should stay at the requested level instead of
    # collapsing into plain wheat flour.
    if 'vetemjöl' in original_name_lower:
        flour_keywords = []
        if 'special' in original_name_lower:
            flour_keywords.append('vetemjölspecial')
        if 'fullkorn' in original_name_lower:
            flour_keywords.append('vetemjölfullkorn')
        if flour_keywords:
            return flour_keywords

    # Flavor-specific compound yoghurts should keep their own exact identity
    # instead of degrading to plain yoghurt or substring collisions like mayo.
    if (
        ('yoghurt' in original_name_lower or 'yogurt' in original_name_lower or 'gurt' in original_name_lower)
        and ('kardemumma' in original_name_lower or 'kardemuma' in original_name_lower)
    ):
        return ['kardemummayoghurt']

    # Soy mayo products should stay in their own condiment family instead of
    # degrading into separate soy-sauce/plain-mayo paths.
    if (
        'soja' in original_name_lower
        and any(token in original_name_lower for token in ('majonnäs', 'majonnas', 'mayo'))
    ):
        return ['sojamajonnäs']

    # Sriracha-mayo products should stay in their own condiment family instead
    # of degrading into plain hot sauce or plain mayonnaise matches.
    if (
        'sriracha' in original_name_lower
        and any(token in original_name_lower for token in ('majonnäs', 'majonnas', 'mayo'))
    ):
        return ['srirachamajonnäs']

    # Explicit sparkling-wine ingredients should reach real mousserande vin
    # products without broadening to other sparkling drinks or preserves.
    _sparkling_wine_like = (
        (category or '').lower() == 'beverages'
        and 'mousserande' in original_name_lower
        and (
            re.search(r'\bvin\b', original_name_lower) is not None
            or 'chardonnay' in original_name_lower
        )
        and not any(token in original_name_lower for token in (
            'rose', 'rosé', 'spritz', 'must',
            'fläderblom', 'fladerblom', 'rabarber',
            'vinäger', 'vinager',
        ))
    )
    if _sparkling_wine_like:
        return ['mousserandevin']

    # Exact pesto compounds should keep their own identity instead of collapsing
    # into generic pesto or the raw ingredient family.
    if 'kantarellpesto' in original_name_lower:
        return ['kantarellpesto']
    if any(token in original_name_lower for token in ('kronärtskockspesto', 'kronartskockspesto')):
        return ['kronärtskockspesto']
    # Taco shells / tubs are a distinct buyable bread family. Keep them
    # searchable without opening the broader taco/tex-mex processed-food space.
    if re.search(
        r'\b(?:tacoskal|taco\s+shells?|tacotubs?|taco\s+tubs?|taco\s+boats?)\b',
        original_name_lower,
    ):
        return ['tacoskal']
    # Nestlé Fitness breakfast cereals should stay in their own cereal family
    # rather than degrading to the broad brand word "fitness", which also hits
    # snack bars. Keep this pantry-only and exclude explicit bar products.
    if (
        (category or '').lower() == 'pantry'
        and 'fitness' in original_name_lower
        and 'bar' not in original_name_lower
    ):
        return ['fitnessflingor']
    # "Flytande smör" recipes are usually shopping for the liquid butter/rapeseed
    # cooking blend sold as "smör & rapsolja flytande", not a solid butter block.
    if (
        re.search(r'\bflytande\b', original_name_lower)
        and re.search(r'\bsm[öo]r\b', original_name_lower)
        and re.search(r'\braps(?:olja)?\b', original_name_lower)
    ):
        return ['flytandesmör']

    # Baby food age label — "Från 12 Månader", "Från 6 mån" — not recipe ingredients
    if _BABY_FOOD_PATTERN.search(original_name_lower):
        return []

    # Normalize using central Swedish utility (for keyword extraction)
    name = normalize_ingredient(product_name)
    name = name.lower()

    # Remove punctuation that can stick to words (e.g., "kokosmjölk," → "kokosmjölk")
    name = _PUNCTUATION_PATTERN.sub(' ', name)
    # Fix broken compound words: "herrgårds- grönsaker" → "herrgårdsgrönsaker"
    # Trailing hyphen + space indicates a split compound word from scraper
    name = name.replace('- ', '')
    name = _WHITESPACE_PATTERN.sub(' ', name).strip()

    # Filter out heavily processed foods (salami, instant noodles, etc)
    # Using pre-compiled combined pattern for ~50x speedup
    # MUST run BEFORE space normalization — "gul curry" in PROCESSED_FOODS won't match
    # "gulcurry" after normalization joins the words.
    # Check BOTH normalized name AND original name — normalize_ingredient strips
    # words like "fryst*" which we need for PROCESSED_FOODS detection (e.g., "frystorkade")
    name_normalized = fix_swedish_chars(name).lower()
    # Pre-PROCESSED_FOODS space norm: "glass noodles" → "glasnudlar" so 'glass'
    # (ice cream blocker) doesn't trigger on glass noodle products.
    # Must happen BEFORE the check, unlike general space norms which run AFTER.
    _pre_check_name = name_normalized.replace('glass noodles', 'glasnudlar').replace('glass noodle', 'glasnudlar')
    _pre_check_orig = original_name_lower.replace('glass noodles', 'glasnudlar').replace('glass noodle', 'glasnudlar')
    _plain_dark_chocolate_bar = (
        'chokladkaka' in _pre_check_orig
        and '%' in _pre_check_orig
        and any(cue in _pre_check_orig for cue in ('mörk choklad', 'mork choklad'))
        and not any(flavor in _pre_check_orig for flavor in (
            'apelsin', 'chili', 'fikon', 'havssalt', 'seasalt',
            'karamell', 'caramel', 'caramelized', 'hazelnut', 'hassel',
            'mint', 'hallon', 'mango', 'passion', 'pistage',
            'almond', 'lakrits', 'saltlakrits',
        ))
    )
    if _plain_dark_chocolate_bar:
        return ['choklad']

    if _PROCESSED_FOODS_PATTERN and (
        _PROCESSED_FOODS_PATTERN.search(_pre_check_name)
        or _PROCESSED_FOODS_PATTERN.search(_pre_check_orig)
    ):
        # Check exemptions (e.g., "Kryddmix Tikka Masala" is a cooking ingredient)
        if not any(ex in original_name_lower for ex in PROCESSED_FOODS_EXEMPTIONS):
            return []

    # Suffix-based processed food check: compound words ending with processed suffixes
    # "Potatis & Purjolöksoppa" → "purjolöksoppa" ends with "soppa" → processed
    if PROCESSED_FOOD_SUFFIXES:
        for word in original_name_lower.split():
            if any(word.endswith(sfx) and len(word) > len(sfx)
                   for sfx in PROCESSED_FOOD_SUFFIXES):
                if not any(ex in original_name_lower for ex in PROCESSED_FOODS_EXEMPTIONS):
                    return []
                break

    # Normalize space variants (e.g., "corn flakes" -> "cornflakes")
    # AFTER processed foods check — joining words would hide multi-word blockers
    name = _apply_space_normalizations(name)
    # Strip punctuation from original_name_lower so carrier detection works
    # (e.g., "Lemonad," → "Lemonad" matches CARRIER_PRODUCTS)
    original_name_lower = _PUNCTUATION_PATTERN.sub(' ', original_name_lower)
    original_name_lower = original_name_lower.replace('- ', '')  # fix broken compounds
    # Split '&' into separate words for carrier/flavor detection
    # "Vitlök&örter Färskost" → "Vitlök örter Färskost" so both are recognized
    # Done AFTER processed foods check to avoid "smör&raps" → "smör raps" false hit
    original_name_lower = original_name_lower.replace('&', ' ')
    original_name_lower = _WHITESPACE_PATTERN.sub(' ', original_name_lower).strip()
    # Save pre-space-norm version for carrier detection (space norms may split
    # compound words like "vitlöksklyftor" → "vitlök klyftor", breaking carrier lookup)
    original_for_carrier = original_name_lower
    original_name_lower = _apply_space_normalizations(original_name_lower)
    # Also split & in normalized name so keyword iteration sees separate words
    name = name.replace('&', ' ')
    name = _WHITESPACE_PATTERN.sub(' ', name).strip()

    # KRYDDA JOINING: multi-word spice products → compound keyword
    # "Kött & Grill Krydda Påse" → words [..., 'grill', 'krydda', 'påse']
    # Join last qualifier + krydda/kryddor → 'grillkrydda', discard remaining words.
    # Compound forms like "Grillkrydda" are already one word and unaffected.
    _name_words = name.split()
    for _krydda_suffix in ('krydda', 'kryddor'):
        if _krydda_suffix in _name_words:
            _ki = _name_words.index(_krydda_suffix)
            if _ki > 0:
                # Join preceding word + krydda/kryddor into compound keyword
                _compound = _name_words[_ki - 1] + _krydda_suffix
                return [_compound]
            # "Krydda Kummin Hel" — krydda is product type, next word is the spice
            if _ki + 1 < len(_name_words):
                _next_word = _name_words[_ki + 1]
                if _next_word not in STOP_WORDS and len(_next_word) >= 4:
                    return [_next_word]
            return []

    # Frozen ready meals with portion indicators ("Ca 3 Port", "4 Portioner")
    # But NOT plain staples in portion packs ("Basmati/2 Port")
    if _PORTION_PATTERN.search(original_name_lower) and not any(
        trigger in original_name_lower for trigger in IMPLICIT_KEYWORDS
    ):
        return []

    # Check for flavored products that should be skipped entirely (e.g., flavored yogurt)
    # "Hallon Jordgubb Yoghurt" should NOT match recipes needing plain yogurt
    # NOTE: Use original_name_lower here, not the normalized name
    # Uses pre-compiled combined regex (1 search instead of 17 individual)
    _skip_match = _SKIP_IF_FLAVORED_PATTERN.search(original_name_lower)
    if _skip_match:
        skip_carrier = _skip_match.group(1)
        # Find all matching flavor words in the product name
        # Exclude flavor words that are part of the skip_carrier itself
        # (e.g., "fraiche" is a FLAVOR_WORD but part of skip_carrier "crème fraiche")
        matching_flavors = {
            fw for fw in FLAVOR_WORDS
            if fw in original_name_lower and fw not in skip_carrier and len(fw) > 3
        }
        has_flavor = bool(matching_flavors)
        # Check if ALL flavors are cooking-valid (vanilj yoghurt for smoothies)
        only_cooking_flavors = matching_flavors and matching_flavors.issubset(COOKING_FLAVORS)
        # Brands that are typically flavored (not plain cooking yogurt)
        is_flavored_brand = any(brand in original_name_lower for brand in [
            'yoggi', 'yoplait', 'activia', 'danone',
        ])
        has_allowed_type = any(allowed in original_name_lower for allowed in ALLOWED_YOGURT_TYPES)
        # Also allow "matlagning" type
        is_cooking_type = 'matlagning' in original_name_lower
        # Plant-based yoghurts explicitly stating their base ("havrebaserad", "sojabaserad",
        # "växtbaserad") are not "flavored" — 'havre' is the BASE ingredient, not a fruit flavor.
        # Allow through so check_yoghurt_match vego logic handles recipe-side filtering.
        is_vego_type = any(v in original_name_lower for v in [
            'havrebaserad', 'sojabaserad', 'växtbaserad', 'vaxtbaserad',
            'vegansk', 'vegetabilisk',
        ])

        # If the product also contains a CARRIER_PRODUCT word (e.g., "röra" in
        # "Yoghurt & Feta Röra"), let the carrier logic handle it instead of
        # blocking here — the carrier will strip flavor words properly.
        _name_words_quick = set(original_for_carrier.split())
        has_other_carrier = bool(
            (_name_words_quick & _CARRIER_SINGLE_WORDS) - {skip_carrier}
        ) or any(
            c in original_for_carrier
            and _apply_space_normalizations(c) != skip_carrier
            for c in _CARRIER_MULTI_WORDS
        )

        if (has_flavor or is_flavored_brand) and not is_cooking_type and not has_other_carrier and not is_vego_type:
            # Cooking flavors (vanilj) are allowed through — they're real ingredients
            if only_cooking_flavors:
                pass  # "Yoghurt Vanilj" → allow (used in smoothies/baking)
            elif not has_allowed_type or has_flavor:
                return []

    # Check for carrier products with flavor words (use pre-space-norm name)
    # "Paprika Lök Färskost" should NOT extract "paprika" as keyword
    # Use original_for_carrier (not original_name_lower) because space norms may
    # split compound carriers like "vitlöksklyftor" → "vitlök klyftor"
    matched_carrier = None
    matched_carrier_pos = len(original_for_carrier)
    name_words = original_for_carrier.split()
    name_words_set = set(name_words)

    # Fast path: check single-word carriers via set intersection (O(n) vs O(173))
    direct_matches = name_words_set & _CARRIER_SINGLE_WORDS
    # Collect ALL carrier candidates, then pick best one
    _carrier_candidates = []  # list of (carrier, pos)
    for carrier in direct_matches:
        carrier_pos = original_for_carrier.index(carrier)
        _carrier_candidates.append((carrier, carrier_pos))

    # Check compound suffixes: "falukorv" ends with "korv", prefix ≥ 3 chars
    # Only for words NOT already matched as direct carriers
    # Carrier must be ≥ 3 chars for suffix matching to avoid false positives
    # (e.g., 'te' matching suffix of 'chocolate'). Short carriers like 'te'
    # still work via direct word match (set intersection above).
    for word in name_words:
        if word in direct_matches:
            continue
        for carrier in _CARRIER_SUFFIX_CANDIDATES:
            if (len(carrier) >= 3 and
                    word.endswith(carrier) and
                    len(word) > len(carrier) and
                    len(word) - len(carrier) >= 3):
                carrier_pos = original_for_carrier.index(carrier)
                _carrier_candidates.append((carrier, carrier_pos))
                break  # one suffix match per word is enough

    # Multi-word carriers: substring check (only ~10 items)
    for carrier in _CARRIER_MULTI_WORDS:
        if carrier in original_for_carrier:
            carrier_pos = original_for_carrier.index(carrier)
            _carrier_candidates.append((carrier, carrier_pos))

    # Pick best carrier: prefer non-flavor carriers over flavor carriers
    # "Tomat&örter Färskost" → färskost wins over örter (örter is a flavor word)
    # Among same priority, pick leftmost (smallest pos)
    if _carrier_candidates:
        _primary = [(c, p) for c, p in _carrier_candidates if c not in FLAVOR_WORDS]
        _secondary = [(c, p) for c, p in _carrier_candidates if c in FLAVOR_WORDS]
        _best = _primary or _secondary
        matched_carrier, matched_carrier_pos = min(_best, key=lambda x: x[1])

    skip_flavor_words = set()
    carrier_words = set()
    if matched_carrier:
        skip_flavor_words = FLAVOR_WORDS
        carrier_words = set(matched_carrier.split())

    name = fix_swedish_chars(name).lower()
    words = name.split()
    keywords = []

    # If this is a carrier product and the carrier word isn't in the normalized name,
    # add it manually ONLY if space normalization didn't consume it into a compound.
    # Example: "Shirataki Nudlar" → space norm → "shirataki" (nudlar consumed).
    #   nudlar in original_for_carrier but NOT in original_name_lower → space norm ate it.
    # Counter-example: "Korv Grillad Chili" → no space norm applies.
    #   korv in both original_for_carrier AND original_name_lower → safe to add back.
    if matched_carrier and matched_carrier not in name:
        carrier_in_pre_norm = matched_carrier in original_for_carrier
        carrier_in_post_norm = matched_carrier in original_name_lower
        if not carrier_in_pre_norm or carrier_in_post_norm:
            # Carrier wasn't consumed by space norm — add it back
            keywords.append(matched_carrier)

    for word in words:
        # Skip stop words
        if word in STOP_WORDS:
            continue

        # Skip flavor words for carrier products (e.g., "paprika" in "Paprika Färskost")
        # but NOT the carrier word itself (e.g., "räkor" in "Räkor Paprika Vitlök")
        # and NOT words that contain the carrier as suffix (e.g., "valnötter" contains
        # carrier "nötter" — it IS the carrier product, not a flavor of it)
        if word in skip_flavor_words and word not in carrier_words:
            if not (matched_carrier and len(matched_carrier) >= 3
                    and word.endswith(matched_carrier) and word != matched_carrier):
                continue

        # Skip too short words UNLESS they are important ingredients
        if len(word) < min_length and word not in IMPORTANT_SHORT_KEYWORDS:
            continue

        # Skip pure numbers
        if word.isdigit():
            continue

        # Check if this word is part of a compound word
        # If yes, only add the compound, not the part
        # Uses pre-built index for O(1) lookup instead of looping all compounds
        is_part_of_compound = False
        candidate_compounds = _COMPOUND_WORD_INDEX.get(word)
        if candidate_compounds:
            for compound in candidate_compounds:
                if compound in name:
                    is_part_of_compound = True
                    if compound not in keywords:
                        keywords.append(compound)
                    break

        if is_part_of_compound:
            continue

        keywords.append(word)

    # Add implicit keywords (e.g., "herrgård" → also add "ost")
    for trigger, implicit_kw in IMPLICIT_KEYWORDS.items():
        if trigger in name and implicit_kw not in keywords:
            # Skip implicit keywords from flavor words in carrier products
            # e.g., "Mayo Sesame & soy" → 'soy' triggers 'soja', but mayo is carrier
            if matched_carrier and trigger in skip_flavor_words and trigger not in carrier_words:
                continue
            # Skip if trigger is embedded inside a compound keyword already extracted
            # e.g., "herrgårdsgrönsaker" contains "herrgård" but ost shouldn't be added
            if any(trigger in kw and kw != trigger for kw in keywords):
                continue
            keywords.append(implicit_kw)

    # Apply multi-word substitutions (e.g., "apelsin" + "röd" → "blodapelsin")
    for required_words, old_kw, new_kw in PRODUCT_NAME_SUBSTITUTIONS:
        if required_words.issubset(set(name.split())):
            if old_kw in keywords:
                keywords = [new_kw if kw == old_kw else kw for kw in keywords]
            elif new_kw not in keywords:
                # old_kw was filtered (e.g., stop word) — add new_kw directly
                keywords.append(new_kw)

    # Apply keyword synonyms (e.g., "ärter" → "ärtor" to match recipe terminology)
    keywords = [KEYWORD_SYNONYMS.get(kw, kw) for kw in keywords]

    # Replace specific keywords with their generic parent
    # e.g., "prästost" → "ost", "jasminris" → "ris"
    # This ensures products group under the generic name in the UI.
    keywords = [INGREDIENT_PARENTS.get(kw, kw) for kw in keywords]

    # Short pasta products named mainly by shape + descriptor ("Tortiglioni Al
    # Bronzo", "Fusilli Al Bronzo") are still just ordinary pasta and should
    # surface for generic pasta ingredients. If a short-pasta carrier was
    # detected but no pasta umbrella survived extraction, add it back.
    if matched_carrier in _SHORT_PASTA_CARRIERS and 'pasta' not in keywords:
        keywords.append('pasta')

    # Add extra parent keywords for compound cuts (keep original + add generic).
    # "kycklingbröstfilé" stays AND adds "kycklingfilé" so the product matches
    # both specific "kycklingbröstfilé" and generic "kycklingfilé" recipes.
    for kw in list(keywords):
        parent = KEYWORD_EXTRA_PARENTS.get(kw)
        if parent:
            parents = parent if isinstance(parent, list) else [parent]
            for p in parents:
                if p not in keywords:
                    keywords.append(p)

    # Generic "vit fiskfilé" recipes should surface common white-fish fillets
    # without also catching salmon fillets.
    if (
        any(kw in _WHITE_FISH_FAMILY_KEYWORDS for kw in keywords)
        and any(marker in name for marker in _WHITE_FISH_FILLET_MARKERS)
        and 'fiskfilé' not in keywords
    ):
        keywords.append('fiskfilé')

    # Specific vinegars should still surface for a generic "vinäger" ingredient.
    # This keeps white/red wine vinegar, cider vinegar, balsamic vinegar, etc.
    # visible next to products that already contain standalone "vinäger".
    for kw in list(keywords):
        if kw not in {'vinäger', 'vinager'}:
            if kw.endswith('vinäger') and 'vinäger' not in keywords:
                keywords.append('vinäger')
            elif kw.endswith('vinager') and 'vinager' not in keywords:
                keywords.append('vinager')

    # Extract base words from compound keywords (e.g., "högrevsburgare" → also add "hamburgare")
    extra = []
    for kw in keywords:
        for suffix, base in COMPOUND_BASE_KEYWORDS.items():
            if kw.endswith(suffix) and len(kw) > len(suffix) + 2 and kw != base:
                extra.append(base)
    keywords.extend(extra)

    # Bread products described only by ingredient names: "Valnöt Russin Honung 540g"
    # has NO bread-type word — just ingredient names. Strip if category is 'bread',
    # ALL keywords are FLAVOR_WORDS, AND the product name has no bread-type word.
    # Products WITH a bread-type word ("Fralla Russin", "Surdegsbröd Valnöt") keep keywords.
    _BREAD_TYPE_WORDS = frozenset({
        'bröd', 'brod', 'bulle', 'bullar', 'fralla', 'baguett', 'baguette',
        'ciabatta', 'focaccia', 'wrap', 'kavring', 'knäcke', 'knackebrod',
        'limpa', 'levain', 'kaka', 'längd', 'langd', 'muffin', 'scone',
        'tortilla', 'pitabröd', 'tunnbröd', 'surdeg', 'franska', 'ruta',
    })
    _is_bread = category and category.lower() == 'bread'  # NOTE: 'deli' removed — contains cheese/charcuterie, not bread
    if _is_bread and not matched_carrier and keywords:
        _has_bread_word = any(
            bt in original_name_lower for bt in _BREAD_TYPE_WORDS
        )
        if not _has_bread_word and all(kw in FLAVOR_WORDS for kw in keywords):
            keywords = []

    # Frozen ready meals: if a carrier product is frozen, the carrier words
    # that are also flavor words are just components of the dish, not standalone
    # ingredients. E.g., "Krämig kyckling med soltorkad tomat 380g Felix"
    # → carrier 'soltorkad tomat' keeps 'tomat', but it's a frozen ready meal.
    # Strip carrier words that are FLAVOR_WORDS in frozen products.
    _is_frozen = (bool({'fryst', 'frysta'} & set(name_words))
                  or (category and category.lower() == 'frozen'))
    if matched_carrier and _is_frozen and keywords:
        keywords = [kw for kw in keywords
                    if kw not in FLAVOR_WORDS or kw not in carrier_words]

    # ── Ice cream normalization ──────────────────────────────────────────
    # Only base-flavor ice cream products get keywords:
    # Vanilla → 'vaniljglass', choklad → 'chokladglass', jordgubb → 'jordgubbsglass', etc.
    # Everything else (exotic combos, novelty items, unknown flavors) → blocked.
    # Recipes map standalone "glass" → 'vaniljglass' via INGREDIENT_PARENTS.
    _GLASS_CARRIER_WORDS = frozenset({
        'glass', 'glasspinnar', 'glasspinne',
    })
    # Base flavor → glass keyword mapping (Swedish + English product names)
    # Order matters: first match wins. Fruit flavors before choklad so
    # "Hallon & vit choklad" → hallonglass (not chokladglass).
    _GLASS_FLAVOR_MAP = {
        'vanilj': 'vaniljglass', 'vanilla': 'vaniljglass',
        'jordgubb': 'jordgubbsglass', 'strawberry': 'jordgubbsglass', 'smultron': 'jordgubbsglass',
        'hallon': 'hallonglass', 'raspberry': 'hallonglass',
        'blåbär': 'blåbärsglass', 'blueberry': 'blåbärsglass',
        'mango': 'mangoglass',
        'päron': 'päronglass',
        'citron': 'citronglass', 'lemon': 'citronglass',
        'lakrits': 'lakritsglass', 'saltlakrits': 'lakritsglass', 'licorice': 'lakritsglass', 'liquorice': 'lakritsglass',
        'kanel': 'kanelglass',
        'pistage': 'pistaschglass', 'pistachio': 'pistaschglass',
        'kaffe': 'kaffeglass', 'coffee': 'kaffeglass',
        'nougat': 'nougatglass',
        'choklad': 'chokladglass', 'chocolate': 'chokladglass',  # after fruits
        'mintchoklad': 'chokladglass',
    }
    # Some mixed-flavor vanilla products use a second flavor word that we do not
    # want to promote to its own exact recipe keyword, but we still need to
    # treat it as a combo signal rather than plain vanilla ice cream.
    _GLASS_VANILLA_COMBO_MARKERS = frozenset({
        'vinbär', 'vinbar',
        'svartvinbär', 'svartvinbar',
        'rödvinbär', 'rodvinbar',
        'passion', 'passionfrukt', 'passionsfrukt',
    })
    # Exotic/brand names that indicate non-base-flavor glass → block
    _GLASS_EXOTIC_WORDS = frozenset({
        'twix', 'snickers', 'daim', 'mars', 'oreo', 'nutella', 'dumle',
        'phish', 'brownie', 'cookie', 'cookies', 'fudge', 'rocky',
        'caramel', 'salted', 'churros', 'tiramisu', 'cheesecake',
        'banoffee', 'honeycomb', 'euphoria', 'utopia', 'bonbon',
        'kids', 'mix', 'flerpack', 'leos', 'minecraft', 'hockeypulver',
        'favorites', 'klassikerlåda', 'familjemix',
        'sitting', 'bull', 'volcanix', 'spectacu',
        'peanut', 'pecan', 'macadamia', 'almond',  # nut combos in glass
        'kola', 'kolasås', 'karamell', 'toffee',
        'kladdkaka', 'kanelbulle', 'äppelpaj', 'punsch',
        'himmelsk', 'brynt', 'rostade', 'popcorn',
        'twist', 'solero', 'magnum', 'nogger', 'calippo',  # novelty brands/formats
        'baked', 'chunk', 'crunch', 'swirl', 'ripple', 'core', 'chip',  # English combo descriptors
    })
    # Isglass products are novelty items — always blocked regardless of carrier detection
    if 'isglass' in original_name_lower:
        keywords = []
    elif matched_carrier and matched_carrier in _GLASS_CARRIER_WORDS:
        _is_pinne_strut = (
            matched_carrier in ('glasspinnar', 'glasspinne')
            or any(w in original_name_lower for w in ('strut', 'strutar'))
            or bool(re.search(r'\b\d+-p\b', original_name_lower))  # "1-p", "3-p" = single/multi pack novelty
        )
        if _is_pinne_strut:
            keywords = []
        else:
            # Check for base flavors in product name
            _matched_flavor = None
            for _flavor_word, _flavor_kw in _GLASS_FLAVOR_MAP.items():
                if _flavor_word in original_name_lower:
                    _matched_flavor = _flavor_kw
                    break
            # Plain vanilla recipes should not accept combo flavors like
            # "Vanilla pistachio" or "Vanilj & svartvinbär". Keep the fix narrow:
            # only block vanilla when a second flavor marker is also present.
            _has_vanilla_combo = False
            if _matched_flavor == 'vaniljglass':
                _has_vanilla_combo = any(
                    _flavor_word not in ('vanilj', 'vanilla')
                    and _flavor_word in original_name_lower
                    for _flavor_word in _GLASS_FLAVOR_MAP
                ) or any(marker in original_name_lower for marker in _GLASS_VANILLA_COMBO_MARKERS)
            # Check for exotic/combo names
            _name_words_set = set(original_name_lower.split())
            _is_exotic = bool(_name_words_set & _GLASS_EXOTIC_WORDS)
            if _matched_flavor and not _is_exotic and not _has_vanilla_combo:
                # Product has a recognized base flavor
                keywords = [_matched_flavor]
                # Vanilla products also get 'glass' so standalone "glass"
                # recipes match them (compound-strict blocks cross-flavor)
                if _matched_flavor == 'vaniljglass':
                    keywords.append('glass')
            elif not _is_exotic and not _matched_flavor:
                # Unknown/unclassified flavor → blocked.
                # Only products with recognized base flavors (vanilj, choklad,
                # jordgubb, kanel, lakrits, etc.) get keywords. Exotic combos
                # (Chunky monkey, Banankola, Tip top) are never recipe ingredients.
                keywords = []
            else:
                # Exotic combo flavor → blocked
                keywords = []

    # Safety net: if carrier stripping removed ALL keywords, the first word
    # in the name is likely the actual product (not a flavor/topping).
    # Example: "Ost Pizza Riven" → carrier 'pizza' strips 'ost' → empty →
    # but 'ost' IS the product (cheese for pizza), so add it back.
    # EXCEPTION 1: for flavor-dominant carriers (saft, juice, chips, etc.),
    # the first word really IS a flavor — "Jordgubb Saft" should NOT
    # re-add 'jordgubb' as keyword.
    # EXCEPTION 2: frozen carrier products are ready meals, not ingredients.
    # "Prosciutto Pizza Fryst" is a frozen pizza, not prosciutto.
    if matched_carrier and not keywords and matched_carrier not in _FLAVOR_DOMINANT_CARRIERS:
        if not _is_frozen:
            first_word = name_words[0] if name_words else ''
            if first_word and first_word in FLAVOR_WORDS and first_word not in carrier_words:
                keywords.append(first_word)

    # Safety net 2: if the product name consists ONLY of carrier/stop words,
    # the carrier itself IS the product. Add the carrier keyword so the product
    # can match recipes. E.g., "Fusilli" → carrier 'fusilli' → no flavor words →
    # empty → add 'fusilli' → mapped to 'pasta' via INGREDIENT_PARENTS below.
    # "Fusilli Pasta" → both words are carriers → add primary carrier 'fusilli'.
    # EXCEPTION: flavor-dominant carriers (saft, juice, dryck etc.) and frozen
    # products — these are intentionally empty when carrier-only.
    # NOTE: this runs AFTER KEYWORD_SYNONYMS/INGREDIENT_PARENTS, so we apply
    # the same mappings here to stay consistent.
    if (matched_carrier and not keywords
            and matched_carrier not in _FLAVOR_DOMINANT_CARRIERS
            and not _is_frozen):
        kw = matched_carrier
        kw = KEYWORD_SYNONYMS.get(kw, kw)
        kw = INGREDIENT_PARENTS.get(kw, kw)
        keywords.append(kw)

    # Remove packaging/medium keywords when they're secondary to the main product
    # e.g., "Pinklaxfilé Solrosolja" — oil is packaging, not the product
    _PACKAGING_OIL_KEYWORDS = {'solrosolja', 'rapsolja', 'olivolja'}
    _FISH_INDICATORS = {'lax', 'laxfilé', 'sill', 'makrill', 'sardiner',
                        'tonfisk', 'ansjovis', 'fisk', 'torsk', 'sej',
                        'kolja', 'rödspätta', 'kummel'}
    oil_kws = _PACKAGING_OIL_KEYWORDS & set(keywords)
    if oil_kws and len(keywords) > len(oil_kws):
        # Only strip oil if product has a fish/meat primary keyword
        other_kws = set(keywords) - oil_kws
        if any(fish in kw for kw in other_kws for fish in _FISH_INDICATORS):
            keywords = [kw for kw in keywords if kw not in oil_kws]

    # Name-conditional: granola — only naturell/natural variants extract 'granola' keyword
    # Flavored granola (Kakao, Hallon, etc.) is too specific — recipe just wants plain granola
    if 'granola' in keywords:
        _name_for_granola = original_name_lower
        if 'naturell' not in _name_for_granola and 'natural' not in _name_for_granola:
            keywords = [k for k in keywords if k != 'granola']

    # Offer-side extras keep cached and uncached matching behavior aligned.
    # Example: fresh champinjoner should also satisfy generic recipe wording "svamp".
    extra_keywords = []
    for kw in keywords:
        for extra in OFFER_EXTRA_KEYWORDS.get(kw, ()):
            if extra not in keywords and extra not in extra_keywords:
                extra_keywords.append(extra)
        # Named sausage families ending in "...korv" should also satisfy generic
        # korv wording without needing a hand-maintained list per variant.
        if kw.endswith('korv') and kw != 'korv':
            if 'korv' not in keywords and 'korv' not in extra_keywords:
                extra_keywords.append('korv')

    if extra_keywords:
        keywords = extra_keywords + keywords

    # Remove duplicates while preserving order (dict.fromkeys is C-optimized)
    unique_keywords = list(dict.fromkeys(keywords))

    _DRIED_MUSHROOM_KEYWORDS = {
        'svamp', 'johan-svamp', 'johansvamp', 'karljohansvamp',
        'kantarell', 'kantareller', 'trattkantarell',
        'ostronskivling', 'shiitake', 'enoki', 'portabellosvamp',
        'champinjon', 'champinjoner',
    }
    if (
        any(token in original_name_lower for token in ('torkad', 'torkade'))
        and any(
            kw in _DRIED_MUSHROOM_KEYWORDS or 'svamp' in kw
            for kw in unique_keywords
        )
        and 'torkadsvamp' not in unique_keywords
    ):
        unique_keywords.append('torkadsvamp')

    # Recipes that explicitly say "champagne" are pragmatically asking for the
    # sparkling-wine family, even when current live offers are sold under
    # mousserande-vin wording instead of "champagne".
    if 'champagne' in unique_keywords and 'mousserandevin' not in unique_keywords:
        unique_keywords.append('mousserandevin')

    # Soy-mayo products should stay in a combined condiment family instead of
    # degrading into separate soy-sauce or plain-mayonnaise matches.
    if (
        'soja' in original_name_lower
        and any(token in original_name_lower for token in ('majonnäs', 'majonnas', 'mayo'))
        and 'sojamajonnäs' not in unique_keywords
    ):
        unique_keywords.append('sojamajonnäs')

    # Keep sriracha mayo distinct from plain sriracha sauce and plain mayo.
    if (
        'sriracha' in original_name_lower
        and any(token in original_name_lower for token in ('majonnäs', 'majonnas', 'mayo'))
        and 'srirachamajonnäs' not in unique_keywords
    ):
        unique_keywords.append('srirachamajonnäs')

    # Block products where the only keyword is too generic (e.g., "Kryddmix Classic" → ['kryddmix'])
    if len(unique_keywords) == 1 and unique_keywords[0] in SOLO_KEYWORD_BLOCK:
        return []

    return unique_keywords


# Buljong ↔ fond cross-rewrite for "eller" patterns.
# Shared between extract_keywords_from_ingredient, recipe_matcher, and cache_manager.
# höns→kyckling because products use "kycklingfond"/"kycklingbuljong", not "höns-"

# "Xbuljong ... eller fond" → "Xbuljong ... eller Xfond"
# "Xfond ... eller buljong[tärning]" → "Xfond ... eller Xbuljong[tärning]"




def extract_keywords_from_ingredient(
    ingredient: str,
    min_length: int = MIN_KEYWORD_LENGTH_STRICT
) -> List[str]:
    """
    Extract searchable keywords from a recipe ingredient.

    More strict than product extraction (requires longer words).

    Args:
        ingredient: The ingredient text
        min_length: Minimum keyword length (default 7 for stricter matching)

    Returns:
        List of keywords suitable for matching

    Example:
        >>> extract_keywords_from_ingredient("2-3 msk grovt salt")
        []  # "grovt" and "salt" filtered by stop_words
        >>> extract_keywords_from_ingredient("ca 1 kg laxfilé")
        ['laxfilé']
    """
    # Skip sub-recipe references — these are not purchasable ingredients
    # e.g., "2 portioner Glass LCHF - Grundrecept", "surdegsstart (se grundrecept)"
    _lower = ingredient.lower()
    if is_subrecipe_reference_text(_lower):
        return []

    # Skip decoration ingredients — these are garnishes/decorations, not food to buy.
    # "marsipankycklingar" would otherwise extract "kycklingar" via reverse-substring
    # and match 60+ chicken products. "chokladägg" is intentionally excluded here:
    # some recipes explicitly want the candy itself.
    _DECORATION_COMPOUNDS = ('marsipankyckling', 'marsipanfigur', 'marsipanägg',
                             'sockerblomm', 'sockerfigur')
    if any(d in _lower for d in _DECORATION_COMPOUNDS):
        return []

    # Fix Swedish chars first (don't use normalize_ingredient as it removes too much)
    name = fix_swedish_chars(ingredient)
    name = name.lower()

    # Normalize space variants (e.g., "corn flakes" -> "cornflakes")
    name = _apply_space_normalizations(name)

    # Plain measured "durumvete" in Swedish pasta recipes typically means durum
    # flour, not bulgur. Keep this ingredient-side and narrow to measured lines
    # without "bulgur"/explicit flour wording so we do not broaden the generic
    # durumvete family elsewhere.
    name = normalize_measured_durumvete_flour(name)
    name = normalize_measured_risotto_rice(name)

    # Candied/pickled ginger should not fall back to generic fresh ginger.
    # Keep explicit "(gari)" hints as a secondary keyword so sushi-ginger
    # products that only expose `gari` still match these ingredient lines.
    if 'syltadingefära' in name or 'syltadingefara' in name:
        return ['syltadingefära', 'gari'] if 'gari' in name else ['syltadingefära']

    # Bread-yeast wording should stay on the exact baker's-yeast-for-bread
    # family instead of collapsing to generic yeast or matbröd.
    if 'matbrödsjäst' in name or 'matbrodsjast' in name:
        return ['matbrödsjäst']
    if (
        'jäst' in name
        and any(cue in name for cue in ('färsk', 'farsk'))
        and not any(cue in name for cue in ('söt', 'sota', 'söta', 'sota'))
    ):
        return ['matbrödsjäst', 'jäst']

    # Bao / steam buns are their own buyable bread family, not generic bread.
    if 'steambuns' in name:
        return ['steambuns']

    # Explicit dried-mushroom umbrella wording should stay on dried mushroom
    # products instead of degrading to generic fresh/preserved svamp fallback.
    if 'torkadsvamp' in name:
        return ['torkadsvamp']

    # Coconut-drink wording should stay on the coconut-drink family instead of
    # leaking to whole coconut produce through the shared base word.
    if 'kokosdryck' in name:
        return ['kokosdryck']

    # Explicit sea salt is a real pantry ingredient and should survive instead
    # of disappearing into the generic salt stop-word path.
    if re.search(r'\b(?:havssalt|sea salt)\b', name):
        return ['havssalt']

    # Generic frozen fish wording in recipes is usually bought as ordinary
    # frozen fish fillets, not as a separate diced-fish product family.
    if (
        'fisk' in name
        and 'fiskfilé' not in name
        and 'fiskfile' not in name
        and any(cue in name for cue in ('fryst', 'frysta', 'djupfryst', 'djupfrysta'))
    ):
        return ['fiskfilé']

    # Plain jam is an intentional umbrella ingredient and should surface
    # ordinary sylt products unless the recipe asks for a more specific flavor.
    if re.search(r'\bsylt\b', name):
        return ['sylt']

    # Qualified wheat flour ingredient lines should keep their requested level
    # instead of degrading to plain wheat flour.
    if 'vetemjöl' in name:
        flour_keywords = []
        if 'special' in name:
            flour_keywords.append('vetemjölspecial')
        if 'fullkorn' in name:
            flour_keywords.append('vetemjölfullkorn')
        if flour_keywords:
            return flour_keywords

    # Trumpet chanterelles should keep their exact mushroom species in recipe
    # wording so explicit lines do not collapse to generic chanterelles.
    if 'trattkantarell' in name:
        return ['trattkantarell']

    # Explicit salt-cured pork should not degrade to generic fresh pork cuts.
    if ('rimmat fläsk' in name or 'rimmat flask' in name):
        return ['rimmatfläsk']

    # Explicit candy ingredient: keep chocolate eggs as their own exact family
    # instead of dropping them as decoration compounds or broadening to plain eggs/chocolate.
    if 'chokladägg' in name or 'chokladagg' in name:
        return ['chokladägg']

    # Exact pesto compounds should not degrade into generic pesto or the raw
    # ingredient family. If stores later carry these exact variants, they can
    # match directly; otherwise the line should stay at 0 matches.
    if 'kantarellpesto' in name:
        return ['kantarellpesto']
    if 'kronärtskockspesto' in name or 'kronartskockspesto' in name:
        return ['kronärtskockspesto']

    # Keep savory spreads/dips distinct when the recipe explicitly asks for a
    # creme/kräm version of an ingredient family.
    if (
        any(token in name for token in ('creme', 'kräm', 'kram'))
        and ('soltorkad tomat' in name or 'soltorkade tomater' in name)
    ):
        return ['soltorkadetomatcreme']

    # "Xbuljong eller fond" → "Xbuljong eller Xfond"
    name = rewrite_buljong_eller_fond(name)
    name = rewrite_truncated_eller_compounds(name)
    name = rewrite_mince_of_alternatives(name)

    # Expand shorthand alternatives where the second option omits the shared prefix.
    # "körsbärssylt eller -marmelad" → "körsbärssylt eller körsbärsmarmelad"
    name = re.sub(
        r'\b([a-zåäöé]+?)(sylt|marmelad)\s+eller\s+-(sylt|marmelad)\b',
        r'\1\2 eller \1\3',
        name,
    )

    # Keep named cheese preferences from parentheticals such as
    # "lagrad ost (helst gruyère)" before stripping the remaining paren text.
    name = preserve_cheese_preference_parentheticals(name)
    # Keep clarifying fresh-chili aliases before generic paren stripping.
    # "röd peppar (chili)" should behave like "röd chilipeppar".
    name = preserve_parenthetical_chili_alias(name)
    name = preserve_fresh_pasta_parenthetical(name)
    name = preserve_non_concentrate_parenthetical(name)
    name = preserve_parenthetical_grouped_herb_leaves(name)
    # Keep explicit shiso herb fallbacks before generic paren stripping.
    name = preserve_parenthetical_shiso_alternatives(name)
    # Parenthetical "eller" segments are true ingredient alternatives, not
    # descriptive aside text. Lift them out before stripping remaining parens:
    # "olivolja (eller smör)" -> "olivolja eller smör"
    # "inlagda gurkor (eller 1 dl cornichons)" -> keep the cornichons option.
    name = re.sub(r'\(\s*eller\s+([^)]*)\)', r' eller \1', name, flags=re.IGNORECASE)

    # Remove parenthetical content, but preserve any fond/buljong keywords that were
    # rewritten inside parens (e.g., "(vatten och tärning eller kycklingfond)" → keep "kycklingfond")
    def _strip_parens_keep_stock(m):
        content = m.group(0)
        # Extract any fond/buljong keyword that was rewritten inside the parens
        stock_match = re.search(
            r'((?:kyckling|grönsaks|gronsaks|fisk|kött|kott|kalv|svamp|skaldjurs)(?:fond|buljong))',
            content
        )
        if stock_match and 'eller' in content:
            return ' ' + stock_match.group(1)
        return ''
    name = re.sub(r'\([^)]*\)', _strip_parens_keep_stock, name)

    # Strip product descriptions: "grillolja Smaksatt med persilja, vitlök och citron"
    # Everything after "smaksatt med" describes the product, not separate ingredients.
    name = re.sub(r'\s+smaksatt\s+med\s+.*', '', name, flags=re.IGNORECASE)

    # Remove quantities but keep the ingredient name
    # Remove patterns like "2-3", "ca 1", "0,5-1"
    name = _NUMBERS_PATTERN.sub('', name)  # Remove numbers
    name = _MEASUREMENTS_PATTERN.sub('', name)  # Remove measurements
    # Treat slash-delimited ingredient alternatives as separate tokens.
    # This keeps cases like "smör/margarin" usable without affecting fractions
    # such as "1/2", because digits are removed above and we only split
    # letter-to-letter slashes here.
    name = re.sub(r'(?<=[a-zåäöéèü])/(?=[a-zåäöéèü])', ' ', name)
    name = _PUNCT_SPLIT_PATTERN.sub(' ', name)  # Remove punctuation that splits words
    name = _WHITESPACE_PATTERN.sub(' ', name).strip()  # Clean up whitespace

    # Serving hints like "kex till ost" should not turn the ingredient into cheese.
    # Keep the purchasable base product and drop the trailing usage cue.
    name = re.sub(r'\bkex\s+till\s+ost\b', 'kex', name)

    # "gurt" is informal Swedish shorthand for yoghurt (plant-based brands: Oatly Havregurt, Planti)
    # e.g., "växtbaserad gurt" → "växtbaserad yoghurt" so check_yoghurt_match vego logic applies
    name = re.sub(r'\bgurt\b', 'yoghurt', name)

    # Plant-based "matlagning" is recipe shorthand for purchasable cooking cream
    # products, not a bare adjective. Emit concrete cream keywords so phrases like
    # "Havrebaserad matlagning" can surface both havregrädde and matlagningsgrädde.
    if 'havrebaserad matlagning' in name:
        return ['havregrädde', 'grädde']
    if 'soyabaserad matlagning' in name or 'sojabaserad matlagning' in name:
        return ['soja', 'grädde']
    if any(phrase in name for phrase in (
        'vegansk matlagning',
        'växtbaserad matlagning',
        'vaxtbaserad matlagning',
        'vegetabilisk matlagning',
    )):
        return ['grädde']

    # Generic fresh-berry garnish lines should surface concrete fresh berry
    # offers instead of staying at 0 matches. Keep this on the ingredient side
    # so existing per-berry blocker rules continue to filter juice, candy,
    # yoghurt flavors, and similar non-berry products.
    if re.search(r'\b(?:blandade\s+)?färska?\s+bär\b', name):
        return ['hallon', 'blåbär', 'jordgubbar', 'björnbär', 'vinbär', 'krusbär', 'smultron']

    # Exact porter wording in recipe text should match porter offers only.
    # Keep this narrow — generic öl stays intentionally unmatched.
    if re.search(r'\bporter\b', name):
        return ['porter']

    # Remove negation phrases: "utan ägg" → remove both words.
    # "pasta utan ägg" should extract only "pasta", not "ägg".
    name = re.sub(r'\butan\s+\w+', '', name)

    # Carrier product detection: if ingredient text contains a multi-word carrier
    # (e.g., "crème fraîche paprika och chili"), treat flavor words as descriptors
    # and only keep the carrier keyword.
    # NOTE: Only multi-word carriers are checked. Single-word carriers (korv, chips,
    # soppa) are too aggressive for ingredients — "soppa med purjolök och potatis"
    # would incorrectly strip purjolök and potatis as flavors.
    skip_flavor_words = set()
    carrier_words = set()
    for carrier in _CARRIER_MULTI_WORDS:
        if carrier in name:
            skip_flavor_words = FLAVOR_WORDS
            carrier_words = set(carrier.split())
            break

    words = name.split()
    keywords = []

    for word in words:
        # Skip stop words
        if word in STOP_WORDS:
            continue

        # Skip flavor words when inside a carrier product ingredient
        # (but keep the carrier's own words, e.g., "fraiche" from "creme fraiche")
        if word in skip_flavor_words and word not in carrier_words:
            continue

        # Skip too short words (stricter for ingredients)
        # But allow important short keywords like 'lax', 'kiwi', 'ost'
        if len(word) < min_length and word not in IMPORTANT_SHORT_KEYWORDS:
            continue

        # Skip pure numbers (shouldn't happen after cleanup but just in case)
        if word.isdigit():
            continue

        # Prefer compound words (uses pre-built index for O(1) lookup)
        is_part_of_compound = False
        candidate_compounds = _COMPOUND_WORD_INDEX.get(word)
        if candidate_compounds:
            for compound in candidate_compounds:
                if compound in name:
                    is_part_of_compound = True
                    if compound not in keywords:
                        keywords.append(compound)
                    break

        if is_part_of_compound:
            continue

        keywords.append(word)

    # Apply KEYWORD_SYNONYMS: normalize plurals and alternate forms
    # e.g., "humrar" → "hummer", "ärter" → "ärtor"
    keywords = [KEYWORD_SYNONYMS.get(kw, kw) for kw in keywords]

    # Apply INGREDIENT_PARENTS: map specific forms to generic parents
    # e.g., "schalottenlök" → "lök", "vitlöksklyfta" → "vitlök"
    keywords = [INGREDIENT_PARENTS.get(kw, kw) for kw in keywords]

    # Fresh sausage wording should participate in the sausage family on the
    # ingredient side, but product-side matching keeps explicit färskkorv rows
    # on a narrow fresh-sausage subset.
    if any(kw in {'färskkorv', 'farskkorv', 'färskkorvar', 'farskkorvar'} for kw in keywords):
        keywords.append('korv')

    # Vinegar flavor suppression: when a vinegar keyword is present, drop standalone
    # fruit/flavor keywords — they describe the vinegar's flavor, not a separate ingredient.
    # e.g., "vinäger, gärna hallon" → keep 'vinäger', drop 'hallon' (avoid matching berries)
    # e.g., "Hallon Balsamvinäger" → keep 'balsamvinäger', drop 'hallon'
    if any(kw.endswith('vinäger') or kw.endswith('vinager') for kw in keywords):
        _VINEGAR_FLAVOR_WORDS = frozenset({
            'hallon', 'fikon', 'äpple', 'apple', 'ingefära', 'ingefara',
            'mango', 'tryffel', 'fläder', 'flader', 'körsbär', 'korsbar',
            'apelsin', 'granatäpple', 'granatapple', 'honung',
            # NOTE: 'citron' excluded — often appears as alternative "citron eller vinäger"
        })
        keywords = [kw for kw in keywords if kw not in _VINEGAR_FLAVOR_WORDS]

    # Remove duplicates while preserving order (dict.fromkeys is C-optimized)
    unique_keywords = list(dict.fromkeys(keywords))

    # Keyword suppression: when a specific stock keyword (hummerfond, kalvfond, etc.)
    # coexists with generic 'buljong' from the same ingredient line (e.g., "Hummerfond
    # Buljong"), suppress 'buljong' to prevent 13+ generic buljong products from matching.
    # The specific keyword already captures the intent; 'buljong' is just a category label.
    _SPECIFIC_STOCK_KEYWORDS = {'hummerfond', 'kalvfond', 'fiskfond', 'kycklingfond',
                                'grönsaksbuljong', 'gronsakbuljong', 'hönsbuljong',
                                'svampfond', 'skaldjursfond', 'kycklingbuljong',
                                'köttbuljong', 'kottbuljong', 'fiskbuljong'}
    if 'buljong' in unique_keywords:
        if any(kw in _SPECIFIC_STOCK_KEYWORDS for kw in unique_keywords):
            # Specific type present → suppress generic 'buljong'
            unique_keywords = [kw for kw in unique_keywords if kw != 'buljong']
        else:
            # No specific type → default generic 'buljong' to 'grönsaksbuljong'
            # Vegetable broth is a safe universal default; recipes that want a
            # specific type (kyckling/kött/fisk) should name it explicitly.
            unique_keywords = ['grönsaksbuljong' if kw == 'buljong' else kw
                               for kw in unique_keywords]

    # Safety net: if a single ingredient line produces too many keywords,
    # it's likely a product description or badly formatted text — drop all.
    if len(unique_keywords) > 5:
        return []

    return unique_keywords
