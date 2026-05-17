# Matcher Rule Type Frequency

Generated: 2026-05-17
Source: `app/tests/batch_review_questions.md`

This is a heuristic scan of local batch-review fix notes. It is used to
choose which `dm matcher add ...` subcommands are worth building first.

Classified fix-note lines: 219

| Pattern | Count | Share | CLI status |
|---|---:|---:|---|
| PNB add | 129 | 58.9% | `dm matcher add pnb <keyword>` (future) |
| FPB add | 41 | 18.7% | `dm matcher add fpb <keyword>` (future) |
| KSBC add | 7 | 3.2% | `dm matcher add ksbc <keyword>` (future) |
| BDPK add | 1 | 0.5% | `dm matcher add bdpk <keyword>` (future) |
| keyword_extra_parent fan-out | 1 | 0.5% | `dm matcher add keyword-extra-parent <canonical>` |
| ingredient_parent add | 4 | 1.8% | `dm matcher add ingredient-parent ...` (candidate) |
| keyword_synonym add | 2 | 0.9% | `dm matcher add keyword-synonym ...` (candidate) |
| offer_extra_keyword add | 4 | 1.8% | `dm matcher add offer-extra-keyword ...` (candidate) |
| recipe_routing_helper add | 0 | 0.0% | `dm matcher add recipe-routing-helper ...` (future candidate) |
| no_match_policy add | 1 | 0.5% | `dm matcher add no-match-policy <policy>` (future) |
| specialty qualifier | 12 | 5.5% | `dm matcher add specialty <keyword>` (future) |
| STOP_WORDS extension | 12 | 5.5% | `dm matcher add stop-word <word>` (future) |
| Other/manual | 7 | 3.2% | Manual |

## Decision

Runtime-table patterns such as PNB/FPB/KSBC, STOP_WORDS, and broad
specialty qualifiers are frequent but remain outside the Step 2 CLI
target until those tables have a safe declarative source or tested
codemod surface. Step 2 uses this report to choose one registry-owned
A2 command at a time. A simple TOML family should have at least 5
distinct observed uses, at least 5% share, or an active real matcher
change waiting for that exact command before it is promoted from
candidate to implementation target.

## Examples

### PNB add
- line 73: - PNB citron: kosttillskott/tran/möllers/berocca/vitamin well (supplements ≠ citron)
- line 74: - PNB lamm: lammkorv (match via 'lamm' substring i 'lammstek' text bypassed lammstek PNB)
- line 75: - PNB olivolja: chili (36 recept); vitlök: krutonger+kryddsmör (38+33 recept)

### FPB add
- line 79: - FPB frön: vaniljstång/vaniljsocker (frökärnor ≠ vanilla-kontext)
- line 2754: - FPB `mjölk`: add 1år/1ar/unna (baby formula ≠ cooking milk)
- line 2770: - FPB: `'tuc': {'cantuccini'}` — TUC brand (3-letter) substring-matched 'cantucciniskorpor'; blocked.

### KSBC add
- line 3380: - KSBC `kikärtor`/`kikärter`: add `spadet`, `kikärtsspad`, `aquafaba` — aquafaba/spadet-recept ≠ hela kikärtor (Stefan-precedent rank 1455)
- line 3382: - KSBC `äppeljuice`: add `granatäpple` — "granatäppeljuice"-ingrediens ≠ vanlig äppeljuice
- line 3383: - KSBC `granatäpple`: add `granatäpplejuice`/`granatäppeljuice` variants — hel granatäppelfrukt ≠ juice

### BDPK add
- line 3314: **Q61 — Röd habanero → generisk "röd chili" (rank 4916):** **Beslut:** Löst tillsammans med Q76. BDPK `chili`/`chilipeppar`: {habanero, naga, bhut jolokia, ghost pepper, carolina reaper, scotch bonnet}.

### keyword_extra_parent fan-out
- line 3555: Q54-2 — citrusfrukter routing gap (rank 5353): **Beslut: A (TOML). LÖST.** Implementation: 8 `keyword_extra_parent.toml`-entries (citron/lime/apelsin/mandarin/clementin/klementin/grapefrukt/blodapelsin → citrusfrukter). Citrus-offers exponerar nu "citrusfrukter" som extra parent keyword på offer-sidan; recept som ber om "3-4 citrusfrukter (valfri sort)" matchar alla 8 sorters citrus-produkter, men en specifik citron-recept broadar INTE till lime/apelsin (verifierat via negative sanity test). Coupled match_bridge.toml entry tillagd (bridge_citrusfrukter_family) — wiring-check passar eftersom KEYWORD_EXTRA_PARENTS täcker varje offer_pattern. Fixtures + inventory + regression test + baseline promoterat. Track B wrapper grön förutom 5 PRE-EXISTING inventory line_ref/coverage failures (icke-relaterade till denna fix; finns redan på main).

### ingredient_parent add
- line 2756: - TOML aliases: toastbrödskivor→bröd, bladpersilja→persilja, hirs (new ingredient parent entries)
- line 3214: - TOML `ingredient_parent`: `persiljestjälk`/`persiljestjälkar` → parent `persilja` — persiljeblad-produkter matchar persilje-stjälkar
- line 3283: - TOML `ingredient_parent`: `scotchbonnet`/`scotch bonnet` → parent `habanero` (scotch bonnet = habanero-variant)

### keyword_synonym add
- line 2969: - TOML keyword_synonym: `gelantinblad` → `gelatinblad` (vanlig stavfel i recept)
- line 3048: - TOML synonym `savoykål` ↔ `savojkål` (recept skriver "savojkål", produkter märkta "Savoykål" — samma grönsak)

### offer_extra_keyword add
- line 2926: - Selleri-routing: ✅ FIXAD — offer_extra_keyword: bladselleri/blekselleri/stjälkselleri → 'selleri' (bekräftat: blad/blek/stjälkselleri = samma grönsak)
- line 2933: - Chokladströssel vs generiskt strössel: FPB `strössel: {chokladströssel}` kräver TOML offer_extra_keyword för chokladströssel-produkter först — skippad, hanteras separat.
- line 3079: - TOML `offer_extra_keyword`: `falafelpulver` → extra keyword `falafelmix` (Falafelpulver 200g Sevan matchar inte "240 g Falafelmix" — samma produkt, annat namn)

### no_match_policy add
- line 2409: - urkärnade oliver → new no_match_policy entry in no_match_policy.toml +

### specialty qualifier
- line 111: - Batch 10-13 specialty pass: explicit chocolate-button variants are kept
- line 259: - `3 dl Långkornigt Ris`: black/red specialty rice should not match ordinary
- line 521: Accepted/fixed: `laxfilé` now uses the lax specialty qualifiers so varmrökt,

### STOP_WORDS extension
- line 80: - STOP_WORDs: barber, mycket, knappar, dragons, tallrik, hållare, sorterade
- line 2755: - STOP_WORD: `veggie` (generic label bleeding into ingredient extraction)
- line 2783: - STOP_WORD: `'mortel'` — "Mortel Granit" (kitchen tool) matched "stötta i mortel" ingredient text.

### Other/manual
- line 3345: - **OBS**: Riven kokos FN (4959/4962) = stale cache (live matcher matchar korrekt), ej kodbug — löses vid nästa dev reload
- line 3407: - matching.py: extend hel-vs-malen-block till `kanel` och `kardemumma` — "Kanel/Kardemumma Hel" blockeras när ingrediensen anger "malen" (analogt med nejlika-fix Q44)
- line 3408: - (Shard 6/5049-5058: inga nya kodfixar — alla fynd var precedent-bundna eller stale cache)
