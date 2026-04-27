"""CLI audit helpers for Swedish ingredient matching rules.

This is intentionally a single-file tool that helps with three common tasks:

1. Keyword x-ray:
   Show which rule tables mention a keyword and where it is derived from.

2. Explain:
   Show how one ingredient/product pair is interpreted by the matcher and which
   major rule families are likely to allow or block the pair.

3. Coverage:
   Show whether a term is already covered by exact rules, adjacent rule systems,
   or only indirectly via synonyms/parents/blockers.

Usage examples:

    python -m languages.sv.ingredient_matching_audit keyword basilika

    python -m languages.sv.ingredient_matching_audit explain \
        --ingredient "100 g färskost naturell" \
        --product "Färskost Black Pepper 150g Boursin"
"""

from __future__ import annotations

import argparse
import contextlib
import io
from typing import Iterable, Mapping, Sequence

with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    try:
        from .normalization import fix_swedish_chars
        from .ingredient_matching.normalization import _apply_space_normalizations
        # Import strategy:
        # - package-level imports for the supported public API
        # - direct submodule imports for internal rule tables/helpers that the
        #   audit tool needs for introspection but that should not widen __all__
        from .ingredient_matching import (
            FALSE_POSITIVE_BLOCKERS,
            KEYWORD_SUPPRESSED_BY_CONTEXT,
            NON_FOOD_KEYWORDS,
            PRODUCT_NAME_BLOCKERS,
            PROCESSED_FOODS,
            STOP_WORDS,
            build_ingredient_match_data,
            build_offer_match_data,
            extract_keywords_from_ingredient,
            extract_keywords_from_product,
            match_offer_to_ingredient,
        )
        from .ingredient_matching.carrier_context import (
            CARRIER_CONTEXT_REQUIRED,
            CARRIER_PRODUCTS,
            CONTEXT_REQUIRED_WORDS,
            INGREDIENT_REQUIRES_IN_PRODUCT,
        )
        from .ingredient_matching.compound_text import (
            _COMPOUND_STRICT_KEYWORDS,
            _COMPOUND_STRICT_PREFIX_KEYWORDS,
            _check_compound_strict,
        )
        from .ingredient_matching.dairy_types import (
            check_kvarg_match,
            check_yoghurt_match,
        )
        from .ingredient_matching.extraction_patterns import _INGREDIENT_PARENTS_REVERSE
        from .ingredient_matching.form_rules import FRESH_HERB_KEYWORDS
        from .ingredient_matching.match_filters import (
            RECIPE_INGREDIENT_BLOCKERS,
            SECONDARY_INGREDIENT_PATTERNS,
            _is_false_positive_blocked,
            check_secondary_ingredient_patterns,
        )
        from .ingredient_matching.processed_rules import SPICE_VS_FRESH_RULES
        from .ingredient_matching.specialty_rules import (
            BIDIRECTIONAL_PER_KEYWORD,
            BIDIRECTIONAL_SPECIALTY_QUALIFIERS,
            QUALIFIER_EQUIVALENTS,
            SPECIALTY_QUALIFIERS,
        )
        from .ingredient_matching.synonyms import (
            INGREDIENT_PARENTS,
            KEYWORD_SYNONYMS,
        )
        from .ingredient_matching.validators import (
            check_processed_product_rules,
            check_specialty_qualifiers,
            check_spice_vs_fresh_rules,
        )
    except ImportError:
        from app.languages.sv.normalization import fix_swedish_chars
        from app.languages.sv.ingredient_matching.normalization import _apply_space_normalizations
        from app.languages.sv.ingredient_matching import (
            FALSE_POSITIVE_BLOCKERS,
            KEYWORD_SUPPRESSED_BY_CONTEXT,
            NON_FOOD_KEYWORDS,
            PRODUCT_NAME_BLOCKERS,
            PROCESSED_FOODS,
            STOP_WORDS,
            build_ingredient_match_data,
            build_offer_match_data,
            extract_keywords_from_ingredient,
            extract_keywords_from_product,
            match_offer_to_ingredient,
        )
        from app.languages.sv.ingredient_matching.carrier_context import (
            CARRIER_CONTEXT_REQUIRED,
            CARRIER_PRODUCTS,
            CONTEXT_REQUIRED_WORDS,
            INGREDIENT_REQUIRES_IN_PRODUCT,
        )
        from app.languages.sv.ingredient_matching.compound_text import (
            _COMPOUND_STRICT_KEYWORDS,
            _COMPOUND_STRICT_PREFIX_KEYWORDS,
            _check_compound_strict,
        )
        from app.languages.sv.ingredient_matching.dairy_types import (
            check_kvarg_match,
            check_yoghurt_match,
        )
        from app.languages.sv.ingredient_matching.extraction_patterns import _INGREDIENT_PARENTS_REVERSE
        from app.languages.sv.ingredient_matching.form_rules import FRESH_HERB_KEYWORDS
        from app.languages.sv.ingredient_matching.match_filters import (
            RECIPE_INGREDIENT_BLOCKERS,
            SECONDARY_INGREDIENT_PATTERNS,
            _is_false_positive_blocked,
            check_secondary_ingredient_patterns,
        )
        from app.languages.sv.ingredient_matching.processed_rules import SPICE_VS_FRESH_RULES
        from app.languages.sv.ingredient_matching.specialty_rules import (
            BIDIRECTIONAL_PER_KEYWORD,
            BIDIRECTIONAL_SPECIALTY_QUALIFIERS,
            QUALIFIER_EQUIVALENTS,
            SPECIALTY_QUALIFIERS,
        )
        from app.languages.sv.ingredient_matching.synonyms import (
            INGREDIENT_PARENTS,
            KEYWORD_SYNONYMS,
        )
        from app.languages.sv.ingredient_matching.validators import (
            check_processed_product_rules,
            check_specialty_qualifiers,
            check_spice_vs_fresh_rules,
        )


def _normalize(text: str) -> str:
    return _apply_space_normalizations(fix_swedish_chars(text).lower().strip())


def _lines_from_mapping_keys(mapping: Mapping[str, object], keyword: str) -> list[str]:
    if keyword not in mapping:
        return []
    value = mapping[keyword]
    if isinstance(value, dict):
        parts = [f"{k}={sorted(v) if isinstance(v, (set, frozenset)) else v}" for k, v in value.items()]
        return [", ".join(parts)]
    if isinstance(value, tuple):
        pretty = []
        for item in value:
            if isinstance(item, (set, frozenset)):
                pretty.append(sorted(item))
            else:
                pretty.append(item)
        return [str(pretty)]
    if isinstance(value, (set, frozenset, list, tuple)):
        return [", ".join(sorted(str(v) for v in value))]
    return [str(value)]


def _reverse_hits(mapping: Mapping[str, str], keyword: str) -> list[str]:
    hits = [source for source, target in mapping.items() if target == keyword]
    return sorted(hits)


def _blocker_hits(mapping: Mapping[str, Iterable[str]], keyword: str) -> list[str]:
    hits = [source for source, blockers in mapping.items() if keyword in blockers]
    return sorted(hits)


def _format_section(title: str, lines: Sequence[str]) -> str:
    if not lines:
        return f"{title}: -"
    body = "\n".join(f"  - {line}" for line in lines)
    return f"{title}:\n{body}"


def _optional_section(title: str, lines: Sequence[str]) -> str:
    if not lines:
        return ""
    return _format_section(title, lines)


def _join_nonempty(parts: Sequence[str]) -> str:
    return "\n".join(part for part in parts if part)


def _keyword_xray(keyword: str) -> str:
    keyword = _normalize(keyword)

    sections = [
        f"Keyword: {keyword}",
        f"Stop word: {'yes' if keyword in STOP_WORDS else 'no'}",
        f"Non-food keyword: {'yes' if keyword in NON_FOOD_KEYWORDS else 'no'}",
        f"Processed food keyword: {'yes' if keyword in PROCESSED_FOODS else 'no'}",
        f"Carrier product: {'yes' if keyword in CARRIER_PRODUCTS else 'no'}",
        f"Carrier requires same word in ingredient: {'yes' if keyword in CARRIER_CONTEXT_REQUIRED else 'no'}",
        f"Context-required word: {'yes' if keyword in CONTEXT_REQUIRED_WORDS else 'no'}",
        f"Ingredient-requires-in-product word: {'yes' if keyword in INGREDIENT_REQUIRES_IN_PRODUCT else 'no'}",
        f"Fresh herb keyword: {'yes' if keyword in FRESH_HERB_KEYWORDS else 'no'}",
        f"Compound-strict suffix keyword: {'yes' if keyword in _COMPOUND_STRICT_KEYWORDS else 'no'}",
        f"Compound-strict prefix keyword: {'yes' if keyword in _COMPOUND_STRICT_PREFIX_KEYWORDS else 'no'}",
        "",
        _format_section("Synonym target", _lines_from_mapping_keys(KEYWORD_SYNONYMS, keyword)),
        _format_section("Ingredient parent target", _lines_from_mapping_keys(INGREDIENT_PARENTS, keyword)),
        _format_section("Reverse parent sources", _reverse_hits(INGREDIENT_PARENTS, keyword)),
        _format_section(
            "Reverse parent sources (precomputed)",
            sorted(_INGREDIENT_PARENTS_REVERSE.get(keyword, ())),
        ),
        _format_section("False-positive blockers for keyword", _lines_from_mapping_keys(FALSE_POSITIVE_BLOCKERS, keyword)),
        _format_section("Product-name blockers for keyword", _lines_from_mapping_keys(PRODUCT_NAME_BLOCKERS, keyword)),
        _format_section("Suppressed by context", _lines_from_mapping_keys(KEYWORD_SUPPRESSED_BY_CONTEXT, keyword)),
        _format_section("Specialty qualifiers", _lines_from_mapping_keys(SPECIALTY_QUALIFIERS, keyword)),
        _format_section("Bidirectional qualifiers", _lines_from_mapping_keys(BIDIRECTIONAL_PER_KEYWORD, keyword)),
        _format_section("Spice-vs-fresh rules", _lines_from_mapping_keys(SPICE_VS_FRESH_RULES, keyword)),
        _format_section("Secondary ingredient patterns", _lines_from_mapping_keys(SECONDARY_INGREDIENT_PATTERNS, keyword)),
        _format_section("Recipe ingredient blockers", _lines_from_mapping_keys(RECIPE_INGREDIENT_BLOCKERS, keyword)),
        "",
        _format_section("Keyword appears as FP blocker under", _blocker_hits(FALSE_POSITIVE_BLOCKERS, keyword)),
        _format_section("Keyword appears as product-name blocker under", _blocker_hits(PRODUCT_NAME_BLOCKERS, keyword)),
        _format_section("Keyword appears as suppressor under", _blocker_hits(KEYWORD_SUPPRESSED_BY_CONTEXT, keyword)),
    ]
    return _join_nonempty(sections)


def _collect_keyword_snapshot(keyword: str) -> dict[str, object]:
    keyword = _normalize(keyword)
    exact_hits: list[str] = []
    adjacent_hits: list[str] = []
    indirect_hits: list[str] = []

    if keyword in STOP_WORDS:
        exact_hits.append("keyword is a STOP_WORD")
    if keyword in NON_FOOD_KEYWORDS:
        exact_hits.append("keyword is a NON_FOOD keyword")
    if keyword in PROCESSED_FOODS:
        exact_hits.append("keyword is blocked at PROCESSED_FOODS layer")
    if keyword in CARRIER_PRODUCTS:
        exact_hits.append("keyword is a carrier product")
    if keyword in CARRIER_CONTEXT_REQUIRED:
        exact_hits.append("keyword is carrier-context-required")
    if keyword in CONTEXT_REQUIRED_WORDS:
        exact_hits.append("keyword is a context-required word")
    if keyword in INGREDIENT_REQUIRES_IN_PRODUCT:
        exact_hits.append("ingredient requires this word in product names")
    if keyword in FRESH_HERB_KEYWORDS:
        exact_hits.append("keyword is treated as fresh herb")
    if keyword in _COMPOUND_STRICT_KEYWORDS:
        exact_hits.append("keyword uses compound-strict suffix logic")
    if keyword in _COMPOUND_STRICT_PREFIX_KEYWORDS:
        exact_hits.append("keyword uses compound-strict prefix logic")
    if keyword in KEYWORD_SYNONYMS:
        exact_hits.append(f"synonym target: {KEYWORD_SYNONYMS[keyword]}")
    if keyword in INGREDIENT_PARENTS:
        exact_hits.append(f"ingredient parent target: {INGREDIENT_PARENTS[keyword]}")
    if keyword in FALSE_POSITIVE_BLOCKERS:
        exact_hits.append(f"false-positive blockers: {', '.join(sorted(FALSE_POSITIVE_BLOCKERS[keyword]))}")
    if keyword in PRODUCT_NAME_BLOCKERS:
        exact_hits.append(f"product-name blockers: {', '.join(sorted(PRODUCT_NAME_BLOCKERS[keyword]))}")
    if keyword in KEYWORD_SUPPRESSED_BY_CONTEXT:
        exact_hits.append(f"context suppressors: {', '.join(sorted(KEYWORD_SUPPRESSED_BY_CONTEXT[keyword]))}")
    if keyword in SPECIALTY_QUALIFIERS:
        exact_hits.append(f"specialty qualifiers: {', '.join(sorted(SPECIALTY_QUALIFIERS[keyword]))}")
    if keyword in BIDIRECTIONAL_PER_KEYWORD:
        exact_hits.append(f"bidirectional qualifiers: {', '.join(sorted(BIDIRECTIONAL_PER_KEYWORD[keyword]))}")
    if keyword in SPICE_VS_FRESH_RULES:
        adjacent_hits.append("keyword has spice-vs-fresh rules")
    if keyword in SECONDARY_INGREDIENT_PATTERNS:
        adjacent_hits.append("keyword has secondary ingredient patterns")
    if keyword in RECIPE_INGREDIENT_BLOCKERS:
        adjacent_hits.append("keyword has recipe ingredient blockers")

    reverse_sources = _reverse_hits(INGREDIENT_PARENTS, keyword)
    if reverse_sources:
        indirect_hits.append(f"reverse parent sources: {', '.join(reverse_sources)}")

    precomputed_sources = sorted(_INGREDIENT_PARENTS_REVERSE.get(keyword, ()))
    if precomputed_sources:
        indirect_hits.append(f"precomputed reverse sources: {', '.join(precomputed_sources)}")

    fp_under = _blocker_hits(FALSE_POSITIVE_BLOCKERS, keyword)
    if fp_under:
        indirect_hits.append(f"appears as FP blocker under: {', '.join(fp_under)}")

    pnb_under = _blocker_hits(PRODUCT_NAME_BLOCKERS, keyword)
    if pnb_under:
        indirect_hits.append(f"appears as product-name blocker under: {', '.join(pnb_under)}")

    suppressor_under = _blocker_hits(KEYWORD_SUPPRESSED_BY_CONTEXT, keyword)
    if suppressor_under:
        indirect_hits.append(f"appears as context suppressor under: {', '.join(suppressor_under)}")

    return {
        "keyword": keyword,
        "exact_hits": exact_hits,
        "adjacent_hits": adjacent_hits,
        "indirect_hits": indirect_hits,
    }


def _coverage_report(keyword: str) -> str:
    snapshot = _collect_keyword_snapshot(keyword)
    exact_hits = snapshot["exact_hits"]
    adjacent_hits = snapshot["adjacent_hits"]
    indirect_hits = snapshot["indirect_hits"]

    if exact_hits:
        assessment = "Existing exact rule coverage already exists. Audit before adding anything new."
    elif adjacent_hits or indirect_hits:
        assessment = "No exact top-level rule hit, but nearby mechanisms already touch this term."
    else:
        assessment = "No obvious existing coverage found. This may be a genuine new-rule candidate."

    next_step = (
        "Check explain-mode on a real ingredient/product pair before adding a rule."
        if (exact_hits or adjacent_hits or indirect_hits)
        else "Start with explain-mode on a real failing pair to confirm the gap."
    )

    sections = [
        f"Coverage term: {snapshot['keyword']}",
        f"Assessment: {assessment}",
        f"Suggested next step: {next_step}",
        "",
        _format_section("Exact coverage", exact_hits),
        _format_section("Adjacent rule systems", adjacent_hits),
        _format_section("Indirect/related coverage", indirect_hits),
    ]
    return _join_nonempty(sections)


def _product_name_blocker_result(matched_keyword: str | None, ingredient_lower: str, product_lower: str) -> tuple[bool, list[str]]:
    if not matched_keyword or matched_keyword not in PRODUCT_NAME_BLOCKERS:
        return True, []
    if matched_keyword in {'stjärnanis', 'stjarnanis'} and ('stjärn' in product_lower or 'stjarn' in product_lower):
        return True, []
    blockers = sorted(b for b in PRODUCT_NAME_BLOCKERS[matched_keyword] if b in product_lower)
    if not blockers:
        return True, []
    passes = any(b in ingredient_lower for b in blockers)
    return passes, blockers


def _specialty_direction_b_hits(offer_specialty_qualifiers: Mapping[str, set], matched_keyword: str | None, ingredient_lower: str) -> list[str]:
    if not matched_keyword:
        return []
    hits = []
    for qualifier in sorted(offer_specialty_qualifiers.get(matched_keyword, set())):
        if qualifier in BIDIRECTIONAL_SPECIALTY_QUALIFIERS or qualifier in BIDIRECTIONAL_PER_KEYWORD.get(matched_keyword, frozenset()):
            equivalents = sorted(QUALIFIER_EQUIVALENTS.get(qualifier, {qualifier}))
            if not any(eq in ingredient_lower for eq in equivalents):
                hits.append(f"{qualifier} (equivalents: {', '.join(equivalents)})")
    return hits


def _candidate_keyword_reasons(offer_data: Mapping[str, object], ingredient_lower: str) -> list[str]:
    reasons: list[str] = []
    for keyword in offer_data['keywords']:
        if keyword not in ingredient_lower:
            continue
        if keyword in FALSE_POSITIVE_BLOCKERS:
            blockers = sorted(b for b in FALSE_POSITIVE_BLOCKERS[keyword] if b in ingredient_lower)
            if blockers:
                reasons.append(f"{keyword}: false-positive blockers present -> {', '.join(blockers)}")
        if keyword in KEYWORD_SUPPRESSED_BY_CONTEXT:
            suppressors = sorted(s for s in KEYWORD_SUPPRESSED_BY_CONTEXT[keyword] if s in ingredient_lower)
            if suppressors:
                reasons.append(f"{keyword}: suppressed by context -> {', '.join(suppressors)}")
        if keyword in _COMPOUND_STRICT_KEYWORDS:
            if _check_compound_strict(keyword, ingredient_lower, offer_data['name_normalized']):
                reasons.append(f"{keyword}: blocked by compound-strict suffix logic")
        if keyword in _COMPOUND_STRICT_PREFIX_KEYWORDS:
            if _check_compound_strict(keyword, ingredient_lower, offer_data['name_normalized'], check_prefix=True):
                reasons.append(f"{keyword}: blocked by compound-strict prefix logic")
    return reasons


def _fast_path_fpb_hits(offer_data: Mapping[str, object], ingredient_lower: str) -> list[str]:
    hits: list[str] = []
    for keyword in offer_data['keywords']:
        if keyword not in ingredient_lower:
            continue
        if _is_false_positive_blocked(keyword, ingredient_lower):
            hits.append(keyword)
    return sorted(set(hits))


def _explain_pair(ingredient: str, product: str, category: str = "", brand: str = "", weight_grams: float | None = None) -> str:
    ingredient_data = build_ingredient_match_data(ingredient)
    offer_match_data = build_offer_match_data(
        product,
        category,
        brand=brand,
        weight_grams=weight_grams,
    )
    offer_data = offer_match_data.precomputed
    ingredient_lower = ingredient_data.normalized_text
    product_lower = offer_match_data.normalized_name or _normalize(product)

    ingredient_keywords = sorted(ingredient_data.extracted_keywords)
    product_keywords = extract_keywords_from_product(product, category, brand=brand)

    fast_result = match_offer_to_ingredient(ingredient_data, offer_match_data)
    fast_match = fast_result.matched_keyword
    recipe_style_match = fast_match
    validation_notes: list[str] = []
    fast_path_fpb_hits = _fast_path_fpb_hits(offer_data, ingredient_lower)

    if not recipe_style_match and fast_path_fpb_hits:
        validation_notes.append(
            "blocked by false-positive blockers in fast matcher: "
            + ", ".join(fast_path_fpb_hits)
        )

    if recipe_style_match:
        if _is_false_positive_blocked(recipe_style_match, ingredient_lower):
            validation_notes.append("blocked by false-positive blockers")
            recipe_style_match = None

    if recipe_style_match:
        if not check_yoghurt_match(recipe_style_match, ingredient_lower, product_lower):
            validation_notes.append("blocked by yoghurt type check")
            recipe_style_match = None
        elif not check_kvarg_match(recipe_style_match, ingredient_lower, product_lower):
            validation_notes.append("blocked by kvarg type check")
            recipe_style_match = None

    if recipe_style_match:
        pnb_ok, pnb_hits = _product_name_blocker_result(recipe_style_match, ingredient_lower, product_lower)
        if not pnb_ok:
            validation_notes.append(f"blocked by product-name blockers: {', '.join(pnb_hits)}")
            recipe_style_match = None

    if recipe_style_match and not check_secondary_ingredient_patterns(product_lower, ingredient_lower, recipe_style_match):
        validation_notes.append("blocked by secondary ingredient patterns")
        recipe_style_match = None

    if recipe_style_match and not check_specialty_qualifiers(
        offer_data['specialty_qualifiers'],
        recipe_style_match,
        ingredient_lower,
    ):
        validation_notes.append("blocked by specialty qualifiers")
        recipe_style_match = None

    if (
        recipe_style_match
        and offer_data.get('processed_checks')
        and not check_processed_product_rules(product_lower, ingredient_lower)
    ):
        validation_notes.append("blocked by processed-product rules")
        recipe_style_match = None

    if recipe_style_match and not check_spice_vs_fresh_rules(product_lower, ingredient_lower):
        validation_notes.append("blocked by spice-vs-fresh rules")
        recipe_style_match = None

    candidate_reasons = _candidate_keyword_reasons(offer_data, ingredient_lower)
    pnb_ok, pnb_hits = _product_name_blocker_result(fast_match, ingredient_lower, product_lower)
    specialty_direction_b = _specialty_direction_b_hits(
        offer_data['specialty_qualifiers'],
        fast_match,
        ingredient_lower,
    )

    sections = [
        f"Ingredient: {ingredient}",
        f"Product: {product}",
        f"Normalized ingredient: {ingredient_lower}",
        f"Normalized product: {product_lower}",
        "",
        _format_section("Ingredient keywords", [", ".join(ingredient_keywords) if ingredient_keywords else "(none)"]),
        _format_section("Product keywords", [", ".join(product_keywords) if product_keywords else "(none)"]),
        _format_section("Precomputed offer keywords", [", ".join(offer_data['keywords']) if offer_data['keywords'] else "(none)"]),
        _format_section("Offer context words", [", ".join(sorted(offer_data['context_words'])) if offer_data['context_words'] else "(none)"]),
        _format_section(
            "Offer specialty qualifiers",
            [
                f"{base}: {', '.join(sorted(values))}"
                for base, values in sorted(offer_data['specialty_qualifiers'].items())
            ] or ["(none)"],
        ),
        "",
        f"Fast matcher result: {fast_match or 'NO MATCH'}",
        f"Recipe-style validator result: {recipe_style_match or 'BLOCKED / NO MATCH'}",
        "",
        _optional_section("Likely blocking reasons in fast matcher", candidate_reasons),
        _optional_section("Product-name blocker hits", [", ".join(pnb_hits)] if pnb_hits else []),
        _optional_section("Bidirectional specialty requirements not satisfied", specialty_direction_b),
        _optional_section("Post-match validator notes", validation_notes),
        "",
        "Note: 'Recipe-style validator result' mirrors the main per-ingredient validator families,",
        "but it is still an audit helper rather than a full trace of every recipe_matcher branch.",
    ]
    return _join_nonempty(sections)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m languages.sv.ingredient_matching_audit",
        description="Audit helpers for Swedish ingredient matching rules.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    keyword_parser = subparsers.add_parser(
        "keyword",
        help="Show which rule families mention a keyword.",
    )
    keyword_parser.add_argument("keyword", help="Keyword to inspect")

    coverage_parser = subparsers.add_parser(
        "coverage",
        help="Show whether a term already has exact or adjacent rule coverage.",
    )
    coverage_parser.add_argument("keyword", help="Term to inspect")

    explain_parser = subparsers.add_parser(
        "explain",
        help="Explain one ingredient/product pair.",
    )
    explain_parser.add_argument("--ingredient", required=True, help="Ingredient text")
    explain_parser.add_argument("--product", required=True, help="Product name")
    explain_parser.add_argument("--category", default="", help="Optional offer category")
    explain_parser.add_argument("--brand", default="", help="Optional offer brand")
    explain_parser.add_argument("--weight-grams", type=float, default=None, help="Optional product weight")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "keyword":
        print(_keyword_xray(args.keyword))
        return 0

    if args.command == "coverage":
        print(_coverage_report(args.keyword))
        return 0

    if args.command == "explain":
        print(_explain_pair(
            args.ingredient,
            args.product,
            category=args.category,
            brand=args.brand,
            weight_grams=args.weight_grams,
        ))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
