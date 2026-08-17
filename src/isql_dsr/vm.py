from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Mapping

from .errors import DSRExecutionError, DSRValidationError
from .native import decode_uvarint, encode_uvarint, operation_name, _encode_semantic_value, _decode_semantic_value
from .program import (
    EFFECT_AXIS,
    EFFECT_CONTEXT,
    EFFECT_PROJECTION,
    EFFECT_RELATION,
    EFFECT_TOPOLOGY,
    operator_effect_mask,
)
from .registry import NativeSymbolRegistry, SymbolNamespace


VM_PROGRAM_MAGIC = bytes((0xD5, 0x51, 0xE2, 0x07))
VM_PROGRAM_FORMAT_VERSION = 7

BIND_EXACT = 1
BIND_DYNAMIC = 2

CAP_CONTEXT = EFFECT_CONTEXT
CAP_AXIS = EFFECT_AXIS
CAP_RELATION = EFFECT_RELATION
CAP_PROJECTION = EFFECT_PROJECTION
CAP_TOPOLOGY = EFFECT_TOPOLOGY
CAP_CALL = 1 << 8
ALL_CAPABILITIES = CAP_CONTEXT | CAP_AXIS | CAP_RELATION | CAP_PROJECTION | CAP_TOPOLOGY | CAP_CALL

VM_OP_CALL = 1001
VM_OP_RETURN = 1002

GUARD_STATE_HASH_EQ = 1
GUARD_AXIS_PRESENT = 2
GUARD_AXIS_ABSENT = 3
GUARD_RELATION_STATUS = 4
GUARD_AXIS_VALUE_EQ = 5

_ZERO_HASH = "0" * 64


def _positive(value: int, error: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise DSRValidationError(error)
    return value


def _nonnegative(value: int, error: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DSRValidationError(error)
    return value


def _hash_hex(value: str, error: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise DSRValidationError(error)
    return value


def _read_blob(data: bytes, offset: int) -> tuple[bytes, int]:
    length, offset = decode_uvarint(data, offset)
    end = offset + length
    if end > len(data):
        raise DSRValidationError("VM_BLOB_TRUNCATED")
    return data[offset:end], end


def _write_blob(out: bytearray, raw: bytes) -> None:
    out += encode_uvarint(len(raw))
    out += raw


def _expected_effect_mask(opcode: int) -> int:
    if opcode in {VM_OP_CALL, VM_OP_RETURN}:
        return 0
    return operator_effect_mask(opcode)


def required_capability_for_opcode(opcode: int) -> int:
    if opcode == VM_OP_CALL:
        return CAP_CALL
    if opcode == VM_OP_RETURN:
        return 0
    return _expected_effect_mask(opcode)


@dataclass(frozen=True, slots=True)
class NativeGuard:
    guard_type: int
    payload: bytes = b""

    def __post_init__(self) -> None:
        if self.guard_type not in {
            GUARD_STATE_HASH_EQ,
            GUARD_AXIS_PRESENT,
            GUARD_AXIS_ABSENT,
            GUARD_RELATION_STATUS,
            GUARD_AXIS_VALUE_EQ,
        }:
            raise DSRValidationError("VM_GUARD_TYPE_INVALID")
        if not isinstance(self.payload, (bytes, bytearray, memoryview)):
            raise DSRValidationError("VM_GUARD_PAYLOAD_BYTES_REQUIRED")
        object.__setattr__(self, "payload", bytes(self.payload))
        if self.guard_type == GUARD_STATE_HASH_EQ and len(self.payload) != 32:
            raise DSRValidationError("VM_GUARD_STATE_HASH_INVALID")


@dataclass(frozen=True, slots=True)
class VMStateBinding:
    slot_ref: int
    binding_mode: int
    base_revision: int = 0
    base_hash: str = _ZERO_HASH

    def __post_init__(self) -> None:
        object.__setattr__(self, "slot_ref", _positive(self.slot_ref, "VM_SLOT_REF_INVALID"))
        if self.binding_mode not in {BIND_EXACT, BIND_DYNAMIC}:
            raise DSRValidationError("VM_BINDING_MODE_INVALID")
        object.__setattr__(self, "base_revision", _nonnegative(self.base_revision, "VM_BINDING_REVISION_INVALID"))
        object.__setattr__(self, "base_hash", _hash_hex(self.base_hash, "VM_BINDING_HASH_INVALID"))
        if self.binding_mode == BIND_DYNAMIC and (self.base_revision != 0 or self.base_hash != _ZERO_HASH):
            raise DSRValidationError("VM_DYNAMIC_BINDING_MUST_BE_UNPINNED")


@dataclass(frozen=True, slots=True)
class VMInstruction:
    instruction_ref: int
    opcode: int
    effect_mask: int
    required_capabilities: int
    target_ref: int
    depends_on: tuple[int, ...] = ()
    guards: tuple[NativeGuard, ...] = ()
    payload: bytes = b""

    def __post_init__(self) -> None:
        object.__setattr__(self, "instruction_ref", _positive(self.instruction_ref, "VM_INSTRUCTION_REF_INVALID"))
        if not isinstance(self.opcode, int) or isinstance(self.opcode, bool) or self.opcode <= 0:
            raise DSRValidationError("VM_OPCODE_INVALID")
        expected_effect = _expected_effect_mask(self.opcode)
        if self.effect_mask != expected_effect:
            raise DSRValidationError("VM_EFFECT_MASK_MISMATCH")
        expected_cap = required_capability_for_opcode(self.opcode)
        if self.required_capabilities != expected_cap:
            raise DSRValidationError("VM_CAPABILITY_MASK_MISMATCH")
        object.__setattr__(self, "target_ref", _positive(self.target_ref, "VM_TARGET_REF_INVALID"))
        if not isinstance(self.depends_on, tuple):
            raise DSRValidationError("VM_DEPENDENCIES_INVALID")
        deps = tuple(sorted(self.depends_on))
        if any(not isinstance(x, int) or isinstance(x, bool) or x <= 0 for x in deps):
            raise DSRValidationError("VM_DEPENDENCY_REF_INVALID")
        if len(set(deps)) != len(deps):
            raise DSRValidationError("VM_DEPENDENCY_DUPLICATE")
        if self.instruction_ref in deps:
            raise DSRValidationError("VM_DEPENDENCY_SELF")
        object.__setattr__(self, "depends_on", deps)
        if not isinstance(self.guards, tuple) or not all(isinstance(x, NativeGuard) for x in self.guards):
            raise DSRValidationError("VM_GUARDS_INVALID")
        object.__setattr__(self, "guards", tuple(self.guards))
        if not isinstance(self.payload, (bytes, bytearray, memoryview)):
            raise DSRValidationError("VM_PAYLOAD_BYTES_REQUIRED")
        object.__setattr__(self, "payload", bytes(self.payload))
        if self.opcode == VM_OP_RETURN and self.payload:
            raise DSRValidationError("VM_RETURN_PAYLOAD_INVALID")
        if self.opcode == VM_OP_CALL:
            try:
                callee_ref, used = decode_uvarint(self.payload, 0)
            except Exception as exc:
                raise DSRValidationError("VM_CALL_PAYLOAD_INVALID") from exc
            if used != len(self.payload) or callee_ref <= 0:
                raise DSRValidationError("VM_CALL_PAYLOAD_INVALID")


@dataclass(frozen=True, slots=True)
class NativeVMProgram:
    registry_revision: int
    registry_hash: str
    program_ref: int
    capability_mask: int
    bindings: tuple[VMStateBinding, ...]
    instructions: tuple[VMInstruction, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "registry_revision", _nonnegative(self.registry_revision, "VM_REGISTRY_REVISION_INVALID"))
        object.__setattr__(self, "registry_hash", _hash_hex(self.registry_hash, "VM_REGISTRY_HASH_INVALID"))
        object.__setattr__(self, "program_ref", _positive(self.program_ref, "VM_PROGRAM_REF_INVALID"))
        if not isinstance(self.capability_mask, int) or isinstance(self.capability_mask, bool) or self.capability_mask < 0:
            raise DSRValidationError("VM_PROGRAM_CAPABILITY_INVALID")
        if not isinstance(self.bindings, tuple) or not self.bindings or not all(isinstance(x, VMStateBinding) for x in self.bindings):
            raise DSRValidationError("VM_BINDINGS_INVALID")
        bindings = tuple(sorted(self.bindings, key=lambda x: x.slot_ref))
        if len({x.slot_ref for x in bindings}) != len(bindings):
            raise DSRValidationError("VM_BINDING_SLOT_DUPLICATE")
        object.__setattr__(self, "bindings", bindings)
        if not isinstance(self.instructions, tuple) or not all(isinstance(x, VMInstruction) for x in self.instructions):
            raise DSRValidationError("VM_INSTRUCTIONS_INVALID")
        rows = tuple(sorted(self.instructions, key=lambda x: x.instruction_ref))
        refs = [x.instruction_ref for x in rows]
        if len(set(refs)) != len(refs):
            raise DSRValidationError("VM_INSTRUCTION_DUPLICATE")
        ref_set = set(refs)
        slot_set = {x.slot_ref for x in bindings}
        required_mask = 0
        returns = 0
        for item in rows:
            if any(dep not in ref_set for dep in item.depends_on):
                raise DSRValidationError("VM_DEPENDENCY_UNKNOWN")
            if item.target_ref not in slot_set:
                raise DSRValidationError("VM_TARGET_SLOT_UNBOUND")
            if item.required_capabilities & ~self.capability_mask:
                raise DSRValidationError("VM_PROGRAM_CAPABILITY_INSUFFICIENT")
            required_mask |= item.required_capabilities
            if item.opcode == VM_OP_RETURN:
                returns += 1
        if self.capability_mask != required_mask:
            raise DSRValidationError("VM_PROGRAM_CAPABILITY_NONCANONICAL")
        if returns > 1:
            raise DSRValidationError("VM_MULTIPLE_RETURN_INVALID")
        order = _topological_order(rows)
        if returns:
            return_ref = next(x.instruction_ref for x in rows if x.opcode == VM_OP_RETURN)
            outgoing = {dep for x in rows for dep in x.depends_on if dep == return_ref}
            if outgoing or order[-1] != return_ref:
                raise DSRValidationError("VM_RETURN_MUST_TERMINATE")
        object.__setattr__(self, "instructions", rows)



def _encode_relation_guard_payload(subject_ref: int, predicate_ref: int, object_ref: int, status: int) -> bytes:
    if status not in {-1, 0, 1}:
        raise DSRValidationError("VM_GUARD_RELATION_STATUS_INVALID")
    out = bytearray()
    out += encode_uvarint(_positive(subject_ref, "VM_GUARD_RELATION_SUBJECT_INVALID"))
    out += encode_uvarint(_positive(predicate_ref, "VM_GUARD_RELATION_PREDICATE_INVALID"))
    out += encode_uvarint(_positive(object_ref, "VM_GUARD_RELATION_OBJECT_INVALID"))
    out += encode_uvarint(status + 1)
    return bytes(out)


def guard_state_hash_eq(state_hash: str) -> NativeGuard:
    return NativeGuard(GUARD_STATE_HASH_EQ, bytes.fromhex(_hash_hex(state_hash, "VM_GUARD_STATE_HASH_INVALID")))


def guard_axis_value_eq(key_ref: int, value: object) -> NativeGuard:
    out = bytearray()
    out += encode_uvarint(_positive(key_ref, "VM_GUARD_AXIS_REF_INVALID"))
    raw = _encode_semantic_value(value)
    _write_blob(out, raw)
    return NativeGuard(GUARD_AXIS_VALUE_EQ, bytes(out))


def guard_relation_status(subject_ref: int, predicate_ref: int, object_ref: int, status: int) -> NativeGuard:
    return NativeGuard(GUARD_RELATION_STATUS, _encode_relation_guard_payload(subject_ref, predicate_ref, object_ref, status))


def evaluate_guard(state: object, guard: NativeGuard, registry: NativeSymbolRegistry) -> bool:
    from .machine import NativeSemanticState, registered_state_hash
    if not isinstance(state, NativeSemanticState):
        raise TypeError("state must be NativeSemanticState")
    if not isinstance(guard, NativeGuard):
        raise TypeError("guard must be NativeGuard")
    if not isinstance(registry, NativeSymbolRegistry):
        raise TypeError("registry must be NativeSymbolRegistry")
    payload = guard.payload
    if guard.guard_type == GUARD_STATE_HASH_EQ:
        return registered_state_hash(state) == payload.hex()
    if guard.guard_type in {GUARD_AXIS_PRESENT, GUARD_AXIS_ABSENT}:
        key_ref, used = decode_uvarint(payload, 0)
        if used != len(payload):
            raise DSRValidationError("VM_GUARD_AXIS_PAYLOAD_INVALID")
        registry.resolve(key_ref, SymbolNamespace.AXIS_KEY)
        present = any(axis.key_ref == key_ref for axis in state.axes)
        return present if guard.guard_type == GUARD_AXIS_PRESENT else not present
    if guard.guard_type == GUARD_AXIS_VALUE_EQ:
        key_ref, offset = decode_uvarint(payload, 0)
        registry.resolve(key_ref, SymbolNamespace.AXIS_KEY)
        blob, offset = _read_blob(payload, offset)
        if offset != len(payload):
            raise DSRValidationError("VM_GUARD_AXIS_VALUE_PAYLOAD_INVALID")
        expected, used = _decode_semantic_value(blob, 0)
        if used != len(blob):
            raise DSRValidationError("VM_GUARD_AXIS_VALUE_INVALID")
        for axis in state.axes:
            if axis.key_ref == key_ref:
                return axis.value == expected
        return False
    if guard.guard_type == GUARD_RELATION_STATUS:
        subject_ref, offset = decode_uvarint(payload, 0)
        predicate_ref, offset = decode_uvarint(payload, offset)
        object_ref, offset = decode_uvarint(payload, offset)
        encoded_status, offset = decode_uvarint(payload, offset)
        if offset != len(payload) or encoded_status not in {0, 1, 2}:
            raise DSRValidationError("VM_GUARD_RELATION_PAYLOAD_INVALID")
        registry.resolve(subject_ref, SymbolNamespace.ATOM)
        registry.resolve(predicate_ref, SymbolNamespace.PREDICATE)
        registry.resolve(object_ref, SymbolNamespace.ATOM)
        key = (subject_ref, predicate_ref, object_ref)
        actual = 1 if any(rel.key == key for rel in state.relations) else (-1 if any(rel.key == key for rel in state.negative_relations) else 0)
        return actual == encoded_status - 1
    raise DSRValidationError("VM_GUARD_TYPE_INVALID")


def _topological_order(instructions: tuple[VMInstruction, ...]) -> tuple[int, ...]:
    by_ref = {item.instruction_ref: item for item in instructions}
    indegree = {ref: 0 for ref in by_ref}
    outgoing: dict[int, set[int]] = {ref: set() for ref in by_ref}
    for item in instructions:
        for dep in item.depends_on:
            if dep not in by_ref:
                raise DSRValidationError("VM_DEPENDENCY_UNKNOWN")
            indegree[item.instruction_ref] += 1
            outgoing[dep].add(item.instruction_ref)
    ready = sorted(ref for ref, degree in indegree.items() if degree == 0)
    order: list[int] = []
    while ready:
        ref = ready.pop(0)
        order.append(ref)
        for child in sorted(outgoing[ref]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()
    if len(order) != len(instructions):
        raise DSRValidationError("VM_DEPENDENCY_CYCLE")
    return tuple(order)


def vm_execution_order(program: NativeVMProgram) -> tuple[int, ...]:
    return _topological_order(program.instructions)


def _encode_guard(guard: NativeGuard) -> bytes:
    out = bytearray()
    out += encode_uvarint(guard.guard_type)
    _write_blob(out, guard.payload)
    return bytes(out)


def _decode_guard(data: bytes, offset: int) -> tuple[NativeGuard, int]:
    kind, offset = decode_uvarint(data, offset)
    payload, offset = _read_blob(data, offset)
    return NativeGuard(kind, payload), offset


def _encode_binding(binding: VMStateBinding) -> bytes:
    out = bytearray()
    out += encode_uvarint(binding.slot_ref)
    out += encode_uvarint(binding.binding_mode)
    out += encode_uvarint(binding.base_revision)
    out += bytes.fromhex(binding.base_hash)
    return bytes(out)


def _decode_binding(data: bytes, offset: int) -> tuple[VMStateBinding, int]:
    slot_ref, offset = decode_uvarint(data, offset)
    mode, offset = decode_uvarint(data, offset)
    revision, offset = decode_uvarint(data, offset)
    end = offset + 32
    if end > len(data):
        raise DSRValidationError("VM_BINDING_HASH_TRUNCATED")
    base_hash = data[offset:end].hex()
    offset = end
    return VMStateBinding(slot_ref, mode, revision, base_hash), offset


def _encode_instruction(item: VMInstruction) -> bytes:
    out = bytearray()
    out += encode_uvarint(item.instruction_ref)
    out += encode_uvarint(item.opcode)
    out += encode_uvarint(item.effect_mask)
    out += encode_uvarint(item.required_capabilities)
    out += encode_uvarint(item.target_ref)
    out += encode_uvarint(len(item.depends_on))
    for dep in item.depends_on:
        out += encode_uvarint(dep)
    out += encode_uvarint(len(item.guards))
    for guard in item.guards:
        _write_blob(out, _encode_guard(guard))
    _write_blob(out, item.payload)
    return bytes(out)


def _decode_instruction(data: bytes, offset: int) -> tuple[VMInstruction, int]:
    instruction_ref, offset = decode_uvarint(data, offset)
    opcode, offset = decode_uvarint(data, offset)
    effect_mask, offset = decode_uvarint(data, offset)
    required_capabilities, offset = decode_uvarint(data, offset)
    target_ref, offset = decode_uvarint(data, offset)
    dep_count, offset = decode_uvarint(data, offset)
    deps: list[int] = []
    for _ in range(dep_count):
        ref, offset = decode_uvarint(data, offset)
        deps.append(ref)
    guard_count, offset = decode_uvarint(data, offset)
    guards: list[NativeGuard] = []
    for _ in range(guard_count):
        blob, offset = _read_blob(data, offset)
        guard, used = _decode_guard(blob, 0)
        if used != len(blob):
            raise DSRValidationError("VM_GUARD_TRAILING_DATA")
        guards.append(guard)
    payload, offset = _read_blob(data, offset)
    return VMInstruction(
        instruction_ref, opcode, effect_mask, required_capabilities, target_ref,
        tuple(deps), tuple(guards), payload,
    ), offset


def encode_vm_program(program: NativeVMProgram) -> bytes:
    if not isinstance(program, NativeVMProgram):
        raise TypeError("encode_vm_program requires NativeVMProgram")
    out = bytearray(VM_PROGRAM_MAGIC)
    out += encode_uvarint(VM_PROGRAM_FORMAT_VERSION)
    out += encode_uvarint(program.registry_revision)
    out += bytes.fromhex(program.registry_hash)
    out += encode_uvarint(program.program_ref)
    out += encode_uvarint(program.capability_mask)
    out += encode_uvarint(len(program.bindings))
    for binding in program.bindings:
        _write_blob(out, _encode_binding(binding))
    out += encode_uvarint(len(program.instructions))
    for item in program.instructions:
        _write_blob(out, _encode_instruction(item))
    return bytes(out)


def decode_vm_program(data: bytes, registry: NativeSymbolRegistry) -> NativeVMProgram:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise DSRValidationError("VM_PROGRAM_BYTES_REQUIRED")
    if not isinstance(registry, NativeSymbolRegistry):
        raise TypeError("registry must be NativeSymbolRegistry")
    raw = bytes(data)
    if not raw.startswith(VM_PROGRAM_MAGIC):
        raise DSRValidationError("VM_PROGRAM_MAGIC_INVALID")
    offset = len(VM_PROGRAM_MAGIC)
    version, offset = decode_uvarint(raw, offset)
    if version != VM_PROGRAM_FORMAT_VERSION:
        raise DSRValidationError("VM_PROGRAM_VERSION_UNSUPPORTED")
    registry_revision, offset = decode_uvarint(raw, offset)
    end = offset + 32
    if end > len(raw):
        raise DSRValidationError("VM_REGISTRY_HASH_TRUNCATED")
    registry_hash = raw[offset:end].hex(); offset = end
    if registry.revision < registry_revision or registry.prefix_hash(registry_revision) != registry_hash:
        raise DSRValidationError("VM_REGISTRY_MISMATCH")
    program_ref, offset = decode_uvarint(raw, offset)
    registry.resolve(program_ref, SymbolNamespace.PROGRAM_ID)
    capability_mask, offset = decode_uvarint(raw, offset)
    binding_count, offset = decode_uvarint(raw, offset)
    bindings: list[VMStateBinding] = []
    for _ in range(binding_count):
        blob, offset = _read_blob(raw, offset)
        binding, used = _decode_binding(blob, 0)
        if used != len(blob):
            raise DSRValidationError("VM_BINDING_TRAILING_DATA")
        registry.resolve(binding.slot_ref, SymbolNamespace.STATE_SLOT_ID)
        bindings.append(binding)
    instruction_count, offset = decode_uvarint(raw, offset)
    instructions: list[VMInstruction] = []
    for _ in range(instruction_count):
        blob, offset = _read_blob(raw, offset)
        item, used = _decode_instruction(blob, 0)
        if used != len(blob):
            raise DSRValidationError("VM_INSTRUCTION_TRAILING_DATA")
        registry.resolve(item.instruction_ref, SymbolNamespace.INSTRUCTION_ID)
        if item.opcode == VM_OP_CALL:
            callee_ref, used = decode_uvarint(item.payload, 0)
            if used != len(item.payload):
                raise DSRValidationError("VM_CALL_PAYLOAD_INVALID")
            registry.resolve(callee_ref, SymbolNamespace.PROGRAM_ID)
        instructions.append(item)
    if offset != len(raw):
        raise DSRValidationError("VM_PROGRAM_TRAILING_DATA")
    program = NativeVMProgram(
        registry_revision, registry_hash, program_ref, capability_mask,
        tuple(bindings), tuple(instructions),
    )
    if encode_vm_program(program) != raw:
        raise DSRValidationError("VM_PROGRAM_NONCANONICAL")
    return program


def vm_program_hash(program: NativeVMProgram) -> str:
    return hashlib.sha256(encode_vm_program(program)).hexdigest()


EXECUTION_SUCCESS = 1
EXECUTION_FAILED = 2


@dataclass(frozen=True, slots=True)
class VMTransactionReceipt:
    status: int
    program_ref: int
    base_hashes: tuple[tuple[int, str], ...]
    final_hashes: tuple[tuple[int, str], ...]
    execution_trace: tuple[tuple[int, int], ...] = ()
    failed_program_ref: int = 0
    failed_instruction_ref: int = 0
    error_code: str = ""

    def __post_init__(self) -> None:
        if self.status not in {EXECUTION_SUCCESS, EXECUTION_FAILED}:
            raise DSRValidationError("VM_RECEIPT_STATUS_INVALID")
        _positive(self.program_ref, "VM_RECEIPT_PROGRAM_REF_INVALID")
        for rows, error in ((self.base_hashes, "VM_RECEIPT_BASE_HASHES_INVALID"), (self.final_hashes, "VM_RECEIPT_FINAL_HASHES_INVALID")):
            if not isinstance(rows, tuple):
                raise DSRValidationError(error)
            last = 0
            for slot_ref, state_hash in rows:
                if not isinstance(slot_ref, int) or slot_ref <= last:
                    raise DSRValidationError(error)
                _hash_hex(state_hash, error)
                last = slot_ref
        if not isinstance(self.execution_trace, tuple) or not all(
            isinstance(x, tuple) and len(x) == 2 and all(isinstance(v, int) and v > 0 for v in x)
            for x in self.execution_trace
        ):
            raise DSRValidationError("VM_RECEIPT_TRACE_INVALID")
        if not isinstance(self.failed_program_ref, int) or self.failed_program_ref < 0:
            raise DSRValidationError("VM_RECEIPT_FAILED_PROGRAM_INVALID")
        if not isinstance(self.failed_instruction_ref, int) or self.failed_instruction_ref < 0:
            raise DSRValidationError("VM_RECEIPT_FAILED_INSTRUCTION_INVALID")
        if not isinstance(self.error_code, str):
            raise DSRValidationError("VM_RECEIPT_ERROR_INVALID")


@dataclass(frozen=True, slots=True)
class VMTransactionResult:
    states: dict[int, object]
    receipt: VMTransactionReceipt


class _VMAbort(Exception):
    def __init__(self, code: str, program_ref: int, instruction_ref: int, trace: list[tuple[int, int]]):
        super().__init__(code)
        self.code = code
        self.program_ref = program_ref
        self.instruction_ref = instruction_ref
        self.trace = tuple(trace)


def _state_hash_rows(states: Mapping[int, object]) -> tuple[tuple[int, str], ...]:
    from .machine import NativeSemanticState, registered_state_hash
    rows: list[tuple[int, str]] = []
    for slot_ref in sorted(states):
        state = states[slot_ref]
        if not isinstance(slot_ref, int) or isinstance(slot_ref, bool) or slot_ref <= 0:
            raise DSRValidationError("VM_STATE_SLOT_INVALID")
        if not isinstance(state, NativeSemanticState):
            raise TypeError("states must map slot refs to NativeSemanticState")
        rows.append((slot_ref, registered_state_hash(state)))
    return tuple(rows)


def _validate_program_environment(program: NativeVMProgram, registry: NativeSymbolRegistry, granted_capabilities: int) -> None:
    if registry.revision < program.registry_revision or registry.prefix_hash(program.registry_revision) != program.registry_hash:
        raise DSRExecutionError("VM_REGISTRY_MISMATCH")
    registry.resolve(program.program_ref, SymbolNamespace.PROGRAM_ID)
    if program.capability_mask & ~granted_capabilities:
        raise DSRExecutionError("VM_CAPABILITY_DENIED")
    for item in program.instructions:
        registry.resolve(item.instruction_ref, SymbolNamespace.INSTRUCTION_ID)
        if item.required_capabilities & ~granted_capabilities:
            raise DSRExecutionError("VM_CAPABILITY_DENIED")


def _binding_actual_slot(binding: VMStateBinding, aliases: Mapping[int, int]) -> int:
    if binding.slot_ref not in aliases:
        raise DSRExecutionError("VM_SLOT_ALIAS_MISSING")
    return aliases[binding.slot_ref]


def _validate_bindings(
    program: NativeVMProgram,
    working: Mapping[int, object],
    aliases: Mapping[int, int],
) -> None:
    from .machine import NativeSemanticState, registered_state_hash
    for binding in program.bindings:
        actual = _binding_actual_slot(binding, aliases)
        if actual not in working:
            raise DSRExecutionError("VM_STATE_SLOT_MISSING")
        state = working[actual]
        if not isinstance(state, NativeSemanticState):
            raise TypeError("states must map slot refs to NativeSemanticState")
        if binding.binding_mode == BIND_EXACT:
            if state.revision != binding.base_revision:
                raise DSRExecutionError("VM_BINDING_REVISION_MISMATCH")
            if registered_state_hash(state) != binding.base_hash:
                raise DSRExecutionError("VM_BINDING_HASH_MISMATCH")


def _decode_call_ref(payload: bytes) -> int:
    try:
        ref, used = decode_uvarint(payload, 0)
    except Exception as exc:
        raise DSRExecutionError("VM_CALL_PAYLOAD_INVALID") from exc
    if used != len(payload) or ref <= 0:
        raise DSRExecutionError("VM_CALL_PAYLOAD_INVALID")
    return ref


def _execute_program_frame(
    program: NativeVMProgram,
    working: dict[int, object],
    aliases: Mapping[int, int],
    registry: NativeSymbolRegistry,
    library: Mapping[int, NativeVMProgram],
    granted_capabilities: int,
    call_stack: tuple[int, ...],
    trace: list[tuple[int, int]],
) -> None:
    from .stream import apply_native_operation
    try:
        _validate_program_environment(program, registry, granted_capabilities)
        _validate_bindings(program, working, aliases)
    except (DSRExecutionError, DSRValidationError) as exc:
        raise _VMAbort(str(exc), program.program_ref, 0, trace) from exc

    by_ref = {item.instruction_ref: item for item in program.instructions}
    for instruction_ref in vm_execution_order(program):
        item = by_ref[instruction_ref]
        actual_slot = aliases.get(item.target_ref)
        if actual_slot is None or actual_slot not in working:
            raise _VMAbort("VM_STATE_SLOT_MISSING", program.program_ref, instruction_ref, trace)
        state = working[actual_slot]
        try:
            if any(not evaluate_guard(state, guard, registry) for guard in item.guards):
                raise DSRExecutionError("VM_GUARD_FAILED")
            if item.opcode == VM_OP_RETURN:
                trace.append((program.program_ref, instruction_ref))
                return
            if item.opcode == VM_OP_CALL:
                callee_ref = _decode_call_ref(item.payload)
                registry.resolve(callee_ref, SymbolNamespace.PROGRAM_ID)
                if callee_ref in call_stack:
                    raise DSRExecutionError("VM_CALL_CYCLE")
                callee = library.get(callee_ref)
                if callee is None or callee.program_ref != callee_ref:
                    raise DSRExecutionError("VM_CALLEE_NOT_FOUND")
                if len(callee.bindings) != 1 or callee.bindings[0].binding_mode != BIND_DYNAMIC:
                    raise DSRExecutionError("VM_CALLEE_BINDING_INVALID")
                trace.append((program.program_ref, instruction_ref))
                callee_aliases = {callee.bindings[0].slot_ref: actual_slot}
                _execute_program_frame(
                    callee, working, callee_aliases, registry, library,
                    granted_capabilities, call_stack + (callee_ref,), trace,
                )
                continue
            working[actual_slot] = apply_native_operation(state, item.opcode, item.payload, registry)
            trace.append((program.program_ref, instruction_ref))
        except _VMAbort:
            raise
        except (DSRExecutionError, DSRValidationError) as exc:
            raise _VMAbort(str(exc), program.program_ref, instruction_ref, trace) from exc


def execute_vm_transaction(
    states: Mapping[int, object],
    program: NativeVMProgram,
    registry: NativeSymbolRegistry,
    program_library: Mapping[int, NativeVMProgram] | None = None,
    granted_capabilities: int = ALL_CAPABILITIES,
) -> VMTransactionResult:
    if not isinstance(program, NativeVMProgram):
        raise TypeError("program must be NativeVMProgram")
    if not isinstance(registry, NativeSymbolRegistry):
        raise TypeError("registry must be NativeSymbolRegistry")
    if not isinstance(granted_capabilities, int) or isinstance(granted_capabilities, bool) or granted_capabilities < 0:
        raise DSRValidationError("VM_GRANTED_CAPABILITIES_INVALID")
    originals = dict(states)
    base_hashes = _state_hash_rows(originals)
    working = dict(originals)
    library = dict(program_library or {})
    root_aliases = {binding.slot_ref: binding.slot_ref for binding in program.bindings}
    trace: list[tuple[int, int]] = []
    try:
        _execute_program_frame(
            program, working, root_aliases, registry, library,
            granted_capabilities, (program.program_ref,), trace,
        )
    except _VMAbort as exc:
        return VMTransactionResult(
            originals,
            VMTransactionReceipt(
                EXECUTION_FAILED, program.program_ref, base_hashes, base_hashes,
                exc.trace, exc.program_ref, exc.instruction_ref, exc.code,
            ),
        )
    final_hashes = _state_hash_rows(working)
    return VMTransactionResult(
        working,
        VMTransactionReceipt(
            EXECUTION_SUCCESS, program.program_ref, base_hashes, final_hashes,
            tuple(trace), 0, 0, "",
        ),
    )
