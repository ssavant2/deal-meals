"""
My Recipes - Universal Recipe Scraper

DESCRIPTION:
Scrapes recipes from user-provided URLs. Supports any website that uses
JSON-LD Recipe schema (schema.org/Recipe). Falls back to Playwright for
JS-rendered pages where httpx can't find the JSON-LD.

STRATEGY:
1. User adds recipe URLs via the config modal in the GUI
2. URLs are stored in the custom_recipe_urls table
3. For each pending URL:
   a. Try httpx GET + extract JSON-LD Recipe schema
   b. If no JSON-LD found, try microdata (itemprop/itemscope)
   c. If still nothing, fall back to Playwright (headless browser)
4. Save successfully parsed recipes to found_recipes

FEATURES:
- Works with any website that has JSON-LD Recipe markup (~80% of recipe sites)
- Microdata fallback for sites using itemprop schema.org/Recipe
- Playwright fallback for JS-heavy sites (slower but more reliable)
- Per-URL status tracking (pending/ok/error/no_recipe/gave_up)
- Automatic retry on failure (up to 5 attempts before giving up)
- User manages URL list via config modal (add/remove)

RUN MODES (GUI-compatible interface):
1. INCREMENTAL (default): Scrape URLs with status pending/error/no_recipe
2. FULL: Re-scrape ALL URLs (reset all statuses to pending first)
3. TEST: Scrape first 5 pending URLs, don't save to database

OUTPUT:
User-selected recipes saved in PostgreSQL

METADATA (for GUI):
SCRAPER_NAME = "My Recipes"
DB_SOURCE_NAME = "My Recipes"
SCRAPER_DESCRIPTION = "Recept från egna länkar"
EXPECTED_RECIPE_COUNT = 0
SOURCE_URL = ""
"""

import httpx
import re
import json
from loguru import logger
from utils.security import ssrf_safe_event_hook, is_safe_url
from typing import List, Dict, Optional
import asyncio
import os
import sys
from datetime import datetime, timezone

# Add app directory to path
app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, app_dir)

from database import get_db_session
from scrapers.recipes._common import (
    extract_json_ld_recipe, parse_iso8601_duration,
    RecipeScrapeResult, make_recipe_scrape_result, StreamingRecipeSaver,
    validate_image_url, unescape_html
)

# GUI Metadata
SCRAPER_NAME = "My Recipes"
DB_SOURCE_NAME = "My Recipes"
SCRAPER_DESCRIPTION = "Recept från egna länkar"
EXPECTED_RECIPE_COUNT = 0
SOURCE_URL = ""

# Scraper config
REQUEST_DELAY = 1.0
MIN_INGREDIENTS = 1  # User deliberately chose these recipes — accept even simple ones
PLAYWRIGHT_TIMEOUT = 15000  # 15s page load timeout
PLAYWRIGHT_JS_WAIT = 3000  # 3s for JS to render
MAX_RETRIES = 5  # Give up after this many failed scrape attempts
MAX_RESPONSE_BODY_BYTES = 50 * 1024 * 1024  # 50 MB hard cap for arbitrary user-provided URLs
_BINARY_CONTENT_TYPE_PREFIXES = ("video/", "audio/", "image/")
_BINARY_CONTENT_TYPES = {
    "application/octet-stream",
    "application/pdf",
    "application/zip",
    "application/x-zip-compressed",
    "application/x-binary",
    "application/vnd.apple.mpegurl",
}


def _normalize_content_type(content_type: Optional[str]) -> str:
    """Normalize Content-Type header to bare lowercase mime type."""
    if not content_type:
        return ""
    return content_type.split(";", 1)[0].strip().lower()


def _is_clearly_non_html_content_type(content_type: Optional[str]) -> bool:
    """Return True only for content types that are clearly not recipe pages.

    We intentionally allow unknown/misconfigured types through because custom
    user-provided recipe URLs are messy in the real world.
    """
    normalized = _normalize_content_type(content_type)
    if not normalized:
        return False
    if normalized in ("text/html", "application/xhtml+xml", "text/plain"):
        return False
    if normalized.startswith(_BINARY_CONTENT_TYPE_PREFIXES):
        return True
    return normalized in _BINARY_CONTENT_TYPES


def _declared_body_too_large(content_length: Optional[str]) -> bool:
    """Reject only when server explicitly declares a response larger than our cap."""
    if not content_length:
        return False
    try:
        return int(content_length) > MAX_RESPONSE_BODY_BYTES
    except (TypeError, ValueError):
        return False


class MyRecipesScraper:
    """Universal scraper for user-provided recipe URLs."""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
        }
        self._progress_callback = None
        self._cancel_flag = False
        self._progress = {"total": 0, "current": 0, "success": 0}

    def cancel(self):
        """Cancel ongoing scrape."""
        self._cancel_flag = True

    def set_progress_callback(self, callback):
        """Set callback for progress updates."""
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
                    "message": message or f"Processing {self._progress['current']}/{self._progress['total']}..."
                })
            except Exception:
                pass

    # ========== URL MANAGEMENT ==========

    def _get_urls_by_status(self, statuses: List[str]) -> List[Dict]:
        """Get custom URLs filtered by status."""
        from sqlalchemy import text
        with get_db_session() as db:
            placeholders = ", ".join(f":s{i}" for i in range(len(statuses)))
            params = {f"s{i}": s for i, s in enumerate(statuses)}
            result = db.execute(
                text(f"SELECT id, url, label, status FROM custom_recipe_urls WHERE status IN ({placeholders}) ORDER BY id"),
                params
            )
            return [{"id": row[0], "url": row[1], "label": row[2], "status": row[3]} for row in result]

    def _update_url_status(self, url: str, status: str, label: str = None, error: str = None):
        """Update the status of a custom URL after scraping."""
        from sqlalchemy import text
        with get_db_session() as db:
            if status in ("error", "no_recipe"):
                # Increment retry count; give up after MAX_RETRIES
                db.execute(
                    text("""
                        UPDATE custom_recipe_urls
                        SET retry_count = retry_count + 1,
                            status = CASE WHEN retry_count + 1 >= :max THEN 'gave_up' ELSE :status END,
                            last_error = :error, updated_at = NOW()
                        WHERE url = :url
                    """),
                    {"status": status, "error": error, "url": url, "max": MAX_RETRIES}
                )
            else:
                db.execute(
                    text("""
                        UPDATE custom_recipe_urls
                        SET status = :status, label = COALESCE(:label, label),
                            last_error = :error, retry_count = 0, updated_at = NOW()
                        WHERE url = :url
                    """),
                    {"status": status, "label": label, "error": error, "url": url}
                )
            db.commit()

    def _get_existing_recipe_urls(self) -> dict:
        """Get all existing recipe URLs from DB (any source). Returns {url: name}."""
        from sqlalchemy import text
        with get_db_session() as db:
            result = db.execute(text("SELECT url, name FROM found_recipes"))
            return {row[0]: row[1] for row in result}

    def _reset_all_statuses(self):
        """Reset all URLs to pending (for full mode)."""
        from sqlalchemy import text
        with get_db_session() as db:
            db.execute(text(
                "UPDATE custom_recipe_urls SET status = 'pending', last_error = NULL, retry_count = 0, updated_at = NOW()"
            ))
            db.commit()

    # ========== RECIPE PARSING ==========

    def _parse_recipe_from_jsonld(self, jsonld: Dict, url: str) -> Optional[Dict]:
        """Convert a JSON-LD Recipe object to our recipe dict format."""
        name = jsonld.get("name", "").strip()
        if not name:
            return None
        name = unescape_html(name)

        ingredients = jsonld.get("recipeIngredient", [])
        if not ingredients or not isinstance(ingredients, list):
            return None
        ingredients = [unescape_html(str(i).strip()) for i in ingredients if i]

        if len(ingredients) < MIN_INGREDIENTS:
            return None

        recipe = {
            "source_name": DB_SOURCE_NAME,
            "url": url,
            "name": name,
            "ingredients": ingredients,
            "scraped_at": datetime.now(timezone.utc),
        }

        # Image
        image = jsonld.get("image")
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
        total_time = jsonld.get("totalTime")
        if total_time:
            recipe["prep_time_minutes"] = parse_iso8601_duration(total_time)
        else:
            cook = parse_iso8601_duration(jsonld.get("cookTime", "")) or 0
            prep = parse_iso8601_duration(jsonld.get("prepTime", "")) or 0
            if cook + prep > 0:
                recipe["prep_time_minutes"] = cook + prep

        # Servings
        servings = jsonld.get("recipeYield")
        if servings:
            if isinstance(servings, list):
                servings = servings[0] if servings else None
            if servings:
                match = re.search(r'(\d+)', str(servings))
                if match:
                    recipe["servings"] = int(match.group(1))

        return recipe

    # ========== MICRODATA EXTRACTION (fallback for sites without JSON-LD Recipe) ==========

    def _extract_microdata_recipe(self, html: str, url: str) -> Optional[Dict]:
        """Extract recipe from HTML microdata (itemprop/itemscope schema.org/Recipe)."""
        # Check if the page has a Recipe itemscope
        if 'itemtype="http://schema.org/Recipe"' not in html and \
           'itemtype="https://schema.org/Recipe"' not in html:
            return None

        recipe = {
            "source_name": DB_SOURCE_NAME,
            "url": url,
            "scraped_at": datetime.now(timezone.utc),
        }

        # Extract name
        name_match = re.search(
            r'itemprop="name"[^>]*>([^<]+)<',
            html
        )
        # Also try: <meta itemprop="name" content="...">
        if not name_match:
            name_match = re.search(
                r'itemprop="name"\s+content="([^"]+)"',
                html
            )
        if not name_match:
            return None
        recipe["name"] = unescape_html(name_match.group(1).strip())

        # Extract ingredients
        ingredients = re.findall(
            r'itemprop="recipeIngredient"[^>]*>([^<]+)<',
            html
        )
        if not ingredients:
            return None
        ingredients = [unescape_html(i.strip()) for i in ingredients if i.strip()]
        # Filter out non-ingredient items (recipeCategory etc. sometimes leaks)
        ingredients = [i for i in ingredients if len(i) > 1]
        if len(ingredients) < MIN_INGREDIENTS:
            return None
        recipe["ingredients"] = ingredients

        # Extract image
        img_match = re.search(
            r'itemprop="image"[^>]*(?:src|content)="(https?://[^"]+)"',
            html
        )
        if img_match:
            validated = validate_image_url(img_match.group(1))
            if validated:
                recipe["image_url"] = validated

        # Extract prep time
        time_match = re.search(
            r'itemprop="totalTime"[^>]*content="([^"]+)"',
            html
        )
        if time_match:
            recipe["prep_time_minutes"] = parse_iso8601_duration(time_match.group(1))

        # Extract servings
        yield_match = re.search(
            r'itemprop="recipeYield"[^>]*(?:content="([^"]+)"|>([^<]+)<)',
            html
        )
        if yield_match:
            yield_val = yield_match.group(1) or yield_match.group(2)
            if yield_val:
                servings_match = re.search(r'(\d+)', yield_val)
                if servings_match:
                    recipe["servings"] = int(servings_match.group(1))

        return recipe

    # ========== HTTPX SCRAPING (fast path) ==========

    async def _scrape_with_httpx(self, client: httpx.AsyncClient, url: str) -> Optional[Dict]:
        """Try to scrape a recipe using httpx (fast, no JS)."""
        try:
            async with client.stream("GET", url, follow_redirects=True) as response:
                response.raise_for_status()

                final_url = str(response.url)
                if not is_safe_url(final_url):
                    logger.warning(f"httpx final URL failed safety check: {final_url}")
                    return None

                content_type = response.headers.get("content-type")
                if _is_clearly_non_html_content_type(content_type):
                    logger.debug(f"Skipping clearly non-HTML URL: {url} ({content_type})")
                    return None

                if _declared_body_too_large(response.headers.get("content-length")):
                    logger.debug(f"Skipping oversized URL by Content-Length: {url}")
                    return None

                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BODY_BYTES:
                        logger.debug(f"Skipping oversized URL after streaming >50MB: {url}")
                        return None

                encoding = response.encoding or "utf-8"
                html = bytes(body).decode(encoding, errors="replace")

            # Strategy 1: JSON-LD (most common)
            jsonld = extract_json_ld_recipe(html)
            if jsonld:
                return self._parse_recipe_from_jsonld(jsonld, final_url)

            # Strategy 2: Microdata (itemprop/itemscope)
            microdata = self._extract_microdata_recipe(html, final_url)
            if microdata:
                return microdata

            return None

        except httpx.HTTPStatusError as e:
            logger.debug(f"HTTP {e.response.status_code}: {url}")
            return None
        except Exception as e:
            logger.debug(f"httpx error for {url}: {e}")
            return None

    # ========== PLAYWRIGHT SCRAPING (fallback) ==========

    async def _scrape_with_playwright(self, url: str) -> Optional[Dict]:
        """Fall back to Playwright for JS-rendered pages."""
        if not is_safe_url(url):
            logger.warning(f"Playwright blocked unsafe URL before navigation: {url}")
            return None

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("Playwright not installed — cannot use fallback for JS-rendered pages")
            return None

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                try:
                    async def _route_request(route):
                        request = route.request
                        if request.resource_type in {"image", "media", "font"}:
                            await route.abort()
                            return
                        if request.resource_type == "document" and not is_safe_url(request.url):
                            logger.warning(f"Playwright blocked unsafe document URL: {request.url}")
                            await route.abort()
                            return
                        await route.continue_()

                    await page.route("**/*", _route_request)
                    response = await page.goto(url, timeout=PLAYWRIGHT_TIMEOUT, wait_until="domcontentloaded")

                    final_url = page.url or url
                    if not is_safe_url(final_url):
                        logger.warning(f"Playwright final URL failed safety check: {final_url}")
                        return None

                    if response:
                        headers = await response.all_headers()
                        content_type = headers.get("content-type")
                        if _is_clearly_non_html_content_type(content_type):
                            logger.debug(f"Playwright skipping clearly non-HTML URL: {url} ({content_type})")
                            return None
                        if _declared_body_too_large(headers.get("content-length")):
                            logger.debug(f"Playwright skipping oversized URL by Content-Length: {url}")
                            return None

                    await page.wait_for_timeout(PLAYWRIGHT_JS_WAIT)

                    # Extract JSON-LD via browser JS
                    jsonld_data = await page.evaluate('''() => {
                        const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                        for (const script of scripts) {
                            try {
                                const data = JSON.parse(script.textContent);
                                // Direct Recipe
                                if (data["@type"] === "Recipe" ||
                                    (Array.isArray(data["@type"]) && data["@type"].includes("Recipe"))) {
                                    return data;
                                }
                                // @graph array
                                if (data["@graph"]) {
                                    for (const item of data["@graph"]) {
                                        if (item["@type"] === "Recipe" ||
                                            (Array.isArray(item["@type"]) && item["@type"].includes("Recipe"))) {
                                            return item;
                                        }
                                    }
                                }
                                // Array of schemas
                                if (Array.isArray(data)) {
                                    for (const item of data) {
                                        if (item["@type"] === "Recipe" ||
                                            (Array.isArray(item["@type"]) && item["@type"].includes("Recipe"))) {
                                            return item;
                                        }
                                    }
                                }
                            } catch (e) {}
                        }
                        return null;
                    }''')

                    if jsonld_data:
                        return self._parse_recipe_from_jsonld(jsonld_data, final_url)

                    # Fallback: try microdata from rendered HTML
                    rendered_html = await page.content()
                    microdata = self._extract_microdata_recipe(rendered_html, final_url)
                    if microdata:
                        return microdata

                    return None

                finally:
                    await browser.close()

        except Exception as e:
            logger.warning(f"Playwright error for {url}: {e}")
            return None

    # ========== MAIN SCRAPING LOGIC ==========

    async def _scrape_single_url(self, client: httpx.AsyncClient, url: str) -> Optional[Dict]:
        """Scrape a single URL: httpx first, Playwright fallback."""
        # Step 1: Try httpx (fast)
        recipe = await self._scrape_with_httpx(client, url)
        if recipe:
            logger.info(f"   OK (httpx): {recipe['name']}")
            return recipe

        # Step 2: Playwright fallback (slow)
        if not is_safe_url(url):
            logger.warning(f"Skipping Playwright fallback for unsafe URL: {url}")
            return None
        logger.debug(f"   No JSON-LD/microdata via httpx, trying Playwright: {url}")
        recipe = await self._scrape_with_playwright(url)
        if recipe:
            logger.info(f"   OK (playwright): {recipe['name']}")
            return recipe

        logger.info(f"   No recipe found: {url}")
        return None

    async def scrape_all_recipes(
        self,
        max_recipes: Optional[int] = None,
        batch_size: int = 10,
        force_all: bool = False,
        stream_saver: Optional[StreamingRecipeSaver] = None,
    ) -> RecipeScrapeResult:
        """Main scraping method (GUI-compatible interface)."""
        self._cancel_flag = False

        is_test = max_recipes is not None and stream_saver is None

        # Full mode: reset all statuses
        if force_all and not is_test:
            self._reset_all_statuses()

        # Get URLs to scrape — include failed URLs for retry (few URLs, worth retrying)
        urls_to_scrape = self._get_urls_by_status(["pending", "error", "no_recipe"])

        if not urls_to_scrape:
            logger.info("No pending URLs to scrape")
            await self._send_progress("No pending URLs to fetch.")
            return make_recipe_scrape_result(
                [],
                force_all=force_all,
                max_recipes=max_recipes,
                reason="no_pending_urls",
            )

        if is_test:
            urls_to_scrape = urls_to_scrape[:max_recipes or 5]

        self._progress = {"total": len(urls_to_scrape), "current": 0, "success": 0}
        await self._send_progress("Starting recipe fetch...")

        recipes = []
        async with httpx.AsyncClient(
            headers=self.headers,
            timeout=30.0,
            follow_redirects=True,
            event_hooks={"request": [ssrf_safe_event_hook]}
        ) as client:

            # Pre-load existing recipe URLs to skip duplicates
            existing_recipe_urls = self._get_existing_recipe_urls()

            for url_entry in urls_to_scrape:
                if self._cancel_flag:
                    break

                url = url_entry["url"]

                # Skip if another scraper already has this recipe
                existing_name = existing_recipe_urls.get(url)
                if existing_name:
                    logger.info(f"   Already in DB (via other scraper): {existing_name}")
                    self._progress["current"] += 1
                    self._progress["success"] += 1
                    if not is_test:
                        self._update_url_status(url, "ok", label=existing_name)
                    await self._send_progress()
                    continue

                recipe = await self._scrape_single_url(client, url)

                self._progress["current"] += 1

                if recipe:
                    if stream_saver:
                        await stream_saver.add(recipe)
                    else:
                        recipes.append(recipe)
                    self._progress["success"] += 1
                    # Update URL status immediately (don't wait for save)
                    if not is_test:
                        self._update_url_status(url, "ok", label=recipe["name"])
                elif not is_test:
                    self._update_url_status(url, "no_recipe", error="No JSON-LD Recipe found")

                await self._send_progress()
                await asyncio.sleep(REQUEST_DELAY)

        found_count = stream_saver.seen_count if stream_saver else len(recipes)
        logger.info(f"Scraped {found_count} recipes from {len(urls_to_scrape)} URLs")
        await self._send_progress(f"Done! {found_count} recipes fetched.")
        return make_recipe_scrape_result(
            recipes,
            force_all=force_all,
            max_recipes=max_recipes,
            reason="cancelled" if self._cancel_flag else None,
            cancelled=self._cancel_flag,
        )

    async def scrape_incremental(self) -> RecipeScrapeResult:
        """Incremental scrape: only pending URLs."""
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


# ========== MODULE-LEVEL FUNCTION (required by GUI) ==========

def save_to_database(recipes: List[Dict], clear_old: bool = False) -> Dict[str, int]:
    """Save recipes to database."""
    from scrapers.recipes._common import save_recipes_to_database
    return save_recipes_to_database(recipes, DB_SOURCE_NAME, clear_old=clear_old)


# ========== CLI ENTRY POINT ==========

async def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="My Recipes - Universal Recipe Scraper")
    parser.add_argument("--test", action="store_true", help="Test mode: scrape 5 URLs, don't save")
    parser.add_argument("--full", action="store_true", help="Re-scrape all URLs")
    parser.add_argument("--add", type=str, help="Add a URL to the list")
    args = parser.parse_args()

    if args.add:
        from sqlalchemy import text
        with get_db_session() as db:
            db.execute(
                text("INSERT INTO custom_recipe_urls (url) VALUES (:url) ON CONFLICT (url) DO NOTHING"),
                {"url": args.add}
            )
            db.commit()
        print(f"Added: {args.add}")
        return

    print("\n" + "=" * 60)
    if args.test:
        print("My Recipes - TEST MODE")
    elif args.full:
        print("My Recipes - FULL RE-SCRAPE")
    else:
        print("My Recipes - INCREMENTAL")
    print("=" * 60 + "\n")

    scraper = MyRecipesScraper()

    if args.test:
        recipes = await scraper.scrape_all_recipes(max_recipes=5)
        print(f"\nTEST: Scraped {len(recipes)} recipes (not saved)")
        for r in recipes:
            print(f"   - {r['name']} ({len(r.get('ingredients', []))} ingredients)")
    else:
        recipes = await scraper.scrape_all_recipes(force_all=args.full)
        if recipes:
            stats = save_to_database(recipes, clear_old=args.full)
            print(f"\nDone! Created: {stats['created']}, Updated: {stats['updated']}")
        else:
            print("\nNo recipes to save")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
