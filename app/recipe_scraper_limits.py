"""Shared recipe scraper fetch-limit helpers."""

from __future__ import annotations

from loguru import logger
from sqlalchemy import text

from database import get_db_session


DEFAULT_MAX_RECIPES = 50
UNLIMITED_SCRAPERS = {"myrecipes"}


def get_scraper_configs() -> dict:
    """Return stored per-scraper fetch limits keyed by scraper id."""
    try:
        with get_db_session() as db:
            result = db.execute(
                text(
                    """
                    SELECT scraper_id, max_recipes_full, max_recipes_incremental
                    FROM scraper_config
                    """
                )
            )
            return {
                row.scraper_id: {
                    "max_recipes_full": row.max_recipes_full,
                    "max_recipes_incremental": row.max_recipes_incremental,
                    "_has_config": True,
                }
                for row in result
            }
    except Exception as e:
        logger.debug(f"Could not fetch scraper configs (table may not exist): {e}")
        return {}


def get_effective_config(scraper_id: str, configs: dict) -> tuple[int | None, int | None]:
    """Return (max_full, max_incremental), applying defaults for unconfigured sources."""
    config = configs.get(scraper_id, {})
    if config.get("_has_config"):
        return config.get("max_recipes_full"), config.get("max_recipes_incremental")
    if scraper_id in UNLIMITED_SCRAPERS:
        return None, None
    return DEFAULT_MAX_RECIPES, DEFAULT_MAX_RECIPES


def get_effective_config_for_scraper(scraper_id: str) -> tuple[int | None, int | None]:
    """Fetch and return the effective limits for one scraper."""
    return get_effective_config(scraper_id, get_scraper_configs())
