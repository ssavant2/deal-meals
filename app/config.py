"""
Application configuration.

Reads environment variables from .env file and validates them.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: PostgresDsn = Field(
        ...,
        description="PostgreSQL connection string"
    )

    # Rate Limiting (values use 'limits' library format: "N/minute", "N/hour", etc.)
    rate_limit_enabled: bool = Field(default=True, description="Enable/disable rate limiting")
    rate_limit_global: str = Field(default="120/minute", description="Global default for all endpoints")
    rate_limit_scraper_run: str = Field(default="3/minute", description="Starting recipe scrapers")
    rate_limit_image_download: str = Field(default="2/minute", description="Starting image downloads")
    rate_limit_heavy_compute: str = Field(default="20/minute", description="Heavy computation endpoints")
    rate_limit_search: str = Field(default="30/minute", description="Search endpoints")
    rate_limit_pantry: str = Field(default="10/minute", description="Pantry match endpoint")

    # Web Server
    debug: bool = Field(default=False, description="Debug mode")

    # Cache rebuild / worker pool
    cache_rebuild_max_workers: int = Field(
        default=3,
        description="Maximum process-pool workers for cache rebuilds",
    )
    cache_delta_verification_max_workers: int = Field(
        default=3,
        description=(
            "Maximum process-pool workers for snapshot-heavy delta verification "
            "previews; also capped by cache_rebuild_max_workers and detected cores"
        ),
    )

    # Cache rebuild / delta
    cache_delta_enabled: bool = Field(
        default=True,
        description="Enable verified delta apply for offer-refresh rebuilds",
    )
    cache_delta_verify_full_preview: bool = Field(
        default=True,
        description="Verify delta patches against a full compiled preview before applying",
    )
    cache_delta_skip_full_preview_after_probation: bool = Field(
        default=True,
        description="Allow delta apply to skip the full preview once probation history is green enough",
    )
    cache_delta_probation_history_file: str | None = Field(
        default=None,
        description="Optional JSONL probation history path used by runtime delta gating",
    )
    cache_delta_probation_min_ready_streak: int = Field(
        default=3,
        description="Minimum consecutive ready probation runs before runtime delta may skip full preview",
    )
    cache_delta_probation_min_version_ready_runs: int = Field(
        default=3,
        description="Minimum ready probation runs for the current version triple before skipping full preview",
    )
    cache_recipe_delta_enabled: bool = Field(
        default=True,
        description="Enable recipe-driven delta apply after recipe scraper changes",
    )
    cache_recipe_delta_verify_full_preview: bool = Field(
        default=True,
        description="Verify recipe-delta patches against a full compiled preview before applying",
    )
    cache_recipe_delta_skip_full_preview_after_probation: bool = Field(
        default=True,
        description="Allow recipe-delta apply to skip full preview once probation history is green enough",
    )
    cache_recipe_delta_probation_history_file: str | None = Field(
        default=None,
        description="Optional separate JSONL probation history path for recipe-delta runtime gating",
    )
    cache_recipe_delta_probation_min_ready_streak: int = Field(
        default=3,
        description="Minimum consecutive ready recipe-delta probation runs before skipping full preview",
    )
    cache_recipe_delta_probation_min_version_ready_runs: int = Field(
        default=3,
        description="Minimum ready recipe-delta probation runs for the current version triple",
    )

    # Cache rebuild / ingredient routing phase 2
    cache_ingredient_routing_mode: str = Field(
        default="hint_first",
        description=(
            "Ingredient routing runtime mode: off, shadow, probation, or hint_first. "
            "hint_first falls back to probation until its safety gate is ready."
        ),
    )
    cache_ingredient_routing_probation_history_file: str | None = Field(
        default=None,
        description="Optional JSONL probation history path used by ingredient-routing gating",
    )
    cache_ingredient_routing_probation_min_ready_streak: int = Field(
        default=3,
        description="Minimum consecutive clean ingredient-routing probation runs before hint_first may run",
    )
    cache_ingredient_routing_probation_min_version_ready_runs: int = Field(
        default=3,
        description="Minimum clean ingredient-routing probation runs for the current version tuple",
    )
    cache_ingredient_routing_probation_recommended_distinct_versions: int = Field(
        default=3,
        description="Recommended distinct clean matcher/compiler version tuples before production hint_first",
    )


# Global settings instance
settings = Settings()
