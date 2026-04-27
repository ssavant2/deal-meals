# -*- coding: utf-8 -*-
"""
English (United Kingdom) recipe filters.

These patterns are intentionally modest. They provide a functional skeleton for
UK recipe sources without claiming to be a complete recipe-quality model.
"""

BORING_RECIPE_PATTERNS = [
    'how to boil rice',
    'how to cook rice',
    'how to cook pasta',
    'how to boil potatoes',
    'how to boil eggs',
    'perfect rice',
    'perfect pasta',
    'boiled rice',
    'boiled potatoes',
    'boiled eggs',
]

JUNK_FOOD_KEYWORDS = [
    'sweets', 'chocolate', 'nougat', 'cola', 'fanta', 'sprite', 'pepsi',
]
JUNK_FOOD_KEYWORDS_NO_CHOCOLATE = [
    'sweets', 'nougat', 'cola', 'fanta', 'sprite', 'pepsi',
]

KITCHEN_TOOLS = (
    'piping bag', 'baking parchment', 'skewers', 'cocktail sticks',
    'lolly sticks', 'star nozzle',
)

LEFTOVER_PREFIX = 'leftover '
SUB_RECIPE_WORD = 'base recipe'


def is_boring_recipe(recipe_name: str) -> bool:
    """Check if a recipe name is likely to be basic cooking instructions."""
    name_lower = (recipe_name or '').lower()
    return any(pattern in name_lower for pattern in BORING_RECIPE_PATTERNS)
