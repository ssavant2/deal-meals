"""UK English pantry matching support data."""

IGNORE_WORDS = frozenset({
    # Measurements
    'tsp', 'tbsp', 'teaspoon', 'teaspoons', 'tablespoon', 'tablespoons',
    'g', 'gram', 'grams', 'kg', 'ml', 'cl', 'dl', 'l', 'litre', 'litres',
    'oz', 'lb', 'pound', 'pounds', 'cup', 'cups', 'tin', 'tins',
    'can', 'cans', 'pack', 'packet', 'packets', 'piece', 'pieces',
    'serving', 'servings',
    # Cooking words
    'about', 'approx', 'approximately', 'optional', 'or', 'and', 'with',
    'finely', 'roughly', 'chopped', 'sliced', 'shredded', 'diced',
    'grated', 'boiled', 'fried', 'fresh', 'frozen', 'thawed',
    'large', 'small', 'medium', 'thin', 'thick',
    # Function words
    'to', 'for', 'as', 'the', 'a', 'an', 'some', 'little',
    'after', 'taste', 'preferred',
    # Common household staples
    'water', 'salt', 'pepper', 'black', 'sugar', 'oil',
    'olive', 'vegetable', 'vinegar',
})
