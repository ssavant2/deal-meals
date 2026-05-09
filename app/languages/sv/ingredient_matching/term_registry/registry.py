"""Load authored Swedish registry entries from TOML files."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import tomllib

from languages.term_registry.models import RegistryEntry, RegistryExample


REGISTRY_DIR = Path(__file__).resolve().parent
ENTRIES_DIR = REGISTRY_DIR / "entries"


def _tuple_str(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    raise ValueError(f"Expected string/list value, got {type(value).__name__}")


def _examples(value: Any) -> tuple[RegistryExample, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"Expected list of examples, got {type(value).__name__}")
    examples: list[RegistryExample] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Expected example tables to be dictionaries")
        examples.append(RegistryExample(
            ingredient=str(item.get("ingredient", "")),
            offer_name=str(item.get("offer_name", "")),
            offer_category=str(item.get("offer_category", "")),
            offer_brand=str(item.get("offer_brand", "")),
            expected=item.get("expected"),
        ))
    return tuple(examples)


def _entry_from_payload(payload: dict[str, Any], *, path: Path) -> RegistryEntry:
    language_payload = dict(payload.get("language_payload") or {})
    if "coverage" in payload:
        language_payload["coverage"] = payload["coverage"]
    if "legacy_coverage" in payload:
        language_payload["legacy_coverage"] = payload["legacy_coverage"]
    try:
        return RegistryEntry(
            entry_id=str(payload["entry_id"]),
            language=str(payload.get("language", "sv")),
            market=str(payload.get("market", "SE")),
            canonical=str(payload["canonical"]),
            status=str(payload.get("status", "active")),
            variants=_tuple_str(payload.get("variants")),
            ingredient_terms=_tuple_str(payload.get("ingredient_terms")),
            offer_terms=_tuple_str(payload.get("offer_terms")),
            route_terms=_tuple_str(payload.get("route_terms")),
            final_match_terms=_tuple_str(payload.get("final_match_terms")),
            negative_guards=_tuple_str(payload.get("negative_guards")),
            source_refs=_tuple_str(payload.get("source_refs")),
            layer_policy=_tuple_str(payload.get("layer_policy")) or ("normal",),
            positive_examples=_examples(payload.get("positive_examples")),
            negative_examples=_examples(payload.get("negative_examples")),
            notes=str(payload.get("notes", "")),
            language_payload=language_payload,
        )
    except KeyError as exc:
        raise ValueError(f"{path}: missing required registry field {exc.args[0]!r}") from exc


def load_registry_entries(entries_dir: Path = ENTRIES_DIR) -> list[RegistryEntry]:
    entries: list[RegistryEntry] = []
    if not entries_dir.exists():
        return entries
    for path in sorted(entries_dir.glob("*.toml")):
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        if "entries" in payload:
            raw_entries = payload["entries"]
            if not isinstance(raw_entries, list):
                raise ValueError(f"{path}: entries must be an array of tables")
            for raw_entry in raw_entries:
                if not isinstance(raw_entry, dict):
                    raise ValueError(f"{path}: entry payload must be a table")
                entries.append(_entry_from_payload(raw_entry, path=path))
        else:
            entries.append(_entry_from_payload(payload, path=path))
    return entries
