"""UK scaffold wrapper for recipe text helpers."""

try:
    from languages.sv.ingredient_matching.recipe_text import *  # noqa: F401,F403
except ModuleNotFoundError:
    from app.languages.sv.ingredient_matching.recipe_text import *  # noqa: F401,F403
