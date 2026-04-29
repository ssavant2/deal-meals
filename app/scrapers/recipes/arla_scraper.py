"""
Arla.se Recipe Scraper

Scrapes Swedish recipes from Arla.se (Sweden's largest dairy brand).
Uses a recipe sitemap to discover URLs and extracts JSON-LD Recipe schema.
Includes comprehensive Arla brand name stripping to convert branded
ingredients to generic names for the matching system.

STRATEGY:
1. Fetch recipe sitemap (~6,900 URLs in one XML file)
2. Filter to new URLs not already in database (incremental)
3. Scrape JSON-LD Recipe schema from each page
4. Strip Arla brand names from ingredients
5. Save to database

NOTE: Arla's sitemap has no lastmod dates, so incremental mode is
purely URL-based (skip already-scraped URLs).

RUN MODES (GUI-compatible interface):
1. DEFAULT: Incremental sync (only new URLs)
   scraper.scrape_all_recipes()  # Returns RecipeScrapeResult
   save_to_database(recipes)

2. TEST MODE: Scrape 20 recipes, don't save
   scraper.scrape_all_recipes(max_recipes=20)

3. OVERWRITE MODE: Clear old, scrape fresh
   scraper.scrape_all_recipes(force_all=True)
   save_to_database(recipes, clear_old=True)

METADATA (for GUI):
SCRAPER_NAME = "Arla.se"
DB_SOURCE_NAME = "Arla.se"
SCRAPER_DESCRIPTION = "Recept från arla.se (~6 900 recept)"
EXPECTED_RECIPE_COUNT = 1000
SOURCE_URL = "https://www.arla.se/recept/"
"""

import httpx
from loguru import logger
from utils.security import ssrf_safe_event_hook
from typing import List, Dict, Optional
import asyncio
import re
import json
import os
import random
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
from scrapers.recipes.url_discovery_cache import (
    record_non_recipe_url,
    record_recipe_url,
    select_urls_for_scrape,
)

# GUI Metadata
SCRAPER_NAME = "Arla.se"
DB_SOURCE_NAME = "Arla.se"
SCRAPER_DESCRIPTION = "Recept från arla.se (~6 900 recept)"
EXPECTED_RECIPE_COUNT = 1000
SOURCE_URL = "https://www.arla.se/recept/"

# Scraper config
MAX_RECIPES = 1000  # Default limit (sitemap has ~6,900 total)
REQUEST_DELAY = 5.0  # Base delay between requests
MAX_DELAY = 10.0  # Max delay after rate limiting
MAX_RETRIES = 1  # Retry each 404 URL once (Arla returns 404 for rate limits)
CONCURRENT_REQUESTS = 5  # Parallel requests
MIN_INGREDIENTS = 3  # Skip recipes with fewer ingredients
RANDOM_SEED = 42  # Fixed seed for deterministic shuffle (same as Coop)

# Sentinel: scrape_recipe returns this for 404 (likely rate-limited, should retry)
_RETRY = "_RETRY"

# Arla's recipe sitemap (single XML file with all recipe URLs)
SITEMAP_URL = (
    "https://www.arla.se/sitemap.xml"
    "?type=Modules.Recipes.Business.SitemapUrlWriter.RecipeSitemapUrlWriter"
)


# ========== ARLA BRAND NAME STRIPPING ==========
#
# Arla recipes embed branded product names in ingredients:
#   "4 dl Arla Ko® Standardmjölk" → should become "4 dl standardmjölk"
#   "100 g Svenskt Smör från Arla®" → should become "100 g smör"
#   "3 msk Arla Köket® Smör- & rapsolja" → "3 msk smör- & rapsolja"
#   "3 dl Arla Köket® Riven ost gratäng" → "3 dl riven ost gratäng"
#   "200 g Arla Keso® Naturell 4%" → "200 g keso naturell 4%"
#
# The stripping happens in 6 steps (order matters):
# 1. Remove ® and ™ symbols
# 2. Replace full branded phrases ("Svenskt Smör från Arla" → "smör")
# 3. Replace Arla product-brands where the brand IS the product
#    ("Arla Keso" → "keso", since keso = cottage cheese)
# 4. Strip Arla sub-brand prefixes that are pure marketing
#    ("Arla Ko", "Arla Köket" → removed, product description follows)
# 5. Strip standalone partner brands ("Castello", "Apetina", etc.)
# 6. Strip any remaining bare "Arla" as fallback

# Trademark symbols
_TRADEMARK_RE = re.compile(r'[®™]')

# Step 2: Full phrase replacements (longest/most specific first)
_BRAND_PHRASE_REPLACEMENTS = [
    (re.compile(r'Svenskt\s+Smör\s+från\s+Arla', re.IGNORECASE), 'smör'),
    (re.compile(r'Svenskt\s+Normaltsaltat\s+Smör\s+från\s+Arla', re.IGNORECASE), 'smör'),
]

# Step 3: Arla product-brands where the brand name IS the product
# "Arla Keso Naturell" → "keso naturell" (keso = cottage cheese in Swedish)
_BRAND_PRODUCT_MAP = [
    (re.compile(r'\bArla\s+Keso\b', re.IGNORECASE), 'keso'),
    (re.compile(r'\bArla\s+Yoggi\b', re.IGNORECASE), 'yoggi'),
    (re.compile(r'\bArla\s+Färskost\b', re.IGNORECASE), 'färskost'),
    (re.compile(r'\bArla\s+Kvarg\b', re.IGNORECASE), 'kvarg'),
    (re.compile(r'\bArla\s+Kesella\b', re.IGNORECASE), 'kesella'),
    (re.compile(r'\bArla\s+Filmjölk\b', re.IGNORECASE), 'filmjölk'),
    (re.compile(r'\bArla\s+Gräddfil\b', re.IGNORECASE), 'gräddfil'),
    (re.compile(r'\bArla\s+Créme\s+Bonjour\b', re.IGNORECASE), 'färskost'),
]

# Step 4: Arla sub-brand prefixes to strip completely (product follows)
# These are marketing/product line labels, not product names
_BRAND_STRIP_PREFIXES = re.compile(
    r'\bArla\s+(?:'
    r'Ko|Köket|Protein|Lactofree|Lactosfree|'
    r'Eco|I\s+Love\s+Eco|Biologisk'
    r')\b\s*',
    re.IGNORECASE,
)

# Step 5: Standalone partner/subsidiary brands (not always "Arla" prefixed)
_STANDALONE_BRAND_STRIP = re.compile(
    r'\b(?:Castello|Apetina|Kelda|Kavli)\b\s*',
    re.IGNORECASE,
)

# Bregott: keep as product name (recognized Swedish butter brand)
_BREGOTT_RE = re.compile(r'\bBregott\b', re.IGNORECASE)

# Step 6: Generic "Arla" fallback (catches anything not matched above)
_BARE_ARLA_RE = re.compile(r'\bArla\b\s*', re.IGNORECASE)

# Step 7: Strip marketing qualifiers that don't help matching
# "Ekologisk Standardmjölk" → "mjölk", not "ekologisk standardmjölk"
_MARKETING_QUALIFIERS_RE = re.compile(
    r'\b(?:Ekologisk|Ekologiska|Ekologiskt|Eko)\b\s*',
    re.IGNORECASE,
)

# Arla-specific product names → generic Swedish names
# "Standardmjölk" is Arla's term for regular 3% milk — in recipes it's just "mjölk"
_ARLA_PRODUCT_SIMPLIFY = [
    (re.compile(r'\bStandardmjölk\b', re.IGNORECASE), 'mjölk'),
    (re.compile(r'\bStandardgrädde\b', re.IGNORECASE), 'grädde'),
    (re.compile(r'\bVispgrädde\b', re.IGNORECASE), 'vispgrädde'),
    (re.compile(r'\bMatlagningsgrädde\b', re.IGNORECASE), 'matlagningsgrädde'),
]

# Cleanup
_MULTI_SPACE_RE = re.compile(r'\s{2,}')


def _strip_arla_brands(text: str) -> str:
    """Strip Arla brand names from ingredient text, preserving the actual product.

    Handles all known Arla brand patterns:
    - Full phrases: "Svenskt Smör från Arla®" → "smör"
    - Sub-brand prefixes: "Arla Ko® Standardmjölk" → "standardmjölk"
    - Product-brands: "Arla Keso® Naturell" → "keso naturell"
    - Standalone brands: "Castello® Creamy White" → "creamy white"
    - Trademark symbols: ® ™ → stripped

    Returns the cleaned ingredient string, lowercased where brand text was removed.
    """
    if not text:
        return text

    # Step 1: Remove trademark symbols
    text = _TRADEMARK_RE.sub('', text)

    # Step 2: Full phrase replacements
    for pattern, replacement in _BRAND_PHRASE_REPLACEMENTS:
        text = pattern.sub(replacement, text)

    # Step 3: Arla product-brands (replace with generic name)
    for pattern, replacement in _BRAND_PRODUCT_MAP:
        text = pattern.sub(replacement, text)

    # Step 4: Arla sub-brand prefixes (strip completely)
    text = _BRAND_STRIP_PREFIXES.sub('', text)

    # Step 5: Standalone partner brands (strip)
    text = _STANDALONE_BRAND_STRIP.sub('', text)

    # Bregott: lowercase but keep (it's a product name people know)
    text = _BREGOTT_RE.sub('bregott', text)

    # Step 6: Generic "Arla" fallback
    text = _BARE_ARLA_RE.sub('', text)

    # Step 7: Strip marketing qualifiers and simplify product names
    text = _MARKETING_QUALIFIERS_RE.sub('', text)
    for pattern, replacement in _ARLA_PRODUCT_SIMPLIFY:
        text = pattern.sub(replacement, text)

    # Lowercase the product part (after brand stripping, remaining text is often
    # capitalized Arla-style: "Riven ost gratäng", "Crème Fraiche", etc.)
    # Quantities and units are fine in lowercase: "4 dl", "100 g"
    text = text.lower()

    # Clean up: collapse whitespace, strip leading/trailing
    text = _MULTI_SPACE_RE.sub(' ', text).strip()

    return text


class ArlaScraper:
    """Scraper for Arla.se recipes using sitemap + JSON-LD."""

    def __init__(self):
        self.base_url = "https://www.arla.se"
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

    async def get_all_recipe_urls(self, client: httpx.AsyncClient) -> List[str]:
        """Fetch all recipe URLs from Arla's recipe sitemap.

        Returns:
            List of recipe URLs (no lastmod dates available in this sitemap).
        """
        logger.info("Fetching recipe URLs from sitemap...")

        try:
            response = await client.get(SITEMAP_URL, follow_redirects=True)
            response.raise_for_status()

            root = ET.fromstring(response.text)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

            urls = []
            for url_elem in root.findall(".//sm:url", ns):
                loc = url_elem.find("sm:loc", ns)
                if loc is not None and loc.text:
                    urls.append(loc.text.strip())

            # Deterministic shuffle — sitemap has no lastmod dates and contains
            # clusters of dead 404 URLs. Seeded shuffle ensures reproducible
            # order across runs while distributing live/dead URLs evenly.
            rng = random.Random(RANDOM_SEED)
            rng.shuffle(urls)

            logger.info(f"   Found {len(urls)} recipe URLs in sitemap")
            return urls

        except Exception as e:
            logger.error(f"Error fetching sitemap: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return []

    # ========== RECIPE SCRAPING ==========

    async def scrape_recipe(self, client: httpx.AsyncClient, url: str):
        """Scrape a single recipe page.

        Returns:
            Recipe dict on success, _RETRY for 404 (likely rate limit),
            or None for other failures.
        """
        try:
            response = await client.get(url, follow_redirects=True)

            if response.status_code == 404:
                logger.debug(f"   HTTP 404 (rate limit?): {url}")
                return _RETRY

            if response.status_code == 403:
                logger.debug(f"   HTTP 403: {url}")
                return None

            response.raise_for_status()

            recipe_data = self._extract_json_ld(response.text, url)
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

                # Array of schemas (Arla uses this format)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and _is_type(item, "Recipe"):
                            return self._parse_recipe_schema(item, url)

            except json.JSONDecodeError:
                continue

        return None

    def _parse_recipe_schema(self, schema: Dict, url: str) -> Optional[Dict]:
        """Parse Recipe schema.org data into our format.

        Strips Arla brand names from all ingredients.
        """
        try:
            name = schema.get("name", "").strip()
            if not name:
                return None

            # Parse ingredients and strip Arla brand names
            ingredients = []
            raw_ingredients = schema.get("recipeIngredient", [])
            if isinstance(raw_ingredients, list):
                for ing in raw_ingredients:
                    if ing and ing.strip():
                        cleaned = _strip_arla_brands(ing.strip())
                        if cleaned:
                            ingredients.append(cleaned)

            # Split "X, Y och Z" serving lists into separate ingredients
            ingredients = split_serving_lists(ingredients)

            if len(ingredients) < MIN_INGREDIENTS:
                logger.debug(f"   Skipping {name}: only {len(ingredients)} ingredients")
                return None

            # Parse cooking time (PT30M -> 30)
            prep_time = parse_iso8601_duration(schema.get("prepTime", ""))
            cook_time = parse_iso8601_duration(schema.get("cookTime", ""))
            total_time = parse_iso8601_duration(schema.get("totalTime", ""))
            time_minutes = total_time or ((prep_time or 0) + (cook_time or 0)) or prep_time

            # Parse servings
            servings = None
            yield_val = schema.get("recipeYield")
            if yield_val:
                if isinstance(yield_val, list):
                    yield_val = yield_val[0] if yield_val else ""
                if isinstance(yield_val, (int, float)):
                    servings = int(yield_val)
                elif isinstance(yield_val, str):
                    num_match = re.search(r'(\d+)', str(yield_val))
                    if num_match:
                        servings = int(num_match.group(1))

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
        stream_saver: Optional[StreamingRecipeSaver] = None,
        max_recipes: Optional[int] = None,
        record_discovery: bool = False,
    ) -> List[Dict]:
        """Scrape multiple recipes with adaptive rate limiting.

        Uses a dynamic delay that increases on 404 (rate limit) and
        decreases on success. Failed URLs are re-queued for one retry.

        Args:
            client: HTTP client
            urls: List of recipe URLs to scrape

        Returns:
            List of recipe dicts
        """
        from collections import deque

        recipes = []
        total_original = len(urls)
        current_delay = REQUEST_DELAY
        retried = 0
        self._discovery_recorded_non_recipe = 0

        # Queue entries: (url, retry_count)
        queue = deque((url, 0) for url in urls)

        logger.info(f"Scraping up to {total_original} selected URLs (delay={current_delay}s)...")
        await self._report_progress(f"Fetching {total_original} recipes...", 0, total_original, 0)

        processed = 0
        while queue:
            if self._cancel_flag:
                logger.info("Scraping cancelled")
                break

            url, retry_count = queue.popleft()
            result = await self.scrape_recipe(client, url)

            if result == _RETRY:
                if retry_count < MAX_RETRIES:
                    # Rate limited: increase delay, re-queue at end
                    current_delay = min(current_delay + 1.0, MAX_DELAY)
                    queue.append((url, retry_count + 1))
                    retried += 1
                    logger.debug(f"   Rate limited, delay → {current_delay}s, re-queued: {url}")
                else:
                    logger.debug(f"   Gave up after retry: {url}")
                    if record_discovery:
                        await asyncio.to_thread(
                            record_non_recipe_url,
                            source_name=DB_SOURCE_NAME,
                            url=url,
                            reason="http_error",
                        )
                        self._discovery_recorded_non_recipe += 1
            elif result is not None:
                if stream_saver:
                    before_seen = stream_saver.seen_count
                    await stream_saver.add(result)
                    saved_recipe = stream_saver.seen_count > before_seen
                else:
                    recipes.append(result)
                    saved_recipe = True
                if saved_recipe and record_discovery:
                    await asyncio.to_thread(
                        record_recipe_url,
                        source_name=DB_SOURCE_NAME,
                        url=url,
                    )
                # Success: ease delay back toward base
                if current_delay > REQUEST_DELAY:
                    current_delay = max(REQUEST_DELAY, current_delay - 0.5)
                if recipe_target_reached(
                    max_recipes=max_recipes,
                    recipes=recipes,
                    stream_saver=stream_saver,
                ):
                    queue.clear()
            elif record_discovery:
                await asyncio.to_thread(
                    record_non_recipe_url,
                    source_name=DB_SOURCE_NAME,
                    url=url,
                    reason="parse_error",
                )
                self._discovery_recorded_non_recipe += 1

            processed += 1
            await self._report_activity()

            # Progress logging (based on original URLs processed)
            done = processed - retried
            if done % 10 == 0 or not queue:
                found_count = stream_saver.seen_count if stream_saver else len(recipes)
                logger.info(
                    f"   Progress: {done}/{total_original} "
                    f"({found_count} found, delay={current_delay}s, retried={retried})"
                )
                await self._report_progress(
                    f"Fetched {found_count} recipes...",
                    done, total_original, found_count,
                )

            await asyncio.sleep(current_delay)

        found_count = stream_saver.seen_count if stream_saver else len(recipes)
        attempted_count = max(0, processed - retried)
        logger.info(
            f"   Done: {found_count} recipes from {attempted_count} attempted URLs "
            f"({total_original} selected, {retried} retried, final delay={current_delay}s)"
        )
        return recipes

    async def scrape_all_recipes(
        self,
        max_recipes: Optional[int] = None,
        batch_size: int = 10,
        force_all: bool = False,
        stream_saver: Optional[StreamingRecipeSaver] = None,
    ) -> RecipeScrapeResult:
        """Main scraping method (matches interface expected by GUI).

        Args:
            max_recipes: Limit number of recipes (for test mode, e.g., 20)
            batch_size: Not used (kept for interface compatibility)
            force_all: If True, scrape all recipes ignoring existing (overwrite)

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
                logger.error("No recipe URLs found!")
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
                urls_to_scrape = all_urls[:max_recipes or MAX_RECIPES]
                logger.info(f"OVERWRITE MODE: Scraping {len(urls_to_scrape)} recipes")
            else:
                # Incremental: only new URLs not in database
                existing_urls = self._get_existing_urls()
                if max_recipes:
                    attempt_limit = incremental_attempt_limit(
                        max_recipes=max_recipes,
                        available_count=len(all_urls),
                        default_limit=MAX_RECIPES,
                    )
                    if record_discovery:
                        urls_to_scrape, discovery_stats = select_urls_for_scrape(
                            source_name=DB_SOURCE_NAME,
                            candidate_urls=all_urls,
                            max_http_attempts=attempt_limit,
                        )
                        logger.info(f"   URL discovery prefilter: {discovery_stats.format_log_suffix()}")
                    else:
                        new_candidate_urls = [
                            url for url in all_urls if url not in existing_urls
                        ]
                        urls_to_scrape = new_candidate_urls[:attempt_limit]
                else:
                    if record_discovery:
                        urls_to_scrape, discovery_stats = select_urls_for_scrape(
                            source_name=DB_SOURCE_NAME,
                            candidate_urls=all_urls,
                            max_http_attempts=MAX_RECIPES,
                        )
                        logger.info(f"   URL discovery prefilter: {discovery_stats.format_log_suffix()}")
                    else:
                        candidate_urls = all_urls[:MAX_RECIPES]
                        urls_to_scrape = [
                            url for url in candidate_urls if url not in existing_urls
                        ]

                logger.info(
                    f"INCREMENTAL: {len(urls_to_scrape)} new recipes to scrape "
                    f"(target {max_recipes or 'auto'}, {len(existing_urls)} already in DB)"
                )

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
                stream_saver=stream_saver,
                max_recipes=max_recipes,
                record_discovery=record_discovery,
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
            logger.info(f"Scraped {found_count} recipes")
            if record_discovery:
                logger.info(f"   URL discovery: recorded_non_recipe={self._discovery_recorded_non_recipe}")
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
                {"source": DB_SOURCE_NAME},
            )
            return {row.url for row in result}


def save_to_database(recipes: List[Dict], clear_old: bool = False) -> Dict[str, int]:
    """Save recipes to database (module-level function for GUI compatibility)."""
    from scrapers.recipes._common import save_recipes_to_database
    return save_recipes_to_database(recipes, DB_SOURCE_NAME, clear_old=clear_old)


async def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Arla.se Recipe Scraper")
    parser.add_argument("--test", action="store_true", help="Test mode: scrape 20 recipes, don't save")
    parser.add_argument("--overwrite", action="store_true", help="Delete existing and scrape fresh")
    args = parser.parse_args()

    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )

    print("\n" + "=" * 60)
    if args.test:
        print("TEST MODE: Arla.se")
    elif args.overwrite:
        print("FULL OVERWRITE: Arla.se")
    else:
        print("INCREMENTAL SYNC: Arla.se")
    print("=" * 60 + "\n")

    scraper = ArlaScraper()

    if args.test:
        recipes = await scraper.scrape_all_recipes(max_recipes=20)
        print(f"\nTEST: Scraped {len(recipes)} recipes (not saved)")
        for r in recipes[:5]:
            print(f"   - {r['name']}")
            if r['ingredients']:
                print(f"     ({len(r['ingredients'])} ingredients, first 3:)")
                for ing in r['ingredients'][:3]:
                    print(f"       {ing}")
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
