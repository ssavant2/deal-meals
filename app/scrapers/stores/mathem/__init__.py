"""
Mathem Store Plugin - E-commerce grocery scraper.

Mathem is Sweden's largest online grocery store with home delivery only.
No physical stores - offers are the same nationwide.

Uses Playwright for scraping since direct HTTP requests are blocked (403).
Includes polite delays and JSON-LD fallback for missing data.
"""

from typing import List, Dict, Optional
from datetime import datetime, timezone
import re
import asyncio
import json
from loguru import logger

from scrapers.stores.base import StorePlugin, StoreConfig, StoreConfigField, StoreScrapeResult
from scrapers.stores.weight_utils import parse_weight
from languages.sv.category_utils import guess_category as shared_guess_category


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
        self.base_url = "https://www.mathem.se"
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
        logger.info("Starting Mathem scraping (with polite delays)...")

        products = await self._scrape_discounts_playwright()

        logger.success(f"Scraped {len(products)} products from Mathem")
        return self._scrape_result_from_products(
            products,
            location_type="ehandel",
        )

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

                    total_tiles = await page.locator('[data-testid="product-tile"]').count()
                    logger.info(f"Found {total_tiles} product tiles on page")

                    # Extract product data from DOM
                    raw_products = await self._extract_products_from_dom(page)
                    logger.info(f"Extracted {len(raw_products)} raw products from DOM")

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

            except Exception as e:
                logger.debug(f"Failed to enrich product {product.get('name', 'unknown')}: {e}")
                await asyncio.sleep(self.ENRICH_DELAY)  # Still delay on error
                continue

        logger.info(f"Enriched {enriched_count} products with JSON-LD data")
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
            "original_price": round(price, 2),  # Regular price
            "savings": round(price - unit_price, 2) if is_multi_buy else 0.0,
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
