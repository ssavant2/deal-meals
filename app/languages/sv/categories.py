"""
Swedish display names and UI text for categories.

This file contains all Swedish text related to recipe categories.
Internal keys are imported from categories.py (English).
"""

from ..categories import MEAT, FISH, VEGETARIAN, SMART_BUY

# Swedish display names for UI
DISPLAY_NAMES = {
    MEAT: 'Kött & Fågel',
    FISH: 'Fisk & Skaldjur',
    VEGETARIAN: 'Vegetariskt',
    SMART_BUY: 'Smarta köp',
}

# Short names (for compact UI)
SHORT_NAMES = {
    MEAT: 'Kött',
    FISH: 'Fisk',
    VEGETARIAN: 'Veg',
    SMART_BUY: 'Budget',
}

# Icons for each category (Bootstrap Icons)
CATEGORY_ICONS = {
    MEAT: 'bi-egg-fried',
    FISH: 'bi-water',
    VEGETARIAN: 'bi-tree',
    SMART_BUY: 'bi-piggy-bank',
}

# Colors for each category (CSS hex)
CATEGORY_COLORS = {
    MEAT: '#dc3545',       # Red
    FISH: '#0d6efd',       # Blue
    VEGETARIAN: '#198754', # Green
    SMART_BUY: '#ffc107',  # Yellow
}

# Exclude checkbox labels (Swedish)
EXCLUDE_LABELS = {
    MEAT: 'Kött & Fågel',
    FISH: 'Fisk & Skaldjur',
    'dairy': 'Mejeriprodukter',  # Special case - not a primary category
}

# Balance slider labels (Swedish)
BALANCE_LABELS = {
    MEAT: 'Kött & Fågel',
    FISH: 'Fisk & Skaldjur',
    VEGETARIAN: 'Vegetariskt',
    SMART_BUY: 'Smarta köp',
}
