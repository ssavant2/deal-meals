"""
Hemköp Store Finder - Uses Hemköp/Axfood official API.

Fetches store list directly from Hemköp backend API.
Same API structure as Willys (both Axfood brands).
"""

import httpx
from typing import List, Dict
from loguru import logger
from utils.security import ssrf_safe_event_hook


class HemkopStoreFinder:
    """Fetches list of Hemköp stores via official API."""

    def __init__(self):
        self.api_url = "https://www.hemkop.se/axfood/rest/search/store"

    async def search_stores(self, search_term: str = "stockholm") -> List[Dict]:
        """
        Search for stores based on city/location.

        Args:
            search_term: Location to search for

        Returns:
            List of stores in standard format
        """
        logger.info(f"Searching for Hemköp stores near: {search_term}")

        try:
            params = {
                'q': search_term,
                'sort': 'score-desc',
                'externalPickupLocation': 'false'
            }

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }

            async with httpx.AsyncClient(event_hooks={"request": [ssrf_safe_event_hook]}) as client:
                response = await client.get(
                    self.api_url,
                    params=params,
                    headers=headers,
                    timeout=10
                )

            if response.status_code != 200:
                logger.error(f"API returned status {response.status_code}")
                return []

            data = response.json()
            stores = self._parse_api_response(data)

            logger.success(f"Found {len(stores)} stores for '{search_term}'")
            return stores

        except Exception as e:
            logger.error(f"Error searching stores: {e}")
            return []

    def _parse_api_response(self, data: dict) -> List[Dict]:
        """Parse API response to standard format."""
        stores = []
        results = data.get('results') or []

        for store_data in results:
            try:
                address_obj = store_data.get('address', {})
                address_parts = []

                if address_obj.get('line1'):
                    address_parts.append(address_obj['line1'])
                if address_obj.get('postalCode'):
                    address_parts.append(address_obj['postalCode'])
                if address_obj.get('town'):
                    address_parts.append(address_obj['town'])

                address = ', '.join(address_parts)

                name = store_data.get('displayName', store_data.get('name', ''))
                store_type = "hemma" if "Hemma" in name else "butik"

                store_id = store_data.get('storeId', '')

                stores.append({
                    "name": name,
                    "address": address,
                    "type": store_type,
                    "store_id": store_id,
                })

            except Exception as e:
                logger.warning(f"Failed to parse store: {e}")
                continue

        return stores


# Global instance
hemkop_store_finder = HemkopStoreFinder()
