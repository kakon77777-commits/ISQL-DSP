from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import math
import struct
from concurrent.futures import ThreadPoolExecutor
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
VM_PROGRAM_FORMAT_VERSION = 10
VM_PROGRAM_LEGACY_VERSION = 7
VM_PROGRAM_V8_VERSION = 8
VM_PROGRAM_V9_VERSION = 9

BIND_EXACT = 1
BIND_DYNAMIC = 2

CAP_CONTEXT = EFFECT_CONTEXT
CAP_AXIS = EFFECT_AXIS
CAP_RELATION = EFFECT_RELATION
CAP_PROJECTION = EFFECT_PROJECTION
CAP_TOPOLOGY = EFFECT_TOPOLOGY
CAP_CALL = 1 << 8
CAP_AXIS_READ = 1 << 9
ALL_CAPABILITIES = CAP_CONTEXT | CAP_AXIS | CAP_RELATION | CAP_PROJECTION | CAP_TOPOLOGY | CAP_CALL | CAP_AXIS_READ

VM_OP_CALL = 1001
VM_OP_RETURN = 1002
VM_OP_REPEAT_CALL = 1003
VM_MAX_REPEAT = 1024
VM_OP_LOAD_AXIS = 1101
VM_OP_STORE_AXIS = 1102

VM_OP_CONST = 1201
VM_OP_MOVE = 1202
VM_OP_ADD = 1211
VM_OP_SUB = 1212
VM_OP_MUL = 1213
VM_OP_DIV = 1214
VM_OP_EQ = 1221
VM_OP_LT = 1222
VM_OP_LE = 1223

VM_OP_VECTOR_PACK = 1301
VM_OP_VECTOR_GET = 1302
VM_OP_VECTOR_LEN = 1303
VM_OP_RECORD_PACK = 1311
VM_OP_RECORD_GET = 1312
VM_OP_RECORD_SET = 1313

GUARD_STATE_HASH_EQ = 1
GUARD_AXIS_PRESENT = 2
GUARD_AXIS_ABSENT = 3
GUARD_RELATION_STATUS = 4
GUARD_AXIS_VALUE_EQ = 5

REG_GUARD_INITIALIZED = 1
REG_GUARD_VALUE_EQ = 2

_ZERO_HASH = "0" * 64

TYPE_ANY = 0
TYPE_NULL = 1
TYPE_BOOL = 2
TYPE_INT = 3
TYPE_FLOAT = 4
TYPE_TEXT = 5
TYPE_INTERVAL = 6
TYPE_CANDIDATES = 7
TYPE_VECTOR = 8
TYPE_RECORD = 9
_VALID_MACHINE_TYPES = frozenset({TYPE_ANY, TYPE_NULL, TYPE_BOOL, TYPE_INT, TYPE_FLOAT, TYPE_TEXT, TYPE_INTERVAL, TYPE_CANDIDATES, TYPE_VECTOR, TYPE_RECORD})


def machine_value_type(value: object) -> int:
    from .model import CandidateSetValue, IntervalValue, PointValue, RecordValue, VectorValue
    if isinstance(value, PointValue):
        raw = value.value
        if raw is None: return TYPE_NULL
        if isinstance(raw, bool): return TYPE_BOOL
        if isinstance(raw, int): return TYPE_INT
        if isinstance(raw, float): return TYPE_FLOAT
        if isinstance(raw, str): return TYPE_TEXT
    if isinstance(value, IntervalValue): return TYPE_INTERVAL
    if isinstance(value, CandidateSetValue): return TYPE_CANDIDATES
    if isinstance(value, VectorValue): return TYPE_VECTOR
    if isinstance(value, RecordValue): return TYPE_RECORD
    raise DSRValidationError("VM_MACHINE_VALUE_TYPE_INVALID")


def machine_value_matches_type(value: object, type_tag: int) -> bool:
    if type_tag == TYPE_ANY:
        try:
            _encode_semantic_value(value)
            return True
        except DSRValidationError:
            return False
    try:
        return machine_value_type(value) == type_tag
    except DSRValidationError:
        return False


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
    if opcode in {VM_OP_CALL, VM_OP_RETURN, VM_OP_REPEAT_CALL, VM_OP_LOAD_AXIS, VM_OP_CONST, VM_OP_MOVE, VM_OP_ADD, VM_OP_SUB, VM_OP_MUL, VM_OP_DIV, VM_OP_EQ, VM_OP_LT, VM_OP_LE, VM_OP_VECTOR_PACK, VM_OP_VECTOR_GET, VM_OP_VECTOR_LEN, VM_OP_RECORD_PACK, VM_OP_RECORD_GET, VM_OP_RECORD_SET}:
        return 0
    if opcode == VM_OP_STORE_AXIS:
        return EFFECT_AXIS
    return operator_effect_mask(opcode)


def required_capability_for_opcode(opcode: int) -> int:
    if opcode in {VM_OP_CALL, VM_OP_REPEAT_CALL}:
        return CAP_CALL
    if opcode == VM_OP_RETURN:
        return 0
    if opcode == VM_OP_LOAD_AXIS:
        return CAP_AXIS_READ
    if opcode == VM_OP_STORE_AXIS:
        return CAP_AXIS
    return _expected_effect_mask(opcode)


def encode_load_axis_payload(key_ref: int, destination_register_ref: int) -> bytes:
    return encode_uvarint(_positive(key_ref, "VM_LOAD_AXIS_KEY_INVALID")) + encode_uvarint(
        _positive(destination_register_ref, "VM_LOAD_AXIS_REGISTER_INVALID")
    )


def _decode_load_axis_payload(payload: bytes) -> tuple[int, int]:
    try:
        key_ref, offset = decode_uvarint(payload, 0)
        register_ref, offset = decode_uvarint(payload, offset)
    except Exception as exc:
        raise DSRExecutionError("VM_LOAD_AXIS_PAYLOAD_INVALID") from exc
    if offset != len(payload) or key_ref <= 0 or register_ref <= 0:
        raise DSRExecutionError("VM_LOAD_AXIS_PAYLOAD_INVALID")
    return key_ref, register_ref


def encode_store_axis_payload(
    key_ref: int, domain_ref: int, source_register_ref: int, uncertainty: float = 0.0, resolution: int = 0
) -> bytes:
    key_ref = _positive(key_ref, "VM_STORE_AXIS_KEY_INVALID")
    domain_ref = _positive(domain_ref, "VM_STORE_AXIS_DOMAIN_INVALID")
    source_register_ref = _positive(source_register_ref, "VM_STORE_AXIS_REGISTER_INVALID")
    if isinstance(uncertainty, bool):
        raise DSRValidationError("VM_STORE_AXIS_UNCERTAINTY_INVALID")
    try:
        uncertainty = float(uncertainty)
    except (TypeError, ValueError) as exc:
        raise DSRValidationError("VM_STORE_AXIS_UNCERTAINTY_INVALID") from exc
    if not math.isfinite(uncertainty) or not 0.0 <= uncertainty <= 1.0:
        raise DSRValidationError("VM_STORE_AXIS_UNCERTAINTY_INVALID")
    resolution = _nonnegative(resolution, "VM_STORE_AXIS_RESOLUTION_INVALID")
    return (
        encode_uvarint(key_ref)
        + encode_uvarint(domain_ref)
        + encode_uvarint(source_register_ref)
        + struct.pack(">d", uncertainty)
        + encode_uvarint(resolution)
    )


def _decode_store_axis_payload(payload: bytes) -> tuple[int, int, int, float, int]:
    try:
        key_ref, offset = decode_uvarint(payload, 0)
        domain_ref, offset = decode_uvarint(payload, offset)
        register_ref, offset = decode_uvarint(payload, offset)
    except Exception as exc:
        raise DSRExecutionError("VM_STORE_AXIS_PAYLOAD_INVALID") from exc
    end = offset + 8
    if end > len(payload):
        raise DSRExecutionError("VM_STORE_AXIS_PAYLOAD_INVALID")
    uncertainty = struct.unpack(">d", payload[offset:end])[0]
    offset = end
    try:
        resolution, offset = decode_uvarint(payload, offset)
    except Exception as exc:
        raise DSRExecutionError("VM_STORE_AXIS_PAYLOAD_INVALID") from exc
    if offset != len(payload) or key_ref <= 0 or domain_ref <= 0 or register_ref <= 0:
        raise DSRExecutionError("VM_STORE_AXIS_PAYLOAD_INVALID")
    if not math.isfinite(uncertainty) or not 0.0 <= uncertainty <= 1.0:
        raise DSRExecutionError("VM_STORE_AXIS_PAYLOAD_INVALID")
    return key_ref, domain_ref, register_ref, uncertainty, resolution



def encode_register_const_payload(destination_register_ref: int, value: object) -> bytes:
    destination_register_ref = _positive(destination_register_ref, "VM_CONST_REGISTER_INVALID")
    raw = _encode_semantic_value(value)
    out = bytearray(encode_uvarint(destination_register_ref))
    _write_blob(out, raw)
    return bytes(out)


def _decode_register_const_payload(payload: bytes) -> tuple[int, object]:
    try:
        register_ref, offset = decode_uvarint(payload, 0)
        raw, offset = _read_blob(payload, offset)
        value, used = _decode_semantic_value(raw, 0)
    except Exception as exc:
        raise DSRExecutionError("VM_CONST_PAYLOAD_INVALID") from exc
    if register_ref <= 0 or offset != len(payload) or used != len(raw):
        raise DSRExecutionError("VM_CONST_PAYLOAD_INVALID")
    return register_ref, value


def encode_register_move_payload(source_register_ref: int, destination_register_ref: int) -> bytes:
    return encode_uvarint(_positive(source_register_ref, "VM_MOVE_SOURCE_INVALID")) + encode_uvarint(
        _positive(destination_register_ref, "VM_MOVE_DESTINATION_INVALID")
    )


def _decode_register_move_payload(payload: bytes) -> tuple[int, int]:
    try:
        source, offset = decode_uvarint(payload, 0)
        destination, offset = decode_uvarint(payload, offset)
    except Exception as exc:
        raise DSRExecutionError("VM_MOVE_PAYLOAD_INVALID") from exc
    if source <= 0 or destination <= 0 or offset != len(payload):
        raise DSRExecutionError("VM_MOVE_PAYLOAD_INVALID")
    return source, destination


def encode_register_binary_payload(left_register_ref: int, right_register_ref: int, destination_register_ref: int) -> bytes:
    return (
        encode_uvarint(_positive(left_register_ref, "VM_BINARY_LEFT_INVALID"))
        + encode_uvarint(_positive(right_register_ref, "VM_BINARY_RIGHT_INVALID"))
        + encode_uvarint(_positive(destination_register_ref, "VM_BINARY_DESTINATION_INVALID"))
    )


def _decode_register_binary_payload(payload: bytes) -> tuple[int, int, int]:
    try:
        left, offset = decode_uvarint(payload, 0)
        right, offset = decode_uvarint(payload, offset)
        destination, offset = decode_uvarint(payload, offset)
    except Exception as exc:
        raise DSRExecutionError("VM_BINARY_PAYLOAD_INVALID") from exc
    if min(left, right, destination) <= 0 or offset != len(payload):
        raise DSRExecutionError("VM_BINARY_PAYLOAD_INVALID")
    return left, right, destination


def _numeric_point(value: object) -> tuple[int | float, bool]:
    from .model import PointValue
    if not isinstance(value, PointValue) or isinstance(value.value, bool) or not isinstance(value.value, (int, float)):
        raise DSRExecutionError("VM_NUMERIC_TYPE_REQUIRED")
    return value.value, isinstance(value.value, int)


def _execute_register_binary(opcode: int, left: object, right: object) -> object:
    from .model import PointValue
    if opcode == VM_OP_EQ:
        return PointValue(left == right)
    lv, lint = _numeric_point(left)
    rv, rint = _numeric_point(right)
    if opcode == VM_OP_ADD:
        value = lv + rv
    elif opcode == VM_OP_SUB:
        value = lv - rv
    elif opcode == VM_OP_MUL:
        value = lv * rv
    elif opcode == VM_OP_DIV:
        if rv == 0:
            raise DSRExecutionError("VM_DIVISION_BY_ZERO")
        value = float(lv) / float(rv)
    elif opcode == VM_OP_LT:
        return PointValue(lv < rv)
    elif opcode == VM_OP_LE:
        return PointValue(lv <= rv)
    else:
        raise DSRExecutionError("VM_REGISTER_OPCODE_INVALID")
    if opcode != VM_OP_DIV and lint and rint:
        return PointValue(int(value))
    return PointValue(float(value))



def encode_vector_pack_payload(source_registers: tuple[int, ...], destination_register_ref: int) -> bytes:
    if not isinstance(source_registers, tuple):
        raise DSRValidationError("VM_VECTOR_PACK_SOURCES_INVALID")
    out = bytearray(encode_uvarint(len(source_registers)))
    for ref in source_registers:
        out += encode_uvarint(_positive(ref, "VM_VECTOR_PACK_SOURCE_INVALID"))
    out += encode_uvarint(_positive(destination_register_ref, "VM_VECTOR_PACK_DESTINATION_INVALID"))
    return bytes(out)


def _decode_vector_pack_payload(payload: bytes) -> tuple[tuple[int, ...], int]:
    try:
        count, offset = decode_uvarint(payload, 0)
        sources = []
        for _ in range(count):
            ref, offset = decode_uvarint(payload, offset); sources.append(ref)
        destination, offset = decode_uvarint(payload, offset)
    except Exception as exc:
        raise DSRExecutionError("VM_VECTOR_PACK_PAYLOAD_INVALID") from exc
    if offset != len(payload) or any(ref <= 0 for ref in sources) or destination <= 0:
        raise DSRExecutionError("VM_VECTOR_PACK_PAYLOAD_INVALID")
    return tuple(sources), destination


def encode_vector_get_payload(vector_register_ref: int, index_register_ref: int, destination_register_ref: int) -> bytes:
    return (encode_uvarint(_positive(vector_register_ref, "VM_VECTOR_GET_VECTOR_INVALID")) +
            encode_uvarint(_positive(index_register_ref, "VM_VECTOR_GET_INDEX_INVALID")) +
            encode_uvarint(_positive(destination_register_ref, "VM_VECTOR_GET_DESTINATION_INVALID")))


def _decode_vector_get_payload(payload: bytes) -> tuple[int, int, int]:
    try:
        vector_ref, offset = decode_uvarint(payload, 0)
        index_ref, offset = decode_uvarint(payload, offset)
        destination, offset = decode_uvarint(payload, offset)
    except Exception as exc:
        raise DSRExecutionError("VM_VECTOR_GET_PAYLOAD_INVALID") from exc
    if offset != len(payload) or min(vector_ref, index_ref, destination) <= 0:
        raise DSRExecutionError("VM_VECTOR_GET_PAYLOAD_INVALID")
    return vector_ref, index_ref, destination


def encode_vector_len_payload(vector_register_ref: int, destination_register_ref: int) -> bytes:
    return encode_uvarint(_positive(vector_register_ref, "VM_VECTOR_LEN_VECTOR_INVALID")) + encode_uvarint(
        _positive(destination_register_ref, "VM_VECTOR_LEN_DESTINATION_INVALID")
    )


def _decode_vector_len_payload(payload: bytes) -> tuple[int, int]:
    try:
        vector_ref, offset = decode_uvarint(payload, 0)
        destination, offset = decode_uvarint(payload, offset)
    except Exception as exc:
        raise DSRExecutionError("VM_VECTOR_LEN_PAYLOAD_INVALID") from exc
    if offset != len(payload) or min(vector_ref, destination) <= 0:
        raise DSRExecutionError("VM_VECTOR_LEN_PAYLOAD_INVALID")
    return vector_ref, destination


def encode_record_pack_payload(field_sources: tuple[tuple[int, int], ...], destination_register_ref: int) -> bytes:
    if not isinstance(field_sources, tuple):
        raise DSRValidationError("VM_RECORD_PACK_FIELDS_INVALID")
    rows = tuple(sorted(field_sources, key=lambda row: row[0]))
    seen = set()
    out = bytearray(encode_uvarint(len(rows)))
    for row in rows:
        if not isinstance(row, tuple) or len(row) != 2:
            raise DSRValidationError("VM_RECORD_PACK_FIELD_INVALID")
        field_ref, source_ref = row
        field_ref = _positive(field_ref, "VM_RECORD_FIELD_REF_INVALID")
        source_ref = _positive(source_ref, "VM_RECORD_SOURCE_REGISTER_INVALID")
        if field_ref in seen:
            raise DSRValidationError("VM_RECORD_FIELD_DUPLICATE")
        seen.add(field_ref)
        out += encode_uvarint(field_ref) + encode_uvarint(source_ref)
    out += encode_uvarint(_positive(destination_register_ref, "VM_RECORD_DESTINATION_INVALID"))
    return bytes(out)


def _decode_record_pack_payload(payload: bytes) -> tuple[tuple[tuple[int, int], ...], int]:
    try:
        count, offset = decode_uvarint(payload, 0)
        rows = []
        previous = 0
        for _ in range(count):
            field_ref, offset = decode_uvarint(payload, offset)
            source_ref, offset = decode_uvarint(payload, offset)
            if field_ref <= previous or source_ref <= 0:
                raise DSRExecutionError("VM_RECORD_PACK_PAYLOAD_INVALID")
            previous = field_ref
            rows.append((field_ref, source_ref))
        destination, offset = decode_uvarint(payload, offset)
    except DSRExecutionError:
        raise
    except Exception as exc:
        raise DSRExecutionError("VM_RECORD_PACK_PAYLOAD_INVALID") from exc
    if offset != len(payload) or destination <= 0:
        raise DSRExecutionError("VM_RECORD_PACK_PAYLOAD_INVALID")
    return tuple(rows), destination


def encode_record_get_payload(record_register_ref: int, field_ref: int, destination_register_ref: int) -> bytes:
    return (encode_uvarint(_positive(record_register_ref, "VM_RECORD_GET_RECORD_INVALID")) +
            encode_uvarint(_positive(field_ref, "VM_RECORD_GET_FIELD_INVALID")) +
            encode_uvarint(_positive(destination_register_ref, "VM_RECORD_GET_DESTINATION_INVALID")))


def _decode_record_get_payload(payload: bytes) -> tuple[int, int, int]:
    try:
        record_ref, offset = decode_uvarint(payload, 0)
        field_ref, offset = decode_uvarint(payload, offset)
        destination, offset = decode_uvarint(payload, offset)
    except Exception as exc:
        raise DSRExecutionError("VM_RECORD_GET_PAYLOAD_INVALID") from exc
    if offset != len(payload) or min(record_ref, field_ref, destination) <= 0:
        raise DSRExecutionError("VM_RECORD_GET_PAYLOAD_INVALID")
    return record_ref, field_ref, destination


def encode_record_set_payload(record_register_ref: int, field_ref: int, source_register_ref: int, destination_register_ref: int) -> bytes:
    return (encode_uvarint(_positive(record_register_ref, "VM_RECORD_SET_RECORD_INVALID")) +
            encode_uvarint(_positive(field_ref, "VM_RECORD_SET_FIELD_INVALID")) +
            encode_uvarint(_positive(source_register_ref, "VM_RECORD_SET_SOURCE_INVALID")) +
            encode_uvarint(_positive(destination_register_ref, "VM_RECORD_SET_DESTINATION_INVALID")))


def _decode_record_set_payload(payload: bytes) -> tuple[int, int, int, int]:
    try:
        record_ref, offset = decode_uvarint(payload, 0)
        field_ref, offset = decode_uvarint(payload, offset)
        source_ref, offset = decode_uvarint(payload, offset)
        destination, offset = decode_uvarint(payload, offset)
    except Exception as exc:
        raise DSRExecutionError("VM_RECORD_SET_PAYLOAD_INVALID") from exc
    if offset != len(payload) or min(record_ref, field_ref, source_ref, destination) <= 0:
        raise DSRExecutionError("VM_RECORD_SET_PAYLOAD_INVALID")
    return record_ref, field_ref, source_ref, destination


def encode_vm_repeat_call_payload(
    callee_ref: int,
    count: int,
    slot_aliases: tuple[tuple[int, int], ...] = (),
    argument_registers: tuple[int, ...] = (),
    return_registers: tuple[int, ...] = (),
) -> bytes:
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= VM_MAX_REPEAT:
        raise DSRValidationError("VM_REPEAT_COUNT_INVALID")
    call_blob = encode_vm_call_payload(callee_ref, slot_aliases, argument_registers, return_registers)
    out = bytearray(encode_uvarint(count))
    _write_blob(out, call_blob)
    return bytes(out)


def decode_vm_repeat_call_payload(payload: bytes) -> tuple[int, int, tuple[tuple[int, int], ...], tuple[int, ...], tuple[int, ...]]:
    try:
        count, offset = decode_uvarint(payload, 0)
        call_blob, offset = _read_blob(payload, offset)
    except Exception as exc:
        raise DSRValidationError("VM_REPEAT_PAYLOAD_INVALID") from exc
    if offset != len(payload) or not 1 <= count <= VM_MAX_REPEAT:
        raise DSRValidationError("VM_REPEAT_COUNT_INVALID")
    callee_ref, aliases, args, returns = decode_vm_call_payload(call_blob)
    canonical = encode_vm_repeat_call_payload(callee_ref, count, aliases, args, returns)
    if canonical != bytes(payload):
        raise DSRValidationError("VM_REPEAT_PAYLOAD_NONCANONICAL")
    return callee_ref, count, aliases, args, returns


def encode_vm_call_payload(
    callee_ref: int,
    slot_aliases: tuple[tuple[int, int], ...] = (),
    argument_registers: tuple[int, ...] = (),
    return_registers: tuple[int, ...] = (),
) -> bytes:
    callee_ref = _positive(callee_ref, "VM_CALL_CALLEE_REF_INVALID")
    if not isinstance(slot_aliases, tuple):
        raise DSRValidationError("VM_CALL_SLOT_ALIASES_INVALID")
    aliases = tuple(sorted(slot_aliases, key=lambda row: row[0]))
    if any(not isinstance(row, tuple) or len(row) != 2 for row in aliases):
        raise DSRValidationError("VM_CALL_SLOT_ALIASES_INVALID")
    child_refs = []
    caller_refs = []
    for child_ref, caller_ref in aliases:
        child_refs.append(_positive(child_ref, "VM_CALL_CHILD_SLOT_INVALID"))
        caller_refs.append(_positive(caller_ref, "VM_CALL_CALLER_SLOT_INVALID"))
    if len(set(child_refs)) != len(child_refs) or len(set(caller_refs)) != len(caller_refs):
        raise DSRValidationError("VM_CALL_SLOT_ALIAS_DUPLICATE")
    if not isinstance(argument_registers, tuple) or any(
        not isinstance(ref, int) or isinstance(ref, bool) or ref <= 0 for ref in argument_registers
    ):
        raise DSRValidationError("VM_CALL_ARGUMENT_REGISTERS_INVALID")
    if not isinstance(return_registers, tuple) or any(
        not isinstance(ref, int) or isinstance(ref, bool) or ref <= 0 for ref in return_registers
    ):
        raise DSRValidationError("VM_CALL_RETURN_REGISTERS_INVALID")
    if len(set(return_registers)) != len(return_registers):
        raise DSRValidationError("VM_CALL_RETURN_REGISTER_DUPLICATE")
    out = bytearray()
    out += encode_uvarint(callee_ref)
    out += encode_uvarint(len(aliases))
    for child_ref, caller_ref in aliases:
        out += encode_uvarint(child_ref)
        out += encode_uvarint(caller_ref)
    out += encode_uvarint(len(argument_registers))
    for ref in argument_registers:
        out += encode_uvarint(ref)
    out += encode_uvarint(len(return_registers))
    for ref in return_registers:
        out += encode_uvarint(ref)
    return bytes(out)


def decode_vm_call_payload(
    payload: bytes,
) -> tuple[int, tuple[tuple[int, int], ...], tuple[int, ...], tuple[int, ...]]:
    try:
        callee_ref, offset = decode_uvarint(payload, 0)
    except Exception as exc:
        raise DSRValidationError("VM_CALL_PAYLOAD_INVALID") from exc
    if callee_ref <= 0:
        raise DSRValidationError("VM_CALL_PAYLOAD_INVALID")
    if offset == len(payload):
        return callee_ref, (), (), ()
    try:
        alias_count, offset = decode_uvarint(payload, offset)
        aliases = []
        for _ in range(alias_count):
            child_ref, offset = decode_uvarint(payload, offset)
            caller_ref, offset = decode_uvarint(payload, offset)
            aliases.append((child_ref, caller_ref))
        arg_count, offset = decode_uvarint(payload, offset)
        args = []
        for _ in range(arg_count):
            ref, offset = decode_uvarint(payload, offset)
            args.append(ref)
        return_count, offset = decode_uvarint(payload, offset)
        returns = []
        for _ in range(return_count):
            ref, offset = decode_uvarint(payload, offset)
            returns.append(ref)
    except Exception as exc:
        raise DSRValidationError("VM_CALL_PAYLOAD_INVALID") from exc
    if offset != len(payload):
        raise DSRValidationError("VM_CALL_PAYLOAD_INVALID")
    try:
        canonical = encode_vm_call_payload(callee_ref, tuple(aliases), tuple(args), tuple(returns))
    except DSRValidationError as exc:
        raise DSRValidationError("VM_CALL_PAYLOAD_INVALID") from exc
    if canonical != bytes(payload):
        raise DSRValidationError("VM_CALL_PAYLOAD_NONCANONICAL")
    return callee_ref, tuple(aliases), tuple(args), tuple(returns)


@dataclass(frozen=True, slots=True)
class NativeRegisterGuard:
    guard_type: int
    register_ref: int
    payload: bytes = b""

    def __post_init__(self) -> None:
        if self.guard_type not in {REG_GUARD_INITIALIZED, REG_GUARD_VALUE_EQ}:
            raise DSRValidationError("VM_REGISTER_GUARD_TYPE_INVALID")
        object.__setattr__(self, "register_ref", _positive(self.register_ref, "VM_REGISTER_GUARD_REF_INVALID"))
        if not isinstance(self.payload, (bytes, bytearray, memoryview)):
            raise DSRValidationError("VM_REGISTER_GUARD_PAYLOAD_BYTES_REQUIRED")
        raw = bytes(self.payload)
        if self.guard_type == REG_GUARD_INITIALIZED and raw:
            raise DSRValidationError("VM_REGISTER_GUARD_INITIALIZED_PAYLOAD_INVALID")
        if self.guard_type == REG_GUARD_VALUE_EQ:
            try:
                _, used = _decode_semantic_value(raw, 0)
            except Exception as exc:
                raise DSRValidationError("VM_REGISTER_GUARD_VALUE_INVALID") from exc
            if used != len(raw):
                raise DSRValidationError("VM_REGISTER_GUARD_VALUE_TRAILING_DATA")
        object.__setattr__(self, "payload", raw)


def register_guard_initialized(register_ref: int) -> NativeRegisterGuard:
    return NativeRegisterGuard(REG_GUARD_INITIALIZED, register_ref, b"")


def register_guard_value_eq(register_ref: int, value: object) -> NativeRegisterGuard:
    return NativeRegisterGuard(REG_GUARD_VALUE_EQ, register_ref, _encode_semantic_value(value))


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
class VMScopedCapability:
    slot_ref: int
    capability_mask: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "slot_ref", _positive(self.slot_ref, "VM_SCOPED_SLOT_REF_INVALID"))
        if not isinstance(self.capability_mask, int) or isinstance(self.capability_mask, bool) or self.capability_mask < 0:
            raise DSRValidationError("VM_SCOPED_CAPABILITY_INVALID")


@dataclass(frozen=True, slots=True)
class VMRegisterSpec:
    register_ref: int
    type_tag: int = TYPE_ANY

    def __post_init__(self) -> None:
        object.__setattr__(self, "register_ref", _positive(self.register_ref, "VM_SIGNATURE_REGISTER_INVALID"))
        if self.type_tag not in _VALID_MACHINE_TYPES:
            raise DSRValidationError("VM_SIGNATURE_TYPE_INVALID")


@dataclass(frozen=True, slots=True)
class VMFunctionSignature:
    arguments: tuple[VMRegisterSpec, ...] = ()
    returns: tuple[VMRegisterSpec, ...] = ()

    def __post_init__(self) -> None:
        for rows, error in ((self.arguments, "VM_SIGNATURE_ARGUMENTS_INVALID"), (self.returns, "VM_SIGNATURE_RETURNS_INVALID")):
            if not isinstance(rows, tuple) or not all(isinstance(x, VMRegisterSpec) for x in rows):
                raise DSRValidationError(error)
            refs = [x.register_ref for x in rows]
            if len(set(refs)) != len(refs):
                raise DSRValidationError(error)


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
    register_guards: tuple[NativeRegisterGuard, ...] = ()
    predicate_register_ref: int = 0
    predicate_expected: bool = True

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
        if not isinstance(self.register_guards, tuple) or not all(isinstance(x, NativeRegisterGuard) for x in self.register_guards):
            raise DSRValidationError("VM_REGISTER_GUARDS_INVALID")
        object.__setattr__(self, "register_guards", tuple(self.register_guards))
        if not isinstance(self.predicate_register_ref, int) or isinstance(self.predicate_register_ref, bool) or self.predicate_register_ref < 0:
            raise DSRValidationError("VM_PREDICATE_REGISTER_INVALID")
        if not isinstance(self.predicate_expected, bool):
            raise DSRValidationError("VM_PREDICATE_EXPECTED_INVALID")
        if self.predicate_register_ref == 0 and self.predicate_expected is not True:
            raise DSRValidationError("VM_PREDICATE_EXPECTED_NONCANONICAL")
        if self.opcode == VM_OP_RETURN and self.payload:
            raise DSRValidationError("VM_RETURN_PAYLOAD_INVALID")
        if self.opcode == VM_OP_CALL:
            decode_vm_call_payload(self.payload)
        elif self.opcode == VM_OP_REPEAT_CALL:
            decode_vm_repeat_call_payload(self.payload)
        elif self.opcode == VM_OP_CONST:
            _decode_register_const_payload(self.payload)
        elif self.opcode == VM_OP_MOVE:
            _decode_register_move_payload(self.payload)
        elif self.opcode in {VM_OP_ADD, VM_OP_SUB, VM_OP_MUL, VM_OP_DIV, VM_OP_EQ, VM_OP_LT, VM_OP_LE}:
            _decode_register_binary_payload(self.payload)
        elif self.opcode == VM_OP_VECTOR_PACK:
            _decode_vector_pack_payload(self.payload)
        elif self.opcode == VM_OP_VECTOR_GET:
            _decode_vector_get_payload(self.payload)
        elif self.opcode == VM_OP_VECTOR_LEN:
            _decode_vector_len_payload(self.payload)
        elif self.opcode == VM_OP_RECORD_PACK:
            _decode_record_pack_payload(self.payload)
        elif self.opcode == VM_OP_RECORD_GET:
            _decode_record_get_payload(self.payload)
        elif self.opcode == VM_OP_RECORD_SET:
            _decode_record_set_payload(self.payload)


@dataclass(frozen=True, slots=True)
class NativeVMProgram:
    registry_revision: int
    registry_hash: str
    program_ref: int
    capability_mask: int
    bindings: tuple[VMStateBinding, ...]
    instructions: tuple[VMInstruction, ...]
    argument_registers: tuple[int, ...] = ()
    return_registers: tuple[int, ...] = ()
    scoped_capabilities: tuple[VMScopedCapability, ...] = ()
    signature: VMFunctionSignature | None = None

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
            if item.opcode in {VM_OP_CALL, VM_OP_REPEAT_CALL}:
                if item.opcode == VM_OP_CALL:
                    _, aliases, _, _ = decode_vm_call_payload(item.payload)
                else:
                    _, _, aliases, _, _ = decode_vm_repeat_call_payload(item.payload)
                if aliases and any(caller_slot not in slot_set for _, caller_slot in aliases):
                    raise DSRValidationError("VM_CALL_CALLER_SLOT_UNBOUND")
            required_mask |= item.required_capabilities
            if item.opcode == VM_OP_RETURN:
                returns += 1
        if self.capability_mask != required_mask:
            raise DSRValidationError("VM_PROGRAM_CAPABILITY_NONCANONICAL")
        if returns > 1:
            raise DSRValidationError("VM_MULTIPLE_RETURN_INVALID")
        for regs, error in (
            (self.argument_registers, "VM_ARGUMENT_REGISTERS_INVALID"),
            (self.return_registers, "VM_RETURN_REGISTERS_INVALID"),
        ):
            if not isinstance(regs, tuple):
                raise DSRValidationError(error)
            if any(not isinstance(ref, int) or isinstance(ref, bool) or ref <= 0 for ref in regs):
                raise DSRValidationError(error)
            if len(set(regs)) != len(regs):
                raise DSRValidationError(error)
        signature = self.signature
        if signature is None:
            signature = VMFunctionSignature(
                tuple(VMRegisterSpec(ref, TYPE_ANY) for ref in self.argument_registers),
                tuple(VMRegisterSpec(ref, TYPE_ANY) for ref in self.return_registers),
            )
        if not isinstance(signature, VMFunctionSignature):
            raise DSRValidationError("VM_SIGNATURE_INVALID")
        if tuple(x.register_ref for x in signature.arguments) != self.argument_registers:
            raise DSRValidationError("VM_SIGNATURE_ARGUMENT_INTERFACE_MISMATCH")
        if tuple(x.register_ref for x in signature.returns) != self.return_registers:
            raise DSRValidationError("VM_SIGNATURE_RETURN_INTERFACE_MISMATCH")
        object.__setattr__(self, "signature", signature)
        expected_scopes = {binding.slot_ref: 0 for binding in bindings}
        for item in rows:
            expected_scopes[item.target_ref] |= item.required_capabilities
        canonical_scopes = tuple(VMScopedCapability(slot, expected_scopes[slot]) for slot in sorted(expected_scopes))
        if self.scoped_capabilities:
            if not isinstance(self.scoped_capabilities, tuple) or not all(isinstance(x, VMScopedCapability) for x in self.scoped_capabilities):
                raise DSRValidationError("VM_SCOPED_CAPABILITIES_INVALID")
            supplied = tuple(sorted(self.scoped_capabilities, key=lambda x: x.slot_ref))
            if len({x.slot_ref for x in supplied}) != len(supplied):
                raise DSRValidationError("VM_SCOPED_CAPABILITY_DUPLICATE")
            if supplied != canonical_scopes:
                raise DSRValidationError("VM_SCOPED_CAPABILITY_NONCANONICAL")
            object.__setattr__(self, "scoped_capabilities", supplied)
        else:
            object.__setattr__(self, "scoped_capabilities", canonical_scopes)
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


def _instruction_register_access(item: VMInstruction) -> tuple[set[int], set[int]]:
    reads: set[int] = set()
    writes: set[int] = set()
    if item.opcode == VM_OP_LOAD_AXIS:
        _, register_ref = _decode_load_axis_payload(item.payload)
        writes.add(register_ref)
    elif item.opcode == VM_OP_STORE_AXIS:
        _, _, register_ref, _, _ = _decode_store_axis_payload(item.payload)
        reads.add(register_ref)
    elif item.opcode == VM_OP_CONST:
        register_ref, _ = _decode_register_const_payload(item.payload)
        writes.add(register_ref)
    elif item.opcode == VM_OP_MOVE:
        source, destination = _decode_register_move_payload(item.payload)
        reads.add(source); writes.add(destination)
    elif item.opcode in {VM_OP_ADD, VM_OP_SUB, VM_OP_MUL, VM_OP_DIV, VM_OP_EQ, VM_OP_LT, VM_OP_LE}:
        left, right, destination = _decode_register_binary_payload(item.payload)
        reads.update((left, right)); writes.add(destination)
    elif item.opcode == VM_OP_VECTOR_PACK:
        sources, destination = _decode_vector_pack_payload(item.payload)
        reads.update(sources); writes.add(destination)
    elif item.opcode == VM_OP_VECTOR_GET:
        vector_ref, index_ref, destination = _decode_vector_get_payload(item.payload)
        reads.update((vector_ref, index_ref)); writes.add(destination)
    elif item.opcode == VM_OP_VECTOR_LEN:
        vector_ref, destination = _decode_vector_len_payload(item.payload)
        reads.add(vector_ref); writes.add(destination)
    elif item.opcode == VM_OP_RECORD_PACK:
        rows, destination = _decode_record_pack_payload(item.payload)
        reads.update(source_ref for _, source_ref in rows); writes.add(destination)
    elif item.opcode == VM_OP_RECORD_GET:
        record_ref, _, destination = _decode_record_get_payload(item.payload)
        reads.add(record_ref); writes.add(destination)
    elif item.opcode == VM_OP_RECORD_SET:
        record_ref, _, source_ref, destination = _decode_record_set_payload(item.payload)
        reads.update((record_ref, source_ref)); writes.add(destination)
    elif item.opcode == VM_OP_CALL:
        _, _, args, returns = decode_vm_call_payload(item.payload)
        reads.update(args); writes.update(returns)
    elif item.opcode == VM_OP_REPEAT_CALL:
        _, _, _, args, returns = decode_vm_repeat_call_payload(item.payload)
        reads.update(args); writes.update(returns)
    reads.update(guard.register_ref for guard in item.register_guards)
    if item.predicate_register_ref:
        reads.add(item.predicate_register_ref)
    return reads, writes


def _instruction_state_write(item: VMInstruction) -> bool:
    return item.effect_mask != 0


def _instructions_conflict(left: VMInstruction, right: VMInstruction) -> bool:
    if left.opcode in {VM_OP_CALL, VM_OP_RETURN, VM_OP_REPEAT_CALL} or right.opcode in {VM_OP_CALL, VM_OP_RETURN, VM_OP_REPEAT_CALL}:
        return True
    if left.target_ref == right.target_ref and (_instruction_state_write(left) or _instruction_state_write(right)):
        return True
    left_reads, left_writes = _instruction_register_access(left)
    right_reads, right_writes = _instruction_register_access(right)
    if left_writes & (right_reads | right_writes):
        return True
    if right_writes & (left_reads | left_writes):
        return True
    return False


def vm_execution_batches(program: NativeVMProgram) -> tuple[tuple[int, ...], ...]:
    if not isinstance(program, NativeVMProgram):
        raise TypeError("program must be NativeVMProgram")
    by_ref = {item.instruction_ref: item for item in program.instructions}
    remaining = set(by_ref)
    completed: set[int] = set()
    batches: list[tuple[int, ...]] = []
    while remaining:
        ready = [by_ref[ref] for ref in sorted(remaining) if set(by_ref[ref].depends_on) <= completed]
        if not ready:
            raise DSRValidationError("VM_DEPENDENCY_CYCLE")
        first = ready[0]
        if first.opcode in {VM_OP_CALL, VM_OP_RETURN, VM_OP_REPEAT_CALL}:
            batch_items = [first]
        else:
            batch_items: list[VMInstruction] = []
            for item in ready:
                if item.opcode in {VM_OP_CALL, VM_OP_RETURN, VM_OP_REPEAT_CALL}:
                    continue
                if all(not _instructions_conflict(item, chosen) for chosen in batch_items):
                    batch_items.append(item)
            if not batch_items:
                batch_items = [first]
        batch = tuple(item.instruction_ref for item in batch_items)
        batches.append(batch)
        completed.update(batch)
        remaining.difference_update(batch)
    return tuple(batches)


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


def _encode_register_guard(guard: NativeRegisterGuard) -> bytes:
    out = bytearray()
    out += encode_uvarint(guard.guard_type)
    out += encode_uvarint(guard.register_ref)
    _write_blob(out, guard.payload)
    return bytes(out)


def _decode_register_guard(data: bytes, offset: int) -> tuple[NativeRegisterGuard, int]:
    kind, offset = decode_uvarint(data, offset)
    register_ref, offset = decode_uvarint(data, offset)
    payload, offset = _read_blob(data, offset)
    return NativeRegisterGuard(kind, register_ref, payload), offset


def _encode_instruction_v8(item: VMInstruction) -> bytes:
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


def _decode_instruction_v8(data: bytes, offset: int) -> tuple[VMInstruction, int]:
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
    return VMInstruction(instruction_ref, opcode, effect_mask, required_capabilities, target_ref, tuple(deps), tuple(guards), payload), offset


def _encode_instruction(item: VMInstruction) -> bytes:
    out = bytearray(_encode_instruction_v8(item))
    out += encode_uvarint(len(item.register_guards))
    for guard in item.register_guards:
        _write_blob(out, _encode_register_guard(guard))
    out += encode_uvarint(item.predicate_register_ref)
    out += encode_uvarint(1 if item.predicate_expected else 0)
    return bytes(out)


def _decode_instruction(data: bytes, offset: int) -> tuple[VMInstruction, int]:
    base, offset = _decode_instruction_v8(data, offset)
    count, offset = decode_uvarint(data, offset)
    register_guards: list[NativeRegisterGuard] = []
    for _ in range(count):
        blob, offset = _read_blob(data, offset)
        guard, used = _decode_register_guard(blob, 0)
        if used != len(blob):
            raise DSRValidationError("VM_REGISTER_GUARD_TRAILING_DATA")
        register_guards.append(guard)
    predicate_ref, offset = decode_uvarint(data, offset)
    encoded_expected, offset = decode_uvarint(data, offset)
    if encoded_expected not in {0, 1}:
        raise DSRValidationError("VM_PREDICATE_EXPECTED_INVALID")
    return replace(base, register_guards=tuple(register_guards), predicate_register_ref=predicate_ref, predicate_expected=bool(encoded_expected)), offset


def _encode_vm_program_v7(program: NativeVMProgram) -> bytes:
    out = bytearray(VM_PROGRAM_MAGIC)
    out += encode_uvarint(VM_PROGRAM_LEGACY_VERSION)
    out += encode_uvarint(program.registry_revision)
    out += bytes.fromhex(program.registry_hash)
    out += encode_uvarint(program.program_ref)
    out += encode_uvarint(program.capability_mask)
    out += encode_uvarint(len(program.bindings))
    for binding in program.bindings:
        _write_blob(out, _encode_binding(binding))
    out += encode_uvarint(len(program.instructions))
    for item in program.instructions:
        _write_blob(out, _encode_instruction_v8(item))
    return bytes(out)


def _encode_vm_program_v8(program: NativeVMProgram) -> bytes:
    out = bytearray(VM_PROGRAM_MAGIC)
    out += encode_uvarint(VM_PROGRAM_V8_VERSION)
    out += encode_uvarint(program.registry_revision)
    out += bytes.fromhex(program.registry_hash)
    out += encode_uvarint(program.program_ref)
    out += encode_uvarint(program.capability_mask)
    out += encode_uvarint(len(program.bindings))
    for binding in program.bindings:
        _write_blob(out, _encode_binding(binding))
    out += encode_uvarint(len(program.instructions))
    for item in program.instructions:
        _write_blob(out, _encode_instruction_v8(item))
    out += encode_uvarint(len(program.argument_registers))
    for ref in program.argument_registers:
        out += encode_uvarint(ref)
    out += encode_uvarint(len(program.return_registers))
    for ref in program.return_registers:
        out += encode_uvarint(ref)
    out += encode_uvarint(len(program.scoped_capabilities))
    for item in program.scoped_capabilities:
        out += encode_uvarint(item.slot_ref)
        out += encode_uvarint(item.capability_mask)
    return bytes(out)


def _encode_vm_program_v9(program: NativeVMProgram) -> bytes:
    if not isinstance(program, NativeVMProgram):
        raise TypeError("encode_vm_program requires NativeVMProgram")
    out = bytearray(VM_PROGRAM_MAGIC)
    out += encode_uvarint(VM_PROGRAM_V9_VERSION)
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
    out += encode_uvarint(len(program.argument_registers))
    for ref in program.argument_registers:
        out += encode_uvarint(ref)
    out += encode_uvarint(len(program.return_registers))
    for ref in program.return_registers:
        out += encode_uvarint(ref)
    out += encode_uvarint(len(program.scoped_capabilities))
    for item in program.scoped_capabilities:
        out += encode_uvarint(item.slot_ref)
        out += encode_uvarint(item.capability_mask)
    return bytes(out)


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
    out += encode_uvarint(len(program.argument_registers))
    for ref in program.argument_registers:
        out += encode_uvarint(ref)
    out += encode_uvarint(len(program.return_registers))
    for ref in program.return_registers:
        out += encode_uvarint(ref)
    out += encode_uvarint(len(program.scoped_capabilities))
    for item in program.scoped_capabilities:
        out += encode_uvarint(item.slot_ref)
        out += encode_uvarint(item.capability_mask)
    out += encode_uvarint(len(program.signature.arguments))
    for spec in program.signature.arguments:
        out += encode_uvarint(spec.type_tag)
    out += encode_uvarint(len(program.signature.returns))
    for spec in program.signature.returns:
        out += encode_uvarint(spec.type_tag)
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
    if version not in {VM_PROGRAM_LEGACY_VERSION, VM_PROGRAM_V8_VERSION, VM_PROGRAM_V9_VERSION, VM_PROGRAM_FORMAT_VERSION}:
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
        item, used = (_decode_instruction(blob, 0) if version in {VM_PROGRAM_V9_VERSION, VM_PROGRAM_FORMAT_VERSION} else _decode_instruction_v8(blob, 0))
        if used != len(blob):
            raise DSRValidationError("VM_INSTRUCTION_TRAILING_DATA")
        registry.resolve(item.instruction_ref, SymbolNamespace.INSTRUCTION_ID)
        if version in {VM_PROGRAM_V9_VERSION, VM_PROGRAM_FORMAT_VERSION}:
            for guard in item.register_guards:
                registry.resolve(guard.register_ref, SymbolNamespace.REGISTER_ID)
            if item.predicate_register_ref:
                registry.resolve(item.predicate_register_ref, SymbolNamespace.REGISTER_ID)
            reads, writes = _instruction_register_access(item)
            for ref in reads | writes:
                registry.resolve(ref, SymbolNamespace.REGISTER_ID)
        if item.opcode in {VM_OP_CALL, VM_OP_REPEAT_CALL}:
            if item.opcode == VM_OP_CALL:
                callee_ref, aliases, args, returns = decode_vm_call_payload(item.payload)
                if version == VM_PROGRAM_LEGACY_VERSION and (aliases or args or returns):
                    raise DSRValidationError("VM_CALL_PAYLOAD_INVALID")
            else:
                callee_ref, _, aliases, args, returns = decode_vm_repeat_call_payload(item.payload)
            registry.resolve(callee_ref, SymbolNamespace.PROGRAM_ID)
            for child_slot, caller_slot in aliases:
                registry.resolve(child_slot, SymbolNamespace.STATE_SLOT_ID)
                registry.resolve(caller_slot, SymbolNamespace.STATE_SLOT_ID)
            for ref in args + returns:
                registry.resolve(ref, SymbolNamespace.REGISTER_ID)
        instructions.append(item)
    argument_registers: list[int] = []
    return_registers: list[int] = []
    scoped_capabilities: list[VMScopedCapability] = []
    if version in {VM_PROGRAM_V8_VERSION, VM_PROGRAM_V9_VERSION, VM_PROGRAM_FORMAT_VERSION}:
        count, offset = decode_uvarint(raw, offset)
        for _ in range(count):
            ref, offset = decode_uvarint(raw, offset)
            registry.resolve(ref, SymbolNamespace.REGISTER_ID)
            argument_registers.append(ref)
        count, offset = decode_uvarint(raw, offset)
        for _ in range(count):
            ref, offset = decode_uvarint(raw, offset)
            registry.resolve(ref, SymbolNamespace.REGISTER_ID)
            return_registers.append(ref)
        count, offset = decode_uvarint(raw, offset)
        for _ in range(count):
            slot_ref, offset = decode_uvarint(raw, offset)
            mask, offset = decode_uvarint(raw, offset)
            registry.resolve(slot_ref, SymbolNamespace.STATE_SLOT_ID)
            scoped_capabilities.append(VMScopedCapability(slot_ref, mask))
    signature = None
    if version == VM_PROGRAM_FORMAT_VERSION:
        arg_type_count, offset = decode_uvarint(raw, offset)
        if arg_type_count != len(argument_registers):
            raise DSRValidationError("VM_SIGNATURE_ARGUMENT_COUNT_MISMATCH")
        arg_specs = []
        for ref in argument_registers:
            type_tag, offset = decode_uvarint(raw, offset)
            arg_specs.append(VMRegisterSpec(ref, type_tag))
        return_type_count, offset = decode_uvarint(raw, offset)
        if return_type_count != len(return_registers):
            raise DSRValidationError("VM_SIGNATURE_RETURN_COUNT_MISMATCH")
        return_specs = []
        for ref in return_registers:
            type_tag, offset = decode_uvarint(raw, offset)
            return_specs.append(VMRegisterSpec(ref, type_tag))
        signature = VMFunctionSignature(tuple(arg_specs), tuple(return_specs))
    if offset != len(raw):
        raise DSRValidationError("VM_PROGRAM_TRAILING_DATA")
    program = NativeVMProgram(
        registry_revision, registry_hash, program_ref, capability_mask,
        tuple(bindings), tuple(instructions), tuple(argument_registers), tuple(return_registers),
        tuple(scoped_capabilities), signature,
    )
    if version == VM_PROGRAM_LEGACY_VERSION:
        expected = _encode_vm_program_v7(program)
    elif version == VM_PROGRAM_V8_VERSION:
        expected = _encode_vm_program_v8(program)
    elif version == VM_PROGRAM_V9_VERSION:
        expected = _encode_vm_program_v9(program)
    else:
        expected = encode_vm_program(program)
    if expected != raw:
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
    returns: tuple[tuple[int, object], ...] = ()


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
        ref, _, _, _ = decode_vm_call_payload(payload)
    except DSRValidationError as exc:
        raise DSRExecutionError("VM_CALL_PAYLOAD_INVALID") from exc
    return ref


def evaluate_register_guard(guard: NativeRegisterGuard, registers: Mapping[int, object]) -> bool:
    if not isinstance(guard, NativeRegisterGuard):
        raise TypeError("guard must be NativeRegisterGuard")
    if guard.guard_type == REG_GUARD_INITIALIZED:
        return guard.register_ref in registers
    if guard.guard_type == REG_GUARD_VALUE_EQ:
        if guard.register_ref not in registers:
            return False
        expected, used = _decode_semantic_value(guard.payload, 0)
        if used != len(guard.payload):
            raise DSRExecutionError("VM_REGISTER_GUARD_VALUE_INVALID")
        return registers[guard.register_ref] == expected
    raise DSRExecutionError("VM_REGISTER_GUARD_TYPE_INVALID")


def _instruction_control_allows(item: VMInstruction, registers: Mapping[int, object]) -> bool:
    from .model import PointValue
    if item.predicate_register_ref:
        if item.predicate_register_ref not in registers:
            raise DSRExecutionError("VM_PREDICATE_REGISTER_UNINITIALIZED")
        value = registers[item.predicate_register_ref]
        if not isinstance(value, PointValue) or not isinstance(value.value, bool):
            raise DSRExecutionError("VM_PREDICATE_BOOL_REQUIRED")
        if value.value is not item.predicate_expected:
            return False
    for guard in item.register_guards:
        if not evaluate_register_guard(guard, registers):
            raise DSRExecutionError("VM_REGISTER_GUARD_FAILED")
    return True


def _validate_instruction_access(
    program: NativeVMProgram,
    item: VMInstruction,
    actual_slot: int,
    state: object,
    registry: NativeSymbolRegistry,
    granted_scoped_capabilities: Mapping[int, int],
) -> None:
    program_scope = next((x.capability_mask for x in program.scoped_capabilities if x.slot_ref == item.target_ref), 0)
    if item.required_capabilities & ~program_scope:
        raise DSRExecutionError("VM_SCOPED_CAPABILITY_PROGRAM_MISMATCH")
    actual_grant = granted_scoped_capabilities.get(actual_slot, 0)
    if item.required_capabilities & ~actual_grant:
        raise DSRExecutionError("VM_SCOPED_CAPABILITY_DENIED")
    if any(not evaluate_guard(state, guard, registry) for guard in item.guards):
        raise DSRExecutionError("VM_GUARD_FAILED")


def _execute_primitive_item(
    program: NativeVMProgram,
    item: VMInstruction,
    actual_slot: int,
    state: object,
    registry: NativeSymbolRegistry,
    granted_scoped_capabilities: Mapping[int, int],
    register_snapshot: Mapping[int, object],
) -> tuple[object | None, dict[int, object]]:
    from .machine import NativeAxis, NativeSemanticState
    from .stream import apply_native_operation
    if not isinstance(state, NativeSemanticState):
        raise TypeError("states must map slot refs to NativeSemanticState")
    _validate_instruction_access(program, item, actual_slot, state, registry, granted_scoped_capabilities)
    if item.opcode == VM_OP_LOAD_AXIS:
        key_ref, register_ref = _decode_load_axis_payload(item.payload)
        registry.resolve(key_ref, SymbolNamespace.AXIS_KEY)
        registry.resolve(register_ref, SymbolNamespace.REGISTER_ID)
        axis = next((x for x in state.axes if x.key_ref == key_ref), None)
        if axis is None:
            raise DSRExecutionError("AXIS_NOT_FOUND")
        return None, {register_ref: axis.value}
    if item.opcode == VM_OP_STORE_AXIS:
        key_ref, domain_ref, register_ref, uncertainty, resolution = _decode_store_axis_payload(item.payload)
        registry.resolve(key_ref, SymbolNamespace.AXIS_KEY)
        registry.resolve(domain_ref, SymbolNamespace.AXIS_DOMAIN)
        registry.resolve(register_ref, SymbolNamespace.REGISTER_ID)
        if register_ref not in register_snapshot:
            raise DSRExecutionError("VM_REGISTER_UNINITIALIZED")
        value = register_snapshot[register_ref]
        _encode_semantic_value(value)
        axis = NativeAxis(key_ref, domain_ref, value, uncertainty, resolution)
        axes = tuple(x for x in state.axes if x.key_ref != key_ref) + (axis,)
        return replace(state, revision=state.revision + 1, axes=axes), {}
    if item.opcode == VM_OP_CONST:
        destination, value = _decode_register_const_payload(item.payload)
        registry.resolve(destination, SymbolNamespace.REGISTER_ID)
        return None, {destination: value}
    if item.opcode == VM_OP_MOVE:
        source, destination = _decode_register_move_payload(item.payload)
        registry.resolve(source, SymbolNamespace.REGISTER_ID); registry.resolve(destination, SymbolNamespace.REGISTER_ID)
        if source not in register_snapshot:
            raise DSRExecutionError("VM_REGISTER_UNINITIALIZED")
        return None, {destination: register_snapshot[source]}
    if item.opcode in {VM_OP_ADD, VM_OP_SUB, VM_OP_MUL, VM_OP_DIV, VM_OP_EQ, VM_OP_LT, VM_OP_LE}:
        left_ref, right_ref, destination = _decode_register_binary_payload(item.payload)
        for ref in (left_ref, right_ref, destination):
            registry.resolve(ref, SymbolNamespace.REGISTER_ID)
        if left_ref not in register_snapshot or right_ref not in register_snapshot:
            raise DSRExecutionError("VM_REGISTER_UNINITIALIZED")
        value = _execute_register_binary(item.opcode, register_snapshot[left_ref], register_snapshot[right_ref])
        return None, {destination: value}
    if item.opcode == VM_OP_VECTOR_PACK:
        from .model import VectorValue
        sources, destination = _decode_vector_pack_payload(item.payload)
        for ref in sources + (destination,): registry.resolve(ref, SymbolNamespace.REGISTER_ID)
        if any(ref not in register_snapshot for ref in sources): raise DSRExecutionError("VM_REGISTER_UNINITIALIZED")
        return None, {destination: VectorValue(tuple(register_snapshot[ref] for ref in sources))}
    if item.opcode == VM_OP_VECTOR_GET:
        from .model import PointValue, VectorValue
        vector_ref, index_ref, destination = _decode_vector_get_payload(item.payload)
        for ref in (vector_ref,index_ref,destination): registry.resolve(ref, SymbolNamespace.REGISTER_ID)
        if vector_ref not in register_snapshot or index_ref not in register_snapshot: raise DSRExecutionError("VM_REGISTER_UNINITIALIZED")
        vector = register_snapshot[vector_ref]; index = register_snapshot[index_ref]
        if not isinstance(vector, VectorValue): raise DSRExecutionError("VM_VECTOR_TYPE_REQUIRED")
        if not isinstance(index, PointValue) or isinstance(index.value, bool) or not isinstance(index.value, int): raise DSRExecutionError("VM_VECTOR_INDEX_INT_REQUIRED")
        if index.value < 0 or index.value >= len(vector.items): raise DSRExecutionError("VM_VECTOR_INDEX_OUT_OF_RANGE")
        return None, {destination: vector.items[index.value]}
    if item.opcode == VM_OP_VECTOR_LEN:
        from .model import PointValue, VectorValue
        vector_ref, destination = _decode_vector_len_payload(item.payload)
        for ref in (vector_ref,destination): registry.resolve(ref, SymbolNamespace.REGISTER_ID)
        if vector_ref not in register_snapshot: raise DSRExecutionError("VM_REGISTER_UNINITIALIZED")
        vector = register_snapshot[vector_ref]
        if not isinstance(vector, VectorValue): raise DSRExecutionError("VM_VECTOR_TYPE_REQUIRED")
        return None, {destination: PointValue(len(vector.items))}
    if item.opcode == VM_OP_RECORD_PACK:
        from .model import RecordValue
        rows, destination = _decode_record_pack_payload(item.payload)
        registry.resolve(destination, SymbolNamespace.REGISTER_ID)
        fields=[]
        for field_ref, source_ref in rows:
            registry.resolve(field_ref, SymbolNamespace.FIELD_ID); registry.resolve(source_ref, SymbolNamespace.REGISTER_ID)
            if source_ref not in register_snapshot: raise DSRExecutionError("VM_REGISTER_UNINITIALIZED")
            fields.append((field_ref, register_snapshot[source_ref]))
        return None, {destination: RecordValue(tuple(fields))}
    if item.opcode == VM_OP_RECORD_GET:
        from .model import RecordValue
        record_ref, field_ref, destination = _decode_record_get_payload(item.payload)
        registry.resolve(record_ref, SymbolNamespace.REGISTER_ID); registry.resolve(destination, SymbolNamespace.REGISTER_ID); registry.resolve(field_ref, SymbolNamespace.FIELD_ID)
        if record_ref not in register_snapshot: raise DSRExecutionError("VM_REGISTER_UNINITIALIZED")
        record=register_snapshot[record_ref]
        if not isinstance(record, RecordValue): raise DSRExecutionError("VM_RECORD_TYPE_REQUIRED")
        mapping=dict(record.fields)
        if field_ref not in mapping: raise DSRExecutionError("VM_RECORD_FIELD_MISSING")
        return None,{destination:mapping[field_ref]}
    if item.opcode == VM_OP_RECORD_SET:
        from .model import RecordValue
        record_ref, field_ref, source_ref, destination = _decode_record_set_payload(item.payload)
        registry.resolve(record_ref, SymbolNamespace.REGISTER_ID); registry.resolve(source_ref, SymbolNamespace.REGISTER_ID); registry.resolve(destination, SymbolNamespace.REGISTER_ID); registry.resolve(field_ref, SymbolNamespace.FIELD_ID)
        if record_ref not in register_snapshot or source_ref not in register_snapshot: raise DSRExecutionError("VM_REGISTER_UNINITIALIZED")
        record=register_snapshot[record_ref]
        if not isinstance(record, RecordValue): raise DSRExecutionError("VM_RECORD_TYPE_REQUIRED")
        mapping=dict(record.fields); mapping[field_ref]=register_snapshot[source_ref]
        return None,{destination:RecordValue(tuple(mapping.items()))}
    return apply_native_operation(state, item.opcode, item.payload, registry), {}


def _execute_program_frame(
    program: NativeVMProgram,
    working: dict[int, object],
    aliases: Mapping[int, int],
    registry: NativeSymbolRegistry,
    library: Mapping[int, NativeVMProgram],
    granted_capabilities: int,
    granted_scoped_capabilities: Mapping[int, int],
    registers: dict[int, object],
    call_stack: tuple[int, ...],
    trace: list[tuple[int, int]],
    parallel: bool,
) -> None:
    try:
        _validate_program_environment(program, registry, granted_capabilities)
        _validate_bindings(program, working, aliases)
    except (DSRExecutionError, DSRValidationError) as exc:
        raise _VMAbort(str(exc), program.program_ref, 0, trace) from exc

    by_ref = {item.instruction_ref: item for item in program.instructions}
    for batch_refs in vm_execution_batches(program):
        batch_items = [by_ref[ref] for ref in batch_refs]
        if len(batch_items) == 1 and batch_items[0].opcode in {VM_OP_CALL, VM_OP_RETURN, VM_OP_REPEAT_CALL}:
            item = batch_items[0]
            instruction_ref = item.instruction_ref
            actual_slot = aliases.get(item.target_ref)
            if actual_slot is None or actual_slot not in working:
                raise _VMAbort("VM_STATE_SLOT_MISSING", program.program_ref, instruction_ref, trace)
            state = working[actual_slot]
            try:
                if not _instruction_control_allows(item, registers):
                    continue
                _validate_instruction_access(program, item, actual_slot, state, registry, granted_scoped_capabilities)
                if item.opcode == VM_OP_RETURN:
                    trace.append((program.program_ref, instruction_ref))
                    return
                if item.opcode == VM_OP_REPEAT_CALL:
                    callee_ref, repeat_count, slot_aliases, caller_arg_regs, caller_return_regs = decode_vm_repeat_call_payload(item.payload)
                else:
                    callee_ref, slot_aliases, caller_arg_regs, caller_return_regs = decode_vm_call_payload(item.payload)
                    repeat_count = 1
                registry.resolve(callee_ref, SymbolNamespace.PROGRAM_ID)
                if callee_ref in call_stack:
                    raise DSRExecutionError("VM_CALL_CYCLE")
                callee = library.get(callee_ref)
                if callee is None or callee.program_ref != callee_ref:
                    raise DSRExecutionError("VM_CALLEE_NOT_FOUND")
                if not slot_aliases and not caller_arg_regs and not caller_return_regs:
                    if len(callee.bindings) != 1 or callee.bindings[0].binding_mode != BIND_DYNAMIC:
                        raise DSRExecutionError("VM_CALLEE_BINDING_INVALID")
                    callee_aliases = {callee.bindings[0].slot_ref: actual_slot}
                    return_destinations: tuple[int, ...] = ()
                else:
                    if any(binding.binding_mode != BIND_DYNAMIC for binding in callee.bindings):
                        raise DSRExecutionError("VM_CALLEE_BINDING_INVALID")
                    expected_child_slots = {binding.slot_ref for binding in callee.bindings}
                    if {child_slot for child_slot, _ in slot_aliases} != expected_child_slots:
                        raise DSRExecutionError("VM_CALL_MAPPING_INVALID")
                    if len(caller_arg_regs) != len(callee.argument_registers) or len(caller_return_regs) != len(callee.return_registers):
                        raise DSRExecutionError("VM_CALL_MAPPING_INVALID")
                    callee_aliases = {}
                    for child_slot, caller_local_slot in slot_aliases:
                        if caller_local_slot not in aliases:
                            raise DSRExecutionError("VM_CALL_MAPPING_INVALID")
                        callee_aliases[child_slot] = aliases[caller_local_slot]
                    for caller_reg in caller_return_regs:
                        registry.resolve(caller_reg, SymbolNamespace.REGISTER_ID)
                    return_destinations = caller_return_regs
                trace.append((program.program_ref, instruction_ref))
                child_arg_specs = {spec.register_ref: spec for spec in callee.signature.arguments}
                child_return_specs = {spec.register_ref: spec for spec in callee.signature.returns}
                for _ in range(repeat_count):
                    child_registers: dict[int, object] = {}
                    for child_reg, caller_reg in zip(callee.argument_registers, caller_arg_regs):
                        registry.resolve(caller_reg, SymbolNamespace.REGISTER_ID)
                        if caller_reg not in registers:
                            raise DSRExecutionError("VM_REGISTER_UNINITIALIZED")
                        value = registers[caller_reg]
                        if not machine_value_matches_type(value, child_arg_specs[child_reg].type_tag):
                            raise DSRExecutionError("VM_CALL_ARGUMENT_TYPE_MISMATCH")
                        child_registers[child_reg] = value
                    _execute_program_frame(
                        callee, working, callee_aliases, registry, library,
                        granted_capabilities, granted_scoped_capabilities, child_registers,
                        call_stack + (callee_ref,), trace, parallel,
                    )
                    if return_destinations:
                        for child_reg, caller_reg in zip(callee.return_registers, return_destinations):
                            if child_reg not in child_registers:
                                raise DSRExecutionError("VM_RETURN_REGISTER_UNINITIALIZED")
                            value = child_registers[child_reg]
                            if not machine_value_matches_type(value, child_return_specs[child_reg].type_tag):
                                raise DSRExecutionError("VM_CALL_RETURN_TYPE_MISMATCH")
                            registers[caller_reg] = value
            except _VMAbort:
                raise
            except (DSRExecutionError, DSRValidationError) as exc:
                raise _VMAbort(str(exc), program.program_ref, instruction_ref, trace) from exc
            continue

        register_snapshot = dict(registers)
        work_items: list[tuple[VMInstruction, int, object]] = []
        for item in batch_items:
            actual_slot = aliases.get(item.target_ref)
            if actual_slot is None or actual_slot not in working:
                raise _VMAbort("VM_STATE_SLOT_MISSING", program.program_ref, item.instruction_ref, trace)
            work_items.append((item, actual_slot, working[actual_slot]))

        def run_one(row: tuple[VMInstruction, int, object]):
            item, actual_slot, state = row
            if not _instruction_control_allows(item, register_snapshot):
                return None, {}, False
            state_update, register_updates = _execute_primitive_item(
                program, item, actual_slot, state, registry,
                granted_scoped_capabilities, register_snapshot,
            )
            return state_update, register_updates, True

        results: list[tuple[VMInstruction, int, object | None, dict[int, object], bool]] = []
        try:
            if parallel and len(work_items) > 1:
                with ThreadPoolExecutor(max_workers=len(work_items)) as pool:
                    futures = [pool.submit(run_one, row) for row in work_items]
                    for row, future in zip(work_items, futures):
                        state_update, register_updates, executed = future.result()
                        results.append((row[0], row[1], state_update, register_updates, executed))
            else:
                for row in work_items:
                    state_update, register_updates, executed = run_one(row)
                    results.append((row[0], row[1], state_update, register_updates, executed))
        except (DSRExecutionError, DSRValidationError) as exc:
            failed_ref = 0
            if parallel and len(work_items) > 1:
                # Re-evaluate in canonical ref order only to identify the deterministic failing instruction.
                for row in work_items:
                    try:
                        run_one(row)
                    except (DSRExecutionError, DSRValidationError) as inner:
                        failed_ref = row[0].instruction_ref
                        exc = inner
                        break
            if failed_ref == 0:
                # Serial path or a defensive fallback.
                for row in work_items:
                    try:
                        run_one(row)
                    except (DSRExecutionError, DSRValidationError) as inner:
                        failed_ref = row[0].instruction_ref
                        exc = inner
                        break
            raise _VMAbort(str(exc), program.program_ref, failed_ref, trace) from exc

        for item, actual_slot, state_update, register_updates, executed in sorted(results, key=lambda row: row[0].instruction_ref):
            if not executed:
                continue
            if state_update is not None:
                working[actual_slot] = state_update
            registers.update(register_updates)
            trace.append((program.program_ref, item.instruction_ref))


def execute_vm_transaction(
    states: Mapping[int, object],
    program: NativeVMProgram,
    registry: NativeSymbolRegistry,
    program_library: Mapping[int, NativeVMProgram] | None = None,
    granted_capabilities: int = ALL_CAPABILITIES,
    arguments: Mapping[int, object] | None = None,
    granted_scoped_capabilities: Mapping[int, int] | None = None,
    parallel: bool = False,
) -> VMTransactionResult:
    if not isinstance(program, NativeVMProgram):
        raise TypeError("program must be NativeVMProgram")
    if not isinstance(registry, NativeSymbolRegistry):
        raise TypeError("registry must be NativeSymbolRegistry")
    if not isinstance(granted_capabilities, int) or isinstance(granted_capabilities, bool) or granted_capabilities < 0:
        raise DSRValidationError("VM_GRANTED_CAPABILITIES_INVALID")
    if granted_scoped_capabilities is not None and not isinstance(granted_scoped_capabilities, Mapping):
        raise DSRValidationError("VM_GRANTED_SCOPED_CAPABILITIES_INVALID")
    if not isinstance(parallel, bool):
        raise DSRValidationError("VM_PARALLEL_FLAG_INVALID")
    originals = dict(states)
    base_hashes = _state_hash_rows(originals)
    supplied_arguments = dict(arguments or {})
    declared_arguments = set(program.argument_registers)
    supplied_refs = set(supplied_arguments)
    if supplied_refs - declared_arguments:
        return VMTransactionResult(
            originals,
            VMTransactionReceipt(
                EXECUTION_FAILED, program.program_ref, base_hashes, base_hashes,
                (), program.program_ref, 0, "VM_ARGUMENT_UNDECLARED",
            ),
            (),
        )
    if declared_arguments - supplied_refs:
        return VMTransactionResult(
            originals,
            VMTransactionReceipt(
                EXECUTION_FAILED, program.program_ref, base_hashes, base_hashes,
                (), program.program_ref, 0, "VM_ARGUMENT_MISSING",
            ),
            (),
        )
    registers: dict[int, object] = {}
    try:
        arg_specs = {spec.register_ref: spec for spec in program.signature.arguments}
        for ref in program.argument_registers:
            registry.resolve(ref, SymbolNamespace.REGISTER_ID)
            value = supplied_arguments[ref]
            _encode_semantic_value(value)
            if not machine_value_matches_type(value, arg_specs[ref].type_tag):
                raise DSRExecutionError("VM_ARGUMENT_TYPE_MISMATCH")
            registers[ref] = value
    except DSRExecutionError as exc:
        return VMTransactionResult(
            originals,
            VMTransactionReceipt(
                EXECUTION_FAILED, program.program_ref, base_hashes, base_hashes,
                (), program.program_ref, 0, str(exc),
            ),
            (),
        )
    except (DSRValidationError, TypeError, ValueError) as exc:
        return VMTransactionResult(
            originals,
            VMTransactionReceipt(
                EXECUTION_FAILED, program.program_ref, base_hashes, base_hashes,
                (), program.program_ref, 0, "VM_ARGUMENT_VALUE_INVALID",
            ),
            (),
        )
    working = dict(originals)
    library = dict(program_library or {})
    if granted_scoped_capabilities is None:
        scoped_grants = {slot_ref: granted_capabilities for slot_ref in originals}
    else:
        scoped_grants = {}
        for slot_ref, mask in granted_scoped_capabilities.items():
            if not isinstance(slot_ref, int) or isinstance(slot_ref, bool) or slot_ref <= 0:
                raise DSRValidationError("VM_GRANTED_SCOPED_SLOT_INVALID")
            if not isinstance(mask, int) or isinstance(mask, bool) or mask < 0:
                raise DSRValidationError("VM_GRANTED_SCOPED_CAPABILITY_INVALID")
            scoped_grants[slot_ref] = mask
    root_aliases = {binding.slot_ref: binding.slot_ref for binding in program.bindings}
    trace: list[tuple[int, int]] = []
    try:
        _execute_program_frame(
            program, working, root_aliases, registry, library,
            granted_capabilities, scoped_grants, registers,
            (program.program_ref,), trace, parallel,
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
    try:
        return_values = tuple((ref, registers[ref]) for ref in program.return_registers)
        return_specs = {spec.register_ref: spec for spec in program.signature.returns}
        if any(not machine_value_matches_type(value, return_specs[ref].type_tag) for ref, value in return_values):
            return VMTransactionResult(
                originals,
                VMTransactionReceipt(
                    EXECUTION_FAILED, program.program_ref, base_hashes, base_hashes,
                    tuple(trace), program.program_ref, 0, "VM_RETURN_TYPE_MISMATCH",
                ),
                (),
            )
    except KeyError:
        return VMTransactionResult(
            originals,
            VMTransactionReceipt(
                EXECUTION_FAILED, program.program_ref, base_hashes, base_hashes,
                tuple(trace), program.program_ref, 0, "VM_RETURN_REGISTER_UNINITIALIZED",
            ),
            (),
        )
    return VMTransactionResult(
        working,
        VMTransactionReceipt(
            EXECUTION_SUCCESS, program.program_ref, base_hashes, final_hashes,
            tuple(trace), 0, 0, "",
        ),
        return_values,
    )
