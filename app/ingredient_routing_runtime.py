"""Runtime helpers for ingredient-routing mode selection."""

from __future__ import annotations

try:
    from config import settings
except ModuleNotFoundError:
    from app.config import settings


INGREDIENT_ROUTING_MODES = frozenset({"off", "hint_first"})
DEPRECATED_INGREDIENT_ROUTING_MODES = frozenset({"shadow", "probation"})


def normalize_ingredient_routing_mode(mode: str | None) -> str:
    """Return a supported ingredient-routing mode, defaulting safely to off."""
    normalized = (mode or "off").strip().lower()
    if normalized in INGREDIENT_ROUTING_MODES:
        return normalized
    if normalized in DEPRECATED_INGREDIENT_ROUTING_MODES:
        return "off"
    return "off"


def get_configured_ingredient_routing_mode() -> str:
    """Return the configured runtime mode for ingredient routing."""
    return normalize_ingredient_routing_mode(settings.cache_ingredient_routing_mode)
