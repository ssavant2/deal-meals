# Ingredient Matching Translation Guide

This guide explains how to create ingredient matching rules for a new language.

## Warning: This is Complex!

Ingredient matching is **much more complex** than UI translation. It requires:

1. Deep knowledge of food terminology in your language
2. Understanding of how grocery stores name products
3. Careful handling of edge cases (compounds, plural forms, etc.)

**Estimated effort:** 40-80 hours for a complete translation.

## Current Implementation (Swedish)

The Swedish ingredient matching is a modular package split across ~20 files in
`app/languages/sv/ingredient_matching/`. See [HOW_TO_ADD_COUNTRIES.md](HOW_TO_ADD_COUNTRIES.md)
for the full file list and what each file contains.

Supporting files at the `sv/` level:
- `normalization.py` — Text normalization (`fix_swedish_chars`, `normalize_ingredient`)
- `categories.py` — Category display names
- `category_utils.py` — Category detection from product names (`guess_category`)
- `food_filters.py` — Non-food product filtering, cooking vs candy classification
- `recipe_filters.py` — Recipe-level filters (boring recipe detection)

## Structure Overview

### 1. Keyword Mapping (`INGREDIENTS` dict)

The main data is in `ingredient_data.py`. Maps recipe ingredient names to
searchable keywords used to find matching store offers:

```python
# Swedish example (in ingredient_data.py):
INGREDIENTS = {
    'kycklingfilé': ['kyckling', 'kycklingfilé', 'kycklingbröst'],
    'nötfärs': ['nötfärs', 'färs', 'köttfärs'],
}

# UK English equivalent would be:
INGREDIENTS = {
    'chicken breast': ['chicken', 'chicken breast', 'chicken fillet'],
    'beef mince': ['beef mince', 'minced beef', 'ground beef'],
}
```

### 2. Classification Constants

Used by `recipe_matcher.py` to classify recipes (meat/fish/vegetarian).
Lives in `recipe_matcher_support.py`:

```python
CLASSIFICATION_MEAT_KEYWORDS = ['beef', 'pork', 'chicken', 'lamb', ...]
CLASSIFICATION_FISH_KEYWORDS = ['salmon', 'cod', 'tuna', 'shrimp', ...]
```

### 3. False Positive Prevention

Several mechanisms prevent wrong products from matching:

- **`processed_rules.py`** — blocks processed/convenience products
  (e.g. "chicken nuggets" shouldn't match a recipe ingredient "chicken")
- **`blocker_data.py`** — `PRODUCT_NAME_BLOCKERS` blocks specific product
  name words from matching a keyword
- **`match_filters.py`** — KSC (keyword suppressed by context), spice-vs-fresh rules

### 4. Text Normalization

`normalization.py` (inside the package) handles multi-word space normalizations.
`sv/normalization.py` handles character-level fixes (diacritics, OCR errors).

## Creating a New Language Pack

See [HOW_TO_ADD_COUNTRIES.md](HOW_TO_ADD_COUNTRIES.md) for the full step-by-step
process and file structure. The short version:

```
languages/
└── xx/                              # Your country/language code (e.g., 'en_gb', 'de')
    ├── __init__.py
    ├── ui.py                        # UI translations (copy from en_gb/ui.py)
    ├── normalization.py             # Character fixes for your language
    ├── categories.py               # Category display names
    ├── category_utils.py           # Category detection keywords
    ├── food_filters.py             # Non-food product filtering
    ├── recipe_filters.py           # Recipe-level filters
    ├── recipe_matcher_backend.py   # Adapter used by matcher_runtime
    └── ingredient_matching/        # ~20 files — see HOW_TO_ADD_COUNTRIES.md
```

Start with `ui.py` to get a working interface, then build `ingredient_matching/`
using the Swedish implementation as reference (it is heavily commented).

`app/languages/en_gb/ingredient_matching/` contains a small commented scaffold
with five sample ingredient families. It is loadable, but it is not a complete
UK matcher; use it as a shape/template, not as production rule coverage.

## Sample Translations (Swedish → English)

| Swedish | English | Category |
|---------|---------|----------|
| kycklingfilé | chicken breast | meat |
| nötfärs | ground beef | meat |
| fläskfilé | pork tenderloin | meat |
| laxfilé | salmon fillet | fish |
| torsk | cod | fish |
| räkor | shrimp | fish |
| mjölk | milk | dairy |
| grädde | cream | dairy |
| smör | butter | dairy |
| ost | cheese | dairy |
| ägg | eggs | dairy |
| lök | onion | vegetable |
| vitlök | garlic | vegetable |
| potatis | potato | vegetable |
| morot | carrot | vegetable |
| tomat | tomato | vegetable |
| pasta | pasta | pantry |
| ris | rice | pantry |
| mjöl | flour | pantry |

## Testing Your Translation

1. From the project root, run `docker compose exec -T web python tests/dev_reload.py` to rebuild the cache after changes
2. Run `docker compose exec -T -w /app web python tests/run_sanity_checks.py` for the tracked app-support sanity checks
3. Keep broader local sanity/regression scripts private unless they become small deterministic `run_*_checks.py` support checks
4. Check for:
   - Missing matches (ingredient should match but doesn't)
   - False matches (wrong product matched)
   - Category errors (meat marked as vegetarian, etc.)
