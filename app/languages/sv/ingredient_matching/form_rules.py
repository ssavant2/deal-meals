"""Form and juice rule data for Swedish ingredient matching.

Used by:
- validators.py — spice/fresh validation
- matching.py — fast herb/form checks and juice-product checks
"""

from typing import FrozenSet

try:
    from languages.sv.normalization import fix_swedish_chars
except ModuleNotFoundError:
    from app.languages.sv.normalization import fix_swedish_chars


FRESH_HERB_KEYWORDS: FrozenSet[str] = frozenset({
    'koriander', 'basilika', 'basilka', 'persilja', 'mynta', 'dill',
    'timjan', 'rosmarin', 'oregano', 'dragon', 'salvia',
    'citronmeliss', 'gräslök', 'graslok',
    'körvel', 'korvel',
    'persiljekvistar', 'persiljekvista',
    'mejram',
    'ingefära', 'ingefara',
    'gurkmeja',
    'kurkuma',
    'chili',
    'chilipeppar',
    'chilifrukt', 'chilifrukter',
})


FRESH_PRODUCT_INDICATORS: FrozenSet[str] = frozenset({
    'bunt', 'kruka', 'knippe', 'färsk', 'färska', 'farsk', 'farska',
    'lösvikt', 'losvikt', 'krus',
    ' blad',
    'klass ',
    '1-p',
    # NOTE: 'chilipeppar' removed — "Chilipeppar Malen" has it too, causing both
    # prod_is_fresh and prod_is_dried to be True → blocking logic skipped.
    # Fresh chilipeppar products still identified via 'klass ' or 'bunt'.
})


DRIED_PRODUCT_INDICATORS: FrozenSet[str] = frozenset({
    'burk', 'påse', 'pase',
    'torkad', 'torkade',
    'frystorkad', 'frystorkade',
    'malen', 'malna', 'malet',
    'pulver',
    'tetra',
})


FROZEN_PRODUCT_INDICATORS: FrozenSet[str] = frozenset({
    'fryst', 'frysta',
})


RECIPE_FRESH_INDICATORS: FrozenSet[str] = frozenset({
    'färsk', 'färska', 'farsk', 'farska',
    'kruka', 'krukor',
    'kvist', 'kvistar',
    'stjälk', 'stjalk',
    'knippe', 'knippa',
    'blad',
    'vippa', 'vippor',
    'kronor',
    'hackad', 'hackade',
    'grovhackad', 'grovhackade',
    'finhackad', 'finhackade',
    'finskuren', 'finskurna',
    'fint skuren', 'fint skurna',
    'klippt', 'klippta',
    'garnering',
    'servering',
    'topping',
    'näve', 'nave',
    'plockad', 'plockade',
    'ansa', 'ansad', 'ansade',
    'strimlad', 'strimlade',
    'skivad', 'skivade',  # sliced = fresh (e.g. "1 skivad chili")
    'riven', 'finriven',
    'chilifrukt', 'chilifrukter',  # always fresh produce — no dried product called "chilifrukt"
    # Colored chili variants = always fresh whole peppers (no spice jar named this way)
    'röd chilipeppar', 'rod chilipeppar',
    'grön chilipeppar', 'gron chilipeppar',
    'gul chilipeppar',
    'röd chili', 'rod chili',
    'grön chili', 'gron chili',
    'gul chili',
    # NOTE: plain 'chilipeppar' removed — ambiguous (can be "Chilipeppar Malen" = dried spice
    # or "1 röd chilipeppar" = fresh). Having it here caused "0,5 tsk chilipeppar" to
    # signal recipe_wants_fresh=True, incorrectly blocking dried chili products.
})


RECIPE_DRIED_INDICATORS: FrozenSet[str] = frozenset({
    'torkad', 'torkade', 'torkat',
    'malen', 'mald', 'malda', 'malna',
    'pulver',
})


RECIPE_FRESH_VOLUME_INDICATORS: FrozenSet[str] = frozenset({
    ' dl ',
    ' dl\n', ' dl,',
    ' st ',
    ' st\n',
})


RECIPE_DRIED_VOLUME_INDICATORS: FrozenSet[str] = frozenset({
    'tsk', 'tesked',
    'krm',
    'msk',
})


RECIPE_FROZEN_INDICATORS: FrozenSet[str] = frozenset({
    'fryst', 'frysta',
    'djupfryst', 'djupfrysta',
})


_PROCESSED_PRODUCT_INDICATORS: FrozenSet[str] = frozenset({
    fix_swedish_chars(w).lower() for w in {
        'fryst', 'frysta', 'fryst',
        'burk', 'konserv',
        'torkad', 'torkade', 'torkat',
        'krossad', 'krossade',
        'passerad', 'passerade',
        'juice', 'saft',
        'pressad', 'pressade',
        'puré', 'pure', 'purée', 'puree',
        'mos',
        'pulver',
        'riven',
        'inlagd', 'inlagda',
        'konserverad', 'konserverade',
        'kanderad', 'kanderade',
    }
})


JUICE_PRODUCT_INDICATORS: FrozenSet[str] = frozenset({
    'juice', 'pressad', 'pressade',
})


JUICE_INGREDIENT_INDICATORS: FrozenSet[str] = frozenset({
    'saft', 'juice',
})


JUICE_RULE_KEYWORDS: FrozenSet[str] = frozenset({
    'citron', 'lime',
})


NON_FOOD_CATEGORIES: FrozenSet[str] = frozenset({
    'hygiene', 'household', 'baby', 'petfood', 'garden'
})
