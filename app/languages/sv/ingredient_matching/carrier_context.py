"""Carrier/context rule data for Swedish ingredient matching.

Used by:
- extraction.py — carrier products strip flavor words during keyword extraction
- matching.py — context-required and suppressed-by-context checks
"""

from typing import Dict, FrozenSet, Set

try:
    from languages.sv.normalization import fix_swedish_chars
except ModuleNotFoundError:
    from app.languages.sv.normalization import fix_swedish_chars


# ============================================================================
# FLAVORED PRODUCTS - Carrier products + flavors = don't extract flavor as keyword
# ============================================================================

# Carrier products that are often flavored (the BASE product)
# These products CONTAIN ingredients as flavors, not AS the ingredient
CARRIER_PRODUCTS: FrozenSet[str] = frozenset({
    'färskost', 'farskost', 'cream cheese',
    'lättost', 'lattost',  # "Lättost Räkor" - sandwich cheese, räkor is flavor
    'smältost', 'smaltost',  # "Smältost Chili cheddar" - processed cheese spread
    # NOTE: 'burgar' NOT added as carrier — "Cheddar Burgar" is real cheese that
    # should match cheddar recipes. Accepts minor tryffel FP from one product.
    'philadelphia',  # cream cheese brand ("Vitlök & Örter 28% Philadelphia" is NOT garlic)
    'örter',  # "Vitlök & Örter 28%" — vitlök is flavor on cream cheese, not standalone garlic
    'pesto',  # pesto contains cheese/nuts but is a sauce, not those ingredients
    'creme fraiche', 'crème fraiche', 'créme fraiche',  # flavored creme fraiche
    'chips', 'dip', 'dipmix', 'dippsås', 'crostini',
    'dumplings',  # "Dumplings Biff/Kyckling/Vegetarisk" — flavor is filling type, not ingredient
    'edamame',  # "Edamame Rostade Havssalt & Olivolja" — roasted snack, olivolja/salt are preparation
    'olivolja',  # "Olivolja Citron Extra Virgin" — citron is flavor
    'breoliv',  # "BreOliv Olivolja & sheanötter" — spread, olivolja is component not standalone oil
    'breton',  # "Breton Olivolja & basilika" — crackers, olivolja is flavor
    'pommes',  # "Pommes Wavy Blends Paprika" - paprika is flavoring
    'glass',  # ice cream ("Glass Jordgubb" — jordgubb is flavor, glass keyword survives via ISK)
    'tårtbotten', 'tartbotten',  # "Tårtbotten Choklad 3-delad" — choklad is variant, not ingredient
    'marmelad', 'marmelade',  # "Orange Whisky Marmelade" — whisky is flavor, not ingredient
    'drömmar', 'drommar',  # "Drömmar Chokladsmak" — cookie brand, chokladsmak is flavor variant
    'sorbet',  # sorbet products (fruit flavor is preparation, not ingredient)
    'müsli', 'musli', 'flingor',  # granola/muesli products
    'havrebites',  # oat snack bites ("Havrebites Jordgubb" is NOT jordgubbar)
    'havregott',  # oat yoghurt ("Havregott Jordgubb" — jordgubb is flavor)
    'havrefras',  # oat cereal ("Havrefras Jordgubb" — jordgubb is flavor)
    'havrekuddar',  # oat cereal pillows ("Havrekuddar kakao" — kakao is flavor)
    'mannafrutti',  # yoghurt brand ("Jordgubb Mannafrutti" — fruit is flavor)
    'sipper',  # drink straw ("Magic Sipper Jordgubb" — fruit is flavor)
    'krisp',  # cereal ("Krisp Jordgubb Havre" — fruit is flavor)
    'vispgrädde', 'vispgradde',  # "Cuisine vispgrädde Soja" — soja is variant, not ingredient
    'matlagningsgrädde', 'matlagningsgradde',  # "Matlagningsgrädde Soja" — soja is variant
    'kokosgurt',  # "Coconut Natural Kokosgurt" — kokos is base, not flavor → strips 'kokos' keyword
    'riven kokos',  # "Riven Kokos 200g ICA" — kokos is the product, riven is preparation
    'kvarg',  # "Kvarg Vanilj" - vanilj is flavor, kvarg is the product
    'fruktkvarg',  # "Jordgubb Hallon Fruktkvarg" — fruit is flavor
    'drickyoghurt',  # "Jordgubb Drickyoghurt" — fruit is flavor
    'vaniljyoghurt',  # "Hallon Slät Vaniljyoghurt" — hallon is flavor, not ingredient
    'filmjölk', 'filmjolk',  # "Jordgubb Filmjölk 2,7%" — fruit is flavor
    'filjmjölk', 'filjmjolk',  # typo variant of filmjölk in product names
    'fjällfil', 'fjallfil',  # "Fjällfil Blåbär" - blåbär is flavor, fjällfil is the product
    'norrskensfil',  # "Norrskensfil Winter Strawberry Lime" — lime is flavor (995 FP recipes)
    'juice', 'saft', 'läsk', 'lask',
    'soda',   # "Pepsi Max Lime Soda Mix" — soft drink, not ingredient
    'zingo',  # soft drink brand ("Zingo Citron" is NOT citron)
    'korv',  # "paprikakorv" etc - flavor words shouldn't match recipes
    'bratwurst',  # "Bratwurst Kummin & vitlök" - spices are flavoring
    'ketchup',  # "Ketchup Svartpeppar" — svartpeppar is flavor variant
    'bbqsås', 'bbqsas', 'bbq sauce',  # "BBQ Sauce Bourbon" — bourbon is flavor variant, not whiskey
    'wrap',  # "Wrap Kallrökt Lax" — ready-to-eat meal, lax is filling
    'smördeg', 'smordeg',  # "Smördeg på smör" — smör describes the dough, not standalone butter
    'pajdeg',  # "Pajdeg med smör" — same
    'rödbetssallad', 'rodbetssallad',  # "Rödbetssallad med Crème Fraiche" — fraiche is variant, not ingredient
    'matfett',  # "Matfett Smör & Raps 58%" - margarine, NOT butter
              # (Arla Köket "Smör- & rapsolja" has no "matfett" → unaffected)
    'bredbart',  # "Bredbart Ekologisk med Raps Shea, Kokos" — spread, kokos is base not flavor
    'kolbász', 'kolbasz',  # "Kolbász Paprika & vitlök" - Hungarian sausage
    'chorizo', 'choritzo',  # "Chorizo Cayenne & paprika" - Spanish sausage
    'kabanoss',  # "Kabanoss Paprika & Kummin" - Polish sausage with spices
    # Seafood with flavor/spice names
    'hälleflundra',  # "Hälleflundra panerad citron & persilja" — citron/persilja are flavoring
    'makrillfiléer', 'makrillfileer', 'makrillfieer',  # ICA has typo "Makrillfiéer" (missing l)
    'taggmakrillfiléer', 'taggmakrillfileer',  # "Makrillfiléer Citrontimjan" — herb is flavoring
    'räkor', 'rakor', 'räka', 'raka',  # "Räkor Paprika Vitlök" - paprika/vitlök are flavoring
    # Bread products with flavors
    'baguett', 'baguetter', 'bröd', 'focaccia',  # "Focaccia Tomat" - tomat is flavor
    # Fond/buljong with flavors
    'fond', 'viltfond', 'fiskfond', 'kycklingfond', 'oxfond',
    # Filled pasta (spenat/ricotta are fillings, not ingredients)
    'ravioli', 'tortellini', 'cannelloni', 'tortelloni',
    # Ready meals - NOT ingredients!
    'pulled pork', 'pulled chicken',
    'ätklar', 'ätklart',  # "Ätklar Taco Kyckling Skivad" / "Soltorkad Tomat Ätklart Kyckling" — pre-cooked meat
    'kyckling drumsticks',  # "Kyckling Drumsticks Örter & Vitlök" - flavored chicken, vitlök is seasoning
    # NOTE: kycklingbröst REMOVED — blocked raw/frozen chicken products.
    # Pre-seasoned products like "Grillkryddad Kycklingfilé" handled by carrier detection.
    # Noodle products — strip flavor words (kyckling, beef, spicy) but keep nudlar keyword
    # so space norms can transform "Nudlar Udon" → "udonnudlar", "Äggnudlar" stays as-is
    'nudlar', 'noodles', 'noodle',
    'äggnudlar',  # "Äggnudlar Kyckling Grönsaker" → strips kyckling/grönsaker, keeps äggnudlar
    'färdigmat', 'färdig mat',  # "Färdigmat Kyckling Curry" is NOT kyckling
    'lasagne', 'lasagnette',  # ready meals with various fillings
    'pizza', 'ristorante',  # "Pizza Ristorante Mozzarella" is NOT mozzarella
    # Soups - flavored with ingredients, not the ingredient itself
    'soppa', 'soppor', 'buljong',  # "Soppa Potatis" is NOT potatis
    # Sauces - contain but aren't the ingredient
    'sås', 'såser',  # "Vitlök & Parmesansås" is NOT vitlök
    'bearnaise',  # "Chipotle Bearnaise" - chipotle is flavor, not standalone chipotle
    # Crisp bread / crackers
    'knäcke', 'knäckebröd', 'knacke', 'knackebrod',  # "Havssalt Knäcke" is NOT havssalt
    'kex', 'kakor',  # "Tuc Paprika" is NOT paprika, "Ballerina" cookies
    # Italian almond-biscuit family is also used as a bought recipe ingredient.
    # Keep the biscuit identity, but strip flavor words like mandel/choklad.
    'cantuccini', 'cantucci', 'biscotti',

    # Chocolate pralines — strip flavor words (mjölk, mint, hallon, pistage) but keep chokladpralin
    # So "LINDOR Mjölk" → keyword 'chokladpralin' only (not 'mjölk')
    # 9 recipes use chokladpraliner as ingredient, so we can't fully block
    'chokladpralin', 'chokladpraliner',

    # Flavored fats/oils (citron/herbs are flavor, not ingredient)
    'messmör', 'messost',  # "Messmör Citron" — citron is flavor
    'rapolja',  # "Rapolja Citron" — citron is flavor

    # Flavored soy/plant-based dairy (fruit is flavor)
    'sojayoghurt', 'soyayoghurt', 'sojagurt',  # "Sojayoghurt Jordgubb" is NOT jordgubb
    'plantgurt',  # "Plantgurt Mango" is NOT mango
    'havregurt',  # "Baked Äpple Havregurt" — äpple is flavor, not ingredient

    # Tea/herbal products (ingredients are flavoring)
    'rooibos',  # "Rooibos Ingefära & citron" is NOT ingefära

    # Baked goods / confectionery (fruit is flavor/decoration)
    'mousse', 'proteinmousse',  # "Citron Mousse High Protein" — citron is flavor, not fresh lemon
    'pudding', 'proteinpudding', 'proteindessert',  # "Pudding Choklad" — dessert, not ingredient
    'marängtoppar', 'maräng',  # "Marängtoppar Jordgubb" is NOT jordgubb
    'figurmarsipan', 'marsipan',  # "Figurmarsipan Jordgubb" is NOT jordgubb
    'fruktrullar',  # "Fruktrullar Jordgubb" — dried fruit snack
    'frukosthjärtan',  # "Frukosthjärtan med Jordgubbar" — cereal, NOT jordgubbar
    'panna cotta',  # "Dessert Panna Cotta Jordgubb" is NOT jordgubb
    'dessertbägare',  # "Dessertbägare Hallon/Choklad" — bakery, fruit/choklad is flavor
    'jelly',  # "Jelly Hallon" — gelatin dessert, hallon is flavor
    'småmål',  # "Småmål Kokos med hallon" — dairy snack, hallon is flavor
    'glasspinnar', 'glasspinne',  # "Glasspinnar Mumsbit mandel" — ice cream, mandel is flavor

    # Flavored dairy (fruit is flavor, not ingredient)
    'gourmetyoghurt',  # "Gourmetyoghurt Hallon" — yoghurt, hallon is flavor
    'soygurt',  # "Soygurt Persika Hallon" — soy yoghurt, fruit is flavor
    'havregrädde', 'havregradde',  # "Havregrädde Cooking Oat Lök" — oat cream, lök is flavor
    'havrering',  # "Havrering Mandel & Hasselnöt" — cereal, nuts are mix-ins

    # Juice/must brands and generic must (fruit is flavor)
    'kullamust',  # "Kullamust Äpple & hallon" — must drink, fruit is flavor
    'must',  # "Must Äpple utan fruktkött" — generic must, fruit is flavor
    'champion',  # "Champion Apelsin/Blåbär" — juice brand, fruit is flavor

    # Cookies/cakes (fruit is flavor)
    'kaka',  # "Kaka Äpple & kola" — cookie, äpple is flavor (plural 'kakor' already carrier)

    # Flavored water (fruit is flavor)
    'vatten',  # "Vatten Granatäpple Lime" — flavored water, fruit is flavor

    # Vinegar (ingredient name is the vinegar BASE, not the ingredient itself)
    'vinäger', 'vinager',  # "Vinäger Schalottenlök" — shallot vinegar ≠ fresh shallots

    # Sparkling/flavored drinks
    'bubbelte',  # "Bubbelte Jordgubb" is NOT jordgubb
    'bubbliz',  # "Bubbliz jordgubb" is NOT jordgubb
    'icetea',  # "Icetea Citron & lime" is NOT citron

    # Trail mix / nut mix — 'nöt' means nut, not beef (nötkött)
    'bärmix', 'barmix',    # "Nöt & Bärmix" — nöt is nut, not beef
    'tranbärsmix', 'tranbarsmix',  # "Nöt & Tranbärsmix" — same
    'nötmix', 'notmix',    # generic nut mix

    # Chocolate products (flavored with nuts, fruits, etc)
    'chokladkaka', 'choklad',  # "Chokladkaka Frukt & Mandel" is NOT mandel
    'chokladsmak',  # "Mjölk UHT med chokladsmak" — choklad-flavored milk is NOT plain mjölk

    # Candy / confectionery (fruit/nut names are flavors, not ingredients)
    'lakrits',  # "Lakrits Salt Hallon" — hallon is candy flavor, not fresh berries
    'chews',  # "Ginger Chews Jordnöt" — jordnöt is flavor in candy, not raw peanuts

    # Frozen bakery/snack (fillings are not standalone ingredients)
    'pizzabullar', 'pizzabulle',  # "Pizzabullar med tomat och ost" — tomat/ost are fillings
    'våffelstrut', 'våffelstrutar',  # "Våffelstrutar hallon" — hallon is flavor/decoration

    # Nut/seed spreads (oils are component, not standalone)
    'hasselnötskräm', 'hasselnötskram',  # "Hasselnötskräm Solrosolja" — solrosolja is component

    # Pizza kits (contain ingredients as toppings)
    'pizzakit',  # "Pizzakit Surdeg" is NOT surdeg

    # Chips variants
    'potatiships',  # "Potatiships Rödlök" is NOT rödlök (chips already in list)

    # Dressings (contain ingredients as flavors)
    'dressing', 'ceasardressing', 'salladdressing',  # NOT the base sauce

    # Smoothies and drinks (fruits as flavors)
    'smoothie', 'smoothies',  # "Smoothie Tropiska Frukter" / "Frukt till smoothies" is NOT frukter
    'milkshake', 'proteinmilkshake', 'proteindryck',  # protein drinks with flavors

    # Flavored dairy drinks (fruit/flavor words are NOT ingredients)
    'drickkvarg',  # "Drickkvarg Mango" is NOT mango
    'proteinkvarg',  # "Proteinkvarg Jordgubb" is NOT jordgubb
    'proteinyoghurt',  # "Proteinyoghurt Hallon" is NOT hallon

    # Granola/cereals/porridge (contain ingredients as mix-ins/flavors)
    'granola',  # "Granola Hazelnut & Cashew" is NOT cashew
    'rismål', 'rismal',  # "Rismål Jordgubb" - flavored rice porridge, NOT jordgubb

    # Vegan deli products (flavored slices)
    'vegoskivor', 'vegopålägg',  # "Vegoskivor Basilika" is NOT basilika
    # NOTE: 'växtbaserad' REMOVED from carriers — it's a descriptor (like 'ekologisk'),
    # not a product category. Handled via STOP_WORDS instead.

    # Sausages/charcuterie with flavor ingredients
    'salsiccia',  # "Salsiccia vitlök och örter" - vitlök is flavoring, not the ingredient
    'salami',  # "Lindösalami Soltorkad Tomat" - tomat is flavoring
    'salamini',  # "Salamini Tryffel 85g" - tryffel is flavoring in mini salami
    'salamisticks',  # "Salamisticks Tryffel 80g" - tryffel is flavoring
    'fuet',  # "Fuet Tryffel 150g" - Spanish dry-cured salami, flavor words shouldn't match
    'mortadella',  # "Mortadella Kyckling Paprika" - kyckling/paprika are flavors in deli meat

    # Spice mixes/rubs - flavor ingredients are NOT standalone
    'spice mix',  # "Taco Spice Mix Chili & Lime" - lime is flavoring, not fruit
    'rub',  # "BBQ rub Chili" — chili is flavor in dry rub, not fresh chili

    # Fresh pasta (filled with ingredients)
    'färsk pasta',  # "Färsk Pasta Tortelloni Prosciutto" is NOT prosciutto

    # Grillost / cheese with flavors — chili/paprika are flavoring
    'grillost',
    'gouda',  # "Gouda Tärningar Chili" — chili is flavor on cheese

    # Frozen snacks with fillings
    'pirog',  # "Pirog chili cheese" — chili is filling flavor
    'pilsnerpinnar',  # "Pilsnerpinnar Chili" — chili is snack flavor

    # Pickled products with flavors
    'cornichons',  # "Cornichons Vitlök Chili" — vitlök/chili are flavoring on pickles

    # Flavored cooking cream
    'matgrädde', 'matgradde',  # "Matgrädde Paprika Chili" — paprika/chili are flavor variants

    # Sparkling/flavored water - "Kolsyrat vatten Hallon Rabarber" is NOT rabarber
    'kolsyrat',
    'kolsyratvatten',  # compound: "Äpple Kolsyratvatten Pet" (NOT äpple)
    'vitaminvatten',  # "Hallon Vitaminvatten" (NOT hallon)
    'funktionsvatten',  # "Defence Citrus/fläder Funktionsvatten" (NOT citrus)
    'smaksatt vatten',  # "Smaksatt Vatten Sour Apple 80cl Zeroh" is NOT äpple

    # Bakery products with spice/flavor names - "Mazariner Saffran" is NOT saffran
    'mazariner', 'mazarin',

    # Pasta-based ready meals - "Rigatoni kyckling pesto 380g Felix" is NOT kyckling
    'pasta',  # "Pasta Pomodoro Ricotta Fryst Felix" → keep 'pasta', strip pomodoro/ricotta
    'rigatoni', 'penne', 'fusilli', 'tagliatelle', 'linguine', 'fettuccine',
    'farfalle', 'conchiglie', 'conchigle', 'gemelli', 'gnocchi', 'radiatori',
    'tortiglioni', 'caserecce', 'girandole', 'strozzapreti', 'strozzapretti',
    'mafalda', 'maniche', 'ziti',

    # NOTE: 'krämig' REMOVED from CARRIER_PRODUCTS — STOP_WORDS already handles it,
    # and keeping it here stripped useful base keywords like `ost`.

    # Greek meat dishes - "Gyros Kyckling med Vitlökssås" is NOT kyckling
    'gyros',

    # Kebab products - "Kyckling Kebab Fryst" is NOT kyckling (but IS kebab)
    'kebab',

    # Mayo products - "Mayo Cactus & Lime" / "Majo Gochugaru Vitlök" is NOT lime/vitlök
    'mayo', 'majo',

    # Nut mixes - "Nötmix Honung & Salt" is NOT honung
    'nötmix', 'notmix',
    'nötter', 'notter',  # "Nötter Honung Trippel" - honung is coating, not honey

    # Beverages - "Dryck Svarta Vinbär Light" is NOT vinbär
    'dryck', 'dricka',  # "Persikadricka"/"Melondricka" — fruit drink, not fresh fruit
    'kombucha',  # fermented tea drink - "Apple Kombucha" is NOT äpple

    # Fruit snack bars - fruit is flavor, not fresh ingredient
    'fruktstänger', 'fruktstang', 'fruktstånger',  # "Fruktstänger blåbär" is NOT fresh blåbär

    # Potatoes (variety names aren't ingredients) - "Potatis Mandel" is NOT mandel (almonds)
    'potatis',

    # Note: 'kryddmix' removed from CARRIER_PRODUCTS - type words (tikka, paneng, etc.)
    # should be KEPT as keywords, not stripped. Specificity via PROCESSED_PRODUCT_RULES.
    # Note: 'krydda' NOT a carrier — conflicts with compound forms via space norm
    # (paprikakrydda → "paprika krydda" → carrier strips paprika). Handled via PROCESSED_FOODS.

    # Beverages - "Lemonad Citron" is NOT citron, "Fruktdryck Äpple" is NOT äpple
    'lemonad', 'fruktdryck',

    # Tea - "Earl Grey Citron Svart Te" is NOT citron, "Iste Citron" is NOT citron
    'te', 'iste',

    # Beer/cider - "Radler Citron Ljus Lager" is NOT citron
    'radler', 'lager',

    # Breakfast/porridge - "Gröt Blåbär" is NOT blåbär, "Grötkopp Äpple & Kanel" is NOT äpple
    'gröt', 'grot', 'grötkopp', 'grotkopp',

    # Popcorn - "Micropopcorn Smör" is NOT smör
    'popcorn', 'mikropopcorn', 'micropopcorn',

    # === ADDITIONS FROM WILLYS CATALOG ANALYSIS ===

    # Condiments/spreads (contain ingredient names as flavors)
    'leverpastej',  # "Leverpastej Gurka"/"Leverpastej Pepparrot" - flavor is packaging, keep 'leverpastej'
    'aioli',  # "Aioli Vitlök" - vitlök is the flavor, not an ingredient
    'hummus',  # "Hummus Soltorkad Tomat" - tomat is the flavor
    'guacamole',  # pre-made dip
    'labneh',  # "Labneh Vitlök&mynta" - yogurt spread with flavors
    'tzatziki',  # pre-made yogurt sauce
    'röra', 'rora',  # "Yoghurt & Feta Röra" - spread/dip, feta is flavor
    'potatissallad',  # "Potatissallad Vitlök" - vitlök is flavor, not standalone garlic
    'krossade tomater',  # "Krossade Tomater Vitlök" - vitlök is flavor on canned tomatoes
    'soltorkade tomater',  # "Soltorkade Tomater Örtmarinad" - örtmarinad is flavor
    'soltorkad tomat',  # "Soltorkad Tomat i Balsamvinäger" - balsamvinäger is flavor
    'soltork tomat',  # abbreviated form: "Soltork Tomat i Balsamvinäger"
    'solt tomat',  # abbreviated: "Pomodori Secchi ... Solt Tomat"

    # Ready meals where first word is flavor
    'risotto',  # "Risotto Svamp Vitlök" - frozen ready meal, not svamp/vitlök

    # Cheese with flavor (brand names)
    'cambozola',  # "Cambozola Vitlök" - flavored cheese, vitlök is not standalone
    'kryddost',  # "Kryddost Spiskummin & Nejlika 31%" - spices are flavorings, not standalone

    # Sauces (pre-made, flavors aren't ingredients)
    'kebabsås', 'kebabsas',  # "Kebabsås Vitlök" - vitlök is flavoring
    'pastasås', 'pastasas',  # "Pastasås Svamp Ost" - svamp/ost are flavors
    'grytbas', 'grytbaser',  # "Grytbas Curry" - curry is the flavor

    # Gratäng ready meals - "Potatisgratäng med Paprika" is NOT paprika
    'potatisgratäng', 'potatisgrätang',
    'gratäng', 'gratang',  # "Gratäng Paprika" - ready meal, paprika is flavor

    # Marinating products
    'marinad',  # "Kyckling Marinad" - kyckling is the target, not ingredient

    # Canned fish/seafood - oil/sauce is packaging, not the product
    'sardiner',  # "Sardiner Delikatessrökta i Rapsolja" - rapsolja is packaging
    'sardeller',  # "Sardeller I Olivolja" — olivolja is packaging medium
    'tonfisk',   # "Tonfisk i Solrosolja" - solrosolja is packaging
    'makrill',   # "Makrill i Tomatsås" - tomatsås is packaging
    'makrillbitar',  # "Makrillbitar i Tomatsås" — compound form, tomatsås is packaging
    'makrillfilé', 'makrillfile',  # "Makrillfilé i Tomatsås" — compound form
    'ansjovis',  # "Ansjovis i Olja" - olja is packaging
    'sill',      # "Sill i Dillmarinad" - dill is flavoring
    'sillskivor', 'sillskiva',  # "Sillskivor tomat" — tomat is flavor on herring

    # Sausage variants (compound words not caught by 'salsiccia' suffix check)
    'salsicciafärs', 'salsicciafars',  # "Salsicciafärs Fänkål" - fänkål is flavoring

    # Veggie burger/patty products
    'bönbiff', 'bonbiff',  # "Kål Bönbiff" - kål describes the biff, not standalone cabbage
    'ostbiff',  # "Spenat och ostbiff" — spenat is component in patty, not fresh spinach

    # Spice mix brands (contain salt/herb names as ingredients, not standalone)
    'herbamare',  # "Ört Havssalt Herbamare" - havssalt is an ingredient in spice mix

    # === BATCH 2: MORE ADDITIONS FROM WILLYS CATALOG (8245 products) ===

    # Preserves/jams - "Hallonsylt" should NOT match "hallon" recipe
    'sylt',  # 30 products (hallonsylt, jordgubbssylt, lingonsylt, etc.)
    'marmelad',  # 25+ products (apelsin marmelad, fikon marmelad, etc.)
    'gelé', 'gele',  # 7 products (svartvinbärsgelé, rödvinbärsgelé, etc.)

    # Beverages - fruit flavors should NOT match ingredient recipes
    'lättdryck', 'lattdryck',  # 16 products (björnbär hallon lättdryck, etc.)
    'blanddryck',  # 27 products (mango lemon blanddryck, etc.)
    'cider',  # 15 products (päroncider, jordgubb lime cider, etc.)
    'nektar',  # 6 products (apelsin nektar, tropisk nektar, etc.)
    'proteinshake',  # "Vanilj Proteinshake" is NOT vanilj

    # Cheese spreads - flavors are toppings, not ingredients
    'mjukost',  # "Mjukost Räkor" - räkor is the flavor, NOT actual shrimp

    # Baked goods - flavors are mix-ins, not standalone ingredients
    'finskorpor',  # "Finskorpor Kardemumma" - kardemumma is flavoring
    'skorpor',  # "Skorpor Mandel" - mandel is flavoring

    # Ready meal brands - ingredient words are contents, not raw ingredients
    'dafgårds',  # "Ugnsrostad kyckling 390g Dafgårds" - kyckling is the meal, not ingredient
    # NOTE: 'findus' removed — Findus sells both ready meals AND plain frozen
    # vegetables (Broccoli 600g Findus). Carrier status blocked broccoli etc.
    # Ready meals are handled by PROCESSED_FOODS/NON_FOOD instead.
    'gooh',  # "Gooh Kyckling Curry" - ready meal brand

    # Pies/pastry - filling ingredients are flavors, not standalone
    'paj',  # "Paj Kyckling Garant" - kyckling is filling, not raw chicken

    # Meatballs - protein type is flavor, the product is meatballs
    'köttbullar', 'kottbullar',  # "Kyckling Köttbullar" - kyckling is type, not raw chicken

    # Dessert/snack products - fruit names are flavors, not ingredients
    'risifrutti',  # "Risifrutti Jordgubb" - dessert cup, not strawberry
    'magisk',  # "Magisk Mango" - Risifrutti dessert product, not mango
    'smoothie',  # "Smoothie Äpple Blåbär" - blended drink, not fruit
    'pie',  # "Sweet Apple Pie Fryst" - baked dessert, not apple

    # Soups/drinks with ingredient names
    'blåbärssoppa', 'blåbarssoppa', 'blabärssoppa', 'blabars soppa',

    # Olives - flavor/type words are mix-ins, not standalone ingredients
    # "Vitlök Halkidiki Oliver med Kärnor" - vitlök/kärnor are descriptors, oliver is the product
    'oliver',  # "Vitlök Halkidiki Oliver med Kärnor" - vitlök is flavoring, not garlic ingredient

    # Spreads/dips where ingredients are just flavors
    'tapenade',  # "Tapenade Al Basilico Basilika Oliv Kapris" — basilika is flavor, not fresh herb

    # Baked goods where ingredient names are flavors
    'muffins', 'minimuffins',  # "Minimuffins Citron" — citron is flavor, not fresh lemon

    # Preserved/marinated items where chili/herbs are flavors
    'vitlöksklyftor', 'vitloksklyftor',  # "Vitlöksklyftor Chili" — chili is flavoring

    # Kaviar — "Kaviar Dill" has dill as flavoring, not herb ingredient
    'kaviar',
})

# Pre-split carrier products for fast lookup:
# Single-word carriers can be checked via set intersection with name_words (O(n) vs O(173))
# Multi-word carriers still need substring check but there are only ~10
_CARRIER_SINGLE_WORDS: frozenset = frozenset(c for c in CARRIER_PRODUCTS if ' ' not in c)
_CARRIER_MULTI_WORDS: tuple = tuple(
    sorted(
        (c for c in CARRIER_PRODUCTS if ' ' in c),
        key=lambda carrier: (-len(carrier), carrier),
    )
)

# For compound suffix detection: single-word carriers that could be word suffixes
# Pre-sorted by length (longest first) for greedy matching
_CARRIER_SUFFIX_CANDIDATES: tuple = tuple(
    sorted(_CARRIER_SINGLE_WORDS, key=len, reverse=True)
)

# Carriers where products must require the carrier word in ingredient text.
# When a product has one of these carriers, its context_words includes the carrier,
# meaning it ONLY matches ingredients that also contain the carrier word.
# Also: stripped flavor words are re-added as keywords for flavor-specific matching.
# Example: "Pastasås Basilika" → keywords ['pastasas', 'basilika'], context {'pastasas'}
#   → matches "pastasås basilika" ✓, blocked from "2 kvistar basilika" ✗
# NOTE: uses ASCII-normalized form (fix_swedish_chars: å→a, ä→a, ö→o)
CARRIER_CONTEXT_REQUIRED: FrozenSet[str] = frozenset({
    'pastasås',  # fix_swedish_chars('pastasas') → 'pastasås'; name_words_all uses Swedish form
    'pinsasås',  # sauce carrier: raw 'nduja' should not match a pinsasås ingredient
    'pinsasas',  # normalized form used in ingredient/product matching
    'pålägg', 'palagg',  # deli-slice carrier: raw cuts and generic spreads should not match
    # Tube soft-cheese spreads: explicit flavored "mjukost" lines should only
    # match products that carry the same flavor signal, while plain "mjukost"
    # remains broad. The carrier context also prevents flavor keywords from
    # leaking into non-mjukost ingredients like plain shrimp or jalapeno.
    'mjukost',
})

# Carriers where the first word is ALWAYS a flavor, never the actual product.
# For these, the safety net should NOT re-add stripped flavor words.
# Example: "Jordgubb Saft" → 'saft' is carrier, 'jordgubb' is flavor (not the product)
# Contrast: "Ost Pizza Riven" → 'pizza' is carrier, 'ost' IS the product
_FLAVOR_DOMINANT_CARRIERS: frozenset = frozenset({
    # Drinks — first word is always a flavor
    'saft', 'juice', 'läsk', 'dryck', 'nektar', 'lemonad', 'cider',
    'blanddryck', 'fruktdryck', 'proteindryck', 'lättdryck', 'lattdryck',
    'smoothie', 'smoothies', 'milkshake', 'proteinmilkshake', 'proteinshake',
    'dricka',  # "Persikadricka" — fruit drink
    'fruktstänger', 'fruktstang',  # fruit snack bars
    'kombucha', 'kolsyrat', 'kolsyratvatten', 'vitaminvatten', 'funktionsvatten', 'zingo',
    'te', 'iste',  # tea — "Earl Grey Citron Svart Te" → citron is flavor
    'radler', 'lager',  # beer — "Radler Citron Ljus Lager" → citron is flavor
    # Snacks — first word is always a flavor
    'chips', 'popcorn', 'micropopcorn', 'mikropopcorn', 'potatiships',
    'nötter', 'notter', 'nötmix', 'notmix',
    # English snack descriptors — "Chili Cream Cheese Chips" → chili is flavor
    'cream cheese',
    # Condiments/sauces — first word is usually a flavor
    'sås', 'såser', 'sylt', 'marmelad', 'gelé', 'gele',
    'dressing', 'salladdressing', 'ceasardressing',
    'dip', 'dipmix', 'dippsås', 'marinad',
    # Dairy carriers — first word is a flavor
    'färskost', 'farskost',  # "Vitlök&örter Färskost" → vitlök is flavor
    'glass', 'sorbet',  # ice cream — "Glass Jordgubb" → jordgubb is flavor
    'filmjölk', 'filmjolk',  # "Jordgubb Filmjölk" → jordgubb is flavor
    'drickyoghurt',  # "Jordgubb Drickyoghurt" → jordgubb is flavor
    'fruktkvarg',  # "Jordgubb Fruktkvarg" → jordgubb is flavor
    'havregott', 'havrefras',  # oat yoghurt/cereal — fruit is flavor
    'mannafrutti',  # yoghurt brand — fruit is flavor
    'gröt', 'grot', 'grötkopp', 'grotkopp',
    'müsli', 'musli', 'granola', 'flingor',
    # Desserts/confectionery where first word = flavor
    'mousse', 'proteinmousse',  # "Citron Mousse" → citron is flavor
    'pudding', 'proteinpudding', 'proteindessert',  # "Pudding Choklad" → choklad is flavor
    'lakrits',  # "Lakrits Salt Hallon" → hallon is candy flavor
    'chews',  # "Ginger Chews Jordnöt" → jordnöt is candy flavor
    'chokladsmak',  # "Mjölk UHT med chokladsmak" → mjölk is base, not ingredient
    'våffelstrut', 'våffelstrutar',  # "Våffelstrutar hallon" → hallon is decoration
    'dessertbägare',  # "Dessertbägare Hallon" → hallon is flavor
    'jelly',  # "Jelly Hallon" → hallon is flavor
    'småmål',  # "Småmål Kokos med hallon" → hallon is flavor
    'glasspinnar', 'glasspinne',  # "Glasspinnar Mumsbit mandel" → mandel is flavor
    # Flavored dairy
    'gourmetyoghurt',  # "Gourmetyoghurt Hallon" → hallon is flavor
    'soygurt',  # "Soygurt Persika Hallon" → fruit is flavor
    'havregrädde', 'havregradde',  # oat cream with flavor
    'havrering',  # cereal with nuts
    # Juice/must/water
    'kullamust',  # "Kullamust Äpple & hallon"
    'champion',  # "Champion Apelsin"
    'vatten',  # "Vatten Granatäpple Lime"
    # Vinegar
    'vinäger', 'vinager',  # "Vinäger Schalottenlök"
    # Snacks/pickles/cheese with flavors
    'pirog',  # "Pirog chili cheese"
    'pilsnerpinnar',  # "Pilsnerpinnar Chili"
    'cornichons',  # "Cornichons Vitlök Chili"
    # Cookies/must
    'kaka',  # "Kaka Äpple & kola"
    'must',  # "Must Äpple"
    # Baked goods where first word = flavor
    'pie', 'paj', 'mazarin', 'mazariner', 'chokladkaka',
    'kex', 'kakor', 'skorpor', 'finskorpor',
    'focaccia',  # "Focaccia Tomat" → tomat is flavor
    # Herb carriers — "Vitlök & Örter 28%" → vitlök is flavor on herb product
    'örter', 'orter',
    # Ready meals/salads — first word is always a flavor
    'potatissallad',  # "Potatissallad Vitlök" → vitlök is flavor
    'krossade tomater',  # "Krossade Tomater Vitlök" → vitlök is flavor
    'soltorkade tomater', 'soltorkad tomat', 'soltork tomat', 'solt tomat',
    'risotto',  # "Risotto Svamp Vitlök" → svamp/vitlök are flavors
    # Mayo — first word is flavor
    'majo',  # "Majo Gochugaru Vitlök" → gochugaru/vitlök are flavors
    # Cheese brands — first word is flavor
    'cambozola',  # "Cambozola Vitlök" → vitlök is flavor
    'kryddost',  # "Kryddost Spiskummin" → spiskummin is flavor
    # Sauces — "Chipotle Bearnaise" → chipotle is flavor
    'bearnaise',
    # Soups — "Potatis Purjo Soppa" = flavor + flavor + carrier, no real ingredients
    'soppa', 'soppor',
    # Canned fish — oil/sauce is packaging, first word is product
    'sardeller',  # "Sardeller I Olivolja" → olivolja is packaging
    'sillskivor', 'sillskiva',  # "Sillskivor tomat" → tomat is flavor
    # Frozen snacks — fillings are not standalone
    'pizzabullar', 'pizzabulle',  # "Pizzabullar med tomat" → tomat is filling
    # Patties/spreads — component ingredients
    'ostbiff',  # "Spenat och ostbiff" → spenat is component
    'hasselnötskräm', 'hasselnötskram',  # "Hasselnötskräm Solrosolja" → oil is component
    # Spreads/crackers with oil
    'breoliv',  # "BreOliv Olivolja" → olivolja is component
    'breton',  # "Breton Olivolja" → olivolja is flavor
    # Spice rubs
    'rub',  # "BBQ rub Chili" → chili is flavor
})

# ============================================================================
# CONTEXT-REQUIRED WORDS - Product only matches if ingredient also has this word
# ============================================================================
# Problem: "kyckling" ingredient matches "Köttbullar Kyckling" (wrong!)
# Solution: If product contains "köttbullar", ingredient must ALSO contain "köttbullar"
#
# This allows:
#   - "kycklingköttbullar" ingredient → matches "Köttbullar Kyckling" ✓
#   - "kyckling" ingredient → does NOT match "Köttbullar Kyckling" ✗

_CONTEXT_REQUIRED_WORDS_RAW: FrozenSet[str] = frozenset({
    # Processed meat forms - ingredient must specify these
    'köttbullar', 'kottbullar', 'köttbulle', 'kottbulle',
    'burgare', 'burger', 'burgers',
    'nuggets', 'nugget',
    'schnitzel',
    'korv',  # "falukorv" recept ska matcha "Falukorv", men "fläsk" ska inte matcha "Fläskkorv"
    'kebab',  # "Kebab av Fläskkarré" is processed kebab meat, not raw fläskkarré

    # NOTE: 'skivor'/'slices' removed — too broad (blocked avokado, kycklingfilé etc.)
    # Cheese slices are already protected by cheese-type context (cheddar, mozzarella)

    # Cheese use-case words - "Riven ost Gratäng" should only match gratäng recipes
    'gratäng', 'gratang',  # "Riven ost Gratäng 24%" is NOT generic "ost"

    # Specialty cheeses - "ost" or "riven ost" should NOT match specialty cheese products
    # Product "Riven Ost Mozzarella" should ONLY match ingredients that say "mozzarella"
    'mozzarella', 'mozarella',
    'parmesan', 'parmigiano', 'parmesanost',
    'ricotta', 'mascarpone', 'burrata',
    'pecorino', 'gorgonzola',
    'cheddar',
    'gruyère', 'gruyere',
    'emmental', 'emmentaler',
    'brie', 'camembert',
    'feta', 'fetaost',
    'halloumi',
    'cottage',  # cottage cheese
    # Specialty cheeses — should NOT match generic "ost" or "riven ost"
    'getost',  # (NB: 'get' too broad — matches 'vegetarisk', 'budget')
    'stracchino', 'twarog', 'paneer', 'apetina',
    'raclette', 'taleggio', 'chevrette', 'rödkit',
    'danablu',  # blue cheese — not generic rivable ost
    'travnicki', 'bosnisk',  # Travnicki bosnisk ost
    'dessertost',  # aged specialty cheese
    'biraghi',  # Gran Biraghi Italian hard cheese

    # Non-cheese products containing 'ost'
    'smördegsstänger',  # "Smördegsstänger Twist ost" — pastry, not cheese
    # Note: Swedish everyday cheeses (präst, herrgård, grevé) removed from
    # CONTEXT_REQUIRED_WORDS - they ARE generic ost and should match "ost" recipes.
    # västerbotten is NOT in this group — distinct flavor, kept in SPECIALTY_QUALIFIERS.

    # Specialty hams - "skinka" should not match "Serrano" unless recipe says "serrano"
    'serrano', 'pata negra', 'patanegra', 'parma', 'parmaskinka',
    'prosciutto', 'iberico', 'ibérico',

    # Tomato varieties - kept for canned/specialty/size distinction
    # NOTE: babyplommon, cocktailtomater REMOVED — fresh small tomato variants (→ småtomat).
    # plommon/plommontomater KEPT — regular-sized plum tomatoes, NOT interchangeable with small.
    'plommon', 'plommontomater',
    'körsbär', 'körsbärstomater', 'cherry',  # keep: körsbärstomater default = canned
    'datterini', 'datterino',  # Italian variety (often canned) - not "vanliga tomater"
    'marzano',  # "San Marzano Tomater" - canned product, not fresh tomatoes

    # Chili pepper varieties - specific types require specific match
    # "chilipeppar" (generic) should NOT match "Chilipeppar Chipotle" unless recipe says "chipotle"
    'chipotle', 'ancho', 'habanero', 'jalapeño', 'jalapeno',
    'flakes', 'flingor',  # "Red Hot Flakes" - specific type

    # Spice intensity - "Paprika Stark" should ONLY match if recipe says "stark"
    # "1 tsk paprikakrydda" should NOT match "Paprika Stark" (specific hot variety)
    'stark',  # hot/strong variety

    # Bread products - only match if recipe actually needs bread
    # "kyckling" should NOT match "Flerkorn Bröd Surdeg..."
    # But "surdegsbröd", "tunnbröd" etc SHOULD match bread products
    # Note: Only "bröd" - the key indicator. "surdeg" is too specific.
    # Note: "ströbröd" vs bread handled via SPECIALTY_QUALIFIERS
    'bröd', 'bread',

    # Coffee products - "mjölk" should NOT match "Bryggkaffe med mjölk"
    # Product "Bryggkaffe Mellanrost Perfekt med mjölk" should only match if ingredient says "kaffe"
    'kaffe', 'coffee', 'bryggkaffe', 'snabbkaffe', 'espresso', 'cappuccino', 'latte',

    # Vanilla - "Yoghurt Vanilj" should only match if recipe also says "vanilj"
    # Prevents matching plain "yoghurt" recipes
    'vanilj', 'vanill',  # "Barista Vanill Havredryck" — 'vanill' is substring of 'vanillinsocker', needs context check

    # Onion qualifiers - "Lök Schalotten" should only match if recipe also says "schalotten"
    'schalotten',

    # Spice mixes - "Kryddmix Tandoori" should only match if recipe also says "kryddmix"
    # Prevents "tandoori" in a kryddmix from matching "tandoori-marinerad kyckling"
    'kryddmix',

    # Potato products - "Pommes Strips Frysta" should NOT match "Vegetariska Strips"
    'pommes',

    # Chips/snacks - "Tortilla Chips" should only match if recipe also says "chips"
    # Prevents matching "tortillabröd" (bread) with tortilla chips products
    'chips',

    # Filled pasta - "Färsk Fylld Pasta" should NOT match plain "pasta" recipes
    # Only match if recipe also says "fylld" (or tortellini/ravioli)
    'fylld', 'fyllda',
})

# Pre-normalized for performance (avoid fix_swedish_chars in hot loop)
CONTEXT_REQUIRED_WORDS: FrozenSet[str] = frozenset({
    fix_swedish_chars(w).lower() for w in _CONTEXT_REQUIRED_WORDS_RAW
})

# Context words to IGNORE when a product has a specific keyword.
# Filled pasta/gnocchi: filling names (mozzarella, ricotta) shouldn't block
# matching on the primary ingredient keyword (tortelloni, gnocchi).
# Named origins: "coppa di parma" IS "coppa" — "parma" is just the origin.
_EMPTY_FROZENSET: FrozenSet[str] = frozenset()

CONTEXT_WORD_KEYWORD_EXEMPTIONS: Dict[str, FrozenSet[str]] = {
    'tortelloni': frozenset({'mozzarella', 'ricotta', 'spinaci', 'pancetta', 'pomodoro'}),
    'tortellini': frozenset({'mozzarella', 'ricotta', 'spinaci', 'pancetta'}),
    'ravioli': frozenset({'mozzarella', 'ricotta', 'spinaci', 'pancetta'}),
    'fylld gnocchi': frozenset({'mozzarella', 'ricotta'}),
    'coppa': frozenset({'parma'}),
    'coppadiparma': frozenset({'parma'}),

    # Sauces: "Srirachasås Stark" is still sriracha — 'stark' is just heat level
    # Key is 'sriracha' because INGREDIENT_PARENTS maps 'srirachasås' → 'sriracha'
    'sriracha': frozenset({'stark'}),

    # Chiliflakes: "Chiliflingor Påse" normalizes to keyword 'chiliflakes' — 'flingor' context
    # is redundant since the keyword itself implies flakes/flingor
    'chiliflakes': frozenset({'flingor', 'flakes'}),

    # Deli platter products expose component cheeses/chark words in the name,
    # but "charkbricka" ingredients are meant to accept those assortments.
    'charkbricka': frozenset({'fuet', 'iberico', 'ibérico', 'manchego'}),

    # Kokosflingor/Kokoschips → extra keyword 'kokos': exempt from carrier context
    # so these products match recipes saying "riven kokos" (without mentioning flingor/chips)
    'kokos': frozenset({'flingor', 'flakes', 'chips'}),

    # "Savoiarde Kex ... Soko Stark" uses Stark as a brand tail, not as a heat
    # qualifier. Keep the exemption narrow to the ladyfinger biscuit family.
    'savoiardikex': frozenset({'stark'}),

    # Chorizo: "Chorizo Kycklingkorv" is still chorizo — 'korv' is its category
    # "Chorizo Iberico" is still chorizo — 'iberico' is origin/quality, not a different product
    # "Chorizo Jalapeño Smal" is still chorizo — 'jalapeño' is just a flavor variant
    'chorizo': frozenset({'korv', 'iberico', 'ibérico', 'jalapeño', 'jalapeno'}),

    # Yeast: "Jäst för matbröd" / "Torrjäst Matbröd" is yeast FOR bread — 'bröd' is usage, not product type
    'jäst': frozenset({'bröd'}),
    'torrjäst': frozenset({'bröd'}),

    # Bagels: "Bagels Classic 300g Liba Bröd" — 'bröd' is the brand (Liba Bröd), not product type
    'bagels': frozenset({'bröd'}),
    'bagel': frozenset({'bröd'}),

    # Cheddar: "Cheddar Hamburgerost" IS cheddar — 'burger' is just the usage form
    'cheddar': frozenset({'burger', 'burgare', 'burgers'}),
    # Hamburgerost recipes already name the burger-cheese use-case. Products like
    # "Burgers Slices Cheddar" / "Cheddar Burgar" should not also require the
    # ingredient to spell out both burger-form and cheddar flavor words.
    'hamburgerost': frozenset({'burger', 'burgare', 'burgers', 'cheddar'}),

    # Heat level: 'stark' just means "hot" — doesn't change what the product IS
    'ajvar': frozenset({'stark'}),
    'paprikapuré': frozenset({'stark'}),
    'pepparrot': frozenset({'stark'}),
    'pimenton': frozenset({'stark'}),

    # Capers: "Kapris Cocktail" — 'cocktail' is now STOP_WORD so no exemption needed

    # Merguez: "Merguez Lammkorv" IS merguez — 'korv' is its category
    'merguez': frozenset({'korv'}),

    # NOTE: grillost/halloumi NOT exempt from burgare context —
    # "Grillost Burgare Oregano" is shaped/seasoned for burgers, not for salads.
    # Plain "Grillost Naturell" (no burgare context word) still matches halloumi recipes.
    'halloumiburgare': frozenset({'burger', 'burgare'}),
    # Generic veg-burger recipe wording should allow burger-form halloumi/grillost
    # products without requiring the cheese type to be repeated explicitly.
    'vegetariskhamburgare': frozenset({'halloumi', 'grillost'}),

    # Somunbröd: "Somunbröd Till Kebab Cevapcici" IS bread — 'kebab' is usage, not product type
    'somunbröd': frozenset({'kebab'}),

    # Feferoni: the current live product is sold as "Feferoni Kebab", where
    # kebab describes serving style/packaging rather than kebab meat.
    'feferoni': frozenset({'kebab'}),

    # Skinka: "Lufttorkad Skinka Jamon Serrano" IS skinka — serrano/prosciutto/iberico
    # are subtypes of lufttorkad skinka. A recipe saying "lufttorkad skinka" should match
    # all air-dried ham variants regardless of specific origin/name.
    'skinka': frozenset({
        'serrano', 'prosciutto', 'parma', 'iberico', 'ibérico',
        'jamon', 'jamón', 'langhirano', 'cebo', 'campo',
        'westfalisk', 'schwarzwalder',  # German-style air-dried
        'monte', 'castello',  # brand names
    }),
    # Parma ham is frequently sold under the Italian name "Prosciutto di Parma".
    # Treat 'parma'/'prosciutto' as naming context for the same deli product when
    # we've already bridged the product into keyword 'parmaskinka'.
    'parmaskinka': frozenset({'parma', 'prosciutto'}),

    # Burger patties: "Marrowbone Beef Burger" IS a burger — 'burger' context shouldn't block itself
    'hamburgare': frozenset({'burger', 'burgare'}),

    # Coffee: "Bryggkaffe 500g" gets offer keyword 'kokkaffe' (via OFFER_EXTRA_KEYWORDS) so that
    # recipe "Brygg- och kokkaffe" can match via 'kokkaffe' substring. But the product's context
    # word 'bryggkaffe' is not a substring of "brygg- och kokkaffe" (hyphenated compound), so
    # we must exempt the 'bryggkaffe' context requirement when matching on 'kokkaffe'.
    # 'kaffe' context word still passes (it IS a substring of 'kokkaffe').
    'kokkaffe': frozenset({'bryggkaffe'}),

    # Keso: "KESO Cottage Cheese" matched via 'keso' keyword should not require
    # 'cottage' in ingredient — ingredient "keso" IS cottage cheese by definition.
    'keso': frozenset({'cottage'}),

    # Tårtbottnar: "Vaniljtårtbotten" / "Chokladtårtbotten" matched via 'tårtbottnar'
    # extra keyword should not require the flavor word in ingredient — any tårtbotten works.
    'tårtbottnar': frozenset({'vanilj', 'choklad'}),
    'tårtbotten': frozenset({'vanilj', 'choklad'}),
}


# ============================================================================
# INGREDIENT CONTEXT REQUIREMENTS (inverse of CONTEXT_REQUIRED_WORDS)
# ============================================================================
# CONTEXT_REQUIRED_WORDS: if PRODUCT has the word, INGREDIENT must too.
# INGREDIENT_REQUIRES_IN_PRODUCT: if INGREDIENT has the word and match is on
# a DIFFERENT keyword, PRODUCT must also contain this word.
#
# Example: ingredient "Kryddmix Guacamole" matched on keyword "guacamole"
#   → ingredient contains "kryddmix" → product must also contain "kryddmix"
#   → product "Guacamole" does NOT contain "kryddmix" → BLOCKED
#   → product "Kryddmix Guacamole" DOES contain "kryddmix" → ALLOWED
_INGREDIENT_REQUIRES_IN_PRODUCT_RAW: FrozenSet[str] = frozenset({
    'kryddmix',  # "Kryddmix Guacamole" should only match kryddmix products, not plain "Guacamole"
    'fraiche',   # flavored crème fraîche lines should still contain the fraiche carrier
    'havredryck',  # flavored oat-drink lines should stay on oat-drink products, not plain choklad
})

INGREDIENT_REQUIRES_IN_PRODUCT: FrozenSet[str] = frozenset({
    fix_swedish_chars(w).lower() for w in _INGREDIENT_REQUIRES_IN_PRODUCT_RAW
})

# Keyword suppression: when a product matches generic keyword X on an ingredient line
# that also contains a more specific keyword Y, suppress the generic match.
# Example: ingredient "Hummerfond Buljong" → generic 'buljong' should NOT match all
# buljong products — only 'hummerfond' should match. The word "buljong" is just a
# product-format label, not a separate ingredient.
# Format: generic_keyword → {specific_keywords_that_suppress_it}
KEYWORD_SUPPRESSED_BY_CONTEXT: Dict[str, Set[str]] = {
    'buljong': {'hummerfond', 'kalvfond', 'fiskfond', 'svampfond', 'skaldjursfond',
                'grönsaksbuljong', 'kycklingbuljong', 'köttbuljong', 'fiskbuljong', 'hönsbuljong'},
    # "schalottenlöksfond" should use the specific shallot-stock keyword, not fall back
    # to generic "fond" products like Fond Du Chef.
    'fond': {'schalottenlöksfond', 'schalottenlökfond'},
    # Branded English "pizza spices ..." lines are too sparse and noisy to route
    # through the generic keyword 'spices'. Prefer 0 matches over unrelated
    # Asian/Indian spice blends surfacing for pizza-specific seasoning lines.
    'spices': {'pizza'},
    # "grönsaksbuljongtärning" contains both "buljongtärning" and "grönsaksbuljong"
    # as substrings. The specific prefix (grönsaks-) should suppress the generic match.
    # Same for kycklingbuljongtärning, etc.
    'buljongtärning': {'grönsaksbuljong', 'kycklingbuljong', 'köttbuljong', 'fiskbuljong', 'hönsbuljong'},
    # "vinäger, gärna hallon" / "fruktdryck med smak av hallon" use hallon
    # as a flavor modifier, not as fresh/frozen raspberries.
    'hallon': {'vinäger', 'vinager', 'yoghurt hallon', 'fruktdryck'},
    # "MAX crispy no chicken" is a branded vegan product — not actual chicken
    'chicken': {'no chicken'},
    # "potatisskalare" = potato peeler (kitchen tool), not potatoes
    'potatis': {'potatisskalare', 'sötpotatis', 'sotpotatis'},
    # "Hushållsaromer" = liquid flavoring, not hushållsost (cheese)
    'hushålls': {'hushållsaromer'},
    # "chokladägg" = hollow chocolate eggs (candy), not real eggs
    'ägg': {'chokladägg'},
    # "baconmjukost" = bacon cream cheese spread, not raw bacon
    'bacon': {'baconmjukost'},
    # "citrontimjan" = lemon thyme (Thymus citriodorus), distinct species from regular thyme.
    # Plain "Timjan" products should NOT match recipes wanting citrontimjan.
    'timjan': {'citrontimjan'},
    # "tångkaviar" = seaweed caviar — no kaviar product in DB is tångkaviar
    'kaviar': {'tångkaviar', 'tangkaviar'},
    # "pastasås chili" / "tapenade med chili" / "pinsasås chili" — chili is a flavor modifier,
    # not a standalone ingredient. Suppress 'chili' keyword when these context words are present.
    'chili': {'tapenade', 'pinsasås', 'pinsasas', 'salsiccia', 'glaze', 'sriracha', 'chipotle'},  # flavor/heat word inside another condiment family
    # "Philadelphia cream cheese sweet chili" = flavored cream cheese, not chili sauce.
    # Suppress 'chilisås' when ingredient mentions 'färskost' or 'cream cheese'.
    'chilisås': {'färskost', 'cream cheese'},
    # NOTE: 'pastasås' removed from chili/tomat/basilika — handled by CARRIER_CONTEXT_REQUIRED
    # ingredient carrier restriction in matches_ingredient_fast() STEP 2b.
    'vitlök': {'vitlökssås', 'vitlokssas', 'parmesansås', 'parmesansas'},
    'vitlok': {'vitlökssås', 'vitlokssas', 'parmesansås', 'parmesansas'},
    # "bbq-sås med smak av honung" / "grillkrydda honung" — honung is a flavor
    # descriptor there, not a standalone honey ingredient.
    'honung': {'bbq-sås', 'bbqsås', 'bbq-sas', 'bbqsas', 'grillkrydda'},
    # "stjärnanis" is star anise. If ingredient says "stjärnanis", suppress parent "anis"
    # to prevent regular anise products ("Kryddor Anis hel") from matching.
    'anis': {'stjärnanis', 'stjarnanis'},
    # "kanelbullar" = cinnamon buns (baked product). Suppress "kanel" (cinnamon spice)
    # to prevent ground cinnamon matching when recipe wants pre-made kanelbullar.
    'kanel': {'kanelbullar', 'kanelbulle', 'kanellikör', 'kanellikor'},
    # "kardemummaskorpor" should match rusk products, not plain cardamom spice.
    'kardemumma': {'kardemummaskorpor'},
    # "3 chorizo korvar" should stay on the chorizo family, not fall back to
    # generic korv products like falukorv or vegokorv.
    'korv': {'chorizo'},
    # "Snackoliver Citron" = lemon-flavored snack olives, not fresh lemons.
    # "Kall citronsås" should stay on the sauce family, not fall back to fresh lemons.
    # Olive/sauce products already match via their own specific keywords.
    'citron': {'snackoliver', 'citronkaka', 'citronsås', 'citronsas'},
    # "maraschinokörsbär" = cocktail cherries, not fresh/frozen cherries.
    # "körsbärsmarmelad" should stay on the preserve instead of falling back
    # to plain fresh/frozen cherries.
    'körsbär': {'maraschinokörsbär', 'maraschinokorsbar', 'marmelad'},
    'korsbar': {'maraschinokörsbär', 'maraschinokorsbar', 'marmelad'},
    # "Creme fraiche fetaost & tomat" should use the fraiche base, not plain feta blocks.
    'fetaost': {'fraiche'},
    'feta': {'fraiche'},
    # "sillkryddor" = herring seasoning mix. Suppress "sill" (pickled herring)
    # to prevent actual herring products matching when recipe wants seasoning.
    'sill': {'sillkryddor'},
    # "fikonmarmelad" = fig jam/preserve. Suppress "fikon" (fresh fruit)
    # so plain figs don't match when recipe wants fig marmalade.
    # "päronkonjak" = pear cognac (alcohol). Suppress "päron" (fresh fruit)
    # so fresh pears don't match when recipe wants päronkonjak/päronlikör.
    'päron': {'konjak'},
    'paron': {'konjak'},
    'fikon': {'marmelad', 'balsamico'},
    # Specialty syrup compounds should stay exact instead of falling back to plain syrup.
    'sirap': {'dadelsirap', 'glykossirap', 'ananassirap'},
    # "köttfärssåser" / "köttfärssås" = ready-made meat sauce. Suppress generic 'såser'
    # so bearnaise/remoulade/majonnäs don't match when recipe wants köttfärssås.
    'såser': {'köttfärssås'},
    # "Spaghetti Pastakrydda" = spice blend for pasta, NOT actual spaghetti noodles.
    # 'spaghetti' normalizes to 'långpasta' — suppress the normalized keyword
    # when ingredient contains 'pastakrydda'.
    'långpasta': {'pastakrydda'},
    'langpasta': {'pastakrydda'},
    # "Pepparsås 250ml Löhmanders" — suppress 'pepparsås' keyword when ingredient
    # mentions sriracha/tabasco (those are hot sauces, not pepper sauce)
    'pepparsås': {'sriracha', 'tabasco'},
    'pepparsas': {'sriracha', 'tabasco'},
    # "Mirin Risvin" = sweet rice wine for cooking, NOT risvinäger (rice vinegar).
    # Suppress 'risvin' keyword when ingredient specifically asks for risvinäger.
    'risvin': {'risvinäger', 'risvinager'},
    # "tryffelolja" should stay on truffle oil, not generic truffle-flavored cheese products.
    'tryffel': {'tryffelolja'},
    'sylt': {'hallonsylt', 'lingonsylt', 'jordgubbssylt', 'jordgubbsylt', 'apelsinskal'},
    # "400g Dumplings Kyckling" = pre-made chicken dumplings, not raw chicken.
    # Suppress 'kyckling' when ingredient mentions 'dumplings' — recipe wants ready-made product.
    'kyckling': {'dumplings', 'dumpling'},
    # "mozzarellaost (limpa à ca 350-400 g)" — 'limpa' describes cheese block form, not bread.
    # Suppress 'limpa' when ingredient mentions 'mozzarella'.
    'limpa': {'mozzarella'},
    # "äggvita (valfritt, sorbeten blir luftigare)" — 'sorbeten' in parenthetical leaks 'sorbet' keyword.
    # The ingredient is egg white, not sorbet.
    'sorbet': {'äggvita'},
    # "kombuchasvamp" = SCOBY culture for brewing kombucha. Bottled kombucha drinks
    # should NOT match when recipe wants the live culture.
    'kombucha': {'svamp'},
    # "filodegskrustader" should stay on the prepared crustade family rather than
    # falling back to plain filo sheets.
    'filodeg': {'krustader'},
    # "katrinplommonpuré" = dried prune paste. Fresh plommon should NOT match
    # when recipe specifically asks for katrinplommon (dried prune product).
    'plommon': {'katrinplommon'},
    # "Salami med Fänkål" = fennel-flavored salami. Suppress 'fänkål' (fresh fennel)
    # when ingredient mentions 'salami' — recipe wants the salami, not fresh fennel.
    'fänkål': {'salami', 'krydda'},
    'fankal': {'salami', 'krydda'},
    # "fullkornsrismjöl" = rice flour, NOT whole grain rice.
    # Suppress 'fullkornsris' when ingredient contains 'mjöl' (flour).
    'fullkornsris': {'mjöl', 'mjol'},
    # Generic "Mjöl ..." products should not satisfy explicit wheat-flour
    # subtypes when the ingredient already carries the normalized compound.
    'mjöl': {
        'mjölmix', 'mjolmix',
        'vetemjölspecial', 'vetemjolfullkorn', 'vetemjölfullkorn', 'vetemjolspecial',
    },
    # "nudlar (glas, ris eller ägg)" — ris here means rice NOODLE type, not cooking rice.
    # Suppress 'ris' when ingredient says "glas, ris" (noodle-type qualifier in parentheses).
    # Does NOT affect "ris eller nudlar" (standalone rice as alternative) since that lacks "glas, ris".
    'ris': {'blomsteris', 'paris', 'puffat', 'glas, ris'},
    # "basilikaolja" = oil infused with basil, not dried basil herb
    'basilika': {'basilikaolja', 'basilikapesto'},
    # "fänkålsdill" means fennel fronds, not separate dill herb products.
    'dill': {'fänkålsdill', 'fankalsdill'},
    # "hasselnötsolja" = oil infused with hazelnuts, not whole hazelnuts
    'hasselnöt': {'hasselnötsolja', 'hasselnötsmjöl', 'nougatkräm', 'nougatkram'},
    'hasselnot': {'hasselnötsolja', 'hasselnotolja', 'hasselnotsmjol', 'nougatkräm', 'nougatkram'},
    # "linfröolja" wants oil, not whole flax seeds.
    'linfrö': {'linfröolja'},
    'linfro': {'linfroolja'},
    # "bittermandel" / "marconamandlar" are distinct almond products.
    # Plain almonds should not match when the ingredient explicitly asks for one of them.
    'mandel': {'bittermandel', 'marconamandlar'},
    'mandlar': {'marconamandlar'},
    # "apelsinskal" / "syltade apelsinskal" wants peel, and explicit
    # "blodapelsin" wants the specific blood-orange variety, not generic orange.
    'apelsin': {'apelsinskal', 'blodapelsin', 'blodapelsiner'},
    # "kittost" = specific dessert cheese (Castello). Generic "ost" products
    # should NOT match when recipe specifically asks for kittost.
    'ost': {'kittost', 'vitmögelost', 'vitmogelost', 'svecia', 'paneer', 'ostkrokar', 'ostkrok'},
    # "kokossocker" is a distinct pantry sweetener. Generic sugar products should not match.
    'socker': {'kokossocker'},
    # "färsk jäst matbröd" = yeast for bread, NOT actual bread.
    # Suppress 'matbröd' when 'jäst' is in the ingredient text.
    'matbröd': {'jäst', 'jast'},
    'matbrod': {'jäst', 'jast'},
    # "varm choklad" = hot chocolate drink, not baking chocolate.
    # "chokladlikör" = liqueur, not plain chocolate.
    # "mörk choklad med mintcrisp" should not fall back to plain chocolate when
    # there is no exact mint-crisp product on sale.
    'choklad': {'varm choklad', 'likör', 'likor', 'mintcrisp'},
    # "kakaolikör" = cocoa/chocolate liqueur, not cocoa powder.
    'kakao': {'likör', 'likor'},
    # "proteinpudding" should match explicit protein pudding products via their
    # own compound keyword, not fall back to any generic product that only says
    # "pudding" somewhere in the name.
    'pudding': {'proteinpudding'},
    # "Tapenade Oliver & Kapris" / "Tapenade Zucchini & Paprika" wants the
    # prepared tapenade, not separate jars or raw vegetables. Exact tapenade
    # products still match via their own keyword.
    'oliver': {'tapenade'},
    'kapris': {'tapenade'},
    'paprika': {'tapenade'},
    'zucchini': {'tapenade'},
    # "tärnad fetaost i marinad" = feta cheese packed in oil/herb marinade.
    # The "marinad" describes the packaging, NOT that you need a separate marinade product.
    # Suppress 'marinad' when ingredient also mentions 'fetaost' or 'oliver' (olives in marinade).
    'marinad': {'fetaost', 'feta', 'oliver'},
    # Whole berries ≠ juice/drink — "tranbärsjuice"/"tranbärsdryck" wants the
    # beverage, not frozen cranberries.
    'lingon': {'juice', 'dryck', 'lingonpulver'},
    'tranbär': {'juice', 'dryck'},
    'tranbar': {'juice', 'dryck'},
    'vinbär': {'juice'},
    'vinbar': {'juice'},
    # "morotsjuice" wants juice, not raw carrots.
    'morot': {'juice'},
    'morötter': {'juice'},
    'morotter': {'juice'},
    # "Tångpärlor Soja" should keep the specialty tångpärlor product, not degrade
    # into ordinary soy sauce matches through the flavor word.
    'soja': {'tångpärlor', 'tangparlor'},
    # "shiitake-svamp" should prefer shiitake offers instead of generic
    # mushroom fallback like champinjoner or kantareller.
    'svamp': {'shiitake'},
    # "Brytbönor eller Haricots Verts" = green beans. Generic 'bönor' should NOT
    # match dried/canned beans (vita bönor, kidney bönor) when recipe wants green beans.
    'bönor': {'haricot', 'brytbönor', 'brytbonor'},
    'bonor': {'haricot', 'brytbönor', 'brytbonor'},
    # "vatten, kallt, gärna filtrerat" — 'fil' is a 3-char substring of 'filtrerat'.
    # Suppress 'fil' (soured milk) when ingredient mentions 'filtrerat' (filtered water).
    # Also suppress 'fil' when ingredient says 'filmjölk': generic "Fil Blåbär/Hallon" products
    # (keyword 'fil') match filmjölk ingredients via substring, but flavored fil ≠ filmjölk.
    # No recipe uses "filmjölk eller fil" as alternatives — confirmed by DB scan.
    'fil': {'filtrerat', 'filtrerad', 'filmjölk'},
    # "skinka/salami pålägg" should resolve through the explicit deli-meat keyword,
    # not through generic sandwich-spread products that only happen to use "pålägg".
    # Extend the same narrowing to deli kalkon and rostbiff lines.
    'pålägg': {'skinka', 'salami', 'salame', 'kalkon', 'rostbiff'},
    'palagg': {'skinka', 'salami', 'salame', 'kalkon', 'rostbiff'},
    # "tortillachips ost" — 'chips' is a substring of 'tortillachips', so plain potato-chip
    # products (Chips Salted, Lantchips) would otherwise match tortillachips ingredients.
    # Suppress generic 'chips' keyword when ingredient contains 'tortilla'.
    # Also suppress when ingredient mentions seaweed context (tång/sjögräs/alger) —
    # "chips av tång" = seaweed chips (specialty snack), not potato chips.
    'chips': {'tortilla', 'tång', 'tang', 'sjögräs', 'sjogras', 'alger', 'algsallad'},
    # Flatbread compounds should not fall back to generic bread products.
    # "libabröd" / "tunnbröd" wants flatbread, not bagels or other bread shapes.
    'bröd': {'tunnbröd', 'tunnbrod', 'liba'},
    # "creme av soltorkade tomater" wants the specific spread/dip, not plain jars
    # of sun-dried tomatoes. The specific creme products use a dedicated compound
    # keyword after normalization, so suppressing the generic family is safe here.
    'soltorkade tomater': {'soltorkadetomatcreme'},
    'soltorkad tomat': {'soltorkadetomatcreme'},
    # "passerade tomater" normalizes to "tomatpassata" and should not fall back
    # to generic fresh tomato matches via the shared "tomat" substring.
    # "tomatpesto" should likewise resolve through pesto products, not fresh tomatoes.
    'tomat': {'tomatpassata', 'tomatpesto', 'soltorkadetomatcreme'},
    'tomater': {'tomatpassata', 'tomatpesto', 'soltorkadetomatcreme'},
    # "syrad gurka" is its own fermented cucumber product concept and should
    # not fall back to generic fresh cucumber.
    'gurka': {'syradgurka'},
    'gurkor': {'syradgurka'},
    # "pimenton ... picante" wants the smoked paprika spice, not generic products
    # that only happen to say "picante" (e.g. salami). Keep the specific pimenton
    # keyword path and suppress the generic heat descriptor in this context.
    'picante': {'pimenton'},
}
