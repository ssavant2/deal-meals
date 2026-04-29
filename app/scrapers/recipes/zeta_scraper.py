"""
Zeta.nu Recipe Scraper - FAST VERSION using Sitemap + httpx

DESCRIPTION:
Scrapes Italian-inspired recipes from Zeta.nu using their XML sitemaps
for URL discovery and httpx for fast async HTTP requests. No browser needed!

STRATEGY:
1. Dynamically discover sitemap URL from robots.txt
2. Parse sitemap index to find recipe sitemaps (oa_recipe-sitemap*.xml)
3. Collect all recipe URLs with lastmod dates
4. Use JSON-LD schema for recipe data extraction
5. Smart incremental sync based on existing URLs

FEATURES:
- Dynamic sitemap discovery from robots.txt (future-proof)
- Pure httpx for speed (no browser overhead)
- JSON-LD parsing for structured recipe data
- 10 concurrent requests for fast scraping
- ISO 8601 duration parsing for prep time

RUN MODES:
1. DEFAULT: Incremental sync - scrapes ALL new recipes
   - Only scrapes recipes not already in database
   - Small site (~1600 recipes total) so no limit needed
   - Typically adds 0-10 new recipes per run
   python zeta_scraper.py

2. TEST MODE: Scrape 20 recipes, don't save
   python zeta_scraper.py --test

3. OVERWRITE MODE: Clear ALL old recipes, full resync
   python zeta_scraper.py --overwrite

METADATA (for GUI):
SCRAPER_NAME = "Zeta.nu"
SCRAPER_DESCRIPTION = "Recept från zeta.nu"
EXPECTED_RECIPE_COUNT = 1600
SOURCE_URL = "https://www.zeta.nu"
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
    save_recipes_to_database, StreamingRecipeSaver, unescape_html
)

# GUI Metadata
SCRAPER_NAME = "Zeta.nu"
DB_SOURCE_NAME = "Zeta.nu"
SCRAPER_DESCRIPTION = "Recept från zeta.nu"
EXPECTED_RECIPE_COUNT = 1600
SOURCE_URL = "https://www.zeta.nu"

# Scraper config
MIN_INGREDIENTS = 3  # Skip recipes with fewer ingredients
SCRAPE_BATCH_SIZE = 6
CONCURRENT_REQUESTS = 3
SAVE_BATCH_SIZE = 50

# Zeta.nu JSON-LD has ingredient text with missing spaces between qualifiers
# and ingredient names (e.g., "torkadoregano" instead of "torkad oregano").
# This regex inserts a space after known qualifier prefixes when followed by
# a lowercase letter (indicating a joined word).
_QUALIFIER_PREFIXES = (
    # Cooking states / preparation methods
    'torkad', 'torkade', 'torkat',
    'färsk', 'färska',
    'malen', 'malna', 'malet', 'nymalen', 'nymalda', 'nymalet',
    'grovmalen', 'grovmalda', 'grovmalet',
    'finmalen', 'finmalda', 'finmalet',
    'hackad', 'hackade', 'hackat',
    'finhackad', 'finhackade', 'finhackat',
    'grovhackad', 'grovhackade', 'grovhackat',
    'riven', 'rivna', 'rivet',
    'finriven', 'finrivna', 'finrivet',
    'grovriven', 'grovrivna', 'grovrivet',
    'krossad', 'krossade', 'krossat',
    'strimlad', 'strimlade', 'strimlat',
    'skivad', 'skivade', 'skivat',
    'kokt', 'kokta', 'kokat',
    'rökt', 'varmrökt', 'kallrökt',
    'fryst', 'frysta',
    'skalad', 'skalade', 'skalat',
    'pressad', 'pressade', 'pressat',
)
# Sort longest first so "finhackad" matches before "hackad".
# Pattern A handles qualifier at word-start: "torkadoregano" → "torkad oregano"
# The left-boundary (?<![a-zåäö]) prevents re-splitting compound qualifiers.
_QUALIFIER_PATTERN_A = re.compile(
    r'(?<![a-zåäö])(' + '|'.join(sorted(_QUALIFIER_PREFIXES, key=len, reverse=True)) + r')([a-zåäö])',
    re.IGNORECASE
)
_QUALIFIER_SET = {q.lower() for q in _QUALIFIER_PREFIXES}
_QUALIFIERS_BY_LEN = sorted(_QUALIFIER_PREFIXES, key=len, reverse=True)
_RE_RECEPTBANK_REFERENCE = re.compile(
    r'\breceptet\s+hittar\s+du\s+här\s+i\s+receptbanken\b',
    re.IGNORECASE
)


def _remove_recipebank_reference_lines(ingredients: List[str]) -> List[str]:
    """Drop Zeta subrecipe reference lines.

    Some Zeta recipes include lines like "1/2 sats pizzadeg, receptet hittar du
    här i receptbanken". Those are references to a separate base recipe, not
    shopping ingredients for packaged dough/sauce.
    """
    cleaned = []
    for ingredient in ingredients:
        text = re.sub(r'\s+', ' ', str(ingredient or '')).strip()
        if not text:
            continue
        if _RE_RECEPTBANK_REFERENCE.search(text):
            continue
        cleaned.append(text)
    return cleaned


def _extract_ingredients_from_html(html: str) -> List[str]:
    """Extract ingredient text from Zeta.nu HTML elements.

    The HTML has properly spaced text (unlike JSON-LD which joins words).
    Combines quantity (Amount) and ingredient name from the IngredientList rows.
    """
    amounts = re.findall(
        r'IngredientList__RowContent--Amount[^"]*"[^>]*>(.*?)</div>',
        html, re.DOTALL
    )
    names = re.findall(
        r'IngredientList__RowContent--Ingredient[^"]*"[^>]*>(.*?)</div>',
        html, re.DOTALL
    )
    if not names:
        return []

    ingredients = []
    for i, name_html in enumerate(names):
        name = re.sub(r'<[^>]+>', ' ', name_html).strip()
        name = re.sub(r'\s+', ' ', name)
        if not name:
            continue
        # Prepend quantity if available
        if i < len(amounts):
            amount = re.sub(r'<[^>]+>', ' ', amounts[i]).strip()
            amount = re.sub(r'\s+', ' ', amount)
            if amount:
                name = f"{amount} {name}"
        ingredients.append(name)

    # Merge "eller" (or) alternatives that Zeta's HTML splits into separate rows.
    # E.g., ["150 g spritade bondbönor", "eller", "frysta sojabönor"] → one line.
    # Also handles "750 ml Barolo eller" + "3 flaskor Zeta Matlagningsvin Rött".
    merged = []
    i = 0
    while i < len(ingredients):
        line = ingredients[i]
        line_stripped = line.strip().lower()

        if line_stripped == 'eller':
            # Standalone "eller" — merge previous + "eller" + next
            if merged and i + 1 < len(ingredients):
                merged[-1] = f"{merged[-1]} eller {ingredients[i + 1]}"
                i += 2
                continue
        elif line_stripped.startswith('eller '):
            # Line starting with "eller ..." — merge with previous line
            if merged:
                merged[-1] = f"{merged[-1]} {line}"
                i += 1
                continue
        elif line_stripped.endswith(' eller'):
            # Line ending with "eller" — merge with next line
            if i + 1 < len(ingredients):
                merged.append(f"{line} {ingredients[i + 1]}")
                i += 2
                continue

        merged.append(line)
        i += 1

    return merged


def _phase1_replace(m):
    """Smart replacement: don't split if qualifier+next_char forms a longer qualifier."""
    qual = m.group(1)
    next_char = m.group(2)
    if (qual + next_char).lower() in _QUALIFIER_SET:
        return m.group(0)  # Keep as-is
    return qual + ' ' + next_char


def _fix_missing_spaces(ingredient: str) -> str:
    """Insert space between qualifier prefix and ingredient when joined.

    Fallback for JSON-LD data where "torkadoregano" needs to become "torkad oregano".
    Phase 1 (regex): split qualifiers at word-start with smart check
    Phase 2 (suffix): split qualifier suffixes from end of each word
    """
    prev = None
    text = ingredient
    while text != prev:
        prev = text
        text = _QUALIFIER_PATTERN_A.sub(_phase1_replace, text)
        # Phase 2: split qualifier suffix from end of each word
        words = text.split()
        new_words = []
        for word in words:
            w = word.lower()
            if w in _QUALIFIER_SET:
                new_words.append(word)
                continue
            split_done = False
            for qual in _QUALIFIERS_BY_LEN:
                if w.endswith(qual) and len(w) > len(qual):
                    new_words.append(word[:-len(qual)])
                    new_words.append(word[-len(qual):])
                    split_done = True
                    break
            if not split_done:
                new_words.append(word)
        text = ' '.join(new_words)
    return text


class ZetaScraper:
    """Fast scraper for Zeta.nu using sitemap + httpx."""

    def __init__(self):
        self.base_url = "https://www.zeta.nu"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
        }
        self._progress_callback = None
        self._cancel_flag = False

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
        3. Find recipe sitemaps (oa_recipe-sitemap*.xml)

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

            # Find all sitemap entries (try with namespace first, then without)
            recipe_sitemaps = []

            # Try with namespace
            sitemap_elements = root.findall("ns:sitemap", ns)
            logger.debug(f"   Found {len(sitemap_elements)} sitemap elements (with ns)")

            # If namespace search fails, try without namespace
            if not sitemap_elements:
                sitemap_elements = root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap")
                logger.debug(f"   Found {len(sitemap_elements)} sitemap elements (full ns path)")

            # Still nothing? Try plain element names
            if not sitemap_elements:
                sitemap_elements = list(root)  # Direct children
                logger.debug(f"   Found {len(sitemap_elements)} direct child elements")

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

            # No recipe-specific sitemaps found, use fallback
            logger.warning("   No recipe sitemaps found in index, using fallback")
            return self._get_fallback_sitemaps()

        except Exception as e:
            logger.warning(f"Error parsing sitemap index: {e}")
            return self._get_fallback_sitemaps()

    def _get_fallback_sitemaps(self) -> List[str]:
        """Fallback to known sitemap pattern if dynamic discovery fails."""
        logger.info("   Using fallback sitemap URLs")
        return [
            f"{self.base_url}/oa_recipe-sitemap.xml",
            f"{self.base_url}/oa_recipe-sitemap2.xml",
        ]

    async def get_recipe_urls_from_sitemap(self) -> List[Tuple[str, Optional[str]]]:
        """
        Fetch all recipe URLs from sitemaps.

        Returns:
            List of (url, lastmod) tuples
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
                        # Try multiple ways to find loc
                        loc = url_elem.find("ns:loc", ns)
                        if loc is None:
                            loc = url_elem.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
                        if loc is None:
                            loc = url_elem.find("loc")

                        # Try multiple ways to find lastmod
                        lastmod = url_elem.find("ns:lastmod", ns)
                        if lastmod is None:
                            lastmod = url_elem.find("{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod")
                        if lastmod is None:
                            lastmod = url_elem.find("lastmod")

                        if loc is not None and loc.text:
                            url = loc.text
                            mod_date = lastmod.text if lastmod is not None else None

                            # Only include recipe URLs (contains /recept/)
                            if '/recept/' in url:
                                all_recipes.append((url, mod_date))
                                count += 1

                    logger.info(f"   {sitemap_url.split('/')[-1]}: {count} recipes")

                except Exception as e:
                    logger.warning(f"   Error fetching {sitemap_url}: {e}")

        logger.info(f"Total recipe URLs: {len(all_recipes)}")
        return all_recipes

    async def get_existing_urls(self) -> Set[str]:
        """Get existing Zeta recipe URLs from database."""
        with get_db_session() as session:
            results = session.query(FoundRecipe.url).filter(
                FoundRecipe.source_name == DB_SOURCE_NAME
            ).all()
            return {r[0] for r in results}

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
                return None

            # Extract fields from JSON-LD
            recipe["name"] = unescape_html(recipe_data.get("name", "").strip())

            if not recipe["name"]:
                return None

            # Image
            image = recipe_data.get("image")
            if image:
                if isinstance(image, list):
                    recipe["image_url"] = unescape_html(image[0]) if image else None
                elif isinstance(image, dict):
                    recipe["image_url"] = unescape_html(image.get("url"))
                else:
                    recipe["image_url"] = unescape_html(str(image))

            # Ingredients — prefer HTML (mostly spaced) over JSON-LD (words joined)
            ingredients = _extract_ingredients_from_html(html)
            if not ingredients:
                # Fallback to JSON-LD
                ld_ingredients = recipe_data.get("recipeIngredient", [])
                if ld_ingredients and isinstance(ld_ingredients, list):
                    ingredients = [str(i).strip() for i in ld_ingredients if i]
            # Fix remaining concatenation issues (present in both HTML and JSON-LD)
            if ingredients:
                ingredients = [_fix_missing_spaces(ing) for ing in ingredients]
            if ingredients:
                ingredients = _remove_recipebank_reference_lines(ingredients)
            recipe["ingredients"] = ingredients or None

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

            # Servings (recipeYield)
            yield_val = recipe_data.get("recipeYield")
            if yield_val:
                if isinstance(yield_val, list):
                    yield_val = yield_val[0] if yield_val else None
                if yield_val:
                    match = re.search(r'(\d+)', str(yield_val))
                    if match:
                        recipe["servings"] = int(match.group(1))

            # Validate: must have enough ingredients and servings
            ingredients = recipe.get("ingredients", [])
            if not ingredients or len(ingredients) < MIN_INGREDIENTS:
                logger.debug(f"   Skipping {url}: only {len(ingredients) if ingredients else 0} ingredients (min {MIN_INGREDIENTS})")
                return None

            return recipe

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug(f"Recipe not found (404): {url}")
            else:
                logger.debug(f"HTTP error for {url}: {e}")
            return None
        except Exception as e:
            logger.debug(f"Error scraping {url}: {e}")
            return None

    async def scrape_recipe_with_semaphore(
        self,
        client: httpx.AsyncClient,
        url: str,
        semaphore: asyncio.Semaphore
    ) -> Optional[Dict]:
        """Wrapper with semaphore for concurrency control."""
        async with semaphore:
            result = await self.scrape_recipe_httpx(client, url)
            await self._report_activity()
            return result

    def save_recipes(self, recipes: List[Dict], overwrite: bool = False) -> Dict:
        """Save recipes to database."""
        return save_recipes_to_database(recipes, DB_SOURCE_NAME, clear_old=overwrite)

    async def _get_urls_to_scrape(
        self,
        max_recipes: Optional[int] = None,
        force_all: bool = False,
    ) -> List[str]:
        """Build the ordered URL list for either full or incremental mode."""
        all_urls_with_dates = await self.get_recipe_urls_from_sitemap()
        all_urls_with_dates.sort(key=lambda x: x[1] or "1970-01-01", reverse=True)
        all_urls = [url for url, _ in all_urls_with_dates]

        logger.info(f"Found {len(all_urls)} total recipe URLs from sitemap")
        if not all_urls:
            return []

        if force_all:
            urls_to_scrape = all_urls[:max_recipes] if max_recipes else all_urls
            logger.info(f"FULL MODE: Scraping {len(urls_to_scrape)} recipes")
            return urls_to_scrape

        existing_urls = await self.get_existing_urls()
        urls_to_scrape = [url for url in all_urls if url not in existing_urls]
        attempt_limit = incremental_attempt_limit(
            max_recipes=max_recipes,
            available_count=len(urls_to_scrape),
            default_limit=len(urls_to_scrape),
        )
        urls_to_scrape = urls_to_scrape[:attempt_limit]

        logger.info(f"Existing in DB: {len(existing_urls)}")
        logger.info(f"New to scrape: {len(urls_to_scrape)} (target {max_recipes or 'auto'})")
        return urls_to_scrape

    async def scrape_and_save(
        self,
        overwrite: bool = False,
        max_recipes: Optional[int] = None,
    ) -> Dict[str, int]:
        """Scrape and save in small chunks to keep full Zeta sync memory flat."""
        logger.info(f"\n{'='*60}")
        logger.info("ZETA RECIPE SCRAPER (streaming save)")
        logger.info(f"{'='*60}\n")

        urls_to_scrape = await self._get_urls_to_scrape(
            max_recipes=max_recipes,
            force_all=overwrite,
        )

        if not urls_to_scrape:
            reason = "no_recipe_urls" if overwrite else "no_new_recipes"
            saver = StreamingRecipeSaver(
                DB_SOURCE_NAME,
                batch_size=SAVE_BATCH_SIZE,
                overwrite=overwrite,
                max_recipes=max_recipes,
            )
            stats = await saver.finish()
            stats["scrape_status"] = "success_empty" if overwrite else "no_new_recipes"
            stats["scrape_reason"] = reason
            return stats

        saver = StreamingRecipeSaver(
            DB_SOURCE_NAME,
            batch_size=SAVE_BATCH_SIZE,
            overwrite=overwrite,
            max_recipes=max_recipes,
        )
        total = len(urls_to_scrape)

        semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
        async with httpx.AsyncClient(
            headers=self.headers,
            timeout=30,
            event_hooks={"request": [ssrf_safe_event_hook]},
        ) as client:
            for i in range(0, total, SCRAPE_BATCH_SIZE):
                if self._cancel_flag:
                    logger.info("Zeta scrape cancelled")
                    break
                if recipe_target_reached(max_recipes=max_recipes, stream_saver=saver):
                    break

                batch = urls_to_scrape[i:i + SCRAPE_BATCH_SIZE]
                tasks = [
                    self.scrape_recipe_with_semaphore(client, url, semaphore)
                    for url in batch
                ]
                results = await asyncio.gather(*tasks)

                for recipe in results:
                    await saver.add(recipe)
                    if recipe_target_reached(max_recipes=max_recipes, stream_saver=saver):
                        break

                progress = min(i + SCRAPE_BATCH_SIZE, total)
                logger.info(f"   Progress: {progress}/{total} ({saver.seen_count} successful)")
                await self._report_progress(progress, total, saver.seen_count)

                if i + SCRAPE_BATCH_SIZE < total:
                    await asyncio.sleep(1.0)

        stats = await saver.finish(cancelled=self._cancel_flag)
        logger.success(f"\nScraped and saved {saver.seen_count} Zeta recipes")
        return stats

    async def scrape_all_recipes(
        self,
        max_recipes: Optional[int] = None,
        batch_size: int = SCRAPE_BATCH_SIZE,
        skip_discovery: bool = False,  # Ignored - we always use sitemap
        force_all: bool = False
    ) -> RecipeScrapeResult:
        """
        Main scraping function (per RECIPE_TEMPLATE.md).

        1. Collect all recipe URLs from sitemap
        2. Compare against database (skip existing)
        3. Scrape only NEW recipes
        4. Return list of recipe dicts

        Args:
            max_recipes: Limit number of recipes (for test mode)
            batch_size: Concurrent batch size (default 10)
            skip_discovery: Ignored (kept for GUI compatibility)
            force_all: If True, scrape all recipes (for overwrite mode)

        Returns:
            RecipeScrapeResult with scraped recipe dicts
        """
        logger.info(f"\n{'='*60}")
        logger.info("ZETA RECIPE SCRAPER (Sitemap + httpx)")
        logger.info(f"{'='*60}\n")

        urls_to_scrape = await self._get_urls_to_scrape(
            max_recipes=max_recipes,
            force_all=force_all,
        )

        if not urls_to_scrape:
            if force_all:
                logger.warning("No recipe URLs found in sitemap!")
            else:
                logger.success("All recipes already in database!")
            return make_recipe_scrape_result(
                [],
                force_all=force_all,
                max_recipes=max_recipes,
                reason="no_recipe_urls" if force_all else "no_new_recipes",
                failed=force_all,
            )

        # Scrape recipes with concurrency
        logger.info(f"\nScraping {len(urls_to_scrape)} recipes ({CONCURRENT_REQUESTS} concurrent)...")

        recipes = []
        semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)

        async with httpx.AsyncClient(headers=self.headers, timeout=30, event_hooks={"request": [ssrf_safe_event_hook]}) as client:
            # Process in batches for progress logging
            batch_size = SCRAPE_BATCH_SIZE
            total = len(urls_to_scrape)

            for i in range(0, total, batch_size):
                if recipe_target_reached(max_recipes=max_recipes, recipes=recipes):
                    break
                batch = urls_to_scrape[i:i + batch_size]

                tasks = [
                    self.scrape_recipe_with_semaphore(client, url, semaphore)
                    for url in batch
                ]

                results = await asyncio.gather(*tasks)

                batch_recipes = [r for r in results if r]
                recipes.extend(batch_recipes)
                if recipe_target_reached(max_recipes=max_recipes, recipes=recipes):
                    recipes = recipes[:max_recipes]

                progress = min(i + batch_size, total)
                logger.info(f"   Progress: {progress}/{total} ({len(recipes)} successful)")

                # Report progress for GUI
                await self._report_progress(progress, total, len(recipes))

                # Delay between batches to be nice
                if i + batch_size < total:
                    await asyncio.sleep(1.0)

        logger.success(f"\nScraped {len(recipes)} recipes successfully!")
        return make_recipe_scrape_result(
            recipes,
            force_all=force_all,
            max_recipes=max_recipes,
        )

    async def scrape_incremental(self) -> RecipeScrapeResult:
        """Incremental scrape: only new recipes not already in database."""
        return await self.scrape_all_recipes()


# ============================================================================
# MODULE-LEVEL FUNCTIONS (for GUI compatibility)
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
    logger.info("\n" + "="*60)
    logger.info("ZETA SCRAPER - TEST MODE (20 recipes, no DB save)")
    logger.info("="*60 + "\n")

    scraper = ZetaScraper()
    recipes = await scraper.scrape_all_recipes(max_recipes=20)

    logger.info(f"\n{'='*60}")
    logger.info(f"TEST COMPLETE: {len(recipes)} recipes scraped")
    logger.info("="*60)

    # Show sample recipes
    for recipe in recipes[:3]:
        logger.info(f"\n  {recipe['name']}")
        logger.info(f"    Time: {recipe.get('prep_time_minutes', 'N/A')} min")
        logger.info(f"    Ingredients: {len(recipe.get('ingredients', []) or [])} items")

    return {"scraped": len(recipes), "saved": 0, "mode": "test"}


async def full_scrape():
    """Incremental mode: Only scrape NEW recipes (default)."""
    logger.info("\n" + "="*60)
    logger.info("ZETA SCRAPER - INCREMENTAL MODE (new recipes only)")
    logger.info("="*60 + "\n")

    scraper = ZetaScraper()
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
    logger.info("ZETA SCRAPER - OVERWRITE MODE (clear + full rescrape)")
    logger.info("="*60 + "\n")

    scraper = ZetaScraper()
    stats = await scraper.scrape_and_save(overwrite=True)

    logger.info(f"\n{'='*60}")
    logger.info("OVERWRITE COMPLETE")
    logger.info(f"  Cleared: {stats['cleared']}")
    logger.info(f"  Created: {stats['created']}")
    logger.info(f"  Updated: {stats['updated']}")
    logger.info(f"  Skipped: {stats['skipped']}")
    logger.info("="*60)

    return {**stats, "mode": "overwrite"}


# ============================================================================
# CLI INTERFACE (per RECIPE_TEMPLATE.md)
# ============================================================================

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
            print("  python zeta_scraper.py              # Incremental sync (default)")
            print("  python zeta_scraper.py --test       # Test mode (20 recipes, no DB)")
            print("  python zeta_scraper.py --overwrite  # Full overwrite (clear + rescrape)")
            sys.exit(1)

    else:
        asyncio.run(full_scrape())
