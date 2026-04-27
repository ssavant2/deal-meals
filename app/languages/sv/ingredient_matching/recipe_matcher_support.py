"""
Swedish recipe-matcher support constants.

These values are consumed primarily by `recipe_matcher.py`, but are re-exported
through `languages.sv.ingredient_matching` for backwards compatibility.
"""

# Fond/buljong type context matching:
# Maps type words found in ingredient text -> valid product name words.
# If ingredient has a type word (e.g. "kyckling"), only products with matching words are allowed.
# If ingredient has NO type word (generic "fond"), all products pass.
FOND_TYPE_CONTEXT = {
    'kyckling': {'kyckling', 'kycklingfond', 'höns', 'hons'},
    'höns': {'kyckling', 'kycklingfond', 'höns', 'hons'},
    'hons': {'kyckling', 'kycklingfond', 'höns', 'hons'},
    'kött': {'kött', 'kott', 'kalv', 'ox', 'nöt', 'not'},
    'kott': {'kött', 'kott', 'kalv', 'ox', 'nöt', 'not'},
    'kalv': {'kött', 'kott', 'kalv', 'ox', 'nöt', 'not'},
    'grönsak': {'grönsak', 'gronsak', 'vegetable'},
    'gronsak': {'grönsak', 'gronsak', 'vegetable'},
    'fisk': {'fisk', 'hummer', 'skaldjur'},
    'hummer': {'fisk', 'hummer', 'skaldjur'},
}

# Contextual cheese: flag use-case cheeses that match the recipe type.
# gratängost for gratäng recipes, texmexost for taco recipes, etc.
CHEESE_CONTEXT = {
    'gratängost': {'gratäng', 'gratang', 'gratin'},
    'gratangost': {'gratäng', 'gratang', 'gratin'},
    'texmexost': {'taco', 'texmex', 'tex-mex', 'fajita', 'burrito', 'enchilada', 'quesadilla', 'nachos'},
    'tacoost': {'taco', 'texmex', 'tex-mex', 'fajita', 'burrito', 'enchilada', 'quesadilla', 'nachos'},
    'pizzaost': {'pizza'},
    'hamburgerost': {'hamburgare', 'burger', 'burgare'},
}

# Seasoning compounds to remove before classification.
# "kycklingbuljong" alone shouldn't classify a vegetarian recipe as meat.
SEASONING_COMPOUNDS = {
    'kycklingbuljong', 'honsbuljong', 'hönsbuljong',
    'kalvbuljong', 'kalvfond', 'nötbuljong', 'nötfond', 'notbuljong', 'notfond',
    'kycklingfond', 'fiskbuljong', 'fiskfond',
    'kycklingpulver', 'hönspulver', 'honspulver',
    'kyckling buljongtärning', 'kyckling buljongtarning',
    'kycklingbuljongtärning', 'kycklingbuljongtarning',
}

# Vegetarian/vegan labels for recipe classification priority
VEGETARIAN_LABELS = ['vegetarisk', 'vegansk', 'vegan ', 'vego']

# Swedish plural/inflection suffixes safe to allow after a keyword
# e.g., 'tomat' + 'er' = 'tomater' (plural), 'lök' + 'ar' = 'lökar'
# But NOT 'färs' + 'k' = 'färsk' (different word)
SAFE_SUFFIXES = {'er', 'ar', 'or', 'en', 'et', 'na', 'n', 's'}

# Buljong type prefixes - detect which type of broth the recipe requests.
# If none match, default to grönsaksbuljong (vegetable broth).
BULJONG_TYPE_PREFIXES = frozenset({
    'kyckling', 'höns', 'hons', 'fisk', 'kött', 'kott',
    'svamp', 'ox', 'kalv', 'skaldjur', 'lant', 'grönsak',
    'gronsak', 'umami', 'örtagård', 'hummer',
})

# Default buljong type words - when recipe says generic "buljong", only allow these
BULJONG_DEFAULT_WORDS = ('grönsak', 'gronsak')

# Compound suffixes for keyword->group assignment (word-boundary checks)
# e.g., "köttbuljong" in "köttbuljongtärning" - 'tärning' is a valid compound suffix
KEYWORD_COMPOUND_SUFFIXES = (
    'erna', 'er', 'ar', 'or', 'na', 'en', 'n', 'r', 's',
    'tärning', 'tärningar',
    'bröd', 'brod', 'deg',
    'kaka', 'ost', 'blad', 'huvud',
    'flingor',
)

# Promotion suffixes - shorter keyword promoted to longer compound
# e.g., herrgård->herrgårdsost, präst->prästost
PROMOTION_COMPOUND_SUFFIXES = ('sost', 'ost', 'mjölk', 'mjolk')

# Pasta-type keywords (kort + lång) - used for "färsk pasta" check
PASTA_KEYWORDS = frozenset({
    # Kort pasta
    'pasta', 'fusilli', 'penne', 'rigate', 'farfalle', 'rigatoni',
    'conchigle', 'conchiglie', 'gemelli', 'radiatori', 'tortiglioni',
    'caserecce', 'girandole', 'strozzapreti', 'strozzapretti',
    'ziti', 'mafalda', 'maniche', 'maccaronetti', 'makaroner',
    'risoni', 'snabbmakaroner',
    # Lång pasta
    'långpasta', 'langpasta', 'spaghetti', 'spagetti', 'linguine',
    'tagliatelle', 'fettuccine', 'fettucine', 'pappardelle',
    'tagliolini', 'bucatini', 'capellini',
})

# Freshness indicators - used to check if recipe requires fresh products
FRESH_WORDS = ('färsk', 'farsk')

# --- Regex pattern components (Swedish words used in ingredient normalization) ---
# These are used to build regex patterns in recipe_matcher.py

# Preference parenthetical words: "(gärna med X)", "(helst Y)"
PREFERENCE_PAREN_WORDS = r'gärna|garnaå?|helst|om möjligt|om mojligt|beroende|t\.?\s*ex\.?|för \d'

# Explanatory parenthetical patterns to remove:
# "haricots verts (bönor)" - 'bönor' would match unrelated bean products
EXPLANATORY_PAREN_WORDS = r'bönor|böna|[^)]*hårdost[^)]*|[^)]*mjukost[^)]*|crabstick'

# Texture descriptors that share substrings with food keywords
# "mjöliga" (floury potato) contains "mjöl" (flour) -> false positive
TEXTURE_DESCRIPTOR_WORDS = r'mjöliga?|fastare?|filead|filéad'

# Negation words: "ej olivolja", "utan ägg" - recipe explicitly excludes
NEGATION_WORDS = r'ej|utan'

# Cooking instruction words after comma: "smör, att bryna löken i"
COOKING_INSTRUCTION_WORDS = r'att|till'

# Purpose phrase words: "olja till marinad"
PURPOSE_PHRASE_WORDS = (
    r'marinad|stekning|servering|garnering|fritering|pensling'
    r'|formen|formarna|pannan|stekpannan|topping|wokning'
)

# Parenthetical instruction starters: "smör (att breda på brödskivorna)"
PAREN_INSTRUCTION_WORDS = r'att|används\s+till|anvands\s+till'

# Citrus fruit names for citrus usage parenthetical removal
CITRUS_FRUITS = r'citron|lime|apelsin|clementin|grape|blodapelsin|yuzu'

# Soda word for junk food filtering
SODA_WORD = 'läsk'

# --- Single-word constants used in recipe_matcher.py matching logic ---
# These are Swedish words referenced in if-statements and keyword comparisons.
BULJONG_WORD = 'buljong'
FOND_WORD = 'fond'
SPARRIS_WORD = 'sparris'
BITAR_WORD = 'bitar'
KALKON_WORD = 'kalkon'
HELKALKON_WORD = 'helkalkon'
CHIPS_WORD = 'chips'
ELLER_WORD = 'eller'

# Meat/poultry keywords for recipe classification (HIGH PRIORITY - indicates meat dishes)
# NOTE: Include word stems for Swedish compound words (e.g., "skink" for "skinkröra")
CLASSIFICATION_MEAT_KEYWORDS = [
    # Swedish meat terms
    'kött', 'fläsk', 'oxkött', 'kalv', 'lamm', 'kyckling', 'anka',
    'bacon', 'skinka', 'skink', 'korv', 'salami', 'salsiccia', 'chorizo',
    # NOTE: 'färs' removed - too generic, matches 'färska' (fresh)
    # Use specific forms: nötfärs, blandfärs, köttfärs below
    'biff', 'filé', 'entrecote', 'fågel', 'höns',
    # Cured/smoked meats
    'kassler', 'prosciutto', 'pancetta', 'speck', 'bresaola', 'mortadella',
    # More Swedish meats
    'fläskkarré', 'fläskfilé', 'kotlett', 'revben', 'sidfläsk',
    'nötfärs', 'blandfärs', 'köttfärs', 'kycklingfilé', 'kalkon',
    'pulled pork', 'rökt', 'rimmat',
    # French meat terms (common in recipe names)
    'boeuf', 'boef', 'poulet', 'coq', 'canard', 'porc', 'agneau', 'veau',
    'bourguignon',
    # Spanish/Italian meat terms
    'carne', 'pollo', 'cerdo', 'asado', 'cordero', 'maiale', 'manzo',
    # English meat terms
    'beef', 'chicken', 'pork', 'lamb', 'duck', 'turkey',
    # Swedish classic meat dishes
    'gulasch', 'wallenbergare', 'köttpaj', 'fläskpannkaka',
    'flankstek', 'flank', 'entrecôte', 'högrev', 'innanlår', 'fransyska',
    'oxfilé', 'ryggbiff', 'tjockstek', 'nötkarré',
    # Taco/Mexican with meat
    'carnitas', 'carne asada',
    # Game meats (vilt)
    # NOTE: 'hjort' removed - matches 'hjortron' (cloudberry). Use specific forms instead.
    'vildsvin', 'älg', 'rådjur', 'hjortstek', 'hjortfilé', 'hjortfärs',
    'hjortgryta', 'hjortinnanlår', 'dovhjort',
    'ren', 'vilt', 'hare', 'fasan', 'ripa', 'kanin',
    # Swedish sausages and specialties
    'isterband', 'falukorv', 'medister', 'prinskorv', 'blodpudding', 'blodkorv',
    'presssylta', 'fläsklägg', 'grisfötter',
    # Compound/missed meat words
    'rostbiff', 'kabanoss', 'bratwurst', 'pepperoni',
    'parmaskinka', 'serranoskinka',
    'spareribs', 'nduja', 'guanciale',
    # Ox-compounds (word-start boundary misses these)
    'oxstek', 'oxrulad', 'oxsvans', 'oxgryta', 'oxtunga', 'oxbringa',
    # Löv-biff compounds (21 recipes with lövbiff)
    'lövbiff', 'lovbiff',
    # Jul/fest compounds
    'julskinka', 'julkorv', 'julprosciutto',
    # Ren (reindeer) compounds - 'ren' is too short for substring matching
    'renstek', 'renskav', 'renfilé', 'renfärs',
    # Korv/fläsk compounds (word-start boundary misses these)
    'stekfläsk', 'frukostkorv', 'ölkorv', 'fuetkorv',
]

# Fish/seafood keywords for recipe classification (HIGH PRIORITY)
CLASSIFICATION_FISH_KEYWORDS = [
    # Swedish fish terms
    'fisk', 'lax', 'torsk', 'sej', 'sill', 'räk', 'räkor', 'skaldjur',
    'hummer', 'krabba', 'musslor', 'abborre', 'gädda', 'gös', 'tonfisk',
    'ansjovis', 'sardell', 'makrill',
    # More seafood
    # NOTE: 'hav'/'havs' removed - too generic, matches 'havregryn', 'havssalt'
    'kräfta', 'kräft', 'kräftsoppa', 'sjötunga', 'rödspätta',
    'piggvar', 'kolja', 'röding', 'öring', 'ål', 'kaviar', 'löjrom',
    # Swedish fish dishes
    'jansson', 'frestelse',  # Janssons frestelse (has anchovies)
    # Swedish fish missed by word-boundary (compound words)
    'strömming', 'lutfisk', 'sashimilax', 'böckling', 'flundra',
    # Havs-compounds (word-start boundary misses these)
    'havsaborre', 'havskräfta', 'havskräftor', 'havskatt',
    # Regnbågs-compounds (regnbågsforell, regnbågsfilé = rainbow trout)
    'regnbågsforell', 'regnbågsfilé', 'regnbågslax', 'regnbågsöring',
    # Other fish compounds
    'insjöfisk', 'havslax',
    # Sill-compounds (40+ recipes: matjessill, senapssill, etc.)
    'matjessill', 'senapssill', 'citronsill', 'kryddsill', 'pepparrotssill',
    'lingonsill', 'limesill', 'currysill', 'sherrysill', 'sesamsill',
    'löksill', 'gräslökssill', 'ouzosill', 'tofusill',
    'hjortronsill', 'basilikasill', 'chilisill', 'kumminsill',
    'citrongrässill', 'rucolasill', 'kaprissill', 'vinbärssill',
    'västerbottenssill', 'västerbottensill', 'rödbetssill',
    'ingefärssill',
    # Musslor-compounds (blåmusslor, pilgrimsmusslor)
    'blåmusslor', 'pilgrimsmusslor', 'kammusslor',
    # Forell compounds
    'forellrom',
    # International
    'salmon', 'shrimp', 'prawn', 'lobster', 'crab', 'mussel', 'oyster',
    'calamari', 'bläckfisk', 'scampi',
]
