"""ISQL Dynamic Spectrum Runtime v0.2."""

from .bridge import (
    CoreDomainEnvelope,
    CoreEnvelopeBundle,
    CoreStateEnvelope,
    SemanticSnapshot,
    decode_core_envelope,
    decode_decimal_payload,
    encode_decimal_payload,
    to_core_bundle,
    to_core_sem_envelope,
    to_core_state_envelope,
)
from .canonical import canonical_bytes, canonical_json, state_hash
from .diff import StateDiff, diff_states
from .events import TransitionEvent
from .fusion import FusionConflict, FusionDecision, SemanticProposal, fuse_proposals
from .model import (
    CandidateSetValue,
    IntervalValue,
    PointValue,
    SemanticProjection,
    SemanticState,
    SpectrumAxis,
    TopologyDescriptor,
    TypedRelation,
)
from .runtime import AppliedTransition, apply_event, replay
from .topology import compute_topology_descriptors, topology_basis_hash
from .validation import ValidationReport, validate_state

__version__ = "0.2.0"

__all__ = [
    "AppliedTransition",
    "CandidateSetValue",
    "CoreDomainEnvelope",
    "CoreEnvelopeBundle",
    "CoreStateEnvelope",
    "FusionConflict",
    "FusionDecision",
    "IntervalValue",
    "PointValue",
    "SemanticProjection",
    "SemanticProposal",
    "SemanticSnapshot",
    "SemanticState",
    "SpectrumAxis",
    "StateDiff",
    "TopologyDescriptor",
    "TransitionEvent",
    "TypedRelation",
    "ValidationReport",
    "apply_event",
    "canonical_bytes",
    "canonical_json",
    "compute_topology_descriptors",
    "decode_core_envelope",
    "decode_decimal_payload",
    "diff_states",
    "encode_decimal_payload",
    "fuse_proposals",
    "replay",
    "state_hash",
    "to_core_bundle",
    "to_core_sem_envelope",
    "to_core_state_envelope",
    "topology_basis_hash",
    "validate_state",
    "__version__",
]
