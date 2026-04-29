#!/usr/bin/env python3
"""Policy checks for recipe URL discovery cache helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from scrapers.recipes import url_discovery_cache as discovery


def check(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"OK {name}")


def main() -> int:
    now = datetime(2026, 4, 29, tzinfo=timezone.utc)

    check(
        "normalizes host, scheme, fragment, slash and tracking query",
        discovery.normalize_recipe_url(
            "HTTPS://WWW.KOKET.SE/recept/pasta/?utm_source=x&portioner=4#top"
        ),
        "https://www.koket.se/recept/pasta?portioner=4",
    )
    check(
        "keeps non-tracking query",
        discovery.normalize_recipe_url("https://www.koket.se/recept/pasta?foo=1&bar="),
        "https://www.koket.se/recept/pasta?foo=1&bar=",
    )
    check(
        "non-recipe retry cycle",
        [discovery._retry_delay_for("known_non_recipe", i).days for i in range(6)],
        [30, 45, 90, 180, 30, 45],
    )
    check(
        "temporary retry delay",
        discovery._retry_delay_for("temporary_failed", 12).days,
        3,
    )
    check(
        "stale discovery retention is two full retry cycles",
        discovery.DISCOVERY_CACHE_RETENTION_DAYS,
        690,
    )

    original_known = discovery._load_existing_and_excluded_urls
    original_rows = discovery._load_discovery_rows
    try:
        future_cached = discovery.normalize_recipe_url("https://www.koket.se/recept/cache")
        due_cached = discovery.normalize_recipe_url("https://www.koket.se/recept/due")

        def fake_known(source_name: str):
            existing = {"https://www.koket.se/recept/existing"}
            excluded = {"https://www.koket.se/recept/excluded"}
            return (
                existing,
                {discovery.normalize_recipe_url(url) for url in existing},
                excluded,
                {discovery.normalize_recipe_url(url) for url in excluded},
            )

        def fake_rows(source_name: str, normalized_urls: list[str]):
            return {
                future_cached: discovery._DiscoveryRow(
                    status="known_non_recipe",
                    reason="no_recipe_type",
                    next_retry_at=now + timedelta(days=1),
                ),
                due_cached: discovery._DiscoveryRow(
                    status="known_non_recipe",
                    reason="no_recipe_type",
                    next_retry_at=now - timedelta(seconds=1),
                ),
            }

        discovery._load_existing_and_excluded_urls = fake_known
        discovery._load_discovery_rows = fake_rows

        selected, stats = discovery.select_urls_for_scrape(
            source_name="Köket.se",
            candidate_urls=[
                "https://www.koket.se/recept/existing",
                "https://www.koket.se/recept/excluded",
                "https://www.koket.se/recept/cache",
                "https://www.koket.se/recept/due",
                "https://www.koket.se/recept/unknown",
                "https://www.koket.se/recept/unknown/",
            ],
            max_http_attempts=2,
            now=now,
        )
        check("selected due and unknown only", selected, [
            "https://www.koket.se/recept/due",
            "https://www.koket.se/recept/unknown",
        ])
        check("skipped existing", stats.url_candidates_skipped_existing, 1)
        check("skipped excluded", stats.url_candidates_skipped_excluded, 1)
        check("skipped cached", stats.url_candidates_skipped_non_recipe_cache, 1)
        check("retry due", stats.url_candidates_retried_non_recipe_cache, 1)
        check("duplicate skipped", stats.url_candidates_skipped_duplicate, 1)

        selected, stats = discovery.select_urls_for_scrape(
            source_name="Köket.se",
            candidate_urls=[
                "https://www.koket.se/recept/cache",
                "https://www.koket.se/recept/unknown-a",
                "https://www.koket.se/recept/unknown-b",
            ],
            max_http_attempts=1,
            now=now,
        )
        check("cache skip does not consume HTTP budget", selected, [
            "https://www.koket.se/recept/unknown-a",
        ])
        check("budget stop", stats.stopped_by_http_budget, True)

        selected, stats = discovery.select_urls_for_scrape(
            source_name="Köket.se",
            candidate_urls=[
                "https://www.koket.se/recept/unknown-a",
                "https://www.koket.se/recept/unknown-b",
            ],
            max_http_attempts=1,
            bulk_import=True,
            now=now,
        )
        check("bulk import ignores normal HTTP budget", selected, [
            "https://www.koket.se/recept/unknown-a",
            "https://www.koket.se/recept/unknown-b",
        ])
    finally:
        discovery._load_existing_and_excluded_urls = original_known
        discovery._load_discovery_rows = original_rows

    print("ALL RECIPE URL DISCOVERY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
