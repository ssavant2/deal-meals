import re
from typing import Dict, List, Tuple

from .runtime_rule_overlays import SPACE_NORMALIZATION_CLI_UPDATES


# Space-variant normalizations: "corn flakes" (two words) = "cornflakes" (one word)
# Applied before compound word checking in keyword extraction and matching
_SPACE_NORMALIZATIONS: List[Tuple[str, str]] = [
    # Recipe wording "kokosnötsdryck" should hit the actual coconut-drink
    # family sold in stores, not whole coconut produce.
    ('kokosnötsdryck', 'kokosdryck'),
    ('kokosnotsdryck', 'kokosdryck'),
    ('kokosnöt dryck', 'kokosdryck'),
    ('kokosnot dryck', 'kokosdryck'),
    # Bread-yeast wording: exact baker's yeast for bread should stay distinct
    # from both generic yeast and sweet-dough yeast products.
    ('jäst för matbröd', 'matbrödsjäst'),
    ('jast for matbrod', 'matbrodsjast'),
    ('torrjäst för matbröd', 'matbrödsjäst'),
    ('torrjast for matbrod', 'matbrodsjast'),
    ('torrjäst matbröd', 'matbrödsjäst'),
    ('torrjast matbrod', 'matbrodsjast'),
    # Bao / steam buns are a dedicated bread family, not generic flatbread.
    ('steam buns bröd', 'steambuns'),
    ('steam buns brod', 'steambuns'),
    ('steam buns', 'steambuns'),
    ('bao buns bröd', 'steambuns'),
    ('bao buns brod', 'steambuns'),
    ('bao buns', 'steambuns'),
    ('bao bun', 'steambuns'),
    ('bao bröd', 'steambuns'),
    ('bao brod', 'steambuns'),
    # Fix split compound: "Zeta Sol torkade Tomater" → soltorkade
    ('sol torkade', 'soltorkade'),
    ('sol torkad', 'soltorkad'),
    ('torkad svamp', 'torkadsvamp'),
    ('torkade svampar', 'torkadsvamp'),
    # Savory spreads/dips should stay distinct from the raw ingredient family.
    ('creme av soltorkade tomater', 'soltorkadetomatcreme'),
    ('creme soltorkade tomater', 'soltorkadetomatcreme'),
    ('kräm av soltorkade tomater', 'soltorkadetomatcreme'),
    ('kräm soltorkade tomater', 'soltorkadetomatcreme'),
    ('kram av soltorkade tomater', 'soltorkadetomatcreme'),
    ('kram soltorkade tomater', 'soltorkadetomatcreme'),
    ('creme av kronärtskockor', 'kronärtskockscreme'),
    ('creme av kronärtskocka', 'kronärtskockscreme'),
    ('kräm av kronärtskockor', 'kronärtskockscreme'),
    ('kräm av kronärtskocka', 'kronärtskockscreme'),
    ('kram av kronärtskockor', 'kronärtskockscreme'),
    ('kram av kronärtskocka', 'kronärtskockscreme'),
    # Recipe shorthand for prepared horseradish on tube should not hit raw root.
    ('pepparrot på tub', 'pepparrotsvisp'),
    ('pepparrot, på tub', 'pepparrotsvisp'),
    ('pepparrot pa tub', 'pepparrotsvisp'),
    ('pepparrot, pa tub', 'pepparrotsvisp'),
    ('pepparrot i tub', 'pepparrotsvisp'),
    ('pepparrot, i tub', 'pepparrotsvisp'),
    # Q80-3: "Syrad grädde" is the soured-cream cooking ingredient — distinct from plain
    # grädde (matlagningsgrädde/vispgrädde) and not interchangeable. Existing PNB
    # grädde + 'syrad' already keeps plain grädde-ingredients away from Syrad-products;
    # this directional override makes the modifier-bearing ingredient route to its own
    # canonical so "Grädde Syrad 30% Arla" products can match it without affecting
    # plain grädde recipes. Both ingredient ('syrad grädde') and product
    # ('grädde syrad') word orders covered.
    ('syrad grädde', 'syradgrädde'),
    ('syrad gradde', 'syradgrädde'),
    ('grädde syrad', 'syradgrädde'),
    ('gradde syrad', 'syradgrädde'),
    ('corn flakes', 'cornflakes'),
    # "Mjöl Tipo 00" → specific keyword, should only match itself
    ('mjöl tipo 00', 'tipo00'),
    ('tipo 00', 'tipo00'),
    # "Chicken Nuggets" → compound keyword so 'chicken' alone doesn't match
    ('chicken nuggets', 'chickennuggets'),
    ('kyckling nuggets', 'kycklingnuggets'),
    ('kyckling steaks', 'kycklingsteaks'),
    ('kyckling steak', 'kycklingsteak'),
    ('coppa di parma', 'coppadiparma'),
    ('non stop', 'nonstop'),
    # Chocolate bars are often written with the colour after the product family
    # in scraped recipe text ("Chokladkaka Vit"). Route explicit colour forms
    # through the ordinary chocolate family so baking bars/buttons can satisfy
    # them while specialty qualifiers still keep white/dark/light apart.
    ('chokladkaka vit', 'vit choklad'),
    ('chokladkaka vitt', 'vit choklad'),
    ('vit chokladkaka', 'vit choklad'),
    ('chokladkaka mörk', 'mörk choklad'),
    ('chokladkaka mork', 'mörk choklad'),
    ('mörk chokladkaka', 'mörk choklad'),
    ('mork chokladkaka', 'mörk choklad'),
    ('chokladkaka ljus', 'ljus choklad'),
    ('ljus chokladkaka', 'ljus choklad'),
    # Blue cheese naming varies across recipes/offers. Normalize these surface
    # forms into the established ädelost family before validation.
    ('blåmögelost', 'ädelost'),
    ('grönmögelost', 'ädelost'),
    # "Lao Gan Ma" → join so keyword 'laoganma' is extracted and matches the brand
    ('lao gan ma', 'laoganma'),
    # Crispy chili oil is a specific condiment family, not fresh chili + oil.
    ('crispy chili in oil', 'crispychiliolja'),
    ('crispy chili oil', 'crispychiliolja'),
    ('crispy chilli in oil', 'crispychiliolja'),
    ('crispy chilli oil', 'crispychiliolja'),
    # "Wasabi Pasta" → join so FPB 'wasabipasta' blocker works (wasabi paste ≠ pasta noodles)
    ('wasabi pasta', 'wasabipasta'),
    # Brand fragment: "rogan josh-pasta" — hyphen splits into standalone "pasta"
    # which defeats pasta FPB (currypasta blocker). Join to prevent split.
    ('josh-pasta', 'joshpasta'),
    # Asian noodle types: join "nudlar udon" → "udonnudlar" so they bypass
    # the "nudlar" PROCESSED_FOODS block (cooking noodles, not instant)
    ('nudlar udon', 'udonnudlar'),
    ('udon nudlar', 'udonnudlar'),
    ('sanuki udon', 'udonnudlar'),
    ('nudlar soba', 'sobanudlar'),
    ('soba nudlar', 'sobanudlar'),
    ('nudlar somen', 'somennudlar'),
    ('somen nudlar', 'somennudlar'),
    ('nudlar ramen', 'ramennudlar'),
    ('ramen nudlar', 'ramennudlar'),
    ('nudlar shirataki', 'shirataki'),
    ('shirataki nudlar', 'shirataki'),
    ('rice noodles', 'risnudlar'),
    ('glass noodles', 'glasnudlar'),
    ('shanghai nudlar', 'shanghainudlar'),
    ('shanxi nudlar', 'shanxinudlar'),
    # Pickled cucumber: normalize all pickled-gurka variants to 'inlagdgurka' compound
    # So PNB can block plain "gurka" from pickled products while pickled recipes still match
    ('inlagd gurka', 'inlagdgurka'),
    # "Syrad gurka" is a specific fermented/pickled cucumber concept of its own.
    # Keep it distinct from both fresh cucumber and the standard inlagdgurka family.
    ('syrad gurka', 'syradgurka'),
    ('syrade gurkor', 'syradgurka'),
    ('gurka i lag', 'inlagdgurka'),
    ('tunnskivad gurka', 'tunnskivadgurka'),
    # "Franska Örter" — both words filtered (nationality + short), join to compound keyword
    ('franska örter', 'franskaörter'),
    # Preserve variant-specific keyword alongside inlagdgurka so FPB can isolate each type.
    # Put the specific keyword first so canonical selection returns the concrete variety.
    ('ättiksgurka', 'ättiksgurka inlagdgurka'),
    ('attiksgurka', 'attiksgurka inlagdgurka'),
    ('ättiksgurkor', 'ättiksgurka inlagdgurka'),
    ('attiksgurkor', 'attiksgurka inlagdgurka'),
    ('smörgåsgurka', 'smörgåsgurka inlagdgurka'),
    ('smorgasgurka', 'smorgasgurka inlagdgurka'),
    ('smörgåsgurkor', 'smörgåsgurka inlagdgurka'),
    ('smorgasgurkor', 'smorgasgurka inlagdgurka'),
    ('pressgurka', 'inlagdgurka'),
    # saltgurkor (plural) preserved alongside inlagdgurka so FPB can isolate saltgurka.
    # saltgurka (singular) already stays as-is (not normalized), matches via saltgurka keyword.
    ('saltgurkor', 'saltgurka inlagdgurka'),
    ('pickles', 'inlagdgurka'),
    ('pickle', 'inlagdgurka'),
    # Small pastry shell naming varies between Swedish krustader and French/English croustades.
    ('minikrustader', 'krustader'),
    ('mini krustader', 'krustader'),
    ('mini-krustader', 'krustader'),
    ('croustades', 'krustader'),
    ('croustade', 'krustader'),
    # Common recipe typos/split compounds that should map to the grocery product form.
    ('alfaalfagroddar', 'alfalfagroddar'),
    ('dinkel flingor', 'dinkelflingor'),
    # Swedish/English microwave-popcorn spelling variants are the same product.
    ('mikropopcorn', 'micropopcorn'),
    ('mikropop', 'micropop'),
    # Couscous variant spelling: "moghrabie" and "moghrabiah" are the same product family.
    ('moghrabie', 'moghrabiah'),
    # Recipe flour wording sometimes reverses the compound ("Vetemjöl Durum").
    ('vetemjöl durum', 'durumvetemjöl'),
    # Wheat-flour qualifiers should stay visible instead of collapsing into
    # plain wheat flour. "Special Fullkorn" counts as both special and fullkorn.
    ('vetemjöl special fullkorn', 'vetemjölspecial vetemjölfullkorn'),
    ('vetemjöl fullkorn special', 'vetemjölspecial vetemjölfullkorn'),
    ('vetemjöl special', 'vetemjölspecial'),
    ('vetemjöl fullkorn', 'vetemjölfullkorn'),
    # Sausage variants: "Salsiccia Fänkål" = fennel-flavored sausage, not fresh fennel
    # Burger buns: "Burger Bun Potato" = bread product, not burger patty
    ('burger buns', 'hamburgerbröd'),
    ('burger bun', 'hamburgerbröd'),
    ('potato buns', 'hamburgerbröd'),
    ('potato bun', 'hamburgerbröd'),
    ('sliderbröd', 'hamburgerbröd'),
    ('sliderbrod', 'hamburgerbröd'),
    ('slider buns', 'hamburgerbröd'),
    ('slider bun', 'hamburgerbröd'),
    ('minihamburgerbröd', 'hamburgerbröd'),
    ('minihamburgerbrod', 'hamburgerbröd'),
    ('mini hamburgerbröd', 'hamburgerbröd'),
    ('mini hamburgerbrod', 'hamburgerbröd'),
    ('salsiccia fänkål', 'salsicciafänkål'),
    ('salsiccia fankal', 'salsicciafankal'),
    ('salsiccia vitlök', 'salsicciavitlök'),
    ('salsiccia vitlok', 'salsicciavitlok'),
    ('salsiccia chili', 'salsicciachili'),
    # Q86-1: Tabasco normalization removed — when this ran before FPB
    # `pepparsås: {tabasco}`, the blocker became dead code. Stefan-policy:
    # Tabasco strikt isolerad från generic pepparsås (1 krm Tabasco = brand-specifik krydda).
    # "Flytande smör" in Swedish grocery recipes typically means the buyable
    # butter/rapeseed liquid cooking blend, not a block of solid butter.
    ('flytande smör', 'flytandesmör'),
    ('flytande smor', 'flytandesmör'),
    # "Veg bacon" (two words) → "vegobacon" so COMPOUND_STRICT blocks real bacon
    ('veg bacon', 'vegobacon'),
    ('veganskt bacon', 'vegobacon'),
    ('vegansk bacon', 'vegobacon'),
    ('vegan bacon', 'vegobacon'),
    ('vegetariskt bacon', 'vegobacon'),
    ('vegetarisk bacon', 'vegobacon'),
    # Flavor-specific mjukost compounds should expose both the carrier and the flavor
    # so carrier-specificity can require the right product variant.
    ('baconmjukost', 'bacon mjukost'),
    ('briesmak', 'brie'),
    # "Naturell fast tofu" → compound so COMPOUND_STRICT requires "naturell" in product
    ('naturell fast tofu', 'naturelltofu'),
    ('naturell tofu', 'naturelltofu'),
    ('fast naturell tofu', 'naturelltofu'),
    # "Rökt tofu" → compound so COMPOUND_STRICT requires "rökt" in product
    # Without this, "rökt" (stop word) is stripped and ALL tofu matches
    ('rökt tofu', 'rökttofu'),
    ('marinerad tofu', 'marineradtofu'),
    # Plant-based cream: drop visp/matlagning prefix so ANY växtbaserad cream matches
    ('växtbaserad vispgrädde', 'växtbaserad grädde'),
    ('växtbaserad matlagningsgrädde', 'växtbaserad grädde'),
    ('vegansk vispgrädde', 'vegansk grädde'),
    ('vegansk matlagningsgrädde', 'vegansk grädde'),
    # Generic plant-based milk/drink recipe lines should reach ordinary oat/soy/almond
    # drink products without falling back to dairy "mjölk".
    ('växtbaserad mjölk', 'växtdryck'),
    ('växtbaserad mjolk', 'växtdryck'),
    ('växtbaserad mjölkdryck', 'växtdryck'),
    ('växtbaserad mjolkdryck', 'växtdryck'),
    ('växtbaserad mjölkryck', 'växtdryck'),
    ('växtbaserad mjolkryck', 'växtdryck'),
    ('växtbaserad dryck', 'växtdryck'),
    ('vaxtbaserad mjölk', 'växtdryck'),
    ('vaxtbaserad mjolk', 'växtdryck'),
    ('vaxtbaserad mjölkdryck', 'växtdryck'),
    ('vaxtbaserad mjolkdryck', 'växtdryck'),
    ('vaxtbaserad mjölkryck', 'växtdryck'),
    ('vaxtbaserad mjolkryck', 'växtdryck'),
    ('vaxtbaserad dryck', 'växtdryck'),
    # Explicit gluten-free oats should stay distinct from ordinary oats.
    ('glutenfri havregryn', 'glutenfrihavregryn'),
    ('glutenfria havregryn', 'glutenfrihavregryn'),
    ('glutenfritt havregryn', 'glutenfrihavregryn'),
    ('havregryn glutenfri', 'glutenfrihavregryn'),
    ('havregryn glutenfria', 'glutenfrihavregryn'),
    ('havregryn glutenfritt', 'glutenfrihavregryn'),
    # Recipe shorthand for vegetarian burgers should stay on vegetarian burger
    # families and not fall back to generic meat/chicken/fish burgers.
    ('veg. hamburgare', 'vegetariskhamburgare'),
    ('veg hamburgare', 'vegetariskhamburgare'),
    ('vegetarisk hamburgare', 'vegetariskhamburgare'),
    ('vegetariska hamburgare', 'vegetariskhamburgare'),
    ('beyond burgers', 'beyondburgare'),
    ('beyond burger', 'beyondburgare'),
    # Plant-based "butter" recipe wording routes to vegomargarin compound so that
    # KSBC can distinguish it from dairy margarin (Q71-1). The compound keyword
    # vegomargarin is exposed by plant-based margarin offers (Växtbaserat/Lätta/Flora/Milda).
    ('växtbaserat smör', 'vegomargarin'),
    ('vaxtbaserat smor', 'vegomargarin'),
    ('veganskt smör', 'vegomargarin'),
    ('veganskt smor', 'vegomargarin'),
    ('vegosmör', 'vegomargarin'),
    ('vegosmor', 'vegomargarin'),
    ('vegasmör', 'vegomargarin'),
    ('vegansmör', 'vegomargarin'),
    ('vegansmor', 'vegomargarin'),
    # Plural → singular for vego-compounds so COMPOUND_STRICT can match suffix
    ('vegokorvar', 'vegokorv'),
    # Mathem generic category "Biffar/Bullar" — too generic, remove "biff" substring
    ('biffar/bullar', 'vegobullar'),
    # Snack products: join so PROCESSED_FOODS can block them
    ('pommes sticks', 'pommessticks'),
    # Salami chips are a bought snack ingredient in a small number of recipes.
    # Keep them as a specific compound so plain chips do not match.
    ('salami chips', 'salamichips'),
    # Flavored snacks: "tortillachips ost" = cheese-flavored chips, not ost ingredient
    ('tortillachips ost', 'tortillachipsost'),
    ('nachos ost', 'nachosost'),
    # Generic mixed-berry recipe lines should reach grocery berry-mix products.
    ('blandade bär', 'bärmix'),
    # Swedish fresh-chili wording: colored "peppar" and "spansk peppar" in
    # grocery recipe language mean fresh chili peppers, matching how stores
    # name Class 1 produce offers.
    ('röd peppar', 'röd chilipeppar'),
    ('rod peppar', 'rod chilipeppar'),
    ('grön peppar', 'grön chilipeppar'),
    ('gron peppar', 'gron chilipeppar'),
    ('gul peppar', 'gul chilipeppar'),
    ('spansk peppar', 'chilipeppar'),
    # Some source recipes use English fresh-chili wording. Keep these on the
    # existing fresh produce family rather than opening branded "Green Chili"
    # seasoning products.
    ('green chili', 'grön chilipeppar'),
    ('green chilli', 'grön chilipeppar'),
    ('red chili', 'röd chilipeppar'),
    ('red chilli', 'röd chilipeppar'),
    ('chilifrukt', 'chilipeppar'),
    ('chilifrukter', 'chilipeppar'),
    # Recipe wording for New Zealand green-shell mussels should hit the existing
    # grönmusslor family instead of falling back to generic/blåmusslor.
    ('green shell musslor', 'grönmusslor'),
    ('greenshell musslor', 'grönmusslor'),
    ('green shell mussla', 'grönmusslor'),
    ('greenshell mussla', 'grönmusslor'),
    ('chorizokorv', 'chorizo'),
    ('chorizokorvar', 'chorizo'),
    # "sockerkaksbotten" is a sponge-cake base and should reuse existing tårtbotten coverage
    ('sockerkaksbotten', 'tårtbotten'),
    # Candy: "turkisk peppar" = Fazer candy, not Turkish pepper spice
    ('turkisk peppar', 'turkiskpeppar'),
    # Ice cream: "Vanilj Glass" → "vaniljglass" so it matches recipe keyword
    ('vanilj glass', 'vaniljglass'),
    ('choklad glass', 'chokladglass'),
    ('jordgubb glass', 'jordgubbsglass'),
    ('blåbär glass', 'blåbärsglass'),
    # English coconut products → Swedish compound words
    ('coconut milk', 'kokosmjölk'),
    ('coconut cream', 'kokosgrädde'),
    ('coconut oil', 'kokosolja'),
    ('coconut flakes', 'kokosflingor'),
    # English cream cheese → Swedish färskost
    ('cream cheese', 'färskost'),
    # English sesame oil → Swedish
    ('sesame oil', 'sesamolja'),
    # Common typo in recipe text
    ('citronjucie', 'citronjuice'),
    # Exact cocktail/cooking ingredient: keep "liquid smoke" together so it
    # matches the real product and does not fall back to generic hickory BBQ items.
    ('liquid smoke', 'liquidsmoke'),
    # Soft-drink/cocktail family: treat "ginger ale" as one compound so both
    # recipe and product extraction keep a usable keyword.
    ('ginger ale', 'gingerale'),
    # Swedish spelling variant for the same cocktail syrup family.
    ('grenadin', 'grenadine'),
    # Salt-cured pork should keep its own exact identity instead of degrading
    # to plain fresh pork cuts.
    ('rimmat fläsk', 'rimmatfläsk'),
    ('rimmat flask', 'rimmatfläsk'),
    ('fläsk rimmat', 'rimmatfläsk'),
    ('flask rimmat', 'rimmatfläsk'),
    # Frozen fruit mixes sold as "Frukt till smoothie(s)" should keep their own
    # exact identity instead of disappearing when "smoothie" is treated as a
    # generic drink word elsewhere.
    ('frukt till smoothie', 'smoothiefrukt'),
    ('frukt till smoothies', 'smoothiefrukt'),
    # Oat-based barista drinks should stay in their own exact family instead of
    # broadening through generic "dryck" or plain "havredryck".
    ('havrebaserad dryck barista', 'havredryckbarista'),
    ('havredryck barista', 'havredryckbarista'),
    ('havredryck, baristatyp', 'havredryckbarista'),
    ('havredryck baristatyp', 'havredryckbarista'),
    ('barista havredryck', 'havredryckbarista'),
    ('havredryck professional barista', 'havredryckbarista'),
    ('havredryck ikaffe barista', 'havredryckbarista'),
    ('havredryck ikaffe', 'havredryckbarista'),
    # Swedish oil compounds sometimes appear split in recipe text
    ('linfrö olja', 'linfröolja'),
    ('linfro olja', 'linfroolja'),
    # Crushed ice should keep its own exact identity instead of disappearing as
    # a short generic "is" token.
    ('krossad is', 'krossadis'),
    # Caramelized/condensed milk should stay in their own specific families.
    # "dulce de leche" is the same product family as Swedish "karamelliserad mjölk".
    ('dulce de leche', 'karamelliseradmjölk'),
    ('karamelliserad mjölk', 'karamelliseradmjölk'),
    ('karamelliserad mjolk', 'karamelliseradmjolk'),
    ('kondenserad mjölk', 'kondenseradmjölk'),
    ('kondenserad mjolk', 'kondenseradmjolk'),
    # English sushi rice → Swedish compound
    ('sushi rice', 'sushiris'),
    # Broth/stock compounds
    ('grönsaks buljong', 'grönsaksbuljong'),
    ('kyckling buljong', 'kycklingbuljong'),
    ('höns buljong', 'hönsbuljong'),
    ('fisk buljong', 'fiskbuljong'),
    ('svamp buljong', 'svampbuljong'),
    ('kött buljong', 'köttbuljong'),
    ('ox buljong', 'oxbuljong'),
    ('lant buljong', 'lantbuljong'),
    ('skaldjurs buljong', 'skaldjursbuljong'),
    ('buljong grönsak', 'grönsaksbuljong'),
    ('buljong kyckling', 'kycklingbuljong'),
    ('buljong kött', 'köttbuljong'),
    ('buljong höns', 'hönsbuljong'),
    ('buljong fisk', 'fiskbuljong'),
    ('buljong svamp', 'svampbuljong'),
    ('buljong ox', 'oxbuljong'),
    ('buljong skaldjur', 'skaldjursbuljong'),
    # Köttbullar with meat type
    ('kyckling köttbullar', 'kycklingköttbullar'),
    ('köttbullar kyckling', 'kycklingköttbullar'),
    ('kalkon köttbullar', 'kalkonköttbullar'),
    ('köttbullar kalkon', 'kalkonköttbullar'),
    # Curry paste types
    ('grön currypasta', 'gröncurrypasta'),
    ('gron currypasta', 'gröncurrypasta'),
    ('röd currypasta', 'rödcurrypasta'),
    ('rod currypasta', 'rödcurrypasta'),
    ('gul currypasta', 'gulcurrypasta'),
    ('grön curry', 'gröncurry'),
    ('röd curry', 'rödcurry'),
    ('gul curry', 'gulcurry'),
    ('red curry paste', 'rödcurrypasta'),
    ('green curry paste', 'gröncurrypasta'),
    ('yellow curry paste', 'gulcurrypasta'),
    ('currypaste', 'currypasta'),
    ('curry paste', 'currypasta'),
    ('curry pasta', 'currypasta'),
    # Condiment compounds
    ('mango chutney', 'mangochutney'),
    ('go chu jang', 'gochujang'),
    ('go-chu-jang', 'gochujang'),
    ('gochujang pasta', 'gochujangpasta'),
    ('orange juice', 'apelsinjuice'),
    ('apelsin dryck', 'apelsinläsk'),
    ('apelsindryck', 'apelsinläsk'),
    ('apelsin lask', 'apelsinläsk'),
    ('orange soda', 'apelsinläsk'),
    ('fanta orange', 'apelsinläsk'),
    ('äppelcider vinäger', 'äppelcidervinäger'),
    ('appelcider vinager', 'äppelcidervinäger'),
    # Common typo/variant in recipe text: still means plain rice vinegar.
    ('risvinsvinäger', 'risvinäger'),
    ('risvinsvinager', 'risvinager'),
    ('libabröd', 'tunnbröd'),
    ('libabrod', 'tunnbrod'),
    # Keep the snack as a real ingredient compound instead of dropping both words
    # through generic salt/shape stop words.
    ('salta pinnar', 'saltapinnar'),
    ('taleggio-ost', 'taleggioost'),
    ('taleggio ost', 'taleggioost'),
    ('worcestershire sauce', 'worcestersås'),
    ('worcestershiresås', 'worcestersås'),
    ('worcestershiresas', 'worcestersas'),
    ('hoisin sauce', 'hoisinsås'),
    ('hoisin sås', 'hoisinsås'),
    ('hoisin sas', 'hoisinsås'),
    ('sötsur sås', 'sötsursås'),
    ('sotsur sas', 'sötsursås'),
    ('sweet & sour sauce', 'sötsursås'),
    ('sweet & sour sås', 'sötsursås'),
    ('sweet and sour sauce', 'sötsursås'),
    ('sweet sour sauce', 'sötsursås'),
    ('sweet sour sås', 'sötsursås'),
    ('alkoholfri öl', 'alkoholfriöl'),
    ('alkoholfri ol', 'alkoholfriöl'),
    ('alkfri öl', 'alkoholfriöl'),
    ('alkfri ol', 'alkoholfriöl'),
    # Whole spices
    ('kryddpepparkorn', 'kryddpeppar hel'),
    ('vitpepparkorn', 'vitpeppar hel'),
    ('paprikakrydda', 'paprikapulver'),
    ('tacokrydda', 'taco kryddmix'),  # "tacokrydda" = taco seasoning mix — STRICT kryddmix PPR requires "kryddmix" in ingredient
    ('guacamole-mix', 'guacamole kryddmix'),
    ('guacamole mix', 'guacamole kryddmix'),
    ('guacamolemix', 'guacamole kryddmix'),
    ('tacochips', 'nachochips'),
    ('taco chips', 'nachochips'),
    ('five spice-kryddmix', 'fivespicekryddmix'),
    ('five spice kryddmix', 'fivespicekryddmix'),
    ('five spice-krydda', 'fivespicekryddmix'),
    ('five spice krydda', 'fivespicekryddmix'),
    ('vegetariska pieces/bitar', 'vegobitar'),
    ('vegetariska bitar', 'vegobitar'),
    ('vegetariska pieces', 'vegobitar'),
    ('vegetarisk kebab', 'vegokebab'),
    ('vegetariska kebab', 'vegokebab'),
    ('vegansk kebab', 'vegokebab'),
    ('vego kebab', 'vegokebab'),
    ('grytbitar av quorn', 'quornbitar'),
    ('machesallad', 'machesallat'),
    ('mache sallad', 'machesallat'),
    ('maché sallad', 'machesallat'),
    ('mache', 'machesallat'),
    ('maché', 'machesallat'),
    ('black eye böna', 'blackeyeböna'),
    ('black eye bönor', 'blackeyebönor'),
    ('black eye bona', 'blackeyebona'),
    ('black eye bonor', 'blackeyebonor'),
    ('haricoverts', 'haricot'),
    ('fänkål krydda', 'fänkålsfrö'),
    ('fankal krydda', 'fankalsfro'),
    ('lime pepper krydda', 'limepepper'),
    ('lime pepper', 'limepepper'),
    ('tom kha gai', 'tomkha'),
    ('tom kha', 'tomkha'),
    ('wok grönsaker', 'wokgrönsaker'),
    ('wok gronsaker', 'wokgrönsaker'),
    ('wok mix vegetables', 'wokmix'),
    ('wok mix', 'wokmix'),
    ('smör- & rapsolja', 'smörrapsolja'),
    ('smör & rapsolja', 'smörrapsolja'),
    ('smör och rapsolja', 'smörrapsolja'),
    ('smör-rapsolja', 'smörrapsolja'),
    ('smor- & rapsolja', 'smörrapsolja'),
    ('smor & rapsolja', 'smörrapsolja'),
    ('smor och rapsolja', 'smörrapsolja'),
    ('smor-rapsolja', 'smörrapsolja'),
    ('sriracha mayo', 'chilimajo'),
    ('sriracha majonnäs', 'chilimajo'),
    ('sriracha majonnas', 'chilimajo'),
    ('chilimajonnäs', 'chilimajo'),
    ('chilimajonnas', 'chilimajo'),
    ('pasta basilico krydda', 'pastakrydda basilico'),
    ('pesto basilico', 'basilikapesto'),
    ('kanel hel', 'kanelhel'),
    ('fraîche', 'fraiche'),
    ('crème', 'creme'),
    ('chilli', 'chili'),  # double-l spelling variant common in recipes
    ('baugette', 'baguette'),
    ('baugetter', 'baguetter'),
    ('surdegsbaugette', 'surdegsbaguette'),
    ('surdegsbaugetter', 'surdegsbaguetter'),
    # Ginger ingredient lines separate into two distinct families:
    # - syltad (candied/sweet) → baking/dessert use
    # - picklad/inlagd (vinegar-pickled/salt) → sushi/Asian dish use
    # Conflating them in one canonical caused FP between e.g. panettone recipes
    # and sushi gari products. Kept as separate canonical families.
    # Red/black rom (fish roe): "röd rom" → "rödrom" + keep 'rom' so generic rom
    # keyword still extracts. PNB rom ← finkorning/stenbitsrom etc blocks plain rom
    # match path, so 'rödrom'/'svartrom' becomes a specific match anchor (analogous
    # to sojagrädde/havregrädde pattern in Q96-3). Mirrored on the offer side by a
    # post-extraction color-tagger in extraction.py.
    ('röd rom', 'rödrom rom'),
    ('rod rom', 'rodrom rom'),
    ('svart rom', 'svartrom rom'),
    ('syltad ingefära', 'syltadingefära'),
    ('syltad ingefara', 'syltadingefara'),
    ('picklad ingefära', 'pickladingefära'),
    ('picklad ingefara', 'pickladingefara'),
    ('inlagd ingefära', 'pickladingefära gari'),
    ('inlagd ingefara', 'pickladingefara gari'),
    # Skånsk senap: both word orders → compound (product names use both orderings)
    ('skånsk senap', 'skånsksenap'),
    ('senap skånsk', 'skånsksenap'),
    # Recipe wording "fransk senap" means Dijon/French-style mustard, not
    # ordinary sweet/standard yellow mustard.
    ('fransk senap', 'dijonsenap'),
    ('french mustard', 'dijonsenap'),
    ('dijon senap', 'dijonsenap'),
    ('sirap agave', 'agavesirap'),
    ('agave sirap', 'agavesirap'),
    ('sirap granatäpple', 'granatäppelsirap'),
    ('sirap granatappel', 'granatappelsirap'),
    ('muscavadosocker', 'muscovadosocker'),
    # Pulled products
    ('pulled beef', 'pulledbeef'),
    ('pulled pork', 'pulledpork'),
    ('pulled chicken', 'pulledchicken'),
    ('pulled oumph', 'pulledoumph'),
    # Parmesan, cream, mayo synonyms
    ('parmesanost', 'parmigiano'),
    ('parmesan', 'parmigiano'),
    ('matgrädde', 'matlagningsgrädde'),
    ('matgradde', 'matlagningsgradde'),
    ('vegansk majonnäs', 'veganskmajonnäs'),
    ('vegansk majonnas', 'veganskmajonnäs'),
    ('vegansk mayo', 'veganskmajonnäs'),
    ('vegan mayo', 'veganskmajonnäs'),
    ('plant based mayo', 'veganskmajonnäs'),
    ('plant-based mayo', 'veganskmajonnäs'),
    ('mayonnaise', 'majonnäs'),
    ('majonäs', 'majonnäs'),
    # Chicken and turkey normalization
    ('kyckling hel', 'helkyckling'),
    ('hel kyckling', 'helkyckling'),
    ('kyckling fryst hel', 'helkyckling'),
    ('kyckling färsk hel', 'helkyckling'),
    ('kyckling farsk hel', 'helkyckling'),
    ('kalkon hel', 'helkalkon'),
    ('hel kalkon', 'helkalkon'),
    ('kalkon fryst hel', 'helkalkon'),
    ('kalkon färsk hel', 'helkalkon'),
    ('kalkon farsk hel', 'helkalkon'),
    ('kyckling bröstfilé', 'kycklingfilé'),
    ('kyckling bröstfilè', 'kycklingfilé'),
    ('kyckling bröstfile', 'kycklingfilé'),
    ('bröstfilé kyckling', 'kycklingfilé'),
    ('bröstfilè kyckling', 'kycklingfilé'),
    ('bröstfile kyckling', 'kycklingfilé'),
    ('kyckling innerfilé', 'kycklingfilé'),
    ('kyckling innerfile', 'kycklingfilé'),
    ('innerfilé kyckling', 'kycklingfilé'),
    ('innerfile kyckling', 'kycklingfilé'),
    ('kyckling lårfilé', 'kycklingfilé'),
    ('kyckling lårfile', 'kycklingfilé'),
    ('kyckling larfilé', 'kycklingfilé'),
    ('kyckling larfile', 'kycklingfilé'),
    ('lårfilé kyckling', 'kycklingfilé'),
    ('lårfile kyckling', 'kycklingfilé'),
    ('larfilé kyckling', 'kycklingfilé'),
    ('larfile kyckling', 'kycklingfilé'),
    ('kyckling filé', 'kycklingfilé'),
    ('kyckling file', 'kycklingfilé'),
    ('filé kyckling', 'kycklingfilé'),
    ('file kyckling', 'kycklingfilé'),
    ('kyckling minutfilé', 'kycklingfilé'),
    ('kyckling minutfile', 'kycklingfilé'),
    ('minutfilé kyckling', 'kycklingfilé'),
    ('minutfile kyckling', 'kycklingfilé'),
    ('kycklingbröstfiléer', 'kycklingfilé'),
    ('kycklingbröstfilé', 'kycklingfilé'),
    ('kycklingbröstfile', 'kycklingfilé'),
    ('kycklingbrostfilé', 'kycklingfilé'),
    ('kycklingbrostfile', 'kycklingfilé'),
    ('kycklinginnerfiléer', 'kycklingfilé'),
    ('kycklinginnerfilé', 'kycklingfilé'),
    ('kycklinginnerfile', 'kycklingfilé'),
    ('kycklinglårfiléer', 'kycklingfilé'),
    ('kycklinglårfilé', 'kycklingfilé'),
    ('kycklinglårfile', 'kycklingfilé'),
    ('kycklinglarfiléer', 'kycklingfilé'),
    ('kycklinglarfilé', 'kycklingfilé'),
    ('kycklinglarfile', 'kycklingfilé'),
    ('kycklingfiléer', 'kycklingfilé'),
    ('kycklinginnerf grillad', 'färdigkyckling'),
    ('kycklinginnerf', 'kycklingfilé'),
    ('kycklinglårfil', 'kycklingfilé'),
    ('kycklinglarfil', 'kycklingfilé'),
    ('kycklinglårf', 'kycklingfilé'),
    ('kycklinglarf', 'kycklingfilé'),
    ('kycklingschnit', 'kycklingschnitzel'),
    ('kycklingbröst', 'kycklingfilé'),
    ('kycklingbrost', 'kycklingfilé'),
    ('höns bröstfilé', 'kycklingfilé'),
    ('höns bröstfile', 'kycklingfilé'),
    ('bröstfilé höns', 'kycklingfilé'),
    ('bröstfile höns', 'kycklingfilé'),
    ('hönsbröstfiléer', 'kycklingfilé'),
    ('hönsbröstfilé', 'kycklingfilé'),
    ('hönsbröstfile', 'kycklingfilé'),
    ('hönsbrostfiléer', 'kycklingfilé'),
    ('hönsbrostfilé', 'kycklingfilé'),
    ('hönsbrostfile', 'kycklingfilé'),
    ('hönsbröst', 'kycklingfilé'),
    ('hönsbrost', 'kycklingfilé'),
    ('hons bröstfilé', 'kycklingfilé'),
    ('hons bröstfile', 'kycklingfilé'),
    ('bröstfilé hons', 'kycklingfilé'),
    ('bröstfile hons', 'kycklingfilé'),
    ('honsbröstfiléer', 'kycklingfilé'),
    ('honsbröstfilé', 'kycklingfilé'),
    ('honsbröstfile', 'kycklingfilé'),
    ('honsbrostfiléer', 'kycklingfilé'),
    ('honsbrostfilé', 'kycklingfilé'),
    ('honsbrostfile', 'kycklingfilé'),
    ('honsbröst', 'kycklingfilé'),
    ('honsbrost', 'kycklingfilé'),
    ('kycklinglår', 'kycklingfilé'),
    ('kycklinglar', 'kycklingfilé'),
    ('kyckling ben', 'kycklingben'),
    ('kyckling klubba', 'kycklingklubba'),
    ('kyckling klubbor', 'kycklingklubba'),
    ('kycklingklubbor', 'kycklingklubba'),
    ('kyckling vingar', 'kycklingvinge'),
    ('kyckling vinge', 'kycklingvinge'),
    ('kycklingvingar', 'kycklingvinge'),
    ('kyckling lår', 'kycklinglår'),
    ('kyckling lar', 'kycklinglår'),
    ('kyckling färs', 'kycklingfärs'),
    ('kyckling fars', 'kycklingfärs'),
    ('kyckling hjärta', 'kycklinghjärta'),
    ('kyckling mage', 'kycklingmage'),
    ('kyckling spett', 'kycklingspett'),
    ('buffalo wings', 'kycklingvinge'),
    ('buffalo wing', 'kycklingvinge'),
    ('färdiggrillad kyckling', 'färdigkyckling'),
    ('fardiggrillad kyckling', 'färdigkyckling'),
    ('färdigstekt kyckling', 'färdigkyckling'),
    ('fardigstekt kyckling', 'färdigkyckling'),
    ('grillad kyckling', 'färdigkyckling'),
    ('kyckling grillad', 'färdigkyckling'),
    ('kycklingfilé grillad', 'färdigkyckling'),
    ('kycklingfile grillad', 'färdigkyckling'),
    ('stekt kyckling', 'färdigkyckling'),
    ('tillagad kyckling', 'färdigkyckling'),
    ('salladskyckling', 'färdigkyckling'),
    ('sallads kyckling', 'färdigkyckling'),
    # Pork cuts
    ('fläsk ytterfilé', 'fläskytterfilé'),
    ('fläsk ytterfile', 'fläskytterfilé'),
    ('flask ytterfilé', 'fläskytterfilé'),
    ('flask ytterfile', 'fläskytterfilé'),
    ('fläsk karré', 'fläskkarré'),
    ('flask karré', 'fläskkarré'),
    ('flask karre', 'fläskkarré'),
    ('fläsk filé', 'fläskfilé'),
    ('fläsk file', 'fläskfilé'),
    ('flask filé', 'fläskfilé'),
    ('flask file', 'fläskfilé'),
    ('lime blad', 'limeblad'),
    ('persilja blad', 'bladpersilja'),
    ('storbladig persilja', 'bladpersilja'),
    # Pasta types → generic "pasta"
    ('penne', 'pasta'),
    ('fusilli', 'pasta'),
    ('rigatoni', 'pasta'),
    ('farfalle', 'pasta'),
    ('conchiglie', 'pasta'),
    ('conchigle', 'pasta'),
    ('gemelli', 'pasta'),
    ('radiatori', 'pasta'),
    ('tortiglioni', 'pasta'),
    ('caserecce', 'pasta'),
    ('girandole', 'pasta'),
    ('strozzapreti', 'pasta'),
    ('strozzapretti', 'pasta'),
    ('mafalda', 'pasta'),
    ('pastamore', 'pasta'),
    ('chili flakes', 'chiliflakes'),
    ('chiliflingor', 'chiliflakes'),
    ('chili flingor', 'chiliflakes'),
    ('chilipulver', 'chili pulver'),
    # Gluten-free flour mixes are sold as "mjölmix" while recipes often say
    # the shorter "glutenfri mix".
    ('glutenfri mix', 'mjölmix'),
    # Wine
    ('mousserande vitt vin', 'mousserandevin vitt'),
    ('mousserande vin', 'mousserandevin'),
    ('vitt vin', 'vitt matlagningsvin'),
    ('rött vin', 'rött matlagningsvin'),
    ('rödvin', 'rött matlagningsvin'),
    ('rodvin', 'rött matlagningsvin'),
    ('vitvin', 'vitt matlagningsvin'),
    # Onion, potato, garlic, etc.
    ('lök schalotten', 'schalottenlök'),
    ('lök bananschalotten', 'schalottenlök'),
    ('lök pulver', 'lökpulver'),
    ('potatis sparris', 'sparrispotatis'),
    ('vitlöksklyfta', 'vitlök klyfta'),
    ('vitlöksklyftor', 'vitlök klyftor'),
    ('vitlöksklyft', 'vitlök klyft'),
    ('vitloksklyfta', 'vitlök klyfta'),
    ('vitloksklyftor', 'vitlök klyftor'),
    ('vitloksklyft', 'vitlök klyft'),
    ('röd lök', 'rödlök'),
    ('röda lökar', 'rödlök'),
    ('rod lok', 'rödlök'),
    ('roda lokar', 'rödlök'),
    ('valnöt', 'valnötter'),
    ('valnot', 'valnötter'),
    ('sötmandel spån', 'mandelspån'),
    ('sotmandel span', 'mandelspån'),
    ('flagad mandel', 'mandelspån'),
    ('mandelsplitter', 'mandelspån'),
    ('havreflingor', 'havregryn'),
    ('stjälkselleri', 'bladselleri'),
    ('stjalkselleri', 'bladselleri'),
    ('stjälk selleri', 'bladselleri'),
    ('stjalk selleri', 'bladselleri'),
    ('selleristjälkar', 'bladselleri'),
    ('selleristjalkar', 'bladselleri'),
    ('selleristjälk', 'bladselleri'),
    ('selleristjalk', 'bladselleri'),
    ('blekselleristjälkar', 'bladselleri'),
    ('blekselleristjälk', 'bladselleri'),
    ('blekselleri', 'bladselleri'),
    ('lasagneplatta', 'lasagneplattor'),
    ('pastaplattor', 'lasagneplattor'),
    ('pasta lasagneplattor', 'lasagneplattor'),
    ('barbequesås', 'bbqsås'),
    ('barbecuesås', 'bbqsås'),
    ('bbq-sås', 'bbqsås'),
    ('bbq sås', 'bbqsås'),
    ('bbq-krydda', 'bbqkrydda'),
    ('sweet chili', 'sweet chilisås'),
    ('chili/limesås', 'lime chilisås'),
    ('chili/limesas', 'lime chilisås'),
    ('pizza sauce', 'pizzasås'),
    ('taco sauce', 'tacosås'),
    ('piri piri', 'piripiri'),
    ('piri-piri', 'piripiri'),
    ('morötter', 'morot'),
    ('morotter', 'morot'),
    ('morätter', 'morot'),
    ('moratter', 'morot'),
    ('babymorötter', 'babymorot'),
    ('babymorotter', 'babymorot'),
    ('snackmorötter', 'snackmorot'),
    ('snackmorotter', 'snackmorot'),
    ('äpplen', 'äpple'),
    ('applen', 'äpple'),
    ('jordärtskockor', 'jordärtskocka'),
    ('jordartskockor', 'jordärtskocka'),
    ('rödbetor', 'rödbeta'),
    ('rodbetor', 'rödbeta'),
    ('palsternackor', 'palsternacka'),
    ('kronärtskockor', 'kronärtskocka'),
    ('kronartskockor', 'kronärtskocka'),
    ('kronärtskockshjärtan', 'kronärtskockshjärta'),
    ('kronartskockshjärtan', 'kronärtskockshjärta'),
    ('kronartskockshjartan', 'kronärtskockshjärta'),
    ('paprikor', 'paprika'),
    ('gurkor', 'gurka'),
    ('citroner', 'citron'),
    ('apelsiner', 'apelsin'),
    ('limefrukter', 'lime'),
    ('persikor', 'persika'),
    ('kålrötter', 'kålrot'),
    ('kalrotter', 'kålrot'),
    ('gula ärter', 'gulaärtor'),
    ('gula ärtor', 'gulaärtor'),
    ('gula arter', 'gulaärtor'),
    ('gula artor', 'gulaärtor'),
    ('gulärt', 'gulaärtor'),
    ('gulart', 'gulaärtor'),
    ('gulärtor', 'gulaärtor'),
    ('gulartor', 'gulaärtor'),
    ('sju kryddor', 'sjukryddor'),
    ('pak choi', 'pakchoi'),
    ('pak choy', 'pakchoy'),  # English/UK spelling; keyword_synonym then rolls to pakchoi
    ('bananschalottenlök', 'schalottenlök'),
    ('bananschalottenlökar', 'schalottenlök'),
    ('bananscharlottenlök', 'schalottenlök'),
    ('bananscharlottenlökar', 'schalottenlök'),  # typo: 'charl' instead of 'chal'
    ('lemon curd', 'lemoncurd'),
    ('raw slaw', 'råkostsallad'),
    ('råkost sallad', 'råkostsallad'),
    ('rakost sallad', 'råkostsallad'),
    ('västerbottens ost', 'västerbottensost'),
    ('västerbotten ost', 'västerbottensost'),
    ('västerbottenost', 'västerbottensost'),
    ('vasterbottens ost', 'västerbottensost'),
    ('vasterbotten ost', 'västerbottensost'),
    ('vasterbottenost', 'västerbottensost'),
    ('melon honung', 'honungsmelon'),
    ('melon galia', 'galiamelon'),
    ('carnaroli ris', 'risottoris'),
    ('arborio ris', 'risottoris'),
    ('avorio ris', 'risottoris'),
    ('vialone nano', 'vialonenano'),
    ('vialone nano ris', 'risottoris'),
    ('torskryggfilé', 'torskrygg'),
    ('torskryggfile', 'torskrygg'),
    ('sugar snap peas', 'sugarsnaps'),
    ('sugar snaps', 'sugarsnaps'),
    ('sugar snap', 'sugarsnaps'),
    ('raw cacao powder', 'kakao'),
    ('raw cocoa powder', 'kakao'),
    ('cacao powder', 'kakao'),
    ('cocoa powder', 'kakao'),
    ('noodles cut', 'äggnudlar'),
    ('noodles quick cooking', 'äggnudlar'),
    ('sweet potato noodle', 'glasnudlar'),
    ('sweet potato noodles', 'glasnudlar'),
    ('körsbärs- ', 'körsbärs'),
    ('körsbärstomat- ', 'körsbärstomat'),
    ('chilipeppar röd', 'röd chilipeppar'),
    ('chilipeppar rod', 'rod chilipeppar'),
    ('chilipeppar grön', 'grön chilipeppar'),
    ('chilipeppar gron', 'gron chilipeppar'),
    ('chilipeppar gul', 'gul chilipeppar'),
    # Fresh small tomato variants — space-separated adjective forms
    ('små tomater', 'småtomater'),
    ('lilla tomater', 'småtomater'),
    ('liten tomat', 'småtomat'),
    ('litet tomat', 'småtomat'),
    ('snacktomater', 'småtomater'),
    ('snacktomat', 'småtomat'),
    ('körsbärskvisttomater', 'småtomater'),
    ('körsbärskvisttomat', 'småtomat'),
    ('korsbarskvisttomat', 'småtomat'),
    ('korsbärskvisttomater', 'småtomater'),
    ('cocktailtomater', 'småtomater'),
    ('cocktailtomat', 'småtomat'),
    ('cocktailtomter', 'småtomater'),
    ('tomater cocktail', 'småtomater'),
    ('tomat cocktail', 'småtomat'),
    ('babyplommontomater', 'småtomater'),
    ('babyplommontomat', 'småtomat'),
    ('piccolinitomater', 'småtomater'),
    ('piccolinitomat', 'småtomat'),
    ('romanticatomater', 'småtomater'),
    ('romanticatomat', 'småtomat'),
    ('tomater babyplommon', 'småtomater'),
    ('tomat babyplommon', 'småtomat'),
    # English "cherry tomatoes" maps to the Swedish small-tomato family so
    # English-labeled fresh products and Swedish recipes can match each other.
    ('cherrytomater', 'småtomater'),
    ('cherrytomat', 'småtomat'),
    ('cherry tomater', 'småtomater'),
    ('cherry tomat', 'småtomat'),
    ('cider äpple', 'äppelcider'),
    ('toastbröd', 'formbröd'),
    ('toastbrod', 'formbröd'),
    # Cider compound forms → split so 'cider' keyword is extractable
    ('flädercider', 'fläder cider'),
    ('fladercider', 'fläder cider'),
    ('päroncider', 'päron cider'),
    ('paroncider', 'päron cider'),
    ('herrgårdscider', 'herrgård cider'),
    ('herrgardscider', 'herrgård cider'),
    ('ciderkaraktär', 'cider'),  # "ciderkaraktär" = cider-style drink
    ('ciderkaraktar', 'cider'),
    ('gruyerost', 'gruyere ost'),
    ('vitt bröd', 'formbröd'),
    ('vitt brod', 'formbröd'),
    ('brödskivor', 'formbröd'),
    ('brodskivor', 'formbröd'),
    ('brödskiva', 'formbröd'),
    ('brodskiva', 'formbröd'),
    ('vita brödskivor', 'formbröd'),
    ('vita brodskivor', 'formbröd'),
    ('balsamico hallon', 'balsamicohallon'),
    ('balsamico mango', 'balsamicomango'),
    ('balsamico fikon', 'balsamicofikon'),
    ('balsamico tryffel', 'balsamicotryffel'),
    ('balsamico ingefära', 'balsamicoingefära'),
    ('balsamico ingefara', 'balsamicoingefara'),
    # Vit choklad is a distinct ingredient (cocoa butter + milk + sugar, no
    # cocoa solids) — must not match plain or dark chocolate. Compound-isolate
    # via space normalization so "vit choklad" recipes match only "Vit Choklad"
    # products. Mörk choklad stays generic (matches plain choklad as fallback).
    ('vit choklad', 'vitchoklad'),
    ('vita choklad', 'vitchoklad'),
    # Mango curry is a specific flavored spice blend (Santa Maria Mangocurry),
    # not plain curry. Compound-isolate so "Mango Curry" recipes match only
    # mangocurry-named products.
    ('mango curry', 'mangocurry'),
    # Polarbröd tunnbröd varieties (Njalla, Sarek, Abisko) — substitute to
    # 'tunnbröd' so all varieties cross-match within the tunnbröd family.
    # Liba tunnbröd brand has its own native 'tunnbröd' keyword extraction.
    ('njalla', 'tunnbröd'),
    ('sarek', 'tunnbröd'),
    ('abisko', 'tunnbröd'),
    ('earl grey', 'earlgrey'),
    ('pad thai sås', 'padthaisås'),
    ('pad thai-sås', 'padthaisås'),
    ('nöt- och fröbitar', 'nötbitar och fröbitar'),
    ('not- och frobitar', 'nötbitar och fröbitar'),
    ('ärter', 'ärtor'),
    ('dragon', 'estragon'),  # dragon and estragon are the same herb (tarragon)
    ('spagetti', 'spaghetti'),
    ('avocado', 'avokado'),
    ('texmex riven', 'texmexost riven'),
    ('chiafrö', 'chiafrön'),
    ('tomat finhackad', 'tomat krossad'),
    ('tomater finhackade', 'tomater krossade'),
    ('konserverade tomater', 'skalade tomater'),
    ('konserverad tomat', 'skalad tomat'),
    ('körsbärstomatertomater', 'körsbärstomater'),
    ('korsbarstomatertomater', 'korsbarstomater'),
    ('portabella', 'portabellosvamp'),
    ('portabellosvampar', 'portabellosvamp'),
    ('formfranska', 'formbröd'),
    ('rostad lök', 'rostadlök'),
    ('rostade lök', 'rostadlök'),
    ('vegetabilikt', 'vegetabiliskt'),
    ('pommes strips', 'pommesstrips'),
    # Gelé/jelly products: keep currant+jelly compounds intact so carrier handling
    # doesn't strip the berry family from current offer naming variants.
    ('gele vinbär', 'vinbärsgele'),
    ('gele svartvinbär', 'svartvinbärsgele'),
    ('gele rödvinbär', 'rödvinbärsgele'),
    # "Passerade tomater" = tomatpassata (same product, different name)
    ('passerade tomater', 'tomatpassata'),
    ('passerad tomat', 'tomatpassata'),
]
_SPACE_NORMALIZATIONS.extend(SPACE_NORMALIZATION_CLI_UPDATES)

# Pre-build combined regex for space normalizations (one pass instead of sequential replacements)
_SPACE_NORM_LOOKUP: Dict[str, str] = {k: v for k, v in _SPACE_NORMALIZATIONS}
_SPACE_NORM_PATTERN = re.compile(
    '|'.join(r'\b' + re.escape(k) + r'\b' for k, _ in sorted(_SPACE_NORMALIZATIONS, key=lambda x: len(x[0]), reverse=True))
) if _SPACE_NORMALIZATIONS else None
_SALAMI_CHIPS_HYPHEN_RE = re.compile(r'\bsalami\s*-\s*chips\b')
_SPRING_ONION_BUNCH_RE = re.compile(r'\bknipp[ea]\s+färsk\s+lök\b')
_SPRING_ONION_STALKS_RE = re.compile(r'\bfärsk(?:a)?\s+lök(?:ar)?\s*,?\s*stjälkarna\b')
_MEASURED_DURUM_FLOUR_RE = re.compile(r'\b\d+(?:[.,]\d+)?\s*(?:dl|l|g|kg)\s+durumvete\b')
_MEASURED_RISOTTO_RICE_RE = re.compile(r'\b\d+(?:[.,]\d+)?\s*(?:dl|l|g|kg)\s+risotto\b')

# Wine mapping keys that target matlagningsvin (cooking-wine substitution).
# When the ingredient line is a drink-context line (large cl-volumes, bottle
# wording, drink-quality descriptors), these mappings should be skipped so
# the wine keyword stays as 'rödvin'/'vitvin' rather than 'matlagningsvin'.
_WINE_TO_MATLAGNINGSVIN_KEYS = frozenset({
    'rödvin', 'rodvin', 'vitvin',
    'rött vin', 'vitt vin',
})
# Cooking-wine recipes use dl-volumes (1-2 dl typical). Drink recipes use
# cl-volumes (50/75 cl ≈ half/full bottle). This regex catches both.
_DRINK_WINE_CL_VOLUME_RE = re.compile(
    r'\b\d+(?:[.,]\d+)?\s*cl\s+(?:r[öo]dvin|r[öo]tt\s+vin|vitvin|vitt\s+vin)\b',
    re.IGNORECASE,
)
# "1 flaska rödvin" / "en flaska vitt vin" — bottle wording is drink-context.
_DRINK_WINE_BOTTLE_RE = re.compile(
    r'\b(?:\d+(?:[.,]\d+)?|en|ett|två|tre)\s*flask(?:a|or)\b.*\b(?:r[öo]dvin|r[öo]tt\s+vin|vitvin|vitt\s+vin)\b',
    re.IGNORECASE,
)


def _is_drink_wine_line(text: str) -> bool:
    """Return True when the ingredient line refers to wine in a drink context.

    Used to skip wine→matlagningsvin normalization for drink/glögg/punsch
    recipes where the wine is the drinking base, not a cooking substitute.
    Heuristic: cl-volumes and bottle wording. Cooking recipes use dl-volumes
    (1-2 dl typical). Quality descriptors like 'fyllig'/'kraftigt' overlap
    with cooking wording and are deliberately not used as triggers.
    """

    return bool(
        _DRINK_WINE_CL_VOLUME_RE.search(text)
        or _DRINK_WINE_BOTTLE_RE.search(text)
    )


def _apply_space_normalizations(text: str) -> str:
    """Apply all space normalizations in a single regex pass."""
    if _SPACE_NORM_PATTERN is not None:
        if _is_drink_wine_line(text):
            # Drink-context line: keep wine words as-is so they don't get mapped
            # to 'matlagningsvin'. All other normalizations still apply.
            def _replace_skip_wine(m: 're.Match[str]') -> str:
                key = m.group()
                if key.lower() in _WINE_TO_MATLAGNINGSVIN_KEYS:
                    return key
                return _SPACE_NORM_LOOKUP[key]
            text = _SPACE_NORM_PATTERN.sub(_replace_skip_wine, text)
        else:
            text = _SPACE_NORM_PATTERN.sub(lambda m: _SPACE_NORM_LOOKUP[m.group()], text)
    text = _SALAMI_CHIPS_HYPHEN_RE.sub('salamichips', text)
    # Spring-onion style recipe wording should normalize before punctuation/number
    # stripping, so use regexes that tolerate commas and leading quantities.
    text = _SPRING_ONION_BUNCH_RE.sub('salladslök', text)
    text = _SPRING_ONION_STALKS_RE.sub('salladslök', text)
    return text


def normalize_measured_durumvete_flour(text: str) -> str:
    """Treat measured plain durumvete lines as durum flour in recipe language.

    Keep this narrow to recipe-style measured ingredients and avoid broadening
    bulgur/durumvete families elsewhere.
    """
    if (
        _MEASURED_DURUM_FLOUR_RE.search(text)
        and 'bulgur' not in text
        and 'mjöl' not in text
        and 'mjol' not in text
    ):
        return _MEASURED_DURUM_FLOUR_RE.sub(
            lambda m: m.group(0).replace('durumvete', 'durumvetemjöl'),
            text,
        )
    return text


def normalize_measured_risotto_rice(text: str) -> str:
    """Treat measured plain risotto lines as risotto rice in recipe language.

    Keep this narrow to measured ingredient lines so prepared products named
    "Risotto ..." stay distinct on the product side.
    """
    if _MEASURED_RISOTTO_RICE_RE.search(text):
        return _MEASURED_RISOTTO_RICE_RE.sub(
            lambda m: m.group(0).replace('risotto', 'risottoris'),
            text,
        )
    return text
