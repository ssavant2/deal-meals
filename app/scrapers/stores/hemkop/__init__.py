"""
Hemköp Store Plugin

Scrapes offers from Hemköp via Axfood REST API.
Hemköp and Willys share the same Axfood backend, so the API structure
and product JSON format are identical.

For e-commerce (home delivery), Playwright is used ONCE to resolve the
delivery address into a virtual store ID via hemkop.se's address lookup.
All actual product scraping is done via pure REST API calls.
"""

from typing import List, Dict, Optional
from scrapers.stores.base import StorePlugin, StoreConfig, StoreConfigField, StoreScrapeResult
from languages.sv.category_utils import guess_category as shared_guess_category
from languages.sv.category_utils import normalize_api_category as shared_normalize_category
from loguru import logger
from scrapers.stores.weight_utils import parse_weight
from languages.sv.normalization import fix_swedish_chars
from constants_timeouts import HTTP_TIMEOUT
import httpx
import re
import asyncio
from utils.security import ssrf_safe_event_hook
from datetime import datetime, timezone


# Polite delay between API requests (seconds)
API_REQUEST_DELAY = 10


class HemkopStore(StorePlugin):
    """Hemköp store plugin - API scraping with Playwright address resolution."""

    def __init__(self):
        self.base_url = "https://www.hemkop.se"
        self.offline_campaigns_api = f"{self.base_url}/search/campaigns/offline"
        self.online_campaigns_api = f"{self.base_url}/search/campaigns/online"
        self.product_api = f"{self.base_url}/axfood/rest/p"
        self.store_list_api = f"{self.base_url}/axfood/rest/store"

    @property
    def config(self) -> StoreConfig:
        return StoreConfig(
            id="hemkop",
            name="Hemköp",
            logo="/scrapers/stores/hemkop/logo.svg",
            color="#ee1c2e",
            url="https://www.hemkop.se",
            enabled=True,
            has_credentials=False,
            description="Handla smart, bra mat"
        )

    def get_config_fields(self) -> List[StoreConfigField]:
        """Define Hemköp configuration fields."""
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
                        "description": "Erbjudanden för en specifik butik"
                    }
                ],
                default="ehandel"
            ),
            StoreConfigField(
                key="location_search",
                label="Sök specifik butik (stad eller adress)",
                field_type="search",
                placeholder="t.ex. göteborg, stockholm...",
                depends_on={"field": "location_type", "value": "butik"}
            )
        ]

    async def search_locations(self, query: str) -> List[Dict]:
        """Search for Hemköp store locations."""
        from scrapers.stores.hemkop.hemkop_store_finder import hemkop_store_finder

        cache_key = self._build_location_search_cache_key("physical", query)

        async def load_locations() -> List[Dict]:
            stores = await hemkop_store_finder.search_stores(query)
            return [
                {
                    "id": s["store_id"],
                    "name": s["name"],
                    "address": s["address"],
                    "type": s["type"]
                }
                for s in stores
            ]

        return await self._get_or_cache_location_search(cache_key, load_locations)

    async def scrape_offers(self, credentials: Optional[Dict] = None) -> StoreScrapeResult:
        """Scrape offers from Hemköp."""
        logger.info("Starting Hemköp scraping...")

        location_type = credentials.get('location_type', 'ehandel') if credentials else 'ehandel'
        location_id = credentials.get('location_id') if credentials else None

        if location_type == 'butik' and location_id:
            logger.info(f"Scraping offline campaigns for store: {location_id}")
            products = await self._scrape_store_campaigns(location_id)
        else:
            logger.info("Scraping online campaigns (e-commerce)")

            # Resolve delivery address to store ID via Playwright
            delivery = self._get_delivery_address()
            store_id = await self._resolve_delivery_store_id(delivery)

            logger.info(f"Waiting {API_REQUEST_DELAY}s before fetching campaigns (polite delay)...")
            await asyncio.sleep(API_REQUEST_DELAY)

            products = await self._scrape_online_campaigns(store_id)

        logger.success(f"Scraped {len(products)} products from Hemköp ({location_type})")
        return self._scrape_result_from_products(
            products,
            location_type=location_type,
        )

    def _get_delivery_address(self) -> Dict[str, Optional[str]]:
        """Read delivery address from user_preferences table."""
        result = {'street': None, 'postal_code': None, 'city': None}
        try:
            from database import get_db_session
            from sqlalchemy import text

            with get_db_session() as db:
                row = db.execute(text(
                    "SELECT delivery_street_address, delivery_postal_code, delivery_city "
                    "FROM user_preferences LIMIT 1"
                )).fetchone()

                if row:
                    result['street'] = row[0]
                    result['postal_code'] = row[1]
                    result['city'] = row[2]
                    logger.info(f"Saved delivery address: {row[0]}, {row[1]} {row[2]}")
        except Exception as e:
            logger.warning(f"Could not read delivery address: {e}")

        return result

    # ==================== PLAYWRIGHT ADDRESS RESOLVER ====================

    async def _resolve_delivery_store_id(self, delivery: Dict) -> str:
        """
        Resolve delivery address to a Hemköp store ID using Playwright.

        Hemköp assigns a virtual e-commerce store ID (not visible in any public API)
        based on the delivery address. This method navigates hemkop.se, enters the
        address in the delivery dialog, and reads the assigned store ID from localStorage.

        Falls back to city-based search if Playwright fails.
        """
        street = delivery.get('street')
        if not street:
            logger.warning("No delivery address saved, using fallback store selection")
            return await self._get_online_store_id(delivery=delivery)

        try:
            from playwright.async_api import async_playwright

            logger.info(f"Resolving delivery store for: {street}")

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 900},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                page = await context.new_page()

                try:
                    store_id = await asyncio.wait_for(
                        self._playwright_address_flow(page, street),
                        timeout=120.0
                    )
                    if store_id:
                        logger.success(f"Resolved delivery store ID: {store_id}")
                        return store_id
                finally:
                    await browser.close()

        except ImportError:
            logger.warning("Playwright not installed, using fallback")
        except Exception as e:
            logger.error(f"Playwright address resolution failed: {e}")

        # Fallback: city-based store search (may return offers from different location)
        logger.warning("Address resolution failed, falling back to city-based store selection")
        return await self._get_online_store_id(delivery=delivery)

    async def _playwright_address_flow(self, page, street: str) -> Optional[str]:
        """
        Execute the address lookup flow on hemkop.se.

        Flow: Open dialog → 'Hemleverans' → type address → click suggestion → 'Bekräfta'
        Returns the promotionStoreId from localStorage, or None on failure.
        """
        # Step 1: Navigate to hemkop.se
        logger.info("Step 1: Navigating to hemkop.se...")
        await page.goto('https://www.hemkop.se', wait_until='domcontentloaded', timeout=30000)

        # Accept cookie consent if present
        try:
            cookie_btn = await page.query_selector('button:has-text("Acceptera")')
            if not cookie_btn:
                cookie_btn = await page.query_selector('button:has-text("Godkänn")')
            if cookie_btn:
                await cookie_btn.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass

        # Step 2: Open delivery dialog
        logger.info("Step 2: Opening delivery dialog...")
        toggle_selectors = [
            'button[aria-label*="leverans"]',
            '[data-testid="delivery-picker-toggle"]',
            'button:has-text("Välj leveranssätt")',
        ]

        toggle_found = False
        for sel in toggle_selectors:
            try:
                toggle = await page.wait_for_selector(sel, timeout=5000)
                if toggle and await toggle.is_visible():
                    await toggle.click()
                    toggle_found = True
                    logger.info(f"  Clicked delivery toggle: {sel}")
                    break
            except Exception:
                continue

        if not toggle_found:
            logger.error("Could not find delivery dialog toggle")
            return None

        # Step 3: Click home delivery ('Hemleverans') - wait for button to appear
        logger.info("Step 3: Clicking home delivery ('Hemleverans')...")
        try:
            hemleverans_btn = await page.wait_for_selector('button:has-text("Hemleverans")', timeout=5000)
            if hemleverans_btn:
                await hemleverans_btn.click()
            else:
                logger.error("Could not find 'Hemleverans' button")
                return None
        except Exception:
            logger.error("Could not click home delivery ('Hemleverans') button")
            return None

        # Step 4: Type address in input field - wait for input to appear
        logger.info(f"Step 4: Typing address: {street}")
        address_input = None
        for sel in ['input#address', 'input[name="address"]', 'input[placeholder*="adress"]']:
            try:
                address_input = await page.wait_for_selector(sel, timeout=5000)
                if address_input and await address_input.is_visible():
                    break
                address_input = None
            except Exception:
                continue

        if not address_input:
            logger.error("Could not find address input field")
            return None

        await address_input.click()
        await address_input.type(street, delay=100)

        # Step 5: Click autocomplete suggestion - wait for it to appear
        logger.info("Step 5: Clicking autocomplete suggestion...")
        try:
            suggestion = page.locator(f'li:has-text("{street}")')
            await suggestion.first.wait_for(state='visible', timeout=10000)
        except Exception:
            logger.error(f"No autocomplete suggestion found for: {street}")
            return None

        await suggestion.first.click(timeout=5000)

        # Step 6: Click confirm ('Bekräfta') - wait for button to appear
        logger.info("Step 6: Clicking confirm ('Bekräfta')...")
        try:
            confirm_btn = page.locator('button:has-text("Bekräfta")')
            await confirm_btn.first.wait_for(state='visible', timeout=5000)
        except Exception:
            logger.error("Could not find confirm ('Bekräfta') button")
            return None

        await confirm_btn.first.click(timeout=5000)

        # Step 7: Wait for localStorage to update, then read promotionStoreId
        logger.info("Step 7: Reading store ID from localStorage...")
        try:
            await page.wait_for_function(
                "() => { try { return !!JSON.parse(localStorage.getItem('promotionStore'))?.promotionStoreId; } catch { return false; } }",
                timeout=15000
            )
        except Exception:
            logger.warning("Timed out waiting for promotionStoreId in localStorage")

        store_data = await page.evaluate('''() => {
            const raw = localStorage.getItem('promotionStore');
            if (!raw) return null;
            try { return JSON.parse(raw); } catch { return null; }
        }''')

        if store_data and store_data.get('promotionStoreId'):
            store_id = store_data['promotionStoreId']
            logger.success(f"Resolved store ID: {store_id} for address: {street}")
            return store_id

        logger.warning("promotionStoreId not found in localStorage after address flow")
        return None

    # ==================== API SCRAPING (OFFLINE - PHYSICAL STORE) ====================

    async def _scrape_store_campaigns(self, store_id: str) -> List[Dict]:
        """Scrape store-specific campaigns via offline API."""
        products = []

        try:
            logger.info(f"Waiting {API_REQUEST_DELAY}s before API request (polite delay)...")
            await asyncio.sleep(API_REQUEST_DELAY)

            params = {
                'q': store_id,
                'type': 'PERSONAL_GENERAL',
                'page': 0,
                'size': 400
            }

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }

            async with httpx.AsyncClient(event_hooks={"request": [ssrf_safe_event_hook]}) as client:
                response = await client.get(
                    self.offline_campaigns_api,
                    params=params,
                    headers=headers,
                    timeout=HTTP_TIMEOUT
                )

            if response.status_code != 200:
                logger.error(f"Offline API returned status {response.status_code}")
                return []

            try:
                data = response.json()
            except Exception:
                logger.error(f"Offline API returned non-JSON response (status {response.status_code})")
                return []
            results = data.get('results', [])
            if not isinstance(results, list):
                logger.error(f"Offline API 'results' is not a list: {type(results)}")
                return []

            logger.info(f"Found {len(results)} offline campaign products from API")

            for item in results:
                try:
                    product = self._parse_campaign_product(item, is_online=False)
                    if product:
                        products.append(product)
                except Exception as e:
                    logger.warning(f"Failed to parse offline product: {e}")
                    continue

            return products

        except Exception as e:
            logger.error(f"Error scraping store campaigns: {e}")
            return []

    # ==================== API SCRAPING (ONLINE - E-COMMERCE) ====================

    async def _get_online_store_id(self, delivery: Optional[Dict] = None) -> str:
        """
        Find an online-capable Hemköp store ID for e-commerce campaigns.

        The store list API (/axfood/rest/store) is authoritative for the
        `onlineStore` flag. If a delivery city is provided, prefer an online
        store whose town matches; otherwise fall back to the first online
        store. Raises RuntimeError if no online store can be found.
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }

        logger.info(f"Waiting {API_REQUEST_DELAY}s before fetching store list (polite delay)...")
        await asyncio.sleep(API_REQUEST_DELAY)

        async with httpx.AsyncClient(event_hooks={"request": [ssrf_safe_event_hook]}) as client:
            response = await client.get(
                self.store_list_api,
                headers=headers,
                timeout=HTTP_TIMEOUT
            )

        response.raise_for_status()
        stores = response.json()
        online_stores = [s for s in stores if s.get('onlineStore') and s.get('storeId')]

        if not online_stores:
            raise RuntimeError("No online Hemköp stores found in store list")

        city = ((delivery or {}).get('city') or '').strip().lower()
        if city:
            for store in online_stores:
                town = ((store.get('address') or {}).get('town') or '').lower()
                if city in town or town in city:
                    logger.info(f"Using online store in {delivery['city']}: {store.get('name')} (ID: {store['storeId']})")
                    return str(store['storeId'])
            logger.warning(f"No online Hemköp store matched city '{delivery['city']}', using first online store")

        first = online_stores[0]
        logger.info(f"Using first online store: {first.get('name')} (ID: {first['storeId']})")
        return str(first['storeId'])

    async def _scrape_online_campaigns(self, store_id: str) -> List[Dict]:
        """Scrape e-commerce campaigns via online API."""
        products = []

        try:
            params = {
                'q': store_id,
                'page': 0,
                'size': 400
            }

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }

            async with httpx.AsyncClient(event_hooks={"request": [ssrf_safe_event_hook]}) as client:
                response = await client.get(
                    self.online_campaigns_api,
                    params=params,
                    headers=headers,
                    timeout=HTTP_TIMEOUT
                )

            if response.status_code != 200:
                logger.error(f"Online API returned status {response.status_code}")
                return []

            try:
                data = response.json()
            except Exception:
                logger.error(f"Online API returned non-JSON response (status {response.status_code})")
                return []
            results = data.get('results', [])
            if not isinstance(results, list):
                logger.error(f"Online API 'results' is not a list: {type(results)}")
                return []
            total = data.get('pagination', {}).get('totalNumberOfResults', len(results))

            logger.info(f"Found {len(results)} online campaign products (total: {total})")

            # Paginate if there are more results
            if total > len(results):
                page = 1
                max_pages = 50  # Safety limit to prevent infinite pagination
                async with httpx.AsyncClient(event_hooks={"request": [ssrf_safe_event_hook]}) as client:
                    while len(results) < total and page <= max_pages:
                        logger.info(f"Waiting {API_REQUEST_DELAY}s before next page (polite delay)...")
                        await asyncio.sleep(API_REQUEST_DELAY)

                        params['page'] = page
                        resp = await client.get(
                            self.online_campaigns_api,
                            params=params,
                            headers=headers,
                            timeout=HTTP_TIMEOUT
                        )
                        if resp.status_code != 200:
                            break
                        try:
                            page_data = resp.json()
                        except Exception:
                            logger.warning(f"Pagination page {page} returned non-JSON, stopping")
                            break
                        page_results = page_data.get('results', [])
                        if not isinstance(page_results, list) or not page_results:
                            break
                        results.extend(page_results)
                        page += 1

                logger.info(f"Total after pagination: {len(results)} products")

            for item in results:
                try:
                    product = self._parse_campaign_product(item, is_online=True)
                    if product:
                        products.append(product)
                except Exception as e:
                    logger.warning(f"Failed to parse online product: {e}")
                    continue

            return products

        except Exception as e:
            logger.error(f"Error scraping online campaigns: {e}")
            return []

    # ==================== PRODUCT PARSING ====================

    def _parse_campaign_product(self, item: dict, is_online: bool = False) -> Optional[Dict]:
        """
        Parse a product from campaign API.

        Same JSON structure as Willys (both Axfood backends).
        Combines name + description + manufacturer for rich product names.
        """
        try:
            # Product name extraction (V4 - same as Willys)
            api_name = (item.get('name') or '').strip()
            manufacturer = (item.get('manufacturer') or '').strip()
            promotions = item.get('potentialPromotions', [])

            description = ''
            if promotions:
                description = (promotions[0].get('description') or '').strip()

            # Generic words to skip in name building
            skip_words = [
                'olika sorter', 'klass 1', 'djupfryst', 'djupfrysta',
                'gäller ej', 'max', 'hushåll', 'skivad', 'skivat'
            ]

            parts = []

            if api_name:
                parts.append(api_name)

            if description:
                desc_lower = description.lower()
                is_generic = any(skip in desc_lower for skip in skip_words)
                if not is_generic and desc_lower not in api_name.lower():
                    parts.append(description)

            if manufacturer:
                mfg_lower = manufacturer.lower()
                already_included = any(
                    mfg_lower in part.lower()
                    for part in parts
                )
                if not already_included:
                    parts.append(manufacturer)

            product_name = ' '.join(parts).strip()

            if not product_name or len(product_name) < 2:
                return None

            # Price extraction. The ehandel (online) and butik (offline) APIs use
            # different semantics for the same fields despite sharing the Axfood
            # backend:
            #   ehandel: promo.price is a dict with per-unit value (e.g. {value: 13.0}),
            #            API pre-divides for multi-buy.
            #   butik:   promo.price is a float with the TOTAL bundle price (e.g. 169.0
            #            for "2 för 169 kr"), and is None for per-kg items where the
            #            deal is only in rewardLabel (e.g. "69,95 kr/kg").
            price_str = item.get('price')
            original_price = self._parse_price(price_str) if price_str else 0.0

            unit = self._parse_unit(item.get('priceUnit', 'kr/st'))

            deal_price = 0.0
            savings = 0.0

            if promotions:
                promo = promotions[0]
                promo_price_obj = promo.get('price')
                qualifying_count = promo.get('qualifyingCount') or 1
                reward_label = promo.get('rewardLabel') or ''

                if isinstance(promo_price_obj, dict):
                    # Ehandel: already per-unit
                    deal_price = float(promo_price_obj.get('value', 0))
                elif isinstance(promo_price_obj, (int, float)):
                    # Butik: total bundle price - divide by qty for multi-buy
                    deal_price = float(promo_price_obj)
                    if qualifying_count > 1:
                        deal_price = round(deal_price / qualifying_count, 2)
                elif promo_price_obj is not None:
                    deal_price = self._parse_price(str(promo_price_obj))

                # Butik per-kg items: promo.price is None, deal is in rewardLabel
                # ("69,95 kr/kg"). Use displayVolume to convert to total price.
                if deal_price == 0 and 'kr/kg' in reward_label.lower():
                    deal_per_kg = self._parse_price(reward_label.split('/')[0])
                    weight_grams = parse_weight(item.get('displayVolume') or '')
                    if deal_per_kg > 0 and weight_grams and weight_grams > 0:
                        weight_kg = weight_grams / 1000.0
                        deal_price = round(deal_per_kg * weight_kg, 2)
                        original_price = round(original_price * weight_kg, 2)
                        unit = 'st'

                if deal_price > 0 and original_price > deal_price:
                    savings = round(original_price - deal_price, 2)

            # Use deal price if available, otherwise original price
            price = deal_price if deal_price > 0 else original_price
            if original_price == 0 and deal_price > 0:
                original_price = deal_price

            # Skip items with no actual savings - these are not real deals.
            # This already filters out flat "Alltid bra pris" items (regular = deal);
            # multi-buy "Alltid bra pris" items (e.g., "2 för 26 kr") have real savings
            # and should be kept.
            if savings == 0:
                logger.debug(f"Skipping item with no savings: {product_name} (price={price}, orig={original_price})")
                return None

            # Image
            image_url = None
            if 'image' in item and item['image']:
                image_url = item['image'].get('url')

            # Product URL via mainProductCode from promotions
            # Hemköp resolves /produkt/{code} regardless of name slug, so we just need the code
            product_url = None
            product_code = None
            if promotions:
                product_code = promotions[0].get('mainProductCode')
            if not product_code:
                product_code = item.get('code') or item.get('productCode') or item.get('id')
            if product_code:
                product_url = f"{self.base_url}/produkt/{product_code}"

            # Package weight from API (same field as Willys - shared Axfood backend)
            weight_grams = None
            volume_str = (item.get('displayVolume') or '').strip()
            if volume_str:
                weight_grams = parse_weight(volume_str)

            # Category - normalize API category to English (same as ICA)
            # e.g. "kott-chark-och-fagel|kott|farsfars" → "meat"
            raw_category = item.get('googleAnalyticsCategory') or ''
            if raw_category:
                category = shared_normalize_category(raw_category)
            else:
                category = shared_guess_category(product_name)

            if price <= 0:
                logger.debug(f"Skipping product with zero/negative price: '{product_name}'")
                return None

            return {
                "name": product_name,
                "price": round(price, 2),
                "original_price": round(original_price, 2),
                "savings": round(savings, 2),
                "unit": unit,
                "category": category,
                "brand": manufacturer.upper() if manufacturer else None,
                "image_url": image_url,
                "product_url": product_url,
                "weight_grams": weight_grams,
                "scraped_at": datetime.now(timezone.utc)
            }

        except Exception as e:
            logger.debug(f"Error parsing campaign product: {e}")
            return None

    # ==================== HELPER FUNCTIONS ====================

    # _parse_price and _parse_unit inherited from StorePlugin base class
