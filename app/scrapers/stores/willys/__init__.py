"""
Willys Store Plugin

Uses Willys API categories when available,
guessing as fallback.
"""

from typing import List, Dict, Optional
from scrapers.stores.base import StorePlugin, StoreConfig, StoreConfigField, StoreScrapeResult
from languages.sv.category_utils import (
    guess_category as shared_guess_category,
    normalize_api_category as shared_normalize_category,
    IMPORTED_MEAT_BRANDS,
)
from scrapers.stores.weight_utils import parse_weight
from loguru import logger
from languages.sv.normalization import fix_swedish_chars
from constants_timeouts import HTTP_TIMEOUT, PAGE_LOAD_TIMEOUT, PAGE_NETWORK_IDLE_TIMEOUT
import httpx
import re
from datetime import datetime, timezone
from utils.security import ssrf_safe_event_hook
from pathlib import Path
import asyncio


def log_filtered_product(store: str, product_name: str, reason: str, manufacturer: str = None):
    """
    Log filtered products to a dedicated file for easy review.
    File: /app/logs/filtered_products.log (inside container)
    Host: ./app/logs/filtered_products.log
    """
    try:
        log_path = Path("/app/logs/filtered_products.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        mfg_info = f" (tillverkare: {manufacturer})" if manufacturer else ""

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {store}: {product_name}{mfg_info} - {reason}\n")
    except Exception as e:
        logger.debug(f"Could not write to filtered_products.log: {e}")

class WillysStore(StorePlugin):
    """Willys store plugin with improved categorization."""

    # Polite delay before butik campaign API calls (seconds).
    STORE_API_DELAY = 1.0

    # ==================== ORIGIN VERIFICATION CONFIG ====================
    # Products to verify via API for manufacturer/origin info.
    # Used as early filter during scraping (belt-and-suspenders with recipe_matcher).
    # Brand list imported from category_utils.py (shared across all scrapers).
    PRODUCTS_TO_VERIFY_ORIGIN = [
        # Fläskfilé
        'fläskfilé', 'fläskfile', 'flaskfile', 'flaskfilé',
        'fläsk filé', 'fläsk file',
        # Burgare (frysta importerade)
        'burger', 'burgare', 'beef burger',
        # Lamm (often imported from NZ/Australia)
        'lammracks', 'lammrack', 'lammstek', 'lammkotlett',
    ]
    # ====================================================================

    def __init__(self):
        self.base_url = "https://www.willys.se"
        self.campaigns_api = f"{self.base_url}/search/campaigns/offline"
        self.ehandel_url = f"{self.base_url}/erbjudanden/ehandel"
        self.product_api = f"{self.base_url}/axfood/rest/p"  # Product details API
    
    @property
    def config(self) -> StoreConfig:
        return StoreConfig(
            id="willys",
            name="Willys",
            logo="/scrapers/stores/willys/logo.svg",
            color="#e30613",
            url="https://www.willys.se",
            enabled=True,
            has_credentials=False,  # No login required for Willys
            description="Sveriges billigaste matkasse"
        )

    def get_config_fields(self) -> List[StoreConfigField]:
        """Define Willys configuration fields."""
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
        """Search for Willys store locations."""
        from scrapers.stores.willys.willys_store_finder import willys_store_finder

        cache_key = self._build_location_search_cache_key("physical", query)

        async def load_locations() -> List[Dict]:
            stores = await willys_store_finder.search_stores(query)
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
        """Scrape offers from Willys."""

        logger.info("Starting Willys scraping...")
        # Reset per-run metadata so one scrape mode never leaks UI counts into the next.
        self._scrape_meta = None

        location_type = credentials.get('location_type', 'ehandel') if credentials else 'ehandel'
        location_id = credentials.get('location_id') if credentials else None
        session_cookies = credentials.get('session_cookies') if credentials else None

        if location_type == 'butik' and location_id:
            logger.info(f"Using API scraping for store: {location_id}")
            products = await self._scrape_store_campaigns(location_id)
            self._scrape_meta = {
                "base_count": len(products),
                "variant_count": 0,
            }
        else:
            logger.info("Using API-first scraping for e-commerce")

            # Fetch delivery address from database (CRITICAL for correct offers!)
            delivery_address = None
            try:
                from database import get_db_session
                from sqlalchemy import text

                with get_db_session() as db:
                    addr = db.execute(text(
                        "SELECT delivery_street_address, delivery_postal_code, delivery_city "
                        "FROM user_preferences LIMIT 1"
                    )).fetchone()

                    if addr and addr[0]:
                        delivery_address = {
                            'street': addr[0],
                            'postal_code': addr[1],
                            'city': addr[2]
                        }
                        logger.info(f"Using delivery address: {addr[0]}, {addr[1]} {addr[2]}")
            except Exception as e:
                logger.warning(f"Could not fetch delivery address: {e}")

            store_code = await self._resolve_ehandel_store_code(
                delivery_address=delivery_address,
                session_cookies=session_cookies,
            )
            if store_code:
                logger.info(f"Using API-based e-commerce scraping with store code: {store_code}")
                products = await self._scrape_ehandel_via_api(
                    store_code,
                    session_cookies=session_cookies,
                )
            else:
                logger.warning("Could not resolve e-commerce store via API - falling back to Playwright")
                products = await self._scrape_ehandel_playwright(
                    cookies=session_cookies,
                    delivery_address=delivery_address
                )

        logger.success(f"Scraped {len(products)} products from Willys ({location_type})")
        return self._scrape_result_from_products(
            products,
            location_type=location_type,
        )
    
    
    # ==================== API SCRAPING (STORE) ====================
    
    async def _scrape_store_campaigns(self, store_id: str) -> List[Dict]:
        """Scrape store-specific campaigns via API."""
        
        products = []
        
        try:
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
                await asyncio.sleep(self.STORE_API_DELAY)
                response = await client.get(
                    self.campaigns_api,
                    params=params,
                    headers=headers,
                    timeout=HTTP_TIMEOUT
                )

            if response.status_code != 200:
                logger.error(f"API returned status {response.status_code}")
                return []

            try:
                data = response.json()
            except Exception:
                logger.error(f"API returned non-JSON response (status {response.status_code})")
                return []
            results = data.get('results', [])
            if not isinstance(results, list):
                logger.error(f"API 'results' is not a list: {type(results)}")
                return []

            logger.info(f"Found {len(results)} campaign products from API")

            # Debug: Log first item keys if needed
            if results:
                logger.debug(f"API item keys: {list(results[0].keys())}")

            for item in results:
                try:
                    product = self._parse_campaign_product(item)
                    if product:
                        products.append(product)
                except Exception as e:
                    logger.warning(f"Failed to parse API product: {e}")
                    continue
            
            return products
            
        except Exception as e:
            logger.error(f"Error scraping store campaigns: {e}")
            return []

    def _build_api_headers(self) -> Dict[str, str]:
        """Default headers for Willys HTTP API calls."""
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }

    def _build_httpx_cookie_jar(self, session_cookies: Optional[list]) -> Optional[httpx.Cookies]:
        """Convert Playwright-style cookies into an httpx cookie jar."""
        if not session_cookies:
            return None

        jar = httpx.Cookies()
        for cookie in session_cookies:
            if not isinstance(cookie, dict):
                continue

            name = cookie.get('name')
            value = cookie.get('value')
            if not name or value is None:
                continue

            domain = (cookie.get('domain') or 'www.willys.se').lstrip('.')
            path = cookie.get('path') or '/'
            jar.set(name, value, domain=domain, path=path)

        return jar

    async def _get_active_ehandel_store_code(self, session_cookies: Optional[list] = None) -> Optional[str]:
        """Return Willys active/default online store code when no address-specific code is available."""
        try:
            async with httpx.AsyncClient(
                event_hooks={"request": [ssrf_safe_event_hook]},
                headers=self._build_api_headers(),
                cookies=self._build_httpx_cookie_jar(session_cookies),
                follow_redirects=True,
                timeout=HTTP_TIMEOUT,
            ) as client:
                response = await client.get(f"{self.base_url}/axfood/rest/store/active")

            if response.status_code != 200:
                logger.warning(f"Active store API returned status {response.status_code}")
                return None

            data = response.json()
            store_id = data.get('storeId')
            if store_id:
                store_id = str(store_id)
                logger.info(f"Using active/default e-commerce store code: {store_id}")
                return store_id

            logger.warning("Active store API did not return a storeId")
            return None
        except Exception as e:
            logger.warning(f"Could not fetch active e-commerce store code: {e}")
            return None

    async def _resolve_delivery_store_code(
        self,
        delivery_address: Optional[Dict],
        session_cookies: Optional[list] = None,
    ) -> Optional[str]:
        """Resolve the delivery-specific Willys online store code from a delivery address."""
        if not delivery_address:
            return None

        postal_code = re.sub(r'\s+', '', str(delivery_address.get('postal_code') or ''))
        if not postal_code:
            logger.warning("Delivery address has no postal code; cannot resolve delivery store code")
            return None

        api_url = f"{self.base_url}/axfood/rest/shipping/delivery/{postal_code}/deliverability"
        try:
            async with httpx.AsyncClient(
                event_hooks={"request": [ssrf_safe_event_hook]},
                headers=self._build_api_headers(),
                cookies=self._build_httpx_cookie_jar(session_cookies),
                follow_redirects=True,
                timeout=HTTP_TIMEOUT,
            ) as client:
                response = await client.get(api_url, params={'b2b': 'false'})

            if response.status_code != 200:
                logger.warning(f"Delivery store API returned status {response.status_code} for postal code {postal_code}")
                return None

            data = response.json()
            store_id = data.get('deliveryStoreId')
            if store_id:
                store_id = str(store_id)
                logger.info(f"Resolved delivery store code {store_id} for postal code {postal_code}")
                return store_id

            logger.warning(f"No deliveryStoreId returned for postal code {postal_code}: {data}")
            return None
        except Exception as e:
            logger.warning(f"Could not resolve delivery store code for {postal_code}: {e}")
            return None

    async def _resolve_ehandel_store_code(
        self,
        delivery_address: Optional[Dict],
        session_cookies: Optional[list] = None,
    ) -> Optional[str]:
        """Resolve the best store code for Willys e-commerce offers."""
        store_code = await self._resolve_delivery_store_code(
            delivery_address,
            session_cookies=session_cookies,
        )
        if store_code:
            return store_code

        if delivery_address:
            logger.warning("Falling back to Willys active/default e-commerce store after delivery lookup failure")

        return await self._get_active_ehandel_store_code(session_cookies=session_cookies)
    
    
    def _parse_campaign_product(self, item: dict, url_prefix: str = "offline") -> Optional[Dict]:
        """Parse a product from campaign API with improved name extraction V4.

        Args:
            item: Product dict from Willys campaign API.
            url_prefix: URL prefix for product links ('offline' for butik, 'online' for ehandel).
        """

        try:
            # IMPROVED NAME EXTRACTION V4
            # Combine name + description + manufacturer intelligently

            # Use 'or' to convert None to empty string before .strip()
            api_name = (item.get('name') or '').strip()
            manufacturer = (item.get('manufacturer') or '').strip()
            promotions = item.get('potentialPromotions', [])

            # Get description from promotion
            description = ''
            if promotions and len(promotions) > 0:
                description = (promotions[0].get('description') or '').strip()

            # List of words NOT to add (generic)
            skip_words = [
                'olika sorter', 'klass 1', 'djupfryst', 'djupfrysta',
                'gäller ej', 'max', 'hushåll', 'skivad', 'skivat'
            ]

            # Build product name by combining fields
            parts = []

            # Always add name
            if api_name:
                parts.append(api_name)

            # Add description if not generic
            if description:
                desc_lower = description.lower()
                is_generic = any(skip in desc_lower for skip in skip_words)

                # Only add if it provides valuable info
                if not is_generic and desc_lower not in api_name.lower():
                    parts.append(description)

            # Add manufacturer if it adds value
            if manufacturer:
                mfg_lower = manufacturer.lower()
                # Add if not already in name or description
                already_included = any(
                    mfg_lower in part.lower()
                    for part in parts
                )
                if not already_included:
                    parts.append(manufacturer)

            # Combine all parts
            product_name = ' '.join(parts).strip()

            if not product_name or len(product_name) < 2:
                logger.debug(f"Invalid product name: '{product_name}'")
                return None

            logger.debug(f"Built: '{product_name}' from name='{api_name}', desc='{description}', mfg='{manufacturer}'")

            # Price extraction
            price_str = item.get('price')
            price = 0.0

            # For "Tillfälligt parti" products, top-level price is null
            # Price is instead in promotions[0]['price']
            if not price_str and promotions:
                promo = promotions[0]
                promo_price = promo.get('price')
                if promo_price:
                    # price can be a dict (online API) or a string (offline API)
                    if isinstance(promo_price, dict):
                        price = float(promo_price.get('value', 0))
                    else:
                        price = float(promo_price)
            else:
                price = self._parse_price(price_str)

            # Unit
            unit = self._parse_unit(item.get('priceUnit', 'kr/st'))

            # Campaign info (savings)
            original_price = price
            savings = 0.0
            is_temporary_deal = False
            is_multi_buy = False
            multi_buy_quantity = 1
            multi_buy_total_price = 0.0

            if promotions:
                promo = promotions[0]
                save_price_str = (promo.get('savePrice') or '')  # Convert None to empty string

                # Multi-buy detection from API (e.g., "6 för 50,00")
                qualifying_count = promo.get('qualifyingCount')
                reward_label = promo.get('rewardLabel', '')
                condition_label = promo.get('conditionLabelFormatted', '')
                _cart_label = promo.get('cartLabelFormatted', '')

                if qualifying_count and qualifying_count > 1 and reward_label:
                    is_multi_buy = True
                    multi_buy_quantity = int(qualifying_count)
                    multi_buy_total_price = self._parse_price(reward_label.split('/')[0])
                    if multi_buy_total_price > 0:
                        price = round(multi_buy_total_price / multi_buy_quantity, 2)
                    logger.debug(f"{api_name}: Multi-buy from API: {multi_buy_quantity} for {multi_buy_total_price} kr")
                elif condition_label and re.search(r'(\d+)\s+för', condition_label, re.IGNORECASE):
                    # Fallback: parse from conditionLabelFormatted
                    m = re.search(r'(\d+)\s+för', condition_label, re.IGNORECASE)
                    if m and reward_label:
                        is_multi_buy = True
                        multi_buy_quantity = int(m.group(1))
                        multi_buy_total_price = self._parse_price(reward_label.split('/')[0])
                        if multi_buy_total_price > 0:
                            price = round(multi_buy_total_price / multi_buy_quantity, 2)

                # Check for "Tillfälligt parti" (temporary deals) - ONLY if top-level price was null
                if not item.get('price') and 'tillfälligt' in save_price_str.lower():
                    is_temporary_deal = True
                    # Simulate 50% discount for recipe matching priority
                    original_price = price * 2
                    savings = price
                    logger.debug(f"Temporary deal ('Tillfälligt parti'): {api_name} - simulating 50% discount")
                elif not is_multi_buy:
                    # Normal campaign - extract actual savings
                    # Historical price
                    historical_price_str = item.get('offlinePromotionLowestHistoricalPrice', '')
                    if historical_price_str:
                        historical_price = self._parse_price(historical_price_str)
                        if historical_price > price:
                            original_price = historical_price

                    # Savings from "Spara X kr"
                    if save_price_str and 'spara' in save_price_str.lower():
                        savings = self._parse_price(save_price_str.replace('Spara', '').strip())

                    # Fallback: extract campaign price from rewardLabel (e.g., "14,90/st")
                    # Many offers have no savePrice but DO have a rewardLabel with the deal price
                    if savings == 0 and reward_label:
                        reward_price = self._parse_price(reward_label.split('/')[0])
                        if 0 < reward_price < price:
                            savings = round(price - reward_price, 2)
                            original_price = price

                    if savings > 0 and original_price == price:
                        original_price = price + savings

                    # Kg-priced items: item['price'] may be the ORIGINAL per-kg
                    # price, not the campaign price. If rewardLabel shows a lower
                    # price, that IS the actual campaign price.
                    # Example: Hushållsost 26% — item['price']=119.90 (orig/kg),
                    # rewardLabel="79,90/kg" (campaign), savePrice="Spara 40,00"
                    if reward_label:
                        reward_price = self._parse_price(reward_label.split('/')[0])
                        if 0 < reward_price < price:
                            original_price = price
                            savings = round(price - reward_price, 2)
                            price = reward_price

                # For multi-buy: calculate savings from original per-item price
                if is_multi_buy:
                    # priceValue is sometimes the normal per-item price, but for
                    # "Välj & Blanda" deals it can be a campaign price lower than
                    # the multi-buy per-item price. Only use it if it's actually
                    # higher than the deal price.
                    normal_price = item.get('priceValue')
                    if normal_price and isinstance(normal_price, (int, float)) and float(normal_price) > price:
                        original_price = float(normal_price)
                        savings = round(original_price - price, 2)
                    elif original_price > price:
                        # original_price was set from the pre-promotion price
                        savings = round(original_price - price, 2)
                    elif savings <= 0:
                        # Fallback: use savingsAmount from API
                        savings_amount = item.get('savingsAmount')
                        if savings_amount:
                            savings_val = self._parse_price(str(savings_amount))
                            if savings_val > 0:
                                savings = savings_val
                                original_price = price + savings

            # Image
            image_url = None
            if 'image' in item and item['image']:
                image_url = item['image'].get('url')

            # Product URL
            # Willys campaign API no longer sends top-level `code` reliably.
            # Use `mainProductCode` from the promotion payload when available.
            product_url = None
            product_code = None
            if promotions:
                product_code = promotions[0].get('mainProductCode')
            if not product_code:
                product_code = item.get('code') or item.get('productCode') or item.get('id')

            if product_code:
                product_url = f"{self.base_url}/produkt/{product_code}"
                logger.debug(f"Constructed product URL: {product_url}")

            # Package weight from API (if available in campaign response)
            weight_grams = None
            volume_str = (item.get('displayVolume') or '').strip()
            if volume_str:
                weight_grams = parse_weight(volume_str)

            # Convert per-kg prices to total price (consistent with ICA/Coop)
            # Willys API gives per-kg price for weight products; multiply by
            # actual package weight so all stores show "what you pay at checkout"
            if unit == 'kg' and weight_grams and weight_grams > 0:
                weight_kg = weight_grams / 1000.0
                price = round(price * weight_kg, 2)
                original_price = round(original_price * weight_kg, 2)
                savings = round(original_price - price, 2)
                unit = 'st'
                logger.debug(f"Kg→total: {product_name} - {weight_kg}kg, price: {price}, orig: {original_price}")

            # CATEGORY from API (if available)
            category = self._extract_api_category(item)

            # Fallback to guessing if API doesn't have category
            if not category or category == 'other':
                category = self._guess_category_improved(product_name)

            if price <= 0:
                logger.debug(f"Skipping product with zero/negative price: '{product_name}'")
                return None

            # Skip products with no savings (not a real deal) unless multi-buy
            if savings <= 0 and not is_temporary_deal and not is_multi_buy:
                logger.debug(f"Skipping product with no savings: '{product_name}' ({price} kr)")
                return None

            # ORIGIN VERIFICATION: Filter imported meat (same as butik path)
            if manufacturer and self._should_verify_origin(product_name):
                if self._is_imported_brand(manufacturer):
                    logger.info(f"⚠ Skipping imported product: {product_name} (tillverkare: {manufacturer})")
                    return None

            # Brand-based name completion: some brands have stripped product names
            # e.g., Willys strips "Färskost" from Philadelphia → "Gräslök Light 11%"
            if manufacturer and manufacturer.lower() == 'philadelphia':
                if 'färskost' not in product_name.lower():
                    product_name = f"Färskost {product_name}"
                    logger.debug(f"Name completion: added 'Färskost' for Philadelphia → '{product_name}'")

            result = {
                "name": product_name,
                "price": round(price, 2),
                "original_price": round(original_price, 2),
                "savings": round(savings, 2),
                "unit": unit,
                "category": category,
                "brand": manufacturer.upper() if manufacturer else None,  # Normalize to uppercase
                "image_url": image_url,
                "product_url": product_url,
                "weight_grams": weight_grams,
                "scraped_at": datetime.now(timezone.utc)
            }

            # Add multi-buy fields when applicable
            if is_multi_buy:
                result["is_multi_buy"] = True
                result["multi_buy_quantity"] = multi_buy_quantity
                result["multi_buy_total_price"] = round(multi_buy_total_price, 2)

            return result

        except Exception as e:
            logger.debug(f"Error parsing campaign product: {e}")
            return None
    
    
    def _extract_api_category(self, item: dict) -> str:
        """
        Extract category from API data.
        
        API may have these fields:
        - googleAnalyticsCategory
        - productType
        - categoryHierarchy
        """
        
        # Check various possible fields
        category_fields = [
            'googleAnalyticsCategory',
            'productType',
            'category',
            'categoryName'
        ]
        
        for field in category_fields:
            if field in item and item[field]:
                raw_category = str(item[field]).lower()
                return self._normalize_category(raw_category)
        
        return 'other'
    
    
    def _normalize_category(self, raw_category: str) -> str:
        """
        Normalize API category to our standard categories.

        Delegates to shared utility. See languages/sv/category_utils.py.
        """
        return shared_normalize_category(raw_category)
    
    
    # ==================== PLAYWRIGHT SCRAPING (E-COMMERCE) ====================
    
    async def _scrape_ehandel_playwright(self, cookies: Optional[list] = None, delivery_address: Optional[Dict] = None) -> List[Dict]:
        """Scrape e-commerce offers with Playwright."""
        logger.info(f"E-commerce scraping called with cookies: {cookies is not None}")
        if cookies:
            logger.info(f"Cookie count: {len(cookies)}")

        products = []

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(locale='sv-SE')
                try:
                    # Load saved session cookies if available
                    if cookies:
                        try:
                            await context.add_cookies(cookies)
                            logger.info("Loaded session cookies - scraping as logged-in user")
                        except Exception as e:
                            logger.warning(f"Failed to load cookies: {e}")

                    page = await context.new_page()

                    logger.debug(f"Navigating to {self.ehandel_url}")
                    await page.goto(self.ehandel_url, timeout=PAGE_LOAD_TIMEOUT)
                    await page.wait_for_load_state("networkidle", timeout=PAGE_NETWORK_IDLE_TIMEOUT)
                    await asyncio.sleep(3)

                    # Check if correct delivery address is already set
                    if delivery_address:
                        logger.info(f"Target delivery address: {delivery_address['street']}, {delivery_address['postal_code']} {delivery_address['city']}")

                        # First, check what address is currently shown on the page
                        page_content = await page.content()
                        target_street = delivery_address['street']  # e.g., "Storgatan 1"
                        target_postal = delivery_address['postal_code']  # e.g., "15172"

                        # Check if we already have the right address set
                        # Must check both street AND postal code to distinguish between same street in different cities
                        address_already_correct = False
                        if "Leverans:" in page_content and target_street in page_content and target_postal in page_content:
                            logger.success(f"✓ Delivery address already set correctly (found '{target_street}' + '{target_postal}' on page)")
                            address_already_correct = True
                        else:
                            logger.info(f"Address not set correctly - '{target_street}' with postal '{target_postal}' not found on page")

                        if not address_already_correct:
                            # Need to set up the delivery address
                            await self._setup_delivery_address(page, delivery_address)
                    else:
                        logger.warning("No delivery address provided - will get generic product list")

                    # Verify final delivery mode
                    page_content = await page.content()
                    current_url = page.url
                    logger.info(f"Current URL after address setup: {current_url}")

                    if "Leverans:" in page_content or "leverans" in page_content.lower():
                        logger.success("✓ Delivery mode active (Leverans)")
                    else:
                        logger.warning("⚠ WARNING: Not in delivery mode - might show wrong products!")

                    # Make sure we're on the right page
                    if "/erbjudanden/ehandel" not in current_url:
                        logger.info("Not on e-handel page - navigating back...")
                        await page.goto(self.ehandel_url, timeout=PAGE_LOAD_TIMEOUT)
                        await page.wait_for_load_state("networkidle", timeout=PAGE_NETWORK_IDLE_TIMEOUT)
                        await asyncio.sleep(3)

                    await self._close_popups_async(page)

                    # Extract store code from the API calls the page makes
                    # The page calls /search/campaigns/online?q={store_code}&...
                    store_code = await self._extract_store_code(page)

                    if store_code:
                        logger.info(f"Using API-based scraping with store code: {store_code}")
                        products = await self._scrape_ehandel_via_api(store_code, session_cookies=cookies)
                    else:
                        logger.warning("Could not extract store code - falling back to DOM scraping")
                        products = await self._scrape_ehandel_dom(page)
                finally:
                    await context.close()
                    await browser.close()

            return products

        except Exception as e:
            logger.error(f"Error in Playwright scraping: {e}")
            return []
    
    
    async def _setup_delivery_address(self, page, delivery_address: dict):
        """
        Set up delivery address on Willys e-commerce page.

        Flow based on user screenshots:
        1. Close any login popups first
        2. Click delivery-picker-toggle (the "Ändra" link in E-handel box)
        3. Click home delivery ('Hemleverans') option
        4. Type address in the dialog's search field
        5. Click on autocomplete suggestion
        6. Close time selection ('Välj tid') dialog with ESC
        """
        logger.info("Starting delivery address setup...")

        try:
            # First, close any login popups that might appear
            await self._close_login_popup(page)
            # STEP 1: Click the delivery picker toggle button
            # Use the specific data-testid from user's HTML
            logger.info("Step 1: Looking for delivery picker toggle...")
            toggle_btn = None

            # Try specific testid first, then fallback to text-based selectors
            toggle_selectors = [
                '[data-testid="delivery-picker-toggle"]',
                'button[aria-label="Välj leveranssätt"]',
                'a:has-text("Ändra")',
                'button:has-text("Ändra")',
            ]

            for sel in toggle_selectors:
                try:
                    toggle_btn = await page.wait_for_selector(sel, timeout=3000)
                    if toggle_btn and await toggle_btn.is_visible():
                        logger.info(f"Found toggle with selector: {sel}")
                        break
                    toggle_btn = None
                except Exception:
                    # Expected: selector not found, try next one
                    continue

            if toggle_btn:
                # Use force=True in case there's an overlay blocking the click
                await toggle_btn.click(force=True, timeout=5000)
                # Wait for dialog or popup to appear instead of fixed sleep
                try:
                    await page.wait_for_selector('[role="dialog"], [data-testid*="login"], [data-testid*="delivery"]', timeout=3000)
                except Exception:
                    # Dialog may not appear immediately, fallback to sleep
                    await asyncio.sleep(1)
                logger.success("✓ Clicked delivery picker toggle")

                # A login popup might appear after clicking - close it
                for _ in range(3):
                    await self._close_login_popup(page)
                    await asyncio.sleep(0.3)

                # Now click toggle AGAIN to actually open the dialog
                # (first click might have been intercepted by popup)
                try:
                    toggle_btn2 = await page.wait_for_selector('[data-testid="delivery-picker-toggle"]', timeout=2000)
                    if toggle_btn2:
                        await toggle_btn2.click(force=True, timeout=3000)
                        try:
                            await page.wait_for_selector('[role="dialog"], [data-testid*="delivery"]', timeout=3000)
                        except Exception:
                            # Dialog may not appear immediately
                            await asyncio.sleep(1)
                        logger.info("Clicked toggle again after closing popup")
                except Exception:
                    # Toggle button not found on second attempt, continue
                    logger.debug("Second delivery picker toggle attempt failed after popup handling")
            else:
                logger.warning("Could not find delivery picker toggle")
                return


            # STEP 2: Click home delivery ('Hemleverans') in the delivery method chooser dialog
            logger.info("Step 2: Looking for home delivery ('Hemleverans') option in dialog...")

            # Wait for dialog to appear - use selector instead of fixed sleep
            try:
                await page.wait_for_selector('[role="dialog"], [data-testid*="delivery"], .delivery-picker', timeout=5000)
            except Exception:
                # Fallback if no dialog selector found
                await asyncio.sleep(1)

            # Use JavaScript to click the Hemleverans option
            # Strategy: Find clickable element containing "Hemleverans" but not "Hämta"
            # Avoid hardcoded prices (like '158') that can change
            clicked = await page.evaluate('''() => {
                // First try: Look for data-testid or specific delivery option elements
                const deliveryOptions = document.querySelectorAll('[data-testid*="delivery"], [class*="delivery"], [role="option"]');
                for (const el of deliveryOptions) {
                    const text = el.textContent || '';
                    if (text.includes('Hemleverans') && !text.includes('Hämta i butik')) {
                        el.click();
                        return 'clicked delivery option: ' + el.tagName;
                    }
                }

                // Second try: Find by text content, prefer smaller/more specific elements
                const candidates = [];
                const allElements = document.querySelectorAll('button, a, div[role="button"], li, [class*="option"]');
                for (const el of allElements) {
                    const text = el.textContent || '';
                    if (text.includes('Hemleverans') && !text.includes('Hämta')) {
                        candidates.push({ el, length: text.length });
                    }
                }

                // Click the most specific (shortest text) match
                if (candidates.length > 0) {
                    candidates.sort((a, b) => a.length - b.length);
                    candidates[0].el.click();
                    return 'clicked: ' + candidates[0].el.tagName;
                }

                return null;
            }''')

            if clicked:
                logger.success(f"✓ Clicked home delivery ('Hemleverans') via JS: {clicked}")
                # Wait for address input to appear instead of fixed sleep
                try:
                    await page.wait_for_selector('input[placeholder*="adress"]', timeout=3000)
                except Exception:
                    # Fallback if selector not found
                    await asyncio.sleep(1)
            else:
                logger.info("Home delivery ('Hemleverans') not found via JS - trying selector approach")
                # Fallback to selector
                try:
                    hemlev_btn = await page.wait_for_selector('text=Hemleverans >> nth=0', timeout=3000)
                    if hemlev_btn:
                        await hemlev_btn.click()
                        try:
                            await page.wait_for_selector('input[placeholder*="adress"]', timeout=3000)
                        except Exception:
                            # Fallback if selector not found
                            await asyncio.sleep(1)
                        logger.success("✓ Clicked home delivery ('Hemleverans') via selector")
                except Exception:
                    logger.warning("Could not click home delivery ('Hemleverans')")

            # STEP 3: Find address input INSIDE the dialog (not the main search bar!)
            logger.info("Step 3: Looking for address input field in dialog...")
            address_input = None

            # The dialog has 'Hemleverans' header and input with placeholder 'Ange adress'
            dialog_input_selectors = [
                'input[placeholder="Ange adress"]',      # Exact match from screenshot
                'input[placeholder*="Ange adress"]',    # Partial match
                'input[placeholder*="adress"]',         # Any address placeholder
            ]

            for sel in dialog_input_selectors:
                try:
                    address_input = await page.wait_for_selector(sel, timeout=5000)
                    if address_input and await address_input.is_visible():
                        logger.info(f"Found address input with selector: {sel}")
                        break
                    address_input = None
                except Exception:
                    # Expected: selector not found, try next one
                    continue

            if not address_input:
                logger.error("Could not find address input field in dialog")
                return

            # Type the address WITHOUT comma
            full_address = f"{delivery_address['street']} {delivery_address['postal_code']} {delivery_address['city']}"
            logger.info(f"Typing address: {full_address}")
            await address_input.click()
            await asyncio.sleep(0.2)
            await address_input.type(full_address, delay=50)
            # Wait for autocomplete list instead of fixed sleep
            try:
                await page.wait_for_selector('[data-testid="autocomplete-list"], [role="listbox"]', timeout=5000)
            except Exception:
                # Autocomplete may be slow, fallback to sleep
                await asyncio.sleep(1)
            logger.success("✓ Typed address")

            # STEP 4: Click on the autocomplete suggestion
            # HTML structure (from user):
            # <ul data-testid="autocomplete-list" role="listbox">
            #   <li role="option" class="...">
            #     <div data-testid="full-address-list-item">
            #       <p><span>Storgatan 1 </span></p>
            #       <p><span>11444 </span><span>Stockholm</span></p>
            #     </div>
            #   </li>
            # </ul>
            logger.info("Step 4: Looking for address suggestion in autocomplete list...")
            suggestion_clicked = False

            # Wait for the autocomplete list to appear
            try:
                autocomplete_list = await page.wait_for_selector(
                    '[data-testid="autocomplete-list"]',
                    timeout=5000
                )
                if autocomplete_list:
                    logger.info("✓ Found autocomplete list!")

                    # Get all suggestions and find the one matching our exact street
                    # Street format: "Storgatan 1" - we need exact match, not "Storgatan 11"
                    street = delivery_address['street']  # e.g. "Storgatan 1" or "Persgatan 4B"

                    # Use JavaScript to find the INDEX of the correct suggestion
                    matched_index = await page.evaluate('''(targetStreet) => {
                        const list = document.querySelector('[data-testid="autocomplete-list"]');
                        if (!list) return -1;

                        const options = list.querySelectorAll('li[role="option"]');

                        for (let i = 0; i < options.length; i++) {
                            const option = options[i];
                            // Get the street text from the first span (structure: p > span with street name)
                            const streetSpan = option.querySelector('p span');
                            if (streetSpan) {
                                const streetText = streetSpan.textContent.trim();
                                // Exact match (the span contains "Storgatan 1 " with trailing space)
                                if (streetText === targetStreet || streetText === targetStreet + " ") {
                                    return i;
                                }
                            }
                        }
                        return -1;
                    }''', street)

                    if matched_index >= 0:
                        # Use Playwright to click the element (more reliable than JS click)
                        options = await page.locator('[data-testid="autocomplete-list"] li[role="option"]').all()
                        if matched_index < len(options):
                            logger.info(f"Clicking option at index {matched_index} with Playwright...")
                            await options[matched_index].click()
                            # Wait for time selection dialog instead of fixed sleep
                            try:
                                await page.wait_for_selector('text=Leverans till, text=Välj tid', timeout=5000)
                            except Exception:
                                # Dialog may take time to appear
                                await asyncio.sleep(1.5)
                            suggestion_clicked = True
                            logger.success(f"✓ Clicked exact match for '{street}'")
                    else:
                        # Fallback: click first option if no exact match
                        logger.warning(f"No exact match for '{street}', clicking first option")
                        first_option = await page.query_selector(
                            '[data-testid="autocomplete-list"] li[role="option"]'
                        )
                        if first_option:
                            await first_option.click()
                            try:
                                await page.wait_for_selector('text=Leverans till, text=Välj tid', timeout=5000)
                            except Exception:
                                # Dialog may take time to appear
                                await asyncio.sleep(1.5)
                            suggestion_clicked = True
                            logger.info("Clicked first autocomplete suggestion as fallback")
            except Exception as e:
                logger.warning(f"Could not find autocomplete list: {e}")

            # Fallback: Try clicking via data-testid on the inner div
            if not suggestion_clicked:
                try:
                    suggestion_div = await page.query_selector('[data-testid="full-address-list-item"]')
                    if suggestion_div:
                        logger.info("Clicking via full-address-list-item...")
                        await suggestion_div.click()
                        try:
                            await page.wait_for_selector('text=Leverans till, text=Välj tid', timeout=5000)
                        except Exception:
                            # Dialog may take time to appear
                            await asyncio.sleep(1.5)
                        suggestion_clicked = True
                        logger.success("✓ Clicked suggestion via data-testid!")
                except Exception as e:
                    logger.debug(f"full-address-list-item click failed: {e}")

            # Last resort: keyboard navigation
            if not suggestion_clicked:
                logger.info("Trying ArrowDown + Enter as last resort...")
                await address_input.press('ArrowDown')
                await asyncio.sleep(0.3)
                await address_input.press('Enter')
                try:
                    await page.wait_for_selector('text=Leverans till, text=Välj tid', timeout=5000)
                except Exception:
                    # Dialog may take time to appear
                    await asyncio.sleep(1.5)
                logger.info("Pressed ArrowDown + Enter")

            # STEP 5: Wait for time selection ('Välj tid') dialog and close it
            # After clicking autocomplete suggestion, a time selection dialog appears
            # We just need to close it with ESC - the address is already saved
            logger.info("Step 5: Closing time selection ('Välj tid') dialog...")

            street_first_word = delivery_address['street'].split()[0]

            # Wait for delivery confirmation dialog with timeout
            for attempt in range(5):
                try:
                    # Wait for dialog content to appear
                    await page.wait_for_function(
                        f'''() => document.body.innerText.includes("Leverans till") && document.body.innerText.includes("{street_first_word}")''',
                        timeout=2000
                    )
                    logger.success(f"✓ Found 'Leverans till {street_first_word}' dialog")

                    # Close the dialog with ESC - address is already saved
                    await page.keyboard.press('Escape')
                    # Wait for dialog to close
                    await asyncio.sleep(0.5)

                    logger.success("✓ Delivery address setup complete!")
                    return
                except Exception:
                    # Dialog not found yet, retry
                    if attempt < 4:
                        await asyncio.sleep(0.5)
                        continue
                    break

                await asyncio.sleep(0.5)

            logger.warning("Time selection ('Välj tid') dialog did not appear as expected")

        except Exception as e:
            logger.error(f"Error setting up delivery address: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _close_login_popup(self, page):
        """Close the login/signup popup that appears on Willys."""
        try:
            # Check if login popup is visible
            popup_visible = await page.query_selector('div:has-text("SOM INLOGGAD FÅR DU MER")')
            if not popup_visible:
                logger.debug("No login popup visible")
                return

            logger.info("Login popup detected - attempting to close...")

            # The X button is typically in the top-right corner of the popup
            # Try clicking it using JavaScript to avoid any overlay issues
            closed = await page.evaluate('''() => {
                // Find the popup container
                const popup = document.querySelector('[class*="modal"], [class*="popup"], [class*="overlay"]');
                if (popup) {
                    // Look for close button inside
                    const closeBtn = popup.querySelector('button, [role="button"]');
                    if (closeBtn) {
                        closeBtn.click();
                        return true;
                    }
                }
                // Try finding any X button near "SOM INLOGGAD" text
                const allButtons = document.querySelectorAll('button');
                for (const btn of allButtons) {
                    const rect = btn.getBoundingClientRect();
                    // X buttons are usually small and in top-right
                    if (rect.width < 50 && rect.height < 50) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }''')

            if closed:
                await asyncio.sleep(1)
                logger.success("✓ Closed login popup via JavaScript")
                return

            # Fallback: Press Escape multiple times
            for _ in range(3):
                await page.keyboard.press('Escape')
                await asyncio.sleep(0.5)

            logger.info("Pressed ESC to close popup")

        except Exception as e:
            logger.debug(f"Could not close login popup: {e}")

    async def _close_popups_async(self, page):
        """Close popups."""
        try:
            close_buttons = [
                '[aria-label="Close"]',
                '[data-testid="close-button"]',
                'button:has-text("Stäng")',
                'button:has-text("×")'
            ]
            
            for selector in close_buttons:
                try:
                    button = await page.query_selector(selector)
                    if button and await button.is_visible():
                        await button.click()
                        await asyncio.sleep(0.5)
                except Exception:
                    # Expected: selector not found or button not clickable
                    pass
        except Exception as e:
            logger.debug(f"Could not close popups: {e}")
    
    
    @staticmethod
    def _extract_latest_store_code_from_resource_urls(resource_urls: List[str]) -> Optional[str]:
        """Return the latest online campaigns store code found among resource URLs."""
        for url in reversed(resource_urls):
            match = re.search(r'/search/campaigns/online\?q=(\d+)', url)
            if match:
                return match.group(1)
        return None

    async def _extract_store_code(self, page) -> Optional[str]:
        """Extract the most recent store code from the page's campaign API calls."""
        try:
            resource_urls = await page.evaluate(r'''() =>
                performance.getEntriesByType('resource').map(entry => entry.name)
            ''')
            store_code = self._extract_latest_store_code_from_resource_urls(resource_urls or [])
            if store_code:
                logger.debug(f"Extracted store code from performance entries: {store_code}")
                return store_code

            # Fallback: trigger a tiny scroll to make the page load campaigns,
            # then check the API call
            await page.evaluate("window.scrollBy(0, 100)")
            await asyncio.sleep(2)

            resource_urls = await page.evaluate(r'''() =>
                performance.getEntriesByType('resource').map(entry => entry.name)
            ''')
            store_code = self._extract_latest_store_code_from_resource_urls(resource_urls or [])
            if store_code:
                logger.debug(f"Extracted store code after scroll: {store_code}")
            return store_code

        except Exception as e:
            logger.warning(f"Failed to extract store code: {e}")
            return None

    # Polite delay between variant API calls (seconds).
    # Hemköp uses 10s; we use 1.5s since each call is lightweight.
    VARIANT_API_DELAY = 1.5

    async def _scrape_ehandel_via_api(
        self,
        store_code: str,
        session_cookies: Optional[list] = None,
    ) -> List[Dict]:
        """Scrape e-commerce offers via API using an explicit online store code.

        Uses /search/campaigns/online for the main product list,
        then /axfood/rest/promotions/{code}/products to expand "Visa fler sorter"
        variants (different products that share the same campaign deal).
        """
        products = []
        seen_codes = set()

        try:
            async with httpx.AsyncClient(
                event_hooks={"request": [ssrf_safe_event_hook]},
                headers=self._build_api_headers(),
                cookies=self._build_httpx_cookie_jar(session_cookies),
                follow_redirects=True,
                timeout=HTTP_TIMEOUT,
            ) as client:
                # Fetch all campaign products via API.
                api_url = f"{self.base_url}/search/campaigns/online?q={store_code}&type=PERSONAL_GENERAL&page=0&size=400"
                resp = await client.get(api_url)

                if resp.status_code != 200:
                    logger.error(f"Campaign API returned status {resp.status_code}")
                    return []

                data = resp.json()
                results = data.get('results', [])
                logger.info(f"Campaign API returned {len(results)} products")

                # Track promotions that need variant expansion (deduplicated)
                seen_promo_codes = set()
                promo_variants_to_fetch = []

                for item in results:
                    item_code = item.get('code', '')
                    seen_codes.add(item_code)

                    product = self._parse_campaign_product(item, url_prefix="online")
                    if product:
                        products.append(product)

                    # Collect unique multi-code promotions for variant expansion
                    for promo in item.get('potentialPromotions', []):
                        promo_codes = promo.get('productCodes') or []
                        promo_code = promo.get('code', '')
                        if len(promo_codes) > 1 and promo_code and promo_code not in seen_promo_codes:
                            seen_promo_codes.add(promo_code)
                            promo_variants_to_fetch.append(promo_code)

                base_count = len(products)
                logger.info(f"Parsed {base_count} base products, {len(promo_variants_to_fetch)} promotions have hidden variants")

                # Expand "Visa fler sorter" variants via promotions API
                if promo_variants_to_fetch:
                    variant_products = await self._fetch_promotion_variants(
                        client, promo_variants_to_fetch, seen_codes
                    )
                    products.extend(variant_products)
                    logger.info(f"Expanded {len(variant_products)} variant products from {len(promo_variants_to_fetch)} promotions")

            variant_count = len(products) - base_count
            self._scrape_meta = {"base_count": base_count, "variant_count": variant_count}
            logger.success(f"Total: {len(products)} products ({base_count} base + {variant_count} variants)")

        except Exception as e:
            logger.error(f"Error in API-based ehandel scraping: {e}")

        return products

    async def _fetch_promotion_variants(self, client: httpx.AsyncClient, promo_codes: List[str],
                                        seen_codes: set) -> List[Dict]:
        """Fetch variant products from the promotions API.

        For each promotion code, calls /axfood/rest/promotions/{code}/products
        and parses products not already seen in the main campaign results.
        """
        variant_products = []

        for i, promo_code in enumerate(promo_codes):
            try:
                url = f"{self.base_url}/axfood/rest/promotions/{promo_code}/products"
                resp = await client.get(url)

                if resp.status_code != 200:
                    logger.debug(f"Promotion API returned {resp.status_code} for {promo_code}")
                    continue

                data = resp.json()
                items = data.get('items', [])
                new_count = 0

                for item in items:
                    item_code = item.get('code', '')
                    if item_code in seen_codes:
                        continue
                    seen_codes.add(item_code)

                    product = self._parse_campaign_product(item, url_prefix="online")
                    if product:
                        variant_products.append(product)
                        new_count += 1

                if new_count:
                    logger.debug(f"Promo {promo_code}: +{new_count} variants")

            except Exception as e:
                logger.debug(f"Error fetching promotion {promo_code}: {e}")

            # Polite delay between API calls
            if i < len(promo_codes) - 1:
                await asyncio.sleep(self.VARIANT_API_DELAY)

        return variant_products

    async def _scrape_ehandel_dom(self, page) -> List[Dict]:
        """Fallback: scrape e-commerce offers via DOM (when API extraction fails)."""
        products = []

        logger.info("Scrolling to load all products...")
        await self._scroll_to_load_all_async(page)

        product_links = await page.query_selector_all('a[href*="/erbjudanden/online-"]')
        logger.info(f"Found {len(product_links)} product links")

        if len(product_links) == 0:
            logger.warning("No product links found")

        async with httpx.AsyncClient(timeout=10, event_hooks={"request": [ssrf_safe_event_hook]}) as http_client:
            for i, link in enumerate(product_links):
                try:
                    product = await self._extract_product_from_link_async(link, page, http_client)
                    if product:
                        products.append(product)
                        logger.debug(f"Extracted: {product['name']} - {product['price']} kr")
                except Exception as e:
                    logger.warning(f"Failed to extract product {i+1}: {e}")
                    continue

        return products

    async def _scroll_to_load_all_async(self, page):
        """Scroll to load all products. Stops after 3 consecutive scrolls with no new products."""
        previous_count = 0
        no_new_count = 0

        for scroll in range(100):  # safety limit only
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)

            current_count = len(await page.query_selector_all('a[href*="/erbjudanden/online-"]'))
            logger.debug(f"Scroll {scroll + 1}: Found {current_count} products")

            if current_count == previous_count:
                no_new_count += 1
                if no_new_count >= 3:
                    break
            else:
                no_new_count = 0

            previous_count = current_count
    
    
    async def _extract_product_from_link_async(self, link_element, page, http_client=None) -> Optional[Dict]:
        """Extract product data from link."""
        
        try:
            href = await link_element.get_attribute("href")
            if not href:
                return None
            
            product_url = href if href.startswith("http") else f"{self.base_url}{href}"
            
            product_card_text = await link_element.evaluate("""
                el => {
                    let current = el;
                    let best = el;
                    let maxLength = el.innerText.length;
                    
                    for (let i = 0; i < 5; i++) {
                        current = current.parentElement;
                        if (!current) break;
                        
                        const text = current.innerText || '';
                        if (text.length > maxLength && text.length < 500) {
                            maxLength = text.length;
                            best = current;
                        }
                    }
                    
                    return best.innerText;
                }
            """)
            
            # Extract product name
            product_name = None
            
            link_text = (await link_element.text_content()).strip()
            if link_text and len(link_text) > 3 and not link_text.startswith("http"):
                product_name = link_text
                product_name = self._fix_swedish_chars(product_name)
            
            if not product_name or len(product_name) < 3:
                match = re.search(r'/online-([^/]+)', href)
                if match:
                    url_name = match.group(1)
                    url_name = re.sub(r'[-_]\d+[-_][A-Z]+$', '', url_name)
                    product_name = url_name.replace('-', ' ')
                    product_name = self._fix_swedish_chars(product_name)
            
            if not product_name or len(product_name) < 3:
                lines = [l.strip() for l in product_card_text.split('\n') if l.strip()]
                for line in lines[1:5]:
                    if 10 < len(line) < 50 and not line[0].isdigit():
                        product_name = line
                        product_name = self._fix_swedish_chars(product_name)
                        break
            
            if not product_name or len(product_name) < 3:
                return None
            
            # Normalize text
            normalized_text = ' '.join(product_card_text.split())
            
            # PRICE
            is_multi_buy = False
            multi_buy_quantity = 1
            current_price = 0.0
            total_price = 0.0
            
            # Multi-buy campaigns
            multi_buy_patterns = [
                r'(?:VÄLJ|Välj).{0,20}(\d+)\s+FÖR\s+(\d+)\s+(\d{2})',
                r'(\d+)\s+FÖR\s+(\d+)\s+(\d{2})',
                r'(\d+)\s+för\s+(\d+)[,.]?(\d{0,2})\s*kr',
            ]
            
            for pattern in multi_buy_patterns:
                multi_buy_match = re.search(pattern, normalized_text, re.IGNORECASE)
                if multi_buy_match:
                    is_multi_buy = True
                    multi_buy_quantity = int(multi_buy_match.group(1))
                    
                    whole = multi_buy_match.group(2)
                    decimal = multi_buy_match.group(3) if len(multi_buy_match.groups()) >= 3 and multi_buy_match.group(3) else "00"
                    
                    total_price = float(f"{whole}.{decimal}")
                    current_price = total_price / multi_buy_quantity
                    
                    logger.debug(f"{product_name}: Multi-buy: {multi_buy_quantity} for {total_price} kr")
                    break
            
            # Regular price
            if not is_multi_buy:
                price_pattern = r'(\d{1,4})\s+(\d{2})(?:\s|$|/)'
                price_match = re.search(price_pattern, normalized_text)
                
                if price_match:
                    current_price = float(f"{price_match.group(1)}.{price_match.group(2)}")
                else:
                    price_pattern2 = r'(\d{1,4})[,.](\d{2})'
                    price_match2 = re.search(price_pattern2, normalized_text)
                    
                    if price_match2:
                        current_price = float(f"{price_match2.group(1)}.{price_match2.group(2)}")
                    else:
                        return None
            
            # SAVINGS
            savings = 0.0
            original_price = current_price
            
            ord_price_pattern = r'Ordinarie pris\s+(\d+)[,.](\d{2})\s*kr'
            ord_match = re.search(ord_price_pattern, normalized_text, re.IGNORECASE)
            
            if ord_match:
                ord_price = float(f"{ord_match.group(1)}.{ord_match.group(2)}")
                original_price = ord_price
                savings = original_price - current_price
            elif not is_multi_buy:
                savings_pattern = r'Spara\s+(\d+)[,.]?(\d{0,2})\s*kr'
                savings_match = re.search(savings_pattern, normalized_text, re.IGNORECASE)
                
                if savings_match:
                    savings = float(f"{savings_match.group(1)}.{savings_match.group(2) or '00'}")
                    original_price = current_price + savings
            
            # Safety checks
            if savings < 0:
                savings = 0.0
                original_price = current_price
            
            if original_price < current_price:
                original_price = current_price
                savings = 0.0
            
            # UNIT
            unit = "st"
            unit_patterns = {
                "kg": r'/kg|per kg',
                "l": r'/l|per liter',
                "förp": r'/förp|förpackning',
                "st": r'/st|styck',
            }
            
            text_lower = normalized_text.lower()
            for unit_name, pattern in unit_patterns.items():
                if re.search(pattern, text_lower):
                    unit = unit_name
                    break
            
            # IMAGE
            image_url = None
            try:
                img = await link_element.evaluate("""
                    el => {
                        let img = el.querySelector('img');
                        if (img) return img.src;
                        
                        let parent = el.parentElement;
                        if (parent) {
                            img = parent.querySelector('img');
                            if (img) return img.src;
                        }
                        
                        return null;
                    }
                """)
                image_url = img if img else None
            except Exception:
                # Image extraction failed, product will have no image
                pass
            
            # PRODUCT DETAILS: Lookup name + manufacturer + weight via API
            # The API always returns correct Unicode (ö/ä/å/ñ/ß/%), fixing broken page text
            brand = None
            weight_grams = None
            details = await self._lookup_product_details(product_url, http_client)
            if details:
                # Use API name if available (fixes broken ö→o, ä→a, ñ→" o", %→"procent")
                api_name = details.get('name')
                if api_name and api_name != product_name:
                    logger.debug(f"Fixed product name: '{product_name}' → '{api_name}'")
                    product_name = api_name

                # Parse package weight from API volume (e.g., "ca: 650g" → 650.0)
                volume_str = details.get('volume')
                if volume_str:
                    weight_grams = parse_weight(volume_str)

                manufacturer = details.get('manufacturer')
                if manufacturer:
                    brand = manufacturer.upper()

                    # ORIGIN VERIFICATION: Filter imported meat for specific products
                    if self._should_verify_origin(product_name):
                        if self._is_imported_brand(manufacturer):
                            logger.info(f"⚠ Skipping imported product: {product_name} (tillverkare: {manufacturer})")
                            log_filtered_product("Willys", product_name, "Importerat kött", manufacturer)
                            return None
                        else:
                            logger.debug(f"✓ Swedish product OK: {product_name} (tillverkare: {manufacturer})")

            # CATEGORY: guess based on (now possibly corrected) product name
            category = self._guess_category_improved(product_name)

            # Skip products with no savings (not a real deal) unless multi-buy
            if savings <= 0 and not is_multi_buy:
                logger.debug(f"Skipping product with no savings: '{product_name}' ({current_price} kr)")
                return None

            return {
                "name": product_name,
                "price": round(current_price, 2),
                "original_price": round(original_price, 2),
                "savings": round(savings, 2),
                "unit": unit,
                "is_multi_buy": is_multi_buy,
                "multi_buy_quantity": multi_buy_quantity if is_multi_buy else None,
                "multi_buy_total_price": round(total_price, 2) if is_multi_buy else None,
                "image_url": image_url,
                "product_url": product_url,
                "category": category,
                "brand": brand,
                "weight_grams": weight_grams,
                "scraped_at": datetime.now(timezone.utc)
            }

        except Exception as e:
            logger.warning(f"Error extracting product: {e}")
            return None
    
    
    # ==================== ORIGIN VERIFICATION (API LOOKUP) ====================

    def _should_verify_origin(self, product_name: str) -> bool:
        """Check if this product should be verified via API for origin/manufacturer."""
        name_lower = product_name.lower()
        return any(pattern in name_lower for pattern in self.PRODUCTS_TO_VERIFY_ORIGIN)

    async def _lookup_product_details(self, product_url: str, client: httpx.AsyncClient = None) -> Dict:
        """
        Look up product details (name, manufacturer, volume) via Willys API.

        The Willys website sometimes has broken product names (stripped ö/ä/å/ñ, % → "procent").
        The API always returns correct Unicode names.

        Args:
            product_url: Full product URL like https://www.willys.se/erbjudanden/online-Flaskfile-101553212_KG
            client: Optional shared httpx client (avoids creating one per call)

        Returns:
            Dict with 'name', 'manufacturer' (lowercase), 'volume' keys. Empty dict on failure.
        """
        try:
            # Extract product ID from URL (including unit suffix like _KG, _ST)
            # Supported formats:
            # - /erbjudanden/online-Flaskfile-101553212_KG
            # - /erbjudanden/...-12345
            # - /produkt/101197478_KG
            # - /produkt/12345
            match = re.search(r'/produkt/(\d+_[A-Z]+)$', product_url)
            if not match:
                match = re.search(r'/produkt/(\d+)$', product_url)
            if not match:
                match = re.search(r'-(\d+_[A-Z]+)$', product_url)
            if not match:
                # Try alternative format without unit suffix
                match = re.search(r'-(\d+)$', product_url)
            if not match:
                logger.debug(f"Could not extract product ID from URL: {product_url}")
                return {}

            product_id = match.group(1)
            api_url = f"{self.product_api}/{product_id}"

            logger.debug(f"Looking up product details for ID {product_id}")

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }

            if client:
                response = await client.get(api_url, headers=headers, timeout=10)
            else:
                async with httpx.AsyncClient(event_hooks={"request": [ssrf_safe_event_hook]}) as c:
                    response = await c.get(api_url, headers=headers, timeout=10)

            if response.status_code != 200:
                logger.debug(f"API returned {response.status_code} for product {product_id}")
                return {}

            try:
                data = response.json()
            except Exception:
                logger.debug(f"Non-JSON response for product {product_id}")
                return {}

            result = {}

            api_name = (data.get('name') or '').strip()
            if api_name:
                result['name'] = api_name

            manufacturer = (data.get('manufacturer') or '').strip().lower()
            if manufacturer:
                result['manufacturer'] = manufacturer

            volume = (data.get('displayVolume') or '').strip()
            if volume:
                result['volume'] = volume

            if api_name:
                logger.debug(f"API product details: '{api_name}' by {manufacturer or 'unknown'}")

            return result

        except Exception as e:
            logger.debug(f"Error looking up product details: {e}")
            return {}

    async def _lookup_product_manufacturer(self, product_url: str, client: httpx.AsyncClient = None) -> Optional[str]:
        """Look up product manufacturer via Willys API. Wrapper for backwards compatibility."""
        details = await self._lookup_product_details(product_url, client)
        return details.get('manufacturer')

    def _is_imported_brand(self, manufacturer: str) -> bool:
        """Check if manufacturer is a known imported meat brand (shared list from category_utils)."""
        if not manufacturer:
            return False
        mfg_lower = manufacturer.lower()
        return any(brand in mfg_lower for brand in IMPORTED_MEAT_BRANDS)

    # ==================== SHARED HELPER FUNCTIONS ====================

    # _parse_price and _parse_unit inherited from StorePlugin base class

    def _fix_swedish_chars(self, text: str) -> str:
        """Fix Swedish characters using central utility."""
        return fix_swedish_chars(text)
    
    def _guess_category_improved(self, product_name: str) -> str:
        """
        Category guessing - delegates to shared utility.

        See languages/sv/category_utils.py for keyword definitions.
        """
        return shared_guess_category(product_name)
