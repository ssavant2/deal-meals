# Recipe Scraper Template

Use this template when creating a new recipe scraper for Deal Meals. For the full
walkthrough and design notes, see [HOW_TO_ADD_SCRAPERS.md](HOW_TO_ADD_SCRAPERS.md).

## Runtime Filesystem

The standalone Docker release uses a read-only root filesystem. Recipe scraper
files are deploy-time code; do not write runtime cache files, downloaded HTML,
debug dumps, browser profiles, or generated files next to the scraper module.

Use the shared database save helpers for recipes, the app logger for
diagnostics, and `/tmp` or Python's `tempfile` module for short-lived scratch
files. Use `/app/data` only for deliberate small persistent runtime state that is
documented and expected to survive container replacement.

In a source/bind-mounted install, new scraper files are picked up after
recreating the `web` container (`docker compose up -d web`). In a
prebuilt/read-only image install, recipe scraper files are baked into the image
and require a rebuilt image or a new release image.

## Start Here: Minimal Contract

Every recipe scraper is discovered by filename (`*_scraper.py`) and must expose
the same small public interface. Copy one of the implementation skeletons below,
but keep this contract intact:

```python
from typing import Dict, Optional

from scrapers.recipes._common import (
    RecipeScrapeResult,
    incremental_attempt_limit,
    make_recipe_scrape_result,
    recipe_target_reached,
    save_recipes_to_database,
    StreamingRecipeSaver,
)

SCRAPER_NAME = "[Site Name]"
DB_SOURCE_NAME = "[Site Name]"  # Must match recipe["source_name"]
SCRAPER_DESCRIPTION = "Recept från [site]"
EXPECTED_RECIPE_COUNT = 0
SOURCE_URL = "https://..."
MIN_INGREDIENTS = 3


class [SiteName]Scraper:
    def __init__(self):
        self._progress_callback = None
        self._cancel_flag = False

    def set_progress_callback(self, callback):
        self._progress_callback = callback

    def cancel(self):
        self._cancel_flag = True

    async def scrape_all_recipes(
        self,
        max_recipes: Optional[int] = None,
        batch_size: int = 10,
        force_all: bool = False,
        stream_saver: Optional[StreamingRecipeSaver] = None,
    ) -> RecipeScrapeResult:
        recipes = []
        return make_recipe_scrape_result(
            recipes,
            force_all=force_all,
            max_recipes=max_recipes,
        )

    async def scrape_incremental(self) -> RecipeScrapeResult:
        return await self.scrape_all_recipes()

    async def scrape_and_save(
        self,
        overwrite: bool = False,
        max_recipes: Optional[int] = None,
    ) -> Dict[str, int]:
        """Scrape and save in small batches for GUI/scheduled production runs."""
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


def save_to_database(recipes, clear_old: bool = False) -> Dict[str, int]:
    return save_recipes_to_database(recipes, DB_SOURCE_NAME, clear_old=clear_old)
```

The rest of this file is template material for the two common implementation
styles. For strategy tradeoffs and design notes, use
[HOW_TO_ADD_SCRAPERS.md](HOW_TO_ADD_SCRAPERS.md).

For large production scrapes, use the shared streaming-save path:
`scrape_and_save()` creates a `StreamingRecipeSaver`, passes it into
`scrape_all_recipes(..., stream_saver=saver)`, and calls `finish()` once after
scraping completes. Test mode still calls `scrape_all_recipes(max_recipes=20)`
without a saver, so keep the normal `RecipeScrapeResult` return path.

When `max_recipes` comes from the GUI for incremental mode, treat it as a target
for usable recipes rather than a raw URL-attempt limit. Use
`incremental_attempt_limit()` when choosing candidate URLs and
`recipe_target_reached()` inside the scrape loop to stop after enough valid
recipes have been parsed.

## Choose One Implementation Skeleton

There are two valid scraping approaches:

| Approach | When to Use | Speed | Dependencies |
|----------|-------------|-------|--------------|
| **Option A: Playwright + Categories** | Sites without sitemaps, JS-heavy sites, login required | Slower (3 concurrent) | playwright |
| **Option B: Sitemap + httpx** | Sites with XML sitemaps containing recipe URLs | Fast (10+ concurrent) | httpx |

---

## Option A: Playwright + Category Discovery

Use this for sites that:
- Don't have XML sitemaps with recipe URLs
- Require JavaScript rendering
- Need browser interaction (pagination, load more buttons)

### Copy/Paste Metadata And Imports

```python
import asyncio
import re
from datetime import datetime
from typing import Dict, List, Optional, Set

from constants_timeouts import PAGE_LOAD_TIMEOUT, PAGE_NETWORK_IDLE_TIMEOUT
from loguru import logger
from playwright.async_api import TimeoutError as PlaywrightTimeout, async_playwright
from scrapers.recipes._common import (
    RecipeScrapeResult,
    make_recipe_scrape_result,
    save_recipes_to_database,
    StreamingRecipeSaver,
)

# GUI Metadata - UPDATE THESE!
SCRAPER_NAME = "[Site Name]"              # Display name in GUI
DB_SOURCE_NAME = "[db_name]"              # MUST match source_name in saved recipes!
SCRAPER_DESCRIPTION = "[Brief description for GUI]"
EXPECTED_RECIPE_COUNT = 0  # Approximate number of recipes
SOURCE_URL = "https://..."
MIN_INGREDIENTS = 3       # Skip recipes with fewer ingredients

CHROMIUM_DOCKER_ARGS = [
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-gpu",
]
```

`DB_SOURCE_NAME` must exactly match the `source_name` field you use when saving
recipes to the database. The GUI uses this to count recipes from each source.

## Option A Skeleton

### 1. Main Scraper Class

```python
class [SiteName]Scraper:
    """Scraper for [site].com"""

    def __init__(self):
        self.base_url = "https://..."
        self.categories = []
        self._progress_callback = None
        self._cancel_flag = False

    def set_progress_callback(self, callback):
        """Set progress callback. Called by the app after instantiation."""
        self._progress_callback = callback

    def cancel(self):
        """Cancel ongoing scrape. Called by the UI cancel button."""
        self._cancel_flag = True

    async def discover_categories(self) -> List[str]:
        """Discover category URLs dynamically."""
        pass
    
    async def scrape_all_recipes(
        self,
        max_recipes: Optional[int] = None,
        batch_size: int = 10,
        force_all: bool = False,
        stream_saver: Optional[StreamingRecipeSaver] = None,
    ) -> RecipeScrapeResult:
        """
        Main scraping function.

        1. Collect all recipe URLs from categories
        2. Compare against database (skip existing)
        3. Scrape only NEW recipes
        4. Return RecipeScrapeResult

        Args:
            max_recipes: Target number of usable recipes (test mode uses 20)
            force_all: If True, skip existing check and scrape everything (for overwrite mode)

        Returns:
            RecipeScrapeResult. It is list-like, so len(result), bool(result),
            iteration, and result[:3] work for simple CLI tests.
        """
        if self._cancel_flag:
            return make_recipe_scrape_result([], cancelled=True, reason="cancelled")

        recipe_urls: Set[str] = set()
        # Discover categories and collect recipe URLs here.
        if not recipe_urls:
            return make_recipe_scrape_result([], failed=True, reason="no_recipe_urls")

        # Filter existing URLs unless force_all=True, scrape the remaining URLs.
        # If stream_saver is provided, add each recipe with
        # await stream_saver.add(recipe) instead of appending to recipes.
        recipes = []
        return make_recipe_scrape_result(
            recipes,
            force_all=force_all,
            max_recipes=max_recipes,
        )

    async def scrape_incremental(self) -> RecipeScrapeResult:
        """
        Incremental scrape: only new recipes not already in database.
        Required by recipe_scraper_manager.py — validated at startup.
        """
        return await self.scrape_all_recipes()

    async def _scrape_category(self, context, category_url: str) -> Set[str]:
        """Scrape all recipe URLs from a category page."""
        pass
    
    async def _scrape_recipe(self, context, url: str) -> Optional[Dict]:
        """Scrape a single recipe page."""
        pass
    
    async def _scrape_recipe_with_semaphore(self, context, url: str, semaphore: asyncio.Semaphore) -> Optional[Dict]:
        """Wrapper with semaphore for concurrent control."""
        async with semaphore:
            return await self._scrape_recipe(context, url)
```

### 2. Optional CLI Save Function

The web UI and scheduler prefer `scrape_and_save()` when it exists. A
module-level save function is still useful for developer CLI runs from
`if __name__ == "__main__"` and for legacy/simple scrapers.

```python
def save_to_database(recipes, clear_old: bool = False) -> Dict[str, int]:
    """
    Save recipes to database.
    
    Args:
        recipes: RecipeScrapeResult or list of scraped recipes
        clear_old: If True, clear old recipes first (default: False for incremental)
    
    Returns:
        Stats dict: {'cleared': X, 'created': Y, 'updated': Z, 'errors': W, 'skipped': S}
    """
    return save_recipes_to_database(recipes, DB_SOURCE_NAME, clear_old=clear_old)
```

### 2b. Production Streaming Save

```python
async def scrape_and_save(
    self,
    overwrite: bool = False,
    max_recipes: Optional[int] = None,
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

`StreamingRecipeSaver` saves batches of 50 recipes by default. In full mode it
upserts batches during the run and deletes stale source recipes only after the
scrape finishes successfully. Cancelled runs do not flush pending unsaved
recipes.

### 3. Three Run Modes

```python
async def test_scrape():
    """Test mode: 20 recipes, no database save."""
    pass

async def full_scrape():
    """Incremental mode: Only scrape NEW recipes (default)."""
    pass

async def overwrite_scrape():
    """Overwrite mode: Clear all old data, scrape everything."""
    pass
```

### 4. Main Execution

```python
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        
        if mode == "--test":
            asyncio.run(test_scrape())
        
        elif mode == "--overwrite":
            asyncio.run(overwrite_scrape())
        
        else:
            print(f"Unknown argument: {mode}")
            print("\nUsage:")
            print("  python [name]_scraper.py              # Incremental sync (default)")
            print("  python [name]_scraper.py --test       # Test mode (20 recipes, no DB)")
            print("  python [name]_scraper.py --overwrite  # Full overwrite (clear + rescrape)")
            sys.exit(1)
    
    else:
        asyncio.run(full_scrape())
```

## Recipe Dict Structure

All scrapers should put recipe dicts in this format inside `RecipeScrapeResult.recipes`:

```python
{
    "name": str,                    # Recipe name
    "description": str,             # Short description (optional)
    "ingredients": List[str],       # List of ingredients with quantities
    "instructions": str,            # Cooking instructions
    "prep_time_minutes": int,       # Preparation time (optional)
    "servings": int,                # Number of servings (optional)
    "image_url": str,               # Image URL (optional)
    "url": str,                     # Source URL (required)
    "source_name": str,             # Site name (e.g., "Recepten.se")
    "scraped_at": datetime          # Timestamp
}
```

## Usage Examples

```bash
# Default: Incremental sync (only new recipes)
python recepten_scraper.py

# Test: 20 recipes, no database
python recepten_scraper.py --test

# Full resync: Clear old + scrape all
python recepten_scraper.py --overwrite
```

## GUI Integration

The GUI (`app/routers/recipes.py`) imports your scraper class and calls it directly — it does NOT use subprocess. At startup, `recipe_scraper_manager.py` discovers all `*_scraper.py` files, reads the module-level constants (`SCRAPER_NAME`, etc.), and instantiates the class.

At scrape time, the router calls:
```python
scraper = YourSiteScraper()
scraper.set_progress_callback(callback)  # If method exists

# Test mode (20 recipes):
result = await scraper.scrape_all_recipes(max_recipes=20)

# Incremental mode:
if hasattr(scraper, "scrape_and_save"):
    result = await scraper.scrape_and_save(overwrite=False, max_recipes=max_incr)
else:
    result = await scraper.scrape_all_recipes(max_recipes=max_incr)

# Full overwrite mode:
if hasattr(scraper, "scrape_and_save"):
    result = await scraper.scrape_and_save(overwrite=True, max_recipes=max_full)
else:
    result = await scraper.scrape_all_recipes(force_all=True, max_recipes=max_full)
```

The result is normalized centrally before final UI status handling. Return
`make_recipe_scrape_result(..., failed=True, reason="...")` for discovery/API
failures so old recipes are kept. Return
`make_recipe_scrape_result(..., reason="no_new_recipes")` when the scrape worked
but there was nothing new to fetch.

For scrapers that implement `scrape_and_save()`, the router expects a stats dict
with `created`, `updated`, `saved`, `errors`, `scrape_status`, and
`scrape_reason` keys. `StreamingRecipeSaver.finish()` fills these fields.

The `if __name__ == "__main__"` block in your scraper is for **developer CLI testing only** — the GUI never calls it.

### Notes (Option A)

- Always use async/await for Playwright operations
- Use Semaphore to limit concurrent browser tabs (3 is a safe default for Playwright)
- Compare URLs against database BEFORE scraping (saves time)
- Handle site-specific quirks (Swedish characters, time formats, etc)
- Log progress clearly for GUI to parse
- Return None for a failed single recipe (don't crash entire batch)
- Return `RecipeScrapeResult`, preferably via `make_recipe_scrape_result()`, from public scrape methods
- Import timeout constants from `constants_timeouts.py` instead of hardcoding
- Always close browser in a `finally` block or use `async with`
- In Docker/read-only deployments, keep browser scratch files under `/tmp` or
  Python's `tempfile` module. Direct Chromium launches should normally use the
  same Docker-safe args as `app/async_browser.py`: `--disable-dev-shm-usage`,
  `--no-sandbox`, `--disable-setuid-sandbox`, and `--disable-gpu`.
- Prefer httpx over Playwright when possible — it's faster and uses less memory

---

## Option B: Sitemap + httpx (Fast Mode)

Use this for sites that:
- Have XML sitemaps with all recipe URLs
- Have JSON-LD schema data embedded in pages
- Don't require JavaScript rendering

This approach is ~10x faster than Playwright.

### Copy/Paste Metadata And Imports

```python
import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

import httpx
from constants_timeouts import HTTP_TIMEOUT
from loguru import logger
from scrapers.recipes._common import (
    RecipeScrapeResult,
    make_recipe_scrape_result,
    save_recipes_to_database,
    StreamingRecipeSaver,
)
from utils.security import ssrf_safe_event_hook

# GUI Metadata - UPDATE THESE!
SCRAPER_NAME = "[Site Name]"              # Display name in GUI
DB_SOURCE_NAME = "[db_name]"              # MUST match source_name in saved recipes!
SCRAPER_DESCRIPTION = "[Brief description for GUI]"
EXPECTED_RECIPE_COUNT = 0  # Approximate number of recipes
SOURCE_URL = "https://..."
MIN_INGREDIENTS = 3       # Skip recipes with fewer ingredients
```

### Option B Skeleton

```python
class [SiteName]Scraper:
    """Fast scraper for [site] using sitemap + httpx."""

    def __init__(self):
        self.base_url = "https://..."
        self._progress_callback = None
        self._cancel_flag = False
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
        }

    def set_progress_callback(self, callback):
        """Set progress callback. Called by the app after instantiation."""
        self._progress_callback = callback

    def cancel(self):
        """Cancel ongoing scrape. Called by the UI cancel button."""
        self._cancel_flag = True

    # ========== SITEMAP DISCOVERY ==========

    async def discover_sitemap_urls(self, client: httpx.AsyncClient) -> List[str]:
        """
        Dynamically discover recipe sitemap URLs from robots.txt.

        Flow:
        1. Fetch robots.txt to find main sitemap URL
        2. Fetch sitemap index
        3. Find recipe sitemaps (containing 'recipe' or '/recept/' in URL)

        Returns:
            List of recipe sitemap URLs
        """
        pass

    def _get_fallback_sitemaps(self) -> List[str]:
        """Fallback to known sitemap pattern if dynamic discovery fails."""
        pass

    async def get_recipe_urls_from_sitemap(self) -> List[Tuple[str, str]]:
        """
        Fetch all recipe URLs from sitemaps.

        Returns:
            List of (url, lastmod) tuples
        """
        pass

    # ========== DATABASE ==========

    async def get_existing_recipes(self) -> Dict[str, datetime]:
        """Get existing recipes with their scraped_at dates."""
        pass

    # ========== RECIPE SCRAPING ==========

    async def scrape_recipe_httpx(
        self,
        client: httpx.AsyncClient,
        url: str
    ) -> Optional[Dict]:
        """
        Scrape a single recipe using httpx.
        Parses JSON-LD schema from the HTML.
        """
        pass

    async def scrape_recipes_concurrent(
        self,
        urls: List[str],
        max_concurrent: int = 10
    ) -> List[Dict]:
        """
        Scrape multiple recipes concurrently with httpx.
        Uses Semaphore for rate limiting.
        """
        pass

    # ========== MAIN INTERFACE ==========

    async def scrape_all_recipes(
        self,
        max_recipes: Optional[int] = None,
        batch_size: int = 10,
        force_all: bool = False,
        stream_saver: Optional[StreamingRecipeSaver] = None,
    ) -> RecipeScrapeResult:
        """
        Main scraping method (matches interface expected by GUI).

        Args:
            max_recipes: Target number of usable recipes (test mode uses 20)
            batch_size: Concurrent requests (default 10)
            force_all: If True, scrape all recipes (for overwrite mode)

        Returns:
            RecipeScrapeResult. It is list-like for len(), iteration, and slicing.
        """
        recipe_urls = await self.get_recipe_urls_from_sitemap()
        if not recipe_urls:
            return make_recipe_scrape_result([], failed=True, reason="no_recipe_urls")

        # Filter existing URLs unless force_all=True, scrape the remaining URLs.
        # If stream_saver is provided, add recipes to it as they are parsed.
        recipes = []
        return make_recipe_scrape_result(
            recipes,
            force_all=force_all,
            max_recipes=max_recipes,
        )

    async def scrape_incremental(self) -> RecipeScrapeResult:
        """
        Incremental scrape: only new recipes not already in database.
        Required by recipe_scraper_manager.py — validated at startup.
        """
        return await self.scrape_all_recipes()

    async def scrape_and_save(
        self,
        overwrite: bool = False,
        max_recipes: Optional[int] = None,
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


def save_to_database(recipes, clear_old: bool = False) -> Dict:
    """
    Module-level save function. Use the shared helper from _common.py:

        from scrapers.recipes._common import save_recipes_to_database
        return save_recipes_to_database(recipes, DB_SOURCE_NAME, clear_old=clear_old)

    Returns:
        Stats dict: {'cleared': X, 'created': Y, 'updated': Z, 'errors': W, 'skipped': S}
    """
    return save_recipes_to_database(recipes, DB_SOURCE_NAME, clear_old=clear_old)
```

### JSON-LD Parsing Pattern

Most recipe sites embed structured data as JSON-LD. Here's the standard parsing pattern:

```python
async def scrape_recipe_httpx(self, client: httpx.AsyncClient, url: str) -> Optional[Dict]:
    """Scrape a single recipe using httpx + JSON-LD."""
    try:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        html = response.text

        recipe = {
            "source_name": "[site_name]",  # Must match DB_SOURCE_NAME!
            "url": url,
            "scraped_at": datetime.now(timezone.utc)
        }

        # Find JSON-LD script
        json_ld_match = re.search(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html,
            re.DOTALL
        )

        if not json_ld_match:
            return None

        data = json.loads(json_ld_match.group(1))

        # Handle potential array of schemas
        if isinstance(data, list):
            data = next((d for d in data if d.get("@type") == "Recipe"), None)

        if not isinstance(data, dict) or data.get("@type") != "Recipe":
            return None

        # Extract standard fields
        recipe["name"] = data.get("name", "").strip()
        recipe["description"] = data.get("description", "").strip() or None
        recipe["ingredients"] = data.get("recipeIngredient", [])

        # Instructions (handle HowToStep objects)
        instructions = data.get("recipeInstructions", [])
        if instructions and isinstance(instructions[0], dict):
            recipe["instructions"] = "\n".join(
                step.get("text", "") for step in instructions
            )
        else:
            recipe["instructions"] = "\n".join(str(s) for s in instructions)

        # Image (can be string or array)
        img = data.get("image")
        if isinstance(img, list) and img:
            recipe["image_url"] = img[0]
        elif isinstance(img, str):
            recipe["image_url"] = img

        # Servings
        servings = data.get("recipeYield")
        if isinstance(servings, str):
            match = re.search(r'(\d+)', servings)
            if match:
                recipe["servings"] = int(match.group(1))
        elif isinstance(servings, int):
            recipe["servings"] = servings

        # Time (ISO 8601 duration) — use shared helper from _common.py
        from scrapers.recipes._common import parse_iso8601_duration
        total_time = data.get("totalTime", "")
        recipe["prep_time_minutes"] = parse_iso8601_duration(total_time)

        # Validate required fields
        if not recipe.get("name") or not recipe.get("ingredients"):
            return None

        return recipe

    except Exception as e:
        logger.debug(f"Error scraping {url}: {e}")
        return None
```

### Sitemap XML Parsing Pattern

```python
async def get_recipe_urls_from_sitemap(self) -> List[Tuple[str, str]]:
    """Fetch all recipe URLs from sitemaps."""
    all_recipes = []

    async with httpx.AsyncClient(headers=self.headers, timeout=30, event_hooks={"request": [ssrf_safe_event_hook]}) as client:
        sitemap_urls = await self.discover_sitemap_urls(client)

        for sitemap_url in sitemap_urls:
            try:
                response = await client.get(sitemap_url)
                response.raise_for_status()

                root = ET.fromstring(response.content)
                ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

                for url_elem in root.findall("ns:url", ns):
                    loc = url_elem.find("ns:loc", ns)
                    lastmod = url_elem.find("ns:lastmod", ns)

                    if loc is not None:
                        url = loc.text
                        mod_date = lastmod.text if lastmod is not None else None

                        # Filter for recipe URLs only
                        if "/recept/" in url or "/recipe/" in url:
                            all_recipes.append((url, mod_date))

            except Exception as e:
                logger.warning(f"Error fetching {sitemap_url}: {e}")

    return all_recipes
```

### Main Entry Points (Option B)

```python
async def test_scrape():
    """Test mode: 20 recipes, no database save."""
    scraper = [SiteName]Scraper()
    result = await scraper.scrape_all_recipes(max_recipes=20)

    logger.info(f"\nTest complete: {len(result)} recipes scraped ({result.status})")
    for recipe in result[:3]:
        logger.info(f"  - {recipe['name']}")

async def full_scrape():
    """Incremental mode: Only scrape NEW recipes."""
    scraper = [SiteName]Scraper()
    result = await scraper.scrape_all_recipes()

    if result.should_save:
        stats = save_to_database(result)
        logger.info(f"Created: {stats['created']}, Updated: {stats['updated']}")
    else:
        logger.info(result.reason or "No new recipes to scrape")

async def overwrite_scrape():
    """Overwrite mode: Clear all old data, scrape everything."""
    scraper = [SiteName]Scraper()
    result = await scraper.scrape_all_recipes(force_all=True)

    stats = save_to_database(result, clear_old=True)
    logger.info(f"Cleared: {stats['cleared']}, Created: {stats['created']}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        mode = sys.argv[1]

        if mode == "--test":
            asyncio.run(test_scrape())
        elif mode == "--overwrite":
            asyncio.run(overwrite_scrape())
        else:
            print(f"Unknown argument: {mode}")
            sys.exit(1)
    else:
        asyncio.run(full_scrape())
```

### Notes (Option B)

- **DB_SOURCE_NAME**: Must match the `source_name` field in saved recipes exactly!
- Use Semaphore to limit concurrent requests (10 is a good default for httpx)
- Always include fallback sitemaps in case dynamic discovery fails
- Deduplicate recipes by URL before saving to prevent DB errors
- Handle both JSON-LD arrays and single objects
- Use `parse_iso8601_duration()` from `_common.py` for prep times (don't reimplement)
- Log progress in batches for GUI parsing
- Use `ssrf_safe_event_hook` on httpx clients to block redirects to private IPs (recommended)

---

## Timeout Constants

Import from `app/constants_timeouts.py` instead of hardcoding:

```python
from constants_timeouts import HTTP_TIMEOUT, PAGE_LOAD_TIMEOUT, PAGE_NETWORK_IDLE_TIMEOUT, DOMCONTENT_TIMEOUT
```

| Constant | Value | Use for |
|---|---|---|
| `HTTP_TIMEOUT` | 30s | httpx: `timeout=HTTP_TIMEOUT` |
| `PAGE_LOAD_TIMEOUT` | 30000ms | Playwright: `page.goto(url, timeout=...)` |
| `PAGE_NETWORK_IDLE_TIMEOUT` | 30000ms | `page.wait_for_load_state("networkidle", timeout=...)` |
| `DOMCONTENT_TIMEOUT` | 30000ms | `page.wait_for_load_state("domcontentloaded", timeout=...)` |

Specific waits (selectors, animations) should stay as local constants tuned to the specific site.

## Database Access

Recipe scrapers may read from the database when they need incremental state,
such as the set of URLs already fetched for this source:

```python
from database import get_db_session
from models import FoundRecipe

# Check which recipes already exist (for incremental mode)
with get_db_session() as db:
    existing = db.query(FoundRecipe.url).filter(
        FoundRecipe.source_name == DB_SOURCE_NAME
    ).all()
    existing_urls = {row.url for row in existing}
```

The `FoundRecipe` model (in `app/models.py`) has these key columns:
- `name` (required), `url` (required, unique), `source_name`, `ingredients` (JSONB array)
- `image_url`, `prep_time_minutes`, `servings`
- `excluded` (user can hide recipes — respect this in incremental mode)

Use `save_recipes_to_database()` from `_common.py` for writes instead of direct
inserts. It applies the shared result semantics, respects permanently excluded
recipe URLs, runs spell-check, and keeps GUI/scheduler behavior consistent.

The `get_db_session()` context manager auto-commits on success and rolls back on
exception.

## Shared Utilities

`scrapers/recipes/_common.py` provides helper functions that new scrapers can
import to avoid reimplementing common patterns. Use the result/save helpers for
new scrapers so the GUI, scheduler, and CLI all interpret empty and failed runs
the same way.

```python
from scrapers.recipes._common import (
    RecipeScrapeResult,
    incremental_attempt_limit,
    make_recipe_scrape_result,
    recipe_target_reached,
    save_recipes_to_database,
    StreamingRecipeSaver,
    parse_iso8601_duration,
    extract_json_ld_recipe,
)
```

### `make_recipe_scrape_result(...) -> RecipeScrapeResult`

Wraps scraped recipes with status metadata:

```python
# Successful scrape with recipes
return make_recipe_scrape_result(recipes, force_all=force_all, max_recipes=max_recipes)

# Scrape worked, but incremental mode found nothing new
return make_recipe_scrape_result([], reason="no_new_recipes")

# Discovery/API failed; keep existing recipes untouched
return make_recipe_scrape_result([], failed=True, reason="no_recipe_urls")
```

`RecipeScrapeResult` is list-like for `len(result)`, iteration, and slicing. Use
`result.recipes` when you need the explicit recipe list.

### `incremental_attempt_limit(...) -> int`

Returns how many candidate URLs an incremental scrape should try for a
configured recipe target:

```python
attempt_limit = incremental_attempt_limit(
    max_recipes=max_recipes,
    available_count=len(candidate_urls),
    default_limit=MAX_RECIPES,
)
urls_to_scrape = candidate_urls[:attempt_limit]
```

Use this when `max_recipes` comes from the GUI. In incremental mode it is a
target for successfully parsed recipes, not a strict URL-attempt count. The
helper gives the scraper a small hidden buffer for recipe-like URLs that turn
out to be articles, categories, or invalid pages, while still enforcing a hard
cap.

### `recipe_target_reached(...) -> bool`

Stops a scrape once the usable-recipe target has actually been reached:

```python
if recipe:
    if stream_saver:
        await stream_saver.add(recipe)
    else:
        recipes.append(recipe)

    if recipe_target_reached(
        max_recipes=max_recipes,
        recipes=recipes,
        stream_saver=stream_saver,
    ):
        break
```

Use this together with `StreamingRecipeSaver`, because `StreamingRecipeSaver`
tracks the number of accepted recipes even when batches have already been
flushed to the database.

### `StreamingRecipeSaver`

Saves parsed recipes in small batches during a production scrape:

```python
saver = StreamingRecipeSaver(DB_SOURCE_NAME, overwrite=overwrite, max_recipes=max_recipes)
await saver.add(recipe)      # Flushes automatically every 50 recipes by default
stats = await saver.finish() # Flushes remaining recipes and returns save stats
```

Use it from `scrape_and_save()` rather than calling `save_recipes_to_database()`
inside your scrape loop. In full/overwrite mode it upserts batches as they are
found, then deletes stale source recipes only after the full scrape succeeds.
Cancelled runs call `finish(cancelled=True)`, which drops pending unsaved
recipes and returns cancelled status metadata.

### `parse_iso8601_duration(duration: str) -> Optional[int]`

Parses ISO 8601 duration strings (PT30M, PT1H30M, P1DT2H30M) to minutes.
Returns None if unparseable or zero.

```python
# Instead of writing your own regex:
prep_time = parse_iso8601_duration(data.get("totalTime", ""))
```

### `extract_json_ld_recipe(html: str) -> Optional[Dict]`

Extracts Recipe schema from JSON-LD `<script>` tags. Handles direct objects,
`@graph` arrays, and list-of-schemas structures.

```python
# Instead of writing your own JSON-LD extraction:
recipe_data = extract_json_ld_recipe(html)
if not recipe_data:
    return None

name = recipe_data.get("name", "").strip()
ingredients = recipe_data.get("recipeIngredient", [])
```

**Note:** Coop's Playwright scraper extracts JSON-LD via browser JavaScript,
so this function is mainly useful for httpx-based scrapers (Option B).

## Spell Check (Automatic)

`save_recipes_to_database()` automatically runs a spell checker on all ingredient text. This uses Levenshtein distance (max 1 edit) to correct typos in ingredient words against the known keyword dictionary (e.g., `kycklingfilé`, `basilika`, `yoghurt`).

**No action needed from scraper authors** — spell check runs automatically at save time. Key rules:
- Only words with 5+ characters are checked
- Only corrects if exactly one candidate matches (ambiguous = skip)
- Skips words already handled by normalization (`normalize_ingredient()`)
- Skips known international/brand words (salame, caviar, rigatini, etc.)
- Corrections are stored in `spell_corrections` table for user review via the Config UI

Users can revert corrections per recipe or globally exclude word pairs from future correction via the Spell Check modal in the Config page. Global exclusions are stored in the `spell_excluded_words` table.
