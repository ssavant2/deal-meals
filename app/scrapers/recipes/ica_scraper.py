"""
ICA.se Recipe Scraper - Top 1000 by lastmod

📝 DESCRIPTION:
Scrapes Swedish recipes from ICA.se (Sweden's largest grocery chain).
Uses sitemaps to find recipes and selects the 1000 most recently updated,
which typically includes the most popular recipes (they get frequent updates).

🎯 STRATEGY:
1. Fetch all 3 recipe sitemaps (23,569 total recipes)
2. Sort by lastmod date (most recent first)
3. Take top 1000 (or new ones in incremental mode)
4. Scrape JSON-LD Recipe schema from each page
5. Also extract comment count for popularity tracking

✨ FEATURES:
- Sitemap-based URL discovery with lastmod dates
- Top 1000 by recency = likely popular recipes
- JSON-LD parsing for structured data
- Comment count extraction for future popularity sorting
- Gentle 1s delay between requests

🔧 RUN MODES (GUI-compatible interface):
1. DEFAULT: Incremental sync from top 1000 by lastmod
   - Only scrapes recipes not already in database
   - Works from the 1000 most recently updated recipes
   - Typically adds 0-50 new recipes per run (as ICA updates content)
   scraper.scrape_all_recipes()  # Returns RecipeScrapeResult
   save_to_database(recipes)      # Saves to DB

2. TEST MODE: Scrape 20 recipes, don't save to database
   scraper.scrape_all_recipes(max_recipes=20)

3. OVERWRITE MODE: Clear ALL old recipes, scrape top 1000
   scraper.scrape_all_recipes(force_all=True)
   save_to_database(recipes, clear_old=True)

📊 OUTPUT:
~1000 recipes from ICA.se saved in PostgreSQL

🏷️ METADATA (for GUI):
SCRAPER_NAME = "ICA.se"
DB_SOURCE_NAME = "ICA.se"
SCRAPER_DESCRIPTION = "Recept från ica.se"
EXPECTED_RECIPE_COUNT = 1000
SOURCE_URL = "https://www.ica.se/recept/"
"""

import httpx
from loguru import logger
from utils.security import ssrf_safe_event_hook
from typing import List, Dict, Optional, Tuple
import asyncio
import re
import json
import os
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

import sys

# Add app directory to path
app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, app_dir)

from database import get_db_session
from scrapers.recipes._common import (
    _is_type, RecipeScrapeResult, incremental_attempt_limit,
    make_recipe_scrape_result, parse_iso8601_duration, recipe_target_reached,
    split_serving_lists, StreamingRecipeSaver
)

# GUI Metadata
SCRAPER_NAME = "ICA.se"
DB_SOURCE_NAME = "ICA.se"
SCRAPER_DESCRIPTION = "Recept från ica.se"
EXPECTED_RECIPE_COUNT = 1000
SOURCE_URL = "https://www.ica.se/recept/"

# Scraper config
MAX_RECIPES = 1000  # Top N by lastmod
REQUEST_DELAY = 1.0  # Seconds between requests
CONCURRENT_REQUESTS = 5  # Parallel requests
MIN_INGREDIENTS = 3  # Skip recipes with fewer ingredients

# ICA's recipe sitemaps (fixed URLs)
SITEMAP_URLS = [
    "https://www.ica.se/recept/sitemaps/recipes/1/",
    "https://www.ica.se/recept/sitemaps/recipes/2/",
    "https://www.ica.se/recept/sitemaps/recipes/3/",
]


class IcaScraper:
    """Scraper for ICA.se recipes using sitemaps."""

    def __init__(self):
        self.base_url = "https://www.ica.se"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
            # Note: Don't set Accept-Encoding - let httpx handle it automatically
        }
        # For progress callbacks (WebSocket updates)
        self._progress_callback = None
        self._cancel_flag = False

    def set_progress_callback(self, callback):
        """Set callback for progress updates."""
        self._progress_callback = callback

    def cancel(self):
        """Signal cancellation."""
        self._cancel_flag = True

    async def _report_progress(self, message: str, current: int = 0, total: int = 0, success: int = 0):
        """Report progress via callback if set."""
        if self._progress_callback:
            await self._progress_callback({
                "message": message,
                "current": current,
                "total": total,
                "success": success,
            })

    async def _report_activity(self):
        """Report scraper activity without changing visible progress."""
        if self._progress_callback:
            try:
                await self._progress_callback({"activity_only": True})
            except Exception:
                pass

    # ========== SITEMAP PARSING ==========

    async def get_all_recipe_urls(self, client: httpx.AsyncClient) -> List[Tuple[str, str]]:
        """
        Fetch all recipe URLs from ICA's sitemaps.

        Returns:
            List of (url, lastmod) tuples, sorted by lastmod descending
        """
        logger.info("📦 Fetching recipe URLs from sitemaps...")
        all_urls = []

        for sitemap_url in SITEMAP_URLS:
            try:
                response = await client.get(sitemap_url, follow_redirects=True)
                response.raise_for_status()

                # Get XML text (httpx handles decompression automatically)
                xml_text = response.text

                root = ET.fromstring(xml_text)
                ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

                for url_elem in root.findall(".//sm:url", ns):
                    loc = url_elem.find("sm:loc", ns)
                    lastmod = url_elem.find("sm:lastmod", ns)

                    if loc is not None:
                        url = loc.text.strip()
                        mod_date = lastmod.text.strip() if lastmod is not None else "1970-01-01"
                        all_urls.append((url, mod_date))

                logger.info(f"   Found {len(all_urls)} URLs so far from {sitemap_url}")

            except Exception as e:
                logger.error(f"Error fetching sitemap {sitemap_url}: {e}")
                import traceback
                logger.debug(traceback.format_exc())

        # Sort by lastmod descending (newest first)
        all_urls.sort(key=lambda x: x[1], reverse=True)
        logger.info(f"   Total: {len(all_urls)} recipe URLs, sorted by lastmod")

        return all_urls

    # ========== RECIPE SCRAPING ==========

    async def scrape_recipe(self, client: httpx.AsyncClient, url: str) -> Optional[Dict]:
        """
        Scrape a single recipe page.

        Returns:
            Recipe dict or None if failed/filtered
        """
        try:
            response = await client.get(url, follow_redirects=True)

            if response.status_code == 403:
                logger.debug(f"   HTTP 403: {url}")
                return None
            elif response.status_code == 404:
                logger.debug(f"   HTTP 404: {url}")
                return None

            response.raise_for_status()
            html = response.text

            # Extract JSON-LD
            recipe_data = self._extract_json_ld(html, url)
            if not recipe_data:
                logger.debug(f"   No JSON-LD found: {url}")
                return None

            return recipe_data

        except httpx.TimeoutException:
            logger.warning(f"   Timeout: {url}")
            return None
        except Exception as e:
            logger.debug(f"   Error scraping {url}: {e}")
            return None

    def _extract_json_ld(self, html: str, url: str) -> Optional[Dict]:
        """Extract recipe data from JSON-LD schema."""
        # Find JSON-LD script tags
        pattern = r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>'
        matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)

        for match in matches:
            try:
                data = json.loads(match)

                # Handle @graph structure
                if isinstance(data, dict) and "@graph" in data:
                    for item in data["@graph"]:
                        if isinstance(item, dict) and _is_type(item, "Recipe"):
                            return self._parse_recipe_schema(item, url)

                # Direct Recipe object
                if isinstance(data, dict) and _is_type(data, "Recipe"):
                    return self._parse_recipe_schema(data, url)

                # List of objects
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") == "Recipe":
                            return self._parse_recipe_schema(item, url)

            except json.JSONDecodeError:
                continue

        return None

    def _parse_recipe_schema(self, schema: Dict, url: str) -> Optional[Dict]:
        """Parse Recipe schema.org data into our format."""
        try:
            name = schema.get("name", "").strip()
            if not name:
                return None

            # Parse ingredients
            ingredients = []
            raw_ingredients = schema.get("recipeIngredient", [])
            if isinstance(raw_ingredients, list):
                ingredients = [ing.strip() for ing in raw_ingredients if ing and ing.strip()]
            # Split "Till servering" lists: "jordgubbar, pistagenötter och dryck" → 3 items
            ingredients = split_serving_lists(ingredients)

            # Filter recipes with too few ingredients
            if len(ingredients) < MIN_INGREDIENTS:
                logger.debug(f"   Skipping {name}: only {len(ingredients)} ingredients")
                return None

            # Parse cooking time (PT30M -> 30)
            prep_time = parse_iso8601_duration(schema.get("prepTime", ""))
            cook_time = parse_iso8601_duration(schema.get("cookTime", ""))
            total_time = parse_iso8601_duration(schema.get("totalTime", ""))

            # Use total time, or sum of prep+cook, or just prep
            time_minutes = total_time or ((prep_time or 0) + (cook_time or 0)) or prep_time

            # Parse servings (optional - recipes without servings are still saved)
            servings = None
            yield_val = schema.get("recipeYield")
            if yield_val:
                if isinstance(yield_val, list):
                    yield_val = yield_val[0] if yield_val else ""
                if isinstance(yield_val, (int, float)):
                    servings = int(yield_val)
                elif isinstance(yield_val, str):
                    # Extract number from "4 portioner" or "4 servings"
                    match = re.search(r'(\d+)', str(yield_val))
                    if match:
                        servings = int(match.group(1))

            # Get image URL
            image_url = ""
            image = schema.get("image")
            if isinstance(image, str):
                image_url = image
            elif isinstance(image, list) and image:
                image_url = image[0] if isinstance(image[0], str) else image[0].get("url", "")
            elif isinstance(image, dict):
                image_url = image.get("url", "")

            return {
                "source_name": DB_SOURCE_NAME,
                "name": name,
                "ingredients": ingredients,
                "prep_time_minutes": time_minutes,
                "servings": servings,
                "image_url": image_url,
                "url": url,
                "scraped_at": datetime.now(timezone.utc),
            }

        except Exception as e:
            logger.debug(f"Error parsing recipe schema: {e}")
            return None

    # ========== MAIN SCRAPING LOGIC ==========

    async def scrape_recipes(
        self,
        client: httpx.AsyncClient,
        urls: List[str],
        test_mode: bool = False,
        stream_saver: Optional[StreamingRecipeSaver] = None,
        max_recipes: Optional[int] = None,
    ) -> List[Dict]:
        """
        Scrape multiple recipes with rate limiting.

        Args:
            client: HTTP client
            urls: List of recipe URLs to scrape
            test_mode: If True, don't count toward limits

        Returns:
            List of recipe dicts
        """
        recipes = []
        total = len(urls)

        logger.info(f"📄 Scraping {total} recipes...")
        await self._report_progress(f"Fetching {total} recipes...", 0, total, 0)

        for i, url in enumerate(urls):
            if self._cancel_flag:
                logger.info("🛑 Scraping cancelled")
                break

            recipe = await self.scrape_recipe(client, url)
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
            await self._report_activity()

            # Progress logging
            if (i + 1) % 10 == 0 or (i + 1) == total:
                found_count = stream_saver.seen_count if stream_saver else len(recipes)
                logger.info(f"   Progress: {i + 1}/{total} ({found_count} recipes found)")
                await self._report_progress(
                    f"Fetched {found_count} recipes...",
                    i + 1, total, found_count
                )

            # Rate limiting
            await asyncio.sleep(REQUEST_DELAY)

        return recipes

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
            max_recipes: Limit number of recipes (for test mode, e.g., 20)
            batch_size: Not used (kept for interface compatibility)
            force_all: If True, scrape all recipes ignoring existing (for overwrite mode)

        Returns:
            RecipeScrapeResult with scraped recipe dicts
        """
        self._cancel_flag = False

        async with httpx.AsyncClient(
            headers=self.headers,
            timeout=30.0,
            follow_redirects=True,
            event_hooks={"request": [ssrf_safe_event_hook]}
        ) as client:

            # Get all URLs sorted by lastmod
            all_urls = await self.get_all_recipe_urls(client)

            if not all_urls:
                logger.error("No recipe URLs found!")
                return make_recipe_scrape_result(
                    [],
                    force_all=force_all,
                    max_recipes=max_recipes,
                    failed=True,
                    reason="no_recipe_urls",
                )

            # Determine which URLs to scrape
            if force_all:
                # Full overwrite mode: top MAX_RECIPES by lastmod
                urls_to_scrape = [url for url, _ in all_urls[:max_recipes or MAX_RECIPES]]
                logger.info(f"🔄 OVERWRITE MODE: Scraping {len(urls_to_scrape)} recipes")
            else:
                # Incremental: only new URLs not in database
                existing_urls = self._get_existing_urls()
                all_candidate_urls = [url for url, _ in all_urls]
                if max_recipes:
                    new_candidate_urls = [
                        url for url in all_candidate_urls if url not in existing_urls
                    ]
                    attempt_limit = incremental_attempt_limit(
                        max_recipes=max_recipes,
                        available_count=len(new_candidate_urls),
                        default_limit=MAX_RECIPES,
                    )
                    urls_to_scrape = new_candidate_urls[:attempt_limit]
                    candidate_count = len(new_candidate_urls)
                else:
                    candidate_urls = all_candidate_urls[:MAX_RECIPES]
                    urls_to_scrape = [
                        url for url in candidate_urls if url not in existing_urls
                    ]
                    candidate_count = len(candidate_urls)

                logger.info(
                    f"📥 INCREMENTAL: {len(urls_to_scrape)} new recipes to scrape "
                    f"(target {max_recipes or 'auto'}, from {candidate_count} sitemap candidates)"
                )

                if not urls_to_scrape:
                    logger.info("✅ Already up to date!")
                    return make_recipe_scrape_result(
                        [],
                        force_all=force_all,
                        max_recipes=max_recipes,
                        reason="no_new_recipes",
                    )

            # Scrape recipes
            recipes = await self.scrape_recipes(
                client,
                urls_to_scrape,
                bool(max_recipes),
                stream_saver=stream_saver,
                max_recipes=max_recipes,
            )

            if self._cancel_flag:
                return make_recipe_scrape_result(
                    [],
                    force_all=force_all,
                    max_recipes=max_recipes,
                    cancelled=True,
                    reason="cancelled",
                )

            logger.info(f"✅ Scraped {len(recipes)} recipes")
            return make_recipe_scrape_result(
                recipes,
                force_all=force_all,
                max_recipes=max_recipes,
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

    # ========== DATABASE OPERATIONS ==========

    def _get_existing_urls(self) -> set:
        """Get all existing recipe URLs from database."""
        with get_db_session() as db:
            from sqlalchemy import text
            result = db.execute(
                text("SELECT url FROM found_recipes WHERE source_name = :source"),
                {"source": DB_SOURCE_NAME}
            )
            return {row.url for row in result}



def save_to_database(recipes: List[Dict], clear_old: bool = False) -> Dict[str, int]:
    """Save recipes to database (module-level function for GUI compatibility)."""
    from scrapers.recipes._common import save_recipes_to_database
    return save_recipes_to_database(recipes, DB_SOURCE_NAME, clear_old=clear_old)


async def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="ICA.se Recipe Scraper")
    parser.add_argument("--test", action="store_true", help="Test mode: scrape 20 recipes, don't save")
    parser.add_argument("--overwrite", action="store_true", help="Delete existing and scrape fresh")
    args = parser.parse_args()

    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )

    print("\n" + "=" * 60)
    if args.test:
        print("🧪 ICA.se TEST MODE")
    elif args.overwrite:
        print("🔄 ICA.se FULL OVERWRITE")
    else:
        print("📥 ICA.se INCREMENTAL SYNC")
    print("=" * 60 + "\n")

    scraper = IcaScraper()

    # Use the template-compatible interface
    if args.test:
        recipes = await scraper.scrape_all_recipes(max_recipes=20)
        print(f"\n🧪 TEST: Scraped {len(recipes)} recipes (not saved)")
        for r in recipes[:3]:
            print(f"   - {r['name']}")
    else:
        recipes = await scraper.scrape_all_recipes(force_all=args.overwrite)

        if recipes:
            stats = save_to_database(recipes, clear_old=args.overwrite)
            print(f"\n✅ Done! Created: {stats['created']}, Updated: {stats['updated']}")
        else:
            print("\n✅ Already up to date - no new recipes to scrape")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
