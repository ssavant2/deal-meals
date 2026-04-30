"""Small one-off startup migrations for existing installs.

Fresh databases are still created from database/init.sql. This module only
handles safe, idempotent cleanup needed when an existing volume is upgraded.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Optional

from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from database import engine as app_engine


MIN_RELEASE_FOR_MEMORY_CACHE_CLEANUP = (1, 0, 6)
DROP_MEMORY_CACHE_PREFS_ID = "20260429_drop_memory_cache_preferences"
CREATE_RECIPE_URL_DISCOVERY_CACHE_ID = "20260429_create_recipe_url_discovery_cache"
ADD_CACHE_LAST_OPERATION_ID = "20260430_add_cache_last_operation"
ADD_CACHE_OPERATION_HISTORY_ID = "20260430_add_cache_operation_history"
ADD_RECIPE_TERM_FOUND_RECIPE_INDEX_ID = "20260430_add_recipe_term_found_recipe_index"
ADD_RECIPE_TERM_FOUND_RECIPE_FK_ID = "20260430_add_recipe_term_found_recipe_fk"
CREATE_RECIPE_SEARCH_TERM_INDEX_ID = "20260430_create_recipe_search_term_index"
MIGRATION_TABLE = "deal_meals_schema_migrations"

DROP_MEMORY_CACHE_PREFS_SQL = """
ALTER TABLE matching_preferences
DROP COLUMN IF EXISTS cache_use_memory,
DROP COLUMN IF EXISTS cache_max_memory_mb;
""".strip()

CREATE_RECIPE_URL_DISCOVERY_CACHE_SQL = """
CREATE TABLE IF NOT EXISTS recipe_url_discovery_cache (
    id SERIAL PRIMARY KEY,
    source_name VARCHAR(100) NOT NULL,
    url TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    status VARCHAR(32) NOT NULL,
    reason VARCHAR(64),
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_checked_at TIMESTAMPTZ DEFAULT NOW(),
    next_retry_at TIMESTAMPTZ,
    retry_count INTEGER DEFAULT 0,
    last_http_status INTEGER,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_recipe_url_discovery_source_url UNIQUE (source_name, normalized_url),
    CONSTRAINT chk_recipe_url_discovery_status CHECK (status IN ('known_non_recipe', 'temporary_failed', 'permanently_skipped')),
    CONSTRAINT chk_recipe_url_discovery_retry_count CHECK (retry_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_recipe_url_discovery_source_status
    ON recipe_url_discovery_cache(source_name, status);
CREATE INDEX IF NOT EXISTS idx_recipe_url_discovery_retry
    ON recipe_url_discovery_cache(next_retry_at);
""".strip()

ADD_CACHE_LAST_OPERATION_SQL = """
ALTER TABLE cache_metadata
ADD COLUMN IF NOT EXISTS last_operation JSONB DEFAULT '{}'::jsonb;

COMMENT ON COLUMN cache_metadata.last_operation
    IS 'Small structured summary of the latest cache operation for diagnostics';
""".strip()

ADD_CACHE_OPERATION_HISTORY_SQL = """
ALTER TABLE cache_metadata
ADD COLUMN IF NOT EXISTS operation_history JSONB DEFAULT '[]'::jsonb;

COMMENT ON COLUMN cache_metadata.operation_history
    IS 'Rolling compact history of recent cache operations for fallback diagnostics';
""".strip()

ADD_RECIPE_TERM_FOUND_RECIPE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_compiled_recipe_term_found_recipe
    ON compiled_recipe_term_index(found_recipe_id);
""".strip()

ADD_RECIPE_TERM_FOUND_RECIPE_FK_SQL = """
DELETE FROM compiled_recipe_term_index t
WHERE NOT EXISTS (
    SELECT 1
    FROM found_recipes r
    WHERE r.id = t.found_recipe_id
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_compiled_recipe_term_found_recipe'
          AND conrelid = 'compiled_recipe_term_index'::regclass
    ) THEN
        ALTER TABLE compiled_recipe_term_index
        ADD CONSTRAINT fk_compiled_recipe_term_found_recipe
        FOREIGN KEY (found_recipe_id)
        REFERENCES found_recipes(id)
        ON DELETE CASCADE;
    END IF;
END $$;
""".strip()

CREATE_RECIPE_SEARCH_TERM_INDEX_SQL = """
CREATE TABLE IF NOT EXISTS compiled_recipe_search_term_index (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    found_recipe_id UUID NOT NULL,
    recipe_identity_key VARCHAR(64) NOT NULL,
    recipe_source_hash VARCHAR(64) NOT NULL,
    matcher_version VARCHAR(64) NOT NULL,
    recipe_compiler_version VARCHAR(64) NOT NULL,
    index_version_hash VARCHAR(64) NOT NULL,
    term VARCHAR(255) NOT NULL,
    term_type VARCHAR(40) NOT NULL,
    indexed_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_compiled_recipe_search_term_entry UNIQUE (
        recipe_identity_key,
        matcher_version,
        recipe_compiler_version,
        index_version_hash,
        term,
        term_type
    )
);

CREATE INDEX IF NOT EXISTS idx_compiled_recipe_search_term_lookup
    ON compiled_recipe_search_term_index(matcher_version, recipe_compiler_version, index_version_hash, term);
CREATE INDEX IF NOT EXISTS idx_compiled_recipe_search_term_found_recipe
    ON compiled_recipe_search_term_index(found_recipe_id);
CREATE INDEX IF NOT EXISTS idx_compiled_recipe_search_term_scoring
    ON compiled_recipe_search_term_index(matcher_version, recipe_compiler_version, index_version_hash, found_recipe_id, term_type, term);
CREATE INDEX IF NOT EXISTS idx_compiled_recipe_search_term_recipe
    ON compiled_recipe_search_term_index(matcher_version, recipe_compiler_version, recipe_identity_key);
CREATE INDEX IF NOT EXISTS idx_compiled_recipe_search_term_hash
    ON compiled_recipe_search_term_index(index_version_hash);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_compiled_recipe_search_term_found_recipe'
          AND conrelid = 'compiled_recipe_search_term_index'::regclass
    ) THEN
        ALTER TABLE compiled_recipe_search_term_index
        ADD CONSTRAINT fk_compiled_recipe_search_term_found_recipe
        FOREIGN KEY (found_recipe_id)
        REFERENCES found_recipes(id)
        ON DELETE CASCADE;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS compiled_recipe_search_term_index_status (
    status_key VARCHAR(50) PRIMARY KEY DEFAULT 'pantry_search',
    status VARCHAR(20) NOT NULL DEFAULT 'degraded',
    matcher_version VARCHAR(64),
    recipe_compiler_version VARCHAR(64),
    index_version_hash VARCHAR(64),
    active_scope_count INTEGER NOT NULL DEFAULT 0,
    indexed_recipe_count INTEGER NOT NULL DEFAULT 0,
    empty_term_recipe_count INTEGER NOT NULL DEFAULT 0,
    last_full_refresh_at TIMESTAMPTZ,
    last_incremental_refresh_at TIMESTAMPTZ,
    last_error TEXT DEFAULT 'never refreshed',
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_compiled_recipe_search_term_status
        CHECK (status IN ('ready', 'refreshing', 'degraded'))
);

INSERT INTO compiled_recipe_search_term_index_status (status_key, status, last_error)
VALUES ('pantry_search', 'degraded', 'never refreshed')
ON CONFLICT (status_key) DO NOTHING;
""".strip()


@dataclass(frozen=True)
class _MigrationEngine:
    engine: Engine
    can_run_ddl: bool
    should_dispose: bool = False


def _parse_release_version(version: str) -> Optional[tuple[int, int, int]]:
    """Parse v1.0.6 or 1.0.5a into a comparable numeric tuple."""
    value = (version or "").strip().lower()
    if value.startswith("v"):
        value = value[1:]
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _version_can_run_startup_migrations(release_version: str) -> bool:
    parsed = _parse_release_version(release_version)
    # Unknown labels such as dev/latest are allowed because the code itself is
    # the migration carrier. Numbered releases below 1.0.6 skip defensively.
    return parsed is None or parsed >= MIN_RELEASE_FOR_MEMORY_CACHE_CLEANUP


def _build_admin_engine_from_env() -> Optional[Engine]:
    explicit_url = os.environ.get("DATABASE_MIGRATION_URL", "").strip()
    if explicit_url:
        return create_engine(explicit_url, pool_pre_ping=True)

    db_user = os.environ.get("DB_USER", "").strip()
    db_password = os.environ.get("DB_PASSWORD", "")
    db_name = os.environ.get("DB_NAME", "").strip()
    if not db_user or not db_password:
        return None

    app_url = make_url(str(settings.database_url))
    admin_url = URL.create(
        drivername=app_url.drivername,
        username=db_user,
        password=db_password,
        host=app_url.host,
        port=app_url.port,
        database=db_name or app_url.database,
    )
    return create_engine(admin_url, pool_pre_ping=True)


def _get_migration_engine() -> _MigrationEngine:
    admin_engine = _build_admin_engine_from_env()
    if admin_engine is not None:
        return _MigrationEngine(admin_engine, can_run_ddl=True, should_dispose=True)

    return _MigrationEngine(app_engine, can_run_ddl=False, should_dispose=False)


def _memory_cache_pref_columns(conn) -> list[str]:
    rows = conn.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'matching_preferences'
          AND column_name IN ('cache_use_memory', 'cache_max_memory_mb')
        ORDER BY column_name
    """)).fetchall()
    return [row.column_name for row in rows]


def _ensure_migration_table(conn) -> None:
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} (
            id TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            app_version TEXT,
            details JSONB NOT NULL DEFAULT '{{}}'::jsonb
        )
    """))


def _is_migration_recorded(conn, migration_id: str) -> bool:
    row = conn.execute(
        text(f"SELECT 1 FROM {MIGRATION_TABLE} WHERE id = :id"),
        {"id": migration_id},
    ).fetchone()
    return row is not None


def _record_migration(conn, migration_id: str, release_version: str, details: dict) -> None:
    conn.execute(
        text(f"""
            INSERT INTO {MIGRATION_TABLE} (id, app_version, details)
            VALUES (:id, :app_version, CAST(:details AS jsonb))
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "id": migration_id,
            "app_version": release_version or None,
            "details": json.dumps(details, sort_keys=True),
        },
    )


def _warn_manual_memory_cache_cleanup(existing_columns: list[str]) -> None:
    if not existing_columns:
        return
    logger.warning(
        "Legacy memory-cache columns still exist in matching_preferences, but "
        "the app DB user cannot run DDL. Run this once with the DB admin user: {}",
        DROP_MEMORY_CACHE_PREFS_SQL,
    )


def _recipe_url_discovery_cache_exists(conn) -> bool:
    row = conn.execute(text("""
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'recipe_url_discovery_cache'
    """)).fetchone()
    return row is not None


def _warn_manual_recipe_url_discovery_cache_create() -> None:
    logger.warning(
        "recipe_url_discovery_cache table is missing, but the app DB user "
        "cannot run DDL. Run the startup migration with DB admin credentials "
        "or create the table from database/init.sql before enabling URL discovery."
    )


def _cache_last_operation_column_exists(conn) -> bool:
    row = conn.execute(text("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'cache_metadata'
          AND column_name = 'last_operation'
    """)).fetchone()
    return row is not None


def _cache_operation_history_column_exists(conn) -> bool:
    row = conn.execute(text("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'cache_metadata'
          AND column_name = 'operation_history'
    """)).fetchone()
    return row is not None


def _compiled_recipe_term_found_recipe_index_exists(conn) -> bool:
    row = conn.execute(text("""
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'compiled_recipe_term_index'
          AND indexname = 'idx_compiled_recipe_term_found_recipe'
    """)).fetchone()
    return row is not None


def _compiled_recipe_term_found_recipe_fk_exists(conn) -> bool:
    row = conn.execute(text("""
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_compiled_recipe_term_found_recipe'
          AND conrelid = 'compiled_recipe_term_index'::regclass
    """)).fetchone()
    return row is not None


def _compiled_recipe_search_term_index_exists(conn) -> bool:
    row = conn.execute(text("""
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'compiled_recipe_search_term_index'
    """)).fetchone()
    return row is not None


def _compiled_recipe_search_term_status_exists(conn) -> bool:
    row = conn.execute(text("""
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'compiled_recipe_search_term_index_status'
    """)).fetchone()
    return row is not None


def _warn_manual_cache_last_operation_add() -> None:
    logger.warning(
        "cache_metadata.last_operation is missing, but the app DB user cannot "
        "run DDL. Run the startup migration with DB admin credentials or add "
        "the column from database/init.sql before relying on cache diagnostics."
    )


def _warn_manual_cache_operation_history_add() -> None:
    logger.warning(
        "cache_metadata.operation_history is missing, but the app DB user "
        "cannot run DDL. Run the startup migration with DB admin credentials "
        "or add the column from database/init.sql before relying on cache "
        "fallback-frequency diagnostics."
    )


def _warn_manual_recipe_term_index_add() -> None:
    logger.warning(
        "compiled_recipe_term_index(found_recipe_id) index is missing, but "
        "the app DB user cannot run DDL. Run the startup migration with DB "
        "admin credentials or create idx_compiled_recipe_term_found_recipe "
        "from database/init.sql."
    )


def _warn_manual_recipe_term_fk_add() -> None:
    logger.warning(
        "compiled_recipe_term_index.found_recipe_id foreign key is missing, "
        "but the app DB user cannot run DDL. Run the startup migration with "
        "DB admin credentials or apply the FK from database/init.sql after "
        "removing orphaned term-index rows."
    )


def _warn_manual_recipe_search_term_index_create() -> None:
    logger.warning(
        "compiled_recipe_search_term_index tables are missing, but the app DB "
        "user cannot run DDL. Run the startup migration with DB admin "
        "credentials or create the tables from database/init.sql before "
        "enabling pantry search-term indexing."
    )


def _run_drop_memory_cache_preferences(engine_info: _MigrationEngine, release_version: str) -> None:
    if not engine_info.can_run_ddl:
        with engine_info.engine.connect() as conn:
            _warn_manual_memory_cache_cleanup(_memory_cache_pref_columns(conn))
        return

    with engine_info.engine.begin() as conn:
        _ensure_migration_table(conn)
        if _is_migration_recorded(conn, DROP_MEMORY_CACHE_PREFS_ID):
            return

        existing_columns = _memory_cache_pref_columns(conn)
        if existing_columns:
            conn.execute(text(DROP_MEMORY_CACHE_PREFS_SQL))
            logger.info(
                "Startup migration {} dropped legacy columns: {}",
                DROP_MEMORY_CACHE_PREFS_ID,
                ", ".join(existing_columns),
            )
        else:
            logger.info(
                "Startup migration {} recorded; legacy memory-cache columns were already absent",
                DROP_MEMORY_CACHE_PREFS_ID,
            )

        _record_migration(
            conn,
            DROP_MEMORY_CACHE_PREFS_ID,
            release_version,
            {"columns_dropped": existing_columns},
        )


def _run_create_recipe_url_discovery_cache(engine_info: _MigrationEngine, release_version: str) -> None:
    if not engine_info.can_run_ddl:
        with engine_info.engine.connect() as conn:
            if not _recipe_url_discovery_cache_exists(conn):
                _warn_manual_recipe_url_discovery_cache_create()
        return

    with engine_info.engine.begin() as conn:
        _ensure_migration_table(conn)
        if _is_migration_recorded(conn, CREATE_RECIPE_URL_DISCOVERY_CACHE_ID):
            return

        conn.execute(text(CREATE_RECIPE_URL_DISCOVERY_CACHE_SQL))
        logger.info(
            "Startup migration {} ensured recipe_url_discovery_cache exists",
            CREATE_RECIPE_URL_DISCOVERY_CACHE_ID,
        )
        _record_migration(
            conn,
            CREATE_RECIPE_URL_DISCOVERY_CACHE_ID,
            release_version,
            {"table": "recipe_url_discovery_cache"},
        )


def _run_add_cache_last_operation(engine_info: _MigrationEngine, release_version: str) -> None:
    if not engine_info.can_run_ddl:
        with engine_info.engine.connect() as conn:
            if not _cache_last_operation_column_exists(conn):
                _warn_manual_cache_last_operation_add()
        return

    with engine_info.engine.begin() as conn:
        _ensure_migration_table(conn)
        if _is_migration_recorded(conn, ADD_CACHE_LAST_OPERATION_ID):
            return

        conn.execute(text(ADD_CACHE_LAST_OPERATION_SQL))
        logger.info(
            "Startup migration {} ensured cache_metadata.last_operation exists",
            ADD_CACHE_LAST_OPERATION_ID,
        )
        _record_migration(
            conn,
            ADD_CACHE_LAST_OPERATION_ID,
            release_version,
            {"column": "cache_metadata.last_operation"},
        )


def _run_add_cache_operation_history(engine_info: _MigrationEngine, release_version: str) -> None:
    if not engine_info.can_run_ddl:
        with engine_info.engine.connect() as conn:
            if not _cache_operation_history_column_exists(conn):
                _warn_manual_cache_operation_history_add()
        return

    with engine_info.engine.begin() as conn:
        _ensure_migration_table(conn)
        if _is_migration_recorded(conn, ADD_CACHE_OPERATION_HISTORY_ID):
            return

        conn.execute(text(ADD_CACHE_OPERATION_HISTORY_SQL))
        logger.info(
            "Startup migration {} ensured cache_metadata.operation_history exists",
            ADD_CACHE_OPERATION_HISTORY_ID,
        )
        _record_migration(
            conn,
            ADD_CACHE_OPERATION_HISTORY_ID,
            release_version,
            {"column": "cache_metadata.operation_history"},
        )


def _run_add_recipe_term_found_recipe_index(engine_info: _MigrationEngine, release_version: str) -> None:
    if not engine_info.can_run_ddl:
        with engine_info.engine.connect() as conn:
            if not _compiled_recipe_term_found_recipe_index_exists(conn):
                _warn_manual_recipe_term_index_add()
        return

    with engine_info.engine.begin() as conn:
        _ensure_migration_table(conn)
        if _is_migration_recorded(conn, ADD_RECIPE_TERM_FOUND_RECIPE_INDEX_ID):
            return

        conn.execute(text(ADD_RECIPE_TERM_FOUND_RECIPE_INDEX_SQL))
        logger.info(
            "Startup migration {} ensured compiled_recipe_term_index(found_recipe_id) index exists",
            ADD_RECIPE_TERM_FOUND_RECIPE_INDEX_ID,
        )
        _record_migration(
            conn,
            ADD_RECIPE_TERM_FOUND_RECIPE_INDEX_ID,
            release_version,
            {"index": "idx_compiled_recipe_term_found_recipe"},
        )


def _run_add_recipe_term_found_recipe_fk(engine_info: _MigrationEngine, release_version: str) -> None:
    if not engine_info.can_run_ddl:
        with engine_info.engine.connect() as conn:
            if not _compiled_recipe_term_found_recipe_fk_exists(conn):
                _warn_manual_recipe_term_fk_add()
        return

    with engine_info.engine.begin() as conn:
        _ensure_migration_table(conn)
        if _is_migration_recorded(conn, ADD_RECIPE_TERM_FOUND_RECIPE_FK_ID):
            return

        orphan_count = conn.execute(text("""
            SELECT COUNT(*)
            FROM compiled_recipe_term_index t
            LEFT JOIN found_recipes r ON r.id = t.found_recipe_id
            WHERE r.id IS NULL
        """)).scalar() or 0
        conn.execute(text(ADD_RECIPE_TERM_FOUND_RECIPE_FK_SQL))
        logger.info(
            "Startup migration {} ensured compiled_recipe_term_index.found_recipe_id FK exists "
            "(removed {} orphaned rows before adding constraint)",
            ADD_RECIPE_TERM_FOUND_RECIPE_FK_ID,
            orphan_count,
        )
        _record_migration(
            conn,
            ADD_RECIPE_TERM_FOUND_RECIPE_FK_ID,
            release_version,
            {
                "constraint": "fk_compiled_recipe_term_found_recipe",
                "orphan_rows_removed": int(orphan_count),
            },
        )


def _run_create_recipe_search_term_index(engine_info: _MigrationEngine, release_version: str) -> None:
    if not engine_info.can_run_ddl:
        with engine_info.engine.connect() as conn:
            if not (
                _compiled_recipe_search_term_index_exists(conn)
                and _compiled_recipe_search_term_status_exists(conn)
            ):
                _warn_manual_recipe_search_term_index_create()
        return

    with engine_info.engine.begin() as conn:
        _ensure_migration_table(conn)
        if _is_migration_recorded(conn, CREATE_RECIPE_SEARCH_TERM_INDEX_ID):
            return

        conn.execute(text(CREATE_RECIPE_SEARCH_TERM_INDEX_SQL))
        logger.info(
            "Startup migration {} ensured compiled_recipe_search_term_index tables exist",
            CREATE_RECIPE_SEARCH_TERM_INDEX_ID,
        )
        _record_migration(
            conn,
            CREATE_RECIPE_SEARCH_TERM_INDEX_ID,
            release_version,
            {
                "tables": [
                    "compiled_recipe_search_term_index",
                    "compiled_recipe_search_term_index_status",
                ],
            },
        )


def run_startup_migrations(release_version: str) -> None:
    """Run one-off migrations that are safe during app startup."""
    if not _version_can_run_startup_migrations(release_version):
        logger.debug(
            "Skipping startup migrations for release version {}",
            release_version or "<unknown>",
        )
        return

    engine_info = _get_migration_engine()
    try:
        _run_drop_memory_cache_preferences(engine_info, release_version)
        _run_create_recipe_url_discovery_cache(engine_info, release_version)
        _run_add_cache_last_operation(engine_info, release_version)
        _run_add_cache_operation_history(engine_info, release_version)
        _run_add_recipe_term_found_recipe_index(engine_info, release_version)
        _run_add_recipe_term_found_recipe_fk(engine_info, release_version)
        _run_create_recipe_search_term_index(engine_info, release_version)
    except SQLAlchemyError as e:
        logger.warning(f"Startup migrations skipped after database error: {e}")
    finally:
        if engine_info.should_dispose:
            engine_info.engine.dispose()
