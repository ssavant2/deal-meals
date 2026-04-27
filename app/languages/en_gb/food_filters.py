# -*- coding: utf-8 -*-
"""
English (United Kingdom) Food Filter Keywords (Template)

Template for UK English store data. Fill in from actual store data when
building a scraper for a UK store (Tesco, Sainsbury's, etc.).

Usage in your store subclass:

    from languages.en_gb.food_filters import (
        FOOD_CATEGORIES, NON_FOOD_CATEGORIES, FOOD_INDICATORS,
        NON_FOOD_STRONG, NON_FOOD_INDICATORS, CERTIFICATION_LOGOS
    )

    class TescoStore(StorePlugin):
        FOOD_CATEGORIES = FOOD_CATEGORIES
        NON_FOOD_CATEGORIES = NON_FOOD_CATEGORIES
        FOOD_INDICATORS = FOOD_INDICATORS
        CERTIFICATION_LOGOS = CERTIFICATION_LOGOS
        NON_FOOD_STRONG = NON_FOOD_STRONG
        NON_FOOD_INDICATORS = NON_FOOD_INDICATORS

Note: These are starting points. UK stores may use different category
names and product naming conventions than Swedish ones. Build and refine
these lists from actual scraped data.
"""

# =============================================================================
# FOOD CATEGORIES - Category strings that indicate food
# =============================================================================
# The English normalized categories are shared with Swedish (from category_utils).
# Add store-specific raw category names as needed.
FOOD_CATEGORIES = {
    # Normalized (shared with Swedish stores)
    "meat", "poultry", "fish", "dairy", "deli", "fruit", "vegetables",
    "bread", "beverages", "candy", "frozen", "pantry", "spices", "pizza",
    # TODO: Add store-specific raw categories (e.g., Tesco's own category names)
}

# =============================================================================
# NON-FOOD CATEGORIES - Category strings that indicate non-food
# =============================================================================
NON_FOOD_CATEGORIES = {
    "hygiene", "household",
    "health", "beauty", "cosmetics", "toiletries",
    "cleaning", "laundry",
    "home", "garden", "pets", "pet care",
    "electronics", "stationery", "clothing",
    "toys", "books",
    # TODO: Add store-specific raw categories
}

# =============================================================================
# FOOD INDICATORS - Words in product names that suggest food
# =============================================================================
FOOD_INDICATORS = [
    # Weight/volume units (universal)
    "kg", "g ", "ml", "liter", "litre", "cl", "dl", "oz", "lb",
    # Organic labels
    "organic", "free range", "fair trade",
    # Preparation methods
    "fresh", "smoked", "grilled", "cooked", "fried", "roasted", "baked",
    # Meat
    "fillet", "steak", "sausage", "ham", "bacon", "pork", "chicken", "beef", "lamb",
    # Fish & seafood
    "salmon", "cod", "herring", "prawns", "shrimp", "fish",
    # Dairy
    "milk", "yoghurt", "yogurt", "cheese", "butter", "cream", "margarine",
    # Bakery
    "bread", "roll", "cake", "pastry", "muffin", "croissant",
    # Produce
    "apple", "banana", "tomato", "potato", "onion", "cucumber", "pepper", "carrot",
    # Drinks
    "juice", "water", "coffee", "tea ", "drink", "soda", "squash",
    # Snacks
    "crisps", "chips", "chocolate", "ice cream", "cereal", "biscuit",
    # Pantry
    "pasta", "rice", "sauce", "ketchup", "mustard", "mayonnaise", "dressing",
    # Baking
    "jam", "honey", "sugar", "flour",
    # TODO: Refine from actual store data
]

# =============================================================================
# CERTIFICATION LOGOS - Scraping artifacts (badge names, not real products)
# =============================================================================
CERTIFICATION_LOGOS = {
    "rainforest alliance", "fairtrade", "fair trade",
    "red tractor", "rspca assured", "soil association",
    "msc", "asc", "fsc",
    # TODO: Add store-specific certification badges
}

# =============================================================================
# NON-FOOD STRONG - Product types that are NEVER food (checked FIRST)
# =============================================================================
# These often have "ml" or "g" in the name but are NOT food.
NON_FOOD_STRONG = [
    # Hair care
    "shampoo", "conditioner", "hair dye", "hair spray",
    # Body care
    "soap", "hand wash", "shower gel", "body wash", "body lotion",
    # Face care
    "moisturiser", "moisturizer", "face cream", "serum", "cleanser",
    # Makeup
    "mascara", "lipstick", "makeup", "foundation", "concealer", "eyeliner",
    # Hygiene
    "deodorant", "perfume", "toothpaste", "toothbrush", "mouthwash",
    "razor", "aftershave",
    "sanitary", "nappy", "nappies", "diaper",
    # Brands that are NEVER food
    "maybelline", "loreal", "l'oreal", "garnier", "dove", "lynx", "sure",
    # Cleaning products
    "washing up liquid", "detergent", "fabric softener", "bleach",
    "surface cleaner", "disinfectant",
    # Pet products
    "cat food", "dog food", "pet food", "cat treats", "dog treats",
    # TODO: Refine from actual store data
]

# =============================================================================
# NON-FOOD INDICATORS - Generic items (checked AFTER food indicators)
# =============================================================================
NON_FOOD_INDICATORS = [
    # Household paper
    "toilet roll", "kitchen roll", "tissue", "napkin",
    # Candles & lighting
    "battery", "batteries", "light bulb", "candle", "matches",
    # Kitchen items (not food)
    "frying pan", "saucepan", "bowl", "plate", "mug", "cup", "cutlery",
    # Toys & books
    "toy", "puzzle", "book ", " book", "magazine",
    # Garden & plants
    "flower", "plant", "pot", "compost",
    # Clothing
    "socks", "underwear", "pyjamas",
    # Electronics
    "headphones", "usb", "cable",
    # Gift & packaging
    "wrapping paper", "gift bag", "card ",
    # TODO: Refine from actual store data
]
