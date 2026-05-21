#!/usr/bin/env python3
"""Checks for the Mathem store SSR discount parser."""

from __future__ import annotations

import json
from pathlib import Path
import sys


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from scrapers.stores.mathem import (  # noqa: E402
    MathemStore,
    extract_mathem_next_data,
    find_mathem_discount_page_data,
    iter_mathem_discount_products,
    mathem_ssr_product_to_raw,
)


def check(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"OK {name}")


def _fixture_payload() -> dict:
    direct_product = {
        "id": 4830,
        "fullName": "Trocadero Zero Sugar",
        "brand": "Trocadero",
        "nameExtra": "1,5 l",
        "frontUrl": "https://www.mathem.se/se/products/4830-trocadero-trocadero-zero-sugar/",
        "grossPrice": "15.00",
        "unitPriceQuantityAbbreviation": "l",
        "discount": {
            "descriptionShort": "Extrapris",
            "undiscountedGrossPrice": "20.35",
        },
        "images": [
            {
                "large": {
                    "url": "https://images.mathem.se/prod/trocadero.jpg",
                    "width": 300,
                    "height": 900,
                },
            },
        ],
    }
    multi_buy_product = {
        "id": 15387,
        "fullName": "Garant Krossade Tomater",
        "brand": "Garant",
        "nameExtra": "400 g",
        "absoluteUrl": "/se/products/15387-garant-krossade-tomater/",
        "grossPrice": "13.72",
        "unitPriceQuantityAbbreviation": "st",
        "discount": {
            "descriptionShort": "2 för 15\u00a0kr",
            "undiscountedGrossPrice": "13.72",
        },
        "images": [
            {
                "thumbnail": {
                    "url": "https://images.mathem.se/prod/tomater.jpg",
                    "width": 92,
                    "height": 92,
                },
            },
        ],
    }
    return {
        "props": {
            "pageProps": {
                "dehydratedState": {
                    "queries": [
                        {"state": {"data": {"ignored": True}}},
                        {
                            "state": {
                                "data": {
                                    "blocks": [
                                        {"component": "page-header", "title": "Extrapris"},
                                        {
                                            "component": "product-grid",
                                            "products": [direct_product, multi_buy_product, direct_product],
                                            "items": [{"itemType": "not-product", "item": {}}],
                                        },
                                    ]
                                }
                            }
                        },
                    ]
                }
            }
        }
    }


def main() -> int:
    payload = _fixture_payload()
    html = (
        "<html><head><script id=\"__NEXT_DATA__\" type=\"application/json\">"
        f"{json.dumps(payload)}"
        "</script></head><body></body></html>"
    )

    next_data = extract_mathem_next_data(html)
    check("Next.js data extracted", isinstance(next_data, dict), True)

    page_data = find_mathem_discount_page_data(next_data or {})
    check("Discount page data found", isinstance(page_data, dict), True)

    raw_records = iter_mathem_discount_products(page_data or {})
    check("Duplicate SSR products deduped", len(raw_records), 2)

    raw_multi = mathem_ssr_product_to_raw(raw_records[1])
    check("Multi-buy quantity parsed", raw_multi["multi_buy_quantity"], 2)
    check("Multi-buy total parsed", raw_multi["multi_buy_price"], 15.0)
    check(
        "Relative product URL made absolute",
        raw_multi["url"],
        "https://www.mathem.se/se/products/15387-garant-krossade-tomater/",
    )

    store = MathemStore()
    products, diagnostics = store._parse_ssr_discount_products(page_data or {})
    check("SSR product count parsed", len(products), 2)
    check("SSR raw count diagnostic", diagnostics["raw_product_count"], 2)
    check("SSR parsed count diagnostic", diagnostics["parsed_product_count"], 2)

    direct = products[0]
    check("Direct discount current price", direct["price"], 15.0)
    check("Direct discount original price", direct["original_price"], 20.35)
    check("Direct discount savings", direct["savings"], 5.35)
    check("Direct discount brand normalized", direct["brand"], "TROCADERO")
    check("Direct discount image carried", direct["image_url"], "https://images.mathem.se/prod/trocadero.jpg")

    multi = products[1]
    check("Multi-buy unit price", multi["price"], 7.5)
    check("Multi-buy original price", multi["original_price"], 13.72)
    check("Multi-buy savings", multi["savings"], 6.22)
    check("Multi-buy flag", multi["is_multi_buy"], True)
    check("Multi-buy quantity", multi["multi_buy_quantity"], 2)

    print("ALL MATHEM STORE SSR CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
