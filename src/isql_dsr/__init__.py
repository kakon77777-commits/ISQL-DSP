"""ISQL Dynamic Spectrum Runtime v0.3 — AI-native canonical state."""

from .bridge import (
    CoreDomainEnvelope, CoreEnvelopeBundle, CoreStateEnvelope, SemanticSnapshot,
    NativeCoreDomainEnvelope, NativeCoreEnvelopeBundle,
    decode_core_envelope, decode_decimal_payload, encode_decimal_payload,
    decode_decimal_bytes, encode_decimal_bytes,
    to_core_bundle, to_core_sem_envelope, to_core_state_envelope,
    to_native_core_bundle, to_native_core_sem_envelope, to_native_core_state_envelope,
)
from .canonical import canonical_bytes, canonical_json, inspection_json, state_hash
from .diff import StateDiff, diff_states
from .events import TransitionEvent
from .fusion import FusionConflict, FusionDecision, SemanticProposal, fuse_proposals
from .model import (
    CandidateSetValue, IntervalValue, PointValue, SemanticProjection, SemanticState,
    SpectrumAxis, TopologyDescriptor, TypedRelation,
)
from .native import (
    NATIVE_FORMAT_VERSION, decode_state, encode_state, native_state_hash,
    operation_name, operation_opcode, decode_uvarint, encode_uvarint,
    decode_value, encode_value,
)
from .runtime import AppliedTransition, apply_event, replay
from .topology import compute_topology_descriptors, topology_basis_hash
from .validation import ValidationReport, validate_state

__version__ = "0.3.0"

__all__ = [
    "AppliedTransition", "CandidateSetValue", "CoreDomainEnvelope", "CoreEnvelopeBundle",
    "CoreStateEnvelope", "FusionConflict", "FusionDecision", "IntervalValue",
    "NativeCoreDomainEnvelope", "NativeCoreEnvelopeBundle", "NATIVE_FORMAT_VERSION",
    "PointValue", "SemanticProjection", "SemanticProposal", "SemanticSnapshot",
    "SemanticState", "SpectrumAxis", "StateDiff", "TopologyDescriptor",
    "TransitionEvent", "TypedRelation", "ValidationReport", "apply_event",
    "canonical_bytes", "canonical_json", "inspection_json", "compute_topology_descriptors",
    "decode_core_envelope", "decode_decimal_payload", "decode_decimal_bytes",
    "decode_state", "decode_uvarint", "decode_value", "diff_states",
    "encode_decimal_payload", "encode_decimal_bytes", "encode_state", "encode_uvarint",
    "encode_value", "fuse_proposals", "native_state_hash", "operation_name",
    "operation_opcode", "replay", "state_hash", "to_core_bundle",
    "to_core_sem_envelope", "to_core_state_envelope", "to_native_core_bundle",
    "to_native_core_sem_envelope", "to_native_core_state_envelope",
    "topology_basis_hash", "validate_state", "__version__",
]
