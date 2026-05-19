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
    processed_product_rules: Dict[str, Set[str]]
    processed_rule_compound_exemptions: Dict[str, Set[str]]
    global_product_name_blockers: Set[str]
    strict_processed_rules: Set[str]
    carrier_context_required: Set[str]
    context_required_words: Set[str]
    ingredient_requires_in_product: Set[str]
    space_normalizations: tuple[tuple[str, str], ...]
    keyword_set_updates: Dict[str, Dict[str, Set[str]]]
    carrier_set_updates: Dict[str, Dict[str, Set[str]]]
    cuisine_context: Dict[str, Set[str]]
    context_word_keyword_exemptions: Dict[str, Set[str]]
    compound_protection_updates: Dict[str, Set[str]]
    specialty_qualifier_updates: Dict[str, Set[str]]
    specialty_bidirectional_updates: Dict[str, Set[str]]
    qualifier_equivalent_updates: Dict[str, Set[str]]
    product_name_substitutions: tuple[tuple[frozenset[str], str, str], ...]
    secondary_ingredient_patterns: Dict[str, tuple[Set[str], Set[str]]]


_SECTION_VALUE_FIELDS = {
    "product_name_blockers": "blockers",
    "false_positive_blockers": "blockers",
    "keyword_suppressed_by_context": "context",
    "processed_product_rules": "blocked_product_words",
    "processed_rule_compound_exemptions": "compounds",
}
_TERM_SET_SECTIONS = {
    "carrier_context_required": "terms",
    "context_required_words": "terms",
    "global_product_name_blockers": "terms",
    "ingredient_requires_in_product": "terms",
    "strict_processed_rules": "terms",
}
_PAIR_SECTION_FIELDS = {
    "space_normalizations": ("source", "target"),
}
_CONTEXT_SECTION_FIELDS = {
    "context_word_keyword_exemptions": ("keyword", "context_words"),
    "cuisine_context": ("trigger", "contexts"),
}
_SET_UPDATE_SECTIONS = {
    "keyword_set_updates": frozenset({
        "flavor_words",
        "important_short_keywords",
        "non_food_keywords",
        "processed_foods",
        "qualifier_required_keywords",
        "stop_words",
    }),
    "carrier_set_updates": frozenset({"carrier_products"}),
}
_SET_ACTIONS = frozenset({"add", "remove"})
_COMPOUND_PROTECTION_MODES = frozenset({
    "suffix_strict",
    "prefix_strict",
    "suffix_protected",
    "embedded_protected",
})
_METADATA_KEYS = frozenset({"id", "status", "inactive_reason"})
_ALLOWED_ENTRY_KEYS = {
    section: frozenset({"keyword", value_field, "reason", *_METADATA_KEYS})
    for section, value_field in _SECTION_VALUE_FIELDS.items()
}
_ALLOWED_TERM_SET_ENTRY_KEYS = {
    section: frozenset({terms_field, "reason", *_METADATA_KEYS})
    for section, terms_field in _TERM_SET_SECTIONS.items()
}
_ALLOWED_PAIR_ENTRY_KEYS = {
    section: frozenset({source_field, target_field, "reason", *_METADATA_KEYS})
    for section, (source_field, target_field) in _PAIR_SECTION_FIELDS.items()
}
_ALLOWED_CONTEXT_ENTRY_KEYS = {
    section: frozenset({key_field, values_field, "reason", *_METADATA_KEYS})
    for section, (key_field, values_field) in _CONTEXT_SECTION_FIELDS.items()
}
_ALLOWED_SET_UPDATE_ENTRY_KEYS = {
    section: frozenset({"surface", "action", "terms", "reason", *_METADATA_KEYS})
    for section in _SET_UPDATE_SECTIONS
}
_ALLOWED_COMPOUND_PROTECTION_ENTRY_KEYS = frozenset({"id", "status", "mode", "keywords", "reason", "inactive_reason"})
_ALLOWED_SPECIALTY_ENTRY_KEYS = frozenset({
    "id", "status", "keyword", "qualifiers", "bidirectional", "reason", "inactive_reason",
})
_ALLOWED_QUALIFIER_EQUIVALENT_ENTRY_KEYS = frozenset({
    "id", "status", "qualifier", "equivalents", "reason", "inactive_reason",
})
_ALLOWED_PRODUCT_NAME_SUBSTITUTION_ENTRY_KEYS = frozenset({
    "id", "status", "required_words", "old_keyword", "new_keyword", "reason", "inactive_reason",
})
_ALLOWED_SECONDARY_INGREDIENT_PATTERN_ENTRY_KEYS = frozenset({
    "id", "status", "keyword", "blockers", "exceptions", "reason", "inactive_reason",
})
_VALID_STATUSES = frozenset({"active", "inactive"})


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


def _entry_status(entry: dict[str, Any], *, path: Path, section: str, index: int) -> str:
    metadata_keys = _METADATA_KEYS & set(entry)
    if metadata_keys and not {"id", "status"}.issubset(entry):
        raise RuntimeRuleOverlayError(
            f"{_path_label(path, section, index)} v2 metadata requires both id and status"
        )

    if "id" in entry:
        _require_string(entry["id"], path=path, section=section, index=index, field="id")
    if "inactive_reason" in entry:
        _require_string(
            entry["inactive_reason"],
            path=path,
            section=section,
            index=index,
            field="inactive_reason",
        )
    if "status" not in entry:
        return "active"

    status = _require_string(entry["status"], path=path, section=section, index=index, field="status").lower()
    if status not in _VALID_STATUSES:
        raise RuntimeRuleOverlayError(
            f"{_path_label(path, section, index)}.status must be one of: {', '.join(sorted(_VALID_STATUSES))}"
        )
    return status


def _merge_section(
    payload: dict[str, Any],
    section: str,
    *,
    path: Path,
    seen_ids: set[str],
    seen_effective_values: set[tuple[str, str, str]],
) -> Dict[str, Set[str]]:
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
        required_keys = {"keyword", value_field, "reason"}
        missing_keys = sorted(required_keys - set(entry))
        if missing_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} is missing keys: {', '.join(missing_keys)}"
            )

        status = _entry_status(entry, path=path, section=section, index=index)
        entry_id = entry.get("id")
        if entry_id is not None:
            normalized_id = _require_string(entry_id, path=path, section=section, index=index, field="id")
            if normalized_id in seen_ids:
                raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} has duplicate id: {normalized_id}")
            seen_ids.add(normalized_id)

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
        if status == "inactive":
            continue
        for value in values:
            effective_value = (section, keyword, value)
            if effective_value in seen_effective_values:
                raise RuntimeRuleOverlayError(
                    f"{_path_label(path, section, index)} duplicates active {keyword!r} -> {value!r}"
                )
            seen_effective_values.add(effective_value)
        merged.setdefault(keyword, set()).update(values)
    return merged


def _load_term_set_section(
    payload: dict[str, Any],
    section: str,
    *,
    path: Path,
    seen_ids: set[str],
    seen_effective_terms: set[tuple[str, str]],
) -> Set[str]:
    raw_entries = payload.get(section, [])
    if not isinstance(raw_entries, list):
        raise RuntimeRuleOverlayError(f"{path}:{section} must be a list of tables")

    terms_field = _TERM_SET_SECTIONS[section]
    allowed_keys = _ALLOWED_TERM_SET_ENTRY_KEYS[section]
    merged: Set[str] = set()
    for index, entry in enumerate(raw_entries, start=1):
        if not isinstance(entry, dict):
            raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} must be a table")
        unknown_keys = sorted(set(entry) - allowed_keys)
        if unknown_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} has unknown keys: {', '.join(unknown_keys)}"
            )
        required_keys = {terms_field, "reason"}
        missing_keys = sorted(required_keys - set(entry))
        if missing_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} is missing keys: {', '.join(missing_keys)}"
            )

        status = _entry_status(entry, path=path, section=section, index=index)
        entry_id = entry.get("id")
        if entry_id is not None:
            normalized_id = _require_string(entry_id, path=path, section=section, index=index, field="id")
            if normalized_id in seen_ids:
                raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} has duplicate id: {normalized_id}")
            seen_ids.add(normalized_id)

        _require_string(entry["reason"], path=path, section=section, index=index, field="reason")
        terms = {
            _normalize_text(item)
            for item in _require_string_list(
                entry[terms_field],
                path=path,
                section=section,
                index=index,
                field=terms_field,
            )
        }
        if status == "inactive":
            continue
        for term in terms:
            key = (section, term)
            if key in seen_effective_terms:
                raise RuntimeRuleOverlayError(
                    f"{_path_label(path, section, index)} duplicates active term {term!r}"
                )
            seen_effective_terms.add(key)
        merged.update(terms)
    return merged


def _load_pair_section(
    payload: dict[str, Any],
    section: str,
    *,
    path: Path,
    seen_ids: set[str],
    seen_effective_pairs: set[tuple[str, str, str]],
) -> tuple[tuple[str, str], ...]:
    raw_entries = payload.get(section, [])
    if not isinstance(raw_entries, list):
        raise RuntimeRuleOverlayError(f"{path}:{section} must be a list of tables")

    source_field, target_field = _PAIR_SECTION_FIELDS[section]
    allowed_keys = _ALLOWED_PAIR_ENTRY_KEYS[section]
    pairs: list[tuple[str, str]] = []
    seen_sources: set[str] = set()
    for index, entry in enumerate(raw_entries, start=1):
        if not isinstance(entry, dict):
            raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} must be a table")
        unknown_keys = sorted(set(entry) - allowed_keys)
        if unknown_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} has unknown keys: {', '.join(unknown_keys)}"
            )
        required_keys = {source_field, target_field, "reason"}
        missing_keys = sorted(required_keys - set(entry))
        if missing_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} is missing keys: {', '.join(missing_keys)}"
            )

        status = _entry_status(entry, path=path, section=section, index=index)
        entry_id = entry.get("id")
        if entry_id is not None:
            normalized_id = _require_string(entry_id, path=path, section=section, index=index, field="id")
            if normalized_id in seen_ids:
                raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} has duplicate id: {normalized_id}")
            seen_ids.add(normalized_id)

        source = _normalize_text(_require_string(
            entry[source_field],
            path=path,
            section=section,
            index=index,
            field=source_field,
        ))
        target = _normalize_text(_require_string(
            entry[target_field],
            path=path,
            section=section,
            index=index,
            field=target_field,
        ))
        _require_string(entry["reason"], path=path, section=section, index=index, field="reason")
        if status == "inactive":
            continue

        if source in seen_sources:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} duplicates active source {source!r}"
            )
        seen_sources.add(source)
        effective_pair = (section, source, target)
        if effective_pair in seen_effective_pairs:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} duplicates active {source!r} -> {target!r}"
            )
        seen_effective_pairs.add(effective_pair)
        pairs.append((source, target))
    return tuple(pairs)


def _load_context_section(
    payload: dict[str, Any],
    section: str,
    *,
    path: Path,
    seen_ids: set[str],
    seen_effective_values: set[tuple[str, str, str]],
) -> Dict[str, Set[str]]:
    raw_entries = payload.get(section, [])
    if not isinstance(raw_entries, list):
        raise RuntimeRuleOverlayError(f"{path}:{section} must be a list of tables")

    key_field, values_field = _CONTEXT_SECTION_FIELDS[section]
    allowed_keys = _ALLOWED_CONTEXT_ENTRY_KEYS[section]
    merged: Dict[str, Set[str]] = {}
    for index, entry in enumerate(raw_entries, start=1):
        if not isinstance(entry, dict):
            raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} must be a table")
        unknown_keys = sorted(set(entry) - allowed_keys)
        if unknown_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} has unknown keys: {', '.join(unknown_keys)}"
            )
        missing_keys = sorted({key_field, values_field, "reason"} - set(entry))
        if missing_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} is missing keys: {', '.join(missing_keys)}"
            )

        status = _entry_status(entry, path=path, section=section, index=index)
        entry_id = entry.get("id")
        if entry_id is not None:
            normalized_id = _require_string(entry_id, path=path, section=section, index=index, field="id")
            if normalized_id in seen_ids:
                raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} has duplicate id: {normalized_id}")
            seen_ids.add(normalized_id)

        key = _normalize_text(_require_string(entry[key_field], path=path, section=section, index=index, field=key_field))
        values = {
            _normalize_text(item)
            for item in _require_string_list(entry[values_field], path=path, section=section, index=index, field=values_field)
        }
        _require_string(entry["reason"], path=path, section=section, index=index, field="reason")
        if status == "inactive":
            continue
        for value in values:
            effective_value = (section, key, value)
            if effective_value in seen_effective_values:
                raise RuntimeRuleOverlayError(
                    f"{_path_label(path, section, index)} duplicates active {key!r} -> {value!r}"
                )
            seen_effective_values.add(effective_value)
        merged.setdefault(key, set()).update(values)
    return merged


def _load_set_update_section(
    payload: dict[str, Any],
    section: str,
    *,
    path: Path,
    seen_ids: set[str],
    seen_effective_updates: set[tuple[str, str, str, str]],
) -> Dict[str, Dict[str, Set[str]]]:
    raw_entries = payload.get(section, [])
    if not isinstance(raw_entries, list):
        raise RuntimeRuleOverlayError(f"{path}:{section} must be a list of tables")

    allowed_surfaces = _SET_UPDATE_SECTIONS[section]
    allowed_keys = _ALLOWED_SET_UPDATE_ENTRY_KEYS[section]
    updates: Dict[str, Dict[str, Set[str]]] = {}
    for index, entry in enumerate(raw_entries, start=1):
        if not isinstance(entry, dict):
            raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} must be a table")
        unknown_keys = sorted(set(entry) - allowed_keys)
        if unknown_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} has unknown keys: {', '.join(unknown_keys)}"
            )
        missing_keys = sorted({"surface", "action", "terms", "reason"} - set(entry))
        if missing_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} is missing keys: {', '.join(missing_keys)}"
            )

        status = _entry_status(entry, path=path, section=section, index=index)
        entry_id = entry.get("id")
        if entry_id is not None:
            normalized_id = _require_string(entry_id, path=path, section=section, index=index, field="id")
            if normalized_id in seen_ids:
                raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} has duplicate id: {normalized_id}")
            seen_ids.add(normalized_id)

        surface = _require_string(entry["surface"], path=path, section=section, index=index, field="surface")
        surface = surface.strip().lower().replace("-", "_")
        if surface not in allowed_surfaces:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)}.surface must be one of: "
                f"{', '.join(sorted(allowed_surfaces))}"
            )
        action = _require_string(entry["action"], path=path, section=section, index=index, field="action").lower()
        if action not in _SET_ACTIONS:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)}.action must be one of: {', '.join(sorted(_SET_ACTIONS))}"
            )
        terms = {
            _normalize_text(item)
            for item in _require_string_list(
                entry["terms"],
                path=path,
                section=section,
                index=index,
                field="terms",
            )
        }
        _require_string(entry["reason"], path=path, section=section, index=index, field="reason")
        if status == "inactive":
            continue

        surface_updates = updates.setdefault(surface, {"add": set(), "remove": set()})
        for term in terms:
            effective_update = (section, surface, action, term)
            if effective_update in seen_effective_updates:
                raise RuntimeRuleOverlayError(
                    f"{_path_label(path, section, index)} duplicates active {surface}.{action} {term!r}"
                )
            seen_effective_updates.add(effective_update)
            surface_updates[action].add(term)
    return updates


def _load_compound_protection_updates(
    payload: dict[str, Any],
    *,
    path: Path,
    seen_ids: set[str],
    seen_effective_updates: set[tuple[str, str]],
) -> Dict[str, Set[str]]:
    section = "compound_protection_updates"
    raw_entries = payload.get(section, [])
    if not isinstance(raw_entries, list):
        raise RuntimeRuleOverlayError(f"{path}:{section} must be a list of tables")

    updates: Dict[str, Set[str]] = {}
    for index, entry in enumerate(raw_entries, start=1):
        if not isinstance(entry, dict):
            raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} must be a table")
        unknown_keys = sorted(set(entry) - _ALLOWED_COMPOUND_PROTECTION_ENTRY_KEYS)
        if unknown_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} has unknown keys: {', '.join(unknown_keys)}"
            )
        missing_keys = sorted({"mode", "keywords", "reason"} - set(entry))
        if missing_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} is missing keys: {', '.join(missing_keys)}"
            )
        status = _entry_status(entry, path=path, section=section, index=index)
        entry_id = entry.get("id")
        if entry_id is not None:
            normalized_id = _require_string(entry_id, path=path, section=section, index=index, field="id")
            if normalized_id in seen_ids:
                raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} has duplicate id: {normalized_id}")
            seen_ids.add(normalized_id)
        mode = _require_string(entry["mode"], path=path, section=section, index=index, field="mode")
        mode = mode.strip().lower().replace("-", "_")
        if mode not in _COMPOUND_PROTECTION_MODES:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)}.mode must be one of: "
                f"{', '.join(sorted(_COMPOUND_PROTECTION_MODES))}"
            )
        keywords = {
            _normalize_text(item)
            for item in _require_string_list(entry["keywords"], path=path, section=section, index=index, field="keywords")
        }
        _require_string(entry["reason"], path=path, section=section, index=index, field="reason")
        if status == "inactive":
            continue
        mode_updates = updates.setdefault(mode, set())
        for keyword in keywords:
            effective_update = (mode, keyword)
            if effective_update in seen_effective_updates:
                raise RuntimeRuleOverlayError(
                    f"{_path_label(path, section, index)} duplicates active {mode} {keyword!r}"
                )
            seen_effective_updates.add(effective_update)
            mode_updates.add(keyword)
    return updates


def _require_bool(value: Any, *, path: Path, section: str, index: int, field: str) -> bool:
    if not isinstance(value, bool):
        raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)}.{field} must be a boolean")
    return value


def _load_specialty_qualifier_updates(
    payload: dict[str, Any],
    *,
    path: Path,
    seen_ids: set[str],
    seen_effective_updates: set[tuple[str, str]],
) -> tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    section = "specialty_qualifiers"
    raw_entries = payload.get(section, [])
    if not isinstance(raw_entries, list):
        raise RuntimeRuleOverlayError(f"{path}:{section} must be a list of tables")
    updates: Dict[str, Set[str]] = {}
    bidirectional_updates: Dict[str, Set[str]] = {}
    for index, entry in enumerate(raw_entries, start=1):
        if not isinstance(entry, dict):
            raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} must be a table")
        unknown_keys = sorted(set(entry) - _ALLOWED_SPECIALTY_ENTRY_KEYS)
        if unknown_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} has unknown keys: {', '.join(unknown_keys)}"
            )
        missing_keys = sorted({"keyword", "qualifiers", "reason"} - set(entry))
        if missing_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} is missing keys: {', '.join(missing_keys)}"
            )
        status = _entry_status(entry, path=path, section=section, index=index)
        entry_id = entry.get("id")
        if entry_id is not None:
            normalized_id = _require_string(entry_id, path=path, section=section, index=index, field="id")
            if normalized_id in seen_ids:
                raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} has duplicate id: {normalized_id}")
            seen_ids.add(normalized_id)
        keyword = _normalize_text(_require_string(entry["keyword"], path=path, section=section, index=index, field="keyword"))
        qualifiers = {
            _normalize_text(item)
            for item in _require_string_list(
                entry["qualifiers"],
                path=path,
                section=section,
                index=index,
                field="qualifiers",
            )
        }
        bidirectional = (
            _require_bool(entry["bidirectional"], path=path, section=section, index=index, field="bidirectional")
            if "bidirectional" in entry
            else False
        )
        _require_string(entry["reason"], path=path, section=section, index=index, field="reason")
        if status == "inactive":
            continue
        target = bidirectional_updates if bidirectional else updates
        for qualifier in qualifiers:
            effective_update = (keyword, qualifier)
            if effective_update in seen_effective_updates:
                raise RuntimeRuleOverlayError(
                    f"{_path_label(path, section, index)} duplicates active {keyword!r} -> {qualifier!r}"
                )
            seen_effective_updates.add(effective_update)
            target.setdefault(keyword, set()).add(qualifier)
            updates.setdefault(keyword, set()).add(qualifier)
    return updates, bidirectional_updates


def _load_qualifier_equivalent_updates(
    payload: dict[str, Any],
    *,
    path: Path,
    seen_ids: set[str],
    seen_effective_updates: set[tuple[str, str]],
) -> Dict[str, Set[str]]:
    section = "qualifier_equivalents"
    raw_entries = payload.get(section, [])
    if not isinstance(raw_entries, list):
        raise RuntimeRuleOverlayError(f"{path}:{section} must be a list of tables")
    updates: Dict[str, Set[str]] = {}
    for index, entry in enumerate(raw_entries, start=1):
        if not isinstance(entry, dict):
            raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} must be a table")
        unknown_keys = sorted(set(entry) - _ALLOWED_QUALIFIER_EQUIVALENT_ENTRY_KEYS)
        if unknown_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} has unknown keys: {', '.join(unknown_keys)}"
            )
        missing_keys = sorted({"qualifier", "equivalents", "reason"} - set(entry))
        if missing_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} is missing keys: {', '.join(missing_keys)}"
            )
        status = _entry_status(entry, path=path, section=section, index=index)
        entry_id = entry.get("id")
        if entry_id is not None:
            normalized_id = _require_string(entry_id, path=path, section=section, index=index, field="id")
            if normalized_id in seen_ids:
                raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} has duplicate id: {normalized_id}")
            seen_ids.add(normalized_id)
        qualifier = _normalize_text(_require_string(entry["qualifier"], path=path, section=section, index=index, field="qualifier"))
        equivalents = {
            _normalize_text(item)
            for item in _require_string_list(
                entry["equivalents"],
                path=path,
                section=section,
                index=index,
                field="equivalents",
            )
        }
        _require_string(entry["reason"], path=path, section=section, index=index, field="reason")
        if status == "inactive":
            continue
        for equivalent in equivalents:
            effective_update = (qualifier, equivalent)
            if effective_update in seen_effective_updates:
                raise RuntimeRuleOverlayError(
                    f"{_path_label(path, section, index)} duplicates active {qualifier!r} -> {equivalent!r}"
                )
            seen_effective_updates.add(effective_update)
            updates.setdefault(qualifier, set()).add(equivalent)
    return updates


def _load_product_name_substitutions(
    payload: dict[str, Any],
    *,
    path: Path,
    seen_ids: set[str],
    seen_effective_updates: set[tuple[frozenset[str], str, str]],
) -> tuple[tuple[frozenset[str], str, str], ...]:
    section = "product_name_substitutions"
    raw_entries = payload.get(section, [])
    if not isinstance(raw_entries, list):
        raise RuntimeRuleOverlayError(f"{path}:{section} must be a list of tables")
    updates: list[tuple[frozenset[str], str, str]] = []
    for index, entry in enumerate(raw_entries, start=1):
        if not isinstance(entry, dict):
            raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} must be a table")
        unknown_keys = sorted(set(entry) - _ALLOWED_PRODUCT_NAME_SUBSTITUTION_ENTRY_KEYS)
        if unknown_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} has unknown keys: {', '.join(unknown_keys)}"
            )
        missing_keys = sorted({"required_words", "old_keyword", "new_keyword", "reason"} - set(entry))
        if missing_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} is missing keys: {', '.join(missing_keys)}"
            )
        status = _entry_status(entry, path=path, section=section, index=index)
        entry_id = entry.get("id")
        if entry_id is not None:
            normalized_id = _require_string(entry_id, path=path, section=section, index=index, field="id")
            if normalized_id in seen_ids:
                raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} has duplicate id: {normalized_id}")
            seen_ids.add(normalized_id)
        required_words = frozenset(
            _normalize_text(item)
            for item in _require_string_list(
                entry["required_words"],
                path=path,
                section=section,
                index=index,
                field="required_words",
            )
        )
        old_keyword = _normalize_text(_require_string(entry["old_keyword"], path=path, section=section, index=index, field="old_keyword"))
        new_keyword = _normalize_text(_require_string(entry["new_keyword"], path=path, section=section, index=index, field="new_keyword"))
        _require_string(entry["reason"], path=path, section=section, index=index, field="reason")
        if status == "inactive":
            continue
        effective_update = (required_words, old_keyword, new_keyword)
        if effective_update in seen_effective_updates:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} duplicates active product substitution"
            )
        seen_effective_updates.add(effective_update)
        updates.append(effective_update)
    return tuple(updates)


def _load_secondary_ingredient_patterns(
    payload: dict[str, Any],
    *,
    path: Path,
    seen_ids: set[str],
    seen_effective_updates: set[tuple[str, str]],
) -> Dict[str, tuple[Set[str], Set[str]]]:
    section = "secondary_ingredient_patterns"
    raw_entries = payload.get(section, [])
    if not isinstance(raw_entries, list):
        raise RuntimeRuleOverlayError(f"{path}:{section} must be a list of tables")
    updates: Dict[str, tuple[Set[str], Set[str]]] = {}
    for index, entry in enumerate(raw_entries, start=1):
        if not isinstance(entry, dict):
            raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} must be a table")
        unknown_keys = sorted(set(entry) - _ALLOWED_SECONDARY_INGREDIENT_PATTERN_ENTRY_KEYS)
        if unknown_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} has unknown keys: {', '.join(unknown_keys)}"
            )
        missing_keys = sorted({"keyword", "blockers", "reason"} - set(entry))
        if missing_keys:
            raise RuntimeRuleOverlayError(
                f"{_path_label(path, section, index)} is missing keys: {', '.join(missing_keys)}"
            )
        status = _entry_status(entry, path=path, section=section, index=index)
        entry_id = entry.get("id")
        if entry_id is not None:
            normalized_id = _require_string(entry_id, path=path, section=section, index=index, field="id")
            if normalized_id in seen_ids:
                raise RuntimeRuleOverlayError(f"{_path_label(path, section, index)} has duplicate id: {normalized_id}")
            seen_ids.add(normalized_id)
        keyword = _normalize_text(_require_string(entry["keyword"], path=path, section=section, index=index, field="keyword"))
        blockers = {
            _normalize_text(item)
            for item in _require_string_list(
                entry["blockers"],
                path=path,
                section=section,
                index=index,
                field="blockers",
            )
        }
        exceptions = {
            _normalize_text(item)
            for item in _require_string_list(
                entry.get("exceptions", []),
                path=path,
                section=section,
                index=index,
                field="exceptions",
            )
        } if "exceptions" in entry else set()
        _require_string(entry["reason"], path=path, section=section, index=index, field="reason")
        if status == "inactive":
            continue
        target_blockers, target_exceptions = updates.setdefault(keyword, (set(), set()))
        for blocker in blockers:
            effective_update = (keyword, blocker)
            if effective_update in seen_effective_updates:
                raise RuntimeRuleOverlayError(
                    f"{_path_label(path, section, index)} duplicates active {keyword!r} blocker {blocker!r}"
                )
            seen_effective_updates.add(effective_update)
            target_blockers.add(blocker)
        target_exceptions.update(exceptions)
    return updates


def load_runtime_rule_overlays(path: Path = OVERLAY_PATH) -> RuntimeRuleOverlays:
    payload = _load_toml(path)
    known_sections = (
        set(_SECTION_VALUE_FIELDS)
        | set(_TERM_SET_SECTIONS)
        | set(_PAIR_SECTION_FIELDS)
        | set(_SET_UPDATE_SECTIONS)
        | set(_CONTEXT_SECTION_FIELDS)
        | {"compound_protection_updates"}
        | {"specialty_qualifiers", "qualifier_equivalents"}
        | {"product_name_substitutions", "secondary_ingredient_patterns"}
    )
    unknown_sections = sorted(set(payload) - known_sections)
    if unknown_sections:
        raise RuntimeRuleOverlayError(f"{path}: unknown sections: {', '.join(unknown_sections)}")

    seen_ids: set[str] = set()
    seen_effective_values: set[tuple[str, str, str]] = set()
    seen_effective_terms: set[tuple[str, str]] = set()
    seen_effective_pairs: set[tuple[str, str, str]] = set()
    seen_effective_updates: set[tuple[str, str, str, str]] = set()
    seen_effective_compound_updates: set[tuple[str, str]] = set()
    seen_effective_specialty_updates: set[tuple[str, str]] = set()
    seen_effective_equivalent_updates: set[tuple[str, str]] = set()
    seen_effective_substitutions: set[tuple[frozenset[str], str, str]] = set()
    seen_effective_secondary_patterns: set[tuple[str, str]] = set()
    specialty_updates, specialty_bidirectional_updates = _load_specialty_qualifier_updates(
        payload,
        path=path,
        seen_ids=seen_ids,
        seen_effective_updates=seen_effective_specialty_updates,
    )
    return RuntimeRuleOverlays(
        product_name_blockers=_merge_section(
            payload,
            "product_name_blockers",
            path=path,
            seen_ids=seen_ids,
            seen_effective_values=seen_effective_values,
        ),
        false_positive_blockers=_merge_section(
            payload,
            "false_positive_blockers",
            path=path,
            seen_ids=seen_ids,
            seen_effective_values=seen_effective_values,
        ),
        keyword_suppressed_by_context=_merge_section(
            payload,
            "keyword_suppressed_by_context",
            path=path,
            seen_ids=seen_ids,
            seen_effective_values=seen_effective_values,
        ),
        processed_product_rules=_merge_section(
            payload,
            "processed_product_rules",
            path=path,
            seen_ids=seen_ids,
            seen_effective_values=seen_effective_values,
        ),
        processed_rule_compound_exemptions=_merge_section(
            payload,
            "processed_rule_compound_exemptions",
            path=path,
            seen_ids=seen_ids,
            seen_effective_values=seen_effective_values,
        ),
        global_product_name_blockers=_load_term_set_section(
            payload,
            "global_product_name_blockers",
            path=path,
            seen_ids=seen_ids,
            seen_effective_terms=seen_effective_terms,
        ),
        strict_processed_rules=_load_term_set_section(
            payload,
            "strict_processed_rules",
            path=path,
            seen_ids=seen_ids,
            seen_effective_terms=seen_effective_terms,
        ),
        carrier_context_required=_load_term_set_section(
            payload,
            "carrier_context_required",
            path=path,
            seen_ids=seen_ids,
            seen_effective_terms=seen_effective_terms,
        ),
        context_required_words=_load_term_set_section(
            payload,
            "context_required_words",
            path=path,
            seen_ids=seen_ids,
            seen_effective_terms=seen_effective_terms,
        ),
        ingredient_requires_in_product=_load_term_set_section(
            payload,
            "ingredient_requires_in_product",
            path=path,
            seen_ids=seen_ids,
            seen_effective_terms=seen_effective_terms,
        ),
        space_normalizations=_load_pair_section(
            payload,
            "space_normalizations",
            path=path,
            seen_ids=seen_ids,
            seen_effective_pairs=seen_effective_pairs,
        ),
        keyword_set_updates=_load_set_update_section(
            payload,
            "keyword_set_updates",
            path=path,
            seen_ids=seen_ids,
            seen_effective_updates=seen_effective_updates,
        ),
        carrier_set_updates=_load_set_update_section(
            payload,
            "carrier_set_updates",
            path=path,
            seen_ids=seen_ids,
            seen_effective_updates=seen_effective_updates,
        ),
        cuisine_context=_load_context_section(
            payload,
            "cuisine_context",
            path=path,
            seen_ids=seen_ids,
            seen_effective_values=seen_effective_values,
        ),
        context_word_keyword_exemptions=_load_context_section(
            payload,
            "context_word_keyword_exemptions",
            path=path,
            seen_ids=seen_ids,
            seen_effective_values=seen_effective_values,
        ),
        compound_protection_updates=_load_compound_protection_updates(
            payload,
            path=path,
            seen_ids=seen_ids,
            seen_effective_updates=seen_effective_compound_updates,
        ),
        specialty_qualifier_updates=specialty_updates,
        specialty_bidirectional_updates=specialty_bidirectional_updates,
        qualifier_equivalent_updates=_load_qualifier_equivalent_updates(
            payload,
            path=path,
            seen_ids=seen_ids,
            seen_effective_updates=seen_effective_equivalent_updates,
        ),
        product_name_substitutions=_load_product_name_substitutions(
            payload,
            path=path,
            seen_ids=seen_ids,
            seen_effective_updates=seen_effective_substitutions,
        ),
        secondary_ingredient_patterns=_load_secondary_ingredient_patterns(
            payload,
            path=path,
            seen_ids=seen_ids,
            seen_effective_updates=seen_effective_secondary_patterns,
        ),
    )


_OVERLAYS = load_runtime_rule_overlays()

PRODUCT_NAME_BLOCKER_CLI_UPDATES = _OVERLAYS.product_name_blockers
FALSE_POSITIVE_BLOCKER_CLI_UPDATES = _OVERLAYS.false_positive_blockers
KEYWORD_SUPPRESSED_BY_CONTEXT_CLI_UPDATES = _OVERLAYS.keyword_suppressed_by_context
PROCESSED_PRODUCT_RULE_CLI_UPDATES = _OVERLAYS.processed_product_rules
PROCESSED_RULE_COMPOUND_EXEMPTION_CLI_UPDATES = _OVERLAYS.processed_rule_compound_exemptions
GLOBAL_PRODUCT_NAME_BLOCKER_CLI_UPDATES = _OVERLAYS.global_product_name_blockers
STRICT_PROCESSED_RULE_CLI_UPDATES = _OVERLAYS.strict_processed_rules
CARRIER_CONTEXT_REQUIRED_CLI_UPDATES = _OVERLAYS.carrier_context_required
CONTEXT_REQUIRED_WORD_CLI_UPDATES = _OVERLAYS.context_required_words
INGREDIENT_REQUIRES_IN_PRODUCT_CLI_UPDATES = _OVERLAYS.ingredient_requires_in_product
SPACE_NORMALIZATION_CLI_UPDATES = _OVERLAYS.space_normalizations
KEYWORD_SET_CLI_UPDATES = _OVERLAYS.keyword_set_updates
CARRIER_SET_CLI_UPDATES = _OVERLAYS.carrier_set_updates
CUISINE_CONTEXT_CLI_UPDATES = _OVERLAYS.cuisine_context
CONTEXT_WORD_KEYWORD_EXEMPTION_CLI_UPDATES = _OVERLAYS.context_word_keyword_exemptions
COMPOUND_PROTECTION_CLI_UPDATES = _OVERLAYS.compound_protection_updates
SPECIALTY_QUALIFIER_CLI_UPDATES = _OVERLAYS.specialty_qualifier_updates
SPECIALTY_BIDIRECTIONAL_CLI_UPDATES = _OVERLAYS.specialty_bidirectional_updates
QUALIFIER_EQUIVALENT_CLI_UPDATES = _OVERLAYS.qualifier_equivalent_updates
PRODUCT_NAME_SUBSTITUTION_CLI_UPDATES = _OVERLAYS.product_name_substitutions
SECONDARY_INGREDIENT_PATTERN_CLI_UPDATES = _OVERLAYS.secondary_ingredient_patterns
