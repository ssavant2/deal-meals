import re
from typing import Dict, FrozenSet, List, Set

try:
    from languages.sv.normalization import fix_swedish_chars
except ModuleNotFoundError:
    from app.languages.sv.normalization import fix_swedish_chars

from .keywords import NON_FOOD_KEYWORDS, PROCESSED_FOODS


# ============================================================================
# COMPOUND WORDS - Must match as complete words only
# ============================================================================

_COMPOUND_WORDS_SET: FrozenSet[str] = frozenset({
    # Spices/seasonings with types (don't match generic "buljong")
    'fiskbuljong', 'fiskbuljongtärning',
    'köttbuljong', 'köttbuljongtärning',
    'grönsaksbuljong', 'grönsaksbuljongtärning',
    'svampbuljong', 'svampbuljongtärning',
    'hönsbuljong', 'hönsbuljongtärning',
    'kycklingbuljong', 'kycklingbuljongtärning',
    'skaldjursbuljong', 'skaldjursbuljongtärning',
    'oxbuljong', 'oxbuljongtärning',
    'lantbuljong', 'lantbuljongtärning',

    # Seasoning mixes (don't match generic "peppar" or "citron")
    'citronpeppar', 'vitlökspeppar', 'örtsalt', 'havsalt',

    # Plant-based milks (don't match generic "mjölk")
    'kokosmjölk', 'mandelmjölk', 'havremjölk', 'sojamjölk',
    'rismjölk', 'cashewmjölk',

    # Specialty products
    'kokosolja', 'olivolja', 'sesamolja', 'rapsolja',

    # Herbs with variety prefix
    'bladpersilja',  # flat-leaf parsley ("Persilja Blad" → bladpersilja)

    # Vegetables with types
    'sötpotatis', 'vitlök', 'rödlök', 'gullök', 'salladslök',
    'schalottenlök', 'schalottenlock',  # shallots - distinct from gul lök
    'purjolök', 'purjolok',  # leeks

    # Potato types (distinct varieties, not interchangeable)
    'färskpotatis', 'farskpotatis',  # new potatoes (seasonal)
    'klyftpotatis',  # wedge potatoes (usually frozen/pre-made)
    'bakpotatis',  # baking potatoes

    # Pommes variants that should NOT match generic "pommes" recipes
    # These extract as their own compound keyword (won't match anything in practice)
    'pommes strips',  # unique variant, only match recipes saying "pommes strips"
    'pommes chateau',  # potatisklyftor, not pommes frites
    'pommes pinnes',  # potato sticks, not pommes frites
    'sötpotatis strips',  # sweet potato strips, own thing

    # Spices (compound forms - don't match just "chili" or "peppar")
    'chilipeppar', 'chiliflakes', 'chilipulver',  # dried chili spice, not fresh pepper
    'paprikapulver',  # spice, not fresh paprika

    # Vanilla compounds (don't match generic "vanilj")
    'vaniljsocker',  # vanilla sugar - NOT vanilla yogurt
    'vaniljextrakt',  # vanilla extract
    'vaniljstång', 'vaniljstang',  # vanilla pod
    'vaniljpulver',  # vanilla powder

    # Cereal/flake compounds
    'cornflakes',  # "corn flakes" = "cornflakes", not just "flakes"
    'kokosflingor',  # coconut flakes - not generic "flingor"
    'havreflingor',  # oat flakes
    'chiliflakes',  # chili flakes - not generic "flakes"

    # Dairy compound products
    'cottage cheese',  # "cottage cheese" should match as whole, not just "cheese"

    # Multi-word products joined via _SPACE_NORMALIZATIONS
    'coppadiparma',  # "coppa di parma" joined — Italian cured meat

    # Asian noodle types (joined from space-separated forms)
    'udonnudlar', 'sobanudlar', 'somennudlar', 'ramennudlar',
    'shanghainudlar', 'shanxinudlar', 'glasnudlar', 'äggnudlar',

    # Filled products (compound so "fylld" + "gnocchi" → "fylld gnocchi" as one keyword)
    'fylld gnocchi', 'fyllda gnocchi',

    # Sun-dried tomatoes — "soltorkade tomater" is a distinct product, not "tomat"
    'soltorkade tomater', 'soltorkad tomat', 'soltork tomat',

    # Fermented/pickled cucumber wording used in some recipes.
    # Must stay distinct from both fresh "gurka" and standard inlagdgurka variants.
    'syradgurka',

    # Multi-word cheese names — one keyword, not two
    'parmigiano reggiano',

    # Paste compounds (not "pasta" the noodle type)
    'misopasta',  # miso paste - "1 tsk vit misopasta" should NOT match pasta products
    'currypasta',  # curry paste - distinct from pasta
    'rödcurrypasta',  # red curry paste - distinct from green/yellow
    'gröncurrypasta',  # green curry paste
    'gulcurrypasta',  # yellow curry paste
})
# Sorted for deterministic iteration (Python set order varies with PYTHONHASHSEED)
COMPOUND_WORDS: List[str] = sorted(_COMPOUND_WORDS_SET)

# Pre-built substring lookup: word → [compounds containing that word as substring]
# Built lazily from COMPOUND_WORDS to speed up the per-word compound check
# from O(69) to O(1) dict lookup + O(small) compound list check.
_COMPOUND_WORD_INDEX: Dict[str, List[str]] = {}
for _cw in COMPOUND_WORDS:
    # Extract all substrings that could be words (3+ chars, alphabetic)
    for _i in range(len(_cw)):
        for _j in range(_i + 3, len(_cw) + 1):
            _sub = _cw[_i:_j]
            if _sub != _cw and _sub.isalpha():
                if _sub not in _COMPOUND_WORD_INDEX:
                    _COMPOUND_WORD_INDEX[_sub] = []
                _COMPOUND_WORD_INDEX[_sub].append(_cw)

# Keywords that must match at a word boundary, not as suffix of a compound word.
# "köttbullar" should match "500g köttbullar" but NOT "fiskköttbullar" (different product).
# "dressing" should match "2 dl dressing" but NOT "hamburgerdressing" (different condiment).
# Checked by verifying the character before the match is non-alpha (space, digit, start).
_SUFFIX_PROTECTED_KEYWORDS: FrozenSet[str] = frozenset({
    fix_swedish_chars(w).lower() for w in {
        'köttbullar', 'dressing',
        'krydda',     # "Klassisk Krydda" should NOT match inside compound "salladskrydda"
        'kärnor',     # "Oliver med Kärnor" should NOT match inside "granatäpplekärnor"
        'spaghetti',  # "Spaghetti Barilla" should NOT match inside "kålrotsspaghetti"
        'spagetti',   # alternate spelling
        'sallat',     # "Sallat Grön" should NOT match inside compound "plocksallat"
                      # (plocksallat recipes need 'plocksallat' keyword via OFFER_EXTRA_KEYWORDS)
        'senap',      # "Senap X" should NOT match inside "skånsksenap" compound
                      # (allows KSC-free qualifier matching for "senap skånsk" ingredients)
    }
})

# Keywords that must NOT be embedded in the MIDDLE of a word.
# Allowed at start of word ("risotto", "rispapper") or end of word ("basmatiris", "sushiris")
# but NOT in the middle ("grissini", "vegetarisk", "harissa", "polkagrisar").
# Less strict than _SUFFIX_PROTECTED — allows valid compound words where the keyword is the base.
_EMBEDDED_PROTECTED_KEYWORDS: FrozenSet[str] = frozenset({
    fix_swedish_chars(w).lower() for w in {
        'ris',  # blocks grissini, vegetarisk, harissa, crispy, polkagrisar, etc.
        'agar',  # blocks korvbrödsbagarn (brand name contains 'agar' as substring)
        'bröd',  # blocks lantbrödsmjöl → "Naan bröd" (bröd embedded in lantBRÖDsmjöl)
        'dryck',  # blocks generic "dryck" inside longer compounds like havredryckbarista
                  # while still allowing standalone "dryck" in explicit drink ingredients
    }
})

# Keywords where compound forms in recipe text require strict matching.
# When keyword appears as SUFFIX of a compound word in the recipe
# (e.g., "vinäger" inside "äppelcidervinäger"), the qualifier prefix
# (e.g., "äppelcider") must also appear in the product name.
# Without this, "Chinkiang Vinäger" would match "äppelcidervinäger".
_COMPOUND_STRICT_KEYWORDS: FrozenSet[str] = frozenset({
    fix_swedish_chars(w).lower() for w in {
        'vinäger',   # äppelcidervinäger, balsamvinäger, vitvinsvinäger
        'dryck',     # hasselnötsdryck, havredryck, mandeldryck
        'mjölk',     # torrmjölk, kokosmjölk, sojamjölk
        'innerfilé', 'innerfiléer', 'innerfileer',  # lamminnerfilé vs kycklinginnerfilé — animal prefix must match
        'färs',      # lammfärs vs nötfärs — animal prefix must match
                     # standalone "färs" matches all (no compound restriction)
        'soja',      # tamarisoja vs soja — tamari prefix must match
        'lök',       # silverlök vs lök — silver prefix must match
        'lökar',     # silverlökar vs lökar — silver prefix must match
        'korv',      # kycklingkorv, falukorv — type prefix must match
        'korvar',    # vegokorvar (plural) — same as korv
        'chorizo',   # vegochorizo → product must have "vego" prefix
                     # standalone "chorizo" matches all (no compound restriction)
        'burgare',   # vegoburgare → product must have "vego" prefix
        'burger',    # vegoburger variant
        'bullar',    # vegobullar → product must have "vego" prefix, not bread rolls
        'bacon',     # vegobacon → product must have "vego" prefix, not real bacon
        'chips',     # kokoschips, potatischips — type prefix must match
        'musslor',   # blåmusslor → product must have "blå", blocks generic canned mussels
        'chicken',   # pulledchicken → product must have "pulled", blocks generic chicken products
                     # standalone "chicken" matches all (no compound restriction)
        'salami',    # tryffelsalami, pepparsalami — type prefix must match
        'marmelad',  # apelsinmarmelad → product must have "apelsin", not just "marmelad"
        'jäst',      # näringsjäst ≠ bakjäst — prefix must match (ICA has real näringsjäst)
        'marinad',   # rödvinsmarinad / vitvinsmarinad should keep their wine prefix
                     # and not fall back to generic BBQ/herb marinades.
                     # standalone "marinad" still matches all marinades.
        'bröd',      # lantbröd, surdegsbröd, rågbröd, formbröd — bread type prefix must match
                     # standalone "bröd" matches all bread (no compound restriction)
        'biff',      # lövbiff, ryggbiff, flankstek — cut prefix must match
                     # standalone "biff" matches all (no compound restriction)
        'kaka',      # chokladkaka → product "Kaka Citronkaka" needs "choklad" prefix
                     # standalone "kaka" matches all (no compound restriction)
        'pudding',   # chokladpudding / vaniljpudding should keep their prefix
                     # and not fall back to generic protein/flavor pudding products.
                     # standalone "pudding" still matches all pudding products.
        'skorpor',   # cantucciniskorpor / fullkornsskorpor should keep their prefix
                     # and not fall back to generic skorpor products.
                     # standalone "skorpor" still matches all skorpor products.
        'tofu',      # naturelltofu → product must have "naturell" prefix
                     # standalone "tofu" matches all (no compound restriction)
        'sallad',    # potatissallad → product must have "potatis", not "wakame" or "provensalsk"
                     # standalone "sallad" matches all (no compound restriction)
        'sorbet',    # citronsorbet → product must have "citron", blocks "Sorbet Hallon"
                     # standalone "sorbet" matches all (no compound restriction)
        'nudlar',    # äggnudlar, glasnudlar → product must have "ägg"/"glas" prefix
                     # blocks "Nudlar Vermicelli", "Nudlar Champinjonsmak" from matching äggnudlar
                     # standalone "nudlar" matches all (no compound restriction)
        'baguette',  # vitlöksbaguette → product must have "vitlök", blocks plain "Baguette 330g"
                     # standalone "baguette" matches all (no compound restriction)
        'filéer',    # sardellfiléer → product must have "sardell", blocks "Filéer vegetariska Quorn"
        'filé',      # kycklingfilé → product must have "kyckling", blocks generic "filé" products
                     # standalone "filé"/"filéer" matches all (no compound restriction)
        'glass',     # vaniljglass → product must have "vanilj", blocks non-vanilla ice cream
        'kex',       # mariekex → product must have "marie", blocks "Frukost Crackers Göteborgs kex"
                     # standalone "kex" matches all (no compound restriction)
        'mjöl',      # potatismjöl → product must have "potatis", blocks "Mjöl 1kg Belje"
                     # vetemjöl → product must have "vete". standalone "mjöl" matches all.
        'strips',    # pommesstrips → product must have "pommes", blocks "Beef style strips"
                     # standalone "strips" matches all (no compound restriction)
        'ärtor',     # gråärtor → product must have "grå" (no ICA product has it → 0 matches)
        'ärter',     # gulaärter already handled; gråärter blocked too
                     # standalone "ärtor"/"ärter" matches all (no compound restriction)
    }
})

# Keywords where PREFIX compound forms in recipe text require strict matching.
# When keyword appears at the START of a compound word in the recipe
# (e.g., "choklad" inside "chokladkaka"), the qualifier suffix
# (e.g., "kaka") must also appear in the product name.
# Handles Swedish connecting letters (s, -) between prefix and suffix.
# Without this, "Mousse Choklad Protein" would match "chokladkaka" recipes.
_COMPOUND_STRICT_PREFIX_KEYWORDS: FrozenSet[str] = frozenset({
    fix_swedish_chars(w).lower() for w in {
        'hamburger',   # hamburgerbröd, hamburgerost, hamburgerdressing
        'mandel',      # mandelmjöl, mandelmassa, mandelspån
        'senap',       # senapsfrö, senapsfrön, senapspulver
        'kokos',       # kokosmjölk, kokosflingor, kokosolja, kokosgrädde
        'chili',       # chiliflakes, chilipulver, chilipeppar, chilisås
        'sallad',      # salladslök — spring onion, not lettuce/salad
        'kalkon',      # kalkonbröst, kalkonkorv, kalkonfärs — compound suffix must match
        'quorn',       # quornfärs, quornbitar, quornfiléer — compound suffix must match
        'pizza',       # pizzadeg, pizzabottnar, pizzamix, pizzasås — compound suffix must match
                       # blocks "MAX Snack Pizza" from matching 'pizzadeg' recipes
        'fläsk',       # fläsklägg, fläskkarré, fläskfilé, fläsksida — pork cut suffix must match
                       # blocks "Fläskfilé" from matching 'fläsklägg' recipes
    }
})

# Alias mappings for compound qualifiers where the Swedish name differs.
# e.g., "torrmjölk" has prefix "torr" but the product is called "mjölkpulver"
_MEAT_MINCE_PREFIXES: Set[str] = {
    'nöt', 'not', 'lamm', 'fläsk', 'flask', 'bland', 'kalv', 'kyckling',
    'kalkon', 'hjort', 'får', 'far', 'vildsvins', 'älg', 'alg',
    'chorizo', 'salsiccia', 'högrevs', 'hogrevs', 'hamburger',
    'höns', 'hons', 'ren', 'vilt',  # game/poultry
    'kött', 'kott',
}

# Poultry/meat cuts — all interchangeable in recipes (bröstfilé ≈ lårfilé ≈ filé)
_POULTRY_CUT_SUFFIXES: Set[str] = {
    'filé', 'file', 'fil',
    'bröst', 'brost',
    'bröstfil', 'bröstfilé', 'brostfil', 'brostfile',
    'lårfil', 'lårfilé', 'larfil', 'larfile',
}

_COMPOUND_QUALIFIER_ALIASES: Dict[str, Set[str]] = {
    'torr': {'pulver', 'torr'},  # torrmjölk = mjölkpulver
    # köttfärs/hushållsfärs = generic meat mince → matches all meat färs types
    # but NOT vegofärs/baljväxtfärs/quornfärs (plant-based ≠ kött)
    'kött': _MEAT_MINCE_PREFIXES,
    'kott': _MEAT_MINCE_PREFIXES,
    'hushålls': _MEAT_MINCE_PREFIXES,  # old Swedish term ≈ blandfärs
    'hushalls': _MEAT_MINCE_PREFIXES,
    # Bread compounds: "surdegsbröd" has connecting 's' → prefix 'surdegs'
    # but products may say "Bröd Surdeg" (without 's'). Accept both forms.
    'surdegs': {'surdegs', 'surdeg'},
    # Poultry cuts — recipe "kalkonfilé" should match kalkonbröstfil, kalkonlårfilé etc.
    **{cut: _POULTRY_CUT_SUFFIXES for cut in _POULTRY_CUT_SUFFIXES},
}


def _check_compound_strict(keyword: str, ingredient_lower: str,
                           product_name_lower: str,
                           ingredient_words: list = None,
                           check_prefix: bool = False) -> bool:
    """Check if a compound-strict keyword should be blocked.

    Returns True if the match should be BLOCKED.

    When check_prefix=False (default, suffix mode):
      keyword as suffix of compound → qualifier prefix must be in product.
      e.g., keyword "vinäger" in "äppelcidervinäger" → product must contain "äppelcider"

    When check_prefix=True (prefix mode):
      keyword as prefix of compound → qualifier suffix must be in product.
      e.g., keyword "choklad" in "chokladkaka" → product must contain "kaka"
      Handles Swedish connecting 's' (e.g., "matlagning" in "matlagningsvin" → suffix "vin")
    """
    words = ingredient_words or _WORD_PATTERN.findall(ingredient_lower)

    if check_prefix:
        # PREFIX mode: keyword at start of compound word
        found_compound = False
        for w in words:
            if w == keyword:
                return False  # standalone → no restriction
            if w.startswith(keyword) and len(w) > len(keyword):
                found_compound = True
                # Extract suffix, stripping Swedish connecting 's'
                suffix = w[len(keyword):]
                if suffix.startswith('s') and len(suffix) > 1:
                    suffix = suffix[1:]  # matlagningsvin → vin
                # Check aliases
                accepted = _COMPOUND_QUALIFIER_ALIASES.get(suffix, {suffix})
                if any(a in product_name_lower for a in accepted):
                    return False  # product has qualifier → valid
        return found_compound
    else:
        # SUFFIX mode: keyword at end of compound word (original behavior)
        for w in words:
            if w == keyword:
                return False
            if w.endswith(keyword) and len(w) > len(keyword):
                prefix = w[:-len(keyword)]
                accepted = _COMPOUND_QUALIFIER_ALIASES.get(prefix, {prefix})
                if not any(a in product_name_lower for a in accepted):
                    continue
                else:
                    return False
        has_compound = any(w.endswith(keyword) and len(w) > len(keyword) for w in words)
        return has_compound


def _has_word_boundary_match(keyword: str, text: str) -> bool:
    """Check if keyword appears at a word boundary (not as suffix of a compound word)."""
    pos = 0
    while True:
        pos = text.find(keyword, pos)
        if pos == -1:
            return False
        if pos == 0 or not text[pos - 1].isalpha():
            return True
        pos += 1


def _has_word_edge_match(keyword: str, text: str) -> bool:
    """Check if keyword appears at start OR end of a word (not embedded in the middle).

    "ris" in "basmatiris" → True (at end of word)
    "ris" in "rispapper" → True (at start of word)
    "ris" in "grissini" → False (embedded in middle)
    "ris" in "vegetarisk" → False (embedded in middle)
    """
    pos = 0
    kw_len = len(keyword)
    while True:
        pos = text.find(keyword, pos)
        if pos == -1:
            return False
        at_start = pos == 0 or not text[pos - 1].isalpha()
        end_pos = pos + kw_len
        at_end = end_pos >= len(text) or not text[end_pos].isalpha()
        if at_start or at_end:
            return True
        pos += 1

# Compound suffix extraction: when a compound keyword ends with one of these
# base words, ALSO add the base word as an additional keyword for FTS matching.
# Example: "högrevsburgare" ends with "burgare" → also add "hamburgare"
COMPOUND_BASE_KEYWORDS: Dict[str, str] = {
    'burgare': 'hamburgare',  # högrevsburgare, angusburage etc → also match "hamburgare" recipes
    'buljong': 'buljong',  # grönsaksbuljong → also extract "buljong" (for "grönsaks- eller hönsbuljong" patterns)
}


# ============================================================================
# PRE-COMPILED REGEX PATTERNS (Performance optimization)
# ============================================================================
# Building regex patterns once at module load instead of per-call
# This gives ~50x speedup for is_non_food_product and extract_keywords_from_product

def _build_combined_word_pattern(keywords: Set[str]) -> re.Pattern:
    """Build a single compiled regex that matches any keyword as whole word."""
    # Pre-normalize all keywords
    normalized = [fix_swedish_chars(kw).lower() for kw in keywords]
    # Sort by length (longest first) to ensure longer matches take precedence
    normalized = sorted(set(normalized), key=len, reverse=True)
    if not normalized:
        return None
    # Build combined pattern with smart word boundaries
    # \b only works at word-char boundaries, so entries ending with
    # non-word chars (e.g., "tonfiskfilé &") need special handling
    parts = []
    for kw in normalized:
        escaped = re.escape(kw)
        prefix = r'\b' if kw[0].isalnum() or kw[0] == '_' else ''
        suffix = r'\b' if kw[-1].isalnum() or kw[-1] == '_' else ''
        parts.append(prefix + escaped + suffix)
    pattern = '(' + '|'.join(parts) + ')'
    return re.compile(pattern, re.IGNORECASE)

# Pre-compiled pattern for NON_FOOD_KEYWORDS
_NON_FOOD_PATTERN = _build_combined_word_pattern(NON_FOOD_KEYWORDS)

# Pre-compiled pattern for PROCESSED_FOODS
_PROCESSED_FOODS_PATTERN = _build_combined_word_pattern(PROCESSED_FOODS)

# Pre-compiled pattern for extracting words from text (used in FP blocker check)
_WORD_PATTERN = re.compile(r'[a-zåäöé]+')
_WORD_PATTERN_4PLUS = re.compile(r'[a-zåäö]{4,}')
_RE_SPICE_AMOUNT = re.compile(r'\b(?:tsk|krm)\b')

def _is_whole_word(word: str, text: str) -> bool:
    """Check if word appears as a standalone word in text (not as suffix of compound word).

    'riven' in 'finriven farsk ingefara' → False (part of compound 'finriven')
    'riven' in 'riven ingefara' → True (standalone word)
    'ris' in 'jasminris och saffran' → False (part of compound 'jasminris')
    'ris' in 'saffran ris' → True (standalone word)
    """
    idx = text.find(word)
    while idx != -1:
        # Not preceded by a letter = standalone word (or start of compound as prefix, which is OK)
        if idx == 0 or not text[idx - 1].isalpha():
            return True
        idx = text.find(word, idx + 1)
    return False
