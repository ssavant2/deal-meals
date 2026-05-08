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
        description=(
            "Maximum process-pool workers for cache rebuilds. The db_candidates "
            "path is designed for up to 3 workers under the 1536 MiB web limit; "
            "the legacy term_index subprocess path is still forced single-worker."
        ),
    )
    cache_delta_verification_max_workers: int = Field(
        default=3,
        description=(
            "Maximum process-pool workers for delta verification previews; "
            "capped by detected cores and an internal maximum of 3, independent "
            "of cache_rebuild_max_workers."
        ),
    )
    cache_rebuild_subprocess_enabled: bool = Field(
        default=True,
        description=(
            "Run async full cache rebuilds in a separate Python subprocess so "
            "CPU-bound matching does not contend with the web event loop GIL."
        ),
    )
    cache_rebuild_process_pool_enabled: bool = Field(
        default=True,
        description=(
            "Allow full cache rebuilds to use a forked process pool. The async "
            "subprocess worker only keeps this enabled for the db_candidates "
            "path; the legacy term_index path remains single-worker."
        ),
    )
    cache_rebuild_candidate_data_source: str = Field(
        default="db_candidates",
        description=(
            "Candidate routing input for full cache rebuilds: db_candidates "
            "(chunked scoring from compiled_recipe_offer_candidates) or "
            "term_index (legacy fallback)."
        ),
    )
    cache_startup_background_rebuild_enabled: bool = Field(
        default=False,
        description=(
            "Run a full recipe-offer cache rebuild automatically after web "
            "startup. Disabled by default so restarts stay responsive; scrapes "
            "and manual cache reset still refresh the cache."
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
        default=0,
        description=(
            "Minimum consecutive ready offer-delta probation runs before runtime "
            "delta may skip full preview. Defaults to zero because small "
            "offer-deltas are verified by patch-preview only; larger offer "
            "changes fall back to the full rebuild subprocess."
        ),
    )
    cache_delta_probation_min_version_ready_runs: int = Field(
        default=0,
        description=(
            "Minimum ready offer-delta probation runs for the current version "
            "triple before skipping full preview"
        ),
    )
    offer_refresh_decision_enabled: bool = Field(
        default=True,
        description=(
            "Enable stable offer-diff decisions before offer-triggered cache refreshes"
        ),
    )
    offer_delta_impacted_recipe_ratio_full_threshold_pct: float = Field(
        default=15.0,
        description=(
            "Maximum impacted active-recipe percentage for offer-delta before "
            "choosing a direct full rebuild"
        ),
    )
    offer_delta_changed_offer_ratio_early_full_threshold_pct: float = Field(
        default=50.0,
        description=(
            "Changed-offer percentage used as a safety valve when offer-impact "
            "estimation is unavailable or fails"
        ),
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
        default=0,
        description=(
            "Minimum consecutive ready recipe-delta probation runs before "
            "skipping full preview. Defaults to zero because small recipe "
            "deltas are verified by patch-preview only; larger recipe changes "
            "fall back to the full rebuild subprocess."
        ),
    )
    cache_recipe_delta_probation_min_version_ready_runs: int = Field(
        default=0,
        description=(
            "Minimum ready recipe-delta probation runs for the current version "
            "triple before skipping full preview"
        ),
    )
    cache_recipe_delta_skip_full_preview_max_affected_ratio: float = Field(
        default=0.05,
        description=(
            "Maximum affected/active recipe ratio that may skip recipe-delta "
            "full-preview after probation. Larger deltas may still use recipe-"
            "delta, but keep full-preview verification."
        ),
    )
    cache_recipe_delta_max_affected_ratio: float = Field(
        default=0.05,
        description=(
            "Maximum fraction of active recipes a recipe scrape may affect before "
            "falling back to a full cache rebuild"
        ),
    )
    pantry_search_term_index_enabled: bool = Field(
        default=True,
        description="Use the compiled pantry search-term index for /api/pantry-match",
    )
    pantry_search_startup_refresh_enabled: bool = Field(
        default=True,
        description=(
            "Refresh the pantry search-term index automatically after web startup. "
            "Runs in the background so startup stays responsive; pantry falls back "
            "to the legacy path while the index is stale."
        ),
    )
    pantry_search_term_index_shadow_logging_enabled: bool = Field(
        default=False,
        description="Log pantry search-term index diagnostics while keeping legacy results",
    )
    pantry_search_term_index_max_candidates: int = Field(
        default=0,
        description=(
            "Optional hard safety cap for pantry search-term index candidates. "
            "0 means no extra cap beyond the active pantry scope."
        ),
    )
    cache_reconciliation_enabled: bool = Field(
        default=True,
        description="Run occasional full cache rebuilds after scheduled jobs as a drift check",
    )
    cache_reconciliation_min_age_days: int = Field(
        default=7,
        description="Minimum age of the last full cache rebuild before scheduled reconciliation is due",
    )
    cache_reconciliation_max_incremental_operations: int = Field(
        default=25,
        description=(
            "Maximum ready delta/skip cache operations after the last full rebuild "
            "before scheduled reconciliation is due. 0 disables the count trigger."
        ),
    )
    cache_reconciliation_inactive_minutes: int = Field(
        default=15,
        description=(
            "Minimum time since likely user activity before scheduled reconciliation may run"
        ),
    )
    # Cache rebuild / ingredient routing phase 2
    cache_ingredient_routing_mode: str = Field(
        default="off",
        description=(
            "Ingredient routing runtime mode: off or hint_first. Default off "
            "keeps full rebuild memory low; deprecated shadow/probation values "
            "are treated as off."
        ),
    )


# Global settings instance
settings = Settings()
