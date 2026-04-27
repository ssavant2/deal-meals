"""Validation helpers for Swedish ingredient matching.

Related data:
- specialty_rules.py — SPECIALTY_QUALIFIERS, BIDIRECTIONAL_PER_KEYWORD, QUALIFIER_EQUIVALENTS
- processed_rules.py — PROCESSED_PRODUCT_RULES, SPICE_VS_FRESH_RULES
- form_rules.py — fresh/dried/frozen indicator sets used by spice/fresh validation
- compound_text.py — word-boundary helpers used by processed-product validation
"""

import re
from typing import Dict, Set

from .compound_text import _is_whole_word
from .extraction import extract_keywords_from_ingredient
from .recipe_text import parse_eller_alternatives
from .processed_rules import (
    PROCESSED_RULES_COMPOUND_EXEMPTIONS,
    PROCESSED_PRODUCT_RULES,
    STRICT_PROCESSED_RULES,
    _PROCESSED_INDICATOR_EQUIVALENTS,
    SPICE_VS_FRESH_RULES,
)
from .specialty_rules import (
    SPECIALTY_QUALIFIERS,
    BIDIRECTIONAL_SPECIALTY_QUALIFIERS,
    BIDIRECTIONAL_PER_KEYWORD,
    QUALIFIER_EQUIVALENTS,
)

_SMOKED_SPECIFIC_QUALIFIERS = frozenset({'kallrökt', 'kallrokt', 'varmrökt', 'varmrokt'})
_GENERIC_SMOKED_QUALIFIERS = frozenset({'rökt', 'rokt'})
_SWEET_CHILI_QUALIFIERS = frozenset({'sweet', 'söt', 'sota'})
_UNSWEETENED_CHILI_QUALIFIERS = frozenset({'osötad', 'osotad', 'osötat', 'osotat'})
_RE_ANIS_WORD = re.compile(r'\banis\b')
_RE_KUMMIN_WORD = re.compile(r'\bkummin\b')
_PAPRIKA_FRESH_COLOR_QUALIFIERS = frozenset({
    'röd', 'rod', 'röda', 'roda',
    'grön', 'gron', 'gröna', 'grona',
    'gul', 'gula',
    'orange',
})
_PAPRIKA_SPICE_INDICATORS = frozenset({
    'krydda', 'paprikakrydda',
    'malen', 'malna', 'malet', 'pulver',
    'rökt', 'rokt', 'stark',
    'tsk', 'tesked', 'krm',
})
_SPECIALTY_BASE_KEYWORD_ALIASES: Dict[str, Set[str]] = {
    # Smoked paprika checks live on the paprika base family even when the
    # recipe/product wording uses the compound spice keyword.
    'paprika': {'paprikapulver', 'paprikakrydda'},
}


def _qualifier_present_in_text(qualifier: str, text: str) -> bool:
    # Generic "rökt" should only count as its own word. Otherwise "varmrökt"
    # and "kallrökt" accidentally satisfy smoked-equivalence checks via the
    # shared substring and hot/cold-smoked salmon collapse together.
    if qualifier in _GENERIC_SMOKED_QUALIFIERS:
        return _is_whole_word(qualifier, text)
    return qualifier in text


def _prune_shadowed_smoked_qualifiers(qualifiers: Set[str]) -> Set[str]:
    if any(q in qualifiers for q in _SMOKED_SPECIFIC_QUALIFIERS):
        return {q for q in qualifiers if q not in _GENERIC_SMOKED_QUALIFIERS}
    return qualifiers


def _specialty_alternative_texts(base_word: str, qualifiers: Set[str], ingredient_lower: str) -> list[str]:
    if ' eller ' not in ingredient_lower and '(eller' not in ingredient_lower:
        return [ingredient_lower]

    alternatives = [alt.strip() for alt in parse_eller_alternatives(ingredient_lower) if alt.strip()]
    if len(alternatives) <= 1:
        return [ingredient_lower]

    full_keywords = set(extract_keywords_from_ingredient(ingredient_lower))
    candidate_texts = []
    base_aliases = _SPECIALTY_BASE_KEYWORD_ALIASES.get(base_word, set())
    for alt in alternatives:
        alt_keywords = set(extract_keywords_from_ingredient(alt))
        alt_has_base = (
            base_word in alt
            or base_word in alt_keywords
            or any(alias in alt_keywords for alias in base_aliases)
        )
        alt_has_qualifier = any(q in alt for q in qualifiers)

        # "7 tomater, färska eller 1 burk krossade" → the second alternative omits
        # the base word, but the qualifier still clearly belongs to the same family.
        if not alt_has_base and alt_has_qualifier and base_word in full_keywords:
            alt = f"{alt} {base_word}"
            alt_keywords = set(extract_keywords_from_ingredient(alt))
            alt_has_base = base_word in alt or base_word in alt_keywords

        if alt_has_base or alt_has_qualifier:
            candidate_texts.append(alt)

    return candidate_texts or [ingredient_lower]


def ingredient_has_spice_indicator(indicators: Set[str], ingredient_lower: str, base_word: str = "") -> bool:
    """
    Spice indicators like "hel" should count as standalone words, not arbitrary
    substrings inside words like "helst". Compound forms such as
    "kardemummakapslar" should still count via base_word+indicator.
    """
    for indicator in indicators:
        idx = ingredient_lower.find(indicator)
        while idx != -1:
            left_ok = (idx == 0 or not ingredient_lower[idx - 1].isalpha())
            end_idx = idx + len(indicator)
            right_ok = (end_idx == len(ingredient_lower) or not ingredient_lower[end_idx].isalpha())
            if left_ok and right_ok:
                return True
            idx = ingredient_lower.find(indicator, idx + 1)
        if base_word and (base_word + indicator) in ingredient_lower:
            return True
    return False


def _has_fennel_spice_list_context(ingredient_lower: str) -> bool:
    return (
        'eller' in ingredient_lower
        and ('fänkål' in ingredient_lower or 'fankal' in ingredient_lower)
        and (_RE_ANIS_WORD.search(ingredient_lower) or _RE_KUMMIN_WORD.search(ingredient_lower))
    )


def _ingredient_implies_whole_kyckling(ingredient_lower: str) -> bool:
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


def check_processed_product_rules(product_lower: str, ingredient_lower: str) -> bool:
    """
    Check if a product passes PROCESSED_PRODUCT_RULES against a SINGLE ingredient.

    Returns True if the match is allowed, False if it should be blocked.

    This function is designed for per-ingredient validation in recipe_matcher,
    where the initial match used combined ingredient text (which can cause
    false positives from cross-ingredient contamination, e.g., "skalade" from
    "skalade mandlar" falsely satisfying the check for "Hela Skalade Tomater").
    """
    for base_word, processed_indicators in PROCESSED_PRODUCT_RULES.items():
        if base_word in product_lower:
            # Skip exempt compound words (e.g., "körsbärstomater")
            exemptions = PROCESSED_RULES_COMPOUND_EXEMPTIONS.get(base_word)
            if exemptions and any(ex in product_lower for ex in exemptions):
                continue
            if base_word in STRICT_PROCESSED_RULES:
                # Base word must appear in the ingredient too (not just the product).
                # Prevents cross-ingredient leakage: "Kryddmix Kyckling Guld" has
                # base_word 'kryddmix' + indicator 'kyckling'. Without this check,
                # the product matches ingredient "kycklingfile" (kyckling found as
                # indicator) even though the ingredient has nothing to do with kryddmix.
                if base_word not in ingredient_lower:
                    return False
                product_indicators = [ind for ind in processed_indicators if ind in product_lower]
                # Expand with equivalents: "malen" also matches "mald"/"malet"/"malna"
                expanded_indicators = set(product_indicators)
                for ind in product_indicators:
                    expanded_indicators.update(_PROCESSED_INDICATOR_EQUIVALENTS.get(ind, ()))
                # Use word-boundary check: 'riven' must be standalone, not suffix
                # of compound like 'finriven' (cooking instruction ≠ product form)
                if product_indicators and not any(_is_whole_word(ind, ingredient_lower) for ind in expanded_indicators):
                    # Compound fallback: check if base_word + product's OWN indicator appears
                    # in ingredient as a compound word (e.g., "chiliflakes" satisfies
                    # 'chili' strict PPR with 'flakes' indicator when product has 'flakes')
                    # BUG FIX: was `processed_indicators` (ALL indicators) — let unrelated
                    # products leak through when a different ingredient had a compound word
                    # (e.g., 'chiliflakes' in one ingredient let 'Örtsalt Chili' pass)
                    if not any((base_word + ind) in ingredient_lower for ind in expanded_indicators):
                        # Spice-amount heuristic: "1 tsk ingefära" (no qualifier) = malen/torkad.
                        # Small spice amounts (tsk/krm) without fresh indicators imply dried/ground.
                        _SPICE_AMOUNT_IMPLICIT_GROUND = frozenset({
                            'ingefära', 'ingefara',
                            'gurkmeja', 'kurkuma',
                            'paprika',
                        })
                        _GROUND_PRODUCT_INDICATORS = frozenset({'malen', 'malna', 'mald', 'malet', 'pulver', 'torkad', 'torkade'})
                        _FRESH_INDICATORS = frozenset({'färsk', 'farsk', 'riven', 'hackad', 'pressad'})
                        _STRICT_GENERIC_MATCHES_ALL = frozenset({'sojabönor', 'sojabonor'})
                        ingredient_has_any_indicator = any(
                            _is_whole_word(ind, ingredient_lower) for ind in processed_indicators
                        )
                        if (
                            base_word in _STRICT_GENERIC_MATCHES_ALL
                            and not ingredient_has_any_indicator
                        ):
                            continue  # Allow: generic soybeans can match canned or frozen
                        if (base_word in _SPICE_AMOUNT_IMPLICIT_GROUND
                                and any(ind in _GROUND_PRODUCT_INDICATORS for ind in expanded_indicators)
                                and not any(fi in ingredient_lower for fi in _FRESH_INDICATORS)
                                and re.search(r'\b(?:tsk|krm)\b', ingredient_lower)):
                            continue  # Allow: spice amount implies ground/dried
                        return False
            else:
                for indicator in processed_indicators:
                    if indicator in product_lower:
                        if indicator not in ingredient_lower:
                            has_any_indicator = any(ind in ingredient_lower for ind in processed_indicators)
                            if not has_any_indicator:
                                return False
                        break
    return True


def check_specialty_qualifiers(
    offer_specialty_qualifiers: Dict[str, set],
    matched_keyword: str,
    ingredient_lower: str
) -> bool:
    """
    Check if a match passes SPECIALTY_QUALIFIERS against a SINGLE ingredient.

    Returns True if the match is allowed, False if it should be blocked.

    Enforces two directions:
    - Direction A (standard): if INGREDIENT has qualifier → OFFER must have it too.
      e.g., "serranoskinka" in ingredient → offer must have "serrano".
    - Direction B (bidirectional): if OFFER has a BIDIRECTIONAL qualifier →
      INGREDIENT must also have it (or an equivalent).
      e.g., offer "Soltorkade Tomater" has qualifier "soltorkade" →
      ingredient "2 tomater" (no qualifier) is blocked.

    This function is designed for per-ingredient validation in recipe_matcher,
    where the initial match used combined ingredient text (which can cause
    false positives from cross-ingredient contamination, e.g., "kokt" from
    "hårdkokta ägg" falsely satisfying the qualifier check for "Skinka Kokt").
    """
    ingredient_keywords = None

    for base_word, qualifiers in SPECIALTY_QUALIFIERS.items():
        if base_word != matched_keyword:
            continue

        candidate_ingredients = _specialty_alternative_texts(base_word, set(qualifiers), ingredient_lower)
        offer_quals = _prune_shadowed_smoked_qualifiers(
            set(offer_specialty_qualifiers.get(base_word, set()))
        )

        # Direction A: if ingredient has a specialty qualifier, offer must match it
        # Skip Direction A for keywords where plain products are valid fallbacks:
        # - fraiche: plain crème fraîche works for any flavored fraiche recipe
        # - matlagningsvin: plain cooking wine works for any colored wine recipe
        # NOT skipped for type-based keywords (linser, vinbärs) where generic ≠ specific.
        _DIRECTION_A_SKIP = {
            'fraiche', 'matlagningsvin',
        }
        # Chocolate partial skip: "mörk choklad" should match generic (no darkness),
        # but "vit choklad" must NOT match dark/generic. Skip Direction A only for
        # mörk/mork qualifiers. Enforce for vit/ljus.
        _DIRECTION_A_SKIP_QUALIFIERS: Dict[str, Set[str]] = {
            'choklad': {'mörk', 'mork'},
            'bakchoklad': {'mörk', 'mork'},
            'blockchoklad': {'mörk', 'mork'},
        }
        # Packaging words like 'burk' can appear in ingredient text referring to
        # a DIFFERENT product ("1 burk kronärtskockscrème med soltorkad tomat").
        # When a more specific qualifier (soltorkad, krossade, etc.) is also present,
        # it takes priority over generic packaging words.
        _PACKAGING_QUALIFIERS = {'burk', 'konserverad', 'konserverade'}
        if base_word not in _DIRECTION_A_SKIP:
            direction_a_checked = False
            direction_a_matched = False
            for candidate in candidate_ingredients:
                ingredient_has_base = base_word in candidate
                if not ingredient_has_base:
                    # Compound ingredient forms are often normalized to the base keyword by
                    # extract_keywords_from_ingredient(), e.g. "kronärtskockshjärtan" →
                    # "kronärtskocka". Use that same extraction here so Direction A still
                    # applies when the base word is only present implicitly via a compound.
                    if ingredient_keywords is None:
                        ingredient_keywords = set(extract_keywords_from_ingredient(candidate))
                    ingredient_has_base = (
                        base_word in ingredient_keywords
                        or any(
                            alias in ingredient_keywords
                            for alias in _SPECIALTY_BASE_KEYWORD_ALIASES.get(base_word, set())
                        )
                    )
                if not ingredient_has_base:
                    continue

                direction_a_checked = True
                found_qualifiers = [q for q in qualifiers if q in candidate]
                if any(q in found_qualifiers for q in _SMOKED_SPECIFIC_QUALIFIERS):
                    found_qualifiers = [q for q in found_qualifiers if q not in _GENERIC_SMOKED_QUALIFIERS]
                # For partial-skip keywords (e.g., choklad), remove skipped qualifiers
                skip_quals = _DIRECTION_A_SKIP_QUALIFIERS.get(base_word, set())
                if skip_quals:
                    found_qualifiers = [q for q in found_qualifiers if q not in skip_quals]
                if (
                    base_word == 'paprika'
                    and ingredient_has_spice_indicator(
                        _PAPRIKA_SPICE_INDICATORS,
                        candidate,
                        base_word,
                    )
                ):
                    found_qualifiers = [
                        q for q in found_qualifiers
                        if q not in _PAPRIKA_FRESH_COLOR_QUALIFIERS
                    ]
                if not found_qualifiers:
                    direction_a_matched = True
                    break

                # Prefer specific qualifiers over packaging words
                specific = [q for q in found_qualifiers if q not in _PACKAGING_QUALIFIERS]
                check_quals = specific if specific else found_qualifiers
                if (
                    base_word == 'chilisås'
                    and any(q in _SWEET_CHILI_QUALIFIERS for q in check_quals)
                    and any(q in offer_quals for q in _UNSWEETENED_CHILI_QUALIFIERS)
                ):
                    continue
                # The most specific qualifier must match the offer
                matched = False
                for qualifier in check_quals:
                    equivalents = QUALIFIER_EQUIVALENTS.get(qualifier, {qualifier})
                    # Steak-/piece-style tuna wording in recipes ("bitar tonfisk",
                    # "tonfiskbiff", "tonfisksteak") is really asking for the
                    # fresh/frozen fillet family, not canned tuna. Accept the
                    # non-canned tuna forms as equivalent signals here.
                    if base_word == 'tonfisk' and qualifier in {'bit', 'bitar', 'biff', 'steak'}:
                        equivalents = set(equivalents) | {
                            'bit', 'bitar', 'biff', 'steak',
                            'färsk', 'fryst', 'filé', 'file',
                        }
                    if base_word == 'bönor' and qualifier in {'grön', 'gröna'}:
                        equivalents = {eq for eq in equivalents if eq != 'mix'}
                    if any(eq in offer_quals for eq in equivalents):
                        matched = True
                        break
                if not matched:
                    continue

                # Some qualifier families are additive rather than interchangeable.
                # "jästa svarta bönor" needs BOTH the black-bean qualifier and a
                # fermented qualifier; matching only "svarta" is not enough.
                _REQUIRED_QUALIFIER_GROUPS = {
                    'bönor': (
                        frozenset({'jäst', 'jästa', 'fermenterad', 'fermenterade'}),
                    ),
                    'tortellini': (
                        frozenset({'ricotta', 'mozzarella', 'mozarella', 'ost', 'ostar', '4 ostar', 'fyra ostar', '5 ostar', 'fem ostar', 'mascarpone'}),
                        frozenset({'spenat', 'spinaci', 'skinka', 'prosciutto', 'mortadella', 'pancetta', 'pomodoro', 'svamp', 'kött', 'kott', 'lax', 'pesto', 'genovese'}),
                    ),
                    'tortelloni': (
                        frozenset({'ricotta', 'mozzarella', 'mozarella', 'ost', 'ostar', '4 ostar', 'fyra ostar', '5 ostar', 'fem ostar', 'mascarpone'}),
                        frozenset({'spenat', 'spinaci', 'skinka', 'prosciutto', 'mortadella', 'pancetta', 'pomodoro', 'svamp', 'kött', 'kott', 'lax', 'pesto', 'genovese'}),
                    ),
                    'ravioli': (
                        frozenset({'ricotta', 'mozzarella', 'mozarella', 'ost', 'ostar', '4 ostar', 'fyra ostar', '5 ostar', 'fem ostar', 'mascarpone'}),
                        frozenset({'spenat', 'spinaci', 'skinka', 'prosciutto', 'mortadella', 'pancetta', 'pomodoro', 'svamp', 'kött', 'kott', 'lax', 'pesto', 'genovese'}),
                    ),
                }
                additive_ok = True
                for required_group in _REQUIRED_QUALIFIER_GROUPS.get(base_word, ()):
                    group_hits = [q for q in check_quals if q in required_group]
                    if not group_hits:
                        continue
                    group_equivalents = set()
                    for qualifier in group_hits:
                        group_equivalents.update(QUALIFIER_EQUIVALENTS.get(qualifier, {qualifier}))
                    if not any(eq in offer_quals for eq in group_equivalents):
                        additive_ok = False
                        break
                if additive_ok:
                    direction_a_matched = True
                    break

            if direction_a_checked and not direction_a_matched:
                return False

        # Direction B: if offer has a BIDIRECTIONAL qualifier, ingredient must match it
        # Combine global bidirectional set with per-keyword bidirectional set
        per_kw_bidir = BIDIRECTIONAL_PER_KEYWORD.get(base_word, frozenset())
        # Some keywords allow generic ingredient to match all variants:
        # - choklad: "choklad" (generic) = any darkness, "mörk choklad" = dark only
        # Most keywords do NOT: "färskost" (generic) = naturell, not flavored.
        _GENERIC_MATCHES_ALL = {'choklad', 'bakchoklad', 'blockchoklad'}
        ingredient_has_qualifier = any(
            any(q in candidate for q in qualifiers) for candidate in candidate_ingredients
        )
        for qualifier in offer_quals:
            if qualifier in BIDIRECTIONAL_SPECIALTY_QUALIFIERS or qualifier in per_kw_bidir:
                # Skip Direction B for per-keyword bidirectional when ingredient is generic
                # AND keyword allows generic-matches-all
                if (not ingredient_has_qualifier
                        and qualifier not in BIDIRECTIONAL_SPECIALTY_QUALIFIERS
                        and base_word in _GENERIC_MATCHES_ALL):
                    continue
                # Steak-/piece-style tuna wording implies the fresh tuna family
                # even when the recipe does not literally say "färsk".
                if (
                    base_word == 'tonfisk'
                    and qualifier in {'färsk', 'farsk'}
                    and any(
                        any(cue in candidate for cue in ('bit', 'bitar', 'biff', 'steak'))
                        for candidate in candidate_ingredients
                    )
                ):
                    continue
                if (
                    base_word == 'kyckling'
                    and qualifier == 'hel'
                    and any(_ingredient_implies_whole_kyckling(candidate) for candidate in candidate_ingredients)
                ):
                    continue
                equivalents = QUALIFIER_EQUIVALENTS.get(qualifier, {qualifier})
                if not any(
                    _qualifier_present_in_text(eq, candidate)
                    for eq in equivalents
                    for candidate in candidate_ingredients
                ):
                    return False

    return True


def check_spice_vs_fresh_rules(product_lower: str, ingredient_lower: str, base_word: str = "") -> bool:
    """
    Check if a match passes SPICE_VS_FRESH_RULES against a SINGLE ingredient.

    Returns True if the match is allowed, False if it should be blocked.

    This function is designed for per-ingredient validation in recipe_matcher,
    where the initial match used combined ingredient text (which can cause
    false negatives from cross-ingredient contamination, e.g., "malen" from
    "malen kanel" falsely triggering the spice check for fresh "Paprika Röd").
    """
    if (
        'vitlök' in ingredient_lower
        and 'torkad' in ingredient_lower
        and 'burk' in ingredient_lower
    ):
        blocked_non_neutral = (
            'olja', 'marinerad', 'marinerade', 'chili',
            'pulver', 'granulat', 'flakes', 'flingor',
            'torkad', 'torkade',
        )
        if any(word in product_lower for word in blocked_non_neutral):
            return False

    rules_iter = (
        [(base_word, SPICE_VS_FRESH_RULES[base_word])]
        if base_word and base_word in SPICE_VS_FRESH_RULES
        else SPICE_VS_FRESH_RULES.items()
    )

    for rule_base_word, rules in rules_iter:
        if rule_base_word in ingredient_lower:
            # Check A: processed/jarred product (blocked_product_words)
            for blocked in rules['blocked_product_words']:
                if blocked in product_lower:
                    if 'allowed_indicators' in rules:
                        # Require mode: ingredient MUST have an allowed indicator
                        has_allowed_indicator = any(ind in ingredient_lower for ind in rules['allowed_indicators'])
                        if not has_allowed_indicator and rule_base_word == 'fänkål':
                            has_allowed_indicator = _has_fennel_spice_list_context(ingredient_lower)
                        if not has_allowed_indicator:
                            return False
                    else:
                        # Block mode: if ingredient has spice indicator → block
                        if ingredient_has_spice_indicator(rules['spice_indicators'], ingredient_lower, rule_base_word):
                            return False
                    break
            # Check A2: whole-spice recipe REQUIRES product to also be whole
            # e.g., "hel spiskummin" → product must contain 'hel'/'hela'
            # "Spiskummin 33g" (no hel) = ground by default → blocked
            if 'required_whole_product_words' in rules:
                if ingredient_has_spice_indicator(rules['spice_indicators'], ingredient_lower, rule_base_word):
                    if not any(rw in product_lower for rw in rules['required_whole_product_words']):
                        return False
            else:
                # Check B: fresh product (fresh_product_words)
                # e.g., "Vitlök Klass 1" has 'klass' → block dried indicators
                if 'fresh_product_words' in rules:
                    for fresh_word in rules['fresh_product_words']:
                        if fresh_word in product_lower:
                            if any(ind in ingredient_lower for ind in rules['dried_indicators']):
                                return False
                            break

                # Check C: pickled recipe requires pickled product
                # e.g., "inlagd jalapeño" should NOT match "Chilli Jalapeno" (fresh)
                if 'pickled_indicators' in rules:
                    if any(ind in ingredient_lower for ind in rules['pickled_indicators']):
                        if not any(pw in product_lower for pw in rules['pickled_product_words']):
                            return False

                # Check D: ground ingredient blocks whole-spice products
                # e.g., "malen kanel" should NOT match "Kanel Hel Påse"
                # but "kanelstång" (no ground indicator) SHOULD match "Kanel Hel Påse"
                if 'ground_indicators' in rules:
                    if any(gi in ingredient_lower for gi in rules['ground_indicators']):
                        if any(wp in product_lower for wp in rules['blocked_whole_product_words']):
                            return False
                        # Check E: ground ingredient REQUIRES product to have a processing indicator
                        # e.g., "Ingefära Malen" → require product to have 'malen'/'burk'/'påse'
                        # blocks fresh "Ingefära" (no processing word) from matching ground recipes
                        if 'required_ground_product_words' in rules:
                            if not any(rw in product_lower for rw in rules['required_ground_product_words']):
                                return False

    return True
