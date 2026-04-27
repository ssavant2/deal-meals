"""Swedish pantry matching support data."""

IGNORE_WORDS = frozenset({
    # Measurements
    'dl', 'ml', 'cl', 'msk', 'tsk', 'krm', 'kg', 'hg', 'gram',
    'st', 'stk', 'stycken', 'port', 'portioner', 'portion',
    'liter', 'kopp', 'koppar', 'paket', 'burk', 'burkar',
    # Cooking words
    'ca', 'cirka', 'ev', 'eventuellt', 'eller', 'och', 'med',
    'fint', 'grovt', 'hackad', 'hackade', 'skivad', 'skivade',
    'strimlad', 'strimlade', 'tärnad', 'tärnade', 'riven', 'rivna',
    'kokt', 'kokta', 'stekt', 'stekta', 'färsk', 'färska',
    'fryst', 'frysta', 'tinad', 'tinade', 'rumstempererad',
    'stor', 'stora', 'liten', 'lilla', 'små', 'medel', 'medium',
    'fin', 'fina', 'grov', 'grova', 'tunt', 'tunna', 'tjock', 'tjocka',
    'vit', 'vita', 'röd', 'röda', 'grön', 'gröna', 'gul', 'gula',
    # Function words
    'till', 'för', 'som', 'den', 'det', 'ett', 'en', 'lite',
    'efter', 'smak', 'valfri', 'valfritt', 'gärna', 'helst',
    # Common household staples
    'vatten', 'salt', 'flingsalt', 'peppar', 'svartpeppar', 'socker', 'olja',
    'matolja', 'olivolja', 'rapsolja', 'vinäger', 'ättika',
})
