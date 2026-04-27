"""Stable recipe identity helpers for delta planning and compiled caches."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any


def build_recipe_identity_payload_from_fields(
    *,
    source_url: str | None = None,
    source_name: str | None = None,
    recipe_name: str | None = None,
    ingredients: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Build the stable identity payload for a recipe-like object.

    Recipes normally have a stable canonical URL, which is the preferred
    identity because it survives ingredient/title updates. If a URL is missing,
    fall back to a conservative content tuple so tooling can still function in
    synthetic tests and partial payloads.
    """
    if source_url:
        return {
            "kind": "source_url",
            "source_url": str(source_url),
        }
    return {
        "kind": "fallback",
        "source_name": str(source_name or ""),
        "recipe_name": str(recipe_name or ""),
        "ingredients": list(ingredients or ()),
    }


def build_recipe_identity_key_from_payload(payload: dict[str, Any]) -> str:
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_recipe_identity_key_from_fields(
    *,
    source_url: str | None = None,
    source_name: str | None = None,
    recipe_name: str | None = None,
    ingredients: list[str] | tuple[str, ...] | None = None,
) -> str:
    payload = build_recipe_identity_payload_from_fields(
        source_url=source_url,
        source_name=source_name,
        recipe_name=recipe_name,
        ingredients=ingredients,
    )
    return build_recipe_identity_key_from_payload(payload)


def build_recipe_identity_key(recipe) -> str:
    return build_recipe_identity_key_from_fields(
        source_url=getattr(recipe, "url", None),
        source_name=getattr(recipe, "source_name", None),
        recipe_name=getattr(recipe, "name", None),
        ingredients=getattr(recipe, "ingredients", None),
    )
