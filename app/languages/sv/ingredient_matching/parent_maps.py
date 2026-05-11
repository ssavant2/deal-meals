"""Parent keyword mappings for Swedish ingredient matching."""

from typing import Dict, List, Union

from .term_registry.exports import (
    KEYWORD_EXTRA_PARENTS as _REGISTRY_KEYWORD_EXTRA_PARENTS,
    PARENT_MATCH_ONLY as _REGISTRY_PARENT_MATCH_ONLY,
)

PARENT_MATCH_ONLY: Dict[str, str] = _REGISTRY_PARENT_MATCH_ONLY
KEYWORD_EXTRA_PARENTS: Dict[str, Union[str, List[str]]] = _REGISTRY_KEYWORD_EXTRA_PARENTS
