"""ISQL Dynamic Spectrum Runtime v1.0 — typed composite native computation architecture."""

from .branch import (
    NativeBranch, NativeMergeConflict, NativeMergeResult, decode_branch, encode_branch, merge_native_branches,
)
from .bridge import (
    CoreDomainEnvelope, CoreEnvelopeBundle, CoreStateEnvelope, SemanticSnapshot,
    NativeCoreDomainEnvelope, NativeCoreEnvelopeBundle,
    decode_core_envelope, decode_decimal_payload, encode_decimal_payload,
    decode_decimal_bytes, encode_decimal_bytes,
    to_core_bundle, to_core_sem_envelope, to_core_state_envelope,
    to_native_core_bundle, to_native_core_sem_envelope, to_native_core_state_envelope,
    RegisteredCoreEnvelope, to_registered_core_exec_envelope, to_registered_core_program_envelope,
    to_registered_core_sem_envelope, to_registered_core_state_envelope, to_registered_core_vm_envelope,
)
from .canonical import canonical_bytes, canonical_json, inspection_json, state_hash
from .diff import StateDiff, diff_states
from .events import TransitionEvent
from .fusion import FusionConflict, FusionDecision, SemanticProposal, fuse_proposals
from .linker import link_vm_programs
from .optimizer import optimize_vm_program
from .model import (
    CandidateSetValue, IntervalValue, PointValue, RecordValue, VectorValue, SemanticProjection, SemanticState,
    SpectrumAxis, TopologyDescriptor, TypedRelation,
)
from .native import (
    NATIVE_FORMAT_VERSION, decode_state, encode_state, native_state_hash,
    operation_name, operation_opcode, decode_uvarint, encode_uvarint,
    decode_value, encode_value,
)
from .runtime import AppliedTransition, apply_event, replay
from .program import (
    EFFECT_AXIS, EFFECT_CONTEXT, EFFECT_PROJECTION, EFFECT_RELATION, EFFECT_TOPOLOGY,
    EXECUTION_FAILED, EXECUTION_SUCCESS, NativeInstruction, NativeProgram,
    ProgramExecutionReceipt, ProgramExecutionResult, decode_program, encode_program,
    execute_native_program, operator_effect_mask, program_execution_order, program_from_stream, program_hash,
)

from .vm import (
    ALL_CAPABILITIES, BIND_DYNAMIC, BIND_EXACT, CAP_AXIS, CAP_AXIS_READ, CAP_CALL, CAP_CONTEXT, CAP_PROJECTION, CAP_RELATION, CAP_TOPOLOGY,
    EXECUTION_FAILED as VM_EXECUTION_FAILED, EXECUTION_SUCCESS as VM_EXECUTION_SUCCESS,
    GUARD_AXIS_ABSENT, GUARD_AXIS_PRESENT, GUARD_AXIS_VALUE_EQ, GUARD_RELATION_STATUS, GUARD_STATE_HASH_EQ,
    NativeGuard, NativeRegisterGuard, NativeVMProgram, VMFunctionSignature, VMRegisterSpec, VMInstruction, VMScopedCapability, VMStateBinding, VMTransactionReceipt, VMTransactionResult,
    REG_GUARD_INITIALIZED, REG_GUARD_VALUE_EQ,
    VM_OP_CALL, VM_OP_REPEAT_CALL, VM_MAX_REPEAT, VM_OP_LOAD_AXIS, VM_OP_RETURN, VM_OP_STORE_AXIS,
    VM_OP_CONST, VM_OP_MOVE, VM_OP_ADD, VM_OP_SUB, VM_OP_MUL, VM_OP_DIV, VM_OP_EQ, VM_OP_LT, VM_OP_LE,
    VM_OP_VECTOR_PACK, VM_OP_VECTOR_GET, VM_OP_VECTOR_LEN, VM_OP_RECORD_PACK, VM_OP_RECORD_GET, VM_OP_RECORD_SET,
    TYPE_ANY, TYPE_NULL, TYPE_BOOL, TYPE_INT, TYPE_FLOAT, TYPE_TEXT, TYPE_INTERVAL, TYPE_CANDIDATES, TYPE_VECTOR, TYPE_RECORD,
    decode_vm_call_payload, decode_vm_repeat_call_payload, decode_vm_program, encode_load_axis_payload, encode_store_axis_payload,
    encode_register_const_payload, encode_register_move_payload, encode_register_binary_payload,
    encode_vector_pack_payload, encode_vector_get_payload, encode_vector_len_payload, encode_record_pack_payload, encode_record_get_payload, encode_record_set_payload,
    encode_vm_call_payload, encode_vm_repeat_call_payload, encode_vm_program, evaluate_guard, evaluate_register_guard, execute_vm_transaction, machine_value_type, machine_value_matches_type,
    guard_axis_value_eq, guard_relation_status, guard_state_hash_eq, register_guard_initialized, register_guard_value_eq,
    vm_execution_batches, vm_execution_order, vm_program_hash,
)

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
    NativeEventStream, NativeStreamRecord, NativeTransitionEvent, apply_native_event, apply_native_operation, build_event_stream,
    compile_native_event, decode_event_stream, encode_event_stream, inspect_native_event,
    replay_native_stream,
)
from .topology import compute_topology_descriptors, topology_basis_hash
from .validation import ValidationReport, validate_state

__version__ = "1.0.0"

__all__ = [
    "AppliedTransition", "CandidateSetValue", "CoreDomainEnvelope", "CoreEnvelopeBundle",
    "NativeBranch", "NativeMergeConflict", "NativeMergeResult",
    "CoreStateEnvelope", "FusionConflict", "FusionDecision", "IntervalValue",
    "NativeAxis", "NativeCoreDomainEnvelope", "NativeCoreEnvelopeBundle",
    "NativeEventStream", "NativeProjection", "NativeRelation", "NativeSemanticState",
    "NativeStreamRecord", "NativeSymbolRegistry", "NativeTopology",
    "NativeTransitionEvent", "NATIVE_FORMAT_VERSION", "PointValue", "VectorValue", "RecordValue",
    "RegisteredCoreEnvelope", "SemanticProjection", "SemanticProposal",
    "SemanticSnapshot", "SemanticState", "SpectrumAxis", "StateDiff", "SymbolEntry",
    "SymbolNamespace", "TopologyDescriptor", "TransitionEvent", "TypedRelation",
    "ValidationReport", "apply_event", "apply_native_event", "build_event_stream", "canonical_bytes",
    "canonical_json", "compile_native_event", "compile_registered_state",
    "compute_topology_descriptors", "decode_core_envelope", "decode_decimal_payload",
    "decode_decimal_bytes", "decode_event_stream", "decode_branch", "decode_registry",
    "decode_registered_state", "decode_state", "decode_uvarint", "decode_value",
    "diff_states", "encode_decimal_payload", "encode_decimal_bytes",
    "encode_event_stream", "encode_branch", "encode_registry", "encode_registered_state", "encode_state",
    "encode_uvarint", "encode_value", "extend_registry_for_events",
    "extend_registry_for_state", "fuse_proposals", "inspect_native_event",
    "inspect_registered_state", "inspection_json", "native_state_hash", "operation_name",
    "operation_opcode", "registered_state_hash", "registry_hash", "replay", "merge_native_branches",
    "replay_native_stream", "state_hash", "to_core_bundle", "to_core_sem_envelope",
    "to_core_state_envelope", "to_native_core_bundle", "to_native_core_sem_envelope",
    "to_native_core_state_envelope", "to_registered_core_exec_envelope",
    "to_registered_core_sem_envelope", "to_registered_core_state_envelope",
    "EFFECT_AXIS", "EFFECT_CONTEXT", "EFFECT_PROJECTION", "EFFECT_RELATION", "EFFECT_TOPOLOGY",
    "EXECUTION_FAILED", "EXECUTION_SUCCESS", "NativeInstruction", "NativeProgram",
    "ProgramExecutionReceipt", "ProgramExecutionResult", "apply_native_operation",
    "decode_program", "encode_program", "execute_native_program", "operator_effect_mask",
    "program_execution_order", "program_from_stream", "program_hash", "to_registered_core_program_envelope",
    "to_registered_core_vm_envelope", "ALL_CAPABILITIES", "BIND_DYNAMIC", "BIND_EXACT", "CAP_AXIS", "CAP_CALL",
    "CAP_CONTEXT", "CAP_PROJECTION", "CAP_RELATION", "CAP_TOPOLOGY", "VM_EXECUTION_FAILED", "VM_EXECUTION_SUCCESS",
    "GUARD_AXIS_ABSENT", "GUARD_AXIS_PRESENT", "GUARD_AXIS_VALUE_EQ", "GUARD_RELATION_STATUS", "GUARD_STATE_HASH_EQ",
    "NativeGuard", "NativeVMProgram", "VMFunctionSignature", "VMRegisterSpec", "VMInstruction", "VMStateBinding", "VMTransactionReceipt", "VMTransactionResult",
    "VM_OP_CALL", "VM_OP_REPEAT_CALL", "VM_MAX_REPEAT", "VM_OP_LOAD_AXIS", "VM_OP_RETURN", "VM_OP_STORE_AXIS",
    "CAP_AXIS_READ", "VMScopedCapability", "decode_vm_call_payload", "encode_vm_call_payload",
    "encode_load_axis_payload", "encode_store_axis_payload", "decode_vm_program", "encode_vm_program",
    "evaluate_guard", "execute_vm_transaction", "guard_axis_value_eq", "guard_relation_status", "guard_state_hash_eq",
    "vm_execution_batches", "vm_execution_order", "vm_program_hash",
    "NativeRegisterGuard", "REG_GUARD_INITIALIZED", "REG_GUARD_VALUE_EQ",
    "register_guard_initialized", "register_guard_value_eq", "evaluate_register_guard",
    "VM_OP_CONST", "VM_OP_MOVE", "VM_OP_ADD", "VM_OP_SUB", "VM_OP_MUL", "VM_OP_DIV",
    "VM_OP_EQ", "VM_OP_LT", "VM_OP_LE", "VM_OP_VECTOR_PACK", "VM_OP_VECTOR_GET", "VM_OP_VECTOR_LEN", "VM_OP_RECORD_PACK", "VM_OP_RECORD_GET", "VM_OP_RECORD_SET",
    "TYPE_ANY", "TYPE_NULL", "TYPE_BOOL", "TYPE_INT", "TYPE_FLOAT", "TYPE_TEXT", "TYPE_INTERVAL", "TYPE_CANDIDATES", "TYPE_VECTOR", "TYPE_RECORD", "encode_register_const_payload",
    "encode_register_move_payload", "encode_register_binary_payload", "encode_vector_pack_payload", "encode_vector_get_payload", "encode_vector_len_payload",
    "encode_record_pack_payload", "encode_record_get_payload", "encode_record_set_payload", "encode_vm_repeat_call_payload", "decode_vm_repeat_call_payload",
    "machine_value_type", "machine_value_matches_type", "optimize_vm_program", "link_vm_programs",
    "topology_basis_hash", "validate_state", "__version__",
]
