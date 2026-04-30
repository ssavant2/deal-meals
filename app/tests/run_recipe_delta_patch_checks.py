#!/usr/bin/env python3
"""Integration checks for the recipe-delta cache patch helper."""

from __future__ import annotations

from pathlib import Path
import json
import sys
import uuid

from loguru import logger
from sqlalchemy import text


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from cache_delta import apply_recipe_delta, patch_recipe_offer_cache_entries  # noqa: E402
from database import get_db_session  # noqa: E402


SOURCE_NAME = "Recipe Delta Patch Check"


def check(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"OK {name}")


def check_true(name: str, value) -> None:
    if not value:
        raise AssertionError(f"{name}: expected truthy value, got {value!r}")
    print(f"OK {name}")


def _new_recipe_id() -> str:
    return str(uuid.uuid4())


def _entry(recipe_id: str, *, marker: str, category: str = "vegetarian") -> dict:
    return {
        "found_recipe_id": recipe_id,
        "recipe_category": category,
        "budget_score": 12.5,
        "total_savings": 34.25,
        "coverage_pct": 67.5,
        "num_matches": 3,
        "is_starred": False,
        "match_data": {
            "matched_offers": [],
            "support_check_marker": marker,
        },
    }


def _cache_count() -> int:
    with get_db_session() as db:
        return int(db.execute(text("SELECT COUNT(*) FROM recipe_offer_cache")).scalar() or 0)


def _insert_recipe(db, recipe_id: str) -> None:
    db.execute(
        text("""
            INSERT INTO found_recipes (
                id, source_name, name, url, ingredients, excluded
            ) VALUES (
                CAST(:id AS uuid),
                :source_name,
                :name,
                :url,
                CAST(:ingredients AS jsonb),
                FALSE
            )
        """),
        {
            "id": recipe_id,
            "source_name": SOURCE_NAME,
            "name": f"Recipe delta patch check {recipe_id}",
            "url": f"https://example.invalid/recipe-delta-patch-check/{recipe_id}",
            "ingredients": json.dumps(["tomat", "pasta", "ost"]),
        },
    )


def _insert_cache_entry(db, recipe_id: str, *, marker: str, category: str = "vegetarian") -> None:
    entry = _entry(recipe_id, marker=marker, category=category)
    db.execute(
        text("""
            INSERT INTO recipe_offer_cache (
                found_recipe_id,
                recipe_category,
                budget_score,
                total_savings,
                coverage_pct,
                num_matches,
                is_starred,
                match_data
            ) VALUES (
                CAST(:found_recipe_id AS uuid),
                :recipe_category,
                :budget_score,
                :total_savings,
                :coverage_pct,
                :num_matches,
                :is_starred,
                CAST(:match_data AS jsonb)
            )
        """),
        {
            **entry,
            "match_data": json.dumps(entry["match_data"]),
        },
    )


def _cache_row(recipe_id: str) -> dict | None:
    with get_db_session() as db:
        row = db.execute(
            text("""
                SELECT recipe_category, budget_score, total_savings, match_data
                FROM recipe_offer_cache
                WHERE found_recipe_id = CAST(:recipe_id AS uuid)
            """),
            {"recipe_id": recipe_id},
        ).fetchone()
    if not row:
        return None
    return {
        "recipe_category": row.recipe_category,
        "budget_score": float(row.budget_score),
        "total_savings": float(row.total_savings),
        "marker": row.match_data.get("support_check_marker"),
    }


def _cleanup(recipe_ids: list[str]) -> None:
    if not recipe_ids:
        return
    with get_db_session() as db:
        db.execute(
            text("""
                DELETE FROM recipe_offer_cache
                WHERE found_recipe_id = ANY(CAST(:recipe_ids AS uuid[]))
            """),
            {"recipe_ids": recipe_ids},
        )
        db.execute(
            text("""
                DELETE FROM found_recipes
                WHERE id = ANY(CAST(:recipe_ids AS uuid[]))
                   OR source_name = :source_name
            """),
            {"recipe_ids": recipe_ids, "source_name": SOURCE_NAME},
        )
        db.commit()


def _expect_exception(name: str, fn) -> None:
    try:
        fn()
    except Exception:
        print(f"OK {name}")
        return
    raise AssertionError(f"{name}: expected exception")


def test_apply_recipe_delta_noop() -> None:
    result = apply_recipe_delta(
        changed_recipe_ids=[],
        removed_recipe_ids=[],
        source="support_check",
        verify_full_preview=False,
    )
    check("noop success", result["success"], True)
    check("noop applied", result["applied"], False)
    check("noop flag", result["noop"], True)
    check("noop changed count", result["changed_recipe_count"], 0)
    check("noop removed count", result["removed_recipe_count"], 0)


def test_patch_replaces_changed_and_removes_deleted() -> None:
    before_count = _cache_count()
    changed_id = _new_recipe_id()
    removed_id = _new_recipe_id()
    recipe_ids = [changed_id, removed_id]
    try:
        with get_db_session() as db:
            for recipe_id in recipe_ids:
                _insert_recipe(db, recipe_id)
                _insert_cache_entry(db, recipe_id, marker="baseline")
            db.commit()

        result = patch_recipe_offer_cache_entries(
            [_entry(changed_id, marker="patched")],
            [changed_id, removed_id],
            removed_recipe_ids=[removed_id],
        )

        check("patch deletes touched rows", result["deleted_count"], 2)
        check("patch inserts changed rows only", result["inserted_count"], 1)
        check("patch total matches", result["total_matches"], before_count + 1)
        check("removed recipe is not reinserted", _cache_row(removed_id), None)

        changed_row = _cache_row(changed_id)
        check_true("changed recipe remains cached", changed_row)
        check("changed recipe marker updated", changed_row["marker"], "patched")
        check("changed recipe category updated", changed_row["recipe_category"], "vegetarian")
        check("cache count after patch", _cache_count(), before_count + 1)
    finally:
        _cleanup(recipe_ids)
        check("cleanup restores cache count", _cache_count(), before_count)


def test_unexpected_patch_recipe_id_rejected_before_delete() -> None:
    before_count = _cache_count()
    changed_id = _new_recipe_id()
    unexpected_id = _new_recipe_id()
    try:
        with get_db_session() as db:
            _insert_recipe(db, changed_id)
            _insert_cache_entry(db, changed_id, marker="baseline")
            db.commit()

        _expect_exception(
            "unexpected patch id rejected",
            lambda: patch_recipe_offer_cache_entries(
                [_entry(unexpected_id, marker="unexpected")],
                [changed_id],
            ),
        )

        row = _cache_row(changed_id)
        check_true("unexpected id leaves baseline row", row)
        check("unexpected id leaves marker", row["marker"], "baseline")
        check("unexpected id leaves cache count", _cache_count(), before_count + 1)
    finally:
        _cleanup([changed_id, unexpected_id])
        check("unexpected id cleanup restores cache count", _cache_count(), before_count)


def test_patch_rolls_back_delete_when_insert_fails() -> None:
    before_count = _cache_count()
    recipe_id = _new_recipe_id()
    try:
        with get_db_session() as db:
            _insert_recipe(db, recipe_id)
            _insert_cache_entry(db, recipe_id, marker="baseline")
            db.commit()

        logger.disable("database")
        try:
            _expect_exception(
                "invalid patch rolls back",
                lambda: patch_recipe_offer_cache_entries(
                    [_entry(recipe_id, marker="invalid", category="not_a_real_category")],
                    [recipe_id],
                ),
            )
        finally:
            logger.enable("database")

        row = _cache_row(recipe_id)
        check_true("rollback keeps baseline row", row)
        check("rollback keeps marker", row["marker"], "baseline")
        check("rollback keeps category", row["recipe_category"], "vegetarian")
        check("rollback keeps cache count", _cache_count(), before_count + 1)
    finally:
        _cleanup([recipe_id])
        check("rollback cleanup restores cache count", _cache_count(), before_count)


def main() -> int:
    test_apply_recipe_delta_noop()
    test_patch_replaces_changed_and_removes_deleted()
    test_unexpected_patch_recipe_id_rejected_before_delete()
    test_patch_rolls_back_delete_when_insert_fails()
    print("ALL RECIPE DELTA PATCH CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
