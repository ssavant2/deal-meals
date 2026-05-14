# Plan: robustare skrapare

Datum: 2026-05-14

Status: lokal planfil. Den ska inte trackas, stageas eller committas.

## Syfte

Målet är att göra butiksskrapare och receptskrapare mer motståndskraftiga mot
normala förändringar hos källorna, utan att låtsas att allt kan förebyggas.

Det viktigaste utfallet är:

- Skraparna ska i högre grad hitta rätt data även när en sitemap, selector eller
  intern endpoint ändras.
- De ska hellre behålla befintlig data än ersätta den med tomma eller
  misstänkt små resultat.
- När något går sönder ska felet vara lätt att förstå: vilken väg användes,
  vilken fallback testades, hur många URL:er eller erbjudanden hittades och var
  tappade vi data?
- Source-specifika blockeringar, som Mathems icke-receptpaket, ska kunna göras
  explicit och repeterbart.

Detta är en plan. Inga skrapare ändras i den här filen.

## Kort svar på grundfrågan

Vi kan inte bygga bort alla framtida haverier. Sajter byter HTML, interna API:er,
bot-skydd, API-nycklar och affärslogik. Däremot kan vi förebygga de vanligaste
och farligaste lägena:

- tyst databortfall
- tomma resultat som råkar sparas som sanning
- delvisa resultat som ser lyckade ut
- brutna sitemaps utan alternativ upptäckt
- parse-fel där datan fortfarande finns i en annan representation
- återkommande icke-recept eller icke-mat som råkar följa med

Rätt strategi är därför inte "en scraper som aldrig går sönder", utan en
trappa: flera upptäcktsvägar, flera tolkningsvägar, tydliga kvalitetsgrindar och
bra diagnostik när vi hamnar utanför det kända.

## Nuläge: saker som redan är bra

Det finns redan flera viktiga skydd i kodbasen:

- Butiker använder `StoreScrapeResult` med statusar som `success`, `failed`,
  `blocked` och `partial`.
- Spara-lagret för erbjudanden undviker att ersätta data när resultatet är tomt
  eller ogiltigt.
- Scheduler-flödet respekterar icke-ersättande statusar och behåller befintliga
  erbjudanden vid misslyckanden.
- Receptskrapare har `RecipeScrapeResult`, `StreamingRecipeSaver` och ett
  overwrite-flöde som inte rensar källan om inga sparbara recept hittats.
- URL discovery cache för recept minskar onödiga återförsök, skiljer på
  permanent icke-recept och temporära fel, och stödjer längre retry-intervall.
- Flera källor har redan mer än en väg, till exempel dynamisk sitemap-upptäckt,
  Playwright när JS krävs, eller API-först för butiker.

Planen bör därför bygga vidare på befintliga kontrakt istället för att införa en
ny parallell mekanism.

## Principer

1. API före DOM när det finns en stabil publik eller halvpublik endpoint.
2. Sitemap eller robots-discovery före hårdkodad URL-lista.
3. JSON-LD och strukturerad data före fri HTML-parsning för recept.
4. Source-specifika HTML-fallbacks hellre än breda generiska gissningar.
5. Kvalitet före färskhet: ersätt inte bra gammal data med misstänkt ny data.
6. Diagnostik ska sparas/loggas som sammanfattningar, inte som HTML-dumpar i
   scraper-katalogerna.
7. `Mina recept` behandlas som en receptskrapare med per-URL-flöde för
   användarvalda länkar, inte som en källa där vi själva äger discovery.
8. Gemensamma helpers får finnas när de är källagnostiska och kan användas brett
   av skraparna. Source-/butiksspecifik logik ska ligga i respektive plugin.
   Undvik helpers som bara binder ihop två eller tre skrapare via delade
   antaganden. En scraper ska kunna tas bort, bytas ut eller läggas till utan att
   andra skrapare påverkas.

## Gemensam robusthetstrappa

Varje scraper bör beskrivas med en liten source-profil, antingen som konstanter
eller en lätt dataklass. Profilen kan innehålla:

- källa och databasnamn
- förväntat ungefärligt antal recept
- regler för när ett resultat får ersätta befintlig data
- discovery-vägar i prioritetsordning
- parse-vägar i prioritetsordning
- canary-URL:er eller canary-endpoints
- kända icke-recept eller URL-regler
- kända temporära feltyper, till exempel maintenance, 403, 429 eller tom JSON

Det behöver inte bli tung arkitektur. Det viktiga är att varje scraper får samma
sätt att svara på: "är detta resultat rimligt nog att spara?"

## Förslag: gemensamma byggblock

### 1. Discovery-helper för recept

Inför eller förstärk en gemensam helper för sitemap-upptäckt:

- hämta `robots.txt`
- hitta sitemap-rader
- expandera sitemap-index rekursivt
- filtrera mot source-specifika recipe-patterns
- falla tillbaka till kända historiska sitemap-URL:er
- normalisera URL:er innan cache och jämförelse
- rapportera antal hittade sitemaps, antal recipe-URL:er och vilka fallbacks som
  användes

Detta skulle minska hårdkodningen i framför allt Arla, ICA, Jävligt gott och
Undertian, där en ändrad sitemap-struktur annars kan bli ett totalstopp.

### 2. Parse-helper för recept

Recept bör helst provas i denna ordning:

1. JSON-LD via gemensam extractor.
2. Microdata/RDFa om sidan har schema.org men saknar JSON-LD.
3. Inbäddad app-state eller JS-objekt när källan tydligt bygger receptkort där.
4. Source-specifika HTML-selectors.
5. Playwright-renderad variant när datan bara finns efter JS.

Alla steg ska kunna ge en liten parse-diagnostik: hittade titel, portioner,
ingredienser, instruktioner, bild och vilken metod som vann.

Generell receptkvalitet: skraparna ska fortsätta kräva minst 3 ingredienser för
att spara ett recept. Det är avsiktligt och gäller alla receptkällor, eftersom
det filtrerar bort triviala "recept" som i praktiken bara innehåller till
exempel vatten och ris.

### 3. Kvalitetsgrindar för recept

Receptskrapare bör kunna misslyckas eller returnera `partial` när:

- discovery hittar långt färre URL:er än källans historiska nivå
- parse-hit-rate faller under en source-specifik gräns
- canary-recept inte längre kan parsas
- en full overwrite-körning hittar noll sparbara recept
- en hög andel URL:er klassas som icke-recept på ett nytt sätt

För inkrementella körningar ska grinden vara mildare, men den ska fortfarande
kunna säga "det här ser ut som ett infrastrukturfel, rör inte befintlig data".

**Beslut (2026-05-14):** Rullande historik, inte statisk konstant. Grinden
jämför aktuell körning mot medianen av de 5 senaste lyckade körningarna per
källa. Koden aktiveras inte förrän minst 5 lyckade körningar finns i historiken
— under burn-in-perioden är grinden alltid öppen. `expected_min_urls` i
source-profilen används bara som bootstrapvärde tills burn-in är uppnådd.

Inkrementella körningar är normalfallet och ska kunna bygga historiken. Däremot
ska historiken inte baseras på antal nya eller sparade recept, eftersom en frisk
inkrementell körning legitimt kan hitta 0 nya recept. Spara i stället separata
discovery-/parse-metrics per körning, till exempel:

- `candidate_url_count`
- `selected_url_count`
- `attempted_url_count`
- `parsed_recipe_count`
- `parse_rate`
- `filtered_non_recipe_count`
- `mode`
- `status`
- `reason`

En inkrementell körning får bidra till baselinen när den har gjort en
representativ discovery över källan eller över den normala kandidatpoolen.
Grinden jämför främst `candidate_url_count` och parse-rate mot historiken, inte
antal nysparade recept.

Tröskeln är ~70% av historisk median (justeras per källa vid behov):
- Ny discovery-/parse-metric ≥ 70% av median → tillåt replace (kan vara legitim
  churn/krympning)
- Ny discovery-/parse-metric < 70% av median → blockera replace, returnera
  `failed`

Motivering: naturlig churn (produkter som slutar tillverkas, recept som tas bort)
sker gradvis. En källa tappar inte 30%+ av sina recept i en enda körning utan att
något är trasigt. `partial` används inte för count-gränsen — antingen är
resultatet tillräckligt bra för att ersätta (success) eller inte (failed).

Ingen separat manuell "acceptera ny baseline"-funktion planeras. Om en
receptkälla faktiskt tappar en stor andel recept över en natt är det i praktiken
antingen ett temporärt site-/scraperfel eller en källa som har lagts om eller
försvunnit. Det hanteras som normalt scraper-underhåll: logga/visa status,
undersök källan och låt nya lyckade körningar bygga historik efter åtgärd.

### 4. Kvalitetsgrindar för butiker

Butiksoffer-count varierar för mycket för att en count-grind ska vara meningsfull
(en butik kan ha 300 erbjudanden ena veckan och 14 nästa beroende på kampanjcykeln).

**Beslut (2026-05-14):** Ingen count-grind för butiker. Den enda regeln är:
- `count == 0` utan verified_empty-signal från källan → stoppa replace, returnera `failed`
- `count == 0` med verified_empty-signal → ok, returnera `success_empty`
- `count > 0` (oavsett hur många) → gå vidare

Robustheten för butiker ligger istället i korrekt felklassning:
- är svaret blockerat, rate-limitat, maintenance eller inloggningsrelaterat?
- saknas obligatoriska fält i ovanligt stor andel av produkterna?
- blev bara en kategori eller en sida skrapad när fler brukar finnas?

### 5. Diagnostik

Varje körning bör logga eller returnera en kompakt sammanfattning:

- discovery-metod
- parse-metod
- antal kandidater
- antal försökte URL:er eller sidor
- antal lyckade
- antal filtrerade och varför
- första 3 till 5 felorsakerna per typ
- om resultatet får ersätta befintlig data

För Playwright-skrapare bör vi även notera vilken selector, endpoint eller
response-fångst som faktiskt gav datan.

### 6. Canary- och smoke-kontroller

Lägg till en automatisk canary-kontroll per källa:

- recept: 1 till 3 kända recept-URL:er per källa som ska kunna parsas
- butiker: 1 känd endpoint eller sida per butik som ska ge strukturell respons
- inga fulla scrape-jobb behövs — canary testar bara att strukturen fortfarande fungerar

Canary-kontrollerna ska inte ersätta fulla scrape-jobb, men de ger snabbare
besked när en källa ändrat struktur.

**Beslut (2026-05-14):**
- Canary körs automatiskt **varannan dag** som bakgrundsjob (ingen manuell trigger)
- Resultatet sparas i DB per källa per körning (pass/fail)
- Alert triggas vid **4 konsekutiva fel** per källa (= 8 dagars störning) — detta
  hanterar tillfälliga avbrott och internetstörningar utan falsklarm
- Vid alert: **UI-indikator** (varningssymbol/status per källa på admin-sidan) +
  **loggfil**. Ingen Telegram eller push-notis — lösningen ska fungera för alla
  användare, inte bara Stefan
- Enstaka canary-fel ska inte poppa upp eller störa användaren i UI:t
- Vid nästa lyckade canary-körning återställs status automatiskt
- Vad eskalering bortom UI-indikatorn innebär (steg 2-3) är en separat fråga

### 7. Skruva befintligt `--test` för recept

Receptskraparna har redan en användbar smoke-växel: `--test` eller motsvarande
UI-väg kör i praktiken `scrape_all_recipes(max_recipes=20)` och sparar inget i
databasen. Den bör behållas, men göras tydligare och mer konsekvent.

Föreslagen uppdelning:

- `--test`: snabb sample-smoke som försöker plocka ned ett litet antal recept
  utan DB-save. Den svarar på "kan skraparen hitta och parsa något just nu?".
- `--canary`: deterministisk kontroll mot 1 till 3 kända recept-URL:er per
  källa. Den ska misslyckas om obligatoriska fält saknas.
- Discovery-diagnostik: kontrollerar sitemap/discovery separat, till exempel
  antal hittade sitemap-filer, antal kandidatrecept och om count är rimligt mot
  source-profilen. Detta ska inte vara en egen återkommande check, utan köras
  som fördjupad felsökning efter canary-larm.

För `--test` bör följande filas på:

- Gör teststorlek source-specifik men deklarerad. De flesta kan köra 20, medan
  långsammare källor kan ha 3 eller 5 om det är ett medvetet val.
- Visa alltid `status`, `reason`, antal kandidater, antal försök, antal lyckade
  och gärna parse-hit-rate när diagnostiken finns.
- Markera misstänkta testresultat tydligt. Om testet ber om 20 recept men bara
  får 2 är det inte nödvändigtvis ett hårt fel, men det ska synas.
- Säkerställ att testläge aldrig skriver recept, uppdaterar `scraped_at` eller
  triggar cache/image-flöden.
- Låt testläget återanvända samma parser- och discovery-kod som produktion, så
  testet inte blir ett parallellt lyckoflöde.

`--canary` bör vara strängare än `--test`:

- Kända URL:er ska parsas deterministiskt.
- Namn, URL och minst ett source-specifikt minimiantal ingredienser ska krävas.
- Bild, portioner, instruktioner och tid kan vara krav där källan normalt alltid
  exponerar dem.
- Exit/status ska vara maskinläsbar nog för support checks eller framtida CI.

## Tekniska kodskisser

Detta avsnitt är inte implementation. Kodsnuttarna visar hur respektive förslag
skulle kunna lösas när vi väl bestämmer oss för att bygga det.

### Source-profiler

En liten profil per receptkälla kan samla de beslut som annars blir utspridda i
varje scraper: förväntade counts, teststorlek, canary-URL:er, sitemap-fallbacks
och kända icke-recept.

**Beslut (2026-05-14):** Python dataclass, inte TOML. TOML används i detta
projekt för enkel data utan logik (synonymer, keyword-mappningar). Source-profiler
är tätt kopplade till scraperlogiken och kan behöva dynamiska värden — de hör
hemma i Python-kod bredvid respektive scraper.

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RecipeSourceProfile:
    source_id: str
    db_source_name: str
    base_url: str
    expected_min_urls: int | None = None
    expected_min_parse_rate: float | None = None
    test_limit: int = 20
    canary_urls: tuple[str, ...] = ()
    known_sitemap_urls: tuple[str, ...] = ()
    blocked_url_fragments: tuple[str, ...] = ()
    blocked_recipe_ids: tuple[str, ...] = ()
```

Exempel för Mathem, där de tidigare paketfelen blir explicit source-data:

```python
MATHEM_PROFILE = RecipeSourceProfile(
    source_id="mathem",
    db_source_name="Mathem.se",
    base_url="https://www.mathem.se",
    expected_min_urls=5000,
    expected_min_parse_rate=0.70,
    test_limit=20,
    known_sitemap_urls=tuple(
        f"https://www.mathem.se/sitemap/sv/recipes/{page}.xml"
        for page in range(1, 7)
    ),
    blocked_recipe_ids=(
        "808",
        "2182",
        "2184",
        "3182",
        "6861",
        "6862",
        "6863",
        "6864",
        "6865",
    ),
)
```

### Kördiagnostik

För att `--test`, `--canary`, scheduler och UI ska kunna prata samma språk kan
skraparna samla en liten diagnostikstruktur under körningen.

```python
from dataclasses import dataclass, field


@dataclass
class RecipeRunDiagnostics:
    discovery_method: str | None = None
    parser_method: str | None = None
    candidate_urls: int = 0
    selected_urls: int = 0
    attempted_urls: int = 0
    parsed_recipes: int = 0
    filtered_urls: int = 0
    failure_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def parse_rate(self) -> float:
        if self.attempted_urls <= 0:
            return 0.0
        return self.parsed_recipes / self.attempted_urls

    def count_failure(self, reason: str) -> None:
        self.failure_reasons[reason] = self.failure_reasons.get(reason, 0) + 1
```

Tanken är inte att varje scraper måste bli identisk, utan att varje scraper kan
returnera jämförbara nycklar:

```python
return RecipeScrapeResult.success(
    recipes,
    diagnostics={
        "discovery_method": diagnostics.discovery_method,
        "parser_method": diagnostics.parser_method,
        "candidate_urls": diagnostics.candidate_urls,
        "selected_urls": diagnostics.selected_urls,
        "attempted_urls": diagnostics.attempted_urls,
        "parsed_recipes": diagnostics.parsed_recipes,
        "parse_rate": diagnostics.parse_rate,
        "failure_reasons": diagnostics.failure_reasons,
    },
)
```

### Discovery-helper för recept

Discovery kan byggas som en trappa: robots, sitemap-index, source-specifika
fallbacks. Om ett steg fungerar behöver nästa steg inte användas.

```python
async def discover_recipe_urls(profile: RecipeSourceProfile) -> tuple[list[str], RecipeRunDiagnostics]:
    diagnostics = RecipeRunDiagnostics()

    sitemap_urls = await sitemaps_from_robots(profile.base_url)
    if sitemap_urls:
        diagnostics.discovery_method = "robots_sitemap"
    else:
        sitemap_urls = list(profile.known_sitemap_urls)
        diagnostics.discovery_method = "known_sitemap_fallback"

    recipe_urls: list[str] = []
    for sitemap_url in sitemap_urls:
        urls = await parse_sitemap_urls(sitemap_url)
        recipe_urls.extend(url for url in urls if looks_like_recipe_url(profile, url))

    recipe_urls = sorted(set(recipe_urls))
    recipe_urls = [
        url for url in recipe_urls
        if not is_blocked_recipe_url(profile, url)
    ]

    diagnostics.candidate_urls = len(recipe_urls)
    return recipe_urls, diagnostics
```

Source-reglerna hålls små och explicita:

```python
def is_blocked_recipe_url(profile: RecipeSourceProfile, url: str) -> bool:
    if any(fragment in url for fragment in profile.blocked_url_fragments):
        return True
    return any(f"/recipes/{recipe_id}-" in url for recipe_id in profile.blocked_recipe_ids)
```

### Parser-fallbacks

Parserordningen är: JSON-LD → microdata → source-specifik HTML → Playwright.
Varje parser returnerar antingen ett recept eller `None`.

**Beslut (2026-05-14):** Ingen gemensam PARSER_CHAIN-driver. Playwright kräver
en live browser-kontext och kan inte ta förhantat HTML som input — en gemensam
signatur `(url, html, profile)` fungerar inte för det sista steget.

Istället: lyft JSON-LD och microdata som delade helpers i `_common.py`
(JSON-LD-helper finns redan). Varje scraper anropar dessa helpers i sin egen
lokala kedja och lägger Playwright som ett explicit sista steg där det behövs.
Det ger samma ordning utan en felaktig gemensam abstraktion.

```python
# Mönster per scraper — inte en gemensam chain-driver
recipe = extract_json_ld_recipe(html)
if not recipe:
    recipe = extract_microdata_recipe(html)
if not recipe:
    recipe = parse_source_specific_html(url, html, profile)
if not recipe and profile.allow_playwright_fallback:
    recipe = await parse_rendered_recipe(url)  # eget fetch, ingen html-arg
```

### Kvalitetsgrind för recept

Kvalitetsgrinden bör ligga efter discovery/parse men före beslutet att ett
resultat är säkert nog. Thresholds bör vara source-specifika och börja mjukt.

```python
def evaluate_recipe_quality(
    profile: RecipeSourceProfile,
    diagnostics: RecipeRunDiagnostics,
    *,
    mode: str,
) -> tuple[bool, str | None]:
    if mode == "test":
        return True, None

    if profile.expected_min_urls and diagnostics.candidate_urls < profile.expected_min_urls:
        return False, "recipe_discovery_count_too_low"

    if (
        profile.expected_min_parse_rate is not None
        and diagnostics.attempted_urls >= 20
        and diagnostics.parse_rate < profile.expected_min_parse_rate
    ):
        return False, "recipe_parse_rate_too_low"

    return True, None
```

Användning i en full eller inkrementell körning:

```python
is_trustworthy, reason = evaluate_recipe_quality(profile, diagnostics, mode=mode)
if not is_trustworthy:
    return RecipeScrapeResult.failed(
        reason=reason,
        diagnostics=diagnostics_as_dict(diagnostics),
    )
```

### `--test`, `--canary` och discovery-diagnostik

CLI-stödet kan delas utan att ändra själva scrapinglogiken. `--test` fortsätter
köra samma kod som produktion, men med `max_recipes`.

```python
parser.add_argument("--test", action="store_true")
parser.add_argument("--canary", action="store_true")
```

Exempel på dispatch:

```python
if args.canary:
    result = await run_canary(PROFILE)
    print_canary_result(result)
    raise SystemExit(0 if result.ok else 1)

if args.test:
    result = await scraper.scrape_all_recipes(max_recipes=PROFILE.test_limit)
    print_test_result(result)
    raise SystemExit(0 if result.status in {"success", "partial"} else 1)
```

Discovery-diagnostik kan däremot återanvända samma helper när ett canary-larm
behöver förklaras:

```python
async def diagnose_canary_failure(profile: RecipeSourceProfile) -> dict:
    urls, diagnostics = await discover_recipe_urls(profile)
    return {
        "candidate_url_count": len(urls),
        "discovery_method": diagnostics.discovery_method,
        "failure_reasons": diagnostics.failure_reasons,
    }
```

Canary-koden bör vara deterministisk och hårdare än `--test`:

```python
async def run_canary(profile: RecipeSourceProfile) -> CanaryResult:
    failures = []
    for url in profile.canary_urls:
        recipe = await scrape_single_recipe(url)
        if not recipe:
            failures.append((url, "not_parsed"))
            continue
        if len(recipe.get("ingredients") or []) < 3:
            failures.append((url, "too_few_ingredients"))

    return CanaryResult(ok=not failures, failures=failures)
```

### Butikarnas kvalitetsgrind

Butiker kan få en motsvarande profil, men med felklassning och canary-endpoints
i stället för recept-discovery. Erbjudande-counts kan loggas som diagnostik, men
ska inte användas som stoppsignal när count är större än noll.

```python
@dataclass(frozen=True)
class StoreSourceProfile:
    store_id: str
    allow_verified_empty: bool = False
    canary_endpoints: tuple[str, ...] = ()
```

En enkel grind ska skydda mot tomma eller strukturellt trasiga resultat, men
inte stoppa legitima små kampanjveckor. Antal erbjudanden över noll är inte i
sig ett fel.

```python
def evaluate_store_quality(products: list[dict], signals: dict):
    if not products and signals.get("verified_empty"):
        return StoreScrapeResult.success_empty(reason="verified_empty")

    if not products:
        return StoreScrapeResult.failed(reason="empty_without_verified_empty")

    if signals.get("blocked") or signals.get("maintenance") or signals.get("auth_failed"):
        return StoreScrapeResult.failed(reason=signals.get("reason") or "store_unavailable")

    return StoreScrapeResult.success(products)
```

### Mathem butik: API-kartläggning före DOM-fallback

Mathem butik är DOM-tung idag. En framtida hårdning bör börja med att observera
nätverksresponser i Playwright och bara falla tillbaka till DOM om ingen stabil
JSON-väg hittas.

**Beslut (2026-05-14):** Network-kartläggning är ett obligatoriskt pre-req-steg
innan Mathem butik designas eller förändras i Fas 4. Kartläggningen ska göras
ordentligt och dokumenteras innan implementation påbörjas — inte ad-hoc under
kodning. Kartläggningen bör besvara:
- Finns ett stabilt JSON/GraphQL-API för erbjudanden?
- Kräver produktlistan scroll-triggers för att laddas fullständigt?
- Hur skiljs produkt-API från analytics/auth-trafik?
- Är endpoints stabila mellan sessioner eller session-bundna?

Resultat dokumenteras i ett separat kartläggningsdokument innan Fas 4 startar.
Kodskissen i detta avsnitt är indikativ — den kan inte implementeras förrän
kartläggningen är klar.

```python
api_payloads = []

page.on(
    "response",
    lambda response: maybe_collect_product_payload(response, api_payloads),
)

await page.goto(discount_url)
await page.wait_for_load_state("networkidle")

products = parse_products_from_payloads(api_payloads)
if products:
    return StoreScrapeResult.success(products, diagnostics={"path": "network_payload"})

products = await parse_products_from_dom(page)
return evaluate_store_quality(MATHEM_STORE_PROFILE, products, {"path": "dom"})
```

### `Mina recept` som per-URL-flöde

`Mina recept` bör använda en annan profil: ingen source-wide discovery, ingen
historisk count-grind, men tydlig status per URL.

```python
@dataclass
class MyRecipeUrlResult:
    url: str
    status: str
    parser_method: str | None = None
    recipe_id: str | None = None
    error_reason: str | None = None
```

Parserkedjan bör fortsätta en URL i taget:

```python
async def import_user_recipe_url(url: str) -> MyRecipeUrlResult:
    if not is_safe_user_url(url):
        return MyRecipeUrlResult(url=url, status="error", error_reason="unsafe_url")

    html = await fetch_limited_html(url)
    for parser_name, parser in MY_RECIPES_PARSERS:
        recipe = await parser(url, html)
        if recipe:
            recipe_id = await save_imported_recipe(recipe)
            return MyRecipeUrlResult(url=url, status="ok", parser_method=parser_name, recipe_id=recipe_id)

    return MyRecipeUrlResult(url=url, status="no_recipe", error_reason="no_supported_recipe_markup")
```

Canary för `Mina recept` bör därför testa parserkedjan, inte discovery:

```python
async def run_myrecipes_canary(urls: list[str]) -> list[MyRecipeUrlResult]:
    return [await import_user_recipe_url(url) for url in urls]
```

## Receptskrapare

### Arla

Nuläge:

- Använder en specifik sitemap-URL med query-parameter.
- Parsar främst JSON-LD.
- Har discovery cache, streaming save, seedad shuffle och viss hantering av
  404-kluster.

Förbättringar:

- Lägg till robots/sitemap-index discovery före den hårdkodade sitemap-URL:en.
- Behåll nuvarande URL som fallback.
- Lägg till canary-recept och parse-hit-rate-grind.
- Undersök HTML eller microdata-fallback för de fall JSON-LD ändras.
- Mät om 404-kluster ska klassas som temporärt fel eller permanent borta.

Prioritet: P1.

### Coop recept

Nuläge:

- Använder Coop recept-sitemap.
- Använder Playwright eftersom receptdatan renderas via JS.
- Har discovery cache och fail reason tracking.

Förbättringar:

- Lägg till alternativ sitemap-upptäckt via robots/sitemap-index.
- Se om JSON-LD eller intern data kan hämtas via nätverksrespons utan full DOM.
- Lägg till canary på både sitemap och ett renderat recept.
- Rapportera om Playwright fallback eller huvudväg gav datan.

Prioritet: P1.

### ICA recept

Nuläge:

- Använder tre hårdkodade recept-sitemaps.
- Parsar med HTTP och JSON-LD.
- Sorterar efter `lastmod` och använder discovery cache.

Förbättringar:

- Upptäck sitemap-sidor dynamiskt så en ny fjärde sitemap inte missas.
- Behåll nuvarande 1 till 3 som fallback.
- Lägg till canary-recept och låg discovery-count-grind.
- Undersök microdata eller HTML-fallback om JSON-LD saknas.
- Gör en lätt kodformsaudit i samband med arbetet, eftersom filen är central och
  bör vara enkel att diffgranska.

Prioritet: P1.

### Köket

Nuläge:

- Använder huvud-sitemap och URL-heuristik för att filtrera recept.
- Parsar JSON-LD.
- Har fail reason tracking, discovery cache och smart stopp när många recept
  redan finns.

Förbättringar:

- Gör filtreringen mer deklarativ: artikelmönster, videomönster och receptmönster
  samlas i source-profilen.
- Lägg till canary-recept för en vanlig receptsida och en sida som ska filtreras.
- Lägg till parse-hit-rate-grind så en ändrad mall inte blir ett tyst bortfall.
- Undersök om sitemap-index ger mer precisa recept-sitemaps än huvud-sitemap.

Prioritet: P2.

### Mathem recept

Nuläge:

- Upptäcker sitemap via robots och sitemap-index när det går.
- Har fallback till kända recipe-sitemaps.
- Parsar JSON-LD.
- Filtrerar vissa icke-recept, färdigpreppat och nu de kända 9 paket-URL:erna.

Förbättringar:

- Gör fallback-intervallet för recipe-sitemaps dynamiskt eller styrt från
  sitemap-index, så nya Mathem-sidor inte missas när antalet växer.
- Flytta kända icke-receptmönster till en tydlig source-profil eller konstant
  med kommentar om varför varje regel finns.
- Lägg till canary för ett riktigt recept och en känd paket-URL som ska nekas.
- Lägg till kontroll för plötslig ökning av icke-recept, eftersom Mathem verkar
  kunna lägga marknadspaket i receptytan.
- Undersök HTML/microdata-fallback om JSON-LD ändras.

Prioritet: P0/P1, eftersom detta redan har gett feldata.

### Jävligt gott

Nuläge:

- Använder en WordPress-lik recept-sitemap.
- Parsar HTML manuellt med OpenGraph och rubriksektioner.
- Har discovery cache och sekventiell, försiktig körning.

Förbättringar:

- Upptäck sitemap via `/wp-sitemap.xml` och robots före den hårdkodade
  recept-sitemapen.
- Lägg till JSON-LD/microdata-försök före manuell HTML om sajten exponerar det.
- Gör ingrediens- och instruktionsextraktion mer selector-baserad där det går.
- Canary för ett vanligt recept och ett edge case med annorlunda rubriker.

Prioritet: P1.

### Recepten

Nuläge:

- Har dynamisk robots/sitemap-index discovery och fallback.
- Parsar JSON-LD.
- Filtrerar URL:er under `/recept/` som slutar på `.html`.
- Har discovery cache och concurrent scraping.

Förbättringar:

- Lägg till HTML/microdata-fallback.
- Lägg till parse-hit-rate och expected-count-grind.
- Lägg till canary för en typisk sida.
- Gör en lätt kodformsaudit när filen ändå rörs, för att hålla discovery-flödet
  lättläst.

Prioritet: P2.

### Undertian

Nuläge:

- Använder en hårdkodad WordPress post-sitemap för recept.
- Parsar `window.recipeSettings` och OpenGraph.
- Kräver minst två ingredienser.
- Kör försiktigt med discovery cache.

Förbättringar:

- Upptäck WordPress sitemap-index dynamiskt via `/wp-sitemap.xml` och robots.
- Lägg till fallback till JSON-LD/microdata om `window.recipeSettings` ändras.
- Gör JS-objekt-extraktionen robustare mot formateringsändringar.
- Canary för ett vanligt recept och gärna ett recept med många sektioner.

Prioritet: P1.

### Zeta

Nuläge:

- Har dynamisk robots/sitemap-index discovery och kända fallback-sitemaps.
- Parsar JSON-LD.
- Har source-specifik HTML-fallback för ingredienser eftersom JSON-LD kan vara
  hopklistrad.
- Gör textnormalisering för kända Zeta-problem.

Förbättringar:

- Lägg till expected-count och parse-hit-rate-grind.
- Canary för ett recept där HTML-ingredienser krävs.
- Dokumentera Zeta-specifika textfixar i source-profilen.
- Behåll nuvarande specialfall, eftersom det är ett bra exempel på rätt sorts
  source-specifik fallback.

Prioritet: P2.

### Mina recept

`Mina recept` ska behandlas separat från de andra receptskraparna.

Grundskillnad:

- Den äger ingen källa.
- Den ska inte crawla en site brett.
- Den får godtyckliga URL:er från användaren.
- Den ska göra sitt bästa per URL, och tydligt säga vad som gick eller inte gick.
- Den ska inte använda source-wide expected counts eller discovery-grindar.

Nuläge:

- Har egen URL-statusmodell.
- Har säkerhetskontroller för URL, content-type och storlek.
- Försöker JSON-LD via gemensam extractor.
- Har microdata-fallback.
- Har Playwright-fallback med request routing som blockerar onödiga eller riskabla
  resurser.
- Har retry/statushantering per URL.

Förbättringar:

- Behåll den som en receptskrapare med per-URL-import av användarvalda länkar,
  inte som en source-wide scraper med egen sitemap/discovery.
- Kvalitetsgrinden ska vara per URL: "kunde vi skapa ett användbart recept?".
- Felmeddelanden bör vara användarvänliga: saknar ingredienser, sidan blockerar
  hämtning, sidan är inte ett recept, sidan kräver inloggning, sidan är för stor.
- Lägg gärna till fler tolkare, men bara som trygga per-sida-fallbacks:
  JSON-LD, microdata, vanliga recipe-card selectors, OpenGraph som stöddata,
  Playwright sist.
- Ingen historisk låg-count-logik.
- Ingen automatisk blocklist på domännivå utan tydligt skäl.
- Ingen bred site-discovery.
- Canary-tester bör vara syntetiska fixtures och ett par offentliga, stabila
  exempelsidor, inte en förväntan om att hela domäner ska fungera.
- `--test` för `Mina recept` bör betyda "testa ett litet antal pending eller
  explicita URL:er", inte "hitta N recept från en källa".
- `--canary` för `Mina recept` bör främst testa parserkedjan per URL:
  JSON-LD, microdata, recipe-card selectors, OpenGraph-stöddata och Playwright
  som sista steg.

Prioritet: separat spår. Den ska robustas, men inte pressas in i samma modell som
Arla, ICA eller Mathem.

## Butiksskrapare

### Willys

Nuläge:

- API-först för kampanjer.
- E-handel kan lösa butikskod via API, adress/cookies och Playwright.
- Playwright kan användas för att hitta butikskod och därefter gå tillbaka till
  API.
- DOM-fallback finns.
- Produktdetalj-API används för bättre namn, tillverkare och vikt.
- Maintenance-lägen klassas särskilt.

Förbättringar:

- Lägg till tydligare diagnostik för API-svar, pagination och dataväg, utan att
  blockera bara på lågt antal erbjudanden.
- Klassificera 403, 429 och icke-JSON som `blocked` eller temporärt fel i stället
  för tomt resultat.
- Lägg till canary för kampanj-API och produktdetalj-API.
- Behåll Axfood-specifik logik lokalt i Willys-pluginet. Dela bara helpers som
  är källagnostiska och faktiskt används brett av skraparna.

Prioritet: P1.

### Hemköp

Nuläge:

- Axfood REST API.
- E-handel använder Playwright främst för att lösa leveransbutik.
- Fallback via city-baserad online store lookup.
- Offline och online-kampanjer går via API med pagination.

Förbättringar:

- Lägg till canary för online/offline endpoints.
- Spara eller återanvänd senast fungerande e-handelsbutik-ID när det är rimligt.
- Klassificera API-fel tydligare.
- Undersök DOM- eller nätverksfallback för läget där Axfood-API:et ändras men
  sidan fortfarande visar erbjudanden.

Prioritet: P1.

### ICA butik

Nuläge:

- Fysisk butik använder Playwright och `window.__INITIAL_DATA__`.
- E-handel använder Playwright för butiksval och fångar produkt-API-responser.
- Har flera vägar: promotions URL, on-offer category API, legacy category
  fallbacks och sidhantering.
- Klassar om non-food där det behövs.

Förbättringar:

- Lägg till tydliga diagnostikfält för vilken väg som gav data.
- Lägg till canary för butikserbjudanden och e-handelsprodukt-API.
- Lägg till diagnostik för pagination/category coverage per location_type, utan
  att blockera bara på lågt antal erbjudanden.
- Dokumentera stabila account/store IDs som testfixtures om de finns.
- Se om vissa e-handelsvägar kan köras API-first efter att store context är känt.

Prioritet: P1.

### Coop butik

Nuläge:

- Store discovery via sitemap.
- Fysisk butik löser store page ID och hämtar erbjudanden via DKE API.
- Berikar originalpriser via Coop search API.
- E-handel har Playwright/DOM-flöde, variantmodaler och viss HTML-fallback.
- Har retry/backoff på flera delar.

Förbättringar:

- Lägg till canary för DKE API, search API och e-handelsflöde.
- Logga tydligare när API-nyckel, endpoint eller selector är orsaken.
- Lägg till diagnostik för om fysisk butik/e-handel bara hämtade en del av den
  förväntade strukturen, utan att blockera bara på lågt antal erbjudanden.
- Minska beroendet av CSS-klasser i e-handel där nätverksdata kan användas.
- Dokumentera endpoint-antaganden eftersom API-nycklar och interna endpoints är
  en uppenbar riskyta.

Prioritet: P1.

### Mathem butik

Nuläge:

- Playwright-only eftersom direkt HTTP blockeras.
- Scrapar discount-sidan via `data-testid="product-tile"`.
- Scrollar fram produkter.
- Berikar produktdetaljer från produktsidor och JSON-LD.
- Kräver ingen adress.

Förbättringar:

- Högsta behovet av live-kartläggning: undersök Network-flödet i Playwright för
  att se om en stabil JSON-endpoint kan användas i stället för DOM.
- Lägg till fallback-selectors runt produktkort, produktlänk, pris och bild.
- Lägg till canary för discount-sidan och ett produktkort.
- Lägg till shape-/selector-diagnostik så en selector-ändring kan skiljas från
  en legitim liten kampanjvecka.
- Skilj tydligt mellan blockering, tom kampanjsida och selector-brott.

Prioritet: P0/P1, eftersom DOM-only är den sköraste butiksvägen.

## Prioriterad genomförandeplan

### Fas 0: Baslinje utan beteendeförändring

- Kör eller läs igenom varje scraper och dokumentera nuvarande discovery-väg,
  parse-väg, förväntat count-intervall och vanliga fel.
- Lägg till diagnostik där den saknas, men utan att ändra spara-beslut.
- Bestäm canary-URL:er/endpoints per källa.

Resultat: vi vet vad som är normalt innan vi börjar stoppa resultat.

### Fas 1: Gemensamma kvalitetsgrindar

- Butiker: stoppa endast tomma resultat utan verified-empty och förbättra
  felklassning/shape-diagnostik.
- Recept: inför discovery-count och parse-hit-rate-grind.
- Se till att misstänkta resultat blir `failed` eller `partial` och därmed inte
  ersätter befintlig data.
- Lägg in tydliga reason-koder.

Resultat: färre tysta fel och färre dåliga ersättningar.

### Fas 2: Recept-discovery

- Inför gemensam robots/sitemap-index helper där det saknas.
- Migrera Arla, ICA, Jävligt gott och Undertian från ren hårdkodning till
  discovery först, hårdkodning som fallback.
- Behåll källornas nuvarande speciallogik där den behövs.

Resultat: ändrade sitemap-strukturer blir mindre farliga.

### Fas 3: Recept-parsing

- Standardisera JSON-LD och microdata-fallback.
- Lägg source-specifika HTML-fallbacks där det ger bäst ROI:
  Jävligt gott, Undertian, Mathem och ICA.
- Lägg canary-tester för minst ett lyckat recept per källa.

Resultat: malländringar behöver inte direkt bli stopp.

### Fas 4: Butiks-API och DOM-fallbacks

- Willys/Hemköp: strama upp Axfood-felklassning och canaries.
- ICA/Coop: gör diagnostiken tydligare för vilken intern väg som användes.
- Mathem: gör en ordentlig Network-kartläggning och bygg eventuell API-väg eller
  bättre DOM-fallbacks.

Resultat: butikarna blir lättare att felsöka och mindre beroende av en enda
selector.

### Krav: i18n för reason-koder

Alla reason-koder som kvalitetsgrindar eller diagnostik kan returnera och som
visas i UI måste ha motsvarande översättningsnycklar i `app/languages/sv/ui.py`
och `app/languages/en/ui.py` innan de deployas. Detta är ett hårt krav, inte
ett efterhandsarbete. Råa kodsträngar (`recipe_discovery_count_too_low` etc.)
får aldrig visas för användaren.

Arbetsordning: definiera reason-koder → lägg till i båda ui.py-filer → implementera grind.

### Fas 5: Tester och drift

- Lägg separata nätverkssmoke-tester som inte körs i vanliga unit tests.
- Behåll befintligt `--test` som snabb sample-smoke, men gör output/status
  konsekvent mellan receptskraparna.
- Lägg `--canary` eller motsvarande kontroll för kända URL:er per receptkälla.
- Ta bort `--discovery-check` som separat återkommande check/CLI-yta. Kör
  discovery-diagnostik som fördjupad felsökning efter canary-larm i stället.
- Lägg små fixtures för parserlogik där vi kan göra det lagligt och stabilt.
- Uppdatera runbook med hur man tolkar reason-koder och när man ska reload/retry.
- Dokumentera att scraper-kod inte ska skriva runtimefiler bredvid modulerna.
- När scraperbeteende ändras, uppdatera relevant dokumentation samtidigt:
  `docs/HOW_TO_ADD_SCRAPERS.md`, `docs/RECIPE_TEMPLATE.md`,
  `docs/STORE_TEMPLATE.md`, deploy-/installationsdokumentation och
  användarmanualerna där ändringen påverkar användarflöden eller drift.

Resultat: snabbare felsökning när en källa ändras.

## Granskningsnoteringar (tillagda 2026-05-14)

### 1. Kod-skisserna är indikativa — inte implementation-redo

Flera skisser i "Tekniska kodskisser"-avsnittet är felaktiga eller spekulativa
(PARSER_CHAIN, Mathem network-fångst). De ska inte följas rakt av vid
implementation — se besluten under respektive avsnitt. Skisserna visar intention,
inte korrekt signatur eller flöde.

### 2. ID-baserad blockering av Mathem-paket är bräcklig — komplettera med innehållsbaserad kontroll

`blocked_recipe_ids` i source-profilen kräver manuell uppdatering varje gång
Mathem lägger till ett nytt marknadspaket. Det har redan inträffat. Lägg till
ett innehållsbaserat komplement som bygger på de generella receptkraven: om en
sida har färre än 3 ingredienser eller saknar instruktioner → klassas den som
icke-recept, oavsett ID. Inte istället för ID-listan, utan som ett extra nät som
fångar nya fall utan manuell uppdatering.

### 3. `--discovery-check` som återkommande check är onödig

Automatisk canary varannan dag täcker hälsoövervakning. En separat återkommande
`--discovery-check` per scraper tillför komplexitet utan klart syfte. Däremot är
discovery-diagnostik värdefull som nästa felsökningssteg när en canary har
larmat: då kan vi avgöra om problemet ligger i sitemap/discovery eller i parsing
av kända recept-URL:er.

### 4. Latent bugg i discovery-logiken — åtgärda vid implementation

Nuvarande `discover_recipe_urls`-kod (och planens skiss kopierar den) *ersätter*
fallback-listan med robots-resultatet istället för att *komplettera* den. Om
robots.txt listar en sitemap-index som inte täcker alla recipe-sitemaps
(Mathems pagineringsproblem med 6 sitemaps) används fallback-URL:erna aldrig.
Korrekt beteende: ta unionen av robots-discovery och kända fallback-URL:er,
deduplicera, och rapportera vilken metod som gav vilka URL:er.

## Särskilda risker

- Interna API:er kan försvinna eller kräva nya headers/cookies.
- Playwright-flöden kan brytas av bot-skydd, consent-dialoger eller layoutbyte.
- API-nycklar i frontend kan roteras.
- Sajter kan sluta exponera JSON-LD.
- "Tomt" kan betyda både legitimt tomt och att vi inte hittade rätt data.
- För aggressiva fallbacks kan importera fel data. Detta är extra viktigt för
  recept, där artiklar, paket och produktsidor kan se receptliknande ut.

## Rekommenderad första arbetsordning

1. Lägg gemensamma kvalitetsgrindar och diagnostik, utan stora parserändringar.
2. Gör Mathem butik och Mathem recept till första source-specifika hårdning,
   eftersom båda redan visat typiska risker.
3. Gör dynamisk sitemap-discovery för Arla, ICA, Jävligt gott och Undertian.
4. Lägg canary/smoke-kontroller per källa.
5. Behandla `Mina recept` som eget spår med per-URL kvalitet och bättre
   användarnära felorsaker.

## Definition of done

En scraper anses robustad när:

- den har minst två rimliga discovery- eller data-vägar, eller en tydlig
  motivering till varför bara en finns
- den har source-specifik kvalitetsgrind
- den kan skilja på tomt, blockerat, temporärt fel och parse-fel
- den returnerar reason-koder som scheduler/spara-lager kan agera på
- den har minst en canary eller smoke-kontroll
- den ersätter inte befintlig data vid misstänkt låg eller trasig körning
- relevant dokumentation är uppdaterad när beteendet, CLI-flaggor,
  driftförväntningar eller användarflöden ändras
- specialfall som `Mina recept` har egna kriterier i stället för att tvingas in
  i samma modell som källor med egen discovery
