"""Best-effort ingredient exclusion profiles for Swedish matching preferences."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re
from typing import Iterable, Sequence

from ..category_utils import is_lactose_free
from ..normalization import fix_swedish_chars
from .extraction import extract_keywords_from_ingredient, extract_keywords_from_product
from .normalization import _apply_space_normalizations


_WORD_CHARS = "a-zåäöéèüA-ZÅÄÖÉÈÜ"


@dataclass(frozen=True)
class IngredientExclusionHit:
    profile: str
    evidence: str
    source: str


_PROFILE_LABELS = {
    "gluten": "gluten",
    "nötter": "nuts",
    "notter": "nuts",
    "nuts": "nuts",
    "skaldjur": "shellfish",
    "shellfish": "shellfish",
    "ägg": "egg",
    "agg": "egg",
    "egg": "egg",
    "soja": "soy",
    "soy": "soy",
    "laktos": "lactose",
    "lactose": "lactose",
}


_GLUTEN_KEYWORDS = frozenset({
    "vete", "vetemjöl", "mjöl", "mjölmix",
    "råg", "rag", "rågmjöl", "ragmjol",
    "korn", "dinkel", "spelt",
    "durum", "durumvete", "semolina", "mannagryn",
    "pasta", "bröd", "brod", "tortillabröd", "tortillabrod",
    "naan", "ströbröd", "strobrod", "panko",
    "bulgur", "couscous", "havre", "havregryn",
    "nudlar", "äggnudlar", "aggnudlar",
})

_GLUTEN_TEXT_CUES = frozenset({
    "gluten", "vete", "vetemjöl", "råg", "rågmjöl", "korn", "dinkel",
    "durum", "durumvete", "semolina", "mannagryn", "pasta", "bröd",
    "brod", "naan", "tortillabröd", "tortillabrod", "ströbröd",
    "strobrod", "panko", "bulgur", "couscous", "havre", "havregryn",
    "äggnudlar", "aggnudlar", "nudlar", "mjöl", "mjol", "mjölmix",
    "mjolmix",
})

_GLUTEN_EXEMPTION_CUES = frozenset({
    "glutenfri", "glutenfritt", "glutenfria", "gluten-free",
})

_GLUTEN_STRONG_CUES = frozenset({
    "gluten", "vete", "vetemjöl", "råg", "rågmjöl", "korn", "dinkel",
    "durum", "durumvete", "semolina", "mannagryn", "bulgur", "couscous",
})

_GLUTEN_FREE_CARRIER_CUES = frozenset({
    "rispasta", "risnudlar", "glasnudlar",
    "rismjöl", "rismjol", "majsmjöl", "majsmjol", "bovetemjöl",
    "bovetemjol", "mandelmjöl", "mandelmjol", "potatismjöl",
    "potatismjol", "majstortilla",
})


_NUT_KEYWORDS = frozenset({
    "nötter", "notter",
    "jordnötter", "jordnotter",
    "cashewnötter", "cashewnotter",
    "valnötter", "valnotter",
    "hasselnötter", "hasselnotter",
    "pistagenötter", "pistagenotter",
    "macadamianötter", "macadamianotter",
    "pekannötter", "pekannotter",
    "pinjenötter", "pinjenotter",
    "mandel", "sötmandel", "sotmandel",
    "nötmix", "notmix",
    "nötsmör", "notsmor", "jordnötssmör", "jordnotssmor",
})

_NUT_TEXT_CUES = _NUT_KEYWORDS


_SHELLFISH_KEYWORDS = frozenset({
    "skaldjur", "räkor", "rakor", "räka", "raka",
    "kräftor", "kraftor", "kräfta", "krafta", "kräftstjärtar",
    "kraftstjartar", "kräftstjärt", "kraftstjart",
    "hummer", "krabba", "krabbor",
    "musslor", "mussla", "blåmusslor", "blamusslor",
    "ostron", "pilgrimsmusslor", "pilgrimsmussla",
    "räkost", "rakost", "kräftost", "kraftost",
    "räksallad", "raksallad", "kräftsallad", "kraftsallad",
    "skagenröra", "skagenrora",
})

_SHELLFISH_TEXT_CUES = _SHELLFISH_KEYWORDS


_EGG_KEYWORDS = frozenset({
    "ägg", "agg", "äggula", "aggula", "äggvita", "aggvita",
    "äggnudlar", "aggnudlar",
})

_EGG_TEXT_CUES = _EGG_KEYWORDS


_SOY_KEYWORDS = frozenset({
    "soja", "sojasås", "sojasas", "sojabönor", "sojabonor",
    "tofu", "tempeh", "edamame",
})

_SOY_TEXT_CUES = _SOY_KEYWORDS


_LACTOSE_KEYWORDS = frozenset({
    "mjölk", "mjolk", "grädde", "gradde", "vispgrädde", "vispgradde",
    "matlagningsgrädde", "matlagningsgradde", "gräddfil", "graddfil",
    "yoghurt", "yogurt", "fil", "filmjölk", "filmjolk",
    "creme fraiche", "crème fraiche", "fraiche", "kvarg", "keso",
    "färskost", "farskost", "mjukost", "cream cheese",
    "mozzarella", "ricotta", "mascarpone", "cottage cheese",
    "feta", "halloumi", "glass", "gelato", "kefir",
})

_LACTOSE_TEXT_CUES = _LACTOSE_KEYWORDS

_LACTOSE_EXEMPTION_CUES = frozenset({"laktosfri", "laktosfritt", "laktosfria"})


def _normalize_text(text: str) -> str:
    return _apply_space_normalizations(fix_swedish_chars(text or "").lower())


def _word_re(cue: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![{_WORD_CHARS}]){re.escape(cue)}(?![{_WORD_CHARS}])", re.IGNORECASE)


@lru_cache(maxsize=4096)
def _cached_word_re(cue: str) -> re.Pattern[str]:
    return _word_re(cue)


def _has_word(text: str, cue: str) -> bool:
    return bool(_cached_word_re(cue).search(text))


def _has_any_word(text: str, cues: Iterable[str]) -> bool:
    return any(_has_word(text, cue) for cue in cues)


def _iter_preference_terms(values: Iterable[str] | None) -> Iterable[str]:
    if not values:
        return
    for value in values:
        if not isinstance(value, str):
            continue
        for part in value.split(","):
            term = part.strip()
            if term:
                yield term


def split_ingredient_exclusion_terms(values: Iterable[str] | None) -> tuple[set[str], list[str]]:
    profiles: set[str] = set()
    literal_terms: list[str] = []
    for term in _iter_preference_terms(values):
        normalized = _normalize_text(term)
        profile = _PROFILE_LABELS.get(normalized)
        if profile:
            profiles.add(profile)
        else:
            literal_terms.append(term.strip().lower())
    return profiles, literal_terms


def selected_ingredient_exclusion_profiles(preferences: dict | None) -> set[str]:
    if not preferences:
        return set()
    profiles, _literal_terms = split_ingredient_exclusion_terms(preferences.get("exclude_keywords", []))
    return profiles


def literal_ingredient_exclusion_terms(preferences: dict | None) -> list[str]:
    if not preferences:
        return []
    _profiles, literal_terms = split_ingredient_exclusion_terms(preferences.get("exclude_keywords", []))
    return literal_terms


def _hit(profile: str, evidence: str, source: str) -> IngredientExclusionHit:
    return IngredientExclusionHit(profile=profile, evidence=evidence, source=source)


def _keyword_hit(profile: str, keywords: set[str], wanted: frozenset[str]) -> IngredientExclusionHit | None:
    matched = sorted(keywords & wanted)
    if not matched:
        return None
    return _hit(profile, ",".join(matched), "keyword")


def _text_hit(profile: str, text: str, cues: frozenset[str]) -> IngredientExclusionHit | None:
    for cue in sorted(cues, key=len, reverse=True):
        if _has_word(text, cue):
            return _hit(profile, cue, "text")
    return None


def _gluten_exempt(text: str, keywords: set[str]) -> bool:
    if _has_any_word(text, _GLUTEN_EXEMPTION_CUES):
        return True
    if keywords & _GLUTEN_FREE_CARRIER_CUES or _has_any_word(text, _GLUTEN_FREE_CARRIER_CUES):
        return not (keywords & _GLUTEN_STRONG_CUES or _has_any_word(text, _GLUTEN_STRONG_CUES))
    return False


def _lactose_exempt(text: str) -> bool:
    return _has_any_word(text, _LACTOSE_EXEMPTION_CUES)


def ingredient_exclusion_hits_for_offer(
    offer_name: str,
    *,
    category: str = "",
    brand: str = "",
) -> list[IngredientExclusionHit]:
    text = _normalize_text(offer_name)
    # Store categories are intentionally ignored here. They are inconsistent
    # across stores and only suitable for broad UI/category filters, not
    # ingredient exclusion rules.
    _ = category
    keywords = set(extract_keywords_from_product(offer_name or "", "", brand=brand or ""))
    hits: list[IngredientExclusionHit] = []

    if not _gluten_exempt(text, keywords):
        hit = _keyword_hit("gluten", keywords, _GLUTEN_KEYWORDS) or _text_hit("gluten", text, _GLUTEN_TEXT_CUES)
        if hit:
            hits.append(hit)

    hit = _keyword_hit("nuts", keywords, _NUT_KEYWORDS) or _text_hit("nuts", text, _NUT_TEXT_CUES)
    if hit:
        hits.append(hit)

    hit = (
        _keyword_hit("shellfish", keywords, _SHELLFISH_KEYWORDS)
        or _text_hit("shellfish", text, _SHELLFISH_TEXT_CUES)
    )
    if hit:
        hits.append(hit)

    hit = _keyword_hit("egg", keywords, _EGG_KEYWORDS) or _text_hit("egg", text, _EGG_TEXT_CUES)
    if hit:
        hits.append(hit)

    hit = _keyword_hit("soy", keywords, _SOY_KEYWORDS) or _text_hit("soy", text, _SOY_TEXT_CUES)
    if hit:
        hits.append(hit)

    lactose_hit = None
    if not is_lactose_free(offer_name) and not _lactose_exempt(text):
        lactose_hit = (
            _keyword_hit("lactose", keywords, _LACTOSE_KEYWORDS)
            or _text_hit("lactose", text, _LACTOSE_TEXT_CUES)
        )
    if lactose_hit:
        hits.append(lactose_hit)

    return hits


def ingredient_exclusion_hits_for_ingredient_text(ingredient_text: str) -> list[IngredientExclusionHit]:
    text = _normalize_text(ingredient_text)
    keywords = set(extract_keywords_from_ingredient(ingredient_text or ""))
    hits: list[IngredientExclusionHit] = []

    if not _gluten_exempt(text, keywords):
        hit = _keyword_hit("gluten", keywords, _GLUTEN_KEYWORDS) or _text_hit("gluten", text, _GLUTEN_TEXT_CUES)
        if hit:
            hits.append(hit)

    hit = _keyword_hit("nuts", keywords, _NUT_KEYWORDS) or _text_hit("nuts", text, _NUT_TEXT_CUES)
    if hit:
        hits.append(hit)

    hit = (
        _keyword_hit("shellfish", keywords, _SHELLFISH_KEYWORDS)
        or _text_hit("shellfish", text, _SHELLFISH_TEXT_CUES)
    )
    if hit:
        hits.append(hit)

    hit = _keyword_hit("egg", keywords, _EGG_KEYWORDS) or _text_hit("egg", text, _EGG_TEXT_CUES)
    if hit:
        hits.append(hit)

    hit = _keyword_hit("soy", keywords, _SOY_KEYWORDS) or _text_hit("soy", text, _SOY_TEXT_CUES)
    if hit:
        hits.append(hit)

    if not _lactose_exempt(text):
        hit = _keyword_hit("lactose", keywords, _LACTOSE_KEYWORDS) or _text_hit("lactose", text, _LACTOSE_TEXT_CUES)
        if hit:
            hits.append(hit)

    return hits


def compile_recipe_ingredient_exclusion_flags(ingredients: Sequence[str] | None) -> list[str]:
    flags: set[str] = set()
    for ingredient in ingredients or ():
        for hit in ingredient_exclusion_hits_for_ingredient_text(str(ingredient)):
            flags.add(hit.profile)
    return sorted(flags)


def profiles_hit_by_offer(
    offer_name: str,
    *,
    category: str = "",
    brand: str = "",
) -> set[str]:
    return {
        hit.profile
        for hit in ingredient_exclusion_hits_for_offer(offer_name, category=category, brand=brand)
    }


def selected_profiles_exclude_offer(
    selected_profiles: set[str],
    offer_name: str,
    *,
    category: str = "",
    brand: str = "",
) -> IngredientExclusionHit | None:
    if not selected_profiles:
        return None
    for hit in ingredient_exclusion_hits_for_offer(offer_name, category=category, brand=brand):
        if hit.profile in selected_profiles:
            return hit
    return None


def selected_profiles_exclude_recipe_ingredients(
    selected_profiles: set[str],
    ingredients: Sequence[str] | None,
) -> bool:
    if not selected_profiles:
        return False
    return bool(selected_profiles & set(compile_recipe_ingredient_exclusion_flags(ingredients)))


def selected_profiles_exclude_compiled_recipe(
    selected_profiles: set[str],
    compiled_data: dict | None,
    *,
    fallback_ingredients: Sequence[str] | None = None,
) -> bool:
    if not selected_profiles:
        return False
    flags = set()
    if isinstance(compiled_data, dict):
        raw_flags = compiled_data.get("ingredient_exclusion_flags", [])
        if isinstance(raw_flags, list):
            flags.update(str(flag) for flag in raw_flags)
    if not flags and fallback_ingredients is not None:
        flags.update(compile_recipe_ingredient_exclusion_flags(fallback_ingredients))
    return bool(selected_profiles & flags)
