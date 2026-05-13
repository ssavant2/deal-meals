#!/usr/bin/env python3
"""Checks for ingredient-routing runtime mode normalization."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, '/app' if os.path.exists('/app') else os.path.join(os.path.dirname(__file__), '..'))

from config import settings  # noqa: E402
from ingredient_routing_runtime import (  # noqa: E402
    get_configured_ingredient_routing_mode,
    normalize_ingredient_routing_mode,
)


passed = 0
failed = 0


def test(desc: str, actual, expected) -> None:
    global passed, failed
    if actual == expected:
        passed += 1
        return
    failed += 1
    print(f"FAIL: {desc}")
    print(f"  got:      {actual}")
    print(f"  expected: {expected}")


original_mode = settings.cache_ingredient_routing_mode
try:
    test("off mode is preserved", normalize_ingredient_routing_mode("off"), "off")
    test("hint_first mode is preserved", normalize_ingredient_routing_mode("hint_first"), "hint_first")
    test("invalid mode falls back to off", normalize_ingredient_routing_mode("turbo"), "off")
    test("empty mode falls back to off", normalize_ingredient_routing_mode(""), "off")
    test("deprecated shadow mode falls back to off", normalize_ingredient_routing_mode("shadow"), "off")
    test("deprecated probation mode falls back to off", normalize_ingredient_routing_mode("probation"), "off")

    settings.cache_ingredient_routing_mode = "hint_first"
    test("configured hint_first is returned", get_configured_ingredient_routing_mode(), "hint_first")
    settings.cache_ingredient_routing_mode = "shadow"
    test("configured deprecated shadow is disabled", get_configured_ingredient_routing_mode(), "off")
finally:
    settings.cache_ingredient_routing_mode = original_mode


print("\n========================================")
print(f"TOTAL: {passed}/{passed + failed} checks passed")
if failed:
    print(f"{failed} FAILED!")
    print("========================================")
    raise SystemExit(1)

print("ALL PASSED!")
print("========================================")
