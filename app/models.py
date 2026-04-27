"""
SQLAlchemy models for Deal Meals database.
"""

from sqlalchemy import Column, String, Integer, Numeric, Boolean, Text, DateTime, ForeignKey, CheckConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timezone


def _utcnow():
    """UTC-aware datetime for column defaults (replaces deprecated datetime.utcnow)."""
    return datetime.now(timezone.utc)


Base = declarative_base()


# ============================================================================
# MODELS
# ============================================================================

class Store(Base):
    """Stores (Willys, ICA, Coop, etc) with config and credentials."""
    __tablename__ = "stores"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    name = Column(String(100), nullable=False, unique=True)
    store_type = Column(String(50), nullable=False)
    url = Column(Text)

    # Store configuration (location, ehandel settings, etc.)
    config = Column(JSONB, default=dict)

    # Metadata
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Scrape tracking
    last_scrape_at = Column(DateTime(timezone=True))
    last_scrape_duration_ehandel = Column(Integer)
    last_scrape_duration_butik = Column(Integer)

    # Relationships
    offers = relationship("Offer", back_populates="store", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_stores_type', 'store_type'),
    )

    def __repr__(self):
        return f"<Store(name='{self.name}')>"


class Offer(Base):
    """
    Active sale prices.

    NOTE: This table is cleared every week!
    We do NOT save old price history.
    """
    __tablename__ = "offers"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    store_id = Column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(255), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    original_price = Column(Numeric(10, 2))
    savings = Column(Numeric(10, 2), default=0.0)
    unit = Column(String(20), default="st")
    category = Column(String(100))
    brand = Column(String(100))  # Manufacturer/brand from store API (e.g., "ARLA", "ELDORADO")
    weight_grams = Column(Numeric(10, 1))  # Package weight in grams (from store API "displayVolume")

    # Multi-buy info (e.g., "5 for 55 kr")
    is_multi_buy = Column(Boolean, default=False)
    multi_buy_quantity = Column(Integer)
    multi_buy_total_price = Column(Numeric(10, 2))

    image_url = Column(Text)
    product_url = Column(Text, unique=True)

    scraped_at = Column(DateTime(timezone=True), default=_utcnow)

    # Location info (what was scraped: e-handel or specific store)
    location_type = Column(String(20), default="ehandel")
    location_name = Column(Text)

    # Relationships
    store = relationship("Store", back_populates="offers")

    __table_args__ = (
        CheckConstraint('price > 0', name='chk_price'),
        CheckConstraint('savings >= 0', name='chk_savings'),
        CheckConstraint("location_type IN ('ehandel', 'butik')", name='chk_location_type'),
        CheckConstraint("unit IN ('st', 'kg', 'l', 'förp')", name='chk_unit'),
        CheckConstraint("category IN ('meat', 'poultry', 'fish', 'dairy', 'deli', 'fruit', 'vegetables', 'bread', 'beverages', 'candy', 'spices', 'pizza', 'frozen', 'pantry', 'hygiene', 'household', 'other')", name='chk_category'),
        Index('idx_offers_store', 'store_id'),
        Index('idx_offers_category', 'category'),
        Index('idx_offers_brand', 'brand'),
        Index('idx_offers_scraped', 'scraped_at'),
        Index('idx_offers_location', 'location_type', 'location_name'),
        Index('idx_offers_category_savings', 'category', 'savings', postgresql_where=text('savings > 0')),
    )

    def __repr__(self):
        return f"<Offer(name='{self.name}', price={self.price} {self.unit})>"


class FoundRecipe(Base):
    """Recipes from external recipe sites matched against sale prices."""
    __tablename__ = "found_recipes"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    source_name = Column(String(100))

    name = Column(String(255), nullable=False)
    url = Column(Text, nullable=False, unique=True)
    image_url = Column(Text)
    local_image_path = Column(Text)  # Local path to downloaded image

    ingredients = Column(JSONB)
    prep_time_minutes = Column(Integer)
    servings = Column(Integer)

    # Full-text search vector (auto-populated by DB trigger)
    search_vector = Column(TSVECTOR)

    # Matching against sale offers
    matching_offer_ids = Column(JSONB, default=list)
    match_score = Column(Integer, default=0)
    estimated_savings = Column(Numeric(10, 2), default=0.0)

    scraped_at = Column(DateTime(timezone=True), default=_utcnow)

    # User exclusion - hidden recipes won't show in searches or be re-scraped
    excluded = Column(Boolean, default=False)

    __table_args__ = (
        CheckConstraint('match_score >= 0', name='chk_match_score'),
        Index('idx_found_recipes_source', 'source_name'),
        Index('idx_found_recipes_match_score', 'match_score'),
        Index('idx_found_recipes_scraped', 'scraped_at'),
        Index('idx_found_recipes_excluded', 'excluded', postgresql_where=text('excluded = FALSE OR excluded IS NULL')),
        Index('idx_found_recipes_source_excluded', 'source_name', 'excluded'),
    )

    def __repr__(self):
        return f"<FoundRecipe(name='{self.name}', source='{self.source_name}')>"


class UserPreferences(Base):
    """User settings and preferences."""
    __tablename__ = "user_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    singleton_key = Column(Boolean, nullable=False, server_default=text("TRUE"))
    delivery_street_address = Column(Text)
    delivery_postal_code = Column(Text)
    delivery_city = Column(Text)
    ui_preferences = Column(JSONB, default=dict)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint('singleton_key', name='user_preferences_singleton'),
    )

    def __repr__(self):
        return f"<UserPreferences(id={self.id})>"


class RecipeSource(Base):
    """Configurable recipe sites for scraping."""
    __tablename__ = "recipe_sources"
    __table_args__ = (
        Index("idx_recipe_sources_name_unique", "name", unique=True),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    name = Column(String(100), nullable=False)
    url = Column(Text, nullable=False, unique=True)
    enabled = Column(Boolean, default=True)
    is_starred = Column(Boolean, default=False)  # Favorite sources rank higher

    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def __repr__(self):
        return f"<RecipeSource(name='{self.name}', enabled={self.enabled}, starred={self.is_starred})>"


class MatchingPreferences(Base):
    """User preferences for recipe matching algorithm."""
    __tablename__ = "matching_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    singleton_key = Column(Boolean, nullable=False, server_default=text("TRUE"))

    # Exclude categories (checkboxes in GUI)
    exclude_meat = Column(Boolean, default=False)
    exclude_fish = Column(Boolean, default=False)
    exclude_dairy = Column(Boolean, default=False)

    # Exclude keywords (freetext, stored as JSONB array)
    exclude_keywords = Column(JSONB, default=list)

    # Filtered products (halvfabrikat/processed foods, stored as JSONB array)
    filtered_products = Column(JSONB, default=list)

    # Excluded brands (e.g., ["eldorado", "ica basic", "garant"])
    excluded_brands = Column(JSONB, default=list)

    # Matching/ranking controls
    ranking_mode = Column(Text, default='absolute')
    min_ingredients = Column(Integer, default=0)
    max_ingredients = Column(Integer, default=0)

    # Local meat only filter; country-specific matching decides what local means.
    local_meat_only = Column(Boolean, default=True)

    # Balance weights (0.0 - 1.0)
    balance_meat = Column(Numeric(4, 2), default=0.25)
    balance_fish = Column(Numeric(4, 2), default=0.25)
    balance_veg = Column(Numeric(4, 2), default=0.25)
    balance_budget = Column(Numeric(4, 2), default=0.25)

    # Cache settings
    cache_use_memory = Column(Boolean, default=False)
    cache_max_memory_mb = Column(Integer, default=150)

    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint('singleton_key', name='matching_preferences_singleton'),
        CheckConstraint('balance_meat >= 0 AND balance_meat <= 4', name='chk_balance_meat'),
        CheckConstraint('balance_fish >= 0 AND balance_fish <= 4', name='chk_balance_fish'),
        CheckConstraint('balance_veg >= 0 AND balance_veg <= 4', name='chk_balance_veg'),
        CheckConstraint('balance_budget >= 0 AND balance_budget <= 4', name='chk_balance_budget'),
    )

    def __repr__(self):
        return f"<MatchingPreferences(meat={self.balance_meat}, fish={self.balance_fish}, veg={self.balance_veg}, budget={self.balance_budget})>"


class RecipeOfferCache(Base):
    """
    Pre-computed recipe-offer matches for fast page loads.

    This cache is refreshed when offers are updated (weekly).
    Stores all match data needed for display without re-computing.
    """
    __tablename__ = "recipe_offer_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))

    # Recipe reference
    found_recipe_id = Column(UUID(as_uuid=True), ForeignKey("found_recipes.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Pre-computed match data (JSON with matched_offers, scores, etc)
    match_data = Column(JSONB, nullable=False)

    # Category classification for filtering
    recipe_category = Column(String(20), nullable=False)

    # Key scores for sorting (extracted from match_data)
    budget_score = Column(Numeric(10, 2), default=0.0)
    total_savings = Column(Numeric(10, 2), default=0.0)
    coverage_pct = Column(Numeric(5, 1), default=0.0)
    num_matches = Column(Integer, default=0)

    # Source starred status (denormalized for fast sorting)
    is_starred = Column(Boolean, default=False)

    # Cache metadata
    computed_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    found_recipe = relationship("FoundRecipe")

    __table_args__ = (
        CheckConstraint("recipe_category IN ('meat', 'fish', 'vegetarian', 'smart_buy')", name='chk_recipe_category'),
        Index('idx_recipe_cache_category', 'recipe_category'),
        Index('idx_recipe_cache_budget_score', 'budget_score'),
        Index('idx_recipe_cache_savings', 'total_savings'),
        Index('idx_recipe_cache_computed', 'computed_at'),
        Index('idx_recipe_cache_category_savings', 'recipe_category', 'total_savings'),
    )

    def __repr__(self):
        return f"<RecipeOfferCache(recipe_id={self.found_recipe_id}, category='{self.recipe_category}')>"


class CompiledOfferMatchData(Base):
    """Persistent offer-side IR for cache rebuilds and delta refreshes."""
    __tablename__ = "compiled_offer_match_data"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    offer_id = Column(UUID(as_uuid=True), nullable=False)
    offer_identity_key = Column(String(64), nullable=False, unique=True)
    store_id = Column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)

    compiler_version = Column(String(64), nullable=False)
    offer_match_hash = Column(String(64), nullable=False)
    offer_score_hash = Column(String(64), nullable=False)
    offer_display_hash = Column(String(64), nullable=False)

    source_name = Column(String(255), nullable=False)
    source_category = Column(String(100))
    source_brand = Column(String(100))
    source_weight_grams = Column(Numeric(10, 1))
    source_price = Column(Numeric(10, 2))
    source_original_price = Column(Numeric(10, 2))
    source_savings = Column(Numeric(10, 2))
    source_product_url = Column(Text)
    source_image_url = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)

    compiled_data = Column(JSONB, nullable=False)
    compiled_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    store = relationship("Store")

    __table_args__ = (
        Index('idx_compiled_offer_match_identity', 'offer_identity_key'),
        Index('idx_compiled_offer_match_store', 'store_id'),
        Index('idx_compiled_offer_match_version', 'compiler_version'),
        Index('idx_compiled_offer_match_active', 'is_active'),
        Index('idx_compiled_offer_match_hashes', 'offer_match_hash', 'offer_score_hash'),
    )

    def __repr__(self):
        return f"<CompiledOfferMatchData(offer_id={self.offer_id}, version='{self.compiler_version}')>"


class CompiledRecipeMatchData(Base):
    """Persistent recipe-side IR for cache rebuilds and delta refreshes."""
    __tablename__ = "compiled_recipe_match_data"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    found_recipe_id = Column(UUID(as_uuid=True), ForeignKey("found_recipes.id", ondelete="CASCADE"), nullable=False)
    recipe_identity_key = Column(String(64), nullable=False, unique=True)

    compiler_version = Column(String(64), nullable=False)
    recipe_source_hash = Column(String(64), nullable=False)

    source_name = Column(String(100))
    source_url = Column(Text)
    recipe_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    compiled_data = Column(JSONB, nullable=False)
    compiled_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    found_recipe = relationship("FoundRecipe")

    __table_args__ = (
        Index('idx_compiled_recipe_match_found_recipe', 'found_recipe_id'),
        Index('idx_compiled_recipe_match_identity', 'recipe_identity_key'),
        Index('idx_compiled_recipe_match_version', 'compiler_version'),
        Index('idx_compiled_recipe_match_active', 'is_active'),
        Index('idx_compiled_recipe_match_hash', 'recipe_source_hash'),
    )

    def __repr__(self):
        return (
            f"<CompiledRecipeMatchData(recipe_id={self.found_recipe_id}, "
            f"version='{self.compiler_version}')>"
        )


class CompiledOfferTermIndex(Base):
    """Persistent offer-term postings for candidate routing."""
    __tablename__ = "compiled_offer_term_index"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    offer_id = Column(UUID(as_uuid=True), nullable=False)
    offer_identity_key = Column(String(64), nullable=False)
    store_id = Column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)

    matcher_version = Column(String(64), nullable=False)
    offer_compiler_version = Column(String(64), nullable=False)
    term_manifest_hash = Column(String(64), nullable=False)

    term = Column(String(255), nullable=False)
    term_type = Column(String(40), nullable=False)
    indexed_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    store = relationship("Store")

    __table_args__ = (
        Index('idx_compiled_offer_term_lookup', 'matcher_version', 'offer_compiler_version', 'term'),
        Index('idx_compiled_offer_term_offer', 'matcher_version', 'offer_compiler_version', 'offer_identity_key'),
        Index('idx_compiled_offer_term_manifest', 'term_manifest_hash'),
        UniqueConstraint(
            'offer_identity_key',
            'matcher_version',
            'offer_compiler_version',
            'term_manifest_hash',
            'term',
            'term_type',
            name='uq_compiled_offer_term_entry',
        ),
    )

    def __repr__(self):
        return f"<CompiledOfferTermIndex(offer_id={self.offer_id}, term='{self.term}')>"


class CompiledRecipeTermIndex(Base):
    """Persistent recipe-term postings for candidate routing."""
    __tablename__ = "compiled_recipe_term_index"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    found_recipe_id = Column(UUID(as_uuid=True), nullable=False)
    recipe_identity_key = Column(String(64), nullable=False)

    matcher_version = Column(String(64), nullable=False)
    recipe_compiler_version = Column(String(64), nullable=False)
    term_manifest_hash = Column(String(64), nullable=False)

    term = Column(String(255), nullable=False)
    term_type = Column(String(40), nullable=False)
    indexed_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index('idx_compiled_recipe_term_lookup', 'matcher_version', 'recipe_compiler_version', 'term'),
        Index('idx_compiled_recipe_term_recipe', 'matcher_version', 'recipe_compiler_version', 'recipe_identity_key'),
        Index('idx_compiled_recipe_term_manifest', 'term_manifest_hash'),
        UniqueConstraint(
            'recipe_identity_key',
            'matcher_version',
            'recipe_compiler_version',
            'term_manifest_hash',
            'term',
            'term_type',
            name='uq_compiled_recipe_term_entry',
        ),
    )

    def __repr__(self):
        return f"<CompiledRecipeTermIndex(recipe_id={self.found_recipe_id}, term='{self.term}')>"


class CacheMetadata(Base):
    """Tracks cache computation status and timing."""
    __tablename__ = "cache_metadata"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    cache_name = Column(String(50), nullable=False, unique=True)
    last_computed_at = Column(DateTime(timezone=True))
    computation_time_ms = Column(Integer)
    total_recipes = Column(Integer)
    total_matches = Column(Integer)
    status = Column(String(20), default='pending')  # pending, computing, ready, error
    error_message = Column(Text)
    last_background_rebuild_at = Column(DateTime(timezone=True))
    background_rebuild_source = Column(Text)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'computing', 'ready', 'error')", name='chk_cache_status'),
    )

    def __repr__(self):
        return f"<CacheMetadata(name='{self.cache_name}', status='{self.status}')>"


class ScraperRunHistory(Base):
    """History of scraper run times per scraper/mode for estimating future runs."""
    __tablename__ = "scraper_run_history"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    scraper_id = Column(String(50), nullable=False)
    mode = Column(String(20), nullable=False)  # 'test', 'incremental', 'full'
    duration_seconds = Column(Integer, nullable=False)
    recipes_found = Column(Integer, default=0)
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    run_at = Column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        CheckConstraint("mode IN ('test', 'incremental', 'full')", name='chk_run_history_mode'),
        Index('idx_scraper_run_history_scraper_mode', 'scraper_id', 'mode'),
        Index('idx_scraper_run_history_run_at', 'run_at'),
    )

    def __repr__(self):
        return f"<ScraperRunHistory(scraper={self.scraper_id}, mode={self.mode}, success={self.success})>"


class ImagePreferences(Base):
    """User preferences for recipe image caching."""
    __tablename__ = "image_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    singleton_key = Column(Boolean, nullable=False, server_default=text("TRUE"))
    save_local = Column(Boolean, default=False)
    auto_download = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint('singleton_key', name='image_preferences_singleton'),
    )

    def __repr__(self):
        return f"<ImagePreferences(save_local={self.save_local}, auto_download={self.auto_download})>"


class ScraperSchedule(Base):
    """Schedule configuration for recipe scrapers."""
    __tablename__ = "scraper_schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    scraper_id = Column(String(50), nullable=False, unique=True)
    frequency = Column(String(20), nullable=False)
    day_of_week = Column(Integer)
    day_of_month = Column(Integer)
    hour = Column(Integer, nullable=False)
    timezone = Column(String(50), default='Europe/Stockholm')
    enabled = Column(Boolean, default=True)
    last_run_at = Column(DateTime(timezone=True))
    next_run_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        CheckConstraint("frequency IN ('daily', 'weekly', 'monthly')", name='chk_scraper_frequency'),
        CheckConstraint('day_of_week >= 0 AND day_of_week <= 6', name='chk_scraper_dow'),
        CheckConstraint('day_of_month >= 1 AND day_of_month <= 28', name='chk_scraper_dom'),
        CheckConstraint('hour >= 0 AND hour <= 23', name='chk_scraper_hour'),
    )

    def __repr__(self):
        return f"<ScraperSchedule(scraper={self.scraper_id}, frequency={self.frequency})>"


class StoreSchedule(Base):
    """Schedule configuration for store offer scrapers."""
    __tablename__ = "store_schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    store_id = Column(String(50), nullable=False, unique=True)
    frequency = Column(String(20), nullable=False)
    day_of_week = Column(Integer)
    day_of_month = Column(Integer)
    hour = Column(Integer, nullable=False)
    timezone = Column(String(50), default='Europe/Stockholm')
    enabled = Column(Boolean, default=True)
    config = Column(JSONB, default=dict)
    last_run_at = Column(DateTime(timezone=True))
    next_run_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        CheckConstraint("frequency IN ('daily', 'weekly', 'monthly')", name='chk_store_frequency'),
        CheckConstraint('day_of_week >= 0 AND day_of_week <= 6', name='chk_store_dow'),
        CheckConstraint('day_of_month >= 1 AND day_of_month <= 28', name='chk_store_dom'),
        CheckConstraint('hour >= 0 AND hour <= 23', name='chk_store_hour'),
        Index('idx_store_schedules_enabled_hour_unique', 'hour', unique=True, postgresql_where=text('enabled = true')),
    )

    def __repr__(self):
        return f"<StoreSchedule(store={self.store_id}, frequency={self.frequency})>"


class ImageDownloadFailure(Base):
    """Tracks failed image download attempts for retry logic."""
    __tablename__ = "image_download_failures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(UUID(as_uuid=True), ForeignKey("found_recipes.id", ondelete="CASCADE"), nullable=False)
    image_url = Column(Text, nullable=False)
    image_url_hash = Column(String(32), nullable=False)
    attempt_count = Column(Integer, default=1)
    first_attempt = Column(DateTime(timezone=True), default=_utcnow)
    last_attempt = Column(DateTime(timezone=True), default=_utcnow)
    last_error = Column(Text)
    permanently_failed = Column(Boolean, default=False)

    # Relationships
    recipe = relationship("FoundRecipe")

    __table_args__ = (
        UniqueConstraint('recipe_id', 'image_url_hash', name='uq_image_failures_recipe_hash'),
        Index('idx_image_failures_recipe', 'recipe_id'),
        Index('idx_image_failures_hash', 'image_url_hash'),
        Index('idx_image_failures_permanent', 'permanently_failed', postgresql_where=text('permanently_failed = TRUE')),
    )

    def __repr__(self):
        return f"<ImageDownloadFailure(recipe_id={self.recipe_id}, attempts={self.attempt_count}, permanent={self.permanently_failed})>"


class CustomRecipeUrl(Base):
    """User-managed recipe URLs for the universal 'Mina Recept' scraper."""
    __tablename__ = "custom_recipe_urls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(Text, nullable=False, unique=True)
    label = Column(String(255))
    status = Column(String(20), default='pending')
    retry_count = Column(Integer, default=0)
    last_error = Column(Text)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'ok', 'error', 'no_recipe', 'gave_up')", name='chk_custom_url_status'),
        Index('idx_custom_recipe_urls_status', 'status'),
    )

    def __repr__(self):
        return f"<CustomRecipeUrl(url='{self.url}', status='{self.status}')>"


class SpellCorrection(Base):
    """Tracks ingredient spelling corrections for user review."""
    __tablename__ = "spell_corrections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(UUID(as_uuid=True), ForeignKey("found_recipes.id", ondelete="CASCADE"), nullable=False)
    ingredient_index = Column(Integer, nullable=False)
    original_word = Column(String(100), nullable=False)
    corrected_word = Column(String(100), nullable=False)
    reviewed = Column(Boolean, default=False)
    excluded = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    recipe = relationship("FoundRecipe")

    __table_args__ = (
        Index('idx_spell_corrections_recipe', 'recipe_id'),
        Index('idx_spell_corrections_reviewed', 'reviewed', postgresql_where=text('reviewed = FALSE')),
        Index('idx_spell_corrections_excluded', 'excluded', postgresql_where=text('excluded = TRUE')),
    )

    def __repr__(self):
        return f"<SpellCorrection(recipe_id={self.recipe_id}, '{self.original_word}' -> '{self.corrected_word}')>"
