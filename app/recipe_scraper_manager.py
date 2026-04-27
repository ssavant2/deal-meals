"""
Recipe Scraper Manager

Provides a unified interface for discovering, managing, and running recipe scrapers.
Used by the web API to list scrapers, get status, and trigger scraping.
"""

import os
import importlib.util
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy import text
from loguru import logger

from database import get_db_session

# Scrapers enabled by default for new installations
DEFAULT_ENABLED_SCRAPERS = {'koket', 'myrecipes'}


def fallback_recipe_source_url(source_name: str) -> str:
    """Build a stable placeholder URL for scraper sources without a website."""
    slug = (source_name or "recipe-source").strip().lower().replace(" ", "-")
    return f"https://{slug or 'recipe-source'}"


def recipe_source_registry_url(source_name: str, source_url: str = "") -> str:
    """Return the URL value used for recipe_sources registration."""
    source_url = (source_url or "").strip()
    return source_url or fallback_recipe_source_url(source_name)


@dataclass
class ScraperInfo:
    """Information about a recipe scraper."""
    id: str  # e.g., "recepten", "zeta"
    name: str  # e.g., "Recepten.se"
    description: str
    expected_recipe_count: int
    source_url: str
    module_path: str  # Path to the scraper module
    db_source_name: str = ""  # Name used in database (may differ from display name)
    enabled: bool = True
    warning: str = ""  # Optional warning message for large scrapers

    # Runtime stats (populated from database)
    last_run_at: Optional[datetime] = None
    recipe_count: int = 0
    database_size_kb: float = 0.0


class RecipeScraperManager:
    """
    Discovers and manages recipe scrapers.

    Scrapers are discovered from app/scrapers/recipes/ directory.
    Each scraper must have these module-level constants:
    - SCRAPER_NAME
    - SCRAPER_DESCRIPTION
    - EXPECTED_RECIPE_COUNT
    - SOURCE_URL
    - DB_SOURCE_NAME (optional, defaults to SCRAPER_NAME)

    Recipe requirements (enforced by scrapers):
    - MIN_INGREDIENTS = 3 (skip recipes with fewer)
    - servings optional (UI hides portion count if None)

    See docs/HOW_TO_ADD_SCRAPERS.md for full documentation.
    """

    SCRAPERS_DIR = os.path.join(os.path.dirname(__file__), "scrapers", "recipes")
    # AI scraper has its own custom UI on recipes.html - exclude from auto-discovery
    EXCLUDED_FILES = {"ai_scraper.py"}

    def __init__(self):
        self._scrapers: Dict[str, ScraperInfo] = {}
        self._scraper_classes: Dict[str, Any] = {}
        self._modules: Dict[str, Any] = {}
        self._discover_scrapers()

    def _discover_scrapers(self):
        """Discover all scrapers in the recipes directory."""
        if not os.path.exists(self.SCRAPERS_DIR):
            logger.warning(f"Scrapers directory not found: {self.SCRAPERS_DIR}")
            return

        for filename in os.listdir(self.SCRAPERS_DIR):
            if filename.endswith("_scraper.py") and not filename.startswith("_"):
                if filename in self.EXCLUDED_FILES:
                    logger.debug(f"Skipping excluded scraper: {filename}")
                    continue
                self._load_scraper(filename)

    def _infer_db_source_name(self, display_name: str) -> str:
        """
        Infer the database source_name from the display name.

        Checks the database for existing source names and tries to match.
        Falls back to display name if no match found.
        """
        try:
            with get_db_session() as db:
                result = db.execute(text(
                    "SELECT DISTINCT source_name FROM found_recipes"
                ))
                existing_names = [row.source_name for row in result]

                # Direct match
                if display_name in existing_names:
                    return display_name

                # Try without domain suffix (e.g., "Zeta.nu" -> "Zeta")
                base_name = display_name.split('.')[0]
                if base_name in existing_names:
                    return base_name

                # No match found, use display name
                return display_name
        except Exception as e:
            logger.debug(f"Could not infer db_source_name for '{display_name}': {e}")
            return display_name

    def _load_scraper(self, filename: str):
        """Load a single scraper module and extract its metadata."""
        module_path = os.path.join(self.SCRAPERS_DIR, filename)
        scraper_id = filename.replace("_scraper.py", "")

        try:
            # Load module dynamically
            spec = importlib.util.spec_from_file_location(scraper_id, module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Extract required metadata
            name = getattr(module, "SCRAPER_NAME", None)
            description = getattr(module, "SCRAPER_DESCRIPTION", None)
            expected_count = getattr(module, "EXPECTED_RECIPE_COUNT", 0)
            source_url = getattr(module, "SOURCE_URL", "")
            # DB_SOURCE_NAME is optional - defaults to name without domain suffix
            db_source_name = getattr(module, "DB_SOURCE_NAME", None)
            # SCRAPER_WARNING is optional - for long-running scrapers
            warning = getattr(module, "SCRAPER_WARNING", "")

            if not name:
                logger.warning(f"Scraper {filename} missing SCRAPER_NAME, skipping")
                return

            # If no explicit DB_SOURCE_NAME, try to infer from name
            # "Zeta.nu" -> "Zeta", "Recepten.se" -> "Recepten.se" (check DB)
            if not db_source_name:
                db_source_name = self._infer_db_source_name(name)

            # Find the scraper class (e.g., ReceptenScraper, ZetaScraper)
            scraper_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and "Scraper" in attr_name and attr_name != "Scraper":
                    scraper_class = attr
                    break

            self._scrapers[scraper_id] = ScraperInfo(
                id=scraper_id,
                name=name,
                description=description,
                expected_recipe_count=expected_count,
                source_url=source_url,
                module_path=module_path,
                db_source_name=db_source_name,
                enabled=True,
                warning=warning
            )

            self._modules[scraper_id] = module

            if scraper_class:
                # Validate required interface methods
                required_methods = {'scrape_all_recipes', 'scrape_incremental'}
                missing = {m for m in required_methods if not hasattr(scraper_class, m)}
                if missing:
                    logger.warning(f"Scraper {name} ({scraper_id}) missing methods: {missing}")
                self._scraper_classes[scraper_id] = scraper_class

            logger.info(f"Loaded scraper: {name} ({scraper_id})")

        except Exception as e:
            logger.error(f"Failed to load scraper {filename}: {e}")

    def get_all_scrapers(self) -> List[ScraperInfo]:
        """Get all discovered scrapers with their current stats."""
        scrapers = list(self._scrapers.values())
        self._populate_stats(scrapers)
        return scrapers

    def get_scraper(self, scraper_id: str) -> Optional[ScraperInfo]:
        """Get a specific scraper by ID."""
        scraper = self._scrapers.get(scraper_id)
        if scraper:
            self._populate_stats([scraper])
        return scraper

    def get_enabled_scrapers(self) -> List[ScraperInfo]:
        """Get only enabled scrapers from database."""
        scrapers = []

        with get_db_session() as db:
            result = db.execute(text("""
                SELECT name, enabled FROM recipe_sources
            """))
            enabled_sources = {row.name: row.enabled for row in result}

        for scraper in self._scrapers.values():
            # Use db_source_name for lookup (matches found_recipes.source_name)
            db_name = scraper.db_source_name or scraper.name
            # Check if enabled in database (default: only DEFAULT_ENABLED_SCRAPERS)
            default_enabled = scraper.id in DEFAULT_ENABLED_SCRAPERS
            scraper.enabled = enabled_sources.get(db_name, default_enabled)
            if scraper.enabled:
                scrapers.append(scraper)

        self._populate_stats(scrapers)
        return scrapers

    def get_registry_sources(self) -> List[Dict[str, Any]]:
        """Return discovered scrapers in recipe_sources registry shape."""
        sources = []
        for scraper in self._scrapers.values():
            db_name = scraper.db_source_name or scraper.name
            sources.append({
                "id": scraper.id,
                "name": db_name,
                "url": recipe_source_registry_url(db_name, scraper.source_url),
                "default_enabled": scraper.id in DEFAULT_ENABLED_SCRAPERS,
            })
        return sources

    def ensure_scraper_registered(self, scraper_id: str, *, enabled: Optional[bool] = None) -> bool:
        """Ensure a discovered scraper has a row in recipe_sources."""
        scraper = self._scrapers.get(scraper_id)
        if not scraper:
            return False

        db_name = scraper.db_source_name or scraper.name
        source_url = recipe_source_registry_url(db_name, scraper.source_url)
        insert_enabled = scraper.id in DEFAULT_ENABLED_SCRAPERS if enabled is None else enabled

        with get_db_session() as db:
            db.execute(
                text("""
                    INSERT INTO recipe_sources (name, url, enabled)
                    SELECT :name, :url, :enabled
                    WHERE NOT EXISTS (
                        SELECT 1 FROM recipe_sources
                        WHERE name = :name OR url = :url
                    )
                    ON CONFLICT (url) DO NOTHING
                """),
                {"name": db_name, "url": source_url, "enabled": insert_enabled}
            )
            db.commit()

        return True

    def _populate_stats(self, scrapers: List[ScraperInfo]):
        """Populate runtime statistics from database."""
        if not scrapers:
            return

        with get_db_session() as db:
            # Get recipe counts per source
            result = db.execute(text("""
                SELECT
                    source_name,
                    COUNT(*) as recipe_count
                FROM found_recipes
                GROUP BY source_name
            """))

            stats = {row.source_name: {
                "count": row.recipe_count
            } for row in result}

            # Get last run time from scraper_run_history (exclude test mode - only real runs)
            last_runs = {}
            try:
                result = db.execute(text("""
                    SELECT DISTINCT ON (scraper_id)
                        scraper_id,
                        run_at as last_run
                    FROM scraper_run_history
                    WHERE success = true
                      AND mode != 'test'
                    ORDER BY scraper_id, run_at DESC
                """))
                last_runs = {row.scraper_id: row.last_run for row in result}
            except Exception as e:
                # Table might not exist yet
                logger.debug(f"Could not fetch run history (table may not exist): {e}")

            # Get enabled status from recipe_sources table
            result = db.execute(text("""
                SELECT name, enabled FROM recipe_sources
            """))
            enabled_status = {row.name: row.enabled for row in result}

            # Get database size per source (approximate)
            result = db.execute(text("""
                SELECT
                    source_name,
                    pg_size_pretty(sum(pg_column_size(found_recipes.*))) as size,
                    sum(pg_column_size(found_recipes.*)) as size_bytes
                FROM found_recipes
                GROUP BY source_name
            """))

            sizes = {row.source_name: row.size_bytes or 0 for row in result}

        # Update scrapers with stats - use db_source_name for lookups
        for scraper in scrapers:
            # Use db_source_name for database lookups (e.g., "Zeta" instead of "Zeta.nu")
            lookup_name = scraper.db_source_name or scraper.name
            source_stats = stats.get(lookup_name, {})
            scraper.recipe_count = source_stats.get("count", 0)
            # Get last_run_at from run history (uses scraper.id like "zeta", "recepten")
            scraper.last_run_at = last_runs.get(scraper.id)
            scraper.database_size_kb = sizes.get(lookup_name, 0) / 1024
            # For enabled status, check both display name and db_source_name
            default_enabled = scraper.id in DEFAULT_ENABLED_SCRAPERS
            scraper.enabled = enabled_status.get(scraper.name, enabled_status.get(lookup_name, default_enabled))

    def set_scraper_enabled(self, scraper_id: str, enabled: bool) -> bool:
        """Enable or disable a scraper in the database."""
        scraper = self._scrapers.get(scraper_id)
        if not scraper:
            return False

        # Use db_source_name for database operations (this matches found_recipes.source_name)
        db_name = scraper.db_source_name or scraper.name

        with get_db_session() as db:
            result = db.execute(
                text("""
                    UPDATE recipe_sources
                    SET enabled = :enabled, updated_at = NOW()
                    WHERE name = :name
                """),
                {"enabled": enabled, "name": db_name}
            )
            db.commit()

            if result.rowcount == 0:
                # Source doesn't exist in DB, insert it
                db.execute(
                    text("""
                        INSERT INTO recipe_sources (name, url, enabled)
                        SELECT :name, :url, :enabled
                        WHERE NOT EXISTS (
                            SELECT 1 FROM recipe_sources
                            WHERE name = :name OR url = :url
                        )
                        ON CONFLICT (url) DO NOTHING
                    """),
                    {
                        "name": db_name,
                        "url": recipe_source_registry_url(db_name, scraper.source_url),
                        "enabled": enabled,
                    }
                )
                db.commit()

        scraper.enabled = enabled
        return True

    def get_scraper_class(self, scraper_id: str):
        """Get the scraper class for running."""
        return self._scraper_classes.get(scraper_id)

    def get_module(self, scraper_id: str):
        """Get the loaded module for a scraper (avoids __import__ with user input)."""
        return self._modules.get(scraper_id)


# Singleton instance
scraper_manager = RecipeScraperManager()
