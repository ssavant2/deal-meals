#!/usr/bin/env python3
"""Minimal frontend browser smoke for the main pages.

Run:
    docker compose exec -T -w /app web python tests/run_frontend_smoke.py

This intentionally uses Python Playwright from the web image and does not
introduce Node, pytest, a bundler, or a frontend lint toolchain.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import ssl
import sys
import urllib.error
import urllib.request


def _reexec_as_appuser_if_needed() -> None:
    """Use the image's Playwright browser cache, which is installed for appuser."""
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return

    gosu = shutil.which("gosu")
    if not gosu:
        return

    env = dict(os.environ)
    env["HOME"] = "/home/appuser"
    os.execvpe(gosu, [gosu, "appuser", sys.executable, *sys.argv], env)


_reexec_as_appuser_if_needed()

from playwright.async_api import TimeoutError as PlaywrightTimeout  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402


PAGE_CHECKS = [
    {
        "name": "home",
        "path": "/",
        "ready": "#quick-actions-row",
        "actions": [
            ("click_force", "#btn-search"),
            ("wait_visible", "#search-section"),
            ("assert_unique_options", "#search-source-filter"),
            ("click_force", "#btn-search"),
        ],
    },
    {
        "name": "stores",
        "path": "/stores",
        "ready": "#store-schedule-select",
        "actions": [
            ("select", "#store-schedule-frequency", "weekly"),
            ("wait_visible", "#store-day-of-week-container"),
            ("select", "#store-schedule-frequency", "daily"),
        ],
    },
    {
        "name": "recipes",
        "path": "/recipes",
        "ready": "#fetch-section",
        "actions": [
            ("select", "#schedule-frequency", "weekly"),
            ("wait_visible", "#day-of-week-container"),
            ("select", "#schedule-frequency", "daily"),
        ],
    },
    {
        "name": "config",
        "path": "/config",
        "ready": "#images-failed-btn",
        "actions": [
            ("click", '[data-action="showExcludedUrlsModal"]'),
            ("wait_visible", "#excludedUrlsModal"),
            ("click", '#excludedUrlsModal [data-bs-dismiss="modal"]'),
            ("wait_hidden", "#excludedUrlsModal"),
        ],
    },
]

VIEWPORTS = [
    ("desktop", {"width": 1366, "height": 900}),
    ("mobile", {"width": 390, "height": 844}),
]

BROWSER_ARGS = [
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-gpu",
]


def _candidate_base_urls() -> list[str]:
    configured = os.environ.get("FRONTEND_SMOKE_BASE_URL", "").strip()
    if configured:
        return [configured.rstrip("/")]

    port = os.environ.get("APP_PORT", "20080")
    return [
        f"https://localhost:{port}",
        f"http://localhost:{port}",
    ]


def _can_reach(base_url: str) -> bool:
    context = None
    if base_url.startswith("https://"):
        context = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(
            f"{base_url}/health",
            timeout=5,
            context=context,
        ) as response:
            return 200 <= response.status < 500
    except (OSError, urllib.error.URLError, ssl.SSLError):
        return False


def _resolve_base_url() -> str:
    for base_url in _candidate_base_urls():
        if _can_reach(base_url):
            return base_url

    candidates = ", ".join(_candidate_base_urls())
    raise RuntimeError(
        "Could not reach Deal Meals for frontend smoke. Tried: "
        f"{candidates}. Set FRONTEND_SMOKE_BASE_URL if needed."
    )


async def _run_action(page, action: tuple) -> None:
    kind = action[0]
    selector = action[1]

    if kind == "click":
        await page.locator(selector).first.click()
        return

    if kind == "click_force":
        await page.locator(selector).first.click(force=True)
        return

    if kind == "select":
        value = action[2]
        await page.locator(selector).first.select_option(value)
        return

    if kind == "wait_visible":
        await page.locator(selector).first.wait_for(state="visible")
        return

    if kind == "wait_hidden":
        await page.locator(selector).first.wait_for(state="hidden")
        return

    if kind == "assert_unique_options":
        values = await page.locator(f"{selector} option").evaluate_all(
            "(options) => options.map((option) => option.value).filter(Boolean)"
        )
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            raise AssertionError(
                f"{selector} has duplicate option values: {', '.join(duplicates)}"
            )
        return

    raise ValueError(f"Unknown smoke action: {kind}")


async def _check_page(context, base_url: str, viewport_name: str, page_check: dict) -> list[str]:
    page = await context.new_page()
    page.set_default_timeout(10_000)
    errors: list[str] = []
    label = f"{viewport_name}:{page_check['name']}"

    page.on("pageerror", lambda exc: errors.append(f"{label} pageerror: {exc}"))
    page.on(
        "console",
        lambda msg: errors.append(f"{label} console.error: {msg.text}")
        if msg.type == "error"
        else None,
    )

    try:
        await page.goto(f"{base_url}{page_check['path']}", wait_until="domcontentloaded")
        await page.locator(page_check["ready"]).first.wait_for(state="visible")

        for action in page_check["actions"]:
            await _run_action(page, action)

        await page.wait_for_timeout(300)
    except PlaywrightTimeout as exc:
        errors.append(f"{label} timeout: {exc}")
    except Exception as exc:
        errors.append(f"{label} failed: {type(exc).__name__}: {exc}")
    finally:
        await page.close()

    return errors


async def main() -> int:
    base_url = _resolve_base_url()
    print(f"Frontend smoke base URL: {base_url}", flush=True)

    all_errors: list[str] = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=BROWSER_ARGS)
        try:
            for viewport_name, viewport in VIEWPORTS:
                print(f"\n--- {viewport_name} ---", flush=True)
                context = await browser.new_context(
                    ignore_https_errors=True,
                    viewport=viewport,
                )
                try:
                    for page_check in PAGE_CHECKS:
                        print(f"checking {page_check['path']}", flush=True)
                        all_errors.extend(
                            await _check_page(context, base_url, viewport_name, page_check)
                        )
                finally:
                    await context.close()
        finally:
            await browser.close()

    print("\n========================================", flush=True)
    if all_errors:
        print("FRONTEND SMOKE FAILED", flush=True)
        for error in all_errors:
            print(f"- {error}", flush=True)
        print("========================================", flush=True)
        return 1

    total = len(PAGE_CHECKS) * len(VIEWPORTS)
    print(f"FRONTEND SMOKE PASSED ({total} page/viewport checks)", flush=True)
    print("========================================", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"FRONTEND SMOKE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
