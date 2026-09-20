"""finmod — the DETERMINISTIC financial engine.

Pure Python: no imports from app/models, app/db, or any LLM provider.
Input: plain dicts / dataclasses. Output: lineage-carrying result objects.
"""

from app.finmod.taxonomy import (
    ALL_KEYS,
    REGISTRY,
    CanonicalItem,
    resolve_label,
    validate_keys,
)

__all__ = ["ALL_KEYS", "REGISTRY", "CanonicalItem", "resolve_label", "validate_keys"]
