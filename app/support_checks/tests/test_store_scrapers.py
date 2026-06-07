from __future__ import annotations

import unittest

from scrapers.stores.willys import WillysStore


class WillysScraperTests(unittest.TestCase):
    def test_campaign_parser_keeps_imported_meat_for_preference_filtering(self) -> None:
        scraper = WillysStore()
        product = scraper._parse_campaign_product(
            {
                "name": "Dry Age Beef Burger Fryst",
                "manufacturer": "Theburgervault",
                "price": "79,90",
                "priceUnit": "kr/st",
                "displayVolume": "2x150g",
                "potentialPromotions": [
                    {
                        "description": "",
                        "savePrice": "Spara 20,00",
                        "mainProductCode": "123456",
                    }
                ],
            }
        )

        self.assertIsNotNone(product)
        assert product is not None
        self.assertEqual(product["name"], "Dry Age Beef Burger Fryst Theburgervault")
        self.assertEqual(product["brand"], "THEBURGERVAULT")
        self.assertGreater(product["savings"], 0)


if __name__ == "__main__":
    unittest.main()
