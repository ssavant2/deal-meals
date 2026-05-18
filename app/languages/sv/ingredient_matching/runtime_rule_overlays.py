"""Runtime-rule overlays written by the dm matcher CLI.

The historical runtime tables still live in their owning modules. This loader
adds a small TOML-backed overlay for new Track A rules so the CLI can write data
without rewriting large Python dict literals.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Set
import tomllib

try:
    from languages.sv.normalization import fix_swedish_chars
except ModuleNotFoundError:
    from app.languages.sv.normalization import fix_swedish_chars


OVERLAY_PATH = Path(__file__).with_suffix(".toml")


class RuntimeRuleOverlayError(ValueError):
    """Raised when the runtime overlay TOML is malformed."""


@dataclass(frozen=True)
class RuntimeRuleOverlays:
    product_name_blockers: Dict[str, Set[str]]
    false_positive_blockers: Dict[str, Set[str]]
    keyword_suppressed_by_context: Dict[str, Set[str]]


_SECTION_VALUE_FIELDS = {
    "product_name_blockers": "blockers",
    "false_positive_blockers": "blockers",
    "keyword_suppressed_by_context": "context",
}
_ALLOWED_ENTRY_KEYS = {
    section: frozenset({"keyword", value_field, "reason"})
    for section, value_field in _SECTION_VALUE_FIELDS.items()
}


def _normalize_text(value: str) -> str:
    return fix_swedish_chars(value).lower()


def _path_label(path: Path, section: str, index: int) -> str:
    return f"{path}:{section}[{index}]"


def _require_string(value: Any, *, path: Path, section: str, index: int, field: str) -> str:
    if not isinstance(value, str):
        raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)}.{field} must be a string")
    stripped = value.strip()
    if not stripped:
        raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)}.{field} must not be empty")
    return stripped


def _require_string_list(value: Any, *, path: Path, section: str, index: int, field: str) -> list[str]:
    if not isinstance(value, list):
        raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)}.{field} must be a list")
    values = [
        _require_string(item, path=path, section=section, index=index, field=f"{field}[]")
        for item in value
    ]
    if not values:
        raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)}.{field} must not be empty")
    return values


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeRuleOverlayError(f"{path}: invalid TOML: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeRuleOverlayError(f"{path}: TOML root must be a table")
    return payload


def _merge_section(payload: dict[str, Any], section: str, *, path: Path) -> Dict[str, Set[str]]:
    raw_entries = payload.get(section, [])
    if not isinstance(raw_entries, list):
        raise RuntimeRuleOverlayError(f"{path}:{section} must be a list of tables")

    value_field = _SECTION_VALUE_FIELDS[section]
    allowed_keys = _ALLOWED_ENTRY_KEYS[section]
    merged: Dict[str, Set[str]] = {}
    for index, entry in enumerate(raw_entries, start=1):
        if not isinstance(entry, dict):
            raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} must be a table")
        unknown_keys = sorted(set(entry) - allowed_keys)
        if unknown_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} has unknown keys: {', '.join(unknown_keys)}"
            )
        missing_keys = sorted(allowed_keys - set(entry))
        if missing_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} is missing keys: {', '.join(missing_keys)}"
            )

        keyword = _normalize_text(_require_string(
            entry["keyword"],
            path=path,
            section=section,
            index=index,
            field="keyword",
        ))
        _require_string(entry["reason"], path=path, section=section, index=index, field="reason")
        values = {
            _normalize_text(item)
            for item in _require_string_list(
                entry[value_field],
                path=path,
                section=section,
                index=index,
                field=value_field,
            )
        }
        merged.setdefault(keyword, set()).update(values)
    return merged


def load_runtime_rule_overlays(path: Path = OVERLAY_PATH) -> RuntimeRuleOverlays:
    payload = _load_toml(path)
    unknown_sections = sorted(set(payload) - set(_SECTION_VALUE_FIELDS))
    if unknown_sections:
        raise RuntimeRuleOverlayError(f"{path}: unknown sections: {', '.join(unknown_sections)}")

    return RuntimeRuleOverlays(
        product_name_blockers=_merge_section(payload, "product_name_blockers", path=path),
        false_positive_blockers=_merge_section(payload, "false_positive_blockers", path=path),
        keyword_suppressed_by_context=_merge_section(payload, "keyword_suppressed_by_context", path=path),
    )


_OVERLAYS = load_runtime_rule_overlays()

PRODUCT_NAME_BLOCKER_CLI_UPDATES = _OVERLAYS.product_name_blockers
FALSE_POSITIVE_BLOCKER_CLI_UPDATES = _OVERLAYS.false_positive_blockers
KEYWORD_SUPPRESSED_BY_CONTEXT_CLI_UPDATES = _OVERLAYS.keyword_suppressed_by_context
