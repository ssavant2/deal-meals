"""
Generic database saver for all stores.

IMPROVED VERSION with detailed error logging.

Also triggers recipe-offer cache computation after offers are saved.
"""

from sqlalchemy import text, func
from loguru import logger
from typing import List, Dict, Any
import asyncio
import sys
import os
from functools import partial

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from database import get_db_session
from models import Store, Offer

try:
    from languages.market_runtime import (
        get_default_unit,
        override_category_by_brand,
        strip_brand_from_name,
    )
except ModuleNotFoundError:
    from app.languages.market_runtime import (
        get_default_unit,
        override_category_by_brand,
        strip_brand_from_name,
    )

try:
    from app.config import settings
except ModuleNotFoundError:
    from config import settings


INGREDIENT_ROUTING_BASELINE_MISMATCH = "ingredient_routing_fullscan_baseline_mismatch"


def _delta_exception_result(exc: Exception) -> Dict[str, Any]:
    return {
        "success": False,
        "applied": False,
        "fallback_reason": f"delta_exception:{type(exc).__name__}",
        "error": str(exc),
    }


def _delta_fallback_requires_fullscan(delta_result: Dict[str, Any]) -> bool:
    """Return whether a failed delta attempt should rebuild with ingredient routing off."""
    return delta_result.get("fallback_reason") == INGREDIENT_ROUTING_BASELINE_MISMATCH


def _mark_background_rebuild(store_name: str | None) -> None:
    if not store_name:
        return

    try:
        with get_db_session() as db:
            db.execute(text("""
                UPDATE cache_metadata
                SET last_background_rebuild_at = NOW(),
                    background_rebuild_source = :store_name
                WHERE cache_name = 'recipe_offer_matches'
            """), {"store_name": store_name})
            db.commit()
    except Exception as e:
        logger.warning(f"Could not mark background rebuild: {e}")


async def _compute_cache_async_after_delta_fallback(
    compute_cache_async,
    temporary_ingredient_routing_mode,
    delta_result: Dict[str, Any],
) -> Dict[str, Any]:
    if _delta_fallback_requires_fullscan(delta_result):
        logger.warning(
            "Ingredient-routing baseline mismatch detected; "
            "falling back with ingredient routing disabled"
        )
        with temporary_ingredient_routing_mode("off"):
            return await compute_cache_async()
    return await compute_cache_async()


def _refresh_cache_after_delta_fallback(
    refresh_cache_locked,
    temporary_ingredient_routing_mode,
    delta_result: Dict[str, Any],
) -> Dict[str, Any]:
    if _delta_fallback_requires_fullscan(delta_result):
        logger.warning(
            "Ingredient-routing baseline mismatch detected; "
            "falling back with ingredient routing disabled"
        )
        with temporary_ingredient_routing_mode("off"):
            return refresh_cache_locked()
    return refresh_cache_locked()


def _build_offer_insert_mapping(
    *,
    store_id,
    location_type: str,
    location_name: str | None,
    product: Dict,
) -> Dict:
    """Build the DB row for one validated offer product."""
    category = override_category_by_brand(
        product.get('category', 'other'),
        product.get('brand')
    )

    product_name = strip_brand_from_name(
        product['name'], product.get('brand', '')
    )

    return {
        'store_id': store_id,
        'name': product_name,
        'price': round(product['price'], 2),
        'original_price': round(product.get('original_price', product['price']), 2),
        'savings': max(round(product.get('savings', 0.0), 2), 0),
        'unit': product.get('unit', get_default_unit()),
        'category': category,
        'brand': product.get('brand'),
        'weight_grams': product.get('weight_grams'),
        'is_multi_buy': product.get('is_multi_buy', False),
        'multi_buy_quantity': product.get('multi_buy_quantity'),
        'multi_buy_total_price': (
            round(product['multi_buy_total_price'], 2)
            if product.get('multi_buy_total_price')
            else None
        ),
        'image_url': product.get('image_url'),
        'product_url': product.get('product_url'),
        'location_type': location_type,
        'location_name': location_name,
    }


def ensure_store_exists(store_id: str, store_name: str, store_url: str = None) -> None:
    """
    Ensure a store exists in the database, creating it if needed.

    Called by store plugins before saving offers. This makes the plugin
    system fully modular - new stores are auto-registered on first use.

    Lookup uses store_type (ASCII lowercase id like 'hemkop') to avoid
    issues with non-ASCII display names like 'Hemköp'.

    Args:
        store_id: Store identifier (e.g., 'willys', 'hemkop')
        store_name: Display name (e.g., 'Willys', 'Hemköp')
        store_url: Store website URL (optional)

    Raises:
        RuntimeError: If store registration fails
    """
    store_type = store_id.lower()

    with get_db_session() as session:
        try:
            # Match on store_type (always ASCII) - safe for names like Hemköp
            existing = session.query(Store).filter(Store.store_type == store_type).first()

            if existing:
                logger.debug(f"Store '{store_name}' already exists in database")
                return

            # Create new store
            new_store = Store(
                name=store_name,
                store_type=store_type,
                url=store_url
            )
            session.add(new_store)
            session.commit()

            logger.success(f"✓ Auto-registered new store: {store_name} ({store_id})")

        except Exception as e:
            session.rollback()
            logger.error(f"✗ Failed to register store {store_name}: {e}")
            raise RuntimeError(f"Failed to register store {store_name}: {e}") from e


def clear_offers_for_empty_scrape(store_name: str, reason: str = None) -> Dict[str, Any]:
    """Clear offers/cache for a verified empty scrape result."""
    stats = {
        'cleared': 0,
        'created': 0,
        'errors': 0,
        'skipped': 0,
        'empty_input': True,
        'verified_empty': True,
        'stale_existing_offers': False,
    }

    with get_db_session() as session:
        try:
            cleared = session.query(Offer).delete(synchronize_session=False)
            stats['cleared'] = cleared
            session.commit()
            logger.info(
                f"✓ Cleared {cleared} old offers after verified empty scrape for {store_name}"
            )
        except Exception as e:
            session.rollback()
            logger.error(f"✗ Failed to clear offers for verified empty {store_name} scrape: {e}")
            raise

    try:
        from cache_manager import cache_manager as _cm
        _cm.clear_to_empty(error_message=reason)
    except Exception as e:
        stats['errors'] += 1
        logger.error(f"✗ Failed to clear cache after verified empty {store_name} scrape: {e}")
        raise

    return stats


async def _trigger_cache_refresh_async(store_name: str = None):
    """
    Trigger recipe-offer cache refresh in the event loop.

    Called after offers are saved to pre-compute matches for fast page loads.
    Uses the global cache_manager instance via compute_cache_async() so
    the DB-backed cache is refreshed for the web server.

    If store_name is provided, marks this as a background rebuild so home.html
    can notify the user via SSE.
    """
    try:
        from cache_manager import compute_cache_async
        from cache_delta import apply_verified_offer_delta, _temporary_ingredient_routing_mode
        from delta_probation_runtime import append_runtime_probation_history

        logger.info(f"Triggering recipe cache refresh (background: {store_name})...")
        result = None
        delta_result = None

        if store_name and settings.cache_delta_enabled:
            logger.info(
                "Delta cache refresh enabled for offer updates "
                f"(verify_full_preview={settings.cache_delta_verify_full_preview})"
            )
            delta_runner = partial(
                apply_verified_offer_delta,
                apply=True,
                verify_full_preview=settings.cache_delta_verify_full_preview,
            )
            try:
                delta_result = await asyncio.get_running_loop().run_in_executor(None, delta_runner)
            except Exception as e:
                logger.warning(
                    f"Delta cache refresh failed ({e}); "
                    "falling back to full compiled rebuild"
                )
                delta_result = _delta_exception_result(e)
            result = delta_result
            if not delta_result.get("applied"):
                reason = delta_result.get("fallback_reason") or "delta_verification_failed"
                logger.warning(
                    f"Delta cache refresh was not applied ({reason}); "
                    "falling back to full compiled rebuild"
                )
                result = await _compute_cache_async_after_delta_fallback(
                    compute_cache_async,
                    _temporary_ingredient_routing_mode,
                    delta_result,
                )
        else:
            result = await compute_cache_async()

        if result.get('skipped'):
            logger.info(f"Cache rebuild skipped: {result.get('reason')}")
            return

        logger.success(
            "Cache refreshed ({mode}): {recipes} recipes in {time_ms}ms".format(
                mode=result.get('effective_rebuild_mode', 'unknown'),
                recipes=result.get('cached', 0),
                time_ms=result.get('time_ms', 0),
            )
        )

        if delta_result is not None:
            history_result = dict(delta_result)
            if not delta_result.get("applied"):
                history_result["effective_rebuild_mode"] = result.get(
                    "effective_rebuild_mode",
                    history_result.get("effective_rebuild_mode"),
                )
            append_runtime_probation_history(
                history_result,
                store_name=store_name,
                trigger="offer_refresh_async",
            )

        # Mark this as a background rebuild so home.html can detect it
        _mark_background_rebuild(store_name)

    except Exception as e:
        logger.error(f"Cache refresh failed: {e}")
        # Don't raise - cache failure shouldn't break offer saving


def save_offers(store_name: str, products: List[Dict]) -> Dict[str, Any]:
    """
    Save products to database (generic function for all stores).

    IMPORTANT: replaces old offers only after at least one new offer row has
    been validated. Empty/invalid scrape results keep the previous offer set
    and are reported as stale_existing_offers.

    Args:
        store_name: Store name or store_type id (e.g., 'Willys', 'hemkop')
        products: List of products

    Returns:
        Dict with statistics: {'cleared': X, 'created': Y, 'errors': Z, 'skipped': W}
    """

    stats = {
        'cleared': 0,
        'created': 0,
        'errors': 0,
        'skipped': 0,
        'empty_input': False,
        'stale_existing_offers': False,
    }

    if not products:
        logger.warning(
            f"No products to save for {store_name}; keeping existing offers and cache"
        )
        stats['empty_input'] = True
        stats['stale_existing_offers'] = True
        return stats

    # Deduplicate products by product_url (keep first occurrence)
    seen_urls = set()
    unique_products = []
    duplicates = 0
    for product in products:
        url = product.get('product_url')
        if url and url in seen_urls:
            duplicates += 1
            continue
        if url:
            seen_urls.add(url)
        unique_products.append(product)

    if duplicates > 0:
        logger.info(f"Removed {duplicates} duplicate products (by URL)")

    products = unique_products
    logger.info(f"Saving {len(products)} products for {store_name}...")

    with get_db_session() as session:
        try:
            # Try store_type first (ASCII-safe, works for Hemköp etc.)
            # Then fall back to case-insensitive name match
            store = session.query(Store).filter(
                Store.store_type == store_name.lower()
            ).first()

            if not store:
                store = session.query(Store).filter(
                    func.lower(Store.name) == func.lower(store_name)
                ).first()

            if not store:
                logger.error(f"{store_name} store not found in database!")
                return stats

            # Get location info from stores config
            config = store.config if store.config else {}
            location_type = config.get('location_type', 'ehandel')
            location_name = config.get('location_name')

            logger.info(f"Saving offers for {store_name} - location_type: {location_type}, location_name: {location_name}")

            # Build validated insert rows first so we can use a fast bulk insert path.
            logger.info(f"Preparing {len(products)} new products for insert...")
            offer_rows = []
            
            for i, product in enumerate(products, 1):
                try:
                    # Validate that product has required fields
                    if not product.get('name'):
                        logger.warning(f"⊘ Product {i}: Missing name, skipping")
                        stats['skipped'] += 1
                        continue
                    
                    if not product.get('price') or product.get('price') <= 0:
                        logger.warning(f"⊘ Product {i} ({product.get('name')}): Invalid price, skipping")
                        stats['skipped'] += 1
                        continue
                    
                    offer_rows.append(
                        _build_offer_insert_mapping(
                            store_id=store.id,
                            location_type=location_type,
                            location_name=location_name,
                            product=product,
                        )
                    )
                    
                    # Log every 25th product
                    if i % 25 == 0:
                        logger.debug(f"  Progress: {i}/{len(products)} products prepared")
                
                except Exception as e:
                    error_msg = str(e)
                    
                    # Detailed error logging
                    if 'product_url' in error_msg and 'unique' in error_msg.lower():
                        logger.warning(
                            f"⊘ Product {i} ({product.get('name')}): "
                            f"Duplicate URL, skipping - {product.get('product_url')}"
                        )
                    elif 'name' in error_msg:
                        logger.error(
                            f"✗ Product {i}: Name issue - {error_msg}"
                        )
                    elif 'price' in error_msg:
                        logger.error(
                            f"✗ Product {i} ({product.get('name')}): "
                            f"Price issue - price={product.get('price')} - {error_msg}"
                        )
                    else:
                        logger.error(
                            f"✗ Product {i} ({product.get('name')}): {error_msg}"
                        )
                    
                    stats['errors'] += 1
                    continue

            if not offer_rows:
                logger.warning(
                    f"No valid products to save for {store_name}; "
                    "keeping existing offers and cache"
                )
                stats['stale_existing_offers'] = True
                return stats

            # Insert prepared rows. Bulk insert is much faster than row-by-row
            # ORM adds, but keep a safe fallback if the bulk path hits an edge case.
            logger.info(f"Bulk inserting {len(offer_rows)} new products...")
            try:
                # Clear ALL old offers (from ALL stores) only after new rows
                # have been validated. Delete + insert stay in one transaction
                # so a bulk failure keeps the old offer set intact.
                cleared = session.query(Offer).delete(synchronize_session=False)
                stats['cleared'] = cleared
                logger.info(f"✓ Cleared {cleared} old offers from ALL stores (replacing with {store_name})")
                session.bulk_insert_mappings(Offer, offer_rows)
                session.commit()
                stats['created'] = len(offer_rows)
            except Exception as bulk_error:
                session.rollback()
                logger.warning(
                    f"Bulk insert failed for {store_name}, falling back to row-by-row insert: "
                    f"{bulk_error}"
                )

                inserted = 0
                cleared = session.query(Offer).delete(synchronize_session=False)
                stats['cleared'] = cleared
                logger.info(f"✓ Cleared {cleared} old offers from ALL stores (fallback insert for {store_name})")

                for i, row in enumerate(offer_rows, 1):
                    try:
                        with session.begin_nested():
                            session.add(Offer(**row))
                        inserted += 1
                        if i % 25 == 0:
                            logger.debug(f"  Fallback progress: {i}/{len(offer_rows)} products inserted")
                    except Exception as row_error:
                        logger.error(
                            f"✗ Fallback insert failed for product {i} ({row.get('name')}): {row_error}"
                        )
                        stats['errors'] += 1

                if inserted == 0:
                    session.rollback()
                    stats['cleared'] = 0
                    stats['stale_existing_offers'] = True
                    logger.warning(
                        f"No products could be inserted for {store_name}; "
                        "keeping existing offers and cache"
                    )
                    return stats

                session.commit()
                stats['created'] = inserted
            
            logger.success(
                f"✓ Saved {store_name} offers - "
                f"Cleared: {stats['cleared']}, "
                f"Created: {stats['created']}, "
                f"Skipped: {stats['skipped']}, "
                f"Errors: {stats['errors']}"
            )

            # Trigger cache refresh in event loop (async-safe)
            # This pre-computes recipe-offer matches for fast page loads
            if stats['created'] > 0:
                logger.info(f"Starting cache refresh in background for {store_name}...")
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(_trigger_cache_refresh_async(store_name))
                except RuntimeError:
                    # No running event loop (e.g. to_thread or CLI usage) — run synchronously
                    from cache_manager import refresh_cache_locked
                    from cache_delta import apply_verified_offer_delta, _temporary_ingredient_routing_mode
                    from delta_probation_runtime import append_runtime_probation_history

                    logger.info("No event loop available, running cache refresh synchronously")
                    if store_name and settings.cache_delta_enabled:
                        try:
                            result = apply_verified_offer_delta(
                                apply=True,
                                verify_full_preview=settings.cache_delta_verify_full_preview,
                            )
                        except Exception as e:
                            logger.warning(
                                f"Delta cache refresh failed ({e}); "
                                "falling back to full compiled rebuild"
                            )
                            result = _delta_exception_result(e)
                        if not result.get("applied"):
                            reason = result.get("fallback_reason") or "delta_verification_failed"
                            logger.warning(
                                f"Delta cache refresh was not applied ({reason}); "
                                "falling back to full compiled rebuild"
                            )
                            fallback_result = _refresh_cache_after_delta_fallback(
                                refresh_cache_locked,
                                _temporary_ingredient_routing_mode,
                                result,
                            )
                            history_result = dict(result)
                            history_result["effective_rebuild_mode"] = fallback_result.get(
                                "effective_rebuild_mode",
                                history_result.get("effective_rebuild_mode"),
                            )
                            append_runtime_probation_history(
                                history_result,
                                store_name=store_name,
                                trigger="offer_refresh_sync",
                            )
                        else:
                            append_runtime_probation_history(
                                result,
                                store_name=store_name,
                                trigger="offer_refresh_sync",
                            )
                    else:
                        refresh_cache_locked()

                    _mark_background_rebuild(store_name)

            return stats

        except Exception as e:
            session.rollback()
            logger.error(f"✗ Database error for {store_name}: {e}")
            raise


if __name__ == "__main__":
    # Test
    from rich.console import Console
    
    console = Console()
    console.print("[yellow]Testing db_saver...[/yellow]")
    
    # Mock data
    test_products = [
        {
            "name": "Test Product 1",
            "price": 19.90,
            "original_price": 29.90,
            "savings": 10.0,
            "unit": "st",
            "category": "test"
        },
        {
            "name": "Test Product 2 - Invalid",
            "price": 0,  # Invalid price
            "unit": "st"
        },
        {
            # Missing name
            "price": 15.0,
            "unit": "st"
        }
    ]
    
    stats = save_offers('Willys', test_products)
    console.print(f"[green]Stats: {stats}[/green]")
    console.print(f"  Created: {stats['created']}")
    console.print(f"  Skipped: {stats['skipped']}")
    console.print(f"  Errors: {stats['errors']}")
