#!/usr/bin/env python3
"""Print review samples for Swedish ingredient exclusion profiles.

This is intentionally an audit helper, not a pass/fail gate. The profiles are
best-effort and need a human glance over current offers/recipes before release.
"""

from __future__ import annotations

from argparse import ArgumentParser
from collections import defaultdict
import os
import sys


sys.path.insert(0, "/app" if os.path.exists("/app") else os.path.join(os.path.dirname(__file__), ".."))

from database import get_db_session  # noqa: E402
from models import FoundRecipe, Offer  # noqa: E402
from languages.sv.ingredient_matching.dietary_exclusions import (  # noqa: E402
    compile_recipe_ingredient_exclusion_flags,
    ingredient_exclusion_hits_for_ingredient_text,
    ingredient_exclusion_hits_for_offer,
)


PROFILES = ("gluten", "nuts", "shellfish", "egg", "soy", "lactose")


def _sample_offer_hits(sample_size: int, scan_limit: int):
    hits = defaultdict(list)
    with get_db_session() as db:
        query = (
            db.query(Offer)
            .filter((Offer.savings.isnot(None)) & (Offer.savings > 0))
            .order_by(Offer.name)
            .limit(scan_limit)
        )
        for offer in query.all():
            for hit in ingredient_exclusion_hits_for_offer(
                offer.name,
                category=offer.category or "",
                brand=offer.brand or "",
            ):
                if len(hits[hit.profile]) < sample_size:
                    hits[hit.profile].append({
                        "name": offer.name,
                        "category": offer.category or "",
                        "brand": offer.brand or "",
                        "source": hit.source,
                        "evidence": hit.evidence,
                    })
    return hits


def _sample_recipe_hits(sample_size: int, scan_limit: int):
    hits = defaultdict(list)
    with get_db_session() as db:
        query = (
            db.query(FoundRecipe)
            .filter((FoundRecipe.excluded == False) | (FoundRecipe.excluded.is_(None)))  # noqa: E712
            .order_by(FoundRecipe.name)
            .limit(scan_limit)
        )
        for recipe in query.all():
            flags = compile_recipe_ingredient_exclusion_flags(recipe.ingredients or [])
            for profile in flags:
                if len(hits[profile]) < sample_size:
                    matching_ingredients = []
                    for ingredient in recipe.ingredients or []:
                        ingredient_hits = [
                            hit for hit in ingredient_exclusion_hits_for_ingredient_text(str(ingredient))
                            if hit.profile == profile
                        ]
                        if ingredient_hits:
                            matching_ingredients.append({
                                "text": str(ingredient),
                                "hits": [
                                    f"{hit.source}:{hit.evidence}"
                                    for hit in ingredient_hits
                                ],
                            })
                    hits[profile].append({
                        "name": recipe.name,
                        "source": recipe.source_name or "",
                        "ingredients": matching_ingredients[:6],
                    })
    return hits


def _print_samples(title: str, samples_by_profile) -> None:
    print(f"\n=== {title} ===")
    for profile in PROFILES:
        samples = samples_by_profile.get(profile, [])
        print(f"\n[{profile}] {len(samples)} sample(s)")
        for sample in samples:
            if "ingredients" in sample:
                print(f"  - {sample['name']} ({sample['source']})")
                for ingredient in sample["ingredients"]:
                    print(f"    - {ingredient['text']} ({', '.join(ingredient['hits'])})")
            else:
                brand = f", brand={sample['brand']}" if sample["brand"] else ""
                print(
                    f"  - {sample['name']} "
                    f"(category={sample['category']}{brand}; "
                    f"{sample['source']}:{sample['evidence']})"
                )


def main() -> int:
    parser = ArgumentParser()
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--offer-scan-limit", type=int, default=5000)
    parser.add_argument("--recipe-scan-limit", type=int, default=3000)
    args = parser.parse_args()

    offer_hits = _sample_offer_hits(args.sample_size, args.offer_scan_limit)
    recipe_hits = _sample_recipe_hits(args.sample_size, args.recipe_scan_limit)

    print("Dietary exclusion profile audit")
    print("Review these samples manually before release; this script is not a gate.")
    print("Store categories are shown for context only and are not used as profile rules.")
    _print_samples("Offer Profile Hits", offer_hits)
    _print_samples("Recipe Profile Hits", recipe_hits)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
