#!/usr/bin/env python3
"""
High-resource cache rebuild — for batch review runs and other situations where
extra CPU and RAM are available.

Use this instead of dev_reload.py when running with elevated container resources.
It passes a higher worker count directly to compute_cache(), bypassing the
conservative default set for the normal 1.5GB dev container.

REQUIRES elevated resources — run as a separate container, not exec into the
live web container:

    docker compose run --rm -w /app \
        --memory=12g --cpus=8 \
        web python support_checks/dev_reload_high_resources.py

Or temporarily raise DEV_WEB_MEM_LIMIT in .env and restart:
    DEV_WEB_MEM_LIMIT=12g  (in .env)
    docker compose up -d web
    docker compose exec -T -w /app web python support_checks/dev_reload_high_resources.py

Workers selected automatically from available CPU cores (cores - 2, min 4, max 12).
Override with --workers N.

Benchmark (3 workers, 4 cores, 1.5GB): ~320s for 14 500 recipes.
Expected (8 workers, 8 cores, 12GB):   ~120s.
Expected (12 workers, 16 cores, 16GB):  ~80s.
"""

import importlib
import multiprocessing
import time
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

parser = argparse.ArgumentParser(description="High-resource cache rebuild")
parser.add_argument(
    "--workers", type=int, default=None,
    help="Number of parallel workers. Default: cpu_count - 2, capped at 12.",
)
args = parser.parse_args()

if args.workers is not None:
    workers = max(1, args.workers)
else:
    cpu_count = multiprocessing.cpu_count()
    workers = max(4, min(12, cpu_count - 2))

print(f"High-resource rebuild: {workers} workers (machine has {multiprocessing.cpu_count()} CPUs)")
print("Reloading matcher modules...", flush=True)

import languages.sv.normalization as norm
importlib.reload(norm)

import languages.sv.ingredient_matching as im
importlib.reload(im)

import recipe_matcher as rm
importlib.reload(rm)

from cache_manager import cache_manager
cache_manager.matcher = rm.RecipeMatcher()

print(f"Starting rebuild with {workers} workers...", flush=True)
start = time.time()
result = cache_manager.compute_cache(max_workers=workers)
elapsed = time.time() - start
print(f"Done in {elapsed:.0f}s ({elapsed/60:.1f} min): {result}")
