"""Dairy type matching rules for Swedish ingredient matching."""

from typing import FrozenSet

try:
    from languages.sv.normalization import fix_swedish_chars
except ModuleNotFoundError:
    from app.languages.sv.normalization import fix_swedish_chars


ALLOWED_YOGURT_TYPES: FrozenSet[str] = frozenset({
    'naturell', 'naturella', 'naturellt',
    'grekisk', 'greek', 'turkisk',
    'mild',
})


_YOGHURT_KEYWORDS: FrozenSet[str] = frozenset({
    fix_swedish_chars(w).lower() for w in {
        'yoghurt', 'yogurt',
        'vaniljyoghurt',
        'matlagningsyoghurt', 'matyoghurt',
        'lättyoghurt',
        'kvargyoghurt', 'yoghurtkvarg',
    }
})


_YOGHURT_SNACK_FLAVORS: FrozenSet[str] = frozenset({
    fix_swedish_chars(w).lower() for w in {
        'ananas', 'apelsin', 'aprikos',
        'banan', 'björnbär', 'blåbär',
        'cherry', 'choklad', 'citron', 'citrus',
        'drottningbär',
        'granatäpple', 'guava',
        'hallon', 'havtorn',
        'jordgubb', 'kiwi', 'krusbär', 'körsbär',
        'lime', 'lemony',
        'mandarin', 'mango', 'melon',
        'passion', 'passionsfrukt', 'persika', 'päron', 'pepparkaka',
        'samoa', 'skogsbär', 'smultron', 'sommarbär', 'svartvinbär', 'vinbär', 'vinbar',
        'tropisk',
        'äpple',
        'granola', 'müsli', 'nötter', 'crisp',
        'smoothie', 'drick',
        'junior', 'robby', 'safari',
        'protein',
        'flingor',
        'gröt',
        'bägare',
        'säsong',
    }
})


_YOGHURT_VANILJ_INDICATORS: FrozenSet[str] = frozenset({
    fix_swedish_chars(w).lower() for w in {
        'vanilj', 'vanilla', 'madagaskar',
    }
})


_YOGHURT_VEGO_INDICATORS: FrozenSet[str] = frozenset({
    fix_swedish_chars(w).lower() for w in {
        'växtbaserad', 'vegansk', 'vego', 'vegetabilisk',
        'soja', 'soya', 'havre', 'kokos', 'mandel',
        'plant', 'gurt',
    }
})


_YOGHURT_COOKING_INDICATORS: FrozenSet[str] = frozenset({
    fix_swedish_chars(w).lower() for w in {
        'matlagning', 'matlagnings',
        'mat',
        'grekisk', 'grekiska', 'greek',
        'turkisk', 'turkiska', 'turkish',
    }
})


_FILMJOLK_KEYWORDS: FrozenSet[str] = frozenset({
    fix_swedish_chars(w).lower() for w in {
        'filmjölk', 'filmjolk',
        'filmmjölk', 'filmmjolk',
        'filjmjölk', 'filjmjolk',
        'fjällfil', 'fjallfil',
    }
})


def check_filmjolk_match(keyword: str, ingredient_lower: str,
                         product_name_lower: str) -> bool:
    """Check if a filmjölk product is allowed to match this recipe ingredient."""
    if keyword not in _FILMJOLK_KEYWORDS:
        return True
    if not any(k in product_name_lower for k in _FILMJOLK_KEYWORDS):
        return True

    if any(f in product_name_lower for f in _YOGHURT_SNACK_FLAVORS):
        return False
    if any(v in product_name_lower for v in _YOGHURT_VANILJ_INDICATORS):
        return False
    return True


def check_yoghurt_match(keyword: str, ingredient_lower: str,
                        product_name_lower: str) -> bool:
    """Check if a yoghurt product is allowed to match this recipe ingredient."""
    if keyword not in _YOGHURT_KEYWORDS:
        return True
    if not ('yoghurt' in product_name_lower or 'yogurt' in product_name_lower
            or 'gurt' in product_name_lower):
        return True

    if any(f in product_name_lower for f in _YOGHURT_SNACK_FLAVORS):
        return False

    is_vanilj_product = any(v in product_name_lower for v in _YOGHURT_VANILJ_INDICATORS)
    is_vego_product = (any(v in product_name_lower for v in _YOGHURT_VEGO_INDICATORS)
                       and not is_vanilj_product)
    is_plain_product = (any(t in product_name_lower for t in ALLOWED_YOGURT_TYPES)
                        and not is_vanilj_product and not is_vego_product)
    is_cooking_product = (any(c in product_name_lower for c in _YOGHURT_COOKING_INDICATORS)
                          and not is_vego_product)

    if not is_vanilj_product and not is_vego_product and not is_plain_product and not is_cooking_product:
        return False

    is_vanilj_recipe = any(v in ingredient_lower for v in _YOGHURT_VANILJ_INDICATORS)
    is_vego_recipe = any(v in ingredient_lower for v in _YOGHURT_VEGO_INDICATORS)

    if is_vanilj_recipe:
        return is_vanilj_product
    if is_vego_recipe:
        return is_vego_product
    return is_plain_product or is_cooking_product


_KVARG_KEYWORDS: FrozenSet[str] = frozenset({'kvarg', 'kesella'})


_KVARG_SNACK_INDICATORS: FrozenSet[str] = frozenset({
    fix_swedish_chars(w).lower() for w in {
        'drick',
        'frukt',
        'protein',
        'dessert',
        'sundae',
        'cheesecake',
        'cookie', 'cookies',
        'crush',
    }
})


def check_kvarg_match(keyword: str, ingredient_lower: str,
                      product_name_lower: str) -> bool:
    """Check if a kvarg product is allowed to match this recipe ingredient."""
    if keyword not in _KVARG_KEYWORDS:
        return True
    if 'kvarg' not in product_name_lower:
        return True

    if any(f in product_name_lower for f in _YOGHURT_SNACK_FLAVORS):
        return False

    if any(s in product_name_lower for s in _KVARG_SNACK_INDICATORS):
        return False

    if any(v in product_name_lower for v in _YOGHURT_VANILJ_INDICATORS):
        return any(v in ingredient_lower for v in _YOGHURT_VANILJ_INDICATORS)

    return True
