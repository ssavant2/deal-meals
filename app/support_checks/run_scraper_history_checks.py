#!/usr/bin/env python3
"""Policy checks for scraper run-history retention helpers."""

from __future__ import annotations

from pathlib import Path
import sys


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from utils.scraper_history import (  # noqa: E402
    RUN_HISTORY_RETENTION_PER_SCRAPER_MODE,
    _cleanup_run_history_for_scraper_mode,
    scrape_result_history_kwargs,
)


class _FakeResult:
    rowcount = 7


class _FakeDb:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return _FakeResult()


def check(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"OK {name}")


def main() -> int:
    check("default retention is 30", RUN_HISTORY_RETENTION_PER_SCRAPER_MODE, 30)

    fake_db = _FakeDb()
    removed = _cleanup_run_history_for_scraper_mode(
        fake_db,
        scraper_id="mathem",
        mode="incremental",
        keep_latest=30,
    )
    check("cleanup returns rowcount", removed, 7)
    check("cleanup call count", len(fake_db.calls), 1)

    sql, params = fake_db.calls[0]
    check("cleanup SQL targets table", "DELETE FROM scraper_run_history" in sql, True)
    check("cleanup SQL is scoped by scraper", "scraper_id = :scraper_id" in sql, True)
    check("cleanup SQL is scoped by mode", "mode = :mode" in sql, True)
    check("cleanup uses offset retention", "OFFSET :keep_latest" in sql, True)
    check("cleanup scraper param", params["scraper_id"], "mathem")
    check("cleanup mode param", params["mode"], "incremental")
    check("cleanup keep param", params["keep_latest"], 30)

    fake_db = _FakeDb()
    _cleanup_run_history_for_scraper_mode(
        fake_db,
        scraper_id="coop",
        mode="test",
        keep_latest=0,
    )
    check("cleanup clamps retention", fake_db.calls[0][1]["keep_latest"], 1)

    class FakeScrapeResult:
        status = "success"
        reason = "target_reached"
        diagnostics = {
            "candidate_url_count": 100,
            "selected_url_count": 20,
            "parsed_recipe_count": 12,
            "filtered_non_recipe_count": 3,
            "parse_rate": 0.6,
            "parser_method": "recipe_api",
        }

    kwargs = scrape_result_history_kwargs(FakeScrapeResult(), source_kind="recipe")
    check("history kwargs source kind", kwargs["source_kind"], "recipe")
    check("history kwargs status", kwargs["status"], "success")
    check("history kwargs reason", kwargs["reason_code"], "target_reached")
    check("history kwargs candidate count", kwargs["candidate_count"], 100)
    check("history kwargs selected count", kwargs["selected_count"], 20)
    check("history kwargs parsed count", kwargs["parsed_count"], 12)
    check("history kwargs filtered count", kwargs["filtered_count"], 3)
    check("history kwargs parse rate", kwargs["parse_rate"], 0.6)
    check("history kwargs data path", kwargs["data_path"], "recipe_api")

    print("ALL SCRAPER HISTORY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
