"""
Jävligt Gott Recipe Scraper

Scrapes vegetarian/vegan recipes from Javligtgott.se.
Uses sitemap for URL discovery and httpx for fetching.
Custom HTML parsing (no JSON-LD Recipe schema available).

STRATEGY:
1. Fetch recipe URLs from recept-sitemap.xml
2. Scrape each page with httpx (server-side rendered, no JS needed)
3. Parse ingredients from HTML tables, title from og:title, image from og:image
4. Gentle: 2s delay between requests, max 2 concurrent

SITE STRUCTURE:
- Ingredients in <table> rows: <td>Name</td><td>Quantity Unit</td>
- Sub-sections (avgränsare) as <h3> headings between tables
- Servings in <span id="recipe_portions">
- No prep_time/cook_time in structured form
"""

import httpx
from loguru import logger
from utils.security import ssrf_safe_event_hook
from typing import List, Dict, Optional, Tuple
import asyncio
import re
import os
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

# Add app directory to path
app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, app_dir)

from database import get_db_session
from scrapers.recipes._common import (
    RecipeScrapeResult, incremental_attempt_limit, make_recipe_scrape_result,
    recipe_target_reached, split_serving_lists, validate_image_url,
    StreamingRecipeSaver
)
from scrapers.recipes.url_discovery_cache import (
    record_non_recipe_url,
    record_recipe_url,
    select_urls_for_scrape,
)

# GUI Metadata
SCRAPER_NAME = "Javligtgott.se"
DB_SOURCE_NAME = "Javligtgott.se"
SCRAPER_DESCRIPTION = "Vegetariska recept från Javligtgott.se"
EXPECTED_RECIPE_COUNT = 500
SOURCE_URL = "https://Javligtgott.se/recept/"

# Scraper config
MAX_RECIPES = 600  # Take all available (~500)
REQUEST_DELAY = 2.0  # Be gentle — hobby site
CONCURRENT_REQUESTS = 2
MIN_INGREDIENTS = 3

SITEMAP_URL = "https://Javligtgott.se/recept-sitemap.xml"


class JavligtGottScraper:
    """Scraper for Javligtgott.se recipes using sitemap + HTML parsing."""

    def __init__(self):
        self.base_url = "https://Javligtgott.se"
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
        """Fetch all recipe URLs from the sitemap.

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
                    # Skip the listing page itself
                    if url.rstrip('/').endswith('/recept'):
                        continue
                    mod_date = lastmod.text.strip() if lastmod is not None else "1970-01-01"
                    all_urls.append((url, mod_date))

            logger.info(f"   Found {len(all_urls)} recipe URLs in sitemap")

        except Exception as e:
            logger.error(f"Error fetching sitemap: {e}")

        all_urls.sort(key=lambda x: x[1], reverse=True)
        return all_urls

    # ========== HTML PARSING ==========

    def _parse_recipe_html(self, html: str, url: str) -> Optional[Dict]:
        """Parse recipe data from HTML page.

        Extracts:
        - Title from og:title meta tag
        - Image from og:image meta tag
        - Servings from <span id="recipe_portions">
        - Ingredients from <table> rows in the Ingredienser section
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

            # Image from og:image
            image_match = re.search(
                r'<meta\s+property="og:image"\s+content="([^"]+)"', html
            )
            image_url = image_match.group(1).strip() if image_match else None

            # Servings from <span id="recipe_portions">
            servings = None
            servings_match = re.search(
                r'<span[^>]*id="recipe_portions"[^>]*>\s*(\d+)\s*</span>', html
            )
            if servings_match:
                servings = int(servings_match.group(1))

            # Extract ingredient section (between "Ingredienser" and "Gör så här")
            ingr_section = self._extract_ingredient_section(html)
            if not ingr_section:
                logger.debug(f"   No ingredient section found: {url}")
                return None

            ingredients = self._parse_ingredients(ingr_section)

            if len(ingredients) < MIN_INGREDIENTS:
                logger.debug(f"   Skipping {name}: only {len(ingredients)} ingredients")
                return None

            # Split serving lists
            ingredients = split_serving_lists(ingredients)

            return {
                "source_name": DB_SOURCE_NAME,
                "name": name,
                "ingredients": ingredients,
                "prep_time_minutes": None,
                "servings": servings,
                "image_url": image_url,
                "url": url,
                "scraped_at": datetime.now(timezone.utc),
            }

        except Exception as e:
            logger.debug(f"Error parsing recipe HTML for {url}: {e}")
            return None

    def _extract_ingredient_section(self, html: str) -> Optional[str]:
        """Extract the HTML between Ingredienser heading and Gör så här heading."""
        # Find the ingredient section marker
        start_match = re.search(
            r'<h2[^>]*>Ingredienser</h2>',
            html, re.IGNORECASE
        )
        if not start_match:
            return None

        # Find where instructions start
        end_match = re.search(
            r'<h2[^>]*>Gör så här</h2>',
            html[start_match.end():], re.IGNORECASE
        )
        if end_match:
            return html[start_match.end():start_match.end() + end_match.start()]

        # Fallback: take a large chunk after Ingredienser
        return html[start_match.end():start_match.end() + 10000]

    def _parse_ingredients(self, section_html: str) -> List[str]:
        """Parse ingredient table rows from the ingredient section HTML.

        Each ingredient is in a <tr> with two <td>s:
        - First <td>: ingredient name (may contain tooltip spans)
        - Second <td>: quantity + unit (in <span class="quantity_calculate"> + text)

        Sub-section headers (avgränsare) are in <h3> tags — these are skipped.
        """
        ingredients = []

        # Find all table rows
        rows = re.findall(r'<tr>(.*?)</tr>', section_html, re.DOTALL)

        for row in rows:
            # Extract cells
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            if len(cells) < 2:
                continue

            # First cell: ingredient name (strip HTML tags, tooltips, whitespace)
            name_html = cells[0]
            # Remove tooltip commentary entirely. Javligt Gott nests the
            # visible icon and the actual prose inside the same tooltip span,
            # so strip the inner tooltiptext first before removing outer tags.
            name_html = re.sub(r'<span class="tooltiptext">.*?</span>', '', name_html, flags=re.DOTALL)
            name = _strip_html(name_html).strip()
            if not name:
                continue

            # Second cell: quantity + unit
            qty_html = cells[1]

            # Extract quantity from quantity_calculate span
            qty_match = re.search(
                r'<span class="quantity_calculate">\s*([\d.]+)\s*</span>',
                qty_html
            )

            # Extract unit (text after the quantity span, inside <strong>)
            unit = ""
            if qty_match:
                # Get everything after the closing </span> but inside <strong>
                after_span = qty_html[qty_match.end():]
                unit_text = _strip_html(after_span).strip()
                unit = unit_text
            else:
                # No quantity_calculate — might be "Efter smak" or similar
                unit_text = _strip_html(qty_html).strip()
                unit = unit_text

            # Build ingredient string: "300 g Chêvre" or "Olivolja"
            if qty_match:
                qty = qty_match.group(1)
                # Clean up quantity: "1.0" -> "1", "1.5" -> "1.5"
                if qty.endswith('.0'):
                    qty = qty[:-2]
                if unit:
                    ingredient_str = f"{qty} {unit} {name}"
                else:
                    ingredient_str = f"{qty} {name}"
            elif unit and unit.lower() != name.lower():
                # No numeric quantity but has text like "Efter smak"
                ingredient_str = f"{name} ({unit})" if unit not in ('', name) else name
            else:
                ingredient_str = name

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

            # Scrape recipes sequentially with delay
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


def _strip_html(text: str) -> str:
    """Remove all HTML tags from a string and collapse whitespace."""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)  # collapse newlines/tabs/multiple spaces
    return text


def save_to_database(recipes: List[Dict], clear_old: bool = False) -> Dict[str, int]:
    """Save recipes to database (module-level function for GUI compatibility)."""
    from scrapers.recipes._common import save_recipes_to_database
    return save_recipes_to_database(recipes, DB_SOURCE_NAME, clear_old=clear_old)


async def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Jävligt Gott Recipe Scraper")
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
        print("TEST: Jävligt Gott (3 recipes)")
    elif args.overwrite:
        print("OVERWRITE: Jävligt Gott")
    else:
        print("INCREMENTAL: Jävligt Gott")
    print("=" * 60 + "\n")

    scraper = JavligtGottScraper()

    if args.test:
        recipes = await scraper.scrape_all_recipes(max_recipes=3)
        print(f"\nTEST: Scraped {len(recipes)} recipes (not saved)")
        for r in recipes:
            print(f"\n--- {r['name']} ---")
            print(f"URL: {r['url']}")
            print(f"Image: {r['image_url']}")
            print(f"Servings: {r['servings']}")
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
