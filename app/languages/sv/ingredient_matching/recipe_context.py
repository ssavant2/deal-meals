"""Recipe-context rules for Swedish ingredient matching."""

import re
from typing import Dict, FrozenSet, Set

try:
    from languages.sv.normalization import fix_swedish_chars
except ModuleNotFoundError:
    from app.languages.sv.normalization import fix_swedish_chars


_DESCRIPTOR_PHRASE_MARKERS = re.compile(
    r'(?:'
    r'gärna med\b'
    r'|garnamåen med\b'
    r'|fylld(?:a)? med\b'
    r'|med\s+\w*fyllning'
    r'|smaksatt(?:a)? med\b'
    r'|med smak av\b'
    r'|med\s+smak\s+av\b'
    r'|\bmed\b'
    r')',
    re.IGNORECASE
)


DESCRIPTOR_SUPPRESSION_PRIMARIES: FrozenSet[str] = frozenset({
    fix_swedish_chars(w).lower() for w in {
        'köttbullar', 'köttbulle',
        'tortellini', 'tortelloni', 'ravioli', 'cannelloni',
        'dumplings', 'wontons', 'gyoza',
        'falafel',
        'proteinpudding',
    }
})


CUISINE_CONTEXT: Dict[str, Set[str]] = {
    'taco': {
        'taco', 'tacos', 'texmex', 'tex mex', 'tex-mex',
        'mexikansk', 'burrito', 'fajita', 'enchilada',
        'quesadilla', 'nacho', 'nachos', 'wrap',
    },
    'texmex': {
        'taco', 'tacos', 'texmex', 'tex mex', 'tex-mex',
        'mexikansk', 'burrito', 'fajita', 'enchilada',
        'quesadilla', 'nacho', 'nachos', 'wrap',
    },
    'tex mex': {
        'taco', 'tacos', 'texmex', 'tex mex', 'tex-mex',
        'mexikansk', 'burrito', 'fajita', 'enchilada',
        'quesadilla', 'nacho', 'nachos', 'wrap',
    },
    'gyros': {
        'gyros', 'souvlaki', 'grekisk', 'pita',
        'tzatziki', 'medelhav',
    },
}
