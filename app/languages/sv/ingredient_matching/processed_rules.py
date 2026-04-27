"""Processed-product and spice/fresh rule data for Swedish ingredient matching.

Used by:
- validators.py — check_processed_product_rules(), check_spice_vs_fresh_rules()
- matching.py — precompute_offer_data() and matches_ingredient_fast()
"""

from typing import Dict, FrozenSet, Set

try:
    from languages.sv.normalization import fix_swedish_chars
except ModuleNotFoundError:
    from app.languages.sv.normalization import fix_swedish_chars

_PROCESSED_PRODUCT_RULES_RAW: Dict[str, Set[str]] = {
    # Note: 'vitlök' removed — now handled by SPICE_VS_FRESH_RULES instead.
    # Burk/rostad products are blocked from matching fresh garlic (klyftor etc.)
    # via blocked_product_words={'rostad', 'burk'} in _SPICE_VS_FRESH_RULES_RAW.
    'ingefära': {
        # Processed ginger forms
        'pulver', 'malen', 'malna', 'malet',
        'torkad', 'torkade', 'torkat',
        'kanderad', 'kanderade',
        'pressad', 'pressade',  # "Ingefära Pressad" = pressed paste, NOT fresh ginger
        'riven',               # "Ingefära Riven" = pre-grated tube, NOT fresh root
    },
    'gurkmeja': {
        # Processed turmeric forms — same pattern as ingefära.
        # "Gurkmeja Malen 43g ICA" should NOT match "färsk gurkmeja".
        'pulver', 'malen', 'malna', 'malet',
        'torkad', 'torkade', 'torkat',
    },
    'paprika': {
        # Spice forms - "Paprika Stark" should NOT match "1 st Gul Paprika"
        # If product is paprika spice, ingredient must also be asking for spice
        'stark', 'pulver', 'malen', 'malna', 'malet', 'rökt', 'rokt',
        'krydda',  # paprikakrydda
    },
    'potatis': {
        # Pre-processed potato forms - "Tärnad potatis 800g Felix" is NOT plain "potatis"
        # If product has a processed indicator, recipe must also have it
        'tärnad', 'tarnad',  # pre-diced
        'mosad', 'mosat',  # mashed
        'strimlad', 'strimlade',  # french-fry cut - "Strimlad Potatis Fryst" != "800g potatis"
    },
    'lök': {
        # Color/type indicators - "Lök Röd" should NOT match generic "lök" or "gul lök"
        # "Lök Vit" handled by PRODUCT_NAME_SUBSTITUTIONS (lök → vitlök)
        'röd',
    },
    'rödlök': {
        # "Picklad Rödlök" is preserved, should NOT match fresh "1 rödlök"
        'picklad', 'picklat', 'picklade',
    },
    'rödbeta': {
        # Pickled/preserved beets ≠ fresh beets
        # "Rödbetor Gammaldags" / "Rödbetor Skivade" = pickled in vinegar/brine
        # "Rödbetor Förkokt" = vacuum-packed pre-cooked, fine as fresh substitute (NOT blocked)
        'gammaldags', 'gammeldags',          # traditional pickled style
        'skivad', 'skivade', 'skivor',       # sliced = always preserved (no pre-sliced fresh beets)
        'inlagd', 'inlagda',                 # recipe says "inlagda rödbetor" → allow all pickled products
        'konserverad', 'konserverade',       # recipe/product says "Rödbetor Konserverade"
        # NOTE: 'hela' intentionally omitted — too common in "4 hela rödbetor" (= 4 whole fresh)
    },
    # Prepared spinach dishes should not match plain spinach ingredients.
    # Frozen chopped spinach is still an acceptable fallback for fresh spinach lines,
    # but "stuvad spenat" is a finished creamed dish, not just a frozen vegetable.
    'spenat': {
        'stuvad', 'stuvade',   # frozen creamed spinach
    },
    'champinjon': {
        # Preserved champignons should not leak into plain fresh-mushroom recipe
        # lines via the broader "svamp" fallback.
        'tetra',
        'konserverad', 'konserverade',
        'burk',
        'skivad', 'skivade',
        'hela',
    },
    'champinjoner': {
        'tetra',
        'konserverad', 'konserverade',
        'burk',
        'skivad', 'skivade',
        'hela',
    },
    'körsbärstomat': {
        # Sun-dried cherry tomatoes ≠ fresh cherry tomatoes
        # "Pomodori Ciliegino Secchi Solt Körsbärstomat" = sun-dried
        'solt', 'soltorkad', 'soltorkade',
        'secchi',  # Italian for "dried"
        'torkad', 'torkade',
        # Canned cherry tomatoes in juice ≠ fresh cherry tomatoes
        # "Körsbärs-Tomater i Tomatjuice" = preserved/canned
        'tomatjuice', 'juice',
        # Allow when recipe explicitly asks for canned/preserved
        'konserverade', 'konserverad', 'konserv',
        # Allow when recipe says "körsbärstomater" (most mean canned, not fresh)
        'körsbärstomater', 'körsbärstomat', 'korsbarstomat',
    },
    'körsbärstomater': {
        'solt', 'soltorkad', 'soltorkade',
        'secchi',
        'torkad', 'torkade',
        'tomatjuice', 'juice',
        'konserverade', 'konserverad', 'konserv',
        'körsbärstomater', 'körsbärstomat', 'korsbarstomat',
    },
    'kalkonbröst': {
        # Charcuterie turkey breast ≠ raw turkey breast
        # "Extrarökt Kalkonbröst Skivad" should NOT match "600 g kalkonbröst"
        # 11 recipes affected. Only "Kalkon Bröstfilé Mörad Fryst" is raw.
        'rökt', 'rokt', 'extrarökt', 'extrarokt',
        'alspånsrökt', 'alspansrokt',
        'basturökt', 'basturokt',
        'pastrami',
        'skivad', 'skivade',  # sliced = always deli
        'kokt',               # "Kokt Kalkon Strimlad" = pre-cooked deli
    },
    'kalkonbröstfil': {
        # Same rules for the -fil variant keyword
        'rökt', 'rokt', 'extrarökt', 'extrarokt',
        'alspånsrökt', 'alspansrokt',
        'basturökt', 'basturokt',
        'pastrami',
        'skivad', 'skivade',
        'kokt',
    },
    'bönor': {
        # Brown beans ≠ green beans - completely different products and uses
        # "Bruna Bönor 500g" should NOT match recipe "400g gröna bönor"
        'bruna',
    },
    'gurka': {
        # Pickled/preserved cucumber ≠ fresh cucumber
        # "Gurka med Dill" and "Inlagd Gurka Saltad" should NOT match "0,5 gurka"
        'dill',        # "Gurka med Dill" = pickled
        'inlagd',      # "Inlagd Gurka Saltad" = pickled
        'inlagda',     # plural form
        'saltad',      # "Gurka Saltad" = brined
        'salt',        # "Salt Gurka" = brined
        'krispig',     # "Gammeldags Krispig Gurka" = pickled
        'gammeldags',  # "Gammeldags Gurka" = pickled (old spelling)
        'gammaldags',  # "Gammaldags Gurka" = pickled (current spelling)
        # NOTE: 'finhackad' and 'tunnskivad' REMOVED — these are prep methods that
        # appear in ingredient text ("gurka, finhackad") causing PPR to let ALL
        # pickled products through. The PRODUCT "Finhackad Gurka" / "Tunnskivad Gurka"
        # is still blocked via 'smörgås'/'ättiks' compound indicators below.
        'delikatess',  # "Gurka Delikatess" = pickled/preserved
        'libanesisk',  # "Gurka Libanesisk" = specific variety, NOT generic gurka
        # Product-side qualifiers for compound pickled cucumber types:
        # Smörgåsgurka/Ättiksgurka/Bostongurka have parent keyword "gurka"
        # and need these qualifiers so "inlagd gurka" matches via QUALIFIER_EQUIVALENTS
        'smörgås', 'smorgås',  # Smörgåsgurka
        'ättiks', 'attiks',    # Ättiksgurka
        'boston',              # Bostongurka
    },
    'dill': {
        # "Gurka med Dill" = pickled cucumber product, dill is flavoring
        # should NOT match recipe wanting fresh "dill" herb
        'gurka',
    },
    # 'lime' removed — handled by SPICE_VS_FRESH_RULES instead.
    # PROCESSED_PRODUCT_RULES uses concatenated ingredient text which causes
    # cross-contamination ('torkad' from 'torkad oregano' lets 'Torkad Lime' through).
    'tomater': {
        # Canned/processed tomatoes ≠ fresh tomatoes
        # "Krossade Tomater 390g" should NOT match "2 st Vanliga Tomater"
        # Per-ingredient validation in recipe_matcher prevents cross-contamination.
        'krossade', 'krossad',
        'finkrossade', 'finkrossad',
        'finhackade', 'finhackad',  # finely chopped (canned/tetra)
        'passerade', 'passerad',
        'skalade', 'skalad',  # peeled = always canned ("Hela Skalade Tomater")
        'soltorkade', 'soltorkad',  # sun-dried
        'torkade', 'torkad',  # dried (safe now: per-ingredient validation in recipe_matcher)
        'polpa',  # Italian crushed (canned)
        'koncentrerade', 'koncentrerad',  # concentrated
        'hela',  # "Hela Tomater" = whole canned (matches "Hela Skalade Tomater")
        'konserverade', 'konserverad',  # canned/preserved
        'burk',  # "1 burk tomater" = wants canned, allow any canned product to match
        # Specific tomato varieties ≠ generic "tomater"
        'cocktail', 'cockt',  # cocktail tomatoes
        'mix',  # tomato mix (variety pack)
        'babyplommon',  # baby plum tomatoes
        # NOT 'marzano' - moved to CONTEXT_REQUIRED_WORDS (avoids cross-ingredient contamination)
    },
    # Singular form — product "Tomat Finhackad" has keyword 'tomat' (not 'tomater')
    'tomat': {
        'krossade', 'krossad',
        'finkrossade', 'finkrossad',
        'finhackade', 'finhackad',
        'passerade', 'passerad',
        'skalade', 'skalad',
        'hela',  # "Hela Tomater Konserverade" = whole canned tomatoes
        'konserverade', 'konserverad',  # canned/preserved
        'soltorkade', 'soltorkad',
        'soltork', 'solt',  # abbreviated forms in product names ("Solt Tomat", "Soltork Tomat")
        'secchi',  # Italian for "dried" — "Pomodori Secchi"
        'torkade', 'torkad',
        'polpa',
        'koncentrerade', 'koncentrerad',
        'burk',
        # Specific tomato varieties ≠ generic "tomat"
        'cocktail', 'cockt',  # cocktail tomatoes
        'mix',  # tomato mix (variety pack)
        'babyplommon',  # baby plum tomatoes
    },
    'tonfisk': {
        # Canned tuna indicators - if product is canned tuna (in oil/water),
        # ingredient must also mention canned context (burk/konserv/olja).
        # "Tonfisk i Solrosolja" should NOT match "tonfisk, tunt skivad" (= fresh)
        # but SHOULD match "1 burk tonfisk" or "tonfisk i olja"
        'solrosolja', 'olja', 'vatten',  # product indicators (canned)
        'burk', 'konserv',  # ingredient indicators (recipe says canned)
    },
    'sojabönor': {
        # "sojabönor konserv" should not fall through to frozen soybeans.
        # Treat canned/jarred soybeans and frozen soybeans as distinct forms,
        # while still letting plain generic "sojabönor" remain broad.
        'burk', 'konserv', 'konserverad', 'konserverade',
        'fryst', 'frysta',
    },
    'sojabonor': {
        'burk', 'konserv', 'konserverad', 'konserverade',
        'fryst', 'frysta',
    },
    'lax': {
        # Smoked/cured salmon ≠ fresh salmon
        # "Kallrökt Laxfilé" should NOT match "300 g laxfilé utan skinn" (= fresh)
        # but SHOULD match "100 g Lax Kallrökt" (recipe wants smoked)
        'rökt', 'gravad',
        'burgare',  # salmon burgers ≠ fresh salmon / fillet
    },
    'laxfilé': {
        'rökt', 'gravad',
        'sushi', 'nigiri',
        'burgare',  # salmon burgers ≠ raw fillet
    },
    'laxfile': {
        'rökt', 'gravad',
        'burgare',
    },
    # Breaded/crispy fish ≠ fresh fish
    # "Sej Panerad" / "Kummel Sprödbakad" should NOT match "600 g fisk"
    # but SHOULD match if recipe explicitly says "panerad"/"sprödbakad"
    'sej': {
        'panerad', 'panerade', 'sprödbakad', 'sprödbakade',
    },
    'torsk': {
        'panerad', 'panerade', 'sprödbakad', 'sprödbakade',
    },
    'kolja': {
        'panerad', 'panerade', 'sprödbakad', 'sprödbakade',
    },
    'kummel': {
        'panerad', 'panerade', 'sprödbakad', 'sprödbakade',
    },
    'mjölk': {
        # Condensed/caramelized milk ≠ regular milk
        # "Kondenserad Mjölk" / "Karamelliserad Mjölk" should NOT match "1 l mjölk"
        # but SHOULD match "1 dl kondenserad mjölk" / "1 burk karamelliserad mjölk"
        'kondenserad', 'kondenserat', 'kondenserade',
        'karamelliserad', 'karamelliserat', 'karamelliserade',
    },
    'mjolk': {
        'kondenserad', 'kondenserat', 'kondenserade',
        'karamelliserad', 'karamelliserat', 'karamelliserade',
    },
    'spiskummin': {
        # Whole (hel) vs ground (malen) cumin are different forms
        # "Spiskummin Malen Burk" should NOT match "1,5 msk hel spiskummin"
        'malen', 'mald', 'malna', 'malet',
        'hel', 'hela',
    },
    'apelsinjuice': {
        # Recipe wants juice, not whole fruit or blended juice
        'klass',   # "Apelsin Klass 1" — whole fruit
        'morot',   # "Apelsinjuice med Morot Juice" — carrot blend
    },
    # NOTE: Leafy herbs NOT in PPR — dried↔fresh blocking handled by STEP 7
    # (FRESH_HERB_KEYWORDS + weight heuristic + RECIPE_FRESH_INDICATORS).
    # PPR would break "rosmarin" (no qualifier) matching "Rosmarin Torkad 20g".
    'quinoa': {
        # "Quinoa Puffar" / "Quinoa Puffad" — puffed quinoa snack, not raw grain
        'puff', 'puffar', 'puffad', 'puffade',
    },
    'persilja': {
        # "Persilja Blad" / "Bladpersilja Lösvikt" = flat-leaf (bladpersilja)
        # PPR auto-allows "Persilja Blad" when recipe says "bladpersilja"
        # (because 'blad' appears in ingredient text too)
        # NOTE: 'fryst' removed — frozen herbs ≈ fresh (herb form system handles it)
        'blad',    # flat-leaf variety — blocks unless ingredient also says "blad"
    },
    # Jalapeño: unconditional blocks (cheese, sauce, relish — never valid).
    # Pickled products (sliced/peppers) handled conditionally via SVF rules.
    'jalapenos': {
        'riven',              # grated cheese ("Jalapeno Chili Texmex Riven 25%")
        'texmex',             # cheese product
        'relish',             # condiment ("Green Jalapeño Relish")
        'sauce',              # condiment ("Cheezy Jalapeño Sauce")
        'cheezy', 'cheesy',   # cheese-flavored sauce
        'hot',                # "Green Jalapeño Hot" = hot sauce
        'green',              # "Green Jalapeño ..." = sauce brand (English, not in SV recipes)
    },
    'jalapeno': {
        'riven', 'texmex',
        'relish', 'sauce', 'cheezy', 'cheesy',
        'hot', 'green',
    },
    'chili': {
        # Fresh chili ≠ chili sauce/spice/condiment products
        # "Chili Röd Ekologisk" is fresh — no indicators in product name
        # Products with these indicators are processed/not fresh chili:
        'burk',        # "Chilipeppar Burk" = canned
        'pulver',      # "Chili Pulver Gochugaru" = ground spice
        'kvarn',       # "Chili Explosion Kvarn" = spice grinder
        'flakes',      # "Chili Flakes" = dried flakes
        'flingor',     # "Chiliflingor" = dried flakes (Swedish)
        'torkad',      # "Mango Chili Torkad" = dried
        'sauce',       # "Sweet Chili Sauce" = condiment
        'ketchup',     # "Hot Chili Ketchup" = condiment
        'olja', 'oil', # "Crispy Chili In Oil" = condiment
        'crunch',      # "Chilli Chili Crunch" = condiment
        'tortilla',    # "Sweet Chili Tortilla Strips" = snack
        'chips',       # chili-flavored chips
        'béarnaise', 'bearnaise',  # chili-flavored sauce
        'chicken',     # "Chicken Sweet Chili" = ready meal
        'salsa',       # "Bean Chili Salsa" = condiment
        'örtsalt', 'ortsalt',  # "Örtsalt Chili&paprika" = spice mix
        'white',       # "White With Chili 38%" = white chocolate
    },
    'kyckling': {
        # Processed chicken products that should NOT match generic "kyckling" recipes
        'paté', 'pate',   # "Kycklingpaté" = chicken pâté, NOT raw chicken
        'korv',           # "Kycklingkorv" = chicken sausage (already in FPB but PPR catches product side)
    },
    'saffran': {
        # Saffron-flavored rice ≠ saffron spice
        # "Saffranris Basmati" should NOT match recipe "1 krm saffran"
        'ris',         # "Saffranris" = rice product, NOT saffron spice
        'basmati',     # "Saffranris Basmati" = flavored rice
    },
    'vetemjöl': {
        # Pizza flour ≠ regular flour
        # "Pizzeria Vetemjöl Tipo 00" should NOT match recipe wanting plain "vetemjöl"
        'pizzeria',    # pizza flour brand/type
        'pizza',       # pizza-specific flour
        'tipo',        # Italian flour grading (Tipo 00/0/1) = specialty
        # NOTE: 'rågsikt' moved to PNB (was incorrectly placed here in PPR)
    },
    'gräslök': {
        # "Gräslök Light 11%" = cream cheese spread, NOT fresh chives
        # NOTE: 'fryst'/'finhackad' removed — frozen herbs ≈ fresh
        'light',       # cream cheese/spread
    },
    'kryddmix': {
        # Specific spice mix types - "Kryddmix Smokey" != "Kryddmix Kerala"
        # If product has a specific type, ingredient must also specify that type
        # With STRICT_PROCESSED_RULES: at least one of the product's indicators
        # must be in the ingredient (exact match, not any-indicator-is-ok)
        # Regional/cuisine types
        'smokey', 'smoke', 'bbq', 'barbecue',
        'kerala', 'indian', 'indisk',
        'taco', 'mexicansk', 'tex-mex', 'texmex', 'fajita',
        'gyros', 'grekisk',
        'tandoori', 'tikka', 'garam',
        'cajun', 'creole',
        'korean', 'koreansk',
        'thai',
        'italian', 'italiensk',
        # Curry variants
        'curry', 'paneng', 'panang', 'massaman',
        # Ranch/other
        'ranch',
        # Flavor profiles
        'sweet', 'hot', 'mild',
        # Protein types — "Kryddmix Kyckling" ≠ "Kryddmix Lasagne"
        'kyckling', 'chicken', 'fisk', 'lamm', 'kalkon',
    },
    # "Kardemumma Längd" is a bakery product (cardamom bread loaf), NOT cardamom spice.
    # Block unconditionally — a bread product should never match spice ingredients.
    'kardemumma': {
        'längd',  # "Kardemumma Längd" = bakery loaf
    },
}

# Compound words that bypass PROCESSED_PRODUCT_RULES for a base word.
# "körsbärstomater" contains "tomater" as substring, but canned/fresh cherry tomatoes
# are interchangeable in cooking - don't enforce canned-indicator matching.
PROCESSED_RULES_COMPOUND_EXEMPTIONS: Dict[str, Set[str]] = {
    'tomater': {'körsbärstomater', 'korsbärstomater', 'korsbarstomate'},
    'tomat': {'körsbärstomat', 'körsbärstomater', 'korsbärstomat'},
    # Sriracha is a specific chili-based sauce ingredient, not a generic chili product.
    # Let "Sriracha Hot Chilli Sauce" match explicit sriracha lines instead of being
    # blocked by the generic chili processed-product rule.
    'chili': {'sriracha'},
}

# Pre-normalized for performance
PROCESSED_PRODUCT_RULES: Dict[str, Set[str]] = {
    fix_swedish_chars(k).lower(): {fix_swedish_chars(w).lower() for w in v}
    for k, v in _PROCESSED_PRODUCT_RULES_RAW.items()
}

# Base words where the product's specific indicator MUST exactly match the ingredient.
# Regular PROCESSED_PRODUCT_RULES allows any indicator (e.g., "krossade" ≈ "passerade" for tomater).
# Strict rules require the EXACT indicator because types are not interchangeable.
STRICT_PROCESSED_RULES: FrozenSet[str] = frozenset({
    'kryddmix',    # "Kryddmix Tikka Masala" ≠ "Fajita Kryddmix"
    'paprika',     # "Rökt Paprika" should only match "rökt paprikapulver", not plain
    # NOTE: kummin REMOVED — whole/ground kummin are interchangeable for cooking.
    # Strict mode blocked ALL kummin matches when recipe just says "1 tsk kummin".
    'spiskummin',  # "Spiskummin Malen" ≠ "hel spiskummin" (different forms)
    'chili',       # "Sweet Chili Sauce" ≠ "chiliflakes" — strict to prevent cross-indicator bleed
    'saffran',     # "Basmati Saffran" has indicator 'basmati' — must match exactly, not via 'ris' substring
    'ingefära',    # "Ingefära Pressad" ≠ "malen ingefära" — pressed/ground/dried not interchangeable
    'gurkmeja',    # "Gurkmeja Malen" ≠ "färsk gurkmeja" — ground/dried not interchangeable with fresh
    'tomat',       # "Krossade Tomater" ≠ "Hela Tomater" ≠ "Passerade" — each form distinct
    'tomater',     # plural form — same strict rules
    'sojabönor',   # canned soybeans ≠ frozen soybeans when recipe explicitly asks for one form
    'sojabonor',
})

# Equivalence groups for processed indicators in STRICT mode.
# "malen"/"mald"/"malet"/"malna" are all the same form (ground/milled).
# "hel"/"hela" are the same form (whole).
# Without this, strict processed keywords like "Spiskummin Malen" won't match
# ingredient text saying "spiskummin, mald" because STRICT mode requires the
# exact product indicator word in the ingredient.
_PROCESSED_INDICATOR_EQUIVALENTS: Dict[str, FrozenSet[str]] = {
    'malen': frozenset({'malen', 'mald', 'malet', 'malna'}),
    'mald': frozenset({'malen', 'mald', 'malet', 'malna'}),
    'malet': frozenset({'malen', 'mald', 'malet', 'malna'}),
    'malna': frozenset({'malen', 'mald', 'malet', 'malna'}),
    'hel': frozenset({'hel', 'hela', 'skalade', 'skalad', 'konserverade', 'konserverad'}),
    'hela': frozenset({'hel', 'hela', 'skalade', 'skalad', 'konserverade', 'konserverad'}),
    'torkad': frozenset({'torkad', 'torkade', 'torkat'}),
    'torkade': frozenset({'torkad', 'torkade', 'torkat'}),
    'torkat': frozenset({'torkad', 'torkade', 'torkat'}),
    # Tomato form equivalents for STRICT mode
    # Crushed group: krossade ≈ finkrossade ≈ polpa (all crushed/chopped canned)
    'krossade': frozenset({'krossade', 'krossad', 'finkrossade', 'finkrossad', 'polpa'}),
    'krossad': frozenset({'krossade', 'krossad', 'finkrossade', 'finkrossad', 'polpa'}),
    'finkrossade': frozenset({'krossade', 'krossad', 'finkrossade', 'finkrossad', 'polpa'}),
    'finkrossad': frozenset({'krossade', 'krossad', 'finkrossade', 'finkrossad', 'polpa'}),
    'polpa': frozenset({'krossade', 'krossad', 'finkrossade', 'finkrossad', 'polpa'}),
    # Whole group: hela ≈ skalade ≈ konserverade (whole/peeled/canned whole)
    'skalade': frozenset({'skalade', 'skalad', 'hela', 'konserverade', 'konserverad'}),
    'skalad': frozenset({'skalade', 'skalad', 'hela', 'konserverade', 'konserverad'}),
    'konserverade': frozenset({'skalade', 'skalad', 'hela', 'burk', 'konserv', 'konserverade', 'konserverad'}),
    'konserverad': frozenset({'skalade', 'skalad', 'hela', 'burk', 'konserv', 'konserverade', 'konserverad'}),
    # Passerade stands alone (different texture from krossade)
    'passerade': frozenset({'passerade', 'passerad'}),
    'passerad': frozenset({'passerade', 'passerad'}),
    # Concentrated stands alone
    'koncentrerade': frozenset({'koncentrerade', 'koncentrerad'}),
    'koncentrerad': frozenset({'koncentrerade', 'koncentrerad'}),
    # Sun-dried group
    'soltorkade': frozenset({'soltorkade', 'soltorkad', 'soltork', 'solt', 'secchi'}),
    'soltorkad': frozenset({'soltorkade', 'soltorkad', 'soltork', 'solt', 'secchi'}),
    'soltork': frozenset({'soltorkade', 'soltorkad', 'soltork', 'solt', 'secchi'}),
    'solt': frozenset({'soltorkade', 'soltorkad', 'soltork', 'solt', 'secchi'}),
    'secchi': frozenset({'soltorkade', 'soltorkad', 'soltork', 'solt', 'secchi'}),
    # Finhackade stands alone (finely chopped, different from crushed)
    'finhackade': frozenset({'finhackade', 'finhackad'}),
    'finhackad': frozenset({'finhackade', 'finhackad'}),
    'burk': frozenset({'burk', 'konserv', 'konserverad', 'konserverade'}),
    'konserv': frozenset({'burk', 'konserv', 'konserverad', 'konserverade'}),
}


# ============================================================================
# SPICE VS FRESH VEGETABLE RULES
# ============================================================================
# When ingredient contains spice indicators, block fresh vegetable products.
#
# Example: "1 tsk paprikakrydda" → ingredient wants the SPICE
#          Should NOT match "Paprika spetsig röd" (fresh vegetable)
#
# Format: ingredient_word -> {
#     'spice_indicators': words/patterns indicating spice (krydda, malen, or implied by unit tsk/msk)
#     'blocked_product_words': product words that indicate fresh vegetable form
# }

_SPICE_VS_FRESH_RULES_RAW: Dict[str, Dict[str, Set[str]]] = {
    'paprika': {
        # "paprikakrydda", "malen paprika", or "1 tsk paprika" = the spice
        # Also: "Paprika Stark" is a spice product
        'spice_indicators': {
            'krydda', 'paprikakrydda',
            'malen', 'malna', 'malet', 'pulver',
            'rökt', 'stark',
            'tsk', 'tesked', 'krm',
        },
        'blocked_product_words': {
            'spetsig', 'spetspaprika', 'spets',
            'röd', 'grön', 'gul', 'orange',  # color indicates fresh pepper
            'mini', 'minipaprika',
            'klass', 'klass1',  # quality class = fresh produce
            'snack', 'snackpaprika',
            'grillad', 'grillat',  # "Paprika Grillad" = grilled bell pepper
            'filé', 'file',  # "Paprika Filé" = bell pepper fillet
            'mix',  # "Paprika Mix" = fresh mixed peppers
        },
    },
    'chili': {
        # "chiliflingor", "malen chili" = dried/spice form
        'spice_indicators': {'flingor', 'flinga', 'malen', 'malna', 'pulver', 'krossad', 'krossade', 'torkad', 'torkade'},
        'blocked_product_words': {
            'färsk', 'färska',
            'röd', 'grön',  # color often indicates fresh
            'habanero', 'jalapeño', 'jalapeno', 'serrano',  # fresh pepper varieties
        },
    },
    'jalapeno': {
        # "Jalapeno Sliced" / "Jalapeno Peppers" = pickled/jarred
        # "Chilli Jalapeno" = fresh (no processing indicator)
        # Cheese/sauce blocked unconditionally via PROCESSED_PRODUCT_RULES.
        #
        # Check A: pickled products blocked for fresh recipes, allowed for pickled
        'allowed_indicators': {
            'inlagd', 'inlagda',             # "inlagd jalapeño"
            'konserverad', 'konserverade',    # "Jalapeno Konserverad"
            'picklad', 'picklade',            # "picklad jalapeño"
            'skivad', 'skivade',             # "skivad jalapeño"
        },
        'blocked_product_words': {
            'sliced',             # "Jalapeno Sliced" — pickled (English)
            'skivad', 'skivade',  # "Jalapeños Skivad" — pickled (Swedish)
            'peppers',            # "Jalapeno Peppers" — jarred
        },
        # Check C: recipe says "inlagd" → require pickled product, block fresh
        'pickled_indicators': {
            'inlagd', 'inlagda',
            'konserverad', 'konserverade',
            'picklad', 'picklade',
        },
        'pickled_product_words': {
            'sliced', 'skivad', 'skivade',   # sliced = pickled
            'peppers',                        # jarred peppers
        },
    },
    # Plural form needed — matched_keyword is often 'jalapenos' (product keyword)
    'jalapenos': {
        'allowed_indicators': {
            'inlagd', 'inlagda',
            'konserverad', 'konserverade',
            'picklad', 'picklade',
            'skivad', 'skivade',
        },
        'blocked_product_words': {
            'sliced',
            'skivad', 'skivade',
            'peppers',
        },
        'pickled_indicators': {
            'inlagd', 'inlagda',
            'konserverad', 'konserverade',
            'picklad', 'picklade',
        },
        'pickled_product_words': {
            'sliced', 'skivad', 'skivade',
            'peppers',
        },
    },
    'fänkål': {
        # "Fänkål Malen Påse" = ground fennel spice
        # "Fänkål Hel Påse" = whole fennel seeds (dried)
        # "Fänkål Klass 1" = fresh vegetable
        # Recipe "1 fänkål" wants vegetable, "1 krm fänkålsfrö" wants seeds
        # NOTE: 'frö' NOT in allowed_indicators — seeds should NOT unlock ground spice.
        # 'påse' NOT in blocked — both Hel Påse and Malen Påse have it.
        #
        # Check A: blocked_product_words blocks spice products (malen, hel) from
        # fresh fänkål recipes. allowed_indicators unlocks them for spice recipes.
        # Check B: fresh_product_words blocks fresh products (klass) from
        # spice fänkål recipes (with dried_indicators).
        'allowed_indicators': {
            'malen', 'mald', 'malda',       # ground → unlocks "Malen Påse"
            'tsk', 'tesked', 'krm',          # measurement → likely spice
            'krydda',                        # "Fänkål Krydda" = spice, not fresh fennel
            'pollen', 'fänkålspollen',       # pollen → unlocks spice products
            'frö', 'fänkålsfrö', 'fankalsfro',  # seeds → unlocks seed products
        },
        'blocked_product_words': {
            'malen',  # "Fänkål Malen Påse" — ground fennel spice
            'hel',    # "Fänkål Hel Påse" — whole dried fennel seeds
        },
        # Check B: if recipe says "1 krm fänkålsfrö" → block fresh "Fänkål Klass 1"
        'fresh_product_words': {
            'klass',  # quality class = fresh produce
        },
        'dried_indicators': {
            'malen', 'mald', 'malda',       # ground spice
            'tsk', 'tesked', 'krm',          # measurement → spice
            'krydda',                        # "Fänkål Krydda" should block fresh bulb
            'frö', 'fänkålsfrö', 'fankalsfro',  # seeds
        },
    },
    'koriander': {
        # Check A: block ground spice unless recipe asks for spice
        'allowed_indicators': {
            'malen', 'mald', 'malda', 'malna',   # ground → unlocks Malen Burk
            'tsk', 'tesked', 'krm',                # measurement → likely spice
            'torkad', 'torkade',                    # dried → unlocks dried products
        },
        'blocked_product_words': {
            'malen',      # "Koriander Malen Burk" — ground spice
        },
        # Check B: block fresh products when recipe wants spice/seeds
        'fresh_product_words': {
            'klass',      # "Koriander Klass 1" — fresh produce
            'kruka',      # "Koriander i kruka" — potted herb
            'bunt',       # "Koriander Bunt" — fresh bunch
            'finhackad',  # "Koriander Finhackad Fryst" — frozen herb (not seeds)
            'fryst',      # frozen herb products
        },
        'dried_indicators': {
            'torkad', 'torkade',                    # "torkad koriander"
            'malen', 'mald', 'malda', 'malna',     # "malen koriander"
            'tsk', 'tesked', 'krm',                 # spice measurement
            'frö', 'korianderfrö', 'fro',           # seeds
            'korianderfrön', 'korianderfron',        # "stötta korianderfrön" — INGREDIENT_PARENTS maps to 'koriander'
        },
    },
    'kanel': {
        # "kanelstång" = whole cinnamon stick → block ground cinnamon products
        # "malen kanel" = ground → block whole cinnamon products
        'spice_indicators': {'stång', 'stänger', 'hel', 'hela'},
        'blocked_product_words': {
            'malen',    # "Kanel Malen Påse" — ground cinnamon
            'cassia',   # "Kanel Cassia Malen Burk" — ground cassia
            'ceylon',   # "Kanel Ceylon Burk" — ground ceylon
        },
        # Reverse direction: ingredient says "malen" or uses tsk/krm measurement
        # (implies ground) → block whole-cinnamon products
        'ground_indicators': {'malen', 'mald', 'malna', 'malet', 'tsk', 'tesked', 'krm'},
        'blocked_whole_product_words': {'hel', 'hela'},
    },
    'kardemumma': {
        # "kardemummakapslar" = whole pods → block ground cardamom products
        # "kardemummakärnor" should behave the same way when the match falls
        # back to generic "kardemumma" rather than the exact kärnor keyword.
        # "malen kardemumma" = ground → block whole cardamom products
        'spice_indicators': {'kapsel', 'kapslar', 'kärna', 'kärnor', 'karna', 'karnor', 'frö', 'frön', 'fro', 'fron', 'hel', 'hela'},
        'blocked_product_words': {
            'malen',   # "Kardemumma Malen Burk" — ground cardamom
        },
        # Reverse direction: ingredient says "malen" → block whole-cardamom products
        'ground_indicators': {'malen', 'mald', 'malna', 'malet'},
        'blocked_whole_product_words': {'kapsel', 'kapslar', 'kärna', 'kärnor', 'karna', 'karnor', 'frö', 'frön', 'fro', 'fron', 'hel', 'hela'},
    },
    'kardemummakärnor': {
        # Whole cardamom seeds should not match ground cardamom products
        'spice_indicators': {'kärnor', 'hel', 'hela'},
        'blocked_product_words': {
            'malen',
        },
        'ground_indicators': {'malen', 'mald', 'malna', 'malet'},
        'blocked_whole_product_words': {'kärnor', 'hel', 'hela'},
    },
    'kardemummakarnor': {
        'spice_indicators': {'karnor', 'hel', 'hela'},
        'blocked_product_words': {
            'malen',
        },
        'ground_indicators': {'malen', 'mald', 'malna', 'malet'},
        'blocked_whole_product_words': {'karnor', 'hel', 'hela'},
    },
    'svartpeppar': {
        # "svartpepparkorn" = whole peppercorns → block ground pepper products
        # "malen/nymalen svartpeppar" = ground → block whole peppercorn products
        'spice_indicators': {'korn', 'hel', 'hela'},
        'blocked_product_words': {
            'malen', 'grovmalen',  # ground pepper products
        },
        'ground_indicators': {'malen', 'mald', 'malna', 'malet', 'nymalen'},
        'blocked_whole_product_words': {'hel', 'hela'},
    },
    'spiskummin': {
        # "hel spiskummin" = whole cumin seeds → block ground products
        # "Spiskummin 33g" without "hel" = ground by default.
        # spice_indicators mode: if ingredient has 'hel' → block products with 'burk'/'malen'
        'spice_indicators': {'hel', 'hela'},
        'blocked_product_words': {
            'burk',   # "Spiskummin Burk" — ground (no "hel" qualifier)
            'malen',  # "Spiskummin Malen" — explicitly ground
            'malna',
            'mald',
        },
        # When recipe says "hel", REQUIRE product to also say "hel"/"hela".
        # "Spiskummin 33g Santa Maria" (no qualifier) = malen by default → blocked.
        'required_whole_product_words': {'hel', 'hela'},
    },
    'lime': {
        # "Torkad Lime Påse" = dried lime spice, "Lime Blad" = kaffir lime leaves
        # Should NOT match recipe wanting fresh lime ("2 limefrukter")
        # Uses allowed_indicators: only match dried/leaf products if ingredient asks for them
        'allowed_indicators': {
            'torkad', 'torkade',  # dried lime
            'blad',               # lime leaves (kaffir)
        },
        'blocked_product_words': {
            'torkad', 'torkade',  # "Torkad Lime Påse"
            'blad',               # "Lime Blad Torkade"
        },
    },
    'vitlök': {
        # TWO directions:
        # 1) Jarred product + fresh ingredient → block (require-mode)
        #    "Vitlök Rostad Burk" only matches "1 msk vitlök" (volume = jarred)
        # 2) Fresh product + dried ingredient → block (block-mode)
        #    "Vitlök Klass 1" should NOT match "1 tsk torkad vitlök"
        'allowed_indicators': {
            'msk', 'matsked',     # tablespoon = jarred/dried
            'tsk', 'tesked',      # teaspoon = dried/powder
            'krm',                # pinch = dried/powder
            'pulver',             # vitlökspulver
            'torkad', 'torkade',  # dried garlic
            'granulat',           # garlic granules
        },
        'blocked_product_words': {
            'rostad',   # "Vitlök Rostad Burk" — roasted garlic paste
            'burk',     # preserved in jar — not fresh cloves
            'pressad',  # "Vitlök Pressad" — pressed garlic paste, not fresh cloves
            'krossad', 'krossade',  # "Vitlök Krossad 210g" — jarred crushed garlic, not fresh cloves
            'finhackad', # "Vitlök Finhackad Burk" — jarred minced garlic
            'marinerad', 'marinerade',  # "Vitlöksklyftor Marinerade" — preserved, not fresh
            'chili',    # "Vitlöksklyftor Chili" — marinated with chili, not fresh
        },
        # Fresh product blockers: if product has these → block dried/volume indicators
        'fresh_product_words': {
            'klass',      # "Vitlök Klass 1" = fresh produce
            'ekologisk',  # "Vitlök Ekologisk Klass 1"
            'fläta',      # "Vitlök Fläta Klass 1" = braided fresh garlic
            'kapsel',     # "Vitlök Kapsel Klass 1"
        },
        'dried_indicators': {
            'pulver',             # vitlökspulver
            'torkad', 'torkade',  # dried garlic
            'granulat',           # garlic granules
            'msk', 'matsked',     # volume = dried/jarred, not fresh
            'tsk', 'tesked',
            'krm',
        },
    },
    # --- Whole-vs-ground only (reverse direction) ---
    # These only need ground→block-whole; no forward spice_indicators needed.
    'mandel': {
        # "mald mandel" = ground almonds → block whole almond products
        # "mandel" (plain) = any form → allow all
        'blocked_product_words': set(),
        'ground_indicators': {'malen', 'mald', 'malna', 'malet'},
        'blocked_whole_product_words': {'hel', 'hela'},
    },
    'vitpeppar': {
        # Bidirectional: "vitpepparkorn"/"vitpeppar hel" blocks ground, and vice versa
        'spice_indicators': {'korn', 'hel', 'hela'},
        'blocked_product_words': {'malen'},  # whole ingredient → block ground products
        'ground_indicators': {'malen', 'mald', 'malna', 'malet'},
        'blocked_whole_product_words': {'hel', 'hela'},
    },
    'grönpeppar': {
        # "torkad grönpeppar" should keep the dry spice products, but not
        # preserved-in-brine peppercorns or explicitly whole peppercorn products.
        'spice_indicators': {'torkad', 'torkade'},
        'blocked_product_words': {'i lag'},
        'ground_indicators': {'torkad', 'torkade'},
        'blocked_whole_product_words': {'hel', 'hela'},
    },
    'gronpeppar': {
        'spice_indicators': {'torkad', 'torkade'},
        'blocked_product_words': {'i lag'},
        'ground_indicators': {'torkad', 'torkade'},
        'blocked_whole_product_words': {'hel', 'hela'},
    },
    'muskot': {
        # "muskot malen" → block "Muskotnöt Hel Påse" (whole nutmeg)
        # Key is 'muskot' (short form) so it matches ingredient "muskot malen"
        # matched_keyword 'muskotnöt' finds this via prefix match in recipe_matcher
        'blocked_product_words': set(),
        'ground_indicators': {'malen', 'mald', 'malna', 'malet'},
        'blocked_whole_product_words': {'hel', 'hela'},
    },
    'anis': {
        'blocked_product_words': set(),
        'ground_indicators': {'malen', 'mald', 'malna', 'malet'},
        'blocked_whole_product_words': {'hel', 'hela'},
    },
    'svamp': {
        # "torkad svamp (15 g/liter)" = dried mushrooms — should NOT match fresh mushroom
        # products like "Portabello Svamp Klass 1" or "Enoki Svamp Kl1".
        # No spice_indicators needed — only Check B (fresh product vs dried ingredient).
        'blocked_product_words': set(),
        'fresh_product_words': {
            'klass', 'kl1',       # quality class = fresh produce
            'färsk', 'färska',
            'eko',                # organic fresh
            'import',             # "Skogschamp Svamp Import Klass 1"
        },
        'dried_indicators': {
            'torkad', 'torkade',
        },
    },
    'ingefära': {
        # "Ingefära Malen" (ground ginger spice) ≠ fresh "Ingefära" (ginger root)
        # Fresh products are just "Ingefära" (no qualifier), so we can't block by word.
        # Instead: use Check E (required_ground_product_words) — when ingredient says
        # "malen", require product to have a processing indicator.
        'blocked_product_words': set(),
        'ground_indicators': {'malen', 'mald', 'malna', 'malet', 'pulver'},
        'blocked_whole_product_words': set(),
        'required_ground_product_words': {'malen', 'mald', 'malet', 'malna', 'pulver', 'burk', 'påse'},
    },
    'gurkmeja': {
        # "Torkad gurkmeja" / "Malen gurkmeja" (ground turmeric) ≠ fresh "Gurkmeja" (turmeric root)
        # Same pattern as ingefära: fresh products are just "Gurkmeja" without qualifier.
        'blocked_product_words': set(),
        'ground_indicators': {'malen', 'mald', 'malna', 'malet', 'pulver', 'torkad', 'torkade'},
        'blocked_whole_product_words': set(),
        'required_ground_product_words': {'malen', 'mald', 'malet', 'malna', 'pulver', 'burk', 'påse'},
    },
    'nejlika': {
        # Singular form shows up in some precomputed keyword paths even when the
        # ingredient normalizes to plural, so keep whole-vs-ground coverage in both.
        'spice_indicators': {'hel', 'hela'},
        'blocked_product_words': {
            'malda', 'malen', 'mald',
        },
        'ground_indicators': {'malda', 'malen', 'mald', 'malna'},
        'blocked_whole_product_words': {'hel', 'hela'},
    },
    'nejlikor': {
        # "Nejlikor Malda" (ground cloves) ≠ "Nejlikor Hela" (whole cloves)
        # Bidirectional: block wrong form in both directions
        'spice_indicators': {'hel', 'hela'},
        'blocked_product_words': {
            'malda', 'malen', 'mald',  # ground cloves
        },
        'ground_indicators': {'malda', 'malen', 'mald', 'malna'},
        'blocked_whole_product_words': {'hel', 'hela'},
    },
    'kryddpeppar': {
        # "Kryddpeppar Malen Burk" (ground allspice) ≠ "Kryddpeppar Hel Påse" (whole berries)
        'spice_indicators': {'hel', 'hela', 'korn'},
        'blocked_product_words': {
            'malen', 'mald',  # ground allspice
        },
        'ground_indicators': {'malen', 'mald', 'malna', 'malet'},
        'blocked_whole_product_words': {'hel', 'hela'},
    },
    'kummin': {
        # "Kummin Hel Påse" (whole caraway seeds) ≠ "Malen Kummin Burk" (ground)
        'spice_indicators': {'hel', 'hela'},
        'blocked_product_words': {
            'malen', 'mald',  # ground caraway
        },
        'ground_indicators': {'malen', 'mald', 'malna', 'malet'},
        'blocked_whole_product_words': {'hel', 'hela'},
    },
}

# Pre-normalized for performance
SPICE_VS_FRESH_RULES: Dict[str, Dict[str, Set[str]]] = {}
for k, v in _SPICE_VS_FRESH_RULES_RAW.items():
    key = fix_swedish_chars(k).lower()
    entry = {
        'blocked_product_words': {fix_swedish_chars(w).lower() for w in v['blocked_product_words']},
    }
    if 'spice_indicators' in v:
        entry['spice_indicators'] = {fix_swedish_chars(w).lower() for w in v['spice_indicators']}
    if 'allowed_indicators' in v:
        entry['allowed_indicators'] = {fix_swedish_chars(w).lower() for w in v['allowed_indicators']}
    if 'fresh_product_words' in v:
        entry['fresh_product_words'] = {fix_swedish_chars(w).lower() for w in v['fresh_product_words']}
        entry['dried_indicators'] = {fix_swedish_chars(w).lower() for w in v['dried_indicators']}
    if 'pickled_indicators' in v:
        entry['pickled_indicators'] = {fix_swedish_chars(w).lower() for w in v['pickled_indicators']}
        entry['pickled_product_words'] = {fix_swedish_chars(w).lower() for w in v['pickled_product_words']}
    if 'ground_indicators' in v:
        entry['ground_indicators'] = {fix_swedish_chars(w).lower() for w in v['ground_indicators']}
        entry['blocked_whole_product_words'] = {fix_swedish_chars(w).lower() for w in v['blocked_whole_product_words']}
        if 'required_ground_product_words' in v:
            entry['required_ground_product_words'] = {fix_swedish_chars(w).lower() for w in v['required_ground_product_words']}
    if 'required_whole_product_words' in v:
        entry['required_whole_product_words'] = {fix_swedish_chars(w).lower() for w in v['required_whole_product_words']}
    SPICE_VS_FRESH_RULES[key] = entry
