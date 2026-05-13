#!/usr/bin/env python3
"""Guard rails for hash-based matcher/compiler version manifests."""

from __future__ import annotations

import os
from pathlib import Path
import sys


sys.path.insert(0, "/app" if os.path.exists("/app") else os.path.join(os.path.dirname(__file__), ".."))

from languages.sv.ingredient_matching.versioning import (  # noqa: E402
    MATCHER_HASH_FILES,
    MATCHER_VERSION,
    OFFER_COMPILER_HASH_FILES,
    OFFER_COMPILER_VERSION,
    PACKAGE_DIR,
    REPO_ROOT,
    RECIPE_COMPILER_HASH_FILES,
    RECIPE_COMPILER_VERSION,
    _hash_manifest,
)


passed = 0
failed = 0


def test(desc: str, condition: bool, detail: str | None = None) -> None:
    global passed, failed
    if condition:
        passed += 1
        return
    failed += 1
    print(f"FAIL: {desc}")
    if detail:
        print(f"  {detail}")


def _assert_manifest_exists(name: str, manifest: tuple[str, ...]) -> None:
    for rel_path in manifest:
        path = REPO_ROOT / rel_path
        test(f"{name} contains existing file {rel_path}", path.exists(), f"missing: {path}")


def _normalize(rel_paths: tuple[str, ...]) -> set[str]:
    return {Path(p).name for p in rel_paths}


print("\n--- matcher version manifest checks ---")

test(
    "matcher version is hash-derived",
    MATCHER_VERSION == _hash_manifest("matcher", MATCHER_HASH_FILES),
)
test(
    "recipe compiler version is hash-derived",
    RECIPE_COMPILER_VERSION == _hash_manifest("recipe-compiler", RECIPE_COMPILER_HASH_FILES),
)
test(
    "offer compiler version is hash-derived",
    OFFER_COMPILER_VERSION == _hash_manifest("offer-compiler", OFFER_COMPILER_HASH_FILES),
)

_assert_manifest_exists("MATCHER_HASH_FILES", MATCHER_HASH_FILES)
_assert_manifest_exists("RECIPE_COMPILER_HASH_FILES", RECIPE_COMPILER_HASH_FILES)
_assert_manifest_exists("OFFER_COMPILER_HASH_FILES", OFFER_COMPILER_HASH_FILES)

package_files = {
    path.name
    for path in PACKAGE_DIR.glob("*.py")
    if path.name not in {"__init__.py", "__main__.py"}
}
manifest_files = (
    _normalize(MATCHER_HASH_FILES)
    | _normalize(RECIPE_COMPILER_HASH_FILES)
    | _normalize(OFFER_COMPILER_HASH_FILES)
)
missing = sorted(package_files - manifest_files)
test(
    "all production ingredient_matching files are covered by a manifest",
    not missing,
    f"missing manifest coverage for: {missing}",
)


print("\n========================================")
print(f"TOTAL: {passed}/{passed + failed} checks passed")
if failed:
    print(f"{failed} FAILED!")
    print("========================================")
    raise SystemExit(1)

print("ALL MATCHER VERSION CHECKS PASSED")
print("========================================")
