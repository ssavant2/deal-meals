"""UK English spell-check profile data."""

DEFAULT_SPELL_EXCLUDED_WORDS = frozenset()

INFLECTION_SUFFIXES = (
    's', 'es', 'ed', 'ing',
)

SAFE_NON_FOOD_WORDS = frozenset({
    'about', 'after', 'baked', 'boiled', 'chopped', 'cooked',
    'diced', 'fresh', 'fried', 'grated', 'large', 'optional',
    'roughly', 'sliced', 'small', 'taste', 'thawed',
})
