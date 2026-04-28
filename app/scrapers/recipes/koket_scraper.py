"""
Köket.se Recipe Scraper - Top 1000 by lastmod

DESCRIPTION:
Scrapes Swedish recipes from Köket.se using their sitemap.
Sorts by lastmod date and takes the top 1000 most recently updated recipes.

STRATEGY:
1. Fetch sitemap.xml (~39,000 URLs)
2. Filter out non-recipe URLs (/mat/, /tv-program/, etc.)
3. Sort by lastmod date (most recent first)
4. Take top 1000
5. Scrape JSON-LD Recipe schema from each page

FEATURES:
- Sitemap-based URL discovery with lastmod dates
- Top 1000 by recency = likely popular/maintained recipes
- JSON-LD parsing for structured data
- Single worker with 1s delay (gentle to avoid rate limiting)

RUN MODES (GUI-compatible interface):
1. DEFAULT: Incremental sync from top 1000 by lastmod
   - Only scrapes recipes not already in database
   - Works from the 1000 most recently updated recipes
   - Typically adds 0-50 new recipes per run (as Köket updates content)
   scraper.scrape_all_recipes()  # Returns RecipeScrapeResult
   save_to_database(recipes)      # Saves to DB

2. TEST MODE: Scrape 20 recipes, don't save to database
   scraper.scrape_all_recipes(max_recipes=20)

3. OVERWRITE MODE: Clear ALL old recipes, scrape top 1000
   scraper.scrape_all_recipes(force_all=True)
   save_to_database(recipes, clear_old=True)

OUTPUT:
~1000 recipes from Köket.se saved in PostgreSQL

METADATA (for GUI):
SCRAPER_NAME = "Köket.se"
DB_SOURCE_NAME = "Köket.se"
SCRAPER_DESCRIPTION = "Recept från köket.se"
EXPECTED_RECIPE_COUNT = 1000
SOURCE_URL = "https://www.koket.se"
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
    _is_type, RecipeScrapeResult, make_recipe_scrape_result,
    parse_iso8601_duration, StreamingRecipeSaver, validate_image_url
)

# GUI Metadata
SCRAPER_NAME = "Köket.se"
DB_SOURCE_NAME = "Köket.se"
SCRAPER_DESCRIPTION = "Recept från köket.se"
EXPECTED_RECIPE_COUNT = 1000
SOURCE_URL = "https://www.koket.se"

# Scraper config
MAX_URLS = 1250  # URLs to try (81% hit-rate → ~1000 recipes)
REQUEST_DELAY = 1.0  # Seconds between requests (gentle)
CONCURRENT_WORKERS = 1  # Single worker to avoid rate limiting
MIN_INGREDIENTS = 3  # Skip recipes with fewer ingredients


class KoketScraper:
    """Scraper for Köket.se using sitemap + httpx."""

    _SE_OVAN_PATTERN = re.compile(r'\s*(?:\(|,)\s*se ovan\s*\)?', re.IGNORECASE)

    def __init__(self):
        self.base_url = "https://www.koket.se"
        self.sitemap_url = f"{self.base_url}/sitemap.xml"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
        }
        self._progress_callback = None
        self._cancel_flag = False
        self._progress = {"total": 0, "current": 0, "success": 0}
        self._fail_reasons = {"http_error": 0, "no_jsonld": 0, "no_recipe_type": 0, "no_name": 0, "no_ingredients": 0, "few_ingredients": 0}

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
                    "total": self._progress["total"],
                    "current": self._progress["current"],
                    "success": self._progress["success"],
                    "percent": round(self._progress["current"] / max(1, self._progress["total"]) * 100, 1),
                    "message": message or f"Bearbetar {self._progress['current']}/{self._progress['total']}..."
                })
            except Exception:
                pass

    async def _send_activity(self):
        """Report scraper activity without changing visible progress."""
        if self._progress_callback:
            try:
                await self._progress_callback({"activity_only": True})
            except Exception:
                pass

    # ========== INGREDIENT FILTERING ==========

    @staticmethod
    def _is_section_header(text: str) -> bool:
        """Detect section headers mixed into Köket.se recipeIngredient.

        Köket.se puts sub-recipe titles ("Pressgurka", "Snabb gräddsås", "Fisk")
        directly in the recipeIngredient JSON-LD array. These are NOT ingredients.

        Pattern: headers start with uppercase word (not a number).
        Real ingredients with quantities start with a digit ("1,5 tsk", "50 g").
        Real no-quantity ingredients (smör, salt) start with lowercase.
        """
        if not text or len(text) > 80:
            return False
        if not text[0].isupper():
            return False

        # If first character is a digit, it's a real ingredient with quantity
        words = text.split()
        if words and words[0][0].isdigit():
            return False

        # Simple header: uppercase start, no digits, no commas, no parens
        # e.g., "Gryta", "Servering", "Pressgurka"
        if not re.search(r'\d', text) and ',' not in text and '(' not in text:
            return True

        # Header with parenthetical description: "Kryddmix (ger 2 msk)",
        # "Poolish (dag 1)", "Focacciadeg (1 långpanna)"
        # Pattern: UppercaseWord(s) (description) — no quantity before the paren
        # vs real ingredient: "1 burk kikärtor (eller 250 g)" starts with number
        if '(' in text:
            before_paren = text[:text.index('(')].strip()
            if before_paren and not re.search(r'\d', before_paren) and ',' not in before_paren:
                return True

        return False

    def _clean_ingredients(self, raw_ingredients: List[str]) -> List[str]:
        """Filter Köket section headers and skip '(se ovan)' usage references."""
        ingredients: List[str] = []

        for raw in raw_ingredients:
            text = str(raw).strip()
            if not text:
                continue

            if self._is_section_header(text):
                continue

            if self._SE_OVAN_PATTERN.search(text):
                continue

            ingredients.append(text)

        return ingredients

    # ========== SITEMAP PARSING ==========

    async def get_all_recipe_urls(self, client: httpx.AsyncClient) -> List[Tuple[str, str]]:
        """
        Fetch all recipe URLs from sitemap, sorted by lastmod (newest first).

        Returns:
            List of (url, lastmod_date) tuples, sorted by date descending
        """
        logger.info("Fetching recipe URLs from sitemap...")

        try:
            response = await client.get(self.sitemap_url)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

            urls_with_dates = []
            excluded = 0

            for url_elem in root.findall("ns:url", ns):
                loc = url_elem.find("ns:loc", ns)
                lastmod = url_elem.find("ns:lastmod", ns)

                if loc is not None and loc.text:
                    url = loc.text
                    mod_date = lastmod.text if lastmod is not None else "1970-01-01"

                    # Filter out non-recipe URLs
                    if self._is_recipe_url(url):
                        urls_with_dates.append((url, mod_date))
                    else:
                        excluded += 1

            # Sort by lastmod date (newest first)
            urls_with_dates.sort(key=lambda x: x[1], reverse=True)

            logger.info(f"   Found {len(urls_with_dates)} recipe URLs (excluded {excluded} non-recipe pages)")
            logger.info(f"   Newest: {urls_with_dates[0][1] if urls_with_dates else 'N/A'}")
            logger.info(f"   Oldest: {urls_with_dates[-1][1] if urls_with_dates else 'N/A'}")
            # Log sample URLs to help debug
            if urls_with_dates:
                logger.info(f"   Sample URLs: {[u[0] for u in urls_with_dates[:5]]}")

            return urls_with_dates

        except Exception as e:
            logger.error(f"Error fetching sitemap: {e}")
            return []

    def _is_recipe_url(self, url: str) -> bool:
        """Check if URL is a recipe (not a category/index/article page)."""
        # Extract path
        path = url.replace("https://www.koket.se", "").replace("http://www.koket.se", "")
        if not path or path == "/" or path == "":
            return False

        # Remove leading slash
        path = path.lstrip("/")

        # Exclude patterns (exact matches or contains)
        exclude_patterns = [
            '/mat/',           # Category pages
            '/tv-program/',    # TV show pages
            '/recept/',        # Recipe index (category)
            '/bok/',           # Book pages
            '/sok/',           # Search pages
            '/om-koket/',      # About pages
            '/nylagat-i-rutan', # TV listing
            '/vara-mest-populara-recept',  # Listing page
        ]

        for pattern in exclude_patterns:
            if pattern in url:
                return False

        # Exclude article/collection page patterns (these are not single recipes)
        # Articles typically have: numbers, collection words, or chef names with "med"
        article_patterns = [
            '-recept',           # Category: "koreanska-recept", "veganska-recept"
            '-tips',             # Articles: "frukosttips", "middagstips"
            '-mat-',             # Articles: "libanesisk-mat-vi-alskar"
            'godaste-',          # Articles: "vinterns-godaste-grytor"
            'basta-',            # Articles: "sommarens-basta-sallader"
            '-meny-',            # Menus: "festlig-helgmeny"
            'antligen-',         # Articles: "antligen-helg"
            'plus-',             # Plus content
            '-helg-',            # Weekend articles
            '-med-catarina',     # Chef articles
            '-med-tommy',        # Chef articles
            '-med-markus',       # Chef articles
            '-och-gott',         # "bakat-och-gott"
            'preppa-',           # "preppa-med-overnight-frukost"
            '-bagarn',           # "korvbrodsbagarn"
            'superbar',          # "havtorn-ett-litet-superbar", "superbaret"
            'vitamin',           # "c-vitamin...", "vitaminguide"
            'kickstarta-',       # Articles
            'veckomeny',         # "tips-pa-veckomeny"
            'gott-med-',         # "gott-med-nypon"
            '-guide',            # Guides
            '-boost-',           # Articles
            'kroppen',           # Health articles
        ]

        path_lower = path.lower()
        for pattern in article_patterns:
            if pattern in path_lower:
                return False

        # Exclude URLs with numbers (often articles like "5-tips", "10-basta")
        # But allow numbers that look like measurements (like "3-4" portions)
        import re
        # Pattern: single digit followed by dash and word (e.g., "5-tips", "10-basta")
        if re.search(r'^\d+-[a-z]', path_lower) or re.search(r'-\d+-[a-z]', path_lower):
            return False

        # Exclude known non-recipe path prefixes
        non_recipe_prefixes = [
            'kock/',             # Chef profiles
            'video/',            # Videos
            'artikel/',          # Articles
            'kategori/',         # Categories
            'tema/',             # Themes
            'kokbok/',           # Cookbooks
        ]

        for prefix in non_recipe_prefixes:
            if path_lower.startswith(prefix):
                return False

        return True

    # ========== JSON-LD PARSING ==========

    async def scrape_single_recipe(self, client: httpx.AsyncClient, url: str) -> Optional[Dict]:
        """Scrape a single recipe using JSON-LD schema."""
        try:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            html = response.text

            # Find JSON-LD script(s)
            json_ld_matches = re.findall(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                html, re.DOTALL
            )

            recipe_data = None
            for match in json_ld_matches:
                try:
                    data = json.loads(match)

                    # Handle @graph array
                    if isinstance(data, dict) and '@graph' in data:
                        for item in data['@graph']:
                            if _is_type(item, 'Recipe'):
                                recipe_data = item
                                break
                    # Handle direct Recipe object
                    elif isinstance(data, dict) and _is_type(data, 'Recipe'):
                        recipe_data = data
                    # Handle array of schemas
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and _is_type(item, 'Recipe'):
                                recipe_data = item
                                break

                    if recipe_data:
                        break
                except json.JSONDecodeError:
                    continue

            if not recipe_data:
                # Log what types we DID find for debugging
                if json_ld_matches:
                    self._fail_reasons["no_recipe_type"] += 1
                else:
                    self._fail_reasons["no_jsonld"] += 1
                return None

            # Extract fields
            name = recipe_data.get("name", "").strip()
            if not name:
                self._fail_reasons["no_name"] += 1
                return None

            # Ingredients
            ingredients = recipe_data.get("recipeIngredient", [])
            if not ingredients or not isinstance(ingredients, list):
                self._fail_reasons["no_ingredients"] += 1
                return None
            ingredients = self._clean_ingredients(ingredients)

            # Filter: Skip recipes with too few ingredients
            if len(ingredients) < MIN_INGREDIENTS:
                self._fail_reasons["few_ingredients"] += 1
                return None

            recipe = {
                "source_name": DB_SOURCE_NAME,
                "url": url,
                "name": name,
                "ingredients": ingredients,
                "scraped_at": datetime.now(timezone.utc),
            }

            # Image (validate to filter out relative/placeholder URLs)
            image = recipe_data.get("image")
            if image:
                if isinstance(image, list):
                    raw_url = image[0] if image else None
                elif isinstance(image, dict):
                    raw_url = image.get("url")
                else:
                    raw_url = str(image)
                validated = validate_image_url(raw_url)
                if validated:
                    recipe["image_url"] = validated

            # Prep time
            total_time = recipe_data.get("totalTime")
            if total_time:
                recipe["prep_time_minutes"] = parse_iso8601_duration(total_time)
            else:
                cook = parse_iso8601_duration(recipe_data.get("cookTime", "")) or 0
                prep = parse_iso8601_duration(recipe_data.get("prepTime", "")) or 0
                if cook + prep > 0:
                    recipe["prep_time_minutes"] = cook + prep

            # Servings
            servings = recipe_data.get("recipeYield")
            if servings:
                if isinstance(servings, list):
                    servings = servings[0] if servings else None
                if servings:
                    match = re.search(r'(\d+)', str(servings))
                    if match:
                        recipe["servings"] = int(match.group(1))

            return recipe

        except httpx.HTTPStatusError as e:
            self._fail_reasons["http_error"] += 1
            if self._fail_reasons["http_error"] <= 3:
                logger.warning(f"   HTTP {e.response.status_code}: {url}")
            return None
        except Exception as e:
            self._fail_reasons["http_error"] += 1
            if self._fail_reasons["http_error"] <= 3:
                logger.warning(f"   Error: {e} - {url}")
            return None

    # ========== PARALLEL SCRAPING ==========

    async def _worker(
        self,
        worker_id: int,
        queue: asyncio.Queue,
        results: List[Dict],
        client: httpx.AsyncClient,
        stream_saver: Optional[StreamingRecipeSaver] = None,
    ):
        """Worker that processes URLs from queue."""
        while not self._cancel_flag:
            try:
                url = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if queue.empty():
                    break
                continue

            try:
                recipe = await self.scrape_single_recipe(client, url)

                self._progress["current"] += 1

                if recipe:
                    if stream_saver:
                        await stream_saver.add(recipe)
                    else:
                        results.append(recipe)
                    self._progress["success"] += 1

                await self._send_activity()

                # Progress update every 10 recipes
                if self._progress["current"] % 10 == 0:
                    await self._send_progress()
                    fails = self._fail_reasons
                    logger.info(f"   Progress: {self._progress['current']}/{self._progress['total']} ({self._progress['success']} success) | Fails: http={fails['http_error']}, no_jsonld={fails['no_jsonld']}, no_recipe={fails['no_recipe_type']}, no_ing={fails['no_ingredients']}, few_ing={fails['few_ingredients']}")

                await asyncio.sleep(REQUEST_DELAY)

            except Exception as e:
                logger.debug(f"   Worker {worker_id} error: {e}")
            finally:
                queue.task_done()

    async def scrape_recipes(
        self,
        client: httpx.AsyncClient,
        urls: List[str],
        is_test: bool = False,
        stream_saver: Optional[StreamingRecipeSaver] = None,
    ) -> List[Dict]:
        """Scrape multiple recipes in parallel."""
        if not urls:
            return []

        results = []
        queue = asyncio.Queue()

        for url in urls:
            await queue.put(url)

        self._progress = {"total": len(urls), "current": 0, "success": 0}
        self._fail_reasons = {"http_error": 0, "no_jsonld": 0, "no_recipe_type": 0, "no_name": 0, "no_ingredients": 0, "few_ingredients": 0}
        await self._send_progress("Startar skrapning...")

        num_workers = 3 if is_test else CONCURRENT_WORKERS  # 3 workers for test, 1 for production
        logger.info(f"   Starting {num_workers} workers for {len(urls)} URLs...")

        workers = [
            asyncio.create_task(self._worker(i, queue, results, client, stream_saver))
            for i in range(num_workers)
        ]

        await queue.join()

        for worker in workers:
            worker.cancel()

        # Log final summary
        fails = self._fail_reasons
        found_count = stream_saver.seen_count if stream_saver else len(results)
        logger.info(f"   DONE: {found_count} recipes scraped")
        logger.info(f"   Fail reasons: http_error={fails['http_error']}, no_jsonld={fails['no_jsonld']}, no_recipe_type={fails['no_recipe_type']}, no_ingredients={fails['no_ingredients']}, few_ingredients={fails['few_ingredients']}")

        await self._send_progress(f"Done! {found_count} recipes scraped.")
        return results

    # ========== MAIN INTERFACE (GUI-compatible) ==========

    async def scrape_all_recipes(
        self,
        max_recipes: Optional[int] = None,
        batch_size: int = 10,  # Not used, kept for interface compatibility
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
                # Full overwrite mode: top MAX_URLS by lastmod
                urls_to_scrape = [url for url, _ in all_urls[:max_recipes or MAX_URLS]]
                logger.info(f"OVERWRITE MODE: Scraping {len(urls_to_scrape)} recipes")
            else:
                # Incremental: only new URLs not in database
                existing_urls = self._get_existing_urls()
                existing_count = len(existing_urls)
                all_candidate_urls = [url for url, _ in all_urls]
                candidate_urls = all_candidate_urls if max_recipes else all_candidate_urls[:MAX_URLS]
                urls_to_scrape = [url for url in candidate_urls if url not in existing_urls]

                if max_recipes and len(urls_to_scrape) > max_recipes:
                    urls_to_scrape = urls_to_scrape[:max_recipes]

                logger.info(f"INCREMENTAL: {len(urls_to_scrape)} new URLs to try (of {len(candidate_urls)} candidates)")
                logger.info(f"   Already in DB: {existing_count} recipes")

                # Smart stop: If we're at 70%+ of expected count, remaining URLs are likely non-recipes
                # (articles, categories, profiles that passed URL filter but have no Recipe schema)
                expected_recipes = 1000  # Expected actual recipes in top URLs
                if max_recipes is None and existing_count >= expected_recipes * 0.70:  # 700+ recipes
                    # Sample first 50 URLs to check if any are actual recipes
                    sample_size = min(50, len(urls_to_scrape))
                    if sample_size > 0:
                        logger.info(f"   Testing {sample_size} URLs to check for new recipes...")
                        urls_to_scrape = urls_to_scrape[:sample_size]
                    else:
                        logger.info("Already up to date!")
                        return make_recipe_scrape_result(
                            [],
                            force_all=force_all,
                            max_recipes=max_recipes,
                            reason="no_new_recipes",
                        )
                elif urls_to_scrape:
                    logger.info(f"   URLs to scrape (first 10): {urls_to_scrape[:10]}")

                if not urls_to_scrape:
                    logger.info("Already up to date!")
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
            )

            if self._cancel_flag:
                return make_recipe_scrape_result(
                    [],
                    force_all=force_all,
                    max_recipes=max_recipes,
                    cancelled=True,
                    reason="cancelled",
                )

            found_count = stream_saver.seen_count if stream_saver else len(recipes)
            logger.info(f"Scraped {found_count} new recipes")

            # Inform if no new recipes found but we're already well-stocked
            if found_count == 0 and not force_all and not max_recipes:
                existing_count = len(self._get_existing_urls())
                if existing_count >= 700:
                    logger.info(f"No new recipes found - already have {existing_count} recipes (fully synced)")
                    await self._send_progress(f"Already synced - {existing_count} recipes in database")

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

    def _get_existing_urls(self) -> set:
        """Get all existing recipe URLs from database."""
        with get_db_session() as db:
            from sqlalchemy import text
            result = db.execute(
                text("SELECT url FROM found_recipes WHERE source_name = :source"),
                {"source": DB_SOURCE_NAME}
            )
            return {row[0] for row in result}


# ========== MODULE-LEVEL FUNCTION (required by GUI) ==========

def save_to_database(recipes: List[Dict], clear_old: bool = False) -> Dict[str, int]:
    """Save recipes to database (module-level function for GUI compatibility)."""
    from scrapers.recipes._common import save_recipes_to_database
    return save_recipes_to_database(recipes, DB_SOURCE_NAME, clear_old=clear_old)


# ========== CLI ENTRY POINT ==========

async def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Köket.se Recipe Scraper")
    parser.add_argument("--test", action="store_true", help="Test mode: scrape 20 recipes, don't save")
    parser.add_argument("--overwrite", action="store_true", help="Delete existing and scrape fresh")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    if args.test:
        print("Köket.se TEST MODE")
    elif args.overwrite:
        print("Köket.se FULL OVERWRITE")
    else:
        print("Köket.se INCREMENTAL SYNC")
    print("=" * 60 + "\n")

    scraper = KoketScraper()

    if args.test:
        recipes = await scraper.scrape_all_recipes(max_recipes=20)
        print(f"\nTEST: Scraped {len(recipes)} recipes (not saved)")
        for r in recipes[:5]:
            print(f"   - {r['name']}")
    else:
        recipes = await scraper.scrape_all_recipes(force_all=args.overwrite)

        if recipes:
            stats = save_to_database(recipes, clear_old=args.overwrite)
            print(f"\nDone! Created: {stats['created']}, Updated: {stats['updated']}")
        else:
            print("\nAlready up to date - no new recipes to scrape")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
