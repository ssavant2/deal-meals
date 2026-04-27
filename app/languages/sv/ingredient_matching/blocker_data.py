"""Blocker data for Swedish ingredient matching.

This module contains the two largest blocker tables plus their normalized
variants. It is intentionally data-only so it can be imported safely from both
legacy and future refactored matcher modules.

Used by:
- matching.py — fast keyword/path checks
- match_filters.py — blocker helper functions
- recipe_matcher.py — per-ingredient PRODUCT_NAME_BLOCKERS validation
"""

from typing import Dict, Set

try:
    from languages.sv.normalization import fix_swedish_chars
except ModuleNotFoundError:
    from app.languages.sv.normalization import fix_swedish_chars


# FALSE POSITIVE BLOCKERS - Ingredients that contain keywords but aren't related
# ============================================================================
# Problem: "ost" keyword matches "Ostronsås" because "ost" is substring of "ostron"
# Solution: If ingredient contains these words, block the keyword match
# Format: keyword -> set of words in ingredient that block the match

_FALSE_POSITIVE_BLOCKERS_RAW: Dict[str, Set[str]] = {
    'ost': {
        'ostron', 'ostronsås', 'ostronsas',  # oyster sauce is NOT cheese
        'rostad', 'rostade', 'rostat', 'rosta', 'rostning',  # "Rostade jordnötter" / "rostning" - ost is substring
        'färskost',  # "Färskost" is specific cheese type - should match färskost products only
        'bostongurka',  # "ost" is substring of "bostongurka" - NOT cheese!
        'ostsmak',  # cheese-flavored (e.g. nacho chips) ≠ actual cheese
        'panko',  # "ost" is substring of "pankoströbröd" (pank-ost-röbröd)
        # Non-cheese words containing "ost" as substring
        'rostbiff',  # roast beef - "ost" is substring of "rostbiff"
        'rostbröd', 'rostbrod',  # toast bread - "ost" is substring of "r-ost-bröd"
        'råkost', 'rakost', 'råkostsallad', 'rakostsallad',  # coleslaw - "ost" substring of "råkost"
        'frukost',  # breakfast - "ost" in "frukostkorv"
        'crostini',  # Italian bread - "ost" substring of "crostini"
        'hälsokost', 'halsokost',  # health food - "hälsokostaffär", "hälsokostbutik"
        'hushållsfärs', 'hushallsfars',  # ground meat - "hushåll" in "hushållsost" is prefix of "hushållsfärs"
        'angostura',  # bitters - "ost" substring of "angostura"
        'kokostyp',  # "ost" substring of "kokostyp" (coconut type) - NOT cheese
        'ostlöpe', 'ostlope',  # rennet - completely different product
        # Specific cheese types - generic "ost" should NOT match recipe asking for specific cheese
        # (the specific cheese name keyword will still match, e.g. "gouda" → "goudaost")
        # Source: Willys cheese assortment (~320 products)
        # NOTE: Generic Swedish cheeses (präst, herrgård, grevé, svecia, edamer, gouda,
        # hushåll, gratäng) are NOT listed here — they map to "ost" via INGREDIENT_PARENTS
        # and should match any "ost" recipe.
        # Swedish specialty cheeses
        'västerbotten', 'vasterbotten',  # very common in Swedish recipes, distinct flavor
        'billinge', 'brännvinsost', 'brannvinsost', 'storsjö', 'storsjo',
        # Blue cheeses
        'blåmögel', 'blamogel', 'ädel', 'adel', 'ädelost', 'adelost',
        'gorgonzola', 'danablu', 'roquefort', 'stilton',
        # International hard/semi-hard (gouda/edamer excluded — mapped to ost via INGREDIENT_PARENTS)
        'manchego', 'cheddar', 'emmentaler',
        'gruyère', 'gruyere', 'jarlsberg', 'havarti', 'danbo',
        'maasdamer', 'norvegia', 'grana padano', 'parmigiano',
        'parmesan', 'pecorino', 'comté', 'comte',
        # Soft/fresh
        'brie', 'camembert', 'ricotta', 'mascarpone', 'burrata',
        'taleggio', 'taleggioost', 'taleggio-ost',
        'mozzarella', 'stracciatella', 'chèvre', 'chevre',
        'feta', 'fetaost',  # Greek brine cheese — specific type, not generic ost
        'philadelphia',  # cream cheese brand
        'paneer',  # Indian cheese
        # Specialty/functional types
        'halloumi', 'grillost',
        'getost', 'gräddost', 'graddost', 'vitost', 'salladsost',
        'färskost', 'farskost', 'smältost', 'smaltost', 'mesost', 'messmör', 'messmor',
        'gratängost', 'gratangost', 'pizzaost', 'hamburgerost',
        'kryddost', 'dessert',
        # Compound cheese products (food+ost)
        'baconost', 'räkost', 'rakost', 'skinkost', 'salamiost', 'kräftost', 'kraftost',
        'port salut',
        # Seasoned/flavored/specialty compound cheeses
        'texmexost',  # seasoned tex-mex cheese blend (spiced, different use)
        'mjukost',  # soft spreadable cheese (tube/tub, different from block cheese)
        'anchostyle',  # "Chilipeppar Anchostyle" — NOT cheese, just substring coincidence
        'post-it',  # office supplies — "ost" substring of "post-it"
        'ostbågar', 'ostbagar',  # cheese puffs (snack) - NOT cheese
        'ostbåge', 'ostbage',  # singular form
        'osthyvel',  # cheese slicer (kitchen tool) - NOT cheese
        # Flavored snacks - "ost" is flavor, not ingredient (joined via _SPACE_NORMALIZATIONS)
        'tortillachipsost',  # "tortillachips ost" = cheese-flavored chips
        'nachosost',  # "nachos ost" = cheese-flavored nachos
        'oregano',  # "ost" substring of "oreganostrimlad" — NOT cheese
        'ostsås', 'ostsas',  # cheese sauce (ready-made) ≠ block cheese
        'ostbricka',  # cheese platter (assorted) ≠ single cheese product
    },
    'gratäng': {
        # Dish names ending in "-gratäng" are NOT cheese ingredients
        # "Gratängost" should NOT match ingredient "potatisgratäng" (dish name)
        'potatis',  # potatisgratäng
        'fisk',  # fiskgratäng
        'kyckling',  # kycklinggratäng
        'pasta', 'makaroni',  # pastagratäng, makaronigratäng
        'grönsak', 'gronsak',  # grönsaksgratäng
        'lax',  # laxgratäng
        'morot',  # morotsgratäng
        'purjolök', 'purjolok',  # purjolöksgratäng
        'kål', 'kal',  # kålgratäng
        'zucchini', 'squash',  # grönsaksgratänger
    },

    # Onion types - "lök" keyword should NOT match specific onion types in recipes
    # "Gul Lök" product should NOT match recipe saying "vitlök" or "schalottenlök"
    'lök': {
        'vitlök', 'vitlok',  # garlic
        'rödlök', 'rodlok',  # red onion
        'gullök', 'gullok',  # yellow onion (compound form)
        'salladslök', 'salladslok',  # spring onion
        'purjolök', 'purjolok',  # leek
        'schalottenlök', 'schalottenlock', 'schalotten',  # shallot
        'steklök', 'stelock',  # fried onion
        'silverlök', 'silverlok',  # pearl onion
        'vårlök', 'varlok',  # spring onion
        'gräslök', 'graslok',  # chives (completely different from onion)
        'knipplök', 'knipplok', 'knipplökar', 'knipplokar',  # pearl onion variety
        'syltlök', 'syltlok',  # pickled pearl onions (preserved product)
        'ramslök', 'ramslok',  # wild garlic/ramsons (different herb)
        'pärllök', 'parllok',  # pearl onion (specific variety)
        'lökpulver', 'lokpulver',  # onion powder (spice, not fresh onion)
        'löksill', 'loksill',  # pickled herring (onion herring) — "lök" is NOT the ingredient
    },

    # Potato types - "potatis" should NOT match specific potato types
    # "Potatis Smattochgott" should NOT match "färskpotatis" recipe
    'potatis': {
        'färskpotatis', 'farskpotatis',  # new potatoes (seasonal)
        'sötpotatis', 'sotpotatis',  # sweet potato (different species)
        'klyftpotatis',  # wedge potatoes (frozen/pre-made)
        'bakpotatis',  # baking potatoes
        'mandelpotatis',  # specific variety, not generic potatis
        'potatismjöl', 'potatismjol',  # potato starch (sauce thickener, different product)
        'potatischips',  # potato chips (snack)
        'potatisgnocchi',  # potato gnocchi (prepared pasta)
        'potatisgratäng', 'potatisgratang',  # ready-made potato gratin
        'potatiskroketter',  # potato croquettes (frozen)
        'potatisbullar',  # potato balls (frozen)
        'potatismospulver',  # instant mashed potato powder
    },
    'potatisar': {
        'färskpotatis', 'farskpotatis',  # plural offer keyword needs same blocker coverage
    },

    # Vanilla - "vanilj" should NOT match vanilla compound ingredients
    # "Yoghurt Vanilj" should NOT match recipe needing "vaniljsocker"
    'vanilj': {
        'vaniljsocker',  # vanilla sugar
        'vaniljextrakt',  # vanilla extract
        'vaniljstång', 'vaniljstang',  # vanilla pod
        'vaniljpulver',  # vanilla powder
    },
    # "vanill" (no trailing j) — product spelling variant (e.g., "Barista Vanill Havredryck")
    # 'vanill' is substring of 'vanillinsocker' → FP. Context check alone doesn't help
    # because 'vanill' IS found inside 'vanillinsocker'.
    'vanill': {
        'vanillinsocker',  # vanillin sugar ≠ vanilla product
    },

    # Flakes/flingor - generic should NOT match specific compound types
    # "Corn Flakes" (keyword "flakes") should NOT match "chiliflakes"
    'flakes': {
        'chili',  # chiliflakes
        'kokos',  # coconut flakes (kokosflingor)
        'havre',  # oat flakes (havreflingor)
    },
    'flingor': {
        'chili',  # chiliflingor
        'kokos',  # kokosflingor
        'havre',  # havreflingor
        'corn',  # cornflakes
        'råg', 'rag',  # rågflingor (rye flakes for porridge ≠ breakfast cereal)
        'fitness',  # fitnessflingor (specific brand)
    },
    'gari': {
        'margarin', 'bordsmargarin',
    },

    # Parsley types - kruspersilja ≠ bladpersilja (different herbs)
    'persilja': {
        'bladpersilja',  # flat-leaf parsley ≠ curly parsley
    },

    # Mayo products - "majo" (tube/packet) != "majonnäs" (jar mayo)
    'majo': {
        'majonnäs', 'majonnas', 'majonäs', 'majonas',
    },

    # Sugar - "socker" != "sockerärta/sockerärtor" (sugar snap peas)
    # Also block sockerdricka (soda) — not a sugar product
    # Block specialty sugar types: plain socker/strösocker != florsocker, pärlsocker, etc.
    'socker': {
        'sockerärta', 'sockerärtor', 'sockerärt',
        'sockerarta', 'sockerartor', 'sockerart',
        'sockerdricka',
        'florsocker', 'pärlsocker', 'parlsocker',
        'muscovadosocker', 'muskovadosocker',
        'farinsocker', 'råsocker', 'rasocker',
        'rörsocker', 'rorsocker', 'rårörsocker', 'rarorsocker',
        'gelésocker', 'gelesocker',
        'vaniljsocker',
        'sockerkaka',  # sponge cake — plain sugar ≠ sockerkaka
        'sockerfri', 'sockerfritt',
    },

    # Bacon - "bacon" != "Dressing Bacon" (bacon-flavored dressing)
    # Also block kycklingbacon (chicken bacon ≠ pork bacon, different product)
    'bacon': {
        'dressing', 'dressingmix',
        'kycklingbacon',  # chicken bacon (different animal/product)
    },

    # Dill (herb) != quesadilla (Mexican food)
    'dill': {
        'quesadilla',  # "dill" is substring of "quesadilla"
        'krondill',  # crown dill (dill flowers) ≠ regular dill herb
        'dillfrön',  # dill seeds (plural) ≠ fresh dill herb
        'dillfrö',  # dill seeds (singular) ≠ fresh dill herb
    },
    'basilika': {
        'thaibasilika',  # Thai basil ≠ regular basil — different herb
    },
    'blomkål': {
        'blomkålsris', 'blomkalsris',  # cauliflower rice ≠ whole cauliflower
    },
    'koriander': {
        'korianderfrön',  # coriander seeds (plural) ≠ coriander herb/leaves
        'korianderfrö',  # coriander seeds (singular) ≠ coriander herb/leaves
    },

    # Majs (corn) != majsstärkelse (corn starch) or majsmjöl (corn flour)
    'majs': {
        'majsstärkelse', 'majsmjöl', 'majzena',
        'majsolja',  # corn oil ≠ corn kernels
        'majsena',  # cornstarch (variant spelling) ≠ corn kernels
        'majskolv', 'majskolvar',  # corn on the cob ≠ loose kernels
        'majskyckling', 'majskycklingfilé', 'majskycklingfile',  # corn-fed chicken ≠ corn
        'minimajs',  # baby corn (wok ingredient) ≠ corn kernels
        'majsvälling', 'majsvalling',  # corn porridge (baby food) ≠ corn kernels
        'majspasta',  # corn pasta ≠ corn kernels
    },

    # Crème fraiche - "fraiche" should NOT match plant-based alternatives
    'fraiche': {
        'havrefraiche',  # oat-based (plant-based alternative)
    },
    # Körsbär (cherry fruit) != körsbärstomater (cherry tomatoes — a vegetable)
    # Also != körsbärslöv/körsbärsblad (cherry leaves for pickling)
    'körsbär': {
        'körsbärstomat', 'korsbarstomat',
        'körsbärstomater', 'korsbarstomat',
        'körsbärskvisttomater', 'körsbärskvisttomat',  # vine cherry tomatoes
        'korsbarskvisttomat', 'körsbärskvist',  # prefix forms
        'körsbärslöv', 'körsbärslov', 'körsbärsblad',  # cherry leaves (pickling)
        'korsbarslov', 'korsbarsblad',  # normalized forms
    },

    # Pasta (noodles) != currypasta/misopasta (paste) or pastafärg (food coloring)
    # Also block specific pasta types that shouldn't match generic "pasta" from tortellini
    'pasta': {
        'currypasta',
        'pastavatten',  # pasta water — you don't buy pasta for pasta water
        'pastakoket',  # "från pastakoket" — instruction text, not an ingredient
        'misopasta',  # "vit misopasta" - miso paste, NOT pasta noodles
        'pastafärg',  # "svart pastafärg" - food coloring, NOT pasta noodles
        'tapastallrik',  # "Zeta Tapastallrik med Manchego" — tapas plate, contains 'pasta' substring
        'chipotlepasta',  # chipotle paste, NOT pasta noodles
        'chilipasta',  # chili paste, NOT pasta noodles
        'strozzapretti',  # specific pasta type - tortellini ≠ strozzapretti
        # All "-pasta" = "-paste" compound words (paste ≠ noodles)
        'kryddpasta',  # spice paste
        'tamarindpasta',  # tamarind paste
        'tandooripasta',  # tandoori paste
        'sesampasta',  # sesame paste (tahini)
        'tomatpasta',  # tomato paste
        'harissapasta',  # harissa paste
        'wasabipasta',  # wasabi paste
        'tahinipasta',  # tahini paste
        'bönpasta', 'bonpasta',  # bean paste (e.g., Korean doenjang)
        'pastasås', 'pastasas',  # pasta sauce ≠ dry pasta noodles
        'pastakrydda',  # pasta spice mix ≠ dry pasta noodles
        'vaniljpasta',  # vanilla paste ≠ pasta noodles
        'pistaschpasta',  # pistachio paste (baking) ≠ pasta noodles
        'långpasta', 'langpasta',  # "långpasta" is a specific group — generic "pasta" keyword
                                   # should NOT substring-match inside recipe text "långpasta"
        'pastamaskin',  # equipment word ("om du har pastamaskin"), not an ingredient
    },

    # Citron (lemon) != citrongräs (lemongrass) - different ingredients
    'citron': {
        'citrongräs', 'citrongras',
        'citronmeliss',  # lemon balm (herb) ≠ lemon fruit
        'citronverbena',  # lemon verbena (herb) ≠ lemon fruit
        'citronpeppar',  # lemon pepper (spice blend) ≠ lemon fruit
        'citronarom',  # lemon extract/flavoring ≠ lemon fruit
        'citrontimjan',  # lemon thyme (herb) ≠ lemon fruit
        'citronsorbet',  # lemon sorbet (dessert) ≠ lemon fruit
        'citronsyra',  # citric acid (powder) ≠ lemon fruit
    },

    # Heart (meat) != artichoke hearts (kronärtskockshjärtan)
    'hjärta': {
        'kronärtskock', 'kronartskock',
    },

    # Matlagning (cooking cream/yoghurt) != matlagningsvin (cooking wine)
    # "Matlagning Laktosfri 4%" should NOT match "1 dl matlagningsvin"
    'matlagning': {
        'matlagningsvin',  # cooking wine ≠ cooking cream/yogurt
        'matlagningsyoghurt',  # cooking yogurt ≠ cooking cream/wine
        'matlagningsgrädde', 'matlagningsgradde',  # cooking cream ≠ cooking wine/yogurt
    },
    'matlagnings': {
        'matlagningsvin',  # "Matlagnings Grädde" → keyword 'matlagnings' ≠ matlagningsvin
        'matlagningsyoghurt',
    },

    # Choklad (chocolate bar/baking) != chokladsås/chokladglass (prepared products)
    # "Mörk Choklad 70%" should NOT match recipe ingredient "chokladsås" or "chokladglass"
    'choklad': {
        'chokladsås', 'chokladsas',  # chocolate sauce ≠ chocolate bar
        'chokladglass',  # chocolate ice cream ≠ chocolate bar
        'chokladägg', 'chokladagg',  # Easter eggs ≠ plain baking/eating chocolate
        'blockchoklad',  # baking block chocolate ≠ chocolate snacks ("Tranbär Mörk Choklad 70%")
        'bakchoklad',  # baking chocolate ≠ eating/snack chocolate
        'chokladsmak',  # "dryck med chokladsmak" ≠ baking chocolate
        'mjölkchoklad', 'mjolkchoklad',  # milk chocolate — dark/white should not match
        'chokladströssel', 'chokladstrossel',  # chocolate sprinkles ≠ baking chocolate (5 recipes)
        'chokladkräm', 'chokladkram',  # chocolate cream/spread (Nutella-style) ≠ solid baking chocolate
        # NOTE: 'varm choklad' handled via KEYWORD_SUPPRESSED_BY_CONTEXT, not FPB
        # NOTE: mörk/vit/ljus darkness qualifiers in _SPECIALTY_QUALIFIERS_RAW, not here
    },
    # NOTE: bakchoklad/blockchoklad darkness qualifiers in _SPECIALTY_QUALIFIERS_RAW

    # Lax (salmon) != laxrom (salmon roe) — different product
    # "lax" is substring of "laxrom" → reverse-substring FP
    'lax': {
        'laxrom',  # salmon roe ≠ salmon fillet
    },

    # Musslor (mussels) != kammusslor (scallops) — different shellfish
    # "musslor" is substring of "kammusslor" → false positive (2 recipes)
    'musslor': {
        'kammusslor', 'kammussla',
        'pilgrimsmusslor', 'pilgrimsmussla',  # scallops ≠ mussels
    },

    # Feta (cheese) != "fetare" (comparative of "fet" = fatty)
    # "feta" is substring of "fetare" in "fiskfiléer av fetare sort" → cheese FP
    'feta': {
        'fetare', 'fetast',  # comparative/superlative of "fet"
    },

    # Vilt (game meat) != fond/stock products
    # "Vilt Kantarell Fond" should NOT match ingredient "viltfärs"
    'vilt': {
        'viltfond', 'viltfärs', 'viltfars',  # vilt in compound → compound-strict handles it
    },

    # Mango (tropical fruit) != mangold (chard, leafy green)
    # "mango" is substring of "mangold" → false positive
    'mango': {
        'mangold',
        'mangochutney',  # mango chutney (condiment) ≠ fresh mango
        'mangorajasås', 'mangorajasas',  # mango raita sauce ≠ fresh mango
        'mangosalsa',  # mango salsa (prepared) ≠ fresh mango
    },

    # Butter - "smör" != nut/seed butters (completely different products)
    'smör': {
        'messmör', 'messmor',  # whey butter (different product)
        'nötsmör', 'notsm\u00f6r',  # nut butter
        'mandelsmör', 'mandelsm\u00f6r',  # almond butter
        'jordnötssmör', 'jordnotssmor',  # peanut butter
        'sesamsmör', 'sesamsm\u00f6r',  # sesame butter (tahini)
        'kakaosmör', 'kakaosm\u00f6r',  # cocoa butter
        'kokossmör', 'kokossm\u00f6r',  # coconut butter
        'smörgås', 'smorgas',  # sandwich compound words (smörgåsgurka, smörgåskaviar, smörgåskrasse)
        'smördeg', 'smordeg',  # puff pastry (butter ≠ pastry dough)
        'smördegsplatta', 'smordegsplatta',  # puff pastry sheets
        'smördegsplattor', 'smordegsplattor',
        'smörja', 'smorja',  # "smörja formen" — instruction verb, not a reason to buy butter
        'smörjning', 'smorjning',  # "för smörjning av plåt" — greasing instruction, not butter
        'aromsmör', 'aromsmor',  # flavored compound butter ≠ plain butter
    },

    # Egg - "ägg" appears inside many Swedish compound words that aren't about eggs
    'ägg': {
        'inläggning', 'inlaggning',  # "inläggningssill" = pickled herring
        'blötlägg', 'blotlagg',  # "blötlägga" = to soak
        'lägg', 'lagg',  # "lägg" standalone = leg/shank (e.g., "lamm, lägg")
        'lammlägg', 'lammlögg',  # "lammlägg" = leg of lamb
        'nötlägg', 'notlagg',  # "nötlägg" = beef shank (osso buco)
        'kalvlägg', 'kalvlagg',  # "kalvlägg" = veal shank
        'läggkött', 'laggkott',  # "läggkött" = shank meat
        'påskägg', 'paskagg',  # Easter egg decorations
        'häggblom', 'haggblom',  # "häggblomssaft" = bird cherry blossom cordial
        'uppläggning', 'upplaggning',  # "uppläggningsfat" = serving platter
        'pålägg', 'palagg',  # "pålägg" = cold cuts/toppings
        'äggnudlar',  # egg noodles — different product from eggs
        'äggpasta',   # egg pasta — different product from eggs
        'kinderägg', 'kinderagg',  # Kinder Surprise (chocolate candy, not eggs)
    },

    # Apple - "äpple" != "granatäpple" (pomegranate is a completely different fruit)
    # Also block äpplemos (applesauce) - processed product, not fresh apples
    'äpple': {
        'granatäpple', 'granatapple',
        'äpplemos', 'applemos',  # applesauce ≠ fresh apples
        'cashewäpple', 'cashew',  # cashew apple (cashew fruit) ≠ regular apple
        'äpplejuice', 'applejuice',  # apple juice ≠ fresh apples
    },

    # Beans - "bönor" should NOT match very different bean species
    # "Små Vita Bönor" should NOT match recipe wanting "sojabönor" or "edamamebönor"
    'bönor': {
        'bondbön',  # fava/broad beans (completely different)
        'mungbön',  # mung beans
        'sojabön',  # soybeans
        'edamame',  # edamame beans
        'vaxbön',  # wax beans
        'kaffebön',  # coffee beans (not food beans!)
        'limabön',  # lima beans
        'gelébönor', 'gelebonor',  # candy jelly beans (not legumes!)
    },

    # Kakor (cookies/biscuits) - "kakor" should NOT match "pannkakor" (pancakes)
    'kakor': {
        'pannkakor', 'pannkaka', 'pannkaks',  # pancakes are NOT cookies
        'småkakor',  # "småkakor" in recipes = recipe FOR cookies, not ingredient
    },

    # Kaka - "kaka" (cookie/cake product keyword) should NOT match recipe keyword "kakao"
    # Product "Kaka Chokladsnitt 300g" has keyword 'kaka' → substring of 'kakao' → FP
    # Affects 318 recipes asking for cocoa powder getting cookie products
    'kaka': {
        'kakao',  # cocoa powder ≠ cookies
        'chokladkaka',  # chocolate bar ≠ cookies (compound split: chokladkaka → choklad + kaka)
        'skaka',  # "skaka" (to shake) contains "kaka" as substring → FP
    },

    # Kakao - cocoa powder should NOT match "kakaonibs" (cacao nibs are a different product)
    'kakao': {
        'kakaonibs',  # cacao nibs ≠ cocoa powder
        'kakaosmör', 'kakaosmor',  # cocoa butter ≠ cocoa powder
        'likör', 'likor',  # "kakaolikör" wants liqueur, not cocoa powder
    },

    # Melon - "melon" should NOT match "vattenmelon" (watermelon ≠ cantaloupe)
    'melon': {
        'vattenmelon',  # watermelon is a completely different fruit
        'melonkärnor', 'melonkarnor',  # melon seeds (snack/topping) ≠ whole melon
    },

    # Halloumi - "halloumi" should NOT match "halloumiburgare" (specific product made FROM halloumi)
    # "Halloumi Skivad" should NOT match recipe ingredient "480g Halloumiburgare"
    'halloumi': {
        'halloumiburgare',  # halloumi burger (different product)
    },

    # Tofu - plain tofu should not match silken tofu wording in ingredient text
    'tofu': {
        'silkestofu',
        'silkesmjuk',
    },

    # Burger - "burgare" should NOT match specific homemade burger types
    # "Burgare Plantbaserad" should NOT match recipe for "svampburgare" (made from scratch)
    'burgare': {
        'svampburgare',  # mushroom burger (made from mushrooms)
        'halloumiburgare',  # halloumi burger (made from halloumi)
        'havreburgare',  # oat burger (made from oats)
        'bönburgare', 'bonburgare',  # bean burger
        'laxburgare',  # salmon burger
        'vegoburgare', 'veggoburgare',  # veggie burger (from scratch)
    },

    # Rice - "ris" is substring of many unrelated Swedish words
    # "Svart Ris" should NOT match "1 msk kapris" or "900 g Sparrispotatis"
    'ris': {
        'kapris',  # capers - completely unrelated to rice
        'sparris',  # asparagus - completely unrelated to rice
        'tamari',  # tamari soy sauce ("tamarisoja") - unrelated
        'risgryn',  # rice porridge (risgrynsgröt) - processed, not raw rice
        'risvinäger', 'risvinager',  # rice vinegar - condiment, not rice
        'risvin',  # rice wine - condiment, not rice
        'riserva',  # Italian wine/vinegar term (e.g., "Vitvinsvinäger Riserva")
        'risnudlar', 'risnudel',  # rice noodles (different product)
        'risoni',  # risoni pasta (rice-shaped pasta, not rice)
        'rismjöl', 'rismjol',  # rice flour (processed, not raw rice)
        'rispapper', 'rispappersblad',  # rice paper (wrapper, not rice)
        'rispuffar',  # puffed rice (snack/cereal, not raw rice)
        'risgröt', 'risgrot',  # rice porridge (ready-made, different product)
        'rapsgris',  # pig breed — "ris" substring of "rapsgris"
        'risförpackningen', 'risforpackningen',  # instruction text: "läs på risförpackningen"
        'riskoket',  # instruction text: "riskoket" (rice cooker reference)
        'risken',  # unrelated word: "risken" (the risk)
        'fullkornsris',  # whole grain rice — specific type (IMPLICIT_KEYWORDS adds fullkornsris to product)
        'blomkålsris', 'blomkalsris',  # cauliflower rice ≠ rice
        'havreris',  # oat grains (mathavre) ≠ rice
        'risberg',  # brand name (Risberg Import) — "ris" substring ≠ rice
        'algsallad',  # algae salad ≠ rice
    },

    # Iceberg lettuce — "isberg" is substring of "risberg" (brand name)
    'isberg': {
        'risberg',  # brand name (Risberg Import) — not iceberg lettuce
    },

    # Vinegar - "ättika" is substring of "rättika" (radish)
    'ättika': {
        'rättika', 'rattika',  # radish ≠ vinegar
    },

    # Nuts - generic "nötter" (mixed nuts) should NOT match specific nut types
    # "Nötter Honung Trippel" should NOT match recipe wanting "cashewnötter"
    'nötter': {
        # Tree nuts
        'cashewnötter', 'cashewnot',  # cashew nuts
        'valnötter', 'valnot',  # walnuts
        'hasselnötter', 'hasselnot',  # hazelnuts
        'pekannötter', 'pekannot',  # pecans
        'pecannötter', 'pecannot',  # pecans (variant spelling)
        'pistagenötter', 'pistagenot',  # pistachios
        'pinjenötter', 'pinjenot',  # pine nuts
        'macadamianötter', 'macadamianot',  # macadamia nuts
        'paranötter', 'paranot',  # Brazil nuts
        'mandelnötter',  # almond nuts (less common compound)
        # Peanuts (technically legumes but sold as nuts)
        'jordnötter', 'jordnot',  # peanuts
        # Coconut (very different product)
        'kokosnötter', 'kokosnot',  # coconuts
    },

    # Asparagus - "sparris" != "sparrisbroccoli" (broccolini/bellaverde - different vegetable)
    'sparris': {
        'sparrisbroccoli',  # broccolini (bellaverde) ≠ asparagus
        'sparrispotatis',  # fingerling potatoes ≠ asparagus
        # NOTE: "Pasta Mezze Lune Sparris" moved to PNB (product name blocker) — FPB checks ingredient text, not product name
    },

    # Kebab meat != kebab sauce/spice
    # "Pirog Chicken Kebab" should NOT match recipes needing kebab sauce or kebab spice
    'kebab': {
        'kebabsås', 'kebabsas',  # kebab sauce ≠ kebab meat
        'kebabkrydda',  # kebab spice ≠ kebab meat
    },

    # Ground meat - "färs" should NOT match "färsk" (fresh), "färska", "färskt"
    # "Asiatisk Färs" should NOT match "0.5 st rosmarin - färsk"
    'färs': {
        'färsk', 'färska', 'färskt',  # "fresh" adjective in Swedish
        'färskost',  # cream cheese (contains 'färs' as substring)
        # NOTE: 'formbar' REMOVED — handled by SPECIALTY_QUALIFIERS instead.
        # FPB blocked "Formbar färs vegansk" from matching keyword "färs",
        # preventing correct matches for Javligtgott "Formbar färs" ingredients.
        'quorn',  # "Färs Mince Quorn Fryst" - vegetarian mince, not nötfärs
        'asiatisk',  # "Asiatisk Färs" - different type of mince
        'ingefär',  # "ingefärsmarmelad" contains 'färs' as substring — not ground meat
        'farfärs',  # brand name "Stensåkra Farfars" — not ground meat
    },

    # Berries - fresh berries should NOT match jam/sylt recipes
    'blåbär': {
        'blåbärssylt', 'blabarssylt',
        'boost',        # "Berry Boost Blåbär" — snack bar, not blueberries
    },
    'hallon': {
        'hallonsylt',
        'hallonsaft',      # raspberry juice/concentrate ≠ fresh raspberries
        'hallonsmak',      # raspberry-flavored product ≠ fresh raspberries
        'hallongrotta', 'hallongrottor',  # cookie compound, not fresh/frozen raspberries
        'balsamicohallon',  # "Balsamico Hallon" is a flavored balsamic product, not fresh hallon
        'torkad frukt',    # "Torkad Frukt Bara Jordgubb hallon" — dried fruit mix, not fresh
    },
    'lingon': {
        'lingonsylt',
        'lingon 35',  # budget lingonsylt without "sylt" in name ("Lingon 35%")
    },
    'jordgubb': {
        'jordgubbssylt',
        'torkad frukt',    # "Torkad Frukt Bara Jordgubb hallon" — dried fruit mix, not fresh
    },
    'rabarber': {
        'rabarbersaft',  # rhubarb cordial/concentrate ≠ fresh rhubarb stalks
    },
    'hjortron': {
        'hjortronsylt',    # "Hjortron Eko 225g" (fresh/frozen berries) ≠ hjortronsylt (jam)
    },
    'björnbär': {
        'björnbärssylt', 'bjornbarssylt',
    },
    'bjornbar': {
        'björnbärssylt', 'bjornbarssylt',
    },
    'matcha': {
        'havredryck',  # "Matcha Havredryck" = oat drink with matcha flavor, not matcha powder
        'latte',       # "Classic Matcha Latte" = ready drink, not matcha powder
    },
    # Flavored sparkling water should not match recipes wanting plain kolsyrat vatten
    'kolsyrat': {
        'jordgubb', 'hallon', 'granatäpple', 'granatapple',
        'mango', 'päron', 'paron', 'skogsbär', 'skogsbar',
        'kaktus', 'björnbä', 'bjornba', 'rabarber',
        'körsbär', 'korsbar', 'crush',
    },

    # Peas - "ärtor" should NOT match completely different legumes/pea types
    # "Gröna Ärtor" should NOT match recipe needing "kikärtor" (chickpeas)
    'ärtor': {
        'kikärtor', 'kikartor', 'kikärt', 'kikart',  # chickpeas (completely different legume)
        'sockerärtor', 'sockerartor', 'sockerärta', 'sockerarta',  # sugar snap peas (eaten whole, pod and all)
        'salladsärtor', 'salladsartor',  # salad peas (fresh, eaten raw)
        'spritärtor', 'spritartor',  # specific pea variety
        'gulaärtor', 'gulartor',  # yellow peas — specific type, "Gröna Ärtor" ≠ "gulärt"
    },

    # Cream - "grädde" should NOT match plant-based alternatives
    'grädde': {
        'kokosgrädde', 'kokosgradule',  # coconut cream (plant-based)
        'sojagrädde', 'sojagradule',  # soy cream (plant-based)
        'havregrädde', 'havregradule',  # oat cream (plant-based)
    },

    # Anis - "anis" should NOT match "manis" (ketjap manis ≠ anise spice)
    'anis': {
        'manis',  # ketjap manis — Indonesian sweet soy sauce
    },

    # Anka - "anka" should NOT match "grillplanka" (plank ≠ duck) or "utbankade" (pounded)
    'anka': {
        'grillplanka',  # grilling plank — substring false positive
        'utbankade', 'utbankat', 'utbankad',  # pounded/flattened meat ("utbankade filéer")
    },

    # Buljong - generic broth should NOT match specific animal broths
    'buljong': {
        'oxbuljong',  # beef broth
        'kycklingbuljong',  # chicken broth
        'grönsaksbuljong', 'gronsaksbuljong',  # vegetable broth
        'fiskbuljong',  # fish broth
        'hönsbuljong', 'honsbuljong',  # hen broth
        'svampbuljong',  # mushroom broth
        'kalvbuljong',  # veal broth
    },

    # Chips - generic "chips" should NOT match taco chips (different product category)
    'chips': {
        'tacochips',  # taco-flavored tortilla chips ≠ generic chips
        'nachochips',  # nacho chips ≠ generic chips
        'bananachips', 'bananchips',  # dried banana slices ≠ chips
    },

    # Sirap - generic syrup should NOT match flavored/specialty syrups
    'sirap': {
        'granatäpplesirap', 'granatäppelsirap', 'granatappelsirap',  # pomegranate syrup ≠ plain syrup
        'lönnsirap', 'lonnsirap',  # maple syrup ≠ plain syrup
        'agavesirap',  # agave syrup ≠ plain syrup
        'balsamico', 'balsamicosirap',  # balsamic cream ≠ cooking syrup
    },

    # Kaviar - generic "kaviar" should NOT match specific types
    'kaviar': {
        # storkornskaviar removed — now mapped to stenbitsrom via INGREDIENT_PARENTS
        'tangkaviar',       # seaweed caviar ≠ tube kaviar (Kalles etc.)
    },
    'caviar': {
        'tångcaviar', 'tangcaviar',  # "Caviar Röd Stenbitsrom" should NOT match tångcaviar
    },

    # Aluminium — kitchen supply keyword leaking into food matching
    'aluminium': {
        'aluminiumfolie',  # "1 st Aluminiumfolie" (kitchen tool) ≠ food product
    },

    # Högrev (whole cut) ≠ högrevsfärs (ground). Nobody grinds whole chuck at home.
    'högrev': {
        'högrevsfärs', 'hogrevsfars',
        'hamburgare', 'burger', 'burgare',  # burger patties ≠ raw chuck cut
    },
    'hogrev': {
        'högrevsfärs', 'hogrevsfars',
        'hamburgare', 'burger', 'burgare',
    },

    # Risotto - ready-made risotto meal ≠ raw risotto rice
    'risotto': {
        'risottoris',  # "Risotto Svamp Vitlök" is a meal, not plain rice
        'risotton',    # "till risotton" — directional phrase, not ingredient
    },

    # Yoghurt - generic yoghurt should NOT match flavored/compound yoghurts
    'yoghurt': {
        'avokadoyoghurt',  # avocado yoghurt — specific mix
        'myntayoghurt',  # mint yoghurt — specific mix
        'vaniljyoghurt',  # vanilla yoghurt — plain yoghurt ≠ vaniljyoghurt
    },

    # Fond - generic "fond" should NOT match specific animal fonds
    'fond': {
        'oxfond',  # beef stock ≠ generic stock
        'köttfond', 'kottfond',  # meat stock
        'kycklingfond',  # chicken stock
        'fiskfond',  # fish stock
        'viltfond',  # game stock
        'grönsaksfond', 'gronsaksfond',  # vegetable stock
        'svampfond',  # mushroom stock
        'kantarellfond',  # chanterelle stock
        'kalvfond',  # veal stock
        'hummerfond',  # lobster stock
        'skaldjursfond',  # shellfish stock
    },

    # Flundra - regular flatfish should NOT match halibut (hälleflundra) or Baltic herring preparation
    'flundra': {
        'hälleflundra', 'halleflundra',  # halibut — different fish species
        'strömmingsflundra', 'strommingsflundra',  # Baltic herring preparation, NOT flounder
    },

    # Mjöl/vetemjöl - should NOT match specialty flours
    'vetemjöl': {
        'bovetemjöl', 'bovetemjol',  # buckwheat flour ≠ wheat flour
        'rågsikt',  # "Rågsikt med vetemjöl" = rye/wheat blend ≠ pure wheat flour
    },
    # Groddar - generic sprouts should NOT match specific types
    'groddar': {
        'böngroddar', 'bongroddar',  # bean sprouts — specific type
        'mungbönsgroddar', 'mungbonsgroddar',  # mung bean sprouts — specific type
        'vetegroddar',  # wheat germ — completely different product (dry pantry item ≠ fresh sprouts)
    },

    # Saltin crackers — "saltin" found as substring in "saltinlagd" (preserved)
    'saltin': {
        'saltinlagd',  # "saltinlagd citron" = preserved lemon, NOT Saltin crackers
    },

    # Senap - generic mustard should NOT match dijon (different flavor profile)
    'senap': {
        'dijonsenap',  # Dijon mustard — distinct type, not interchangeable
    },

    # Majonnäs/mayo - generic mayo should NOT match flavored variants
    'majonnäs': {
        'chilimajonnäs', 'chilimajonnas',  # chili mayo ≠ plain mayo
        'srirachamajonnäs', 'srirachamajonnas',  # spicy sriracha mayo ≠ plain mayo
    },
    'mayo': {
        'chilimayo',  # chili mayo ≠ plain mayo
        'srirachamayo',  # spicy sriracha mayo ≠ plain mayo
    },

    # Ströbröd - generic breadcrumbs should NOT match panko
    'ströbröd': {
        'pankoströbröd', 'pankostrobrod',  # panko — Japanese style, different texture
    },

    # Ham - "skinka" should NOT match cured specialty hams
    # "Kokt Skinka" should NOT match recipe needing "parmaskinka"
    'skinka': {
        'parmaskinka',  # Parma ham (Italian cured, very different from cooked ham)
        'serranoskinka',  # Serrano ham (Spanish cured)
        'bayonneskinka',  # Bayonne ham (French cured)
        'prosciutto',  # Italian cured ham
    },

    # Pork cuts - "fläsk" should NOT cross-match different cuts.
    # Keep all fläsk blockers in a single entry to avoid duplicate-key drift.

    # Chop - "kotlett" should NOT match lamb chops (different animal)
    # "Fläskkotlett" should NOT match recipe needing "lammkotlett"
    'kotlett': {
        'lammkotlett', 'lammkotletter',  # lamb chop (different animal)
        'kalvkotlett', 'kalvkotletter',  # veal chop (different animal)
        'laxkotlett', 'laxkotletter',  # salmon steak (different species entirely)
    },

    # Rom (fish roe / rum) - "rom" substring in "romansallad" (romaine lettuce)
    'rom': {
        'arom',  # citronarom / arraksarom / romarom are extracts, not fish roe or rum
        'tångrom', 'tangrom',  # seaweed caviar ≠ fish roe
        'romansallad',  # romaine lettuce — "rom" is substring, not fish roe/rum
        'roman',  # short form of romansallad
    },

    # Roast beef - "rostbiff" should NOT match lamb roast
    'rostbiff': {
        'lammrostbiff',  # lamb roast (different animal)
    },
    'ostbiff': {
        'rostbiff', 'lammrostbiff',  # "ostbiff" is substring of "rostbiff"/"lammrostbiff" — cheese patty ≠ roast beef
    },

    # Nöt (beef) should NOT match nut-type ingredients — 'nöt' is substring of all *nöt compounds
    # SPACE_NORM expands "nöt- och fröbitar" → "nötbitar och fröbitar", then FPB blocks
    'nöt': {
        'nötbitar', 'nötter',  # nut pieces / nuts — beef keyword should not match
        # Specific nut types where 'nöt' (beef) is a false substring match
        'hasselnöt', 'hasselnötter', 'hasselnot', 'hasselnotter',
        'jordnöt', 'jordnötter', 'jordnot', 'jordnotter',
        'valnöt', 'valnötter', 'valnot', 'valnotter',
        'cashewnöt', 'cashewnötter', 'cashewnot', 'cashewnotter',
        'pistagenöt', 'pistagenötter', 'pistagenot', 'pistagenotter',
        'pekannöt', 'pekannötter', 'pekannot', 'pekannotter',
        'kokosnöt', 'kokosnötter', 'kokosnot', 'kokosnotter',
        'macadamianöt', 'macadamianötter',
        'paranöt', 'paranötter',
        'muskotnöt', 'muskotnot',  # nutmeg — spice, not beef
        'nötsmör', 'notsmor',  # nut butter — nut product, not beef
    },
    'not': {
        'nötbitar', 'nötter',
        'hasselnöt', 'hasselnötter', 'hasselnot', 'hasselnotter',
        'jordnöt', 'jordnötter', 'jordnot', 'jordnotter',
        'valnöt', 'valnötter', 'valnot', 'valnotter',
        'cashewnöt', 'cashewnötter', 'cashewnot', 'cashewnotter',
        'pistagenöt', 'pistagenötter', 'pistagenot', 'pistagenotter',
        'pekannöt', 'pekannötter', 'pekannot', 'pekannotter',
        'kokosnöt', 'kokosnötter', 'kokosnot', 'kokosnotter',
        'macadamianöt', 'macadamianötter',
        'paranöt', 'paranötter',
        'muskotnöt', 'muskotnot',  # nutmeg
        'nötsmör', 'notsmor',  # nut butter
    },

    # Hushålls- products should NOT match 'hushållsfärg' (food coloring) in recipes
    # Product keyword 'hushålls'/'hushåll' is substring of recipe text 'hushållsfärg' → false match
    'hushålls': {
        'hushållsfärg', 'hushallsfarg',
        'hushållsost',  # cheese ≠ sausage (hushålls medwurst)
    },
    'hushåll': {
        'hushållsfärg', 'hushallsfarg',
    },
    'hushalls': {
        'hushållsfärg', 'hushallsfarg',
    },
    'hushall': {
        'hushållsfärg', 'hushallsfarg',
    },

    # Fläsk (pork generic) should NOT match specific fläsk compounds in recipes
    # Product "Fläskfilé" has keyword 'fläsk' (via KEYWORD_EXTRA_PARENTS) which is substring
    # of 'fläskkorv' in recipe text — but fläskfilé ≠ fläskkorv
    # NOTE: fix_swedish_chars('flask')='fläsk' — both compile to same key, so use ONE entry
    # with ALL Swedish and ASCII blocker variants (was split into 2 entries = key collision!)
    'fläsk': {
        'fläskkorv', 'flaskkorv',
        'fläskfilé', 'flaskfile', 'flaskfilé',
        'fläskytterfilé', 'flaskytterfile', 'flaskytterfilé',
        'fläskkarré', 'flaskkarre',
        'fläskfärs', 'flaskfars',  # ground pork ≠ whole cuts
        'fläskkotlett', 'flaskkotlett',
        'sidfläsk', 'sidflask',
        'stekfläsk', 'stekflask',  # side pork for frying ≠ fläskfilé/karré
        'fläsksmak', 'flasksmak',  # pork-flavored ≠ actual pork
        'fläsksida', 'flasksida',  # pork belly ≠ fläskfilé/karré
    },

    # Mandel (almond) should NOT match when ingredient is a baked good with almond flavor
    # "Cantuccini Mandel" = almond-flavored cookies, NOT raw almonds
    # "bittermandelarom"/"mandelarom" = almond extract, NOT whole almonds
    'mandel': {'cantuccini', 'mandelarom'},
    'mandlar': {'cantuccini', 'mandelarom'},

    # Ananas (pineapple fruit) should NOT match ananasjuice (different product)
    'ananas': {'ananasjuice'},

    # Plommon (plum) should NOT match plommontomat (plum tomato) or plommonvin (plum wine)
    # "plommontomater" is a tomato variety, not plums — recipe wants tomatoes
    'plommon': {'plommontomat', 'plommonvin'},

    # Vinäger should NOT match pickled/prepared items — recipe wants the prepared food, not plain vinegar
    'vinäger': {'vinägerinlagd', 'vinägerpicklad', 'vinägerpicklade', 'vinägerpicklat'},
    'vinager': {'vinagerinlagd', 'vinagerpicklad', 'vinagerpicklade', 'vinagerpicklat'},

    # Svartvinbärs (blackcurrant) should NOT match svartvinbärsblad (pickling leaves)
    'svartvinbärs': {'svartvinbärsblad'},

    # Vinbär (currant berry) should NOT match vinbärsblad/svartvinbärsblad (pickling leaves)
    'vinbär': {'vinbärsblad', 'svartvinbärsblad', 'vinbarsblad', 'svartvinbarsblad'},

    # Curry powder should NOT match when ingredient is a distinct curry family:
    # curry leaves, sauces, or colored Thai curry bases/pastes.
    'curry': {
        'curryblad',
        'currysås', 'currysas',
        'röd curry', 'rod curry', 'red curry', 'rödcurry', 'rodcurry',
        'grön curry', 'gron curry', 'green curry', 'gröncurry', 'groncurry',
        'gul curry', 'yellow curry', 'gulcurry',
    },
    'vinbar': {'vinbarsblad', 'svartvinbarsblad', 'vinbärsblad', 'svartvinbärsblad'},

    # Holland (country/origin) should NOT match Hollandaisesås
    'holland': {'hollandaisesås', 'hollandaisesas'},

    # Äppeljuice should NOT match granatäppeljuice (pomegranate ≠ apple)
    'äppeljuice': {'granatäppeljuice', 'granatappeljuice'},

    # Pudding - blodpudding ≠ generic pudding (protein pudding, vaniljpudding etc)
    'pudding': {'blodpudding'},

    # Lasagne (ready meal) ≠ lasagneplattor (pasta sheets)
    'lasagne': {'lasagneplattor'},

    # Cantal (French cheese) ≠ cantaloupemelon (fruit)
    'cantal': {'cantaloupe', 'cantaloupemelon'},

    # "Kyckling Hel Fryst" is for stock, soup, or roasting whole - not for cutting into parts
    'kyckling': {
        # Marzipan figurines: "marsipankycklingar" contains 'kyckling' but isn't chicken
        'marsipan',  # "marsipankycklingar" (Easter marzipan chicks) ≠ real chicken
        # Processed products
        'kycklingpulver',  # chicken powder (spice)
        'kycklingbuljong',  # chicken broth (liquid/cube)
        'kycklingbacon',  # processed chicken bacon
        'kycklingkorv',  # chicken sausage
        'kycklingstekkorv',  # chicken grilling sausage
        'kycklingfond',  # chicken stock
        'kycklingfärs', 'kycklingfars',  # ground chicken
        # NOTE: kycklingfilé/bröst/lår are NOT blockers — they're generic chicken cuts
        'kycklingklubba',  # chicken drumstick
        'kycklingben',  # chicken leg (bone-in) ≠ generic chicken
        'kycklinghalva', 'kycklinghalvor',  # half chicken is a distinct cut/prep
        'kycklingvinge', 'kycklingvingar',  # chicken wing(s)
        # Specific breed
        'majskyckling',  # corn-fed chicken (not generic)
        'marsipankyckling', 'marsipankycklingar',  # marzipan decoration ≠ chicken
        'helkyckling',  # whole chicken ≠ generic chicken (different product/use)
        'helkalkon',  # whole turkey ≠ generic chicken
        'kycklinghjärta',  # chicken heart — specific offal
        'kycklingmage',  # chicken gizzard — specific offal
        'färdigkyckling',  # pre-cooked chicken (grillad, stekt, salladskyckling)
        'kycklingskrov',  # chicken carcass (for stock)
        'kycklinggrillkorv',  # grilled chicken sausage
        'kycklingklubbor',  # chicken drumsticks plural
        'kycklingkebab',  # chicken kebab
        'kycklingköttbullar',  # chicken meatballs
        'kycklinglever',  # chicken liver
        'kycklingpastej',  # chicken pâté
        'kycklingschnitzel',  # chicken schnitzel
        'kycklingspett',  # chicken skewer
        'kycklingsteak', 'kycklingsteaks',  # chicken steak(s)
        'kycklingwrap',  # chicken wrap (ready meal)
        'kycklingsmak',  # chicken-flavored (e.g. instant noodles) ≠ actual chicken
    },
    'kycklingar': {
        'marsipan',  # "marsipankycklingar" — matched_keyword can be plural form
    },

    # Banana fruit != banana shallot (completely different)
    'banan': {
        'matbanan',  # plantain ≠ dessert banana
        'bananschalottenlök', 'bananschalottenlock',  # banana shallot (onion type)
        'bananscharlottenlök', 'bananscharlottenlock',  # alternate spelling (charlotte vs chalotte)
        'bananchips', 'bananachips',  # dried banana chips ≠ fresh banana
    },

    # Lime fruit != kaffir lime leaves (different ingredient)
    'lime': {
        'limeblad',  # kaffir lime leaves (Thai cooking) ≠ lime fruit
        'jordgubblime',  # strawberry-lime flavor ≠ lime fruit
    },

    # Lager (beer) != lagerblad (bay leaf)
    # "Special Effect 0,4% Lager, Burk" should NOT match "3 st lagerblad"
    'lager': {
        'lagerblad',  # bay leaf — "lager" is substring
    },

    # Herring != fusilli pasta / persillade / matjessill
    'sill': {
        'fusilli',      # Italian pasta shape — "sill" is embedded in "fusilli"
        'persillade',   # French herb crust — "sill" is embedded in "persillade"
        'matjessill', 'matjessillfiléer', 'matjessillfileer',  # matjessill is a specific type
        'saltsillfileer',  # generic sill should not match urvattnade saltsillfiléer
        'physillium', 'psillium', 'psyllium',  # fiber husk supplement — "sill" substring in "physillium"
    },


    # Fermented milk (fil) != filé/filet/phyllo dough
    'fil': {
        'filoncini',    # Italian bread rolls — "fil" is embedded in "filoncini"
        'filodeg',      # phyllo dough — "fil" is embedded in "filodeg"
        'filé', 'file', 'filéer', 'fileer', 'filet', 'fileter',  # fillet (meat/fish)
        'filéad', 'filead', 'filéade', 'fileade',  # "clementiner, filéade" — prep instruction, not dairy fil
        'kycklingfilé', 'kycklingfile', 'kycklingfiléer',  # chicken fillet
        'kycklinginnerfilé', 'kycklinginnerfile', 'kycklinginnerfiléer',  # chicken inner fillet
        'kycklinglårfilé', 'kycklinglårfile', 'kycklinglårfiléer',  # chicken thigh fillet
        'laxfilé', 'laxfile', 'fiskfilé', 'fiskfile',  # fish fillet
        'fläskfilé', 'fläskfile',  # pork fillet
        'innerfilé', 'innerfile',  # inner fillet
        'matjesfilé', 'matjesfile', 'matjesfiléer',  # matjes fillet
        'torskfilé', 'torskfile', 'torskfilér', 'torskfiler', 'torskfiléer',  # cod fillet
        'rödspättafile',  # plaice fillet
        # Gräddfil ≠ fil — completely different dairy products
        'gräddfil', 'graddfil',  # "3 dl Gräddfil" should NOT match "Fil Original"
        # Nationality adjective — "filippinsk soja" ≠ fil (dairy)
        'filippinsk', 'filippinska',
    },

    # Delikatess (cucumber) != delikatess potatoes
    'delikatess': {
        'delikatesspotatis',  # delikatess potatoes ≠ delikatess cucumber
    },

    # Caramel (candy) != karamelliserad (cooking method)
    'karamel': {
        'karamelliserad', 'karamelliserade', 'karamelliserat',
        'karamellfärg', 'karamellfarg',  # food coloring ≠ caramel candy
    },

    # Coconut flour != coconut milk
    'kokosmjöl': {
        'kokosmjölk',  # coconut milk ≠ coconut flour
    },

    # Steak (biff) != beefsteak tomato (bifftomat), != lamb roast
    'biff': {
        'bifftomat', 'bifftomater',  # beefsteak tomato — "biff" is prefix but different food
        'lammrostbiff',  # lamb roast ≠ beef
        'biffsmak',  # beef-flavored (e.g. instant noodles) ≠ actual beef
    },

    # Flavor descriptions: Xsmak = X-flavored (e.g. instant noodles, chips)
    # These should NOT match the actual food product
    'fisk': {'fisksmak'},
    'räkor': {'räksmak'},
    'räk': {'räksmak'},
    'grönsak': {'grönsaksmak'},
    'grönsaker': {'grönsaksmak'},

    # Grape != grapefruit (grapefrukt)
    'grape': {
        'grapefrukt', 'grapefrukter',  # grapefruit — not grapes
    },

    # Cider (drink) != cider vinegar
    'cider': {
        'äppelcidervinäger', 'appelcidervinager', 'cidervinäger', 'cidervinager',
    },
    'äppelcider': {
        'äppelcidervinäger', 'appelcidervinager', 'cidervinäger', 'cidervinager',
    },

    # Meat != orange-fleshed description
    'kött': {
        'orangeköttig', 'orangekottigt',  # "orangeköttig cantaloupemelon" = flesh description, not meat
        'köttbullar', 'kottbullar',  # köttbullar is a distinct product, not generic "kött"
        'köttfärs', 'kottfars',  # köttfärs is a distinct product
        'köttfond', 'kottfond',  # köttfond is a distinct product (stock, not meat)
        'köttbuljong', 'kottbuljong',  # köttbuljong = stock cube, not meat
    },

    # Fresh paprika != paprikapulver (spice)
    'paprika': {
        'paprikapulver',  # paprika spice is a different product from fresh bell pepper
        'paprikakrydda',  # "3 tsk Paprikakrydda" = dried spice, not fresh bell pepper
        'spetspaprika',  # pointed pepper — "Paprika Burk" should NOT match spetspaprika recipes
        'paprikakräm',  # paprika paste/cream ≠ fresh bell pepper
    },

    # Thickener (redning) != preparation text (beredning)
    'redning': {
        'beredning', 'beredningstexten', 'beredningstips',  # preparation instructions, not thickener
    },

    # Jam (sylt) != jam-making sugar (syltsocker)
    'sylt': {
        'syltsocker',  # jam sugar — different product from jam itself
        'syltlök', 'syltlok',  # pickled onion ≠ jam
    },

    # Vegeta (spice brand) != vegetabilisk/vegetarisk
    'vegeta': {
        'vegetabilisk', 'vegetabiliska', 'vegetarisk', 'vegetariska',
    },

    # Kalamata olives (whole) != kalamataoliver (olive oil/paste)
    'kalamata': {
        'kalamataoliver',  # "kalamataoliver" in recipe = whole olives, not just the variety name
        'hummus',  # "Hummus med Kalamata Oliver" — hummus is the product, not olives
        'tapenade',  # olive paste/spread ≠ whole kalamata olives
    },
    'kalamataoliver': {
        'hummus',  # "Hummus med Kalamata Oliver" — hummus product, not olive product
        'tapenade',  # olive paste/spread ≠ whole kalamata olives
    },

    # Bread != flour
    'lantbröd': {
        'lantbrödsmjöl', 'lantbrodsmjol',  # bread flour ≠ bread
    },

    # Milk chocolate (baking) != Lindor milk chocolate candy
    'mjölkchoklad': {
        'mjölkchokladknappar', 'mjolkchokladknappar',  # Lindor candy ≠ baking chocolate
        'dadlar',  # "Dadlar mjölkchoklad och kokos" — dates coated in chocolate, not a chocolate bar
    },

    # Beef stew meat != fish stew meat
    'grytbitar': {
        'fiskgrytbitar',  # fish stew pieces (different animal)
    },

    # Nectar (juice drink) != nectarine (stone fruit)
    'nektar': {
        'nektarin', 'nektariner',  # nectarine fruit ≠ juice nectar
    },

    # Sourdough bread != sourdough starter
    'surdeg': {
        'surdegsstart',  # sourdough starter (different product)
    },

    # Bread != bread-derived/related products
    'bröd': {
        'brödsirap', 'brodsirap',  # bread syrup (baking ingredient, not bread)
        'brödkryddor', 'brodkryddor',  # bread spices (spice blend, not bread)
        'brödkrutonger', 'brodkrutonger',  # croutons (topping, not bread)
        'brödkrydda', 'brodkrydda',  # bread spice (singular)
        'brödet',  # definite singular (cooking instruction reference)
        'bröden', 'broden',  # definite plural ("till bröden" = serving instruction)
        'korvbrödsbagarn', 'korvbrodsbagarn',  # brand name containing "bröd"
        'bao',  # "bao bröd" = Asian steamed buns ≠ regular bread
    },

    # Korvbröd offer keyword should not match brand name "Korvbrödsbagarn"
    'korvbröd': {
        'korvbrödsbagarn', 'korvbrodsbagarn',  # brand name, not the product
    },

    # Milk (cow's) != plant-based milks, chocolate, powder, etc.
    # "Mjölk 3%" should NOT match recipes needing coconut milk or milk chocolate
    'mjölk': {
        'kokosmjölk', 'kokosmjolk',  # coconut milk (plant-based)
        'havremjölk', 'havremjolk',  # oat milk (plant-based)
        'mjölkchoklad', 'mjolkchoklad',  # milk chocolate (confectionery)
        'mjölkchokladknappar', 'mjolkchokladknappar',  # milk chocolate buttons
        'mjölkfritt', 'mjolkfritt',  # milk-free (explicitly NOT milk!)
        'mjölkfri', 'mjolkfri',  # milk-free (adjective)
        'mjölkproteinfritt', 'mjolkproteinfritt',  # milk-protein-free
        'mjölkpulver', 'mjolkpulver',  # milk powder (processed)
        'mjölkdryck', 'mjolkdryck',  # plant-based milk drink
        'filmjölk', 'filmjolk',  # soured milk (different product)
    },

    # Soy sauce != other soy products
    # "Japanese Soy Sauce" should NOT match recipes needing soybeans, soy mince, etc.
    'soja': {
        'sojabönor', 'sojabonor', 'sojabön', 'sojabon',  # soybeans
        'sojadryck',  # soy drink (plant-based)
        'sojagurt',  # soy yogurt
        'sojamjöl', 'sojamjol',  # soy flour
        'sojafärs', 'sojafars',  # soy mince
        'sojaglass',  # soy ice cream
        'sojagrädde', 'sojagradde',  # soy cream
        'sojabitar', 'sojabit',  # soy chunks/protein (TVP) ≠ soy sauce
    },

    # Orange (fruit) != orange juice, marmalade, etc.
    # "Apelsin Klass 1" should NOT match recipes needing orange juice
    'apelsin': {
        'apelsinjuice',  # orange juice (processed)
        'apelsinsaft',  # orange juice/squash
        'apelsinmarmelad',  # orange marmalade (processed)
        'apelsinkrokant',  # orange croquant (chocolate product)
        'apelsinsmak',  # orange flavor (flavoring, not fresh fruit)
        'apelsinlikör', 'apelsinlikor',  # orange liqueur ≠ fresh orange
        'likör', 'likor',  # any liqueur context — recipe wants alcohol, not fruit
        'juice',  # "Juice Apelsin Röd Grape" ≠ fresh oranges
        'apelsinblomsvatten',  # orange blossom water ≠ fresh oranges
    },

    # Pomegranate (fruit) != pomegranate syrup
    # "Granatäpple 300g" should NOT match "granatäpplesirap" ingredient
    'granatäpple': {
        'granatäpplesirap',  # pomegranate syrup (concentrated product)
    },

    # Honey != honeydew melon and honey-based products
    # "Blomsterhonung" should NOT match recipes needing honeydew melon
    'honung': {
        'honungsmelon',  # honeydew melon (completely different food!)
        'honungsrostade', 'honungsrostad',  # honey-roasted (processed product)
        'honungsmarinad',  # honey marinade (prepared sauce)
    },

    # Tortilla (wraps) != tortilla chips (nachos)
    'tortilla': {
        'tortillachips',  # tortilla chips / nachos ≠ soft wraps
    },

    # Taco (ready meals) != tacochips/tacosås
    # "Tacokyckling Fryst" should NOT match "tacochips" or "tacosås" recipes
    # Note: tacokrydda NOT blocked — "Taco Spice Mix" IS a tacokrydda
    'taco': {
        'tacochips',    # taco chips ≠ taco meat
        'tacosås',      # taco sauce ≠ taco meat
        'tacokrydda',   # taco seasoning ≠ taco shells/meat
        'tacokyckling',  # "Guldgågel Tacokyckling" — pre-marinated chicken, not taco spice/sauce
    },

    # Garlic (fresh) != garlic-flavored products
    # "Vitlök Kapsel" should NOT match recipes needing garlic powder or garlic sauce
    'vitlök': {
        'vitlökspulver', 'vitlokspulver',  # garlic powder (spice)
        'vitlöksdressing', 'vitloksdressing',  # garlic dressing (prepared)
        'vitlöksmarinad', 'vitloksmarinad',  # garlic marinade (prepared)
        'vitlökspeppar', 'vitlokspeppar',  # garlic pepper (spice blend)
        'vitlökssås', 'vitlokssas',  # garlic sauce (prepared)
        'vitlöksbaguett', 'vitloksbaguett',  # garlic bread (baked product)
        'vitlöksbröd', 'vitloksbrod',  # garlic bread
    },

    # Salad (prepared) != salladslök (spring onion)
    # "Kycklingcurry Sallad" should NOT match recipe ingredient "salladslök"
    'sallad': {
        'salladslök', 'salladslok',  # spring onion is a vegetable, not a salad
        'salladskrydda',  # spice mix ≠ fresh salad greens
        'salladsmix',  # pre-mixed bag ≠ head of lettuce/generic sallad
        'morotssallad',  # carrot salad ≠ green salad
        'fruktsalladen', 'fruksalladen',  # "(till fruktsalladen)" = serving instruction, not a salad ingredient
        'potatissalladen',  # "till potatissalladen" = dish name in bestämd form
        'pastasalladen',  # same pattern
    },
    'sallat': {  # alternate spelling (products: "Sallat Cosmopolitan", recipes: "romansallat")
        'salladslök', 'salladslok',
        'salladskrydda',
        'salladsmix',
    },
    'sallads': {
        'salladslök', 'salladslok',  # "Sallads Kyckling" should NOT match salladslök
    },

    # Tomato (fresh) != tomato products (puré, sauce, paste)
    # "Tomat Klass 1" should NOT match recipe ingredient "tomatpuré"
    'tomat': {
        'tomatpuré', 'tomatpure',  # tomato paste (concentrated product)
        'tomatpasta',  # tomato paste (Italian name)
        'tomatbas',  # prepared tomato base / sub-recipe reference, not fresh tomatoes
        'tomatsås', 'tomatsas',  # tomato sauce (prepared)
        'tomatsoppa',  # tomato soup (prepared)
        'tomatketchup',  # ketchup
        'tomatjuice',  # tomato juice
        'bifftomat', 'bifftomater',  # beefsteak tomatoes are specific, not generic tomatoes
        'småtomat', 'småtomater',  # small tomatoes ≠ regular tomatoes
        'körsbärstomat', 'körsbärstomater',  # cherry tomatoes (canned) ≠ regular tomatoes
        'tomatsmak',  # tomato-flavored ≠ actual tomatoes
    },
    'tomater': {
        'tomatbas',  # prepared tomato base / sub-recipe reference
        'bifftomat', 'bifftomater',  # specific beefsteak tomatoes ≠ generic tomatoes
        'småtomat', 'småtomater',  # small tomatoes ≠ regular tomatoes (plural keyword)
        'körsbärstomat', 'körsbärstomater',  # cherry tomatoes (canned) ≠ regular tomatoes
    },

    # Durum wheat (bulgur) != durum wheat flour
    # "Bulgur av Durumvete" should NOT match recipes needing durum flour
    'durumvete': {
        'durumvetemjöl', 'durumvetemjol',  # durum flour ≠ bulgur
    },

    # "Gyllen" is a branded aged cheese (e.g. "Gyllen 24m") — should NOT match inside
    # compound cooking terms like "gyllenbrun" (golden-brown), "gyllengul" (golden-yellow)
    'gyllen': {
        'gyllenbrun', 'gyllengul', 'gyllenröd', 'gyllenbrunt',
    },

    # Cucumber (fresh) != pickled/preserved cucumber products
    # "Gurka ca 320g" should NOT match recipe needing "saltgurka" or "bostongurka"
    'gurka': {
        'saltgurka', 'saltgurkor',  # pickled cucumber (singular + plural)
        'bostongurka', 'bostongurkor',  # sweet pickled relish
        'smörgåsgurka', 'smorgasgurka', 'smörgåsgurkor', 'smorgasgurkor',
        'ättiksgurka', 'attiksgurka', 'ättiksgurkor', 'attiksgurkor',
        'cornichon', 'cornichoner',  # small pickled gherkins
        'västeråsgurka', 'vasterasgurka', 'västeråsgurkor', 'vasterasgurkor',
    },
    'gurkor': {
        'saltgurkor',  # plural pickled
        'bostongurkor',
        'smörgåsgurkor', 'smorgasgurkor',  # "2 hela smörgåsgurkor" ≠ fresh cucumber
        'ättiksgurkor', 'attiksgurkor',
        'västeråsgurkor', 'vasterasgurkor',
    },

    # Cumin (kummin/karve) != cumin (spiskummin)
    # In Swedish: "kummin" = caraway seeds, "spiskummin" = cumin
    # These are completely different spices!
    'kummin': {
        'spiskummin',  # cumin (different spice from caraway)
    },

    # Chipotle (dried pepper) != chipotlepasta (chipotle paste)
    # "Chilli Chipotle" should NOT match recipe needing "chipotlepasta"
    'chipotle': {
        'chipotlepasta',  # chipotle paste (different product from dried chipotle)
    },

    # Pumpa (squash) != pumpakärnor (pumpkin seeds) — different products
    'pumpa': {
        'pumpakärnor', 'pumpakärna', 'pumpakaernor', 'pumpakarnor',  # seeds, not squash (singular + plural)
        'pumpafrön', 'pumpafron',  # pumpkin seeds alt. name — not squash
    },

    # Pizza products != pizza-kit recipe ingredients
    # "Capricciosa Pizza" extracts keyword 'pizza' (category-aware) which matches inside 'pizzakit'
    'pizza': {
        'pizzakit',   # pizza kit (recipe makes pizza from scratch) ≠ frozen/fresh pizza products
        'pizzaost',   # pizza cheese ≠ frozen pizza
        'pizzadeg',   # pizza dough ≠ frozen pizza
        'pizzasås', 'pizzasas',  # pizza sauce ≠ frozen pizza
        'pizzasten',  # pizza stone (cooking tool) ≠ pizza product
    },


    # Ice cream ("glass") != empty cones ("glasstrutar")
    # Without this, product keyword 'glass' matches inside ingredient "glasstrutar".
    'glass': {
        'glasstrut', 'glasstrutar',
    },

    # Whole hazelnuts != hazelnut cream/spread/drink
    'hasselnöt': {
        'hasselnötskräm', 'hasselnötskram',  # hazelnut cream/spread — not whole nuts
        'hasselnötsdryck',  # hazelnut milk/drink ≠ actual nuts
    },

    # Generic 'lamm' from lamb cut products should not match 'lammfärs' ingredients
    # (Lammfilé, Lammstek etc. are whole cuts ≠ ground meat)
    'lamm': {
        'lammfärs', 'lammfars',  # ground lamb ≠ lamb fillet/steak
        'lammkorv',  # lamb sausage ≠ lamb cuts (filé/stek/racks)
        'lammsmak',  # lamb-flavored ≠ actual lamb
        'lammfiol',  # "rökt lammfiol" → block generic lamm, only "lammfiol" products match
        'lammkotlett', 'lammkotletter',  # explicit lamb chops should not fall back to other lamb cuts
        'lammracks',  # explicit lamb racks should not fall back to other lamb cuts
        'lammytterfilé', 'lammytterfile',  # explicit lamb tenderloin should not fall back to other lamb cuts
    },
    'lammkött': {
        'lammkotlett', 'lammkotletter',  # same cut-specific protection for parent fallback
        'lammracks',
        'lammytterfilé', 'lammytterfile',
    },
    'lammkott': {
        'lammkotlett', 'lammkotletter',
        'lammytterfilé', 'lammytterfile',
    },

    # Beef innanlår should not match veal innanlår
    'innanlår': {
        'kalvinnanlår', 'kalvinnanlar',  # veal shank ≠ beef innanlår (Rostbiff Innanlår)
    },

    # Whole buckwheat grain ≠ buckwheat flour
    'bovete': {
        'bovetemjöl', 'bovetemjol',  # buckwheat flour ≠ whole buckwheat grain
    },

    # Fresh fennel != fennel pollen or sausage flavoring
    'fänkål': {
        'fänkålspollen', 'fankålspollen', 'fankalspollen',  # fennel pollen ≠ fennel bulb
        'salsicciafänkål', 'salsicciafankal',  # "Salsiccia Fänkål" = fennel-flavored sausage
        'fänkålssalsiccia', 'fankålssalsiccia', 'fankalssalsiccia',  # reverse compound
    },

    # Fresh mushrooms != fermented mushroom juice (specialty product)
    'svamp': {
        'svampjuice',  # fermented mushroom juice ≠ fresh mushrooms
        'svamparna',  # definite plural (cooking instruction reference)
        'portabellosvamp',  # portabello is a specific mushroom type — generic 'svamp' from compound shouldn't match Enoki etc.
        'svampsmak',  # mushroom-flavored ≠ actual mushrooms
    },

    # "Inläggning Snabb" (pickling liquid) ≠ "inläggningssill" (pickled herring)
    'inläggning': {
        'inläggningssill',  # compound word: pickling + herring = pickled herring
    },
    # "Pinsa" (bread base) matches "pinsasås" via substring — block when ingredient is sauce
    'pinsa': {
        'pinsasås',  # ingredient says "pinsasås" → product "Pinsa" (bread) should NOT match
    },
    # "tamari" (soy sauce) is substring of "tamarind" — block when ingredient is tamarind
    'tamari': {
        'tamarind', 'tamarindpasta',
    },

    # "matbas" (oat cream product) is substring of "tomatbas" (tomato base, a sub-recipe reference)
    'matbas': {
        'tomatbas',
    },

    # "chicken" is substring of "chickennuggets" (compound from SPACE_NORM)
    # "Chicken Wing Sauce" should NOT match recipe wanting chicken nuggets
    'chicken': {
        'chickennuggets',
    },

    # Sausage (korv) != hot dog buns (korvbröd)
    # "Enrisrökt Korv" keyword "korv" should NOT match ingredient "korvbröd"
    'korv': {
        'korvbröd', 'korvbrod',  # hot dog buns ≠ sausage
        'korvspad',              # sausage cooking liquid ≠ sausage product
        'kryddmix',    # "Korv Stroganoff Kryddmix" — spice mix, not sausage
        'stroganoff',  # "Korv Stroganoff Kryddmix"
        'prinskorv', 'prinskorvar',  # specific small sausage ≠ generic korv families
        'vego', 'vegansk', 'växtbaserad',  # vegan sausage ≠ meat sausage
        'lammkorv', 'lammkorvar',  # generic korv ≠ lammkorv (COMPOUND_STRICT
        # catches 'korv' in 'lammkorv' but NOT 'korv' in 'lammkorvar' plural)
    },

    # Flour (mjöl) != milk (mjölk) — "mjöl" is substring of "mjölk"
    # "Mjöl 1kg Belje" should NOT match "6 dl mjölk" (795 affected recipes!)
    'mjöl': {
        'bovetemjöl', 'bovetemjol',  # buckwheat flour ≠ generic flour
        'mjölk', 'mjolk',  # milk ≠ flour
        'lättmjölk', 'lattmjolk',
        'mellanmjölk', 'mellanmjolk',
        'standardmjölk', 'standardmjolk',
        'helmjölk', 'helmjolk',
        'kokosmjölk', 'kokosmjolk',  # coconut milk ≠ flour
        'mandelmjölk', 'mandelmjolk',  # almond milk ≠ flour
        'havremjölk', 'havremjolk',  # oat milk ≠ flour
        # Specific flour types — generic "Mjöl Tipo 00" should NOT match these
        'rågmjöl', 'ragmjol',  # rye flour ≠ generic flour
        'dinkelmjöl', 'dinkelmjol',  # spelt flour ≠ generic flour
        'grahamsmjöl', 'grahamsmjol',  # graham flour ≠ generic flour
        'mandelmjöl', 'mandelmjol',  # almond flour ≠ generic flour
        'havremjöl', 'havremjol',  # oat flour ≠ generic flour
        'rismjöl', 'rismjol',  # rice flour ≠ generic flour
        'majsmjöl', 'majsmjol',  # corn flour ≠ generic flour
        'kokosmjöl', 'kokosmjol',  # coconut flour ≠ generic flour
        'kikärtsmjöl', 'kikartsmjol',  # chickpea flour ≠ generic flour
        'rågsikt',  # "Rågsikt med vetemjöl" = rye blend ≠ pure wheat/generic flour
    },

    # Buns (bullar) != potato balls (potatisbullar) — "bullar" is substring of "potatisbullar"
    # "Släta bullar 240g" should NOT match "12 Felix Potatisbullar"
    'bullar': {
        'potatisbullar',  # potato balls ≠ bread buns
        'köttbullar', 'kottbullar',  # meatballs ≠ bread buns
        'kycklingköttbullar', 'kycklingkottbullar',  # chicken meatballs
        'fiskbullar',  # fish balls ≠ bread buns
    },

    # Baker's yeast (jäst) should NOT match "bjäst" (nutritional yeast) recipes
    # or adjective forms like "jästa svarta bönor".
    'jäst': {'bjäst', 'jästa'},
    # Reverse-substring leak: "ärta" from pea-based products inside "kräftstjärtar".
    'ärta': {'kräftstjärt', 'kräftstjärtar', 'kraftstjart', 'kraftstjartar'},

    # Meringue — "spara vitorna till marängen" is a cooking instruction, not a meringue ingredient
    # Must include 'marängen' as blocker because smart blocker sees 'maräng' in 'marängen' as valid compound
    'maräng': {
        'äggulor', 'äggula',  # egg yolk ingredient mentioning meringue in instructions
        'äggvitor', 'äggvita',  # egg white ingredient mentioning meringue in instructions
        'marängen',  # instruction form "till marängen" — not a standalone meringue ingredient
    },
    # Oat flour (havremjöl) ≠ oat milk (havremjölk)
    'havremjöl': {'havremjölk'},  # "Havremjöl 300g" matching "havremjölk" ingredient via reverse substring
    'havremjol': {'havremjölk', 'havremjolk'},
    # Apple must drink ≠ rågmustbröd (bread)
    'must': {'bröd', 'brod'},  # "Must Äpple 1l" matching "rågmustbröd" ingredient via reverse substring


}

# Intentionally selective — not exhaustive. Add new blockers when actual false
# positives are observed in production data via the normal manual cache review flow.
FALSE_POSITIVE_BLOCKERS: Dict[str, Set[str]] = {
    fix_swedish_chars(k).lower(): {fix_swedish_chars(w).lower() for w in v}
    for k, v in _FALSE_POSITIVE_BLOCKERS_RAW.items()
}

# ============================================================================
# PRODUCT NAME BLOCKERS (reverse of FALSE_POSITIVE_BLOCKERS)
# ============================================================================
# Problem: "curry" keyword matches both "Curry Burk" (powder) and "Green Curry
# Thai Mild" (paste). Recipe "1 tsk curry" means powder, not paste.
# Solution: If blocker word appears in PRODUCT name but NOT in ingredient text,
# block the match.
# Format: keyword -> set of words that, if in product name, block the match
# UNLESS the same word also appears in the ingredient text.
_PRODUCT_NAME_BLOCKERS_RAW: Dict[str, Set[str]] = {
    # BBQ sauce ≠ pulled meat with BBQ glaze
    # "Pulled Chicken Smokey BBQ med glaze" has keyword "bbqsås" but is a meat product
    'bbqsås': {
        'pulled', 'pulledchicken', 'pulledpork', 'pulledbeef',
    },
    'bbqsas': {
        'pulled', 'pulledchicken', 'pulledpork', 'pulledbeef',
    },
    # Cream pepparsås (Lohmanders) ≠ hot pepper sauce (Tabasco)
    # "Pepparsås 250ml Lohmanders" = cream-based steak sauce, NOT hot sauce
    # Recipes use 'pepparsås' to mean hot sauce (Tabasco, sambal context)
    'pepparsås': {
        'lohmanders',  # Lohmanders = cream sauce brand (bearnaise, pepparsås etc.)
    },
    # Sweet chili sauce ≠ frozen ready meals / flavored products with chili in name
    # "Sweet chili kyckling Fryst 600g Guldfågeln" = ready meal, not sauce
    # "Färskost Sweet chili 200g Philadelphia" = cream cheese, not sauce
    # "Pasta Sweet Chili 450g ICA" = ready pasta, not sauce
    # "Marinad BBQ Sweet Chili 75g Santa Maria" = marinade, not sauce
    # "Vegeta Sweet Chili 200g Podravka" = spice mix, not sauce
    'chilisås': {
        'kyckling', 'kycklinglårfilé', 'kycklinglarfile',
        'färskost', 'farskost', 'cream cheese',
        'pasta',
        'marinad',    # BBQ/meat marinade ≠ chili sauce
        'vegeta',     # spice mix ≠ chili sauce
    },
    'curry': {
        'paste', 'pasta',       # curry paste products
        'thai',                 # Thai curry = paste
        'green', 'grön',       # green curry = paste
        'red', 'röd',          # red curry = paste
        'yellow', 'gul',       # yellow curry = paste
        'panang', 'panaeng', 'paneng', 'massaman',  # Thai curry variants = paste
        'sauce',               # "Curry Mango Sauce 220ml Heinz" — sauce, not curry powder
        'mango',               # "Curry Mango 41g Santa Maria" — mango-flavored ≠ plain curry
        'chicken',             # "Thai chicken red curry 750g Findus" — frozen ready meal
    },
    # Plain eggs ≠ liquid/pasteurized egg products unless recipe explicitly asks for them
    'ägg': {
        'pastöriserad', 'pastöriserade',
        'flytande',
    },
    'tomat': {
        'ätklart', 'ätklar',   # "Soltorkad Tomat Ätklart Kyckling" — chicken product, not tomatoes
        'fusii',               # "Fusii mozzarella & tomat" — ready pasta dish, not tomatoes
        'krämig kyckling',     # "Krämig kyckling med soltorkad tomat" — ready meal, not tomato sauce
    },
    'tomater': {
        'ätklart', 'ätklar',   # same as above, plural form
        'krämig kyckling',     # same as above
    },
    'tomatsopp': {
        'färskost',   # "Tomatsopp Färskost ICA" — cream cheese flavor, not tomato soup
    },
    'tortilla': {
        'pizza',      # "Pizza Tortilla" is a pizza base, not a wrap/taco tortilla
        'strips',     # "Tortilla Strips Crunchy Cheesy" — snack, not wrap
        'crunchy',
        'cheesy',
        'chips',      # "Tortilla Chips" — also snack
    },
    'tortillas': {
        'pizza',
    },
    # Chili products that are NOT fresh chili peppers
    # NOTE: chili PPR (PROCESSED_PRODUCT_RULES) has these as indicators,
    # but the PPR compound fallback bug lets them through when another
    # ingredient has 'chiliflakes' etc. PNB catches them reliably.
    'chilipeppar': {
        'örtsalt', 'ortsalt',  # "Örtsalt Chili&paprika" — herb salt spice mix
        'grillkrydda',         # "Grillkrydda Chili Burk" — BBQ spice mix
        'white',               # "White With Chili 38%" — white chocolate
        'cheez', 'ballz',      # "Chili Cheez Cheez Ballz" — snack, not fresh chili
        'tofu',                # "Tofu Chili Vitlök" — tofu product
        'red hot',             # "Ost Red Hot chili pepper" — cheese slices
        'majonnäs', 'majonnas', 'hellmann',  # "Majonnäs med chilli"
        'havre cooking',       # "Havre Cooking Oat Chili"
        'ostsnacks',           # "Ostsnacks cheez ballz chili cheez"
        'crispy',              # "Chilli Crispy I Olja" — chili oil condiment, not fresh chili
        'olja',                # "Chiliolja" — oil condiment, not fresh chili
        'mild',                # "Yellow/Green Chili Mild" — sauce, not fresh
        'favabönor', 'favabonor', 'foul modemmas',  # bean conserve with chili flavor
    },
    'chili': {
        'örtsalt', 'ortsalt',
        'grillkrydda',
        'white',
        'cheez', 'ballz',      # "Chili Cheez Cheez Ballz" — snack, not fresh chili
        'tofu',                # "Tofu Chili Vitlök" — tofu product, not chili
        'red hot',             # "Ost Red Hot chili pepper" — cheese slices, not chili
        'majonnäs', 'majonnas', 'majonnäs', 'hellmann',  # "Majonnäs med chilli" — mayo, not chili
        'havre cooking',       # "Havre Cooking Oat Chili" — oat cooking cream, not chili
        'crispy',              # "Chilli Crispy I Olja" — chili oil product, not fresh chili
        'olja',                # "Chiliolja" blocked when recipe wants fresh chili (not oil)
        'mild',                # "Yellow/Green Chili Mild" Santa Maria — chili sauce, not fresh
        'ostsnacks',           # "Ostsnacks cheez ballz chili cheez" — snack
        'favabönor', 'favabonor', 'foul modemmas',  # bean conserve with chili flavor
        'mango',               # "Torkad Mango Chili Twist" — dried mango snack, not chili
    },
    'chilifrukt': {
        'örtsalt', 'ortsalt',
        'grillkrydda',
        'white',
        'cheez', 'ballz',      # "Chili Cheez Cheez Ballz" — snack, not chili fruit
        'tofu',                # "Tofu Chili Vitlök" — tofu product
        'red hot',             # "Ost Red Hot chili pepper" — cheese slices
        'majonnäs', 'majonnas', 'hellmann',
        'havre cooking',
        'ostsnacks',
        'crispy',              # "Chilli Crispy I Olja" — chili oil condiment
        'olja',                # "Chiliolja" — oil condiment
        'mild',                # "Yellow/Green Chili Mild" — sauce
        'favabönor', 'favabonor', 'foul modemmas',  # bean conserve
        'mango',               # "Torkad Mango Chili Twist" — dried mango snack
    },
    'chilifrukter': {
        'örtsalt', 'ortsalt',
        'grillkrydda',
        'white',
        'cheez', 'ballz',
        'tofu',
        'red hot',
        'majonnäs', 'majonnas', 'hellmann',
        'havre cooking',
        'ostsnacks',
        'crispy',              # "Chilli Crispy I Olja" — chili oil condiment
        'olja',                # "Chiliolja" — oil condiment
        'mild',                # "Yellow/Green Chili Mild" — sauce
        'favabönor', 'favabonor', 'foul modemmas',  # bean conserve
        'mango',               # "Torkad Mango Chili Twist" — dried mango snack
    },
    # Broad beans - raw/cooking bondböna should not match plant-based whipping products
    'bondböna': {
        'visp',  # "Visp Bondböna" ≠ broad beans or barista drink unless ingredient says visp
    },
    # Ginger — block non-fresh ginger products
    'ingefära': {
        'picklad', 'picklade',  # "Ingefära Picklad" — pickled ginger ≠ fresh
        'syltad',               # "Ingefära Syltad Kub" — candied/pickled ginger ≠ fresh
        'sushi', 'garisushi',   # "Garisushi Ingefära" / "Skivad Ingefära Sushi" — pickled sushi ginger
        'balsamico', 'crema',   # "Crema di Balsamico ingefära" — balsamico cream, not ginger
        'tofu',                 # "Tofu marinerad soja ingefära" — tofu product, not ginger
        'marinerad',            # "Marinerad Tofu Sojasås & Ingefära" — marinated product
    },
    # Tamari soy — block tofu products
    'tamarisoja': {
        'tofu',                # "Tofu marinerad soja ingefära" — tofu, not soy sauce
    },
    # Cherry tomatoes — block pasta sauce
    'körsbärstomater': {
        'pastasås', 'pastasas',  # "Pastasås Körsbärstomat & Basilika" — sauce, not fresh tomatoes
    },
    # Balsamic vinegar — crema/glaze is not plain vinegar
    'balsamvinäger': {
        'crema',  # "Crema di Balsamico" — glaze/cream, not plain balsamic vinegar
    },
    'balsamvinager': {
        'crema',
    },
    # Burrata — block stuffed pasta
    'burrata': {
        'cappellacci',         # "Pasta Cappellacci Pesto och Burrata" — stuffed pasta, not burrata cheese
    },
    # Parmigiano — flarn are cheese chips, not grated/shaved cheese for cooking
    'parmigiano': {
        'flarn',
    },
    # Grana Padano — same cheese-chip form issue as parmigiano
    'padano': {
        'flarn',
    },
    # Plain salsiccia ≠ vegan or minced variants unless recipe says so
    'salsiccia': {
        'färs', 'fars', 'växtbaserad', 'vaxtbaserad',
    },
    # Spinach — block dumplings and pre-made stuvad
    'spenat': {
        'ostknyten', 'knyten',  # "Spenat- & ostknyten Fryst" — dumplings, not fresh spinach
        'stuvad', 'stuvade',    # "Stuvad spenat" — pre-made creamed spinach ≠ raw/frozen
    },
    'bladspenat': {
        'ostknyten', 'knyten',
    },
    'babyspenat': {
        'ostknyten', 'knyten',
    },
    # Knyten — block dimsum from matching pastaknyten
    'knyten': {
        'dimsum', 'dim sum',  # "Dimsum knyten" — Asian dumplings, not pasta knyten
    },
    # Skruvar — block snack chips from matching pastaskruvar
    'skruvar': {
        'olw', 'lättsaltade', 'saltade',  # "Skruvar Lättsaltade 100g OLW" — potato snack, not pasta
    },
    # Fiskgrytbitar — block pre-made sushi from matching (only fish stew pieces for fish stew)
    # The mapping 'fiskgrytbitar' → 'lax' causes sushi products to match (they contain 'lax' keyword).
    # PNB blocks ready-made sushi dishes while allowing raw lax to match via the mapping.
    'fiskgrytbitar': {
        'sushi', 'nigiri', 'roll', 'meny',  # "Sushi Lax Nigiri 10 Bitar", "Sushi Meny Duo Lax" etc.
    },
    # Beetroot — block juice products
    'rödbeta': {
        'juice', 'bag-in-box',  # "Juice Rödbeta" / "Rödbeta Bag-In-Box" — juice, not fresh beetroot
        'stekt',                # "Rödbetor Stekta 540g Rolnik" — roasted jar beets ≠ fresh beetroot
    },
    'rödbetor': {
        'juice', 'bag-in-box',
        'stekt',                # "Rödbetor Stekta" — roasted preserved ≠ fresh rödbetor
    },
    'rodbetor': {
        'juice', 'bag-in-box',
        'stekt',
    },
    # NOTE: PNB 'karamell' → 'glass' removed — glass normalization blocks karamell ice cream
    #       (karamell is in _GLASS_EXOTIC_WORDS)
    # Pumpkin products
    'pumpa': {
        'bröd', 'brod',  # "Rågbröd Solros & Pumpa" — bread with pumpkin seeds ≠ fresh pumpkin
    },
    # Tomato sauce - beans/fish in tomato sauce ≠ a jar of tomato sauce
    # NOTE: 'tomatsas' omitted — fix_swedish_chars('tomatsas') = 'tomatsås' (same compiled key)
    'tomatsås': {
        'bönor', 'bonor',  # "Vita Bönor i Tomatsås" — bean product, not tomato sauce
        'brisling',        # "Brisling I Tomatsås" — canned fish, not tomato sauce
        'pizzabottnar',    # "2 Pizzabottnar med Tomatsås" — pizza dough product, not sauce
    },
    'tomatsos': {
        'bönor', 'bonor',
        'brisling',
    },
    # Paprika powder ≠ products with paprika as a flavor
    # OFFER_EXTRA_KEYWORDS adds 'paprikapulver' to products with 'paprika' in name,
    # but cheese cubes and frozen veggie mixes are NOT paprika powder
    'paprikapulver': {
        'tärnad', 'tarnad',  # "Tärnad ost i olja Paprika" — cheese cubes
        'ärtor', 'artor',    # "Ärtor, Majs & Paprika" — frozen veggie mix
        'rökt', 'rokt',      # "Paprikapulver Rökt" ≠ vanlig paprikapulver
    },
    # Dill-flavored cucumber product ≠ fresh dill herb
    # Dill-flavored snacks (e.g. "Skruvar Dill") ≠ fresh dill herb
    'dill': {
        'gurka', 'gurkor',  # "Gurka med Dill" — cucumber product, not dill
        'skruvar',          # "Skruvar Dill" — dill-flavored snack, not fresh dill
    },
    # Edamame dumplings are prepared convenience food, not plain edamame beans.
    'edamame': {
        'dumpling', 'dumplings',
    },
    # Granulated/powdered onion ≠ fresh onion
    'lök': {
        'granulerad',  # "Lök Granulerad 41g" — dried granulated onion, not fresh onion
    },
    # Fresh plums ≠ dried/pitted prune products unless the ingredient says so.
    'plommon': {
        'soft',
        'urkärnade', 'urkarnade',
    },
    # Manchego cheese ≠ fuet (sausage) with manchego flavor
    'manchego': {
        'fuet',  # "Fuet Manchego 150g ICA" — cured sausage, not cheese
        'tapastallrik',  # "Tapastallrik med Manchego" — tapas assortment, not a cheese block
    },
    # Fig confit/preserve ≠ fresh figs
    'fikon': {
        'confit',  # "Fikon & Valnöt Confit" — preserve, not fresh fruit
        'balsamico', 'crema',  # "Crema Di Balsamico Fikon" is balsamic cream, not figs
    },
    # Sunflower seed bread/crispbread/oil ≠ sunflower seeds
    'solros': {
        'fröknäcke', 'froknacke', 'knäcke', 'knacke', 'knäckebröd',  # crispbread
        'bröd', 'brod', 'rågbröd', 'ragbrod',  # bread with seeds ≠ raw seeds
        'olivolja', 'olja',  # "Solros & Olivolja" — oil product, not seeds
    },
    # Stuffed pepper products ≠ pepperoni salami
    'peperoni': {
        'ostfyllning',  # "Peperoni Grön med ostfyllning" — stuffed pepper, not salami
    },
    # Stuffed pepper product matching tortellini "med ostfyllning" ≠ cheese-filled pasta
    'ostfyllning': {
        'peperoni',  # "Peperoni Grön med ostfyllning" — stuffed pepper, not pasta
    },
    # Mayo/sauce products with gochugaru ≠ gochugaru spice flakes
    'gochugaru': {
        'majo', 'majonnäs',  # "Majo Gochugaru Vitlök" — mayo product, not spice
    },
    # Soy sauce keyword matching tofu product ≠ actual soy sauce
    'sojasås': {
        'tofu',  # "Marinerad Tofu Sojasås & Ingefära" — tofu product, not soy sauce
    },
    # Mirin (sweet rice wine) ≠ risvinäger (rice vinegar)
    'risvinäger': {
        'mirin',  # "Mirin Risvin 500 ml" — sweet rice wine, not vinegar
    },
    'risvinager': {
        'mirin',
    },
    # "Marabou Schweizernöt kladdkaka 420g Almondy" — frozen cake, not chocolate for melting
    'marabou': {
        'kladdkaka',  # ready-made kladdkaka products, not chocolate bars
    },
    # Candy/paste products with mandel ≠ raw almonds
    'mandel': {
        'cone',      # "Mandel Mini Cone Flerpack" — ice cream candy
        'fyllning', 'mandelfyllning',  # "Mandelfyllning 38% Mandel" — baking paste
        'nötsmör', 'nötsmor',  # nut butter products
        'marsipan',  # "Marsipan 24% sötmandel" is marzipan, not raw almonds
        'caramel', 'salted caramel',  # "Mandel Salted Caramel" — flavored snack
        'saltad', 'saltade',  # "Mandlar Rostade och Saltade" — snack almonds, not plain baking/cooking mandel
    },
    'mandlar': {
        'cone', 'fyllning',
        'nötsmör', 'nötsmor',  # nut butter products
        'marsipan',  # "Marsipan 24% sötmandel" is marzipan, not raw almonds
        'caramel', 'salted caramel',  # "Mandel Salted Caramel" — flavored snack
        'saltad', 'saltade',
    },
    'sötmandel': {
        'cone', 'fyllning',
        'nötsmör', 'nötsmor',  # nut butter products
        'marsipan',  # "Marsipan 24% sötmandel" is marzipan, not raw almonds
        'caramel', 'salted caramel',  # "Mandel Salted Caramel" — flavored snack
        'saltad', 'saltade',
    },
    # "Eriks s��ser" brand products — 'såser' extracted from brand name, matches any "X såser" ingredient
    'såser': {
        'eriks',  # "Bearnaise 450ml Eriks såser" — brand name, not relevant sauce
    },
    'soltor': {'oliver', 'oliv'},  # "Snackoliver Soltor" is sun-dried olives, not soltorkade tomater
    'högrev': {
        'hamburgare', 'burger', 'burgare',  # burger patties ≠ raw chuck cut
    },
    'hogrev': {
        'hamburgare', 'burger', 'burgare',
    },
    'nötfärs': {
        'högrev',  # "Högrev av nöt i bit" is a beef cut, not ground beef (416 FP recipes)
        'vego', 'vegansk', 'soja', 'växtbaserad',  # vegan mince ≠ beef mince
    },
    'vaniljsmak': {'marsipan', 'figurmarsipan'},  # "Figurmarsipan Vit Vaniljsmak" ≠ vanilla extract
    'schalottenlök': {'fond'},  # "Scharlottenlök Brynt Fond" is stock product, not fresh shallots
    'scharlottenlök': {'fond'},
    'baguette': {'vitlök', 'vitlok'},  # "Baguetter Vitlök Frysta" is garlic bread, not plain baguette
    'gojibär': {'kokosbite', 'kokos bite'},  # "Kokosbite Gojibär" — coconut snack ≠ dried goji berries
    'gojibärbär': {'kokosbite', 'kokos bite'},
    'yuzu': {'juice äpple', 'äpple grapefrukt'},  # "Juice Äpple Grapefrukt Yuzu" — fruit juice ≠ yuzu spice/paste
    'mjölkfritt': {'margarin', 'bordsmargarin'},  # "Margarin Mjölkfritt" — margarine is not a milk-free milk alternative
    'mjolkfritt': {'margarin', 'bordsmargarin'},  # same, ASCII variant
    'hallonsmak': {'proteinshake', 'shake'},  # "Proteinshake Hallonsmak" — not raspberry-flavored chocolate
    'syrade': {'morötter', 'morot', 'morotter'},  # "Morötter Naturligt Syrade" — pickled carrots matching "syrad blomkål" via reverse substring
    'fetaost': {'sås'},  # "Sås Fetaost Original" — sauce product, not solid feta cheese
    'revbensspjäll': {'rub'},  # "BBQ rub Ribs" — spice rub product, not actual ribs/revbensspjäll
    'solrosfrön': {
        'knäcke', 'fröknäcke',
        'saltad', 'saltade',
    },  # Crispbread and salted snack seeds are not plain loose sunflower seeds
    'feta': {'sås fetaost'},  # "Sås Fetaost Original" — sauce product, not solid feta cheese
    'baguetter': {'vitlök', 'vitlok'},
    # Fish roe "rom" products ≠ rum (the spirit) for baking/desserts
    'rom': {
        'finkornig',   # "Rom röd finkornig 80g Abba" — fish roe, not rum
        'finkorning',  # "Röd Rom Finkorning 70g ICA" — typo variant of finkornig
        'caviarmix',   # "Caviarmix svart rom av sill och lodda" — fish roe
        'arom',        # "Arraksarom"/"Citronarom" are extracts, not fish roe or rum
    },
    # Råsocker/rörsocker — sugar cubes are not the granulated baking form
    'råsocker': {
        'bit',
    },
    'rasocker': {
        'bit',
    },
    'rörsocker': {
        'bit',
    },
    # Nutella snack products ≠ Nutella hazelnut spread
    'nutella': {'biscuit', 'ready', '6-pack', 'semla'},  # "Nutella Biscuit", "B-ready Nutella 6-pack", "Semla Nutella"
    # "Pinsa Sås" (sauce for pinsa) and "Pinsa Margherita" (ready-made topped base)
    # ≠ plain "Mini Pinsa" (bread base)
    'pinsa': {'sås', 'margherita'},
    # Elderflower wellness shots ≠ elderflower cordial/saft
    'fläder': {
        'shot', 'ingefärsshot',  # "Ingefärsshot Fläder" is a wellness drink, not elderflower saft
    },
    # Spelt crackers ≠ spelt flour (dinkelsikt/dinkelmjöl)
    'dinkel': {
        'kex',  # "Lätta Dinkel Kex Utvalda" is a cracker, not spelt flour
    },
    # Dried fruit mix ≠ fresh melon
    'melon': {
        'torkad frukt',  # "Torkad frukt Tropisk Dried Melon 200g" — dried fruit snack, not fresh melon
    },
    # Filled pasta with asparagus ≠ fresh asparagus
    'sparris': {
        'mezze lune', 'pasta mezze',  # "Pasta Mezze Lune Sparris och Pancetta" — filled pasta, not raw asparagus
    },
    # Canned makrill in tomato sauce ≠ fresh makrill
    'makrill': {
        'tomatsås', 'tomatssås',  # "Makrill i tomatsås 185g Abba" — canned product ≠ fresh mackerel
    },
    # Frozen pizza products ≠ salami ingredient
    'salame': {
        'pizza',  # "Pizza Salame Ristorante Fryst" is a frozen pizza, not salami
    },
    # Herring products with mustard ≠ mustard condiment
    'senap': {
        'sill',  # "Senapssill", "Senap & Maltwhiskysill" — herring, not mustard
    },
    'dijonsenap': {
        'sill',  # "Dijonsenapssill" — herring with dijon, not dijon mustard
    },
    # Cayenne pepper sauce ≠ cayenne pepper spice
    'cayennepeppar': {
        'sauce',  # "Cayenne Pepper Sauce 177ml Bulliard's" — hot sauce, not cayenne powder
    },
    'cayenne': {
        'sauce',  # same product, matched_keyword may be 'cayenne' instead of 'cayennepeppar'
    },
    'timjan': {
        'zaatar', 'za\'atar',  # "Zaatar Aleppo Timjan" — spice blend, not pure thyme
    },
    'timjankvistar': {
        'zaatar', 'za\'atar',
    },
    'timjankvista': {
        'zaatar', 'za\'atar',
    },
    # Tacosalsa — block ready meals and non-salsa taco products
    'tacosalsa': {
        'pulled',    # "Pulled Beef Taco 370g ICA" — meat ready meal, not salsa
        'kit',       # "Taco kit 288g Santa Maria" — taco kit, not salsa
        'ostcrème', 'ostcreme',  # "Taco Ostcrème Middagsmagi" — cheese cream, not salsa
        'spice',     # "Spice Mix Cheesy Taco Spice Mix" — dry spice, not salsa
    },
    # NOTE: PNB matched_keyword = product keyword, not ingredient keyword.
    # "Taco kit" product has keyword 'taco', which matches ingredient 'tacosalsa'
    # via reverse substring. PNB key must be 'taco' (product keyword), not 'tacosalsa'.
    'taco': {
        'pulled',    # "Pulled Beef Taco" — meat ready meal
        'kit',       # "Taco kit" — contains tortillas+spice, not salsa
        'ostcrème', 'ostcreme',  # "Taco Ostcrème" — cheese cream
        'spice',     # "Spice Mix Cheesy Taco" — dry spice mix
    },
    # Nacho cheese dip ≠ nachochips/tortillachips
    'nacho': {
        'dip',  # "Dip Nacho Cheese 250g ICA" — cheese dip, not tortilla chips
    },
    'nachochips': {
        'dip',  # same product
    },
    # Jalapeno cheese cream / snacks ≠ fresh jalapeno
    'jalapeno': {
        'ostcrème', 'ostcreme',  # "Jalapeno ostcrème middagsmagi" — cheese cream, not pepper
        'cashew',                # "Cashew Jalapeno 140g Exotic Snacks" — snack, not pepper
    },
    # Laoganma products (jordnötter/bönor i chiliolja) should only match recipes
    # that specifically ask for Laoganma, not generic "chiliolja" recipes
    'chiliolja': {
        'laoganma',  # "Jordnötter I Chiliolja 275g Laoganma" — nut/bean product, not pure chili oil
    },
    # Chili oil/sauce products ≠ fresh chili or chili powder
    # NOTE: extends existing 'chili' PNB (which already blocks örtsalt, grillkrydda, etc.)
    # These additions target specific products not covered by existing blockers.
    # Coriander Lime tortilla ≠ fresh lime; Läkerol pastilles ≠ fresh lime
    'lime': {
        'coriander',  # "Coriander Lime 250ml El Taco Truck" — tortilla product, not lime fruit
        'pastill', 'pastiller', 'läkerol', 'lakerol',  # candy, not fruit
    },
    # Mango-flavored products ≠ fresh mango
    'mango': {
        'sojaprodukt',  # "Sojaprodukt Greek Style Mango" — yoghurt, not fruit
        'mochi',        # "Mochi strawberry, mango & passion" — dessert, not fruit
        'sauce',        # "Hot Mango Sauce" — sauce, not fruit
        'curry',        # "Curry Mango 41g Santa Maria" — spice blend, not mango fruit
        'hallon',       # "Mango & hallon Fryst" = mixed fruit ≠ pure mango
        'torkad frukt',  # "Torkad frukt Bara Mango Ananas" — dried fruit snack ≠ fresh mango
    },
    'papaya': {
        'torkad',        # "Papaya Torkad Tärningar" — dried fruit, not fresh papaya
        'torkade',
        'torkad frukt',
    },
    # Frozen wok mixes ≠ raw vegetables
    'grönkål': {'wok'},  # "Nordisk wok med grönkål" ≠ raw kale
    'gronkal': {'wok'},
    # Dried fruit snack products ("Torkad Frukt Bara", "Sunshine Delights") ≠ fresh/frozen fruit
    # Pastilles, yoghurt, and candy with fruit flavors ≠ actual fruit
    'hallon': {'torkad frukt', 'pastill', 'pastiller', 'läkerol', 'lakerol', 'lättyoghurt', 'lattyoghurt', 'godisrem',
               'mango', 'blåbär', 'hallongrotta', 'hallongrottor'},  # mixed berries/cookies ≠ pure hallon
    'jordgubb': {'torkad frukt', 'pastill', 'pastiller', 'läkerol', 'lakerol', 'godisrem', 'lättyoghurt', 'lattyoghurt'},
    'jordgubbar': {'torkad frukt', 'pastill', 'pastiller', 'läkerol', 'lakerol', 'godisrem', 'lättyoghurt', 'lattyoghurt'},
    'ananas': {'torkad frukt'},
    'svartvinbär': {'torkad frukt'},
    # Juice products ≠ whole fruit
    'blodapelsin': {'juice'},  # "Juice Apelsin Röd Grape" gets keyword 'blodapelsin' via substitution
    # Candy strips with fruit flavor ≠ fresh fruit
    'äpple': {'godisrem'},
    # "Popcorn chicken" = breaded bites, not actual popcorn
    'popcorn': {'chicken', 'chcken'},
    # Marmalade with spirit flavor ≠ the spirit itself
    'brandy': {'marmelad'},
    'calvados': {'marmelad'},
    # Ready-meal/pesto with sun-dried tomatoes ≠ actual sun-dried tomatoes
    'soltorkad tomat': {'pesto', 'krämig kyckling', 'tapenade'},
    'soltorkade tomater': {'pesto', 'krämig kyckling', 'creme', 'créme', 'tapenade'},
    # Piri-piri flavored sausage ≠ piri-piri sauce
    'piripiri': {'kabanoss', 'vegokabanoss', 'korv'},
    # Olive snack product ≠ provencal herbs
    'provencal': {'oliver', 'snack'},
    'provensalsk': {'sallad'},  # "Provensalsk sallad" ≠ provensalska örter
    # Licorice candy ≠ licorice powder for baking
    'lakrits': {'sockerfri', 'de bron', 'godis', 'stång'},
    # Juice product ≠ whole blodgrape fruit
    'blodgrape': {'juice', 'god morgon'},
    # Hummus with kalamata olives ≠ plain kalamata olives
    'kalamata': {'hummus'},
    # Coriander seeds ≠ fresh coriander herb
    # Product "Korianderfrön Hela" has keyword 'koriander' (via INGREDIENT_PARENTS)
    # but recipe wanting "Färsk koriander" should not get seeds
    'koriander': {
        'frön', 'fron',  # "Korianderfrön" = seeds, not fresh leaves
        'blad',          # "Korianderblad" = dried/fresh leaves, not ground coriander
    },
    # Habanero sauce ≠ fresh habanero pepper
    'habanero': {
        'sauce', 'sås',  # "Hot Habanero Sauce", "Sås Habanero het" — sauces, not fresh pepper
    },
    # Harissa paste/sauce products ≠ hummus
    'harissa': {
        'hummus',  # "Hummus Harissa" — hummus product with harissa flavor, not harissa paste
    },
    # Pasta sauce / fond / preserved mushroom ≠ fresh mushrooms
    'champinjon': {
        'pastasås', 'pastasas',  # "Pastasås Tomat och champinjon" — sauce, not fresh mushrooms
        'fond',                  # "Fond Du Chef Champinjon" — stock, not fresh mushrooms
        'tetra',                 # "Champinjoner i tetra" — preserved, not fresh
        'konserverade', 'konserverad',  # canned mushrooms
        'burk',                  # "Champinjoner på burk" — canned
        'inlagd', 'inlagda',     # pickled/preserved
        # Fresh champinjoner always have "Klass 1" in name; "skivade"/"hela" = preserved jar products.
        # DB: Champinjoner Skivade 290g ICA, Champinjoner Hela 290g ICA, Champinjoner skivade och smakrika 180g ICA
        # are all preserved. Only "Klass 1" products are fresh. Safe to block these descriptors.
        'skivade',               # "Champinjoner Skivade 290g" — preserved glass jar
        'hela',                  # "Champinjoner Hela 290g" — preserved glass jar
    },
    'champinjoner': {
        'pastasås', 'pastasas',
        'fond',
        'tetra',
        'konserverade', 'konserverad',
        'burk',
        'inlagd', 'inlagda',
        'skivade',               # "Champinjoner Skivade 290g ICA" — preserved glass jar
        'hela',                  # "Champinjoner Hela 290g ICA" — preserved glass jar
    },
    # Filled pasta with mushroom ≠ raw/dried mushroom
    'karl-johansvamp': {
        'pasta', 'mezze', 'ravioli', 'tortellini',  # "Pasta Mezze Lune Karl-johansvamp" — filled pasta, not raw mushrooms
    },
    # Vegetable cheese patty ≠ fresh vegetables
    'blomkål': {
        'ostbiff',  # "Broccoli blomkål och ostbiff" — processed patty, not fresh cauliflower
        'mix', 'blandning',  # frozen veggie mix ≠ plain cauliflower
    },
    'broccoli': {
        'ostbiff',  # same product
        'quorn', 'escalopes',  # "Vegetarisk Cheese & broccoli escalopes Quorn" — composite product
        'mix', 'blandning',  # "Broccolimix Fryst" — frozen veggie mix ≠ plain broccoli
    },
    # Product-containing-ingredient: block keywords that appear as secondary
    # flavoring/topping in composite products (not the main product)
    'oliver': {
        'hummus',  # "Hummus med Kalamata Oliver" — hummus is the product, oliver is flavoring
        'tärnad ost', 'tarnad ost',  # "Tärnad ost i olja Gröna oliver" — cheese product, not olives
        'tapenade',  # olive paste/spread ≠ whole olives
    },
    'mozzarella': {
        'fusii', 'pastakopp',  # ready pasta dishes with mozzarella as topping
    },
    'ricotta': {
        'potatisterrin',  # "Potatisterrin spenat & ricotta" is a potato dish, not ricotta cheese
        'pastasås',       # "Pastasås Ricotta Pecorino 400g ICA Selection" — pasta sauce ≠ ricotta cheese
        'tortellini',     # "Pasta Tortellini Ricottaost och Spenat" — filled pasta ≠ ricotta cheese
    },
    'ricottaost': {
        'tortellini',     # "Pasta Tortellini Ricottaost och Spenat" — filled pasta ≠ ricotta cheese
    },
    'pecorino': {
        'pastasås',       # "Pastasås Ricotta Pecorino 400g ICA Selection" — pasta sauce ≠ pecorino cheese
        'tryffel',        # truffle-flavored pecorino ≠ plain pecorino in cooking
    },
    'gurka': {
        'i lag',        # "Gurka i lag" = pickled, not fresh cucumber
        'tunnskivad',   # "Tunnskivad Gurka" = pickled (ICA/Önos product name)
        'boston',        # "Bostongurka" = sweet pickled relish, not fresh
    },
    'färskost': {
        'tomatsopp',              # "Tomatsopp Färskost ICA" — tomato soup, not cream cheese
        'chips',                  # "Västkustchips Färskost" — chips, not cream cheese
        'dessertost',             # dessert cheese ring
        'salad',                  # "Salad mediterranean" Boursin
        'mediterranean',          # Mediterranean-flavored (Boursin)
        '4 peppar',               # "Färskost 4 Peppar" ≠ explicit pepparrot / other cream cheese flavors
        'pepper',                 # English pepper-flavored variant
        'chevre',                 # goat cheese flavored/spiked cream cheese
        'plant based', 'vegansk', 'växtbaserad',  # plant-based substitutes ≠ dairy cream cheese
    },
    'cream cheese': {
        # Same as färskost — block flavored variants
        'vitlök', 'vitlok',
    },
    'gelatin': {
        'jordgubbsmak',  # "Gelatin Jordgubbsmak Calnort" = flavored jelly mix, not plain gelatin
    },
    'gelatinblad': {
        'jordgubbsmak',  # same product, different keyword form
    },
    'sallad': {
        'wakame',      # "Wakame Sallad" = seaweed salad, not green salad
        'sushi',       # "Sallad Asiatisk Veggie 366g Sushi Daily" = sushi counter salad
        'asiatisk',    # Asian prepared salad ≠ "blandad sallad"
        'provensalsk', # "Provensalsk sallad" = specific herb mix, not generic sallad
    },
    'aubergine': {
        'ganoush', 'baba',  # "Baba Ganoush" is a dip, not raw aubergine
    },
    'kokos': {
        'aminos',      # "Coconut Aminos" — soy sauce alternative, not coconut
        'nick',        # "Nick Coconut" — candy/protein bar, not coconut
        'pineapple',   # "Torkad frukt Mango & Coconut Pineapple" — fruit mix
    },
    'valnöt': {
        'rondelé', 'rondele', 'julien',  # walnut cheese
        'råglevain', 'levain',  # walnut bread
    },
    'päron': {
        'mimosasallad',  # pre-made fruit salad, not fresh pears
    },
    'kronärtskocka': {
        'creme', 'kräm', 'kram',  # "Creme av Kronärtskockor" — spread/dip, not plain artichoke
        'toscana',               # "Kronärtskockor Toscana" — preserved antipasto, not fresh whole artichoke
        'kronärtskockspesto', 'kronartskockspesto',
    },
    'kronartskocka': {
        'creme', 'kräm', 'kram',
        'toscana',
        'kronärtskockspesto', 'kronartskockspesto',
    },
    'cottage cheese': {
        'blåbär', 'blabar',   # "Cottage cheese Blåbär" — flavored, not naturell
        'ananas',              # "Cottage Cheese Ananas Passion" — flavored
        'passion',             # passion fruit flavor
        'mango',               # mango flavor
    },
    'pommes': {
        'friteskrydd', 'friteskrydda', 'kryddmix',  # "Pommes Friteskrydd/a" is seasoning, not fries
    },
    'kryddmix': {
        'stroganoff',           # "Korv Stroganoff Kryddmix 50g Knorr" — too specific for generic kryddmix
        'gulasch',              # "Kryddmix för Gulasch 25g Kamis" — Hungarian stew spice ≠ taco/tandoori kryddmix
        'guacamole',            # "Guacamole Kryddmix 20g ICA" — guacamole spice ≠ enchilada/fajita kryddmix
        'köftekrydda',          # "Köftekrydda Kryddmix 50g Sevan" — köfte spice ≠ generic kryddmix
        'enchilada',            # "Enchilada Kryddmix" ≠ "five spice kryddmix" etc.
    },
    'persika': {
        'mimosasallad',  # same product
    },
    'persikor': {
        'mimosasallad',
    },
    'salami': {
        'pizza',  # same for Swedish spelling
    },
    # Polkagris karameller: block non-polkagris candy products
    'karameller': {
        'kola',     # "Karameller Kola Salmiak" ≠ polkagriskarameller
        'salmiak',  # licorice candy ≠ peppermint candy
        'lakrits',  # licorice ≠ polkagris
    },
    # Truffle: block non-truffle-oil products when recipe wants truffle oil/truffle
    'tryffel': {
        'creme', 'crème',  # "Creme Svamp & tryffel 130g Zeta" — cream product
        'balsamico',       # "Crema Di Balsamico Tryffel" — balsamic cream with truffle flavor
        'vitmögelost',     # "Vitmögelost Tryffel" — cheese with truffle ≠ truffle oil
        'olja',            # "Tryffelolja" — truffle oil ≠ truffle cheese/flavored products
    },
    # Canned stew pork ≠ fresh pork
    'fläsk': {
        'gulasch',  # "Engelsk Gulasch Konserverad Fläsk 300g Pamapol" — canned stew ≠ fresh pork
        'lufttorkad', 'lufttorkade', 'lufttorkat',  # air-dried cured pork ≠ fresh pork
    },
    'flask': {
        'gulasch',  # diacritics-free variant
        'lufttorkad', 'lufttorkade', 'lufttorkat',
    },
    'fläskkött': {
        'gulasch',  # same product, different keyword
        'lufttorkad', 'lufttorkade', 'lufttorkat',
        'hamburgare', 'burger', 'burgare',  # burger patties ≠ raw pork meat
    },
    'flaskkott': {
        'gulasch',
        'lufttorkad', 'lufttorkade', 'lufttorkat',
        'hamburgare', 'burger', 'burgare',
    },
    # Snack chips ≠ actual bruschetta bread
    'bruschetta': {
        'pizza',  # "Bruschetta pizza 150g Maretti" — snack chip ≠ toasted bread
        'vitlök', 'vitlok',  # garlic-flavored bruschetta ≠ plain bruschetta
    },
    # Flavored crostini ≠ plain crostini
    'crostini': {
        'vitlök', 'vitlok',
        'chili',
        'svartpeppar',
    },
    # Frozen pizza with pepperoni ≠ pepperoni sausage
    'pepperoni': {
        'pizza',  # "Pizza pockets Pepperoni", "Pizza Ristorante pepperoni" — frozen pizza ≠ sausage
    },
    # Easter candy ≠ actual eggs
    'påskägg': {
        'godismix', 'godis',  # "Påskägg Godismix 167g Cloetta" — candy ≠ eggs
    },
    'paskägg': {
        'godismix', 'godis',
    },
    # Matcha-flavored drinks ≠ matcha powder
    'matcha': {
        'havredryck', 'ärtdryck', 'artdryck', 'dryck',  # matcha-flavored drinks ≠ matcha powder
    },
    # Pinsa (Italian flatbread pizza) ≠ generic bread types
    'tunnbröd': {'pinsa'},
    'tunnbrod': {'pinsa'},
    'surdegsbröd': {'pinsa'},
    'surdegsbrod': {'pinsa'},
    'formbröd': {'pinsa', 'hamburgerbröd', 'hamburgarbröd', 'hamburgerbrod', 'hamburgarbrod'},
    'formbrod': {'pinsa', 'hamburgerbröd', 'hamburgarbröd', 'hamburgerbrod', 'hamburgarbrod'},
    'rostbröd': {'pinsa'},
    'rostbrod': {'pinsa'},
    # Ready-made pinsa / filled pasta ≠ sliced prosciutto or mortadella
    'mortadella': {'tortellini', 'tortelloni', 'ravioli'},
    'prosciutto': {'pinsa', 'tortellini', 'tortelloni', 'ravioli', 'perline'},
    'skinka': {'pinsa'},
    # Breaded/processed fish fillets ≠ fresh fish fillets
    'fiskfileer': {
        'frasig', 'frasiga', 'sprödbakad', 'sprodbakad',  # breaded products
        'panerad', 'panerade',
    },
    'fiskfilé': {
        'frasig', 'frasiga', 'sprödbakad', 'sprodbakad',
        'panerad', 'panerade',
    },
    'fiskfile': {
        'frasig', 'frasiga', 'sprödbakad', 'sprodbakad',
        'panerad', 'panerade',
    },
    # Fish nuggets ≠ chicken nuggets
    'nuggets': {
        'fisk', 'fish',  # "Fisk Nuggets" / "Fish & Crisp Nuggets" should NOT match chicken nuggets
    },
    # Calabrese frozen pizza ≠ calabrese salami
    'calabrese': {
        'pizza',  # "Pepperoni Cala Calabrese Pizza Fryst" is a frozen pizza, not salami
        'pesto',  # "Pesto Calabrese" is pesto, not calabrese salami
    },
    # Pimiento-stuffed olives ≠ pimientos de padrón (peppers)
    'pimiento': {
        'oliver', 'oliv',  # "Oliver med Pimiento" is olives, not padrón peppers
        'padron',          # "Pimiento Padron" peppers ≠ pimiento-stuffed olives
    },
    'pimientos': {
        'oliver', 'oliv',
        'padron',
    },
    # Hamburger dressing ≠ hamburgerbröd/hamburgare
    'hamburger': {
        'dressing',  # "Original Hamburger Dressing" is not hamburger buns
    },
    'hamburgare': {
        'dressing',  # "Original Hamburgare Dressing" is not a burger patty
        'vego', 'vegansk', 'växtbaserad',  # vegan burger ≠ meat burger
    },
    # Pulled Turkey ≠ pulled vegobitar
    'pulled': {
        'turkey', 'kalkon',  # "Pulled Turkey" is meat, not vegan pulled pieces
    },
    # Nöt (ambiguous: nut vs beef) — block beef products when recipe says "nöt" (usually nuts)
    # Beef recipes use specific compounds: nötkött, nötfärs, nötbog — never bare "nöt"
    'nöt': {
        'biff',  # "Rostbiff Nöt", "Pepparbiff av Nöt"
        'kött',  # "Nöt & Grönt Nötkött Grönsaker"
        'grytbitar',  # "Grytbitar Nöt Sverige"
        'märgben',  # "Märgben av Nöt"
        'bog',  # "Nötbog" as product
    },
    'not': {
        'biff', 'kött', 'grytbitar', 'märgben', 'bog',
    },
    # "Nöt Fruktmix", "Nöt & Bärmix" = nut/fruit snacks, NOT beef
    # These get 'nötkött' via OFFER_EXTRA_KEYWORDS ('nöt' → 'nötkött')
    'nötkött': {
        'fruktmix',      # "Nöt Fruktmix" — nut/fruit trail mix
        'bärmix',        # "Nöt & Bärmix" — nut/berry trail mix
        'oumph',         # "Beef style strips 700g Oumph" — plant-based, not real beef
        'gelatinblad',   # "Gelatinblad av Nöt" — gelatin sheets, not meat
        'fågelmatare',   # "Fågelmatare Nöt Brons" — bird feeder, not food!
        'ekosalami', 'salami',  # cured meat ≠ fresh beef
        'oxpytt',        # "Oxpytt Nötkött Fryst" — convenience meal (pytt i panna)
        'jerky', 'beef jerky', 'torkat kött',  # dried snack ≠ fresh beef
        'märgben',       # marrow bones ≠ beef meat
        'fond du chef',  # stock concentrate ≠ beef meat
    },
    'notkott': {
        'fruktmix', 'bärmix', 'oumph', 'gelatinblad',
        'fågelmatare', 'ekosalami', 'salami', 'oxpytt',
        'jerky', 'beef jerky', 'torkat kött', 'märgben', 'fond du chef',
    },
    # fix_swedish_chars normalizes ASCII `farskost` to the same key as `färskost`,
    # so only a single combined färskost entry should exist here.
    # Specific/filled/pre-flavored pasta excluded from generic "pasta"
    # NOTE: long pasta types (spaghetti, linguine, etc.) NOT blocked here — recipe "pasta"
    # should match ALL regular pasta (both short and long). Only filled/specific/pre-sauced blocked.
    'pasta': {
        'gnocchi',                  # specific product (potato dumpling, not pasta)
        'tortelloni', 'tortellini', # filled pasta
        'ravioli', 'cannelloni',    # filled pasta
        'lasagneplattor',           # specific flat sheet
        'spinaci',                  # flavored pasta (Fettuccine Agli Spinaci)
        'arrabbiata',               # flavored filling (Arrabbiata Tortelloni)
        'formaggi',                 # cheese-filled (Formaggi Tortelloni)
        'ricotta',                  # cheese-filled (Ricotta Spinaci Tortelloni)
        'pomodoro',                 # flavored filling (Tortelloni Pomodoro)
        'wasabi',                   # "Wasabi Pasta" = wasabi paste (tube), not pasta
        'pancetta',                 # "Pasta Mezze Lune Sparris och Pancetta" — meat-filled
        'pesto',                    # "Pasta Pesto 450g ICA" — pre-sauced, not plain pasta
        'sweet chili',              # "Pasta Sweet Chili 450g ICA" — pre-sauced, not plain pasta
        'cacio',                    # "Pasta Cacio e Pepe" — pre-sauced
        'girasoli',                 # "Pasta girasoli svampfyllning" — filled sunflower pasta
        'mezze lune',               # "Pasta Mezze Lune Karl-johansvamp" — filled half-moon
        'fyllning',                 # any filled pasta (svampfyllning, spenatfyllning)
        'chicken',                  # "Tagliatelle chicken 1kg Findus" — frozen ready meal
    },
    'makaroner': {
        'wasabi',                   # "Wasabi Pasta" = wasabi paste (tube), not makaroner
        'pancetta',                # "Pasta Mezze Lune Sparris och Pancetta" — meat-filled, not plain pasta
    },
    # Frozen ready meals with "chicken" in name ≠ plain pasta
    'spaghetti': {'chicken', 'pastakrydda'},  # "Tagliatelle chicken 1kg Findus" via långpasta alias; "Spaghetti Pastakrydda" = spice mix
    'spagetti': {'chicken', 'pastakrydda'},
    'tagliatelle': {'chicken', 'pastakrydda'},
    'linguine': {'chicken', 'pastakrydda'},
    'capellini': {'chicken', 'pastakrydda'},       # "Tagliatelle chicken 1kg Findus" via långpasta alias
    'fettuccine': {'chicken', 'pastakrydda'},
    'fettuccini': {'chicken', 'pastakrydda'},
    'fettucine': {'chicken', 'pastakrydda'},
    'pappardelle': {'chicken'},
    'tagliolini': {'chicken'},
    'bucatini': {'chicken'},
    # Long pasta types excluded from "långpasta" group — specific products only match themselves
    'långpasta': {
        'gnocchi',
        'tortelloni', 'tortellini',
        'ravioli', 'cannelloni',
        'lasagneplattor',
        'chicken',                  # "Tagliatelle chicken 1kg Findus" — frozen ready meal
        'pastakrydda',             # "Spaghetti Pastakrydda" = spice mix, not pasta noodles
    },
    'bönpasta': {
        'spaghetti', 'spagetti',  # "Spaghetti Bönpasta" — pasta shape, not bean paste
        'fusilli',   # "Fusilli Bönpasta"
        'fettucine', 'fettuccine',  # "Fettucine Bönpasta"
        'penne',     # "Penne Bönpasta"
    },
    'bonpasta': {
        'spaghetti', 'spagetti', 'fusilli', 'fettucine', 'fettuccine', 'penne',
    },
    # Flavored eating chocolate ≠ plain baking/cooking chocolate
    # "35 g mörk choklad" wants plain dark chocolate, not "Mango& Passion Mörk Choklad"
    'choklad': {
        'mango', 'passion',     # tropical fruit flavored
        'hallon',               # raspberry flavored
        'pistage',              # pistachio flavored
        'mint', 'kakaonibs',    # mint/nibs flavored
        'havssalt', 'seasalt',  # salted varieties
        'ingefära',             # ginger flavored
        'tranbär',              # cranberry flavored
        'apelsin',              # orange flavored
        'helnöt', 'hassel',     # nut-filled
        'almond',               # almond flavored
        'noblesse',             # candy box brand
        'chocolonely',          # brand name (Tony's Chocolonely)
        'dadlar',               # "Dadlar Mörk Choklad" — chocolate-covered dates, not baking chocolate
        'dessert',              # "Dessert Choklad Kokos" — ready-made dessert, not baking chocolate
        'flingor',              # "Flingor Crunchy Choklad 500g ICA" — cereal, not baking chocolate
        'chokladdryck',         # "Chokladdryck Original O'boy" — drink powder, not baking chocolate
        'majspuffar',           # "Choco corns Fullkornsmajspuffar med choklad" — cereal, not baking chocolate
        'corns',                # "Choco corns" — chocolate cereal brand, not baking chocolate
        'nötspread', 'notspread',  # "Nötspread Hasselnöt & Choklad" — nut spread, not baking chocolate
        'digestive',            # "Digestive Choklad 150g" / "Digestive doppade i mörk choklad" — biscuits, not baking chocolate
        'likör', 'likor',       # "chokladlikör" wants liqueur, not plain chocolate
    },
    # Kakao (cocoa powder) ≠ hazelnut spread containing "kakao" in name
    # "Hasselnötkräm Kakao Duo Nutella" has kakao in name but is a spread, not cocoa powder
    'kakao': {
        'hasselnötkräm', 'hasselnotkram',  # hazelnut spread (Nutella) ≠ cocoa powder
        'likör', 'likor',  # "kakaolikör" wants liqueur, not cocoa powder
    },
    # schweizernöt chocolate ≠ ready-made schweizernöt cake
    'schweizernöt': {
        'kladdkaka',            # "Marabou Schweizernöt kladdkaka 420g Almondy" — frozen cake, not chocolate
        'tårta', 'tarta',       # frozen cake products, not baking chocolate
    },
    # Cheddar cheese sauce/snacks/flavored ≠ solid plain cheddar cheese
    'cheddar': {
        'sauce',          # "Cheddar Cheese Sauce" is liquid, not solid cheese
        'linsbågar', 'linsbaagar',  # "Linsbågar Cheddar Estrella" — lentil chips, not cheese
        'burger toast',   # "Burger Toast Cheddar" — processed cheese product
        'mjukost',        # tube soft-cheese spread ≠ sliced/block cheddar
        'svartpeppar',    # "Cheddar svartpeppar lagrad" — pepper-flavored
        'rökt', 'rokt',   # "Cheddar Rökt" — smoked variant
        'chili',          # "Hamburgerost Cheddar Chili" — chili-flavored
    },
    'cheddarost': {
        'sauce',
        'linsbågar', 'linsbaagar',  # "Linsbågar Cheddar Estrella" — lentil chips, not cheese
        'mjukost',  # tube soft-cheese spread ≠ cheddar cheese for sandwiches/grating
    },
    'brie': {
        'mjukost',  # tube soft-cheese spread ≠ whole/served brie
    },
    'emmentaler': {
        'kex',  # "Kex Mini twist Emmentaler" — snack crackers, not cheese
    },
    # Napoli (origin) — pizzadeg ≠ salame napoli
    'napoli': {
        'pizzadeg', 'deg',  # "Pizzadeg Napoli" is dough, not salami
    },
    # Paprika spice (burk/påse) ≠ fresh bell pepper (st)
    # "Paprika Burk" is ground spice, "1 st Paprika" is fresh vegetable
    'paprika': {
        'burk', 'påse', 'pase',  # spice packaging → not fresh bell pepper
        'tärnad',                # "Tärnad ost i olja Paprika" — cheese cubes, not fresh peppers
        'ost i olja',            # "Tärnad ost i olja Paprika" — cheese in oil, not bell pepper
        'santa maria',           # "Paprika Ekologisk 36g Santa Maria" — spice brand, not fresh
        'vegeta',                # "Paprika Mild malen 100g Vegeta Maestro" — spice brand
        'pesto',                 # "Pesto Paprika 130g ICA" — pesto, not fresh peppers
        'ärter', 'majs',         # "Ärter, Majs & Paprika 600g Apetit" — frozen mix, not fresh paprika
    },
    # Plural form 'paprikor' — mirrors 'paprika' PNB above.
    # PNB checks matched_keyword directly; keyword alias 'paprikor'→'paprika' doesn't resolve for PNB.
    'paprikor': {
        'burk', 'påse', 'pase',
        'tärnad',
        'santa maria',
        'vegeta',
        'pesto',
        'ärter', 'majs',
    },
    # NOTE: Yoghurt matching is handled by check_yoghurt_match() function
    # instead of PNB entries. See YOGHURT TYPE MATCHING section below.
    # Ready-meal köttbullar (with sauce) ≠ plain köttbullar ingredient
    'köttbullar': {
        'gräddsås', 'graddsas',  # "Köttbullar i Gräddsås" is a complete dish
        'potatismos',             # "Köttbullar Potatismos Gräddsås" is a complete meal
        'med mos',                # "Köttbullar med mos 400g Findus" is a complete meal
    },
    'kottbullar': {
        'gräddsås', 'graddsas', 'potatismos', 'med mos',
    },
    # Ponzu/tofu ≠ regular soy sauce
    'soja': {
        'ponzu',  # "Ponzu Citrus Seasoned Soy Sauce" is citrus dipping sauce, not soy
        'tofu',   # "Tofu marinerad soja ingefära" — tofu product, not soy sauce
        'kycklingspett',  # "Kycklingspett Yakitori Soya" — chicken skewer, not soy sauce
    },
    # Beef+vegetable mix ≠ plain vegetables
    'grönsaker': {
        'nötkött', 'notkott',  # "Nöt & Grönt Nötkött Grönsaker" has beef
    },
    'gronsaker': {
        'nötkött', 'notkott',
    },
    # Smokey (flavor) — meat products ≠ BBQ sauce
    'smokey': {
        'ribs', 'spareribs',  # "Ribs Sweet Smokey" is meat, not sauce
    },
    'smoky': {
        'ribs', 'spareribs',
    },
    # BBQ rub (spice blend) ≠ actual ribs/spareribs (meat)
    'ribs': {
        'rub',  # "BBQ rub Ribs 30g Santa Maria" — spice blend, not meat
    },
    'spareribs': {
        'rub',  # "BBQ rub Ribs 30g Santa Maria" — spice, not meat
    },
    # Konjac noodles ≠ egg noodles / regular noodles
    # Instant cup noodles with sauce ≠ plain noodles for cooking
    'nudlar': {
        'konjac',  # "Nudlar Konjac" is shirataki, completely different from wheat noodles
        'biffsmak', 'kycklingsmak',  # "Nudlar med biffsmak" — meat-flavored instant ≠ plain noodles
        'kopp',  # "Nudlar i kopp Soba" — instant cup noodles with sauce
        'champinjonsmak',  # "Nudlar Champinjonsmak" — flavored instant noodles
        'bulgur',  # "Bulgur med Nudlar" — bulgur mix, not plain noodles
    },
    'vetenudlar': {
        'biffsmak', 'kycklingsmak',
    },
    'aggnudlar': {
        'konjac',
    },
    # Chili-roasted sesame seeds ≠ plain sesame seeds
    'sesamfrön': {'chilirostade', 'chilirost'},
    'sesamfron': {'chilirostade', 'chilirost'},
    # Solroskärnor (sunflower seeds) ≠ fröknäcke (crispbread)
    'solroskärnor': {
        'fröknäcke', 'froknacke', 'knäcke', 'knäckebröd',
    },
    'solroskarnor': {
        'fröknäcke', 'froknacke', 'knäcke', 'knäckebröd',
    },
    # Pineapple salsa ≠ vodka drink or dried fruit mix
    'pineapple': {
        'vodka',        # "Salsa Pineapple Vodka" is a cocktail, not food salsa
        'torkad frukt', # "Torkad frukt Mango & Coconut Pineapple" — dried fruit mix, not salsa
    },
    # Indian spice products ≠ indian tonic (beverage)
    'indian': {
        'spice', 'masala', 'tandoori',  # "Garam Masala Indian Spices" ≠ "3 dl indian tonic"
    },
    # Matolja/rapsolja (cooking oil) ≠ smör&rapsolja blends (butter-oil spread)
    # "Normalsaltat Smör & Rapsolja 75%" is NOT cooking oil
    'matolja': {
        'smör',  # butter-oil blends — not suitable as cooking oil
    },
    'rapsolja': {
        'smör',  # same: "Rapsolja med Smörsmak" / "Smör & Rapsolja" ≠ plain rapsolja
        'vitlök', 'vitlok',  # "Rapsolja Vitlök" — garlic-flavored ≠ plain rapeseed oil
    },
    'sesamolja': {
        'woksås', 'woksas',  # sesame-oil wok sauce ≠ plain sesame oil
    },
    # Nut butter (nötsmör) products should not match whole-nut keywords.
    # "Nötsmör Pistasch&cashew" is a spread — recipes wanting "cashewnötter"
    # want whole cashew nuts, not nut butter.
    'nötter': {
        'sourcream', 'onion',  # "Nötter Sourcream & Onion" — snack nuts, not baking nuts
        'honung', 'trippel',   # "Nötter Honung Trippel" — honey-glazed snack nuts
        'salt', 'salta', 'saltade', 'havssalt', 'sea salt',
        'chili', 'jalapeno', 'bbq', 'mango', 'blueberry', 'kokos', 'coconut',
        'rostad', 'rostade', 'rostat', 'torrostade', 'torrostat', 'lättrostade', 'lattrostade',
        'ost', 'julien', 'rondelé', 'rondele', 'råglevain', 'raglevain', 'levain',  # cheese/bread products with nut flavor
    },
    'cashewnötter': {
        'nötsmör', 'nötsmor',
        'sourcream', 'onion', 'jalapeno',  # snack flavors ≠ plain cashews
        'brynt smör',                       # "Cashew Brynt Smör & Havssalt"
        'sea salt',                         # "Cashewnötter Sea Salt"
    },
    'cashew': {
        'nötsmör', 'nötsmor',
        'sourcream', 'onion', 'jalapeno',
        'brynt smör', 'sea salt',
    },
    'jordnötter': {'nötsmör', 'nötsmor'},
    'hasselnöt': {'start'},  # "Hasselnöt 750g Start" — cereal, not plain hazelnuts
    'hasselnötter': {
        'nötsmör', 'nötsmor',
        'start',  # cereal brand, not loose hazelnuts
    },
    # "Gelato Cashew med hasselnötskräm" is ice cream, not hazelnut spread
    'hasselnötskräm': {'gelato'},
    'hasselnötskram': {'gelato'},
    'valnötter': {'nötsmör', 'nötsmor', 'rondelé', 'rondele', 'julien', 'råglevain', 'levain'},
    'valnötskärnor': {'nötsmör', 'nötsmor', 'rondelé', 'rondele', 'julien', 'råglevain', 'levain'},
    'pistagenötter': {
        'nötsmör', 'nötsmor',
        'salt', 'saltade', 'havssalt',  # salted snack pistachios ≠ plain pistachios for baking/cooking
    },  # glass removed — glass normalization handles pistachio ice cream
    'pinjenötter': {'nötsmör', 'nötsmor'},
    # "Original Junior Kyckling" is a cold cut (pålägg), not raw chicken.
    # Block from matching recipes wanting kycklingfilé/kyckling.
    'kycklinglårfilé': {'junior', 'wook', 'wok'},
    'kycklingbröst': {'junior', 'wook', 'wok'},
    # Ready-made frozen pizzas should not match recipes wanting pizza dough/bottnar.
    # "Margherita Pizza" ≠ "4 st Färdiga pizzabottnar"
    'pizza': {
        'margherita', 'capricciosa', 'hawaii', 'vesuvio',
        'kebab', 'quattro', 'calzone', 'funghi',
        'riven ost',  # "Riven ost Pizza" = cheese for pizza, not pizza product
    },
    'pizzabottn': {
        'margherita', 'capricciosa', 'hawaii', 'vesuvio',
        'kebab', 'quattro', 'calzone', 'funghi',
    },
    # Quorn Pepperoni/Tenders/Skivor ≠ quornfärs (different product forms)
    'quornfärs': {'pepperoni', 'tenders', 'skivor', 'chiqin', 'filéer', 'fileer'},
    'quornfars': {'pepperoni', 'tenders', 'skivor', 'chiqin', 'filéer', 'fileer'},
    # "Jordgubbs Granola Glutenfritt" ≠ "jordgubbssylt" (jam, not cereal)
    # PNB key must be the OFFER keyword ('jordgubbs'), not recipe keyword
    'jordgubbs': {'granola'},
    # "Mint&kakaonibs Mörk Choklad 70%" ≠ raw kakaonibs (chocolate bar, not baking ingredient)
    'kakaonibs': {'choklad', 'chocolate', 'mint'},
    # "Hazelnut Cocoa Proteinella Spread" ≠ "silverlöksspread" (savory onion spread)
    'spread': {
        'hazelnut', 'cocoa', 'choklad', 'chocolate',
        'proteinella', 'nutella',
    },
    # "Chicken Hoisin 1p" is a frozen ready meal, not hoisin sauce.
    'hoisinsås': {'chicken'},
    'hoisin': {'chicken'},
    # "Hushålls Medwurst Skivad" is a sausage, not cheese
    'hushållsost': {'medwurst'},
    # Dressing mix ≠ plain örtagårdskrydda
    'örtagård': {'dressingmix'},
    # "Stracciatella Kvarg" = vanilla kvarg with chocolate chips (dessert)
    # ≠ Stracciatella cheese (burrata interior, used in pasta/salad recipes)
    'stracciatella': {'kvarg', 'mousse'},  # "Mousse Stracciatella Protein" = dessert ≠ cheese
    # NOTE: Kvarg matching moved to check_kvarg_match() function — handles all flavored variants
    # "Barkis Vallmo" (baked bread with poppy seeds) ≠ raw vallmofrö for baking
    'vallmo': {'barkis'},
    # NOTE: 'havredryck' PNB moved to full entry below (with all flavored variants)
    # "Syrad Grädde Visp- & Kokbar" ≠ vispgrädde or regular grädde
    # Syrad grädde is a cultured cream product — only match when recipe explicitly says "syrad"
    # Flavored matgrädde (Paprika Chili, Tre Ostar) / protein pudding
    # ≠ plain matlagningsgrädde
    'grädde': {'syrad', 'paprika chili', 'tre ostar', 'proteinpudding'},
    'gradde': {'syrad', 'paprika chili', 'tre ostar', 'proteinpudding'},
    'matlagningsgrädde': {'proteinpudding'},
    'matlagningsgradde': {'proteinpudding'},
    # Flavored oat cream ≠ plain havregrädde
    'havregrädde': {'lök', 'lok'},
    # NOTE: fond PNB blockers removed — replaced by _FOND_TYPE_CONTEXT validation
    # in recipe_matcher.py which is context-aware (typed vs generic fond).
    # Flavored mayonnaise ≠ plain majonnäs
    # "1 dl majonnäs" wants plain mayo, not garlic/chili/truffle/mango flavored
    'majonnäs': {
        'garlic', 'vitlök', 'vitloks',   # "Roasted Garlic Mayonnaise", "Aioli Garlic"
        'chili', 'sriracha', 'jalapeno',  # spicy variants
        'tryffel', 'tryffelmayo',         # truffle mayo
        'mango', 'habanero',              # fruit/hot variants
        'citron',                          # lemon mayo
        'korean',                          # "Majonnäs Korean Chili"
        'gurk',                            # "Gurkmajonnäs" = dressing, not mayo
        'cactus', 'lime',                  # "Cactus/lime Mayo"
    },
    'majonnas': {
        'garlic', 'vitlök', 'vitloks', 'chili', 'sriracha', 'jalapeno',
        'tryffel', 'tryffelmayo', 'mango', 'habanero', 'citron',
        'korean', 'gurk', 'cactus', 'lime',
    },
    # "Kyckling Wook" is a ready-made meal, not raw chicken fillet
    # "Original Junior Kyckling" is a spreadable pâté, not raw chicken fillet
    # "Äggjaktsägg kyckling" is Easter egg candy (påskgodis), not chicken
    'kycklingfilé': {
        'wook', 'wok', 'junior', 'äggjaktsägg', 'aggjaktsagg',
        'stekt', 'färdiglagad',  # pre-cooked deli chicken ≠ raw fillet
        'pålägg', 'palagg',      # sliced cold cuts ≠ raw fillet
        'dumpling', 'dumplings',  # dumplings ≠ raw chicken fillet
        'thaikryddad',            # "Thaikryddad kyckling" — pre-seasoned
        'örtkryddad', 'ortkryddad',  # "Kyckling Örtkryddad" — herb-seasoned
        'bbq',                    # "Kycklinglårfilé BBQ" / "BBQ Black Garlic"
        'marinerad',              # "Kycklingbröstfilé strimlad marinerad"
        'korean',                 # "Korean Style" marinerad
        'thai strimlad',          # "Kyckling Färsk Thai Strimlad"
        'pastramibröst', 'pastramibrost',  # deli pastrami ≠ raw fillet
        'örtmarinerad', 'ortmarinerad',    # deli herb-marinated slices
        'sweet chili',            # "Sweet chili kyckling Fryst" — pre-seasoned ready meal
    },
    'kycklingfile': {
        'wook', 'wok', 'junior', 'äggjaktsägg', 'aggjaktsagg',
        'stekt', 'färdiglagad',
        'pålägg', 'palagg',
        'dumpling', 'dumplings',
        'thaikryddad', 'örtkryddad', 'ortkryddad', 'bbq',
        'marinerad', 'korean', 'thai strimlad',
        'pastramibröst', 'pastramibrost', 'örtmarinerad', 'ortmarinerad',
        'sweet chili',            # "Sweet chili kyckling Fryst" — pre-seasoned ready meal
    },
    'kyckling': {
        'wook', 'wok', 'junior', 'äggjaktsägg', 'aggjaktsagg',
        'stekt', 'färdiglagad',
        'pålägg', 'palagg',
        'dumpling', 'dumplings',  # dumplings ≠ raw chicken
        'bacon',  # "Bacon Kyckling Skivad" — processed, not raw chicken
        'thaikryddad', 'örtkryddad', 'ortkryddad', 'bbq',
        'marinerad', 'korean', 'thai strimlad',
        'pastramibröst', 'pastramibrost', 'örtmarinerad', 'ortmarinerad',
        'presentpåse', 'presentpase', 'presesentpåse', 'presesentpase',  # gift bag
        'sweet chili',            # "Sweet chili kyckling Fryst" — pre-seasoned ready meal
    },
    # "Kyckling Örtkryddad" is seasoned chicken, not herb sauce/seasoning
    'örtkryddad': {'kyckling'},
    'ortkryddad': {'kyckling'},
    # "Isberg Frisé" is frisée lettuce (curly salad mix), not iceberg
    'isberg': {'frisé', 'frise'},
    # Blend oils containing olivolja as a component ≠ pure olive oil
    'olivolja': {'raps', 'solros'},
    # Spreads/margarin with "smör" in the name ≠ real butter (smör = 80%+ fat)
    # Bregott (smör&raps), Flora ("med Smör 70%"), Gårdsgoda, etc. are NOT butter.
    # Herb butters (persiljesmör, vitlökssmör) are serving condiments, not cooking butter.
    'smör': {
        'raps',       # Bregott "Smör & Raps", "Smör&rapsolja", Gårdsgoda Smör & Raps, etc.
        'rapsolja',   # "Smör & Rapsolja 75%", "Smör-&rapsolja Flytande"
        '70%',        # Flora "Normalsaltat med Smör 70%", "Havssalt med Smör 70%" (real butter is 80%+)
        '75%',        # Gårdsgoda/Grådö Bre 75% spread products ≠ butter
        '57%',        # Gårdsgoda Mellan 57% spread ≠ butter
        'havssalt',   # Flora "Havssalt med Smör 70%" (also caught by '70', but belt-and-suspenders)
        'persilje',   # Persiljesmör (herb butter condiment, not cooking butter)
        'vitlöks',    # Vitlökssmör (garlic herb butter condiment)
        'smörsmak',   # "Rapsolja med Smörsmak" — oil with butter flavor
        # glass/triumf removed — glass normalization blocks "Farbror Arnes Brynt smör" ice cream
    },
    'smor': {
        'raps', 'rapsolja', '70%', '75%', '57%', 'havssalt', 'persilje', 'vitloks', 'smorsmak',
    },
    # Dried passion fruit snack ≠ fresh passion fruit in desserts/candying
    'passionsfrukt': {
        'torkad',
    },
    # Flavored meringues ≠ plain maräng/maränger
    'maräng': {'choklad', 'kolasmak', 'polka', 'jordgubb'},
    'maranger': {'choklad', 'kolasmak', 'polka', 'jordgubb'},
    'maränger': {'choklad', 'kolasmak', 'polka', 'jordgubb'},
    # Garlic-flavored products ≠ fresh garlic
    # "Le Roulé Vitlök" (cheese), "Bruschetta Vitlök" (spread), "Rapsolja Vitlök" (oil)
    'vitlök': {
        'roule',                 # Le Roulé garlic cream cheese (é normalized to e by fix_swedish_chars)
        'bruschetta',            # garlic bruschetta spread
        'rapsolja',              # garlic-flavored rapeseed oil
        'marinerad', 'marinerade',  # marinated garlic cloves ≠ neutral jarred garlic
        'tofu',                  # "Tofu Chili Vitlök" — tofu product, not fresh garlic
        'dumpling', 'dumplings',  # dumpling filling/flavor ≠ fresh garlic
    },
    'vitlok': {
        'roule', 'bruschetta', 'rapsolja', 'marinerad', 'marinerade', 'tofu', 'dumpling', 'dumplings',
    },
    # Compound forms of vitlök — same blockers apply
    'vitlöksklyftor': {
        'roule', 'bruschetta', 'rapsolja', 'marinerad', 'marinerade', 'tofu', 'dumpling', 'dumplings',
    },
    'vitloksklyftor': {
        'roule', 'bruschetta', 'rapsolja', 'marinerad', 'marinerade', 'tofu',
    },
    'vitlöksklyfta': {
        'roule', 'bruschetta', 'rapsolja', 'marinerad', 'marinerade', 'tofu',
    },
    'vitloksklyfta': {
        'roule', 'bruschetta', 'rapsolja', 'marinerad', 'marinerade', 'tofu',
    },
    'vitlöksklyft': {
        'roule', 'bruschetta', 'rapsolja', 'marinerad', 'marinerade', 'tofu',
    },
    'vitloksklyft': {
        'roule', 'bruschetta', 'rapsolja', 'tofu',
    },
    # Parsley-flavored products ≠ fresh parsley
    'persilja': {
        'kryddsmör', 'kryddsm\u00f6r',  # "Kryddsmör Persilja" — herb butter
        'bruschetta',                    # "Bruschetta Vitlök & persilja" — spread
    },
    'persilje': {
        'torsk',  # "Torsk persilje & citronsmör" — fish product, not parsley
    },
    # Green pepper-flavored products ≠ actual green peppercorns
    'grönpeppar': {
        'anklevermousse',  # "Anklevermousse Med Grönpeppar" — pâté, not peppercorns
        'mousse',          # any mousse with grönpeppar flavor
    },
    'gronpeppar': {
        'anklevermousse', 'mousse',  # normalized form
    },
    # Bulgur in ready-made salads ≠ dry bulgur
    'bulgur': {
        'laxsallad',   # "Laxsallad med Bulgur XL 450g ICA" — fish salad, not dry grain
        'sallad med',  # any prepared salad with bulgur
    },
    # Smoked tofu keyword matching bacon/charcuterie
    'alspånsrökt': {
        'bacon',        # "Bacon Björk och Alspånsrökt 125g Scan" — meat product
        'cognacsmedwurst',  # "Cognacsmedwurst Alspånsrökt 300g ICA" — sausage
        'korv',         # any smoked sausage
        'skinka',       # smoked ham
    },
    'alspansrokt': {
        'bacon', 'cognacsmedwurst', 'korv', 'skinka',  # normalized
    },
    # Tofu in fish products ≠ actual tofu
    'tofu': {
        'silkestofu',   # silken tofu — completely different texture
        'silkesmjuk',   # "Tofu silkesmjuk" — same silken-tofu family in live offer wording
        'pesto',        # "Pesto Con Tofu Vegansk" — pesto sauce, not tofu
        'fiskexporten',  # "Tofu i drömsås/senapsgravad" from Fiskexporten — fish product
        'drömsås',       # "Tofu i drömsås" — fish in sauce, not tofu
        'dromsas',       # normalized
        'senapsgravad',  # "Tofu senapsgravad" — fish product, not tofu
    },
    # Persiljestjälk keyword also needs kryddsmör block (persilja PNB doesn't cover it)
    'persiljestjälk': {
        'kryddsmör',    # "Kryddsmör Persilja 65g Biggans" — herb butter ≠ fresh parsley stems
        'bruschetta',   # "Bruschetta Vitlök & persilja" — spread
    },
    'persiljestjalk': {
        'kryddsmör', 'bruschetta',  # normalized
    },
    # Creme products ≠ fresh mushrooms
    'svamp': {
        'creme',    # "Creme Svamp & tryffel 130g Zeta" — cream product, not mushrooms
        'créme',    # accent variant
    },
    'kantareller': {
        'creme', 'créme', 'kantarellpesto',  # same block for kantareller keyword
    },
    'kantarell': {
        'creme', 'créme', 'kantarellpesto',
    },
    # Crisp-fried onions should not fan out to sausages just because the flavor
    # name includes "rostad lök".
    'rostadlök': {
        'korv', 'kryddkorv',
    },
    # Protein milkshakes ≠ cooking milk
    'mjölkdryck': {
        'protein',      # "Protein Mjölkdryck Blåbär 5dl Arla" — sports drink, not cooking milk
    },
    # Flavored date snacks ≠ plain baking dates
    'dadlar': {
        'fizzy',        # "Dadlar Fizzy Bottle 125g Dave & Jon's" — candy-coated dates
        'sweet peach',  # "Dadlar Sweet Peach" — flavored snack
        'salted caramel', # "Dadlar Salted Caramel Peanuts" — snack mix
        'pepparkakssmak', # "Dadlar med Pepparkakssmak" — flavored
        'sour cola',    # "Dadlar Sour Cola" — candy dates
        'saltlakrits',  # "Dadlar Saltlakrits" — candy dates
        's-märke',      # "Dadlar S-Märke Sur Citron" — candy dates
        'chokladboll',  # "Dadlar Chokladboll" — candy dates
        'kanelbulle',   # "Dadlar Kanelbulle" — candy dates
        'peacemärke',   # "Dadlar Peacemärke" — candy dates
    },
    # Roasted snack chickpeas ≠ canned/dried cooking chickpeas
    # NOTE: extractor commonly returns the accented form "kikärter", so keep both.
    'kikärter': {
        'rostade',      # "Kikärter rostade saltade 180g Besler" — snack, not cooking chickpeas
        'rostad',       # singular
    },
    'kikarter': {
        'rostade',
        'rostad',
    },
    'kikärtor': {
        'rostade',      # "Kikärtor Rostade vita/gula 150g Tadim" — snack, not cooking chickpeas
        'rostad',       # singular
    },
    # Korianderblad ≠ korianderfrön (leaves ≠ seeds)
    'korianderfrön': {
        'blad',         # "Korianderblad 20g Risberg" — leaves, recipe wants seeds
    },
    'korianderfron': {
        'blad',         # normalized
    },
    # Flavored/specialty oat drinks ≠ plain oat drink for cooking
    # Only plain naturell/mellan/ekologisk should match recipe "havredryck"
    'havredryck': {
        # Flavored
        'choklad',      # "Havredryck Choklad 1l" — chocolate flavored
        'matcha',       # "Havredryck Matcha" — tea flavored
        'strawberry',   # "Havredryck Matcha Strawberry" — berry flavored
        'vanilj',       # "Havredryck Vanilj 2,6% 1l Oatly" — vanilla flavored
        'vanilla',      # "Barista Nutty Vanilla" — vanilla flavored
        'hasselnöt',    # "Barista Hasselnöt" — hazelnut flavored
        'hasselno',     # normalized
        'lönnsirap',    # "Barista Lönnsirap Valnötter" — maple syrup flavored
        'lonnsirap',    # normalized
        'salt karamell', # "Barista Salt Karamell" — caramel flavored
        'dumle',        # "Havredryck Dumle Barista" — candy flavored
        'iskaffe',      # "Havredryck Iskaffe Vanilj" — iced coffee
        'churros',      # "Havredryck iKaffe Churros" — pastry flavored
        'popcorn',      # "Havredryck iKaffe Popcorn" — popcorn flavored
        'kakao',        # "Proteinhavredryck Choko Kakao" — cocoa flavored
        'caramel',      # "Proteinhavredryck Salted Caramel" — caramel
        # Coffee-specific (not for cooking)
        'barista',      # "Havredryck Barista" — coffee-optimized, not cooking
        'ikaffe',       # "Havredryck iKaffe" — coffee-specific
        'professional', # "Havredryck Professional Barista" — café use
    },
    # Explicit barista oat drink should still avoid dessert/flavor variants.
    'havredryckbarista': {
        'choklad',
        'matcha',
        'strawberry',
        'vanilj',
        'vanilla',
        'hasselnöt',
        'hasselno',
        'lönnsirap',
        'lonnsirap',
        'salt karamell',
        'dumle',
        'iskaffe',
        'churros',
        'popcorn',
        'kakao',
        'caramel',
        'nutty',
    },
    # Honey-flavored products ≠ actual honey
    'honung': {
        'grillkrydda',  # "Grillkrydda Honung 98g" — BBQ spice, not honey
    },
    # Pistachio-flavored products ≠ pistachio nuts
    # Product keyword "pistage" matches "pistagenötter" via substring
    'pistage': {
        'bar ',   # "Bar Pistage 80g" — energy bar, not nuts
        'halva',  # "Halva Pistage 350g" — confection, not nuts
        # glass removed — glass normalization handles pistachio ice cream
    },
    # Sushi with salmon ≠ raw salmon fillet
    # Najad salmon ≠ raw salmon fillet (marinated/prepared product)
    'lax': {
        'sushi',  # "Sushi Lax Nigiri" — pre-made sushi, not raw salmon
        'najad',  # "Lax najad" — marinated prepared salmon, not raw fillet
    },
    # Ready-made sushi products ≠ raw sushi-grade salmon
    'sushilax': {
        'nigiri',  # "Sushi Lax Nigiri" — complete dish, not raw fish
        'roll',    # "Sushi Lax Crunch Roll" — complete dish
        'meny',    # "Sushi Meny Duo Lax" — complete meal
        'seared',  # "Sushi Seared Lax" — already cooked
    },
    # Herring products with spring onion flavor ≠ actual spring onion
    'salladslök': {
        'sill',  # "Sill Asian Fusion Salladslök" — herring product
    },
    'salladslok': {
        'sill',
    },
    # Salt licorice flavored products ≠ actual salt licorice sauce
    'saltlakrits': {
        'dadlar',  # "Dadlar Saltlakrits 125g" — candy dates, not sauce
    },
    # Cracker products with "Flingsalt" ≠ actual flake salt
    'flingsalt': {
        'knäcke',       # "Sesamknäcke Flingsalt 150g" — cracker, not salt
        'sesamknäcke',  # belt-and-suspenders
    },
    # Canned tuna in broth ≠ actual bouillon
    'buljong': {
        'tonfisk',  # "Tonfisk i buljong 120g" — canned tuna, not bouillon
    },
    'buljongtärning': {
        'tonfisk',  # "Tonfisk i buljong 120g" — canned tuna, not bouillon cube
    },
    'buljongtärningar': {
        'tonfisk',
    },
    'buljongtarning': {
        'tonfisk',
    },
    'buljongtarningar': {
        'tonfisk',
    },
    # Baguette spread with tuna ≠ raw tuna
    'tonfisk': {
        'baguetteröra',  # "Baguetteröra med Tonfisk 175g ICA" — prepared spread, not canned/fresh tuna
        'baguetterora',
    },
    # Prepared clam dish with tomatoes ≠ plain raw vongole
    'vongole': {
        'pomodorini',  # "Vongole con pomodorini" — ready-made clam dish, not raw shellfish
    },
    # Pre-filled wraps ≠ empty wraps/tortillas
    'wrap': {
        'kyckling',   # "Wrap Kyckling BBQ" — filled wrap, not empty
        'bbq',        # "Wrap Kyckling BBQ"
        'korean',     # "Wrap Kyckling Korean"
    },
    # Flavored drinks ≠ actual syrup/ingredient
    'lönnsirap': {
        'havredryck',  # "Havredryck Barista Lönnsirap" — oat drink, not syrup
        'dryck',       # belt-and-suspenders
    },
    'lonnsirap': {
        'havredryck',
        'dryck',
    },
    # Herring (sill) ≠ caviar/roe/flavored sill products
    'sill': {
        'caviarmix',      # "Caviarmix röd rom av sill" — roe product, not herring
        'kaviar',         # "Årets sill Kalles kaviar" — flavored sill, not plain inläggningssill
        'rom',            # "röd rom av sill" — roe, not herring fillet
        'ceviche',        # "Årets Sill Ceviche" — flavored
        'kräftgravad', 'kraftgravad',    # "Kräftgravad sill" — flavored
        'kräftmarinerad', 'kraftmarinerad',  # "Kräftmarinerad Sill" — flavored
        'ansjoviskryddad',  # "Ansjoviskryddad Sill" — flavored
        'asian fusion',   # "Sill Asian Fusion Chili Ingefära" — flavored
        # Pre-seasoned sill ≠ plain inläggningssill. PNB safe: if ingredient text says
        # "senapsmarinerad"/"rökt"/"gravad" etc., that word IS in ingredient → not blocked.
        'brynt smör', 'brynt smor',  # browned-butter flavor variant, not plain inläggningssill
        'ingefära', 'ingefara',      # ginger-flavored sill
        'lime',                      # citrus-flavored sill
        'senapsmarinerad',  # "Sill Senapsmarinerad 500g Abba" — mustard-marinated
        'senapsgravad',     # mustard-cured sill variant
        'rökt', 'rokt',     # "Rökt Sill" — smoked herring ≠ plain inläggningssill
        'gravad',           # "Gravad Sill" — cured sill ≠ plain inläggningssill
    },
    # Artichoke hearts should surface preserved/jarred artichoke products, not fresh whole artichokes
    # or prepared spreads/antipasto lines. Exact "kronärtskockshjärtan" products still pass.
    'kronärtskockshjärta': {
        'färsk', 'farsk', 'klass',
        'creme', 'kräm', 'kram',
        'toscana',
    },
    'kronartskockshjarta': {
        'färsk', 'farsk', 'klass',
        'creme', 'kräm', 'kram',
        'toscana',
    },
    # Plocksallat ≠ seed packets / grow-your-own products
    # 'sallat' offers get 'plocksallat' via reverse parent — block seed/garden products
    'plocksallat': {'nelson', 'garden', 'frö', 'frön', 'seed', 'sådd'},
    # Prepared sweet/soured red cabbage ≠ fresh raw rödkål
    'rödkål': {'klassisk', 'dansk'},
    'rodkal': {'klassisk', 'dansk'},
    # ---- Vegan substitutes ≠ animal-product recipes ----
    # PNB blocks when 'vego'/'vegansk' IS in product name but NOT in ingredient text.
    # Vegan recipes (ingredient says "vegofärs") have 'vego' in text → NOT blocked.
    'köttfärs': {'vego', 'vegansk', 'soja', 'växtbaserad', 'fiskfärs'},  # fish mince ≠ meat mince
    'kottfars': {'vego', 'vegansk', 'soja', 'växtbaserad', 'fiskfärs', 'fiskfars'},
    'hushållsfärs': {'vego', 'vegansk', 'soja', 'växtbaserad'},
    'hushallsfars': {'vego', 'vegansk', 'soja', 'växtbaserad'},
    'färs': {'vego', 'vegansk', 'soja', 'växtbaserad', 'fiskfärs'},  # fish mince ≠ meat mince
    'fars': {'vego', 'vegansk', 'soja', 'växtbaserad', 'fiskfärs', 'fiskfars'},
    'chorizo': {
        'salami',    # sliced salami-style chorizo ≠ cooking chorizo
        'fuet',      # fuet = dry-cured Spanish sausage, not cooking chorizo
        'pamplona',  # pamplona chorizo = cured charcuterie, not cooking chorizo
        'iberico',   # ibérico = cured/charcuterie format, not cooking chorizo
    },
    'bacon': {
        'vego', 'vegansk', 'växtbaserad',
        'kalkon', 'kalkonbacon',  # turkey bacon ≠ pork bacon
        'lyckans ost',  # cheese product with bacon flavor ≠ bacon slices
    },
    'schnitzel': {'vego', 'vegansk', 'växtbaserad'},
    # ---- Frozen vegetable mixes ----
    # Cross-vegetable blockers for classic combos (e.g., "Ärtor & Morötter")
    'ärtor': {'morötter', 'morot', 'majs'},    # "Ärtor & Morötter" / "Ärter, Majs & Paprika" mix ≠ plain peas
    'artor': {'morötter', 'morot', 'majs'},
    'ärta': {'vegonuggets'},                   # pea-based nuggets ≠ fresh/plain peas
    'arta': {'vegonuggets'},
    'majs': {'ärtor', 'ärter', 'paprika'},     # "Ärter, Majs & Paprika" mix ≠ plain corn
    'morötter': {'ärtor', 'ärter', 'syrade', 'sallad', 'surkål', 'soppa', 'riven'},
    'morot': {'ärtor', 'ärter', 'syrade', 'sallad', 'surkål', 'kanin', 'soppa', 'riven'},
    'morotter': {'ärtor', 'ärter', 'syrade', 'sallad', 'surkål', 'kanin', 'soppa', 'riven'},
    # ---- Processed/prepared products ----
    # NOTE: 'spenat' stuvad entry merged into existing spenat PNB
    # NOTE: 'koriander' blad entry merged into existing koriander PNB
    # ---- Flavored oils ----
    # NOTE: 'olivolja' limone entry merged into existing olivolja PNB
    # NOTE: 'rapsolja' vitlök entry merged into existing rapsolja PNB
    # ---- Specialty vinegar / herb-in-vinegar ----
    'vinäger': {'dragonblad', 'crema', 'balsamico', 'chips'},  # chips / crema ≠ cooking vinegar
    'vinager': {'dragonblad', 'crema', 'balsamico', 'chips'},
    # ---- Flavored curry / snack bars ----
    # NOTE: 'curry' mango entry merged into existing curry PNB
    'blåbär': {'boost', 'hallon'},  # "Berry Boost Blåbär" snack bar; "Hallon & blåbär" mix ≠ pure blåbär
    # Berry mixes for recipes should not fall through to nut/berry trail mixes.
    'bärmix': {'nöt', 'not'},
    # ---- Bean products in sauce ----
    'bönor': {'tomatsås', 'tomatsas'},    # "Vita Bönor i Tomatsås" ≠ plain cooked beans
    'bonor': {'tomatsås', 'tomatsas'},
    # ---- Thickener products ----
    'majsstärkelse': {'redning'},          # "Redning Brun Maizena" — brown roux ≠ pure cornstarch
    # Flavored yoghurt matched via fruit keyword (not caught by check_yoghurt_match)
    'havtorn': {'yoghurt', 'gurt'},  # "Yoghurt Havtorn 2.7%" ≠ fresh havtorn berries
    # ---- Arla review 2026-03-26 ----
    # Smoked fläskfilé ≠ raw fläskfilé
    'fläskfilé': {'rökt', 'rokt'},
    'flaskfile': {'rökt', 'rokt'},
    # Marinated/flavored fläskytterfilé ≠ plain
    'fläskytterfilé': {'mörmarinerad', 'mormarinerad', 'medaljonger', 'vitlök & peppar'},
    'flaskytterfile': {'mörmarinerad', 'mormarinerad', 'medaljonger'},
    # BBQ/grillmarinerad fläskkarré ≠ plain
    'karré': {'grillmarinerad', 'bbq', 'asian bbq', 'vedrökt'},
    'karre': {'grillmarinerad', 'bbq', 'asian bbq', 'vedrökt'},
    'fläskkarré': {'grillmarinerad', 'bbq', 'asian bbq', 'vedrökt'},
    'flaskkarre': {'grillmarinerad', 'bbq', 'asian bbq', 'vedrökt'},
    # Seasoned chicken drumsticks ≠ plain kycklingben
    'kycklingben': {'bbq', 'grillkrydda', 'grillkryddad', 'kryddmarinerad'},
    # Pre-seasoned torsk ≠ plain (all keyword forms)
    'torskfilé': {'citronsmör', 'citronsmor', 'dillsmör', 'dillsmor', 'laxtärningar', 'laxtarningar'},
    'torskfile': {'citronsmör', 'citronsmor', 'dillsmör', 'dillsmor', 'laxtärningar', 'laxtarningar'},
    'torskrygg': {'citronsmör', 'citronsmor', 'dillsmör', 'dillsmor', 'laxtärningar', 'laxtarningar'},
    'torsk': {'citronsmör', 'citronsmor', 'dillsmör', 'dillsmor', 'laxtärningar', 'laxtarningar'},
    # Flavored halloumi ≠ plain
    'halloumi': {'tryffel', 'chili'},
    # Le Roulé-style cream cheese ≠ generic hard/riven ost
    'ost': {'roule'},
    # Flavored vitmögelost ≠ plain
    'vitmögelost': {'tryffel'},
    'vitmogelost': {'tryffel'},
    # Blue cheese spread ≠ actual ädelost wedge/block
    'ädelost': {'mjukost'},
    'adelost': {'mjukost'},
    # Sherry style "manzanilla" ≠ manzanilla olive products
    'manzanilla': {'oliver'},
    # Plain chèvre/getost should not match chèvre-flavored cream cheese
    'chevre': {'färskost', 'farskost', 'kavli'},
    # Flavored getost ≠ plain
    'getost': {'honung', 'färskost', 'farskost'},
    # Flavored mjölkchoklad ≠ plain baking chocolate
    'mjölkchoklad': {'dadlar', 'caramel', 'påskgodis', 'paskgodis', 'gold bunny', 'salty', 'eggs', 'digestive', 'hasselnöt', 'hasselnot'},
    'mjolkchoklad': {'dadlar', 'caramel', 'påskgodis', 'paskgodis', 'gold bunny', 'salty', 'eggs', 'digestive', 'hasselnöt', 'hasselnot'},
    # Svart kardemumma ≠ green kardemumma
    'kardemumma': {'svart'},
    'kardemummakärnor': {'svart'},
    'kardemummakarnor': {'svart'},
    # Flavored balsamico crema ≠ plain
    'balsamico': {'tryffel', 'ingefära', 'ingefara', 'fikon'},
    # Flavored pesto ≠ plain basil pesto
    'pesto': {'arrabbiata', 'kantarellpesto', 'kronärtskockspesto', 'kronartskockspesto'},
    # Flavored pastasås ≠ plain
    'pastasås': {'arrabbiata'},
    'pastasas': {'arrabbiata'},
    # Smoked musslor ≠ fresh blåmusslor
    'musslor': {'rökta', 'rokta', 'rökt', 'rokt'},
    'blåmusslor': {'rökta', 'rokta', 'rökt', 'rokt', 'i vatten', 'i lake'},
    'blamusslor': {'rökta', 'rokta', 'rökt', 'rokt', 'i vatten', 'i lake'},
    # Rökt paprikapulver ≠ vanlig paprikapulver (and vice versa)
    # NOTE: 'paprikapulver' already has 'tärnad'/'ärtor' above — this adds 'rökt'
    # The reverse case (recipe wants rökt, gets plain) can't be handled by PNB.
    # Sardeller med chili ≠ plain sardeller
    'sardeller': {'chili'},
    'sardellfileer': {'chili'},
    # Gochujang mayo ≠ gochujang paste
    'gochujang': {'mayo', 'chilimayo'},
    # Sambal badjak ≠ sambal oelek (block cross-matching)
    'sambal': {'badjak'},
    # Teriyaki sauce should not broaden to jerky / ready meals / wok sauces.
    'teriyakisås': {
        'jerky', 'beef jerky', 'torkat kött', 'torkat kott',
        'tempeh',
        'woksås', 'woksas', 'wok ',
        'dafgårds', 'dafgards', 'mama chin', 'bbq',
        'fryst', 'glazed',
    },
    'teriyakisas': {
        'jerky', 'beef jerky', 'torkat kött', 'torkat kott',
        'tempeh',
        'woksås', 'woksas', 'wok ',
        'dafgårds', 'dafgards', 'mama chin', 'bbq',
        'fryst', 'glazed',
    },
    'teriyaki': {
        'jerky', 'beef jerky', 'torkat kött', 'torkat kott',
        'tempeh',
        'woksås', 'woksas', 'wok ',
        'dafgårds', 'dafgards', 'mama chin', 'bbq',
        'fryst', 'glazed',
    },
    # Anklevermousse flavored ≠ plain
    'anklevermousse': {'cognac', 'grönpeppar', 'gronpeppar'},
    # Kebab pizza/sauce ≠ kebab meat
    'kebab': {'pizza', 'vitlöksås', 'vitloksas', 'feferoni', 'pirog'},
    # Korv kryddmix ≠ actual korv
    'korv': {'kryddmix', 'stroganoff kryddmix', 'stroganoff'},
    # Sprödpanerade räkor ≠ råa räkor; räkost (cheese spread) ≠ actual shrimp
    'räkor': {'sprödpanerade', 'sprodpanerade', 'panerade', 'räkost', 'lyckans'},
    'rakor': {'sprödpanerade', 'sprodpanerade', 'panerade', 'räkost', 'lyckans'},
    'räka': {'räkost', 'lyckans'},
    # Flavored ost matching generic ost/svecia keyword
    'svecia': {
        'rökt', 'rokt',           # smoked cheese
        'red hot', 'pepper jack',  # spicy cheese
        'chili',                   # chili cheese
        'i olja',                  # marinated cheese cubes
    },
    # Breaded/snack camembert products are not plain camembert cheese.
    'camembert': {'panerad', 'bites'},
    # Våfflor/bullar from Liba Bröd matching generic "bröd"
    'bröd': {'våfflor', 'vafflor', 'maamoul', 'mjölkbullar', 'mjolkbullar', 'pinsa'},
    'brod': {'våfflor', 'vafflor', 'maamoul', 'mjölkbullar', 'mjolkbullar', 'pinsa'},
    # Deli kalkon products ≠ raw kalkonfilé
    'kalkon': {'pastramibröst', 'pastramibrost', 'örtmarinerad', 'ortmarinerad'},
    # Kanin (rabbit) ≠ toys/decorations — Easter products matching rabbit recipes
    'kanin': {
        'filt', 'snuttefilt',  # baby blankets
        'keramik',             # ceramic decorations
        'korg',                # baskets
        'teddykompaniet',      # toy brand
    },
    # NOTE: 'mandel' caramel entry merged into existing mandel PNB above
    # --- Batch 4-5 review fixes ---
    # Ready-made products matching raw ingredient keywords
    'västerbottensost': {'bites'},  # "Västerbottenost crispy bites" = snack ≠ cheese
    'vasterbottensost': {'bites'},
    'vindruvor': {'smoothie'},  # "Fruktsmoothie Green Dream Äpple Vindruvor" ≠ fresh grapes
    'piadina': {'ristorante'},  # "Ristorante Piadina 4 formaggi" = frozen pizza ≠ plain flatbread
    'pizzadeg': {'sauce'},  # "Pizza sauce Tomat & Örter" ≠ pizza dough
    'kex': {'frukost'},  # "Frukost Crackers Göteborgs kex" ≠ digestive/baking kex
    # Plain digestive crumbs/biscuits should not broaden to chocolate/cocoa-filled variants.
    'digestive': {'choklad', 'chocolate', 'cocoa', 'cream'},
    'kondenserad': {'osötad', 'osotad'},  # "Kondenserad Mjölk Osötad" ≠ sötad kondenserad mjölk
    'kondenseradmjölk': {'osötad', 'osotad'},
    'kondenseradmjolk': {'osötad', 'osotad'},
    # Anis (anise) ≠ Stjärnanis (star anise) — different spices
    'stjärnanis': {'anis hel'},  # "Kryddor Anis hel" = regular anise, NOT star anise
    'stjarnanis': {'anis hel'},
    'vetemjöl': {'rågsikt'},  # "Rågsikt med vetemjöl" = rye blend ≠ pure wheat flour
    'vetemjol': {'rågsikt', 'ragsikt'},
    'mjöl': {'rågsikt'},  # Same for generic "mjöl" keyword
    'mjol': {'rågsikt', 'ragsikt'},
    # Bourbon vanilla powder ≠ bourbon whiskey
    'bourbon': {'vaniljpulver'},  # "Vaniljpulver Bourbon Ekologiskt" — vanilla product, not bourbon whiskey
    # Crispy Chicken Spice Mix ≠ generic chili/taco spice mix
    'spice mix': {'chicken', 'crispy chicken'},
    # "Vegetabilisk Visp" = non-dairy whipping cream ≠ vegetabilisk mjölk
    'vegetabilisk': {'visp'},
    # "Toppingsås Peperoncino" = sauce, not dried chili flakes
    'peperoncino': {'toppingsås', 'toppingsas'},
    # Deli rostbiff (pre-cooked, sliced pålägg) ≠ raw rostbiff cut for roasting
    'rostbiff': {'griljerad', 'grillad'},
    # "Basmatiris Biryani 4,5kg" = rice variety, not biryanikrydda (spice mix)
    'biryani': {'basmatiris', 'ris'},
    # "Lemonad Pink Grape" = soft drink, not grapefruit juice
    'grape': {'lemonad', 'juice'},
    # Generic kryddblandning (Ras El Hanout, Allroundkrydda, Berbere) ≠ kinesisk femkrydda
    'kryddblandning': {'tärnad ost', 'ost i olja', 'ras el hanout', 'allroundkrydda', 'allround', 'berbere'},
    # "Sockerkaka Med Chokladfyllning 30g Lubisie" = pre-made snack cake ≠ baking mix
    'sockerkaka': {'chokladfyllning'},
    # "Kycklingpytt med rotsaker Fryst 700g ICA" = ready meal ≠ raw root vegetables
    'rotsaker': {'pytt', 'kycklingpytt'},
    # "Pasta, bacon & parmesansås" = ready meal, not a buyable parmesan sauce
    'parmesansås': {'pasta'},
    # Loose herb blend != flavored crème fraîche product family.
    # Ingredient-side herb lines such as "torkade franska örter" should not
    # match products whose "franskaörter" lives inside a crème fraîche carrier.
    'franskaörter': {'creme fraiche', 'crème fraiche', 'fraiche'},
    # "Apelsinmarmelad utan tillsatt socker" / "Blodpudding utan socker" — NOT sugar products
    'socker': {'utan', 'mindre'},
    # "Rågmackor 450g Åkes Äkta Hönökaka" extracts 'kaka' — rye crackers ≠ cake/cookies
    'kaka': {'hönökaka', 'honokaka', 'rågmackor', 'ragmackor'},
}

PRODUCT_NAME_BLOCKERS: Dict[str, Set[str]] = {
    fix_swedish_chars(k).lower(): {fix_swedish_chars(w).lower() for w in v}
    for k, v in _PRODUCT_NAME_BLOCKERS_RAW.items()
}
