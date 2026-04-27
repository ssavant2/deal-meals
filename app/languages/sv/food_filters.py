# -*- coding: utf-8 -*-
"""
Swedish Food Filter Keywords

Used by StorePlugin._filter_food_items() to separate food from non-food products.
Only needed for stores with mixed inventories (ICA, Coop). Stores that sell
mostly food (Willys, Mathem) typically don't need filtering.

For a non-Swedish store, create a matching file in the appropriate language
folder (e.g., languages/de/food_filters.py) and override the class attributes
in your store subclass:

    from languages.de.food_filters import (
        FOOD_CATEGORIES, NON_FOOD_CATEGORIES, FOOD_INDICATORS,
        NON_FOOD_STRONG, NON_FOOD_INDICATORS, CERTIFICATION_LOGOS
    )

    class LidlStore(StorePlugin):
        FOOD_CATEGORIES = FOOD_CATEGORIES
        NON_FOOD_STRONG = NON_FOOD_STRONG
        ...

Note on compound words:
    Swedish uses compound words, e.g. "ostbricka" (cheese board).
    The filter checks FOOD_INDICATORS first, so "ost" matches before "bricka".
    This means "ostbricka" → kept as food, "plastbricka" → filtered out.
"""

# =============================================================================
# FOOD CATEGORIES - Category strings that indicate food
# =============================================================================
# Both Swedish (raw from store APIs) and English (normalized by category_utils).
# ASCII variants (halsa, skonhet) for Hemköp/Axfood APIs without å/ä/ö.
FOOD_CATEGORIES = {
    "semlor", "frukt", "grönt", "kött", "fisk", "skaldjur", "mejeri", "ost",
    "bröd", "vegetariskt", "färdigmat", "glass", "godis", "snacks", "dryck",
    "skafferi", "fryst", "chark", "pålägg", "juice", "läsk", "vatten", "kaffe",
    "te", "müsli", "flingor", "pasta", "ris", "konserv", "sås", "kryddor",
    "bakning", "sylt", "honung", "nötter", "torkad frukt",
    # English (from normalize_api_category)
    "meat", "poultry", "fish", "dairy", "deli", "fruit", "vegetables",
    "bread", "beverages", "candy", "frozen", "pantry", "spices", "pizza",
}

# =============================================================================
# NON-FOOD CATEGORIES - Category strings that indicate non-food
# =============================================================================
NON_FOOD_CATEGORIES = {
    "apotek", "hälsa", "halsa", "träning", "städ", "tvätt", "papper",
    "kök", "hem", "fritid", "blommor", "kläder", "husdjur",
    "elektronik", "trädgård", "verktyg", "böcker", "leksaker",
    "hygien", "skönhet", "skonhet",
    # English (from normalize_api_category)
    "hygiene", "household",
}

# =============================================================================
# FOOD INDICATORS - Words in product names that suggest food
# =============================================================================
FOOD_INDICATORS = [
    # Weight/volume units
    "kg", "g ", "ml", "liter", "cl", "dl",
    # Organic labels
    "ekologisk", "eko ", "krav",
    # Preparation methods
    "färsk", "rökt", "grillad", "kokt", "stekt",
    # Meat
    "filé", "biff", "korv", "skinka", "bacon", "fläsk", "kyckling", "nöt",
    # Fish & seafood
    "lax", "torsk", "sill", "räkor", "fisk",
    # Dairy
    "mjölk", "yoghurt", "ost", "smör", "grädde", "kvarg", "filmjölk", "margarin",
    # Bakery
    "bröd", "bulle", "kaka", "tårta", "semlor",
    # Produce
    "äpple", "banan", "tomat", "potatis", "lök", "gurka", "paprika", "morot",
    # Drinks
    "juice", "läsk", "vatten", "kaffe", "te ", "dryck",
    # Snacks
    "chips", "godis", "choklad", "glass", "müsli", "flingor", "mellanmål", "risifrutti",
    # Pantry
    "pasta", "ris", "sås", "ketchup", "senap", "majonäs", "aioli", "dressing",
    # Baking
    "sylt", "marmelad", "honung", "socker", "mjöl",
    # Deli
    "oliver", "kapris", "pesto", "hummus",
]

# =============================================================================
# CERTIFICATION LOGOS - Scraping artifacts (badge names, not real products)
# =============================================================================
CERTIFICATION_LOGOS = {
    "nyckelhålet", "rainforest alliance", "producerad i sverige", "svanen-märket",
    "svanen", "eu lövet", "eu-lövet", "eu ekologiskt", "krav-märkt", "krav märkt",
    "fsc", "fsc för hållbart skogsbruk", "msc", "asc", "fairtrade",
    "bra miljöval", "från sverige", "svenskt sigill",
}

# =============================================================================
# NON-FOOD STRONG - Product types that are NEVER food (checked FIRST)
# =============================================================================
# These often have "ml" or "g" in the name but are NOT food.
# Must be checked before FOOD_INDICATORS to catch "handtvål 500ml" etc.
NON_FOOD_STRONG = [
    # Hair care
    "schampo", "balsam", "hårvård", "hårfärg", "hårspray", "hårtoning", "intensivtoning",
    # Body care
    "tvål", "handtvål", "duschtvål", "duschkräm", "duschgel",
    # Face care
    "dagkräm", "nattkräm", "ansiktskräm", "kroppskräm", "hudkräm", "ögonkräm",
    "ansiktsserum", "bodylotion", "hudlotion",
    # Makeup
    "mascara", "läppstift", "smink", "makeup", "foundation", "bronzing",
    "concealer", "puder", "rouge", "eyeliner", "ögonskugga", "ögonbrynspenna",
    # Hygiene
    "deodorant", "parfym", "tandkräm", "tandborste", "munskölj",
    "rakblad", "rakhyvel", "aftershave",
    "binda", "bindor", "blöja", "blöjor", "byxblöja",
    # Brands that are NEVER food
    "maybelline", "loreal", "l'oréal", "l'oreal", "elvital", "garnier",
    "mywear",  # ICA clothing brand
    # Cleaning products (also often have "ml")
    "diskmedel", "tvättmedel", "sköljmedel", "rengöring", "allrengöring",
    "fönsterputs", "avkalkare",
    # Pet products
    "kattsnacks", "kattmat", "hundmat", "hundsnacks", "djurfoder",
    "dentastix", "pedigree",
    # Household items with food-like units
    "diskduk", "diskhandduk", "kökshandduk",
]

# =============================================================================
# NON-FOOD INDICATORS - Generic items (checked AFTER food indicators)
# =============================================================================
# Checked last so that "ostbricka" matches "ost" first.
NON_FOOD_INDICATORS = [
    # Household paper
    "toalettpapper", "hushållspapper", "servett", "näsduk",
    "tvättlapp", "disktrasa", "diskborste",
    # Candles & lighting
    "batterier", "batteri", "glödlampa", "lampa",
    "tändstickor", "värmeljus", "blockljus", "antikljus", "kronljus",
    # Kitchen appliances & items (not food)
    "stekpanna", "kastrull", "gryta", "bunke", "skål", "bricka", "fat",
    "gaffel", "sked", "sleev", "slev",
    "tallrik", "mugg", "kopp", "bestick", "köksredskap",
    "brödrost", "kaffebryggare", "vattenkokare", "dammsugare",
    "förvaringsburk", "förvaring", "matförvaring",
    "termos", "ståltermos", "termosmugg", "vattenflaska",
    # Toys, books & brands
    "leksak", "mjukis", "docka", "pussel", "spel", "lego",
    "bok ", " bok", "målarbok", "pysselbok", "sagobok", "kokbok", "godnattsagor",
    "tidning", "anteckningsbok", "kalender",
    "disney", "frozen", "frost",
    # Tools & crafts
    "verktyg", "skruv", "tejp", "lim",
    # Garden & plants
    "blomma", "växt", "kruka", "jord",
    # Clothing
    "kläd", "strumpa", "socka", "socks", "trosa", "bh ", "underkläder", "boxer", "vante", "vantar",
    "pyjamas", "pyjamasbyxa", "pyjamastopp",
    "raggsocka", "thermosocka", "hiddensocka", "knästrumpa",
    # Electronics
    "hörlurar", "usb", "kabel", "elektronik",
    # Gift & packaging
    "presentpapper", "kort ", "påse",
]

# =============================================================================
# NON-FOOD BRANDS - Brands whose products should never match recipes
# =============================================================================
# Checked against offer.brand (case-insensitive) in the recipe matcher pre-filter.
# These brands sell ONLY non-food products that should never match cooking recipes.
NON_FOOD_BRANDS: set = {
    'friggs',              # tea, rice cakes, supplements
    'magnum',              # ice cream — not recipe-relevant
    'risifrutti',          # rice pudding snack cups
    'yalla',               # flavored dairy drinks
    'sunshine delig',      # dried fruit snacks
    'sunshine delight',    # alternate spelling
    'semper',              # baby food — välling, barnmat, modersmjölksersättning
    'alex&phil',           # baby food — barnmat, smoothies, gröt

    # Ready meal / deli brands (complete dishes/tapas, not individual ingredients)
    'topsfoods pure',      # "Kyckling Red Curry med Ris" — ready meals only
    'ridderheims',         # marinerade oliver, tapas, ölkorv, creme — not recipe ingredients

    # Candy brands (ONLY make candy — no cooking ingredients)
    # NOT blocked: Fazer (bakchoklad/bröd), Ferrero (Nutella), Cloetta (mandelbiskvier),
    #              Marabou (used in baking), Lindt (Excellence in baking), Treatville (nötmix)
    'haribo', 'malaco', 'anthon berg', 'toms', 'wellibites', 'tweek', 'fluffyz',
    'steenland chocolate', 'swizzels', 'dragster', 'candypeople', 'brynild',
    'hulten', 'konfekta', 'mentos', 'bubs', 'bubs godis', 'werthers original',
    'riesen', 'kinder', 'amos', 'wedel', 'karen volf', 'crispy',

    # Cosmetics / hygiene brands
    'loreal', "l'oréal", "l'oreal",
    'men expert',              # L'Oréal sub-brand — men's grooming (one product miscategorized as 'dairy')
    'maybelline', 'isadora', 'essie', 'max factor', 'lumene',
    'nivea', 'dove', 'colgate', 'rexona', 'head & shoulders',
    'october',                 # hair care/beauty — 66 products (shampoo, balsam, etc.)
    'libero',                  # baby care — 37 products (badskum, olja, schampo)

    # Garden / seeds brands
    'nelson garden',           # seeds, bulbs, garden supplies — not food

    # Board game / toy / book brands
    'lautapelti.fi',           # Finnish board game company — "Taco Cat Goat Cheese Pizza" etc.
    'tukan',                   # children's books — "Bä, bä, vita lamm" miscategorized as 'meat'
    'kärnan',                  # children's books/toys — 73 products (sagoböcker, målarböcker)

    # Clothing / household / electronics brands
    'mywear', 'depend', 'osram', 'holdit', 'sloggi', 'energizer',
    'järbo',                   # yarn/knitting — 108 products
    'waye readers',            # reading glasses — 75 products
    'happy party',             # balloons/party supplies — 69 products
    'derby',                   # shoes/shoe polish — 60 products
    'smartstore',              # storage containers — 46 products
    'sense',                   # face paint/crafts — 43 products
    'weber',                   # grill accessories (not food) — 43 products

    # Pharmacy / cleaning brands
    'ica hjärtat',             # pharmacy/supplements — 76 products (not recipe ingredients)
    'ica skona',               # cleaning products — 47 products

    # Pet food brands
    'mjau', 'sheba', 'gourmet', 'latz', 'dogman', 'whiskas',
    'doggy', 'doggy prof', 'doggy delikat',
    'smart pets', 'primadog', 'vitakraft', 'brit premium', 'sjöbogårdens',
    'pedigree', 'best friend', 'dreamies', 'cesar', 'one',
    'primacat', 'best in show', 'perfect fit', 'vov', 'naturligt',
    'friskies', 'adventuros', 'frolic', 'magnusson', 'natur hundtugg',
    'kattuna', 'axess', 'clever cat', 'peewee', 'smart cat',
}


# =============================================================================
# COOKING CHIPS - Chips types relevant for cooking (tortilla, nacho, etc.)
# =============================================================================
# Compound chip types used in cooking (tortilla wraps, nachos, coconut, etc.)
COOKING_CHIP_COMPOUNDS = (
    'tortillachips', 'tortilla chips',
    'nachochips', 'nacho chips', 'nachos chips',
    'tacochips', 'taco chips',
    'kokoschips', 'kokos chips',
    'rotfruktschips', 'rotfrukts chips',
    'grönkålschips', 'gronkalschips', 'grönkåls chips',
    'äppelchips', 'appelchips', 'äppel chips',
    'bananachips', 'bananchips', 'banan chips',
    'potatischips', 'potatis chips',
    'mandelpotatischips', 'lantchips',
    'sjögräschips', 'sjograschips',
)
# Salt descriptors that indicate plain (unflavored) chips
PLAIN_CHIPS_SALT_WORDS = ('lättsaltade', 'lattsaltade', 'saltade', 'havssalt', 'salted')


def is_cooking_chips(name_lower: str) -> bool:
    """Check if a chips product is cooking-relevant (not a flavored snack)."""
    if any(c in name_lower for c in COOKING_CHIP_COMPOUNDS):
        return True
    if any(s in name_lower for s in PLAIN_CHIPS_SALT_WORDS):
        return True
    return False


# =============================================================================
# COOKING NUTS - Distinguish plain cooking nuts from candy/snack nuts
# =============================================================================
# Nut keywords that identify a product as containing nuts
NUT_KEYWORDS = (
    'nöt', 'nötter', 'mandel', 'cashew', 'pistage', 'pistasch',
    'pecan', 'pekannöt', 'macadamia', 'jordnöt', 'valnöt',
    'hasselnöt', 'pinjenöt', 'hazelnut',
)
# Words that indicate a nut product is NOT for cooking (chocolate, ice cream, snack mix)
NUT_CANDY_INDICATORS = (
    'choklad', 'chocolate', 'mjölk', 'milk', 'kakao', 'cacao', 'cocoa',
    'glass', 'glasspinne', 'krokant', 'crunch', 'brittle',
    'créme', 'creme', 'kräm', 'nella',
    'müsli', 'musli', 'granola', 'frutti',
    'godis', 'belöning', 'ranchos', 'kuber',
    'schweizernöt', 'helnöt',  # chocolate bar brands
    'bar',  # candy bar
)
NUT_SNACK_INDICATORS = (
    'sourcream', 'onion', 'sting', 'wasabi', 'ranch',
    'honung', 'honning', 'honey',
    'chili', 'virginia',
    'smakfull', 'krispig', 'snacksnöt',
    'ringar',  # jordnötsringar
)
# Combined superset used by category_utils reclassification
# Includes all of NUT_CANDY_INDICATORS + NUT_SNACK_INDICATORS + brand names
NOT_COOKING_NUTS = (
    # Chocolate/confectionery
    'choklad', 'chocolate', 'mjölk', 'milk', 'kakao', 'cacao', 'cocoa',
    'krokant', 'crunch', 'brittle', 'schweizernöt', 'helnöt', 'bar',
    # Ice cream
    'glass', 'glasspinne',
    # Spreads
    'créme', 'creme', 'kräm', 'nella',
    # Cereal/granola (not plain nuts)
    'müsli', 'musli', 'granola', 'frutti',
    # Candy/treats
    'godis', 'belöning', 'ranchos', 'kuber',
    # Flavored snack nuts
    'sourcream', 'onion', 'sting', 'wasabi', 'ranch',
    'honung', 'honning', 'honey',
    'chili', 'virginia',
    'smakfull', 'krispig', 'snacksnöt',
    'ringar',
    # Mixed bags (snack mixes, not cooking)
    'nötmix', 'fruktmix', 'bärmix',
    # English-named candy/chocolate products
    'kitkat', 'kit kat', 'noisette', 'raisin', 'pralin',
    'whole hazelnut', 'rum ',
    'marabou', 'lindt', 'ferrero', 'toblerone', 'snickers',
    'daim', 'twix', 'bounty', 'milka', 'oreo',
)


def is_cooking_nuts(name_lower: str) -> bool:
    """Check if a nut product in candy category is cooking-relevant (plain nuts)."""
    if not any(n in name_lower for n in NUT_KEYWORDS):
        return False
    if any(c in name_lower for c in NUT_CANDY_INDICATORS):
        return False
    if any(s in name_lower for s in NUT_SNACK_INDICATORS):
        return False
    if 'nötmix' in name_lower or 'fruktmix' in name_lower or 'bärmix' in name_lower:
        return False
    return True


# =============================================================================
# COOKING CHOCOLATE - Distinguish baking chocolate from candy bars
# =============================================================================
# Explicitly cooking-relevant chocolate products
COOKING_CHOCOLATE_WORDS = (
    'bakchoklad', 'chokladsås', 'chokladknappar', 'chokladpudding',
    'choklad strössel', 'chokladströssel',
)
# Candy-specific indicators that disqualify a chocolate product from cooking use
CHOCOLATE_CANDY_INDICATORS = (
    # Candy bar formats
    'chokladkaka', 'chockladkaka',  # common typo in product names
    'chokladbar', 'choklad bar',  # "Mjölkchoklad Bar" (space variant)
    'chokladbit', 'chokladask', 'chokladpraliner',
    'chokladkola', 'chokladägg', 'chokladboll', 'chokladbomb', 'chokladkross',
    'kexchoklad', 'rischoklad', 'chokladmousse', 'chokladbollar',
    # Gift boxes and premium assortments
    'guldask', 'noblesse', 'hjärtask',
    # Candy brands and bar types
    'kitkat', 'maltesers', 'chocolonely', 'snickers', 'bounty', 'sportlunch',
    'kinder', 'bueno', 'daim', 'japp', 'plopp', 'lion', 'riesen', 'toffifee',
    'smash', 'marabou', 'fazer', 'lindor', 'excellence', 'merci', 'tuc',
    'oreo', 'nella', 'majsskruvar', 'magic sipper', 'tigo',
    'polly', 'bridge', 'bilar',  # Cloetta candy bars
    'amicelli', 'ritter',  # Ritter Sport candy
    'masterpieces', 'champs',  # Lindt gift boxes
    'mini bag', 'minibar',  # Mars/Twix mini bags
    'teddy', 'minikyckling',  # Lindt Easter/seasonal
    'hjärta',  # "Choklad hjärta" — gift chocolate
    'nesquik',  # Nesquik chocolate bar
    'peru',  # Malmö Chokladfabrik single-origin bar
    'schweizernöt', 'helnöt',  # Marabou bar types
    'saltlakrits',  # flavored candy
    'krokant',  # crunchy candy coating (apelsinkrokant etc.)
    # Ice cream and snacks
    'glasspinne', 'glass',
    'dadelboll',
    # Drinks and tea
    'chokladdryck', 'dryck', 'örtte',
    # Chocolate-covered nuts/fruit (not baking chocolate)
    'cashewnötter med',
    # Candy-specific words
    'choco cube', 'choco o', 'choco nibs',
    'roasted peanut',
    # Flavored milk chocolate bars = candy, not baking chocolate
    'jordgubb mjölkchoklad',  # "Jordgubb Mjölkchoklad" — strawberry candy bar
    'frukt & mandel',  # "Frukt & Mandel Mjölkchoklad" — fruit & nut candy bar
    'karamel havssalt',  # "Karamel Havssalt Mjölkchoklad" — caramel candy bar
)


def is_cooking_chocolate(name_lower: str) -> bool:
    """Check if a chocolate product is recipe-relevant despite candy-ish wording."""
    if 'choklad' not in name_lower:
        return False
    if 'chokladägg' in name_lower or 'chokladagg' in name_lower:
        return True
    if any(w in name_lower for w in COOKING_CHOCOLATE_WORDS):
        return True
    if any(w in name_lower for w in CHOCOLATE_CANDY_INDICATORS):
        return False
    return True


# =============================================================================
# VEGETARIAN/VEGAN INDICATORS - Classify recipe/product as plant-based
# =============================================================================
VEG_QUALIFIER_WORDS = {
    'vegetarisk', 'vegetariska', 'vegetariskt', 'vegansk', 'veganska', 'veganskt', 'vego',
    'växtbaserad', 'växtbaserade', 'växtbaserat',
    'vegetabilisk', 'vegetabiliska', 'vegetabiliskt',  # plant-based (≠ vegetarisk)
    'veg',  # common abbreviation for vegansk/vegetarisk
    'oatly',  # Oatly brand = always plant-based
    'vegosmör', 'vegasmör', 'vegansmör',  # compound words with vego-prefix
    'vegochorizo', 'vegobacon', 'vegokorvar',  # vego-compound products
}
VEG_PRODUCT_INDICATORS = {
    'veg', 'vego', 'vegetarisk', 'vegansk', 'växtbaserad',
    'växtbaserat', 'quorn', 'oumph', 'baljväxt',
    'havre', 'soja', 'kokos', 'mandel',  # plant-based base ingredients
    'alpro', 'oatly', 'oddlygood',  # plant-based brands
    'formbar',  # Anamma formbar färs
}
