"""Hash-based version manifests for matcher/compiler cache invalidation.

These manifests are intentionally explicit and conservative. In phase 0 it is
better to invalidate too often than to silently reuse stale compiled data.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[3]


MATCHER_HASH_FILES = (
    "app/cache_manager.py",
    "app/languages/matcher_runtime.py",
    "app/recipe_matcher.py",
    "app/languages/categories.py",
    "app/languages/sv/category_utils.py",
    "app/languages/sv/food_filters.py",
    "app/languages/sv/normalization.py",
    "app/languages/sv/recipe_filters.py",
    "app/languages/sv/recipe_matcher_backend.py",
    "app/languages/sv/ingredient_matching/blocker_data.py",
    "app/languages/sv/ingredient_matching/carrier_context.py",
    "app/languages/sv/ingredient_matching/compiled_offers.py",
    "app/languages/sv/ingredient_matching/compiled_recipes.py",
    "app/languages/sv/ingredient_matching/compound_text.py",
    "app/languages/sv/ingredient_matching/compiled_recipes.py",
    "app/languages/sv/ingredient_matching/dairy_types.py",
    "app/languages/sv/ingredient_matching/delta_planner.py",
    "app/languages/sv/ingredient_matching/engine.py",
    "app/languages/sv/ingredient_matching/extraction.py",
    "app/languages/sv/ingredient_matching/extraction_patterns.py",
    "app/languages/sv/ingredient_matching/form_rules.py",
    "app/languages/sv/ingredient_matching/ingredient_data.py",
    "app/languages/sv/ingredient_matching/ingredient_routing.py",
    "app/languages/sv/ingredient_matching/keywords.py",
    "app/languages/sv/ingredient_matching/match_filters.py",
    "app/languages/sv/ingredient_matching/match_result.py",
    "app/languages/sv/ingredient_matching/matching.py",
    "app/languages/sv/ingredient_matching/normalization.py",
    "app/languages/sv/ingredient_matching/offer_identity.py",
    "app/languages/sv/ingredient_matching/offer_data.py",
    "app/languages/sv/ingredient_matching/parent_maps.py",
    "app/languages/sv/ingredient_matching/processed_rules.py",
    "app/languages/sv/ingredient_matching/recipe_context.py",
    "app/languages/sv/ingredient_matching/recipe_identity.py",
    "app/languages/sv/ingredient_matching/recipe_matcher_support.py",
    "app/languages/sv/ingredient_matching/recipe_text.py",
    "app/languages/sv/ingredient_matching/seasonal.py",
    "app/languages/sv/ingredient_matching/specialty_rules.py",
    "app/languages/sv/ingredient_matching/synonyms.py",
    "app/languages/sv/ingredient_matching/term_indexes.py",
    "app/languages/sv/ingredient_matching/validators.py",
    "app/languages/sv/ingredient_matching/versioning.py",
)

RECIPE_COMPILER_HASH_FILES = (
    "app/recipe_matcher.py",
    "app/languages/matcher_runtime.py",
    "app/languages/sv/normalization.py",
    "app/languages/sv/ingredient_matching/compound_text.py",
    "app/languages/sv/ingredient_matching/engine.py",
    "app/languages/sv/ingredient_matching/extraction.py",
    "app/languages/sv/ingredient_matching/extraction_patterns.py",
    "app/languages/sv/ingredient_matching/form_rules.py",
    "app/languages/sv/ingredient_matching/ingredient_data.py",
    "app/languages/sv/ingredient_matching/keywords.py",
    "app/languages/sv/ingredient_matching/match_filters.py",
    "app/languages/sv/ingredient_matching/normalization.py",
    "app/languages/sv/ingredient_matching/offer_identity.py",
    "app/languages/sv/ingredient_matching/parent_maps.py",
    "app/languages/sv/ingredient_matching/processed_rules.py",
    "app/languages/sv/ingredient_matching/recipe_context.py",
    "app/languages/sv/ingredient_matching/recipe_identity.py",
    "app/languages/sv/ingredient_matching/recipe_matcher_support.py",
    "app/languages/sv/ingredient_matching/recipe_text.py",
    "app/languages/sv/ingredient_matching/seasonal.py",
    "app/languages/sv/ingredient_matching/specialty_rules.py",
    "app/languages/sv/ingredient_matching/synonyms.py",
    "app/languages/sv/ingredient_matching/term_indexes.py",
    "app/languages/sv/ingredient_matching/validators.py",
    "app/languages/sv/ingredient_matching/versioning.py",
)

OFFER_COMPILER_HASH_FILES = (
    "app/languages/matcher_runtime.py",
    "app/languages/sv/ingredient_matching/blocker_data.py",
    "app/languages/sv/ingredient_matching/carrier_context.py",
    "app/languages/sv/ingredient_matching/compiled_offers.py",
    "app/languages/sv/ingredient_matching/compound_text.py",
    "app/languages/sv/ingredient_matching/dairy_types.py",
    "app/languages/sv/ingredient_matching/delta_planner.py",
    "app/languages/sv/ingredient_matching/engine.py",
    "app/languages/sv/ingredient_matching/extraction.py",
    "app/languages/sv/ingredient_matching/extraction_patterns.py",
    "app/languages/sv/ingredient_matching/form_rules.py",
    "app/languages/sv/ingredient_matching/keywords.py",
    "app/languages/sv/ingredient_matching/match_filters.py",
    "app/languages/sv/ingredient_matching/matching.py",
    "app/languages/sv/ingredient_matching/normalization.py",
    "app/languages/sv/ingredient_matching/offer_identity.py",
    "app/languages/sv/ingredient_matching/offer_data.py",
    "app/languages/sv/ingredient_matching/parent_maps.py",
    "app/languages/sv/ingredient_matching/processed_rules.py",
    "app/languages/sv/ingredient_matching/recipe_context.py",
    "app/languages/sv/ingredient_matching/recipe_matcher_support.py",
    "app/languages/sv/ingredient_matching/recipe_text.py",
    "app/languages/sv/ingredient_matching/seasonal.py",
    "app/languages/sv/ingredient_matching/specialty_rules.py",
    "app/languages/sv/ingredient_matching/synonyms.py",
    "app/languages/sv/ingredient_matching/term_indexes.py",
    "app/languages/sv/ingredient_matching/validators.py",
    "app/languages/sv/ingredient_matching/versioning.py",
)


def _hash_manifest(prefix: str, manifest: tuple[str, ...]) -> str:
    digest = sha256()
    for rel_path in manifest:
        digest.update(rel_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update((REPO_ROOT / rel_path).read_bytes())
        digest.update(b"\0")
    return f"{prefix}-{digest.hexdigest()[:12]}"


MATCHER_VERSION = _hash_manifest("matcher", MATCHER_HASH_FILES)
RECIPE_COMPILER_VERSION = _hash_manifest("recipe-compiler", RECIPE_COMPILER_HASH_FILES)
OFFER_COMPILER_VERSION = _hash_manifest("offer-compiler", OFFER_COMPILER_HASH_FILES)


def get_version_triplet() -> tuple[str, str, str]:
    """Return the current hash-based build version triple."""
    return (
        MATCHER_VERSION,
        RECIPE_COMPILER_VERSION,
        OFFER_COMPILER_VERSION,
    )
