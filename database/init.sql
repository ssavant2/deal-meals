-- ============================================================================
-- DEAL MEALS DATABASE SCHEMA (v1.0)
-- Consolidated from pg_dump on 2026-02-08.
-- This is the single source of truth for fresh installs.
-- ============================================================================

-- UUID: PG18 has built-in uuidv7(). Keep uuid-ossp for backwards compat with dumps.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- STORES
-- ============================================================================
CREATE TABLE stores (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    name VARCHAR(100) NOT NULL UNIQUE,
    store_type VARCHAR(50) NOT NULL,
    url TEXT,
    config JSONB DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_scrape_at TIMESTAMPTZ,
    last_scrape_duration_ehandel INTEGER,
    last_scrape_duration_butik INTEGER
);

CREATE INDEX idx_stores_type ON stores(store_type);
CREATE INDEX idx_stores_config ON stores USING GIN(config);

COMMENT ON TABLE stores IS 'Configurable store sites for scraping';

-- ============================================================================
-- OFFERS - Active sale prices only (cleared weekly)
-- ============================================================================
CREATE TABLE offers (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    store_id UUID REFERENCES stores(id) ON DELETE CASCADE NOT NULL,

    name VARCHAR(255) NOT NULL,
    price NUMERIC(10,2) NOT NULL,
    original_price NUMERIC(10,2),
    savings NUMERIC(10,2) DEFAULT 0.0,
    unit VARCHAR(20) DEFAULT 'st',
    category VARCHAR(100),
    brand VARCHAR(100),
    weight_grams NUMERIC(10,1),      -- Package weight in grams (from store API)

    image_url TEXT,
    product_url TEXT UNIQUE,

    scraped_at TIMESTAMPTZ DEFAULT NOW(),

    -- Multi-buy campaigns (e.g., "5 for 55 kr")
    is_multi_buy BOOLEAN DEFAULT false,
    multi_buy_quantity INTEGER,
    multi_buy_total_price NUMERIC(10,2),

    -- Location tracking
    location_type VARCHAR(20) DEFAULT 'ehandel',
    location_name TEXT,

    CONSTRAINT chk_price CHECK (price > 0),
    CONSTRAINT chk_savings CHECK (savings >= 0),
    CONSTRAINT chk_location_type CHECK (location_type IN ('ehandel', 'butik')),
    CONSTRAINT chk_unit CHECK (unit IN ('st', 'kg', 'l', 'förp')),
    CONSTRAINT chk_category CHECK (category IN (
        'meat', 'poultry', 'fish', 'dairy', 'deli',
        'fruit', 'vegetables', 'bread', 'beverages',
        'candy', 'spices', 'pizza', 'frozen', 'pantry',
        'hygiene', 'household', 'other'
    ))
);

CREATE INDEX idx_offers_store ON offers(store_id);
CREATE INDEX idx_offers_brand ON offers(brand);
CREATE INDEX idx_offers_scraped ON offers(scraped_at DESC);
CREATE INDEX idx_offers_location ON offers(location_type, location_name);
CREATE INDEX idx_offers_category_savings ON offers(category, savings DESC) WHERE savings > 0;

COMMENT ON TABLE offers IS 'Active sale prices - cleared weekly';
COMMENT ON COLUMN offers.is_multi_buy IS 'True if this is a "X for Y kr" campaign';
COMMENT ON COLUMN offers.multi_buy_quantity IS 'Quantity required (e.g., 5 in "5 for 55 kr")';
COMMENT ON COLUMN offers.multi_buy_total_price IS 'Total price for the bundle (e.g., 55 kr)';
COMMENT ON COLUMN offers.location_type IS 'Offer type: ehandel or physical';
COMMENT ON COLUMN offers.location_name IS 'E.g., "E-commerce Gothenburg" or "Willys Kungsbacka Hede"';

-- ============================================================================
-- FOUND_RECIPES - Recipes from external recipe sites
-- ============================================================================

-- Full-text search config for persisted recipe search vectors.
-- Defaults to Swedish, but can be overridden by starting Postgres with:
--   -c deal_meals.recipe_fts_config=<postgres-regconfig>
-- Keep this aligned with the app/matcher RECIPE_FTS_CONFIG setting.
CREATE FUNCTION deal_meals_recipe_fts_config() RETURNS regconfig
    LANGUAGE sql
    STABLE
AS $$
    SELECT COALESCE(
        NULLIF(current_setting('deal_meals.recipe_fts_config', true), ''),
        'swedish'
    )::regconfig;
$$;

-- Full-text search trigger function
CREATE FUNCTION found_recipes_search_vector_update() RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector(deal_meals_recipe_fts_config(), COALESCE(NEW.name, '')), 'A') ||
        setweight(to_tsvector(deal_meals_recipe_fts_config(), COALESCE(
            array_to_string(
                ARRAY(SELECT jsonb_array_elements_text(NEW.ingredients)),
                ' '
            ), ''
        )), 'B');
    RETURN NEW;
END;
$$;

CREATE TABLE found_recipes (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    source_name VARCHAR(100),

    name VARCHAR(255) NOT NULL,
    url TEXT NOT NULL UNIQUE,
    image_url TEXT,
    local_image_path TEXT,

    ingredients JSONB,
    prep_time_minutes INTEGER,
    servings INTEGER,

    -- Matching against sale offers
    matching_offer_ids JSONB DEFAULT '[]',
    match_score INTEGER DEFAULT 0,
    estimated_savings NUMERIC(10,2) DEFAULT 0.0,

    scraped_at TIMESTAMPTZ DEFAULT NOW(),
    search_vector TSVECTOR,

    -- Recipe exclusion (hide from UI)
    excluded BOOLEAN DEFAULT false,

    CONSTRAINT chk_match_score CHECK (match_score >= 0)
);

CREATE INDEX idx_found_recipes_source ON found_recipes(source_name);
CREATE INDEX idx_found_recipes_match_score ON found_recipes(match_score DESC);
CREATE INDEX idx_found_recipes_scraped ON found_recipes(scraped_at DESC);
CREATE INDEX idx_found_recipes_fts ON found_recipes USING GIN(search_vector);
CREATE INDEX idx_found_recipes_excluded ON found_recipes(excluded) WHERE excluded = FALSE OR excluded IS NULL;
CREATE INDEX idx_found_recipes_source_excluded ON found_recipes(source_name, excluded);

CREATE TRIGGER update_found_recipes_search_vector
    BEFORE INSERT OR UPDATE ON found_recipes
    FOR EACH ROW EXECUTE FUNCTION found_recipes_search_vector_update();

COMMENT ON TABLE found_recipes IS 'Recipes from external recipe sites matched against sale offers';

-- ============================================================================
-- IMAGE_DOWNLOAD_FAILURES - Retry tracking for recipe images
-- ============================================================================
CREATE TABLE image_download_failures (
    id SERIAL PRIMARY KEY,
    recipe_id UUID NOT NULL REFERENCES found_recipes(id) ON DELETE CASCADE,
    image_url TEXT NOT NULL,
    image_url_hash VARCHAR(32) NOT NULL,
    attempt_count INTEGER DEFAULT 1,
    first_attempt TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    last_attempt TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    last_error TEXT,
    permanently_failed BOOLEAN DEFAULT false,
    UNIQUE(recipe_id, image_url_hash)
);

CREATE INDEX idx_image_failures_recipe ON image_download_failures(recipe_id);
CREATE INDEX idx_image_failures_hash ON image_download_failures(image_url_hash);
CREATE INDEX idx_image_failures_permanent ON image_download_failures(permanently_failed)
    WHERE permanently_failed = TRUE;

COMMENT ON TABLE image_download_failures IS 'Tracks failed image download attempts for retry logic';
COMMENT ON COLUMN image_download_failures.attempt_count IS 'Total attempts across all download sessions';
COMMENT ON COLUMN image_download_failures.permanently_failed IS 'True after 5 failed attempts - never retry';

-- ============================================================================
-- EXCLUDED_RECIPE_URLS - Permanently blocked recipe URLs (won't be re-scraped)
-- ============================================================================
CREATE TABLE excluded_recipe_urls (
    id SERIAL PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    source_name VARCHAR(100),
    recipe_name VARCHAR(255),
    excluded_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE excluded_recipe_urls IS 'URLs permanently excluded from recipe scraping (deleted duplicates etc)';

-- ============================================================================
-- IMAGE_PREFERENCES
-- ============================================================================
CREATE TABLE image_preferences (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    singleton_key BOOLEAN NOT NULL DEFAULT TRUE,
    save_local BOOLEAN DEFAULT false,
    auto_download BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT image_preferences_singleton UNIQUE (singleton_key)
);

COMMENT ON TABLE image_preferences IS 'User preferences for recipe image caching';

-- ============================================================================
-- MATCHING_PREFERENCES - Recipe matching algorithm settings
-- ============================================================================
CREATE TABLE matching_preferences (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    singleton_key BOOLEAN NOT NULL DEFAULT TRUE,
    exclude_meat BOOLEAN DEFAULT false,
    exclude_fish BOOLEAN DEFAULT false,
    exclude_dairy BOOLEAN DEFAULT false,
    exclude_keywords JSONB DEFAULT '[]',
    local_meat_only BOOLEAN DEFAULT true,
    balance_meat NUMERIC(4,2) DEFAULT 0.25,
    balance_fish NUMERIC(4,2) DEFAULT 0.25,
    balance_veg NUMERIC(4,2) DEFAULT 0.25,
    balance_budget NUMERIC(4,2) DEFAULT 0.25,
    filtered_products JSONB DEFAULT '[]',
    excluded_brands JSONB DEFAULT '[]',
    ranking_mode TEXT DEFAULT 'absolute',
    min_ingredients INTEGER DEFAULT 0,
    max_ingredients INTEGER DEFAULT 0,
    cache_use_memory BOOLEAN DEFAULT false,
    cache_max_memory_mb INTEGER DEFAULT 150,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT matching_preferences_singleton UNIQUE (singleton_key),
    CONSTRAINT chk_balance_meat CHECK (balance_meat >= 0 AND balance_meat <= 4),
    CONSTRAINT chk_balance_fish CHECK (balance_fish >= 0 AND balance_fish <= 4),
    CONSTRAINT chk_balance_veg CHECK (balance_veg >= 0 AND balance_veg <= 4),
    CONSTRAINT chk_balance_budget CHECK (balance_budget >= 0 AND balance_budget <= 4)
);

COMMENT ON TABLE matching_preferences IS 'User preferences for recipe matching algorithm';

-- ============================================================================
-- USER_PREFERENCES - General user settings
-- ============================================================================
CREATE TABLE user_preferences (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    singleton_key BOOLEAN NOT NULL DEFAULT TRUE,
    delivery_street_address TEXT,
    delivery_postal_code TEXT,
    delivery_city TEXT,
    ui_preferences JSONB DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT user_preferences_singleton UNIQUE (singleton_key)
);

COMMENT ON TABLE user_preferences IS 'User settings and preferences';
COMMENT ON COLUMN user_preferences.delivery_street_address IS 'Street address for e-commerce delivery';
COMMENT ON COLUMN user_preferences.delivery_postal_code IS 'Postal code for e-commerce delivery';
COMMENT ON COLUMN user_preferences.delivery_city IS 'City for e-commerce delivery';

-- ============================================================================
-- RECIPE_SOURCES - Configurable recipe sites
-- ============================================================================
CREATE TABLE recipe_sources (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    name VARCHAR(100) NOT NULL,
    url TEXT NOT NULL UNIQUE,
    enabled BOOLEAN DEFAULT true,
    is_starred BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE recipe_sources IS 'Configurable recipe sites for scraping';
CREATE UNIQUE INDEX idx_recipe_sources_name_unique ON recipe_sources(name);

-- ============================================================================
-- RECIPE_OFFER_CACHE - Pre-computed recipe-offer matches
-- ============================================================================
CREATE TABLE recipe_offer_cache (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    found_recipe_id UUID NOT NULL REFERENCES found_recipes(id) ON DELETE CASCADE,
    match_data JSONB NOT NULL,
    recipe_category VARCHAR(20) NOT NULL CHECK (recipe_category IN ('meat', 'fish', 'vegetarian', 'smart_buy')),
    budget_score NUMERIC(10,2) DEFAULT 0.0,
    total_savings NUMERIC(10,2) DEFAULT 0.0,
    coverage_pct NUMERIC(5,1) DEFAULT 0.0,
    num_matches INTEGER DEFAULT 0,
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    is_starred BOOLEAN DEFAULT false,
    UNIQUE(found_recipe_id)
);

CREATE INDEX idx_recipe_cache_budget_score ON recipe_offer_cache(budget_score DESC);
CREATE INDEX idx_recipe_cache_computed ON recipe_offer_cache(computed_at DESC);
CREATE INDEX idx_recipe_cache_category_savings ON recipe_offer_cache(recipe_category, total_savings DESC);

COMMENT ON TABLE recipe_offer_cache IS 'Pre-computed recipe-offer matches for fast page loads';
COMMENT ON COLUMN recipe_offer_cache.match_data IS 'Full match data JSON: matched_offers, scores, etc';

-- ============================================================================
-- COMPILED_OFFER_MATCH_DATA - Persistent offer-side IR for cache rebuilds
-- ============================================================================
CREATE TABLE compiled_offer_match_data (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    offer_id UUID NOT NULL,
    offer_identity_key VARCHAR(64) NOT NULL UNIQUE,
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    compiler_version VARCHAR(64) NOT NULL,
    offer_match_hash VARCHAR(64) NOT NULL,
    offer_score_hash VARCHAR(64) NOT NULL,
    offer_display_hash VARCHAR(64) NOT NULL,
    source_name VARCHAR(255) NOT NULL,
    source_category VARCHAR(100),
    source_brand VARCHAR(100),
    source_weight_grams NUMERIC(10,1),
    source_price NUMERIC(10,2),
    source_original_price NUMERIC(10,2),
    source_savings NUMERIC(10,2),
    source_product_url TEXT,
    source_image_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    compiled_data JSONB NOT NULL,
    compiled_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_compiled_offer_match_identity ON compiled_offer_match_data(offer_identity_key);
CREATE INDEX idx_compiled_offer_match_store ON compiled_offer_match_data(store_id);
CREATE INDEX idx_compiled_offer_match_version ON compiled_offer_match_data(compiler_version);
CREATE INDEX idx_compiled_offer_match_active ON compiled_offer_match_data(is_active);
CREATE INDEX idx_compiled_offer_match_hashes ON compiled_offer_match_data(offer_match_hash, offer_score_hash);

COMMENT ON TABLE compiled_offer_match_data IS 'Persistent offer-side IR for cache rebuilds and delta refreshes';
COMMENT ON COLUMN compiled_offer_match_data.compiled_data IS 'Current compiled offer payload used by recipe-offer matching';

-- ============================================================================
-- COMPILED_RECIPE_MATCH_DATA - Persistent recipe-side IR for cache rebuilds
-- ============================================================================
CREATE TABLE compiled_recipe_match_data (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    found_recipe_id UUID NOT NULL REFERENCES found_recipes(id) ON DELETE CASCADE,
    recipe_identity_key VARCHAR(64) NOT NULL UNIQUE,
    compiler_version VARCHAR(64) NOT NULL,
    recipe_source_hash VARCHAR(64) NOT NULL,
    source_name VARCHAR(100),
    source_url TEXT,
    recipe_name VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    compiled_data JSONB NOT NULL,
    compiled_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_compiled_recipe_match_found_recipe ON compiled_recipe_match_data(found_recipe_id);
CREATE INDEX idx_compiled_recipe_match_identity ON compiled_recipe_match_data(recipe_identity_key);
CREATE INDEX idx_compiled_recipe_match_version ON compiled_recipe_match_data(compiler_version);
CREATE INDEX idx_compiled_recipe_match_active ON compiled_recipe_match_data(is_active);
CREATE INDEX idx_compiled_recipe_match_hash ON compiled_recipe_match_data(recipe_source_hash);

COMMENT ON TABLE compiled_recipe_match_data IS 'Persistent recipe-side IR for cache rebuilds and delta refreshes';
COMMENT ON COLUMN compiled_recipe_match_data.compiled_data IS 'Prepared recipe-side matcher inputs used by recipe-offer matching';

-- ============================================================================
-- COMPILED_OFFER_TERM_INDEX - Persistent offer-term postings for candidate routing
-- ============================================================================
CREATE TABLE compiled_offer_term_index (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    offer_id UUID NOT NULL,
    offer_identity_key VARCHAR(64) NOT NULL,
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    matcher_version VARCHAR(64) NOT NULL,
    offer_compiler_version VARCHAR(64) NOT NULL,
    term_manifest_hash VARCHAR(64) NOT NULL,
    term VARCHAR(255) NOT NULL,
    term_type VARCHAR(40) NOT NULL,
    indexed_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_compiled_offer_term_entry UNIQUE (
        offer_identity_key,
        matcher_version,
        offer_compiler_version,
        term_manifest_hash,
        term,
        term_type
    )
);

CREATE INDEX idx_compiled_offer_term_lookup
    ON compiled_offer_term_index(matcher_version, offer_compiler_version, term);
CREATE INDEX idx_compiled_offer_term_offer
    ON compiled_offer_term_index(matcher_version, offer_compiler_version, offer_identity_key);
CREATE INDEX idx_compiled_offer_term_manifest
    ON compiled_offer_term_index(term_manifest_hash);

COMMENT ON TABLE compiled_offer_term_index IS 'Persistent offer-term postings for candidate routing';

-- ============================================================================
-- COMPILED_RECIPE_TERM_INDEX - Persistent recipe-term postings for candidate routing
-- ============================================================================
CREATE TABLE compiled_recipe_term_index (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    found_recipe_id UUID NOT NULL,
    recipe_identity_key VARCHAR(64) NOT NULL,
    matcher_version VARCHAR(64) NOT NULL,
    recipe_compiler_version VARCHAR(64) NOT NULL,
    term_manifest_hash VARCHAR(64) NOT NULL,
    term VARCHAR(255) NOT NULL,
    term_type VARCHAR(40) NOT NULL,
    indexed_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_compiled_recipe_term_entry UNIQUE (
        recipe_identity_key,
        matcher_version,
        recipe_compiler_version,
        term_manifest_hash,
        term,
        term_type
    )
);

CREATE INDEX idx_compiled_recipe_term_lookup
    ON compiled_recipe_term_index(matcher_version, recipe_compiler_version, term);
CREATE INDEX idx_compiled_recipe_term_recipe
    ON compiled_recipe_term_index(matcher_version, recipe_compiler_version, recipe_identity_key);
CREATE INDEX idx_compiled_recipe_term_manifest
    ON compiled_recipe_term_index(term_manifest_hash);

COMMENT ON TABLE compiled_recipe_term_index IS 'Persistent recipe-term postings for candidate routing';

-- ============================================================================
-- CACHE_METADATA - Tracks cache computation status
-- ============================================================================
CREATE TABLE cache_metadata (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    cache_name VARCHAR(50) NOT NULL UNIQUE,
    last_computed_at TIMESTAMPTZ,
    computation_time_ms INTEGER,
    total_recipes INTEGER,
    total_matches INTEGER,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'computing', 'ready', 'error')),
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_background_rebuild_at TIMESTAMPTZ,
    background_rebuild_source TEXT
);

COMMENT ON TABLE cache_metadata IS 'Tracks cache computation status and timing';

-- ============================================================================
-- SCRAPER_SCHEDULES - Scheduled recipe scraper runs
-- ============================================================================
CREATE TABLE scraper_schedules (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    scraper_id VARCHAR(50) NOT NULL UNIQUE,
    frequency VARCHAR(20) NOT NULL CHECK (frequency IN ('daily', 'weekly', 'monthly')),
    day_of_week INTEGER CHECK (day_of_week >= 0 AND day_of_week <= 6),
    day_of_month INTEGER CHECK (day_of_month >= 1 AND day_of_month <= 28),
    hour INTEGER NOT NULL CHECK (hour >= 0 AND hour <= 23),
    timezone VARCHAR(50) DEFAULT 'Europe/Stockholm',
    enabled BOOLEAN DEFAULT true,
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE scraper_schedules IS 'Scheduled runs for recipe scrapers';

-- ============================================================================
-- SCRAPER_RUN_HISTORY - Run time history per scraper
-- ============================================================================
CREATE TABLE scraper_run_history (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    scraper_id VARCHAR(50) NOT NULL,
    mode VARCHAR(20) NOT NULL CHECK (mode IN ('test', 'incremental', 'full')),
    duration_seconds INTEGER NOT NULL,
    recipes_found INTEGER DEFAULT 0,
    attempted_count INTEGER,
    success BOOLEAN DEFAULT true,
    error_message TEXT,
    run_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_scraper_run_history_scraper_mode ON scraper_run_history(scraper_id, mode);
CREATE INDEX idx_scraper_run_history_run_at ON scraper_run_history(run_at);

COMMENT ON TABLE scraper_run_history IS 'Run time history for estimating future scraper durations';
COMMENT ON COLUMN scraper_run_history.attempted_count IS 'Number of recipe URLs/items attempted during the run; used for scalable time estimates';

-- ============================================================================
-- SCRAPER_CONFIG - Per-scraper recipe fetch limits (configurable via UI)
-- ============================================================================
CREATE TABLE scraper_config (
    scraper_id VARCHAR(50) PRIMARY KEY,
    max_recipes_full INT CHECK (max_recipes_full >= 1 AND max_recipes_full <= 9999),
    max_recipes_incremental INT CHECK (max_recipes_incremental >= 1 AND max_recipes_incremental <= 9999),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE scraper_config IS 'User-configurable recipe fetch limits per scraper. NULL = scraper default (fetch all).';

-- ============================================================================
-- STORE_SCHEDULES - Scheduled store offer fetches
-- ============================================================================
CREATE TABLE store_schedules (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    store_id VARCHAR(50) NOT NULL UNIQUE,
    frequency VARCHAR(20) NOT NULL CHECK (frequency IN ('daily', 'weekly', 'monthly')),
    day_of_week INTEGER CHECK (day_of_week >= 0 AND day_of_week <= 6),
    day_of_month INTEGER CHECK (day_of_month >= 1 AND day_of_month <= 28),
    hour INTEGER NOT NULL CHECK (hour >= 0 AND hour <= 23),
    timezone VARCHAR(50) DEFAULT 'Europe/Stockholm',
    enabled BOOLEAN DEFAULT true,
    config JSONB DEFAULT '{}',
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_store_schedules_enabled_hour_unique
    ON store_schedules (hour)
    WHERE enabled = true;

COMMENT ON TABLE store_schedules IS 'Scheduled runs for store offer scrapers';

-- ============================================================================
-- SPELL_CORRECTIONS - Tracks ingredient text corrections made by spell checker
-- ============================================================================
CREATE TABLE spell_corrections (
    id SERIAL PRIMARY KEY,
    recipe_id UUID NOT NULL REFERENCES found_recipes(id) ON DELETE CASCADE,
    ingredient_index INTEGER NOT NULL,
    original_word VARCHAR(100) NOT NULL,
    corrected_word VARCHAR(100) NOT NULL,
    reviewed BOOLEAN DEFAULT false,
    excluded BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_spell_corrections_recipe ON spell_corrections(recipe_id);
CREATE INDEX idx_spell_corrections_reviewed ON spell_corrections(reviewed) WHERE reviewed = false;
CREATE INDEX idx_spell_corrections_excluded ON spell_corrections(excluded) WHERE excluded = true;

COMMENT ON TABLE spell_corrections IS 'Tracks ingredient spelling corrections for user review';
COMMENT ON COLUMN spell_corrections.ingredient_index IS 'Index into the recipe ingredients JSONB array';
COMMENT ON COLUMN spell_corrections.reviewed IS 'True once the user has seen this correction';
COMMENT ON COLUMN spell_corrections.excluded IS 'True = never apply this correction again for this recipe';

-- ============================================================================
-- SPELL_EXCLUDED_WORDS - Global spell check word exclusions
-- ============================================================================
CREATE TABLE spell_excluded_words (
    original_word VARCHAR(100) NOT NULL,
    corrected_word VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (original_word, corrected_word)
);

COMMENT ON TABLE spell_excluded_words IS 'Words the user has decided should never be corrected';

-- Seed: known false-positive spell corrections (valid words that look like typos)
INSERT INTO spell_excluded_words (original_word, corrected_word) VALUES
    ('bubblig', 'bubbliz'),
    ('cornichon', 'cornichons'),
    ('cotto', 'cotta'),
    ('dream', 'cream'),
    ('grädd', 'grädde'),
    ('ifraiche', 'fraiche'),
    ('juicy', 'juice'),
    ('kokar', 'lokar'),
    ('kolla', 'kolja'),
    ('pudring', 'pudding'),
    ('rostbiff', 'ostbiff'),
    ('salma', 'salsa'),
    ('salamino', 'salamini'),
    ('salta', 'salsa')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- CUSTOM_RECIPE_URLS - User-managed recipe URLs for the universal scraper
-- ============================================================================
CREATE TABLE custom_recipe_urls (
    id SERIAL PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    label VARCHAR(255),
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'ok', 'error', 'no_recipe', 'gave_up')),
    retry_count INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_custom_recipe_urls_status ON custom_recipe_urls(status);

COMMENT ON TABLE custom_recipe_urls IS 'User-managed recipe URLs for the universal "Mina Recept" scraper';
COMMENT ON COLUMN custom_recipe_urls.label IS 'Optional user-friendly label (auto-filled from recipe name after scraping)';
COMMENT ON COLUMN custom_recipe_urls.status IS 'pending=not yet scraped, ok=scraped successfully, error=scraping failed, no_recipe=no recipe data found';

-- ============================================================================
-- GRANTS
-- Superuser (deal_meals_user) owns all tables.
-- Application user (deal_meals_app) gets DML privileges via 02-security.sh.
-- ============================================================================
