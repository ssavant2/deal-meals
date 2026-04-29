"""
Undertian.com Recipe Scraper - FAST VERSION using Sitemap + httpx

Scrapes budget vegetarian/vegan recipes from Undertian.com (Portionen Under Tian).
Uses WordPress sitemap for URL discovery and httpx for fetching.
Custom parsing: ingredients from window.recipeSettings JS object, prep time from HTML.

STRATEGY:
1. Fetch recipe URLs from wp-sitemap-posts-recept-1.xml
2. Scrape each page with httpx (server-side rendered, no JS needed)
3. Parse ingredients from window.recipeSettings JS object
4. Extract prep time from HTML time indicator
5. Gentle: 2s delay between requests, max 2 concurrent (hobby site)

SITE STRUCTURE:
- Ingredients in window.recipeSettings JS object with {amount, unit, type, alternative}
- Ingredient sections via part_name (e.g., "Pizzadeg", "Topping")
- Servings from recipeSettings.multiplier + recipeSettings.unit
- Prep time as "X min" text near clock icon in HTML
- Title from og:title, image from og:image
"""

import httpx
from loguru import logger
from utils.security import ssrf_safe_event_hook
from typing import List, Dict, Optional, Tuple
import asyncio
import re
import json
import os
import sys
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

# Add app directory to path
app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, app_dir)

from database import get_db_session
from scrapers.recipes._common import (
    RecipeScrapeResult, incremental_attempt_limit, make_recipe_scrape_result,
    recipe_target_reached, split_serving_lists, StreamingRecipeSaver
)
from scrapers.recipes.url_discovery_cache import (
    record_non_recipe_url,
    record_recipe_url,
    select_urls_for_scrape,
)

# GUI Metadata
SCRAPER_NAME = "Undertian.com"
DB_SOURCE_NAME = "Undertian.com"
SCRAPER_DESCRIPTION = "Vegetariska budgetrecept från Undertian.com"
EXPECTED_RECIPE_COUNT = 400  # Current WordPress recipe sitemap count
SOURCE_URL = "https://undertian.com"

# Scraper config
MAX_RECIPES = 400  # Take all recipes currently exposed by the recipe sitemap
REQUEST_DELAY = 2.0  # Be gentle — hobby site
CONCURRENT_REQUESTS = 2
MIN_INGREDIENTS = 2

SITEMAP_URL = "https://undertian.com/wp-sitemap-posts-recept-1.xml"

# Regex to extract the recipeSettings JS object from HTML
_RECIPE_SETTINGS_RE = re.compile(
    r'window\.recipeSettings\s*=\s*(\{.*?\})\s*;?\s*</script>',
    re.DOTALL
)

# Regex to extract prep time from HTML (e.g., "60 min" near a time icon)
_PREP_TIME_RE = re.compile(
    r'<span[^>]*>\s*(\d+)\s*min\s*</span>',
    re.IGNORECASE
)


class UndertianScraper:
    """Scraper for Undertian.com recipes using sitemap + JS object parsing."""

    def __init__(self):
        self.base_url = "https://undertian.com"
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
        """Fetch all recipe URLs from the WordPress sitemap.

        Returns:
            List of (url, lastmod) tuples, sorted by lastmod descending.
        """
        logger.info("Fetching recipe URLs from sitemap...")
        all_urls = []

        try:
            response = await client.get(SITEMAP_URL, follow_redirects=True)
            response.raise_for_status()

            root = ET.fromstring(response.text)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

            for url_elem in root.findall(".//sm:url", ns):
                loc = url_elem.find("sm:loc", ns)
                lastmod = url_elem.find("sm:lastmod", ns)

                if loc is not None:
                    url = loc.text.strip()
                    mod_date = lastmod.text.strip() if lastmod is not None else "1970-01-01"
                    all_urls.append((url, mod_date))

            logger.info(f"   Found {len(all_urls)} recipe URLs in sitemap")

        except Exception as e:
            logger.error(f"Error fetching sitemap: {e}")

        all_urls.sort(key=lambda x: x[1], reverse=True)
        return all_urls

    # ========== RECIPE PARSING ==========

    def _parse_recipe_html(self, html: str, url: str) -> Optional[Dict]:
        """Parse recipe data from HTML page.

        Extracts:
        - Title from og:title meta tag
        - Image from og:image meta tag
        - Ingredients from window.recipeSettings JS object
        - Prep time from HTML time span
        - Servings from recipeSettings.multiplier
        """
        try:
            # Title from og:title
            title_match = re.search(
                r'<meta\s+property="og:title"\s+content="([^"]+)"', html
            )
            if not title_match:
                logger.debug(f"   No og:title found: {url}")
                return None
            name = _unescape_html(title_match.group(1).strip())
            # Remove site suffix if present (e.g., "Recept - Undertian")
            name = re.sub(r'\s*[-–|]\s*Undertian.*$', '', name, flags=re.IGNORECASE).strip()

            # Image from og:image
            image_match = re.search(
                r'<meta\s+property="og:image"\s+content="([^"]+)"', html
            )
            image_url = image_match.group(1).strip() if image_match else None

            # Parse recipeSettings JS object
            settings_match = _RECIPE_SETTINGS_RE.search(html)
            if not settings_match:
                logger.debug(f"   No recipeSettings found: {url}")
                return None

            try:
                raw_js = settings_match.group(1)
                # Convert JS object to valid JSON: unquoted keys → quoted keys
                # e.g., ingredients: → "ingredients":, part_name: → "part_name":
                raw_json = re.sub(r'(?<=[{,\n])\s*(\w+)\s*:', r' "\1":', raw_js)
                settings = json.loads(raw_json)
            except (json.JSONDecodeError, ValueError) as e:
                logger.debug(f"   Invalid recipeSettings JSON: {url} ({e})")
                return None

            # Extract servings
            servings = None
            multiplier = settings.get('multiplier')
            if multiplier:
                try:
                    servings = int(float(multiplier))
                except (ValueError, TypeError):
                    pass

            # Extract ingredients
            ingredients = self._parse_ingredients(settings.get('ingredients', []))

            if len(ingredients) < MIN_INGREDIENTS:
                logger.debug(f"   Skipping {name}: only {len(ingredients)} ingredients")
                return None

            # Split serving lists (shared utility)
            ingredients = split_serving_lists(ingredients)

            # Prep time from HTML
            prep_time = None
            time_match = _PREP_TIME_RE.search(html)
            if time_match:
                prep_time = int(time_match.group(1))

            return {
                "source_name": DB_SOURCE_NAME,
                "name": name,
                "ingredients": ingredients,
                "prep_time_minutes": prep_time,
                "servings": servings,
                "image_url": image_url,
                "url": url,
                "scraped_at": datetime.now(timezone.utc),
            }

        except Exception as e:
            logger.debug(f"Error parsing recipe HTML for {url}: {e}")
            return None

    def _parse_ingredients(self, ingredient_sections: list) -> List[str]:
        """Parse ingredients from recipeSettings.ingredients structure.

        Each section has:
        - part_name: section name (e.g., "Pizzadeg", "" for main)
        - part: list of {amount, unit, type, alternative}

        Ingredients with alternative=True are alternatives to the previous
        ingredient and are prefixed with "alternativt".
        """
        ingredients = []

        for section in ingredient_sections:
            for item in section.get('part', []):
                amount = str(item.get('amount', '')).strip()
                unit = str(item.get('unit', '')).strip()
                ing_type = str(item.get('type', '')).strip()
                is_alternative = item.get('alternative', False)

                if not ing_type:
                    continue

                # Build ingredient string
                parts = []
                if amount and amount != '0':
                    # Clean: "1.0" → "1", "1.5" stays
                    try:
                        num = float(amount)
                        if num == int(num):
                            amount = str(int(num))
                    except ValueError:
                        pass
                    parts.append(amount)
                if unit:
                    parts.append(unit)
                parts.append(ing_type)

                ingredient_str = ' '.join(parts)

                # Mark alternatives clearly — these are NOT separate ingredients
                # but substitutions for the previous line
                if is_alternative:
                    ingredient_str = f"alternativt {ingredient_str}"

                ingredients.append(ingredient_str)

        return ingredients

    # ========== RECIPE SCRAPING ==========

    async def scrape_recipe(self, client: httpx.AsyncClient, url: str) -> Optional[Dict]:
        """Scrape a single recipe page."""
        try:
            response = await client.get(url, follow_redirects=True)

            if response.status_code in (403, 404):
                logger.debug(f"   HTTP {response.status_code}: {url}")
                return None

            response.raise_for_status()
            return self._parse_recipe_html(response.text, url)

        except httpx.TimeoutException:
            logger.warning(f"   Timeout: {url}")
            return None
        except Exception as e:
            logger.debug(f"   Error scraping {url}: {e}")
            return None

    async def scrape_all_recipes(
        self,
        max_recipes: Optional[int] = None,
        batch_size: int = 10,
        force_all: bool = False,
        stream_saver: Optional[StreamingRecipeSaver] = None,
    ) -> RecipeScrapeResult:
        """Main scraping method (GUI-compatible interface).

        Args:
            max_recipes: Limit number of recipes (for test mode, e.g., 20)
            batch_size: Not used (kept for interface compatibility)
            force_all: If True, scrape all recipes ignoring existing

        Returns:
            RecipeScrapeResult with scraped recipe dicts
        """
        self._cancel_flag = False

        async with httpx.AsyncClient(
            headers=self.headers,
            timeout=30.0,
            follow_redirects=True,
            event_hooks={"request": [ssrf_safe_event_hook]},
        ) as client:

            # Get all URLs from sitemap
            all_urls = await self.get_all_recipe_urls(client)

            if not all_urls:
                logger.error("No recipe URLs found in sitemap!")
                return make_recipe_scrape_result(
                    [],
                    force_all=force_all,
                    max_recipes=max_recipes,
                    failed=True,
                    reason="no_recipe_urls",
                )

            # Determine which URLs to scrape
            record_discovery = bool(stream_saver is not None and not force_all)
            if force_all:
                candidate_urls = [url for url, _ in all_urls[:max_recipes or MAX_RECIPES]]
                urls_to_scrape = candidate_urls
                logger.info(f"OVERWRITE MODE: Scraping {len(urls_to_scrape)} recipes")
            else:
                # Incremental: skip already-saved URLs
                existing_urls = self._get_existing_urls()
                all_candidate_urls = [url for url, _ in all_urls]
                if max_recipes:
                    attempt_limit = incremental_attempt_limit(
                        max_recipes=max_recipes,
                        available_count=len(all_candidate_urls),
                        default_limit=MAX_RECIPES,
                    )
                    if record_discovery:
                        urls_to_scrape, discovery_stats = select_urls_for_scrape(
                            source_name=DB_SOURCE_NAME,
                            candidate_urls=all_candidate_urls,
                            max_http_attempts=attempt_limit,
                        )
                        logger.info(f"   URL discovery prefilter: {discovery_stats.format_log_suffix()}")
                    else:
                        new_candidate_urls = [
                            url for url in all_candidate_urls if url not in existing_urls
                        ]
                        urls_to_scrape = new_candidate_urls[:attempt_limit]
                else:
                    if record_discovery:
                        urls_to_scrape, discovery_stats = select_urls_for_scrape(
                            source_name=DB_SOURCE_NAME,
                            candidate_urls=all_candidate_urls,
                            max_http_attempts=MAX_RECIPES,
                        )
                        logger.info(f"   URL discovery prefilter: {discovery_stats.format_log_suffix()}")
                    else:
                        candidate_urls = all_candidate_urls[:MAX_RECIPES]
                        urls_to_scrape = [
                            url for url in candidate_urls if url not in existing_urls
                        ]

                logger.info(
                    f"INCREMENTAL: {len(urls_to_scrape)} new recipes to scrape "
                    f"(target {max_recipes or 'auto'})"
                )

                if not urls_to_scrape:
                    logger.info("Already up to date!")
                    return make_recipe_scrape_result(
                        [],
                        force_all=force_all,
                        max_recipes=max_recipes,
                        reason="no_new_recipes",
                    )

            # Scrape recipes sequentially with delay (gentle on hobby site)
            recipes = []
            total = len(urls_to_scrape)
            self._discovery_recorded_non_recipe = 0

            logger.info(f"Scraping {total} recipes...")
            await self._report_progress(f"Fetching {total} recipes...", 0, total, 0)

            for i, url in enumerate(urls_to_scrape):
                if self._cancel_flag:
                    logger.info("Scraping cancelled")
                    break

                recipe = await self.scrape_recipe(client, url)
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
                await self._report_activity()

                if (i + 1) % 10 == 0 or (i + 1) == total:
                    found_count = stream_saver.seen_count if stream_saver else len(recipes)
                    logger.info(f"   Progress: {i + 1}/{total} ({found_count} recipes found)")
                    await self._report_progress(
                        f"Fetched {found_count} recipes...",
                        i + 1, total, found_count,
                    )

                await asyncio.sleep(REQUEST_DELAY)

            found_count = stream_saver.seen_count if stream_saver else len(recipes)
            logger.info(f"Scraped {found_count} recipes")
            if record_discovery:
                logger.info(f"   URL discovery: recorded_non_recipe={self._discovery_recorded_non_recipe}")
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

    # ========== DATABASE OPERATIONS ==========

    def _get_existing_urls(self) -> set:
        """Get all existing recipe URLs from database."""
        with get_db_session() as db:
            from sqlalchemy import text
            result = db.execute(
                text("SELECT url FROM found_recipes WHERE source_name = :source"),
                {"source": DB_SOURCE_NAME},
            )
            return {row.url for row in result}


# ========== MODULE-LEVEL HELPERS ==========

def _unescape_html(text: str) -> str:
    """Decode HTML entities."""
    import html as html_module
    return html_module.unescape(text) if text else text


def save_to_database(recipes: List[Dict], clear_old: bool = False) -> Dict[str, int]:
    """Save recipes to database (module-level function for GUI compatibility)."""
    from scrapers.recipes._common import save_recipes_to_database
    return save_recipes_to_database(recipes, DB_SOURCE_NAME, clear_old=clear_old)


async def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Undertian.com Recipe Scraper")
    parser.add_argument("--test", action="store_true", help="Test mode: scrape 3 recipes, don't save")
    parser.add_argument("--overwrite", action="store_true", help="Delete existing and scrape fresh")
    args = parser.parse_args()

    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )

    print("\n" + "=" * 60)
    if args.test:
        print("TEST: Undertian.com (3 recipes)")
    elif args.overwrite:
        print("OVERWRITE: Undertian.com")
    else:
        print("INCREMENTAL: Undertian.com")
    print("=" * 60 + "\n")

    scraper = UndertianScraper()

    if args.test:
        recipes = await scraper.scrape_all_recipes(max_recipes=3)
        print(f"\nTEST: Scraped {len(recipes)} recipes (not saved)")
        for r in recipes:
            print(f"\n--- {r['name']} ---")
            print(f"URL: {r['url']}")
            print(f"Image: {r['image_url']}")
            print(f"Servings: {r['servings']}")
            print(f"Prep time: {r['prep_time_minutes']} min")
            print(f"Ingredients ({len(r['ingredients'])}):")
            for ing in r['ingredients']:
                print(f"   - {ing}")
    else:
        recipes = await scraper.scrape_all_recipes(force_all=args.overwrite)

        if recipes:
            stats = save_to_database(recipes, clear_old=args.overwrite)
            print(f"\nDone! Created: {stats['created']}, Updated: {stats['updated']}")
        else:
            print("\nAlready up to date")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
