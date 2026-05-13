## Övrigt

Curated by orchestrator after worker review. This file is a decision log plus
the place for new Stefan questions. Direct fix candidates from the same pilot
should be handled by matcher edits, not asked as policy questions.

Open questions: none.

Recurring root-cause cleanup - 2026-05-03:
- Raw `kyckling`/`kycklingfilé` recipe ingredients must exclude deli/pålägg
  products sold as `tunna skivor`/`deliskivor`, while raw `tunnskivad`
  kycklingfilé remains valid.
- `Riven` in cheese ingredients is preparation/use, not a hard product-form
  requirement. `Riven mozzarella` may match ordinary mozzarella that can be
  grated by the cook, and generic `ost` may match riven cheese products.
- Explicit `färska lasagneplattor` requires fresh lasagne-sheet products such
  as `Lasagneplattor Färsk Pasta Garant`; dry shelf lasagneplattor are a
  different form.
- Batch 10-13 root-cause pass added carrier-required handling for `salsa` and
  `knäckebröd`/`knäcke`: flavor/liquor/seed words inside those carriers must
  not satisfy standalone ingredients. Examples: `Salsa Pineapple Vodka El Taco
  Truck` can match `salsa` but not `vodka`; `Vallmofrö Falu Knäckebröd` can
  match `knäckebröd` but not standalone `vallmofrö`.
  Both carrier examples are now covered by matcher-layer parity fixtures.
- Batch 10-13 form/type pass: preserved/ready-cooked carrot packs such as
  `Morötter Små Hela` are not plain fresh carrots; dry lentil wording blocks
  cooked/pre-cooked lentil packs; explicit `äggnudlar` blocks non-egg noodle
  families; citrus juice products now route to `citronjuice`/`limejuice` while
  still blocking whole-fruit/zest requirements; dry `Indian Spices` products
  route as spice mixes without allowing curry paste/sauce carriers; explicit
  spice-mix variants such as `taco`, `tikka`, `garam`, `tandoori`, `bifteki`,
  `five spice`, and `Asian spice mix crispy coating garlic` must match the
  product's own variant instead of falling through the bare `kryddmix` carrier.
  The core variant matrix is now covered by matcher-layer parity fixtures.
- Batch 10-13 specialty pass: explicit chocolate-button variants are kept
  separate (`vit`, `mörk`/dark, `mjölk`/milk), while generic
  `chokladknappar` may use any normal button variant.
- Verification for this pass after final dev reload:
  `tests/test_matching_sanity.py` passed `1666/1666`; targeted ruff on the
  touched Python/test files passed; full cache pair revalidation checked
  `320372` groups / `1206744` cache entries with `0` rejects. The dev cache was
  current for that pass at matcher `matcher-d9e12d4f6edd`.

Cache keyword audit follow-ups:
- Full cache keyword audit initially flagged false rejects because the audit
  script revalidated a single isolated ingredient row and lost recipe-level
  context. Correct audit behavior is to revalidate with the full recipe
  ingredients/name from the representative cached row.
- `guacamole-mix`: ingredients such as `20 g guacamole-mix` should not match
  ready guacamole (`Guacamole El Taco Truck`). They are seasoning/mix products;
  correct goods would need a guacamole kryddmix/mix product. Plain ingredients
  such as `2 dl guacamole` still match ready guacamole.
- `kebab`: ingredients such as `330 g kebabkött`, `500 g kebab`, and
  `400 g kebabskav` should match kebab meat products such as
  `Kebab Grillad Och Skuren Fryst Eldorado`, `Klassisk Kebab Schysst Käk`, and
  `Kebab av Fläskkarré Sverige Garant`. They should not match kebab sauce,
  kebab bread, or ready kebab pizza products such as `Kebab Mild Sås Felix`,
  `Somunbröd Till Kebab Cevapcici Fryst Plivit`, or
  `Kebab Supreme Fryst Grandiosa`.
- `tortillabröd` / `tortilla`: soft tortilla/wrap ingredients should not match
  Spanish tortilla/omelette products such as `Tortilla med Lök Palacios` or
  `Tortilla Utan Lök Palacios`. Ordinary tortilla bread/wrap products remain
  correct matches.
- `vetetortillas`: explicit wheat tortilla ingredients should not match
  corn-only tortilla products such as `Corn Tortillas Glutenfri El Taco Truck`.
  Generic `tortillas` ingredients may still match corn tortillas, and mixed
  corn/wheat tortilla products remain acceptable for wheat tortilla wording.
- Alternative groups such as `ägg / kikärtor`,
  `mortadella / prosciutto / salame`, `tunnbröd / tortilla`, and
  `pesto / svamp / parmigiano reggiano / tapenade` can look odd in a
  product-level audit, but in the inspected recipes they came from explicit
  `eller` alternatives or grouped ingredient lines and revalidated cleanly with
  full recipe context.

Recipe term audit follow-ups:
- Product `name_word` routing terms must match whole recipe words only.
  Substring routing caused false candidate routes such as `läsk` from `fläsk`,
  `pepp` from `svartpeppar`, `toma` from `tomat`, `citr` from `citron`,
  `strö` from `strösocker`, and `potat` from `potatis`.
- Recipe term routing must use prepared ingredient text from compiled recipe IR,
  not only raw `ingredients_search_text`. Prepared text carries canonical
  aliases already used by the live matcher, e.g. `makaroner` -> `pasta`,
  `humrar` -> `hummer`, `färska bär` -> berry keywords, and plant-based
  `matlagning` -> cream-family routing.
- `burger buns` means hamburger bread/buns, not burger patties. It should match
  hamburger bread products and should not match products such as
  `Crispy Kycklingburgare Fryst Kronfågel`.
- `Havrebaserad matlagning` / `Soyabaserad matlagning` are explicit
  plant-based cooking-cream requirements. They should not match ordinary dairy
  cooking cream such as `Matlagnings Grädde Lång Hållbarhet 15% Kelda`; oat
  wording should match oat cooking products such as Oatly iMat.

Recipe route-pruning status - 2026-05-02:
- Sole-route audit showed broad `name_word` routes such as `vatten`, `salt`,
  `burk`, `fryst`, `riven`, `malen`, `port`, `läsk`, `chokladkaka`, `zeta`,
  etc. mostly created candidate noise rather than carrying accepted matches.
  Do not route on generic descriptors/packaging/brand/state words as product
  `name_word` terms.
- Specific identities remain routeable: `flingsalt`, `havssalt`, and
  `mineralvatten` via keyword, and `kolsyrat` as a useful product name word.
  This addresses the salt/water concern without letting plain `salt`/`vatten`
  route every product that happens to contain those words.
- `stor/hel kyckling` now gets recipe-side routing alias `helkyckling`, so
  whole-chicken offers no longer depend on broad `färsk` routing.
- Measured after dev reload: candidate pairs dropped from `4,343,062` to
  `3,281,433`; recipe term-index rows dropped from `265,696` to `230,449`;
  cache compute was `140,730ms`, full reload wall time `168s`; cache coverage
  stayed `13273/13331`, route coverage stayed `missing_pairs=0`.
- Verification completed: `tests/run_recipe_ingredient_term_map_checks.py`
  passed `18/18`, and `tests/test_matching_sanity.py` passed `1573/1573`.
- Remaining on this track: no open Stefan decision right now. Optional later
  work is a second route-pruning pass over remaining high-volume identity terms
  if rebuild time is still too high. The all-groups live revalidation script was
  started as extra safety but abandoned because it is too slow for this loop;
  route coverage and sanity tests are the current source of truth here.

All-groups live revalidation follow-up - 2026-05-02:
- The audit script can be made useful by reusing compiled recipe/offer IR
  instead of rebuilding recipe/offer matcher state for every representative
  cached group.
- Tested modes on full `--all-groups --group-by-ingredient` scope:
  `321,145` representative groups and `1,205,714` cached entries.
  `--revalidate-mode compiled` ran the full matcher path with compiled IR in
  `88,548ms` after `1,042ms` cache-load time and found `0` rejected groups.
  `--revalidate-mode pair` ran the fast phase-1 accept/reject path in
  `23,980ms` after `1,027ms` cache-load time and also found `0` rejected
  groups.
- Practical recommendation: use `pair` mode as a quick regression/audit check
  after matcher changes, and `compiled` mode when we specifically need the full
  grouped matcher semantics. The old raw full path is still available as
  `--revalidate-mode full` for debugging.
- Decision: keep this dev script local and untracked, but place it with the
  other batch-review tools under ignored
  `app/tests/batch_review_cache_matched_keyword_audit.py`. Do not promote it to
  a tracked test utility unless we later need it as a formal regression command.

## Batch 1 selection_rank 1-20 pilot - 2026-05-02
Not questions:

- `växtbaserad gurt` and `micropopcorn` are not Stefan questions. Treat
  live-vs-cache divergence for these as direct cache/routing fix candidates,
  not as product-policy questions.
- Generic `lax`/`laxfilé` remains broad by accepted policy unless the recipe asks
  for a stricter form.
- English/store naming variants such as `bamboo shoot`, `nori`/`seaweed`, and
  `ketjap manis` are direct fix candidates, not Stefan questions.
- Flavor/carrier FPs are direct fix candidates when the product is a different
  carrier and the matched ingredient is only a taste/component, or when a
  plain/ordinary ingredient matches a strong flavored product that changes the
  cooking role. Examples from this pilot:
  - In `Ugnsrostad kyckling med sötpotatismos`, ingredient
    `1 msk torkad oregano` matched `Greek Style Oregano & Olive Oil Vegansk
    Greenvie`; this is a false positive because the recipe asks for standalone
    dried oregano, not cheese. If a recipe context is actually cheese/vegan
    cheese, inspect it before deciding.
  - Soy sauce variants are acceptable as soy sauce: `Japansk soja`/`Kinesisk
    soja`/ordinary soy may match chili/hot/sweet soy sauce variants unless the
    product is not actually soy sauce.
  - `1 dl Mellanmjölk` -> flavored/protein/baby `Mjölkdryck` products is not
    plain cooking milk. Flavored milk is out for milk ingredients; ordinary
    lactose-free milk can still be acceptable when it is the same milk role.
- Fresh small tomato fallback for fresh `körsbärstomater` is already accepted
  policy and should be fixed if live matcher misses it.

Accepted direct fixes from this pilot:

- `Växtbaserad gurt`: live matcher can match plantgurt/kokosgurt, but compiled
  cache/routing must expose the canonical `yoghurt` token too.
- `1 påse micropopcorn`: micro/mikro/Micropop/Micropopcorn spelling variants
  are the same real product and should route in compiled cache.
- `227 g Bambuskott`: English offer wording `Bamboo Shoot` should match
  Swedish `bambuskott`.
- `20 g Alger`: nori/seaweed/`seeweed` products can satisfy generic algae
  wording; this does not change the separate tångpärlor/tångcaviar decision.
- `1 msk torkad oregano`: oregano-flavored vegan cheese/carrier products are
  not standalone dried oregano.
- `1/2 gurka`: the current `Gurka Finhackad Garant` product is preserved/pickled
  and should not match fresh cucumber.
- `ny kokt pasta` and `Tagliatelle`: konjac/shirataki noodles are not ordinary
  wheat pasta or long pasta.
- `125 g Körsbärstomater`: fresh cherry tomatoes may fall back to fresh
  cocktail/small tomatoes, but not preserved tomatoes in tomato juice.
- `3 dl Långkornigt Ris`: black/red specialty rice should not match ordinary
  long-grain rice.
- `2 st Paprika`: preserved paprika fillets (`Paprika File`) should not match
  fresh whole paprika.
- `1 dl Mellanmjölk`: flavored/protein/baby milk drinks are not plain cooking
  milk; ordinary same-role milk drinks/lactose-free milk remain acceptable.
- `600 g laxfilé med skinnet kvar`: salmon stew pieces are not skin-on
  salmon fillet/side.

Accepted direct-fix references from batch 1 ranks 21-100:

- `4 tsk Grön Currypasta`: correct goods are green curry paste products such
  as `Green Curry Paste Garant`; do not fall back to red/yellow/plain curry.
- `1 msk Röd Currypasta`: correct goods are red curry paste products such as
  `Red Curry Paste Garant` and `Red Curry Paste Currypasta Cock Brand`.
- `100 g Färsk bladspenat`, `250 g hel spenat`, and
  `200 g färsk grönkål eller färsk spenat`: correct goods are raw/fresh/frozen
  spinach or greens. `Svamp&spenat Ostschnitzel Garant` is a schnitzel product;
  its flavor/filling words must not match standalone vegetables.
- `250 g Svamp`: correct goods are mushroom products. A schnitzel flavored with
  mushroom is not a mushroom product, unless the recipe explicitly asks for
  schnitzel.
- `2 msk kapris` / `3 msk Kapris`: correct goods are capers such as
  `Kapris Cocktail Garant`, `Kapris Medelstora Garant`, `Kapris Non Pareilles
  Garant Eko`, or `Kapris Små Zeta`; not `Tapenade Al Basilico Basilika Oliv
  Kapris Garant`.
- `2 msk worcestersås`: correct good is `Worcestershire Sauce Lea&perrins`.
- `0,5 dl pistagenötter`: correct goods are pistachio nuts/kernels such as
  `Pistaschkärnor Utan Skal Rostade Och Saltade Garant` and
  `Pistaschnötter Rostade Saltade ...`.
- `200 g Cashewmeetlyfärs`: correct good is the named vegan mince if present;
  it must not match plain cashew nuts.
- `2 msk Hoisinsås Eller vegansk ostronssås`: correct goods are hoisin sauces
  such as `Hoisin Sauce Spicefield`, `Hoisin Wok Sauce Blue Dragon`, and
  `Hoisinsås Koon Chun`; ordinary oyster sauce is not a vegan oyster-sauce
  match.
- `2 portioner färdiglagat kalkonkött`: correct good is cooked turkey meat such
  as `Kokt Kalkon Strimlad Tulip`; not raw turkey fillet and not turkey sausage
  or deli salami/mortadella.
- `2 st tunnbröd`: correct goods are actual tunnbröd products such as
  `Tunnbröd 8p Garant`, `Liba Original Tunnbröd Vitt 4-pack Liba Bröd`, and
  `Gammeldags Tunnbröd Mjälloms`; not `Hönökaka` or `Polarpärlan`.
- `99 cl Alkoholfri öl`: correct goods are alcohol-free beer/lager products
  such as `Ljus Alkoholfri, Eko Lager, Burk Norrlands Guld`,
  `Hoppy Lager Alkoholfri 0,0% Flaska Carlsberg`, and other alkfri/non-alcoholic
  beer rows; not regular folköl/lager.
- `1 tsk Dragon - torkad`: correct goods are tarragon/dragon herb products
  such as `Dragon Burk Kockens` or `Fransk Dragon Garant`; not products where
  Dragon is only part of the `Twin Dragon` brand.
- `125 g Mozzarellaost`: correct goods are mozzarella cheese products such as
  `Mozzarella 17% Castelli`, `Mozzarella Bio Michelangelo`, or
  `Mozzarella Bufala Campana 23% Garant`; not `Pompodoro Mozzarella Mix Knorr`.
- `2 msk Gelé Svartvinbär`: correct goods are blackcurrant jelly products such
  as `Svartvinbärs Gele Eko Björnekulla` and `Svartvinbärs- Gele Eldorado`;
  not blackcurrant cordial/saft.
- `600 g kall färsk potatis kokt i grönsaksbuljong`: correct goods include
  ordinary fresh/normal potatoes; the bouillon cooking liquid should not hide
  the potato ingredient.
- `3 dl Sötsur Sås`: correct goods are sweet-and-sour sauce products such as
  `Sweet & Sour Original Sås Ben's Original`, `Sweet & Sour Extra Ananas Sås
  Ben's Original`, and `Sweet & Sour Sås Spicefield`.
- `90 g Prosciutto`: correct goods are the air-dried ham/prosciutto family,
  including `Prosciutto Crudo Skivad Garant`, `Prosciutto Di Parma Skivad
  Garant`, `Prosciutto 18 Månader Terre Ducali`, `Jamon Serrano 11mån Skivad
  Garant`, and ordinary lufttorkad-skinka equivalents; not pizza/filled-pasta
  carriers.
- `1 förp tryffelmajonnäs`: correct goods are truffle mayonnaise products such
  as `Tryffel Majonnäs Garant` and `Tryffelmayo Hellmann's`; not plain
  mayonnaise.
- `0.5 tsk Spiskummin`, `1 msk hel spiskummin eller 1 tsk malen spiskummin`,
  and `1 tsk Spiskummin`: correct goods are cumin/spiskummin spice products
  such as `Spiskummin Burk Kockens`, `Spiskummin Malen Burk Kockens`, and
  `Spiskummin Malen Eldorado`; not cheese flavored with spiskummin.
- `1 tsk chilipeppar ancho style` and measured generic `1 tsk Chili`: correct
  goods are chili flakes/chili powder such as `Chili Flakes Burk Kockens`,
  `Gochugaru Chili Flakes Kockens`, and `Chilipulver Påse Eldorado`; not
  cayenne, fresh chili, sauces, meat, or flavored carriers.
- `1 dl rom (kan uteslutas)`: with dl/cl volume units, correct goods are spirit
  rum products; fish roe remains correct only for weight/roe contexts such as
  `80 g rom`.
- `2 ättiksgurkor`: correct goods are pickled cucumber/smörgåsgurka products
  such as `Smörgåsgurka Skivad Felix`, `Smörgåsgurka Skivad Eldorado`, and
  `Smörgåsgurka Mor Annas Önos`.

Resolved decisions:

- `Lax och kålrabbi på friterat rispapper med grönkål, jalapeño mayo och tångpärlor`:
  ingredient `50 g Tångpärlor Citron` got 0 live matches even though Willys has
  `Tångcaviar Röd Garant`, `Tångcaviar Svart Garant`, and `Haviar Tångkaviar Garant`.
  Decision: `Tångpärlor` are a distinct specialty and should not match generic
  tångcaviar/tångkaviar/haviar.

- `Het chorizogryta med paprika`: ingredient `2 dl Creme Fraiche Paprika & Chili`
  matched plain/naturell crème fraiche products alongside exact paprika/chili
  products such as `Paprika Chili Creme Fraiche Laktosfri 11% Arla`.
  Decision: match the requested crème fraiche flavor when available, and also
  allow plain/naturell crème fraiche as the standard fallback.

- `Marinerad laxsida`: ingredient `1 st laxsida eller laxfilé med skinnet kvar`
  matched `Lax Varmr Portion Eldorado`.
  Decision: `Lax Varmr Portion Eldorado` is hot-smoked salmon and must not match
  ordinary `lax`, `laxfilé`, or `laxsida`.

## Batch 2 review proposals - 2026-05-02

Direct-fix/reference entries:

- `Vegansk Sparristarte`: ingredient `250 g Vegansk smördeg, tinad` had 0 live
  matches even though Willys has smördeg/puff-pastry offers such as
  `Smördeg Plattor Fryst Garant`, `Smördeg Rektangulär Deg Pop! Bakery`, and
  `Puff Pastry Smördeg Glutenfri Fryst Schär`. Correct goods are smördeg
  products that are vegan/plant-based or at least not contradicted by product
  identity. Narrow mechanism: `smördeg` should route as its own product family
  instead of being suppressed by the generic `smör`/smördeg blocker; do not use
  this to allow explicitly butter/dairy puff pastry for a vegan ingredient.
  Accepted/fixed: if the recipe line explicitly says vegan/vegetarian/
  lactose-free/gluten-free, that label is a one-way requirement on the product.
  Normal ingredient lines may still include matching special-diet variants.
- `Vegansk Sparristarte`: ingredient `100 g Violife veganost` matched ordinary
  dairy cheeses such as `Gouda 28% Eldorado`, `Edamer 24% Eldorado`, and
  `Hushållsost 26% Arla`. Narrow mechanism: when the recipe ingredient says
  `veganost` or names `Violife`, allow vegan/Violife cheese products but block
  ordinary dairy cheese fallback.
  Accepted/fixed: vegan cheese products stay in the cheese proposal family for
  normal `ost`, but ordinary dairy cheese cannot satisfy explicit `veganost`.
- `Chokladtårta med hallon`: ingredient `hackad vit- och mörk choklad` matched
  dark/generic chocolate but missed current white-chocolate baking offers such
  as `Bakchoklad Vit Garant`, `Bakchoklad Ögon Vit Fazer`, and
  `Chokladknappar Vit Odense`. Narrow mechanism: parse `vit- och mörk choklad`
  as both white and dark chocolate instead of only generic/dark chocolate.
  Accepted/fixed: the truncated wording is expanded to separate white and dark
  chocolate families, and color-qualified chocolate buttons can satisfy the
  matching chocolate family.
- `Revbensspjäll till jul`: ingredient `1 kg Revbensspjäll` matched some ribs
  products but missed current spareribs offers such as `Spareribs Sverige
  Garant`, `Spareribs Original Tulip`, and `Spareribs Sweet & Smokey Tulip`.
  Narrow mechanism: map `spareribs` offers into the `revbensspjäll` family.
  Accepted/fixed: `ribs` and `spareribs` are revbensspjäll-family products;
  rub/spice products that merely say ribs stay blocked.
- `Höstgryta med bönor och kantareller`: ingredient
  `200 g kantareller, avrunna (på burk)` had 0 matches even though Willys has
  canned/in-water chanterelles such as `Kantareller i Vatten Borgens`. Correct
  goods are canned/in-water kantareller; do not use kantarell-flavored fresh
  cheese, soup, or fond as mushroom matches.
  Accepted/verified: canned/in-water kantareller match preserved kantareller;
  kantarell-flavored carriers such as fresh cheese, soup, or fond stay blocked.
- `Grekisk pastasallad med avokado` and `Klassisk Grekisk sallad`: ingredients
  `290 g Kalamataoliver` and `1½ dl Zeta Kalamataoliver urkärnade` matched
  generic black/Gemlik olives such as `Skivade Oliver Svarta Eldorado`,
  `Svarta Oliver Urkärnade Eldorado`, `Svarta Oliver Utan Kärnor Figaro`, and
  `Gemlik Oliver Ceren`. Correct goods are explicitly Kalamata products, or
  olivmix products that explicitly contain Kalamata if the recipe can accept
  mixed olives. Generic black/Gemlik olives are accepted black-olive fallbacks
  for Kalamata, but exact Kalamata/explicit Kalamata olivmix should rank first.
  Kalamata olive oil, hummus, and tapenade are not whole-olive matches.
- `Prinsesstårta`: ingredient `2.5 dl Standardmjölk` matched non-milk carriers
  such as `Chokladknappar Mjölk Odense` and flavored/protein milk drinks such
  as `Blåbär Protein Mjölkdryck 0,5% Arla` and `Rosa Jordgubb Mjölkdryck 1%
  Arla Ko`. Correct goods include plain standardmjölk, mellanmjölk,
  lättmjölk, and lactose-free plain milk products; do not over-tighten those
  accepted milk fallbacks. Repeated in `Naanbröd` for ingredient
  `1.5 dl Standardmjölk` and `Pannbiff med potatis` for ingredient
  `1.5 dl Standardmjölk`, and in `Omelettrulle med grönkål och fetaost` for
  ingredient `5 dl standardmjölk`. Accepted/fixed: plain milk family is OK;
  flavored/protein/chocolate-button/baby-style milk carriers are not.
- `Rödbetssallad`: ingredient `710 g hela inlagda rödbetor (en burk)` matched
  fresh/plain/förkokta beetroot such as `Rödbetor Förkokt Klass 1` and
  `Rödbetor Förkokta Eko Klass 1`. Correct goods are pickled/inlagda/jar
  beetroot rows such as skivade, hela, or gammaldags rödbetor in jar.
  Accepted/fixed: förkokta/plain fresh beetroot is not enough when the recipe
  asks for inlagda/jarred beets.
- `Viltgryta med potatismos, stekt savoykål & lingon`: ingredient
  `1 msk Svartvinbärsgelé` matched `Rödvinbärs- Gele Eldorado`. Corrected
  decision: red and black currant jelly are acceptable fallbacks for each
  other; keep the vinbärsgelé family consistent and normalize both
  `Rödvinbärs- Gele` and `Röd Vinbärs Gele` naming variants.
- `Fläskfilépasta`: ingredient `2 msk Grillkrydda Vitlök` matched standalone
  garlic products such as `Vitlök Finhackad Burk Kockens`, `Vitlök Pressad
  Cajom`, and `Vitlöksklyftor Chili Garant`. Correct goods are grillkrydda or
  grill-seasoning products; garlic-flavored grill seasoning is best, ordinary
  grillkrydda fallback is acceptable. Standalone garlic is not the requested
  seasoning. Accepted/fixed: named spice mixes must not degrade to flavor
  components alone.
- `Falafel`: ingredient `0.5 skiva Feferoni` matched the ready sandwich
  `Kebab Feferoni Baguette Good`. Correct goods are feferoni/kebabfeferoni
  pepper products, not ready sandwiches. Accepted/fixed: `Feferoni Kebab`
  pepper jars are OK; baguette/sandwich/pizza-style carriers are not.
- `Falafel`: ingredient `1 tsk Havssalt` matched salted-nut carrier products
  such as `Cashewnötter Stora Rostade med Havssalt Denlillenött`. Correct
  goods are havssalt/mineralsalt products such as `Fint Havssalt med Jod Jozo`;
  salted nuts, chips, or chocolate are carrier false positives. Repeated in
  `Stockholmschili med ugnsrostade tomater och dinkelchips` for ingredient
  `1 krm Havssalt`. Accepted/verified: nut/chip carriers were already blocked
  live; expanded the guard to pantry-miscategorized cracker/chocolate/nut
  carriers too.
- `Poké Bowl`: ingredient `4 dl Jasminris` matched pure basmati, fullkorn, and
  långkornigt rice products. Decision: this is acceptable. Plain everyday rice
  should match standard rice variants such as basmati, fullkorn, långkornigt
  ris, and jasminris; boil-in-bag packs of those rice types are also acceptable
  because they are still plain cooking rice, not ready meals. No matcher
  tightening is needed for this family. Repeated in `Poké Bowl med frasig tofu`
  for ingredient `3 dl Jasminris`.
- `Champinjonsallad med citron och tryffelolja`: ingredient
  `1 msk Zeta Olivolja Vit Tryffel` had 0 matches. Correct goods are
  truffle-oil products such as `Olivolja Tryffel Levante`; white/black truffle
  color wording is not important. Decision: when both the ingredient and recipe
  name ask for a specific critical ingredient like tryffelolja, do not fall back
  to ordinary/plain olivolja.
- `Teaterbrons Paprikalasagne` (`found_recipe_id`
  `44c3b227-6464-47b3-84a9-1a1aa0d7d202`): recipe-level cache/routing false
  negative. There is no `recipe_offer_cache` row at all, despite obvious
  current offer families for ingredients such as `3 st Paprika`,
  `400 g Färska lasagneplattor`, `100 g Riven Västerbottensost`,
  `2 tsk Timjan - torkad`, `2 tsk Sambal Oelek`, `800 g Krossade Tomater`,
  `300 g Fänkål Färsk`, and `2 tsk Honung Flytande`. Count as one recipe-level
  issue, not one issue per ingredient.
- `Stockholmschili med ugnsrostade tomater och dinkelchips`: ingredient
  `900 g Högrev` matched `Kryddkorv Högrev Scan`. Correct goods are raw/cooking
  högrev products. Decision: sausage products where högrev is a component or
  marketing/flavor word are not raw högrev.
- `Snabbpicklade grönsaker`: ingredient `2 morätter` had 0 matches because of
  the typo/variant. Correct goods are carrots/morötter such as
  `Morötter Klass 1 Garant`, eko carrots, or små hela carrots as appropriate.
  Accepted/fixed: normalize `morätter`/`moratter` as a typo for `morötter`.
- `Ljuvliga Havrebollar`: ingredient `0.75 dl Chokladdryck` matched solid
  chocolate and baking chocolate such as `85% Cacao Mörk Choklad Garant`,
  `Bakchoklad Mörk 55% Garant`, and `Bakchoklad Vit Garant`. Correct goods are
  chokladdryck/O'boy/Tigo-style chocolate drink or chocolate-drink powder
  products when current offers exist, not solid chocolate bars.
  Accepted/fixed: `chokladdryck` is its own drink-powder family and must not
  fall back to ordinary `choklad`/`bakchoklad`.
- `Kyckling Hoisin med sesamnudlar`: ingredient `200 g Kycklingfile` matched
  cooked/deli sliced chicken products such as
  `Hönsbröstfilé Pastramikryddad Skivad Guldfågeln` and
  `Kycklingbröst File Grillkryddad Skivad Guldfågeln`. Correct goods are raw
  chicken fillet, breast fillet, inner fillet, or ordinary raw cut/prepared
  chicken pieces suitable for cooking; deli/cooked sliced chicken is not raw
  kycklingfilé. Accepted/fixed: keep raw/tillagningsbar fillet forms, including
  majskyckling breast/inner/thigh fillet variants, but block pastrami/deli or
  explicitly cooked sliced fillet products.
- `Vegansk Gulasch` and `Portabelloburgare med karamelliserad lök`:
  ingredients `Ev. lite rökt paprikapulver till avslutning (Efter smak)` and
  `2 tsk paprikapulver, ev rökt` had 0 live matches even though current offers
  include `Rökt Paprika Kockens`, `Paprikapulver Milt Eldorado`, and
  `Paprika Burk/Påse Kockens`. Correct goods are paprikapulver/paprika spice
  products, with smoked paprika accepted or preferred when the ingredient asks
  for `rökt`. Accepted/fixed: `ev rökt` is optional and can match plain or
  smoked paprika spice jars; exact `rökt paprikapulver` should stay on smoked
  paprika spice products. Fresh/preserved bell pepper products are not
  paprikapulver.
- `Blomkåls- Jansson`: ingredient `2 dl riven Västerbottensost` matched
  `Västerbotten Philadelphia` and missed current cheese products such as
  `Västerbottens Riven Ost 32%` and `Västerbottens Original Ost`. Correct goods
  are Västerbottensost hard cheese/riven cheese products; Västerbotten-flavored
  fresh cheese is not a grated Västerbottensost match. Accepted/fixed: preserve
  Västerbottens as product identity despite brand stripping and block
  Philadelphia/färskost variants for `västerbottensost`.
- `Smörgåstårta med varmrökt lax, räkor och pepparrot`: ingredient
  `350 g varmrökt laxfilé` matched raw/cold-smoked salmon products such as
  `Laxfilé Garant` and `Kallrökt Laxfilé Korshags`. Correct goods are varmrökt
  lax/varmrökt laxfilé products such as `Varmrökt Lax Naturell Portionsbit
  Falkenberg`; raw or cold-smoked lax is not a varmrökt-lax match.
  Accepted/fixed: `laxfilé` now uses the lax specialty qualifiers so varmrökt,
  kallrökt and raw salmon do not collapse into each other; hot-smoked salmon
  also stays out of plain `laxfilé`.
- `Portabelloburgare med karamelliserad lök`: ingredient `salladsmix` had 0
  live matches even though current offers include mixed salad products such as
  `Blandsallad Klass 1 Garant` and `Gourmetsallad Klass 1 Garant`. Correct
  goods are mixed salad/salladsmix/blandsallad products, not ready meal salads.
  Accepted/fixed: mixed leaf-salad products such as `Blandsallad`,
  `Gourmetsallad`, and `Blandad Sallad` expose `salladsmix`; prepared salad
  carriers such as potato/shrimp/chicken/baguette salads remain blocked.
- `Portabelloburgare med karamelliserad lök`: ingredient
  `1 tsk chipotlepasta eller pulver` had 0 live matches even though current
  offers include chipotle seasoning products such as
  `Chilli Chipotle Capeherb&spice`. Correct goods are chipotle paste, chipotle
  powder, or close chipotle chili seasoning products; chipotle-flavored mayo,
  bearnaise, BBQ sauce, meat, or other carriers are not the requested paste or
  powder. Accepted/fixed: `chipotlepasta eller pulver` exposes both
  `chipotlepasta` and `chipotlepulver`; only dry chipotle seasoning/powder or
  explicit paste products may satisfy this, not sauce/mayo/meat carriers.
- `Pancetta-lindade halloumi fries`: ingredient `200 g Pancetta` had 0 live
  matches even though current offers include pancetta products such as
  `Pancetta Garant`, `Pancetta Tärnad Fumagalli`, and
  `Pancetta Tärnat Rökt 2-pack Tulip`. Correct goods are pancetta products;
  ordinary bacon is not a fallback. Accepted/fixed: `pancetta` stays exact to
  pancetta meat products and rejects bacon plus prepared carriers such as filled
  pasta containing pancetta.

Resolved decisions:

- `Smal fisksoppa med tomat och saffran`: ingredient `1.5 msk Skaldjursfond`
  had 0 matches while Willys has related fond offers including `Hummerfond Touch
  Of Taste` and `Fiskfond Touch Of Taste`.
  Decision: `skaldjursfond` should match the shellfish fond family, e.g.
  hummer/räk/kräfta/krabba/mussla/skaldjur fonds that actually exist in offers.
  It should not fall back to ordinary `fiskfond`.

Real Stefan questions: none.

## Batch 3 review proposals - 2026-05-02

Direct-fix/reference entries:

- `Kycklingsteak med grillade potatishalvor och chilimajo`: ingredient
  `800 g Kyckling Steak` matched cooked/deli sliced chicken products such as
  `Kycklingbröst File Grillkryddad Skivad Guldfågeln` and
  `Hönsbröstfilé Pastramikryddad Skivad Guldfågeln`. Correct goods are raw
  chicken steak/lårfilé/bröstfilé/innerfilé or ordinary raw chicken pieces
  suitable for cooking; cooked deli slices are carrier/ready-product false
  positives. This repeats the raw-kycklingfilé vs deli-sliced chicken family.
  Accepted/fixed: `Kyckling Steak` normalizes to `kycklingsteak` and can fall
  back to raw chicken fillet where appropriate; cooked/deli sliced chicken stays
  blocked.
- `Tiramisù a la Toscana`: ingredient `1 dl starkt kaffe, gärna espresso`
  matched `Tripleshot Espresso Starbucks`. Correct goods: none in ordinary
  grocery matching. This is already brewed coffee/espresso to make at home, not
  beans, powder, capsules, instant coffee, or ready dairy coffee drink.
  Accepted/fixed: brewed coffee/espresso volume lines get no purchasable
  coffee-product match.
- `Tiramisù a la Toscana`: ingredient `10-12 st Vicenzi Savoiardo kex` matched
  generic crackers and salty/matkex products such as
  `Havssalt Salta Kex Garant`, `Ranch Matkex Göteborgs Kex`, and
  `Kex Focaccia Engelmanns`, while current Willys offers include
  `Savoiardikex Balocco`. Correct goods are savoiardi/ladyfinger biscuits;
  generic salty crackers should not satisfy this specialty biscuit.
  Accepted/fixed: `savoiardo`/`savoiardi`/ladyfinger wording maps to
  `savoiardikex`; generic `kex` products are blocked when the recipe asks for
  this specialty biscuit.
- `Rommarinerade bär med choklad- och kokosmousse`: ingredient
  `2 dl Kesella Vanilj` matched only `Kesella Kvarg Naturell 10% Arla Köket`
  while current Willys offers include `Kesella Vanilj Dessertkvarg 7,5%
  Dreamy Dessert` and other vanilla-quark products. Correct goods include
  vanilla Kesella/vaniljkvarg products; naturell Kesella can remain a pragmatic
  fallback, but exact vanilla products should not be missed when available.
- `Old fashioned`: ingredient `1 remsa apelsinskal (endast det gula)` matched
  `Apelsinskal Kanderat Dr Oetker`, while current Willys offers include fresh
  oranges such as `Apelsin Klass 1` and `Apelsiner Eko Klass 1 Garant Eko`.
  Correct goods for a cocktail peel/garnish are fresh oranges; candied baking
  peel is not the same ingredient.
- `Fredriks pasta med morötter och broccoli`: ingredient `1 st chili` matched
  `Peppar Grön Klass 1` / `Peppar Röd Klass 1`. Accepted correction:
  these Willys product names are fresh chili/pepper wording and should not be
  treated as bell pepper. Actual `paprika` products remain false positives for
  standalone chili.
- `Veganska hot cross buns`: ingredient `50 g Kanderade citrusskal` had 0
  matches even though current Willys offers include candied peel such as
  `Apelsinskal Kanderat Dr Oetker`. Correct goods are candied citrus/orange
  peel products.
- `Björnbärsdrink med citrussting`: ingredient `3 cl björnbärssaft` matched
  `Björnbär Frysta Garant` and `Björnbärs Marmelad Garant`. Correct goods are
  björnbärssaft/blackberry cordial or juice-drink products if available; berries
  and jam are not the requested drink ingredient.
- `Björnbärsdrink med citrussting`: ingredient `sodavatten` had 0 matches even
  though current Willys offers include naturell/original carbonated water and
  mineral-water products such as `Naturell Kolsyrat Vatten Pet Eldorado`,
  `Naturell Kolsyrat Vatten Burk Loka`, and
  `Original Kolsyrat Vatten Pet Ramlösa`. Correct goods are the
  carbonated/soda-water family.
- `Smal tomatsoppa med linser och sötpotatis`: ingredient
  `0.5 st Chilipeppar Röd` matched `Peppar Röd Klass 1`. Accepted correction:
  this is a valid fresh chili/pepper product name. Actual `paprika` products
  remain false positives for chilipeppar.
- `Havregrynsgröt`: ingredient `4 dl havregryn` matched
  `Tunn Havre Havreflingor Havsalt Wasa`. Correct goods are havregryn/oat-flake
  products, which also matched; crispbread/cracker carriers should not match
  standalone havregryn.
- `Pappardelle med salsiccia, vitt vin och tomat`: ingredient
  `0.5 st Chilipeppar Röd` matched `Peppar Röd Klass 1`. Accepted correction:
  this is valid fresh chili/pepper wording. Actual `paprika` products remain
  false positives for chilipeppar.
- `Fattiga riddare på stormkök`: ingredient
  `4 skivor vitt bröd (gärna några dagar gammalt)` matched
  `Bröd Sirap Dansukker`. Correct goods are white/sliced bread products, many of
  which also matched; bread syrup should not match bread.
- `Mathems stora frukostpaket`: ingredient `280 g Hårt tunnbröd` matched
  soft/broad bread products such as `Liba Original Tunnbröd Vitt 4-pack Liba
  Bröd` and `Sarek 8-pack Polarbröd`. Correct hard products such as
  `Tunnbröd Hårt Gene` and `Fiber Tunnbröd Gene` also matched; the issue is the
  soft/broad false positives for explicit hard tunnbröd.
- `Mathems stora frukostpaket`: ingredient `1 st Styckbröd` had 0 matches even
  though current Willys offers include bread-roll/småbröd/fralla products such
  as `Fröfralla Fryst/6p Garant`, `Grötfralla 10-pack Dahls Bageri`, and
  `Surdegsfralla Svenskt Dafgårds`. Correct goods are styckbröd/fralla/småbröd
  products.
- `Kycklingstroganoff`: ingredient `550 g Tärnad Kycklingbröstfilé` matched
  cooked/deli sliced chicken products such as
  `Kycklingbröst File Grillkryddad Skivad Guldfågeln` and
  `Hönsbröstfilé Pastramikryddad Skivad Guldfågeln`. Correct goods are raw
  diced/strimlad chicken breast/fillet or ordinary raw chicken fillet products;
  cooked deli slices are not raw chicken for cooking.
- `Kycklingstroganoff`: ingredient `2 dl Basmatiris` matched pure jasminris,
  långkornigt ris, and fullkornsris products such as `Jasminris`,
  `Jasminris Garant`, and `Långkornigt Ris Garant`. Correct goods are explicit
  basmati rice products; mixed products that explicitly include basmati, such
  as `Jasmin&basmati`, can remain acceptable or product-identity uncertainty
  rather than the core issue.
- `Solrossnitt med Västerbottensost`: ingredient `150 g Västerbottensost`
  matched `Västerbotten Philadelphia`. Current correct goods include
  Västerbottens hard/grated cheese products such as
  `Västerbottens Original Ost` and `Västerbottens Riven Ost 32%`;
  Västerbotten-flavored fresh cheese is not a hard/grated Västerbottensost
  match.
- `Avokado- och grapesallad med balsamvinäger`: ingredient
  `1-2 blond eller blod grapefrukter i skinnfria klyftor` had 0 matches even
  though current Willys offers include fresh grapefruit/grape fruit such as
  `Grape Röd Klass 1`. Correct goods are fresh grapefruit/grape fruit; do not
  use grapefruit drinks, snacks, household items, or other carriers.
- `Kokosmassa`: ingredient `ca 50 g kokosflingor` had 0 matches even though
  current Willys offers include coconut flake/shredded coconut products such as
  `Kokos Riven Eldorado`, `Kokos Riven Ekologisk Garant Eko`,
  `Kokos Rostade Flakes Garant`, and `Kokoschips Naturella Ekologiska Garant
  Eko`. Correct goods are kokosflingor/riven kokos/kokosflakes products.
- `Flankstek med belugalinssallad och örtolja`: ingredient
  `1 tsk grovmald svartpeppar` matched meat products where `grovmald` describes
  sausage texture, such as `Grill 1898 Grovmald Hirschmanchark` and
  `Chorizo Mild Grovmald Hirschmanchark`. Correct goods are grovmalen/malen
  svartpeppar spice products; meat products should not match the adjective
  `grovmald`.
- `Kycklingcurry-baguette`: ingredient `600 g kycklingfilé` matched cooked/deli
  sliced chicken products such as `Kycklingbröst File Grillkryddad Skivad
  Guldfågeln` and `Hönsbröstfilé Pastramikryddad Skivad Guldfågeln`. Correct
  goods are raw chicken fillet/breast/inner fillet or ordinary raw chicken
  pieces suitable for cooking; this repeats the raw-chicken vs deli-sliced
  chicken family.
- `Lax i hummerfondsås`: ingredient `3 dl Basmatiris` matched pure jasminris,
  långkornigt ris, and fullkornsris products such as `Jasminris`,
  `Jasminris Garant`, and `Långkornigt Ris Garant`. Correct goods are explicit
  basmati rice products; mixed products that explicitly include basmati, such
  as `Jasmin&basmati`, can remain acceptable or product-identity uncertainty
  rather than the core issue.
- `Senapsdressade rotfrukter med kryddiga korvar`: ingredient
  `100 g Salladsmix` had 0 matches even though current Willys offers include
  mixed salad products such as `Blandsallad Klass 1 Garant`,
  `Gourmetsallad Klass 1 Garant`, and `Blandad Sallad Melis`. Correct goods
  are mixed salad/salladsmix/blandsallad products, not ready meal salads.
- `Picknickmacka`: ingredient `8 brödskivor` matched `Bröd Sirap Dansukker`.
  Correct goods are sliced bread/bread-slice products, many of which also
  matched; bread syrup should not match bread. Same bread/carrier family as
  `Fattiga riddare på stormkök`.
- `Mexikansk majssoppa`: ingredient `8 medelstora tortillabröd` matched
  Spanish tortilla products `Tortilla med Lök Palacios` and
  `Tortilla Utan Lök Palacios`. Correct tortilla bread/wrap products also
  matched; the issue is those non-bread tortilla false positives.
- `10. CB-wook`: ingredient `320 g Färsk kycklingfilé` matched cooked/deli
  sliced chicken products such as `Kycklingbröst File Grillkryddad Skivad
  Guldfågeln` and `Hönsbröstfilé Pastramikryddad Skivad Guldfågeln`. Correct
  goods are raw chicken fillet/breast/inner fillet or ordinary raw chicken
  pieces suitable for cooking; this repeats the raw-chicken vs deli-sliced
  chicken family.
- `Frappé och islatte`: ingredient `3 msk snabbkaffepulver` had 0 matches even
  though current Willys offers include instant coffee products such as
  `Snabbkaffe Mellanrost Garant`, `Gold Snabbkaffe Nescafe`,
  `Snabbkaffe Mellanrost Eldorado`, and `Mörkrost Snabbkaffe Garant Eko`.
  Correct goods are snabbkaffe/instant coffee products.
- `Frappé och islatte`: ingredient `2 dubbla espresso` matched
  `Tripleshot Espresso Starbucks`. Correct goods are coffee/espresso inputs
  such as beans, ground coffee, capsules, or instant espresso; other
  coffee/espresso inputs in the match list can be acceptable, but ready dairy
  coffee drinks are not an espresso ingredient.
- `Frappé och islatte`: ingredient `4 msk nötcreme` had 0 matches even though
  current Willys offers include hazelnut/nut cream spread products such as
  `Hasselnötkräm Kakao Duo Dr Chef` and similar hazelnut cocoa spreads.
  Correct goods are nötcreme/hazelnut cream spread products.
- `Khoreshgryta med kyckling och citron`: ingredient `250 g Basmatiris`
  matched pure jasminris, långkornigt ris, and fullkornsris products such as
  `Jasminris`, `Jasminris Garant`, and `Långkornigt Ris Garant`. Correct goods
  are explicit basmati rice products; mixed products that explicitly include
  basmati, such as `Jasmin&basmati`, can remain acceptable or
  product-identity uncertainty rather than the core issue.
- `Khoreshgryta med kyckling och citron`: ingredient `600 g Kycklingfile`
  matched cooked/deli sliced chicken products such as
  `Kycklingbröst File Grillkryddad Skivad Guldfågeln` and
  `Hönsbröstfilé Pastramikryddad Skivad Guldfågeln`. Correct goods are raw
  chicken fillet/breast/inner fillet or ordinary raw chicken pieces suitable
  for cooking; this repeats the raw-chicken vs deli-sliced chicken family.
- `Lasagne med belugalinser`: ingredient `4 dl havredryck` matched flavored
  `Maple Walnut Havredryck Glutenfri Oddlygood`. Plain/neutral havredryck
  products remain accepted; strongly flavored oat drinks should not satisfy a
  plain cooking havredryck ingredient.
- `Grillade lammkotletter`: ingredient `1 kg Lammracks` had 0 matches even
  though current Willys offers include lammracks products such as
  `Lammracks Frenched Fryst Nya Zeeland Affco` and
  `Lammracks Singel Färsk Nya Zeeland Farmers`. Correct goods are lammracks
  offers.
- `Mexikansk bowl`: ingredient `1/2 röd chili` matched `Peppar Röd Klass 1`.
  Accepted correction: this is valid fresh chili/pepper wording. Actual
  `paprika` products remain false positives for standalone chili.
- `Sliders med cheddar och stekt lök`: ingredient
  `8 sliderbröd (minihamburgerbröd) eller 4 normalstora bröd` matched bread
  syrup and broad non-bun breads such as `Bröd Sirap Dansukker`,
  `Liba Original Tunnbröd Vitt 4-pack Liba Bröd`, and `Sarek 8-pack
  Polarbröd`. Correct goods are slider/hamburger buns such as
  `Brioche Sliders 6p Garant`.
- `Kebabsås`: ingredient `½ dl kolsyrad apelsindryck, t ex fanta` matched
  fresh oranges such as `Apelsin Klass 1`. Correct goods are orange soda/läsk
  products such as `Orange Fanta Läsk`, `Fanta Orange Zero Läsk`, or
  `Zingo Apelsin Läsk`.
- `Senap- och honungsfylld kycklingfilé`: ingredient
  `500 g Kycklingfile Fryst` matched cooked/deli sliced chicken products such
  as `Kycklingbröst File Grillkryddad Skivad Guldfågeln` and
  `Kycklingfilé Tunna Skivor Lönneberga`. Correct goods are frozen/raw chicken
  fillet/breast/inner fillet or ordinary raw chicken pieces suitable for
  cooking; this repeats the raw-chicken vs deli-sliced chicken family.
- `Jävligt Husman`: ingredient `1 st Svartpepparstekt Beyondburgare` matched
  black pepper spices such as `Svartpeppar Malen Burk Kockens`. Correct
  fallback goods, when exact Beyond products are absent, are plant-based/vegan
  burger patties such as `Vegan Burger Frysta 4x80g Garant`; pepper spices
  should not satisfy the burger ingredient.
- `Jävligt Husman`: ingredient
  `1 st Potato Burger buns från Korvbrödbagaren` matched burger patties,
  korvbröd, potato soup, and fries such as `Hamburgare 8x90g Frysta Prime
  Patrol`, `Korvbröd 8-pack Pågen`, `Potato Leek Soup Heinz`, and
  `Fries Sweet Potato Fryst Garant`. Correct goods are potato burger bun or
  burger bun products such as `Burger Bun Potato 4-pack Korvbrödbagarn`.
- `Jävligt Husman`: ingredient `200 g Frysta lingon` matched
  `Lingon 35% Eldorado`. Correct goods are frozen/raw lingon products such as
  `Lingon Ekologiska Frysta Garant Eko`, which also matched; lingon jam/sylt
  should not satisfy explicit frozen lingon.
- `Jävligt Husman`: ingredient `2 msk Koncentrerad svampfond` had 0 matches
  even though current Willys offers include mushroom-family fond such as
  `Kantarellfond Touch Of Taste`. Correct goods are concentrated mushroom fond
  products.
- `Jävligt Husman`: ingredient `0.5 dl Svartvinbärssaft` matched frozen black
  currants such as `Svarta Vinbär Ekologiska Frysta Garant Eko`. Correct goods
  are svartvinbärssaft products, which also matched; frozen berries should not
  satisfy the drink/cordial ingredient.
- `Porchettamacka med syrad salladskål`: ingredient
  `1 stor surdegsbaugette eller motsvarande` had 0 matches even though current
  Willys offers include baguette/sourdough-baguette products such as
  `Baguette Surdeg Cereal Dafgårds`, `Baguette Vete Bonjour`, and
  `Baguette Vete 4-pack Eldorado`. Correct goods are baguette or
  surdegsbaguette products.
- `Rostbiff på medelhavsvis`: ingredient `0.66 kg Rostbiff Pålägg` had 0
  matches even though current Willys offers include rostbiff/deli-sliced
  rostbiff products such as `Rostbiff Deliskivor Garant`,
  `Rostbiff i Skivor Sverige Garant`, and `Skeva Skivor Rostbiff Willys`.
  Correct goods are rostbiff or rostbiff pålägg/skivor products.
- `Kalkonkebab med raita`: ingredient `1 dl havregryn` matched
  `Tunn Havre Havreflingor Havsalt Wasa`. Correct goods are havregryn/oat-flake
  products, which also matched; crispbread/cracker carriers should not match
  standalone havregryn. Same family as the `Havregrynsgröt` entry above.
- `Kalkonkebab med raita`: ingredient `2 chili` matched `Peppar Grön Klass 1`
  and `Peppar Röd Klass 1`. Accepted correction: these are valid fresh
  chili/pepper product names. Actual `paprika` products remain false positives
  for standalone chili.
- `Tastelines lussebullar`: ingredient `5 dl Standardmjölk` matched flavored
  non-plain milk carriers such as `Rosa Jordgubb Mjölkdryck 1% Arla Ko`.
  Correct goods are plain milk/standardmjölk products; flavored milk drinks
  should not satisfy a plain baking milk ingredient. Same family as earlier
  milk-carrier entries.
- `Veganska Animal Style Fries`: ingredient
  `50 g Violife Smokey Flavour, Block` matched chicken-flavour noodle products
  such as `Chicken Flavou Pho Ga Nudlar Vifon`. Correct goods are vegan smoked
  Violife/block products such as `Block Smoked Flavour Vegansk Violife`;
  chicken-flavour noodles are carrier false positives.
- `Veganska Animal Style Fries`: ingredient
  `150 g Violife Mature Cheddar, Block` matched dairy cheddar products such as
  `Cheddar Vit Garant`, `Cheddar Block Hårdost 32 % Wernerssons`, and
  `Cheddar Extra Mature 14 Månader Cathedral City`. Because the recipe and
  ingredient are explicitly vegan/Violife, correct goods are vegan
  Violife/vegan cheddar block products such as
  `Block Cheddar Flavour Vegansk Violife` or
  `Epic Mature Cheddar Flavour Vegansk Violife`.
- `Veganska Animal Style Fries`: ingredient `300 g Veganskt bacon` had 0
  matches even though current Willys offers include
  `Vegobacon Klippta Skivor Vegansk Eldorado`. Correct goods are vegan bacon
  products.
- `Morotskakesmoothie`: typo ingredient `2 dl växtbaserad mjölkryck` had 0
  matches even though current Willys offers include plant-based drink products
  such as havredryck, sojadryck, and mandeldryck. The typo should normalize to
  växtbaserad mjölkdryck/dryck; correct goods are plant-based milk/drink
  products.
- `Kycklingfilé med citronsmak och dragonsås`: ingredient `4 st Kycklingfile`
  matched cooked/deli sliced chicken products such as
  `Kycklingbröst File Grillkryddad Skivad Guldfågeln` and
  `Kycklingfilé Tunna Skivor Lönneberga`. Correct goods are raw chicken
  fillet/breast/inner fillet or ordinary raw chicken pieces suitable for
  cooking; this repeats the raw-chicken vs deli-sliced chicken family.
- `Zucchinisoppa med potatis och curry`: optional ingredient `ev bröd` matched
  `Bröd Sirap Dansukker`. Correct bread products also matched; bread syrup
  should not satisfy optional bread. Same bread/carrier family as earlier
  entries.
- `Grön smoothie och knäcke med färskost och paprika`: ingredient
  `1.5 dl Havredryck Naturell` matched flavored
  `Maple Walnut Havredryck Glutenfri Oddlygood`. Plain/neutral havredryck
  products remain accepted; strongly flavored oat drinks should not satisfy an
  explicit naturell havredryck ingredient.
- `Vegansk Philly Cheese Steak`: ingredient `1 tsk Rökt paprikapulver` had 0
  matches even though current Willys offers include `Rökt Paprika Kockens`.
  Correct goods are smoked paprika/rökt paprikapulver spice products.
- `Vegansk Philly Cheese Steak`: ingredient `0.5 dl öl` had 0 matches even
  though current Willys offers include beer/folköl/lättöl products such as
  `Ljus Lager 3,5% Folköl Burk Falcon`, `Gränges 2,1% Lättöl Burk
  Grängesberg`, and alcohol-free lager products. Correct goods are beer/öl
  cooking inputs.
- `Vegansk Philly Cheese Steak`: ingredient `2 st "halva" baugetter` had 0
  matches even though current Willys offers include baguette products such as
  `Baguette Vete Bonjour`, `Baguette Vete 4-pack Eldorado`, and
  `Baguette Halv Vete Bonjour`. Correct goods are baguette products.
- `Potatisbullar med bejkonfräs och lingon`: ingredient
  `90 g Vegetariskt bacon` had 0 matches even though current Willys offers
  include `Vegobacon Klippta Skivor Vegansk Eldorado`. Correct goods are
  vegetarian/vegan bacon products.
- `Honungslax med citron och ingefära`: ingredient
  `0.5 st Chilipeppar Röd` matched `Peppar Röd Klass 1`. Accepted correction:
  this is valid fresh chili/pepper wording. Actual `paprika` products remain
  false positives for chilipeppar.
- `Majsplättar med korvtorn och färgsprakande sallad`: ingredient
  `2 dl Standardmjölk` matched flavored non-plain milk carriers such as
  `Rosa Jordgubb Mjölkdryck 1% Arla Ko`. Correct goods are plain
  milk/standardmjölk products; flavored milk drinks should not satisfy a plain
  cooking/batter milk ingredient. Same family as earlier milk-carrier entries.
- `Pulled pork i ugn`: ingredient `1 msk koriander` had 0 matches even though
  current Willys offers include coriander spice products such as
  `Koriander Malen Burk Kockens` and `Korianderblad Burk Kockens`. In this
  spice-rub context, correct goods are dried/ground coriander spice products.
- `Lökpaj`: ingredient `2 msk valfri mjölk ex. havredryck` matched flavored
  `Maple Walnut Havredryck Glutenfri Oddlygood`. Plain milk or plain/neutral
  havredryck products remain accepted; strongly flavored oat drinks should not
  satisfy a savory pie milk ingredient.
- `Veganska wraps med sötpotatiskräm`: ingredient `1 tsk koriander, fryst`
  had 0 matches even though current Willys offers include
  `Koriander Finhackad Fryst Garant`. Correct goods are frozen/fresh coriander
  products.
- `Veganska wraps med sötpotatiskräm`: ingredient `0.5 st röd chili` matched
  `Peppar Röd Klass 1`. Accepted correction: this is valid fresh chili/pepper
  wording. Actual `paprika` products remain false positives for standalone
  chili.
- `Veganska wraps med sötpotatiskräm`: ingredient `4 st tortillabröd` matched
  Spanish tortilla products `Tortilla med Lök Palacios` and
  `Tortilla Utan Lök Palacios`. Correct tortilla bread/wrap products also
  matched; the issue is those non-bread tortilla false positives.
- `Chicken tacos med syrlig mangosås`: ingredient `0.5 st Huvudsallat` had 0
  matches even though current Willys offers include `Huvudsallad Klass 1` and
  iceberg/head lettuce products. Correct goods are huvudsallad/head lettuce
  products.
- `Chicken tacos med syrlig mangosås`: ingredient `320 g Tortilla` matched
  Spanish tortilla products `Tortilla med Lök Palacios` and
  `Tortilla Utan Lök Palacios`. Correct tortilla bread/wrap products also
  matched; the issue is those non-bread tortilla false positives.
- `Chicken tacos med syrlig mangosås`: ingredient `550 g Strimlad kyckling`
  matched cooked/deli sliced chicken products such as
  `Kycklingbröst File Grillkryddad Skivad Guldfågeln` and
  `Kycklingfilé Tunna Skivor Lönneberga`. Correct goods are raw strimlad
  chicken or ordinary raw chicken fillet/pieces suitable for cooking; this
  repeats the raw-chicken vs deli-sliced chicken family.
- `Chicken tacos med syrlig mangosås`: ingredient
  `0.5 st Chilipeppar Färsk` matched `Peppar Grön Klass 1` and
  `Peppar Röd Klass 1`. Accepted correction: these are valid fresh chili/pepper
  product names. Actual `paprika` products remain false positives for
  chilipeppar.
- `Kolja i kokossås med blomkålsris`: ingredient `0.5 st Chilipeppar Röd`
  matched `Peppar Röd Klass 1`. Accepted correction: this is valid fresh
  chili/pepper wording. Actual `paprika` products remain false positives for
  chilipeppar.
- `Rostbiff`: ingredient `1-1,5 kg rostbiff` matched ready/deli sliced
  rostbiff products such as `Rostbiff Deliskivor Garant`,
  `Rostbiff i Skivor Sverige Garant`, and `Skeva Skivor Rostbiff Willys`.
  Correct goods for this roast recipe are raw roast-beef/innanlår/nötstek style
  products such as `Rostbiff Innanlår Prime Patrol`; deli sliced roast beef is
  not a raw roast for cooking.

Batch 3 user-decision references - 2026-05-03:
- `Kesella Vanilj`: correct goods are explicit vanilla Kesella/vanilla kvarg
  products such as `Kesella Vanilj Dessertkvarg` and plain `Vanilj Kvarg`.
  Naturell Kesella/kvarg and berry/elderflower vanilla variants are not the
  requested vanilla product.
- `apelsinskal` in cocktail/zest context should match fresh orange products
  such as `Apelsin Klass 1`; `kanderade/syltade citrusskal` should instead
  match candied peel such as `Apelsinskal Kanderat`.
- Fresh `grön/röd peppar` in recipe text means chili pepper, not bell pepper.
  `Peppar Grön/Röd Klass 1` is acceptable as fresh chili wording; paprika
  products are not.
- `björnbärssaft` and `svartvinbärssaft` are saft/cordial requirements. They
  should not fall back to berries, marmalade, juice, or flavored sparkling
  water; `Svart Vinbärs Extra Koncentrerad Saft` is a correct saft match.
- `sodavatten` should match plain/naturell/original sparkling water only, not
  flavored sparkling water.
- `havregryn` should match oat/oat-flake products, not crispbread/cracker
  carriers that merely mention oats.
- `hårt tunnbröd` is specific hard tunnbröd, e.g. Gene hard/fiber tunnbröd.
  It should not fall back to soft Liba/Sarek-style tunnbröd.
- `styckbröd` may match bread rolls/småbröd/fralla products.
- `basmatiris` remains in the generic `ris` umbrella; do not make it an exact
  basmati-only requirement.
- `kokosflingor` can match `Kokos Riven`, coconut flakes, and coconut chips.
- `grovmald svartpeppar` is pepper spice; `grovmald` as a meat descriptor is
  not an ingredient keyword.
- `snabbkaffepulver` should match plain instant coffee products, not flavored
  cappuccino/3-in-1 instant drink mixes. Brewed coffee/espresso ingredient
  lines such as `2 dubbla espresso` should remain at zero purchasable matches.
- `nötcreme` should match nut/hazelnut cream spread such as
  `Hasselnötkräm Kakao Duo`.
- `Havredryck Naturell` should match plain oat drink, not maple/walnut or
  other flavored oat drinks.
- `sliderbröd`, `minihamburgerbröd`, `burger buns`, and
  `Potato Burger buns` are hamburger/slider bread products. They should not
  match patties, fries, soup, or hot-dog bread.
- `kolsyrad apelsindryck` / `Fanta` is orange soda; fresh oranges must not
  match that drink requirement. It is acceptable if the DB filters some soda
  products out and the result is zero.
- `Beyondburgare` is an extremely specific product request. Do not fall back
  to generic vegan burgers, ordinary burgers, or pepper/spice matches.
- `Frysta lingon` should match frozen/raw lingon, not lingonsylt or `Lingon
  35%` jam-style products.
- `Koncentrerad svampfond` can match mushroom/chanterelle fond, e.g.
  `Kantarellfond Touch Of Taste`.
- `baguette` / `surdegsbaguette` / typo `surdegsbaugette` should match
  baguette products, including mini/half baguettes; garlic baguettes remain a
  separate flavored/prepared product.
- `Rostbiff Pålägg` should match sliced deli roast beef such as
  `Rostbiff Deliskivor`, `Rostbiff i Skivor`, and `Skeva Skivor Rostbiff`.
  Raw `rostbiff` roast recipes should instead match raw roast-beef cuts such
  as `Rostbiff Innanlår`, not deli slices.
- Explicit `Violife` cheese ingredients must stay on Violife/vegan cheese
  variants and respect the named variant, e.g. smoked block or mature cheddar.
  Ordinary dairy cheddar and unrelated `flavour` products are false positives.
- `veganskt`/`vegetariskt`/`laktosfritt`/similar explicit recipe labels are
  one-way strict: if the recipe asks for the label, only products carrying that
  label/family should match. Ordinary unlabeled recipes may still receive
  vegan/vegetarian/lactose-free alternatives where otherwise compatible.
- `veganskt bacon` / `vegetariskt bacon` should match vegobacon products.
- `växtbaserad mjölkryck` is a typo for plant-based milk/drink and should
  normalize to the plant-drink family.
- `öl` for cooking can match beer/lättöl/folköl/alcohol-free lager style beer
  products, but not ginger beer soda.
- `1 msk koriander` is spice context and should match ground/dried coriander,
  not fresh/frozen herb. `koriander, fryst` should match frozen/fresh herb
  form, not ground spice.
- `Huvudsallat` means `Huvudsallad Klass 1`, not generic salad mixes.
- `guacamole-mix` is a seasoning/mix requirement; ready guacamole is not a
  match unless the recipe asks for guacamole itself.
- `kebab`, `kebabkött`, and `kebabskav` should match kebab meat products, not
  kebab sauce, kebab bread, or kebab pizza.
- `vetetortillas` may match wheat/mixed wheat tortillas. Corn-only tortillas
  are not a match for explicit wheat tortilla wording, although generic
  tortillas may match corn tortillas.
- `Havrebaserad matlagning` and `Soyabaserad matlagning` are plant-based
  cooking-cream requirements. They should not match ordinary dairy cream or
  crème fraîche carriers.

Real Stefan questions: none.

Batch 4 checkpoint references - 2026-05-03:
- `600 g Kycklingfile`: correct goods are raw chicken fillet family products.
  Deli/pålägg-style sliced chicken products such as `Kycklingfilé Tunna Skivor
  Lönneberga` are not matches, while raw thin-sliced/minutfilé products remain
  acceptable.
- `Zeta Mozzarella Di Bufala Campana`: correct goods are fresh mozzarella and
  buffalo mozzarella products such as `Mozzarella Bufala Campana`. Grated
  mozzarella, vegan mozzarella-flavour slices/blocks, and other cheese carriers
  are not matches for an explicit fresh/bufala mozzarella salad ingredient.
- `1 msk Dadelsirap`: correct goods are date syrup products such as
  `Dadelsirap Zeinas`; do not broaden this to date snacks or date-flavored
  carriers.
- Generic dessert garnish `bär` may match fresh/frozen berry family products
  such as blueberries, blackberries, raspberries, strawberries, currants, and
  lingonberries, while berry-flavored carriers remain blocked.
- `citronmeliss`: correct goods are fresh citronmeliss herb products such as
  `Citronmeliss Klass 1 Garant`; teas or flavored carriers that merely contain
  citronmeliss are not matches.

Real Stefan questions: none.

Batch 4 review references - 2026-05-03:
- Repeated `vetemjöl`/`vetemjöl special` and
  `mellanmjölk`/`standardmjölk` ingredients matched beer/folköl/lager products
  because the short keyword `öl` matched inside longer words such as `mjöl`.
  Decision/fix: 1-2 character keywords must match whole recipe words for both
  live matching and term-index routing. Standalone `öl` for cooking remains a
  beer match.
- Raw `kycklingfilé`/`kycklinglårfilé` ingredients should match raw chicken
  fillet/cut products. Deli/pålägg-style products such as
  `Kycklingfilé Tunna Skivor Lönneberga` are not matches.
- `Nötpaj med pepparkaka`: ingredient
  `blandade nötkött, t ex hassel, valnöt och pinjenöt` is a scraped/wording
  issue where the examples clearly mean nuts. Correct goods are nut products
  such as hazelnuts, walnuts, and pine nuts; beef products are false positives.
- `Västerbottensill`: `5-minuterssill` should match herring/sill products if
  present; `Ansjoviskrydda Sill Garant` is a spice mix and not the fish.
- Fresh red chili wording such as `hackad färsk röd chili` should route to
  fresh chili produce, not stay at zero when fresh chili offers exist.
- `Nigiri-sushi`: `fiskfilé gärna lax eller färsk tonfisk` is sushi fish
  context. Prefer salmon/tuna/sushi-grade fish; frozen generic white fish is
  not an acceptable fallback.
- `Vildsvinsfärs` is mince and should not match whole wild-boar cuts such as
  vildsvinsytterfilé.
- Explicit fresh mozzarella/bufala salad ingredients stay on mozzarella/bufala
  family products rather than ready-meal carriers. `Riven` is not a hard
  product-form requirement; ordinary mozzarella can be grated by the cook.
- `machesallad`/`maché` should normalize to mache salad offers.
- Exact branded/specific vegan burger ingredients such as `Beyond Burgare`
  should stay on Beyond/explicitly requested products, not ordinary cheese or
  generic burger products.
- `Svejkon` is a vegan bacon synonym and should route to vegobacon products.
- In burger context, a generic `Bröd` ingredient may route to hamburger/slider
  buns rather than broad everyday bread.
- `tranbärsjuice` should route to cranberry juice/drink products.
- `citronmeliss` should match fresh citronmeliss herb products, not teas or
  flavored carriers.
- `Chili Explosion` is an exact spice product/alias and should route to the
  corresponding Santa Maria-style chili explosion grinder if present.
- `Zeta Röda linser Ekologiska` should route to red lentil products.
- `Tomatsås till pizza` / pizza sauce should match pizza-sauce products, not
  pizza bases or ready/frozen pizzas.
- `hushållsfärs eller nötfärs` should match beef or household pork/beef mince;
  chicken, vegetarian, sausage, or other mince families are false positives.
- `Feferoni` should match pickled feferoni/kebabfeferoni pepper products, while
  ready sandwiches/pizzas carrying feferoni stay blocked.
- `Jamaican jerk spices` should not match unrelated Indian spice blends such as
  garam masala or tandoori when jerk seasoning is unavailable.
- Exact snack/candy ingredients such as `Salta Pinnar` and
  `Godispåse - Non stop` should route to those snack/candy products if current
  offers exist.
- `vodka` as a spirit ingredient should not match salsa/condiment products such
  as `Salsa Pineapple Vodka El Taco Truck`.

Real Stefan questions: none.

Batch 5 checkpoint references - 2026-05-03:
- Missing cache rows for intentionally filtered buffet/party/menu recipes such
  as `Mathems midsommarbuffé för 8 personer` are accepted cache exclusions, not
  recipe-level false negatives.
- `Grapefrukt` should match fresh grapefruit/grape produce such as
  `Grape Röd Klass 1`.
- `Apelsinsaft` in a drink/juice volume context may match orange juice products
  such as `Apelsinjuice Bravo` and `Apelsinjuice Ekologisk Koncentrat`.

Real Stefan questions: none.

Batch 5 review references - 2026-05-03:
- Non-food prep aids in recipe ingredient lists, e.g. `Bakplåtspapper` and
  `Tandpetare`, are accepted zero food matches unless review scope is
  explicitly expanded to household items.
- `Riven mozzarella` may match ordinary mozzarella that can be grated by the
  cook. Do not make `riven` a hard product-form requirement for cheese.
- `hjortronsylt` should match cloudberry jam if present; it should not fall
  back to strawberry, raspberry, lingonberry, or other jams.
- Plain/savory `turkisk havregurt` should not match fruit-flavored havregurt.
- `grön currypasta` should route to green curry paste/curry products such as
  `Green Curry Paste Garant`; this is the same direct-fix family as earlier
  curry-paste decisions and should not fall back to red/yellow/plain curry.
- `brötchen`/`flerkornsbrötchen` are bread rolls/frallor, not crispbread,
  pasta, or unrelated carriers.
- Raw `kycklingfilé`/`kycklingbröst` remains raw chicken fillet/cut products;
  `Kycklingfilé Tunna Skivor Lönneberga` is deli sliced chicken and not a raw
  fillet match.
- `müsli`/`musli` should route to muesli/cereal products.
- `kalkonbröstfilé` is turkey breast fillet and should not match turkey thigh
  fillet.
- `dumplingdeg`/`gyoza skin` should match dumpling wrapper dough such as
  `Gyoza Skin Deg Fryst Twin Dragon`, not ready dumplings.
- `frysta blåmusslor` should route to suitable mussel/blåmussla products.
- `konserverade persikohalvor` should match canned peach halves, while candy
  peach ingredients such as `godis persikor` should not match fresh/canned
  fruit.
- Frozen Provencal herb blends should match herb products, not meat/sausage
  products that contain `provencal` as a flavor/style.
- Exact vegan/seaweed burger ingredients such as `VegMe Seaweed Burgare`
  should not fall back to chicken, meat, Quorn, or ordinary burger products.
- Exact brand/specialty dessert ingredients such as `After Eight` should route
  to that candy family if offers exist; do not replace them with generic mint
  or chocolate unless policy is explicitly broadened.
- Normal single-dish recipes with no cache row, e.g. `Ciabatta med
  buffelmozzarella och salami`, are cache/routing/materialization issues when
  live offers clearly match several ingredients.
- `osaltade pistagenötter` should not match salted pistachios.
- `fläderblomssaft` should route to elderflower saft/cordial products.
- Standalone `vallmofrö` should match poppy seeds, not crispbread or bread
  carriers that merely contain poppy seeds.
- Explicit `mjukt tunnbröd` should not match hard/crisp tunnbröd variants.
- `pickles`/`cornichons` should route to pickled cucumber/cornichon products.
- `läsk` as a recipe ingredient should route to soda/soft-drink products.
- `chilipeppar-pulver` and chili powder wording should match chili powder or
  flakes, not meat or soy/sauce carriers.
- `krossat vete eller råg` should route to grain-crush products such as
  vetekross/rågkross.
- Explicit fat constraints such as `riven hårdost max 17%` should avoid
  high-fat cheese proposals.
- `storkornskaviar röd` should stay on red roe/stenbitsrom-style products, not
  Kalles tube caviar.
- `majsvälling` should route/cache to majsvälling products when live matcher
  can find them.
- `muscovadosocker` should route to muscovado sugar products.
- `glutenfri vegansk mjölmix` requires gluten-free and vegan/milk-free baking
  mix products; ordinary flour mixes are not enough.
- `knipplök` can match salladslök/knippe-style onion products.
- `lagrad ost eller ädelost` should match aged cheese or blue cheese, not mild
  broad cheese or vegan cheese fallback.

Real Stefan questions: none.

Batch 6 checkpoint references - 2026-05-03:
- Tapenade wording such as `Zeta Tapenade Paprika & Oliver` should route to the
  tapenade family. Exact requested flavor is preferred when present; ordinary
  olive/caper tapenade is an acceptable pragmatic fallback unless the recipe
  makes the flavor critical.
- `torkad chili (chiliflakes)` should normalize to chili flakes/chiliflingor
  products such as `Chili Flakes Burk Kockens` and `Gochugaru Chili Flakes
  Kockens`.
- Explicit `Färska lasagneplattor` should require or strongly prefer fresh
  pasta sheets such as `Lasagneplattor Färsk Pasta Garant`; dry shelf
  lasagneplattor are not the same form.

Real Stefan questions: none.

Batch 6 review references - 2026-05-03:
- Raw `kycklingfilé` ingredients continue to exclude deli sliced chicken such
  as `Kycklingfilé Tunna Skivor Lönneberga`.
- Explicit `riven mozzarella` / `riven ost mozzarella` should stay in the
  mozzarella family, but `riven` itself is preparation/use and may match
  non-riven mozzarella products. Conversely, generic `ost` may match riven
  cheese products.
- `mörk chokladkaka` should route to dark chocolate bar/baking chocolate
  products.
- `pressad apelsinsaft` may route to orange juice or fresh orange products in
  cooking/baking contexts.
- Singular `dadel` should match date/dadlar products.
- `kavring` should route to kavring bread products.
- `fläsksida` should match pork belly/sidfläsk cooking cuts, not unrelated
  pork products.
- `lagrad ost` should require aged/lagrad cheese rather than mild/generic or
  vegan cheese fallback.
- `Tabasco Habanero`/habanero hot sauce wording should route to habanero hot
  sauce products and block fresh chili fallback.
- `rökextrakt` should route to liquid smoke/rökarom products such as `Liquid
  Smoke`, not cracker/kex carriers.
- Volume-context `rom` in sweet/cooking contexts, e.g. `2 msk rom`, is spirit
  rum and should not match fish roe.
- `Fläskytterfilé` should stay pork/fläsk, not vildsvin or other animal cuts.
- `vaniljyoghurt` should require vanilla yoghurt, not plain/naturell yoghurt.
- Explicit `tryffelburrata` should not fall back to plain burrata.
- Standalone `strössel` should route to sprinkles products.
- `risnudlar` should not match flavored instant noodle meals.
- `gari` / `inlagd ingefära` should route to pickled ginger if available, not
  jams or unrelated sweet products.
- `konserverade körsbärstomater` should match canned/preserved tomato products,
  not fresh baby plum/cocktail tomatoes.
- `inläggningssill` / `5-minuterssill` should match herring/sill products if
  available and block seasoning carriers such as ansjoviskrydda.
- `vodka` as a spirit ingredient should not match salsa/condiment products.
- `riven veganost` should stay on cheese-like vegan cheese products; grated or
  block forms are both acceptable because `riven` is preparation/use. Creamy or
  spread products are not the same cheese role.
- `kronärtskocksbottnar på burk` should route to canned/jar artichoke
  bottoms/hearts.
- `morotssylt` should not fall back to non-carrot jams; zero matches is better
  if no carrot jam exists.
- `tryffelolja` should match truffle oil products such as `Olivolja Tryffel`.
- `mache`/`mâche`/`machesallad` should normalize to mâche salad offers.
- `Gröna linser förkokta` should route to cooked/ready green lentil products.
- `tomatsås arrabbiata` should require an arrabbiata/tomato sauce product, not
  filled pasta or ready carriers.
- `grön feferoni` should route to pickled feferoni/kebabfeferoni products.
- `jordgubbsglass` should require strawberry ice cream, not jam or drinks.
- Exact candy/brand ingredients such as `Lakrisal` should route to that candy
  family if present.
- `maränger` should route to marängtoppar/marängdroppar or equivalent meringue
  products.
- `mozzarella till pizza` should match mozzarella cheese, not finished pizza
  products.
- `tomatpesto` should prefer/require red/tomato pesto, not green/genovese
  pesto.
- `Vegetarisk File` should route to vegetarian/Quorn-style fillets.
- `surdegskakor, ca 12 skivor` should route to soft sliced sourdough bread
  equivalents.
- `kräftor` should route to edible shellfish/crayfish family products, in line
  with the accepted shellfish-family policy, and block cheese/sill/cat-food
  carriers.

Real Stefan questions: none.

Batch 7-9 gatekeeping notes - 2026-05-03:
- Reviewed ranks 601-900 with three Codex workers. After orchestrator
  corrections, the DB issue counts are batch 7: 52, batch 8: 63, batch 9: 51.
- Verification follow-up: a deterministic 60-row spot check was run after the
  parallel worker run: 10 clean + 10 issue rows from each batch. Sampled issue
  rows were mostly coherent, but sampled clean rows had clear misses. Corrected
  DB counts for ranks 632, 676, 723, 727, 865, 876, and 878. Conclusion:
  parallel-run output is useful as a proposal, but not safe to accept without
  sequential orchestration plus local verification.
- Clean misses found by verification: explicit `svarta/vita/skalade sesamfrön`
  accepted wrong sesame color/hulled forms; fresh/raw beetroot accepted
  förkokta/inlagda beet products; explicit `extra fast tofu` or
  `tofu, fast eller silkes` accepted crispy/smoked/fried/marinated tofu.
- Applied matcher regressions after verification: sesame seed color/hulled
  requirements, beetroot fresh/pre-cooked/jarred directionality, and explicit
  fast/plain/silken tofu blocking prepared/flavored tofu are now covered by
  `tests/test_matching_sanity.py`.
- Corrected agent over-counts: fresh Willys `Peppar Röd/Grön Klass 1` is valid
  for fresh chili/chilipeppar/chilifrukter wording; brewed `kaffe`/`starkt
  kaffe` as recipe liquid is an accepted zero-match grocery item; whole/ground/
  coarse ordinary pepper forms are interchangeable; generic `köttfärs` may
  include compatible plant-based mince alternatives when the recipe is not
  explicitly meat-only.
- High-confidence direct-fix families from these batches: citrus juice wording
  (`citronsaft`/`citronjuice`/`limejuice`), `ingefärsmarmelad`,
  `sötmandel spån` -> `mandelspån`, pistage/pistasch spelling, `krondill` ->
  standalone dill, canned/in-water `kantareller`, English `Oyster Sauce`,
  `kavring`, `ruccola`, `machesallat`, `körvel`, `pistasch`, `TUC`, and
  `Oreo`.
- High-confidence FP families from these batches: flavor/carrier leakage such as
  `grillolja lime` -> fresh lime, tomato/classico `pastasås` -> cheese sauces,
  `gochujang` paste -> gochujang chicken skewers, balsamico/crema flavors ->
  fresh citrus, riven/generic cheese -> creamy spread/grillost/vitost products,
  and standalone seeds/herbs/spices -> bread/snack/cheese products carrying the
  same flavor word.
- Specific form/specialty candidates to preserve for manual fix review:
  explicit vegan products must not match meat/dairy; fresh/raw beets, peaches,
  pineapple, salmon, chicken, turkey, veal, and pork cuts should not fall into
  preserved/smoked/cured/prepared/wrong-cut products; `tryffelolja` and
  `tryffelsalami` need the requested truffle specialty; `röd kebabsås` should
  not match white/garlic kebab sauces; `matjesill` should not fall back to
  ordinary/inlagd/senap sill.
- Resolved Stefan decision from batch 8 rank 704, `Dillkött`: ingredient
  `ca 1 kg kalvkött med ben` may accept raw boneless veal cuts when no bone-in
  veal is available, as long as the product is still the correct meat type
  (`kalv`). Correct fallback goods include `Kalvhögrev i Bit Import Prime`,
  `Kalvbiff Import Prime`, `Kalventrecote Import Prime`, and
  `Kalvschnitzel Import Prime`; wrong animal, mince, sausage, sylta, stock, and
  other processed/cooked carriers remain invalid.

Batch 10 checkpoint notes - 2026-05-03:
- Rank 901-906 checkpoint was reviewed with the stricter Codex precedent
  prompt. The worker produced no Stefan questions and used the prior batches as
  policy context.
- Direct fixes accepted/applied from rank 903
  `Kalkonsmörgås med äpple och skott`: explicit `brödskiva` should not widen
  to flatbread/bagel/somun/bun-style bread products; `pepparrotsvisp, på tub`
  should require prepared pepparrotsvisp rather than fresh/riven horseradish;
  `1 skiva rökt kalkonbröst` should stay in smoked/sliced deli turkey products
  and block raw turkey fillet/thigh cuts.
- Batch 10 grouped root fixes applied after full review: plain plant drinks
  block flavored drink variants; explicit plant-based burgers/fats block
  meat/dairy fallbacks; `hjortronsylt` does not fall back to ordinary jam;
  fresh/canned/color produce constraints were tightened for peach, cherry
  tomatoes, zucchini, and asparagus; glass/rice noodles block ordinary pasta
  and flavored instant meals; gochujang blocks prepared chicken carriers; raw
  ribs, boneless pork neck, and plain chicken legs block smoked/marinated/bone-in
  prepared products; and missing current-offer routing was added for sugar
  snaps/sockerärtor, maché, Dumle, torrmjölk/mjölkpulver, basil pesto, and
  cornichon/pickle wording.

Batch 11 gatekeeping notes - 2026-05-03:
- Batch 11 was accepted after orchestrator correction at 71 issues. Agent
  over-counts removed from DB: fresh/frozen ordinary vegetables/herbs are
  accepted substitutions, plain milk family remains broad across fat/lactose
  variants, and ordinary pepper forms are interchangeable.
- Applied direct FN fixes: `pickles`/`smörgåspickles` route to inlagd gurka;
  `polenta` routes to majsmjöl; `minikrustader`/`croustades` route to
  krustader; `salladsärtor` and `sockerärtor`/sugar snaps are the same practical
  family; typo `haricoverts` routes to haricots verts; `quornfärs` may use
  compatible vegofärs; `maränger` route to marängtoppar/marängdroppar; exact
  `Oreo` dessert/cookie ingredients route to Oreo cookie packs.
- Remaining batch 11 direct-fix families to watch in later batches: explicit
  truffle cheese/oil specialties should not fall back to plain variants; dried
  mushrooms should not match frozen/fresh mushrooms; explicit fresh sausage
  should avoid cured/deli sausage; exact plant-based/vegan dairy/fat wording
  should not fall back to ordinary dairy; and fresh smördeg on roll should not
  fall into frozen sheets or filled pastry products.

Batch 12 gatekeeping notes - 2026-05-03:
- Batch 12 was accepted after orchestrator correction at 35 issues. Over-counts
  removed from DB: current Willys `Peppar Röd/Grön Klass 1` remain valid
  fresh-chili products; long pasta ingredients such as `Tagliatelle` and
  `Gotlandsspagetti` already had refreshed cache coverage; and `frysta humrar`
  already matched frozen lobster in cache.
- Direct-fix families to carry forward: riven/cooking cheese should block
  creamy spreads, grillost, and salad-white/vitost carriers while preserving
  ordinary hard/grated cheese and compatible grated vegan cheese; sauce-form
  `chilisås` should not match dry chili flakes/powder; explicit
  `mörk choklad` should require dark/cacao/baking-dark chocolate; explicit
  `naturell tempeh` should not match smoked tempeh; exact candy/snack/pantry
  names such as `Daim`, `puffat ris`, and chili oil need current-offer routing;
  tomato/classico pasta sauce should not match cheese/svamp/ost sauces; cooked
  or deli-sliced chicken should not match raw chicken ingredients; liquor `rom`
  should not match fish roe; and explicit fresh filled pasta should avoid ready
  bowls or wrong filling families.

Batch 13 gatekeeping notes - 2026-05-03:
- Batch 13 was accepted after orchestrator correction at 65 issues. Over-counts
  removed from DB: ordinary fresh potato wording must stay broad across
  fast/mjölig/färskpotatis/delikatess/normal fresh potato variants. Corrected
  ranks: 1210, 1241, 1250, 1259, 1263, 1274, and 1297.
- Direct-fix families to carry forward: preserved/canned whole carrots should
  not match plain fresh carrots; white chocolate buttons should not match milk/
  dark buttons; broad fruit/berry garnish needs acceptable current fresh/frozen
  fruit or berry routes; exact citrus juice indexes must expose lemon/lime
  offers; flavored/carrier products such as vallmofrö knäckebröd,
  ingefärsmarmelad, tomatsalsa/vodka salsa, kanelglass, and pulled oats tomato
  should not satisfy standalone seed/spice/salsa/plain-base ingredients.
- Other batch 13 fix candidates: explicit egg noodles should avoid non-egg
  noodles; honey-roasted nuts should not fall back to plain/salted nuts;
  coriander seed should not match fresh herb; dried green lentils should not
  match cooked/preserved lentils; Fish&Crisp/fish-and-chips style product names,
  raw deer/venison substitute routing, fruit tea, vanilla extract, tikka masala
  spice mix, pistachio, and Oreo/light chocolate need exact current-offer
  handling or confirmed no-current-offer handling.

Matcher layer parity import status - 2026-05-05:
- First Batch 14 parity slice imported into
  `app/languages/sv/matcher_contracts/matcher_regression_cases.json` and
  `app/languages/sv/matcher_contracts/matcher_rule_inventory.json`.
- Covered decisions: flavored plain `växtdryck` no-match, `fransk senap`
  -> Dijon, `mörk chokladkaka`, rimmad/skivad `lax` boundaries, and spaced
  `fläderblomssaft`/`rabarbersaft` product labels. The next imported slice
  also covers fresh `tonfisk`, Bärta/tempeh helbit-state, `dillfrö`, `surkål`,
  fläskkarré/kycklingfilé prepared-state, `lagrad ost`, limejuice, generic
  `nudlar`, and `chunky salsa`. The third imported slice covers mixed fresh
  herbs, `potatismos`, `vitlöksmarinad`, white/form bread, `mandelspån`,
  `citronmeliss`, ketchup-style `chilisås`, and `knipplök`. The fourth imported
  slice covers white `chokladkaka`, pistachio salt-state, yellow/green kiwi,
  `falafelmix`, sparkling `mineralvatten`, pitted/Kalamata/black olive
  fallbacks, `majsmjöl`, `kardemummayoghurt`, `kantareller i vatten`, and
  canned `körsbärstomater`.
  The fifth imported slice covers plain `chilisås`, `wokgrönsaker` including
  canned/brine state, `Polly`, `strössel`, `färskost med örter`, generic fresh
  herbs, plain `mineralvatten`, `aromsmör`, `chilimajonnäs`, and
  `sommargrönsaker`. The sixth imported slice covers packaged `tonfisk`,
  `kruksallad`, `smör- & rapsolja`, plain `vaniljglass`,
  ground `kryddnejlika`, sweet-context `cream cheese`, generic `köttfärs`,
  and fänkålsfrö brand/context leakage. The seventh imported slice covers vegan
  recipe-title context for burger alternatives, `äggfri tagliatelle` versus egg
  pasta, and `blomkålshuvud` to fresh/frozen `blomkål`. The eighth imported
  slice covers route-only families for `oreokakor`, `kycklingschnitzel`, dried
  Karl Johan/forest mushroom wording, and explicit `prästost`. The ninth
  imported slice covers declared canonical families for `bostongurka`,
  `Tom Kha Gai kryddmix`, and `svart böna`. The tenth imported slice covers
  `limepepper`, `kolasås`, and `ancho chili`. The eleventh imported slice covers
  route-only handling for `kycklinginnerfilé`. The twelfth imported slice covers
  the declared diagnostic family for `Tempeh Helbit, Naturell` while preserving
  the smoked Bärta/tempeh negative. The latest parity pass also covers exact
  `Grillkrydda Vitlök`, the Batch 10-13/14 spice-mix variant matrix including
  Korean/Bulgogi, explicit `rökig chili fläskkarré`, and Batch 3 slices for
  `savoiardikex`, `björnbärssaft`, plain `sodavatten`, `havregryn`,
  `snabbkaffepulver`, brewed coffee/espresso no-match policy, `nötcreme`,
  `sliderbröd`, `kolsyrad apelsindryck`/`Fanta`, exact `Beyondburgare`,
  frysta `lingon`, `svampfond`, `surdegsbaugette`/`baugetter`, and
  `Rostbiff Pålägg` with the raw/deli boundary. The newest Batch 3 slice covers
  explicit `Violife` smoked/mature cheddar, vegan/vegetarian `vegobacon`,
  typo `växtbaserad mjölkryck`, plain `Havredryck Naturell`, smoked
  `paprikapulver`, `öl`, spice/frozen-form `koriander`, `tortillabröd`, and
  `Huvudsallat`. The latest Batch 3 slice covers `Kesella Vanilj`/
  `vaniljkvarg`, fresh versus candied `apelsinskal`/`citrusskal`, hard
  `tunnbröd`, `styckbröd`/fröfralla, `kokosflingor`, cut-specific
  `lammracks`, and generic `tortilla` versus Spanish tortilla. The final
  pre-wrap slice covers fresh `grapefrukt`/`Grape Röd` and generic
  `brödskivor` to sliced/form bread.
- Current matcher-layer parity totals after these slices: `438/438` fixtures,
  `184` inventory rules, `parity_mismatches = 0`, `duplicate_signal_source = 0`,
  `ambiguous_canonical = 0`, and compiled hint-first fallbacks
  `{"hinted_validation_rejected": 20}`.
- Runner filters are now available for `--policy-ref`, `--canonical`, and
  `--diagnosis-class` in both fixture and parity runners. Legacy inventory
  status now reports `184/184` rules with fixtures, `453/453` anchored
  line_refs and `255/453` recorded ranges still current, `0` wrapped
  rules, `127` migration candidates, and `1` deprecated rule.
- Latest reload after the legacy-old auto-candidate completion pass finished
  ready in 175s with `matcher-2422be69fa8f`,
  `recipe-compiler-8648a753cc55`, `offer-compiler-b9708ad6838b`, and
  `13279` cached recipes.
- Legacy-old import tooling has started. `app/tests/import_legacy_questions.py`
  now parses `batch_review_questions_old.md` in read-only dry-run mode,
  classifies old questions before any fixture merge, and can emit/filter
  candidate fixture JSON from a validation report. The importer now also drops
  bracket-only ingredient-index captures such as `[2]`, treats accepted broad
  family notes as non-candidate decisions, and infers a small set of negative
  sibling products inside otherwise positive legacy questions. The diagnostics
  layer now also declares narrow canonical families for `taco`/`kryddmix`,
  `durumvete`/`durumvetemjöl`, and `gochujang`/`chilipasta` so accepted exact
  matches do not fail as ambiguous. This pass also fixed legacy-old no-match
  leaks for raw potatoes versus `mandelpotatischips` and prepared/preserved
  makrillfilé products versus plain `makrillfiléer`, and infers `beverages`
  for obvious old synthetic beer/wine offers such as porter. Direct policy
  correction: explicit `snabbnudlar`/`instantnudlar` ingredients are now
  intentional no-match and have a permanent main fixture/inventory reference.
  The latest legacy-old triage also added route-only bridges for
  `bladspenat -> spenat`, `rödspättafilé -> rödspätta`, and
  `ansjovisfiléer -> ansjovis`, keeps `glutenfri` ingredients from accepting
  non-gluten-free products, treats `persiljekvistar` according to the current
  fresh/frozen parsley policy, and marks only the specific
  `Green Chili Mild 113g Santa Maria` jar as no-match rather than globally
  blocking sensible `Green Chili Mild` products. The final legacy-old
  candidate pass also keeps explicit `Extra jungfruolivolja Classico` away
  from lemon-flavored olive oil and olive-oil spray while leaving plain
  `olivolja` broad enough to match extra-virgin olive oil. The importer now
  filters embedded `### Notes` blocks, commit/metadata phrases, ellipsis
  fragments, generic form words, explicit ingredient quotes in
  `Product ... matched Ingredient ...` lines, and known title fragments that
  are not real offer names. It also extracts all recipe names from `Seen in`
  rows so they do not leak into product candidates, and recognizes correct
  positive sibling products such as exact tomato soup, chipotle paste, pickled
  ginger, preserved chanterelles, and jarred jalapeño where the legacy comment
  already states that intent. The importer now
  writes `app/tests/fixtures/matcher_legacy_questions_triage_report.json`,
  which splits the remaining old-file work into auto-fixture, non-actionable,
  parser-recoverable missing-field, and real policy-review buckets. Candidate
  ids now include an offer-name slug instead of only an offer index, so later
  parser improvements do not rename existing auto-cases just because more
  offers were extracted earlier in the same old question.
  The completion pass added singular/plural route aliases for `aprikoser` and
  `champinjoner`, offer keyword bridges for `cornichoner`/`cornichons` and
  `salladsblad`, `ädel -> ädelost`, exact `vitlökssmör`, a soy-sauce vs soy
  cuisine block, whole-cardamom-seed form strictness, branded `pizza spices`
  no-match behavior, and preserved/sliced `skogschampinjoner` blocking.
  Latest pass parsed `346` numbered questions across `83` batch sections and wrote
  `app/tests/fixtures/matcher_legacy_questions_candidate_cases.json` with
  `921` conservative candidates: `550` expected no-match cases and `371`
  expected positive cases. Candidate fixture diagnostics are now fully green
  (`921/921`), and all 921 confirmed candidates were written to
  `app/tests/fixtures/matcher_legacy_questions_confirmed_cases.json`. The
  rejected staging file
  `app/tests/fixtures/matcher_legacy_questions_rejected_candidates.json` is now
  empty after validation (`0` rejected candidates). Confirmed fixture and parity
  both pass (`921/921`, `parity_mismatches = 0`, hint-first fallbacks
  `{"hinted_validation_rejected": 57}`).
  Current triage leaves `62` manual action questions: `1`
  parser-recoverable missing-offer question and `61` policy/unclear-direction
  questions, with `68` old questions classified as non-actionable. Full
  matcher-layer fixture/parity stayed green
  (`438/438`), inventory line-ref anchors remain `453/453` while recorded
  ranges are current for `255/453`, matcher version checks passed `100/100`, support sanity
  passed `67/67`, matching sanity passed `1894/1894`, and ruff passed with
  the project `tests/ruff.toml`.

Batch 14 checkpoint notes - 2026-05-03:
- Ranks 1301-1306 were checkpointed before the worker continued. No Stefan
  questions were accepted from this checkpoint; the issues were direct matcher
  fixes or cache/stale verification work.
- `1 påse kryddmix (à 35 g, gärna Asian Spices Korean BBQ Bulgogi)` must not
  match unrelated dry Indian spice mixes such as `Garam Masala Indian Spices`
  or `Tandoori Chicken Indian Spices`. Keep explicit spice-mix product/variant
  hints from parentheticals before stripping preference text.
- Generic/plain `växtdryck` may match neutral oat/soy/almond/pea/rice/coconut
  drink products, but must block strong flavor variants such as caramel,
  hazelnut, maple/walnut, nöt/vanilj, chocolate, berry, or Dumle.
- `Fransk senap` means Dijon/French-style mustard. Correct goods include
  `Dijonsenap Garant`, `Dijonsenap French Style Johnny's`, and
  `Dijon Senap Dijona`; ordinary `Senap Sötstark`/`Original Senap` are not
  valid.
- `Mörk chokladkaka` should route to plain dark chocolate bars or dark baking
  chocolate, including English `Dark Excellence` wording, while flavored/white
  chocolate variants stay blocked.
- `Rimmad lax i tunna skivor` should route to cured/cold-smoked sliced salmon
  style products such as `Gravad Lax Skivad`, `Kallrökt Lax Skivad`, or
  `Najadlax Skivad`; raw `Laxfilé` and hot-smoked `Lax Varmr Portion` are not
  valid.
- Verification before continuing batch 14: `tests/test_matching_sanity.py`
  passed `1683/1683`; `dev_reload.py` rebuilt cache to
  `matcher-574a20dd13b3` / `recipe-compiler-e310e309a31f` with status
  `ready`, `13331` recipes and `13275` matched cache rows.

Batch 14 continuation notes - 2026-05-03:
- Ranks 1307-1322 were reviewed by the single batch-14 worker after the first
  reload. The orchestrator accepted 6 direct matcher fixes and no Stefan
  questions from this span.
- `Fläderblomssaft eller rabarbersaft` should route to saft/cordial products
  even when the product text splits the flavor from `Saft`, e.g.
  `Fläderblom Ekologisk Saft Glas Tillmans` and
  `Rabarber Ekologisk Saft Glas Tillmans`.
- `Färsk tonfisk` should match fresh/frozen tuna steak or fillet style fish
  products such as `Tonfisk Steaks Leröy`, while canned tuna in water/oil,
  tuna paste/salads/sandwiches, and cat food remain invalid. `Tonfisk Tataki`
  was intentionally not broadened here because it is a prepared/seared product
  name unless Stefan explicitly accepts it later.
- Exact `Paket Bärta Helbit, Naturell` should not fall back to unrelated
  smoked/flavored tempeh such as `Tempeh Alspånsrökt Helbit Yipin`. Generic
  `Tempeh Helbit, Naturell` may still match naturell helbit products.
- `Dillfrö` and `Dillfrön` are the same spice seed family and should match
  each other without matching fresh dill.
- `Surkål` is a real buyable fermented-cabbage family. Products like
  `Fass Kraut Surkål Premium Kuhne`, `Surkål Stollenwerk`, and
  `Surkål med Morot Urbanek` can satisfy surkål, but `Surkål med Morot` must
  not satisfy standalone carrot lines.
- Plain/raw `fläskkarré` should block flavored/prepared cuts such as
  `Karré Rökig Chili Sverige Scan`; if the recipe itself explicitly requests
  the same rökig/chili preparation, the product can match.
- Verification after these fixes: `tests/test_matching_sanity.py` passed
  `1696/1696`; `dev_reload.py` rebuilt cache in 174s to
  `matcher-52387769ff4b` / `recipe-compiler-d80e490ec782` /
  `offer-compiler-ea5e90ca4f97` with status `ready`, `13331` recipes and
  `13275` matched cache rows. Cache spot-checks for ranks 1308, 1315, 1318,
  and 1322 confirmed the intended products and absence of the rejected ones.

Batch 14 second continuation notes - 2026-05-03:
- Ranks 1323-1330 triggered the stop rule with 6 worker direct-fix candidates
  in 8 recipes. The orchestrator accepted those and added 1 extra gatekeeping
  fix for a kimchi-flavored udon product the worker missed. No Stefan questions
  were needed. DB issue count for rank 1329 was corrected from 2 to 3.
- Plain/raw `Kycklingfile`/`Kycklingfilé`, including frozen plain wording,
  should match raw/plain chicken fillet products such as
  `Kycklingfilé Bröstfilé Sverige Garant` and
  `Kycklingfilé Svensk Fryst Garant`, but block seasoned/pre-flavored fillets
  such as `Kyckling Bröstfilé Grillkryddad Eldorado` unless the recipe asks
  for that seasoning.
- `Riven lagrad ost, t ex Västerbottensost` should require aged/hard cheese or
  the Västerbottens family. Correct goods include `Herrgård Lagrad`,
  `Präst Lagrad`, `Präst Lagrad Riven`, `Västerbottens Original Ost`, and
  `Västerbottens Riven Ost`. Ordinary mild/generic cheese (`Gouda 31%`) and
  vegan/spread/grill/salad-white carriers are not valid.
- `Lime, juicen` can match plain lime juice/pressed lime products such as
  `Lime Juice Eko Garant Eko`, but should block blended fruit juices where
  lime is only one flavor component, e.g. `Äpple Ananas Kiwi Lime Juice`.
- Generic `Nudlar (efter smak)` should route to plain noodle families such as
  `Nudlar Soba`, `Nudlar Udon`, and `Nudlar Ramen Fresh Hokkien`, but block
  flavored/instant/prepared noodle products such as `Chicken Flavou Pho Ga
  Nudlar`, `Demae Ramen Biff Nudlar`, and `Nudlar Udon Kimchi Garak`.
- `Chunky Salsa` should match ordinary salsa products such as `Chunky Salsa
  Medium/Mild` and `Salsa Mild`, but block cheese-sauce products where salsa is
  only a style/flavor, e.g. `Cheese Sauce Salsa Mexicana`.
- Verification after these fixes: `tests/test_matching_sanity.py` passed
  `1713/1713`; final `dev_reload.py` rebuilt cache in 161s to
  `matcher-06259a9ed79c` / `recipe-compiler-a41e9fa7d558` /
  `offer-compiler-a8e7d60d063d` with status `ready`, `13331` recipes and
  `13275` matched cache rows. Cache spot-checks for ranks 1323, 1327, 1328,
  1329, and 1330 confirmed intended products and absence of the rejected rows.

Batch 14 third continuation notes - 2026-05-03:
- Ranks 1331-1338 were marked late by the previous worker at
  `2026-05-03 15:51:54 UTC` / `17:51:54 CEST`. Replacement worker did a
  read-only audit only; the orchestrator accepted the 4 real DB issues from
  this span and raised no Stefan questions.
- `Kantarellsås` was not broadened in this pass: current Willys offers include
  kantarell soup/powder/fond/färskost style products, but no real kantarell
  sauce offer. Zero/limited matches are acceptable until a sauce product exists.
- `Blandade örter t ex basilika, rucola och persilja` should expand as fresh
  herb/salad-leaf alternatives. Correct goods include fresh/frozen basil,
  rucola/ruccola, and parsley products such as `Basilika i Kruka Ekologisk`,
  `Basilika Finhackad Fryst Garant`, `Ruccola Klass 1`, and
  `Persilja Krus Garant`; dried spice jars/bags are not valid for this fresh
  mixed-herb example.
- `Inlagd hackad gurka (t ex bostongurka)` should preserve the concrete
  product-style example and route to `Bostongurka Felix` /
  `Bostongurka Gurkmix Felix` as well as compatible pickled/salted cucumber
  fallback rows.
- `Potatismos` should match instant mash products such as `Potatismos 12 Port
  Felix` and may keep raw potato fallback for homemade mash, but it must block
  complete ready meals such as `Panerad Fisk med Potatismos Redo`.
- `Vitlöksmarinad` should match spaced product wording such as
  `Vitlök Marinad Caj P`, but not unrelated generic marinade carriers such as
  `Allround Marinad`.
- Verification after these fixes: `tests/test_matching_sanity.py` passed
  `1723/1723`; `dev_reload.py` rebuilt cache in 174s to
  `matcher-99b0a2390ba5` / `recipe-compiler-c62c7fe0da3e` /
  `offer-compiler-ea9a2072acb2` with status `ready`, `13331` recipes and
  `13275` matched cache rows. Cache spot-checks for ranks 1333, 1334, and 1336
  confirmed intended products and absence of dried-herb, ready-meal, and
  allround-marinade false positives.

Batch 14 fourth continuation notes - 2026-05-03:
- Ranks 1339-1346 were reviewed by the single worker in about 6 minutes. The
  worker stopped at the checkpoint as instructed and reported 7 direct-fix
  candidates, no real Stefan questions, no code edits, no reload, no commits,
  and no subagents. The orchestrator accepted the 7 issue counts after local
  live/cache verification, then applied the fixes below.
- `Tunt skuret vitt bröd` should route to white/form/toast bread products such
  as `Rostbröd Klassiskt Garant`, `Jättefranska Pågen`, `Tasty Toast Pågen`,
  and `Brioche Rostbröd Garant`. It should not widen to flatbread, dark/rye
  bread, bagels, somun, or similar broad bread carriers.
- Exact Oreo cookie ingredients such as `oreokakor` should include Oreo cookie
  packs in the prepared cache. Correct current goods include `Oreo Original
  Kakor`, `Oreo Original`, `Oreo Double Cream Kakor`, `Golden Oreo Cookies
  Kakor`, and `Mini Oreo Cookies`; Oreo chocolate bars/sandwich-style candy are
  not cookie-pack fallbacks for `oreokakor`.
- `Sötmandel Spån` means almond flakes/slivered almonds and should route to
  `Mandelspån Garant` / `Mandelspån Rostade Dr Oetker`, not whole almonds.
- Plain `citronmeliss` should match fresh lemon-balm herb products such as
  `Citronmeliss Klass 1 Garant`; tea or flavored carriers remain invalid.
- `Chilisås av ketchuptyp` is the ketchup-style chili-sauce family. Correct
  goods include `Chilisås Klassisk Garant`, `Chilisås Original Felix`, and
  `Chilisås Heinz`; Asian/garlic/sriracha/sweet-chili carriers such as
  `Chilisås Vitlök Ayam` are not valid for this wording.
- `Knipplök` can match bunch/spring onion products including
  `Lök Röd i Knippe Klass 1` and `Salladslök Knippe`.
- `Konserverade körsbärstomater` should match canned/in-juice cherry tomato
  products such as `Körsbärs- Tomater i Tomatjuice Eldorado`, while fresh
  baby-plum/cocktail tomatoes remain blocked for explicit canned wording.
- Root-cause note: two checkpoint FNs were not live matcher failures. Oreo
  cookies were dropped by the global processed-offer filter, and the canned
  cherry tomato product was in the store `beverages` category until the category
  reclassification rule put `tomater i tomatjuice` into pantry-style food
  offers.
- Verification after these fixes: `tests/test_matching_sanity.py` passed
  `1744/1744`; `dev_reload.py` rebuilt cache in 173s to
  `matcher-d002076dab73` / `recipe-compiler-90b87c207988` /
  `offer-compiler-1bcbb00958f1` with status `ready`, `13331` recipes and
  `13276` matched cache rows. Cache spot-checks for ranks 1339-1346 confirmed
  intended products and absence of the rejected broad-bread, Oreo-chocolate,
  whole-almond, garlic-chilisås, and fresh-tomato false positives.

Batch 14 fifth continuation notes - 2026-05-03:
- Ranks 1347-1356 were reviewed by the single worker in about 4 minutes and
  10 seconds. The worker reported 7 direct-fix families and no Stefan questions.
  The worker stopped after crossing the review threshold, but reported after 10
  recipes rather than immediately at the threshold; the orchestrator gatekept the
  decisions, added one smultron-water filter correction found during cache
  spotcheck, and then reloaded before continuing.
- `Chokladkaka Vit` / white chocolate bar wording should route to explicit white
  chocolate products such as `Bakchoklad Vit Garant`, `Bakchoklad Ögon Vit
  Fazer`, and `Chokladknappar Vit Odense`. Dark/milk chocolate rows remain
  blocked for explicit white wording.
- Generic `pistagenötter` can match pistachio/pistasch nuts or kernels, including
  salted current snack rows such as `Pistaschkärnor Utan Skal Rostade Och
  Saltade Garant` and `Pistaschnötter Rostade Saltade Eldorado`. Explicit
  `osaltade pistagenötter` still blocks salted/havssalt products.
- Explicit kiwi colour is directional: `Kiwi Gul` should require yellow/gold kiwi
  products, while `Kiwi Grön` may use ordinary generic green kiwi rows and should
  not match yellow kiwi.
- `Falafelmix` is a mix/powder product, not ready frozen falafel. It can match
  `Falafelmix`/falafel-mix wording when such an offer exists; `Falafel Fryst`
  style ready products are invalid.
- `Kolsyrat mineralvatten` should route to plain/naturell/original sparkling
  water/mineral-water products such as `San Pellegrino Mineralvatten Kolsyrat
  Vatten Pet`, `Naturell Kolsyrat Vatten`, and `Original Kolsyrat Vatten`.
  Smaksatt sparkling water such as citron/smultron/päron/etc. remains invalid.
- `Kalamataoliver urkärnade` keeps the accepted Kalamata -> black/Gemlik fallback
  principle, and with/without pits is pragmatic rather than critical. Correct
  goods include pitted rows, rows with pits such as `Kalamata Oliver med Kärnor`,
  and black/Gemlik olive fallbacks such as `Svarta Oliver Utan Kärnor` and
  `Gemlik Oliver Ceren`.
- Plain `Kantareller` may match practical mushroom rows including
  `Kantareller i Vatten Borgens` from the store beverages category after
  reclassification; kantarell-flavored carriers such as färskost/fond/soup are
  not standalone kantarell matches.
- Verification after these fixes: `tests/test_matching_sanity.py` passed
  `1767/1767`; final `dev_reload.py` rebuilt cache in 174s to
  `matcher-3bb562867665` / `recipe-compiler-ae245f333072` /
  `offer-compiler-120e7ba41097` with status `ready`, `13331` recipes and
  `13280` matched cache rows. Cache spot-checks for ranks 1350, 1352, 1353, and
  1356 confirmed intended products and zero rejected matches for generic-green
  yellow kiwi, yellow green-kiwi, ready falafel, smaksatt sparkling water,
  kantarell flavored carriers.

Batch 14 sixth partial notes - 2026-05-03:
- Ranks 1357-1362 were reviewed by the single worker in about 5 minutes and
  43 seconds before orchestration stopped the run. The worker reported 1 real
  DB issue, for `Kardemummayoghurt`; ranks 1357, 1358, 1360, 1361, and 1362
  were marked clean. This brings batch 14 to 62 reviewed recipes with 37 logged
  issues across those reviewed rows.
- `Kardemummayoghurt` requires an explicit cardamom yoghurt/cardamom-yoghur
  style product, or zero matches if none exists. Plain/naturell yoghurt rows,
  including typo product wording such as `Turkisk Yoghur Naturell 17% Salakis`,
  are not valid for explicit cardamom-yoghurt wording.
- Orchestration also gatekept the worker's read-only suspicions from unreviewed
  ranks 1366 and 1368 before continuing. These are fixed now but are not part of
  the 37 DB-logged batch-14 issues because those recipe rows remain unreviewed.
- `Majsmjöl` should match corn flour/maize flour rows such as
  `Majsmjöl Grovmalet Favero`, `Majsmjöl Glutenfri Risenta`, and
  `Majsmjöl Finmalet Favero`; it must not match breadcrumb carriers such as
  `Ströbröd Instant Majsmjöl Glutenfritt Olda`, where majsmjöl is only an
  ingredient/flour component.
- `Svarta oliver utan kärnor` preserves the recipe wording in compiled data,
  but with/without pits is pragmatic rather than critical. Correct goods can
  include pitted/urkärnade rows, rows with pits such as `Kalamata Oliver med
  Kärnor`, and accepted black/Gemlik/Kalamata olive fallbacks such as
  `Gemlik Oliver Ceren`.
- Root-cause note: recipe-preparation changes in `compiled_recipes.py` must
  invalidate compiled recipe payloads. `compiled_recipes.py` is now part of
  `RECIPE_COMPILER_HASH_FILES`, so `dev_reload.py` rebuilds recipe payloads
  when that preparation logic changes instead of reusing stale compiled recipe
  data.
- Verification after these fixes: `tests/test_matching_sanity.py` passed
  `1774/1774`; final `dev_reload.py` rebuilt cache in 160s to
  `matcher-67802b30e0de` / `recipe-compiler-a2fe2de689d3` /
  `offer-compiler-8abdbdacbf10` with status `ready`, `13331` recipes and
  `13280` matched cache rows. Cache spot-check for rank 1368 confirmed
  `Svarta oliver utan kärnor` now includes both `Kalamata Oliver med Kärnor`
  and `Gemlik Oliver Ceren`; rank 1366 confirmed majsmjöl-only offers and no
  ströbröd carrier; rank 1359 no longer has the plain yoghurt false positive.

Batch 14 completion notes - 2026-05-03:
- Ranks 1363-1400 were reviewed locally by the orchestrator under
  `collect_findings` mode after the final cache reload. Batch 14 is fully
  reviewed in DB: 100/100 recipes, 72 logged issues total. The final 38-recipe
  span contributed 35 logged direct-fix candidates and no real Stefan questions.
  Follow-up implementation pass fixed the verified matcher/filter issues below,
  added regression coverage, and rebuilt the live cache to matcher
  `matcher-5df88d338e3e` / offer compiler `offer-compiler-7e9261c606dc`.
- Verification after implementation: `tests/test_matching_sanity.py` passed
  `1831/1831`; final `dev_reload.py` finished in 159s with status `ready`,
  `13331` active recipes, `13280` cache rows, `5246` filtered matching offers,
  and `3753` matched offer identities. Cache spotcheck of the final span had
  0/31 failures across the key corrected ingredients (`Polly`, `strössel`,
  `kolasås`, canned wok vegetables, vegan burger/färs, `Tom Kha`, canned tuna,
  `smör- & rapsolja`, etc.).
- Review correction after Stefan's `Kanel Hel` challenge: use
  `recipe_offer_cache.match_data->matched_offers` grouped by `_matched_ing_idx`
  as the source of truth for cached recipe/offer matches. Do not use
  `ingredient_groups` exact/original labels as a zero-match detector; that view
  can omit or compress groups. `Kanel Hel`, `Pappardelle`, and `äggula` were
  false positives in the review notes, not confirmed matcher failures.
- Verified accepted/non-issues from the final pass: `Kanel Hel` correctly
  matches whole-cinnamon rows (`Kanel Hel Påse Eldorado`, `Kanel Hel Påse
  Kockens`) and blocks ground cinnamon; `Pappardelle` has cached pasta matches
  including current pappardelle products; `äggula` pragmatically matches
  ordinary eggs; explicit fresh/kyld smördeg may pragmatically match frozen
  smördeg.
- Accepted policy correction from Stefan during the pass: explicit fresh/kyld
  smördeg may pragmatically match frozen smördeg, the same way frozen herbs and
  vegetables can satisfy fresh/common-use wording. Do not count
  `färsk kyld smördeg` -> frozen smördeg as an issue.
- Pasta/pantry routing FNs: plain `mineralvatten` should match plain
  mineral/sparkling-water products such as `San Pellegrino Mineralvatten
  Kolsyrat Vatten Pet`.
- Exact/specialty grocery FNs: `Polly` should match current Polly candy bags;
  `strössel` and `kolasås` should match current dessert-topping rows;
  `blomkålshuvud` should match fresh/frozen blomkål rows; `kruksallad` should
  match `Krispsallat i Kruka Ekologisk Klass 1`.
- Wok/vegetable FNs: ordinary `wokgrönsaker` should match real wok-mix or
  wok-vegetable rows such as `Wokmix Fryst Eldorado`,
  `Wokmix Klassisk Fryst Garant`, and `Wok Classic Bigpack Findus`; it should
  not match wok sauces. Explicit canned/in-brine wording such as `425 g sköljda
  wokgrönsaker (på burk)` should be stricter and match the brine/canned family,
  e.g. `Wok Mix Vegetables In Brine Spicefield`, not frozen wokmixes. `Apetit
  frysta sommargrönsaker` should match `Grönsaker Sommar Fryst Apetit`.
- Sauce/condiment FPs/FNs: plain Swedish `chilisås` in cooking sauce context
  should not match Asian garlic chili sauce such as `Chilisås Vitlök Ayam`;
  `chilimajonnäs` should match chili-mayo products such as `Chilimajo Garant`
  and `Sriracha Mayo`, not standalone chili peppers; `aromsmör` can match
  practical flavored butter rows such as `Persiljesmör Biggans` and
  `Vitlökssmör Biggans`.
- Spice-mix/specialty FPs: `lime pepper krydda` should not match fresh lime
  fruit; if no lime-pepper seasoning exists it should have zero matches.
  `Tom Kha Gai kryddmix` should not degrade to unrelated Indian spice mixes
  (`Garam Masala Indian Spices`, `Tandoori Chicken Indian Spices`); prefer an
  explicit Tom Kha product if available (`Tom Kha Soup Asian Spice Santa Maria`)
  or zero. `Ancho chili, malen` is dish-critical in
  `Böngryta med ancho chili och mörk choklad`; generic chili flakes/powder or
  gochugaru are not ancho fallback rows when no ancho product exists.
- Cheese/dairy FNs/FPs: `100 g färskost (med örter)` should include herb/garlic
  cream-cheese products such as `Vitlök & Örter Färskost`/Philadelphia/Cantadou
  and may keep plain naturell fresh-cheese fallback. `cream cheese` for sweet
  frosting should not match strongly savory flavored rows such as
  `Västerbotten Philadelphia`. `2 dl riven prästost (gärna lagrad i 18 månader)`
  should prioritize/principally require prästost or close aged hard-cheese
  fallbacks, not generic Gouda/Greek-white/vegan spread/grill cheese carriers.
- Generic herb/seed FNs: `1 dl färska örter` should match practical fresh/frozen
  herb rows such as basilika, persilja, dill, timjan, and gräslök without
  letting herb-flavored carriers through. Bare `solroskärnor` should match
  sunflower kernels/seeds such as `Solroskärnor Garant Eko`, `Solroskärnor
  Risenta`, and `Solroskärnor Rostade Risenta`.
- Meat/fish specificity FPs/FNs: `kycklingschnitzel` should keep the right meat
  type; generic pork schnitzel, Oumph, and vegetarian schnitzel are not valid
  for chicken schnitzel. `kycklinginnerfiléer` should not match seasoned chicken
  products such as `Kyckling Bröstfilé Grillkryddad Eldorado`. `Tonfiskröra`
  style canned tuna ingredients should match canned/tetra tuna in water/oil and
  should not match fresh `Tonfisk Steaks` or prepared `Tonfisk Tataki`.
- Vegan/special requirement FPs/FNs: explicit vegan pasta context should keep
  vegan/egg-free requirements. `äggfri tagliatelle` should match non-egg
  tagliatelle/pasta rows and block egg tagliatelle; vegan burger/mince
  alternatives should not include non-vegan Quorn rows if the product is not
  actually vegan.
- Carrier/name leakage FPs: `Hela fänkålsfrön från Kockens kryddor` should not
  match unrelated Kockens products such as four-pepper blends or persillade via
  brand/context words. `Torkad karl johansvamp eller annan blandad torkad
  skogssvamp` should not match fresh/frozen champignons or canned/in-water
  chanterelles; if no dried porcini/forest-mushroom row exists it should have
  zero or only dried mushroom-family matches. Generic `köttfärs` for kålpudding
  should not match strongly flavored/specialty mince such as chorizo/salsiccia
  mince. `malen kryddnejlika` should not match whole cloves.
- Other FNs: `svart böna` should match current black-bean rows; `smör- &
  rapsolja` should match smör-rapsolja products such as
  `Smör-&rapsolja Flytande Original 80% Arla Köket` and Bregott/Valio
  smör-raps rows. Policy correction from Stefan on 2026-05-04: generic `olja`
  remains intentionally unmatched, including cooking/frying context such as
  `olja till stekning`; only explicit purchasable variants such as `rapsolja`,
  `olivolja`, or `smör- & rapsolja` should match.

Batch 15 checkpoint gatekeeping - 2026-05-04:
- Ranks 1401-1408 were reviewed by one Codex worker with
  `cache_state=fresh_prepared_cache`, `code_edits=forbidden`, no reload, no
  tests, no commits, and no subagents. The worker marked all eight rows
  reviewed. Orchestrator spot-check accepted the checkpoint shape but corrected
  one worker judgment: rank 1406 was not clean because `280 g Vegetarisk kebab`
  has current offer `Vegokebab Garant` and live matcher returns 0. DB
  `issues_found` for queue id 1906 was corrected from 0 to 1.
- Accepted direct-fix candidates from the checkpoint: `2 msk crispy chili oil`
  should match `Crispy Chili In Oil Laoganma`; raw sausage meat wording
  `fläskkött, bog eller skinka` should not match cooked/cured deli ham
  (`Kokt Skinka ...`, `Schwarzwälder Schinken ...`) or prepared/marinated
  products such as `Grillspett Souvlaki Fläsk Garant`; `2 msk sötströ` should
  match granular sweetener rows such as `Stevia Sweet Lättströ Sötningsmedel`
  and `Lättströ 40% Fibrer`; explicit `1 Vitlök hel` should not match
  `Vitlök Hackad Fryst Garant`; `280 g Vegetarisk kebab` should match
  `Vegokebab Garant`.
- Accepted non-issues from the checkpoint: generic `salt`/`vatten` zero matches
  remain accepted; broad yoghurt, ordinary/lactose-free milk, plant-based or
  lactose-free crème fraiche/mayo, fresh/frozen ordinary vegetables/herbs,
  broad olive oil, and soy sauce variants remain accepted under prior policy;
  `Kalamataoliver` may use the existing black/Gemlik/Kalamata fallback.
- Real Stefan questions from this checkpoint: none. The worker's missed
  vegetarian-kebab FN is a direct matcher/routing fix candidate, not a policy
  question.

Batch 15 completion notes - 2026-05-04:
- Batch 15 is fully reviewed in DB: ranks 1401-1500, 100/100 recipes reviewed,
  48 accepted DB issues total after orchestrator gatekeeping and Stefan's
  correction of generic `olja` policy. The worker reviewed ranks 1409-1500
  after the checkpoint and reported 45 continuation issues; one continuation
  finding was rejected (`olja till stekning` in rank 1447), and Stefan later
  rejected the `Kikärtsspad` FN in rank 1455 because chickpea brine is not
  bought as its own product and the plain `grädde` issue in rank 1496 because
  ordinary `grädde` must not be inferred as `vispgrädde` from recipe dessert
  context alone. The checkpoint contributed 6 accepted issues after the
  orchestrator corrected rank 1406. No real Stefan questions were found, and no
  worker code edits, reloads, cache rebuilds, tests, commits, or subagents were
  used.
- Orchestrator acceptance gate: DB counts and file status were checked, the
  worker was asked for itemized details before acceptance, and representative
  live matcher checks confirmed the risky examples. Current live matcher still
  returns 0 for `Smördegsark Veganskt` -> `Smördeg Plattor Fryst Garant` and
  `Sushilax Falkenberg` in the sashimi recipe; it returns 1 for rejected
  examples such as `Cider Äpple` -> pear cider, `hela svartpepparkorn` -> ground
  pepper, sashimi-context salmon -> generic laxfilé, and vegan cacio e pepe ->
  egg pasta.
- Stefan correction after review: if beverage/drink ingredients can be matched
  to current food/offer rows, they should be matched. `läsk`, `jordgubbssaft`,
  `folköl`, and `pressad ingefärsjuice` remain accepted direct-fix candidates;
  current offers include strawberry cordial, folköl rows, and pressed
  ginger/ginger-shot rows such as `Ingefära Pressad Garant Eko`. Generic `olja`,
  including `olja till stekning`, remains intentionally unmatched under project
  pantry-staple policy, and rank 1447 was corrected from 1 to 0. Explicit
  vegan/vegetarian wording remains binding: `vegansk smördeg` may route to
  smördeg/puff-pastry rows only when the product does not contradict the vegan
  requirement. `Kikärtsspad` should stay zero; do not route it to canned
  chickpeas just because that is how a cook obtains aquafaba.
- Accepted FN direct-fix candidates from ranks 1409-1500: common typo
  `svarpeppar` should route to `svartpeppar`; `Majskolv färdigkokt` should
  match pre-cooked corn rows such as `Majs Förkokt Garant`; `Smördegsark
  Veganskt` should route to compatible smördeg/puff-pastry rows without
  violating vegan context; exact beverage `läsk` should match current soda rows;
  `glasstrutar` should match empty waffle-cone products such as `Våffelstrutar`;
  bare `fikon` may match dried fig rows when no fresh form is specified; generic
  `rotfrukter` with examples should route to practical root veg and
  `Rotfruktsmix`; `daimchoklad` should match Daim products, not generic
  chocolate; `jordgubbssaft` should match saft/blandsaft rows; `Formbar
  vegetarisk färs` should match vegetarian/formbar mince rows; `Spisbröd`
  should alias to knäckebröd/crispbread; `Burgarbröd` should alias to
  hamburger buns; `Folköl 3,5 %` should match folköl/3.5% beer rows; `Pressad
  ingefärsjuice` should match pressed ginger/ginger-shot rows when available;
  `Tzaybitar` should match practical vegobitar/plant protein pieces.
- Accepted FP/direct-fix candidates from ranks 1409-1500: raw/plain chicken
  ingredients such as `Strimlad kyckling` and `kycklingfiléer` may match
  seasoned raw chicken, but should block ready-cooked/prepared chicken rows;
  `Potato Buns` should be treated as bun/bread wording, not potato soup/fries;
  `jordgubbssaft` must block marmelad; `gari`/inlagd ingefära must block
  sylt/jam; `kanelglass` must not match cinnamon spice; `Dillpicklad gurka` must
  not degrade to standalone dill; `Kumminstekt fejkon` must not make cumin spice
  the matched ingredient; potato chips explicitly `saltade` should block
  bacon/flavored chips.
- Accepted explicit form/specialty decisions: `Apelsinjuice - Koncentrat`
  should require concentrate products; `Balsamvinäger rosé` should route to
  rose/rosé vinegar or condimento and avoid ordinary dark balsamic fallback;
  `Zeta Pastasås Classico`/tomato sauce wording should not match cheese/svamp
  pasta sauces; whole peppercorn wording should require whole peppercorns;
  `Svartpeppar Malen` should block whole/coarse pepper; `grovmalen svartpeppar`
  may match whole peppercorns because the cook can grind them, but should block
  fine-ground pepper; `fänkålsfrö` should prefer whole seed rows over ground
  fennel; `Cider Äpple` should not match pear, berry, fläder, or other cider
  flavors; `Senap Grovkornig` should require coarse mustard rows;
  sashimi-context salmon should require sushi/sashimi-grade style rows such as
  `Sushilax`/likely back-loin products instead of generic laxfilé; `Guajillo
  Chilis, hela` should require guajillo or zero, while separate `Habanero`
  should route to habanero offers rather than being consumed by broader chili
  grouping.
- Accepted vegan/diet and dairy-context decisions: explicit vegan burger context
  should block non-vegan burger rows and match vegan/plant burger rows; explicit
  vegan pasta context should block egg pasta even though broad pasta shape
  fallback is otherwise accepted; cream strictness is only for explicit
  `vispgrädde` or explicit high-fat/30-40% wording such as rank 1423
  `vispgrädde (eller syrad grädde 30 %)` and rank 1499 `grädde (40 %)`.
  Plain `grädde`, even in dessert context such as rank 1496 `Chokladmousse`,
  should not be spontaneously converted to `vispgrädde`; that would over-tighten
  other recipes.
- Accepted non-issues from the continuation: generic `salt`/`vatten` zero
  matches remain accepted; duplicate zero rows caused by same-family grouping
  are not issues by themselves; broad everyday yoghurt/crème fraiche/milk,
  olive oil, rice, pasta-shape, produce, herbs, berries, lactose-free, and
  plant-based base-role variants remain accepted under prior policy; no-current
  offer zeros such as kumquat, gulbeta, julskinka, rättika, fresh watermelon,
  smoked makrill, cognac, and whiskey were not counted. Stale/live-current
  non-issues for hallonsorbet and makaroner/olivolja were not counted.
- Next review target after this accepted batch: batch 16, selection_rank 1501.

Batch 15 implementation follow-up - 2026-05-04:
- Implemented the accepted Batch 15 direct fixes in the Swedish matcher/backend:
  beverage routing for läsk/jordgubbssaft/folköl/pressed ginger, exact aliases
  for typo/special product wording, form strictness for pepper/cider/cream/
  mustard/chips/sashimi/guajillo/fennel, vegan recipe-context blocks, and the
  explicit generic-oil policy where `olja`/`olja till stekning` stay unmatched.
- Added regression coverage in `test_matching_sanity.py` for the accepted
  Batch 15 decisions and updated the older neutral/generic oil expectations to
  the corrected policy. Verification passed: ruff F-rules, `git diff --check`,
  and full sanity `1889/1889`.

Batch 2-3 re-verification - 2026-05-09:
- Re-checked the previous Batch 2 and Batch 3 findings against the current
  prepared `recipe_offer_cache` after the Willys full-assortment scrape and a
  full matcher/cache rebuild. The batch queue now reflects current findings:
  Batch 2 has 0 issues left and Batch 3 has 0 issues left. Stefan confirmed
  that generic/specific `svartpeppar` should remain intentionally unmatched and
  that Fanta/läsk being filtered from cache by current categories is
  acceptable. No real Stefan questions were found.
- Fixed and verified the previous Batch 2 direct-fix/cache candidates:
  `Vegansk Sparristarte` `vegansk smördeg` now matches neutral/vegan-compatible
  smördeg rows; `Falafel` `Feferoni` now matches `Kebabfeferoni`; and
  `Teaterbrons Paprikalasagne` now has a cache row after the `kalas` buffet
  detector was word-scoped so `Paprikalasagne` is not treated as a party menu.
- Fixed and verified the previous Batch 3 cache candidate:
  `Frappé och islatte` `snabbkaffepulver` now matches plain instant coffee
  rows while flavored cappuccino/3-in-1 mixes remain blocked. `Grillade
  lammkotletter` `Lammracks` matches when the current cache/preference scope
  allows non-Swedish meat; with `local_meat_only` enabled the current New
  Zealand lammracks rows are intentionally filtered.
- Rejected/stale from the old Batch 3 notes: `björnbärssaft`,
  `grapefrukter`, and exact `Beyondburgare` zeros were not counted because the
  current Willys offer table has no relevant exact product rows; the two missing
  cache rows in Batch 3 are accepted buffet/party exclusions. Raw chicken,
  bread/tortilla, milk, hard tunnbröd, havregryn, Violife, vegobacon,
  baguette, rostbiff-pålägg/raw rostbiff, coriander, huvudsallad, and the other
  previously logged families spot-checked cleanly.

Batch 4-6 Track A term-pipeline audit - 2026-05-09:
- Ran the first read-only term-pipeline sweep for Batch 4, Batch 5, and Batch 6
  review references. Cache/index freshness was ready before the audit:
  `recipe_offer_matches`, recipe/offer term indexes, and
  `compiled_recipe_offer_candidates` all matched the current matcher/compiler
  versions.
- Checked 135 positive/negative variants with synthetic pair diagnostics:
  81 pass, 6 `ambiguous_canonical`, 18 `route_pair_missing`, 9
  `fast_match_missing`, 3 `recipe_signal_missing`, 1
  `backend_validation_rejected`, and 17 `unexpected_positive`.
- Current-offer retests confirmed high-confidence gaps for `dadelsirap`,
  `pizzasås`, `apelsinsaft`, `gyoza skin`, `After Eight`, `chiliflakes`,
  `Liquid Smoke`/`rökextrakt`, `arrabbiata`, and sliced/soft sourdough wording.
  `majsvälling` retested clean with the current Willys row.
- No matcher edits, DB queue edits, or cache rebuild were performed in this
  read-only pass. Detailed local report:
  `app/tests/batch_review_term_pipeline_audit_batch_4_6.md`.

Batch 7-15 Track A term-pipeline audit - 2026-05-09:
- Ran the same read-only sweep for Batch 7 through Batch 15 references. Cache
  and compiled index freshness was still ready.
- Checked 177 positive/negative variants with synthetic pair diagnostics:
  147 pass, 13 `route_pair_missing`, 7 `unexpected_positive`, 6
  `fast_match_missing`, 2 `recipe_signal_missing`, and 2
  `backend_validation_rejected`.
- Current-offer retests confirmed remaining high-confidence gaps for
  `pistasch`, `kantareller i vatten`, `TUC`, `matjesill`, `smörgåspickles`,
  `puffat ris`, `Crispy Chili In Oil`, `Fish&Crisp`, raw pork/ham wording
  versus cooked ham, and `Burgarbröd`/hamburger bun blocker behavior.
- Current-offer retests were clean for `körvel`, `tikka masala spice mix`, and
  `Mörk chokladkaka` with current rows. `Pesto Basilika` and `Tzaybitar` need
  historical/current product text before being treated as live-catalog gaps.
- No matcher edits, DB queue edits, or cache rebuild were performed in this
  read-only pass. Detailed local report:
  `app/tests/batch_review_term_pipeline_audit_batch_7_15.md`.

Track A current-offer fix wave 1 - 2026-05-09:
- Implemented and verified the first grouped fix wave from the Batch 4-15
  Track A audit. Covered current/live product-text positives for `dadelsirap`,
  `tomatsås till pizza`/`pizzasås`, `apelsinsaft`, `dumplingdeg`/`gyoza skin`,
  `After Eight`, `chiliflakes`, `rökextrakt`/`Liquid Smoke`, `tomatsås
  arrabbiata`, `pistasch`, `kantareller i vatten`, `TUC`, `matjesill`,
  `smörgåspickles`, `puffat ris`, `chili oil`/`Crispy Chili In Oil`,
  `Fish&Crisp`, and `Burgarbröd`.
- Added narrow negative guards/filters for the same wave: `puffat ris` no
  longer routes to ordinary rice, `chili oil` does not route to fresh chili,
  `Tuc Paprika` does not leak `paprika`, raw `fläskkött ... skinka` blocks
  cooked sliced ham, and `Korvbrödbagarn` is treated as a hamburger-bun brand
  tail rather than hot-dog-bread context.
- Cache filtering had to be fixed as part of the wave: exact ingredient
  families `dadelsirap`, `puffat ris`, `TUC`, and `Crispy Chili In Oil` were
  previously excluded as processed products, and `Apelsinjuice Bravo` lost its
  keyword through the drink-brand guard. After the filter fix, all affected
  Willys rows were present in `get_filtered_offers`.
- Verification passed: full sanity `1929/1929`, cache freshness `fresh`, and a
  full compiled rebuild completed ready with 13,538 cached recipes, 3,797 of
  10,427 offer rows, 2,779,066 candidate rows, matcher
  `matcher-ead4f6ddaa91`, recipe compiler `recipe-compiler-e8936359618a`, and
  offer compiler `offer-compiler-264ba483aa51`.
- Cache spotchecks found live cached matches for the rows with current recipe
  text in DB (`dadelsirap`, `pizzasås`, `apelsinsaft`, `dumplingdeg`,
  `After Eight`, `chiliflakes`, `rökextrakt`, `arrabbiata`, `matjesill`,
  `puffat ris`, `chili oil`, and `Burgarbröd`). Synthetic pair tests cover the
  live product rows whose exact batch ingredient text is not currently present
  in the recipe DB (`kantareller i vatten`, `TUC`, `smörgåspickles`,
  `Fish&Crisp`, and bare `pistasch`).

Track A follow-up fix wave 2 - 2026-05-09:
- Implemented and verified the remaining high-confidence Batch 4-15 Track A
  terms with current or synthetic product text: `surdegskakor` ->
  `surdegsbröd`, `Svejkon` -> `vegobacon`, `tranbärsjuice` ->
  cranberry drink/juice rows, `5-minuterssill` -> inläggningssill/sill rows,
  `Tabasco Habanero` -> habanero hot-sauce rows, and `tomatpesto` -> red
  pesto/pesto rosso rows.
- Added narrow negative guards for the documented false positives:
  `tomatpesto` blocks green/genovese pesto, bufala mozzarella blocks vegan
  mozzarella-flavour substitutes, `5-minuterssill` blocks `Ansjoviskrydda
  Sill`, sushi-fish context blocks generic white fish, `hushållsfärs eller
  nötfärs` blocks chicken/vegetarian mince, plain `turkisk havregurt` blocks
  fruit havregurt, `kalkonbröstfilé` blocks turkey thigh fillet, `mjukt
  tunnbröd` blocks hard tunnbröd, `riven hårdost max 17%` blocks higher-fat
  cheese, `storkornskaviar röd` blocks Kalles/Svennes-style tube kaviar,
  `Tabasco Habanero` blocks fresh habanero, `rökextrakt` blocks smoke-flavored
  crackers/bread carriers, measured spirit `rom` blocks fish roe,
  `tryffelburrata` blocks plain burrata, `riven veganost` blocks creamy/spread
  vegan cheese, and `morotssylt` blocks non-carrot jams.
- Verification passed: targeted diagnostics for the wave returned expected
  results, full sanity is `1952/1952`, cache freshness is `fresh`, and a full
  compiled rebuild completed ready with 13,538 cached recipes, 3,801 of 10,427
  offer rows, 2,778,862 candidate rows, matcher `matcher-8d9c9bac71b5`, recipe
  compiler `recipe-compiler-6a658126ab7c`, and offer compiler
  `offer-compiler-faeec6e913c6`.
- Cache spotchecks found materialized rows for the current/live positives:
  `Kärnsund Surdegsbröd`, `Vegobacon`, cranberry drink rows, `5minuters Sill`,
  `Chilisås Original Habanero`, `Pesto Rosso`, and burger-title generic `Bröd`
  to hamburger bun rows. Representative forbidden cache rows for green pesto as
  `tomatpesto`, `Ansjoviskrydda` as `sill`, fresh habanero as habanero sauce,
  tube kaviar as `storkornskaviar`, and strawberry jam as `morotssylt` were
  absent.

Batch 16-18 ICA checkpoint gatekeeping - 2026-05-12:
- Preflight: rebuilt the prepared cache against the current ICA full assortment
  before starting review. Cache is `ready` with 24,768 ICA offers, 13,540 cached
  recipes, 4,384,149 candidate rows, and matcher
  `matcher-820d3408fe0a`. Batches 16-18 are the current review targets:
  ranks 1501-1800.
- Batch 16 checkpoint ranks 1501-1506 accepted after DB and live spot-checks:
  6/6 reviewed, 9 accepted DB issues, no real Stefan questions, no worker file
  edits. Accepted direct-fix candidates: chocolate-cookie ingredient should not
  match plain chocolate/cake carriers; dark chocolate should block banana/
  caramel/candy carriers; `drickfärdig svartvinbärssaft` should match current
  Kiviks blackcurrant drink rows; optional nuts/seeds should block bread/spice
  seed carriers; fresh `paprika` should block paprika spice; plain
  `crème fraiche` should block sweet mango crème fraiche; standalone `persilja`
  should block vitost carrier products; `inläggningssill` should block
  `Västkustsallad` carrier rows. Accepted non-issues: generic salt/water/
  pepper and `svartpeppar` zero matches, broad produce/dairy variants, and
  normal egg/bread/potato/onion breadth.
- Batch 17 checkpoint ranks 1601-1606 accepted after DB and live spot-checks:
  6/6 reviewed, 11 accepted DB issues, no real Stefan questions, no worker file
  edits. Accepted direct-fix candidates: plain mayonnaise should block curry
  mayo; whole/lemon ingredient should block supplement/sports-gel carriers;
  standalone garlic should block seafood salad/vitost carriers; carrots should
  block non-food decoration; standalone cardamom should block pancake-mix
  carriers; cooked green lentils should route to current ready green-lentil
  rows; baby spinach should block pasta/seasoning carriers; garlic carrier
  issue repeats in rank 1605; explicit `sambal oelek` should not match harissa
  sambal; raw squid rings should block breaded squid rings; `sesamfrön` should
  require sesame rows and not generic seed/bread fallback. Accepted non-issues:
  generic salt/water/oil and pepper zero matches, same-family duplicate zero
  rows, broad bread alternative for naan/milk-free bread, and whole/spiskummin
  not being counted for explicit ground caraway.
- Batch 18 checkpoint ranks 1701-1706 accepted after itemized breakdown, DB
  check, and exact live spot-checks: 6/6 reviewed, 18 accepted DB issues, no
  real Stefan questions, no worker file edits. The high issue rate is plausible
  because the ICA full assortment exposes many carrier products and some ICA
  category guesses are wrong. Accepted direct-fix candidates: lemon should
  block supplement/sports-gel carriers; standalone garlic should block seafood
  salad/vitost carriers; tortiglioni/pasta should block pasta seasoning mix and
  ready-meal macaroni carriers; carrots should block non-food decoration;
  Parmigiano Reggiano should block cracker carriers; fresh red chili and fresh
  mint should match current ICA `Peppar Röd`/`Mynta` rows even when scraped
  category is misclassified as `meat`; cinnamon should block pancake-mix
  carriers; fresh cucumber should block preserved/chopped cucumber; firm tofu
  should block prepared tofu skagen/spread. Accepted non-issues: `julskinka`
  with no current relevant offer, generic salt/water/pepper zero matches,
  duplicate same-family grouping, broad soy/olive-oil/produce/dairy variants.
- Batch 16 final ranks 1501-1600 accepted after DB confirmation: 100/100
  reviewed, 205 accepted DB issues, no real Stefan questions, no worker file
  edits. Main accepted fix families: block carrier products for standalone
  garlic, parsley, citrus, chocolate, fresh paprika, creme fraiche/mayo, seeds,
  crackers/cakes/snacks/bread/ready-meals; tighten raw-vs-prepared meat/fish/
  chicken/squid/tofu/pasta products; add or repair current-offer coverage for
  fresh chili/herbs, skin-on salmon, fullkorn lasagne plates, pasta-shape
  specificity, kalamata/citron olives, saltgurka, blackcurrant drink, melon,
  lettuce, ginger, non-alcohol/dark beer, vanilla protein powder, dried
  apricots, ice cubes, instant coffee, truffle oil, and the rank 1580 seitan
  pantry-match/cache-materialization gap. Gatekeeper note: several listed live
  false negatives pass a direct synthetic pair check, so those should be
  treated as cache/materialization/filter candidates until the exact fix wave
  proves whether the term itself is missing. Accepted non-issues include generic
  salt/water/pepper/oil, ordinary broad produce/dairy/bread/pasta/olive-oil
  matches, fresh/frozen vegetable variants, and no-current-offer alcohol/
  cocktail ingredients.
- Batch 17 final ranks 1601-1700 accepted after DB confirmation and
  representative live/synthetic checks: 100/100 reviewed, 264 accepted DB
  issues, no real Stefan questions, no worker file edits. Main accepted fix
  families: recurring garlic/citrus/flavored-oil carriers; non-food carrot;
  baby/flavored milk drinks; cheese/pesto/kex/soft-cheese carriers for cheese;
  prepared/seasoned raw meat, chicken, fish, and seafood products; rice/pasta/
  cereal/ready-meal carriers; generic seed fallback overmatching; cooked-vs-dry
  lentils; canned/preserved vs fresh tomato/cucumber; fresh herb/chili/
  jalapeno/mint/thyme routing/category misses; whole-cinnamon and dry-spice form
  misses; named/current-offer gaps for Non Stop, Cheez Doodles, dulce de leche,
  kanelstänger, and fresh chili/herbs. Gatekeeper spot-checks reproduced the
  policy-sensitive cases for `julmust` -> current apple-must carrier, `Di Bufala
  Campana` -> ordinary/riven mozzarella, `grovt rågmjöl` -> fine rye flour,
  pitted olives -> olives with pits, and `havskräfta` -> current signalkräftor
  row. Accepted non-issues: generic salt/water/oil/black pepper zeros, brewed
  coffee/espresso zeros, kitchen aids, broad ordinary dairy/lactose-free/plant
  variants, broad potatoes/pasta/soy sauce, duplicate same-family zero rows,
  optional glaze, and no-current-offer speciality items.
- Batch 18 final ranks 1701-1800 accepted after DB confirmation and
  representative live/synthetic checks: 100/100 reviewed, 223 accepted DB
  issues, no real Stefan questions, no worker file edits. Main accepted fix
  families: repeated supplement/carrier false positives for lemon/citron juice;
  repeated standalone garlic carriers; ICA category/coverage anomalies around
  fresh chili/herbs/root rows such as `Peppar Röd`, `Mynta`, `Timjan`, and
  `Ingefära`; generic sugar and coconut coverage gaps; pasta/rice/ready-meal
  carriers; prepared meat/fish/poultry false positives; non-food product false
  positives such as `Hänge morot`; cheese/cream qualifier problems; seed/herb
  carrier overmatches; dry-vs-cooked legume mismatches; prepared-pancake/mix
  confusion; `dillfrön` falling back to generic seeds/breads; `gräddost`
  matching blue-cheese/grädd carriers; and `cottage cheese` matching
  almond/plant-based `Cottage Pearls`. Gatekeeper spot-checks reproduced the
  citron supplement, garlic carrier, dill seed fallback, gräddost/blue-cheese
  carrier, cottage-pearl carrier, and current kombucha live match. The generic
  sugar and coconut cases are accepted as coverage/term gaps because direct
  synthetic checks still miss representative current ICA rows. Accepted
  non-issues: broad fresh/frozen ordinary veg/herbs, ordinary dairy/lactose
  variants, broad soy sauce, salt/pepper/water/generic oil behavior, raw
  fresh/frozen substitutions where not clearly prepared, and the rank 1792
  kombucha cache miss because current kombucha rows live-match.

Batch 16-18 ICA deduplicated fix backlog - 2026-05-12:
- Gatekeeper summary: the 692 counted issues are review occurrences, not 692
  independent fixes. Collapsed by behavior, this looks like roughly 18 practical
  follow-up families. Several are broad recurring rule families that should be
  fixed and rebuilt in waves; several are store-category/data-quality issues;
  and a smaller group are term/coverage additions.
- P0/high - standalone ingredient carrier false positives. Seen across all
  three batches. Examples: `vitlök` -> `Kräftstjärtsallad Vitlök` / `Vitost
  ... vitlök persilja`, `persilja` -> vitost carrier, `citron`/`citronjuice`
  -> supplements/sports gels, `mörk choklad` -> banana/caramel/chocolate candy
  carriers, `Parmigiano Reggiano` -> crackers, `babyspenat` -> Knorr pasta.
  Fix direction: stronger component/carrier blocking for prepared products
  where the recipe asks for the standalone ingredient.
- P0/high - raw/fresh ingredient vs prepared/seasoned product false positives.
  Seen across all three batches. Examples: raw chicken/fish/meat/squid/tofu
  matching gyoza, roasted/smoked/cured products, ready meals, breaded squid,
  pasta meals, `Skagenröra Tofu`, and other prepared carriers. Fix direction:
  prepared-product blockers that respect explicit recipe wording and avoid
  blocking valid broad raw/frozen substitutions.
- P0/high - category-dependent food matching is the wrong abstraction. Seen in
  batches 16-18. Examples: `Peppar Röd`, `Mynta`, `Timjan`, `Ingefära`, and
  some dried fruit rows are stored with misleading categories such as `meat` or
  `dairy`. Stefan clarified on 2026-05-12 that store categories are only
  trustworthy enough to filter obvious non-food; no food-vs-food matching
  decision should depend on them because store/source categories are routinely
  wrong. Fix direction: make product text and matcher terms drive food matching;
  use category only as a coarse non-food guard, never as a reason to reject or
  accept a plausible food match.
- P0/high - generic seed fallback overmatching. Seen across all three batches.
  Examples: `sesamfrön` and `dillfrön` falling back to generic seeds, breads,
  spice seeds, and `Bockhornsklöver Hela Frön`. Fix direction: require the
  requested seed/herb-seed family when the ingredient is specific; keep generic
  `frön` broad only when the recipe itself is generic.
- P1/high - spice/fresh/form specificity. Seen across all three batches.
  Examples: fresh `paprika` -> paprika spice, fresh chili/herbs missed or
  blocked, `kanel`/`kanelstänger` vs pancake mix/whole cinnamon, `hel` vs
  ground spice, `mal d kummin` not same as whole/spiskummin. Fix direction:
  extend the existing fresh-vs-spice and form-qualifier gates.
- P1/high - cheese and dairy qualifier specificity. Seen in batches 16-18.
  Examples: plain `crème fraiche` -> sweet mango creme fraiche, plain
  mayonnaise -> curry mayo, `Di Bufala Campana` -> ordinary/riven mozzarella,
  `gräddost` -> blue-cheese/grädd carriers, `cottage cheese` -> almond/plant
  based `Cottage Pearls`, baby/flavored milk drinks for ordinary milk. Fix
  direction: named subtype/qualifier guards for cheese, dairy, mayo, and cream.
- P1/high - pasta/rice/cereal/bread/ready-meal carriers. Seen across all three
  batches. Examples: tortiglioni/pasta -> pasta seasoning or ready-meal
  macaroni, rice/pasta/cereal carriers, cakes/chips/snacks/bagels/crackers
  satisfying base ingredients, `mörkt filmjölksbröd` matching filmjölk instead
  of bread. Fix direction: distinguish base ingredient from product/meal/bakery
  carrier unless the recipe wording asks for that product family.
- P1/medium - canned/preserved/cooked vs fresh form specificity. Seen across
  batches 16-18. Examples: fresh cucumber -> chopped/preserved cucumber,
  saltgurka vs mixed pickles, cooked green lentils vs dry lentils, canned/
  preserved tomato vs fresh tomato, olives with pits vs `urkärnade oliver`.
  Fix direction: add narrow form guards; avoid reducing accepted fresh/frozen
  breadth for ordinary produce.
- P1/medium - current-offer coverage/term gaps that should be checked in the
  next fix wave. Seen across all three batches. Examples: blackcurrant drink,
  fresh herbs/chili, skin-on salmon, fullkorn lasagne plates, pappardelle/
  strozzapreti-like pasta specificity, kalamata/citron olives, melon, lettuce,
  ginger, non-alcohol/dark beer, vanilla protein powder, dried apricots, ice
  cubes, instant coffee, truffle oil, Non Stop, Cheez Doodles, dulce de leche,
  kanelstänger, sugar, and coconut. Fix direction: run targeted synthetic checks
  first; some are true term gaps and some are cache/filter/materialization
  gaps.
- P1/medium - generic sugar and coconut should probably not behave like
  generic oil/pepper. Seen mostly in batch 18. Examples: `socker` missing
  `Strösocker`, coconut milk/cream and coconut flakes/products not routing
  consistently. Fix direction: confirm policy, then add explicit pantry
  coverage with guards for desserts/snacks where needed.
- P1/medium - drink and named beverage specificity. Seen in batches 16-18.
  Examples: `julmust` -> apple must, `alkoholfri öl` / dark beer current-offer
  misses, `drickfärdig svartvinbärssaft` should find current blackcurrant
  drink. Fix direction: named drink families should not collapse to generic
  `must`/drink terms unless explicitly accepted.
- P2/medium - seafood/meat subtype specificity. Seen in batches 16-17 and
  overlaps the raw/prepared family. Examples: `havskräfta` -> signalkräftor,
  raw pork/ham/chicken/fish vs cooked/smoked/cured alternatives, squid rings vs
  breaded squid rings. Fix direction: subtype and preparation guards; this
  should be patched carefully because broad fish/meat substitutions can be
  intentional in some recipe contexts.
- P2/medium - vegetarian/tofu/plant-based prepared-product qualifiers. Seen in
  batches 16 and 18. Examples: firm tofu -> tofu skagen/spread, vegan/plant
  dairy products as ordinary dairy, `Cottage Pearls` almond/plant-based as
  cottage cheese. Fix direction: use explicit plant-based qualifier rules rather
  than broad brand/name keyword hits.
- P2/medium - non-food offer false positives. Seen in batches 17-18. Examples:
  `Hänge morot ull`, kitchen aids, hygiene products with herb/citrus names.
  Fix direction: category/text guard for non-food rows before semantic matching.
- P2/medium - parser/normalization oddities. Seen in batch 16 and related to
  existing broad text cleanup. Examples: `färsk hackad persilja` producing
  mince/`färs` matches, `mörkt filmjölksbröd` matching filmjölk. Fix direction:
  add regression fixtures before touching normalization; risk of unintended
  matcher-wide effects.
- P2/low - no-current-offer or accepted-broad cases should stay out of the fix
  wave. Examples: generic salt/water/pepper/oil, broad ordinary produce/dairy/
  bread/pasta/olive-oil matches, coffee/espresso zeros, cocktail/alcohol
  ingredients without current grocery offers, and duplicate same-family zero
  rows. Fix direction: do not spend fix time here unless later evidence shows a
  real current-offer product text.
- Suggested fix-wave order: first handle P0 carrier/raw-prepared/category-
  dependent matching/seed fallback families together, then rebuild once and
  rerun a targeted sample from batches 16-18. After that, take the P1 term/coverage and form
  specificity items in smaller groups. Avoid using the raw 692 count as the
  progress metric; track by these families plus targeted regression cases.

Batch 16-18 policy decisions before fix wave - 2026-05-12:
- Store/source categories must only be trusted as a coarse non-food filter.
  `hygiene`, `household`, `baby`, `petfood`, and `garden` are hard non-food
  blocks. Everything else should pass into the text/term matcher, because
  grocery store categories are often wrong. Food-vs-food decisions must not be
  based on `fruit`, `vegetables`, `meat`, `dairy`, `beverages`, `pantry`,
  `spices`, etc.
- The path into `household` must be conservative. ICA has many real non-food
  products such as grills, clothing, books, napkins, and outdoor furniture, but
  a borderline product should stay matchable and be blocked later by text rules
  rather than being dropped as non-food too early.
- Beverages are not non-food by category, but they should only match when the
  recipe explicitly asks for a drink ingredient. Named drink families stay
  narrow: `julmust` is not ordinary/apple must, `porter` is not generic beer,
  apple cider is not pear cider, and drink products must not satisfy fruit/flavor
  ingredients.
- Stefan decisions for the first fix wave: block `havskräfta` ->
  `signalkräftor`; block `julmust` -> ordinary/apple must; treat `socker` as
  `strösocker`; treat `kokosmjölk` as only coconut milk, while bare `kokos`
  needs its own context.

Batch 16-18 first safe fix wave - 2026-05-12:
- Implemented the category policy for the first affected paths: fresh herb/chili
  form checks and the local-meat/flavor-carrier guards no longer reject obvious
  food matches just because ICA/source category says `meat`, `fruit`, etc.
  Hard non-food categories still block before semantic matching.
- Patched accepted direct decisions: `havskräfta` no longer matches
  `signalkräftor`; `julmust` no longer falls back to ordinary/apple must;
  `socker` is buyable again and matches `strösocker` while specialty sugars/
  sockerärtor stay blocked; `äppelmust` gets its own offer extraction.
- Added alcohol-free beer extraction that does not depend on `beverages`
  category. Follow-up targeted verification caught that alcohol-free beer was
  still leaking into generic/dark beer via product extraction; `alkoholfri öl`
  now stays named-only and does not satisfy `öl` or `mörkt öl`.
- Follow-up targeted verification also caught that generic `socker` overmatched
  low-sugar carriers such as marmalade/jam with "mindre/utan tillsatt socker".
  Runtime matching now requires plain recipe `socker` to hit `strösocker`, while
  `sockerärter`/`sockerärtor` keep their own route and stay blocked from plain
  sugar.
- Added regression coverage in `test_matching_sanity.py` for the decisions
  above, including bad ICA categories, household hard block, drink specificity,
  sugar, crayfish subtype, and alcohol-free beer.
- Verification: targeted live/synthetic checks for this fix wave passed without
  rerunning all 300 batch recipes; `tests/test_matching_sanity.py` passed
  1970/1970; term registry export, guard/bridge, contract, and matcher-rule
  model checks passed. The contract check now treats line-based verified-term variant-id
  churn as a warning while coverage-key gates remain blocking for real lost/new
  terms.

Batch 16-18 continuation checkpoint - 2026-05-12:
- First safe fix wave is committed as `31b14de Fix batch 16-18 matching edge
  cases`; worktree was clean immediately after that commit.
- Started looking at the next P0 wave, focused on standalone component carriers,
  raw/fresh ingredient vs prepared product, and generic seed fallback. Targeted
  reproduction confirmed representative still-open failures before any accepted
  patch: standalone `vitlök` can match `Kräftstjärtsallad Vitlök`/`Vitost
  Vitlök Persilja`; `citron`/`citronjuice` can match supplement/sportgel rows;
  `babyspenat` can match a pasta carrier; raw `kyckling` can match `Gyoza
  Kyckling`; raw `bläckfiskringar` can match panerade squid rings; `sesamfrön`
  and `dillfrön` can fall back to unrelated generic `frön` products.
- Important rejected approach: do not solve the next wave with raw-ingredient
  keyed blocker maps such as `kyckling -> {gyoza, paj, pizza, pasta, wrap,
  sallad, ...}`. That patch direction was tried briefly, reviewed, and fully
  reverted before this checkpoint. It is too ad hoc, would likely grow into
  brittle rule sprawl, and does not fit the matcher architecture.
- Preferred continuation direction for next session: fix these at the existing
  extraction/carrier/form layers. Product extraction should avoid exposing
  standalone component keywords from clear carrier/prepared products; carrier
  context rules should express product-family requirements generically; specific
  seed ingredients should not be satisfied by unrelated generic seed products;
  raw-vs-prepared should use form/preparation semantics rather than per-raw-
  ingredient carrier lists.
- No accepted wave-2 code is currently in place. Resume by designing a smaller
  architecture-aligned patch and adding regression coverage only once that
  direction is agreed.

Batch 16-18 wave-2 completion - 2026-05-12:
- Root cause confirmed: all failures were missing CARRIER_PRODUCTS entries for
  ICA-specific product types not seen in Willys. Same pattern as existing
  räkor/potatissallad/rödbetssallad — just new ICA vocabulary.
- New carriers added: `vitost`, `kräftstjärtsallad`, `laxsallad`, `pastasallad`,
  `energigel`, `proteingel`, `kollagen`, `gyoza`, `spaghetteria`.
- `frön`/`fron` added to `_SUFFIX_PROTECTED_KEYWORDS` (compound_text.py) so
  `sesamfrön`/`dillfrön` no longer match `Bockhornsklöver Hela Frön` via
  bare-suffix substring. Same mechanism as `kärnor`/`spaghetti`.
- `bläckfiskringar` added to PROCESSED_PRODUCT_RULES with `panerad`/`panerade`
  (processed_rules.py). Same pattern as sej/torsk/kolja/kummel.
- 19 regression cases added to test_matching_sanity.py.
- Supplement products (energigel etc.) are categorized as `beverages` by ICA,
  not `hygiene`/`household` — confirmed: carrier approach is the right defense,
  not category blocking.
- Term registry baseline promoted: `must`/`äppelmust` from extraction_helper.toml
  (added in first wave 31b14de but baseline not updated) merged in via new
  promote_term_baseline.py script. EXPECTED_VERIFIED_TERM_VARIANT_COUNT 5472 → 5474.
  new_legacy_coverage_keys back to 0.
- Commits: `480fe4e Fix batch 16-18 carrier/seed/prepared-product matching gaps`,
  `d378ecc Promote must/äppelmust into verified-term baseline`.
- Remaining open items from P1/P2 backlog: term/coverage gaps for blackcurrant
  drink, fresh herbs/chili, skin-on salmon, fullkorn lasagne, pasta specificity,
  kalamata olives, melon, ginger, non-alcohol beer, vanilla protein, dried
  apricots, ice cubes, instant coffee, truffle oil, Non Stop, Cheez Doodles,
  dulce de leche, kanelstänger, sugar, coconut (P1/medium); seafood/meat
  subtypes and vegetarian/tofu qualifiers (P2/medium); non-food text guard
  for `Hänge morot ull` etc. (P2/medium). P0 families fully resolved.

Batch 16-18 P1/high wave completion - 2026-05-12:
- All P1/high families from the backlog are now fixed and committed (c7867dc).
- pannkaksmix added to CARRIER_PRODUCTS (blocks kanel/kardemumma flavor words
  in pancake mix products).
- bufala/campana added to CONTEXT_WORD_KEYWORD_EXEMPTIONS in carrier_context.py
  so `di bufala campana` recipe ingredient matches `Mozzarella di Bufala Campana`
  product without requiring `mozzarella` in the ingredient text.
- PPR entries added to processed_rules.py: fraiche + {mango, sötstark};
  cottage + {pearls, mandel, havre}; inlagdgurka + {mixed}.
- kanelstänger/kanelstång added to _REVERSE_PARENT_EXCLUSIONS (matching.py) so
  ground kanel products no longer acquire whole-cinnamon keywords via reverse
  parent expansion.
- urkärnade oliver → new no_match_policy entry in no_match_policy.toml +
  hint in no_match_policies.py. Blocks olives-with-pits products when ingredient
  says urkärnade. entry_id uses ASCII form (urkarnade) per _ENTRY_ID_RE regex.
- 16 regression tests added to test_matching_sanity.py. Baseline 5476 variants.
  73/73 sanity checks pass. Dev reload completed.
- Remaining work: P1/medium term/coverage gaps and P2/medium families (see above).

Batch 16-18 P1/medium wave (partial) - 2026-05-13:
- Commit 890d46a. Pasta/bread carrier family and socker/kokos base coverage
  verified as already working. Real gaps found and fixed: kokosflingor extraction
  and svartvinbärssaft extraction.
- kokosflakes (ICA compound form "Kokosflakes Rostade" etc.) added to the
  kokosflingor token list in extraction.py. Was missing because "Rostade" between
  "Kokos" and "Flakes" blocked the spaced-form match.
- svartvinbärsdryck early-return added to extraction.py so products like
  "Svartvinbärsdryck Drickfärdig Kiviks" also emit svartvinbärssaft keyword,
  enabling drickfärdig svartvinbärssaft recipe lines to find them.
- blandsaft (e.g. "Blandsaft Svartvinbär") and svarta vinbär (spaced form with
  'a') added to the svartvinbärssaft extraction conditions. Previously only
  standalone \bsaft\b and the form without 'a' were handled.
- TOML entry sv-se.family.svartvinbarsdryck added to extraction_helper.toml.
- promote_term_baseline.py gains --migrate-hashes flag for extraction
  source_order shifts (when a new if-block is inserted, all subsequent
  extraction outputs get new source_order hashes; --migrate-hashes replaces
  old hash IDs with new ones for entries with matching content).
- 11 regression tests added to test_matching_sanity.py. Baseline 5475 → 5476,
  coverage keys 5336 → 5337. 73/73 sanity checks pass.
- Remaining P1/medium: pasta/bröd-carriers already working; kanelstänger offer-
  side, ginger, vanilla protein, Non Stop, Cheez Doodles, dulce de leche,
  truffle oil, ice cubes, instant coffee still open; also socker/kokos cross-
  matching (kokosmjölk/kokosgrädde not cross-matchable by design per Stefan).
- Remaining P2/medium: seafood/meat subtypes, vegetarian/tofu qualifiers,
  non-food text guard (Hänge morot ull), parser oddities.
- Resume here next session for remaining P1/medium coverage gaps.
