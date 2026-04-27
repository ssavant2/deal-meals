"""
Cross-platform Playwright cleanup utilities.

Works on Linux, Windows, macOS - both in Docker and native.
Use this module in all scrapers for automatic cleanup.
"""

import subprocess
import sys
import glob
import shutil
from pathlib import Path
from loguru import logger


def cleanup_chrome_processes() -> bool:
    """
    Kill all Chrome/Chromium processes.

    Platform-agnostic - works on:
    - Linux (pkill)
    - Windows (taskkill)
    - macOS (pkill)
    - Docker containers (pkill)

    Returns:
        True if cleanup succeeded or was not needed
    """
    try:
        if sys.platform == "win32":
            # Native Windows (rare, usually Docker)
            subprocess.run(
                ["taskkill", "/F", "/IM", "chrome.exe"],
                capture_output=True,
                check=False
            )
            subprocess.run(
                ["taskkill", "/F", "/IM", "chromium.exe"],
                capture_output=True,
                check=False
            )
            logger.debug("Used taskkill (Windows)")
        else:
            # Linux/macOS/Docker containers
            subprocess.run(
                ["pkill", "-9", "chrome"],
                capture_output=True,
                check=False
            )
            subprocess.run(
                ["pkill", "-9", "chromium"],
                capture_output=True,
                check=False
            )
            logger.debug("Used pkill (Linux/macOS/Docker)")

        return True

    except Exception as e:
        logger.warning(f"Could not kill Chrome processes: {e}")
        return False


def cleanup_playwright_temp() -> bool:
    """
    Delete Playwright temp files.

    Platform-agnostic via Python's stdlib.

    Returns:
        True if cleanup succeeded or was not needed
    """
    try:
        # /tmp on Linux/macOS, %TEMP% on Windows
        if sys.platform == "win32":
            import tempfile
            temp_base = Path(tempfile.gettempdir())
        else:
            temp_base = Path("/tmp")

        # Find all playwright temp directories
        pattern = str(temp_base / "playwright_*")
        temp_dirs = glob.glob(pattern)

        removed = 0
        for temp_dir in temp_dirs:
            try:
                shutil.rmtree(temp_dir)
                removed += 1
            except Exception as e:
                logger.debug(f"Could not delete {temp_dir}: {e}")

        if removed > 0:
            logger.debug(f"Deleted {removed} Playwright temp directories")

        return True

    except Exception as e:
        logger.warning(f"Could not delete temp files: {e}")
        return False


def full_cleanup(silent: bool = False) -> bool:
    """
    Complete cleanup of Chrome + temp files.

    Call this at the end of all scrapers.

    Args:
        silent: If True, only log errors (no info/success)

    Returns:
        True if cleanup fully or partially succeeded
    """
    if not silent:
        logger.info("Cleaning up after Playwright...")

    chrome_ok = cleanup_chrome_processes()
    temp_ok = cleanup_playwright_temp()

    if chrome_ok and temp_ok:
        if not silent:
            logger.success("Cleanup complete!")
        return True
    else:
        if not silent:
            logger.warning("Cleanup partially failed (not critical)")
        return False


# Convenience alias
cleanup = full_cleanup


if __name__ == "__main__":
    # Can be run standalone for manual cleanup
    print("Running manual Playwright cleanup...")
    success = full_cleanup(silent=False)
    sys.exit(0 if success else 1)
