#!/usr/bin/env python3
"""Policy checks for the first scraper robustness fixes."""

from __future__ import annotations

from pathlib import Path
import sys


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from scrapers.recipes.coop_scraper import (  # noqa: E402
    extract_coop_recipe_api_refs,
    parse_coop_recipe_api_payload,
)
from scrapers.recipes.mathem_scraper import (  # noqa: E402
    _unique_sorted_recipe_sitemaps,
    is_blocked_non_recipe_package_url,
    is_mathem_recipe_sitemap_url,
    non_recipe_package_reason,
)


def check(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"OK {name}")


def main() -> int:
    check(
        "Mathem real recipe sitemap accepted",
        is_mathem_recipe_sitemap_url("https://www.mathem.se/sitemap/sv/recipes/6.xml"),
        True,
    )
    check(
        "Mathem recipe-tags sitemap rejected",
        is_mathem_recipe_sitemap_url("https://www.mathem.se/sitemap/sv/recipe-tags/1.xml"),
        False,
    )
    check(
        "Mathem recipe-providers sitemap rejected",
        is_mathem_recipe_sitemap_url("https://www.mathem.se/sitemap/sv/recipe-providers/1.xml"),
        False,
    )
    check(
        "Mathem sitemap union is exact and sorted",
        _unique_sorted_recipe_sitemaps([
            "https://www.mathem.se/sitemap/sv/recipe-tags/1.xml",
            "https://www.mathem.se/sitemap/sv/recipes/3.xml",
            "https://www.mathem.se/sitemap/sv/recipes/1.xml",
            "https://www.mathem.se/sitemap/sv/recipes/3.xml",
        ]),
        [
            "https://www.mathem.se/sitemap/sv/recipes/1.xml",
            "https://www.mathem.se/sitemap/sv/recipes/3.xml",
        ],
    )

    check(
        "Mathem AW package URL blocked",
        is_blocked_non_recipe_package_url(
            "https://www.mathem.se/se/recipes/7000-mathem-mathems-lilla-aw-paket/"
        ),
        True,
    )
    check(
        "Mathem food packet recipe URL not broadly blocked",
        is_blocked_non_recipe_package_url(
            "https://www.mathem.se/se/recipes/7001-kock-laxpaket-med-citron/"
        ),
        False,
    )
    check(
        "Mathem package guard rejects package without real instructions",
        non_recipe_package_reason(
            {
                "name": "Mathems lilla AW-paket",
                "ingredients": ["chips", "oliver", "kex", "läsk"],
            },
            [],
            "https://www.mathem.se/se/recipes/7000-mathem-mathems-lilla-aw-paket/",
        ),
        "package_without_instructions",
    )
    check(
        "Mathem package guard leaves normal packet recipe alone",
        non_recipe_package_reason(
            {
                "name": "Laxpaket med citron",
                "ingredients": ["600 g laxfilé", "1 citron", "1 knippe dill"],
            },
            ["Lägg laxen i folie och baka i ugnen tills fisken är klar."],
            "https://www.mathem.se/se/recipes/7001-kock-laxpaket-med-citron/",
        ),
        None,
    )

    html = (
        '<main data-react-props="{"contentId":108201,'
        '"recipeExternalId":"2708855","isAdmin":false}"></main>'
        '<script>window.coopSettings={"recipe":{"apiUrl":'
        '"https://proxy.api.coop.se/external/recipe"}};</script>'
    )
    check(
        "Coop recipe API refs extracted",
        extract_coop_recipe_api_refs(html),
        ("2708855", "108201", "https://proxy.api.coop.se/external/recipe"),
    )

    recipe = parse_coop_recipe_api_payload(
        {
            "name": "Acaibowl",
            "relativeUrl": "/recept/acaibowl/",
            "imageUrl": "http://res.cloudinary.com/coopsverige/image/upload/test.jpg",
            "yieldValue": 2.0,
            "cookingTime": "10 min",
            "recipePart": [
                {
                    "sequenceNumber": 0,
                    "ingredients": [
                        {
                            "sequenceNumber": 0,
                            "name": "jordgubbar",
                            "quantity": "8.0",
                            "unit": "",
                            "prePreparation": "frysta",
                            "postPreparation": "",
                            "usePlural": True,
                            "ingredient": {"pluralName": "jordgubbar"},
                        },
                        {
                            "sequenceNumber": 1,
                            "name": "banan",
                            "quantity": "2.0",
                            "unit": "",
                            "prePreparation": "",
                            "postPreparation": "skalade",
                            "usePlural": True,
                            "ingredient": {"pluralName": "bananer"},
                        },
                        {
                            "sequenceNumber": 2,
                            "name": "appelmust",
                            "quantity": "1.0",
                            "unit": "dl",
                            "prePreparation": "",
                            "postPreparation": "",
                            "usePlural": False,
                            "ingredient": {"singularName": "appelmust"},
                        },
                    ],
                }
            ],
        },
        "https://www.coop.se/recept/acaibowl/",
    )
    check("Coop API payload parsed", recipe["name"], "Acaibowl")
    check("Coop API payload canonical URL", recipe["url"], "https://www.coop.se/recept/acaibowl/")
    check("Coop API payload time", recipe["prep_time_minutes"], 10)
    check("Coop API payload servings", recipe["servings"], 2)
    check("Coop API payload ingredients", recipe["ingredients"], [
        "8 frysta jordgubbar",
        "2 bananer skalade",
        "1 dl appelmust",
    ])

    print("ALL SCRAPER P0 CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
