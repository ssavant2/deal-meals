"""
Mathem.se Recipe Scraper - FAST VERSION using Sitemap + httpx

DESCRIPTION:
Scrapes recipes from Mathem.se using their XML sitemap for URL discovery
and httpx for fast async HTTP requests. No browser needed!

STRATEGY:
1. Dynamically discover sitemap URL from robots.txt
2. Parse sitemap index to find recipe sitemaps
3. Filter out pre-made meals ("färdigpreppat" recipes)
4. Use lastmod dates for smart incremental sync
5. Scrape recipes with httpx + JSON-LD parsing (10x faster than Playwright)

FEATURES:
- Dynamic sitemap discovery from robots.txt (future-proof)
- Pure httpx for speed (no browser overhead)
- lastmod-based incremental sync
- 10 concurrent requests (vs 3 with browser)

RUN MODES:
1. DEFAULT: Smart incremental sync using lastmod dates
   - Only scrapes recipes not already in database
   - Uses sitemap lastmod to detect new/updated recipes
   - Scrapes ALL new recipes found (typically 0-20 per run)
   python mathem_scraper.py

2. TEST MODE: Scrape 20 recipes, don't save
   python mathem_scraper.py --test

3. OVERWRITE MODE: Clear ALL old recipes, full resync
   python mathem_scraper.py --overwrite

METADATA (for GUI):
SCRAPER_NAME = "Mathem.se"
SCRAPER_DESCRIPTION = "Recept från mathem.se"
EXPECTED_RECIPE_COUNT = 1000
SOURCE_URL = "https://www.mathem.se"
"""

import httpx
import html
from utils.security import ssrf_safe_event_hook
from loguru import logger
from typing import List, Dict, Optional, Tuple
import asyncio
import re
import json
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
import sys
import os

# Add app directory to path
app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, app_dir)

from database import get_db_session
from models import FoundRecipe
from scrapers.recipes._common import (
    _is_type, RecipeScrapeResult, incremental_attempt_limit,
    make_recipe_scrape_result, parse_iso8601_duration, recipe_target_reached,
    StreamingRecipeSaver
)
from scrapers.recipes.url_discovery_cache import (
    record_non_recipe_url,
    record_recipe_url,
    select_urls_for_scrape,
)

# GUI Metadata
SCRAPER_NAME = "Mathem.se"
DB_SOURCE_NAME = "Mathem.se"
SCRAPER_DESCRIPTION = "Recept från mathem.se"
EXPECTED_RECIPE_COUNT = 6000
SOURCE_URL = "https://www.mathem.se"

# Scraper config
MIN_INGREDIENTS = 3  # Skip recipes with fewer ingredients

# Non-food ingredient keywords that indicate product bundles, not recipes.
# Mathem has "recipes" that are actually product packages (office supplies,
# cleaning kits, party supplies). If ANY ingredient matches, skip the recipe.
# These words never appear in real cooking recipes.
NON_FOOD_INGREDIENTS = {
    'batterier', 'glödlampor', 'kopieringspapper', 'kollegieblock',
    'wc-rengöring', 'allrengöringsmedel', 'dammsugare', 'dokumentförstörare',
    'lamineringsmaskin', 'engångsgaffel', 'engångskniv', 'engångssked',
    'plastglas', 'häftapparat', 'bläckpatron', 'pennor',
    'konfettibomb', 'serpentin', 'ljusslinga',
    'ballonger', 'engångsduk', 'luftuppfriskare', 'fönsterputs',
    'städhandskar', 'skurhink', 'skurborste', 'dammsugarpåsar',
}

class MathemScraper:
    """Fast scraper for Mathem.se using sitemap + httpx."""

    def __init__(self):
        self.base_url = "https://www.mathem.se"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
        }
        self._progress_callback = None
        self._cancel_flag = False
        self._discovery_recorded_non_recipe = 0

    def set_progress_callback(self, callback):
        """Set callback for progress updates."""
        self._progress_callback = callback

    def cancel(self):
        """Signal cancellation."""
        self._cancel_flag = True

    async def _report_progress(self, current: int, total: int, success: int = 0):
        """Report progress via callback if set."""
        if self._progress_callback:
            await self._progress_callback({
                "current": current,
                "total": total,
                "success": success
            })

    async def _report_activity(self):
        """Report scraper activity without changing visible progress."""
        if self._progress_callback:
            try:
                await self._progress_callback({"activity_only": True})
            except Exception:
                pass

    async def discover_sitemap_urls(self, client: httpx.AsyncClient) -> List[str]:
        """
        Dynamically discover recipe sitemap URLs from robots.txt.

        Flow:
        1. Fetch robots.txt to find main sitemap URL
        2. Fetch sitemap index
        3. Find recipe sitemaps (containing 'recipe' in URL)

        Returns:
            List of recipe sitemap URLs
        """
        logger.info("Discovering sitemaps from robots.txt...")

        # Step 1: Get sitemap URL from robots.txt
        try:
            response = await client.get(f"{self.base_url}/robots.txt")
            response.raise_for_status()

            # Find Sitemap: line
            sitemap_match = re.search(r'Sitemap:\s*(\S+)', response.text, re.IGNORECASE)
            if not sitemap_match:
                logger.warning("No Sitemap found in robots.txt, using fallback")
                return self._get_fallback_sitemaps()

            main_sitemap = sitemap_match.group(1)
            logger.info(f"   Found main sitemap: {main_sitemap}")

        except Exception as e:
            logger.warning(f"Error fetching robots.txt: {e}")
            return self._get_fallback_sitemaps()

        # Step 2: Fetch sitemap index
        try:
            response = await client.get(main_sitemap)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

            # Find all sitemap entries containing 'recipe'
            recipe_sitemaps = []
            for sitemap_elem in root.findall("ns:sitemap", ns):
                loc = sitemap_elem.find("ns:loc", ns)
                if loc is not None and 'recipe' in loc.text.lower():
                    recipe_sitemaps.append(loc.text)

            if recipe_sitemaps:
                logger.info(f"   Found {len(recipe_sitemaps)} recipe sitemaps")
                return recipe_sitemaps

            # No recipe-specific sitemaps found
            logger.info("   No recipe sitemaps in index, checking main sitemap")
            return [main_sitemap]

        except Exception as e:
            logger.warning(f"Error parsing sitemap index: {e}")
            return self._get_fallback_sitemaps()

    def _get_fallback_sitemaps(self) -> List[str]:
        """Fallback to known sitemap pattern if dynamic discovery fails."""
        logger.info("   Using fallback sitemap URLs")
        return [
            f"{self.base_url}/sitemap/sv/recipes/{i}.xml"
            for i in range(1, 7)
        ]

    async def get_recipe_urls_from_sitemap(self) -> List[Tuple[str, str]]:
        """
        Fetch all recipe URLs from sitemaps.

        Returns:
            List of (url, lastmod) tuples, excluding pre-made meals ('färdigpreppat')
        """
        logger.info("Fetching recipe URLs from sitemaps...")

        all_recipes = []

        async with httpx.AsyncClient(headers=self.headers, timeout=30, event_hooks={"request": [ssrf_safe_event_hook]}) as client:
            # Dynamically discover sitemaps
            sitemap_urls = await self.discover_sitemap_urls(client)

            for sitemap_url in sitemap_urls:
                try:
                    response = await client.get(sitemap_url)
                    response.raise_for_status()

                    # Parse XML
                    root = ET.fromstring(response.content)
                    ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

                    count = 0
                    for url_elem in root.findall("ns:url", ns):
                        loc = url_elem.find("ns:loc", ns)
                        lastmod = url_elem.find("ns:lastmod", ns)

                        if loc is not None:
                            url = loc.text
                            mod_date = lastmod.text if lastmod is not None else None

                            # Filter out pre-made meals ('fardigpreppat')
                            if "fardigpreppat" not in url.lower():
                                all_recipes.append((url, mod_date))
                                count += 1

                    logger.info(f"   {sitemap_url.split('/')[-1]}: {count} recipes")

                except Exception as e:
                    logger.warning(f"   Error fetching {sitemap_url}: {e}")

        logger.info(f"Total recipe URLs (excl. pre-made meals): {len(all_recipes)}")
        return all_recipes

    async def get_existing_recipes(self) -> Dict[str, datetime]:
        """Get existing Mathem recipes with their scraped_at dates."""
        with get_db_session() as session:
            results = session.query(
                FoundRecipe.url,
                FoundRecipe.scraped_at
            ).filter(
                FoundRecipe.source_name == DB_SOURCE_NAME
            ).all()
            return {r[0]: r[1] for r in results}

    async def scrape_recipe_httpx(
        self,
        client: httpx.AsyncClient,
        url: str
    ) -> Optional[Dict]:
        """
        Scrape a single recipe using httpx (fast, no browser).
        Parses JSON-LD schema from the HTML.
        """
        try:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            page_html = response.text

            recipe = {
                "source_name": DB_SOURCE_NAME,
                "url": url,
                "scraped_at": datetime.now(timezone.utc)
            }

            # Find all JSON-LD scripts (page may have Organization, BreadcrumbList, etc.)
            json_ld_matches = re.findall(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                page_html,
                re.DOTALL
            )

            if not json_ld_matches:
                return None

            # Search all JSON-LD blocks for a Recipe schema
            data = None
            for json_ld_text in json_ld_matches:
                try:
                    parsed = json.loads(json_ld_text)
                except json.JSONDecodeError:
                    continue

                # Handle array of schemas within one block
                if isinstance(parsed, list):
                    found = next((d for d in parsed if isinstance(d, dict) and _is_type(d, "Recipe")), None)
                    if found:
                        data = found
                        break
                elif isinstance(parsed, dict) and _is_type(parsed, "Recipe"):
                    data = parsed
                    break

            if data is None:
                return None

            # Extract fields
            recipe["name"] = html.unescape(data.get("name", "").strip())

            # Image - decode HTML entities in URL (e.g., &amp; -> &)
            img = data.get("image")
            if isinstance(img, list) and img:
                recipe["image_url"] = html.unescape(img[0])
            elif isinstance(img, str):
                recipe["image_url"] = html.unescape(img)

            # Ingredients
            ingredients = data.get("recipeIngredient", [])
            if ingredients:
                recipe["ingredients"] = ingredients

            # Servings
            servings = data.get("recipeYield")
            if servings:
                if isinstance(servings, str):
                    match = re.search(r'(\d+)', servings)
                    if match:
                        recipe["servings"] = int(match.group(1))
                elif isinstance(servings, int):
                    recipe["servings"] = servings

            # Time
            total_time = data.get("totalTime", "")
            recipe["prep_time_minutes"] = parse_iso8601_duration(total_time)

            # Validate: must have name, enough ingredients, and servings
            if not recipe.get("name"):
                return None

            ingredients = recipe.get("ingredients", [])
            if not ingredients or len(ingredients) < MIN_INGREDIENTS:
                logger.debug(f"   Skipping {url}: only {len(ingredients) if ingredients else 0} ingredients (min {MIN_INGREDIENTS})")
                return None

            # Filter out product bundles (office supplies, cleaning kits, etc.)
            all_ingredients_lower = ' '.join(ingredients).lower()
            for keyword in NON_FOOD_INGREDIENTS:
                if keyword in all_ingredients_lower:
                    logger.info(f"   Skipping non-recipe bundle: {recipe['name']} (ingredient: {keyword})")
                    return None

            return recipe

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.debug(f"403 Forbidden: {url}")
            return None
        except Exception as e:
            logger.debug(f"Error scraping {url}: {e}")
            return None

    async def scrape_recipes_concurrent(
        self,
        urls: List[str],
        max_concurrent: int = 5,
        stream_saver: Optional[StreamingRecipeSaver] = None,
        max_recipes: Optional[int] = None,
        record_discovery: bool = False,
    ) -> List[Dict]:
        """
        Scrape multiple recipes concurrently with httpx.
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        recipes = []
        failed_count = 0
        self._discovery_recorded_non_recipe = 0

        async def scrape_with_semaphore(client: httpx.AsyncClient, url: str):
            nonlocal failed_count
            async with semaphore:
                result = await self.scrape_recipe_httpx(client, url)
                if result is None:
                    failed_count += 1
                await self._report_activity()
                return result

        async with httpx.AsyncClient(
            headers=self.headers,
            timeout=30,
            follow_redirects=True,
            event_hooks={"request": [ssrf_safe_event_hook]}
        ) as client:
            # Process in batches for progress logging
            batch_size = 10
            for i in range(0, len(urls), batch_size):
                if recipe_target_reached(
                    max_recipes=max_recipes,
                    recipes=recipes,
                    stream_saver=stream_saver,
                ):
                    break
                batch = urls[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(urls) + batch_size - 1) // batch_size

                logger.info(f"   Batch {batch_num}/{total_batches}: scraping {len(batch)} recipes...")

                tasks = [scrape_with_semaphore(client, url) for url in batch]
                results = await asyncio.gather(*tasks)

                for url, recipe in zip(batch, results):
                    if recipe:
                        if stream_saver:
                            before_seen = stream_saver.seen_count
                            await stream_saver.add(recipe)
                            saved_recipe = stream_saver.seen_count > before_seen
                        else:
                            recipes.append(recipe)
                            saved_recipe = True
                        if saved_recipe and record_discovery:
                            await asyncio.to_thread(
                                record_recipe_url,
                                source_name=DB_SOURCE_NAME,
                                url=url,
                            )
                            final_url = recipe.get("url")
                            if final_url and final_url != url:
                                await asyncio.to_thread(
                                    record_recipe_url,
                                    source_name=DB_SOURCE_NAME,
                                    url=final_url,
                                )
                        if recipe_target_reached(
                            max_recipes=max_recipes,
                            recipes=recipes,
                            stream_saver=stream_saver,
                        ):
                            break
                    elif record_discovery:
                        await asyncio.to_thread(
                            record_non_recipe_url,
                            source_name=DB_SOURCE_NAME,
                            url=url,
                            reason="parse_error",
                        )
                        self._discovery_recorded_non_recipe += 1

                # Report progress for GUI
                progress = min(i + batch_size, len(urls))
                found_count = stream_saver.seen_count if stream_saver else len(recipes)
                await self._report_progress(progress, len(urls), found_count)

                # Delay between batches to be nice
                if i + batch_size < len(urls):
                    await asyncio.sleep(1.0)

        if failed_count > 0:
            logger.info(f"   ({failed_count} recipes failed/skipped)")
        if record_discovery:
            logger.info(f"   URL discovery: recorded_non_recipe={self._discovery_recorded_non_recipe}")

        return recipes

    def save_recipes(self, recipes: List[Dict], overwrite: bool = False) -> Dict:
        """Save recipes to database."""
        from scrapers.recipes._common import save_recipes_to_database
        return save_recipes_to_database(recipes, DB_SOURCE_NAME, clear_old=overwrite)

    async def scrape_all_recipes(
        self,
        max_recipes: Optional[int] = None,
        force_all: bool = False,
        stream_saver: Optional[StreamingRecipeSaver] = None,
    ) -> RecipeScrapeResult:
        """
        Main scraping method (matches interface expected by GUI).

        Args:
            max_recipes: Limit number of recipes (for test mode)
            force_all: If True, scrape all recipes (for overwrite mode)

        Returns:
            RecipeScrapeResult with scraped recipe dicts
        """
        logger.info(f"\n{'='*60}")
        logger.info("MATHEM RECIPE SCRAPER (FAST)")
        logger.info(f"{'='*60}\n")

        # Get all URLs from sitemap
        all_urls_with_dates = await self.get_recipe_urls_from_sitemap()
        # Sort by lastmod descending (newest first) for incremental priority
        all_urls_with_dates.sort(key=lambda x: x[1] or "1970-01-01", reverse=True)
        all_urls = [url for url, _ in all_urls_with_dates]

        if not all_urls:
            logger.warning("No recipe URLs found in sitemap!")
            return make_recipe_scrape_result(
                [],
                force_all=force_all,
                max_recipes=max_recipes,
                failed=True,
                reason="no_recipe_urls",
            )

        if force_all:
            # Full mode - scrape everything
            urls_to_scrape = all_urls[:max_recipes] if max_recipes else all_urls
            logger.info(f"FULL MODE: Scraping {len(urls_to_scrape)} recipes")
        else:
            # Incremental mode - only new recipes
            existing = await self.get_existing_recipes()
            record_discovery = bool(stream_saver is not None)

            attempt_limit = incremental_attempt_limit(
                max_recipes=max_recipes,
                available_count=len(all_urls),
                default_limit=len(all_urls),
            )
            if record_discovery:
                urls_to_scrape, discovery_stats = select_urls_for_scrape(
                    source_name=DB_SOURCE_NAME,
                    candidate_urls=all_urls,
                    max_http_attempts=attempt_limit,
                )
                logger.info(f"   URL discovery prefilter: {discovery_stats.format_log_suffix()}")
            else:
                urls_to_scrape = [url for url in all_urls if url not in existing]
                urls_to_scrape = urls_to_scrape[:attempt_limit]

            logger.info(
                f"INCREMENTAL MODE: {len(urls_to_scrape)} new recipes to scrape "
                f"(target {max_recipes or 'auto'})"
            )

            if not urls_to_scrape:
                logger.info("   No new recipes found!")
                return make_recipe_scrape_result(
                    [],
                    force_all=force_all,
                    max_recipes=max_recipes,
                    reason="no_new_recipes",
                )

        recipes = await self.scrape_recipes_concurrent(
            urls_to_scrape,
            stream_saver=stream_saver,
            max_recipes=max_recipes,
            record_discovery=bool(stream_saver is not None and not force_all),
        )
        found_count = stream_saver.seen_count if stream_saver else len(recipes)
        logger.info(f"\nScraped {found_count} recipes successfully")

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
        """
        Scrape and save in one operation (for GUI full mode).

        Returns:
            Stats dict with created/updated counts
        """
        saver = StreamingRecipeSaver(
            DB_SOURCE_NAME,
            overwrite=overwrite,
            max_recipes=max_recipes,
        )
        result = await self.scrape_all_recipes(
            force_all=overwrite,
            max_recipes=max_recipes,
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

    async def run(self, mode: str = "incremental", test_limit: int = 20) -> Dict:
        """
        Main entry point.

        Args:
            mode: "incremental", "overwrite", or "test"
            test_limit: Number of recipes for test mode
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"MATHEM RECIPE SCRAPER (FAST) - Mode: {mode.upper()}")
        logger.info(f"{'='*60}\n")

        # Get all URLs from sitemap
        all_urls_with_dates = await self.get_recipe_urls_from_sitemap()
        all_urls = [url for url, _ in all_urls_with_dates]

        if mode == "test":
            logger.info(f"TEST MODE: Scraping {test_limit} recipes, not saving")
            urls_to_scrape = all_urls[:test_limit]

            recipes = await self.scrape_recipes_concurrent(urls_to_scrape)

            logger.info(f"\n{'='*60}")
            logger.info(f"TEST COMPLETE: {len(recipes)} recipes scraped")
            logger.info(f"{'='*60}")

            for recipe in recipes[:3]:
                logger.info(f"\n  {recipe['name']}")
                logger.info(f"    Time: {recipe.get('prep_time_minutes', 'N/A')} min")
                logger.info(f"    Ingredients: {len(recipe.get('ingredients', []))} items")

            return {"scraped": len(recipes), "saved": 0, "mode": "test"}

        elif mode == "overwrite":
            logger.info(f"OVERWRITE MODE: Full resync of {len(all_urls)} recipes")

            recipes = await self.scrape_recipes_concurrent(all_urls)

            logger.info(f"\nSaving {len(recipes)} recipes to database...")
            stats = self.save_recipes(recipes, overwrite=True)

            logger.info(f"\n{'='*60}")
            logger.info("OVERWRITE COMPLETE")
            logger.info(f"  Created: {stats['created']}")
            logger.info(f"  Skipped: {stats['skipped']}")
            logger.info(f"{'='*60}")

            return {**stats, "mode": "overwrite"}

        else:
            # Incremental mode
            logger.info("INCREMENTAL MODE: Finding new recipes...")

            existing = await self.get_existing_recipes()
            logger.info(f"   Existing in database: {len(existing)}")

            # Find new URLs (not in database)
            new_urls = [url for url in all_urls if url not in existing]
            logger.info(f"   New recipes to scrape: {len(new_urls)}")

            if not new_urls:
                logger.info("\n   No new recipes found!")
                return {"created": 0, "updated": 0, "mode": "incremental"}

            recipes = await self.scrape_recipes_concurrent(new_urls)

            logger.info(f"\nSaving {len(recipes)} recipes to database...")
            stats = self.save_recipes(recipes, overwrite=False)

            logger.info(f"\n{'='*60}")
            logger.info("INCREMENTAL COMPLETE")
            logger.info(f"  Created: {stats['created']}")
            logger.info(f"  Updated: {stats['updated']}")
            logger.info(f"  Skipped: {stats['skipped']}")
            logger.info(f"{'='*60}")

            return {**stats, "mode": "incremental"}


# Module-level function for GUI compatibility
def save_to_database(recipes: List[Dict], clear_old: bool = False) -> Dict:
    """Save recipes to database."""
    from scrapers.recipes._common import save_recipes_to_database
    return save_recipes_to_database(recipes, DB_SOURCE_NAME, clear_old=clear_old)


# Three Run Modes (per RECIPE_TEMPLATE.md)
async def test_scrape():
    """Test mode: 20 recipes, no database save."""
    logger.info("\n" + "="*60)
    logger.info("MATHEM SCRAPER - TEST MODE (20 recipes, no DB save)")
    logger.info("="*60 + "\n")

    scraper = MathemScraper()
    recipes = await scraper.scrape_all_recipes(max_recipes=20)

    logger.info(f"\n{'='*60}")
    logger.info(f"TEST COMPLETE: {len(recipes)} recipes scraped")
    logger.info("="*60)

    # Show sample recipes
    for recipe in recipes[:3]:
        logger.info(f"\n  {recipe['name']}")
        logger.info(f"    Time: {recipe.get('prep_time_minutes', 'N/A')} min")
        logger.info(f"    Ingredients: {len(recipe.get('ingredients', []))} items")

    return {"scraped": len(recipes), "saved": 0, "mode": "test"}


async def full_scrape():
    """Incremental mode: Only scrape NEW recipes (default)."""
    logger.info("\n" + "="*60)
    logger.info("MATHEM SCRAPER - INCREMENTAL MODE (new recipes only)")
    logger.info("="*60 + "\n")

    scraper = MathemScraper()
    recipes = await scraper.scrape_all_recipes(force_all=False)

    if not recipes:
        logger.info("No new recipes to save!")
        return {"created": 0, "updated": 0, "skipped": 0, "mode": "incremental"}

    logger.info(f"\nSaving {len(recipes)} recipes to database...")
    stats = scraper.save_recipes(recipes, overwrite=False)

    logger.info(f"\n{'='*60}")
    logger.info("INCREMENTAL COMPLETE")
    logger.info(f"  Created: {stats['created']}")
    logger.info(f"  Updated: {stats['updated']}")
    logger.info(f"  Skipped: {stats['skipped']}")
    logger.info("="*60)

    return {**stats, "mode": "incremental"}


async def overwrite_scrape():
    """Overwrite mode: Clear all old data, scrape everything."""
    logger.info("\n" + "="*60)
    logger.info("MATHEM SCRAPER - OVERWRITE MODE (clear + full rescrape)")
    logger.info("="*60 + "\n")

    scraper = MathemScraper()
    recipes = await scraper.scrape_all_recipes(force_all=True)

    if not recipes:
        logger.warning("No recipes scraped!")
        return {"created": 0, "updated": 0, "skipped": 0, "mode": "overwrite"}

    logger.info(f"\nSaving {len(recipes)} recipes to database (clearing old first)...")
    stats = scraper.save_recipes(recipes, overwrite=True)

    logger.info(f"\n{'='*60}")
    logger.info("OVERWRITE COMPLETE")
    logger.info(f"  Created: {stats['created']}")
    logger.info(f"  Skipped: {stats['skipped']}")
    logger.info("="*60)

    return {**stats, "mode": "overwrite"}


# CLI interface (per RECIPE_TEMPLATE.md)
if __name__ == "__main__":
    if len(sys.argv) > 1:
        mode = sys.argv[1]

        if mode == "--test":
            asyncio.run(test_scrape())

        elif mode == "--overwrite":
            asyncio.run(overwrite_scrape())

        else:
            print(f"Unknown argument: {mode}")
            print("\nUsage:")
            print("  python mathem_scraper.py              # Incremental sync (default)")
            print("  python mathem_scraper.py --test       # Test mode (20 recipes, no DB)")
            print("  python mathem_scraper.py --overwrite  # Full overwrite (clear + rescrape)")
            sys.exit(1)

    else:
        asyncio.run(full_scrape())
