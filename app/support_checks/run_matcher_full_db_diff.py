#!/usr/bin/env python3
"""Compare persisted recipe-offer cache rows with a fresh full DB preview.

This is intentionally read-only and does not write recipe_offer_cache.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from typing import Any
from uuid import UUID

sys.path.insert(0, "/app" if os.path.exists("/app") else os.path.join(os.path.dirname(__file__), ".."))

from cache_manager import CacheManager  # noqa: E402
from database import get_db_session  # noqa: E402
from models import FoundRecipe  # noqa: E402
from sqlalchemy import text  # noqa: E402


PERSISTED_ENTRY_FIELDS = (
    "found_recipe_id",
    "recipe_category",
    "budget_score",
    "total_savings",
    "coverage_pct",
    "num_matches",
    "is_starred",
    "match_data",
)
VERSION_FIELDS = (
    "matcher_version",
    "recipe_compiler_version",
    "offer_compiler_version",
)


def _normalize_alternative_string(value: str) -> str:
    parts = [part.strip() for part in value.split(" / ") if part.strip()]
    if len(parts) <= 1:
        return value
    return " / ".join(sorted(parts))


def _normalize_number(value: Any) -> str:
    decimal = Decimal(str(value))
    normalized = decimal.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _normalize_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            return value
        return _normalize_value(parsed)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (int, float, Decimal)):
        return _normalize_number(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        normalized_dict = {}
        has_stable_offer_identity = isinstance(value.get("offer_identity_key"), str)
        for key in sorted(value):
            if has_stable_offer_identity and key == "id":
                continue
            item = value[key]
            if key == "matched_keyword" and isinstance(item, str):
                normalized_dict[key] = _normalize_alternative_string(item)
            else:
                normalized_dict[key] = _normalize_value(item)
        return normalized_dict
    if isinstance(value, list):
        normalized = [_normalize_value(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
    return value


def _canonicalize_cache_entry(entry: dict[str, Any]) -> dict[str, Any]:
    canonical = {}
    for field in PERSISTED_ENTRY_FIELDS:
        if field not in entry:
            continue
        canonical[field] = _normalize_value(entry[field])
    if isinstance(canonical.get("match_data"), dict):
        canonical["match_data"] = {
            key: value
            for key, value in canonical["match_data"].items()
            if key not in VERSION_FIELDS
        }
    if "found_recipe_id" in canonical:
        canonical["found_recipe_id"] = str(canonical["found_recipe_id"])
    return canonical


def snapshot_from_entries(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    snapshot = {}
    for raw_entry in entries:
        entry = _canonicalize_cache_entry(raw_entry)
        recipe_id = entry.get("found_recipe_id")
        if not recipe_id:
            raise ValueError(f"Cache entry missing found_recipe_id: {raw_entry}")
        snapshot[str(recipe_id)] = entry
    return snapshot


def snapshot_from_db() -> dict[str, dict[str, Any]]:
    with get_db_session() as db:
        rows = db.execute(text("""
            SELECT
                found_recipe_id::text AS found_recipe_id,
                recipe_category,
                budget_score,
                total_savings,
                coverage_pct,
                num_matches,
                is_starred,
                match_data
            FROM recipe_offer_cache
            ORDER BY found_recipe_id
        """)).fetchall()
    return snapshot_from_entries([dict(row._mapping) for row in rows])


def compare_snapshots(
    baseline: dict[str, dict[str, Any]],
    candidate: dict[str, dict[str, Any]],
    *,
    sample_limit: int = 10,
) -> dict[str, Any]:
    baseline_ids = set(baseline)
    candidate_ids = set(candidate)
    baseline_only = sorted(baseline_ids - candidate_ids)
    candidate_only = sorted(candidate_ids - baseline_ids)
    mismatched = [
        recipe_id
        for recipe_id in sorted(baseline_ids & candidate_ids)
        if baseline[recipe_id] != candidate[recipe_id]
    ]
    return {
        "baseline_count": len(baseline),
        "candidate_count": len(candidate),
        "baseline_only_count": len(baseline_only),
        "candidate_only_count": len(candidate_only),
        "mismatched_count": len(mismatched),
        "parity_ok": not baseline_only and not candidate_only and not mismatched,
        "baseline_only_sample": baseline_only[:sample_limit],
        "candidate_only_sample": candidate_only[:sample_limit],
        "mismatched_sample": mismatched[:sample_limit],
    }


def _recipe_metadata(recipe_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not recipe_ids:
        return {}
    with get_db_session() as db:
        rows = (
            db.query(FoundRecipe)
            .filter(FoundRecipe.id.in_(recipe_ids))
            .order_by(FoundRecipe.id)
            .all()
        )
    return {
        str(recipe.id): {
            "name": recipe.name,
            "source_name": recipe.source_name,
            "url": recipe.url,
        }
        for recipe in rows
    }


def _field_diffs(
    baseline_entry: dict[str, Any] | None,
    candidate_entry: dict[str, Any] | None,
) -> list[str]:
    if baseline_entry is None or candidate_entry is None:
        return []
    return [
        field
        for field in sorted(set(baseline_entry) | set(candidate_entry))
        if baseline_entry.get(field) != candidate_entry.get(field)
    ]


def _matched_offer_preview(entry: dict[str, Any] | None, *, limit: int = 5) -> list[dict[str, Any]]:
    if not entry:
        return []
    match_data = entry.get("match_data")
    if not isinstance(match_data, dict):
        return []
    matched_offers = match_data.get("matched_offers")
    if not isinstance(matched_offers, list):
        return []
    preview = []
    for offer in matched_offers[:limit]:
        if not isinstance(offer, dict):
            continue
        preview.append({
            "name": offer.get("name"),
            "matched_keyword": offer.get("matched_keyword"),
            "matched_ingredient_index": offer.get("matched_ingredient_index"),
            "offer_identity_key": offer.get("offer_identity_key"),
        })
    return preview


def _entry_summary(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not entry:
        return None
    return {
        "recipe_category": entry.get("recipe_category"),
        "budget_score": entry.get("budget_score"),
        "total_savings": entry.get("total_savings"),
        "coverage_pct": entry.get("coverage_pct"),
        "num_matches": entry.get("num_matches"),
        "is_starred": entry.get("is_starred"),
        "matched_offer_preview": _matched_offer_preview(entry),
    }


def _sample_details(
    recipe_ids: list[str],
    *,
    baseline: dict[str, dict[str, Any]],
    candidate: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    metadata = _recipe_metadata(recipe_ids)
    details = []
    for recipe_id in recipe_ids:
        baseline_entry = baseline.get(recipe_id)
        candidate_entry = candidate.get(recipe_id)
        details.append({
            "recipe_id": recipe_id,
            "recipe": metadata.get(recipe_id, {}),
            "field_diffs": _field_diffs(baseline_entry, candidate_entry),
            "baseline": _entry_summary(baseline_entry),
            "candidate": _entry_summary(candidate_entry),
        })
    return details


def _diff_field_counts(
    baseline: dict[str, dict[str, Any]],
    candidate: dict[str, dict[str, Any]],
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for recipe_id in sorted(set(baseline) & set(candidate)):
        counter.update(_field_diffs(baseline[recipe_id], candidate[recipe_id]))
    return dict(sorted(counter.items()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-limit", type=int, default=25)
    parser.add_argument(
        "--write-report",
        type=Path,
        help="Optional path to write the JSON report. The report is always printed.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline_snapshot = snapshot_from_db()
    preview = CacheManager().compute_cache(
        persist=False,
        return_entries=True,
        run_kind="matcher_full_db_diff",
        input_scope="live",
    )
    candidate_snapshot = snapshot_from_entries(preview["entries"])
    comparison = compare_snapshots(
        baseline_snapshot,
        candidate_snapshot,
        sample_limit=max(0, args.sample_limit),
    )

    baseline_ids = set(baseline_snapshot)
    candidate_ids = set(candidate_snapshot)
    baseline_only = sorted(baseline_ids - candidate_ids)
    candidate_only = sorted(candidate_ids - baseline_ids)
    mismatched = [
        recipe_id
        for recipe_id in sorted(baseline_ids & candidate_ids)
        if baseline_snapshot[recipe_id] != candidate_snapshot[recipe_id]
    ]
    sample_limit = max(0, args.sample_limit)

    report = {
        "summary": {
            **comparison,
            "full_preview_time_ms": preview.get("time_ms"),
            "ingredient_routing_mode": preview.get("ingredient_routing_mode"),
            "ingredient_routing_effective_mode": preview.get("ingredient_routing_effective_mode"),
            "field_diff_counts": _diff_field_counts(baseline_snapshot, candidate_snapshot),
        },
        "samples": {
            "baseline_only": _sample_details(
                baseline_only[:sample_limit],
                baseline=baseline_snapshot,
                candidate=candidate_snapshot,
            ),
            "candidate_only": _sample_details(
                candidate_only[:sample_limit],
                baseline=baseline_snapshot,
                candidate=candidate_snapshot,
            ),
            "mismatched": _sample_details(
                mismatched[:sample_limit],
                baseline=baseline_snapshot,
                candidate=candidate_snapshot,
            ),
        },
    }

    if args.write_report:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if comparison["parity_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
