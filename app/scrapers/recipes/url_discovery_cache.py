"""Shared URL discovery cache for recipe scrapers.

The cache stores decisions about recipe-like URLs that did not produce usable
recipes. It deliberately does not mirror real recipes; those live in
``found_recipes``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from loguru import logger
from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError

from database import get_db_session


NON_RECIPE_RETRY_DAYS = (30, 45, 90, 180)
DISCOVERY_CACHE_RETENTION_DAYS = sum(NON_RECIPE_RETRY_DAYS) * 2
TEMPORARY_FAILURE_RETRY_DAYS = 3
TEMPORARY_FAILURE_REASONS = {"http_error", "timeout", "network_error"}
TRACKING_QUERY_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "msclkid",
}
TRACKING_QUERY_PREFIXES = ("utm_",)
_CHUNK_SIZE = 5000


@dataclass
class UrlDiscoveryStats:
    """Counters for one candidate-selection pass."""

    url_candidates_seen: int = 0
    url_candidates_attempted: int = 0
    url_candidates_skipped_duplicate: int = 0
    url_candidates_skipped_existing: int = 0
    url_candidates_skipped_excluded: int = 0
    url_candidates_skipped_non_recipe_cache: int = 0
    url_candidates_retried_non_recipe_cache: int = 0
    discovery_cache_hit_count: int = 0
    discovery_cache_retry_due_count: int = 0
    stopped_by_http_budget: bool = False

    def as_dict(self) -> dict[str, int | bool]:
        return {
            "url_candidates_seen": self.url_candidates_seen,
            "url_candidates_attempted": self.url_candidates_attempted,
            "url_candidates_skipped_duplicate": self.url_candidates_skipped_duplicate,
            "url_candidates_skipped_existing": self.url_candidates_skipped_existing,
            "url_candidates_skipped_excluded": self.url_candidates_skipped_excluded,
            "url_candidates_skipped_non_recipe_cache": self.url_candidates_skipped_non_recipe_cache,
            "url_candidates_retried_non_recipe_cache": self.url_candidates_retried_non_recipe_cache,
            "discovery_cache_hit_count": self.discovery_cache_hit_count,
            "discovery_cache_retry_due_count": self.discovery_cache_retry_due_count,
            "stopped_by_http_budget": self.stopped_by_http_budget,
        }

    def format_log_suffix(self) -> str:
        return (
            f"attempted={self.url_candidates_attempted}, "
            f"skipped_existing={self.url_candidates_skipped_existing}, "
            f"skipped_excluded={self.url_candidates_skipped_excluded}, "
            f"skipped_discovery={self.url_candidates_skipped_non_recipe_cache}, "
            f"retry_due={self.url_candidates_retried_non_recipe_cache}"
        )


@dataclass(frozen=True)
class _DiscoveryRow:
    status: str
    reason: Optional[str]
    next_retry_at: Optional[datetime]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _chunks(values: list[str], size: int = _CHUNK_SIZE) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def normalize_recipe_url(url: str) -> str:
    """Return a stable URL key for recipe discovery decisions."""
    value = (url or "").strip()
    if not value:
        return value

    try:
        parts = urlsplit(value)
    except ValueError:
        return value

    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    if not hostname:
        return value

    netloc = hostname
    if parts.port and not (
        (scheme == "http" and parts.port == 80)
        or (scheme == "https" and parts.port == 443)
    ):
        netloc = f"{netloc}:{parts.port}"

    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")

    query_pairs = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        key_lower = key.lower()
        if key_lower in TRACKING_QUERY_PARAMS:
            continue
        if any(key_lower.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES):
            continue
        query_pairs.append((key, val))

    query = urlencode(query_pairs, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def _normalize_many(values: Iterable[str]) -> set[str]:
    return {normalize_recipe_url(value) for value in values if value}


def _load_existing_and_excluded_urls(source_name: str) -> tuple[set[str], set[str], set[str], set[str]]:
    with get_db_session() as db:
        existing_rows = db.execute(
            text("SELECT url FROM found_recipes WHERE source_name = :source"),
            {"source": source_name},
        ).fetchall()
        excluded_rows = db.execute(text("SELECT url FROM excluded_recipe_urls")).fetchall()

    existing_raw = {row[0] for row in existing_rows if row[0]}
    excluded_raw = {row[0] for row in excluded_rows if row[0]}
    return existing_raw, _normalize_many(existing_raw), excluded_raw, _normalize_many(excluded_raw)


def _load_discovery_rows(source_name: str, normalized_urls: list[str]) -> dict[str, _DiscoveryRow]:
    if not normalized_urls:
        return {}

    rows_by_url: dict[str, _DiscoveryRow] = {}
    stmt = text("""
        SELECT normalized_url, status, reason, next_retry_at
        FROM recipe_url_discovery_cache
        WHERE source_name = :source
          AND normalized_url IN :urls
    """).bindparams(bindparam("urls", expanding=True))

    try:
        with get_db_session() as db:
            for chunk in _chunks(normalized_urls):
                rows = db.execute(stmt, {"source": source_name, "urls": chunk}).mappings().fetchall()
                for row in rows:
                    rows_by_url[row["normalized_url"]] = _DiscoveryRow(
                        status=row["status"],
                        reason=row["reason"],
                        next_retry_at=row["next_retry_at"],
                    )
    except SQLAlchemyError as e:
        logger.debug(f"Recipe URL discovery cache unavailable; continuing without it: {e}")
        return {}

    return rows_by_url


def select_urls_for_scrape(
    *,
    source_name: str,
    candidate_urls: list[str],
    max_http_attempts: Optional[int],
    bulk_import: bool = False,
    now: Optional[datetime] = None,
) -> tuple[list[str], UrlDiscoveryStats]:
    """Filter candidate URLs before HTTP while preserving the HTTP attempt budget."""
    now = now or _utcnow()
    stats = UrlDiscoveryStats(url_candidates_seen=len(candidate_urls))
    max_attempts = None if bulk_import else max_http_attempts

    try:
        existing_raw, existing_normalized, excluded_raw, excluded_normalized = (
            _load_existing_and_excluded_urls(source_name)
        )
    except SQLAlchemyError as e:
        logger.warning(f"Could not pre-load known recipe URLs for {source_name}: {e}")
        existing_raw, existing_normalized, excluded_raw, excluded_normalized = set(), set(), set(), set()

    normalized_by_url = {url: normalize_recipe_url(url) for url in candidate_urls}
    discovery_rows = _load_discovery_rows(source_name, list(set(normalized_by_url.values())))

    selected: list[str] = []
    seen_normalized: set[str] = set()

    for url in candidate_urls:
        normalized_url = normalized_by_url[url]
        if normalized_url in seen_normalized:
            stats.url_candidates_skipped_duplicate += 1
            continue
        seen_normalized.add(normalized_url)

        if url in existing_raw or normalized_url in existing_normalized:
            stats.url_candidates_skipped_existing += 1
            continue

        if url in excluded_raw or normalized_url in excluded_normalized:
            stats.url_candidates_skipped_excluded += 1
            continue

        row = discovery_rows.get(normalized_url)
        if row and row.status in {"known_non_recipe", "temporary_failed", "permanently_skipped"}:
            stats.discovery_cache_hit_count += 1
            if row.next_retry_at and row.next_retry_at > now:
                stats.url_candidates_skipped_non_recipe_cache += 1
                continue
            stats.discovery_cache_retry_due_count += 1
            stats.url_candidates_retried_non_recipe_cache += 1

        if max_attempts is not None and stats.url_candidates_attempted >= max_attempts:
            stats.stopped_by_http_budget = True
            break

        selected.append(url)
        stats.url_candidates_attempted += 1

    return selected, stats


def _status_for_reason(reason: str) -> str:
    if reason in TEMPORARY_FAILURE_REASONS:
        return "temporary_failed"
    return "known_non_recipe"


def _retry_delay_for(status: str, retry_count: int) -> timedelta:
    if status == "temporary_failed":
        return timedelta(days=TEMPORARY_FAILURE_RETRY_DAYS)
    return timedelta(days=NON_RECIPE_RETRY_DAYS[retry_count % len(NON_RECIPE_RETRY_DAYS)])


def record_non_recipe_url(
    *,
    source_name: str,
    url: str,
    reason: str,
    http_status: Optional[int] = None,
    error: Optional[str] = None,
    now: Optional[datetime] = None,
) -> None:
    """Record that a URL did not produce a usable recipe."""
    normalized_url = normalize_recipe_url(url)
    if not source_name or not normalized_url:
        return

    now = now or _utcnow()
    reason = (reason or "parse_error")[:64]
    status = _status_for_reason(reason)

    try:
        with get_db_session() as db:
            row = db.execute(
                text("""
                    SELECT retry_count
                    FROM recipe_url_discovery_cache
                    WHERE source_name = :source
                      AND normalized_url = :normalized_url
                """),
                {"source": source_name, "normalized_url": normalized_url},
            ).fetchone()
            current_retry_count = int(row.retry_count or 0) if row else 0
            retry_count = current_retry_count + 1 if row else 0
            next_retry_at = now + _retry_delay_for(status, retry_count)

            db.execute(
                text("""
                    INSERT INTO recipe_url_discovery_cache (
                        source_name, url, normalized_url, status, reason,
                        first_seen_at, last_checked_at, next_retry_at,
                        retry_count, last_http_status, last_error,
                        created_at, updated_at
                    )
                    VALUES (
                        :source, :url, :normalized_url, :status, :reason,
                        :now, :now, :next_retry_at,
                        :retry_count, :last_http_status, :last_error,
                        :now, :now
                    )
                    ON CONFLICT (source_name, normalized_url) DO UPDATE SET
                        url = EXCLUDED.url,
                        status = EXCLUDED.status,
                        reason = EXCLUDED.reason,
                        last_checked_at = EXCLUDED.last_checked_at,
                        next_retry_at = EXCLUDED.next_retry_at,
                        retry_count = EXCLUDED.retry_count,
                        last_http_status = EXCLUDED.last_http_status,
                        last_error = EXCLUDED.last_error,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "source": source_name,
                    "url": url,
                    "normalized_url": normalized_url,
                    "status": status,
                    "reason": reason,
                    "now": now,
                    "next_retry_at": next_retry_at,
                    "retry_count": retry_count,
                    "last_http_status": http_status,
                    "last_error": (error or "")[:1000] or None,
                },
            )
            db.commit()
    except SQLAlchemyError as e:
        logger.debug(f"Could not record recipe URL discovery miss for {url}: {e}")


def record_recipe_url(*, source_name: str, url: str) -> None:
    """Remove stale discovery state after a URL produced a real recipe."""
    normalized_url = normalize_recipe_url(url)
    if not source_name or not normalized_url:
        return

    try:
        with get_db_session() as db:
            db.execute(
                text("""
                    DELETE FROM recipe_url_discovery_cache
                    WHERE source_name = :source
                      AND normalized_url = :normalized_url
                """),
                {"source": source_name, "normalized_url": normalized_url},
            )
            db.commit()
    except SQLAlchemyError as e:
        logger.debug(f"Could not clear recipe URL discovery row for {url}: {e}")


def clear_source_discovery_cache(source_name: str) -> int:
    """Clear discovery decisions for one source, used by source reset flows."""
    if not source_name:
        return 0
    try:
        with get_db_session() as db:
            result = db.execute(
                text("DELETE FROM recipe_url_discovery_cache WHERE source_name = :source"),
                {"source": source_name},
            )
            db.commit()
            return int(result.rowcount or 0)
    except SQLAlchemyError as e:
        logger.debug(f"Could not clear recipe URL discovery cache for {source_name}: {e}")
        return 0


def cleanup_stale_discovery_cache(
    *,
    retention_days: int = DISCOVERY_CACHE_RETENTION_DAYS,
    now: Optional[datetime] = None,
) -> int:
    """Delete old discovery rows that have not been checked for two retry cycles."""
    now = now or _utcnow()
    retention_days = max(1, int(retention_days or DISCOVERY_CACHE_RETENTION_DAYS))
    cutoff = now - timedelta(days=retention_days)

    try:
        with get_db_session() as db:
            result = db.execute(
                text("""
                    DELETE FROM recipe_url_discovery_cache
                    WHERE last_checked_at < :cutoff
                """),
                {"cutoff": cutoff},
            )
            db.commit()
            deleted = int(result.rowcount or 0)
            if deleted:
                logger.info(
                    "Recipe URL discovery cleanup removed {} stale rows "
                    "(retention_days={})",
                    deleted,
                    retention_days,
                )
            return deleted
    except SQLAlchemyError as e:
        logger.debug(f"Could not clean stale recipe URL discovery cache rows: {e}")
        return 0
