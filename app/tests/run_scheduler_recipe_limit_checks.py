#!/usr/bin/env python3
"""Checks for scheduled recipe scraper fetch limits."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

import scheduler as scheduler_module  # noqa: E402
from recipe_scraper_limits import get_effective_config  # noqa: E402
from scheduler import ScraperScheduler  # noqa: E402


def check(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"OK {name}")


def check_effective_limits() -> None:
    check("unconfigured scraper defaults to 50", get_effective_config("arla", {}), (50, 50))
    check("myrecipes defaults to unlimited", get_effective_config("myrecipes", {}), (None, None))
    check(
        "configured values are respected",
        get_effective_config(
            "mathem",
            {
                "mathem": {
                    "_has_config": True,
                    "max_recipes_full": 500,
                    "max_recipes_incremental": 17,
                }
            },
        ),
        (500, 17),
    )
    check(
        "configured null means all",
        get_effective_config(
            "ica",
            {
                "ica": {
                    "_has_config": True,
                    "max_recipes_full": None,
                    "max_recipes_incremental": None,
                }
            },
        ),
        (None, None),
    )


class FakeScraper:
    calls: list[dict] = []
    cancelled = False

    def __init__(self):
        self._progress = {"current": 0}
        self._progress_callback = None

    def set_progress_callback(self, callback):
        self._progress_callback = callback

    def cancel(self):
        FakeScraper.cancelled = True

    async def scrape_and_save(self, *, overwrite=False, max_recipes=None):
        FakeScraper.calls.append({"overwrite": overwrite, "max_recipes": max_recipes})
        self._progress = {"current": 7}
        if self._progress_callback:
            await self._progress_callback({"current": 7})
        return {
            "created": 2,
            "scrape_status": "success",
            "changed_recipe_ids": ["recipe-1", "recipe-2"],
        }

    async def scrape_incremental(self):
        raise AssertionError("scheduled runs should prefer scrape_and_save when available")


class FakeScraperManager:
    def get_scraper_class(self, scraper_id):
        return FakeScraper if scraper_id == "fake" else None

    def get_scraper(self, scraper_id):
        return SimpleNamespace(name="Fake", db_source_name="Fake")


async def check_scheduler_passes_incremental_limit() -> None:
    FakeScraper.calls = []
    fake_module = SimpleNamespace(scraper_manager=FakeScraperManager())
    original_manager_module = sys.modules.get("recipe_scraper_manager")
    original_save_run_history = scheduler_module.save_run_history
    run_history_calls = []

    try:
        sys.modules["recipe_scraper_manager"] = fake_module
        scheduler_module.save_run_history = lambda *args, **kwargs: run_history_calls.append((args, kwargs))

        instance = ScraperScheduler()
        instance._update_last_run = lambda scraper_id: None
        instance._update_next_run = lambda scraper_id, next_run: None

        found = await instance._execute_scraper(
            "fake",
            scraper_configs={
                "fake": {
                    "_has_config": True,
                    "max_recipes_full": 100,
                    "max_recipes_incremental": 17,
                }
            },
        )
    finally:
        scheduler_module.save_run_history = original_save_run_history
        if original_manager_module is None:
            sys.modules.pop("recipe_scraper_manager", None)
        else:
            sys.modules["recipe_scraper_manager"] = original_manager_module

    check("scheduled scrape returns created count", found, 2)
    check("scheduled scrape passes incremental limit", FakeScraper.calls, [
        {"overwrite": False, "max_recipes": 17}
    ])
    check("scheduled scrape records cache changes", instance._batch_has_cache_changes, True)
    check("scheduled scrape records new recipes", instance._batch_has_new_recipes, True)
    check("scheduled scrape history attempted count", run_history_calls[0][1]["attempted_count"], 7)


def check_scheduler_cancel_state() -> None:
    FakeScraper.cancelled = False
    instance = ScraperScheduler()
    instance._recipe_schedule_status = {"running": True, "status": "running"}
    instance._current_recipe_scraper = FakeScraper()

    check("scheduled cancel accepted", instance.cancel_recipe_schedule(), True)
    check("scheduled cancel signalled scraper", FakeScraper.cancelled, True)
    check("scheduled cancel requested", instance._recipe_schedule_cancel_requested, True)
    check("scheduled cancel status", instance.get_recipe_schedule_status()["status"], "cancelling")


def main() -> int:
    check_effective_limits()
    asyncio.run(check_scheduler_passes_incremental_limit())
    check_scheduler_cancel_state()
    print("ALL SCHEDULER RECIPE LIMIT CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
