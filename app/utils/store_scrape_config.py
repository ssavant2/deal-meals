"""Shared validation for store offer scrape configuration."""

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import text


NO_DELIVERY_ADDRESS_REQUIRED = {"mathem"}
REQUIRES_EHANDEL_STORE = {"ica"}


@dataclass
class StoreScrapeConfigContext:
    """Store config, credentials and validation state for a scrape attempt."""

    store_id: str
    store_name: str
    db_store_id: Optional[Any]
    config: dict
    credentials: dict
    valid: bool = True
    message_key: Optional[str] = None
    message_params: dict = field(default_factory=dict)
    last_scrape_duration_ehandel: Optional[int] = None
    last_scrape_duration_butik: Optional[int] = None

    @property
    def location_type(self) -> str:
        return self.credentials.get("location_type", "ehandel")

    def error_response(self) -> dict:
        return {
            "success": False,
            "message_key": self.message_key,
            "message_params": self.message_params,
        }


def _has_value(value: Any) -> bool:
    return bool(str(value).strip()) if value is not None else False


def _delivery_address_is_complete(credentials: dict) -> bool:
    return all(
        _has_value(credentials.get(key))
        for key in ("delivery_street", "postal_code", "delivery_city")
    )


def _load_delivery_address(db) -> dict:
    result = db.execute(text("""
        SELECT delivery_street_address, delivery_postal_code, delivery_city
        FROM user_preferences
        LIMIT 1
    """)).mappings().fetchone()

    if not result:
        return {}

    return {
        "delivery_street": result["delivery_street_address"],
        "postal_code": result["delivery_postal_code"],
        "delivery_city": result["delivery_city"],
    }


def _build_credentials(config: dict, delivery_address: dict) -> dict:
    credentials = {
        "location_type": config.get("location_type", "ehandel"),
        "location_id": config.get("location_id"),
        "location_name": config.get("location_name"),
        "ehandel_store_id": config.get("ehandel_store_id"),
        "ehandel_store_name": config.get("ehandel_store_name"),
    }
    credentials.update(delivery_address)
    return credentials


def _validate_context(context: StoreScrapeConfigContext) -> None:
    store_id = context.store_id
    store_name = context.store_name
    location_type = context.location_type

    if location_type not in {"ehandel", "butik"}:
        context.valid = False
        context.message_key = "stores.invalid_store_config"
        context.message_params = {"store": store_name}
        return

    if location_type == "butik":
        if not _has_value(context.credentials.get("location_id")):
            context.valid = False
            context.message_key = "stores.missing_store_location"
            context.message_params = {"store": store_name}
        return

    if store_id not in NO_DELIVERY_ADDRESS_REQUIRED and not _delivery_address_is_complete(context.credentials):
        context.valid = False
        context.message_key = "stores.missing_delivery_address"
        context.message_params = {"store": store_name}
        return

    if store_id in REQUIRES_EHANDEL_STORE and not _has_value(context.credentials.get("ehandel_store_id")):
        context.valid = False
        context.message_key = "stores.missing_ehandel_store"
        context.message_params = {"store": store_name}


def build_store_scrape_config_context(
    db,
    store_id: str,
    *,
    config_override: Optional[dict] = None,
    store_name: Optional[str] = None,
) -> StoreScrapeConfigContext:
    """
    Load and validate the config needed to scrape a store.

    config_override is used by scheduled jobs to validate their saved snapshot.
    Delivery address is always read live, since it is not stored in schedule snapshots.
    """
    store_id = store_id.lower()
    store_row = db.execute(text("""
        SELECT id, name, config,
               last_scrape_duration_ehandel, last_scrape_duration_butik
        FROM stores
        WHERE store_type = :store_type
    """), {"store_type": store_id}).mappings().fetchone()

    loaded_config = {}
    if store_row and store_row["config"]:
        loaded_config = store_row["config"] if isinstance(store_row["config"], dict) else {}

    config = config_override if config_override is not None else loaded_config
    if not isinstance(config, dict):
        config = {}

    display_name = store_name or (store_row["name"] if store_row else store_id.capitalize())
    credentials = _build_credentials(config, _load_delivery_address(db))

    context = StoreScrapeConfigContext(
        store_id=store_id,
        store_name=display_name,
        db_store_id=store_row["id"] if store_row else None,
        config=config,
        credentials=credentials,
        last_scrape_duration_ehandel=store_row["last_scrape_duration_ehandel"] if store_row else None,
        last_scrape_duration_butik=store_row["last_scrape_duration_butik"] if store_row else None,
    )
    _validate_context(context)
    return context
