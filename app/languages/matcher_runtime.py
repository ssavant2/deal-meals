"""Thin matcher backend adapter for locale/country-aware cache work.

This app currently only has a production-ready Swedish matcher backend, but the
shared cache/matcher orchestration code should not hardcode ``languages.sv``
more than necessary. This module centralizes backend selection so future
country/language implementations can plug in behind the same API.
"""

from __future__ import annotations

import importlib
import os
from types import ModuleType

from .i18n import DEFAULT_LANGUAGE, normalize_language_code
from .market_runtime import normalize_market_text


MATCHER_LANGUAGE_ENV = "MATCHER_LANGUAGE"
RECIPE_FTS_CONFIG_ENV = "RECIPE_FTS_CONFIG"
FALLBACK_MATCHER_LANGUAGE = "sv"


def _normalize_language_code(value: str | None) -> str:
    return normalize_language_code(value) if value else DEFAULT_LANGUAGE


def get_matcher_language() -> str:
    """Return the configured matcher backend language code.

    Today this is environment-driven because there is no persisted market/country
    selector for the matching engine yet. UI language remains separate.
    """
    return _normalize_language_code(os.getenv(MATCHER_LANGUAGE_ENV))


def _import_language_module(language: str, suffix: str) -> ModuleType:
    errors: list[Exception] = []
    for base in ("languages", "app.languages"):
        module_name = f"{base}.{language}.{suffix}"
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            errors.append(exc)
    raise ModuleNotFoundError(
        f"Could not import matcher backend module for language '{language}' and suffix '{suffix}'"
    ) from errors[-1]


def _load_ingredient_matching_package() -> ModuleType:
    requested = get_matcher_language()
    for candidate in (requested, DEFAULT_LANGUAGE, FALLBACK_MATCHER_LANGUAGE):
        try:
            return _import_language_module(candidate, "ingredient_matching")
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("No usable ingredient_matching backend found")


def _load_recipe_match_backend_module() -> ModuleType:
    requested = get_matcher_language()
    for candidate in (requested, DEFAULT_LANGUAGE, FALLBACK_MATCHER_LANGUAGE):
        try:
            return _import_language_module(candidate, "recipe_matcher_backend")
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("No usable recipe_matcher_backend found")


_MATCHER_PACKAGE = _load_ingredient_matching_package()
_RECIPE_MATCH_BACKEND = _load_recipe_match_backend_module()
MATCHER_LANGUAGE = getattr(_MATCHER_PACKAGE, "__name__", "").split(".")[-2] or FALLBACK_MATCHER_LANGUAGE


def _build_empty_recipe_ingredient_term_map(compiled_recipe_payload, routing_terms):
    return {str(term): set() for term in routing_terms if term}


MATCHER_VERSION = _MATCHER_PACKAGE.MATCHER_VERSION
RECIPE_COMPILER_VERSION = _MATCHER_PACKAGE.RECIPE_COMPILER_VERSION
OFFER_COMPILER_VERSION = _MATCHER_PACKAGE.OFFER_COMPILER_VERSION

precompute_offer_data = _MATCHER_PACKAGE.precompute_offer_data
extract_keywords_from_product = _MATCHER_PACKAGE.extract_keywords_from_product
load_compiled_offer_runtime_cache = _MATCHER_PACKAGE.load_compiled_offer_runtime_cache
load_compiled_recipe_runtime_cache = _MATCHER_PACKAGE.load_compiled_recipe_runtime_cache
load_compiled_recipe_payload_cache = _MATCHER_PACKAGE.load_compiled_recipe_payload_cache
load_compiled_offer_match_map = _MATCHER_PACKAGE.load_compiled_offer_match_map
build_offer_candidate_term_map = _MATCHER_PACKAGE.build_offer_candidate_term_map
build_offer_candidate_terms = _MATCHER_PACKAGE.build_offer_candidate_terms
build_offer_identity_key = _MATCHER_PACKAGE.build_offer_identity_key
build_recipe_identity_key = _MATCHER_PACKAGE.build_recipe_identity_key
build_recipe_search_text = _MATCHER_PACKAGE.build_recipe_search_text
build_recipe_search_text_map = _MATCHER_PACKAGE.build_recipe_search_text_map
build_relevant_offer_map_from_search_texts = _MATCHER_PACKAGE.build_relevant_offer_map_from_search_texts
build_candidate_map_from_term_postings = _MATCHER_PACKAGE.build_candidate_map_from_term_postings
build_candidate_term_detail_from_term_postings = _MATCHER_PACKAGE.build_candidate_term_detail_from_term_postings
build_recipe_ingredient_term_map = getattr(
    _MATCHER_PACKAGE,
    "build_recipe_ingredient_term_map",
    _build_empty_recipe_ingredient_term_map,
)
build_fts_keyword_set = _MATCHER_PACKAGE.build_fts_keyword_set
ensure_compiled_offer_term_index_table = _MATCHER_PACKAGE.ensure_compiled_offer_term_index_table
ensure_compiled_recipe_term_index_table = _MATCHER_PACKAGE.ensure_compiled_recipe_term_index_table
load_compiled_offer_term_manifest = _MATCHER_PACKAGE.load_compiled_offer_term_manifest
load_compiled_offer_term_postings = _MATCHER_PACKAGE.load_compiled_offer_term_postings
load_compiled_recipe_term_postings = _MATCHER_PACKAGE.load_compiled_recipe_term_postings
resolve_recipe_match_runtime_data = _MATCHER_PACKAGE.resolve_recipe_match_runtime_data
classify_current_offer_changes = _MATCHER_PACKAGE.classify_current_offer_changes
classify_current_recipe_changes = _MATCHER_PACKAGE.classify_current_recipe_changes
plan_offer_delta_recipe_impacts = _MATCHER_PACKAGE.plan_offer_delta_recipe_impacts
plan_combined_delta_recipe_impacts = _MATCHER_PACKAGE.plan_combined_delta_recipe_impacts
load_persisted_offer_recipe_map = _MATCHER_PACKAGE.load_persisted_offer_recipe_map
refresh_compiled_offer_match_data = _MATCHER_PACKAGE.refresh_compiled_offer_match_data
refresh_compiled_recipe_match_data = _MATCHER_PACKAGE.refresh_compiled_recipe_match_data
refresh_compiled_recipe_match_data_for_recipe_ids = _MATCHER_PACKAGE.refresh_compiled_recipe_match_data_for_recipe_ids
refresh_compiled_offer_term_index = _MATCHER_PACKAGE.refresh_compiled_offer_term_index
refresh_compiled_recipe_term_index = _MATCHER_PACKAGE.refresh_compiled_recipe_term_index
refresh_compiled_recipe_term_index_for_recipe_ids = _MATCHER_PACKAGE.refresh_compiled_recipe_term_index_for_recipe_ids

_NORMALIZATION_MODULE = _import_language_module(MATCHER_LANGUAGE, "ingredient_matching.normalization")
_SEASONAL_MODULE = _import_language_module(MATCHER_LANGUAGE, "ingredient_matching.seasonal")
_RECIPE_TEXT_MODULE = _import_language_module(MATCHER_LANGUAGE, "ingredient_matching.recipe_text")
_SYNONYMS_MODULE = _import_language_module(MATCHER_LANGUAGE, "ingredient_matching.synonyms")
_RECIPE_FILTERS_MODULE = _import_language_module(MATCHER_LANGUAGE, "recipe_filters")

_SPACE_NORMALIZATIONS = _NORMALIZATION_MODULE._SPACE_NORMALIZATIONS
_apply_space_normalizations = _NORMALIZATION_MODULE._apply_space_normalizations
expand_grouped_ingredient_text = _RECIPE_TEXT_MODULE.expand_grouped_ingredient_text
rewrite_buljong_eller_fond = _RECIPE_TEXT_MODULE.rewrite_buljong_eller_fond
INGREDIENT_PARENTS = _SYNONYMS_MODULE.INGREDIENT_PARENTS
is_boring_recipe = _RECIPE_FILTERS_MODULE.is_boring_recipe
is_buffet_or_party_recipe = _SEASONAL_MODULE.is_buffet_or_party_recipe
is_off_season_recipe = _SEASONAL_MODULE.is_off_season_recipe


def match_recipe_to_offers_backend(*args, **kwargs):
    """Dispatch recipe matching through the active matcher backend."""
    return _RECIPE_MATCH_BACKEND.match_recipe_to_offers(*args, **kwargs)


def get_filtered_offers_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.get_filtered_offers(*args, **kwargs)


def analyze_unmatched_offers_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.analyze_unmatched_offers(*args, **kwargs)


def build_keyword_patterns_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.build_keyword_patterns(*args, **kwargs)


def keyword_match_fast_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.keyword_match_fast(*args, **kwargs)


def has_keyword_match_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.has_keyword_match(*args, **kwargs)


def build_initial_ingredient_groups_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.build_initial_ingredient_groups(*args, **kwargs)


def apply_pre_promotion_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.apply_pre_promotion(*args, **kwargs)


def assign_offers_to_ingredient_groups_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.assign_offers_to_ingredient_groups(*args, **kwargs)


def apply_group_keyword_promotion_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.apply_group_keyword_promotion(*args, **kwargs)


def merge_exact_group_keywords_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.merge_exact_group_keywords(*args, **kwargs)


def finalize_grouped_match_results_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.finalize_grouped_match_results(*args, **kwargs)


def prepare_offer_match_candidate_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.prepare_offer_match_candidate(*args, **kwargs)


def build_offer_match_context_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.build_offer_match_context(*args, **kwargs)


def collect_offer_match_candidates_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.collect_offer_match_candidates(*args, **kwargs)


def select_offer_match_candidate_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.select_offer_match_candidate(*args, **kwargs)


def validate_offer_match_candidate_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.validate_offer_match_candidate(*args, **kwargs)


def analyze_ingredient_routing_shadow_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.analyze_ingredient_routing_shadow(*args, **kwargs)


def get_classification_keywords_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.get_classification_keywords(*args, **kwargs)


def get_recipe_fts_config_backend(*args, **kwargs):
    configured = os.getenv(RECIPE_FTS_CONFIG_ENV)
    if configured:
        return configured.strip()
    return _RECIPE_MATCH_BACKEND.get_recipe_fts_config(*args, **kwargs)


def classify_recipe_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.classify_recipe(*args, **kwargs)


def ingredient_implies_whole_kyckling_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.ingredient_implies_whole_kyckling(*args, **kwargs)


def ingredient_satisfies_product_name_blockers_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.ingredient_satisfies_product_name_blockers(*args, **kwargs)


def compute_qualifier_specificity_rank_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.compute_qualifier_specificity_rank(*args, **kwargs)


def compute_group_match_signature_backend(*args, **kwargs):
    return _RECIPE_MATCH_BACKEND.compute_group_match_signature(*args, **kwargs)
