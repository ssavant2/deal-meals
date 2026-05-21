#!/usr/bin/env python3
"""Checks for recipe source profile derivation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from scrapers.recipes import ica_scraper, mathem_scraper, myrecipes_scraper  # noqa: E402
from scrapers.recipes.profiles import (  # noqa: E402
    RecipeSourceProfile,
    build_recipe_source_profile,
)


def check(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"OK {name}")


def main() -> int:
    mathem = build_recipe_source_profile("mathem", mathem_scraper)
    check("Mathem source id", mathem.source_id, "mathem")
    check("Mathem DB source", mathem.db_source_name, "Mathem.se")
    check("Mathem expected min URLs", mathem.expected_min_urls, 6000)
    check("Mathem blocked package id included", "3262" in mathem.blocked_recipe_ids, True)
    check("Mathem default test limit", mathem.test_limit, 20)

    ica = build_recipe_source_profile("ica", ica_scraper)
    check("ICA sitemap count", len(ica.known_sitemap_urls), 3)
    check("ICA first sitemap", ica.known_sitemap_urls[0], "https://www.ica.se/recept/sitemaps/recipes/1/")

    myrecipes = build_recipe_source_profile("myrecipes", myrecipes_scraper)
    check("My Recipes has no discovery floor", myrecipes.expected_min_urls, None)

    fake = SimpleNamespace(
        SCRAPER_NAME="Example",
        DB_SOURCE_NAME="Example DB",
        SOURCE_URL="https://example.test",
        EXPECTED_RECIPE_COUNT=123,
        EXPECTED_MIN_URLS=100,
        EXPECTED_MIN_PARSE_RATE=0.25,
        TEST_RECIPE_LIMIT=7,
        ALLOW_PLAYWRIGHT_FALLBACK=True,
        PREFLIGHT_URLS=("https://example.test/recipe",),
        NEGATIVE_PREFLIGHT_URLS=("https://example.test/not-a-recipe",),
        SITEMAP_URL="https://example.test/sitemap.xml",
        BLOCKED_URL_FRAGMENTS=("/tag/",),
    )
    profile = build_recipe_source_profile("example", fake)
    check("Fake expected min override", profile.expected_min_urls, 100)
    check("Fake parse rate", profile.expected_min_parse_rate, 0.25)
    check("Fake test limit", profile.test_limit, 7)
    check("Fake playwright flag", profile.allow_playwright_fallback, True)
    check("Fake preflight URL", profile.preflight_urls, ("https://example.test/recipe",))
    check("Fake negative preflight URL", profile.negative_preflight_urls, ("https://example.test/not-a-recipe",))
    check("Fake sitemap URL", profile.known_sitemap_urls, ("https://example.test/sitemap.xml",))
    check("Fake blocked fragment", profile.blocked_url_fragments, ("/tag/",))

    explicit = RecipeSourceProfile(
        source_id="explicit",
        db_source_name="Explicit",
        base_url="https://explicit.test",
        expected_min_urls=5,
    )
    explicit_module = SimpleNamespace(RECIPE_SOURCE_PROFILE=explicit)
    check("Explicit profile wins", build_recipe_source_profile("ignored", explicit_module), explicit)

    print("ALL RECIPE SOURCE PROFILE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
