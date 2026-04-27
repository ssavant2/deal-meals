"""UK scaffold wrapper for matcher space-normalization hooks."""

try:
    from languages.sv.ingredient_matching.normalization import *  # noqa: F401,F403
    from languages.sv.ingredient_matching.normalization import (
        _SPACE_NORM_LOOKUP,
        _SPACE_NORM_PATTERN,
        _SPACE_NORMALIZATIONS,
        _apply_space_normalizations,
    )
except ModuleNotFoundError:
    from app.languages.sv.ingredient_matching.normalization import *  # noqa: F401,F403
    from app.languages.sv.ingredient_matching.normalization import (
        _SPACE_NORM_LOOKUP,
        _SPACE_NORM_PATTERN,
        _SPACE_NORMALIZATIONS,
        _apply_space_normalizations,
    )
