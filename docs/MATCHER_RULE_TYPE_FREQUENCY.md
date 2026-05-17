# Matcher Rule Type Frequency

Generated: 2026-05-17
Source: `app/tests/batch_review_questions.md`

This is a heuristic scan of local batch-review fix notes. It is used to
choose which `dm matcher add ...` subcommands are worth building first.

Classified fix-note lines: 214

| Pattern | Count | Share | CLI status |
|---|---:|---:|---|
| PNB add | 129 | 60.3% | `dm matcher add pnb <keyword>` (future) |
| FPB add | 41 | 19.2% | `dm matcher add fpb <keyword>` (future) |
| KSBC add | 7 | 3.3% | `dm matcher add ksbc <keyword>` (future) |
| BDPK add | 1 | 0.5% | `dm matcher add bdpk <keyword>` (future) |
| keyword_extra_parent fan-out | 1 | 0.5% | `dm matcher add keyword-extra-parent <canonical>` |
| no_match_policy add | 1 | 0.5% | `dm matcher add no-match-policy <policy>` (future) |
| specialty qualifier | 12 | 5.6% | `dm matcher add specialty <keyword>` (future) |
| STOP_WORDS extension | 12 | 5.6% | `dm matcher add stop-word <word>` (future) |
| Other/manual | 11 | 5.1% | Manual |

## Decision

Phase 4 ships only `keyword-extra-parent`. The PNB/FPB-like patterns are
more frequent, but they encode more policy-specific blocker semantics.
`keyword_extra_parent` is lower risk and already has a uniform registry,
fixture, inventory, and sanity-test shape.

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
- line 3048: - TOML synonym `savoykål` ↔ `savojkål` (recept skriver "savojkål", produkter märkta "Savoykål" — samma grönsak)
- line 3096: - TOML `offer_extra_keyword`: `falafelpulver` → `falafelmix` (Falafelpulver 200g Sevan = samma produkt)
- line 3214: - TOML `ingredient_parent`: `persiljestjälk`/`persiljestjälkar` → parent `persilja` — persiljeblad-produkter matchar persilje-stjälkar
