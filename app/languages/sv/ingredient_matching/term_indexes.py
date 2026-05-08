"""Persistent term indexes for candidate routing."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
import json
import re
import time
from typing import Any

from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError

try:
    from database import engine, get_db_session
    from models import (
        CompiledRecipeOfferCandidate,
        CompiledOfferTermIndex,
        CompiledRecipeTermIndex,
        FoundRecipe,
        Offer,
    )
except ModuleNotFoundError:
    from app.database import engine, get_db_session
    from app.models import (
        CompiledRecipeOfferCandidate,
        CompiledOfferTermIndex,
        CompiledRecipeTermIndex,
        FoundRecipe,
        Offer,
    )

from ..normalization import fix_swedish_chars
from .compiled_offers import load_compiled_offer_runtime_cache
from .offer_identity import build_offer_identity_key
from .recipe_identity import build_recipe_identity_key
from .compiled_recipes import ensure_compiled_recipe_match_table, load_compiled_recipe_payload_cache
from .normalization import _SPACE_NORMALIZATIONS, _apply_space_normalizations
from .parent_maps import PARENT_MATCH_ONLY
from .recipe_text import expand_grouped_ingredient_text, rewrite_buljong_eller_fond
from .synonyms import INGREDIENT_PARENTS
from .versioning import MATCHER_VERSION, OFFER_COMPILER_VERSION, RECIPE_COMPILER_VERSION
from .compound_text import _WORD_PATTERN

_COMPILED_OFFER_TERM_REFRESH_LOCK = 82003
_COMPILED_RECIPE_TERM_REFRESH_LOCK = 82004
_COMPILED_RECIPE_OFFER_CANDIDATE_REFRESH_LOCK = 82005
_RECIPE_TERM_COPY_BATCH_SIZE = 5000
_RECIPE_TERM_RECIPE_BATCH_SIZE = 500
_RECIPE_OFFER_CANDIDATE_RECIPE_BATCH_SIZE = 500
_RECIPE_OFFER_CANDIDATE_WORK_MEM = "128MB"
_RECIPE_TERM_COPY_COLUMNS = (
    "found_recipe_id, recipe_identity_key, matcher_version, "
    "recipe_compiler_version, term_manifest_hash, term, term_type, indexed_at"
)
_RECIPE_TERM_STREAM_TABLE = "tmp_compiled_recipe_term_index_refresh"
_RECIPE_OFFER_CANDIDATE_STREAM_TABLE = "tmp_compiled_recipe_offer_candidates_refresh"
_TERM_TYPE_PRIORITY = {
    "keyword": 0,
    "parent_keyword": 1,
    "name_word": 2,
}

_NAME_WORD_ROUTE_STOPWORDS = frozenset({
    # Candidate routing should use ingredient identities, not pack/state/brand
    # descriptors. Specific keywords such as flingsalt/havssalt/mineralvatten
    # still route through the keyword path.
    "burk",
    "flaska",
    "förp",
    "forp",
    "förpackning",
    "forpackning",
    "pack",
    "port",
    "portion",
    "portions",
    "stor",
    "stora",
    "liten",
    "lilla",
    "färsk",
    "farsk",
    "färska",
    "farska",
    "fryst",
    "frysta",
    "frusen",
    "frusna",
    "torkad",
    "torkade",
    "skivad",
    "skivade",
    "riven",
    "rivet",
    "rivna",
    "malen",
    "malet",
    "flytande",
    "hackad",
    "hackade",
    "extra",
    "naturell",
    "naturella",
    "original",
    "classic",
    "classico",
    "premium",
    "från",
    "fran",
    "till",
    "utan",
    "salt",
    "vatten",
    "läsk",
    "lask",
    "chokladkaka",
    "zeta",
    "garant",
})


def _format_progress_duration(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def _progress_bar(completed: int, total: int, *, width: int = 20) -> str:
    if total <= 0:
        return "-" * width
    filled = min(width, max(0, int((completed / total) * width)))
    return "#" * filled + "-" * (width - filled)


def _log_recipe_term_index_progress(
    *,
    completed: int,
    total: int,
    row_count: int,
    started_at: float,
    state: dict[str, Any],
    force: bool = False,
) -> None:
    if total <= 0:
        return

    now = time.perf_counter()
    completed = min(max(0, completed), total)
    percent = int((completed / total) * 100)
    bucket = percent // 10
    last_bucket = state.get("last_bucket")
    last_logged_at = state.get("last_logged_at", 0)
    if not force and last_bucket == bucket and now - last_logged_at < 30:
        return

    elapsed = now - started_at
    rate = completed / elapsed if completed and elapsed > 0 else 0
    eta = ((total - completed) / rate) if rate else None

    state["last_bucket"] = bucket
    state["last_logged_at"] = now
    logger.info(
        "CACHE_REBUILD_PROGRESS "
        "run=term_index "
        "phase=recipe_term_index "
        f"[{_progress_bar(completed, total)}] "
        f"{percent:3d}% "
        f"recipes={completed}/{total} "
        f"rows={row_count} "
        f"elapsed={_format_progress_duration(elapsed)} "
        f"eta={_format_progress_duration(eta)}"
    )


def _log_recipe_offer_candidate_progress(
    *,
    completed: int,
    total: int,
    row_count: int,
    started_at: float,
    state: dict[str, Any],
    force: bool = False,
) -> None:
    if total <= 0:
        return

    now = time.perf_counter()
    completed = min(max(0, completed), total)
    percent = int((completed / total) * 100)
    bucket = percent // 10
    last_bucket = state.get("last_bucket")
    last_logged_at = state.get("last_logged_at", 0)
    if not force and last_bucket == bucket and now - last_logged_at < 30:
        return

    elapsed = now - started_at
    rate = completed / elapsed if completed and elapsed > 0 else 0
    eta = ((total - completed) / rate) if rate else None

    state["last_bucket"] = bucket
    state["last_logged_at"] = now
    logger.info(
        "CACHE_REBUILD_PROGRESS "
        "run=candidate_index "
        "phase=recipe_offer_candidates "
        f"[{_progress_bar(completed, total)}] "
        f"{percent:3d}% "
        f"recipes={completed}/{total} "
        f"rows={row_count} "
        f"elapsed={_format_progress_duration(elapsed)} "
        f"eta={_format_progress_duration(eta)}"
    )


_HALFTEN_TILL_RE = re.compile(r'hälften till \w+')

_WHOLE_KYCKLING_BLOCKERS = (
    "filé",
    "file",
    "innerfil",
    "lårfil",
    "larfil",
    "bröst",
    "brost",
    "ving",
    "klubba",
    "ben",
    "strimlad",
)


def _stable_json_hash(payload: Any) -> str:
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def ensure_compiled_offer_term_index_table() -> None:
    with get_db_session() as db:
        exists = db.execute(text(
            "SELECT to_regclass('public.compiled_offer_term_index')"
        )).scalar()
    if not exists:
        raise RuntimeError(
            "compiled_offer_term_index table is missing. Apply the schema change "
            "from database/init.sql before running candidate-routing tools."
        )


def ensure_compiled_recipe_term_index_table() -> None:
    with get_db_session() as db:
        exists = db.execute(text(
            "SELECT to_regclass('public.compiled_recipe_term_index')"
        )).scalar()
    if not exists:
        raise RuntimeError(
            "compiled_recipe_term_index table is missing. Apply the schema change "
            "from database/init.sql before running candidate-routing tools."
        )


def ensure_compiled_recipe_offer_candidates_table() -> None:
    with get_db_session() as db:
        exists = db.execute(text(
            "SELECT to_regclass('public.compiled_recipe_offer_candidates')"
        )).scalar()
    if not exists:
        raise RuntimeError(
            "compiled_recipe_offer_candidates table is missing. Apply the schema "
            "change from database/init.sql or run startup migrations before "
            "database-backed candidate scoring."
        )


def _acquire_refresh_lock(db, lock_key: int) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": lock_key},
    )


def _dedupe_recipe_ids(*id_lists: list[str] | None) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for id_list in id_lists:
        for value in id_list or []:
            if value is None:
                continue
            str_value = str(value)
            if str_value in seen:
                continue
            ids.append(str_value)
            seen.add(str_value)
    return ids


def _dedupe_offer_identity_keys(*key_lists: list[str] | None) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for key_list in key_lists:
        for value in key_list or []:
            if value is None:
                continue
            str_value = str(value)
            if str_value in seen:
                continue
            keys.append(str_value)
            seen.add(str_value)
    return keys


def _candidate_offer_scope_hash(offer_identity_keys: list[str] | set[str] | tuple[str, ...]) -> str:
    """Return a stable metadata hash for a complete candidate offer scope."""
    ordered_keys = sorted({str(key) for key in offer_identity_keys if key is not None and str(key)})
    payload = json.dumps(ordered_keys, ensure_ascii=False, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _coerce_metadata_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _load_cache_metadata_last_operation(cursor, cache_name: str) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT last_operation
        FROM cache_metadata
        WHERE cache_name = %s
        """,
        (cache_name,),
    )
    row = cursor.fetchone()
    return _coerce_metadata_dict(row[0] if row else {})


def _recipe_term_index_metadata_is_complete(
    metadata: dict[str, Any],
    *,
    active_recipe_count: int,
    term_manifest_hash: str | None,
) -> bool:
    if not metadata:
        return False
    if not bool(metadata.get("complete")):
        return False
    expected = {
        "matcher_version": MATCHER_VERSION,
        "recipe_compiler_version": RECIPE_COMPILER_VERSION,
    }
    if term_manifest_hash:
        expected["term_manifest_hash"] = term_manifest_hash
    for key, value in expected.items():
        if metadata.get(key) != value:
            return False
    try:
        metadata_active_count = int(metadata.get("active_recipe_count") or -1)
        metadata_indexed_count = int(metadata.get("indexed_recipes") or 0)
    except (TypeError, ValueError):
        return False
    return (
        metadata_active_count == active_recipe_count
        and metadata_indexed_count >= active_recipe_count
    )


def _validate_full_candidate_recipe_scope(
    *,
    indexed_recipe_count: int,
    active_recipe_count: int,
    recipe_term_metadata: dict[str, Any] | None = None,
    term_manifest_hash: str | None = None,
) -> None:
    """Refuse full candidate refresh from a scoped/incomplete recipe term index."""
    if _recipe_term_index_metadata_is_complete(
        recipe_term_metadata or {},
        active_recipe_count=active_recipe_count,
        term_manifest_hash=term_manifest_hash,
    ):
        return
    if indexed_recipe_count < active_recipe_count:
        raise RuntimeError(
            "compiled_recipe_term_index is incomplete for current active "
            f"recipe scope: indexed_recipes={indexed_recipe_count}, "
            f"active_recipes={active_recipe_count}"
        )


def _replace_compiled_term_rows(db, *, table_name: str, model, rows: list[dict[str, Any]], lock_key: int) -> str:
    _acquire_refresh_lock(db, lock_key)
    replace_mode = "truncate"
    try:
        db.execute(text(f"TRUNCATE {table_name}"))
    except ProgrammingError as exc:
        if getattr(exc.orig, "pgcode", None) != "42501":
            raise
        db.rollback()
        replace_mode = "delete_fallback_no_truncate_privilege"
        _acquire_refresh_lock(db, lock_key)
        db.execute(model.__table__.delete())

    if rows:
        db.bulk_insert_mappings(model, rows)
    db.commit()
    return replace_mode


def _copy_recipe_term_rows(cursor, rows: list[tuple[Any, ...]], *, table_name: str) -> None:
    copy_sql = (
        f"COPY {table_name} ({_RECIPE_TERM_COPY_COLUMNS}) "
        "FROM STDIN WITH (FORMAT text)"
    )

    for i in range(0, len(rows), _RECIPE_TERM_COPY_BATCH_SIZE):
        batch = rows[i:i + _RECIPE_TERM_COPY_BATCH_SIZE]
        buf = StringIO()
        for row in batch:
            buf.write("\t".join(_copy_text(value) for value in row))
            buf.write("\n")
        buf.seek(0)
        cursor.copy_expert(copy_sql, buf)
        del buf, batch


def _begin_recipe_term_stream():
    raw_conn = engine.raw_connection()
    cursor = raw_conn.cursor()
    try:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (_COMPILED_RECIPE_TERM_REFRESH_LOCK,),
        )
        cursor.execute(
            f"CREATE TEMP TABLE {_RECIPE_TERM_STREAM_TABLE} "
            "(LIKE compiled_recipe_term_index INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        return raw_conn, cursor
    except Exception:
        raw_conn.rollback()
        raw_conn.close()
        raise


def _finish_recipe_term_stream(
    writer,
    *,
    recipe_ids: list[str] | None = None,
    metadata_payload: dict[str, Any] | None = None,
    metadata_time_ms: int = 0,
    metadata_total_recipes: int = 0,
    metadata_total_matches: int = 0,
) -> str:
    raw_conn, cursor = writer
    try:
        if recipe_ids is None:
            cursor.execute("DELETE FROM compiled_recipe_term_index")
            replace_mode = "delete"
        else:
            cursor.execute(
                "DELETE FROM compiled_recipe_term_index "
                "WHERE found_recipe_id = ANY(%s::uuid[])",
                (recipe_ids,),
            )
            replace_mode = "delete_selected"

        cursor.execute(
            f"INSERT INTO compiled_recipe_term_index ({_RECIPE_TERM_COPY_COLUMNS}) "
            f"SELECT {_RECIPE_TERM_COPY_COLUMNS} FROM {_RECIPE_TERM_STREAM_TABLE}"
        )
        if metadata_payload is not None:
            cursor.execute(
                """
                INSERT INTO cache_metadata (
                    cache_name,
                    last_computed_at,
                    computation_time_ms,
                    total_recipes,
                    total_matches,
                    status,
                    error_message,
                    last_operation
                ) VALUES (
                    'compiled_recipe_term_index',
                    NOW(),
                    %s,
                    %s,
                    %s,
                    'ready',
                    NULL,
                    %s::jsonb
                )
                ON CONFLICT (cache_name) DO UPDATE SET
                    last_computed_at = EXCLUDED.last_computed_at,
                    computation_time_ms = EXCLUDED.computation_time_ms,
                    total_recipes = EXCLUDED.total_recipes,
                    total_matches = EXCLUDED.total_matches,
                    status = EXCLUDED.status,
                    error_message = EXCLUDED.error_message,
                    last_operation = EXCLUDED.last_operation
                """,
                (
                    metadata_time_ms,
                    metadata_total_recipes,
                    metadata_total_matches,
                    json.dumps(metadata_payload, sort_keys=True),
                ),
            )
        raw_conn.commit()
        return replace_mode
    except Exception:
        raw_conn.rollback()
        raise
    finally:
        raw_conn.close()


def _abort_recipe_term_stream(writer) -> None:
    raw_conn, _ = writer
    try:
        raw_conn.rollback()
    finally:
        raw_conn.close()


def _copy_text(value: Any) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def _iter_list_batches(items: list[Any], batch_size: int) -> list[Any]:
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]


def _iter_active_recipe_batches(batch_size: int):
    offset = 0
    while True:
        with get_db_session() as db:
            batch = db.query(FoundRecipe).filter(
                (FoundRecipe.excluded == False) | (FoundRecipe.excluded.is_(None))  # noqa: E712
            ).order_by(FoundRecipe.id).offset(offset).limit(batch_size).all()
        if not batch:
            break
        yield batch
        offset += batch_size


def _count_active_recipes() -> int:
    with get_db_session() as db:
        return db.query(FoundRecipe).filter(
            (FoundRecipe.excluded == False) | (FoundRecipe.excluded.is_(None))  # noqa: E712
        ).count()


def build_offer_candidate_terms(compiled_offer_data: dict[str, Any]) -> set[tuple[str, str]]:
    """Build the exact term set used by today's candidate-routing loop."""
    terms: set[tuple[str, str]] = set()
    keywords = {str(value) for value in compiled_offer_data.get("keywords", ()) if value}
    carrier_stripped = {str(value) for value in compiled_offer_data.get("carrier_stripped", ()) if value}

    for keyword in keywords:
        terms.add((keyword, "keyword"))
        parent = INGREDIENT_PARENTS.get(keyword) or PARENT_MATCH_ONLY.get(keyword)
        if parent:
            terms.add((parent, "parent_keyword"))

    for word in str(compiled_offer_data.get("name_normalized", "")).split():
        if (
            len(word) >= 4
            and word not in keywords
            and word not in carrier_stripped
            and word not in _NAME_WORD_ROUTE_STOPWORDS
        ):
            terms.add((word, "name_word"))

    return terms


def build_offer_candidate_term_map(
    offer_data_cache: dict[int, dict[str, Any]],
) -> dict[str, set[int]]:
    term_to_offer_ids: dict[str, set[int]] = defaultdict(set)
    for offer_object_id, compiled_offer_data in offer_data_cache.items():
        for term, _term_type in build_offer_candidate_terms(compiled_offer_data):
            term_to_offer_ids[term].add(offer_object_id)
    return term_to_offer_ids


def build_fts_keyword_set(
    offer_data_cache: dict[int, dict[str, Any]],
) -> set[str]:
    """Build keyword expansion for legacy recipe FTS paths."""
    all_keywords: set[str] = set()
    for compiled_offer_data in offer_data_cache.values():
        keywords = set(compiled_offer_data.get("keywords", ()))
        all_keywords.update(keywords)
        for keyword in keywords:
            parent = INGREDIENT_PARENTS.get(keyword)
            if parent:
                all_keywords.add(parent)

    reverse_space_normalizations: dict[str, set[str]] = {}
    for source, destination in _SPACE_NORMALIZATIONS:
        reverse_space_normalizations.setdefault(destination, set()).add(source)

    for keyword in list(all_keywords):
        all_keywords.update(reverse_space_normalizations.get(keyword, ()))

    return all_keywords


def build_recipe_search_text(recipe: FoundRecipe) -> str:
    expanded_ingredients: list[str] = []
    for ingredient in recipe.ingredients or ():
        expanded = expand_grouped_ingredient_text(str(ingredient))
        if expanded:
            expanded_ingredients.extend(expanded)

    if not expanded_ingredients:
        return ""

    search_text = fix_swedish_chars(
        " ".join(str(ingredient).lower() for ingredient in expanded_ingredients)
    ).lower()
    search_text = _apply_space_normalizations(search_text)
    search_text = rewrite_buljong_eller_fond(search_text)
    search_text = _HALFTEN_TILL_RE.sub("", search_text)
    return search_text


def build_recipe_search_text_map(
    recipes: list[FoundRecipe],
    *,
    compiled_recipe_payload_cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, str]:
    search_texts: dict[str, str] = {}
    for recipe in recipes:
        recipe_id = str(recipe.id)
        if compiled_recipe_payload_cache is not None:
            payload = compiled_recipe_payload_cache.get(recipe_id, {})
            search_text = _build_recipe_routing_search_text_from_payload(payload)
        else:
            search_text = build_recipe_search_text(recipe).strip()
        if search_text:
            search_texts[recipe_id] = search_text
    return search_texts


def _build_recipe_routing_search_text_from_payload(payload: dict[str, Any]) -> str:
    """Build recipe-side routing text from compiled matcher payloads.

    ``ingredients_search_text`` is the cleaned recipe text, while each prepared
    ingredient ``normalized_text`` includes the canonical aliases that the live
    matcher actually uses (for example makaroner -> pasta, humrar -> hummer,
    and plant-based "matlagning" -> grädde/havregrädde).
    """
    if not payload:
        return ""
    parts: list[str] = [str(payload.get("ingredients_search_text", ""))]
    for item in payload.get("ingredient_match_data", ()):
        if not isinstance(item, dict):
            continue
        normalized_text = str(item.get("normalized_text", "")).strip()
        if normalized_text:
            parts.append(normalized_text)
            parts.extend(_recipe_routing_extra_aliases(normalized_text))
    return " ".join(part for part in parts if part).strip()


def _recipe_routing_extra_aliases(normalized_text: str) -> tuple[str, ...]:
    text_value = normalized_text.lower()
    aliases: list[str] = []
    if (
        "kyckling" in text_value
        and not any(blocker in text_value for blocker in _WHOLE_KYCKLING_BLOCKERS)
        and (
            "hel kyckling" in text_value
            or "helkyckling" in text_value
            or "stor kyckling" in text_value
        )
    ):
        aliases.append("helkyckling")
    if "oreokaka" in text_value or "oreokakor" in text_value:
        aliases.append("oreo")
    if "kycklingschnitzel" in text_value:
        aliases.append("schnitzel")
    if "kycklinginnerfil" in text_value or "kycklinginnerfile" in text_value:
        aliases.append("kyckling")
    if "prästost" in text_value or "prastost" in text_value:
        aliases.append("ost")
    if "johansvamp" in text_value or "skogssvamp" in text_value:
        aliases.append("svamp")
    if (
        "snabbkaffepulver" in text_value
        or "kaffepulver" in text_value
        or "pulverkaffe" in text_value
    ):
        aliases.append("snabbkaffe")
    if "baguetter" in text_value:
        aliases.append("baguette")
    if "tortillabröd" in text_value or "tortillabrod" in text_value:
        aliases.append("tortilla")
    return tuple(aliases)


def build_relevant_offer_map_from_search_texts(
    recipe_search_texts: dict[str, str],
    term_to_offer_ids: dict[str, set[str] | set[int]],
) -> dict[str, set[str] | set[int]]:
    relevant_offer_map: dict[str, set[str] | set[int]] = {}
    for recipe_id, search_text in recipe_search_texts.items():
        relevant: set[str] | set[int] = set()
        for term, offer_ids in term_to_offer_ids.items():
            if term in search_text:
                relevant.update(offer_ids)
        if relevant:
            relevant_offer_map[recipe_id] = relevant
    return relevant_offer_map


def build_candidate_map_from_term_postings(
    recipe_term_postings: dict[str, set[str]],
    offer_term_postings: dict[str, set[str]],
) -> dict[str, set[str]]:
    candidate_map: dict[str, set[str]] = defaultdict(set)
    for term, recipe_ids in recipe_term_postings.items():
        offer_ids = offer_term_postings.get(term)
        if not offer_ids:
            continue
        for recipe_id in recipe_ids:
            candidate_map[recipe_id].update(offer_ids)
    return {recipe_id: set(offer_ids) for recipe_id, offer_ids in candidate_map.items()}


def build_candidate_term_detail_from_term_postings(
    recipe_term_postings: dict[str, set[str]],
    offer_term_postings: dict[str, set[str]],
) -> dict[str, dict[str, set[str]]]:
    """Build recipe -> offer -> routing terms without changing candidate routing."""
    candidate_detail: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for term, recipe_ids in recipe_term_postings.items():
        offer_ids = offer_term_postings.get(term)
        if not offer_ids:
            continue
        for recipe_id in recipe_ids:
            recipe_detail = candidate_detail[recipe_id]
            for offer_id in offer_ids:
                recipe_detail[offer_id].add(term)
    return {
        recipe_id: {
            offer_id: set(terms)
            for offer_id, terms in offer_terms.items()
        }
        for recipe_id, offer_terms in candidate_detail.items()
    }


def refresh_compiled_recipe_offer_candidates(
    *,
    term_manifest_hash: str | None = None,
    cleanup_stale: bool = True,
    recipe_ids: list[str] | None = None,
    offer_identity_keys: list[str] | None = None,
    complete_offer_identity_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Refresh persistent recipe-offer candidate pairs from term indexes."""
    ensure_compiled_recipe_offer_candidates_table()
    ensure_compiled_offer_term_index_table()
    ensure_compiled_recipe_term_index_table()

    scoped_recipe_ids = _dedupe_recipe_ids(recipe_ids)
    scoped_offer_identity_keys = _dedupe_offer_identity_keys(offer_identity_keys)
    complete_scope_offer_identity_keys = _dedupe_offer_identity_keys(complete_offer_identity_keys)
    is_scoped_refresh = bool(scoped_recipe_ids or scoped_offer_identity_keys)
    if is_scoped_refresh and complete_scope_offer_identity_keys:
        raise ValueError("complete_offer_identity_keys cannot be combined with scoped refresh ids")
    is_complete_offer_scope_refresh = bool(complete_scope_offer_identity_keys) and not is_scoped_refresh
    effective_cleanup_stale = cleanup_stale and not is_scoped_refresh
    refresh_scope_label = (
        "subset"
        if is_scoped_refresh
        else ("offer_scope" if is_complete_offer_scope_refresh else "full")
    )
    complete_offer_scope_hash = (
        _candidate_offer_scope_hash(complete_scope_offer_identity_keys)
        if is_complete_offer_scope_refresh
        else None
    )

    if term_manifest_hash is None:
        _, offer_term_stats = load_compiled_offer_term_manifest()
        term_manifest_hash = offer_term_stats.get("term_manifest_hash")
    if not term_manifest_hash:
        raise RuntimeError("compiled_offer_term_index is empty; refresh offer term index first")

    raw_conn = engine.raw_connection()
    cursor = raw_conn.cursor()
    started_at = time.perf_counter()
    try:
        logger.info(
            "CACHE_REBUILD_PROGRESS "
            "run=candidate_index phase=recipe_offer_candidates "
            f"status=starting scope={refresh_scope_label} "
            f"requested_recipes={len(scoped_recipe_ids)} "
            f"requested_offers={len(scoped_offer_identity_keys)} "
            f"complete_offer_scope={len(complete_scope_offer_identity_keys)}"
        )
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (_COMPILED_RECIPE_OFFER_CANDIDATE_REFRESH_LOCK,),
        )
        cursor.execute(f"SET LOCAL work_mem = '{_RECIPE_OFFER_CANDIDATE_WORK_MEM}'")
        cursor.execute("ANALYZE compiled_recipe_term_index")
        cursor.execute("ANALYZE compiled_offer_term_index")
        cursor.execute(
            f"CREATE TEMP TABLE {_RECIPE_OFFER_CANDIDATE_STREAM_TABLE} "
            "(LIKE compiled_recipe_offer_candidates INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM compiled_recipe_term_index
            WHERE matcher_version = %s
              AND recipe_compiler_version = %s
              AND term_manifest_hash = %s
            """,
            (MATCHER_VERSION, RECIPE_COMPILER_VERSION, term_manifest_hash),
        )
        recipe_term_rows = int(cursor.fetchone()[0] or 0)
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM compiled_offer_term_index
            WHERE matcher_version = %s
              AND offer_compiler_version = %s
              AND term_manifest_hash = %s
            """,
            (MATCHER_VERSION, OFFER_COMPILER_VERSION, term_manifest_hash),
        )
        offer_term_rows = int(cursor.fetchone()[0] or 0)
        if recipe_term_rows == 0:
            raise RuntimeError("compiled_recipe_term_index is empty for current matcher/recipe compiler")
        if offer_term_rows == 0:
            raise RuntimeError("compiled_offer_term_index is empty for current matcher/offer compiler")

        candidate_metadata = _load_cache_metadata_last_operation(
            cursor,
            "compiled_recipe_offer_candidates",
        )
        recipe_term_metadata = _load_cache_metadata_last_operation(
            cursor,
            "compiled_recipe_term_index",
        )
        has_complete_candidate_metadata = (
            bool(candidate_metadata.get("complete"))
            and candidate_metadata.get("matcher_version") == MATCHER_VERSION
            and candidate_metadata.get("recipe_compiler_version") == RECIPE_COMPILER_VERSION
            and candidate_metadata.get("offer_compiler_version") == OFFER_COMPILER_VERSION
        )

        inserted_candidate_reason = (
            "term_overlap"
            if not is_scoped_refresh or has_complete_candidate_metadata
            else "term_overlap_scoped"
        )

        offer_affected_recipe_ids: list[str] = []
        if scoped_offer_identity_keys:
            cursor.execute(
                """
                SELECT DISTINCT recipe_terms.found_recipe_id::text
                FROM compiled_recipe_term_index recipe_terms
                JOIN compiled_offer_term_index offer_terms
                  ON offer_terms.term = recipe_terms.term
                 AND offer_terms.matcher_version = recipe_terms.matcher_version
                 AND offer_terms.term_manifest_hash = recipe_terms.term_manifest_hash
                WHERE recipe_terms.matcher_version = %s
                  AND recipe_terms.recipe_compiler_version = %s
                  AND offer_terms.offer_compiler_version = %s
                  AND recipe_terms.term_manifest_hash = %s
                  AND offer_terms.offer_identity_key = ANY(%s::text[])
                ORDER BY recipe_terms.found_recipe_id::text
                """,
                (
                    MATCHER_VERSION,
                    RECIPE_COMPILER_VERSION,
                    OFFER_COMPILER_VERSION,
                    term_manifest_hash,
                    scoped_offer_identity_keys,
                ),
            )
            offer_affected_recipe_ids = [row[0] for row in cursor.fetchall()]

        if is_scoped_refresh:
            target_recipe_ids = _dedupe_recipe_ids(scoped_recipe_ids, offer_affected_recipe_ids)
        else:
            cursor.execute(
                """
                SELECT DISTINCT found_recipe_id::text
                FROM compiled_recipe_term_index
                WHERE matcher_version = %s
                  AND recipe_compiler_version = %s
                  AND term_manifest_hash = %s
                ORDER BY found_recipe_id::text
                """,
                (MATCHER_VERSION, RECIPE_COMPILER_VERSION, term_manifest_hash),
            )
            target_recipe_ids = [row[0] for row in cursor.fetchall()]
            active_recipe_count = _count_active_recipes()
            _validate_full_candidate_recipe_scope(
                indexed_recipe_count=len(target_recipe_ids),
                active_recipe_count=active_recipe_count,
                recipe_term_metadata=recipe_term_metadata,
                term_manifest_hash=term_manifest_hash,
            )

        progress_state: dict[str, Any] = {}
        candidate_rows = 0
        processed_recipe_count = 0
        _log_recipe_offer_candidate_progress(
            completed=0,
            total=len(target_recipe_ids),
            row_count=0,
            started_at=started_at,
            state=progress_state,
            force=True,
        )
        for recipe_id_batch in _iter_list_batches(
            target_recipe_ids,
            _RECIPE_OFFER_CANDIDATE_RECIPE_BATCH_SIZE,
        ):
            scope_conditions: list[str] = []
            scope_params: list[Any] = []
            if scoped_recipe_ids:
                scope_conditions.append("recipe_terms.found_recipe_id = ANY(%s::uuid[])")
                scope_params.append(scoped_recipe_ids)
            if scoped_offer_identity_keys:
                scope_conditions.append("offer_terms.offer_identity_key = ANY(%s::text[])")
                scope_params.append(scoped_offer_identity_keys)
            if complete_scope_offer_identity_keys:
                scope_conditions.append("offer_terms.offer_identity_key = ANY(%s::text[])")
                scope_params.append(complete_scope_offer_identity_keys)
            scope_sql = (
                "\n                  AND (" + " OR ".join(scope_conditions) + ")"
                if scope_conditions
                else ""
            )
            cursor.execute(
                f"""
                INSERT INTO {_RECIPE_OFFER_CANDIDATE_STREAM_TABLE} (
                    found_recipe_id,
                    recipe_identity_key,
                    offer_identity_key,
                    store_id,
                    matcher_version,
                    recipe_compiler_version,
                    offer_compiler_version,
                    term_manifest_hash,
                    matched_terms,
                    candidate_reason,
                    indexed_at
                )
                SELECT
                    recipe_terms.found_recipe_id,
                    recipe_terms.recipe_identity_key,
                    offer_terms.offer_identity_key,
                    offer_terms.store_id,
                    recipe_terms.matcher_version,
                    recipe_terms.recipe_compiler_version,
                    offer_terms.offer_compiler_version,
                    recipe_terms.term_manifest_hash,
                    array_agg(DISTINCT recipe_terms.term ORDER BY recipe_terms.term)::text[] AS matched_terms,
                    %s AS candidate_reason,
                    NOW() AS indexed_at
                FROM compiled_recipe_term_index recipe_terms
                JOIN compiled_offer_term_index offer_terms
                  ON offer_terms.term = recipe_terms.term
                 AND offer_terms.matcher_version = recipe_terms.matcher_version
                 AND offer_terms.term_manifest_hash = recipe_terms.term_manifest_hash
                WHERE recipe_terms.matcher_version = %s
                  AND recipe_terms.recipe_compiler_version = %s
                  AND offer_terms.offer_compiler_version = %s
                  AND recipe_terms.term_manifest_hash = %s
                  AND recipe_terms.found_recipe_id = ANY(%s::uuid[])
                  {scope_sql}
                GROUP BY
                    recipe_terms.found_recipe_id,
                    recipe_terms.recipe_identity_key,
                    offer_terms.offer_identity_key,
                    offer_terms.store_id,
                    recipe_terms.matcher_version,
                    recipe_terms.recipe_compiler_version,
                    offer_terms.offer_compiler_version,
                    recipe_terms.term_manifest_hash
                HAVING bool_or(offer_terms.term_type IN ('keyword', 'parent_keyword'))
                """,
                (
                    inserted_candidate_reason,
                    MATCHER_VERSION,
                    RECIPE_COMPILER_VERSION,
                    OFFER_COMPILER_VERSION,
                    term_manifest_hash,
                    recipe_id_batch,
                    *scope_params,
                ),
            )
            candidate_rows += int(cursor.rowcount or 0)
            processed_recipe_count += len(recipe_id_batch)
            _log_recipe_offer_candidate_progress(
                completed=processed_recipe_count,
                total=len(target_recipe_ids),
                row_count=candidate_rows,
                started_at=started_at,
                state=progress_state,
            )
        if candidate_rows == 0 and not is_scoped_refresh:
            raise RuntimeError(
                "compiled_recipe_offer_candidates refresh produced no rows "
                "despite non-empty recipe and offer term indexes"
            )
        _log_recipe_offer_candidate_progress(
            completed=len(target_recipe_ids),
            total=len(target_recipe_ids),
            row_count=candidate_rows,
            started_at=started_at,
            state=progress_state,
            force=True,
        )

        delete_scope_conditions: list[str] = []
        delete_scope_params: list[Any] = []
        if scoped_recipe_ids:
            delete_scope_conditions.append("found_recipe_id = ANY(%s::uuid[])")
            delete_scope_params.append(scoped_recipe_ids)
        if scoped_offer_identity_keys:
            delete_scope_conditions.append("offer_identity_key = ANY(%s::text[])")
            delete_scope_params.append(scoped_offer_identity_keys)
        delete_scope_sql = (
            "\n              AND (" + " OR ".join(delete_scope_conditions) + ")"
            if delete_scope_conditions
            else ""
        )

        retagged_rows = 0
        if is_scoped_refresh:
            exclude_scope_sql = (
                "\n              AND NOT (" + " OR ".join(delete_scope_conditions) + ")"
                if delete_scope_conditions
                else ""
            )
            cursor.execute(
                f"""
                UPDATE compiled_recipe_offer_candidates
                SET term_manifest_hash = %s,
                    indexed_at = NOW()
                WHERE matcher_version = %s
                  AND recipe_compiler_version = %s
                  AND offer_compiler_version = %s
                  AND term_manifest_hash <> %s
                  {exclude_scope_sql}
                """,
                (
                    term_manifest_hash,
                    MATCHER_VERSION,
                    RECIPE_COMPILER_VERSION,
                    OFFER_COMPILER_VERSION,
                    term_manifest_hash,
                    *delete_scope_params,
                ),
            )
            retagged_rows = int(cursor.rowcount or 0)

        cursor.execute(
            f"""
            DELETE FROM compiled_recipe_offer_candidates
            WHERE matcher_version = %s
              AND recipe_compiler_version = %s
              AND offer_compiler_version = %s
              AND term_manifest_hash = %s
              {delete_scope_sql}
            """,
            (
                MATCHER_VERSION,
                RECIPE_COMPILER_VERSION,
                OFFER_COMPILER_VERSION,
                term_manifest_hash,
                *delete_scope_params,
            ),
        )
        replaced_rows = int(cursor.rowcount or 0)
        cursor.execute(
            f"""
            INSERT INTO compiled_recipe_offer_candidates (
                id,
                found_recipe_id,
                recipe_identity_key,
                offer_identity_key,
                store_id,
                matcher_version,
                recipe_compiler_version,
                offer_compiler_version,
                term_manifest_hash,
                matched_terms,
                candidate_reason,
                indexed_at
            )
            SELECT
                id,
                found_recipe_id,
                recipe_identity_key,
                offer_identity_key,
                store_id,
                matcher_version,
                recipe_compiler_version,
                offer_compiler_version,
                term_manifest_hash,
                matched_terms,
                candidate_reason,
                indexed_at
            FROM {_RECIPE_OFFER_CANDIDATE_STREAM_TABLE}
            """,
        )
        inserted_rows = int(cursor.rowcount or 0)
        stale_deleted_rows = 0
        if effective_cleanup_stale:
            cursor.execute(
                """
                DELETE FROM compiled_recipe_offer_candidates
                WHERE matcher_version <> %s
                   OR recipe_compiler_version <> %s
                   OR offer_compiler_version <> %s
                   OR term_manifest_hash <> %s
                """,
                (
                    MATCHER_VERSION,
                    RECIPE_COMPILER_VERSION,
                    OFFER_COMPILER_VERSION,
                    term_manifest_hash,
                ),
            )
            stale_deleted_rows = int(cursor.rowcount or 0)

        metadata_updated = False
        current_candidate_rows = None
        if not is_scoped_refresh or has_complete_candidate_metadata:
            metadata_recipe_count = _count_active_recipes()
            metadata_offer_scope_filter_sql = ""
            metadata_offer_scope_params: list[Any] = []
            if complete_scope_offer_identity_keys:
                metadata_offer_scope_filter_sql = (
                    "\n                  AND offer_identity_key = ANY(%s::text[])"
                )
                metadata_offer_scope_params.append(complete_scope_offer_identity_keys)
            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM compiled_recipe_offer_candidates
                WHERE matcher_version = %s
                  AND recipe_compiler_version = %s
                  AND offer_compiler_version = %s
                  AND term_manifest_hash = %s
                  {metadata_offer_scope_filter_sql}
                """,
                (
                    MATCHER_VERSION,
                    RECIPE_COMPILER_VERSION,
                    OFFER_COMPILER_VERSION,
                    term_manifest_hash,
                    *metadata_offer_scope_params,
                ),
            )
            current_candidate_rows = int(cursor.fetchone()[0] or 0)
            if complete_scope_offer_identity_keys:
                metadata_complete_offer_scope_count = len(complete_scope_offer_identity_keys)
                metadata_complete_offer_scope_hash = complete_offer_scope_hash
            elif is_scoped_refresh:
                metadata_complete_offer_scope_count = int(
                    candidate_metadata.get("complete_offer_scope_count") or 0
                )
                metadata_complete_offer_scope_hash = candidate_metadata.get(
                    "complete_offer_scope_hash"
                )
            else:
                metadata_complete_offer_scope_count = 0
                metadata_complete_offer_scope_hash = None
            metadata_payload = {
                "complete": True,
                "last_refresh_scope": refresh_scope_label,
                "matcher_version": MATCHER_VERSION,
                "recipe_compiler_version": RECIPE_COMPILER_VERSION,
                "offer_compiler_version": OFFER_COMPILER_VERSION,
                "term_manifest_hash": term_manifest_hash,
                "candidate_rows": current_candidate_rows,
                "processed_recipe_count": processed_recipe_count,
                "active_recipe_count": metadata_recipe_count,
                "complete_offer_scope_count": metadata_complete_offer_scope_count,
                "complete_offer_scope_hash": metadata_complete_offer_scope_hash,
                "requested_recipe_count": len(scoped_recipe_ids),
                "requested_offer_count": len(scoped_offer_identity_keys),
                "retagged_rows": retagged_rows,
            }
            cursor.execute(
                """
                INSERT INTO cache_metadata (
                    cache_name,
                    last_computed_at,
                    computation_time_ms,
                    total_recipes,
                    total_matches,
                    status,
                    error_message,
                    last_operation
                ) VALUES (
                    'compiled_recipe_offer_candidates',
                    NOW(),
                    %s,
                    %s,
                    %s,
                    'ready',
                    NULL,
                    %s::jsonb
                )
                ON CONFLICT (cache_name) DO UPDATE SET
                    last_computed_at = EXCLUDED.last_computed_at,
                    computation_time_ms = EXCLUDED.computation_time_ms,
                    total_recipes = EXCLUDED.total_recipes,
                    total_matches = EXCLUDED.total_matches,
                    status = EXCLUDED.status,
                    error_message = EXCLUDED.error_message,
                    last_operation = EXCLUDED.last_operation
                """,
                (
                    int((time.perf_counter() - started_at) * 1000),
                    metadata_recipe_count,
                    current_candidate_rows,
                    json.dumps(metadata_payload, sort_keys=True),
                ),
            )
            metadata_updated = True

        raw_conn.commit()
    except Exception:
        raw_conn.rollback()
        raise
    finally:
        raw_conn.close()

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    logger.info(
        "CACHE_REBUILD_PROGRESS "
        "run=candidate_index phase=recipe_offer_candidates "
        f"scope={refresh_scope_label} "
        f"rows={candidate_rows} elapsed={_format_progress_duration(elapsed_ms / 1000)}"
    )
    return {
        "matcher_version": MATCHER_VERSION,
        "recipe_compiler_version": RECIPE_COMPILER_VERSION,
        "offer_compiler_version": OFFER_COMPILER_VERSION,
        "term_manifest_hash": term_manifest_hash,
        "refresh_scope": refresh_scope_label,
        "requested_recipe_count": len(scoped_recipe_ids),
        "requested_offer_count": len(scoped_offer_identity_keys),
        "complete_offer_scope_count": len(complete_scope_offer_identity_keys),
        "complete_offer_scope_hash": complete_offer_scope_hash,
        "candidate_reason": inserted_candidate_reason,
        "has_complete_candidate_metadata": has_complete_candidate_metadata,
        "metadata_updated": metadata_updated,
        "current_candidate_rows": current_candidate_rows,
        "offer_affected_recipe_count": len(offer_affected_recipe_ids),
        "processed_recipe_count": processed_recipe_count,
        "recipe_term_rows": recipe_term_rows,
        "offer_term_rows": offer_term_rows,
        "candidate_rows": candidate_rows,
        "replaced_rows": replaced_rows,
        "inserted_rows": inserted_rows,
        "retagged_rows": retagged_rows,
        "stale_deleted_rows": stale_deleted_rows,
        "cleanup_stale": cleanup_stale,
        "effective_cleanup_stale": effective_cleanup_stale,
        "time_ms": elapsed_ms,
    }


def load_compiled_recipe_offer_candidate_map(
    *,
    matcher_version: str = MATCHER_VERSION,
    recipe_compiler_version: str = RECIPE_COMPILER_VERSION,
    offer_compiler_version: str = OFFER_COMPILER_VERSION,
    term_manifest_hash: str | None = None,
    recipe_ids: set[str] | None = None,
    offer_identity_keys: set[str] | None = None,
    include_term_detail: bool = False,
) -> tuple[dict[str, set[str]], dict[str, Any]]:
    """Load persisted candidate pairs as recipe id -> offer identity keys."""
    ensure_compiled_recipe_offer_candidates_table()
    select_columns = [
        "found_recipe_id::text AS found_recipe_id",
        "offer_identity_key",
        "term_manifest_hash",
    ]
    if include_term_detail:
        select_columns.append("matched_terms")
    where_clauses = [
        "matcher_version = :matcher_version",
        "recipe_compiler_version = :recipe_compiler_version",
        "offer_compiler_version = :offer_compiler_version",
    ]
    params: dict[str, Any] = {
        "matcher_version": matcher_version,
        "recipe_compiler_version": recipe_compiler_version,
        "offer_compiler_version": offer_compiler_version,
    }
    if term_manifest_hash:
        where_clauses.append("term_manifest_hash = :term_manifest_hash")
        params["term_manifest_hash"] = term_manifest_hash
    if recipe_ids:
        where_clauses.append("found_recipe_id = ANY(CAST(:recipe_ids AS uuid[]))")
        params["recipe_ids"] = sorted(str(recipe_id) for recipe_id in recipe_ids)
    if offer_identity_keys:
        where_clauses.append("offer_identity_key = ANY(CAST(:offer_identity_keys AS text[]))")
        params["offer_identity_keys"] = sorted(str(offer_key) for offer_key in offer_identity_keys)

    stmt = text(f"""
        SELECT {", ".join(select_columns)}
        FROM compiled_recipe_offer_candidates
        WHERE {" AND ".join(where_clauses)}
    """)

    with get_db_session() as db:
        rows = db.execute(stmt, params).mappings().yield_per(10000)

        candidate_map: dict[str, set[str]] = defaultdict(set)
        candidate_term_detail: dict[str, dict[str, set[str]]] = defaultdict(dict)
        manifest_hashes = set()
        row_count = 0
        term_count = 0
        for row in rows:
            row_count += 1
            recipe_id = row["found_recipe_id"]
            offer_key = row["offer_identity_key"]
            candidate_map[recipe_id].add(offer_key)
            manifest_hashes.add(row["term_manifest_hash"])
            if include_term_detail:
                matched_terms = set(row["matched_terms"] or ())
                candidate_term_detail[recipe_id][offer_key] = matched_terms
                term_count += len(matched_terms)

    stats = {
        "matcher_version": matcher_version,
        "recipe_compiler_version": recipe_compiler_version,
        "offer_compiler_version": offer_compiler_version,
        "loaded_rows": row_count,
        "recipe_count": len(candidate_map),
        "manifest_hashes": sorted(manifest_hashes),
        "term_manifest_hash": next(iter(manifest_hashes), None) if len(manifest_hashes) == 1 else None,
        "included_term_detail": include_term_detail,
        "matched_term_count": term_count if include_term_detail else None,
    }
    if include_term_detail:
        stats["candidate_term_detail"] = {
            recipe_id: dict(offer_terms)
            for recipe_id, offer_terms in candidate_term_detail.items()
        }
    return {recipe_id: set(offer_ids) for recipe_id, offer_ids in candidate_map.items()}, stats


def _build_term_manifest(term_pairs: set[tuple[str, str]]) -> tuple[list[dict[str, str]], str]:
    payload = [
        {"term": term, "term_type": term_type}
        for term, term_type in sorted(term_pairs)
    ]
    return payload, _stable_json_hash(payload)


def _term_type_sort_key(term_type: str) -> tuple[int, str]:
    return (_TERM_TYPE_PRIORITY.get(term_type, 99), term_type)


def _select_routing_term_types(term_pairs: set[tuple[str, str]]) -> dict[str, str]:
    selected: dict[str, str] = {}
    for term, term_type in sorted(term_pairs):
        current = selected.get(term)
        if current is None or _term_type_sort_key(term_type) < _term_type_sort_key(current):
            selected[term] = term_type
    return selected


def recipe_text_contains_routing_term(
    search_text: str,
    term: str,
    term_type: str,
    *,
    search_words: set[str] | None = None,
) -> bool:
    """Return whether a recipe search payload should route on an offer term.

    Canonical keywords intentionally keep the historical substring behavior so
    compound Swedish ingredient forms still route. Product name words are much
    noisier, so they only route on whole recipe words; otherwise "läsk" routes
    from "fläsk", "pepp" from "svartpeppar", and similar false candidates.
    """
    if not search_text or not term:
        return False
    if term_type == "name_word":
        words = search_words if search_words is not None else set(_WORD_PATTERN.findall(search_text))
        return term in words
    if len(term) <= 2:
        words = search_words if search_words is not None else set(_WORD_PATTERN.findall(search_text))
        return term in words
    return term in search_text


def refresh_compiled_offer_term_index() -> dict[str, Any]:
    ensure_compiled_offer_term_index_table()
    with get_db_session() as db:
        _acquire_refresh_lock(db, _COMPILED_OFFER_TERM_REFRESH_LOCK)
        offers = db.query(Offer).order_by(Offer.id).all()

    offer_data_cache, _stats = load_compiled_offer_runtime_cache(offers)

    term_pairs_by_offer: dict[str, set[tuple[str, str]]] = {}
    manifest_terms: set[tuple[str, str]] = set()
    for offer in offers:
        terms = build_offer_candidate_terms(offer_data_cache[id(offer)])
        term_pairs_by_offer[str(offer.id)] = terms
        manifest_terms.update(terms)

    manifest_payload, term_manifest_hash = _build_term_manifest(manifest_terms)
    indexed_at = datetime.now(timezone.utc)
    rows = []
    for offer in offers:
        for term, term_type in sorted(term_pairs_by_offer[str(offer.id)]):
            rows.append({
                "offer_id": offer.id,
                "offer_identity_key": build_offer_identity_key(offer),
                "store_id": offer.store_id,
                "matcher_version": MATCHER_VERSION,
                "offer_compiler_version": OFFER_COMPILER_VERSION,
                "term_manifest_hash": term_manifest_hash,
                "term": term,
                "term_type": term_type,
                "indexed_at": indexed_at,
            })

    with get_db_session() as db:
        replace_mode = _replace_compiled_term_rows(
            db,
            table_name="compiled_offer_term_index",
            model=CompiledOfferTermIndex,
            rows=rows,
            lock_key=_COMPILED_OFFER_TERM_REFRESH_LOCK,
        )

    return {
        "matcher_version": MATCHER_VERSION,
        "offer_compiler_version": OFFER_COMPILER_VERSION,
        "indexed_offers": len(offers),
        "index_rows": len(rows),
        "distinct_terms": len(manifest_terms),
        "term_manifest_hash": term_manifest_hash,
        "replace_mode": replace_mode,
        "term_manifest_sample": manifest_payload[:20],
    }


def _load_offer_term_rows(
    *,
    matcher_version: str = MATCHER_VERSION,
    offer_compiler_version: str = OFFER_COMPILER_VERSION,
) -> list[CompiledOfferTermIndex]:
    ensure_compiled_offer_term_index_table()
    with get_db_session() as db:
        return db.query(CompiledOfferTermIndex).filter(
            CompiledOfferTermIndex.matcher_version == matcher_version,
            CompiledOfferTermIndex.offer_compiler_version == offer_compiler_version,
        ).all()


def load_compiled_offer_term_manifest(
    *,
    matcher_version: str = MATCHER_VERSION,
    offer_compiler_version: str = OFFER_COMPILER_VERSION,
) -> tuple[set[tuple[str, str]], dict[str, Any]]:
    rows = _load_offer_term_rows(
        matcher_version=matcher_version,
        offer_compiler_version=offer_compiler_version,
    )
    term_pairs = {(row.term, row.term_type) for row in rows}
    manifest_hashes = {row.term_manifest_hash for row in rows}
    if rows and len(manifest_hashes) != 1:
        raise RuntimeError(
            "compiled_offer_term_index contains multiple manifest hashes for the "
            "same matcher/offer compiler version"
        )
    stats = {
        "matcher_version": matcher_version,
        "offer_compiler_version": offer_compiler_version,
        "loaded_rows": len(rows),
        "distinct_terms": len(term_pairs),
        "term_manifest_hash": next(iter(manifest_hashes), None),
    }
    return term_pairs, stats


def load_compiled_offer_term_postings(
    *,
    matcher_version: str = MATCHER_VERSION,
    offer_compiler_version: str = OFFER_COMPILER_VERSION,
    key_field: str = "offer_identity_key",
) -> tuple[dict[str, set[str]], dict[str, Any]]:
    key_columns = {
        "offer_id": CompiledOfferTermIndex.offer_id,
        "offer_identity_key": CompiledOfferTermIndex.offer_identity_key,
        "store_id": CompiledOfferTermIndex.store_id,
    }
    key_column = key_columns.get(key_field)
    if key_column is None:
        raise ValueError(f"Unsupported offer term posting key_field: {key_field}")

    ensure_compiled_offer_term_index_table()
    stmt = (
        select(
            CompiledOfferTermIndex.term,
            key_column.label("posting_key"),
            CompiledOfferTermIndex.offer_identity_key,
            CompiledOfferTermIndex.term_manifest_hash,
        )
        .where(
            CompiledOfferTermIndex.matcher_version == matcher_version,
            CompiledOfferTermIndex.offer_compiler_version == offer_compiler_version,
        )
    )
    with get_db_session() as db:
        rows = db.execute(
            stmt.execution_options(stream_results=True)
        ).mappings().yield_per(5000)

        postings: dict[str, set[str]] = defaultdict(set)
        manifest_hashes = set()
        offer_keys = set()
        loaded_rows = 0
        for row in rows:
            loaded_rows += 1
            posting_key = str(row["posting_key"])
            postings[row["term"]].add(posting_key)
            manifest_hashes.add(row["term_manifest_hash"])
            offer_keys.add(str(row["offer_identity_key"]))

    stats = {
        "matcher_version": matcher_version,
        "offer_compiler_version": offer_compiler_version,
        "loaded_rows": loaded_rows,
        "distinct_terms": len(postings),
        "offer_count": len(offer_keys),
        "term_manifest_hash": next(iter(manifest_hashes), None),
    }
    return dict(postings), stats


def refresh_compiled_recipe_term_index(
    *,
    recipes: list[FoundRecipe] | None = None,
    compiled_recipe_payload_cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ensure_compiled_recipe_term_index_table()
    ensure_compiled_recipe_match_table()
    term_pairs, offer_term_stats = load_compiled_offer_term_manifest()
    term_manifest_hash = offer_term_stats["term_manifest_hash"]
    if not term_manifest_hash:
        raise RuntimeError("compiled_offer_term_index is empty; refresh offer term index first")
    routing_term_types = _select_routing_term_types(term_pairs)
    routing_items = tuple(sorted(routing_term_types.items()))
    if recipes is None:
        total_recipe_count = _count_active_recipes()
        recipe_batches = _iter_active_recipe_batches(_RECIPE_TERM_RECIPE_BATCH_SIZE)
    else:
        total_recipe_count = len(recipes)
        recipe_batches = _iter_list_batches(recipes, _RECIPE_TERM_RECIPE_BATCH_SIZE)

    indexed_at = datetime.now(timezone.utc).isoformat()
    row_count = 0
    indexed_recipe_count = 0
    row_buffer: list[tuple[Any, ...]] = []
    progress_started_at = time.perf_counter()
    progress_state: dict[str, Any] = {}
    _log_recipe_term_index_progress(
        completed=0,
        total=total_recipe_count,
        row_count=0,
        started_at=progress_started_at,
        state=progress_state,
        force=True,
    )
    writer = _begin_recipe_term_stream()
    try:
        _, cursor = writer
        for recipe_batch in recipe_batches:
            if compiled_recipe_payload_cache is None:
                batch_payload_cache, _stats = load_compiled_recipe_payload_cache(recipe_batch)
            else:
                batch_payload_cache = compiled_recipe_payload_cache

            indexed_recipe_count += len(recipe_batch)
            for recipe in recipe_batch:
                recipe_id = str(recipe.id)
                search_text = _build_recipe_routing_search_text_from_payload(
                    batch_payload_cache.get(recipe_id, {})
                )
                if not search_text:
                    continue
                search_words = set(_WORD_PATTERN.findall(search_text))
                recipe_identity_key = build_recipe_identity_key(recipe)
                for term, term_type in routing_items:
                    if recipe_text_contains_routing_term(
                        search_text,
                        term,
                        term_type,
                        search_words=search_words,
                    ):
                        row_buffer.append((
                            recipe.id,
                            recipe_identity_key,
                            MATCHER_VERSION,
                            RECIPE_COMPILER_VERSION,
                            term_manifest_hash,
                            term,
                            term_type,
                            indexed_at,
                        ))
                        row_count += 1
                        if len(row_buffer) >= _RECIPE_TERM_COPY_BATCH_SIZE:
                            _copy_recipe_term_rows(
                                cursor,
                                row_buffer,
                                table_name=_RECIPE_TERM_STREAM_TABLE,
                            )
                            row_buffer.clear()
            if compiled_recipe_payload_cache is None:
                batch_payload_cache.clear()
            _log_recipe_term_index_progress(
                completed=indexed_recipe_count,
                total=total_recipe_count,
                row_count=row_count,
                started_at=progress_started_at,
                state=progress_state,
            )

        if row_buffer:
            _copy_recipe_term_rows(
                cursor,
                row_buffer,
                table_name=_RECIPE_TERM_STREAM_TABLE,
            )
            row_buffer.clear()

        metadata_payload = {
            "complete": True,
            "last_refresh_scope": "full" if recipes is None else "provided_recipes",
            "matcher_version": MATCHER_VERSION,
            "recipe_compiler_version": RECIPE_COMPILER_VERSION,
            "term_manifest_hash": term_manifest_hash,
            "indexed_recipes": indexed_recipe_count,
            "active_recipe_count": total_recipe_count,
            "index_rows": row_count,
            "distinct_terms": len(term_pairs),
            "distinct_routing_terms": len(routing_term_types),
        }
        replace_mode = _finish_recipe_term_stream(
            writer,
            metadata_payload=metadata_payload,
            metadata_time_ms=int((time.perf_counter() - progress_started_at) * 1000),
            metadata_total_recipes=total_recipe_count,
            metadata_total_matches=row_count,
        )
        writer = None
        _log_recipe_term_index_progress(
            completed=indexed_recipe_count,
            total=total_recipe_count,
            row_count=row_count,
            started_at=progress_started_at,
            state=progress_state,
            force=True,
        )
    finally:
        if writer is not None:
            _abort_recipe_term_stream(writer)

    return {
        "matcher_version": MATCHER_VERSION,
        "recipe_compiler_version": RECIPE_COMPILER_VERSION,
        "indexed_recipes": indexed_recipe_count,
        "index_rows": row_count,
        "distinct_terms": len(term_pairs),
        "distinct_routing_terms": len(routing_term_types),
        "term_manifest_hash": term_manifest_hash,
        "replace_mode": replace_mode,
    }


def refresh_compiled_recipe_term_index_for_recipe_ids(
    recipe_ids: list[str],
    remove_recipe_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Refresh recipe term-index rows for selected recipes."""
    ensure_compiled_recipe_term_index_table()
    ensure_compiled_recipe_match_table()

    requested_ids = _dedupe_recipe_ids(recipe_ids)
    remove_ids = _dedupe_recipe_ids(remove_recipe_ids)
    affected_ids = _dedupe_recipe_ids(requested_ids, remove_ids)
    if not affected_ids:
        return {
            "matcher_version": MATCHER_VERSION,
            "recipe_compiler_version": RECIPE_COMPILER_VERSION,
            "indexed_recipes": 0,
            "index_rows": 0,
            "missing_recipe_ids": [],
            "inactive_recipe_ids": [],
        }

    term_pairs, offer_term_stats = load_compiled_offer_term_manifest()
    term_manifest_hash = offer_term_stats["term_manifest_hash"]
    if not term_manifest_hash:
        raise RuntimeError("compiled_offer_term_index is empty; refresh offer term index first")
    routing_term_types = _select_routing_term_types(term_pairs)

    with get_db_session() as db:
        _acquire_refresh_lock(db, _COMPILED_RECIPE_TERM_REFRESH_LOCK)
        recipes = db.query(FoundRecipe).filter(FoundRecipe.id.in_(affected_ids)).all()

        found_ids = {str(recipe.id) for recipe in recipes}
        missing_ids = [recipe_id for recipe_id in affected_ids if recipe_id not in found_ids]
        active_recipes = [
            recipe for recipe in recipes
            if not bool(recipe.excluded)
        ]
        inactive_ids = [
            str(recipe.id)
            for recipe in recipes
            if bool(recipe.excluded)
        ]

        payload_cache, _stats = load_compiled_recipe_payload_cache(active_recipes)
        search_texts = build_recipe_search_text_map(
            active_recipes,
            compiled_recipe_payload_cache=payload_cache,
        )

        indexed_at = datetime.now(timezone.utc)
        rows = []
        for recipe in active_recipes:
            recipe_id = str(recipe.id)
            search_text = search_texts.get(recipe_id)
            if not search_text:
                continue
            search_words = set(_WORD_PATTERN.findall(search_text))
            recipe_identity_key = build_recipe_identity_key(recipe)
            for term, term_type in sorted(routing_term_types.items()):
                if recipe_text_contains_routing_term(search_text, term, term_type, search_words=search_words):
                    rows.append({
                        "found_recipe_id": recipe.id,
                        "recipe_identity_key": recipe_identity_key,
                        "matcher_version": MATCHER_VERSION,
                        "recipe_compiler_version": RECIPE_COMPILER_VERSION,
                        "term_manifest_hash": term_manifest_hash,
                        "term": term,
                        "term_type": term_type,
                        "indexed_at": indexed_at,
                    })

        db.query(CompiledRecipeTermIndex).filter(
            CompiledRecipeTermIndex.found_recipe_id.in_(affected_ids)
        ).delete(synchronize_session=False)
        if rows:
            db.bulk_insert_mappings(CompiledRecipeTermIndex, rows)
        db.commit()

    return {
        "matcher_version": MATCHER_VERSION,
        "recipe_compiler_version": RECIPE_COMPILER_VERSION,
        "indexed_recipes": len(active_recipes),
        "index_rows": len(rows),
        "distinct_terms": len(term_pairs),
        "distinct_routing_terms": len(routing_term_types),
        "term_manifest_hash": term_manifest_hash,
        "missing_recipe_ids": missing_ids,
        "inactive_recipe_ids": inactive_ids,
    }


def load_compiled_recipe_term_postings(
    *,
    matcher_version: str = MATCHER_VERSION,
    recipe_compiler_version: str = RECIPE_COMPILER_VERSION,
    term_manifest_hash: str | None = None,
    key_field: str = "found_recipe_id",
) -> tuple[dict[str, set[str]], dict[str, Any]]:
    key_columns = {
        "found_recipe_id": CompiledRecipeTermIndex.found_recipe_id,
        "recipe_identity_key": CompiledRecipeTermIndex.recipe_identity_key,
    }
    key_column = key_columns.get(key_field)
    if key_column is None:
        raise ValueError(f"Unsupported recipe term posting key_field: {key_field}")

    ensure_compiled_recipe_term_index_table()
    stmt = (
        select(
            CompiledRecipeTermIndex.term,
            key_column.label("posting_key"),
            CompiledRecipeTermIndex.term_manifest_hash,
        )
        .where(
            CompiledRecipeTermIndex.matcher_version == matcher_version,
            CompiledRecipeTermIndex.recipe_compiler_version == recipe_compiler_version,
        )
    )
    if term_manifest_hash:
        stmt = stmt.where(CompiledRecipeTermIndex.term_manifest_hash == term_manifest_hash)

    with get_db_session() as db:
        rows = db.execute(
            stmt.execution_options(stream_results=True)
        ).mappings().yield_per(10000)

        postings: dict[str, set[str]] = defaultdict(set)
        manifest_hashes = set()
        recipe_keys = set()
        loaded_rows = 0
        for row in rows:
            loaded_rows += 1
            posting_key = str(row["posting_key"])
            postings[row["term"]].add(posting_key)
            manifest_hashes.add(row["term_manifest_hash"])
            recipe_keys.add(posting_key)

    stats = {
        "matcher_version": matcher_version,
        "recipe_compiler_version": recipe_compiler_version,
        "loaded_rows": loaded_rows,
        "distinct_terms": len(postings),
        "recipe_count": len(recipe_keys),
        "term_manifest_hash": next(iter(manifest_hashes), None),
        "key_field": key_field,
    }
    return dict(postings), stats
