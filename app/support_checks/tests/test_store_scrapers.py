from __future__ import annotations

import unittest

from languages.sv.category_utils import guess_category
from scrapers.stores.hemkop import HemkopStore
from scrapers.stores.willys import WillysStore


class CategoryUtilityTests(unittest.TestCase):
    def test_mini_watermelon_reclassifies_from_beverages_to_fruit(self) -> None:
        self.assertEqual(guess_category("Melon Mini Vatten Eko Klass 1", "dryck|vatten"), "fruit")
        self.assertEqual(guess_category("Vattenmelon Mini Eko Klass 1", "beverages"), "fruit")
        self.assertEqual(guess_category("Vatten Kolsyrad Melon 1,5l", "beverages"), "beverages")


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

    def test_campaign_parser_reclassifies_mini_watermelon_as_fruit(self) -> None:
        scraper = WillysStore()
        product = scraper._parse_campaign_product(
            {
                "name": "Melon Mini Vatten Eko Klass 1",
                "price": "29,90",
                "priceUnit": "kr/st",
                "googleAnalyticsCategory": "dryck|vatten",
                "potentialPromotions": [
                    {
                        "description": "",
                        "savePrice": "Spara 10,00",
                        "mainProductCode": "987654",
                    }
                ],
            }
        )

        self.assertIsNotNone(product)
        assert product is not None
        self.assertEqual(product["category"], "fruit")


class HemkopScraperTests(unittest.TestCase):
    def test_campaign_parser_reclassifies_mini_watermelon_as_fruit(self) -> None:
        scraper = HemkopStore()
        product = scraper._parse_campaign_product(
            {
                "name": "Melon Mini Vatten Eko Klass 1",
                "price": "29,90",
                "priceUnit": "kr/st",
                "googleAnalyticsCategory": "dryck|vatten",
                "potentialPromotions": [
                    {
                        "price": {"value": 19.90},
                        "mainProductCode": "987654",
                    }
                ],
            }
        )

        self.assertIsNotNone(product)
        assert product is not None
        self.assertEqual(product["category"], "fruit")


if __name__ == "__main__":
    unittest.main()
