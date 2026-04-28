# How to Add Scrapers

This guide explains how to add new store and recipe scrapers to Deal Meals.

Both systems use a **plugin architecture** — you create a self-contained module, follow the interface contract, and the app discovers it automatically at startup. No registration needed.

## Runtime Filesystem

The standalone Docker release runs with a read-only root filesystem. Treat
scraper code and static assets as deploy-time files, not runtime storage.

Scrapers should:

- write normal data to PostgreSQL through the existing save helpers
- log through `loguru`/the app logger, not by opening ad-hoc log files
- use `/tmp` or Python's `tempfile` module for temporary files
- use `/app/data` only for deliberate small persistent runtime state
- leave recipe image storage to the existing image cache pipeline

Do not write cache files, debug dumps, downloaded HTML, browser profiles, or
generated assets next to the scraper module. That may work in a loose dev setup
but will fail in the standalone read-only Docker release.

How scraper code changes are deployed depends on the install style:

- **Source/bind-mounted install:** add or remove files, then recreate `web` with
  `docker compose up -d web`.
- **Prebuilt/read-only image install:** scraper code is baked into the image, so
  changes require a rebuilt image or a new release image.

---

## Table of Contents

1. [Adding a Store Scraper](#1-adding-a-store-scraper)
   - [1.1 Folder Structure](#11-folder-structure) · [1.2 Minimal Plugin](#12-minimal-store-plugin) · [1.3 Product Format](#13-product-format) · [1.4 Config UI](#14-optional-store-configuration-ui) · [1.5 Other Overrides](#15-optional-other-overrides) · [1.6 Food Filtering](#16-food-filtering) · [1.7 Mathem Example](#17-real-example-mathem-simplest-store)
   - [1.8 Login Stores](#18-stores-that-require-login) · [1.9 Strategy Decision Tree](#19-choosing-a-scraping-strategy) · [1.10 Multi-Buy Offers](#110-multi-buy-offers) · [1.11 Error Handling](#111-error-handling-in-scrape_offers)
2. [Adding a Recipe Scraper](#2-adding-a-recipe-scraper)
   - [2.1 File Structure](#21-file-structure) · [2.2 Discovery](#22-discovery) · [2.3 Constants](#23-required-module-constants) · [2.4 Interface](#24-required-class-interface) · [2.5 Recipe Format](#25-required-recipe-format) · [2.6 Saving](#26-saving-streaming-and-legacy)
   - [2.7 Result Contract](#27-recipe-scrape-result-contract) · [2.8 scrape_and_save()](#28-recommended-scrape_and_save-method) · [2.9 Progress Callbacks](#29-progress-callbacks-recommended) · [2.10 Examples](#210-real-examples) · [2.11 Strategies](#211-common-scraping-strategies)
3. [Shared Utilities](#3-shared-utilities)
4. [Testing](#4-testing)
5. [Troubleshooting](#5-troubleshooting)
6. [Removing a Scraper](#6-removing-a-scraper)

---

## 1. Adding a Store Scraper

Store scrapers live in `app/scrapers/stores/`. Each store is a folder containing an `__init__.py` that defines a class inheriting from `StorePlugin`.

### 1.1 Folder Structure

```
app/scrapers/stores/
├── base.py                  # StorePlugin ABC — DO NOT MODIFY
├── __init__.py              # Auto-discovery engine — DO NOT MODIFY
├── weight_utils.py          # Shared weight parser (parse_weight)
├── willys/                  # Example store plugin
│   ├── __init__.py          # WillysStore(StorePlugin) class
│   └── logo.svg             # Store logo (displayed in UI)
└── your_store/              # ← Your new store
    ├── __init__.py           # YourStore(StorePlugin) class
    └── logo.svg              # Store logo (SVG preferred, ~2-4 KB)
```

**That's it.** Create a folder, add `__init__.py` with a `StorePlugin` subclass, and the app discovers it at startup. No registration needed.

### 1.2 Minimal Store Plugin

```python
"""
Your Store Plugin - Brief description.
"""

from typing import List, Dict, Optional
from datetime import datetime, timezone
from loguru import logger

from scrapers.stores.base import (
    StorePlugin, StoreConfig, StoreConfigField, StoreScrapeResult
)
from scrapers.stores.weight_utils import parse_weight
from languages.sv.category_utils import guess_category


class YourStore(StorePlugin):
    """Your store scraper."""

    @property
    def config(self) -> StoreConfig:
        return StoreConfig(
            id="your_store",               # Unique ID (lowercase, underscores)
            name="Your Store",             # Display name
            logo="/scrapers/stores/your_store/logo.svg",
            color="#ff6600",               # Brand hex color
            url="https://www.yourstore.se",
            enabled=True,
            has_credentials=False,         # True if login is needed
            description="Short description"
        )

    async def scrape_offers(self, credentials: Optional[Dict] = None) -> StoreScrapeResult:
        """
        Scrape current offers. This is the only required method.

        Return StoreScrapeResult.success(products) for trustworthy results.
        """
        logger.info(f"Scraping {self.config.name}...")
        products = []

        # Your scraping logic here (httpx, Playwright, API calls, etc.)
        # ...

        logger.success(f"Scraped {len(products)} products from {self.config.name}")
        return StoreScrapeResult.success(products)
```

### 1.3 Product Format

`scrape_offers()` should return `StoreScrapeResult.success(products)`. Each
product must at least include `name` and `price`. Include the other fields
whenever the store exposes them; better original-price/savings data produces
better recipe ranking and user-facing explanations.

```python
{
    "name": "Fläskfilé",                         # str — Product name (required)
    "price": 69.90,                              # float — Sale price in SEK (required)
    "original_price": 89.90,                     # float — Normal price (recommended if known)
    "savings": 20.00,                            # float — Discount amount, never negative
    "unit": "kg",                                # str — "st", "kg", "l", or "förp" (default: "st")
    "category": "meat",                          # str — English category (recommended; default: "other")
    "image_url": "https://...",                  # str — Product image URL (optional)
    "product_url": "https://...",                # str — Product page URL (optional but recommended)
    "brand": "SCAN",                             # str — Brand name (UPPERCASE)
    "weight_grams": 500.0,                       # float — Package weight in grams
    "is_multi_buy": True,                        # bool — "3 for 99 kr" type deals
    "multi_buy_quantity": 3,                     # int — Number of items
    "multi_buy_total_price": 99.0,               # float — Total multi-buy price
}
```

**Valid categories** (enforced by database constraint):
`meat`, `poultry`, `fish`, `dairy`, `deli`, `fruit`, `vegetables`, `bread`, `beverages`, `candy`, `spices`, `pizza`, `frozen`, `pantry`, `hygiene`, `household`, `other`

**Valid units** (enforced by database constraint):
`st`, `kg`, `l`, `förp`

The save layer defaults missing `original_price` to `price`, missing `savings`
to `0`, missing `unit` to `"st"`, and missing `category` to `"other"`. The
database sets the scrape timestamp. Still, provide original-price/savings and a
good category whenever possible; those fields make ranking and explanations much
better.

Use `guess_category(product_name)` from `languages.sv.category_utils` to auto-detect the category from the Swedish product name. For the unit, default to `"st"` if unknown.

### 1.4 Optional: Store Configuration UI

If your store needs user configuration (selecting a branch, choosing e-commerce vs physical, etc.), override `get_config_fields()`:

```python
def get_config_fields(self) -> List[StoreConfigField]:
    return [
        StoreConfigField(
            key="location_type",
            label="Location type",
            field_type="radio",
            options=[
                {"value": "ehandel", "label": "E-handel",
                 "icon": "bi-truck", "description": "Online delivery"},
                {"value": "butik", "label": "Fysisk butik",
                 "icon": "bi-shop", "description": "In-store offers"},
            ],
            default="ehandel"
        ),
        StoreConfigField(
            key="store_name",
            label="Search for your store",
            field_type="search",
            placeholder="e.g. Stockholm, Göteborg...",
            depends_on={"field": "location_type", "value": "butik"}
        ),
    ]
```

**Field types:** `radio`, `text`, `select`, `search`, `async_select`, `display`

When using `search` type, also override `search_locations(query)`:

```python
async def search_locations(self, query: str) -> List[Dict]:
    # Call store's API or scrape store finder
    return [
        {"id": "store123", "name": "Your Store Kungsbacka",
         "address": "Storgatan 1, 434 30 Kungsbacka"}
    ]
```

The user's configuration is passed to `scrape_offers()` via `credentials` dict (despite the name — it carries all config, not just login credentials). Access it like: `credentials.get("location_type")`, `credentials.get("store_name")`.

### 1.5 Optional: Other Overrides

| Method | Default | Override when... |
|---|---|---|
| `estimated_scrape_time` | 300 (5 min) | Your scraper takes significantly more or less |
| `test_connection()` | Attempts a full scrape | You want a faster health check (e.g., just ping the URL) |
| `verify_credentials()` | Returns "not supported" | Your store requires login (see section 1.8) |
| `_filter_food_items()` | Built-in filter | Your store sells mixed food/non-food (call from `scrape_offers()`) |

### 1.6 Food Filtering

If your store sells non-food items (like ICA, Coop), call `self._filter_food_items(products)` at the end of `scrape_offers()` to filter out hygiene, household items, etc. The base class loads keyword lists from the active market profile.

For non-Swedish stores, override the keyword class attributes by importing from the appropriate language file in `app/languages/`:

```python
from languages.en_gb.food_filters import (
    FOOD_CATEGORIES, NON_FOOD_CATEGORIES, FOOD_INDICATORS,
    NON_FOOD_STRONG, NON_FOOD_INDICATORS, CERTIFICATION_LOGOS
)

class TescoStore(StorePlugin):
    FOOD_CATEGORIES = FOOD_CATEGORIES
    NON_FOOD_CATEGORIES = NON_FOOD_CATEGORIES
    FOOD_INDICATORS = FOOD_INDICATORS
    NON_FOOD_STRONG = NON_FOOD_STRONG
    NON_FOOD_INDICATORS = NON_FOOD_INDICATORS
    CERTIFICATION_LOGOS = CERTIFICATION_LOGOS
```

Swedish keywords live in `app/languages/sv/food_filters.py`. UK English starter keywords are in `app/languages/en_gb/food_filters.py` (template — refine from actual store data). The active profile is selected through `MATCHER_LANGUAGE`.

> **Note for non-Swedish stores:** Adding a store in another country requires more than just swapping food filter keywords. Use a corresponding `languages/{code}/category_utils.py` with localized keywords, or map categories from the store's own API data instead of relying on Swedish category guessing. The `en_gb` folder has a starter `category_utils.py`, but it should be expanded from real store data.

### 1.7 Real Example: Mathem (Simplest Store)

Mathem (`app/scrapers/stores/mathem/__init__.py`, ~490 lines) is the simplest real store plugin. It's e-commerce only, needs no store selection, and uses Playwright to scrape a single page. Good reference for a first scraper.

### 1.8 Stores That Require Login

No built-in store currently requires login, but the infrastructure is ready. If your store needs authentication (e.g., member-only prices), here's how:

> **Note:** This flow is untested in production — no existing store uses `has_credentials=True`. The base class and API plumbing exist, but the first real implementation may uncover gaps (e.g., how the frontend renders login fields). If you hit issues, check `app/templates/stores.html` and `app/routers/stores.py` for the credential UI logic.

**Step 1:** Set `has_credentials=True` in your `StoreConfig`:

```python
@property
def config(self) -> StoreConfig:
    return StoreConfig(
        id="member_store",
        name="Member Store",
        # ...
        has_credentials=True,  # Enables login UI
    )
```

**Step 2:** Override `verify_credentials()` to test login:

```python
async def verify_credentials(self, username: str, password: str) -> Dict:
    """Test if username/password work."""
    try:
        async with httpx.AsyncClient(
            event_hooks={"request": [ssrf_safe_event_hook]}
        ) as client:
            response = await client.post(
                "https://api.memberstore.se/login",
                json={"user": username, "password": password},
                timeout=HTTP_TIMEOUT
            )
            if response.status_code == 200:
                return {"success": True, "message": "Login successful"}
            return {"success": False, "message": "Invalid credentials"}
    except Exception as e:
        return {"success": False, "message": f"Connection error: {e}"}
```

The return value **must** be a dict with `success` (bool) and `message` (str).

**Step 3:** Use credentials in `scrape_offers()`:

```python
async def scrape_offers(self, credentials: Optional[Dict] = None) -> StoreScrapeResult:
    username = credentials.get("username") if credentials else None
    password = credentials.get("password") if credentials else None

    if not username or not password:
        logger.warning("No credentials provided, cannot scrape member prices")
        return StoreScrapeResult.failed(reason="missing_credentials")

    # Login and scrape...
```

**How credentials flow:** The user's store config is stored as JSONB in the `stores` table. When scraping starts, the websocket router (`app/routers/websockets.py`) loads this config and passes it as the `credentials` dict to `scrape_offers()`. The dict contains everything from the store's JSONB config — location settings, login fields, etc.

**Note:** The `credentials` parameter name is misleading — it carries **all** store config, not just login info. Location type, store ID, postal code, delivery address, and any custom fields from `get_config_fields()` are all in this dict.

### Delivery Address Requirement (E-commerce)

Before any e-commerce scraping starts, the websocket router automatically checks that the user has a complete delivery address (street, postal code, city) configured in Settings. If any field is missing, the scrape is blocked with an error message — your `scrape_offers()` method is never called.

This applies to **all stores** when `location_type` is e-commerce (`"ehandel"`), ensuring a consistent experience. For e-commerce scrapes, your scraper can rely on these `credentials` keys always being present:

- `credentials['delivery_street']` — street address (e.g., "Storgatan 1")
- `credentials['postal_code']` — postal code (e.g., "41658")
- `credentials['delivery_city']` — city (e.g., "Göteborg")

Use these from `credentials` instead of querying the database yourself — it avoids duplicate DB calls and keeps the address source consistent.

### 1.9 Choosing a Scraping Strategy

Use this decision tree to pick the right approach for your store:

```
Does the store have a public REST/JSON API?
├── YES → Use httpx (fastest, most reliable)
│         Example: Willys physical store API, Hemköp API
│
└── NO → Is the data in the HTML source (view-source shows products)?
    ├── YES → Use httpx + BeautifulSoup
    │         Example: Static HTML product pages
    │
    └── NO (JavaScript renders the data) → Use Playwright
              Example: Mathem, Willys e-commerce (infinite scroll)
```

**Guidelines:**
- **Always prefer httpx** — it's 10-50x faster than Playwright, uses ~100x less memory, and is more reliable
- **Playwright** is only for sites where products are loaded by JavaScript (React/Vue/Angular SPAs, infinite scroll)
- **Check for hidden APIs** before resorting to Playwright — open browser DevTools → Network tab → filter XHR/Fetch. Many "JavaScript-rendered" sites actually load data from JSON APIs that you can call directly with httpx
- **Hybrid approach** is valid — Willys uses httpx for physical store API data AND Playwright for e-commerce infinite scroll, selected by user config
- **Docker/read-only runtime:** If you launch Chromium directly, use the same
  Docker-safe args as `app/async_browser.py` unless the site needs something
  different: `--disable-dev-shm-usage`, `--no-sandbox`,
  `--disable-setuid-sandbox`, and `--disable-gpu`. Keep browser scratch files
  under `/tmp`/`tempfile`, and avoid persistent profiles or downloads next to
  the scraper module.

### 1.10 Multi-Buy Offers

When a product has a "3 for 99 kr" type deal:

```python
{
    "name": "Coca-Cola 33cl",
    "price": 10.0,                  # ← Per-unit price (30 / 3 = 10 kr)
    "original_price": 15.90,        # ← Normal single-unit price
    "savings": 5.90,                # ← Per-unit savings, never negative
    "is_multi_buy": True,
    "multi_buy_quantity": 3,        # ← Number of items in deal
    "multi_buy_total_price": 30.0,  # ← Total deal price
}
```

**Rules:**
- `price` is always the **per-unit price** (total ÷ quantity)
- `original_price` is the normal single-unit price
- `savings` = `max(original_price - price, 0)`; if the multi-buy is not actually
  cheaper per unit, store it as `0`
- The UI displays multi-buy deals with the total price and quantity

### 1.11 Error Handling in `scrape_offers()`

The caller (websocket router) wraps your `scrape_offers()` in a try/except. You should:

**DO:**
- Return `StoreScrapeResult.success(products)` when data is trustworthy
- Return `StoreScrapeResult.partial(products, reason="...")` if some products succeed and others fail
- Return `StoreScrapeResult.success_empty(reason="verified_empty")` only when you can verify the store truly has no offers
- Return `StoreScrapeResult.failed(reason="...")` or `.blocked(...)` when the page/API failed and old offers should be kept
- Log errors with `logger.warning()` or `logger.error()` for debugging
- Clean up resources (close browsers, sessions) in a `finally` block

**DON'T:**
- Silently return an empty list when something fails — log it
- Return `[]` for failures. Legacy empty lists are treated as failed/stale by the app.
- Raise exceptions for individual product parsing failures — skip and continue
- Leave Playwright browsers open on error

**Pattern:**

```python
CHROMIUM_DOCKER_ARGS = [
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-gpu",
]

async def scrape_offers(self, credentials=None):
    products = []
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=CHROMIUM_DOCKER_ARGS,
            )
            page = await browser.new_page()

            # Navigate...
            items = await page.query_selector_all(".product")

            for item in items:
                try:
                    product = await self._parse_product(item)
                    if product:
                        products.append(product)
                except Exception as e:
                    logger.warning(f"Failed to parse product: {e}")
                    continue  # Skip this product, continue with next

    except Exception as e:
        logger.error(f"Scraping failed after {len(products)} products: {e}")
        return StoreScrapeResult.partial(products, reason="page_failed")
    finally:
        if browser:
            await browser.close()

    return StoreScrapeResult.success(products)
```

---

## 2. Adding a Recipe Scraper

> **Before writing a custom scraper:** If you just want to add a few recipes from a specific website, you don't need to write any code. The built-in **"My Recipes"** source lets you add individual recipe URLs from any site that uses schema.org/Recipe structured data (~80% of recipe sites). Just paste the URL via the gear icon on the My Recipes card on the Recipes page. See the User Manual for details.
>
> Write a custom scraper only when you want to **automatically discover and import many recipes** from a site — not for adding individual recipes one by one.

Recipe scrapers live as individual files in `app/scrapers/recipes/`. They follow a convention-based interface (no base class).

### 2.1 File Structure

```
app/scrapers/recipes/
├── _common.py               # Shared helpers (save_recipes_to_database, etc.)
├── __init__.py              # Package docstring (auto-discovery, no registration)
├── coop_scraper.py          # Example: Coop.se scraper (Playwright)
├── zeta_scraper.py          # Example: Zeta.nu scraper (httpx + sitemap)
├── myrecipes_scraper.py     # Built-in: user-managed URLs (schema.org/Recipe)
└── yoursite_scraper.py      # ← Your new scraper
```

**Naming convention:** `{sitename}_scraper.py` — the filename minus `_scraper.py` becomes the scraper ID used internally (e.g., `yoursite`).

### 2.2 Discovery

Recipe scrapers are discovered **automatically** by `RecipeScraperManager` — any file matching `*_scraper.py` in the recipes directory is loaded. It extracts the module-level constants and finds the `*Scraper` class.

No manual registration is needed. In a source/bind-mounted install, create the
file and recreate `web` with `docker compose up -d web`. In a prebuilt/read-only
image install, include the scraper in the rebuilt image.

### 2.3 Required Module Constants

Every recipe scraper file must define these at module level:

```python
SCRAPER_NAME = "YourSite.se"              # Display name in UI
DB_SOURCE_NAME = "YourSite.se"            # Name stored in database (must be consistent)
SCRAPER_DESCRIPTION = "Recept från yoursite.se"   # Use "Recept från [url]" — fetch limits are shown dynamically from DB config
EXPECTED_RECIPE_COUNT = 500               # Approximate total recipe count
SOURCE_URL = "https://www.yoursite.se"    # Link shown in UI

MIN_INGREDIENTS = 3                       # Skip recipes with fewer ingredients
```

Optional:
```python
SCRAPER_WARNING = "Large scraper — full mode takes ~30 minutes"
```

### 2.4 Required Class Interface

```python
from scrapers.recipes._common import (
    RecipeScrapeResult,
    StreamingRecipeSaver,
    make_recipe_scrape_result,
)

class YourSiteScraper:
    """Scraper for YourSite.se."""

    def __init__(self):
        self._progress_callback = None
        self._cancel_flag = False

    def set_progress_callback(self, callback):
        """Set progress callback. Called by the app after instantiation."""
        self._progress_callback = callback

    def cancel(self):
        """Cancel ongoing scrape. Called by the UI cancel button."""
        self._cancel_flag = True

    async def scrape_all_recipes(
        self,
        max_recipes: int = None,
        force_all: bool = False,
        stream_saver: StreamingRecipeSaver = None,
    ) -> RecipeScrapeResult:
        """
        Main entry point. Called by the GUI for all three modes:

        - Test mode:        scrape_all_recipes(max_recipes=20)
        - Incremental mode: scrape_all_recipes()
        - Full mode:        scrape_all_recipes(force_all=True)

        Returns a RecipeScrapeResult. The result is list-like, so len(result),
        result[:5], and for recipe in result keep working in CLI helpers.
        """
        self._cancel_flag = False

        if force_all:
            # Re-scrape everything
            urls = await self._get_all_urls()
        else:
            # Only scrape new URLs not already in database
            all_urls = await self._get_all_urls()
            existing = self._get_existing_urls()
            urls = [u for u in all_urls if u not in existing]

        if max_recipes:
            urls = urls[:max_recipes]

        recipes = []
        processed = 0
        success = 0
        for url in urls:
            if self._cancel_flag:
                break
            recipe = await self._scrape_recipe(url)
            processed += 1
            if recipe:
                if stream_saver:
                    await stream_saver.add(recipe)
                else:
                    recipes.append(recipe)
                success += 1
            # Send progress updates
            if self._progress_callback:
                await self._progress_callback({
                    "type": "progress",
                    "current": processed,
                    "total": len(urls),
                    "success": success
                })

        return make_recipe_scrape_result(
            recipes,
            force_all=force_all,
            max_recipes=max_recipes,
            reason="cancelled" if self._cancel_flag else None,
            cancelled=self._cancel_flag,
        )
```

### 2.5 Required Recipe Format

Each recipe dict must have:

```python
{
    "name": "Pasta Carbonara",                   # str — Recipe name (required)
    "url": "https://yoursite.se/recipe/123",     # str — Unique URL (required, used as dedup key)
    "source_name": DB_SOURCE_NAME,               # str — Must match your constant (required)
    "ingredients": ["pasta", "bacon", "egg"],    # list[str] — Ingredient strings (required)
    "image_url": "https://...",                  # str — Recipe image URL
    "prep_time_minutes": 30,                     # int — Cooking time in minutes (optional)
    "servings": 4,                               # int — Number of portions (optional)
}
```

**Important:** Skip recipes with fewer than `MIN_INGREDIENTS` (3) ingredients. These are typically ingredient pages, not real recipes.

### 2.6 Saving: Streaming and Legacy

For production GUI/scheduled runs, prefer streaming saves with
`scrape_and_save()` and `StreamingRecipeSaver` (see section 2.8). This keeps
large recipe imports memory-flat and saves progress every 50 recipes by default.

Keep a module-level `save_to_database()` function for developer CLI helpers,
older integrations, and simple scrapers that still return all recipes at the
end. Use the shared helper from `_common.py`:

```python
from scrapers.recipes._common import save_recipes_to_database

def save_to_database(recipes, clear_old=False):
    """Save recipes to database."""
    return save_recipes_to_database(recipes, DB_SOURCE_NAME, clear_old=clear_old)
```

`recipes` may be either a plain `list[dict]` or a `RecipeScrapeResult`. The shared function handles deduplication, upsert (update existing / insert new), permanently excluded URLs, spell checking, per-recipe commits, and error handling. Returns `{"cleared": N, "created": N, "updated": N, "skipped": N, "errors": N, "spell_corrections": N}` plus scrape status metadata.

When using `StreamingRecipeSaver`, do **not** call `save_to_database()` for each
batch yourself. Add recipes to the saver and call `finish()` once after the
scrape completes.

### 2.7 Recipe Scrape Result Contract

New scrapers should return `RecipeScrapeResult` from `scrape_all_recipes()` via `make_recipe_scrape_result()`:

```python
from scrapers.recipes._common import make_recipe_scrape_result

if not urls:
    return make_recipe_scrape_result(
        [],
        force_all=force_all,
        max_recipes=max_recipes,
        failed=True,
        reason="no_recipe_urls",
    )

if not urls_to_scrape:
    return make_recipe_scrape_result(
        [],
        force_all=force_all,
        max_recipes=max_recipes,
        reason="no_new_recipes",
    )

return make_recipe_scrape_result(
    recipes,
    force_all=force_all,
    max_recipes=max_recipes,
)
```

The app still accepts legacy `list[dict]` returns, but the result object lets the central router distinguish "no new recipes", "verified empty", "failed", "partial", and "cancelled" without each plugin duplicating UI policy.

When the result is passed to `save_recipes_to_database()`, the shared save
helper also:
- Skips URLs listed in the `excluded_recipe_urls` table (permanently deleted by the user via Settings > Advanced > Recipe Management)
- Runs **spell check** on all ingredient text using Levenshtein distance (max 1 edit). Typos like "basilka" → "basilika", "morrot" → "morot" are corrected automatically. Corrections are stored in the `spell_corrections` table and can be reverted per recipe or globally excluded (via `spell_excluded_words` table) by the user in the Spell Check modal on the Config page.

If you write custom save logic, you must handle excluded URLs and spell checking yourself.

> **Strongly recommended:** While technically you could write your own save logic, the built-in recipe scrapers use this shared helper. It handles edge cases (duplicate URLs, preserving user-excluded recipes, permanently excluded URLs, per-recipe commits to avoid cascading rollbacks) that are easy to get wrong. Use it unless you have a specific reason not to.

### 2.8 Recommended: `scrape_and_save()` Method

The web route prefers `scrape_and_save()` for full and incremental modes when
the method exists. Implement it with `StreamingRecipeSaver` for any scraper that
can return hundreds or thousands of recipes.

```python
from scrapers.recipes._common import StreamingRecipeSaver

async def scrape_and_save(
    self,
    overwrite: bool = False,
    max_recipes: int = None,
) -> Dict[str, int]:
    """Scrape and save in small batches."""
    saver = StreamingRecipeSaver(
        DB_SOURCE_NAME,
        overwrite=overwrite,
        max_recipes=max_recipes,
    )
    result = await self.scrape_all_recipes(
        max_recipes=max_recipes,
        force_all=overwrite,
        stream_saver=saver,
    )
    if result.status == "failed":
        stats = saver.stats.copy()
        stats["scrape_status"] = "failed"
        stats["scrape_reason"] = result.reason
        return stats

    stats = await saver.finish(cancelled=result.status == "cancelled")
    if result.status == "no_new_recipes":
        stats["scrape_status"] = "no_new_recipes"
        stats["scrape_reason"] = result.reason
    return stats
```

Your `scrape_all_recipes()` should accept `stream_saver=None`. When a recipe is
successfully parsed, call `await stream_saver.add(recipe)` instead of appending
it to the in-memory list. Test mode still calls `scrape_all_recipes(max_recipes=20)`
without a saver, so keep returning a normal `RecipeScrapeResult` there.

Streaming full-mode semantics differ slightly from the legacy clear-then-save
path: batches are upserted during the run, and stale source recipes are deleted
only after `finish()` succeeds. If a full scrape fails or is cancelled, old
recipes are kept. `finish(cancelled=True)` drops unsaved pending recipes instead
of flushing them.

Cache rebuilds and automatic image downloads are triggered by the router after
the whole scraper (or run-all queue) completes, not after each streaming batch.

### 2.9 Progress Callbacks (Recommended)

Progress callbacks let the UI show real-time scraping status. The app calls `set_progress_callback()` on your scraper before scraping starts.

**Implementation:**

```python
class YourSiteScraper:
    def __init__(self):
        self._progress_callback = None
        self._cancel_flag = False

    def set_progress_callback(self, callback):
        """Called by the app before scraping starts."""
        self._progress_callback = callback

    async def _send_progress(self, current, total, success, message=None):
        """Helper to send progress updates."""
        if self._progress_callback:
            try:
                await self._progress_callback({
                    "type": "progress",
                    "current": current,      # Items processed so far
                    "total": total,          # Total items to process
                    "success": success,      # Successful recipes found
                    "message": message       # Optional status text
                })
            except Exception:
                pass  # Don't crash if callback fails (e.g., WebSocket closed)
```

**When to call it:**
- After each recipe is processed (or every 10th recipe for performance)
- The frontend polls `/api/recipe-scrapers/{id}/status` every 2 seconds, so updates faster than that are unnecessary

**The callback dict keys used by the router** (`app/routers/recipes.py`):
- `current` (int) — number of items processed
- `total` (int) — total items to process
- `success` (int) — number of successful recipes
- `message` (str, optional) — status text

### 2.10 Real Examples

**Simplest: Zeta** (`app/scrapers/recipes/zeta_scraper.py`) — sitemap + httpx, no browser needed. Best starting point for new scrapers.

**With Playwright: Coop** (`app/scrapers/recipes/coop_scraper.py`) — sitemap + Playwright for JS-rendered pages. Use this pattern when the site requires a browser.

### 2.11 Common Scraping Strategies

| Strategy | When to use | Example |
|---|---|---|
| **Sitemap + httpx** | Site has sitemap, data in HTML/JSON-LD server-side | Zeta, Mathem (recipes) |
| **Sitemap + Playwright** | Site has sitemap, but JSON-LD needs JS rendering | Coop, ICA (recipes) |
| **API + httpx** | Store has a public REST API | Hemköp, Willys (physical stores) |
| **Playwright scroll** | Products loaded via infinite scroll | Mathem, Willys (e-commerce) |

**Always prefer httpx over Playwright** when possible — it's faster, uses less memory, and is more reliable.

---

## 3. Shared Utilities

### Recipe Save Helpers

```python
from scrapers.recipes._common import (
    make_recipe_scrape_result,
    save_recipes_to_database,
    StreamingRecipeSaver,
)
```

Use `make_recipe_scrape_result()` for public scrape method returns,
`StreamingRecipeSaver` for GUI/scheduled production saves, and
`save_recipes_to_database()` for CLI helpers or simple legacy save paths.

### Category Detection

```python
from languages.sv.category_utils import guess_category

category = guess_category("Kycklingfilé 500g")  # → "poultry"
category = guess_category("Laxfilé")            # → "fish"
```

### Weight Parsing

```python
from scrapers.stores.weight_utils import parse_weight

grams = parse_weight("500 g")       # → 500.0
grams = parse_weight("1,5 kg")      # → 1500.0
grams = parse_weight("750 ml")      # → 750.0
```

### Ingredient List Cleanup

```python
from scrapers.recipes._common import split_serving_lists, clean_ingredient_quantities

# Split "Till servering" lists into separate ingredients
# "jordgubbar, pistagenötter och dryck" → 3 items
ingredients = split_serving_lists(ingredients)

# Fix floating-point precision errors: "0.499998 dl" → "0.5 dl"
ingredients = clean_ingredient_quantities(ingredients)
```

`split_serving_lists` handles recipe sources that combine serving suggestions into one line (e.g., ICA "Till servering:" section). Only splits comma+och patterns **without** leading quantities to avoid breaking "1 dl grädde, vispat och kylt".

### SSRF Protection (Recommended)

When making outgoing HTTP requests, use the `ssrf_safe_event_hook` to prevent redirects to internal/private IP ranges. This is included in all built-in scrapers:

```python
from utils.security import ssrf_safe_event_hook

async with httpx.AsyncClient(
    event_hooks={"request": [ssrf_safe_event_hook]}
) as client:
    response = await client.get(url)
```

This blocks requests to private networks (10.x.x.x, 192.168.x.x, 127.0.0.1, etc.) — protecting against servers that redirect to internal addresses.

### Timeout Constants

Centralized in `app/constants_timeouts.py`:

```python
from constants_timeouts import HTTP_TIMEOUT, PAGE_LOAD_TIMEOUT, PAGE_NETWORK_IDLE_TIMEOUT, DOMCONTENT_TIMEOUT
```

| Constant | Value | Use for |
|---|---|---|
| `HTTP_TIMEOUT` | 30 (seconds) | httpx requests: `timeout=HTTP_TIMEOUT` |
| `PAGE_LOAD_TIMEOUT` | 30000 (ms) | Playwright `page.goto(url, timeout=...)` |
| `PAGE_NETWORK_IDLE_TIMEOUT` | 30000 (ms) | `page.wait_for_load_state("networkidle", timeout=...)` |
| `DOMCONTENT_TIMEOUT` | 30000 (ms) | `page.wait_for_load_state("domcontentloaded", timeout=...)` |

**When to use:** Import these instead of hardcoding timeouts. Specific waits (selectors, animations) should stay as local constants in each scraper since they're tuned to specific UI behavior.

### Database Reads (`get_db_session`)

Recipe scrapers may use `get_db_session()` from `app/database.py` when they need
to read incremental state, such as URLs already fetched for this source:

```python
from database import get_db_session
from models import FoundRecipe

# Read existing recipe URLs (to skip already-scraped)
with get_db_session() as db:
    existing = db.query(FoundRecipe.url).filter(
        FoundRecipe.source_name == DB_SOURCE_NAME
    ).all()
    existing_urls = {row.url for row in existing}
```

Use `StreamingRecipeSaver` from `scrape_and_save()` for production writes, or
`save_recipes_to_database()` via your module-level `save_to_database()` function
for CLI/legacy writes. Do not insert `FoundRecipe` rows directly unless you are
also intentionally reimplementing the shared excluded-URL, spell-check, upsert,
and result-status behavior.

The `get_db_session()` context manager auto-commits on success and rolls back on
exception. Always use `with` — never create sessions manually.

### Store Save Flow

Store scrapers don't save offers directly. The app handles it via two functions in `app/db_saver.py`:

1. **`ensure_store_exists(store_id, store_name, store_url)`** — called before saving. Auto-registers new stores in the database on first use (matches on `store_type`, the ASCII lowercase ID).

2. **`save_offers(store_name, products)`** — saves scraped products to the `offers` table. **Clears ALL existing offers from ALL stores first**, then inserts the new products. This means only one store's offers are active at a time (by design — recipes are based on one store's deals).

Your `scrape_offers()` method only needs to return `StoreScrapeResult.success(products)` for trustworthy data. The app calls `save_offers()` for you.

### Database Tables (Reference)

The two tables your scrapers populate:

**`offers`** (populated by store scrapers via `save_offers()`):
- `name`, `price`, `original_price`, `savings`, `unit`, `category`, `brand`
- `weight_grams`, `image_url`, `product_url`
- `is_multi_buy`, `multi_buy_quantity`, `multi_buy_total_price`
- `location_type` ("ehandel" or "butik"), `location_name`
- Constraints: `price > 0`, unit ∈ {st, kg, l, förp}, category from standard list

**`found_recipes`** (populated by recipe scrapers via `StreamingRecipeSaver` or `save_recipes_to_database()`):
- `name`, `url` (unique), `source_name`, `ingredients` (JSONB array), `image_url`
- `prep_time_minutes`, `servings`
- `excluded` (user can hide recipes)
- Matching fields (auto-computed): `matching_offer_ids`, `match_score`, `estimated_savings`

**`excluded_recipe_urls`** (permanently blocked URLs, managed via Settings UI):
- `url` (unique), `source_name`, `recipe_name`, `excluded_at`
- Checked automatically by `save_recipes_to_database()` — excluded URLs are skipped

See `app/models.py` for the complete schema including constraints and indexes.

### Ingredient Matching

The ingredient matching system (how offers are matched to recipe ingredients) is documented separately in [INGREDIENT_TEMPLATE.md](INGREDIENT_TEMPLATE.md). You don't need to modify it unless your scraper introduces recipes in a new language.

---

## 4. Testing

### Store Scraper

```bash
# Start the app
docker compose up -d web

# Check the logs to see if your store was discovered
docker compose logs web | grep "Loaded store"

# Test via the Stores page in the browser — your store should appear
# Click "Fetch Offers" to run your scraper
```

### Recipe Scraper

```bash
# Check discovery
docker compose logs web | grep "Loaded scraper"

# Test via the Recipes page — your source should appear in the list
# Use "Test" mode first (scrapes 20 recipes, doesn't save)
```

### Quick Smoke Test (CLI)

You can also test a store scraper directly from the Docker container:

```bash
docker compose exec -T web python -c "
import asyncio
from scrapers.stores.your_store import YourStore

async def test():
    store = YourStore()
    result = await store.scrape_offers()
    products = result.products
    print(f'Found {len(products)} products ({result.status})')
    for p in products[:3]:
        print(f'  {p[\"name\"]}: {p[\"price\"]} kr (was {p[\"original_price\"]})')

asyncio.run(test())
"
```

The production `web` container is read-only apart from its mounted volumes and
tmpfs paths. If a smoke test needs scratch files, write them under `/tmp`. If it
needs persistent state, prefer the database or an explicitly documented file
under `/app/data`.

### Validating Product Data

After scraping, check that your data meets database constraints:

```python
# Quick validation check
VALID_CATEGORIES = {"meat", "poultry", "fish", "dairy", "deli", "fruit",
                     "vegetables", "bread", "beverages", "candy", "spices",
                     "pizza", "frozen", "pantry", "hygiene", "household", "other"}
VALID_UNITS = {"st", "kg", "l", "förp"}

for p in products:
    assert p.get("name"), "Missing name"
    assert p.get("price") and p["price"] > 0, f"Invalid price: {p.get('price')}"
    assert p.get("unit", "st") in VALID_UNITS, f"Invalid unit: {p.get('unit')}"
    assert p.get("category", "other") in VALID_CATEGORIES, f"Invalid category: {p.get('category')}"
    assert p.get("savings", 0) >= 0, f"Invalid savings: {p.get('savings')}"
```

Common data issues:
- **Price = 0 or negative** → database rejects it (constraint: `price > 0`)
- **Category not in valid list** → database rejects it
- **Unit not in valid list** → database rejects it
- **Negative `savings`** → database rejects it; clamp non-deals to `0`

---

## 5. Troubleshooting

### Store not showing up

- Check that your folder is directly under `app/scrapers/stores/` (not nested deeper)
- Check that `__init__.py` defines a class that inherits from `StorePlugin`
- Check the logs: `docker compose logs web | grep -i "store\|error"`
- Folder names starting with `_` or `.` are skipped

### Recipe scraper not showing up

- File must end with `_scraper.py` (e.g., `yoursite_scraper.py`)
- File must not start with `_`
- Must define `SCRAPER_NAME` at module level
- Must contain a class with "Scraper" in the name
- Check logs: `docker compose logs web | grep -i "scraper\|error"`

### Playwright issues

**Timeouts:**
- Default `PAGE_LOAD_TIMEOUT` is 30 seconds. If a site is slow, increase it locally: `await page.goto(url, timeout=60000)`
- For infinite scroll, wait for a specific selector rather than `networkidle` (which may never fire if the page keeps loading analytics)
- Symptom: `TimeoutError: Timeout 30000ms exceeded` → the page didn't finish loading in time

**Selector not found:**
- Websites change their HTML structure. If `.product-card` stops working, inspect the live site
- Use resilient selectors: prefer `data-testid` or `role` attributes over CSS classes
- Test selectors in browser DevTools first: `document.querySelectorAll('.your-selector').length`

**Browser crashes:**
- Playwright runs headless Chromium inside Docker. Memory is limited
- Limit concurrent tabs with `asyncio.Semaphore(3)` for Playwright (vs 10+ for httpx)
- Always close browsers in `finally` blocks or use `async with`
- If the container runs out of memory, reduce concurrency or scrape in smaller batches

**Docker/read-only filesystem:**
- The standalone Docker release runs `web` with a read-only root filesystem.
  Browser profiles, downloads, traces, screenshots, and temporary HTML dumps
  must go under `/tmp` or Python's `tempfile` module.
- Direct `p.chromium.launch(...)` scrapers should use a consistent Docker arg
  set. Start with:

```python
CHROMIUM_DOCKER_ARGS = [
    "--disable-dev-shm-usage",  # use /tmp instead of Docker's small /dev/shm
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-gpu",
]

browser = await p.chromium.launch(
    headless=True,
    args=CHROMIUM_DOCKER_ARGS,
)
```

- `AsyncBrowserManager` already uses this pattern. Prefer it for shared-browser
  flows, and keep direct-launch scrapers consistent unless a site needs
  different launch behavior.

**General Playwright tips:**
- Use `locale='sv-SE'` in browser context for Swedish sites
- Import timeout constants from `constants_timeouts.py` instead of hardcoding
- **Always prefer httpx** when possible — Playwright should be a last resort

### Rate limiting (HTTP 429 / IP blocking)

Stores will block you if you scrape too aggressively. Follow these guidelines:

| Transport | Max concurrency | Delay between requests |
|-----------|----------------|----------------------|
| httpx (API calls) | 10 concurrent requests | 0.1-0.5 seconds |
| httpx (HTML pages) | 5 concurrent requests | 0.5-1 second |
| Playwright (browser) | 3 concurrent tabs | 1-2 seconds |

**Implementation using Semaphore:**

```python
import asyncio

SEM = asyncio.Semaphore(5)  # Max 5 concurrent requests
DELAY = 0.5                  # Seconds between requests

async def fetch_with_limit(client, url):
    async with SEM:
        response = await client.get(url)
        await asyncio.sleep(DELAY)
        return response
```

**Symptoms of being rate limited:**
- HTTP 429 "Too Many Requests" → add delays, reduce concurrency
- HTTP 403 "Forbidden" → you may be IP-blocked. Wait 10-30 minutes, then try slower
- Empty responses or CAPTCHA pages → the site detected bot behavior
- Connection resets → too many simultaneous connections

**Recovery:** If blocked, wait and retry with lower concurrency. Don't retry immediately in a loop.

### Category not recognized

- Check `app/languages/sv/category_utils.py` for the keyword lists
- Add new keywords there if your store uses unusual category names
- The `guess_category()` function falls back to `"other"` for unknown items

### Products getting filtered out

- The base class `_filter_food_items()` has aggressive non-food filtering
- If legitimate food products are being removed, check the keyword lists in `app/languages/sv/food_filters.py`
- Log filtered items with `log_filtered=True` (default) to see what's removed

---

## 6. Removing a Scraper

In a source/bind-mounted install, store and recipe scrapers can be removed by
deleting their files and recreating `web`. In a prebuilt/read-only image install,
removing a scraper means building or installing an image without that scraper.

### Removing a Store Scraper

1. Delete the store folder: `rm -rf app/scrapers/stores/your_store/`
2. Recreate web: `docker compose up -d web`

The store disappears from the UI automatically. On startup, Deal Meals also removes
the matching row from the `stores` table and removes any matching
`store_schedules` row. Dependent offer rows are removed by the database cascade.

This cleanup only runs after a clean store-plugin discovery. If a store folder
still exists but has an import or initialization error, Deal Meals logs the
plugin error clearly and skips destructive store cleanup for that startup. Fix the
plugin error, recreate `web`, and let startup run again.

### Removing a Recipe Scraper

1. Delete the scraper file: `rm app/scrapers/recipes/yoursite_scraper.py`
2. Recreate web: `docker compose up -d web`

The scraper disappears from the UI automatically. Existing recipes from that source remain in the database and continue to work for matching. To also remove the recipes, use the "Delete recipes" button on the Recipes page before removing the file (or delete from database: `DELETE FROM found_recipes WHERE source_name = 'YourSite.se'`).
