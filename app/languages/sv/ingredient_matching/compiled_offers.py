"""Persistent offer-side compiler for cache rebuilds."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any
from sqlalchemy import text

try:
    from database import get_db_session
    from models import CompiledOfferMatchData, Offer
except ModuleNotFoundError:
    from app.database import get_db_session
    from app.models import CompiledOfferMatchData, Offer

from .matching import precompute_offer_data
from .offer_identity import build_offer_identity_key
from .versioning import OFFER_COMPILER_VERSION

_COMPILED_OFFER_REFRESH_LOCK = 82001


def _normalize_decimal(value: Decimal | float | int | None) -> str | None:
    if value is None:
        return None
    normalized = Decimal(str(value)).normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def normalize_compiled_offer_payload(value: Any) -> Any:
    """Convert precompute_offer_data() output to stable JSONB-safe structures."""
    if isinstance(value, dict):
        return {key: normalize_compiled_offer_payload(value[key]) for key in sorted(value)}
    if isinstance(value, (set, frozenset)):
        normalized = [normalize_compiled_offer_payload(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
    if isinstance(value, tuple):
        return [normalize_compiled_offer_payload(item) for item in value]
    if isinstance(value, list):
        return [normalize_compiled_offer_payload(item) for item in value]
    if isinstance(value, Decimal):
        return _normalize_decimal(value)
    return value


def _stable_json_hash(payload: dict[str, Any]) -> str:
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def ensure_compiled_offer_match_table() -> None:
    """Ensure the compiled-offer table exists in the current schema."""
    with get_db_session() as db:
        exists = db.execute(text(
            "SELECT to_regclass('public.compiled_offer_match_data')"
        )).scalar()
    if not exists:
        raise RuntimeError(
            "compiled_offer_match_data table is missing. Apply the schema change "
            "from database/init.sql to this database before running offer-IR tools."
        )


def _acquire_refresh_lock(db) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": _COMPILED_OFFER_REFRESH_LOCK},
    )


def build_compiled_offer_match_row(offer: Offer, *, compiler_version: str = OFFER_COMPILER_VERSION) -> dict[str, Any]:
    """Compile one Offer row into the persistent offer-side IR shape."""
    offer_identity_key = build_offer_identity_key(offer)
    compiled_data = precompute_offer_data(
        offer.name,
        offer.category or "",
        brand=offer.brand or "",
        weight_grams=float(offer.weight_grams) if offer.weight_grams is not None else None,
    )
    compiled_data = normalize_compiled_offer_payload(compiled_data)

    match_hash_payload = {
        "name": offer.name,
        "category": offer.category,
        "brand": offer.brand,
        "weight_grams": _normalize_decimal(offer.weight_grams),
        "compiler_version": compiler_version,
    }
    score_hash_payload = {
        "price": _normalize_decimal(offer.price),
        "original_price": _normalize_decimal(offer.original_price),
        "savings": _normalize_decimal(offer.savings),
        "is_multi_buy": bool(offer.is_multi_buy),
        "multi_buy_quantity": offer.multi_buy_quantity,
        "multi_buy_total_price": _normalize_decimal(offer.multi_buy_total_price),
    }
    display_hash_payload = {
        "product_url": offer.product_url,
        "image_url": offer.image_url,
        "location_name": offer.location_name,
        "location_type": offer.location_type,
    }

    return {
        "offer_id": offer.id,
        "offer_identity_key": offer_identity_key,
        "store_id": offer.store_id,
        "compiler_version": compiler_version,
        "offer_match_hash": _stable_json_hash(match_hash_payload),
        "offer_score_hash": _stable_json_hash(score_hash_payload),
        "offer_display_hash": _stable_json_hash(display_hash_payload),
        "source_name": offer.name,
        "source_category": offer.category,
        "source_brand": offer.brand,
        "source_weight_grams": offer.weight_grams,
        "source_price": offer.price,
        "source_original_price": offer.original_price,
        "source_savings": offer.savings,
        "source_product_url": offer.product_url,
        "source_image_url": offer.image_url,
        "is_active": True,
        "compiled_data": compiled_data,
        "compiled_at": datetime.now(timezone.utc),
    }


def refresh_compiled_offer_match_data() -> dict[str, Any]:
    """Rebuild the persistent compiled offer table from the current offers table."""
    ensure_compiled_offer_match_table()

    with get_db_session() as db:
        _acquire_refresh_lock(db)
        offers = db.query(Offer).order_by(Offer.id).all()
        rows = [build_compiled_offer_match_row(offer) for offer in offers]

        db.execute(CompiledOfferMatchData.__table__.delete())
        if rows:
            db.bulk_insert_mappings(CompiledOfferMatchData, rows)
        db.commit()

    return {
        "compiler_version": OFFER_COMPILER_VERSION,
        "compiled_offers": len(rows),
    }


def load_compiled_offer_match_map(*, key_field: str = "offer_identity_key") -> dict[str, dict[str, Any]]:
    """Load compiled offer rows keyed by offer_id for parity/comparison helpers."""
    ensure_compiled_offer_match_table()

    with get_db_session() as db:
        rows = db.query(CompiledOfferMatchData).order_by(CompiledOfferMatchData.offer_id).all()

    result = {}
    for row in rows:
        key_value = getattr(row, key_field)
        result[str(key_value)] = {
            "offer_id": str(row.offer_id),
            "offer_identity_key": row.offer_identity_key,
            "compiler_version": row.compiler_version,
            "offer_match_hash": row.offer_match_hash,
            "offer_score_hash": row.offer_score_hash,
            "offer_display_hash": row.offer_display_hash,
            "source_name": row.source_name,
            "source_category": row.source_category,
            "source_brand": row.source_brand,
            "source_weight_grams": _normalize_decimal(row.source_weight_grams),
            "source_price": _normalize_decimal(row.source_price),
            "source_original_price": _normalize_decimal(row.source_original_price),
            "source_savings": _normalize_decimal(row.source_savings),
            "source_product_url": row.source_product_url,
            "source_image_url": row.source_image_url,
            "is_active": row.is_active,
            "compiled_data": row.compiled_data,
        }
    return result


def classify_offer_change_sets(
    current_rows_by_offer_id: dict[str, dict[str, Any]],
    persisted_rows_by_offer_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Classify offer deltas using the stored match/score/display hashes.

    Active-status transitions are treated as add/remove events for delta
    rebuild semantics.
    """
    added: list[str] = []
    removed: list[str] = []
    match_changed: list[str] = []
    score_changed: list[str] = []
    display_changed: list[str] = []
    version_mismatch: list[str] = []
    unchanged: list[str] = []

    current_ids = set(current_rows_by_offer_id)

    for offer_id, current_row in current_rows_by_offer_id.items():
        persisted_row = persisted_rows_by_offer_id.get(offer_id)
        if persisted_row is None:
            added.append(offer_id)
            continue
        if not bool(persisted_row.get("is_active", True)):
            added.append(offer_id)
            continue
        if persisted_row.get("compiler_version") != current_row.get("compiler_version"):
            version_mismatch.append(offer_id)
            continue
        if persisted_row.get("offer_match_hash") != current_row.get("offer_match_hash"):
            match_changed.append(offer_id)
            continue
        if persisted_row.get("offer_score_hash") != current_row.get("offer_score_hash"):
            score_changed.append(offer_id)
            continue
        if persisted_row.get("offer_display_hash") != current_row.get("offer_display_hash"):
            display_changed.append(offer_id)
            continue
        unchanged.append(offer_id)

    for offer_id, persisted_row in persisted_rows_by_offer_id.items():
        if offer_id not in current_ids and bool(persisted_row.get("is_active", True)):
            removed.append(offer_id)

    def _sorted(values: list[str]) -> list[str]:
        return sorted(values)

    added = _sorted(added)
    removed = _sorted(removed)
    match_changed = _sorted(match_changed)
    score_changed = _sorted(score_changed)
    display_changed = _sorted(display_changed)
    version_mismatch = _sorted(version_mismatch)
    unchanged = _sorted(unchanged)

    semantic_rematch_offer_ids = _sorted(added + removed + match_changed)
    forced_version_rematch_offer_ids = _sorted(version_mismatch)
    rematch_offer_ids = _sorted(added + removed + match_changed + version_mismatch)
    rescore_offer_ids = _sorted(score_changed)
    display_only_offer_ids = _sorted(display_changed)

    return {
        "added_offer_ids": added,
        "removed_offer_ids": removed,
        "match_changed_offer_ids": match_changed,
        "score_changed_offer_ids": score_changed,
        "display_changed_offer_ids": display_changed,
        "version_mismatch_offer_ids": version_mismatch,
        "unchanged_offer_ids": unchanged,
        "semantic_rematch_offer_ids": semantic_rematch_offer_ids,
        "forced_version_rematch_offer_ids": forced_version_rematch_offer_ids,
        "rematch_offer_ids": rematch_offer_ids,
        "rescore_offer_ids": rescore_offer_ids,
        "display_only_offer_ids": display_only_offer_ids,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "match_changed": len(match_changed),
            "score_changed": len(score_changed),
            "display_changed": len(display_changed),
            "version_mismatch": len(version_mismatch),
            "unchanged": len(unchanged),
            "semantic_rematch": len(semantic_rematch_offer_ids),
            "forced_version_rematch": len(forced_version_rematch_offer_ids),
            "rematch": len(rematch_offer_ids),
            "rescore": len(rescore_offer_ids),
            "display_only": len(display_only_offer_ids),
        },
    }


def classify_current_offer_changes(
    offers: list[Offer],
    *,
    compiler_version: str = OFFER_COMPILER_VERSION,
) -> dict[str, Any]:
    """Compare current offers against persisted compiled offers for delta prep."""
    current_rows_by_offer_id = {
        build_offer_identity_key(offer): build_compiled_offer_match_row(offer, compiler_version=compiler_version)
        for offer in offers
    }
    persisted_rows_by_offer_id = load_compiled_offer_match_map()
    summary = classify_offer_change_sets(current_rows_by_offer_id, persisted_rows_by_offer_id)
    summary.update({
        "compiler_version": compiler_version,
        "current_offer_count": len(current_rows_by_offer_id),
        "persisted_offer_count": len(persisted_rows_by_offer_id),
    })
    return summary


def load_compiled_offer_runtime_cache(
    offers: list[Offer],
    *,
    compiler_version: str = OFFER_COMPILER_VERSION,
    strict: bool = True,
) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
    """Load compiled offer payloads for the current Offer objects.

    Returns a cache keyed by ``id(offer)`` so the existing cache rebuild path
    can consume the persistent offer IR without changing the hot-loop API.
    """
    ensure_compiled_offer_match_table()

    offer_identity_keys = [build_offer_identity_key(offer) for offer in offers]
    if not offer_identity_keys:
        return {}, {
            "compiler_version": compiler_version,
            "loaded": 0,
            "missing_offer_ids": [],
            "stale_offer_ids": [],
        }

    with get_db_session() as db:
        rows = db.query(CompiledOfferMatchData).filter(
            CompiledOfferMatchData.offer_identity_key.in_(offer_identity_keys)
        ).all()

    row_by_offer_identity_key = {row.offer_identity_key: row for row in rows}
    runtime_cache = {}
    missing_offer_ids = []
    stale_offer_ids = []

    for offer in offers:
        offer_identity_key = build_offer_identity_key(offer)
        row = row_by_offer_identity_key.get(offer_identity_key)
        if row is None:
            missing_offer_ids.append(offer_identity_key)
            continue
        if row.compiler_version != compiler_version:
            stale_offer_ids.append(offer_identity_key)
            continue
        runtime_cache[id(offer)] = row.compiled_data

    stats = {
        "compiler_version": compiler_version,
        "loaded": len(runtime_cache),
        "missing_offer_ids": missing_offer_ids,
        "stale_offer_ids": stale_offer_ids,
    }

    if strict and (missing_offer_ids or stale_offer_ids):
        raise RuntimeError(
            "compiled_offer_match_data is missing or stale for current offers: "
            f"missing={len(missing_offer_ids)}, stale={len(stale_offer_ids)}"
        )

    return runtime_cache, stats
