"""Manual smoke entry point for the Swedish ingredient matching package."""

from . import (
    extract_keywords_from_ingredient,
    extract_keywords_from_product,
    is_non_food_product,
    matches_ingredient,
)


def main() -> None:
    """Run a few quick manual smoke checks."""
    print("=== Testing Swedish Ingredient Matching ===\n")

    print("Test 1: Non-food detection")
    print(f"  Zinksalva: {is_non_food_product('Nappy Care Cream Zinksalva')}")
    print(f"  Kokosmjölk: {is_non_food_product('Kokosmjölk Extra Creamy')}")
    print()

    print("Test 2: Product keywords")
    print(f"  'Vispgrädde Laktosfri 40%': {extract_keywords_from_product('Vispgrädde Laktosfri 40%')}")
    print(f"  'Shot Gurkmeja Citron': {extract_keywords_from_product('Shot Gurkmeja Ingefara Citron')}")
    print(f"  'Gronsaks Buljong': {extract_keywords_from_product('Gronsaks Buljong Tarningar')}")
    print()

    print("Test 3: Ingredient keywords")
    print(f"  '2-3 msk grovt salt': {extract_keywords_from_ingredient('2-3 msk grovt salt')}")
    print(f"  'ca 1 kg laxfilé': {extract_keywords_from_ingredient('ca 1 kg laxfilé')}")
    print(f"  '1 st fiskbuljongtärning': {extract_keywords_from_ingredient('1 st fiskbuljongtärning')}")
    print()

    print("Test 4: Matching")
    product_kw = extract_keywords_from_product('Vispgrädde Laktosfri 40%')
    print(f"  Product keywords: {product_kw}")
    print(f"  Matches '1 dl vispgrädde': {matches_ingredient(product_kw, '1 dl vispgrädde')}")
    print(f"  Matches '1 dl grädde': {matches_ingredient(product_kw, '1 dl grädde')}")


if __name__ == "__main__":
    main()
