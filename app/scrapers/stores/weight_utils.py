"""
Shared weight/volume parsing utilities for store scrapers.

Parses product weight strings from store APIs into grams.

USAGE:
    from scrapers.stores.weight_utils import parse_weight

    grams = parse_weight("ca: 650g")        # 650.0
    grams = parse_weight("2200 gram")        # 2200.0
    grams = parse_weight("1.5kg")            # 1500.0
    grams = parse_weight("320ml")            # 320.0
    grams = parse_weight("75cl")             # 750.0
    grams = parse_weight("3dl")             # 300.0
    grams = parse_weight("st")              # None
"""
import re
from typing import Optional


def parse_weight(text: str) -> Optional[float]:
    """
    Parse a weight/volume string to grams (or ml for liquids).

    Handles formats from store API volume fields and product text.

    Examples:
        "ca: 650g" → 650.0
        "2200 gram ungefärlig vikt" → 2200.0
        "1.5kg" → 1500.0
        "320ml" → 320.0
        "75cl" → 750.0
        "8p/100g" → 100.0
        "2 liter" → 2000.0
        "st" → None
    """
    if not text:
        return None
    t = text.lower().strip()

    # "8p/100g" → take the weight part after /
    if '/' in t:
        t = t.split('/')[-1].strip()

    # kg: "1.5kg", "ca: 1,4kg", "2200 gram ungefärlig vikt"
    kg_match = re.search(r'(\d+(?:[,\.]\d+)?)\s*kg\b', t)
    if kg_match:
        return float(kg_match.group(1).replace(',', '.')) * 1000

    # grams: "650g", "ca: 650g", "400 gram", "2200 gram ungefärlig vikt"
    g_match = re.search(r'(\d+(?:[,\.]\d+)?)\s*(?:g|gram)\b', t)
    if g_match:
        return float(g_match.group(1).replace(',', '.'))

    # dl: "3dl", "5 dl" → ml (1 dl = 100 ml)
    dl_match = re.search(r'(\d+(?:[,\.]\d+)?)\s*dl\b', t)
    if dl_match:
        return float(dl_match.group(1).replace(',', '.')) * 100

    # cl: "75cl" → ml (≈ grams for water-based)
    cl_match = re.search(r'(\d+(?:[,\.]\d+)?)\s*cl\b', t)
    if cl_match:
        return float(cl_match.group(1).replace(',', '.')) * 10

    # ml: "320ml"
    ml_match = re.search(r'(\d+(?:[,\.]\d+)?)\s*ml\b', t)
    if ml_match:
        return float(ml_match.group(1).replace(',', '.'))

    # liters: "1.5l", "2 liter"
    l_match = re.search(r'(\d+(?:[,\.]\d+)?)\s*(?:l|liter)\b', t)
    if l_match:
        return float(l_match.group(1).replace(',', '.')) * 1000

    return None
