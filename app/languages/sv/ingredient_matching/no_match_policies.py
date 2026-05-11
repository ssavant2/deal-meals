"""Declarative no-match policies staged for matcher migration."""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
import re

from .term_registry.exports import NO_MATCH_POLICIES as _REGISTRY_NO_MATCH_POLICIES


NO_MATCH_POLICIES = _REGISTRY_NO_MATCH_POLICIES
NO_MATCH_POLICIES_BY_ID = {policy.id: policy for policy in NO_MATCH_POLICIES}

_POLICY_INGREDIENT_HINTS = {
    "policy_generic_oil": ("olja",),
    "policy_generic_sugar": ("socker",),
    "policy_black_pepper_staple": ("peppar",),
    "policy_riven_cheddarost_not_spread": ("cheddarost",),
    "policy_chocolate_coffee_beans_not_choco_cereal": ("kaffebonor",),
    "policy_raspberry_chocolate_not_raspberry_fruit": ("hallonsmak",),
    "policy_bjast_not_bakers_yeast": ("bjast", "bjäst"),
    "policy_plain_sotmandel_not_roasted_salted": ("sötmandel", "sotmandel"),
    "policy_kottfarssaser_not_table_sauces": ("köttfärssåser", "kottfarssaser"),
    "policy_light_rum_not_fish_roe": ("ljus rom", "cocktail"),
    "policy_fresh_ingefara_not_turmeric_or_misc": ("ingefära", "ingefara"),
    "policy_chili_fruit_not_crispy_chicken_spice_mix": ("chilifrukt",),
    "policy_tabasco_sriracha_not_pepper_sauce": ("sriracha",),
    "policy_fresh_oregano_not_dried_spice": ("oregano",),
    "policy_smoothie_fruit_not_ready_drinks": ("smoothie",),
    "policy_plant_milk_not_plant_cream": ("vegetabilisk",),
    "policy_oat_barista_not_lactose_dairy_milk": ("havrebaserad",),
    "policy_rapsolja_chips_not_olivolja_purpose": ("till chips", "rapsolja"),
    "policy_rosemary_stalk_not_dried_or_plain_stalk": ("rosmarinstj",),
    "policy_herb_marinated_chicken_not_other_protein": ("örtmarinerad", "ortmarinerad"),
    "policy_truffle_cheese_not_truffle_oil": ("tryffelsmak", "gorgonzola"),
    "policy_maizena_sauce_context_not_premade_sauces": ("maizenaredning",),
    "policy_dumplings_chicken_not_paprika_cheese": ("dumplings kyckling",),
    "policy_optional_egg_white_sorbet_context": ("äggvita", "aggvita"),
    "policy_kombuchasvamp_not_kombucha_drink": ("kombuchasvamp",),
    "policy_katrinplommonpure_not_fresh_plums_or_sushi": ("katrinplommon",),
    "policy_dried_peperoncino_not_topping_sauce": ("peperoncino",),
    "policy_fullkornsrismjol_not_rice": ("fullkornsrismj",),
    "policy_noodle_type_parenthetical_not_plain_rice": ("nudlar",),
    "policy_file_text_not_fil_milk": ("file",),
    "policy_oil_marinade_purpose_phrase": ("olja till marinad",),
    "policy_bostongurka_not_other_pickles": ("bostongurka",),
    "policy_filmjolk_naturell_not_flavored_fil": ("filmjölk", "filmjolk"),
    "policy_chocolate_pudding_not_other_puddings": ("chokladpudding",),
    "policy_syrade_gurkor_not_fresh_gurka": ("syrade gurkor",),
    "policy_proteinpudding_compound_not_other_protein_pudding": ("proteinpudding",),
    "policy_cooking_chorizo_not_cured_chorizo": ("chorizo",),
    "policy_chicken_fillet_not_turkey_breast": ("kyckling", "bröstfilé", "brostfile"),
    "policy_smoked_pork_not_plain_pork_cuts": ("rökt fläsk", "rokt flask"),
    "policy_kantarellpesto_not_plain_pesto": ("kantarellpesto",),
    "policy_extra_virgin_olive_oil_not_flavored_or_spray": ("jungfruolivolja", "virgin"),
    "policy_olive_oil_salmon_purpose_phrase": ("till laxen",),
    "policy_flytande_smor_not_solid_butter": ("flytande",),
    "policy_durumvetemjol_not_plain_vetemjol": ("durum",),
    "policy_sojamajonnas_not_soy_or_mayo_components": ("sojamajonn",),
    "policy_steam_buns_not_generic_bread": ("steam buns",),
    "policy_whole_chicken_not_cut_fillets": ("stor kyckling",),
    "policy_fresh_mushroom_not_preserved_or_dried": ("färsk svamp", "farsk svamp"),
    "policy_prep_biff_phrase_not_beef_product": ("delad i 4 biffar",),
    "policy_pastadeg_reference_not_dry_pasta": ("pastadeg",),
    "policy_vegan_pasta_not_eggpasta": ("vegansk pasta",),
    "policy_fresh_chili_not_crispy_chili_oil": ("chili",),
    "policy_flaskkott_not_soda_lask_substring": ("fläskkött", "flaskkott"),
    "policy_raw_flaskkott_not_prepared_souvlaki": ("fläskkött", "flaskkott"),
    "policy_salted_potato_chips_not_flavored": ("potatischips",),
    "policy_kumminstekt_not_cumin_spice": ("kumminstekt",),
    "policy_dillpicklad_not_dill_spice": ("dillpicklad",),
    "policy_oregano_not_vegan_cheese_carrier": ("oregano",),
    "policy_fresh_gurka_not_finhackad_preserved": ("gurka",),
    "policy_plain_milk_not_flavored_milk_drink": ("mellanmjölk", "mellanmjolk"),
    "policy_havssalt_not_carrier_flavor": ("havssalt",),
    "policy_grillkrydda_not_garlic_component": ("grillkrydda",),
    "policy_feferoni_not_ready_baguette": ("feferoni",),
    "policy_plain_plant_drinks_not_flavored": ("havremjölk", "havremjolk", "sojadryck", "växtdryck"),
    "policy_glasnudlar_not_pasta_vermicelli": ("glasnudlar", "vermicellinudlar"),
    "policy_risnudlar_not_flavored_instant": ("risnudlar",),
    "policy_aggnudlar_not_risnudlar": ("äggnudlar", "aggnudlar"),
    "policy_generic_nudlar_not_flavored_instant": ("nudlar",),
    "policy_snabbnudlar_non_buyable": ("snabbnudlar", "instantnudlar"),
    "policy_plant_based_burger_not_chicken_burger": ("blödande burgare", "blodande burgare"),
    "policy_vallmofro_not_crispbread_carrier": ("vallmofrö", "vallmofro"),
    "policy_vodka_not_salsa_carrier": ("vodka",),
    "policy_brewed_coffee_not_ready_drink": ("espresso", "kaffe"),
    "policy_kikartsspad_non_buyable_byproduct": ("kikärtsspad", "kikartsspad", "aquafaba"),
    "policy_root_veg_spaghetti_non_buyable": (
        "morotsspaghetti",
        "kålrotsspaghetti",
        "kalrotsspaghetti",
    ),
    "policy_pickled_peaches_not_dried_or_cashew_carriers": ("inlagda persikor",),
    "policy_mozzarella_loaf_note_not_bread_or_misc": ("mozzarellaost",),
    "policy_fresh_chilipeppar_not_ground_spice_or_onion": ("chilipeppar",),
    "policy_sojaglass_vanilla_not_dairy_or_mousse_carriers": ("sojaglass",),
    "policy_hot_chocolate_drink_not_chocolate_products": ("varm choklad",),
    "policy_philadelphia_sweet_chili_not_sauce_or_plain_cream_cheese": (
        "philadelphia",
        "sweet chili",
    ),
    "policy_white_kladdkakamix_not_bread": ("kladdkakamix",),
    "policy_explain_trace_placeholder_not_offer_terms": ("current explain trace says",),
    "policy_dishwasher_tablets_non_food": ("maskindiskmedel",),
    "policy_compound_candy_nut_or_peel_not_raw_components": (
        "nougatkräm",
        "nougatkram",
        "bittermandel",
        "syltade apelsinskal",
    ),
    "policy_fermented_black_beans_not_bakers_yeast": ("jästa svarta", "jasta svarta"),
    "policy_natural_cashews_not_papaya": ("cashewnötter", "cashewnotter"),
    "policy_pickled_beets_not_raw_or_diagnostic_terms": ("inlagda rödbetor",),
    "policy_fresh_jalapeno_or_glaze_chili_not_processed_chili": (
        "jalapeno",
        "chilifrukt",
        "glaze chili",
    ),
    "policy_counted_chili_not_ground_spice": ("chili",),
    "policy_vaniljglass_not_other_flavors_or_sparse_glass": ("vaniljglass",),
    "policy_placeholder_or_sojabonor_konserv_not_components": ("(", "sojabönor", "sojabonor"),
    "policy_pizza_spices_not_sparse_spice_carriers": ("pizza spices",),
    "policy_frozen_chopped_spinach_not_fresh_spinach": ("hackad fryst spenat",),
    "policy_cooked_drumstick_not_raw_or_sparse_terms": ("kycklingklubba",),
    "policy_generic_mushroom_pieces_not_preserved_champignon": ("svamp", "kantareller"),
    "policy_canned_cherry_tomatoes_not_fresh_or_sparse": (
        "konserverade",
        "körsbärstomat",
        "korsbarstomat",
    ),
    "policy_grillkorv_or_precooked_lentils_not_unrelated_components": (
        "grillkorvar",
        "röda linser",
        "roda linser",
    ),
    "policy_tomatpesto_not_green_pesto": ("tomatpesto",),
    "policy_bufala_mozzarella_not_vegan_mozzarella_flavour": ("mozzarella", "bufala"),
    "policy_sill_not_ansjoviskrydda_carrier": ("sill",),
    "policy_sushi_fish_not_generic_white_fish": ("fiskfil", "sushi", "tonfisk", "lax"),
    "policy_hushallsfars_not_chicken_mince": ("hushållsfärs", "hushallsfars"),
    "policy_plain_havregurt_not_fruit_flavored": ("havregurt",),
    "policy_kalkonbrostfile_not_thigh": ("kalkonbröst", "kalkonbrost"),
    "policy_mjukt_tunnbrod_not_hard_tunnbrod": ("tunnbröd", "tunnbrod"),
    "policy_low_fat_hard_cheese_not_high_fat": ("hårdost", "hardost"),
    "policy_storkornskaviar_not_tube_kaviar": ("storkornskaviar",),
    "policy_habanero_hot_sauce_not_fresh_chili": ("habanero", "tabasco"),
    "policy_rokextrakt_not_smoke_flavored_carriers": ("rökextrakt", "rokextrakt"),
    "policy_measured_spirit_rom_not_fish_roe": (" rom",),
    "policy_tryffelburrata_not_plain_burrata": ("tryffelburrata",),
    "policy_riven_veganost_not_spread": ("veganost",),
    "policy_morotssylt_not_other_jams": ("morotssylt",),
}


def _contains_token(text: str, token: str) -> bool:
    return re.search(rf"\b{re.escape(token)}\b", text) is not None


def _contains_any_hint(texts: Iterable[str], hints: Iterable[str]) -> bool:
    return any(hint in text for text in texts for hint in hints)


@lru_cache(maxsize=32768)
def _find_ingredient_policy_matches(
    normalized_ingredients: tuple[str, ...],
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    """Return policies whose ingredient side matches these normalized texts."""
    matches: list[tuple[int, tuple[int, ...]]] = []

    for policy_index, policy in enumerate(NO_MATCH_POLICIES):
        ingredient_hints = _POLICY_INGREDIENT_HINTS.get(policy.id)
        if ingredient_hints and not _contains_any_hint(normalized_ingredients, ingredient_hints):
            continue

        matched_ingredient_indices = []
        for index, ingredient_text in enumerate(normalized_ingredients):
            if any(_contains_token(ingredient_text, specific) for specific in policy.allowed_specifics):
                continue
            if any(re.search(pattern, ingredient_text) for pattern in policy.ingredient_patterns):
                matched_ingredient_indices.append(index)
        if matched_ingredient_indices:
            matches.append((policy_index, tuple(matched_ingredient_indices)))

    return tuple(matches)


def find_no_match_policy_hits(
    *,
    ingredient_texts: Iterable[str],
    offer_keywords: Iterable[str],
    offer_text: str = "",
) -> tuple[dict[str, object], ...]:
    """Return declarative no-match policies applicable to one offer/recipe pair."""

    normalized_ingredients = tuple(str(text or "").lower() for text in ingredient_texts)
    normalized_offer_keywords = frozenset(
        str(keyword or "").lower()
        for keyword in offer_keywords
        if keyword
    )
    normalized_offer_text = str(offer_text or "").lower()
    hits: list[dict[str, object]] = []

    for policy_index, matched_ingredient_indices in _find_ingredient_policy_matches(normalized_ingredients):
        policy = NO_MATCH_POLICIES[policy_index]
        blocked_keywords = sorted(
            keyword
            for keyword in policy.blocked_offer_keywords
            if keyword in normalized_offer_keywords or _contains_token(normalized_offer_text, keyword)
        )
        blocked_patterns = sorted(
            pattern
            for pattern in policy.blocked_offer_patterns
            if re.search(pattern, normalized_offer_text)
        )
        if not blocked_keywords and not blocked_patterns:
            continue

        hits.append({
            "id": policy.id,
            "canonical": policy.canonical,
            "policy_ref": policy.policy_ref,
            "matched_ingredient_indices": list(matched_ingredient_indices),
            "blocked_offer_keywords": blocked_keywords,
            "blocked_offer_patterns": blocked_patterns,
        })

    return tuple(hits)
