"""Safe cleanup helpers for locally cached recipe images."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote

from loguru import logger
from sqlalchemy import text

from database import get_db_session


APP_DIR = Path(__file__).resolve().parents[1]
RECIPE_IMAGES_DIR = APP_DIR / "static" / "recipe_images"
NO_IMAGE_FILENAME = "no_image.svg"
DEFAULT_MINIMUM_ORPHAN_AGE_SECONDS = 300
_ALLOWED_IMAGE_EXTENSIONS = {".webp", ".jpg", ".jpeg", ".png", ".gif"}
_MAX_REPORTED_ERRORS = 20


def _format_error_sample(errors: list[str], error_count: int, *, limit: int = 5) -> str:
    sample = "; ".join(errors[:limit])
    if error_count > limit:
        sample = f"{sample}; ... {error_count - limit} more"
    return sample


def _record_error(errors: list[str], message: str) -> int:
    if len(errors) < _MAX_REPORTED_ERRORS:
        errors.append(message)
    return 1


def _recipe_image_filename(local_image_path: str | None) -> str | None:
    """Return a safe recipe-image filename from a stored local_image_path."""
    if not local_image_path:
        return None

    normalized = unquote(str(local_image_path)).replace("\\", "/")
    normalized = normalized.split("?", 1)[0].split("#", 1)[0]
    if "recipe_images/" not in normalized:
        return None

    filename = Path(normalized).name
    if not filename or filename == NO_IMAGE_FILENAME:
        return None
    if Path(filename).suffix.lower() not in _ALLOWED_IMAGE_EXTENSIONS:
        return None
    return filename


def _referenced_recipe_image_filenames() -> set[str]:
    with get_db_session() as db:
        rows = db.execute(text("""
            SELECT local_image_path
            FROM found_recipes
            WHERE local_image_path IS NOT NULL
              AND local_image_path != ''
        """)).scalars().all()
    return {
        filename
        for filename in (_recipe_image_filename(path) for path in rows)
        if filename
    }


def _recipe_image_files() -> list[Path]:
    if not RECIPE_IMAGES_DIR.exists():
        return []
    return [
        path
        for path in RECIPE_IMAGES_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in _ALLOWED_IMAGE_EXTENSIONS
    ]


def delete_unreferenced_recipe_image_file(
    local_image_path: str | None,
    *,
    reason: str = "recipe_delete",
) -> dict:
    """Delete one local recipe image only when no recipe row still references it."""
    filename = _recipe_image_filename(local_image_path)
    if not filename:
        return {"deleted_count": 0, "deleted_bytes": 0, "skipped": "not_recipe_image"}

    if filename in _referenced_recipe_image_filenames():
        return {"deleted_count": 0, "deleted_bytes": 0, "skipped": "still_referenced"}

    path = RECIPE_IMAGES_DIR / filename
    if not path.exists():
        return {"deleted_count": 0, "deleted_bytes": 0, "skipped": "missing"}

    size = path.stat().st_size
    try:
        path.unlink()
    except OSError as exc:
        logger.warning(f"Failed to delete recipe image {filename} ({reason}): {exc}")
        return {"deleted_count": 0, "deleted_bytes": 0, "errors": [str(exc)]}

    logger.info(f"Deleted unreferenced recipe image {filename} ({reason})")
    return {"deleted_count": 1, "deleted_bytes": size}


def delete_unreferenced_recipe_image_files(
    local_image_paths: Iterable[str | None],
    *,
    reason: str = "recipe_delete",
) -> dict:
    """Delete many local recipe images, preserving files still referenced elsewhere."""
    filenames = {
        filename
        for filename in (_recipe_image_filename(path) for path in local_image_paths)
        if filename
    }
    if not filenames:
        return {"deleted_count": 0, "deleted_bytes": 0, "errors": []}

    referenced = _referenced_recipe_image_filenames()
    deleted_count = 0
    deleted_bytes = 0
    errors: list[str] = []
    error_count = 0
    skipped_referenced = 0
    skipped_missing = 0

    for filename in sorted(filenames):
        if filename in referenced:
            skipped_referenced += 1
            continue

        path = RECIPE_IMAGES_DIR / filename
        if not path.exists():
            skipped_missing += 1
            continue

        size = path.stat().st_size
        try:
            path.unlink()
        except OSError as exc:
            error_count += _record_error(errors, f"{filename}: {exc}")
            continue

        deleted_count += 1
        deleted_bytes += size

    if deleted_count or error_count:
        logger.info(
            f"Recipe image delete ({reason}): deleted={deleted_count}, "
            f"skipped_referenced={skipped_referenced}, skipped_missing={skipped_missing}, "
            f"errors={error_count}"
        )
        if error_count:
            logger.warning(f"Recipe image delete errors ({reason}): {_format_error_sample(errors, error_count)}")

    return {
        "deleted_count": deleted_count,
        "deleted_bytes": deleted_bytes,
        "skipped_referenced": skipped_referenced,
        "skipped_missing": skipped_missing,
        "error_count": error_count,
        "errors": errors,
    }


def prune_orphan_recipe_images(
    *,
    dry_run: bool = False,
    minimum_age_seconds: int = DEFAULT_MINIMUM_ORPHAN_AGE_SECONDS,
    reason: str = "manual",
) -> dict:
    """Prune local recipe image files that no recipe row references."""
    referenced = _referenced_recipe_image_filenames()
    image_files = _recipe_image_files()
    now = time.time()

    orphan_files = [path for path in image_files if path.name not in referenced]
    eligible_files: list[Path] = []
    skipped_young = 0
    for path in orphan_files:
        age = now - path.stat().st_mtime
        if age < minimum_age_seconds:
            skipped_young += 1
            continue
        eligible_files.append(path)

    candidate_bytes = sum(path.stat().st_size for path in eligible_files)
    deleted_count = 0
    deleted_bytes = 0
    errors: list[str] = []
    error_count = 0

    if not dry_run:
        for path in eligible_files:
            size = path.stat().st_size
            try:
                path.unlink()
            except OSError as exc:
                error_count += _record_error(errors, f"{path.name}: {exc}")
                continue
            deleted_count += 1
            deleted_bytes += size

    result = {
        "dry_run": dry_run,
        "reason": reason,
        "files_on_disk": len(image_files),
        "referenced_files": len(referenced),
        "orphan_count": len(orphan_files),
        "eligible_orphan_count": len(eligible_files),
        "skipped_young_count": skipped_young,
        "candidate_bytes": candidate_bytes,
        "deleted_count": deleted_count,
        "deleted_bytes": deleted_bytes,
        "error_count": error_count,
        "errors": errors,
    }

    if dry_run or deleted_count or error_count:
        logger.info(
            f"Recipe image prune ({reason}): orphans={len(orphan_files)}, "
            f"eligible={len(eligible_files)}, deleted={deleted_count}, "
            f"bytes={deleted_bytes if not dry_run else candidate_bytes}, "
            f"skipped_young={skipped_young}, errors={error_count}, dry_run={dry_run}"
        )
        if error_count:
            logger.warning(f"Recipe image prune errors ({reason}): {_format_error_sample(errors, error_count)}")
    else:
        logger.debug(f"Recipe image prune ({reason}): no eligible orphan files")

    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prune orphan local recipe image files")
    parser.add_argument("--dry-run", action="store_true", help="Report orphan images without deleting them")
    parser.add_argument(
        "--minimum-age-seconds",
        type=int,
        default=DEFAULT_MINIMUM_ORPHAN_AGE_SECONDS,
        help="Only prune orphan files older than this many seconds",
    )
    parser.add_argument("--reason", default="cli", help="Reason label included in logs")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = prune_orphan_recipe_images(
        dry_run=args.dry_run,
        minimum_age_seconds=args.minimum_age_seconds,
        reason=args.reason,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
