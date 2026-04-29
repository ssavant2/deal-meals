"""Shared recipe scraper utilities.

Optional helpers that recipe scrapers can import to avoid duplication.
Scrapers are NOT required to use these — they're convenience functions.
"""

import html
import asyncio
import ctypes
import gc
import os
import re
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Union, Set

from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError
from loguru import logger


DEFAULT_INCREMENTAL_ATTEMPT_HARD_CAP = 300


@dataclass
class RecipeScrapeResult:
    """
    Standard result returned by recipe scraper plugins.

    Status values:
    - success: recipes were fetched
    - success_empty: the scraper completed but found no recipes
    - no_new_recipes: incremental scrape found nothing new
    - partial: some recipes were fetched, but the result may be incomplete
    - failed: scraping did not produce trustworthy data
    - cancelled: the user cancelled the scrape

    The class is intentionally list-like so older CLI code can still use
    len(result), result[:5], and for recipe in result.
    """
    status: str
    recipes: List[Dict] = field(default_factory=list)
    reason: Optional[str] = None
    message_key: Optional[str] = None
    message_params: Dict[str, Any] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.recipes)

    def __bool__(self) -> bool:
        return bool(self.recipes)

    def __iter__(self):
        return iter(self.recipes)

    def __getitem__(self, item):
        return self.recipes[item]

    @property
    def should_save(self) -> bool:
        return self.status in {"success", "partial"} and bool(self.recipes)

    @property
    def is_empty(self) -> bool:
        return not self.recipes

    @property
    def is_failure(self) -> bool:
        return self.status in {"failed", "cancelled"}

    @classmethod
    def success(
        cls,
        recipes: List[Dict],
        *,
        reason: Optional[str] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> "RecipeScrapeResult":
        return cls(
            status="success",
            recipes=recipes or [],
            reason=reason,
            diagnostics=diagnostics or {},
        )

    @classmethod
    def success_empty(
        cls,
        *,
        reason: Optional[str] = None,
        message_key: Optional[str] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> "RecipeScrapeResult":
        return cls(
            status="success_empty",
            recipes=[],
            reason=reason or "empty_result",
            message_key=message_key,
            diagnostics=diagnostics or {},
        )

    @classmethod
    def no_new_recipes(
        cls,
        *,
        reason: Optional[str] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> "RecipeScrapeResult":
        return cls(
            status="no_new_recipes",
            recipes=[],
            reason=reason or "no_new_recipes",
            message_key="recipes.no_new_recipes",
            diagnostics=diagnostics or {},
        )

    @classmethod
    def partial(
        cls,
        recipes: List[Dict],
        *,
        reason: Optional[str] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> "RecipeScrapeResult":
        return cls(
            status="partial",
            recipes=recipes or [],
            reason=reason,
            diagnostics=diagnostics or {},
        )

    @classmethod
    def failed(
        cls,
        *,
        reason: Optional[str] = None,
        message_key: Optional[str] = None,
        message_params: Optional[Dict[str, Any]] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> "RecipeScrapeResult":
        return cls(
            status="failed",
            reason=reason,
            message_key=message_key or "recipes.fetch_failed",
            message_params=message_params or {},
            diagnostics=diagnostics or {},
        )

    @classmethod
    def cancelled(
        cls,
        *,
        reason: Optional[str] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> "RecipeScrapeResult":
        return cls(
            status="cancelled",
            reason=reason or "cancelled",
            message_key="recipes.fetch_cancelled",
            diagnostics=diagnostics or {},
        )


def make_recipe_scrape_result(
    recipes: List[Dict],
    *,
    force_all: bool = False,
    max_recipes: Optional[int] = None,
    reason: Optional[str] = None,
    diagnostics: Optional[Dict[str, Any]] = None,
    failed: bool = False,
    cancelled: bool = False,
) -> RecipeScrapeResult:
    """Create a standardized recipe scrape result from a plugin's local context."""
    if cancelled:
        return RecipeScrapeResult.cancelled(reason=reason, diagnostics=diagnostics)
    if failed:
        return RecipeScrapeResult.failed(reason=reason, diagnostics=diagnostics)
    if max_recipes and recipes and len(recipes) > max_recipes:
        recipes = recipes[:max_recipes]
    if recipes:
        return RecipeScrapeResult.success(recipes, reason=reason, diagnostics=diagnostics)
    if reason in {"no_new_recipes", "no_pending_urls"}:
        return RecipeScrapeResult.no_new_recipes(reason=reason, diagnostics=diagnostics)
    return RecipeScrapeResult.success_empty(reason=reason, diagnostics=diagnostics)


def incremental_attempt_limit(
    *,
    max_recipes: Optional[int],
    available_count: int,
    default_limit: Optional[int] = None,
    hard_cap: int = DEFAULT_INCREMENTAL_ATTEMPT_HARD_CAP,
) -> int:
    """Return how many candidate URLs to try for an incremental target.

    ``max_recipes`` is a target for usable recipes, not a strict URL-attempt
    limit. Some sites expose articles/profiles in recipe-like sitemaps, so a
    hidden attempt budget keeps the UI target intuitive without surfacing noisy
    attempt counts. For small configured targets, the hard cap is the maximum
    number of URLs to try before giving up; for larger targets, the target
    itself becomes the maximum.
    """
    available_count = max(0, int(available_count or 0))
    if max_recipes:
        target = max(1, int(max_recipes))
        attempt_budget = max(target, int(hard_cap or 0))
        return min(available_count, attempt_budget)
    if default_limit is None:
        return available_count
    return min(available_count, max(0, int(default_limit)))


def recipe_target_reached(
    *,
    max_recipes: Optional[int],
    recipes: Optional[List[Dict]] = None,
    stream_saver: Optional[Any] = None,
) -> bool:
    """Return True when a scrape has reached its usable-recipe target."""
    if not max_recipes:
        return False
    if stream_saver is not None:
        return int(getattr(stream_saver, "seen_count", 0) or 0) >= int(max_recipes)
    return len(recipes or []) >= int(max_recipes)


def normalize_recipe_scrape_result(
    raw_result: Union[RecipeScrapeResult, List[Dict], Dict, None],
    *,
    mode: Optional[str] = None,
    source_name: Optional[str] = None,
) -> RecipeScrapeResult:
    """Normalize legacy recipe plugin returns into RecipeScrapeResult."""
    if isinstance(raw_result, RecipeScrapeResult):
        return raw_result

    diagnostics = {"source": source_name} if source_name else {}

    if isinstance(raw_result, list):
        if raw_result:
            return RecipeScrapeResult.success(
                raw_result,
                reason="legacy_list_result",
                diagnostics=diagnostics,
            )
        if mode == "incremental":
            return RecipeScrapeResult.no_new_recipes(
                reason="legacy_empty_incremental",
                diagnostics=diagnostics,
            )
        return RecipeScrapeResult.success_empty(
            reason=f"legacy_empty_{mode or 'unknown'}",
            diagnostics=diagnostics,
        )

    if isinstance(raw_result, dict):
        recipes = raw_result.get("recipes") or []
        status = raw_result.get("status") or ("success" if recipes else "success_empty")
        return RecipeScrapeResult(
            status=status,
            recipes=recipes,
            reason=raw_result.get("reason"),
            message_key=raw_result.get("message_key"),
            message_params=raw_result.get("message_params") or {},
            diagnostics={**diagnostics, **(raw_result.get("diagnostics") or {})},
        )

    return RecipeScrapeResult.failed(
        reason=f"unexpected_result_type:{type(raw_result).__name__}",
        diagnostics=diagnostics,
    )


def parse_iso8601_duration(duration: str) -> Optional[int]:
    """Parse ISO 8601 duration string to minutes.

    Handles: PT30M, PT1H, PT1H30M, P1DT2H30M, P0DT00H30M00S, etc.

    Returns:
        Minutes as int, or None if unparseable/zero.
    """
    if not duration:
        return None

    total_mins = 0

    days = re.search(r'(\d+)D', duration)
    if days:
        total_mins += int(days.group(1)) * 24 * 60

    hours = re.search(r'(\d+)H', duration)
    if hours:
        total_mins += int(hours.group(1)) * 60

    minutes = re.search(r'(\d+)M', duration)
    if minutes:
        total_mins += int(minutes.group(1))

    return total_mins if total_mins > 0 else None


def unescape_html(text: str) -> str:
    """Decode HTML entities in text (e.g., &amp; -> &, &lt; -> <).

    Safe to call on already-clean text — returns it unchanged.
    """
    if not text:
        return text
    return html.unescape(text)


def _is_type(data: Dict, type_name: str) -> bool:
    """Check if a JSON-LD object has the given @type (handles both string and list)."""
    t = data.get('@type')
    if isinstance(t, list):
        return type_name in t
    return t == type_name


_QUANTITY_RE = re.compile(r'(\d+)\.(\d{3,})')

def _round_quantity(match):
    """Round floating-point precision errors in ingredient quantities.
    E.g. 0.499998 -> 0.5, 1.000002 -> 1, 2.333333 -> 2.3
    """
    num = float(match.group(0))
    rounded_int = round(num)
    if abs(num - rounded_int) < 0.01:
        return str(rounded_int)
    # Round to 1 decimal
    result = f"{num:.1f}".rstrip('0').rstrip('.')
    return result

def clean_ingredient_quantities(ingredients: Optional[List]) -> Optional[List]:
    """Fix floating-point precision errors in ingredient quantity strings."""
    if not ingredients:
        return ingredients
    cleaned = []
    for ing in ingredients:
        if isinstance(ing, str):
            cleaned.append(_QUANTITY_RE.sub(_round_quantity, ing))
        else:
            cleaned.append(ing)
    return cleaned


_SERVING_LIST_RE = re.compile(
    r'^([A-ZÅÄÖ]?[a-zåäöéèü]+(?:\s+[a-zåäöéèü]+)*)'  # first item (no quantity)
    r',\s*'                                               # comma separator
    r'([a-zåäöéèü]+(?:\s+[a-zåäöéèü]+)*)'                # second item
    r'\s+och\s+'                                           # " och "
    r'([a-zåäöéèü]+(?:\s+[a-zåäöéèü]+)*)$'               # third item
)


def split_serving_lists(ingredients: Optional[List]) -> Optional[List]:
    """Split comma-separated serving/topping lists into individual ingredients.

    Recipe sources sometimes combine serving suggestions into one line:
      "skivade jordgubbar, pistagenötter och växtbaserad dryck"
    This should be 3 separate ingredients.

    Only splits lines that:
    - Start WITHOUT a quantity (no leading digits)
    - Match pattern "X, Y och Z" (exactly 3 items)
    - Don't contain parentheses (those are usually descriptions, not lists)

    Safe: "1 dl grädde, vispat och kylt" is NOT split (starts with quantity).
    """
    if not ingredients:
        return ingredients
    result = []
    for ing in ingredients:
        if not isinstance(ing, str):
            result.append(ing)
            continue
        stripped = ing.strip()
        # Skip if starts with digit (has quantity) or contains parentheses
        if not stripped or stripped[0].isdigit() or '(' in stripped:
            result.append(ing)
            continue
        m = _SERVING_LIST_RE.match(stripped)
        if m:
            parts = [m.group(1).strip(), m.group(2).strip(), m.group(3).strip()]
            # Require each split part to be a real food item (>= 8 chars),
            # not a cooking method like "rostade" or "hackade"
            if all(len(p) >= 8 for p in parts[1:]):
                result.extend(parts)
            else:
                result.append(ing)
        else:
            result.append(ing)
    return result


def validate_image_url(url: Optional[str]) -> Optional[str]:
    """Validate and normalize a recipe image URL from JSON-LD.

    Returns the URL if it's a valid absolute http(s) URL, otherwise None.
    Filters out relative paths (e.g. /static/img/placeholder.png) that some
    sites return for recipes without a real image.
    """
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return None
    return url


def extract_json_ld_recipe(html_content: str) -> Optional[Dict]:
    """Extract Recipe schema from JSON-LD script tags in HTML.

    Handles three common structures:
    - Direct Recipe object: {"@type": "Recipe", ...}
    - @graph array: {"@graph": [{"@type": "Recipe", ...}, ...]}
    - List of schemas: [{"@type": "Recipe", ...}, ...]

    Returns:
        The raw Recipe dict from JSON-LD, or None if not found.
    """
    json_ld_matches = re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html_content,
        re.DOTALL
    )

    for match in json_ld_matches:
        try:
            data = json.loads(match)

            # Handle @graph array
            if isinstance(data, dict) and '@graph' in data:
                for item in data['@graph']:
                    if isinstance(item, dict) and _is_type(item, 'Recipe'):
                        return item

            # Handle direct Recipe object
            if isinstance(data, dict) and _is_type(data, 'Recipe'):
                return data

            # Handle array of schemas
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and _is_type(item, 'Recipe'):
                        return item

        except json.JSONDecodeError:
            continue

    return None


def touch_source_scraped_at(source_name: str) -> int:
    """Update scraped_at for all recipes of a source to mark it as recently synced.

    Called after every sync (including incremental with 0 new recipes) so that
    the 'synced last month' status metric stays accurate.

    Returns number of recipes touched.
    """
    from database import get_db_session
    with get_db_session() as db:
        result = db.execute(
            text("UPDATE found_recipes SET scraped_at = NOW() WHERE source_name = :src"),
            {"src": source_name}
        )
        db.commit()
        return result.rowcount


def _extend_unique_id_list(target: List[str], values: List[Any]) -> None:
    """Append stringified IDs to target, preserving order and uniqueness."""
    seen = set(target)
    for value in values or []:
        if value is None:
            continue
        str_value = str(value)
        if str_value in seen:
            continue
        target.append(str_value)
        seen.add(str_value)


def delete_stale_source_recipes_with_ids(source_name: str, keep_urls: Set[str]) -> Dict[str, Any]:
    """Delete non-excluded recipes for a source that were not seen in a full sync."""
    result = {"deleted": 0, "removed_recipe_ids": []}
    if not keep_urls:
        return result

    from database import get_db_session
    from models import FoundRecipe

    with get_db_session() as db:
        stale_rows = db.query(FoundRecipe.id).filter(
            FoundRecipe.source_name == source_name,
            (FoundRecipe.excluded == False) | (FoundRecipe.excluded.is_(None)),  # noqa: E712
            ~FoundRecipe.url.in_(list(keep_urls)),
        ).all()
        removed_ids = [str(row[0]) for row in stale_rows]
        deleted = db.query(FoundRecipe).filter(
            FoundRecipe.source_name == source_name,
            (FoundRecipe.excluded == False) | (FoundRecipe.excluded.is_(None)),  # noqa: E712
            ~FoundRecipe.url.in_(list(keep_urls)),
        ).delete(synchronize_session=False)
        db.commit()

    result["deleted"] = deleted
    result["removed_recipe_ids"] = removed_ids
    return result


def delete_stale_source_recipes(source_name: str, keep_urls: Set[str]) -> int:
    """Delete non-excluded recipes for a source that were not seen in a full sync."""
    return int(delete_stale_source_recipes_with_ids(source_name, keep_urls)["deleted"])


_MALLOC_TRIM = None
_MALLOC_TRIM_CHECKED = False


def _get_malloc_trim():
    """Return glibc malloc_trim when available."""
    global _MALLOC_TRIM, _MALLOC_TRIM_CHECKED
    if _MALLOC_TRIM_CHECKED:
        return _MALLOC_TRIM

    _MALLOC_TRIM_CHECKED = True
    if os.name != "posix":
        return None

    try:
        libc = ctypes.CDLL("libc.so.6")
        trim = libc.malloc_trim
        trim.argtypes = [ctypes.c_size_t]
        trim.restype = ctypes.c_int
        _MALLOC_TRIM = trim
    except Exception:
        _MALLOC_TRIM = None
    return _MALLOC_TRIM


def release_recipe_batch_memory() -> None:
    """Encourage freed batch/session memory to return to the container."""
    gc.collect()
    trim = _get_malloc_trim()
    if trim:
        try:
            trim(0)
        except Exception:
            pass


class StreamingRecipeSaver:
    """Save scraped recipes in small batches while keeping final-sync semantics."""

    def __init__(
        self,
        source_name: str,
        *,
        batch_size: int = 50,
        overwrite: bool = False,
        max_recipes: Optional[int] = None,
    ):
        self.source_name = source_name
        self.batch_size = batch_size
        self.overwrite = overwrite
        self.max_recipes = max_recipes
        self.pending: List[Dict] = []
        self.saved_urls: Set[str] = set()
        self.seen_count = 0
        self.stats: Dict[str, Any] = {
            "cleared": 0,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "spell_corrections": 0,
            "stale_deleted": 0,
            "saved": 0,
        }
        self.stats["created_recipe_ids"] = []
        self.stats["updated_recipe_ids"] = []
        self.stats["changed_recipe_ids"] = []
        self.stats["removed_recipe_ids"] = []

    def _add_stats(self, stats: Dict[str, Any]) -> None:
        for key in ("cleared", "created", "updated", "skipped", "errors", "spell_corrections"):
            self.stats[key] = self.stats.get(key, 0) + int(stats.get(key, 0) or 0)
        for key in ("created_recipe_ids", "updated_recipe_ids", "changed_recipe_ids", "removed_recipe_ids"):
            self.stats.setdefault(key, [])
            _extend_unique_id_list(self.stats[key], stats.get(key, []))
        self.stats["saved"] = self.stats.get("created", 0) + self.stats.get("updated", 0)

    async def add(self, recipe: Optional[Dict]) -> None:
        if not recipe:
            return
        if self.max_recipes and self.seen_count >= self.max_recipes:
            return

        self.pending.append(recipe)
        self.seen_count += 1
        url = recipe.get("url")
        if url:
            self.saved_urls.add(url)

        if len(self.pending) >= self.batch_size:
            await self.flush()

    async def flush(self) -> None:
        if not self.pending:
            return

        result = make_recipe_scrape_result(
            self.pending,
            force_all=self.overwrite,
            max_recipes=self.max_recipes,
        )
        stats = await asyncio.to_thread(
            save_recipes_to_database,
            result,
            self.source_name,
            False,
            False,
        )
        self._add_stats(stats)
        logger.info(
            f"Saved {self.source_name} batch: {len(self.pending)} recipes "
            f"(created={stats.get('created', 0)}, updated={stats.get('updated', 0)})"
        )
        self.pending.clear()
        release_recipe_batch_memory()

    async def finish(self, *, cancelled: bool = False) -> Dict[str, Any]:
        if cancelled:
            self.pending.clear()
            self.stats["scrape_status"] = "cancelled"
            self.stats["scrape_reason"] = "cancelled"
            return self.stats

        await self.flush()

        if self.overwrite and self.saved_urls:
            stale_result = await asyncio.to_thread(
                delete_stale_source_recipes_with_ids,
                self.source_name,
                self.saved_urls,
            )
            stale_deleted = int(stale_result.get("deleted", 0) or 0)
            self.stats["stale_deleted"] = stale_deleted
            self.stats["cleared"] = self.stats.get("cleared", 0) + stale_deleted
            _extend_unique_id_list(
                self.stats["removed_recipe_ids"],
                stale_result.get("removed_recipe_ids", []),
            )
            logger.info(
                f"Deleted {stale_deleted} stale {self.source_name} recipes "
                "after completed full scrape"
            )
        elif self.overwrite:
            logger.warning(
                f"Full {self.source_name} scrape produced no saveable recipes; "
                "keeping existing DB rows"
            )

        if self.saved_urls or not self.overwrite:
            touched = await asyncio.to_thread(touch_source_scraped_at, self.source_name)
            logger.info(f"Touched scraped_at for {touched} {self.source_name} recipes")

        self.stats["scrape_status"] = "success" if self.saved_urls else "success_empty"
        self.stats["scrape_reason"] = None if self.saved_urls else "empty_result"
        self.stats["saved"] = self.stats.get("created", 0) + self.stats.get("updated", 0)
        release_recipe_batch_memory()
        return self.stats


def save_recipes_to_database(
    recipes: Union[RecipeScrapeResult, List[Dict]],
    source_name: str,
    clear_old: bool = False,
    touch_source: bool = True,
) -> Dict[str, Any]:
    """Save scraped recipes to database with upsert logic.

    Shared implementation used by all recipe scrapers. Handles:
    - Deduplication of input recipes by URL
    - Clearing old recipes (preserving user-excluded ones)
    - Updating existing recipes or inserting new ones
    - Per-recipe commits to prevent rollback cascades

    Args:
        recipes: List of recipe dicts. Each must have at minimum:
            url, name, source_name, scraped_at.
            Optional: image_url, ingredients, prep_time_minutes, servings.
        source_name: The DB source identifier (e.g. "ICA.se", "Coop.se").
        clear_old: If True, delete old recipes for this source first.
        touch_source: If True, update scraped_at for the whole source after saving.

    Returns:
        Stats dict with counters and affected recipe ID lists.
    """
    from database import get_db_session
    from models import FoundRecipe, SpellCorrection
    from utils.spell_check import apply_corrections_to_ingredients

    scrape_result = normalize_recipe_scrape_result(recipes, source_name=source_name)
    recipes = scrape_result.recipes

    stats: Dict[str, Any] = {
        "cleared": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "spell_corrections": 0,
        "created_recipe_ids": [],
        "updated_recipe_ids": [],
        "changed_recipe_ids": [],
        "removed_recipe_ids": [],
    }

    if not recipes:
        # Still touch scraped_at for successful empty/no-new runs so
        # 'synced last month' stays accurate. Failed/cancelled runs should
        # not look like a fresh sync.
        if not scrape_result.is_failure:
            if touch_source:
                touch_source_scraped_at(source_name)
        stats["scrape_status"] = scrape_result.status
        stats["scrape_reason"] = scrape_result.reason
        return stats

    # Deduplicate by URL (keep first occurrence)
    seen_urls = set()
    unique_recipes = []
    for recipe in recipes:
        url = recipe.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_recipes.append(recipe)

    dupes = len(recipes) - len(unique_recipes)
    if dupes > 0:
        logger.info(f"Deduplicated: {len(recipes)} -> {len(unique_recipes)} recipes")
        stats["skipped"] += dupes

    unique_urls = [recipe.get("url") for recipe in unique_recipes if recipe.get("url")]

    with get_db_session() as db:
        # Load permanently excluded URLs (deleted duplicates etc)
        if unique_urls:
            excluded_stmt = text(
                "SELECT url FROM excluded_recipe_urls WHERE url IN :urls"
            ).bindparams(bindparam("urls", expanding=True))
            excluded_urls = {
                row[0] for row in db.execute(excluded_stmt, {"urls": unique_urls}).fetchall()
            }
        else:
            excluded_urls = set()

        # Filter out excluded URLs
        before_excl = len(unique_recipes)
        unique_recipes = [r for r in unique_recipes if r.get("url") not in excluded_urls]
        excl_skipped = before_excl - len(unique_recipes)
        if excl_skipped > 0:
            logger.info(f"Skipped {excl_skipped} permanently excluded URLs")
            stats["skipped"] += excl_skipped

        # Clear old recipes if requested (preserve excluded)
        if clear_old:
            clear_rows = db.query(FoundRecipe.id).filter(
                FoundRecipe.source_name == source_name,
                (FoundRecipe.excluded == False) | (FoundRecipe.excluded.is_(None))  # noqa: E712
            ).all()
            cleared_ids = [str(row[0]) for row in clear_rows]
            deleted = db.query(FoundRecipe).filter(
                FoundRecipe.source_name == source_name,
                (FoundRecipe.excluded == False) | (FoundRecipe.excluded.is_(None))  # noqa: E712
            ).delete(synchronize_session=False)
            db.commit()
            stats["cleared"] = deleted
            _extend_unique_id_list(stats["removed_recipe_ids"], cleared_ids)
            logger.info(f"Cleared {deleted} old recipes (preserved excluded)")

        # Pre-load only the rows this save call can update. Streaming saves call
        # this many times, so source-wide ORM loads become expensive over time.
        if unique_urls:
            existing_rows = db.query(FoundRecipe).filter(
                FoundRecipe.source_name == source_name,
                FoundRecipe.url.in_(unique_urls),
            ).all()
        else:
            existing_rows = []
        existing_map = {r.url: r for r in existing_rows}

        # Pre-load per-recipe spell check exclusions (original_word only, index-independent)
        existing_ids = [r.id for r in existing_rows]
        if existing_ids:
            spell_exclusions_raw = db.query(
                SpellCorrection.recipe_id,
                SpellCorrection.original_word,
            ).filter(
                SpellCorrection.excluded == True,  # noqa: E712
                SpellCorrection.recipe_id.in_(existing_ids),
            ).all()
        else:
            spell_exclusions_raw = []
        spell_exclusions_by_recipe = {}
        for row in spell_exclusions_raw:
            rid = row[0]
            if rid not in spell_exclusions_by_recipe:
                spell_exclusions_by_recipe[rid] = set()
            spell_exclusions_by_recipe[rid].add(row[1])

        # Pre-load global spell check exclusions
        global_exclusions_raw = db.execute(
            text("SELECT original_word, corrected_word FROM spell_excluded_words")
        ).fetchall()
        global_exclusions = {(row[0], row[1]) for row in global_exclusions_raw}

        for i, recipe in enumerate(unique_recipes, 1):
            try:
                existing = existing_map.get(recipe["url"])

                cleaned_ingredients = clean_ingredient_quantities(recipe.get("ingredients"))

                # Apply spell corrections
                recipe_id = existing.id if existing else None
                excluded_per_recipe = spell_exclusions_by_recipe.get(recipe_id, set()) if recipe_id else set()
                corrected_ingredients, corrections = apply_corrections_to_ingredients(
                    cleaned_ingredients or [], excluded_per_recipe, global_exclusions
                )
                if corrections:
                    cleaned_ingredients = corrected_ingredients

                if existing:
                    existing.name = recipe["name"]
                    existing.image_url = validate_image_url(recipe.get("image_url"))
                    existing.ingredients = cleaned_ingredients
                    existing.prep_time_minutes = recipe.get("prep_time_minutes")
                    existing.servings = recipe.get("servings")
                    existing.scraped_at = recipe.get("scraped_at", datetime.now(timezone.utc))
                    stats["updated"] += 1
                    pending_change_kind = "updated"
                else:
                    db.add(FoundRecipe(
                        source_name=source_name,
                        url=recipe["url"],
                        name=recipe["name"],
                        image_url=validate_image_url(recipe.get("image_url")),
                        ingredients=cleaned_ingredients,
                        prep_time_minutes=recipe.get("prep_time_minutes"),
                        servings=recipe.get("servings"),
                        scraped_at=recipe.get("scraped_at", datetime.now(timezone.utc)),
                    ))
                    stats["created"] += 1
                    pending_change_kind = "created"

                db.commit()
                saved_recipe_id = existing.id if existing else db.execute(
                    text("SELECT id FROM found_recipes WHERE url = :url"),
                    {"url": recipe["url"]}
                ).scalar()
                if saved_recipe_id:
                    if pending_change_kind == "updated":
                        _extend_unique_id_list(stats["updated_recipe_ids"], [saved_recipe_id])
                    else:
                        _extend_unique_id_list(stats["created_recipe_ids"], [saved_recipe_id])
                    _extend_unique_id_list(stats["changed_recipe_ids"], [saved_recipe_id])

                # Save spell corrections to DB (after commit so we have recipe_id)
                if corrections:
                    rid = saved_recipe_id
                    if rid:
                        # Remove old non-excluded corrections for this recipe
                        db.execute(
                            text("DELETE FROM spell_corrections WHERE recipe_id = :rid AND excluded = false"),
                            {"rid": rid}
                        )
                        for c in corrections:
                            db.add(SpellCorrection(
                                recipe_id=rid,
                                ingredient_index=c['ingredient_index'],
                                original_word=c['original_word'],
                                corrected_word=c['corrected_word'],
                            ))
                        db.commit()
                        stats["spell_corrections"] += len(corrections)

                if i % 100 == 0:
                    logger.debug(f"Progress: {i}/{len(unique_recipes)}")

            except IntegrityError:
                db.rollback()
                logger.debug(f"Duplicate recipe URL, skipping: {recipe.get('url', '?')}")
                stats["errors"] += 1
            except Exception as e:
                db.rollback()
                logger.warning(f"Error saving recipe: {e}")
                stats["errors"] += 1

    logger.info(
        f"Database: created={stats['created']}, updated={stats['updated']}, "
        f"spell_corrections={stats['spell_corrections']}, errors={stats['errors']}"
    )
    stats["scrape_status"] = scrape_result.status
    stats["scrape_reason"] = scrape_result.reason

    if touch_source:
        # Touch all recipes for this source so 'synced last month' stays accurate
        touched = touch_source_scraped_at(source_name)
        logger.info(f"Touched scraped_at for {touched} {source_name} recipes")

    return stats
