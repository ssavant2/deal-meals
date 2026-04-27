"""
Auto-discover all store plugins.

Scans stores/ folder and automatically loads all stores.
"""

import importlib
from typing import Dict, List, Optional
from pathlib import Path
from loguru import logger

from .base import (
    StoreConfig,
    StoreConfigField,
    StorePlugin,
    StoreScrapeResult,
    normalize_store_scrape_result,
)


# Cache for loaded stores
_STORES: Dict[str, StorePlugin] = {}
_DISCOVERY_ERRORS: List[Dict[str, str]] = []
_DISCOVERY_COMPLETE = False


def _record_discovery_error(
    module_name: str,
    phase: str,
    error: Exception,
    class_name: Optional[str] = None,
) -> None:
    entry = {
        "module": module_name,
        "phase": phase,
        "error": repr(error),
    }
    if class_name:
        entry["class"] = class_name
    _DISCOVERY_ERRORS.append(entry)


def _format_discovery_errors() -> str:
    details = []
    for error in _DISCOVERY_ERRORS:
        target = error["module"]
        if error.get("class"):
            target = f"{target}.{error['class']}"
        details.append(f"{target} ({error['phase']}): {error['error']}")
    return "; ".join(details)


def discover_stores() -> Dict[str, StorePlugin]:
    """
    Automatically find all stores in this folder.
    
    Scans all submodules in stores/ and looks for classes
    that inherit from StorePlugin.
    
    Returns:
        Dict with stores: {"willys": WillysStore(), "ica": ICAStore(), ...}
    
    Example:
        stores = discover_stores()
        willys = stores["willys"]
        print(willys.config.name)  # "Willys"
    """
    global _DISCOVERY_COMPLETE

    if _DISCOVERY_COMPLETE:  # Already loaded
        return _STORES
    
    logger.info("Discovering store plugins...")
    _STORES.clear()
    _DISCOVERY_ERRORS.clear()
    
    # Find all submodules (willys, ica, coop, mathem)
    stores_path = Path(__file__).parent
    
    for item in stores_path.iterdir():
        if not item.is_dir():
            continue
        if item.name.startswith('_') or item.name.startswith('.'):
            continue
        
        module_name = item.name
        
        try:
            # Import the module (e.g., stores.willys)
            module = importlib.import_module(f'.{module_name}', package=__name__)
            
            # Look for StorePlugin classes
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                
                # Check if it's a StorePlugin subclass
                if (isinstance(attr, type) and 
                    issubclass(attr, StorePlugin) and 
                    attr != StorePlugin):
                    
                    # Create instance
                    try:
                        store = attr()
                        store_id = store.config.id
                        _STORES[store_id] = store
                        
                        logger.success(
                            f"Loaded store: {store.config.name} "
                            f"(enabled={store.config.enabled})"
                        )
                    except Exception as e:
                        _record_discovery_error(module_name, "instantiate", e, attr_name)
                        logger.exception(
                            "Store plugin '{}.{}' failed during initialization; "
                            "startup cleanup will skip destructive store removal",
                            module_name,
                            attr_name,
                        )
        
        except Exception as e:
            _record_discovery_error(module_name, "import", e)
            logger.exception(
                "Store plugin '{}' failed during import; startup cleanup will skip "
                "destructive store removal",
                module_name,
            )
    
    _DISCOVERY_COMPLETE = True
    logger.info(f"Discovered {len(_STORES)} stores: {list(_STORES.keys())}")
    if _DISCOVERY_ERRORS:
        logger.error(
            "Store plugin discovery completed with {} error(s); destructive store "
            "registry cleanup must be skipped: {}",
            len(_DISCOVERY_ERRORS),
            _format_discovery_errors(),
        )
    return _STORES


def get_store_discovery_errors() -> List[Dict[str, str]]:
    """Return store plugin discovery errors from the cached startup scan."""
    discover_stores()
    return [dict(error) for error in _DISCOVERY_ERRORS]


def get_all_stores() -> List[StorePlugin]:
    """
    Fetch all stores (both enabled and disabled).
    
    Returns:
        List of all StorePlugin instances, sorted alphabetically
    """
    stores = discover_stores()
    return sorted(stores.values(), key=lambda s: s.config.name)


def get_enabled_stores() -> List[StorePlugin]:
    """
    Fetch all enabled stores.
    
    Returns:
        List of enabled StorePlugin instances, sorted alphabetically
    
    Example:
        for store in get_enabled_stores():
            print(f"{store.config.name}: {store.config.url}")
    """
    stores = discover_stores()
    enabled = [s for s in stores.values() if s.is_enabled()]
    return sorted(enabled, key=lambda s: s.config.name)


def get_store(store_id: str) -> StorePlugin:
    """
    Fetch a specific store by ID.
    
    Args:
        store_id: Store ID (e.g., "willys", "ica")
    
    Returns:
        StorePlugin instance
    
    Raises:
        KeyError: If store_id doesn't exist
    
    Example:
        willys = get_store("willys")
        offers = await willys.scrape_offers(credentials)
    """
    stores = discover_stores()
    return stores[store_id]




# Export for easy import
__all__ = [
    'StorePlugin',
    'StoreConfig',
    'StoreConfigField',
    'StoreScrapeResult',
    'normalize_store_scrape_result',
    'discover_stores',
    'get_store_discovery_errors',
    'get_all_stores',
    'get_enabled_stores',
    'get_store',
]
