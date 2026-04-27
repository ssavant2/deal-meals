"""
Coop Store Plugin

Scrapes offers from Coop stores (physical stores and online).

Coop has multiple store types: Coop, Stora Coop, X-tra, Coop Forum, Coop Konsum, Coop Mini.
Each physical store has its own offer page at:
  https://www.coop.se/butiker-erbjudanden/{store-type}/{store-name}/

E-commerce offers are at:
  https://www.coop.se/handla/aktuella-erbjudanden/

API Research (Feb 2026):
- Hybris eCommerce API: https://external.api.coop.se/ecommerce (requires browser context)
- Store API: https://proxy.api.coop.se/external/store/
- DKE Offers API: https://external.api.coop.se/dke/offers/
- Product Search API: https://external.api.coop.se/personalization/search/products
  (works with httpx + subscription key, used for price enrichment)
- Offer APIs return 404 on direct calls - need Playwright for offer scraping
"""

from typing import List, Dict, Optional
from scrapers.stores.base import StorePlugin, StoreConfig, StoreConfigField, StoreScrapeResult
from languages.sv.category_utils import guess_category as shared_guess_category
from scrapers.stores.weight_utils import parse_weight
from loguru import logger
from languages.sv.normalization import fix_swedish_chars
from constants_timeouts import HTTP_TIMEOUT, PAGE_LOAD_TIMEOUT, PAGE_NETWORK_IDLE_TIMEOUT
import httpx
import re
from datetime import datetime, timezone
from utils.security import ssrf_safe_event_hook
import asyncio


class CoopStore(StorePlugin):
    """
    Coop Store Plugin

    Supports:
    - Physical store offers (via store-specific pages)
    - E-commerce offers (via coop.se/handla/aktuella-erbjudanden/)
    """

    # Coop store types from sitemap
    STORE_TYPES = ["coop", "stora-coop", "x-tra", "coop-forum", "coop-konsum", "coop-mini"]

    # Obfuscated CSS class for brand extraction (Coop may change this at any deploy)
    BRAND_CSS_CLASS = "span.q5vMS42j"

    def __init__(self):
        self.base_url = "https://www.coop.se"
        self.offers_url = f"{self.base_url}/handla/aktuella-erbjudanden/"
        self.sitemap_url = f"{self.base_url}/sitemap_pages.xml"
        self._store_cache: List[Dict] = []  # Cache for store list

    @property
    def config(self) -> StoreConfig:
        return StoreConfig(
            id="coop",
            name="Coop",
            logo="/scrapers/stores/coop/logo.svg",
            color="#0a9f4f",  # Coop green
            url="https://www.coop.se",
            enabled=True,
            has_credentials=False,
            description="Tillsammans gör vi skillnad"
        )

    @property
    def estimated_scrape_time(self) -> int:
        """Coop scraping estimate."""
        return 180  # 3 minutes

    def get_config_fields(self) -> List[StoreConfigField]:
        """Define Coop configuration fields."""
        return [
            StoreConfigField(
                key="location_type",
                label="Välj typ",
                field_type="radio",
                options=[
                    {
                        "value": "ehandel",
                        "label": "E-handel",
                        "suffix": "(Hemkörning)",
                        "description": "Erbjudanden för din hemadress"
                    },
                    {
                        "value": "butik",
                        "label": "Butik",
                        "description": "Erbjudanden för en specifik Coop-butik"
                    }
                ],
                default="ehandel"
            ),
            StoreConfigField(
                key="location_search",
                label="Sök butik (stad eller butiksnamn)",
                field_type="search",
                placeholder="t.ex. göteborg, avenyn, stora coop...",
                depends_on={"field": "location_type", "value": "butik"}
            )
        ]

    async def search_locations(self, query: str) -> List[Dict]:
        """
        Search for Coop store locations.

        Uses sitemap parsing to find stores matching the query.
        """
        cache_key = self._build_location_search_cache_key("physical", query)

        async def load_locations() -> List[Dict]:
            logger.info(f"Searching Coop stores for: {query}")

            # Load store list if not cached
            if not self._store_cache:
                self._store_cache = await self._load_stores_from_sitemap()

            query_lower = self._normalize_search(query.lower())
            query_words = query_lower.split()

            # Filter stores matching query
            matching_stores = []
            for store in self._store_cache:
                searchable = self._normalize_search(
                    f"{store['name']} {store.get('city', '')} {store.get('store_type', '')}"
                )

                # Match ALL query words
                if all(word in searchable for word in query_words):
                    matching_stores.append(store)

            # Sort by relevance (exact name match first)
            def sort_key(store):
                exact_matches = sum(1 for word in query_words if word in self._normalize_search(store["name"]))
                return (-exact_matches, store["name"])

            matching_stores.sort(key=sort_key)

            logger.info(f"Found {len(matching_stores)} Coop stores matching '{query}'")
            return matching_stores[:50]  # Return up to 50 results

        return await self._get_or_cache_location_search(cache_key, load_locations)

    async def _load_stores_from_sitemap(self) -> List[Dict]:
        """
        Load all Coop stores from sitemap.

        Parses sitemap_pages.xml to extract store URLs and metadata.
        """
        logger.info("Loading Coop stores from sitemap...")
        stores = []

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/xml, text/xml, */*",
            }

            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, event_hooks={"request": [ssrf_safe_event_hook]}) as client:
                response = await client.get(self.sitemap_url, headers=headers)

                if response.status_code != 200:
                    logger.error(f"Failed to fetch sitemap: {response.status_code}")
                    return []

                # Parse sitemap XML
                content = response.text

                # Extract store URLs using regex (faster than XML parsing for simple extraction)
                # Pattern: butiker-erbjudanden/{store-type}/{store-name}/
                pattern = r'<loc>https://www\.coop\.se/butiker-erbjudanden/([^/]+)/([^/]+)/</loc>'
                matches = re.findall(pattern, content)

                for store_type, store_slug in matches:
                    # Skip the main category pages
                    if store_slug == store_type:
                        continue

                    # Parse store name from slug
                    store_name = self._format_store_name(store_slug)
                    city = self._extract_city_from_slug(store_slug)

                    # Map store type to display name
                    type_labels = {
                        "coop": "Coop",
                        "stora-coop": "Stora Coop",
                        "x-tra": "Coop X-tra",
                        "coop-forum": "Coop Forum",
                        "coop-konsum": "Coop Konsum",
                        "coop-mini": "Coop Mini",
                    }
                    type_label = type_labels.get(store_type, store_type.title())

                    stores.append({
                        "id": f"{store_type}/{store_slug}",
                        "name": store_name,
                        "address": f"{city} ({type_label})" if city else type_label,
                        "type": "butik",
                        "store_type": store_type,
                        "url_slug": store_slug,
                        "city": city,
                    })

                logger.success(f"Loaded {len(stores)} Coop stores from sitemap")
                return stores

        except Exception as e:
            logger.error(f"Error loading stores from sitemap: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return []

    def _normalize_search(self, text: str) -> str:
        """Normalize text for search matching (handle Swedish chars)."""
        replacements = {
            "å": "a", "ä": "a", "ö": "o",
            "é": "e", "è": "e", "ü": "u"
        }
        result = text.lower()
        for char, replacement in replacements.items():
            result = result.replace(char, replacement)
        return result

    def _format_store_name(self, slug: str) -> str:
        """Format store slug to proper Swedish name."""
        # Start with title case
        name = slug.replace("-", " ").title()

        # Fix "Coop" capitalization
        name = re.sub(r'\bCoop\b', 'Coop', name, flags=re.IGNORECASE)

        # Swedish character fixes
        replacements = {
            " Ostra ": " Östra ",
            " Vastra ": " Västra ",
            " Norra ": " Norra ",
            " Sodra ": " Södra ",
            " Sjo": " Sjö",
            " As ": " Ås ",
            " Ang": " Äng",
            "Goteborg": "Göteborg",
            "Malmo": "Malmö",
            "Linkoping": "Linköping",
            "Norrkoping": "Norrköping",
            "Orebro": "Örebro",
            "Vasteras": "Västerås",
            "Jonkoping": "Jönköping",
            "Gavle": "Gävle",
            "Boras": "Borås",
            "Vaxjo": "Växjö",
            "Umea": "Umeå",
            "Lulea": "Luleå",
            "Ostersund": "Östersund",
            "Sundsvall": "Sundsvall",
            "Frolunda": "Frölunda",
            "Molndal": "Mölndal",
            "Hogsbo": "Högsbo",
            "Kungalv": "Kungälv",
            "Trollhattan": "Trollhättan",
            "Skovde": "Skövde",
            "Hassleholm": "Hässleholm",
            "Angelholm": "Ängelholm",
            "Karlskrona": "Karlskrona",
        }

        for old, new in replacements.items():
            name = name.replace(old, new)
            # Also try lowercase version
            name = name.replace(old.lower(), new)

        return name

    # Scraping artifacts that appear as product names but aren't real products
    _NOISE_NAMES = {
        'ny', 'nyhet', 'new',          # "New" badges
        'kampanj', 'erbjudande',        # Promotion labels
        'utvald', 'utvalt',             # "Selected" labels
    }
    _NOISE_PATTERNS = [
        r'^\d+-årsgräns$',             # Age restriction labels ("15-årsgräns")
        r'^\d+$',                       # Pure numbers
    ]
    _NONFOOD_HARDGOOD_KEYWORDS = {
        "air fryer", "bagagetag", "cafeset", "dammsug", "grill", "grillolja",
        "grillset", "grillspett", "grillwipes", "handske", "hårfärg",
        "kabel", "kylväska", "lövräfsa", "mugg", "måttkanna", "non-stick",
        "parasoll", "picknickfilt", "pizzaskärare", "pizzasten", "pläd",
        "popcornskål", "redskapsset", "resetillbehör", "servettring",
        "solcells", "spade", "spruta", "stekpanna", "strykjärn", "tallrik",
        "termos", "trädgård", "uppbindningssnöre", "yoghurtbägare",
    }

    def _is_noise_product(self, name: str) -> bool:
        """Check if a scraped name is a scraping artifact, not a real product."""
        name_lower = name.strip().lower()
        if name_lower in self._NOISE_NAMES:
            return True
        if len(name_lower) <= 2:
            return True
        return any(re.match(p, name_lower) for p in self._NOISE_PATTERNS)

    def _extract_city_from_slug(self, slug: str) -> str:
        """Extract city name from store slug if present."""
        # Common city patterns in Coop store names
        # e.g., "coop-avenyn" -> might be in Göteborg
        # e.g., "stora-coop-orebro" -> Örebro

        # Check for known cities in slug
        cities = {
            "goteborg": "Göteborg",
            "stockholm": "Stockholm",
            "malmo": "Malmö",
            "uppsala": "Uppsala",
            "linkoping": "Linköping",
            "orebro": "Örebro",
            "vasteras": "Västerås",
            "norrkoping": "Norrköping",
            "jonkoping": "Jönköping",
            "gavle": "Gävle",
            "boras": "Borås",
            "umea": "Umeå",
            "lulea": "Luleå",
            "sundsvall": "Sundsvall",
            "karlstad": "Karlstad",
            "halmstad": "Halmstad",
        }

        slug_lower = slug.lower()
        for city_slug, city_name in cities.items():
            if city_slug in slug_lower:
                return city_name

        return ""

    async def scrape_offers(self, credentials: Optional[Dict] = None) -> StoreScrapeResult:
        """
        Scrape offers from Coop.

        For butik: Navigates to store page and extracts offers
        For e-handel: Navigates to offers page with postal code selection
        """
        logger.info("Starting Coop scraping...")
        logger.debug(f"Credentials received: {credentials}")

        location_type = credentials.get("location_type", "ehandel") if credentials else "ehandel"
        failure_reason = None

        if location_type == "butik":
            location_id = credentials.get("location_id") if credentials else None

            if location_id:
                # location_id format: "store-type/store-slug" e.g., "coop/coop-avenyn"
                store_url = f"{self.base_url}/butiker-erbjudanden/{location_id}/"
                logger.info(f"Scraping physical store: {store_url}")
                products = await self._scrape_physical_store(store_url)
            else:
                logger.error("No store selected for Coop butik scraping")
                failure_reason = "missing_store_selection"
                products = []
        else:
            # E-handel
            logger.info("Scraping Coop e-commerce offers")

            # Get postal code from user preferences
            postal_code = None
            try:
                from database import get_db_session
                from sqlalchemy import text

                with get_db_session() as db:
                    result = db.execute(text(
                        "SELECT delivery_postal_code FROM user_preferences LIMIT 1"
                    )).fetchone()

                    if result and result[0]:
                        postal_code = result[0]
                        logger.info(f"Using postal code: {postal_code}")
            except Exception as e:
                logger.warning(f"Could not fetch postal code: {e}")

            products = await self._scrape_ehandel_offers(postal_code)

        # Filter out certification logos (scraping artifacts like "Nyckelhålet", "EU Lövet")
        # These are badge names that get scraped as products - not real products
        # Note: We keep ALL real products (including hygiene/household) - they get categorized
        if products:
            original_count = len(products)
            products = self._filter_certification_logos(products)
            if original_count != len(products):
                logger.info(f"Removed {original_count - len(products)} certification logo artifacts")

            deduped_count_before = len(products)
            products = self._dedupe_products(products)
            if deduped_count_before != len(products):
                logger.info(
                    f"Deduplicated {deduped_count_before - len(products)} Coop products "
                    f"({deduped_count_before} -> {len(products)})"
                )

            if location_type in {"ehandel", "butik"}:
                card_count = int((getattr(self, "_scrape_meta", {}) or {}).get("card_count") or 0)
                if card_count > 0:
                    base_count = min(card_count, len(products))
                    self._scrape_meta = {
                        "base_count": base_count,
                        "variant_count": max(len(products) - base_count, 0),
                        "card_count": card_count,
                    }

        # Warn if brand extraction may have stopped working (CSS class changed)
        if products:
            brands_found = sum(1 for p in products if "," in p.get("name", ""))
            if brands_found == 0:
                logger.warning(
                    f"No brands extracted from {len(products)} Coop products. "
                    f"CSS class '{self.BRAND_CSS_CLASS}' may have changed — check coop.se HTML."
                )

        logger.success(f"Scraped {len(products)} products from Coop ({location_type})")
        return self._scrape_result_from_products(
            products,
            location_type=location_type,
            reason=failure_reason,
        )

    def _build_product_dedupe_key(self, product: Dict) -> tuple:
        """Build a stable Coop-local key for collapsing duplicate logical products."""
        product_url = (product.get("product_url") or "").strip()
        if product_url:
            return ("product_url", product_url)

        name = fix_swedish_chars((product.get("name") or "").strip()).lower()
        category = (product.get("category") or "").strip().lower()
        unit = (product.get("unit") or "").strip().lower()
        weight_grams = product.get("weight_grams")
        weight_key = round(float(weight_grams), 1) if isinstance(weight_grams, (int, float)) else weight_grams
        return ("content", name, category, unit, weight_key)

    def _merge_duplicate_product_rows(self, kept: Dict, candidate: Dict) -> Dict:
        """Choose the better duplicate row and preserve sane enrichment when possible."""
        kept_price = float(kept.get("price") or 0)
        candidate_price = float(candidate.get("price") or 0)
        kept_savings = float(kept.get("savings") or 0)
        candidate_savings = float(candidate.get("savings") or 0)

        if candidate_price and (
            kept_price == 0
            or candidate_price < kept_price
            or (
                candidate_price == kept_price
                and candidate_savings > kept_savings
            )
        ):
            primary = dict(candidate)
            secondary = kept
        else:
            primary = dict(kept)
            secondary = candidate

        primary_price = float(primary.get("price") or 0)
        primary_original = float(primary.get("original_price") or 0)
        secondary_original = float(secondary.get("original_price") or 0)
        primary_savings = float(primary.get("savings") or 0)

        should_upgrade_original = (
            primary_price > 0
            and secondary_original > primary_price
            and (primary_original <= primary_price or primary_savings <= 0)
            and (secondary_original - primary_price) <= primary_price
        )
        if should_upgrade_original:
            primary["original_price"] = round(secondary_original, 2)
            primary["savings"] = round(secondary_original - primary_price, 2)

        if not primary.get("product_url") and secondary.get("product_url"):
            primary["product_url"] = secondary["product_url"]
        if not primary.get("image_url") and secondary.get("image_url"):
            primary["image_url"] = secondary["image_url"]
        if not primary.get("weight_grams") and secondary.get("weight_grams"):
            primary["weight_grams"] = secondary["weight_grams"]

        return primary

    def _dedupe_products(self, products: List[Dict]) -> List[Dict]:
        """Collapse duplicate Coop products to one best row per logical product."""
        deduped: Dict[tuple, Dict] = {}
        order: List[tuple] = []

        for product in products:
            key = self._build_product_dedupe_key(product)
            existing = deduped.get(key)
            if existing is None:
                deduped[key] = dict(product)
                order.append(key)
                continue
            deduped[key] = self._merge_duplicate_product_rows(existing, product)

        return [deduped[key] for key in order]

    # ==================== E-COMMERCE SCRAPING ====================

    async def _scrape_ehandel_offers(self, postal_code: Optional[str] = None) -> List[Dict]:
        """
        Scrape e-commerce offers with Playwright.

        Flow:
        1. Navigate to offers page
        2. Handle postal code popup if needed
        3. Loop through all pages (pagination)
        4. For each page, extract products including variants ("Se X varor")
        """
        all_products = []
        total_base = 0
        total_variants = 0

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(locale='sv-SE')
                page = await context.new_page()

                logger.debug(f"Navigating to {self.offers_url}")
                await page.goto(self.offers_url, timeout=PAGE_LOAD_TIMEOUT)
                await page.wait_for_load_state("networkidle", timeout=PAGE_NETWORK_IDLE_TIMEOUT)
                await asyncio.sleep(1)

                # Handle postal code popup if needed
                if postal_code:
                    await self._handle_postal_code_popup(page, postal_code)

                # Close any remaining popups and remove cookie wrapper
                await self._close_popups(page)
                try:
                    await page.evaluate('document.getElementById("cmpwrapper")?.remove()')
                except Exception as e:
                    logger.debug(f"Could not remove cmpwrapper: {e}")

                # Determine total number of pages
                max_pages = min(await self._get_total_pages(page), 100)  # Safety cap
                logger.info(f"E-commerce has {max_pages} pages to scrape")

                total_cards = 0

                # Scrape each page
                for page_num in range(1, max_pages + 1):
                    if page_num > 1:
                        # Navigate to next page
                        page_url = f"{self.offers_url}?page={page_num}"
                        logger.info(f"Navigating to page {page_num}/{max_pages}")
                        await page.goto(page_url, timeout=PAGE_LOAD_TIMEOUT)
                        await page.wait_for_load_state("domcontentloaded", timeout=PAGE_NETWORK_IDLE_TIMEOUT)
                        await asyncio.sleep(0.5)

                        # Remove cookie wrapper again
                        try:
                            await page.evaluate('document.getElementById("cmpwrapper")?.remove()')
                        except Exception as e:
                            logger.debug(f"Could not remove cmpwrapper on page {page_num}: {e}")

                    # Scroll to load all products on this page
                    await self._scroll_to_load_all(page)
                    total_cards += len(await page.query_selector_all('article'))

                    # Extract products from this page (including variants)
                    page_products, page_base, page_variants = await self._extract_ehandel_products_with_variants(page)
                    all_products.extend(page_products)
                    total_base += page_base
                    total_variants += page_variants

                    logger.info(f"Page {page_num}: extracted {len(page_products)} products (total: {len(all_products)})")

                await context.close()
                await browser.close()

        except Exception as e:
            logger.error(f"Error in e-commerce scraping: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return all_products

        self._scrape_meta = {
            "base_count": total_base,
            "variant_count": total_variants,
            "card_count": total_cards,
        }
        return all_products

    async def _get_total_pages(self, page) -> int:
        """Determine total number of pages from pagination."""
        try:
            # Look for pagination links
            # Format: ?page=N
            pagination_links = await page.query_selector_all('a[href*="page="]')

            max_page = 1
            for link in pagination_links:
                href = await link.get_attribute('href')
                if href:
                    match = re.search(r'page=(\d+)', href)
                    if match:
                        page_num = int(match.group(1))
                        max_page = max(max_page, page_num)

            return max_page

        except Exception as e:
            logger.debug(f"Could not determine total pages: {e}")
            return 1

    async def _extract_ehandel_products_with_variants(self, page) -> tuple:
        """
        Extract products from e-commerce page, including variants.

        For products with "Se X varor" button, expands and extracts individual variants.
        Returns (products, base_count, variant_count).
        """
        products = []

        try:
            articles = await page.query_selector_all('article')
            logger.debug(f"Found {len(articles)} articles on e-commerce page")

            # Phase 1: Extract single products (no DOM interaction needed)
            # Also collect indices of variant articles for phase 2
            variant_indices = []
            for i, article in enumerate(articles):
                try:
                    variant_btn = await article.query_selector('button:has-text("Se")')
                    if variant_btn:
                        btn_text = await variant_btn.text_content()
                        if btn_text and "varor" in btn_text.lower():
                            variant_indices.append(i)
                            continue

                    product = await self._extract_single_product(article)
                    if product:
                        products.append(product)

                except Exception as e:
                    logger.debug(f"Error extracting e-commerce product: {e}")
                    continue

            base_count = len(products)

            # Phase 2: Process variant modals (re-query articles each time
            # because React re-renders the DOM after modal open/close)
            for idx in variant_indices:
                try:
                    # Re-query all articles to get fresh DOM references
                    fresh_articles = await page.query_selector_all('article')
                    if idx >= len(fresh_articles):
                        continue

                    article = fresh_articles[idx]
                    variant_btn = await article.query_selector('button:has-text("Se")')
                    if not variant_btn:
                        continue

                    variant_products = await self._extract_ehandel_variants(
                        page, variant_btn, article
                    )
                    products.extend(variant_products)

                except Exception as e:
                    logger.debug(f"Error extracting e-commerce variant at index {idx}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error extracting e-commerce products: {e}")
            base_count = len(products)

        variant_count = len(products) - base_count
        return products, base_count, variant_count

    async def _extract_ehandel_variants(self, page, variant_btn, parent_article) -> List[Dict]:
        """
        Extract individual product variants from e-commerce "Se X varor" modal.

        E-commerce modals show full product cards with individual prices.
        """
        products = []

        try:
            # Get parent offer price info (shared across variants)
            parent_text = await parent_article.text_content()

            # Extract offer price from parent
            offer_price = 0.0
            is_multi_buy = False
            multi_buy_quantity = 1
            multi_buy_total = 0.0

            # Multi-buy pattern: "2 för 65 kr"
            multi_buy_match = re.search(
                r'(\d+)\s*för\s*(\d+)(?:[,.](\d{1,2}))?\s*kr',
                parent_text,
                re.IGNORECASE
            )
            if multi_buy_match:
                is_multi_buy = True
                multi_buy_quantity = int(multi_buy_match.group(1))
                whole = multi_buy_match.group(2)
                decimal = multi_buy_match.group(3) if multi_buy_match.group(3) else "00"
                decimal = decimal.ljust(2, '0')[:2]
                multi_buy_total = float(f"{whole}.{decimal}")
                offer_price = multi_buy_total / multi_buy_quantity

            # Extract original price from parent text (always per-piece "Ord. pris X kr")
            original_price = offer_price
            ord_match = re.search(
                r'Ord\.?\s*pris\s+(\d+)(?:[,.](\d{1,2}))?\s*kr',
                parent_text,
                re.IGNORECASE
            )
            if ord_match:
                whole = ord_match.group(1)
                decimal = ord_match.group(2) if ord_match.group(2) else "00"
                decimal = decimal.ljust(2, '0')[:2]
                original_price = float(f"{whole}.{decimal}")

            if offer_price == 0:
                # Try single price pattern
                single_match = re.search(
                    r'(\d+)(?:[,.](\d{1,2}))?\s*kr/st',
                    parent_text,
                    re.IGNORECASE
                )
                if single_match:
                    whole = single_match.group(1)
                    decimal = single_match.group(2) if single_match.group(2) else "00"
                    decimal = decimal.ljust(2, '0')[:2]
                    offer_price = float(f"{whole}.{decimal}")
                    if original_price == 0:
                        original_price = offer_price

            if offer_price == 0:
                logger.debug("Could not extract price from e-commerce parent article")
                return []

            # Click button to open modal and wait for it to appear.
            # Coop sometimes needs the card scrolled into view, and a force-click
            # can still race ahead of the dialog content render.
            dialog = None
            try:
                await variant_btn.scroll_into_view_if_needed()
            except Exception:
                pass

            for attempt in range(2):
                try:
                    if attempt == 0:
                        await variant_btn.click(force=True)
                    else:
                        await asyncio.sleep(0.2)
                        await variant_btn.click()
                    dialog = await page.wait_for_selector('[role="dialog"]', timeout=3000)
                    if dialog:
                        break
                except Exception:
                    dialog = None
            if not dialog:
                logger.debug("No dialog found after clicking variant button")
                return []

            # Coop variant cards often render a fraction of a second after the dialog
            # itself appears, so wait for the card list before querying it.
            try:
                await dialog.wait_for_selector('li article, article.ohKiwh8z, article', timeout=2500)
                await asyncio.sleep(0.3)
            except Exception:
                logger.debug("Dialog opened but variant articles did not appear in time")

            # Find product articles in the modal
            modal_articles = await dialog.query_selector_all('li article')
            if not modal_articles:
                modal_articles = await dialog.query_selector_all('article.ohKiwh8z, article')

            logger.debug(f"Found {len(modal_articles)} variants in e-commerce modal")

            for modal_article in modal_articles:
                try:
                    # Extract product name from product link/label first so badge
                    # icons like "Nyckelhålet" do not get mistaken for products.
                    name = None
                    try:
                        link = await modal_article.query_selector('a[href*="/varor/"][aria-label]')
                        if link:
                            aria_label = await link.get_attribute('aria-label')
                            if aria_label:
                                parts = aria_label.split(',')
                                if parts:
                                    name = parts[0].strip()
                    except Exception:
                        pass

                    # Fallback: product image alt on the actual product link only.
                    if not name:
                        try:
                            img = await modal_article.query_selector('a[href*="/varor/"] img[alt]')
                            if img:
                                name = await img.get_attribute('alt')
                        except Exception:
                            pass

                    # Final fallback: visible product-name div used on Coop cards.
                    if not name:
                        try:
                            name_el = await modal_article.query_selector('.d7r5pDyW')
                            if name_el:
                                name = await name_el.text_content()
                        except Exception:
                            pass

                    if not name or len(name.strip()) < 2:
                        logger.debug("Skipping Coop e-handel variant: could not extract variant name")
                        continue

                    name = fix_swedish_chars(name.strip())

                    if self._is_noise_product(name):
                        continue

                    # Extract brand
                    brand = None
                    brand_span = await modal_article.query_selector(self.BRAND_CSS_CLASS)
                    if brand_span:
                        brand = await brand_span.text_content()
                        if brand:
                            brand = brand.strip().rstrip('.')

                    if brand and brand.lower() not in name.lower():
                        name = f"{name}, {brand}"

                    # Extract image URL (product image from cloudinary, skip badges)
                    image_url = None
                    img = await modal_article.query_selector('a[href*="/varor/"] img[src]')
                    if img:
                        srcset = await img.get_attribute('srcset')
                        if srcset:
                            image_url = srcset.split()[0]
                        else:
                            image_url = await img.get_attribute('src')

                        if image_url:
                            if image_url.startswith('//'):
                                image_url = f"https:{image_url}"
                            elif not image_url.startswith('http'):
                                image_url = f"{self.base_url}{image_url}"

                    # Prices are always per-piece (kr/st or multi-buy)
                    # "per liter" in parent text is from comparison price, not actual price
                    unit = "st"

                    # Calculate savings
                    savings = original_price - offer_price if original_price > offer_price else 0.0

                    # Trust Coop's on-page pricing for direct variant cards, including
                    # steep multi-buy offers such as "4 för 20" where per-piece savings
                    # can legitimately exceed the discounted piece price.

                    # Extract package weight from name or parent text
                    weight_grams = parse_weight(name)
                    if not weight_grams:
                        w_match = re.search(
                            r'(\d+(?:[,\.]\d+)?)\s*(g|kg|ml|cl|l|gram|liter)\b',
                            parent_text, re.IGNORECASE
                        )
                        if w_match:
                            weight_grams = parse_weight(w_match.group(0))

                    # Extract product URL from modal article
                    product_url = None
                    try:
                        link = await modal_article.query_selector('a[href*="/varor/"]')
                        if link:
                            href = await link.get_attribute('href')
                            if href:
                                product_url = href if href.startswith('http') else f"{self.base_url}{href}"
                    except Exception:
                        pass

                    # Create product
                    product = {
                        "name": name,
                        "price": round(offer_price, 2),
                        "original_price": round(original_price, 2),
                        "savings": round(savings, 2),
                        "unit": unit,
                        "category": shared_guess_category(name),
                        "image_url": image_url,
                        "product_url": product_url,
                        "weight_grams": weight_grams,
                        "scraped_at": datetime.now(timezone.utc)
                    }

                    if is_multi_buy:
                        product["is_multi_buy"] = True
                        product["multi_buy_quantity"] = multi_buy_quantity
                        product["multi_buy_total_price"] = round(multi_buy_total, 2)

                    products.append(product)

                except Exception as e:
                    logger.debug(f"Error extracting e-commerce variant: {e}")
                    continue

            # Close the modal
            close_btn = None
            for selector in (
                'button[aria-label*="Stäng"]',
                'button:has([aria-label*="Stäng"])',
                'button:has-text("Stäng")',
            ):
                try:
                    close_btn = await dialog.query_selector(selector)
                    if close_btn:
                        break
                except Exception:
                    continue

            if close_btn:
                await close_btn.click()
            else:
                await page.keyboard.press('Escape')

            try:
                await page.wait_for_selector('[role="dialog"]', state='hidden', timeout=3000)
            except Exception:
                await asyncio.sleep(0.5)

            logger.debug(f"Extracted {len(products)} variants from e-commerce modal")

        except Exception as e:
            logger.debug(f"Error extracting e-commerce variants: {e}")
            try:
                await page.keyboard.press('Escape')
            except Exception as esc_error:
                logger.debug(f"Could not press Escape: {esc_error}")

        return products

    async def _handle_postal_code_popup(self, page, postal_code: str):
        """Handle the postal code selection popup."""
        try:
            logger.info(f"Setting postal code: {postal_code}")

            # Look for postal code input
            # Coop typically shows a popup asking for postal code
            postal_selectors = [
                'input[placeholder*="postnummer"]',
                'input[placeholder*="Postnummer"]',
                'input[name*="zip"]',
                'input[name*="postal"]',
                'input[type="text"][maxlength="5"]',
            ]

            postal_input = None
            for selector in postal_selectors:
                try:
                    postal_input = await page.wait_for_selector(selector, timeout=3000)
                    if postal_input and await postal_input.is_visible():
                        logger.debug(f"Found postal code input: {selector}")
                        break
                    postal_input = None
                except Exception:
                    # Expected: selector not found, try next one
                    continue

            if postal_input:
                await postal_input.click()
                await postal_input.fill(postal_code)
                await asyncio.sleep(0.5)

                # Try to submit/confirm
                submit_selectors = [
                    'button:has-text("Bekräfta")',
                    'button:has-text("OK")',
                    'button:has-text("Fortsätt")',
                    'button[type="submit"]',
                ]

                for selector in submit_selectors:
                    try:
                        submit_btn = await page.query_selector(selector)
                        if submit_btn and await submit_btn.is_visible():
                            await submit_btn.click()
                            await asyncio.sleep(2)
                            logger.success(f"✓ Set postal code to {postal_code}")
                            break
                    except Exception:
                        # Expected: selector not found, try next one
                        continue
            else:
                logger.debug("No postal code popup found - might already be set")

        except Exception as e:
            logger.warning(f"Could not handle postal code popup: {e}")

    async def _close_popups(self, page):
        """Close any popups/overlays."""
        try:
            close_selectors = [
                '[aria-label="Close"]',
                '[aria-label="Stäng"]',
                'button:has-text("Stäng")',
                'button:has-text("×")',
                '[data-testid="close-button"]',
                '.modal-close',
            ]

            for selector in close_selectors:
                try:
                    buttons = await page.query_selector_all(selector)
                    for button in buttons:
                        if await button.is_visible():
                            await button.click()
                            await asyncio.sleep(0.2)
                except Exception:
                    # Expected: selector not found or button not clickable
                    pass

            # Also try pressing Escape
            await page.keyboard.press('Escape')
            await asyncio.sleep(0.1)

        except Exception as e:
            logger.debug(f"Could not close popups: {e}")

    async def _scroll_to_load_all(self, page):
        """Scroll to load all products. Stops after 3 consecutive scrolls with no new products."""
        previous_count = 0
        no_new_count = 0

        for scroll in range(100):  # safety limit only
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(0.5)

            current_count = len(await page.query_selector_all('[class*="product"], [data-product], article'))
            logger.debug(f"Scroll {scroll + 1}: Found {current_count} products")

            if current_count == previous_count:
                no_new_count += 1
                if no_new_count >= 3:
                    break
            else:
                no_new_count = 0

            previous_count = current_count

    async def _extract_products_from_page(self, page) -> List[Dict]:
        """Extract product data from the offers page."""
        products = []

        try:
            # Coop product cards - we need to find the right selector
            # Try multiple possible selectors
            product_selectors = [
                '[data-testid="product-card"]',
                '[class*="ProductCard"]',
                '[class*="product-card"]',
                'article[class*="product"]',
                '[class*="offer-card"]',
                '.Grid-cell article',
            ]

            product_elements = []
            for selector in product_selectors:
                product_elements = await page.query_selector_all(selector)
                if product_elements:
                    logger.info(f"Found {len(product_elements)} products with selector: {selector}")
                    break

            if not product_elements:
                # Fallback: try to find any product-like elements
                logger.warning("No product elements found with standard selectors, trying fallback...")

                # Try extracting from page content
                page_content = await page.content()
                products = self._extract_products_from_html(page_content)
                return products

            for element in product_elements:
                try:
                    product = await self._extract_single_product(element)
                    if product:
                        products.append(product)
                except Exception as e:
                    logger.debug(f"Error extracting product: {e}")
                    continue

            logger.info(f"Extracted {len(products)} products from page")

        except Exception as e:
            logger.error(f"Error extracting products: {e}")

        return products

    async def _extract_single_product(self, element) -> Optional[Dict]:
        """Extract data from a single product element."""
        try:
            # Get all text content for price extraction
            text_content = await element.text_content()
            if not text_content:
                return None

            text_content = text_content.strip()

            # Extract product name from multiple sources
            # Priority: 1) img alt, 2) aria-label from link, 3) first div text
            name = None

            # Method 1: Get from product image alt attribute (cleanest)
            try:
                img = await element.query_selector('a img[alt]')
                if img:
                    name = await img.get_attribute('alt')
            except Exception:
                # Selector not found, try other methods
                pass

            # Method 2: Parse from aria-label on the link
            if not name:
                try:
                    link = await element.query_selector('a[aria-label]')
                    if link:
                        aria_label = await link.get_attribute('aria-label')
                        if aria_label:
                            # aria-label format: "Morötter Eko, Änglamark. Klass 1. Sverige, 1 kg, ..."
                            # Take first part before the brand/class info
                            parts = aria_label.split(',')
                            if parts:
                                name = parts[0].strip()
                except Exception:
                    # Selector not found, try other methods
                    pass

            # Method 3: Get from add-to-cart button aria-label
            if not name:
                try:
                    btn = await element.query_selector('button[aria-label*="Lägg i varukorg"]')
                    if btn:
                        aria = await btn.get_attribute('aria-label')
                        if aria:
                            # Format: "Lägg i varukorg, Morötter Eko"
                            name = aria.replace('Lägg i varukorg,', '').strip()
                except Exception:
                    # Selector not found
                    pass

            if not name:
                logger.debug("Skipping Coop product card: could not extract product name")
                return None
            if self._is_noise_product(name):
                return None

            # Clean up name
            name = fix_swedish_chars(name.strip())

            # Get aria-label for cleaner price extraction
            # Format: "..., Erbjudande 15 kronor styck, ..., Ordinarie pris 22 kronor och 95 öre..."
            aria_label = ""
            try:
                link = await element.query_selector('a[aria-label]')
                if link:
                    aria_label = await link.get_attribute('aria-label') or ""
            except Exception:
                # Selector not found, will use text content fallback
                pass

            # Extract price from aria-label (most reliable)
            price = 0.0
            is_multi_buy = False
            multi_buy_quantity = 1
            multi_buy_total = 0.0
            _is_member_price = False  # noqa: F841

            # Pattern 1: Multi-buy "Erbjudande/Medlemspris X för Y kronor"
            multi_buy_match = re.search(
                r'(?:Erbjudande|Medlemspris)\s+(\d+)\s+för\s+(\d+)\s+kronor(?:\s+och\s+(\d+)\s+öre)?',
                aria_label,
                re.IGNORECASE
            )
            if multi_buy_match:
                is_multi_buy = True
                _is_member_price = 'Medlemspris' in aria_label  # noqa: F841 — kept for future use
                multi_buy_quantity = int(multi_buy_match.group(1))
                whole = multi_buy_match.group(2)
                decimal = multi_buy_match.group(3) if multi_buy_match.group(3) else "00"
                multi_buy_total = float(f"{whole}.{decimal}")
                price = multi_buy_total / multi_buy_quantity  # Price per unit
            else:
                # Pattern 2: Single price "Erbjudande/Medlemspris X kronor"
                offer_match = re.search(
                    r'(?:Erbjudande|Medlemspris)\s+(\d+)\s+kronor(?:\s+och\s+(\d+)\s+öre)?(?:\s+styck)?',
                    aria_label,
                    re.IGNORECASE
                )
                if offer_match:
                    _is_member_price = 'Medlemspris' in aria_label
                    whole = offer_match.group(1)
                    decimal = offer_match.group(2) if offer_match.group(2) else "00"
                    price = float(f"{whole}.{decimal}")

            # Fallback: try text content
            if price == 0:
                # Look for "Xkr/st" pattern
                price_match = re.search(r'(\d+)\s*kr/st', text_content)
                if price_match:
                    price = float(price_match.group(1))
                else:
                    # Try more generic pattern
                    price_match = re.search(r'(\d+)[,.](\d{2})\s*kr', text_content)
                    if price_match:
                        price = float(f"{price_match.group(1)}.{price_match.group(2)}")

            if price == 0:
                logger.debug(f"Skipping Coop product card '{name}': could not extract price")
                return None

            # For per-kilo products, the initial regex matched "Medlemspris X kronor per kilo".
            # Re-extract per-piece price from "Erbjudande X kronor och Y öre styck" instead,
            # so price, original_price and savings are all in the same unit (per piece).
            is_per_kilo = 'per kilo' in aria_label.lower()
            if is_per_kilo and not is_multi_buy:
                erbjudande_match = re.search(
                    r'Erbjudande\s+(\d+)\s+kronor(?:\s+och\s+(\d+)\s+öre)?',
                    aria_label, re.IGNORECASE
                )
                if erbjudande_match:
                    whole = erbjudande_match.group(1)
                    decimal = erbjudande_match.group(2) if erbjudande_match.group(2) else "00"
                    price = float(f"{whole}.{decimal}")

            # Extract original price from aria-label (always per-piece)
            original_price = price
            ord_match = re.search(r'Ordinarie\s+pris\s+(\d+)\s+kronor(?:\s+och\s+(\d+)\s+öre)?', aria_label)
            if ord_match:
                whole = ord_match.group(1)
                decimal = ord_match.group(2) if ord_match.group(2) else "00"
                original_price = float(f"{whole}.{decimal}")
            else:
                # Try "Tidigare lägsta pris"
                prev_match = re.search(r'Tidigare\s+lägsta\s+pris\s+(\d+)\s+kronor(?:\s+och\s+(\d+)\s+öre)?', aria_label)
                if prev_match:
                    whole = prev_match.group(1)
                    decimal = prev_match.group(2) if prev_match.group(2) else "00"
                    original_price = float(f"{whole}.{decimal}")
                else:
                    # Fallback to text content
                    ord_text_match = re.search(r'Ord\.?\s*pris\s+(\d+)[,.](\d{2})', text_content)
                    if ord_text_match:
                        original_price = float(f"{ord_text_match.group(1)}.{ord_text_match.group(2)}")

            savings = original_price - price if original_price > price else 0.0

            # Trust Coop's own on-page pricing here as well; extremely aggressive
            # promotions can legitimately have savings larger than the discounted
            # price, especially for multi-buy and campaign items.

            # All Coop prices are per-piece (kr/st or multi-buy)
            # Per-kilo products already re-extracted to per-piece price above
            # text_content comparison prices ("Jfr-pris kr/kg", "per liter") are NOT price units
            unit = "st"

            # Extract package weight from name or aria-label
            weight_grams = parse_weight(name)
            if not weight_grams and aria_label:
                # aria-label format: "...Sverige, 1 kg, Erbjudande..."
                # Search for weight pattern before price section
                w_match = re.search(
                    r'(\d+(?:[,\.]\d+)?)\s*(g|kg|ml|cl|l|gram|liter)\b',
                    aria_label, re.IGNORECASE
                )
                if w_match:
                    weight_grams = parse_weight(w_match.group(0))

            # Extract image URL
            image_url = None
            try:
                img = await element.query_selector('a img[src]')
                if img:
                    # Try srcset first for higher quality
                    srcset = await img.get_attribute('srcset')
                    if srcset:
                        # Get first URL from srcset
                        image_url = srcset.split()[0]
                    else:
                        image_url = await img.get_attribute('src')

                    if image_url:
                        if image_url.startswith('//'):
                            image_url = f"https:{image_url}"
                        elif not image_url.startswith('http'):
                            image_url = f"{self.base_url}{image_url}"
            except Exception:
                # Image extraction failed, product will have no image
                pass

            # Skip badge/icon articles (not real products)
            if image_url and '/Assets/Icons/' in image_url:
                logger.debug(f"Skipping badge article: {name} ({image_url})")
                return None

            # Extract product URL
            product_url = None
            try:
                link = await element.query_selector('a[href*="/varor/"]')
                if link:
                    href = await link.get_attribute('href')
                    if href:
                        product_url = href if href.startswith('http') else f"{self.base_url}{href}"
            except Exception:
                # URL extraction failed, product will have no link
                pass

            # Guess category
            category = shared_guess_category(name)

            result = {
                "name": name,
                "price": round(price, 2),
                "original_price": round(original_price, 2),
                "savings": round(savings, 2),
                "unit": unit,
                "category": category,
                "image_url": image_url,
                "product_url": product_url,
                "weight_grams": weight_grams,
                "scraped_at": datetime.now(timezone.utc)
            }

            # Add multi-buy info if applicable
            if is_multi_buy:
                result["is_multi_buy"] = True
                result["multi_buy_quantity"] = multi_buy_quantity
                result["multi_buy_total_price"] = round(multi_buy_total, 2)

            return result

        except Exception as e:
            logger.debug(f"Error extracting single product: {e}")
            return None

    def _extract_products_from_html(self, html: str) -> List[Dict]:
        """
        Fallback: Extract products from raw HTML using regex.

        Used when standard selectors don't work.
        """
        products = []

        # This is a basic fallback - might need refinement based on actual page structure
        # Look for JSON-LD product data if available
        json_ld_pattern = r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>'
        matches = re.findall(json_ld_pattern, html, re.DOTALL)

        for match in matches:
            try:
                import json
                data = json.loads(match)

                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "Product":
                            product = self._parse_json_ld_product(item)
                            if product:
                                products.append(product)
                elif isinstance(data, dict) and data.get("@type") == "Product":
                    product = self._parse_json_ld_product(data)
                    if product:
                        products.append(product)
            except (json.JSONDecodeError, KeyError, TypeError):
                # Invalid JSON or unexpected structure, skip
                continue

        return products

    def _parse_json_ld_product(self, data: dict) -> Optional[Dict]:
        """Parse JSON-LD product data."""
        try:
            name = data.get("name", "").strip()
            if not name:
                logger.debug("Skipping Coop physical-store article: could not extract product name")
                return None
            if self._is_noise_product(name):
                return None

            # Get price from offers
            offers = data.get("offers", {})
            price = 0.0
            if isinstance(offers, dict):
                price = float(offers.get("price", 0))
            elif isinstance(offers, list) and offers:
                price = float(offers[0].get("price", 0))

            if price == 0:
                logger.debug(f"Skipping Coop physical-store article '{name}': could not extract price")
                return None

            return {
                "name": fix_swedish_chars(name),
                "price": round(price, 2),
                "original_price": round(price, 2),
                "savings": 0.0,
                "unit": "st",
                "category": shared_guess_category(name),
                "image_url": data.get("image"),
                "product_url": data.get("url"),
                "scraped_at": datetime.now(timezone.utc)
            }
        except (KeyError, ValueError, TypeError) as e:
            logger.debug(f"Could not parse JSON-LD product: {e}")
            return None

    # ==================== PHYSICAL STORE SCRAPING ====================

    async def _scrape_physical_store(self, store_url: str) -> List[Dict]:
        """
        Scrape offers from a physical store page.

        Uses Coop's DKE offers API as the primary source for physical-store
        offers. This gives us the real grouped card count, exact variant list,
        stable offer ids, and product external ids that can later be used for
        much more reliable original-price enrichment than fuzzy DOM scraping.
        """
        try:
            store_page_id = await self._load_physical_store_page_id(store_url)
            if not store_page_id:
                logger.warning(f"Could not resolve Coop store page id from {store_url}")
                return []

            logger.info(f"Using Coop DKE store page id: {store_page_id}")

            grouped_offers = await self._fetch_dke_grouped_offers(store_page_id)
            if not grouped_offers:
                logger.warning(f"No DKE grouped offers returned for Coop store {store_page_id}")
                return []

            products, card_count = self._build_products_from_dke_grouped_offers(grouped_offers)
            self._scrape_meta = {
                "base_count": card_count,
                "variant_count": max(len(products) - card_count, 0),
                "card_count": card_count,
            }
            logger.info(
                f"Extracted {len(products)} products from Coop DKE "
                f"({card_count} grouped cards)"
            )

            if products:
                products = await self._enrich_with_original_prices(products)

            return products

        except Exception as e:
            logger.error(f"Error scraping physical store: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return []

    async def _load_physical_store_page_id(self, store_url: str) -> Optional[str]:
        """Resolve Coop's physical-store page id from the rendered store page HTML."""
        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            event_hooks={"request": [ssrf_safe_event_hook]},
        ) as client:
            resp = await client.get(store_url)
            resp.raise_for_status()
            html = resp.text

        patterns = [
            r'store_page_id":"(\d+)"',
            r'"store_page_id":"(\d+)"',
            r'dr\.coop\.se/butik/(\d+)',
            r'ledgerAccountNumber":"(\d+)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return match.group(1)
        return None

    async def _fetch_dke_grouped_offers(self, store_page_id: str) -> Optional[Dict]:
        """Fetch grouped physical-store offers from Coop's DKE API."""
        params = {
            "api-version": "v2",
            "clustered": "true",
            "grouped": "true",
        }
        headers = {
            "ocp-apim-subscription-key": self.DKE_API_KEY,
            "Accept": "application/json",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
        }

        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            event_hooks={"request": [ssrf_safe_event_hook]},
        ) as client:
            resp = await client.get(
                f"{self.DKE_API_URL}/{store_page_id}",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        for group in data.get("sortingGroups", []):
            if group.get("id") == "alla":
                return group
        return None

    def _build_products_from_dke_grouped_offers(self, grouped_offers: Dict) -> tuple[List[Dict], int]:
        """Flatten Coop's grouped DKE offer structure into products plus visible card count."""
        products: List[Dict] = []
        seen_offer_ids = set()

        for offer in grouped_offers.get("offers") or []:
            cluster_offers = offer.get("clusterInteriorOffers") or []
            entries = [(offer, bool(cluster_offers))] + [
                (entry, False) for entry in cluster_offers
            ]

            for entry, is_group_parent in entries:
                offer_id = entry.get("id")
                if offer_id and offer_id in seen_offer_ids:
                    continue
                if offer_id:
                    seen_offer_ids.add(offer_id)

                product = self._build_product_from_dke_offer(
                    entry,
                    is_group_parent=is_group_parent,
                )
                if product:
                    products.append(product)

        return products, int(grouped_offers.get("offerAmount") or 0)

    def _build_product_from_dke_offer(
        self,
        offer: Dict,
        *,
        is_group_parent: bool = False,
    ) -> Optional[Dict]:
        """Convert one DKE offer row into the app's product shape."""
        content = offer.get("content") or {}
        price_information = offer.get("priceInformation") or {}

        title = (content.get("title") or "").strip()
        if not title:
            return None

        brand = (content.get("brand") or "").strip().rstrip(".")
        if brand and brand != "." and brand.lower() not in title.lower():
            name = f"{title}, {brand}"
        else:
            name = title

        if self._is_noise_product(name):
            return None

        total_price = float(price_information.get("discountValue") or 0)
        if total_price <= 0:
            return None

        quantity = int(price_information.get("minimumAmount") or 1)
        normalized_price = round(total_price / quantity, 2) if quantity > 1 else round(total_price, 2)

        image_url = content.get("imageUrl")
        if image_url:
            if image_url.startswith("//"):
                image_url = f"https:{image_url}"
            elif not image_url.startswith("http"):
                image_url = f"{self.base_url}{image_url}"

        amount_information = (
            content.get("amountInformation")
            or content.get("parentAmountInformation")
            or ""
        )
        weight_grams = parse_weight(amount_information) or parse_weight(name)

        unit = (price_information.get("unit") or "st").lower()
        if quantity > 1 and unit == "mix":
            unit = "st"

        category = shared_guess_category(name)
        category_team = ((offer.get("categoryTeam") or {}).get("name") or "").strip()
        if not category and category_team:
            category = shared_guess_category(category_team)

        product = {
            "name": fix_swedish_chars(name.strip()),
            "price": normalized_price,
            "original_price": normalized_price,
            "savings": 0.0,
            "unit": unit,
            "category": category,
            "image_url": image_url,
            "product_url": None,
            "weight_grams": weight_grams,
            "scraped_at": datetime.now(timezone.utc),
            "_coop_external_id": offer.get("externalId"),
            "_coop_dke_offer_id": offer.get("id"),
            "_coop_group_key": str(offer.get("eagId") or offer.get("id") or ""),
            "_coop_is_group_parent": is_group_parent,
        }

        if quantity > 1:
            product["is_multi_buy"] = True
            product["multi_buy_quantity"] = quantity
            product["multi_buy_total_price"] = round(total_price, 2)

        return product

    async def _extract_physical_store_product(self, article) -> Optional[Dict]:
        """
        Extract product data from a physical store article element.

        Coop butik HTML structure (Feb 2026):
        - <h3 class="OXTlHT32">Product Name</h3>  (reliable product name)
        - <span class="q5vMS42j">Brand.</span>
        - <span>Weight.</span>
        - Price div (.slH8Imgo): <span>59,90</span><span>kr</span><span>/st</span>
        - Aria text (p.u-hiddenVisuallyOutlined): "59 kronor och 90 öre per styck"
        - Badge icons (img alt) can be "MSC", "Nyckelhål" etc. - NOT product name

        Price formats in aria text:
        - Multi-buy: "4 för 30 kronor"
        - Per piece: "59 kronor och 90 öre per styck"
        - Per kilo: "169 kronor per kilo" (lösvikt)
        """
        try:
            text_content = await article.text_content()
            if not text_content:
                return None

            text_content = text_content.strip()

            # Skip non-product articles (gift cards, point-based offers)
            if 'ppoäng' in text_content.lower() or 'värdecheck' in text_content.lower():
                return None

            # Extract product name from h3 (reliable) - NOT img alt (can be badge icon)
            name = None
            try:
                h3 = await article.query_selector('h3')
                if h3:
                    name = await h3.text_content()
            except Exception:
                pass

            # Fallback: product image alt (from cloudinary product images only)
            if not name:
                try:
                    img = await article.query_selector('img[srcset*="coopsverige"]')
                    if img:
                        name = await img.get_attribute('alt')
                except Exception:
                    pass

            if not name:
                logger.debug("Skipping Coop physical-store article: could not extract product name")
                return None
            if self._is_noise_product(name):
                return None

            name = fix_swedish_chars(name.strip())

            # Extract brand
            brand = None
            try:
                brand_span = await article.query_selector(self.BRAND_CSS_CLASS)
                if brand_span:
                    brand = await brand_span.text_content()
                    if brand:
                        brand = brand.strip().rstrip('.')
            except Exception:
                pass

            if brand and brand.lower() not in name.lower():
                name = f"{name}, {brand}"

            aria_text = ""
            try:
                aria_el = await article.query_selector('p.u-hiddenVisuallyOutlined')
                if aria_el:
                    aria_text = (await aria_el.text_content()).strip()
            except Exception:
                pass
            price_info = self._parse_physical_store_price_info(text_content, aria_text)
            price = price_info["price"]
            is_multi_buy = price_info["is_multi_buy"]
            multi_buy_quantity = price_info["multi_buy_quantity"]
            multi_buy_total = price_info["multi_buy_total"]
            unit = price_info["unit"]

            if price == 0:
                logger.debug(f"Skipping Coop physical-store article '{name}': could not extract price")
                return None

            original_price = price
            savings = 0.0

            # Extract image URL (product image from cloudinary, skip badge icons)
            image_url = None
            try:
                img = await article.query_selector('img[srcset*="coopsverige"]')
                if img:
                    srcset = await img.get_attribute('srcset')
                    if srcset:
                        image_url = srcset.split()[0]
                    else:
                        image_url = await img.get_attribute('src')

                    if image_url:
                        if image_url.startswith('//'):
                            image_url = f"https:{image_url}"
                        elif not image_url.startswith('http'):
                            image_url = f"{self.base_url}{image_url}"
            except Exception:
                pass

            # Extract product URL
            product_url = None
            try:
                link = await article.query_selector('a[href]')
                if link:
                    href = await link.get_attribute('href')
                    if href and '/varor/' in href:
                        product_url = href if href.startswith('http') else f"{self.base_url}{href}"
            except Exception:
                pass

            # Extract package weight from name or text content
            weight_grams = parse_weight(name)
            if not weight_grams:
                w_match = re.search(
                    r'(\d+(?:[,\.]\d+)?)\s*(g|kg|ml|cl|l|gram|liter)\b',
                    text_content, re.IGNORECASE
                )
                if w_match:
                    weight_grams = parse_weight(w_match.group(0))

            category = shared_guess_category(name)

            result = {
                "name": name,
                "price": round(price, 2),
                "original_price": round(original_price, 2),
                "savings": round(savings, 2),
                "unit": unit,
                "category": category,
                "image_url": image_url,
                "product_url": product_url,
                "weight_grams": weight_grams,
                "is_member_price": True,
                "scraped_at": datetime.now(timezone.utc)
            }

            if is_multi_buy:
                result["is_multi_buy"] = True
                result["multi_buy_quantity"] = multi_buy_quantity
                result["multi_buy_total_price"] = round(multi_buy_total, 2)

            return result

        except Exception as e:
            logger.debug(f"Error extracting physical store product: {e}")
            return None

    async def _query_visible_store_articles(self, page) -> List:
        """Return visible physical-store product cards outside any modal dialog."""
        visible_articles = []

        for article in await page.query_selector_all('article'):
            try:
                if not await article.is_visible():
                    continue
                if await article.evaluate("el => !!el.closest('[role=\"dialog\"]')"):
                    continue
                visible_articles.append(article)
            except Exception:
                continue

        return visible_articles

    def _parse_physical_store_price_info(self, text_content: str, aria_text: str = "") -> Dict:
        """Parse Coop butik price info from aria/visible text."""
        price = 0.0
        is_multi_buy = False
        multi_buy_quantity = 1
        multi_buy_total = 0.0
        unit = "st"

        if aria_text:
            multi_match = re.search(
                r'(\d+)\s+för\s+(\d+)\s+kronor',
                aria_text, re.IGNORECASE
            )
            if multi_match:
                is_multi_buy = True
                multi_buy_quantity = int(multi_match.group(1))
                multi_buy_total = float(multi_match.group(2))
                price = multi_buy_total / multi_buy_quantity

            if price == 0:
                piece_match = re.search(
                    r'(\d+)\s+kronor(?:\s+och\s+(\d+)\s+öre)?\s+per\s+styck',
                    aria_text, re.IGNORECASE
                )
                if piece_match:
                    whole = piece_match.group(1)
                    decimal = piece_match.group(2) if piece_match.group(2) else "00"
                    price = float(f"{whole}.{decimal}")

            if price == 0:
                kg_match = re.search(
                    r'(\d+)\s+kronor(?:\s+och\s+(\d+)\s+öre)?\s+per\s+kilo',
                    aria_text, re.IGNORECASE
                )
                if kg_match:
                    whole = kg_match.group(1)
                    decimal = kg_match.group(2) if kg_match.group(2) else "00"
                    price = float(f"{whole}.{decimal}")
                    unit = "kg"

        if price == 0:
            multi_buy_match = re.search(
                r'(\d+)\s*för\s*(\d+)(?:[,.](\d{1,2}))?\s*kr(?!\s*/)',
                text_content, re.IGNORECASE
            )
            if multi_buy_match:
                is_multi_buy = True
                multi_buy_quantity = int(multi_buy_match.group(1))
                whole = multi_buy_match.group(2)
                decimal = multi_buy_match.group(3) if multi_buy_match.group(3) else "00"
                decimal = decimal.ljust(2, '0')[:2]
                multi_buy_total = float(f"{whole}.{decimal}")
                price = multi_buy_total / multi_buy_quantity

        if price == 0:
            single_match = re.search(
                r'(\d+)(?:[,.](\d{1,2}))?\s*kr/st',
                text_content, re.IGNORECASE
            )
            if single_match:
                whole = single_match.group(1)
                decimal = single_match.group(2) if single_match.group(2) else "00"
                decimal = decimal.ljust(2, '0')[:2]
                price = float(f"{whole}.{decimal}")

        if price == 0:
            kg_match = re.search(
                r'(\d+)(?:[,.](\d{1,2}))?\s*kr/kg',
                text_content, re.IGNORECASE
            )
            if kg_match:
                whole = kg_match.group(1)
                decimal = kg_match.group(2) if kg_match.group(2) else "00"
                decimal = decimal.ljust(2, '0')[:2]
                price = float(f"{whole}.{decimal}")
                unit = "kg"

        return {
            "price": price,
            "is_multi_buy": is_multi_buy,
            "multi_buy_quantity": multi_buy_quantity,
            "multi_buy_total": multi_buy_total,
            "unit": unit,
        }

    async def _extract_variant_products(self, page, variant_btn, parent_article) -> List[Dict]:
        """
        Extract individual product variants from "Se X varor" modal.

        When a product card has multiple variants (e.g., 6 yoghurt flavors),
        clicking "Se X varor" opens a modal with individual products.

        Args:
            page: Playwright page object
            variant_btn: The "Se X varor" button element
            parent_article: The parent article element (for fallback price info)

        Returns:
            List of individual product variants
        """
        products = []

        try:
            # Get parent product info for price (fallback only)
            parent_text = await parent_article.text_content()
            parent_price_info = self._parse_physical_store_price_info(parent_text, "")
            parent_price = parent_price_info["price"]
            if parent_price == 0:
                logger.debug("Could not extract price from parent article")
                return []

            # Click button to open modal and wait for it to appear
            await variant_btn.click(force=True)
            try:
                dialog_locator = page.locator('[role="dialog"]').last
                await dialog_locator.wait_for(state="visible", timeout=3000)
                dialog = await dialog_locator.element_handle()
            except Exception:
                dialog = None
                dialog_locator = None
            if not dialog:
                logger.debug("No dialog found after clicking variant button")
                return []

            # Find product articles in the modal
            # Structure: ul > li.Grid-cell > article
            modal_articles = await dialog.query_selector_all('li article')
            if not modal_articles:
                # Fallback: try direct article selection
                modal_articles = await dialog.query_selector_all('article')

            logger.debug(f"Found {len(modal_articles)} variants in modal")

            for modal_article in modal_articles:
                try:
                    # Extract product name from h3 (reliable, avoids badge icons)
                    name = None
                    try:
                        h3 = await modal_article.query_selector('h3')
                        if h3:
                            name = await h3.text_content()
                    except Exception:
                        pass

                    # Fallback: product image alt (cloudinary only)
                    if not name:
                        img = await modal_article.query_selector('img[srcset*="coopsverige"]')
                        if img:
                            name = await img.get_attribute('alt')

                    if not name or len(name.strip()) < 2:
                        logger.debug("Skipping Coop variant modal article: could not extract variant name")
                        continue

                    name = fix_swedish_chars(name.strip())

                    if self._is_noise_product(name):
                        continue

                    # Extract brand
                    brand = None
                    brand_span = await modal_article.query_selector(self.BRAND_CSS_CLASS)
                    if brand_span:
                        brand = await brand_span.text_content()
                        if brand:
                            brand = brand.strip().rstrip('.')

                    if brand and brand.lower() not in name.lower():
                        name = f"{name}, {brand}"

                    # Extract image URL (product image from cloudinary, skip badges)
                    image_url = None
                    img = await modal_article.query_selector('img[srcset*="coopsverige"]')
                    if img:
                        srcset = await img.get_attribute('srcset')
                        if srcset:
                            image_url = srcset.split()[0]
                        else:
                            image_url = await img.get_attribute('src')

                        if image_url:
                            if image_url.startswith('//'):
                                image_url = f"https:{image_url}"
                            elif not image_url.startswith('http'):
                                image_url = f"{self.base_url}{image_url}"

                    # Parse the variant's own price first; some physical-store
                    # modal variants do not share the parent card's campaign.
                    variant_text = await modal_article.text_content() or ""
                    variant_aria_text = ""
                    try:
                        aria_el = await modal_article.query_selector('p.u-hiddenVisuallyOutlined')
                        if aria_el:
                            variant_aria_text = (await aria_el.text_content()).strip()
                    except Exception:
                        pass

                    price_info = self._parse_physical_store_price_info(variant_text, variant_aria_text)
                    price = price_info["price"] or parent_price
                    is_multi_buy = price_info["is_multi_buy"] or parent_price_info["is_multi_buy"]
                    multi_buy_quantity = (
                        price_info["multi_buy_quantity"]
                        if price_info["is_multi_buy"] else parent_price_info["multi_buy_quantity"]
                    )
                    multi_buy_total = (
                        price_info["multi_buy_total"]
                        if price_info["is_multi_buy"] else parent_price_info["multi_buy_total"]
                    )
                    unit = price_info["unit"] or parent_price_info["unit"]

                    # Extract package weight from variant's own text, then name
                    weight_grams = parse_weight(name)
                    if not weight_grams:
                        w_match = re.search(
                            r'(\d+(?:[,\.]\d+)?)\s*(g|kg|ml|cl|l|gram|liter)\b',
                            variant_text, re.IGNORECASE
                        )
                        if w_match:
                            weight_grams = parse_weight(w_match.group(0))

                    # Extract product URL from modal article
                    product_url = None
                    try:
                        link = await modal_article.query_selector('a[href*="/varor/"]')
                        if link:
                            href = await link.get_attribute('href')
                            if href:
                                product_url = href if href.startswith('http') else f"{self.base_url}{href}"
                    except Exception:
                        pass

                    # Create product with variant price (fallback to parent price)
                    product = {
                        "name": name,
                        "price": round(price, 2),
                        "original_price": round(price, 2),
                        "savings": 0.0,
                        "unit": unit,
                        "category": shared_guess_category(name),
                        "image_url": image_url,
                        "product_url": product_url,
                        "weight_grams": weight_grams,
                        "is_member_price": True,
                        "scraped_at": datetime.now(timezone.utc)
                    }

                    if is_multi_buy:
                        product["is_multi_buy"] = True
                        product["multi_buy_quantity"] = multi_buy_quantity
                        product["multi_buy_total_price"] = round(multi_buy_total, 2)

                    products.append(product)

                except Exception as e:
                    logger.debug(f"Error extracting variant product: {e}")
                    continue

            # Close the modal
            close_btn = await dialog.query_selector('button[aria-label*="Stäng"]')
            if close_btn:
                await close_btn.click()
            else:
                # Try pressing Escape
                await page.keyboard.press('Escape')
            if dialog_locator:
                try:
                    await dialog_locator.wait_for(state="hidden", timeout=2000)
                except Exception:
                    await asyncio.sleep(0.2)

            logger.debug(f"Extracted {len(products)} variants from modal")

        except Exception as e:
            logger.debug(f"Error extracting variant products: {e}")
            # Try to close any open modal
            try:
                await page.keyboard.press('Escape')
            except Exception as esc_error:
                logger.debug(f"Could not press Escape: {esc_error}")

        return products

    # ==================== PRICE CROSS-REFERENCE ====================

    # Coop public search API (visible in browser dev tools on coop.se, not a secret)
    DKE_API_URL = "https://external.api.coop.se/dke/offers/sorting-groups"
    DKE_API_KEY = "32895bd5b86e4a5ab6e94fb0bc8ae234"
    SEARCH_API_URL = "https://external.api.coop.se/personalization/search/products"
    SEARCH_API_KEY = "3becf0ce306f41a1ae94077c16798187"
    SEARCH_API_STORE = "251300"
    SEARCH_BATCH_SIZE = 3  # Keep physical Coop enrichment gentle on Coop's API
    SEARCH_BATCH_DELAY_SECONDS = 1.25
    SEARCH_API_MAX_RETRIES = 3
    SEARCH_API_RETRY_BACKOFF_SECONDS = 1.5

    async def _enrich_with_original_prices(self, products: List[Dict]) -> List[Dict]:
        """
        Enrich physical store products with original prices from e-commerce.

        Uses Coop's search API directly (httpx) instead of Playwright page
        navigation. Searches are batched conservatively with a pause between
        batches to be gentle to the server.

        Products not found in e-commerce are kept in the list; they just won't
        get original-price enrichment from the e-commerce API.
        """
        enriched_products = []
        enriched_count = 0
        kept_without_enrichment = 0
        total = len(products)

        logger.info(f"Looking up original prices for {total} products via API...")

        async with httpx.AsyncClient(timeout=15, event_hooks={"request": [ssrf_safe_event_hook]}) as client:
            # Process in batches
            for batch_start in range(0, total, self.SEARCH_BATCH_SIZE):
                batch = products[batch_start:batch_start + self.SEARCH_BATCH_SIZE]

                # Search all products in this batch concurrently
                tasks = [
                    self._lookup_original_price_api(
                        client,
                        p["name"],
                        p["price"],
                        p.get("_coop_external_id"),
                    )
                    for p in batch
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for j, (product, result) in enumerate(zip(batch, results)):
                    idx = batch_start + j + 1
                    if isinstance(result, Exception):
                        logger.debug(f"[{idx}/{total}] Error: {result}")
                        enriched_products.append(product)
                        kept_without_enrichment += 1
                        continue

                    if not result:
                        logger.debug(
                            f"[{idx}/{total}] ✗ {product['name']}: "
                            f"not found in e-commerce or no discount"
                        )
                        enriched_products.append(product)
                        kept_without_enrichment += 1
                        continue

                    original_price = result

                    if original_price and original_price > product["price"]:
                        savings = round(original_price - product["price"], 2)

                        if self._is_suspicious_original_price_match(
                            product["name"],
                            product.get("category"),
                            product["price"],
                            original_price,
                        ):
                            logger.warning(
                                f"[{idx}/{total}] ⚠ {product['name']}: "
                                f"suspicious savings {savings:.2f} > price "
                                f"{product['price']:.2f} (orig {original_price:.2f}), "
                                "keeping product without enrichment"
                            )
                            enriched_products.append(product)
                            kept_without_enrichment += 1
                            continue

                        product["original_price"] = round(original_price, 2)
                        product["savings"] = savings
                        enriched_products.append(product)
                        enriched_count += 1
                        logger.debug(
                            f"[{idx}/{total}] ✓ {product['name']}: "
                            f"{product['price']} kr (ord. {original_price} kr, "
                            f"spara {savings} kr)"
                        )
                    else:
                        logger.debug(
                            f"[{idx}/{total}] ✗ {product['name']}: "
                            f"not found in e-commerce or no discount"
                        )
                        enriched_products.append(product)
                        kept_without_enrichment += 1

                # Pause between batches to be gentle to the server
                if batch_start + self.SEARCH_BATCH_SIZE < total:
                    await asyncio.sleep(self.SEARCH_BATCH_DELAY_SECONDS)

        logger.info(
            f"Price lookup complete: {enriched_count}/{total} enriched, "
            f"{kept_without_enrichment}/{total} kept without enrichment"
        )
        propagated_count = self._propagate_group_original_prices(enriched_products)
        if propagated_count:
            logger.info(
                f"Group-propagated original prices for {propagated_count} Coop products "
                f"after exact-match enrichment"
            )
        dropped_group_parents = self._drop_unresolved_group_parents(enriched_products)
        if dropped_group_parents:
            logger.info(
                f"Dropped {dropped_group_parents} synthetic Coop group-parent rows "
                f"after enrichment"
            )
        for product in enriched_products:
            product.pop("_coop_external_id", None)
            product.pop("_coop_dke_offer_id", None)
            product.pop("_coop_group_key", None)
            product.pop("_coop_is_group_parent", None)
        return enriched_products

    def _propagate_group_original_prices(self, products: List[Dict]) -> int:
        """
        Reuse original prices within the same Coop DKE offer group when safe.

        Some grouped Coop cards ("Se X varor") represent sibling variants where
        only one or a few variants are directly findable in e-commerce. When a
        group has a single consistent enriched original price among already
        matched siblings, propagate that price to the remaining siblings with
        the same discounted price/multi-buy shape.

        This is intentionally conservative:
        - group must be the same DKE eagId/offer group
        - discounted price must match
        - multi-buy shape must match
        - all enriched siblings in that bucket must agree on one original price
        """
        buckets: Dict[tuple, List[Dict]] = {}
        for product in products:
            group_key = product.get("_coop_group_key")
            if not group_key:
                continue
            bucket_key = (
                group_key,
                round(float(product.get("price") or 0), 2),
                int(product.get("multi_buy_quantity") or 1),
                round(float(product.get("multi_buy_total_price") or 0), 2),
            )
            buckets.setdefault(bucket_key, []).append(product)

        propagated_count = 0
        for grouped_products in buckets.values():
            enriched = [
                product for product in grouped_products
                if float(product.get("original_price") or 0) > float(product.get("price") or 0)
            ]
            missing = [
                product for product in grouped_products
                if not (float(product.get("original_price") or 0) > float(product.get("price") or 0))
            ]
            if not enriched or not missing:
                continue

            original_candidates = {
                round(float(product.get("original_price") or 0), 2)
                for product in enriched
                if float(product.get("original_price") or 0) > float(product.get("price") or 0)
            }
            if len(original_candidates) != 1:
                continue

            original_price = next(iter(original_candidates))
            for product in missing:
                price = round(float(product.get("price") or 0), 2)
                if original_price <= price:
                    continue
                savings = round(original_price - price, 2)
                if price > 0 and savings > price:
                    continue
                product["original_price"] = original_price
                product["savings"] = savings
                propagated_count += 1

        return propagated_count

    def _is_nonfood_hardgood_product(self, name: str, category: Optional[str]) -> bool:
        """Best-effort check for non-food products where deep discounts are normal."""
        category_lower = (category or "").lower()
        name_lower = (name or "").lower()
        if category_lower == "household":
            return True
        return any(keyword in name_lower for keyword in self._NONFOOD_HARDGOOD_KEYWORDS)

    def _is_suspicious_original_price_match(
        self,
        name: str,
        category: Optional[str],
        member_price: float,
        original_price: float,
    ) -> bool:
        """
        Filter obviously wrong enrichment matches without rejecting normal
        non-food markdowns.
        """
        if member_price <= 0 or original_price <= member_price:
            return False

        savings = original_price - member_price
        if not self._is_nonfood_hardgood_product(name, category):
            return savings > member_price

        return original_price > (member_price * 5)

    def _drop_unresolved_group_parents(self, products: List[Dict]) -> int:
        """
        Remove grouped-card parent rows when concrete children exist.

        In Coop DKE grouped offers, the visible card label is often a synthetic
        group header ("Chokladkaka, Marabou", "Kaffedryck, Löfbergs", etc.)
        rather than a real purchasable SKU. The real products live in the
        interior offers. For the app's purposes we only want the concrete child
        products when a group is expanded.
        """
        child_counts: Dict[str, int] = {}
        for product in products:
            group_key = product.get("_coop_group_key")
            if not group_key or product.get("_coop_is_group_parent"):
                continue
            child_counts[group_key] = child_counts.get(group_key, 0) + 1

        kept_products: List[Dict] = []
        dropped = 0

        for product in products:
            group_key = product.get("_coop_group_key")

            if (
                product.get("_coop_is_group_parent")
                and group_key
                and child_counts.get(group_key, 0) > 0
            ):
                dropped += 1
                continue

            kept_products.append(product)

        if dropped:
            products[:] = kept_products

        return dropped

    async def _lookup_original_price_api(
        self,
        client: httpx.AsyncClient,
        product_name: str,
        member_price: float,
        external_id: Optional[str] = None,
    ) -> Optional[float]:
        """
        Look up original price for a product via Coop's search API.

        Tries multiple search strategies to find a matching product.
        Returns original price if found, None otherwise.
        """
        if external_id:
            exact_match_price = await self._lookup_original_price_by_external_id_api(
                client,
                external_id,
                member_price,
            )
            if exact_match_price:
                return exact_match_price

        search_variants = self._generate_search_variants(product_name)

        for search_term in search_variants:
            try:
                items = await self._search_product_api(client, search_term)
                if not items:
                    continue

                result = self._find_matching_product_api(
                    items[:8], product_name, member_price
                )
                if result:
                    return result

            except Exception as e:
                logger.debug(f"API search error for '{search_term}': {e}")
                continue

        return None

    async def _lookup_original_price_by_external_id_api(
        self,
        client: httpx.AsyncClient,
        external_id: str,
        member_price: float,
    ) -> Optional[float]:
        """Try exact Coop e-commerce lookup via the physical offer's external id/EAN."""
        items = await self._search_product_api(client, external_id)
        if not items:
            return None

        exact_item = next(
            (item for item in items if str(item.get("ean") or "") == str(external_id)),
            None,
        )
        if not exact_item:
            return None

        candidate_prices = self._extract_api_compare_prices(exact_item)
        return self._select_original_price_candidate(candidate_prices, member_price)

    async def _search_product_api(
        self,
        client: httpx.AsyncClient,
        query: str
    ) -> List[Dict]:
        """
        Search for products using Coop's e-commerce search API.

        Returns list of product items from the API response.
        """
        params = {
            "api-version": "v1",
            "store": self.SEARCH_API_STORE,
            "groups": "CUSTOMER_PRIVATE",
            "device": "desktop",
            "direct": "false",
        }
        headers = {
            "ocp-apim-subscription-key": self.SEARCH_API_KEY,
            "Content-Type": "application/json",
        }
        body = {
            "query": query,
            "resultsOptions": {
                "skip": 0,
                "take": 8,
                "sortBy": [],
                "facets": [],
            },
            "relatedResultsOptions": {"skip": 0, "take": 0},
            "customData": {"searchABTest": True, "consent": False},
        }

        for attempt in range(1, self.SEARCH_API_MAX_RETRIES + 1):
            resp = await client.post(
                self.SEARCH_API_URL,
                params=params,
                headers=headers,
                json=body,
            )

            # Temporary overload / throttling: back off and try again.
            if resp.status_code in {429, 500, 502, 503, 504}:
                if attempt < self.SEARCH_API_MAX_RETRIES:
                    delay = self.SEARCH_API_RETRY_BACKOFF_SECONDS * attempt
                    logger.debug(
                        f"Coop search API retry for '{query}' "
                        f"(status={resp.status_code}, attempt={attempt}/{self.SEARCH_API_MAX_RETRIES}, "
                        f"sleep={delay:.2f}s)"
                    )
                    await asyncio.sleep(delay)
                    continue

            resp.raise_for_status()
            data = resp.json()
            return data.get("results", {}).get("items", [])

        return []

    def _generate_search_variants(self, product_name: str) -> List[str]:
        """
        Generate multiple search term variants for better matching.

        Examples:
            "Pizza, Billys" -> ["Pizza Billys", "Billys Pizza", "Pizza"]
            "Yoghurt, Arla" -> ["Yoghurt Arla", "Arla Yoghurt", "Yoghurt"]
        """
        variants = []

        # Keep decimal commas intact while still treating the trailing
        # ", Brand" part as a real separator.
        normalized_name = re.sub(r'(?<=\d),(?=\d)', '.', product_name)

        # Split brand from the final comma only. Product names themselves can
        # contain commas for weights/percentages, e.g. "0,5%, Arla".
        brand_suffix = None
        product_only = normalized_name
        if "," in normalized_name:
            candidate_product, candidate_brand = normalized_name.rsplit(",", 1)
            candidate_brand = candidate_brand.strip()
            if candidate_brand and any(ch.isalpha() for ch in candidate_brand):
                product_only = candidate_product.strip()
                brand_suffix = candidate_brand

        # Clean up remaining commas in the product part for tokenisation and
        # preserve a more exact query before falling back to shorter variants.
        clean_product = product_only.replace(",", " ").strip()
        if clean_product:
            variants.append(clean_product)

        # Tokenized fallbacks for fuzzier hits.
        clean_name = clean_product
        words = clean_name.split()

        # Variant 1: Full name (first 3 words)
        if len(words) >= 2:
            variants.append(" ".join(words[:3]))

        # Variant 2: If has brand (after comma), try "Brand Product"
        if brand_suffix:
            brand = brand_suffix.split()[0]  # First word of brand
            variants.append(f"{brand} {product_only}")

        # Variant 3: Just first word (product type)
        if words:
            first_word = words[0]
            if len(first_word) >= 4:  # Only if meaningful
                variants.append(first_word)

        # Variant 4: First two words
        if len(words) >= 2:
            variants.append(" ".join(words[:2]))

        # Remove duplicates while preserving order
        seen = set()
        unique_variants = []
        for v in variants:
            v_lower = v.lower()
            if v_lower not in seen and len(v) >= 3:
                seen.add(v_lower)
                unique_variants.append(v)

        return unique_variants[:4]  # Keep exact query plus a few fuzzy fallbacks

    def _find_matching_product_api(
        self,
        items: List[Dict],
        product_name: str,
        member_price: float
    ) -> Optional[float]:
        """
        Find a matching product in API search results and return its best
        comparable per-piece price.

        Requires at least 2 keyword matches (or 1 if product name is a single word)
        and picks the closest price to member_price (not just the first match).
        """
        product_lower = product_name.lower()
        key_words = [w.lower() for w in product_name.replace(",", " ").split() if len(w) >= 3]

        # Single-word products (e.g., "Tomater") need only 1 match
        min_matches = 1 if len(key_words) <= 1 else 2

        best_price = None
        best_diff = float('inf')

        for item in items:
            try:
                result_name = item.get("name", "")
                if not result_name:
                    continue

                result_lower = result_name.strip().lower()

                # Count keyword matches (both directions)
                matches = sum(1 for word in key_words if word in result_lower)
                if matches < min_matches:
                    result_words = [w for w in result_lower.split() if len(w) >= 3]
                    reverse_matches = sum(1 for word in result_words if word in product_lower)
                    if reverse_matches < min_matches:
                        continue

                candidate_prices = self._extract_api_compare_prices(item)
                if not candidate_prices:
                    continue

                candidate_price = self._select_original_price_candidate(
                    candidate_prices,
                    member_price,
                )
                if candidate_price is None:
                    continue

                diff = candidate_price - member_price
                if diff < best_diff:
                    best_diff = diff
                    best_price = round(candidate_price, 2)

            except Exception as e:
                logger.debug(f"Error matching API result: {e}")
                continue

        return best_price

    def _select_original_price_candidate(
        self,
        candidate_prices: List[float],
        member_price: float,
    ) -> Optional[float]:
        """
        Pick the smallest credible original price above the discounted member price.

        Coop's e-commerce results often include the active promotion price and the
        ordinary piece price at the same time. For original-price enrichment we
        want the closest strictly higher candidate, not an equal promo price.
        """
        if member_price <= 0:
            return None

        higher_prices = [price for price in candidate_prices if price > (member_price + 1e-9)]
        if not higher_prices:
            return None

        return min(higher_prices, key=lambda price: price - member_price)

    def _extract_api_compare_prices(self, item: Dict) -> List[float]:
        """Extract plausible per-piece comparison prices from Coop API data."""
        candidates: List[float] = []

        for key in ("piecePriceData", "salesPriceData"):
            price_data = item.get(key) or {}
            price = price_data.get("b2cPrice")
            if isinstance(price, (int, float)) and price > 0:
                candidates.append(round(float(price), 2))

        for promotion in item.get("onlinePromotions") or []:
            price_data = promotion.get("priceData") or {}
            price = price_data.get("b2cPrice")
            if not isinstance(price, (int, float)) or price <= 0:
                continue

            promotion_type = (promotion.get("type") or "").upper()
            quantity = promotion.get("numberOfProductRequired") or 1

            if promotion_type == "MULTI_BUY_FIXED_PRICE" and quantity > 1:
                price = float(price) / float(quantity)

            candidates.append(round(float(price), 2))

        # Preserve order while removing duplicates
        unique_candidates = []
        seen = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            unique_candidates.append(candidate)

        return unique_candidates
