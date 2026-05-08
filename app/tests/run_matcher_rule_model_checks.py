#!/usr/bin/env python3
"""Checks for declarative matcher rule model constructors and seed registry."""

from __future__ import annotations

from pathlib import Path
import sys


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from languages.sv.ingredient_matching import build_offer_match_data  # noqa: E402
from languages.sv.ingredient_matching.no_match_policies import (  # noqa: E402
    NO_MATCH_POLICIES,
    NO_MATCH_POLICIES_BY_ID,
    find_no_match_policy_hits,
)
from languages.sv.ingredient_matching.match_bridges import (  # noqa: E402
    MATCH_BRIDGES,
    MATCH_BRIDGES_BY_ID,
    find_match_bridge_hits,
)
from languages.sv.ingredient_matching.rule_models import (  # noqa: E402
    BackendAllowance,
    BlockerRule,
    CanonicalEquivalence,
    MatchBridge,
    NoMatchPolicy,
    RouteExpansion,
)
from tests.run_matcher_layer_fixture_cases import (  # noqa: E402
    DEFAULT_FIXTURE_FILE,
    _load_fixture_payload,
    has_temporary_fixture_id,
    has_temporary_policy_ref,
)
from tests.run_matcher_rule_inventory_checks import (  # noqa: E402
    DEFAULT_INVENTORY_FILE,
    _entry_adapter_refs,
    load_inventory,
)


def check(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"OK {name}")


def check_raises(name: str, factory, expected_fragment: str) -> None:
    try:
        factory()
    except ValueError as exc:
        check(name, expected_fragment in str(exc))
        return
    raise AssertionError(f"{name}: expected ValueError")


def main() -> int:
    fixture_payloads = _load_fixture_payload(Path(DEFAULT_FIXTURE_FILE))
    fixture_ids = {str(payload["id"]) for payload in fixture_payloads}
    fixture_by_id = {str(payload["id"]): payload for payload in fixture_payloads}
    inventory_entries = load_inventory(Path(DEFAULT_INVENTORY_FILE))
    inventory_ids = {str(entry["id"]) for entry in inventory_entries}
    inventory_by_id = {str(entry["id"]): entry for entry in inventory_entries}

    blocker = BlockerRule(
        id="check_blocker",
        rule_schema_version=1,
        rule_version=1,
        side="offer",
        code="check:blocker",
        reason="check",
        policy_ref="sanity:rule_model",
        fixture_refs=frozenset({"plan_initial_generic_oil_negative"}),
    )
    allowance = BackendAllowance(
        id="check_allowance",
        rule_schema_version=1,
        rule_version=1,
        code="check:allowance",
        reason="check",
        policy_ref="sanity:rule_model",
        fixture_refs=frozenset({"plan_initial_pressad_ingefarsjuice_positive"}),
    )
    bridge = MatchBridge(
        id="check_bridge",
        rule_schema_version=1,
        rule_version=1,
        canonical="check",
        ingredient_patterns=(r"\bcheck\b",),
        offer_patterns=(r"\bcheck\b",),
        fixture_refs=frozenset({"plan_initial_jordgubbssaft_positive"}),
        aliases=frozenset({"check_alias"}),
        blockers=frozenset({blocker}),
        backend_allowances=frozenset({allowance}),
    )
    check("match bridge fixture refs coerced", bridge.fixture_refs == frozenset({"plan_initial_jordgubbssaft_positive"}))
    check("match bridge nested blocker", blocker in bridge.blockers)
    check("match bridge nested allowance", allowance in bridge.backend_allowances)

    expansion = RouteExpansion(
        id="check_expansion",
        rule_schema_version=1,
        rule_version=1,
        source="check",
        exposes=frozenset({"parent_check"}),
        side="offer",
        reason="check",
        fixture_refs=frozenset({"plan_initial_jordgubbssaft_positive"}),
    )
    check("route expansion exposes", expansion.exposes == frozenset({"parent_check"}))

    equivalence = CanonicalEquivalence(
        id="check_equivalence",
        rule_schema_version=1,
        rule_version=1,
        canonicals=frozenset({"check", "parent_check"}),
        scope="parity_only",
        reason="check",
        policy_ref="sanity:rule_model",
        fixture_refs=frozenset({"plan_initial_jordgubbssaft_positive"}),
    )
    check("canonical equivalence size", len(equivalence.canonicals) == 2)

    check_raises(
        "fixture refs required",
        lambda: NoMatchPolicy(
            id="invalid_no_fixture",
            rule_schema_version=1,
            rule_version=1,
            canonical="invalid",
            ingredient_patterns=(r"\binvalid\b",),
            blocked_offer_keywords=frozenset({"invalid"}),
            reason="invalid",
            policy_ref="sanity:rule_model",
            fixture_refs=frozenset(),
        ),
        "fixture_refs",
    )
    check_raises(
        "schema version rejected",
        lambda: RouteExpansion(
            id="invalid_schema",
            rule_schema_version=99,
            rule_version=1,
            source="invalid",
            exposes=frozenset({"invalid"}),
            side="offer",
            reason="invalid",
            fixture_refs=frozenset({"plan_initial_jordgubbssaft_positive"}),
        ),
        "rule_schema_version",
    )
    check_raises(
        "no-match blocker required",
        lambda: NoMatchPolicy(
            id="invalid_no_blocker",
            rule_schema_version=1,
            rule_version=1,
            canonical="invalid",
            ingredient_patterns=(r"\binvalid\b",),
            reason="invalid",
            policy_ref="sanity:rule_model",
            fixture_refs=frozenset({"plan_initial_generic_oil_negative"}),
        ),
        "blocked_offer_keywords",
    )

    check("no-match policy ids unique", len(NO_MATCH_POLICIES_BY_ID) == len(NO_MATCH_POLICIES))
    registered_policy_refs = {
        policy.policy_ref
        for policy in NO_MATCH_POLICIES
    }
    registered_policy_refs.update(
        blocker.policy_ref
        for bridge in MATCH_BRIDGES
        for blocker in bridge.blockers
    )
    registered_policy_refs.update(
        allowance.policy_ref
        for bridge in MATCH_BRIDGES
        for allowance in bridge.backend_allowances
    )
    check(
        "registered policy refs stable",
        not any(has_temporary_policy_ref(policy_ref) for policy_ref in registered_policy_refs),
    )
    registered_fixture_refs = set()
    for policy in NO_MATCH_POLICIES:
        registered_fixture_refs.update(policy.fixture_refs)
    for bridge in MATCH_BRIDGES:
        registered_fixture_refs.update(bridge.fixture_refs)
        for blocker in bridge.blockers:
            registered_fixture_refs.update(blocker.fixture_refs)
        for allowance in bridge.backend_allowances:
            registered_fixture_refs.update(allowance.fixture_refs)
    check(
        "registered fixture refs stable",
        not any(has_temporary_fixture_id(fixture_ref) for fixture_ref in registered_fixture_refs),
    )
    check("registered no-match policy count", len(NO_MATCH_POLICIES) == 98)
    expected_policy_ids = {
        "policy_aggnudlar_not_risnudlar",
        "policy_bjast_not_bakers_yeast",
        "policy_black_pepper_staple",
        "policy_bostongurka_not_other_pickles",
        "policy_brewed_coffee_not_ready_drink",
        "policy_chicken_fillet_not_turkey_breast",
        "policy_chili_fruit_not_crispy_chicken_spice_mix",
        "policy_chocolate_coffee_beans_not_choco_cereal",
        "policy_chocolate_pudding_not_other_puddings",
        "policy_compound_candy_nut_or_peel_not_raw_components",
        "policy_cooked_drumstick_not_raw_or_sparse_terms",
        "policy_cooking_chorizo_not_cured_chorizo",
        "policy_canned_cherry_tomatoes_not_fresh_or_sparse",
        "policy_counted_chili_not_ground_spice",
        "policy_dillpicklad_not_dill_spice",
        "policy_dishwasher_tablets_non_food",
        "policy_dried_peperoncino_not_topping_sauce",
        "policy_dumplings_chicken_not_paprika_cheese",
        "policy_durumvetemjol_not_plain_vetemjol",
        "policy_explain_trace_placeholder_not_offer_terms",
        "policy_extra_virgin_olive_oil_not_flavored_or_spray",
        "policy_feferoni_not_ready_baguette",
        "policy_fermented_black_beans_not_bakers_yeast",
        "policy_file_text_not_fil_milk",
        "policy_filmjolk_naturell_not_flavored_fil",
        "policy_flaskkott_not_soda_lask_substring",
        "policy_flytande_smor_not_solid_butter",
        "policy_fresh_chili_not_crispy_chili_oil",
        "policy_fresh_chilipeppar_not_ground_spice_or_onion",
        "policy_fresh_gurka_not_finhackad_preserved",
        "policy_fresh_ingefara_not_turmeric_or_misc",
        "policy_fresh_jalapeno_or_glaze_chili_not_processed_chili",
        "policy_fresh_mushroom_not_preserved_or_dried",
        "policy_fresh_oregano_not_dried_spice",
        "policy_frozen_chopped_spinach_not_fresh_spinach",
        "policy_fullkornsrismjol_not_rice",
        "policy_generic_oil",
        "policy_generic_sugar",
        "policy_generic_nudlar_not_flavored_instant",
        "policy_generic_mushroom_pieces_not_preserved_champignon",
        "policy_glasnudlar_not_pasta_vermicelli",
        "policy_grillkorv_or_precooked_lentils_not_unrelated_components",
        "policy_grillkrydda_not_garlic_component",
        "policy_havssalt_not_carrier_flavor",
        "policy_herb_marinated_chicken_not_other_protein",
        "policy_hot_chocolate_drink_not_chocolate_products",
        "policy_kikartsspad_non_buyable_byproduct",
        "policy_kantarellpesto_not_plain_pesto",
        "policy_katrinplommonpure_not_fresh_plums_or_sushi",
        "policy_kombuchasvamp_not_kombucha_drink",
        "policy_kottfarssaser_not_table_sauces",
        "policy_kumminstekt_not_cumin_spice",
        "policy_light_rum_not_fish_roe",
        "policy_maizena_sauce_context_not_premade_sauces",
        "policy_mozzarella_loaf_note_not_bread_or_misc",
        "policy_natural_cashews_not_papaya",
        "policy_noodle_type_parenthetical_not_plain_rice",
        "policy_oat_barista_not_lactose_dairy_milk",
        "policy_oil_marinade_purpose_phrase",
        "policy_olive_oil_salmon_purpose_phrase",
        "policy_optional_egg_white_sorbet_context",
        "policy_oregano_not_vegan_cheese_carrier",
        "policy_pastadeg_reference_not_dry_pasta",
        "policy_philadelphia_sweet_chili_not_sauce_or_plain_cream_cheese",
        "policy_pickled_beets_not_raw_or_diagnostic_terms",
        "policy_pickled_peaches_not_dried_or_cashew_carriers",
        "policy_plain_sotmandel_not_roasted_salted",
        "policy_plain_milk_not_flavored_milk_drink",
        "policy_plant_milk_not_plant_cream",
        "policy_plain_plant_drinks_not_flavored",
        "policy_plant_based_burger_not_chicken_burger",
        "policy_placeholder_or_sojabonor_konserv_not_components",
        "policy_pizza_spices_not_sparse_spice_carriers",
        "policy_prep_biff_phrase_not_beef_product",
        "policy_proteinpudding_compound_not_other_protein_pudding",
        "policy_rapsolja_chips_not_olivolja_purpose",
        "policy_raw_flaskkott_not_prepared_souvlaki",
        "policy_raspberry_chocolate_not_raspberry_fruit",
        "policy_riven_cheddarost_not_spread",
        "policy_risnudlar_not_flavored_instant",
        "policy_root_veg_spaghetti_non_buyable",
        "policy_rosemary_stalk_not_dried_or_plain_stalk",
        "policy_salted_potato_chips_not_flavored",
        "policy_snabbnudlar_non_buyable",
        "policy_smoked_pork_not_plain_pork_cuts",
        "policy_smoothie_fruit_not_ready_drinks",
        "policy_sojamajonnas_not_soy_or_mayo_components",
        "policy_sojaglass_vanilla_not_dairy_or_mousse_carriers",
        "policy_steam_buns_not_generic_bread",
        "policy_syrade_gurkor_not_fresh_gurka",
        "policy_tabasco_sriracha_not_pepper_sauce",
        "policy_truffle_cheese_not_truffle_oil",
        "policy_vallmofro_not_crispbread_carrier",
        "policy_vegan_pasta_not_eggpasta",
        "policy_vaniljglass_not_other_flavors_or_sparse_glass",
        "policy_vodka_not_salsa_carrier",
        "policy_whole_chicken_not_cut_fillets",
        "policy_white_kladdkakamix_not_bread",
    }
    check("registered no-match policy ids", set(NO_MATCH_POLICIES_BY_ID) == expected_policy_ids)

    generic_oil_hits = find_no_match_policy_hits(
        ingredient_texts=("1 msk olja till stekning",),
        offer_keywords=("rapsolja",),
        offer_text="rapsolja eldorado",
    )
    check(
        "no-match helper generic oil hit",
        [hit["id"] for hit in generic_oil_hits] == ["policy_generic_oil"],
    )

    specific_oil_hits = find_no_match_policy_hits(
        ingredient_texts=("1 msk rapsolja",),
        offer_keywords=("rapsolja",),
        offer_text="rapsolja eldorado",
    )
    check("no-match helper specific oil allowed", specific_oil_hits == ())

    expected_bridge_ids = {
        "bridge_alger_nori",
        "bridge_ananas_krossad_or_fryst",
        "bridge_ansjovis_fileer_grouping",
        "bridge_ancho_chili_exact",
        "bridge_apelsinjuice_concentrate",
        "bridge_apelsinlask_soda",
        "bridge_apelsinskal_fresh_fruit",
        "bridge_apple_cider_exact",
        "bridge_apple_cider_flavor_parent",
        "bridge_aromsmor_flavored_butter",
        "bridge_avrunnen_ananas_preserved",
        "bridge_baguette_typo_route_alias",
        "bridge_balsamvinager_rose",
        "bridge_bambuskott_bamboo_shoot",
        "bridge_barjuice_exact",
        "bridge_beyondburgare_exact",
        "bridge_bifftomat_exact",
        "bridge_bjornbarssaft_cordial",
        "bridge_bladkal_cabbage_alternatives",
        "bridge_blandade_bonor_bonmix",
        "bridge_blomkalshuvud_fresh",
        "bridge_bostongurka_relish_family",
        "bridge_boveteflingor_exact",
        "bridge_breoliv_spread_family",
        "bridge_brodskivor_formbrod",
        "bridge_burgarbrod_hamburgerbrod",
        "bridge_cantuccini_biscotti_exact",
        "bridge_champinjoner_exact",
        "bridge_charkbricka_platter",
        "bridge_chilimajo_exact",
        "bridge_chilipeppar_malen_spice",
        "bridge_chilisas_original_exact",
        "bridge_chipotlepasta_paste_exact",
        "bridge_chokladagg_exact",
        "bridge_chorizokorv_exact",
        "bridge_citron_juice_skal_whole_fruit",
        "bridge_citronmeliss_exact",
        "bridge_classico_pastasas_exact",
        "bridge_cornichons_cornichoner",
        "bridge_couscous_plain",
        "bridge_creme_fraiche_franska_orter",
        "bridge_crispy_chili_oil",
        "bridge_daimchoklad_exact",
        "bridge_dill_fresh_herb",
        "bridge_dillfro_plural",
        "bridge_dried_forest_mushroom_family",
        "bridge_dulce_de_leche_karamelliserad_mjolk",
        "bridge_durumvete_flour_family",
        "bridge_falafelmix_mix",
        "bridge_fankal_seed_spice_list",
        "bridge_farsk_bladspenat_family",
        "bridge_farsk_lok_salladslok_stalks",
        "bridge_farska_aprikoser_fresh",
        "bridge_farska_fikon_fresh",
        "bridge_farska_orter_fresh_or_frozen_basil",
        "bridge_farska_trattkantareller_exact",
        "bridge_farskkorv_salsiccia_family",
        "bridge_farskost_smaksatt_flavored",
        "bridge_feferoni_kebab_variant",
        "bridge_fettuccine_farsk_longpasta",
        "bridge_fish_roe_rom_products",
        "bridge_fiskgrytbitar_laxfile",
        "bridge_fitnessflingor_exact",
        "bridge_fladerdryck_elderflower",
        "bridge_folkol_beer",
        "bridge_forkoktmajskolv_prepared",
        "bridge_forkoktmajskolv_prepared_route",
        "bridge_fransk_senap_dijon",
        "bridge_fresh_chilipeppar_not_spice",
        "bridge_fresh_red_chilipeppar_produce",
        "bridge_frysta_orter_frozen_herbs",
        "bridge_frysta_lingon_raw",
        "bridge_gari_kalrotsgari_exact",
        "bridge_gemsallad_hjartsallad_family",
        "bridge_generic_fars_practical_scope",
        "bridge_generic_fron_seeds",
        "bridge_generic_frozen_fiskfile",
        "bridge_generic_kex_compound_products",
        "bridge_generic_sylt_berry_jams",
        "bridge_glasstrutar_vaffelstrutar",
        "bridge_glutenfri_cantucci_exact",
        "bridge_glutenfri_havregryn_exact",
        "bridge_gochujang_chilipasta_exact",
        "bridge_gradde_40pct",
        "bridge_grana_padano_exact",
        "bridge_grapefrukt_grape",
        "bridge_graslok_fresh",
        "bridge_graslok_i_kruka",
        "bridge_grenadine_exact",
        "bridge_gronsallad_salladsblad",
        "bridge_grotris_exact",
        "bridge_guajillo_chili_variant",
        "bridge_hackade_notter_generic",
        "bridge_haricoverts_typo",
        "bridge_harissa_exact_not_hummus",
        "bridge_hart_tunnbrod_form",
        "bridge_hasselnotsolja_exact",
        "bridge_havrebaserad_matlagning",
        "bridge_havredryck_naturell",
        "bridge_havregryn_plain",
        "bridge_hoisin_vegan_alternative_scope",
        "bridge_huvudsallat_head_lettuce",
        "bridge_ingefarsshot_juice",
        "bridge_inlagd_jalapeno_preserved",
        "bridge_jordgubbssaft_blandsaft",
        "bridge_kalhuvud_vitkal",
        "bridge_kalkon_palagg_deli_slice",
        "bridge_kanderade_citrusskal_exact",
        "bridge_kanelglass_exact",
        "bridge_kantareller_burk_i_vatten",
        "bridge_kantareller_i_vatten_reclass",
        "bridge_kardemumma_malen_spice",
        "bridge_kardemummakarnor_exact",
        "bridge_kardemummayoghurt_exact",
        "bridge_kesella_vaniljkvarg",
        "bridge_keso_cottage_cheese_naturell",
        "bridge_kikartor_ready_packaged_guard",
        "bridge_kinesisk_japansk_soja",
        "bridge_kalamata_oliver_parent",
        "bridge_knipplok_bunch",
        "bridge_kokkaffe_exact",
        "bridge_kokosflingor_riven_kokos",
        "bridge_kokosnotsdryck_kokosdryck",
        "bridge_kolasas_exact",
        "bridge_kolsyrat_mineralvatten_sodavatten",
        "bridge_koriander_fresh_herb",
        "bridge_koriander_fryst_herb",
        "bridge_koriander_malen_spice",
        "bridge_kormasas_sauce_products",
        "bridge_korsbar_frozen_fruit",
        "bridge_korsbarstomater_cocktail",
        "bridge_korvar_garna_lamm_family",
        "bridge_krossad_is_exact",
        "bridge_kycklinginnerfile_parent",
        "bridge_kycklingschnitzel_chicken",
        "bridge_kruksallad_krispsallat",
        "bridge_kryddpeppar_exact",
        "bridge_kvibille_adel_blue_cheese",
        "bridge_laktosfri_mjolk_scope",
        "bridge_lammkotlett_exact",
        "bridge_lammracks_exact",
        "bridge_lask_cola",
        "bridge_lax_laxfile_raw",
        "bridge_libabrod_tunnbrod",
        "bridge_limepepper_seasoning",
        "bridge_lingondryck_non_concentrate",
        "bridge_liquid_smoke_exact",
        "bridge_ljus_sirap_usage_tail",
        "bridge_maccaronetti_exact",
        "bridge_makrillfileer_plain",
        "bridge_mandariner_fruktkonserver",
        "bridge_mandelspan_spelling",
        "bridge_maranger_toppers",
        "bridge_marinerad_kronartskocka",
        "bridge_matbrodsjast_generic_route_sibling",
        "bridge_micropopcorn_mikropopcorn",
        "bridge_mixed_fresh_herbs_examples",
        "bridge_minikrustader_croustades",
        "bridge_mjukost_hot_jalapeno_exact",
        "bridge_moghrabiah_parlcouscous",
        "bridge_mork_chokladkaka_dark",
        "bridge_mousserande_vitt_vin_exact",
        "bridge_musslor_lake_frozen",
        "bridge_mynta_grouped_herb_leaf",
        "bridge_notcreme_spread",
        "bridge_ol_beer",
        "bridge_oliver_plain_not_stuffed",
        "bridge_olivolja_toscana_exact",
        "bridge_oreo_original_cookie",
        "bridge_oreokakor_cookie_pack",
        "bridge_paprika_exact_not_cheese",
        "bridge_paprika_later_variant",
        "bridge_paprikakrydda_pulver",
        "bridge_parmaskinka_prosciutto_di_parma",
        "bridge_parmesansas_exact_sauce",
        "bridge_pesto_gron",
        "bridge_philadelphia_farskost",
        "bridge_pickles_inlagdgurka",
        "bridge_pimenton_picante_exact",
        "bridge_pimientos_piquillo_exact",
        "bridge_plocksallat_sallat_products",
        "bridge_polenta_majsmjol",
        "bridge_polly_exact",
        "bridge_porter_beer",
        "bridge_potatischips_lantchips_family",
        "bridge_potatismos_instant",
        "bridge_potato_buns_hamburgerbrod",
        "bridge_prastost_abbreviated",
        "bridge_pressad_ingefarsjuice",
        "bridge_pulled_chicken_exact",
        "bridge_quornfars_vegofars",
        "bridge_revbensspjall_spareribs",
        "bridge_rimmat_flask_exact",
        "bridge_risotto_rice_family",
        "bridge_rod_spansk_peppar_fresh_chili",
        "bridge_rodbetor_fresh_sliced",
        "bridge_rodcurry_paste_exact",
        "bridge_rodspatta_spattafile",
        "bridge_rokt_paprikapulver",
        "bridge_romsas_exact",
        "bridge_rotfrukter_rotfruktsmix",
        "bridge_rostbiff_palagg_deli_slice",
        "bridge_rostbiff_raw_cut_exact",
        "bridge_ruccola_rucola",
        "bridge_salami_palagg_exact",
        "bridge_salamichips_exact",
        "bridge_salladsartor_sockerartor",
        "bridge_salladsblad_leafy_salad_products",
        "bridge_salta_kex_plain",
        "bridge_sambal_oelek_exact",
        "bridge_sashimi_lax_sushilax",
        "bridge_sataysas_cooking_sauce",
        "bridge_savoiardikex_specialty",
        "bridge_shisoblad_herb_alternatives",
        "bridge_sill_stromming_file_family",
        "bridge_skaldjursfond_hummerfond",
        "bridge_skinkschnitzel_raw_exact",
        "bridge_skorpor_plain",
        "bridge_sliderbrod_sliders",
        "bridge_smor_plain_common",
        "bridge_smorrapsolja_blend",
        "bridge_snabbkaffepulver_snabbkaffe",
        "bridge_sodavatten_plain_sparkling",
        "bridge_sojabonor_generic_processed_allowance",
        "bridge_soltorkadetomatcreme_exact",
        "bridge_sommargronsaker_apetit",
        "bridge_sotstro_lattstro",
        "bridge_spaced_saft_flavors",
        "bridge_spisbrod_knackebrod",
        "bridge_sriracha_exact",
        "bridge_standardmjolk_plain",
        "bridge_steklok_exact",
        "bridge_strosocker_exact",
        "bridge_styckbrod_bread_rolls",
        "bridge_surkal_exact",
        "bridge_svampfond_kantarellfond",
        "bridge_svart_bona_swedish_black_beans",
        "bridge_sweet_chili_sauce",
        "bridge_syltad_ingefara_exact",
        "bridge_tacokrydda_spice_mix",
        "bridge_tandoori_cooking_sauce",
        "bridge_tapenade_exact",
        "bridge_teriyakisas_exact",
        "bridge_tomkha_spice_mix",
        "bridge_tomat_fresh_or_canned_alternative",
        "bridge_tomatpassata_passerade_tomater",
        "bridge_tomatsas_pastasas_products",
        "bridge_tomatsas_pinsasas_alternative_line",
        "bridge_tomatsoppa_exact",
        "bridge_tonfisk_farsk",
        "bridge_tortellini_ricotta_spenat_exact",
        "bridge_tortillabrod_tortilla",
        "bridge_tortiglioni_exact",
        "bridge_tortilla_wrap_not_spanish",
        "bridge_tortillachips_ost_exact",
        "bridge_tzaybitar_vegobitar",
        "bridge_vaniljsas_alternative_line",
        "bridge_varmrokt_lax_exact",
        "bridge_vaxtbaserad_gurt_naturell",
        "bridge_vaxtbaserad_mjolkryck",
        "bridge_veg_hamburgare_vegoburgare",
        "bridge_veganost_plant_cheese_family",
        "bridge_vegetarisk_kebab_vegokebab",
        "bridge_vegobacon",
        "bridge_vetemjol_fullkorn_exact",
        "bridge_vetemjol_special_exact",
        "bridge_vinbarsgele_color_family",
        "bridge_vinbarsgele_variants",
        "bridge_violife_vegan_cheddar_variant",
        "bridge_vit_chokladkaka_white",
        "bridge_vit_fiskfile_white_fish",
        "bridge_vitlok_torkad_burk_crushed",
        "bridge_vitloksmarinad_spaced",
        "bridge_vitlokssmor_exact",
        "bridge_vitt_brod_formbrod",
        "bridge_vitt_vin_matlagningsvin",
        "bridge_wokgronsaker_brine",
        "bridge_wokgronsaker_forms",
        "bridge_woksas_teriyaki_exact",
        "bridge_worcestersas_worcestershire",
        "bridge_yoghurt_alt_naturell",
        "bridge_white_dark_chocolate_color_list",
    }
    check("seed match bridge count", len(MATCH_BRIDGES) == 282)
    check("seed match bridge ids", set(MATCH_BRIDGES_BY_ID) == expected_bridge_ids)
    dill_bridge_hits = find_match_bridge_hits(
        ingredient_texts=("1 tsk Dillfrö",),
        offer_keywords=("dillfrö",),
        offer_text="dillfrön burk kockens",
    )
    check(
        "match bridge helper dillfrö hit",
        [hit["id"] for hit in dill_bridge_hits] == ["bridge_dillfro_plural"],
    )

    negative_pattern_bridge = MatchBridge(
        id="check_negative_offer_pattern_bridge",
        rule_schema_version=1,
        rule_version=1,
        canonical="check",
        ingredient_patterns=(r"\bcheck\b",),
        offer_patterns=(r"\bcheck\b",),
        negative_offer_patterns=(r"\bblocked\b",),
        fixture_refs=frozenset({"plan_initial_jordgubbssaft_positive"}),
    )
    original_match_bridges = find_match_bridge_hits.__globals__["MATCH_BRIDGES"]
    find_match_bridge_hits.__globals__["MATCH_BRIDGES"] = (negative_pattern_bridge,)
    try:
        check(
            "match bridge helper negative offer pattern blocks",
            find_match_bridge_hits(
                ingredient_texts=("check",),
                offer_keywords=("check", "blocked"),
                offer_text="check blocked",
            ) == (),
        )
    finally:
        find_match_bridge_hits.__globals__["MATCH_BRIDGES"] = original_match_bridges

    all_policy_fixture_refs = {
        fixture_ref
        for policy in NO_MATCH_POLICIES
        for fixture_ref in policy.fixture_refs
    }
    check("no-match policy fixture refs exist", all_policy_fixture_refs <= fixture_ids)

    no_match_policy_fixture_misses: list[tuple[str, str, object]] = []
    no_match_policy_positive_hits: list[tuple[str, str]] = []
    for policy in NO_MATCH_POLICIES:
        for fixture_ref in policy.fixture_refs:
            payload = fixture_by_id[fixture_ref]
            offer = payload["offer"]
            offer_data = build_offer_match_data(
                offer["name"],
                offer.get("category", ""),
                brand=offer.get("brand", ""),
                weight_grams=offer.get("weight_grams"),
            )
            policy_hits = find_no_match_policy_hits(
                ingredient_texts=payload["ingredients"],
                offer_keywords=offer_data.keywords,
                offer_text=" ".join(
                    str(value)
                    for value in (offer.get("name"), offer.get("category"), offer.get("brand"))
                    if value
                ),
            )
            hit_ids = {hit["id"] for hit in policy_hits}
            if payload.get("expected") == 0 and policy.id not in hit_ids:
                no_match_policy_fixture_misses.append((policy.id, fixture_ref, sorted(hit_ids)))
            if payload.get("expected") == 1 and policy.id in hit_ids:
                no_match_policy_positive_hits.append((policy.id, fixture_ref))
    if no_match_policy_fixture_misses:
        print(f"no-match policy fixture misses: {no_match_policy_fixture_misses[:20]}")
    check("no-match policy negative fixture refs hit helper", not no_match_policy_fixture_misses)
    if no_match_policy_positive_hits:
        print(f"no-match policy positive fixture hits: {no_match_policy_positive_hits[:20]}")
    check("no-match policy positive fixture refs stay allowed", not no_match_policy_positive_hits)

    all_bridge_fixture_refs = {
        fixture_ref
        for bridge in MATCH_BRIDGES
        for fixture_ref in bridge.fixture_refs
    }
    check("match bridge fixture refs exist", all_bridge_fixture_refs <= fixture_ids)

    bridge_fixture_misses: list[tuple[str, str, object]] = []
    for bridge in MATCH_BRIDGES:
        for fixture_ref in bridge.fixture_refs:
            payload = fixture_by_id[fixture_ref]
            if payload.get("expected") != 1:
                bridge_fixture_misses.append((bridge.id, fixture_ref, "expected != 1"))
                continue

            offer = payload["offer"]
            offer_data = build_offer_match_data(
                offer["name"],
                offer.get("category", ""),
                brand=offer.get("brand", ""),
                weight_grams=offer.get("weight_grams"),
            )
            bridge_hits = find_match_bridge_hits(
                ingredient_texts=payload["ingredients"],
                offer_keywords=offer_data.keywords,
                offer_text=" ".join(
                    str(value)
                    for value in (offer.get("name"), offer.get("category"), offer.get("brand"))
                    if value
                ),
            )
            if bridge.id not in {hit["id"] for hit in bridge_hits}:
                bridge_fixture_misses.append((
                    bridge.id,
                    fixture_ref,
                    [hit["id"] for hit in bridge_hits],
                ))
    if bridge_fixture_misses:
        print(f"match bridge fixture misses: {bridge_fixture_misses[:20]}")
    check("match bridge fixture refs hit helper", not bridge_fixture_misses)

    bridge_negative_fixture_hits: list[tuple[str, str]] = []
    for bridge in MATCH_BRIDGES:
        legacy_fixture_refs = {
            fixture_ref
            for legacy_id in bridge.supersedes
            for fixture_ref in inventory_by_id[legacy_id].get("fixture_refs", ())
        }
        negative_fixture_refs = sorted(legacy_fixture_refs - bridge.fixture_refs)
        for fixture_ref in negative_fixture_refs:
            payload = fixture_by_id[fixture_ref]
            if payload.get("expected") != 0:
                continue

            offer = payload["offer"]
            offer_data = build_offer_match_data(
                offer["name"],
                offer.get("category", ""),
                brand=offer.get("brand", ""),
                weight_grams=offer.get("weight_grams"),
            )
            bridge_hits = find_match_bridge_hits(
                ingredient_texts=payload["ingredients"],
                offer_keywords=offer_data.keywords,
                offer_text=" ".join(
                    str(value)
                    for value in (offer.get("name"), offer.get("category"), offer.get("brand"))
                    if value
                ),
            )
            if bridge.id in {hit["id"] for hit in bridge_hits}:
                bridge_negative_fixture_hits.append((bridge.id, fixture_ref))
    if bridge_negative_fixture_hits:
        print(f"match bridge negative fixture hits: {bridge_negative_fixture_hits[:20]}")
    check("match bridge superseded negative fixtures stay blocked", not bridge_negative_fixture_hits)

    all_superseded_legacy_ids = {
        legacy_id
        for policy in NO_MATCH_POLICIES
        for legacy_id in policy.supersedes
    }
    check("no-match superseded legacy ids exist", all_superseded_legacy_ids <= inventory_ids)
    all_bridge_superseded_legacy_ids = {
        legacy_id
        for bridge in MATCH_BRIDGES
        for legacy_id in bridge.supersedes
    }
    check("match bridge superseded legacy ids exist", all_bridge_superseded_legacy_ids <= inventory_ids)

    valid_adapter_refs = {
        *(f"match_bridges:{bridge.id}" for bridge in MATCH_BRIDGES),
        *(f"no_match_policies:{policy.id}" for policy in NO_MATCH_POLICIES),
    }
    inventory_adapter_refs = {
        adapter_ref
        for entry in inventory_entries
        if entry.get("status") == "wrapped_adapter"
        for adapter_ref in _entry_adapter_refs(entry)
    }
    known_diagnostic_adapter_prefixes = (
        "backend_validation.events:",
        "matcher_layer_diagnostics:",
    )
    unknown_inventory_adapter_refs = sorted(
        adapter_ref
        for adapter_ref in inventory_adapter_refs
        if adapter_ref not in valid_adapter_refs
        and not adapter_ref.startswith(known_diagnostic_adapter_prefixes)
    )
    check("wrapped adapter refs point to registered or known diagnostic adapters", not unknown_inventory_adapter_refs)

    print("ALL MATCHER RULE MODEL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
