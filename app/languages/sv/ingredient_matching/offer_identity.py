"""Stable offer identity helpers for delta planning and compiled caches."""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import json
from typing import Any


def _normalize_decimal(value: Decimal | float | int | str | None) -> str | None:
    if value is None:
        return None
    normalized = Decimal(str(value)).normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def build_offer_identity_payload(
    *,
    product_url: str | None,
    store_id: str | None = None,
    store_name: str | None = None,
    name: str | None = None,
    brand: str | None = None,
    unit: str | None = None,
    category: str | None = None,
    weight_grams: Decimal | float | int | str | None = None,
) -> dict[str, Any]:
    """Build a stable identity payload for one offer-like object.

    If a product URL exists we treat that as the canonical identity anchor,
    since store scrapers already deduplicate on that field. Otherwise we fall
    back to a stable, price-independent content signature.
    """
    if product_url:
        return {
            "kind": "product_url",
            "product_url": str(product_url),
        }

    return {
        "kind": "content_fallback",
        "store_id": str(store_id) if store_id else None,
        "store_name": store_name,
        "name": name,
        "brand": brand,
        "unit": unit,
        "category": category,
        "weight_grams": _normalize_decimal(weight_grams),
    }


def build_offer_identity_key_from_payload(payload: dict[str, Any]) -> str:
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_offer_identity_key_from_fields(**kwargs: Any) -> str:
    return build_offer_identity_key_from_payload(build_offer_identity_payload(**kwargs))


def build_offer_identity_key(offer) -> str:
    return build_offer_identity_key_from_fields(
        product_url=getattr(offer, "product_url", None),
        store_id=getattr(offer, "store_id", None),
        name=getattr(offer, "name", None),
        brand=getattr(offer, "brand", None),
        unit=getattr(offer, "unit", None),
        category=getattr(offer, "category", None),
        weight_grams=getattr(offer, "weight_grams", None),
    )
