#!/usr/bin/env python3
"""Checks for PostgreSQL session defaults used by cache rebuilds."""

from __future__ import annotations

from pathlib import Path
import sys

from sqlalchemy import text

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from database import SESSION_TEMP_BUFFERS, engine  # noqa: E402


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


def main() -> int:
    engine.dispose()
    with engine.connect() as conn:
        temp_buffers = conn.execute(text("SHOW temp_buffers")).scalar()

    test("DB sessions use cache-writer temp_buffers", temp_buffers, SESSION_TEMP_BUFFERS)

    print("\n========================================")
    print(f"TOTAL: {passed}/{passed + failed} checks passed")
    if failed:
        print(f"{failed} FAILED!")
        return 1
    print("All database session default checks passed!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
