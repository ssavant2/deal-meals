"""
ICA Store Plugin

Scrapes offers from ICA stores (physical stores and online).
No authentication required - all data is from public pages.

ICA has multiple store types: Maxi, Kvantum, Supermarket, Nara.

Physical store (butik):
  Extracts offers from window.__INITIAL_DATA__ on store-specific pages at:
  https://www.ica.se/erbjudanden/{store-slug}-{store-id}/

E-commerce (ehandel):
  Uses Playwright to navigate handlaprivatkund.ica.se with store selection flow.
  Store selection: postal code → Hemleverans → select specific store.
  Products scraped via scroll + DOM extraction (ICA uses list virtualization).
"""

from typing import List, Dict, Optional
from scrapers.stores.base import StorePlugin, StoreConfig, StoreConfigField, StoreScrapeResult
from languages.sv.category_utils import guess_category as shared_guess_category
from languages.sv.category_utils import normalize_api_category as shared_normalize_category
from loguru import logger
from scrapers.stores.weight_utils import parse_weight
from constants_timeouts import HTTP_TIMEOUT, PAGE_LOAD_TIMEOUT, PAGE_NETWORK_IDLE_TIMEOUT, DOMCONTENT_TIMEOUT
import httpx
import re
import json
from utils.security import ssrf_safe_event_hook
from datetime import datetime, timezone
import asyncio


class ICAStore(StorePlugin):
    """
    ICA Store Plugin

    Supports:
    - Physical store offers (via store-specific pages)
    - E-commerce offers (via handla.ica.se)
    """

    def __init__(self):
        self.base_url = "https://www.ica.se"
        self.offers_base = f"{self.base_url}/erbjudanden"
        self._physical_store_catalog: List[Dict] = []

    @property
    def config(self) -> StoreConfig:
        return StoreConfig(
            id="ica",
            name="ICA",
            logo="/scrapers/stores/ica/logo.svg",
            color="#e3000b",  # ICA red
            url="https://www.ica.se",
            enabled=True,
            has_credentials=False,
            description="En del av ditt närområde"
        )

    @property
    def estimated_scrape_time(self) -> int:
        """ICA scraping estimate."""
        return 120  # 2 minutes

    def get_config_fields(self) -> List[StoreConfigField]:
        """Define ICA configuration fields."""
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
                        "description": "Erbjudanden för en specifik ICA-butik"
                    }
                ],
                default="ehandel"
            ),
            # E-handel: dropdown with stores that deliver to user's postal code
            StoreConfigField(
                key="ehandel_store",
                label="Välj e-handels butik",
                field_type="async_select",  # Special type: loads options from API
                placeholder="Välj butik...",
                depends_on={"field": "location_type", "value": "ehandel"},
                invalidate_on_postal_change=True  # Different stores serve different postal codes
            ),
            # Butik: search field for physical stores
            StoreConfigField(
                key="location_search",
                label="Sök specifik butik (stad, adress eller typ)",
                field_type="search",
                placeholder="t.ex. göteborg, maxi, kvantum",
                depends_on={"field": "location_type", "value": "butik"}
            )
        ]

    async def search_locations(self, query: str, postal_code: str = None) -> List[Dict]:
        """
        Search for ICA store locations.

        Args:
            query: Search query (store name, city, etc.)
            postal_code: If provided, search e-commerce stores that deliver to this
                        postal code and filter by query. If None, search physical stores.
        """
        query = query.strip()

        if postal_code:
            # E-commerce mode: search stores that deliver to postal code
            return await self._search_ehandel_stores(postal_code, query)
        else:
            # Physical store mode: search by name/city
            return await self._search_physical_stores(query)

    async def _search_ehandel_stores(self, postal_code: str, query: str = "") -> List[Dict]:
        """
        Search for e-commerce stores that deliver to a postal code.

        Uses https://handla.ica.se/api/store/v1?zip={postnr}&customerType=B2C
        Optionally filters by query (store name/city).
        """
        logger.info(f"Searching ICA e-commerce stores for postal code: {postal_code}, query: '{query}'")
        stores = []

        # Prepare query filter
        query_lower = self._normalize_search(query.lower()) if query else ""
        query_words = query_lower.split() if query_lower else []

        try:
            api_url = "https://handla.ica.se/api/store/v1"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Accept-Language": "sv-SE,sv;q=0.9",
            }

            async with httpx.AsyncClient(follow_redirects=True, timeout=HTTP_TIMEOUT, event_hooks={"request": [ssrf_safe_event_hook]}) as client:
                params = {"zip": postal_code, "customerType": "B2C"}
                response = await client.get(api_url, headers=headers, params=params)

                if response.status_code == 200:
                    data = response.json()

                    if not data.get("validZipCode"):
                        logger.warning(f"Invalid postal code: {postal_code}")
                        return []

                    # Get stores that offer home delivery
                    delivery_stores = data.get("forHomeDelivery", [])
                    logger.info(f"Found {len(delivery_stores)} e-commerce stores for {postal_code}")

                    for store in delivery_stores:
                        store_id = store.get("id", "")
                        name = store.get("name", "")
                        city = store.get("city", "")
                        store_format = store.get("storeFormat", "").title()

                        if not store_id or not name:
                            continue

                        # Filter by query if provided
                        if query_words:
                            searchable = self._normalize_search(f"{name} {city} {store_format}")
                            if not all(word in searchable for word in query_words):
                                continue

                        # Map store format to label
                        format_labels = {
                            "Maxi": "Maxi ICA Stormarknad",
                            "Kvantum": "ICA Kvantum",
                            "Supermarket": "ICA Supermarket",
                            "Nara": "ICA Nära",
                        }
                        format_label = format_labels.get(store_format, store_format)

                        stores.append({
                            "id": store_id,
                            "name": name,
                            "address": f"{city} ({format_label})",
                            "type": "ehandel",
                            "store_format": store_format.lower(),
                            "postal_code": postal_code,
                        })

                    logger.info(f"Returning {len(stores)} stores after filtering")
                    return stores
                else:
                    logger.error(f"E-commerce API error: {response.status_code}")
                    return []

        except Exception as e:
            logger.error(f"Error searching e-commerce stores: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return []

    async def _search_physical_stores(self, query: str) -> List[Dict]:
        """
        Search for physical ICA stores by city/name.

        Uses https://www.ica.se/api/store/search which returns all 1287 stores
        with proper Swedish characters. We filter client-side since the API's
        q parameter doesn't work reliably.
        """
        cache_key = self._build_location_search_cache_key("physical", query)

        async def load_locations() -> List[Dict]:
            logger.info(f"Searching ICA physical stores for: {query}")
            stores = []
            query_lower = self._normalize_search(query.lower())
            query_words = query_lower.split()

            try:
                all_stores = await self._load_physical_store_catalog()

                # Filter stores based on query
                for store in all_stores:
                    try:
                        name = store.get("Name", "")
                        city = store.get("VisitingCity", "")
                        store_type = store.get("ShortProfileName", "")
                        account_number = store.get("AccountNumber", "")

                        if not name or not account_number:
                            continue

                        # Build searchable text
                        searchable = self._normalize_search(
                            f"{name} {city} {store_type}"
                        )

                        # Match ALL query words
                        if not all(word in searchable for word in query_words):
                            continue

                        # Extract offer URL slug from Urls array
                        url_slug = None
                        for url_info in store.get("Urls", []):
                            if url_info.get("Type") == "Erbjudande":
                                offer_url = url_info.get("Url", "")
                                # Extract slug from: https://www.ica.se/erbjudanden/ica-nara-toppen-goteborg-1004063/
                                match = re.search(r"/erbjudanden/([^/]+)/?$", offer_url)
                                if match:
                                    url_slug = match.group(1)
                                break

                        # Fall back to constructing slug from account number
                        if not url_slug:
                            url_slug = f"{account_number}"

                        # Map store type to full label
                        type_labels = {
                            "Nära": "ICA Nära",
                            "Supermarket": "ICA Supermarket",
                            "Kvantum": "ICA Kvantum",
                            "Maxi": "Maxi ICA Stormarknad",
                            "ToGo": "ICA ToGo",
                        }
                        type_label = type_labels.get(store_type, store_type)

                        stores.append({
                            "id": url_slug,
                            "name": name,
                            "address": f"{city} ({type_label})",
                            "type": "butik",
                            "store_type": store_type.lower() if store_type else "other",
                            "store_number": account_number,
                            "url_slug": url_slug
                        })

                    except Exception as e:
                        logger.debug(f"Error parsing store: {e}")
                        continue

                # Remove duplicates (by id)
                seen_ids = set()
                unique_stores = []
                for store in stores:
                    if store["id"] not in seen_ids:
                        seen_ids.add(store["id"])
                        unique_stores.append(store)

                # Sort by relevance (exact city match first, then alphabetically)
                def sort_key(store):
                    # Prioritize exact query word matches in name
                    exact_matches = sum(1 for word in query_words if word in self._normalize_search(store["name"]))
                    return (-exact_matches, store["name"])

                unique_stores.sort(key=sort_key)

                logger.info(f"Found {len(unique_stores)} ICA stores matching '{query}'")
                return unique_stores[:100]  # Return up to 100 results

            except Exception as e:
                logger.error(f"Error searching ICA stores: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                return []

        return await self._get_or_cache_location_search(cache_key, load_locations)

    async def _load_physical_store_catalog(self) -> List[Dict]:
        """Load ICA's full physical store catalog once per runtime."""
        if self._physical_store_catalog:
            return self._physical_store_catalog

        api_url = "https://www.ica.se/api/store/search"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Accept-Language": "sv-SE,sv;q=0.9",
        }

        async with httpx.AsyncClient(follow_redirects=True, timeout=HTTP_TIMEOUT, event_hooks={"request": [ssrf_safe_event_hook]}) as client:
            all_stores = []

            for skip in [0, 1000]:
                params = {"take": 1000, "skip": skip}
                response = await client.get(api_url, headers=headers, params=params)

                if response.status_code != 200:
                    logger.error(f"ICA store API error: {response.status_code}")
                    break

                data = response.json()
                batch = data.get("Documents", [])
                if not isinstance(batch, list):
                    logger.error(f"ICA API 'Documents' is not a list: {type(batch)}")
                    break

                all_stores.extend(batch)
                logger.debug(f"Fetched {len(batch)} stores (skip={skip})")

                if len(batch) < 1000:
                    break

        logger.info(f"Fetched total {len(all_stores)} stores from ICA API")
        self._physical_store_catalog = all_stores
        return self._physical_store_catalog

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

    def _format_city_name(self, city_slug: str) -> str:
        """Format city slug to proper Swedish name."""
        # Common Swedish cities with special characters
        city_mapping = {
            "goteborg": "Göteborg",
            "malmo": "Malmö",
            "linkoping": "Linköping",
            "norrkoping": "Norrköping",
            "orebro": "Örebro",
            "vasteras": "Västerås",
            "helsingborg": "Helsingborg",
            "jonkoping": "Jönköping",
            "lulea": "Luleå",
            "umea": "Umeå",
            "gavle": "Gävle",
            "soderhamn": "Söderhamn",
            "ostersund": "Östersund",
            "stromstad": "Strömstad",
            "karlskrona": "Karlskrona",
            "kristianstad": "Kristianstad",
            "vaxjo": "Växjö",
            "kalmar": "Kalmar",
            "sundsvall": "Sundsvall",
            "boras": "Borås",
            "halmstad": "Halmstad",
            "eskilstuna": "Eskilstuna",
            "karlstad": "Karlstad",
            "taby": "Täby",
            "sollentuna": "Sollentuna",
            "nacka": "Nacka",
            "huddinge": "Huddinge",
            "stockholm": "Stockholm",
            "uppsala": "Uppsala",
            "almhult": "Älmhult",
            "ale": "Ale",
            "alingsas": "Alingsås",
            "ockero": "Öckerö",
            "ovanaker": "Ovanåker",
            "monsteras": "Mönsterås",
            "morbylanga": "Mörbylånga",
        }

        slug_clean = city_slug.replace("-", "").lower()
        if slug_clean in city_mapping:
            return city_mapping[slug_clean]

        # Default: title case
        return city_slug.replace("-", " ").title()

    def _format_store_name(self, name_slug: str) -> str:
        """Format store name slug to proper Swedish name."""
        # Start with title case
        name = name_slug.replace("-", " ").title()

        # Fix ICA prefix
        name = name.replace("Ica ", "ICA ")

        # Fix Swedish words in store names (including city names)
        replacements = {
            # Store type words
            " Nara ": " Nära ",
            " Nara": " Nära",
            "Nara ": "Nära ",
            # Göteborg area
            " Hogsbo": " Högsbo",
            " Ovrells": " Övrells",
            " Kvillebacken": " Kvillebäcken",
            " Munkeback": " Munkebäck",
            " Frolunda": " Frölunda",
            " Molndal": " Mölndal",
            " Molnlycke": " Mölnlycke",
            " Sjomarken": " Sjömarken",
            # Cities with special chars
            " Lulea": " Luleå",
            " Umea": " Umeå",
            " Malmo": " Malmö",
            " Goteborg": " Göteborg",
            " Gavle": " Gävle",
            " Orebro": " Örebro",
            " Vasteras": " Västerås",
            " Jonkoping": " Jönköping",
            " Linkoping": " Linköping",
            " Norrkoping": " Norrköping",
            " Ostersund": " Östersund",
            " Sundsvall": " Sundsvall",
            " Boras": " Borås",
            " Vaxjo": " Växjö",
            " Kalmar": " Kalmar",
            # Common Swedish words
            " Sjo": " Sjö",
            " Ang": " Äng",
            " As ": " Ås ",
            " Strand": " Strand",
        }

        for old, new in replacements.items():
            name = name.replace(old, new)

        return name

    async def scrape_offers(self, credentials: Optional[Dict] = None) -> StoreScrapeResult:
        """
        Scrape offers from ICA.

        For butik: Extracts offers from window.__INITIAL_DATA__.offers.weeklyOffers
        For e-handel: Scrapes from handla.ica.se with selected store
        """
        logger.info("Starting ICA scraping...")
        logger.debug(f"Credentials received: {credentials}")

        location_type = credentials.get("location_type", "ehandel") if credentials else "ehandel"
        failure_reason = None

        if location_type == "butik":
            # Butik uses location_id (which is the url_slug, e.g., "ica-nara-lunden-1004169")
            location_id = credentials.get("location_id") if credentials else None
            url_slug = credentials.get("url_slug") if credentials else None
            store_slug = location_id or url_slug

            if store_slug:
                store_url = f"{self.offers_base}/{store_slug}/"
                logger.info(f"Scraping store: {store_url}")
                products = await self._scrape_store_offers_playwright(store_url)
            else:
                logger.error("No store selected for ICA butik scraping")
                failure_reason = "missing_store_selection"
                products = []
        else:
            # E-handel uses ehandel_store_id from dropdown selection
            logger.debug(f"ICA e-handel credentials received: {credentials}")
            ehandel_store_id = credentials.get("ehandel_store_id") if credentials else None
            ehandel_store_name = credentials.get("ehandel_store_name", "") if credentials else ""
            postal_code = credentials.get("postal_code") if credentials else None
            location_id = credentials.get("location_id") if credentials else None

            if ehandel_store_id:
                logger.info(f"Scraping ICA e-handel for store: {ehandel_store_name} (ID: {ehandel_store_id}), postal: {postal_code}")
                products = await self._scrape_ehandel_offers(
                    ehandel_store_id,
                    postal_code,
                    ehandel_store_name,
                    location_id=location_id,
                )
            else:
                logger.error("No e-handel store selected for ICA")
                failure_reason = "missing_ehandel_store"
                products = []

        # Reclassify obvious non-food from 'other' → 'household'/'hygiene'
        # ICA puts clothing, books, cleaning products etc. in 'other' category
        # Recipe matcher skips household/hygiene, so this prevents false matches
        reclassified = 0
        for product in products:
            if product.get('category') == 'other':
                new_cat = self._reclassify_non_food(product.get('name', ''))
                if new_cat:
                    product['category'] = new_cat
                    reclassified += 1

        logger.success(f"Scraped {len(products)} products from ICA ({reclassified} reclassified to non-food)")
        return self._scrape_result_from_products(
            products,
            location_type=location_type,
            reason=failure_reason,
        )

    def _extract_ica_account_id(self, value: Optional[str]) -> Optional[str]:
        """Extract ICA account/store URL ID (e.g. 1004219) from a slug or raw value."""
        if not value:
            return None

        text = str(value).strip()
        if re.fullmatch(r"\d{7,}", text):
            return text

        match = re.search(r"(\d{7,})$", text)
        if match:
            return match.group(1)

        return None

    async def _resolve_ehandel_account_id(
        self,
        store_id: str,
        postal_code: Optional[str],
        store_name: str = "",
        location_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Resolve ICA e-handel account/store URL ID.

        ICA's location API returns two different IDs:
        - `id`        -> e-handel store selector ID (e.g. 08926)
        - `accountId` -> URL/store page ID used on handlaprivatkund (e.g. 1004219)
        """
        account_id = self._extract_ica_account_id(location_id) or self._extract_ica_account_id(store_id)
        if account_id:
            return account_id

        if not postal_code:
            return None

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Accept-Language": "sv-SE,sv;q=0.9",
            }

            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=HTTP_TIMEOUT,
                event_hooks={"request": [ssrf_safe_event_hook]},
            ) as client:
                response = await client.get(
                    "https://handla.ica.se/api/store/v1",
                    headers=headers,
                    params={"zip": postal_code, "customerType": "B2C"},
                )

            if response.status_code != 200:
                logger.warning(f"Could not resolve ICA accountId ({response.status_code})")
                return None

            data = response.json()
            delivery_stores = data.get("forHomeDelivery", [])
            normalized_name = self._normalize_search((store_name or "").lower())

            for store in delivery_stores:
                if str(store.get("id", "")) == str(store_id):
                    return str(store.get("accountId") or "") or None

            if normalized_name:
                for store in delivery_stores:
                    candidate = self._normalize_search(
                        f"{store.get('name', '')} {store.get('city', '')} {store.get('street', '')}".lower()
                    )
                    if normalized_name and normalized_name in candidate:
                        return str(store.get("accountId") or "") or None

        except Exception as e:
            logger.warning(f"ICA accountId resolution failed for store {store_id}: {e}")

        return None

    def _ingest_ica_product_candidate(self, data: Dict) -> bool:
        """Normalize a single ICA product candidate from API or SSR state into _api_product_map."""
        if not isinstance(data, dict):
            return False

        name = data.get("name") or data.get("productName") or data.get("title") or ""
        if not isinstance(name, str):
            return False
        name = name.strip()

        if not name or re.match(r"^(Ordinarie Pris|Jämförpris|Erbjudande)\b", name, re.IGNORECASE):
            return False

        prod_id = data.get("productId") or data.get("id") or ""
        if not prod_id:
            return False

        price_obj = data.get("price") or {}
        regular_price = None
        if isinstance(price_obj, dict):
            if price_obj.get("amount") is not None:
                regular_price = price_obj.get("amount")
            else:
                current_price = price_obj.get("current") or {}
                if isinstance(current_price, dict) and current_price.get("amount") is not None:
                    regular_price = current_price.get("amount")

        if regular_price is None:
            return False

        try:
            regular_price = float(regular_price)
        except (TypeError, ValueError):
            return False

        if regular_price <= 0:
            return False

        retailer_id = data.get("retailerProductId") or ""
        has_product_shape = bool(
            retailer_id
            or data.get("categoryPath")
            or data.get("imagePaths")
            or data.get("images")
            or data.get("packSizeDescription")
            or data.get("size")
            or data.get("unitPrice")
        )
        if not has_product_shape:
            return False

        offers = []
        primary_offer = data.get("offer")
        if isinstance(primary_offer, dict):
            offers.append(primary_offer)

        list_offers = data.get("promotions") or data.get("offers") or []
        if isinstance(list_offers, dict):
            offers.append(list_offers)
        elif isinstance(list_offers, list):
            offers.extend(pr for pr in list_offers if isinstance(pr, dict))

        offer_parts = []
        for pr in offers:
            desc = pr.get("description") or ""
            if desc and pr.get("type") in (None, "OFFER", "PROMOTION"):
                offer_parts.append(desc)

        offer_desc = " | ".join(dict.fromkeys(offer_parts))
        if not offer_desc:
            return False

        image_url = ""
        img_paths = data.get("imagePaths")
        if isinstance(img_paths, list) and img_paths:
            first = img_paths[0]
            if isinstance(first, str) and first:
                image_url = f"{first.rstrip('/')}/500x500.webp"

        if not image_url:
            image_obj = data.get("image") or {}
            if isinstance(image_obj, dict):
                image_url = image_obj.get("src") or ""

        if not image_url:
            imgs = data.get("images") or []
            if isinstance(imgs, list) and imgs and isinstance(imgs[0], dict):
                srcset = imgs[0].get("bopSrcset") or imgs[0].get("src") or ""
                if isinstance(srcset, str) and srcset:
                    image_url = srcset.split(",")[0].strip().split(" ")[0]

        cat_path_raw = data.get("categoryPath") or []
        category_str = ""
        if isinstance(cat_path_raw, list) and cat_path_raw:
            first_cat = cat_path_raw[0]
            if isinstance(first_cat, str):
                category_str = first_cat

        brand = data.get("brand") or ""
        if isinstance(brand, dict):
            brand = brand.get("name") or ""
        if not isinstance(brand, str):
            brand = ""

        unit_label = ""
        unit_price = data.get("unitPrice") or {}
        if isinstance(unit_price, dict):
            unit_label = unit_price.get("unit") or ""

        if not unit_label and isinstance(price_obj, dict):
            unit_node = price_obj.get("unit") or {}
            if isinstance(unit_node, dict):
                unit_label = unit_node.get("label") or ""

        pack_size = data.get("packSizeDescription") or ""
        if not pack_size:
            size_obj = data.get("size") or {}
            if isinstance(size_obj, dict):
                pack_size = size_obj.get("value") or ""

        key = str(prod_id)
        existing = self._api_product_map.get(key, {})
        self._api_product_map[key] = {
            "product_id": prod_id or existing.get("product_id", ""),
            "retailer_id": retailer_id or existing.get("retailer_id", ""),
            "name": name or existing.get("name", ""),
            "regular_price": regular_price or existing.get("regular_price", 0.0),
            "offer_description": offer_desc or existing.get("offer_description", ""),
            "image_url": image_url or existing.get("image_url", ""),
            "category_path": category_str or existing.get("category_path", ""),
            "brand": brand or existing.get("brand", ""),
            "pack_size": pack_size or existing.get("pack_size", ""),
            "unit_label": unit_label or existing.get("unit_label", ""),
        }
        return True

    def _bootstrap_ica_products_from_initial_state(self, initial_state: Dict) -> int:
        """Seed API product map from server-rendered ICA promotions state."""
        try:
            products_node = ((initial_state or {}).get("data") or {}).get("products") or {}
            entities = products_node.get("productEntities") or {}
            before = len(self._api_product_map)

            if isinstance(entities, dict):
                for entity in entities.values():
                    if isinstance(entity, dict):
                        self._ingest_ica_product_candidate(entity)

            return len(self._api_product_map) - before
        except Exception:
            return 0

    async def _scrape_ehandel_offers(
        self,
        store_id: str,
        postal_code: str = None,
        store_name: str = None,
        location_id: str = None,
    ) -> List[Dict]:
        """
        Scrape offers from ICA e-handel (handlaprivatkund.ica.se).

        Flow:
        1. Go to handla.ica.se/?chooseStore=true
        2. Enter postal code
        3. Click "Hemleverans" (home delivery)
        4. Select the SPECIFIC store (by ID or name)
        5. Navigate to promotions page - NOW prices are visible!

        Args:
            store_id: ICA store ID (e.g., "1004219")
            postal_code: User's postal code for delivery (e.g., "41658")
            store_name: Store name to search for (e.g., "Maxi ICA Stormarknad Göteborg")
        """
        from playwright.async_api import async_playwright
        import json

        if not postal_code:
            logger.error("No postal code configured - delivery address check should have caught this")
            return []

        logger.info(f"Scraping ICA e-handel for store {store_id} with postal code {postal_code}")

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox"]
                )

                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    locale="sv-SE",
                )
                page = await context.new_page()

                # Capture API responses as the primary product data source.
                # React hydration removes the aria-labels we previously relied on, so DOM
                # extraction became unreliable. The same JSON the frontend consumes is
                # captured here and used to build the offer list.
                self._api_brand_map = {}    # name_lower -> brand
                self._api_product_map = {}  # productId -> full product dict

                async def capture_product_api(response):
                    """Capture JSON API responses containing product data."""
                    try:
                        url = response.url
                        ct = response.headers.get('content-type', '')
                        if 'json' not in ct:
                            return
                        normalized_url = url.lower()
                        if not any(
                            marker in normalized_url
                            for marker in (
                                "webproductpagews",
                                "/api/product-listing-pages/",
                                "/v1/pages/promotions",
                                "productquerylayer",
                            )
                        ):
                            return
                        body = await response.json()
                        self._extract_brands_from_api(body)
                        self._extract_products_from_api(body)
                    except Exception:
                        logger.debug(f"ICA product API capture failed for {response.url}")

                page.on('response', capture_product_api)

                resolved_account_id = await self._resolve_ehandel_account_id(
                    store_id,
                    postal_code,
                    store_name or "",
                    location_id=location_id,
                )
                actual_store_id = resolved_account_id or str(store_id)
                if resolved_account_id:
                    logger.info(f"Resolved ICA e-handel accountId: {resolved_account_id}")
                else:
                    logger.warning(
                        f"Could not resolve ICA accountId for selector store {store_id}; "
                        "falling back to legacy store-selection flow"
                    )

                async def bootstrap_initial_state(source_label: str) -> int:
                    try:
                        initial_state = await page.evaluate("() => window.__INITIAL_STATE__ || null")
                    except Exception as e:
                        logger.debug(f"{source_label}: could not read window.__INITIAL_STATE__: {e}")
                        return 0

                    if not isinstance(initial_state, dict):
                        return 0

                    bootstrapped = self._bootstrap_ica_products_from_initial_state(initial_state)
                    if bootstrapped:
                        logger.info(
                            f"{source_label}: bootstrapped {bootstrapped} ICA products from __INITIAL_STATE__"
                        )
                    return bootstrapped

                prefetched_on_offer_api = False

                async def fetch_on_offer_category_api(source_label: str) -> int:
                    """
                    Fetch the full "Alla kampanjer" category API.

                    Some ICA e-handel stores (notably Kvantum/Focus) do not expose
                    /promotions. Their frontend instead renders the on-offer filter
                    through this v6 product-pages endpoint.
                    """
                    nonlocal prefetched_on_offer_api
                    initial_total = len(self._api_product_map)
                    if "handlaprivatkund.ica.se" not in page.url:
                        store_url = f"https://handlaprivatkund.ica.se/stores/{actual_store_id}"
                        try:
                            response = await page.goto(
                                store_url,
                                timeout=60000,
                                wait_until="domcontentloaded",
                            )
                            await asyncio.sleep(2)
                            status = response.status if response else None
                            logger.info(
                                f"{source_label}: loaded store page status={status}, url={page.url}"
                            )
                        except Exception as e:
                            logger.debug(f"{source_label}: could not load store page: {e}")
                    else:
                        logger.debug(
                            f"{source_label}: using existing ICA page context for API fetch: {page.url}"
                        )

                    api_url = (
                        f"https://handlaprivatkund.ica.se/stores/{actual_store_id}"
                        "/api/webproductpagews/v6/product-pages"
                        "?filters=boolean%3DonOffer"
                        "&includeAdditionalPageInfo=true"
                        "&maxPageSize=1000"
                        "&maxProductsToDecorate=1000"
                        "&sortOptionId=favorite"
                        "&tag=web"
                        "&tag=category-item"
                    )

                    try:
                        polite_delay_seconds = 2.0
                        logger.info(
                            f"{source_label}: waiting {polite_delay_seconds:.1f}s before on-offer API fetch"
                        )
                        await asyncio.sleep(polite_delay_seconds)
                        result = await page.evaluate("""
                            async (url) => {
                                const response = await fetch(url, {
                                    credentials: 'include',
                                    headers: { accept: 'application/json' }
                                });
                                const text = await response.text();
                                let body = null;
                                try {
                                    body = JSON.parse(text);
                                } catch (error) {
                                    body = null;
                                }
                                return {
                                    status: response.status,
                                    url: response.url,
                                    textLength: text.length,
                                    body
                                };
                            }
                        """, api_url)
                    except Exception as e:
                        logger.debug(f"{source_label}: on-offer API fetch failed: {e}")
                        return 0

                    status = result.get("status")
                    body = result.get("body")
                    if status != 200 or not isinstance(body, dict):
                        logger.info(
                            f"{source_label}: on-offer API unavailable "
                            f"(status={status}, bytes={result.get('textLength')})"
                        )
                        return 0

                    before_extract = len(self._api_product_map)
                    self._extract_brands_from_api(body)
                    self._extract_products_from_api(body)
                    extracted = len(self._api_product_map) - before_extract
                    added = len(self._api_product_map) - initial_total
                    logger.info(
                        f"{source_label}: fetched ICA on-offer API "
                        f"(status={status}, bytes={result.get('textLength')}, "
                        f"added={added}, extracted={extracted}, "
                        f"total_api_products={len(self._api_product_map)})"
                    )
                    if added:
                        prefetched_on_offer_api = True
                    return added

                # Block navigation away from the promotions page
                original_url_host = "handlaprivatkund.ica.se"

                async def block_navigation(route):
                    """Block navigations that would leave the promotions page."""
                    url = route.request.url
                    if original_url_host not in url and "handla.ica.se" in url:
                        logger.info(f"Blocked navigation to: {url}")
                        await route.abort()
                    else:
                        await route.continue_()

                # Strategy: Complete the store selection flow on handla.ica.se
                # ICA redirects to store selector if no store is selected
                direct_navigation_ok = False
                if resolved_account_id:
                    direct_candidates = [
                        ("direct promotions", f"https://handlaprivatkund.ica.se/stores/{actual_store_id}/promotions"),
                    ]

                    for label, direct_url in direct_candidates:
                        logger.info(f"Trying {label}: {direct_url}")
                        try:
                            response = await page.goto(
                                direct_url,
                                timeout=60000,
                                wait_until="domcontentloaded",
                            )
                            await asyncio.sleep(4)
                            current_url = page.url
                            status = response.status if response else None
                            bootstrapped = await bootstrap_initial_state(label)
                            logger.info(
                                f"{label} result: status={status}, url={current_url}, "
                                f"bootstrapped={bootstrapped}, api_products={len(self._api_product_map)}"
                            )

                            if status == 200 and (
                                "promotions" in current_url
                                or "boolean=onoffer" in current_url.lower()
                            ):
                                direct_navigation_ok = True
                                break
                        except Exception as e:
                            logger.debug(f"{label} failed: {e}")

                    if not direct_navigation_ok:
                        added = await fetch_on_offer_category_api("direct on-offer category API")
                        if added:
                            direct_navigation_ok = True

                if not direct_navigation_ok:
                    # Step 1: Go to store selector page directly
                    store_select_url = "https://handla.ica.se/?chooseStore=true"
                    logger.info(f"Step 1: Loading store selector: {store_select_url}")
                    await page.goto(store_select_url, timeout=60000, wait_until="domcontentloaded")
                    await asyncio.sleep(3)

                    # Step 2: Handle cookie consent
                    try:
                        cookie_btn = page.locator('button#onetrust-accept-btn-handler, button:has-text("Godkänn")').first
                        if await cookie_btn.is_visible(timeout=3000):
                            await cookie_btn.click()
                            logger.info("Clicked cookie consent")
                            await asyncio.sleep(1)
                    except Exception:
                        pass

                    # Step 3: Enter postal code
                    logger.info(f"Step 3: Entering postal code: {postal_code}")
                    try:
                        postal_input = page.locator('input#zipcode, input[name="zipcode"]').first
                        await postal_input.wait_for(timeout=10000)
                        await postal_input.fill(postal_code)
                        await asyncio.sleep(1)
                        await postal_input.press("Enter")
                        logger.info(f"Submitted postal code: {postal_code}")
                        await asyncio.sleep(4)  # Wait for delivery options to load
                    except Exception as e:
                        logger.error(f"Could not enter postal code: {e}")

                    # Step 4: Click home delivery ('Hemleverans') button using JavaScript (to bypass modal backdrop)
                    # The ICA modal has a backdrop that intercepts regular clicks
                    logger.info("Step 4: Clicking home delivery ('Hemleverans') button via JavaScript")
                    hemleverans_clicked = await page.evaluate("""
                        () => {
                            // Find Hemleverans button by data-automation-id or text
                            const btn = document.querySelector('[data-automation-id="store-selector-view-home-delivery"]') ||
                                       Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Hemleverans'));
                            if (btn) {
                                btn.click();
                                return true;
                            }
                            return false;
                        }
                    """)
                    logger.info(f"Home delivery ('Hemleverans') clicked: {hemleverans_clicked}")
                    await asyncio.sleep(3)

                    # Step 4b: Click "Stores near you" ('Butiker nära dig') to show the list
                    logger.info("Step 4b: Clicking 'Stores near you' ('Butiker nära dig') via JavaScript")
                    butiker_clicked = await page.evaluate("""
                        () => {
                            // Find "Butiker nära dig" button
                            const buttons = Array.from(document.querySelectorAll('button'));
                            const btn = buttons.find(b => b.textContent.includes('Butiker nära dig'));
                            if (btn) {
                                btn.click();
                                return true;
                            }
                            return false;
                        }
                    """)
                    logger.info(f"Stores near you ('Butiker nära dig') clicked: {butiker_clicked}")
                    await asyncio.sleep(3)

                    # Step 5: Select the SPECIFIC store from the list via JavaScript
                    # After clicking "Butiker nära dig", a list of stores should be visible
                    logger.info(f"Step 5: Selecting store via JavaScript: {store_name} (ID: {store_id})")

                    # Use JavaScript to find and click the store - bypasses modal backdrop issues
                    store_selection_result = await page.evaluate("""
                    (params) => {
                        const storeId = params.storeId;
                        const storeName = params.storeName.toLowerCase();
                        const result = { found: false, method: '', storeListItems: 0, debug: [] };

                        // Look for store list items - ICA uses various class patterns
                        const storeItems = document.querySelectorAll(
                            '.store-selector-stores-list li, ' +
                            '[class*="store-list"] li, ' +
                            '[class*="StoreList"] li, ' +
                            '.store-selector__stores-list li, ' +
                            'ul li[class*="store"]'
                        );
                        result.storeListItems = storeItems.length;

                        // Debug: log what elements we find in the dialog
                        const dialog = document.querySelector('#store-selector-app');
                        if (dialog) {
                            const buttons = dialog.querySelectorAll('button');
                            result.debug.push(`Dialog has ${buttons.length} buttons`);
                            buttons.forEach((btn, i) => {
                                if (i < 5) result.debug.push(`Button ${i}: ${btn.textContent.substring(0, 50)}`);
                            });
                        }

                        // Method 1a: Look for EXACT store ID match in HTML/href
                        for (const item of storeItems) {
                            const html = item.innerHTML;
                            // Look for store ID in href or data attributes
                            if (html.includes(`/${storeId}`) || html.includes(`"${storeId}"`) || html.includes(`=${storeId}`)) {
                                const btn = item.querySelector('button');
                                if (btn) {
                                    result.debug.push(`Matched by ID: ${storeId}`);
                                    btn.click();
                                    result.found = true;
                                    result.method = 'exact-id-match';
                                    return result;
                                }
                            }
                        }

                        // Method 1b: Look for EXACT store name match (normalize whitespace)
                        const normalizedStoreName = storeName.replace(/\\s+/g, ' ').trim();
                        for (const item of storeItems) {
                            const text = item.textContent.toLowerCase().replace(/\\s+/g, ' ').trim();
                            // Check if text contains the exact store name (not just a substring of a longer name)
                            // Look for the name followed by address info or end of text
                            if (text.includes(normalizedStoreName + ',') ||
                                text.includes(normalizedStoreName + ' -') ||
                                text.includes(normalizedStoreName + '(') ||
                                text.endsWith(normalizedStoreName) ||
                                text === normalizedStoreName) {
                                const btn = item.querySelector('button');
                                if (btn) {
                                    result.debug.push(`Matched by exact name: ${normalizedStoreName}`);
                                    btn.click();
                                    result.found = true;
                                    result.method = 'exact-name-match';
                                    return result;
                                }
                            }
                        }

                        // Method 1c: Fallback to substring match but log a warning
                        for (const item of storeItems) {
                            const text = item.textContent.toLowerCase();
                            if (text.includes(storeName)) {
                                const btn = item.querySelector('button');
                                if (btn) {
                                    result.debug.push(`WARNING: Substring match for: ${storeName}`);
                                    result.debug.push(`Matched text: ${text.substring(0, 100)}`);
                                    btn.click();
                                    result.found = true;
                                    result.method = 'substring-name-match';
                                    return result;
                                }
                            }
                        }

                        // Method 2: Look for store links with ID in href
                        const storeLinks = document.querySelectorAll(`a[href*="${storeId}"]`);
                        if (storeLinks.length > 0) {
                            storeLinks[0].click();
                            result.found = true;
                            result.method = 'store-link';
                            return result;
                        }

                        // Method 3: Look for any button with store name text
                        const allButtons = document.querySelectorAll('button');
                        for (const btn of allButtons) {
                            const text = btn.textContent.toLowerCase();
                            if (text.includes(storeName) || (text.includes('välj') && btn.closest('li')?.textContent.toLowerCase().includes(storeName))) {
                                btn.click();
                                result.found = true;
                                result.method = 'name-button';
                                return result;
                            }
                        }

                        // Method 4: Fallback - click first "Välj butik" inside a store list
                        const valjButtons = Array.from(document.querySelectorAll('button')).filter(b =>
                            b.textContent.trim() === 'Välj butik' ||
                            b.textContent.includes('Välj')
                        );
                        result.debug.push(`Found ${valjButtons.length} Välj buttons`);

                        if (valjButtons.length > 0) {
                            // Try to find one that's inside a list structure
                            for (const btn of valjButtons) {
                                const parent = btn.closest('li') || btn.closest('[class*="store"]');
                                if (parent) {
                                    btn.click();
                                    result.found = true;
                                    result.method = 'valj-button-in-list';
                                    return result;
                                }
                            }

                            // Last resort - click the first one
                            valjButtons[0].click();
                            result.found = true;
                            result.method = 'first-valj-button';
                        }

                        return result;
                    }
                    """, {"storeId": store_id, "storeName": store_name or ""})

                    found_store = store_selection_result.get('found', False)
                    logger.info(f"Store selection result: {store_selection_result}")
                    await asyncio.sleep(5)  # Wait for redirect to store page

                    logger.info(f"Store selection complete. found_store={found_store}")

                    # Step 6: Navigate to promotions page
                    # IMPORTANT: Extract the ACTUAL store ID from the URL, not the API's ID
                    # The API returns one ID format (e.g., "12313") but the URL uses internal IDs (e.g., "1003415")
                    current_url = page.url
                    logger.info(f"Current URL after store selection: {current_url}")

                    # Extract actual store ID from URL if we're on handlaprivatkund.ica.se
                    if "handlaprivatkund.ica.se/stores/" in current_url:
                        url_match = re.search(r'/stores/(\d+)', current_url)
                        if url_match:
                            actual_store_id = url_match.group(1)
                            if actual_store_id != store_id:
                                logger.info(f"Using URL store ID ({actual_store_id}) instead of API ID ({store_id})")

                    # Step 6: Navigate to offers ('Erbjudanden') page via categories menu
                    # The direct URL /stores/{id}/promotions doesn't work for all stores
                    # Instead, we need to click through 'Kategorier' -> 'Erbjudanden'
                    if "handlaprivatkund.ica.se" in current_url:
                        logger.info("Step 6: Navigating to offers ('Erbjudanden') via categories menu")

                        # Try multiple methods to find and click Erbjudanden
                        erbjudanden_clicked = await page.evaluate("""
                            () => {
                                const result = { clicked: false, method: '', debug: [] };

                                // Method 1: Direct link to erbjudanden in navigation
                                const directLinks = document.querySelectorAll('a[href*="erbjudanden"], a[href*="Erbjudanden"], a[href*="offers"], a[href*="promotions"]');
                                result.debug.push(`Found ${directLinks.length} direct erbjudanden links`);
                                for (const link of directLinks) {
                                    // Skip links that are just anchors or have weird paths
                                    const href = link.getAttribute('href') || '';
                                    const individualOffer = /\\/offers\\/[^/?#]+\\/[^/?#]+/.test(href);
                                    if (href && !href.startsWith('#') && !href.includes('external') && !individualOffer) {
                                        result.debug.push(`Clicking: ${href}`);
                                        link.click();
                                        result.clicked = true;
                                        result.method = 'direct-link';
                                        return result;
                                    }
                                }

                                // Method 2: Click Kategorier button to open menu, then find Erbjudanden
                                const kategoriButtons = document.querySelectorAll('button, a, [role="button"]');
                                for (const btn of kategoriButtons) {
                                    const text = btn.textContent.toLowerCase().trim();
                                    if (text.includes('kategori')) {
                                        result.debug.push(`Found Kategorier button: ${text}`);
                                        btn.click();
                                        result.debug.push('Clicked Kategorier, waiting for menu...');
                                        // Return to allow menu to open, we'll continue in next step
                                        result.method = 'kategorier-clicked';
                                        result.clicked = false;
                                        return result;
                                    }
                                }

                                // Method 3: Look in visible navigation/menu items
                                const allLinks = document.querySelectorAll('nav a, [class*="nav"] a, [class*="menu"] a, header a');
                                for (const link of allLinks) {
                                    const text = link.textContent.toLowerCase().trim();
                                    if (text.includes('erbjud') || text.includes('rabatt') || text.includes('deal') || text.includes('offer')) {
                                        result.debug.push(`Found nav link: ${text}`);
                                        link.click();
                                        result.clicked = true;
                                        result.method = 'nav-link';
                                        return result;
                                    }
                                }

                                return result;
                            }
                        """)
                        logger.info(f"Offers ('Erbjudanden') navigation result: {erbjudanden_clicked}")
                        await asyncio.sleep(3)

                        # If categories ('Kategorier') was clicked, wait for menu and click offers
                        if erbjudanden_clicked.get('method') == 'kategorier-clicked':
                            logger.info("Categories menu opened, looking for offers ('Erbjudanden')...")
                            await asyncio.sleep(2)  # Wait for menu animation

                            erbjudanden_in_menu = await page.evaluate("""
                                () => {
                                    const result = { clicked: false, debug: [] };

                                    // Look for Erbjudanden in the now-open menu
                                    const menuItems = document.querySelectorAll('a, button, [role="menuitem"]');
                                    for (const item of menuItems) {
                                        const text = item.textContent.toLowerCase().trim();
                                        if (text.includes('erbjud') || text === 'erbjudanden') {
                                            result.debug.push(`Found in menu: ${text}`);
                                            item.click();
                                            result.clicked = true;
                                            return result;
                                        }
                                    }

                                    // List what we found for debugging
                                    const visibleItems = Array.from(document.querySelectorAll('[class*="menu"] a, [class*="dropdown"] a, [class*="Category"] a'))
                                        .slice(0, 10)
                                        .map(a => a.textContent.trim());
                                    result.debug.push(`Visible menu items: ${visibleItems.join(', ')}`);

                                    return result;
                                }
                            """)
                            logger.info(f"Offers ('Erbjudanden') in menu result: {erbjudanden_in_menu}")
                            await asyncio.sleep(3)

                        # Check current URL after navigation attempts
                        current_url = page.url
                        logger.info(f"URL after Erbjudanden navigation: {current_url}")

                        # ICA e-handel stores have multiple different offer surfaces:
                        # 1. /promotions - dedicated promotions page (e.g., Maxi Göteborg 1004219)
                        # 2. v6 category API with filters=boolean=onOffer (e.g., ICA Focus 1004247)
                        # 3. Legacy /categories?boolean=onOffer URL fallback
                        # We try each pattern and use whichever works.

                        offers_found = False

                        # Pattern 1: Try /promotions first (some stores have this)
                        # Maxi stores serve a dedicated promotions page with the full offer catalog.
                        # Smaller stores (e.g. Nära, Supermarket) return 404 and we fall back to the
                        # onOffer category filter. ICA's HTML always includes the Swedish string
                        # "finns inte" inside i18n translation dumps, so the page response status
                        # is the only reliable signal.
                        promotions_url = f"https://handlaprivatkund.ica.se/stores/{actual_store_id}/promotions"
                        logger.info(f"Trying promotions URL: {promotions_url}")
                        try:
                            response = await page.goto(promotions_url, timeout=30000, wait_until="domcontentloaded")
                            await asyncio.sleep(3)
                            current_url = page.url
                            status = response.status if response else None
                            await bootstrap_initial_state("legacy promotions fallback")

                            if status == 200 and "promotions" in current_url:
                                logger.info(f"Promotions page works ({status}): {current_url}")
                                offers_found = True
                            else:
                                logger.info(f"Promotions page not available (status={status}, url={current_url})")
                        except Exception as e:
                            logger.debug(f"Promotions URL failed: {e}")

                        # Pattern 2: Fall back to the same "Alla kampanjer" category API
                        # that ICA's frontend calls when the on-offer checkbox is selected.
                        if not offers_found:
                            added = await fetch_on_offer_category_api("legacy on-offer category API")
                            if added:
                                offers_found = True

                        # Pattern 3: Legacy URL fallback.
                        if not offers_found:
                            offers_url = f"https://handlaprivatkund.ica.se/stores/{actual_store_id}/categories?boolean=onOffer&sortBy=favorite"
                            logger.info(f"Trying categories with onOffer filter: {offers_url}")
                            try:
                                await page.goto(offers_url, timeout=60000, wait_until="domcontentloaded")
                                await asyncio.sleep(5)
                                current_url = page.url
                                await bootstrap_initial_state("legacy categories fallback")
                                logger.info(f"Successfully navigated to: {current_url}")
                                offers_found = True
                            except Exception as e:
                                logger.error(f"Failed to navigate to offers page: {e}")

                    elif "handla.ica.se" in current_url:
                        # Still on store selector - this shouldn't happen after store selection
                        logger.warning(f"Still on store selector after store selection, current URL: {current_url}")

                current_url = page.url
                logger.info(f"Final URL: {current_url}")
                await bootstrap_initial_state("final page")

                # Initialize products list (used later regardless of code path)
                all_extracted_products = []

                # Check if we're on a page that might have products
                # The key URL patterns for ICA e-handel offers:
                # - /categories?boolean=onOffer (all offers)
                # - /categories (all products)
                # - /promotions (some stores have this, others don't)
                is_offers_page = "onoffer" in current_url.lower() or "boolean=onoffer" in current_url.lower()
                is_product_page = any(pattern in current_url.lower() for pattern in [
                    "promotion", "erbjud", "categor", "search", "catalog"
                ])
                is_store_page = "handlaprivatkund.ica.se/stores/" in current_url

                if is_offers_page:
                    logger.info(f"On offers page (Alla kampanjer): {current_url}")
                elif is_product_page:
                    logger.info(f"On product page: {current_url}")
                elif is_store_page:
                    logger.info(f"On store page: {current_url}")
                else:
                    logger.error(f"Not on expected page. Current URL: {current_url}")
                    return []

                logger.info("Attempting to scrape products...")

                # Try to find and scrape products
                if prefetched_on_offer_api:
                    logger.info("On-offer API already loaded products; skipping product-card wait")
                else:
                    logger.info("Waiting for products to load...")
                    try:
                        # Wait for product cards to appear
                        await page.wait_for_selector('.product-card-container, [class*="ProductCard"], [class*="product-card"]', timeout=15000)
                        logger.info("Product cards appeared")
                        await asyncio.sleep(2)
                    except Exception as e:
                        logger.warning(f"Timeout waiting for products: {e}")

                # ICA uses list virtualization - only visible cards have real content
                # We need to scroll and extract products incrementally
                logger.info("Extracting products while scrolling (ICA uses virtualization)...")

                all_extracted_products = []
                seen_product_names = set()
                max_scroll_attempts = 150  # Increased to reach all products
                scroll_pause = 1.5
                no_new_products_count = 0
                last_total = 0
                scroll_start_time = asyncio.get_event_loop().time()
                scroll_timeout = 480  # 8 minutes overall timeout for scroll loop
                evaluate_timeout = 10  # 10 seconds per page.evaluate() call

                for scroll_attempt in range(max_scroll_attempts):
                    # Check overall timeout
                    elapsed = asyncio.get_event_loop().time() - scroll_start_time
                    if elapsed > scroll_timeout:
                        logger.warning(f"Scroll loop timeout ({scroll_timeout}s) reached after {scroll_attempt} scrolls, returning {len(all_extracted_products)} products")
                        break

                    # Extract products currently visible
                    try:
                        batch = await asyncio.wait_for(page.evaluate("""
                        () => {
                            const products = [];
                            const skipped = [];
                            const allCards = document.querySelectorAll('.product-card-container');

                            for (const card of allCards) {
                                // Skip skeleton placeholders
                                if (card.innerHTML.includes('_skeleton_')) continue;
                                if (card.querySelector('[class*="skeleton"]')) continue;

                                // Extract name - try multiple methods
                                let name = '';
                                let extractMethod = '';

                                // Method 1: aria-label on card itself
                                const ariaLabel = card.getAttribute('aria-label');
                                if (ariaLabel) {
                                    name = ariaLabel
                                        .replace(/^(Lägg till|Ta bort)\\s*/i, '')
                                        .replace(/\\s*(i varukorg|från varukorg)$/i, '')
                                        .trim();
                                    extractMethod = 'aria-label-card';
                                }

                                // Method 2: aria-label on child element
                                if (!name || name.length < 3) {
                                    const ariaChild = card.querySelector('[aria-label]');
                                    if (ariaChild) {
                                        const childLabel = ariaChild.getAttribute('aria-label');
                                        if (childLabel) {
                                            name = childLabel
                                                .replace(/^(Lägg till|Ta bort)\\s*/i, '')
                                                .replace(/\\s*(i varukorg|från varukorg)$/i, '')
                                                .trim();
                                            extractMethod = 'aria-label-child';
                                        }
                                    }
                                }

                                // Method 3: Product name element (common pattern)
                                if (!name || name.length < 3) {
                                    const nameEl = card.querySelector('[class*="product-name"], [class*="ProductName"], [class*="title"], h3, h4');
                                    if (nameEl) {
                                        name = nameEl.textContent.trim();
                                        extractMethod = 'name-element';
                                    }
                                }

                                // Method 4: Image alt attribute
                                if (!name || name.length < 3) {
                                    const imgEl = card.querySelector('img');
                                    if (imgEl && imgEl.alt) {
                                        name = imgEl.alt.trim();
                                        extractMethod = 'img-alt';
                                    }
                                }

                                // Method 5: Link text (for book/media products)
                                if (!name || name.length < 3) {
                                    const linkEl = card.querySelector('a[href*="/products/"]');
                                    if (linkEl) {
                                        // Try to get product name from URL
                                        const href = linkEl.getAttribute('href');
                                        const urlMatch = href.match(/\\/products\\/([^\\/]+)/);
                                        if (urlMatch) {
                                            name = decodeURIComponent(urlMatch[1]).replace(/-/g, ' ');
                                            extractMethod = 'url-decode';
                                        }
                                    }
                                }

                                // Method 6: First meaningful text content
                                if (!name || name.length < 3) {
                                    // Get text nodes directly under card children (not deep nested)
                                    const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
                                    let textNode;
                                    while (textNode = walker.nextNode()) {
                                        const text = textNode.textContent.trim();
                                        // Skip price/quantity text
                                        if (text.length >= 3 && !text.match(/^\\d+[,.]?\\d*\\s*(kr|st|g|ml|l|kg)$/i)) {
                                            name = text;
                                            extractMethod = 'text-walker';
                                            break;
                                        }
                                    }
                                }

                                if (!name || name.length < 3) {
                                    // Log skipped card for debugging
                                    skipped.push({
                                        html: card.outerHTML.substring(0, 500),
                                        textContent: card.textContent.substring(0, 200)
                                    });
                                    continue;
                                }

                                // Get price
                                const priceText = card.textContent || '';
                                const priceMatch = priceText.match(/(\\d+)[,.]?(\\d{0,2})\\s*kr/i);
                                const price = priceMatch ? parseFloat(priceMatch[1] + '.' + (priceMatch[2] || '00')) : 0;

                                // Get full card text for offer parsing
                                const offerDesc = card.textContent.trim().replace(/\\s+/g, ' ');

                                // Get image
                                const imgEl = card.querySelector('img');
                                const imageUrl = imgEl ? (imgEl.src || imgEl.getAttribute('data-src')) : null;

                                // Get product URL from link (use handlaprivatkund for e-commerce)
                                let productUrl = null;
                                const productLink = card.querySelector('a[href*="/produkt/"], a[href*="/products/"], a[href]');
                                if (productLink) {
                                    const href = productLink.getAttribute('href');
                                    if (href && !href.startsWith('#') && !href.startsWith('javascript:')) {
                                        productUrl = href.startsWith('http') ? href : 'https://handlaprivatkund.ica.se' + href;
                                    }
                                }

                                // Detect multi-buy offers (e.g., "2 för 85 kr")
                                let isMultiBuy = false;
                                let multiBuyQty = null;
                                let multiBuyPrice = null;
                                const multiBuyMatch = offerDesc.match(/(\\d+)\\s*(?:för|st)\\s*(\\d+(?:[,.]\\d+)?)\\s*kr/i);
                                if (multiBuyMatch) {
                                    isMultiBuy = true;
                                    multiBuyQty = parseInt(multiBuyMatch[1]);
                                    multiBuyPrice = parseFloat(multiBuyMatch[2].replace(',', '.'));
                                }

                                products.push({
                                    name: name,
                                    price: price,
                                    offer_description: offerDesc,
                                    image_url: imageUrl,
                                    product_url: productUrl,
                                    is_multi_buy: isMultiBuy,
                                    multi_buy_quantity: multiBuyQty,
                                    multi_buy_price: multiBuyPrice,
                                    _extractMethod: extractMethod
                                });
                            }
                            return { products: products, skipped: skipped };
                        }
                    """), timeout=evaluate_timeout)
                    except asyncio.TimeoutError:
                        logger.warning(f"Scroll {scroll_attempt + 1}: DOM product extraction timed out ({evaluate_timeout}s), continuing — API capture still active")
                        batch = {'products': [], 'skipped': []}
                    except Exception as e:
                        logger.warning(f"Scroll {scroll_attempt + 1}: DOM product extraction failed ({e}), continuing — API capture still active")
                        batch = {'products': [], 'skipped': []}

                    # Extract products and skipped info from result
                    batch_products = batch.get('products', [])
                    batch_skipped = batch.get('skipped', [])

                    # Log skipped cards occasionally for debugging
                    if batch_skipped and scroll_attempt % 10 == 0:
                        logger.debug(f"Skipped {len(batch_skipped)} cards without extractable names")
                        if batch_skipped:
                            logger.debug(f"Sample skipped card text: {batch_skipped[0].get('textContent', '')[:100]}")

                    # Add new products to our collection
                    new_count = 0
                    for p in batch_products:
                        name_lower = p['name'].lower()
                        if name_lower not in seen_product_names:
                            seen_product_names.add(name_lower)
                            all_extracted_products.append(p)
                            new_count += 1
                            # Log extraction method for first few products
                            if len(all_extracted_products) <= 5:
                                logger.debug(f"Extracted '{p['name'][:50]}' via {p.get('_extractMethod', 'unknown')}")

                    # Stop signal: track API-captured product count (DOM extraction is unreliable
                    # post-hydration; API has all ~900 products, DOM dedup collapses to ~224).
                    api_total = len(self._api_product_map)
                    dom_total = len(all_extracted_products)

                    if api_total > last_total:
                        api_new = api_total - last_total
                        logger.info(f"Scroll {scroll_attempt + 1}: API +{api_new} (total {api_total}), DOM +{new_count} (total {dom_total})")
                        last_total = api_total
                        no_new_products_count = 0
                    else:
                        no_new_products_count += 1
                        logger.debug(f"Scroll {scroll_attempt + 1}: no new API products ({no_new_products_count}/5), API={api_total} DOM={dom_total}")

                    # Check if we've reached the true end of products
                    # Footer detection is only valid if NO skeleton placeholders are visible
                    try:
                        end_of_page_info = await asyncio.wait_for(page.evaluate("""
                            () => {
                                // First check if there are skeleton placeholders still loading
                                const allCards = document.querySelectorAll('.product-card-container');
                                let skeletonCount = 0;
                                let realProductCount = 0;

                                for (const card of allCards) {
                                    const rect = card.getBoundingClientRect();
                                    // Only check cards in or near the viewport
                                    if (rect.top < window.innerHeight + 500) {
                                        if (card.innerHTML.includes('_skeleton_') || card.querySelector('[class*="skeleton"]')) {
                                            skeletonCount++;
                                        } else {
                                            realProductCount++;
                                        }
                                    }
                                }

                                // Check if we're near the bottom of the page
                                const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
                                const scrollHeight = document.documentElement.scrollHeight;
                                const clientHeight = window.innerHeight;
                                const nearBottom = (scrollHeight - scrollTop - clientHeight) < 200;

                                // Only look for footer if no skeletons visible AND near bottom
                                if (skeletonCount === 0 && nearBottom) {
                                    const footerTexts = ['Kontakta oss', 'Cookiepolicy', 'Kundservice'];
                                    for (const text of footerTexts) {
                                        const elements = document.evaluate(
                                            `//*[contains(text(), '${text}')]`,
                                            document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null
                                        );
                                        for (let i = 0; i < elements.snapshotLength; i++) {
                                            const el = elements.snapshotItem(i);
                                            const rect = el.getBoundingClientRect();
                                            if (rect.top < window.innerHeight && rect.bottom > 0) {
                                                return {
                                                    footerFound: text,
                                                    skeletonCount: skeletonCount,
                                                    realProductCount: realProductCount,
                                                    nearBottom: nearBottom
                                                };
                                            }
                                        }
                                    }
                                }

                                return {
                                    footerFound: null,
                                    skeletonCount: skeletonCount,
                                    realProductCount: realProductCount,
                                    nearBottom: nearBottom
                                };
                            }
                        """), timeout=evaluate_timeout)
                    except asyncio.TimeoutError:
                        logger.warning(f"Scroll {scroll_attempt + 1}: end-of-page check timed out ({evaluate_timeout}s), continuing")
                        end_of_page_info = {'footerFound': None, 'skeletonCount': 0, 'realProductCount': 0, 'nearBottom': False}
                    except Exception as e:
                        logger.warning(f"Scroll {scroll_attempt + 1}: end-of-page check failed ({e}), continuing")
                        end_of_page_info = {'footerFound': None, 'skeletonCount': 0, 'realProductCount': 0, 'nearBottom': False}

                    footer_found = end_of_page_info.get('footerFound')
                    skeleton_count = end_of_page_info.get('skeletonCount', 0)

                    if footer_found:
                        logger.info(f"Footer detected ('{footer_found}'), reached end of page at API={api_total} DOM={dom_total}")
                        break

                    # Log skeleton status periodically
                    if scroll_attempt % 5 == 0:
                        logger.debug(f"Status: API={api_total} DOM={dom_total}, {skeleton_count} skeletons visible, near bottom: {end_of_page_info.get('nearBottom')}")

                    # Stop if no new products after consecutive scrolls
                    # Note: ICA uses virtualization so old products become skeletons as you scroll
                    # We can't rely on skeleton count = 0, instead check:
                    # - If near bottom AND no new products for 10 scrolls -> definitely done
                    # - If not near bottom AND no new products for 5 scrolls AND no skeletons -> done
                    near_bottom = end_of_page_info.get('nearBottom', False)

                    if no_new_products_count >= 10 and near_bottom:
                        logger.info(f"Near bottom with no new API products after 10 scrolls, stopping at API={api_total} DOM={dom_total}")
                        break
                    elif no_new_products_count >= 5:
                        if skeleton_count > 0 and not near_bottom:
                            logger.debug(f"Would stop but {skeleton_count} skeletons still loading, continuing...")
                            no_new_products_count = 0  # Reset and keep trying
                        elif skeleton_count > 0 and near_bottom:
                            logger.debug(f"Near bottom with {skeleton_count} skeletons (virtualization), waiting...")
                            # Don't reset counter when near bottom - these are virtualized, not new
                        else:
                            logger.info(f"No new API products after 5 scrolls, stopping at API={api_total} DOM={dom_total}")
                            break

                    # Periodically remove off-screen skeleton nodes to reduce memory usage
                    # ICA's virtualization creates hundreds of skeleton placeholders that bloat the DOM
                    if scroll_attempt > 0 and scroll_attempt % 10 == 0:
                        try:
                            removed = await asyncio.wait_for(page.evaluate("""
                                () => {
                                    const cards = document.querySelectorAll('.product-card-container');
                                    let removed = 0;
                                    for (const card of cards) {
                                        const rect = card.getBoundingClientRect();
                                        // Remove cards far above viewport that are skeletons
                                        if (rect.bottom < -1000 &&
                                            (card.innerHTML.includes('_skeleton_') || card.querySelector('[class*="skeleton"]'))) {
                                            card.remove();
                                            removed++;
                                        }
                                    }
                                    return removed;
                                }
                            """), timeout=evaluate_timeout)
                            if removed > 0:
                                logger.debug(f"Cleaned {removed} off-screen skeleton nodes to reduce memory")
                        except Exception:
                            pass  # Non-critical, continue scrolling

                    # Scroll down
                    try:
                        await asyncio.wait_for(
                            page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)"),
                            timeout=evaluate_timeout
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Scroll {scroll_attempt + 1}: scroll command timed out, continuing")
                    except Exception as e:
                        logger.warning(f"Scroll {scroll_attempt + 1}: scroll command failed ({e}), continuing")
                    await asyncio.sleep(scroll_pause)

                if scroll_attempt >= max_scroll_attempts - 1:
                    logger.warning(f"Hit max scroll attempts ({max_scroll_attempts}), may not have captured all products")

                api_products_map = getattr(self, '_api_product_map', {})
                api_brands = getattr(self, '_api_brand_map', {})
                logger.info(
                    f"Finished scrolling: API captured {len(api_products_map)} products, "
                    f"{len(api_brands)} brands; DOM saw {len(all_extracted_products)} unique card names"
                )

                await context.close()
                await browser.close()

                # Build offer list from API-captured product data.
                # DOM extraction is kept during the scroll as a stop-signal aid, but its
                # names are unreliable after React hydration. The JSON the ICA frontend
                # renders from is captured here and used as the authoritative source.
                #
                # ICA pricing model:
                #   regular_price       = price.amount (ordinarie styckpris from API)
                #   offer_description   = promotions[0].description as Swedish text
                #                         ("2 för 28 kr", "25 kr/kg", "49,90 kr/st")
                # _parse_offer_description turns the text into an effective per-unit
                # price plus a unit hint; kg offers are converted to total per-item.
                import re as _re_mb
                products = []
                logger.info(f"Processing {len(api_products_map)} products from API capture")

                for p in api_products_map.values():
                    name = (p.get('name') or '').strip()
                    if not name or re.match(r"^(Ordinarie Pris|Jämförpris|Erbjudande)\b", name, re.IGNORECASE):
                        continue

                    original_price = float(p.get('regular_price') or 0)
                    offer_desc = p.get('offer_description') or ''
                    if original_price <= 0 or not offer_desc:
                        # Without regular price or promo text we can't derive savings
                        continue

                    # Parse the promo text into an effective per-unit offer price + unit.
                    # Fallback when parsing fails = original_price (savings will be 0 → skipped).
                    offer_price, _parsed_orig, unit, _orig_per_unit = self._parse_offer_description(
                        offer_desc, original_price
                    )

                    # For per-kg offers, multiply by item weight to get total item price.
                    # Weight is available in packSizeDescription ("0.23kg") or in the name.
                    if unit == 'kg':
                        weight_kg = 0.0
                        pack_size = p.get('pack_size') or ''
                        if pack_size:
                            m_kg = _re_mb.search(r'(\d+(?:[,.]\d+)?)\s*kg', pack_size, _re_mb.IGNORECASE)
                            if m_kg:
                                try:
                                    weight_kg = float(m_kg.group(1).replace(',', '.'))
                                except ValueError:
                                    weight_kg = 0.0
                        if weight_kg <= 0:
                            weight_kg = self._extract_weight_from_name(name)
                        if weight_kg > 0:
                            offer_price = round(offer_price * weight_kg, 2)
                            unit = 'st'

                    savings = max(0, original_price - offer_price)
                    if savings <= 0:
                        logger.debug(f"Skipping non-deal product: {name} (offer={offer_price}, orig={original_price}, desc='{offer_desc}')")
                        continue

                    brand = p.get('brand') or self._api_brand_map.get(name.lower(), '')
                    if brand and isinstance(brand, str):
                        brand = brand.strip().upper()

                    cat_path = p.get('category_path') or ''
                    category = self._map_ica_category(cat_path) if cat_path else shared_guess_category(name)

                    # Multi-buy detection from offer description ("2 för 45 kr")
                    is_multi_buy = False
                    multi_buy_qty = None
                    multi_buy_price = None
                    mb = _re_mb.search(r'(\d+)\s*för\s*(\d+(?:[,.]\d+)?)\s*kr', offer_desc, _re_mb.IGNORECASE)
                    if mb:
                        is_multi_buy = True
                        multi_buy_qty = int(mb.group(1))
                        multi_buy_price = float(mb.group(2).replace(',', '.'))

                    product_id = p.get('product_id') or ''
                    retailer_id = p.get('retailer_id') or ''
                    product_page_id = retailer_id or product_id
                    product_url = (
                        f"https://handlaprivatkund.ica.se/stores/{actual_store_id}/products/{product_page_id}"
                        if product_page_id else None
                    )

                    products.append({
                        'name': name,
                        'price': offer_price,
                        'original_price': original_price,
                        'savings': savings,
                        'unit': unit,
                        'category': category,
                        'image_url': p.get('image_url'),
                        'product_url': product_url,
                        'offer_description': offer_desc,
                        'brand': brand if brand else None,
                        'is_multi_buy': is_multi_buy,
                        'multi_buy_quantity': multi_buy_qty,
                        'multi_buy_price': multi_buy_price,
                        'weight_grams': parse_weight(name),
                        'scraped_at': datetime.now(timezone.utc)
                    })

                logger.info(f"Processed {len(products)} deal products from API, sample prices: {[p['price'] for p in products[:5]]}")
                return products

        except Exception as e:
            # Graceful cleanup on exception (async with async_playwright handles ultimate cleanup)
            try:
                await context.close()
                await browser.close()
            except Exception:
                pass
            logger.error(f"Error scraping ICA e-handel: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return []


    # Keywords for reclassifying 'other' category products to household/hygiene
    _HOUSEHOLD_KEYWORDS = [
        # Clothing (ICA mywear brand, ~100 products)
        'mywear', 'resteröds', 'strumpa', 'socka', 'hiddensocka', 'raggsocka',
        'thermosocka', 'knästrumpa', 'herrboxer', 'pyjamas', 'pyjamasbyxa',
        'pyjamastopp', 'babypyjamas', 'klänning', 'handske', 'skinnhandske',
        'hidden 3p', 'big tee', 'mid cut',
        # Laundry/cleaning
        'tvättmedel', 'sköljmedel',
        # Books/stationery
        'ljudbok', 'klistermärken', 'aktivitetsbok', 'anteckningsbok', 'anteckingsbok',
        'spiralblock', 'pysselbok', 'pennfodral', 'fiberpennor', 'tuschpenna',
        'suddgummi', 'gummibandsmapp', 'godnattsagor', 'lärabok', 'målarbok',
        'tygbok', 'måla mini', 'måla med', 'mandala', 'busy book',
        'lär dig', 'skriv och',
        # Children's books (common patterns)
        'pokémon', 'pokemon', 'minecraft', 'tittut',
        'alfons', 'fantus', 'musse & helium', 'skalmans',
        'valparna', 'sommarskuggan', 'proffsens',
        'fotbollstrick', 'pannkakstårtan',
        'bli bra på', 'matte!',
        # Toys/children
        'babblarna', 'squishmallows', 'paw patrol', 'charader', 'disney',
        'star trading', 'fira tillbehör',
        # Household items
        'blockljus', 'vattenflaska', 'grilltändare', 'tändkuber', 'flyttlåda',
        'popcornmaskin', 'galge', 'hörlur', 'resekudde', 'lunchlåda',
        'servettbox', 'muffinsform', 'sminkspegel',
        'scrub daddy', 'scrub mommy', 'städsvamp',
        'fläckborttagning', 'fläckborttaging', 'förbehandlare',
        'hushållsduk', 'wc bref', 'wc-block',
        'tvättmedel', 'sköljmedel',
        # Kitchenware/appliances
        'gjutjärnsgryta', 'kastrull', 'gryta rostfri', 'airfryer',
        'förvaringsform', 'cook & freeze',
        # Glue/tools
        'loctite', 'super glue', 'lim repair',
        # Trash bags
        'sopsäck', 'sopsäckar',
        # Garden
        'växtnäring',
        # Pet products
        'dentastix', 'pedigree', 'dreamies',
        'hundbajspåse',
        # Decorations/gift
        'presentpåse', 'prydnadskanin', 'kanin med morot',
        # Flowers
        'rosor', 'bukett',
        # Misc non-food
        'i love you',  # Valentine's gift product
    ]

    _HYGIENE_KEYWORDS = [
        'handtvål', 'barntandborste', 'tandborstrefill',
        'tandborste',  # Jordan toothbrushes
        'bomullspinnar', 'bomullsrondeller', 'make up pad',
        'tampong', 'binda ultra', 'våtservetter',
        'toalettrengöring',
        # Diapers
        'blöjor', 'byxblöjor',
        # Cosmetics/hair
        'foundation', 'mascara', 'concealer',
        'hårspray', 'stylingkräm', 'stylingspray', 'stylinggel',
    ]

    # Weight/volume pattern: digits followed by unit (500g, 1.5kg, 330ml, etc.)
    _WEIGHT_VOLUME_RE = re.compile(
        r'\d+\s*(?:g|gram|kg|kilo|ml|milliliter|cl|centiliter|dl|deciliter|l|liter|st|styck|stk|pack|p)\b', re.IGNORECASE
    )

    # Food indicator words — if ANY of these appear, keep as 'other' (likely food).
    # Only checked for products WITHOUT weight/volume, so compound words like
    # "blåmögelost" (which have weight) are already handled by _WEIGHT_VOLUME_RE.
    # Uses word boundaries to avoid false positives ("ost" in "Rostskogen").
    _FOOD_INDICATOR_RE = re.compile(
        r'\b(?:'
        r'ost|lax|ris|öl|vin|sås|fil|mjöl'
        r'|korv|skinka|fläsk|kött|kyckling|torsk|sill|räkor|färs|bacon|salami|ribs|biff'
        r'|mjölk|grädde|smör|yoghurt|kvarg'
        r'|bröd|bulle|kaka|kakor|chips|choklad|godis'
        r'|glass|sylt|müsli|flingor|havregryn|gryn'
        r'|juice|saft|vatten|dricka|läsk'
        r'|pasta|potatis|tomat|gurka|paprika'
        r'|äpple|banan|citron|frukt|grönsak|svamp'
        r'|soppa|senap|ketchup|majonnäs|pesto'
        r'|krydda|salt|socker|olja|vinäger'
        r'|fryst|frys|konserv|burk|paket'
        r'|kcal|protein|ekologisk|laktosfri'
        r'|semper|arla|scan|findus|felix'
        r'|barilla|kavli|göteborgs|axfood'
        r')\b', re.IGNORECASE
    )

    def _reclassify_non_food(self, name: str) -> str | None:
        """
        Check if a product in 'other' category should be household/hygiene.

        Returns 'household', 'hygiene', or None (keep as 'other').
        """
        name_lower = name.lower()

        for kw in self._HYGIENE_KEYWORDS:
            if kw in name_lower:
                return 'hygiene'

        for kw in self._HOUSEHOLD_KEYWORDS:
            if kw in name_lower:
                return 'household'

        # Books/non-food heuristic: products in 'other' without weight/volume
        # units and without food indicator words are likely books, household
        # items, or cosmetics. Reclassify to 'household' to prevent recipe matching.
        if not self._WEIGHT_VOLUME_RE.search(name):
            if not self._FOOD_INDICATOR_RE.search(name_lower):
                return 'household'

        return None

    async def _find_url_slug_by_id(self, store_id: str) -> Optional[str]:
        """
        Find url_slug for a store by its ID.

        Uses Playwright to find the store's offer page URL.
        """
        logger.debug(f"Looking up url_slug for store ID: {store_id}")

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                # Load store search page
                await page.goto(f"{self.base_url}/butiker/", timeout=60000)
                await page.wait_for_load_state("networkidle", timeout=PAGE_NETWORK_IDLE_TIMEOUT)

                # Find all store links and look for matching ID
                store_links = await page.query_selector_all('a[href*="/butiker/"]')

                for link in store_links:
                    href = await link.get_attribute("href")
                    if href and f"-{store_id}/" in href:
                        # Found it! Extract the slug
                        match = re.search(r"/butiker/[^/]+/[^/]+/([^/]+-\d+)/?$", href)
                        if match:
                            url_slug = match.group(1)
                            logger.debug(f"Found url_slug: {url_slug}")
                            await browser.close()
                            return url_slug

                await browser.close()

            logger.warning(f"Store ID {store_id} not found")
            return None

        except Exception as e:
            logger.error(f"Error finding url_slug for store ID {store_id}: {e}")
            return None

    async def _scrape_store_offers_playwright(self, store_url: str) -> List[Dict]:
        """
        Scrape store offers using Playwright.

        Extracts data from window.__INITIAL_DATA__.offers.weeklyOffers
        """
        products = []

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox"]
                )
                page = await browser.new_page()

                logger.info(f"Navigating to {store_url}")
                await page.goto(store_url, timeout=60000)
                await page.wait_for_load_state("networkidle", timeout=PAGE_NETWORK_IDLE_TIMEOUT)
                await asyncio.sleep(2)

                # Extract __INITIAL_DATA__
                initial_data = await page.evaluate("""
                    () => {
                        if (window.__INITIAL_DATA__) {
                            return JSON.stringify(window.__INITIAL_DATA__);
                        }
                        return null;
                    }
                """)

                await browser.close()

                if not initial_data:
                    logger.error("Could not find __INITIAL_DATA__ on page")
                    return []

                data = json.loads(initial_data)
                offers = data.get("offers", {}).get("weeklyOffers", [])

                logger.info(f"Found {len(offers)} offers in __INITIAL_DATA__")

                for offer in offers:
                    try:
                        product = self._parse_ica_offer(offer, store_url=store_url)
                        if product:
                            products.append(product)
                    except Exception as e:
                        logger.debug(f"Error parsing offer: {e}")
                        continue

            return products

        except Exception as e:
            logger.error(f"Error in Playwright scraping: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return []

    def _parse_ica_offer(self, offer: Dict, store_url: str = None) -> Optional[Dict]:
        """
        Parse a single ICA offer from __INITIAL_DATA__ JSON.

        ICA offer structure:
        - details.name: Product name
        - details.brand: Brand/origin
        - details.packageInformation: Package size
        - details.mechanicInfo: Price description
        - parsedMechanics: Structured price info
        - stores[0].regularPrice: Original price
        - eans[0].image: Image URL
        - category.articleGroupName: Category
        """
        try:
            details = offer.get("details", {})
            name = details.get("name", "").strip()
            if not name:
                return None

            # Build full product name
            brand = details.get("brand", "").strip()
            package_info = details.get("packageInformation", "").strip()

            full_name = name
            if brand and brand.lower() not in name.lower():
                full_name = f"{name} {brand}"
            if package_info:
                full_name = f"{full_name} {package_info}"

            # Parse price from parsedMechanics
            mechanics = offer.get("parsedMechanics", {})
            price = 0.0
            is_multi_buy = False
            multi_buy_qty = None
            multi_buy_total = None

            quantity = mechanics.get("quantity", 0)
            value2 = mechanics.get("value2", "")
            value4 = mechanics.get("value4", "")

            if value2:
                try:
                    price_val = float(value2.replace(",", ".").replace(":", "."))
                    if quantity and quantity > 1:
                        # Multi-buy offer: "2 for 139 kr"
                        is_multi_buy = True
                        multi_buy_qty = quantity
                        multi_buy_total = price_val
                        price = price_val / quantity
                    else:
                        price = price_val
                except ValueError:
                    pass

            # Original price from stores
            original_price = price
            stores = offer.get("stores", [])
            if stores:
                reg_price_str = stores[0].get("regularPrice", "")
                if reg_price_str:
                    try:
                        original_price = float(reg_price_str.replace(",", ".").replace(":", "."))
                    except ValueError:
                        pass

            # For multi-buy, calculate per-unit original price
            if is_multi_buy and original_price > 0:
                # regularPrice is per-item, so total original = regularPrice * quantity
                original_total = original_price * multi_buy_qty
                savings = original_total - multi_buy_total if multi_buy_total else 0
            else:
                savings = max(0, original_price - price)

            # Unit
            unit = "st"
            if value4:
                if "/kg" in value4:
                    unit = "kg"
                elif "/l" in value4:
                    unit = "l"

            # For per-kg products with variable weight, calculate actual total price
            if unit == "kg":
                weight_kg = self._extract_weight_from_name(full_name)
                if weight_kg > 0:
                    price = round(price * weight_kg, 2)
                    original_price = round(original_price * weight_kg, 2)
                    savings = max(0, original_price - price)
                    unit = "st"
                    logger.debug(f"Butik variable weight: {full_name} - {weight_kg}kg, offer: {price}, orig: {original_price}")

            # Image URL
            image_url = None
            eans = offer.get("eans", [])
            if eans:
                image_url = eans[0].get("image")

            # Category mapping
            category_name = offer.get("category", {}).get("articleGroupName", "")
            category = self._map_ica_category(category_name)

            # Product URL - link to store page with query params to open offer modal
            # ICA's JS reads ?action=details&id={offerId} to auto-open the popup
            offer_id = offer.get("id", "")
            if store_url and offer_id:
                product_url = f"{store_url}?action=details&id={offer_id}"
            elif store_url:
                product_url = store_url
            else:
                product_url = None

            # Weight from packageInformation (e.g., "500g", "1l", "ca 1,4kg")
            weight_grams = parse_weight(package_info) if package_info else parse_weight(full_name)

            return {
                "name": full_name,
                "price": round(price, 2),
                "original_price": round(original_price, 2),
                "savings": round(savings, 2),
                "unit": unit,
                "category": category,
                "brand": self._clean_brand(brand).upper() if brand else None,
                "image_url": image_url,
                "product_url": product_url,
                "is_multi_buy": is_multi_buy,
                "multi_buy_quantity": multi_buy_qty,
                "multi_buy_total_price": round(multi_buy_total, 2) if multi_buy_total else None,
                "weight_grams": weight_grams,
                "scraped_at": datetime.now(timezone.utc)
            }

        except Exception as e:
            logger.debug(f"Error parsing ICA offer: {e}")
            return None

    @staticmethod
    def _clean_brand(brand: str) -> str:
        """
        Clean brand string from ICA data.

        ICA often appends origin info to brand, e.g.:
        - "ICA. Brasilien/Peru" -> "ICA"
        - "Kronfågel. Ursprung Sverige" -> "Kronfågel"
        - "Coca-Cola, Fanta, Sprite" -> "Coca-Cola, Fanta, Sprite" (keep as-is)
        """
        if not brand:
            return brand

        # Strip origin info after ". " (dot + space)
        # Pattern: "Brand. Country" or "Brand. Ursprung Country"
        dot_idx = brand.find('. ')
        if dot_idx > 0:
            after_dot = brand[dot_idx + 2:].lower()
            # Known origin patterns
            origin_words = [
                'ursprung', 'sverige', 'brasilien', 'italien', 'spanien',
                'polen', 'nederländerna', 'belgien', 'sydafrika', 'peru',
                'tyskland', 'danmark', 'norge', 'frankrike', 'grekland',
                'holland', 'irland', 'portugal', 'usa', 'thailand',
                'kina', 'indien', 'vietnam', 'indonesien', 'marocko',
                'chile', 'argentina', 'ecuador', 'costa rica', 'kenya',
            ]
            if any(after_dot.startswith(w) for w in origin_words):
                brand = brand[:dot_idx]

        return brand.strip()

    def _extract_brands_from_api(self, data, depth=0):
        """
        Recursively extract brand info from ICA ehandel API responses.

        Builds a mapping of product name (lowercase) -> brand string
        so DOM-scraped products can be enriched with brand data.
        """
        if depth > 5:
            return

        if isinstance(data, dict):
            # Check if this dict looks like a product with brand info
            name = data.get("name") or data.get("productName") or data.get("title") or ""
            brand = data.get("brand") or data.get("manufacturer") or data.get("brandName") or ""

            if name and brand and isinstance(name, str) and isinstance(brand, str):
                name_clean = name.strip().lower()
                brand_clean = brand.strip()
                if name_clean and brand_clean:
                    self._api_brand_map[name_clean] = brand_clean

            # Recurse into nested structures
            for value in data.values():
                if isinstance(value, (dict, list)):
                    self._extract_brands_from_api(value, depth + 1)

        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    self._extract_brands_from_api(item, depth + 1)

    def _extract_products_from_api(self, data, depth=0):
        """
        Recursively pull ICA deal products out of API responses.

        We intentionally funnel every candidate through _ingest_ica_product_candidate()
        so the acceptance rules stay in one place. That lets us reject junk nodes
        such as price labels ("Ordinarie Pris 35,00 kr") while still merging
        progressively richer product payloads across SSR and API responses.
        """
        if depth > 8:
            return

        if isinstance(data, dict):
            self._ingest_ica_product_candidate(data)

            for value in data.values():
                if isinstance(value, (dict, list)):
                    self._extract_products_from_api(value, depth + 1)

        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    self._extract_products_from_api(item, depth + 1)

    def _map_ica_category(self, ica_category: str) -> str:
        """
        Map ICA category names to our standard categories.

        Falls back to shared category utility for unmatched categories.
        """
        category_lower = ica_category.lower()

        # ICA-specific mappings (their category strings)
        mapping = {
            "meat": ["kott", "kött"],
            "poultry": ["fagel", "fågel", "kyckling"],
            "fish": ["fisk", "skaldjur"],
            "dairy": ["mejeri", "ost", "mjolk", "mjölk"],
            "deli": ["chark", "palagg", "pålägg"],
            "fruit": ["frukt", "bar", "bär"],
            "vegetables": ["gront", "grönt", "grönsak", "rotfrukt"],
            "bread": ["brod", "bröd", "bageri"],
            "beverages": ["dryck", "lask", "läsk", "juice"],
            "frozen": ["frys", "djupfryst", "glass"],
            "candy": ["godis", "snacks", "choklad"],
            "hygiene": ["hygien", "skönhet"],
            "household": ["hushall", "hushåll", "städ"],
        }

        # Check for "Färskvaror" which can be meat, fish, or deli
        if "farsk" in category_lower or "färsk" in category_lower:
            return "deli"  # Default for fresh goods

        for our_cat, keywords in mapping.items():
            if any(kw in category_lower for kw in keywords):
                return our_cat

        # Fallback to shared utility for better coverage
        return shared_normalize_category(ica_category)

    def _map_ica_categories_to_standard(self, categories: List[str]) -> str:
        """
        Map ICA category array to our standard category.

        ICA uses hierarchical categories like:
        ["Kött, Chark & Fågel", "Köttfärs", "Nötfärs"]
        ["Mejeri & Ost", "Ost", "Matlagningsost"]

        We use the first (top-level) category for mapping.
        """
        if not categories:
            return "other"

        # Join all categories for better matching
        combined = " ".join(categories).lower()

        # Priority-based mapping (check most specific first)
        if any(kw in combined for kw in ["kyckling", "fågel", "kalkon"]):
            return "poultry"
        if any(kw in combined for kw in ["fisk", "skaldjur", "lax", "torsk", "räk"]):
            return "fish"
        if any(kw in combined for kw in ["kött", "färs", "biff", "fläsk", "lamm", "nöt"]):
            return "meat"
        if any(kw in combined for kw in ["chark", "korv", "bacon", "skinka", "pålägg"]):
            return "deli"
        if any(kw in combined for kw in ["mejeri", "mjölk", "ost", "yoghurt", "grädde", "smör", "ägg"]):
            return "dairy"
        if any(kw in combined for kw in ["frukt", "bär"]):
            return "fruit"
        if any(kw in combined for kw in ["grönt", "grönsak", "sallad", "tomat", "potatis"]):
            return "vegetables"
        if any(kw in combined for kw in ["bröd", "bageri", "kaka"]):
            return "bread"
        # Pantry/skafferi BEFORE beverages — "Skafferi" contains staples, not drinks
        if any(kw in combined for kw in ["skafferi", "konserv", "pasta", "ris", "olja", "sås",
                                          "bakning", "socker", "mjöl", "gryn", "müsli",
                                          "bönor", "linser", "honung", "sylt", "marmelad"]):
            return "pantry"
        if any(kw in combined for kw in ["dryck", "läsk", "juice", "vatten", "kaffe", "te"]):
            return "beverages"
        if any(kw in combined for kw in ["fryst", "glass"]):
            return "frozen"
        if any(kw in combined for kw in ["godis", "snacks", "chips", "choklad"]):
            return "candy"
        if any(kw in combined for kw in ["hygien", "skönhet", "tvål", "schampo"]):
            return "hygiene"
        if any(kw in combined for kw in ["hushåll", "städ", "tvätt", "papper"]):
            return "household"
        if any(kw in combined for kw in ["barn", "blöj", "bebis"]):
            return "other"  # Baby items - filter these out later if needed

        return "other"

    def _extract_weight_from_name(self, name: str) -> float:
        """
        Extract weight in kg from product name for variable weight products.

        Handles formats like:
        - "ca 1,4kg" -> 1.4
        - "ca 750g" -> 0.75
        - "ca 1.5 kg" -> 1.5
        - "ca 500 g" -> 0.5

        Returns:
            Weight in kg, or 0.0 if no weight found
        """
        if not name:
            return 0.0

        name_lower = name.lower()

        # Pattern for kg: "ca 1,4kg", "ca 1.5 kg", "ca 1 kg"
        kg_match = re.search(r'ca\s+(\d+(?:[,\.]\d+)?)\s*kg', name_lower)
        if kg_match:
            return float(kg_match.group(1).replace(',', '.'))

        # Pattern for grams with "ca": "ca 750g", "ca 500 g"
        g_match = re.search(r'ca\s+(\d+)\s*g(?!\w)', name_lower)
        if g_match:
            return float(g_match.group(1)) / 1000.0

        # Pattern for exact grams: "42g", "330g", "1440g" (without "ca" prefix)
        # Handles spice products like "Sriracha 42g Santa Maria"
        g_exact_match = re.search(r'(?<!\d)(\d+)\s*g(?:\b|$)', name_lower)
        if g_exact_match:
            return float(g_exact_match.group(1)) / 1000.0

        return 0.0

    def _parse_offer_description(self, offer_desc: str, fallback_price: float) -> tuple:
        """
        Parse ICA offer description to extract offer price and original price.

        Formats handled for offer price:
        - "4 för 50 kr" -> 50/4 = 12.50 kr/st
        - "2 för 69 kr" -> 69/2 = 34.50 kr/st
        - "25 kr/st" -> 25 kr/st (fixed price)
        - "119 kr/kg" -> 119 kr/kg (per kilo)
        - "89,90 kr" -> 89.90 kr/st (single price)

        Formats handled for original price:
        - "Ord.pris 37,95 kr"
        - "Ord.pris 15,95 kr/st"
        - "Ord.pris 158,00 kr/kg"

        Args:
            offer_desc: Offer description string
            fallback_price: Price from DOM as fallback

        Returns:
            Tuple of (offer_price, original_price, unit, original_is_per_unit)
            where original_is_per_unit indicates if original price has /kg, /st etc suffix
        """
        if not offer_desc:
            return fallback_price, fallback_price, 'st', False

        offer_desc_lower = offer_desc.lower().strip()
        offer_price = None
        original_price = None
        unit = 'st'
        original_is_per_unit = False  # Track if original price has /kg suffix

        # Extract original price from "Ord.pris X kr" pattern
        ord_match = re.search(r'ord\.?\s*pris\s*(\d+(?:[,\.]\d+)?)\s*kr(?:/(st|kg|l|förp))?', offer_desc_lower)
        if ord_match:
            original_price = float(ord_match.group(1).replace(',', '.'))
            if ord_match.group(2):
                unit = ord_match.group(2)
                original_is_per_unit = True  # Original price has unit suffix

        # Pattern 1: "X för Y kr" (multi-buy)
        match = re.search(r'(\d+)\s*för\s*(\d+(?:[,\.]\d+)?)\s*kr', offer_desc_lower)
        if match:
            qty = int(match.group(1))
            total = float(match.group(2).replace(',', '.'))
            if qty > 0:
                offer_price = total / qty
                unit = 'st'

        # Pattern 1b: "Köp 3 betala för 2"
        if offer_price is None:
            match = re.search(r'köp\s*(\d+)\s*betala\s*för\s*(\d+)', offer_desc_lower)
            if match:
                buy_qty = int(match.group(1))
                pay_qty = int(match.group(2))
                if buy_qty > 0 and 0 < pay_qty < buy_qty:
                    offer_price = round(fallback_price * (pay_qty / buy_qty), 2)
                    unit = 'st'

        # Pattern 1c: "25 % rabatt"
        if offer_price is None:
            match = re.search(r'(\d+(?:[,\.]\d+)?)\s*%\s*rabatt', offer_desc_lower)
            if match:
                percent_discount = float(match.group(1).replace(',', '.'))
                if 0 < percent_discount < 100:
                    offer_price = round(fallback_price * (1 - (percent_discount / 100.0)), 2)
                    unit = 'st'

        # Pattern 2: "X kr/st" or "X kr/kg" (per-unit price) - but not "Ord.pris"
        if offer_price is None:
            # Find all prices with units and take the first one that's not the original price
            for match in re.finditer(r'(\d+(?:[,\.]\d+)?)\s*kr/(st|kg|l|förp)', offer_desc_lower):
                price = float(match.group(1).replace(',', '.'))
                # Skip if this matches the original price we already found
                if original_price and abs(price - original_price) < 0.01:
                    continue
                offer_price = price
                unit = match.group(2)
                break

        # Pattern 3: First price in text (headline price like "89,90 kr")
        if offer_price is None:
            # Look for the first price that appears (usually the offer price)
            match = re.search(r'pris\s*(\d+(?:[,\.]\d+)?)\s*kr', offer_desc_lower)
            if match:
                offer_price = float(match.group(1).replace(',', '.'))

        # Fallback to DOM price
        if offer_price is None:
            offer_price = fallback_price

        # If no original price found, try to find it from standalone prices
        # ICA e-handel format: "Ca 69,95 kr 109,50 kr" where:
        # - Lower price = offer total (69,95 kr)
        # - Higher price = original total (109,50 kr)
        if original_price is None:
            # Find all standalone prices (X kr or X,YY kr, but NOT X kr/kg)
            # Pattern: number followed by "kr" but NOT followed by /kg, /st, etc.
            standalone_prices = []
            for match in re.finditer(r'(\d+(?:[,\.]\d+)?)\s*kr(?!\s*/)', offer_desc_lower):
                price = float(match.group(1).replace(',', '.'))
                standalone_prices.append(price)

            # If we found multiple standalone prices, the higher one is likely original
            if len(standalone_prices) >= 2:
                # Sort unique prices - highest is original, second highest is offer total
                unique_prices = sorted(set(standalone_prices), reverse=True)
                if len(unique_prices) >= 2:
                    original_price = unique_prices[0]  # Highest = original
                    original_is_per_unit = False  # This is already total price, NOT per-kg
                    logger.debug(f"Found standalone prices: {unique_prices}, using {original_price} as original")

        # Still no original price? Use fallback
        if original_price is None:
            original_price = fallback_price

        # Sanity check: original_price >= offer_price
        # BUT: Skip this check if we have a per-kg offer price and a standalone total original price
        # (they're in different units and can't be compared directly)
        if original_price < offer_price:
            # Only overwrite if both are in the same unit
            # If unit is 'kg' but original_is_per_unit is False, original is total and offer is per-kg
            if not (unit == 'kg' and not original_is_per_unit):
                original_price = offer_price

        return offer_price, original_price, unit, original_is_per_unit
