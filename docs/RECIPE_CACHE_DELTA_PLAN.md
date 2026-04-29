# Plan: Inkrementell cacheuppdatering efter receptskrap

## Aktuell status

Senast uppdaterad: 2026-04-29 12:07.

- Fas: Implementation, smoke-verifiering och dokumentationsuppdatering pågår.
- Pågår: sista kontroll efter att inkrementella skrapgränser gjorts konsekventa
  över receptskraparna:
  ett konfigurerat antal betyder mål för sparbara recept, medan skraparna får
  prova en dold URL-buffert med hårt tak. UI-progress visar hittade recept mot
  användarens mål, inte interna URL-försök.
- Klart: memory-cache är bortstädad och planen är uppdaterad med
  UI-exclude/hard-delete-förtydliganden; receptsparflödet returnerar nu
  skapade/ändrade/borttagna recept-ID:n. Inkrementella helpers för
  recipe-IR och recipe term-index finns. `cache_delta.py` har nu en
  `apply_recipe_delta`-entrypoint som previewar berörda recept, verifierar mot
  full preview under probation och patchar `recipe_offer_cache` utan truncate.
  Routerflödet använder recipe-delta för incremental scrape och för full scrape
  när högst 50 recept berörs; UI-exclude/restore/delete triggar samma kedja i
  bakgrunden.
- Verifierat i dev-container: no-op-delta returnerar utan lockad DB-skrivning.
  En single-recipe preview föll först tillbaka eftersom compiled term-index låg
  på äldre matcher/offer-compiler-version, vilket verifierade fallbackvägen.
  Efter en full rebuild med aktuella versioner gick single-recipe delta igenom:
  med full-preview/probation patchades 1 cache-rad och totalen var stabil
  (`10282` cacheträffar). Utan full-preview tog samma single-recipe delta ca
  `847ms` och bevarade `cache_metadata.total_recipes=10757`.
  Patch-transaktionen är rollback-verifierad genom ett avsiktligt
  CHECK-constraint-fel efter DELETE; den gamla cache-raden låg kvar efter
  rollback.
- Run-all-kön har kvar första versionens strategi: ingen per-scraper delta där.
  Den räknar däremot nu cache-berörda recept separat från "nya recept", så en
  slutlig full rebuild triggas även om en run-all bara uppdaterar befintliga
  recept.
- Dokumentation uppdateras samtidigt i användarmanualerna, README,
  scraper-guiden, receptmallen och testdokumentet så cache-delta och
  receptantalens mål/buffert-semantik inte beskrivs som äldre full-rebuild eller
  strikt URL-limit.
- Slutkontroll: AST/syntax är OK för alla ändrade Python-filer,
  `git diff --check` är OK, och kvarvarande `memory_cache`/`cache_use_memory`
  träffar är begränsade till den avsiktliga startup-migrationen för att droppa
  gamla kolumner. `deal-meals-dev-web` är omstartad och healthcheck är OK; vid
  startup gjorde den en varm full rebuild på ca `4531ms`.
- Nästa: kodreview och commit.

## Bakgrund

Efter en inkrementell receptskrap kan loggen visa att bara ett fåtal recept
skapades, till exempel:

```text
Database: created=6, updated=0, spell_corrections=0, errors=0
Cache computed: 8580 recipes in 17163ms
```

Det är praktiskt för långsamt och tekniskt onödigt. Om sex nya recept har
skapats ska cacheflödet i normalfallet bara behöva:

1. kompilera dessa sex recept till recept-IR,
2. uppdatera deras rader i receptens termindex,
3. matcha dessa sex recept mot aktuella erbjudanden,
4. patcha `recipe_offer_cache` för just dessa recept.

Dagens flöde triggar istället full cacheberäkning efter receptskrap via
`compute_cache_async()`. Det gör att hela receptmängden går igenom cachepipen
även när ändringen är liten.

Memory-cache-läget har städats bort före denna implementation. Recept-delta
behöver därför bara stödja DB-cache och behöver ingen fallback för separata
in-memory views.

## Motiv

Målet är att minska väntetiden efter inkrementell receptskrap, särskilt innan
nya recept kan användas i rekommendationerna och innan automatisk bildhämtning
är klar.

Nuvarande varma full rebuild ligger ungefär på:

```text
time_ms: ca 4300ms
compile_ms: ca 700ms
score_ms: ca 2100ms
```

Men när kompilerad receptdata behöver byggas om kan samma flöde hamna runt:

```text
time_ms: ca 17000ms
compile_ms: ca 13400ms
```

Det visar att den stora risken inte är själva matchningen, utan att en liten
receptändring kan orsaka en stor kompilerings- och cachekostnad.

## Nuvarande tekniska läge

- `app/routers/recipes.py` triggar `compute_cache_async()` efter receptskrap
  när `recipes_found > 0`.
- `app/scrapers/recipes/_common.py::save_recipes_to_database()` returnerar
  räknare som `created` och `updated`, men inte vilka recept-ID:n som skapades
  eller ändrades.
- `app/cache_manager.py::compute_cache()` har redan stöd för `recipe_ids`,
  men bara säkert i preview-läge.
- `app/cache_manager.py::_save_cache_to_db()` truncatar hela
  `recipe_offer_cache`.
- `app/languages/sv/ingredient_matching/compiled_recipes.py`
  har full refresh för `compiled_recipe_match_data`.
- `app/languages/sv/ingredient_matching/term_indexes.py`
  har full refresh för `compiled_recipe_term_index`.
- Offer-delta finns redan i `app/cache_delta.py`, men receptskrapflödet använder
  inte en motsvarande recept-delta.

## Viktig fallgrop

Kör inte detta som en "snabb fix":

```python
compute_cache(recipe_ids=changed_ids, persist=True)
```

Det ser ut som en begränsad rebuild, men `persist=True` går fortfarande genom
`_save_cache()`, och DB-vägen truncatar hela `recipe_offer_cache`. Det skulle
alltså riskera att ersätta hela cachetabellen med bara patchresultatet.

Rätt princip är:

```python
compute_cache(
    recipe_ids=changed_ids,
    persist=False,
    return_entries=True,
    run_kind="recipe_delta_patch_preview",
)
```

och därefter en separat patch-operation:

```sql
DELETE FROM recipe_offer_cache WHERE found_recipe_id IN (...);
INSERT INTO recipe_offer_cache (...) VALUES (...patch entries...);
```

Recept som inte längre matchar något erbjudande ska alltså bara få sin gamla
cache-rad borttagen.

## Beslut: cachepatch ska vara ny snabb helper

Det finns två möjliga sätt att skriva tillbaka deltaresultatet:

- **A. Materialisera hela cachen i minnet och återanvänd `_save_cache_to_db()`.**
  Det är enkelt och liknar offer-deltans beprövade mönster, men skriver om alla
  cache-rader. Då försvinner mycket av prestandavinsten för små receptdeltan.
- **B. Lägg till en ny patch-helper som bara gör DELETE+INSERT för berörda
  recept-ID:n i samma transaktion.**
  Det är ny kod, men det är den väg som faktiskt ger önskad effekt.

Planen väljer **B** för normal drift. A kan fortfarande vara användbar i
dev/probation-läge för paritetskontroll, men ska inte vara standardvägen för
incremental scrape.

## Beslut: egna runtime-flaggor

Recept-delta ska gate:as separat från offer-delta, så att respektive delta kan
slås av under utrullning utan att påverka den andra.

Föreslagna settings:

- `cache_recipe_delta_enabled: bool = True`
- `cache_recipe_delta_verify_full_preview: bool = True`
- `cache_recipe_delta_skip_full_preview_after_probation: bool = True`
- `cache_recipe_delta_probation_history_file: str | None = None`
- `cache_recipe_delta_probation_min_ready_streak: int = 3`
- `cache_recipe_delta_probation_min_version_ready_runs: int = 3`

Första implementationen kan börja med `cache_recipe_delta_enabled` och
`cache_recipe_delta_verify_full_preview`. Om probation-mönstret inte byggs
direkt ska planen ändå lämna plats för samma modell som offer-deltan använder.

## Föreslagen implementation

### 1. Returnera ändrade recept-ID:n från sparflödet

Uppdatera `save_recipes_to_database()` så stats innehåller:

- `created_recipe_ids`
- `updated_recipe_ids`
- `changed_recipe_ids`
- `removed_recipe_ids` när relevant

`changed_recipe_ids` ska vara `created_recipe_ids + updated_recipe_ids`
deduplicerat. Alternativt kan stats utelämna `changed_recipe_ids` helt och låta
delta-anroparen göra unionen, men begreppet måste vara entydigt i
implementationen.

För `StreamingRecipeSaver` ska dessa listor aggregeras över batchar.

Praktiskt:

- Vid update: `existing.id` finns redan tillgängligt och läggs i
  `updated_recipe_ids`.
- Vid insert: återanvänd befintligt SELECT-by-URL-mönster efter commit, samma
  princip som redan används för spell corrections.
- Lägg bara till ID:n efter lyckad commit. `IntegrityError`-fallet ska fortsätta
  räknas som error/skipped enligt dagens beteende och får inte hamna i
  `created_recipe_ids`.
- `StreamingRecipeSaver._add_stats()` aggregerar idag bara skalärer. Lägg till
  explicit `.extend()`/dedupe för listnycklarna.
- Första versionen kan vara konservativ och behandla alla updates som
  `changed_recipe_ids`.
- En senare förbättring kan jämföra receptets source-hash och ignorera rena
  `scraped_at`-touches.

Verifiering:

- Kör en liten sparning med ett nytt recept och kontrollera att `created=1` och
  att `created_recipe_ids` innehåller ett UUID.
- Kör en sparning mot befintlig URL och kontrollera att `updated_recipe_ids`
  innehåller befintligt recept-ID.
- Kontrollera att befintliga callers som bara läser `created`/`updated` inte
  påverkas.

### 2. Lägg till inkrementell recipe-IR refresh

Skapa en helper, exempelvis:

```python
refresh_compiled_recipe_match_data_for_recipe_ids(
    recipe_ids: list[str],
    remove_recipe_ids: list[str] | None = None,
) -> dict
```

Den ska:

- ta samma advisory lock som full refresh,
- hålla lock, läsning, delete och insert i samma DB-session/transaktion eftersom
  `pg_advisory_xact_lock` är transaktionsbundet,
- läsa aktuella `FoundRecipe`-rader för `recipe_ids ∪ remove_recipe_ids`,
- bygga compiled rows för alla dessa ID:n som fortfarande finns i
  `found_recipes` med befintlig `build_compiled_recipe_match_row()`. Det är
  viktigt för UI-exclude: full refresh behåller sådana recept i
  `compiled_recipe_match_data` med `is_active=False`, och incremental helpern
  ska matcha det beteendet,
- jämföra lästa rader mot förväntade ID:n. Om ett ID inte längre finns i
  `found_recipes` är det en hard-delete och ska behandlas som removed internt,
  inte ignoreras tyst eller orsaka exception,
- ta bort gamla compiled rows för berörda ID:n,
- lägga in nya compiled rows för de ID:n som fortfarande finns.

Hard-deletade ID:n behöver i normalfallet ingen explicit compiled-delete,
eftersom `compiled_recipe_match_data` har FK-cascade mot `found_recipes`.
En defensiv DELETE för saknade ID:n är ändå ofarlig, men den får inte användas
som beteende för UI-exclude där `FoundRecipe`-raden finns kvar.

Verifiering:

- Kör helpern med ett känt recept-ID.
- Kontrollera att `compiled_recipe_match_data` har exakt en aktiv rad för ID:t.
- Exkludera ett recept och kontrollera att raden finns kvar med
  `is_active=False`.
- Kontrollera att `compiler_version` är aktuell.
- Kontrollera att full refresh fortfarande fungerar.

### 3. Lägg till inkrementell recipe term-index refresh

Skapa en helper, exempelvis:

```python
refresh_compiled_recipe_term_index_for_recipe_ids(
    recipe_ids: list[str],
    remove_recipe_ids: list[str] | None = None,
) -> dict
```

Den ska:

- använda aktuell offer-term-manifest från `compiled_offer_term_index`,
- falla tillbaka till full rebuild om offer-term-manifest saknas,
- ta samma advisory lock som full recipe term-index refresh,
- hålla lock, delete och insert i samma DB-session/transaktion eftersom
  `pg_advisory_xact_lock` släpps på commit/rollback,
- behandla saknade `recipe_ids` som `remove_recipe_ids`, på samma sätt som
  recipe-IR-helpern,
- radera gamla termrader för ändrade/borttagna recept,
- ladda compiled payload för ändrade recept,
- bygga nya termrader för ändrade recept,
- insert:a bara dessa rader.

Verifiering:

- Kör helpern med ett känt recept-ID.
- Kontrollera att `compiled_recipe_term_index` bara får rader för detta recept
  med aktuell `term_manifest_hash`.
- Kontrollera att borttagna recept-ID:n får sina termrader raderade.
- Kontrollera att full term-index refresh fortfarande fungerar.

### 4. Lägg till recept-delta för cachetabellen

Lägg till en ny entrypoint, exempelvis i `cache_delta.py`:

```python
apply_recipe_delta(
    changed_recipe_ids: list[str],
    removed_recipe_ids: list[str] | None = None,
    source: str | None = None,
) -> dict
```

Flöde:

0. Normalisera input:
   - deduplicera ID-listor,
   - om samma ID finns i både `changed_recipe_ids` och `removed_recipe_ids`
     vinner remove och ID:t tas bort från changed-listan,
   - om båda listor är tomma efter normalisering, returnera no-op direkt utan
     att sätta cachemetadata till `computing`.
1. Kör genom `run_cache_operation()` så det inte krockar med full rebuild eller
   offer-delta. Använd `operation_name="recipe_delta"`.
2. Sätt cachemetadata till `computing`.
3. Validera att aktiv cache finns och är `ready`; annars fallback till full
   rebuild.
4. Uppdatera recipe-IR för `changed_recipe_ids + removed_recipe_ids`. Helpern
   ska skriva aktiva/inaktiva compiled rows för ID:n som fortfarande finns och
   behandla saknade ID:n som hard-delete.
5. Uppdatera recipe term-index för `changed_recipe_ids + removed_recipe_ids`.
   Changed IDs får nya termrader; removed IDs får gamla termrader raderade.
6. Kör `cache_manager.refresh_cache(..., persist=False, return_entries=True,
   recipe_ids=changed_recipe_ids)`.
7. Kör en ny patch-helper som i en och samma transaktion:
   - tar bort cache-rader för `changed_recipe_ids + removed_recipe_ids`,
   - insert:ar patch entries för de ändrade recept som faktiskt matchade,
   - lämnar alla andra cache-rader orörda.
8. Uppdatera cachemetadata till `ready` med `total_matches` från
   `SELECT COUNT(*) FROM recipe_offer_cache` efter patch-commit. Återanvänd
   `_update_cache_metadata(...)` i `cache_delta.py` istället för att skriva en ny
   metadata-upsert.
9. Uppdatera unmatched-offer-count.
10. Logga `CACHE_RECIPE_DELTA_SUMMARY`.

Ordningen i steg 4-6 är load-bearing. Recipe-IR och termindex måste vara
uppdaterade och commitade innan patch preview körs. Annars riskerar en parallell
offer-delta att se recipe changes och falla ut med `recipe_changes_detected`.

Om steg 4 eller 5 kastar exception, till exempel vid korrupt receptdata,
FK-konflikt eller låsproblem, ska `apply_recipe_delta` fånga felet, sätta en
tydlig fallback_reason som `ir_refresh_failed` eller
`term_index_refresh_failed`, återställa cachemetadata från `computing` och
delegera till full rebuild via samma kedja som övriga fallback-fall.

Patch-helpern får inte använda `_save_cache()` eller `_save_cache_to_db()`,
eftersom båda representerar "ersätt hela cachetillståndet". Den ska vara en ny
funktion, till exempel:

```python
patch_recipe_offer_cache_entries(
    patch_entries: list[dict],
    changed_recipe_ids: list[str],
    removed_recipe_ids: list[str] | None = None,
) -> dict
```

`source` ska användas som receptskrapans källa/scraper-id i loggning och
probation-historik, motsvarande `store_name` i offer-deltans flöde.

Verifiering:

- Kör no-op med tomma input-listor och kontrollera att cachemetadata inte sätts
  till `computing`.
- Delta med sex nya recept ska logga `changed_recipe_count=6`.
- Loggen ska inte visa en full `Cache computed: 8580 recipes...` efter en ren
  incremental scrape, om inte delta faller tillbaka.
- Emittera en egen `CACHE_RECIPE_DELTA_SUMMARY` för delta-specifika fält.
- Emittera även en `CACHE_REBUILD_SUMMARY` med `run_kind="recipe_delta"` eller
  motsvarande om observability-vyer ska fånga recept-delta i samma sökväg som
  full rebuild.
- `recipe_offer_cache` ska behålla tidigare rader för alla andra recept.
- Om ett ändrat recept inte längre matchar något erbjudande ska dess gamla
  cache-rad försvinna.
- Simulera SQL-fel mellan DELETE och INSERT, till exempel med en patch-entry som
  bryter `recipe_category`-CHECK-constraint, och verifiera att transaktionen
  rullas tillbaka så inga cache-rader försvinner.
- Kontrollera att `cache_metadata.total_matches` efter patch motsvarar
  `SELECT COUNT(*) FROM recipe_offer_cache`.

### 5. Uppdatera unmatched-offer-count säkert

Eftersom planen väljer patchmönster B finns inte hela cache-entry-listan i
minnet efter skrivning. Därför behövs en DB-baserad variant, till exempel:

```python
refresh_unmatched_offer_count_from_db()
```

Den kan återanvända samma SQL-princip som endpointens fallback:

```sql
SELECT COUNT(*) FROM offers;

SELECT COUNT(DISTINCT COALESCE(mo->>'offer_identity_key', mo->>'id'))
FROM recipe_offer_cache c, jsonb_array_elements(c.match_data->'matched_offers') mo
```

`_unmatched_count` ska sedan sättas till:

```text
max(0, total_offers - matched_offer_ids)
```

Detta matchar dagens `update_unmatched_offer_count(entries)`-semantik.

Verifiering:

- Jämför count före och efter full rebuild.
- Kör recept-delta och kontrollera att `/api/matching/unmatched-offers/count`
  returnerar samma värde som fallback-queryn.
- Om implementationen tillfälligt använder mönster A, där hela cachet
  materialiseras i minnet, kan befintliga `update_unmatched_offer_count(entries)`
  återanvändas. Vid mönster B ska DB-varianten användas.

### 6. Wire:a receptskrapen

I `app/routers/recipes.py`:

- Vid `mode == "test"`: gör inget, som idag.
- Vid incremental med `changed_recipe_ids`: kör recept-delta.
- Recept-delta ska följa samma fallback-struktur som offer-delta i
  `db_saver.py`: settings-flagga, försök delta, logga fallback reason, kör full
  rebuild om delta inte applicerades.
- `apply_recipe_delta` är synkron, precis som `apply_verified_offer_delta`.
  Routerintegration från async-context ska därför köra den via `run_in_executor`
  eller en tunn `apply_recipe_delta_async`-wrapper, så event-loopen inte blockas.
- Vid full/overwrite: använd recept-delta om ändringsmängden är liten och
  tydlig, annars full rebuild.
- Vid saknade ID-listor: fallback till full rebuild.
- Vid run-all: första versionen ska fortsätta med full rebuild på slutet.
  Senare kan changed IDs samlas över hela kön och köras som en gemensam delta.

Praktisk första version:

- Börja med enskild incremental scrape.
- Tillåt även full/overwrite att använda delta när
  `changed_recipe_ids + removed_recipe_ids <= 50`, inga breda source-clears har
  gjorts, och alla berörda ID:n är kända.
- Full/overwrite-delta kräver att borttagna/stale recept-ID:n fångas innan
  delete. `delete_stale_source_recipes()` returnerar idag bara antal, så den
  måste utökas till att returnera ID:n, eller så ska flödet falla tillbaka till
  full rebuild.
- Flöden som använder `save_recipes_to_database(..., clear_old=True)` gör en
  bred source-delete före insert och ska falla tillbaka till full rebuild om de
  inte refaktoreras så borttagna ID:n samlas in först.
- Låt run-all ligga kvar på full rebuild tills en tydlig "queue done"-hook och
  ID-aggregation är på plats.
- Det minskar risk och ger ändå förbättring för fallet "Koket hämtade 6 nya".

Verifiering:

- Stäng av `cache_recipe_delta_enabled` och kontrollera att incremental scrape
  kör full rebuild.
- Slå på flaggan och kontrollera att incremental scrape försöker delta först.
- Kör en incremental Koket-skrap med få nya recept.
- Kontrollera att `CACHE_RECIPE_DELTA_SUMMARY` skrivs.
- Kontrollera att automatisk bildhämtning fortfarande startar efter cachejobbet.
- Kör full/overwrite med färre än eller lika med 50 kända ändrade/borttagna
  recept och kontrollera att delta används.
- Kör full/overwrite med fler än 50 ändrade/borttagna recept, eller med okända
  borttagningar, och kontrollera att full rebuild används.
- Kör full/overwrite via ett `clear_old=True`-flöde och kontrollera att full
  rebuild används tills det flödet kan rapportera exakta removed IDs.

### 7. Hantera UI-exclude och manuella borttagningar

Recept kan ändra cachepåverkan utan att komma från skrapflödet, till exempel
när användaren exkluderar ett recept i UI:t eller tar bort ett recept. Dessa
flöden behöver antingen:

- trigga `apply_recipe_delta(removed_recipe_ids=[...])`, eller
- falla tillbaka till full rebuild om berörda ID:n inte finns tillgängliga.

Explicit mapping:

| Flöde | Delta-lista |
| --- | --- |
| UI-exclude | `removed_recipe_ids` för cache/termindex, men recipe-IR-helpern ska skriva `is_active=False` eftersom raden finns kvar |
| UI-include / återaktivera | `changed_recipe_ids` |
| Hard-delete | `removed_recipe_ids` |

Detta ska inte lämnas åt `classify_current_recipe_changes()` inne i offer-delta,
eftersom recept-deltans entrypoint annars bara ser ID:n från sparflödet.

Verifiering:

- Exkludera ett recept via UI och kontrollera att dess cache-rad tas bort.
- Ångra/återaktivera om sådant flöde finns, och kontrollera att receptet kan
  patchas in igen.
- Radera ett recept och kontrollera att cache, compiled recipe IR och termindex
  inte längre har rader för ID:t.
- För delete-flöden som identifierar recept via URL eller source ska ID:n läsas
  före delete. Om ID:n inte kan fångas ska flödet trigga full rebuild.

## FTS-verifiering

`compute_cache(recipe_ids=...)` filtrerar idag recept efter FTS först och
applicerar sedan `recipe_ids`-subset. Det är onödigt dyrt för små deltan och
kan bli en tyst risk om FTS-kolumnen inte är synkront uppdaterad.

Verifierat i nuvarande schema och lokal DB:

- `found_recipes.search_vector` är en `tsvector`.
- `update_found_recipes_search_vector` är en `BEFORE INSERT OR UPDATE`-trigger.
- Triggern använder `found_recipes_search_vector_update()`.

Det betyder att FTS i nuvarande setup är synkron, inte async. Trots det bör
recept-delta helst undvika FTS-prefiltret när `recipe_ids` anges och istället
läsa exakt dessa ID:n direkt, med samma `enabled_sources` och `excluded`-filter.
Candidate routing avgör sedan om receptet faktiskt matchar något erbjudande.

Kodval: ändra `compute_cache()` så `requested_recipe_ids is not None` använder
en direkt DB-läsväg för dessa ID:n och hoppar över `_get_recipes_by_fts(...)`.
Det bevarar `enabled_sources`/`excluded`-filtrering men undviker FTS för små
deltan. Full rebuild utan `recipe_ids` ska fortsätta använda FTS som idag.

Första versionen kan låta alla `recipe_ids` hoppa över FTS. Om stora
recipe-id-mängder senare blir vanliga kan man lägga till tröskel, till exempel
"direkt-ID-väg under 500 ID:n, annars FTS/full rebuild".

Verifiering:

- Kör patch preview för ett nytt recept-ID och kontrollera att receptet väljs
  även om det bara finns i `recipe_ids`.
- Kontrollera att ett recept utan relevanta offertermer får sin gamla cache-rad
  borttagen och inte genererar en ny entry.
- Kontrollera att full rebuild fortfarande använder FTS som tidigare.

## Fallback-regler

Använd full rebuild istället för recept-delta när:

- cachemetadata saknas eller inte är `ready`,
- `recipe_offer_cache` är tom men det finns aktuella erbjudanden,
- matcher/compiler-version har ändrats,
- offer-term-manifest saknas eller är inkonsistent,
- källor enable/disable:as,
- matching preferences ändras,
- starred source ändras,
- full/overwrite-skrap har raderat eller uppdaterat fler än 50 recept,
- full/overwrite-skrap har gjort bred source-clear eller har okända borttagna
  recept-ID:n,
- stale-delete/full-sync-flöde returnerar bara antal borttagna recept, inte
  recept-ID:n,
- `recipe_ids` saknas för ett flöde som bara vet antal ändrade recept,
- recept-delta kastar exception.

Fallback ska loggas tydligt, till exempel:

```text
CACHE_RECIPE_DELTA_SUMMARY {"applied": false, "fallback_reason": "..."}
```

## Fallgropar

- `persist=True` med `recipe_ids` får inte användas för patchning eftersom DB-save
  truncatar hela cachetabellen.
- `_save_cache()` och `_save_cache_to_db()` får inte användas för receptpatchen;
  de representerar hel ersättning av cachetillståndet.
- Updates kan vara semantiskt oförändrade. Om alla updates patchas blir det
  korrekt men kan bli onödigt dyrt vid full scrape.
- UI-exclude och manuella delete-flöden måste också trigga delta eller full
  rebuild. Det räcker inte att bara lyssna på receptskrapens `created`.
- Hard-delete måste fånga berörda recept-ID:n före delete. Efter delete finns
  inte längre `FoundRecipe`-raden kvar att bygga cleanup-listor från.
- Samma ID kan i race-fall hamna i både changed och removed. Input ska
  normaliseras så remove vinner.
- Recept som går från match till ingen match måste få sin gamla cache-rad
  borttagen.
- Borttagna eller exkluderade recept måste bort från cache och termindex.
  Däremot ska UI-exclude inte ta bort raden ur `compiled_recipe_match_data`;
  full refresh behåller raden med `is_active=False`, och incremental helpern
  ska göra samma. Hard-delete rensar `compiled_recipe_match_data` via FK-cascade.
  `compiled_recipe_term_index` har ingen FK mot `found_recipes`, så termrader
  för permanent borttagna recept måste raderas explicit.
- Offer-term-manifest styr recipe term-index. Om manifestet ändras måste
  receptens termindex byggas om mot det nya manifestet.
- Advisory locks som används här är transaktionsbundna. Om helpern tar lock i
  en session och sedan gör delete/insert i en annan session finns inget skydd.
- FTS är synkron i nuvarande DB, men recept-delta bör ändå inte vara beroende av
  FTS-prefilter för explicit angivna `recipe_ids`.
- Run-all kan starta många skrapare i följd. Delta ska helst köras en gång på
  slutet, inte efter varje källa.
- Cachemetadata får inte lämnas i `computing` om delta fallerar.
- `persist=False` sätter inte cachemetadata till `computing` åt oss. Deltaflödet
  måste själv sätta och återställa status i både success-, fallback- och
  exception-vägar.
- Om recipe-delta faller tillbaka till full rebuild ska fallbacken följa samma
  struktur som offer-delta: tydlig reason, full rebuild via låst cacheoperation,
  och historik/probation om den är aktiverad.
- Automatisk bildhämtning ska inte starta före cachejobbet om UI:t förutsätter
  att cachefasen är klar.

## Mätbara mål

För en incremental scrape med 1-10 nya recept:

- recept-delta bör normalt gå klart under 2 sekunder,
- full `Cache computed: ...` ska inte köras,
- `CACHE_RECIPE_DELTA_SUMMARY` ska innehålla antal ändrade recept,
- `recipe_offer_cache` ska ha samma slutresultat som en full preview,
- användaren ska kunna fortsätta utan att sidan väntar på en 10-20 sekunders
  full rebuild.

För full/overwrite med högst 50 kända ändrade/borttagna recept gäller samma
mål. Över tröskeln, eller när borttagna ID:n inte är kända, är full rebuild det
förväntade och säkra beteendet.

Målen förutsätter den nuvarande DB-cache-vägen. Det finns inte längre någon
aktiv memory-cache-väg som recept-delta behöver patcha.

Tröskeln på 2 sekunder förutsätter delta utan parallell full-preview-verifiering.
Med `cache_recipe_delta_verify_full_preview=True`, vilket bör vara default i
första probation-perioden, kan total tid hamna runt 1.5-2 sekunder eftersom
hela compute-pipen körs för verifieringen. Det är acceptabelt under probation;
efter probation faller verifieringen bort och målet bör hållas med bättre
marginal.

## Paritetskontroll och probation

Under utveckling och första utrullning bör recept-delta kunna köras med
frivillig full preview:

1. Ta snapshot av aktiv `recipe_offer_cache`.
2. Kör patch preview för ändrade recept.
3. Materialisera snapshot + patch i minnet.
4. Kör full preview utan persist.
5. Jämför fingerprint per `found_recipe_id`.
6. Logga mismatch-sample om något skiljer.

Rekommenderat beslut: ha full-preview-verifiering på som default i början via
`cache_recipe_delta_verify_full_preview=True`, och låt
`cache_recipe_delta_skip_full_preview_after_probation` kunna stänga av den först
efter N gröna körningar. Det speglar offer-deltans säkerhetsmodell men kan
implementeras i en senare commit om första steget behöver hållas mindre.

Återanvänd `delta_probation_runtime.append_runtime_probation_history(...)` med
en trigger som `recipe_scrape` eller `recipe_delta`. Om
`cache_recipe_delta_probation_history_file` pekar på en separat fil från
offer-deltans historik hålls probation för recept-delta och offer-delta isär,
men samma runtime-gate-mönster kan återanvändas.

## Definition of Done

- `save_recipes_to_database()` returnerar recept-ID:n för skapade/ändrade
  recept.
- Streaming-sparning aggregerar recept-ID:n korrekt.
- Det finns helpers för inkrementell refresh av `compiled_recipe_match_data`.
- Det finns helpers för inkrementell refresh av `compiled_recipe_term_index`.
- Det finns en recept-delta-entrypoint som patchar `recipe_offer_cache` utan
  truncate.
- Explicit `recipe_ids`-preview läser ändrade recept direkt eller verifierar
  att FTS inte kan tappa dem.
- Tomma input-listor ger no-op utan cachemetadata-skrivning.
- Saknade changed IDs behandlas som removed IDs.
- Överlapp mellan changed och removed normaliseras så removed vinner.
- UI-exclude behåller compiled recipe IR-raden med `is_active=False`, men tar
  bort cache- och termindexrader.
- Recept-delta styrs av en egen settings-flagga.
- Async-routerflöden kör sync-deltan via executor/wrapper.
- Unmatched-offer-count beräknas som `total_offers - matched_offer_ids`.
- `cache_metadata.total_matches` räknas från `recipe_offer_cache` efter patch.
- Incremental scrape använder recept-delta när changed IDs finns.
- UI-exclude/delete triggar recept-delta eller full rebuild.
- Full scrape använder recept-delta när högst 50 kända recept påverkas.
- Full/overwrite-flöden med `clear_old=True` eller stale-delete utan removed IDs
  faller tillbaka till full rebuild.
- Stora/oklara ändringar faller tillbaka till full rebuild.
- Loggarna skiljer tydligt på full rebuild och recept-delta.
- Fallback från recept-delta till full rebuild följer offer-deltans mönster.
- Minst en manuell test med få nya recept visar delta i loggen.
- Minst en paritetskontroll mot full preview är gjord i dev.
