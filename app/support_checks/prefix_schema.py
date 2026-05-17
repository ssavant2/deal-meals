"""Shared prefix allow-lists for matcher support checks."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
from typing import Any

import yaml


APP_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PREFIX_SCHEMA = APP_DIR / "support_checks" / "schemas" / "prefixes.yml"


@lru_cache(maxsize=1)
def load_prefix_schema(path: Path = DEFAULT_PREFIX_SCHEMA) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"prefix schema must be a mapping: {path}")
    if payload.get("version") != 1:
        raise ValueError(f"unsupported prefix schema version: {payload.get('version')!r}")
    return payload


def allowed_prefixes(kind: str) -> tuple[str, ...]:
    section = load_prefix_schema().get(kind) or {}
    prefixes = section.get("allowed_prefixes") or []
    if not isinstance(prefixes, list) or not all(isinstance(prefix, str) for prefix in prefixes):
        raise ValueError(f"prefix schema {kind}.allowed_prefixes must be a string list")
    return tuple(prefixes)


def diagnostic_prefixes(kind: str = "adapter_ref") -> tuple[str, ...]:
    section = load_prefix_schema().get(kind) or {}
    prefixes = section.get("diagnostic_prefixes") or []
    if not isinstance(prefixes, list) or not all(isinstance(prefix, str) for prefix in prefixes):
        raise ValueError(f"prefix schema {kind}.diagnostic_prefixes must be a string list")
    return tuple(prefixes)


def non_registered_prefixes(kind: str = "adapter_ref") -> tuple[str, ...]:
    section = load_prefix_schema().get(kind) or {}
    prefixes = section.get("non_registered_prefixes") or section.get("diagnostic_prefixes") or []
    if not isinstance(prefixes, list) or not all(isinstance(prefix, str) for prefix in prefixes):
        raise ValueError(f"prefix schema {kind}.non_registered_prefixes must be a string list")
    return tuple(prefixes)


def temporary_patterns(kind: str) -> tuple[str, ...]:
    section = load_prefix_schema().get(kind) or {}
    patterns = section.get("temporary_patterns") or []
    if not isinstance(patterns, list) or not all(isinstance(pattern, str) for pattern in patterns):
        raise ValueError(f"prefix schema {kind}.temporary_patterns must be a string list")
    return tuple(patterns)


def temporary_re(kind: str, *, fullmatch: bool = False) -> re.Pattern[str]:
    patterns = temporary_patterns(kind)
    if not patterns:
        return re.compile(r"a^")
    body = "|".join(f"(?:{pattern})" for pattern in patterns)
    if fullmatch:
        body = f"^(?:{body})$"
    return re.compile(body)


def prefix_hint(kind: str) -> str:
    return f"Allowed: {', '.join(allowed_prefixes(kind))}"
