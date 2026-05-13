#!/usr/bin/env python3
"""Read-only diagnostics for one Swedish matcher recipe/offer case."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import text


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, "/app" if os.path.exists("/app") else str(APP_DIR))

from languages.sv.ingredient_matching.compiled_offers import normalize_compiled_offer_payload  # noqa: E402
from languages.sv.ingredient_matching.compiled_recipes import (  # noqa: E402
    prepare_recipe_match_runtime_data,
    serialize_prepared_recipe_match_runtime_data,
)
from languages.sv.ingredient_matching.ingredient_routing import (  # noqa: E402
    build_recipe_ingredient_term_map,
)
from languages.sv.ingredient_matching.match_bridges import find_match_bridge_hits  # noqa: E402
from languages.sv.ingredient_matching.matching import precompute_offer_data  # noqa: E402
from languages.sv.ingredient_matching.no_match_policies import find_no_match_policy_hits  # noqa: E402
from languages.sv.ingredient_matching.offer_identity import build_offer_identity_key  # noqa: E402
from languages.sv.ingredient_matching.parent_maps import PARENT_MATCH_ONLY  # noqa: E402
from languages.sv.ingredient_matching.synonyms import INGREDIENT_PARENTS  # noqa: E402
from languages.sv.ingredient_matching.term_indexes import build_offer_candidate_terms  # noqa: E402
from languages.sv.ingredient_matching.versioning import (  # noqa: E402
    MATCHER_VERSION,
    OFFER_COMPILER_VERSION,
    RECIPE_COMPILER_VERSION,
)
from languages.sv.recipe_matcher_backend import (  # noqa: E402
    build_keyword_patterns,
    collect_offer_match_candidates,
    get_classification_keywords,
    has_keyword_match,
    keyword_match_fast,
    match_recipe_to_offers,
    prepare_offer_match_candidate,
    select_offer_match_candidate,
    validate_offer_match_candidate,
)
from models import FoundRecipe, Offer  # noqa: E402


DEFAULT_CASE_ID = "inline_case"
_DECLARED_DIAGNOSTIC_CANONICAL_PARENTS = {
    # Typed expansion in the parity plan: förkoktmajskolv may route through
    # majskolv, but the precision canonical still wins for materialization.
    "förkoktmajskolv": "majskolv",
    # Folköl emits the broad beer parent for generic beer recipes while keeping
    # folköl as the precision canonical for explicit low-alcohol beer wording.
    "folköl": "öl",
    # Dill-pickled cucumber products pair the precision preparation with the
    # cucumber carrier; this is an intentional family, not competing canonicals.
    "dillpicklad": "gurka",
    # Route-only parents that align compiled routing with fullscan substring
    # family matches without broadening offer precompute reverse keywords.
    "kalamataoliver": "oliver",
    "svartvinbärsgele": "vinbärsgele",
    "svartvinbarsgele": "vinbarsgele",
    "rödvinbärsgele": "vinbärsgele",
    "rodvinbarsgele": "vinbarsgele",
    # Exact subtype/product examples that intentionally carry both precision and
    # broad family route terms.
    "svartabönor": "bönor",
    "tomkha": "kryddmix",
    "bostongurka": "gurka",
    "ancho": "chili",
    "helbit": "tempeh",
    "matbrödsjäst": "jäst",
    "matbrodsjast": "jäst",
}
_DECLARED_DIAGNOSTIC_CANONICAL_GROUPS = (
    # Variant wording on the same carrier should not count as two competing
    # ingredients when the product and recipe name the same concrete variant.
    frozenset({"grillkrydda", "vitlök"}),
    frozenset({"tikka", "masala", "kryddmix"}),
    frozenset({"garam", "masala", "kryddmix"}),
    frozenset({"tandoori", "kryddmix"}),
    frozenset({"taco", "kryddmix"}),
    frozenset({"spice", "spices", "kryddmix"}),
    frozenset({"durumvete", "durumvetemjöl"}),
    frozenset({"gochujang", "chilipasta"}),
    frozenset({"rödspätta", "rödspättafilé"}),
    frozenset({"rucola", "ruccola"}),
    frozenset({"grädde", "havre", "havregrädde", "matlagningsbas"}),
    frozenset({"körsbärstomat", "körsbärstomater", "småtomat"}),
    frozenset({"pimenton", "pimentón", "picante"}),
    frozenset({"tortellini", "ricotta/spenat"}),
    frozenset({"kardemumma", "malen", "nymald"}),
    frozenset({"mjukost", "jalapeno", "jalapeño"}),
    frozenset({"teriyaki", "teriyakisås", "sojasås"}),
    frozenset({"pimiento", "pimientos", "piquillo", "paprika"}),
    frozenset({"kvibille", "ädel", "ädelost"}),
    frozenset({"färskkorv", "salsiccia", "korv"}),
    frozenset({
        "färs", "fars",
        "köttfärs", "kottfars",
        "hushållsfärs", "hushallsfars",
        "nötfärs", "notfars",
        "blandfärs", "blandfars",
        "kalvfärs", "kalvfars",
        "lammfärs", "lammfars",
        "högrevsfärs", "hogrevsfars",
        "kycklingfärs", "kycklingfars",
        "kalkonfärs", "kalkonfars",
        "hönsfärs", "honsfars",
        "vegofärs", "vegofars",
        "sojafärs", "sojafars",
        "quornfärs", "quornfars",
        "baljväxtfärs", "baljvaxtfars",
    }),
    frozenset({"korv", "korvar", "lamm", "lammkött", "lammkorv"}),
    frozenset({
        "sillfilé", "sillfile",
        "sillfiléer", "sillfileer",
        "strömmingsfilé", "strommingsfile",
        "strömmingsfiléer", "strommingsfileer",
        "strömmingsfileer",
    }),
    frozenset({"salami", "pålägg"}),
    frozenset({"rostbiff", "pålägg"}),
    frozenset({"kalkon", "pålägg"}),
    frozenset({"aprikos", "aprikoser"}),
    frozenset({"champinjon", "champinjoner", "skogschampinjoner"}),
    frozenset({"kantareller", "trattkantarell", "trattkantareller"}),
    frozenset({"chili", "fläskkarré", "karré"}),
    frozenset({"cheddar", "mature", "violife"}),
    frozenset({"fraiche", "franskaörter"}),
)


@dataclass(frozen=True)
class DiagnosticCase:
    case_id: str
    recipe_name: str
    ingredients: tuple[str, ...]
    offer_name: str
    offer_category: str
    offer_brand: str = ""
    expected: int | None = None


class DiagnosticMatcher:
    """Small classifier facade expected by match_recipe_to_offers()."""

    def __init__(self) -> None:
        classification_keywords = get_classification_keywords()
        self._meat_patterns_compiled = build_keyword_patterns(classification_keywords["meat"])
        self._fish_patterns_compiled = build_keyword_patterns(classification_keywords["fish"])

    def _keyword_match_fast(self, value: str, patterns: dict[str, Any]) -> list[str]:
        return keyword_match_fast(value, patterns)

    def _has_keyword_match(self, value: str, patterns: dict[str, Any]) -> bool:
        return has_keyword_match(value, patterns)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (set, frozenset, tuple)):
        return [_json_safe(item) for item in sorted(value, key=lambda item: json.dumps(_json_safe(item), ensure_ascii=False, sort_keys=True))]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _build_recipe(case: DiagnosticCase) -> FoundRecipe:
    recipe = FoundRecipe(
        source_name="matcher_layer_diagnostics",
        name=case.recipe_name,
        url=f"matcher-layer-diagnostics://recipe/{case.case_id}",
        ingredients=list(case.ingredients),
        excluded=False,
    )
    return recipe


def _build_offer(case: DiagnosticCase) -> Offer:
    offer = Offer(
        name=case.offer_name,
        category=case.offer_category,
        brand=case.offer_brand,
        price=Decimal("10.00"),
        original_price=Decimal("20.00"),
        savings=Decimal("10.00"),
        unit="st",
        product_url=f"matcher-layer-diagnostics://offer/{case.case_id}",
        is_multi_buy=False,
    )
    return offer


def _add_term_source(
    target: dict[str, dict[str, Any]],
    term: str,
    source: str,
    *,
    ingredient_index: int | None = None,
    term_type: str | None = None,
) -> None:
    if not term:
        return
    entry = target.setdefault(str(term), {
        "term": str(term),
        "sources": set(),
        "ingredient_indices": set(),
        "term_types": set(),
    })
    entry["sources"].add(source)
    if ingredient_index is not None:
        entry["ingredient_indices"].add(int(ingredient_index))
    if term_type:
        entry["term_types"].add(str(term_type))


def _term_parent(term: str) -> str | None:
    return (
        INGREDIENT_PARENTS.get(term)
        or PARENT_MATCH_ONLY.get(term)
        or _DECLARED_DIAGNOSTIC_CANONICAL_PARENTS.get(term)
    )


def _terms_have_declared_parent_relation(term_a: str, term_b: str) -> bool:
    return _term_parent(term_a) == term_b or _term_parent(term_b) == term_a


def _terms_are_declared_family(terms: set[str]) -> bool:
    if len(terms) <= 1:
        return True
    if any(terms <= group for group in _DECLARED_DIAGNOSTIC_CANONICAL_GROUPS):
        return True
    for term_a in terms:
        for term_b in terms:
            if term_a == term_b:
                continue
            if not _terms_have_declared_parent_relation(term_a, term_b):
                return False
    return True


def _is_allowed_duplicate_source(entry: dict[str, Any]) -> bool:
    sources = set(entry["sources"])
    term_types = set(entry["term_types"])
    if sources <= {"offer.keyword", "offer.route.keyword", "offer.route.parent_keyword"}:
        return term_types <= {"keyword", "parent_keyword"}
    if sources <= {"recipe.extracted_keyword", "recipe.parent_keyword", "recipe.route_term"}:
        return True
    return len(sources) <= 1


def _summarize_term_sources(term_sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "term": term,
            "sources": sorted(entry["sources"]),
            "ingredient_indices": sorted(entry["ingredient_indices"]),
            "term_types": sorted(entry["term_types"]),
        }
        for term, entry in sorted(term_sources.items())
    ]


def _build_signal_provenance(
    *,
    prepared_recipe: dict[str, Any],
    ingredient_match_data_per_ing: list[Any],
    recipe_term_map: dict[str, set[int]],
    offer_precomputed: dict[str, Any],
    offer_route_terms_typed: set[tuple[str, str]],
    paired_route_terms: set[str],
    fullscan_candidates: list[tuple[int, str]],
    materialized_matches: list[dict[str, Any]],
) -> dict[str, Any]:
    recipe_terms: dict[str, dict[str, Any]] = {}
    offer_terms: dict[str, dict[str, Any]] = {}

    for index, item in enumerate(ingredient_match_data_per_ing):
        for keyword in getattr(item, "extracted_keywords", ()):
            keyword_value = str(keyword)
            _add_term_source(
                recipe_terms,
                keyword_value,
                "recipe.extracted_keyword",
                ingredient_index=index,
            )
            parent = _term_parent(keyword_value)
            if parent:
                _add_term_source(
                    recipe_terms,
                    parent,
                    "recipe.parent_keyword",
                    ingredient_index=index,
                )

    for term, indices in recipe_term_map.items():
        for index in indices:
            _add_term_source(recipe_terms, term, "recipe.route_term", ingredient_index=index)

    for keyword in offer_precomputed.get("keywords", ()):
        _add_term_source(offer_terms, str(keyword), "offer.keyword")

    offer_term_types_by_term: dict[str, set[str]] = {}
    for term, term_type in offer_route_terms_typed:
        offer_term_types_by_term.setdefault(term, set()).add(term_type)
        _add_term_source(
            offer_terms,
            term,
            f"offer.route.{term_type}",
            term_type=term_type,
        )

    paired_details = []
    for term in sorted(paired_route_terms):
        recipe_entry = recipe_terms.get(term, {"sources": set(), "ingredient_indices": set()})
        offer_entry = offer_terms.get(term, {"sources": set(), "term_types": set()})
        paired_details.append({
            "term": term,
            "recipe_sources": sorted(recipe_entry["sources"]),
            "offer_sources": sorted(offer_entry["sources"]),
            "ingredient_indices": sorted(recipe_entry.get("ingredient_indices", set())),
            "offer_term_types": sorted(offer_entry.get("term_types", set())),
        })

    duplicate_terms = []
    for side, term_sources in (("recipe", recipe_terms), ("offer", offer_terms)):
        for term, entry in sorted(term_sources.items()):
            if len(entry["sources"]) > 1 and not _is_allowed_duplicate_source(entry):
                duplicate_terms.append({
                    "side": side,
                    "term": term,
                    "sources": sorted(entry["sources"]),
                })

    route_canonical_terms = {
        term
        for term in paired_route_terms
        if "name_word" not in offer_term_types_by_term.get(term, set())
    }
    matched_canonicals = {
        str(keyword)
        for _index, keyword in fullscan_candidates
        if keyword
    }
    matched_canonicals.update(
        str(item.get("matched_keyword"))
        for item in materialized_matches
        if item.get("matched_keyword")
    )
    canonical_candidates = route_canonical_terms | matched_canonicals
    ambiguous_terms = []
    if len(canonical_candidates) > 1 and not _terms_are_declared_family(canonical_candidates):
        ambiguous_terms.append({
            "terms": sorted(canonical_candidates),
            "matched_canonicals": sorted(matched_canonicals),
            "paired_route_terms": sorted(route_canonical_terms),
        })

    return {
        "recipe_terms": _summarize_term_sources(recipe_terms),
        "offer_terms": _summarize_term_sources(offer_terms),
        "paired_terms": paired_details,
        "duplicate_signal_source": {
            "count": len(duplicate_terms),
            "terms": duplicate_terms,
        },
        "ambiguous_canonical": {
            "count": len(ambiguous_terms),
            "groups": ambiguous_terms,
        },
    }


def _group_version_counts(rows: list[Any], *fields: str) -> list[dict[str, Any]]:
    grouped = []
    for row in rows:
        mapping = row._mapping
        grouped.append({
            **{field: mapping.get(field) for field in fields},
            "count": int(mapping.get("count") or 0),
        })
    return grouped


def _freshness_status(version_counts: list[dict[str, Any]], expected: dict[str, str]) -> str:
    if not version_counts:
        return "stale"
    if len(version_counts) != 1:
        return "stale"
    row = version_counts[0]
    for key, expected_value in expected.items():
        if row.get(key) != expected_value:
            return "stale"
    return "fresh"


def check_cache_freshness() -> dict[str, Any]:
    """Check compiled matcher/cache versions without mutating the database."""
    try:
        from database import get_db_session  # noqa: WPS433
    except Exception as exc:  # pragma: no cover - depends on local env config
        return {
            "status": "unavailable",
            "blocked": False,
            "error": f"{type(exc).__name__}: {exc}",
            "tables": {},
        }

    table_specs = {
        "compiled_recipe_match_data": {
            "sql": """
                SELECT compiler_version, count(*) AS count
                FROM compiled_recipe_match_data
                GROUP BY 1
            """,
            "fields": ("compiler_version",),
            "expected": {"compiler_version": RECIPE_COMPILER_VERSION},
            "refresh": "compiled_recipe",
        },
        "compiled_offer_match_data": {
            "sql": """
                SELECT compiler_version, count(*) AS count
                FROM compiled_offer_match_data
                GROUP BY 1
            """,
            "fields": ("compiler_version",),
            "expected": {"compiler_version": OFFER_COMPILER_VERSION},
            "refresh": "compiled_offer",
        },
        "compiled_recipe_term_index": {
            "sql": """
                SELECT matcher_version, recipe_compiler_version, count(*) AS count
                FROM compiled_recipe_term_index
                GROUP BY 1, 2
            """,
            "fields": ("matcher_version", "recipe_compiler_version"),
            "expected": {
                "matcher_version": MATCHER_VERSION,
                "recipe_compiler_version": RECIPE_COMPILER_VERSION,
            },
            "refresh": "recipe_term_index",
        },
        "compiled_offer_term_index": {
            "sql": """
                SELECT matcher_version, offer_compiler_version, count(*) AS count
                FROM compiled_offer_term_index
                GROUP BY 1, 2
            """,
            "fields": ("matcher_version", "offer_compiler_version"),
            "expected": {
                "matcher_version": MATCHER_VERSION,
                "offer_compiler_version": OFFER_COMPILER_VERSION,
            },
            "refresh": "offer_term_index",
        },
        "recipe_offer_cache": {
            "sql": """
                SELECT
                    match_data->>'matcher_version' AS matcher_version,
                    match_data->>'recipe_compiler_version' AS recipe_compiler_version,
                    match_data->>'offer_compiler_version' AS offer_compiler_version,
                    count(*) AS count
                FROM recipe_offer_cache
                GROUP BY 1, 2, 3
            """,
            "fields": ("matcher_version", "recipe_compiler_version", "offer_compiler_version"),
            "expected": {
                "matcher_version": MATCHER_VERSION,
                "recipe_compiler_version": RECIPE_COMPILER_VERSION,
                "offer_compiler_version": OFFER_COMPILER_VERSION,
            },
            "refresh": "full_cache_rebuild",
        },
    }

    tables: dict[str, Any] = {}
    try:
        with get_db_session() as db:
            for table_name, spec in table_specs.items():
                exists = db.execute(
                    text("SELECT to_regclass(:table_name)"),
                    {"table_name": f"public.{table_name}"},
                ).scalar()
                if not exists:
                    tables[table_name] = {
                        "status": "missing",
                        "expected": spec["expected"],
                        "version_counts": [],
                        "needed_refresh": spec["refresh"],
                    }
                    continue

                rows = db.execute(text(spec["sql"])).fetchall()
                version_counts = _group_version_counts(rows, *spec["fields"])
                status = _freshness_status(version_counts, spec["expected"])
                tables[table_name] = {
                    "status": status,
                    "expected": spec["expected"],
                    "version_counts": version_counts,
                    "needed_refresh": None if status == "fresh" else spec["refresh"],
                }
    except Exception as exc:  # pragma: no cover - depends on local DB state
        return {
            "status": "unavailable",
            "blocked": False,
            "error": f"{type(exc).__name__}: {exc}",
            "tables": tables,
        }

    stale_tables = [
        table_name
        for table_name, table_result in tables.items()
        if table_result["status"] != "fresh"
    ]
    return {
        "status": "fresh" if not stale_tables else "stale",
        "blocked": bool(stale_tables),
        "stale_cache_tables": len(stale_tables),
        "needed_refreshes": [
            tables[table_name]["needed_refresh"]
            for table_name in stale_tables
            if tables[table_name].get("needed_refresh")
        ],
        "tables": tables,
    }


def diagnose_case(
    case: DiagnosticCase,
    *,
    include_cache_freshness: bool = True,
    require_fresh_cache: bool = False,
) -> dict[str, Any]:
    cache_freshness = check_cache_freshness() if include_cache_freshness else {
        "status": "skipped",
        "blocked": False,
        "tables": {},
    }
    if require_fresh_cache and cache_freshness.get("blocked"):
        return _json_safe({
            "case_id": case.case_id,
            "expected": case.expected,
            "actual": None,
            "passed": False,
            "versions": {
                "matcher_version": MATCHER_VERSION,
                "recipe_compiler_version": RECIPE_COMPILER_VERSION,
                "offer_compiler_version": OFFER_COMPILER_VERSION,
            },
            "cache_freshness": cache_freshness,
            "semantic_diagnostics_blocked": True,
            "diagnosis_class": "cache_freshness_blocked",
            "first_action": "Refresh stale compiled data/term indexes before semantic diagnostics.",
        })

    recipe = _build_recipe(case)
    offer = _build_offer(case)

    prepared_recipe = prepare_recipe_match_runtime_data(recipe)
    compiled_recipe_payload = serialize_prepared_recipe_match_runtime_data(prepared_recipe)
    offer_precomputed_raw = precompute_offer_data(
        offer.name,
        offer.category or "",
        brand=offer.brand or "",
        weight_grams=float(offer.weight_grams) if offer.weight_grams is not None else None,
    )
    offer_precomputed = normalize_compiled_offer_payload(offer_precomputed_raw)
    offer_route_terms_typed = build_offer_candidate_terms(offer_precomputed)
    offer_route_terms = {term for term, _term_type in offer_route_terms_typed}

    recipe_probe_terms = set(offer_route_terms)
    for item in prepared_recipe["ingredient_match_data_per_ing"]:
        recipe_probe_terms.update(str(keyword) for keyword in item.extracted_keywords if keyword)

    recipe_term_map = build_recipe_ingredient_term_map(compiled_recipe_payload, recipe_probe_terms)
    recipe_route_terms = {term for term, indices in recipe_term_map.items() if indices}
    paired_route_terms = recipe_route_terms & offer_route_terms
    hinted_indices = sorted({
        index
        for term in paired_route_terms
        for index in recipe_term_map.get(term, set())
    })

    offer_identity_key = build_offer_identity_key(offer)
    offer_id = id(offer)
    offer_data_cache = {offer_id: offer_precomputed}
    ingredient_match_data_per_ing = prepared_recipe["ingredient_match_data_per_ing"]
    fullscan_candidates = collect_offer_match_candidates(
        ingredient_match_data_per_ing,
        prepare_offer_match_candidate(
            offer,
            offer_id,
            None,
            offer_data_cache,
            ingredient_match_data_per_ing,
            [],
        )["offer_match_data"],
    )
    fullscan_selection = select_offer_match_candidate(
        fullscan_candidates,
        ingredient_match_data_per_ing,
    )
    hint_candidates = collect_offer_match_candidates(
        ingredient_match_data_per_ing,
        prepare_offer_match_candidate(
            offer,
            offer_id,
            None,
            offer_data_cache,
            ingredient_match_data_per_ing,
            [],
        )["offer_match_data"],
        hinted_indices,
    )
    hint_selection = select_offer_match_candidate(
        hint_candidates,
        ingredient_match_data_per_ing,
    )
    initial_match = prepare_offer_match_candidate(
        offer,
        offer_id,
        None,
        offer_data_cache,
        ingredient_match_data_per_ing,
    )

    validation_events: list[dict[str, Any]] = []
    validated_offer_data = validate_offer_match_candidate(
        offer,
        offer_id,
        offer_data_cache,
        initial_match["matched_keyword"],
        initial_match["matched_ing_idx"],
        initial_match["offer_precomputed"],
        initial_match["offer_match_data"],
        initial_match["effective_offer_data"],
        initial_match["offer_match_keywords"],
        initial_match["offer_name_normalized"],
        ingredient_match_data_per_ing,
        prepared_recipe["ingredients_normalized"],
        prepared_recipe["ingredient_source_texts"],
        prepared_recipe["ingredient_source_indices"],
        prepared_recipe["merged_ingredients"],
        prepared_recipe["full_recipe_text"],
        validation_events,
    )

    matcher = DiagnosticMatcher()
    materialized = match_recipe_to_offers(
        matcher,
        recipe,
        [offer],
        preferences={},
        offer_data_cache=offer_data_cache,
        prepared_recipe_data=prepared_recipe,
        ingredient_candidate_indices_by_offer={
            offer_identity_key: set(hinted_indices),
        },
        ingredient_routing_mode="hint_first",
    )
    materialized_matches = [
        item
        for item in materialized.get("matched_offers", [])
        if item.get("offer_identity_key") == offer_identity_key
    ]
    actual = 1 if materialized_matches else 0

    recipe_ingredients = []
    for index, item in enumerate(ingredient_match_data_per_ing):
        route_terms = sorted(
            term
            for term, indices in recipe_term_map.items()
            if index in indices
        )
        recipe_ingredients.append({
            "ingredient_index": index,
            "source_index": item.source_index,
            "ingredient_text": prepared_recipe["ingredient_source_texts"][index]
            if index < len(prepared_recipe["ingredient_source_texts"])
            else item.raw_text,
            "normalized_text": prepared_recipe["ingredients_normalized"][index]
            if index < len(prepared_recipe["ingredients_normalized"])
            else item.normalized_text,
            "prepared_text": item.normalized_text,
            "ingredient_keywords": sorted(item.extracted_keywords),
            "route_terms": route_terms,
        })

    last_reject = next(
        (
            event
            for event in reversed(validation_events)
            if event.get("type") == "validation_reject"
        ),
        None,
    )
    backend_accepted = validated_offer_data is not None
    signal_provenance = _build_signal_provenance(
        prepared_recipe=prepared_recipe,
        ingredient_match_data_per_ing=ingredient_match_data_per_ing,
        recipe_term_map=recipe_term_map,
        offer_precomputed=offer_precomputed,
        offer_route_terms_typed=offer_route_terms_typed,
        paired_route_terms=paired_route_terms,
        fullscan_candidates=fullscan_candidates,
        materialized_matches=materialized_matches,
    )
    normalized_ingredients = prepared_recipe["ingredients_normalized"]
    policy_ingredient_texts = []
    for index, source_text in enumerate(prepared_recipe["ingredient_source_texts"]):
        normalized = normalized_ingredients[index] if index < len(normalized_ingredients) else ""
        policy_ingredient_texts.append(f"{source_text} {normalized}")
    declarative_no_match_policies = list(
        find_no_match_policy_hits(
            ingredient_texts=policy_ingredient_texts,
            offer_keywords=offer_precomputed.get("keywords", []),
            offer_text=offer_precomputed.get("name_normalized", ""),
        )
    )
    declarative_match_bridges = list(
        find_match_bridge_hits(
            ingredient_texts=policy_ingredient_texts,
            offer_keywords=offer_precomputed.get("keywords", []),
            offer_text=offer_precomputed.get("name_normalized", ""),
        )
    )
    diagnosis_class, first_action = classify_diagnosis(
        expected=case.expected,
        actual=actual,
        recipe_route_terms=recipe_route_terms,
        offer_route_terms=offer_route_terms,
        paired_route_terms=paired_route_terms,
        hinted_indices=hinted_indices,
        fullscan_selection=fullscan_selection,
        backend_accepted=backend_accepted,
        materialized_matches=materialized_matches,
        last_reject=last_reject,
    )
    if diagnosis_class == "pass" and signal_provenance["duplicate_signal_source"]["count"]:
        diagnosis_class = "duplicate_signal_source"
        first_action = "Declare precedence/equivalence or retire the duplicate signal source."
    if diagnosis_class == "pass" and signal_provenance["ambiguous_canonical"]["count"]:
        diagnosis_class = "ambiguous_canonical"
        first_action = "Declare canonical precedence/equivalence for the competing signal terms."

    passed = (
        None
        if case.expected is None
        else actual == case.expected and diagnosis_class == "pass"
    )

    result = {
        "case_id": case.case_id,
        "expected": case.expected,
        "actual": actual,
        "passed": passed,
        "versions": {
            "matcher_version": MATCHER_VERSION,
            "recipe_compiler_version": RECIPE_COMPILER_VERSION,
            "offer_compiler_version": OFFER_COMPILER_VERSION,
        },
        "cache_freshness": cache_freshness,
        "semantic_diagnostics_blocked": False,
        "recipe_signals": {
            "route_terms": sorted(recipe_route_terms),
            "ingredients": recipe_ingredients,
        },
        "offer_signals": {
            "offer_keywords": sorted(str(value) for value in offer_precomputed.get("keywords", []) if value),
            "name_normalized": offer_precomputed.get("name_normalized", ""),
            "route_terms": sorted(offer_route_terms),
            "route_terms_typed": [
                {"term": term, "term_type": term_type}
                for term, term_type in sorted(offer_route_terms_typed)
            ],
        },
        "signal_provenance": signal_provenance,
        "declarative_rules": {
            "no_match_policies": declarative_no_match_policies,
            "match_bridges": declarative_match_bridges,
        },
        "candidate_routing": {
            "offer_recipe_routed": bool(paired_route_terms),
            "paired_route_terms": sorted(paired_route_terms),
            "hint_first_simulated": True,
            "hinted_ingredient_indices": hinted_indices,
            "offer_identity_key": offer_identity_key,
        },
        "hint_first": {
            "probe_scope": "routed_pair" if paired_route_terms else "unrouted_diagnostic_probe",
            "routed": bool(paired_route_terms),
            "hinted_ingredient_indices": hinted_indices,
            "fullscan_fallback_count": materialized.get("fullscan_fallback_count", 0),
            "fullscan_fallback_reason_counts": materialized.get("fullscan_fallback_reason_counts", {}),
            "hinted_no_match_count": materialized.get("hinted_no_match_count", 0),
        },
        "fast_match": {
            "matched": bool(fullscan_selection["matched_keyword"]),
            "matched_keyword": fullscan_selection["matched_keyword"],
            "matched_ingredient_index": fullscan_selection["matched_ing_idx"],
            "matched_candidates": [
                {"ingredient_index": ing_idx, "matched_keyword": keyword}
                for ing_idx, keyword in fullscan_candidates
            ],
            "hinted_matched": bool(hint_selection["matched_keyword"]),
            "hinted_matched_keyword": hint_selection["matched_keyword"],
            "hinted_matched_ingredient_index": hint_selection["matched_ing_idx"],
            "hinted_matched_candidates": [
                {"ingredient_index": ing_idx, "matched_keyword": keyword}
                for ing_idx, keyword in hint_candidates
            ],
        },
        "backend_validation": {
            "accepted": backend_accepted,
            "matched_keyword": validated_offer_data.get("matched_keyword") if validated_offer_data else None,
            "matched_ingredient_index": validated_offer_data.get("_matched_ing_idx") if validated_offer_data else None,
            "reject_rule": last_reject.get("rule") if last_reject else None,
            "reject_detail": last_reject.get("detail") if last_reject else None,
            "events": validation_events,
        },
        "materialization": {
            "matched": bool(materialized_matches),
            "matched_offers": [
                {
                    "name": item.get("name"),
                    "matched_keyword": item.get("matched_keyword"),
                    "matched_ingredient_index": item.get("_matched_ing_idx"),
                    "offer_identity_key": item.get("offer_identity_key"),
                }
                for item in materialized_matches
            ],
            "num_matches": materialized.get("num_matches", 0),
            "num_offers": materialized.get("num_offers", 0),
            "fullscan_fallback_count": materialized.get("fullscan_fallback_count", 0),
            "fullscan_fallback_reason_counts": materialized.get("fullscan_fallback_reason_counts", {}),
        },
        "diagnosis_class": diagnosis_class,
        "first_action": first_action,
    }
    return _json_safe(result)


def classify_diagnosis(
    *,
    expected: int | None,
    actual: int,
    recipe_route_terms: set[str],
    offer_route_terms: set[str],
    paired_route_terms: set[str],
    hinted_indices: list[int],
    fullscan_selection: dict[str, Any],
    backend_accepted: bool,
    materialized_matches: list[dict[str, Any]],
    last_reject: dict[str, Any] | None,
) -> tuple[str, str]:
    if expected == 0 and actual == 1:
        return (
            "unexpected_positive",
            "Add or tighten a no-match policy/negative fixture for this recipe-offer pair.",
        )

    if expected == 1 and not recipe_route_terms:
        return (
            "recipe_signal_missing",
            "Expose the accepted canonical term from ingredient extraction or recipe signals.",
        )
    if expected == 1 and not offer_route_terms:
        return (
            "offer_signal_missing",
            "Expose the accepted canonical term from offer precompute/offer signals.",
        )
    if expected == 1 and not paired_route_terms:
        return (
            "route_pair_missing",
            "Add the shared canonical route term through a declared rule or typed expansion.",
        )
    if expected == 1 and not hinted_indices:
        return (
            "ingredient_hint_missing",
            "Check ingredient hint map generation for the paired route terms.",
        )
    if expected == 1 and not fullscan_selection.get("matched_keyword"):
        return (
            "fast_match_missing",
            "Route reaches the pair, but matches_ingredient_fast does not accept it.",
        )
    if expected == 1 and not backend_accepted:
        reject_rule = last_reject.get("rule") if last_reject else "unknown"
        return (
            "backend_validation_rejected",
            f"Review backend validation rule {reject_rule!r} for this accepted policy.",
        )
    if expected == 1 and backend_accepted and not materialized_matches:
        return (
            "materialization_dropped",
            "The backend accepted the match, but grouped cache materialization lost it.",
        )

    if expected is None:
        return (
            "observed_positive" if actual else "observed_negative",
            "Set --expected 1 or --expected 0 to turn this observation into a gate.",
        )
    return ("pass", "No action needed for this case.")


def _load_case_file(path: Path, case_id: str | None) -> DiagnosticCase:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    cases = payload if isinstance(payload, list) else [payload]
    if case_id is None and len(cases) != 1:
        raise SystemExit("--case-id is required when --case-file contains multiple cases")

    selected = None
    for item in cases:
        if case_id is None or item.get("case_id") == case_id or item.get("id") == case_id:
            selected = item
            break
    if selected is None:
        raise SystemExit(f"case id not found in {path}: {case_id}")
    return _case_from_mapping(selected)


def _case_from_mapping(payload: dict[str, Any]) -> DiagnosticCase:
    offer_payload = payload.get("offer") or {}
    ingredients = payload.get("ingredients") or []
    if not ingredients and payload.get("ingredient"):
        ingredients = [payload["ingredient"]]
    if not ingredients:
        raise SystemExit("case requires ingredients or ingredient")
    if not offer_payload.get("name") and not payload.get("offer_name"):
        raise SystemExit("case requires offer.name or offer_name")
    return DiagnosticCase(
        case_id=str(payload.get("case_id") or payload.get("id") or DEFAULT_CASE_ID),
        recipe_name=str(payload.get("recipe_name") or "Sanity Recipe"),
        ingredients=tuple(str(item) for item in ingredients),
        offer_name=str(offer_payload.get("name") or payload.get("offer_name")),
        offer_category=str(offer_payload.get("category") or payload.get("offer_category") or ""),
        offer_brand=str(offer_payload.get("brand") or payload.get("offer_brand") or ""),
        expected=(
            None
            if payload.get("expected") is None
            else int(payload.get("expected"))
        ),
    )


def _case_from_args(args: argparse.Namespace) -> DiagnosticCase:
    if args.case_file:
        return _load_case_file(Path(args.case_file), args.case_id)
    if args.case_id and not args.ingredient:
        raise SystemExit("--case-id currently requires --case-file unless inline ingredients are provided")
    if not args.ingredient:
        raise SystemExit("--ingredient is required for inline diagnostics")
    if not args.offer_name:
        raise SystemExit("--offer-name is required for inline diagnostics")
    return DiagnosticCase(
        case_id=args.case_id or DEFAULT_CASE_ID,
        recipe_name=args.recipe_name,
        ingredients=tuple(args.ingredient),
        offer_name=args.offer_name,
        offer_category=args.offer_category,
        offer_brand=args.offer_brand,
        expected=args.expected,
    )


def format_text(result: dict[str, Any]) -> str:
    cache = result["cache_freshness"]
    if result.get("semantic_diagnostics_blocked"):
        return "\n".join([
            f"case: {result['case_id']}",
            f"expected: {result['expected']} actual: {result['actual']} passed: {result['passed']}",
            f"cache freshness: {cache.get('status')} stale_tables: {cache.get('stale_cache_tables', 0)}",
            f"needed refreshes: {', '.join(cache.get('needed_refreshes', [])) or '-'}",
            f"diagnosis: {result['diagnosis_class']}",
            f"first action: {result['first_action']}",
        ])

    recipe_terms = ", ".join(result["recipe_signals"]["route_terms"]) or "-"
    offer_terms = ", ".join(result["offer_signals"]["route_terms"]) or "-"
    paired_terms = ", ".join(result["candidate_routing"]["paired_route_terms"]) or "-"
    hinted = result["candidate_routing"]["hinted_ingredient_indices"]
    hint_first = result["hint_first"]
    fast = result["fast_match"]
    backend = result["backend_validation"]
    materialization = result["materialization"]
    provenance = result.get("signal_provenance", {})
    no_match_policies = result.get("declarative_rules", {}).get("no_match_policies", [])
    match_bridges = result.get("declarative_rules", {}).get("match_bridges", [])
    duplicate_count = provenance.get("duplicate_signal_source", {}).get("count", 0)
    ambiguous_count = provenance.get("ambiguous_canonical", {}).get("count", 0)
    no_match_policy_ids = ", ".join(policy["id"] for policy in no_match_policies) or "-"
    match_bridge_ids = ", ".join(bridge["id"] for bridge in match_bridges) or "-"

    lines = [
        f"case: {result['case_id']}",
        f"expected: {result['expected']} actual: {result['actual']} passed: {result['passed']}",
        f"cache freshness: {cache.get('status')} stale_tables: {cache.get('stale_cache_tables', 0)}",
        f"recipe signals -> route_terms: {recipe_terms}",
        f"offer signals -> keywords: {', '.join(result['offer_signals']['offer_keywords']) or '-'}",
        f"offer signals -> route_terms: {offer_terms}",
        f"routing -> routed: {result['candidate_routing']['offer_recipe_routed']} terms: {paired_terms}",
        f"hint -> indices: {hinted if hinted else '-'}",
        "hint-first -> "
        f"scope: {hint_first['probe_scope']} "
        f"fallbacks: {hint_first['fullscan_fallback_count']} "
        f"reasons: {hint_first['fullscan_fallback_reason_counts'] or '-'}",
        "fastmatch -> "
        f"matched: {fast['matched']} keyword: {fast['matched_keyword']} "
        f"ingredient: {fast['matched_ingredient_index']}",
        "backend -> "
        f"accepted: {backend['accepted']} reject_rule: {backend['reject_rule']} "
        f"reject_detail: {backend['reject_detail']}",
        "materialization -> "
        f"matched: {materialization['matched']} num_matches: {materialization['num_matches']} "
        f"fallbacks: {materialization['fullscan_fallback_count']}",
        f"signal provenance -> duplicate_signal_source: {duplicate_count} ambiguous_canonical: {ambiguous_count}",
        f"declarative no-match policies -> {no_match_policy_ids}",
        f"declarative match bridges -> {match_bridge_ids}",
        f"diagnosis: {result['diagnosis_class']}",
        f"first action: {result['first_action']}",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose which matcher layer loses one Swedish recipe/offer case.",
    )
    parser.add_argument("--ingredient", action="append", help="Inline ingredient row. Can be repeated.")
    parser.add_argument("--recipe-name", default="Sanity Recipe")
    parser.add_argument("--offer-name")
    parser.add_argument("--offer-category", default="")
    parser.add_argument("--offer-brand", default="")
    parser.add_argument("--expected", type=int, choices=(0, 1))
    parser.add_argument("--case-id")
    parser.add_argument("--case-file", help="JSON case file with one case or a list of cases.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--skip-cache-freshness",
        action="store_true",
        help="Skip DB freshness preflight for offline inline diagnostics.",
    )
    parser.add_argument(
        "--require-fresh-cache",
        action="store_true",
        help="Fail before semantic diagnostics when compiled/cache versions are stale.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    case = _case_from_args(args)
    result = diagnose_case(
        case,
        include_cache_freshness=not args.skip_cache_freshness,
        require_fresh_cache=args.require_fresh_cache,
    )
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 1 if result.get("passed") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
