"""
Willys Store Finder v3 - Uses Willys official API.

Fetches store list directly from Willys backend API.
"""

import httpx
from typing import List, Dict, Optional
from loguru import logger
from utils.security import ssrf_safe_event_hook


class WillysStoreFinder:
    """Fetches list of Willys stores via official API."""
    
    def __init__(self):
        self.api_url = "https://www.willys.se/axfood/rest/search/store"
    
    
    async def search_stores(self, search_term: str = "göteborg") -> List[Dict]:
        """
        Search for stores based on city/location.

        Args:
            search_term: Location to search for

        Returns:
            List of stores
        """

        logger.info(f"Searching for Willys stores near: {search_term}")

        try:
            # Call Willys API
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
            stores = self._parse_api_response(data, search_term)

            logger.success(f"Found {len(stores)} stores for '{search_term}'")
            return stores

        except Exception as e:
            logger.error(f"Error searching stores: {e}")
            return []
    
    
    def _parse_api_response(self, data: dict, search_term: str) -> List[Dict]:
        """Parse API response to our format."""
        
        stores = []
        
        results = data.get('results', [])
        
        for store_data in results:
            try:
                # Extract address
                address_obj = store_data.get('address', {})
                address_parts = []
                
                if address_obj.get('line1'):
                    address_parts.append(address_obj['line1'])
                if address_obj.get('postalCode'):
                    address_parts.append(address_obj['postalCode'])
                if address_obj.get('town'):
                    address_parts.append(address_obj['town'])
                
                address = ', '.join(address_parts)
                
                # Determine type (store or home delivery)
                name = store_data.get('displayName', store_data.get('name', ''))
                store_type = "hemma" if "Hemma" in name else "butik"
                
                # Generate store_id from storeId or name
                store_id = store_data.get('storeId', '')
                if not store_id:
                    # Fallback: generate from name
                    store_id = self._generate_store_id(name)
                
                stores.append({
                    "name": name,
                    "address": address,
                    "type": store_type,
                    "store_id": store_id,
                    "search_term": search_term,
                    # Extra info from API
                    "phone": address_obj.get('phoneNumber'),
                    "opening_hours": store_data.get('todaysOpeningHours'),
                    "click_and_collect": store_data.get('clickAndCollect', False)
                })
                
            except Exception as e:
                logger.warning(f"Failed to parse store: {e}")
                continue
        
        return stores
    
    
    def _generate_store_id(self, store_name: str) -> str:
        """
        Generate a store_id from store name.
        
        "Willys Göteborg Gamlestaden" -> "gamlestaden"
        """
        import re
        
        name = store_name.lower()
        name = re.sub(r'willys\s*', '', name)
        
        # Remove common cities
        cities = ['göteborg', 'stockholm', 'malmö', 'uppsala', 'luleå', 'umeå']
        for city in cities:
            name = re.sub(rf'\b{city}\b', '', name)
        
        # Take last word
        parts = name.split()
        if parts:
            if 'hemma' in parts:
                idx = parts.index('hemma')
                if idx + 1 < len(parts):
                    return f"hemma-{parts[idx+1]}"
                return "hemma"
            
            store_id = parts[-1].strip()
            store_id = re.sub(r'[^a-zåäö0-9-]', '', store_id)
            return store_id if store_id else "butik"
        
        return "butik"
    
    
    async def get_all_stores(self, cities: List[str] = None) -> List[Dict]:
        """
        Fetch stores for multiple cities.

        Args:
            cities: List of cities

        Returns:
            Combined list
        """

        if not cities:
            cities = ["göteborg", "stockholm", "malmö", "uppsala", "luleå"]

        all_stores = []

        for city in cities:
            stores = await self.search_stores(city)
            all_stores.extend(stores)

        # Deduplicate based on store_id
        unique = {s['store_id']: s for s in all_stores}.values()

        return sorted(list(unique), key=lambda x: x['name'])


# Global instance
willys_store_finder = WillysStoreFinder()


if __name__ == "__main__":
    # Test
    import asyncio
    from rich.console import Console
    from rich.table import Table

    async def main():
        console = Console()

        # Test different cities
        for city in ["luleå", "göteborg", "stockholm"]:
            stores = await willys_store_finder.search_stores(city)

            if stores:
                table = Table(title=f"Willys Stores - {city.capitalize()}")
                table.add_column("Name", style="cyan")
                table.add_column("Address", style="yellow")
                table.add_column("Type", style="green")
                table.add_column("ID", style="magenta")

                for store in stores:
                    table.add_row(
                        store['name'],
                        store['address'][:50] + "..." if len(store['address']) > 50 else store['address'],
                        store['type'],
                        store['store_id']
                    )

                console.print(table)
                console.print(f"[green]Total: {len(stores)} stores[/green]\n")
            else:
                console.print(f"[red]No stores found for {city}[/red]\n")

    asyncio.run(main())
