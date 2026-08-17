from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from .errors import DSRExecutionError, DSRValidationError
from .native import decode_uvarint, encode_uvarint, operation_name
from .registry import NativeSymbolRegistry, SymbolNamespace


PROGRAM_MAGIC = bytes((0xD5, 0x51, 0xE1, 0x06))
PROGRAM_FORMAT_VERSION = 6

EFFECT_CONTEXT = 1 << 0
EFFECT_AXIS = 1 << 1
EFFECT_RELATION = 1 << 2
EFFECT_PROJECTION = 1 << 3
EFFECT_TOPOLOGY = 1 << 4


def _positive(value: int, error: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise DSRValidationError(error)
    return value


def _hash_hex(value: str, error: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise DSRValidationError(error)
    return value


def operator_effect_mask(opcode: int) -> int:
    name = operation_name(opcode)
    if name == "set_context":
        return EFFECT_CONTEXT
    if name in {"upsert_axis", "remove_axis"}:
        return EFFECT_AXIS
    if name in {"upsert_relation", "remove_relation", "deny_relation", "retract_relation"}:
        return EFFECT_RELATION | EFFECT_TOPOLOGY
    if name in {"upsert_projection", "remove_projection"}:
        return EFFECT_PROJECTION
    if name in {"refresh_topology", "upsert_topology_descriptor", "remove_topology_descriptor"}:
        return EFFECT_TOPOLOGY
    if name == "fuse_proposals":
        return EFFECT_AXIS | EFFECT_RELATION | EFFECT_TOPOLOGY
    raise DSRValidationError("PROGRAM_OPCODE_UNSUPPORTED")


@dataclass(frozen=True, slots=True)
class NativeInstruction:
    instruction_ref: int
    opcode: int
    effect_mask: int
    depends_on: tuple[int, ...] = ()
    payload: bytes = b""

    def __post_init__(self) -> None:
        object.__setattr__(self, "instruction_ref", _positive(self.instruction_ref, "PROGRAM_INSTRUCTION_REF_INVALID"))
        if not isinstance(self.opcode, int) or isinstance(self.opcode, bool) or self.opcode <= 0:
            raise DSRValidationError("PROGRAM_OPCODE_INVALID")
        expected = operator_effect_mask(self.opcode)
        if self.effect_mask != expected:
            raise DSRValidationError("PROGRAM_EFFECT_MASK_MISMATCH")
        if not isinstance(self.depends_on, tuple):
            raise DSRValidationError("PROGRAM_DEPENDENCIES_INVALID")
        deps = tuple(sorted(self.depends_on))
        if any(not isinstance(ref, int) or isinstance(ref, bool) or ref <= 0 for ref in deps):
            raise DSRValidationError("PROGRAM_DEPENDENCY_REF_INVALID")
        if len(set(deps)) != len(deps):
            raise DSRValidationError("PROGRAM_DEPENDENCY_DUPLICATE")
        if self.instruction_ref in deps:
            raise DSRValidationError("PROGRAM_DEPENDENCY_SELF")
        object.__setattr__(self, "depends_on", deps)
        if not isinstance(self.payload, (bytes, bytearray, memoryview)):
            raise DSRValidationError("PROGRAM_PAYLOAD_BYTES_REQUIRED")
        object.__setattr__(self, "payload", bytes(self.payload))


@dataclass(frozen=True, slots=True)
class NativeProgram:
    registry_revision: int
    registry_hash: str
    program_ref: int
    base_revision: int
    base_hash: str
    instructions: tuple[NativeInstruction, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.registry_revision, int) or isinstance(self.registry_revision, bool) or self.registry_revision < 0:
            raise DSRValidationError("PROGRAM_REGISTRY_REVISION_INVALID")
        object.__setattr__(self, "registry_hash", _hash_hex(self.registry_hash, "PROGRAM_REGISTRY_HASH_INVALID"))
        object.__setattr__(self, "program_ref", _positive(self.program_ref, "PROGRAM_REF_INVALID"))
        if not isinstance(self.base_revision, int) or isinstance(self.base_revision, bool) or self.base_revision < 0:
            raise DSRValidationError("PROGRAM_BASE_REVISION_INVALID")
        object.__setattr__(self, "base_hash", _hash_hex(self.base_hash, "PROGRAM_BASE_HASH_INVALID"))
        if not isinstance(self.instructions, tuple) or not all(isinstance(x, NativeInstruction) for x in self.instructions):
            raise DSRValidationError("PROGRAM_INSTRUCTIONS_INVALID")
        rows = tuple(sorted(self.instructions, key=lambda x: x.instruction_ref))
        refs = [x.instruction_ref for x in rows]
        if len(set(refs)) != len(refs):
            raise DSRValidationError("PROGRAM_INSTRUCTION_DUPLICATE")
        ref_set = set(refs)
        for item in rows:
            if any(dep not in ref_set for dep in item.depends_on):
                raise DSRValidationError("PROGRAM_DEPENDENCY_UNKNOWN")
        _topological_order(rows)
        object.__setattr__(self, "instructions", rows)


def _topological_order(instructions: tuple[NativeInstruction, ...]) -> tuple[int, ...]:
    by_ref = {item.instruction_ref: item for item in instructions}
    indegree = {ref: 0 for ref in by_ref}
    outgoing: dict[int, set[int]] = {ref: set() for ref in by_ref}
    for item in instructions:
        for dep in item.depends_on:
            if dep not in by_ref:
                raise DSRValidationError("PROGRAM_DEPENDENCY_UNKNOWN")
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
        raise DSRValidationError("PROGRAM_DEPENDENCY_CYCLE")
    return tuple(order)


def program_execution_order(program: NativeProgram) -> tuple[int, ...]:
    if not isinstance(program, NativeProgram):
        raise TypeError("program must be NativeProgram")
    return _topological_order(program.instructions)


def _write_blob(out: bytearray, raw: bytes) -> None:
    out += encode_uvarint(len(raw))
    out += raw


def _read_blob(data: bytes, offset: int) -> tuple[bytes, int]:
    length, offset = decode_uvarint(data, offset)
    end = offset + length
    if end > len(data):
        raise DSRValidationError("PROGRAM_BLOB_TRUNCATED")
    return data[offset:end], end


def _encode_instruction(item: NativeInstruction) -> bytes:
    out = bytearray()
    out += encode_uvarint(item.instruction_ref)
    out += encode_uvarint(item.opcode)
    out += encode_uvarint(item.effect_mask)
    out += encode_uvarint(len(item.depends_on))
    for ref in item.depends_on:
        out += encode_uvarint(ref)
    _write_blob(out, item.payload)
    return bytes(out)


def _decode_instruction(data: bytes, offset: int) -> tuple[NativeInstruction, int]:
    instruction_ref, offset = decode_uvarint(data, offset)
    opcode, offset = decode_uvarint(data, offset)
    effect_mask, offset = decode_uvarint(data, offset)
    count, offset = decode_uvarint(data, offset)
    deps: list[int] = []
    for _ in range(count):
        ref, offset = decode_uvarint(data, offset)
        deps.append(ref)
    payload, offset = _read_blob(data, offset)
    return NativeInstruction(instruction_ref, opcode, effect_mask, tuple(deps), payload), offset


def encode_program(program: NativeProgram) -> bytes:
    if not isinstance(program, NativeProgram):
        raise TypeError("encode_program requires NativeProgram")
    out = bytearray(PROGRAM_MAGIC)
    out += encode_uvarint(PROGRAM_FORMAT_VERSION)
    out += encode_uvarint(program.registry_revision)
    out += bytes.fromhex(program.registry_hash)
    out += encode_uvarint(program.program_ref)
    out += encode_uvarint(program.base_revision)
    out += bytes.fromhex(program.base_hash)
    out += encode_uvarint(len(program.instructions))
    for item in program.instructions:
        blob = _encode_instruction(item)
        _write_blob(out, blob)
    return bytes(out)


def decode_program(data: bytes, registry: NativeSymbolRegistry) -> NativeProgram:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise DSRValidationError("PROGRAM_BYTES_REQUIRED")
    if not isinstance(registry, NativeSymbolRegistry):
        raise TypeError("registry must be NativeSymbolRegistry")
    data = bytes(data)
    if not data.startswith(PROGRAM_MAGIC):
        raise DSRValidationError("PROGRAM_MAGIC_INVALID")
    offset = len(PROGRAM_MAGIC)
    version, offset = decode_uvarint(data, offset)
    if version != PROGRAM_FORMAT_VERSION:
        raise DSRValidationError("PROGRAM_VERSION_UNSUPPORTED")
    registry_revision, offset = decode_uvarint(data, offset)
    end = offset + 32
    if end > len(data):
        raise DSRValidationError("PROGRAM_REGISTRY_HASH_TRUNCATED")
    registry_hash = data[offset:end].hex(); offset = end
    if registry.revision < registry_revision or registry.prefix_hash(registry_revision) != registry_hash:
        raise DSRValidationError("PROGRAM_REGISTRY_MISMATCH")
    program_ref, offset = decode_uvarint(data, offset)
    registry.resolve(program_ref, SymbolNamespace.PROGRAM_ID)
    base_revision, offset = decode_uvarint(data, offset)
    end = offset + 32
    if end > len(data):
        raise DSRValidationError("PROGRAM_BASE_HASH_TRUNCATED")
    base_hash = data[offset:end].hex(); offset = end
    count, offset = decode_uvarint(data, offset)
    rows: list[NativeInstruction] = []
    for _ in range(count):
        blob, offset = _read_blob(data, offset)
        item, used = _decode_instruction(blob, 0)
        if used != len(blob):
            raise DSRValidationError("PROGRAM_INSTRUCTION_TRAILING_DATA")
        registry.resolve(item.instruction_ref, SymbolNamespace.INSTRUCTION_ID)
        rows.append(item)
    if offset != len(data):
        raise DSRValidationError("PROGRAM_TRAILING_DATA")
    program = NativeProgram(registry_revision, registry_hash, program_ref, base_revision, base_hash, tuple(rows))
    if encode_program(program) != data:
        raise DSRValidationError("PROGRAM_NONCANONICAL")
    return program


def program_hash(program: NativeProgram) -> str:
    return hashlib.sha256(encode_program(program)).hexdigest()


def program_from_stream(
    stream: object,
    registry: NativeSymbolRegistry,
    program_ref: int,
    instruction_refs: Iterable[int],
    *,
    causal_chain: bool = True,
) -> NativeProgram:
    from .stream import NativeEventStream
    if not isinstance(stream, NativeEventStream):
        raise TypeError("stream must be NativeEventStream")
    refs = tuple(instruction_refs)
    if len(refs) != len(stream.records):
        raise DSRValidationError("PROGRAM_INSTRUCTION_COUNT_MISMATCH")
    registry.resolve(program_ref, SymbolNamespace.PROGRAM_ID)
    for ref in refs:
        registry.resolve(ref, SymbolNamespace.INSTRUCTION_ID)
    rows: list[NativeInstruction] = []
    for index, (ref, record) in enumerate(zip(refs, stream.records)):
        deps = (refs[index - 1],) if causal_chain and index else ()
        rows.append(NativeInstruction(
            ref,
            record.event.opcode,
            operator_effect_mask(record.event.opcode),
            deps,
            record.event.payload,
        ))
    base_revision = stream.records[0].event.base_revision if stream.records else 0
    return NativeProgram(
        registry.revision,
        registry.prefix_hash(registry.revision),
        program_ref,
        base_revision,
        stream.genesis_hash,
        tuple(rows),
    )


EXECUTION_SUCCESS = 1
EXECUTION_FAILED = 2


@dataclass(frozen=True, slots=True)
class ProgramExecutionReceipt:
    status: int
    program_ref: int
    base_hash: str
    final_hash: str
    execution_order: tuple[int, ...] = ()
    failed_instruction_ref: int = 0
    error_code: str = ""

    def __post_init__(self) -> None:
        if self.status not in {EXECUTION_SUCCESS, EXECUTION_FAILED}:
            raise DSRValidationError("PROGRAM_RECEIPT_STATUS_INVALID")
        _positive(self.program_ref, "PROGRAM_RECEIPT_PROGRAM_REF_INVALID")
        _hash_hex(self.base_hash, "PROGRAM_RECEIPT_BASE_HASH_INVALID")
        _hash_hex(self.final_hash, "PROGRAM_RECEIPT_FINAL_HASH_INVALID")
        if not isinstance(self.execution_order, tuple) or not all(isinstance(x, int) and x > 0 for x in self.execution_order):
            raise DSRValidationError("PROGRAM_RECEIPT_ORDER_INVALID")
        if not isinstance(self.failed_instruction_ref, int) or isinstance(self.failed_instruction_ref, bool) or self.failed_instruction_ref < 0:
            raise DSRValidationError("PROGRAM_RECEIPT_FAILED_REF_INVALID")
        if not isinstance(self.error_code, str):
            raise DSRValidationError("PROGRAM_RECEIPT_ERROR_INVALID")


@dataclass(frozen=True, slots=True)
class ProgramExecutionResult:
    state: object
    receipt: ProgramExecutionReceipt


def _failure_result(base: object, program: NativeProgram, error_code: str, *, executed: tuple[int, ...] = (), failed_ref: int = 0) -> ProgramExecutionResult:
    from .machine import registered_state_hash
    base_hash = registered_state_hash(base)
    return ProgramExecutionResult(
        base,
        ProgramExecutionReceipt(
            EXECUTION_FAILED,
            program.program_ref,
            base_hash,
            base_hash,
            executed,
            failed_ref,
            error_code,
        ),
    )


def execute_native_program(base: object, program: NativeProgram, registry: NativeSymbolRegistry) -> ProgramExecutionResult:
    from .machine import NativeSemanticState, registered_state_hash
    from .stream import apply_native_operation
    if not isinstance(base, NativeSemanticState):
        raise TypeError("base must be NativeSemanticState")
    if not isinstance(program, NativeProgram):
        raise TypeError("program must be NativeProgram")
    if not isinstance(registry, NativeSymbolRegistry):
        raise TypeError("registry must be NativeSymbolRegistry")
    base_hash = registered_state_hash(base)
    if registry.revision < program.registry_revision or registry.prefix_hash(program.registry_revision) != program.registry_hash:
        return _failure_result(base, program, "PROGRAM_REGISTRY_MISMATCH")
    try:
        registry.resolve(program.program_ref, SymbolNamespace.PROGRAM_ID)
        for item in program.instructions:
            registry.resolve(item.instruction_ref, SymbolNamespace.INSTRUCTION_ID)
    except DSRValidationError:
        return _failure_result(base, program, "PROGRAM_SYMBOL_MISMATCH")
    if program.base_revision != base.revision:
        return _failure_result(base, program, "PROGRAM_BASE_REVISION_MISMATCH")
    if program.base_hash != base_hash:
        return _failure_result(base, program, "PROGRAM_BASE_HASH_MISMATCH")
    order = program_execution_order(program)
    by_ref = {item.instruction_ref: item for item in program.instructions}
    working = base
    executed: list[int] = []
    for ref in order:
        item = by_ref[ref]
        try:
            working = apply_native_operation(working, item.opcode, item.payload, registry)
        except (DSRExecutionError, DSRValidationError) as exc:
            return _failure_result(base, program, str(exc), executed=tuple(executed), failed_ref=ref)
        executed.append(ref)
    final_hash = registered_state_hash(working)
    return ProgramExecutionResult(
        working,
        ProgramExecutionReceipt(
            EXECUTION_SUCCESS,
            program.program_ref,
            base_hash,
            final_hash,
            tuple(executed),
            0,
            "",
        ),
    )
