"""
Category constants for recipe classification.

These are the INTERNAL keys used throughout the codebase.
All keys are in English for code clarity and international readability.

Localized display names live in each language package's categories.py.
"""

# Primary recipe categories (used in balance sliders, cache, matching)
MEAT = 'meat'
FISH = 'fish'
VEGETARIAN = 'vegetarian'
SMART_BUY = 'smart_buy'

# All primary categories (for iteration)
PRIMARY_CATEGORIES = [MEAT, FISH, VEGETARIAN]
ALL_CATEGORIES = [MEAT, FISH, VEGETARIAN, SMART_BUY]

# Exclude categories (for checkbox filtering)
# These map to the primary categories when filtering
POULTRY = 'poultry'  # Maps to MEAT
DELI = 'deli'        # Maps to MEAT
DAIRY = 'dairy'      # Separate (for lactose-free filtering)

# Categories that should be treated as meat when excluded
MEAT_RELATED = [MEAT, POULTRY, DELI]

# Default balance weights (raw counts 0-4, normalized when used)
DEFAULT_BALANCE = {
    MEAT: 3,
    FISH: 3,
    VEGETARIAN: 3,
    SMART_BUY: 3,
}

# Default balance as percentages (for API responses)
DEFAULT_BALANCE_PCT = {
    MEAT: 0.25,
    FISH: 0.25,
    VEGETARIAN: 0.25,
    SMART_BUY: 0.25,
}


def is_meat_category(category: str) -> bool:
    """Check if a category should be treated as meat."""
    return category in MEAT_RELATED
