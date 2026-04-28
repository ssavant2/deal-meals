"""
Coop.se Recipe Scraper - Playwright + Sitemap

DESCRIPTION:
Scrapes Swedish recipes from Coop.se using their sitemap.
Takes ~1250 URLs to get approximately 1000 valid recipes.
Requires Playwright for JavaScript rendering (JSON-LD is client-side).

STRATEGY:
1. Fetch sitemap.xml (~9200 URLs)
2. Shuffle URLs with fixed seed (deterministic but varied selection)
3. Take first 1250 URLs from shuffled list
4. Render each page with Playwright (2 concurrent workers)
5. Extract JSON-LD Recipe schema after JS execution
6. Save to database

FEATURES:
- Sitemap-based URL discovery
- Seeded random shuffle for varied recipe selection
- Playwright for JS-rendered pages
- JSON-LD parsing for structured data
- 2 concurrent workers for faster scraping

RUN MODES (GUI-compatible interface):
1. DEFAULT: Incremental sync - max 50 new recipes per run
   scraper.scrape_all_recipes()
   (Good for scheduled jobs - won't overwhelm with 1000+ recipes)

2. TEST MODE: Scrape 20 recipes, don't save to database
   scraper.scrape_all_recipes(max_recipes=20)

3. OVERWRITE MODE: Clear ALL old recipes, scrape up to 1100 URLs
   scraper.scrape_all_recipes(force_all=True)
   save_to_database(recipes, clear_old=True)

OUTPUT:
~1000 recipes from Coop.se saved in PostgreSQL

METADATA (for GUI):
SCRAPER_NAME = "Coop.se"
DB_SOURCE_NAME = "Coop.se"
SCRAPER_DESCRIPTION = "Recept från coop.se"
EXPECTED_RECIPE_COUNT = 1000
SOURCE_URL = "https://www.coop.se/recept"
"""

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from loguru import logger
from typing import List, Dict, Optional
import asyncio
import html as html_lib
import re
import json
import os
import random
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
import sys
import httpx
from utils.security import ssrf_safe_event_hook

# Add app directory to path
app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, app_dir)

from database import get_db_session
from models import FoundRecipe
from scrapers.recipes._common import (
    RecipeScrapeResult, make_recipe_scrape_result,
    parse_iso8601_duration, split_serving_lists, StreamingRecipeSaver
)

# GUI Metadata
SCRAPER_NAME = "Coop.se"
DB_SOURCE_NAME = "Coop.se"
SCRAPER_DESCRIPTION = "Recept från coop.se"
EXPECTED_RECIPE_COUNT = 1000
SOURCE_URL = "https://www.coop.se/recept"

# Scraper config
MAX_URLS = 1100  # URLs to try for FULL scrape (expect ~90% hit rate → ~1000 recipes)
MAX_INCREMENTAL = 50  # Max new recipes per INCREMENTAL run (scheduled jobs)
REQUEST_DELAY = 1.0  # Seconds between requests (safe with single worker)
CONCURRENT_WORKERS = 1  # Single worker to avoid Playwright race conditions
PAGE_TIMEOUT = 30000  # 30 seconds for page load
JS_WAIT_TIME = 2000  # Wait for JS to render JSON-LD
MIN_INGREDIENTS = 3  # Skip recipes with fewer ingredients
RANDOM_SEED = 42  # Fixed seed for deterministic shuffle


class CoopScraper:
    """Scraper for Coop.se using Playwright + sitemap."""

    def __init__(self):
        self.base_url = "https://www.coop.se"
        self.sitemap_url = f"{self.base_url}/recept/sitemap.xml"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
        }
        self._progress_callback = None
        self._cancel_flag = False
        self._progress = {"total": 0, "current": 0, "success": 0}
        self._fail_reasons = {
            "http_error": 0,
            "no_jsonld": 0,
            "no_recipe_type": 0,
            "no_name": 0,
            "no_ingredients": 0,
            "few_ingredients": 0,
            "timeout": 0
        }

    def cancel(self):
        """Cancel ongoing scrape."""
        self._cancel_flag = True

    def set_progress_callback(self, callback):
        """Set callback for progress updates (called by router)."""
        self._progress_callback = callback

    async def _send_progress(self, message: str = None):
        """Send progress update via WebSocket."""
        if self._progress_callback:
            try:
                await self._progress_callback({
                    "type": "progress",
                    "current": self._progress["current"],
                    "total": self._progress["total"],
                    "success": self._progress["success"],
                    "message": message
                })
            except Exception as e:
                logger.debug(f"WebSocket progress callback failed: {e}")

    async def _send_activity(self):
        """Report scraper activity without changing visible progress."""
        if self._progress_callback:
            try:
                await self._progress_callback({"activity_only": True})
            except Exception as e:
                logger.debug(f"WebSocket activity callback failed: {e}")

    async def get_recipe_urls_from_sitemap(self) -> List[str]:
        """Fetch recipe URLs from sitemap."""
        logger.info(f"Fetching sitemap: {self.sitemap_url}")

        async with httpx.AsyncClient(headers=self.headers, timeout=30, event_hooks={"request": [ssrf_safe_event_hook]}) as client:
            try:
                response = await client.get(self.sitemap_url)
                response.raise_for_status()

                root = ET.fromstring(response.content)
                ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

                urls = []
                for url_elem in root.findall("ns:url", ns):
                    loc = url_elem.find("ns:loc", ns)
                    if loc is not None and loc.text:
                        url = loc.text.strip()
                        # Filter: only recipe detail pages, not category pages
                        # Recipe URLs: /recept/recipe-name/
                        # Category URLs have nested paths like /recept/category/subcategory/
                        path = url.replace(f"{self.base_url}/recept/", "")
                        if path and "/" not in path.rstrip("/"):
                            urls.append(url)

                logger.info(f"Found {len(urls)} recipe URLs in sitemap")
                return urls

            except Exception as e:
                logger.error(f"Failed to fetch sitemap: {e}")
                return []

    def get_existing_urls(self) -> set:
        """Get URLs of recipes already in database."""
        with get_db_session() as db:
            existing = db.query(FoundRecipe.url).filter(
                FoundRecipe.source_name == DB_SOURCE_NAME
            ).all()
            return {r[0] for r in existing}

    async def scrape_recipe_playwright(
        self,
        page,
        url: str
    ) -> Optional[Dict]:
        """Scrape a single recipe using Playwright."""
        try:
            await page.goto(url, timeout=PAGE_TIMEOUT)
            await page.wait_for_timeout(JS_WAIT_TIME)

            # Extract JSON-LD after JS renders
            jsonld_data = await page.evaluate('''() => {
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                for (const script of scripts) {
                    try {
                        const data = JSON.parse(script.textContent);
                        const t = data["@type"];
                        if (t === "Recipe" || (Array.isArray(t) && t.includes("Recipe"))) {
                            return data;
                        }
                    } catch (e) {}
                }
                return null;
            }''')

            if not jsonld_data:
                self._fail_reasons["no_jsonld"] += 1
                return None

            at_type = jsonld_data.get("@type")
            is_recipe = at_type == "Recipe" or (isinstance(at_type, list) and "Recipe" in at_type)
            if not is_recipe:
                self._fail_reasons["no_recipe_type"] += 1
                return None

            # Use final URL after redirects (e.g. /rodkalslasagne/ → /gronsakslasagne/)
            final_url = page.url or url

            recipe = {
                "source_name": DB_SOURCE_NAME,
                "url": final_url,
                "scraped_at": datetime.now(timezone.utc)
            }

            # Name (required)
            name = jsonld_data.get("name", "").strip()
            if not name:
                self._fail_reasons["no_name"] += 1
                return None
            recipe["name"] = html_lib.unescape(name)

            # Ingredients (required)
            ingredients = jsonld_data.get("recipeIngredient", [])
            # Split "Till servering" lists: "salladslök, chilimajonnäs och sesamfrön" → 3 items
            ingredients = split_serving_lists(ingredients)
            if not ingredients:
                self._fail_reasons["no_ingredients"] += 1
                return None

            if len(ingredients) < MIN_INGREDIENTS:
                self._fail_reasons["few_ingredients"] += 1
                return None

            recipe["ingredients"] = ingredients

            # Image
            image = jsonld_data.get("image")
            if isinstance(image, list) and image:
                image = image[0]
            if isinstance(image, str):
                # Fix protocol-relative URLs
                if image.startswith("//"):
                    image = "https:" + image
                recipe["image_url"] = html_lib.unescape(image)
            else:
                recipe["image_url"] = None

            # Servings
            servings = jsonld_data.get("recipeYield")
            if isinstance(servings, str):
                match = re.search(r'(\d+)', servings)
                if match:
                    recipe["servings"] = int(match.group(1))
            elif isinstance(servings, int):
                recipe["servings"] = servings

            # Prep time
            total_time = jsonld_data.get("totalTime") or jsonld_data.get("cookTime")
            recipe["prep_time_minutes"] = parse_iso8601_duration(total_time)

            return recipe

        except PlaywrightTimeout:
            self._fail_reasons["timeout"] += 1
            return None
        except Exception as e:
            logger.debug(f"Error scraping {url}: {e}")
            self._fail_reasons["http_error"] += 1
            return None

    async def scrape_all_recipes(
        self,
        max_recipes: Optional[int] = None,
        batch_size: int = CONCURRENT_WORKERS,
        force_all: bool = False,
        stream_saver: Optional[StreamingRecipeSaver] = None,
    ) -> RecipeScrapeResult:
        """
        Main scraping method.

        Args:
            max_recipes: Limit number of recipes (for test mode)
            batch_size: Number of concurrent workers (default: CONCURRENT_WORKERS)
            force_all: If True, ignore existing recipes

        Returns:
            RecipeScrapeResult with scraped recipe dicts
        """
        self._cancel_flag = False
        self._progress = {"total": 0, "current": 0, "success": 0}
        self._fail_reasons = {k: 0 for k in self._fail_reasons}

        # Get URLs from sitemap
        all_urls = await self.get_recipe_urls_from_sitemap()
        if not all_urls:
            logger.error("No URLs found in sitemap")
            return make_recipe_scrape_result(
                [],
                force_all=force_all,
                max_recipes=max_recipes,
                failed=True,
                reason="no_recipe_urls",
            )

        # Shuffle URLs with fixed seed for deterministic but varied selection
        rng = random.Random(RANDOM_SEED)
        shuffled_urls = all_urls.copy()
        rng.shuffle(shuffled_urls)
        logger.info(f"Shuffled {len(shuffled_urls)} URLs with seed {RANDOM_SEED}")

        # Filter out existing unless force_all
        if force_all:
            urls_to_scrape = shuffled_urls[:MAX_URLS]
            logger.info(f"Force mode: scraping {len(urls_to_scrape)} URLs")
        else:
            existing_urls = self.get_existing_urls()
            new_urls = [u for u in shuffled_urls if u not in existing_urls]
            # Use higher limit until we reach target (~1000 recipes), then small batches
            filling_initial_target = len(existing_urls) < EXPECTED_RECIPE_COUNT * 0.9
            if max_recipes:
                limit = max_recipes
            elif filling_initial_target:
                limit = MAX_URLS
            else:
                limit = MAX_INCREMENTAL
            urls_to_scrape = new_urls[:limit]
            if max_recipes:
                logger.info(f"Incremental mode (configured): {len(urls_to_scrape)} URLs (of {len(new_urls)} new, skipped {len(existing_urls)} existing)")
            elif filling_initial_target:
                logger.info(f"Incremental mode (filling): {len(urls_to_scrape)} URLs — DB has {len(existing_urls)}, target {EXPECTED_RECIPE_COUNT}")
            else:
                logger.info(f"Incremental mode: {len(urls_to_scrape)} URLs (of {len(new_urls)} new, skipped {len(existing_urls)} existing)")

        # Apply max_recipes limit
        if max_recipes:
            urls_to_scrape = urls_to_scrape[:max_recipes]

        if not urls_to_scrape:
            logger.info("No new recipes to scrape")
            return make_recipe_scrape_result(
                [],
                force_all=force_all,
                max_recipes=max_recipes,
                reason="no_new_recipes",
            )

        self._progress["total"] = len(urls_to_scrape)
        recipes = []
        recipes_lock = asyncio.Lock()

        logger.info(f"Starting Playwright scrape of {len(urls_to_scrape)} URLs with {batch_size} workers...")

        async def worker(worker_id: int, browser, urls: List[str]):
            """Worker that processes a subset of URLs with its own context."""
            # Track all contexts so we can clean up on exit (prevents leaks)
            contexts = []
            context = await browser.new_context(
                user_agent=self.headers["User-Agent"],
                locale="sv-SE"
            )
            contexts.append(context)
            page = await context.new_page()
            consecutive_errors = 0
            max_consecutive_errors = 5

            try:
                for url in urls:
                    if self._cancel_flag:
                        break

                    try:
                        recipe = await self.scrape_recipe_playwright(page, url)
                        consecutive_errors = 0  # Reset on success
                    except Exception as e:
                        logger.warning(f"Worker {worker_id} error on {url}: {e}")
                        consecutive_errors += 1
                        recipe = None

                        # If too many consecutive errors, recreate context
                        if consecutive_errors >= max_consecutive_errors:
                            logger.warning(f"Worker {worker_id}: {consecutive_errors} consecutive errors, recreating context...")
                            try:
                                await context.close()
                            except Exception:
                                pass
                            context = await browser.new_context(
                                user_agent=self.headers["User-Agent"],
                                locale="sv-SE"
                            )
                            contexts.append(context)
                            page = await context.new_page()
                            consecutive_errors = 0

                    async with recipes_lock:
                        self._progress["current"] += 1
                        if recipe:
                            if stream_saver:
                                await stream_saver.add(recipe)
                            else:
                                recipes.append(recipe)
                            self._progress["success"] += 1

                        await self._send_activity()

                        # Progress logging every 10 recipes (Coop is slow, 1 worker)
                        if self._progress["current"] % 10 == 0:
                            logger.info(f"Progress: {self._progress['current']}/{len(urls_to_scrape)} ({self._progress['success']} successful)")
                            await self._send_progress()

                    # Delay between requests
                    await asyncio.sleep(REQUEST_DELAY)
            finally:
                for ctx in contexts:
                    try:
                        await ctx.close()
                    except Exception:
                        pass

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                # Split URLs among workers
                url_chunks = [urls_to_scrape[i::batch_size] for i in range(batch_size)]

                # Run workers concurrently - each worker manages its own context.
                # return_exceptions=True prevents one crashed worker from cancelling
                # the others — already-collected recipes are preserved.
                tasks = [
                    worker(i, browser, url_chunks[i])
                    for i in range(batch_size)
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"Worker {i} crashed: {result}")
            finally:
                await browser.close()

        # Log final stats
        found_count = stream_saver.seen_count if stream_saver else len(recipes)
        logger.info(f"Scraping complete: {found_count} recipes from {len(urls_to_scrape)} URLs")
        if urls_to_scrape:
            logger.info(f"Hit rate: {found_count/len(urls_to_scrape)*100:.1f}%")
        logger.info(f"Fail reasons: {self._fail_reasons}")

        return make_recipe_scrape_result(
            recipes,
            force_all=force_all,
            max_recipes=max_recipes,
            reason="cancelled" if self._cancel_flag else None,
            cancelled=self._cancel_flag,
        )

    async def scrape_incremental(self) -> RecipeScrapeResult:
        """Incremental scrape: only new recipes not already in database."""
        return await self.scrape_all_recipes()

    async def scrape_and_save(
        self,
        overwrite: bool = False,
        max_recipes: Optional[int] = None,
    ) -> Dict:
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


def save_to_database(recipes: List[Dict], clear_old: bool = False) -> Dict[str, int]:
    """Save recipes to database."""
    from scrapers.recipes._common import save_recipes_to_database
    return save_recipes_to_database(recipes, DB_SOURCE_NAME, clear_old=clear_old)


# =============================================================================
# RUN MODES
# =============================================================================

async def test_scrape():
    """Test mode: 20 recipes, no database save."""
    print("=" * 60)
    print("COOP SCRAPER - TEST MODE")
    print("Scraping 20 recipes (no database save)")
    print("=" * 60 + "\n")

    scraper = CoopScraper()
    recipes = await scraper.scrape_all_recipes(max_recipes=20)

    print(f"\nTest complete: {len(recipes)} recipes scraped")
    print("\nSample recipes:")
    for recipe in recipes[:5]:
        print(f"  - {recipe['name']} ({len(recipe.get('ingredients', []))} ingredients)")

    print("\n" + "=" * 60 + "\n")


async def full_scrape():
    """Incremental mode: Only scrape NEW recipes (default)."""
    print("=" * 60)
    print("COOP SCRAPER - INCREMENTAL MODE")
    print(f"Scraping up to {MAX_URLS} new recipes")
    print("=" * 60 + "\n")

    scraper = CoopScraper()
    recipes = await scraper.scrape_all_recipes()

    if recipes:
        stats = save_to_database(recipes)
        print(f"\nDone! Created: {stats['created']}, Updated: {stats['updated']}")
    else:
        print("\nNo new recipes to scrape")

    print("=" * 60 + "\n")


async def overwrite_scrape():
    """Overwrite mode: Clear all old data, scrape everything."""
    print("=" * 60)
    print("COOP SCRAPER - OVERWRITE MODE")
    print("Clearing old data and scraping fresh")
    print("=" * 60 + "\n")

    scraper = CoopScraper()
    recipes = await scraper.scrape_all_recipes(force_all=True)

    stats = save_to_database(recipes, clear_old=True)
    print(f"\nDone! Cleared: {stats['cleared']}, Created: {stats['created']}")

    print("=" * 60 + "\n")


async def main():
    """Main entry point with argument parsing."""
    if len(sys.argv) > 1:
        mode = sys.argv[1]

        if mode == "--test":
            await test_scrape()
        elif mode == "--overwrite":
            await overwrite_scrape()
        else:
            print(f"Unknown argument: {mode}")
            print("\nUsage:")
            print("  python coop_scraper.py              # Incremental sync (default)")
            print("  python coop_scraper.py --test       # Test mode (20 recipes, no DB)")
            print("  python coop_scraper.py --overwrite  # Full overwrite (clear + rescrape)")
            sys.exit(1)
    else:
        await full_scrape()


if __name__ == "__main__":
    asyncio.run(main())
