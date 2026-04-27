#!/usr/bin/env python3
"""
Dev reload — hot-reload matching code and rebuild cache without restarting.

Usage:
    docker compose exec -T web python tests/dev_reload.py

Rebuilds the cache through the normal cache manager path in the running dev
container.
"""

import importlib
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import languages.sv.normalization as norm
importlib.reload(norm)

import languages.sv.ingredient_matching as im
importlib.reload(im)

import recipe_matcher as rm
importlib.reload(rm)

from cache_manager import cache_manager
cache_manager.matcher = rm.RecipeMatcher()

start = time.time()
result = cache_manager.compute_cache()
print(f"Done in {time.time()-start:.0f}s: {result}")
