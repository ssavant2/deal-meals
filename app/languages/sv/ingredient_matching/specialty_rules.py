"""Specialty qualifier data for Swedish ingredient matching.

Used by:
- validators.py — check_specialty_qualifiers()
- matching.py — precompute_offer_data() for offer qualifier indexing
"""

from typing import Dict, FrozenSet, List, Set

try:
    from languages.sv.normalization import fix_swedish_chars
except ModuleNotFoundError:
    from app.languages.sv.normalization import fix_swedish_chars

_SPECIALTY_QUALIFIERS_RAW: Dict[str, Set[str]] = {
    # Premium hams - "skinka" should not match "Serrano" unless recipe says "serrano"
    # Also handles: "kokt skinka" should NOT match "rökt skinka"
    'skinka': {
        # Premium varieties
        'serrano', 'parma', 'prosciutto', 'iberico', 'ibérico', 'pata negra',
        'jamon', 'jamón',
        # Curing/drying methods - "lufttorkad skinka" != "rökt skinka"
        'lufttorkad', 'torkad',
        # Smoking methods - "kokt skinka" != "rökt skinka"
        'rökt', 'rokt', 'flatrökt', 'flatrokt', 'basturökt', 'basturokt',
        'extrarökt', 'extrarokt', 'gallerrökt', 'gallerrokt', 'svartrökt', 'svartrokt',
        # Cooking methods
        'griljerad', 'kokt',
        # Cut forms - "skivad skinka" != "strimlad skinka"
        'skivad', 'strimlad',
        # Seasonal specialties - "julskinka" != "rökt skinka"
        'jul', 'julskinka',
    },
    # Iberico cuts vs iberico charcuterie/cheese
    # "Iberico Secreto" (pork cut) should NOT match "Fuet Iberico" (salami) or "Manchego Iberico" (cheese)
    # Bidirectional: product with "secreto"/"pluma" requires ingredient to say the same
    'iberico': {
        'secreto',  # premium pork cut
        'pluma',  # premium pork cut
        'fuet',  # dry salami — different product entirely
        'manchego',  # cheese — not meat at all
    },

    # Tomato varieties - kept for canned/specialty/size distinction
    # NOTE: cocktail REMOVED — fresh small tomatoes interchangeable (→ småtomat)
    # plommon KEPT — regular-sized plum tomatoes, NOT interchangeable with small
    'tomat': {
        'körsbär', 'körsbärs', 'cherry',  # cherry tomatoes ≠ regular
        'plommon', 'plommontomater',  # plum tomatoes ≠ small tomatoes
        'soltorkad', 'soltorkade',  # sun-dried ≠ fresh/canned
        'solt', 'secchi',  # abbreviated/Italian for sun-dried
        'krossad', 'krossade', 'passerade',  # canned forms
        'finkrossad', 'finkrossade',  # "Tomater Finkrossade" variant of krossade
        'skalad', 'skalade',  # peeled whole tomatoes
        'burk',  # "på burk" → QUALIFIER_EQUIVALENTS maps to all canned forms
        'konserverad', 'konserverade',  # → QUALIFIER_EQUIVALENTS maps to all canned forms
    },
    # Plural form needed too - "Krossade tomater" extracts keyword "tomater" not "tomat"
    'tomater': {
        'körsbär', 'körsbärs', 'cherry',
        'plommon', 'plommontomater',
        'soltorkad', 'soltorkade',
        'solt', 'secchi',  # abbreviated/Italian for sun-dried
        'krossad', 'krossade', 'passerade',
        'finkrossad', 'finkrossade',
        'skalad', 'skalade',
        'burk', 'konserverad', 'konserverade',
    },
    # Cherry tomatoes: sun-dried ≠ canned/fresh
    'körsbärstomat': {
        'soltorkad', 'soltorkade', 'solt', 'secchi',
    },
    'körsbärstomater': {
        'soltorkad', 'soltorkade', 'solt', 'secchi',
    },
    # Whole/grilled chicken: "hel kyckling" or "grillad kyckling" should only
    # match products with those qualifiers, not generic chicken cuts.
    # NOTE: buljong/fond qualifiers removed — handled by dedicated buljong context
    # check in recipe_matcher.py (lines ~1260-1283) which works per-ingredient.
    # Having them here caused cross-ingredient contamination on combined text.
    'kyckling': {
        'hel',
        # Smoked/pre-cooked chicken should NOT match fresh chicken recipes
        'rökt', 'rokt',
        'kallrökt', 'kallrokt',
        'grillad', 'grillat',       # pre-grilled deli chicken
    },
    'lamm': {
        'rostbiff',
    },
    # Smoked/pre-cooked chicken should NOT match fresh chicken fillet recipes
    # "Kyckling Rökt Deliskivor" (kw: kycklingfilé) must not match "600 g kycklinglårfilé"
    # Bidirectional: product 'rökt' → ingredient must also say 'rökt'
    # Drumsticks: "Chicken Drumsticks Grillade Frysta" should NOT match raw "kycklingben"
    'kycklingben': {
        'grillad', 'grillade', 'grillat',
        'rökt', 'rokt',
        'kallrökt', 'kallrokt',
    },
    'kycklingfilé': {
        'rökt', 'rokt',
        'kallrökt', 'kallrokt',
        'grillad', 'grillat',       # pre-grilled deli chicken
    },
    'kycklingfile': {
        'rökt', 'rokt',
        'kallrökt', 'kallrokt',
        'grillad', 'grillat',
    },
    'renstek': {
        'rökt', 'rokt',
    },
    'sidfläsk': {'rökt', 'rokt', 'rimmat'},
    'sidflask': {'rökt', 'rokt', 'rimmat'},
    # Generic pork: explicit "rökt fläsk" should not degrade to plain fresh pork cuts.
    'fläsk': {'rökt', 'rokt'},
    'flask': {'rökt', 'rokt'},
    # NOTE: cucumber (gurka) qualifiers live in BIDIRECTIONAL_PER_KEYWORD instead.
    # Broth/stock protein types: buljong/fond handled by dedicated context check
    # in recipe_matcher.py, NOT here (combined text causes false blocks).
    # 'höns', 'nöt', 'grönsak', 'fisk' — removed buljong/fond qualifiers.
    # Breadcrumbs vs bread loaves - if ingredient says "ströbröd", product must too
    # "ströbröd" should NOT match "Flerkorn Bröd Surdeg..."
    # Also: "pitabröd" should NOT match "Jubileumskaka" or other bread
    'bröd': {
        'strö', 'ströbröd', 'panko',
        'pita', 'pitabröd',
        'tortilla', 'tortillabröd',
        'hamburgare', 'hamburgerbröd',
        'korvbröd',
        # Specialty flatbreads - generic "bröd" should not match these
        'naan', 'naanbröd',
        'focaccia',
        'ciabatta',
        'baguette', 'baguett',
        'tunnbröd',
        'polarbröd',
        'knäcke', 'knäckebröd',  # crispbread
    },

    # Strömming: "Strömming Inlagd/stekt" ≠ fresh "strömmingsfilé"
    # Direction B (via BIDIRECTIONAL 'inlagd'): preserved/cooked product blocked from fresh recipes
    'strömming': {
        'inlagd', 'inlagda',
        'stekt', 'stekta',  # pan-fried prepared product
    },

    # Cucumber: "inlagd gurka" ≠ fresh "gurka"
    # Direction A: recipe says "inlagd gurka" → product must have "inlagd"
    # Direction B (via BIDIRECTIONAL): product "Inlagd Gurka" → recipe must say "inlagd"
    # (Direction B is also handled by PPR, this adds the reverse direction A)
    'gurka': {
        'inlagd', 'inlagda',
        'saltad', 'salt',
        'dill',        # "Gurka med Dill" = pickled
        'krispig',     # "Gammeldags Krispig Gurka" = pickled
        'gammeldags', 'gammaldags',
        # Product-side qualifiers for compound pickled types (parent kw "gurka"):
        'smörgås', 'smorgås',  # Smörgåsgurka → qualifier "smörgås" detected in product name
        'ättiks', 'attiks',    # Ättiksgurka
        'boston',              # Bostongurka
    },
    'gurkor': {
        'inlagd', 'inlagda',
        'saltad', 'salt',
        'smörgås', 'smorgås', 'ättiks', 'attiks', 'boston',
    },

    # Food coloring is color-specific: "röd hushållsfärg" should not match
    # green/yellow/blue variants.
    'hushållsfärg': {
        'röd', 'rod', 'red',
        'grön', 'gron', 'green',
        'gul', 'yellow',
        'blå', 'bla', 'blue',
    },

    # Citron: "inlagda citroner" (preserved lemons) ≠ fresh "citron"
    # Direction A: recipe says "inlagda citroner" → fresh "Citron Klass 1" blocked
    # No BIDIRECTIONAL needed — no "Inlagda Citroner" product exists in stores
    'citron': {
        'inlagd', 'inlagda',
    },
    'citroner': {
        'inlagd', 'inlagda',
    },

    # Olives - "svarta oliver" ≠ "gröna oliver"
    # Direction A: recipe "svarta oliver" blocks green olive products
    # No bidirectional: "Gröna Oliver Zeta" should still match generic "oliver" recipes
    'oliver': {
        'svart', 'svarta',  # black olives
        'grön', 'gröna',  # green olives
        # Green varieties
        'halkidiki',  # green Greek olive
        'gordal',  # large green Spanish olive
        'cerignola',  # green Italian olive
        'nocellera',  # green Sicilian olive (Nocellera del Belice)
        'taggiasca',  # green Italian olive (Liguria)
        # Black varieties
        'kalamata',  # black Greek olive
        'gemlik',  # black Turkish olive
        # Filled/stuffed olives are a distinct product family and should not
        # surface for plain whole-olive ingredients unless the recipe says so.
        'fylld', 'fyllda',
        'pimiento',
    },

    # Lentil types - "röda linser" ≠ "gröna linser"
    # Direction A: recipe says "röda linser" → "Gröna Linser" blocked
    # Not bidirectional: "Röda Linser" should still match generic "linser" recipes
    'linser': {
        'röd', 'röda',        # red lentils
        'grön', 'gröna',      # green lentils (e.g., Puy)
        'svart', 'svarta',    # black (Beluga) lentils
        'beluga',             # "Beluga Linser" = black lentils (type name ≠ color name)
        'brun', 'bruna',      # brown lentils
        'gul', 'gula',        # yellow lentils
    },

    # Currant jelly: red vs black are different berries
    'vinbärs': {
        'röd', 'röda',        # "Röd Vinbärs Gelé" — red currant
        'svart', 'svarta',    # "Svart Vinbärs Gelé" — black currant
    },
    'vinbär': {
        'röd', 'röda',        # "Röda Vinbär" — red currant
        'svart', 'svarta',    # "Svarta Vinbär" — black currant
    },

    # Cinnamon: "kanelstång" (cinnamon stick) ≠ ground cinnamon
    # Direction A: recipe "1 kanelstång" has qualifier 'stång' → product must have 'stång'/'hel'
    # Not bidirectional: "Kanel Malen Burk" should still match "1 tsk kanel" recipes
    'kanel': {
        'stång',      # "kanelstång" = cinnamon stick
        'stänger',    # plural
        'hel',        # "Kanel Hel Påse" = whole cinnamon
    },

    # NOTE: Fresh herbs (koriander, basilika, persilja, mynta, dill) removed.
    # The qualifiers {färsk, kruka, bunt, knippe} are packaging descriptors,
    # not specialty types. Direction A blocked "Koriander Bunt" from matching
    # any recipe saying just "koriander" (757 recipes!). "torkad" was never
    # in the qualifier list anyway, so the intended dried/fresh distinction
    # wasn't working.

    # Salmon preparation types - "kallrökt lax" ≠ plain "lax"
    # Bidirectional: product "Kallrökt Lax" requires ingredient to also say "kallrökt"
    'lax': {
        'kallrökt', 'kallrokt',  # cold-smoked salmon
        'varmrökt', 'varmrokt',  # hot-smoked salmon
        'gravad', 'gravade',  # cured salmon
        'rökt', 'rokt',  # generic smoked
    },

    # Meat cut: "vildsvinskarré" ≠ generic pork "karré"
    # Direction A: recipe says "vildsvinskarré" → offer must have "vildsvin"
    # Not bidirectional: "Karré Rapsgris" should still match recipes saying just "karré"
    'karré': {
        'vildsvin', 'vildsvins',  # wild boar cut
        'lamm',  # lamb cut
        'kalv',  # veal cut
    },

    # Kaviar: "oscietra kaviar" (sturgeon roe) ≠ "Kalles Kaviar" (cod roe spread)
    # Direction A: recipe says "oscietra kaviar" → offer must have "oscietra"
    'kaviar': {
        'oscietra', 'osetra', 'oscitra',  # sturgeon roe
        'löjrom', 'löj',  # vendace roe
        'forellrom', 'forell',  # trout roe
        'laxrom',  # salmon roe
    },

    # Wine color - "Matlagningsvin Röd" ≠ "vitt vin" recipe
    # Bidirectional: product "Matlagningsvin Röd" requires ingredient to say "rött",
    # and recipe "rött matlagningsvin" requires product to have "röd/rött"
    # QUALIFIER_EQUIVALENTS maps röd↔rött and vit↔vitt
    'matlagningsvin': {
        'röd', 'rod', 'rött', 'rott',   # red wine
        'vit', 'vitt',                    # white wine
    },

    # Broth types - "grönsaksbuljong" ≠ "kycklingbuljong"
    # Direction A: ingredient "kycklingbuljong" → product must have "kyckling"
    # Direction B (bidirectional): product "Grönsaks Buljong" → ingredient must have "grönsaks"
    'buljong': {
        'kyckling', 'höns',  # chicken stock
        'grönsak', 'grönsaks',  # vegetable stock
        'fisk',  # fish stock
        'skaldjur', 'skaldjurs',  # shellfish stock
        'kalv',  # veal stock
        'kött', 'ox',  # beef stock
        'svamp',  # mushroom stock
        'lant',  # country/rustic stock
        'örtagårds',  # herb garden stock
        'umami',  # umami stock (e.g. Maggi Umami)
    },

    # Same qualifiers for compound keywords "buljongtärning"/"buljongtärningar"
    # (matched_keyword lookup uses exact key, not substring)
    'buljongtärning': {
        'kyckling', 'höns',
        'grönsak', 'grönsaks',
        'fisk',
        'skaldjur', 'skaldjurs',
        'kalv',
        'kött', 'ox',
        'svamp',
        'lant',
        'örtagårds',
        'umami',
    },
    'buljongtärningar': {
        'kyckling', 'höns',
        'grönsak', 'grönsaks',
        'fisk',
        'skaldjur', 'skaldjurs',
        'kalv',
        'kött', 'ox',
        'svamp',
        'lant',
        'örtagårds',
        'umami',
    },

    # Canned vs fresh/frozen tuna - "Tonfisk ICA 170g" (canned) should NOT match
    # recipes wanting tuna steaks/fillets (fresh or frozen)
    'tonfisk': {
        'färsk', 'fryst', 'filé', 'file', 'biff', 'steak', 'bit',
        'vatten', 'olja', 'buljong',
    },

    # Rice types - risotto rice (carnaroli/arborio) ≠ regular long-grain rice
    # Direction A: ingredient "carnaroliris" → product must have "carnaroli"
    'ris': {
        'carnaroli', 'arborio', 'vialone', 'avorio',  # risotto rice
        'risotto', 'risottoris',  # risotto rice (generic)
        'grötris', 'gröt',  # porridge rice (round grain)
        'sushiris', 'sushi',  # sushi rice (short grain, sticky)
        'paella', 'paellaris',  # paella rice
        'vildris', 'vild',  # wild rice (different species)
        'råris',  # brown rice (unhulled)
    },

    # Pommes variants - "pommes strips" is a specific product, generic "pommes" should not match
    'pommes': {'strips', 'chateau', 'pinnar', 'pinnes', 'wedges', 'klyft', 'klyftor'},

    # Onion types - "purjolök" should NOT match "Schalottenlök" or generic "lök"
    # If ingredient has specific onion type, product must also have it
    # IMPORTANT: "vitlök" (garlic) is a completely different vegetable, not an onion!
    'lök': {
        'purjo', 'purjolök',  # leek vs regular onion
        'röd', 'rödlök',  # red onion
        'gul', 'gullök',  # yellow onion - "gul lök" should NOT match "Lök Röd"
        'sallads', 'salladslök',  # salad onion / spring onion
        'schalotten', 'charlotten',  # shallot
        'vår', 'vårlök',  # spring onion
        'vit', 'vitlök',  # garlic - NOT an onion, completely different!
    },

    # Salad types - "Sallad Isberg" should NOT match generic "sallad", "salladsmix" or "grönsallad"
    # Bidirectional: product with specific salad type requires ingredient to say the same type
    'sallad': {
        'isberg', 'isbergs',  # iceberg lettuce
        'roman', 'romansallad',  # romaine lettuce
        'ruccola', 'rucola',  # arugula
        'spenat',  # spinach (sometimes sold as "Spenatsallad")
    },
    'sallat': {  # alternate spelling (products say "Sallat", recipes say "romansallat")
        'isberg', 'isbergs',
        'roman', 'romansallat',
        'ruccola', 'rucola',
        'spenat',
    },

    # Mince: "vegetarisk färs" / "formbar färs" should only match plant-based mince
    # Direction A: ingredient "vegetarisk/formbar färs" → product must have vego/vegansk equivalent
    # "formbar" = Javligtgott/Anamma brand term for moldable plant-based mince
    'färs': {
        'vegetarisk', 'vegansk', 'vego',  # plant-based mince qualifier
        'formbar', 'formbara',  # moldable plant-based mince (Anamma/Javligtgott)
        'soja',  # soy-based mince
        'baljväxt', 'baljvaxt',  # legume-based mince
    },

    # Shiitake: "Shiitake Torkad" (dried) should NOT match fresh "shiitakesvamp"
    # 'torkad' is already in BIDIRECTIONAL_SPECIALTY_QUALIFIERS → Direction B blocks dried product
    # Direction A: ingredient "torkad shiitake" → product must also be dried
    'shiitake': {
        'torkad', 'torkade',  # dried shiitake ≠ fresh shiitake
    },

    # Curry spice vs curry paste - "Curry Burk" (powder) should NOT match ingredient "currypasta"
    # Direction A: ingredient "currypasta" has qualifier 'pasta' → product must also have pasta/paste
    'curry': {
        'pasta', 'paste',  # curry paste ≠ curry powder
    },

    # Filled gnocchi is a distinct product type from plain gnocchi.
    'gnocchi': {
        'fylld', 'fyllda',
    },

    # Vodka sauce should only match pasta sauces that actually contain vodka.
    'pastasås': {
        'vodka',
    },
    'pastasas': {
        'vodka',
    },

    # Asparagus: "grön sparris" ≠ "Hel Sparris Vit" (white asparagus)
    # Direction A: ingredient "grön sparris" → product must have 'grön'
    'sparris': {
        'grön', 'gröna',   # green asparagus
        'vit', 'vita',     # white asparagus
    },

    # Artichokes: marinated artichoke hearts ≠ plain whole artichokes
    'kronärtskocka': {
        'marinerad', 'marinerade',
    },
    'kronartskocka': {
        'marinerad', 'marinerade',
    },

    # Pesto: "Pesto Grön" ≠ "Pesto Rosso" (red pesto)
    # Direction A: ingredient "pesto grön" → product must have 'grön' (or equivalent: genovese, basilico)
    # QUALIFIER_EQUIVALENTS maps genovese/basilico → grön, rosso → röd
    'pesto': {
        'grön', 'gröna', 'genovese', 'basilico', 'basilika',  # green pesto variants
        'rosso', 'röd', 'röda',                                 # red pesto variants
    },

    # Lingonberries: "Rårörda Lingon" (jam) ≠ plain lingon (fresh/frozen berries)
    # "Lingon 500g ICA" IS frozen berries in practice — fryst/frysta qualifier was blocking it
    # Direction B (via BIDIRECTIONAL_PER_KEYWORD): rårörda/rörda block generic "lingon" recipes
    # Sylt already blocked by PNB ('lingonsylt', 'lingon 35')
    'lingon': {
        'rårörda', 'rörda',    # preserved/stirred (jam) — also bidirectional
    },

    # Prosciutto: cotto (cooked) ≠ crudo (cured/raw)
    # Direction A: ingredient "prosciutto cotto" → product must have 'cotto'
    # "Prosciutto Crudo Skivad" has 'crudo' → blocked for 'cotto' recipe ✓
    'prosciutto': {
        'cotto',   # cooked ham
        'crudo',   # cured/raw ham
        'pinsa',   # "Pinsa Prosciutto Cotto" = ready-made pizza ≠ sliced prosciutto
    },

    # Balsamic vinegar: flavored/colored variants ≠ regular dark "balsamvinäger"
    # Direction A: ingredient "vit balsamvinäger" → product must have 'vit'
    # Direction B (via BIDIRECTIONAL_PER_KEYWORD): product qualifier blocks generic recipe
    # Flavor words mirror _VINEGAR_FLAVOR_WORDS in extract_keywords_from_ingredient
    'balsamvinäger': {
        'vit', 'vita',   # white balsamic ≠ dark/regular balsamic
        # Fruit/flavor variants (e.g., "Crema di Balsamico Hallon" from ICA)
        'hallon', 'fikon', 'äpple', 'ingefära',
        'mango', 'tryffel', 'fläder', 'körsbär',
        'apelsin', 'granatäpple', 'honung',
    },

    # Pork tenderloin: smoked/marinated ≠ fresh
    # Direction B (via BIDIRECTIONAL 'rökt'): "Fläskytterfilé Rökt" blocked from fresh recipe
    'fläskytterfilé': {
        'rökt', 'rokt',           # smoked
        'grillkryddad', 'mörad',  # marinated/seasoned
    },
    'fläskytterfile': {
        'rökt', 'rokt',
        'grillkryddad', 'mörad',
    },

    # Syrup types: "Mörk Sirap" ≠ "ljus sirap" ≠ "vit sirap"
    # Direction A: ingredient "ljus sirap" → product must have 'ljus'
    # Direction B (via BIDIRECTIONAL_PER_KEYWORD): product 'mörk' blocks "ljus sirap" recipe
    'sirap': {
        'ljus',   # light syrup (golden, for baking)
        'mörk',   # dark syrup (molasses-like)
        'vit',    # white syrup
    },

    # Muscovado sugar types: "mörkt muscovadosocker" ≠ "ljus muscovadosocker"
    # Direction A only: explicit light/dark recipe wording should keep the right product.
    # Plain generic muscovado sugar can remain broad across both variants.
    'muscovadosocker': {
        'ljus',
        'mörk',
    },
    'muskovadosocker': {
        'ljus',
        'mörk',
    },

    # Milk: condensed/caramelized milk ≠ regular milk
    # Direction A: ingredient "kondenserad mjölk" → product must have 'kondenserad'
    # Direction A: ingredient "karamelliserad mjölk" → product must have 'karamelliserad'
    # Complements the PPR which handles reverse (product→recipe) direction
    'mjölk': {
        'kondenserad', 'kondenserat', 'kondenserade',
        'karamelliserad', 'karamelliserat', 'karamelliserade',
    },
    'mjolk': {
        'kondenserad', 'kondenserat', 'kondenserade',
        'karamelliserad', 'karamelliserat', 'karamelliserade',
    },
    # Butter salt level matters when the recipe says so explicitly.
    # Plain generic "smör" should stay broad across salted/unsalted products.
    'smör': {
        'osaltat',
        'normalsaltat',
        'extrasaltat',
    },
    'smor': {
        'osaltat',
        'normalsaltat',
        'extrasaltat',
    },

    'socker': {
        'frukt', 'fruktsocker',
        'sylt', 'syltsocker',
    },

    # Curry paste colors - "röd currypasta" ≠ "grön currypasta"
    # Bidirectional: product "Red Curry Paste" (→ rödcurrypasta) should not match "grön currypasta"
    'currypasta': {
        'röd', 'rod', 'red',  # red curry paste
        'grön', 'gron', 'green',  # green curry paste
        'gul', 'yellow',  # yellow curry paste
    },

    'pumpa': {
        'butternut',
    },

    # Paprika: color/preparation qualifiers distinguish fresh peppers from dried spice or jarred
    # Direction A: "grön paprika" in ingredient → product must have "grön" ("Paprika Burk" blocked)
    # Direction A: "grillad paprika" in ingredient → product must have "grillad"
    # "mix" added so "Paprika Mix" products are recognized by the qualifier system —
    # QUALIFIER_EQUIVALENTS makes 'mix' equivalent to all colors (any-color match)
    'paprika': {
        'grön', 'röd', 'gul', 'orange',  # color = fresh bell pepper
        'mix',  # "Paprika Mix" — matches any color via QUALIFIER_EQUIVALENTS
        'grillad', 'grillat', 'rostade', 'rostad', 'röstad', 'rökt',  # prepared varieties
        'inlagd',  # pickled/jarred peppers ≠ fresh bell pepper
    },

    # Pimenton variants are specific smoked paprika spice types.
    # "pimenton ... picante" should require the picante variant, not any
    # product that merely contains a generic heat descriptor.
    'pimenton': {
        'picante',
        'dulce',
    },

    # Fresh chili: color qualifiers distinguish red from green chili
    # Same logic as paprika — "grön chili" should NOT match "Chili Röd" and vice versa
    'chili': {
        'röd', 'rod', 'red',      # red chili
        'grön', 'gron', 'green',   # green chili
    },

    # Chili sauce types - "sweet chilisås" ≠ "lime chilisås" ≠ "sriracha chilisås"
    # Bidirectional: product "Lime Chilisås" should NOT match ingredient "sweet chilisås"
    'chilisås': {
        'sweet', 'söt', 'sota',  # sweet chili sauce
        'osötad', 'osotad', 'osötat', 'osotat',  # unsweetened chili sauce
        'lime',  # lime chili sauce
        'sriracha',  # sriracha-style chili sauce
        'gochujang', 'go-chu-jang',  # Korean chili sauce base, not plain/original chilisås
    },

    # Crème fraiche flavors — bidirectional: "Paprika Chili Crème Fraiche" should NOT
    # match plain "crème fraiche" recipe. Plain products (no flavor qualifier) always match.
    # If recipe says "crème fraiche paprika chili", BOTH the flavored product AND plain
    # products match (plain = fallback). Frontend sorts exact flavor match first.
    'fraiche': {
        # Actual product flavors (from Willys/ICA inventory)
        'paprika', 'chili',  # "Paprika Chili Crème Fraiche"
        'tomat', 'basilika',  # "Tomat Basilika Crème Fraiche"
        'dragon', 'citron',  # "Dragon Citron Crème Fraiche"
        'feta',  # "Feta Tomat Crème Fraiche"
        'parmesan',  # "Parmesan Crème Fraiche"
        'karljohan',  # "Creme Fraiche Karljohan"
        'örter', 'orter',  # "Franska Örter Crème Fraiche"
        # Common recipe flavors (may not have matching product → fallback to plain)
        'vitlök', 'vitlok',  # "crème fraiche vitlök/parmesan"
        'saffran',  # "Creme Fraiche Saffran & Tomat"
    },

    # Dried vs fresh fruit/berries - "torkade X" should NOT match fresh "X"
    # If recipe says "torkade", product must also have "torkad/torkade"
    'blåbär': {'torkad', 'torkade'},
    'aprikos': {'torkad', 'torkade', 'soft'},  # "Soft" = English soft-dried form
    'aprikoser': {'torkad', 'torkade', 'soft'},
    'fikon': {'torkad', 'torkade', 'färsk', 'färska'},
    'päron': {'halvor'},
    'paron': {'halvor'},
    'tranbär': {'torkad', 'torkade'},
    'plommon': {'torkad', 'torkade'},
    'hallon': {'sorbet', 'frystorkad', 'frystorkade'},
    'jordgubb': {'frystorkad', 'frystorkade'},
    'jordgubbar': {'frystorkad', 'frystorkade'},
    'körsbär': {'torkad', 'torkade'},
    # 'dadlar' removed — dried is the default form in Sweden. "Dadlar" = torkade dadlar.
    # "Torkade Dadlar" should match any recipe asking for "dadlar".
    'mango': {'torkad', 'torkade', 'inlagd', 'inlagda'},
    'banan': {'torkad', 'torkade'},
    'persika': {'torkad', 'torkade'},
    'persikor': {'torkad', 'torkade'},
    # 'lime' removed — handled by PROCESSED_PRODUCT_RULES instead
    # (SPECIALTY_QUALIFIERS with concatenated search text causes cross-contamination)

    # Italian/specialty cheeses - "parmesanost" should NOT match generic "Riven Ost"
    # If ingredient has specific cheese type, product must also have it
    'ost': {
        'parmesan', 'parmigiano', 'parmesanost',
        'mozzarella', 'mozarella',
        'ricotta',
        'mascarpone',
        'burrata',
        'grana', 'padano',  # grana padano
        'pecorino',
        'gorgonzola',
        'cheddar',
        'gruyère', 'gruyere',
        'grevé', 'greve', 'grevéost', 'greveost',
        'emmental', 'emmentaler',
        'brie', 'camembert',
        'feta', 'fetaost',
        'halloumi',
        'cottage',  # cottage cheese
        # Note: Swedish everyday cheeses (präst, herrgård, gratäng, hushåll) removed -
        # they ARE generic ost and should match "ost" recipes.
        # västerbotten is NOT in this group — distinct flavor, in SPECIALTY_QUALIFIERS.
        # Note: Cheese forms (riven) removed from Direction A - any cheese can be grated.
        # But 'skivad' is BIDIRECTIONAL (via BIDIRECTIONAL_PER_KEYWORD): pre-sliced
        # cheese should NOT match "riven ost" or generic "ost" cooking recipes.
        'skivad', 'skivade',
        'rökt', 'rokt',  # smoked cheese — distinct from generic ost
        'tärnad', 'tärnade', 'tärning', 'tärningar',  # pre-diced cheese (ost i olja) — not generic ost
        # Specific cheese types
        'färsk', 'färskost',  # cream cheese / fresh cheese
        # Note: Aged cheese (lagrad/vällagrad) removed - most store cheeses say
        # "lagrad" and should still match generic "ost" recipes.
        # Goat/blue cheese - "getost" and "ädelost" are NOT generic ost
        'get', 'getost',
        'ädel', 'ädelost',
        'kvibille',  # specific blue cheese brand
    },

    # Filled pasta: filling-specific lines like "tortellini ricotta/spenat"
    # should not fall back to unrelated fillings such as ost/skinka.
    # Direction A only: generic "tortellini" can still match any filled tortellini.
    'tortellini': {
        'ricotta',
        'spenat', 'spinaci',
        'ost',
        'ostar', '4 ostar', 'fyra ostar', '5 ostar', 'fem ostar',
        'skinka',
        'prosciutto', 'mortadella',
        'svamp',
        'kött', 'kott',
        'lax',
        'mascarpone',
        'pesto', 'genovese',
        'pancetta',
        'pomodoro',
        'mozzarella', 'mozarella',
    },
    'tortelloni': {
        'ricotta',
        'spenat', 'spinaci',
        'ost',
        'ostar', '4 ostar', 'fyra ostar', '5 ostar', 'fem ostar',
        'skinka',
        'prosciutto', 'mortadella',
        'svamp',
        'kött', 'kott',
        'lax',
        'mascarpone',
        'pesto', 'genovese',
        'pancetta',
        'pomodoro',
        'mozzarella', 'mozarella',
    },
    'ravioli': {
        'ricotta',
        'spenat', 'spinaci',
        'ost',
        'ostar', '4 ostar', 'fyra ostar', '5 ostar', 'fem ostar',
        'skinka',
        'prosciutto', 'mortadella',
        'svamp',
        'kött', 'kott',
        'lax',
        'mascarpone',
        'pesto', 'genovese',
        'pancetta',
        'pomodoro',
        'mozzarella', 'mozarella',
    },

    # Mini mozzarella balls are distinct from ordinary mozzarella blocks/shreds.
    'mozzarella': {
        'mini',
    },
    'mozarella': {
        'mini',
    },

    # Cream types - "vispgrädde" is a specific type that matgrädde cannot substitute
    # Direction A: if ingredient says "vispgrädde", product must have "visp" qualifier
    # Vispgrädde products have "visp" in name → qualifier found → matches everything.
    # Matgrädde products have no "visp" → blocked when ingredient says "vispgrädde".
    'grädde': {
        'visp', 'vispgrädde', 'vispgradde',
        'matlagning', 'matlagnings',
        'havre', 'havrebaserad',
    },

    # Cream cheese — flavor qualifiers (Direction A + Direction B via BIDIRECTIONAL_PER_KEYWORD)
    # Direction A: recipe "färskost vitlök & örter" → product must have 'vitlök'
    # Direction B: product "Färskost Vitlök & Örter" → recipe must mention 'vitlök'
    # 'naturell' kept — Direction A: recipe "naturell färskost" → product must have 'naturell'
    'färskost': {
        'naturell',
        'vitlök', 'vitlok', 'örter', 'orter',
        'garlic', 'herbs',              # English = vitlök & örter (QUALIFIER_EQUIVALENTS maps)
        'paprika',
        'curry',
        'chili',
        'jalapeno', 'jalapeño',
        'tryffel',
        'blue',
        'blåmögel', 'blamogel',
        'bleu',
        'peppar',
        'pepparrot',
        'gräslök', 'graslok',
        'chimichurri',
        'kantarell',
        'ramslök', 'ramslok',
        'tomat',
        'nöt', 'not',
        'oliver',
        'grekisk',                       # Grekisk Vitlök Färskost
    },

    # NOTE: Yoghurt type matching removed from SQ — handled by check_yoghurt_match()
    # function which classifies both recipe and product into cooking/vanilj/vego/snack types.

    # Cashews: explicit salted/naturell requests should not collapse into each other.
    'cashewnötter': {
        'naturell', 'naturella',
        'saltad', 'saltade', 'salta',
    },
    'cashewnotter': {
        'naturell', 'naturella',
        'saltad', 'saltade', 'salta',
    },
    'cashew': {
        'naturell', 'naturella',
        'saltad', 'saltade', 'salta',
    },
    'jordnötter': {
        'naturell', 'naturella',
        'osaltad', 'osaltade',
        'saltad', 'saltade', 'salta',
    },
    'jordnotter': {
        'naturell', 'naturella',
        'osaltad', 'osaltade',
        'saltad', 'saltade', 'salta',
    },

    # Bean types - "kidneybönor" should NOT match generic "Blandade Bönor"
    # If ingredient has specific bean type, product must also have it
    'bönor': {
        'kidney', 'kidneybönor',
        'svart', 'svarta',  # svarta bönor
        'jäst', 'jästa', 'fermenterad', 'fermenterade',  # fermented black beans
        'vit', 'vita',  # vita bönor
        'grön', 'gröna', 'haricot', 'brytbönor', 'brytbonor',  # green bean families
        'röd', 'röda',  # röda bönor
        'brun', 'bruna',  # bruna bönor
        'blandad', 'blandade', 'mix',  # mixed-bean products: "Bönmix" etc.
        'stor', 'stora',  # stora vita bönor
        'flageolet',
        'cannellini',
        'borlotti',
        'pintobönor', 'pinto',
        'vax', 'vaxbönor',  # wax beans
        'lima', 'limabönor',
        'blackeyeböna', 'blackeyebönor', 'blackeyebona', 'blackeyebonor',
    },
    # Mixed-bean package wording should stay on mixed-bean products.
    'bönmix': {
        'mix', 'blandad', 'blandade',
    },
    'bonmix': {
        'mix', 'blandad', 'blandade',
    },

    # Salad dressing types - "caesardressing" should NOT match "Dressing Original"
    'dressing': {
        'caesar', 'caesardressing', 'ceasardressing',
        'ranch',
        'thousand island', 'tusen öar', 'tusenöar',
        'vinaigrette', 'vinägrett',
        'balsamico', 'balsamic',
        'italian', 'italiensk',
        'french', 'fransk',
    },
    'salladskrydda': {
        'grekisk', 'greek',
        'italiensk', 'italian',
    },

    # Drink type: "havrebaserad dryck" / "växtbaserad dryck" should NOT match dairy
    # "Mellanmjölkdryck" (kw: 'dryck'). Qualifier enforces plant-based qualifier in product.
    'dryck': {
        'havrebaserad',  # oat-based drink
        'växtbaserad', 'vaxtbaserad',  # plant-based drink
    },

    # Fond types - "rostad fond" is a restaurant technique, not regular stock
    'fond': {
        'rostad', 'rostade',
    },

    # Black garlic - "svart vitlök" is fermented, completely different from regular garlic
    'vitlök': {
        'svart', 'svarta',  # "svart vitlök" ≠ regular vitlök
    },

    # Chocolate darkness: "Bakchoklad Vit" should NOT match "mörk choklad" (Direction B blocks).
    # "mörk choklad" SHOULD match products without darkness qualifier (generic/unspecified).
    # Direction A skipped for these keywords — only Direction B enforced.
    'choklad': {
        'mörk', 'mork',
        'vit',
        'ljus',
    },
    'bakchoklad': {
        'mörk', 'mork',
        'vit',
        'ljus',
    },
    'blockchoklad': {
        'mörk', 'mork',
        'vit',
        'ljus',
    },

    # Fresh pasta — "färsk pasta/långpasta" should only match products with "färsk" in name
    'pasta': {
        'färsk',  # "färsk pasta" ≠ torkad pasta
    },
    'långpasta': {
        'färsk',  # "färsk långpasta" ≠ torkad (unlikely but consistent)
    },

    # Melon types — specific melon ≠ other melons
    'melon': {
        'cantaloupe',  # "Melon Cantaloupe" ≠ watermelon/galia
        'galia',  # "Melon Galia" ≠ cantaloupe/watermelon
        'vatten', 'vattenmelon',  # "Vattenmelon" ≠ cantaloupe/galia
        'honungsmelon',  # honeydew ≠ other melons
    },
}

# Pre-normalized for performance
# Sorted lists for deterministic iteration (Python set order varies with PYTHONHASHSEED)
SPECIALTY_QUALIFIERS: Dict[str, List[str]] = {
    fix_swedish_chars(k).lower(): sorted(fix_swedish_chars(q).lower() for q in qualifiers)
    for k, qualifiers in _SPECIALTY_QUALIFIERS_RAW.items()
}

# Qualifiers enforced in BOTH directions (product→ingredient AND ingredient→product).
# Used when the qualifier indicates a fundamental transformation of the base ingredient
# (e.g., sun-dried, canned, or broth) rather than just a variety or cut.
#
# Standard SPECIALTY_QUALIFIERS: ingredient says "serranoskinka" → product must have "serrano"
# BIDIRECTIONAL: product says "soltorkade" (tomater) → ingredient must also say "soltorkade"
#                so "Soltorkade Tomater" does NOT match recipe "2 tomater" (fresh).
BIDIRECTIONAL_SPECIALTY_QUALIFIERS: FrozenSet[str] = frozenset({
    # Processed/preserved tomato forms (completely different from fresh tomatoes)
    'soltorkad', 'soltorkade', 'soltorkat', 'soltork',
    'secchi', 'solt',  # shortened forms in product names ("Pomodori Secchi Soltork Tomat")
    'krossad', 'krossade', 'passerade',
    'burk',   # jarred/canned (tomater, paprika) - QUALIFIER_EQUIVALENTS['burk'] covers variants
    # Stock/broth (derived product, not the base ingredient itself)
    'buljong', 'buljongtarning', 'buljongtärning', 'fond',
    # NOTE: broth type qualifiers (kyckling, grönsak, etc.) are NOT bidirectional.
    # Direction A alone handles cross-type blocking (e.g., "grönsaksbuljong" product
    # won't match "kycklingbuljong" ingredient). Making them bidirectional would
    # wrongly block specific products from matching generic "buljong" ingredients.
    # Canned/preserved - "hela konserverade tomater" ≠ fresh tomatoes
    'konserverad', 'konserverade',
    # Grillad/röstad paprika is a specific prepared product, not generic paprika
    'grillad', 'grillade', 'grillat',
    'rostade', 'rostad',
    # Chili sauce types are distinct - "Lime Chilisås" ≠ "sweet chilisås"
    'sweet', 'lime', 'sriracha', 'gochujang', 'go-chu-jang',
    # Smoked/cured fish preparation - "Kallrökt Lax" should NOT match plain "lax"
    'kallrökt', 'kallrokt', 'varmrökt', 'varmrokt', 'gravad', 'gravade',
    # Dried products - "Blåbär Torkade" should NOT match fresh "blåbär",
    # but "Shiitake Torkad" SHOULD match "torkad shiitake"
    'torkad', 'torkade', 'torkat',
    'rökt', 'rokt',
    # Salad types - "Sallad Isberg" should NOT match "salladsmix" or "grönsallad"
    'isberg', 'isbergs',
    'roman',
    'ruccola', 'rucola',
    # Iberico cuts - "Iberico Secreto" should NOT match "Fuet Iberico" (salami)
    'secreto', 'pluma',
    'fuet', 'manchego',
    # Curry paste colors - "Red Curry Paste" should NOT match "grön currypasta"
    'red', 'green', 'yellow',
    # Pickled/brined cucumber - "Inlagd Gurka" should NOT match plain "gurka" recipe
    'inlagd', 'inlagda',
    'saltad',
    # Fresh qualifier - "färska fikon" should NOT match dried "Fikon Naturell 500g"
    'färsk', 'färska', 'farsk', 'farska',
    # Soft-dried qualifier - "Aprikoser Soft" is dried, should NOT match fresh apricot recipes
    'soft',
})

# Per-keyword bidirectional qualifiers — same as BIDIRECTIONAL_SPECIALTY_QUALIFIERS but
# only enforced for a SPECIFIC base_word. This prevents collisions when the same qualifier
# word appears for multiple base_words (e.g., "feta" is qualifier for both "fraiche" and "ost",
# but only bidirectional for "fraiche" — feta cheese should still match generic "ost" recipes).
BIDIRECTIONAL_PER_KEYWORD: Dict[str, FrozenSet[str]] = {
    # Whole chicken is a distinct product form and should not surface for
    # generic chicken or chicken-fillet ingredients unless the recipe says so.
    'kyckling': frozenset({
        'hel',
    }),
    # Air-dried/premium hams are skinka-family products, but not substitutes for
    # plain cooked/sandwich ham unless the recipe asks for that cured family.
    'skinka': frozenset({
        'serrano', 'parma', 'prosciutto', 'iberico', 'pata negra', 'jamon',
    }),
    'oliver': frozenset({
        'fylld', 'fyllda', 'pimiento',
    }),
    'fraiche': frozenset({
        'paprika', 'chili', 'tomat', 'basilika', 'dragon', 'citron',
        'feta', 'parmesan', 'saffran',
        'vitlök', 'vitlok', 'örter', 'orter',
    }),
    # Cream cheese flavors: "Färskost Vitlök & Örter" should NOT match plain "färskost" recipe
    # 'naturell' excluded — it means "plain" (= no flavor), same as unqualified "färskost"
    'färskost': frozenset({
        'vitlök', 'vitlok', 'örter', 'orter',   # vitlök & örter
        'paprika',                                 # paprika
        'curry',
        'chili',
        'jalapeno', 'jalapeño',
        'tryffel',
        'blue',
        'blåmögel', 'blamogel',
        'bleu',
        'peppar',
        'pepparrot',                               # pepparrot
        'gräslök', 'graslok',                      # gräslök
        'chimichurri',                             # chimichurri
        'kantarell',                               # kantarell
        'ramslök', 'ramslok',                      # ramslök
        'tomat',                                   # tomat & örter
        'nöt', 'not',                              # nöt
        'oliver',                                  # gröna oliver
        'garlic', 'herbs',                         # English = vitlök & örter
        'grekisk',                                 # Grekisk Vitlök Färskost
    }),
    # Wine color: "Matlagningsvin Röd" should NOT match "vitt matlagningsvin" recipe
    # Per-keyword to avoid collisions with 'röd'/'vit' used elsewhere (e.g., paprika colors)
    'matlagningsvin': frozenset({
        'röd', 'rod', 'rött', 'rott',
        'vit', 'vitt',
    }),
    'vinbärs': frozenset({
        'röd', 'röda',
        'svart', 'svarta',
    }),
    # 'vinbär' NOT bidirectional — generic "vinbär" should match any color.
    # Direction A alone handles: "röda vinbär" → product must have röda (blocks svarta).
    # Chocolate darkness: "Bakchoklad Vit" should NOT match "mörk choklad" recipe
    'choklad': frozenset({
        'mörk', 'mork',
        'vit',
        'ljus',
    }),
    'bakchoklad': frozenset({
        'mörk', 'mork',
        'vit',
        'ljus',
    }),
    'blockchoklad': frozenset({
        'mörk', 'mork',
        'vit',
        'ljus',
    }),
    # Pre-sliced cheese: "Herrgård Skivad" should NOT match "riven ost" or generic "ost"
    # Per-keyword because 'skivad' in other contexts (e.g., skivad lök) isn't bidirectional
    'ost': frozenset({
        'skivad', 'skivade',  # pre-sliced cheese
        'rökt', 'rokt',  # smoked cheese — not generic "ost"
        'tärnad', 'tärnade', 'tärning', 'tärningar',  # pre-diced (ost i olja) — not generic "ost"
    }),
    'sidfläsk': frozenset({'rökt', 'rokt', 'rimmat'}),
    'sidflask': frozenset({'rökt', 'rokt', 'rimmat'}),
    'fläsk': frozenset({'rökt', 'rokt'}),
    'flask': frozenset({'rökt', 'rokt'}),
    # Lingonberry jam/preserve: "Rårörda Lingon" should NOT match generic "lingon"
    'lingon': frozenset({'rårörda', 'rörda'}),
    'päron': frozenset({'halvor'}),
    'paron': frozenset({'halvor'}),
    'hallon': frozenset({'frystorkad', 'frystorkade'}),
    'jordgubb': frozenset({'frystorkad', 'frystorkade'}),
    'jordgubbar': frozenset({'frystorkad', 'frystorkade'}),
    'kronärtskocka': frozenset({'marinerad', 'marinerade'}),
    'kronartskocka': frozenset({'marinerad', 'marinerade'}),
    # Generic prosciutto recipes can accept crudo/parma variants, but "cotto"
    # (cooked ham) should only match when the ingredient explicitly says cotto.
    'prosciutto': frozenset({'cotto'}),
    # Balsamic vinegar: flavored/colored variant should NOT match plain "balsamvinäger" recipe
    'balsamvinäger': frozenset({
        'vit', 'vita',
        'hallon', 'fikon', 'äpple', 'ingefära',
        'mango', 'tryffel', 'fläder', 'körsbär',
        'apelsin', 'granatäpple', 'honung',
    }),
    # Pork tenderloin: marinated/seasoned product should NOT match fresh recipe
    # 'rökt' is globally bidirectional already; these are per-keyword only
    'fläskytterfilé': frozenset({'grillkryddad', 'mörad'}),
    'fläskytterfile': frozenset({'grillkryddad', 'mörad'}),
    # Reindeer roast: smoked product/request is distinct from fresh raw roast
    'renstek': frozenset({'rökt', 'rokt'}),
    # NOTE: 'sirap' REMOVED from BDSQ — 229 recipes say just "sirap" without ljus/mörk
    # and got NO sirap matches because BDSQ blocked "Ljus sirap" when ingredient had no qualifier.
    # In Swedish cooking, plain "sirap" ≈ ljus sirap. Better to show both types than nothing.
    # FPB still blocks lönnsirap, agavesirap, granatäppelsirap etc.
    # Milk: "Kondenserad/Karamelliserad Mjölk" should NOT match plain "mjölk" recipe
    # (also handled by PPR, but per-keyword bidir adds extra safety)
    'mjölk': frozenset({'kondenserad', 'kondenserat', 'kondenserade',
                        'karamelliserad', 'karamelliserat', 'karamelliserade'}),
    'mjolk': frozenset({'kondenserad', 'kondenserat', 'kondenserade',
                        'karamelliserad', 'karamelliserat', 'karamelliserade'}),
}

# Qualifier equivalents: if ingredient says "grekisk", product can have "turkisk" (and vice versa)
# Used in specialty qualifier check — these types are interchangeable in cooking
QUALIFIER_EQUIVALENTS: Dict[str, Set[str]] = {
    # Yoghurt types: grekisk ↔ turkisk ↔ matlagning are interchangeable in cooking
    'grekisk': {'grekisk', 'grekiska', 'greek', 'turkisk', 'turkiska', 'turkish', 'matlagning', 'matlagnings'},
    'grekiska': {'grekisk', 'grekiska', 'greek', 'turkisk', 'turkiska', 'turkish', 'matlagning', 'matlagnings'},
    'greek': {'grekisk', 'grekiska', 'greek', 'turkisk', 'turkiska', 'turkish', 'matlagning', 'matlagnings'},
    'turkisk': {'turkisk', 'turkiska', 'turkish', 'grekisk', 'grekiska', 'greek', 'matlagning', 'matlagnings'},
    'turkiska': {'turkisk', 'turkiska', 'turkish', 'grekisk', 'grekiska', 'greek', 'matlagning', 'matlagnings'},
    'turkish': {'turkisk', 'turkiska', 'turkish', 'grekisk', 'grekiska', 'greek', 'matlagning', 'matlagnings'},
    'matlagning': {'matlagning', 'matlagnings', 'grekisk', 'grekiska', 'greek', 'turkisk', 'turkiska', 'turkish'},
    # Lentil type names: "Beluga" = svarta linser
    'beluga': {'beluga', 'svart', 'svarta'},
    'matlagnings': {'matlagning', 'matlagnings', 'grekisk', 'grekiska', 'greek', 'turkisk', 'turkiska', 'turkish'},
    # Black adjective forms: lentils (beluga) + olives (kalamata/gemlik) + beans
    'svart': {'svart', 'svarta', 'beluga', 'kalamata', 'gemlik'},
    'svarta': {'svart', 'svarta', 'beluga', 'kalamata', 'gemlik'},
    'kalamata': {'svart', 'svarta', 'kalamata', 'gemlik', 'hummus'},
    'gemlik': {'svart', 'svarta', 'kalamata', 'gemlik'},
    'grön': {'grön', 'gröna', 'green', 'halkidiki', 'gordal', 'cerignola', 'nocellera', 'taggiasca', 'genovese', 'basilico', 'mix', 'haricot', 'brytbönor', 'brytbonor'},
    'gröna': {'grön', 'gröna', 'green', 'halkidiki', 'gordal', 'cerignola', 'nocellera', 'taggiasca', 'genovese', 'basilico', 'mix', 'haricot', 'brytbönor', 'brytbonor'},
    'haricot': {'grön', 'gröna', 'haricot', 'brytbönor', 'brytbonor'},
    'brytbönor': {'grön', 'gröna', 'haricot', 'brytbönor', 'brytbonor'},
    'brytbonor': {'grön', 'gröna', 'haricot', 'brytbönor', 'brytbonor'},
    # Paprika colors: gul/orange + mix equivalences (fresh bell peppers)
    'gul': {'gul', 'yellow', 'mix'},
    'orange': {'orange', 'mix'},
    'yellow': {'yellow', 'gul', 'mix'},
    # Mix = any color (paprika mix matches any color request, any color matches mix)
    'mix': {'mix', 'röd', 'rod', 'grön', 'gul', 'orange', 'red', 'green', 'yellow'},
    'halkidiki': {'grön', 'gröna', 'halkidiki', 'gordal', 'cerignola', 'nocellera', 'taggiasca'},
    'gordal': {'grön', 'gröna', 'halkidiki', 'gordal', 'cerignola', 'nocellera', 'taggiasca'},
    'cerignola': {'grön', 'gröna', 'halkidiki', 'gordal', 'cerignola', 'nocellera', 'taggiasca'},
    'nocellera': {'grön', 'gröna', 'halkidiki', 'gordal', 'cerignola', 'nocellera', 'taggiasca'},
    'taggiasca': {'grön', 'gröna', 'halkidiki', 'gordal', 'cerignola', 'nocellera', 'taggiasca'},
    # Pesto green variants: genovese, basilico = green pesto
    'genovese': {'grön', 'gröna', 'genovese', 'basilico'},
    'basilico': {'grön', 'gröna', 'genovese', 'basilico'},
    # Frozen equivalents: frysta ↔ fryst (adjective forms)
    'frysta': {'frysta', 'fryst'},
    'fryst': {'frysta', 'fryst'},
    # Cold-smoked salmon is an acceptable subtype of generic smoked salmon,
    # but hot-smoked salmon remains distinct.
    'rökt': {'rökt', 'rokt', 'kallrökt', 'kallrokt'},
    'rokt': {'rökt', 'rokt', 'kallrökt', 'kallrokt'},
    'kallrökt': {'kallrökt', 'kallrokt', 'rökt', 'rokt'},
    'kallrokt': {'kallrökt', 'kallrokt', 'rökt', 'rokt'},
    # Air-dried ham origins: a recipe saying "lufttorkad skinka" may accept the
    # named origins, but each named origin still requires itself when specified.
    'lufttorkad': {'lufttorkad', 'lufttorkade', 'lufttorkat', 'torkad', 'torkade', 'torkat', 'serrano', 'parma', 'prosciutto', 'iberico', 'pata negra', 'jamon'},
    'lufttorkade': {'lufttorkad', 'lufttorkade', 'lufttorkat', 'torkad', 'torkade', 'torkat', 'serrano', 'parma', 'prosciutto', 'iberico', 'pata negra', 'jamon'},
    'lufttorkat': {'lufttorkad', 'lufttorkade', 'lufttorkat', 'torkad', 'torkade', 'torkat', 'serrano', 'parma', 'prosciutto', 'iberico', 'pata negra', 'jamon'},
    'serrano': {'serrano', 'lufttorkad', 'lufttorkade', 'lufttorkat', 'torkad', 'torkade', 'torkat'},
    'parma': {'parma', 'lufttorkad', 'lufttorkade', 'lufttorkat', 'torkad', 'torkade', 'torkat'},
    'prosciutto': {'prosciutto', 'lufttorkad', 'lufttorkade', 'lufttorkat', 'torkad', 'torkade', 'torkat'},
    'iberico': {'iberico', 'lufttorkad', 'lufttorkade', 'lufttorkat', 'torkad', 'torkade', 'torkat'},
    'pata negra': {'pata negra', 'lufttorkad', 'lufttorkade', 'lufttorkat', 'torkad', 'torkade', 'torkat'},
    'jamon': {'jamon', 'lufttorkad', 'lufttorkade', 'lufttorkat', 'torkad', 'torkade', 'torkat'},
    # Parmesan ↔ parmigiano (space normalization converts parmesan → parmigiano in recipe text)
    'parmesan': {'parmesan', 'parmigiano', 'parmesanost'},
    'parmigiano': {'parmesan', 'parmigiano', 'parmesanost'},
    'spenat': {'spenat', 'spinaci'},
    'spinaci': {'spenat', 'spinaci'},
    'ostar': {'ostar', '4 ostar', 'fyra ostar', '5 ostar', 'fem ostar'},
    '4 ostar': {'ostar', '4 ostar', 'fyra ostar'},
    'fyra ostar': {'ostar', '4 ostar', 'fyra ostar'},
    '5 ostar': {'ostar', '5 ostar', 'fem ostar'},
    'fem ostar': {'ostar', '5 ostar', 'fem ostar'},
    # Curry paste colors: English ↔ Swedish
    # "Curry Paste Red" should match "röd currypasta" and vice versa
    'red': {'red', 'röd', 'röda', 'rött', 'rod', 'rott', 'rosso', 'mix'},
    'röd': {'red', 'röd', 'röda', 'rött', 'rod', 'rott', 'rosso', 'mix'},
    'röda': {'red', 'röd', 'röda', 'rött', 'rod', 'rott', 'rosso', 'mix'},
    'rött': {'red', 'röd', 'röda', 'rött', 'rod', 'rott', 'rosso', 'mix'},
    'rod': {'red', 'röd', 'röda', 'rött', 'rod', 'rott', 'rosso', 'mix'},
    'rott': {'red', 'röd', 'röda', 'rött', 'rod', 'rott', 'rosso', 'mix'},
    'rosso': {'red', 'röd', 'röda', 'rött', 'rod', 'rott', 'rosso', 'mix'},  # Italian red (pesto rosso)
    # White adjective forms: wine (vitt) + beans (vita)
    'vit': {'vit', 'vita', 'vitt'},
    'vita': {'vit', 'vita', 'vitt'},
    'vitt': {'vit', 'vita', 'vitt'},
    # Pickled/preserved forms: "inlagd gurka" = smörgåsgurka, ättiksgurka, saltgurka
    'inlagd': {'inlagd', 'inlagda', 'smörgås', 'smorgås', 'ättiks', 'attiks', 'salt', 'boston'},
    'inlagda': {'inlagd', 'inlagda', 'smörgås', 'smorgås', 'ättiks', 'attiks', 'salt', 'boston'},
    # Brown adjective forms: beans (bruna bönor)
    'brun': {'brun', 'bruna'},
    'bruna': {'brun', 'bruna'},
    # Cream cheese: English ↔ Swedish flavor names (bidirectional)
    'garlic': {'garlic', 'vitlök', 'vitlok'},
    'vitlök': {'vitlök', 'vitlok', 'garlic'},
    'vitlok': {'vitlök', 'vitlok', 'garlic'},
    'herbs': {'herbs', 'örter', 'orter'},
    'örter': {'örter', 'orter', 'herbs'},
    'orter': {'örter', 'orter', 'herbs'},
    # Mixed adjective forms: beans (blandade bönor)
    'blandad': {'blandad', 'blandade', 'mix'},
    'blandade': {'blandad', 'blandade', 'mix'},
    # Fermented bean forms: "jästa" and "fermenterade" are equivalent.
    'jäst': {'jäst', 'jästa', 'fermenterad', 'fermenterade'},
    'jästa': {'jäst', 'jästa', 'fermenterad', 'fermenterade'},
    'fermenterad': {'jäst', 'jästa', 'fermenterad', 'fermenterade'},
    'fermenterade': {'jäst', 'jästa', 'fermenterad', 'fermenterade'},
    'green': {'green', 'grön'},
    # Note: 'grön' already has olive equivalents above — curry paste qualifier check
    # uses Direction A which checks ingredient qualifier against product, so 'green'
    # in product name will match 'grön' in ingredient via these equivalents.
    'sweet': {'sweet', 'söt', 'sota'},
    'söt': {'sweet', 'söt', 'sota'},
    'sota': {'sweet', 'söt', 'sota'},
    # Vegetarian/vegan mince: "vegetarisk färs" ↔ "vegofärs" ↔ "växtbaserad färs"
    # Generic plant-based qualifiers are interchangeable with each other:
    'vegetarisk': {'vegetarisk', 'vegansk', 'vego', 'växtbaserad', 'vegetabilisk', 'baljväxt', 'quorn', 'soja'},
    'vegansk': {'vegetarisk', 'vegansk', 'vego', 'växtbaserad', 'vegetabilisk', 'baljväxt', 'quorn', 'soja'},
    'vego': {'vegetarisk', 'vegansk', 'vego', 'växtbaserad', 'vegetabilisk', 'baljväxt', 'quorn', 'soja'},
    'vegetabilisk': {'vegetarisk', 'vegansk', 'vego', 'växtbaserad', 'vegetabilisk', 'baljväxt', 'quorn', 'soja'},
    'växtbaserad': {'vegetarisk', 'vegansk', 'vego', 'växtbaserad', 'vegetabilisk', 'baljväxt', 'quorn', 'soja'},
    'soja': {'vegetarisk', 'vegansk', 'vego', 'växtbaserad', 'vegetabilisk', 'baljväxt', 'quorn', 'soja'},
    'baljväxt': {'vegetarisk', 'vegansk', 'vego', 'växtbaserad', 'vegetabilisk', 'baljväxt', 'quorn', 'soja'},
    # "formbar" is a FUNCTIONAL qualifier (moldable), NOT interchangeable with generic vegan.
    # "Formbar färs" must match products that are actually formbar (can be shaped into
    # patties/meatballs). Regular vegofärs/sojafärs is loose and cannot be formed.
    'formbar': {'formbar', 'formbara'},
    'formbara': {'formbar', 'formbara'},
    # "1 burk tomater" - product doesn't need to say "burk", any canned form suffices
    # NOTE: soltorkade/torkade REMOVED — sun-dried is NOT a "burk" product
    'burk': {'burk', 'konserverad', 'konserverade',
             'krossade', 'krossad', 'finkrossade', 'finkrossad',
             'passerade', 'passerad', 'skalade', 'skalad',
             'polpa', 'koncentrerade', 'koncentrerad'},
    # "konserverade tomater" — any canned product form is equivalent
    'konserverad': {'konserverad', 'konserverade', 'burk',
                    'krossade', 'krossad', 'finkrossade', 'finkrossad',
                    'passerade', 'passerad', 'skalade', 'skalad',
                    'polpa', 'koncentrerade', 'koncentrerad'},
    'konserverade': {'konserverad', 'konserverade', 'burk',
                     'krossade', 'krossad', 'finkrossade', 'finkrossad',
                     'passerade', 'passerad', 'skalade', 'skalad',
                     'polpa', 'koncentrerade', 'koncentrerad'},
    # Canned tomato forms: Direction B needs reverse mapping so "1 burk tomater"
    # satisfies Direction B for any specific canned form (passerade, krossade, etc.)
    'passerade': {'passerade', 'passerad', 'burk', 'konserverad', 'konserverade'},
    'passerad': {'passerade', 'passerad', 'burk', 'konserverad', 'konserverade'},
    'krossade': {'krossade', 'krossad', 'finkrossade', 'finkrossad', 'burk', 'konserverad', 'konserverade'},
    'krossad': {'krossade', 'krossad', 'finkrossade', 'finkrossad', 'burk', 'konserverad', 'konserverade'},
    'finkrossade': {'krossade', 'krossad', 'finkrossade', 'finkrossad', 'burk', 'konserverad', 'konserverade'},
    'finkrossad': {'krossade', 'krossad', 'finkrossade', 'finkrossad', 'burk', 'konserverad', 'konserverade'},
    'skalade': {'skalade', 'skalad', 'burk', 'konserverad', 'konserverade'},
    'skalad': {'skalade', 'skalad', 'burk', 'konserverad', 'konserverade'},
    'marinerad': {'marinerad', 'marinerade'},
    'marinerade': {'marinerad', 'marinerade'},
    # Cinnamon: "kanelstång" ↔ "Kanel Hel" (stick and whole are interchangeable)
    'stång': {'stång', 'stänger', 'hel'},
    'stänger': {'stång', 'stänger', 'hel'},
    'hel': {'stång', 'stänger', 'hel'},
    # Sun-dried tomatoes: recipe says "soltorkade", product may say "solt" or "secchi" (Italian)
    'soltorkade': {'soltorkade', 'soltorkad', 'solt', 'secchi'},
    'soltorkad': {'soltorkade', 'soltorkad', 'solt', 'secchi'},
    'solt': {'soltorkade', 'soltorkad', 'solt', 'secchi'},
    'secchi': {'soltorkade', 'soltorkad', 'solt', 'secchi'},
}
