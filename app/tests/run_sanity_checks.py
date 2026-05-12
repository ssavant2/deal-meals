#!/usr/bin/env python3
"""Quick app support sanity checks.

This is the small, tracked "must not be broken" suite. It intentionally avoids
pytest, the database, live scraping, and benchmark fixtures so it can run in the
normal web container.

Run:
    docker compose exec -T -w /app web python tests/run_sanity_checks.py
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, '/app' if os.path.exists('/app') else os.path.join(os.path.dirname(__file__), '..'))

from loguru import logger  # noqa: E402
from languages.sv.ingredient_matching import (  # noqa: E402
    build_ingredient_match_data,
    build_offer_match_data,
    match_offer_to_ingredient,
    precompute_offer_data,
)
from recipe_matcher import RecipeMatcher  # noqa: E402
from scrapers.stores import get_all_stores, get_store_discovery_errors  # noqa: E402


for noisy_module in ("app", "recipe_scraper_manager", "scrapers.stores"):
    logger.disable(noisy_module)

passed = 0
failed = 0


def test(desc: str, actual, expected) -> None:
    global passed, failed
    if actual == expected:
        passed += 1
        return
    failed += 1
    print(f"FAIL: {desc}")
    print(f"  got:      {actual}")
    print(f"  expected: {expected}")


def _offer_obj(offer: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id='sanity-offer',
        name=offer['name'],
        category=offer.get('category', ''),
        brand=offer.get('brand', ''),
        price=offer.get('price', 0),
        original_price=offer.get('original_price'),
        savings=offer.get('savings', 0),
        store=None,
        product_url=None,
        is_multi_buy=False,
        multi_buy_quantity=None,
        weight_grams=offer.get('weight_grams'),
    )


def _audit_match_num(ingredient: str, offer: dict) -> int:
    ingredient_data = build_ingredient_match_data(ingredient)
    offer_data = build_offer_match_data(
        offer['name'],
        offer.get('category', ''),
        brand=offer.get('brand', ''),
        weight_grams=offer.get('weight_grams'),
    )
    return 1 if match_offer_to_ingredient(ingredient_data, offer_data).matched else 0


def _recipe_match_num(
    ingredients: list[str],
    offer: dict,
    *,
    cached: bool,
    recipe_name: str = "Sanity Recipe",
) -> int:
    matcher = RecipeMatcher()
    recipe = SimpleNamespace(
        id='sanity-recipe',
        name=recipe_name,
        ingredients=ingredients,
    )
    offer_obj = _offer_obj(offer)

    kwargs = {}
    if cached:
        offer_key = id(offer_obj)
        offer_data = precompute_offer_data(
            offer_obj.name,
            offer_obj.category,
            brand=offer_obj.brand,
            weight_grams=offer_obj.weight_grams,
        )
        kwargs["offer_keywords"] = {offer_key: tuple(offer_data.get("keywords", ()))}
        kwargs["offer_data_cache"] = {offer_key: offer_data}

    return matcher._match_recipe_to_offers(
        recipe,
        [offer_obj],
        preferences={},
        **kwargs,
    )["num_matches"]


def _run_matching_sanity_checks() -> None:
    cases = [
        {
            "name": "fiberhusk exact product stays aligned",
            "ingredients": ["0.5 dl Fiberhusk"],
            "offer": {
                "name": "Fiberhusk Glutenfri 300g Husk",
                "category": "pantry",
                "brand": "FIBERHUSK",
            },
            "expected": 1,
        },
        {
            "name": "dark chocolate bars stay aligned",
            "ingredients": ["100 g Mörk chokladkaka"],
            "offer": {
                "name": "Chokladkaka EXCELLENCE 70% Kakao Mörk Choklad 100g Lindt",
                "category": "candy",
            },
            "expected": 1,
        },
        {
            "name": "porter still does not widen to light beer",
            "ingredients": ["33 cl porter eller annan mörk öl"],
            "offer": {
                "name": "Lättöl 2,1% 33cl Grängesberg",
                "category": "beverages",
                "brand": "GRÄNGESBERG",
            },
            "expected": 0,
        },
        {
            "name": "fresh oregano blocks household seed packets",
            "ingredients": ["1/2 kruka färsk oregano, plockade blad"],
            "offer": {
                "name": "Oregano Grekisk 1-p Nelson Garden",
                "category": "household",
            },
            "expected": 0,
        },
        {
            "name": "fresh oregano matches a fresh herb offer",
            "ingredients": ["1/2 kruka färsk oregano, plockade blad"],
            "offer": {
                "name": "Oregano i kruka Klass 1 Test",
                "category": "vegetables",
            },
            "expected": 1,
        },
    ]

    print("\n--- matching sanity: audit/full/cached parity ---", flush=True)
    for case in cases:
        ingredient_text = case["ingredients"][0]
        expected = case["expected"]
        audit_val = _audit_match_num(ingredient_text, case["offer"])
        full_val = _recipe_match_num(case["ingredients"], case["offer"], cached=False)
        cached_val = _recipe_match_num(case["ingredients"], case["offer"], cached=True)

        test(f"{case['name']} audit", audit_val, expected)
        test(f"{case['name']} full", full_val, expected)
        test(f"{case['name']} cached", cached_val, expected)
        test(f"{case['name']} audit/full parity", audit_val, full_val)
        test(f"{case['name']} audit/cached parity", audit_val, cached_val)


def _run_store_discovery_sanity_checks() -> None:
    print("\n--- store plugin discovery ---", flush=True)
    stores = get_all_stores()
    discovery_errors = get_store_discovery_errors()
    store_ids = [store.config.id for store in stores]

    test("store plugin discovery has no import/init errors", discovery_errors, [])
    test("store plugin IDs are unique", len(store_ids), len(set(store_ids)))


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.deleted = []
        self.executed = []
        self.committed = False

    def query(self, _model):
        return FakeQuery(self.rows)

    def add(self, _row):
        raise AssertionError("unexpected add")

    def delete(self, row):
        self.deleted.append(row)

    def execute(self, statement, params):
        self.executed.append((str(statement), params))
        return SimpleNamespace(rowcount=1)

    def commit(self):
        self.committed = True


def _run_store_registry_sanity_checks() -> None:
    print("\n--- store registry startup cleanup ---", flush=True)
    import app as deal_app  # noqa: E402

    def run_with_fake_session(session: FakeSession, discovery_errors: list[dict]) -> None:
        @contextmanager
        def fake_db_session():
            yield session

        original_get_db_session = deal_app.get_db_session
        deal_app.get_db_session = fake_db_session
        try:
            deal_app._sync_store_registry([], discovery_errors=discovery_errors)
        finally:
            deal_app.get_db_session = original_get_db_session

    skipped = FakeSession([SimpleNamespace(store_type="removed_store")])
    run_with_fake_session(
        skipped,
        [{"module": "broken_store", "phase": "import", "error": "ImportError('boom')"}],
    )
    test("discovery errors skip store deletion", skipped.deleted, [])
    test("discovery errors skip schedule cleanup", skipped.executed, [])
    test("discovery errors do not commit destructive cleanup", skipped.committed, False)

    clean = FakeSession([SimpleNamespace(store_type="removed_store")])
    run_with_fake_session(clean, [])
    test("clean discovery deletes removed store row", [row.store_type for row in clean.deleted], ["removed_store"])
    test(
        "clean discovery deletes removed store schedule",
        clean.executed,
        [
            (
                "DELETE FROM store_schedules WHERE store_id = :store_id",
                {"store_id": "removed_store"},
            )
        ],
    )
    test("clean discovery commits cleanup", clean.committed, True)


def _run_recipe_source_registry_sanity_checks() -> None:
    print("\n--- recipe source registry ---", flush=True)
    import recipe_scraper_manager as rsm  # noqa: E402

    class FakeRegistrySession:
        def __init__(self):
            self.executed = []
            self.committed = False

        def execute(self, statement, params=None):
            self.executed.append((str(statement), params))
            return SimpleNamespace(rowcount=1)

        def commit(self):
            self.committed = True

    session = FakeRegistrySession()

    @contextmanager
    def fake_db_session():
        yield session

    original_get_db_session = rsm.get_db_session
    rsm.get_db_session = fake_db_session
    try:
        registered = rsm.scraper_manager.ensure_scraper_registered("myrecipes")
    finally:
        rsm.get_db_session = original_get_db_session

    insert_params = session.executed[0][1] if session.executed else {}
    test("myrecipes source can self-register", registered, True)
    test("myrecipes registry name", insert_params.get("name"), "My Recipes")
    test("myrecipes registry fallback URL", insert_params.get("url"), "https://my-recipes")
    test("myrecipes registry default enabled", insert_params.get("enabled"), True)
    test("myrecipes registry commits insert", session.committed, True)


def _run_pantry_input_validation_checks() -> None:
    print("\n--- pantry input validation ---", flush=True)
    from routers.pantry import _extract_raw_ingredients  # noqa: E402

    test("pantry rejects non-object JSON", _extract_raw_ingredients([]), (None, "error.invalid_data"))
    test(
        "pantry rejects non-string ingredients",
        _extract_raw_ingredients({"ingredients": []}),
        (None, "error.invalid_data"),
    )
    test(
        "pantry keeps empty string as no ingredients",
        _extract_raw_ingredients({"ingredients": "   "}),
        (None, "pantry.no_ingredients"),
    )
    test(
        "pantry accepts string ingredients",
        _extract_raw_ingredients({"ingredients": "pasta, tomat"}),
        ("pasta, tomat", None),
    )


def _run_json_payload_validation_checks() -> None:
    print("\n--- JSON payload validation ---", flush=True)
    from routers.preferences import (  # noqa: E402
        _extract_delivery_address_payload,
        _extract_ui_preferences_payload,
    )
    from routers.ssl import (  # noqa: E402
        _content_length_over_limit,
        _extract_ssl_enabled_payload,
        _extract_ssl_upload_payload,
    )
    from routers.stores import _extract_store_config_payload  # noqa: E402

    test(
        "delivery address rejects non-object JSON",
        _extract_delivery_address_payload([]),
        (None, None, None, "error.invalid_data", 400),
    )
    test(
        "delivery address rejects non-string fields",
        _extract_delivery_address_payload({"street_address": [], "postal_code": "12345", "city": "X"}),
        (None, None, None, "error.invalid_data", 400),
    )
    test(
        "delivery address keeps required-field validation",
        _extract_delivery_address_payload({"street_address": "", "postal_code": "12345", "city": "X"}),
        (None, None, None, "preferences.street_required", 422),
    )
    test(
        "delivery address trims valid fields",
        _extract_delivery_address_payload({
            "street_address": "  Main 1 ",
            "postal_code": " 12345 ",
            "city": " City ",
        }),
        ("Main 1", "12345", "City", None, 200),
    )
    test("UI preferences rejects non-object JSON", _extract_ui_preferences_payload([]), (None, "error.invalid_data"))
    test("UI preferences accepts object JSON", _extract_ui_preferences_payload({"sort": "savings"}), ({"sort": "savings"}, None))

    test("store config rejects non-object JSON", _extract_store_config_payload([]), (None, "error.invalid_data"))
    test("store config rejects non-object config", _extract_store_config_payload({"config": []}), (None, "error.invalid_data"))
    test("store config accepts direct object", _extract_store_config_payload({"location_id": "1"}), ({"location_id": "1"}, None))
    test("store config accepts nested object", _extract_store_config_payload({"config": {"location_id": "1"}}), ({"location_id": "1"}, None))

    test("SSL upload rejects non-object JSON", _extract_ssl_upload_payload([]), (None, None, "error.invalid_data"))
    test("SSL upload keeps missing cert/key validation", _extract_ssl_upload_payload({}), (None, None, "ssl.cert_and_key_required"))
    test("SSL upload rejects non-string cert/key", _extract_ssl_upload_payload({"cert": [], "key": "key"}), (None, None, "error.invalid_data"))
    test("SSL upload accepts string cert/key", _extract_ssl_upload_payload({"cert": "cert", "key": "key"}), (b"cert", b"key", None))
    test("SSL enable rejects non-object JSON", _extract_ssl_enabled_payload([]), (None, "error.invalid_data"))
    test("SSL enable rejects non-boolean value", _extract_ssl_enabled_payload({"enabled": "true"}), (None, "error.invalid_data"))
    test("SSL enable keeps missing value as false", _extract_ssl_enabled_payload({}), (False, None))
    test("SSL enable accepts boolean value", _extract_ssl_enabled_payload({"enabled": True}), (True, None))
    test("SSL content length ignores malformed header", _content_length_over_limit("not-a-number", 100), False)
    test("SSL content length blocks oversized upload", _content_length_over_limit("101", 100), True)


def _run_myrecipes_playwright_security_checks() -> None:
    print("\n--- myrecipes playwright request safety ---", flush=True)
    from scrapers.recipes import myrecipes_scraper  # noqa: E402

    calls = []

    def fake_is_safe_url(url: str) -> bool:
        calls.append(url)
        return "public.example" in url

    original_is_safe_url = myrecipes_scraper.is_safe_url
    myrecipes_scraper.is_safe_url = fake_is_safe_url
    try:
        cache = {}
        test(
            "myrecipes allows non-network playwright data url",
            myrecipes_scraper._is_playwright_request_url_allowed("data:text/plain,hello", cache),
            True,
        )
        test("myrecipes non-network url skips ssrf check", calls, [])
        test(
            "myrecipes allows safe public playwright request",
            myrecipes_scraper._is_playwright_request_url_allowed("https://public.example/app.js", cache),
            True,
        )
        test(
            "myrecipes blocks unsafe playwright request",
            myrecipes_scraper._is_playwright_request_url_allowed("http://127.0.0.1/admin", cache),
            False,
        )
        myrecipes_scraper._is_playwright_request_url_allowed("https://public.example/other.js", cache)
        test(
            "myrecipes caches playwright host safety checks",
            calls,
            ["https://public.example/app.js", "http://127.0.0.1/admin"],
        )
    finally:
        myrecipes_scraper.is_safe_url = original_is_safe_url


def _run_term_registry_gate_checks() -> None:
    print("\n--- term registry R4 gate ---", flush=True)
    from tests.run_term_registry_contract_checks import (  # noqa: E402
        DEFAULT_BASELINE_JSON,
        DEFAULT_SHARED_REGISTRY_DIR,
        run_checks,
    )

    payload, issues = run_checks(SimpleNamespace(
        language="sv",
        market="SE",
        batch_size=60,
        baseline_json=DEFAULT_BASELINE_JSON,
        shared_registry_dir=DEFAULT_SHARED_REGISTRY_DIR,
    ))
    error_codes = [issue.code for issue in issues if issue.severity == "error"]
    new_term_gate = payload["summary"].get("new_term_gate", {})
    test("term registry contract check passes", error_codes, [])
    test("term registry new legacy key count", new_term_gate.get("new_legacy_coverage_keys"), 0)
    test("term registry R4 failure probe", new_term_gate.get("failure_probe_passed"), True)


def _run_term_registry_add_term_checks() -> None:
    print("\n--- term registry add-term export plan ---", flush=True)
    from tests.run_term_registry_add_term_checks import run_checks  # noqa: E402

    payload, issues = run_checks(SimpleNamespace(
        language="sv",
        market="SE",
        report_dir=Path("/tmp/term_registry_add_term_sanity"),
    ))
    error_codes = [issue.code for issue in issues if issue.severity == "error"]
    summary = payload["summary"]
    test("term registry add-term check passes", error_codes, [])
    test("term registry add-term coverage count", summary.get("unique_coverage_key_count"), 5335)
    test("term registry add-term layer count", summary.get("known_export_layer_count"), 25)


_run_matching_sanity_checks()
_run_store_discovery_sanity_checks()
_run_store_registry_sanity_checks()
_run_recipe_source_registry_sanity_checks()
_run_pantry_input_validation_checks()
_run_json_payload_validation_checks()
_run_myrecipes_playwright_security_checks()
_run_term_registry_gate_checks()
_run_term_registry_add_term_checks()

print("\n========================================", flush=True)
print(f"TOTAL: {passed}/{passed + failed} checks passed", flush=True)
if failed:
    print(f"{failed} FAILED!", flush=True)
    print("========================================", flush=True)
    raise SystemExit(1)

print("ALL PASSED!", flush=True)
print("========================================", flush=True)
