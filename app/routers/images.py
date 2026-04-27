"""
Image Management API Routes.

This router handles all image-related API endpoints:
- /api/images/preferences - Image preferences (GET/POST)
- /api/images/status - Image status
- /api/images/download - Start/status/cancel download
- /api/images/clear - Clear all images
- /api/images/failures - List and reset failures
"""

import os
import asyncio
import hashlib
import html
from io import BytesIO
from collections import defaultdict
from urllib.parse import urlparse
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from utils.rate_limit import limiter
from config import settings
from sqlalchemy import text
from loguru import logger
import httpx

from database import get_db_session
from utils.errors import friendly_error, is_valid_uuid
from utils.recipe_image_cleanup import (
    delete_unreferenced_recipe_image_file,
    delete_unreferenced_recipe_image_files,
    prune_orphan_recipe_images,
)
from utils.security import is_safe_url, ssrf_safe_event_hook
from state import image_download_state, get_image_state, update_image_state, try_start_image_download
from constants_timeouts import HTTP_TIMEOUT

router = APIRouter(prefix="/api/images", tags=["images"])


# Path for locally cached images
RECIPE_IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "recipe_images")
os.makedirs(RECIPE_IMAGES_DIR, exist_ok=True)

# Rate limiting constants for image downloads
IMAGE_DELAY_PER_IMAGE = 1.0           # 1 second between each image
IMAGE_BATCH_SIZE = 50                 # Pause after this many images
IMAGE_BATCH_PAUSE_MANUAL = 15         # 15 seconds pause for manual download
IMAGE_BATCH_PAUSE_AUTO = 20           # 20 seconds pause for auto-download

# Reference to active download task (prevents GC before task starts)
_active_download_task: asyncio.Task | None = None


def _prune_recipe_image_orphans_after_download() -> None:
    """Run a best-effort orphan prune after local image paths have been refreshed."""
    try:
        image_cleanup = prune_orphan_recipe_images(
            dry_run=False,
            reason="image_download_complete",
        )
        image_download_state["orphans_pruned"] = image_cleanup["deleted_count"]
    except Exception as e:
        logger.warning(f"Could not prune orphan recipe images after image download: {e}")


@router.get("/preferences")
def get_image_preferences():
    """Get image caching preferences."""
    try:
        with get_db_session() as db:
            # Check if table exists first
            table_check = db.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'image_preferences'
                )
            """)).scalar()

            if not table_check:
                return JSONResponse({
                    "success": True,
                    "save_local": False,
                    "auto_download": False
                })

            result = db.execute(text("""
                SELECT save_local, auto_download FROM image_preferences LIMIT 1
            """)).fetchone()

            if result:
                return JSONResponse({
                    "success": True,
                    "save_local": result.save_local or False,
                    "auto_download": result.auto_download or False
                })
            else:
                return JSONResponse({
                    "success": True,
                    "save_local": False,
                    "auto_download": False
                })
    except Exception as e:
        logger.error(f"Error getting image preferences: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        })


@router.post("/preferences")
async def save_image_preferences(request: Request):
    """Save image caching preferences."""
    try:
        data = await request.json()
        save_local = data.get('save_local', False)
        auto_download = data.get('auto_download', False)

        with get_db_session() as db:
            db.execute(text("""
                INSERT INTO image_preferences (save_local, auto_download)
                VALUES (:save_local, :auto_download)
                ON CONFLICT (singleton_key) DO UPDATE SET
                    save_local = EXCLUDED.save_local,
                    auto_download = EXCLUDED.auto_download,
                    updated_at = NOW()
            """), {
                "save_local": save_local,
                "auto_download": auto_download
            })

            db.commit()

        return JSONResponse({
            "success": True,
            "message_key": "images.preferences_saved"
        })
    except Exception as e:
        logger.error(f"Error saving image preferences: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        })


@router.get("/status")
def get_image_status():
    """Get recipe image status (downloaded count, total, disk usage, failures)."""
    try:
        # Calculate disk usage from files
        total_size_bytes = 0
        file_count = 0

        if os.path.exists(RECIPE_IMAGES_DIR):
            for filename in os.listdir(RECIPE_IMAGES_DIR):
                filepath = os.path.join(RECIPE_IMAGES_DIR, filename)
                if os.path.isfile(filepath):
                    file_count += 1
                    total_size_bytes += os.path.getsize(filepath)

        with get_db_session() as db:
            # Count total recipes (all, regardless of image availability)
            total = db.execute(text("""
                SELECT COUNT(*) FROM found_recipes
            """)).scalar() or 0

            # Count recipes with locally downloaded images
            downloaded = db.execute(text("""
                SELECT COUNT(*) FROM found_recipes
                WHERE local_image_path IS NOT NULL
            """)).scalar() or 0

            # Count failed images
            retrying_count = 0
            permanently_failed = 0
            try:
                retrying_count = db.execute(text("""
                    SELECT COUNT(*) FROM image_download_failures WHERE permanently_failed = FALSE
                """)).scalar() or 0

                permanently_failed = db.execute(text("""
                    SELECT COUNT(*) FROM image_download_failures WHERE permanently_failed = TRUE
                """)).scalar() or 0
            except Exception:
                # Table might not exist yet
                pass

        # Format size
        if total_size_bytes < 1024:
            size_str = f"{total_size_bytes} B"
        elif total_size_bytes < 1024 * 1024:
            size_str = f"{total_size_bytes / 1024:.1f} KB"
        elif total_size_bytes < 1024 * 1024 * 1024:
            size_str = f"{total_size_bytes / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{total_size_bytes / (1024 * 1024 * 1024):.2f} GB"

        return JSONResponse({
            "success": True,
            "downloaded": downloaded,
            "total": total,
            "size": size_str,
            "size_bytes": total_size_bytes,
            "files_on_disk": file_count,
            "retrying_count": retrying_count,
            "permanently_failed": permanently_failed
        })
    except Exception as e:
        logger.error(f"Error getting image status: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        })


# NOTE: image_download_state is imported from state.py

async def _download_images_task(batch_pause: int = IMAGE_BATCH_PAUSE_MANUAL):
    """Background task to download recipe images with safe rate limiting.

    Rate limiting strategy:
    - 1 second delay between each image
    - 15-20 second pause every 50 images
    - Max 3 retries per image with exponential backoff (5s, 15s, 45s)
    - Per-domain 429 tracking: skip domain after 2x 429

    Persistent failure tracking:
    - Records failed attempts in database
    - After 5 total attempts across sessions, marks as permanently failed
    - Permanently failed images are skipped in future downloads

    Args:
        batch_pause: Seconds to pause after every 50 images.
                     - 15s for manual download
                     - 20s for auto-download after scraping
    """
    try:
        from PIL import Image
        PILLOW_AVAILABLE = True
    except ImportError:
        PILLOW_AVAILABLE = False
        logger.warning("Pillow not installed - images will not be compressed")

    global image_download_state

    # Image compression settings
    # Display sizes: cards show images at max ~400x120px (800x240 for retina)
    MAX_IMAGE_WIDTH = 800   # Max width in pixels (covers retina displays)
    MAX_IMAGE_HEIGHT = 400  # Max height in pixels
    TARGET_SIZE_KB = 70     # Target file size in KB
    WEBP_QUALITY = 75       # Starting quality for WebP

    def compress_image(image_data: bytes, target_kb: int = TARGET_SIZE_KB) -> tuple[bytes, str]:
        """
        Compress image to target size using WebP format.
        Returns (compressed_bytes, extension).
        """
        logger.debug(f"[COMPRESS] Called with {len(image_data)} bytes, PILLOW={PILLOW_AVAILABLE}")
        if not PILLOW_AVAILABLE:
            logger.warning("[COMPRESS] Pillow not available!")
            return image_data, '.jpg'  # Return original if Pillow not available

        try:
            img = Image.open(BytesIO(image_data))
            original_size = len(image_data)
            orig_w, orig_h = img.width, img.height
            logger.debug(f"[COMPRESS] Image: {orig_w}x{orig_h}")

            # Convert to RGB if necessary (for PNG with transparency)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

            # Resize if too large (check both width and height)
            if img.width > MAX_IMAGE_WIDTH or img.height > MAX_IMAGE_HEIGHT:
                width_ratio = MAX_IMAGE_WIDTH / img.width
                height_ratio = MAX_IMAGE_HEIGHT / img.height
                ratio = min(width_ratio, height_ratio)
                new_width = int(img.width * ratio)
                new_height = int(img.height * ratio)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.debug(f"Resized {orig_w}x{orig_h} -> {new_width}x{new_height}")

            # Try WebP with decreasing quality until target size reached
            quality = WEBP_QUALITY
            while quality >= 20:
                buffer = BytesIO()
                img.save(buffer, format='WEBP', quality=quality, optimize=True)
                final_size = buffer.tell()
                if final_size <= target_kb * 1024 or quality <= 20:
                    logger.debug(f"Compressed {original_size//1024}KB -> {final_size//1024}KB (q={quality})")
                    return buffer.getvalue(), '.webp'
                quality -= 10

            return buffer.getvalue(), '.webp'

        except Exception as e:
            logger.warning(f"Image compression failed: {e}, using original")
            return image_data, '.jpg'

    # Retry settings
    MAX_RETRIES_PER_SESSION = 3
    RETRY_BACKOFF = [5, 15, 45]  # seconds between retries
    RATE_LIMIT_WAIT = 300  # 5 minutes wait on 429
    MAX_429_PER_DOMAIN = 2  # Skip domain after this many 429s
    MAX_TOTAL_ATTEMPTS = 5  # Mark as permanently failed after this many total attempts
    MAX_IMAGE_SIZE = 30 * 1024 * 1024  # 30 MB - reject oversized responses

    def get_url_hash(url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def get_file_extension(url: str) -> str:
        url_lower = url.lower()
        if '.png' in url_lower:
            return '.png'
        elif '.webp' in url_lower:
            return '.webp'
        elif '.gif' in url_lower:
            return '.gif'
        return '.jpg'

    async def record_failure(db, recipe_id: int, image_url: str, url_hash: str, error: str):
        """Record or update a failure in the database."""
        try:
            # Check if record exists
            existing = db.execute(text("""
                SELECT id, attempt_count FROM image_download_failures
                WHERE recipe_id = :recipe_id AND image_url_hash = :hash
            """), {"recipe_id": recipe_id, "hash": url_hash}).fetchone()

            if existing:
                new_count = existing.attempt_count + 1
                permanently_failed = new_count >= MAX_TOTAL_ATTEMPTS
                db.execute(text("""
                    UPDATE image_download_failures
                    SET attempt_count = :count, last_attempt = CURRENT_TIMESTAMP,
                        last_error = :error, permanently_failed = :permanent
                    WHERE id = :id
                """), {
                    "count": new_count,
                    "error": error,
                    "permanent": permanently_failed,
                    "id": existing.id
                })
                if permanently_failed:
                    logger.warning(f"Image permanently failed after {new_count} attempts: {image_url[:80]}")
            else:
                db.execute(text("""
                    INSERT INTO image_download_failures
                    (recipe_id, image_url, image_url_hash, attempt_count, last_error)
                    VALUES (:recipe_id, :url, :hash, 1, :error)
                """), {
                    "recipe_id": recipe_id,
                    "url": image_url,
                    "hash": url_hash,
                    "error": error
                })
            db.commit()
        except Exception as e:
            logger.error(f"Failed to record image failure: {e}")

    async def clear_failure(db, recipe_id: int, url_hash: str):
        """Remove failure record on successful download."""
        try:
            db.execute(text("""
                DELETE FROM image_download_failures
                WHERE recipe_id = :recipe_id AND image_url_hash = :hash
            """), {"recipe_id": recipe_id, "hash": url_hash})
            db.commit()
        except Exception as e:
            logger.error(f"Failed to clear image failure: {e}")

    def set_message(key: str, params: dict = None):
        """Helper to set i18n message key and params."""
        image_download_state["message_key"] = key
        image_download_state["message_params"] = params or {}

    try:
        image_download_state["status"] = "running"
        image_download_state["batch_pause"] = batch_pause
        set_message("config.images_progress_analyzing")

        with get_db_session() as db:
            # Get all recipes with images
            result = db.execute(text("""
                SELECT id, image_url FROM found_recipes
                WHERE image_url IS NOT NULL AND image_url != ''
            """)).fetchall()

            # Get permanently failed images to skip
            permanently_failed = set()
            try:
                failed_rows = db.execute(text("""
                    SELECT image_url_hash FROM image_download_failures
                    WHERE permanently_failed = TRUE
                """)).fetchall()
                permanently_failed = {row.image_url_hash for row in failed_rows}
            except Exception as e:
                logger.warning(f"Could not load permanently failed images (table may not exist): {e}")

            # Pre-filter: only include images that need downloading
            images_to_download = []
            already_local = 0
            skipped_permanent = 0

            for row in result:
                # Decode HTML entities (e.g., &amp; -> &) in URLs
                image_url = html.unescape(row.image_url)

                # Skip if URL is already local
                if image_url.startswith('/static/'):
                    already_local += 1
                    continue

                url_hash = get_url_hash(image_url)

                # Skip if permanently failed
                if url_hash in permanently_failed:
                    skipped_permanent += 1
                    continue

                # Check for existing file (any common extension)
                found_existing = False
                existing_ext = None
                for ext in ['.webp', '.jpg', '.jpeg', '.png', '.gif']:
                    check_path = os.path.join(RECIPE_IMAGES_DIR, f"{url_hash}{ext}")
                    if os.path.exists(check_path):
                        found_existing = True
                        existing_ext = ext
                        break

                if found_existing:
                    already_local += 1
                    # Update database if local_image_path isn't set (handles duplicate URLs)
                    local_path = f"/static/recipe_images/{url_hash}{existing_ext}"
                    db.execute(text("""
                        UPDATE found_recipes
                        SET local_image_path = :local_path
                        WHERE id = :recipe_id AND (local_image_path IS NULL OR local_image_path = '')
                    """), {"local_path": local_path, "recipe_id": row.id})
                    continue

                # Will be saved as .webp after compression
                filepath = os.path.join(RECIPE_IMAGES_DIR, f"{url_hash}.webp")
                images_to_download.append((row.id, image_url, url_hash, filepath))

            # Set no_image.svg for recipes without any image_url
            no_image_count = db.execute(text("""
                UPDATE found_recipes
                SET local_image_path = '/static/no_image.svg'
                WHERE (image_url IS NULL OR image_url = '')
                  AND (local_image_path IS NULL OR local_image_path = '')
            """)).rowcount
            if no_image_count:
                logger.info(f"Set no_image.svg for {no_image_count} recipes without source image")

            # Commit any local_image_path updates from pre-filter
            if already_local > 0 or no_image_count:
                db.commit()

        # Group URLs by domain to track rate limiting per site
        domain_counts = defaultdict(int)
        for _, url, _, _ in images_to_download:
            try:
                domain = urlparse(url).netloc
                domain_counts[domain] += 1
            except (ValueError, AttributeError):
                # Invalid URL format
                pass

        logger.info(f"Image download: {len(images_to_download)} to download, {already_local} already local, {skipped_permanent} permanently failed")
        logger.info(f"  Rate: {IMAGE_DELAY_PER_IMAGE}s/image + {batch_pause}s pause every {IMAGE_BATCH_SIZE} images")
        logger.info(f"  Retry: {MAX_RETRIES_PER_SESSION} attempts/image, {RATE_LIMIT_WAIT}s on 429, skip domain after {MAX_429_PER_DOMAIN}x 429")
        for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1])[:5]:
            logger.info(f"  - {domain}: {count} images")

        image_download_state["total"] = len(images_to_download)
        image_download_state["skipped"] = already_local
        image_download_state["permanently_failed"] = skipped_permanent

        if len(images_to_download) == 0:
            image_download_state["status"] = "complete"
            if skipped_permanent > 0:
                set_message("config.images_progress_all_done_failed", {"count": skipped_permanent})
            else:
                set_message("config.images_progress_all_done", {"count": already_local})
            _prune_recipe_image_orphans_after_download()
            return

        # Calculate estimated time
        num_batches = len(images_to_download) // IMAGE_BATCH_SIZE
        estimated_seconds = len(images_to_download) * IMAGE_DELAY_PER_IMAGE + num_batches * batch_pause
        if estimated_seconds >= 3600:
            eta_str = f"{estimated_seconds / 3600:.1f}h"
        else:
            eta_str = f"{int(estimated_seconds / 60)}min"
        set_message("config.images_progress_downloading", {"total": len(images_to_download), "eta": eta_str})

        # Track 429s per domain during this session
        domain_429_count = defaultdict(int)
        blocked_domains = set()

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True, event_hooks={"request": [ssrf_safe_event_hook]}) as client:
            with get_db_session() as db:
                for i, (recipe_id, image_url, url_hash, filepath) in enumerate(images_to_download):
                    if not image_download_state["running"]:
                        image_download_state["status"] = "cancelled"
                        set_message("config.images_progress_cancelled")
                        return

                    image_download_state["processed"] = i + 1

                    # Batch pause every 50 images (except first batch)
                    if i > 0 and i % IMAGE_BATCH_SIZE == 0:
                        logger.info(f"Image download: batch {i // IMAGE_BATCH_SIZE} complete, pausing {batch_pause}s...")
                        set_message("config.images_progress_batch_pause", {"count": i, "seconds": batch_pause})
                        await asyncio.sleep(batch_pause)

                    # Update progress message
                    if i % 10 == 0:
                        remaining = len(images_to_download) - i
                        remaining_batches = remaining // IMAGE_BATCH_SIZE
                        eta_seconds = remaining * IMAGE_DELAY_PER_IMAGE + remaining_batches * batch_pause
                        if eta_seconds >= 3600:
                            eta_str = f"{eta_seconds / 3600:.1f}h"
                        else:
                            eta_str = f"{int(eta_seconds // 60)}min"
                        set_message("config.images_progress_current", {
                            "current": i + 1,
                            "total": len(images_to_download),
                            "eta": eta_str
                        })

                    # SSRF protection: reject internal/private URLs
                    if not is_safe_url(image_url):
                        image_download_state["skipped"] += 1
                        logger.warning(f"SSRF blocked: {image_url}")
                        await record_failure(db, recipe_id, image_url, url_hash, "Blocked: URL resolves to non-public address")
                        continue

                    # Check if domain is blocked
                    try:
                        domain = urlparse(image_url).netloc
                    except (ValueError, AttributeError):
                        domain = "unknown"

                    if domain in blocked_domains:
                        image_download_state["skipped"] += 1
                        await record_failure(db, recipe_id, image_url, url_hash, f"Domain {domain} blocked due to rate limiting")
                        continue

                    # Retry loop for this image
                    success = False
                    last_error = ""

                    for attempt in range(MAX_RETRIES_PER_SESSION):
                        try:
                            response = await client.get(image_url)

                            if response.status_code == 200:
                                # Reject oversized responses
                                if len(response.content) > MAX_IMAGE_SIZE:
                                    last_error = f"Image too large ({len(response.content) // 1024 // 1024} MB)"
                                    logger.warning(f"Skipping {image_url}: {last_error}")
                                    break

                                # Compress the image before saving
                                compressed_data, ext = compress_image(response.content)
                                with open(filepath, 'wb') as f:
                                    f.write(compressed_data)

                                # Update database with local image path
                                local_path = f"/static/recipe_images/{url_hash}.webp"
                                db.execute(text("""
                                    UPDATE found_recipes
                                    SET local_image_path = :local_path
                                    WHERE id = :recipe_id
                                """), {"local_path": local_path, "recipe_id": recipe_id})
                                db.commit()

                                image_download_state["downloaded"] += 1
                                await clear_failure(db, recipe_id, url_hash)
                                success = True
                                break

                            elif response.status_code == 429:
                                domain_429_count[domain] += 1
                                if domain_429_count[domain] >= MAX_429_PER_DOMAIN:
                                    logger.warning(f"Domain {domain} blocked after {MAX_429_PER_DOMAIN}x 429")
                                    blocked_domains.add(domain)
                                    last_error = "429 Rate Limited (domain blocked)"
                                    break
                                else:
                                    logger.warning(f"Rate limited (429) on {domain}, waiting {RATE_LIMIT_WAIT}s ({domain_429_count[domain]}/{MAX_429_PER_DOMAIN})...")
                                    set_message("config.images_progress_rate_limited", {
                                        "domain": domain,
                                        "minutes": RATE_LIMIT_WAIT // 60
                                    })
                                    await asyncio.sleep(RATE_LIMIT_WAIT)
                                    last_error = "429 Rate Limited"

                            elif response.status_code == 404:
                                last_error = "404 Not Found"
                                break  # No point retrying 404

                            else:
                                last_error = f"HTTP {response.status_code}"
                                if attempt < MAX_RETRIES_PER_SESSION - 1:
                                    await asyncio.sleep(RETRY_BACKOFF[attempt])

                        except httpx.TimeoutException:
                            last_error = "Timeout"
                            if attempt < MAX_RETRIES_PER_SESSION - 1:
                                await asyncio.sleep(RETRY_BACKOFF[attempt])

                        except Exception as e:
                            last_error = str(e)[:100]
                            if attempt < MAX_RETRIES_PER_SESSION - 1:
                                await asyncio.sleep(RETRY_BACKOFF[attempt])

                    if not success:
                        image_download_state["errors"] += 1
                        await record_failure(db, recipe_id, image_url, url_hash, last_error)

                    # Rate limiting delay after each image
                    await asyncio.sleep(IMAGE_DELAY_PER_IMAGE)

        # Final status message
        image_download_state["status"] = "complete"
        downloaded = image_download_state['downloaded']
        errors = image_download_state["errors"]
        blocked = len(blocked_domains)

        if errors > 0 and blocked > 0:
            set_message("config.images_progress_complete_errors", {"downloaded": downloaded, "errors": errors})
        elif blocked > 0:
            set_message("config.images_progress_complete_blocked", {"downloaded": downloaded, "blocked": blocked})
        elif errors > 0:
            set_message("config.images_progress_complete_errors", {"downloaded": downloaded, "errors": errors})
        else:
            set_message("config.images_progress_complete", {"downloaded": downloaded})

        _prune_recipe_image_orphans_after_download()

    except Exception as e:
        logger.error(f"Error in download task: {e}")
        image_download_state["status"] = "error"
        # Error messages are kept as-is (technical, not translated)
        image_download_state["message_key"] = "error"
        image_download_state["message_params"] = {"error": friendly_error(e)}
    finally:
        image_download_state["running"] = False


@router.post("/download")
@limiter.limit(settings.rate_limit_image_download)
async def start_image_download(request: Request):
    """Start downloading missing recipe images (background task).

    Rate limiting (safe mode):
    - 1s delay between each image
    - 15 min pause every 100 images (manual) or 20 min (auto)
    - Total ~3-4 hours for 1000 images

    Body params:
        mode: "manual" (default) or "auto" (triggered after scraping, extra cautious)
    """
    # Get mode from request body or use default
    try:
        data = await request.json()
        mode = data.get('mode', 'manual')
    except Exception:
        mode = 'manual'

    # Select batch pause based on mode
    if mode == 'auto':
        batch_pause = IMAGE_BATCH_PAUSE_AUTO  # 20 min - extra safe after scraping
    else:
        batch_pause = IMAGE_BATCH_PAUSE_MANUAL  # 15 min - safe manual download

    # Atomically check if idle and start — prevents duplicate tasks on double-click
    started = await try_start_image_download({
        "running": True,
        "total": 0,
        "processed": 0,
        "downloaded": 0,
        "skipped": 0,
        "errors": 0,
        "status": "running",
        "message_key": "config.images_starting",
        "message_params": {},
        "batch_pause": batch_pause
    })
    if not started:
        return JSONResponse({
            "success": False,
            "message_key": "images.download_already_running"
        }, status_code=409)

    # Start background task with appropriate batch pause.
    # Store reference to prevent garbage collection before task starts.
    global _active_download_task
    _active_download_task = asyncio.create_task(
        _download_images_task(batch_pause=batch_pause),
        name="image_download"
    )

    return JSONResponse({
        "success": True,
        "message_key": "images.download_started",
        "mode": mode,
        "delay_per_image": IMAGE_DELAY_PER_IMAGE,
        "batch_pause_seconds": batch_pause
    })


@router.get("/download/status")
async def get_download_status():
    """Get current image download progress."""
    state = await get_image_state()
    progress = 0
    eta_minutes = 0
    if state["total"] > 0:
        progress = int((state["processed"] / state["total"]) * 100)
        remaining = state["total"] - state["processed"]
        batch_pause = state.get("batch_pause", IMAGE_BATCH_PAUSE_MANUAL)
        remaining_batches = remaining // IMAGE_BATCH_SIZE
        eta_seconds = remaining * IMAGE_DELAY_PER_IMAGE + remaining_batches * batch_pause
        eta_minutes = int(eta_seconds / 60)

    return JSONResponse({
        "success": True,
        "running": state["running"],
        "status": state["status"],
        "message_key": state["message_key"],
        "message_params": state["message_params"],
        "total": state["total"],
        "processed": state["processed"],
        "downloaded": state["downloaded"],
        "skipped": state["skipped"],
        "errors": state["errors"],
        "progress": progress,
        "eta_minutes": eta_minutes,
        "delay_per_image": IMAGE_DELAY_PER_IMAGE,
        "batch_pause": state.get("batch_pause", IMAGE_BATCH_PAUSE_MANUAL)
    })


@router.post("/download/cancel")
async def cancel_image_download():
    """Cancel ongoing image download."""
    state = await get_image_state()
    if not state["running"]:
        return JSONResponse({
            "success": False,
            "message_key": "images.no_download_running"
        })

    await update_image_state(running=False)
    return JSONResponse({
        "success": True,
        "message_key": "images.download_cancelling"
    })


@router.post("/clear")
def clear_all_images():
    """Delete all locally cached recipe images."""
    try:
        deleted_count = 0

        if os.path.exists(RECIPE_IMAGES_DIR):
            for filename in os.listdir(RECIPE_IMAGES_DIR):
                filepath = os.path.join(RECIPE_IMAGES_DIR, filename)
                if os.path.isfile(filepath):
                    os.remove(filepath)
                    deleted_count += 1

        # Clear local_image_path in DB so frontend doesn't reference deleted files
        with get_db_session() as db:
            db.execute(text("""
                UPDATE found_recipes SET local_image_path = NULL
                WHERE local_image_path IS NOT NULL
            """))
            db.commit()

        return JSONResponse({
            "success": True,
            "deleted": deleted_count,
            "message_key": "images.deleted_count",
            "message_params": {"count": deleted_count}
        })
    except Exception as e:
        logger.error(f"Error clearing images: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        })


@router.get("/failures")
def get_image_failures():
    """Get list of recipes with permanently failed image downloads."""
    try:
        with get_db_session() as db:
            # Get failure records with recipe info
            result = db.execute(text("""
                SELECT
                    f.id as failure_id,
                    f.recipe_id,
                    f.image_url,
                    f.attempt_count,
                    f.last_attempt,
                    f.last_error,
                    f.permanently_failed,
                    r.name as recipe_name,
                    r.source_name as recipe_source
                FROM image_download_failures f
                JOIN found_recipes r ON f.recipe_id = r.id
                ORDER BY f.permanently_failed DESC, f.attempt_count DESC, f.last_attempt DESC
            """)).fetchall()

            failures = []
            for row in result:
                failures.append({
                    "failure_id": row.failure_id,
                    "recipe_id": str(row.recipe_id),  # Convert UUID to string
                    "recipe_name": row.recipe_name,
                    "recipe_source": row.recipe_source,
                    "image_url": row.image_url,
                    "attempt_count": row.attempt_count,
                    "last_attempt": row.last_attempt.isoformat() if row.last_attempt else None,
                    "last_error": row.last_error,
                    "permanently_failed": row.permanently_failed
                })

            permanent_count = sum(1 for f in failures if f["permanently_failed"])

            return JSONResponse({
                "success": True,
                "failures": failures,
                "total": len(failures),
                "permanent_count": permanent_count
            })

    except Exception as e:
        logger.error(f"Error getting image failures: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e),
            "failures": []
        })


@router.delete("/failures/{recipe_id}")
def delete_recipe_with_failed_image(recipe_id: str):
    """Delete a recipe that has a failed image download.
    The failure record is automatically deleted via CASCADE.
    """
    if not is_valid_uuid(recipe_id):
        return JSONResponse({"success": False, "message_key": "error.invalid_data"}, status_code=400)
    try:
        with get_db_session() as db:
            # Get recipe details for confirmation and safe local image cleanup.
            recipe = db.execute(text(
                "SELECT name, local_image_path FROM found_recipes WHERE id = :id"
            ), {"id": recipe_id}).fetchone()

            if not recipe:
                return JSONResponse({
                    "success": False,
                    "message_key": "images.recipe_not_found",
                    "message_params": {"id": str(recipe_id)}
                }, status_code=404)

            recipe_name = recipe.name
            local_image = recipe.local_image_path

            # Delete recipe (cascade will delete failure record)
            db.execute(text("DELETE FROM found_recipes WHERE id = :id"), {"id": recipe_id})
            db.commit()

            image_cleanup = delete_unreferenced_recipe_image_file(
                local_image,
                reason="failed_image_recipe_delete",
            )

            return JSONResponse({
                "success": True,
                "message_key": "images.recipe_deleted",
                "message_params": {"name": recipe_name},
                "image_deleted": image_cleanup["deleted_count"] > 0,
            })

    except Exception as e:
        logger.error(f"Error deleting recipe {recipe_id}: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        })


@router.delete("/failures")
def delete_all_recipes_with_failed_images():
    """Delete all recipes that have permanently failed image downloads."""
    try:
        with get_db_session() as db:
            # Get count of permanently failed
            count_result = db.execute(text("""
                SELECT COUNT(*) as count FROM image_download_failures
                WHERE permanently_failed = TRUE
            """)).fetchone()
            count = count_result.count if count_result else 0

            if count == 0:
                return JSONResponse({
                    "success": True,
                    "deleted": 0,
                    "message_key": "images.no_failed_to_delete"
                })

            image_paths = db.execute(text("""
                SELECT local_image_path
                FROM found_recipes
                WHERE id IN (
                    SELECT recipe_id FROM image_download_failures
                    WHERE permanently_failed = TRUE
                )
                  AND local_image_path IS NOT NULL
                  AND local_image_path != ''
            """)).scalars().all()

            # Delete all recipes with permanently failed images
            db.execute(text("""
                DELETE FROM found_recipes
                WHERE id IN (
                    SELECT recipe_id FROM image_download_failures
                    WHERE permanently_failed = TRUE
                )
            """))
            db.commit()

            image_cleanup = delete_unreferenced_recipe_image_files(
                image_paths,
                reason="failed_image_recipes_delete",
            )

            return JSONResponse({
                "success": True,
                "deleted": count,
                "message_key": "images.deleted_failed_count",
                "message_params": {"count": count},
                "images_deleted": image_cleanup["deleted_count"],
            })

    except Exception as e:
        logger.error(f"Error deleting recipes with failed images: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        })


@router.post("/failures/{recipe_id}/reset")
def reset_failure_attempts(recipe_id: str):
    """Reset the attempt count for a failed image, allowing retry."""
    if not is_valid_uuid(recipe_id):
        return JSONResponse({"success": False, "message_key": "error.invalid_data"}, status_code=400)
    try:
        with get_db_session() as db:
            result = db.execute(text("""
                UPDATE image_download_failures
                SET attempt_count = 0, permanently_failed = FALSE
                WHERE recipe_id = :recipe_id
            """), {"recipe_id": recipe_id})
            db.commit()

            if result.rowcount == 0:
                return JSONResponse({
                    "success": False,
                    "message_key": "images.no_failure_record"
                }, status_code=404)

            return JSONResponse({
                "success": True,
                "message_key": "images.failure_reset"
            })

    except Exception as e:
        logger.error(f"Error resetting failure for recipe {recipe_id}: {e}")
        return JSONResponse({
            "success": False,
            "message_key": friendly_error(e)
        })
