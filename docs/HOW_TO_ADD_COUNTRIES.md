# How to Add a New Country

This guide explains what you need to create to support a new market/country
(e.g., German grocery stores with German recipes). Each country gets its own
language folder — even if two countries share a language (e.g., Germany and
Austria), they will likely need separate configurations due to different
stores, product naming conventions, and local terminology.

## Architecture Overview

All country/language-specific data lives in `app/languages/<code>/` (e.g.,
`app/languages/de/` or `app/languages/en_gb/`).
The matching engine (`app/recipe_matcher.py`) imports constants and functions from
the language layer — it contains **no hardcoded Swedish words in its logic**.
Comments in `recipe_matcher.py` use Swedish examples for illustration, but the
executable code references only imported constants.

```
app/
├── recipe_matcher.py          # Language-neutral matching engine
├── cache_manager.py           # Cache builder (imports from language layer)
├── languages/
│   ├── categories.py          # Shared category constants (English keys)
│   ├── i18n.py                # Translation loader
│   ├── market_runtime.py      # Lightweight runtime adapter for country helpers
│   ├── sv/                    # Swedish (complete implementation)
│   │   ├── ui.py              # UI translations
│   │   ├── normalization.py   # Text normalization (character fixes, variants)
│   │   ├── categories.py      # Category display names
│   │   ├── category_utils.py  # Category detection from product names
│   │   ├── food_filters.py    # Food vs non-food + cooking vs candy classification
│   │   ├── pantry.py          # Pantry matching ignore words
│   │   ├── recipe_filters.py  # Recipe-level filters (boring recipes, junk food, tools)
│   │   ├── spell_check.py     # Spell-check exclusions and inflection data
│   │   ├── store_units.py     # Store unit aliases/default unit
│   │   ├── ingredient_matching_audit.py   # Audit tooling (not part of runtime)
│   │   └── ingredient_matching/
│   │       ├── engine.py               # Pipeline orchestrator + MATCHER_VERSION
│   │       ├── matching.py             # matches_ingredient() / matches_ingredient_fast()
│   │       ├── match_result.py         # MatchResult data class
│   │       ├── extraction.py           # extract_keywords_from_product/ingredient()
│   │       ├── extraction_patterns.py  # Regex patterns for extraction
│   │       ├── normalization.py        # Multi-word space normalizations (SPACE_NORM)
│   │       ├── ingredient_data.py      # INGREDIENTS dict + IngredientMatchData class
│   │       ├── offer_data.py           # OFFER_EXTRA_KEYWORDS (one-way offer-side)
│   │       ├── synonyms.py             # INGREDIENT_PARENTS (generic→specific)
│   │       ├── parent_maps.py          # PARENT_MATCH_ONLY
│   │       ├── blocker_data.py         # PRODUCT_NAME_BLOCKERS, RECIPE_INGREDIENT_BLOCKERS
│   │       ├── processed_rules.py      # PROCESSED_PRODUCT_RULES, PROCESSED_FOODS
│   │       ├── specialty_rules.py      # SPECIALTY_QUALIFIERS
│   │       ├── match_filters.py        # KSC, spice-vs-fresh, secondary ingredient patterns
│   │       ├── carrier_context.py      # Carrier flavor products (don't extract flavor)
│   │       ├── dairy_types.py          # Yogurt/kvarg type validation constants
│   │       ├── validators.py           # Validation functions (yogurt, cheese, etc.)
│   │       ├── form_rules.py           # Fresh herb keywords, product form rules
│   │       ├── compound_text.py        # Compound word matching rules
│   │       ├── keywords.py             # Stop words + general keyword constants
│   │       ├── recipe_text.py          # Buljong/fond text parsing
│   │       ├── recipe_context.py       # Recipe ingredient text parsing helpers
│   │       ├── recipe_matcher_support.py  # FOND_TYPE_CONTEXT, classification constants
│   │       └── seasonal.py             # Seasonal/buffet filtering
│   └── en_gb/                 # UK scaffold (UI/address + starter helpers)
│       ├── ui.py
│       ├── normalization.py
│       ├── categories.py
│       ├── category_utils.py
│       ├── food_filters.py
│       ├── recipe_filters.py
│       ├── recipe_matcher_backend.py
│       └── ingredient_matching/
```

The `en_gb` folder is intentionally a scaffold. It can be selected in the UI
and loaded with `MATCHER_LANGUAGE=en_gb`, but the heavy matcher currently
delegates to the Swedish implementation until UK-specific rules are written.
This is useful as a smoke-test path, not as a production-ready UK matcher.

## Files You Need to Create

### Required (minimum viable)

| File | Purpose | Effort |
|------|---------|--------|
| `ui.py` | UI translations (copy from `en_gb/ui.py`, translate) | Low |
| `normalization.py` | Character fixes for your language, word variants | Medium |
| `categories.py` | Category display names in your language | Low |
| `category_utils.py` | Map product names → categories using your language keywords | Medium |
| `food_filters.py` | Non-food detection + cooking classification constants | Medium |
| `pantry.py` | Measurement/cooking words ignored by pantry search | Low |
| `spell_check.py` | Inflection suffixes and default false-positive exclusions | Low |
| `store_units.py` | Store unit aliases and default unit | Low |

### Required (for recipe matching)

| File | Purpose | Effort |
|------|---------|--------|
| `ingredient_matching/` | The big one: keyword extraction, matching rules, all constants | **High** |
| `recipe_filters.py` | Boring recipe patterns, junk food keywords, kitchen tools | Low |
| `recipe_matcher_backend.py` | Adapter that imports the country-specific matching functions | Medium |

## What Each File Contains

### `normalization.py`
- `normalize_market_text()` for offer/recipe text
- Character normalization (accents, diacritics, common OCR errors)
- `normalize_ingredient()` — clean up ingredient text

### `pantry.py`, `spell_check.py`, `store_units.py`
These small files keep shared app code from hardcoding one market's stop words,
inflections, false-positive spell corrections, or unit defaults. The shared
code loads them through `app/languages/market_runtime.py`.

### `food_filters.py`
All constants for classifying products:
- `FOOD_CATEGORIES` / `NON_FOOD_CATEGORIES` — category-level classification
- `FOOD_INDICATORS` / `NON_FOOD_STRONG` / `NON_FOOD_INDICATORS` — product name keywords
- `NON_FOOD_BRANDS` — brands that never match recipes
- `COOKING_CHIP_COMPOUNDS`, `PLAIN_CHIPS_SALT_WORDS` — cooking chips vs snack chips
- `NUT_KEYWORDS`, `NUT_CANDY_INDICATORS`, `NUT_SNACK_INDICATORS` — cooking nuts vs candy nuts
- `COOKING_CHOCOLATE_WORDS`, `CHOCOLATE_CANDY_INDICATORS` — baking chocolate vs candy
- `VEG_QUALIFIER_WORDS`, `VEG_PRODUCT_INDICATORS` — vegetarian/vegan classification
- Helper functions: `is_cooking_chips()`, `is_cooking_nuts()`, `is_cooking_chocolate()`

### `recipe_filters.py`
- `BORING_RECIPE_PATTERNS` — "how to boil rice" type recipes to skip
- `JUNK_FOOD_KEYWORDS` — candy/soda words to filter out
- `KITCHEN_TOOLS` — non-buyable items listed as ingredients (piping bags etc.)
- `LEFTOVER_PREFIX` — "leftovers of..." prefix
- `SUB_RECIPE_WORD` — sub-recipe reference word
- `is_boring_recipe()` function

### `ingredient_matching/`
This is the largest matching package for Swedish. It is a modular package split
across ~20 files. Key files and what they contain:

| File | Key contents |
|------|-------------|
| `engine.py` | Pipeline orchestrator, `MATCHER_VERSION` |
| `matching.py` | `matches_ingredient()`, `matches_ingredient_fast()` |
| `extraction.py` | `extract_keywords_from_product()`, `extract_keywords_from_ingredient()` |
| `extraction_patterns.py` | Regex patterns used during extraction |
| `normalization.py` | Multi-word space normalizations (e.g. "corn flakes" → "cornflakes") |
| `ingredient_data.py` | `INGREDIENTS` dict — the main keyword data per ingredient |
| `offer_data.py` | `OFFER_EXTRA_KEYWORDS` — one-way offer-side keyword additions |
| `synonyms.py` | `INGREDIENT_PARENTS` — generic→specific parent mapping |
| `parent_maps.py` | `PARENT_MATCH_ONLY` — parents that only match via parent logic |
| `blocker_data.py` | `PRODUCT_NAME_BLOCKERS`, `RECIPE_INGREDIENT_BLOCKERS` |
| `processed_rules.py` | `PROCESSED_PRODUCT_RULES`, `PROCESSED_FOODS` — false positive prevention |
| `specialty_rules.py` | `SPECIALTY_QUALIFIERS` — specialty/qualifier matching rules |
| `match_filters.py` | KSC (keyword suppressed by context), spice-vs-fresh rules |
| `carrier_context.py` | Carrier flavor products (don't extract flavor as keyword from e.g. chips) |
| `dairy_types.py` | Yogurt/kvarg type validation constants |
| `validators.py` | Validation functions (yogurt, cheese type matching) |
| `form_rules.py` | Fresh herb keywords, product form rules |
| `compound_text.py` | Compound word matching rules |
| `keywords.py` | Stop words + general keyword constants |
| `recipe_text.py` | Buljong/fond text parsing, `BULJONG_TYPE_PREFIXES` |
| `recipe_matcher_support.py` | `FOND_TYPE_CONTEXT`, `CLASSIFICATION_MEAT_KEYWORDS`, `CLASSIFICATION_FISH_KEYWORDS`, vegetarian labels |
| `seasonal.py` | Seasonal/buffet filtering |
| `match_result.py` | `MatchResult` data class |

The Swedish implementation is heavily commented — use it as reference when building
a new language package. Start with `ingredient_data.py` (the `INGREDIENTS` dict) and
`engine.py` to understand the pipeline entry point.

### `category_utils.py`
- `guess_category()` — product name → category string
- Brand detection, meat keyword lists, lactose-free detection
- `_reclassify()` — fix miscategorized products (nuts in candy → pantry, etc.)
- Imports `NUT_KEYWORDS`, `NOT_COOKING_NUTS` from `food_filters.py`

## Step-by-Step Process

1. **Start with `ui.py`** — copy `en_gb/ui.py`, translate all strings
2. **Create `normalization.py`** — character fixes for your language
3. **Create `categories.py`** — translate category display names
4. **Create `food_filters.py`** — adapt non-food detection to your market
5. **Create `recipe_filters.py`** — translate boring patterns, junk food words
6. **Create `category_utils.py`** — keyword-based category detection
7. **Create `recipe_matcher_backend.py`** — start from the `en_gb` wrapper, then replace delegated imports with your country-specific modules
8. **Create `ingredient_matching/`** — this is the bulk of the work:
   - Start with the constants (keyword lists, regex components)
   - Then the `INGREDIENTS` dict (largest single piece)
   - Then the matching functions
9. **Set recipe full-text search config** — set `RECIPE_FTS_CONFIG` in `.env`
   to the PostgreSQL text search config used by your recipe language
   (`swedish`, `english`, etc.) and keep `recipe_matcher_backend.RECIPE_FTS_CONFIG`
   aligned with it.

## Before Enabling a New Country in Production

Do not switch production to a new `MATCHER_LANGUAGE` just because the folder
loads. A real country backend should pass this checklist first:

- `app/languages/<code>/recipe_matcher_backend.py` imports your country-specific
  matcher modules instead of delegating to `sv`.
- `app/languages/<code>/ingredient_matching/` contains real extraction,
  ingredient data, blocker, synonym, and validation rules for the local recipe
  and product language.
- `MATCHER_LANGUAGE` and `RECIPE_FTS_CONFIG` are set together. For example, a
  UK backend would normally pair `MATCHER_LANGUAGE=en_gb` with PostgreSQL's
  `english` full-text search config.
- After changing `RECIPE_FTS_CONFIG`, rebuild `found_recipes.search_vector`
  before relying on recipe search or cache rebuild results.
- Rebuild compiled recipe/offer data and the cache after switching language or
  matcher rules.
- Run a language smoke test, a cache rebuild, and a matching preview before
  exposing the country to users.

Unknown or incomplete languages should fail softly: the runtime can load a
scaffold or fall back to the Swedish default, but that only proves the app does
not crash. It does not prove that matching quality is correct for the new
country.

## What You Do NOT Need to Change

- `app/recipe_matcher.py` — language-neutral, imports everything
- `app/cache_manager.py` — language-neutral
- `app/languages/categories.py` — shared English category keys
- Store scrapers — these are per-store, not per-language
- Database schema — mostly language-independent. Recipe full-text search uses
  PostgreSQL's language-specific `regconfig`; configure it with
  `RECIPE_FTS_CONFIG` and rebuild `found_recipes.search_vector` after changing
  it.
- Most frontend JavaScript — country-specific address handling is the main exception

## Delivery Address Fields

The address section in config.html has **three base fields** (street, postal code, city)
that are always shown. The labels, placeholders, postal-code validation, and
autocomplete country follow the selected country profile.

**What needs attention for a new country:**

| Item | Location | Change needed |
|------|----------|---------------|
| Language metadata | `app/languages/i18n.py` | Add `LANGUAGE_INFO` entry with flag, browser locale, and display code |
| Country mapping | `config.html`, `LOCALE_COUNTRY_MAP` | Map your language folder to the country code used by address search |
| Postal code validation | `config.html`, `normalizePostalCode()` and `isValidPostalCode()` | Add the country's postcode format |
| Address labels | `app/languages/<code>/ui.py` | Translate street/postcode/city text to the country's terminology |
| Extra address lines | `config.html` | Add `delivery-street2-input` etc. wrapped in `data-i18n-locale="xx"` |
| Extra DB columns | `database/init.sql`, `user_preferences` table | `ALTER TABLE ADD COLUMN delivery_address_line2 TEXT` etc. |

The three existing DB columns (`delivery_street_address`, `delivery_postal_code`,
`delivery_city`) are all `TEXT` with no length constraints — they won't break.
The only additions needed are extra columns for countries that require more fields.

The `data-i18n-locale` + `data-i18n-feature` pattern is still useful for any
country-specific field blocks, but the current autocomplete block itself follows
the selected profile rather than being Swedish-only.

## Tips

- The Swedish `ingredient_matching/` package is heavily commented — use it as reference
- Start small: get basic matching working with 50-100 ingredients, then expand
- The `INGREDIENTS` dict is the most important piece — start there
- From the project root, run `docker compose exec -T web python tests/dev_reload.py` after changes to verify the cache builds correctly
- Run `docker compose exec -T -w /app web python tests/run_sanity_checks.py` for the tracked app-support sanity checks
- Keep broader local sanity/regression scripts private unless they become small deterministic `run_*_checks.py` support checks
