"""
English (United Kingdom) recipe matcher backend scaffold.

The full production matcher is still Swedish. This module keeps en_gb loadable
through MATCHER_LANGUAGE=en_gb while making the current limitation explicit.
Replace this wrapper with UK-specific imports and functions when the UK matcher
has real rule coverage.
"""

try:
    from languages.sv.recipe_matcher_backend import *  # noqa: F401,F403
except ModuleNotFoundError:
    from app.languages.sv.recipe_matcher_backend import *  # noqa: F401,F403
