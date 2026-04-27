# Testing

Deal Meals keeps two different kinds of local checks:

- **Tracked app-support checks** live in `app/tests/run_*_checks.py`. These are
  small, deterministic scripts that support the app itself and can be run in the
  normal web container without pytest.
- **Private/dev workbench tests** live in ignored files such as
  `app/tests/test_*.py`, live scraper scripts, cache benchmark fixtures, and
  batch-review notes. These are useful during local development but are not part
  of the public support surface.

## Sanity Check

Run this first after touching matching, store plugin discovery, or startup
registry cleanup:

```bash
docker compose exec -T -w /app web python tests/run_sanity_checks.py
```

The sanity check covers:

- a few high-value Swedish ingredient matching false-positive/true-positive
  cases
- parity between pair-level audit matching, full recipe matching, and cached
  recipe matching
- store plugin discovery import/initialization errors
- fail-safe store registry startup cleanup when plugin discovery fails

It does not scrape websites, use live product data, or require a database.

## App Support Checks

Run the tracked support suite with:

```bash
docker compose exec -T -w /app web python tests/run_app_support_checks.py
```

This runs the sanity check plus the tracked helper checks for candidate routing,
ingredient term maps, shadow candidate selection, ingredient-routing probation,
delta verification policy, and the minimal frontend smoke.

The frontend smoke can also be run directly:

```bash
docker compose exec -T -w /app web python tests/run_frontend_smoke.py
```

It opens the four main pages in Chromium at desktop and mobile viewport sizes,
captures `pageerror`/`console.error`, and performs a few safe UI interactions. It
uses Python Playwright from the web image; no Node toolchain is required.

## Local Workbench Tests

Files matching `app/tests/test_*.py` are intentionally ignored. Keep using them
for broader local regression work, pytest experiments, live-data investigations,
and one-off review fixtures. If a check becomes part of the app's public support
surface, move or copy the small deterministic part into a `run_*_checks.py`
script instead of publishing the whole workbench test.
