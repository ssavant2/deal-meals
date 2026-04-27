"""Swedish recipe matcher backend adapter.

This is intentionally a thin shim in the first extraction step. The goal is to
give shared orchestration code a backend seam without moving the full Swedish
recipe matcher implementation in one risky refactor.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

try:
    from database import get_db_session
    from languages.categories import MEAT, FISH, VEGETARIAN
    from languages.categories import DAIRY
    from languages.sv.category_utils import (
        IMPORTED_COUNTRIES,
        IMPORTED_MEAT_BRANDS,
        IMPORTED_SPECIALTY_EXCEPTIONS,
        MEAT_CATEGORIES,
        MEAT_EXTENDED_CATEGORIES,
        MEAT_NAME_KEYWORDS,
        is_lactose_free,
    )
    from languages.sv.food_filters import (
        NON_FOOD_BRANDS,
        VEG_PRODUCT_INDICATORS,
        VEG_QUALIFIER_WORDS,
        is_cooking_chips,
        is_cooking_chocolate,
        is_cooking_nuts,
    )
    from languages.sv.ingredient_matching import (
        BITAR_WORD,
        BULJONG_DEFAULT_WORDS,
        BULJONG_TYPE_PREFIXES,
        BULJONG_WORD,
        CHEESE_CONTEXT,
        CUISINE_CONTEXT,
        DRIED_PRODUCT_INDICATORS,
        FLAVOR_WORDS,
        FOND_TYPE_CONTEXT,
        FOND_WORD,
        FRESH_HERB_KEYWORDS,
        FRESH_PRODUCT_INDICATORS,
        FRESH_WORDS,
        FROZEN_PRODUCT_INDICATORS,
        HELKALKON_WORD,
        KALKON_WORD,
        KEYWORD_SUPPRESSED_BY_CONTEXT,
        PASTA_KEYWORDS,
        PRODUCT_NAME_BLOCKERS,
        RECIPE_DRIED_INDICATORS,
        RECIPE_DRIED_VOLUME_INDICATORS,
        RECIPE_FRESH_INDICATORS,
        RECIPE_FRESH_VOLUME_INDICATORS,
        RECIPE_FROZEN_INDICATORS,
        RECIPE_INGREDIENT_BLOCKERS,
        MATCHER_VERSION,
        NON_FOOD_CATEGORIES,
        OFFER_COMPILER_VERSION,
        SAFE_SUFFIXES,
        RECIPE_COMPILER_VERSION,
        SEASONING_COMPOUNDS,
        SPARRIS_WORD,
        VEGETARIAN_LABELS,
        _CARRIER_MULTI_WORDS,
        _CARRIER_SINGLE_WORDS,
        _PROCESSED_PRODUCT_INDICATORS,
        check_filmjolk_match,
        check_kvarg_match,
        check_processed_product_rules,
        check_secondary_ingredient_patterns,
        check_spice_vs_fresh_rules,
        check_yoghurt_match,
        build_offer_identity_key,
        resolve_recipe_match_runtime_data,
        extract_keywords_from_product,
    )
    from languages.sv.ingredient_matching.extraction import extract_keywords_from_ingredient
    from languages.sv.ingredient_matching.extraction import is_non_food_product
    from languages.sv.ingredient_matching.matching import precompute_offer_data
    from languages.sv.ingredient_matching.engine import (
        build_precomputed_offer_match_data,
        match_offer_to_ingredient,
    )
    from languages.sv.ingredient_matching.keywords import (
        PROCESSED_FOODS,
        PROCESSED_FOODS_EXEMPTIONS,
    )
    from languages.sv.ingredient_matching.normalization import _apply_space_normalizations
    from languages.sv.ingredient_matching.compound_text import _NON_FOOD_PATTERN
    from languages.sv.ingredient_matching.recipe_matcher_support import (
        KEYWORD_COMPOUND_SUFFIXES,
        PROMOTION_COMPOUND_SUFFIXES,
    )
    from languages.sv.ingredient_matching.recipe_text import has_eller_pattern, parse_eller_alternatives
    from languages.sv.ingredient_matching.synonyms import INGREDIENT_PARENTS
    from languages.sv.ingredient_matching.match_filters import _is_false_positive_blocked
    from languages.sv.ingredient_matching.recipe_context import (
        DESCRIPTOR_SUPPRESSION_PRIMARIES,
        _DESCRIPTOR_PHRASE_MARKERS,
    )
    from languages.sv.ingredient_matching.processed_rules import (
        SPICE_VS_FRESH_RULES,
        STRICT_PROCESSED_RULES,
    )
    from languages.sv.recipe_filters import (
        JUNK_FOOD_KEYWORDS,
        JUNK_FOOD_KEYWORDS_NO_CHOCOLATE,
    )
    from languages.sv.ingredient_matching.specialty_rules import (
        QUALIFIER_EQUIVALENTS,
        SPECIALTY_QUALIFIERS,
    )
    from languages.sv.ingredient_matching.recipe_matcher_support import (
        CHIPS_WORD,
        CLASSIFICATION_FISH_KEYWORDS,
        CLASSIFICATION_MEAT_KEYWORDS,
        SODA_WORD,
    )
    from languages.sv.ingredient_matching.validators import ingredient_has_spice_indicator
    from languages.sv.ingredient_matching.validators import check_specialty_qualifiers
    from languages.sv.normalization import fix_swedish_chars
except ModuleNotFoundError:
    from app.database import get_db_session
    from app.languages.categories import MEAT, FISH, VEGETARIAN
    from app.languages.categories import DAIRY
    from app.languages.sv.category_utils import (
        IMPORTED_COUNTRIES,
        IMPORTED_MEAT_BRANDS,
        IMPORTED_SPECIALTY_EXCEPTIONS,
        MEAT_CATEGORIES,
        MEAT_EXTENDED_CATEGORIES,
        MEAT_NAME_KEYWORDS,
        is_lactose_free,
    )
    from app.languages.sv.food_filters import (
        NON_FOOD_BRANDS,
        VEG_PRODUCT_INDICATORS,
        VEG_QUALIFIER_WORDS,
        is_cooking_chips,
        is_cooking_chocolate,
        is_cooking_nuts,
    )
    from app.languages.sv.ingredient_matching import (
        BITAR_WORD,
        BULJONG_DEFAULT_WORDS,
        BULJONG_TYPE_PREFIXES,
        BULJONG_WORD,
        CHEESE_CONTEXT,
        CUISINE_CONTEXT,
        DRIED_PRODUCT_INDICATORS,
        FLAVOR_WORDS,
        FOND_TYPE_CONTEXT,
        FOND_WORD,
        FRESH_HERB_KEYWORDS,
        FRESH_PRODUCT_INDICATORS,
        FRESH_WORDS,
        FROZEN_PRODUCT_INDICATORS,
        HELKALKON_WORD,
        KALKON_WORD,
        KEYWORD_SUPPRESSED_BY_CONTEXT,
        PASTA_KEYWORDS,
        PRODUCT_NAME_BLOCKERS,
        RECIPE_DRIED_INDICATORS,
        RECIPE_DRIED_VOLUME_INDICATORS,
        RECIPE_FRESH_INDICATORS,
        RECIPE_FRESH_VOLUME_INDICATORS,
        RECIPE_FROZEN_INDICATORS,
        RECIPE_INGREDIENT_BLOCKERS,
        MATCHER_VERSION,
        NON_FOOD_CATEGORIES,
        OFFER_COMPILER_VERSION,
        SAFE_SUFFIXES,
        RECIPE_COMPILER_VERSION,
        SEASONING_COMPOUNDS,
        SPARRIS_WORD,
        VEGETARIAN_LABELS,
        _CARRIER_MULTI_WORDS,
        _CARRIER_SINGLE_WORDS,
        _PROCESSED_PRODUCT_INDICATORS,
        check_filmjolk_match,
        check_kvarg_match,
        check_processed_product_rules,
        check_secondary_ingredient_patterns,
        check_spice_vs_fresh_rules,
        check_yoghurt_match,
        build_offer_identity_key,
        resolve_recipe_match_runtime_data,
        extract_keywords_from_product,
    )
    from app.languages.sv.ingredient_matching.extraction import extract_keywords_from_ingredient
    from app.languages.sv.ingredient_matching.extraction import is_non_food_product
    from app.languages.sv.ingredient_matching.matching import precompute_offer_data
    from app.languages.sv.ingredient_matching.engine import (
        build_precomputed_offer_match_data,
        match_offer_to_ingredient,
    )
    from app.languages.sv.ingredient_matching.keywords import (
        PROCESSED_FOODS,
        PROCESSED_FOODS_EXEMPTIONS,
    )
    from app.languages.sv.ingredient_matching.normalization import _apply_space_normalizations
    from app.languages.sv.ingredient_matching.compound_text import _NON_FOOD_PATTERN
    from app.languages.sv.ingredient_matching.recipe_matcher_support import (
        KEYWORD_COMPOUND_SUFFIXES,
        PROMOTION_COMPOUND_SUFFIXES,
    )
    from app.languages.sv.ingredient_matching.recipe_text import has_eller_pattern, parse_eller_alternatives
    from app.languages.sv.ingredient_matching.synonyms import INGREDIENT_PARENTS
    from app.languages.sv.ingredient_matching.match_filters import _is_false_positive_blocked
    from app.languages.sv.ingredient_matching.recipe_context import (
        DESCRIPTOR_SUPPRESSION_PRIMARIES,
        _DESCRIPTOR_PHRASE_MARKERS,
    )
    from app.languages.sv.ingredient_matching.processed_rules import (
        SPICE_VS_FRESH_RULES,
        STRICT_PROCESSED_RULES,
    )
    from app.languages.sv.recipe_filters import (
        JUNK_FOOD_KEYWORDS,
        JUNK_FOOD_KEYWORDS_NO_CHOCOLATE,
    )
    from app.languages.sv.ingredient_matching.specialty_rules import (
        QUALIFIER_EQUIVALENTS,
        SPECIALTY_QUALIFIERS,
    )
    from app.languages.sv.ingredient_matching.recipe_matcher_support import (
        CHIPS_WORD,
        CLASSIFICATION_FISH_KEYWORDS,
        CLASSIFICATION_MEAT_KEYWORDS,
        SODA_WORD,
    )
    from app.languages.sv.ingredient_matching.validators import ingredient_has_spice_indicator
    from app.languages.sv.ingredient_matching.validators import check_specialty_qualifiers
    from app.languages.sv.normalization import fix_swedish_chars

try:
    from models import FoundRecipe, Offer
except ModuleNotFoundError:
    from app.models import FoundRecipe, Offer

from sqlalchemy.orm import joinedload
import re


SPECIALTY_KEYWORD_ALIASES = {
    'chilipeppar': 'chili',
    'chilifrukt': 'chili',
    'chilifrukter': 'chili',
    'paprikapulver': 'paprika',
    'paprikakrydda': 'paprika',
}

RECIPE_FTS_CONFIG = "swedish"
SAVINGS_CAP_PER_INGREDIENT = 50.0

_RE_GRAM_MEASURE = re.compile(r'\d+\s*g\b')
_RE_CHILI_COUNT_FRESH = re.compile(
    r'\b\d+\s*(?:st\s+)?(?:chili|chilipeppar|chilifrukt|chilifrukter)\b'
)


def _flavor_keyword_blocked_by_carrier_text(ingredient_text: str, matched_keyword: str) -> bool:
    """Return True when a flavor keyword only appears inside carrier wording."""
    carrier_blocked = False
    matching_multi_word_carriers = [
        carrier for carrier in _CARRIER_MULTI_WORDS
        if carrier in ingredient_text
    ]
    matching_multi_word_carriers.sort(
        key=lambda carrier: (
            0 if matched_keyword in carrier.split() else 1,
            -len(carrier),
            carrier,
        )
    )
    for carrier in matching_multi_word_carriers:
        if carrier in ingredient_text:
            carrier_words = set(carrier.split())
            kw_is_carrier_word = matched_keyword in carrier_words
            if not kw_is_carrier_word:
                for carrier_word in carrier_words:
                    if carrier_word.startswith(matched_keyword):
                        suffix = carrier_word[len(matched_keyword):]
                        if suffix in SAFE_SUFFIXES:
                            kw_is_carrier_word = True
                            break
            if not kw_is_carrier_word:
                carrier_blocked = True
            break
    if not carrier_blocked:
        ingredient_words = set(ingredient_text.split())
        if (ingredient_words & _CARRIER_SINGLE_WORDS) - {matched_keyword}:
            carrier_blocked = True
    return carrier_blocked


def match_recipe_to_offers(
    matcher,
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
    """Swedish recipe-offer matching orchestration."""
    prepared_recipe = resolve_recipe_match_runtime_data(
        recipe,
        prepared_recipe_data=prepared_recipe_data,
        compiled_recipe_data=compiled_recipe_data,
    )
    merged_ingredients = prepared_recipe['merged_ingredients']
    ingredient_source_texts = prepared_recipe['ingredient_source_texts']
    ingredient_source_indices = prepared_recipe['ingredient_source_indices']
    ingredients_normalized = prepared_recipe['ingredients_normalized']
    full_recipe_text = prepared_recipe['full_recipe_text']
    ingredient_match_data_per_ing = prepared_recipe['ingredient_match_data_per_ing']

    matched_offers = []
    matched_keywords_set = set()
    ingredient_check_count = 0
    hinted_check_count = 0
    hinted_no_match_count = 0
    fullscan_fallback_count = 0
    fullscan_fallback_reason_counts: dict[str, int] = {}

    def _record_fullscan_fallback(reason: str) -> None:
        nonlocal fullscan_fallback_count
        fullscan_fallback_count += 1
        fullscan_fallback_reason_counts[reason] = (
            fullscan_fallback_reason_counts.get(reason, 0) + 1
        )

    def _validate_selection(initial_match: dict, shadow_events: Optional[list[dict]] = None):
        return validate_offer_match_candidate(
            offer,
            offer_id,
            offer_data_cache,
            initial_match['matched_keyword'],
            initial_match['matched_ing_idx'],
            initial_match['offer_precomputed'],
            initial_match['offer_match_data'],
            initial_match['effective_offer_data'],
            initial_match['offer_match_keywords'],
            initial_match['offer_name_normalized'],
            ingredient_match_data_per_ing,
            ingredients_normalized,
            ingredient_source_texts,
            ingredient_source_indices,
            merged_ingredients,
            full_recipe_text,
            shadow_events,
        )

    for offer in offers:
        offer_id = id(offer)
        use_hint_first = (
            ingredient_routing_mode == "hint_first"
            and ingredient_candidate_indices_by_offer is not None
        )
        offer_identity_key = build_offer_identity_key(offer)
        hinted_indices = (
            ingredient_candidate_indices_by_offer.get(offer_identity_key)
            if use_hint_first
            else None
        )

        if use_hint_first:
            initial_match = prepare_offer_match_candidate(
                offer,
                offer_id,
                offer_keywords,
                offer_data_cache,
                ingredient_match_data_per_ing,
                hinted_indices or set(),
            )
            ingredient_check_count += initial_match['ingredient_check_count']
            hinted_check_count += initial_match['ingredient_check_count']
            fallback_reason = None
            offer_data = None

            if not hinted_indices:
                fallback_reason = "no_hint_for_routed_pair"
            elif not initial_match['matched_keyword'] or initial_match['matched_ing_idx'] is None:
                hinted_no_match_count += 1
            else:
                validation_events: list[dict] = []
                hinted_offer_data = _validate_selection(initial_match, validation_events)
                retry_outside_hint = any(
                    event.get('type') == 'validation_retry'
                    and event.get('to_idx') not in hinted_indices
                    for event in validation_events
                )
                if retry_outside_hint:
                    fallback_reason = "validation_retry_moved_match_outside_hint"
                elif hinted_offer_data:
                    offer_data = hinted_offer_data
                else:
                    fallback_reason = "hinted_validation_rejected"

            if fallback_reason:
                _record_fullscan_fallback(fallback_reason)
                initial_match = prepare_offer_match_candidate(
                    offer,
                    offer_id,
                    offer_keywords,
                    offer_data_cache,
                    ingredient_match_data_per_ing,
                )
                ingredient_check_count += initial_match['ingredient_check_count']
                offer_data = _validate_selection(initial_match)
        else:
            initial_match = prepare_offer_match_candidate(
                offer,
                offer_id,
                offer_keywords,
                offer_data_cache,
                ingredient_match_data_per_ing,
            )
            ingredient_check_count += initial_match['ingredient_check_count']
            offer_data = _validate_selection(initial_match)

        if not offer_data:
            continue
        matched_offers.append(offer_data)
        matched_keyword = offer_data['matched_keyword']
        matched_keywords_set.add(matched_keyword)
        canonical_keyword = INGREDIENT_PARENTS.get(matched_keyword, matched_keyword)
        matched_keywords_set.add(canonical_keyword)

    if not matched_offers:
        return {
            'matched_offers': [],
            'match_score': 0,
            'total_savings': 0,
            'num_matches': 0,
            'num_offers': 0,
            'recipe_category': 'VEGETARIAN',
            'budget_score': 0,
            'coverage_pct': 0,
            'ingredient_groups': [],
            'ingredient_check_count': ingredient_check_count,
            'hinted_check_count': hinted_check_count,
            'hinted_no_match_count': hinted_no_match_count,
            'fullscan_fallback_count': fullscan_fallback_count,
            'fullscan_fallback_reason_counts': fullscan_fallback_reason_counts,
        }

    total_ingredients, ingredient_groups, keyword_to_groups = build_initial_ingredient_groups(
        merged_ingredients,
        ingredients_normalized,
        matched_keywords_set,
        ingredient_match_data_per_ing,
    )

    apply_pre_promotion(matched_offers)
    assign_offers_to_ingredient_groups(
        matched_offers,
        ingredient_groups,
        keyword_to_groups,
        ingredient_match_data_per_ing,
        matched_keywords_set,
    )
    apply_group_keyword_promotion(matched_offers, ingredient_groups)
    merge_exact_group_keywords(matched_offers, ingredient_groups)

    result = finalize_grouped_match_results(
        matcher,
        recipe,
        full_recipe_text,
        matched_offers,
        ingredient_groups,
        ingredients_normalized,
        total_ingredients,
        merged_ingredients,
        SAVINGS_CAP_PER_INGREDIENT,
    )
    result['matcher_version'] = MATCHER_VERSION
    result['recipe_compiler_version'] = RECIPE_COMPILER_VERSION
    result['offer_compiler_version'] = OFFER_COMPILER_VERSION
    result['ingredient_check_count'] = ingredient_check_count
    result['hinted_check_count'] = hinted_check_count
    result['hinted_no_match_count'] = hinted_no_match_count
    result['fullscan_fallback_count'] = fullscan_fallback_count
    result['fullscan_fallback_reason_counts'] = fullscan_fallback_reason_counts
    return result


def get_filtered_offers(preferences: Dict) -> List[Offer]:
    """Return Swedish sale offers filtered by user preferences."""
    with get_db_session() as db:
        food_categories = [
            'meat', 'fish', 'poultry', 'dairy', 'vegetables', 'fruit',
            'bread', 'deli', 'frozen', 'spices', 'pantry', 'pizza', 'other',
        ]

        query = db.query(Offer).options(joinedload(Offer.store)).filter(Offer.category.in_(food_categories))
        all_offers = query.all()

        all_offers = [
            o for o in all_offers
            if 'choklad' not in o.name.lower()
            or is_cooking_chocolate(o.name.lower())
        ]

        candy_cooking = db.query(Offer).options(joinedload(Offer.store)).filter(
            Offer.category == 'candy',
        ).all()
        for offer in candy_cooking:
            name_lower = offer.name.lower()
            if (
                (CHIPS_WORD in name_lower and is_cooking_chips(name_lower))
                or is_cooking_nuts(name_lower)
                or 'marshmallow' in name_lower
                or is_cooking_chocolate(name_lower)
            ):
                all_offers.append(offer)

    filtered = []
    exclude_cats = preferences.get('exclude_categories', [])
    exclude_keywords = preferences.get('exclude_keywords', [])
    filtered_products = preferences.get('filtered_products', [])
    local_meat_only = preferences.get('local_meat_only', True)
    excluded_brands = preferences.get('excluded_brands', [])

    for offer in all_offers:
        name_lower = offer.name.lower()

        if not offer.savings or offer.savings <= 0:
            continue

        if offer.category in exclude_cats:
            if offer.category == DAIRY and is_lactose_free(offer.name):
                pass
            else:
                continue

        if local_meat_only:
            in_meat_cat = offer.category in MEAT_CATEGORIES
            meat_keywords_in_name = any(kw in name_lower for kw in MEAT_NAME_KEYWORDS)
            in_extended = offer.category in MEAT_EXTENDED_CATEGORIES and meat_keywords_in_name

            if in_meat_cat or in_extended:
                is_specialty = any(s in name_lower for s in IMPORTED_SPECIALTY_EXCEPTIONS)
                if is_specialty:
                    pass
                elif any(re.search(r'\b' + re.escape(country) + r'\b', name_lower) for country in IMPORTED_COUNTRIES):
                    continue
                elif any(re.search(r'\b' + re.escape(brand) + r'\b', name_lower) for brand in IMPORTED_MEAT_BRANDS):
                    continue

        if any(re.search(r'\b' + re.escape(keyword.lower()) + r'\b', name_lower) for keyword in exclude_keywords):
            continue

        if any(re.search(r'\b' + re.escape(product_keyword.lower()) + r'\b', name_lower) for product_keyword in filtered_products):
            continue

        if excluded_brands and offer.brand:
            offer_brand_upper = offer.brand.upper()
            if any(excl.upper() == offer_brand_upper for excl in excluded_brands):
                continue

        if offer.brand and offer.brand.lower() in NON_FOOD_BRANDS:
            continue

        name_normalized = fix_swedish_chars(offer.name).lower()
        skip_processed = False
        for processed_keyword in PROCESSED_FOODS:
            keyword_normalized = fix_swedish_chars(processed_keyword).lower()
            if re.search(r'\b' + re.escape(keyword_normalized) + r'\b', name_normalized):
                skip_processed = not any(
                    re.search(r'\b' + re.escape(exemption) + r'\b', name_normalized)
                    for exemption in PROCESSED_FOODS_EXEMPTIONS
                )
                break
        if skip_processed:
            continue

        if CHIPS_WORD in name_lower and not is_cooking_chips(name_lower):
            continue

        if re.search(r'\b' + re.escape(SODA_WORD) + r'\b', name_lower):
            continue

        if any(re.search(r'\b' + re.escape(bad) + r'\b', name_lower) for bad in JUNK_FOOD_KEYWORDS_NO_CHOCOLATE):
            continue

        if is_non_food_product(offer.name, offer.category):
            continue

        filtered.append(offer)

    return filtered


def build_keyword_patterns(keywords: List[str]) -> Dict:
    """Build locale-aware keyword regexes for Swedish recipe classification."""
    long_keywords = [kw for kw in keywords if len(kw) >= 3]
    short_keywords = [kw for kw in keywords if len(kw) <= 2]

    long_pattern = None
    if long_keywords:
        escaped = [re.escape(keyword) for keyword in long_keywords]
        long_pattern = re.compile(
            r'(?<![a-zåäöA-ZÅÄÖ])(' + '|'.join(escaped) + ')',
            re.IGNORECASE,
        )

    short_pattern = None
    if short_keywords:
        escaped = [re.escape(keyword) for keyword in short_keywords]
        short_pattern = re.compile(
            r'(?<![a-zåäöA-ZÅÄÖ])(' + '|'.join(escaped) + r')(?![a-zåäöA-ZÅÄÖ])',
            re.IGNORECASE,
        )

    return {
        'combined_long': long_pattern,
        'combined_short': short_pattern,
        'keywords_long': long_keywords,
        'keywords_short': short_keywords,
    }


def keyword_match_fast(text: str, patterns: Dict) -> list:
    """Fast locale-aware keyword matching using precompiled backend regexes."""
    matches = []

    if patterns['combined_long']:
        found = patterns['combined_long'].findall(text)
        if found:
            matches.extend(found)

    if patterns['combined_short']:
        found = patterns['combined_short'].findall(text)
        if found:
            matches.extend(found)

    return [match.lower() for match in matches]


def has_keyword_match(text: str, patterns: Dict) -> bool:
    """Fast locale-aware keyword existence check."""
    if patterns['combined_long'] and patterns['combined_long'].search(text):
        return True
    if patterns['combined_short'] and patterns['combined_short'].search(text):
        return True
    return False


def analyze_unmatched_offers(preferences: Dict, matched_offer_ids: set[str]) -> dict:
    """Analyze Swedish offers and explain why they were filtered or left unmatched."""
    food_categories = [
        'meat', 'fish', 'poultry', 'dairy', 'vegetables',
        'fruit', 'bread', 'deli', 'frozen', 'other',
    ]
    with get_db_session() as db:
        all_offers = db.query(Offer).options(
            joinedload(Offer.store)
        ).filter(Offer.category.in_(food_categories)).all()

    exclude_cats = preferences.get('exclude_categories', [])
    exclude_keywords = preferences.get('exclude_keywords', [])
    filtered_products = preferences.get('filtered_products', [])
    excluded_brands = preferences.get('excluded_brands', [])
    local_meat_only = preferences.get('local_meat_only', True)

    filtered_list = []
    passed_offers = []
    stats = {}

    def add_filtered(offer, reason, detail=""):
        filtered_list.append({
            "name": offer.name,
            "price": float(offer.price) if offer.price else 0,
            "savings": float(offer.savings) if offer.savings else 0,
            "category": offer.category or "",
            "brand": offer.brand or "",
            "reason": reason,
            "detail": detail,
        })
        stats[reason] = stats.get(reason, 0) + 1

    for offer in all_offers:
        name_lower = offer.name.lower()

        if not offer.savings or offer.savings <= 0:
            continue

        if offer.category in exclude_cats:
            if offer.category == DAIRY and is_lactose_free(offer.name):
                pass
            else:
                add_filtered(offer, "category_excluded", offer.category)
                continue

        if local_meat_only:
            in_meat_cat = offer.category in MEAT_CATEGORIES
            meat_keywords_in_name = any(kw in name_lower for kw in MEAT_NAME_KEYWORDS)
            in_extended = offer.category in MEAT_EXTENDED_CATEGORIES and meat_keywords_in_name
            if in_meat_cat or in_extended:
                is_specialty = any(s in name_lower for s in IMPORTED_SPECIALTY_EXCEPTIONS)
                if not is_specialty:
                    matched_country = next(
                        (
                            country for country in IMPORTED_COUNTRIES
                            if re.search(r'\b' + re.escape(country) + r'\b', name_lower)
                        ),
                        None,
                    )
                    if matched_country:
                        add_filtered(offer, "local_meat", matched_country)
                        continue
                    matched_brand = next(
                        (
                            brand for brand in IMPORTED_MEAT_BRANDS
                            if re.search(r'\b' + re.escape(brand) + r'\b', name_lower)
                        ),
                        None,
                    )
                    if matched_brand:
                        add_filtered(offer, "local_meat", matched_brand)
                        continue

        matched_kw = next(
            (
                keyword for keyword in exclude_keywords
                if re.search(r'\b' + re.escape(keyword.lower()) + r'\b', name_lower)
            ),
            None,
        )
        if matched_kw:
            add_filtered(offer, "keyword_excluded", matched_kw)
            continue

        matched_filtered_product = next(
            (
                product_keyword for product_keyword in filtered_products
                if re.search(r'\b' + re.escape(product_keyword.lower()) + r'\b', name_lower)
            ),
            None,
        )
        if matched_filtered_product:
            add_filtered(offer, "filtered_product", matched_filtered_product)
            continue

        if excluded_brands and offer.brand:
            offer_brand_upper = offer.brand.upper()
            matched_brand = next(
                (excluded for excluded in excluded_brands if excluded.upper() == offer_brand_upper),
                None,
            )
            if matched_brand:
                add_filtered(offer, "brand_excluded", matched_brand)
                continue

        if offer.brand and offer.brand.lower() in NON_FOOD_BRANDS:
            add_filtered(offer, "brand_excluded", f"non-food brand: {offer.brand}")
            continue

        name_normalized = fix_swedish_chars(offer.name).lower()
        matched_processed = next(
            (
                processed_keyword for processed_keyword in PROCESSED_FOODS
                if re.search(
                    r'\b' + re.escape(fix_swedish_chars(processed_keyword).lower()) + r'\b',
                    name_normalized,
                )
            ),
            None,
        )
        if matched_processed:
            is_exempt = any(
                re.search(r'\b' + re.escape(exemption) + r'\b', name_normalized)
                for exemption in PROCESSED_FOODS_EXEMPTIONS
            )
            if not is_exempt:
                add_filtered(offer, "processed", matched_processed)
                continue

        if CHIPS_WORD in name_lower and not is_cooking_chips(name_lower):
            add_filtered(offer, "junk_food", "chips")
            continue

        if re.search(r'\b' + re.escape(SODA_WORD) + r'\b', name_lower):
            add_filtered(offer, "junk_food", SODA_WORD)
            continue

        matched_bad = next(
            (
                bad for bad in JUNK_FOOD_KEYWORDS
                if re.search(r'\b' + re.escape(bad) + r'\b', name_lower)
            ),
            None,
        )
        if matched_bad:
            add_filtered(offer, "junk_food", matched_bad)
            continue

        if is_non_food_product(offer.name, offer.category):
            nf_normalized = fix_swedish_chars(offer.name).lower()
            detail = ""
            if offer.category and offer.category.lower() in NON_FOOD_CATEGORIES:
                detail = f"category:{offer.category}"
            elif _NON_FOOD_PATTERN:
                match = _NON_FOOD_PATTERN.search(nf_normalized)
                if match:
                    detail = match.group(0)
            add_filtered(offer, "non_food", detail)
            continue

        passed_offers.append(offer)

    unmatched_list = []
    matched_count = 0
    for offer in passed_offers:
        offer_match_key = build_offer_identity_key(offer)
        if offer_match_key in matched_offer_ids:
            matched_count += 1
            continue

        keywords = extract_keywords_from_product(offer.name, offer.category, brand=offer.brand)
        reason = "no_keywords" if not keywords else "no_recipe_match"
        unmatched_list.append({
            "name": offer.name,
            "price": float(offer.price) if offer.price else 0,
            "savings": float(offer.savings) if offer.savings else 0,
            "category": offer.category or "",
            "brand": offer.brand or "",
            "reason": reason,
            "detail": ", ".join(keywords) if keywords else "",
            "keywords": keywords,
        })
        stats[reason] = stats.get(reason, 0) + 1

    return {
        "total": len(all_offers),
        "matched": matched_count,
        "filtered": filtered_list,
        "unmatched": unmatched_list,
        "stats": stats,
    }


def build_initial_ingredient_groups(
    merged_ingredients: List[str],
    ingredients_normalized: List[str],
    matched_keywords_set: set[str],
    ingredient_match_data_per_ing,
) -> tuple[int, list[dict], dict[str, list[dict]]]:
    """Build initial Swedish ingredient groups before offer assignment."""
    total_ingredients = len(merged_ingredients) if merged_ingredients else 6
    ingredient_groups: list[dict] = []
    keyword_to_groups: dict[str, list[dict]] = {}

    for ing_idx, ingredient in enumerate(merged_ingredients):
        ingredient_text = str(ingredient)
        ingredient_lower = (
            ingredients_normalized[ing_idx]
            if ing_idx < len(ingredients_normalized)
            else ingredient_text.lower()
        )
        if not any(keyword in ingredient_lower for keyword in matched_keywords_set):
            continue

        alternatives = parse_eller_alternatives(ingredient_text)
        alternatives_normalized = [
            _apply_space_normalizations(fix_swedish_chars(alternative).lower())
            for alternative in alternatives
        ]

        family_keywords = set()
        for alternative in alternatives:
            for keyword in extract_keywords_from_ingredient(str(alternative)):
                canonical_keyword = INGREDIENT_PARENTS.get(keyword, keyword)
                if canonical_keyword in matched_keywords_set:
                    family_keywords.add(canonical_keyword)

        group = {
            'original': ingredient_text,
            'alternatives': alternatives,
            'alternatives_normalized': alternatives_normalized,
            'is_alternative': len(alternatives) > 1,
            'matched_keywords': {},
            'best_savings': 0.0,
            '_family_keywords': family_keywords,
            '_extracted_keywords': (
                ingredient_match_data_per_ing[ing_idx].extracted_keywords
                if ing_idx < len(ingredient_match_data_per_ing)
                else frozenset()
            ),
            '_ing_idx': ing_idx,
        }
        ingredient_groups.append(group)

        for alternative_normalized in alternatives_normalized:
            if any(keyword in alternative_normalized for keyword in matched_keywords_set):
                keyword_to_groups.setdefault(alternative_normalized, []).append(group)

    return total_ingredients, ingredient_groups, keyword_to_groups


def apply_pre_promotion(matched_offers: list[dict]) -> None:
    """Merge singular/plural Swedish keyword variants before group assignment."""
    all_matched_keywords = {offer['matched_keyword'] for offer in matched_offers}
    pre_promote: dict[str, str] = {}
    sorted_keywords = sorted(all_matched_keywords, key=len)

    for index, shorter in enumerate(sorted_keywords):
        for longer in sorted_keywords[index + 1:]:
            if not longer.startswith(shorter):
                continue

            suffix = longer[len(shorter):]
            suffix_len = len(suffix)
            if suffix_len <= 3 and suffix in ('er', 'ar', 'or', 'r', 'n', 'en', 'na', 'erna'):
                pre_promote[shorter] = longer
                break
            if suffix in PROMOTION_COMPOUND_SUFFIXES:
                pre_promote[shorter] = longer
                break

    for key in list(pre_promote):
        target = pre_promote[key]
        while target in pre_promote:
            target = pre_promote[target]
        pre_promote[key] = target

    if not pre_promote:
        return

    for offer_data in matched_offers:
        keyword = offer_data['matched_keyword']
        if keyword in pre_promote:
            offer_data['matched_keyword'] = pre_promote[keyword]


def build_offer_match_context(
    offer: Offer,
    offer_id: int,
    offer_keywords: Optional[Dict],
    offer_data_cache: Optional[Dict],
) -> dict:
    """Prepare Swedish offer precompute data shared by fullscan and shadow paths."""
    offer_precomputed = (
        offer_data_cache[offer_id]
        if offer_data_cache and offer_id in offer_data_cache
        else None
    )
    if offer_precomputed is None:
        offer_precomputed = precompute_offer_data(
            offer.name,
            offer.category,
            brand=getattr(offer, 'brand', ''),
            weight_grams=getattr(offer, 'weight_grams', None),
        )

    offer_match_data = build_precomputed_offer_match_data(
        offer.name,
        category=offer.category,
        brand=getattr(offer, 'brand', ''),
        weight_grams=getattr(offer, 'weight_grams', None),
        precomputed=offer_precomputed,
    )
    effective_offer_data = offer_match_data.precomputed
    offer_match_keywords = (
        offer_keywords.get(offer_id, [])
        if offer_keywords
        else (effective_offer_data.get('keywords', []) if effective_offer_data else [])
    )
    offer_name_normalized = (
        effective_offer_data.get('name_normalized', '')
        if effective_offer_data
        else _apply_space_normalizations(fix_swedish_chars(offer.name).lower())
    )

    return {
        'offer_precomputed': offer_precomputed,
        'offer_match_data': offer_match_data,
        'effective_offer_data': effective_offer_data,
        'offer_match_keywords': offer_match_keywords,
        'offer_name_normalized': offer_name_normalized,
    }


def _normalized_candidate_indices(
    candidate_indices: Optional[Iterable[int]],
    ingredient_count: int,
) -> range | list[int]:
    if candidate_indices is None:
        return range(ingredient_count)
    return sorted({
        int(idx)
        for idx in candidate_indices
        if isinstance(idx, int) and 0 <= idx < ingredient_count
    })


def collect_offer_match_candidates(
    ingredient_match_data_per_ing,
    offer_match_data,
    candidate_indices: Optional[Iterable[int]] = None,
) -> list[tuple[int, str]]:
    """Collect initial offer/ingredient candidates in matcher index order."""
    matched_candidates: list[tuple[int, str]] = []
    for ing_idx in _normalized_candidate_indices(
        candidate_indices,
        len(ingredient_match_data_per_ing),
    ):
        ing_data = ingredient_match_data_per_ing[ing_idx]
        result = match_offer_to_ingredient(ing_data, offer_match_data)
        if result.matched:
            matched_candidates.append((ing_idx, result.matched_keyword))
    return matched_candidates


def select_offer_match_candidate(
    matched_candidates: Iterable[tuple[int, str]],
    ingredient_match_data_per_ing,
) -> dict[str, Any]:
    """Select the production initial winner from collected candidates."""
    matched_candidates = list(matched_candidates)
    matched_keyword = None
    matched_ing_idx = None
    first_keyword = None
    first_ing_idx = None
    selected_by_fewer_keywords = False
    if matched_candidates:
        matched_ing_idx, matched_keyword = matched_candidates[0]
        first_ing_idx, first_keyword = matched_ing_idx, matched_keyword
        best_keyword_count = len(ingredient_match_data_per_ing[matched_ing_idx].extracted_keywords)
        for candidate_ing_idx, candidate_keyword in matched_candidates[1:]:
            if candidate_keyword != first_keyword:
                continue
            candidate_keyword_count = len(ingredient_match_data_per_ing[candidate_ing_idx].extracted_keywords)
            if candidate_keyword_count < best_keyword_count:
                matched_ing_idx = candidate_ing_idx
                matched_keyword = candidate_keyword
                best_keyword_count = candidate_keyword_count
                selected_by_fewer_keywords = True

    return {
        'matched_candidates': matched_candidates,
        'first_ing_idx': first_ing_idx,
        'first_keyword': first_keyword,
        'matched_keyword': matched_keyword,
        'matched_ing_idx': matched_ing_idx,
        'selected_keyword': matched_keyword,
        'selected_ing_idx': matched_ing_idx,
        'selected_by_fewer_keywords': selected_by_fewer_keywords,
    }


def prepare_offer_match_candidate(
    offer: Offer,
    offer_id: int,
    offer_keywords: Optional[Dict],
    offer_data_cache: Optional[Dict],
    ingredient_match_data_per_ing,
    candidate_indices: Optional[Iterable[int]] = None,
) -> dict:
    """Prepare Swedish offer precompute data and choose the initial ingredient match."""
    context = build_offer_match_context(
        offer,
        offer_id,
        offer_keywords,
        offer_data_cache,
    )
    normalized_indices = (
        None if candidate_indices is None
        else _normalized_candidate_indices(candidate_indices, len(ingredient_match_data_per_ing))
    )
    selection = select_offer_match_candidate(
        collect_offer_match_candidates(
            ingredient_match_data_per_ing,
            context['offer_match_data'],
            normalized_indices,
        ),
        ingredient_match_data_per_ing,
    )
    return {
        **context,
        **selection,
        'ingredient_check_count': (
            len(ingredient_match_data_per_ing)
            if normalized_indices is None
            else len(normalized_indices)
        ),
    }


def _record_shadow_event(
    shadow_events: Optional[list[dict]],
    event_type: str,
    **details,
) -> None:
    if shadow_events is not None:
        shadow_events.append({'type': event_type, **details})


def validate_offer_match_candidate(
    offer: Offer,
    offer_id: int,
    offer_data_cache: Optional[Dict],
    matched_keyword: Optional[str],
    matched_ing_idx: Optional[int],
    offer_precomputed,
    offer_match_data,
    effective_offer_data,
    offer_match_keywords,
    offer_name_normalized: str,
    ingredient_match_data_per_ing,
    ingredients_normalized: list[str],
    ingredient_source_texts: list[str],
    ingredient_source_indices: list[int],
    merged_ingredients: list[str],
    full_recipe_text: str,
    shadow_events: Optional[list[dict]] = None,
) -> Optional[dict]:
    """Run Swedish phase-1 validation and return finalized offer_data or None."""
    if not matched_keyword or matched_ing_idx is None:
        return None

    product_lower = (
        offer_precomputed['name_normalized']
        if offer_precomputed is not None
        else offer_name_normalized
    )

    # === PROCESSED_PRODUCT_RULES validation ===
    matched_processed_kw = SPECIALTY_KEYWORD_ALIASES.get(
        matched_keyword.lower(), matched_keyword.lower()
    )
    processed_checks = (
        offer_precomputed.get('processed_checks', ())
        if offer_precomputed is not None
        else ()
    )
    should_run_processed_rules = bool(processed_checks) or matched_processed_kw in STRICT_PROCESSED_RULES
    if should_run_processed_rules:
        ing_norm = ingredients_normalized[matched_ing_idx]
        ing_norm = re.sub(r'\btandori\b', 'tandoori', ing_norm)
        if not check_processed_product_rules(product_lower, ing_norm):
            _record_shadow_event(
                shadow_events,
                'validation_reject',
                rule='processed_product',
                ing_idx=matched_ing_idx,
                keyword=matched_keyword,
            )
            matched_keyword = None

    valid_ingredient_indices = None
    matched_specialty_kw = SPECIALTY_KEYWORD_ALIASES.get(
        matched_keyword.lower(), matched_keyword.lower()
    ) if matched_keyword else None
    if matched_keyword and matched_ing_idx is not None and matched_specialty_kw in SPECIALTY_QUALIFIERS:
        if offer_precomputed is not None:
            offer_spec_quals = offer_precomputed.get('specialty_qualifiers', {})
        else:
            offer_spec_quals = {}
            for base_word, qualifiers in SPECIALTY_QUALIFIERS.items():
                if base_word in offer_name_normalized or base_word in offer_match_keywords:
                    found_in_offer = {q for q in qualifiers if q in product_lower}
                    if found_in_offer:
                        offer_spec_quals[base_word] = found_in_offer

        kw_candidates = [matched_specialty_kw]
        if matched_specialty_kw not in SPECIALTY_QUALIFIERS:
            extra = [
                k.lower() for k in offer_spec_quals
                if k.lower() != matched_specialty_kw and k.lower() in SPECIALTY_QUALIFIERS
            ]
            kw_candidates.extend(extra)

        valid_ingredient_indices = set()
        ing_norm = ingredients_normalized[matched_ing_idx]
        for kw_try in kw_candidates:
            if check_specialty_qualifiers(offer_spec_quals, kw_try, ing_norm):
                valid_ingredient_indices.add(matched_ing_idx)
                break
        if not valid_ingredient_indices:
            sq_retried = False
            retry_from_idx = matched_ing_idx
            retry_from_keyword = matched_keyword
            for retry_idx in range(matched_ing_idx + 1, len(ingredients_normalized)):
                retry_ing = ingredients_normalized[retry_idx]
                retry_result = match_offer_to_ingredient(
                    ingredient_match_data_per_ing[retry_idx],
                    offer_match_data,
                ).matched_keyword
                if not retry_result:
                    continue
                retry_kw = retry_result.lower()
                retry_candidates = [SPECIALTY_KEYWORD_ALIASES.get(retry_kw, retry_kw)]
                if retry_candidates[0] not in SPECIALTY_QUALIFIERS:
                    extra = [
                        k.lower() for k in offer_spec_quals
                        if k.lower() != retry_candidates[0] and k.lower() in SPECIALTY_QUALIFIERS
                    ]
                    retry_candidates.extend(extra)
                retry_valid = False
                for kw_try in retry_candidates:
                    if check_specialty_qualifiers(offer_spec_quals, kw_try, retry_ing):
                        retry_valid = True
                        break
                if retry_valid:
                    matched_keyword = retry_result
                    matched_ing_idx = retry_idx
                    valid_ingredient_indices = {retry_idx}
                    sq_retried = True
                    _record_shadow_event(
                        shadow_events,
                        'validation_retry',
                        rule='specialty_qualifier',
                        from_idx=retry_from_idx,
                        to_idx=retry_idx,
                        from_keyword=retry_from_keyword,
                        to_keyword=retry_result,
                    )
                    break
            if not sq_retried:
                _record_shadow_event(
                    shadow_events,
                    'validation_reject',
                    rule='specialty_qualifier',
                    ing_idx=matched_ing_idx,
                    keyword=matched_keyword,
                )
                matched_keyword = None

    if matched_keyword and matched_ing_idx is not None and matched_keyword in KEYWORD_SUPPRESSED_BY_CONTEXT:
        suppressors = KEYWORD_SUPPRESSED_BY_CONTEXT[matched_keyword]
        ing_norm = ingredients_normalized[matched_ing_idx]
        if any(s in ing_norm for s in suppressors):
            _record_shadow_event(
                shadow_events,
                'validation_reject',
                rule='context_suppression',
                ing_idx=matched_ing_idx,
                keyword=matched_keyword,
            )
            matched_keyword = None

    if matched_keyword and matched_ing_idx is not None:
        ing_norm = ingredients_normalized[matched_ing_idx]
        if not check_secondary_ingredient_patterns(
            product_lower,
            ing_norm,
            matched_keyword=matched_keyword.lower(),
        ):
            _record_shadow_event(
                shadow_events,
                'validation_reject',
                rule='secondary_ingredient_pattern',
                ing_idx=matched_ing_idx,
                keyword=matched_keyword,
            )
            matched_keyword = None

    if matched_keyword and matched_ing_idx is not None:
        matched_kw_lower = matched_keyword.lower()
        if matched_kw_lower not in DESCRIPTOR_SUPPRESSION_PRIMARIES:
            ing_norm = ingredients_normalized[matched_ing_idx]
            has_primary = any(p in ing_norm for p in DESCRIPTOR_SUPPRESSION_PRIMARIES)
            if has_primary:
                marker_match = _DESCRIPTOR_PHRASE_MARKERS.search(ing_norm)
                if marker_match:
                    marker_end = marker_match.end()
                    if ing_norm.find(matched_kw_lower, marker_end) >= 0:
                        _record_shadow_event(
                            shadow_events,
                            'validation_reject',
                            rule='descriptor_suppression',
                            ing_idx=matched_ing_idx,
                            keyword=matched_keyword,
                        )
                        matched_keyword = None

    if matched_keyword and matched_ing_idx is not None:
        icm = offer_precomputed.get('ingredient_context_missing', set()) if offer_precomputed is not None else set()
        if icm:
            ing_norm = ingredients_normalized[matched_ing_idx]
            matched_kw_lower = matched_keyword.lower()
            for req_word in icm:
                if req_word in ing_norm and matched_kw_lower != req_word:
                    _record_shadow_event(
                        shadow_events,
                        'validation_reject',
                        rule='ingredient_context_missing',
                        ing_idx=matched_ing_idx,
                        keyword=matched_keyword,
                    )
                    matched_keyword = None
                    break

    svf_key = None
    if matched_keyword and matched_ing_idx is not None:
        if matched_keyword in SPICE_VS_FRESH_RULES:
            svf_key = matched_keyword
        else:
            for base in SPICE_VS_FRESH_RULES:
                if matched_keyword.startswith(base) and len(matched_keyword) > len(base):
                    svf_key = base
                    break
    if svf_key:
        precomputed_svf = offer_precomputed if offer_precomputed is not None else effective_offer_data
        product_lower = precomputed_svf['name_normalized']
        ing_norm = ingredients_normalized[matched_ing_idx]
        svf_rule = precomputed_svf.get('spice_fresh_blocks', {}).get(svf_key)
        if svf_rule:
            if svf_rule['mode'] == 'require':
                svf_allowed = any(ind in ing_norm for ind in svf_rule['indicators'])
            else:
                svf_allowed = not ingredient_has_spice_indicator(
                    set(svf_rule['indicators']), ing_norm, svf_key
                )
        else:
            svf_allowed = check_spice_vs_fresh_rules(product_lower, ing_norm, svf_key)

        if not svf_allowed:
            svf_retried = False
            retry_from_idx = matched_ing_idx
            retry_from_keyword = matched_keyword
            for retry_idx in range(matched_ing_idx + 1, len(ingredients_normalized)):
                retry_ing = ingredients_normalized[retry_idx]
                retry_offer_match_data = build_precomputed_offer_match_data(
                    offer.name,
                    category=offer.category,
                    brand=getattr(offer, 'brand', ''),
                    weight_grams=getattr(offer, 'weight_grams', None),
                    precomputed=precomputed_svf,
                )
                retry_result = match_offer_to_ingredient(
                    ingredient_match_data_per_ing[retry_idx],
                    retry_offer_match_data,
                ).matched_keyword
                if not retry_result:
                    continue
                retry_svf_key = retry_result if retry_result in SPICE_VS_FRESH_RULES else None
                if retry_svf_key is None:
                    for base in SPICE_VS_FRESH_RULES:
                        if retry_result.startswith(base) and len(retry_result) > len(base):
                            retry_svf_key = base
                            break
                if retry_svf_key:
                    retry_rule = precomputed_svf.get('spice_fresh_blocks', {}).get(retry_svf_key)
                    if retry_rule:
                        if retry_rule['mode'] == 'require':
                            retry_allowed = any(ind in retry_ing for ind in retry_rule['indicators'])
                        else:
                            retry_allowed = not ingredient_has_spice_indicator(
                                set(retry_rule['indicators']), retry_ing, retry_svf_key
                            )
                    else:
                        retry_allowed = check_spice_vs_fresh_rules(product_lower, retry_ing, retry_svf_key)
                    if not retry_allowed:
                        continue
                matched_keyword = retry_result
                matched_ing_idx = retry_idx
                svf_retried = True
                _record_shadow_event(
                    shadow_events,
                    'validation_retry',
                    rule='spice_fresh',
                    from_idx=retry_from_idx,
                    to_idx=retry_idx,
                    from_keyword=retry_from_keyword,
                    to_keyword=retry_result,
                )
                break
            if not svf_retried:
                _record_shadow_event(
                    shadow_events,
                    'validation_reject',
                    rule='spice_fresh',
                    ing_idx=matched_ing_idx,
                    keyword=matched_keyword,
                )
                matched_keyword = None

    if matched_keyword and matched_ing_idx is not None and matched_keyword in FRESH_HERB_KEYWORDS:
        product_lower = (
            offer_precomputed['name_normalized']
            if offer_precomputed is not None
            else offer_name_normalized
        )

        prod_is_dried = any(di in product_lower for di in DRIED_PRODUCT_INDICATORS)
        prod_is_frozen = any(fi in product_lower for fi in FROZEN_PRODUCT_INDICATORS)
        prod_is_fresh = any(fi in product_lower for fi in FRESH_PRODUCT_INDICATORS)
        if not prod_is_fresh and not prod_is_dried and not prod_is_frozen:
            weight_grams = (
                offer_precomputed.get('weight_grams')
                if offer_precomputed is not None
                else getattr(offer, 'weight_grams', None)
            )
            if weight_grams and weight_grams > 80:
                prod_is_fresh = True
            else:
                prod_is_dried = True
        if prod_is_dried or prod_is_frozen or prod_is_fresh:
            ing_norm = ingredients_normalized[matched_ing_idx]
            ing_original_source = (
                ingredient_source_texts[matched_ing_idx]
                if matched_ing_idx < len(ingredient_source_texts)
                else merged_ingredients[matched_ing_idx]
            )
            ing_original = fix_swedish_chars(str(ing_original_source)).lower()
            recipe_wants_fresh = (
                any(fi in ing_norm for fi in RECIPE_FRESH_INDICATORS)
                or any(fi in ing_original for fi in RECIPE_FRESH_INDICATORS)
            )
            recipe_wants_dried = any(di in ing_norm for di in RECIPE_DRIED_INDICATORS)
            recipe_wants_frozen = any(zi in ing_norm for zi in RECIPE_FROZEN_INDICATORS)
            plain_graslok_default = False
            if (
                matched_keyword in {'chili', 'chilipeppar', 'chilifrukt', 'chilifrukter'}
                and _RE_CHILI_COUNT_FRESH.search(ing_norm)
            ):
                recipe_wants_fresh = True
            if not recipe_wants_fresh and not recipe_wants_dried and not recipe_wants_frozen:
                if any(m in ing_norm for m in ('tsk ', 'krm ', ' tsk ', ' krm ')):
                    recipe_wants_dried = True
            if not recipe_wants_fresh and not recipe_wants_dried and not recipe_wants_frozen:
                if (
                    any(vi in ing_norm for vi in RECIPE_FRESH_VOLUME_INDICATORS)
                    or _RE_GRAM_MEASURE.search(ing_norm)
                ):
                    recipe_wants_fresh = True
                elif (
                    'eller' in ing_norm
                    and matched_keyword in FRESH_HERB_KEYWORDS
                    and 'oxalis' in ing_norm
                ):
                    recipe_wants_fresh = True
                elif any(vi in ing_norm for vi in RECIPE_DRIED_VOLUME_INDICATORS):
                    recipe_wants_dried = True
                elif matched_keyword in {'gräslök', 'graslok'}:
                    plain_graslok_default = True
                else:
                    recipe_wants_dried = True
            should_block = False
            if prod_is_frozen:
                if not recipe_wants_frozen and not plain_graslok_default:
                    should_block = True
            elif prod_is_dried and not prod_is_fresh:
                if not recipe_wants_dried:
                    should_block = True
            elif prod_is_fresh and not prod_is_dried:
                if not recipe_wants_fresh and not plain_graslok_default:
                    should_block = True
            if should_block:
                _record_shadow_event(
                    shadow_events,
                    'validation_reject',
                    rule='carrier_flavor_context',
                    detail='fresh_herb_form',
                    ing_idx=matched_ing_idx,
                    keyword=matched_keyword,
                )
                matched_keyword = None

    if matched_keyword and matched_ing_idx is not None:
        product_lower = (
            offer_precomputed['name_normalized']
            if offer_precomputed is not None
            else offer_name_normalized
        )
        ing_norm = ingredients_normalized[matched_ing_idx]

        if any(ind in product_lower for ind in _PROCESSED_PRODUCT_INDICATORS):
            if has_eller_pattern(ing_norm):
                processed_alt_allowed = False
                for alt in parse_eller_alternatives(ing_norm):
                    alt_norm = _apply_space_normalizations(fix_swedish_chars(str(alt)).lower())
                    explicitly_allows_processed = (
                        any(di in alt_norm for di in RECIPE_DRIED_INDICATORS)
                        or any(fi in alt_norm for fi in RECIPE_FROZEN_INDICATORS)
                        or any(ind in alt_norm for ind in _PROCESSED_PRODUCT_INDICATORS)
                    )
                    if not any(fw in alt_norm for fw in FRESH_WORDS) or explicitly_allows_processed:
                        processed_alt_allowed = True
                        break
                if not processed_alt_allowed:
                    _record_shadow_event(
                        shadow_events,
                        'validation_reject',
                        rule='processed_product',
                        detail='processed_eller_alternatives',
                        ing_idx=matched_ing_idx,
                        keyword=matched_keyword,
                    )
                    matched_keyword = None
            else:
                explicitly_allows_processed = (
                    any(di in ing_norm for di in RECIPE_DRIED_INDICATORS)
                    or any(fi in ing_norm for fi in RECIPE_FROZEN_INDICATORS)
                )
                mushroom_fresh_frozen_fallback_kw = frozenset({
                    'svamp',
                    'champinjon', 'champinjoner',
                    'kantarell', 'kantareller',
                    'trattkantarell',
                    'shiitake',
                    'ostronskivling',
                })
                frozen_mushroom_fallback = (
                    matched_keyword in mushroom_fresh_frozen_fallback_kw
                    and any(fi in ing_norm for fi in FRESH_WORDS)
                    and any(fi in product_lower for fi in FROZEN_PRODUCT_INDICATORS)
                )
                if (
                    any(fw in ing_norm for fw in FRESH_WORDS)
                    and not explicitly_allows_processed
                    and not frozen_mushroom_fallback
                ):
                    _record_shadow_event(
                        shadow_events,
                        'validation_reject',
                        rule='processed_product',
                        detail='fresh_recipe_processed_product',
                        ing_idx=matched_ing_idx,
                        keyword=matched_keyword,
                    )
                    matched_keyword = None

        if (
            matched_keyword == SPARRIS_WORD
            and any(fw in ing_norm for fw in FRESH_WORDS)
            and BITAR_WORD in product_lower
        ):
            _record_shadow_event(
                shadow_events,
                'validation_reject',
                rule='processed_product',
                detail='sparris_bitar',
                ing_idx=matched_ing_idx,
                keyword=matched_keyword,
            )
            matched_keyword = None

        if (
            matched_keyword == 'fiskfilé'
            and 'fisk' in ing_norm
            and 'fiskfilé' not in ing_norm
            and 'fiskfile' not in ing_norm
            and any(fi in ing_norm for fi in RECIPE_FROZEN_INDICATORS)
            and not any(fi in product_lower for fi in FROZEN_PRODUCT_INDICATORS)
        ):
            _record_shadow_event(
                shadow_events,
                'validation_reject',
                rule='processed_product',
                detail='frozen_fishfile',
                ing_idx=matched_ing_idx,
                keyword=matched_keyword,
            )
            matched_keyword = None

        if matched_keyword in {'kantarell', 'kantareller'}:
            kantarell_preserved_ingredient = frozenset({
                'burk', 'konserv', 'konserverad', 'konserverade',
                'avrunnen', 'avrunna',
            })
            kantarell_preserved_product = frozenset({
                'burk', 'konserv', 'konserverad', 'konserverade',
                'vatten',
            })
            if any(ind in ing_norm for ind in kantarell_preserved_ingredient):
                if not any(ind in product_lower for ind in kantarell_preserved_product):
                    _record_shadow_event(
                        shadow_events,
                        'validation_reject',
                        rule='processed_product',
                        detail='preserved_kantarell',
                        ing_idx=matched_ing_idx,
                        keyword=matched_keyword,
                    )
                    matched_keyword = None

        if matched_keyword in {
            'körsbärstomat', 'körsbärstomater',
            'korsbarstomat', 'korsbarstomater',
        }:
            cherry_tomato_preserved_ingredient = frozenset({
                'burk', 'konserv', 'konserverad', 'konserverade',
            })
            cherry_tomato_fresh_product_cues = frozenset({
                'klass', 'färsk', 'farsk',
                'fryst', 'frysta',
            })
            if any(ind in ing_norm for ind in cherry_tomato_preserved_ingredient):
                if any(ind in product_lower for ind in cherry_tomato_fresh_product_cues):
                    _record_shadow_event(
                        shadow_events,
                        'validation_reject',
                        rule='processed_product',
                        detail='preserved_cherry_tomato',
                        ing_idx=matched_ing_idx,
                        keyword=matched_keyword,
                    )
                    matched_keyword = None

        if matched_keyword == 'ananas':
            drained_pineapple_product_cues = frozenset({
                'juice', 'krossad', 'krossade',
                'skivor', 'skiva',
                'ringar', 'ring',
                'bitar',
            })
            non_canned_pineapple_cues = frozenset({
                'fryst', 'frysta',
                'torkad', 'torkade',
                'klass', 'färsk', 'farsk',
                'smoothie',
            })
            if any(ind in ing_norm for ind in ('avrunnen', 'avrunna')):
                if any(ind in product_lower for ind in non_canned_pineapple_cues):
                    _record_shadow_event(
                        shadow_events,
                        'validation_reject',
                        rule='processed_product',
                        detail='drained_pineapple',
                        ing_idx=matched_ing_idx,
                        keyword=matched_keyword,
                    )
                    matched_keyword = None
                elif not any(ind in product_lower for ind in drained_pineapple_product_cues):
                    _record_shadow_event(
                        shadow_events,
                        'validation_reject',
                        rule='processed_product',
                        detail='drained_pineapple',
                        ing_idx=matched_ing_idx,
                        keyword=matched_keyword,
                    )
                    matched_keyword = None

        if matched_keyword == KALKON_WORD and HELKALKON_WORD in ing_norm:
            _record_shadow_event(
                shadow_events,
                'validation_reject',
                rule='carrier_flavor_context',
                detail='whole_turkey',
                ing_idx=matched_ing_idx,
                keyword=matched_keyword,
            )
            matched_keyword = None

        if matched_keyword in {
            'filé', 'file', 'fil',
            'bröst', 'brost',
            'bröstfil', 'bröstfilé', 'brostfil', 'brostfile',
            'lårfil', 'lårfilé', 'larfil', 'larfile',
        }:
            wants_kyckling = 'kyckling' in ing_norm and 'kalkon' not in ing_norm
            wants_kalkon = 'kalkon' in ing_norm and 'kyckling' not in ing_norm
            if wants_kyckling and 'kalkon' in product_lower:
                _record_shadow_event(
                    shadow_events,
                    'validation_reject',
                    rule='carrier_flavor_context',
                    detail='poultry_context',
                    ing_idx=matched_ing_idx,
                    keyword=matched_keyword,
                )
                matched_keyword = None
            if wants_kalkon and 'kyckling' in product_lower:
                _record_shadow_event(
                    shadow_events,
                    'validation_reject',
                    rule='carrier_flavor_context',
                    detail='poultry_context',
                    ing_idx=matched_ing_idx,
                    keyword=matched_keyword,
                )
                matched_keyword = None

    if matched_keyword and matched_ing_idx is not None:
        matched_kw_lower = matched_keyword.lower()
        if matched_kw_lower in PASTA_KEYWORDS:
            product_lower = (
                offer_precomputed['name_normalized']
                if offer_precomputed is not None
                else offer_name_normalized
            )
            ing_norm = ingredients_normalized[matched_ing_idx]
            if any(fw in ing_norm for fw in FRESH_WORDS):
                if not any(fw in product_lower for fw in FRESH_WORDS):
                    _record_shadow_event(
                        shadow_events,
                        'validation_reject',
                        rule='carrier_flavor_context',
                        detail='fresh_pasta',
                        ing_idx=matched_ing_idx,
                        keyword=matched_keyword,
                    )
                    matched_keyword = None

    if matched_keyword and matched_ing_idx is not None:
        product_lower = (
            offer_precomputed['name_normalized']
            if offer_precomputed is not None
            else offer_name_normalized
        )
        if BULJONG_WORD not in product_lower and FOND_WORD not in product_lower:
            ing_norm = ingredients_normalized[matched_ing_idx]
            if BULJONG_WORD in ing_norm or FOND_WORD in ing_norm:
                _record_shadow_event(
                    shadow_events,
                    'validation_reject',
                    rule='carrier_flavor_context',
                    detail='bouillon_context',
                    ing_idx=matched_ing_idx,
                    keyword=matched_keyword,
                )
                matched_keyword = None

    if matched_keyword and matched_ing_idx is not None:
        matched_kw_lower = matched_keyword.lower()
        if matched_kw_lower == BULJONG_WORD:
            ing_norm = ingredients_normalized[matched_ing_idx]
            if not any(t in ing_norm for t in BULJONG_TYPE_PREFIXES):
                product_lower = (
                    offer_precomputed['name_normalized']
                    if offer_precomputed is not None
                    else offer_name_normalized
                )
                if not any(dw in product_lower for dw in BULJONG_DEFAULT_WORDS):
                    _record_shadow_event(
                        shadow_events,
                        'validation_reject',
                        rule='carrier_flavor_context',
                        detail='bouillon_type_context',
                        ing_idx=matched_ing_idx,
                        keyword=matched_keyword,
                    )
                    matched_keyword = None

    if matched_keyword and matched_ing_idx is not None:
        product_lower = (
            offer_precomputed['name_normalized']
            if offer_precomputed is not None
            else offer_name_normalized
        )
        ing_norm = ingredients_normalized[matched_ing_idx]
        if not check_yoghurt_match(matched_keyword, ing_norm, product_lower):
            _record_shadow_event(
                shadow_events,
                'validation_reject',
                rule='carrier_flavor_context',
                detail='dairy_type',
                ing_idx=matched_ing_idx,
                keyword=matched_keyword,
            )
            matched_keyword = None
        elif not check_filmjolk_match(matched_keyword, ing_norm, product_lower):
            _record_shadow_event(
                shadow_events,
                'validation_reject',
                rule='carrier_flavor_context',
                detail='dairy_type',
                ing_idx=matched_ing_idx,
                keyword=matched_keyword,
            )
            matched_keyword = None
        elif not check_kvarg_match(matched_keyword, ing_norm, product_lower):
            _record_shadow_event(
                shadow_events,
                'validation_reject',
                rule='carrier_flavor_context',
                detail='dairy_type',
                ing_idx=matched_ing_idx,
                keyword=matched_keyword,
            )
            matched_keyword = None

    if matched_keyword and matched_ing_idx is not None and matched_keyword in PRODUCT_NAME_BLOCKERS:
        product_lower = (
            offer_precomputed['name_normalized']
            if offer_precomputed is not None
            else offer_name_normalized
        )
        if not (
            matched_keyword in {'stjärnanis', 'stjarnanis'}
            and ('stjärn' in product_lower or 'stjarn' in product_lower)
        ):
            blocker_words = PRODUCT_NAME_BLOCKERS[matched_keyword]
            product_blockers = [b for b in blocker_words if b in product_lower]
            if product_blockers:
                ing_norm = ingredients_normalized[matched_ing_idx]
                if not ingredient_satisfies_product_name_blockers(ing_norm, product_blockers):
                    _record_shadow_event(
                        shadow_events,
                        'validation_reject',
                        rule='product_name_blocker',
                        ing_idx=matched_ing_idx,
                        keyword=matched_keyword,
                    )
                    matched_keyword = None

    if matched_keyword and matched_ing_idx is not None and matched_keyword == FOND_WORD:
        product_lower = (
            offer_precomputed['name_normalized']
            if offer_precomputed is not None
            else offer_name_normalized
        )
        ing_norm = ingredients_normalized[matched_ing_idx]
        type_found = None
        for type_word, valid_product_words in FOND_TYPE_CONTEXT.items():
            if type_word in ing_norm:
                type_found = valid_product_words
                break
        if type_found:
            if not any(word in product_lower for word in type_found):
                _record_shadow_event(
                    shadow_events,
                    'validation_reject',
                    rule='carrier_flavor_context',
                    detail='fond_type_context',
                    ing_idx=matched_ing_idx,
                    keyword=matched_keyword,
                )
                matched_keyword = None

    if matched_keyword and matched_ing_idx is not None:
        matched_kw_lower = matched_keyword.lower()
        if matched_kw_lower in RECIPE_INGREDIENT_BLOCKERS:
            blockers = RECIPE_INGREDIENT_BLOCKERS[matched_kw_lower]
            ing_norm = ingredients_normalized[matched_ing_idx]
            if any(blocker in ing_norm for blocker in blockers):
                _record_shadow_event(
                    shadow_events,
                    'validation_reject',
                    rule='carrier_flavor_context',
                    detail='recipe_ingredient_blocker',
                    ing_idx=matched_ing_idx,
                    keyword=matched_keyword,
                )
                matched_keyword = None

    if matched_keyword and matched_ing_idx is not None:
        matched_kw_lower = matched_keyword.lower()
        ing_norm = ingredients_normalized[matched_ing_idx]
        if matched_kw_lower in ing_norm and _is_false_positive_blocked(matched_kw_lower, ing_norm):
            _record_shadow_event(
                shadow_events,
                'validation_reject',
                rule='carrier_flavor_context',
                detail='false_positive_blocker',
                ing_idx=matched_ing_idx,
                keyword=matched_keyword,
            )
            matched_keyword = None

    if matched_keyword and matched_ing_idx is not None:
        prod_lower = (
            offer_precomputed['name_normalized']
            if offer_precomputed is not None
            else offer_name_normalized
        )
        if not any(vi in prod_lower for vi in VEG_PRODUCT_INDICATORS):
            ing_norm = ingredients_normalized[matched_ing_idx]
            ing_words = set(ing_norm.split())
            if ing_words & VEG_QUALIFIER_WORDS:
                _record_shadow_event(
                    shadow_events,
                    'validation_reject',
                    rule='carrier_flavor_context',
                    detail='veg_qualifier',
                    ing_idx=matched_ing_idx,
                    keyword=matched_keyword,
                )
                matched_keyword = None

    if matched_keyword and matched_ing_idx is not None:
        matched_kw_lower = matched_keyword.lower()
        if matched_kw_lower in FLAVOR_WORDS:
            ing_norm = ingredients_normalized[matched_ing_idx]
            if matched_kw_lower in ing_norm:
                carrier_blocked = False
                carrier_product_lower = (
                    offer_precomputed.get('name_normalized', '')
                    if offer_precomputed is not None
                    else offer_name_normalized
                )
                contextual_cheese_use_case = (
                    matched_kw_lower == 'ost'
                    and any(
                        cheese_kw in carrier_product_lower
                        and any(cw in ing_norm for cw in context_words)
                        for cheese_kw, context_words in CHEESE_CONTEXT.items()
                    )
                )
                dark_chocolate_bar_use_case = (
                    matched_kw_lower == 'choklad'
                    and 'chokladkaka' in ing_norm
                    and any(cue in ing_norm for cue in ('mörk chokladkaka', 'mork chokladkaka'))
                    and 'chokladkaka' in carrier_product_lower
                    and '%' in carrier_product_lower
                    and any(cue in carrier_product_lower for cue in ('mörk choklad', 'mork choklad'))
                    and not any(flavor in carrier_product_lower for flavor in (
                        'apelsin', 'chili', 'fikon', 'havssalt', 'seasalt',
                        'karamell', 'caramel', 'caramelized', 'hazelnut', 'hassel',
                        'mint', 'hallon', 'mango', 'passion', 'pistage',
                        'almond', 'lakrits', 'saltlakrits',
                    ))
                )
                if not contextual_cheese_use_case and not dark_chocolate_bar_use_case:
                    carrier_blocked = _flavor_keyword_blocked_by_carrier_text(
                        ing_norm,
                        matched_kw_lower,
                    )
                    if carrier_blocked and has_eller_pattern(ing_norm):
                        for alt in parse_eller_alternatives(ing_norm):
                            alt_norm = _apply_space_normalizations(
                                fix_swedish_chars(str(alt)).lower()
                            )
                            if matched_kw_lower not in alt_norm:
                                continue
                            if not _flavor_keyword_blocked_by_carrier_text(
                                alt_norm,
                                matched_kw_lower,
                            ):
                                carrier_blocked = False
                                break
                if carrier_blocked:
                    flavor_retried = False
                    retry_from_idx = matched_ing_idx
                    retry_from_keyword = matched_keyword
                    if offer_data_cache and offer_id in offer_data_cache:
                        retry_offer_match_data = build_precomputed_offer_match_data(
                            offer.name,
                            category=offer.category,
                            brand=getattr(offer, 'brand', ''),
                            weight_grams=getattr(offer, 'weight_grams', None),
                            precomputed=offer_precomputed,
                        )
                        for retry_idx in range(matched_ing_idx + 1, len(ingredients_normalized)):
                            retry_ing = ingredients_normalized[retry_idx]
                            retry_result = match_offer_to_ingredient(
                                ingredient_match_data_per_ing[retry_idx],
                                retry_offer_match_data,
                            ).matched_keyword
                            if retry_result:
                                retry_keyword_lower = retry_result.lower()
                                if retry_keyword_lower in FLAVOR_WORDS and retry_keyword_lower in retry_ing:
                                    retry_ing_words = set(retry_ing.split())
                                    if (retry_ing_words & _CARRIER_SINGLE_WORDS) - {retry_keyword_lower}:
                                        continue
                                    if any(carrier in retry_ing for carrier in _CARRIER_MULTI_WORDS):
                                        continue
                                matched_keyword = retry_result
                                matched_ing_idx = retry_idx
                                flavor_retried = True
                                _record_shadow_event(
                                    shadow_events,
                                    'validation_retry',
                                    rule='carrier_flavor_context',
                                    from_idx=retry_from_idx,
                                    to_idx=retry_idx,
                                    from_keyword=retry_from_keyword,
                                    to_keyword=retry_result,
                                )
                                break
                    if not flavor_retried:
                        _record_shadow_event(
                            shadow_events,
                            'validation_reject',
                            rule='carrier_flavor_context',
                            ing_idx=matched_ing_idx,
                            keyword=matched_keyword,
                        )
                        matched_keyword = None

    if matched_keyword:
        if offer_precomputed is not None:
            cuisine_triggers = offer_precomputed.get('cuisine_triggers', {})
        else:
            cuisine_triggers = {}
            for trigger, contexts in CUISINE_CONTEXT.items():
                if trigger in product_lower:
                    cuisine_triggers[trigger] = contexts
                    break

        for trigger, contexts in cuisine_triggers.items():
            if not any(ctx in full_recipe_text for ctx in contexts):
                _record_shadow_event(
                    shadow_events,
                    'validation_reject',
                    rule='carrier_flavor_context',
                    detail='cuisine_context',
                    ing_idx=matched_ing_idx,
                    keyword=matched_keyword,
                )
                matched_keyword = None
            break

    if matched_keyword:
        ing_norm = (
            ingredients_normalized[matched_ing_idx]
            if matched_ing_idx is not None and matched_ing_idx < len(ingredients_normalized)
            else ''
        )
        offer_quals = (
            offer_precomputed.get('specialty_qualifiers', {}).get('kyckling', set())
            if offer_precomputed is not None
            else set()
        )
        if (
            matched_keyword == 'kyckling'
            and ingredient_implies_whole_kyckling(ing_norm)
            and 'hel' not in offer_quals
        ):
            _record_shadow_event(
                shadow_events,
                'validation_reject',
                rule='carrier_flavor_context',
                detail='whole_chicken',
                ing_idx=matched_ing_idx,
                keyword=matched_keyword,
            )
            matched_keyword = None

    if not matched_keyword:
        return None

    if offer_precomputed is not None:
        offer_spec_quals = offer_precomputed.get('specialty_qualifiers', {})
        rank_product_lower = offer_precomputed.get('name_normalized', '')
    else:
        rank_product_lower = offer_name_normalized
        offer_spec_quals = {}
        for base_word, qualifiers in SPECIALTY_QUALIFIERS.items():
            if base_word in rank_product_lower or base_word in offer_match_keywords:
                found_in_offer = {q for q in qualifiers if q in rank_product_lower}
                if found_in_offer:
                    offer_spec_quals[base_word] = found_in_offer

    rank_ingredient = (
        ingredients_normalized[matched_ing_idx]
        if matched_ing_idx is not None and matched_ing_idx < len(ingredients_normalized)
        else ''
    )
    has_qualifier_match = bool(offer_spec_quals.get(matched_keyword))
    qualifier_specificity_rank = compute_qualifier_specificity_rank(
        rank_ingredient,
        matched_keyword,
        offer_spec_quals,
        rank_product_lower,
    )
    source_ing_idx = (
        ingredient_source_indices[matched_ing_idx]
        if matched_ing_idx is not None and matched_ing_idx < len(ingredient_source_indices)
        else matched_ing_idx
    )
    return {
        'id': str(offer.id),
        'offer_identity_key': build_offer_identity_key(offer),
        'name': offer.name,
        'price': float(offer.price) if offer.price else 0,
        'original_price': float(offer.original_price) if offer.original_price else None,
        'savings': float(offer.savings) if offer.savings else 0,
        'category': offer.category,
        'matched_keyword': matched_keyword,
        'store_name': offer.store.name if offer.store else 'Willys',
        'product_url': offer.product_url,
        'is_multi_buy': offer.is_multi_buy or False,
        'multi_buy_quantity': offer.multi_buy_quantity,
        'weight_grams': float(offer.weight_grams) if offer.weight_grams else None,
        'qualifier_match': has_qualifier_match,
        'qualifier_specificity_rank': qualifier_specificity_rank,
        '_valid_ingredients': valid_ingredient_indices,
        '_matched_ing_idx': source_ing_idx,
        '_matched_expanded_ing_idx': matched_ing_idx,
    }


def _validated_match_signature(offer_data: Optional[dict]) -> tuple[str, int | None] | None:
    if not offer_data:
        return None
    return (
        offer_data.get('matched_keyword'),
        offer_data.get('_matched_expanded_ing_idx', offer_data.get('_matched_ing_idx')),
    )


def _validation_events_by_rule(events: list[dict], event_type: str) -> set[str]:
    return {
        str(event.get('rule'))
        for event in events
        if event.get('type') == event_type and event.get('rule')
    }


def _validate_shadow_selection(
    *,
    offer: Offer,
    offer_id: int,
    offer_data_cache: Optional[Dict],
    context: dict,
    selection: dict,
    ingredient_match_data_per_ing,
    ingredients_normalized: list[str],
    ingredient_source_texts: list[str],
    ingredient_source_indices: list[int],
    merged_ingredients: list[str],
    full_recipe_text: str,
) -> tuple[Optional[dict], list[dict]]:
    events: list[dict] = []
    selected_keyword = selection.get('selected_keyword')
    selected_ing_idx = selection.get('selected_ing_idx')
    if not selected_keyword or selected_ing_idx is None:
        return None, events

    offer_data = validate_offer_match_candidate(
        offer,
        offer_id,
        offer_data_cache,
        selected_keyword,
        selected_ing_idx,
        context['offer_precomputed'],
        context['offer_match_data'],
        context['effective_offer_data'],
        context['offer_match_keywords'],
        context['offer_name_normalized'],
        ingredient_match_data_per_ing,
        ingredients_normalized,
        ingredient_source_texts,
        ingredient_source_indices,
        merged_ingredients,
        full_recipe_text,
        events,
    )
    return offer_data, events


def analyze_ingredient_routing_shadow(
    offer: Offer,
    offer_id: int,
    offer_keywords: Optional[Dict],
    offer_data_cache: Optional[Dict],
    ingredient_match_data_per_ing,
    hinted_indices: Iterable[int],
    ingredients_normalized: list[str],
    ingredient_source_texts: list[str],
    ingredient_source_indices: list[int],
    merged_ingredients: list[str],
    full_recipe_text: str,
) -> dict[str, Any]:
    """Compare production fullscan selection with hinted selection without changing output."""
    hint_set = set(_normalized_candidate_indices(hinted_indices, len(ingredient_match_data_per_ing)))
    context = build_offer_match_context(
        offer,
        offer_id,
        offer_keywords,
        offer_data_cache,
    )
    full_selection = select_offer_match_candidate(
        collect_offer_match_candidates(
            ingredient_match_data_per_ing,
            context['offer_match_data'],
        ),
        ingredient_match_data_per_ing,
    )
    hinted_selection = select_offer_match_candidate(
        collect_offer_match_candidates(
            ingredient_match_data_per_ing,
            context['offer_match_data'],
            hint_set,
        ),
        ingredient_match_data_per_ing,
    )

    full_offer_data, full_events = _validate_shadow_selection(
        offer=offer,
        offer_id=offer_id,
        offer_data_cache=offer_data_cache,
        context=context,
        selection=full_selection,
        ingredient_match_data_per_ing=ingredient_match_data_per_ing,
        ingredients_normalized=ingredients_normalized,
        ingredient_source_texts=ingredient_source_texts,
        ingredient_source_indices=ingredient_source_indices,
        merged_ingredients=merged_ingredients,
        full_recipe_text=full_recipe_text,
    )
    hinted_offer_data, hinted_events = _validate_shadow_selection(
        offer=offer,
        offer_id=offer_id,
        offer_data_cache=offer_data_cache,
        context=context,
        selection=hinted_selection,
        ingredient_match_data_per_ing=ingredient_match_data_per_ing,
        ingredients_normalized=ingredients_normalized,
        ingredient_source_texts=ingredient_source_texts,
        ingredient_source_indices=ingredient_source_indices,
        merged_ingredients=merged_ingredients,
        full_recipe_text=full_recipe_text,
    )

    mismatch_classes: set[str] = set()
    full_initial_idx = full_selection.get('selected_ing_idx')
    hinted_initial_idx = hinted_selection.get('selected_ing_idx')
    if not hint_set:
        mismatch_classes.add('no_hint_for_routed_pair')
    if full_initial_idx is not None and full_initial_idx not in hint_set:
        mismatch_classes.add('fullscan_initial_winner_outside_hint')
    if full_selection.get('selected_by_fewer_keywords'):
        mismatch_classes.add('fullscan_fewer_keyword_preference_winner')
    if full_selection.get('selected_keyword') and not hinted_selection.get('selected_keyword'):
        mismatch_classes.add('hinted_initial_no_match')
    elif hinted_selection.get('selected_keyword') != full_selection.get('selected_keyword'):
        mismatch_classes.add('hinted_different_matched_keyword')
    elif (
        hinted_initial_idx is not None
        and full_initial_idx is not None
        and hinted_initial_idx != full_initial_idx
    ):
        mismatch_classes.add('hinted_same_keyword_different_ingredient_line')

    full_sig = _validated_match_signature(full_offer_data)
    hinted_sig = _validated_match_signature(hinted_offer_data)
    if full_sig != hinted_sig:
        mismatch_classes.add('validated_candidate_change')

    full_retry_events = [
        event for event in full_events
        if event.get('type') == 'validation_retry'
    ]
    for event in full_retry_events:
        to_idx = event.get('to_idx')
        if to_idx not in hint_set:
            mismatch_classes.add('validation_retry_moved_match_outside_hint')
            rule = event.get('rule')
            if rule == 'specialty_qualifier':
                mismatch_classes.add('specialty_retry_moved_match_outside_hint')
            elif rule == 'spice_fresh':
                mismatch_classes.add('spice_fresh_retry_moved_match_outside_hint')
            elif rule == 'carrier_flavor_context':
                mismatch_classes.add('carrier_flavor_context_retry_moved_match_outside_hint')
            if full_initial_idx in hint_set:
                mismatch_classes.add('hints_contain_initial_winner_but_miss_later_retry_candidates')

    hinted_reject_rules = _validation_events_by_rule(hinted_events, 'validation_reject')
    if full_sig and not hinted_sig:
        if 'processed_product' in hinted_reject_rules:
            mismatch_classes.add('processed_rule_rejected_hinted_match_fullscan_avoided')
        if hinted_reject_rules & {
            'carrier_flavor_context',
            'context_suppression',
            'secondary_ingredient_pattern',
            'descriptor_suppression',
            'ingredient_context_missing',
        }:
            mismatch_classes.add('carrier_flavor_context_rejected_hinted_match_fullscan_avoided')
        if 'product_name_blocker' in hinted_reject_rules:
            mismatch_classes.add('product_name_blocker_rejected_hinted_match_fullscan_avoided')

    if full_sig != hinted_sig and not mismatch_classes:
        mismatch_classes.add('unexplained_validated_mismatch')

    return {
        'hinted_indices': sorted(hint_set),
        'fullscan_selection': full_selection,
        'hinted_selection': hinted_selection,
        'fullscan_validated_signature': full_sig,
        'hinted_validated_signature': hinted_sig,
        'fullscan_validation_events': full_events,
        'hinted_validation_events': hinted_events,
        'mismatch_classes': sorted(mismatch_classes),
        'parity': full_sig == hinted_sig,
    }


def assign_offers_to_ingredient_groups(
    matched_offers: list[dict],
    ingredient_groups: list[dict],
    keyword_to_groups: dict[str, list[dict]],
    ingredient_match_data_per_ing,
    matched_keywords_set: set[str],
) -> None:
    """Assign matched offers to their Swedish ingredient groups."""
    for offer_data in matched_offers:
        matched_keyword = offer_data['matched_keyword']
        valid_ings = offer_data.get('_valid_ingredients')
        matched_expanded_idx = offer_data.get(
            '_matched_expanded_ing_idx',
            offer_data.get('_matched_ing_idx'),
        )
        matched_ing_keywords = (
            ingredient_match_data_per_ing[matched_expanded_idx].extracted_keywords
            if matched_expanded_idx is not None and matched_expanded_idx < len(ingredient_match_data_per_ing)
            else frozenset()
        )
        for alt_text, groups in keyword_to_groups.items():
            kw_len = len(matched_keyword)
            pos = alt_text.find(matched_keyword)
            found_valid = False
            while pos != -1:
                end_pos = pos + kw_len
                if end_pos >= len(alt_text) or not alt_text[end_pos].isalpha():
                    found_valid = True
                    break
                remaining = alt_text[end_pos:]
                for suffix in KEYWORD_COMPOUND_SUFFIXES:
                    if remaining.startswith(suffix):
                        suffix_end = end_pos + len(suffix)
                        if suffix_end >= len(alt_text) or not alt_text[suffix_end].isalpha():
                            found_valid = True
                            break
                if found_valid:
                    break
                if kw_len >= 5 and (pos == 0 or not alt_text[pos - 1].isalpha()):
                    if any(
                        remaining.startswith(other_kw)
                        for other_kw in matched_keywords_set
                        if other_kw != matched_keyword and len(other_kw) >= 3
                    ):
                        found_valid = True
                        break
                pos = alt_text.find(matched_keyword, pos + 1)
            if (
                not found_valid
                and matched_expanded_idx is not None
                and any(
                    matched_keyword in ing_kw and len(ing_kw) > len(matched_keyword)
                    for ing_kw in matched_ing_keywords
                )
                and any(group.get('_ing_idx') == matched_expanded_idx for group in groups)
            ):
                found_valid = True
            if not found_valid:
                continue
            if matched_keyword not in DESCRIPTOR_SUPPRESSION_PRIMARIES:
                has_primary = any(primary in alt_text for primary in DESCRIPTOR_SUPPRESSION_PRIMARIES)
                if has_primary:
                    marker_match = _DESCRIPTOR_PHRASE_MARKERS.search(alt_text)
                    if marker_match:
                        kw_before = alt_text.find(matched_keyword)
                        kw_after = alt_text.find(matched_keyword, marker_match.end())
                        if kw_after != -1 and (kw_before == -1 or kw_before >= marker_match.start()):
                            continue
            if _is_false_positive_blocked(matched_keyword, alt_text):
                words = alt_text.split()
                has_standalone = any(
                    word == matched_keyword
                    or (
                        word.startswith(matched_keyword)
                        and word[len(matched_keyword):] in ('er', 'ar', 'or', 'en', 'na', 'n', 'r', 's', 'erna')
                    )
                    for word in words
                )
                if not has_standalone:
                    continue
            for group in groups:
                if valid_ings is not None and group['_ing_idx'] not in valid_ings:
                    continue
                matched_idx = offer_data.get('_matched_expanded_ing_idx', offer_data.get('_matched_ing_idx'))
                if matched_idx is not None and group['_ing_idx'] != matched_idx:
                    continue
                if matched_keyword not in group['matched_keywords']:
                    group['matched_keywords'][matched_keyword] = []
                if offer_data not in group['matched_keywords'][matched_keyword]:
                    group['matched_keywords'][matched_keyword].append(offer_data)

    for offer_data in matched_offers:
        offer_data.pop('_valid_ingredients', None)


def apply_group_keyword_promotion(
    matched_offers: list[dict],
    ingredient_groups: list[dict],
) -> None:
    """Promote less-specific Swedish keywords when they hit the same groups."""
    kw_to_groups: dict[str, set[int]] = {}
    for group_index, group in enumerate(ingredient_groups):
        for keyword in group['matched_keywords']:
            kw_to_groups.setdefault(keyword, set()).add(group_index)

    all_matched_keywords = {offer['matched_keyword'] for offer in matched_offers}
    promote_map: dict[str, str] = {}
    sorted_keywords = sorted(all_matched_keywords, key=len)
    for index, shorter in enumerate(sorted_keywords):
        shorter_groups = kw_to_groups.get(shorter, set())
        for longer in sorted_keywords[index + 1:]:
            if shorter not in longer:
                continue
            if _is_false_positive_blocked(shorter, longer):
                continue
            longer_groups = kw_to_groups.get(longer, set())
            if not shorter_groups or shorter_groups <= longer_groups:
                promote_map[shorter] = longer
                break

    for key in list(promote_map):
        target = promote_map[key]
        while target in promote_map:
            target = promote_map[target]
        promote_map[key] = target

    if not promote_map:
        return

    for offer_data in matched_offers:
        keyword = offer_data['matched_keyword']
        if keyword in promote_map:
            offer_data['matched_keyword'] = promote_map[keyword]

    for group in ingredient_groups:
        new_keywords: dict[str, list[dict]] = {}
        for keyword, offers_list in group['matched_keywords'].items():
            target = promote_map.get(keyword, keyword)
            new_keywords.setdefault(target, []).extend(offers_list)
        group['matched_keywords'] = new_keywords

    grouped_offers = set()
    for group in ingredient_groups:
        for offers_list in group['matched_keywords'].values():
            for offer_data in offers_list:
                grouped_offers.add(id(offer_data))
    for offer_data in matched_offers:
        if id(offer_data) in grouped_offers:
            continue
        keyword = offer_data['matched_keyword']
        for group in ingredient_groups:
            if keyword in group['matched_keywords']:
                group['matched_keywords'][keyword].append(offer_data)
                break


def merge_exact_group_keywords(
    matched_offers: list[dict],
    ingredient_groups: list[dict],
) -> None:
    """Merge Swedish keyword variants that end up on the exact same groups."""
    kw_to_groups_final: dict[str, set[int]] = {}
    for group_index, group in enumerate(ingredient_groups):
        for keyword in group['matched_keywords']:
            kw_to_groups_final.setdefault(keyword, set()).add(group_index)

    same_group_keywords: dict[frozenset[int], list[str]] = {}
    for keyword, groups in kw_to_groups_final.items():
        same_group_keywords.setdefault(frozenset(groups), []).append(keyword)

    kw_offer_counts: dict[str, int] = {}
    for group in ingredient_groups:
        for keyword, offers_list in group['matched_keywords'].items():
            kw_offer_counts[keyword] = kw_offer_counts.get(keyword, 0) + len(offers_list)

    merge_map: dict[str, str] = {}
    for group_key, keywords in same_group_keywords.items():
        if len(keywords) <= 1:
            continue
        group_indices = list(group_key)
        if any(
            ingredient_groups[group_index].get('is_alternative')
            for group_index in group_indices
            if group_index < len(ingredient_groups)
        ):
            continue
        keywords.sort(key=lambda keyword: (-kw_offer_counts.get(keyword, 0), -len(keyword), keyword))
        canonical = keywords[0]
        for other in keywords[1:]:
            if other in canonical or canonical in other:
                merge_map[other] = canonical

    if not merge_map:
        return

    for offer_data in matched_offers:
        keyword = offer_data['matched_keyword']
        if keyword in merge_map:
            offer_data['matched_keyword'] = merge_map[keyword]

    for group in ingredient_groups:
        new_keywords: dict[str, list[dict]] = {}
        for keyword, offers_list in group['matched_keywords'].items():
            target = merge_map.get(keyword, keyword)
            new_keywords.setdefault(target, []).extend(offers_list)
        group['matched_keywords'] = new_keywords


def finalize_grouped_match_results(
    matcher,
    recipe: FoundRecipe,
    full_recipe_text: str,
    matched_offers: list[dict],
    ingredient_groups: list[dict],
    ingredients_normalized: list[str],
    total_ingredients: int,
    merged_ingredients: list[str],
    savings_cap_per_ingredient: float,
) -> dict:
    """Finalize Swedish grouped match scoring, display merging, and UI groups."""
    by_ingredient: dict[str, list[dict]] = {}
    for offer in matched_offers:
        keyword = offer['matched_keyword']
        by_ingredient.setdefault(keyword, []).append(offer)

    total_savings = 0.0
    ingredients_with_matches = 0
    processed_group_signatures = set()
    keywords_counted_via_groups = set()
    matched_signatures = set()
    savings_by_signature: dict[tuple, float] = {}
    best_keywords_per_group = set()

    savings_pct_sum = 0.0
    savings_pct_count = 0

    for group in ingredient_groups:
        if not group['matched_keywords']:
            continue

        group_signature = compute_group_match_signature(group)
        if group_signature in processed_group_signatures:
            continue

        group_best = 0.0
        group_best_offer = None
        for keyword, offers_list in group['matched_keywords'].items():
            for offer_data in offers_list:
                savings = offer_data.get('savings') or 0.0
                if savings > group_best:
                    group_best = savings
                    group_best_offer = offer_data

        group['best_savings'] = group_best
        ingredients_with_matches += 1
        matched_signatures.add(group_signature)
        processed_group_signatures.add(group_signature)
        keywords_counted_via_groups.update(group['matched_keywords'].keys())
        best_keywords_per_group.update(group['matched_keywords'].keys())

        if group_best > 0:
            total_savings += min(group_best, savings_cap_per_ingredient)
            savings_by_signature[group_signature] = group_best
            if group_best_offer:
                original_price = group_best_offer.get('original_price') or group_best_offer.get('price', 0)
                if original_price > 0:
                    savings_pct_sum += (group_best / original_price) * 100
                    savings_pct_count += 1

    for keyword, offers_list in by_ingredient.items():
        if keyword in keywords_counted_via_groups:
            continue
        best_offer = max(offers_list, key=lambda offer_data: offer_data.get('savings') or 0.0)
        best_savings = best_offer.get('savings') or 0.0
        ingredients_with_matches += 1
        match_signature = ((keyword,), ())
        matched_signatures.add(match_signature)
        if best_savings > 0:
            total_savings += min(best_savings, savings_cap_per_ingredient)
            savings_by_signature[match_signature] = best_savings
        keywords_counted_via_groups.add(keyword)
        best_keywords_per_group.add(keyword)
        if best_savings > 0:
            original_price = best_offer.get('original_price') or best_offer.get('price', 0)
            if original_price > 0:
                savings_pct_sum += (best_savings / original_price) * 100
                savings_pct_count += 1

    avg_savings_pct = round(savings_pct_sum / savings_pct_count, 1) if savings_pct_count > 0 else 0.0
    coverage_weight = (savings_pct_count / total_ingredients) if total_ingredients > 0 else 0.0
    total_savings_pct = round(avg_savings_pct * coverage_weight, 1)

    matched_offers = [offer_data for offer_data in matched_offers if offer_data['matched_keyword'] in best_keywords_per_group]

    recipe_name_lower = recipe.name.lower() if recipe.name else ''
    for offer_data in matched_offers:
        product_name_lower = (offer_data.get('name') or '').lower()
        for cheese_keyword, context_words in CHEESE_CONTEXT.items():
            if cheese_keyword in product_name_lower and any(context_word in recipe_name_lower for context_word in context_words):
                offer_data['context_match'] = True
                break

    for group in ingredient_groups:
        if not group['is_alternative'] or len(group['matched_keywords']) < 2:
            continue
        active_keywords = [keyword for keyword in group['matched_keywords'] if keyword in best_keywords_per_group]
        if len(active_keywords) < 2:
            continue
        combined_label = ' / '.join(active_keywords)
        for offer_data in matched_offers:
            if offer_data['matched_keyword'] in active_keywords:
                offer_data['matched_keyword'] = combined_label

    num_ingredients_matched = ingredients_with_matches
    typical_ingredients = 6
    match_score = min(100, int((num_ingredients_matched / typical_ingredients) * 100))
    coverage_pct = min(100, (num_ingredients_matched / total_ingredients * 100)) if total_ingredients > 0 else 0
    recipe_category = classify_recipe(matcher, recipe.name, full_recipe_text)
    budget_score = (coverage_pct / 100) * total_savings * num_ingredients_matched

    word_re = re.compile(r'[a-zåäöé]+')
    plural_suffixes = ('erna', 'arna', 'orna', 'er', 'ar', 'or', 'na', 'en', 'r', 's')
    standalone_keywords = set()
    standalone_re_cache = {}
    for offer_data in matched_offers:
        keyword = offer_data['matched_keyword']
        if keyword not in standalone_re_cache:
            standalone_re_cache[keyword] = re.compile(
                r'(?:^|\s)' + re.escape(keyword) + r'(?:' + '|'.join(plural_suffixes) + r')?(?:[^a-zåäö]|$)'
            )
        for ingredient_normalized in ingredients_normalized:
            if keyword in ingredient_normalized and standalone_re_cache[keyword].search(ingredient_normalized):
                standalone_keywords.add(keyword)
                break

    for offer_data in matched_offers:
        keyword = offer_data['matched_keyword']
        if keyword in standalone_keywords:
            continue
        display = keyword
        matched_idx = offer_data.get('_matched_expanded_ing_idx', offer_data.get('_matched_ing_idx'))
        search_ingredients = (
            [ingredients_normalized[matched_idx]]
            if matched_idx is not None and matched_idx < len(ingredients_normalized)
            else ingredients_normalized
        )
        for ingredient_normalized in search_ingredients:
            if keyword not in ingredient_normalized:
                continue
            for word in word_re.findall(ingredient_normalized):
                if keyword in word and len(word) > len(display):
                    candidate = word
                    for suffix in plural_suffixes:
                        if candidate.endswith(suffix) and len(candidate) - len(suffix) >= len(keyword):
                            candidate = candidate[:-len(suffix)]
                            break
                    if len(candidate) > len(display):
                        display = candidate
        if display != keyword:
            offer_data['display_keyword'] = display

    display_to_keywords: dict[str, set[str]] = {}
    for offer_data in matched_offers:
        keyword = offer_data['matched_keyword']
        display_keyword = offer_data.get('display_keyword', keyword)
        display_to_keywords.setdefault(display_keyword, set()).add(keyword)

    display_merge: dict[str, str] = {}
    for display_keyword, keywords in display_to_keywords.items():
        if len(keywords) <= 1:
            continue
        sorted_keywords = sorted(keywords, key=lambda keyword: (-len(keyword), keyword))
        canonical = sorted_keywords[0]
        for other in sorted_keywords[1:]:
            if other in canonical or canonical in other:
                display_merge[other] = canonical

    if display_merge:
        for offer_data in matched_offers:
            keyword = offer_data['matched_keyword']
            if keyword in display_merge:
                offer_data['matched_keyword'] = display_merge[keyword]
        for group in ingredient_groups:
            new_keywords: dict[str, list[dict]] = {}
            for keyword, offers_list in group['matched_keywords'].items():
                target = display_merge.get(keyword, keyword)
                new_keywords.setdefault(target, []).extend(offers_list)
            group['matched_keywords'] = new_keywords

    merge_excluded_family_keywords = set(FRESH_HERB_KEYWORDS) | set(SPICE_VS_FRESH_RULES.keys())
    family_to_primary_group = {}
    for group in ingredient_groups:
        family_key = frozenset(group.get('_family_keywords', set()))
        if not family_key or not group['matched_keywords']:
            continue
        if family_key & merge_excluded_family_keywords:
            continue
        merge_key = (family_key, frozenset(group.get('_extracted_keywords', frozenset())))
        family_to_primary_group.setdefault(merge_key, group)

    shadow_merged_groups = set()
    for group in ingredient_groups:
        if group['matched_keywords']:
            continue
        family_key = frozenset(group.get('_family_keywords', set()))
        if not family_key:
            continue
        if family_key & merge_excluded_family_keywords:
            continue
        merge_key = (family_key, frozenset(group.get('_extracted_keywords', frozenset())))
        primary_group = family_to_primary_group.get(merge_key)
        if not primary_group or primary_group is group:
            continue
        merged_originals = primary_group.setdefault('_merged_originals', [primary_group['original']])
        if group['original'] not in merged_originals:
            merged_originals.append(group['original'])
        shadow_merged_groups.add(id(group))

    if shadow_merged_groups:
        total_ingredients = max(1, len(merged_ingredients) - len(shadow_merged_groups))
        coverage_weight = (savings_pct_count / total_ingredients) if total_ingredients > 0 else 0.0
        total_savings_pct = round(avg_savings_pct * coverage_weight, 1)
        coverage_pct = min(100, (num_ingredients_matched / total_ingredients * 100)) if total_ingredients > 0 else 0
        budget_score = (coverage_pct / 100) * total_savings * num_ingredients_matched

    ui_groups = []
    for group in ingredient_groups:
        if id(group) in shadow_merged_groups:
            continue
        if group['matched_keywords']:
            merged_originals = group.get('_merged_originals')
            group_original = ' / '.join(merged_originals) if merged_originals else group['original']
            ui_groups.append({
                'original': group_original,
                'alternatives': group['alternatives'],
                'is_alternative': group['is_alternative'],
                'matched_keywords': list(group['matched_keywords'].keys()),
                'best_savings': group['best_savings'],
                'offers': [offer_data for offers in group['matched_keywords'].values() for offer_data in offers],
            })

    total_savings = sum(
        min(savings, savings_cap_per_ingredient)
        for savings in savings_by_signature.values()
    )

    for offer_data in matched_offers:
        offer_data.pop('_matched_expanded_ing_idx', None)

    return {
        'matched_offers': matched_offers,
        'match_score': match_score,
        'total_savings': round(total_savings, 2),
        'num_matches': len(matched_signatures),
        'num_offers': len(matched_offers),
        'recipe_category': recipe_category,
        'budget_score': round(budget_score, 2),
        'coverage_pct': round(coverage_pct, 1),
        'total_savings_pct': total_savings_pct,
        'avg_savings_pct': avg_savings_pct,
        'ingredient_groups': ui_groups,
    }


def get_classification_keywords() -> Dict[str, List[str]]:
    return {
        'meat': list(CLASSIFICATION_MEAT_KEYWORDS),
        'fish': list(CLASSIFICATION_FISH_KEYWORDS),
    }


def get_recipe_fts_config() -> str:
    return RECIPE_FTS_CONFIG


def ingredient_satisfies_product_name_blockers(
    ingredient_lower: str,
    product_blockers: list[str],
) -> bool:
    """Check ingredient-side blocker cues, preferring the most specific phrases."""
    phrase_blockers = [b for b in product_blockers if ' ' in b]
    blockers_to_check = phrase_blockers or product_blockers
    return any(b in ingredient_lower for b in blockers_to_check)


def ingredient_implies_whole_kyckling(ingredient_lower: str) -> bool:
    return (
        'kyckling' in ingredient_lower
        and all(cut not in ingredient_lower for cut in (
            'filé', 'file', 'innerfil', 'lårfil', 'larfil', 'bröst', 'brost',
            'ving', 'klubba', 'ben', 'strimlad',
        ))
        and (
            'hel kyckling' in ingredient_lower
            or 'helkyckling' in ingredient_lower
            or 'stor kyckling' in ingredient_lower
        )
    )


def classify_recipe(
    matcher,
    recipe_name: str,
    full_search_text: str,
) -> str:
    """Swedish recipe classification backend."""
    name_lower = recipe_name.lower()

    if any(label in name_lower for label in VEGETARIAN_LABELS):
        return VEGETARIAN

    has_meat_in_name = matcher._has_keyword_match(name_lower, matcher._meat_patterns_compiled)
    has_fish_in_name = matcher._has_keyword_match(name_lower, matcher._fish_patterns_compiled)

    if has_meat_in_name and not has_fish_in_name:
        return MEAT

    if has_fish_in_name and not has_meat_in_name:
        return FISH

    if has_meat_in_name and has_fish_in_name:
        meat_kws = matcher._keyword_match_fast(name_lower, matcher._meat_patterns_compiled)
        fish_kws = matcher._keyword_match_fast(name_lower, matcher._fish_patterns_compiled)
        meat_pos = min((name_lower.find(kw) for kw in meat_kws), default=999)
        fish_pos = min((name_lower.find(kw) for kw in fish_kws), default=999)
        return MEAT if meat_pos < fish_pos else FISH

    filtered_text = full_search_text
    for compound in SEASONING_COMPOUNDS:
        filtered_text = filtered_text.replace(compound, '')
    has_meat_anywhere = matcher._has_keyword_match(filtered_text, matcher._meat_patterns_compiled)
    has_fish_anywhere = matcher._has_keyword_match(filtered_text, matcher._fish_patterns_compiled)

    if has_meat_anywhere and not has_fish_anywhere:
        return MEAT

    if has_fish_anywhere and not has_meat_anywhere:
        return FISH

    if has_meat_anywhere and has_fish_anywhere:
        meat_kws = matcher._keyword_match_fast(full_search_text, matcher._meat_patterns_compiled)
        fish_kws = matcher._keyword_match_fast(full_search_text, matcher._fish_patterns_compiled)
        meat_pos = min((full_search_text.find(kw) for kw in meat_kws), default=999)
        fish_pos = min((full_search_text.find(kw) for kw in fish_kws), default=999)
        return MEAT if meat_pos < fish_pos else FISH

    return VEGETARIAN


def compute_qualifier_specificity_rank(
    ingredient_lower: str,
    matched_keyword: str | None,
    offer_specialty_qualifiers: Dict[str, set[str]],
    product_lower: str,
) -> int:
    """Rank exact Swedish specialty matches above broader family fallbacks."""
    if not matched_keyword:
        return 0

    specialty_keyword = SPECIALTY_KEYWORD_ALIASES.get(matched_keyword, matched_keyword)
    if specialty_keyword not in SPECIALTY_QUALIFIERS:
        return 0

    offer_quals = set(offer_specialty_qualifiers.get(specialty_keyword, set()))
    if not offer_quals:
        return 0

    requested_quals = [
        qualifier
        for qualifier in SPECIALTY_QUALIFIERS[specialty_keyword]
        if qualifier in ingredient_lower
    ]
    if not requested_quals:
        return 0

    if any(qualifier in product_lower for qualifier in requested_quals):
        return 2

    for qualifier in requested_quals:
        equivalents = QUALIFIER_EQUIVALENTS.get(qualifier, {qualifier})
        if any(eq in offer_quals for eq in equivalents):
            return 1

    return 0


def compute_group_match_signature(group: Dict) -> tuple[tuple[str, ...], tuple[tuple[str, tuple[str, ...]], ...]]:
    """Build a stable Swedish group-counting signature for matched ingredients."""
    matched_keywords = tuple(sorted(group.get('matched_keywords', {}).keys()))
    ingredient_lower = fix_swedish_chars(group.get('original', '')).lower()

    specialty_signature = []
    for matched_keyword in matched_keywords:
        specialty_keyword = SPECIALTY_KEYWORD_ALIASES.get(matched_keyword, matched_keyword)
        if specialty_keyword not in SPECIALTY_QUALIFIERS:
            continue
        requested_quals = tuple(sorted(
            qualifier
            for qualifier in SPECIALTY_QUALIFIERS[specialty_keyword]
            if qualifier in ingredient_lower
        ))
        if requested_quals:
            specialty_signature.append((specialty_keyword, requested_quals))

    return matched_keywords, tuple(specialty_signature)
