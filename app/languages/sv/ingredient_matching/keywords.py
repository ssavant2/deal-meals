"""Keyword and classification data for Swedish ingredient matching."""

from typing import Dict, FrozenSet, List


STOP_WORDS: FrozenSet[str] = frozenset({
    # Basic Swedish prepositions/conjunctions
    'och', 'med', 'i', 'till', 'för', 'på', 'av', 'från', 'som', 'den', 'det',
    'att', 'är', 'en', 'ett',

    # Cooking states/methods (too generic)
    'färsk', 'färska', 'frysta', 'fryst', 'stek', 'stekt', 'stekta', 'kokt', 'kokta', 'förkokt', 'förkokta',
    'halstrad', 'halstrade', 'halstrat',  # cooking method (seared) — same category as stekt/grillad
    'grillad', 'grillade', 'grillat',  # "Kyckling Grillad" → 'kyckling' is enough
    'ungsbakad', 'ungsbakade', 'ungsbakat', 'ugnsbakad', 'ugnsbakade', 'ugnsbakat',  # oven-baked method
    'benfri', 'benfritt', 'benfria',  # "benfri älgstek" != "benfri kalvstek"
    'hackad', 'hackade', 'finhackad', 'finhackade',  # preparation methods - "finhackad vitlök" != "finhackade selleristjälkar"
    'mixad', 'mixade', 'mixat', 'grovmixade', 'finmixade',  # blending method — "fint mixade mandlar" not a food keyword
    'panerad', 'panerade', 'panerat',  # cooking method — "Bläckfiskring Panerade" should match via 'bläckfiskring', not 'panerade'
    'skuren', 'skurna', 'strimlad', 'strimlade',
    'riven', 'rivna', 'grovriven', 'finriven', 'finrivna', 'tärnad', 'tärnade', 'tärnat', 'smält', 'smälta',
    'grovmalen', 'grovmalet', 'grovmalda',  # grinding descriptor - "Svartpeppar Grovmalen" should match on svartpeppar, not grovmalen
    'finmalet', 'finmalen', 'finmald', 'finmalda', 'finmalt',  # same for fine-ground — "Majsmjöl Finmalet" crosses flour types
    'vitaminberikad', 'vitaminberikade', 'vitaminberikat',  # fortification label — "Rapsolja D-vitaminberikad" crosses product types
    'passerad', 'passerade',  # processing form, not ingredient
    'koncentrerad', 'koncentrerade',  # processing form, not ingredient
    'skalad', 'skalade', 'oskalade', 'oskalad',  # (un)peeled - prep descriptor, not ingredient
    'skivad', 'skivade', 'skivor', 'tunnskivad', 'tunnskivade',  # too generic (packaging/form, not ingredient)
    'flytande',  # too generic (liquids, detergents, oils)
    'naturell', 'naturellt', 'naturella',  # too generic (everything is "naturell")
    'neutral',  # descriptor ("neutral olja") - not an ingredient
    'klippt', 'klippta', 'klippa',  # too generic (cut/chopped form)
    'fylld', 'fyllda', 'fyllning',  # "Fyllda pepparfrukter" - preparation method
    'rostad', 'rostade', 'rostat',  # too generic as standalone - "jordnötter rostade" shouldn't match "rostad müsli"
    # Note: "rostad lök" handled via space norm → 'rostadlök' (specific compound keyword)
    'saltad', 'saltade', 'saltat', 'osaltad', 'osaltade', 'osaltat',  # salt descriptors
    'sköljd', 'sköljda', 'skoljd', 'skoljda',  # rinsed/washed - "Babyspenat Sköljd" is preparation, not ingredient

    # Preparation methods (require exact match - "passionsfrukt" should NOT match "torkad passionsfrukt")
    'torkad', 'torkat', 'torkade',  # "passionsfrukt" != "torkad passionsfrukt"
    'soltorkad', 'soltorkade', 'soltorkat', 'soltork',  # preparation method, not ingredient
    'picklad', 'picklade', 'picklat',  # preparation method, not ingredient
    'rökt', 'rokt', 'kallrökt', 'varmrökt', 'varmrokt', 'kallrokt',  # "laxfilé" != "varmrökt lax"
    'gravad', 'gravade',  # "lax" != "gravad lax"
    'rimmad', 'rimmade', 'rimmat',  # "Fläsklägg Rimmad" is NOT "rimmad lax" (curing method)
    'marinerad', 'marinerade', 'marinerats', 'marinerat',  # too specific preparation
    'örtmarinerad', 'örtmarinerade', 'ortmarinerad', 'ortmarinerade',  # herb-marinated — preparation method, not ingredient
    'rårörd', 'rårörda', 'rarörd', 'rarörda',  # "Svarta Vinbär Rårörd" — preparation method, not ingredient
    'krossad', 'krossade', 'krossat',  # "tomater" != "krossade tomater"
    'inlagd', 'inlagda', 'inlagt',  # "inlagd ingefära" → ingefära is the ingredient, not "inlagd"
    'syltad', 'syltade', 'syltat',  # "syltade apelsinskal" → apelsinskal is the ingredient, not "syltad"
    'färdigkokta', 'färdigkokt',  # "färdigkokta kikärtor" — prep state, not ingredient
    'färdiga', 'färdig', 'färdigt',  # "Färdiga pizzabottnar" — readiness descriptor, not ingredient
    'fileade', 'filead', 'filerade',  # "fileade apelsiner" — cooking method (segmented/filleted), not ingredient
    'råpressad', 'råpressade', 'rapressad',  # "Limejuice - råpressad" — processing method
    'färskpressad', 'färskpressade',  # "färskpressad citronjuice" — processing method
    'fritering',  # "neutral olja, till fritering" — cooking method
    'smaksatt', 'smaksatta',  # "yoghurt" != "smaksatt yoghurt"
    'portionsbit', 'portionsbitar',  # packaging, not ingredient
    'portion', 'portioner',  # serving size ("O'boy Portion 10x28g" ≠ "4 portioner bulgur")

    # Basic seasoning (too common - would match everything)
    'salt', 'peppar', 'vatten', 'olja',
    # NOTE: svartpeppar, vitpeppar, citronpeppar, vitlökspeppar removed —
    # these are actual products that should match when recipes ask for them specifically

    # Generic descriptive words (cause false matches)
    'pressad', 'pressade',  # "Pressad Citron" - preparation method, not ingredient
    'grovt', 'grova', 'fint', 'fina', 'stor', 'stora', 'liten', 'lilla', 'vanliga', 'vanlig', 'spetsig',
    'fyrkantigt',  # shape descriptor ("fyrkantigt tunnbröd") — caused rispapper shape matches
    'medelstor', 'medelstora',  # size descriptor ("jordärtskockor (medelstora)")
    'nymalen', 'nymalda',  # prep descriptor ("nymalen svartpeppar" — just freshly ground)
    'grovkornig', 'grovkornigt',  # texture descriptor ("grovkornig dijonsenap")
    'grovhackad', 'grovhackade', 'grovhackat',  # prep method ("hasselnötter grovhackade")
    'grovkrossad', 'grovkrossade',  # prep method ("grovkrossad vitpeppar")
    'halvor', 'halvorna',  # cut/shape descriptor ("potatis i halvor") — not the fruit "Persikor i Halvor"
    'vilt',  # generic descriptor ("gärna av vilt") — too broad, matches "Vilt Kantarell Fond" (wild mushroom stock)
    'smoked',  # English cooking descriptor ("smoked paprikapulver") — matches "Black Smoked Bacon" via substring
    'fingers',  # English word — "Chicken fingers" ≠ "savoiardikex (ladyfingers)"
    'kolsyrat',  # water state ("kolsyrat vatten") — matches flavored "Citron Kolsyrat Vatten" drinks
    'kokande',  # water state ("vatten, kokande")
    'finkrossad', 'finkrossade',  # prep method ("Finkrossade Tomater Basilika")
    'delikatess',  # quality descriptor ("Salami Delikatess", "Gurka Delikatess") — not a food type
    'konserv',  # packaging type ("Kantareller Konserv")
    'sockerlag',  # packaging medium ("Fruktcocktail i Sockerlag", "Persikor i Halvor i Sockerlag") — not simple syrup ingredient
    'matlagning',  # description ("Yoghurt för Matlagning")
    'blötlagd', 'blötlagda',  # prep method ("anchochili, blötlagd")
    'urkärnad', 'urkärnade', 'urkärnat',  # prep method ("oliver, urkärnade")
    'kärnfri', 'kärnfria', 'kärnfritt',  # property descriptor — "päron, skalade och kärnfria" matched "Russin Kärnfria", "Melon Kärnfri"
    'konserverad', 'konserverade',  # preservation method ("Jalapeno Konserverad")
    'motsvarar',  # measurement word ("1 klyfta motsvarar ca 250 g")
    'används',  # verb ("25 g används vid fräsning")
    'fräsning',  # cooking method
    'fyllig', 'fylliga',  # descriptor ("extra fylliga havregryn")
    'kraftig', 'kraftiga', 'kraftigare',  # descriptor ("kraftigare vin") — not a food
    'spröd', 'spröda', 'sprött', 'sprod', 'sproda', 'sprott',  # texture adjective, not a product type
    'garnering',  # "till garnering" — presentation, not ingredient
    'garnityr', 'förslag',  # section headers / metadata, not ingredients
    'finrivet', 'finriven',  # prep method ("finrivet skal")
    'ekfatslagrade',  # descriptor ("ekfatslagrade viner")
    'teskedar',  # measurement unit
    'bruttovikt',  # weight descriptor, not ingredient
    'förpackningen', 'förpackning',  # "vatten enligt förpackningen" / "1 förpackning skumtomtar" — packaging descriptor
    'packning',  # gasket/seal — "Plastknopp m packning till perkulator" is not food
    'färger',  # "gärna olika sorter och färger" — color descriptor, not food keyword
    'grytbitar',  # styckning, inte köttsort — alla recept anger köttsort separat (nöt/fläsk/lamm/fisk)
    'justera',  # "justera efter smak" — instruction verb
    'mortlad', 'mortlade',  # "timutpeppar, mortlad" — ground in mortar (prep method)
    'plockade', 'plockad',  # "plockade blad" — prep method (picking leaves)
    'avsköljda', 'avsköljd',  # rinsed - prep descriptor
    'stekning',  # "till stekning" — cooking method, not ingredient
    'servering',  # "till servering" — serving context, not ingredient
    'smörjning',  # "till smörjning av formen" — cooking method, not ingredient
    'rökspån', 'rokspan',  # wood chips for smoking — not food
    'kallrökning', 'kallrokning',  # cold smoking method — not ingredient
    'burgaren',  # bestämd form in context phrase ("till stekning av burgaren") — not an ingredient
    'dressingen',  # bestämd form ("att späda dressingen med") — dish name, not ingredient
    'stekpannan',  # kitchen equipment ("smör till stekpannan") — not an ingredient
    'valfritt',  # "honung (valfritt)" — optional marker, not ingredient
    'valfria', 'alternativt',  # option markers, not ingredient words
    'stjälkar', 'stjälk',  # plant part ("2 stjälkar selleri") — selleri is the ingredient
    'piccante',  # Italian descriptor ("spicy") — "Gorgonzola Piccante D.O.P" ≠ "Salami Spianata Piccante"
    'mellan', 'extra', 'original', 'orginal', 'klassisk', 'klassiska', 'klassiker', 'classico',
    'virgin',  # "Extra Virgin Olivolja" - quality grade, not ingredient
    'gourmet',  # marketing descriptor — "Président Gourmet le Bleu" brand name, not ingredient
    'caesar',  # "Kyckling Caesar Stekt" — dish name, not ingredient. Compound 'caesardressing' unaffected.
    'premium', 'deluxe', 'special', 'traditional', 'traditionell', 'traditionella', 'traditionellt', 'falbygdens',
    'hokkaido',  # pumpkin variety — "Sushi Meny Hokkaido" is sushi, not pumpkin
    'delice',  # pumpkin variety — "Färskost Bleu delice" is cheese, not pumpkin
    'texture', 'texturerat',  # descriptor — "Hår Paste Texture" is hair product, not "texturerat vegoprotein"
    'giganti',  # Italian size word for olives ("Cerignola Giganti") — matches "gigantiskt" in recipes
    'ekologisk', 'ekologiskt', 'ekologiska', 'eko',
    'miljömärkt', 'miljömärkta',  # certification label ("KRAV- eller miljömärkt") — not a food keyword
    'exotisk', 'exotiska',  # "Nötmüsli Exotisk" ≠ "exotisk frukt" in recipes
    'svensk', 'svenska', 'sverige', 'ursprung',  # too generic
    'fransk', 'franska', 'italiensk', 'italienska', 'italien',  # too generic
    'spansk', 'spanska',  # origin ("Olivolja Spansk") ≠ "spansk salami" in recipes
    'turkisk', 'turkiska',  # origin ("Matlagningsyoghurt Turkisk")
    'vegetarisk', 'vegetariska', 'vegansk', 'veganska',  # diet qualifier, not food ("Krögarpytt Vegetarisk" ≠ "vegetarisk färs")
    'alkoholfri', 'alkoholfritt', 'alkoholfria',  # qualifier, not food ("Alkoholfri Öl" shouldn't match recipes mentioning "alkoholfritt" in parenthetical)
    'alkohol',  # metadata in product names ("Matlagningsvin Rött Alkohol 2,2%") — not a useful keyword
    'asiatisk', 'asiatiska', 'asiatiskt',  # cuisine style, not ingredient
    'mexikansk', 'mexikanska', 'texmex', 'tex mex',  # cuisine styles
    'thai', 'kinesisk', 'kinesiska',  # cuisine styles
    'grekisk', 'grekiska', 'grekiskt',  # "Grekisk färsbiff Dafgårds" ≠ "grekisk yoghurt"
    'indisk', 'indiska', 'japansk', 'japanska', 'koreansk', 'koreanska',
    'filippinsk', 'filippinska',  # Filipino cuisine style — not food keyword
    'libanesisk', 'libanesiskt', 'libanesiska',  # Lebanese — geographic descriptor, not food
    'provencale', 'provençale',  # French cuisine style ("provencale oliver") — not a food keyword
    'toscana', 'toscanska',  # Italian region — "Zeta Olivolja ex Toscana" ≠ Örtsalt/Antipasto Toscana
    'korean',  # English cuisine style ("Korean BBQ bulgogi" ≠ gochujang)
    'gotland', 'skåne', 'norrland',  # Swedish regional names on meat/dairy products
    'medelhavs',  # "Levain Medelhavs" — geographic style descriptor, not food keyword
    'polen', 'litauen', 'greenland', 'bonduelle',  # countries/brands from product labels
    # English non-food words that cause substring collisions with Swedish food words
    # "nature" from "Passion of nature" matches "naturell" in ingredient text
    # "passion" from flavor products matches "passionfrukt" in ingredient text
    'nature', 'passion', 'aliens',
    # Compound words where suffix-matching causes FP:
    'vaniljsmak',  # flavor descriptor ("sojaglass, vaniljsmak") — matches kvarg/proteinshake with vanilla flavor
    'svampsmak',  # flavor descriptor ("snabbnudlar med svampsmak") — matches "Sojasås med Svampsmak", not an ingredient
    'chokladdryck',  # "Färdig chokladdryck" → compound "choklad" matches bakchoklad. Ready-made drink, not cooking ingredient.
    'ostfondue', 'fondue',  # "Ostfondue" → compound "fond" matches buljong/fond. Specific packaged product.
    'triple',  # "Triple sec" (liqueur) → matches "Triple cheese". Not a food word.
    'säsong', 'säsongens',  # "frukt i säsong" / "säsongens frukt" — season descriptor, not food keyword
    'vinter',  # seasonal marketing ("Nötmix Vinter LTD") — reverse-substring matches "vinterpotatis"
    'silver',  # material/color ("Soft Silver Pearls") — reverse-substring matches "silverlök"
    'quattro',  # Italian "four" — "Glasburk Quattro stagioni"/"Pizza quattro formaggi" reverse-substring matches "quattrocento" (cheese)
    'dubbel',  # "dubbelkolla innehållet!" → compound "dubbel" matches candy bars (Japp Dubbel, Sportlunch Dubbel). Not a food keyword.
    'brunt',  # "Brunt Farinsocker" — color descriptor. Matches "Krydda Brunt Senapsfrö"
    'garant', 'eldorado', 'sevan', 'findus', 'minella', 'ducali', 'risberg', 'delicato',  # store/product brand names (not food keywords)
    'vegeta',  # Podravka seasoning brand — substring matches "vegetabilisk/vegetarisk" in ingredient text
    'saluhall', 'thom',  # "Saluhall Paul Och Thom" - not food keywords
    'zeinas',  # "Basmati Quick N' Easy/2 Port Zeinas" brand
    'pataks', "patak's",  # brand name ("Patak's rogan josh-pasta")
    'josh-pasta',  # brand product name fragment ("rogan josh-pasta")
    'onion-dippmix',  # brand flavor name ("sourcream & onion-dippmix")
    'gammaldags', 'gammeldags',  # style descriptor ("gammaldags/gammeldags mjölk", "Rödbetor Gammaldags") — not an ingredient
    'morfars', 'farmors', 'mormors',  # marketing prefixes on cheese/meat products
    'familjefavoriter',  # marketing word ("Gräddis Familjefavoriter 30%")
    'gräddis',  # brand name (Arla Gräddis), not a food keyword
    'presso',  # brand/style name ("Kaffe Presso Mellanrost") - matches "espresso" falsely
    'twin',  # brand name "TWIN DRAGON" (sesame oil) — "dragon" removed: it's a real herb (tarragon)
    'ringar',  # too generic shape word - "Ringar Sourcream" (snack) matches "bläckfiskringar"
    'pinnar',  # non-food ("Fiskfria Pinnar", "Finska Pinnar") matches "Grillpinnar" in recipes
    'smörgås', 'smörgas',  # non-food keyword — "Smörgås Margarin" matches "smörgåskrasse" in recipes
    'sourcream',  # brand/flavor word ("sourcream & onion" dippmix)
    'och/eller',  # conjunction ("smör och/eller olja")
    'stekning/rostning',  # compound cooking method
    'beroende',  # descriptor ("beroende på storlek")
    'storlek',  # size descriptor ("beroende på storlek")
    'ordentligt',  # adverb ("häll av ordentligt")
    'färskmalen', 'färskmalda',  # prep descriptor ("färskmalen svartpeppar")
    'stycken',  # quantity word ("2 stycken paprikor")
    'personer',  # serving-count metadata ("för 2 personer")
    'avrunna', 'avrunda', 'avrunnav',  # prep method / typo variant ("avrunna kikärtor")
    'tvättad', 'tvättade',  # prep method ("tvättade blad")
    'mjöliga', 'mjölig',  # descriptor ("mjöliga potatisar")
    'tillsätts',  # instruction verb ("tillsätts i slutet")
    'nyriven', 'nyrivet', 'nyrivna',  # prep descriptor ("nyriven parmesan")
    'skinnfri', 'skinnfria',  # property ("skinnfri kycklingfilé")
    'sötsyrlig', 'sötsyrliga',  # taste descriptor
    'filtrerat', 'filtrerad',  # processing method
    'kokvätska',  # cooking liquid (instruction, not ingredient)
    'munstora',  # size descriptor ("munstora bitar")
    'dagsgammalt', 'dagsgammal', 'dagsgamla',  # age descriptor ("dagsgammalt bröd")
    'finfördelat', 'finfördelad', 'finfördelade',  # prep method
    'finhackde',  # typo variant of finhackade (already stop word)
    'sigillo',  # Italian brand word ("Sigillo Rosso")
    'flaskor',  # packaging ("2 flaskor öl")
    'utspädd', 'utspädda',  # prep method ("utspädd buljong")
    'guerrieri',  # Italian brand name ("Guerrieri")
    'knaperstekt', 'knaperstekta',  # cooking method ("knaperstekt bacon")
    'friterad', 'friterade', 'friterat',  # cooking method
    'ätmogen', 'ätmogna',  # ripeness descriptor ("ätmogen mango") — not a food keyword
    'såser',  # category word ("maizenaredning för mörka såser") — too generic, matches "Eriks såser" brand
    'dekoration',  # usage ("till dekoration")
    'panering',  # cooking method ("till panering")
    'urkramad', 'urkramade',  # prep method ("urkramad spenat")
    'normalstor', 'normalstora',  # size descriptor
    'skållade', 'skållad',  # prep method ("skållade mandlar")
    'sötaktig',  # taste descriptor
    'iskallt',  # temperature instruction ("serveras iskallt")
    'småbitar', 'gaffelbitar',  # cut-size descriptors, not ingredients
    'blötlägger',  # instruction verb ("alternativt blötlägger du...")
    'samarbete', 'jävligt',  # site/metadata leakage from scraped text
    'breoliv',  # specific brand/product name (not an ingredient)
    'pocheringen',  # cooking method reference
    'finhackat',  # neuter form of finhackad ("finhackat äpple")
    'klyftad', 'klyftade',  # cut into wedges ("klyftade äpplen")
    'råriven',  # raw-grated ("råriven lök")
    'oskivad', 'oskivade',  # unsliced ("oskivad kavring")
    'hårdkokt', 'hårdkokta', 'hårdkokat',  # hard-boiled ("hårdkokta ägg")
    'finstrimlad', 'finstrimlat', 'finstrimlade',  # finely shredded
    'handskalad', 'handskalade',  # hand-peeled ("handskalade räkor")
    'uppvispad', 'uppvispade',  # whisked up
    'lufttorkad', 'lufttorkade', 'lufttorkat',  # air-dried — consistent with torkad/rökt/varmrökt
    'nymortlad', 'nymortlade',  # freshly ground in mortar — consistent with mortlad/mortlade
    'vitorna',  # egg whites part reference
    'vätskan',  # "the liquid" — not buyable
    'ingredienslista',  # recipe instruction ("se ingredienslista nedan")
    'gratinering',  # cooking method ("till gratinering")
    'rektangulär', 'rektangulära',  # shape descriptor ("rektangulära tunnbröd")
    'utformning',  # shaping method ("vetemjöl, till utformning")
    'stekrester',  # pan drippings — not buyable
    'version',  # recipe text ("för vegetarisk version")
    'produkter',  # too generic ("Vegetariska produkter")
    'osötad', 'osotad', 'osötade', 'osotade',  # unsweetened descriptor — singular/plural inflections
    'rullpack',  # packaging format — "Kalvfärs 16% Rullpack" matched risgrynsgröt recipe via shared keyword
    'salted',  # English modifier — "Salted Caramel Glass/Syrup" is never a recipe ingredient
    'kokbar',  # product descriptor — "Crème Fraiche Kokbar" means cookable, not a food type
    'växtbaserad', 'vaxtbaserad', 'växtbaserat', 'växtbaserade',  # plant-based descriptor — all inflections
    'växtbas', 'vaxtbas',  # shortened form — "Växtbas Margarin" is not a food type
    'msc-märkt',  # certification label ("MSC-märkt")
    'rostade/saltade',  # compound prep descriptor
    'sorter',  # variety word ("gärna olika sorter") — "Peppar Fyra Sorter Påse" FP

    # English marketing words (common in Swedish products)
    'creamy', 'cream', 'smooth', 'light', 'mild', 'strong',
    'fresh', 'frozen', 'original', 'classic',
    'apple', 'berry', 'fruit', 'juice',  # too generic English words
    'ginger',  # English for ingefära — "Ginger Turmeric Tea" etc. Swedish uses 'ingefära'
    'golden',  # "Örtte Golden honey" - too generic English adjective
    'yellow',  # "Yellow Mustard" - color word, not ingredient
    'marble', 'marbles',  # brand word ("Juicy Marbles" plant-based brand) — matched a keychain toy
    'mustig', 'mustigt', 'mustiga',  # cooking adjective (full-bodied) — "Mustigt rödvin" matched baby food välling
    'hickory',  # BBQ flavor descriptor — "Grillsås Hickory" is a sauce flavor, not a food keyword
    'smokey',  # English flavor descriptor — "Violife Smokey Flavour" matched "Pulled Chicken Smokey BBQ"
    'breakfast',  # English meal word — "Kex Breakfast Golden Oats" matched "Te English Breakfast" recipe

    # Quantities/forms (meaningless for matching)
    'paket', 'pack', 'burk', 'påse', 'flaska', 'liter', 'gram', 'kilo',
    'knippe', 'knippa',  # "salladslök knippe" - knippe is a quantity
    'flakes', 'flingor',  # too generic form - "Kokos Flakes" ≠ "Chili Flakes" ≠ "Corn Flakes"

    # Forms/cuts (not ingredients)
    'skivat', 'strimlat', 'rivet', 'hackat',  # adjective forms
    'filé', 'filéer',  # cut form - "Filéer" should not match "matjessillfiléer"
    'tärningar', 'tärning', 'tärningsstora',  # cutting method/size - not ingredient
    'klyfta', 'klyftor', 'klyft',  # form word from vitlöksklyfta split (via _SPACE_NORMALIZATIONS)
    'plattor',  # form word from pastaplattor split — "Smördeg Plattor" FP
    'krydda', 'kryddor',  # form word from paprikakrydda split — "Texas Grill Krydda" etc.
    'matlagnings',  # form word from matlagningsgrädde split — "Matlagnings Grädde" FP
    'kapslar', 'kapsel',  # container/form word — "kardemummakapslar" splits to "kapslar" which matches coffee capsules

    # Descriptive words (not ingredients)
    'kärnor', 'karnor',  # "Oliver Utan Kärnor" — with/without pits, not an ingredient

    # Too generic body parts (candy "Röda hjärtan" matches "kronärtskockshjärtan")
    'hjärtan', 'hjartan',  # recipes use compound: kronärtskockshjärtan, kycklinghjärtan
    'hjärta', 'hjarta',  # decoration ("Hjärta Röd" LED light, "Ballong Hjärta")
    'sticks',  # packaging term ("Kattsnacks Sticks Lax")

    # Swedish adjectives (too generic)
    'god', 'goda', 'läcker', 'läckra', 'perfekt', 'perfekta',
    'syrlig', 'syrliga', 'syrligt',  # "Bilar Syrlig Frukt" candy ≠ "syrliga äpplen" in recipes

    # Too generic product descriptors
    'normal',  # "LED Normal E27" — size descriptor, matches "normalsaltat smör" falsely
    'fullkorn', 'fullkorns',  # "Fullkorns Skorpor" — wholegrain descriptor, matches "fullkornsris" falsely
    'sommar',  # "Yoghurt Vår & Sommar" — season descriptor, matches "sommargrönsaker" falsely
    'variant', 'varianten',  # "Smörgåskex Variant" — generic, matches "varianten med fullkorn" in recipe text
    'osötat', 'osotat', 'osötad', 'osotad', 'osötade', 'osotade',  # generic descriptor
    # NOTE: 'nektar' NOT here — it's a valid keyword for juice drinks, but nektarin/nektariner
    # blocked via FALSE_POSITIVE_BLOCKERS to prevent matching nectarine fruit

    # Too generic compound words
    'blandning',  # "kryddblandning" != "Mollbergs Blandning Kaffekapslar"
    # Note: 'kryddmix' removed from STOP_WORDS - it IS a valid keyword for recipe matching
    # Specificity enforced by CONTEXT_REQUIRED_WORDS + PROCESSED_PRODUCT_RULES
    'buketter',  # too generic - "Broccoli Buketter" already matches on 'broccoli'
    'kvistar',  # quantity descriptor ("5-6 kvistar timjan")
    'björkris',  # birch branches (for smoking/decoration) — "björkris" compound extracts 'ris' which matches cooking rice
    'fyrkant', 'fyrkanter',  # shape descriptor ("små fyrkanter av vårrulledeg") — "Carlssons Fyrkant Limpa" is a bread brand, not a shape ingredient
    'formbar', 'formbara',  # product form descriptor ("400g formbar vegofärs")
    'djupfrys', 'djupfryst', 'djupfrysta',  # cooking/storage method — "tärnad djupfryst fisk" matched "Räkor Djupfrys"
    'napoletana',  # style name — "pastasås Napoletana" matched "Base Pizza Alla Napoletana" (pizza base, not sauce)
    'napoli',  # origin name — "Salami Napoli" is a brand/origin, not ingredient keyword
    'genovese',  # origin/style — "Pesto Genovese" already matches via 'pesto' keyword; genovese as standalone keyword caused 73 redundant matches
    'laktos',  # diet property — "Smör Laktosfritt" extracted 'laktos' which matched non-dairy products
    'storbit',  # size descriptor — "Zeta Storbit Grana Padano" matched "Kassler Storbit" (pork, not cheese)
    'laxbiff', 'laxbiffar',  # not a buyable product — recipes make these from laxfilé, 'lax' keyword covers matching
    'rosta',  # cooking method — "rostade nötter", "rostad potatis" matched bread brand "Rosta"
    'frukost',  # meal type — "frukostkorv" splits to frukost+korv; 'frukost' matched breakfast products (Marmelad, Crackers, Veteknäcke)
    'förbereds', 'forbereds',  # cooking instruction ("förbereds dagen innan")
    'mittbit',  # cut descriptor ("oxfilé, mittbit")
    # NOTE: 'redning' NOT here — it's an actual product (ljus/brun redning)
    'hemgjord', 'hemgjorda', 'hemlagad', 'hemlagade', 'hemlagat',  # preparation method ("hemgjord hjortfond", "hemlagad surgurka")
    'topping',  # usage descriptor ("nötter för topping")
    'finmaskig',  # tool descriptor ("finmaskig sil")
    'marine',  # "marinerad" != "Marine Toalett Rengöring"
    'double',  # brand word - "Pinnglass Double caramel" != "Double sesam burger bun"
    'dubbla',  # quantity word ("dubbla mängden") — "Gille Dubbla Flarn" is NOT an ingredient
    'sugars',  # English "No Sugars" label — 'sugars' substring matches 'sugarsnaps' (FP)
    'flavour', 'flavor',  # English taste descriptor ("Noodles Chicken Flavour") — never a Swedish keyword
    'cooking',  # English method word ("Noodles Quick Cooking") — not a product keyword
    'dipping',  # English serving word ("Ssamjang Pasta Korean Dipping Sauce")
    'roasted',  # English method word ("Roasted Garlic Mayonnaise")
    'sauterad',  # cooking method ("sauterad lök") — not a product keyword
    'yakisoba',  # noodle dish type ("Nudlar Yakisoba Beef") — not a standalone ingredient
    'hokkien',  # noodle type ("Nudlar Ramen Fresh Hokkien") — not a standalone ingredient
    'demae',  # instant noodle brand ("Demae Ramen") — not an ingredient
    'sanuki',  # Japanese udon region name ("Sanuki Udon") — not an ingredient

    # Processing/preparation methods that cause false matches
    'kallpressad',  # "rapsolja (ej kallpressad)" should NOT match "Kallpressad Juice"
    'bakning',  # "till utbakning" is preparation method, not ingredient
    # NOTE: 'mousserande' removed — it's a real product keyword (Willys has 5 mousserande vin products)
    'mousse',  # dessert product, not a standalone ingredient
    'cocktail',  # size descriptor ("Chorizo Cocktail") — compound "cocktailtomat" still works
    'lungo', 'estremo',  # coffee terms ("Lungo Estremo Kapslar") — not food
    'ugnsrostad', 'ugnsrostade', 'ugnsrostat',  # "Ugnsrostad kyckling Dafgårds" ≠ "ugnsrostad potatis"

    # Candy/non-food words that extract false food keywords
    'gummi',  # "Gummi Burger" (candy) → extracts 'hamburgare' via synonym — not real burger
    'stjärn', 'stjarna',  # "Sur Stjärn Mix" (candy) → matches "stjärnanis" — not a spice

    # Packaging/form descriptors (not ingredients)
    'koncentrat',  # "Lättdryck Koncentrat" ≠ "Äppeljuice Koncentrat"

    # Too generic descriptive words (cause false matches with ready meals/products)
    'krämig', 'kramig',  # "krämig kokosmjölk" != "Cheddar Krämig Mild"
    'chunky',  # "tacosås chunky salsa" != "Redskapsförvaring Chunky"
    'butter',  # "butternut" squash != "Butter Chicken" ready meal
    'masala',  # "garam masala" spice != "Tikka Masala" ready meal
    'frukter', 'frukt',  # "pepparfrukter" != "Smoothie Tropiska Frukter"
    'fruktkött',  # descriptor "flesh/pulp of fruit" — "1 klyfta pomelo (fruktkött)" matches juice products
    'smoothie',  # drink type — "Smoothie Mango Passion" ≠ recipe "Frukt till Smoothie" (the fruit is the ingredient, not the smoothie)

    # Product properties / nutritional labels (not ingredients)
    'fetthalt',  # "Fetthalt 13%" — nutritional info, not ingredient
    'sockerfri', 'sockerfritt',  # "gärna sockerfri" != "Monster Energy Sockerfri"
    'växtbaserad', 'vaxtbaserad',  # "växtbaserad dryck" != "Margarin Växtbaserad"
    'laktosfri', 'mjölkfri',  # properties, not ingredients
    'glutenfri', 'glutenfritt',  # diet label, not product type (moved from PROCESSED_FOODS)
    'vegansk', 'veganska', 'veganskt', 'vegan',  # diet type, not ingredient - "vegansk choklad" != "Margarin Vegansk"

    # Flavor words that are too generic as standalone keywords
    'vanilj',  # "vanilj" matches too broadly — specificity via CONTEXT_REQUIRED_WORDS instead
    'mindre',  # "Mindre söt" — comparative adjective, not ingredient

    # Pizza variety names (not cooking ingredients)
    'margherita', 'capricciosa', 'vesuvio', 'calzone', 'ristorante',
    'grandiosa',  # frozen pizza brand

    # English flavor/marketing words
    'vanilla', 'caramel', 'chocolate',  # common flavors in snacks/drinks
    'cheese',  # "cream cheese" != "Cheese Ballz"
    'orange',  # English color/fruit word - "Pressed Orange Tropicana" matches "orangea" (peel color) falsely
    'gluten',  # diet property - "Gluten Free Friggs" should NOT match "glutenfri" in recipes
    'pulver',  # form descriptor - "Bearnaisesås Pulver" should NOT match "pulverkaffe" in recipes
    'crispy', 'crunchy', 'crunch',  # texture words - not ingredients

    # Colors (too generic - "svarta bönor" != "svarta sesamfrön")
    'svart', 'svarta', 'vit', 'vita', 'röd', 'röda', 'grön', 'gröna',

    # Verbs that appear in recipe text but aren't ingredients
    'hittar',  # "receptet hittar du här" - verb, not ingredient

    # Brewing/preparation state adjectives (not ingredients)
    'nybryggt', 'nybryggd',  # "nybryggt kaffe" = freshly brewed (instruction), not a product

    # Cooking method descriptors (not ingredients)
    'karamelliserad', 'karamelliserade', 'karamelliserat',  # "karamelliserad lök" — method, not ingredient

    # Maturation/aging descriptors (not ingredients)
    'lagrad', 'lagrat', 'lagrade',  # "Mjukost Storsjö lagrad" - aging descriptor, not ingredient

    # Generic adjectives (not ingredients)
    'vanligt', 'vanlig',  # "vanligt socker" — adjective, not ingredient. "Havrekakor Utan Vanligt Socker" FP.

    # Size/heat level descriptors (not ingredients)
    'medium',  # "Dentastix Medium" - size descriptor, not ingredient
    'stark', 'starka',  # heat level - already in CONTEXT_REQUIRED_WORDS but also stop as standalone
    'kryddig', 'kryddiga', 'kryddigt',  # "kryddig korv" → korv is the ingredient, not kryddig

    # Nutritional/vitamin descriptors (not ingredients)
    'd-vitaminberikad', 'd-vitamin', 'vitaminberikad',  # "Olivolja D-vitaminberikad" — matches mjölk/rapsolja with same label
    'vitamin',  # nutritional descriptor, not a food ("Mjölk Vitamin D" keyword 'vitamin' matches 'd-vitaminberikad')
    'gentile',  # Zeta product line name, not an ingredient

    # Directional/reference words (not ingredients)
    'risotton',  # "till risotton" = "for the risotto" — direction, not ingredient

    # Origin/nationality descriptors (not ingredients)
    'amerikansk', 'amerikanska', 'svenska', 'svenskt', 'svensk',
    'italiensk', 'italienska', 'italienskt',
    'japansk', 'japanska',  # NOTE: "Japansk soja" has soja as the real keyword
    'kinesisk', 'kinesiska',
    'grekisk', 'grekiska', 'grekiskt',
    'engelsk', 'engelska', 'engelskt',
    'fransk', 'franska', 'franskt',
    'thailändsk', 'thailändska',
    'indisk', 'indiska', 'indiskt',

    # Color combinations (not ingredients) - "Småbladsmix Röd/grön" ≠ "röd/grön jalapeño"
    'röd/grön', 'rod/gron', 'röd/gron', 'rod/grön',

    # Too generic category words
    'tillbehör', 'tillbehor',  # "FIRA tillbehör hjärtan" - generic category word
    'hushåll', 'hushall',  # "Mjukost Smakrik Hushåll" - product line name, not ingredient

    # Sugar modifiers
    'tillsatt',  # "utan tillsatt socker" - modifier, not ingredient

    # Product descriptors
    'smakrik', 'smakrika',  # "Mjukost Smakrik" - flavor descriptor

    # Sun-dried preparation method (not ingredient)
    'soltorkad', 'soltorkade', 'soltorkat',  # "Russin Soltorkade" != "Soltorkade Tomater"

    # Too generic category/marketing words
    'dessert',  # "Karleksmums Dessert" - category word, matches "dessertost" falsely
    'protein',  # "High Protein Drink" - marketing word, matches "proteinmjöl" falsely

    # Scraper artifacts from Willys stripping ñ incorrectly ("Jalape o")
    # Note: jalapeño/jalapeno removed from STOP_WORDS — Willys sells fresh
    # "Chilli Jalapeno" which needs to match jalapeño recipes via keyword
    'jalapen', 'jalape',  # fragments from bad scraping

    # Texture/shape descriptors (not ingredients)
    'räfflade', 'krispiga', 'krispig', 'frasiga', 'frasig',  # "Waffle Fries Räfflade", "Fiskfiléer Frasiga"
    'dippvänliga', 'dippvanliga',  # "Pommes Chips Dippvänliga"
    'finkornig', 'finkornigt', 'finkorniga',  # texture descriptor ("salt finkornigt") — NOT an ingredient
    'blancherade', 'blancherad', 'blancherat',  # cooking method ("blancherade tomater") — NOT an ingredient

    # Cooking/preparation method descriptors (not ingredients)
    'grillad', 'grillade', 'grillat',  # "Kycklingbröst Grillad Skivad" — cooking method
    'skivad', 'skivade', 'skivat',  # sliced — cutting method
    'rostade', 'rostad', 'rostat',  # roasted — cooking method
    'havssalt',  # seasoning, no recipe asks for "havssalt" specifically

    # Diet/allergy descriptors (not ingredients)
    'glutenfria', 'glutenfri', 'glutenfritt',  # "Fiskfiléer Frasiga Glutenfria"
    'laktosfria', 'laktosfri', 'laktosfritt',  # diet label, not ingredient

    # English marketing/shape words (not useful as keywords)
    'waffle',  # "Waffle Fries" - shape descriptor, 'fries' maps to 'pommes' via synonyms

    # Standalone dough type (not useful alone — compounds like 'surdegsbröd' are fine)
    'surdeg',  # "Surdeg Pizza Xxl" is a pizza kit, not sourdough ingredient

    # Serving format descriptors
    'take', 'awa',  # "Take Awa" / "Take Away" - serving format

    # English food words (Swedish recipes use Swedish terms)
    'bananas',  # "Choc-go Bananas Granola" — English plural, substring of 'ananas'
    'caramel', 'carame',  # English candy flavor — "Caramel Glazed Bananas" is a product flavor, not ingredient
    'vegetables',  # "Minivårrullar Beef Vegetables" - Swedish recipes say 'grönsaker'

    # English seasoning/description words (Swedish recipes use Swedish terms)
    'pepper',  # "Quorn Tenders Salt Pepper" - English seasoning descriptor
    'marrowbone',  # brand/marketing word ("Marrowbone Beef Burger")
    'garlic',  # "Dark Soy & Garlic Cooking Sauce" — Swedish recipes say 'vitlök'
    'mushroom',  # "Mushroom Soy" — Swedish recipes say 'svamp'
    'japanese',  # "Japanese Soy" — origin descriptor, not a keyword
    'seasoned',  # "Ponzu Citrus Seasoned" — preparation descriptor
    'citrus',  # "Ponzu Citrus" — English fruit word, Swedish uses 'citron'/'lime'
    'strawberry', 'strawbe',  # "Strawberry Soygurt", "Strawbe Raspbe" — Swedish recipes say 'jordgubb'
    'raspbe',  # truncated "raspberry" on Greek Style Yoghurt products
    'peach',  # "Peach Mango Black Tea" — Swedish recipes say 'persika'
    'pyramid',  # "Black Tea Pyramid" — tea bag shape descriptor
    'snacks',  # "Paprika Snacks Mix" — snack descriptor
    'oriental',  # "Basmati Linser Smoky Oriental" — cuisine style descriptor
    'smoky',  # "Smoky Oriental" — flavor descriptor on ready rice

    # Generic Swedish adjectives (not ingredients)
    'blandat', 'blandad', 'blandade',  # "mixed" — "Salt Gott & Blandat" is candy

    # English marketing/packaging words
    'easy', 'quick',  # "Quick N' Easy/2 Port" — packaging descriptor

    # Portion/packaging descriptors
    'port',  # "2 Port" — portion count, not an ingredient

    # Temperature/state descriptors
    'rumstempererat', 'rumstempererad', 'rumstempererade',  # "smör, rumstempererat" — state, not ingredient
    'rumsvarmt', 'rumsvarma',  # "smör, rumsvarmt" — same as rumstempererat

    # Marketing/recipe filler words
    'favorit',  # "valfri favorit" — not an ingredient
    'eventuellt',  # "eventuellt 0.5 gingershoot" — optionality, not ingredient
    'ungefär',  # "ungefär 1 del kycklingbröst" — approximation, not ingredient

    # Quality/descriptor words and brand/variety names (not ingredients)
    'kvalitet', 'kvalité',  # "av hög kvalitet" — quality descriptor
    'långkornigt', 'kortkornigt',  # rice grain type — descriptor, not ingredient
    'fruttato',  # Zeta Fruttato brand name — not an ingredient
    'granny',  # Granny Smith apple variety — "äpple" is the keyword
    'skånsk', 'skånska',  # regional descriptor — "senap" is the keyword
    'intensitet',  # "justera efter önskad intensitet" — taste descriptor
    'bitterhet',  # "för mer bitterhet" — taste descriptor
    'fruktig',  # "mild och fruktig" — taste descriptor

    # Recipe instruction words (not ingredients)
    'konsistensen', 'konsistens',  # "för lösare konsistensen" — texture instruction
    'spackling',  # "för spackling och dekor" — baking instruction
    'pensling',  # "för pensling av bottnar" — baking instruction
    'bottnar',  # "pensling av bottnar" — baking instruction
    'hälften',  # "hälften svart kakao" — quantity word

    # Butchering/processing methods
    'styckad', 'styckade', 'styckat',  # "kanin, styckad i 6 delar" — cutting method
    'fermenterad', 'fermenterade', 'fermenterat',  # "krabba, fermenterad" — processing method
    'siktat', 'siktad', 'siktade',  # "bovetemjöl, siktat" — sifting method
    'utesluta',  # "går att utesluta" — cooking instruction
    'torrostade', 'torrostad', 'torrostat',  # "pumpakärnor, torrostade" — preparation method

    # Non-food descriptors found via excess-matches analysis (2026-03-21)
    'innehåller',  # verb "contains" — matches dinosaur books
    'standard',  # adjective — matches "Standardmjölkdryck"
    'organic',  # English adjective — matches supplement powders
    'finbladig', 'storbladig',  # leaf-size adjectives — descriptor, not shopping keyword
    'tropisk',  # adjective "tropical" — matches Plus Plus toys
    'bredbar',  # adjective "spreadable" — matches margarin/leverpastej
    'drickfärdig', 'drickfärdigt',  # adjective "ready to drink"
    '5-minuters',  # descriptor — matches "5-minuters sillfilé"
    'abisko',  # place/brand name (Polarbröd variety)
    'bag-in-box',  # packaging type
    'barista',  # coffee style descriptor
    'ceylon',  # origin descriptor for cinnamon
    'allround',  # descriptor — matches "BBQ rub Allround"
    'persillade',  # adjective "parsley-flavored" — describes grillolja, not separate parsley
    'variera',  # verb "vary" — "variera med blomkål, morötter..."
    'långkornig', 'långkornigt', 'kortkornig', 'kortkornigt',  # grain size descriptors — "Långkornigt Ris" should just match 'ris'
    'mjölig', 'mjöliga',  # texture descriptor — "Potatis Mjölig" should just match 'potatis', not 'mjöl'
    'kryddad', 'kryddade', 'kryddat',  # descriptor — "Kryddad Korv" should just match 'korv'
    'sötstark',  # descriptor — "sötstark senap" should just match 'senap'
    'lättsaltad', 'lättsaltade', 'lättsaltat',  # descriptor — "Chips Lättsaltade" should match 'chips'
    'lesvos',  # Greek island name — "Feta från ön Lesvos" should just match 'feta'
    'opastöriserad', 'opastöriserade',  # processing descriptor — "Pesto opastöriserad" should match 'pesto'
    'conference',  # pear variety name — "Päron Conference" should just match 'päron'
    'delicious', 'delicius',  # apple variety name / typo variant — "Golden Delicious" should just match 'äpple'
    'smaker',  # generic — "glass i olika smaker" not matchable
    'pulled',  # cooking method — "pulled BBQ chunkes" match on specific product, not 'pulled'
    'delade',  # preparation descriptor — "minimajs, delade på längden" matches "Linser Röda Delade"
    'halverad', 'halverade', 'halverat',  # preparation descriptor — "jordgubbar, halverade"
    'uppvispad', 'uppvispade', 'uppvispat',  # preparation descriptor — "uppvispat ägg"
    'naturlig', 'naturligt', 'naturliga',  # adjective — "Yoghurt Mild Naturlig", not an ingredient
    'dreamy',  # brand name (Oddlygood Dreamy) — not an ingredient
    'finger',  # "Petit bör finger" (lady fingers) matches "fingervarmt vatten"/"finger salt" — FP
    'fingervarm', 'fingervarma', 'fingervarmt',  # temperature instruction for yeast liquids
    'handfull',  # quantity cue — "1 handfull mynta", not an ingredient keyword
    'finskuren', 'finskurna',  # preparation descriptor (finely sliced) — "finskuren gräslök" interferes with gräslök matching
    'fileer', 'filéer',  # generic "fillets" — matches chicken/veg/herring fillets for any fish recipe
    'filéad', 'filead',  # past tense of "filéa" (to fillet) — "apelsin, filéad" extracts "fil" → filmjölk FP
    'ljusgrön', 'ljusgröna',  # color adjective — "(den vita och ljusgröna delen)" extracts keyword → Kronjus juice FP

    'utvalda', 'utvald',  # marketing term — "Göteborgs Utvalda" matches "Juice Våra Utvalda", "Flankstek utvald"

    'levande',  # adjective (alive/living) — "Levande kräftor" matches "Fermenterad dryck Levande bakteriekultur"
    'picnic',  # packaging format — "Ketchup Picnic size" matches "picnicbog" (pork cut)

    # Too-generic category words — specific sub-ingredients are matched separately
    'kött',  # "Marinad till grillat kött" — matches Beef Jerky. Specific meats (nötkött, fläsk) matched separately
    'grönsaker',  # "400 g grönsaker (t ex broccoli)" — the specific items are matched already
    'rotfrukter',  # "blandade rotfrukter" — specific roots (morot, palsternacka) matched separately
    'dryck',  # "(eller berikad vegetabilisk dryck)" — too generic, matches all laktosfri drinks

    # Kitchen tools (in cooking instructions, not food)
    'osthyvel',  # "hyvlat med osthyvel" — cheese slicer (kitchen tool), not food
    'potatisskalare',  # "skalad med potatisskalare" — vegetable peeler (kitchen tool), not food
})

NON_FOOD_KEYWORDS: FrozenSet[str] = frozenset({
    # Cleaning products
    'disk', 'diskmedel', 'maskindisk', 'handdisk', 'handdiskmedel', 'diskborste', 'diskduk',
    'städ', 'städning', 'rengör', 'rengöring', 'allrengöring', 'allrengörings',
    'tvättmedel', 'tvättlappar', 'sköljmedel', 'fläckborttagning',
    'rengöringsspray', 'städservett', 'torkpapper',
    'golvmopp', 'mopp',  # floor mop ("Wet Refills Golvmopp Våt Citron")
    # Note: 'refill' removed — blocks food products (Hallonsylt Refill, Äppelmos Refill).
    # Non-food refills are caught by other keywords (tvål, tvättmedel, schampo).
    'vat',  # detergent ("VAT" brand cleaning products)
    # Compound cleaning forms (Swedish word boundaries don't catch root inside compound word):
    'allrengöringsmedel',  # compound of 'allrengöring' — all-purpose cleaner
    'maskindiskmedel',  # compound of 'maskindisk' — dishwasher detergent
    'diskmaskinsrengöring',  # dishwasher machine cleaner
    'luftuppfriskare',  # air freshener (different word from 'luftfräschare' already blocked)
    'sprayflaska',  # spray bottle
    'vaskrensare',  # drain cleaner
    'fönsterputs',  # window cleaner
    'golvskrapa',  # floor squeegee/scraper
    'skurborste',  # scrubbing brush — 'borste' doesn't match inside compound
    'skurhink',  # cleaning bucket
    'sopborstar',  # brooms/brushes
    'städhandskar',  # cleaning gloves — 'städ' doesn't match inside compound
    'dammsugarpåsar',  # vacuum cleaner bags
    'microfiberdukar',  # microfiber cloths — 'duk' doesn't match inside compound

    # Seasoning/spice products (NOT ingredients)
    # "Crunchy Topping" is already blocked by 'topping'
    # Note: 'crunch' removed — too broad (blocks pommes frites "Super Crunch", müsli, etc.)
    'topping', 'crunchy topping',

    # Personal hygiene
    'tvål', 'tval', 'deo', 'deodorant', 'schampo', 'balsam',
    'dusch', 'duschgel', 'duschtvål', 'bad', 'kroppsvård', 'hårvård',
    'tandkräm', 'tandborste', 'munvatten', 'tandtråd', 'munsköl',
    'fluorskölj', 'fluorskolj',  # mouthwash
    'rakblad', 'rakhyvel', 'rakskum', 'rakvård',
    'handtvål',  # hand soap (compound: tvål doesn't match inside handtvål)
    'barntandborste',  # children's toothbrush

    # Skin care
    'salva', 'zinksalva', 'kräm', 'lotion', 'bodylotion', 'ansiktskräm',
    'hudvård', 'hudkräm', 'fuktkräm', 'dagkräm', 'nattkräm',
    'solkräm', 'solskydd', 'after sun',
    # English skin care (e.g., "Vitamin C Citrus Day Cream Glow Boost")
    'day cream', 'night cream', 'face cream', 'body cream',
    'glow boost', 'skin care', 'skincare',

    # Baby products
    'blöj', 'blöja', 'blöjor', 'blöjpåse', 'blöjpase',
    'nappy', 'barnvård', 'babyvård', 'babymat',
    'barnmat',  # "Barnmat Grönsaker & kyckling 6m" — baby food, not recipe ingredients
    'barnsnacks',  # "Barnsnacks Majs & linssköldpaddor 8m" — baby snacks
    'barngröt',  # "Barngröt Röda bär havre & korn 6m" — baby porridge
    'grötsmoothie',  # "Grötsmoothie jordgubb, banan, havre & dinkel 6m" — baby porridge smoothie
    'päronpuré',  # "Katrinplommon & päronpuré Ekologisk 4m" — baby fruit puree
    'smoothie äpple & kokosnöt 6m',  # specific ICA baby smoothie (too broad to block "smoothie" generically)
    'våtservett', 'vatservett', 'barntvål', 'napp', 'nappar',
    'silikon', 'esska',  # Esska = baby products brand

    # Household items
    'servett', 'servetter', 'papper', 'hushållspapper', 'toalettpapper',
    'borste', 'trasa', 'duk', 'handduk', 'mugg',
    # Compound tableware (root form 'mugg'/'duk' doesn't match inside compound):
    'kaffemuggar',  # coffee mugs — 'mugg' doesn't match compound
    'vinglas',  # wine glasses
    'plastglas',  # plastic cups
    'engångsduk',  # disposable tablecloth — 'duk' doesn't match compound
    'avfallspåsar',  # garbage bags plural — 'avfallspåse' singular already blocked
    # Note: 'svamp' removed — ambiguous (mushroom vs sponge). Sponge products use
    # compound forms (disksvamp, kökssvamp, badsvamp, putssvamp) which are caught below.
    'disksvamp', 'kökssvamp', 'badsvamp', 'putssvamp', 'skrubbsvamp',
    'metallsvamp', 'skosvamp', 'refillsvamp',
    'soppåse', 'sopsack', 'fryspåse', 'avfallspåse',
    'förvaringsask', 'forvaringsask',
    'toafräschare', 'toafraschare', 'toa',
    'toalettfräschare', 'toalettfraschare',  # "Lime Refill Fresh Discs Toalettfräschare"
    'luftfräschare', 'luftfraschare',  # "Freesia&jasmin Duopack Luftfräschare"

    # Pet/animal products
    'vildfågelmat', 'vildfågel', 'vildfågelblandning',  # bird feed ("Vildfågel Solrosfrön 4kg")
    'kattmat', 'hundmat', 'kattsand', 'bajspåse', 'hundbajspåse',
    'kattgodis', 'hundgodis', 'kattsnacks',  # "Kattsnacks Sticks Lax & öring"
    'kattströ', 'kattstro',  # cat litter ("Kattströ Bentonit Vit Lavendel" matched baking recipes via 'lavendel')
    'dentastix',  # Pedigree dental treats for dogs
    'pedigree',  # pet food brand
    'dreamies',  # cat treat brand
    'pouch',  # "Cat Pouch Chicken" — pet food format (wet food packets)
    'bilanx',  # pet food brand ("Bilanx Kyckling Anksticks", "Original Junior Kyckling")
    # Pet food types (78 products with "kyckling", 63 with "lax" in pet categories!)
    'torrfoder',  # dry pet food (hund & katt)
    'hundfoder', 'kattfoder', 'helfoder', 'fiskfoder',
    'fågelmat',  # bird food
    'tuggben', 'tuggpinnar', 'tuggpinne',  # dog chew treats
    'tuggrulle', 'tuggrullar',  # dog chew rolls
    'munchy',  # dog chew brand name
    'hundsnacks', 'hundtugg',  # "Softies Godbitar med Kött Hundsnacks"
    'godbitar',  # "Godbitar med Kött" — pet treats
    'softies',  # pet treat brand ("Softies Godbitar")
    'rocky sticks',  # "Ox & Lamm Rocky Sticks Hund Tugg" — pet treats

    # Hair products
    'hårfärg', 'harfarg', 'hårvax', 'hårspray', 'hårgelé', 'hårolja',
    'balsamspray',  # "Kids Hallon Balsamspray" — hair product, not hallon
    'serum', 'inpackning', 'hair',  # "Growth Booster Hair Serum Inpackning"

    # Toys and games
    'lego', 'fortnite', 'minecraft', 'pokemon', 'playmobil',
    'leksak', 'leksaker', 'badleksak', 'spel',
    'charader',  # board game ("Charader Bluey")
    'playbox',  # craft bead brand ("Pärlor 1000st Playbox", "Pärlplattor 5-p Playbox")
    'pärlplattor', 'rörpärlor', 'heishipärlor', 'kristallpärlor',  # craft beads
    'pysselset', 'pysselbox', 'pärlpysselset',  # craft kits

    # Children's books/media/stationery (NOT food!)
    'valparna', 'valp',  # "Valparna hittar en hemlig djungel" is a book, not food
    'klistermärken',  # sticker books
    'aktivitetsbok',  # activity books
    'anteckningsbok', 'anteckingsbok',  # notebooks
    'spiralblock',  # spiral notebooks
    'pysselbok',  # craft books
    'pennfodral',  # pencil cases
    'fiberpennor', 'tuschpenna',  # pens/markers
    'suddgummi',  # erasers
    'gummibandsmapp',  # rubber band folders
    'godnattsagor',  # bedtime story books
    'lärabok',  # teaching books ("Min första lärabok")
    'målarbok', 'målarboken',  # coloring books
    'tygbok',  # fabric books ("Tygbok Prassla med Babblarna")
    'babblarna',  # children's characters (books/toys, not food)
    'busy book',  # activity books ("mini busy book")
    'måla',  # paint/coloring books ("Måla mini", "Måla med vatten")
    'mandala',  # mandala coloring books
    'squishmallows',  # toy brand
    'paw patrol',  # children's brand
    'alfons',  # children's character (Alfons Åberg)

    # Clothing (ICA sells clothes via mywear/ICA I love eco brands)
    'mywear',  # ICA's clothing brand (~100 products: socks, pajamas, underwear)
    'resteröds',  # underwear/boxer brand
    'strumpa', 'strumpor',  # socks
    'socka', 'sockor',  # socks (variant)
    'hiddensocka',  # hidden/ankle socks
    'raggsocka',  # wool socks
    'thermosocka',  # thermal socks
    'knästrumpa',  # knee socks
    'herrboxer',  # men's boxer shorts
    'pyjamas', 'pyjamasbyxa', 'pyjamastopp',  # pajamas
    'babypyjamas',  # baby pajamas
    'klänning',  # dresses ("Klänning Elsa Disney Frozen")
    'handske', 'skinnhandske',  # gloves
    'hidden',  # hidden/ankle socks ("Hidden 3p svart" - ICA I love eco brand)

    # Winter/car/outdoor accessories (NOT food!)
    'snöborste', 'snoborste',  # snow brush ("Snöborste med Skrapa")
    'broddar',  # ice grips for shoes
    'isskrapa',  # ice scraper
    'grillkol',  # charcoal for grilling (NOT food ingredient)
    'reflex',  # "Reflex Tassel Silver RFX" - safety reflector, NOT food

    # Party/decoration accessories (NOT food!)
    'drinkpinne',  # drink stirrer stick ("Drinkpinne Discokula Silver 19cm")
    'discokula',  # disco ball decoration
    'ballong', 'ballonger',  # balloons ("Ballong Hjärta Röd")
    'konfettibomb', 'konfettibomber',  # confetti bombs (singular + plural)
    'proseccopong',  # prosecco pong game
    'uppläggningsfat',  # serving platter (tableware, not food)
    'engångsgaffel', 'engångskniv', 'engångssked',  # disposable cutlery

    # Other non-food
    'näsduk', 'nasduk', 'näsdukar', 'nasdukar',
    'tamponger', 'tampong', 'bindor', 'binda', 'trosskydd',
    'bomullspinnar', 'bomullsrondeller',  # cotton buds/pads
    'värmeljus', 'stearinljus', 'kronljus', 'kronjus', 'tändare', 'tändstickor',
    'tändkuber',  # fire starters
    'doftljus',  # scented candles ("Doftljus Granatäpple", "Doftljus Mango")
    'kronljus',  # taper candles
    'antikljus',  # antique-style candles
    'blockljus',  # block candles
    'ljusslinga',  # string lights / LED light chains
    'blommor', 'tulpan', 'tulpaner', 'ros', 'rosor', 'blomma',
    'bukett',  # flower bouquet ("Bukett Botanicals" ≠ broccolibuketter)
    'sugrör', 'sugror',  # straws ("Smoothie Sugrör" ≠ smoothie)
    'sminkspegel',  # makeup mirror
    'vattenflaska',  # water bottle (NOT food)
    'grilltändare',  # grill lighter
    'tandborstrefill',  # toothbrush refill
    'städsvamp',  # cleaning sponge ("Scrub Mommy Städsvamp")
    'scrub daddy', 'scrub mommy',  # cleaning product brand
    'toalettrengöring',  # toilet cleaner
    'wc-block', 'wc bref', 'wc',  # toilet block/cleaner ("WC Active Clean Citrus")
    'handtvättmedel', 'handtvatmedel',  # hand wash detergent
    'förbehandlare',  # stain pre-treatment ("Förbehandlare Tvätt")
    'galge',  # hangers ("Galge i plast", "Galge i trä")
    'hörlur',  # headphones
    'popcornmaskin',  # popcorn machine (appliance, not food)
    'resekudde',  # travel pillow
    'flyttlåda',  # moving box
    'lunchlåda',  # lunch box (container, not food)

    # Storage/organization products (NOT food!)
    'redskapsförvaring', 'förvaring', 'forvaring',  # "Redskapsförvaring Chunky" is NOT salsa

    # Gift packaging (NOT food contents!)
    'presentask', 'present', 'presentförpackning',  # gift boxes with chocolates etc

    # Decorations (NOT food!)
    'paljett', 'paljetter', 'dekoration', 'dekorationer',  # craft/baking decorations

    # Home/party decoration brands
    'star trading',  # "FIRA tillbehör hjärtan 10-p Star Trading" - LED lights/decorations
    'fira',  # party decorations brand/series

    # Baby food (88 products with ingredient words like kyckling, lax, mango, äpple)
    'barnmat',  # baby food category
    'barnsnacks',  # baby/toddler snacks ("Barnsnacks Banan jordgubb 8m")
    'välling', 'vallning',  # baby/toddler porridge drinks (34 products)
    'klämmis', 'klammis',  # baby food squeeze pouches
    'klämpåse', 'klampase',  # baby food squeeze pouches (Mathem variant)
    'fruktstång', 'fruktstang',  # baby fruit sticks ("Fruktstång Äpple 12M")
    'fruktmums',  # baby fruit puree pouches
    'fruktmellis',  # baby fruit squeeze pouches ("Fruktmellis Äpple jordgubb banan & hallon Från 6mån")
    'yogofrukt',  # Nestle baby yogurt line ("Min YogoFrukt Jordgubb & banan Från 6m")
    'lovemade',  # baby food brand ("Potatis & biffgryta 8m 185g Lovemade")
    'min frukt',  # Nestle baby food product line ("Min frukt Äpple & blåbär Från 5m")
    'ella\'s kitchen', 'ellas kitchen',  # baby food brand (with and without apostrophe)
    'hipp',  # baby food brand (HiPP organic baby food)
    'knatteplock',  # baby snack brand ("Grötbar blåbär & vanilj 1 år 25g Knatteplock")
    'danonino',  # kids yogurt brand ("Banan Jordgubbsyoghurt 2,1% 4-p 280g Danonino")

    # Health shots / snack bars / snack cups (NOT cooking ingredients)
    'shots',  # health shots ("Shots Immun Ingefära Äpple Citron" ≠ ingefära)
    'råwbar', 'rawbar',  # raw snack bars for kids ("Råwbar Äpple Morot Kanel" ≠ äpple)
    'bara för nu',  # snack cups ("Bara För Nu Jordgubb & Hallon" ≠ jordgubbar)

    # Candy/gum (contain fruit/flavor words but are NOT ingredients)
    'tuggummi',  # 30+ products with mint, melon, hallon
    'halstablett', 'halstabletter',  # throat lozenges with citron, mint

    # Tablets/placemats (NOT food ingredients)
    # 'tabletter' extracted from "Maskindiskmedel Tabletter" matches ICA placemats ("Tablett Irma Grön")
    # and egg dye tablets. 'buljongtablett' is NOT blocked — it's a compound matched as whole keyword.
    'tablett', 'tabletter',

    # Medicine/supplements (NOT food!)
    'brustablett',  # effervescent tablets ("C-vitamin Citron Brustablett" ≠ citron)
    'tuggtablett',  # chewable tablets ("D-vitamin Tuggtablett Jordgubb" ≠ jordgubb)
    'sugtablett', 'sugtabletter',  # lozenges ("Strepsils Honung & Citron Sugtabletter" ≠ honung)
    'halstablett', 'halstabletter',  # throat lozenges
    'strepsils',  # throat lozenge brand
    'vätskeersättning',  # rehydration supplements ("Vätskeersättning Hallon" ≠ hallon)
    'resorb',  # rehydration medicine brand ("Resorb Sommar Jordgubb" ≠ jordgubb)
    'nipenesin',  # cough medicine ("Nipenesin Sirap 20mg/ml" ≠ sirap)
    'kosttillskott',  # dietary supplements ("Kosttillskott Tran Citron 150ml" ≠ citron)
    'energitillskott',  # energy gels ("Energitillskott Gel Citron 25ml" ≠ citron)
    'proteinpulver',  # protein powder ("Proteinpulver Whey-80 Jordgubb" ≠ jordgubb)
    'måltidsersättning',  # meal replacement ("Måltidsersättning Choklad 500ml" ≠ choklad)
    'måltidsshake',  # meal replacement shake ("Måltidsshake Choklad Karamell" ≠ choklad)
    'biosalma',  # supplement brand — all products are supplements, not food
    'active care',  # supplement brand ("Vitamin Björnar D-vitamin Jordgubb 60-p Active Care")
    'laxolja',  # fish oil supplement ("Norsk laxolja Hund & katt" — pet supplement!)
    'kreatin',  # workout supplement ("Kreatin monohydrat 500g")
    'collagen',  # supplement ("Pure Collagen 97% Protein")

    # Educational/book products (NOT food!)
    'siffror',  # "Lär dig siffror och tal" - children's book/game
    'målarbok',  # "Squishmallows målarbok" - coloring book, not food

    # Cookbooks / food books (NOT food ingredients!)
    'recept',  # "Grilla! Festliga recept och enkla tekniker" - cookbook
    'kokbok', 'kokboken',  # cookbook
    'kompaniet',  # "Väninnorna på Nordiska Kompaniet" - book
    'tekniker',  # "enkla tekniker" in cookbook titles

    # Light bulbs / electronics (NOT food!)
    'led', 'e27', 'e14',  # "LED Normal E27 470lm(40W) ICA"
    'dimbar', 'lumen',  # light bulb descriptors
    'halogen', 'glödlampa', 'glodlampa',

    # Ready-made pastries (flavor words ≠ raw ingredients)
    'gifflar',  # "Gifflar Kanel" → 'kanel' matches cinnamon recipes — wrong

    # Tobacco / snus / nicotine products (contain fruit/flavor names!)
    # ~100+ products with äpple, lime, mango, citrus, lingon, mint as flavors
    'snus', 'portionssnus',  # "Lingon White Large Portionssnus"
    'tobaksfritt',  # "Loop Spicy Äpple Tobaksfritt Snus"
    'cigaretter', 'cigarett',  # "John Silver Filter Hp Cigaretter"
    'nikotin', 'nikotinfritt',  # nicotine products

    # Pet treats (contain meat names as flavors!)
    'belöningsgodis', 'beloningsgodis',  # "Soft Drops Lamm Belöningsgodis"
    'trainers',  # "Soft Trainers Lamm Belöningsgodis"

    # Chemical/technical terms that appear in ingredient lists but aren't food
    'natrium',  # "Havssalt Finkornigt Mindre Natrium" — chemical term, not food

    # Kitchen tools / non-food products that slip through category filters
    'bakformar', 'bakform',  # "Bakformar 240st Toppits" — baking molds, not food

    # Garden/plant products
    'dahlia',  # "Dahlia Creme de Cognac gul/orange ICA Garden" — flower, not food
})

PROCESSED_FOODS: FrozenSet[str] = frozenset({
    # Heavily processed meats (not usable as fresh meat in recipes)
    'ölkorv', 'olkorv',  # Not used in Swedish cooking

    # Instant/ready-made meals (not fresh ingredients)
    'snabbnudlar', 'snabb nudlar',
    'instantnudlar', 'instant nudlar', 'instant noodles',
    # "kyckling" recipe should NOT match "Snabbnudlar Kyckling"
    # NOTE: 'nudlar'/'noodles' moved to CARRIER_PRODUCTS — strips flavor words (kyckling, beef)
    # but keeps nudlar keyword so "Nudlar Udon" → udonnudlar (via space norm) can match.
    # Snabbnudlar/instantnudlar still fully blocked above.
    # Bare carrier keyword blocked via SOLO_KEYWORD_BLOCK.
    'cup noodles', 'cup noodle',  # instant cup noodles
    'rabokki',  # Korean instant noodle dish ("Rabokki Hot Chicken")
    'instan',  # truncated "instant" in product names ("Noodles Instan Chicken")
    # NOTE: '5-pack' removed — blocked "Pitabröd 5-pack". Noodle 5-packs caught by other terms.
    # NOTE: 'flavour'/'flavou' removed — blocked veganost (Violife). Noodles caught by 'instantnudlar'/'snabbnudlar'/'cup noodles'.
    'japchae',  # Korean glass noodle ready meal ("Spicy Japchae Korean Style")
    'tom yum',  # Thai soup flavor — "Tom Yum Risnudlar Glutenfri" is flavored noodles, not plain
    'rostade nudlar',  # "Bulgur Grov med Rostade Nudlar" — bulgur mix, nudlar is filler
    'vegetable rice noodles',  # instant rice noodles ("Vegetable Rice Noodles Glutenfri")
    'puffar',  # cereal puffs ("Nesquik Puffar") - NOT cooking puffs
    'puffat',  # "Puffat Ris" - puffed rice snack, NOT cooking rice
    'kycklingcurry',  # "Kycklingcurry Ris" - ready meal, not plain rice
    "quick n'",       # "Basmati Saffran Quick N' Easy/2 Port" - ready meal, not plain rice

    # Smoked/cured fish — handled via SPECIALTY_QUALIFIERS + BIDIRECTIONAL instead.
    # "Kallrökt Lax" IS a real cooking ingredient (hundreds of recipes need it),
    # so we use qualifiers to prevent it matching plain "lax" recipes, not a
    # blanket block.  Kept here: compound forms that are never recipe ingredients.
    'rökt lax', 'rokt lax',  # catch "Rökt Lax Peppar" etc. (compound product names)

    # NOTE: 'torkad'/'torkade'/'torkat' moved to BIDIRECTIONAL_SPECIALTY_QUALIFIERS
    # so dried products match when recipe also says "torkad" (e.g. "torkad shiitake")

    # Note: 'kondenserad' REMOVED from PROCESSED_FOODS — 59 recipes use kondenserad mjölk.
    # Handled by PROCESSED_PRODUCT_RULES for 'mjölk' instead (blocks unless recipe says "kondenserad").
    'dulce de leche',  # "Dulce De Leche Karamelliserad Mjölk" - caramelized milk product
    # NOTE: chokladpraliner REMOVED — moved to CARRIER_PRODUCTS (9 recipes need pralines)
    'chokladägg',  # "Chokladägg LINDOR Mjölk" — Easter candy, not eggs or chocolate ingredient

    # Note: "korv" (sausage) is NOT filtered - falukorv/grillkorv ARE used in cooking!

    # READY-MADE CHEESE PRODUCTS - not usable as fresh cheese
    # "cheddar" recipe should NOT match "Mac and Cheese"
    'mac and cheese', 'mac & cheese', 'mac och cheese', 'macaroni',
    'ostbricka',  # cheese platter/board - not for cooking
    'smältost', 'smaltost',  # processed cheese (burgers) - NOT real cheddar/ost

    # PREPARED VEGETABLE/FRUIT MIXES - not individual ingredients
    'surkål', 'surkal',  # "Surkål med Morot" — fermented cabbage, not carrots
    'kålmix', 'kalmix',  # "Kålmix Vitkål&morot" — coleslaw mix, not carrots or cabbage
    'morötter ärter', 'morotter arter',  # frozen peas+carrots mix, not individual vegetables
    'ärter majs paprika',  # "Ärter Majs Paprika Fryst" — frozen veggie mix
    'grönsaker ärtor majs',  # "Grönsaker Ärtor Majs Paprika Fryst" — frozen veggie mix
    'mango hallon persika',  # "Mango Hallon Persika Fryst" — frozen fruit mix
    'hallon blåbär', 'hallon blabar',  # "Hallon Blåbär Frysta" — frozen berry mix

    # CONDIMENT/SPREAD PRODUCTS - not the base ingredients
    # 'hasselnötkräm' REMOVED from PROCESSED_FOODS — it maps to 'nötkräm' via INGREDIENT_PARENTS
    # so it correctly matches nötkräm recipe ingredients. 'kakao' FP protected by PRODUCT_NAME_BLOCKERS.
    'mangoraja',  # "Mangoraja Mango&curry" — mango chutney, not mango or curry
    'favabön kikärt foul',  # prepared Middle Eastern fava bean/chickpea stew, not plain chickpeas

    # DAIRY DRINKS - not recipe ingredients
    'drickfil',  # "Profibi Hallon Drickfil" — drinkable fil, not hallon
    'profibi',  # Arla Profibi brand — flavored dairy drink

    # SNACK BRANDS - flavored snacks with ingredient-sounding names
    'bara vara',  # "Bara Vara Mango & Ananas" (Exotic Snacks) — dried fruit snack
    'bara för nu',  # "Bara För Nu Jordgubb & Hallon" (Exotic Snacks)
    'sunshine delig',  # dried fruit snack brand ("Strawberry Mango Dried", "Torkad Mango")
    'sunshine delight',  # alternate spelling of same brand

    # SNACK FOODS - not recipe ingredients
    'comunamandlar',  # truffle-flavored almonds snack — not a cooking ingredient
    'cheese snack',  # "Cheese Snack Tryffel" — processed snack, not cheese
    'rye snacks',  # "Cheddar Cheese Rye Snacks" (Finn Crisp) — flavored crackers, not cheese
    'salami snacks',  # "Classic/Garlic/Parmesan Salami Snacks" — too small for cooking
    'pommessticks',  # potato stick snacks (OLW etc.) - NOT pommes frites
    'krisp',  # "Krisp Jordgubb Havre" / "Kakao Dadel Krisp Granola" — snack bars, not salad
    'majssnacks',  # "Majssnacks Corners Chili & Lime Style" - snack, not ingredient
    'cheetos',  # "Cheetos med ost & ketchupsmak" — flavored snack, not cheese
    'västkustchips', 'vastkustchips',  # chip brand compound word ("Västkustchips Havssalt & Vinäger")
    # Note: 'chips' removed - tortilla chips CAN be recipe ingredients
    # chips is in CARRIER_PRODUCTS instead (strips flavor words, keeps 'chips' keyword)

    # READY-MADE SAUCES/CONDIMENTS - not the individual ingredients
    'cooking sauce',  # "Dark Soy & Garlic Cooking Sauce" — not soy sauce/garlic
    'bönsalsa', 'bonsalsa',  # "Bönsalsa Ready To Eat Bean Chili Salsa" — condiment, not chili/beans

    # VEGAN/QUORN DELI SLICES — processed pålägg, not raw ingredients
    # "Skivor Tomat&basilika" (Quorn), "Vegoskivor Tomat&basilika" (Pärsons),
    # "Quorn Rökt Smak Skivor", "Quorn Chiqin Skivor"
    # NB: Can't use bare 'skivor' — would block "Lövbiff Skivad", "Halloumi Skivad" etc.
    'vegoskivor',
    'quorn rökt smak skivor', 'quorn chiqin skivor',
    'skivor tomat',  # "Skivor Tomat&basilika" (Quorn) — deli product starting with "Skivor"

    # READY-MADE MEALS/WRAPS — not raw ingredients
    'dillstuvad',  # "Dillstuvad potatis 500g" — prepared dish, not potatoes
    # Note: 'rödbetssallad' moved to CARRIER_PRODUCTS — keeps keyword so it matches
    # recipes asking specifically for "rödbetssallad", but strips 'fraiche' as flavor

    # PÂTÉ PRODUCTS - flavored pâté is not the flavor ingredient
    # Note: 'leverpastej' moved to CARRIER_PRODUCTS — keeps 'leverpastej' keyword
    # but strips flavor words (gurka, pepparrot), so recipes can find leverpastej products.
    'pastej',  # "Pastej Karljohansvamp Vegansk" is NOT karljohansvamp

    # KAVIAR: removed from PROCESSED_FOODS — Kalles Kaviar is a real Swedish
    # cooking ingredient.  "Kaviar ägg randig" matching "ägg" recipes is
    # handled by SECONDARY_INGREDIENT_PATTERNS instead.

    # ICE CREAM PRODUCTS - not recipe ingredients
    'glasspinne', 'glasstrut', 'glasstårta', 'glassbåt', 'glassbat',
    'isglass',  # cheap popsicles — fruit flavor names leak as keywords (päron, mango, hallon)
    'smoothieglass',  # frozen smoothie bars ≠ regular ice cream (jordgubbsglass etc.)

    # NOTE: glutenfri moved to STOP_WORDS — it's a diet label, not a product type
    # Glutenfri tortillas/pasta/bröd are functionally the same as regular versions

    # READY-MADE SOUPS - "Ärtsoppa med fläsk" is NOT fläsk as ingredient
    'soppa', 'soppor',  # all ready-made soups: "Potatis Purjo Soppa", "Tomatsoppa", etc.
    'ärtsoppa', 'artsoppa',  # traditional Swedish pea soup with pork (also caught by 'soppa')

    # COOKIES/BISCUITS/CHOCOLATE/CEREAL brands - not recipe ingredients
    'ballerina', 'singoalla',  # NOTE: 'digestive'/'digestives' removed — used in cheesecake recipes
    'dinosaurus',  # "Dinosaurus Mjölkchoklad" — cookie brand, not baking chocolate
    'hobnobs',  # "Hobnobs Mjölkchoklad" — biscuit brand, not baking chocolate
    'tuc',  # "Tuc Paprika" is crackers, not paprika
    'trésor', 'tresor',  # Kellogg's cereal brand ("Trésor Cookies & cream")
    # NOTE: 'marabou' REMOVED — bakchoklad (31 recipes) needs to match. Carrier 'choklad' handles flavor stripping.
    'chokladdoppade',  # chocolate-dipped frozen items ("Chokladdoppade Hallon Frysta")
    'chokladkaka',  # chocolate bar/cake product (not a baking ingredient)
    'delikatessboll',  # "Delikatessboll Choklad 8-pack" — bakery snack, not baking chocolate
    'wafers',  # "Wafers Choklad" — chocolate wafer biscuit, not baking chocolate
    'jätten', 'jatten',  # "Chokladsmak Rån Jätten" / "Jätten Vanilj Rån" — wafer snack brand
    'chokladtårta', 'chokladtarta',  # "Toblerone Chokladtårta Fryst" / "Chokladtårta Fransk" — pre-made cakes
    'pineapple chocolate dipped',  # "Pineapple Chocolate Dipped" — candy-coated fruit
    'fikon choklad',  # "Fikon Choklad" — chocolate-covered figs, not baking chocolate
    'mango choklad',  # "Mango Choklad Torkad Frukt" — chocolate-covered dried fruit
    'rulltårta', 'rulltarta',  # swiss roll cake ("Rulltårta Jordgubb") — not fresh fruit
    'drömrulltårta', 'dromrulltarta',  # dream swiss roll variant
    'trinitario',  # "70% Cacao Mörk Choklad Trinitario Bönor" — cacao bean chocolate, not food bönor

    # CRISP BREAD variants - not substitutes for regular bread
    'lilla lingon',  # "Lilla Lingon" - Leksands crispbread brand, not fresh lingon
    'havretrekant',  # "Havretrekant" is NOT "hamburgerbröd" or "tortillabröd"
    'leksandsbröd', 'leksandsbrод', 'leksands',  # crisp bread brand
    'fröfrallor', 'frofrallor', 'fröfralla', 'frofralla',  # "Fröfrallor Pumpa Solros" — seed rolls, not pumpa/solros ingredients

    # READY MEAL brands and product types
    'kitchen joy', 'indian cube', 'thai cube', 'green cube',  # Asian ready meal brands
    'thai mahal',  # "Thai Mahal Curry Mango" — ready meal brand, not raw ingredients
    'real littles',  # "Real Littles Liquid Charms" — toy product, not food
    'sweet & sour', 'sweet sour', 'sweet/sour',  # ready-made sauce/meal, NOT chilisås
    'butter chicken', 'tikka masala', 'chicken tikka',  # ready meal flavors
    'gul curry', 'grön curry', 'gron curry', 'röd curry', 'rod curry',  # curry ready meals ("Kyckling i Gul Curry Fryst")
    'lagat & klart', 'lagat och klart',  # "Cooked & Ready" brand - pre-cooked meals
    'frikadeller',  # meatballs in sauce - ready meal, not ingredient
    'fiskbullar',  # "Fiskbullar i Buljong/Dillsås" — processed fish product, not buljong/dill
    'sylta',  # "Sylta med Kalvkött" — processed head cheese, not kalvkött
    'cabanossy',  # "Cabanossy Anchochili" — dried sausage, not ancho/chili
    # NOTE: 'rostad lök' REMOVED from PROCESSED_FOODS — now handled via space normalization
    # ('rostad lök' → 'rostadlök') so recipes get specific keyword 'rostadlök' matching
    # the product. Was blocking 42 recipes from matching the actual product.

    # Cocktail/snack olives - not cooking ingredients
    'pimento',  # "Oliver Pimento" - cocktail olives stuffed with pepper

    # BEER products in 'other' category
    'norrlands guld',  # "Norrlands Guld Lager" — beer, not food ingredient

    # CANNED PROCESSED MEAT - not suitable for fresh meat recipes
    'luncheon',  # "Fläsk Luncheon" — canned SPAM-like product, not fresh fläsk

    # FINISHED BAKERY/SPECIALTY PRODUCTS - not raw ingredients
    'jubileumskaka', 'jubileumskakor',  # "Jubileumskaka Vallmo" — finished cookies, not vallmofrön
    'confit',  # "Fikon & Valnöt Confit" — preserved specialty, not raw figs/walnuts
    'pavé', 'pave',  # "Pavé Surdeg Vallmo" — finished bread product, not poppy seeds
    'kulpotatis',  # "Kulpotatis Kryddig" — seasoned potato product, not a spice
    'ice tea',  # "Ice Tea Skogsbär" — ready-made drink, not fresh berries

    # GLAZE/CONDIMENT products - not vinegar
    'glassa',  # "Glassa Balsamica" — ready-made glaze, not balsamvinäger

    # FLAVORED MARMALADE - whisky/fikon is flavor, not ingredient
    'whisky marmelade',  # "Orange Whisky Marmelade" — marmalade, not actual whisky
    'fikonmarmelad',  # "Fikonmarmelad Med Lagerblad" — jam, not bay leaves

    # NOTE: 'sia glass', 'emil i lönneberga' REMOVED — glass products need to match glass recipes.
    # Carrier 'glass' handles flavor stripping (jordgubb, vanilj etc. stripped correctly).

    # READY-MADE NOODLE MEALS - not plain noodles
    'äggnudlar kyckling', 'aggnudlar kyckling',  # "Äggnudlar Kyckling Grönsaker" (Kin Food)
    'äggnudlar grönsaker', 'aggnudlar gronsaker',  # ready meal with vegetables

    # SAUCE PRODUCTS - not the base ingredient
    'dill pepparrot fisksås', 'dill pepparrot fisksas',  # Swedish cream sauce ≠ Thai fish sauce
    'vaniljsås', 'vaniljsas',  # "Kyld Vaniljsås Grädde & Mjölk" ≠ cream or milk
    # READY MEALS - block entire product (more aggressive than CARRIER_PRODUCTS)
    'västerbotten paj', 'vasterbotten paj',  # "Västerbotten Paj Fryst" — ready-made pie, not cheese
    'stuvning',  # "Stuvning Champinjon" / "Stuvning Champinjoner Skinka" — ready meal, not mushrooms
    'kroketter',  # "Kroketter Potatis" — processed potato product, not fresh potatoes
    'pasta carbonar', 'pasta bolognes',  # frozen pasta meals without "/1 Port" suffix
    'rigatoni kyckling',  # "Rigatoni Kyckling Pesto" — refrigerated ready meal
    'ssamjang',  # "Ssamjang Pasta Korean Dipping Sauce" — Korean paste, not pasta
    'kyckling curry',  # "Kyckling Curry" (Redo) — ready meal, not raw chicken
    'köttfärssås', 'kottfarssas',  # "Köttfärssås och Spagetti 500g" — complete meal, not pasta
    'tagliatelle lax',  # "Tagliatelle lax & spenat 370g" — frozen fish pasta dish
    'kyckling panaeng',  # "Kyckling Panaeng Red Curry" — ready meal
    'paneng red curry',  # "Kycklingbröstfilé strimlad paneng red curry" — marinated fillet, too specific
    'chicken curry',  # "Chicken Curry Baguette" — filled baguette, not chicken
    'ärtor med fläsk', 'artor med flask',  # pea soup — ready meal, not peas or pork
    'semlebullar',  # frozen semla buns — not kardemumma
    'kardemumma stora bullar',  # "Kardemumma Stora Bullar Frysta" — frozen buns, not cardamom
    'kanelbulle', 'kanelbullekaka', 'kanelbullesemla',  # bakery items ("Kanelbulle Dadlar" ≠ plain dadlar)
    'dadlar jordgubbe', 'dadlar lakrits', 'dadlar salt kola',  # flavored date snacks ≠ plain dates
    'körsbärstomatkräm', 'korsbarstomat kräm',  # crema di ciliegino — specific product, not cherry tomatoes
    'aloe vera', 'aloe',  # "Mango Aloe Vera Pet" drink + skin care products
    'duokaka',  # "Duokaka Blåbär" — cookie/cake, not blueberries
    'vinbladsdolmar',  # "Vinbladsdolmar Bulgur" — ready-made dolma, not bulgur
    'fikonbollar',  # "Fikonbollar Aprikos Kokos" — snack balls, not aprikos/kokos
    # 'sallads kyckling' removed — now handled via SPACE_NORM → färdigkyckling
    'färdigmat', 'faardigmat',  # "Färdigmat Köttbullar" should NOT match köttbullar recipe
    'gooh',  # ready meal brand
    'dafgårds', 'dafgård',  # Dafgårds ready meal brand (pannbiff, lasagne, schnitzel etc.)
    'zeinas',  # Zeinas ready meal brand ("Basmati Linser Smoky Oriental Quick N' Easy")
    'dagens',  # Dagens frozen ready meals ("Dagens Rostad Kyckling Fryst", "Dagens Pasta Fyra Ostar")
    'tareqs',  # Tareqs ready meal brand (lasagne, köttbullar, kycklinggratäng, etc.)

    # READY-MADE DISHES - complete dishes, not individual ingredients
    'kycklinggryta',  # ready-made chicken stew
    'bolognese',  # ready-made pasta sauce/dish
    'färsbullar', 'kalvfärsbullar',  # pre-made meatballs
    'snack pot',  # instant meal cups
    # Frozen ready meals from Mathem
    'bourguignon', 'bourgiugnon',  # "Boeuf Bourgiugnon Fryst"
    'chicken thai',  # "Chicken Thai Fryst"
    'kyckling thai',  # "Kyckling Thai 500g Kitchenwiz" — ready meal (862 FP recipes)
    'jordnötssås', 'jordnotssas',  # "Thai Kycklingfilé i Jordnötssås med Ris" — complete dish
    'ljus rosa',  # "Kyckling ljus rosa" — deli cold cut, not raw chicken
    'kycklingragu',  # "Kycklingragu Fryst"
    'carbonara',  # "Pasta Carbonara Fryst" - frozen ready meal
    'tagliatelle kyckling',  # "Tagliatelle Kyckling Fryst" - frozen ready meal, not raw pasta
    'spansk tortilla',  # "Spansk Tortilla med Lök" — Spanish omelette (egg dish), not tortilla wrap
    'con carne',  # "Chili con Carne 560g Felix" — ready meal, not fresh chili (899 FP recipes)
    'beef and bean',  # "Chili Färsk Beef and Bean 450g" — ready meal (711 FP recipes)
    # NOTE: Laoganma "crispy chilli/chilli crispy" removed from PROCESSED_FOODS
    # because recipes use "crispy chili oil" as ingredient. Handled via PNB instead.
    'spicy chilli',  # "Spicy Chilli 450g Dolmio" — pasta sauce, not fresh chili (900 FP recipes)
    'green curry',  # "Kyckling green curry 320g ICA" — ready meal (828 FP recipes)
    'färdiglagad', 'fardiglagad',  # "Kyckling Färdiglagad Skivad BBQ" — pre-cooked, not raw (862 FP recipes)
    'caesar stekt',  # "Kyckling Caesar Stekt och Skivad" — pre-cooked deli (862 FP recipes)
    'kullamust',  # "Kullamust Äpple & hallon 63cl" — soft drink, not fruit (773 FP recipes)
    'drinkmix',  # "Drinkmix Lime 35cl Mixtales" — drink mix, not fresh lime (995 FP recipes)
    'jarritos',  # "Lime 355ml Jarritos" — Mexican soda brand, not fresh lime (995 FP recipes)
    'mixer lime syrup', 'lime syrup',  # "Mixer Lime Syrup 500ml" — cocktail syrup (995 FP recipes)
    'ramlösa', 'ramlosa',  # sparkling water brand ("Ramlösa Grönt Äpple" is NOT äpple)
    # Taco bread products - shells/boats are bread, not recipe ingredients
    'taco tubs', 'taco shells', 'taco boats', 'tacoskal',
    # NOTE: tacokyckling removed — handled via CUISINE_CONTEXT + parent mapping
    'rödvinssky', 'rodvinssky',  # "Kalvfärsbiff i Rödvinssky Fryst"
    'hotpot',  # "Creamy Halloumi Hotpot"
    'pomodoro',  # "Pasta Pomodoro Ricotta Fryst Felix" - frozen ready meal
    # Exemption: tortelloni/tortellini in PROCESSED_FOODS_EXEMPTIONS (fresh filled pasta)
    'piccanti',  # "Penne Rosse Piccanti Fryst"
    'med gräddsås', 'med graddsas',  # "Svenska Köttbullar med Gräddsås Fryst"
    'med pepparsås', 'med pepparsas',  # "Fläskfilé med Pepparsås Fryst" - complete dish

    # FLAVORED DELI COLD CUTS — pålägg with flavor words that cause FP matches
    'kalkon med paprika',  # "Kalkon med Paprika Tunna Skivor" — turkey cold cut, NOT paprika (426 FP recipes)

    # DELI/TAPAS PLATTERS - not individual cooking ingredients
    'tapas',  # "Tapas Italia Chark & Ost" — charcuterie platter, not cheese/meat ingredient
    'majskakor', 'majskaka', 'majskako',  # "Ost Majskakor Friggs" / "Ost Majskako" — cheese-flavored rice cake snack, not cheese

    # DESSERT/CANDY/SNACK PRODUCTS - never recipe ingredients
    'kokos saltad karamell',  # "Kokos Saltad Karamell 340g Alpro" — vegansk dessert
    'soft karamell',  # "Soft Karamell Toffee glutenfri 28g Nick's" — candy bar
    'brownie',  # "Brownie Choklad 285g ICA" etc. — ready-made baked goods (22 products)
    # NOTE: chokladpralin REMOVED — 9 recipes use it. Moved to CARRIER_PRODUCTS instead
    'gräddessert', 'graddessert',  # "Gräddessert Choklad Nötgrädde" — ready-made dessert
    'kokostoppar',  # "Kokostoppar Choklad 200g ICA" — candy
    'miniwafers',  # "Miniwafers med choklad 250g ICA" — snack wafers
    'snack rån', 'snack ran',  # "Snack rån med nötkräm och choklad" — snack bars
    'proteinkasein',  # "Proteinkasein Varm choklad 750g Tyngre" — protein supplement
    'grötmix', 'grotmix',  # "Grötmix Protein Varm Choklad" — protein supplement
    # NOTE: kycklingspett REMOVED — 1 recipe uses it as ingredient. FP handled by PNB soja→kycklingspett

    # SNACKS - not recipe ingredients
    'choco chips',  # "Choco Chips Mini" — chocolate snack, not regular chips
    'cheese ballz', 'ostbågar', 'ostbagar',  # cheese puff snacks
    'minitwists',  # "Minitwists Gruyère" — cheese-flavored snack, not gruyère cheese
    'cheez cruncherz', 'cruncherz',  # cheese snacks
    'pringles',  # "Pringles Paprika" — flavored chips, not paprika
    'corners',  # "Corners Chili Cheese" — snack, not chili
    'ostringar',  # "Ostringar Chili Cheese" — cheese ring snacks, not chili
    's-märke', 's-marke',  # "S-märke Supersur Ananas" — candy, not ananas
    'mellanmål', 'mellanmal',  # snack products
    'nötbar', 'notbar', 'proteinbar', 'energibar',  # snack bars - NOT recipe ingredients
    'fruktbar',  # fruit bars ("Hallon Äpple Fruktbar" — snack, not fresh fruit)
    'havrebar',  # oat bars
    'müslibar', 'muslibar',  # muesli bars
    'havrehjärtan',  # oat heart cookies ("Havrehjärtan Hallon" - snack, not hallon)
    'havregurt',  # oat yogurt ("Baked Äpple Havregurt" — dairy product, not fresh äpple)

    # BEVERAGES - not recipe ingredients
    'energidryck', 'monster energy',  # energy drinks
    'te ', 'lipton', 'twinings',  # tea products (note: "te " with space to avoid matching "tomate")
    'örtte', 'ortte',  # herbal tea
    'green tea',  # English tea name ("Green Tea Lime & Ginger" is NOT lime/ginger)
    'black tea',  # "Peach Mango Black Tea Pyramid" — tea, not fruit
    'iskaffe',  # iced coffee drinks ("Iskaffe Hazelnut" is NOT hasselnöt)
    'tonic', 'tonicvatten',  # tonic water ("Tonicvatten Gurka 20cl" is NOT gurka ingredient)
    'tonic vatten',  # variant spelling
    'fruktdryck',  # fruit drinks ("Fruktdryck Hallon Björnbär" is NOT hallon)
    'lättdryck',  # light drinks ("Lättdryck Citron & lime" is NOT citron)
    'drinkmixer',  # drink mixer ("Drinkmixer Soda Nordic Apple" is NOT äpple)
    'multivitamindryck',  # vitamin drinks
    'vitamin boost',  # vitamin drink brand ("Lemon Lime Vitamin Boost" is NOT lime)
    'sparkling',  # sparkling drinks ("Strawberry Lime Sparkling" is NOT lime)
    'folköl', 'folkol',  # beer ("Porter 3.5% Folköl Glas" is NOT a recipe ingredient)
    'starköl', 'starkol',  # strong beer
    'porter',  # dark beer style — substring of "importerade" causes FP
    'peroni',  # beer brand ("Peroni Nastro Assurro" ≠ pepperonikorv)
    'bryggkaffe',  # brewed coffee (store product, not ingredient)
    'kaffekapslar', 'kaffekapsel',  # coffee capsules
    'hela bönor', 'kaffebönor',  # coffee beans ("Espresso Kaffe Hela Bönor") — NOT matbönor
    'böna glass',  # coffee bean ice cream ("Kaffe Böna Glass") — NOT matböna
    # Note: 'kapslar'/'kapsel' REMOVED from PROCESSED_FOODS — they wrongly blocked
    # products like "Vitlök Kapsel Klass 1", while STOP_WORDS already handles
    # non-ingredient capsule wording such as "kardemummakapslar".
    'proviva',  # Proviva juice brand
    'ayran',  # Turkish yogurt drink - NOT matlagningsyoghurt
    'yoghurtdryck',  # yogurt drinks in general - not cooking yogurt
    'yoghurt dryck',  # space variant ("Jordgubb Banan Laktosfri Yoghurt Dryck")
    'awake',  # juice/energy drink brand ("Awake Hallon Pet" ≠ hallon)
    'daiquiri',  # cocktail mix ("Lime Daiquiri" is NOT lime ingredient)
    'margarita',  # cocktail mix ("Strawberry Margarita" is NOT jordgubb)
    'granatäppel sirap', 'granatappel sirap',  # pomegranate syrup — specialty, not plain cooking syrup
    'mojito',  # cocktail mix ("Mojito" is NOT lime/mynta ingredient)
    'piña colada', 'pina colada',  # cocktail mix

    # NOTE: 'lohilo', 'alvestaglass' REMOVED — glass products need to match glass recipes.
    # Carrier 'glass' handles flavor stripping correctly.

    # FREEZE-DRIED PRODUCTS - specialty preservation, NOT fresh/frozen
    'frystorkad', 'frystorkade', 'frystorkat',  # "Blåbär Frystorkade 50g" is NOT blåbär ingredient
    'frukost!',  # "Frukost!" brand - freeze-dried cereal toppings, not real fruit

    # DIP MIXES - herb keywords should NOT match
    'dippmix',  # "Dippmix Dill & Gräslök" is NOT dill/gräslök ingredient

    # Multi-word spice mixes handled by krydda-joining logic in extract_keywords_from_product
    # (e.g., "Kött & Grill Krydda" → keyword 'grillkrydda')

    'chai latte',  # "Chai Latte Krydda" - not a cooking spice

    # SHOTS/JUICES - "Shot Ingefära Citron" is NOT ingefära spice
    'shot',  # juice shots (ginger, turmeric etc) - not the actual ingredient

    # FROZEN READY MEALS - complete dishes, not raw ingredients
    # 'fylld gnocchi' removed — treated like tortellini/ravioli, carrier logic keeps 'gnocchi'
    'chicken tagliatelle', 'chicken penne', 'chicken pasta',  # frozen pasta meals
    'ugnsrostad',  # "Ugnsrostad Kyckling Fryst" - pre-cooked ready meal
    'kyckling jacob',  # Findus "Kyckling Jacob Fryst" - complete dish
    'kyckling linguine',  # "Kyckling Linguine/zicchini Parmesan" — frozen ready meal, not fresh ingredients
    'köttbullar potatismos', 'kottbullar potatismos',  # "Köttbullar Potatismos Gräddsås" — frozen ready meal
    'gryta',  # "Fläskfilégryta med Cocktailpølser Och Bacon" — ready meal, not raw ingredients
    'paj',  # "Paj Västerbottenost" — frozen pie, not cheese (suffix 'paj' only catches compounds)

    # BREAKFAST/SNACK CEREALS - not recipe ingredients
    # granola: REMOVED from PROCESSED_FOODS — naturell variants match via name-conditional
    'müsli', 'musli',  # muesli products

    # FROZEN APPETIZERS / SNACKS - not fresh ingredients
    'spring rolls', 'spring roll', 'vårrullar', 'vårrulle',  # "spring" in product != "springformen" in recipe
    'minivårrullar', 'minivårrulle',  # compound form: "Minivårrullar Beef Vegetables"

    # CANDY / CHOCOLATE / COOKIE brands - not recipe ingredients
    'ferrari',  # Ferrari Sur candy brand
    'nonstop',  # Non Stop candy brand
    'noblesse',  # Marabou Noblesse chocolate box ("Noblesse Apelsin Crisp" ≠ apelsin)
    'oreo',  # Oreo cookies ("Oreo Original Kakor" ≠ kakor in recipes)
    'godis', 'godispåse',  # candy bags ("Godis Ferrari Rabarber" ≠ rabarber)
    'chokladstycksak',  # individual chocolate bars ("Chokladstycksak Dumle Crunchy Lakrits")
    'chokladask',  # chocolate gift boxes
    'peacemärke', 'peacemarks',  # candy brand ("Peacemärke Jordgubb Lakrits" is NOT jordgubb)
    'skalle',  # skull candy ("Hallon Lakrits Skalle" ≠ hallon)

    # PRE-MADE BAKERY - not recipe ingredients
    'munk', 'munkar',  # pre-made donuts
    'donut', 'donuts', 'doughnut',  # "Donut Jordgubb" — not a jordgubb ingredient
    'muffin', 'muffins',  # pre-made muffins
    'wienerfläta', 'wienerflata',  # pre-made pastry braids
    'croissant', 'croissanter',  # "Choklad Croissant" — baked good, not choklad ingredient
    'cookies', 'cookie',  # "Choklad Cookies" — baked good, not choklad ingredient
    'strössel', 'strossel',  # "Choklad Strössel" — baking decoration, not choklad

    # SNACK PRODUCTS - flavored snacks, not raw ingredients
    'rostad majs',  # "Rostad Majs Chili" — snack, not chili ingredient

    # MARGARINE/SPREADS - NOT real butter
    'bregott',  # Swedish margarine/spread brand (marketed as butter-substitute)
    'flora',  # Flora margarine brand ("Flora Normalsaltat med Smör 70%" is NOT butter)
    'smör raps', 'smör & raps',  # butter-rapeseed blend, not real smör (& variant for original name check)

    # === ADDITIONS FROM WILLYS CATALOG ANALYSIS (8245 products scraped) ===

    # SWEDISH TRADITIONAL READY MEALS - complete dishes, not raw ingredients
    'pytt i panna', 'pytt',  # "Oxpytt" contains nöt but is a ready meal
    'wallenbergare',  # classic Swedish veal dish - ready meal
    'kålpudding', 'kalpudding',  # cabbage pudding with meat - ready meal
    'skomakarlåda', 'skomakarlada',  # cobbler's box - ready meal
    'kroppkakor',  # potato dumplings with pork filling
    'pölsa', 'polsa', 'norrlandspölsa',  # hash from offal/meat
    'pitepalt',  # potato dumplings (Pite style)
    'dumpling', 'dumplings',  # "Dumpling Kyckling & Mild Vitlök Fryst" — ready meal, not vitlök/kyckling ingredient
    'rotmos',  # mashed root vegetables (pre-made side)
    # NOT blocked: pannbiff, schnitzel, cevapcici, kotlettrad, renskav,
    # potatissallad, bearnaise - these are valid ingredients/products

    # INTERNATIONAL READY MEALS
    'burek',  # "Burek Spenat & Ost" - filled pastry, ready meal
    'calzone',  # folded pizza - ready meal
    'asia box',  # "Asia Box Massaman Curry" - complete dish
    'thai coconut curry',  # "Thai Coconut Curry" — complete ready meal, not kokos ingredient

    # FROZEN PROCESSED - contain ingredient keywords
    'pan pizza',  # "Pan Pizza Vesuvio" - frozen pizza variant
    'pizza slice',  # frozen pizza slices
    'fish & chips', 'fish & chip',  # frozen fish & chips
    'tonfiskfilé &', 'tonfiskfile &',  # "Tonfiskfilé & Kikärtor Linser Röd Paprika" - prepared fish salad
    'onion rings',  # frozen appetizer
    'kebabskav', 'kebab skav',  # frozen kebab meat shavings
    'chili cheese nuggets',  # frozen appetizer
    'mozzarella sticks',  # frozen appetizer
    'southern fried chicken',  # breaded frozen chicken

    # READY-TO-EAT CATEGORIES
    'baguettesallad',  # "Kyckling Curry Baguettesallad" - ready meal
    'rice bowl',  # "Korean Rice Bowl" - complete dish
    'pasta bowl',  # "Pasta Bowl Fussili Pesto" - complete dish
    'tramezzini',  # Italian sandwich - ready meal

    # COMPLETE READY MEALS
    'korvstroganoff',  # "Korvstroganoff med Ris" - complete ready meal

    # DESSERT SOUPS (not ingredients)
    'nyponsoppa',  # 6 products - pre-made dessert soup (extra safety, partly covered by soppa carrier)

    # NOTE: tex mex/texmex removed — handled via CUISINE_CONTEXT

    # CANDY / SUPPLEMENTS - not recipe ingredients
    'proteinmousse',  # protein supplement product (not food ingredient)
    'proteinpudding',  # protein supplement product ("Choklad Proteinpudding")
    'chokladcrisp',  # "Choklad med Chokladcrisp Yoghurt" — snack yoghurt, not baking chocolate
    'protein mousse',  # "Mousse Choklad Protein Mousse" (space-separated variant)
    'pingvinstång',  # candy bar brand (Pingvin/Cloetta)
    'turkiskpeppar',  # Fazer "Turkisk Peppar" candy (joined via _SPACE_NORMALIZATIONS)

    # SANDWICH PRODUCTS - filling words are contents, not raw ingredients
    # "Wasa Sandwich Pesto" is NOT pesto
    'sandwich',

    # CONVENIENCE CREAM PRODUCTS - cannot substitute raw cream in recipes
    'spraygrädde',  # aerosol whipped cream - NOT vispgrädde

    # COFFEE ROAST TERMS / BRANDS - only appear on coffee products
    'mellanmörk',  # medium-dark coffee roast ("Gran Dia Mellanmörk Hela Bönor" = coffee beans)
    'ljusrost',    # light roast
    'mörkrost',    # dark roast
    'mellanrost',  # medium roast ("Mellanrost Hela Bönor" = coffee, NOT food beans)
    'medium roast',  # English variant ("Medium Roast Hela Bönor")
    'bella crema',  # Melitta coffee brand ("Bella Crema La Crema Hela Bönor" = coffee beans)
    'crema e aroma',  # Lavazza coffee brand ("Crema E Aroma Hela Bönor" = coffee beans)

    # CRISPY-BAKED FISH - ready-to-eat, not raw ingredients
    # "Kummel Sprödbakad Stilla Havet" is a prepared product, not raw kummel for cooking
    'sprödbakad', 'sprödbakat', 'sprödbakade',

    # Ready meals with protein/vegetable names (kyckling, grönsaker = filling, not ingredient)
    # NOTE: 'äggnudlar' removed — now handled via carrier logic (strips flavor, keeps äggnudlar keyword)
    'stekt ris',  # "Thai Stekt Ris Kyckling & Grönsaker"

    # Deli salads — ready-made, not raw salad leaves
    'skinka sallad',  # "Ost Och Skinka Sallad" — deli ham salad
    'räksallad',  # "Räksallad Färska Räkor" — prepared shrimp salad
    'picklad sallad',  # "Picklad Sallad" — pickled, not fresh

    # NOTE: Philadelphia stripped names ("Gräslök Light 11%") handled by
    # _BRAND_NAME_COMPLETIONS in extract_keywords_from_product()

    # Snack products with dairy/staple names
    'linskaka',  # "Gräddfil & Lök Linskaka" — lentil snack, not gräddfil

    # Dried fruit snacks with spice names (mango/chili → not a chili product)
    'mango chili torkad',  # "Mango Chili Torkad" — dried fruit snack

    # Canned fish compound product names — 'makrillbitar'/'makrillfilé' moved to
    # CARRIER_PRODUCTS + OFFER_EXTRA_KEYWORDS so they match recipe keyword 'makrill'
    'pinklaxfilé', 'pinklaxfile',  # "Pinklaxfilé Tomatsås" — canned salmon ready meal

    # Sauce/condiment/oil products that match fresh ingredient keywords
    'grilloil',        # "Grilloil Chili" — always a spray/oil product
    # NOTE: 'sweet chili' removed — blocked "Färskost Sweet chili Philadelphia". Sauces caught by 'sweet chilisås'/'sweet chili sås'.
    'crispy chili',    # "Crispy Chili In Oil" — condiment (Lao Gan Ma style)
    'chili mayo',      # "Chili Mayo Hot" — always a mayo/condiment
    'chilimajo',       # "Chilimajo" — compound form
    'chili crunch',    # "Chilli Chili Crunch" — condiment
    'hot chili ketchup',  # "Hot Chili Ketchup" — ketchup
    'habanero mango',  # "Habanero Mango Chilisås" — chili sauce
    'mango habanero',  # "Mango Habanero Hot Mayo" — mayo/condiment
    'salsa habanero',  # "Salsa Habanero Hot" — salsa
    'salsa hot',       # "Salsa Hot Habanero" — salsa

    # Müsli/cereal products with fruit flavoring (not actual fruits)
    'crunchy citron',   # "Crunchy Citron Jordgubb" müsli — not actual citron/jordgubb
    'crunchy kokos',    # "Crunchy Kokos" müsli — not actual coconut
    'crunchy russin',   # "Crunchy Russin" müsli — not actual raisins
    'crunchy fries',    # "Crunchy Fries" — frozen processed fries, not raw potato
})

PROCESSED_FOOD_SUFFIXES: FrozenSet[str] = frozenset({
    'soppa',  # ready-made soups: purjolöksoppa, tomatsoppa, ärtsoppa
    'paj',  # ready-made pies: broccolipaj, kycklingpaj, västerbottenpaj
    'pastej',  # pâté/paste: örtpastej, svamppastej — not raw ingredients
    'gryta',  # ready-meal stews: fläskfilégryta, kycklinggryta
})

PROCESSED_FOODS_EXEMPTIONS: FrozenSet[str] = frozenset({
    'dumpling',
    'dumplings',
    'dulce de leche',  # exact cooking ingredient; keep the phrase alive until space-normalized
    'chokladägg',  # explicit candy ingredient in some dessert recipes; keep exact compound alive
    'vaniljsås', 'vaniljsas',  # explicit dessert sauce ingredient; should survive processed-food filtering
    'vaniljvisp',  # Flora brand blocker should not hide the exact whipped vanilla topping product
    'kryddmix',
    'cooking spice sauce',  # "Cooking Spice Sauce Tikka Masala" is a real cooking sauce ingredient
    'tortelloni',  # "Pomodoro Mozzarella Tortelloni Garant" is fresh filled pasta
    'tortellini',  # same — fresh tortellini with pomodoro filling is a valid ingredient
    'leverpastej',  # liver pâté IS a recipe ingredient — suffix 'pastej' triggers block
    'bryggkaffe',   # "Bryggkaffe 500g" is a product ingredient — 'bryggkaffe' entry in PROCESSED_FOODS
                    # was added to stop generic "kaffe" matches, but 'kaffe' is already blocked from
                    # recipe extraction (see IMPORTANT_SHORT_KEYWORDS note). Exempt so "bryggkaffe"
                    # keyword is extracted and can match recipes asking for "brygg- och kokkaffe".
    'havregurt',    # "Havregurt 1kg" is a plant-based yoghurt ingredient — in PROCESSED_FOODS to prevent
                    # flavored variants ("Baked Äpple Havregurt") from matching apple ingredients.
                    # Exempt so "havregurt" keyword is extracted and OFFER_EXTRA_KEYWORDS can add 'yoghurt'.
    'proteinpudding',  # explicit protein pudding lines should match real protein pudding products via the
                       # compound keyword itself, not degrade through generic "pudding".
    'nyponsoppa',   # exact dessert soup ingredient; keep the compound keyword so real nyponsoppa products match
    'tomatsoppa',   # exact prepared soup ingredient; should match real tomato soup products without
                    # reopening generic ready-made soup products as ingredient families
    # NOTE: 'glass noodles' exemption removed — it also exempted "Spicy Japchae ... Glass Noodle"
    # Instead, "Glass Noodles" is handled by pre-PROCESSED_FOODS space norm (see below)
})

FLAVOR_WORDS: FrozenSet[str] = frozenset({
    # Vegetables as flavors
    'paprika', 'lök', 'lok', 'tomat', 'körsbärstomat', 'korsbarstomat',
    'vitlök', 'vitlok', 'vitlöks', 'vitloks',
    'schalottenlök', 'schalottenlok',  # "Vinäger Schalottenlök" — shallot is flavor base
    'jalapeño', 'jalapeno', 'chili',
    'rödlök', 'rodlok', 'gräddfil', 'graddfil',  # chips flavors
    'spenat', 'ricotta', 'pomodoro',  # pasta fillings
    'gurka',  # "Smoothie Gurka Citron" - cucumber as smoothie flavor, not fresh
    'kantarell', 'karl-johan', 'svamp',  # fond flavors
    'potatis', 'purjolök', 'purjolok', 'purjo',  # soup flavors
    'morot', 'morötter',  # soup/juice flavors

    # Herbs/spices as flavors
    'dill', 'basilika', 'oregano', 'timjan', 'citrontimjan', 'persilja', 'persilj',
    'dragon',  # "Dragon Citron Lätt Crème Fraiche 11%" — tarragon as flavor in dairy carrier
    'koriander',  # "Dressing Koriander & Lime" - koriander is the flavor
    'curry', 'sriracha', 'wasabi',
    'örter', 'orter',  # "Salsiccia vitlök och örter" - herbs as flavoring
    'chipotle', 'barbecue', 'bbq', 'bourbon',  # ready meal/sauce flavors
    'cayenne',  # "Chorizo Cayenne & paprika" - spice as flavor in sausage
    'cayennepeppar',  # "Chorizo Paprika Chili Cayennepeppar" - compound form
    'svartpeppar',  # "Ketchup Svartpeppar", "Kabanoss Svartpeppar" — pepper as flavor variant
    'vitpeppar',  # "Vitpeppar" as spice flavor in carrier products
    'kummin',  # "Bratwurst Kummin & vitlök" - spice as flavor in sausage
    'spiskummin',  # "Kryddost Spiskummin & Nejlika" - spice as cheese flavor
    'nejlika',  # "Kryddost Spiskummin & Nejlika" - spice as cheese flavor
    'ingefära', 'ingefara',  # juice flavor
    'citrongräs', 'citrongras',  # "Citrongräs Fänkål&Ingefära Te" — tea flavor, not fresh lemongrass

    # Egg as pasta type (in pappardelle, tagliatelle, etc)
    'ägg',  # "Pappardelle Ägg Pasta" / "Tagliatelle Ägg" - ägg is pasta type, not eggs

    # Dairy as flavors (in pastasås, gratäng, glass, choklad, etc)
    'mjölk', 'mjolk',  # "Glass mjölk" = milk ice cream variant, "Choklad Mjölk" = milk chocolate type
                        # Standalone "Mjölk 3% 1l" unaffected — no carrier in name
    'creme', 'fraiche',  # "Pastasås Tomat Creme Fraiche Kelda" - creme fraiche is a flavor
                         # Standalone "Creme Fraiche 34%" unaffected — creme fraiche is ALSO a carrier
    # Cheese as flavors (in creme fraiche, pizza, pasta, röra, grillkorv, etc)
    'ost', 'ostar',  # "Mild Ost Pastasås" - ost is flavor in sauce; "Fyra Ostar" = cheese blend
           # Standalone cheese ("Ost Mager Riven") unaffected — no carrier in name
    'parmesan', 'parmigiano', 'cheddar', 'gorgonzola', 'brie',
    'vodka',  # "Pastasås med Vodka" — vodka is the sauce flavor, not an ingredient
    'feta',  # "Yoghurt & Feta Röra" - feta is flavor in spread/dip
    'mozzarella', 'mozarella',  # pizza topping

    # Proteins as flavors (in ready meals, soups, sauces, paj, gratäng)
    'kyckling', 'fläsk', 'flask', 'nöt', 'not',  # "Soppa Kyckling" is NOT kyckling
    'biff',  # "Snabbnudlar Biff", "Demae Ramen Biff Nudlar" — filling/flavor, not ingredient
    'beef',  # English: "Beef Flavour Rice Noodles" — meat flavor, not ingredient
    'veggie',  # English: "Nudlar Yakisoba Veggie" — variant descriptor, not ingredient
    'grönsaker', 'gronsaker', 'grönsak', 'gronsak',  # "Äggnudlar Kyckling Grönsaker" — filling, not ingredient
    'kimchi',  # "Nudlar Udon Kimchi" — condiment-flavor on noodle products, not ingredient
    'lax', 'torsk', 'fisk', 'räk', 'rak', 'räkor', 'räka', 'skaldjur',  # "Fiskgratäng", "Mjukost Räkor"
    'skinka',  # "Ost & Skinkpaj" - skinka is filling
    'bacon',  # "Bacon Broccoli Paj" - bacon is filling
    'ris',  # "Färdigmat med Ris" - ris is part of the meal
    'broccoli',  # "Kycklingpaj med Broccoli" - broccoli is filling
    'pasta',  # "Pasta Tortellini" - generic word in carrier products (standalone "Pasta 500g" unaffected)
    'chicken',  # English: "Chicken Alfredo Dafgårds" - chicken is the dish content
    'nuggets',  # "Fish Nuggets Findus" - nuggets is the product form

    # Dish names as flavors (in ready meal carriers like Dafgårds, Felix, Findus)
    'lasagne',  # "Karins lasagne Dafgårds" ≠ färska lasagneplattor
    # NOTE: 'lasagneplattor' REMOVED — it's a product type, not a flavor. Was causing
    # "Pasta Lasagneplattor Färska ICA" to suppress 'lasagneplattor' and keep only 'pasta'.
    'carbonara',  # "Spagetti carbonara Dafgårds" ≠ 400g spagetti
    'alfredo',  # "Chicken Alfredo Dafgårds" - dish name
    # 'spagetti', 'spaghetti' — REMOVED: pasta type names are product variants, not flavors.
    # Ready meals like "Spaghetti Carbonara Fryst" are handled by PROCESSED_FOODS (carbonara/bolognese).
    'popcorn',  # "Glass Popcorn brynt smör" ≠ nypoppade popcorn
    'smör', 'smor',  # "Matfett Smör & Raps" - smör is a descriptor in margarine products
                     # (standalone "Smör 500g" is NOT a carrier, so unaffected)

    # Sauce types as flavors (in crème fraiche, färskost, etc)
    'bearnaise', 'béarnaise',  # "Creme Fraiche Bearnaise" — sauce type, not ingredient
    'hollandaise',  # sauce type variant

    # Alcohol as flavors (in fond, sauces, crème fraiche)
    'cognac',  # "Creme Fraiche Kantarell & Cognac" — alcohol flavor, not ingredient
    'rödvin', 'rodvin', 'vitvin',  # "Oxfond med Rödvin" is NOT rödvin
    'matlagningsvin',  # after space norm: rödvin→matlagningsvin, still a carrier flavor

    # Vinegar as flavor (in soltorkade tomater, chips)
    'balsamvinäger', 'balsamvinager',  # "Soltork Tomat i Balsamvinäger" — flavor, not ingredient
    'balsamico',  # Italian balsamic descriptor

    # Salt flavors (in chips, knäcke)
    'havssalt', 'salt',

    # Nuts as flavors (in chocolate, granola, etc)
    'mandel', 'mandlar',  # singular and plural
    'hasselnöt', 'hasselnot', 'hasselnötter', 'hazelnut',
    'hasseln',   # shortened form used in product names ("Mandel Hasseln Krispig Müsli")
    'hasselnö',  # abbreviated without t, Swedish chars intact (product names sometimes truncate)
    'hasselno',  # same abbreviation after fix_swedish_chars ASCII conversion
    'cashew', 'cashewnöt', 'cashewnötter',  # in granola
    'jordnöt', 'jordnot', 'jordnötter', 'jordnotter',  # "Ginger Chews Jordnöt" is NOT jordnötter
    'pistage', 'pistagenöt', 'pistagenötter',  # "Chokladkaka Pistage"
    'valnöt', 'valnötter',  # "Granola Valnöt"
    'nötter', 'notter',

    # Fruits/berries as flavors (in smoothies, juices, chocolate, snacks, water, yogurt, bars)
    # COMPREHENSIVE LIST - any fruit/berry as flavor in a carrier product should NOT match recipes
    # Berries
    'hallon', 'jordgub', 'jordgubb', 'jordgubbar', 'jordgubbe',
    'blåbär', 'blabar', 'lingon',
    'vinbär', 'vinbar', 'svartvinbär',
    'björnbär', 'bjornbar',
    'smultron',
    'tranbär', 'tranbar', 'cranberry',
    'krusbär', 'krusbar',
    'hjortron',
    'nypon',
    'skogsbär', 'skogsbar',
    'sommarbär', 'sommarbar',
    'açai', 'acai',
    # Stone fruits
    'persika', 'aprikos', 'aprikoser',
    'plommon',  # note: also tomato variety but fine as flavor word
    'körsbär', 'korsbar', 'cherry',
    'nektarin',
    # Citrus
    'citron', 'lime', 'apelsin', 'orange',
    'grapefrukt', 'clementin', 'mandarin', 'blodapelsin',
    # Tropical fruits
    'mango', 'ananas', 'pineapple', 'papaya', 'passionsfrukt', 'passion',
    'kokos', 'coconut', 'kiwi', 'guava', 'lychee', 'litchi', 'avokado', 'drakfrukt',
    'tropisk', 'tropiska',
    # Common fruits
    'äpple', 'apple', 'päron', 'paron',
    'banan',
    'fikon',
    'druva', 'druvor',
    'melon', 'vattenmelon', 'honungsmelon',
    'rabarber',
    'granatäpple', 'granatapple',

    # Sweet/floral flavors (in yogurt, müsli, drinks, etc)
    'vanilj', 'choklad',  # "Yoghurt Vanilj", "Müsli Choklad" - sweet flavors
    'fläder', 'flader', 'fläderblom', 'fladerblom',  # "Saft Fläder Citron", "Juice Fläderblom"

    # Spices as flavors (in juices, ready meals, bakery)
    'gurkmeja', 'kurkuma',  # turmeric in juice
    'saffran',  # "Mazariner Saffran" - saffran is flavor in bakery
    'kakao',  # "Granola Kakao" - kakao is the flavor

    # Deli meat as flavor (in filled pasta)
    'prosciutto',  # "Tortelloni Prosciutto" - prosciutto is the filling
    'pancetta',  # "Tortelloni Pancetta" - pancetta is the filling

    # Oils as packaging medium (in canned fish/meat)
    'rapsolja', 'solrosolja', 'olivolja',  # "Sardiner i Rapsolja" - oil is packaging, not product

    # Grains/seeds as mix-ins (in gröt, müsli, bröd, etc)
    'quinoa',  # "Havre & Quinoa Gröt" - quinoa is a mix-in, not the product
    'havre',   # "Havre & Quinoa Gröt" - havre is a descriptor in gröt/müsli
    'solrosfrö', 'solrosfro',  # "Bröd Surdeg Lin Och Solrosfrö" - seed topping, not ingredient
    'linfrö', 'linfro',  # "Fullkornsgott Bröd Linfrö" - seed topping in bread
    'vallmo',  # "Granola Blåbär Vallmo" — poppy seed as flavor, not raw vallmofrön
    'rabarbe',  # truncated 'rabarber' in product names ("Blåbär Rabarbe Granola Glutenfri")

    # Vegetables/herbs as flavor/descriptor in processed products
    'kål',  # "Kål Bönbiff" - kål describes the biff, not standalone cabbage
    'ramslök', 'ramslok',  # "Ramslök Vitlök Gräslök Färskost" — flavor in cream cheese/sauce
    'jordnötssmör', 'jordnotssmor',  # "Jordnötssmör Kakao Granola" — flavor in granola
    'nötsmör', 'notsmor',  # nut butter as flavor in baked products
    'pistasch',  # "Nötsmör Pistasch&cashew" — nut type as flavor

    # Sauces as flavors (in ready meals)
    'tomatsås', 'tomatsas',  # "Färdigmat i Tomatsås" - sauce is part of meal

    # Bread types as flavors (in pizza kits etc)
    'surdeg',  # "Pizzakit Surdeg" - surdeg is the base type

    # Cheese variety names as flavors (in cider, cream cheese, etc)
    'herrgård', 'herrgard',  # "Äppelcider Herrgård" is cider brand, not Herrgård cheese

    # Drink flavors (in protein shakes, etc)
    'karamell', 'karamel', 'kaffe', 'coffee',  # "Proteinmilkshake Kaffe Karamell" / "Salt Karamel Glass"

    # Butter/fat as flavor (in popcorn etc)
    'smör', 'smor',  # "Micropopcorn Smör" - smör is the flavor

    # Banana as flavor (in smoothies, yogurt, granola etc)
    'banan',  # "Smoothie Banan" - banan is the flavor

    # Condiments as flavors (in mayo, dressing, etc)
    'soja', 'soy',  # "Mayo Sesame & soy" - soja is flavor in mayo, not standalone soy sauce
    'sesam', 'sesame',  # "Mayo Sesame & soy" - sesame is flavor, not ingredient

    # Sweeteners as flavors (in nut mixes, cereals, etc)
    'honung',  # "Nötmix Honung & Salt" - honung is the flavor

    # Toppings as flavors (in bakery products)
    'strössel', 'strossel',  # "Munk Rosa Strössel" - strössel is the topping

    # === BATCH 2: MORE FLAVOR_WORDS FROM WILLYS CATALOG ===

    # Spices/herbs as flavors (in färskost, korv, granola, knäcke)
    'kanel',  # cinnamon (14x: "Äpple Kanel Yoghurt", "Äpple Kanel Granola")
    'kardemumma', 'kardemum',  # cardamom — both forms (3x: "Mullbär Kardemumma Granola", "Kanel Kardemum Granola")
    'gräslök', 'graslok',  # chives (9x: "Gräslök Färskost", "Dill/gräslök Majskakor")
    'rucola', 'ruccola',  # arugula as flavor in pesto ("Pesto Basilika Ruccola Barilla")
    'fänkål', 'fankal',  # fennel (4x: "Salsiccia Fänkål")
    'pepparrot',  # horseradish (5x: "Pepparrot Färskost")
    'tryffel',  # truffle (6x: "Tryffelkorv", "Tryffel Färskost")
    'mint',  # mint flavor (4x: "Intense Mint Chokladkaka")
    'mynta',  # Swedish mint (3x: "Äpple Ananas Lime Ingefära Mynta Juice")
    'pesto',  # pesto (12x: "Rigatoni Kyckling Pesto", "Mozzarella Pesto Pizza")

    # Dried fruits/nuts as flavors (in müsli, granola, hummus)
    'russin',  # raisins (8x: "Russin Aprikos Dadlar Müsli")
    'dadlar',  # dates (5x: "Hasselnöt Dadlar Granola")
    'pinjenötter', 'pinjenotter',  # pine nuts as flavor ("Hummus Pinjenötter")

    # Sweets as flavors (in glass, choklad, carrier products)
    'nougat',  # nougat (7x: "Nougat Gräddglass", "Nougat Swirl Glass")
    'saltlakrits',  # salty licorice (5x: "Saltlakrits Gräddglass", "Saltlakrits Mjölkchoklad")
    'lakrits',  # licorice flavor (in choklad, glass)
    'choklad',  # chocolate as flavor in ice cream ("Choklad Krossad Laktosfri Glass")
    'mjölkchoklad',  # milk chocolate as flavor variant ("Päron Mjölkchoklad Glass")
    'chokladsmak',  # chocolate flavor variant ("Drömmar Chokladsmak" — stripped by drömmar carrier)

    # Note: fruit flavors are in FLAVOR_WORDS above (not in STOP_WORDS)

    # Product line names used as flavors in yoghurt/dessert products
    'samoa',  # "Mini Samoa Yoghurt", "Samoa Original Yoghurt" — coconut/chocolate flavor
    'hairy',  # "Hairy Berry Yoghurt 2%" — brand flavor name (berry mix)
    'strawbe',  # truncated "strawberry" on yoghurt products
    'raspbe',  # truncated "raspberry" on yoghurt products
})

SKIP_IF_FLAVORED: FrozenSet[str] = frozenset({
    'yoghurt', 'yogurt', 'yo-ghurt',  # ICA spells it "YO-ghurt"
    'fil', 'filmjölk', 'filmmjölk', 'filmjolk',  # Willys strips ö
    'kvarg',  # only naturell + vanilj are used in cooking (vanilj via COOKING_FLAVORS)
    'keso',
    'majonnäs', 'majonnas', 'majonäs', 'majonas',  # flavored mayo = dressing, not plain mayo
    'drickyoghurt',  # 18 products - ALL are flavored (jordgubb, skogsbär, mango, etc.)
    'skyr',  # flavored skyr (like yoghurt) - naturell skyr should still match
    'kefir',  # flavored kefir - naturell kefir should still match
    # NOTE: crème fraiche NOT here — uses BIDIRECTIONAL_SPECIALTY_QUALIFIERS instead,
    # so flavored products (paprika chili, etc.) match recipes asking for that flavor,
    # while plain products serve as fallback for any crème fraiche recipe.
    'fruktyoghurt',  # "Fruktyoghurt Citron" - compound word, "yoghurt" alone doesn't match
    'hälsofil',  # "Hälsofil Hallon Passion Vanilj" - compound word, "fil" alone doesn't match
    # Yogurt brands (product name may not contain "yoghurt")
    'yoggi', 'yoplait', 'activia', 'danone',
})

COOKING_FLAVORS: FrozenSet[str] = frozenset({
    'vanilj',  # vanilj yoghurt used in smoothies, baking
})

IMPLICIT_KEYWORDS: Dict[str, str] = {
    # Mild/neutral cheeses that can substitute for generic "ost" in recipes
    # Only cheeses with bland, interchangeable flavor belong here
    'herrgård': 'ost',
    'herrgard': 'ost',
    'präst': 'ost',
    'prast': 'ost',
    'grevé': 'ost',
    'greve': 'ost',
    'hushållsost': 'ost',
    'hushallsost': 'ost',
    'svecia': 'ost',
    'edamer': 'ost',
    'gouda': 'ost',
    'gräddis': 'ost',
    'gräddost': 'ost',
    # NOT included: cheddar, emmentaler, mozzarella, parmesan, manchego,
    # gruyère, halloumi, feta, ricotta, mascarpone, burrata, brie, camembert
    # - these have distinct flavor/texture and should only match their own name

    # English product names → Swedish recipe keywords
    # NOTE: "coconut milk/cream/oil/flakes" handled via _SPACE_NORMALIZATIONS
    # Only map standalone "coconut" (rare, e.g. "Coconut 200g")
    'coconut': 'kokos',

    # Honey variants → generic honung
    'blomsterhonung': 'honung',  # "Blomsterhonung" = regular honey
    'akaciahonung': 'honung',
    'skogshonung': 'honung',

    # Ribs (English) → Swedish revbensspjäll
    'ribs': 'revbensspjäll',  # "Baby back ribs" → matches revbensspjäll recipes

    # Soy sauce (English product name) → Swedish keyword
    'soy': 'soja',  # "Japanese Soy Sauce" → soja (matches sojasås recipes)

    # Rice type as standalone word → generic ris
    'basmati': 'ris',  # "Basmati Quick N' Easy" → ris (basmatiris handled by INGREDIENT_PARENTS)

    # Whole grain rice — compound word where "fullkorns" is a stop word,
    # so "Fullkornsris" only extracts "ris". This re-adds the compound keyword
    # so fullkornsris products match fullkornsris recipes (FPB blocks generic ris).
    'fullkornsris': 'fullkornsris',

    # Cured meats → Swedish keywords. Specialty qualifiers keep air-dried ham
    # origins out of plain "skinka" recipes unless the recipe asks for that form.
    'jamon': 'skinka',
    'coppadiparma': 'coppa',  # space-normalized "Coppa Di Parma" → coppa (matches recipe ingredient)

    # Spelling normalization (product vs recipe spelling differ)
    'sallatsmix': 'salladsmix',  # ICA spells with t, recipes with d

    # Fresh chili peppers → also match recipe keyword "chili"
    # "Chilipeppar Röd" → keyword 'chilipeppar' + implicit 'chili' → matches "1 röd chili"
    # Note: jalapeño is a specific variety (STOP_WORD) - generic chili ≠ jalapeño
    'chilipeppar': 'chili',

    # Brand-name products → generic ingredient
    'norrloumi': 'halloumi',  # Norrmejerier brand = halloumi
    'grilloumi': 'halloumi',  # Arla brand = halloumi
    'eldost': 'halloumi',    # Fontana brand = halloumi
    'grillost': 'halloumi',  # generic Swedish name = halloumi
    'grillost burgare': 'halloumiburgare',  # also generates halloumiburgare keyword
    'burger slices cheddar': 'hamburgerost',
    'burgers slices cheddar': 'hamburgerost',
    'cheddar burgar': 'hamburgerost',

    # Blue cheese / cream cheese types
    'ädel': 'ädelost',         # "Ädel Grädd 36%" = ädelost
    'ädel grädd': 'gräddost',  # "Ädel Grädd" = also gräddost style
    'blåmögelost': 'ädelost',
    'blamogelost': 'adelost',
    'grönmögelost': 'ädelost',
    'gronmogelost': 'adelost',

    # Pizza kits (sourdough base + toppings sold as kit)
    'surdeg pizza': 'pizzakit',  # "Surdeg Pizza Xxl" = pizza kit, not sourdough
}

IMPORTANT_SHORT_KEYWORDS: FrozenSet[str] = frozenset({
    'lax', 'torsk', 'sej', 'sill', 'räkor', 'räka',  # fish
    'nöt', 'kött', 'fläsk', 'lamm', 'kalv', 'vilt', 'bacon', 'karré', 'korv', 'skinka', 'kalkon', 'salami',  # meat
    'beef', 'pork',  # English meat words (common in Swedish store names: "Pulled Beef", "Pulled Pork")
    'ägg', 'ost', 'brie', 'feta', 'ädel', 'adel', 'mjölk', 'kvarg', 'smör', 'grädde',  # dairy / blue cheese family
    'mandel',  # almond singular (6 chars, below 7-char strict min) — "hackad mandel", "rostad mandel"
    'nötter', 'notter',  # generic nut lines ("hackade nötter")
    'ris', 'bröd', 'mjöl', 'pasta', 'pesto', 'kex',  # grains & staples
    'penne', 'ziti',  # short pasta types (< 6 chars, needed for parent mapping)
    'lök', 'kål', 'bön', 'majs', 'dill', 'mynta', 'timjan', 'svamp', 'fänkål', 'murkla', 'vitkål', 'squash',  # vegetables & herbs
    'spenat',  # spinach (6 chars) — "Babyspenat", "Spenat Fryst"
    'bulgur',  # grain (6 chars) — "Bulgur Grov", "Bulgur Fin"
    'kapris',  # capers (6 chars) — "Kapris Burk"
    'ananas',  # pineapple (6 chars) — "Ananas Färsk", "Ananas Ring"
    'quinoa',  # grain (6 chars) — "Quinoa", "Quinoa Röd"
    'jäst',  # yeast (4 chars) — "Jäst Original Färsk"
    'bjäst',  # nutritional yeast (5 chars) — maps to näringsjäst
    # Japanese/Korean cooking ingredients
    'nori',  # seaweed sheets (4 chars) — "Sushi Nori Roasted Seeweed"
    'mirin',  # rice wine (5 chars) — "Mirin"
    'wasabi',  # wasabi (6 chars) — "Wasabi Paste"
    'comte', 'comté',  # Comté cheese — needed for "Comte" product names
    'padano',  # Grana Padano (6 chars) — product side already extracts it; ingredient side needs ISK to pass strict min
    'gari',  # pickled sushi ginger
    'vitlök', 'rödlök', 'gullök',  # onion types (6 chars, below threshold)
    'vinbär', 'vinbar',  # currants (6 chars) — "Svarta Vinbär Ekologiska Frysta"
    'rödkål',  # red cabbage (6 chars) — vitkål already in ISK
    'oliver',  # olives (6 chars) — "Gröna Oliver", "Oliver Vitlök"
    'must',  # apple/berry must drink (4 chars) — carrier, strips fruit flavors
    'kaka',  # cookie/cake singular (4 chars) — carrier, strips fruit flavors
    'lökar', 'lokar',  # plural of lök (5 chars) — maps to 'lök' via INGREDIENT_PARENTS
    'citron', 'chili',  # common ingredients (5-6 chars)
    'ancho', 'naga',  # specific chili varieties (4-5 chars)
    'sumak',  # Middle Eastern spice (5 chars)
    'bagel', 'bagels',  # bread type (5-6 chars) — "Bagels Classic 300g Liba Bröd"
    'tomat', 'gurka', 'pumpa', 'rova', 'beta', 'purjo', 'morot',  # vegetables (≤5 chars)
    'böna', 'bönor', 'ärta', 'ärter', 'ärtor',  # legumes (≤5 chars)
    'pinsa',  # Italian flatbread (Zeta brand, used in recipes)
    'tipo00',  # Italian flour grade (from space norm "tipo 00" → "tipo00")
    'mango', 'lime', 'kiwi', 'päron', 'paron', 'lingon',  # fruits
    'banan', 'druva', 'fikon', 'melon', 'äpple',  # fruits (5 chars)
    'grape', 'guava', 'dadel', 'dadlar', 'goji', 'acai',  # exotic fruits (≤6 chars)
    'kanel', 'senap', 'ajvar', 'soja', 'sambal', 'honung', 'salsa',  # spices/condiments
    'kummin',  # cumin spice (6 chars)
    'salvia',  # sage herb (6 chars) — "Salvia Kruka" etc.
    'russin',  # raisins (6 chars)
    'linser',  # lentils (6 chars)
    'linfrö', 'linfro',  # flax seeds (6 chars) — "Linfrö Helt", "Linfrö Krossat"
    # NOTE: 'kaffe' intentionally NOT here — recipes say "1 dl starkt kaffe" meaning
    # brewed coffee (make it yourself), not a product to buy. Same as vatten/salt.
    'råris',  # brown rice (5 chars)
    'oxfond',  # beef stock (6 chars)
    'coppa',  # cured meat ("Coppa Di Parma")
    'nduja',  # spicy spreadable salami (5 chars)
    'glass',  # ice cream (5 chars) — recipe ingredient in desserts
    'majo', 'mayo',  # mayonnaise (colloquial/English)
    'vodka',  # pastasås flavor — "Pastasås med Vodka" (5 chars)
    'ostar',  # pastasås flavor — "Pastasås Fyra Ostar" (5 chars, plural of ost)
    # NOTE: 'sylt' removed — too generic as solo keyword. "Hallon Sylt" matched ALL
    # 183 sylt recipes. Compound "hallonsylt"/"lingonsylt" (10 chars) still pass min_length.
    'panko',  # Japanese breadcrumbs
    'naan',  # Indian bread ("Naan Bread Original") — 23 recipes use naan/naanbröd
    'gyros', 'kebab', 'ribs',  # prepared meat dishes
    'fylld', 'fyllda',  # "Fylld Gnocchi" → compound keyword (see _COMPOUND_WORDS_SET)
    'oumph',  # vegetarian pulled product ("Pulled Oumph")
    'fries',  # english name for pommes (mapped to 'pommes' via KEYWORD_SYNONYMS)
    'spätta', # flatfish (after fix_swedish_chars from "spatta")
    # Spice mix type words (≤5 chars, needed for kryddmix matching)
    # Note: 'curry' removed - caused regression (extracted from ready meals like "Green Cube Curry")
    # Note: 'thai' already in STOP_WORDS so adding it here has no effect
    'tikka', 'taco', 'cajun', 'garam', 'raita',
    'kakao',  # cocoa powder (5 chars)
    'hallon',  # raspberry (6 chars)
    'maräng', 'marang',  # meringue (6 chars)
    'oxfilé', 'oxfile',  # beef tenderloin (6 chars)
    'äggula', 'aggula',  # egg yolk (6 chars) — maps to 'ägg' via INGREDIENT_PARENTS
    'gurkor',  # cucumbers plural (6 chars)
    'hummus',  # chickpea spread (6 chars)
    'muskot',  # nutmeg (6 chars)
    'kanin',  # rabbit (5 chars)
    'hummer',  # lobster (6 chars)
    'humrar',  # lobster plural (6 chars) — maps to 'hummer' via KEYWORD_SYNONYMS
    'krabba',  # crab (6 chars)
    'yuzu',  # Japanese citrus (4 chars)
    'kimchi',  # Korean fermented cabbage (6 chars)
    'kålrot',  # swede/turnip (6 chars)
    'kalrot',  # swede without diacritics (6 chars)
    'curry',  # curry spice (5 chars)
    'rädisa',  # radish (6 chars)
    'radisa',  # radish without diacritics (6 chars)
    'risoni',  # orzo pasta (6 chars)
    'sallad',  # lettuce/salad (6 chars)
    'fuet',  # specialty salami type (4 chars) — needs extraction for substitution rule
    'chips', 'nacho', 'nachos',  # cooking chips (tortillachips, nachochips, plain chips)
    'beef',  # English meat word → maps to 'nötkött' via KEYWORD_SYNONYMS
    # Meat/protein
    'biff',  # beef ("Biff med Kappa")
    'färs',  # minced meat ("Färs 12%")
    'anka',  # duck ("Anka Hel Fryst")
    'quorn',  # meat substitute
    'tofu',  # vegan protein
    # Dairy/fermented
    'keso',  # cottage cheese
    'kata',  # Castello Kata cheese
    'fil',  # soured milk ("Fil 3%")
    'a-fil',  # fermented milk
    'skyr',  # Icelandic yogurt
    'kefir',  # fermented dairy
    'aioli',  # garlic condiment
    'fond',  # stock/broth ("Fond Svamp Vegan") — carrier but needs to survive length filter
    # Baking/pantry
    'sirap',  # syrup ("Ljus Sirap")
    'farin',  # brown sugar ("Brun Farin")
    'kokos',  # coconut ("Kokos Riven")
    'agar',  # agar agar (vegan gelatin)
    'anis',  # anise spice
    'dragon',  # tarragon herb (6 chars) — "Dragon Burk", "Dragon Färsk"
    'mejram',  # marjoram herb (6 chars) — "Mejram Burk"
    'ättika',  # vinegar (6 chars) — "Ättika 12%"
    'rucola', 'ruccola',  # arugula (6-7 chars) — stores spell "Ruccola", recipes often "rucola"
    'lättöl',  # light beer (6 chars) — used in cooking
    # Bread/vegetables
    'limpa',  # bread loaf
    'frisé',  # frisée lettuce
    'bbqsås',  # BBQ sauce (6 chars, from _SPACE_NORMALIZATIONS: barbequesås/bbq-sås → bbqsås)
    # Batch 10 additions
    'paneer',  # Indian cheese (6 chars)
    'röding',  # Arctic char fish (6 chars)
    'löjrom',  # bleak roe (6 chars)
    'nudlar',  # noodles (6 chars)
    'cognac',  # cooking liquor (6 chars)
    'sherry',  # cooking wine (6 chars)
    'krasse',  # cress/watercress (6 chars)
    'körvel', 'korvel',  # chervil (6 chars)
    'enbär', 'enbar',  # juniper berries (5 chars)
    'tajin',  # Moroccan spice blend (5 chars)
    'mynta',  # mint herb (5 chars) — "Mynta Burk"
    # Batch 11 additions
    'högrev', 'hogrev',  # beef chuck (6 chars)
    'kombu',  # seaweed for dashi (5 chars)
    'pomelo',  # citrus fruit (6 chars)
    'blåbär', 'blabar',  # blueberry (6 chars) — below STRICT threshold
    'bärmix', 'barmix',  # mixed berries (6 chars) — enabled by "blandade bär" space normalization
    'chèvre', 'chevre',  # goat cheese (6 chars)
    'getost',  # goat cheese Swedish (6 chars)
    'whisky',  # cooking spirit (6 chars)
    'dinkel',  # spelt grain (6 chars)
    'rom',  # rum for cooking (3 chars)
    # Note: 'örter' NOT added — too generic, matches flavored färskost/sås FPs
    # Batch 12 additions
    'kolja',  # haddock fish (5 chars)
    # Bread brand names (needed for OFFER_EXTRA_KEYWORDS mapping)
    # NOTE: 'rosta' NOT here — collides with cooking method "rostad/rostade" causing FPs in 12+ recipes
    'sarek',  # Norrländskt tunnbröd brand (5 chars) — maps to tunnbröd
    'liba',   # Liba tunnbröd brand (4 chars) — maps to tunnbröd
    'cider',  # alcoholic/non-alcoholic cider (5 chars) — FPB already blocks cidervinäger collision
})

OFFER_EXTRA_KEYWORDS: Dict[str, List[str]] = {
    'färskpotatis': ['potatis'],
    'farskpotatis': ['potatis'],
    'glutenfrihavregryn': ['havregryn'],
    'vegoburgare': ['vegetariskhamburgare'],
    'veggoburgare': ['vegetariskhamburgare'],
    'halloumiburgare': ['vegetariskhamburgare'],
    'grillostburgare': ['vegetariskhamburgare'],
    # Fish fillets → base fish name (recipes say "torsk"/"lax", stores sell "Torskfilé"/"Laxfilé")
    'laxfilé': ['lax', 'fiskfilé'],
    'laxfile': ['lax', 'fiskfilé'],
    # Mussel species → base mussels (recipes say "musslor", stores sell "Blåmusslor"/"Grönmusslor")
    'blåmusslor': ['musslor'],
    'blamusslor': ['musslor'],
    'grönmusslor': ['musslor'],
    'gronmusslor': ['musslor'],
    # Scallop packs are sold in plural, while recipes often ask for singular
    # "kammussla"/"pilgrimsmussla" on the ingredient side.
    'kammusslor': ['kammussla', 'pilgrimsmussla'],
    'pilgrimsmusslor': ['kammussla', 'pilgrimsmussla'],
    # Tårtbotten compound forms → base 'tårtbottnar' so recipe "tårtbottnar med chokladsmak"
    # finds "Chokladtårtbotten" / "Vaniljtårtbotten" products
    'chokladtårtbotten': ['tårtbottnar', 'tårtbotten'],
    'chokladtartbotten': ['tårtbottnar', 'tårtbotten'],
    'vaniljtårtbotten': ['tårtbottnar', 'tårtbotten'],
    'vaniljtartbotten': ['tårtbottnar', 'tårtbotten'],
    # Sill and strömming are the same fish in everyday Swedish grocery
    # matching. Keep the equivalence narrow to the fillet family here so
    # explicit fillet recipe lines can accept either store wording.
    'sillfilé': ['sillfileer', 'strömmingsfileer'],
    'sillfile': ['sillfileer', 'strömmingsfileer'],
    'strömmingsfileer': ['sillfileer'],
    # Deli platter products are pragmatic fallbacks for recipe "charkbricka"
    # lines, but we keep the bridge narrow to explicit platter/mix names.
    'antipastitallrik': ['charkbricka'],
    'tapastallrik': ['charkbricka'],
    'tapasmix': ['charkbricka'],
    'pepparsalami': ['salami'],
    # Cocktail cherries are the store product family for maraschino-cherry garnish lines.
    'cocktailbär': ['maraschinokörsbär'],
    'cocktailbar': ['maraschinokörsbär'],
    'torskfilé': ['torsk'],
    'torskfile': ['torsk'],
    'torskrygg': ['torsk'],
    'sejfilé': ['sej'],
    'sejfile': ['sej'],
    'koljafilé': ['kolja'],
    'koljafile': ['kolja'],
    'rödspättafilé': ['rödspätta'],
    'rodspattafile': ['rödspätta'],
    # Parmigiano Reggiano → also match plain "parmigiano" keyword
    # Recipes say "parmesanost" which normalizes to "parmigiano" — must match all 19+ products
    'parmigiano reggiano': ['parmigiano'],
    # Baby/blad spinach → also match plain "spenat" keyword
    # Recipes say "spenat", stores sell "Babyspenat" / "Bladspenat" / "Spenat i storpack"
    'babyspenat': ['spenat'],
    'bladspenat': ['spenat'],
    # Prepared artichoke products should still surface for artichoke-heart recipe lines,
    # but exact heart products rank naturally via the dedicated keyword.
    'kronärtskocka': ['kronärtskockshjärta'],
    'kronartskocka': ['kronärtskockshjärta'],
    # Strösocker → also match plain "socker" (recipes say "socker", stores sell "Strösocker")
    'strösocker': ['socker'],
    'strosocker': ['socker'],
    # Plain recipe "majs" usually means loose corn kernels sold as "Majskorn".
    'majskorn': ['majs'],
    # Balsamic products → match balsamvinäger recipes
    'balsamico': ['balsamvinäger'],
    # Ruccola/rucola spelling variants: recipes often say "ruccola" while
    # product extraction normalizes to canonical "rucola".
    'rucola': ['ruccola'],
    # Gruyère accent normalization — products use è/é accents but recipes say "gruyerost" (no accent)
    'gruyère': ['gruyere'],
    'gruyére': ['gruyere'],
    # Swedish standard hard cheeses should still satisfy generic "ost" recipes
    # from the PRODUCT side, while explicit ingredient names stay specific.
    'prästost': ['ost'],
    'prastost': ['ost'],
    'herrgårdsost': ['ost'],
    'herrgardost': ['ost'],
    'grevéost': ['ost'],
    'greveost': ['ost'],
    'hushållsost': ['ost'],
    'hushallsost': ['ost'],
    'edamerost': ['ost'],
    'sveciaost': ['ost'],
    # Generic nut lines ("hackade nötter") should surface plain single-nut products,
    # but not mixed nut bags. Keep this one-way on the product side only.
    'cashewnötter': ['nötter'],
    'cashewnotter': ['nötter'],
    # Generic "växtbaserad mjölk/dryck" recipe lines should surface ordinary plant drinks
    # without broadening dairy milk or generic "dryck" products.
    'havredryck': ['växtdryck'],
    'sojadryck': ['växtdryck'],
    'mandeldryck': ['växtdryck'],
    'ärtdryck': ['växtdryck'],
    'artdryck': ['växtdryck'],
    'risdryck': ['växtdryck'],
    'kokosdryck': ['växtdryck'],
    # The live dairy offer family is sold as "Mjölkdryck ..." rather than plain
    # "mjölk", so bridge it back to the ordinary milk recipe wording.
    'mjölkdryck': ['mjölk', 'mellanmjölk'],
    'mjolkdryck': ['mjölk', 'mellanmjölk'],
    # Soy sauce products should still satisfy ordinary "soja" recipe lines.
    'sojasås': ['soja'],
    'sojasas': ['soja'],
    # Recipe wording "fläderdryck" is an umbrella for the ordinary elderflower
    # drink/cordial families sold as either ready drink or saft.
    'fläderblomsdryck': ['fläderdryck'],
    'fladerblomsdryck': ['fladerdryck'],
    'flädersaft': ['fläderdryck'],
    'fladersaft': ['fladerdryck'],
    # The live "Rice Krispies" cereal is the practical store equivalent for
    # recipe "rispuffar" lines in baking/snack recipes.
    'krispies': ['rispuffar'],
    'hasselnötter': ['nötter'],
    'hasselnotter': ['nötter'],
    'hasselnötskärnor': ['nötter'],
    'hasselnotskarnor': ['nötter'],
    'jordnötter': ['nötter'],
    'jordnotter': ['nötter'],
    'macadamianötter': ['nötter'],
    'macadamianotter': ['nötter'],
    'paranötter': ['nötter'],
    'paranotter': ['nötter'],
    'pekannötter': ['nötter'],
    'pekannotter': ['nötter'],
    'pecannötter': ['nötter'],
    'pecannotter': ['nötter'],
    'pinjenötter': ['nötter'],
    'pinjenotter': ['nötter'],
    'pistagenötter': ['nötter'],
    'pistagenotter': ['nötter'],
    'pistaschnötter': ['nötter'],
    'pistaschnotter': ['nötter'],
    'valnötter': ['nötter'],
    'valnotter': ['nötter'],
    'valnötskärnor': ['nötter'],
    'valnotskarnor': ['nötter'],
    # Canned fish compounds → base fish name (recipes say "makrill", stores sell "Makrillbitar")
    'makrillbitar': ['makrill'],
    'makrillfilé': ['makrill'],
    'makrillfile': ['makrill'],
    # Preserved fruit segments should satisfy the umbrella fruit wording used in recipes.
    'mandarinklyftor': ['mandariner'],
    # Plant-based chorizo should still satisfy generic chorizo lines.
    'vegochorizo': ['chorizo'],
    # Generic sausage wording should surface common named sausage families too.
    'chorizo': ['korv'],
    'salsiccia': ['korv'],
    # Plain macaroni recipes should still surface ordinary dry macaroni products.
    'idealmakaroner': ['pasta'],
    # Colored Thai curry pastes should satisfy the matching colored curry family.
    'rödcurrypasta': ['rödcurry'],
    'rodcurrypasta': ['rodcurry'],
    'gröncurrypasta': ['gröncurry'],
    'groncurrypasta': ['groncurry'],
    'gulcurrypasta': ['gulcurry'],
    # Turkey compound products → generic base keyword (direction 1 only, no reverse mapping)
    # So recipe "bacon" finds "Kalkonbacon", but recipe "kalkonbacon" does NOT find generic bacon
    'kalkonbacon': ['bacon'],
    'kalkonkorv': ['korv'],
    'kalkonköttbullar': ['köttbullar'],
    # BaconOst tube cheese should satisfy explicit "baconmjukost" wording.
    'baconost': ['baconmjukost'],
    # Long pasta → also "pasta" umbrella keyword (recipe "pasta" should match all regular pasta)
    'långpasta': ['pasta'],
    'langpasta': ['pasta'],  # without diacritics
    # NOTE: buljong↔fond cross-matching removed. Buljong and fond are separate product
    # categories. "kycklingbuljong eller fond" is handled in extract_keywords_from_ingredient
    # by rewriting "eller fond" → "eller kycklingfond" based on the preceding buljong type.
    'kantarellfond': ['fond'],  # kantarellfond has no parent, keeps original keyword
    # === Bread type mappings ===
    # Rost/toast breads → formbröd (same sliced bread category)
    'rostbröd': ['formbröd'],
    'rostbrod': ['formbröd'],
    'frasrost': ['formbröd'],
    'ostrost': ['formbröd'],
    'fiberrost': ['formbröd'],
    'originalrost': ['formbröd'],
    'frörost': ['formbröd'],
    'frorost': ['formbröd'],
    'vallmorost': ['formbröd'],
    # NOTE: 'rosta' removed — now a STOP_WORD (cooking method "rostad/rostade")
    # Product "Rosta" (Pågen bread) won't match recipes, but Frasrost/Ostrost/Rostbröd cover formbröd
    'levainrost': ['formbröd'],  # Levainrost (sourdough toast)
    "roast'n": ['formbröd'],  # Roast'n Toast
    'brioche': ['formbröd'],  # brioche rostbröd
    # Formbröd products → also match recipe keyword 'formfranska' (55 recipes)
    'formbröd': ['formfranska'],
    # Norrländska tunnbröd brand names → tunnbröd
    'sarek': ['tunnbröd'],
    'abisko': ['tunnbröd'],
    'njalla': ['tunnbröd'],
    'polarkaka': ['tunnbröd'],
    'polarpärlan': ['tunnbröd'],
    'polarparlan': ['tunnbröd'],
    'hönökaka': ['tunnbröd'],
    'honokaka': ['tunnbröd'],
    'liba': ['tunnbröd'],  # Liba Original Tunnbröd
    # Generic "kex" recipe lines should surface obvious cracker/cookie families
    # without having to collapse every product to the generic keyword.
    'digestivekex': ['kex'],
    'digestive': ['kex'],
    'aperitivokex': ['kex'],
    'mariekex': ['kex'],
    'smörgåskex': ['kex'],
    'smorgaskex': ['kex'],
    'matkex': ['kex'],
    'bokstavskex': ['kex'],
    'breton': ['kex'],
    'saltiner': ['kex'],
    # Generic "nötsmör" lines should see the obvious nut-butter families
    # already present in store product names.
    'mandelsmör': ['nötsmör'],
    'mandelsmor': ['nötsmör'],
    'jordnötssmör': ['nötsmör'],
    'jordnotssmor': ['nötsmör'],
    # Coconut products → 'kokos' so they match "riven kokos" recipes
    'kokosflingor': ['kokos'],
    'kokoschips': ['kokos'],
    # Pickled cucumber products → 'inlagdgurka' so they match "inlagd gurka" / "ättiksgurka" recipes
    'gurkailag': ['inlagdgurka'],          # "Gurka i lag" (after SPACE_NORM)
    'tunnskivadgurka': ['inlagdgurka'],    # "Tunnskivad Gurka" (after SPACE_NORM)
    # NOTE: bostongurka not mapped — sweet relish, different from inlagd gurka
    'saltgurka': ['inlagdgurka'],           # "Hel Saltgurka 700g Felix", "Saltgurka skivad 700g Felix"
    # 5-minuterssill = inläggningssill (same product, different name)
    '5-minuterssill': ['inläggningssill'],  # "5-minuterssill i bitar 430g Abba"
    # Plocksallat = leaf/crispy lettuce. 'sallat' in _SUFFIX_PROTECTED_KEYWORDS blocks substring
    # match in "plocksallat", so fresh sallat offers need 'plocksallat' added explicitly.
    # PNB in blocker_data blocks seed packets (Nelson Garden, frö etc.).
    # 'salladsblad' = generic leaf-salad wording in recipes ("4 stora salladsblad").
    # 'grönsallad' is a nearby generic wording used for the same leafy lettuce family.
    # None of the species-specific keywords (kruksallat, isbergssallat, etc.) are substrings
    # of those recipe words, so leafy lettuce offers need explicit extra keywords.
    'sallat': ['plocksallat', 'salladsblad', 'grönsallad'],
    'plocksallat': ['salladsblad', 'grönsallad'],
    'kruksallat': ['plocksallat', 'salladsblad', 'grönsallad'],
    'krispsallat': ['plocksallat', 'salladsblad', 'grönsallad'],
    'isbergssallat': ['salladsblad', 'grönsallad'],
    'hjärtsallad': ['salladsblad', 'grönsallad'],
    'hjartsallad': ['salladsblad', 'grönsallad'],
    'hjärtbergsallad': ['grönsallad'],
    'hjartbergsallad': ['grönsallad'],
    'bistrosallad': ['salladsblad', 'grönsallad'],
    'romansallad': ['salladsblad', 'grönsallad'],
    'romanasallad': ['grönsallad'],
    'miniromansallat': ['salladsblad', 'grönsallad'],
    'machesallat': ['salladsblad', 'grönsallad'],
    # Gelé products: specific vinbär → generic parent
    # Space norms convert "Gele Svartvinbär" → compound "svartvinbärsgele" so carrier doesn't strip it
    'svartvinbärsgele': ['vinbärsgele'],  # "Gele Svartvinbär" → matches recipe "vinbärsgelé"
    'rödvinbärsgele': ['vinbärsgele'],    # "Gele Rödvinbär" → matches recipe "vinbärsgelé"
    'bordsgurka': ['inlagdgurka'],          # "Gammaldags Bordsgurka 730g Felix" — pickled table cucumber
    # --- Batch 4-5 FN fixes: offer-side keyword extraction ---
    # Coffee products: "Bryggkaffe 500g" should match recipe "2 dl bryggkaffe"
    # Also add 'kokkaffe' so "Brygg- och kokkaffe" ingredient (hyphenated compound)
    # can match via 'kokkaffe' substring ("bryggkaffe" is not in "brygg- och kokkaffe").
    'bryggkaffe': ['bryggkaffe', 'kokkaffe'],
    # Coffee bean products: "Kaffebönor Brazil" should match recipe "kaffebönor"
    'kaffebönor': ['kaffebönor'],
    'kaffeböna': ['kaffebönor'],   # singular form
    # Cottage cheese products often lose trailing brand "Keso" during brand
    # stripping, so keep a stable keso bridge on the product side.
    'cottage cheese': ['keso'],
    # Tomato sauce products containing "tomatsås" in name but extracted as "pastasås"
    'tomatsås': ['tomatsås'],
    # Plural→singular for carrier-context re-added flavors
    'ostar': ['ost'],  # "Pastasås Fyra Ostar" → also match 'ost' in "pastasås ost"
    # Fresh mushroom families should also match generic recipe wording "svamp".
    # Keep this narrow to actual fresh cooking mushrooms, not dried/fond/pastej products.
    'champinjoner': ['svamp'],
    'skogschampinjoner': ['skogschampinjoner', 'champinjoner', 'svamp'],
    'babychampinjoner': ['babychampinjoner', 'champinjoner', 'svamp'],
    'kantarell': ['svamp'],
    'kantareller': ['svamp'],
    'ostronskivling': ['svamp'],
    'karljohansvamp': ['svamp'],
    # Mixed-bean products should match generic mixed-bean ingredient lines
    'bönmix': ['bönor'],
    # Green-bean offers should participate in the generic bean family, with
    # bean specialty qualifiers deciding when they are actually acceptable.
    'haricot': ['bönor'],
    'brytbönor': ['bönor'],
    'brytbonor': ['bönor'],
    # Silken tofu offer wording should match recipe wording "silkestofu"
    'silkesmjuk': ['silkestofu'],
    # Salmon-roe variants should match generic salmon-roe ingredients
    'regnbågslaxrom': ['laxrom'],
    # Fjällröding is a specific char variant that should satisfy generic röding.
    'fjällrödingfilé': ['röding'],
    'fjallrodingfile': ['röding'],
    # Plant-based yoghurt brands → also match 'yoghurt' so "växtbaserad gurt" recipes find them.
    # check_yoghurt_match ensures only vego recipes match vego yoghurt products.
    'plantgurt': ['plantgurt', 'yoghurt'],
    'havregurt': ['havregurt', 'yoghurt'],
    # Cherry tomato singular/plural: recipes use singular "körsbärstomat" but offers have keyword
    # "körsbärstomater" (plural). Swedish plural is longer than singular, so "körsbärstomater"
    # is not a substring of "körsbärstomat" → FTS pre-filter misses the recipe.
    # Adding singular as extra keyword makes FTS search for it too.
    'körsbärstomater': ['körsbärstomater', 'körsbärstomat'],
    'korsbarstomat': ['körsbärstomat'],  # normalized form
}
