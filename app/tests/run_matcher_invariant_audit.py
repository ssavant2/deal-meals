#!/usr/bin/env python3
"""Live DB invariant audit for Swedish recipe-offer matching.

This intentionally tests policy invariants against the current offer table.
It does not refresh caches, rebuild compiled match data, or run dev_reload.

Run:
    docker compose exec -T web python tests/run_matcher_invariant_audit.py
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Callable, Iterable

sys.path.insert(0, "/app" if os.path.exists("/app") else os.path.join(os.path.dirname(__file__), ".."))

from database import get_db_session  # noqa: E402
from languages.sv.ingredient_matching import (  # noqa: E402
    extract_keywords_from_product,
    precompute_offer_data,
)
from languages.sv.normalization import fix_swedish_chars  # noqa: E402
from models import Offer, Store  # noqa: E402
from recipe_matcher import RecipeMatcher  # noqa: E402


@dataclass(frozen=True)
class AuditOffer:
    id: str
    name: str
    category: str
    brand: str
    price: float
    original_price: float | None
    savings: float
    store: object
    product_url: str | None
    is_multi_buy: bool
    multi_buy_quantity: int | None
    weight_grams: float | None


@dataclass(frozen=True)
class Failure:
    section: str
    check: str
    ingredient: str
    offer: AuditOffer | None
    detail: str


def norm(text: str | None) -> str:
    return fix_swedish_chars(text or "").lower()


def offer_stub(offer: Offer) -> AuditOffer:
    return AuditOffer(
        id=str(offer.id),
        name=offer.name,
        category=offer.category or "",
        brand=offer.brand or "",
        price=float(offer.price) if offer.price else 0.0,
        original_price=float(offer.original_price) if offer.original_price else None,
        savings=float(offer.savings) if offer.savings else 0.0,
        store=SimpleNamespace(name=offer.store.name if offer.store else "Willys"),
        product_url=offer.product_url,
        is_multi_buy=bool(offer.is_multi_buy),
        multi_buy_quantity=offer.multi_buy_quantity,
        weight_grams=float(offer.weight_grams) if offer.weight_grams is not None else None,
    )


def load_offers() -> list[AuditOffer]:
    with get_db_session() as db:
        rows = (
            db.query(Offer)
            .join(Store)
            .filter(Store.store_type == "willys")
            .order_by(Offer.category, Offer.name, Offer.id)
            .all()
        )
        return [offer_stub(row) for row in rows]


def build_caches(offers: Iterable[AuditOffer]) -> tuple[dict[int, set[str]], dict[int, dict]]:
    offer_keywords: dict[int, set[str]] = {}
    offer_data_cache: dict[int, dict] = {}
    for offer in offers:
        oid = id(offer)
        offer_keywords[oid] = extract_keywords_from_product(
            offer.name,
            offer.category,
            brand=offer.brand,
        )
        offer_data_cache[oid] = precompute_offer_data(
            offer.name,
            offer.category,
            brand=offer.brand,
            weight_grams=offer.weight_grams,
        )
    return offer_keywords, offer_data_cache


class MatcherAudit:
    def __init__(self, offers: list[AuditOffer]) -> None:
        self.offers = offers
        self.matcher = RecipeMatcher()
        self.offer_keywords, self.offer_data_cache = build_caches(offers)
        self.failures: list[Failure] = []
        self.checks = 0

    def match(self, ingredient: str, offers: list[AuditOffer] | None = None) -> set[str]:
        selected_offers = offers if offers is not None else self.offers
        recipe = SimpleNamespace(
            id=f"audit-{self.checks}",
            name="Matcher invariant audit",
            ingredients=[ingredient],
        )
        result = self.matcher._match_recipe_to_offers(
            recipe,
            selected_offers,
            preferences={},
            offer_keywords=self.offer_keywords,
            offer_data_cache=self.offer_data_cache,
        )
        return {str(offer["id"]) for offer in result["matched_offers"]}

    def expect_all_match(
        self,
        *,
        section: str,
        check: str,
        ingredient: str,
        candidates: list[AuditOffer],
    ) -> None:
        self.checks += 1
        matched = self.match(ingredient, candidates)
        for offer in candidates:
            if offer.id not in matched:
                self.failures.append(
                    Failure(
                        section=section,
                        check=check,
                        ingredient=ingredient,
                        offer=offer,
                        detail="expected live offer to match",
                    )
                )

    def expect_none_match(
        self,
        *,
        section: str,
        check: str,
        ingredient: str,
        candidates: list[AuditOffer],
    ) -> None:
        self.checks += 1
        matched = self.match(ingredient, candidates)
        for offer in candidates:
            if offer.id in matched:
                self.failures.append(
                    Failure(
                        section=section,
                        check=check,
                        ingredient=ingredient,
                        offer=offer,
                        detail="expected live offer not to match",
                    )
                )

    def expect_matched_subset(
        self,
        *,
        section: str,
        check: str,
        ingredient: str,
        forbidden: Callable[[AuditOffer], bool],
        allowed: Callable[[AuditOffer], bool],
    ) -> None:
        self.checks += 1
        matched_ids = self.match(ingredient)
        by_id = {offer.id: offer for offer in self.offers}
        for offer_id in matched_ids:
            offer = by_id[offer_id]
            if forbidden(offer) or not allowed(offer):
                self.failures.append(
                    Failure(
                        section=section,
                        check=check,
                        ingredient=ingredient,
                        offer=offer,
                        detail="matched outside allowed invariant subset",
                    )
                )


def contains_any(text: str, words: Iterable[str]) -> bool:
    return any(word in text for word in words)


def word_re(words: Iterable[str]) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(re.escape(word) for word in words) + r")\b")


READY_OR_CARRIER_CUES = word_re(
    [
        "paj",
        "soppa",
        "burek",
        "canneloni",
        "cannelloni",
        "pizza",
        "pan",
        "nuggets",
        "pinnar",
        "stuvad",
        "gratäng",
        "gratangen",
        "sås",
        "sas",
        "sauce",
        "mayo",
        "dressing",
        "ketchup",
        "glaze",
        "marinad",
        "olja",
        "grillolja",
        "kryddmix",
        "dippmix",
        "chips",
        "chip",
        "tortilla",
        "riskakor",
        "majskakor",
        "snus",
        "tobaksfritt",
        "choklad",
        "korv",
        "salami",
        "karré",
        "karre",
        "grillspett",
        "färs",
        "fars",
        "kött",
        "kott",
        "nudlar",
        "ramen",
        "oliver",
    ]
)


READY_OR_CARRIER_SUBSTRINGS = (
    "paj",
    "soppa",
    "burek",
    "canneloni",
    "cannelloni",
    "pizza",
    "nuggets",
    "pinnar",
    "stuvad",
    "gratäng",
    "gratang",
    "sås",
    "sas",
    "sauce",
    "mayo",
    "dressing",
    "ketchup",
    "glaze",
    "marinad",
    "grillolja",
    "kryddmix",
    "dippmix",
    "chips",
    "chip",
    "tortilla",
    "riskakor",
    "majskakor",
    "snus",
    "tobaksfritt",
    "choklad",
    "korv",
    "salami",
    "karré",
    "karre",
    "grillspett",
    "färs",
    "fars",
    "kött",
    "kott",
    "nudlar",
    "ramen",
    "oliver",
)


def is_ready_or_carrier(text: str) -> bool:
    return READY_OR_CARRIER_CUES.search(text) is not None or contains_any(text, READY_OR_CARRIER_SUBSTRINGS)


def select_plain_frozen(
    offers: list[AuditOffer],
    *,
    include: Iterable[str],
    exclude_ready: bool = True,
) -> list[AuditOffer]:
    include = tuple(include)
    selected: list[AuditOffer] = []
    for offer in offers:
        text = norm(offer.name)
        if offer.category not in {"frozen", "vegetables", "fruit"}:
            continue
        if "fryst" not in text and "frysta" not in text:
            continue
        if not contains_any(text, include):
            continue
        if exclude_ready and is_ready_or_carrier(text):
            continue
        if contains_any(text, ["broccolimix", "blomkålsris", "blomkalsris"]):
            continue
        selected.append(offer)
    return selected


def select_name_family(
    offers: list[AuditOffer],
    *,
    include: Iterable[str],
    categories: set[str] | None = None,
    exclude: Iterable[str] = (),
) -> list[AuditOffer]:
    include = tuple(include)
    exclude = tuple(exclude)
    selected: list[AuditOffer] = []
    for offer in offers:
        text = norm(offer.name)
        if categories is not None and offer.category not in categories:
            continue
        if not contains_any(text, include):
            continue
        if exclude and contains_any(text, exclude):
            continue
        selected.append(offer)
    return selected


def run_fresh_frozen_produce(audit: MatcherAudit) -> None:
    cases = [
        ("färsk gräslök accepts frozen chives", "5 g färsk gräslök", ["gräslök", "graslok"]),
        ("plain parsley sprigs accept frozen parsley", "ett par persiljekvistar", ["persilja"]),
        ("fresh coriander accepts frozen coriander", "2 msk färsk koriander", ["koriander"]),
        ("fresh basil accepts frozen basil", "2 msk färsk basilika", ["basilika"]),
        ("plain broccoli accepts plain frozen broccoli", "250 g broccoli", ["broccoli"]),
        ("plain spinach accepts plain frozen spinach", "200 g spenat", ["spenat", "bladspenat"]),
        ("plain cauliflower accepts plain frozen cauliflower", "250 g blomkål", ["blomkål", "blomkal"]),
        ("plain haricots verts accept frozen haricots verts", "200 g haricots verts", ["haricots verts"]),
        ("plain mushrooms accept frozen mushrooms", "250 g champinjoner", ["champinjon"]),
    ]
    for check, ingredient, include in cases:
        candidates = select_plain_frozen(audit.offers, include=include)
        audit.expect_all_match(
            section="fresh/frozen produce",
            check=check,
            ingredient=ingredient,
            candidates=candidates,
        )

    dried_herb_cases = [
        ("dried-measure chives block frozen chives", "1 tsk gräslök", ["gräslök", "graslok"]),
        ("dried-measure parsley block frozen parsley", "1 tsk persilja", ["persilja"]),
        ("dried-measure coriander block frozen coriander", "1 tsk koriander", ["koriander"]),
        ("dried-measure basil block frozen basil", "1 tsk basilika", ["basilika"]),
    ]
    for check, ingredient, include in dried_herb_cases:
        candidates = select_plain_frozen(audit.offers, include=include)
        audit.expect_none_match(
            section="fresh/frozen produce",
            check=check,
            ingredient=ingredient,
            candidates=candidates,
        )


def run_chili(audit: MatcherAudit) -> None:
    positive = select_name_family(
        audit.offers,
        categories={"fruit", "frozen"},
        include=[
            "chili röd",
            "chilli habanero",
            "chilli jalapeno",
            "chilli peppar",
            "chilli piri",
            "chillipeppar",
            "chili hackad fryst",
            "jalapeno hackad fryst",
        ],
        exclude=["snus", "tobaksfritt", "torkad", "kryddmix", "taco", "mayo"],
    )
    audit.expect_all_match(
        section="fresh chili",
        check="generic chilifrukter match fresh/frozen plain chili products",
        ingredient="2 st chilifrukter",
        candidates=positive,
    )

    negative = select_name_family(
        audit.offers,
        include=["chili", "chilli", "jalapeno", "habanero", "piri"],
        exclude=[
            "chili röd",
            "chilli habanero",
            "chilli jalapeno",
            "chilli peppar",
            "chilli piri",
            "chillipeppar",
            "chili hackad fryst",
            "jalapeno hackad fryst",
            "chili flakes",
            "chili pulver",
            "chilipulver",
            "chiliflingor",
            "chilipeppar burk",
            "chili habanero burk",
            "chili jalapeno flakes",
            "gochugaru",
        ],
    )
    negative = [offer for offer in negative if is_ready_or_carrier(norm(offer.name))]
    audit.expect_none_match(
        section="fresh chili",
        check="generic chilifrukter reject flavor carriers, sauces, snacks, meat, snus",
        ingredient="2 st chilifrukter",
        candidates=negative,
    )


def run_micropopcorn(audit: MatcherAudit) -> None:
    candidates = select_name_family(
        audit.offers,
        categories={"candy"},
        include=["micropop", "micropopcorn", "mikropop", "mikropopcorn"],
        exclude=["cheddar"],
    )
    for ingredient in ("1 påse micropopcorn", "1 påse mikropopcorn"):
        audit.expect_all_match(
            section="normalization",
            check=f"{ingredient} matches micro/mikro popcorn offers",
            ingredient=ingredient,
            candidates=candidates,
        )


def run_plant_based_gurt(audit: MatcherAudit) -> None:
    plant_gurts = select_name_family(
        audit.offers,
        categories={"dairy"},
        include=["plantgurt", "havregurt", "kokosgurt", "soygurt"],
        exclude=["blueberry", "baked äpple", "baked apple", "mango", "raspberry", "strawberry", "vanilla"],
    )
    audit.expect_all_match(
        section="plant-based dairy",
        check="växtbaserad gurt matches plant-based gurt/yoghurt families",
        ingredient="1 dl växtbaserad gurt",
        candidates=plant_gurts,
    )

    plant_markers = ("plantgurt", "havregurt", "kokosgurt", "soygurt", "alpro", "oddlygood", "oatly")

    audit.expect_matched_subset(
        section="plant-based dairy",
        check="växtbaserad gurt does not match ordinary yoghurt",
        ingredient="1 dl växtbaserad gurt",
        forbidden=lambda offer: offer.category == "dairy"
        and contains_any(norm(offer.name), ["yoghurt", "yogurt", "gurt"])
        and not contains_any(norm(offer.name + " " + offer.brand), plant_markers),
        allowed=lambda offer: contains_any(norm(offer.name + " " + offer.brand), plant_markers),
    )


def run_flavor_carriers(audit: MatcherAudit) -> None:
    audit.expect_matched_subset(
        section="flavor carriers",
        check="parmesan ingredient only matches cheese-like products",
        ingredient="1 dl parmesan",
        forbidden=lambda offer: is_ready_or_carrier(norm(offer.name)),
        allowed=lambda offer: offer.category == "dairy",
    )

    audit.expect_matched_subset(
        section="flavor carriers",
        check="honung ingredient does not match glaze/meat/sauce flavor carriers",
        ingredient="1 msk honung",
        forbidden=lambda offer: is_ready_or_carrier(norm(offer.name))
        or offer.category in {"meat", "poultry", "fish", "bread", "candy"},
        allowed=lambda offer: offer.category in {"pantry", "spices", "other"},
    )

    audit.expect_matched_subset(
        section="flavor carriers",
        check="gul lök ingredient stays on onion/produce-like products",
        ingredient="1 st gul lök",
        forbidden=lambda offer: is_ready_or_carrier(norm(offer.name))
        or offer.category in {"meat", "poultry", "fish", "bread", "candy", "dairy", "pizza"},
        allowed=lambda offer: offer.category in {"vegetables", "fruit", "frozen"},
    )


def run_stock_fond_policy(audit: MatcherAudit) -> None:
    shellfish_fond_words = ("hummer", "räk", "rak", "kräft", "kraft", "krabb", "mussel", "musslor", "skaldjur")
    shellfish_fonds = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"pantry"},
            include=["fond"],
        )
        if contains_any(norm(offer.name), shellfish_fond_words)
    ]
    audit.expect_all_match(
        section="fond policy",
        check="skaldjursfond accepts shellfish fond family",
        ingredient="1.5 msk Skaldjursfond",
        candidates=shellfish_fonds,
    )

    fish_fonds = select_name_family(
        audit.offers,
        categories={"pantry"},
        include=["fiskfond"],
    )
    audit.expect_none_match(
        section="fond policy",
        check="skaldjursfond rejects ordinary fish fond",
        ingredient="1.5 msk Skaldjursfond",
        candidates=fish_fonds,
    )


def run_rice_policy(audit: MatcherAudit) -> None:
    standard_rice_words = ("jasminris", "basmati", "fullkornsris", "långkorn", "langkorn")
    standard_rice = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"pantry"},
            include=["ris"],
        )
        if contains_any(norm(offer.name), standard_rice_words)
    ]
    audit.expect_all_match(
        section="rice policy",
        check="jasminris accepts everyday standard rice variants",
        ingredient="4 dl Jasminris",
        candidates=standard_rice,
    )


def run_exact_specific_policy(audit: MatcherAudit) -> None:
    truffle_oils = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"pantry"},
            include=["tryffel"],
        )
        if re.search(r"\b(?:olivolja|olja)\b", norm(offer.name)) is not None
    ]
    audit.expect_all_match(
        section="exact specific policy",
        check="tryffelolja accepts truffle oil regardless of truffle color",
        ingredient="1 msk Zeta Olivolja Vit Tryffel",
        candidates=truffle_oils,
    )

    non_truffle_olive_oils = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"pantry"},
            include=["olivolja"],
            exclude=["tryffel"],
        )
    ]
    audit.expect_none_match(
        section="exact specific policy",
        check="tryffelolja rejects plain olive oil fallback",
        ingredient="1 msk Zeta Olivolja Vit Tryffel",
        candidates=non_truffle_olive_oils,
    )


def run_meat_component_policy(audit: MatcherAudit) -> None:
    sausage_words = ("korv", "chorizo", "salsiccia")
    highrev_sausages = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"meat"},
            include=["högrev"],
        )
        if contains_any(norm(offer.name), sausage_words)
    ]
    audit.expect_none_match(
        section="meat component policy",
        check="raw högrev rejects sausage products where högrev is only a component",
        ingredient="900 g Högrev",
        candidates=highrev_sausages,
    )


def run_batch2_direct_fix_policy(audit: MatcherAudit) -> None:
    fresh_carrots = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"fruit", "vegetables"},
            include=["morot"],
        )
        if not is_ready_or_carrier(norm(offer.name))
        and not contains_any(norm(offer.name), (
            "juice", "surkål", "surkal", "kålmix", "kalmix",
            "från", "fran", "mån", "man", "pure", "smoothie",
        ))
    ]
    audit.expect_all_match(
        section="batch2 direct fixes",
        check="morätter typo accepts ordinary carrots",
        ingredient="2 morätter",
        candidates=fresh_carrots,
    )

    chocolate_drinks = [
        offer for offer in audit.offers
        if contains_any(norm(offer.name), ("chokladdryck", "o'boy", "oboy"))
    ]
    audit.expect_all_match(
        section="batch2 direct fixes",
        check="chokladdryck accepts chocolate drink powders",
        ingredient="0.75 dl Chokladdryck",
        candidates=chocolate_drinks,
    )

    solid_chocolate = select_name_family(
        audit.offers,
        categories={"candy", "pantry"},
        include=["choklad"],
        exclude=["chokladdryck", "o'boy", "oboy"],
    )
    audit.expect_none_match(
        section="batch2 direct fixes",
        check="chokladdryck rejects solid chocolate fallback",
        ingredient="0.75 dl Chokladdryck",
        candidates=solid_chocolate,
    )

    raw_chicken_fillets = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"meat"},
            include=["kyckling"],
        )
        if contains_any(norm(offer.name), ("filé", "file", "bröstfil", "brostfil", "innerfil", "minutstrimlor"))
        and not contains_any(norm(offer.name), (
            "pastrami", "stekt", "färdiglagad", "fardiglagad",
            "teriyaki", "grillad skivad", "grillkryddad skivad",
            "tunna skivor", "deliskivor",
        ))
    ]
    audit.expect_all_match(
        section="batch2 direct fixes",
        check="kycklingfile accepts raw chicken fillet family",
        ingredient="200 g Kycklingfile",
        candidates=raw_chicken_fillets,
    )

    cooked_or_deli_chicken = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"meat"},
            include=["filé"],
        )
        if contains_any(norm(offer.name), ("pastrami", "grillad skivad", "grillkryddad skivad"))
    ]
    audit.expect_none_match(
        section="batch2 direct fixes",
        check="kycklingfile rejects cooked/deli sliced chicken",
        ingredient="200 g Kycklingfile",
        candidates=cooked_or_deli_chicken,
    )

    paprika_spice_products = [
        offer for offer in audit.offers
        if offer.category in {"pantry", "spices"}
        and (
            "paprikapulver" in norm(offer.name)
            or re.search(r"\bpaprika\s+(?:burk|påse|pase)\b", norm(offer.name)) is not None
            or re.search(r"\b(?:rökt|rokt)\s+paprika\b", norm(offer.name)) is not None
        )
        and "stark" not in norm(offer.name)
    ]
    audit.expect_all_match(
        section="batch2 direct fixes",
        check="optional smoked paprikapulver accepts plain and smoked paprika spice jars",
        ingredient="2 tsk paprikapulver, ev rökt",
        candidates=paprika_spice_products,
    )

    smoked_paprika_spices = [
        offer for offer in paprika_spice_products
        if re.search(r"\b(?:rökt|rokt)\s+paprika\b", norm(offer.name)) is not None
    ]
    audit.expect_all_match(
        section="batch2 direct fixes",
        check="explicit rökt paprikapulver accepts smoked paprika spice jars",
        ingredient="1 tsk Rökt paprikapulver",
        candidates=smoked_paprika_spices,
    )

    plain_paprika_spices = [
        offer for offer in paprika_spice_products
        if re.search(r"\b(?:rökt|rokt)\s+paprika\b", norm(offer.name)) is None
    ]
    audit.expect_none_match(
        section="batch2 direct fixes",
        check="explicit rökt paprikapulver rejects plain paprika spice jars",
        ingredient="1 tsk Rökt paprikapulver",
        candidates=plain_paprika_spices,
    )

    fresh_paprika_products = [
        offer for offer in audit.offers
        if offer.category in {"fruit", "vegetables"}
        and "paprika" in norm(offer.name)
    ]
    audit.expect_none_match(
        section="batch2 direct fixes",
        check="paprikapulver rejects fresh or preserved bell-pepper products",
        ingredient="2 tsk paprikapulver, ev rökt",
        candidates=fresh_paprika_products,
    )

    vasterbotten_cheeses = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"dairy"},
            include=["västerbottens", "vasterbottens"],
            exclude=["philadelphia", "färskost", "farskost", "bites"],
        )
    ]
    audit.expect_all_match(
        section="batch2 direct fixes",
        check="riven västerbottensost accepts västerbottensost cheese products",
        ingredient="2 dl riven Västerbottensost",
        candidates=vasterbotten_cheeses,
    )

    vasterbotten_fresh_cheese = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"dairy"},
            include=["västerbotten", "vasterbotten"],
        )
        if contains_any(norm(offer.name), ("philadelphia", "färskost", "farskost", "cream cheese"))
    ]
    audit.expect_none_match(
        section="batch2 direct fixes",
        check="riven västerbottensost rejects västerbotten-flavored fresh cheese",
        ingredient="2 dl riven Västerbottensost",
        candidates=vasterbotten_fresh_cheese,
    )

    hot_smoked_salmon = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"fish"},
            include=["lax"],
        )
        if contains_any(norm(offer.name), ("varmrökt", "varmrokt", "varmr"))
        and not contains_any(norm(offer.name), (
            "glaze", "mexican", "regnbågslax", "regnbagslax", "hel",
        ))
    ]
    audit.expect_all_match(
        section="batch2 direct fixes",
        check="varmrökt laxfilé accepts hot-smoked salmon products",
        ingredient="350 g varmrökt laxfilé",
        candidates=hot_smoked_salmon,
    )

    raw_or_cold_salmon = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"fish"},
            include=["lax"],
        )
        if not contains_any(norm(offer.name), ("varmrökt", "varmrokt", "varmr"))
        and contains_any(norm(offer.name), ("laxfil", "kallrökt", "kallrokt", "kallr"))
    ]
    audit.expect_none_match(
        section="batch2 direct fixes",
        check="varmrökt laxfilé rejects raw and cold-smoked salmon products",
        ingredient="350 g varmrökt laxfilé",
        candidates=raw_or_cold_salmon,
    )

    audit.expect_none_match(
        section="batch2 direct fixes",
        check="plain laxfilé rejects hot-smoked salmon products",
        ingredient="300 g laxfilé",
        candidates=hot_smoked_salmon,
    )

    mixed_leaf_salads = [
        offer for offer in audit.offers
        if offer.category in {"fruit", "vegetables"}
        and (
            contains_any(norm(offer.name), ("blandsallad", "gourmetsallad"))
            or re.search(r"\bblandad\s+sallad\b", norm(offer.name)) is not None
        )
    ]
    audit.expect_all_match(
        section="batch2 direct fixes",
        check="salladsmix accepts mixed leaf salad products",
        ingredient="salladsmix",
        candidates=mixed_leaf_salads,
    )

    prepared_salads = [
        offer for offer in audit.offers
        if "sallad" in norm(offer.name)
        and offer.id not in {candidate.id for candidate in mixed_leaf_salads}
        and (
            offer.category not in {"fruit", "vegetables"}
            or contains_any(norm(offer.name), (
                "potatissallad", "räksallad", "raksallad", "kycklingsallad",
                "baguettesallad", "pizzasallad", "paprikasallad",
                "picklad", "salladskrydda", "salladsdressing",
            ))
        )
    ]
    audit.expect_none_match(
        section="batch2 direct fixes",
        check="salladsmix rejects prepared salad/carrier products",
        ingredient="salladsmix",
        candidates=prepared_salads,
    )

    chipotle_spices = [
        offer for offer in audit.offers
        if offer.category in {"pantry", "spices"}
        and "chipotle" in norm(offer.name)
        and not contains_any(norm(offer.name), (
            "sås", "sas", "sauce", "hot sauce", "bbq", "barbecue",
            "mayo", "majonnäs", "majonnas", "bearnaise", "glaze", "marinad",
        ))
    ]
    audit.expect_all_match(
        section="batch2 direct fixes",
        check="chipotlepasta eller pulver accepts dry chipotle seasoning",
        ingredient="1 tsk chipotlepasta eller pulver",
        candidates=chipotle_spices,
    )

    chipotle_carriers = [
        offer for offer in audit.offers
        if "chipotle" in norm(offer.name)
        and offer.id not in {candidate.id for candidate in chipotle_spices}
    ]
    audit.expect_none_match(
        section="batch2 direct fixes",
        check="chipotlepasta eller pulver rejects chipotle-flavored carriers",
        ingredient="1 tsk chipotlepasta eller pulver",
        candidates=chipotle_carriers,
    )

    pancetta_products = select_name_family(
        audit.offers,
        categories={"meat"},
        include=["pancetta"],
    )
    audit.expect_all_match(
        section="batch2 direct fixes",
        check="pancetta accepts pancetta products",
        ingredient="200 g Pancetta",
        candidates=pancetta_products,
    )

    pancetta_fallback_blocks = [
        offer for offer in audit.offers
        if "bacon" in norm(offer.name)
        or (offer.category != "meat" and "pancetta" in norm(offer.name))
    ]
    audit.expect_none_match(
        section="batch2 direct fixes",
        check="pancetta rejects bacon fallback and prepared pancetta carriers",
        ingredient="200 g Pancetta",
        candidates=pancetta_fallback_blocks,
    )


def run_batch3_direct_fix_policy(audit: MatcherAudit) -> None:
    chicken_steak_or_raw_fillet = [
        offer for offer in audit.offers
        if offer.category == "meat"
        and (
            "kycklingsteak" in norm(offer.name)
            or "kycklingfilé tunnskivad" in norm(offer.name)
            or "kycklingfile tunnskivad" in norm(offer.name)
        )
    ]
    audit.expect_all_match(
        section="batch3 direct fixes",
        check="kyckling steak accepts chicken steak and raw fillet fallback",
        ingredient="800 g Kyckling Steak",
        candidates=chicken_steak_or_raw_fillet,
    )

    cooked_or_deli_chicken = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"meat"},
            include=["kyckling", "höns", "hons"],
        )
        if contains_any(norm(offer.name), (
            "pastrami", "pastramikryddad",
            "grillkryddad skivad", "grillad skivad",
            "ätklar", "atklar", "färdiglagad", "fardiglagad",
            "pålägg", "palagg", "rökt skivad", "rokt skivad",
        ))
    ]
    audit.expect_none_match(
        section="batch3 direct fixes",
        check="kyckling steak rejects cooked/deli sliced chicken",
        ingredient="800 g Kyckling Steak",
        candidates=cooked_or_deli_chicken,
    )

    coffee_products = [
        offer for offer in audit.offers
        if contains_any(norm(offer.name), (
            "kaffe", "espresso", "coffee", "snabbkaffe",
            "kaffekaps", "kaffebön", "kaffebon", "bryggkaffe",
        ))
    ]
    audit.expect_none_match(
        section="batch3 direct fixes",
        check="brewed strong coffee ingredient has no purchasable coffee-product match",
        ingredient="1 dl starkt kaffe, gärna espresso",
        candidates=coffee_products,
    )

    savoiardi_biscuits = [
        offer for offer in audit.offers
        if contains_any(norm(offer.name), ("savoiardi", "savoiarde", "savoiardikex", "ladyfinger"))
    ]
    audit.expect_all_match(
        section="batch3 direct fixes",
        check="savoiardo kex accepts savoiardi/ladyfinger biscuits",
        ingredient="10-12 st Vicenzi Savoiardo kex",
        candidates=savoiardi_biscuits,
    )

    generic_crackers = [
        offer for offer in audit.offers
        if "kex" in norm(offer.name)
        and offer.id not in {candidate.id for candidate in savoiardi_biscuits}
    ]
    audit.expect_none_match(
        section="batch3 direct fixes",
        check="savoiardo kex rejects generic crackers and salty kex",
        ingredient="10-12 st Vicenzi Savoiardo kex",
        candidates=generic_crackers,
    )


def run_staple_form_policy(audit: MatcherAudit) -> None:
    fresh_potatoes = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"fruit"},
            include=["potatis"],
            exclude=["sötpotatis", "sotpotatis"],
        )
        if not is_ready_or_carrier(norm(offer.name))
    ]
    audit.expect_all_match(
        section="staple form policy",
        check="fast potatis accepts fresh normal potato variants",
        ingredient="1 kg Potatis Fast",
        candidates=fresh_potatoes,
    )

    preserved_whole_potatoes = select_name_family(
        audit.offers,
        include=["potatis hel"],
    )
    audit.expect_none_match(
        section="staple form policy",
        check="fast potatis rejects preserved whole potato packs",
        ingredient="1 kg Potatis Fast",
        candidates=preserved_whole_potatoes,
    )

    liquid_honey = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"pantry"},
            include=["honung"],
        )
        if "flytande" in norm(offer.name)
    ]
    audit.expect_all_match(
        section="staple form policy",
        check="flytande honung matches explicit liquid honey",
        ingredient="1 msk Honung Flytande",
        candidates=liquid_honey,
    )

    ordinary_non_liquid_honey = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"pantry"},
            include=["honung"],
            exclude=["flytande", "glazer", "nötmix", "notmix", "granola"],
        )
        if not is_ready_or_carrier(norm(offer.name))
    ]
    audit.expect_none_match(
        section="staple form policy",
        check="flytande honung rejects ordinary non-liquid honey",
        ingredient="1 msk Honung Flytande",
        candidates=ordinary_non_liquid_honey,
    )

    black_pepper = select_name_family(
        audit.offers,
        categories={"pantry", "spices"},
        include=["svartpeppar"],
    )
    audit.expect_none_match(
        section="staple form policy",
        check="nymalen svartpeppar is ignored as a manual no-match staple",
        ingredient="1 tsk nymalen svartpeppar",
        candidates=black_pepper,
    )

    beer_products = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"other"},
            include=["öl"],
            exclude=["ginger beer"],
        )
        if "öl" in audit.offer_keywords.get(id(offer), set())
    ]
    audit.expect_none_match(
        section="staple form policy",
        check="short beer keyword does not match inside vetemjöl",
        ingredient="1 msk vetemjöl",
        candidates=beer_products,
    )
    audit.expect_none_match(
        section="staple form policy",
        check="short beer keyword does not match inside mjölk",
        ingredient="2 dl mellanmjölk",
        candidates=beer_products,
    )
    audit.expect_all_match(
        section="staple form policy",
        check="standalone öl still matches beer products",
        ingredient="2 dl öl",
        candidates=beer_products,
    )


def run_batch3_user_decision_policy(audit: MatcherAudit) -> None:
    section = "batch3 user decisions"

    audit.expect_none_match(
        section=section,
        check="björnbärssaft does not fall back to berries, marmalade, or flavored water",
        ingredient="1 dl björnbärssaft",
        candidates=select_name_family(
            audit.offers,
            include=["björnbär", "björnbä", "bjornbar"],
        ),
    )

    flavored_sparkling_water = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"beverages"},
            include=["kolsyrat vatten"],
        )
        if contains_any(norm(offer.name), (
            "citron", "lime", "citrus", "äpple", "apple", "hallon",
            "björnbär", "björnbä", "mango", "päron", "paron",
        ))
    ]
    audit.expect_none_match(
        section=section,
        check="sodavatten rejects flavored sparkling water",
        ingredient="2 dl sodavatten",
        candidates=flavored_sparkling_water,
    )

    hard_tunnbrod = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"bread"},
            include=["tunnbröd"],
        )
        if contains_any(norm(offer.name), (
            "hårt", "fiber tunnbröd", "gene", "mjälloms", "mjalloms", "moilas",
        ))
    ]
    audit.expect_all_match(
        section=section,
        check="hårt tunnbröd accepts hard Gene-style tunnbröd",
        ingredient="4 st hårt tunnbröd",
        candidates=hard_tunnbrod,
    )
    soft_tunnbrod = select_name_family(
        audit.offers,
        categories={"bread"},
        include=["liba", "sarek", "tunnbröd 8p"],
    )
    audit.expect_none_match(
        section=section,
        check="hårt tunnbröd rejects soft/broad tunnbröd families",
        ingredient="4 st hårt tunnbröd",
        candidates=soft_tunnbrod,
    )

    flavored_instant_coffee = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"beverages"},
            include=["snabbkaffe"],
        )
        if contains_any(norm(offer.name), ("3in 1", "cappuccino", "cappucino", "choklad", "karamell", "vanilla"))
    ]
    audit.expect_none_match(
        section=section,
        check="snabbkaffepulver rejects flavored instant coffee drinks",
        ingredient="2 msk snabbkaffepulver",
        candidates=flavored_instant_coffee,
    )

    roastbeef_deli = [
        offer for offer in select_name_family(audit.offers, categories={"meat"}, include=["rostbiff"])
        if contains_any(norm(offer.name), ("deliskivor", "skivor", "skivad", "skeva"))
    ]
    roastbeef_raw = [
        offer for offer in select_name_family(audit.offers, categories={"meat"}, include=["rostbiff"])
        if offer not in roastbeef_deli and "lammrostbiff" not in norm(offer.name)
    ]
    audit.expect_all_match(
        section=section,
        check="rostbiff pålägg accepts sliced deli roast beef",
        ingredient="200 g Rostbiff Pålägg",
        candidates=roastbeef_deli,
    )
    audit.expect_none_match(
        section=section,
        check="rostbiff pålägg rejects raw roast beef cuts",
        ingredient="200 g Rostbiff Pålägg",
        candidates=roastbeef_raw,
    )
    audit.expect_none_match(
        section=section,
        check="raw rostbiff rejects sliced deli roast beef",
        ingredient="800 g rostbiff",
        candidates=roastbeef_deli,
    )

    audit.expect_matched_subset(
        section=section,
        check="explicit Violife smoked block stays on the requested vegan cheese variant",
        ingredient="200 g Violife Smokey Flavour, Block",
        forbidden=lambda offer: "violife" not in norm(offer.name) or "smoked" not in norm(offer.name),
        allowed=lambda offer: True,
    )
    audit.expect_matched_subset(
        section=section,
        check="explicit Violife mature cheddar stays on the requested vegan cheese variant",
        ingredient="200 g Violife Mature Cheddar",
        forbidden=lambda offer: "violife" not in norm(offer.name) or "mature" not in norm(offer.name) or "cheddar" not in norm(offer.name),
        allowed=lambda offer: True,
    )

    audit.expect_matched_subset(
        section=section,
        check="msk koriander is spice context, not fresh/frozen herb",
        ingredient="1 msk koriander",
        forbidden=lambda offer: contains_any(norm(offer.name), ("klass", "fryst", "finhackad", "kruka", "blad")),
        allowed=lambda offer: "koriander" in norm(offer.name),
    )
    audit.expect_matched_subset(
        section=section,
        check="fryst koriander stays on frozen/fresh herb form",
        ingredient="1 dl koriander, fryst",
        forbidden=lambda offer: "malen" in norm(offer.name) or "blad" in norm(offer.name),
        allowed=lambda offer: "koriander" in norm(offer.name),
    )

    audit.expect_matched_subset(
        section=section,
        check="huvudsallat does not fall back to generic salad mixes",
        ingredient="1 st Huvudsallat",
        forbidden=lambda offer: "huvudsallad" not in norm(offer.name),
        allowed=lambda offer: True,
    )

    audit.expect_none_match(
        section=section,
        check="potato burger buns rejects fries, soup, hot-dog buns, and patties",
        ingredient="4 st Potato Burger buns",
        candidates=select_name_family(
            audit.offers,
            include=["fries", "soup", "soppa", "korvbröd", "hamburgare"],
        ),
    )

    audit.expect_none_match(
        section=section,
        check="öl for cooking rejects ginger beer soda",
        ingredient="2 flaskor öl",
        candidates=select_name_family(audit.offers, include=["ginger beer"]),
    )


def run_recurring_root_cause_policy(audit: MatcherAudit) -> None:
    section = "recurring root-cause policies"

    deli_sliced_chicken = [
        offer for offer in select_name_family(
            audit.offers,
            categories={"meat"},
            include=["kyckling"],
        )
        if contains_any(norm(offer.name), ("tunna skivor", "deliskivor"))
    ]
    audit.expect_none_match(
        section=section,
        check="raw kycklingfilé rejects deli sliced chicken products",
        ingredient="600 g färsk kycklingfilé",
        candidates=deli_sliced_chicken,
    )

    raw_thin_sliced_chicken = [
        offer for offer in audit.offers
        if offer.category == "meat"
        and "kycklingfilé tunnskivad" in norm(offer.name)
    ]
    audit.expect_all_match(
        section=section,
        check="raw kycklingfilé still accepts raw tunnskivad fillet products",
        ingredient="600 g färsk kycklingfilé",
        candidates=raw_thin_sliced_chicken,
    )

    mozzarella_products = [
        offer for offer in audit.offers
        if offer.category == "dairy"
        and "mozzarella" in norm(offer.name)
        and not contains_any(norm(offer.name), (
            "gnocchi", "lasagnette", "pasta bowl", "penne",
            "pomodoro", "pompodoro", "tortelloni", "pizza", "paj",
        ))
    ]
    audit.expect_all_match(
        section=section,
        check="riven mozzarella accepts mozzarella product forms",
        ingredient="125 g riven mozzarella",
        candidates=mozzarella_products,
    )

    riven_mozzarella_products = [
        offer for offer in audit.offers
        if offer.category == "dairy"
        and "mozzarella" in norm(offer.name)
        and contains_any(norm(offer.name), ("riven", "grated"))
    ]
    audit.expect_all_match(
        section=section,
        check="generic mozzarella accepts grated mozzarella products",
        ingredient="125 g mozzarella",
        candidates=riven_mozzarella_products,
    )

    mozzarella_ready_carriers = [
        offer for offer in audit.offers
        if "mozzarella" in norm(offer.name)
        and offer.id not in {candidate.id for candidate in mozzarella_products}
    ]
    audit.expect_none_match(
        section=section,
        check="mozzarella rejects ready-meal and carrier products",
        ingredient="125 g mozzarella",
        candidates=mozzarella_ready_carriers,
    )

    fresh_lasagne_sheets = [
        offer for offer in audit.offers
        if "lasagneplattor" in norm(offer.name)
        and "färsk" in norm(offer.name)
    ]
    audit.expect_all_match(
        section=section,
        check="fresh lasagneplattor accepts fresh sheet products",
        ingredient="400 g färska lasagneplattor",
        candidates=fresh_lasagne_sheets,
    )

    dry_lasagne_sheets = [
        offer for offer in audit.offers
        if "lasagneplattor" in norm(offer.name)
        and "färsk" not in norm(offer.name)
    ]
    audit.expect_none_match(
        section=section,
        check="fresh lasagneplattor rejects dry shelf sheets",
        ingredient="400 g färska lasagneplattor",
        candidates=dry_lasagne_sheets,
    )


def print_summary(audit: MatcherAudit) -> int:
    print(f"offers={len(audit.offers)} checks={audit.checks} failures={len(audit.failures)}")
    by_section: dict[str, int] = {}
    for failure in audit.failures:
        by_section[failure.section] = by_section.get(failure.section, 0) + 1
    for section, count in sorted(by_section.items()):
        print(f"section.{section}.failures={count}")

    if audit.failures:
        print("\nFAILURES")
        for failure in audit.failures[:200]:
            offer = failure.offer
            offer_text = (
                f"{offer.category} | {offer.name} | {offer.brand} | {offer.weight_grams}g"
                if offer
                else "<no offer>"
            )
            print(
                f"- [{failure.section}] {failure.check}\n"
                f"  ingredient: {failure.ingredient}\n"
                f"  offer: {offer_text}\n"
                f"  detail: {failure.detail}"
            )
        if len(audit.failures) > 200:
            print(f"... truncated {len(audit.failures) - 200} more failures")
        return 1

    print("PASS")
    return 0


def main() -> int:
    offers = load_offers()
    audit = MatcherAudit(offers)
    run_fresh_frozen_produce(audit)
    run_chili(audit)
    run_micropopcorn(audit)
    run_plant_based_gurt(audit)
    run_flavor_carriers(audit)
    run_stock_fond_policy(audit)
    run_rice_policy(audit)
    run_exact_specific_policy(audit)
    run_meat_component_policy(audit)
    run_batch2_direct_fix_policy(audit)
    run_batch3_direct_fix_policy(audit)
    run_staple_form_policy(audit)
    run_batch3_user_decision_policy(audit)
    run_recurring_root_cause_policy(audit)
    return print_summary(audit)


if __name__ == "__main__":
    raise SystemExit(main())
