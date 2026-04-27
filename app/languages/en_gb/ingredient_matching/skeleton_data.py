"""
Seed data for a future UK ingredient matcher.

These dictionaries are examples, not active production data. They show the
shape and level of care expected when replacing the temporary Swedish backend
delegation with real UK-specific matching rules.
"""

# Main ingredient families. A real port should expand this into an
# ingredient_data.py module equivalent to the Swedish implementation.
SAMPLE_INGREDIENTS = {
    # Poultry wording differs between recipe sites and supermarkets:
    # "chicken breast fillets" is a common product name, while recipes often say
    # just "chicken breast" or "chicken fillet".
    'chicken breast': ['chicken breast', 'chicken fillet', 'chicken breast fillet'],

    # UK recipes and stores usually say "beef mince"; US-origin recipes may use
    # "ground beef". Keep both, but prefer the UK term as the canonical key.
    'beef mince': ['beef mince', 'minced beef', 'ground beef'],

    # Fish offers often include cut/form words. Start with the common fillet
    # phrase and add broader salmon only after false positives are understood.
    'salmon fillet': ['salmon fillet', 'salmon portions', 'salmon'],

    # Dairy needs fat-level qualifiers eventually. This seed intentionally keeps
    # the family small so semi-skimmed/whole/skimmed can be validated later.
    'milk': ['milk', 'whole milk', 'semi-skimmed milk', 'skimmed milk'],

    # UK stores use both singular and plural potato terms, plus named varieties.
    # A complete matcher should distinguish baking, baby, new and sweet potatoes.
    'potato': ['potato', 'potatoes', 'baking potato', 'new potatoes'],
}

# Parent mappings show when a specific item can satisfy a broader ingredient.
SAMPLE_PARENT_SYNONYMS = {
    'new potatoes': 'potato',
    'baking potato': 'potato',
    'chicken fillet': 'chicken breast',
    'minced beef': 'beef mince',
}

# Offer-side phrases are useful when supermarkets market the same food with
# extra words that recipe ingredients rarely contain.
SAMPLE_MARKET_TERMS = {
    'chicken breast': {'skinless', 'boneless', 'breast fillets'},
    'beef mince': {'lean', '5% fat', '12% fat'},
    'salmon fillet': {'skin on', 'boneless', 'portions'},
    'milk': {'whole', 'semi-skimmed', 'skimmed'},
    'potato': {'white potatoes', 'maris piper', 'king edward'},
}
