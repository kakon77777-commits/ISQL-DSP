"""ISQL Dynamic Spectrum Runtime v0.1."""

from .bridge import CoreStateEnvelope, to_core_state_envelope
from .canonical import canonical_bytes, canonical_json, state_hash
from .diff import StateDiff, diff_states
from .events import TransitionEvent
from .model import (
    CandidateSetValue,
    IntervalValue,
    PointValue,
    SemanticProjection,
    SemanticState,
    SpectrumAxis,
    TypedRelation,
)
from .runtime import AppliedTransition, apply_event, replay
from .validation import ValidationReport, validate_state

__version__ = "0.1.0"

__all__ = [
    "AppliedTransition",
    "CandidateSetValue",
    "CoreStateEnvelope",
    "IntervalValue",
    "PointValue",
    "SemanticProjection",
    "SemanticState",
    "SpectrumAxis",
    "StateDiff",
    "TransitionEvent",
    "TypedRelation",
    "ValidationReport",
    "apply_event",
    "canonical_bytes",
    "canonical_json",
    "diff_states",
    "replay",
    "state_hash",
    "to_core_state_envelope",
    "validate_state",
    "__version__",
]
