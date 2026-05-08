#!/usr/bin/env python3
"""Checks for Phase 2 recipe ingredient term-map helpers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from types import SimpleNamespace

sys.path.insert(0, '/app' if os.path.exists('/app') else os.path.join(os.path.dirname(__file__), '..'))

from languages.matcher_runtime import build_recipe_ingredient_term_map  # noqa: E402
from languages.sv.ingredient_matching import (  # noqa: E402
    build_prepared_ingredient_match_data,
    serialize_prepared_recipe_match_runtime_data,
)
from languages.sv.ingredient_matching.term_indexes import (  # noqa: E402
    build_offer_candidate_terms,
    build_recipe_search_text_map,
    recipe_text_contains_routing_term,
)


passed = 0
failed = 0


def test(desc: str, actual, expected) -> None:
    global passed, failed
    if actual == expected:
        passed += 1
        return
    failed += 1
    print(f"FAIL: {desc}")
    print(f"  got:      {actual}")
    print(f"  expected: {expected}")


def _ingredient_data(raw_text: str, normalized_text: str, keywords: set[str], idx: int):
    return build_prepared_ingredient_match_data(
        normalized_text,
        raw_text=raw_text,
        extracted_keywords=frozenset(keywords),
        source_index=idx,
        expanded_index=idx,
        prepared_fast_text=True,
    )


prepared_payload = {
    "merged_ingredients": [
        "2 dl vispgradde",
        "1 burk tomat arla",
        "",
        "extra tomater",
    ],
    "ingredient_source_texts": [
        "2 dl vispgradde",
        "1 burk tomat arla",
        "",
        "extra tomater",
    ],
    "ingredient_source_indices": [0, 1, 2, 3],
    "ingredients_normalized": [
        "vispgradde",
        "tomat arla",
        "",
        "tomater",
    ],
    "ingredients_search_text": "vispgradde tomat arla tomater",
    "full_recipe_text": "testrecept vispgradde tomat arla tomater",
    "ingredient_match_data_per_ing": [
        _ingredient_data("2 dl vispgradde", "vispgradde", {"vispgradde"}, 0),
        _ingredient_data("1 burk tomat arla", "tomat arla", {"tomat"}, 1),
        _ingredient_data("", "", set(), 2),
        _ingredient_data("extra tomater", "tomater", {"tomat"}, 3),
    ],
}
compiled_payload = serialize_prepared_recipe_match_runtime_data(prepared_payload)

term_map = build_recipe_ingredient_term_map(
    compiled_payload,
    {"gradde", "tomat", "arla", "mat", "saknas"},
)
test("parent keyword maps to expanded ingredient index", term_map["gradde"], {0})
test("direct keyword maps to all matching expanded indices", term_map["tomat"], {1, 3})
test("normalized text containment maps offer name words", term_map["arla"], {1})
test("offer name words do not map by substring inside recipe words", term_map["mat"], set())
test("missing terms stay present with empty hint sets", term_map["saknas"], set())

runtime_shape_map = build_recipe_ingredient_term_map(
    prepared_payload,
    {"gradde", "tomat"},
)
test("runtime prepared payload shape is accepted", runtime_shape_map["tomat"], {1, 3})

env = dict(os.environ)
env["MATCHER_LANGUAGE"] = "en-gb"
probe = subprocess.run(
    [
        sys.executable,
        "-c",
        (
            "import json; "
            "from languages.matcher_runtime import MATCHER_LANGUAGE, build_recipe_ingredient_term_map; "
            "hints = build_recipe_ingredient_term_map({'ingredients_normalized':['tomat']}, {'tomat'}); "
            "print(json.dumps({'language': MATCHER_LANGUAGE, 'hints': {k: sorted(v) for k, v in hints.items()}}))"
        ),
    ],
    check=True,
    capture_output=True,
    env=env,
    text=True,
)
probe_payload = json.loads(probe.stdout)
test("en_gb backend remains loadable", probe_payload["language"], "en_gb")
test("en_gb skeleton returns no ingredient hints", probe_payload["hints"], {"tomat": []})

search_text = "1 pkt fläsk 2 krm svartpeppar 1 dl strösocker"
test("name_word recipe routing requires whole word", recipe_text_contains_routing_term(search_text, "läsk", "name_word"), False)
test("name_word recipe routing does not match pepper prefix", recipe_text_contains_routing_term(search_text, "pepp", "name_word"), False)
test("keyword recipe routing keeps compound substring behavior", recipe_text_contains_routing_term(search_text, "peppar", "keyword"), True)
test("short keyword routing does not match inside longer words", recipe_text_contains_routing_term("1 msk vetemjöl 2 dl mellanmjölk", "öl", "keyword"), False)
test("short keyword routing still matches standalone words", recipe_text_contains_routing_term("2 dl öl till gryta", "öl", "keyword"), True)

offer_terms = build_offer_candidate_terms({
    "keywords": ["flingsalt", "mineralvatten"],
    "carrier_stripped": [],
    "name_normalized": "vatten salt flingsalt mineralvatten kolsyrat zeta port färsk riven pasta",
})
test("offer routing keeps specific salt/water keywords", ("flingsalt", "keyword") in offer_terms and ("mineralvatten", "keyword") in offer_terms, True)
test("offer routing keeps useful specific name words", ("kolsyrat", "name_word") in offer_terms and ("pasta", "name_word") in offer_terms, True)
test("offer routing suppresses generic descriptor name words", any(term in offer_terms for term in {
    ("vatten", "name_word"),
    ("salt", "name_word"),
    ("zeta", "name_word"),
    ("port", "name_word"),
    ("färsk", "name_word"),
    ("riven", "name_word"),
}), False)

payload_with_alias = {
    "ingredients_search_text": "340 g makaroner 3 dl soyabaserad matlagning",
    "ingredient_match_data": [
        {
            "normalized_text": "340 g makaroner pasta",
            "extracted_keywords": ["pasta"],
        },
        {
            "normalized_text": "3 dl soyabaserad matlagning grädde",
            "extracted_keywords": ["grädde", "soja"],
        },
    ],
}
routing_text = build_recipe_search_text_map(
    [SimpleNamespace(id="recipe-1")],
    compiled_recipe_payload_cache={"recipe-1": payload_with_alias},
)["recipe-1"]
test("compiled recipe routing text includes prepared canonical aliases", "pasta" in routing_text and "grädde" in routing_text, True)
test("compiled recipe routing text does not append extracted-only keywords blindly", " soja " in f" {routing_text} ", False)

whole_chicken_routing_text = build_recipe_search_text_map(
    [SimpleNamespace(id="recipe-2")],
    compiled_recipe_payload_cache={
        "recipe-2": {
            "ingredients_search_text": "1 stor kyckling i 8 bitar",
            "ingredient_match_data": [
                {
                    "normalized_text": "1 stor kyckling i 8 bitar",
                    "extracted_keywords": ["kyckling"],
                },
            ],
        },
    },
)["recipe-2"]
test("whole chicken recipe routing includes helkyckling alias", " helkyckling " in f" {whole_chicken_routing_text} ", True)

cut_chicken_routing_text = build_recipe_search_text_map(
    [SimpleNamespace(id="recipe-3")],
    compiled_recipe_payload_cache={
        "recipe-3": {
            "ingredients_search_text": "500 g kycklingfile",
            "ingredient_match_data": [
                {
                    "normalized_text": "500 g kycklingfile",
                    "extracted_keywords": ["kycklingfilé"],
                },
            ],
        },
    },
)["recipe-3"]
test("cut chicken recipe routing does not include helkyckling alias", " helkyckling " in f" {cut_chicken_routing_text} ", False)


print("\n========================================")
print(f"TOTAL: {passed}/{passed + failed} checks passed")
if failed:
    print(f"{failed} FAILED!")
    print("========================================")
    raise SystemExit(1)

print("ALL PASSED!")
print("========================================")
