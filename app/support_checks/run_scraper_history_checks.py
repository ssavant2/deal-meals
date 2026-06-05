#!/usr/bin/env python3
"""Policy checks for scraper run-history retention helpers."""

from __future__ import annotations

from pathlib import Path
import asyncio
import sys


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from utils.scraper_history import (  # noqa: E402
    RUN_HISTORY_RETENTION_PER_SCRAPER_MODE,
    _cleanup_run_history_for_scraper_mode,
    scrape_result_history_kwargs,
)
from startup_migrations import (  # noqa: E402
    ADD_SCRAPER_RUN_HISTORY_HEALTH_COLUMNS_SQL,
    ALLOW_MANUAL_SCRAPER_RUN_HISTORY_MODE_SQL,
)
from scrapers.recipes._common import (  # noqa: E402
    RecipeScrapeResult,
    StreamingRecipeSaver,
    finish_streaming_recipe_scrape,
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
    check(
        "health-column migration allows manual store history mode",
        "'manual'" in ADD_SCRAPER_RUN_HISTORY_HEALTH_COLUMNS_SQL,
        True,
    )
    check(
        "manual-mode migration allows manual store history mode",
        "'manual'" in ALLOW_MANUAL_SCRAPER_RUN_HISTORY_MODE_SQL,
        True,
    )

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

    class FakeStoreScrapeResult:
        status = "success"
        reason = "ssr_ok"
        diagnostics = {
            "raw_product_count": 402,
            "parsed_product_count": 400,
            "skipped_product_count": 2,
            "data_path": "next_data_product_grid",
        }

    kwargs = scrape_result_history_kwargs(FakeStoreScrapeResult(), source_kind="store")
    check("store history kwargs source kind", kwargs["source_kind"], "store")
    check("store history kwargs raw product count", kwargs["candidate_count"], 402)
    check("store history kwargs parsed products", kwargs["parsed_count"], 400)
    check("store history kwargs skipped products", kwargs["filtered_count"], 2)
    check("store history kwargs data path", kwargs["data_path"], "next_data_product_grid")

    async def finish_cancelled_saver_with_diagnostics():
        saver = StreamingRecipeSaver("History Test", overwrite=False)
        return await saver.finish(
            cancelled=True,
            diagnostics={"candidate_url_count": 10, "parser_method": "fixture"},
        )

    stats = asyncio.run(finish_cancelled_saver_with_diagnostics())
    check("streaming saver keeps diagnostics", stats["diagnostics"]["candidate_url_count"], 10)
    check("streaming saver cancelled status", stats["scrape_status"], "cancelled")

    async def finish_blocked_saver():
        saver = StreamingRecipeSaver("History Test", overwrite=True)
        result = RecipeScrapeResult.success(
            [],
            diagnostics={"candidate_url_count": 4},
        )

        def quality_gate_callback(scrape_result):
            scrape_result.diagnostics["quality_gate"] = {
                "should_block": True,
                "reason_code": "recipe_discovery_count_too_low",
            }
            return scrape_result.diagnostics["quality_gate"]

        return await finish_streaming_recipe_scrape(
            saver,
            result,
            quality_gate_callback=quality_gate_callback,
        )

    stats = asyncio.run(finish_blocked_saver())
    check("streaming quality gate blocks finish", stats["scrape_status"], "failed")
    check("streaming quality gate reason", stats["scrape_reason"], "recipe_discovery_count_too_low")
    check("streaming quality gate diagnostics", stats["diagnostics"]["quality_gate"]["should_block"], True)

    print("ALL SCRAPER HISTORY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
