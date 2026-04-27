# -*- coding: utf-8 -*-
"""
Swedish Recipe Filters

Patterns and functions for filtering out uninteresting recipes
(e.g., "how to boil rice" type content).
"""

# Boring "how to cook X" recipes to skip in suggestions
BORING_RECIPE_PATTERNS = [
    'koka ris', 'koka pasta', 'koka potatis', 'koka ägg',
    'koka bulgur', 'koka couscous', 'koka quinoa', 'koka bönor',
    'koka linser', 'koka nudlar', 'koka spaghetti', 'koka makaroner',
    'så kokar du', 'hur man kokar',
    'perfekt ris', 'perfekt pasta', 'perfekta ägg',
    'kokt ris', 'kokt pasta', 'kokta ägg',
]


# Junk food keywords — products that should never match recipes
# Two variants: with and without 'choklad' (candy chocolate, not baking chocolate)
JUNK_FOOD_KEYWORDS = ['godis', 'choklad', 'nougat', 'cola', 'fanta', 'sprite', 'pepsi']
JUNK_FOOD_KEYWORDS_NO_CHOCOLATE = ['godis', 'nougat', 'cola', 'fanta', 'sprite', 'pepsi']

# Kitchen tools sometimes listed as recipe "ingredients" — not buyable
KITCHEN_TOOLS = (
    'spritspås', 'sprits med', 'bakplåtspapper', 'grillspett',
    'cocktailpinnar', 'stjärntyll', 'glasspinnar', 'glasspinne',
)

# Prefix indicating leftover reuse — not a buyable ingredient
LEFTOVER_PREFIX = 'resterna '

# Sub-recipe reference word — ingredient refers to another recipe, not buyable
SUB_RECIPE_WORD = 'grundrecept'


def is_boring_recipe(recipe_name: str) -> bool:
    """Check if recipe name matches boring 'how to cook' patterns."""
    name_lower = (recipe_name or '').lower()
    return any(pattern in name_lower for pattern in BORING_RECIPE_PATTERNS)
