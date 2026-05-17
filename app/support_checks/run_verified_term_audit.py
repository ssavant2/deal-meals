#!/usr/bin/env python3
"""Build the verified term audit ledger.

This is the verified-term initializer. It does not rebuild cache and does not
decide whether terms are semantically correct. It rebuilds a deterministic,
persistent dev-only working table that later verification waves can update as
variants are audited.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha1
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable

try:
    from sqlalchemy import text
except ModuleNotFoundError:
    def text(sql: str) -> str:
        return sql


APP_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = APP_DIR.parent
sys.path.insert(0, "/app" if os.path.exists("/app") else str(APP_DIR))

from languages.sv.ingredient_matching.ingredient_routing import _ROUTING_PARENT_TERMS  # noqa: E402
from languages.sv.ingredient_matching.keywords import OFFER_EXTRA_KEYWORDS  # noqa: E402
from languages.sv.ingredient_matching.match_bridges import MATCH_BRIDGES  # noqa: E402
from languages.sv.ingredient_matching.no_match_policies import NO_MATCH_POLICIES  # noqa: E402
from languages.sv.ingredient_matching.parent_maps import KEYWORD_EXTRA_PARENTS, PARENT_MATCH_ONLY  # noqa: E402
from languages.sv.ingredient_matching.synonyms import INGREDIENT_PARENTS, KEYWORD_SYNONYMS  # noqa: E402
from support_checks.prefix_schema import diagnostic_prefixes  # noqa: E402


DEFAULT_BATCH_SIZE = 60
IDENTITY_HASH_VERSION_V1 = "v1_source_ref"
IDENTITY_HASH_VERSION_V2 = "v2_stable_without_source_ref"
DEFAULT_IDENTITY_HASH_VERSION = IDENTITY_HASH_VERSION_V2
SUPPORTED_IDENTITY_HASH_VERSIONS = frozenset({
    IDENTITY_HASH_VERSION_V1,
    IDENTITY_HASH_VERSION_V2,
})
DEFAULT_REPORT_DIR = (
    Path(os.environ.get("DEAL_MEALS_SUPPORT_REPORT_ROOT", "/tmp/deal-meals-support-checks"))
    / "verified_term_audit"
)
RULE_INVENTORY_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json"
REGRESSION_CASES_FILE = APP_DIR / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json"
EXTRACTION_FILE = APP_DIR / "languages" / "sv" / "ingredient_matching" / "extraction.py"
TERM_INDEXES_FILE = APP_DIR / "languages" / "sv" / "ingredient_matching" / "term_indexes.py"
WORKING_TABLE = "tmp_verified_term_audit_variants"
KNOWN_DIAGNOSTIC_ADAPTER_PREFIXES = diagnostic_prefixes("adapter_ref")
MAPPING_SOURCE_TYPES = frozenset({
    "ingredient_parent",
    "keyword_synonym",
    "parent_match_only",
    "keyword_extra_parent",
    "offer_extra_keyword",
    "ingredient_routing_parent",
})


@dataclass(frozen=True)
class AuditVariant:
    source_order: int
    source_type: str
    source_file: str
    source_ref: str
    source_id: str
    variant_role: str
    variant_text: str
    canonical: str = ""
    expected_family: str = ""
    ingredient_text: str = ""
    product_text: str = ""
    product_category: str = ""
    product_brand: str = ""
    expected: int | None = None
    needs_product_text: bool = False
    notes: str = ""
    metadata: dict[str, Any] | None = None
    variant_id: str = ""
    batch_id: str = ""
    batch_index: int = 0
    row_index: int = 0

    def identity_payload_v1(self) -> dict[str, Any]:
        """Legacy hash payload; retained for one-cycle migration tooling."""
        payload = self.identity_payload_v2()
        return {
            **payload,
            "source_ref": self.source_ref,
        }

    def identity_payload_v2(self) -> dict[str, Any]:
        """Stable semantic identity. source_ref is provenance, not identity."""
        return {
            "source_type": self.source_type,
            "source_file": self.source_file,
            "source_id": self.source_id,
            "variant_role": self.variant_role,
            "variant_text": self.variant_text,
            "canonical": self.canonical,
            "expected_family": self.expected_family,
            "ingredient_text": self.ingredient_text,
            "product_text": self.product_text,
            "expected": self.expected,
        }

    def identity_payload(self, hash_version: str = DEFAULT_IDENTITY_HASH_VERSION) -> dict[str, Any]:
        if hash_version == IDENTITY_HASH_VERSION_V1:
            return self.identity_payload_v1()
        if hash_version == IDENTITY_HASH_VERSION_V2:
            return self.identity_payload_v2()
        raise ValueError(f"Unsupported verified-term identity hash version: {hash_version}")

    def identity_key(self, hash_version: str = DEFAULT_IDENTITY_HASH_VERSION) -> str:
        return json.dumps(
            self.identity_payload(hash_version),
            sort_keys=True,
            ensure_ascii=False,
        )

    def variant_id_for_hash_version(self, hash_version: str = DEFAULT_IDENTITY_HASH_VERSION) -> str:
        digest = sha1(
            self.identity_key(hash_version).encode("utf-8")
        ).hexdigest()
        return f"vterm-{digest[:16]}"

    def with_identity(
        self,
        *,
        row_index: int,
        batch_size: int,
        hash_version: str = DEFAULT_IDENTITY_HASH_VERSION,
    ) -> "AuditVariant":
        return AuditVariant(
            **{
                **asdict(self),
                "variant_id": self.variant_id_for_hash_version(hash_version),
                "batch_id": f"VT{((row_index - 1) // batch_size) + 1:03d}",
                "batch_index": ((row_index - 1) % batch_size) + 1,
                "row_index": row_index,
            }
        )


def _validate_hash_version(hash_version: str) -> str:
    if hash_version not in SUPPORTED_IDENTITY_HASH_VERSIONS:
        raise ValueError(
            f"Unsupported verified-term identity hash version {hash_version!r}; "
            f"expected one of {sorted(SUPPORTED_IDENTITY_HASH_VERSIONS)}"
        )
    return hash_version


def _repo_rel(path: Path) -> str:
    return str(path.relative_to(REPO_DIR))


def _json_default(value: Any) -> Any:
    if isinstance(value, (set, frozenset, tuple)):
        return sorted(value)
    return str(value)


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected list payload in {path}")
    return payload


def _literal_strings(node: ast.AST | None) -> list[str]:
    values: list[str] = []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        values.append(node.value)
    elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for child in node.elts:
            values.extend(_literal_strings(child))
    elif isinstance(node, ast.BinOp):
        values.extend(_literal_strings(node.left))
        values.extend(_literal_strings(node.right))
    elif isinstance(node, ast.Subscript):
        values.extend(_literal_strings(node.slice))
    return values


def _function_defs(path: Path, names: set[str]) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in names
    }


def _iter_return_literal_keyword_variants(
    *,
    path: Path,
    function_names: set[str],
    source_order: int,
    source_type: str,
    role_prefix: str,
) -> Iterable[AuditVariant]:
    rel_path = _repo_rel(path)
    outputs: dict[tuple[str, str], list[int]] = {}
    for function_name, function_node in _function_defs(path, function_names).items():
        for node in ast.walk(function_node):
            if not isinstance(node, ast.Return):
                continue
            for value in _literal_strings(node.value):
                value = value.strip()
                if value:
                    outputs.setdefault((function_name, value), []).append(node.lineno)

    for (function_name, value), lines in sorted(outputs.items()):
        first_line = min(lines)
        yield AuditVariant(
            source_order=source_order,
            source_type=source_type,
            source_file=rel_path,
            source_ref=f"{rel_path}:{function_name}:{first_line}",
            source_id=f"{function_name}:{value}",
            variant_role=f"{role_prefix}:{function_name}",
            variant_text=value,
            canonical=value,
            expected_family=value,
            expected=1,
            metadata={
                "function": function_name,
                "lines": sorted(set(lines)),
                "output": value,
            },
        )


def _iter_append_literal_keyword_variants(
    *,
    path: Path,
    function_name: str,
    target_name: str,
    source_order: int,
    source_type: str,
    variant_role: str,
) -> Iterable[AuditVariant]:
    rel_path = _repo_rel(path)
    function_node = _function_defs(path, {function_name}).get(function_name)
    if function_node is None:
        return

    outputs: dict[str, list[int]] = {}
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "append":
            continue
        if not isinstance(node.func.value, ast.Name) or node.func.value.id != target_name:
            continue
        for arg in node.args:
            for value in _literal_strings(arg):
                value = value.strip()
                if value:
                    outputs.setdefault(value, []).append(node.lineno)

    for value, lines in sorted(outputs.items()):
        first_line = min(lines)
        yield AuditVariant(
            source_order=source_order,
            source_type=source_type,
            source_file=rel_path,
            source_ref=f"{rel_path}:{function_name}:{first_line}",
            source_id=f"{function_name}:{value}",
            variant_role=variant_role,
            variant_text=value,
            canonical=value,
            expected_family=value,
            expected=1,
            metadata={
                "function": function_name,
                "lines": sorted(set(lines)),
                "output": value,
                "target": target_name,
            },
        )


def _source_ref(entry: dict[str, Any]) -> str:
    source_refs = entry.get("source_refs")
    if isinstance(source_refs, list) and source_refs:
        return str(source_refs[0])
    return str(entry.get("source_ref") or entry.get("policy_ref") or entry.get("id") or "")


def _expected_canonicals(case: dict[str, Any]) -> list[str]:
    canonicals = []
    for item in case.get("expected_matches") or []:
        if isinstance(item, dict) and item.get("canonical"):
            canonicals.append(str(item["canonical"]))
    allowed = case.get("allowed_additional_matches") or {}
    if isinstance(allowed, dict):
        for key in ("allowed_canonicals", "forbidden_canonicals"):
            canonicals.extend(str(value) for value in allowed.get(key, []) if value)
    return sorted(set(canonicals))


def _iter_rule_inventory_variants() -> Iterable[AuditVariant]:
    rel_path = _repo_rel(RULE_INVENTORY_FILE)
    for index, entry in enumerate(_load_json_list(RULE_INVENTORY_FILE), start=1):
        canonical = str(entry.get("canonical") or "")
        source_id = str(entry.get("id") or f"inventory-{index}")
        yield AuditVariant(
            source_order=10,
            source_type="matcher_rule_inventory",
            source_file=rel_path,
            source_ref=_source_ref(entry),
            source_id=source_id,
            variant_role=str(entry.get("kind") or "inventory_rule"),
            variant_text=canonical or source_id,
            canonical=canonical,
            expected_family=canonical,
            needs_product_text=True,
            notes=str(entry.get("notes") or ""),
            metadata={
                "status": entry.get("status"),
                "risk": entry.get("risk"),
                "policy_ref": entry.get("policy_ref"),
                "fixture_refs": entry.get("fixture_refs") or [],
                "adapter_ref": entry.get("adapter_ref"),
                "adapter_refs": entry.get("adapter_refs") or [],
                "source_refs": entry.get("source_refs") or [],
            },
        )


def _iter_regression_case_variants() -> Iterable[AuditVariant]:
    rel_path = _repo_rel(REGRESSION_CASES_FILE)
    for case in _load_json_list(REGRESSION_CASES_FILE):
        case_id = str(case["id"])
        offer = case.get("offer") or {}
        ingredients = [str(value) for value in case.get("ingredients") or []]
        expected = int(case["expected"])
        canonicals = _expected_canonicals(case)
        expected_family = ", ".join(canonicals)
        yield AuditVariant(
            source_order=20,
            source_type="matcher_regression_case",
            source_file=rel_path,
            source_ref=str(case.get("source_ref") or case.get("policy_ref") or case_id),
            source_id=case_id,
            variant_role="positive_regression" if expected else "negative_regression",
            variant_text=f"{case_id}: {offer.get('name', '')}",
            canonical=expected_family,
            expected_family=expected_family or str(case.get("policy_ref") or ""),
            ingredient_text=" | ".join(ingredients),
            product_text=str(offer.get("name") or ""),
            product_category=str(offer.get("category") or ""),
            product_brand=str(offer.get("brand") or ""),
            expected=expected,
            needs_product_text=False,
            notes=str(case.get("policy_ref") or ""),
            metadata={
                "recipe_name": case.get("recipe_name"),
                "policy_ref": case.get("policy_ref"),
                "expected_matches": case.get("expected_matches") or [],
                "allowed_additional_matches": case.get("allowed_additional_matches") or None,
            },
        )


def _iter_match_bridge_variants() -> Iterable[AuditVariant]:
    rel_path = "app/languages/sv/ingredient_matching/match_bridges.py"
    for bridge in MATCH_BRIDGES:
        metadata = {
            "rule_version": bridge.rule_version,
            "aliases": sorted(bridge.aliases),
            "fixture_refs": sorted(bridge.fixture_refs),
            "supersedes": sorted(bridge.supersedes),
            "ingredient_form_signals": sorted(bridge.ingredient_form_signals),
            "offer_form_signals": sorted(bridge.offer_form_signals),
            "required_offer_form_signals": sorted(bridge.required_offer_form_signals),
            "forbidden_offer_form_signals": sorted(bridge.forbidden_offer_form_signals),
        }
        for ingredient_pattern in bridge.ingredient_patterns:
            for offer_pattern in bridge.offer_patterns:
                yield AuditVariant(
                    source_order=30,
                    source_type="match_bridge",
                    source_file=rel_path,
                    source_ref=f"match_bridges:{bridge.id}",
                    source_id=bridge.id,
                    variant_role="bridge_positive",
                    variant_text=f"{ingredient_pattern} -> {offer_pattern}",
                    canonical=bridge.canonical,
                    expected_family=bridge.canonical,
                    ingredient_text=ingredient_pattern,
                    product_text=offer_pattern,
                    expected=1,
                    needs_product_text=True,
                    metadata=metadata,
                )
        for negative_pattern in bridge.negative_offer_patterns:
            yield AuditVariant(
                source_order=31,
                source_type="match_bridge",
                source_file=rel_path,
                source_ref=f"match_bridges:{bridge.id}",
                source_id=bridge.id,
                variant_role="bridge_negative_guard",
                variant_text=f"{bridge.canonical} ! {negative_pattern}",
                canonical=bridge.canonical,
                expected_family=negative_pattern,
                product_text=negative_pattern,
                expected=0,
                needs_product_text=True,
                metadata=metadata,
            )


def _iter_no_match_policy_variants() -> Iterable[AuditVariant]:
    rel_path = "app/languages/sv/ingredient_matching/no_match_policies.py"
    for policy in NO_MATCH_POLICIES:
        metadata = {
            "rule_version": policy.rule_version,
            "reason": policy.reason,
            "policy_ref": policy.policy_ref,
            "fixture_refs": sorted(policy.fixture_refs),
            "allowed_specifics": sorted(policy.allowed_specifics),
            "supersedes": sorted(policy.supersedes),
            "ingredient_patterns": list(policy.ingredient_patterns),
        }
        for keyword in sorted(policy.blocked_offer_keywords):
            yield AuditVariant(
                source_order=40,
                source_type="no_match_policy",
                source_file=rel_path,
                source_ref=f"no_match_policies:{policy.id}",
                source_id=policy.id,
                variant_role="negative_guard_keyword",
                variant_text=f"{policy.canonical} ! {keyword}",
                canonical=policy.canonical,
                expected_family=keyword,
                product_text=keyword,
                expected=0,
                needs_product_text=True,
                notes=policy.reason,
                metadata=metadata,
            )
        for pattern in policy.blocked_offer_patterns:
            yield AuditVariant(
                source_order=41,
                source_type="no_match_policy",
                source_file=rel_path,
                source_ref=f"no_match_policies:{policy.id}",
                source_id=policy.id,
                variant_role="negative_guard_pattern",
                variant_text=f"{policy.canonical} ! {pattern}",
                canonical=policy.canonical,
                expected_family=pattern,
                product_text=pattern,
                expected=0,
                needs_product_text=True,
                notes=policy.reason,
                metadata=metadata,
            )


def _as_targets(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set, frozenset)):
        return sorted(str(item) for item in value if item)
    if value:
        return [str(value)]
    return []


def _iter_mapping_variants(
    *,
    mapping: dict[str, Any],
    source_order: int,
    source_type: str,
    source_file: str,
    variant_role: str,
) -> Iterable[AuditVariant]:
    for source in sorted(mapping):
        for target in _as_targets(mapping[source]):
            yield AuditVariant(
                source_order=source_order,
                source_type=source_type,
                source_file=source_file,
                source_ref=f"{source_file}:{source}",
                source_id=str(source),
                variant_role=variant_role,
                variant_text=str(source),
                canonical=target,
                expected_family=target,
                expected=1,
                needs_product_text=True,
                metadata={"target": target},
            )


def _identity_collision_sample(variants: list[AuditVariant], *, hash_version: str) -> list[dict[str, Any]]:
    groups: dict[str, list[AuditVariant]] = {}
    for variant in variants:
        groups.setdefault(variant.identity_key(hash_version), []).append(variant)

    collisions: list[dict[str, Any]] = []
    for identity_key, grouped in groups.items():
        if len(grouped) <= 1:
            continue
        legacy_keys = {variant.identity_key(IDENTITY_HASH_VERSION_V1) for variant in grouped}
        # Exact duplicate source rows are already de-duplicated below. The
        # migration blocker is a v2 key shared by distinct legacy identities.
        if len(legacy_keys) <= 1:
            continue
        collisions.append({
            "identity_key": identity_key,
            "variants": [
                {
                    "source_type": variant.source_type,
                    "source_id": variant.source_id,
                    "source_ref": variant.source_ref,
                    "variant_role": variant.variant_role,
                    "variant_text": variant.variant_text,
                    "canonical": variant.canonical,
                    "expected": variant.expected,
                }
                for variant in grouped[:5]
            ],
            "count": len(grouped),
        })
    return collisions


def build_variants(
    batch_size: int,
    *,
    hash_version: str = DEFAULT_IDENTITY_HASH_VERSION,
) -> list[AuditVariant]:
    hash_version = _validate_hash_version(hash_version)
    variants: list[AuditVariant] = []
    variants.extend(_iter_rule_inventory_variants())
    variants.extend(_iter_regression_case_variants())
    variants.extend(_iter_match_bridge_variants())
    variants.extend(_iter_no_match_policy_variants())
    variants.extend(_iter_mapping_variants(
        mapping=INGREDIENT_PARENTS,
        source_order=50,
        source_type="ingredient_parent",
        source_file="app/languages/sv/ingredient_matching/synonyms.py",
        variant_role="ingredient_parent_mapping",
    ))
    variants.extend(_iter_mapping_variants(
        mapping=KEYWORD_SYNONYMS,
        source_order=51,
        source_type="keyword_synonym",
        source_file="app/languages/sv/ingredient_matching/synonyms.py",
        variant_role="keyword_synonym_mapping",
    ))
    variants.extend(_iter_mapping_variants(
        mapping=PARENT_MATCH_ONLY,
        source_order=52,
        source_type="parent_match_only",
        source_file="app/languages/sv/ingredient_matching/parent_maps.py",
        variant_role="parent_match_only_mapping",
    ))
    variants.extend(_iter_mapping_variants(
        mapping=KEYWORD_EXTRA_PARENTS,
        source_order=53,
        source_type="keyword_extra_parent",
        source_file="app/languages/sv/ingredient_matching/parent_maps.py",
        variant_role="keyword_extra_parent_mapping",
    ))
    variants.extend(_iter_mapping_variants(
        mapping=OFFER_EXTRA_KEYWORDS,
        source_order=54,
        source_type="offer_extra_keyword",
        source_file="app/languages/sv/ingredient_matching/keywords.py",
        variant_role="offer_extra_keyword_mapping",
    ))
    variants.extend(_iter_mapping_variants(
        mapping=_ROUTING_PARENT_TERMS,
        source_order=55,
        source_type="ingredient_routing_parent",
        source_file="app/languages/sv/ingredient_matching/ingredient_routing.py",
        variant_role="ingredient_routing_parent_mapping",
    ))
    variants.extend(_iter_return_literal_keyword_variants(
        path=EXTRACTION_FILE,
        function_names={"extract_keywords_from_product", "extract_keywords_from_ingredient"},
        source_order=90,
        source_type="extraction_helper",
        role_prefix="hardcoded_keyword_output",
    ))
    variants.extend(_iter_append_literal_keyword_variants(
        path=TERM_INDEXES_FILE,
        function_name="_recipe_routing_extra_aliases",
        target_name="aliases",
        source_order=91,
        source_type="recipe_routing_helper",
        variant_role="recipe_routing_extra_alias",
    ))

    variants = sorted(
        variants,
        key=lambda item: (
            item.source_order,
            item.source_type,
            item.source_file,
            item.source_id,
            item.variant_role,
            item.variant_text,
            item.product_text,
            item.expected if item.expected is not None else -1,
        ),
    )
    collisions = _identity_collision_sample(variants, hash_version=hash_version)
    if collisions:
        sample = json.dumps(collisions[:3], ensure_ascii=False, sort_keys=True)
        raise RuntimeError(
            f"Verified-term {hash_version} identity payload is not unique; "
            f"sample collisions: {sample}"
        )

    seen_identity_keys: set[str] = set()
    unique_variants: list[AuditVariant] = []
    for variant in variants:
        identity_key = variant.identity_key(hash_version)
        if identity_key in seen_identity_keys:
            continue
        seen_identity_keys.add(identity_key)
        unique_variants.append(variant)
    variants = unique_variants
    return [
        variant.with_identity(row_index=index, batch_size=batch_size, hash_version=hash_version)
        for index, variant in enumerate(variants, 1)
    ]


CREATE_TABLE_SQL = f"""
CREATE TABLE {WORKING_TABLE} (
    variant_id text PRIMARY KEY,
    batch_id text NOT NULL,
    batch_index integer NOT NULL,
    row_index integer NOT NULL,
    source_order integer NOT NULL,
    source_type text NOT NULL,
    source_file text NOT NULL,
    source_ref text NOT NULL,
    source_id text NOT NULL,
    variant_role text NOT NULL,
    variant_text text NOT NULL,
    canonical text,
    expected_family text,
    ingredient_text text,
    product_text text,
    product_category text,
    product_brand text,
    expected integer,
    status text NOT NULL DEFAULT 'pending',
    classification text,
    needs_product_text boolean NOT NULL DEFAULT false,
    notes text,
    metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)
"""


INSERT_SQL = text(f"""
INSERT INTO {WORKING_TABLE} (
    variant_id, batch_id, batch_index, row_index, source_order, source_type,
    source_file, source_ref, source_id, variant_role, variant_text, canonical,
    expected_family, ingredient_text, product_text, product_category,
    product_brand, expected, status, classification, needs_product_text, notes,
    metadata
) VALUES (
    :variant_id, :batch_id, :batch_index, :row_index, :source_order,
    :source_type, :source_file, :source_ref, :source_id, :variant_role,
    :variant_text, :canonical, :expected_family, :ingredient_text,
    :product_text, :product_category, :product_brand, :expected, 'pending',
    NULL, :needs_product_text, :notes, CAST(:metadata AS jsonb)
)
""")


LOAD_BATCH_SQL = text(f"""
SELECT
    variant_id,
    batch_id,
    batch_index,
    row_index,
    source_type,
    source_file,
    source_ref,
    source_id,
    variant_role,
    variant_text,
    canonical,
    expected_family,
    ingredient_text,
    product_text,
    product_category,
    product_brand,
    expected,
    needs_product_text,
    notes,
    metadata
FROM {WORKING_TABLE}
WHERE batch_id = :batch_id
ORDER BY batch_index
""")


UPDATE_AUDIT_SQL = text(f"""
UPDATE {WORKING_TABLE}
SET
    status = :status,
    classification = :classification,
    notes = COALESCE(:notes, notes),
    metadata = metadata || CAST(:audit_metadata AS jsonb),
    updated_at = now()
WHERE variant_id = :variant_id
""")


def _variant_row(variant: AuditVariant) -> dict[str, Any]:
    return {
        "variant_id": variant.variant_id,
        "batch_id": variant.batch_id,
        "batch_index": variant.batch_index,
        "row_index": variant.row_index,
        "source_order": variant.source_order,
        "source_type": variant.source_type,
        "source_file": variant.source_file,
        "source_ref": variant.source_ref,
        "source_id": variant.source_id,
        "variant_role": variant.variant_role,
        "variant_text": variant.variant_text,
        "canonical": variant.canonical or None,
        "expected_family": variant.expected_family or None,
        "ingredient_text": variant.ingredient_text or None,
        "product_text": variant.product_text or None,
        "product_category": variant.product_category or None,
        "product_brand": variant.product_brand or None,
        "expected": variant.expected,
        "needs_product_text": variant.needs_product_text,
        "notes": variant.notes or None,
        "metadata": json.dumps(variant.metadata or {}, ensure_ascii=False, sort_keys=True, default=_json_default),
    }


def ensure_working_table(db: Any) -> None:
    exists = db.execute(text("SELECT to_regclass(:table_name)"), {"table_name": WORKING_TABLE}).scalar()
    if not exists:
        raise RuntimeError(
            f"{WORKING_TABLE} does not exist. Create the dev-only table once "
            "with an admin DB user before running --rebuild-table:\n"
            f"{CREATE_TABLE_SQL.strip()}"
        )


def rebuild_working_table(variants: list[AuditVariant]) -> None:
    from database import get_db_session

    with get_db_session() as db:
        ensure_working_table(db)
        db.execute(text(f"TRUNCATE TABLE {WORKING_TABLE}"))
        for index in range(0, len(variants), 500):
            db.execute(INSERT_SQL, [_variant_row(variant) for variant in variants[index:index + 500]])
        db.commit()


def _fixture_ids() -> set[str]:
    return {str(case["id"]) for case in _load_json_list(REGRESSION_CASES_FILE)}


def _fixture_by_id() -> dict[str, dict[str, Any]]:
    return {str(case["id"]): case for case in _load_json_list(REGRESSION_CASES_FILE)}


def _valid_adapter_refs() -> set[str]:
    return {
        *(f"match_bridges:{bridge.id}" for bridge in MATCH_BRIDGES),
        *(f"no_match_policies:{policy.id}" for policy in NO_MATCH_POLICIES),
    }


def _classify_static_variant(
    row: dict[str, Any],
    *,
    fixture_ids: set[str],
    fixture_by_id: dict[str, dict[str, Any]],
    valid_adapter_refs: set[str],
) -> dict[str, Any]:
    metadata = row.get("metadata") or {}
    problems: list[str] = []
    checks: list[str] = []
    source_type = str(row.get("source_type") or "")

    if source_type == "matcher_rule_inventory":
        fixture_refs = [str(ref) for ref in metadata.get("fixture_refs") or [] if ref]
        checks.append("inventory_row_present")
        if fixture_refs:
            checks.append("fixture_refs_present")
            unknown_fixture_refs = sorted(set(fixture_refs) - fixture_ids)
            if unknown_fixture_refs:
                problems.append("unknown_fixture_refs:" + ",".join(unknown_fixture_refs[:5]))
            else:
                checks.append("fixture_refs_resolve")
        else:
            problems.append("missing_fixture_refs")

        inventory_status = str(metadata.get("status") or "")
        if inventory_status == "wrapped_adapter":
            adapter_refs = []
            adapter_ref = metadata.get("adapter_ref")
            if adapter_ref:
                adapter_refs.append(str(adapter_ref))
            adapter_refs.extend(str(ref) for ref in metadata.get("adapter_refs") or [] if ref)
            if not adapter_refs:
                problems.append("missing_adapter_ref")
            else:
                checks.append("adapter_refs_present")
                unknown_adapter_refs = sorted(
                    ref
                    for ref in set(adapter_refs) - valid_adapter_refs
                    if not any(ref.startswith(prefix) for prefix in KNOWN_DIAGNOSTIC_ADAPTER_PREFIXES)
                )
                if unknown_adapter_refs:
                    problems.append("unknown_adapter_refs:" + ",".join(unknown_adapter_refs[:5]))
                else:
                    checks.append("adapter_refs_resolve")
    elif source_type == "matcher_regression_case":
        from support_checks.matcher_layer_diagnostics import diagnose_case
        from support_checks.run_matcher_layer_fixture_cases import (
            _diagnostic_case_from_fixture,
            evaluate_match_expectation,
            materialized_match_signature,
        )

        checks.append("regression_case_present")
        payload = fixture_by_id.get(str(row.get("source_id") or ""))
        diagnostic_summary: dict[str, Any] | None = None
        if payload is None:
            problems.append("missing_regression_payload")
        else:
            diagnostic = diagnose_case(
                _diagnostic_case_from_fixture(payload),
                include_cache_freshness=False,
            )
            expected_diagnosis = str(payload.get("expected_diagnosis") or "pass")
            match_expectation = evaluate_match_expectation(
                payload,
                materialized_match_signature(diagnostic),
            )
            diagnostic_passed = (
                diagnostic["actual"] == payload["expected"]
                and diagnostic["diagnosis_class"] == expected_diagnosis
                and match_expectation["passed"]
            )
            diagnostic_summary = {
                "actual": diagnostic["actual"],
                "expected": payload["expected"],
                "diagnosis_class": diagnostic["diagnosis_class"],
                "expected_diagnosis": expected_diagnosis,
                "match_expectation": match_expectation["reason"],
                "paired_route_terms": diagnostic.get("candidate_routing", {}).get("paired_route_terms", []),
                "fast_match_keyword": diagnostic.get("fast_match", {}).get("matched_keyword"),
                "backend_accepted": diagnostic.get("backend_validation", {}).get("accepted"),
                "materialized": diagnostic.get("materialization", {}).get("matched"),
            }
            checks.append("synthetic_diagnostic_run")
            if diagnostic_passed:
                checks.append("synthetic_diagnostic_passed")
            else:
                problems.append(f"synthetic_diagnostic_failed:{diagnostic['diagnosis_class']}")

        if row.get("ingredient_text"):
            checks.append("ingredient_text_present")
        else:
            problems.append("missing_ingredient_text")
        if row.get("product_text"):
            checks.append("product_text_present")
        else:
            problems.append("missing_product_text")
        if row.get("expected") not in (0, 1):
            problems.append("invalid_expected")
        else:
            checks.append("expected_flag_valid")
        if not problems and diagnostic_summary:
            return {
                "variant_id": row["variant_id"],
                "status": "audited",
                "classification": "synthetic_verified",
                "checks": checks,
                "problems": problems,
                "notes": "B synthetic regression diagnostic passed.",
                "diagnostic": diagnostic_summary,
            }
    elif source_type == "match_bridge":
        fixture_refs = [str(ref) for ref in metadata.get("fixture_refs") or [] if ref]
        checks.append("match_bridge_present")
        if not fixture_refs:
            problems.append("missing_fixture_refs")
        elif sorted(set(fixture_refs) - fixture_ids):
            problems.append("unknown_fixture_refs")
        else:
            checks.append("fixture_refs_resolve")
        if row.get("expected") not in (0, 1):
            problems.append("invalid_expected")
    elif source_type == "no_match_policy":
        fixture_refs = [str(ref) for ref in metadata.get("fixture_refs") or [] if ref]
        checks.append("no_match_policy_present")
        if not fixture_refs:
            problems.append("missing_fixture_refs")
        elif sorted(set(fixture_refs) - fixture_ids):
            problems.append("unknown_fixture_refs")
        else:
            checks.append("fixture_refs_resolve")
        if row.get("expected") != 0:
            problems.append("invalid_negative_expected")
    else:
        checks.append("mapping_source_present")
        if row.get("variant_text") and row.get("canonical"):
            checks.append("mapping_source_and_target_present")
        else:
            problems.append("missing_mapping_side")
        if (
            source_type in MAPPING_SOURCE_TYPES
            and not problems
            and row.get("needs_product_text")
            and not row.get("product_text")
        ):
            return {
                "variant_id": row["variant_id"],
                "status": "audited",
                "classification": "no_product_text",
                "checks": checks,
                "problems": problems,
                "notes": "Static mapping is coherent, but no historical/live product text is attached.",
                "diagnostic": None,
            }

    classification = "needs_fix" if problems else "static_verified"
    status = "needs_fix" if problems else "audited"
    return {
        "variant_id": row["variant_id"],
        "status": status,
        "classification": classification,
        "checks": checks,
        "problems": problems,
        "notes": "; ".join(problems) if problems else "B static contract checks passed.",
        "diagnostic": None,
    }


def audit_batch(batch_id: str, *, apply: bool, report_dir: Path) -> dict[str, Any]:
    from database import get_db_session

    fixture_ids = _fixture_ids()
    fixture_payloads_by_id = _fixture_by_id()
    valid_adapter_refs = _valid_adapter_refs()
    with get_db_session() as db:
        exists = db.execute(text("SELECT to_regclass(:table_name)"), {"table_name": WORKING_TABLE}).scalar()
        if not exists:
            raise RuntimeError(f"{WORKING_TABLE} does not exist")
        rows = [dict(row) for row in db.execute(LOAD_BATCH_SQL, {"batch_id": batch_id}).mappings()]
        if not rows:
            raise RuntimeError(f"No rows found for batch {batch_id!r}")

        findings = [
            _classify_static_variant(
                row,
                fixture_ids=fixture_ids,
                fixture_by_id=fixture_payloads_by_id,
                valid_adapter_refs=valid_adapter_refs,
            )
            for row in rows
        ]
        if apply:
            for finding in findings:
                db.execute(
                    UPDATE_AUDIT_SQL,
                    {
                        "variant_id": finding["variant_id"],
                        "status": finding["status"],
                        "classification": finding["classification"],
                        "notes": finding["notes"],
                        "audit_metadata": json.dumps(
                            {
                                "b_static_audit": {
                                    "batch_id": batch_id,
                                    "checks": finding["checks"],
                                    "problems": finding["problems"],
                                    "diagnostic": finding.get("diagnostic"),
                                    "audited_at": datetime.now(timezone.utc).isoformat(),
                                }
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    },
                )
            db.commit()

    source_counts = Counter(str(row["source_type"]) for row in rows)
    classification_counts = Counter(str(finding["classification"]) for finding in findings)
    status_counts = Counter(str(finding["status"]) for finding in findings)
    problem_counts = Counter(problem.split(":", maxsplit=1)[0] for finding in findings for problem in finding["problems"])
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batch_id": batch_id,
        "working_table": WORKING_TABLE,
        "applied": apply,
        "variant_count": len(rows),
        "source_counts": dict(sorted(source_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "classification_counts": dict(sorted(classification_counts.items())),
        "problem_counts": dict(sorted(problem_counts.items())),
        "findings": findings,
    }
    write_batch_audit_report(report, report_dir)
    return report


def write_batch_audit_report(report: dict[str, Any], report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    batch_id = str(report["batch_id"]).lower()
    json_path = report_dir / f"{batch_id}_static_audit.json"
    md_path = report_dir / f"{batch_id}_static_audit.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )

    problem_lines = "\n".join(
        f"- `{problem}`: {count}"
        for problem, count in report["problem_counts"].items()
    ) or "- none"
    source_lines = "\n".join(
        f"- `{source}`: {count}"
        for source, count in report["source_counts"].items()
    )
    classification_lines = "\n".join(
        f"- `{classification}`: {count}"
        for classification, count in report["classification_counts"].items()
    )
    md_path.write_text(
        "\n".join([
            f"# Verified Term Static Audit {report['batch_id']}",
            "",
            f"Generated: {report['generated_at']}",
            f"Applied to table: {report['applied']}",
            "",
            "## Summary",
            "",
            f"- variants: {report['variant_count']}",
            "",
            "## Sources",
            "",
            source_lines,
            "",
            "## Classifications",
            "",
            classification_lines,
            "",
            "## Problems",
            "",
            problem_lines,
            "",
        ]),
        encoding="utf-8",
    )
    return json_path, md_path


def summarize_variants(variants: list[AuditVariant], *, batch_size: int) -> dict[str, Any]:
    source_counts = Counter(variant.source_type for variant in variants)
    role_counts = Counter(variant.variant_role for variant in variants)
    batch_counts = Counter(variant.batch_id for variant in variants)
    product_text_count = sum(1 for variant in variants if variant.product_text)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "working_table": WORKING_TABLE,
        "variant_count": len(variants),
        "batch_count": len(batch_counts),
        "normal_batch_size": batch_size,
        "variants_with_product_text": product_text_count,
        "variants_missing_product_text": len(variants) - product_text_count,
        "source_counts": dict(sorted(source_counts.items())),
        "role_counts": dict(sorted(role_counts.items())),
        "batch_counts": dict(sorted(batch_counts.items())),
        "first_batch_id": variants[0].batch_id if variants else None,
        "last_batch_id": variants[-1].batch_id if variants else None,
    }


def write_reports(variants: list[AuditVariant], report_dir: Path, *, batch_size: int) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_variants(variants, batch_size=batch_size)
    json_path = report_dir / "term_pipeline_audit.json"
    md_path = report_dir / "term_pipeline_audit.md"

    json_payload = {
        "summary": summary,
        "variants": [asdict(variant) for variant in variants],
    }
    json_path.write_text(
        json.dumps(json_payload, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )

    source_lines = "\n".join(
        f"- `{source}`: {count}"
        for source, count in summary["source_counts"].items()
    )
    batch_lines = "\n".join(
        f"- `{batch}`: {count}"
        for batch, count in list(summary["batch_counts"].items())[:10]
    )
    if summary["batch_count"] > 10:
        batch_lines += f"\n- ... {summary['batch_count'] - 10} more batches"

    md_path.write_text(
        "\n".join([
            "# Verified Term Audit",
            "",
            f"Generated: {summary['generated_at']}",
            "",
            "## Summary",
            "",
            f"- working table: `{WORKING_TABLE}`",
            f"- variants: {summary['variant_count']}",
            f"- batches: {summary['batch_count']} at {batch_size} variants per normal batch",
            f"- variants with product text: {summary['variants_with_product_text']}",
            f"- variants missing product text: {summary['variants_missing_product_text']}",
            "",
            "## Sources",
            "",
            source_lines,
            "",
            "## First Batches",
            "",
            batch_lines,
            "",
            "## Notes",
            "",
            "- Initialization only creates the ledger; all variant statuses start as `pending`.",
            "- This report is generated/local and should not be committed unless explicitly promoted.",
            "- Drop the working table after the frozen verified-term baseline is complete.",
            "",
        ]),
        encoding="utf-8",
    )
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument(
        "--rebuild-table",
        action="store_true",
        help="Truncate and refill the existing dev-only working table.",
    )
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--audit-batch", help="Run static contract checks for one generated batch id, e.g. VT001.")
    parser.add_argument("--apply-audit", action="store_true", help="Persist audit status/classification to the table.")
    parser.add_argument(
        "--use-stable-hash-v2",
        action="store_true",
        help="Use stable v2 variant ids that ignore source_ref provenance text. This is the default.",
    )
    parser.add_argument(
        "--legacy-hash-v1",
        action="store_true",
        help="Debug-only: generate legacy variant ids whose hash input includes source_ref.",
    )
    args = parser.parse_args()

    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")
    if args.use_stable_hash_v2 and args.legacy_hash_v1:
        raise ValueError("--use-stable-hash-v2 and --legacy-hash-v1 are mutually exclusive")
    hash_version = IDENTITY_HASH_VERSION_V1 if args.legacy_hash_v1 else DEFAULT_IDENTITY_HASH_VERSION

    if args.audit_batch:
        report = audit_batch(args.audit_batch, apply=args.apply_audit, report_dir=args.report_dir)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default))
        return 0

    variants = build_variants(args.batch_size, hash_version=hash_version)
    summary = summarize_variants(variants, batch_size=args.batch_size)

    if args.rebuild_table:
        rebuild_working_table(variants)

    report_paths: tuple[Path, Path] | None = None
    if args.write_report:
        report_paths = write_reports(variants, args.report_dir, batch_size=args.batch_size)

    print(json.dumps({
        **summary,
        "identity_hash_version": hash_version,
        "table_rebuilt": bool(args.rebuild_table),
        "reports": [str(path) for path in report_paths] if report_paths else [],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
