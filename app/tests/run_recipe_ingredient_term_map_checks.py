#!/usr/bin/env python3
"""Checks for Phase 2 recipe ingredient term-map helpers."""

from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, '/app' if os.path.exists('/app') else os.path.join(os.path.dirname(__file__), '..'))

from languages.matcher_runtime import build_recipe_ingredient_term_map  # noqa: E402
from languages.sv.ingredient_matching import (  # noqa: E402
    build_prepared_ingredient_match_data,
    serialize_prepared_recipe_match_runtime_data,
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
    {"gradde", "tomat", "arla", "saknas"},
)
test("parent keyword maps to expanded ingredient index", term_map["gradde"], {0})
test("direct keyword maps to all matching expanded indices", term_map["tomat"], {1, 3})
test("normalized text containment maps offer name words", term_map["arla"], {1})
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


print("\n========================================")
print(f"TOTAL: {passed}/{passed + failed} checks passed")
if failed:
    print(f"{failed} FAILED!")
    print("========================================")
    raise SystemExit(1)

print("ALL PASSED!")
print("========================================")
