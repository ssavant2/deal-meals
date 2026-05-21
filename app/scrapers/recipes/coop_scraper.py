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
from typing import Any, List, Dict, Optional, Tuple
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
    RecipeScrapeResult, incremental_attempt_limit, make_recipe_scrape_result,
    parse_iso8601_duration, recipe_target_reached, split_serving_lists,
    StreamingRecipeSaver, finish_streaming_recipe_scrape
)
from scrapers.recipes.url_discovery_cache import (
    record_non_recipe_url,
    record_recipe_url,
    select_urls_for_scrape,
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
COOP_RECIPE_API_BASE_URL = "https://proxy.api.coop.se/external/recipe"
COOP_RECIPE_API_VERSION = "v1"
COOP_API_CONCURRENT_REQUESTS = 4


def extract_coop_recipe_api_refs(page_html: str) -> Tuple[Optional[str], Optional[str], str]:
    """Extract Coop recipe IDs and API base URL from server-rendered recipe HTML."""
    text = html_lib.unescape(page_html or "")
    external_id_match = re.search(r'recipeExternalId["\']?\s*:\s*["\']?(\d+)', text)
    content_id_match = re.search(r'contentId["\']?\s*:\s*["\']?(\d+)', text)
    api_url_match = re.search(r'apiUrl["\']?\s*:\s*["\']([^"\']+)', text)
    return (
        external_id_match.group(1) if external_id_match else None,
        content_id_match.group(1) if content_id_match else None,
        api_url_match.group(1) if api_url_match else COOP_RECIPE_API_BASE_URL,
    )


def _format_api_quantity(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return str(value).strip()
    if number.is_integer():
        return str(int(number))
    return f"{number:g}".replace(".", ",")


def _format_coop_api_ingredient(item: Dict) -> str:
    ingredient_meta = item.get("ingredient") or {}
    name = item.get("name") or ingredient_meta.get("singularName") or ingredient_meta.get("pluralName") or ""
    if item.get("usePlural") and ingredient_meta.get("pluralName"):
        name = ingredient_meta["pluralName"]

    parts = [
        _format_api_quantity(item.get("quantity")),
        str(item.get("unit") or "").strip(),
        str(item.get("prePreparation") or "").strip(" ,"),
        str(name or "").strip(" ,"),
        str(item.get("postPreparation") or "").strip(" ,"),
    ]
    return re.sub(r"\s+", " ", " ".join(part for part in parts if part)).strip()


def _parse_coop_time_minutes(value: Any) -> Optional[int]:
    text = str(value or "").strip().lower()
    if not text:
        return None
    hours = re.search(r"(\d+)\s*(?:h|tim)", text)
    minutes = re.search(r"(\d+)\s*min", text)
    total = 0
    if hours:
        total += int(hours.group(1)) * 60
    if minutes:
        total += int(minutes.group(1))
    if total:
        return total
    only_number = re.search(r"\d+", text)
    return int(only_number.group(0)) if only_number else None


def parse_coop_recipe_api_payload(data: Dict, page_url: str) -> Optional[Dict]:
    """Convert Coop recipe API JSON into the app's FoundRecipe shape."""
    name = html_lib.unescape(str(data.get("name") or "").strip())
    if not name:
        return None

    ingredients: List[str] = []
    recipe_parts = sorted(data.get("recipePart") or [], key=lambda part: part.get("sequenceNumber") or 0)
    for part in recipe_parts:
        part_ingredients = sorted(
            part.get("ingredients") or [],
            key=lambda item: item.get("sequenceNumber") or 0,
        )
        for item in part_ingredients:
            ingredient = _format_coop_api_ingredient(item)
            if ingredient:
                ingredients.append(ingredient)

    ingredients = split_serving_lists(ingredients) or []
    if len(ingredients) < MIN_INGREDIENTS:
        return None

    relative_url = str(data.get("relativeUrl") or "").strip()
    recipe_url = f"https://www.coop.se{relative_url}" if relative_url.startswith("/") else page_url
    image_url = data.get("imageUrl")
    if isinstance(image_url, str) and image_url.startswith("http://"):
        image_url = "https://" + image_url.removeprefix("http://")

    servings = data.get("yieldValue") or data.get("numberOfServings")
    try:
        servings = int(float(servings)) if servings is not None else None
    except (TypeError, ValueError):
        servings = None

    return {
        "source_name": DB_SOURCE_NAME,
        "url": recipe_url,
        "name": name,
        "image_url": html_lib.unescape(image_url) if isinstance(image_url, str) else None,
        "ingredients": ingredients,
        "servings": servings,
        "prep_time_minutes": (
            _parse_coop_time_minutes(data.get("totalTime"))
            or _parse_coop_time_minutes(data.get("cookingTime"))
            or _parse_coop_time_minutes(data.get("preparationTime"))
        ),
        "scraped_at": datetime.now(timezone.utc),
    }


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
            "api_http_error": 0,
            "api_no_recipe_id": 0,
            "api_shape_changed": 0,
            "http_error": 0,
            "no_jsonld": 0,
            "no_recipe_type": 0,
            "no_name": 0,
            "no_ingredients": 0,
            "few_ingredients": 0,
            "timeout": 0
        }
        self._last_fail_reasons_by_url = {}
        self._last_fail_http_status_by_url = {}
        self._last_fail_errors_by_url = {}
        self._discovery_recorded_non_recipe = 0

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

    def _mark_failure(
        self,
        url: str,
        reason: str,
        *,
        http_status: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        self._fail_reasons[reason] = self._fail_reasons.get(reason, 0) + 1
        self._last_fail_reasons_by_url[url] = reason
        if http_status is not None:
            self._last_fail_http_status_by_url[url] = http_status
        if error:
            self._last_fail_errors_by_url[url] = error

    async def get_recipe_urls_from_sitemap(self) -> List[str]:
        """Fetch recipe URLs from sitemap."""
        logger.info(f"Fetching sitemap: {self.sitemap_url}")

        async with httpx.AsyncClient(
            headers=self.headers,
            timeout=30,
            event_hooks={"request": [ssrf_safe_event_hook]},
        ) as client:
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

    async def scrape_recipe_api_httpx(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> Optional[Dict]:
        """Scrape a Coop recipe through the public recipe API, with Playwright as fallback."""
        try:
            html_response = await client.get(url, follow_redirects=True)
            if html_response.status_code >= 400:
                self._mark_failure(url, "api_http_error", http_status=html_response.status_code)
                return None

            recipe_external_id, _content_id, api_base_url = extract_coop_recipe_api_refs(
                html_response.text
            )
            if not recipe_external_id:
                self._mark_failure(url, "api_no_recipe_id")
                return None

            api_response = await client.get(
                f"{api_base_url.rstrip('/')}/recipes/{recipe_external_id}",
                params={"api-version": COOP_RECIPE_API_VERSION},
            )
            if api_response.status_code >= 400:
                self._mark_failure(url, "api_http_error", http_status=api_response.status_code)
                return None

            recipe = parse_coop_recipe_api_payload(api_response.json(), str(html_response.url or url))
            if not recipe:
                self._mark_failure(url, "api_shape_changed")
                return None
            return recipe

        except httpx.HTTPError as e:
            self._mark_failure(url, "api_http_error", error=str(e))
            return None
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            self._mark_failure(url, "api_shape_changed", error=str(e))
            return None

    async def scrape_recipes_api_first(
        self,
        urls: List[str],
        recipes: List[Dict],
        *,
        stream_saver: Optional[StreamingRecipeSaver],
        max_recipes: Optional[int],
        record_discovery: bool,
    ) -> List[str]:
        """Try Coop's recipe API before falling back to Playwright for misses."""
        if not urls:
            return []

        failed_urls: List[str] = []
        semaphore = asyncio.Semaphore(COOP_API_CONCURRENT_REQUESTS)

        async def scrape_with_semaphore(client: httpx.AsyncClient, url: str):
            async with semaphore:
                return url, await self.scrape_recipe_api_httpx(client, url)

        async with httpx.AsyncClient(
            headers=self.headers,
            timeout=30,
            follow_redirects=True,
            event_hooks={"request": [ssrf_safe_event_hook]},
        ) as client:
            batch_size = 12
            for i in range(0, len(urls), batch_size):
                if self._cancel_flag or recipe_target_reached(
                    max_recipes=max_recipes,
                    recipes=recipes,
                    stream_saver=stream_saver,
                ):
                    break

                batch = urls[i:i + batch_size]
                logger.info(
                    f"Coop API-first batch {i // batch_size + 1}/"
                    f"{(len(urls) + batch_size - 1) // batch_size}: {len(batch)} URLs"
                )
                results = await asyncio.gather(
                    *(scrape_with_semaphore(client, url) for url in batch),
                    return_exceptions=True,
                )

                for result in results:
                    if isinstance(result, Exception):
                        logger.debug(f"Coop API-first task failed: {result}")
                        continue

                    url, recipe = result
                    if recipe:
                        if stream_saver:
                            before_seen = stream_saver.seen_count
                            await stream_saver.add(recipe)
                            saved_recipe = stream_saver.seen_count > before_seen
                        else:
                            recipes.append(recipe)
                            saved_recipe = True

                        self._progress["current"] += 1
                        if saved_recipe:
                            self._progress["success"] += 1
                            if record_discovery:
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
                    else:
                        failed_urls.append(url)

                    await self._send_activity()
                    if recipe_target_reached(
                        max_recipes=max_recipes,
                        recipes=recipes,
                        stream_saver=stream_saver,
                    ):
                        self._target_reached = True
                        self._cancel_flag = True
                        break

        api_success = self._progress["success"]
        logger.info(
            f"Coop API-first complete: {api_success} recipe(s), "
            f"{len(failed_urls)} URL(s) need Playwright fallback"
        )
        return failed_urls

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
                self._mark_failure(url, "no_jsonld")
                return None

            at_type = jsonld_data.get("@type")
            is_recipe = at_type == "Recipe" or (isinstance(at_type, list) and "Recipe" in at_type)
            if not is_recipe:
                self._mark_failure(url, "no_recipe_type")
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
                self._mark_failure(url, "no_name")
                return None
            recipe["name"] = html_lib.unescape(name)

            # Ingredients (required)
            ingredients = jsonld_data.get("recipeIngredient", [])
            # Split "Till servering" lists: "salladslök, chilimajonnäs och sesamfrön" → 3 items
            ingredients = split_serving_lists(ingredients)
            if not ingredients:
                self._mark_failure(url, "no_ingredients")
                return None

            if len(ingredients) < MIN_INGREDIENTS:
                self._mark_failure(url, "few_ingredients")
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
            self._mark_failure(url, "timeout", error="playwright_timeout")
            return None
        except Exception as e:
            logger.debug(f"Error scraping {url}: {e}")
            self._mark_failure(url, "http_error", error=str(e))
            return None

    async def scrape_all_recipes(
        self,
        max_recipes: Optional[int] = None,
        batch_size: int = CONCURRENT_WORKERS,
        force_all: bool = False,
        stream_saver: Optional[StreamingRecipeSaver] = None,
        bulk_import: bool = False,
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
        self._target_reached = False
        self._progress = {"total": 0, "current": 0, "success": 0}
        self._fail_reasons = {k: 0 for k in self._fail_reasons}
        self._last_fail_reasons_by_url = {}
        self._last_fail_http_status_by_url = {}
        self._last_fail_errors_by_url = {}
        self._discovery_recorded_non_recipe = 0

        # Get URLs from sitemap
        all_urls = await self.get_recipe_urls_from_sitemap()
        diagnostics = {
            "candidate_url_count": len(all_urls),
            "discovery_method": "coop_recipe_sitemap",
            "parser_method": "recipe_api_with_playwright_fallback",
        }
        if not all_urls:
            logger.error("No URLs found in sitemap")
            return make_recipe_scrape_result(
                [],
                force_all=force_all,
                max_recipes=max_recipes,
                failed=True,
                reason="no_recipe_urls",
                diagnostics=diagnostics,
            )

        # Shuffle URLs with fixed seed for deterministic but varied selection
        rng = random.Random(RANDOM_SEED)
        shuffled_urls = all_urls.copy()
        rng.shuffle(shuffled_urls)
        logger.info(f"Shuffled {len(shuffled_urls)} URLs with seed {RANDOM_SEED}")

        # Filter out existing unless force_all
        record_discovery = bool(stream_saver is not None and not force_all)
        if force_all:
            urls_to_scrape = shuffled_urls[:max_recipes or MAX_URLS]
            logger.info(f"Force mode: scraping {len(urls_to_scrape)} URLs")
        else:
            existing_urls = self.get_existing_urls()
            # Use higher limit until we reach target (~1000 recipes), then small batches
            filling_initial_target = len(existing_urls) < EXPECTED_RECIPE_COUNT * 0.9
            if max_recipes:
                limit = incremental_attempt_limit(
                    max_recipes=max_recipes,
                    available_count=len(shuffled_urls),
                    default_limit=MAX_INCREMENTAL,
                )
            elif filling_initial_target:
                limit = MAX_URLS
            else:
                limit = MAX_INCREMENTAL

            if record_discovery:
                urls_to_scrape, discovery_stats = select_urls_for_scrape(
                    source_name=DB_SOURCE_NAME,
                    candidate_urls=shuffled_urls,
                    max_http_attempts=limit,
                    bulk_import=bulk_import,
                )
                logger.info(f"URL discovery prefilter: {discovery_stats.format_log_suffix()}")
            else:
                new_urls = [u for u in shuffled_urls if u not in existing_urls]
                urls_to_scrape = new_urls[:limit]

            if max_recipes:
                logger.info(
                    "Incremental mode (configured): "
                    f"{len(urls_to_scrape)} candidate URLs selected "
                    f"(target {max_recipes}, {len(shuffled_urls)} sitemap URLs, "
                    f"{len(existing_urls)} recipes already in DB)"
                )
            elif filling_initial_target:
                logger.info(
                    "Incremental mode (filling): "
                    f"{len(urls_to_scrape)} URLs — DB has {len(existing_urls)}, "
                    f"target {EXPECTED_RECIPE_COUNT}"
                )
            else:
                logger.info(
                    "Incremental mode: "
                    f"{len(urls_to_scrape)} candidate URLs selected "
                    f"({len(shuffled_urls)} sitemap URLs, {len(existing_urls)} recipes already in DB)"
                )

        if not urls_to_scrape:
            logger.info("No new recipes to scrape")
            diagnostics["selected_url_count"] = 0
            return make_recipe_scrape_result(
                [],
                force_all=force_all,
                max_recipes=max_recipes,
                reason="no_new_recipes",
                diagnostics=diagnostics,
            )

        self._progress["total"] = len(urls_to_scrape)
        diagnostics["selected_url_count"] = len(urls_to_scrape)
        recipes = []
        recipes_lock = asyncio.Lock()

        api_failed_urls = await self.scrape_recipes_api_first(
            urls_to_scrape,
            recipes,
            stream_saver=stream_saver,
            max_recipes=max_recipes,
            record_discovery=record_discovery,
        )
        if recipe_target_reached(
            max_recipes=max_recipes,
            recipes=recipes,
            stream_saver=stream_saver,
        ):
            self._target_reached = True

        if self._target_reached or not api_failed_urls:
            found_count = stream_saver.seen_count if stream_saver else len(recipes)
            attempted_count = int(self._progress.get("current", 0) or 0)
            diagnostics.update({
                "attempted_url_count": attempted_count,
                "parsed_recipe_count": found_count,
                "filtered_non_recipe_count": self._discovery_recorded_non_recipe,
                "parse_rate": round(found_count / attempted_count, 4) if attempted_count else 0.0,
            })
            logger.info(f"Coop API-first finished without Playwright fallback: {found_count} recipes")
            return make_recipe_scrape_result(
                recipes,
                force_all=force_all,
                max_recipes=max_recipes,
                reason="target_reached" if self._target_reached else None,
                cancelled=self._cancel_flag and not self._target_reached,
                diagnostics=diagnostics,
            )

        urls_to_scrape = api_failed_urls
        self._cancel_flag = False
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
                    if recipe_target_reached(
                        max_recipes=max_recipes,
                        recipes=recipes,
                        stream_saver=stream_saver,
                    ):
                        self._target_reached = True
                        self._cancel_flag = True
                        break

                    try:
                        recipe = await self.scrape_recipe_playwright(page, url)
                        consecutive_errors = 0  # Reset on success
                    except Exception as e:
                        logger.warning(f"Worker {worker_id} error on {url}: {e}")
                        consecutive_errors += 1
                        recipe = None
                        self._mark_failure(url, "http_error", error=str(e))

                        # If too many consecutive errors, recreate context
                        if consecutive_errors >= max_consecutive_errors:
                            logger.warning(
                                f"Worker {worker_id}: {consecutive_errors} "
                                "consecutive errors, recreating context..."
                            )
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
                                before_seen = stream_saver.seen_count
                                await stream_saver.add(recipe)
                                saved_recipe = stream_saver.seen_count > before_seen
                            else:
                                recipes.append(recipe)
                                saved_recipe = True
                            if recipe_target_reached(
                                max_recipes=max_recipes,
                                recipes=recipes,
                                stream_saver=stream_saver,
                            ):
                                self._target_reached = True
                                self._cancel_flag = True
                            if saved_recipe:
                                self._progress["success"] += 1
                                if record_discovery:
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

                        await self._send_activity()
                        if not recipe and record_discovery:
                            reason = self._last_fail_reasons_by_url.pop(url, "parse_error")
                            http_status = self._last_fail_http_status_by_url.pop(url, None)
                            error = self._last_fail_errors_by_url.pop(url, None)
                            await asyncio.to_thread(
                                record_non_recipe_url,
                                source_name=DB_SOURCE_NAME,
                                url=url,
                                reason=reason,
                                http_status=http_status,
                                error=error,
                            )
                            self._discovery_recorded_non_recipe += 1

                        # Progress logging every 10 recipes (Coop is slow, 1 worker)
                        if self._progress["current"] % 10 == 0:
                            logger.info(
                                f"Progress: {self._progress['current']}/{len(urls_to_scrape)} "
                                f"({self._progress['success']} successful)"
                            )
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
        attempted_count = int(self._progress.get("current", 0) or 0)
        selected_count = len(urls_to_scrape)
        logger.info(
            f"Scraping complete: {found_count} recipes from {attempted_count} "
            f"attempted URLs ({selected_count} selected)"
        )
        if attempted_count:
            logger.info(f"Hit rate: {found_count/attempted_count*100:.1f}%")
        logger.info(f"Fail reasons: {self._fail_reasons}")
        if record_discovery:
            logger.info(f"URL discovery: recorded_non_recipe={self._discovery_recorded_non_recipe}")
        diagnostics.update({
            "attempted_url_count": attempted_count,
            "parsed_recipe_count": found_count,
            "filtered_non_recipe_count": self._discovery_recorded_non_recipe,
            "parse_rate": round(found_count / attempted_count, 4) if attempted_count else 0.0,
        })

        return make_recipe_scrape_result(
            recipes,
            force_all=force_all,
            max_recipes=max_recipes,
            reason=(
                "target_reached"
                if self._target_reached
                else ("cancelled" if self._cancel_flag else None)
            ),
            cancelled=self._cancel_flag and not self._target_reached,
            diagnostics=diagnostics,
        )

    async def scrape_incremental(self) -> RecipeScrapeResult:
        """Incremental scrape: only new recipes not already in database."""
        return await self.scrape_all_recipes()

    async def scrape_and_save(
        self,
        overwrite: bool = False,
        max_recipes: Optional[int] = None,
        quality_gate_callback=None,
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
        return await finish_streaming_recipe_scrape(
            saver,
            result,
            quality_gate_callback=quality_gate_callback,
        )


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
