"""
Swedish product category utilities for store scrapers.

This module provides standardized product categorization based on Swedish
product names. All keywords are in Swedish since Swedish grocery stores
are the target market.

Located in languages/sv/ because the category keywords are language-specific.
If non-Swedish stores are added, a separate category module would be needed
for that language.

USAGE IN YOUR SCRAPER:
    from languages.sv.category_utils import guess_category

IMPORTED MEAT FILTERING (used by recipe_matcher and store scrapers):
    from languages.sv.category_utils import (
        IMPORTED_MEAT_BRANDS, IMPORTED_COUNTRIES,
        IMPORTED_SPECIALTY_EXCEPTIONS, MEAT_NAME_KEYWORDS
    )

Categories returned:
    - hygiene: Personal care, cosmetics, hair products
    - household: Cleaning, paper products, pet supplies, clothing
    - meat: Beef, pork, lamb, game (älg, vildsvin, etc.)
    - poultry: Chicken, turkey, duck
    - fish: Fish, shellfish, seafood
    - dairy: Milk, cheese, yogurt, cream, butter
    - deli: Cold cuts, sausages, bacon
    - fruit: Fruits, berries
    - vegetables: Vegetables, potatoes, herbs
    - bread: Bread, bakery items
    - beverages: Soft drinks, juice, water, energy drinks
    - candy: Candy, chips, snacks, chocolate
    - spices: Sauces, oils, condiments, spices
    - pizza: Pizza, ready-made pizza products
    - pantry: Pasta, rice, noodles, canned goods, pantry staples
    - frozen: Frozen foods (general)
    - other: Unclassified
"""

import re
from typing import List, Optional, Set

try:
    from languages.sv.food_filters import NUT_KEYWORDS, NOT_COOKING_NUTS
except ModuleNotFoundError:
    from app.languages.sv.food_filters import NUT_KEYWORDS, NOT_COOKING_NUTS


# ============================================================================
# IMPORTED MEAT FILTERING
# ============================================================================
# Centralized data for the "Endast svenskt kött" user preference.
# Used by recipe_matcher.py (at match time) and optionally by store scrapers
# (at scrape time as early filter).
#
# The filtering logic lives in recipe_matcher._get_filtered_offers() and
# respects the user's local_meat_only preference toggle.

# Country names in product names that indicate imported meat (Swedish)
IMPORTED_COUNTRIES: List[str] = [
    'brasilien', 'frankrike', 'nya zeeland', 'italien', 'spanien',
    'holland', 'polen', 'irland', 'tyskland', 'danmark', 'argentina',
    'uruguay', 'usa', 'australien', 'norge', 'storbritannien', 'uk',
]

# Known imported meat brands/producers (lowercase)
IMPORTED_MEAT_BRANDS: List[str] = [
    'danish crown',       # Denmark - major pork producer
    'affco',              # New Zealand - lamb/beef processor
    'theburgervault',     # Ireland - frozen beef burgers
    'the burger vault',   # Same as above, spaced variant
    'cesar nieto',        # Spain - Iberian pork (secreto, pluma)
]

# Specialty charcuterie that is inherently imported (no Swedish equivalent)
# These products ARE their country of origin — always allowed through
IMPORTED_SPECIALTY_EXCEPTIONS: List[str] = [
    'salsiccia', 'serrano', 'chorizo', 'prosciutto', 'coppa',
    'bresaola', 'salami', 'pepperoni', 'nduja', 'pancetta',
    'parma',
    # NOTE: iberico removed — Iberico Secreto/Pluma are meat cuts, not charcuterie.
    # They should be filtered by local_meat_only. Iberico charcuterie products
    # like "Rollitos Chorizo Iberico" are covered by 'chorizo' exception.
]

# Swedish meat keywords for detecting meat products by name
# Used when offer.category is 'other' but name suggests it's meat
MEAT_NAME_KEYWORDS: List[str] = [
    'stek', 'fläsk', 'kött', 'nöt', 'fågel', 'kyckling', 'kalkon',
    'bacon', 'korv', 'skinka', 'lamm', 'vilt', 'anka', 'gris',
    'entrecôte', 'entrecote',  # beef cut often categorized as 'other'
    'färs', 'blandfärs', 'nötfärs',  # minced meat (often category=other)
    'secreto', 'pluma',  # Iberian pork cuts (often category=frozen)
]

# Meat-related DB categories (English keys used in offers table)
MEAT_CATEGORIES: Set[str] = {'meat', 'poultry', 'deli'}

# Categories that may contain meat — checked with MEAT_NAME_KEYWORDS (same as 'other')
MEAT_EXTENDED_CATEGORIES: Set[str] = {'other', 'frozen'}


# ============================================================================
# LACTOSE-FREE DAIRY FILTERING
# ============================================================================
# When the user enables "exclude lactose", we skip dairy offers
# UNLESS the product is naturally lactose-free or explicitly labeled as such.
# Used by recipe_matcher.py at offer-filtering time.

# Explicit "laktosfri" labels — always trusted (manufacturer guarantee)
_EXPLICIT_LACTOSE_FREE: List[str] = ['laktosfri', 'laktosfritt']

# Naturally lactose-free hard/aged cheeses (< 0.01g/100g) + butter
_NATURALLY_LACTOSE_FREE: List[str] = [
    'västerbotten', 'vasterbotten',
    'prästost', 'prastost', 'präst', 'prast',
    'herrgård', 'herrgard',
    'grevé', 'greve',
    'parmesan', 'gouda', 'edamer', 'emmentaler',
    'cheddar', 'manchego', 'pecorino',
    'gruyère', 'gruyere',
    'havarti',
    'hårdost', 'hardost',
    'lagrad ost',
    'smör', 'smor',
]

# Dairy base products that contain lactose — if present, only explicit
# "laktosfri" labels can override (not cheese-name keywords which may
# just be a flavoring, e.g. "Crème Fraiche Parmesan")
_LACTOSE_CONTAINING_BASES: List[str] = [
    'yoghurt', 'yogurt', 'fil', 'filmjölk', 'mjölk', 'mjolk',
    'grädde', 'gradde', 'gräddfil', 'graddfil',
    'crème fraiche', 'creme fraiche', 'créme fraiche',
    'glass', 'gelato', 'kvarg', 'kefir', 'keso',
]

_BUTTER_COMPOUND_BLOCKERS = {'gås', 'gas'}  # smörgås ≠ smör (butter)


def _build_pattern(keywords, butter_lookahead=False):
    """Build pre-compiled regex with word-START boundary only.

    No trailing \\b to handle Swedish compounds (e.g. Västerbottensost).
    """
    sorted_kw = sorted(set(keywords), key=len, reverse=True)
    parts = []
    for kw in sorted_kw:
        escaped = re.escape(kw)
        if butter_lookahead and kw in ('smör', 'smor'):
            blockers = '|'.join(re.escape(b) for b in _BUTTER_COMPOUND_BLOCKERS)
            parts.append(r'\b' + escaped + r'(?!' + blockers + r')')
        else:
            parts.append(r'\b' + escaped)
    return re.compile('(' + '|'.join(parts) + ')', re.IGNORECASE)


_EXPLICIT_PATTERN = _build_pattern(_EXPLICIT_LACTOSE_FREE)
_NATURAL_PATTERN = _build_pattern(_NATURALLY_LACTOSE_FREE, butter_lookahead=True)
_LACTOSE_BASE_PATTERN = _build_pattern(_LACTOSE_CONTAINING_BASES)


def is_lactose_free(product_name: str) -> bool:
    """Check if a dairy product is lactose-free based on its name.

    Two-level check:
    1. Explicit "laktosfri"/"laktosfritt" → always allow (manufacturer label)
    2. Naturally lactose-free keywords (hard cheeses, butter) → allow ONLY if
       the product doesn't also contain a lactose-containing base (yoghurt,
       crème fraiche etc.), which would mean the cheese name is just a flavor.
    """
    if _EXPLICIT_PATTERN.search(product_name):
        return True
    if _NATURAL_PATTERN.search(product_name):
        # Don't trust cheese names if the product is a lactose-containing base
        # e.g. "Crème Fraiche Parmesan" — parmesan is just a flavor here
        if _LACTOSE_BASE_PATTERN.search(product_name):
            return False
        return True
    return False


def guess_category(product_name: str, api_category: Optional[str] = None) -> str:
    """
    Guess product category from name (and optionally API-provided category).

    The function checks categories in a specific ORDER to handle keyword
    collisions:
    - hygiene BEFORE dairy (prevents "booster" matching "ost")
    - meat BEFORE beverages (prevents "fläsk" matching "läsk")

    Args:
        product_name: Product name to categorize
        api_category: Optional category from store API (used as hint)

    Returns:
        Category string (e.g., "meat", "dairy", "household")

    Examples:
        >>> guess_category("Fläskfärs 500g")
        'meat'
        >>> guess_category("Growth Booster Schampo")
        'hygiene'
        >>> guess_category("Toalettpapper 18-pack")
        'household'
    """
    # First try API category if provided
    if api_category:
        category = normalize_api_category(api_category)
        if category == "other":
            category = _guess_from_name(product_name)
    else:
        category = _guess_from_name(product_name)

    # Post-classification: reclassify misplaced items based on product name
    return _reclassify(product_name, category)


# --- Post-classification reclassification ---
# Fixes products that end up in the wrong category due to broad API categories.
# E.g., store API puts all "Godis & Snacks" together, but plain cooking nuts ≠ candy.
# NUT_KEYWORDS and NOT_COOKING_NUTS imported from food_filters.py

_NOT_COOKING_ICE_CREAM = (
    # Novelty formats (pinnar, strutar, båtar)
    'glasspinne', 'glasspinnar', 'glasstrut', 'glasstrutar', 'glassbåt',
    'strut ', 'pinne ', 'pinnar ',
    # Multi-packs and portion formats
    'flerpack', 'minicups', 'partypinnar', 'mixbox', '-pack',
    # Sandwich ice cream
    'sandwich',
    # Protein/diet
    'proteinglass', 'proteinbar',
    # Novelty/brand names
    '88', 'piggelin', 'nogger', 'solero', 'snickers', 'magnum',
    'sitting bull', 'pippi', 'spinner', 'tip top', 'cornetto',
    'viennetta', 'push up', 'haribo', 'tuttifrutti',
    # Fancy flavors (not plain ice cream)
    'cookie dough', 'brownie', 'rocky road', 'peanut butter',
    'cheesecake', 'banoffee', 'caramel sutra', 'billionaire',
    'cookies&cream', 'cookies cream',
    # Novelty compound flavors
    'pecan', 'brittle', 'brookies', 'sundae',
    'krumelur', 'chokladbomb', 'chokladkross',
    'split',  # "Banana Split", "Ananas Split", "Päronsplitt"
    'after dinner', 'tresmak', 'klassiker',
    'himmelsk röra', 'himmelsk rora',
    'mango memories', 'smooth caramel', 'smooth vanilla',
    'strawberries', 'nougat swirl', 'sea salt caramel',
    'karamel sutra', 'karamell sutra',
    'kladdkaka', 'mandelkrokant', 'mango & raspberry',
    'kaffe böna', 'kaffe bona',  # Ben & Jerry's "Kaffe Böna"
)


def _reclassify(product_name: str, category: str) -> str:
    """
    Reclassify products that ended up in the wrong category.

    Called after initial classification. Currently handles:
    - Plain cooking nuts in candy → pantry
    - Plain ice cream in candy → frozen (recipes use vaniljglass etc.)
    """
    if category == 'candy':
        name_lower = product_name.lower()
        # Plain nuts used in cooking should be pantry, not candy
        if any(n in name_lower for n in NUT_KEYWORDS):
            if not any(c in name_lower for c in NOT_COOKING_NUTS):
                return 'pantry'

        # Plain ice cream for recipes (vaniljglass, gräddglass, etc.) → frozen
        if 'glass' in name_lower:
            if not any(n in name_lower for n in _NOT_COOKING_ICE_CREAM):
                return 'frozen'

    # Finished/ready pizzas in 'pizza' category → frozen (not recipe ingredients)
    if category == 'pizza':
        name_lower = product_name.lower()
        # Non-food items in pizza category
        if any(kw in name_lower for kw in ('badmadrass', 'kortspel', 'taco cat')):
            return 'household'
        # Finished pizzas → frozen (blocked by PROCESSED_FOODS)
        if any(kw in name_lower for kw in ('max snack', 'pinsa')):
            return 'frozen'
        # Cheetos/snacks → candy
        if 'cheetos' in name_lower:
            return 'candy'

    # Sättpotatis (seed potatoes for planting) → household
    if category == 'vegetables':
        name_lower = product_name.lower()
        if 'sättpotatis' in name_lower:
            return 'household'

    # Cheetos/Ostbågar snacks misclassified as dairy → candy
    if category == 'dairy':
        name_lower = product_name.lower()
        if any(kw in name_lower for kw in ('cheetos', 'ostbågar')):
            return 'candy'

    # Non-food items misclassified as food categories (Easter decorations, hygiene)
    name_lower = product_name.lower()
    _DECORATION_KEYWORDS = ('chenillekyckling', 'äggjaktsägg', 'hänge ägg', 'krans med ägg')
    if any(kw in name_lower for kw in _DECORATION_KEYWORDS):
        return 'household'
    _HYGIENE_KEYWORDS = ('skäggfärg', 'skaggfarg')
    if any(kw in name_lower for kw in _HYGIENE_KEYWORDS):
        return 'hygiene'

    # Food products misclassified as beverages (e.g., ICA puts some pantry items
    # under "dryck" navigation). Reclassify to pantry based on product name.
    if category == 'beverages':
        name_lower = product_name.lower()
        _BEVERAGES_TO_PANTRY_KEYWORDS = (
            'gnocco', 'gnocchi', 'pasta ', 'nudlar',
            'flingor', 'müsli', 'musli', 'granola', 'müslibar',
            'gryn', 'bulgur', 'couscous', 'quinoa',
            'basmati', 'jasminris',
            'mjöl ',  # trailing space to avoid 'mjölk'
            'honung',
            'vinäger',
            'sylt ', 'marmelad',
            'bakpulver', 'bikarbonat',
            'bönor', 'linser', 'kikärtor',
            'krydda',  # "Chai Latte Krydda" — spice product
        )
        if any(kw in name_lower for kw in _BEVERAGES_TO_PANTRY_KEYWORDS):
            return 'pantry'

    return category


def normalize_api_category(raw_category: str) -> str:
    """
    Normalize API-provided category string to standard category.

    Used when store APIs provide their own category classification.
    More reliable than name guessing when available.

    Args:
        raw_category: Category string from store API (e.g., "Kött & Chark")

    Returns:
        Normalized category string
    """
    raw_lower = raw_category.lower()

    # Prefix check for categories that collide as substrings
    # "djur|kattmat" starts with "djur" but "skaldjur|fisk" contains "djur" too
    if raw_lower.startswith("djur"):
        return "household"

    # Order matters:
    # 1. Hygiene FIRST (before dairy to prevent collisions)
    # 2. Household BEFORE candy (so "barn|barnsnacks" matches "barn" → household,
    #    not "snacks" → candy. All barn items are non-food)
    # ASCII Swedish variants (skonhet, hushall, kott) added for Hemköp/Axfood APIs
    category_mapping = {
        "hygiene": [
            "hygien", "hygiene", "kosmetik", "personal care",
            "skönhet", "skonhet", "hårvård", "harvard",
            "halsa-och-skonhet", "apotek", "lakemedel",
        ],
        "household": [
            "hushåll", "hushall", "household", "städ", "stad",
            "hem-och-hushall", "blommor", "barn",
        ],
        "meat": ["kött", "kott", "meat", "nöt", "fläsk", "lamm", "kalv", "gris"],
        "poultry": ["fågel", "fagel", "kyckling", "kalkon", "anka", "poultry"],
        "fish": ["fisk", "skaldjur", "seafood", "fish"],
        "dairy": ["mejeri", "dairy", "mjölk", "yoghurt", "grädde", "smör", "ost-och-agg"],
        "deli": ["chark", "skinka", "korv", "salami", "palagg"],
        "fruit": ["frukt", "fruit", "bär", "berry"],
        "vegetables": ["grönsaker", "gronsaker", "vegetables", "sallad", "rotfrukter", "gront"],
        "bread": ["bröd", "brod", "bread", "bakery", "bakverk"],
        "beverages": ["dryck", "beverage", "läsk", "juice", "vatten"],
        "candy": ["godis", "candy", "choklad", "snacks"],
        "frozen": ["fryst", "frozen"],
        "pantry": ["skafferi"],
    }

    for our_category, keywords in category_mapping.items():
        if any(keyword in raw_lower for keyword in keywords):
            return our_category

    return "other"


def _guess_from_name(product_name: str) -> str:
    """
    Guess category from product name using keyword matching.

    ORDER MATTERS! Categories are checked in specific order to handle
    keyword collisions:
    - hygiene first (catches "booster" before dairy's "ost")
    - meat early (catches "fläsk" before beverages' "läsk")
    - household catches non-food items

    Args:
        product_name: Product name to categorize

    Returns:
        Category string
    """
    name_lower = product_name.lower()

    # Expanded category mapping - ORDER MATTERS!
    categories = {
        # Check hygiene FIRST - prevents "booster" matching "ost" in dairy
        "hygiene": [
            "schampo", "shampoo", "balsam", "hårvård", "harvard", "serum",
            "inpackning", "booster",  # Hair booster products
            "tissues", "näsdukar", "nasdukar", "tandkräm", "tandkram",
            "deodorant", "handtvål", "handtval", "duschcreme",
            "eye make up", "handcreme", "moisturiser", "face wash", "body lotion",
            "munsk", "plax", "tvål", "tval", "dusch", "rakhyvel", "kroppsvård", "kroppsvard",
            "ansiktskräm", "ansiktstvätt", "ansiktsvård", "rakvård", "munvård",
            "ansiktskram", "ansiktsrengoring", "ansiktmask", "ansiktsmask",  # ASCII variants
            "pastiller", "duschgel", "hudvård", "hudvard",
            # Feminine hygiene
            "tamponger", "tampong", "bindor", "trosskydd", "nattbinda",
            # Baby/personal wipes
            "våtservetter", "vatservetter", "tvattservetter",
            # Shaving
            "rakgel", "rakskum",
            # Skin care
            "pimple patch", "hydrocolloid", "intimtvatt", "intimtvätt",
            # Dental
            "tandtråd", "tandtrad",
        ],
        # Check household early to catch non-food items
        "household": [
            # Cleaning & laundry - with ASCII variants
            "diskmedel", "tvättmedel", "tvattmedel", "sköljmedel", "skoljmedel",
            "handdisk", "städ", "maskindisk",
            "toalettrengöring", "toalettrengoring", "allrengöring", "allrengoring",
            "rengöring", "rengoring", "rengöringssprey", "badrumsrengoring",
            "fläckborttagning", "flackborttagning", "vanish",
            "kulortvatt", "kulörtvätt",
            # Kitchen non-food items
            "fryspåsar", "fryspasar", "plastfolie", "aluminiumfolie", "folie", "toppits",
            "bakplåtspapper", "hushållspapper", "matlåda", "matlada", "matförvaring", "matforvaring",
            "diskborste",
            "mugg",  # Cups/mugs
            "skål",  # Bowls (no food collision - "skaldjur" has 'a' not 'å')
            "stekpanna", "ugnsform", "muffinsform",
            "skärbräda", "skarbrada",
            "köksredskap", "koksredskap",
            "slickepott", "snurrbricka",
            "sugrör", "sugror",  # Drinking straws
            "lunchlåda", "lunchlada",
            # Storage & organization
            "förvaringsburk", "forvaringsburk",
            "förvaringsväska", "forvaringsvaska",
            "galge",  # Hangers
            "påskläm",  # Bag clips (catches påsklämmor)
            # Paper products
            "toalettpapper", "toapapper", "serla", "lambi",
            "servetter", "servett",
            # Bags & waste
            "avfallspåse", "avfallspase", "sopåse", "sopase", "soppåsar",
            "blöjor", "blojor", "bajspåsar", "bajspasar",
            # Clothing & misc
            "strumpor", "strumpa", "socka", "socks",
            "vante", "vantar", "resekudde",
            "klädvårdsrulle", "kladvardsrulle",
            "skinnhandske",
            # Party & decor
            "isfackla", "isfacklor", "serpentin", "champagneglas",
            "tulpan", "rosor", "bukett", "blommor", "orkidé", "hortensia",  # "rosor" not "ros" - avoids "gyros" collision
            "hårfärg", "harfarg", "partypoppers",
            "ballonger", "ljusslinga",
            # Candles - "flamme" catches LED Flamme candles before "lamm" (lamb) collision
            "värmeljus", "varmeljus", "stearinljus", "kronljus", "antikljus", "flamme",
            "julgranskulor",
            # Pet supplies
            "hundmat", "kattmat", "djurmat",
            "hundgodis", "kattgodis",  # Pet treats
            # Vacuum & appliances
            "dammsug",  # Catches dammsugare, dammsugarpåse, dammsugpåse
            "popcornmaskin",
            # Misc household
            "glasogonputs", "glasögonputs",
            "korkunderlagg", "glasunderlagg", "underlägg",
            "termosmugg", "led lampor", "led tv",
            "högtalare", "hogtalare",
            "sminkspegel",
            "tändkub", "tandkub",  # Firelighters
            # Toys & crafts (non-food)
            "målarbok", "malarbok", "godnattsagor", "nintendo", "måla med",
            "ögonmask", "ogonmask",
            "lego", "yogaboll", "squishmallows",
            "pyss",  # Catches pyssel, pyssla, pysselbok, pysselböcker
            "charader",
            "tygbok",
            # Stationery (non-food)
            "fotbollskort",
            "klistermärk",  # Catches klistermärken
            "anteckningsbok",
            "pennfodral",
            "spiralblock",
            "gummibandsmapp",
            "suddgummi",
            "tuschpenna",
        ],
        # Check meat early - "fläsk/flask" must be caught before beverages "läsk"
        "meat": [
            "fläsk", "flask",  # Generic pork - catches fläskfärs, sidfläsk, etc.
            "oxfilé", "oxfile", "fläskfilé", "fläskfile", "flaskfile",
            "entrecote", "ryggbiff", "biff", "nötfärs", "fläskfärs", "köttfärs",
            "flaskfars", "sidfläsk", "sidflask",  # Explicit variants
            "lamm", "lammfile", "lammstek", "oxpytt", "kalv", "innanlår",
            "högrev", "hogrev", "fransyska", "griskött", "grisrack",
            # Wild game
            "älgfärs", "algfars", "vildsvinsfärs", "vildsvinfars",
            "vildsvin", "hjort", "rådjur", "viltkött", "viltfärs",
            # Italian sausage mince
            "salsiccia",
            # Greek/kebab style
            "gyros",
            # Additional cuts
            "kotlett", "revbensspjäll", "revbensspjall",
            "renskav",  # Reindeer
            "köttbull", "kottbull",  # Meatballs
        ],
        "poultry": [
            "kyckling", "kycklingfile", "majskyckling", "höns", "kalkon",
            "minikalkon", "ankbrost", "anka", "höna", "ankbröst",
            "drumstick", "kycklingklubba"  # Chicken drumsticks
        ],
        "fish": [
            "lax", "torsk", "torskrygg", "räkor", "rakor", "räka", "raka",
            "hummer", "skaldjur", "fisk", "skagenrora", "rom", "havskraftor",
            "nuggets", "röd rom", "rod rom"
        ],
        "dairy": [
            "mjölk", "mellanmjolk", "fil", "yoghurt", "turkisk yoghurt",
            "grädde", "vispgradde", "graddfil", "gelato",
            "smör", "smor", "mellan smor",
            # Specific cheese names (NOT generic "ost" - causes "booster" collision)
            "fetaost", "mozzarella", "brie", "gorgonzola", "västerbotten",
            "prast", "präst", "havarti", "cambozola", "burrata", "gräddost",
            "crème fraîche", "gyllen", "bavaria", "quattrocento", "herrgård",
            "grevé", "cheesedip", "ostbricka", "cheese selection", "lagrad ost",
            "cheddar", "parmesan", "gouda", "edamer", "emmentaler",
            # Dairy products
            "kvarg",
            "halloumi",
            "hårdost", "hardost",
            # Cheese brands/series
            "familjefavoriter",  # Arla cheese series
            "vänerost", "vanerost",
            "port salut",
            "castello",
        ],
        "deli": [
            "skink",  # Catches skinka, skinkschnitzel, skinkor
            "korv", "salami", "bacon", "falukorv", "prosciutto",
            "serrano", "cabanos", "fuet", "chorizo", "skivade delikatesser",
            "bratwurst",
            "oumph",  # Plant-based meat alternatives
            "kebab",  # Kebab meat/vegan products
        ],
        # Frozen BEFORE fruit — "Glass Jordgubb" should be frozen, not fruit
        "frozen": [
            "fryst", "frysta", "frozen", "vårrullar",
            "glass", "gräddglass", "graddglass",  # ice cream
        ],
        # Sparkling water BEFORE fruit — "Vatten Kolsyrad Citron" must not match fruit's "citron"
        "beverages": [
            # NOTE: "lask" removed - collides with "flask" (pork)
            "läsk", "juice", "vatten kolsyrad", "kolsyrad", "vatten",
            "cola", "fanta", "sprite",
            "pepsi", "crush", "red bull", "energidryck", "tonic", "havredryck",
            "blanddryck", "ikaffe", "drinkmix", "lightdryck", "sodavatten",
            "snabbkaffe", "kaffekapslar",
            "kaffe",  # Catches kaffebönor, kaffekapsel, etc.
            "ristretto",  # L'Or coffee capsules
        ],
        "fruit": [
            "äpple", "apple", "banan", "apelsin", "päron", "paron", "druv",
            "melon", "honungsmelon", "clementin", "mango", "lime", "kiwi",
            "blåbär", "blabar", "persimon", "passionsfrukt", "avokado", "citron",
            "jordgubb",  # Catches jordgubbar, jordgubbe
        ],
        "vegetables": [
            "potatis", "tomat", "gurka", "sallad", "morot", "broccoli", "paprika",
            "lök", "lok", "schalotten", "sparris", "fankal", "fänkål", "sotpotatis",
            "spetskal", "spetskål", "persiljerot", "polkabeta", "polkabetor",
            "salladslok", "persilja", "majs", "jordärtskocka", "jordärtskockor",
            "ekologiska",
            # Kale & greens
            "grönkål", "gronkal",
            "svartkål", "svartkal",
            # Plural carrots (morot doesn't match morötter due to ö vs o)
            "morötter", "morotter",
            # Vegetable mixes
            "kronmix",
            "grönsaker", "gronsaker",  # Generic "vegetables"
        ],
        "bread": [
            "bröd", "limpa", "fralla", "ostfralla", "bulle", "toscabulle",
            "skogaholm", "baguette", "levainbrod", "levainbröd", "bladdeg",
            "pizzadeg", "tortilla", "roast", "toast", "vetekaka", "rågkaka",
            "panini", "ciabatta",
            "mazarin",  # Catches mazariner
            "hönökaka", "honokaka",
            "himla go",  # Pågen bread
            "rågbit", "ragbit",  # Rye bread pieces
            "chia god",  # Hatting bread
        ],
        "candy": [
            "godis", "chips", "snacks", "choklad", "nougat", "gott", "blandat",
            "tuggummi", "daim", "marshmallow", "tuc", "pinnar", "havssalt",
            "donuts", "wafer", "cornflakes",
            "halstabletter", "läkerol", "lakerol",  # Throat lozenges
            "ahlgrens",  # Ahlgrens Bilar candy
            "pralin",  # Pralines/chocolate
            "popcorn",  # Popcorn snacks (popcornmaskin → household first)
        ],
        "spices": [
            "pesto", "aioli", "bearnaise", "tacosas", "dippmix", "olivolja",
            "vitlok", "oliver", "jalapeno", "jalapeño", "chili mayo", "taco spice",
            "tacokryddmix", "fond", "kylda såser", "salsa", "mayo", "färska kryddor",
            "matolja", "sesamolja", "japansk soja", "sojasås",
            "ostronsås", "ostronsas",  # oyster sauce
            "woksås", "woksas",  # wok sauce
            "teriyaki",  # teriyaki sauce
            "sriracha",  # hot sauce
            "risvinäger", "risvinager",  # rice vinegar
            "chiliolja",  # chili oil
        ],
        "pizza": [
            "pizza", "pinsa", "pizzakit", "pizzasas", "kebab x tra allt"
        ],
        # Pantry items - pasta, rice, noodles, cereals, flour, baking, staples
        "pantry": [
            "pasta", "spaghetti", "penne", "fusilli", "rigatoni", "tagliatelle",
            "glasnudlar", "risnudlar", "nudlar",
            "jasminris", "basmatiris", " ris ", "fullkornsris", "boil in bag",
            "arborioris", "avorioris",  # risotto rice variants
            "soppa", "buljong",
            # Additional pasta shapes
            "rigatini", "tortiglioni", "mezze maniche", "radiatori",
            # Cereals & breakfast
            "cheerios", "nesquik", "flingor",
            "müsli", "musli", "granola",
            "havregryn", "gryn",  # fiberhavregryn, bulgurgryn, etc.
            # Flour & baking (safe: dairy catches "mjölk" before pantry)
            "vetemjöl", "vetemjol",
            "mjöl",  # dinkelmjöl, rågmjöl, mandelmjöl, majsmjöl, mjölmix, etc.
            "bakpulver", "bikarbonat",
            "mandelmassa", "marsipan",
            "jäst",  # Kronjäst, jäst för söta degar
            # Sugar
            "strösocker", "florsocker", "farinsocker", "vaniljsocker",
            "pärlsocker", "sockermassa",
            # Honey & syrups
            "honung",
            "sirap",  # agavesirap, dadelsirap, brödsirap, lönnsirap
            # Jam & preserves
            "sylt",  # hallonsylt, jordgubbssylt
            "marmelad",  # aprikosmarmelad, citrusmarmelad
            # Grains & legumes
            "bulgur", "couscous", "quinoa", "bovete",
            "bönor", "bonor",
            "linser",
            "kikärtor", "kikartor",
            # Rice snacks
            "riskakor",
            "rismål", "rismal",
            # Asian staples
            "risark",  # rice paper for spring rolls
            "agar agar",
            # Plant-based protein
            "tofu",
            # Pasta sauce/ready meal brands
            "lasagne", "dolmio",
        ]
    }

    # Substring collision overrides: keyword matches that should NOT trigger a category
    # when certain food-related words are also present in the product name
    _category_overrides = {
        # "balsam" (hygiene) collides with balsamico/balsamvinäger (food)
        ("hygiene", "balsam"): ("vinäger", "vinager", "balsamico", "balsamica", "glassa"),
        # "glass" (frozen/ice cream) collides with "glassa balsamica" (condiment)
        # and "glass noodle(s)" (pantry)
        ("frozen", "glass"): ("glassa", "glass noodle"),
    }

    # Check each category
    for category, keywords in categories.items():
        if any(keyword in name_lower for keyword in keywords):
            # Check if a substring override should skip this category
            for (ovr_cat, ovr_kw), food_indicators in _category_overrides.items():
                if category == ovr_cat and ovr_kw in name_lower:
                    if any(ind in name_lower for ind in food_indicators):
                        break  # triggers the for/else → skip return
            else:
                return category
            continue  # override matched → skip this category

    return "other"


# Convenience function for quick checks
def is_food_category(category: str) -> bool:
    """
    Check if category represents food items.

    Used to filter out non-food from recipe matching/generation.

    Args:
        category: Category string

    Returns:
        True if the category is a food category
    """
    non_food = {"hygiene", "household", "other"}
    return category not in non_food


# ============================================================================
# BRAND-BASED CATEGORY OVERRIDES
# ============================================================================
# Some brands ONLY produce non-ingredient products (dessert cups, ready meals,
# baby food, smart home, etc.). Override their category so they get excluded
# from recipe matching regardless of what the name-based guesser thinks.
#
# Called from db_saver.py when saving offers to DB.

BRAND_CATEGORY_OVERRIDES = {
    # Dessert cups / snack products → candy (excluded from recipe matching)
    'risifrutti': 'candy',
    'mannafrutti': 'candy',
    # Ready meals → candy (not recipe ingredients)
    'gooh': 'candy',
    'kitchen joy': 'candy',
    # Baby food → candy
    'lovemade': 'candy',
    # Snack bars → candy
    'corny': 'candy',
    # Instant noodles (ready meals) → candy
    'mama': 'candy',
    # Electronics / smart home → household
    'philips': 'household',
    # Reflectors / safety gear → household
    'rfx': 'household',
    # Batteries → household
    'energizer': 'household',
    # Kitchen equipment → household
    'pyrex': 'household',
}

# Characters to strip from brand names before lookup (®, ™, etc.)
_BRAND_CLEAN_RE = re.compile(r'[®™©]')


def override_category_by_brand(category: str, brand: Optional[str]) -> str:
    """
    Override product category based on brand name.

    Brands that exclusively produce non-ingredient products (dessert cups,
    ready meals, electronics, etc.) are remapped to excluded categories
    so they don't pollute recipe matching.

    Args:
        category: Current category from guess_category()
        brand: Brand/manufacturer name from store API

    Returns:
        Overridden category, or original if no override applies
    """
    if not brand:
        return category
    clean = _BRAND_CLEAN_RE.sub('', brand).lower().strip()
    return BRAND_CATEGORY_OVERRIDES.get(clean, category)
