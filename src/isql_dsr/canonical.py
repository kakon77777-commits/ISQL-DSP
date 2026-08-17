from __future__ import annotations

import hashlib
import json

from .model import SemanticState
from .native import encode_state


def inspection_json(state: SemanticState) -> str:
    """Deterministic JSON inspection projection. Not canonical storage."""
    if not isinstance(state, SemanticState):
        raise TypeError("inspection_json requires SemanticState")
    return json.dumps(
        state.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_json(state: SemanticState) -> str:
    """Compatibility alias for the inspection projection.

    v0.3 canonical authority is `canonical_bytes`, not this JSON string.
    """
    return inspection_json(state)


def canonical_bytes(state: SemanticState) -> bytes:
    """Authoritative v0.3 AI-native state representation."""
    return encode_state(state)


def state_hash(state: SemanticState) -> str:
    return hashlib.sha256(canonical_bytes(state)).hexdigest()
