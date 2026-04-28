"""
HTML Page Routes.

This router handles all HTML page rendering:
- / (home)
- /stores
- /recipes
- /config
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from loguru import logger

from languages.i18n import get_language_info
from utils.request_helpers import get_theme, get_language, get_i18n_context

# Import plugin system
try:
    from scrapers.stores import get_enabled_stores, get_all_stores
    PLUGIN_SYSTEM_AVAILABLE = True
except ImportError:
    PLUGIN_SYSTEM_AVAILABLE = False


router = APIRouter(tags=["pages"])

# Templates are set up by the main app and passed here
templates: Jinja2Templates = None


def init_templates(app_templates: Jinja2Templates):
    """Initialize templates reference from main app."""
    global templates
    templates = app_templates


# NOTE: get_theme, get_language, get_i18n_context imported from utils/request_helpers.py

# ==================== PAGE ROUTES ====================

@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Home page - displays store overview."""
    stores_list = []
    if PLUGIN_SYSTEM_AVAILABLE:
        stores_list = get_enabled_stores()

    # Get ranking mode for recipe display
    ranking_mode = 'absolute'
    try:
        from recipe_matcher import get_matching_preferences_from_db
        prefs = get_matching_preferences_from_db()
        if prefs:
            ranking_mode = prefs.get('ranking_mode', 'absolute')
    except Exception as e:
        logger.debug(f"Could not load ranking mode: {e}")

    # Get cache generation for sessionStorage auto-invalidation
    cache_generation = ""
    try:
        from database import get_db_session
        from sqlalchemy import text
        with get_db_session() as db:
            result = db.execute(text(
                "SELECT last_computed_at FROM cache_metadata WHERE cache_name = 'recipe_offer_matches'"
            )).fetchone()
            if result and result.last_computed_at:
                cache_generation = result.last_computed_at.isoformat()
    except Exception as e:
        logger.debug(f"Could not load cache generation: {e}")

    # Get enabled recipe sources for search filter dropdown
    recipe_sources = []
    try:
        from database import get_db_session
        from sqlalchemy import text
        with get_db_session() as db:
            rows = db.execute(text("""
                SELECT DISTINCT rs.name FROM recipe_sources rs
                WHERE rs.enabled = true
                AND EXISTS (SELECT 1 FROM found_recipes fr WHERE fr.source_name = rs.name)
                ORDER BY rs.name
            """)).fetchall()
            recipe_sources = [row.name for row in rows]
    except Exception as e:
        logger.debug(f"Could not load recipe sources: {e}")

    return templates.TemplateResponse("home.html", {
        "request": request,
        "stores": stores_list,
        "plugin_system": PLUGIN_SYSTEM_AVAILABLE,
        "ranking_mode": ranking_mode,
        "cache_generation": cache_generation,
        "recipe_sources": recipe_sources,
        **get_i18n_context(request)
    })


@router.get("/stores", response_class=HTMLResponse)
def stores_page(request: Request):
    """Stores page - displays store cards for fetching offers."""
    stores_list = []
    if PLUGIN_SYSTEM_AVAILABLE:
        stores_list = get_enabled_stores()

    return templates.TemplateResponse("stores.html", {
        "request": request,
        "stores": stores_list,
        "plugin_system": PLUGIN_SYSTEM_AVAILABLE,
        **get_i18n_context(request)
    })


@router.get("/recipes", response_class=HTMLResponse)
async def recipes_page(request: Request):
    """Recipe sources management page."""
    image_download_running = False
    try:
        from state import get_image_state
        image_state = await get_image_state()
        image_download_running = bool(image_state.get("running"))
    except Exception as e:
        logger.debug(f"Could not load image download state for recipes page: {e}")

    return templates.TemplateResponse("recipes.html", {
        "request": request,
        "image_download_running": image_download_running,
        **get_i18n_context(request)
    })


@router.get("/config", response_class=HTMLResponse)
def config_page(request: Request):
    """Configuration page - settings and preferences."""
    stores_list = []
    if PLUGIN_SYSTEM_AVAILABLE:
        stores_list = get_all_stores()

    return templates.TemplateResponse("config.html", {
        "request": request,
        "stores": stores_list,
        "plugin_system": PLUGIN_SYSTEM_AVAILABLE,
        **get_i18n_context(request)
    })
