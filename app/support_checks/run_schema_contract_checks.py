#!/usr/bin/env python3
"""Checks for schema metadata that must stay aligned with initial DDL."""

from __future__ import annotations

from pathlib import Path
import re
import sys


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from models import Offer  # noqa: E402


def _repo_dir() -> Path:
    for candidate in (APP_DIR.parent, Path("/repo"), Path.cwd(), Path.cwd().parent):
        if (candidate / "database" / "init.sql").exists():
            return candidate
    raise FileNotFoundError("could not locate database/init.sql from host or container paths")


INIT_SQL = _repo_dir() / "database" / "init.sql"

passed = 0
failed = 0


def test(desc: str, actual, expected) -> None:
    global passed, failed
    if actual == expected:
        passed += 1
        print(f"OK {desc}")
        return
    failed += 1
    print(f"FAIL: {desc}")
    print(f"  got:      {actual}")
    print(f"  expected: {expected}")


def _init_sql_index_names(table_name: str) -> set[str]:
    sql = INIT_SQL.read_text(encoding="utf-8")
    pattern = re.compile(
        r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+"
        r"(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\s+"
        r"ON\s+(?P<table>[a-zA-Z_][a-zA-Z0-9_]*)\b",
        re.IGNORECASE | re.MULTILINE,
    )
    return {
        match.group("name")
        for match in pattern.finditer(sql)
        if match.group("table") == table_name
    }


def _orm_index_names(model) -> set[str]:
    return {index.name for index in model.__table__.indexes}


def main() -> int:
    offer_orm_indexes = _orm_index_names(Offer)
    offer_init_indexes = _init_sql_index_names("offers")

    test(
        "Offer ORM indexes exist in database/init.sql",
        sorted(offer_orm_indexes - offer_init_indexes),
        [],
    )

    print("\n========================================")
    print(f"TOTAL: {passed}/{passed + failed} checks passed")
    if failed:
        print(f"{failed} FAILED!")
        return 1
    print("ALL SCHEMA CONTRACT CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
