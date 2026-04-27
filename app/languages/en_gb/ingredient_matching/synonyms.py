"""UK scaffold wrapper for ingredient parent mappings."""

try:
    from languages.sv.ingredient_matching.synonyms import *  # noqa: F401,F403
except ModuleNotFoundError:
    from app.languages.sv.ingredient_matching.synonyms import *  # noqa: F401,F403
