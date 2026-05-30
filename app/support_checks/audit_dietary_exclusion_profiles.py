#!/usr/bin/env python3
"""Audit Swedish ingredient exclusion profiles.

By default this prints review samples. With ``--check`` it also performs a
scripted corpus audit for high-confidence mistakes such as gluten-free products
being flagged as gluten or obvious cues like vetemjöl being missed.
"""

from __future__ import annotations

from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import asdict, dataclass
import json
import os
import re
import sys
from typing import Iterable


sys.path.insert(0, "/app" if os.path.exists("/app") else os.path.join(os.path.dirname(__file__), ".."))

from database import get_db_session  # noqa: E402
from models import FoundRecipe, Offer  # noqa: E402
from languages.sv.ingredient_matching.dietary_exclusions import (  # noqa: E402
    compile_recipe_ingredient_exclusion_flags,
    ingredient_exclusion_hits_for_ingredient_text,
    ingredient_exclusion_hits_for_offer,
)


PROFILES = ("gluten", "nuts", "shellfish", "egg", "soy", "lactose")

_WORD_CHARS = "a-zåäöéèüA-ZÅÄÖÉÈÜ"


@dataclass(frozen=True)
class AuditFinding:
    severity: str
    area: str
    profile: str
    item: str
    evidence: str
    message: str


@dataclass(frozen=True)
class AuditSummary:
    offer_hits: dict[str, int]
    recipe_hits: dict[str, int]
    scanned_offers: int
    scanned_recipes: int
    findings: list[AuditFinding]


_STATIC_OFFER_CASES = (
    ("gluten", "Pasta Fusilli 500g", "pantry", "", True),
    ("gluten", "Vetemjöl Special 2kg", "pantry", "", True),
    ("gluten", "Glutenfri Pasta 500g", "pantry", "", False),
    ("gluten", "Rispasta 400g", "pantry", "", False),
    ("gluten", "Glasnudlar 100g", "pantry", "", False),
    ("nuts", "Cashewnötter 200g", "pantry", "", True),
    ("nuts", "Jordnötssmör 350g", "pantry", "", True),
    ("nuts", "Nötfärs 500g", "meat", "", False),
    ("nuts", "Muskotnöt Hel 20g", "spices", "", False),
    ("shellfish", "Räkor Handskalade 300g", "fish", "", True),
    ("shellfish", "Skagenröra 200g", "deli", "", True),
    ("shellfish", "Laxfilé 500g", "fish", "", False),
    ("egg", "Ägg 12-pack", "dairy", "", True),
    ("egg", "Äggnudlar 250g", "pantry", "", True),
    ("soy", "Sojasås Japansk 150ml", "pantry", "", True),
    ("soy", "Tofu Naturell 250g", "pantry", "", True),
    ("lactose", "Mjölk 1L Arla", "dairy", "", True),
    ("lactose", "Crème Fraiche Parmesan 2dl", "dairy", "", True),
    ("lactose", "Mozzarella 125g", "dairy", "", True),
    ("lactose", "Mjölk Laktosfri 1L Arla", "dairy", "", False),
    ("lactose", "Kokosmjölk 200ml", "dairy", "", False),
    ("lactose", "TUC Original 100g", "dairy", "", False),
)

_STATIC_RECIPE_CASES = (
    ("gluten", "2 dl vetemjöl", True),
    ("gluten", "250 g pasta fusilli", True),
    ("gluten", "1 dl glutenfritt mjöl", False),
    ("gluten", "100 g risnudlar", False),
    ("nuts", "1 dl cashewnötter", True),
    ("nuts", "400 g nötfärs", False),
    ("shellfish", "300 g räkor", True),
    ("shellfish", "300 g lax", False),
    ("egg", "2 ägg", True),
    ("soy", "1 msk japansk soja", True),
    ("lactose", "2 dl vispgrädde", True),
    ("lactose", "2 dl laktosfri grädde", False),
)

_MUST_HIT_CUES = {
    "gluten": (
        "gluten", "vetemjöl", "vetemjol", "rågmjöl", "ragmjol",
        "durumvete", "ströbröd", "strobrod", "panko", "bulgur",
        "couscous",
    ),
    "nuts": (
        "jordnöt", "jordnot", "cashewnöt", "cashewnot", "valnöt",
        "valnot", "hasselnöt", "hasselnot", "pistagenöt", "pistagenot",
        "pekannöt", "pekannot", "pinjenöt", "pinjenot", "mandel",
        "nötsmör", "notsmor",
    ),
    "shellfish": (
        "räka", "raka", "räkor", "rakor", "kräft", "kraft", "hummer",
        "krabba", "mussla", "musslor", "ostron", "skagenröra",
        "skagenrora", "räkost", "rakost",
    ),
    "egg": ("ägg", "agg", "äggula", "aggula", "äggvita", "aggvita"),
    "soy": ("soja", "tofu", "tempeh", "edamame"),
    "lactose": (
        "mjölk", "mjolk", "grädde", "gradde", "vispgrädde", "vispgradde",
        "crème fraiche", "creme fraiche", "yoghurt", "kvarg", "keso",
        "färskost", "farskost", "mjukost", "mozzarella", "ricotta",
        "mascarpone", "halloumi",
    ),
}

_MUST_NOT_HIT_CUES = {
    "gluten": (
        "glutenfri", "glutenfritt", "glutenfria", "rispasta",
        "risnudlar", "glasnudlar",
    ),
    "nuts": ("nötfärs", "notfars", "muskotnöt", "muskotnot"),
    "lactose": ("laktosfri", "laktosfritt", "laktosfria", "kokosmjölk", "kokosmjolk"),
}


def _normalize(text: str) -> str:
    return (text or "").lower()


def _word_re(cue: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![{_WORD_CHARS}]){re.escape(cue)}(?![{_WORD_CHARS}])", re.IGNORECASE)


def _has_word(text: str, cue: str) -> bool:
    return bool(_word_re(cue).search(text))


def _matching_cue(text: str, cues: Iterable[str]) -> str | None:
    normalized = _normalize(text)
    for cue in sorted(cues, key=len, reverse=True):
        if _has_word(normalized, cue):
            return cue
    return None


def _hit_profiles_for_offer(name: str, *, category: str = "", brand: str = "") -> set[str]:
    return {
        hit.profile
        for hit in ingredient_exclusion_hits_for_offer(name, category=category, brand=brand)
    }


def _hit_profiles_for_ingredient(text: str) -> set[str]:
    return {
        hit.profile
        for hit in ingredient_exclusion_hits_for_ingredient_text(text)
    }


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


def _audit_static_cases() -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    for profile, name, category, brand, should_hit in _STATIC_OFFER_CASES:
        hit = profile in _hit_profiles_for_offer(name, category=category, brand=brand)
        if hit != should_hit:
            findings.append(AuditFinding(
                severity="error",
                area="static_offer",
                profile=profile,
                item=name,
                evidence="expected_hit" if should_hit else "expected_miss",
                message=f"static offer expectation failed: got {'hit' if hit else 'miss'}",
            ))

    for profile, ingredient, should_hit in _STATIC_RECIPE_CASES:
        hit = profile in _hit_profiles_for_ingredient(ingredient)
        if hit != should_hit:
            findings.append(AuditFinding(
                severity="error",
                area="static_recipe",
                profile=profile,
                item=ingredient,
                evidence="expected_hit" if should_hit else "expected_miss",
                message=f"static recipe expectation failed: got {'hit' if hit else 'miss'}",
            ))
    return findings


def _audit_profile_expectations(
    *,
    area: str,
    item: str,
    hit_profiles: set[str],
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    for profile, cues in _MUST_NOT_HIT_CUES.items():
        cue = _matching_cue(item, cues)
        if cue and profile in hit_profiles:
            findings.append(AuditFinding(
                severity="error",
                area=area,
                profile=profile,
                item=item,
                evidence=cue,
                message="exemption or known false-positive cue was flagged",
            ))

    for profile, cues in _MUST_HIT_CUES.items():
        if profile in hit_profiles:
            continue
        cue = _matching_cue(item, cues)
        if cue and not _matching_cue(item, _MUST_NOT_HIT_CUES.get(profile, ())):
            findings.append(AuditFinding(
                severity="error",
                area=area,
                profile=profile,
                item=item,
                evidence=cue,
                message="high-confidence dietary cue was not flagged",
            ))
    return findings


def _scripted_audit(offer_scan_limit: int, recipe_scan_limit: int) -> AuditSummary:
    findings = _audit_static_cases()
    offer_counts = {profile: 0 for profile in PROFILES}
    recipe_counts = {profile: 0 for profile in PROFILES}
    scanned_offers = 0
    scanned_recipes = 0

    with get_db_session() as db:
        offer_query = (
            db.query(Offer)
            .filter((Offer.savings.isnot(None)) & (Offer.savings > 0))
            .order_by(Offer.name)
            .limit(offer_scan_limit)
        )
        for offer in offer_query.all():
            scanned_offers += 1
            item = offer.name or ""
            hits = ingredient_exclusion_hits_for_offer(
                item,
                category=offer.category or "",
                brand=offer.brand or "",
            )
            hit_profiles = {hit.profile for hit in hits}
            for profile in hit_profiles:
                if profile in offer_counts:
                    offer_counts[profile] += 1
            findings.extend(_audit_profile_expectations(
                area="offer",
                item=item,
                hit_profiles=hit_profiles,
            ))

        recipe_query = (
            db.query(FoundRecipe)
            .filter((FoundRecipe.excluded == False) | (FoundRecipe.excluded.is_(None)))  # noqa: E712
            .order_by(FoundRecipe.name)
            .limit(recipe_scan_limit)
        )
        for recipe in recipe_query.all():
            scanned_recipes += 1
            recipe_profiles = set()
            for ingredient in recipe.ingredients or []:
                item = str(ingredient)
                hit_profiles = _hit_profiles_for_ingredient(item)
                recipe_profiles.update(hit_profiles)
                findings.extend(_audit_profile_expectations(
                    area=f"recipe:{recipe.name}",
                    item=item,
                    hit_profiles=hit_profiles,
                ))
            for profile in recipe_profiles:
                if profile in recipe_counts:
                    recipe_counts[profile] += 1

    for profile in PROFILES:
        if offer_counts[profile] == 0:
            findings.append(AuditFinding(
                severity="warning",
                area="offer",
                profile=profile,
                item="current sale-offer corpus",
                evidence="count=0",
                message="no current offer examples hit this profile in the scanned corpus",
            ))
        if recipe_counts[profile] == 0:
            findings.append(AuditFinding(
                severity="warning",
                area="recipe",
                profile=profile,
                item="current active-recipe corpus",
                evidence="count=0",
                message="no current recipe examples hit this profile in the scanned corpus",
            ))

    return AuditSummary(
        offer_hits=offer_counts,
        recipe_hits=recipe_counts,
        scanned_offers=scanned_offers,
        scanned_recipes=scanned_recipes,
        findings=findings,
    )


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


def _print_check_summary(summary: AuditSummary) -> None:
    errors = [finding for finding in summary.findings if finding.severity == "error"]
    warnings = [finding for finding in summary.findings if finding.severity == "warning"]
    print("Dietary exclusion scripted audit")
    print(f"Scanned sale offers: {summary.scanned_offers}")
    print(f"Scanned active recipes: {summary.scanned_recipes}")
    print("\nOffer hits by profile:")
    for profile in PROFILES:
        print(f"  {profile}: {summary.offer_hits.get(profile, 0)}")
    print("\nRecipe hits by profile:")
    for profile in PROFILES:
        print(f"  {profile}: {summary.recipe_hits.get(profile, 0)}")

    if summary.findings:
        print("\nFindings:")
        for finding in summary.findings:
            print(
                f"  [{finding.severity}] {finding.area} {finding.profile}: "
                f"{finding.item} ({finding.evidence}) - {finding.message}"
            )
    else:
        print("\nFindings: none")
    print(f"\nResult: {len(errors)} error(s), {len(warnings)} warning(s)")


def main() -> int:
    parser = ArgumentParser()
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--offer-scan-limit", type=int, default=5000)
    parser.add_argument("--recipe-scan-limit", type=int, default=3000)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run scripted corpus checks and fail on high-confidence errors.",
    )
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Make --check fail if the scanned corpus lacks examples for a profile.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable --check output.")
    args = parser.parse_args()

    if args.check:
        summary = _scripted_audit(args.offer_scan_limit, args.recipe_scan_limit)
        errors = [finding for finding in summary.findings if finding.severity == "error"]
        warnings = [finding for finding in summary.findings if finding.severity == "warning"]
        if args.json:
            print(json.dumps({
                "offer_hits": summary.offer_hits,
                "recipe_hits": summary.recipe_hits,
                "scanned_offers": summary.scanned_offers,
                "scanned_recipes": summary.scanned_recipes,
                "findings": [asdict(finding) for finding in summary.findings],
            }, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            _print_check_summary(summary)
        if errors or (args.fail_on_warnings and warnings):
            return 1
        return 0

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
