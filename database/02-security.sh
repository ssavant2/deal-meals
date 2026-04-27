#!/bin/bash
# ============================================================================
# Security setup - Creates application user with limited privileges
# This script runs during PostgreSQL initialization (first start only)
# ============================================================================

set -e

# Use environment variable for app password, with a default for development
APP_PASSWORD="${DB_APP_PASSWORD:?DB_APP_PASSWORD must be set}"

psql -v ON_ERROR_STOP=1 -v app_password="$APP_PASSWORD" -v dbname="$POSTGRES_DB" --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-'EOSQL'
    -- Create application user with limited privileges (no superuser, no createdb)
    CREATE ROLE deal_meals_app WITH LOGIN PASSWORD :'app_password';

    -- Grant connect to database
    GRANT CONNECT ON DATABASE :dbname TO deal_meals_app;

    -- Grant usage on public schema
    GRANT USAGE ON SCHEMA public TO deal_meals_app;

    -- Grant DML privileges on all existing tables (TRUNCATE needed for cache rebuild)
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public TO deal_meals_app;

    -- Grant usage on all sequences (for auto-increment/serial columns)
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO deal_meals_app;

    -- Make these grants apply to future tables created by superuser
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO deal_meals_app;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO deal_meals_app;
EOSQL

echo "Created deal_meals_app user with DML-only privileges"
