# Cache Fallback Runbook

Den här runbooken är för lägen där recipe-delta eller offer-delta ofta faller
tillbaka till full rebuild, eller där cachebyggandet känns oväntat långsamt.

Målet är att snabbt avgöra om fallbacken är förväntad, tillfällig eller ett
tecken på att cache/IR/index behöver städas eller byggas om.

## Snabb Triage

1. Leta efter de korta summary-raderna först:

   ```bash
   docker compose logs --since=30m web \
     | rg "CACHE_RECIPE_DELTA|CACHE_REBUILD|cache decision|fallback|ERROR|WARNING"
   ```

2. Kör cache doctor:

   ```bash
   curl -ks https://localhost:${APP_PORT:-20080}/api/cache/doctor | jq
   ```

   I dev kan porten vara `20070` i stället:

   ```bash
   curl -ks https://localhost:20070/api/cache/doctor | jq
   ```

3. Titta på tre saker i doctor-svaret:

   - `status`: ska helst vara `ok`.
   - `metadata.last_operation`: senaste cacheoperationen.
   - `cache_metadata:operation_history`: fallback-rate, senaste fallbackar och
     `delta_ratio_threshold_pct`.

4. Om `cache_metadata:consecutive_fallbacks` varnar, börja med
   `fallback_reasons`. Tre fallbackar i rad är inte automatiskt katastrof, men
   det är en signal att titta närmare.

## När Det Inte Är Ett Problem

Det här är normalt beteende:

- `recipe_delta_decision=full` med `recipe_delta_reason=ratio_above_threshold`
  betyder att för många recept berördes jämfört med aktiv receptbas. Systemet
  valde full rebuild avsiktligt.
- Första körningen efter större deploy, compiler-/matcher-versionbyte eller
  tom cache kan behöva full rebuild.
- Enstaka `cache_operation_in_progress` betyder oftast bara att en annan
  cacheoperation redan körs.
- Under probation kan total tid bli högre eftersom full-preview verifierar att
  delta och full rebuild skulle ge samma resultat.

## Vanliga Recipe-Delta Reasons

| Reason | Betydelse | Praktisk åtgärd |
| --- | --- | --- |
| `ratio_above_threshold` | Ändringen är större än delta-gränsen. | Normalt. Låt full rebuild gå klart. |
| `delta_ids_missing` | Skrapningen ändrade recept men saknar ID-listor för delta. | Kontrollera save-resultatet från skraparen. Kör support-checks om detta dyker upp efter kodändring. |
| `recipe_delta_disabled` | `CACHE_RECIPE_DELTA_ENABLED` är av. | Slå på igen om det inte var avsiktligt. |
| `cache_not_ready` | Cachemetadata var inte `ready` när delta skulle starta. | Vänta på pågående jobb. Om status fastnar: kör doctor och därefter manuell full rebuild. |
| `active_cache_empty` | Aktiv cache är tom trots att offer finns. | Kör full rebuild. Om den blir tom igen, kontrollera offer/filter/källor. |
| `cache_operation_in_progress` | En annan cacheoperation höll låset. | Vänta. Om det händer ofta, kontrollera schemalagda jobb och run-all-tider. |
| `recipe_ir_refresh_failed` | Inkrementell recipe-IR refresh misslyckades. | Kör doctor. Misstänk korrupt receptdata, stale schema eller migrationsproblem. |
| `recipe_term_index_refresh_failed` | Inkrementell term-index refresh misslyckades. | Kör doctor. Om term-index är trasigt: kör full rebuild efter att felet är fixat. |
| `recipe_delta_full_preview_failed` | Full-preview kunde inte räknas fram. | Läs närliggande ERROR/WARNING i loggen. Full rebuild är rätt fallback. |
| `recipe_delta_patch_preview_failed` | Patch-preview för ändrade recept kunde inte räknas fram. | Kontrollera recept-ID:n, compiled recipe payload och term-index. |
| `recipe_delta_scope_missed_preview_diff` | Full-preview ändrade recept som inte fanns i delta-listan. | Delta-listan är ofullständig. Kör full rebuild och undersök ID-fångst i skrap-/UI-flödet. |
| `materialized_patch_mismatch` | Patchat resultat matchar inte full-preview. | Kör full rebuild. Om det upprepas: misstänk planner-/term-index-/scope-bugg. |
| `recipe_cache_patch_failed` | DELETE/INSERT-patchen mot `recipe_offer_cache` misslyckades. | Kör doctor. Kontrollera DB-fel i loggen. Full rebuild återställer baseline. |
| `recipe_delta_exception` / `recipe_delta_unexpected_error` | Oväntat exception i delta-kedjan. | Läs tracebacken, kör doctor, kör full rebuild efter fix. |

## Vanliga Offer-Delta Reasons

| Reason | Betydelse | Praktisk åtgärd |
| --- | --- | --- |
| `recipe_changes_detected` | Offer-delta vägrar köra när recipe-IR inte matchar recepten. | Kör recipe/full rebuild först. Detta skyddar mot att offer-delta baseras på fel receptbaseline. |
| `planner_missed_preview_diff` | Offer-delta-plannern täckte inte full-preview-diffen. | Låt fallback/full rebuild gå. Upprepat fel kräver planner-analys. |
| `materialized_patch_mismatch` | Materialiserad offer-delta matchar inte full-preview. | Kör full rebuild. Upprepat fel betyder delta-planerings- eller materialiseringsbugg. |
| `ingredient_routing_fullscan_baseline_mismatch` | Hint-routing och fullscan-baseline gav olika resultat under verifiering. | Behåll fallback. Kontrollera ingredient-routing probation innan hint-first får lita på sig själv. |
| `delta_exception:*` | Offer-delta kastade exception. | Läs loggen runt felet och låt fallback/full rebuild etablera ny baseline. |

## Vad Man Gör I Praktiken

### Enstaka fallback

1. Låt jobbet köra klart.
2. Kör `GET /api/cache/doctor`.
3. Om doctor är `ok` och nästa körning använder delta igen behövs ingen åtgärd.

### Flera fallbackar i rad

1. Kör doctor och notera `fallback_reasons`.
2. Kör en manuell full rebuild för att etablera ren baseline.
3. Kör en liten inkrementell receptskrapning.
4. Om samma fallback kommer tillbaka direkt är det sannolikt kod/data, inte bara
   stale baseline.

### Cache fastnar i `computing`

1. Kontrollera om ett cachejobb fortfarande kör:

   ```bash
   docker compose logs --since=15m web | rg "Starting cache operation|Cache computed|CACHE_"
   ```

2. Om inget jobb kör men doctor visar `computing`, kör en manuell full rebuild.
3. Om det återkommer: leta efter exception mellan "status computing" och
   fallback/full rebuild i loggen.

### Full rebuild är långsam

Titta på `CACHE_REBUILD`-raden:

```text
CACHE_REBUILD run=full status=ready mode=compiled cached=... time=... compile=... route=... score=... write=...
```

- Hög `compile`: compiled IR eller term-index byggs/laddas långsamt.
- Hög `route`: candidate routing eller term-index-scope är dyrt.
- Hög `score`: själva matchningen dominerar.
- Hög `write`: DB/COPY eller disk är flaskhalsen.

Om `CACHE_REBUILD_SUMMARY` behövs, använd `jq` eller filtrera ut bara fält du
behöver. Den är avsiktligt detaljerad men svårläst som vanlig loggrad.

## Bra Kommandon

Primär logg utan gamla rader:

```bash
docker compose logs -f --tail=0 web
```

Senaste cachehändelser:

```bash
docker compose logs --since=1h web \
  | rg "CACHE_RECIPE_DELTA|CACHE_REBUILD|CACHE_REBUILD_SUMMARY|CACHE_RECIPE_DELTA_SUMMARY"
```

Varningar och fel:

```bash
docker compose logs --since=1h web | rg "WARNING|ERROR|CRITICAL|fallback"
```

Accesslogg om du behöver HTTP-bruset separat:

```bash
docker compose exec web tail -f /app/logs/access.log
```

Support-checks i dev:

```bash
docker compose exec -T -w /app web python tests/run_app_support_checks.py
```

## Säker Fallback

Om du är osäker och cacheläget ser inkonsekvent ut:

1. Kör doctor.
2. Kör full rebuild.
3. Kör doctor igen.
4. Kör en liten inkrementell skrapning och verifiera att delta antingen
   appliceras eller faller tillbaka med en begriplig reason.

Full rebuild är långsammare men ska vara den säkra baseline-vägen.
