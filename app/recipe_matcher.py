"""
Recipe Matcher v3 - Match recipes against sale offers with improved classification.

✨ FEATURES:
- 4 clear categories: Meat & Poultry, Fish & Seafood, Vegetarian, Smart buy
- Fixed classification based on recipe NAME priority
- Budget score: Coverage × Savings × Matches (Formula 3)
- Exclude categories (checkbox: meat, fish, dairy)
- Exclude keywords (freetext: milk, eggs, gluten, nuts)
- Paginated results (20 at a time, user can skip and get next 20)

🎯 USAGE:
    matcher = RecipeMatcher()

    # User preferences from GUI
    preferences = {
        'exclude_categories': ['fish'],  # Use English category keys
        'exclude_keywords': ['milk', 'eggs'],  # Locale-specific ingredient keywords
        'balance': {
            'meat': 0.35,
            'fish': 0.25,
            'vegetarian': 0.20,
            'smart_buy': 0.20
        }
    }

    # Match all recipes and get top 20
    top_recipes = matcher.match_all_recipes(preferences, max_results=20)
"""

from loguru import logger
from typing import List, Dict, Optional, Set
from database import get_db_session
from models import Offer, FoundRecipe
from sqlalchemy import text

# Import category constants (stable code keys; UI display labels are locale-specific)
try:
    from languages.categories import (
        MEAT, FISH, VEGETARIAN,
        POULTRY, DELI, DAIRY,
    )
except ModuleNotFoundError:
    from app.languages.categories import (
        MEAT, FISH, VEGETARIAN,
        POULTRY, DELI, DAIRY,
    )

# Import smart matching functions
try:
    from languages.matcher_runtime import (
        analyze_unmatched_offers_backend,
        build_keyword_patterns_backend,
        extract_keywords_from_product,
        get_classification_keywords_backend,
        get_filtered_offers_backend,
        get_recipe_fts_config_backend,
        has_keyword_match_backend,
        is_boring_recipe,
        keyword_match_fast_backend,
        match_recipe_to_offers_backend,
    )
except ModuleNotFoundError:
    from app.languages.matcher_runtime import (
        analyze_unmatched_offers_backend,
        build_keyword_patterns_backend,
        extract_keywords_from_product,
        get_classification_keywords_backend,
        get_filtered_offers_backend,
        get_recipe_fts_config_backend,
        has_keyword_match_backend,
        is_boring_recipe,
        keyword_match_fast_backend,
        match_recipe_to_offers_backend,
    )


# Max savings per ingredient for ranking purposes.
# Prevents single high-value items (e.g. 2.2kg cheese at 83 kr off) from
# dominating recipe rankings. Displayed savings are NOT affected.
SAVINGS_CAP_PER_INGREDIENT = 50.0


def get_default_matching_preferences() -> Dict:
    """Return matcher preferences used when no DB row exists."""
    return {
        'exclude_categories': [],
        'exclude_keywords': [],
        'local_meat_only': True,
        'balance': {
            MEAT: 3,
            FISH: 3,
            VEGETARIAN: 3,
            'smart_buy': 3
        },
        'filtered_products': [],
        'excluded_brands': [],
        'ranking_mode': 'absolute',
        'min_ingredients': 0,
        'max_ingredients': 0
    }


def get_matching_preferences_from_db() -> Optional[Dict]:
    """
    Fetch matching preferences from the database.

    Returns preferences dict in the format expected by RecipeMatcher,
    or None if no preferences are found.
    """
    try:
        with get_db_session() as db:
            result = db.execute(text("""
                SELECT
                    exclude_meat, exclude_fish, exclude_dairy,
                    exclude_keywords, local_meat_only,
                    balance_meat, balance_fish, balance_veg, balance_budget,
                    filtered_products, excluded_brands, ranking_mode,
                    min_ingredients, max_ingredients
                FROM matching_preferences
                LIMIT 1
            """)).fetchone()

            if result:
                # Build exclude_categories list based on boolean flags
                exclude_categories = []
                exclude_meat = result[0]
                exclude_fish = result[1]
                exclude_dairy = result[2]

                if exclude_meat:
                    exclude_categories.extend([MEAT, POULTRY, DELI])
                if exclude_fish:
                    exclude_categories.append(FISH)
                if exclude_dairy:
                    exclude_categories.append(DAIRY)

                # Build balance dict - IMPORTANT: sync with exclude flags!
                # If exclude_meat is True, force balance to 0 regardless of DB value
                # Note: Use 'is not None' instead of 'or' to preserve 0.0 values
                # Values are raw counts (0-4), normalized internally when used
                balance = {
                    MEAT: 0 if exclude_meat else (float(result[5]) if result[5] is not None else 3),
                    FISH: 0 if exclude_fish else (float(result[6]) if result[6] is not None else 3),
                    VEGETARIAN: float(result[7]) if result[7] is not None else 3,
                    'smart_buy': float(result[8]) if result[8] is not None else 3
                }

                return {
                    'exclude_categories': exclude_categories,
                    'exclude_keywords': result[3] or [],
                    'local_meat_only': result[4] if result[4] is not None else True,
                    'balance': balance,
                    'filtered_products': result[9] or [],
                    'excluded_brands': result[10] or [],
                    'ranking_mode': result[11] or 'absolute',
                    'min_ingredients': int(result[12] or 0),
                    'max_ingredients': int(result[13] or 0)
                }

    except Exception as e:
        logger.warning(f"Could not fetch matching preferences from database: {e}")

    return None


def get_effective_matching_preferences() -> Dict:
    """Return DB preferences, falling back to the shared defaults."""
    return get_matching_preferences_from_db() or get_default_matching_preferences()


def get_enabled_recipe_sources() -> Set[str]:
    """
    Get the list of enabled recipe source names from the database.
    Returns a set of source_name values that are enabled in recipe_sources.
    """
    enabled_sources = set()
    try:
        with get_db_session() as db:
            # Get enabled sources from recipe_sources table
            result = db.execute(text("""
                SELECT name FROM recipe_sources WHERE enabled = true
            """))
            db_enabled = {row.name for row in result}

            # Also get the actual source_names used in found_recipes
            # (they might differ, e.g., "Zeta" vs "Zeta.nu")
            result = db.execute(text("""
                SELECT DISTINCT source_name FROM found_recipes
            """))
            actual_sources = {row.source_name for row in result}

            # Match enabled sources to actual source_names
            for source in actual_sources:
                # Check if source or its base name is enabled
                if source in db_enabled:
                    enabled_sources.add(source)
                else:
                    # Try matching base name (e.g., "Zeta" matches "Zeta.nu")
                    for enabled in db_enabled:
                        if enabled.split('.')[0] == source or source.split('.')[0] == enabled.split('.')[0]:
                            enabled_sources.add(source)
                            break

            # If no matches found in recipe_sources, assume all are enabled
            if not enabled_sources and actual_sources:
                enabled_sources = actual_sources

    except Exception as e:
        logger.warning(f"Could not fetch enabled recipe sources: {e}")
        # On error, return empty set (will match all)

    return enabled_sources


def analyze_unmatched_offers() -> dict:
    """
    Analyze all offers and report why each is filtered out or unmatched.

    Runs the same filter pipeline as _get_filtered_offers but tracks
    the reason each offer was removed. For offers that pass all filters,
    checks if they appear in the recipe_offer_cache.

    Returns dict with: total, matched, filtered (list), unmatched (list), stats
    """
    preferences = get_effective_matching_preferences()

    from cache_manager import cache_manager as _cm
    matched_offer_ids = _cm.get_matched_offer_ids()
    return analyze_unmatched_offers_backend(preferences, matched_offer_ids)


class RecipeMatcher:
    """
    Match recipes against sale offers with improved classification.

    v4 Update: Uses PostgreSQL Full-Text Search for 10x faster matching.
    v5 Update: Uses pre-computed cache for <1s page loads.
    """

    # Flag to enable/disable FTS (for testing)
    USE_FTS = True

    # Flag to enable/disable cache (set False to always compute live)
    USE_CACHE = True

    def __init__(self):
        classification_keywords = get_classification_keywords_backend()
        self.meat_keywords = classification_keywords['meat']
        self.fish_keywords = classification_keywords['fish']

        # Pre-compile classification regex patterns (major performance win)
        # Split keywords by length: short (<= 2 chars) need word boundaries, longer just need word-start
        self._meat_patterns_compiled = self._build_keyword_patterns(self.meat_keywords)
        self._fish_patterns_compiled = self._build_keyword_patterns(self.fish_keywords)

    def _build_keyword_patterns(self, keywords: List[str]) -> Dict:
        """Pre-compile locale-aware classification patterns via the matcher backend."""
        return build_keyword_patterns_backend(keywords)

    def _keyword_match_fast(self, text: str, patterns: Dict) -> list:
        """Fast locale-aware keyword matching via the matcher backend."""
        return keyword_match_fast_backend(text, patterns)

    def _has_keyword_match(self, text: str, patterns: Dict) -> bool:
        """Fast locale-aware keyword existence check via the matcher backend."""
        return has_keyword_match_backend(text, patterns)

    def _get_recipes_by_fts(
        self,
        keywords: List[str],
        enabled_sources: set
    ) -> List[FoundRecipe]:
        """
        Use PostgreSQL Full-Text Search to quickly find recipes matching keywords.

        This is ~10-50x faster than loading all recipes and doing Python string matching.

        Args:
            keywords: List of keywords from offers (e.g., ['lax', 'kyckling', 'potatis'])
            enabled_sources: Set of enabled source names

        Returns:
            List of FoundRecipe objects that match at least one keyword
        """
        if not keywords:
            return []

        # Build tsquery: 'lax | kyckling | potatis'
        # Clean keywords: remove very short ones and special chars
        clean_keywords = []
        for kw in keywords:
            kw = kw.strip().lower()
            if len(kw) >= 3 and kw.isalpha():
                clean_keywords.append(kw)

        if not clean_keywords:
            return []

        # Sort to ensure deterministic results (keywords come from a set)
        clean_keywords = sorted(clean_keywords)

        tsquery_str = ' | '.join(clean_keywords)
        fts_config = get_recipe_fts_config_backend()

        with get_db_session() as db:
            # Use raw SQL for FTS query (always exclude hidden recipes)
            if enabled_sources:
                # Build parameterized IN clause to prevent SQL injection
                source_params = {f"src_{i}": s for i, s in enumerate(enabled_sources)}
                source_placeholders = ', '.join(f":{k}" for k in source_params)
                sql = text(f"""
                    SELECT * FROM found_recipes
                    WHERE search_vector @@ to_tsquery(CAST(:fts_config AS regconfig), :query)
                    AND source_name IN ({source_placeholders})
                    AND (excluded = FALSE OR excluded IS NULL)
                """)
                params = {"query": tsquery_str, "fts_config": fts_config, **source_params}
            else:
                sql = text("""
                    SELECT * FROM found_recipes
                    WHERE search_vector @@ to_tsquery(CAST(:fts_config AS regconfig), :query)
                    AND (excluded = FALSE OR excluded IS NULL)
                """)
                params = {"query": tsquery_str, "fts_config": fts_config}

            result = db.execute(sql, params)
            rows = result.fetchall()

            # Convert to FoundRecipe objects
            recipes = []
            for row in rows:
                recipe = FoundRecipe(
                    id=row.id,
                    source_name=row.source_name,
                    name=row.name,
                    url=row.url,
                    image_url=row.image_url,
                    local_image_path=row.local_image_path,
                    ingredients=row.ingredients,
                    prep_time_minutes=row.prep_time_minutes,
                    servings=row.servings,
                    matching_offer_ids=row.matching_offer_ids,
                    match_score=row.match_score,
                    estimated_savings=row.estimated_savings,
                    scraped_at=row.scraped_at,
                    excluded=row.excluded,
                )
                recipes.append(recipe)

            return recipes
    
    
    def match_all_recipes(
        self,
        preferences: Optional[Dict] = None,
        max_results: int = 20,
        exclude_ids: Optional[List[str]] = None,
        offset: int = 0
    ) -> List[Dict]:
        """
        Match ALL recipes against sale offers and return top N.

        Args:
            preferences: User preferences dict
            max_results: Max number of recipes to return (default 20)
            exclude_ids: Recipe IDs already shown to client (for pagination)

        Returns:
            List of top recipes sorted by score + balance
        """

        logger.info(f"🔍 Matching all recipes against offers (exclude={len(exclude_ids or [])})...")

        # TRY CACHE FIRST (v5 optimization)
        if self.USE_CACHE:
            try:
                from cache_manager import cache_manager

                if cache_manager.is_cache_valid():
                    logger.info("  ⚡ Using pre-computed cache...")
                    cached_result = cache_manager.get_cached_recipes(
                        preferences=preferences,
                        max_results=max_results,
                        exclude_ids=exclude_ids
                    )
                    if cached_result is not None:
                        logger.success(f"✅ Cache hit: {len(cached_result)} recipes")
                        return cached_result
                    else:
                        logger.info("  Cache returned None, falling back to live computation")
                else:
                    logger.info("  Cache not ready, using live computation")
            except Exception as e:
                logger.warning(f"  Cache error: {e}, falling back to live computation")

        # If no preferences provided, try to load from database
        if not preferences:
            preferences = get_effective_matching_preferences()
            logger.info("  Loaded effective matching preferences")

        # Get enabled recipe sources (only match recipes from active sources)
        enabled_sources = get_enabled_recipe_sources()

        # Get all sale offers (filtered)
        offers = self._get_filtered_offers(preferences)
        logger.info(f"  Found {len(offers)} matching offers")

        if not offers:
            logger.warning("⚠️  No offers found matching preferences!")
            return []

        # Pre-extract keywords for all offers ONCE (optimization)
        offer_keywords = {
            id(offer): extract_keywords_from_product(offer.name, offer.category, brand=offer.brand)
            for offer in offers
        }

        # Collect all unique keywords for FTS
        all_keywords = set()
        for keywords in offer_keywords.values():
            all_keywords.update(keywords)
        logger.debug(f"  Extracted {len(all_keywords)} unique keywords from offers")

        # Use FTS to pre-filter recipes (MUCH faster)
        if self.USE_FTS and all_keywords:
            import time
            fts_start = time.perf_counter()

            all_recipes = self._get_recipes_by_fts(list(all_keywords), enabled_sources)

            fts_time = time.perf_counter() - fts_start
            logger.info(f"  ⚡ FTS found {len(all_recipes)} matching recipes in {fts_time:.2f}s")
        else:
            # Fallback: load all recipes (slower)
            with get_db_session() as db:
                if enabled_sources:
                    all_recipes = db.query(FoundRecipe).filter(
                        FoundRecipe.source_name.in_(enabled_sources)
                    ).all()
                    logger.info(f"  Found {len(all_recipes)} recipes from {len(enabled_sources)} active sources")
                else:
                    all_recipes = db.query(FoundRecipe).all()
                    logger.info(f"  Found {len(all_recipes)} recipes in database (all sources)")

        # Filter out already-shown recipes (for "load more" pagination)
        if exclude_ids:
            exclude_set = set(str(eid) for eid in exclude_ids)
            all_recipes = [r for r in all_recipes if str(r.id) not in exclude_set]
            logger.info(f"  Excluded {len(exclude_ids)} already-shown recipes, {len(all_recipes)} remain")

        # Match each recipe (now with FTS pre-filtering, this is much faster)
        matched_recipes = []

        for recipe in all_recipes:
            # Skip boring "how to cook X" recipes
            if is_boring_recipe(recipe.name):
                continue

            match_result = self._match_recipe_to_offers(recipe, offers, preferences, offer_keywords)

            if match_result['num_matches'] > 0:
                matched_recipes.append({
                    'recipe': recipe,
                    'match_data': match_result
                })
        
        logger.info(f"  ✅ {len(matched_recipes)} recipes matched with offers")
        
        # Rank and balance
        all_top_recipes = self._rank_and_balance(matched_recipes, preferences, max_results + offset)
        
        # Apply pagination (skip first 'offset' recipes)
        paginated_recipes = all_top_recipes[offset:offset + max_results]
        
        logger.success(f"✅ Returning {len(paginated_recipes)} recipes (offset={offset})")
        
        return paginated_recipes
    
    
    def _get_filtered_offers(self, preferences: Dict) -> List[Offer]:
        """Get sale offers filtered by the active language/country backend."""
        return get_filtered_offers_backend(preferences)
    
    
    def _match_recipe_to_offers(
        self,
        recipe: FoundRecipe,
        offers: List[Offer],
        preferences: Dict,
        offer_keywords: Optional[Dict] = None,
        offer_data_cache: Optional[Dict] = None,
        prepared_recipe_data: Optional[Dict] = None,
        compiled_recipe_data: Optional[Dict] = None,
        ingredient_candidate_indices_by_offer: Optional[Dict[str, set[int]]] = None,
        ingredient_routing_mode: str = "off",
    ) -> Dict:
        """Dispatch recipe matching through the active language/country backend."""
        return match_recipe_to_offers_backend(
            self,
            recipe,
            offers,
            preferences,
            offer_keywords,
            offer_data_cache,
            prepared_recipe_data,
            compiled_recipe_data,
            ingredient_candidate_indices_by_offer,
            ingredient_routing_mode,
        )

    def _rank_and_balance(
        self,
        matched_recipes: List[Dict],
        preferences: Dict,
        max_results: int
    ) -> List[Dict]:
        """
        Rank recipes and balance between 4 categories.

        Budget scoring: Formula 3 (Coverage × Savings × Matches)
        """

        # Default balance (if not specified) - raw counts, normalized internally
        default_balance = {
            MEAT: 3,
            FISH: 3,
            VEGETARIAN: 3,
            'smart_buy': 3
        }

        balance = preferences.get('balance', default_balance).copy()

        # IMPORTANT: Respect exclude_categories by forcing weight to 0
        exclude_cats = preferences.get('exclude_categories', [])

        # Map exclude_categories to balance keys
        # exclude_categories uses DB categories like MEAT, POULTRY, DELI, FISH, DAIRY
        # balance uses display categories like MEAT, FISH, VEGETARIAN
        if any(cat in exclude_cats for cat in [MEAT, POULTRY, DELI]):
            balance[MEAT] = 0
            logger.debug("  Forced meat balance to 0 (excluded)")
        if FISH in exclude_cats:
            balance[FISH] = 0
            logger.debug("  Forced fish balance to 0 (excluded)")

        # HARD excluded = checkbox exclude (completely filtered out)
        hard_excluded_cats = set()
        if any(cat in exclude_cats for cat in [MEAT, POULTRY, DELI]):
            hard_excluded_cats.add(MEAT)
        if FISH in exclude_cats:
            hard_excluded_cats.add(FISH)

        # SOFT excluded = balance is 0 (don't pick from category, but allow in budget pool)
        # UNLESS smart_buy is the only category with weight > 0
        soft_excluded_cats = set()
        # Use threshold < 0.01 to handle floating point (0% = 0.00, but 1% = 0.01)
        budget_only_mode = (
            balance.get('smart_buy', 0) >= 0.01 and
            balance.get(MEAT, 0) < 0.01 and
            balance.get(FISH, 0) < 0.01 and
            balance.get(VEGETARIAN, 0) < 0.01
        )

        if not budget_only_mode:
            # Normal mode: 0% balance = exclude from results entirely
            # Use threshold < 0.01 to handle floating point (0% = 0.00, but 1% = 0.01)
            if balance.get(MEAT, 0) < 0.01 and MEAT not in hard_excluded_cats:
                soft_excluded_cats.add(MEAT)
            if balance.get(FISH, 0) < 0.01 and FISH not in hard_excluded_cats:
                soft_excluded_cats.add(FISH)
            if balance.get(VEGETARIAN, 0) < 0.01:
                soft_excluded_cats.add(VEGETARIAN)

        logger.info(f"  Balance weights: {balance}")
        logger.info(f"  Hard excluded: {hard_excluded_cats}, Soft excluded: {soft_excluded_cats}")

        # Group by category
        by_category = {
            MEAT: [],
            FISH: [],
            VEGETARIAN: [],
            'smart_buy': []  # Will contain all non-excluded recipes
        }

        for item in matched_recipes:
            cat = item['match_data']['recipe_category']
            match_data = item['match_data']

            # Skip recipes from HARD excluded categories (checkbox = never show)
            if cat in hard_excluded_cats:
                continue

            # Skip recipes from SOFT excluded categories (0% balance = don't show)
            # EXCEPT in budget_only_mode where all recipes compete
            if cat in soft_excluded_cats:
                continue

            # Calculate scores
            savings_score = match_data['total_savings']
            budget_score = match_data['budget_score']

            # Add to primary category
            by_category[cat].append({
                'recipe': item['recipe'],
                'match_data': match_data,
                'savings_score': savings_score,
                'budget_score': budget_score
            })

            # Also add to smart_buy pool
            by_category['smart_buy'].append({
                'recipe': item['recipe'],
                'match_data': match_data,
                'savings_score': savings_score,
                'budget_score': budget_score
            })
        
        # Sort each category by appropriate metric
        ranking_mode = preferences.get('ranking_mode', 'absolute')
        if ranking_mode == 'percentage':
            sort_key = lambda x: x['match_data'].get('total_savings_pct', 0)
        else:
            sort_key = lambda x: x['savings_score']
        by_category[MEAT].sort(key=sort_key, reverse=True)
        by_category[FISH].sort(key=sort_key, reverse=True)
        by_category[VEGETARIAN].sort(key=sort_key, reverse=True)
        by_category['smart_buy'].sort(key=lambda x: x['budget_score'], reverse=True)

        # Calculate how many to take from each category
        # Step 1: Get active categories (weight >= 1%)
        active_cats = []
        for cat in [MEAT, FISH, VEGETARIAN, 'smart_buy']:
            weight = balance.get(cat, 0)
            if weight >= 0.01:  # At least 1% to be active
                active_cats.append((cat, weight))

        if not active_cats:
            logger.warning("No active categories - using default balance")
            active_cats = [(MEAT, 0.25), (FISH, 0.25), (VEGETARIAN, 0.25), ('smart_buy', 0.25)]

        # Step 2: Normalize weights to sum to 1.0
        total_weight = sum(w for _, w in active_cats)
        normalized = [(cat, w / total_weight) for cat, w in active_cats]

        # Step 3: Calculate exact num_to_take for each category
        # Use proportional allocation with remainder distribution
        num_to_take = {}
        remaining = max_results

        for cat, norm_weight in normalized:
            count = int(max_results * norm_weight)
            num_to_take[cat] = count
            remaining -= count

        # Distribute remainder to categories with highest fractional parts
        # Tie-break: prefer category with higher original weight
        if remaining > 0 and normalized:
            fractional = [(cat, (max_results * w) - int(max_results * w), w) for cat, w in normalized]
            fractional.sort(key=lambda x: (x[1], x[2]), reverse=True)
            for i in range(remaining):
                cat = fractional[i % len(fractional)][0]
                num_to_take[cat] += 1

        # Fairness fix: equal-weight categories should get equal counts.
        # If 3+ categories share the same weight but got unequal counts,
        # move the excess to the highest-weight category instead.
        weight_groups = {}
        for cat, w in normalized:
            raw_w = balance.get(cat, 0)
            weight_groups.setdefault(raw_w, []).append(cat)

        for raw_w, group in weight_groups.items():
            if len(group) < 3:
                continue
            min_count = min(num_to_take.get(c, 0) for c in group)
            excess = 0
            for c in group:
                excess += num_to_take[c] - min_count
                num_to_take[c] = min_count
            if excess > 0:
                # Give excess to highest-weight category
                highest_cat = max(normalized, key=lambda x: x[1])[0]
                num_to_take[highest_cat] += excess

        logger.info(f"  Category allocation: {num_to_take}")

        # Step 4: Pick recipes from each category
        result = []
        taken_ids = set()

        for cat in [MEAT, FISH, VEGETARIAN]:
            count = num_to_take.get(cat, 0)
            if count == 0:
                continue

            for item in by_category[cat]:
                if len([r for r in result if r.get('_cat') == cat]) >= count:
                    break

                recipe_id = str(item['recipe'].id)
                if recipe_id in taken_ids:
                    continue

                item['_cat'] = cat  # Track which category this came from
                result.append(item)
                taken_ids.add(recipe_id)

        # Pick from smart_buy (only recipes not already picked)
        budget_count = num_to_take.get('smart_buy', 0)
        if budget_count > 0:
            picked = 0
            for item in by_category['smart_buy']:
                if picked >= budget_count:
                    break

                recipe_id = str(item['recipe'].id)
                if recipe_id in taken_ids:
                    continue

                # Mark as budget pick
                budget_item = item.copy()
                budget_item['match_data'] = item['match_data'].copy()
                budget_item['match_data']['recipe_category'] = 'smart_buy'
                budget_item['match_data']['display_category'] = 'smart_buy'
                budget_item['_cat'] = 'smart_buy'

                result.append(budget_item)
                taken_ids.add(recipe_id)
                picked += 1

        # Step 5: Interleave for nice display order
        # Group by category, then interleave
        by_cat_result = {cat: [] for cat in [MEAT, FISH, VEGETARIAN, 'smart_buy']}
        for item in result:
            cat = item.get('_cat', item['match_data']['recipe_category'])
            by_cat_result[cat].append(item)

        # Interleave: take 1 from each category in rotation
        interleaved = []
        indices = {cat: 0 for cat in by_cat_result}
        while len(interleaved) < len(result):
            added = False
            for cat in [MEAT, FISH, VEGETARIAN, 'smart_buy']:
                idx = indices[cat]
                if idx < len(by_cat_result[cat]):
                    interleaved.append(by_cat_result[cat][idx])
                    indices[cat] += 1
                    added = True
            if not added:
                break

        result = interleaved
        
        # Format output
        formatted = []
        for item in result:
            recipe = item['recipe']
            match_data = item['match_data']
            
            formatted.append({
                'id': str(recipe.id),
                'name': recipe.name,
                'url': recipe.url,
                'source': recipe.source_name,
                'image_url': recipe.local_image_path or recipe.image_url,  # Prefer local image
                'ingredients': recipe.ingredients or [],
                'prep_time_minutes': recipe.prep_time_minutes,
                'category': match_data.get('display_category', match_data['recipe_category']),
                'match_score': match_data['match_score'],
                'total_savings': match_data['total_savings'],
                'num_matches': match_data['num_matches'],
                'num_offers': match_data.get('num_offers', len(match_data['matched_offers'])),
                'matched_offers': match_data['matched_offers'],
                'coverage_pct': match_data['coverage_pct'],
                'budget_score': match_data['budget_score'],
                'ingredient_groups': match_data.get('ingredient_groups', [])  # New: alternatives grouped
            })
        
        return formatted
    
    


# Global instance
recipe_matcher = RecipeMatcher()


# ============================================================================
# CLI TEST
# ============================================================================

if __name__ == "__main__":
    import argparse
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Recipe Matcher - Match recipes against sale offers')
    
    # Exclusion flags
    parser.add_argument('--exclude-meat', action='store_true', help='Exclude meat/poultry recipes')
    parser.add_argument('--exclude-fish', action='store_true', help='Exclude fish/seafood recipes')
    parser.add_argument('--exclude-dairy', action='store_true', help='Exclude dairy products')
    parser.add_argument('--exclude-keywords', type=str, help='Comma-separated list of ingredients to exclude (e.g., milk,eggs,gluten)')
    parser.add_argument('--no-local-meat', action='store_true', help='Allow imported meat (default: local only)')
    
    # Balance weights
    parser.add_argument('--balance-meat', type=float, default=0.25, help='Weight for meat category (0.0-1.0)')
    parser.add_argument('--balance-fish', type=float, default=0.25, help='Weight for fish category (0.0-1.0)')
    parser.add_argument('--balance-veg', type=float, default=0.25, help='Weight for vegetarian category (0.0-1.0)')
    parser.add_argument('--balance-budget', type=float, default=0.25, help='Weight for budget category (0.0-1.0)')
    
    # Output options
    parser.add_argument('--max-results', type=int, default=20, help='Number of recipes to return')
    parser.add_argument('--offset', type=int, default=0, help='Skip first N recipes (for pagination)')
    parser.add_argument('--json', action='store_true', help='Output as JSON instead of table')

    # Benchmark mode
    parser.add_argument('--benchmark', action='store_true', help='Run performance benchmark')
    
    args = parser.parse_args()
    
    # Build preferences from arguments
    preferences = {
        'exclude_categories': [],
        'exclude_keywords': [],
        'local_meat_only': not args.no_local_meat,
        'balance': {
            MEAT: args.balance_meat,
            FISH: args.balance_fish,
            VEGETARIAN: args.balance_veg,
            'smart_buy': args.balance_budget
        }
    }
    
    # Add exclusions
    if args.exclude_meat:
        preferences['exclude_categories'].append(MEAT)
        preferences['exclude_categories'].append(POULTRY)
        preferences['exclude_categories'].append(DELI)
        preferences['balance'][MEAT] = 0.0
    
    if args.exclude_fish:
        preferences['exclude_categories'].append(FISH)
        preferences['balance'][FISH] = 0.0
    
    if args.exclude_dairy:
        preferences['exclude_categories'].append(DAIRY)
    
    if args.exclude_keywords:
        keywords = [kw.strip() for kw in args.exclude_keywords.split(',')]
        preferences['exclude_keywords'] = keywords

    # Benchmark mode
    if args.benchmark:
        import time
        from database import get_db_session

        console.print("\n[bold blue]📊 Recipe Matcher Benchmark[/bold blue]\n")

        # Get counts
        with get_db_session() as db:
            recipe_count = db.execute(text("SELECT COUNT(*) FROM found_recipes")).scalar()
            offer_count = db.execute(text("SELECT COUNT(*) FROM offers WHERE savings > 0")).scalar()

        console.print("[cyan]Dataset:[/cyan]")
        console.print(f"  Recipes: {recipe_count:,}")
        console.print(f"  Offers: {offer_count:,}")
        console.print()

        # Run benchmark
        matcher = RecipeMatcher()
        test_sizes = [100, 500, 1000, 2000, 5000, 10000, 20000, 40000]
        test_sizes = [s for s in test_sizes if s <= recipe_count]

        if not test_sizes:
            test_sizes = [recipe_count]

        results = []
        console.print("[yellow]Running benchmarks...[/yellow]\n")

        for size in test_sizes:
            # Time the matching
            start = time.perf_counter()

            with get_db_session() as db:
                # Load limited recipes
                recipes = db.execute(
                    text("SELECT * FROM found_recipes LIMIT :limit"),
                    {"limit": size}
                ).fetchall()

                # Load offers
                from models import Offer
                offers = db.query(Offer).filter(Offer.savings > 0).all()

                # Extract keywords once
                offer_keywords = {}
                for offer in offers:
                    offer_keywords[id(offer)] = extract_keywords_from_product(offer.name, offer.category, brand=offer.brand)

                # Simulate matching loop (without full processing)
                match_count = 0
                for row in recipes:
                    recipe_text = (row.name or '').lower()
                    for offer in offers:
                        keywords = offer_keywords.get(id(offer), [])
                        for kw in keywords:
                            if kw in recipe_text:
                                match_count += 1
                                break

            elapsed = time.perf_counter() - start
            rate = size / elapsed if elapsed > 0 else 0

            results.append({
                'recipes': size,
                'time': elapsed,
                'rate': rate
            })

            console.print(f"  {size:>6,} recipes: {elapsed:.2f}s ({rate:,.0f} recipes/sec)")

        # Summary
        console.print()
        console.print("[bold green]📈 Results Summary[/bold green]")

        # Extrapolate to 40k
        if results:
            last = results[-1]
            if last['recipes'] < 40000:
                estimated_40k = 40000 / last['rate'] if last['rate'] > 0 else 999
                console.print(f"  Estimated time for 40,000 recipes: {estimated_40k:.1f}s")

                if estimated_40k > 3:
                    console.print("  [red]⚠️  >3s - Consider FTS optimization[/red]")
                else:
                    console.print("  [green]✅ <3s - Current approach is fine[/green]")
            else:
                if last['time'] > 3:
                    console.print(f"  [red]⚠️  {last['time']:.1f}s >3s - Consider FTS optimization[/red]")
                else:
                    console.print(f"  [green]✅ {last['time']:.1f}s <3s - Performance is good[/green]")

        console.print()
        exit(0)

    # Match recipes
    if not args.json:
        console.print("\n[bold blue]🧪 Recipe Matcher v3[/bold blue]\n")
        console.print("[yellow]Preferences:[/yellow]")
        console.print(f"  Local meat only: {preferences['local_meat_only']}")
        console.print(f"  Exclude categories: {preferences['exclude_categories']}")
        console.print(f"  Exclude keywords: {preferences['exclude_keywords']}")
        console.print(f"  Balance: {preferences['balance']}\n")
    
    matcher = RecipeMatcher()
    top_recipes = matcher.match_all_recipes(
        preferences, 
        max_results=args.max_results,
        offset=args.offset
    )
    
    # Output
    if args.json:
        import json
        print(json.dumps(top_recipes, indent=2, ensure_ascii=False))
    else:
        # Display results
        table = Table(title=f"Top {len(top_recipes)} Recipes")
        table.add_column("Name", style="cyan", no_wrap=False, max_width=35)
        table.add_column("Category", style="magenta", max_width=12)
        table.add_column("Matches", style="green", justify="right")
        table.add_column("Coverage", style="blue", justify="right")
        table.add_column("Savings", style="yellow", justify="right")
        
        for recipe in top_recipes:
            table.add_row(
                recipe['name'][:35],
                recipe['category'],
                str(recipe['num_matches']),
                f"{recipe['coverage_pct']:.0f}%",
                f"{recipe['total_savings']:.0f} kr"
            )
        
        console.print(table)
        console.print()
