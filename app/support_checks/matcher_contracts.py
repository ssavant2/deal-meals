#!/usr/bin/env python3
"""Shared access helpers for matcher contract JSON files."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = APP_DIR.parent
MATCHER_CONTRACTS_RELATIVE_DIR = Path("languages") / "sv" / "matcher_contracts"
FIXTURE_CONTRACT_FILENAME = "matcher_regression_cases.json"
INVENTORY_CONTRACT_FILENAME = "matcher_rule_inventory.json"


@dataclass(frozen=True)
class MatcherContractPaths:
    app_dir: Path
    repo_root: Path
    fixture_file: Path
    inventory_file: Path


def app_dir_for_tree_root(tree_root: Path | None = None) -> Path:
    if tree_root is None:
        return APP_DIR
    root = tree_root.resolve()
    if (root / "app").is_dir():
        return root / "app"
    return root


def repo_root_for_tree_root(tree_root: Path | None = None) -> Path:
    app_dir = app_dir_for_tree_root(tree_root)
    return app_dir.parent if app_dir.name == "app" else app_dir


def contract_paths(tree_root: Path | None = None) -> MatcherContractPaths:
    app_dir = app_dir_for_tree_root(tree_root)
    repo_root = app_dir.parent if app_dir.name == "app" else app_dir
    contract_dir = app_dir / MATCHER_CONTRACTS_RELATIVE_DIR
    return MatcherContractPaths(
        app_dir=app_dir,
        repo_root=repo_root,
        fixture_file=contract_dir / FIXTURE_CONTRACT_FILENAME,
        inventory_file=contract_dir / INVENTORY_CONTRACT_FILENAME,
    )


def fixture_contract_path(tree_root: Path | None = None) -> Path:
    return contract_paths(tree_root).fixture_file


def inventory_contract_path(tree_root: Path | None = None) -> Path:
    return contract_paths(tree_root).inventory_file


def load_json_list(path: Path, *, label: str = "contract JSON") -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{label} must contain a list: {path}")
    return payload


def load_fixture_contract(path: Path | None = None, *, tree_root: Path | None = None) -> list[dict[str, Any]]:
    return load_json_list(path or fixture_contract_path(tree_root), label="fixture contract")


def load_inventory_contract(path: Path | None = None, *, tree_root: Path | None = None) -> list[dict[str, Any]]:
    return load_json_list(path or inventory_contract_path(tree_root), label="inventory contract")


def write_json_list(path: Path, payload: list[dict[str, Any]], *, sort_keys: bool = False) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=sort_keys) + "\n",
        encoding="utf-8",
    )


def write_fixture_contract(
    payload: list[dict[str, Any]],
    path: Path | None = None,
    *,
    tree_root: Path | None = None,
    sort_keys: bool = False,
) -> None:
    write_json_list(path or fixture_contract_path(tree_root), payload, sort_keys=sort_keys)


def write_inventory_contract(
    payload: list[dict[str, Any]],
    path: Path | None = None,
    *,
    tree_root: Path | None = None,
    sort_keys: bool = False,
) -> None:
    write_json_list(path or inventory_contract_path(tree_root), payload, sort_keys=sort_keys)


def append_json_list_items(
    path: Path,
    items: tuple[dict[str, Any], ...],
    *,
    dry_run: bool,
    sort_keys: bool = False,
) -> None:
    payload = load_json_list(path)
    payload.extend(items)
    if not dry_run:
        write_json_list(path, payload, sort_keys=sort_keys)
