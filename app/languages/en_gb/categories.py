"""
English (United Kingdom) display names and UI text for recipe categories.

The internal category keys are shared across all countries and remain in
English in app/languages/categories.py. This file only controls country/local
display labels for UK-facing UI surfaces.
"""

from ..categories import FISH, MEAT, SMART_BUY, VEGETARIAN


DISPLAY_NAMES = {
    MEAT: 'Meat & Poultry',
    FISH: 'Fish & Seafood',
    VEGETARIAN: 'Vegetarian',
    SMART_BUY: 'Smart Buys',
}

SHORT_NAMES = {
    MEAT: 'Meat',
    FISH: 'Fish',
    VEGETARIAN: 'Veg',
    SMART_BUY: 'Budget',
}

CATEGORY_ICONS = {
    MEAT: 'bi-egg-fried',
    FISH: 'bi-water',
    VEGETARIAN: 'bi-tree',
    SMART_BUY: 'bi-piggy-bank',
}

CATEGORY_COLORS = {
    MEAT: '#dc3545',
    FISH: '#0d6efd',
    VEGETARIAN: '#198754',
    SMART_BUY: '#ffc107',
}

EXCLUDE_LABELS = {
    MEAT: 'Meat & Poultry',
    FISH: 'Fish & Seafood',
    'dairy': 'Dairy products',
}

BALANCE_LABELS = {
    MEAT: 'Meat & Poultry',
    FISH: 'Fish & Seafood',
    VEGETARIAN: 'Vegetarian',
    SMART_BUY: 'Smart Buys',
}
