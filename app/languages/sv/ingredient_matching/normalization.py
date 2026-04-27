import re
from typing import Dict, List, Tuple


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
    ('corn flakes', 'cornflakes'),
    # "Mjöl Tipo 00" → specific keyword, should only match itself
    ('mjöl tipo 00', 'tipo00'),
    ('tipo 00', 'tipo00'),
    # "Chicken Nuggets" → compound keyword so 'chicken' alone doesn't match
    ('chicken nuggets', 'chickennuggets'),
    ('kyckling nuggets', 'kycklingnuggets'),
    ('coppa di parma', 'coppadiparma'),
    ('non stop', 'nonstop'),
    # Blue cheese naming varies across recipes/offers. Normalize these surface
    # forms into the established ädelost family before validation.
    ('blåmögelost', 'ädelost'),
    ('grönmögelost', 'ädelost'),
    # "Lao Gan Ma" → join so keyword 'laoganma' is extracted and matches the brand
    ('lao gan ma', 'laoganma'),
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
    ('ättiksgurka', 'inlagdgurka'),
    ('attiksgurka', 'inlagdgurka'),
    ('smörgåsgurka', 'inlagdgurka'),
    ('smorgasgurka', 'inlagdgurka'),
    ('pressgurka', 'inlagdgurka'),
    ('saltgurka', 'inlagdgurka'),
    ('saltgurkor', 'inlagdgurka'),
    # Common recipe typos/split compounds that should map to the grocery product form.
    ('alfaalfagroddar', 'alfalfagroddar'),
    ('dinkel flingor', 'dinkelflingor'),
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
    ('burger bun', 'hamburgerbröd'),
    ('salsiccia fänkål', 'salsicciafänkål'),
    ('salsiccia fankal', 'salsicciafankal'),
    ('salsiccia vitlök', 'salsicciavitlök'),
    ('salsiccia vitlok', 'salsicciavitlok'),
    ('salsiccia chili', 'salsicciachili'),
    # Tabasco = pepparsås (brand name used generically in recipes)
    ('tabasco', 'pepparsås'),
    # Neutral cooking oil recipes should use the existing matolja/rapsolja family.
    ('neutral olja', 'matolja'),
    # "Flytande smör" in Swedish grocery recipes typically means the buyable
    # butter/rapeseed liquid cooking blend, not a block of solid butter.
    ('flytande smör', 'flytandesmör'),
    ('flytande smor', 'flytandesmör'),
    # "Veg bacon" (two words) → "vegobacon" so COMPOUND_STRICT blocks real bacon
    ('veg bacon', 'vegobacon'),
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
    ('växtbaserad dryck', 'växtdryck'),
    ('vaxtbaserad mjölk', 'växtdryck'),
    ('vaxtbaserad mjolk', 'växtdryck'),
    ('vaxtbaserad mjölkdryck', 'växtdryck'),
    ('vaxtbaserad mjolkdryck', 'växtdryck'),
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
    # Plant-based "butter" recipe wording is represented as margarine/spread
    # families in current store offers.
    ('växtbaserat smör', 'margarin'),
    ('vaxtbaserat smor', 'margarin'),
    ('veganskt smör', 'margarin'),
    ('veganskt smor', 'margarin'),
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
    ('orange juice', 'apelsinjuice'),
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
    ('worcestershiresås', 'worcestersås'),
    ('worcestershiresas', 'worcestersas'),
    # Whole spices
    ('kryddpepparkorn', 'kryddpeppar hel'),
    ('vitpepparkorn', 'vitpeppar hel'),
    ('paprikakrydda', 'paprikapulver'),
    ('tacokrydda', 'taco kryddmix'),  # "tacokrydda" = taco seasoning mix — STRICT kryddmix PPR requires "kryddmix" in ingredient
    ('tacochips', 'nachochips'),
    ('taco chips', 'nachochips'),
    ('five spice-kryddmix', 'fivespicekryddmix'),
    ('five spice kryddmix', 'fivespicekryddmix'),
    ('five spice-krydda', 'fivespicekryddmix'),
    ('five spice krydda', 'fivespicekryddmix'),
    ('vegetariska pieces/bitar', 'vegobitar'),
    ('vegetariska bitar', 'vegobitar'),
    ('vegetariska pieces', 'vegobitar'),
    ('grytbitar av quorn', 'quornbitar'),
    ('machesallad', 'machesallat'),
    ('black eye böna', 'blackeyeböna'),
    ('black eye bönor', 'blackeyebönor'),
    ('black eye bona', 'blackeyebona'),
    ('black eye bonor', 'blackeyebonor'),
    ('fänkål krydda', 'fänkålsfrö'),
    ('fankal krydda', 'fankalsfro'),
    ('pasta basilico krydda', 'pastakrydda basilico'),
    ('kanel hel', 'kanelhel'),
    ('fraîche', 'fraiche'),
    ('crème', 'creme'),
    ('chilli', 'chili'),  # double-l spelling variant common in recipes
    ('syltad ingefära', 'syltadingefära'),
    ('syltad ingefara', 'syltadingefara'),
    ('picklad ingefära', 'syltadingefära'),
    ('picklad ingefara', 'syltadingefara'),
    ('inlagd ingefära', 'syltadingefära gari'),
    ('inlagd ingefara', 'syltadingefara gari'),
    # Skånsk senap: both word orders → compound (product names use both orderings)
    ('skånsk senap', 'skånsksenap'),
    ('senap skånsk', 'skånsksenap'),
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
    ('olivolja citron', 'olivolja'),
    ('piri piri', 'piripiri'),
    ('piri-piri', 'piripiri'),
    ('morötter', 'morot'),
    ('morotter', 'morot'),
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
    ('bananschalottenlök', 'schalottenlök'),
    ('bananschalottenlökar', 'schalottenlök'),
    ('bananscharlottenlök', 'schalottenlök'),
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
    # Fresh small tomato variants
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
    ('balsamico hallon', 'balsamicohallon'),
    ('earl grey', 'earlgrey'),
    ('pad thai sås', 'padthaisås'),
    ('pad thai-sås', 'padthaisås'),
    ('nöt- och fröbitar', 'nötbitar och fröbitar'),
    ('not- och frobitar', 'nötbitar och fröbitar'),
    ('ärter', 'ärtor'),
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


def _apply_space_normalizations(text: str) -> str:
    """Apply all space normalizations in a single regex pass."""
    if _SPACE_NORM_PATTERN is not None:
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
