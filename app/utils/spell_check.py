"""
Spell checker for recipe ingredient text.

Compares ingredient words against known keywords from the active market
matching profile and corrects likely typos using Levenshtein distance.

Rules:
- Minimum 5 characters (short words are too ambiguous)
- Max 1 edit distance (distance 2 gives too many false positives)
- Only corrects if exactly ONE candidate matches (ambiguous = skip)
- Skips words already known (keywords, stop words, flavor words, etc.)
- Only corrects toward ingredient keywords, not flavor/stop words.
"""

import re
import json
from typing import FrozenSet, List, Dict, Optional, Tuple, Set
from loguru import logger

try:
    from languages.market_runtime import (
        build_spell_check_profile,
        get_default_spell_excluded_words,
        normalize_ingredient_text,
    )
except ModuleNotFoundError:
    from app.languages.market_runtime import (
        build_spell_check_profile,
        get_default_spell_excluded_words,
        normalize_ingredient_text,
    )


# Word list built lazily on first use
_KNOWN_WORDS: Optional[Set[str]] = None
_CORRECTION_TARGETS: Optional[Set[str]] = None
_SAFE_NON_FOOD_WORDS: FrozenSet[str] = frozenset()
_INFLECTION_SUFFIXES: Tuple[str, ...] = ()

# Minimum word length for correction attempts
MIN_WORD_LENGTH = 5

# Known false-positive correction pairs. Keep these in language data as well as
# DB seed so existing installations get the protection immediately after deploy.
DEFAULT_SPELL_EXCLUDED_WORDS: FrozenSet[Tuple[str, str]] = get_default_spell_excluded_words()


def _build_word_lists():
    """Build the known-word set and correction target set from ingredient_matching data."""
    global _KNOWN_WORDS, _CORRECTION_TARGETS, _SAFE_NON_FOOD_WORDS, _INFLECTION_SUFFIXES

    profile = build_spell_check_profile(MIN_WORD_LENGTH)
    _KNOWN_WORDS = set(profile.known_words)
    _CORRECTION_TARGETS = set(profile.correction_targets)
    _SAFE_NON_FOOD_WORDS = profile.safe_non_food_words
    _INFLECTION_SUFFIXES = profile.inflection_suffixes

    logger.debug(
        f"Spell check: {len(_KNOWN_WORDS)} known words, "
        f"{len(_CORRECTION_TARGETS)} correction targets (>= {MIN_WORD_LENGTH} chars)"
    )


def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)

    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost: 0 if same char, 1 if different
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(
                curr_row[j] + 1,       # insert
                prev_row[j + 1] + 1,   # delete
                prev_row[j] + cost     # substitute
            ))
        prev_row = curr_row

    return prev_row[-1]


def _max_distance(word_length: int) -> int:
    """Maximum allowed edit distance based on word length.

    Always 1 because distance 2 produces too many false positives with
    compact food vocabularies.
    """
    return 1


def _is_language_inflection(word: str) -> bool:
    """Check if a word looks like a valid inflected form of a known word."""
    if _KNOWN_WORDS is None:
        _build_word_lists()

    for suffix in _INFLECTION_SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            stem = word[:-len(suffix)]
            if stem in _KNOWN_WORDS:
                return True

    return False


def _is_compound_of_known(word: str) -> bool:
    """Check if a word is a valid compound of two known parts.

    E.g., "potatischips" = "potatis" + "chips" — both parts known → skip.
    But "kycklingfile" = "kyckling" + "file" — "file" NOT known → don't skip
    (it's a typo of "filé").

    Also handles optional 's' binding letter: "vitlöks" + "klyftor".
    """
    if _KNOWN_WORDS is None:
        _build_word_lists()

    for known in _KNOWN_WORDS:
        if len(known) < 4:
            continue

        # Check as prefix: known + remainder
        if word.startswith(known) and len(word) > len(known):
            remainder = word[len(known):]
            # Direct remainder is known
            if remainder in _KNOWN_WORDS and len(remainder) >= 3:
                return True
            # Binding 's': "vitlöks" → "vitlök" + "s" + remainder
            if remainder.startswith('s') and remainder[1:] in _KNOWN_WORDS and len(remainder) > 3:
                return True

        # Check as suffix: remainder + known
        if word.endswith(known) and len(word) > len(known):
            remainder = word[:len(word) - len(known)]
            if remainder in _KNOWN_WORDS and len(remainder) >= 3:
                return True
            # Binding 's'
            if remainder.endswith('s') and remainder[:-1] in _KNOWN_WORDS and len(remainder) > 3:
                return True

    return False


def _find_correction(word: str) -> Optional[str]:
    """Find a spelling correction for a word, or None if no unique match."""
    if _CORRECTION_TARGETS is None:
        _build_word_lists()

    # Skip words that look like valid inflections of known words
    if _is_language_inflection(word):
        return None

    max_dist = _max_distance(len(word))
    candidates = []

    for target in _CORRECTION_TARGETS:
        # Quick length filter — edit distance can't be less than length difference
        if abs(len(target) - len(word)) > max_dist:
            continue

        dist = _levenshtein(word, target)
        if dist <= max_dist:
            candidates.append((target, dist))

    if not candidates:
        return None

    # Sort by distance, then alphabetically for stability
    candidates.sort(key=lambda x: (x[0], x[1]))

    # Only correct if there's exactly one candidate at the best distance
    best_dist = candidates[0][1]
    best_candidates = [c for c in candidates if c[1] == best_dist]

    if len(best_candidates) == 1:
        return best_candidates[0][0]

    # Ambiguous — multiple equally-close candidates
    return None


# Regex to split ingredient text into words
# Include common Latin food-word characters used by current market profiles.
_WORD_RE = re.compile(r'[a-zåäöüéèêñ]+', re.IGNORECASE)


def check_ingredient(ingredient: str) -> List[Tuple[str, str]]:
    """Check a single ingredient string for spelling errors.

    Returns list of (original_word, corrected_word) tuples.
    """
    if _KNOWN_WORDS is None:
        _build_word_lists()

    corrections = []

    for match in _WORD_RE.finditer(ingredient.lower()):
        word = match.group()

        # Skip short words
        if len(word) < MIN_WORD_LENGTH:
            continue

        # Skip words we already know
        if word in _KNOWN_WORDS:
            continue

        # Skip common non-food words that are easily confused with food terms
        if word in _SAFE_NON_FOOD_WORDS:
            continue

        # Skip words that look like compound words containing a known keyword
        # (e.g., "potatischips" contains "potatis", "snacksmorötter" contains "morötter")
        if _is_compound_of_known(word):
            continue

        # Skip words that normalization already handles (e.g. kycklingfile → kycklingfilé)
        normalized = normalize_ingredient_text(word)
        if normalized != word and normalized in _KNOWN_WORDS:
            continue

        correction = _find_correction(word)
        if correction:
            if (word, correction) in DEFAULT_SPELL_EXCLUDED_WORDS:
                continue
            corrections.append((word, correction))

    return corrections


def apply_corrections_to_ingredients(
    ingredients: List[str],
    excluded_per_recipe: Optional[Set[str]] = None,
    excluded_global: Optional[Set[Tuple[str, str]]] = None,
) -> Tuple[List[str], List[Dict]]:
    """Apply spell corrections to a list of ingredient strings.

    Args:
        ingredients: List of ingredient strings from recipe.
        excluded_per_recipe: Set of original_word strings to skip for this recipe.
        excluded_global: Set of (original_word, corrected_word) tuples to skip globally.

    Returns:
        Tuple of (corrected_ingredients, corrections_made) where
        corrections_made is a list of dicts with keys:
            ingredient_index, original_word, corrected_word
    """
    if not ingredients:
        return ingredients, []

    if excluded_per_recipe is None:
        excluded_per_recipe = set()
    if excluded_global is None:
        excluded_global = set()
    excluded_global = set(excluded_global) | set(DEFAULT_SPELL_EXCLUDED_WORDS)

    corrected = list(ingredients)
    all_corrections = []

    for idx, ingredient in enumerate(ingredients):
        if not isinstance(ingredient, str):
            continue

        corrections = check_ingredient(ingredient)
        for original, correction in corrections:
            # Check per-recipe exclusion (word only, index-independent)
            if original in excluded_per_recipe:
                continue

            # Check global exclusion
            if (original, correction) in excluded_global:
                continue

            # Replace in ingredient text (case-insensitive, first occurrence)
            pattern = re.compile(re.escape(original), re.IGNORECASE)
            new_text = pattern.sub(correction, corrected[idx], count=1)
            if new_text != corrected[idx]:
                corrected[idx] = new_text
                all_corrections.append({
                    'ingredient_index': idx,
                    'original_word': original,
                    'corrected_word': correction,
                })

    return corrected, all_corrections


def _revert_word_in_recipe(db, recipe_id, corrected_word: str, original_word: str) -> bool:
    """Restore original word in one recipe ingredient line."""
    from models import FoundRecipe

    recipe = db.query(FoundRecipe).filter(FoundRecipe.id == recipe_id).first()
    if not recipe or not recipe.ingredients:
        return False

    ingredients = json.loads(recipe.ingredients) if isinstance(recipe.ingredients, str) else list(recipe.ingredients)
    pattern = re.compile(re.escape(corrected_word), re.IGNORECASE)

    for idx, ingredient in enumerate(ingredients):
        if isinstance(ingredient, str) and pattern.search(ingredient):
            ingredients[idx] = pattern.sub(original_word, ingredient, count=1)
            recipe.ingredients = ingredients
            return True

    return False


def sync_default_spell_exclusions() -> Dict[str, int]:
    """Seed default global spell exclusions and revert any active false positives."""
    from sqlalchemy import text
    from database import get_db_session
    from models import SpellCorrection

    inserted = 0
    reverted = 0
    deleted = 0

    with get_db_session() as db:
        for original_word, corrected_word in sorted(DEFAULT_SPELL_EXCLUDED_WORDS):
            result = db.execute(
                text("""
                    INSERT INTO spell_excluded_words (original_word, corrected_word)
                    VALUES (:orig, :corr)
                    ON CONFLICT DO NOTHING
                """),
                {"orig": original_word, "corr": corrected_word},
            )
            inserted += result.rowcount or 0

            affected = db.query(SpellCorrection).filter(
                SpellCorrection.original_word == original_word,
                SpellCorrection.corrected_word == corrected_word,
                SpellCorrection.excluded == False,  # noqa: E712
            ).all()

            for correction in affected:
                if _revert_word_in_recipe(db, correction.recipe_id, corrected_word, original_word):
                    reverted += 1

            delete_result = db.execute(
                text("""
                    DELETE FROM spell_corrections
                    WHERE original_word = :orig AND corrected_word = :corr
                """),
                {"orig": original_word, "corr": corrected_word},
            )
            deleted += delete_result.rowcount or 0

        db.commit()

    return {"inserted": inserted, "reverted": reverted, "deleted": deleted}
