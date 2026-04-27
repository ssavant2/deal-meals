"""
Base class for all stores.

Each store inherits from this and defines its config + scraper.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, List, Any, Callable, Awaitable, Union
from dataclasses import dataclass, field
from datetime import datetime, timezone
import copy
import re
import time

try:
    from languages.market_runtime import (
        get_default_unit,
        get_food_filter_profile,
        get_unit_aliases,
    )
except ModuleNotFoundError:
    from app.languages.market_runtime import (
        get_default_unit,
        get_food_filter_profile,
        get_unit_aliases,
    )


_FOOD_FILTER_PROFILE = get_food_filter_profile()


@dataclass
class StoreConfigField:
    """
    Describes a configuration field for UI generation.

    Plugins define their config fields via get_config_fields().
    Frontend renders appropriate UI controls based on field_type.
    """
    key: str                    # "location_type" - used as JSON key
    label: str                  # Displayed to user
    field_type: str             # "radio", "text", "select", "search", "async_select"
    options: List[Dict] = None  # [{"value": "ehandel", "label": "E-handel", "description": "..."}]
    default: Any = None         # Default value
    required: bool = False      # Is this field required?
    depends_on: Dict = None     # {"field": "location_type", "value": "butik"} - show only when condition met
    placeholder: str = ""       # Placeholder text for inputs
    invalidate_on_postal_change: bool = False
    # If True, saved selection is cleared when user's postal code changes.
    # Used when available options depend on location (e.g., ICA e-handel
    # where different physical stores serve different postal codes).
    # Not needed for stores with centralized fulfillment (Willys, Mathem).

    def to_dict(self) -> Dict:
        """Convert to dict for JSON serialization."""
        return {
            "key": self.key,
            "label": self.label,
            "field_type": self.field_type,
            "options": self.options,
            "default": self.default,
            "required": self.required,
            "depends_on": self.depends_on,
            "placeholder": self.placeholder,
            "invalidate_on_postal_change": self.invalidate_on_postal_change
        }


@dataclass
class StoreConfig:
    """
    Configuration for a store.
    
    Contains all metadata needed to display and manage the store.
    """
    id: str              # "willys", "ica", "coop", "mathem"
    name: str            # "Willys", "ICA", "Coop", "Mathem"
    logo: str            # "/stores/willys/logo.svg"
    color: str           # "#e30613" (brand color for buttons, etc)
    url: str             # "https://www.willys.se"
    enabled: bool = True # Enabled/disabled
    has_credentials: bool = False  # Requires login?
    description: str = ""  # Short description
    
    def __post_init__(self):
        """Validation after creation."""
        if not self.id or not self.name:
            raise ValueError(f"Store must have id and name: {self.id}, {self.name}")


@dataclass
class StoreScrapeResult:
    """
    Standard result returned by store plugins.

    Status values:
    - success: products were fetched and should replace current offers
    - success_empty: the plugin verified a real empty-offer state
    - failed: scraping did not produce trustworthy data
    - blocked: the store/page blocked access or required unavailable interaction
    - partial: some data was fetched, but the result is incomplete
    """
    status: str
    products: List[Dict] = field(default_factory=list)
    reason: Optional[str] = None
    message_key: Optional[str] = None
    message_params: Dict[str, Any] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    replace_offers: Optional[bool] = None

    @property
    def should_replace_offers(self) -> bool:
        if self.replace_offers is not None:
            return self.replace_offers
        return self.status in {"success", "success_empty"}

    @property
    def is_empty_success(self) -> bool:
        return self.status == "success_empty"

    @classmethod
    def success(
        cls,
        products: List[Dict],
        *,
        reason: Optional[str] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> "StoreScrapeResult":
        return cls(
            status="success",
            products=products or [],
            reason=reason,
            diagnostics=diagnostics or {},
            replace_offers=True,
        )

    @classmethod
    def success_empty(
        cls,
        *,
        reason: Optional[str] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> "StoreScrapeResult":
        return cls(
            status="success_empty",
            products=[],
            reason=reason or "verified_empty",
            diagnostics=diagnostics or {},
            replace_offers=True,
        )

    @classmethod
    def failed(
        cls,
        *,
        reason: Optional[str] = None,
        message_key: Optional[str] = None,
        message_params: Optional[Dict[str, Any]] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> "StoreScrapeResult":
        return cls(
            status="failed",
            reason=reason,
            message_key=message_key,
            message_params=message_params or {},
            diagnostics=diagnostics or {},
            replace_offers=False,
        )

    @classmethod
    def blocked(
        cls,
        *,
        reason: Optional[str] = None,
        message_key: Optional[str] = None,
        message_params: Optional[Dict[str, Any]] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> "StoreScrapeResult":
        return cls(
            status="blocked",
            reason=reason,
            message_key=message_key,
            message_params=message_params or {},
            diagnostics=diagnostics or {},
            replace_offers=False,
        )

    @classmethod
    def partial(
        cls,
        products: List[Dict],
        *,
        reason: Optional[str] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
        replace_offers: bool = False,
    ) -> "StoreScrapeResult":
        return cls(
            status="partial",
            products=products or [],
            reason=reason,
            diagnostics=diagnostics or {},
            replace_offers=replace_offers,
        )


def normalize_store_scrape_result(
    raw_result: Union[StoreScrapeResult, List[Dict], Dict, None],
    *,
    store_name: Optional[str] = None,
) -> StoreScrapeResult:
    """Normalize legacy plugin returns into StoreScrapeResult."""
    if isinstance(raw_result, StoreScrapeResult):
        return raw_result

    diagnostics = {"store": store_name} if store_name else {}

    if isinstance(raw_result, list):
        if raw_result:
            return StoreScrapeResult.success(
                raw_result,
                reason="legacy_list_result",
                diagnostics=diagnostics,
            )
        return StoreScrapeResult.failed(
            reason="legacy_empty_result",
            diagnostics=diagnostics,
        )

    if isinstance(raw_result, dict):
        products = raw_result.get("products") or []
        status = raw_result.get("status") or ("success" if products else "failed")
        return StoreScrapeResult(
            status=status,
            products=products,
            reason=raw_result.get("reason"),
            message_key=raw_result.get("message_key"),
            message_params=raw_result.get("message_params") or {},
            diagnostics={**diagnostics, **(raw_result.get("diagnostics") or {})},
            replace_offers=raw_result.get("replace_offers"),
        )

    return StoreScrapeResult.failed(
        reason=f"unexpected_result_type:{type(raw_result).__name__}",
        diagnostics=diagnostics,
    )


class StorePlugin(ABC):
    """
    Base class for all store plugins.
    
    Each store implements this and defines:
    - config: StoreConfig with metadata
    - scrape_offers(): Logic to fetch offers
    """

    LOCATION_SEARCH_CACHE_TTL_SECONDS = 1800
    
    @property
    @abstractmethod
    def config(self) -> StoreConfig:
        """
        Return store configuration.
        
        Must be implemented by each store.
        
        Returns:
            StoreConfig with store metadata
        """
        pass
    
    @abstractmethod
    async def scrape_offers(
        self,
        credentials: Optional[Dict] = None
    ) -> Union[StoreScrapeResult, List[Dict]]:
        """
        Scrape offers from the store.
        
        Args:
            credentials: Optional dict with login credentials
                        {"personnummer": "XXXXXX-XXXX", "password": "..."}
        
        Returns:
            StoreScrapeResult with status + products. Legacy plugins may still
            return a plain product list; callers should normalize via
            normalize_store_scrape_result().
        
        Raises:
            NotImplementedError: If store hasn't implemented scraper yet
            Exception: On scraping error (logged and handled by caller)
        """
        pass

    def _scrape_result_from_products(
        self,
        products: Optional[List[Dict]],
        *,
        location_type: Optional[str] = None,
        reason: Optional[str] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> StoreScrapeResult:
        """Build a conservative plugin result from a product list."""
        product_list = products or []
        result_diagnostics = {
            "store": self.config.id,
            "location_type": location_type,
            "product_count": len(product_list),
        }
        if diagnostics:
            result_diagnostics.update(diagnostics)

        if product_list:
            return StoreScrapeResult.success(
                product_list,
                diagnostics=result_diagnostics,
            )

        return StoreScrapeResult.failed(
            reason=reason or "no_products_returned",
            diagnostics=result_diagnostics,
        )
    
    def is_enabled(self) -> bool:
        """
        Is the store enabled?
        
        Returns:
            True if enabled=True in config
        """
        return self.config.enabled
    
    def requires_credentials(self) -> bool:
        """
        Does the store require login?

        Returns:
            True if has_credentials=True in config
        """
        return self.config.has_credentials

    @property
    def estimated_scrape_time(self) -> int:
        """
        Estimated scrape time in seconds.

        Override this for stores that take longer (e.g., Mathem ~360s).
        Used by the UI to show appropriate progress messages.
        After first scrape, actual measured time is used instead.

        Returns:
            Estimated seconds for a full scrape (default: 300 = 5 min)
        """
        return 300

    async def test_connection(self) -> bool:
        """
        Test if store website is accessible.

        Default implementation: attempt to scrape 0 products.
        Can be overridden by specific stores for faster testing.

        Returns:
            True if connection works
        """
        try:
            # Attempt to scrape (returns empty list on error)
            result = normalize_store_scrape_result(
                await self.scrape_offers(),
                store_name=self.config.name,
            )
            return result.status in {"success", "success_empty", "partial"}
        except Exception:
            return False

    async def verify_credentials(self, username: str, password: str) -> Dict:
        """
        Verify store credentials by attempting login.

        Default implementation returns "not supported".
        Stores that require authentication should override this.

        Args:
            username: Username/personnummer for login
            password: Password for login

        Returns:
            Dict with 'success' (bool) and 'message' (str)
        """
        return {
            "success": False,
            "message": f"Credential verification not implemented for {self.config.name}"
        }

    def get_config_fields(self) -> List[StoreConfigField]:
        """
        Return configuration fields for this store.

        Override this to define store-specific configuration UI.
        The fields will be rendered dynamically on the stores page.

        Returns:
            List of StoreConfigField definitions
        """
        return []

    async def search_locations(self, query: str) -> List[Dict]:
        """
        Search for store locations/branches.

        Override this if your store supports location selection.
        Used by "search" type config fields.

        Args:
            query: Search query (e.g., city name, address)

        Returns:
            List of locations:
            [
                {
                    "id": "store123",
                    "name": "Willys Kungsbacka",
                    "address": "Storgatan 1, 434 30 Kungsbacka",
                    "type": "physical"  # or "ehandel"
                },
                ...
            ]
        """
        return []

    def _normalize_location_search_query(self, query: str) -> str:
        """Normalize location-search queries for cache keys."""
        return re.sub(r"\s+", " ", (query or "").strip().lower())

    def _build_location_search_cache_key(self, scope: str, query: str, **context) -> str:
        """Build a stable cache key for store-location searches."""
        parts = [scope.strip().lower(), self._normalize_location_search_query(query)]
        for key, value in sorted(context.items()):
            parts.append(f"{key}={str(value).strip().lower()}")
        return "|".join(parts)

    async def _get_or_cache_location_search(
        self,
        cache_key: str,
        loader: Callable[[], Awaitable[List[Dict]]],
        ttl_seconds: Optional[int] = None,
    ) -> List[Dict]:
        """Cache location search results in-memory for the current app runtime."""
        ttl = ttl_seconds or self.LOCATION_SEARCH_CACHE_TTL_SECONDS
        now = time.monotonic()

        cache = getattr(self, "_location_search_cache", None)
        if cache is None:
            cache = {}
            setattr(self, "_location_search_cache", cache)

        cached = cache.get(cache_key)
        if cached and (now - cached["cached_at"]) < ttl:
            return copy.deepcopy(cached["results"])

        results = await loader()
        cache[cache_key] = {
            "cached_at": now,
            "results": copy.deepcopy(results),
        }
        return copy.deepcopy(results)

    def __repr__(self):
        return f"<{self.__class__.__name__}(id='{self.config.id}', enabled={self.config.enabled})>"

    # ==========================================================================
    # Food filter word lists from the active market profile.
    #
    # Used by _filter_food_items() to separate food from non-food products.
    # Store subclasses can override these if a specific chain needs its own
    # category names or product heuristics.
    #
    #   from languages.de.food_filters import (
    #       FOOD_CATEGORIES, NON_FOOD_CATEGORIES, FOOD_INDICATORS, ...
    #   )
    #   class LidlStore(StorePlugin):
    #       FOOD_CATEGORIES = FOOD_CATEGORIES
    #       ...
    # ==========================================================================

    FOOD_CATEGORIES = _FOOD_FILTER_PROFILE.food_categories
    NON_FOOD_CATEGORIES = _FOOD_FILTER_PROFILE.non_food_categories
    FOOD_INDICATORS = _FOOD_FILTER_PROFILE.food_indicators
    CERTIFICATION_LOGOS = _FOOD_FILTER_PROFILE.certification_logos
    NON_FOOD_STRONG = _FOOD_FILTER_PROFILE.non_food_strong
    NON_FOOD_INDICATORS = _FOOD_FILTER_PROFILE.non_food_indicators

    def _parse_price(self, price_str) -> float:
        """Parse store price text to float. Handles comma/colon decimals."""
        try:
            price_str = str(price_str).replace(',', '.').replace(':', '.')
            price_str = re.sub(r'[^\d.]', '', price_str)
            return float(price_str)
        except (ValueError, AttributeError):
            return 0.0

    def _parse_unit(self, unit_str: str) -> str:
        """Parse store unit text to a standard internal unit."""
        unit_map = get_unit_aliases()
        return unit_map.get(unit_str, get_default_unit())

    def _filter_food_items(self, products: List[Dict], log_filtered: bool = True) -> List[Dict]:
        """
        Filter products to only include food items.

        Use this for stores with mixed food/non-food inventory (ICA, Coop).
        Willys/Mathem typically don't need this as they sell mostly food.

        Args:
            products: List of product dicts with 'name' and optionally 'category'
            log_filtered: If True, log filtered items for debugging

        Returns:
            List of products that are likely food items
        """
        from loguru import logger

        food_products = []
        filtered_out = []

        for product in products:
            category = (product.get("category") or "").lower()
            name = (product.get("name") or "").lower()
            price = product.get("price", 0)

            # Step 0: Filter out certification logos (scraping artifacts, not real products)
            # These are badge names like "Nyckelhålet", "EU Lövet" that got scraped as products
            name_stripped = name.strip()
            if name_stripped in self.CERTIFICATION_LOGOS:
                filtered_out.append({
                    "name": product.get("name"),
                    "price": price,
                    "reason": "certification logo (not a product)"
                })
                continue

            # Step 1: Check if explicitly non-food category
            is_non_food_category = any(nf in category for nf in self.NON_FOOD_CATEGORIES)
            if is_non_food_category:
                filtered_out.append({
                    "name": product.get("name"),
                    "price": price,
                    "reason": f"non-food category: {category}"
                })
                continue

            # Step 2: Check STRONG non-food indicators (schampo, tvål, etc.)
            # These are product types that are NEVER food, even if they have "ml" in name
            is_strong_non_food = any(ind in name for ind in self.NON_FOOD_STRONG)
            if is_strong_non_food:
                filtered_out.append({
                    "name": product.get("name"),
                    "price": price,
                    "reason": "non-food product type"
                })
                continue

            # Step 3: Check if it's a known food category
            is_food_category = any(fc in category for fc in self.FOOD_CATEGORIES)
            if is_food_category:
                food_products.append(product)
                continue

            # Step 4: Check if name contains FOOD indicators
            # This ensures "ostbricka" matches "ost" before "bricka" filters it
            if self._looks_like_food(name):
                food_products.append(product)
                continue

            # Step 5: Check REGULAR non-food indicators (bricka, skål, etc.)
            is_non_food_name = self._looks_like_non_food(name)
            if is_non_food_name:
                filtered_out.append({
                    "name": product.get("name"),
                    "price": price,
                    "reason": "non-food product name"
                })
                continue

            # Step 6: Unknown category and no indicators - exclude to be safe
            filtered_out.append({
                "name": product.get("name"),
                "price": price,
                "reason": "unknown category, no food indicators"
            })

        # Log filter statistics
        if log_filtered and filtered_out:
            logger.info(f"Filtered out {len(filtered_out)} non-food items from {len(products)} total")
            # Show last 3 filtered items for sanity check
            for item in filtered_out[-3:]:
                logger.info(f"  Filtered: {item['name']} ({item['price']} kr) - {item['reason']}")

        return food_products

    def _looks_like_food(self, name: str) -> bool:
        """Heuristic check if product name looks like food."""
        return any(indicator in name for indicator in self.FOOD_INDICATORS)

    def _looks_like_non_food(self, name: str) -> bool:
        """Heuristic check if product name looks like non-food."""
        return any(indicator in name for indicator in self.NON_FOOD_INDICATORS)

    def _filter_certification_logos(self, products: List[Dict], log_filtered: bool = True) -> List[Dict]:
        """
        Filter out certification logos that got scraped as product names.

        These are scraping artifacts like "Nyckelhålet", "EU Lövet" that are
        badge names, not real products. Unlike _filter_food_items(), this only
        removes artifacts and keeps all real products (including hygiene/household).

        Args:
            products: List of product dicts with 'name'
            log_filtered: If True, log filtered items for debugging

        Returns:
            List of products with certification logos removed
        """
        from loguru import logger

        valid_products = []
        filtered_out = []

        for product in products:
            name = (product.get("name") or "").lower().strip()

            # Check if name matches a certification logo exactly
            if name in self.CERTIFICATION_LOGOS:
                filtered_out.append(product.get("name"))
                continue

            valid_products.append(product)

        if log_filtered and filtered_out:
            logger.info(f"Filtered {len(filtered_out)} certification logos: {filtered_out[:5]}")

        return valid_products
