"""Synonym and parent mappings for Swedish ingredient matching."""

from typing import Dict


INGREDIENT_PARENTS: Dict[str, str] = {
    # Rice variants → generic "ris"
    # These 4 types are interchangeable for everyday cooking (stir-fry, stews, etc.)
    'jasminris': 'ris',
    'basmatiris': 'ris',
    'arborio': 'risottoris',  # standalone arborio implies risotto rice
    'arborioris': 'risottoris',  # risotto rice → matches "risottoris" recipes
    'carnaroliris': 'risottoris',  # compound form ("320 g carnaroliris") missed by space norm
    'carnaroli': 'risottoris',  # standalone word ("350 g Zeta Carnaroli") — not caught by compound form
    'vialonenano': 'risottoris',  # another standard risotto-rice family
    'avorio': 'risottoris',  # round-grain risotto rice variant
    # NOTE: fullkornsris intentionally NOT mapped to ris — it's a distinct type
    'långkornsris': 'ris',
    'langkornsris': 'ris',  # without diacritics

    # Pasta variants (short/shaped) → generic "pasta"
    # These are all short-cut shapes that work interchangeably in sauces, salads, etc.
    'fusilli': 'pasta',
    'penne': 'pasta',
    'rigate': 'pasta',      # modifier: "Penne Rigate", "Mezze Maniche Rigate"
    'maniche': 'pasta',     # "Mezze Maniche"
    'mafalda': 'pasta',     # "Mafalda Corta"
    'conchiglie': 'pasta',
    'conchigle': 'pasta',   # alternate spelling
    'gemelli': 'pasta',
    'rigatoni': 'pasta',    # also covers "Mezzi Rigatoni"
    # 'gnocchi': 'pasta',  # REMOVED - gnocchi is a potato dumpling, NOT pasta
    'radiatori': 'pasta',
    'farfalle': 'pasta',
    'tortiglioni': 'pasta',
    'caserecce': 'pasta',
    'girandole': 'pasta',
    'strozzapreti': 'pasta',
    'strozzapretti': 'pasta',  # alternate spelling
    'orecchiette': 'pasta',
    'ziti': 'pasta',        # "Ziti Corti"

    # Long/thin pasta → "långpasta" group (interchangeable within group)
    # These are used for different dishes than short pasta — NOT interchangeable with penne etc.
    'spaghetti': 'långpasta',
    'spagetti': 'långpasta',    # Swedish spelling
    'linguine': 'långpasta',
    'tagliatelle': 'långpasta',
    'fettuccine': 'långpasta',
    'fettuccini': 'långpasta',  # Italian spelling variant (i instead of e)
    'fettucine': 'långpasta',   # alternate spelling
    'pappardelle': 'långpasta',
    'tagliolini': 'långpasta',
    'bucatini': 'långpasta',
    'capellini': 'långpasta',

    # Short pasta additions (were missing)
    'makaroner': 'pasta',
    'maccaronetti': 'pasta',

    # NOT mapped (specific products, match only themselves):
    # gnocchi — potato dumpling, not pasta
    # lasagneplattor — flat sheets, specific use
    # tortellini, tortelloni, ravioli, cannelloni — filled pasta

    # Köttbullar variants → generic "köttbullar"
    'delikatessköttbullar': 'köttbullar',
    'delikatesskottbullar': 'köttbullar',  # without diacritics
    'nötköttbullar': 'köttbullar',
    'notkottbullar': 'köttbullar',  # without diacritics

    # Minute chicken (pre-cut fresh pieces) → generic "kyckling"
    'minutkyckling': 'kyckling',
    'minutstrimlor': 'kyckling',
    'minutfilé': 'kyckling',
    'minutfile': 'kyckling',  # without diacritics
    'minutbitar': 'kyckling',

    # Pommes frites variants → generic "pommes"
    'gårdspommes': 'pommes',
    'gardspommes': 'pommes',  # without diacritics

    # Potato varieties → generic "potatis"
    'mandelpotatis': 'potatis',  # almond potato variety, NOT almonds

    # Vegetable whole-head forms → generic name
    'blomkålshuvud': 'blomkål',  # whole cauliflower head
    'blomkalshuvud': 'blomkål',  # without diacritics
    'kålhuvud': 'vitkål',        # whole cabbage head means plain white cabbage
    'kalhuvud': 'vitkål',        # without diacritics

    # Salad compound forms → base vegetable
    'ruccolasallat': 'rucola',  # "Ruccolasallat" = arugula salad mix
    'ruccolasallad': 'rucola',


    # Egg variants → generic "ägg"
    'frukostägg': 'ägg',

    # Cuisine-specific chicken → generic "kyckling"
    # (also requires cuisine context via CUISINE_CONTEXT below)
    'tacokyckling': 'kyckling',
    'gyroskyckling': 'kyckling',

    # Tomato variants → generic "tomat"
    # Kvisttomater are regular tomatoes sold on the vine — same thing for cooking
    'kvisttomat': 'tomat',
    'kvisttomater': 'tomat',
    # NOTE: körsbärstomater NOT mapped here — default is CANNED (burk).
    # Direct keyword matching against products with "Körsbärstomater" in name.

    # Fresh small tomato variants → generic "småtomat" (interchangeable)
    # All these are essentially the same thing for cooking: small tomatoes.
    # Stefan confirmed: babyplommon, cocktail, körsbär(s), kvisttomater piccolini,
    # småtomater, romantica — all interchangeable when fresh.
    # NOT körsbärstomater (default = canned) or kvisttomat (already → tomat, broader).
    'cocktailtomat': 'småtomat',
    'cocktailtomater': 'småtomat',
    'babyplommontomat': 'småtomat',
    'babyplommontomater': 'småtomat',
    'babyplommon': 'småtomat',  # product keyword from "Tomat Babyplommon"
    'piccolinitomat': 'småtomat',
    'piccolinitomater': 'småtomat',
    'piccolini': 'småtomat',
    'småtomater': 'småtomat',
    'romanticatomat': 'småtomat',
    'romanticatomater': 'småtomat',
    'romantica': 'småtomat',
    # NOTE: plommontomater → tomat (regular-sized plum tomatoes, NOT small)
    # Only babyplommon are small and in the småtomat group.
    'plommontomat': 'tomat',
    'plommontomater': 'tomat',

    # Fennel seeds → generic "fänkål"
    # SVF has 'frö'/'fänkålsfrö' in allowed_indicators → unlocks dried products ✓
    # SVF has 'frö'/'fänkålsfrö' in dried_indicators → blocks fresh Klass 1 ✓
    'fänkålsfrön': 'fänkålsfrö',
    'fankalsfron': 'fankalsfro',
    'fänkålsfrö': 'fänkål',
    'fankalsfro': 'fänkål',  # without diacritics

    # Coriander seeds → generic "koriander"
    # SVF rule for koriander blocks fresh products when recipe has 'frö' indicator
    'korianderfrön': 'koriander',
    'korianderfron': 'koriander',  # without diacritics

    # Walnut kernels → walnuts (same product, different naming)
    'valnötskärnor': 'valnötter',
    'valnotskarnor': 'valnotter',

    # Hazelnut kernels → hazelnuts (same product, different naming)
    'hasselnötkärnor': 'hasselnötter',
    'hasselnotkarnor': 'hasselnotter',

    # Pumpkin seeds — two Swedish names for the same product
    'pumpakärnor': 'pumpafrön',    # "Pumpakärnor Rostade" matches recipe "pumpafrön"
    'pumpakaernor': 'pumpafrön',
    'pumpakarnor': 'pumpafron',
    'pumpafrön': 'pumpakärnor',    # reverse: recipe "pumpakärnor" matches offer "pumpafrön"
    'pumpafron': 'pumpakarnor',

    # Chickpeas — both plural spellings occur in products and recipes
    'kikärtor': 'kikärter',
    'kikartor': 'kikarter',
    'kikärter': 'kikärtor',
    'kikarter': 'kikartor',

    # Black eye beans — specific bean type should still fall back to generic beans.
    'blackeyeböna': 'böna',
    'blackeyebönor': 'bönor',
    'blackeyebona': 'bona',
    'blackeyebonor': 'bonor',
    # Mixed bean products should satisfy generic mixed-bean recipe lines.
    'bönmix': 'bönor',
    'bonmix': 'bonor',

    # Strömmingsflundra → strömming (dish name, NOT flounder)
    # "Strömmingsflundra" is a Baltic herring preparation — 'flundra' in the name
    # is a shape descriptor, not the fish species. Without this mapping, the
    # extracted 'flundra' falsely matches Pacific flounder products.
    'strömmingsflundra': 'strömming',
    'strommingsflundra': 'strömming',

    # Fish grytbitar → lax (only fish grytbitar product in stores is "Lax Grytbitar")
    'fiskgrytbitar': 'lax',
    # Plural filé-forms — "4 laxfiléer" → laxfilé (8 recipes)
    'laxfiléer': 'laxfilé',
    'laxfileer': 'laxfilé',
    # Storkornskaviar = large-grain roe = stenbitsrom (storkorning variant)
    'storkornskaviar': 'stenbitsrom',
    # Whole cinnamon → generic "kanel"
    # SPICE_VS_FRESH rule handles blocking ground products for kanelstång recipes
    'kanelhel': 'kanel',

    # Citrus juice products → parent fruit
    # Requires JUICE_PRODUCT_INDICATORS check in matching paths to ensure
    # ingredient actually calls for juice/saft, not whole fruit.
    'citronjuice': 'citron',
    'limejuice': 'lime',
    # Generic "karamellfärg" recipe wording maps to the standard food-color family
    # sold as "hushållsfärg" in current offers.
    'karamellfärg': 'hushållsfärg',
    'karamellfarg': 'hushållsfärg',
    'limefrukt': 'lime',  # "limefrukt" = same as "lime" (67 recipes)
    # Plural forms — "2 avokador" → avokado (71 recipes)
    'avokador': 'avokado',
    'avocados': 'avokado',  # English plural — "4 st Avocados" (javligtgott.se)
    # Hirs forms — "hirsflingor" → hirs (millet flakes → millet)
    'hirsflingor': 'hirs',
    # Banana — "3 st bananer" → banan. Needed for reverse matching
    # (product "Banan ca 180g Klass 1 ICA" → recipe ingredient "bananer").
    # COMPOUND_STRICT blocks bananschalottenlök (different item).
    'bananer': 'banan',

    # NOTE: Swedish everyday cheeses are intentionally NOT normalized from the
    # ingredient side to generic "ost". If a recipe explicitly asks for
    # "prästost" / "hushållsost" / "herrgård" etc., it should stay specific.
    # The broader "ost" fallback is added on the PRODUCT side via IMPLICIT_KEYWORDS
    # so generic cheese recipes still surface these products.
    # NOT included: västerbottens — distinct flavor, should NOT match generic "ost" recipes.
    # User explicitly requested exclusion. Västerbottens is in SPECIALTY_QUALIFIERS.
    # NOT included: use-case cheeses (gratängost, texmexost, etc.) — handled
    # via KEYWORD_EXTRA_PARENTS / product-side rules to keep BOTH specific + generic coverage.

    # Brand cheese → generic type
    'philadelphiaost': 'färskost',  # "philadelphiaost" in recipes = cream cheese

    # Cream types → generic "grädde"
    # Both vispgrädde and matlagningsgrädde map to "grädde".
    # Matgrädde → matlagningsgrädde synonym handled in _SPACE_NORMALIZATIONS.
    # SPECIALTY_QUALIFIERS prevents matgrädde matching "vispgrädde" recipes.
    'vispgrädde': 'grädde', 'vispgradde': 'gradde',
    'matlagningsgrädde': 'grädde', 'matlagningsgradde': 'gradde',
    # NOTE: havregrädde NOT mapped to grädde — recipe saying "havregrädde" should
    # only match havregrädde products, not all dairy cream. Reverse direction works:
    # recipe "grädde" matches product "havregrädde" via reverse substring.

    # Pickled cucumber types → "inlagdgurka" (NOT "gurka" — fresh ≠ pickled)
    # SPACE_NORM normalizes the text first, then keyword extraction gets "inlagdgurka"
    'smörgåsgurka': 'inlagdgurka', 'smorgasgurka': 'inlagdgurka',
    'ättiksgurka': 'inlagdgurka', 'attiksgurka': 'inlagdgurka',
    'saltgurka': 'inlagdgurka',
    # NOTE: bostongurka not mapped to inlagdgurka — different product (sweet relish vs pickled cucumber)

    # Shrimp: ishavsräkor are just large peeled shrimp
    'ishavsräkor': 'räkor', 'ishavsrakor': 'rakor',

    # Kräftor: generic whole-crayfish recipe wording maps to the common
    # signalkräftor family in stores. Explicit havskräftor is still allowed
    # to ride that same broad crayfish family in ordinary grocery matching.
    'kräftor': 'signalkräftor', 'kraftor': 'signalkraftor',
    'signalkräfta': 'signalkräftor', 'signalkrafta': 'signalkraftor',
    'havskräfta': 'havskräftor', 'havskrafta': 'havskraftor',

    # Cheese: recipes say "brieost", stores sell "Brie"
    'brieost': 'brie',

    # Cheese: recipes say "gruyèreost"/"gruyerost", stores sell "Gruyère"/"Gruyere"
    # Map to non-accented 'gruyere' — matches inverted index AND substring in 'gruyerost'
    'gruyèreost': 'gruyere', 'gruyereost': 'gruyere',
    'gruyerost': 'gruyere',

    # Senapsfrön: recipes say "senapsfrön" (plural), stores sell "Senapsfrö" (singular)
    'senapsfrön': 'senapsfrö', 'senapsfron': 'senapsfrö',

    # Linfrön (plural) → linfrö (singular): stores sell "Linfrön 300g", recipes say "1 dl linfrö"
    'linfrön': 'linfrö', 'linfron': 'linfro',

    # Corn starch / thickener: recipes say "maizena", "majsena", or "redning"
    # Stores sell "Majsstärkelse", "Ljus Redning", "Brun Redning"
    # All are interchangeable thickeners → map to "majsstärkelse"
    'maizena': 'majsstärkelse',
    'majsena': 'majsstärkelse',
    'redning': 'majsstärkelse',

    # Korianderblad: "Korianderblad Burk" = dried coriander leaves → generic "koriander"
    'korianderblad': 'koriander',

    # Sardell variants → match "Sardeller" products
    'sardellfiléer': 'sardeller', 'sardellfileer': 'sardeller',
    'sardellfilé': 'sardeller', 'sardellfile': 'sardeller',
    # sardellcreme: three accent variants (recipe è, Willys é, ICA éme) → plain
    'sardellcrème': 'sardellcreme', 'sardellcremé': 'sardellcreme',
    'sardellcréme': 'sardellcreme',
    'sardellkräm': 'sardellcreme',
    'sardellkram': 'sardellcreme',  # ASCII-normalized variant

    # Sriracha sauce: recipes say "sriracha" or "srirachasås" interchangeably
    # Shorter form 'sriracha' matches both since it's a substring of 'srirachasås'
    'srirachasås': 'sriracha',


    # Worcestershire sauce: Swedish stores often shorten the product name to
    # "worcestersås", while recipes frequently use the full "worcestershiresås".
    'worcestershiresås': 'worcestersås',
    'worcestershiresas': 'worcestersas',
    'worchestersås': 'worcestersås',
    'worchestersas': 'worcestersas',

    # Liba bread products: recipe text often uses the branded flatbread term
    # "libabröd", while store products may expose either "liba" or "tunnbröd".
    'libabröd': 'tunnbröd',
    'libabrod': 'tunnbröd',
    'liba': 'tunnbröd',

    # Onion variants
    # NOTE: schalottenlök NOT mapped to generic 'lök' — too broad.
    # Instead, space normalization "lök schalotten" → "schalottenlök" on product side.
    'schalotten': 'schalottenlök',  # product name fragment "Schalotten" → schalottenlök
    'schalottenlökar': 'schalottenlök',  # plural
    'schalottenlokar': 'schalottenlök',  # plural without diacritics
    'scharlottenlök': 'schalottenlök',  # spelling variant with 'r' (Zeta recipes)
    'scharlottenlökar': 'schalottenlök',  # plural of spelling variant
    'scharlottenlokar': 'schalottenlök',  # without diacritics
    'lökar': 'lök',  # plural form ("2 gula lökar" → lök)
    'lokar': 'lök',  # without diacritics
    'steklökar': 'steklök',  # plural → singular
    'steklokar': 'steklök',  # without diacritics
    'rödlökar': 'rödlök', 'rodlokar': 'rodlok',  # plural → singular
    'salladslökar': 'salladslök', 'salladslokar': 'salladslok',  # plural → singular

    # Romaine lettuce: recipes write "romansallat", products say "romansallad"
    'romansallat': 'romansallad',
    'krispsallad': 'krispsallat',
    # Little Gem / gem lettuce recipes should match the common grocery family
    # sold as hjärtsallad.
    'gemsallad': 'hjärtsallad',
    'babygemsallad': 'hjärtsallad',
    'gemsalladshuvud': 'hjärtsallad',
    'gemsalladshuvuden': 'hjärtsallad',

    # Selleri stalk variants → "bladselleri" (store term for celery stalks)
    'selleristjälkar': 'bladselleri',
    'selleristjalkar': 'bladselleri',  # without diacritics
    'selleristjälk': 'bladselleri',  # singular
    'selleristjalk': 'bladselleri',  # singular without diacritics
    'blekselleristjälkar': 'bladselleri',  # "blekselleri" = pale celery stalks
    'blekselleristjälk': 'bladselleri',  # singular

    # Pasta plates → "lasagneplattor" (store term for fresh pasta sheets)
    'pastaplattor': 'lasagneplattor',

    # Paprikakrydda → paprikapulver (via SPACE_NORM), then INGREDIENT_PARENTS maps to 'paprikapulver'
    # FTS exact-token: keyword "paprika" only matches products with word "paprika" (fresh peppers)
    # but NOT "Paprikapulver 70g" (different token). Must keep keyword as "paprikapulver".
    'paprikakrydda': 'paprikapulver',

    # Cooking oil: "matolja" in recipes → rapsolja (standard Swedish cooking oil)
    # FALSE_POSITIVE_BLOCKERS on 'rapsolja' already blocks "Smör & Rapsolja" etc.
    'matolja': 'rapsolja',

    # Singular/plural mismatches — recipes use one form, stores the other
    'nejlika': 'nejlikor',  # "1 hel nejlika" → "Nejlikor Hela Påse" (88 recipes)
    'kryddnejlika': 'nejlikor',  # product form → recipe form ("Kryddnejlikor Hela" = cloves spice)
    'kryddnejlikor': 'nejlikor',
    'gulbetor': 'gulbeta',  # "4 gulbetor" → "Gulbeta Klass 1"
    'sockerärta': 'sockerärtor',  # "150 g Sockerärta Färsk" → "Sockerärtor Klass 1" (176 recipes)
    'sockerarta': 'sockerärtor',  # without diacritics
    'sockerärter': 'sockerärtor',  # alternate plural — "100 g sockerärter" (recipe variant)
    'sockerarter': 'sockerärtor',  # without diacritics
    'sugarsnaps': 'sockerärtor',  # common Swedish loanword for sugar snap peas
    'sugarsnap': 'sockerärtor',
    'salladsärta': 'salladsärtor',
    'salladsarta': 'salladsärtor',
    'salladsärter': 'salladsärtor',
    'salladsarter': 'salladsärtor',
    'potatisklyftor': 'klyftpotatis',  # store form → recipe form for frozen wedge potatoes
    'muscovadorörsocker': 'muscovadosocker',  # store spelling variant for muscovado sugar
    'muscovadororsocker': 'muscovadosocker',  # without diacritics
    'råsocker': 'rörsocker',  # common retail equivalent in Swedish grocery offers
    'rasocker': 'rörsocker',
    'wasabipasta': 'wasabi',
    'wasabipulver': 'wasabi',
    'gullök': 'lök',  # "1 gullök" (compound) → "Lök Gul Klass 1" (2 recipes)
    'gullok': 'lök',  # without diacritics
    'sashimilax': 'sushilax',  # "360 g Sashimilax" → "Sushilax" (specific raw salmon variant, 7 recipes)
    'trattkantareller': 'kantareller',  # trumpet chanterelles → chanterelles (16 recipes)
    'trattkantarell': 'kantareller',
    'polkabetor': 'polkabeta',  # plural → singular: "200 g Polkabetor" → "Polkabeta Klass 1" (20 recipes)

    # Nutmeg: recipe says "muskot", product is "Muskotnöt Malen/Hel" (90 recipes)
    'muskot': 'muskotnöt',
    'muskotnot': 'muskotnöt',

    # "nöt" in product names like "Högrev av nöt" means cattle, not nut.
    # Replace with 'nötkött' so the generic 'nöt' keyword doesn't match
    # nut ingredients (nötmix, pinjenöt) or ground meat (nötfärs) via substring.
    'nöt': 'nötkött',
    'not': 'nötkött',  # ascii variant

    # Chili fruit plural → "chili"
    'chilifrukter': 'chili',  # "20 g Chilifrukter" = fresh chili peppers

    # Chili: generic forms → "chili"
    # Spice-vs-fresh rules on 'chili' handle blocking dried/processed products
    'chilifrukt': 'chili',  # "chilifrukt" = generic fresh chili pepper
    'chilipeppar': 'chili',  # "Chilipeppar Röd" in recipes = generic fresh chili
    # NOTE: specific varieties are NOT mapped to generic "chili" —
    # they are distinct types. Map to their specific name instead.
    'anchochili': 'ancho',
    'habanerochili': 'habanero',
    'nagachili': 'naga',
    'jalapenos': 'jalapeno',  # plural → singular
    # chipotlepasta is its OWN product (paste/puré), not the dry spice

    # Basilika: "basilka" is a common misspelling in recipes
    'basilka': 'basilika',
    'basilikablad': 'basilika',  # "några basilikablad" = basilika

    # Potatis/morot plural forms → singular
    'potatisar': 'potatis',
    'morötter': 'morot',
    'morotter': 'morot',  # without diacritics
    'delikatesspotatis': 'potatis',  # fancy name for firm potatoes
    'snackmorötter': 'morot',  # snack carrots = carrots
    # NOTE: färskpotatis NOT mapped to potatis — specific type, not interchangeable.
    # Reverse (recipe "potatis" → offer "Färskpotatis") needs one-way offer-side mapping (TODO).
    'tomater': 'tomat',  # plural
    'kantareller': 'kantarell',  # plural
    'murklor': 'murkla',  # plural
    'fläskkotletter': 'fläskkotlett',  # plural

    # Kyckling variants → generic "kyckling"
    'kycklingar': 'kyckling',
    # kycklingbröst = kycklingbröstfilé in practice → map to kycklingfilé
    'kycklingbröst': 'kycklingfilé',
    'kycklingbrost': 'kycklingfilé',
    # Plural forms — "4 kycklingfiléer" → kycklingfilé (57 recipes use this form)
    'kycklingfiléer': 'kycklingfilé',
    'kycklingfileer': 'kycklingfilé',
    # NOTE: kycklingvingar→kycklingvinge and kycklingklubbor→kycklingklubba
    # handled by _SPACE_NORMALIZATIONS (text-level, works for both sides)

    # Köttfärs = generic minced meat → map to 'färs'
    # Stores sell "Nötfärs", "Blandfärs" etc. — never "Köttfärs"
    # As standalone 'färs', matches all färs products via COMPOUND_STRICT
    'köttfärs': 'färs',
    'kottfars': 'färs',  # without diacritics
    # Generic/old terms → generic färs
    'hushållsfärs': 'färs',  # old Swedish term ≈ blandfärs
    'hushallsfars': 'färs',
    # Spelling fix
    'lamfärs': 'lammfärs',  # common misspelling (one m)
    'lamfars': 'lammfärs',
    # Plant-based synonym
    'sojafärs': 'vegofärs',
    'sojafars': 'vegofärs',
    # Quorn compound → match "Färs Mince Quorn" product
    'quornfärs': 'quorn',  # product has keywords ['färs', 'quorn']
    'quornfars': 'quorn',

    # Squash = zucchini (squash is the older Swedish word, stores use zucchini)
    'squash': 'zucchini',

    # Jordärtskocka plural → singular
    'jordärtskockor': 'jordärtskocka',
    'jordartskockor': 'jordärtskocka',  # without diacritics

    # Rödbeta plural → singular
    'rödbetor': 'rödbeta',
    'rodbetor': 'rödbeta',

    # Swedish -a → -or plurals (product side)
    'palsternackor': 'palsternacka',
    'kronärtskockor': 'kronärtskocka',
    'kronartskockor': 'kronärtskocka',
    'paprikor': 'paprika',
    'gurkor': 'gurka',
    'persikor': 'persika',
    # Swedish -rot → -rötter plural
    'kålrötter': 'kålrot',
    'kalrotter': 'kålrot',

    # Kanel forms → generic "kanel"
    # Kanelstång = whole cinnamon stick → maps to "kanel"
    # SPICE_VS_FRESH rule on 'kanel' blocks ground (malen/cassia/ceylon) products
    # when ingredient has stång/hel indicator
    'kanelstång': 'kanel',
    'kanelstang': 'kanel',  # without diacritics
    'kanelstänger': 'kanel',  # plural
    'kanelstanger': 'kanel',  # without diacritics

    # Kardemumma forms
    'kardemummakapslar': 'kardemumma',  # whole cardamom pods → cardamom
    'kardemummakapsel': 'kardemumma',

    # Mandel singular → plural (ingredient "hackad mandel" / "rostad mandel")
    'mandel': 'mandlar',

    # Plural sausage wording should keep the generic korv family.
    'korvar': 'korv',

    # Sötmandel = vanlig mandel
    'sötmandel': 'mandlar',
    'sötmandlar': 'mandlar',
    'sotmandel': 'mandlar',  # without diacritics
    'sotmandlar': 'mandlar',  # without diacritics

    # Bananschalottenlök → schalottenlök (same family, not generic lök)
    'bananschalottenlök': 'schalottenlök',
    'bananschalottenloek': 'schalottenlök',  # without diacritics
    'bananschalotten': 'schalottenlök',  # fragment from word splitting
    'bananscharlottenlök': 'schalottenlök',  # common typo variant (r inserted)
    'bananscharlottenlock': 'schalottenlök',  # typo without diacritics

    # Mjölk forms → generic "mjölk"
    'standardmjölk': 'mjölk',
    'standardmjolk': 'mjölk',  # without diacritics

    # Plant milk: consumer term "havremjölk" → legal product term "havredryck"
    # Swedish law prohibits calling oat drink "mjölk"; stores label it "havredryck"
    'havremjölk': 'havredryck',
    'havremjolk': 'havredryck',  # without diacritics

    # Skånsk senap: compound keyword maps to generic "senap" parent so that
    # recipes saying just "senap" still match skånsk senap products via parent path.
    'skånsksenap': 'senap',
    'comteost': 'comte',

    # Yoghurt: "matlagningsyoghurt" → "yoghurt"
    # Products are named "Yoghurt för Matlagning", not "Matlagningsyoghurt"
    'matlagningsyoghurt': 'yoghurt',

    # Mint: "myntablad" = mint leaves = mynta
    'myntablad': 'mynta',

    # Cayenne spelling variant (kajenn = Swedish phonetic spelling)
    'kajennpeppar': 'cayennepeppar',

    # Äggulor → ägg (egg yolks are part of eggs, no separate yolk products)
    'äggulor': 'ägg',
    'äggula': 'ägg',
    'maränger': 'maräng',
    'maranger': 'marang',

    # Parsley forms → generic "persilja"
    'persiljestjälk': 'persilja',  # parsley stems (used in stocks/reductions)
    # 'bladpersilja' NOT mapped to 'persilja' — they are different varieties
    # (flat-leaf vs curly). Kept as separate keyword for distinct matching.

    # Bouillon cubes → bouillon (tärning/tärningar = cube/cubes, packaging form)
    'köttbuljongtärning': 'köttbuljong',
    'köttbuljongtärningar': 'köttbuljong',
    'kycklingbuljongtärning': 'kycklingbuljong',
    'kycklingbuljongtärningar': 'kycklingbuljong',
    'grönsaksbuljongtärning': 'grönsaksbuljong',
    'grönsaksbuljongtärningar': 'grönsaksbuljong',
    'buljongtärning': 'buljong',
    'buljongtärningar': 'buljong',
    # Höns = Kyckling in Swedish cooking (hönsbuljong = kycklingbuljong)
    'hönsbuljong': 'kycklingbuljong',
    'honsbuljong': 'kycklingbuljong',
    'hönsbuljongtärning': 'kycklingbuljong',
    'hönsbuljongtärningar': 'kycklingbuljong',
    # Fond and buljong are separate product categories:
    # - Buljong = tärningar/pulver (dry stock cubes)
    # - Fond = flytande (liquid stock)
    # "kycklingbuljong eller fond" is handled by rewriting to "kycklingbuljong eller kycklingfond"
    # in extract_keywords_from_ingredient, producing both keywords.
    # Specific fond→fond mappings kept so fond products match their own keyword.
    'oxfond': 'köttfond',              # oxfond = beef stock, matches köttfond products
    'schalottenlökfond': 'schalottenlöksfond',
    # NOTE: hummerfond NOT mapped — it's its own product keyword

    # Dragon (tarragon) compounds
    'dragonreduktion': 'dragon',  # tarragon reduction needs tarragon herb

    # Olive oil: "jungfruolivolja" (extra virgin) = olivolja
    'jungfruolivolja': 'olivolja',

    # Garlic form words → generic "vitlök"
    'vitlöksklyfta': 'vitlök',
    'vitloksklyfta': 'vitlök',  # without diacritics
    'vitlöksklyftor': 'vitlök',
    'vitloksklyftor': 'vitlök',  # without diacritics
    'vitlöksklyft': 'vitlök',
    'vitloksklyft': 'vitlök',  # without diacritics

    # Japanese/Korean ingredient forms
    'noriblad': 'nori',  # "2 st noriblad" → nori seaweed sheets
    'sjögräsark': 'nori',  # "4 st sjögräsark" → nori sushi sheets
    'sjograsark': 'nori',

    # Herb stem/twig forms → parent herb
    'timjankvistar': 'timjan',  # "4 kvistar timjan" = thyme sprigs
    'timjankvista': 'timjan',  # singular without r
    'persiljekvistar': 'persilja',  # "ett par persiljekvistar" = fresh parsley sprigs
    'persiljekvista': 'persilja',  # singular without r
    # Citrus forms
    'citronzest': 'citron',  # lemon zest = lemon product
    'citrongrässtjälkar': 'citrongräs',  # lemongrass stalks = lemongrass
    'citrongrasstjalkar': 'citrongräs',  # without diacritics
    # Cheese forms
    'miniburrata': 'burrata',  # mini burrata = burrata
    # Block chocolate (recipe compound) → bakchoklad (product keyword)
    # "blockchoklad" in recipe = baking chocolate. Without this, FPB 'blockchoklad' blocks
    # bakchoklad products because 'bakchoklad' isn't substring of 'blockchoklad'.
    # This mapping creates _INGREDIENT_PARENTS_REVERSE['bakchoklad'] → {'blockchoklad'}
    # so products with keyword 'bakchoklad' try matching 'blockchoklad' in ingredient text.
    'blockchoklad': 'bakchoklad',
    # NOTE: kalkon and salami compounds are in PARENT_MATCH_ONLY (not here)
    # to avoid extraction replacement and reverse mapping.
    # NOTE: steklökar NOT mapped to lök — steklök is a specific onion variety
    # NOTE: granapadano NOT mapped to parmigiano — different cheese (similar but not interchangeable)

    # Ice cream: generic/type descriptors → 'vaniljglass' (vanilla is the default)
    # Flavor-specific keywords (chokladglass, jordgubbsglass, etc.) are kept as-is
    # so they only match products with the matching base flavor.
    'glass': 'vaniljglass',
    'gräddglass': 'vaniljglass',
    'graddglass': 'vaniljglass',
    # NOTE: 'isglass' intentionally NOT mapped — isglass products are novelty items, always blocked
    # NOTE: chokladglass, jordgubbsglass, kanelglass, sojaglass, lakritsglass
    # intentionally NOT mapped — they stay as-is for flavor-specific matching.

    # Cider variants → generic 'cider'
    # äppelcider (from SPACE_NORM "cider äpple" → "äppelcider") maps to parent cider
    # so offer "Äppelcider Original" matches recipe "2 dl cider"
    'äppelcider': 'cider',
    'applelcider': 'cider',  # without diacritics
}

KEYWORD_SYNONYMS: Dict[str, str] = {
    'ärter': 'ärtor',  # product says "ärter", recipes say "ärtor"
    'cabanossy': 'kabanoss',  # alternative spelling of Polish sausage
    'fries': 'pommes',  # "Premium Fries Super Crunch" → recipes say "pommes frites"
    'frites': 'pommes',  # "Jumbo Frites" → recipes say "pommes frites"
    'mustard': 'senap',  # "Yellow Mustard Johnny's" → recipes say "senap"
    'tandori': 'tandoori',  # common recipe typo should match tandoori products
    'drumsticks': 'kycklingben',  # "Kyckling Drumsticks" → recipes say "kycklingben"
    'burger': 'hamburgare',  # "Marrowbone Beef Burger" → recipes say "hamburgare"
    'beef': 'nötkött',  # "Beef Burger" → recipes say "nötkött"
    'philadelphia': 'färskost',  # Philadelphia brand = cream cheese (färskost)
    'pecannöt': 'pekannöt',  # product spelling variant → recipe spelling
    'pecannot': 'pekannot',
    'pecannötter': 'pekannötter',
    'pecannotter': 'pekannotter',
    'haricots': 'haricot',  # French plural form on products, singular in recipes
    'chilli': 'chili',  # double-l spelling variant (e.g., "Chilli Peppar Röd Kl1")
    'chillipeppar': 'chilipeppar',  # compound form of double-l variant
    'morötter': 'morot',  # product "Morötter Klass 1" → recipe uses "morot" (via ISK)
    'morotter': 'morot',  # without diacritics
    'ruccola': 'rucola',  # product "Ruccola Klass 1" → recipe says "rucola" (single c)
    'machesallad': 'machesallat',  # recipe spelling should match product "Machesallat"
    'cantucci': 'cantuccini',  # product/recipe spelling variant
    'biscotti': 'cantuccini',  # same Italian biscuit family in recipes
    'gille-drömmar': 'drömmar',  # branded cookie pack should match recipe "drömmar"
    'gille-drommar': 'drommar',
    'savoiardokex': 'savoiardikex',
    'savoiarde': 'savoiardikex',  # store wording for ladyfinger biscuits
    'savoiardi': 'savoiardikex',
    'spätta': 'rödspätta',
    'spatta': 'rodspatta',
    'spättafilé': 'rödspättafilé',
    'spättafile': 'rodspattafile',
    'spättafiléer': 'rödspättafilé',
    'spattafileer': 'rodspattafile',
    'västerbottens': 'västerbottensost',  # product "Västerbottens Original Ost" → recipe says "västerbottensost"
    'vasterbottens': 'västerbottensost',  # without diacritics
    'humrar': 'hummer',  # plural of hummer (lobster)
    'balsamica': 'balsamico',  # "Glassa Balsamica" → recipes say "balsamico"
    'bjäst': 'näringsjäst',  # nutritional yeast — "bjäst" in recipes → match "näringsjäst" products
    # Blue cheese naming varies across recipes/offers (grönmögel/blåmögel/ädelost).
    # Normalize them into the existing ädelost family.
    'blåmögelost': 'ädelost',
    'blamogelost': 'adelost',
    'grönmögelost': 'ädelost',
    'gronmogelost': 'adelost',
    'muscovadosocker': 'muskovadosocker',  # product spelling variant → common recipe spelling
    # Hazelnut spread → generic nut cream keyword
    # "Hasselnötkräm Nutella" should match recipes asking for "nötkräm" (nut cream spread)
    'hasselnötkräm': 'nötkräm',
    'hasselnotkram': 'nötkräm',  # without diacritics
    'karamelliseradmjolk': 'karamelliseradmjölk',
    'kondenseradmjolk': 'kondenseradmjölk',
    # Elderflower cordial products are commonly labeled "fläderblomssaft"/"fläderblomsaft"
    # while recipes often ask for the shorter "flädersaft".
    'fläderblomssaft': 'flädersaft',
    'fläderblomsaft': 'flädersaft',
    'fladerblomssaft': 'fladersaft',
    'fladerblomsaft': 'fladersaft',
    # Wild-raspberry cordial is a normal substitute for generic raspberry cordial.
    'skogshallonsaft': 'hallonsaft',
    # Soft caramel candy wording varies between recipe "kolakaramell" and
    # current product names like "Gräddkola" / "Gräddkaramell".
    'gräddkola': 'kolakaramell',
    'graddkola': 'kolakaramell',
    'gräddkaramell': 'kolakaramell',
    'graddkaramell': 'kolakaramell',
}
