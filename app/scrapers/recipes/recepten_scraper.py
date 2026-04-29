"""
Recepten.se Recipe Scraper - Sitemap + httpx

📝 DESCRIPTION:
Scrapes traditional Swedish home cooking recipes from Recepten.se using their
XML sitemaps for URL discovery and httpx for fast async HTTP requests.
No browser needed - pure httpx for speed.

🎯 STRATEGY:
1. Dynamically discover sitemap URL from robots.txt
2. Parse sitemap index to find recipe sitemaps (sitemap-recipe.xml)
3. Extract all recipe URLs from sitemaps with lastmod dates
4. Use lastmod dates for smart incremental sync
5. Scrape recipes with httpx + JSON-LD parsing

✨ FEATURES:
- Dynamic sitemap discovery from robots.txt (future-proof)
- Pure httpx for speed (no browser overhead)
- lastmod-based incremental sync
- 10 concurrent requests (vs 3-5 with browser)
- JSON-LD parsing for structured data
- Three run modes: incremental, test, full overwrite

🔧 RUN MODES:
1. DEFAULT (no arguments): Incremental sync - scrapes ALL new recipes
   - Only scrapes recipes not already in database
   - Small site (~800 recipes total) so no limit needed
   - Typically adds 0-5 new recipes per run
   python recepten_scraper.py

2. TEST MODE (--test): Scrape 20 recipes, don't save to database
   python recepten_scraper.py --test

3. OVERWRITE MODE (--overwrite): Clear ALL old recipes, full resync
   python recepten_scraper.py --overwrite

📊 OUTPUT:
~800 recipes from Recepten.se saved in PostgreSQL with:
- Name, ingredients (JSONB), prep time (minutes)
- Servings, image URL, source URL
- Source URL and scraping timestamp

🏷️ METADATA (for GUI):
SCRAPER_NAME = "Recepten.se"
DB_SOURCE_NAME = "Recepten.se"
SCRAPER_DESCRIPTION = "Recept från recepten.se"
EXPECTED_RECIPE_COUNT = 800
SOURCE_URL = "https://www.recepten.se"
"""

import httpx
from loguru import logger
from utils.security import ssrf_safe_event_hook
from typing import List, Dict, Optional, Tuple, Set
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
SCRAPER_NAME = "Recepten.se"
DB_SOURCE_NAME = "Recepten.se"  # MUST match source_name in saved recipes!
SCRAPER_DESCRIPTION = "Recept från recepten.se"
EXPECTED_RECIPE_COUNT = 800
SOURCE_URL = "https://www.recepten.se"

# Scraper config
MIN_INGREDIENTS = 3  # Skip recipes with fewer ingredients


class ReceptenScraper:
    """Fast scraper for Recepten.se using sitemap + httpx."""

    def __init__(self):
        self.base_url = "https://www.recepten.se"
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

    # ========== SITEMAP DISCOVERY ==========

    async def discover_sitemap_urls(self, client: httpx.AsyncClient) -> List[str]:
        """
        Dynamically discover recipe sitemap URLs from robots.txt.

        Flow:
        1. Fetch robots.txt to find main sitemap URL
        2. Fetch sitemap index
        3. Find recipe sitemaps (sitemap-recipe.xml)

        Returns:
            List of recipe sitemap URLs
        """
        logger.info("🔍 Discovering sitemaps from robots.txt...")

        # Step 1: Get sitemap URL from robots.txt
        try:
            response = await client.get(f"{self.base_url}/robots.txt")
            response.raise_for_status()

            # Find Sitemap: line
            sitemap_match = re.search(r'Sitemap:\s*(\S+)', response.text, re.IGNORECASE)
            if not sitemap_match:
                logger.warning("   No Sitemap found in robots.txt, using fallback")
                return self._get_fallback_sitemaps()

            main_sitemap = sitemap_match.group(1)
            logger.info(f"   Found main sitemap: {main_sitemap}")

        except Exception as e:
            logger.warning(f"   Error fetching robots.txt: {e}")
            return self._get_fallback_sitemaps()

        # Step 2: Fetch sitemap index
        try:
            response = await client.get(main_sitemap)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

            # Find all sitemap entries
            recipe_sitemaps = []

            # Try with namespace
            sitemap_elements = root.findall("ns:sitemap", ns)
            if not sitemap_elements:
                sitemap_elements = root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap")
            if not sitemap_elements:
                sitemap_elements = list(root)

            for sitemap_elem in sitemap_elements:
                # Try multiple ways to find loc
                loc = sitemap_elem.find("ns:loc", ns)
                if loc is None:
                    loc = sitemap_elem.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
                if loc is None:
                    loc = sitemap_elem.find("loc")

                if loc is not None and loc.text and 'recipe' in loc.text.lower():
                    recipe_sitemaps.append(loc.text)

            if recipe_sitemaps:
                logger.info(f"   Found {len(recipe_sitemaps)} recipe sitemaps")
                for url in recipe_sitemaps:
                    logger.info(f"      - {url.split('/')[-1]}")
                return recipe_sitemaps

            logger.warning("   No recipe sitemaps found in index, using fallback")
            return self._get_fallback_sitemaps()

        except Exception as e:
            logger.warning(f"   Error parsing sitemap index: {e}")
            return self._get_fallback_sitemaps()

    def _get_fallback_sitemaps(self) -> List[str]:
        """Fallback to known sitemap pattern if dynamic discovery fails."""
        logger.info("   Using fallback sitemap URLs")
        return [f"{self.base_url}/sitemap/sitemap-recipe.xml"]

    # ========== URL COLLECTION ==========

    async def get_recipe_urls_from_sitemap(self) -> List[Tuple[str, Optional[str]]]:
        """
        Fetch all recipe URLs from sitemaps.

        Returns:
            List of (url, lastmod) tuples
        """
        logger.info("📦 Fetching recipe URLs from sitemaps...")

        all_recipes = []

        async with httpx.AsyncClient(headers=self.headers, timeout=30, event_hooks={"request": [ssrf_safe_event_hook]}) as client:
            sitemap_urls = await self.discover_sitemap_urls(client)

            for sitemap_url in sitemap_urls:
                try:
                    response = await client.get(sitemap_url)
                    response.raise_for_status()

                    root = ET.fromstring(response.content)
                    ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

                    # Try multiple namespace approaches
                    url_elements = root.findall("ns:url", ns)
                    if not url_elements:
                        url_elements = root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}url")
                    if not url_elements:
                        url_elements = root.findall(".//url")

                    count = 0
                    for url_elem in url_elements:
                        # Find loc
                        loc = url_elem.find("ns:loc", ns)
                        if loc is None:
                            loc = url_elem.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
                        if loc is None:
                            loc = url_elem.find("loc")

                        # Find lastmod
                        lastmod = url_elem.find("ns:lastmod", ns)
                        if lastmod is None:
                            lastmod = url_elem.find("{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod")
                        if lastmod is None:
                            lastmod = url_elem.find("lastmod")

                        if loc is not None and loc.text:
                            url = loc.text
                            mod_date = lastmod.text if lastmod is not None else None

                            # Only include recipe URLs
                            if '/recept/' in url and url.endswith('.html'):
                                all_recipes.append((url, mod_date))
                                count += 1

                    logger.info(f"   {sitemap_url.split('/')[-1]}: {count} recipes")

                except Exception as e:
                    logger.warning(f"   Error fetching {sitemap_url}: {e}")

        logger.success(f"✅ Total recipe URLs: {len(all_recipes)}")
        return all_recipes

    # ========== DATABASE ==========

    async def get_existing_urls(self) -> Set[str]:
        """Get existing Recepten.se recipe URLs from database."""
        with get_db_session() as session:
            results = session.query(FoundRecipe.url).filter(
                FoundRecipe.source_name == DB_SOURCE_NAME
            ).all()
            return {r[0] for r in results}

    # ========== JSON-LD PARSING ==========

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
            html = response.text

            recipe = {
                "source_name": DB_SOURCE_NAME,
                "url": url,
                "scraped_at": datetime.now(timezone.utc)
            }

            # Find JSON-LD script(s)
            json_ld_matches = re.findall(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                html,
                re.DOTALL
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
                logger.debug(f"   No JSON-LD Recipe found: {url}")
                return None

            # Extract fields from JSON-LD
            recipe["name"] = recipe_data.get("name", "").strip()

            if not recipe["name"]:
                return None

            # Image
            image = recipe_data.get("image")
            if image:
                if isinstance(image, list):
                    recipe["image_url"] = image[0] if image else None
                elif isinstance(image, dict):
                    recipe["image_url"] = image.get("url")
                else:
                    recipe["image_url"] = str(image)

            # Ingredients — clean up whitespace and filter non-ingredient text
            raw_ingredients = recipe_data.get("recipeIngredient", [])
            if raw_ingredients and isinstance(raw_ingredients, list):
                cleaned = []
                for ing in raw_ingredients:
                    if not ing:
                        continue
                    # Collapse whitespace/newlines/nbsp into single spaces
                    text = re.sub(r'[\s\xa0]+', ' ', str(ing)).strip()
                    if not text:
                        continue
                    # Skip "eller ..." alternatives (duplicated from parent ingredient)
                    if text.lower().startswith('eller '):
                        continue
                    # Skip tips/comments (long sentences, exclamation marks, "tips:")
                    if len(text) > 120 or '!' in text or text.lower().startswith('tips'):
                        continue
                    cleaned.append(text)
                recipe["ingredients"] = cleaned if cleaned else None
            else:
                recipe["ingredients"] = None

            # Prep time (totalTime in ISO 8601 format)
            total_time = recipe_data.get("totalTime")
            if total_time:
                recipe["prep_time_minutes"] = parse_iso8601_duration(total_time)
            else:
                # Try cookTime + prepTime
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

            # Validate: must have enough ingredients and servings
            ingredients = recipe.get("ingredients", [])
            if not ingredients or len(ingredients) < MIN_INGREDIENTS:
                logger.debug(f"   Skipping {url}: only {len(ingredients) if ingredients else 0} ingredients (min {MIN_INGREDIENTS})")
                return None

            return recipe

        except httpx.HTTPStatusError as e:
            logger.debug(f"   HTTP error {e.response.status_code}: {url}")
            return None
        except Exception as e:
            logger.debug(f"   Error scraping {url}: {e}")
            return None

    # ========== CONCURRENT SCRAPING ==========

    async def scrape_recipes_concurrent(
        self,
        urls: List[str],
        max_concurrent: int = 2,
        stream_saver: Optional[StreamingRecipeSaver] = None,
        max_recipes: Optional[int] = None,
        record_discovery: bool = False,
    ) -> List[Dict]:
        """
        Scrape multiple recipes concurrently with httpx.
        Uses Semaphore for rate limiting.
        """
        recipes = []
        semaphore = asyncio.Semaphore(max_concurrent)
        self._discovery_recorded_non_recipe = 0

        async def scrape_with_semaphore(client: httpx.AsyncClient, url: str) -> Optional[Dict]:
            async with semaphore:
                result = await self.scrape_recipe_httpx(client, url)
                await self._report_activity()
                return result

        async with httpx.AsyncClient(headers=self.headers, timeout=30, event_hooks={"request": [ssrf_safe_event_hook]}) as client:
            total = len(urls)
            batch_size = 10

            for i in range(0, total, batch_size):
                if recipe_target_reached(
                    max_recipes=max_recipes,
                    recipes=recipes,
                    stream_saver=stream_saver,
                ):
                    break
                batch = urls[i:i + batch_size]

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

                found_count = stream_saver.seen_count if stream_saver else len(recipes)
                logger.info(f"   Progress: {min(i + batch_size, total)}/{total} ({found_count} successful)")

                # Report progress for GUI
                await self._report_progress(min(i + batch_size, total), total, found_count)

                # Delay between batches to be nice
                await asyncio.sleep(1.0)

        if record_discovery:
            logger.info(f"   URL discovery: recorded_non_recipe={self._discovery_recorded_non_recipe}")

        return recipes

    # ========== MAIN INTERFACE ==========

    async def scrape_all_recipes(
        self,
        max_recipes: Optional[int] = None,
        batch_size: int = 2,
        force_all: bool = False,
        stream_saver: Optional[StreamingRecipeSaver] = None,
    ) -> RecipeScrapeResult:
        """
        Main scraping method (matches interface expected by GUI).

        Args:
            max_recipes: Limit number of recipes (for test mode)
            batch_size: Concurrent requests (default 10)
            force_all: If True, scrape all recipes (for overwrite mode)

        Returns:
            RecipeScrapeResult with scraped recipe dicts
        """
        logger.info("🚀 Starting Recepten.se scrape (fast mode)...")

        # Get all URLs from sitemap
        all_urls = await self.get_recipe_urls_from_sitemap()

        if not all_urls:
            logger.warning("⚠️  No recipe URLs found in sitemap!")
            return make_recipe_scrape_result(
                [],
                force_all=force_all,
                max_recipes=max_recipes,
                failed=True,
                reason="no_recipe_urls",
            )

        # Sort by lastmod descending (newest first) for incremental priority
        all_urls.sort(key=lambda x: x[1] or "1970-01-01", reverse=True)
        urls_only = [url for url, _ in all_urls]

        # Check which URLs are already in database (unless force_all)
        if not force_all:
            existing_urls = await self.get_existing_urls()
            record_discovery = bool(stream_saver is not None)

            logger.info(f"   Existing in DB: {len(existing_urls)}")

            urls_to_scrape = urls_only
        else:
            urls_to_scrape = urls_only
            record_discovery = False
            logger.info(f"   Force mode: scraping ALL {len(urls_to_scrape)} recipes")

        if force_all:
            if max_recipes:
                urls_to_scrape = urls_to_scrape[:max_recipes]
        else:
            attempt_limit = incremental_attempt_limit(
                max_recipes=max_recipes,
                available_count=len(urls_only),
                default_limit=len(urls_only),
            )
            if record_discovery:
                urls_to_scrape, discovery_stats = select_urls_for_scrape(
                    source_name=DB_SOURCE_NAME,
                    candidate_urls=urls_only,
                    max_http_attempts=attempt_limit,
                )
                logger.info(f"   URL discovery prefilter: {discovery_stats.format_log_suffix()}")
            else:
                urls_to_scrape = [
                    url for url in urls_only if url not in existing_urls
                ][:attempt_limit]

            if not urls_to_scrape:
                logger.success("✅ All recipes already in database!")
                return make_recipe_scrape_result(
                    [],
                    force_all=force_all,
                    max_recipes=max_recipes,
                    reason="no_new_recipes",
                )

        logger.info(f"📄 Scraping {len(urls_to_scrape)} recipes...")

        # Scrape concurrently
        recipes = await self.scrape_recipes_concurrent(
            urls_to_scrape,
            max_concurrent=batch_size,
            stream_saver=stream_saver,
            max_recipes=max_recipes,
            record_discovery=record_discovery,
        )

        found_count = stream_saver.seen_count if stream_saver else len(recipes)
        logger.success(f"✅ Successfully scraped {found_count} recipes!")
        return make_recipe_scrape_result(
            recipes,
            force_all=force_all,
            max_recipes=max_recipes,
        )

    async def scrape_incremental(self) -> RecipeScrapeResult:
        """Incremental scrape: only new recipes not already in database."""
        return await self.scrape_all_recipes()

    # ========== DATABASE SAVE ==========

    def save_recipes(self, recipes: List[Dict], overwrite: bool = False) -> Dict:
        """Save recipes to database."""
        from scrapers.recipes._common import save_recipes_to_database
        return save_recipes_to_database(recipes, DB_SOURCE_NAME, clear_old=overwrite)

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


# ============================================================================
# MODULE-LEVEL FUNCTIONS (required by GUI/scheduler)
# ============================================================================

def save_to_database(recipes: List[Dict], clear_old: bool = False) -> Dict:
    """Save recipes to database."""
    from scrapers.recipes._common import save_recipes_to_database
    return save_recipes_to_database(recipes, DB_SOURCE_NAME, clear_old=clear_old)


# ============================================================================
# THREE RUN MODES (per RECIPE_TEMPLATE.md)
# ============================================================================

async def test_scrape():
    """Test mode: 20 recipes, no database save."""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    console.print("\n[bold blue]🍳 Recepten.se Recipe Scraper - TEST MODE[/bold blue]")
    console.print("[dim]Using sitemap + httpx (fast mode)[/dim]\n")

    scraper = ReceptenScraper()
    recipes = await scraper.scrape_all_recipes(max_recipes=20, batch_size=2)

    if recipes:
        console.print(f"\n[bold green]✅ Scraped {len(recipes)} recipes![/bold green]\n")

        table = Table(title="Sample Recipes")
        table.add_column("Name", style="cyan", width=35)
        table.add_column("Time", style="yellow", justify="right")
        table.add_column("Ingredients", style="green", justify="right")
        table.add_column("Servings", style="magenta", justify="right")

        for recipe in recipes[:10]:
            time_str = f"{recipe.get('prep_time_minutes', 'N/A')} min" if recipe.get('prep_time_minutes') else "N/A"

            table.add_row(
                recipe.get("name", "N/A")[:35],
                time_str,
                str(len(recipe.get("ingredients", []))) + " st",
                str(recipe.get("servings", "N/A"))
            )

        console.print(table)
        console.print("\n[yellow]⚠️  NOT saved to database (test mode)[/yellow]\n")
    else:
        console.print("[bold red]❌ No recipes scraped![/bold red]")

    return {"scraped": len(recipes) if recipes else 0, "saved": 0, "mode": "test"}


async def full_scrape():
    """Incremental mode: Only scrape NEW recipes (default)."""
    from rich.console import Console

    console = Console()

    console.print("\n[bold blue]" + "=" * 60 + "[/bold blue]")
    console.print("[bold blue]🍳 Recepten.se INCREMENTAL SYNC[/bold blue]")
    console.print("[bold blue]" + "=" * 60 + "[/bold blue]\n")

    scraper = ReceptenScraper()

    console.print("[yellow]📥 Checking for new recipes...[/yellow]\n")
    recipes = await scraper.scrape_all_recipes(batch_size=2)

    if not recipes:
        console.print("\n[bold green]✅ All recipes already in database![/bold green]")
        console.print("[dim]No new recipes to scrape.[/dim]\n")
        return {"created": 0, "updated": 0, "skipped": 0, "errors": 0, "mode": "incremental"}

    console.print(f"\n[bold green]✅ Scraped {len(recipes)} NEW recipes![/bold green]\n")

    console.print("[yellow]💾 Saving to database...[/yellow]\n")
    stats = scraper.save_recipes(recipes, overwrite=False)

    console.print("\n[cyan]Statistics:[/cyan]")
    console.print(f"  Created: {stats['created']}")
    console.print(f"  Updated: {stats['updated']}")
    console.print(f"  Skipped: {stats['skipped']}")
    console.print(f"  Errors:  {stats['errors']}")

    console.print("\n[bold blue]" + "=" * 60 + "[/bold blue]")
    console.print("[bold green]🎉 Done![/bold green]")
    console.print("[bold blue]" + "=" * 60 + "[/bold blue]\n")

    return {**stats, "mode": "incremental"}


async def overwrite_scrape():
    """Overwrite mode: Clear all old data, scrape everything."""
    from rich.console import Console

    console = Console()

    console.print("\n[bold red]" + "=" * 60 + "[/bold red]")
    console.print("[bold red]⚠️  Recepten.se FULL OVERWRITE MODE[/bold red]")
    console.print("[bold red]" + "=" * 60 + "[/bold red]\n")
    console.print("[yellow]This will DELETE all existing Recepten.se recipes and rescrape everything![/yellow]\n")

    scraper = ReceptenScraper()

    console.print("[yellow]📥 Scraping ALL recipes...[/yellow]\n")
    recipes = await scraper.scrape_all_recipes(batch_size=2, force_all=True)

    if not recipes:
        console.print("\n[bold red]❌ No recipes scraped![/bold red]")
        return {"cleared": 0, "created": 0, "updated": 0, "skipped": 0, "errors": 0, "mode": "overwrite"}

    console.print(f"\n[bold green]✅ Scraped {len(recipes)} recipes![/bold green]\n")

    console.print("[yellow]💾 Clearing old data and saving...[/yellow]\n")
    stats = scraper.save_recipes(recipes, overwrite=True)

    console.print("\n[cyan]Statistics:[/cyan]")
    console.print(f"  Cleared: {stats['cleared']}")
    console.print(f"  Created: {stats['created']}")
    console.print(f"  Updated: {stats['updated']}")
    console.print(f"  Skipped: {stats['skipped']}")
    console.print(f"  Errors:  {stats['errors']}")

    console.print("\n[bold blue]" + "=" * 60 + "[/bold blue]")
    console.print("[bold green]🎉 Full overwrite complete![/bold green]")
    console.print("[bold blue]" + "=" * 60 + "[/bold blue]\n")

    return {**stats, "mode": "overwrite"}


# ============================================================================
# CLI INTERFACE (per RECIPE_TEMPLATE.md)
# ============================================================================

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
            print("  python recepten_scraper.py              # Incremental sync (default)")
            print("  python recepten_scraper.py --test       # Test mode (20 recipes, no DB)")
            print("  python recepten_scraper.py --overwrite  # Full overwrite (clear + rescrape)")
            sys.exit(1)

    else:
        asyncio.run(full_scrape())
