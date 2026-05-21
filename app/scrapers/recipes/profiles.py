"""Source profiles for recipe scraper robustness decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RecipeSourceProfile:
    """Small source-owned contract for scraper health and preflight policy."""

    source_id: str
    db_source_name: str
    base_url: str
    # Bootstrap floor during burn-in and canary floor after burn-in.
    expected_min_urls: int | None = None
    expected_min_parse_rate: float | None = None
    allow_playwright_fallback: bool = False
    test_limit: int = 20
    preflight_urls: tuple[str, ...] = ()
    negative_preflight_urls: tuple[str, ...] = ()
    known_sitemap_urls: tuple[str, ...] = ()
    blocked_url_fragments: tuple[str, ...] = ()
    blocked_recipe_ids: tuple[str, ...] = ()


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    try:
        return tuple(str(item) for item in value if item)
    except TypeError:
        return ()


def _int_or_none(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _float_or_none(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _known_sitemap_urls(module: Any) -> tuple[str, ...]:
    urls = []
    urls.extend(_as_tuple(getattr(module, "KNOWN_SITEMAP_URLS", ())))
    urls.extend(_as_tuple(getattr(module, "SITEMAP_URLS", ())))
    urls.extend(_as_tuple(getattr(module, "SITEMAP_URL", None)))
    return tuple(dict.fromkeys(urls))


def build_recipe_source_profile(
    source_id: str,
    module: Any,
    *,
    db_source_name: str | None = None,
) -> RecipeSourceProfile:
    """Build a profile from optional explicit profile data plus module constants."""
    explicit = getattr(module, "RECIPE_SOURCE_PROFILE", None)
    if isinstance(explicit, RecipeSourceProfile):
        return explicit

    db_name = db_source_name or getattr(module, "DB_SOURCE_NAME", None) or getattr(module, "SCRAPER_NAME", "")
    expected_count = _int_or_none(getattr(module, "EXPECTED_RECIPE_COUNT", None))
    expected_min_urls = _int_or_none(getattr(module, "EXPECTED_MIN_URLS", None))
    if expected_min_urls is None and source_id != "myrecipes":
        expected_min_urls = expected_count

    base_url = getattr(module, "SOURCE_URL", "") or ""
    test_limit = _int_or_none(getattr(module, "TEST_RECIPE_LIMIT", None)) or 20

    return RecipeSourceProfile(
        source_id=source_id,
        db_source_name=db_name,
        base_url=base_url,
        expected_min_urls=expected_min_urls,
        expected_min_parse_rate=_float_or_none(getattr(module, "EXPECTED_MIN_PARSE_RATE", None)),
        allow_playwright_fallback=bool(getattr(module, "ALLOW_PLAYWRIGHT_FALLBACK", False)),
        test_limit=test_limit,
        preflight_urls=_as_tuple(getattr(module, "PREFLIGHT_URLS", ())),
        negative_preflight_urls=_as_tuple(getattr(module, "NEGATIVE_PREFLIGHT_URLS", ())),
        known_sitemap_urls=_known_sitemap_urls(module),
        blocked_url_fragments=_as_tuple(getattr(module, "BLOCKED_URL_FRAGMENTS", ())),
        blocked_recipe_ids=tuple(sorted(_as_tuple(getattr(module, "BLOCKED_NON_RECIPE_PACKAGE_IDS", ())))),
    )
