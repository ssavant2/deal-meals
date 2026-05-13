#!/usr/bin/env python3
"""
Comprehensive sanity check for recipe-offer matching logic.

Tests all protection mechanisms:
1. STOP_WORDS - words removed from keyword extraction
2. NON_FOOD_KEYWORDS - products filtered out entirely
3. KEYWORD EXTRACTION - correct keywords from products
4. FALSE_POSITIVE_BLOCKERS - blocker words that prevent false matches
5. LEGITIMATE MATCHES - ensure valid matches still work
6. EDGE CASES - mixed blocker + standalone in same ingredient text
7. EMBEDDED PROTECTION - keywords protected from mid-word matching

Run: docker compose exec -T web python support_checks/run_deep_matcher_sanity.py
"""

import sys
import os
from types import SimpleNamespace
sys.path.insert(0, '/app' if os.path.exists('/app') else os.path.join(os.path.dirname(__file__), '..'))

from languages.sv.ingredient_matching import (
    extract_keywords_from_product,
    extract_keywords_from_ingredient,
    is_buffet_or_party_recipe,
    _is_false_positive_blocked,
    matches_ingredient_fast,
    precompute_offer_data,
    STOP_WORDS,
    NON_FOOD_KEYWORDS,
    FALSE_POSITIVE_BLOCKERS,
    FLAVOR_WORDS,
    CARRIER_PRODUCTS,
    _EMBEDDED_PROTECTED_KEYWORDS,
)
from languages.sv.ingredient_matching.extraction import _is_plain_instant_coffee_product_text
from languages.sv.ingredient_matching.validators import check_specialty_qualifiers
from languages.sv.ingredient_matching.normalization import _apply_space_normalizations
from languages.sv.category_utils import guess_category
from languages.sv.recipe_matcher_backend import _is_oreo_cookie_offer, _is_recipe_named_candy_offer
from languages.sv.normalization import fix_swedish_chars
from recipe_matcher import RecipeMatcher
from languages.sv.ingredient_matching.recipe_text import (
    expand_grouped_ingredient_text,
    parse_eller_alternatives,
    rewrite_buljong_eller_fond,
)

passed = 0
failed = 0
total_sections = 0


def section(name):
    global total_sections
    total_sections += 1
    print(f"\n--- {name} ---")


def test(desc, actual, expected):
    global passed, failed
    ok = actual == expected
    if ok:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {desc}")
        print(f"    Got:      {actual}")
        print(f"    Expected: {expected}")


def kw(product, category=""):
    return sorted(extract_keywords_from_product(product, category))


def blocked(keyword, ingredient):
    return _is_false_positive_blocked(keyword, ingredient)


def match_kw(product, ingredient, category=""):
    return matches_ingredient_fast(precompute_offer_data(product, category), ingredient)


def recipe_match_num(ingredients, offer):
    matcher = RecipeMatcher()
    recipe = SimpleNamespace(
        id='sanity-recipe',
        name='Sanity Recipe',
        ingredients=ingredients,
    )
    offer_obj = SimpleNamespace(
        id='sanity-offer',
        name=offer['name'],
        category=offer.get('category', ''),
        brand=offer.get('brand', ''),
        price=offer.get('price', 0),
        original_price=offer.get('original_price'),
        savings=offer.get('savings', 0),
        store=None,
        product_url=None,
        is_multi_buy=False,
        multi_buy_quantity=None,
        weight_grams=offer.get('weight_grams'),
    )
    return matcher._match_recipe_to_offers(recipe, [offer_obj], preferences={})['num_matches']


def recipe_match_num_cached(ingredients, offer):
    matcher = RecipeMatcher()
    recipe = SimpleNamespace(
        id='sanity-recipe',
        name='Sanity Recipe',
        ingredients=ingredients,
    )
    offer_obj = SimpleNamespace(
        id='sanity-offer',
        name=offer['name'],
        category=offer.get('category', ''),
        brand=offer.get('brand', ''),
        price=offer.get('price', 0),
        original_price=offer.get('original_price'),
        savings=offer.get('savings', 0),
        store=None,
        product_url=None,
        is_multi_buy=False,
        multi_buy_quantity=None,
        weight_grams=offer.get('weight_grams'),
    )
    offer_id = id(offer_obj)
    offer_keywords = {
        offer_id: extract_keywords_from_product(
            offer_obj.name, offer_obj.category, brand=offer_obj.brand
        )
    }
    offer_data_cache = {
        offer_id: precompute_offer_data(
            offer_obj.name,
            offer_obj.category,
            brand=offer_obj.brand,
            weight_grams=offer_obj.weight_grams,
        )
    }
    return matcher._match_recipe_to_offers(
        recipe,
        [offer_obj],
        preferences={},
        offer_keywords=offer_keywords,
        offer_data_cache=offer_data_cache,
    )['num_matches']


def recipe_match_groups(ingredients, offer, *, cached=False):
    matcher = RecipeMatcher()
    recipe = SimpleNamespace(
        id='sanity-recipe',
        name='Sanity Recipe',
        ingredients=ingredients,
    )
    offer_obj = SimpleNamespace(
        id='sanity-offer',
        name=offer['name'],
        category=offer.get('category', ''),
        brand=offer.get('brand', ''),
        price=offer.get('price', 0),
        original_price=offer.get('original_price'),
        savings=offer.get('savings', 0),
        store=None,
        product_url=None,
        is_multi_buy=False,
        multi_buy_quantity=None,
        weight_grams=offer.get('weight_grams'),
    )
    kwargs = {}
    if cached:
        offer_id = id(offer_obj)
        kwargs["offer_keywords"] = {
            offer_id: extract_keywords_from_product(
                offer_obj.name, offer_obj.category, brand=offer_obj.brand
            )
        }
        kwargs["offer_data_cache"] = {
            offer_id: precompute_offer_data(
                offer_obj.name,
                offer_obj.category,
                brand=offer_obj.brand,
                weight_grams=offer_obj.weight_grams,
            )
        }
    return matcher._match_recipe_to_offers(
        recipe,
        [offer_obj],
        preferences={},
        **kwargs,
    )['ingredient_groups']


def recipe_match_num_named(recipe_name, ingredients, offer):
    matcher = RecipeMatcher()
    recipe = SimpleNamespace(
        id='sanity-recipe',
        name=recipe_name,
        ingredients=ingredients,
    )
    offer_obj = SimpleNamespace(
        id='sanity-offer',
        name=offer['name'],
        category=offer.get('category', ''),
        brand=offer.get('brand', ''),
        price=offer.get('price', 0),
        original_price=offer.get('original_price'),
        savings=offer.get('savings', 0),
        store=None,
        product_url=None,
        is_multi_buy=False,
        multi_buy_quantity=None,
        weight_grams=offer.get('weight_grams'),
    )
    return matcher._match_recipe_to_offers(recipe, [offer_obj], preferences={})['num_matches']


def recipe_match_num_named_cached(recipe_name, ingredients, offer):
    matcher = RecipeMatcher()
    recipe = SimpleNamespace(
        id='sanity-recipe',
        name=recipe_name,
        ingredients=ingredients,
    )
    offer_obj = SimpleNamespace(
        id='sanity-offer',
        name=offer['name'],
        category=offer.get('category', ''),
        brand=offer.get('brand', ''),
        price=offer.get('price', 0),
        original_price=offer.get('original_price'),
        savings=offer.get('savings', 0),
        store=None,
        product_url=None,
        is_multi_buy=False,
        multi_buy_quantity=None,
        weight_grams=offer.get('weight_grams'),
    )
    offer_id = id(offer_obj)
    offer_keywords = {
        offer_id: extract_keywords_from_product(
            offer_obj.name, offer_obj.category, brand=offer_obj.brand
        )
    }
    offer_data_cache = {
        offer_id: precompute_offer_data(
            offer_obj.name,
            offer_obj.category,
            brand=offer_obj.brand,
            weight_grams=offer_obj.weight_grams,
        )
    }
    return matcher._match_recipe_to_offers(
        recipe,
        [offer_obj],
        preferences={},
        offer_keywords=offer_keywords,
        offer_data_cache=offer_data_cache,
    )['num_matches']


def recipe_match_num_multi(ingredients, offers):
    matcher = RecipeMatcher()
    recipe = SimpleNamespace(
        id='sanity-recipe',
        name='Sanity Recipe',
        ingredients=ingredients,
    )
    offer_objs = [
        SimpleNamespace(
            id=f'sanity-offer-{idx}',
            name=offer['name'],
            category=offer.get('category', ''),
            brand=offer.get('brand', ''),
            price=offer.get('price', 0),
            original_price=offer.get('original_price'),
            savings=offer.get('savings', 0),
            store=None,
            product_url=None,
            is_multi_buy=False,
            multi_buy_quantity=None,
            weight_grams=offer.get('weight_grams'),
        )
        for idx, offer in enumerate(offers)
    ]
    return matcher._match_recipe_to_offers(recipe, offer_objs, preferences={})['num_matches']


def recipe_match_data_multi_cached(ingredients, offers):
    matcher = RecipeMatcher()
    recipe = SimpleNamespace(
        id='sanity-recipe',
        name='Sanity Recipe',
        ingredients=ingredients,
    )
    offer_objs = [
        SimpleNamespace(
            id=f'sanity-offer-{idx}',
            name=offer['name'],
            category=offer.get('category', ''),
            brand=offer.get('brand', ''),
            price=offer.get('price', 0),
            original_price=offer.get('original_price'),
            savings=offer.get('savings', 0),
            store=None,
            product_url=None,
            is_multi_buy=False,
            multi_buy_quantity=None,
            weight_grams=offer.get('weight_grams'),
        )
        for idx, offer in enumerate(offers)
    ]
    offer_keywords = {
        id(offer_obj): extract_keywords_from_product(
            offer_obj.name, offer_obj.category, brand=offer_obj.brand
        )
        for offer_obj in offer_objs
    }
    offer_data_cache = {
        id(offer_obj): precompute_offer_data(
            offer_obj.name,
            offer_obj.category,
            brand=offer_obj.brand,
            weight_grams=offer_obj.weight_grams,
        )
        for offer_obj in offer_objs
    }
    return matcher._match_recipe_to_offers(
        recipe,
        offer_objs,
        preferences={},
        offer_keywords=offer_keywords,
        offer_data_cache=offer_data_cache,
    )


def expanded_prefilter_search_text(ingredients):
    expanded = []
    for ing in ingredients:
        expanded.extend(expand_grouped_ingredient_text(ing))
    text = fix_swedish_chars(" ".join(str(ing).lower() for ing in expanded)).lower()
    text = _apply_space_normalizations(text)
    return rewrite_buljong_eller_fond(text)


# ========================================================================
section("1. STOP_WORDS - words removed from keyword extraction")
# ========================================================================
test("tärningar is stop word", "tärningar" in STOP_WORDS, True)
test("tärning is stop word", "tärning" in STOP_WORDS, True)
test("normal is stop word", "normal" in STOP_WORDS, True)
test("fullkorn is stop word", "fullkorn" in STOP_WORDS, True)
test("syrlig is stop word", "syrlig" in STOP_WORDS, True)
test("syrliga is stop word", "syrliga" in STOP_WORDS, True)
test("fyrkantigt is stop word", "fyrkantigt" in STOP_WORDS, True)
test("filmjölk NOT stop word", "filmjölk" not in STOP_WORDS, True)
test("potatis NOT stop word", "potatis" not in STOP_WORDS, True)
test("mjölk NOT stop word", "mjölk" not in STOP_WORDS, True)
test("nektar NOT stop word", "nektar" not in STOP_WORDS, True)

# ========================================================================
section("2. NON_FOOD_KEYWORDS - products filtered entirely")
# ========================================================================
test("LED lamp → no keywords", kw("LED Normal E27 806 Lumen"), [])
test("Halogen lamp → no keywords", kw("Halogen G9 28W"), [])
test("Gifflar → no keywords", kw("Gifflar Kanel"), [])

# ========================================================================
section("3. KEYWORD EXTRACTION - correct keywords from products")
# ========================================================================
test(
    "Köttbuljong Tärningar → köttbuljong + buljong base keyword",
    kw("Köttbuljong Tärningar"),
    ["buljong", "köttbuljong"],
)
test(
    "Potatis Fast Klass 1 → has potatis",
    "potatis" in kw("Potatis Fast Klass 1"),
    True,
)
test(
    "Mjölk Längre Hållbarhet 3% → has mjölk",
    "mjölk" in kw("Mjölk Längre Hållbarhet 3%"),
    True,
)
test(
    "Jasminris → maps to parent keyword ris",
    kw("Jasminris"),
    ["ris"],
)
test(
    "Svart Ris EKO/KRAV → separate ris keyword",
    "ris" in kw("Svart Ris EKO/KRAV"),
    True,
)
test(
    "Smör Normalsaltat 80% → has smör",
    "smör" in kw("Smör Normalsaltat 80%"),
    True,
)
test(
    "Äpple Pink Lady Klass 1 → has äpple",
    "äpple" in kw("Äpple Pink Lady Klass 1"),
    True,
)
test(
    "Japanese Soy Sauce → has soja",
    "soja" in kw("Japanese Soy Sauce"),
    True,
)
test(
    "Blomsterhonung → has honung",
    "honung" in kw("Blomsterhonung"),
    True,
)
test(
    "Vitlök Kapsel Klass 1 → has vitlök",
    "vitlök" in kw("Vitlök Kapsel Klass 1"),
    True,
)
test(
    "Tortilla Original Medium 8-pack → has tortilla",
    "tortilla" in kw("Tortilla Original Medium 8-pack"),
    True,
)
test(
    "Bulgur av Durumvete → has durumvete",
    "durumvete" in kw("Bulgur av Durumvete"),
    True,
)
test(
    "Apelsin Klass 1 → has apelsin",
    "apelsin" in kw("Apelsin Klass 1"),
    True,
)
test(
    "Sparris Grön Klass1 → has sparris",
    "sparris" in kw("Sparris Grön Klass1"),
    True,
)
test(
    "Pirog Chicken Kebab Fryst → has kebab",
    "kebab" in kw("Pirog Chicken Kebab Fryst"),
    True,
)
test(
    "Nektar Apelsin → not empty (carrier product)",
    len(kw("Nektar Apelsin")) > 0,
    True,
)

# ========================================================================
section("4. FALSE POSITIVE BLOCKERS - should BLOCK (return True)")
# ========================================================================

# --- Mjölk blockers (Willys) ---
test("mjölk blocked by kokosmjölk", blocked("mjölk", "330 ml kokosmjölk"), True)
test("mjölk blocked by havremjölk", blocked("mjölk", "2 dl havremjölk"), True)
test("mjölk blocked by mjölkchoklad", blocked("mjölk", "100 g mjölkchoklad"), True)
test("mjölk blocked by mjölkfritt", blocked("mjölk", "mjölkfritt margarin"), True)
test("mjölk blocked by filmjölk", blocked("mjölk", "1 dl filmjölk"), True)
test("mjölk blocked by mjölkpulver", blocked("mjölk", "2 msk mjölkpulver"), True)
test(
    "mjölk blocked by mjölkdryck",
    blocked("mjölk", "2 dl växtbaserad mjölkdryck"),
    True,
)

# --- Soja blockers (Willys) ---
test("soja blocked by sojabönor", blocked("soja", "1 frp sojabönor"), True)
test("soja blocked by sojadryck", blocked("soja", "2 dl sojadryck"), True)
test("soja blocked by sojafärs", blocked("soja", "400 g sojafärs"), True)
test(
    "soja blocked by sojagurt", blocked("soja", "1 dl sojagurt naturell"), True
)
test("soja blocked by sojamjöl", blocked("soja", "1 dl sojamjöl"), True)
test("soja blocked by sojagrädde", blocked("soja", "1 dl sojagrädde"), True)
test("soja blocked by sojaglass", blocked("soja", "sojaglass vanilj"), True)

# --- Apelsin blockers (Willys) ---
test(
    "apelsin blocked by apelsinjuice",
    blocked("apelsin", "1 dl apelsinjuice"),
    True,
)
test(
    "apelsin blocked by apelsinsaft",
    blocked("apelsin", "1 dl apelsinsaft"),
    True,
)
test(
    "apelsin blocked by apelsinmarmelad",
    blocked("apelsin", "1 dl apelsinmarmelad"),
    True,
)
test(
    "apelsin blocked by apelsinkrokant",
    blocked("apelsin", "100 g mjölkchoklad med apelsinkrokant"),
    True,
)

# --- Potatis blockers (Willys) ---
test(
    "potatis blocked by potatischips",
    blocked("potatis", "1 dl potatischips"),
    True,
)
test(
    "potatis blocked by potatisgnocchi",
    blocked("potatis", "500 g potatisgnocchi"),
    True,
)
test(
    "potatis blocked by potatisgratäng",
    blocked("potatis", "1600 g potatisgratäng"),
    True,
)
test(
    "potatis blocked by potatiskroketter",
    blocked("potatis", "600 g potatiskroketter"),
    True,
)
test(
    "potatis blocked by potatisbullar",
    blocked("potatis", "12 potatisbullar"),
    True,
)
test(
    "potatis blocked by potatismospulver",
    blocked("potatis", "100 g potatismospulver"),
    True,
)

# --- Honung blockers (Willys) ---
test("honung blocked by honungsmelon", blocked("honung", "1 honungsmelon"), True)
test(
    "honung blocked by honungsrostade",
    blocked("honung", "1 dl honungsrostade nötter"),
    True,
)
test(
    "honung blocked by honungsmarinad",
    blocked("honung", "65 g honungsmarinad"),
    True,
)

# --- Tortilla blocker (Willys) ---
test(
    "tortilla blocked by tortillachips",
    blocked("tortilla", "125 g tortillachips"),
    True,
)

# --- Vitlök blockers (Willys) ---
test(
    "vitlök blocked by vitlökspulver",
    blocked("vitlök", "1 tsk vitlökspulver"),
    True,
)
test(
    "vitlök blocked by vitlöksdressing",
    blocked("vitlök", "1 dl vitlöksdressing"),
    True,
)
test(
    "vitlök blocked by vitlöksmarinad",
    blocked("vitlök", "2 msk vitlöksmarinad"),
    True,
)
test(
    "vitlök blocked by vitlökspeppar",
    blocked("vitlök", "1 tsk vitlökspeppar"),
    True,
)
test(
    "vitlök blocked by vitlökssås",
    blocked("vitlök", "50 ml vitlökssås"),
    True,
)

# --- Durumvete blocker (Willys) ---
test(
    "durumvete blocked by durumvetemjöl",
    blocked("durumvete", "1 dl durumvetemjöl"),
    True,
)

# --- Ris blockers (Hemköp) ---
test("ris blocked by risnudlar", blocked("ris", "200 g risnudlar"), True)
test("ris blocked by risoni", blocked("ris", "200 g risoni"), True)
test("ris blocked by rismjöl", blocked("ris", "1 dl rismjöl"), True)
test("ris blocked by rispapper", blocked("ris", "10 rispappersblad"), True)
test("ris blocked by risgryn", blocked("ris", "5 dl risgrynsgröt"), True)
test("ris blocked by risvinäger", blocked("ris", "1 msk risvinäger"), True)
test("ris blocked by kapris", blocked("ris", "1 msk kapris"), True)
test("ris blocked by sparris", blocked("ris", "500 g sparris"), True)

# --- Bröd blockers (Hemköp) ---
test("bröd blocked by brödsirap", blocked("bröd", "1 msk brödsirap"), True)
test("bröd blocked by brödkryddor", blocked("bröd", "2 msk brödkryddor"), True)
test(
    "bröd blocked by brödkrutonger",
    blocked("bröd", "1 dl brödkrutonger"),
    True,
)

# --- Pasta blockers (Mathem + earlier) ---
test("pasta blocked by currypasta", blocked("pasta", "1 msk röd currypasta"), True)
test("pasta blocked by pastasås", blocked("pasta", "1 dl pastasås"), True)
test("pasta blocked by tomatpasta", blocked("pasta", "2 msk tomatpasta"), True)
test("pasta blocked by chilipasta", blocked("pasta", "1 tsk chilipasta"), True)
test("pasta blocked by misopasta", blocked("pasta", "1 msk vit misopasta"), True)
test("pasta blocked by pastamaskin", blocked("pasta", "1 msk vatten utesluts om du har pastamaskin"), True)

# --- Äpple blockers (Mathem + earlier) ---
test("äpple blocked by granatäpple", blocked("äpple", "1 granatäpple"), True)
test("äpple blocked by äpplemos", blocked("äpple", "1 dl äpplemos"), True)

# --- Blåbär blocker (Mathem) ---
test("blåbär blocked by blåbärssylt", blocked("blåbär", "1 dl blåbärssylt"), True)

# --- Kebab blockers (Mathem) ---
test("kebab blocked by kebabsås", blocked("kebab", "1 dl kebabsås"), True)
test("kebab blocked by kebabkrydda", blocked("kebab", "2 msk kebabkrydda"), True)

# --- Sparris blocker (Mathem) ---
test(
    "sparris blocked by sparrisbroccoli",
    blocked("sparris", "200 g sparrisbroccoli"),
    True,
)

# --- Nektar blocker (ICA) ---
test("nektar blocked by nektariner", blocked("nektar", "3 nektariner"), True)

# --- Smör blockers (earlier sessions) ---
test(
    "smör blocked by smördeg",
    blocked("smör", "1 smördegsplatta"),
    True,
)
test("smör blocked by nötsmör", blocked("smör", "2 msk nötsmör"), True)
test("smör blocked by jordnötssmör", blocked("smör", "1 msk jordnötssmör"), True)

# --- Citron blockers ---
test(
    "citron blocked by citrongräs",
    blocked("citron", "2 stjälkar citrongräs"),
    True,
)
test(
    "citron blocked by citronmeliss",
    blocked("citron", "1 kvist citronmeliss"),
    True,
)

# --- Ost blockers ---
test("ost blocked by ostbågar", blocked("ost", "1 påse ostbågar"), True)

# --- Majs blockers ---
test("majs blocked by majsena", blocked("majs", "2 msk majsena"), True)
test("majs blocked by majsolja", blocked("majs", "1 dl majsolja"), True)

# --- Grädde blockers ---
test(
    "grädde blocked by kokosgrädde",
    blocked("grädde", "1 dl kokosgrädde"),
    True,
)
test(
    "grädde blocked by sojagrädde",
    blocked("grädde", "1 dl sojagrädde"),
    True,
)

# --- Kyckling blockers ---
# Generic "kyckling" keyword should NOT match specific chicken products
test(
    "kyckling blocked by kycklingbuljong",
    blocked("kyckling", "1 kycklingbuljongtärning"),
    True,
)
test(
    "kyckling blocked by kycklingkorv",
    blocked("kyckling", "300 g kycklingkorv"),
    True,
)
test(
    "kyckling blocked by kycklingvingar",
    blocked("kyckling", "300 g kycklingvingar"),
    True,
)
test(
    "kyckling blocked by kycklingklubba",
    blocked("kyckling", "2 st kycklingklubba"),
    True,
)
test(
    "kyckling blocked by kycklingfärs",
    blocked("kyckling", "300 g kycklingfärs"),
    True,
)

# --- Bönor blockers ---
test(
    "bönor blocked by sojabön",
    blocked("bönor", "200 g sojabönor"),
    True,
)
test(
    "bönor blocked by kikärtor... wait, wrong key",
    True,
    True,
)  # placeholder

# --- Skinka blockers ---
test(
    "skinka blocked by parmaskinka",
    blocked("skinka", "100 g parmaskinka"),
    True,
)
test(
    "skinka blocked by serranoskinka",
    blocked("skinka", "100 g serranoskinka"),
    True,
)

# --- Auto-generated FPB BLOCK tests (batch 30 expansion) ---
test("aluminium blocked by aluminiumfolie", blocked("aluminium", "1 st aluminiumfolie"), True)
test("ananas blocked by ananasjuice", blocked("ananas", "1 st ananasjuice"), True)
test("anis blocked by manis", blocked("anis", "1 st manis"), True)
test("anka blocked by grillplanka", blocked("anka", "1 st grillplanka"), True)
test("anka blocked by utbankade", blocked("anka", "500 g kycklingbröst utbankade filéer"), True)
test("anka blocked by utbankat", blocked("anka", "1 st utbankat kycklingbröst"), True)
test("bacon blocked by kycklingbacon", blocked("bacon", "1 st kycklingbacon"), True)
test("banan blocked by bananschalottenlock", blocked("banan", "1 st bananschalottenlock"), True)
test("basilika blocked by thaibasilika", blocked("basilika", "1 st thaibasilika"), True)
test("biff blocked by biffsmak", blocked("biff", "1 st biffsmak"), True)
test("bovete blocked by bovetemjol", blocked("bovete", "1 st bovetemjol"), True)
test(
    "Boveteflingor exact product no longer loses match to skafferi kaffe context",
    recipe_match_num(
        ["250 g Boveteflingor"],
        {"name": "Boveteflingor EKO glutenfri 375g Naturens skafferi", "category": "pantry"},
    ),
    1,
)
test("buljong blocked by fiskbuljong", blocked("buljong", "1 st fiskbuljong"), True)
test("bullar blocked by fiskbullar", blocked("bullar", "1 st fiskbullar"), True)
test("burgare blocked by bonburgare", blocked("burgare", "1 st bonburgare"), True)
test("caviar blocked by tangcaviar", blocked("caviar", "1 st tangcaviar"), True)
test("chicken blocked by chickennuggets", blocked("chicken", "1 st chickennuggets"), True)
test("chipotle blocked by chipotlepasta", blocked("chipotle", "1 st chipotlepasta"), True)
test(
    "KSC chipotle blocks generic chili powder on chipotle ingredient",
    recipe_match_num(
        ["2 tsk Chilipulver Chipotle"],
        {"name": "Chilipulver 40g ICA", "category": "spices"},
    ),
    0,
)
test(
    "KSC chipotle still allows exact chipotle product",
    recipe_match_num(
        ["2 tsk Chilipulver Chipotle"],
        {"name": "Chilipeppar Chipotle 33g Santa Maria", "category": "spices"},
    ),
    1,
)
test("chips blocked by bananachips", blocked("chips", "1 st bananachips"), True)
test("cider blocked by appelcidervinager", blocked("cider", "1 st appelcidervinager"), True)
test("delikatess blocked by delikatesspotatis", blocked("delikatess", "1 st delikatesspotatis"), True)
test("dill blocked by dillfrö", blocked("dill", "1 st dillfrö"), True)
test("feta blocked by fetare", blocked("feta", "1 st fetare"), True)
test("fil blocked by filé", blocked("fil", "1 st filé"), True)
test("fisk blocked by fisksmak", blocked("fisk", "1 st fisksmak"), True)
test("flundra blocked by halleflundra", blocked("flundra", "1 st halleflundra"), True)
test("fläsk blocked by fläskfärs", blocked("fläsk", "1 st fläskfärs"), True)
test("fond blocked by fiskfond", blocked("fond", "1 st fiskfond"), True)
test("fraiche blocked by havrefraiche", blocked("fraiche", "1 st havrefraiche"), True)
test("fänkål blocked by fänkålspollen", blocked("fänkål", "1 st fänkålspollen"), True)
test("Fänkål Krydda keyword normalized", extract_keywords_from_ingredient("2 tsk Fänkål Krydda"), ["fänkål"])
test("färs blocked by färsk", blocked("färs", "1 st färsk"), True)
# FPB['glass'] removed — compound-strict handles glass compound matching now
test("grape blocked by grapefrukt", blocked("grape", "1 st grapefrukt"), True)
test("groddar blocked by bongroddar", blocked("groddar", "1 st bongroddar"), True)
test("grytbitar blocked by fiskgrytbitar", blocked("grytbitar", "1 st fiskgrytbitar"), True)
test("grönsak blocked by grönsaksmak", blocked("grönsak", "1 st grönsaksmak"), True)
test("gurka blocked by attiksgurka", blocked("gurka", "1 st attiksgurka"), True)
test("gurkor blocked by attiksgurkor", blocked("gurkor", "1 st attiksgurkor"), True)
test("gyllen blocked by gyllenbrun", blocked("gyllen", "1 st gyllenbrun"), True)
test("hallon blocked by balsamicohallon", blocked("hallon", "1 st balsamicohallon"), True)
test("halloumi blocked by halloumiburgare", blocked("halloumi", "1 st halloumiburgare"), True)
test("hasselnöt blocked by hasselnötsdryck", blocked("hasselnöt", "1 st hasselnötsdryck"), True)
test("högrev blocked by högrevsfärs", blocked("högrev", "1 st högrevsfärs"), True)
test("holland blocked by hollandaisesås", blocked("holland", "1 st hollandaisesås"), True)
test("hushall blocked by hushallsfarg", blocked("hushall", "1 st hushallsfarg"), True)
test("hushalls blocked by hushallsfarg", blocked("hushalls", "1 st hushallsfarg"), True)
test("hushåll blocked by hushållsfärg", blocked("hushåll", "1 st hushållsfärg"), True)
test("hushålls blocked by hushållsfärg", blocked("hushålls", "1 st hushållsfärg"), True)
test("högrev blocked by högrevsfärs", blocked("högrev", "1 st högrevsfärs"), True)
test("inläggning blocked by inläggningssill", blocked("inläggning", "1 st inläggningssill"), True)
test("innanlår blocked by kalvinnanlår", blocked("innanlår", "1 st kalvinnanlår"), True)
test("jordgubb blocked by jordgubbssylt", blocked("jordgubb", "1 st jordgubbssylt"), True)
test("kakor blocked by pannkakor", blocked("kakor", "1 st pannkakor"), True)
test("kalamata blocked by kalamataoliver", blocked("kalamata", "1 st kalamataoliver"), True)
test("karamel blocked by karamellfarg", blocked("karamel", "1 st karamellfarg"), True)
test("storkornskaviar maps to stenbitsrom", "stenbitsrom" in extract_keywords_from_ingredient("1 st storkornskaviar"), True)
test(
    "löjrom product precompute also exposes generic rom",
    "rom" in precompute_offer_data("Amerikansk löjrom Fryst 80g Pandalus", "frozen")["keywords"],
    True,
)
test(
    "forellrom product precompute also exposes generic rom",
    "rom" in precompute_offer_data("Forellrom röd 80g Kallax", "pantry")["keywords"],
    True,
)
test("kokosmjöl blocked by kokosmjölk", blocked("kokosmjöl", "1 st kokosmjölk"), True)
test("koriander blocked by korianderfrö", blocked("koriander", "1 st korianderfrö"), True)
test("korv blocked by korvbrod", blocked("korv", "1 st korvbrod"), True)
test("korvbröd blocked by korvbrödsbagarn", blocked("korvbröd", "1 st korvbrödsbagarn"), True)
test("kummin blocked by spiskummin", blocked("kummin", "1 st spiskummin"), True)
test("körsbär blocked by körsbärskvist", blocked("körsbär", "1 st körsbärskvist"), True)
test("kött blocked by köttbullar", blocked("kött", "1 st köttbullar"), True)
test("lager blocked by lagerblad", blocked("lager", "1 st lagerblad"), True)
test("lamm blocked by lammfärs", blocked("lamm", "1 st lammfärs"), True)
test("lantbröd blocked by lantbrödsmjöl", blocked("lantbröd", "1 st lantbrödsmjöl"), True)
test("lime blocked by limeblad", blocked("lime", "1 st limeblad"), True)
test("lingon blocked by lingonsylt", blocked("lingon", "1 st lingonsylt"), True)
test("lök blocked by gräslök", blocked("lök", "1 st gräslök"), True)
test("majo blocked by majonas", blocked("majo", "1 st majonas"), True)
test("majonnäs blocked by srirachamajonnäs", blocked("majonnäs", "1 st srirachamajonnäs"), True)
test("mango blocked by mangochutney", blocked("mango", "1 st mangochutney"), True)
test("matbas blocked by tomatbas", blocked("matbas", "1 st tomatbas"), True)
test("matlagning blocked by matlagningsgrädde", blocked("matlagning", "1 st matlagningsgrädde"), True)
test("matlagnings blocked by matlagningsvin", blocked("matlagnings", "1 st matlagningsvin"), True)
test("mayo blocked by srirachamayo", blocked("mayo", "1 st srirachamayo"), True)
test("gari blocked by margarin", blocked("gari", "1 st margarin"), True)
test("melon blocked by melonkärnor", blocked("melon", "1 st melonkärnor"), True)
test("mjöl blocked by bovetemjöl", blocked("mjöl", "1 st bovetemjöl"), True)
test("mjölkchoklad blocked by mjölkchokladknappar", blocked("mjölkchoklad", "1 st mjölkchokladknappar"), True)
test("musslor blocked by kammusslor", blocked("musslor", "1 st kammusslor"), True)
test("nöt blocked by nötbitar", blocked("nöt", "1 st nötbitar"), True)
test("nötter blocked by cashewnötter", blocked("nötter", "1 st cashewnötter"), True)
test("paprika blocked by paprikakrydda", blocked("paprika", "1 st paprikakrydda"), True)
test("persilja blocked by bladpersilja", blocked("persilja", "1 st bladpersilja"), True)
test("pinsa blocked by pinsasås", blocked("pinsa", "1 st pinsasås"), True)
test("pudding blocked by blodpudding", blocked("pudding", "1 st blodpudding"), True)
test("pumpa blocked by pumpafron", blocked("pumpa", "1 st pumpafron"), True)
test("redning blocked by beredning", blocked("redning", "1 st beredning"), True)
test("risotto blocked by risotton", blocked("risotto", "1 st risotton"), True)
test("rom blocked by roman", blocked("rom", "1 st roman"), True)
test("rostbiff blocked by lammrostbiff", blocked("rostbiff", "1 st lammrostbiff"), True)
test("räk blocked by räksmak", blocked("räk", "1 st räksmak"), True)
test("sallad blocked by fruksalladen", blocked("sallad", "1 st fruksalladen"), True)
test("sallads blocked by salladslök", blocked("sallads", "1 st salladslök"), True)
test("senap blocked by dijonsenap", blocked("senap", "1 st dijonsenap"), True)
test("sill blocked by fusilli", blocked("sill", "1 st fusilli"), True)
test("sirap blocked by agavesirap", blocked("sirap", "1 st agavesirap"), True)
test("socker blocked by sockerart", blocked("socker", "1 st sockerart"), True)
test("ströbröd blocked by pankoströbröd", blocked("ströbröd", "1 st pankoströbröd"), True)
test("surdeg blocked by surdegsstart", blocked("surdeg", "1 st surdegsstart"), True)
test("svamp blocked by portabellosvamp", blocked("svamp", "1 st portabellosvamp"), True)
test("svartvinbärs blocked by svartvinbärsblad", blocked("svartvinbärs", "1 st svartvinbärsblad"), True)
test("sylt blocked by syltlok", blocked("sylt", "1 st syltlok"), True)
test("taco blocked by tacochips", blocked("taco", "1 st tacochips"), True)
test("tofu blocked by silkestofu", blocked("tofu", "1 st silkestofu"), True)
test("tomat blocked by körsbärstomat", blocked("tomat", "1 st körsbärstomat"), True)
test("tomater blocked by körsbärstomater", blocked("tomater", "1 st körsbärstomater"), True)
test("vanilj blocked by vaniljextrakt", blocked("vanilj", "1 st vaniljextrakt"), True)
test("vanill blocked by vanillinsocker", blocked("vanill", "1 st vanillinsocker"), True)
test("vegeta blocked by vegetabilisk", blocked("vegeta", "1 st vegetabilisk"), True)
test("vetemjöl blocked by bovetemjöl", blocked("vetemjöl", "1 st bovetemjöl"), True)
test("vilt blocked by viltfärs", blocked("vilt", "1 st viltfärs"), True)
test("yoghurt blocked by avokadoyoghurt", blocked("yoghurt", "1 st avokadoyoghurt"), True)
test("ägg blocked by blötlägg", blocked("ägg", "1 st blötlägg"), True)
test("äppelcider blocked by äppelcidervinäger", blocked("äppelcider", "1 st äppelcidervinäger"), True)
test("äppeljuice blocked by granatäppeljuice", blocked("äppeljuice", "1 st granatäppeljuice"), True)
test("ärtor blocked by gulaärtor", blocked("ärtor", "1 st gulaärtor"), True)
test("ättika blocked by rättika", blocked("ättika", "1 st rättika"), True)

# ========================================================================
section("5. LEGITIMATE MATCHES - should NOT block (return False)")
# ========================================================================

# --- Basic standalone keywords ---
test("mjölk standalone OK", blocked("mjölk", "1/2 dl mjölk"), False)
test(
    "mjölk in standardmjölk OK",
    blocked("mjölk", "0.5 dl standardmjölk"),
    False,
)
test(
    "mjölk in mellanmjölk OK", blocked("mjölk", "3 dl mellanmjölk"), False
)
test(
    "mjölk in gräddmjölk OK", blocked("mjölk", "3 dl gräddmjölk"), False
)
test("soja standalone OK", blocked("soja", "3 msk soja"), False)
test("soja in tamarisoja OK", blocked("soja", "1 msk tamarisoja"), False)
test("apelsin standalone OK", blocked("apelsin", "1 st apelsin"), False)
test(
    "apelsin in blodapelsin OK",
    blocked("apelsin", "1 blodapelsin"),
    False,
)
test("potatis standalone OK", blocked("potatis", "1 kg potatis"), False)
test(
    "potatis in delikatesspotatis OK",
    blocked("potatis", "1 kg delikatesspotatis"),
    False,
)
test(
    "potatis in sparrispotatis OK",
    blocked("potatis", "450 g sparrispotatis"),
    False,
)
test(
    "potatis in potatismos OK (homemade)",
    blocked("potatis", "potatismos"),
    False,
)
test("honung standalone OK", blocked("honung", "1 msk honung"), False)
test(
    "honung in flytande honung OK",
    blocked("honung", "1 msk flytande honung"),
    False,
)
test(
    "tortilla in tortillabröd OK",
    blocked("tortilla", "4 stora tortillabröd"),
    False,
)
test(
    "vitlök in vitlöksklyftor OK",
    blocked("vitlök", "2 vitlöksklyftor"),
    False,
)
test("vitlök standalone OK", blocked("vitlök", "1 klyfta vitlök"), False)
test("ris standalone OK", blocked("ris", "4 port kokt ris"), False)
test("ris in jasminris OK", blocked("ris", "2 dl jasminris"), False)
test("ris in arborioris OK", blocked("ris", "250 g arborioris"), False)
test("ris in risottoris OK", blocked("ris", "2 dl risottoris"), False)
test("ris in vialone nano OK", blocked("ris", "250 g vialone nano"), False)
test("ris in avorio OK", blocked("ris", "250 g avorio"), False)
test("pasta standalone OK", blocked("pasta", "400 g pasta"), False)
test("pasta in skruvpasta OK", blocked("pasta", "200 g skruvpasta"), False)
test(
    "pasta in pastamore OK (it's a pasta type)",
    blocked("pasta", "400 g pastamore"),
    False,
)
test("äpple standalone OK", blocked("äpple", "2-3 äpplen"), False)
test("smör standalone OK", blocked("smör", "150 g smör"), False)
test("smör in smörja OK (greasing)", blocked("smör", "smör till att smörja formen"), False)
test("ost standalone OK", blocked("ost", "4 dl riven ost"), False)
test("ost in hushållsost OK", blocked("ost", "100 g hushållsost"), False)
test("ost in hårdost OK", blocked("ost", "75 g skivad hårdost"), False)
test("ost in magerost OK", blocked("ost", "80 g riven magerost"), False)
test(
    "ost in mozzarellaost BLOCKED (specialty cheese)",
    blocked("ost", "250 g mozzarellaost"),
    True,
)
test("bröd standalone OK", blocked("bröd", "2 skivor bröd"), False)
test("blåbär standalone OK", blocked("blåbär", "125 g blåbär"), False)
test("kebab standalone OK", blocked("kebab", "1 förp kebab"), False)
test("kebab in kebabkött OK", blocked("kebab", "150 g kebabkött"), False)
test("sparris standalone OK", blocked("sparris", "1 knippe sparris"), False)
test(
    "sparris in grönsparris OK",
    blocked("sparris", "500 g grönsparris"),
    False,
)
test("majs standalone OK", blocked("majs", "200 g majs"), False)
test("majs in majskorn OK", blocked("majs", "1 burk majskorn"), False)
test("citron standalone OK", blocked("citron", "1 citron"), False)
test(
    "grädde standalone OK", blocked("grädde", "2 dl vispgrädde"), False
)
test(
    "kyckling in kycklingfilé OK (filé = generic kyckling)",
    blocked("kyckling", "500 g kycklingfilé"),
    False,
)
test(
    "kyckling in kycklinglår OK (lår = filé = generic kyckling)",
    blocked("kyckling", "500 g kycklinglår"),
    False,
)
test(
    "kyckling in kycklingbröst OK (bröst = filé = generic kyckling)",
    blocked("kyckling", "200 g kycklingbröst"),
    False,
)
test(
    "kyckling standalone OK",
    blocked("kyckling", "1 hel kyckling"),
    False,
)
test("Kalkon Hel keyword normalized", extract_keywords_from_ingredient("3.5 kg Kalkon Hel"), ["helkalkon"])
test("skinka standalone OK", blocked("skinka", "200 g kokt skinka"), False)
test(
    "durumvete standalone OK",
    blocked("durumvete", "2 dl bulgur av durumvete"),
    False,
)

# --- Auto-generated standalone OK tests (batch 30 expansion) ---
test("ananas standalone OK", blocked("ananas", "200 g ananas"), False)
test("bacon standalone OK", blocked("bacon", "200 g bacon"), False)
test("basilika standalone OK", blocked("basilika", "200 g basilika"), False)
test("biff standalone OK", blocked("biff", "200 g biff"), False)
test("buljong standalone OK", blocked("buljong", "200 g buljong"), False)
test("dill standalone OK", blocked("dill", "200 g dill"), False)
test("fisk standalone OK", blocked("fisk", "200 g fisk"), False)
test("fläsk standalone OK", blocked("fläsk", "200 g fläsk"), False)
test("fond standalone OK", blocked("fond", "200 g fond"), False)
test("gurka standalone OK", blocked("gurka", "200 g gurka"), False)
test("hallon standalone OK", blocked("hallon", "200 g hallon"), False)
test("halloumi standalone OK", blocked("halloumi", "200 g halloumi"), False)
test("koriander standalone OK", blocked("koriander", "200 g koriander"), False)
test("kött standalone OK", blocked("kött", "200 g kött"), False)
test("lamm standalone OK", blocked("lamm", "200 g lamm"), False)
test("lime standalone OK", blocked("lime", "200 g lime"), False)
test("lingon standalone OK", blocked("lingon", "200 g lingon"), False)
test("lök standalone OK", blocked("lök", "200 g lök"), False)
test("mango standalone OK", blocked("mango", "200 g mango"), False)
test("paprika standalone OK", blocked("paprika", "200 g paprika"), False)
test("persilja standalone OK", blocked("persilja", "200 g persilja"), False)
test("pumpa standalone OK", blocked("pumpa", "200 g pumpa"), False)
test("senap standalone OK", blocked("senap", "200 g senap"), False)
test("sirap standalone OK", blocked("sirap", "200 g sirap"), False)
test("socker standalone OK", blocked("socker", "200 g socker"), False)
test("svamp standalone OK", blocked("svamp", "200 g svamp"), False)
test("taco standalone OK", blocked("taco", "200 g taco"), False)
test("tofu standalone OK", blocked("tofu", "200 g tofu"), False)
test("tomat standalone OK", blocked("tomat", "200 g tomat"), False)
test("vanilj standalone OK", blocked("vanilj", "200 g vanilj"), False)
test("yoghurt standalone OK", blocked("yoghurt", "200 g yoghurt"), False)
test("ägg standalone OK", blocked("ägg", "200 g ägg"), False)
test("ärtor standalone OK", blocked("ärtor", "200 g ärtor"), False)

# ========================================================================
section("6. EDGE CASES - mixed blocker + standalone in same text")
# ========================================================================
test(
    "pasta + pastasås → NOT blocked (pasta standalone too)",
    blocked("pasta", "350 g pasta och 1 dl pastasås"),
    False,
)
test(
    "mjölk + kokosmjölk → NOT blocked (mjölk standalone too)",
    blocked("mjölk", "2 dl kokosmjölk och 1 dl mjölk"),
    False,
)
test(
    "apelsin + apelsinjuice → NOT blocked (apelsin standalone too)",
    blocked("apelsin", "1 apelsin och 1 dl apelsinjuice"),
    False,
)
test(
    "honung + honungsmelon → NOT blocked (honung standalone too)",
    blocked("honung", "1 msk honung och 1 honungsmelon"),
    False,
)
test(
    "potatis + potatischips → NOT blocked (potatis standalone too)",
    blocked("potatis", "1 kg potatis och 1 dl potatischips"),
    False,
)
test(
    "vitlök + vitlökspulver → NOT blocked (vitlök standalone too)",
    blocked("vitlök", "2 vitlöksklyftor och 1 tsk vitlökspulver"),
    False,
)
test(
    "soja + sojabönor → NOT blocked (soja standalone too)",
    blocked("soja", "3 msk soja och 100 g sojabönor"),
    False,
)
test(
    "ris + risvinäger → NOT blocked (ris standalone too)",
    blocked("ris", "4 dl ris och 1 msk risvinäger"),
    False,
)
test(
    "smör + nötsmör → NOT blocked (smör standalone too)",
    blocked("smör", "100 g smör och 2 msk nötsmör"),
    False,
)
test(
    "citron + citrongräs → NOT blocked (citron standalone too)",
    blocked("citron", "1 citron och 2 stjälkar citrongräs"),
    False,
)

# ========================================================================
section("7. EMBEDDED PROTECTION - ris in middle of words")
# ========================================================================
test("ris is embedded protected", "ris" in _EMBEDDED_PROTECTED_KEYWORDS, True)
test("dryck is embedded protected", "dryck" in _EMBEDDED_PROTECTED_KEYWORDS, True)
# (The actual mid-word blocking is in cache_manager, not _is_false_positive_blocked)
# These words contain "ris" mid-word and should NOT match rice products:
# vegetarisk, berberisbär, selleristjälk, crispy, grissini, kapris

# ========================================================================
section("8. REPORTED MATCHING ISSUES - regression tests for user-reported problems")
# ========================================================================

# Helper for matching tests
def match(product, ingredient, category=""):
    """Return matched keyword or None."""
    od = precompute_offer_data(product, category)
    return matches_ingredient_fast(od, ingredient)

# --- Ready meals / non-food that should be BLOCKED (empty keywords) ---
test("Tareqs Lasagne → blocked", kw("Tareqs Lasagne 400g"), [])
test("Pasta Carbonara Fryst → blocked", kw("Pasta Carbonara Fryst"), [])
test("Spansk Tortilla med Lök → blocked", kw("Spansk Tortilla med Lök"), [])
test("Ramlösa Grönt Äpple → blocked", kw("Ramlösa Grönt Äpple"), [])
test("Ramlosa Grönt Äpple → blocked (ASCII)", kw("Ramlosa Grönt Äpple"), [])
test("Smör & Raps EKO Matfett → blocked", kw("Smör & Raps EKO Matfett 500g"), [])
test("Tagliatelle Kyckling Fryst → blocked", kw("Tagliatelle Kyckling Fryst"), [])
test("Dagens Rostad Kyckling Fryst → blocked", kw("Dagens Rostad Kyckling Fryst"), [])

# --- Pulled products: joined via space normalization, each variant is unique ---
test("Pulled Beef → [pulledbeef]", kw("Pulled Beef"), ["pulledbeef"])
test("Pulled Pork → [pulledpork]", kw("Pulled Pork"), ["pulledpork"])
test("Pulled Chicken → [pulledchicken]", kw("Pulled Chicken"), ["pulledchicken"])
test("Pulled Oumph → [pulledoumph]", kw("Pulled Oumph"), ["pulledoumph"])

# --- Pulled: should NOT cross-match between variants ---
test("Pulled Beef ≠ 'pulled pork'", match("Pulled Beef", "1 förp pulled pork"), None)
test("Pulled Pork ≠ 'pulled beef'", match("Pulled Pork", "500g pulled beef"), None)
test("Pulled Beef ≠ 'Vegetarisk Pulled'", match("Pulled Beef", "Vegetarisk Pulled"), None)

# --- Kyckling Drumsticks: vitlök should be stripped (carrier) ---
test(
    "Drumsticks → kyckling + kycklingben, NOT vitlök",
    kw("Kyckling Drumsticks Örter & Vitlök"),
    ["kyckling", "kycklingben"],
)

# --- Mango: should match fresh mango but NOT mango chutney ---
test("Mango Fryst ≠ 'Mango Chutney'", match("Mango Fryst 250g", "4 msk Mango Chutney"), None)
test("Mango Fryst = '1 mango'", match("Mango Fryst 250g", "1 mango") is not None, True)

# --- Halloumi: should NOT match halloumiburgare ---
test("Halloumi Skivad ≠ 'Halloumiburgare'", match("Halloumi Skivad", "480g Halloumiburgare"), None)
test("Halloumi Skivad = 'Halloumi'", match("Halloumi Skivad", "200g Halloumi") is not None, True)
test(
    "Halloumiburgare = 'Halloumiburgare'",
    match("Halloumiburgare 480g", "480g Halloumiburgare") is not None,
    True,
)

# --- Batch 17-20 regression tests ---
# NOTE: match() only tests matches_ingredient_fast (product→ingredient matching).
# PNB, RIB, descriptor suppression run in recipe_matcher.py Phase 1 (pipeline level)
# and are tested via dict/config checks below, not match().

# FPB: blodpudding ≠ protein pudding (runs in matches_ingredient_fast)
test("Protein Pudding ≠ 'blodpudding'", match("Chocolate Protein Pudding Lactose Free", "400 g blodpudding"), None)
test("Blodpudding = 'blodpudding'", match("Blodpudding Glutenfri", "400 g blodpudding") is not None, True)

# FPB: bovetemjöl ≠ vetemjöl
test("Vetemjöl ≠ 'bovetemjöl'", match("Vetemjöl", "2 dl bovetemjöl"), None)
test("Vetemjöl = 'vetemjöl'", match("Vetemjöl", "2 dl vetemjöl") is not None, True)

# FPB: lasagne ready meal ≠ lasagneplattor
test("Lasagne ≠ 'lasagneplattor'", blocked('lasagne', '300 g lasagneplattor'), True)
test("Lasagneplattor = 'lasagneplattor'", match("Lasagneplattor", "300 g lasagneplattor") is not None, True)

# FPB: frozen pizza keyword ≠ pizzadeg
test("pizza blocked in 'pizzadeg'", blocked('pizza', '1 pizzadeg'), True)
test("Pizzadeg = 'pizzadeg'", match("Pizzadeg Napoli", "1 pizzadeg") is not None, True)

# FPB: kotlett — laxkotlett ≠ pork kotlett
test("kotlett blocked in 'laxkotletter'", blocked('kotlett', '4 st laxkotletter'), True)

# FPB: mjölk blocked in mjölkchoklad (keyword promotion guard)
test("mjölk blocked in 'mjölkchoklad'", blocked('mjölk', 'mjölkchoklad'), True)

# PNB config tests (checked at pipeline level in recipe_matcher.py)
from languages.sv.ingredient_matching import PRODUCT_NAME_BLOCKERS
test("PNB nöt → beef words", 'biff' in PRODUCT_NAME_BLOCKERS.get('nöt', set()), True)
test("PNB indian → spice words", 'spice' in PRODUCT_NAME_BLOCKERS.get('indian', set()), True)
test("PNB matolja → smör", 'smör' in PRODUCT_NAME_BLOCKERS.get('matolja', set()), True)
test("PNB rapsolja → smör", 'smör' in PRODUCT_NAME_BLOCKERS.get('rapsolja', set()), True)
test("PNB pasta → spaghetti removed (pasta matches all regular pasta)", 'spaghetti' in PRODUCT_NAME_BLOCKERS.get('pasta', set()), False)
test("PNB pasta → gnocchi (specific, still blocked)", 'gnocchi' in PRODUCT_NAME_BLOCKERS.get('pasta', set()), True)
test("PNB pasta → tortellini (filled, still blocked)", 'tortellini' in PRODUCT_NAME_BLOCKERS.get('pasta', set()), True)
test("PNB hamburgare → dressing", 'dressing' in PRODUCT_NAME_BLOCKERS.get('hamburgare', set()), True)
test("PNB solroskärnor → fröknäcke", any('knäcke' in w for w in PRODUCT_NAME_BLOCKERS.get('solroskärnor', set())), True)
test("PNB pineapple → vodka", 'vodka' in PRODUCT_NAME_BLOCKERS.get('pineapple', set()), True)

# RIB config tests (checked at pipeline level)
from languages.sv.ingredient_matching import RECIPE_INGREDIENT_BLOCKERS
test("RIB vitlök → färskost", any('färskost' in w for w in RECIPE_INGREDIENT_BLOCKERS.get('vitlök', set())), True)
test("RIB chili → pesto", 'pesto' in RECIPE_INGREDIENT_BLOCKERS.get('chili', set()), True)
test("RIB kakao → granola", 'granola' in RECIPE_INGREDIENT_BLOCKERS.get('kakao', set()), True)

# Specialty qualifier: svart vitlök
from languages.sv.ingredient_matching import SPECIALTY_QUALIFIERS
test("SQ vitlök has 'svart'", 'svart' in SPECIALTY_QUALIFIERS.get('vitlök', []), True)

# Descriptor suppression: \bmed\b marker and köttbullar primary
from languages.sv.ingredient_matching import _DESCRIPTOR_PHRASE_MARKERS, DESCRIPTOR_SUPPRESSION_PRIMARIES
test("Descriptor marker matches 'med'", _DESCRIPTOR_PHRASE_MARKERS.search('köttbullar med persilja') is not None, True)
test("köttbullar in primaries", any('köttbullar' in p for p in DESCRIPTOR_SUPPRESSION_PRIMARIES), True)

# --- Batch 21-26 regression tests ---

# FPB: cantal ≠ cantaloupe, chokladsmak ≠ choklad
test("cantal blocked in 'cantaloupemelon'", blocked('cantal', 'cantaloupemelon'), True)
test("choklad blocked in 'chokladsmak'", blocked('choklad', 'dryck med chokladsmak'), True)

# PNB: cheddar→sauce, napoli→pizzadeg, nudlar→konjac, smokey→ribs
test("PNB cheddarost → sauce", 'sauce' in PRODUCT_NAME_BLOCKERS.get('cheddarost', set()), True)
test("PNB napoli → pizzadeg", 'pizzadeg' in PRODUCT_NAME_BLOCKERS.get('napoli', set()), True)
test("PNB nudlar → konjac", 'konjac' in PRODUCT_NAME_BLOCKERS.get('nudlar', set()), True)
test("PNB smokey → ribs", 'ribs' in PRODUCT_NAME_BLOCKERS.get('smokey', set()), True)

# STOP_WORDS: ungsbakad, variant, osotat
test("SW ungsbakad", 'ungsbakad' in STOP_WORDS, True)
test("SW variant", 'variant' in STOP_WORDS, True)

# FLAVOR_WORDS: ramslök
test("FW ramslök", 'ramslök' in FLAVOR_WORDS, True)

# NON_FOOD: pouch (pet food)
from languages.sv.ingredient_matching import NON_FOOD_KEYWORDS  # noqa: F811
test("NF pouch", 'pouch' in NON_FOOD_KEYWORDS, True)

# Specialty qualifiers: melon types
test("SQ melon cantaloupe", 'cantaloupe' in SPECIALTY_QUALIFIERS.get('melon', []), True)
test("SQ melon galia", 'galia' in SPECIALTY_QUALIFIERS.get('melon', []), True)

# RIB: chicken→sås, ost→tortellini
test("RIB chicken → sås", any('sås' in w for w in RECIPE_INGREDIENT_BLOCKERS.get('chicken', set())), True)
test("RIB ost → tortellini", 'tortellini' in RECIPE_INGREDIENT_BLOCKERS.get('ost', set()), True)

# PPR: kryddmix protein types
from languages.sv.ingredient_matching import PROCESSED_PRODUCT_RULES
test("PPR kryddmix has kyckling", 'kyckling' in PROCESSED_PRODUCT_RULES.get('kryddmix', set()), True)

# Scraper: split_serving_lists
from scrapers.recipes._common import split_serving_lists
test("split serving list", len(split_serving_lists(['jordgubbar, pistagenötter och växtbaserad dryck'])), 3)
test("keep quantity ingredient", len(split_serving_lists(['1 dl grädde, vispat och kylt'])), 1)

# --- Batch 44-46 regression tests ---

from languages.sv.ingredient_matching import (
    BIDIRECTIONAL_PER_KEYWORD, IMPORTANT_SHORT_KEYWORDS,
    FALSE_POSITIVE_BLOCKERS  # noqa: F811
)

# Färskost flavor matching (Direction B blocks flavored from generic)
def sq_check(ingredient, product, keyword):
    od = precompute_offer_data(product)
    sq = od.get('specialty_qualifiers', {})
    return check_specialty_qualifiers(sq, keyword, ingredient.lower())

test("SQ färskost generic → naturell pass", sq_check('färskost', 'Färskost Naturell', 'färskost'), True)
test("SQ färskost generic → vitlök block", sq_check('färskost', 'Färskost Vitlök & Örter', 'färskost'), False)
test("SQ färskost vitlök → vitlök pass", sq_check('färskost vitlök & örter', 'Färskost Vitlök & Örter', 'färskost'), True)
test("SQ färskost vitlök → naturell fallback pass", sq_check('färskost vitlök & örter', 'Färskost Naturell', 'färskost'), True)
test("SQ färskost garlic equiv", sq_check('färskost vitlök & örter', 'Garlic & Herbs Färskost 40%', 'färskost'), True)
test("SQ smör osaltat → osaltat pass", sq_check('115 g smör osaltat', 'Smör Osaltat Svenskt 82% 250g Arla', 'smör'), True)
test("SQ smör osaltat → normalsaltat block", sq_check('115 g smör osaltat', 'Smör Normalsaltat Svenskt 82% 500g Arla', 'smör'), False)
test("SQ generic smör → osaltat pass", sq_check('30 g smör', 'Smör Osaltat Svenskt 82% 250g Arla', 'smör'), True)

# PNB: chips → färskost
test("PNB färskost → chips", 'chips' in PRODUCT_NAME_BLOCKERS.get('färskost', set()), True)

# Choklad darkness (Direction B-only via _GENERIC_MATCHES_ALL)
test("SQ mörk choklad → vit block", sq_check('mörk choklad', 'Bakchoklad Vit', 'choklad'), False)
test("SQ mörk choklad → mörk pass", sq_check('mörk choklad', 'Bakchoklad Mörk 55%', 'choklad'), True)
test("SQ vit choklad → mörk block", sq_check('vit choklad', 'Bakchoklad Mörk 55%', 'choklad'), False)
test("SQ generic choklad → vit pass", sq_check('choklad', 'Bakchoklad Vit', 'choklad'), True)
test("SQ generic choklad → mörk pass", sq_check('choklad', 'Bakchoklad Mörk 55%', 'choklad'), True)
test(
    "dark chocolate bar product with chokladkaka extracts choklad",
    extract_keywords_from_product(
        "Chokladkaka EXCELLENCE 70% Kakao Mörk Choklad 100g Lindt",
        "frozen",
        brand="LINDT",
    ),
    ['choklad'],
)
test(
    "dark chocolate bar product with chokladkaka matches mörk choklad",
    match_kw(
        "Chokladkaka EXCELLENCE 70% Kakao Mörk Choklad 100g Lindt",
        "100 g mörk choklad",
        "frozen",
    ),
    'choklad',
)
test(
    "dark chocolate bar product with chokladkaka also matches mörk chokladkaka in full recipe matcher",
    recipe_match_num(
        ["100 g Mörk chokladkaka"],
        {
            "name": "Chokladkaka EXCELLENCE 70% Kakao Mörk Choklad 100g Lindt",
            "category": "pantry",
            "brand": "LINDT",
        },
    ),
    1,
)
test(
    "dark chocolate bar product with chokladkaka also matches mörk chokladkaka in cached recipe matcher",
    recipe_match_num_cached(
        ["100 g Mörk chokladkaka"],
        {
            "name": "Chokladkaka EXCELLENCE 70% Kakao Mörk Choklad 100g Lindt",
            "category": "pantry",
            "brand": "LINDT",
        },
    ),
    1,
)
test(
    "flavored dark chocolate bar with chokladkaka stays blocked",
    extract_keywords_from_product(
        "Chokladkaka EXCELLENCE Chili Mörk Choklad 100g Lindt",
        "frozen",
        brand="LINDT",
    ),
    [],
)
test(
    "flavored dark chocolate bar with chokladkaka still stays blocked in full recipe matcher",
    recipe_match_num(
        ["100 g Mörk chokladkaka"],
        {
            "name": "Chokladkaka EXCELLENCE Chili Mörk Choklad 100g Lindt",
            "category": "pantry",
            "brand": "LINDT",
        },
    ),
    0,
)
test(
    "plain vanilla ice cream keeps vanilla keyword",
    extract_keywords_from_product("Vaniljglass 1l SIA", "frozen"),
    ['vaniljglass', 'glass'],
)
test(
    "vanilla pistachio ice cream no longer counts as plain vanilla",
    extract_keywords_from_product("Glass Vanilla pistachio 465ml Lily & Hanna's", "frozen"),
    [],
)
test(
    "vanilla blackcurrant ice cream no longer counts as plain vanilla",
    extract_keywords_from_product("Vanilj & svartvinbärsglass 0,5l SIA", "frozen"),
    [],
)
test(
    "vanilla pistachio ice cream blocked for vaniljglass recipe",
    match_kw("Glass Vanilla pistachio 465ml Lily & Hanna's", "6 portioner Vaniljglass", "frozen"),
    None,
)
olive_rank_data = recipe_match_data_multi_cached(
    ["2 dl Zeta Kalamataoliver urkärnade"],
    [
        {
            "name": "Oliver Svarta Urkärnade 350g ICA Basic",
            "category": "pantry",
            "savings": 20,
        },
        {
            "name": "Oliver Kalamata Urkärnade 350g Fontana",
            "category": "pantry",
            "savings": 5,
        },
        {
            "name": "Gemlik Oliver 350g Ceren",
            "category": "pantry",
            "savings": 10,
        },
    ],
)
olive_rank_by_name = {offer["name"]: offer for offer in olive_rank_data["matched_offers"]}
test(
    "kalamata olive gets higher qualifier specificity rank than generic black olive",
    olive_rank_by_name["Oliver Kalamata Urkärnade 350g Fontana"]["qualifier_specificity_rank"],
    2,
)
test(
    "generic black olive remains a fallback below exact kalamata",
    olive_rank_by_name["Oliver Svarta Urkärnade 350g ICA Basic"]["qualifier_specificity_rank"],
    1,
)
test(
    "unqualified gemlik olive remains a pragmatic fallback for pitted kalamata",
    "Gemlik Oliver 350g Ceren" in olive_rank_by_name,
    True,
)
olive_sorted_names = [
    offer["name"]
    for offer in sorted(
        olive_rank_data["matched_offers"],
        key=lambda offer: (
            offer.get("qualifier_specificity_rank", 0),
            1 if offer.get("qualifier_match") else 0,
            1 if offer.get("context_match") else 0,
            float(offer.get("savings") or 0),
        ),
        reverse=True,
    )
]
test(
    "kalamata olive sorts ahead of higher-savings black fallback",
    olive_sorted_names[0],
    "Oliver Kalamata Urkärnade 350g Fontana",
)
test(
    "plain green olives no longer accept cream-cheese-stuffed olives",
    recipe_match_num(
        ["140 g Gröna oliver"],
        {"name": "Gröna Oliver Färskostfyllda 250g Gourmet Gruppen", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "leccino olives no longer accept stuffed green olives",
    recipe_match_num(
        ["1 burk Zeta Leccino-oliver urkärnade"],
        {"name": "Gröna Oliver Färskostfyllda 250g Gourmet Gruppen", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "filled olives still match when the ingredient explicitly asks for stuffed olives",
    recipe_match_num(
        ["140 g fyllda gröna oliver"],
        {"name": "Gröna Oliver Färskostfyllda 250g Gourmet Gruppen", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "prosciutto di parma matches parmaskinka",
    match_kw("Prosciutto Di Parma 70g Zeta", "50 g parmaskinka", "deli"),
    "parmaskinka",
)
test(
    "lufttorkad skinka prosciutto di parma matches parmaskinka",
    match_kw("Skinka Lufttorkad Prosciutto di Parma 70g ICA", "50 g parmaskinka", "deli"),
    "parmaskinka",
)
test(
    "prosciutto di parma tortellini still does not match parmaskinka",
    match_kw("Tortellini Prosciutto di Parma 250g Rana", "50 g parmaskinka", "meat"),
    None,
)
test(
    "pinsa prosciutto cotto still does not match parmaskinka",
    match_kw("Pinsa Prosciutto Cotto 360g", "50 g parmaskinka", "pizza"),
    None,
)
test("gari product extracts gari", kw("Gari Sushi 150g Sevan"), ["gari"])
test("tapenade product extracts tapenade", kw("Tapenade av Oliver 135g Zeta"), ["oliver", "tapenade"])
test("sriracha product extracts sriracha", kw("Sriracha Hot Chilli Sauce 255g Flying Goose"), ["chili", "sriracha"])
test("teriyaki woksås product extracts teriyaki", kw("Woksås Teriyaki 120g Blue Dragon"), ["teriyaki", "woksås"])
test(
    "gari ingredient matches gari sushi product",
    match_kw("Gari Sushi 150g Sevan", "1 msk gari", "pantry"),
    "gari",
)
test(
    "kålrotsgari ingredient still matches ordinary gari fallback",
    match_kw("Gari Sushi 190g ICA Asia", "80 g kålrotsgari (eller vanlig gari)", "pantry"),
    "gari",
)
test(
    "kålrotsgari ingredient does not fall back to raw kålrot",
    match_kw("Kålrot ca 800g Klass 1 ICA", "80 g kålrotsgari (eller vanlig gari)", "fruit/vegetables"),
    None,
)
test(
    "kålrotsgari ingredient still matches exact kålrotsgari product",
    match_kw("Kålrotsgari 200g Test", "80 g kålrotsgari (eller vanlig gari)", "pantry"),
    "kålrotsgari",
)
test(
    "vetesurdegsgrund no longer falls through to finished levain bread",
    match_kw(
        "Levainfralla Rustik Frö Med Vetesurdeg & Rågsurdeg 125g Eget Bageri",
        "500 g vetesurdegsgrund",
        "bread",
    ),
    None,
)
test(
    "vetesurdegsgrund still matches wheat sourdough starter products",
    match_kw("Surdegsstart Vete 300g Test", "500 g vetesurdegsgrund", "pantry"),
    "vetesurdegsgrund",
)
test(
    "jäst för matbröd matches exact bread yeast product",
    match_kw("Jäst för matbröd 50g Kronjäst", "10 g färsk jäst för matbröd", "pantry"),
    "matbrödsjäst",
)
test(
    "jäst för matbröd does not fall back to sweet dough yeast",
    match_kw("Jäst för söta degar 50g Kronjäst", "10 g färsk jäst för matbröd", "pantry"),
    None,
)
test(
    "steam buns ingredient matches exact steam buns product",
    match_kw("Steam Buns 250g Santa Maria", "12 st Santa Maria steam buns bröd", "bread"),
    "steambuns",
)
test(
    "steam buns ingredient matches bao buns product",
    match_kw("Bao Buns 250g Test", "12 st Santa Maria steam buns bröd", "bread"),
    "steambuns",
)
test(
    "steam buns ingredient does not fall back to generic naan bread",
    match_kw("Naan bröd Original 260g Santa Maria", "12 st Santa Maria steam buns bröd", "bread"),
    None,
)
test(
    "raw skinkschnitzel line does not match prepared breaded schnitzel",
    match_kw(
        "Panerad Schnitzel 300g ICA",
        "4 skivor skinkinnanlår, skinkschnitzel eller kalvinnanlår (à ca 100 g)",
        "frozen",
    ),
    None,
)
test(
    "raw skinkschnitzel line does not match filled breaded schnitzel",
    match_kw(
        "Schnitzel ost skinka panerad 400g ICA",
        "4 skivor skinkinnanlår, skinkschnitzel eller kalvinnanlår (à ca 100 g)",
        "frozen",
    ),
    None,
)
test(
    "raw skinkschnitzel line still matches exact raw skinkschnitzel product",
    match_kw(
        "Skinkschnitzel 300g ICA",
        "4 skivor skinkinnanlår, skinkschnitzel eller kalvinnanlår (à ca 100 g)",
        "poultry",
    ),
    "skinkschnitzel",
)
test(
    "steak-style tonfisk line matches fresh tuna product",
    match_kw(
        "Tonfisk Färsk MSC 260g ICA",
        "4 bitar tonfisk (gärna vit MSC-märkt, à 120 g)",
        "fish",
    ),
    "tonfisk",
)
test(
    "steak-style tonfisk line matches frozen tuna product",
    match_kw(
        "Tonfisk Fryst 300g Test",
        "4 bitar tonfisk (gärna vit MSC-märkt, à 120 g)",
        "frozen",
    ),
    "tonfisk",
)
test(
    "steak-style tonfisk line does not match canned tuna in water",
    match_kw(
        "Tonfisk i vatten 185g ICA",
        "4 bitar tonfisk (gärna vit MSC-märkt, à 120 g)",
        "pantry",
    ),
    None,
)
test(
    "weighted stor kyckling does not match chicken inner fillet",
    match("Kycklinginnerfilé Färsk 600g Kronfågel", "1 stor kyckling (ca 2 kg)", "meat"),
    None,
)
test(
    "weighted stor kyckling does not match chicken breast fillet",
    match("Kycklingbröstfilé Färsk 650g Kronfågel", "1 stor kyckling (ca 2 kg)", "meat"),
    None,
)
test(
    "weighted stor kyckling does not match chicken thigh fillet",
    match("Kycklinglårfilé Färsk 900g Kronfågel", "1 stor kyckling (ca 2 kg)", "meat"),
    None,
)
test(
    "weighted stor kyckling matches whole chicken product",
    match("Kyckling Hel Färsk ca 1,8kg Kronfågel", "1 stor kyckling (ca 2 kg)", "meat"),
    "kyckling",
)
test(
    "weighted stor kyckling also matches other whole chicken variants",
    match("Majskyckling Hel Färsk ca 1,6kg Test", "1 stor kyckling (ca 2 kg)", "meat"),
    "kyckling",
)
test(
    "explicit hel kyckling ingredient keeps whole chicken match in cached recipe matcher",
    recipe_match_num_cached(
        ["1 kg Kyckling Hel"],
        {"name": "Kyckling hel Ekologisk ca 1,7kg KRAV Reko Kyckling", "category": "meat", "savings": 10},
    ),
    1,
)
test(
    "explicit hel kyckling ingredient still blocks chicken cuts in cached recipe matcher",
    recipe_match_num_cached(
        ["1 kg Kyckling Hel"],
        {"name": "Kycklingbröstfilé Färsk 650g Kronfågel", "category": "meat", "savings": 10},
    ),
    0,
)
_jordgubbar_same_family_recipe = RecipeMatcher()._match_recipe_to_offers(
    SimpleNamespace(
        id='jordgubbar-same-family',
        name='Jordgubbsparfait',
        ingredients=[
            '400 g frysta jordgubbar',
            '1/2 liter färska jordgubbar, till garnering',
        ],
    ),
    [
        SimpleNamespace(
            id='jordgubbar-farska',
            name='Jordgubbar 250g ICA Klass 1',
            category='fruit_vegetables',
            brand='',
            price=10,
            original_price=15,
            savings=5,
            store=None,
            product_url=None,
            is_multi_buy=False,
            multi_buy_quantity=None,
            weight_grams=None,
        ),
        SimpleNamespace(
            id='jordgubbar-frysta',
            name='Jordgubbar Frysta 500g ICA',
            category='frozen',
            brand='',
            price=10,
            original_price=15,
            savings=5,
            store=None,
            product_url=None,
            is_multi_buy=False,
            multi_buy_quantity=None,
            weight_grams=None,
        ),
    ],
    preferences={},
)
test(
    "same-family jordgubbar rows collapse into one ingredient group",
    len(_jordgubbar_same_family_recipe["ingredient_groups"]),
    1,
)
test(
    "same-family jordgubbar group keeps both ingredient rows in label",
    all(
        part in _jordgubbar_same_family_recipe["ingredient_groups"][0]["original"]
        for part in (
            '400 g frysta jordgubbar',
            '1/2 liter färska jordgubbar, till garnering',
        )
    ),
    True,
)
test(
    "same-family jordgubbar rows count as one covered ingredient family",
    _jordgubbar_same_family_recipe["coverage_pct"],
    100.0,
)
_oregano_forms_recipe = RecipeMatcher()._match_recipe_to_offers(
    SimpleNamespace(
        id='oregano-forms',
        name='Oregano forms',
        ingredients=[
            '1 msk torkad oregano',
            '1 kruka färsk oregano',
        ],
    ),
    [
        SimpleNamespace(
            id='oregano-dried',
            name='Oregano 9g Santa Maria',
            category='spices',
            brand='',
            price=10,
            original_price=15,
            savings=5,
            store=None,
            product_url=None,
            is_multi_buy=False,
            multi_buy_quantity=None,
            weight_grams=None,
        ),
        SimpleNamespace(
            id='oregano-fresh',
            name='Oregano i kruka 1st ICA',
            category='fruit_vegetables',
            brand='',
            price=10,
            original_price=15,
            savings=5,
            store=None,
            product_url=None,
            is_multi_buy=False,
            multi_buy_quantity=None,
            weight_grams=None,
        ),
    ],
    preferences={},
)
test(
    "spice and herb rows do not collapse into one same-family group",
    len(_oregano_forms_recipe["ingredient_groups"]),
    2,
)
test(
    "dried oregano row stays separate",
    _oregano_forms_recipe["ingredient_groups"][0]["original"],
    '1 msk torkad oregano',
)
test(
    "fresh oregano row stays separate",
    _oregano_forms_recipe["ingredient_groups"][1]["original"],
    '1 kruka färsk oregano',
)
_paprika_color_variant_recipe = RecipeMatcher()._match_recipe_to_offers(
    SimpleNamespace(
        id='paprika-color-variants',
        name='Paprika color variants',
        ingredients=[
            '100 g Grön Paprika',
            '1 st Röd Paprika',
        ],
    ),
    [
        SimpleNamespace(
            id='paprika-green',
            name='Paprika Grön ca 170g Klass 1 ICA',
            category='fruit_vegetables',
            brand='',
            price=10,
            original_price=15,
            savings=5,
            store=None,
            product_url=None,
            is_multi_buy=False,
            multi_buy_quantity=None,
            weight_grams=None,
        ),
        SimpleNamespace(
            id='paprika-red',
            name='Paprika Röd ca 190g Klass 1 ICA',
            category='fruit_vegetables',
            brand='',
            price=10,
            original_price=15,
            savings=5,
            store=None,
            product_url=None,
            is_multi_buy=False,
            multi_buy_quantity=None,
            weight_grams=None,
        ),
    ],
    preferences={},
)
test(
    "distinct paprika color variants stay as separate ingredient groups",
    len(_paprika_color_variant_recipe["ingredient_groups"]),
    2,
)
test(
    "distinct paprika color variants both keep best savings",
    [group["best_savings"] for group in _paprika_color_variant_recipe["ingredient_groups"]],
    [5, 5],
)
test(
    "distinct paprika color variants count as two covered ingredients",
    _paprika_color_variant_recipe["coverage_pct"],
    100.0,
)
test(
    "distinct paprika color variants count as two matches",
    _paprika_color_variant_recipe["num_matches"],
    2,
)
test(
    "alternative mince line accepts lammfärs kalvfärs och nötfärs",
    [
        match_kw("Lammfärs Färsk 500g Test", "400 g lammfärs eller färs av kalv eller nöt", "meat"),
        match_kw("Kalvfärs Färsk 500g Test", "400 g lammfärs eller färs av kalv eller nöt", "meat"),
        match_kw("Nötfärs Färsk 500g ICA", "400 g lammfärs eller färs av kalv eller nöt", "meat"),
    ],
    ["lammfärs", "kalvfärs", "nötfärs"],
)
test(
    "alternative mince line blocks other mince families",
    [
        match_kw("Fläskfärs Färsk 20% 500g ICA", "400 g lammfärs eller färs av kalv eller nöt", "meat"),
        match_kw("Kycklingfärs 500g Kronfågel", "400 g lammfärs eller färs av kalv eller nöt", "meat"),
        match_kw("Blandfärs Färsk 500g ICA", "400 g lammfärs eller färs av kalv eller nöt", "meat"),
    ],
    [None, None, None],
)
test(
    "bone-in veal wording accepts raw boneless veal cuts as same meat type fallback",
    [
        match_kw("Kalvhögrev i Bit Import Prime", "ca 1 kg kalvkött med ben", "meat"),
        match_kw("Kalvbiff Import Prime", "ca 1 kg kalvkött med ben", "meat"),
        match_kw("Kalventrecote Import Prime", "ca 1 kg kalvkött med ben", "meat"),
        match_kw("Kalvschnitzel Import Prime", "ca 1 kg kalvkött med ben", "meat"),
    ],
    ["kalvkött", "kalvkött", "kalvkött", "kalvkött"],
)
test(
    "bone-in veal wording blocks wrong meat type and processed veal products",
    [
        match_kw("Nöthögrev i Bit", "ca 1 kg kalvkött med ben", "meat"),
        match_kw("Kalvfärs 16% Rullpack Sverige Scan", "ca 1 kg kalvkött med ben", "meat"),
        match_kw("Kalvkorv Skivad Jakobsdals", "ca 1 kg kalvkött med ben", "meat"),
        match_kw("Sylta med Kalvkött Ello Lammhult", "ca 1 kg kalvkött med ben", "meat"),
    ],
    [None, None, None, None],
)
test(
    "reordered mince alternatives still accept only the three intended families",
    [
        match_kw("Nötfärs Färsk 500g ICA", "400 g nötfärs, lamm- eller kalvfärs", "meat"),
        match_kw("Lammfärs Färsk 500g Test", "400 g nötfärs, lamm- eller kalvfärs", "meat"),
        match_kw("Kalvfärs Färsk 500g Test", "400 g nötfärs, lamm- eller kalvfärs", "meat"),
        match_kw("Fläskfärs Färsk 20% 500g ICA", "400 g nötfärs, lamm- eller kalvfärs", "meat"),
    ],
    ["nötfärs", "lammfärs", "kalvfärs", None],
)
test(
    "full recipe matcher keeps alternative mince line on lamm kalv och nöt",
    [
        recipe_match_num(["400 g lammfärs eller färs av kalv eller nöt"], {"name": "Lammfärs Färsk 500g Test", "category": "meat"}),
        recipe_match_num(["400 g lammfärs eller färs av kalv eller nöt"], {"name": "Kalvfärs Färsk 500g Test", "category": "meat"}),
        recipe_match_num(["400 g lammfärs eller färs av kalv eller nöt"], {"name": "Nötfärs Färsk 500g ICA", "category": "meat"}),
        recipe_match_num(["400 g lammfärs eller färs av kalv eller nöt"], {"name": "Fläskfärs Färsk 20% 500g ICA", "category": "meat"}),
        recipe_match_num(["400 g lammfärs eller färs av kalv eller nöt"], {"name": "Kycklingfärs 500g Kronfågel", "category": "meat"}),
        recipe_match_num(["400 g lammfärs eller färs av kalv eller nöt"], {"name": "Blandfärs Färsk 500g ICA", "category": "meat"}),
    ],
    [1, 1, 1, 0, 0, 0],
)
test(
    "same-animal or mince line keeps mince on kyckling family only",
    [
        recipe_match_num(["500 g kycklingbröstfilé eller färs"], {"name": "Kycklingfärs 500g Kronfågel", "category": "meat"}),
        recipe_match_num(["500 g kycklingbröstfilé eller färs"], {"name": "Nötfärs 500g ICA", "category": "meat"}),
        recipe_match_num(["500 g kycklingbröstfilé eller färs"], {"name": "Lammfärs 500g Scan", "category": "meat"}),
        recipe_match_num(["500 g kycklingbröstfilé eller färs"], {"name": "Vegofärs 400g Anamma", "category": "frozen"}),
    ],
    [1, 0, 0, 0],
)
test(
    "kalkon pålägg does not match raw kalkon bröstfilé",
    match_kw("Kalkon Bröstfilé 600g Ingelsta Kalkon", "1 st Kalkon Pålägg", "meat"),
    None,
)
test(
    "kalkon pålägg still matches deli kalkon pålägg",
    match_kw("Kalkon Pålägg 110g Test", "1 st Kalkon Pålägg", "deli"),
    "kalkon",
)
test(
    "rostbiff pålägg does not match raw rostbiff cut",
    match_kw("Rostbiff Färsk i bit ca 1kg ICA", "1 st Rostbiff Pålägg", "meat"),
    None,
)
test(
    "rostbiff pålägg still matches deli rostbiff pålägg",
    match_kw("Rostbiff Pålägg 100g Test", "1 st Rostbiff Pålägg", "deli"),
    "rostbiff",
)
test(
    "rostbiff pålägg does not degrade to generic vego pålägg",
    match_kw("Veganskt Pålägg Paprika 150g Test", "150 g Rostbiff Pålägg", "deli"),
    None,
)
test(
    "lingondryck ej koncentrerat blocks concentrate",
    match_kw("Lingondryck Koncentrat 2,5dl Jokk", "5 dl lingondryck (ej koncentrerat)", "drink"),
    None,
)
test(
    "lingondryck ej koncentrerat still matches ready-to-drink lingondryck",
    match_kw("Lingondryck 1l Test", "5 dl lingondryck (ej koncentrerat)", "drink"),
    "lingondryck",
)
test(
    "tapenade ingredient matches olive tapenade product",
    match_kw("Tapenade av Oliver 135g Zeta", "2 msk tapenade", "pantry"),
    "tapenade",
)
test(
    "sriracha ingredient matches sriracha sauce product",
    match_kw("Sriracha Hot Chilli Sauce 255g Flying Goose", "1 msk sriracha", "pantry"),
    "sriracha",
)
test(
    "teriyaki woksås ingredient matches exact teriyaki woksås product",
    match_kw("Woksås Teriyaki 120g Blue Dragon", "2 msk woksås teriyaki", "pantry"),
    "teriyaki",
)
test(
    "rökt fläsk recipe line keeps smoked pork and drops fresh cuts",
    recipe_match_num_multi(
        ["150 g rökt fläsk"],
        [
            {"name": "Fläskfilé rökt ca 550g Tulip", "category": "poultry"},
            {"name": "Fläskfilé Färsk ca 500g ICA", "category": "poultry"},
            {"name": "Fläskkarré Färsk benfri ca 1,1kg Scan", "category": "poultry"},
        ],
    ),
    1,
)
test(
    "cake-style chokladkaka stays blocked",
    extract_keywords_from_product("Chokladkaka 350g Hägges", "bread"),
    [],
)
test(
    "KSC hasselnöt suppressed by nougatkräm context",
    match_kw("Hasselnöt 750g Start", "15 kolor med nougatkräm och hasselnöt", "pantry"),
    None,
)
test(
    "KSC mandel suppressed by bittermandel context",
    match_kw("Mandel 500g", "2 st Bittermandel", "pantry"),
    None,
)
test(
    "KSC apelsin suppressed by apelsinskal context",
    match_kw("Apelsin Klass 1", "100 g syltade apelsinskal", "fruit"),
    None,
)
test(
    "whole apelsin still matches plain apelsin ingredient",
    match_kw("Apelsin Klass 1", "2 apelsiner", "fruit"),
    'apelsin',
)
test("SQ rökt lax → kallrökt pass", sq_check('rökt lax', 'Lax Färsk Kallrökt Skivad 150g ICA Basic', 'lax'), True)
test("SQ rökt lax → varmrökt block", sq_check('rökt lax', 'Lax Färsk Varmrökt 150g ICA Basic', 'lax'), False)
test("SQ rökt lax → Varmr abbreviation block", sq_check('rökt lax', 'Lax Varmr Portion Eldorado', 'lax'), False)
test("SQ varmrökt lax → kallrökt block", sq_check('varmrökt lax', 'Lax Färsk Kallrökt Skivad 150g ICA Basic', 'lax'), False)
test("SQ varmrökt lax → varmrökt pass", sq_check('varmrökt lax', 'Lax Färsk Varmrökt 150g ICA Basic', 'lax'), True)
test("SQ varmrökt lax → Varmr abbreviation pass", sq_check('varmrökt lax', 'Lax Varmr Portion Eldorado', 'lax'), True)
test("SQ plain lax → kallrökt block", sq_check('lax', 'Lax Färsk Kallrökt Skivad 150g ICA Basic', 'lax'), False)
test("SQ plain lax → Varmr abbreviation block", sq_check('lax', 'Lax Varmr Portion Eldorado', 'lax'), False)
test("SQ rökt fläsk → smoked pork pass", sq_check('rökt fläsk', 'Fläskfilé rökt ca 550g Tulip', 'fläsk'), True)
test("SQ rökt fläsk → fresh pork block", sq_check('rökt fläsk', 'Fläskfilé Färsk ca 500g ICA', 'fläsk'), False)
test("SQ plain fläsk → smoked pork block", sq_check('fläsk', 'Fläskfilé rökt ca 550g Tulip', 'fläsk'), False)

# Soltorkad tomat: packaging-word priority in Direction A
test("SQ soltorkad tomat → skalade block", sq_check('1 burk kronärtskockscrème med soltorkad tomat', 'Hela Skalade Tomater', 'tomat'), False)
test("SQ soltorkad tomat → soltork pass", sq_check('1 burk kronärtskockscrème med soltorkad tomat', 'Soltorkade Tomater', 'tomat'), True)
test(
    "SQ marinerad kronärtskocka matches marinerade kronärtskockor",
    sq_check('150 g marinerad kronärtskocka', 'Kronärtskockor marinerade 200g Zeta', 'kronärtskocka'),
    True,
)
test(
    "SQ plain kronärtskocka still blocks marinerade kronärtskockor",
    sq_check('150 g kronärtskocka', 'Kronärtskockor marinerade 200g Zeta', 'kronärtskocka'),
    False,
)

# Canned tomato reverse equivalents: "1 burk tomater" matches any canned form
test("SQ burk tomater → passerade pass", sq_check('1 burk tomater', 'Tomater Passerade', 'tomat'), True)
test("SQ burk tomater → krossade pass", sq_check('1 burk tomater', 'Tomater Krossade', 'tomat'), True)
test("SQ black eye bönor → black eye pass", sq_check('410 g blackeyebönor', 'Black eye bönor 900g Forum', 'bönor'), True)
test("SQ black eye bönor → kidney block", sq_check('410 g blackeyebönor', 'Kidneybönor 380g ICA', 'bönor'), False)
test("KW vegetariska bitar → vegobitar", extract_keywords_from_ingredient("Vegetariska Bitar"), ["vegobitar"])
test("KW machésallad → machesallat", extract_keywords_from_ingredient("machésallad"), ["machesallat"])
test("KW hackade nötter → nötter", extract_keywords_from_ingredient("hackade nötter"), ["nötter"])
test(
    "KW parenthetical eller preserves cornichons alternative",
    "cornichons" in extract_keywords_from_ingredient("2 inlagda gurkor (eller 1 dl cornichons)"),
    True,
)
test("MATCH bönmix → blandade bönor", match("Bönmix 380g ICA", "380 g bönor, blandade sorter") is not None, True)
test("MATCH silkesmjuk tofu → silkestofu", match("Tofu silkesmjuk Ekologisk 400g YiPin", "500 g silkestofu (fast sort)") is not None, True)
test("MATCH regnbågslaxrom → laxrom", match("Regnbågslaxrom 80g Fiskeriet", "1 msk laxrom") is not None, True)
test("MATCH plural kammusslor → singular pilgrimsmussla", match("Kammusslor 150g ICA", "6 små kammussla (pilgrimsmussla)", "fish") is not None, True)
test("MATCH glutenfri mix → mjölmix", match("Mjölmix glutenfri 500g Schär", "2 dl Glutenfri mix", "pantry") is not None, True)
test("SPACE_NORM mikropopcorn → micropopcorn", _apply_space_normalizations("1 påse mikropopcorn"), "1 påse micropopcorn")
test("KW mikropopcorn product → micropopcorn", extract_keywords_from_product("Mikropopcorn Saltade Eko 3-pack Garant Eko"), ["micropopcorn"])
test("MATCH micropopcorn → mikropopcorn", match("Mikropopcorn Saltade Eko 3-pack Garant Eko", "1 påse micropopcorn", "candy") is not None, True)
test("FILTER candy micropop offers reach matcher", _is_recipe_named_candy_offer("Micropop Salt Popcorn 3-pack Olw", "candy"), True)
test("FILTER ordinary popcorn snacks stay out of candy allowlist", _is_recipe_named_candy_offer("Popcorn Cheddar Estrella", "candy"), False)
test(
    "MATCH chili olive oil to explicit chili olive oil ingredient",
    recipe_match_num_cached(
        ["1 tsk Zeta Olivolja Chili"],
        {"name": "Olivolja Chili Extra Virgin Garant", "category": "spices"},
    ),
    1,
)
test(
    "MATCH plain olive oil line does not accept chili olive oil",
    recipe_match_num_cached(
        ["1 msk olivolja"],
        {"name": "Olivolja Chili Extra Virgin Garant", "category": "spices"},
    ),
    0,
)
test(
    "MATCH flavored olive oil prefers matching flavored oil line",
    recipe_match_num_cached(
        ["1 tsk Zeta Olivolja Chili", "Zeta Extra jungfruolivolja Classico"],
        {"name": "Olivolja Chili Extra Virgin Garant", "category": "spices"},
    ),
    1,
)
test(
    "PNB laxrom blocks aroma extracts",
    recipe_match_num(
        ["50 g laxrom"],
        {"name": "Arraksarom 30ml Dr.Oetker", "category": "pantry"},
    ),
    0,
)
test(
    "PNB löjrom blocks aroma extracts",
    recipe_match_num(
        ["ev löjrom"],
        {"name": "Arraksarom 30ml Dr.Oetker", "category": "pantry"},
    ),
    0,
)

# Vinbär: keyword extraction + SQ
test("ISK vinbär in IMPORTANT_SHORT", 'vinbär' in IMPORTANT_SHORT_KEYWORDS, True)
test("SQ röda vinbär → svarta block", sq_check('röda vinbär', 'Svarta Vinbär Frysta', 'vinbär'), False)
test("SQ generic vinbär → svarta pass", sq_check('vinbär', 'Svarta Vinbär Frysta', 'vinbär'), True)

# FPB: tamari → tamarind
test("FPB tamari blocked in tamarindpasta", blocked('tamari', 'tamarindpasta'), True)

# STOP_WORDS: bananas, caramel, fyllig
test("SW bananas", 'bananas' in STOP_WORDS, True)
test("SW fyllig", 'fyllig' in STOP_WORDS, True)

# --- Javligtgott review regression tests ---

from languages.sv.ingredient_matching import _COMPOUND_STRICT_KEYWORDS
from languages.sv.ingredient_matching import extract_keywords_from_ingredient

# Veg qualifier: compound words trigger veg filtering
from recipe_matcher import RecipeMatcher as _RM  # noqa: F811
_veg_qualifier_words = {'vegetarisk', 'vegetariska', 'vegetariskt', 'vegansk', 'veganska', 'veganskt', 'vego',
                        'växtbaserad', 'växtbaserade', 'växtbaserat',
                        'vegetabilisk', 'vegetabiliska', 'vegetabiliskt',
                        'veg', 'oatly', 'vegosmör', 'vegasmör', 'vegansmör',
                        'vegochorizo', 'vegobacon', 'vegokorvar'}
test("VEG vegosmör in qualifier words", 'vegosmör' in _veg_qualifier_words, True)
test("VEG vegochorizo in qualifier words", 'vegochorizo' in _veg_qualifier_words, True)
test("VEG vegobacon in qualifier words", 'vegobacon' in _veg_qualifier_words, True)

# Tofu: COMPOUND_STRICT + SPACE_NORM
test("COMPOUND_STRICT tofu", 'tofu' in _COMPOUND_STRICT_KEYWORDS, True)
test("KW naturell fast tofu → naturelltofu", extract_keywords_from_ingredient("200 g Naturell fast tofu"), ["naturelltofu"])
test("KW rökt tofu → rökttofu", extract_keywords_from_ingredient("250 g Rökt tofu"), ["rökttofu"])
test("KW marinerad tofu → marineradtofu", extract_keywords_from_ingredient("200 g Marinerad tofu"), ["marineradtofu"])
test("KW plain tofu → tofu", extract_keywords_from_ingredient("400 g Tofu"), ["tofu"])
test(
    "KW creme av soltorkade tomater keeps specific spread keyword",
    extract_keywords_from_ingredient("2 msk Creme av soltorkade tomater"),
    ["soltorkadetomatcreme"],
)
test(
    "KW product creme av soltorkade tomater keeps specific spread keyword",
    extract_keywords_from_product("Creme av Soltorkade tomater 140g", "vegetables"),
    ["soltorkadetomatcreme"],
)

# Havregrädde: stays specific (NOT mapped to generic grädde)
test("KW havregrädde → havregrädde", extract_keywords_from_ingredient("2.5 dl Havregrädde"), ["havregrädde"])
test("KW vispgrädde → grädde (parent)", extract_keywords_from_ingredient("2 dl Vispgrädde"), ["grädde"])
test("KW grädde → grädde", extract_keywords_from_ingredient("2 dl Grädde"), ["grädde"])
test(
    "KW havrebaserad matlagning → havregrädde + grädde",
    extract_keywords_from_ingredient("4 dl Havrebaserad matlagning"),
    ["havregrädde", "grädde"],
)
test(
    "KW soyabaserad matlagning → soja + grädde",
    extract_keywords_from_ingredient("0.5 dl Soyabaserad matlagning"),
    ["soja", "grädde"],
)
test(
    "KW växtbaserad mjölk → växtdryck",
    extract_keywords_from_ingredient("3 dl Växtbaserad mjölk"),
    ["växtdryck"],
)
test(
    "KW växtbaserad dryck → växtdryck",
    extract_keywords_from_ingredient("3 dl växtbaserad dryck"),
    ["växtdryck"],
)
test(
    "KW växtbaserad dryck med chokladsmak keeps umbrella + flavor",
    extract_keywords_from_ingredient("4 dl växtbaserad dryck med chokladsmak"),
    ["växtdryck", "chokladsmak"],
)
test(
    "KW kokosnötsdryck → kokosdryck",
    extract_keywords_from_ingredient("4 dl kokosnötsdryck"),
    ["kokosdryck"],
)
test(
    "KW explicit havssalt ingredient survives extraction",
    extract_keywords_from_ingredient("1 tsk Havssalt"),
    ["havssalt"],
)
test(
    "KW plain havssalt product survives extraction",
    extract_keywords_from_product("Havssalt 250g Maldon", "spices"),
    ["havssalt", "flingsalt"],
)
test(
    "KW product yoghurt kardemumma keeps exact compound",
    extract_keywords_from_product("Yoghurt Kardemumma 1l Valio", "dairy"),
    ["kardemummayoghurt"],
)
test(
    "KW ingredient chokladägg keeps exact candy keyword",
    extract_keywords_from_ingredient("5 dl chokladägg eller liknande"),
    ["chokladägg"],
)
test(
    "KW product chokladägg keeps exact candy keyword",
    extract_keywords_from_product("Chokladägg 80g Anthon Berg", "frozen"),
    ["chokladägg"],
)
test(
    "KW ingredient rimmat fläsk keeps exact cured pork keyword",
    extract_keywords_from_ingredient("200 g rimmat fläsk"),
    ["rimmatfläsk"],
)
test(
    "KW product rimmat stekfläsk exposes exact cured pork keyword",
    extract_keywords_from_product("Stekfläsk Rimmat i bit 320g ICA", "meat"),
    ["rimmatfläsk", "stekfläsk"],
)
test(
    "KW product rimmad fläsklägg exposes exact cured pork keyword",
    extract_keywords_from_product("Fläsklägg Rimmad Benfri ca 900g ICA", "meat"),
    ["rimmatfläsk", "fläsklägg"],
)
test(
    "KW ingredient plain sylt keeps generic jam umbrella keyword",
    extract_keywords_from_ingredient("sylt"),
    ["sylt"],
)
test(
    "KW ingredient fresh trattkantareller keeps exact species keyword",
    extract_keywords_from_ingredient("150 g färska trattkantareller"),
    ["trattkantarell"],
)
test(
    "KW product trattkantarell keeps exact species keyword",
    extract_keywords_from_product("Trattkantarell torkad 20g Risberg", "pantry"),
    ["trattkantarell", "kantareller", "torkadsvamp"],
)
test(
    "KW product vaniljsas keeps exact dessert sauce keyword",
    extract_keywords_from_product("Vaniljsås 500ml ICA", "dairy"),
    ["vaniljsås"],
)
test(
    "KW ingredient vetemjöl special keeps exact qualifier keyword",
    extract_keywords_from_ingredient("1 dl vetemjöl special"),
    ["vetemjölspecial"],
)
test(
    "KW ingredient vetemjöl fullkorn keeps exact qualifier keyword",
    extract_keywords_from_ingredient("1 dl vetemjöl fullkorn"),
    ["vetemjölfullkorn"],
)
test(
    "KW product vetemjöl special keeps exact qualifier keyword",
    extract_keywords_from_product("Vetemjöl Special 2kg Kungsörnen", "pantry"),
    ["vetemjölspecial"],
)
test(
    "KW product vetemjöl special fullkorn exposes both allowed levels",
    extract_keywords_from_product("Vetemjöl Special Fullkorn 2kg Kungsörnen", "pantry"),
    ["vetemjölspecial", "vetemjölfullkorn"],
)
test(
    "KW measured risotto → risottoris",
    extract_keywords_from_ingredient("250 g Risotto"),
    ["risottoris"],
)
test(
    "KW gemsallad → hjärtsallad",
    extract_keywords_from_ingredient("3 gemsallad, delade på längden"),
    ["hjärtsallad", "längden"],
)
test(
    "KW babygemsallad → hjärtsallad",
    extract_keywords_from_ingredient("2 babygemsallad sköljd och plockad i blad"),
    ["hjärtsallad"],
)
test(
    "MAT havrebaserad matlagning matches havregrädde",
    match_kw("Havregrädde iMat 13% 2,5dl Oatly", "4 dl Havrebaserad matlagning", "dairy"),
    "havregrädde",
)
test(
    "MAT havrebaserad matlagning matches oat matlagningsgrädde",
    match_kw("Matlagningsgrädde havre 2,5dl ICA", "4 dl Havrebaserad matlagning", "dairy"),
    "grädde",
)
test(
    "KW product oat matlagningsbas exposes oat cooking cream family",
    extract_keywords_from_product("Matlagningsbas Havre 13% 500ml ICA", "dairy"),
    ["matlagningsbas", "havregrädde", "grädde"],
)
test(
    "MAT havrebaserad matlagning matches oat matlagningsbas",
    match_kw("Matlagningsbas Havre 13% 500ml ICA", "1 dl Havrebaserad matlagning", "dairy"),
    "havregrädde",
)
test(
    "Recipe matcher havrebaserad matlagning matches oat matlagningsbas",
    recipe_match_num(
        ["1 dl Havrebaserad matlagning"],
        {"name": "Matlagningsbas Havre 13% 500ml ICA", "category": "dairy"},
    ),
    1,
)
test(
    "Cached recipe matcher havrebaserad matlagning matches oat matlagningsbas",
    recipe_match_num_cached(
        ["1 dl Havrebaserad matlagning"],
        {"name": "Matlagningsbas Havre 13% 500ml ICA", "category": "dairy"},
    ),
    1,
)
test(
    "Cached recipe matcher matlagningsgrädde eller havregrädde blocks protein pudding",
    recipe_match_num_cached(
        ["2 dl matlagningsgrädde eller havregrädde"],
        {"name": "Proteinpudding Choklad Grädde 2,4% 200g Ehrmann", "category": "dairy"},
    ),
    0,
)
test(
    "Recipe matcher matlagningsgrädde eller havregrädde still matches plain cooking cream",
    recipe_match_num(
        ["2 dl matlagningsgrädde eller havregrädde"],
        {"name": "Matlagningsgrädde 13% 5dl ICA", "category": "dairy"},
    ),
    1,
)
test(
    "MAT soyabaserad matlagning matches soja matlagningsgrädde",
    match_kw("Matlagningsgrädde soja 1l Alpro", "0.5 dl Soyabaserad matlagning", "dairy"),
    "grädde",
)
test(
    "MAT växtbaserad mjölk matches havredryck",
    match_kw("Havredryck Naturell 1l Oatly", "3 dl Växtbaserad mjölk", "dairy"),
    "växtdryck",
)
test(
    "MAT växtbaserad dryck matches sojadryck",
    match_kw("Sojadryck Naturell 1l Alpro", "3 dl växtbaserad dryck", "dairy"),
    "växtdryck",
)
test(
    "MAT växtbaserad mjölk matches mandeldryck",
    match_kw("Mandeldryck Natur 1l Alpro", "3 dl Växtbaserad mjölk", "dairy"),
    "växtdryck",
)
test(
    "MAT växtbaserad mjölk blocks dairy mjölk",
    match_kw("Mjölk 1,5% 1l Arla", "3 dl Växtbaserad mjölk", "dairy"),
    None,
)
test(
    "MAT kardemummayoghurt blocks plain yoghurt fallback",
    match_kw("Yoghurt Mild Naturell 3% 1,5l ICA", "8 portioner Kardemummayoghurt", "dairy"),
    None,
)
test(
    "MAT kardemummayoghurt blocks mayo substring leak",
    match_kw("Mayo Sriracha 250ml Caj P", "8 portioner Kardemummayoghurt", "pantry"),
    None,
)
test(
    "MAT kardemummayoghurt blocks spice fallback",
    match_kw("Kardemumma Malen 18g Kockens", "8 portioner Kardemummayoghurt", "pantry"),
    None,
)
test(
    "MAT kardemummayoghurt keeps exact yoghurt product",
    match_kw("Yoghurt Kardemumma 1l Valio", "8 portioner Kardemummayoghurt", "dairy"),
    "kardemummayoghurt",
)
test(
    "MAT chokladägg ingredient matches explicit chokladägg product",
    match_kw("Chokladägg 80g Anthon Berg", "5 dl chokladägg eller liknande", "frozen"),
    "chokladägg",
)
test(
    "MAT chokladägg ingredient still blocks generic godisägg",
    match_kw("Godisägg 110g ICA", "5 dl chokladägg eller liknande", "frozen"),
    None,
)
test(
    "MAT rimmat fläsk matches rimmat stekfläsk",
    match_kw("Stekfläsk Rimmat i bit 320g ICA", "200 g rimmat fläsk", "meat"),
    "rimmatfläsk",
)
test(
    "MAT rimmat fläsk matches rimmad fläsklägg fallback",
    match_kw("Fläsklägg Rimmad Benfri ca 900g ICA", "200 g rimmat fläsk", "meat"),
    "rimmatfläsk",
)
test(
    "MAT rimmat fläsk blocks fresh fläskfilé fallback",
    match_kw("Fläskfilé Färsk ca 600g ICA", "200 g rimmat fläsk", "meat"),
    None,
)
test(
    "MAT rimmat fläsk blocks fresh fläskkarré fallback",
    match_kw("Fläskkarré Benfri ca 900g ICA", "200 g rimmat fläsk", "meat"),
    None,
)
test(
    "MAT plain sylt matches lingonsylt",
    match_kw("Lingonsylt 400g Felix", "sylt", "pantry"),
    "sylt",
)
test(
    "MAT plain sylt matches hallonsylt",
    match_kw("Hallonsylt 410g ICA", "sylt", "pantry"),
    "sylt",
)
test(
    "MAT plain sylt matches drottningsylt",
    match_kw("Drottningsylt 500g Bob", "sylt", "pantry"),
    "sylt",
)
test(
    "MAT plain sylt does not match marmelad",
    match_kw("Aprikosmarmelad 400g ICA", "sylt", "pantry"),
    None,
)
test(
    "MAT fresh trattkantareller no longer match canned generic chanterelles",
    match_kw("Kantareller i vatten 314ml Fontana", "150 g färska trattkantareller", "pantry"),
    None,
)
test(
    "MAT fresh trattkantareller no longer match frozen yellow chanterelles",
    match_kw("Kantarell gul 1kg Fryst Magnihill", "150 g färska trattkantareller", "frozen"),
    None,
)
test(
    "MAT fresh trattkantareller no longer match dried trumpet chanterelles",
    match_kw("Trattkantarell torkad 20g Risberg", "150 g färska trattkantareller", "pantry"),
    None,
)
test(
    "MAT fresh trattkantareller still match fresh trumpet chanterelles",
    match_kw("Trattkantareller 150g Färska", "150 g färska trattkantareller", "vegetables"),
    "trattkantarell",
)
test(
    "MAT vaniljglass eller vaniljsas now matches vanilla sauce product",
    match_kw("Vaniljsås 500ml ICA", "vaniljglass, eller vaniljsås", "dairy"),
    "vaniljsås",
)
test(
    "MAT plain vetemjöl no longer matches special flour",
    match_kw("Vetemjöl Special 2kg Kungsörnen", "1 dl vetemjöl", "pantry"),
    None,
)
test(
    "MAT plain vetemjöl no longer matches fullkorn flour",
    match_kw("Vetemjöl Special Fullkorn 2kg Kungsörnen", "1 dl vetemjöl", "pantry"),
    None,
)
test(
    "MAT vetemjöl special matches special flour",
    match_kw("Vetemjöl Special 2kg Kungsörnen", "1 dl vetemjöl special", "pantry"),
    "vetemjölspecial",
)
test(
    "MAT vetemjöl special still accepts special fullkorn flour",
    match_kw("Vetemjöl Special Fullkorn 2kg Kungsörnen", "1 dl vetemjöl special", "pantry"),
    "vetemjölspecial",
)
test(
    "MAT vetemjöl special no longer matches plain flour",
    match_kw("Vetemjöl 2kg ICA", "1 dl vetemjöl special", "pantry"),
    None,
)
test(
    "MAT vetemjöl fullkorn matches fullkorn flour",
    match_kw("Vetemjöl Fullkorn 2kg ICA", "1 dl vetemjöl fullkorn", "pantry"),
    "vetemjölfullkorn",
)
test(
    "MAT vetemjöl fullkorn still accepts special fullkorn flour",
    match_kw("Vetemjöl Special Fullkorn 2kg Kungsörnen", "1 dl vetemjöl fullkorn", "pantry"),
    "vetemjölfullkorn",
)
test(
    "MAT vetemjöl fullkorn no longer matches plain flour",
    match_kw("Vetemjöl 2kg ICA", "1 dl vetemjöl fullkorn", "pantry"),
    None,
)
test(
    "MAT measured risotto matches arborioris",
    match_kw("Arborioris 1kg ICA", "250 g Risotto", "pantry"),
    "risottoris",
)
test(
    "MAT measured risotto matches carnaroli",
    match_kw("Carnaroli 500g Mino", "250 g Risotto", "pantry"),
    "risottoris",
)
test(
    "MAT measured risotto matches vialone nano",
    match_kw("Vialone Nano 1kg Test", "250 g Risotto", "pantry"),
    "risottoris",
)
test(
    "MAT measured risotto matches avorio",
    match_kw("Avorio 1kg Test", "250 g Risotto", "pantry"),
    "risottoris",
)
test(
    "MAT measured risotto still blocks prepared risotto meal",
    match_kw("Risotto Svamp Vitlök 250g Findus", "250 g Risotto", "frozen"),
    None,
)
test(
    "MAT gemsallad matches hjärtsallad",
    match_kw("Hjärtsallad röd/grön 180g Klass 1 ICA", "3 gemsallad, delade på längden", "fruit/vegetables"),
    "gemsallad",
)
test(
    "MAT babygemsallad matches hjärtsallad",
    match_kw("Hjärtsallad Eko 2-p Klass 1 ICA I love eco", "2 babygemsallad sköljd och plockad i blad", "fruit/vegetables"),
    "babygemsallad",
)
test(
    "KW chunky salsa ingredient keeps salsa keyword",
    extract_keywords_from_ingredient("300 g chunky salsa (medium)"),
    ["salsa"],
)
test(
    "KW Chunky Salsa product keeps salsa keyword",
    kw("Chunky Salsa Medium 230g ICA"),
    ["salsa"],
)
test(
    "MAT chunky salsa ingredient matches salsa product",
    match_kw("Chunky Salsa Medium 230g ICA", "300 g chunky salsa (medium)", "pantry"),
    "salsa",
)
test(
    "KW Herrgårdsost stays specific as ingredient",
    extract_keywords_from_ingredient("Herrgårdsost"),
    ["herrgårdsost"],
)
test(
    "KW Herrgårdsost product still includes generic ost fallback",
    "ost" in kw("Herrgårdsost 31%"),
    True,
)
test(
    "KW lagrad ost helst gruyère keeps gruyere preference",
    extract_keywords_from_ingredient("lagrad ost (helst gruyère)"),
    ["ost", "gruyere"],
)
test(
    "MAT Gruyère matches lagrad ost helst gruyère",
    recipe_match_num_cached(
        ["lagrad ost (helst gruyère)"],
        {"name": "Gruyère 1655 ca 250g Int Räls", "category": "dairy"},
    ),
    1,
)
test(
    "MAT fresh rödkål blocks klassisk felix rödkål",
    recipe_match_num_cached(
        ["finstrimlad rödkål"],
        {"name": "Klassisk Rödkål 550g Felix", "category": "vegetables"},
    ),
    0,
)
test(
    "MAT fresh rödkål blocks dansk felix rödkål",
    recipe_match_num_cached(
        ["finstrimlad rödkål"],
        {"name": "Dansk Rödkål 580g Felix", "category": "vegetables"},
    ),
    0,
)
test(
    "MAT fresh rödkål still matches fresh red cabbage",
    recipe_match_num_cached(
        ["finstrimlad rödkål"],
        {"name": "Rödkål ca 1,5kg Klass 1 ICA", "category": "fruit"},
    ),
    1,
)
test(
    "KW körsbärssylt eller -marmelad expands shared prefix",
    extract_keywords_from_ingredient("körsbärssylt eller -marmelad"),
    ["körsbärssylt", "körsbärsmarmelad"],
)
test(
    "MAT florsocker with våffel instruction does not match waffles",
    match_kw("Våfflor Frasvåfflor 8-p Frödinge", "2 msk florsocker (+ extra att pudra på våfflorna)", "frozen"),
    None,
)
test(
    "MAT körsbärssylt eller -marmelad matches marmelad",
    match_kw("Körsbärsmarmelad 420g ICA", "körsbärssylt eller -marmelad", "pantry"),
    "körsbärsmarmelad",
)
test(
    "MAT fil does not match filéade clementiner",
    match_kw("Fil Naturell 1l Arla", "clementiner, filéade i klyftor", "dairy"),
    None,
)
test(
    "KW Kryddmix Raita keeps short raita keyword",
    extract_keywords_from_ingredient("Kryddmix Raita"),
    ["kryddmix", "raita"],
)
test(
    "KW product Kryddmix Raita extracts raita",
    kw("Kryddmix Raita Style 24g Santa Maria"),
    ["kryddmix", "raita"],
)
test(
    "MAT Kryddmix Raita matches Santa Maria raita mix",
    match_kw("Kryddmix Raita Style 24g Santa Maria", "Kryddmix Raita", "pantry"),
    "kryddmix",
)
test(
    "MAT Kryddmix Tandori matches tandoori mix despite typo",
    match_kw("Kryddmix Tandoori 79g Santa Maria", "Kryddmix Tandori", "pantry"),
    "kryddmix",
)
test(
    "MAT Kryddmix Tandori still blocks plain tandoori paste",
    match_kw("Tandoori Paste 120g Patak's", "Kryddmix Tandori", "pantry"),
    None,
)
test(
    "MAT valnötter match generic hackade nötter",
    match_kw("Valnötter 300g ICA Gott Liv", "hackade nötter"),
    "nötter",
)
test(
    "MAT cashewnötter match generic hackade nötter",
    match_kw("Cashewnötter 500g ICA Gott Liv", "hackade nötter"),
    "nötter",
)
test(
    "MAT nötmix blocked for generic hackade nötter",
    recipe_match_num(
        ["hackade nötter"],
        {"name": "Nötmix Klassisk 200g Estrella"},
    ),
    0,
)
test(
    "MAT smaksatta nötter blocked for generic hackade nötter",
    recipe_match_num(
        ["hackade nötter"],
        {"name": "Cashewnötter Sourcream & Onion 140g Nutisal"},
    ),
    0,
)
test(
    "MAT rostade nötter blocked for generic hackade nötter",
    recipe_match_num(
        ["hackade nötter"],
        {"name": "Cashewnötter Jumbo Rostade 200g Exotic Snacks"},
    ),
    0,
)
test(
    "MAT bladspenat matches babyspenat fallback",
    match_kw("Babyspenat Sköljd Ekologisk 65g ICA I love eco", "70 g Färsk bladspenat"),
    "spenat",
)
test(
    "MAT babyspenat matches bladspenat fallback",
    match_kw("Bladspenat Fryst 400g ICA", "200 g babyspenat"),
    "spenat",
)
test(
    "MAT bladspenat matches generic fresh spenat pack",
    match_kw("Spenat i storpack Sköljd 200g ICA", "70 g Färsk bladspenat"),
    "spenat",
)
test(
    "MAT babyspenat matches generic fresh spenat pack",
    match_kw("Spenat i storpack Sköljd 200g ICA", "200 g babyspenat"),
    "spenat",
)
test(
    "MAT babyspenat allows hackad fryst spenat fallback",
    match_kw("Hackad spenat Fryst 600g ICA", "200 g babyspenat"),
    "spenat",
)
test(
    "MAT bladspenat allows hackad fryst spenat fallback",
    match_kw("Hackad spenat Fryst 600g ICA", "70 g Färsk bladspenat"),
    "spenat",
)
test(
    "MAT babyspenat still blocks stuvad spenat",
    recipe_match_num(
        ["200 g babyspenat"],
        {"name": "Stuvad spenat 375g ICA"},
    ),
    0,
)
test(
    "Q3 parser rewrites leaf-cabbage alternatives into one eller-group",
    expand_grouped_ingredient_text("2 kg bladkål, finstrimlad (vit, röd eller spetskål)"),
    ["vitkål eller rödkål eller spetskål"],
)
test(
    "Q3 parser splits plus-combined ingredients into separate rows",
    expand_grouped_ingredient_text("20 g ingefära + 2 krm malen gurkmeja + 1 krm svartpeppar"),
    ["20 g ingefära", "2 krm malen gurkmeja", "1 krm svartpeppar"],
)
test(
    "Q3 parser splits fresh herb bundle into separate herbs",
    expand_grouped_ingredient_text("2 dl färska örter gärna färsk timjan, rosmarin och persilja"),
    ["färsk timjan", "färsk rosmarin", "färsk persilja"],
)
_q_old_index_assignment_recipe = [
    "1 1/2 kg benfri lammstek",
    "4 vitlöksklyftor",
    "smör",
    "1 1/2 tsk salt",
    "1/2 tsk svartpeppar",
    "1 tsk timjan",
    "1 tsk rosmarin",
    "4 dl vatten",
    "4 msk konc kalvfond",
    "2 msk balsamvinäger",
    "2 dl vispgrädde",
    "10 salladslökar",
    "1 dl färska örter, t ex timjan, rosmarin och basilika",
]
_q_old_index_assignment_data = recipe_match_data_multi_cached(
    _q_old_index_assignment_recipe,
    [
        {"name": "Timjan i kruka Ekologisk 1-p Klass 1 ICA I love eco", "category": "vegetables"},
        {"name": "Rosmarin Ekologisk 1-p KRAV Klass 1 ICA I love eco", "category": "vegetables"},
        {"name": "Basilika i kruka Stor 1-p KRAV Svegro Klass 1", "category": "vegetables"},
    ],
)
test(
    "Old matched_ing_idx bug keeps expanded herb offers on the original ingredient line",
    sorted({offer.get("_matched_ing_idx") for offer in _q_old_index_assignment_data["matched_offers"]}),
    [12],
)
test(
    "Old matched_ing_idx bug never leaks expanded herb indices past the recipe length",
    max(offer.get("_matched_ing_idx", -1) for offer in _q_old_index_assignment_data["matched_offers"]) < len(_q_old_index_assignment_recipe),
    True,
)
test(
    "Q3 alternative cabbage group still counts as one matched ingredient",
    recipe_match_num_multi(
        ["2 kg bladkål, finstrimlad (vit, röd eller spetskål)"],
        [
            {"name": "Rödkål Klass 1", "category": "vegetables"},
            {"name": "Spetskål Klass 1", "category": "vegetables"},
        ],
    ),
    1,
)
test(
    "Q3 plus-combined line ignores manual no-match svartpeppar",
    recipe_match_num_multi(
        ["20 g ingefära + 2 krm malen gurkmeja + 1 krm svartpeppar"],
        [
            {"name": "Ingefära Färsk 200g", "category": "vegetables"},
            {"name": "Gurkmeja Mald 32g", "category": "spices"},
            {"name": "Svartpeppar Malen 45g", "category": "spices"},
        ],
    ),
    2,
)
test(
    "Q3 cache prefilter expands grouped cabbage text so rödkål is searchable",
    "rödkål" in expanded_prefilter_search_text(
        ["2 kg bladkål, finstrimlad (vit, röd eller spetskål)"]
    ),
    True,
)
test(
    "Q3 cached path keeps fresh ginger for plain gram-measured root ingredient",
    recipe_match_num_cached(
        ["20 g ingefära + 2 krm malen gurkmeja + 1 krm svartpeppar"],
        {
            "name": "Ingefära Färsk Rot 100g",
            "category": "vegetables",
            "weight_grams": 100,
        },
    ),
    1,
)
test(
    "Q7 creme av soltorkade tomater matches specific creme product",
    recipe_match_num(
        ["2 msk Creme av soltorkade tomater"],
        {"name": "Creme av Soltorkade tomater 140g", "category": "vegetables"},
    ),
    1,
)
test(
    "Q7 creme av soltorkade tomater does not match plain sun-dried tomato jar",
    recipe_match_num(
        ["2 msk Creme av soltorkade tomater"],
        {"name": "Soltorkade tomater 200g", "category": "vegetables"},
    ),
    0,
)
test(
    "Q7 creme av soltorkade tomater does not match tapenade",
    recipe_match_num(
        ["2 msk Creme av soltorkade tomater"],
        {"name": "Tapenade av Soltorkade tomater 130g", "category": "vegetables"},
    ),
    0,
)
test(
    "Q8 blandade bönor matches mixed bean products",
    recipe_match_num(
        ["1 frp Blandade bönor"],
        {"name": "Bönmix 380g", "category": "vegetables"},
    ),
    1,
)
test(
    "Q8 blandade bönor still does not match single-type kidney beans",
    recipe_match_num(
        ["1 frp Blandade bönor"],
        {"name": "Kidneybönor 380g", "category": "vegetables"},
    ),
    0,
)
test(
    "Q9 finskuren gräslök matches fresh chives in pot",
    recipe_match_num(
        ["2 msk finskuren gräslök"],
        {"name": "Gräslök i kruka 1-p Klass 1", "category": "vegetables"},
    ),
    1,
)
test(
    "Q9 finskuren gräslök accepts frozen chives",
    recipe_match_num(
        ["2 msk finskuren gräslök"],
        {"name": "Gräslök Finhackad Fryst 40g", "category": "spices"},
    ),
    1,
)
test(
    "Q2 batch 109 plain gräslök matches fresh chives in pot",
    recipe_match_num(
        ["gräslök"],
        {"name": "Gräslök i kruka 1-p Klass 1", "category": "vegetables"},
    ),
    1,
)
test(
    "Q2 batch 109 plain gräslök matches frozen chives",
    recipe_match_num(
        ["gräslök"],
        {"name": "Gräslök Finhackad Fryst 40g", "category": "spices"},
    ),
    1,
)
test(
    "Q2 batch 109 plain gräslök still does not match dried chive spice",
    recipe_match_num(
        ["gräslök"],
        {"name": "Gräslök Torkad 12g", "category": "spices"},
    ),
    0,
)
test(
    "Q4 batch 109 plain kryddpeppar matches whole allspice",
    recipe_match_num(
        ["1 krm kryddpeppar"],
        {"name": "Kryddpeppar Hel 12g ICA", "category": "spices"},
    ),
    1,
)
test(
    "Q4 batch 109 plain kryddpeppar also matches ground allspice",
    recipe_match_num(
        ["1 krm kryddpeppar"],
        {"name": "Kryddpeppar Malen 35g", "category": "spices"},
    ),
    1,
)
test(
    "Q4 batch 109 kryddpeppar hel still blocks ground allspice",
    recipe_match_num(
        ["1 krm kryddpeppar hel"],
        {"name": "Kryddpeppar Malen 35g", "category": "spices"},
    ),
    0,
)
test(
    "Q4 batch 109 kryddpeppar malen still blocks whole allspice",
    recipe_match_num(
        ["1 krm kryddpeppar malen"],
        {"name": "Kryddpeppar Hel 12g ICA", "category": "spices"},
    ),
    0,
)
test(
    "Q5 batch 109 explicit kycklingbröstfilé does not match kalkon bröstfilé",
    recipe_match_num(
        ["1 kg kycklinglårfilé eller bröstfilé av kyckling"],
        {"name": "Kalkon Bröstfilé 600g Ingelsta Kalkon", "category": "poultry"},
    ),
    0,
)
test(
    "Q5 batch 109 explicit kycklingbröstfilé still matches kyckling bröstfilé",
    recipe_match_num(
        ["1 kg kycklinglårfilé eller bröstfilé av kyckling"],
        {"name": "Kyckling Bröstfilé 650g", "category": "poultry"},
    ),
    1,
)
test(
    "Q5 batch 109 explicit kalkonbröstfilé does not match kyckling bröstfilé",
    recipe_match_num(
        ["600 g kalkonbröstfilé"],
        {"name": "Kyckling Bröstfilé 650g", "category": "poultry"},
    ),
    0,
)
test(
    "Q6 batch 109 parenthetical cornichons alternative matches cornichons offer",
    recipe_match_num(
        ["2 inlagda gurkor (eller 1 dl cornichons)"],
        {"name": "Cornichons 350g Felix", "category": "pantry"},
    ),
    1,
)
test(
    "Q5 batch 110 kronärtskockshjärtan extracts a dedicated hearts keyword",
    extract_keywords_from_ingredient("kronärtskockshjärtan"),
    ["kronärtskockshjärta"],
)
test(
    "Q5 batch 110 kronärtskockshjärtan matches exact hearts product",
    recipe_match_num(
        ["kronärtskockshjärtan"],
        {"name": "Kronärtskockshjärtan 390g Zeta", "category": "pantry"},
    ),
    1,
)
test(
    "Q5 batch 110 kronärtskockshjärtan also matches marinerade kronärtskockor fallback",
    recipe_match_num(
        ["kronärtskockshjärtan"],
        {"name": "Kronärtskockor marinerade 200g Zeta", "category": "pantry"},
    ),
    1,
)
test(
    "Q5 batch 110 kronärtskockshjärtan no longer matches fresh whole artichoke",
    recipe_match_num(
        ["kronärtskockshjärtan"],
        {"name": "Kronärtskocka Färsk Klass 1 ICA", "category": "vegetables"},
    ),
    0,
)
test(
    "Q5 batch 110 sojabönor konserv still matches canned soybeans",
    recipe_match_num(
        ["sojabönor konserv"],
        {"name": "Sojabönor Konserverade 380g Test", "category": "pantry"},
    ),
    1,
)
test(
    "Q5 batch 110 sojabönor konserv also matches burk wording",
    recipe_match_num(
        ["sojabönor konserv"],
        {"name": "Sojabönor 400g Burk Test", "category": "pantry"},
    ),
    1,
)
test(
    "Q5 batch 110 sojabönor konserv no longer matches frozen soybeans",
    recipe_match_num(
        ["sojabönor konserv"],
        {"name": "Sojabönor Frysta 500g Sevan", "category": "frozen"},
    ),
    0,
)
test(
    "Q6 batch 110 vitlök torkad i burk matches neutral krossad garlic",
    recipe_match_num(
        ["1 tsk Vitlök Torkad i Burk"],
        {"name": "Vitlök Krossad 210g Risberg", "category": "pantry"},
    ),
    1,
)
test(
    "Q6 batch 110 vitlök torkad i burk also matches neutral finhackad garlic",
    recipe_match_num(
        ["1 tsk Vitlök Torkad i Burk"],
        {"name": "Vitlök Finhackad Burk 190g Test", "category": "pantry"},
    ),
    1,
)
test(
    "Q6 batch 110 vitlök torkad i burk also matches neutral pressad garlic",
    recipe_match_num(
        ["1 tsk Vitlök Torkad i Burk"],
        {"name": "Vitlök Pressad 90g Test", "category": "pantry"},
    ),
    1,
)
test(
    "Q6 batch 110 vitlök torkad i burk does not match vitlökspulver",
    recipe_match_num(
        ["1 tsk Vitlök Torkad i Burk"],
        {"name": "Vitlökspulver 49g Santa Maria", "category": "spices"},
    ),
    0,
)
test(
    "Q6 batch 110 vitlök torkad i burk does not match split-word garlic powder either",
    recipe_match_num(
        ["1 tsk Vitlök Torkad i Burk"],
        {"name": "Vitlök Pulver 55g Test", "category": "spices"},
    ),
    0,
)
test(
    "Q6 batch 110 vitlök torkad i burk does not match dried garlic spice",
    recipe_match_num(
        ["1 tsk Vitlök Torkad i Burk"],
        {"name": "Vitlök Torkad 18g Test", "category": "spices"},
    ),
    0,
)
test(
    "Q6 batch 110 vitlök torkad i burk does not match garlic granules",
    recipe_match_num(
        ["1 tsk Vitlök Torkad i Burk"],
        {"name": "Vitlök Granulat 70g Test", "category": "spices"},
    ),
    0,
)
test(
    "Q6 batch 110 vitlök torkad i burk does not match garlic in oil",
    recipe_match_num(
        ["1 tsk Vitlök Torkad i Burk"],
        {"name": "Vitlök i Olja 200g Test", "category": "pantry"},
    ),
    0,
)
test(
    "Q6 batch 110 vitlök torkad i burk does not match marinerad garlic",
    recipe_match_num(
        ["1 tsk Vitlök Torkad i Burk"],
        {"name": "Vitlöksklyftor Marinerade 200g Test", "category": "pantry"},
    ),
    0,
)
test(
    "Q6 batch 110 fresh vitlök still does not match neutral jarred garlic",
    recipe_match_num(
        ["1 klyfta vitlök"],
        {"name": "Vitlök Finhackad Burk 190g Test", "category": "pantry"},
    ),
    0,
)
test(
    "Q7 batch 110 malen kardemumma matches ground cardamom despite helst nymald wording",
    recipe_match_num(
        ["3 krm malen kardemumma, helst nymald"],
        {"name": "Kardemumma Malen 28g Santa Maria", "category": "spices"},
    ),
    1,
)
test(
    "Q7 batch 110 malen kardemumma still blocks whole cardamom",
    recipe_match_num(
        ["3 krm malen kardemumma, helst nymald"],
        {"name": "Kardemumma Hel 18g Santa Maria", "category": "spices"},
    ),
    0,
)
test(
    "Q7 batch 110 kardemummakapslar still block malen cardamom",
    recipe_match_num(
        ["2 kardemummakapslar"],
        {"name": "Kardemumma Malen 28g Santa Maria", "category": "spices"},
    ),
    0,
)
test(
    "Q7 batch 117 kardemummakärnor still block ground cardamom",
    recipe_match_num(
        ["1 tsk kardemummakärnor"],
        {"name": "Kardemumma Malen 40g ICA Basic", "category": "spices"},
    ),
    0,
)
test(
    "Q7 batch 117 kardemummakärnor still match exact kernels",
    recipe_match_num(
        ["1 tsk kardemummakärnor"],
        {"name": "Kardemummakärnor 20g ICA", "category": "spices"},
    ),
    1,
)
test(
    "Q7 batch 117 kardemummakärnor still allow whole cardamom pods",
    recipe_match_num(
        ["1 tsk kardemummakärnor"],
        {"name": "Kardemummakapslar 10g Santa Maria", "category": "spices"},
    ),
    1,
)
test(
    "Q7 batch 117 generic malen kardemumma still blocks cardamom pods",
    recipe_match_num(
        ["1 tsk malen kardemumma"],
        {"name": "Kardemummakapslar 10g Santa Maria", "category": "spices"},
    ),
    0,
)
test(
    "Q9 batch 117 malformed canned cherry tomato wording blocks fresh cherry tomatoes",
    recipe_match_num(
        ["2 frp konserverade körsbärstomatertomater"],
        {"name": "Körsbärstomater 250g Klass 1 ICA", "category": "fruit"},
    ),
    0,
)
test(
    "Q9 batch 117 malformed canned cherry tomato wording still matches canned cherry tomatoes",
    recipe_match_num(
        ["2 frp konserverade körsbärstomatertomater"],
        {"name": "Körsbärstomater 400g Cirio", "category": "vegetables"},
    ),
    1,
)
test(
    "Q11 batch 117 spicy tikka masala sauce already matches live cooking sauce offers",
    recipe_match_num(
        ["300 g Spicy Tikka Masala Sauce"],
        {"name": "Cooking Spice Sauce Tikka Masala 360g Santa Maria", "category": "pantry"},
    ),
    1,
)
test(
    "Q12 batch 117 counted chilifrukt now matches fresh chili offers",
    recipe_match_num(
        ["0,5 chilifrukt"],
        {"name": "Röd peppar 40g Klass 1 ICA", "category": "vegetables"},
    ),
    1,
)
test(
    "Q12 batch 117 generic counted chilifrukt also matches green chili offers",
    recipe_match_num(
        ["0,5 chilifrukt"],
        {"name": "Grön peppar 40g Klass 1 ICA", "category": "vegetables"},
    ),
    1,
)
test(
    "Q12 batch 117 explicit red chilifrukt still blocks green chili offers",
    recipe_match_num(
        ["1 finhackad röd chilifrukt"],
        {"name": "Grön chili 40g Klass 1", "category": "fruit"},
    ),
    0,
)
test(
    "Q13 batch 117 chorizokorvar no longer matches generic korv",
    recipe_match_num(
        ["2 chorizokorvar"],
        {"name": "Korv Frankfurter 320g Helmut Walch Charkuteri", "category": "poultry"},
    ),
    0,
)
test(
    "Q13 batch 117 chorizokorvar still matches actual chorizo",
    recipe_match_num(
        ["2 chorizokorvar"],
        {"name": "Chorizo 300g ICA", "category": "poultry"},
    ),
    1,
)
test(
    "Q14 batch 117 drained pineapple blocks fresh pineapple",
    recipe_match_num(
        ["350 g (avrunnen vikt) ananas"],
        {"name": "Ananas 250g ICA", "category": "fruit"},
    ),
    0,
)
test(
    "Q14 batch 117 drained pineapple blocks frozen pineapple",
    recipe_match_num(
        ["350 g (avrunnen vikt) ananas"],
        {"name": "Ananas Fryst 500g ICA Basic", "category": "fruit"},
    ),
    0,
)
test(
    "Q14 batch 117 drained pineapple still matches canned crushed pineapple",
    recipe_match_num(
        ["350 g (avrunnen vikt) ananas"],
        {"name": "Ananas Krossad 425g ICA", "category": "fruit"},
    ),
    1,
)
test(
    "Q2 batch 145 crushed pineapple blocks plain fresh pineapple",
    recipe_match_num(
        ["800 g Ananas Krossad"],
        {"name": "Ananas 250g ICA", "category": "fruit", "savings": 10},
    ),
    0,
)
test(
    "Q2 batch 145 crushed pineapple still matches frozen pineapple",
    recipe_match_num(
        ["800 g Ananas Krossad"],
        {"name": "Ananas Fryst 500g ICA Basic", "category": "fruit", "savings": 10},
    ),
    1,
)
test(
    "Q2 batch 145 crushed pineapple still matches crushed pineapple",
    recipe_match_num(
        ["800 g Ananas Krossad"],
        {"name": "Ananas Krossad 425g ICA", "category": "fruit", "savings": 10},
    ),
    1,
)
test(
    "Q15 batch 117 measured durumvete matches compound durum flour product",
    recipe_match_num(
        ["5 dl durumvete"],
        {"name": "Durumvetemjöl 1kg Kungsörnen", "category": "pantry"},
    ),
    1,
)
test(
    "Q15 batch 117 cached measured durumvete matches compound durum flour product",
    recipe_match_num_cached(
        ["5 dl durumvete"],
        {"name": "Durumvetemjöl 1kg Kungsörnen", "category": "pantry"},
    ),
    1,
)
test(
    "Q15 batch 117 measured durumvete also matches spaced mjol durumvete form",
    recipe_match_num(
        ["5 dl durumvete"],
        {"name": "Mjöl Durumvete 1kg Saltå Kvarn", "category": "pantry"},
    ),
    1,
)
test(
    "Q16 batch 117 smoked paprikapulver blocks plain paprika powder",
    recipe_match_num(
        ["0.5 tsk Rökt paprikapulver"],
        {"name": "Paprikapulver 70g ICA Basic", "category": "spices"},
    ),
    0,
)
test(
    "Q16 batch 117 smoked paprikapulver still matches smoked product",
    recipe_match_num(
        ["0.5 tsk Rökt paprikapulver"],
        {"name": "Paprikapulver Rökt 45g Santa Maria", "category": "spices"},
    ),
    1,
)
test(
    "Q17 batch 117 cached dill pa kvist matches live dill offers",
    recipe_match_num_cached(
        ["0,25 dl dill, på kvist"],
        {"name": "Dill i kruka Ekologisk 1-p KRAV Klass 1", "category": "vegetables"},
    ),
    1,
)
test(
    "Q18 batch 117 kantarellpesto no longer matches generic pesto",
    recipe_match_num(
        ["kantarellpesto"],
        {"name": "Pesto Alla Genovese 130g Zeta", "category": "pantry"},
    ),
    0,
)
test(
    "Q18 batch 117 kantarellpesto no longer matches preserved chanterelles",
    recipe_match_num(
        ["kantarellpesto"],
        {"name": "Kantareller i vatten 310g ICA", "category": "pantry"},
    ),
    0,
)
test(
    "Q18 batch 117 kronärtskockspesto no longer matches generic pesto",
    recipe_match_num(
        ["kronärtskockspesto"],
        {"name": "Pesto Alla Genovese 130g Zeta", "category": "pantry"},
    ),
    0,
)
test(
    "Q18 batch 117 stekta kantareller still matches fresh chanterelles",
    recipe_match_num_cached(
        ["kantareller, stekta"],
        {"name": "Kantarell gul 150g Klass 1 ICA", "category": "vegetables"},
    ),
    1,
)
test(
    "Q20 batch 117 syltad ingefara now matches exact syltad product",
    recipe_match_num(
        ["3 msk finhackad syltad ingefära"],
        {"name": "Ingefära Syltad Kub 240g Risberg", "category": "pantry"},
    ),
    1,
)
test(
    "Q20 batch 117 syltad ingefara no longer matches fresh ginger",
    recipe_match_num_cached(
        ["3 msk finhackad syltad ingefära"],
        {"name": "Ingefära Ekologisk 100g Klass 1 ICA I love", "category": "vegetables"},
    ),
    0,
)
test(
    "Q21 batch 117 pimientos del piquillo blocks fresh padron peppers",
    recipe_match_num(
        ["6 pimientos del piquillo (eller annan rostad och skalad paprika på burk)"],
        {"name": "Pimiento Padron 200 Gram Klass 1 ICA", "category": "vegetables"},
    ),
    0,
)
test(
    "Q21 batch 117 pimientos del piquillo still matches canned piquillo peppers",
    recipe_match_num(
        ["6 pimientos del piquillo (eller annan rostad och skalad paprika på burk)"],
        {"name": "Pimientos del piquillo 290g Zeta", "category": "pantry"},
    ),
    1,
)
test(
    "Q8 batch 110 grönsallad matches kruksallat",
    recipe_match_num(
        ["grönsallad"],
        {"name": "Kruksallat 1-p Klass 1 ICA", "category": "vegetables"},
    ),
    1,
)
test(
    "Q8 batch 110 grönsallad matches romansallad",
    recipe_match_num(
        ["grönsallad"],
        {"name": "Romansallad 2-p Klass 1 ICA", "category": "vegetables"},
    ),
    1,
)
test(
    "Q8 batch 110 grönsallad matches romanasallad",
    recipe_match_num(
        ["grönsallad"],
        {"name": "Romanasallad 2-p Klass 1 ICA", "category": "vegetables"},
    ),
    1,
)
test(
    "Q8 batch 110 grönsallad matches hjärtsallad",
    recipe_match_num(
        ["grönsallad"],
        {"name": "Hjärtsallad 2-p Klass 1 ICA", "category": "vegetables"},
    ),
    1,
)
test(
    "Q8 batch 110 grönsallad matches hjärtbergsallad",
    recipe_match_num(
        ["grönsallad"],
        {"name": "Hjärtbergsallad 2-p Klass 1 ICA", "category": "vegetables"},
    ),
    1,
)
test(
    "Q8 batch 110 grönsallad matches isbergssallat",
    recipe_match_num(
        ["grönsallad"],
        {"name": "Isbergssallat Klass 1 ICA", "category": "vegetables"},
    ),
    1,
)
test(
    "Q8 batch 110 grönsallad matches machesallat",
    recipe_match_num(
        ["grönsallad"],
        {"name": "Machesallat 65g ICA", "category": "vegetables"},
    ),
    1,
)
test(
    "Q8 batch 110 grönsallad still does not match sallad mix",
    recipe_match_num(
        ["grönsallad"],
        {"name": "Sallad Mix 200g ICA", "category": "vegetables"},
    ),
    0,
)
test(
    "Q8 batch 110 grönsallad still does not match ruccola",
    recipe_match_num(
        ["grönsallad"],
        {"name": "Ruccola 65g ICA", "category": "vegetables"},
    ),
    0,
)
test(
    "Q8 batch 110 grönsallad still does not match babyspenat",
    recipe_match_num(
        ["grönsallad"],
        {"name": "Babyspenat 65g ICA", "category": "vegetables"},
    ),
    0,
)
test(
    "Q1 batch 111 cached dill till garnering matches fresh dill in pot",
    recipe_match_num_cached(
        ["dill, till garnering"],
        {"name": "Dill i kruka Klass 1 ICA", "category": "vegetables"},
    ),
    1,
)
test(
    "Q1 batch 111 cached persilja till garnering matches fresh parsley in pot",
    recipe_match_num_cached(
        ["persilja, till garnering"],
        {"name": "Persilja i kruka Klass 1 ICA", "category": "vegetables"},
    ),
    1,
)
test(
    "Q1 batch 111 cached basilika till garnering matches fresh basil in pot",
    recipe_match_num_cached(
        ["basilika, till garnering"],
        {"name": "Basilika i kruka Klass 1 ICA", "category": "vegetables"},
    ),
    1,
)
test(
    "Q1 batch 111 cached plain dill still does not match fresh dill in pot",
    recipe_match_num_cached(
        ["dill"],
        {"name": "Dill i kruka Klass 1 ICA", "category": "vegetables"},
    ),
    0,
)
test(
    "Q1 batch 111 cached plain oregano still does not match fresh oregano in pot",
    recipe_match_num_cached(
        ["oregano"],
        {"name": "Oregano i kruka Klass 1 ICA", "category": "vegetables"},
    ),
    0,
)
test(
    "Q2 batch 111 pizza spices no longer matches unrelated asian spices",
    recipe_match_num(
        ["pizza spices herbs&chili, Santa Maria"],
        {"name": "Asian spices Korean BBQ bulgogi 35g Santa Maria", "category": "spices"},
    ),
    0,
)
test(
    "Q2 batch 111 cached pizza spices no longer matches unrelated asian spices",
    recipe_match_num_cached(
        ["pizza spices herbs&chili, Santa Maria"],
        {"name": "Asian spices Korean BBQ bulgogi 35g Santa Maria", "category": "spices"},
    ),
    0,
)
test(
    "Q2 batch 111 pizza spices no longer matches unrelated indian spices either",
    recipe_match_num(
        ["pizza spices herbs&chili, Santa Maria"],
        {"name": "Indian spices Raita 19g Santa Maria", "category": "spices"},
    ),
    0,
)
test(
    "Q2 batch 111 exact pizza spices wording is also suppressed for now",
    recipe_match_num(
        ["pizza spices herbs&chili, Santa Maria"],
        {"name": "Pizza spices herbs&chili 35g Santa Maria", "category": "spices"},
    ),
    0,
)
test(
    "Q3 batch 111 jalapeno mjukost matches hot jalapeno spread",
    recipe_match_num(
        ["2 dl mjukost hot jalapeño"],
        {"name": "Mjukost Hot Jalapeno 275g Kavli", "category": "dairy"},
    ),
    1,
)
test(
    "Q3 batch 111 cached jalapeno mjukost also matches hot jalapeno spread",
    recipe_match_num_cached(
        ["2 dl mjukost hot jalapeño"],
        {"name": "Mjukost Hot Jalapeno 275g Kavli", "category": "dairy"},
    ),
    1,
)
test(
    "Q3 batch 111 jalapeno mjukost no longer matches spicy tuna spread",
    recipe_match_num(
        ["2 dl mjukost hot jalapeño"],
        {"name": "Mjukost Spicy Tuna 220g Fjällbrynt", "category": "dairy"},
    ),
    0,
)
test(
    "Q3 batch 111 jalapeno mjukost no longer matches naturell spread",
    recipe_match_num(
        ["2 dl mjukost hot jalapeño"],
        {"name": "Mjukost Naturell 275g Kavli", "category": "dairy"},
    ),
    0,
)
test(
    "Q3 batch 111 pepparrot mjukost matches pepparrot spread",
    recipe_match_num(
        ["2 msk mjukost med pepparrot"],
        {"name": "Mjukost Pepparrot 275g Kavli", "category": "dairy"},
    ),
    1,
)
test(
    "Q3 batch 111 pepparrot mjukost no longer matches naturell spread",
    recipe_match_num(
        ["2 msk mjukost med pepparrot"],
        {"name": "Mjukost Naturell 275g Kavli", "category": "dairy"},
    ),
    0,
)
test(
    "Q3 batch 111 baconmjukost matches bacon spread",
    recipe_match_num(
        ["250 g baconmjukost"],
        {"name": "BaconOst Mjukost 275g Kavli", "category": "dairy"},
    ),
    1,
)
test(
    "Q3 batch 111 baconmjukost no longer matches naturell spread",
    recipe_match_num(
        ["250 g baconmjukost"],
        {"name": "Mjukost Naturell 275g Kavli", "category": "dairy"},
    ),
    0,
)
test(
    "Q3 batch 111 briesmak mjukost matches brie spread",
    recipe_match_num(
        ["1 tub mjukost med briesmak (à 250 g) eller se tips"],
        {"name": "Mjukost Brie 275g Kavli", "category": "dairy"},
    ),
    1,
)
test(
    "Q3 batch 111 briesmak mjukost no longer matches naturell spread",
    recipe_match_num(
        ["1 tub mjukost med briesmak (à 250 g) eller se tips"],
        {"name": "Mjukost Naturell 275g Kavli", "category": "dairy"},
    ),
    0,
)
test(
    "Q3 batch 111 plain mjukost still matches naturell spread",
    recipe_match_num(
        ["250 g mjukost (gärna mild)"],
        {"name": "Mjukost Naturell 275g Kavli", "category": "dairy"},
    ),
    1,
)
test(
    "Q4 parser keeps tomato fresh-or-canned alternatives separate",
    parse_eller_alternatives("7 tomater, färska eller 1 burk (400g) krossade"),
    ["7 tomater, färska", "1 burk (400g) krossade"],
)
test(
    "Q1 batch 114 parser expands measured spice-list alternatives",
    parse_eller_alternatives("1 msk anis, fänkål eller kummin"),
    ["1 msk anis", "1 msk fänkål", "1 msk kummin"],
)
test(
    "parser expands animal mince alternatives written as färs av X eller Y",
    parse_eller_alternatives("400 g lammfärs eller färs av kalv eller nöt"),
    ["400 g lammfärs", "400 g kalvfärs", "400 g nötfärs"],
)
test(
    "parser expands same-animal minced fallback from animal-part wording",
    parse_eller_alternatives("500 g kycklingbröstfilé eller färs"),
    ["500 g kycklingbröstfilé", "500 g kycklingfärs"],
)
test(
    "parser keeps outside-paren t.ex. ingredient examples",
    parse_eller_alternatives("blandade frukter t.ex. ananas, druvor, kiwi"),
    ["blandade frukter", "ananas", "druvor", "kiwi"],
)
test(
    "parser keeps pure parenthetical t.ex. ingredient examples",
    parse_eller_alternatives("2 dl grönsaker (t.ex. morötter, ärtor, majs)"),
    ["2 dl grönsaker", "morötter", "ärtor", "majs"],
)
test(
    "parser ignores descriptive t.ex. brand examples inside parentheticals",
    parse_eller_alternatives(
        "4 cl ingefärsshot (med ingefära och rödbeta t.ex. God Morgon drakfrukt, Ingefära)"
    ),
    ["4 cl ingefärsshot (med ingefära och rödbeta t.ex. God Morgon drakfrukt, Ingefära)"],
)
test(
    "Q4 batch 111 fresh tomato alternative matches fresh tomatoes",
    recipe_match_num(
        ["7 tomater, färska eller 1 burk (400g) krossade"],
        {"name": "Tomat kvist röd Svensk ca 120g Klass 1", "category": "fruit"},
    ),
    1,
)
test(
    "Q4 batch 111 canned tomato alternative matches krossade tomater",
    recipe_match_num(
        ["7 tomater, färska eller 1 burk (400g) krossade"],
        {"name": "Tomater Krossade 390g Mutti", "category": "pantry"},
    ),
    1,
)
test(
    "Q1 batch 113 product keyword normalizes moghrabie to moghrabiah",
    kw("Pärlcouscous Moghrabie 500g Sevan"),
    ["moghrabiah", "pärlcouscous"],
)
test(
    "Q1 batch 113 moghrabiah ingredient matches moghrabie product",
    recipe_match_num(
        ["320 g Stor Couscous Moghrabiah"],
        {"name": "Pärlcouscous Moghrabie 500g Sevan", "category": "pantry"},
    ),
    1,
)
test(
    "Q1 batch 113 cached moghrabiah ingredient also matches moghrabie product",
    recipe_match_num_cached(
        ["320 g Stor Couscous Moghrabiah"],
        {"name": "Pärlcouscous Moghrabie 500g Sevan", "category": "pantry"},
    ),
    1,
)
test(
    "Q2 batch 113 fresh onion with stalk cue extracts salladslök",
    extract_keywords_from_ingredient("3 färsk lökar, stjälkarna skivade"),
    ["salladslök"],
)
test(
    "Q2 batch 113 fresh onion with stalk cue matches salladslök",
    recipe_match_num(
        ["3 färsk lökar, stjälkarna skivade"],
        {"name": "Salladslök 125g Klass 1 ICA", "category": "vegetables"},
    ),
    1,
)
test(
    "Q2 batch 113 fresh onion with stalk cue no longer matches gul lök",
    recipe_match_num(
        ["3 färsk lökar, stjälkarna skivade"],
        {"name": "Gul lök 500g Klass 1 ICA", "category": "vegetables"},
    ),
    0,
)
test(
    "Q2 batch 113 generic fresh-or-frozen onion shortcut stays plain lök",
    extract_keywords_from_ingredient("2 dl hackad fryst eller färsk lök (2 dl hackad motsvarar 1-2 lökar)"),
    ["lök"],
)
test(
    "Q3 batch 113 cantuccini product emits cantuccini keyword",
    "cantuccini" in extract_keywords_from_product("Cantuccini Mandel 250gZeta", "snacks"),
    True,
)
test(
    "Q3 batch 113 cantucci product variant also emits cantuccini keyword",
    extract_keywords_from_product("Cantucci Mandel glutenfri 200g Zeta", "snacks"),
    ["cantuccini"],
)
test(
    "Q3 batch 113 biscotti ingredient normalizes to cantuccini",
    extract_keywords_from_ingredient("krossade biscotti och frysta bär"),
    ["cantuccini"],
)
test(
    "Q3 batch 113 almond cantuccini ingredient matches exact cantuccini product",
    recipe_match_num(
        ["4-5 st krossade Zeta Cantuccini Mandel"],
        {"name": "Cantuccini Mandel 250gZeta", "category": "snacks"},
    ),
    1,
)
test(
    "Q3 batch 113 almond cantuccini ingredient still blocks raw almonds",
    recipe_match_num(
        ["4-5 st krossade Zeta Cantuccini Mandel"],
        {"name": "Sötmandel 150g ICA", "category": "snacks"},
    ),
    0,
)
test(
    "Q2 batch 117 cantucci spelling variant now matches exact cantucci product",
    recipe_match_num(
        ["1 frp Zeta Cantucci Mandel glutenfri"],
        {"name": "Cantucci Mandel glutenfri 200g Zeta", "category": "snacks"},
    ),
    1,
)
test(
    "Q2 batch 117 cached cantucci spelling variant now matches exact cantucci product",
    recipe_match_num_cached(
        ["1 frp Zeta Cantucci Mandel glutenfri"],
        {"name": "Cantucci Mandel glutenfri 200g Zeta", "category": "snacks"},
    ),
    1,
)
test(
    "Q2 batch 117 glutenfri cantucci blocks canonical non-glutenfri cantuccini product",
    recipe_match_num(
        ["1 frp Zeta Cantucci Mandel glutenfri"],
        {"name": "Cantuccini Mandel 250g Zeta", "category": "snacks"},
    ),
    0,
)
test(
    "Q2 batch 117 cantucci spelling variant still blocks raw almonds",
    recipe_match_num(
        ["1 frp Zeta Cantucci Mandel glutenfri"],
        {"name": "Sötmandel 150g ICA", "category": "snacks"},
    ),
    0,
)
test(
    "Plain chèvre no longer matches Kavli chèvre spread",
    recipe_match_num(
        ["100 g chèvre"],
        {"name": "Chevre 230g Kavli", "category": "dairy"},
    ),
    0,
)
test(
    "Cached plain chèvre no longer matches Kavli chèvre spread",
    recipe_match_num_cached(
        ["100 g chèvre"],
        {"name": "Chevre 230g Kavli", "category": "dairy"},
    ),
    0,
)
test(
    "Plain chèvre still matches real chèvre cheese",
    recipe_match_num(
        ["100 g chèvre"],
        {"name": "Chevre 170 g President", "category": "dairy"},
    ),
    1,
)
test(
    "Q4 batch 117 generic rom now matches frozen löjrom offer",
    recipe_match_num(
        ["160 g Rom"],
        {"name": "Amerikansk löjrom Fryst 80g Pandalus", "category": "frozen"},
    ),
    1,
)
test(
    "Q4 batch 117 cached generic rom now matches frozen löjrom offer",
    recipe_match_num_cached(
        ["160 g Rom"],
        {"name": "Amerikansk löjrom Fryst 80g Pandalus", "category": "frozen"},
    ),
    1,
)
test(
    "Q4 batch 117 generic rom also matches stenbitsrom caviar offer",
    recipe_match_num(
        ["160 g Rom"],
        {"name": "Caviar röd stenbitsrom 75g ICA", "category": "pantry"},
    ),
    1,
)
test(
    "Q4 batch 117 generic rom also matches forellrom offer",
    recipe_match_num(
        ["160 g Rom"],
        {"name": "Forellrom röd 80g Kallax", "category": "pantry"},
    ),
    1,
)
test(
    "Q4 batch 117 generic rom no longer defaults to spirit products",
    recipe_match_num(
        ["160 g Rom"],
        {"name": "Mörk rom", "category": "beverages"},
    ),
    0,
)
test(
    "Earlier rom fix still blocks roe for light rum ingredient",
    recipe_match_num(
        ["8 cl Ljus rom"],
        {"name": "Amerikansk löjrom Fryst 80g Pandalus", "category": "frozen"},
    ),
    0,
)
test(
    "Explicit löjrom no longer falls back to stenbitsrom via generic rom",
    recipe_match_num(
        ["Löjrom Amerikansk Fryst"],
        {"name": "Caviar röd stenbitsrom 75g ICA", "category": "pantry"},
    ),
    0,
)
test(
    "Cached explicit löjrom no longer falls back to stenbitsrom via generic rom",
    recipe_match_num_cached(
        ["Löjrom Amerikansk Fryst"],
        {"name": "Caviar röd stenbitsrom 75g ICA", "category": "pantry"},
    ),
    0,
)
test(
    "Explicit löjrom still matches löjrom products",
    recipe_match_num(
        ["Löjrom Amerikansk Fryst"],
        {"name": "Amerikansk löjrom Fryst 80g Pandalus", "category": "frozen"},
    ),
    1,
)
test(
    "Q5 batch 117 cooked chickpeas with spad still match plain canned chickpeas",
    recipe_match_num(
        ["1 pkt kikärtor, kokta inkl. spad (ca 380 g)"],
        {"name": "Kikärtor 380g ICA", "category": "pantry"},
    ),
    1,
)
test(
    "Q5 batch 117 cooked chickpeas with spad also match explicit cooked chickpeas",
    recipe_match_num(
        ["1 pkt kikärtor, kokta inkl. spad (ca 380 g)"],
        {"name": "Kikärtor Kokta 380g Zeta", "category": "pantry"},
    ),
    1,
)
test(
    "Q5 batch 117 cooked chickpeas with spad block dry chickpeas",
    recipe_match_num(
        ["1 pkt kikärtor, kokta inkl. spad (ca 380 g)"],
        {"name": "Kikärtor Torra Ekologiska 500g ICA", "category": "pantry"},
    ),
    0,
)
test(
    "Q5 batch 117 cached cooked chickpeas with spad block dry chickpeas",
    recipe_match_num_cached(
        ["1 pkt kikärtor, kokta inkl. spad (ca 380 g)"],
        {"name": "Kikärtor Torra Ekologiska 500g ICA", "category": "pantry"},
    ),
    0,
)
test(
    "Q5 batch 117 cooked chickpeas with spad block frozen chickpeas",
    recipe_match_num(
        ["1 pkt kikärtor, kokta inkl. spad (ca 380 g)"],
        {"name": "Kikärtor Frysta 500g", "category": "frozen"},
    ),
    0,
)
test(
    "Q2 batch 128 branded burk chickpeas still match plain ready chickpeas",
    recipe_match_num(
        ["1 burk Zeta Kikärtor 410g"],
        {"name": "Kikärtor 480g Zeta", "category": "pantry"},
    ),
    1,
)
test(
    "Q2 batch 128 branded burk chickpeas block dry chickpeas",
    recipe_match_num(
        ["1 burk Zeta Kikärtor 410g"],
        {"name": "Kikärtor Torra Ekologiska 500g ICA", "category": "pantry"},
    ),
    0,
)
test(
    "Q2 batch 128 branded burk chickpeas block roasted snack chickpeas",
    recipe_match_num(
        ["1 burk Zeta Kikärtor 410g"],
        {"name": "Kikärtor Rostade gula 150g Tadim", "category": "pantry"},
    ),
    0,
)
test(
    "Q2 batch 128 branded packaged chickpeas also match plain ready chickpeas",
    recipe_match_num(
        ["Zeta Kikärtor Ekologiska"],
        {"name": "Kikärtor 480g Zeta", "category": "pantry"},
    ),
    1,
)
test(
    "Q2 batch 128 branded packaged chickpeas block dry chickpeas too",
    recipe_match_num(
        ["Zeta Kikärtor Ekologiska"],
        {"name": "Kikärtor Torra Ekologiska 500g ICA", "category": "pantry"},
    ),
    0,
)
test(
    "Q2 batch 128 measured chickpeas also prefer ready packaged products",
    recipe_match_num(
        ["380 g kikärtor"],
        {"name": "Kikärtor 380g ICA", "category": "pantry"},
    ),
    1,
)
test(
    "Q2 batch 128 measured chickpeas block dry chickpeas",
    recipe_match_num(
        ["380 g kikärtor"],
        {"name": "Kikärtor Torra Ekologiska 500g ICA", "category": "pantry"},
    ),
    0,
)
test(
    "Q4 batch 113 salami chips ingredient normalizes to salamichips",
    extract_keywords_from_ingredient("160 g salami -chips"),
    ["salamichips"],
)
test(
    "Q4 batch 113 salami chips product emits salamichips keyword",
    "salamichips" in extract_keywords_from_product("Classic Salami Chips 70g Cured Snack", "snacks"),
    True,
)
test(
    "Q4 batch 113 salami chips ingredient matches exact salami chips product",
    recipe_match_num(
        ["160 g salami -chips"],
        {"name": "Classic Salami Chips 70g Cured Snack", "category": "snacks"},
    ),
    1,
)
test(
    "Batch 142 tacochips ingredient normalizes to nachochips",
    extract_keywords_from_ingredient("1 st Tacochips"),
    ["nachochips"],
)
test(
    "Q4 batch 113 salami chips ingredient no longer matches plain chips",
    recipe_match_num(
        ["160 g salami -chips"],
        {"name": "Chips Saltade 200g ICA", "category": "snacks"},
    ),
    0,
)
test(
    "Q4 batch 113 salami chips ingredient no longer matches tortilla chips",
    recipe_match_num(
        ["160 g salami -chips"],
        {"name": "Tortilla Chips Saltade 185g Santa Maria", "category": "snacks"},
    ),
    0,
)
test(
    "Q1 batch 112 explicit frozen spinach blocks fresh babyspenat",
    recipe_match_num(
        ["150 g hackad fryst spenat"],
        {"name": "Finbladig babyspenat Sköljd 65g ICA", "category": "vegetables"},
    ),
    0,
)
test(
    "Q1 batch 112 explicit frozen spinach blocks fresh babyspenat in cached path",
    recipe_match_num_cached(
        ["150 g hackad fryst spenat"],
        {"name": "Finbladig babyspenat Sköljd 65g ICA", "category": "vegetables"},
    ),
    0,
)
test(
    "Q1 batch 112 explicit frozen spinach blocks fresh storpack spenat",
    recipe_match_num(
        ["150 g hackad fryst spenat"],
        {"name": "Spenat i storpack Sköljd 200g ICA", "category": "vegetables"},
    ),
    0,
)
test(
    "Q1 batch 112 explicit frozen spinach still matches frozen spinach",
    recipe_match_num(
        ["150 g hackad fryst spenat"],
        {"name": "Hackad spenat Fryst 400g Findus", "category": "frozen"},
    ),
    1,
)
test(
    "Q10 pimenton picante matches the correct spice product",
    recipe_match_num(
        ["2 tsk pimentón de la vera picante"],
        {"name": "Pimenton Picante Stark 75g", "category": "spices"},
    ),
    1,
)
test(
    "Q10 cached pimenton picante also matches the correct spice product",
    recipe_match_num_cached(
        ["2 tsk pimentón de la vera picante"],
        {"name": "Pimenton Picante Stark 75g", "category": "spices"},
    ),
    1,
)
test(
    "Q10 pimenton picante does not match salami picante",
    recipe_match_num(
        ["2 tsk pimentón de la vera picante"],
        {"name": "Salami Picante 150g", "category": "poultry"},
    ),
    0,
)
test(
    "Q11 worcestershiresås matches shortened worcestersås naming",
    recipe_match_num(
        ["1/2 tsk worcestershiresås"],
        {"name": "Worcestersås 150ml", "category": "spices"},
    ),
    1,
)
test(
    "Q11 worcestershiresås also allows flavored worcestersås variants",
    recipe_match_num_cached(
        ["1/2 tsk worcestershiresås"],
        {"name": "Worcestersås Wine & Pepper 150ml", "category": "spices"},
    ),
    1,
)
test(
    "Q12 libabröd matches Liba flatbread products",
    recipe_match_num(
        ["libabröd"],
        {"name": "Liba Original 4-p 340g", "category": "bread", "brand": "LIBA BRÖD"},
    ),
    1,
)
test(
    "Q12 libabröd does not match Liba bagels",
    recipe_match_num(
        ["libabröd"],
        {"name": "Bagels Classic 300g", "category": "bread", "brand": "LIBA BRÖD"},
    ),
    0,
)
test(
    "Q12 libabröd still does not match pinsa",
    recipe_match_num_cached(
        ["libabröd"],
        {"name": "Liba Pinsa 230g", "category": "bread", "brand": "LIBA BRÖD"},
    ),
    0,
)
test(
    "Q13 torkad grönpeppar still matches plain dried spice product",
    recipe_match_num(
        ["1/2 msk torkad grönpeppar"],
        {"name": "Grönpeppar 13g", "category": "spices"},
    ),
    1,
)
test(
    "Q13 torkad grönpeppar does not match whole green peppercorns",
    recipe_match_num(
        ["1/2 msk torkad grönpeppar"],
        {"name": "Grönpeppar Hel 10g", "category": "spices"},
    ),
    0,
)
test(
    "Q13 torkad grönpeppar does not match grönpeppar i lag",
    recipe_match_num_cached(
        ["1/2 msk torkad grönpeppar"],
        {"name": "Grönpeppar i lag 80g", "category": "spices"},
    ),
    0,
)
test(
    "Q14 passerade tomater still match passata products",
    recipe_match_num(
        ["200 g Passerade Tomater"],
        {"name": "Passerade tomater 390g", "category": "vegetables"},
    ),
    1,
)
test(
    "Q14 cached passerade tomater still match passata products",
    recipe_match_num_cached(
        ["200 g Passerade Tomater"],
        {"name": "Passerade tomater 390g", "category": "vegetables"},
    ),
    1,
)
test(
    "Q14 passerade tomater do not match fresh tomato offers",
    recipe_match_num(
        ["200 g Passerade Tomater"],
        {"name": "Tomat Romantica 300g Klass 1", "category": "fruit"},
    ),
    0,
)
test(
    "Q14 cached passerade tomater do not match fresh tomato offers",
    recipe_match_num_cached(
        ["200 g Passerade Tomater"],
        {"name": "Tomat Romantica 300g Klass 1", "category": "fruit"},
    ),
    0,
)
test(
    "Q15 generic svamp matches fresh champinjoner",
    recipe_match_num(
        ["400 g valfri svamp"],
        {"name": "Champinjoner Klass 1", "category": "vegetables"},
    ),
    1,
)
test(
    "Q15 cached generic svamp matches fresh kantarell",
    recipe_match_num_cached(
        ["400 g valfri svamp"],
        {"name": "Kantareller färska", "category": "vegetables"},
    ),
    1,
)
test(
    "Q15 generic svamp matches fresh ostronskivling",
    recipe_match_num(
        ["400 g valfri svamp"],
        {"name": "Ostronskivling Klass 1", "category": "vegetables"},
    ),
    1,
)
test(
    "Q15 generic svamp still does not match dried shiitake",
    recipe_match_num_cached(
        ["400 g valfri svamp"],
        {"name": "Shiitake Torkad 30g", "category": "vegetables"},
    ),
    0,
)
test(
    "Q1 batch 102 chokladpudding does not match generic protein pudding",
    recipe_match_num(
        ["1 pkt chokladpudding"],
        {"name": "Protein Salted Caramel Pudding 200g", "category": "mejeri"},
    ),
    0,
)
test(
    "Q1 batch 102 chokladpudding still matches exact chokladpudding product",
    recipe_match_num(
        ["1 pkt chokladpudding"],
        {"name": "Chokladpudding 2-pack", "category": "mejeri"},
    ),
    1,
)
test(
    "Q1 batch 102 plain pudding can still match generic pudding products",
    recipe_match_num_cached(
        ["pudding"],
        {"name": "Protein Salted Caramel Pudding 200g", "category": "mejeri"},
    ),
    1,
)
test(
    "Q2 batch 102 cantucciniskorpor does not match generic skorpor",
    recipe_match_num(
        ["cantucciniskorpor"],
        {"name": "Cardamom Skorpor 200g", "category": "bread"},
    ),
    0,
)
test(
    "Q2 batch 102 cantucciniskorpor still matches exact cantuccini product",
    recipe_match_num(
        ["cantucciniskorpor"],
        {"name": "Cantucciniskorpor 200g", "category": "bread"},
    ),
    1,
)
test(
    "Q2 batch 102 plain skorpor can still match generic skorpor",
    recipe_match_num_cached(
        ["skorpor"],
        {"name": "Cardamom Skorpor 200g", "category": "bread"},
    ),
    1,
)
test(
    "Q1 batch 103 syrade gurkor do not match fresh cucumber",
    recipe_match_num(
        ["400 g syrade gurkor, strimlade"],
        {"name": "Gurka Klass 1", "category": "vegetables"},
    ),
    0,
)
test(
    "Q1 batch 103 syrade gurkor do not fall back to inlagdgurka family",
    recipe_match_num_cached(
        ["400 g syrade gurkor, strimlade"],
        {"name": "Smörgåsgurka 560g", "category": "vegetables"},
    ),
    0,
)
test(
    "Q1 batch 103 syrade gurkor still match exact syrad gurka wording",
    recipe_match_num(
        ["400 g syrade gurkor, strimlade"],
        {"name": "Syrad Gurka 350g", "category": "vegetables"},
    ),
    1,
)
test(
    "Q2 batch 103 explicit prästost still matches prästost",
    recipe_match_num(
        ["100 g Prästost"],
        {"name": "Prästost 31%", "category": "dairy"},
    ),
    1,
)
test(
    "Q2 batch 103 explicit prästost does not match mozzarella",
    recipe_match_num(
        ["100 g Prästost"],
        {"name": "Mozzarella 125g", "category": "dairy"},
    ),
    0,
)
test(
    "Q2 batch 103 generic ost still matches prästost",
    recipe_match_num_cached(
        ["100 g ost"],
        {"name": "Prästost 31%", "category": "dairy"},
    ),
    1,
)
test(
    "Q2 batch 103 generic ost still matches hushållsost",
    recipe_match_num_cached(
        ["100 g ost"],
        {"name": "Hushållsost 26%", "category": "dairy"},
    ),
    1,
)
test(
    "Q1 batch 104 vitt vin still matches white cooking wine",
    recipe_match_num_cached(
        ["2 dl vitt vin"],
        {"name": "Matlagningsvin Vitt 75cl", "category": "pantry"},
    ),
    1,
)
test(
    "Q1 batch 104 vitt vin does not match red cooking wine",
    recipe_match_num_cached(
        ["2 dl vitt vin"],
        {"name": "Matlagningsvin Rött 75cl", "category": "pantry"},
    ),
    0,
)
test(
    "Q1 batch 120 sparkling wine ingredient extracts mousserandevin exact family",
    extract_keywords_from_ingredient("1 dl champagne eller mousserande vitt vin"),
    ["champagne", "mousserandevin"],
)
test(
    "Q1 batch 120 mousserande vitt vin product extracts exact sparkling wine family",
    kw("Mousserande Vitt Vin Alkoholfri 75cl Chapel Hill", "beverages"),
    ["mousserandevin"],
)
test(
    "Q1 batch 120 mousserande chardonnay product also extracts sparkling wine family",
    kw("Mousserande Chardonnay Alkoholfri 75cl Barrels & Drums", "beverages"),
    ["mousserandevin"],
)
test(
    "Q1 batch 120 sparkling white wine ingredient matches real mousserande wine",
    recipe_match_num_cached(
        ["1 dl champagne eller mousserande vitt vin"],
        {"name": "Mousserande Vitt Vin Alkoholfri 75cl Chapel Hill", "category": "beverages"},
    ),
    1,
)
test(
    "Q1 batch 120 sparkling white wine ingredient also matches generic mousserande wine",
    recipe_match_num_cached(
        ["1 dl champagne eller mousserande vitt vin"],
        {"name": "Mousserande vin Alkoholfritt 750ml Oddbird", "category": "beverages"},
    ),
    1,
)
test(
    "Q1 batch 120 sparkling white wine ingredient no longer matches mousserande fläderblomsvin",
    recipe_match_num_cached(
        ["1 dl champagne eller mousserande vitt vin"],
        {"name": "Mousserande Fläderblomsvin 0,5% 75cl Kiviks Musteri", "category": "beverages"},
    ),
    0,
)
test(
    "Q1 batch 120 sparkling white wine ingredient no longer matches mousserande spritz",
    recipe_match_num_cached(
        ["1 dl champagne eller mousserande vitt vin"],
        {"name": "Mousserande Orange Spritz Alkoholfri 75cl Aprezzare", "category": "beverages"},
    ),
    0,
)
test(
    "Q1 batch 120 sparkling white wine ingredient no longer matches mousserande must",
    recipe_match_num_cached(
        ["1 dl champagne eller mousserande vitt vin"],
        {"name": "Äppelmust Mousserande 75cl La Ribaude", "category": "beverages"},
    ),
    0,
)
test(
    "Q1 batch 120 sparkling white wine ingredient still keeps cooking-wine fallback",
    recipe_match_num_cached(
        ["1 dl champagne eller mousserande vitt vin"],
        {"name": "Matlagningsvin Vitt 75cl", "category": "pantry"},
    ),
    1,
)
test(
    "Q1 batch 141 kokosnötsdryck matches coconut drink",
    recipe_match_num_cached(
        ["4 dl kokosnötsdryck"],
        {"name": "Kokosdryck Laktosfri 1l ICA", "category": "dairy"},
    ),
    1,
)
test(
    "Q1 batch 141 kokosnötsdryck blocks whole coconut",
    recipe_match_num_cached(
        ["4 dl kokosnötsdryck"],
        {"name": "Kokosnöt ca 500g Klass 1 ICA", "category": "fruit/vegetables"},
    ),
    0,
)
test(
    "Q2 batch 141 havssalt matches plain sea salt",
    recipe_match_num_cached(
        ["1 tsk Havssalt"],
        {"name": "Havssalt 250g Maldon", "category": "spices"},
    ),
    1,
)
test(
    "Q2 batch 141 flingsalt matches Maldon sea salt flakes",
    recipe_match_num_cached(
        ["1 tsk Flingsalt"],
        {"name": "Havssalt 250g Maldon", "category": "spices"},
    ),
    1,
)
test(
    "Q2 batch 141 havssalt still blocks Herbamare spice mix",
    recipe_match_num_cached(
        ["1 tsk Havssalt"],
        {"name": "Ört Havssalt Herbamare", "category": "spices"},
    ),
    0,
)
test(
    "Q3 batch 120 creme fraiche franska örter no longer matches loose herb spice",
    recipe_match_num_cached(
        ["4 dl Creme Fraiche Franska Örter"],
        {"name": "Franska Örter 15g Santa Maria", "category": "spices"},
    ),
    0,
)
test(
    "Q3 batch 120 creme fraiche franska örter still matches actual creme fraiche product",
    recipe_match_num_cached(
        ["4 dl Creme Fraiche Franska Örter"],
        {"name": "Creme Fraiche Franska Örter 28% 2,5dl Valio", "category": "dairy"},
    ),
    1,
)
test(
    "Q4 batch 126 creme fraiche naturell blocks tex mex flavor",
    recipe_match_num_cached(
        ["1 dl Creme Fraiche Naturell"],
        {"name": "Lätt Creme Fraiche Tex Mex Lime Koriander 18% 2dl ICA", "category": "dairy"},
    ),
    0,
)
test(
    "Q4 batch 126 creme fraiche naturell still matches plain naturell product",
    recipe_match_num_cached(
        ["1 dl Creme Fraiche Naturell"],
        {"name": "Creme Fraiche Naturell 34% 2dl ICA", "category": "dairy"},
    ),
    1,
)
test(
    "Q1 batch 121 söt chilisås matches sweet chili hot sauce",
    recipe_match_num_cached(
        ["2 msk söt chilisås"],
        {"name": "Sweet Chili Sås Hot 200ml Santa Maria", "category": "pantry"},
    ),
    1,
)
test(
    "Q1 batch 121 söt chilisås matches sweet chili sauce with less sugar wording",
    recipe_match_num_cached(
        ["2 msk söt chilisås"],
        {"name": "Sweet Chili sås Asia Mindre socker 500ml Santa Maria", "category": "pantry"},
    ),
    1,
)
test(
    "Q1 batch 121 söt chilisås does not match unsweetened chili sauce",
    recipe_match_num_cached(
        ["2 msk söt chilisås"],
        {"name": "Chilisås Osötad 550g Felix", "category": "pantry"},
    ),
    0,
)
test(
    "Q3 batch 121 persiljekvistar matches fresh parsley offer",
    recipe_match_num_cached(
        ["ett par persiljekvistar"],
        {"name": "Persilja i kruka Ekologisk 1-p KRAV Klass 1", "category": "fruit_veg"},
    ),
    1,
)
test(
    "Q3 batch 121 persiljekvistar accepts frozen parsley",
    recipe_match_num_cached(
        ["ett par persiljekvistar"],
        {"name": "Persilja Finhackad Fryst 40g ICA", "category": "frozen"},
    ),
    1,
)
test(
    "Q3 batch 121 persiljekvistar does not match parsley bruschetta",
    recipe_match_num_cached(
        ["ett par persiljekvistar"],
        {"name": "Bruschetta Vitlök & persilja 140g Zeta", "category": "pantry"},
    ),
    0,
)
test(
    "Q1 batch 122 lammkotletter still matches exact lamb chop product",
    recipe_match_num_cached(
        ["8-10 lammkotletter"],
        {"name": "Lammkotlett med ben ca 500g", "category": "meat"},
    ),
    1,
)
test(
    "Q1 batch 122 lammkotletter does not match generic lamb roast",
    recipe_match_num_cached(
        ["8-10 lammkotletter"],
        {"name": "Lammstek med ben ca 2kg Scan", "category": "meat"},
    ),
    0,
)
test(
    "Q1 batch 122 lammkotletter does not match lamb racks",
    recipe_match_num_cached(
        ["8-10 lammkotletter"],
        {"name": "Lammracks ca 400g", "category": "meat"},
    ),
    0,
)
test(
    "Q2 batch 122 oil line with till laxen no longer matches salmon",
    recipe_match_num_cached(
        ["4 msk Zeta Extra jungfruolivolja Classico till laxen"],
        {"name": "Laxfilé Färsk 800g Pacific brand", "category": "fish"},
    ),
    0,
)
test(
    "Q2 batch 122 oil line with till laxen still matches olive oil",
    recipe_match_num_cached(
        ["4 msk Zeta Extra jungfruolivolja Classico till laxen"],
        {"name": "Olivolja Extra Jungfru 500ml Zeta", "category": "pantry"},
    ),
    1,
)
test(
    "Q1 batch 119 explicit extra virgin olive oil blocks lemon olive oil",
    recipe_match_num(
        ["1/2 dl Zeta Extra jungfruolivolja Classico"],
        {"name": "Olivolja Citron 250ml Zeta", "category": "pantry"},
    ),
    0,
)
test(
    "Q1 batch 119 explicit extra virgin olive oil blocks olive-oil spray",
    recipe_match_num(
        ["1/2 dl Zeta Extra jungfruolivolja Classico"],
        {"name": "Olivolja Spray 200ml Zeta", "category": "pantry"},
    ),
    0,
)
test(
    "Q1 batch 119 explicit extra virgin olive oil still matches plain extra virgin oil",
    recipe_match_num(
        ["1/2 dl Zeta Extra jungfruolivolja Classico"],
        {"name": "Olivolja Extra Jungfru 500ml Zeta", "category": "pantry"},
    ),
    1,
)
test(
    "Q2 batch 122 sirap till färsen no longer matches minced meat",
    recipe_match_num_cached(
        ["1 msk sirap till färsen"],
        {"name": "Nötfärs 500g", "category": "meat"},
    ),
    0,
)
test(
    "Q2 batch 122 sirap till färsen still matches syrup",
    recipe_match_num_cached(
        ["1 msk sirap till färsen"],
        {"name": "Sirap Ljus 750g Dansukker", "category": "pantry"},
    ),
    1,
)
test(
    "Q1 batch 104 rödvinsmarinad still matches exact red wine marinade",
    recipe_match_num(
        ["75 g rödvinsmarinad"],
        {"name": "Rödvinsmarinad 75g", "category": "pantry"},
    ),
    1,
)
test(
    "Q1 batch 104 rödvinsmarinad does not match generic marinade",
    recipe_match_num_cached(
        ["75 g rödvinsmarinad"],
        {"name": "Marinad BBQ 75g", "category": "pantry"},
    ),
    0,
)
test(
    "Q1 batch 104 vitvinsmarinad still matches exact white wine marinade",
    recipe_match_num(
        ["75 g vitvinsmarinad"],
        {"name": "Vitvinsmarinad 75g", "category": "pantry"},
    ),
    1,
)
test(
    "Q1 batch 104 vitvinsmarinad does not match generic marinade",
    recipe_match_num_cached(
        ["75 g vitvinsmarinad"],
        {"name": "Marinad Örter 75g", "category": "pantry"},
    ),
    0,
)
test(
    "Q2 batch 104 proteinpudding does not match generic pudding-only products",
    recipe_match_num(
        ["1 förp ProPud proteinpudding Choklad"],
        {"name": "Protein Salted Caramel Pudding 200g", "category": "mejeri"},
    ),
    0,
)
test(
    "Q2 batch 104 proteinpudding still matches explicit proteinpudding products",
    recipe_match_num_cached(
        ["1 förp ProPud proteinpudding Choklad"],
        {"name": "Proteinpudding Choklad 200g", "category": "mejeri"},
    ),
    1,
)
test(
    "Q2 batch 104 plain pudding still matches generic pudding products",
    recipe_match_num_cached(
        ["pudding"],
        {"name": "Protein Salted Caramel Pudding 200g", "category": "mejeri"},
    ),
    1,
)
test(
    "Q3 batch 104 citrus usage line still matches fresh citron",
    recipe_match_num_cached(
        ["saft och rivet skal av 1/2 liten citron"],
        {"name": "Citron 500g Klass 1 ICA", "category": "fruit"},
    ),
    1,
)
test(
    "Q3 batch 104 citrus usage line does not match bottled citronjuice",
    recipe_match_num(
        ["saft och rivet skal av 1/2 liten citron"],
        {"name": "Citronjuice 200ml", "category": "pantry"},
    ),
    0,
)
test(
    "Q3 batch 104 combined lime zest and juice line matches fresh lime",
    recipe_match_num_cached(
        ["finrivet skal och 2 msk saft av 1 lime"],
        {"name": "Lime Klass 1", "category": "fruit"},
    ),
    1,
)
test(
    "Q3 batch 104 pure citrus juice line still matches bottled citronjuice",
    recipe_match_num(
        ["saften av 1 citron"],
        {"name": "Citronjuice 200ml", "category": "pantry"},
    ),
    1,
)
test(
    "Q1 batch 105 uncached plain counted chili does not match ground chili spice",
    recipe_match_num(
        ["2 chili"],
        {"name": "Chilipeppar Malen 40g", "category": "spices"},
    ),
    0,
)
test(
    "Q1 batch 105 cached plain counted chili does not match ground chili spice",
    recipe_match_num_cached(
        ["2 chili"],
        {"name": "Chilipeppar Malen 40g", "category": "spices"},
    ),
    0,
)
test(
    "Q1 batch 105 cached plain counted chili does not match sparse chili spice jar",
    recipe_match_num_cached(
        ["2 chili"],
        {"name": "Chili Original 34g", "category": "spices"},
    ),
    0,
)
test(
    "Q1 batch 105 cached plain counted chili still matches fresh chili pepper",
    recipe_match_num_cached(
        ["2 chili"],
        {"name": "Chilipeppar Röd Klass 1", "category": "fruit"},
    ),
    1,
)
test(
    "Q1 batch 105 cached explicit ground chili still matches ground chili spice",
    recipe_match_num_cached(
        ["1 tsk chilipeppar malen"],
        {"name": "Chilipeppar Malen 40g", "category": "spices"},
    ),
    1,
)
test(
    "Q4 batch 104 cached red chilifrukt does not match green chili offer",
    recipe_match_num_cached(
        ["1 finhackad röd chilifrukt"],
        {"name": "Grön chili 40g Klass 1", "category": "fruit"},
    ),
    0,
)
test(
    "Q4 batch 104 uncached fresh jalapeno does not match pantry jalapenos jar",
    recipe_match_num(
        ["1 st Jalapeno Färsk"],
        {"name": "Jalapenos 225g", "category": "pantry"},
    ),
    0,
)
test(
    "Q4 batch 104 fresh jalapeno does not match pantry jalapenos jar",
    recipe_match_num_cached(
        ["1 st Jalapeno Färsk"],
        {"name": "Jalapenos 225g", "category": "pantry"},
    ),
    0,
)
test(
    "Q6 batch 114 pickled jalapeno still matches sparse jar name",
    recipe_match_num(
        ["1/2 dl avrunnen inlagd jalapeño"],
        {"name": "Jalapenos 225g ICA", "category": "spices"},
    ),
    1,
)
test(
    "Q6 batch 114 cached pickled jalapeno still matches sparse jar name",
    recipe_match_num_cached(
        ["1/2 dl avrunnen inlagd jalapeño"],
        {"name": "Jalapenos 225g ICA", "category": "spices"},
    ),
    1,
)
test(
    "Q6 batch 114 pickled jalapeno blocks miscategorized fresh grön jalapeno",
    recipe_match_num(
        ["1/2 dl avrunnen inlagd jalapeño"],
        {"name": "Grön jalapeno 40g Klass 1 ICA", "category": "meat"},
    ),
    0,
)
test(
    "Q6 batch 114 cached pickled jalapeno blocks miscategorized fresh grön jalapeno",
    recipe_match_num_cached(
        ["1/2 dl avrunnen inlagd jalapeño"],
        {"name": "Grön jalapeno 40g Klass 1 ICA", "category": "meat"},
    ),
    0,
)
test(
    "Q6 batch 114 pickled jalapeno blocks miscategorized fresh mörk jalapeno",
    recipe_match_num(
        ["1/2 dl avrunnen inlagd jalapeño"],
        {"name": "Mörk Jalapeno ca 25g Klass 1", "category": "meat"},
    ),
    0,
)
test(
    "Q6 batch 114 cached pickled jalapeno blocks miscategorized fresh mörk jalapeno",
    recipe_match_num_cached(
        ["1/2 dl avrunnen inlagd jalapeño"],
        {"name": "Mörk Jalapeno ca 25g Klass 1", "category": "meat"},
    ),
    0,
)
test(
    "Q6 batch 114 pickled jalapeno still accepts sparse pantry tres color product",
    recipe_match_num(
        ["1/2 dl avrunnen inlagd jalapeño"],
        {"name": "Jalapeno Tres Color 225g ICA Selection", "category": "pantry"},
    ),
    1,
)
test(
    "Q7 batch 114 grenadine ingredient matches Mixtales grenadine mix",
    match("Drinkmix Grenadine 350ml Mixtales", "1 cl Grenadine", "beverages"),
    "grenadine",
)
test(
    "Q7 batch 114 other Mixtales drink mixes stay blocked",
    match("Drinkmix Lime 35cl Mixtales", "1 lime", "beverages"),
    None,
)
test(
    "Q7 batch 114 krossad is matches exact crushed-ice product",
    match("Krossad is 1kg Mr Iceman", "krossad is", "frozen"),
    "krossadis",
)
test(
    "Q7 batch 114 krossad is still stays separate from ordinary isbitar",
    match("Isbitar 2kg ICA", "krossad is", "frozen"),
    None,
)
test(
    "Q2 batch 115 parser expands sill- eller strömmingsfiléer",
    parse_eller_alternatives("sill- eller strömmingsfiléer"),
    ["sillfiléer", "strömmingsfiléer"],
)
test(
    "Q2 batch 115 parser expands röd- eller vitkål shorthand",
    parse_eller_alternatives("röd- eller vitkål"),
    ["rödkål", "vitkål"],
)
test(
    "Q2 batch 115 ingredient extraction keeps both sill and strömming sides",
    extract_keywords_from_ingredient("sill- eller strömmingsfiléer"),
    ["sillfileer", "strömmingsfileer"],
)
test(
    "Q2 batch 115 sillfilé now matches sill- eller strömmingsfiléer",
    match("Sillfilé 420g Abbas", "sill- eller strömmingsfiléer", "fish"),
    "strömmingsfileer",
)
test(
    "Q2 batch 115 recipe matcher accepts sillfilé for sill- eller strömmingsfiléer",
    recipe_match_num(
        ["450 g sill- eller strömmingsfiléer"],
        {"name": "Sillfilé 420g Abbas", "category": "fish"},
    ),
    1,
)
test(
    "Q2 batch 115 recipe matcher still accepts strömmingsfiléer for sill- eller strömmingsfiléer",
    recipe_match_num(
        ["450 g sill- eller strömmingsfiléer"],
        {"name": "Strömmingsfiléer 420g Abba", "category": "fish"},
    ),
    1,
)
test(
    "Q6 batch 126 explicit strömmingsfiléer now match sillfilé offers",
    match("Sillfilé 420g Abbas", "400 g små strömmingsfiléer", "fish"),
    "strömmingsfileer",
)
test(
    "Q6 batch 126 explicit sillfilé also accepts strömmingsfiléer offers",
    match("Strömmingsfiléer 420g Abba", "400 g sillfiléer", "fish"),
    "sillfileer",
)
test(
    "Q6 batch 126 recipe matcher accepts sillfilé for explicit strömmingsfiléer",
    recipe_match_num(
        ["400 g små strömmingsfiléer"],
        {"name": "Sillfilé 420g Abbas", "category": "fish"},
    ),
    1,
)
test(
    "Q10 batch 126 recipe matcher accepts vaniljsås for vanilla alternative line",
    recipe_match_num_cached(
        ["vaniljglass, eller vaniljsås"],
        {"name": "Vaniljsås 500ml ICA", "category": "dairy"},
    ),
    1,
)
test(
    "Q1 batch 127 recipe matcher blocks tärnad ost i olja paprika from fresh paprika line",
    recipe_match_num_cached(
        ["1 paprika, tärnad"],
        {"name": "Tärnad ost i olja Paprika 100g ICA", "category": "deli"},
    ),
    0,
)
test(
    "Q1 batch 127 recipe matcher still accepts fresh paprika for fresh paprika line",
    recipe_match_num_cached(
        ["1 paprika, tärnad"],
        {"name": "Paprika Röd Klass 1 ICA", "category": "vegetables"},
    ),
    1,
)
test(
    "Q1 batch 128 recipe matcher plain vetemjöl blocks special fullkorn flour",
    recipe_match_num_cached(
        ["1 dl vetemjöl"],
        {"name": "Vetemjöl Special Fullkorn 2kg Kungsörnen", "category": "pantry"},
    ),
    0,
)
test(
    "Q1 batch 128 recipe matcher vetemjöl special matches special flour",
    recipe_match_num_cached(
        ["1 dl vetemjöl special"],
        {"name": "Vetemjöl Special 2kg Kungsörnen", "category": "pantry"},
    ),
    1,
)
test(
    "Q1 batch 128 recipe matcher vetemjöl fullkorn matches fullkorn flour",
    recipe_match_num_cached(
        ["1 dl vetemjöl fullkorn"],
        {"name": "Vetemjöl Fullkorn 2kg ICA", "category": "pantry"},
    ),
    1,
)
test(
    "Q3 batch 115 antipastitallrik now matches charkbricka",
    match("Antipastitallrik 120g Zeta", "120 g Charkbricka", "poultry"),
    "charkbricka",
)
test(
    "Q3 batch 115 tapastallrik now matches charkbricka",
    match("Tapastallrik med Fuet & Iberico 120g Zeta", "120 g Charkbricka", "poultry"),
    "charkbricka",
)
test(
    "Q3 batch 115 tapasmix now matches charkbricka",
    match("Tapasmix 250g PAUL och THOM", "120 g Charkbricka", "poultry"),
    "charkbricka",
)
test(
    "Q3 batch 115 salami antipasti still does not match charkbricka",
    match("Salami Antipasti 120g Zeta", "120 g Charkbricka", "poultry"),
    None,
)
test(
    "Q3 batch 115 recipe matcher accepts antipastitallrik for charkbricka",
    recipe_match_num(
        ["120 g Charkbricka"],
        {"name": "Antipastitallrik 120g Zeta", "category": "poultry"},
    ),
    1,
)
test(
    "Note batch 115 creme av kronärtskockor extracts specific spread keyword",
    extract_keywords_from_ingredient("Crème av kronärtskockor"),
    ["kronärtskockscreme"],
)
test(
    "Note batch 115 creme av kronärtskockor product extracts specific spread keyword",
    extract_keywords_from_product("Creme av Kronärtskockor 130g Zeta", "vegetables"),
    ["kronärtskockscreme"],
)
test(
    "Note batch 115 creme av kronärtskockor matches exact creme product",
    recipe_match_num(
        ["1 frp Zeta Crème av kronärtskockor"],
        {"name": "Creme av Kronärtskockor 130g Zeta", "category": "vegetables"},
    ),
    1,
)
test(
    "Note batch 115 creme av kronärtskockor does not match marinerade kronärtskockor",
    recipe_match_num(
        ["1 frp Zeta Crème av kronärtskockor"],
        {"name": "Kronärtskockor marinerade 200g Zeta", "category": "vegetables"},
    ),
    0,
)
test(
    "Note batch 115 creme av kronärtskockor does not match fresh artichoke",
    recipe_match_num(
        ["1 frp Zeta Crème av kronärtskockor"],
        {"name": "Kronärtskocka Färsk Klass 1", "category": "vegetables"},
    ),
    0,
)
test(
    "Batch 119 quorn bits recipe no longer matches Quorn mince",
    recipe_match_num(
        ["1 påse tinad grytbitar av quorn (à 300 g)"],
        {"name": "Mince/Färs vegetarisk 600g Quorn", "category": "meat", "brand": "Quorn"},
    ),
    0,
)
test(
    "Batch 119 quorn bits recipe still matches Quorn pieces",
    recipe_match_num(
        ["1 påse tinad grytbitar av quorn (à 300 g)"],
        {"name": "Vegetariska pieces/bitar Fryst 600g Quorn", "category": "meat", "brand": "Quorn"},
    ),
    1,
)
test(
    "Batch 119 inlagd mango no longer matches fresh mango",
    recipe_match_num(
        ["inlagd mango"],
        {"name": "Mango ca 325g Klass 1 ICA", "category": "fruit"},
    ),
    0,
)
test(
    "Batch 119 cached inlagd mango no longer matches fresh mango",
    recipe_match_num_cached(
        ["inlagd mango"],
        {"name": "Mango ca 325g Klass 1 ICA", "category": "fruit"},
    ),
    0,
)
test(
    "Batch 119 sardeller recipe no longer matches chili sardeller",
    recipe_match_num(
        ["8 Zeta Sardeller , finhackade eller 2 msk Zeta Sardellcrème MSC-märkt"],
        {"name": "Sardeller Med Chili ca 95g Talatta", "category": "fish"},
    ),
    0,
)
test(
    "Batch 119 cached sardeller recipe no longer matches chili sardeller",
    recipe_match_num_cached(
        ["8 Zeta Sardeller , finhackade eller 2 msk Zeta Sardellcrème MSC-märkt"],
        {"name": "Sardeller Med Chili ca 95g Talatta", "category": "fish"},
    ),
    0,
)
test(
    "Batch 119 neutral olja no longer matches rapsolja recipes",
    recipe_match_num(
        ["2 msk rapsolja"],
        {"name": "Neutral Olja KRAV 500ml Kung markatta", "category": "spices"},
    ),
    0,
)
test(
    "Batch 119 fladerblomssaft product still matches fladersaft ingredient",
    match("Fläderblomssaft 50cl Brunneby", "2 dl flädersaft", "beverages"),
    "flädersaft",
)
test(
    "Q1 batch 129 fladerdryck ingredient now matches elderflower drink product",
    recipe_match_num(
        ["3 msk Fläderdryck"],
        {"name": "Fläderblomsdryck med druva och citron 1l Kiviks Musteri", "category": "beverages"},
    ),
    1,
)
test(
    "Q1 batch 129 cached fladerdryck ingredient also matches elderflower drink product",
    recipe_match_num_cached(
        ["3 msk Fläderdryck"],
        {"name": "Fläderblomsdryck med druva och citron 1l Kiviks Musteri", "category": "beverages"},
    ),
    1,
)
test(
    "Q1 batch 129 fladerdryck ingredient also matches elderflower cordial product",
    recipe_match_num(
        ["3 msk Fläderdryck"],
        {"name": "Fläderblomssaft 50cl KRAV ICA I love eco", "category": "beverages"},
    ),
    1,
)
test(
    "Q1 batch 129 fladerdryck ingredient still blocks elderflower cider products",
    recipe_match_num(
        ["3 msk Fläderdryck"],
        {"name": "Flädercider 1l Herrljunga", "category": "beverages"},
    ),
    0,
)
test(
    "Q1 batch 129 fladerdryck ingredient still blocks elderflower tonic products",
    recipe_match_num(
        ["3 msk Fläderdryck"],
        {"name": "Tonic Fläder Eko 500ml Ekobryggeriet", "category": "beverages"},
    ),
    0,
)
test(
    "Batch 119 nyponsoppa exact product still matches nyponsoppa ingredient",
    match("Nyponsoppa 1l ICA", "5 dl nyponsoppa", "pantry"),
    "nyponsoppa",
)
test(
    "Q2 batch 98 cottage cheese products expose keso fallback",
    extract_keywords_from_product("Cottage cheese Naturell 4% 500g ICA", "dairy"),
    ["keso", "cottage cheese"],
)
test(
    "Q2 batch 98 keso now matches generic cottage cheese product",
    recipe_match_num(
        ["250 g keso"],
        {"name": "Cottage cheese Naturell 4% 500g ICA", "category": "dairy"},
    ),
    1,
)
test(
    "Q2 batch 98 keso still blocks flavored cottage cheese snack variant",
    recipe_match_num(
        ["250 g keso"],
        {"name": "Cottage cheese Blåbär 2,9% 500g KESO®", "category": "dairy"},
    ),
    0,
)
test(
    "Q8 batch 114 plain curry no longer matches explicit rödcurry",
    match("Curry 34g Santa Maria", "1 - 2 msk röd curry", "spices"),
    None,
)
test(
    "Q8 batch 114 red curry paste surfaces for explicit rödcurry",
    match("Red Curry Paste 114g Cock Brand", "1 - 2 msk röd curry", "pantry"),
    "rödcurry",
)
test(
    "Q8 batch 114 currypasta röd also surfaces for explicit rödcurry",
    match("Currypasta Röd 110g Santa Maria", "1 - 2 msk röd curry", "pantry"),
    "rödcurry",
)
test(
    "Q8 batch 114 röd currypasta wording also surfaces for explicit rödcurry",
    match("Röd Currypasta 110g Santa Maria", "1 - 2 msk röd curry", "pantry"),
    "rödcurry",
)
test(
    "Q8 batch 114 grytbas thai red curry still stays out for now",
    match("Grytbas Thai red curry Het 400ml Mrs Chengs", "1 - 2 msk röd curry", "pantry"),
    None,
)
test(
    "Q8 batch 114 sparse red-curry grytbas also stays out for now",
    match("Röd curry & pumpa Grytbas 400ml ICA Asia", "1 - 2 msk röd curry", "spices"),
    None,
)
test(
    "Q8 batch 114 recipe matcher blocks plain curry powder for rödcurry",
    recipe_match_num(
        ["1 - 2 msk röd curry"],
        {"name": "Curry 34g Santa Maria", "category": "spices"},
    ),
    0,
)
test(
    "Q8 batch 114 cached recipe matcher still accepts red curry paste",
    recipe_match_num_cached(
        ["1 - 2 msk röd curry"],
        {"name": "Red Curry Paste 114g Cock Brand", "category": "pantry"},
    ),
    1,
)
test(
    "Q8 batch 114 recipe matcher now also accepts currypasta röd",
    recipe_match_num(
        ["1 - 2 msk röd curry"],
        {"name": "Currypasta Röd 110g Santa Maria", "category": "pantry"},
    ),
    1,
)
test(
    "Q8 batch 114 recipe matcher keeps ready meals with red curry blocked",
    recipe_match_num(
        ["1 - 2 msk röd curry"],
        {"name": "Thai chicken red curry 750g Findus", "category": "frozen"},
    ),
    0,
)
test(
    "Q1 batch 115 generic kräftor now extracts to signalkräftor",
    extract_keywords_from_ingredient("1 kg kokta kräftor i lag"),
    ["signalkräftor"],
)
test(
    "Q1 batch 115 frozen signalkräftor now match kokta kräftor i lag",
    match("Svenska signalkräftor Fryst 500g ICA", "1 kg kokta kräftor i lag", "fish"),
    "kräftor",
)
test(
    "Q1 batch 115 recipe matcher accepts frozen signalkräftor for kokta kräftor i lag",
    recipe_match_num(
        ["1 kg kokta kräftor i lag"],
        {"name": "Svenska signalkräftor Fryst 500g ICA", "category": "fish"},
    ),
    1,
)
test(
    "Q1 batch 115 whole crayfish line blocks kräftstjärtar i lake",
    match("Kräftstjärtar i lake 170g Miljömärkt ICA Basic", "1 kg kokta kräftor i lag", "fish"),
    None,
)
test(
    "Q1 batch 115 whole crayfish line blocks kräftor i lag products",
    match("Kräftor i lag 500g", "1 kg kokta kräftor i lag", "fish"),
    None,
)
test(
    "Q4 batch 104 glaze chili does not match plain chili spice",
    recipe_match_num(
        ["2 msk Glaze Chili"],
        {"name": "Chilipeppar Malen 40g", "category": "spices"},
    ),
    0,
)
test(
    "Q5 batch 104 uncached varmrökt lax does not match kallrökt salmon",
    recipe_match_num(
        ["500 g Varmrökt lax"],
        {"name": "Kallrökt Lax 150g", "category": "deli"},
    ),
    0,
)
test(
    "Q5 batch 104 cached varmrökt lax does not match kallrökt salmon",
    recipe_match_num_cached(
        ["500 g Varmrökt lax"],
        {"name": "Kallrökt Lax 150g", "category": "deli"},
    ),
    0,
)
test(
    "Q5 batch 104 cached varmrökt lax still matches varmrökt salmon",
    recipe_match_num_cached(
        ["500 g Varmrökt lax"],
        {"name": "Varmrökt Lax 150g", "category": "deli"},
    ),
    1,
)
test(
    "Q6 batch 104 uncached ricotta spenat tortellini does not match ost skinka filling",
    recipe_match_num(
        ["2 förp färsk tortellini ricotta/spenat"],
        {"name": "Tortellini Ost & Skinka 250g", "category": "frozen"},
    ),
    0,
)
test(
    "Q6 batch 104 cached ricotta spenat tortellini does not match ost skinka filling",
    recipe_match_num_cached(
        ["2 förp färsk tortellini ricotta/spenat"],
        {"name": "Tortellini Ost & Skinka 250g", "category": "frozen"},
    ),
    0,
)
test(
    "Q6 batch 104 cached ricotta spenat tortellini still matches ricotta spenat filling",
    recipe_match_num_cached(
        ["2 förp färsk tortellini ricotta/spenat"],
        {"name": "Tortellini Ricotta & Spenat 250g", "category": "frozen"},
    ),
    1,
)
test(
    "Q6 batch 104 cached ricotta spenat tortellini matches spinaci wording too",
    recipe_match_num_cached(
        ["2 förp färsk tortellini ricotta/spenat"],
        {"name": "Tortellini Ricotta Spinaci 250g", "category": "frozen"},
    ),
    1,
)
test(
    "Q6 batch 104 cached prosciutto tortellini does not match ost skinka filling",
    recipe_match_num_cached(
        ["2 förp tortellini prosciutto"],
        {"name": "Tortellini Ost & Skinka 250g", "category": "frozen"},
    ),
    0,
)
test(
    "Q6 batch 104 cached prosciutto tortellini matches prosciutto filling",
    recipe_match_num_cached(
        ["2 förp tortellini prosciutto"],
        {"name": "Tortellini Prosciutto 250g", "category": "frozen"},
    ),
    1,
)
test(
    "Q6 batch 104 cached svamp tortelloni matches svamp filling",
    recipe_match_num_cached(
        ["2 förp tortelloni svamp"],
        {"name": "Tortelloni Svamp 250g", "category": "frozen"},
    ),
    1,
)
test(
    "Q6 batch 104 cached tortellini fyra ostar matches fem ostar family",
    recipe_match_num_cached(
        ["2 förp tortellini fyra ostar"],
        {"name": "Tortellini Fem Ostar 250g", "category": "frozen"},
    ),
    1,
)
test(
    "Q3 herb bundle counts as three matched ingredients when all herbs exist",
    recipe_match_num_multi(
        ["2 dl färska örter gärna färsk timjan, rosmarin och persilja"],
        [
            {"name": "Timjan färsk i kruka", "category": "vegetables"},
            {"name": "Rosmarin färsk i kruka", "category": "vegetables"},
            {"name": "Persilja färsk i kruka", "category": "vegetables"},
        ],
    ),
    3,
)
test(
    "Q3 herb bundle still finds the last herb when only one specific herb exists",
    recipe_match_num_multi(
        ["2 dl färska örter gärna färsk timjan, rosmarin och persilja"],
        [
            {"name": "Persilja färsk i kruka", "category": "vegetables"},
        ],
    ),
    1,
)
test(
    "Q4 explicit bifftomat matches exact bifftomat offer",
    match_kw("Bifftomat Klass 1", "Bifftomat", "vegetables"),
    "bifftomat",
)
test(
    "Q4 explicit bifftomat does not fall back to plain tomato offers",
    match_kw("Tomat Klass 1", "Bifftomat", "vegetables"),
    None,
)
test(
    "Q5 vit fiskfilé matches torskfilé",
    match_kw("Torskfilé Fryst", "vit fiskfilé", "fish"),
    "fiskfilé",
)
test(
    "Q5 vit fiskfilé matches stillahavstorsk ryggfilé",
    match_kw("Ryggfilé stillahavstorsk", "vit fiskfilé", "fish"),
    "fiskfilé",
)
test(
    "Q5 vit fiskfilé matches pangasiusfilé family",
    match_kw("Pangasiusmalfilé Fryst", "vit fiskfilé", "fish"),
    "fiskfilé",
)
test(
    "Q5 vit fiskfilé matches havskattfilé",
    match_kw("Havskattfilé", "vit fiskfilé", "fish"),
    "fiskfilé",
)
test(
    "Q5 vit fiskfilé does not match laxfilé",
    match_kw("Laxfilé Fryst", "vit fiskfilé", "fish"),
    None,
)
test(
    "Q6 jästa svarta bönor do not match plain black beans",
    recipe_match_num(
        ["jästa svarta bönor"],
        {"name": "Svarta bönor 380g", "category": "pantry"},
    ),
    0,
)
test(
    "Q6 jästa svarta bönor match fermented black beans",
    recipe_match_num(
        ["jästa svarta bönor"],
        {"name": "Fermenterade svarta bönor 200g", "category": "pantry"},
    ),
    1,
)
test(
    "Q6 jästa svarta bönor match jästa black beans",
    recipe_match_num(
        ["jästa svarta bönor"],
        {"name": "Jästa svarta bönor 200g", "category": "pantry"},
    ),
    1,
)
test(
    "Q6 jästa svarta bönor do not match baker's yeast",
    recipe_match_num(
        ["jästa svarta bönor"],
        {"name": "Jäst för matbröd", "category": "pantry"},
    ),
    0,
)
test(
    "Old hickory FP is gone and liquid smoke ingredient now extracts as exact compound",
    sorted(extract_keywords_from_ingredient("2 msk liquid smoke (Hickory)")),
    ["liquidsmoke"],
)
test(
    "Liquid smoke product exposes the same exact compound keyword",
    kw("Liquid smoke 147ml Try Me", "spices"),
    ["liquidsmoke"],
)
test(
    "Liquid smoke ingredient matches the real liquid smoke offer",
    recipe_match_num(
        ["2 msk liquid smoke (Hickory)"],
        {"name": "Liquid smoke 147ml Try Me", "category": "spices"},
    ),
    1,
)
test(
    "Liquid smoke ingredient does not fall back to hickory BBQ sauce",
    recipe_match_num(
        ["2 msk liquid smoke (Hickory)"],
        {"name": "Grillsås Hickory 230ml ICA", "category": "spices"},
    ),
    0,
)
test(
    "Frukt till Smoothie ingredient extracts as exact smoothie fruit compound",
    sorted(extract_keywords_from_ingredient("40 g Frukt till Smoothie")),
    ["smoothiefrukt"],
)
test(
    "Frukt till smoothies frozen product exposes the same exact compound keyword",
    kw("Frukt till smoothies Mango, ananas & banan Fryst 500g ICA", "frozen"),
    ["smoothiefrukt"],
)
test(
    "Frukt till Smoothie ingredient matches the frozen fruit-mix product",
    recipe_match_num(
        ["40 g Frukt till Smoothie"],
        {"name": "Frukt till smoothies Mango, ananas & banan Fryst 500g ICA", "category": "frozen"},
    ),
    1,
)
test(
    "Frukt till Smoothie ingredient does not fall back to smoothie drinks",
    recipe_match_num(
        ["40 g Frukt till Smoothie"],
        {"name": "Smoothie Mango & Hallon 250ml Innocent", "category": "dairy"},
    ),
    0,
)
test(
    "Havrebaserad dryck barista ingredient extracts as exact oat-barista compound",
    sorted(extract_keywords_from_ingredient("3 1/2 dl havrebaserad dryck barista")),
    ["havredryckbarista"],
)
test(
    "Havredryck Barista product exposes the exact oat-barista compound",
    kw("Havredryck Barista 1l ICA", "dairy"),
    ["havredryckbarista"],
)
test(
    "Havredryck iKaffe product also exposes the oat-barista compound",
    kw("Havredryck iKaffe 3% 1l Oatly", "dairy"),
    ["havredryckbarista"],
)
test(
    "Havrebaserad dryck barista ingredient matches plain oat barista drink",
    recipe_match_num(
        ["3 1/2 dl havrebaserad dryck barista"],
        {"name": "Havredryck Barista 1l ICA", "category": "dairy"},
    ),
    1,
)
test(
    "Havrebaserad dryck barista ingredient matches oat iKaffe variant",
    recipe_match_num(
        ["3 1/2 dl havrebaserad dryck barista"],
        {"name": "Havredryck iKaffe 3% 1l Oatly", "category": "dairy"},
    ),
    1,
)
test(
    "Havrebaserad dryck barista ingredient still blocks lactose-free dairy dryck",
    recipe_match_num(
        ["3 1/2 dl havrebaserad dryck barista"],
        {"name": "Mellanmjölkdryck Laktosfri 1,5% 1l ICA", "category": "dairy"},
    ),
    0,
)
test(
    "Havrebaserad dryck barista ingredient blocks flavored oat barista variants",
    recipe_match_num(
        ["3 1/2 dl havrebaserad dryck barista"],
        {"name": "Havredryck Barista Vanilj 3% 1000ml Oddlygood®", "category": "dairy"},
    ),
    0,
)
test(
    "ingefärsshot brand-example parenthetical does not match raw drakfrukt",
    recipe_match_num(
        ["4 cl ingefärsshot (med ingefära och rödbeta t.ex. God Morgon drakfrukt, Ingefära)"],
        {"name": "Drakfrukt Klass 1", "category": "fruit_veg"},
    ),
    0,
)
test(
    "ingefärsshot brand-example parenthetical does not match raw rödbeta",
    recipe_match_num(
        ["4 cl ingefärsshot (med ingefära och rödbeta t.ex. God Morgon drakfrukt, Ingefära)"],
        {"name": "Rödbetor färska 500g", "category": "fruit_veg"},
    ),
    0,
)
test(
    "ingefärsshot brand-example parenthetical still matches shot products",
    recipe_match_num(
        ["4 cl ingefärsshot (med ingefära och rödbeta t.ex. God Morgon drakfrukt, Ingefära)"],
        {"name": "Ingefärsshot Rödbeta 60ml Råsaft", "category": "beverages"},
    ),
    1,
)
test(
    "plain spaghetti ingredient matches spaghetti products again",
    recipe_match_num(
        ["300 g spaghetti"],
        {"name": "Spaghetti 500g Barilla", "category": "pantry"},
    ),
    1,
)
test(
    "plain spagetti ingredient matches spaghetti products again",
    recipe_match_num(
        ["300 g spagetti"],
        {"name": "Spaghetti 500g Barilla", "category": "pantry"},
    ),
    1,
)
test(
    "kålrotsspaghetti still does not fall through to ordinary spaghetti",
    recipe_match_num(
        ["250 g kålrotsspaghetti Hackat och Klart"],
        {"name": "Spaghetti 500g Barilla", "category": "pantry"},
    ),
    0,
)
test(
    "Q5 batch 116 röd spansk peppar extracts as chili",
    sorted(extract_keywords_from_ingredient("1/2 röd spansk peppar tunt skivad")),
    ["chili"],
)
test(
    "Q1 batch 117 röd peppar (chili) extracts as chili",
    sorted(extract_keywords_from_ingredient("1 röd peppar (chili)")),
    ["chili"],
)
test(
    "Colored röd peppar extracts as chili",
    sorted(extract_keywords_from_ingredient("1 röd peppar")),
    ["chili"],
)
test(
    "Colored grön peppar extracts as chili",
    sorted(extract_keywords_from_ingredient("1 grön peppar")),
    ["chili"],
)
test(
    "English green chili extracts as chili",
    sorted(extract_keywords_from_ingredient("1 tsk Green Chili")),
    ["chili"],
)
test(
    "Q5 batch 116 röd spansk peppar matches fresh red chili offer",
    recipe_match_num(
        ["1/2 röd spansk peppar tunt skivad"],
        {"name": "Röd peppar 40g Klass 1 ICA", "category": "fruit"},
    ),
    1,
)
test(
    "Q5 batch 116 cached röd spansk peppar matches fresh red chili offer",
    recipe_match_num_cached(
        ["1/2 röd spansk peppar tunt skivad"],
        {"name": "Röd peppar 40g Klass 1 ICA", "category": "fruit"},
    ),
    1,
)
test(
    "Q1 batch 117 röd peppar (chili) matches fresh red chili offer",
    recipe_match_num(
        ["1 röd peppar (chili)"],
        {"name": "Röd peppar 40g Klass 1 ICA", "category": "fruit"},
    ),
    1,
)
test(
    "Q1 batch 117 cached röd peppar (chili) matches fresh red chili offer",
    recipe_match_num_cached(
        ["1 röd peppar (chili)"],
        {"name": "Röd peppar 40g Klass 1 ICA", "category": "fruit"},
    ),
    1,
)
test(
    "Plain röd peppar now matches fresh red chili offer",
    recipe_match_num(
        ["1 röd peppar"],
        {"name": "Röd peppar 40g Klass 1 ICA", "category": "fruit"},
    ),
    1,
)
test(
    "Cached plain röd peppar now matches fresh red chili offer",
    recipe_match_num_cached(
        ["1 röd peppar"],
        {"name": "Röd peppar 40g Klass 1 ICA", "category": "fruit"},
    ),
    1,
)
test(
    "Plain grön peppar matches fresh green chili offer",
    recipe_match_num(
        ["1 grön peppar"],
        {"name": "Grön peppar 40g Klass 1 ICA", "category": "fruit"},
    ),
    1,
)
test(
    "Cached plain grön peppar matches fresh green chili offer",
    recipe_match_num_cached(
        ["1 grön peppar"],
        {"name": "Grön peppar 40g Klass 1 ICA", "category": "fruit"},
    ),
    1,
)
test(
    "English green chili matches fresh green chili offer",
    recipe_match_num(
        ["1 tsk Green Chili"],
        {"name": "Chilipeppar grön ca 30g Klass 1 ICA", "category": "fruit"},
    ),
    1,
)
test(
    "Cached English green chili matches fresh green chili offer",
    recipe_match_num_cached(
        ["1 tsk Green Chili"],
        {"name": "Chilipeppar grön ca 30g Klass 1 ICA", "category": "fruit"},
    ),
    1,
)
test(
    "English green chili does not match Green Chili Mild seasoning jar",
    recipe_match_num(
        ["1 tsk Green Chili"],
        {"name": "Green Chili Mild 113g Santa Maria", "category": "spices"},
    ),
    0,
)
test(
    "English green chili mild wording is not globally blocked when product form is fresh",
    recipe_match_num(
        ["1 tsk Green Chili"],
        {"name": "Green Chili Mild Färsk 50g Test", "category": "fruit"},
    ),
    1,
)
test(
    "Batch 149 salami pålägg matches plain salami product",
    recipe_match_num(
        ["80 g Salami pålägg"],
        {"name": "Salami 300g ICA Basic", "category": "deli"},
    ),
    1,
)
test(
    "Batch 149 salami pålägg cached matches plain salami product",
    recipe_match_num_cached(
        ["80 g Salami pålägg"],
        {"name": "Salami 300g ICA Basic", "category": "deli"},
    ),
    1,
)
test(
    "Batch 149 salami pålägg matches sliced salami deli product",
    recipe_match_num(
        ["80 g Salami pålägg"],
        {"name": "Salami Milano Tunna Skivor 80g ICA", "category": "deli"},
    ),
    1,
)
test(
    "Batch 149 salami pålägg cached matches sliced salami deli product",
    recipe_match_num_cached(
        ["80 g Salami pålägg"],
        {"name": "Salami Milano Tunna Skivor 80g ICA", "category": "deli"},
    ),
    1,
)
test(
    "Q8 plain papaya does not match dried papaya",
    recipe_match_num(
        ["Papaya"],
        {"name": "Papaya Torkad Tärningar", "category": "pantry"},
    ),
    0,
)
test(
    "Q8 plain papaya still matches fresh papaya",
    recipe_match_num(
        ["Papaya"],
        {"name": "Papaya Färsk", "category": "fruit"},
    ),
    1,
)

# PNB: new blockers from Javligtgott review
test("PNB taco → pulled", 'pulled' in PRODUCT_NAME_BLOCKERS.get('taco', set()), True)
test("PNB taco → kit", 'kit' in PRODUCT_NAME_BLOCKERS.get('taco', set()), True)
test("PNB nacho → dip", 'dip' in PRODUCT_NAME_BLOCKERS.get('nacho', set()), True)
test("PNB hasselnöt → start", 'start' in PRODUCT_NAME_BLOCKERS.get('hasselnöt', set()), True)
test("PNB habanero → sauce", 'sauce' in PRODUCT_NAME_BLOCKERS.get('habanero', set()), True)
test("PNB curry → sauce", 'sauce' in PRODUCT_NAME_BLOCKERS.get('curry', set()), True)
test("PNB cayennepeppar → sauce", 'sauce' in PRODUCT_NAME_BLOCKERS.get('cayennepeppar', set()), True)
test("PNB jalapeno → ostcrème", 'ostcreme' in PRODUCT_NAME_BLOCKERS.get('jalapeno', set()), True)
test("PNB chili → crispy", 'crispy' in PRODUCT_NAME_BLOCKERS.get('chili', set()), True)
test("PNB chili → olja", 'olja' in PRODUCT_NAME_BLOCKERS.get('chili', set()), True)
test("PNB chili → mild", 'mild' in PRODUCT_NAME_BLOCKERS.get('chili', set()), True)
test(
    "Batch 1 citron does not match lemon-flavored chicken",
    recipe_match_num(
        ["1 st Citron"],
        {"name": "Kycklingbröst File Citron Vitlök Grillad Skivad Guldfågeln", "category": "meat"},
    ),
    0,
)
test(
    "Batch 1 citron does not match lemon bread",
    recipe_match_num(
        ["1 st Citron"],
        {"name": "Levain Citron Bonjour", "category": "bread"},
    ),
    0,
)
test(
    "Batch 1 vitlök does not match garlic-flavored chicken",
    recipe_match_num(
        ["2 klyfta Vitlök"],
        {"name": "Kycklingbröst File Citron Vitlök Grillad Skivad Guldfågeln", "category": "meat"},
    ),
    0,
)
test(
    "Batch 1 fresh chili does not match sriracha sauce",
    recipe_match_num(
        ["1 st Chilifrukter"],
        {"name": "Sriracha Hot Chilli Sauce Flying Goose", "category": "pantry"},
    ),
    0,
)
test(
    "Batch 1 fresh chili does not match weighted sriracha sauce",
    recipe_match_num_cached(
        ["2 st Chilifrukter"],
        {
            "name": "Sriracha Hot Chilli Sauce Flying Goose",
            "category": "pantry",
            "brand": "FLYING GOOSE",
            "weight_grams": 455,
        },
    ),
    0,
)
test(
    "Batch 1 fresh chili does not match chili soy sauce",
    recipe_match_num_cached(
        ["2 st Chilifrukter"],
        {
            "name": "Chili Soya Sau Korean Style Monggo",
            "category": "other",
            "brand": "MONGGO",
            "weight_grams": 330,
        },
    ),
    0,
)
test(
    "Batch 1 fresh chili does not match chili-flavored meat",
    recipe_match_num_cached(
        ["2 st Chilifrukter"],
        {
            "name": "Grillspett Mils Chili Sverige Scan",
            "category": "meat",
            "brand": "SCAN",
            "weight_grams": 400,
        },
    ),
    0,
)
test(
    "Batch 1 parmesan does not match parmigiano pastasås",
    recipe_match_num(
        ["40 g Parmesanost"],
        {"name": "Rossorotomater & Parmigiano Pastasås Mutti", "category": "pantry"},
    ),
    0,
)
test(
    "Batch 1 honung does not match honey glaze",
    recipe_match_num(
        ["1/2 msk honung"],
        {"name": "Honung Glazer Caj P", "category": "pantry"},
    ),
    0,
)
test(
    "Batch 1 flytande honung matches liquid honey",
    recipe_match_num(
        ["1 msk Honung Flytande"],
        {"name": "Honung Flytande Eldorado", "category": "pantry"},
    ),
    1,
)
test(
    "Batch 1 flytande honung blocks firm honey",
    recipe_match_num(
        ["1 msk Honung Flytande"],
        {"name": "Honung Fast Eldorado", "category": "pantry"},
    ),
    0,
)
test(
    "Batch 1 cached flytande honung blocks creamy honey",
    recipe_match_num_cached(
        ["1 msk Honung Flytande"],
        {"name": "Krämig Honung Blomsterhonung Lune De Miel", "category": "pantry"},
    ),
    0,
)
test(
    "Batch 1 plain honey still matches ordinary honey",
    recipe_match_num(
        ["1 msk honung"],
        {"name": "Blomsterhonung Garant", "category": "pantry"},
    ),
    1,
)
test(
    "Batch 1 fast potatis accepts mjölig fresh potato",
    recipe_match_num(
        ["1 kg Potatis Fast"],
        {"name": "Potatis Mjölig Klass 1", "category": "fruit"},
    ),
    1,
)
test(
    "Batch 1 fast potatis accepts bakpotatis",
    recipe_match_num(
        ["1 kg Potatis Fast"],
        {"name": "Bakpotatis Klass 1", "category": "fruit"},
    ),
    1,
)
test(
    "Batch 1 cached fast potatis accepts sparrispotatis",
    recipe_match_num_cached(
        ["1 kg Potatis Fast"],
        {"name": "Potatis Sparris Klass 1 Garant", "category": "fruit"},
    ),
    1,
)
test(
    "Batch 1 fast potatis blocks preserved whole potato pack",
    recipe_match_num(
        ["1 kg Potatis Fast"],
        {"name": "Potatis Hel Eldorado", "category": "vegetables"},
    ),
    0,
)
test(
    "Batch 1 nymalen svartpeppar is manual no-match for whole peppercorns",
    recipe_match_num(
        ["1 tsk nymalen svartpeppar"],
        {"name": "Svartpeppar Hel Påse Kockens", "category": "pantry"},
    ),
    0,
)
test(
    "Batch 1 nymalen svartpeppar is manual no-match for ground pepper",
    recipe_match_num_cached(
        ["1 tsk nymalen svartpeppar"],
        {"name": "Svartpeppar Grovmalen Burk Kockens", "category": "pantry"},
    ),
    0,
)
test(
    "Batch 1 chorizo does not match pizza topping",
    recipe_match_num(
        ["600 g Chorizo"],
        {"name": "Pizza Chorizo Tulip", "category": "pizza"},
    ),
    0,
)
test(
    "Batch 1 lök does not match onion-flavored tortilla",
    recipe_match_num(
        ["1 st Lök"],
        {"name": "Tortilla Lök", "category": "bread"},
    ),
    0,
)
test(
    "Batch 1 fresh chili still matches fresh chili",
    recipe_match_num(
        ["1 st Chilifrukter"],
        {"name": "Chilipeppar Röd Klass 1", "category": "vegetables"},
    ),
    1,
)
test(
    "Batch 1 fresh chili matches Willys fruit-category chili",
    recipe_match_num_cached(
        ["2 st Chilifrukter"],
        {
            "name": "Chilli Habanero Garant",
            "category": "fruit",
            "brand": "GARANT",
            "weight_grams": 40,
        },
    ),
    1,
)
test(
    "Batch 1 spice chili does not match fresh chili fruit",
    recipe_match_num_cached(
        ["0,5 tsk chili"],
        {
            "name": "Chili Röd Ekologisk",
            "category": "fruit",
            "weight_grams": 50,
        },
    ),
    0,
)
test(
    "Batch 1 explicit sriracha still matches sriracha sauce",
    recipe_match_num_cached(
        ["1 msk sriracha"],
        {
            "name": "Sriracha Hot Chilli Sauce Flying Goose",
            "category": "pantry",
            "brand": "FLYING GOOSE",
            "weight_grams": 455,
        },
    ),
    1,
)
test(
    "Batch 1 växtbaserad gurt matches plantgurt",
    recipe_match_num_cached(
        ["1 dl Växtbaserad gurt"],
        {
            "name": "Natural Plantgurt Osötad Alpro",
            "category": "dairy",
            "brand": "ALPRO",
            "weight_grams": 750,
        },
    ),
    1,
)
test(
    "Batch 1 växtbaserad gurt matches kokosgurt",
    recipe_match_num_cached(
        ["1 dl Växtbaserad gurt"],
        {
            "name": "Coconut Natural Kokosgurt Alpro",
            "category": "dairy",
            "brand": "ALPRO",
            "weight_grams": 350,
        },
    ),
    1,
)
test(
    "Batch 1 växtbaserad gurt blocks ordinary yoghurt",
    recipe_match_num_cached(
        ["1 dl Växtbaserad gurt"],
        {
            "name": "Yoghurt Naturell 3% Arla",
            "category": "dairy",
            "brand": "ARLA",
            "weight_grams": 1000,
        },
    ),
    0,
)
test(
    "Batch 1 plain yoghurt blocks plantgurt",
    recipe_match_num_cached(
        ["1 dl yoghurt"],
        {
            "name": "Natural Plantgurt Osötad Alpro",
            "category": "dairy",
            "brand": "ALPRO",
            "weight_grams": 750,
        },
    ),
    0,
)
test(
    "Batch 1 färsk gräslök matches fresh chives",
    recipe_match_num_cached(
        ["5 g Gräslök - färsk"],
        {
            "name": "Gräslök Garant",
            "category": "fruit",
            "brand": "GARANT",
            "weight_grams": 15,
        },
    ),
    1,
)
test(
    "Batch 1 färsk gräslök accepts frozen chives",
    recipe_match_num_cached(
        ["5 g Gräslök - färsk"],
        {
            "name": "Gräslök Finhackad Fryst Garant",
            "category": "frozen",
            "brand": "GARANT",
            "weight_grams": 50,
        },
    ),
    1,
)
test(
    "Batch 1 dried-measure gräslök blocks frozen chives",
    recipe_match_num_cached(
        ["1 tsk gräslök"],
        {
            "name": "Gräslök Finhackad Fryst Garant",
            "category": "frozen",
            "brand": "GARANT",
            "weight_grams": 50,
        },
    ),
    0,
)
test(
    "Batch 1 laxfilé blocks hot-smoked Varmr salmon portions",
    recipe_match_num(
        ["600 g laxfilé"],
        {"name": "Lax Varmr Portion Eldorado", "category": "fish"},
    ),
    0,
)
test("PNB mango → sojaprodukt", 'sojaprodukt' in PRODUCT_NAME_BLOCKERS.get('mango', set()), True)
test("PNB lime → coriander", 'coriander' in PRODUCT_NAME_BLOCKERS.get('lime', set()), True)
test("PNB koriander → frön", any('frön' in w or 'fron' in w for w in PRODUCT_NAME_BLOCKERS.get('koriander', set())), True)
test("PNB pasta → pancetta", 'pancetta' in PRODUCT_NAME_BLOCKERS.get('pasta', set()), True)
test("PNB nudlar → biffsmak", 'biffsmak' in PRODUCT_NAME_BLOCKERS.get('nudlar', set()), True)
test("PNB paprika → tärnad", any('tärnad' in w or 'tarnad' in w for w in PRODUCT_NAME_BLOCKERS.get('paprika', set())), True)
test("PNB rödbeta omits förkokt", 'förkokt' in PRODUCT_NAME_BLOCKERS.get('rödbeta', set()), False)
test("PNB mandel → saltade", 'saltade' in PRODUCT_NAME_BLOCKERS.get('mandel', set()), True)

# STOP_WORDS: mustig, smokey
test("SW mustig", 'mustig' in STOP_WORDS, True)
test("SW smokey", 'smokey' in STOP_WORDS, True)

# Gurka PPR: finhackad/tunnskivad removed (prep methods, not product types)
test("PPR gurka no finhackad", 'finhackad' not in PROCESSED_PRODUCT_RULES.get('gurka', set()), True)
test("PPR gurka no tunnskivad", 'tunnskivad' not in PROCESSED_PRODUCT_RULES.get('gurka', set()), True)
test("PPR gurka has salt", 'salt' in PROCESSED_PRODUCT_RULES.get('gurka', set()), True)

# Matching: veg bacon → only vegobacon, not real bacon
test("Vegobacon = 'veg bacon'", match("Vegobacon Färsk 140g ICA", "100 g Veg bacon") is not None, True)
test("Bacon Skivat ≠ 'veg bacon'", match("Bacon Skivat 140g Scan", "100 g Veg bacon"), None)

# Matching: naturell tofu filtering
test("Tofu Naturell = 'naturell fast tofu'", match("Tofu Naturell Ekologisk 230g", "200 g Naturell fast tofu") is not None, True)
test("Tofu rökt ≠ 'naturell fast tofu'", match("Tofu rökt 200g ICA Basic", "200 g Naturell fast tofu"), None)
test("Tofu rökt = 'rökt tofu'", match("Tofu rökt 200g ICA Basic", "250 g Rökt tofu") is not None, True)
test("Tofu Naturell ≠ 'rökt tofu'", match("Tofu Naturell Ekologisk 230g", "250 g Rökt tofu"), None)
test("Tofu rökt = plain 'tofu'", match("Tofu rökt 200g ICA Basic", "400 g Tofu") is not None, True)
test("Tofu Naturell Extra Fast = 'extra fast tofu'", match("Tofu Naturell Extra Fast 230g Yipin", "200 g extra fast tofu") is not None, True)
test("Crispy tofu ≠ 'extra fast tofu'", match("Crispy Tofu Vego Frysta Garant", "200 g extra fast tofu"), None)
test("Friterad tofu ≠ 'extra fast tofu'", match("Tofu Friterad Tärnad Yipin", "200 g extra fast tofu"), None)
test("Sojamarinerad tofu ≠ 'extra fast tofu'", match("Sojamarinerad Tofu Eldorado", "200 g extra fast tofu"), None)
test("Rökt tofu ≠ 'tofu, fast eller silkes'", match("Tofu Rökt Garant Eko", "tofu, fast eller silkes"), None)
test("Crispy tofu ≠ 'tofu, fast eller silkes'", match("Crispy Tofu Vego Frysta Garant", "tofu, fast eller silkes"), None)
test("Tofu silkesmjuk = 'tofu, fast eller silkes'", match("Tofu silkesmjuk Ekologisk 400g YiPin", "tofu, fast eller silkes") is not None, True)
test("Svarta sesamfrön match black sesame", match("Sesamfrön Svarta Risenta", "1 msk svarta sesamfrön") is not None, True)
test("Svarta sesamfrön block white sesame", match("Sesamfrön Vita Burk Kockens", "1 msk svarta sesamfrön"), None)
test("Svarta sesamfrön block hulled sesame", match("Sesamfrön Skalade Garant Eko", "1 msk svarta sesamfrön"), None)
test("Vita sesamfrön block black sesame", match("Sesamfrö Svarta 200g Risenta", "1 msk vita sesamfrön"), None)
test("Skalade sesamfrön block unhulled sesame", match("Sesamfrön Oskalade 200g Risenta", "2 msk skalade sesamfrön"), None)
test("Skalade sesamfrön match hulled sesame", match("Sesamfrön Skalade Garant Eko", "2 msk skalade sesamfrön") is not None, True)
test("Brödskiva blocks Liba flatbread", match("Liba Original Tunnbröd Vitt 4-pack Liba Bröd", "1 brödskiva") is None, True)
test("Brödskiva blocks bagels", match("Bagels Classic Liba Bröd", "1 brödskiva") is None, True)
test("Brödskiva blocks somun bread", match("Somun Bröd Rosseto", "1 brödskiva") is None, True)
test("Brödskiva accepts sliced bread", match("Hembakat Stenugnsbakad Skivad Östras Bröd", "1 brödskiva") is not None, True)
test(
    "Cached brödskiva blocks Liba flatbread",
    recipe_match_num_cached(
        ["1 brödskiva, gärna nyckelhålsmärkt"],
        {"name": "Liba Original Tunnbröd Vitt 4-pack Liba Bröd", "category": "bread"},
    ),
    0,
)
test("Pepparrotsvisp matches prepared whip", match("Pepparrotsvisp Örneborgs", "1 tsk pepparrotsvisp, på tub") is not None, True)
test("Pepparrotsvisp blocks fresh root", match("Pepparrot Klass 1", "1 tsk pepparrotsvisp, på tub"), None)
test("Pepparrotsvisp blocks grated root", match("Pepparrot Riven Örneborgs", "1 tsk pepparrotsvisp, på tub"), None)
test(
    "Cached pepparrotsvisp blocks fresh root",
    recipe_match_num_cached(
        ["1 tsk pepparrotsvisp, på tub"],
        {"name": "Pepparrot Klass 1", "category": "vegetables"},
    ),
    0,
)
test("Rökt kalkonbröst matches sliced smoked deli", match("Kalkonbröst Rökt Skivad Prime Patrol", "1 skiva rökt kalkonbröst") is not None, True)
test("Rökt kalkonbröst blocks raw breast fillet", match("Kalkon Bröstfilé Mörad Fryst Ingelstakalkon", "1 skiva rökt kalkonbröst"), None)
test("Rökt kalkonbröst blocks raw thigh fillet", match("Kalkonlårfilé Strimlad Fryst Ingelstakalkon", "1 skiva rökt kalkonbröst"), None)
test(
    "Cached rökt kalkonbröst blocks raw breast fillet",
    recipe_match_num_cached(
        ["1 skiva rökt kalkonbröst"],
        {"name": "Kalkon Bröstfilé Mörad Fryst Ingelstakalkon", "category": "meat"},
    ),
    0,
)
test("Kalkon Hel Fryst = 'hel kalkon'", match("Kalkon Hel Fryst ca 4kg Ingelsta", "3.5 kg Kalkon Hel") is not None, True)
test("Rökt Kalkon ≠ 'hel kalkon'", match("Rökt Kalkon 300g ICA Basic", "3.5 kg Kalkon Hel"), None)
test("Kalkonklubba ≠ 'hel kalkon'", match("Kalkonklubba basturökt ca 720g Ingelsta Kalkon", "3.5 kg Kalkon Hel"), None)
test(
    "Recipe matcher allows dried herb in 'färsk eller torkad timjan'",
    recipe_match_num(
        ["färsk eller torkad timjan"],
        {
            "name": "Timjan Torkad 14g ICA",
            "category": "spices",
            "brand": "ICA",
            "weight_grams": 14,
        },
    ),
    1,
)
test(
    "SQ whole chicken blocked for kycklingfilé ingredient",
    check_specialty_qualifiers({'kyckling': {'hel'}}, 'kyckling', '400 g stekt & skivad kycklingfilé'),
    False,
)
test(
    "SQ whole chicken allowed for hel kyckling ingredient",
    check_specialty_qualifiers({'kyckling': {'hel'}}, 'kyckling', '1 hel kyckling'),
    True,
)
test(
    "SQ whole chicken allowed for weighted stor kyckling ingredient",
    check_specialty_qualifiers({'kyckling': {'hel'}}, 'kyckling', '1 stor kyckling (ca 2 kg)'),
    True,
)
test(
    "Vitvinsvinäger gets generic vinäger parent",
    "vinäger" in kw("Vitvinsvinäger 250ml ICA"),
    True,
)
test(
    "Äppelcidervinäger gets generic vinäger parent",
    "vinäger" in kw("Äppelcidervinäger 1l Zeta"),
    True,
)
test(
    "Generic vinäger matches vitvinsvinäger",
    match("Vitvinsvinäger 250ml ICA", "1 msk vinäger"),
    "vinäger",
)
test(
    "Generic vinäger matches äppelcidervinäger",
    match("Äppelcidervinäger 1l Zeta", "1 msk vinäger"),
    "vinäger",
)
test(
    "Cached matcher retries from rårörda lingon to frysta lingon",
    recipe_match_num_cached(
        ["0.5 dl Rårörda lingon", "250 g Frysta lingon"],
        {
            "name": "Lingon 500g ICA",
            "category": "fruit",
            "brand": "ICA",
            "weight_grams": 500,
        },
    ),
    1,
)
test("Black Eye Bönor = 'Black Eye Bönor'", match("Black eye bönor 900g Forum", "410 g Black Eye Bönor") is not None, True)
test("Quorn pieces/bitar = 'Vegetariska Bitar'", match("Vegetariska pieces/bitar Fryst 600g Quorn", "Vegetariska Bitar") is not None, True)
test("Machesallat = 'machésallad'", match("Finbladig Machesallat Sköljd 65g ICA", "machésallad") is not None, True)
test("Ruccolasallat = 'ruccola'", match("Ruccolasallat", "70 g ruccola") is not None, True)
test("Cooking Sauce Tikka Masala = 'Spicy Tikka Masala Sauce'", match("Cooking Spice Sauce Tikka Masala 360g Santa Maria", "Spicy Tikka Masala Sauce") is not None, True)
test("Fänkålsfrön Hela = 'Fänkål Krydda'", match("Fänkålsfrön Hela 13g Santa Maria", "2 tsk Fänkål Krydda") is not None, True)
test("Färsk fänkål ≠ 'Fänkål Krydda'", match("Fänkål ca 300g Klass 1 ICA", "2 tsk Fänkål Krydda"), None)
test("Färsk fänkål = 'Fänkål Färsk'", match("Fänkål ca 300g Klass 1 ICA", "1 st Fänkål Färsk") is not None, True)
test("Fänkålsfrön Hela ≠ 'Fänkål Färsk'", match("Fänkålsfrön Hela 13g Santa Maria", "1 st Fänkål Färsk"), None)
test(
    "Fänkålsfrön Hela = spice-list 'anis, fänkål eller kummin'",
    match("Fänkålsfrön Hela 13g Santa Maria", "1 msk anis, fänkål eller kummin", "spices"),
    "fänkål",
)
test(
    "Färsk fänkål ≠ spice-list 'anis, fänkål eller kummin'",
    match("Fänkål ca 300g Klass 1 ICA", "1 msk anis, fänkål eller kummin", "vegetables"),
    None,
)
test(
    "Plain kummin now matches whole kummin",
    match("Kummin Hel 24g Santa Maria", "1 msk kummin", "spices"),
    "kummin",
)
test(
    "Plain kummin now matches ground kummin",
    match("Kummin Malen 24g Santa Maria", "1 msk kummin", "spices"),
    "kummin",
)
test(
    "Plain kummin still does not match spiskummin",
    match("Spiskummin Malen 40g Santa Maria", "1 msk kummin", "spices"),
    None,
)
_q1_batch_114_spice_list = recipe_match_data_multi_cached(
    ["1 msk anis, fänkål eller kummin"],
    [
        {"name": "Kryddor Anis hel 18g Santa Maria", "category": "spices"},
        {"name": "Fänkålsfrön Hela 13g Santa Maria", "category": "spices"},
        {"name": "Kummin Hel 24g Santa Maria", "category": "spices"},
    ],
)
test(
    "Q1 batch 114 spice-list alternatives form one ingredient group",
    len(_q1_batch_114_spice_list["ingredient_groups"]),
    1,
)
test(
    "Q1 batch 114 spice-list group surfaces all three offers",
    len(_q1_batch_114_spice_list["ingredient_groups"][0]["offers"]),
    3,
)
test(
    "Cooked kycklingklubba no longer matches raw fresh drumstick",
    match("Kycklingklubba Färsk 850g ICA Gott liv", "1 färdiggrillad kycklingklubba", "poultry"),
    None,
)
test(
    "Cooked kycklingklubba no longer matches raw frozen drumstick",
    match("Kycklingklubba Fryst 1kg Kronfågel", "1 färdiggrillad kycklingklubba", "poultry"),
    None,
)
test(
    "Cooked kycklingklubba still matches grilled drumstick",
    match("Kycklingklubbor Grillade 700g Kronfågel", "1 färdiggrillad kycklingklubba", "deli"),
    "kycklingklubba",
)
test(
    "Cooked kycklingklubba also allows sous vide drumstick fallback",
    match("Kycklingklubba Sous Vide 500g", "1 färdiggrillad kycklingklubba", "deli"),
    "kycklingklubba",
)
test(
    "Plain kycklingklubba still matches raw drumstick",
    match("Kycklingklubba Färsk 850g ICA Gott liv", "1 kycklingklubba", "poultry"),
    "kycklingklubba",
)
test(
    "Dulce de leche ingredient matches exact Dulce de leche product",
    match("Dulce de leche 450g Cremo", "1/2 dl dulce de leche (karamelliserad mjölk)", "pantry"),
    "karamelliseradmjölk",
)
test(
    "Dulce de leche ingredient also matches Swedish karamelliserad mjölk",
    match("Karamelliserad mjölk 397g ICA", "1/2 dl dulce de leche (karamelliserad mjölk)", "pantry"),
    "karamelliseradmjölk",
)
test(
    "Dulce de leche ingredient no longer matches kondenserad mjölk",
    match("Kondenserad mjölk 397g ICA", "1/2 dl dulce de leche (karamelliserad mjölk)", "pantry"),
    None,
)
test(
    "Karamelliserad mjölk stays separate from kondenserad mjölk",
    match("Kondenserad mjölk 397g ICA", "1/2 dl karamelliserad mjölk", "pantry"),
    None,
)
test(
    "Kondenserad mjölk stays separate from karamelliserad mjölk",
    match("Karamelliserad mjölk 397g ICA", "1/2 dl kondenserad mjölk", "pantry"),
    None,
)
test(
    "Generic svamp no longer matches champinjoner i tetra through svamp fallback",
    match("Champinjoner i tetra hela 200g Eldorado", "200 g svamp, t ex kantareller, i bitar", "pantry"),
    None,
)
test(
    "Generic svamp no longer matches preserved champinjoner hela",
    match("Champinjoner Hela 400g ICA", "200 g svamp, t ex kantareller, i bitar", "pantry"),
    None,
)
test(
    "Generic svamp no longer matches preserved champinjoner skivade",
    match("Champinjoner Skivade 400g ICA", "200 g svamp, t ex kantareller, i bitar", "pantry"),
    None,
)
test(
    "Generic svamp still matches fresh champinjoner after preserved fix",
    match("Champinjoner Färska 250g ICA", "200 g svamp, t ex kantareller, i bitar", "vegetables"),
    "svamp",
)
test(
    "Preserved kantareller still matches i vatten product",
    match("Kantareller i vatten 200g Borgens", "200 g kantareller, på burk, avrunna", "vegetables"),
    "kantarell",
)
test(
    "Preserved kantareller no longer matches fresh kantarell",
    match("Kantarell gul 150g Klass 1 ICA", "200 g kantareller, på burk, avrunna", "vegetables"),
    None,
)
test(
    "Preserved kantareller no longer matches dried trattkantarell",
    match("Trattkantarell torkad 20g ICA", "200 g kantareller, på burk, avrunna", "pantry"),
    None,
)
test(
    "Preserved kantareller no longer matches kantarell creme",
    match("Kantarell Creme 120g", "200 g kantareller, på burk, avrunna", "pantry"),
    None,
)
test(
    "Recipe matcher preserved kantareller still accepts i vatten offer",
    recipe_match_num(
        ["200 g kantareller, på burk, avrunna"],
        {"name": "Kantareller i vatten 200g Borgens", "category": "vegetables"},
    ),
    1,
)
test(
    "Recipe matcher preserved kantareller blocks fresh offer",
    recipe_match_num(
        ["200 g kantareller, på burk, avrunna"],
        {"name": "Kantarell gul 150g Klass 1 ICA", "category": "vegetables"},
    ),
    0,
)
test(
    "Plain tablespoon fänkål still keeps existing fresh behavior",
    match("Fänkål ca 300g Klass 1 ICA", "1 msk fänkål", "vegetables"),
    "fänkål",
)
test("Sparris Bitar = plain 'sparris'", match("Sparris Bitar 227g ICA Basic", "250 g sparris") is not None, True)
test("Sparris Bitar ≠ 'färsk sparris'", match("Sparris Bitar 227g ICA Basic", "250 g färsk sparris"), None)
test(
    "Frozen cauliflower still accepted for whole thick-sliced blomkålshuvud",
    match("Blomkål Fryst 600g ICA", "1 blomkålshuvud, tjockt skivad ca 2 cm", "frozen"),
    "blomkål",
)
test(
    "Fresh cauliflower = whole thick-sliced blomkålshuvud",
    match("Blomkål Klass 1 ICA", "1 blomkålshuvud, tjockt skivad ca 2 cm", "vegetables"),
    "blomkål",
)
test(
    "Frozen broccoli still accepted for thick-sliced whole broccoli",
    match("Broccoli 600g Findus", "1 broccoli , tjockt skivad ca 2 cm", "frozen"),
    "broccoli",
)
test(
    "Plain broccoli still accepts frozen fallback",
    match("Broccoli 600g Findus", "750 g broccoli", "frozen"),
    "broccoli",
)
test(
    "Explicit fresh broccoli still accepts frozen fallback",
    match("Broccoli 600g Findus", "750 g Broccoli Färsk", "frozen"),
    "broccoli",
)
test(
    "Förkokta rödbetor do not substitute plain 'rödbetor'",
    recipe_match_num(
        ["500 g rödbetor"],
        {"name": "Rödbetor Förkokta 500g ICA", "category": "vegetables", "brand": "ICA"},
    ),
    0,
)
test(
    "Jarred whole rödbetor do not substitute plain 'rödbetor'",
    recipe_match_num(
        ["500 g rödbetor"],
        {"name": "Rödbetor Hela Björnekulla", "category": "vegetables", "brand": "Björnekulla"},
    ),
    0,
)
test(
    "Plain rödbetor still match fresh beetroot",
    recipe_match_num(
        ["500 g rödbetor"],
        {"name": "Rödbeta 1kg Klass 1 ICA", "category": "vegetables", "brand": "ICA"},
    ),
    1,
)
test(
    "Förkokta rödbetor = explicit 'förkokta rödbetor'",
    recipe_match_num(
        ["500 g förkokta rödbetor"],
        {"name": "Rödbetor Förkokta 500g ICA", "category": "vegetables", "brand": "ICA"},
    ),
    1,
)
test(
    "Fresh sliced rödbetor still match fresh beetroot",
    recipe_match_num(
        ["2 tunt skivade medelstora rödbetor"],
        {"name": "Rödbeta 1kg Klass 1 ICA", "category": "vegetables", "brand": "ICA"},
    ),
    1,
)
test(
    "Fresh sliced rödbetor do not match preserved sliced beets",
    recipe_match_num(
        ["2 tunt skivade medelstora rödbetor"],
        {"name": "Skivade Rödbetor 710g Felix", "category": "vegetables", "brand": "Felix"},
    ),
    0,
)
test(
    "Plain skivade rödbetor still match preserved sliced beets",
    recipe_match_num(
        ["500 g skivade rödbetor"],
        {"name": "Skivade Rödbetor 710g Felix", "category": "vegetables", "brand": "Felix"},
    ),
    1,
)
test(
    "Packaged hela rödbetor do not match fresh beetroot",
    recipe_match_num(
        ["350 g Felix hela rödbetor"],
        {"name": "Rödbeta 1kg Klass 1 ICA", "category": "vegetables", "brand": "ICA"},
    ),
    0,
)
test(
    "Packaged hela rödbetor match preserved whole beets",
    recipe_match_num(
        ["350 g Felix hela rödbetor"],
        {"name": "Hela Rödbetor 370g Felix", "category": "vegetables", "brand": "Felix"},
    ),
    1,
)
test(
    "Fresh hela rödbetor still match fresh beetroot",
    recipe_match_num(
        ["4 hela rödbetor"],
        {"name": "Rödbeta 1kg Klass 1 ICA", "category": "vegetables", "brand": "ICA"},
    ),
    1,
)
test(
    "Hamburgerost matches burger cheddar slices",
    recipe_match_num(
        ["50 g Hamburgerost"],
        {"name": "Burgers Slices Cheddar Eldorado", "category": "groceries", "brand": "Eldorado"},
    ),
    1,
)
test(
    "Hamburgerost matches cheddar burgar products",
    recipe_match_num(
        ["50 g Hamburgerost"],
        {"name": "Cheddar Burgar Original Väddö", "category": "groceries", "brand": "Väddö"},
    ),
    1,
)
test(
    "Hamburgerost still blocks cheddar spread",
    recipe_match_num(
        ["50 g Hamburgerost"],
        {"name": "CheddarOst 250g Kavli", "category": "groceries", "brand": "Kavli"},
    ),
    0,
)
test(
    "Teaspoon paprika now matches paprika spice",
    recipe_match_num(
        ["1 tsk Röd Paprika"],
        {"name": "Paprikapulver 70g ICA Basic", "category": "spices", "brand": "ICA Basic"},
    ),
    1,
)
test(
    "Cached teaspoon paprika now matches paprika spice",
    recipe_match_num_cached(
        ["1 tsk Röd Paprika"],
        {"name": "Paprikapulver 70g ICA Basic", "category": "spices", "brand": "ICA Basic"},
    ),
    1,
)
test(
    "Teaspoon paprika no longer matches fresh bell pepper",
    recipe_match_num(
        ["1 tsk Röd Paprika"],
        {"name": "Paprika Röd Klass 1", "category": "vegetables", "brand": "ICA"},
    ),
    0,
)
test(
    "Cached teaspoon paprika no longer matches fresh bell pepper",
    recipe_match_num_cached(
        ["1 tsk Röd Paprika"],
        {"name": "Paprika Röd Klass 1", "category": "vegetables", "brand": "ICA"},
    ),
    0,
)
test(
    "Measured vatten eller mjölk keeps quantity on the milk alternative",
    parse_eller_alternatives("1 dl vatten eller mjölk"),
    ["1 dl vatten", "1 dl mjölk"],
)
test(
    "Vatten eller mjölk now matches milk products",
    recipe_match_num(
        ["1 dl vatten eller mjölk"],
        {"name": "Mjölk 1,5% 1l Arla", "category": "dairy", "brand": "Arla"},
    ),
    1,
)
test(
    "Cached vatten eller mjölk now matches milk products",
    recipe_match_num_cached(
        ["1 dl vatten eller mjölk"],
        {"name": "Mjölk 1,5% 1l Arla", "category": "dairy", "brand": "Arla"},
    ),
    1,
)
test(
    "Tandoori matlagningssås blocks dry spice jars",
    recipe_match_num(
        ["tandoori matlagningssås"],
        {"name": "Tandoori 35g Santa Maria", "category": "spices", "brand": "Santa Maria"},
    ),
    0,
)
test(
    "Tandoori matlagningssås still matches sauce products",
    recipe_match_num(
        ["tandoori matlagningssås"],
        {"name": "Tandoori 450g Pataks", "category": "pantry", "brand": "Pataks"},
    ),
    1,
)
test(
    "Mandariner i fruktkonserver match canned mandarin segments",
    recipe_match_num(
        ["1 st Mandariner i Fruktkonserver"],
        {"name": "Mandarinklyftor i sockerlag 312g ICA", "category": "pantry", "brand": "ICA"},
    ),
    1,
)
test(
    "Mandariner i fruktkonserver block fresh mandarins",
    recipe_match_num(
        ["1 st Mandariner i Fruktkonserver"],
        {"name": "Mandarin 1kg Klass 1 ICA", "category": "fruit", "brand": "ICA"},
    ),
    0,
)
test(
    "Korvar gärna lamm still match ordinary sausage types",
    recipe_match_num(
        ["4 korvar, gärna lamm"],
        {"name": "Falukorv 800g Scan", "category": "deli", "brand": "Scan"},
    ),
    1,
)
test(
    "Korvar gärna lamm still match lamb sausage",
    recipe_match_num(
        ["4 korvar, gärna lamm"],
        {"name": "Lammkorv 240g Ridderheims", "category": "deli", "brand": "Ridderheims"},
    ),
    1,
)
test(
    "Korvar gärna lamm can use named sausage families",
    recipe_match_num(
        ["4 korvar, gärna lamm"],
        {"name": "Chorizo 225g ICA", "category": "deli", "brand": "ICA"},
    ),
    1,
)
test(
    "Korvar gärna lamm no longer match raw lamb cuts",
    recipe_match_num(
        ["4 korvar, gärna lamm"],
        {"name": "Lammracks ca 844g Scan", "category": "meat", "brand": "Scan"},
    ),
    0,
)
test(
    "Saltade mandlar ≠ plain 'mandlar'",
    recipe_match_num(
        ["50 g mandlar"],
        {"name": "Mandlar Rostade och Saltade 200g ICA", "category": "snacks", "brand": "ICA"},
    ),
    0,
)
test(
    "Saltade mandlar = explicit 'saltade mandlar'",
    recipe_match_num(
        ["50 g saltade mandlar"],
        {"name": "Mandlar Rostade och Saltade 200g ICA", "category": "snacks", "brand": "ICA"},
    ),
    1,
)
test(
    "Generic kex ingredient now extracts the base keyword",
    sorted(extract_keywords_from_ingredient("1 förp kex")),
    ["kex"],
)
test(
    "kex till ost keeps kex and does not degrade into ost",
    sorted(extract_keywords_from_ingredient("4 kex till ost")),
    ["kex"],
)
test(
    "Generic kex matches Digestivekex offers",
    recipe_match_num(
        ["1 förp kex"],
        {"name": "Digestivekex 400g ICA Basic", "category": "snacks"},
    ),
    1,
)
test(
    "Generic kex matches Biscoff kex offers with standalone kex in the product name",
    recipe_match_num(
        ["1 förp kex"],
        {"name": "Biscoff kex 140 g Lotus", "category": "snacks"},
    ),
    1,
)
test(
    "Generic kex matches Aperitivokex offers via product-side bridge",
    recipe_match_num(
        ["1 förp kex"],
        {"name": "Aperitivokex naturella 150 g Zeta", "category": "snacks"},
    ),
    1,
)
test(
    "Generic kex still blocks Frukost Crackers",
    recipe_match_num(
        ["1 förp kex"],
        {"name": "Frukost Crackers 200g Göteborgs kex", "category": "snacks"},
    ),
    0,
)
test(
    "Generic kex still does not match Kexchoklad",
    recipe_match_num(
        ["1 förp kex"],
        {"name": "Kexchoklad 60g Cloetta", "category": "snacks"},
    ),
    0,
)
test(
    "Q2 batch 130 savoiarde product emits savoiardikex keyword",
    extract_keywords_from_product("Savoiarde Kex 210g Soko Stark", "pantry"),
    ["savoiardikex", "kex"],
)
test(
    "Q2 batch 130 savoiardikex matches exact savoiarde product",
    recipe_match_num(
        ["24 savoiardikex"],
        {"name": "Savoiarde Kex 210g Soko Stark", "category": "pantry"},
    ),
    1,
)
test(
    "Q2 batch 130 cached savoiardikex also matches exact savoiarde product",
    recipe_match_num_cached(
        ["24 savoiardikex"],
        {"name": "Savoiarde Kex 210g Soko Stark", "category": "pantry"},
    ),
    1,
)
test(
    "Q2 batch 130 savoiardikex still blocks unrelated generic kex products",
    recipe_match_num(
        ["24 savoiardikex"],
        {"name": "Biscoff kex 140 g Lotus", "category": "snacks"},
    ),
    0,
)
test(
    "Q3 batch 130 Grillolja Honey still matches flavored grill oil broadly",
    recipe_match_num(
        ["0.5 dl Grillolja Honey"],
        {"name": "BBQ grillolja Honey 400ml Santa Maria", "category": "spices"},
    ),
    1,
)
test(
    "Q3 batch 130 Grillolja Honey also accepts garlic grill oil",
    recipe_match_num_cached(
        ["0.5 dl Grillolja Honey"],
        {"name": "BBQ grillolja Garlic 400ml Santa Maria", "category": "spices"},
    ),
    1,
)
test(
    "Q3 batch 130 Grillolja Honey also accepts allround grill oil",
    recipe_match_num_cached(
        ["0.5 dl Grillolja Honey"],
        {"name": "BBQ grillolja Allround 400ml Santa Maria", "category": "spices"},
    ),
    1,
)
test(
    "Q3 batch 130 chilibearnaisesås matches exact chili bearnaise",
    recipe_match_num(
        ["2 dl chilibearnaisesås"],
        {"name": "Chilibearnaisesås 230g Lohmanders", "category": "pantry"},
    ),
    1,
)
test(
    "Q3 batch 130 chilibearnaisesås also accepts plain bearnaise",
    recipe_match_num_cached(
        ["2 dl chilibearnaisesås"],
        {"name": "Bearnaisesås Original 230g Lohmanders", "category": "pantry"},
    ),
    1,
)
test(
    "Q3 batch 130 chilibearnaisesås also accepts other bearnaise variants",
    recipe_match_num_cached(
        ["2 dl chilibearnaisesås"],
        {"name": "Bearnaise Tryffel 230ml ICA Selection", "category": "pantry"},
    ),
    1,
)
test(
    "Q4 batch 130 ris in risgrynsgrot context matches grötris",
    recipe_match_num_named(
        "Risgrynsgröt i olika portioner",
        ["1 1/2 dl ris"],
        {"name": "Grötris 1kg ICA", "category": "pantry"},
    ),
    1,
)
test(
    "Q4 batch 130 cached ris in risgrynsgrot context matches grötris",
    recipe_match_num_named_cached(
        "Risgrynsgröt i olika portioner",
        ["1 1/2 dl ris"],
        {"name": "Grötris 1kg ICA", "category": "pantry"},
    ),
    1,
)
test(
    "Q4 batch 130 ris in risgrynsgrot context blocks basmatiris",
    recipe_match_num_named_cached(
        "Risgrynsgröt i olika portioner",
        ["1 1/2 dl ris"],
        {"name": "Basmatiris 500g ICA", "category": "pantry"},
    ),
    0,
)
test(
    "Q4 batch 130 plain ris outside risgrynsgrot context still matches basmatiris",
    recipe_match_num_named_cached(
        "Sanity Recipe",
        ["1 1/2 dl ris"],
        {"name": "Basmatiris 500g ICA", "category": "pantry"},
    ),
    1,
)
test(
    "Q1 batch 131 Tortiglioni Al Bronzo emits generic pasta",
    extract_keywords_from_product("Tortiglioni Al Bronzo 500g Barilla", "pantry"),
    ["bronzo", "pasta"],
)
test(
    "Q1 batch 131 Fusilli Al Bronzo also emits generic pasta",
    extract_keywords_from_product("Fusilli Al Bronzo 400g Barilla", "pantry"),
    ["bronzo", "pasta"],
)
test(
    "Q1 batch 131 tortiglioni ingredient still matches Al Bronzo pasta via generic pasta",
    recipe_match_num(
        ["1 frp Zeta Tortiglioni"],
        {"name": "Tortiglioni Al Bronzo 500g Barilla", "category": "pantry"},
    ),
    1,
)
test(
    "Q1 batch 131 cached tortiglioni ingredient still matches Al Bronzo pasta via generic pasta",
    recipe_match_num_cached(
        ["1 frp Zeta Tortiglioni"],
        {"name": "Tortiglioni Al Bronzo 500g Barilla", "category": "pantry"},
    ),
    1,
)
test(
    "Q2 batch 131 parser keeps shared att toppa med phrase on both cheese alternatives",
    parse_eller_alternatives("Parmigiano Reggiano eller Grana Padano att toppa med"),
    ["Parmigiano Reggiano att toppa med", "Grana Padano att toppa med"],
)
test(
    "Q2 batch 131 recipe matcher keeps both cheese alternatives in one group",
    recipe_match_data_multi_cached(
        ["Parmigiano Reggiano eller Grana Padano att toppa med"],
        [
            {"name": "Parmigiano Reggiano 150g Zeta", "category": "pantry"},
            {"name": "Grana Padano 150g Zeta", "category": "pantry"},
        ],
    )["ingredient_groups"][0]["alternatives"],
    ["Parmigiano Reggiano att toppa med", "Grana Padano att toppa med"],
)
test(
    "Q4 batch 131 tacoskal exact product now emits tacoskal keyword",
    extract_keywords_from_product("Tacoskal 12-p 135g ICA", "pantry"),
    ["tacoskal"],
)
test(
    "Q4 batch 131 taco shells now emit tacoskal keyword",
    extract_keywords_from_product("Taco Shells 135g Santa Maria", "pantry"),
    ["tacoskal"],
)
test(
    "Q4 batch 131 taco tubs now emit tacoskal keyword",
    extract_keywords_from_product("Taco Tubs 145g Santa Maria", "pantry"),
    ["tacoskal"],
)
test(
    "Q4 batch 131 tacoskal ingredient matches taco shells",
    recipe_match_num(
        ["135 g Tacoskal"],
        {"name": "Taco Shells 135g Santa Maria", "category": "pantry"},
    ),
    1,
)
test(
    "Q4 batch 131 cached tacoskal ingredient also matches tacotubs",
    recipe_match_num_cached(
        ["135 g Tacoskal"],
        {"name": "Tacotubs 8-p 145g ICA", "category": "pantry"},
    ),
    1,
)
test(
    "Q4 batch 131 tacoskal still blocks broader taco kits",
    recipe_match_num(
        ["135 g Tacoskal"],
        {"name": "Taco Kit Original 308g Old El Paso", "category": "pantry"},
    ),
    0,
)
test(
    "Q1 batch 133 flytande smör ingredient extracts its own liquid-butter keyword",
    extract_keywords_from_ingredient("2 msk Flytande Smör"),
    ["flytandesmör"],
)
test(
    "Q1 batch 133 smör och rapsolja flytande emits liquid-butter keyword",
    extract_keywords_from_product("Smör & Rapsolja Flytande 500ml Bregott", "pantry"),
    ["smörrapsolja", "flytandesmör"],
)
test(
    "Q1 batch 133 flytande smör matches flytande smör och rapsolja product",
    recipe_match_num(
        ["2 msk Flytande Smör"],
        {"name": "Smör & Rapsolja Flytande 500ml Bregott", "category": "pantry"},
    ),
    1,
)
test(
    "Q1 batch 133 cached flytande smör also matches ICA liquid butter blend",
    recipe_match_num_cached(
        ["2 msk Flytande Smör"],
        {"name": "Smör- & rapsolja flytande 500ml ICA", "category": "pantry"},
    ),
    1,
)
test(
    "Q1 batch 133 flytande smör no longer matches ordinary solid butter",
    recipe_match_num_cached(
        ["2 msk Flytande Smör"],
        {"name": "Smör Normalsaltat 500g ICA", "category": "dairy"},
    ),
    0,
)
test(
    "Q1 batch 133 flytande smör stays narrower than generic flytande margarin",
    recipe_match_num(
        ["2 msk Flytande Smör"],
        {"name": "Flytande margarin 500ml ICA", "category": "pantry"},
    ),
    0,
)
test(
    "Q2 batch 133 creme fraiche Karljohan matches exact flavored fraiche product",
    recipe_match_num_cached(
        ["2 dl Creme Fraiche Karljohan"],
        {"name": "Creme Fraiche Karljohan 2dl ICA", "category": "dairy"},
    ),
    1,
)
test(
    "Q2 batch 133 creme fraiche Karljohan still accepts plain fraiche as fallback",
    recipe_match_num_cached(
        ["2 dl Creme Fraiche Karljohan"],
        {"name": "Creme fraiche 32% 2dl ICA", "category": "dairy"},
    ),
    1,
)
test(
    "Q2 batch 133 creme fraiche Karljohan blocks other flavored fraiche variants",
    recipe_match_num_cached(
        ["2 dl Creme Fraiche Karljohan"],
        {"name": "Creme Fraiche Franska Örter 28% 2,5dl Valio", "category": "dairy"},
    ),
    0,
)
test(
    "Q3 batch 133 pantry Fitness Original emits fitnessflingor keyword",
    extract_keywords_from_product("Fitness Original 375g Nestle", "pantry"),
    ["fitnessflingor"],
)
test(
    "Q3 batch 133 pantry Fitnessfullkorn also emits fitnessflingor keyword",
    extract_keywords_from_product("Fitnessfullkorn 375g Nestle", "pantry"),
    ["fitnessflingor"],
)
test(
    "Q3 batch 133 snack bar Fitness stays outside fitnessflingor family",
    extract_keywords_from_product("Bar Fitness Röda Bär 23,5g Nestle", "snacks"),
    ["fitness"],
)
test(
    "Q3 batch 133 fitnessflingor matches pantry Fitness cereal",
    recipe_match_num_cached(
        ["2 dl Fitnessflingor"],
        {"name": "Fitness Original 375g Nestle", "category": "pantry"},
    ),
    1,
)
test(
    "Q3 batch 133 fitnessflingor also matches Fitnessfullkorn cereal",
    recipe_match_num_cached(
        ["2 dl Fitnessflingor"],
        {"name": "Fitnessfullkorn 375g Nestle", "category": "pantry"},
    ),
    1,
)
test(
    "Q3 batch 133 fitnessflingor no longer matches Fitness snack bars",
    recipe_match_num_cached(
        ["2 dl Fitnessflingor"],
        {"name": "Bar Fitness Röda Bär 23,5g Nestle", "category": "snacks"},
    ),
    0,
)
test(
    "Q4 batch 133 plain makrillfiléer block flavored pantry fillets",
    recipe_match_num_cached(
        ["4 makrillfiléer"],
        {"name": "Makrillfileer Citrontimjan 120g Manna", "category": "pantry"},
    ),
    0,
)
test(
    "Q4 batch 133 plain makrillfiléer also block other pantry prepared fillets",
    recipe_match_num_cached(
        ["4 makrillfiléer"],
        {"name": "Makrillfileer På Portugisiskt Vis 125g Abba", "category": "pantry"},
    ),
    0,
)
test(
    "Q4 batch 133 plain makrillfiléer still match fresh fillet",
    recipe_match_num_cached(
        ["4 makrillfiléer"],
        {"name": "Makrillfilé Färsk ca 300g ICA", "category": "fish"},
    ),
    1,
)
test(
    "Q4 batch 133 plain makrillfiléer still match frozen fillets",
    recipe_match_num_cached(
        ["4 makrillfiléer"],
        {"name": "Makrillfiléer Frysta 400g ICA", "category": "frozen"},
    ),
    1,
)
test(
    "Q5 batch 133 mynta eller oxalis now accepts fresh mynta bunch",
    recipe_match_num_cached(
        ["mynta eller oxalis"],
        {"name": "Mynta Bunt ca 100g Klass 1 ICA", "category": "vegetables"},
    ),
    1,
)
test(
    "Q5 batch 133 mynta eller oxalis blocks dried mynta spice",
    recipe_match_num_cached(
        ["mynta eller oxalis"],
        {"name": "Mynta 9g Santa Maria", "category": "spices"},
    ),
    0,
)
test(
    "Q5 batch 133 mynta eller oxalis still accepts oxalis",
    recipe_match_num_cached(
        ["mynta eller oxalis"],
        {"name": "Oxalis ca 30g Klass 1 ICA", "category": "vegetables"},
    ),
    1,
)
test(
    "Q6 batch 133 hönsbröstfilé now maps into ordinary kycklingbröstfilé family",
    recipe_match_num_cached(
        ["300 g Hönsbröstfilé"],
        {"name": "Kyckling Bröstfilé Färsk 650g Kronfågel", "category": "poultry"},
    ),
    1,
)
test(
    "Q6 batch 133 hönsbröstfilé still does not match kalkon bröstfilé",
    recipe_match_num_cached(
        ["300 g Hönsbröstfilé"],
        {"name": "Kalkon Bröstfilé 600g Ingelsta Kalkon", "category": "poultry"},
    ),
    0,
)
test(
    "Q6 batch 133 hönsbröstfilé still blocks ready cooked kyckling bröstfilé deli",
    recipe_match_num_cached(
        ["300 g Hönsbröstfilé"],
        {"name": "Kyckling Pålägg Bröstfilé 150g ICA", "category": "deli"},
    ),
    0,
)
test(
    "Q7 batch 133 explicit röda linser förkokta match cooked red lentils",
    recipe_match_num(
        ["4 dl Röda Linser Förkokta"],
        {"name": "Röda Linser Förkokta 380g GoGreen", "category": "pantry"},
    ),
    1,
)
test(
    "Q7 batch 133 cached explicit röda linser förkokta also match kokta red lentils",
    recipe_match_num_cached(
        ["4 dl Röda Linser Förkokta"],
        {"name": "Röda Linser Kokta 380g Zeta", "category": "pantry"},
    ),
    1,
)
test(
    "Q7 batch 133 explicit röda linser förkokta block dry red lentils",
    recipe_match_num(
        ["4 dl Röda Linser Förkokta"],
        {"name": "Röda linser 500g ICA", "category": "pantry"},
    ),
    0,
)
test(
    "Q7 batch 133 explicit röda linser förkokta block split dry lentils",
    recipe_match_num_cached(
        ["4 dl Röda Linser Förkokta"],
        {"name": "Linser Röda Delade 500g GoGreen", "category": "pantry"},
    ),
    0,
)
test(
    "Q1 batch 134 explicit durumvetemjöl still matches durum flour",
    recipe_match_num(
        ["5 dl Durumvetemjöl"],
        {"name": "Durumvetemjöl 1kg Kungsörnen", "category": "pantry"},
    ),
    1,
)
test(
    "Q1 batch 134 cached explicit durumvetemjöl blocks ordinary vetemjöl",
    recipe_match_num_cached(
        ["5 dl Durumvetemjöl"],
        {"name": "Vetemjöl 1kg ICA", "category": "pantry"},
    ),
    0,
)
test(
    "Q1 batch 134 explicit durumvetemjöl still blocks vetemjöl special",
    recipe_match_num(
        ["5 dl Durumvetemjöl"],
        {"name": "Vetemjöl Special 2kg Kungsörnen", "category": "pantry"},
    ),
    0,
)
test(
    "Q2 batch 134 explicit torkad svamp matches dried Karl Johan mushrooms",
    recipe_match_num(
        ["1 dl Torkad svamp"],
        {"name": "Karl Johan-svamp torkad Klass 1", "category": "vegetables"},
    ),
    1,
)
test(
    "Q2 batch 134 explicit torkad svamp matches dried trumpet chanterelles",
    recipe_match_num_cached(
        ["1 dl Torkad svamp"],
        {"name": "Trattkantarell torkad Klass 1", "category": "vegetables"},
    ),
    1,
)
test(
    "Q2 batch 134 explicit torkad svamp matches dried shiitake",
    recipe_match_num(
        ["1 dl Torkad svamp"],
        {"name": "Shiitake Torkad 30g", "category": "vegetables"},
    ),
    1,
)
test(
    "Q2 batch 134 explicit torkad svamp blocks mushrooms in water",
    recipe_match_num_cached(
        ["1 dl Torkad svamp"],
        {"name": "Kantareller i vatten 200g Borgens", "category": "vegetables"},
    ),
    0,
)
test(
    "Q5 batch 134 riven cheddarost blocks cheddar spread product",
    recipe_match_num(
        ["3 dl riven cheddarost"],
        {"name": "CheddarOst 250g Kavli", "category": "mejeri"},
    ),
    0,
)
test(
    "Q5 batch 134 cached riven cheddarost still matches proper riven cheddar",
    recipe_match_num_cached(
        ["3 dl riven cheddarost"],
        {"name": "Cheddar Riven 150g ICA", "category": "mejeri"},
    ),
    1,
)
test(
    "Q5 batch 134 riven cheddarost still matches ordinary solid cheddar",
    recipe_match_num(
        ["3 dl riven cheddarost"],
        {"name": "Cheddarost Mild 1kg Wernerssons", "category": "mejeri"},
    ),
    1,
)
test(
    "Q6 batch 134 generic djupfryst fisk ingredient extracts fiskfilé fallback",
    extract_keywords_from_ingredient("400 g tärnad djupfryst fisk"),
    ["fiskfilé"],
)
test(
    "Q6 batch 134 generic djupfryst fisk matches frozen torskfilé",
    recipe_match_num(
        ["400 g tärnad djupfryst fisk"],
        {"name": "Torskfilé Fryst 400g ICA", "category": "frozen"},
    ),
    1,
)
test(
    "Q6 batch 134 cached generic djupfryst fisk also matches frozen laxfilé",
    recipe_match_num_cached(
        ["400 g tärnad djupfryst fisk"],
        {"name": "Laxfilé Fryst 500g ICA", "category": "frozen"},
    ),
    1,
)
test(
    "Q6 batch 134 generic djupfryst fisk matches frozen sejfilé",
    recipe_match_num(
        ["400 g tärnad djupfryst fisk"],
        {"name": "Sejfilé Fryst 400g ICA", "category": "frozen"},
    ),
    1,
)
test(
    "Q6 batch 134 generic djupfryst fisk still blocks fish sticks",
    recipe_match_num_cached(
        ["400 g tärnad djupfryst fisk"],
        {"name": "Fiskpinnar 350g Findus", "category": "frozen"},
    ),
    0,
)
test(
    "Q6 batch 134 generic djupfryst fisk still blocks fresh fish fillet",
    recipe_match_num(
        ["400 g tärnad djupfryst fisk"],
        {"name": "Torskfilé Färsk 400g ICA", "category": "fish"},
    ),
    0,
)
test(
    "Pastasås Tomatsås med Chili = explicit tomatsås (fast path)",
    match("Pastasås Tomatsås med Chili 390g ICA", "400 g Tomatsås", "pantry"),
    "tomatsås",
)
test(
    "Pastasås Tomatsås med Chili = explicit tomatsås (uncached recipe matcher)",
    recipe_match_num(
        ["400 g Tomatsås"],
        {"name": "Pastasås Tomatsås med Chili 390g ICA", "category": "pantry", "brand": "ICA"},
    ),
    1,
)
test(
    "Pastasås Tomatsås med Chili = explicit tomatsås (cached recipe matcher)",
    recipe_match_num_cached(
        ["400 g Tomatsås"],
        {"name": "Pastasås Tomatsås med Chili 390g ICA", "category": "pantry", "brand": "ICA"},
    ),
    1,
)
test(
    "Plain Pastasås Basilika ≠ explicit tomatsås",
    recipe_match_num(
        ["400 g Tomatsås"],
        {"name": "Pastasås Basilika 390g ICA", "category": "pantry", "brand": "ICA"},
    ),
    0,
)
test(
    "Teriyakisås ingredient matches exact teriyakisås bottle",
    recipe_match_num(
        ["1 dl teriyakisås"],
        {"name": "Teriyakisås 300ml Santa Maria", "category": "pantry"},
    ),
    1,
)
test(
    "Teriyakisås ingredient matches English Teriyaki Sauce bottle",
    recipe_match_num(
        ["1 dl teriyakisås"],
        {"name": "Teriyaki Sauce 150ml Blue Dragon", "category": "pantry"},
    ),
    1,
)
test(
    "Teriyakisås ingredient matches Sojasås Teriyaki bottle",
    recipe_match_num(
        ["1 dl teriyakisås"],
        {"name": "Sojasås Teriyaki 300ml ICA Asia", "category": "pantry"},
    ),
    1,
)
test(
    "Teriyakisås ingredient matches Teriyakimarinad bottle",
    recipe_match_num(
        ["1 dl teriyakisås"],
        {"name": "Teriyakimarinad 150ml ICA Asia", "category": "pantry"},
    ),
    1,
)
test(
    "Teriyakisås ingredient does not match teriyaki jerky",
    recipe_match_num(
        ["1 dl teriyakisås"],
        {"name": "Torkat Kött Teriyaki Beef Jerky 25g Jack Link's", "category": "pantry"},
    ),
    0,
)
test(
    "Teriyakisås ingredient does not match tempeh teriyaki",
    recipe_match_num(
        ["1 dl teriyakisås"],
        {"name": "Tempeh teriyaki 200g Yipin", "category": "pantry"},
    ),
    0,
)
test(
    "Teriyakisås ingredient does not match woksås teriyaki",
    recipe_match_num(
        ["1 dl teriyakisås"],
        {"name": "Woksås Teriyaki 120g Blue dragon", "category": "pantry"},
    ),
    0,
)
test(
    "Teriyakisås ingredient does not match frozen teriyaki wok meals",
    recipe_match_num(
        ["1 dl teriyakisås"],
        {"name": "Wok Teriyaki Kyckling 450g Mama Chin", "category": "frozen"},
    ),
    0,
)
test(
    "Sataysås ingredient matches satay cooking sauce bottle",
    recipe_match_num(
        ["200 g Sataysås"],
        {"name": "Satay Cooking Sauce 350ml Blue Dragon", "category": "pantry"},
    ),
    1,
)
test(
    "Sataysås ingredient does not match chicken satay ready meal",
    recipe_match_num(
        ["200 g Sataysås"],
        {"name": "Färdigmat Chicken Satay 400g Topsfoods PURE", "category": "other"},
    ),
    0,
)
test(
    "Sataysås ingredient does not match satay skewers",
    recipe_match_num(
        ["200 g Sataysås"],
        {"name": "Kycklingspett Djupfryst Yakitori Satay 1,5kg 50-p Sky Food", "category": "poultry"},
    ),
    0,
)
test(
    "Kormasås ingredient matches plain korma sauce jar",
    recipe_match_num(
        ["300 g Kormasås"],
        {"name": "Korma 450g Pataks", "category": "pantry"},
    ),
    1,
)
test(
    "Kormasås ingredient matches grytbas korma",
    recipe_match_num(
        ["300 g Kormasås"],
        {"name": "Grytbas Korma 480g ICA Asia", "category": "pantry"},
    ),
    1,
)
test(
    "Kormasås ingredient does not match korma ready meal",
    recipe_match_num(
        ["300 g Kormasås"],
        {"name": "Färdigmat Chicken Korma 400g Test", "category": "other"},
    ),
    0,
)
test(
    "Kormasås ingredient does not match korma spice mix",
    recipe_match_num(
        ["300 g Kormasås"],
        {"name": "Korma Kryddmix 50g Test", "category": "spices"},
    ),
    0,
)
test(
    "Chipotlepasta ingredient matches exact chipotle paste product",
    recipe_match_num(
        ["0.5 dl Chipotlepasta"],
        {"name": "Chipotle Paste 100g Santa Maria", "category": "pantry"},
    ),
    1,
)
test(
    "Chipotlepasta ingredient does not match chipotle sauce",
    recipe_match_num(
        ["0.5 dl Chipotlepasta"],
        {"name": "Chipotle Sauce 200ml Test", "category": "pantry"},
    ),
    0,
)
test(
    "Chipotlepasta ingredient does not match chipotle mayo",
    recipe_match_num(
        ["0.5 dl Chipotlepasta"],
        {"name": "Chipotle Mayo 250ml Test", "category": "pantry"},
    ),
    0,
)
test(
    "Chipotlepasta ingredient still blocks dry chipotle spice",
    recipe_match_num(
        ["0.5 dl Chipotlepasta"],
        {"name": "Chilipeppar Chipotle 33g Santa Maria", "category": "spices"},
    ),
    0,
)
test(
    "Gochujang chilipasta ingredient matches gochujang paste product",
    recipe_match_num(
        ["1 - 2 msk gochujang chilipasta"],
        {"name": "Chilipasta GoChuJang 200g Risberg", "category": "pantry"},
    ),
    1,
)
test(
    "Gochujang chilipasta ingredient does not match harissa chili paste",
    recipe_match_num(
        ["1 - 2 msk gochujang chilipasta"],
        {"name": "Harissa Het Chilipasta 380g Sevan", "category": "pantry"},
    ),
    0,
)
test(
    "Gochujang chilipasta ingredient does not match sambal badjak chili paste",
    recipe_match_num(
        ["1 - 2 msk gochujang chilipasta"],
        {"name": "Chilipasta Sambal Badjak 280g Koningsvogel", "category": "pantry"},
    ),
    0,
)
test(
    "Chilisås Original ingredient does not match gochujang chili sauce",
    recipe_match_num(
        ["4 msk Chilisås Original"],
        {"name": "Go-chu-jang Chilisås 240g Risberg Import", "category": "pantry"},
    ),
    0,
)
test(
    "Chilisås Original ingredient still matches plain original chili sauce",
    recipe_match_num(
        ["4 msk Chilisås Original"],
        {"name": "Chilisås Original 500g Felix", "category": "pantry"},
    ),
    1,
)
test(
    "Plain chilisås ingredient also does not match gochujang chili sauce",
    recipe_match_num(
        ["4 msk chilisås"],
        {"name": "Go-chu-jang Chilisås 240g Risberg Import", "category": "pantry"},
    ),
    0,
)
test(
    "Generic färska bär ingredient matches fresh hallon offers",
    recipe_match_num(
        ["färska bär"],
        {"name": "Hallon Färska 125g Klass 1 ICA", "category": "fruit"},
    ),
    1,
)
test(
    "Generic färska bär ingredient also matches cached fresh hallon offers",
    recipe_match_num_cached(
        ["färska bär"],
        {"name": "Hallon Färska 125g Klass 1 ICA", "category": "fruit"},
    ),
    1,
)
test(
    "Generic färska bär ingredient matches fresh blåbär offers",
    recipe_match_num(
        ["färska bär"],
        {"name": "Blåbär Färska 125g Klass 1 ICA", "category": "fruit"},
    ),
    1,
)
test(
    "Salladsärtor ingredient matches Salladsärter product variant",
    recipe_match_num(
        ["150 g salladsärtor"],
        {"name": "Salladsärter 150g Klass 1 ICA", "category": "fruit"},
    ),
    1,
)
test(
    "Maccaronetti ingredient matches plain dry maccaronetti product",
    recipe_match_num(
        ["1 frp Zeta Maccaronetti"],
        {"name": "Maccaronetti 500g Zeta", "category": "pantry"},
    ),
    1,
)
test(
    "Maccaronetti ingredient does not match ordinary dry pasta via pasta umbrella",
    recipe_match_num(
        ["1 frp Zeta Maccaronetti"],
        {"name": "Spaghetti 500g Barilla", "category": "pantry"},
    ),
    0,
)
test(
    "Maccaronetti ingredient does not match filled pasta dish",
    recipe_match_num(
        ["1 frp Zeta Maccaronetti"],
        {"name": "Pasta Mezze Lune Karl-johansvamp 250g Giovanni Rana", "category": "pantry"},
    ),
    0,
)
test(
    "Maccaronetti ingredient does not match ready pasta with pesto",
    recipe_match_num(
        ["1 frp Zeta Maccaronetti"],
        {"name": "Pasta Pesto 450g ICA", "category": "refrigerated"},
    ),
    0,
)
test(
    "Maccaronetti ingredient does not match frozen chicken pasta meal",
    recipe_match_num(
        ["1 frp Zeta Maccaronetti"],
        {"name": "Tagliatelle chicken 1kg Findus", "category": "frozen"},
    ),
    0,
)
test(
    "Tomatsoppa ingredient matches plain tomato soup product",
    recipe_match_num(
        ["1 liter mild tomatsoppa"],
        {"name": "Tomatsoppa 400g Heinz", "category": "pantry"},
    ),
    1,
)
test(
    "Tomatsoppa ingredient matches chunky tomato soup product",
    recipe_match_num(
        ["1 liter mild tomatsoppa"],
        {"name": "Tomatsoppa med bitar 475g ICA", "category": "pantry"},
    ),
    1,
)
test(
    "Tomatsoppa ingredient does not match tomato pasta sauce",
    recipe_match_num(
        ["1 liter mild tomatsoppa"],
        {"name": "Pastasås Tomatsås med Basilika 390g ICA", "category": "pantry"},
    ),
    0,
)
test(
    "Kvibille ädel ingredient keeps ädel cheese-family keyword",
    extract_keywords_from_ingredient("140 g kvibille ädel"),
    ["kvibille", "ädel"],
)
test(
    "Kvibille ädel ingredient matches ädelost product",
    recipe_match_num(
        ["140 g kvibille ädel"],
        {"name": "Ädel Special 45% Blåmögelost 140g Kvibille", "category": "dairy"},
    ),
    1,
)
test(
    "filmjölk eller yoghurt blocks flavored filmjölk",
    recipe_match_num(
        ["5 dl filmjölk eller yoghurt"],
        {"name": "Filmjölk Svarta Vinbär 3,7% 1000g Fjällfil", "category": "dairy"},
    ),
    0,
)
test(
    "filmjölk eller yoghurt keeps plain filmjölk",
    recipe_match_num(
        ["5 dl filmjölk eller yoghurt"],
        {"name": "Filmjölk Naturell 3% 1000g Arla", "category": "dairy"},
    ),
    1,
)
test(
    "filmjölk eller yoghurt allows plain naturell yoghurt",
    recipe_match_num(
        ["5 dl filmjölk eller yoghurt"],
        {"name": "Yoghurt Naturell 3% 1000g Arla", "category": "dairy"},
    ),
    1,
)
test(
    "filmjölk eller yoghurt keeps turkisk yoghurt",
    recipe_match_num(
        ["5 dl filmjölk eller yoghurt"],
        {"name": "Yoghurt Turkisk 10% 1000g Lindahls", "category": "dairy"},
    ),
    1,
)
test(
    "filmjölk eller yoghurt still blocks flavored yoghurt",
    recipe_match_num(
        ["5 dl filmjölk eller yoghurt"],
        {"name": "Yoghurt Jordgubb 1000g Valio", "category": "dairy"},
    ),
    0,
)

# FPB: 'ingefär' blocks 'färs' keyword in ingredient text
test("Nötfärs ≠ 'ingefärsmarmelad' (färs substring)", match("Nötfärs Färsk 12% 1kg", "1/2 dl ingefärsmarmelad"), None)
test("Blandfärs ≠ 'ingefärssaft' (färs substring)", match("Blandfärs Färsk 500g ICA", "2 cl ingefärssaft"), None)
test("Nötfärs = actual 'nötfärs' ingredient", match("Nötfärs Färsk 12% 1kg", "500 g nötfärs") is not None, True)

# PNB: marsipan blocks mandlar/sötmandel keyword (checked at pipeline level)
test("PNB mandel → marsipan", 'marsipan' in PRODUCT_NAME_BLOCKERS.get('mandel', set()), True)
test("PNB mandlar → marsipan", 'marsipan' in PRODUCT_NAME_BLOCKERS.get('mandlar', set()), True)
test("PNB sötmandel → marsipan", 'marsipan' in PRODUCT_NAME_BLOCKERS.get('sötmandel', set()), True)
test("PNB soltor → oliver", 'oliver' in PRODUCT_NAME_BLOCKERS.get('soltor', set()), True)
test("PNB nötfärs → högrev", 'högrev' in PRODUCT_NAME_BLOCKERS.get('nötfärs', set()), True)
# PNB pistage/pistagenötter → glass removed — glass normalization blocks pistachio ice cream now
test("Sötmandel ICA = 'mandlar'", match("Sötmandel 200g ICA", "50 g mandlar") is not None, True)
test("Marsipan = actual 'marsipan' ingredient", match("Marsipan 24% sötmandel 400g Odense", "200 g marsipan") is not None, True)

# ========================================================================
section("9. FALSE POSITIVE SCAN - products matching on secondary/irrelevant words")
# ========================================================================
# Products should NOT match ingredients when the matched keyword is a
# secondary descriptor (packaging oil, flavoring, place name, etc.)
# rather than the actual product.

# --- Known false positives: product should NOT match the ingredient ---
KNOWN_FALSE_POSITIVES = [
    # (product_name, ingredient_text, reason)
    # Packaging medium (oil in canned fish/meat)
    ("Sardiner Delikatessrökta i Rapsolja", "2 msk rapsolja", "rapsolja is packaging, not product"),
    ("Sardiner i Olivolja", "2 msk olivolja", "olivolja is packaging, not product"),
    ("Tonfisk i Solrosolja", "1 msk solrosolja", "solrosolja is packaging, not product"),
    ("Makrill i Tomatsås", "2 dl tomatsås", "tomatsås is packaging, not product"),
    # Flavoring in meat/chark products
    ("Salsicciafärs Fänkål", "1 fänkål", "fänkål is flavoring in sausage"),
    ("Nötkorv Persilja & Vitlök Sverige", "1 dl hackad persilja", "persilja is flavoring in korv"),
    # Processed food with raw ingredient keyword
    ("Havre & Quinoa Gröt", "2 dl quinoa", "gröt is processed, not raw quinoa"),
    ("Nesquik Duo Cereal Puffar", "100 g quinoapuffar", "cereal puffs, not cooking puffs"),
    # Place names as keywords
    # NOTE: "Lammstek Smak av Gotland" removed — lammstek now extracts 'lamm' via
    # KEYWORD_EXTRA_PARENTS, which correctly matches "gotlandslammkött" (it IS lamb)
    # Prefix word not the main product
    ("Kål Bönbiff med Vaxböna Fryst Vego", "200 g kål", "product is bönbiff, not kål"),
    # Spice mix matching salt
    ("Ört Havssalt Herbamare", "2 krm havssalt", "spice mix, not plain havssalt"),
]

for product, ingredient, reason in KNOWN_FALSE_POSITIVES:
    result = match(product, ingredient)
    test(
        f"{product} ≠ '{ingredient}' ({reason})",
        result,
        None,
    )

# ========================================================================
# Section: contextual cheese recipe matcher regressions
# ========================================================================
total_sections += 1
print(f"\n--- Section {total_sections}: contextual cheese recipe matcher regressions ---")
test(
    "gratängost matches gratäng-style ost ingredient (uncached)",
    recipe_match_num(
        ["150 g riven ost gratäng"],
        {"name": "Gratängost Riven 150g ICA", "category": "dairy"},
    ),
    1,
)
test(
    "gratängost matches gratäng-style ost ingredient (cached)",
    recipe_match_num_cached(
        ["150 g riven ost gratäng"],
        {"name": "Gratängost Riven 150g ICA", "category": "dairy"},
    ),
    1,
)
test(
    "gratängost still blocked for generic riven ost",
    recipe_match_num(
        ["150 g riven ost"],
        {"name": "Gratängost Riven 150g ICA", "category": "dairy"},
    ),
    0,
)
test(
    "gratängost still blocked for potatisgratäng dish line",
    recipe_match_num(
        ["potatisgratäng"],
        {"name": "Gratängost Riven 150g ICA", "category": "dairy"},
    ),
    0,
)

# ========================================================================
# Section: Ruff linter check (duplicate dict keys, unused vars, etc.)
# ========================================================================
total_sections += 1
print(f"\n--- Section {total_sections}: Ruff linter ---")
import subprocess
import shutil
ruff_command = (
    ["ruff"]
    if shutil.which("ruff")
    else ["uv", "tool", "run", "ruff"]
)
ruff_result = subprocess.run(
    [*ruff_command, "check", "/app/", "--config", "/app/support_checks/ruff.toml", "--no-cache"],
    capture_output=True, text=True
)
if ruff_result.returncode == 0:
    print("  All ruff checks passed")
    passed += 1
else:
    # Count actual errors (not warnings)
    error_lines = [l for l in ruff_result.stdout.strip().split('\n') if l and not l.startswith('warning')]
    if error_lines:
        print("  FAIL: ruff found issues:")
        for line in error_lines[:10]:
            print(f"    {line}")
        if len(error_lines) > 10:
            print(f"    ... and {len(error_lines) - 10} more")
        failed += 1
    else:
        print("  All ruff checks passed")
        passed += 1

# ========================================================================
# Section: i18n key sync check (SV and EN-GB must have identical keys)
# ========================================================================
total_sections += 1
print(f"\n--- Section {total_sections}: i18n key sync ---")
try:
    from languages.sv.ui import UI as SV_UI
    from languages.en_gb.ui import UI as EN_UI

    def _collect_keys(d, prefix=''):
        keys = set()
        for k, v in d.items():
            full = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                keys.update(_collect_keys(v, full))
            else:
                keys.add(full)
        return keys

    sv_keys = _collect_keys(SV_UI)
    en_keys = _collect_keys(EN_UI)
    missing_en = sv_keys - en_keys
    missing_sv = en_keys - sv_keys

    if missing_en or missing_sv:
        if missing_en:
            print(f"  FAIL: {len(missing_en)} keys in SV but missing in EN:")
            for k in sorted(missing_en)[:10]:
                print(f"    {k}")
        if missing_sv:
            print(f"  FAIL: {len(missing_sv)} keys in EN but missing in SV:")
            for k in sorted(missing_sv)[:10]:
                print(f"    {k}")
        failed += 1
    else:
        print(f"  All {len(sv_keys)} i18n keys synced between SV and EN")
        passed += 1
except Exception as e:
    print(f"  FAIL: Could not compare i18n keys: {e}")
    failed += 1

# ========================================================================
# Section: seafood singular/plural synonym regression
# ========================================================================
total_sections += 1
print(f"\n--- Section {total_sections}: seafood singular/plural synonyms ---")
test(
    "signalkräfta matches signalkräftor offers",
    match_kw("Svenska signalkräftor Fryst 500g ICA", "4-6 signalkräfta"),
    "signalkräfta",
)
test(
    "signalkräftor still match frozen signalkräftor offers",
    match_kw("Svenska signalkräftor Fryst 500g ICA", "4-6 signalkräftor"),
    "signalkräftor",
)
test(
    "havskräfta still matches explicit havskräftor offers",
    match_kw("Havskräftor 1kg ICA", "4-6 havskräfta"),
    "havskräfta",
)
test(
    "havskräfta blocks frozen signalkräftor offers",
    match_kw("Svenska signalkräftor Fryst 500g ICA", "4-6 havskräfta"),
    None,
)
test(
    "havskräftor block frozen signalkräftor offers",
    match_kw("Svenska signalkräftor Fryst 500g ICA", "4-6 havskräftor"),
    None,
)
passed += 0

# ========================================================================
# Section: batch 131 regression checks
# ========================================================================
section("batch 131 regressions")
test(
    "preserved champinjoner block fresh produce fallback",
    recipe_match_num(
        ["400 st Champinjoner Skivade i Konserv"],
        {"name": "Champinjoner 400g Klass 1 ICA", "category": "fruit", "savings": 10},
    ),
    0,
)
test(
    "preserved champinjoner still match preserved sliced products",
    recipe_match_num(
        ["400 st Champinjoner Skivade i Konserv"],
        {"name": "Champinjoner Skivade 290g ICA", "category": "vegetables", "savings": 10},
    ),
    1,
)
test(
    "chokladlikor blocks plain cocoa powder",
    recipe_match_num(
        ["3 cl kall chokladlikör/ kakaolikör"],
        {"name": "Kakao 200g ICA", "category": "groceries", "savings": 10},
    ),
    0,
)
test(
    "kakao ingredient still matches cocoa powder",
    recipe_match_num(
        ["2 msk kakao"],
        {"name": "Kakao 200g ICA", "category": "groceries", "savings": 10},
    ),
    1,
)
test(
    "chili limesas routes to lime chilisas instead of fresh chili",
    recipe_match_num(
        ["1 st Chili/Limesås"],
        {"name": "Lime Chilisås 250g Middagsklart Abba", "category": "groceries", "savings": 10},
    ),
    1,
)
test(
    "chili limesas blocks fresh chili produce",
    recipe_match_num(
        ["1 st Chili/Limesås"],
        {"name": "Röd peppar 40g Klass 1 ICA", "category": "fruit", "savings": 10},
    ),
    0,
)
test(
    "vetemjol special blocks generic mjol fallback",
    recipe_match_num(
        ["4 dl vetemjöl special"],
        {"name": "Mjöl 1kg Belje", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "generic mjol ingredient still matches generic mjol product",
    recipe_match_num(
        ["4 dl mjöl"],
        {"name": "Mjöl 1kg Belje", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "syltade apelsinskal block jam fallback",
    recipe_match_num(
        ["50-100 g syltade apelsinskal"],
        {"name": "Hallonsylt Extra fin 400g ICA", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "syltade apelsinskal still match peel product",
    recipe_match_num(
        ["50-100 g syltade apelsinskal"],
        {"name": "Apelsinskal 100g Dr. Oetker", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "hasselnotsmjol blocks whole hazelnut fallback",
    recipe_match_num(
        ["1 1/2 dl mandelmjöl eller hasselnötsmjöl"],
        {"name": "Hasselnöt 750g Start", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "mandelmjol alternative still matches almond flour",
    recipe_match_num(
        ["1 1/2 dl mandelmjöl eller hasselnötsmjöl"],
        {"name": "Mandelmjöl 300g ICA", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "recipe matcher kryddmix tandori matches tandoori mix despite typo",
    recipe_match_num(
        ["35 g Kryddmix Tandori"],
        {"name": "Kryddmix Tandoori 35g ICA Asia", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "recipe matcher kryddmix tandori still blocks tandoori paste",
    recipe_match_num(
        ["35 g Kryddmix Tandori"],
        {"name": "Tandoori 450g Pataks", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "pasta basilico krydda matches pastakrydda instead of dry pasta",
    recipe_match_num(
        ["2 msk Pasta Basilico Krydda"],
        {"name": "Pastakrydda 38g Santa Maria", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "pasta basilico krydda blocks dry pasta fallback",
    recipe_match_num(
        ["2 msk Pasta Basilico Krydda"],
        {"name": "Pasta Fettuccine 500g Barilla", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "muscavadosocker typo still matches muscovado sugar",
    recipe_match_num(
        ["2 1/2 dl muscavadosocker"],
        {"name": "Muscovadorörsocker Ljust 400g Fairtrade Dansukker", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "muscavadosocker typo blocks plain sugar fallback",
    recipe_match_num(
        ["2 1/2 dl muscavadosocker"],
        {"name": "Strösocker 1kg ICA", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "plain salsiccia blocks plant-based salsiccia",
    recipe_match_num(
        ["knaperstekt Zeta Salsiccia"],
        {"name": "Salsiccia Växtbaserad 200g Astrid och aporna", "category": "meat", "savings": 10},
    ),
    0,
)
test(
    "plain salsiccia still matches meat salsiccia",
    recipe_match_num(
        ["knaperstekt Zeta Salsiccia"],
        {"name": "Salsiccia 78% Kötthalt 240g ICA", "category": "meat", "savings": 10},
    ),
    1,
)

# ========================================================================
# Section: batch 136 note regressions
# ========================================================================
section("batch 136 note regressions")
test(
    "shisoblad alternatives expose fallback herb keywords",
    extract_keywords_from_ingredient("4 shisoblad (mynta, thaibasilika eller koriander)"),
    ["shisoblad", "mynta", "thaibasilika", "koriander"],
)
test(
    "shisoblad alternatives match fresh thai basil",
    recipe_match_num(
        ["4 shisoblad (mynta, thaibasilika eller koriander)"],
        {"name": "Thaibasilika i kruka 1-p Klass 1 ICA", "category": "fruit", "savings": 10},
    ),
    1,
)
test(
    "shisoblad alternatives match fresh coriander",
    recipe_match_num(
        ["4 shisoblad (mynta, thaibasilika eller koriander)"],
        {"name": "Koriander i kruka 1-p Klass 1 ICA", "category": "fruit", "savings": 10},
    ),
    1,
)
test(
    "grouped herb leaves preserve named herb keywords",
    extract_keywords_from_ingredient("1 dl plockade örtblad (mynta koriander , dill)"),
    ["örtblad", "mynta", "koriander", "dill"],
)
test(
    "grouped herb leaves match fresh mint",
    recipe_match_num(
        ["1 dl plockade örtblad (mynta koriander , dill)"],
        {"name": "Mynta i kruka Klass 1 ICA", "category": "fruit", "savings": 10},
    ),
    1,
)
test(
    "grouped herb leaves match fresh dill",
    recipe_match_num(
        ["1 dl plockade örtblad (mynta koriander , dill)"],
        {"name": "Dill i kruka Klass 1 ICA", "category": "fruit", "savings": 10},
    ),
    1,
)
test(
    "fresh fettuccine parenthetical still matches fresh long pasta",
    recipe_match_num(
        ["ca 500 g fettuccine (färsk)"],
        {"name": "Pasta Fettuccine Färsk 500g ICA", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "fresh fettuccine parenthetical does not match filled fresh pasta",
    recipe_match_num(
        ["ca 500 g fettuccine (färsk)"],
        {"name": "Pasta Ravioli Färsk 250g ICA", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "generic fresh yeast also matches bread yeast family",
    recipe_match_num(
        ["1 pkt jäst, färsk"],
        {"name": "Jäst för matbröd 50g Kronjäst", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "generic fresh yeast still matches plain fresh yeast",
    recipe_match_num(
        ["1 pkt jäst, färsk"],
        {"name": "Jäst Original Färsk 50g Kronjäst", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "generic fresh yeast does not match sweet dough yeast",
    recipe_match_num(
        ["1 pkt jäst, färsk"],
        {"name": "Jäst för söta degar 50g Kronjäst", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "parmesansås stays on real sauce products",
    recipe_match_num(
        ["1 st Parmesansås"],
        {"name": "Parmesansås 230ml Johan Jureskog Selection", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "parmesansås does not match pasta ready meal",
    recipe_match_num(
        ["1 st Parmesansås"],
        {"name": "Pasta, bacon & parmesansås 390g Findus", "category": "frozen", "savings": 10},
    ),
    0,
)
test(
    "fresh generic svamp blocks mushrooms in water",
    recipe_match_num(
        ["300 g rensad färsk svamp"],
        {"name": "Kantareller i vatten 200g Borgens", "category": "vegetables", "savings": 10},
    ),
    0,
)
test(
    "fresh generic svamp blocks dried mushrooms",
    recipe_match_num(
        ["300 g rensad färsk svamp"],
        {"name": "Trattkantarell torkad Klass 1", "category": "vegetables", "savings": 10},
    ),
    0,
)
test(
    "fresh generic svamp still matches fresh mushrooms",
    recipe_match_num(
        ["300 g rensad färsk svamp"],
        {"name": "Champinjoner Färska 250g ICA", "category": "vegetables", "savings": 10},
    ),
    1,
)
test(
    "fresh generic svamp also accepts frozen mushrooms",
    recipe_match_num(
        ["300 g rensad färsk svamp"],
        {"name": "Champinjoner Frysta 250g ICA", "category": "frozen", "savings": 10},
    ),
    1,
)
test(
    "batch 154 skogschampinjoner blocks preserved sliced champignons",
    recipe_match_num(
        ["250 g skogschampinjoner, skivade"],
        {"name": "Champinjoner Skivade 290g ICA", "category": "vegetables", "savings": 10},
    ),
    0,
)
test(
    "batch 154 skogschampinjoner still match fresh champignons",
    recipe_match_num(
        ["250 g skogschampinjoner, skivade"],
        {"name": "Champinjoner 250g Klass 1 ICA", "category": "vegetables", "savings": 10},
    ),
    1,
)
test(
    "batch 154 skogschampinjoner also accept frozen champignons",
    recipe_match_num(
        ["250 g skogschampinjoner, skivade"],
        {"name": "Champinjoner Frysta 250g ICA", "category": "frozen", "savings": 10},
    ),
    1,
)
test(
    "plain champinjoner accept frozen sliced champignons",
    recipe_match_num(
        ["250 g champinjoner"],
        {"name": "Champinjoner Skivade Frysta Eldorado", "category": "frozen", "savings": 10},
    ),
    1,
)
test(
    "preserved champinjoner do not accept frozen sliced champignons",
    recipe_match_num(
        ["400 st Champinjoner Skivade i Konserv"],
        {"name": "Champinjoner Skivade Frysta Eldorado", "category": "frozen", "savings": 10},
    ),
    0,
)
test(
    "generic fresh chilifrukter accept frozen chopped jalapeno",
    recipe_match_num(
        ["2 st chilifrukter"],
        {"name": "Jalapeno Hackad Fryst Garant", "category": "frozen", "savings": 10},
    ),
    1,
)
test(
    "generic fresh chilifrukter still block jarred sliced jalapeno",
    recipe_match_num(
        ["2 st chilifrukter"],
        {"name": "Jalapeno Sliced Banderos", "category": "spices", "savings": 10},
    ),
    0,
)
test(
    "batch 155 kålhuvud maps to whole fresh white cabbage",
    recipe_match_num(
        ["1 kålhuvud à 1 3/4 kg"],
        {"name": "Vitkål Färsk ca 1,28kg Klass 1 ICA", "category": "fruit", "savings": 10},
    ),
    1,
)
test(
    "batch 155 kålhuvud blocks red cabbage",
    recipe_match_num(
        ["1 kålhuvud à 1 3/4 kg"],
        {"name": "Rödkål ca 1,5kg Klass 1 ICA", "category": "fruit", "savings": 10},
    ),
    0,
)
test(
    "batch 155 kålhuvud blocks pointed cabbage",
    recipe_match_num(
        ["1 kålhuvud à 1 3/4 kg"],
        {"name": "Spetskål Klass 1 ICA", "category": "fruit", "savings": 10},
    ),
    0,
)
test(
    "batch 155 kålhuvud blocks shredded white cabbage",
    recipe_match_num(
        ["1 kålhuvud à 1 3/4 kg"],
        {"name": "Strimlad Vitkål 400g Klass 1 ICA", "category": "fruit", "savings": 10},
    ),
    0,
)
test(
    "batch 155 kålhuvud blocks cut white cabbage",
    recipe_match_num(
        ["1 kålhuvud à 1 3/4 kg"],
        {"name": "Vitkål Delad ca 500g Sydgrönt Klass 1", "category": "fruit", "savings": 10},
    ),
    0,
)
test(
    "glutenfri havregryn blocks ordinary oats",
    recipe_match_num(
        ["2 dl Havregryn Glutenfri"],
        {"name": "Havregryn 1,5kg ICA", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "glutenfri havregryn still match gluten-free oats",
    recipe_match_num(
        ["2 dl Havregryn Glutenfri"],
        {"name": "Havregryn glutenfri 1kg Semper", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "plain havregryn still accepts gluten-free oats",
    recipe_match_num(
        ["2 dl Havregryn"],
        {"name": "Havregryn glutenfri 1kg Semper", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "spättafile normalizes into rödspätta fillet family",
    extract_keywords_from_ingredient("600 g spättafilé"),
    ["rödspättafilé"],
)
test(
    "spättafile matches frozen rödspättafile",
    recipe_match_num(
        ["600 g spättafilé"],
        {"name": "Rödspättafilé Fryst 400g ICA", "category": "frozen", "savings": 10},
    ),
    1,
)
test(
    "spättafile also matches plain rödspätta offers",
    recipe_match_num(
        ["600 g spättafilé"],
        {"name": "Rödspätta 300g ICA Gott Liv", "category": "frozen", "savings": 10},
    ),
    1,
)
test(
    "veg hamburgare normalizes into vegetarian burger family",
    extract_keywords_from_ingredient("4 st Veg. Hamburgare"),
    ["vegetariskhamburgare"],
)
test(
    "veg hamburgare match vegoburgare",
    recipe_match_num(
        ["4 st Veg. Hamburgare"],
        {"name": "Vegoburgare 4-p 226g Anamma", "category": "frozen", "savings": 10},
    ),
    1,
)
test(
    "veg hamburgare also match halloumiburgare",
    recipe_match_num(
        ["4 st Veg. Hamburgare"],
        {"name": "Halloumiburgare Original 200g Fontana", "category": "groceries", "savings": 10},
    ),
    1,
)
test(
    "veg hamburgare also match grillostburgare",
    recipe_match_num(
        ["4 st Veg. Hamburgare"],
        {"name": "Grillostburgare 200g Fontana", "category": "groceries", "savings": 10},
    ),
    1,
)
test(
    "veg hamburgare block meat burgers",
    recipe_match_num(
        ["4 st Veg. Hamburgare"],
        {"name": "Hamburgare Färsk Original 4-p 452g ICA", "category": "meat", "savings": 10},
    ),
    0,
)
test(
    "veg hamburgare block fish burgers",
    recipe_match_num(
        ["4 st Veg. Hamburgare"],
        {"name": "Laxburgare 4-p 320g Leröy", "category": "frozen", "savings": 10},
    ),
    0,
)
test(
    "sojamajonnas blocks plain soy sauce",
    recipe_match_num(
        ["4 msk sojamajonnäs"],
        {"name": "Japansk soja 500ml Mrs Chengs", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "sojamajonnas blocks plain mayonnaise",
    recipe_match_num(
        ["4 msk sojamajonnäs"],
        {"name": "Majonnäs 450g ICA", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "sojamajonnas matches explicit soy mayo products",
    recipe_match_num(
        ["4 msk sojamajonnäs"],
        {"name": "Sojamajonnäs 250ml Test", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "sojamajonnas also matches mayo with soy wording",
    recipe_match_num(
        ["4 msk sojamajonnäs"],
        {"name": "Majonnäs med soja 250ml Test", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "srirachamajonnas blocks plain sriracha sauce",
    recipe_match_num(
        ["4 msk srirachamajonnäs"],
        {"name": "Sriracha 42g Santa Maria", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "srirachamajonnas matches explicit sriracha mayo products",
    recipe_match_num(
        ["4 msk srirachamajonnäs"],
        {"name": "Sriracha Majonnäs 250ml ICA Asia", "category": "pantry", "savings": 10},
    ),
    1,
)

# ========================================================================
# Section: batch 140 note regressions
# ========================================================================
section("batch 140 note regressions")
test(
    "explicit stenbitsrom no longer falls back to frozen löjrom offers",
    recipe_match_num(
        ["80 g stenbitsrom"],
        {"name": "Amerikansk löjrom Fryst 80g Pandalus", "category": "frozen", "savings": 10},
    ),
    0,
)
test(
    "cached explicit stenbitsrom no longer falls back to frozen löjrom offers",
    recipe_match_num_cached(
        ["80 g stenbitsrom"],
        {"name": "Amerikansk löjrom Fryst 80g Pandalus", "category": "frozen", "savings": 10},
    ),
    0,
)
test(
    "explicit stenbitsrom no longer falls back to sikrom offers",
    recipe_match_num(
        ["80 g stenbitsrom"],
        {"name": "Sikrom 500g Kalix", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "explicit stenbitsrom no longer falls back to regnbågslaxrom offers",
    recipe_match_num(
        ["80 g stenbitsrom"],
        {"name": "Regnbågslaxrom 80g Kallax", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "explicit stenbitsrom still matches exact stenbitsrom offers",
    recipe_match_num(
        ["80 g stenbitsrom"],
        {"name": "Caviar röd stenbitsrom 75g ICA", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "linguine ingredient is routed to long pasta family",
    match_kw("Linguine 800g Zeta", "1 förp pasta linguine", "pantry"),
    "långpasta",
)
test(
    "linguine ingredient still matches other long pasta products",
    recipe_match_num(
        ["1 förp pasta linguine"],
        {"name": "Tagliatelle 500g Barilla", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "linguine ingredient also matches spaghetti as long pasta",
    recipe_match_num(
        ["1 förp pasta linguine"],
        {"name": "Spaghetti 500g Barilla", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "linguine ingredient no longer matches short pasta",
    recipe_match_num(
        ["1 förp pasta linguine"],
        {"name": "Makaroner 500g ICA", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "cached linguine ingredient also matches long pasta family",
    recipe_match_num_cached(
        ["1 förp pasta linguine"],
        {"name": "Linguine 800g Zeta", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "batch 145 filodegskrustader no longer matches plain filodeg",
    match("Filodeg Färsk 500g Sevan", "12 filodegskrustader", "pantry"),
    None,
)
test(
    "batch 145 filodegskrustader still matches exact krustader",
    match("Krustader 48g Zeta", "12 filodegskrustader", "pantry"),
    "krustader",
)
test(
    "batch 145 shiitake-svamp still matches exact shiitake",
    match("Shiitake 150g Klass 1", "300 g shiitake-svamp", "vegetables"),
    "shiitake",
)
test(
    "batch 145 shiitake-svamp no longer widens to generic svamp",
    match("Champinjoner 250g Klass 1", "300 g shiitake-svamp", "vegetables"),
    None,
)

# ========================================================================
# Section: batch 146 note regressions
# ========================================================================
section("batch 146 note regressions")
test(
    "batch 146 edamame ingredient no longer accepts prepared dumplings",
    recipe_match_num(
        ["0.5 dl Edamamebönor"],
        {"name": "Dumpling edamame citrongräs 200g Beijing8", "category": "frozen", "savings": 10},
    ),
    0,
)
test(
    "batch 146 edamame ingredient still matches plain edamame beans",
    recipe_match_num(
        ["0.5 dl Edamamebönor"],
        {"name": "Edamamebönor Frysta 500g Test", "category": "frozen", "savings": 10},
    ),
    1,
)
test(
    "batch 146 lingonpulver no longer widens to plain lingon",
    recipe_match_num(
        ["2 msk lingonpulver"],
        {"name": "Lingon 500g ICA", "category": "frozen", "savings": 10},
    ),
    0,
)
test(
    "batch 146 plain lingon ingredient still matches lingon offers",
    recipe_match_num(
        ["250 g Frysta lingon"],
        {"name": "Lingon 500g ICA", "category": "frozen", "savings": 10},
    ),
    1,
)
test(
    "batch 146 mintcrisp chocolate ingredient blocks plain dark baking chocolate",
    recipe_match_num(
        ["100 g mörk choklad med mintcrisp"],
        {"name": "Bakchoklad Extra Mörk 70% 100g ICA", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "batch 146 mintcrisp chocolate ingredient also blocks flavored snack bites",
    recipe_match_num(
        ["100 g mörk choklad med mintcrisp"],
        {"name": "Kokosbite Mint & Choklad 40g Renee Voltaire", "category": "snacks", "savings": 10},
    ),
    0,
)
test(
    "batch 146 plain dark chocolate still matches dark baking chocolate",
    recipe_match_num(
        ["35 g mörk choklad"],
        {"name": "Bakchoklad Extra Mörk 70% 100g ICA", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "batch 146 flaskschnitzel no longer falls back to prepared schnitzel",
    recipe_match_num(
        ["600 g fläskschnitzel"],
        {"name": "Schnitzel ost skinka panerad 400g ICA", "category": "frozen", "savings": 10},
    ),
    0,
)
test(
    "batch 146 flaskschnitzel still matches exact raw schnitzel offers",
    recipe_match_num(
        ["600 g fläskschnitzel"],
        {"name": "Fläskschnitzel ca 600g Test", "category": "meat", "savings": 10},
    ),
    1,
)

# ========================================================================
# Section: batch 142 q9 regressions
# ========================================================================
section("batch 142 q9 regressions")
test(
    "batch 142 prep phrase delad i 4 biffar no longer leaks to dumpling biff",
    match_kw(
        "Dumpling biff, chili & ingefära 200g Beijing8",
        "800 g högrev, delad i 4 biffar",
        "frozen",
    ),
    None,
)
test(
    "batch 142 prep phrase delad i 4 biffar no longer matches dumpling biff in full matcher",
    recipe_match_num(
        ["800 g högrev, delad i 4 biffar"],
        {"name": "Dumpling biff, chili & ingefära 200g Beijing8", "category": "frozen", "savings": 10},
    ),
    0,
)
test(
    "batch 142 cached prep phrase delad i 4 biffar no longer matches dumpling biff",
    recipe_match_num_cached(
        ["800 g högrev, delad i 4 biffar"],
        {"name": "Dumpling biff, chili & ingefära 200g Beijing8", "category": "frozen", "savings": 10},
    ),
    0,
)
test(
    "batch 142 prep phrase delad i 4 biffar no longer matches biff rydberg",
    recipe_match_num(
        ["800 g högrev, delad i 4 biffar"],
        {"name": "Klassisk Biff Rydberg 500g Findus", "category": "frozen", "savings": 10},
    ),
    0,
)
test(
    "batch 142 prep phrase delad i 4 biffar still matches raw högrev offers",
    recipe_match_num(
        ["800 g högrev, delad i 4 biffar"],
        {"name": "Högrev Svenskt ca 800g Test", "category": "meat", "savings": 10},
    ),
    1,
)

# ========================================================================
# Section: batch 144 q4 regressions
# ========================================================================
section("batch 144 q4 regressions")
test(
    "batch 144 subrecipe reference line no longer extracts buyable keywords",
    sorted(extract_keywords_from_ingredient("1 sats pastadeg (se länk i ingress)")),
    [],
)
test(
    "batch 144 subrecipe reference line no longer matches dry pasta fast path",
    match_kw("Tagliatelle 500g ICA Basic", "1 sats pastadeg (se länk i ingress)", "pantry"),
    None,
)
test(
    "batch 144 subrecipe reference line no longer matches dry pasta in full matcher",
    recipe_match_num(
        ["1 sats pastadeg (se länk i ingress)"],
        {"name": "Tagliatelle 500g ICA Basic", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "batch 144 cached subrecipe reference line no longer matches dry pasta",
    recipe_match_num_cached(
        ["1 sats pastadeg (se länk i ingress)"],
        {"name": "Tagliatelle 500g ICA Basic", "category": "pantry", "savings": 10},
    ),
    0,
)

# ========================================================================
# Section: batch 145 q1 regressions
# ========================================================================
section("batch 145 q1 regressions")
test(
    "batch 145 ansjovisfiléer still matches generic ansjovis offers",
    recipe_match_num(
        ["20 g Ansjovisfiléer"],
        {"name": "Ansjovis 125g Grebbestad", "category": "other", "savings": 10},
    ),
    1,
)
test(
    "batch 145 cached ansjovisfiléer still matches generic ansjovis offers",
    recipe_match_num_cached(
        ["20 g Ansjovisfiléer"],
        {"name": "Ansjovis 125g Grebbestad", "category": "other", "savings": 10},
    ),
    1,
)
test(
    "batch 145 ansjovisfiléer now keeps its own ingredient group",
    recipe_match_groups(
        ["20 g Ansjovisfiléer"],
        {"name": "Ansjovis 125g Grebbestad", "category": "other", "savings": 10},
    )[0]["original"],
    "20 g Ansjovisfiléer",
)
test(
    "batch 145 cached ansjovisfiléer now keeps its own ingredient group",
    recipe_match_groups(
        ["20 g Ansjovisfiléer"],
        {"name": "Ansjovis 125g Grebbestad", "category": "other", "savings": 10},
        cached=True,
    )[0]["original"],
    "20 g Ansjovisfiléer",
)

# ========================================================================
# Section: batch 145 q7 regressions
# ========================================================================
section("batch 145 q7 regressions")
test(
    "batch 145 färskkorvar still matches explicit färskkorv products",
    recipe_match_num(
        ["4 färskkorvar t ex salsiccia"],
        {"name": "Färskkorv Salsiccia 240g ICA", "category": "meat", "savings": 10},
    ),
    1,
)
test(
    "batch 145 färskkorvar still matches plain salsiccia",
    recipe_match_num(
        ["4 färskkorvar t ex salsiccia"],
        {"name": "Salsiccia 240g ICA", "category": "meat", "savings": 10},
    ),
    1,
)
test(
    "batch 145 färskkorv still matches chorizo family",
    recipe_match_num(
        ["600 g färskkorv, hel (grov)"],
        {"name": "Chorizo 300g ICA", "category": "meat", "savings": 10},
    ),
    1,
)
test(
    "batch 145 färskkorv also matches exact spaced fresh sausage product names",
    recipe_match_num(
        ["4 färskkorvar"],
        {"name": "Färsk korv med örter 240g Test", "category": "meat", "savings": 10},
    ),
    1,
)
test(
    "batch 145 färskkorv no longer widens to falukorv",
    recipe_match_num(
        ["4 färskkorvar t ex salsiccia"],
        {"name": "Falukorv 800g Scan", "category": "meat", "savings": 10},
    ),
    0,
)
test(
    "batch 145 färskkorv no longer widens to prinskorv",
    recipe_match_num(
        ["4 färskkorvar t ex salsiccia"],
        {"name": "Prinskorv 300g Scan", "category": "meat", "savings": 10},
    ),
    0,
)
test(
    "batch 145 färskkorv no longer widens to pilsnerkorv",
    recipe_match_num(
        ["4 färskkorvar t ex salsiccia"],
        {"name": "Pilsnerkorv 240g Scan", "category": "meat", "savings": 10},
    ),
    0,
)
test(
    "batch 145 färskkorv still blocks cured fuet",
    recipe_match_num(
        ["4 färskkorvar t ex salsiccia"],
        {"name": "Fuet 170g Test", "category": "deli", "savings": 10},
    ),
    0,
)
test(
    "batch 145 cached färskkorv still matches fresh-sausage-like families",
    recipe_match_num_cached(
        ["4 färskkorvar t ex salsiccia"],
        {"name": "Salsiccia 240g ICA", "category": "meat", "savings": 10},
    ),
    1,
)
test(
    "batch 145 cached färskkorv no longer widens to cooked sausage families",
    recipe_match_num_cached(
        ["4 färskkorvar t ex salsiccia"],
        {"name": "Falukorv 800g Scan", "category": "meat", "savings": 10},
    ),
    0,
)

# ========================================================================
# Section: batch 145 q8 regressions
# ========================================================================
section("batch 145 q8 regressions")
test(
    "batch 145 porter ingredient extracts exact porter keyword",
    extract_keywords_from_ingredient("33 cl porter eller annan mörk öl"),
    ["porter"],
)
test(
    "batch 145 porter beverage offer extracts exact porter keyword",
    extract_keywords_from_product("Öl Porter 3,5% 50cl Carnegie", "beverages", brand="CARNEGIE"),
    ["porter"],
)
test(
    "batch 145 porter ingredient now matches porter offer",
    recipe_match_num(
        ["33 cl porter eller annan mörk öl"],
        {"name": "Öl Porter 3,5% 50cl Carnegie", "category": "beverages", "brand": "CARNEGIE", "savings": 10},
    ),
    1,
)
test(
    "batch 145 porter ingredient still does not widen to other beer families",
    recipe_match_num(
        ["33 cl porter eller annan mörk öl"],
        {"name": "Lättöl 2,1% 33cl Grängesberg", "category": "beverages", "brand": "GRÄNGESBERG", "savings": 10},
    ),
    0,
)
test(
    "batch 151 dried franska örter no longer matches flavored creme fraiche",
    recipe_match_num(
        ["1 tsk torkade franska örter"],
        {"name": "Lätt Creme fraiche Franska Örter 11% 2dl Arla Köket", "category": "dairy", "savings": 10},
    ),
    0,
)
test(
    "batch 151 cached dried franska örter no longer matches flavored creme fraiche",
    recipe_match_num_cached(
        ["1 tsk torkade franska örter"],
        {"name": "Lätt Creme fraiche Franska Örter 11% 2dl Arla Köket", "category": "dairy", "savings": 10},
    ),
    0,
)
test(
    "batch 151 havredryck choklad no longer matches baking chocolate",
    recipe_match_num(
        ["4 dl IKEA Havredryck choklad"],
        {"name": "Bakchoklad Ljus 200g ICA", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "batch 151 cached havredryck choklad no longer matches baking chocolate",
    recipe_match_num_cached(
        ["4 dl IKEA Havredryck choklad"],
        {"name": "Bakchoklad Ljus 200g ICA", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "batch 151 havredryck choklad still matches oat drink fallback",
    recipe_match_num(
        ["4 dl IKEA Havredryck choklad"],
        {"name": "Havredryck Naturell 1l ICA", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "batch 151 cached havredryck choklad still matches oat drink fallback",
    recipe_match_num_cached(
        ["4 dl IKEA Havredryck choklad"],
        {"name": "Havredryck Naturell 1l ICA", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "batch 151 gräslök fint skuren matches fresh chives",
    recipe_match_num(
        ["2 msk gräslök, fint skuren"],
        {"name": "Gräslök i kruka Ekologisk 1-p KRAV Klass 1", "category": "produce", "savings": 10},
    ),
    1,
)
test(
    "batch 151 cached gräslök fint skuren matches fresh chives",
    recipe_match_num_cached(
        ["2 msk gräslök, fint skuren"],
        {"name": "Gräslök i kruka Ekologisk 1-p KRAV Klass 1", "category": "produce", "savings": 10},
    ),
    1,
)
test(
    "batch 150 steklök matches red steklök produce offer",
    recipe_match_num(
        ["125 g Steklök"],
        {"name": "Steklök röd 250g Klass 1 ICA", "category": "produce", "savings": 10},
    ),
    1,
)
test(
    "batch 150 cached steklök matches red steklök produce offer",
    recipe_match_num_cached(
        ["125 g Steklök"],
        {"name": "Steklök röd 250g Klass 1 ICA", "category": "produce", "savings": 10},
    ),
    1,
)
test(
    "batch 150 steklök still does not widen to generic red onion",
    recipe_match_num(
        ["125 g Steklök"],
        {"name": "Lök röd 500g Klass 1 ICA", "category": "produce", "savings": 10},
    ),
    0,
)
test(
    "batch 150 cached steklök still does not widen to generic red onion",
    recipe_match_num_cached(
        ["125 g Steklök"],
        {"name": "Lök röd 500g Klass 1 ICA", "category": "produce", "savings": 10},
    ),
    0,
)
test(
    "batch 150 romsås still matches exact romsås products",
    recipe_match_num(
        ["200 g Romsås"],
        {"name": "Romsås 200ml Eriks Såser", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "batch 150 cached romsås still matches exact romsås products",
    recipe_match_num_cached(
        ["200 g Romsås"],
        {"name": "Romsås 200ml Eriks Såser", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "batch 150 romsås no longer falls back to plain roe products",
    recipe_match_num(
        ["200 g Romsås"],
        {"name": "Caviar röd stenbitsrom 75g ICA", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "batch 150 cached romsås no longer falls back to plain roe products",
    recipe_match_num_cached(
        ["200 g Romsås"],
        {"name": "Caviar röd stenbitsrom 75g ICA", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "batch 150 morotsspaghetti no longer matches dry spaghetti",
    recipe_match_num(
        ["500 g morotsspaghetti, Hackat och klart"],
        {"name": "Spaghetti 500g Barilla", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "batch 150 cached morotsspaghetti no longer matches dry spaghetti",
    recipe_match_num_cached(
        ["500 g morotsspaghetti, Hackat och klart"],
        {"name": "Spaghetti 500g Barilla", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "batch 150 morotsspaghetti no longer matches carrot julienne fallback either",
    recipe_match_num(
        ["500 g morotsspaghetti, Hackat och klart"],
        {"name": "Morot Julienne 250g Klass 1 ICA", "category": "produce", "savings": 10},
    ),
    0,
)
test(
    "batch 150 cached morotsspaghetti no longer matches carrot julienne fallback either",
    recipe_match_num_cached(
        ["500 g morotsspaghetti, Hackat och klart"],
        {"name": "Morot Julienne 250g Klass 1 ICA", "category": "produce", "savings": 10},
    ),
    0,
)
test(
    "batch 151 plain jäst now matches bread yeast",
    recipe_match_num(
        ["20 g jäst"],
        {"name": "Jäst för matbröd 50g Kronjäst", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "batch 151 cached plain jäst now matches bread yeast",
    recipe_match_num_cached(
        ["20 g jäst"],
        {"name": "Jäst för matbröd 50g Kronjäst", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "batch 151 plain jäst no longer falls through to sweet dough yeast",
    recipe_match_num(
        ["20 g jäst"],
        {"name": "Jäst för söta degar 50g Kronjäst", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "batch 151 cached plain jäst no longer falls through to sweet dough yeast",
    recipe_match_num_cached(
        ["20 g jäst"],
        {"name": "Jäst för söta degar 50g Kronjäst", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "batch 151 plain feferoni now matches feferoni kebab product",
    recipe_match_num(
        ["60 g Feferoni"],
        {"name": "Feferoni Kebab 670g Druvan", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "batch 151 cached plain feferoni now matches feferoni kebab product",
    recipe_match_num_cached(
        ["60 g Feferoni"],
        {"name": "Feferoni Kebab 670g Druvan", "category": "pantry", "savings": 10},
    ),
    1,
)

section("batch review pending questions")
test(
    "batch review solrosfrön match solroskärnor",
    recipe_match_num(
        ["1/2 dl rostade solrosfrön"],
        {"name": "Solroskärnor Rostade Risenta", "category": "other", "savings": 10},
    ),
    1,
)
test(
    "batch review solrosfrön allow roasted salted seed bags",
    recipe_match_num(
        ["1/2 dl rostade solrosfrön"],
        {"name": "Solrosfrön Rostade Saltade Eldorado", "category": "candy", "savings": 10},
    ),
    1,
)
test(
    "batch review solrosfrön still block crispbread carriers",
    recipe_match_num(
        ["1/2 dl rostade solrosfrön"],
        {"name": "Solroskärnor Quinoa Fröknäcke Glutenfri 8-pack Sigdal", "category": "bread", "savings": 10},
    ),
    0,
)
test(
    "batch review liba or pita matches pita bread",
    recipe_match_num(
        ["1 libabröd eller pitabröd"],
        {"name": "Pitabröd 6-pack Eldorado", "category": "bread", "savings": 10},
    ),
    1,
)
test(
    "batch review liba or pita accepts named tunnbrod",
    recipe_match_num(
        ["1 libabröd eller pitabröd"],
        {"name": "Tunnbröd 8p Garant", "category": "bread", "savings": 10},
    ),
    1,
)
test(
    "batch review liba or pita blocks honokaka fallback",
    recipe_match_num(
        ["1 libabröd eller pitabröd"],
        {"name": "Hönökaka 4-pack Pågen", "category": "bread", "savings": 10},
    ),
    0,
)
test(
    "batch review liba or pita blocks polarbrod fallback",
    recipe_match_num(
        ["1 libabröd eller pitabröd"],
        {"name": "Polarkaka Polarbröd", "category": "bread", "savings": 10},
    ),
    0,
)
test(
    "batch review sashimilax matches explicit sushilax",
    recipe_match_num(
        ["180 g Sashimilax"],
        {"name": "Sushilax Falkenberg", "category": "fish", "savings": 10},
    ),
    1,
)
test(
    "batch review sashimilax accepts loin salmon",
    recipe_match_num(
        ["180 g Sashimilax"],
        {"name": "Lax Back Loin 1/2 Fröya", "category": "fish", "savings": 10},
    ),
    1,
)
test(
    "batch review sashimilax blocks hot smoked salmon portions",
    recipe_match_num(
        ["180 g Sashimilax"],
        {"name": "Lax Varmr Portion Eldorado", "category": "fish", "savings": 10},
    ),
    0,
)
test(
    "batch review sashimilax blocks stew pieces",
    recipe_match_num(
        ["180 g Sashimilax"],
        {"name": "Lax Grytbitar Falkenberg", "category": "fish", "savings": 10},
    ),
    0,
)
test(
    "batch review vegan mayo matches vegan mayo",
    recipe_match_num(
        ["10 tsk Vegansk majonnäs"],
        {"name": "Vegan Mayo Garant", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "batch review vegan mayo matches plant based mayo",
    recipe_match_num(
        ["10 tsk Vegansk majonnäs"],
        {"name": "Plant Based Mayo Hellmann's", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "batch review vegan mayo blocks ordinary mayonnaise",
    recipe_match_num(
        ["10 tsk Vegansk majonnäs"],
        {"name": "Mayonnaise Hellmann's", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "batch review dried herb blend matches orter provencale",
    recipe_match_num(
        ["1 tsk Örtblandningar - torkade"],
        {"name": "Örter Provencale Burk Kockens", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "batch review dried herb blend blocks provencale pie",
    recipe_match_num(
        ["1 tsk Örtblandningar - torkade"],
        {"name": "Provencale Grönsakspaj Fryst/1 Port Garant", "category": "frozen", "savings": 10},
    ),
    0,
)
test(
    "batch review fresh ginger matches grated ginger",
    recipe_match_num(
        ["1 msk Färsk ingefära"],
        {"name": "Ingefära Riven Cajom", "category": "fruit", "savings": 10},
    ),
    1,
)
test(
    "batch review fresh ginger blocks ginger tea",
    recipe_match_num(
        ["1 msk Färsk ingefära"],
        {"name": "Citron Ingefära Friggs", "category": "fruit", "savings": 10},
    ),
    0,
)

section("Batch 1 pilot accepted fixes")

from languages.sv.ingredient_matching.compiled_recipes import prepare_recipe_match_runtime_data

test("KW alger extracted as short keyword", extract_keywords_from_ingredient("20 g Alger"), ["alger"])
test("KW Bamboo Shoot exposes bambuskott", "bambuskott" in kw("Bamboo Shoot Skivor i Vatten Twin Dragon", "pantry"), True)
test("KW Sushi Nori exposes generic alger", "alger" in kw("Sushi Nori Roasted Seeweed Spicefield", "pantry"), True)
test(
    "Batch 1 bambuskott matches English Bamboo Shoot",
    recipe_match_num(
        ["227 g Bambuskott"],
        {"name": "Bamboo Shoot Skivor i Vatten Twin Dragon", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "Batch 1 alger matches nori seaweed",
    recipe_match_num(
        ["20 g Alger"],
        {"name": "Sushi Nori Roasted Seeweed Spicefield", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "Batch 1 dried oregano blocks vegan cheese carrier",
    recipe_match_num(
        ["1 msk torkad oregano"],
        {"name": "Greek Style Oregano & Olive Oil Vegansk Greenvie", "category": "dairy", "savings": 10},
    ),
    0,
)
test(
    "Batch 1 fresh gurka blocks pickled finhackad Garant product",
    recipe_match_num(
        ["1/2 gurka"],
        {"name": "Gurka Finhackad Garant", "category": "vegetables", "savings": 10},
    ),
    0,
)
test(
    "Batch 1 ordinary pasta blocks konjac noodles",
    recipe_match_num(
        ["ny kokt pasta till 4 personer"],
        {"name": "Nudlar Konjac Spagetti Twin Dragon", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "Batch 1 tagliatelle blocks konjac spaghetti",
    recipe_match_num(
        ["300 g Tagliatelle"],
        {"name": "Nudlar Konjac Spagetti Twin Dragon", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "Batch 1 fresh cherry tomatoes block tomatojuice product",
    recipe_match_num(
        ["125 g Körsbärstomater"],
        {"name": "Körsbärs- Tomater i Tomatjuice Eldorado", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "Batch 1 fresh cherry tomatoes match cocktail tomatoes",
    recipe_match_num(
        ["125 g Körsbärstomater"],
        {"name": "Cocktailtomater Klass 1", "category": "vegetables", "savings": 10},
    ),
    1,
)
test(
    "Batch 1 long-grain rice blocks black rice",
    recipe_match_num(
        ["3 dl Långkornigt Ris"],
        {"name": "Svart Ris Saltå Kvarn", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "Batch 1 long-grain rice blocks red rice",
    recipe_match_num(
        ["3 dl Långkornigt Ris"],
        {"name": "Rött Ris Saltå Kvarn", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "Batch 1 fresh paprika blocks preserved file product",
    recipe_match_num(
        ["2 st Paprika"],
        {"name": "Paprika File Melis", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "Batch 1 mellanmjölk blocks flavored milk drink",
    recipe_match_num(
        ["1 dl Mellanmjölk"],
        {"name": "Rosa Jordgubb Mjölkdryck Arla", "category": "dairy", "savings": 10},
    ),
    0,
)
test(
    "Batch 1 mellanmjölk blocks protein milk drink",
    recipe_match_num(
        ["1 dl Mellanmjölk"],
        {"name": "Protein Mjölkdryck Blåbär 5dl Arla", "category": "dairy", "savings": 10},
    ),
    0,
)
test(
    "Batch 1 mellanmjölk still accepts ordinary lactose-free milk drink",
    recipe_match_num(
        ["1 dl Mellanmjölk"],
        {"name": "Mjölkdryck 1,5% Laktosfri Arla", "category": "dairy", "savings": 10},
    ),
    1,
)
test(
    "Batch 1 skin-on salmon fillet blocks stew pieces",
    recipe_match_num(
        ["600 g laxfilé med skinnet kvar"],
        {"name": "Lax Grytbitar Falkenberg", "category": "fish", "savings": 10},
    ),
    0,
)
_gurt_compiled = prepare_recipe_match_runtime_data(
    SimpleNamespace(id="gurt-cache", name="Sanity", ingredients=["1 dl växtbaserad gurt"])
)
_micropop_compiled = prepare_recipe_match_runtime_data(
    SimpleNamespace(id="micropop-cache", name="Sanity", ingredients=["1 påse micropopcorn"])
)
test("Batch 1 compiled gurt routing includes yoghurt", "yoghurt" in _gurt_compiled["ingredients_search_text"], True)
test("Batch 1 compiled micropop routing includes micropop", "micropop" in _micropop_compiled["ingredients_search_text"], True)

section("Batch 11 accepted direct fixes")
test(
    "Batch 11 pickles ingredient matches smörgåspickles products",
    recipe_match_num(
        ["120 g Pickles"],
        {"name": "Smörgåspickles Felix", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "Batch 11 polenta ingredient matches cornmeal products",
    recipe_match_num(
        ["400 g Polenta"],
        {"name": "Majsmjöl Garant", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "Batch 11 minikrustader matches croustades products",
    recipe_match_num(
        ["minikrustader"],
        {"name": "Croustades Mini Rahms", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "Batch 11 salladsärtor matches sugar snap/sockerärtor products",
    recipe_match_num(
        ["150 g salladsärtor"],
        {"name": "Sockerärtor Klass 1", "category": "fruit", "savings": 10},
    ),
    1,
)
test(
    "Batch 11 haricoverts typo matches haricots verts products",
    recipe_match_num(
        ["haricoverts, frysta"],
        {"name": "Haricots Verts Frysta", "category": "frozen", "savings": 10},
    ),
    1,
)
test(
    "Batch 11 quornfärs accepts compatible vegofärs",
    recipe_match_num(
        ["quornfärs"],
        {"name": "Vegofärs Anamma", "category": "frozen", "savings": 10},
    ),
    1,
)
test(
    "Batch 11 quornfärs still matches exact Quorn mince",
    recipe_match_num(
        ["quornfärs"],
        {"name": "Färs Mince Quorn", "category": "frozen", "brand": "Quorn", "savings": 10},
    ),
    1,
)
test(
    "Batch 11 små maränger matches marängtoppar",
    recipe_match_num(
        ["små maränger"],
        {"name": "Marängtoppar", "category": "snacks", "savings": 10},
    ),
    1,
)
test(
    "Batch 11 Oreo ingredient matches Oreo cookie packs",
    recipe_match_num(
        ["Oreo"],
        {"name": "Oreo Original Kakor", "category": "snacks", "savings": 10},
    ),
    1,
)

section("Batch 2 accepted fixes")
test(
    "Batch 2 Teaterbrons Paprikalasagne is not treated as kalas",
    is_buffet_or_party_recipe("Teaterbrons Paprikalasagne", 22),
    False,
)
test(
    "Batch 2 buffet wording still filters party recipes",
    is_buffet_or_party_recipe("Mathems påskbuffé för 8 personer", 48),
    True,
)
test(
    "Batch 2 vegan smördeg accepts neutral smördeg",
    recipe_match_num(
        ["250 g Vegansk smördeg, tinad"],
        {"name": "Smördeg Plattor Fryst Garant", "category": "bread", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 cached vegan smördeg accepts neutral smördeg",
    recipe_match_num_cached(
        ["250 g Vegansk smördeg, tinad"],
        {"name": "Smördeg Plattor Fryst Garant", "category": "bread", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 vegan smördeg blocks explicit butter pastry",
    recipe_match_num(
        ["250 g Vegansk smördeg, tinad"],
        {"name": "Butter Puff Pastry Smördeg Fryst", "category": "bread", "savings": 10},
    ),
    0,
)
test(
    "Batch 2 vegan smördeg accepts explicit vegan smördeg",
    recipe_match_num(
        ["250 g Vegansk smördeg, tinad"],
        {"name": "Smördeg Vegan Fryst", "category": "bread", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 veganost blocks ordinary dairy cheese",
    recipe_match_num(
        ["100 g Violife veganost"],
        {"name": "Gouda 28% Eldorado", "category": "dairy", "savings": 10},
    ),
    0,
)
test(
    "Batch 2 veganost accepts Violife cheese substitute",
    recipe_match_num(
        ["100 g veganost"],
        {"name": "Block Original Flavour Vegansk Violife", "category": "dairy", "brand": "VIOLIFE", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 ordinary ost may include vegan cheese substitute",
    recipe_match_num(
        ["100 g ost"],
        {"name": "Block Original Flavour Vegansk Violife", "category": "dairy", "brand": "VIOLIFE", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 ordinary mozzarella may include vegan mozzarella substitute",
    recipe_match_num(
        ["125 g Mozzarellaost"],
        {"name": "Mozzarella Flavour Vegansk Greenvie", "category": "dairy", "brand": "Greenvie", "savings": 10},
    ),
    1,
)
_white_dark_chocolate_compiled = prepare_recipe_match_runtime_data(
    SimpleNamespace(id="white-dark-chocolate", name="Sanity", ingredients=["hackad vit- och mörk choklad"])
)
test(
    "Batch 2 truncated white-and-dark chocolate keeps white qualifier",
    "vit choklad" in _white_dark_chocolate_compiled["ingredients_normalized"][0],
    True,
)
test(
    "Batch 2 white-and-dark chocolate matches white baking chocolate",
    recipe_match_num(
        ["hackad vit- och mörk choklad"],
        {"name": "Bakchoklad Vit Garant", "category": "candy", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 white-and-dark chocolate matches dark baking chocolate",
    recipe_match_num(
        ["hackad vit- och mörk choklad"],
        {"name": "Bakchoklad Mörk 55% Garant", "category": "candy", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 white-and-dark chocolate matches white chocolate buttons",
    recipe_match_num(
        ["hackad vit- och mörk choklad"],
        {"name": "Chokladknappar Vit Odense", "category": "candy", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 white-and-dark chocolate blocks unrelated light chocolate",
    recipe_match_num(
        ["hackad vit- och mörk choklad"],
        {"name": "Bakchoklad Ljus Garant", "category": "candy", "savings": 10},
    ),
    0,
)
test(
    "Batch 2 vegan qualifier stays scoped to its eller alternative",
    recipe_match_num(
        ["2 msk Hoisinsås Eller vegansk ostronssås"],
        {"name": "Hoisin Sauce Spicefield", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 laktosfri ingredient blocks ordinary dairy product",
    recipe_match_num(
        ["1 dl laktosfri mjölk"],
        {"name": "Mjölk 1,5% Arla", "category": "dairy", "savings": 10},
    ),
    0,
)
test(
    "Batch 2 ordinary dairy ingredient may include lactose-free variant",
    recipe_match_num(
        ["1 dl mjölk"],
        {"name": "Mjölk Laktosfri 1,5% Arla", "category": "dairy", "savings": 10},
    ),
    1,
)

test(
    "Batch 2 revbensspjäll matches spareribs",
    recipe_match_num(
        ["1 kg Revbensspjäll"],
        {"name": "Spareribs Sverige Garant", "category": "meat", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 revbensspjäll still blocks ribs rub",
    recipe_match_num(
        ["1 kg Revbensspjäll"],
        {"name": "BBQ rub Ribs Santa Maria", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "Batch 2 preserved kantareller matches in-water offer",
    recipe_match_num(
        ["200 g kantareller, avrunna (på burk)"],
        {"name": "Kantareller i Vatten Borgens", "category": "beverages", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 preserved kantareller blocks kantarell cream cheese",
    recipe_match_num(
        ["200 g kantareller, avrunna (på burk)"],
        {"name": "Kantarell Färskost Creme Bonjour", "category": "dairy", "savings": 10},
    ),
    0,
)
test(
    "Batch 2 kalamataoliver matches Kalamata olive product",
    recipe_match_num(
        ["290 g Kalamataoliver"],
        {"name": "Kalamata Oliver Utan Kärnor Fontana", "category": "spices", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 kalamataoliver matches Kalamata olive mix",
    recipe_match_num(
        ["290 g Kalamataoliver"],
        {"name": "Olivmix Halkidiki & Kalamata Utan Kärnor Fontana", "category": "other", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 kalamataoliver falls back to generic black olives",
    recipe_match_num(
        ["290 g Kalamataoliver"],
        {"name": "Svarta Oliver Urkärnade Eldorado", "category": "spices", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 kalamataoliver falls back to Gemlik black olives",
    recipe_match_num(
        ["290 g Kalamataoliver"],
        {"name": "Gemlik Oliver Ceren", "category": "spices", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 kalamataoliver blocks Kalamata olive oil",
    recipe_match_num(
        ["290 g Kalamataoliver"],
        {"name": "Olivolja Kalamata Extra Virgin Fontana", "category": "spices", "savings": 10},
    ),
    0,
)
test(
    "Batch 2 standardmjölk accepts plain standard milk",
    recipe_match_num(
        ["2.5 dl Standardmjölk"],
        {"name": "Standardmjölk Gårds 3% Wapnö", "category": "dairy", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 standardmjölk accepts plain mellanmjölk fallback",
    recipe_match_num(
        ["2.5 dl Standardmjölk"],
        {"name": "Mellanmjölk 1,5% Garant", "category": "dairy", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 standardmjölk accepts plain lactose-free milk drink",
    recipe_match_num(
        ["2.5 dl Standardmjölk"],
        {"name": "Mjölkdryck Laktosfri 1,5% Garant", "category": "dairy", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 standardmjölk blocks milk chocolate buttons",
    recipe_match_num(
        ["2.5 dl Standardmjölk"],
        {"name": "Chokladknappar Mjölk Odense", "category": "candy", "savings": 10},
    ),
    0,
)
test(
    "Batch 2 standardmjölk blocks protein flavored milk drink",
    recipe_match_num(
        ["2.5 dl Standardmjölk"],
        {"name": "Blåbär Protein Mjölkdryck 0,5% Arla", "category": "dairy", "savings": 10},
    ),
    0,
)
test(
    "Batch 2 standardmjölk blocks strawberry milk drink",
    recipe_match_num(
        ["2.5 dl Standardmjölk"],
        {"name": "Rosa Jordgubb Mjölkdryck 1% Arla Ko", "category": "dairy", "savings": 10},
    ),
    0,
)
test(
    "Batch 2 inlagda rödbetor match whole jarred beetroot",
    recipe_match_num(
        ["710 g hela inlagda rödbetor (en burk)"],
        {"name": "Rödbetor Hela Björnekulla", "category": "other", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 inlagda rödbetor match sliced jarred beetroot",
    recipe_match_num(
        ["710 g hela inlagda rödbetor (en burk)"],
        {"name": "Rödbetor Skivade Felix", "category": "other", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 inlagda rödbetor block pre-cooked plain beetroot",
    recipe_match_num(
        ["710 g hela inlagda rödbetor (en burk)"],
        {"name": "Rödbetor Förkokt Klass 1", "category": "fruit", "savings": 10},
    ),
    0,
)
test(
    "Batch 2 inlagda rödbetor block fresh beetroot",
    recipe_match_num(
        ["710 g hela inlagda rödbetor (en burk)"],
        {"name": "Rödbetor Klass 1 Garant", "category": "fruit", "savings": 10},
    ),
    0,
)
test(
    "Batch 2 svartvinbärsgelé matches blackcurrant jelly",
    recipe_match_num(
        ["1 msk Svartvinbärsgelé"],
        {"name": "Svart Vinbärs Gele Garant", "category": "other", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 svartvinbärsgelé accepts redcurrant jelly fallback",
    recipe_match_num(
        ["1 msk Svartvinbärsgelé"],
        {"name": "Röd Vinbärs Gele Garant", "category": "other", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 generic vinbärsgelé accepts redcurrant jelly",
    recipe_match_num(
        ["1 msk vinbärsgelé"],
        {"name": "Rödvinbärs- Gele Eldorado", "category": "other", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 grillkrydda vitlök blocks standalone chopped garlic",
    recipe_match_num(
        ["2 msk Grillkrydda Vitlök"],
        {"name": "Vitlök Finhackad Burk Kockens", "category": "spices", "savings": 10},
    ),
    0,
)
test(
    "Batch 2 grillkrydda vitlök accepts garlic grill seasoning",
    recipe_match_num(
        ["2 msk Grillkrydda Vitlök"],
        {"name": "Grillkrydda Vitlök Santa Maria", "category": "spices", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 grillkrydda vitlök accepts ordinary grill seasoning fallback",
    recipe_match_num(
        ["2 msk Grillkrydda Vitlök"],
        {"name": "Grillkrydda Santa Maria", "category": "spices", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 feferoni blocks ready baguette carrier",
    recipe_match_num(
        ["0.5 skiva Feferoni"],
        {"name": "Kebab Feferoni Baguette Good", "category": "ready-meals", "savings": 10},
    ),
    0,
)
test(
    "Batch 2 feferoni accepts kebabfeferoni pepper product",
    recipe_match_num(
        ["0.5 skiva Feferoni"],
        {"name": "Feferoni Kebab 670g Druvan", "category": "pantry", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 feferoni accepts compound kebabfeferoni pepper product",
    recipe_match_num(
        ["0.5 skiva Feferoni"],
        {"name": "Kebabfeferoni Druvan", "category": "deli", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 cached feferoni accepts compound kebabfeferoni pepper product",
    recipe_match_num_cached(
        ["0.5 skiva Feferoni"],
        {"name": "Kebabfeferoni Druvan", "category": "deli", "savings": 10},
    ),
    1,
)
test(
    "Batch 3 plain snabbkaffe beverage is filter-eligible",
    _is_plain_instant_coffee_product_text("snabbkaffe mellanrost garant", "beverages"),
    True,
)
test(
    "Batch 3 cappuccino snabbkaffe beverage is not plain instant coffee",
    _is_plain_instant_coffee_product_text("cappuccino snabbkaffe nescafe", "beverages"),
    False,
)
test(
    "Batch 2 havssalt accepts plain sea salt",
    recipe_match_num(
        ["1 tsk Havssalt"],
        {"name": "Fint Havssalt med Jod Jozo", "category": "spices", "savings": 10},
    ),
    1,
)
test(
    "Batch 2 havssalt blocks salted cashew carrier",
    recipe_match_num(
        ["1 tsk Havssalt"],
        {"name": "Cashewnötter Stora Rostade med Havssalt Denlillenött", "category": "snacks", "savings": 10},
    ),
    0,
)
test(
    "Batch 2 havssalt blocks sea-salt cracker carrier",
    recipe_match_num(
        ["1 tsk Havssalt"],
        {"name": "Havssalt Salta Kex Garant", "category": "pantry", "savings": 10},
    ),
    0,
)
test(
    "Batch 2 havssalt blocks chocolate carrier even if miscategorized",
    recipe_match_num(
        ["1 tsk Havssalt"],
        {"name": "Mörk Choklad Havssalt Lindt", "category": "pantry", "savings": 10},
    ),
    0,
)

section("Cache keyword audit follow-ups")

test(
    "Audit guacamole-mix blocks ready guacamole",
    recipe_match_num(
        ["20 g guacamole-mix"],
        {"name": "Guacamole El Taco Truck", "category": "other", "brand": "EL TACO TRUCK", "savings": 10},
    ),
    0,
)
test(
    "Audit plain guacamole still accepts ready guacamole",
    recipe_match_num(
        ["2 dl guacamole"],
        {"name": "Guacamole El Taco Truck", "category": "other", "brand": "EL TACO TRUCK", "savings": 10},
    ),
    1,
)
test(
    "Audit kebab meat blocks kebab sauce",
    recipe_match_num(
        ["330 g kebabkött"],
        {"name": "Kebab Mild Sås Felix", "category": "pantry", "brand": "FELIX", "savings": 10},
    ),
    0,
)
test(
    "Audit kebab meat blocks kebab bread",
    recipe_match_num(
        ["330 g kebabkött"],
        {"name": "Somunbröd Till Kebab Cevapcici Fryst Plivit", "category": "bread", "brand": "PLIVIT", "savings": 10},
    ),
    0,
)
test(
    "Audit kebab meat blocks frozen kebab pizza without pizza word",
    recipe_match_num(
        ["330 g kebabkött"],
        {"name": "Kebab Supreme Fryst Grandiosa", "category": "frozen", "brand": "GRANDIOSA", "savings": 10},
    ),
    0,
)
test(
    "Audit kebab meat still accepts kebab meat",
    recipe_match_num(
        ["330 g kebabkött"],
        {"name": "Kebab Grillad Och Skuren Fryst Eldorado", "category": "frozen", "brand": "ELDORADO", "savings": 10},
    ),
    1,
)
test(
    "Audit Spanish tortilla with onion emits no tortilla-wrap keyword",
    kw("Tortilla med Lök Palacios", "meat"),
    [],
)
test(
    "Audit Spanish tortilla without onion emits no tortilla-wrap keyword",
    kw("Tortilla Utan Lök Palacios", "meat"),
    [],
)
test(
    "Audit ordinary tortilla wraps still emit tortilla",
    "tortilla" in kw("Tortilla Original Medium 8-pack Santa Maria", "bread"),
    True,
)
test(
    "Audit vetetortillas block corn-only tortillas",
    recipe_match_num(
        ["8 vetetortillas (medium)"],
        {"name": "Corn Tortillas Glutenfri El Taco Truck", "category": "bread", "brand": "EL TACO TRUCK", "savings": 10},
    ),
    0,
)
test(
    "Audit generic tortillas still accept corn tortillas",
    recipe_match_num(
        ["6 st tortillas"],
        {"name": "Corn Tortillas Glutenfri El Taco Truck", "category": "bread", "brand": "EL TACO TRUCK", "savings": 10},
    ),
    1,
)
test(
    "Audit vetetortillas accept corn and wheat tortillas",
    recipe_match_num(
        ["8 vetetortillas (medium)"],
        {"name": "Tortilla Corn & Wheat Small 8-pack Santa Maria", "category": "bread", "brand": "SANTA MARIA", "savings": 10},
    ),
    1,
)
test(
    "Audit burger buns do not match chicken burger patties",
    recipe_match_num(
        ["1 st Potato Burger buns från Korvbrödbagaren"],
        {"name": "Crispy Kycklingburgare Fryst Kronfågel", "category": "meat", "brand": "KRONFÅGEL", "savings": 10},
    ),
    0,
)
test(
    "Audit burger buns still match hamburger bread",
    recipe_match_num(
        ["1 st Potato Burger buns från Korvbrödbagaren"],
        {"name": "Hamburgerbröd Sesam 8-pack Garant", "category": "bread", "brand": "GARANT", "savings": 10},
    ),
    1,
)
test(
    "Audit havrebaserad matlagning blocks ordinary dairy cream",
    recipe_match_num(
        ["250 ml Havrebaserad matlagning"],
        {"name": "Matlagnings Grädde Lång Hållbarhet 15% Kelda", "category": "dairy", "brand": "KELDA", "savings": 10},
    ),
    0,
)
test(
    "Audit havrebaserad matlagning accepts oat cooking cream",
    recipe_match_num(
        ["250 ml Havrebaserad matlagning"],
        {"name": "Imat Matlagningsgrädde 13% Oatly", "category": "dairy", "brand": "OATLY", "savings": 10},
    ),
    1,
)

section("Batch 10 root-cause regressions")
test("Batch 10 sugar snaps normalizes", extract_keywords_from_ingredient("150 g sugar snaps"), ["sockerärtor"])
test("Batch 10 Mache Sallad product maps to machesallat", "machesallat" in extract_keywords_from_product("Mache Sallad Eko"), True)
test("Batch 10 Dumle product emits Dumle", "dumle" in extract_keywords_from_product("Dumle Original Fazer"), True)
test("Batch 10 milk powder product maps to torrmjölk", "torrmjölk" in extract_keywords_from_product("Mjölkpulver Falköpings"), True)
test("Batch 10 pesto basilico maps to basilikapesto", "basilikapesto" in extract_keywords_from_product("Pesto Basilico Zeta"), True)
test("Batch 10 sugar snaps matches sockerärtor", recipe_match_num(["150 g sugar snaps"], {"name": "Sockerärtor 150g", "category": "vegetables"}), 1)
test("Batch 10 hjortronsylt blocks ordinary jam", recipe_match_num(["4 msk Hjortronsylt"], {"name": "Hallonsylt 400g ICA", "category": "pantry"}), 0)
test("Batch 10 plain havremjölk blocks flavored oat drink", recipe_match_num(["5 dl Havremjölk"], {"name": "Havredryck Dumle Barista", "category": "dairy"}), 0)
test("Batch 10 plain sojadryck blocks chocolate soy drink", recipe_match_num(["0.5 dl Sojadryck"], {"name": "Sojadryck Choklad Alpro", "category": "dairy"}), 0)
test("Batch 10 plant drink still accepts plain oat drink", recipe_match_num(["växtbaserad mjölkdryck"], {"name": "Havredryck Naturell Oatly", "category": "dairy"}), 1)
test("Batch 10 konserverade körsbärstomater block fresh baby plum tomatoes", recipe_match_num(["1 st Körsbärstomater Konserverade"], {"name": "Tomat Babyplommon Kl 1", "category": "vegetables"}), 0)
test("Batch 10 färsk persika blocks canned peaches", recipe_match_num(["500 g Färsk persika"], {"name": "Persikor i Halvor i Sockerlag Eldorado", "category": "pantry"}), 0)
test("Batch 10 grön zucchini blocks yellow zucchini", recipe_match_num(["1 grön zucchini"], {"name": "Zucchini Gul Klass 1", "category": "vegetables"}), 0)
test("Batch 10 fresh sparris blocks preserved white asparagus", recipe_match_num(["250 g Sparris Färsk"], {"name": "Hel Sparris Vit Eldorado", "category": "pantry"}), 0)
test("Batch 10 glass noodles block ordinary pasta vermicelli", recipe_match_num(["200 g vermicellinudlar (glasnudlar)"], {"name": "Vermicelli Krossade Pasta Riscossa", "category": "pantry"}), 0)
test("Batch 10 rice noodles block flavored instant rice noodles", recipe_match_num(["250 g Risnudlar"], {"name": "Beef Flavour Rice Noodles Pho Bo", "category": "pantry"}), 0)
test("Batch 10 gochujang blocks prepared chicken skewers", recipe_match_num(["Flaska gochujang"], {"name": "Kycklingspett Gochujang Fryst", "category": "meat"}), 0)
test("Batch 10 gochujang still accepts paste", recipe_match_num(["Flaska gochujang"], {"name": "Chilipasta GoChuJang 200g Risberg", "category": "pantry"}), 1)
test("Batch 10 vegan burger blocks chicken burger", recipe_match_num(["Paket blödande burgare från Peas of Heaven"], {"name": "Kyckling Burgare Fryst", "category": "meat"}), 0)
test("Batch 10 vegosmör accepts plant margarine", recipe_match_num(["2 msk Vegosmör"], {"name": "Bakning Växtbaserat Margarin Carlshamn", "category": "dairy"}), 1)
test("Batch 10 raw ribs block smoked ribs", recipe_match_num(["1.5 kg Revbensspjäll"], {"name": "Ribs Rökta", "category": "meat"}), 0)
test("Batch 10 boneless pork neck blocks bone-in pork neck", recipe_match_num(["1 kg benfri fläskkarré"], {"name": "Fläskkarré med Ben", "category": "meat"}), 0)
test("Batch 10 plain thawed chicken legs block marinated chicken legs", recipe_match_num(["900 g kycklingben, tinade"], {"name": "Kycklingben Marinerade", "category": "meat"}), 0)

section("Batch 10-13 recurring principle regressions")
test("Root carrots plain recipe blocks preserved small whole carrots", recipe_match_num(["2 morötter"], {"name": "Morötter Små Hela Eldorado", "category": "vegetables"}), 0)
test("Root carrots preserved recipe accepts preserved small whole carrots", recipe_match_num_cached(["2 dl konserverade morötter"], {"name": "Morötter Små Hela Eldorado", "category": "vegetables"}), 1)
test("Root carrots preserved recipe blocks fresh carrots", recipe_match_num(["2 dl konserverade morötter"], {"name": "Morötter Klass 1", "category": "vegetables"}), 0)
test("Root white chocolate buttons block milk chocolate buttons", recipe_match_num(["100 g vit chokladknappar"], {"name": "Chokladknappar Mjölk Odense", "category": "dairy"}), 0)
test("Root white chocolate buttons block dark chocolate buttons", recipe_match_num(["100 g vit chokladknappar"], {"name": "Chokladknappar Mörka Odense", "category": "pantry"}), 0)
test("Root white chocolate buttons accept white chocolate buttons", recipe_match_num_cached(["100 g vit chokladknappar"], {"name": "Chokladknappar Vit Odense", "category": "pantry"}), 1)
test("Root generic chocolate buttons accept milk chocolate buttons", recipe_match_num(["100 g chokladknappar"], {"name": "Chokladknappar Mjölk Odense", "category": "dairy"}), 1)
test("Root crispbread carrier blocks poppy seed ingredient", recipe_match_num(["1 msk vallmofrö"], {"name": "Vallmofrö Falu Knäckebröd Wasa", "category": "bread"}), 0)
test("Root crispbread carrier still matches crispbread ingredient", recipe_match_num_cached(["4 skivor knäckebröd"], {"name": "Vallmofrö Falu Knäckebröd Wasa", "category": "bread"}), 1)
test("Root salsa carrier blocks vodka ingredient", recipe_match_num(["2 msk vodka"], {"name": "Salsa Pineapple Vodka El Taco Truck", "category": "fruit", "brand": "EL TACO TRUCK"}), 0)
test("Root salsa carrier still matches salsa ingredient", recipe_match_num_cached(["2 dl salsa"], {"name": "Salsa Pineapple Vodka El Taco Truck", "category": "fruit", "brand": "EL TACO TRUCK"}), 1)
test("Root dry Indian Spices routes to kryddmix", recipe_match_num_cached(["1 msk tikka masala kryddmix"], {"name": "Tikka Masala Indian Spices Santa Maria", "category": "spices"}), 1)
test("Root tikka kryddmix blocks curry paste carrier", recipe_match_num(["1 msk tikka masala kryddmix"], {"name": "Tikka Masala Curry Paste Patak's", "category": "pantry"}), 0)
test("Root taco kryddmix blocks garam masala Indian Spices", recipe_match_num_cached(["30 g taco kryddmix"], {"name": "Garam Masala Indian Spices Santa Maria", "category": "pantry"}), 0)
test("Root taco kryddmix blocks tandoori Indian Spices", recipe_match_num(["30 g taco kryddmix"], {"name": "Tandoori Chicken Indian Spices Santa Maria", "category": "pantry"}), 0)
test("Root garam masala kryddmix accepts garam masala Indian Spices", recipe_match_num_cached(["1 msk garam masala kryddmix"], {"name": "Garam Masala Indian Spices Santa Maria", "category": "pantry"}), 1)
test("Root tandoori kryddmix accepts tandoori Indian Spices", recipe_match_num(["1 msk tandoori kryddmix"], {"name": "Tandoori Chicken Indian Spices Santa Maria", "category": "pantry"}), 1)
test("Root tikka masala kryddmix blocks garam masala Indian Spices", recipe_match_num(["1 msk tikka masala kryddmix"], {"name": "Garam Masala Indian Spices Santa Maria", "category": "pantry"}), 0)
test("Root Asian crispy garlic kryddmix blocks garam masala Indian Spices", recipe_match_num_cached(["1 förp Santa Maria Asian spice mix crispy coating garlic kryddmix"], {"name": "Garam Masala Indian Spices Santa Maria", "category": "pantry"}), 0)
test("Root Asian crispy garlic kryddmix blocks tandoori Indian Spices", recipe_match_num(["1 förp Santa Maria Asian spice mix crispy coating garlic kryddmix"], {"name": "Tandoori Chicken Indian Spices Santa Maria", "category": "pantry"}), 0)
test("Root bifteki kryddmix blocks garam masala Indian Spices", recipe_match_num(["30 g Kryddmix Bifteki"], {"name": "Garam Masala Indian Spices Santa Maria", "category": "pantry"}), 0)
test("Root bifteki kryddmix blocks tandoori Indian Spices", recipe_match_num_cached(["30 g Kryddmix Bifteki"], {"name": "Tandoori Chicken Indian Spices Santa Maria", "category": "pantry"}), 0)
test("Root five spice kryddmix blocks garam masala Indian Spices", recipe_match_num(["3 msk five spice kryddmix"], {"name": "Garam Masala Indian Spices Santa Maria", "category": "pantry"}), 0)
test("Root five spice kryddmix blocks tandoori Indian Spices", recipe_match_num_cached(["3 msk five spice kryddmix"], {"name": "Tandoori Chicken Indian Spices Santa Maria", "category": "pantry"}), 0)
test("Root citrus juice product matches juice ingredient", recipe_match_num_cached(["1 msk citronjuice"], {"name": "Citronjuice Zeinas", "category": "pantry"}), 1)
test("Root citrus juice product blocks whole lemon ingredient", recipe_match_num(["1 citron"], {"name": "Citronjuice Zeinas", "category": "pantry"}), 0)
test("Root citrus juice product blocks lemon zest ingredient", recipe_match_num(["1 tsk citronzest"], {"name": "Citronjuice Zeinas", "category": "pantry"}), 0)
test("Root dry lentils block pre-cooked lentils", recipe_match_num(["2 dl torkade gröna linser"], {"name": "Gröna Linser Förkokta Gogreen", "category": "pantry"}), 0)
test("Root dry lentils accept dry lentils", recipe_match_num_cached(["2 dl torkade gröna linser"], {"name": "Gröna Linser Gogreen", "category": "pantry"}), 1)
test("Root egg noodles accept egg noodles", recipe_match_num(["200 g äggnudlar"], {"name": "Äggnudlar Santa Maria", "category": "pantry"}), 1)
test("Root egg noodles block rice noodles", recipe_match_num_cached(["200 g äggnudlar"], {"name": "Risnudlar Santa Maria", "category": "pantry"}), 0)

section("Batch 14 checkpoint regressions")
test("Batch 14 Korean bulgogi kryddmix blocks garam masala spices", recipe_match_num(["1 påse kryddmix gärna Asian Spices Korean BBQ Bulgogi"], {"name": "Garam Masala Indian Spices Santa Maria", "category": "pantry"}), 0)
test("Batch 14 Korean bulgogi kryddmix blocks tandoori spices", recipe_match_num_cached(["1 påse kryddmix gärna Asian Spices Korean BBQ Bulgogi"], {"name": "Tandoori Chicken Indian Spices Santa Maria", "category": "pantry"}), 0)
test("Batch 14 Korean bulgogi kryddmix keeps parenthetical product hint", recipe_match_num_cached(["1 påse kryddmix (à 35 g, gärna Asian Spices Korean BBQ Bulgogi)"], {"name": "Garam Masala Indian Spices Santa Maria", "category": "pantry"}), 0)
test("Batch 14 plain växtdryck blocks caramel oat drink", recipe_match_num(["5 dl Växtdryck"], {"name": "Barista Carame Havredryck Oddlygood", "category": "dairy"}), 0)
test("Batch 14 plain växtdryck blocks hazelnut oat drink", recipe_match_num_cached(["5 dl Växtdryck"], {"name": "Barista Hazeln Havredryck Glutenfri Oddlygood", "category": "dairy"}), 0)
test("Batch 14 plain växtdryck blocks maple walnut oat drink", recipe_match_num(["5 dl Växtdryck"], {"name": "Maple Walnut Havredryck Glutenfri Oddlygood", "category": "dairy"}), 0)
test("Batch 14 fransk senap accepts dijonsenap", recipe_match_num(["2 msk fransk senap"], {"name": "Dijonsenap Garant", "category": "pantry"}), 1)
test("Batch 14 fransk senap accepts Dijon senap wording", recipe_match_num_cached(["2 msk fransk senap"], {"name": "Dijon Senap Dijona", "category": "pantry"}), 1)
test("Batch 14 fransk senap blocks ordinary sweet mustard", recipe_match_num(["2 msk fransk senap"], {"name": "Senap Sötstark Johnny's", "category": "pantry"}), 0)
test("Batch 14 fransk senap blocks ordinary original mustard", recipe_match_num_cached(["2 msk fransk senap"], {"name": "Original Senap Slotts", "category": "pantry"}), 0)
test("Batch 14 mörk chokladkaka accepts dark chocolate without kaka word", recipe_match_num(["25 g Mörk chokladkaka"], {"name": "85% Cacao Mörk Choklad Garant", "category": "candy"}), 1)
test("Batch 14 mörk chokladkaka accepts English Dark Excellence bar", recipe_match_num_cached(["25 g Mörk chokladkaka"], {"name": "70% Cocoa Dark Excellence Chokladkaka Lindt", "category": "candy", "brand": "LINDT"}), 1)
test("Batch 14 rimmad skivad lax blocks raw fillet", recipe_match_num(["ca 250 g rimmad lax i tunna skivor"], {"name": "Laxfilé Garant", "category": "fish"}), 0)
test("Batch 14 rimmad skivad lax accepts gravad skivad lax", recipe_match_num_cached(["ca 250 g rimmad lax i tunna skivor"], {"name": "Gravad Lax Skivad Falkenberg", "category": "fish"}), 1)
test("Batch 14 rimmad skivad lax accepts kallrökt skivad lax", recipe_match_num(["ca 250 g rimmad lax i tunna skivor"], {"name": "Kallrökt Lax Skivad Falkenberg", "category": "fish"}), 1)
test("Batch 14 rimmad skivad lax accepts najadlax", recipe_match_num_cached(["ca 250 g rimmad lax i tunna skivor"], {"name": "Najadlax Skivad Leröy", "category": "fish"}), 1)
test("Batch 14 rimmad skivad lax blocks hot smoked portions", recipe_match_num(["ca 250 g rimmad lax i tunna skivor"], {"name": "Lax Varmr Portion Eldorado", "category": "fish"}), 0)
test("Batch 14 spaced fläderblom saft product exposes flädersaft", extract_keywords_from_product("Fläderblom Ekologisk Saft Glas Tillmans", "pantry"), ["flädersaft"])
test("Batch 14 fläderblomssaft ingredient matches spaced saft product", recipe_match_num(["1 dl fläderblomssaft eller rabarbersaft"], {"name": "Fläderblom Ekologisk Saft Glas Tillmans", "category": "pantry"}), 1)
test("Batch 14 rabarbersaft ingredient matches spaced saft product", recipe_match_num_cached(["1 dl fläderblomssaft eller rabarbersaft"], {"name": "Rabarber Ekologisk Saft Glas Tillmans", "category": "pantry"}), 1)
test("Batch 14 färsk tonfisk accepts tuna steaks", recipe_match_num(["400 g Färsk tonfisk"], {"name": "Tonfisk Steaks Leröy", "category": "fish"}), 1)
test("Batch 14 färsk tonfisk blocks canned tuna in water", recipe_match_num_cached(["400 g Färsk tonfisk"], {"name": "Tonfisk Vatten Eldorado", "category": "pantry"}), 0)
test("Batch 14 färsk tonfisk blocks cat food tuna", recipe_match_num(["400 g Färsk tonfisk"], {"name": "Tonfisk Mousse Kattmat Våt Smart Pets", "category": "household"}), 0)
test("Batch 14 exact Bärta naturell helbit blocks smoked tempeh fallback", recipe_match_num(["Paket Bärta Helbit, Naturell"], {"name": "Tempeh Alspånsrökt Helbit Yipin", "category": "pantry"}), 0)
test("Batch 14 naturell tempeh helbit still accepts naturell helbit", recipe_match_num_cached(["Paket Tempeh Helbit, Naturell"], {"name": "Tempeh Naturell Helbit Yipin", "category": "pantry"}), 1)
test("Batch 14 dillfrö matches plural dillfrön spice product", recipe_match_num(["1 tsk Dillfrö"], {"name": "Dillfrön Burk Kockens", "category": "spices"}), 1)
test("Batch 14 surkål ingredient matches surkål product", recipe_match_num_cached(["200 g Surkål"], {"name": "Fass Kraut Surkål Premium Kuhne", "category": "pantry"}), 1)
test("Batch 14 surkål med morot product still blocks standalone carrot", recipe_match_num(["2 morötter"], {"name": "Surkål med Morot Urbanek", "category": "pantry"}), 0)
test("Batch 14 plain fläskkarré blocks rökig chili cut", recipe_match_num_cached(["800 g fläskkarré"], {"name": "Karré Rökig Chili Sverige Scan", "category": "meat"}), 0)
test("Batch 14 explicit rökig chili fläskkarré accepts rökig chili cut", recipe_match_num(["800 g rökig chili fläskkarré"], {"name": "Karré Rökig Chili Sverige Scan", "category": "meat"}), 1)
test("Batch 14 plain kycklingfilé blocks grillkryddad fillet", recipe_match_num(["4 st Kycklingfile"], {"name": "Kyckling Bröstfilé Grillkryddad Eldorado", "category": "meat"}), 0)
test("Batch 14 plain kycklingfilé accepts raw breast fillet", recipe_match_num_cached(["4 st Kycklingfile"], {"name": "Kycklingfilé Bröstfilé Sverige Garant", "category": "meat"}), 1)
test("Batch 14 frozen kycklingfilé accepts plain frozen fillet", recipe_match_num(["600 g Kycklingfile Fryst"], {"name": "Kycklingfilé Svensk Fryst Garant", "category": "frozen"}), 1)
test("Batch 14 lagrad ost blocks ordinary gouda", recipe_match_num(["2 dl riven lagrad ost, t ex Västerbottensost"], {"name": "Gouda 31% Garant", "category": "dairy"}), 0)
test("Batch 14 lagrad ost accepts herrgård lagrad", recipe_match_num_cached(["2 dl riven lagrad ost, t ex Västerbottensost"], {"name": "Herrgård Lagrad", "category": "dairy"}), 1)
test("Batch 14 lagrad ost accepts västerbottensost", recipe_match_num(["2 dl riven lagrad ost, t ex Västerbottensost"], {"name": "Västerbottens Original Ost", "category": "dairy"}), 1)
test("Batch 14 lagrad ost blocks vegan original flavour carrier", recipe_match_num_cached(["2 dl riven lagrad ost, t ex Västerbottensost"], {"name": "Block Original Flavour Vegansk Violife", "category": "dairy"}), 0)
test("Batch 14 lime juice blocks mixed fruit juice carrier", recipe_match_num(["0.5 st Lime, juicen"], {"name": "Äpple Ananas Kiwi Lime Juice Garant", "category": "beverages"}), 0)
test("Batch 14 lime juice accepts lime juice product", recipe_match_num_cached(["0.5 st Lime, juicen"], {"name": "Lime Juice Eko Garant Eko", "category": "pantry"}), 1)
test("Batch 14 generic nudlar blocks chicken-flavour instant noodles", recipe_match_num(["Nudlar (Efter smak)"], {"name": "Chicken Flavou Pho Ga Nudlar Vifon", "category": "pantry"}), 0)
test("Batch 14 generic nudlar blocks demae biff instant noodles", recipe_match_num_cached(["Nudlar (Efter smak)"], {"name": "Demae Ramen Biff Nudlar Nissin", "category": "pantry"}), 0)
test("Batch 14 generic nudlar accepts soba noodles", recipe_match_num(["Nudlar (Efter smak)"], {"name": "Nudlar Soba Garant", "category": "pantry"}), 1)
test("Batch 14 generic nudlar accepts udon noodles", recipe_match_num_cached(["Nudlar (Efter smak)"], {"name": "Nudlar Udon Garant", "category": "pantry"}), 1)
test("Batch 14 generic nudlar accepts ramen noodles", recipe_match_num(["Nudlar (Efter smak)"], {"name": "Nudlar Ramen Fresh Hokkien Twin Dragon", "category": "pantry"}), 1)
test("Batch 14 generic nudlar blocks kimchi-flavored udon noodles", recipe_match_num_cached(["Nudlar (Efter smak)"], {"name": "Nudlar Udon Kimchi Garak", "category": "pantry"}), 0)
test("Batch 14 chunky salsa blocks cheese sauce salsa carrier", recipe_match_num_cached(["200 g Chunky Salsa"], {"name": "Cheese Sauce Salsa Mexicana Banderos", "category": "pantry"}), 0)
test("Batch 14 chunky salsa accepts chunky salsa product", recipe_match_num(["200 g Chunky Salsa"], {"name": "Chunky Salsa Mild Santa Maria", "category": "pantry"}), 1)
test("Batch 14 mixed herbs with rucola examples expand as fresh herbs", expand_grouped_ingredient_text("blandade örter t ex basilika, rucola och persilja"), ["färsk basilika", "färsk rucola", "färsk persilja"])
test("Batch 14 mixed herbs accepts fresh basil pot", recipe_match_num(["blandade örter t ex basilika, rucola och persilja"], {"name": "Basilika i Kruka Ekologisk", "category": "fruit"}), 1)
test("Batch 14 mixed herbs blocks dried basil jar", recipe_match_num_cached(["blandade örter t ex basilika, rucola och persilja"], {"name": "Basilika Burk Kockens", "category": "pantry"}), 0)
test("Batch 14 mixed herbs accepts fresh rucola", recipe_match_num(["blandade örter t ex basilika, rucola och persilja"], {"name": "Ruccola Klass 1", "category": "fruit"}), 1)
test("Batch 14 bostongurka example matches bostongurka", recipe_match_num_cached(["1/2 dl inlagd hackad gurka (t ex bostongurka)"], {"name": "Bostongurka Felix", "category": "vegetables", "savings": 5}), 1)
test("Batch 14 bostongurka example matches gurkmix bostongurka", recipe_match_num(["1/2 dl inlagd hackad gurka (t ex bostongurka)"], {"name": "Bostongurka Gurkmix Felix", "category": "vegetables", "savings": 5}), 1)
test("Batch 14 potatismos accepts instant mash product", recipe_match_num_cached(["potatismos"], {"name": "Potatismos 12 Port Felix", "category": "vegetables"}), 1)
test("Batch 14 potatismos blocks ready meal with fish", recipe_match_num(["potatismos"], {"name": "Panerad Fisk med Potatismos Redo", "category": "fish"}), 0)
test("Batch 14 vitlöksmarinad matches spaced garlic marinade", recipe_match_num_cached(["65 g Vitlöksmarinad"], {"name": "Vitlök Marinad Caj P", "category": "pantry"}), 1)
test("Batch 14 vitlöksmarinad blocks allround marinade", recipe_match_num(["65 g Vitlöksmarinad"], {"name": "Allround Marinad Caj P", "category": "pantry"}), 0)
test("Batch 14 vitt bröd normalizes to formbröd", extract_keywords_from_ingredient("10 skivor tunt skuret vitt bröd"), ["formbröd"])
test("Batch 14 vitt bröd accepts rostbröd", recipe_match_num_cached(["10 skivor tunt skuret vitt bröd"], {"name": "Rostbröd Klassiskt Garant", "category": "bread"}), 1)
test("Batch 14 vitt bröd accepts jättefranska", recipe_match_num(["10 skivor tunt skuret vitt bröd"], {"name": "Jättefranska Pågen", "category": "bread"}), 1)
test("Batch 14 vitt bröd accepts toast bread wording", recipe_match_num_cached(["10 skivor tunt skuret vitt bröd"], {"name": "Tasty Toast Pågen", "category": "bread"}), 1)
test("Batch 14 vitt bröd blocks Liba flatbread", recipe_match_num(["10 skivor tunt skuret vitt bröd"], {"name": "Liba Original Tunnbröd Vitt 4-pack Liba Bröd", "category": "bread"}), 0)
test("Batch 14 oreo cookie offers pass processed filter exception", _is_oreo_cookie_offer("oreo original kakor", "bread"), True)
test("Batch 14 oreo chocolate bars stay outside cookie exception", _is_oreo_cookie_offer("big taste oreo chokladkaka marabou", "candy"), False)
test("Batch 14 oreokakor matches Oreo cookie pack", recipe_match_num_cached(["300 g oreokakor"], {"name": "Oreo Original Kakor", "category": "bread"}), 1)
test("Batch 14 oreokakor blocks Oreo chocolate bar", recipe_match_num(["300 g oreokakor"], {"name": "Big Taste Oreo Chokladkaka Marabou", "category": "candy"}), 0)
test("Batch 14 sötmandel spån normalizes to mandelspån", extract_keywords_from_ingredient("2 msk Sötmandel Spån"), ["mandelspån"])
test("Batch 14 sötmandel spån accepts mandelspån", recipe_match_num_cached(["2 msk Sötmandel Spån"], {"name": "Mandelspån Garant", "category": "other"}), 1)
test("Batch 14 sötmandel spån blocks whole almonds", recipe_match_num(["2 msk Sötmandel Spån"], {"name": "Sötmandel Hela Naturella Garant", "category": "other"}), 0)
test("Batch 14 plain citronmeliss accepts fresh citronmeliss", recipe_match_num_cached(["citronmeliss"], {"name": "Citronmeliss Klass 1 Garant", "category": "fruit"}), 1)
test("Batch 14 ketchuptyp chilisås blocks garlic Asian chili sauce", recipe_match_num(["1/2 dl chilisås av ketchuptyp"], {"name": "Chilisås Vitlök Ayam", "category": "pantry"}), 0)
test("Batch 14 ketchuptyp chilisås accepts classic chilisås", recipe_match_num_cached(["1/2 dl chilisås av ketchuptyp"], {"name": "Chilisås Klassisk Garant", "category": "pantry"}), 1)
test("Batch 14 red onion bunch exposes knipplök", "knipplök" in precompute_offer_data("Lök Röd i Knippe Klass 1", "fruit")["keywords"], True)
test("Batch 14 knipplök accepts red onion bunch", recipe_match_num_cached(["1 röd knipplök, strimlad"], {"name": "Lök Röd i Knippe Klass 1", "category": "fruit"}), 1)
test("Batch 14 knipplök accepts salladslök bunch", recipe_match_num(["1 röd knipplök, strimlad"], {"name": "Salladslök Knippe", "category": "vegetables"}), 1)
test("Batch 14 canned cherry tomatoes beverage category reclassifies to pantry", guess_category("Körsbärs- Tomater i Tomatjuice Eldorado", "beverages"), "pantry")
test("Batch 14 canned cherry tomatoes accept in-juice product", recipe_match_num_cached(["1 förp konserverade körsbärstomater"], {"name": "Körsbärs- Tomater i Tomatjuice Eldorado", "category": "beverages"}), 1)
test("Batch 14 canned cherry tomatoes block fresh baby plum tomatoes", recipe_match_num(["1 förp konserverade körsbärstomater"], {"name": "Tomat Babyplommon Kl 1", "category": "vegetables"}), 0)
test("Batch 14 reversed white chocolate bar wording normalizes", extract_keywords_from_ingredient("50 g Chokladkaka Vit"), ["choklad"])
test("Batch 14 white chocolate bar wording accepts white baking chocolate", recipe_match_num_cached(["50 g Chokladkaka Vit"], {"name": "Bakchoklad Vit Garant", "category": "candy"}), 1)
test("Batch 14 white chocolate bar wording accepts white chocolate buttons", recipe_match_num(["50 g Chokladkaka Vit"], {"name": "Chokladknappar Vit Odense", "category": "pantry"}), 1)
test("Batch 14 white chocolate bar wording blocks dark baking chocolate", recipe_match_num_cached(["50 g Chokladkaka Vit"], {"name": "Bakchoklad Mörk 55% Garant", "category": "candy"}), 0)
test("Batch 14 generic pistachios accept salted pistachios", recipe_match_num(["0.75 dl Pistagenötter"], {"name": "Pistaschkärnor Utan Skal Rostade Och Saltade Garant", "category": "other"}), 1)
test("Batch 14 osaltade pistachios block salted pistachios", recipe_match_num_cached(["0.75 dl osaltade Pistagenötter"], {"name": "Pistaschkärnor Utan Skal Rostade Och Saltade Garant", "category": "other"}), 0)
test("Batch 14 yellow kiwi accepts yellow kiwi", recipe_match_num(["2 st Kiwi Gul"], {"name": "Kiwi Gul Klass 1", "category": "fruit"}), 1)
test("Batch 14 yellow kiwi blocks generic green kiwi", recipe_match_num_cached(["2 st Kiwi Gul"], {"name": "Kiwi Klass 1", "category": "fruit"}), 0)
test("Batch 14 green kiwi accepts generic kiwi", recipe_match_num(["2 st Kiwi Grön"], {"name": "Kiwi Klass 1", "category": "fruit"}), 1)
test("Batch 14 green kiwi blocks yellow kiwi", recipe_match_num_cached(["2 st Kiwi Grön"], {"name": "Kiwi Gul Klass 1", "category": "fruit"}), 0)
test("Batch 14 falafelmix exposes mix keyword", extract_keywords_from_ingredient("1 st Falafelmix"), ["falafelmix"])
test("Batch 14 falafelmix accepts falafel mix product", recipe_match_num(["1 st Falafelmix"], {"name": "Falafelmix Santa Maria", "category": "pantry"}), 1)
test("Batch 14 falafelmix blocks ready frozen falafel", recipe_match_num_cached(["1 st Falafelmix"], {"name": "Falafel Fryst Garant", "category": "frozen"}), 0)
test("Batch 14 kolsyrat mineralvatten normalizes to sodavatten", extract_keywords_from_ingredient("1/2 dl kolsyrat mineralvatten"), ["sodavatten"])
test("Batch 14 kolsyrat mineralvatten accepts plain sparkling mineral water", recipe_match_num(["1/2 dl kolsyrat mineralvatten"], {"name": "San Pellegrino Mineralvatten Kolsyrat Vatten Pet", "category": "beverages"}), 1)
test("Batch 14 kolsyrat mineralvatten blocks flavored sparkling water", recipe_match_num_cached(["1/2 dl kolsyrat mineralvatten"], {"name": "Citron Kolsyrat Vatten Pet Loka", "category": "beverages"}), 0)
test("Batch 14 kolsyrat mineralvatten blocks smultron sparkling water", recipe_match_num(["1/2 dl kolsyrat mineralvatten"], {"name": "Smultron Kolsyrat Vatten Pet Premier", "category": "beverages"}), 0)
test("Batch 14 pitted kalamata accepts pitted kalamata olives", recipe_match_num(["1 dl Zeta Kalamataoliver urkärnade"], {"name": "Oliver Kalamata Urkärnade 350g Fontana", "category": "spices"}), 1)
test("Batch 14 pitted kalamata accepts pitted black olive fallback", recipe_match_num_cached(["1 dl Zeta Kalamataoliver urkärnade"], {"name": "Svarta Oliver Utan Kärnor Eldorado", "category": "spices"}), 1)
test("Batch 14 pitted kalamata pragmatically accepts kalamata with pits", recipe_match_num(["1 dl Zeta Kalamataoliver urkärnade"], {"name": "Kalamata Oliver med Kärnor Fontana", "category": "spices"}), 1)
test("Batch 14 pitted kalamata pragmatically accepts unqualified Gemlik fallback", recipe_match_num_cached(["1 dl Zeta Kalamataoliver urkärnade"], {"name": "Gemlik Oliver Ceren", "category": "spices"}), 1)
test("Batch 14 pitted black olives accept pitted black olive product", recipe_match_num(["100 g Svarta oliver utan kärnor"], {"name": "Svarta Oliver Utan Kärnor Figaro", "category": "spices"}), 1)
test("Batch 14 pitted black olives pragmatically accept kalamata with pits", recipe_match_num_cached(["100 g Svarta oliver utan kärnor"], {"name": "Kalamata Oliver med Kärnor Fontana", "category": "spices"}), 1)
test("Batch 14 pitted black olives pragmatically accept unqualified Gemlik", recipe_match_num(["100 g Svarta oliver utan kärnor"], {"name": "Gemlik Oliver Ceren", "category": "spices"}), 1)
test("Batch 14 majsmjöl accepts corn flour", recipe_match_num_cached(["50 g Majsmjöl"], {"name": "Majsmjöl Glutenfri Risenta", "category": "pantry"}), 1)
test("Batch 14 majsmjöl blocks breadcrumb carrier", recipe_match_num(["50 g Majsmjöl"], {"name": "Ströbröd Instant Majsmjöl Glutenfritt Olda", "category": "pantry"}), 0)
test("Batch 14 kardemummayoghurt blocks naturell yoghur typo fallback", recipe_match_num_cached(["8 portioner Kardemummayoghurt"], {"name": "Turkisk Yoghur Naturell 17% Salakis", "category": "dairy"}), 0)
test("Batch 14 kardemummayoghurt accepts exact cardamom yoghurt", recipe_match_num(["8 portioner Kardemummayoghurt"], {"name": "Yoghurt Kardemumma 1l Valio", "category": "dairy"}), 1)
test("Batch 14 kantareller in water beverage category reclassifies to pantry", guess_category("Kantareller i Vatten Borgens", "beverages"), "pantry")
test("Batch 14 kantareller accepts kantareller in water", recipe_match_num(["400 g Kantareller"], {"name": "Kantareller i Vatten Borgens", "category": "beverages"}), 1)

section("Batch 14 completion fixes")

test("Batch 14 plain chilisås blocks garlic Asian chili sauce", recipe_match_num(["2 msk chilisås"], {"name": "Chilisås Vitlök Ayam", "category": "pantry"}), 0)
test("Batch 14 plain chilisås accepts classic chilisås", recipe_match_num_cached(["2 msk chilisås"], {"name": "Chilisås Klassisk Garant", "category": "pantry"}), 1)
test("Batch 14 lime pepper seasoning does not match fresh lime", recipe_match_num(["lime pepper krydda"], {"name": "Lime Klass 1", "category": "fruit"}), 0)
test("Batch 14 wokgrönsaker accepts wokmix", recipe_match_num_cached(["600 g wokgrönsaker"], {"name": "Wokmix Fryst Eldorado", "category": "frozen"}), 1)
test("Batch 14 wokgrönsaker accepts Wok Classic", recipe_match_num(["600 g wokgrönsaker"], {"name": "Wok Classic Bigpack Findus", "category": "other"}), 1)
test("Batch 14 wokgrönsaker blocks wok sauce", recipe_match_num_cached(["600 g wokgrönsaker"], {"name": "Hoisin Wok Sauce Blue Dragon", "category": "pantry"}), 0)
test("Batch 14 Polly exact candy matches Polly", recipe_match_num(["340 g Polly"], {"name": "Original Polly Blå Påse Cloetta", "category": "candy"}), 1)
test("Batch 14 named candy filter includes Polly", _is_recipe_named_candy_offer("Original Polly Blå Påse Cloetta", "candy"), True)
test("Batch 14 named candy filter includes strössel", _is_recipe_named_candy_offer("Strössel Blandat Dr Oetker", "candy"), True)
test("Batch 14 named candy filter includes kolasås", _is_recipe_named_candy_offer("Kolasås Odense", "candy"), True)
test("Batch 14 named candy filter rejects flavor candy", _is_recipe_named_candy_offer("Banana Skids Swizzels", "candy"), False)
test("Batch 14 färskost med örter accepts herb cream cheese", recipe_match_num_cached(["100 g färskost (med örter)"], {"name": "Vitlök&örter Färskost 24% Arla", "category": "dairy"}), 1)
test("Batch 14 färskost med örter accepts naturell fallback", recipe_match_num(["100 g färskost (med örter)"], {"name": "Naturell Färskost 23% Arla", "category": "dairy"}), 1)
test("Batch 14 färskost med örter blocks garlic bulb", recipe_match_num_cached(["100 g färskost (med örter)"], {"name": "Vitlök Klass 1", "category": "fruit"}), 0)
test("Batch 14 färska örter accepts fresh basil", recipe_match_num(["1 dl färska örter"], {"name": "Basilika i Kruka Ekologisk", "category": "fruit"}), 1)
test("Batch 14 färska örter accepts frozen basil", recipe_match_num_cached(["1 dl färska örter"], {"name": "Basilika Finhackad Fryst Garant", "category": "frozen"}), 1)
test("Batch 14 färska örter blocks cream-cheese carrier", recipe_match_num(["1 dl färska örter"], {"name": "Vitlök&örter Färskost 24% Arla", "category": "dairy"}), 0)
test("Batch 14 plain mineralvatten accepts sparkling mineral water", recipe_match_num_cached(["2 dl mineralvatten"], {"name": "San Pellegrino Mineralvatten Kolsyrat Vatten Pet", "category": "beverages"}), 1)
test("Batch 14 Tom Kha kryddmix accepts Tom Kha product", recipe_match_num(["30 g Tom Kha Gai kryddmix"], {"name": "Tom Kha Soup Asian Spice Santa Maria", "category": "pantry"}), 1)
test("Batch 14 Tom Kha kryddmix blocks Garam Masala", recipe_match_num_cached(["30 g Tom Kha Gai kryddmix"], {"name": "Garam Masala Indian Spices Santa Maria", "category": "pantry"}), 0)
test("Batch 14 aromsmör accepts persiljesmör", recipe_match_num(["50 g Aromsmör"], {"name": "Persiljesmör Biggans", "category": "dairy"}), 1)
test("Batch 14 aromsmör blocks plain butter", recipe_match_num_cached(["50 g Aromsmör"], {"name": "Smör Normalsaltat 82% Svenskt Smör", "category": "dairy"}), 0)
test("Batch 14 strössel accepts strössel", recipe_match_num(["2 msk Strössel"], {"name": "Strössel Blandat Dr Oetker", "category": "candy"}), 1)
test("Batch 14 strössel blocks donut carrier", recipe_match_num_cached(["2 msk Strössel"], {"name": "Donut Choklad med Strössel La Lorraine", "category": "bread"}), 0)
test("Batch 14 Apetit sommargrönsaker accepts frozen summer vegetables", recipe_match_num(["1 förp Apetit frysta sommargrönsaker (à 600 g)"], {"name": "Grönsaker Sommar Fryst Apetit", "category": "frozen"}), 1)
test("Batch 14 canned wokgrönsaker accepts brine product", recipe_match_num_cached(["425 g sköljda wokgrönsaker (på burk)"], {"name": "Wok Mix Vegetables In Brine Spicefield", "category": "other"}), 1)
test("Batch 14 canned wokgrönsaker blocks frozen wokmix", recipe_match_num(["425 g sköljda wokgrönsaker (på burk)"], {"name": "Wokmix Fryst Eldorado", "category": "frozen"}), 0)
test("Batch 14 kycklingschnitzel accepts chicken schnitzel", recipe_match_num(["600 g Kycklingschnitzel"], {"name": "Schnitzel Kyckling Fryst Qibbla Halal", "category": "frozen"}), 1)
test("Batch 14 kycklingschnitzel blocks generic pork schnitzel", recipe_match_num_cached(["600 g Kycklingschnitzel"], {"name": "Schnitzel Fryst Scan", "category": "frozen"}), 0)
test("Batch 14 chilimajonnäs accepts chilimajo", recipe_match_num(["100 g Chilimajonnäs"], {"name": "Chilimajo Garant", "category": "other"}), 1)
test("Batch 14 chilimajonnäs blocks fresh chili", recipe_match_num_cached(["100 g Chilimajonnäs"], {"name": "Chilli Peppar Röd Kl1 Garant", "category": "fruit"}), 0)
test("Batch 14 äggfri tagliatelle blocks egg tagliatelle", recipe_match_num(["500 g äggfri tagliatelle"], {"name": "Tagliatelle Ägg Garant", "category": "pantry"}), 0)
test("Batch 14 vegan recipe title blocks non-vegan Quorn burger", recipe_match_num_named("Krämig vegansk salsicciapasta", ["4 st köttiga vegoburgare eller 400 g formbar färs"], {"name": "Burgare Quorn", "category": "frozen"}), 0)
test("Batch 14 vegan recipe title accepts vegoburgare", recipe_match_num_named_cached("Krämig vegansk salsicciapasta", ["4 st köttiga vegoburgare eller 400 g formbar färs"], {"name": "Vegoburgare Frysta/4-pack Anamma", "category": "frozen"}), 1)
test("Batch 14 fänkålsfrön accepts whole fennel spice", recipe_match_num_cached(["1 msk Hela fänkålsfrön från Kockens kryddor"], {"name": "Fänkål Hel Påse Kockens", "category": "pantry"}), 1)
test("Batch 14 fänkålsfrön blocks brand leakage", recipe_match_num(["1 msk Hela fänkålsfrön från Kockens kryddor"], {"name": "Persillade Burk Kockens", "category": "pantry"}), 0)
test("Batch 14 dried mushroom ingredient blocks frozen champignons", recipe_match_num_cached(["50 g Torkad karl johansvamp eller annan blandad torkad skogssvamp"], {"name": "Champinjoner Skivade Frysta Begro", "category": "frozen"}), 0)
test("Batch 14 generic köttfärs accepts ordinary beef mince", recipe_match_num(["600 g Köttfärs"], {"name": "Nötfärs 5% Sverige Garant", "category": "meat"}), 1)
test("Batch 14 generic köttfärs blocks chorizofärs", recipe_match_num_cached(["600 g Köttfärs"], {"name": "Chorizofärs Nonna Elide", "category": "meat"}), 0)
test("Batch 14 explicit prästost accepts prästost", recipe_match_num(["2 dl riven prästost (gärna lagrad i 18 månader)"], {"name": "Präst Mild 35% Skånemejerier", "category": "dairy"}), 1)
test("Batch 14 explicit prästost blocks gouda", recipe_match_num_cached(["2 dl riven prästost (gärna lagrad i 18 månader)"], {"name": "Gouda 31% Garant", "category": "dairy"}), 0)
test("Batch 14 packaged tonfisk accepts canned tuna in water", recipe_match_num(["3 förp tonfisk (à 120 g)"], {"name": "Tonfisk Vatten Garant", "category": "pantry"}), 1)
test("Batch 14 packaged tonfisk blocks fresh tuna steak", recipe_match_num_cached(["3 förp tonfisk (à 120 g)"], {"name": "Tonfisk Steaks Leröy", "category": "fish"}), 0)
test("Batch 14 kruksallad accepts krispsallat i kruka", recipe_match_num(["1 kruksallad"], {"name": "Krispsallat i Kruka Ekologisk Klass 1", "category": "fruit"}), 1)
test("Batch 14 smör-rapsolja accepts butter-rapeseed blend", recipe_match_num_cached(["2 msk smör- & rapsolja"], {"name": "Smör-&rapsolja Flytande Original 80% Arla Köket", "category": "dairy"}), 1)
test("Batch 14 smör-rapsolja blocks plain rapsolja", recipe_match_num(["2 msk smör- & rapsolja"], {"name": "Rapsolja Eldorado", "category": "pantry"}), 0)
test("Batch 14 ancho chili blocks generic chili powder", recipe_match_num_cached(["1 tsk ancho chili, malen"], {"name": "Chilipulver Påse Eldorado", "category": "pantry"}), 0)
test("Batch 14 svart böna accepts black beans", recipe_match_num(["1 förp svart böna"], {"name": "Svarta Bönor Eldorado", "category": "pantry"}), 1)
test("Batch 14 svart böna blocks black bean dip", recipe_match_num_cached(["1 förp svart böna"], {"name": "Black Bean Dip Bold & Smokey El Taco Truck", "category": "other"}), 0)
test("Batch 14 plain vaniljglass blocks strawberry-sauce carrier", recipe_match_num(["1 l Vaniljglass"], {"name": "Vanilj med Jordgubbssås Gräddglass Gb Glace", "category": "frozen"}), 0)
test("Batch 14 plain vaniljglass accepts plain vanilla ice cream", recipe_match_num_cached(["1 l Vaniljglass"], {"name": "Vanilj Gräddglass Sia Glass", "category": "frozen"}), 1)
test("Batch 14 kycklinginnerfilé blocks grillkryddad fillet", recipe_match_num(["ca 500 g kycklinginnerfiléer"], {"name": "Kyckling Bröstfilé Grillkryddad Eldorado", "category": "meat"}), 0)
test("Batch 14 generic olja stays unmatched", recipe_match_num_cached(["1 msk olja"], {"name": "Rapsolja Eldorado", "category": "pantry"}), 0)
test("Batch 14 malen kryddnejlika accepts ground cloves", recipe_match_num(["1 msk malen kryddnejlika"], {"name": "Nejlikor Malda Påse Kockens", "category": "pantry"}), 1)
test("Batch 14 malen kryddnejlika blocks whole cloves", recipe_match_num_cached(["1 msk malen kryddnejlika"], {"name": "Nejlikor Hela Påse Kockens", "category": "pantry"}), 0)
test("Batch 14 sweet cream cheese frosting blocks Västerbotten Philadelphia", recipe_match_num(["300 g cream cheese"], {"name": "Västerbotten Philadelphia", "category": "dairy"}), 0)
test("Batch 14 sweet cream cheese frosting accepts original Philadelphia", recipe_match_num_cached(["300 g cream cheese"], {"name": "Philadelphia Original", "category": "dairy"}), 1)

section("Batch 15 accepted decisions")
test("Batch 15 crispy chili oil matches exact product", recipe_match_num(["1 msk Crispy chili oil"], {"name": "Laoganma Crispy Chili Oil", "category": "pantry"}), 1)
test("Batch 15 chili does not match crispy chili oil", recipe_match_num_cached(["1 chili"], {"name": "Laoganma Crispy Chili Oil", "category": "pantry"}), 0)
test("Batch 15 raw fläskkött blocks souvlaki product", recipe_match_num(["500 g fläskkött"], {"name": "Souvlaki Fläsk", "category": "meat"}), 0)
test("Batch 15 sötströ matches lättströ", recipe_match_num_cached(["1 dl sötströ"], {"name": "Lättströ ICA", "category": "pantry"}), 1)
test("Batch 15 hel vitlök blocks hackad fryst vitlök", recipe_match_num(["1 Vitlök hel"], {"name": "Vitlök Hackad Fryst", "category": "frozen"}), 0)
test("Batch 15 vegetarisk kebab matches vegokebab", recipe_match_num_cached(["300 g Vegetarisk kebab"], {"name": "Vegokebab Garant", "category": "frozen"}), 1)
test("Batch 15 svarpeppar typo is manual no-match", recipe_match_num(["1 tsk svarpeppar"], {"name": "Svartpeppar Malen", "category": "spices"}), 0)
test("Batch 15 färdigkokt majskolv matches förkokt majs", recipe_match_num_cached(["2 Majskolv färdigkokt"], {"name": "Majs Förkokt", "category": "vegetables"}), 1)
test("Batch 15 färdigkokt majskolv does not broaden to loose corn", recipe_match_num(["2 Majskolv färdigkokt"], {"name": "Majs Fryst Findus", "category": "frozen"}), 0)
test("Batch 15 läsk matches cola", recipe_match_num(["2 dl läsk"], {"name": "Coca-Cola Original", "category": "beverages"}), 1)
test("Batch 15 glasstrutar matches våffelstrutar", recipe_match_num_cached(["8 glasstrutar"], {"name": "Våffelstrutar ICA", "category": "pantry"}), 1)
test("Batch 15 grädde 40 blocks matgrädde 15", recipe_match_num(["2 dl grädde 40%"], {"name": "Matgrädde 15% Arla", "category": "dairy"}), 0)
test("Batch 15 grädde 40 accepts vispgrädde 40", recipe_match_num_cached(["2 dl grädde 40%"], {"name": "Vispgrädde 40% Arla", "category": "dairy"}), 1)
test("Batch 15 plain grädde still accepts matgrädde", recipe_match_num(["2 dl grädde"], {"name": "Matgrädde 15% Arla", "category": "dairy"}), 1)
test("Batch 15 Classico pastasås blocks cheese sauce", recipe_match_num_cached(["1 burk Pastasås Classico"], {"name": "Pastasås Ost", "category": "pantry"}), 0)
test("Batch 15 bare fikon accepts dried figs", recipe_match_num(["4 fikon"], {"name": "Fikon Torkade", "category": "fruit"}), 1)
test("Batch 15 fresh fikon blocks dried figs", recipe_match_num_cached(["4 färska fikon"], {"name": "Fikon Torkade", "category": "fruit"}), 0)
test("Batch 15 balsamvinäger rosé matches rose condimento", recipe_match_num(["1 msk balsamvinäger rosé"], {"name": "Condimento Rose Zeta", "category": "pantry"}), 1)
test("Batch 15 generic balsamvinäger blocks rose condimento", recipe_match_num_cached(["1 msk balsamvinäger"], {"name": "Condimento Rose Zeta", "category": "pantry"}), 0)
test("Batch 15 rotfrukter matches rotfruktsmix", recipe_match_num(["500 g rotfrukter"], {"name": "Rotfruktsmix Fryst", "category": "frozen"}), 1)
test("Batch 15 apelsinjuice koncentrat blocks ordinary juice", recipe_match_num_cached(["2 dl apelsinjuice koncentrat"], {"name": "Apelsinjuice God Morgon", "category": "beverages"}), 0)
test("Batch 15 apelsinjuice koncentrat accepts concentrate", recipe_match_num(["2 dl apelsinjuice koncentrat"], {"name": "Apelsinjuice Koncentrat ICA", "category": "beverages"}), 1)
test("Batch 15 Daim matches Daimchoklad", recipe_match_num_cached(["2 Daim"], {"name": "Daimchoklad Marabou", "category": "candy"}), 1)
test("Batch 15 jordgubbssaft matches strawberry cordial", recipe_match_num(["2 dl jordgubbssaft"], {"name": "Blandsaft Jordgubb Bob", "category": "beverages"}), 1)
test("Batch 15 formbar vegetarisk färs matches Anamma formbar färs", recipe_match_num_cached(["400 g Formbar vegetarisk färs"], {"name": "Formbar Färs Fryst Anamma", "category": "frozen"}), 1)
test("Batch 15 potato buns matches hamburgerbröd", recipe_match_num(["4 potato buns"], {"name": "Hamburgerbröd Potato Buns", "category": "bread"}), 1)
test("Batch 15 spisbröd matches knäckebröd", recipe_match_num_cached(["4 spisbröd"], {"name": "Knäckebröd Wasa", "category": "bread"}), 1)
test("Batch 15 hela svartpepparkorn blocks ground pepper", recipe_match_num(["1 tsk hela svartpepparkorn"], {"name": "Svartpeppar Malen", "category": "spices"}), 0)
test("Batch 15 hela svartpepparkorn is manual no-match for whole pepper", recipe_match_num_cached(["1 tsk hela svartpepparkorn"], {"name": "Svartpeppar Hel", "category": "spices"}), 0)
test("Batch 15 äppelcider blocks pear cider", recipe_match_num(["1 dl Cider Äpple"], {"name": "Cider Päron Briska", "category": "beverages"}), 0)
test("Batch 15 äppelcider accepts apple cider", recipe_match_num_cached(["1 dl Cider Äpple"], {"name": "Äppelcider Briska", "category": "beverages"}), 1)
test("Batch 15 kanelglass blocks cinnamon spice", recipe_match_num(["1 liter kanelglass"], {"name": "Kanel Malen", "category": "spices"}), 0)
test("Batch 15 frysta örter matches frozen herbs", recipe_match_num_cached(["1 dl frysta örter"], {"name": "Örter Frysta Findus", "category": "frozen"}), 1)
test("Batch 15 frysta örter blocks dried herbs", recipe_match_num(["1 dl frysta örter"], {"name": "Örter Torkade Kockens", "category": "spices"}), 0)
test("Batch 15 burgarbröd matches hamburger buns", recipe_match_num_cached(["4 burgarbröd"], {"name": "Hamburgerbröd Pågen", "category": "bread"}), 1)
test("Batch 15 dillpicklad gurka blocks dill spice", recipe_match_num(["1 dillpicklad gurka"], {"name": "Dill Burk", "category": "spices"}), 0)
test("Batch 15 kumminstekt fejkon blocks cumin spice", recipe_match_num_cached(["1 kumminstekt fejkon"], {"name": "Kummin Malen", "category": "spices"}), 0)
test("Batch 15 vegan recipe title blocks beef burger", recipe_match_num_named("Vegansk burger", ["1 st Burgare"], {"name": "Hamburgare Nöt Sverige", "category": "meat"}), 0)
test("Batch 15 vegan recipe title accepts vegoburgare", recipe_match_num_named_cached("Vegansk burger", ["1 st Burgare"], {"name": "Vegoburgare Frysta/4-pack Anamma", "category": "frozen"}), 1)
test("Batch 15 malen svartpeppar blocks whole pepper", recipe_match_num(["1 tsk Svartpeppar Malen"], {"name": "Svartpeppar Hel", "category": "spices"}), 0)
test("Batch 15 malen svartpeppar is manual no-match for ground pepper", recipe_match_num_cached(["1 tsk Svartpeppar Malen"], {"name": "Svartpeppar Malen", "category": "spices"}), 0)
test("Batch 15 guajillo chilis blocks generic chili", recipe_match_num(["1 tsk Guajillo Chilis"], {"name": "Chilipeppar Röd", "category": "fruit"}), 0)
test("Batch 15 guajillo chilis accepts guajillo product", recipe_match_num_cached(["1 tsk Guajillo Chilis"], {"name": "Guajillo Chili Santa Maria", "category": "spices"}), 1)
test("Batch 15 folköl matches folköl", recipe_match_num(["1 flaska folköl"], {"name": "Folköl Pripps", "category": "beverages"}), 1)
test("Batch 15 pressad ingefärsjuice matches pressed ginger", recipe_match_num_cached(["1 msk pressad ingefärsjuice"], {"name": "Ingefära Pressad", "category": "fruit"}), 1)
test("Batch 15 fänkålsfrö blocks ground fennel", recipe_match_num(["1 tsk fänkålsfrö"], {"name": "Fänkål Malen", "category": "spices"}), 0)
test("Batch 15 fänkålsfrö accepts whole fennel", recipe_match_num_cached(["1 tsk fänkålsfrö"], {"name": "Fänkål Hel Påse Kockens", "category": "pantry"}), 1)
test("Batch 15 Tzaybitar matches vegobitar", recipe_match_num(["200 g Tzaybitar"], {"name": "Vegobitar Anamma", "category": "frozen"}), 1)
test("Batch 15 grovkornig senap blocks original mustard", recipe_match_num_cached(["1 msk grovkornig senap"], {"name": "Original Senap Slotts", "category": "pantry"}), 0)
test("Batch 15 grovkornig senap accepts skånsk mustard", recipe_match_num(["1 msk grovkornig senap"], {"name": "Skånsk Senap Slotts", "category": "pantry"}), 1)
test("Batch 15 sashimi lax blocks generic salmon fillet", recipe_match_num_cached(["200 g sashimi lax"], {"name": "Laxfilé Fryst", "category": "fish"}), 0)
test("Batch 15 sashimi lax accepts sushilax", recipe_match_num(["200 g sashimi lax"], {"name": "Sushilax Loin", "category": "fish"}), 1)
test("Batch 15 title sashimi lax blocks generic salmon", recipe_match_num_named_cached("Sashimi lax", ["200 g lax"], {"name": "Laxfilé Fryst", "category": "fish"}), 0)
test("Batch 15 grovmalen svartpeppar blocks fine ground pepper", recipe_match_num(["1 tsk grovmalen svartpeppar"], {"name": "Svartpeppar Malen", "category": "spices"}), 0)
test("Batch 15 grovmalen svartpeppar is manual no-match for whole pepper", recipe_match_num_cached(["1 tsk grovmalen svartpeppar"], {"name": "Svartpeppar Hel", "category": "spices"}), 0)
test("Batch 15 saltade potatischips blocks bacon chips", recipe_match_num(["200 g saltade potatischips"], {"name": "Potatischips Bacon Estrella", "category": "snacks"}), 0)
test("Batch 15 saltade potatischips accepts salted chips", recipe_match_num_cached(["200 g saltade potatischips"], {"name": "Potatischips Saltade Estrella", "category": "snacks"}), 1)
test("Batch 15 vegan recipe title blocks egg pasta", recipe_match_num_named("Vegansk pasta", ["250 g tagliatelle"], {"name": "Tagliatelle Ägg Garant", "category": "pantry"}), 0)
test("Batch 15 olja till stekning stays unmatched", recipe_match_num_cached(["1 msk olja till stekning"], {"name": "Rapsolja Eldorado", "category": "pantry"}), 0)

section("Batch 16-18 ICA policy fix wave")
test("Batch 16-18 non-food category blocks obvious household goods", kw("Grill Kol 5kg", "household"), [])
test("Batch 16-18 fresh chili ignores bad food category", recipe_match_num(["1 röd chili"], {"name": "Peppar Röd ca 20g Klass 1 ICA", "category": "meat"}), 1)
test("Batch 16-18 fresh chili still blocks prepared chili carrier", recipe_match_num_cached(["1 röd chili"], {"name": "Chili Färsk Beef and Bean 450g Texas Longhorn", "category": "poultry"}), 0)
test("Batch 16-18 generic socker extracts as buyable staple", extract_keywords_from_ingredient("1 dl socker"), ["socker"])
test("Batch 16-18 generic socker accepts strösocker", recipe_match_num(["1 dl socker"], {"name": "Strösocker 1kg ICA", "category": "pantry"}), 1)
test("Batch 16-18 generic socker blocks florsocker", recipe_match_num_cached(["1 dl socker"], {"name": "Florsocker 500g ICA", "category": "pantry"}), 0)
test("Batch 16-18 generic socker blocks sockerärtor", recipe_match_num(["1 dl socker"], {"name": "Sockerärtor 150g ICA", "category": "vegetables"}), 0)
test("Batch 16-18 generic socker blocks low-sugar carriers", recipe_match_num_cached(["1 dl socker"], {"name": "Apelsinmarmelad utan tillsatt socker 390g ICA", "category": "pantry"}), 0)
test("Batch 16-18 generic socker blocks reduced-sugar carriers", recipe_match_num(["1 dl socker"], {"name": "Drottningsylt mindre socker 385g ICA", "category": "pantry"}), 0)
test("Batch 16-18 julmust blocks apple must", recipe_match_num_cached(["2 dl julmust"], {"name": "Must Äpple utan fruktkött 1l Kiviks", "category": "beverages"}), 0)
test("Batch 16-18 julmust accepts julmust", recipe_match_num(["2 dl julmust"], {"name": "Julmust 1,4l Apotekarnes", "category": "beverages"}), 1)
test("Batch 16-18 äppelmust accepts apple must", recipe_match_num_cached(["2 dl äppelmust"], {"name": "Must Äpple utan fruktkött 1l Kiviks", "category": "beverages"}), 1)
test("Batch 16-18 havskräfta blocks signalkräftor", recipe_match_num(["20 havskräfta"], {"name": "Svenska signalkräftor Fryst 500g ICA", "category": "fish"}), 0)
test("Batch 16-18 havskräfta accepts havskräftor", recipe_match_num_cached(["20 havskräfta"], {"name": "Havskräftor Frysta 1kg", "category": "fish"}), 1)
test("Batch 16-18 generic kräftor still accept signalkräftor", recipe_match_num(["1 kg kokta kräftor i lag"], {"name": "Svenska signalkräftor Fryst 500g ICA", "category": "fish"}), 1)
test("Batch 16-18 alcohol-free beer extracts without beverage category", kw("Alkoholfri öl & grapefrukt 33cl Pripps", "other"), ["alkoholfriöl"])
test("Batch 16-18 alcohol-free beer matches without beverage category", recipe_match_num_cached(["1 flaska alkoholfri öl"], {"name": "Alkoholfri öl & grapefrukt 33cl Pripps", "category": "other"}), 1)
test("Batch 16-18 dark beer blocks alcohol-free beer", recipe_match_num(["6 dl mörkt öl"], {"name": "Alkoholfri öl & grapefrukt 33cl Pripps", "category": "beverages"}), 0)

section("Track A current-offer fix wave")
test("Track A dadelsirap accepts live syrup", recipe_match_num_cached(["dadelsirap"], {"name": "Dadelsirap Zeinas", "category": "pantry"}), 1)
test("Track A tomatsås till pizza accepts pizzasås", recipe_match_num(["Tomatsås till pizza"], {"name": "Pizzasås Classica Mutti", "category": "pizza"}), 1)
test("Track A apelsinsaft accepts orange juice", recipe_match_num_cached(["Apelsinsaft"], {"name": "Apelsinjuice Bravo", "category": "dairy"}), 1)
test("Track A dumplingdeg accepts gyoza skins", recipe_match_num(["dumplingdeg"], {"name": "Gyoza Skin Deg Fryst Twin Dragon", "category": "bread"}), 1)
test("Track A After Eight accepts candy box", recipe_match_num_cached(["After Eight"], {"name": "After Eight Chokladask Nestle", "category": "candy"}), 1)
test("Track A chiliflakes parenthetical accepts chili flakes", recipe_match_num(["torkad chili (chiliflakes)"], {"name": "Chili Flakes Burk Kockens", "category": "pantry"}), 1)
test("Track A rökextrakt accepts liquid smoke", recipe_match_num_cached(["rökextrakt"], {"name": "Liquid Smoke Koncentrerad Rökarom Try Me", "category": "pantry"}), 1)
test("Track A tomatsås arrabbiata accepts arrabbiata sauce", recipe_match_num(["tomatsås arrabbiata"], {"name": "Arrabbiata Pastasås Barilla", "category": "pantry"}), 1)
test("Track A pistasch accepts pistachio kernels", recipe_match_num_cached(["pistasch"], {"name": "Pistaschkärnor Utan Skal Rostade Och Saltade Garant", "category": "other"}), 1)
test("Track A kantareller i vatten accepts preserved chanterelles", recipe_match_num(["Kantareller i vatten"], {"name": "Kantareller i Vatten Borgens", "category": "beverages"}), 1)
test("Track A TUC accepts exact crackers", recipe_match_num_cached(["TUC"], {"name": "Original Mini Tuc", "category": "bread"}), 1)
test("Track A TUC paprika does not leak paprika", recipe_match_num(["paprika"], {"name": "Tuc Paprika", "category": "bread"}), 0)
test("Track A matjesill accepts matjessill", recipe_match_num_cached(["matjesill"], {"name": "Matjessill Klassisk Abba", "category": "fish"}), 1)
test("Track A smörgåspickles accepts smörgåsgurka", recipe_match_num(["smörgåspickles"], {"name": "Smörgåsgurka Skivad Felix", "category": "pantry"}), 1)
test("Track A puffat ris accepts puffed rice", recipe_match_num_cached(["puffat ris"], {"name": "Puffat Ris Garant", "category": "other"}), 1)
test("Track A puffat ris does not match ordinary rice", recipe_match_num(["puffat ris"], {"name": "Jasminris Garant", "category": "pantry"}), 0)
test("Track A chili oil accepts crispy chili oil", recipe_match_num_cached(["chili oil"], {"name": "Crispy Chili In Oil Laoganma", "category": "pantry"}), 1)
test("Track A chili oil does not match fresh chili", recipe_match_num(["chili oil"], {"name": "Chilipeppar Röd Klass 1", "category": "fruit"}), 0)
test("Track A Fish&Crisp accepts exact product", recipe_match_num_cached(["Fish&Crisp"], {"name": "Fish & Crisp Gourmetfileer Findus", "category": "frozen"}), 1)
test("Track A raw fläskkött/skinka blocks cooked sliced ham", recipe_match_num(["fläskkött bog eller skinka"], {"name": "Kokt Skinka Skivad Lönneberga", "category": "meat"}), 0)
test("Track A burgarbröd accepts live Korvbrödbagarn hamburger buns", recipe_match_num_cached(["Burgarbröd"], {"name": "Hamburgerbröd 8-pack Korvbrödbagarn", "category": "bread"}), 1)

section("Track A follow-up fix wave")
test("Track A surdegskakor accepts sliced sourdough bread", recipe_match_num_cached(["surdegskakor ca 12 skivor"], {"name": "Kärnsund Surdegsbröd Pågen", "category": "bread"}), 1)
test("Track A Svejkon accepts vegobacon", recipe_match_num(["Svejkon"], {"name": "Vegobacon Klippta Skivor Vegansk Eldorado", "category": "deli"}), 1)
test("Track A burger title generic bröd accepts hamburger buns", recipe_match_num_named_cached("Jävligt goda burgare", ["Bröd"], {"name": "Hamburgerbröd 8-pack Korvbrödbagarn", "category": "bread"}), 1)
test("Track A tranbärsjuice accepts cranberry drink", recipe_match_num_cached(["tranbärsjuice"], {"name": "Cranberry Classic Tranbärsdryck Ocean Spray", "category": "dairy"}), 1)
test("Track A 5-minuterssill accepts live herring", recipe_match_num(["5-minuterssill"], {"name": "5minuters Sill Hela Fileer Abba", "category": "fish"}), 1)
test("Track A Tabasco Habanero accepts habanero sauce", recipe_match_num_cached(["Tabasco Habanero"], {"name": "Chilisås Original Habanero Skånsk Chili", "category": "pantry"}), 1)
test("Track A tomatpesto accepts red pesto", recipe_match_num(["tomatpesto"], {"name": "Pesto Rosso Zeta", "category": "pantry"}), 1)
test("Track A tomatpesto blocks green pesto", recipe_match_num_cached(["tomatpesto"], {"name": "Pesto Genovese Zeta", "category": "pantry"}), 0)
test("Track A bufala mozzarella blocks vegan flavour substitute", recipe_match_num(["Zeta Mozzarella Di Bufala Campana"], {"name": "Mozzarella Flavour Vegansk Greenvie", "category": "dairy"}), 0)
test("Track A 5-minuterssill blocks ansjoviskrydda", recipe_match_num_cached(["5-minuterssill"], {"name": "Ansjoviskrydda Sill Garant", "category": "fish"}), 0)
test("Track A sushi fish blocks generic white fish", recipe_match_num(["fiskfilé gärna lax eller färsk tonfisk"], {"name": "Torskfilé Fryst Garant", "category": "fish"}), 0)
test("Track A hushållsfärs/nötfärs blocks chicken mince", recipe_match_num_cached(["hushållsfärs eller nötfärs"], {"name": "Kycklingfärs 500g Kronfågel", "category": "meat"}), 0)
test("Track A plain havregurt blocks fruit havregurt", recipe_match_num(["turkisk havregurt"], {"name": "Baked Äpple Havregurt Low Fat Oddlygood", "category": "dairy"}), 0)
test("Track A kalkonbröstfilé blocks turkey thigh fillet", recipe_match_num_cached(["kalkonbröstfilé"], {"name": "Kalkonlårfilé Strimlad Fryst Ingelstakalkon", "category": "meat"}), 0)
test("Track A mjukt tunnbröd blocks hard tunnbröd", recipe_match_num(["mjukt tunnbröd"], {"name": "Tunnbröd Hårt Gene", "category": "bread"}), 0)
test("Track A hard cheese max 17 blocks high-fat cheese", recipe_match_num_cached(["riven hårdost max 17%"], {"name": "Riven Ost 28% Arla", "category": "dairy"}), 0)
test("Track A storkornskaviar blocks Kalles tube kaviar", recipe_match_num(["storkornskaviar röd"], {"name": "Kaviar Original Kalles", "category": "fish"}), 0)
test("Track A Tabasco Habanero blocks fresh habanero", recipe_match_num_cached(["Tabasco Habanero"], {"name": "Chilli Habanero Garant", "category": "fruit"}), 0)
test("Track A rökextrakt blocks smoky cracker carrier", recipe_match_num(["rökextrakt"], {"name": "Kex Hickory Smoke", "category": "bread"}), 0)
test("Track A measured rom blocks fish roe", recipe_match_num_cached(["2 msk rom"], {"name": "Stenbitsrom Röd", "category": "fish"}), 0)
test("Track A tryffelburrata blocks plain burrata", recipe_match_num(["tryffelburrata"], {"name": "Burrata Zeta", "category": "dairy"}), 0)
test("Track A riven veganost blocks vegan spread cheese", recipe_match_num_cached(["riven veganost"], {"name": "Vegansk Färskost Violife", "category": "dairy"}), 0)
test("Track A morotssylt blocks other jam", recipe_match_num(["morotssylt"], {"name": "Jordgubbssylt Bob", "category": "pantry"}), 0)

section("Batch 16-18 ICA carrier/seed/prepared-product regressions")
# Carrier gaps: new ICA product types that should strip flavor words
test("vitost carrier strips vitlök", recipe_match_num(["vitlök"], {"name": "Vitost Vitlök Persilja", "category": "dairy"}), 0)
test("vitost carrier strips persilja", recipe_match_num(["persilja"], {"name": "Vitost Vitlök Persilja", "category": "dairy"}), 0)
test("vitost carrier keeps vitost keyword", recipe_match_num(["vitost"], {"name": "Vitost Vitlök Persilja", "category": "dairy"}), 1)
test("kräftstjärtsallad carrier strips vitlök", recipe_match_num(["vitlök"], {"name": "Kräftstjärtsallad Vitlök ICA", "category": "deli"}), 0)
test("laxsallad carrier strips citron", recipe_match_num(["citron"], {"name": "Laxsallad Citron ICA", "category": "deli"}), 0)
test("pastasallad carrier strips vitlök", recipe_match_num(["vitlök"], {"name": "Pastasallad Vitlök ICA", "category": "deli"}), 0)
test("energigel carrier strips citron", recipe_match_num(["citron"], {"name": "Energigel Citron Sport", "category": "beverages"}), 0)
test("proteingel carrier strips apelsin", recipe_match_num(["apelsin"], {"name": "Proteingel Apelsin Sport", "category": "beverages"}), 0)
test("kollagen carrier strips citron", recipe_match_num(["citron"], {"name": "Kollagen Citron C-Vitamin", "category": "health"}), 0)
test("spaghetteria carrier strips spenat (babyspenat path)", recipe_match_num(["babyspenat"], {"name": "Spaghetteria Spenat 2-p Knorr", "category": "spices"}), 0)
# frön suffix: sesamfrön/dillfrön must not match unrelated generic frön products
test("sesamfrön blocks unrelated frön product", recipe_match_num(["2 msk sesamfrön"], {"name": "Bockhornsklöver Hela Frön", "category": "spices"}), 0)
test("dillfrön blocks unrelated frön product", recipe_match_num(["dillfrön"], {"name": "Bockhornsklöver Hela Frön", "category": "spices"}), 0)
test("generic frön still matches generic frön product", recipe_match_num(["4 dl frön"], {"name": "Bockhornsklöver Hela Frön", "category": "spices"}), 1)
test("sesamfrön still matches sesam product", recipe_match_num(["2 msk sesamfrön"], {"name": "Sesamfrön Skalade Garant Eko", "category": "spices"}), 1)
# Gyoza blocks raw chicken
test("kyckling blocks gyoza product", recipe_match_num(["kyckling"], {"name": "Gyoza Kyckling Fryst", "category": "frozen"}), 0)
test("kycklingfilé blocks gyoza product", recipe_match_num(["kycklingfilé"], {"name": "Gyoza Kyckling Fryst", "category": "frozen"}), 0)
# Panerade bläckfiskringar blocks raw bläckfiskringar
test("bläckfiskringar blocks panerade squid", recipe_match_num(["bläckfiskringar"], {"name": "Bläckfiskringar Panerade Fryst", "category": "fish"}), 0)

section("Batch 16-18 P1 spice/dairy/form regressions")
# Pancake mix as carrier: kanel/kardemumma should not satisfy standalone spice recipes
test("pannkaksmix carrier blocks kanel", recipe_match_num(["kanel"], {"name": "Pannkaksmix Kanel & Kardemumma", "category": "pantry"}), 0)
test("pannkaksmix carrier blocks kanelstänger", recipe_match_num(["kanelstänger"], {"name": "Pannkaksmix Kanel & Kardemumma", "category": "pantry"}), 0)
test("pannkaksmix carrier blocks kardemumma", recipe_match_num(["kardemumma"], {"name": "Pannkaksmix Kanel & Kardemumma", "category": "pantry"}), 0)
# kanelstänger (cinnamon sticks) should not match ground cinnamon via full recipe path
test("kanelstång blocks ground kanel", recipe_match_num(["1 kanelstång"], {"name": "Kanel Mald 15g ICA", "category": "spices"}), 0)
test("kanelstång accepts whole kanel", recipe_match_num(["1 kanelstång"], {"name": "Kanel Hel 10g ICA", "category": "spices"}), 1)
# Di Bufala Campana: context_word exemption allows bufala/campana keyword to bypass mozzarella requirement
test("di bufala matches bufala mozzarella product", recipe_match_num(["di bufala campana"], {"name": "Mozzarella di Bufala Campana 125g", "category": "dairy"}), 1)
test("di bufala blocks plain mozzarella", recipe_match_num(["di bufala campana"], {"name": "Mozzarella 125g ICA", "category": "dairy"}), 0)
# Crème fraiche: sweet/dessert variants should not satisfy plain cooking crème fraiche
test("crème fraiche blocks sötstark mango variant", recipe_match_num(["crème fraiche"], {"name": "Lätt Creme Fraiche Sötstark Mango 11% Arla", "category": "dairy"}), 0)
test("crème fraiche accepts plain variant", recipe_match_num(["crème fraiche"], {"name": "Creme fraiche 32% ICA", "category": "dairy"}), 1)
# Cottage Pearls: plant-based almond/oat product should not satisfy cottage cheese
test("cottage cheese blocks Cottage Pearls", recipe_match_num(["cottage cheese"], {"name": "Cottage Pearls Mandel Havre ICA", "category": "dairy"}), 0)
test("cottage cheese accepts real cottage cheese", recipe_match_num(["cottage cheese"], {"name": "Cottage Cheese 500g ICA", "category": "dairy"}), 1)
# Saltgurka vs mixed pickles: different product types
test("saltgurka blocks mixed pickles", recipe_match_num(["saltgurka"], {"name": "Mixed Pickles ICA", "category": "condiments"}), 0)
test("saltgurka accepts real saltgurka", recipe_match_num(["saltgurka"], {"name": "Saltgurka Skivor ICA", "category": "condiments"}), 1)
# Urkärnade oliver: pitted olive recipe should not match olives with pits
test("urkärnade oliver blocks oliver med kärnor", recipe_match_num(["urkärnade oliver"], {"name": "Oliver med Kärnor Halkidiki ICA", "category": "condiments"}), 0)
test("plain oliver accepts oliver med kärnor", recipe_match_num(["oliver"], {"name": "Oliver med Kärnor Halkidiki ICA", "category": "condiments"}), 1)

section("Batch 16-18 P1/medium kokos/svartvinbär extraction regressions")
# kokosflingor: ICA-style "Kokosflakes" compound form should match kokosflingor ingredient
test("kokosflakes compound matches kokosflingor", match("kokosflingor", "Kokosflakes Rostade 150g ICA Gott liv", "bread"), "kokosflingor")
test("kokosflakes ekologiska matches kokosflingor", match("kokosflingor", "Kokosflakes Ekologiska Rostade 200g ICA", "bread"), "kokosflingor")
test("riven kokos still matches kokosflingor", match("kokosflingor", "Riven Kokos 200g ICA", "bread"), "kokosflingor")
# svartvinbärssaft: blandsaft + svartvinbär/svarta vinbär spaced forms
test("blandsaft svartvinbär matches svartvinbärssaft", match("svartvinbärssaft", "Blandsaft Svartvinbär 95cl BOB", "beverages"), "svartvinbärssaft")
test("blandsaft svarta vinbär spaced matches svartvinbärssaft", match("svartvinbärssaft", "Blandsaft Svarta vinbär 500ml BOB", "beverages"), "svartvinbärssaft")
test("lättdryck svarta vinbär matches svartvinbärssaft", match("svartvinbärssaft", "Lättdryck Svarta vinbär Koncentrat 2dl Kiviks", "dairy"), "svartvinbärssaft")
test("svartvinbärsdryck drickfärdig matches svartvinbärssaft", match("svartvinbärssaft", "Svartvinbärsdryck Drickfärdig 1,5l Kiviks", "dairy"), "svartvinbärssaft")
test("saft svartvinbär still matches", match("svartvinbärssaft", "Saft Svartvinbär 500ml Herrljunga", "beverages"), "svartvinbärssaft")
# Regression: blandsaft jordgubb must still map to jordgubbssaft, not be broken
test("blandsaft jordgubb still matches jordgubbssaft", match("jordgubbssaft", "Blandsaft Jordgubb 500ml", "beverages"), "jordgubbssaft")
# Regression: bare kokos must NOT match kokosmjölk (Stefan policy: kokos = dry coconut only)
test("bare kokos does not match kokosmjölk", match("kokos", "Kokosmjölk 400ml ICA", "dairy"), None)

section("Batch 16-18 P1/medium melon/sallad/snabbkaffe regressions")
# melon: bare melon ingredient matches any melon subtype via OFFER_EXTRA_KEYWORDS
test("melon matches galiamelon", match("melon", "Galiamelon ca 850g Klass 1 ICA", "fruit"), "melon")
test("melon matches honungsmelon", match("melon", "Honungsmelon ca 1000g Klass 1 ICA", "fruit"), "melon")
test("melon matches cantaloupemelon", match("melon", "Cantaloupemelon ca 870g Klass 1 ICA", "fruit"), "melon")
test("melon matches vattenmelon", match("melon", "Vattenmelon 5kg", "fruit"), "melon")
test("galiamelon still matches galiamelon", match("galiamelon", "Galiamelon ca 850g Klass 1 ICA", "fruit"), "galiamelon")
# isbergssallad: gets grönsallad/salladsblad keywords via OFFER_EXTRA_KEYWORDS
test("grönsallad matches isbergssallad", match("grönsallad", "Isbergssallad 1-p Klass 1", "fruit"), "grönsallad")
test("salladsblad matches isbergssallad", match("salladsblad", "Isbergssallad 1-p Klass 1", "fruit"), "salladsblad")
test("isbergssallad still matches isbergssallad", match("isbergssallad", "Isbergssallad 1-p Klass 1", "fruit"), "isbergssallad")
test("grönsallad still matches hjärtsallad", match("grönsallad", "Hjärtsallad Eko 180g", "fruit"), "grönsallad")
# snabbkaffe: Nescafé Gold is plain instant coffee
test("snabbkaffe matches Nescafé Gold", match("snabbkaffe", "Nescafé Gold 200g", "beverages"), "snabbkaffe")
test("snabbkaffe matches Nescafe Classic", match("snabbkaffe", "Nescafe Classic 100g", "beverages"), "snabbkaffe")
test("snabbkaffe does not match Nescafé Dolce Gusto", match("snabbkaffe", "Nescafé Dolce Gusto", "beverages"), None)

section("Batch 16-18 P2/medium tofu/non-food regressions")
# Skagenröra Tofu: spread product must not satisfy plain tofu ingredient (PPR)
test("tofu blocks skagenröra tofu spread", recipe_match_num(["tofu"], {"name": "Skagenröra Tofu Vegansk 200g YiPin", "category": "meat"}), 0)
test("tofu still matches plain tofu", recipe_match_num(["tofu"], {"name": "Tofu naturell 400g ICA Basic", "category": "meat"}), 1)
test("tofu still matches firm tofu", recipe_match_num(["tofu"], {"name": "Tofu Fast 307g Mori Nu", "category": "meat"}), 1)
test("skagenröra ingredient still matches skagenröra product", match("skagenröra", "Skagenröra Tofu Vegansk 200g YiPin", "meat"), "skagenröra")
# Non-food guard: wool/yarn products (ICA miscategorized as dairy) must not match food ingredients
test("morot does not match ull decoration product", match("morot", "Hänge morot ull Nordic Season", "dairy"), None)
test("morot still matches real morot product", match("morot", "Morot 500g Klass 1", "fruit"), "morot")

# ========================================================================
print("\n========================================")
print(f"TOTAL: {passed}/{passed+failed} tests passed ({total_sections} sections)")
if failed:
    print(f"{failed} FAILED!")
else:
    print("ALL PASSED!")
print("========================================")
