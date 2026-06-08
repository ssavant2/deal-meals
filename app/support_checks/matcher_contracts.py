#!/usr/bin/env python3
"""Shared access helpers for matcher contract sources."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import tomllib
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = APP_DIR.parent
MATCHER_CONTRACTS_RELATIVE_DIR = Path("languages") / "sv" / "matcher_contracts"
MATCHER_CONTRACT_SOURCES_RELATIVE_DIR = MATCHER_CONTRACTS_RELATIVE_DIR / "sources"
FIXTURE_CONTRACT_FILENAME = "matcher_regression_cases.toml"
INVENTORY_CONTRACT_FILENAME = "matcher_rule_inventory.toml"


@dataclass(frozen=True)
class MatcherContractPaths:
    app_dir: Path
    repo_root: Path
    contract_dir: Path
    source_dir: Path
    fixture_file: Path
    inventory_file: Path


@dataclass(frozen=True)
class ContractSpec:
    contract: str
    table_name: str
    repo_root: Path
    source_toml_path: Path


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
    source_dir = app_dir / MATCHER_CONTRACT_SOURCES_RELATIVE_DIR
    return MatcherContractPaths(
        app_dir=app_dir,
        repo_root=repo_root,
        contract_dir=contract_dir,
        source_dir=source_dir,
        fixture_file=source_dir / FIXTURE_CONTRACT_FILENAME,
        inventory_file=source_dir / INVENTORY_CONTRACT_FILENAME,
    )


def fixture_contract_path(tree_root: Path | None = None) -> Path:
    return contract_paths(tree_root).fixture_file


def inventory_contract_path(tree_root: Path | None = None) -> Path:
    return contract_paths(tree_root).inventory_file


def source_dir_for_tree_root(tree_root: Path | None = None) -> Path:
    return contract_paths(tree_root).source_dir


def contract_specs(
    tree_root: Path | None = None,
    *,
    source_dir: Path | None = None,
) -> tuple[ContractSpec, ...]:
    paths = contract_paths(tree_root)
    source_root = source_dir or paths.source_dir
    return (
        ContractSpec(
            contract="matcher_regression_cases",
            table_name="fixtures",
            repo_root=paths.repo_root,
            source_toml_path=source_root / FIXTURE_CONTRACT_FILENAME,
        ),
        ContractSpec(
            contract="matcher_rule_inventory",
            table_name="inventory",
            repo_root=paths.repo_root,
            source_toml_path=source_root / INVENTORY_CONTRACT_FILENAME,
        ),
    )


def contract_spec_by_name(
    contract: str,
    *,
    tree_root: Path | None = None,
    source_dir: Path | None = None,
) -> ContractSpec:
    for spec in contract_specs(tree_root, source_dir=source_dir):
        if spec.contract == contract:
            return spec
    raise ValueError(f"unknown contract: {contract}")


def _repo_rel(path: Path, *, repo_root: Path = REPO_DIR) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _toml_key(key: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return json.dumps(key, ensure_ascii=False)


def _toml_path(parts: tuple[str, ...]) -> str:
    return ".".join(_toml_key(part) for part in parts)


def _toml_scalar(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    raise TypeError(f"unsupported TOML scalar type: {type(value).__name__}")


def _toml_array(values: list[Any]) -> str:
    if not all(not isinstance(value, (dict, list)) for value in values):
        raise TypeError("TOML inline arrays only support scalar values in this contract schema")
    return "[" + ", ".join(_toml_scalar(value) for value in values) + "]"


def _is_table_array(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, dict) for item in value)


def _emit_mapping(lines: list[str], mapping: dict[str, Any], table_path: tuple[str, ...]) -> None:
    scalar_items: list[tuple[str, Any]] = []
    dict_items: list[tuple[str, dict[str, Any]]] = []
    table_array_items: list[tuple[str, list[dict[str, Any]]]] = []

    for key, value in mapping.items():
        if isinstance(value, dict):
            dict_items.append((key, value))
        elif _is_table_array(value):
            table_array_items.append((key, value))
        else:
            scalar_items.append((key, value))

    for key, value in scalar_items:
        if isinstance(value, list):
            lines.append(f"{_toml_key(key)} = {_toml_array(value)}")
        else:
            lines.append(f"{_toml_key(key)} = {_toml_scalar(value)}")

    for key, value in dict_items:
        lines.append("")
        lines.append(f"[{_toml_path((*table_path, key))}]")
        _emit_mapping(lines, value, (*table_path, key))

    for key, values in table_array_items:
        for item in values:
            lines.append("")
            lines.append(f"[[{_toml_path((*table_path, key))}]]")
            _emit_mapping(lines, item, (*table_path, key))


def _source_toml(spec: ContractSpec, payload: list[dict[str, Any]]) -> str:
    lines = [
        "# AUTHORITATIVE MATCHER CONTRACT TOML SOURCE.",
        "# Canonical emitter: support_checks/matcher_contracts.py.",
        "# Edit this source, then regenerate derived registry coverage.",
        "schema_version = 1",
        f"contract = {_toml_scalar(spec.contract)}",
    ]
    for row in payload:
        lines.append("")
        lines.append(f"[[{_toml_key(spec.table_name)}]]")
        _emit_mapping(lines, row, (spec.table_name,))
    return "\n".join(lines).rstrip() + "\n"


def _payload_from_source_toml(spec: ContractSpec, toml_text: str) -> list[dict[str, Any]]:
    parsed = tomllib.loads(toml_text)
    payload = parsed.get(spec.table_name)
    if not isinstance(payload, list):
        raise ValueError(f"{spec.source_toml_path.name} must contain [[{spec.table_name}]]")
    if not all(isinstance(row, dict) for row in payload):
        raise ValueError(f"{spec.source_toml_path.name} rows must be TOML tables")
    return payload


def load_contract_source(spec: ContractSpec) -> list[dict[str, Any]]:
    return _payload_from_source_toml(spec, spec.source_toml_path.read_text(encoding="utf-8"))


def write_contract_source(spec: ContractSpec, payload: list[dict[str, Any]]) -> None:
    spec.source_toml_path.parent.mkdir(parents=True, exist_ok=True)
    spec.source_toml_path.write_text(_source_toml(spec, payload), encoding="utf-8")


def canonical_json(payload: list[dict[str, Any]]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _spec_for_path(path: Path, *, tree_root: Path | None, contract: str) -> ContractSpec:
    if path.suffix != ".toml":
        raise ValueError(f"matcher contract source must be TOML: {path}")
    if path.name == FIXTURE_CONTRACT_FILENAME or contract == "matcher_regression_cases":
        base = contract_spec_by_name("matcher_regression_cases", tree_root=tree_root)
    elif path.name == INVENTORY_CONTRACT_FILENAME or contract == "matcher_rule_inventory":
        base = contract_spec_by_name("matcher_rule_inventory", tree_root=tree_root)
    else:
        raise ValueError(f"cannot infer matcher contract type from path: {path}")
    return ContractSpec(
        contract=base.contract,
        table_name=base.table_name,
        repo_root=base.repo_root,
        source_toml_path=path,
    )


def load_fixture_contract(path: Path | None = None, *, tree_root: Path | None = None) -> list[dict[str, Any]]:
    path = path or fixture_contract_path(tree_root)
    return load_contract_source(_spec_for_path(path, tree_root=tree_root, contract="matcher_regression_cases"))


def load_inventory_contract(path: Path | None = None, *, tree_root: Path | None = None) -> list[dict[str, Any]]:
    path = path or inventory_contract_path(tree_root)
    return load_contract_source(_spec_for_path(path, tree_root=tree_root, contract="matcher_rule_inventory"))


def write_fixture_contract(
    payload: list[dict[str, Any]],
    path: Path | None = None,
    *,
    tree_root: Path | None = None,
    sort_keys: bool = False,
) -> None:
    path = path or fixture_contract_path(tree_root)
    write_contract_source(_spec_for_path(path, tree_root=tree_root, contract="matcher_regression_cases"), payload)


def write_inventory_contract(
    payload: list[dict[str, Any]],
    path: Path | None = None,
    *,
    tree_root: Path | None = None,
    sort_keys: bool = False,
) -> None:
    path = path or inventory_contract_path(tree_root)
    write_contract_source(_spec_for_path(path, tree_root=tree_root, contract="matcher_rule_inventory"), payload)
