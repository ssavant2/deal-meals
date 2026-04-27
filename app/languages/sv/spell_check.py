"""Swedish spell-check profile data."""

DEFAULT_SPELL_EXCLUDED_WORDS = frozenset({
    ('bubblig', 'bubbliz'),
    ('cotto', 'cotta'),
    ('ifraiche', 'fraiche'),
    ('salma', 'salsa'),
    ('salamino', 'salamini'),
    ('salta', 'salsa'),
})

INFLECTION_SUFFIXES = (
    'n', 'en', 'an', 'et', 'erna', 'arna', 'orna',
    'ns', 'ens', 'ans', 'ets',
    's',
    'na', 'ade', 'ad', 'at', 'ar', 'or', 'er',
)

SAFE_NON_FOOD_WORDS = frozenset({
    'enbart', 'fräst', 'frästa', 'fräste', 'mager', 'magra', 'frisk',
    'limma', 'kokar', 'kokas', 'kokad', 'kokade', 'kokat',
    'fasta', 'färdiga', 'färskt',
    'bubblig', 'salta',
    'kvarn', 'skopor', 'smaksätt', 'hummrar',
    'kolsyrad', 'kolsyrat', 'växtbaserat', 'växtbaserad',
    'timjankvist', 'timjankvista', 'timjankvisten',
    'natten', 'kakan', 'fötter', 'lagen',
    'rättika', 'rättikar',
    'cannellini',
    'hushållsfärg',
    'whiskey',
    'caviar',
    'crema',
    'cotto',
    'ifraiche',
    'salame',
    'salma',
    'salamino',
    'rigatini',
    'fettuccini', 'fettucine',
    'linguini',
    'chevré', 'chevre',
    'frisée', 'frisé',
    'cremé', 'crème',
    'bananas', 'spices', 'spicy', 'fried', 'cream', 'eight', 'doodles',
    'bream', 'paste', 'crisp', 'pomme', 'chile', 'penner',
    'padron', 'padrón', 'iberica', 'frijs',
})
