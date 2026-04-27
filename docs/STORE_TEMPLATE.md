# Store Scraper Template

Use this template when creating a new store plugin for Deal Meals. For the full
walkthrough and design notes, see [HOW_TO_ADD_SCRAPERS.md](HOW_TO_ADD_SCRAPERS.md).

## Quick Start

1. Create a new folder under `app/scrapers/stores/` with the store name (lowercase)
2. Create `__init__.py` with a class that inherits from `StorePlugin`
3. Add a `logo.svg` in the same folder
4. Recreate `web` in source/bind-mounted installs: `docker compose up -d web`
5. The system will automatically discover your store at startup.

## Runtime Filesystem

The standalone Docker release uses a read-only root filesystem. The store plugin
folder is for deploy-time code and assets such as `logo.svg`; do not write
runtime cache files, downloaded HTML, debug dumps, browser profiles, or generated
files next to the scraper module.

Use:

- PostgreSQL for scraped offers and durable app data
- `loguru`/the app logger for diagnostics
- `/tmp` or Python's `tempfile` module for temporary files
- `/app/data` only for small persistent runtime state that is intentionally part
  of the app contract

In a source/bind-mounted install, new store files are picked up after recreating
the `web` container (`docker compose up -d web`). In a prebuilt/read-only image
install, store plugin files are baked into the image and require a rebuilt image
or a new release image.

## Folder Structure

```
app/scrapers/stores/
├── base.py              # Base class (don't touch)
├── __init__.py          # Auto-discovery (don't touch)
├── weight_utils.py      # Shared: weight/volume parsing (universal, not language-specific)
├── willys/              # Example: Willys (complete implementation)
│   ├── __init__.py
│   ├── logo.svg
│   └── willys_store_finder.py  # Helper for store search
└── yourstore/           # <-- Your new store
    ├── __init__.py
    └── logo.svg

app/languages/sv/
├── category_utils.py    # Swedish category keywords (shared by all Swedish stores)
├── normalization.py     # Swedish text normalization (fix åäö, etc.)
├── ingredient_matching/    # Swedish ingredient matching for recipes
├── food_filters.py      # Non-food filtering + cooking vs candy classification
├── recipe_filters.py    # Recipe-level filters (boring recipes, etc.)
└── ui.py                # Swedish UI translations
```

## Minimal Implementation

Copy this to `app/scrapers/stores/yourstore/__init__.py`:

```python
"""
YourStore Store Plugin

Scrapes offers from YourStore.
"""

from typing import Dict, List, Optional
from datetime import datetime, timezone
from loguru import logger

from scrapers.stores.base import StorePlugin, StoreConfig, StoreScrapeResult


class YourStoreStore(StorePlugin):
    """
    YourStore - [Short description].
    """

    @property
    def config(self) -> StoreConfig:
        return StoreConfig(
            id="yourstore",                          # Unique ID (lowercase, no spaces)
            name="YourStore",                        # Display name
            logo="/scrapers/stores/yourstore/logo.svg",
            color="#FF6600",                         # Store brand color (hex)
            url="https://www.yourstore.se",
            enabled=True,                            # Set False during development
            description="Store tagline"
        )

    async def scrape_offers(self, credentials: Optional[Dict] = None) -> StoreScrapeResult:
        """
        Scrape offers from the store.

        Args:
            credentials: Dict with config values from database:
                - location_type: "ehandel" or "butik"
                - location_id: Store ID if butik selected
                - session_cookies: Saved cookies (if applicable)

        Returns:
            StoreScrapeResult with products in standard format (see below)
        """
        logger.info(f"Starting scrape of {self.config.name}...")

        # Get config values
        location_type = credentials.get('location_type', 'ehandel') if credentials else 'ehandel'
        location_id = credentials.get('location_id') if credentials else None

        products = []

        # TODO: Implement your scraping logic here
        # See "Scraping Strategies" below

        logger.success(f"Scraped {len(products)} products from {self.config.name}")
        return StoreScrapeResult.success(products)
```

## Product Format

Each product must at least include `name` and `price`. Include the other fields
whenever the store exposes them; better original-price/savings data produces
better recipe ranking and user-facing explanations.

```python
{
    "name": "Kycklingfilé",           # Product name (required)
    "price": 69.90,                   # Sale price (required)
    "original_price": 89.90,          # Regular price (recommended if known)
    "savings": 20.00,                 # Savings in SEK, never negative (recommended if known)
    "unit": "kg",                     # Unit: "kg", "st", "l", "förp" (default: "st")
    "category": "poultry",            # Category (recommended; see list below)
    "image_url": "https://...",       # Product image (optional)
    "product_url": "https://...",     # Link to product page (optional but recommended)
    "brand": "SCAN",                  # Brand name (optional, UPPERCASE)
    "weight_grams": 700.0,           # Package weight in grams (optional, for oversized warnings)
    "scraped_at": datetime.now(timezone.utc)  # Optional; DB timestamp is set by save layer
}
```

### Multi-buy Offers (optional)

For "3 for 100 kr" offers, add:

```python
{
    "is_multi_buy": True,
    "multi_buy_quantity": 3,          # Number of items in offer
    "multi_buy_total_price": 100.00,  # Total price for all
    "price": 33.33,                   # Unit price (total / quantity)
    "savings": 0.00,                  # Per-unit savings; use 0 if it is not cheaper
    ...
}
```

## Categories

Use these standard categories for the `category` field:

| Category     | Description                              |
|--------------|------------------------------------------|
| `meat`       | Meat (beef, pork, lamb, game)            |
| `poultry`    | Poultry (chicken, turkey, duck)          |
| `fish`       | Fish and seafood                         |
| `dairy`      | Dairy (milk, cheese, yogurt)             |
| `deli`       | Deli (ham, sausage, bacon)               |
| `fruit`      | Fruit and berries                        |
| `vegetables` | Vegetables                               |
| `bread`      | Bread and bakery                         |
| `pantry`     | Pantry (pasta, rice, noodles)            |
| `spices`     | Sauces, oils, condiments, spices         |
| `pizza`      | Pizza and ready-made pizza products      |
| `frozen`     | Frozen goods                             |
| `beverages`  | Beverages                                |
| `candy`      | Candy and snacks                         |
| `hygiene`    | Hygiene and beauty (non-food)            |
| `household`  | Household items (non-food)               |
| `other`      | Unclassified (fallback)                  |

**Note:** `hygiene` and `household` are non-food categories excluded from AI recipe matching.

## How Offers Are Saved

Your `scrape_offers()` method only needs to return `StoreScrapeResult.success(products)` for trustworthy results. The app handles saving:

1. **`ensure_store_exists()`** — auto-registers your store in the database on first use (matched by `config.id`)
2. **`save_offers()`** — clears ALL existing offers (from ALL stores), then inserts your products

This means only one store's offers are active at a time. This is by design — recipe matching works against one store's current deals.

Your store is registered automatically when discovered. You do not need to insert it into the database manually.

## Timeout Constants

Import from `app/constants_timeouts.py` instead of hardcoding:

```python
from constants_timeouts import HTTP_TIMEOUT, PAGE_LOAD_TIMEOUT, PAGE_NETWORK_IDLE_TIMEOUT
```

| Constant | Value | Use for |
|---|---|---|
| `HTTP_TIMEOUT` | 30s | httpx: `timeout=HTTP_TIMEOUT` |
| `PAGE_LOAD_TIMEOUT` | 30000ms | Playwright: `page.goto(url, timeout=...)` |
| `PAGE_NETWORK_IDLE_TIMEOUT` | 30000ms | `page.wait_for_load_state("networkidle", timeout=...)` |

Specific waits (selectors, animations) should stay as local constants tuned to the specific site.

## Scraping Strategies

### Option 1: REST API (preferred if available)

Many stores have hidden APIs. Open DevTools (F12) → Network → filter on XHR/Fetch while browsing the store's offers page.

**IMPORTANT:** Always use `httpx` with async/await for HTTP requests. Never use `requests` in async code as it blocks the event loop.

```python
import httpx
from utils.security import ssrf_safe_event_hook

async def scrape_offers(self, credentials=None):
    async with httpx.AsyncClient(
        event_hooks={"request": [ssrf_safe_event_hook]}
    ) as client:
        response = await client.get(
            "https://api.yourstore.se/campaigns",
            headers={"User-Agent": "Mozilla/5.0..."},
            timeout=30
        )
    data = response.json()

    products = []
    for item in data["products"]:
        products.append({
            "name": item["title"],
            "price": item["salePrice"],
            "original_price": item["regularPrice"],
            ...
        })
    return StoreScrapeResult.success(products)
```

### Option 2: Playwright (for JavaScript-heavy sites)

```python
from playwright.async_api import async_playwright

CHROMIUM_DOCKER_ARGS = [
    "--disable-dev-shm-usage",  # use /tmp instead of Docker's small /dev/shm
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-gpu",
]

async def scrape_offers(self, credentials=None):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=CHROMIUM_DOCKER_ARGS,
        )
        page = await browser.new_page()

        await page.goto("https://www.yourstore.se/erbjudanden")
        await page.wait_for_selector(".product-card")

        # Scroll to load all products
        await self._scroll_to_load_all(page)

        # Extract products
        products = []
        cards = await page.query_selector_all(".product-card")

        for card in cards:
            name = await card.query_selector(".product-name")
            price = await card.query_selector(".product-price")
            # ... extract data

        await browser.close()
        return StoreScrapeResult.success(products)
```

The standalone Docker release has a read-only root filesystem. If your
Playwright scraper writes downloads, traces, screenshots, HTML dumps, or browser
profiles, put them under `/tmp` or Python's `tempfile` module and clean them up.
Avoid writing runtime files next to the scraper module.

### Option 3: BeautifulSoup (for static pages)

```python
import httpx
from bs4 import BeautifulSoup

from utils.security import ssrf_safe_event_hook

async def scrape_offers(self, credentials=None):
    async with httpx.AsyncClient(
        event_hooks={"request": [ssrf_safe_event_hook]}
    ) as client:
        response = await client.get(
            "https://www.yourstore.se/erbjudanden",
            timeout=30
        )
    soup = BeautifulSoup(response.text, "html.parser")

    products = []
    for card in soup.select(".product-card"):
        name = card.select_one(".name").text.strip()
        price = float(card.select_one(".price").text.replace("kr", ""))
        # ...

    return StoreScrapeResult.success(products)
```

## Store Configuration (optional)

If your store needs user configuration (e.g., selecting a physical store or region), implement `get_config_fields()`:

```python
from scrapers.stores.base import StoreConfigField

def get_config_fields(self) -> List[StoreConfigField]:
    """Define configuration fields for the UI."""
    return [
        StoreConfigField(
            key="location_type",
            label="Välj typ",
            field_type="radio",
            options=[
                {
                    "value": "ehandel",
                    "label": "E-handel",
                    "suffix": "(Hemkörning)",  # Optional: shown in normal font after bold label
                    "description": "Erbjudanden för hemkörning"
                },
                {
                    "value": "butik",
                    "label": "Butik",
                    "description": "Erbjudanden för en specifik butik"
                }
            ],
            default="ehandel"
        ),
        StoreConfigField(
            key="location_search",
            label="Sök butik",
            field_type="search",
            placeholder="t.ex. göteborg, stockholm...",
            depends_on={"field": "location_type", "value": "butik"}  # Only shown when butik is selected
        )
    ]
```

### Field Types

| Type     | Description                                      |
|----------|--------------------------------------------------|
| `radio`  | Radio buttons (mutually exclusive options)       |
| `select` | Dropdown menu                                    |
| `text`   | Text input                                       |
| `search` | Text input with search button (uses `search_locations()`) |
| `async_select` | Dropdown with async-loaded options |
| `display` | Read-only display field |

### Radio Option Properties

| Property      | Required | Description                                           |
|---------------|----------|-------------------------------------------------------|
| `value`       | Yes      | The value stored in database                          |
| `label`       | Yes      | Bold text shown to user                               |
| `suffix`      | No       | Text shown after label in normal font                 |
| `description` | No       | Small muted text shown below the label                |
| `icon`        | No       | Bootstrap icon class (e.g. `"bi-truck"`)              |

### Location Search

If your store supports selecting a physical location, implement `search_locations()`:

```python
async def search_locations(self, query: str) -> List[Dict]:
    """Search for store locations."""
    import httpx
    from utils.security import ssrf_safe_event_hook

    async with httpx.AsyncClient(
        event_hooks={"request": [ssrf_safe_event_hook]}
    ) as client:
        response = await client.get(
            f"https://api.yourstore.se/stores?q={query}",
            timeout=10
        )

    stores = []
    for item in response.json()["results"]:
        stores.append({
            "id": item["storeId"],        # Unique store ID
            "name": item["displayName"],  # Display name
            "address": item["address"],   # Address for display
            "type": "butik"               # "butik" or "hemma"
        })
    return stores
```

The frontend will automatically call `/api/stores/{store_id}/locations?q=...` which routes to this method.

## Shared Utilities

Your scraper should use these shared modules instead of reimplementing common logic.

### Category Guessing (language-specific)

Category keywords are country/language-specific, so the Swedish module lives
under `app/languages/sv/`. For a non-Swedish store, use or create a matching
module in the appropriate country folder (e.g., `app/languages/en_gb/category_utils.py`
for UK stores or `app/languages/da/category_utils.py` for Danish stores).

```python
from languages.sv.category_utils import guess_category as shared_guess_category

# In your product extraction:
category = shared_guess_category(product_name)
```

If the store API provides its own category, pass it for better accuracy:

```python
from languages.sv.category_utils import guess_category as shared_guess_category
from languages.sv.category_utils import normalize_api_category as shared_normalize_category

# When parsing products:
api_category = item.get("category", "")
category = shared_guess_category(product_name, api_category=api_category)

# Or normalize API category directly:
category = shared_normalize_category(api_category)
```

See `app/languages/sv/category_utils.py` for the full production implementation
and `app/languages/en_gb/category_utils.py` for a small commented scaffold.

### Weight/Volume Parsing (universal)

Converts weight strings (e.g., "650g", "1.5kg", "75cl") to grams. This is universal metric unit conversion — not language-specific — so it lives in `app/scrapers/stores/`.

```python
from scrapers.stores.weight_utils import parse_weight

# In your product extraction:
weight_grams = parse_weight(product_name)       # "Arla Ost 700g" → 700.0
weight_grams = parse_weight("ca: 650g")         # 650.0
weight_grams = parse_weight("1.5kg")            # 1500.0
weight_grams = parse_weight("75cl")             # 750.0
weight_grams = parse_weight("st")               # None (no weight)
```

Add `weight_grams` to your product dict so the oversized product warning works in the frontend.

### SSRF Protection (Recommended)

Prevents outgoing HTTP requests from being redirected to internal/private networks:

```python
from utils.security import ssrf_safe_event_hook

async with httpx.AsyncClient(
    event_hooks={"request": [ssrf_safe_event_hook]}
) as client:
    response = await client.get(url)
```

All built-in scrapers include this hook. It blocks requests to 10.x.x.x, 192.168.x.x, 127.0.0.1, etc.

### Swedish Text Normalization

Fixes broken Swedish characters (common in web scraping):

```python
from languages.sv.normalization import fix_swedish_chars

name = fix_swedish_chars(raw_name)  # "Flaskfile" → "Fläskfilé"
```

## Testing Your Implementation

```bash
# From your Deal Meals project root

# Start/recreate web so discovery sees source changes
docker compose up -d web

# Run interactive test
docker compose exec -T web python -c "
from scrapers.stores import get_store, get_all_stores
import asyncio

# List all stores
for s in get_all_stores():
    print(f'{s.config.id}: {s.config.name} (enabled={s.config.enabled})')

# Test your store
store = get_store('yourstore')
print(f'Store: {store.config.name}')
print(f'Enabled: {store.config.enabled}')
print(f'Config fields: {len(store.get_config_fields())}')

# Test scraping
result = asyncio.run(store.scrape_offers())
products = result.products
print(f'Found {len(products)} products ({result.status})')

# Show first product
if products:
    print(products[0])
"
```

## Estimated Scrape Time (optional)

The UI shows a progress bar during scraping based on expected duration.
After the first scrape, the actual measured time is stored and shown in the UI.
But on the **very first scrape** (no stored time yet), it falls back to `estimated_scrape_time`.

Default is 300 seconds (5 min). Override if your store is significantly faster or slower:

```python
@property
def estimated_scrape_time(self) -> int:
    """Estimated scrape time in seconds (used only on first-ever scrape)."""
    return 120  # This store is fast (~2 min)
```

## Invalidate on Postal Change (optional)

Whether you need this depends on how the store works in reality:

- **ICA e-handel** uses it — the user picks a specific store from a list that depends on
  their postal code (different stores deliver to different areas). If the user changes
  postal code, the previously selected store may no longer be valid.
- **Coop/Willys/Hemkop** don't need it — they read the postal code directly from user
  preferences at scrape time, so there's no intermediate store selection to invalidate.

If your store has a similar flow where a config selection depends on the user's postal
code, set `invalidate_on_postal_change=True` on that config field:

```python
StoreConfigField(
    key="location_search",
    label="Sök butik",
    field_type="search",
    placeholder="t.ex. göteborg...",
    invalidate_on_postal_change=True  # Clears saved selection when postal code changes
)
```

The frontend will clear the saved value and prompt the user to re-select when the
postal code changes.

## Delivery Address Requirement (E-commerce)

Before any e-commerce scraping starts, the app automatically checks that the user has a complete delivery address (street, postal code, and city) configured in Settings. If any field is missing, the scrape is blocked and the user sees an error message asking them to complete their address.

This check applies to **all stores** when `location_type` is e-commerce (`"ehandel"`) — even stores like Mathem that have nationwide pricing. This ensures a consistent user experience and means your scraper can always rely on `credentials['delivery_street']`, `credentials['postal_code']`, and `credentials['delivery_city']` being present for e-commerce scrapes.

Your scraper doesn't need to implement this check — it's handled by the websocket router before `scrape_offers()` is called. But you should use the address fields from `credentials` instead of fetching them from the database yourself.

## Checklist Before You're Done

- [ ] `config.id` is unique and lowercase
- [ ] `logo.svg` exists in the folder (get from store's website or create)
- [ ] `scrape_offers()` returns `StoreScrapeResult.success(products)` with correct format
- [ ] All products have at least `name` and `price`
- [ ] Categories use standard names from the list above (via `languages.sv.category_utils`)
- [ ] Swedish characters (åäö) are handled correctly (via `languages.sv.normalization`)
- [ ] Weight extraction returns `weight_grams` when possible (via `scrapers.stores.weight_utils`)
- [ ] SSRF protection via `ssrf_safe_event_hook` on httpx clients (recommended)
- [ ] Error handling with try/except and logging
- [ ] Tested that scraping works
- [ ] (optional) `get_config_fields()` if store needs user configuration
- [ ] (optional) `search_locations()` if store supports location search

## Example: Willys (complete implementation)

See `app/scrapers/stores/willys/__init__.py` for a full implementation with:
- API scraping for physical stores
- Playwright scraping for e-commerce
- Location search via `search_locations()`
- Config UI via `get_config_fields()`
- Multi-buy offers
- Swedish character fixes
- Category mapping

## API Endpoints (automatic)

Once your store is created, these endpoints are automatically available:

| Endpoint | Description |
|----------|-------------|
| `GET /api/stores` | List all stores with metadata |
| `GET /api/stores/{store_id}/config-fields` | Get config field definitions |
| `GET /api/stores/{store_id}/config` | Get saved config values |
| `POST /api/stores/{store_id}/config` | Save config values |
| `GET /api/stores/{store_id}/locations?q=...` | Search locations (if implemented) |

For more examples and troubleshooting, see [HOW_TO_ADD_SCRAPERS.md](HOW_TO_ADD_SCRAPERS.md).
