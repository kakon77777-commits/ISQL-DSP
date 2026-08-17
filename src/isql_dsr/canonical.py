from __future__ import annotations

import hashlib
import json

from .model import SemanticState


def canonical_json(state: SemanticState) -> str:
    if not isinstance(state, SemanticState):
        raise TypeError("canonical_json requires SemanticState")
    return json.dumps(
        state.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_bytes(state: SemanticState) -> bytes:
    return canonical_json(state).encode("utf-8")


def state_hash(state: SemanticState) -> str:
    return hashlib.sha256(canonical_bytes(state)).hexdigest()
