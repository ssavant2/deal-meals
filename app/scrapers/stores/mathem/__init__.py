"""
Mathem Store Plugin - E-commerce grocery scraper.

Mathem is Sweden's largest online grocery store with home delivery only.
No physical stores - offers are the same nationwide.

Uses Mathem's server-rendered Next.js data first, with Playwright kept as a
fallback. Includes polite delays and JSON-LD fallback for browser scraping.
"""

from typing import Any, List, Dict, Optional, Tuple
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import re
import asyncio
import json
import os
import httpx
from loguru import logger

from scrapers.stores.base import StorePlugin, StoreConfig, StoreConfigField, StoreScrapeResult
from scrapers.stores.weight_utils import parse_weight
from languages.sv.category_utils import guess_category as shared_guess_category
from utils.security import ssrf_safe_event_hook


MATHEM_BASE_URL = "https://www.mathem.se"
MATHEM_STORE_USER_AGENT = os.getenv(
    "MATHEM_STORE_USER_AGENT",
    "DealMealsBot/1.0 (store scraper; contact: local)",
)
MATHEM_HTTP_HEADERS = {
    "User-Agent": MATHEM_STORE_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.6",
}
MATHEM_RETRY_STATUSES = {429, 500, 502, 503, 504}
MATHEM_MAX_RETRIES = 3
MATHEM_RETRY_BACKOFF_SECONDS = 2.0


class _NextDataHTMLParser(HTMLParser):
    """Extract the JSON payload from Next.js' __NEXT_DATA__ script."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._capturing = False
        self._chunks: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "script":
            return
        attr_map = {key.lower(): value for key, value in attrs}
        if attr_map.get("id") == "__NEXT_DATA__":
            self._capturing = True

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._capturing:
            self._capturing = False

    @property
    def data(self) -> str:
        return "".join(self._chunks).strip()


def extract_mathem_next_data(html_text: str) -> Optional[Dict[str, Any]]:
    """Return the parsed __NEXT_DATA__ payload from a Mathem page."""
    parser = _NextDataHTMLParser()
    parser.feed(html_text or "")
    if not parser.data:
        return None
    try:
        parsed = json.loads(parser.data)
    except json.JSONDecodeError:
        logger.debug("Mathem __NEXT_DATA__ payload was not valid JSON")
        return None
    return parsed if isinstance(parsed, dict) else None


def _iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_dicts(item)


def find_mathem_discount_page_data(next_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Find the dehydrated page data that owns the discount product grids."""
    for candidate in _iter_dicts(next_data):
        blocks = candidate.get("blocks")
        if not isinstance(blocks, list):
            continue
        if any(block.get("component") == "product-grid" for block in blocks if isinstance(block, dict)):
            return candidate
    return None


def _parse_decimal(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("\xa0", " ").replace("kr", "").replace("SEK", "")
    text = re.sub(r"\s+", "", text).replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _absolute_mathem_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"{MATHEM_BASE_URL}{url}"
    return f"{MATHEM_BASE_URL}/{url.lstrip('/')}"


def _mathem_product_image(product: Dict[str, Any]) -> Optional[str]:
    for image in product.get("images") or []:
        if not isinstance(image, dict):
            continue
        for key in ("large", "thumbnail"):
            candidate = image.get(key)
            if isinstance(candidate, dict) and candidate.get("url"):
                return candidate["url"]
    return None


def _multi_buy_from_description(description: Optional[str]) -> Tuple[Optional[int], Optional[float]]:
    if not description:
        return None, None
    match = re.search(r"(\d+)\s+f[öo]r\s+([\d\s\xa0,.]+)\s*kr", description, re.IGNORECASE)
    if not match:
        return None, None
    total_price = _parse_decimal(match.group(2))
    if total_price is None:
        return None, None
    return int(match.group(1)), total_price


def iter_mathem_discount_products(page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return unique product records from Mathem product-grid blocks."""
    products: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for block in page_data.get("blocks") or []:
        if not isinstance(block, dict) or block.get("component") != "product-grid":
            continue

        block_products = block.get("products")
        if not isinstance(block_products, list):
            block_products = []
            for item in block.get("items") or []:
                if isinstance(item, dict) and item.get("itemType") == "product":
                    product = item.get("item")
                    if isinstance(product, dict):
                        block_products.append(product)

        for product in block_products:
            if not isinstance(product, dict):
                continue
            key = str(product.get("id") or product.get("frontUrl") or product.get("absoluteUrl") or "")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            products.append(product)

    return products


def mathem_ssr_product_to_raw(product: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map a Mathem Next.js product record to the raw format used by _parse_product."""
    price = _parse_decimal(product.get("grossPrice"))
    if price is None:
        return None

    discount = product.get("discount") if isinstance(product.get("discount"), dict) else {}
    promotion = product.get("promotion") if isinstance(product.get("promotion"), dict) else {}
    description = discount.get("descriptionShort") or promotion.get("descriptionShort")
    multi_buy_quantity, multi_buy_price = _multi_buy_from_description(description)

    original_price = _parse_decimal(discount.get("undiscountedGrossPrice"))
    if original_price is None:
        original_price = price

    raw: Dict[str, Any] = {
        "name": product.get("fullName") or product.get("name"),
        "price": price,
        "original_price": original_price,
        "unit": product.get("unitPriceQuantityAbbreviation") or "st",
        "size": product.get("nameExtra"),
        "brand": product.get("brand"),
        "image": _mathem_product_image(product),
        "url": _absolute_mathem_url(product.get("frontUrl") or product.get("absoluteUrl")),
    }

    if multi_buy_quantity and multi_buy_price:
        raw["multi_buy_quantity"] = multi_buy_quantity
        raw["multi_buy_price"] = multi_buy_price

    return raw


class MathemStore(StorePlugin):
    """
    Mathem store plugin.

    Scrapes "Extrapriser" (discounts) from Mathem's website.
    Mathem only has e-commerce, so no store selection is needed.
    """

    # Polite scraping settings
    SCROLL_DELAY = 1.5          # Seconds between scrolls (be nice to the server)
    PAGE_LOAD_DELAY = 2.0       # Seconds to wait after page load
    ENRICH_DELAY = 0.5          # Seconds between product page fetches
    MAX_ENRICH_PRODUCTS = None  # None = enrich every eligible product page

    def __init__(self):
        self.base_url = MATHEM_BASE_URL
        self.discounts_url = f"{self.base_url}/se/products/discounts/"

    @property
    def config(self) -> StoreConfig:
        return StoreConfig(
            id="mathem",
            name="Mathem",
            logo="/scrapers/stores/mathem/logo.svg",
            color="#00a651",  # Mathem green
            url="https://www.mathem.se",
            enabled=True,
            has_credentials=False,  # No login required
            description="Sveriges största nätmatbutik"
        )

    @property
    def estimated_scrape_time(self) -> int:
        """Mathem can take up to ~10 minutes when all eligible products are enriched."""
        return 600

    def get_config_fields(self) -> List[StoreConfigField]:
        """
        Return configuration fields for Mathem.

        Mathem is e-commerce only (no physical stores), so we just display
        a static info field - no selection needed.
        """
        return [
            StoreConfigField(
                key="info",
                label="E-handel",
                field_type="display",
                options=[{
                    "suffix": "(Hemkörning)",
                    "description": "Erbjudanden för din hemadress"
                }]
            )
        ]

    async def scrape_offers(self, credentials: Optional[Dict] = None) -> StoreScrapeResult:
        """
        Scrape offers from Mathem's discount page.

        Mathem has the same prices nationwide (e-commerce only),
        so no address selection is needed.

        Returns:
            StoreScrapeResult with products in standard format
        """
        logger.info("Starting Mathem scraping...")

        products, diagnostics = await self._scrape_discounts_http()
        if not products:
            logger.info("Mathem SSR scrape did not yield products, falling back to Playwright")
            playwright_products = await self._scrape_discounts_playwright()
            products = playwright_products
            diagnostics = {
                **diagnostics,
                "data_path": "playwright_dom",
                "playwright_product_count": len(playwright_products),
            }

        await self._report_progress(
            progress=65,
            message_key="ws.fetched_products",
            message_params={"count": len(products)},
        )
        logger.success(f"Scraped {len(products)} products from Mathem")
        return self._scrape_result_from_products(
            products,
            location_type="ehandel",
            diagnostics=diagnostics,
        )

    def _retry_after_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=timezone.utc)
                    return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
                except (TypeError, ValueError):
                    pass
        return MATHEM_RETRY_BACKOFF_SECONDS * attempt

    async def _get_with_backoff(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        """GET with polite retry/backoff for Mathem throttling and transient errors."""
        last_response: Optional[httpx.Response] = None
        for attempt in range(1, MATHEM_MAX_RETRIES + 1):
            response = await client.get(url)
            last_response = response
            if response.status_code not in MATHEM_RETRY_STATUSES:
                return response
            if attempt >= MATHEM_MAX_RETRIES:
                return response

            delay = self._retry_after_delay(response, attempt)
            logger.debug(
                "Mathem store retry "
                f"(status={response.status_code}, attempt={attempt}/{MATHEM_MAX_RETRIES}, "
                f"sleep={delay:.2f}s): {url}"
            )
            await asyncio.sleep(delay)
        return last_response

    async def _scrape_discounts_http(self) -> Tuple[List[Dict], Dict[str, Any]]:
        """Scrape discount products from Mathem's server-rendered Next.js data."""
        diagnostics: Dict[str, Any] = {"data_path": "next_data_product_grid"}

        try:
            async with httpx.AsyncClient(
                headers=MATHEM_HTTP_HEADERS,
                timeout=30,
                follow_redirects=True,
                event_hooks={"request": [ssrf_safe_event_hook]},
            ) as client:
                response = await self._get_with_backoff(client, self.discounts_url)
                diagnostics["http_status"] = response.status_code
                response.raise_for_status()
        except httpx.HTTPError as exc:
            diagnostics["http_error"] = type(exc).__name__
            logger.warning(f"Mathem SSR scrape failed before parsing: {exc}")
            return [], diagnostics

        next_data = extract_mathem_next_data(response.text)
        if not next_data:
            diagnostics["reason"] = "missing_next_data"
            return [], diagnostics

        page_data = find_mathem_discount_page_data(next_data)
        if not page_data:
            diagnostics["reason"] = "missing_product_grid"
            return [], diagnostics

        products, parse_diagnostics = self._parse_ssr_discount_products(page_data)
        diagnostics.update(parse_diagnostics)
        return products, diagnostics

    def _parse_ssr_discount_products(self, page_data: Dict[str, Any]) -> Tuple[List[Dict], Dict[str, Any]]:
        """Parse Mathem discount products from dehydrated Next.js page data."""
        products: List[Dict] = []
        raw_records = iter_mathem_discount_products(page_data)
        skipped = 0

        for raw_record in raw_records:
            try:
                raw_product = mathem_ssr_product_to_raw(raw_record)
                product = self._parse_product(raw_product) if raw_product else None
                if product:
                    products.append(product)
                else:
                    skipped += 1
            except Exception as exc:
                skipped += 1
                logger.debug(f"Failed to parse Mathem SSR product: {exc}")

        diagnostics = {
            "raw_product_count": len(raw_records),
            "parsed_product_count": len(products),
            "skipped_product_count": skipped,
        }
        return products, diagnostics

    async def _scrape_discounts_playwright(self) -> List[Dict]:
        """Scrape discount products using Playwright with polite delays."""

        products = []

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(locale='sv-SE')
                    page = await context.new_page()

                    logger.debug(f"Navigating to {self.discounts_url}")
                    await page.goto(self.discounts_url, timeout=60000)
                    await page.wait_for_load_state("networkidle", timeout=30000)

                    # Polite delay after page load
                    logger.debug(f"Waiting {self.PAGE_LOAD_DELAY}s after page load...")
                    await asyncio.sleep(self.PAGE_LOAD_DELAY)

                    # Scroll to load all products (lazy loading) with polite delays
                    logger.info("Scrolling to load all products (with delays)...")
                    prev_count = 0
                    no_new_count = 0

                    for i in range(100):  # safety limit only
                        count = await page.locator('[data-testid="product-tile"]').count()

                        if count == prev_count:
                            no_new_count += 1
                            if no_new_count >= 3:
                                logger.debug(f"No new products after 3 consecutive scrolls, stopping at {count}")
                                break
                        else:
                            no_new_count = 0

                        prev_count = count
                        await page.evaluate('window.scrollBy(0, 1000)')

                        # Polite delay between scrolls
                        await asyncio.sleep(self.SCROLL_DELAY)

                        if i % 5 == 0:
                            logger.debug(f"  Scroll {i}: {count} products loaded")
                            await self._report_progress(
                                progress=min(45, 10 + i),
                                message_key="ws.fetching_product_progress",
                                message_params={"count": count},
                            )

                    total_tiles = await page.locator('[data-testid="product-tile"]').count()
                    logger.info(f"Found {total_tiles} product tiles on page")

                    # Extract product data from DOM
                    raw_products = await self._extract_products_from_dom(page)
                    logger.info(f"Extracted {len(raw_products)} raw products from DOM")
                    await self._report_progress(
                        progress=50,
                        message_key="ws.fetched_products",
                        message_params={"count": len(raw_products)},
                    )

                    # Convert to standard product format
                    for raw in raw_products:
                        try:
                            product = self._parse_product(raw)
                            if product:
                                products.append(product)
                        except Exception as e:
                            logger.debug(f"Failed to parse product: {e}")
                            continue

                    # Enrich products missing data with JSON-LD.
                    products = await self._enrich_with_jsonld(page, products)
                finally:
                    await browser.close()

        except Exception as e:
            logger.error(f"Playwright scraping failed: {e}")

        return products

    async def _extract_products_from_dom(self, page) -> List[Dict]:
        """Extract product data from DOM elements."""

        return await page.evaluate(r'''() => {
            const results = [];
            const tiles = document.querySelectorAll('[data-testid="product-tile"]');

            // Patterns to skip when finding product name
            const skipPatterns = [
                /^Välj\s*&\s*blanda$/i,
                /^\d+\s+för\s+[\d,]+\s*kr$/i,  // Multi-buy
                /^[\d,]+\s*kr$/i,               // Price
                /^[\d,]+\s*kr\s*\//,            // Per unit price
                /^Extrapris$/i,
                /^Prisnedsatt$/i,
                /^Nyhet$/i,
                /^Toppsäljare$/i,
                /^Max\s+\d+\s+varor?$/i,        // "Max 2 varor"
                /^-?\d+\s*%$/i,                 // Discount percentage: "-10%", "10%"
                /^Spara\s+\d+/i,                // "Spara 10 kr"
            ];

            tiles.forEach((tile) => {
                const text = tile.innerText;
                const lines = text.split('\n').map(l => l.trim()).filter(l => l);

                // Get link and image
                const linkEl = tile.querySelector('a[href*="/products/"]');
                const imgEl = tile.querySelector('img');
                const url = linkEl ? linkEl.href : null;

                // Extract name from URL as fallback
                let urlName = null;
                if (url) {
                    const match = url.match(/\/products\/\d+-(.+?)\/?$/);
                    if (match) {
                        urlName = match[1]
                            .replace(/-/g, ' ')
                            .replace(/\s+/g, ' ')
                            .trim();
                    }
                }

                const product = {
                    url: url,
                    url_name: urlName,
                    img_alt: imgEl ? imgEl.alt : null,
                    image: imgEl ? imgEl.src : null,
                    raw_lines: lines
                };

                // Parse each line
                for (const line of lines) {
                    // Multi-buy: "4 för 99 kr"
                    if (/^\d+\s+för\s+[\d,]+\s*kr$/i.test(line)) {
                        const match = line.match(/(\d+)\s+för\s+([\d,]+)/i);
                        if (match) {
                            product.multi_buy_quantity = parseInt(match[1]);
                            product.multi_buy_price = parseFloat(match[2].replace(',', '.'));
                        }
                    }
                    // Price: "36,95 kr"
                    else if (/^[\d,]+\s*kr$/i.test(line)) {
                        if (!product.price) {
                            product.price = parseFloat(line.replace(',', '.').replace(/\s*kr/i, ''));
                        }
                    }
                    // Per unit price: "153,96 kr /kg"
                    else if (/^[\d,]+\s*kr\s*\//.test(line)) {
                        const match = line.match(/([\d,]+)\s*kr\s*\/(kg|st|l|förp|liter)/i);
                        if (match) {
                            product.price_per_unit = parseFloat(match[1].replace(',', '.'));
                            product.unit = match[2].toLowerCase();
                        }
                    }
                    // Size and brand: "240 g, Dafgårds"
                    else if (/^\d+[\s,]*(g|kg|ml|l|cl|st)\s*,/.test(line)) {
                        const match = line.match(/^([\d,\s]+(?:g|kg|ml|l|cl|st))\s*,\s*(.+)$/i);
                        if (match) {
                            product.size = match[1].trim();
                            product.brand = match[2].trim();
                        }
                    }
                    // Just size: "500 g"
                    else if (/^\d+[\s,]*(g|kg|ml|l|cl|st)$/.test(line) && !product.size) {
                        product.size = line;
                    }
                }

                // Find product name - first line that doesn't match skip patterns
                for (const line of lines) {
                    if (skipPatterns.some(p => p.test(line))) continue;
                    if (/^\d+[\s,]*(g|kg|ml|l|cl|st)/.test(line)) continue;  // Skip size line
                    if (line.length < 4) continue;

                    product.name = line;
                    break;
                }

                // Fallback to image alt or URL name
                if (!product.name || /^(Extrapris|Max\s+\d+)/i.test(product.name)) {
                    product.name = product.img_alt || product.url_name || null;
                }

                if (product.name && product.price) {
                    results.push(product);
                }
            });

            return results;
        }''')

    async def _enrich_with_jsonld(self, page, products: List[Dict]) -> List[Dict]:
        """
        Enrich products with original price, brand, and description from product pages.

        Mathem shows "Ursprungspriset var: X kr" on product pages but not on listings.
        Uses the same browser session and adds polite delays between requests.
        """

        # Find products that need enrichment:
        # 1. Products without savings (need original price)
        # 2. Products without brand
        products_to_enrich = [
            (i, p) for i, p in enumerate(products)
            if (p.get('savings', 0) == 0 or not p.get('brand')) and p.get('product_url')
        ]

        if not products_to_enrich:
            logger.debug("All products have complete data, skipping enrichment")
            return products

        to_enrich = self._select_products_to_enrich(products_to_enrich)
        if not to_enrich:
            logger.debug("Product enrichment disabled, skipping product page lookups")
            return products

        if len(to_enrich) == len(products_to_enrich):
            logger.info(f"Enriching {len(to_enrich)} products with original prices (with delays)...")
        else:
            logger.info(
                f"Enriching {len(to_enrich)}/{len(products_to_enrich)} products "
                "with original prices (with delays)..."
            )

        enriched_count = 0
        started_at = asyncio.get_event_loop().time()
        await self._report_progress(
            progress=50,
            message_key="ws.enriching_products",
            message_params={
                "done": 0,
                "total": len(to_enrich),
                "eta": self._format_progress_eta(len(to_enrich) * self.ENRICH_DELAY),
            },
        )

        for idx, (product_idx, product) in enumerate(to_enrich):
            try:
                url = product['product_url']

                # Navigate to product page
                await page.goto(url, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=15000)

                # Extract price and product data from page
                page_data = await page.evaluate(r'''() => {
                    const result = {
                        original_price: null,
                        current_price: null,
                        brand: null,
                        description: null
                    };

                    // Find "Ursprungspriset var: X kr" pattern
                    const allText = document.body.innerText;

                    // Original price pattern
                    const origMatch = allText.match(/Ursprungspriset\s+var:\s*([\d,]+)\s*kr/i);
                    if (origMatch) {
                        result.original_price = parseFloat(origMatch[1].replace(',', '.'));
                    }

                    // Current price pattern
                    const currMatch = allText.match(/Nuvarande\s+pris\s+är:\s*([\d,]+)\s*kr/i);
                    if (currMatch) {
                        result.current_price = parseFloat(currMatch[1].replace(',', '.'));
                    }

                    // JSON-LD for brand and description
                    const script = document.querySelector('script[type="application/ld+json"]');
                    if (script) {
                        try {
                            const data = JSON.parse(script.textContent);
                            if (data["@type"] === "Product") {
                                result.brand = data.brand || null;
                                result.description = data.description || null;
                            }
                        } catch (e) {}
                    }

                    return result;
                }''')

                if page_data:
                    updated = False

                    # Update original price if found
                    if page_data.get('original_price') and product.get('savings', 0) == 0:
                        orig_price = page_data['original_price']
                        curr_price = product['price']

                        if orig_price > curr_price:
                            products[product_idx]['original_price'] = round(orig_price, 2)
                            products[product_idx]['savings'] = round(orig_price - curr_price, 2)
                            updated = True

                    # Update brand if missing
                    if page_data.get('brand') and not product.get('brand'):
                        products[product_idx]['brand'] = page_data['brand']
                        updated = True

                    # Update description if missing
                    if page_data.get('description') and not product.get('description'):
                        desc = page_data['description']
                        desc = desc.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                        products[product_idx]['description'] = desc
                        updated = True

                    if updated:
                        enriched_count += 1

                # Polite delay before next request
                await asyncio.sleep(self.ENRICH_DELAY)

                # Progress logging
                if (idx + 1) % 10 == 0:
                    logger.debug(f"  Enriched {idx + 1}/{len(to_enrich)} products...")
                    elapsed = max(asyncio.get_event_loop().time() - started_at, 0.001)
                    done = idx + 1
                    remaining = (len(to_enrich) - done) * elapsed / done
                    await self._report_progress(
                        progress=min(64, 50 + int((done / len(to_enrich)) * 14)),
                        message_key="ws.enriching_products",
                        message_params={
                            "done": done,
                            "total": len(to_enrich),
                            "eta": self._format_progress_eta(remaining),
                        },
                    )

            except Exception as e:
                logger.debug(f"Failed to enrich product {product.get('name', 'unknown')}: {e}")
                await asyncio.sleep(self.ENRICH_DELAY)  # Still delay on error
                continue

        logger.info(f"Enriched {enriched_count} products with JSON-LD data")
        await self._report_progress(
            progress=64,
            message_key="ws.enriching_products",
            message_params={
                "done": len(to_enrich),
                "total": len(to_enrich),
                "eta": "0 s",
            },
        )
        return products

    def _select_products_to_enrich(
        self,
        products_to_enrich: List[tuple[int, Dict]],
    ) -> List[tuple[int, Dict]]:
        """Apply the optional enrich cap while defaulting to full enrichment."""
        if self.MAX_ENRICH_PRODUCTS is None:
            return list(products_to_enrich)
        if self.MAX_ENRICH_PRODUCTS <= 0:
            return []
        return list(products_to_enrich[:self.MAX_ENRICH_PRODUCTS])

    def _parse_product(self, raw: dict) -> Optional[Dict]:
        """Convert raw extracted data to standard product format."""

        name = raw.get('name')
        price = raw.get('price')

        if not name or not price:
            return None

        # Clean up the name
        name = self._clean_product_name(name)

        if not name or len(name) < 3:
            return None

        # Calculate unit price for multi-buy
        unit_price = price
        is_multi_buy = False
        multi_buy_quantity = raw.get('multi_buy_quantity')
        multi_buy_price = raw.get('multi_buy_price')

        if multi_buy_quantity and multi_buy_quantity > 0 and multi_buy_price and multi_buy_price > 0:
            is_multi_buy = True
            unit_price = round(multi_buy_price / multi_buy_quantity, 2)

        original_price = raw.get('original_price')
        try:
            original_price = float(original_price) if original_price is not None else None
        except (TypeError, ValueError):
            original_price = None
        if not original_price or original_price < unit_price:
            original_price = price

        # Determine unit
        unit = raw.get('unit', 'st')
        if unit == 'liter':
            unit = 'l'

        # Guess category
        category = self._guess_category(name)

        # Normalize brand to uppercase for consistent filtering
        brand = raw.get('brand')
        if brand and isinstance(brand, str):
            brand = brand.strip().upper()

        # Weight from size field (e.g., "500 g", "1,5 kg", "750 ml")
        size_str = raw.get('size', '')
        weight_grams = parse_weight(size_str) if size_str else parse_weight(name)

        product = {
            "name": name,
            "price": round(unit_price, 2),
            "original_price": round(original_price, 2),  # Regular price
            "savings": round(max(original_price - unit_price, 0), 2),
            "unit": unit,
            "category": category,
            "image_url": raw.get('image'),
            "product_url": raw.get('url'),
            "brand": brand if brand else None,  # Normalized to uppercase
            "weight_grams": weight_grams,
            "scraped_at": datetime.now(timezone.utc)
        }

        # Add multi-buy info if applicable
        if is_multi_buy:
            product["is_multi_buy"] = True
            product["multi_buy_quantity"] = multi_buy_quantity
            product["multi_buy_total_price"] = multi_buy_price

        return product

    def _clean_product_name(self, name: str) -> str:
        """Clean and normalize product name."""

        if not name:
            return ""

        # Remove common prefixes/suffixes
        name = name.strip()

        # Reject names that are just discount percentages or price indicators
        # e.g., "-10%", "10%", "Spara 15 kr"
        if re.match(r'^-?\d+\s*%$', name):
            return ""
        if re.match(r'^Spara\s+\d+', name, re.IGNORECASE):
            return ""

        # Capitalize first letter of each word properly
        # (URL names are all lowercase)
        if name.islower():
            name = ' '.join(word.capitalize() for word in name.split())

        return name

    def _guess_category(self, product_name: str) -> str:
        """
        Guess product category from name.

        Delegates to shared utility. See languages/sv/category_utils.py.
        """
        return shared_guess_category(product_name)
