"""
Deal Meals - Grocery deal aggregator with recipe suggestions.

FastAPI web server with plugin-based store system, WebSocket support,
and self-contained store modules.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import uvicorn
import sys
import os
import json
import secrets
from datetime import datetime
from loguru import logger
from sqlalchemy import text

# Keep the primary Docker log focused on app events. HTTP access lines are
# persisted separately below and are intentionally hidden from stdout/stderr.
logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
    filter=lambda record: record["extra"].get("name") != "access",
)

# Persist logs to file (survives container restarts via volume mount)
try:
    logger.add(
        "/app/logs/app.log",
        rotation="10 MB",
        retention="7 days",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} | {message}",
        filter=lambda record: record["extra"].get("name") != "access",
    )
except PermissionError:
    logger.warning("Could not open /app/logs/app.log — file logging disabled")

# Separate access log for HTTP requests (method, path, status, client IP, duration)
_access_logger = logger.bind(name="access")
try:
    logger.add(
        "/app/logs/access.log",
        rotation="10 MB",
        retention="7 days",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {message}",
        filter=lambda record: record["extra"].get("name") == "access",
    )
except PermissionError:
    pass


def _get_build_version() -> str:
    """Read build date (YYMMDD) stamped during docker build."""
    try:
        with open("/build_date") as f:
            return f.read().strip()
    except FileNotFoundError:
        # Dev mode (volume mount hides baked-in file) — use today's date
        return datetime.now().strftime("%y%m%d")


def _read_optional_file(path: str) -> str:
    try:
        with open(path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _get_release_version() -> str:
    """Read the pinned or baked release/image version."""
    configured = os.environ.get("DEAL_MEALS_VERSION", "").strip()
    if configured and configured.lower() != "latest":
        return configured
    return _read_optional_file("/release_version") or configured


def _format_version_label(release_version: str, build_version: str) -> str:
    """Return a compact version label for the navbar."""
    if release_version and release_version.lower() != "latest":
        if release_version.lower() in {"dev", "development"}:
            return f"dev {build_version}"
        return release_version if release_version.startswith("v") else f"v{release_version}"
    return f"build {build_version}"


def _get_display_hostname() -> str:
    """Pick the most useful hostname from ALLOWED_HOSTS for log display."""
    hosts = os.environ.get("ALLOWED_HOSTS", "localhost").split(",")
    for h in hosts:
        h = h.strip()
        if h and h not in ("localhost", "127.0.0.1"):
            return h
    return "localhost"


BUILD_VERSION = _get_build_version()
RELEASE_VERSION = _get_release_version()
VERSION_LABEL = _format_version_label(RELEASE_VERSION, BUILD_VERSION)
VERSION_TITLE = f"Build {BUILD_VERSION}"

# Import i18n framework
from languages.i18n import get_language_info

# Import shared request helpers
from utils.request_helpers import get_theme, get_language, get_i18n_context

# Import routers
from routers import pages as pages_router
from routers import stores as stores_router
from routers import recipes as recipes_router
from routers import images as images_router
from routers import websockets as websockets_router
from routers import status as status_router
from routers import preferences as preferences_router
from routers import pantry as pantry_router
from routers import schedules as schedules_router
from routers import ssl as ssl_router
from routers import spellcheck as spellcheck_router

# Import SSL configuration (needed for uvicorn startup)
try:
    from ssl_config import ssl_manager
    SSL_AVAILABLE = True
except ImportError:
    SSL_AVAILABLE = False
    ssl_manager = None
    logger.warning("SSL configuration not available")


# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from database import get_db_session, shutdown_db
from models import Store

# Import plugin system
try:
    from scrapers.stores import get_all_stores, get_store_discovery_errors
    PLUGIN_SYSTEM_AVAILABLE = True
except ImportError:
    PLUGIN_SYSTEM_AVAILABLE = False
    logger.warning("Plugin system not available - using fallback mode")

# Import scheduler
try:
    from scheduler import scraper_scheduler
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False
    logger.warning("Scheduler not available")


def _format_store_discovery_errors(discovery_errors) -> str:
    details = []
    for error in discovery_errors:
        target = error.get("module", "unknown")
        if error.get("class"):
            target = f"{target}.{error['class']}"
        details.append(
            f"{target} ({error.get('phase', 'unknown')}): "
            f"{error.get('error', 'unknown error')}"
        )
    return "; ".join(details)


def _sync_store_registry(discovered_stores, discovery_errors=None) -> None:
    """Reconcile DB store rows with the currently discovered plugin set."""
    discovery_errors = discovery_errors or []
    plugin_by_type = {store.config.id: store for store in discovered_stores}
    enabled_types = {
        store.config.id
        for store in discovered_stores
        if store.config.enabled
    }

    created = 0
    updated = 0
    removed = 0
    removed_schedules = 0
    removed_store_types = []

    with get_db_session() as db:
        existing_rows = {
            row.store_type: row
            for row in db.query(Store).all()
        }

        for store_type in sorted(enabled_types):
            plugin = plugin_by_type[store_type]
            row = existing_rows.get(store_type)

            if row is None:
                db.add(Store(
                    name=plugin.config.name,
                    store_type=plugin.config.id,
                    url=plugin.config.url,
                    config={},
                ))
                created += 1
                continue

            changed = False
            if row.name != plugin.config.name:
                row.name = plugin.config.name
                changed = True
            if row.url != plugin.config.url:
                row.url = plugin.config.url
                changed = True
            if changed:
                updated += 1

        if discovery_errors:
            logger.error(
                "Skipping destructive store registry cleanup because store plugin "
                "discovery had {} error(s): {}",
                len(discovery_errors),
                _format_store_discovery_errors(discovery_errors),
            )
        else:
            for store_type, row in existing_rows.items():
                if store_type in enabled_types:
                    continue

                schedule_result = db.execute(
                    text("DELETE FROM store_schedules WHERE store_id = :store_id"),
                    {"store_id": store_type},
                )
                rowcount = schedule_result.rowcount or 0
                if rowcount > 0:
                    removed_schedules += rowcount

                db.delete(row)
                removed += 1
                removed_store_types.append(store_type)

        if created or updated or removed or removed_schedules:
            db.commit()

    logger.info(
        "Store registry synced at startup "
        "(created={}, updated={}, removed={}, removed_schedules={})",
        created,
        updated,
        removed,
        removed_schedules,
    )
    if removed_store_types:
        logger.info(
            "Removed store registry entries without enabled plugins: {}",
            ", ".join(sorted(removed_store_types)),
        )


def _fallback_recipe_source_url(source_name: str) -> str:
    slug = (source_name or "recipe-source").strip().lower().replace(" ", "-")
    return f"https://{slug or 'recipe-source'}"


def _recipe_source_registry_rows() -> list[dict]:
    try:
        from recipe_scraper_manager import scraper_manager
        return scraper_manager.get_registry_sources()
    except Exception as e:
        logger.debug(f"Could not load recipe source registry rows: {e}")
        return []


def _sync_recipe_sources() -> None:
    """Register recipe sources and collapse legacy duplicate rows by name."""
    registry_sources = _recipe_source_registry_rows()
    canonical_urls = {
        source["name"]: source["url"]
        for source in registry_sources
        if source.get("name") and source.get("url")
    }
    inserted = 0
    deduped = 0
    url_updates = 0

    with get_db_session() as db:
        actual_sources = db.execute(text("""
            SELECT DISTINCT source_name
            FROM found_recipes
            WHERE source_name IS NOT NULL AND source_name <> ''
        """)).fetchall()
        actual_source_names = {row.source_name for row in actual_sources}

        for source in registry_sources:
            result = db.execute(text("""
                INSERT INTO recipe_sources (name, url, enabled)
                SELECT :name, :url, :enabled
                WHERE NOT EXISTS (
                    SELECT 1 FROM recipe_sources
                    WHERE name = :name OR url = :url
                )
                ON CONFLICT (url) DO NOTHING
            """), {
                "name": source["name"],
                "url": source["url"],
                "enabled": (
                    source["name"] in actual_source_names
                    or bool(source.get("default_enabled", False))
                ),
            })
            inserted += result.rowcount or 0

        for row in actual_sources:
            source_name = row.source_name
            source_url = canonical_urls.get(source_name) or _fallback_recipe_source_url(source_name)
            result = db.execute(text("""
                INSERT INTO recipe_sources (name, url, enabled)
                SELECT :name, :url, true
                WHERE NOT EXISTS (
                    SELECT 1 FROM recipe_sources WHERE name = :name
                )
                ON CONFLICT (url) DO NOTHING
            """), {"name": source_name, "url": source_url})
            inserted += result.rowcount or 0

        duplicate_names = db.execute(text("""
            SELECT name
            FROM recipe_sources
            GROUP BY name
            HAVING COUNT(*) > 1
            ORDER BY name
        """)).fetchall()

        for duplicate in duplicate_names:
            source_name = duplicate.name
            preferred_url = canonical_urls.get(source_name) or _fallback_recipe_source_url(source_name)
            rows = db.execute(text("""
                SELECT id::text AS id, url, enabled, is_starred
                FROM recipe_sources
                WHERE name = :name
                ORDER BY
                    (url = :preferred_url) DESC,
                    is_starred DESC,
                    enabled DESC,
                    updated_at DESC NULLS LAST,
                    created_at DESC NULLS LAST,
                    id
            """), {"name": source_name, "preferred_url": preferred_url}).fetchall()
            if not rows:
                continue

            keep = rows[0]
            keep_id = keep.id
            keep_enabled = bool(keep.enabled)
            keep_starred = any(bool(row.is_starred) for row in rows)
            delete_ids = [row.id for row in rows[1:]]

            for delete_id in delete_ids:
                db.execute(
                    text("DELETE FROM recipe_sources WHERE id = CAST(:id AS uuid)"),
                    {"id": delete_id},
                )

            db.execute(text("""
                UPDATE recipe_sources
                SET enabled = :enabled,
                    is_starred = :is_starred,
                    url = :url,
                    updated_at = NOW()
                WHERE id = CAST(:id AS uuid)
            """), {
                "id": keep_id,
                "enabled": keep_enabled,
                "is_starred": keep_starred,
                "url": preferred_url,
            })
            deduped += len(delete_ids)

        for source_name, source_url in canonical_urls.items():
            result = db.execute(text("""
                UPDATE recipe_sources rs
                SET url = :url,
                    updated_at = NOW()
                WHERE rs.name = :name
                  AND rs.url <> :url
                  AND NOT EXISTS (
                      SELECT 1 FROM recipe_sources other
                      WHERE other.url = :url AND other.name <> :name
                  )
            """), {"name": source_name, "url": source_url})
            url_updates += result.rowcount or 0

        db.commit()

    logger.info(
        "Recipe sources synced at startup (inserted={}, deduped={}, url_updates={})",
        inserted,
        deduped,
        url_updates,
    )


async def _ensure_pantry_search_index_ready_on_startup():
    if not app_settings.pantry_search_term_index_enabled:
        return None

    try:
        from pantry_search_index import (
            compiled_recipe_search_term_index_needs_refresh,
            refresh_compiled_recipe_search_term_index,
        )
        import asyncio

        needs_refresh, reason = compiled_recipe_search_term_index_needs_refresh()
        if not needs_refresh:
            logger.info("Pantry search-term index ready at startup")
            return None

        if not app_settings.pantry_search_startup_refresh_enabled:
            logger.info(
                "Pantry search-term index refresh needed at startup ({}) but "
                "startup refresh is disabled",
                reason,
            )
            return None

        logger.info(
            "Pantry search-term index refresh queued at startup ({})",
            reason,
        )

        async def _refresh_in_background() -> None:
            try:
                result = await asyncio.get_running_loop().run_in_executor(
                    None,
                    refresh_compiled_recipe_search_term_index,
                )
                logger.info(
                    "Pantry search-term index refreshed at startup "
                    "(rows={}, recipes={})",
                    result.get("index_rows", 0),
                    result.get("indexed_recipe_count", 0),
                )
            except Exception as exc:
                logger.warning(
                    "Pantry search-term index startup refresh failed; pantry "
                    "will fall back to legacy until refreshed: {}",
                    exc,
                )

        return asyncio.create_task(
            _refresh_in_background(),
            name="startup-pantry-search-index-refresh",
        )
    except Exception as exc:
        logger.warning(
            "Could not inspect pantry search-term index at startup; pantry will "
            "fall back to legacy if needed: {}",
            exc,
        )
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events."""
    port = os.environ.get("APP_PORT", "20080")
    hostname = _get_display_hostname()
    protocol = "https" if (SSL_AVAILABLE and ssl_manager and ssl_manager.is_ssl_ready()) else "http"
    logger.info(f"Starting Deal Meals ({VERSION_LABEL}) on port {port}")
    logger.info(f"Access at: {protocol}://{hostname}:{port}")

    try:
        from startup_migrations import run_startup_migrations
        run_startup_migrations(RELEASE_VERSION)
    except Exception as e:
        logger.warning(f"Startup migrations failed (non-critical): {e}")

    if PLUGIN_SYSTEM_AVAILABLE:
        stores = get_all_stores()
        store_discovery_errors = get_store_discovery_errors()
        logger.info(f"Loaded {len(stores)} store plugins:")
        for store in stores:
            status = "✓" if store.config.enabled else "✗"
            logger.info(f"   {status} {store.config.name} ({store.config.id})")
        _sync_store_registry(stores, discovery_errors=store_discovery_errors)

    # Seed built-in spell-check false-positive exclusions before cache rebuild,
    # so existing installs get the same protection as fresh databases.
    try:
        from utils.spell_check import sync_default_spell_exclusions
        result = sync_default_spell_exclusions()
        logger.info(
            "Default spell exclusions synced (inserted={}, reverted={}, deleted={})",
            result.get("inserted", 0),
            result.get("reverted", 0),
            result.get("deleted", 0),
        )
    except Exception as e:
        logger.warning(f"Default spell exclusion sync failed (non-critical): {e}")

    try:
        _sync_recipe_sources()
    except Exception as e:
        logger.warning(f"Recipe source sync at startup failed (non-critical): {e}")

    # Start scheduler
    if SCHEDULER_AVAILABLE:
        try:
            scraper_scheduler.start()
            logger.info("Scheduler started")
        except Exception as e:
            logger.error(f"Scheduler failed to start: {e} — app continues without scheduling")

    # Queue recipe-offer cache rebuild on startup without blocking the web
    # process from becoming healthy. Existing cache rows remain servable while
    # the background rebuild computes a fresh replacement.
    from cache_manager import cache_manager, compute_cache_async
    import asyncio

    existing_cache_rows = 0
    try:
        from database import SessionLocal
        session = SessionLocal()
        existing_cache_rows = session.execute(
            text("SELECT COUNT(*) FROM recipe_offer_cache")
        ).scalar()
        if existing_cache_rows and existing_cache_rows > 0:
            session.execute(text(
                "UPDATE cache_metadata SET status = 'ready' "
                "WHERE cache_name = 'recipe_offer_matches' "
                "AND status = 'computing'"
            ))
            session.commit()
        session.close()
        if existing_cache_rows and existing_cache_rows > 0:
            logger.info(
                "Serving existing cache at startup "
                f"({existing_cache_rows} entries)"
            )
        else:
            logger.warning(
                "No cache data available at startup; recipe suggestions may be "
                "missing until a scrape or manual cache reset rebuilds it"
            )

        cache_freshness = cache_manager.inspect_cache_freshness(include_version_scan=True)
        app.state.startup_cache_freshness = cache_freshness
        freshness_state = cache_freshness.get("state", "unknown")
        freshness_reasons = cache_freshness.get("reasons") or []
        if freshness_state == "fresh":
            logger.info(
                "Startup cache freshness: fresh "
                f"(rows={cache_freshness.get('cached_rows')}, "
                f"active_recipes={cache_freshness.get('active_recipe_count')})"
            )
        elif cache_freshness.get("servable"):
            logger.warning(
                "Startup cache freshness: serving existing cache but rebuild "
                f"is recommended (state={freshness_state}, "
                f"reasons={','.join(freshness_reasons) or 'unknown'}, "
                f"rows={cache_freshness.get('cached_rows')}, "
                f"active_recipes={cache_freshness.get('active_recipe_count')})"
            )
        else:
            logger.warning(
                "Startup cache freshness: cache is not servable "
                f"(state={freshness_state}, "
                f"reasons={','.join(freshness_reasons) or 'unknown'})"
            )
    except Exception as e:
        logger.warning(f"Could not inspect startup cache state: {e}")

    pantry_search_task = await _ensure_pantry_search_index_ready_on_startup()

    async def _refresh_cache_after_startup() -> None:
        if pantry_search_task is not None:
            logger.info(
                "Startup cache rebuild waiting for pantry search-term index "
                "refresh to finish"
            )
            await pantry_search_task

        cache_ok = False
        for attempt in range(2):
            try:
                result = await compute_cache_async(
                    skip_if_busy=False,
                    run_kind="startup_background_full_rebuild",
                    source="startup",
                )
                logger.info(
                    "Startup background cache rebuilt ({}/{}): {} recipes in {}ms",
                    result.get('effective_rebuild_mode', 'unknown'),
                    result.get('configured_rebuild_mode', 'unknown'),
                    result.get('cached', 0),
                    result.get('time_ms', 0),
                )
                cache_ok = True
                break
            except Exception as e:
                if attempt == 0:
                    logger.error(
                        "Startup background cache rebuild failed "
                        f"(attempt 1/2): {e} — retrying..."
                    )
                else:
                    logger.critical(
                        f"STARTUP BACKGROUND CACHE BUILD FAILED after 2 attempts: {e}\n"
                        "The web server will keep serving existing cache data "
                        "if available. Check database connectivity and disk space."
                    )

        if not cache_ok:
            # Check if stale cache data exists in DB
            try:
                from database import SessionLocal
                session = SessionLocal()
                stale_count = session.execute(
                    text("SELECT COUNT(*) FROM recipe_offer_cache")
                ).scalar()
                session.close()
                if stale_count and stale_count > 0:
                    logger.warning(
                        f"Using STALE cache data ({stale_count} entries) — "
                        "recipes may show outdated offers"
                    )
                    # Set status to 'ready' so stale data is served
                    session = SessionLocal()
                    session.execute(text(
                        "UPDATE cache_metadata SET status = 'ready' "
                        "WHERE cache_name = 'recipe_offer_matches'"
                    ))
                    session.commit()
                    session.close()
                else:
                    logger.critical(
                        "No cache data available — recipes will use live "
                        "computation (SLOW)"
                    )
            except Exception as e2:
                logger.critical(f"Could not check stale cache: {e2}")

    app.state.startup_pantry_search_task = pantry_search_task
    if app_settings.cache_startup_background_rebuild_enabled:
        app.state.startup_cache_rebuild_task = asyncio.create_task(
            _refresh_cache_after_startup(),
            name="startup-cache-rebuild",
        )
    else:
        app.state.startup_cache_rebuild_task = None
        logger.info(
            "Startup cache policy: serving existing cache; full rebuild is "
            "manual/scheduled, not part of web startup"
        )

    yield

    startup_cache_task = getattr(app.state, "startup_cache_rebuild_task", None)
    if startup_cache_task and not startup_cache_task.done():
        logger.info("Startup cache rebuild still running during shutdown")

    # Shutdown scheduler
    if SCHEDULER_AVAILABLE:
        try:
            scraper_scheduler.shutdown()
        except Exception as e:
            logger.warning(f"Scheduler shutdown failed: {e}")

    # Close database connections
    shutdown_db()

    logger.info("Shutting down...")


from config import settings as app_settings

app = FastAPI(
    title=f"Deal Meals ({BUILD_VERSION})",
    lifespan=lifespan,
    docs_url="/docs" if app_settings.debug else None,
    redoc_url="/redoc" if app_settings.debug else None,
    openapi_url="/openapi.json" if app_settings.debug else None,
)
templates = Jinja2Templates(directory="templates")

# ==================== RATE LIMITING ====================
from utils.rate_limit import get_client_ip, limiter, rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


# ==================== GLOBAL EXCEPTION HANDLERS ====================

@app.exception_handler(json.JSONDecodeError)
async def json_decode_error_handler(request: Request, exc: json.JSONDecodeError):
    """Return 400 instead of 500 when request body contains invalid JSON."""
    return JSONResponse(
        {"success": False, "message_key": "error.invalid_data"},
        status_code=400
    )


# ==================== REQUEST BODY SIZE LIMIT ====================
# Most mutating API calls only carry small JSON payloads. Read and replay the
# body with a hard cap so endpoints can keep using request.json() safely even
# when Content-Length is absent or wrong.

MAX_MUTATING_REQUEST_BODY_BYTES = 1 * 1024 * 1024
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _request_body_too_large_response() -> JSONResponse:
    return JSONResponse(
        {"success": False, "message_key": "error.payload_too_large"},
        status_code=413,
    )


def _content_length_exceeds_limit(request: Request, limit_bytes: int) -> bool:
    content_length = request.headers.get("content-length")
    if not content_length:
        return False
    try:
        return int(content_length) > limit_bytes
    except ValueError:
        return False


def _replay_request_body(request: Request, body: bytes) -> None:
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    request._body = body  # noqa: SLF001 - Starlette uses this cache internally.
    request._receive = receive  # noqa: SLF001 - Replays the capped body downstream.


@app.middleware("http")
async def cap_mutating_request_body(request: Request, call_next):
    """Reject mutating request bodies over 1 MB before endpoint parsing."""
    if request.method not in MUTATING_METHODS:
        return await call_next(request)

    if _content_length_exceeds_limit(request, MAX_MUTATING_REQUEST_BODY_BYTES):
        logger.warning(f"Blocked oversized request body for {request.method} {request.url.path}")
        return _request_body_too_large_response()

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_MUTATING_REQUEST_BODY_BYTES:
            logger.warning(f"Blocked oversized streamed request body for {request.method} {request.url.path}")
            return _request_body_too_large_response()

    _replay_request_body(request, bytes(body))
    return await call_next(request)


# ==================== CSRF / ORIGIN PROTECTION MIDDLEWARE ====================
# Requires valid Origin header on all mutating requests (POST/PUT/PATCH/DELETE).
# Blocks requests without Origin (curl, scripts) AND requests with wrong Origin.
# Only browser fetch()/XHR from an allowed origin will pass through.

from utils.security import ALLOWED_ORIGINS


@app.middleware("http")
async def csrf_origin_check(request: Request, call_next):
    """Require valid Origin header on mutating requests."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")

        if not origin:
            logger.warning(f"Blocked: Missing Origin header for {request.method} {request.url.path}")
            return JSONResponse(
                {"success": False, "message_key": "error.unauthorized"},
                status_code=403
            )

        if origin not in ALLOWED_ORIGINS:
            logger.warning(f"Blocked: Origin '{origin}' not in allowed list for {request.method} {request.url.path}")
            return JSONResponse(
                {"success": False, "message_key": "error.unauthorized"},
                status_code=403
            )

    return await call_next(request)


# ==================== SECURITY HEADERS MIDDLEWARE ====================

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers and access logging to all responses."""
    # Generate a unique nonce for this request
    nonce = secrets.token_urlsafe(16)
    request.state.csp_nonce = nonce

    import time as _time
    start = _time.monotonic()
    path = request.url.path
    try:
        from activity_tracker import record_user_activity
        record_user_activity(path, request.method)
    except Exception as exc:
        logger.debug(f"Could not record user activity for {request.method} {path}: {exc}")
    response = await call_next(request)
    duration_ms = int((_time.monotonic() - start) * 1000)

    # Access log (skip health checks and static assets to reduce noise)
    if not path.startswith("/static/") and path != "/health":
        client = get_client_ip(request)
        _access_logger.info(
            f"{request.method} {path} {response.status_code} {client} {duration_ms}ms"
        )

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self'; "
        "connect-src 'self' ws: wss: https://nominatim.openstreetmap.org; "
        "frame-ancestors 'self'"
    )
    return response


# Register i18n language info as Jinja2 global (for language selector dropdown)
templates.env.globals['available_languages'] = get_language_info
templates.env.globals['app_version_label'] = VERSION_LABEL
templates.env.globals['app_version_title'] = VERSION_TITLE

# Serve static files (optional, no longer used but may be needed for legacy)
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve store logos only (not source code) from store plugin directories
import re as _re

@app.get("/scrapers/stores/{store_id}/{filename}")
async def serve_store_asset(store_id: str, filename: str):
    """Serve only static assets (logos) from store directories - not source code."""
    if not _re.match(r'^[a-z0-9_]+$', store_id):
        return Response(status_code=404)
    if not _re.match(r'^[a-z0-9_.-]+$', filename):
        return Response(status_code=404)
    allowed_ext = {'.svg', '.png', '.jpg', '.jpeg', '.webp', '.ico'}
    ext = os.path.splitext(filename)[1].lower()
    if ext not in allowed_ext:
        return Response(status_code=404)
    base_dir = os.path.abspath("scrapers/stores")
    filepath = os.path.abspath(os.path.join(base_dir, store_id, filename))
    if not filepath.startswith(base_dir):
        return Response(status_code=404)
    if os.path.isfile(filepath):
        return FileResponse(filepath)
    return Response(status_code=404)


# ==================== REGISTER ROUTERS ====================

pages_router.init_templates(templates)
app.include_router(pages_router.router)
app.include_router(stores_router.router)
app.include_router(recipes_router.router)
app.include_router(images_router.router)
app.include_router(websockets_router.router)
app.include_router(status_router.router)
app.include_router(preferences_router.router)
app.include_router(pantry_router.router)
app.include_router(schedules_router.router)
app.include_router(ssl_router.router)
app.include_router(spellcheck_router.router)


# ==================== MAIN ====================

if __name__ == "__main__":
    # Read port from environment (configurable in docker-compose)
    port = int(os.environ.get("APP_PORT", "20080"))

    # Base uvicorn config
    # UVICORN_RELOAD=false disables auto-reload during bulk code edits
    reload_enabled = os.environ.get("UVICORN_RELOAD", "true").lower() != "false"
    uvicorn_config = {
        "app": "app:app",
        "host": "0.0.0.0",
        "port": port,
        "reload": reload_enabled,
        "access_log": False
    }

    # Add SSL config if available and enabled
    if SSL_AVAILABLE and ssl_manager.is_ssl_ready():
        ssl_args = ssl_manager.get_uvicorn_ssl_args()
        uvicorn_config.update(ssl_args)
        logger.info(f"SSL enabled on port {port} - using certificates from {ssl_manager.certs_dir}")
    else:
        logger.info(f"Running without SSL on port {port} (HTTP only)")

    uvicorn.run(**uvicorn_config)
