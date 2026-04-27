"""UK scaffold wrapper for seasonal recipe filters."""

try:
    from languages.sv.ingredient_matching.seasonal import *  # noqa: F401,F403
except ModuleNotFoundError:
    from app.languages.sv.ingredient_matching.seasonal import *  # noqa: F401,F403
