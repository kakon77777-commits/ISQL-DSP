"""ISQL Dynamic Spectrum Runtime v0.4 — registered AI-native state and native event streams."""

from .bridge import (
    CoreDomainEnvelope, CoreEnvelopeBundle, CoreStateEnvelope, SemanticSnapshot,
    NativeCoreDomainEnvelope, NativeCoreEnvelopeBundle,
    decode_core_envelope, decode_decimal_payload, encode_decimal_payload,
    decode_decimal_bytes, encode_decimal_bytes,
    to_core_bundle, to_core_sem_envelope, to_core_state_envelope,
    to_native_core_bundle, to_native_core_sem_envelope, to_native_core_state_envelope,
    RegisteredCoreEnvelope, to_registered_core_exec_envelope,
    to_registered_core_sem_envelope, to_registered_core_state_envelope,
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

from .machine import (
    NativeAxis, NativeProjection, NativeRelation, NativeSemanticState, NativeTopology,
    compile_registered_state, decode_registered_state, encode_registered_state,
    inspect_registered_state, registered_state_hash,
)
from .registry import (
    NativeSymbolRegistry, SymbolEntry, SymbolNamespace, decode_registry, encode_registry,
    extend_registry_for_events, extend_registry_for_state, registry_hash,
)
from .stream import (
    NativeEventStream, NativeStreamRecord, NativeTransitionEvent, build_event_stream,
    compile_native_event, decode_event_stream, encode_event_stream, inspect_native_event,
    replay_native_stream,
)
from .topology import compute_topology_descriptors, topology_basis_hash
from .validation import ValidationReport, validate_state

__version__ = "0.4.0"

__all__ = [
    "AppliedTransition", "CandidateSetValue", "CoreDomainEnvelope", "CoreEnvelopeBundle",
    "CoreStateEnvelope", "FusionConflict", "FusionDecision", "IntervalValue",
    "NativeAxis", "NativeCoreDomainEnvelope", "NativeCoreEnvelopeBundle",
    "NativeEventStream", "NativeProjection", "NativeRelation", "NativeSemanticState",
    "NativeStreamRecord", "NativeSymbolRegistry", "NativeTopology",
    "NativeTransitionEvent", "NATIVE_FORMAT_VERSION", "PointValue",
    "RegisteredCoreEnvelope", "SemanticProjection", "SemanticProposal",
    "SemanticSnapshot", "SemanticState", "SpectrumAxis", "StateDiff", "SymbolEntry",
    "SymbolNamespace", "TopologyDescriptor", "TransitionEvent", "TypedRelation",
    "ValidationReport", "apply_event", "build_event_stream", "canonical_bytes",
    "canonical_json", "compile_native_event", "compile_registered_state",
    "compute_topology_descriptors", "decode_core_envelope", "decode_decimal_payload",
    "decode_decimal_bytes", "decode_event_stream", "decode_registry",
    "decode_registered_state", "decode_state", "decode_uvarint", "decode_value",
    "diff_states", "encode_decimal_payload", "encode_decimal_bytes",
    "encode_event_stream", "encode_registry", "encode_registered_state", "encode_state",
    "encode_uvarint", "encode_value", "extend_registry_for_events",
    "extend_registry_for_state", "fuse_proposals", "inspect_native_event",
    "inspect_registered_state", "inspection_json", "native_state_hash", "operation_name",
    "operation_opcode", "registered_state_hash", "registry_hash", "replay",
    "replay_native_stream", "state_hash", "to_core_bundle", "to_core_sem_envelope",
    "to_core_state_envelope", "to_native_core_bundle", "to_native_core_sem_envelope",
    "to_native_core_state_envelope", "to_registered_core_exec_envelope",
    "to_registered_core_sem_envelope", "to_registered_core_state_envelope",
    "topology_basis_hash", "validate_state", "__version__",
]
