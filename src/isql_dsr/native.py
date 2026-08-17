from __future__ import annotations

import math
import struct
from typing import Any

from .errors import DSRValidationError
from .model import JSONValue

# Primitive type tags. These are protocol constants, not human-facing schema names.
T_NULL = 0
T_FALSE = 1
T_TRUE = 2
T_SINT = 3
T_FLOAT64 = 4
T_TEXT = 5
T_LIST = 6
T_MAP = 7


def encode_uvarint(value: int) -> bytes:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DSRValidationError("NATIVE_UVARINT_INVALID")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def decode_uvarint(data: bytes, offset: int = 0) -> tuple[int, int]:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise DSRValidationError("NATIVE_BYTES_REQUIRED")
    if not isinstance(offset, int) or offset < 0:
        raise DSRValidationError("NATIVE_OFFSET_INVALID")
    value = 0
    shift = 0
    start = offset
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            if data[start:offset] != encode_uvarint(value):
                raise DSRValidationError("NATIVE_UVARINT_NONCANONICAL")
            return value, offset
        shift += 7
        if shift > 70:
            raise DSRValidationError("NATIVE_UVARINT_TOO_LARGE")
    raise DSRValidationError("NATIVE_UVARINT_TRUNCATED")


def _zigzag_encode(value: int) -> int:
    return value * 2 if value >= 0 else (-value * 2) - 1


def _zigzag_decode(value: int) -> int:
    return value // 2 if value % 2 == 0 else -(value // 2) - 1


def _encode_text_bytes(value: str) -> bytes:
    raw = value.encode("utf-8")
    return encode_uvarint(len(raw)) + raw


def _decode_text_bytes(data: bytes, offset: int) -> tuple[str, int]:
    length, offset = decode_uvarint(data, offset)
    end = offset + length
    if end > len(data):
        raise DSRValidationError("NATIVE_TEXT_TRUNCATED")
    try:
        value = bytes(data[offset:end]).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DSRValidationError("NATIVE_TEXT_INVALID_UTF8") from exc
    return value, end


def encode_value(value: JSONValue) -> bytes:
    if value is None:
        return bytes((T_NULL,))
    if value is False:
        return bytes((T_FALSE,))
    if value is True:
        return bytes((T_TRUE,))
    if isinstance(value, int) and not isinstance(value, bool):
        return bytes((T_SINT,)) + encode_uvarint(_zigzag_encode(value))
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DSRValidationError("NATIVE_FLOAT_NONFINITE")
        return bytes((T_FLOAT64,)) + struct.pack(">d", value)
    if isinstance(value, str):
        return bytes((T_TEXT,)) + _encode_text_bytes(value)
    if isinstance(value, list):
        out = bytearray((T_LIST,))
        out += encode_uvarint(len(value))
        for item in value:
            out += encode_value(item)
        return bytes(out)
    if isinstance(value, dict):
        encoded_items: list[tuple[bytes, bytes]] = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise DSRValidationError("NATIVE_MAP_KEY_MUST_BE_TEXT")
            key_bytes = key.encode("utf-8")
            encoded_items.append((key_bytes, encode_value(item)))
        encoded_items.sort(key=lambda pair: pair[0])
        out = bytearray((T_MAP,))
        out += encode_uvarint(len(encoded_items))
        for key_bytes, item_bytes in encoded_items:
            out += encode_uvarint(len(key_bytes))
            out += key_bytes
            out += item_bytes
        return bytes(out)
    raise DSRValidationError("NATIVE_VALUE_TYPE_UNSUPPORTED")


def decode_value(data: bytes, offset: int = 0) -> tuple[JSONValue, int]:
    if offset >= len(data):
        raise DSRValidationError("NATIVE_VALUE_TRUNCATED")
    tag = data[offset]
    offset += 1
    if tag == T_NULL:
        return None, offset
    if tag == T_FALSE:
        return False, offset
    if tag == T_TRUE:
        return True, offset
    if tag == T_SINT:
        value, offset = decode_uvarint(data, offset)
        return _zigzag_decode(value), offset
    if tag == T_FLOAT64:
        end = offset + 8
        if end > len(data):
            raise DSRValidationError("NATIVE_FLOAT_TRUNCATED")
        value = struct.unpack(">d", bytes(data[offset:end]))[0]
        if not math.isfinite(value):
            raise DSRValidationError("NATIVE_FLOAT_NONFINITE")
        return value, end
    if tag == T_TEXT:
        return _decode_text_bytes(data, offset)
    if tag == T_LIST:
        count, offset = decode_uvarint(data, offset)
        out: list[JSONValue] = []
        for _ in range(count):
            item, offset = decode_value(data, offset)
            out.append(item)
        return out, offset
    if tag == T_MAP:
        count, offset = decode_uvarint(data, offset)
        out: dict[str, JSONValue] = {}
        previous_key: bytes | None = None
        for _ in range(count):
            length, offset = decode_uvarint(data, offset)
            end = offset + length
            if end > len(data):
                raise DSRValidationError("NATIVE_MAP_KEY_TRUNCATED")
            raw_key = bytes(data[offset:end])
            offset = end
            if previous_key is not None and raw_key <= previous_key:
                raise DSRValidationError("NATIVE_MAP_KEYS_NONCANONICAL")
            previous_key = raw_key
            try:
                key = raw_key.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise DSRValidationError("NATIVE_MAP_KEY_INVALID_UTF8") from exc
            item, offset = decode_value(data, offset)
            out[key] = item
        return out, offset
    raise DSRValidationError("NATIVE_VALUE_TAG_UNKNOWN")

# State wire constants. Layout is fixed and field-name-free.
NATIVE_MAGIC = bytes((0xD5, 0x51, 0xA9, 0x05))
NATIVE_FORMAT_VERSION = 5

V_POINT = 0
V_INTERVAL = 1
V_CANDIDATES = 2


def _write_text(out: bytearray, value: str) -> None:
    raw = value.encode("utf-8")
    out += encode_uvarint(len(raw))
    out += raw


def _read_text(data: bytes, offset: int) -> tuple[str, int]:
    return _decode_text_bytes(data, offset)


def _write_f64(out: bytearray, value: float) -> None:
    if not math.isfinite(float(value)):
        raise DSRValidationError("NATIVE_FLOAT_NONFINITE")
    out += struct.pack(">d", float(value))


def _read_f64(data: bytes, offset: int) -> tuple[float, int]:
    end = offset + 8
    if end > len(data):
        raise DSRValidationError("NATIVE_FLOAT_TRUNCATED")
    value = struct.unpack(">d", bytes(data[offset:end]))[0]
    if not math.isfinite(value):
        raise DSRValidationError("NATIVE_FLOAT_NONFINITE")
    return value, end


def _write_blob(out: bytearray, blob: bytes) -> None:
    out += encode_uvarint(len(blob))
    out += blob


def _read_blob(data: bytes, offset: int) -> tuple[bytes, int]:
    length, offset = decode_uvarint(data, offset)
    end = offset + length
    if end > len(data):
        raise DSRValidationError("NATIVE_BLOB_TRUNCATED")
    return bytes(data[offset:end]), end


def _encode_semantic_value(value: Any) -> bytes:
    from .model import CandidateSetValue, IntervalValue, PointValue

    out = bytearray()
    if isinstance(value, PointValue):
        out.append(V_POINT)
        out += encode_value(value.value)
    elif isinstance(value, IntervalValue):
        out.append(V_INTERVAL)
        _write_f64(out, value.lower)
        _write_f64(out, value.upper)
    elif isinstance(value, CandidateSetValue):
        out.append(V_CANDIDATES)
        out += encode_uvarint(len(value.values))
        for item in value.values:
            out += encode_value(item)
    else:
        raise DSRValidationError("NATIVE_SEMANTIC_VALUE_UNSUPPORTED")
    return bytes(out)


def _decode_semantic_value(data: bytes, offset: int) -> tuple[Any, int]:
    from .model import CandidateSetValue, IntervalValue, PointValue

    if offset >= len(data):
        raise DSRValidationError("NATIVE_SEMANTIC_VALUE_TRUNCATED")
    tag = data[offset]
    offset += 1
    if tag == V_POINT:
        value, offset = decode_value(data, offset)
        if isinstance(value, (list, dict)):
            raise DSRValidationError("NATIVE_POINT_NOT_SCALAR")
        return PointValue(value), offset
    if tag == V_INTERVAL:
        lower, offset = _read_f64(data, offset)
        upper, offset = _read_f64(data, offset)
        return IntervalValue(lower, upper), offset
    if tag == V_CANDIDATES:
        count, offset = decode_uvarint(data, offset)
        values = []
        for _ in range(count):
            value, offset = decode_value(data, offset)
            if isinstance(value, (list, dict)):
                raise DSRValidationError("NATIVE_CANDIDATE_NOT_SCALAR")
            values.append(value)
        return CandidateSetValue(tuple(values)), offset
    raise DSRValidationError("NATIVE_SEMANTIC_VALUE_TAG_UNKNOWN")


def encode_state(state: Any) -> bytes:
    from .model import SemanticState

    if not isinstance(state, SemanticState):
        raise TypeError("encode_state requires SemanticState")
    out = bytearray(NATIVE_MAGIC)
    out += encode_uvarint(NATIVE_FORMAT_VERSION)
    _write_text(out, state.identity)
    out += encode_uvarint(state.revision)
    _write_blob(out, encode_value(state.context))

    out += encode_uvarint(len(state.axes))
    for axis in state.axes:
        _write_text(out, axis.key)
        _write_text(out, axis.domain)
        _write_blob(out, _encode_semantic_value(axis.value))
        _write_f64(out, axis.uncertainty)
        out += encode_uvarint(axis.resolution)

    out += encode_uvarint(len(state.relations))
    for relation in state.relations:
        _write_text(out, relation.subject)
        _write_text(out, relation.predicate)
        _write_text(out, relation.object)

    out += encode_uvarint(len(state.negative_relations))
    for relation in state.negative_relations:
        _write_text(out, relation.subject)
        _write_text(out, relation.predicate)
        _write_text(out, relation.object)

    out += encode_uvarint(len(state.topology))
    for descriptor in state.topology:
        _write_text(out, descriptor.descriptor_id)
        _write_text(out, descriptor.method)
        try:
            basis = bytes.fromhex(descriptor.basis_hash)
        except ValueError as exc:
            raise DSRValidationError("NATIVE_TOPOLOGY_HASH_INVALID") from exc
        if len(basis) != 32:
            raise DSRValidationError("NATIVE_TOPOLOGY_HASH_INVALID")
        out += basis
        _write_blob(out, encode_value(descriptor.value))
        _write_f64(out, descriptor.confidence)
        _write_blob(out, encode_value(descriptor.parameters))

    out += encode_uvarint(len(state.projections))
    for projection in state.projections:
        _write_text(out, projection.projection_id)
        _write_text(out, projection.media_type)
        _write_blob(out, encode_value(projection.payload))

    out += encode_uvarint(len(state.history))
    for record in state.history:
        _write_blob(out, _encode_history_record(record))
    return bytes(out)


def decode_state(data: bytes) -> Any:
    from .model import SemanticProjection, SemanticState, SpectrumAxis, TopologyDescriptor, TypedRelation

    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise DSRValidationError("NATIVE_BYTES_REQUIRED")
    data = bytes(data)
    if not data.startswith(NATIVE_MAGIC):
        raise DSRValidationError("NATIVE_MAGIC_INVALID")
    offset = len(NATIVE_MAGIC)
    version, offset = decode_uvarint(data, offset)
    if version != NATIVE_FORMAT_VERSION:
        raise DSRValidationError("NATIVE_FORMAT_VERSION_UNSUPPORTED")
    identity, offset = _read_text(data, offset)
    revision, offset = decode_uvarint(data, offset)

    blob, offset = _read_blob(data, offset)
    context, used = decode_value(blob)
    if used != len(blob) or not isinstance(context, dict):
        raise DSRValidationError("NATIVE_CONTEXT_INVALID")

    axis_count, offset = decode_uvarint(data, offset)
    axes = []
    for _ in range(axis_count):
        key, offset = _read_text(data, offset)
        domain, offset = _read_text(data, offset)
        blob, offset = _read_blob(data, offset)
        semantic_value, used = _decode_semantic_value(blob, 0)
        if used != len(blob):
            raise DSRValidationError("NATIVE_AXIS_VALUE_TRAILING_DATA")
        uncertainty, offset = _read_f64(data, offset)
        resolution, offset = decode_uvarint(data, offset)
        axes.append(SpectrumAxis(key, domain, semantic_value, uncertainty, resolution))

    relation_count, offset = decode_uvarint(data, offset)
    relations = []
    for _ in range(relation_count):
        subject, offset = _read_text(data, offset)
        predicate, offset = _read_text(data, offset)
        obj, offset = _read_text(data, offset)
        relations.append(TypedRelation(subject, predicate, obj))

    negative_relation_count, offset = decode_uvarint(data, offset)
    negative_relations = []
    for _ in range(negative_relation_count):
        subject, offset = _read_text(data, offset)
        predicate, offset = _read_text(data, offset)
        obj, offset = _read_text(data, offset)
        negative_relations.append(TypedRelation(subject, predicate, obj))

    topology_count, offset = decode_uvarint(data, offset)
    topology = []
    for _ in range(topology_count):
        descriptor_id, offset = _read_text(data, offset)
        method, offset = _read_text(data, offset)
        end = offset + 32
        if end > len(data):
            raise DSRValidationError("NATIVE_TOPOLOGY_HASH_TRUNCATED")
        basis_hash = data[offset:end].hex()
        offset = end
        blob, offset = _read_blob(data, offset)
        value, used = decode_value(blob)
        if used != len(blob):
            raise DSRValidationError("NATIVE_TOPOLOGY_VALUE_TRAILING_DATA")
        confidence, offset = _read_f64(data, offset)
        blob, offset = _read_blob(data, offset)
        parameters, used = decode_value(blob)
        if used != len(blob) or not isinstance(parameters, dict):
            raise DSRValidationError("NATIVE_TOPOLOGY_PARAMETERS_INVALID")
        topology.append(TopologyDescriptor(descriptor_id, method, basis_hash, value, confidence, parameters))

    projection_count, offset = decode_uvarint(data, offset)
    projections = []
    for _ in range(projection_count):
        projection_id, offset = _read_text(data, offset)
        media_type, offset = _read_text(data, offset)
        blob, offset = _read_blob(data, offset)
        payload, used = decode_value(blob)
        if used != len(blob):
            raise DSRValidationError("NATIVE_PROJECTION_TRAILING_DATA")
        projections.append(SemanticProjection(projection_id, media_type, payload))

    history_count, offset = decode_uvarint(data, offset)
    history = []
    for _ in range(history_count):
        blob, offset = _read_blob(data, offset)
        record, used = _decode_history_record(blob, 0)
        if used != len(blob):
            raise DSRValidationError("NATIVE_HISTORY_RECORD_TRAILING_DATA")
        history.append(record)

    if offset != len(data):
        raise DSRValidationError("NATIVE_STATE_TRAILING_DATA")
    state = SemanticState(
        identity=identity,
        revision=revision,
        context=context,
        axes=tuple(axes),
        relations=tuple(relations),
        negative_relations=tuple(negative_relations),
        topology=tuple(topology),
        projections=tuple(projections),
        history=tuple(history),
    )
    if encode_state(state) != data:
        raise DSRValidationError("NATIVE_STATE_NONCANONICAL")
    return state


def native_state_hash(state: Any) -> str:
    import hashlib

    return hashlib.sha256(encode_state(state)).hexdigest()

_OPERATION_CODES = {
    "set_context": 1,
    "upsert_axis": 2,
    "remove_axis": 3,
    "upsert_relation": 4,
    "remove_relation": 5,
    "upsert_projection": 6,
    "remove_projection": 7,
    "refresh_topology": 8,
    "upsert_topology_descriptor": 9,
    "remove_topology_descriptor": 10,
    "fuse_proposals": 11,
    "deny_relation": 12,
    "retract_relation": 13,
}
_CODE_OPERATIONS = {value: key for key, value in _OPERATION_CODES.items()}


def operation_opcode(name: str) -> int:
    try:
        return _OPERATION_CODES[name]
    except KeyError as exc:
        raise DSRValidationError("NATIVE_EVENT_OPERATION_UNKNOWN") from exc


def operation_name(code: int) -> str:
    try:
        return _CODE_OPERATIONS[code]
    except KeyError as exc:
        raise DSRValidationError("NATIVE_EVENT_OPCODE_UNKNOWN") from exc


def _hash_bytes(value: str) -> bytes:
    try:
        raw = bytes.fromhex(value)
    except (TypeError, ValueError) as exc:
        raise DSRValidationError("NATIVE_HASH_INVALID") from exc
    if len(raw) != 32:
        raise DSRValidationError("NATIVE_HASH_INVALID")
    return raw


def _encode_axis_dict(value: Any) -> bytes:
    from .model import SpectrumAxis
    axis = SpectrumAxis.from_dict(value)
    out = bytearray()
    _write_text(out, axis.key)
    _write_text(out, axis.domain)
    _write_blob(out, _encode_semantic_value(axis.value))
    _write_f64(out, axis.uncertainty)
    out += encode_uvarint(axis.resolution)
    return bytes(out)


def _decode_axis_dict(data: bytes, offset: int) -> tuple[dict[str, Any], int]:
    from .model import SpectrumAxis
    key, offset = _read_text(data, offset)
    domain, offset = _read_text(data, offset)
    blob, offset = _read_blob(data, offset)
    value, used = _decode_semantic_value(blob, 0)
    if used != len(blob):
        raise DSRValidationError("NATIVE_AXIS_VALUE_TRAILING_DATA")
    uncertainty, offset = _read_f64(data, offset)
    resolution, offset = decode_uvarint(data, offset)
    return SpectrumAxis(key, domain, value, uncertainty, resolution).to_dict(), offset


def _encode_relation_dict(value: Any) -> bytes:
    from .model import TypedRelation
    relation = TypedRelation.from_dict(value)
    out = bytearray()
    _write_text(out, relation.subject)
    _write_text(out, relation.predicate)
    _write_text(out, relation.object)
    return bytes(out)


def _decode_relation_dict(data: bytes, offset: int) -> tuple[dict[str, str], int]:
    from .model import TypedRelation
    subject, offset = _read_text(data, offset)
    predicate, offset = _read_text(data, offset)
    obj, offset = _read_text(data, offset)
    return TypedRelation(subject, predicate, obj).to_dict(), offset


def _encode_projection_dict(value: Any) -> bytes:
    from .model import SemanticProjection
    projection = SemanticProjection.from_dict(value)
    out = bytearray()
    _write_text(out, projection.projection_id)
    _write_text(out, projection.media_type)
    _write_blob(out, encode_value(projection.payload))
    return bytes(out)


def _decode_projection_dict(data: bytes, offset: int) -> tuple[dict[str, Any], int]:
    from .model import SemanticProjection
    projection_id, offset = _read_text(data, offset)
    media_type, offset = _read_text(data, offset)
    blob, offset = _read_blob(data, offset)
    payload, used = decode_value(blob)
    if used != len(blob):
        raise DSRValidationError("NATIVE_PROJECTION_TRAILING_DATA")
    return SemanticProjection(projection_id, media_type, payload).to_dict(), offset


def _encode_topology_dict(value: Any) -> bytes:
    from .model import TopologyDescriptor
    descriptor = TopologyDescriptor.from_dict(value)
    out = bytearray()
    _write_text(out, descriptor.descriptor_id)
    _write_text(out, descriptor.method)
    out += _hash_bytes(descriptor.basis_hash)
    _write_blob(out, encode_value(descriptor.value))
    _write_f64(out, descriptor.confidence)
    _write_blob(out, encode_value(descriptor.parameters))
    return bytes(out)


def _decode_topology_dict(data: bytes, offset: int) -> tuple[dict[str, Any], int]:
    from .model import TopologyDescriptor
    descriptor_id, offset = _read_text(data, offset)
    method, offset = _read_text(data, offset)
    end = offset + 32
    if end > len(data):
        raise DSRValidationError("NATIVE_HASH_TRUNCATED")
    basis_hash = data[offset:end].hex()
    offset = end
    blob, offset = _read_blob(data, offset)
    value, used = decode_value(blob)
    if used != len(blob):
        raise DSRValidationError("NATIVE_TOPOLOGY_VALUE_TRAILING_DATA")
    confidence, offset = _read_f64(data, offset)
    blob, offset = _read_blob(data, offset)
    parameters, used = decode_value(blob)
    if used != len(blob) or not isinstance(parameters, dict):
        raise DSRValidationError("NATIVE_TOPOLOGY_PARAMETERS_INVALID")
    return TopologyDescriptor(descriptor_id, method, basis_hash, value, confidence, parameters).to_dict(), offset




def _encode_proposal_dict(value: Any) -> bytes:
    from .fusion import SemanticProposal
    proposal = SemanticProposal.from_dict(value)
    out = bytearray()
    _write_text(out, proposal.proposal_id)
    _write_text(out, proposal.source_id)
    _write_text(out, proposal.identity)
    out += encode_uvarint(proposal.base_revision)
    out += _hash_bytes(proposal.base_hash)
    _write_f64(out, proposal.source_weight)
    out += encode_uvarint(len(proposal.axes))
    for axis in proposal.axes:
        _write_blob(out, _encode_axis_dict(axis.to_dict()))
    out += encode_uvarint(len(proposal.relations))
    for relation in proposal.relations:
        _write_blob(out, _encode_relation_dict(relation.to_dict()))
    out += encode_uvarint(len(proposal.negative_relations))
    for relation in proposal.negative_relations:
        _write_blob(out, _encode_relation_dict(relation.to_dict()))
    out.append(1 if proposal.produced_at is not None else 0)
    if proposal.produced_at is not None:
        _write_text(out, proposal.produced_at)
    return bytes(out)


def _decode_proposal_dict(data: bytes, offset: int) -> tuple[dict[str, Any], int]:
    from .fusion import SemanticProposal
    from .model import SpectrumAxis, TypedRelation
    proposal_id, offset = _read_text(data, offset)
    source_id, offset = _read_text(data, offset)
    identity, offset = _read_text(data, offset)
    base_revision, offset = decode_uvarint(data, offset)
    end = offset + 32
    if end > len(data):
        raise DSRValidationError("NATIVE_PROPOSAL_HASH_TRUNCATED")
    base_hash = data[offset:end].hex(); offset = end
    source_weight, offset = _read_f64(data, offset)
    axis_count, offset = decode_uvarint(data, offset)
    axes = []
    for _ in range(axis_count):
        blob, offset = _read_blob(data, offset)
        axis_dict, used = _decode_axis_dict(blob, 0)
        if used != len(blob):
            raise DSRValidationError("NATIVE_PROPOSAL_AXIS_TRAILING_DATA")
        axes.append(SpectrumAxis.from_dict(axis_dict))
    relation_count, offset = decode_uvarint(data, offset)
    relations = []
    for _ in range(relation_count):
        blob, offset = _read_blob(data, offset)
        relation_dict, used = _decode_relation_dict(blob, 0)
        if used != len(blob):
            raise DSRValidationError("NATIVE_PROPOSAL_RELATION_TRAILING_DATA")
        relations.append(TypedRelation.from_dict(relation_dict))
    negative_count, offset = decode_uvarint(data, offset)
    negative_relations = []
    for _ in range(negative_count):
        blob, offset = _read_blob(data, offset)
        relation_dict, used = _decode_relation_dict(blob, 0)
        if used != len(blob):
            raise DSRValidationError("NATIVE_PROPOSAL_NEGATIVE_RELATION_TRAILING_DATA")
        negative_relations.append(TypedRelation.from_dict(relation_dict))
    if offset >= len(data):
        raise DSRValidationError("NATIVE_PROPOSAL_TIME_FLAG_TRUNCATED")
    flag = data[offset]; offset += 1
    produced_at = None
    if flag == 1:
        produced_at, offset = _read_text(data, offset)
    elif flag != 0:
        raise DSRValidationError("NATIVE_PROPOSAL_TIME_FLAG_INVALID")
    proposal = SemanticProposal(
        proposal_id=proposal_id,
        source_id=source_id,
        identity=identity,
        base_revision=base_revision,
        base_hash=base_hash,
        source_weight=source_weight,
        axes=tuple(axes),
        relations=tuple(relations),
        negative_relations=tuple(negative_relations),
        produced_at=produced_at,
    )
    return proposal.to_dict(), offset


_FUSION_KIND_CODES = {"axis": 1, "relation": 2}
_FUSION_CODE_KINDS = {value: key for key, value in _FUSION_KIND_CODES.items()}
_FUSION_REASON_CODES = {"TIED_SUPPORT": 1, "INSUFFICIENT_SUPPORT": 2, "POLARITY_CONFLICT": 3}
_FUSION_CODE_REASONS = {value: key for key, value in _FUSION_REASON_CODES.items()}


def _encode_fusion_result(result: Any) -> bytes:
    from .model import semantic_value_from_dict
    if not isinstance(result, dict) or set(result) != {"fusion"} or not isinstance(result["fusion"], dict):
        raise DSRValidationError("NATIVE_HISTORY_RESULT_UNSUPPORTED")
    decision = result["fusion"]
    if decision.get("algorithm") != "weighted-agreement/v0.2":
        raise DSRValidationError("NATIVE_FUSION_ALGORITHM_UNSUPPORTED")
    out = bytearray()
    out += encode_uvarint(1)  # weighted-agreement/v0.2
    _write_text(out, decision["identity"])
    out += encode_uvarint(decision["base_revision"])
    out += _hash_bytes(decision["base_hash"])
    proposal_ids = decision.get("proposal_ids", [])
    out += encode_uvarint(len(proposal_ids))
    for proposal_id in proposal_ids:
        _write_text(out, proposal_id)
    _write_f64(out, decision["axis_threshold"])
    _write_f64(out, decision["relation_threshold"])
    axes = decision.get("axes", [])
    out += encode_uvarint(len(axes))
    for axis in axes:
        _write_blob(out, _encode_axis_dict(axis))
    relations = decision.get("relations", [])
    out += encode_uvarint(len(relations))
    for relation in relations:
        _write_blob(out, _encode_relation_dict(relation))
    negative_relations = decision.get("negative_relations", [])
    out += encode_uvarint(len(negative_relations))
    for relation in negative_relations:
        _write_blob(out, _encode_relation_dict(relation))
    conflicts = decision.get("conflicts", [])
    out += encode_uvarint(len(conflicts))
    for conflict in conflicts:
        kind = conflict.get("kind")
        reason = conflict.get("reason")
        if kind not in _FUSION_KIND_CODES or reason not in _FUSION_REASON_CODES:
            raise DSRValidationError("NATIVE_FUSION_CONFLICT_UNSUPPORTED")
        out += encode_uvarint(_FUSION_KIND_CODES[kind])
        _write_text(out, conflict["key"])
        out += encode_uvarint(_FUSION_REASON_CODES[reason])
        candidates = conflict.get("candidates", [])
        out += encode_uvarint(len(candidates))
        for candidate in candidates:
            if kind == "axis":
                out += encode_uvarint(1)
                variant = candidate.get("variant", {})
                _write_text(out, variant["domain"])
                _write_blob(out, _encode_semantic_value(semantic_value_from_dict(variant["value"])))
                _write_f64(out, candidate["effective_support"])
                _write_f64(out, candidate["support_ratio"])
                sources = candidate.get("sources", [])
                out += encode_uvarint(len(sources))
                for source in sources:
                    _write_text(out, source)
            else:
                out += encode_uvarint(2)
                polarity = candidate.get("polarity")
                if polarity not in (-1, 1):
                    raise DSRValidationError("NATIVE_FUSION_POLARITY_INVALID")
                out += encode_uvarint(1 if polarity > 0 else 2)
                _write_f64(out, candidate["support_ratio"])
    return bytes(out)


def _decode_fusion_result(data: bytes, offset: int) -> tuple[dict[str, Any], int]:
    algorithm_code, offset = decode_uvarint(data, offset)
    if algorithm_code != 1:
        raise DSRValidationError("NATIVE_FUSION_ALGORITHM_UNSUPPORTED")
    identity, offset = _read_text(data, offset)
    base_revision, offset = decode_uvarint(data, offset)
    end = offset + 32
    if end > len(data):
        raise DSRValidationError("NATIVE_FUSION_HASH_TRUNCATED")
    base_hash = data[offset:end].hex(); offset = end
    proposal_count, offset = decode_uvarint(data, offset)
    proposal_ids = []
    for _ in range(proposal_count):
        value, offset = _read_text(data, offset); proposal_ids.append(value)
    axis_threshold, offset = _read_f64(data, offset)
    relation_threshold, offset = _read_f64(data, offset)
    axis_count, offset = decode_uvarint(data, offset)
    axes = []
    for _ in range(axis_count):
        blob, offset = _read_blob(data, offset); value, used = _decode_axis_dict(blob, 0)
        if used != len(blob): raise DSRValidationError("NATIVE_FUSION_AXIS_TRAILING_DATA")
        axes.append(value)
    relation_count, offset = decode_uvarint(data, offset)
    relations = []
    for _ in range(relation_count):
        blob, offset = _read_blob(data, offset); value, used = _decode_relation_dict(blob, 0)
        if used != len(blob): raise DSRValidationError("NATIVE_FUSION_RELATION_TRAILING_DATA")
        relations.append(value)
    negative_relation_count, offset = decode_uvarint(data, offset)
    negative_relations = []
    for _ in range(negative_relation_count):
        blob, offset = _read_blob(data, offset); value, used = _decode_relation_dict(blob, 0)
        if used != len(blob): raise DSRValidationError("NATIVE_FUSION_NEGATIVE_RELATION_TRAILING_DATA")
        negative_relations.append(value)
    conflict_count, offset = decode_uvarint(data, offset)
    conflicts = []
    for _ in range(conflict_count):
        kind_code, offset = decode_uvarint(data, offset)
        if kind_code not in _FUSION_CODE_KINDS: raise DSRValidationError("NATIVE_FUSION_KIND_UNKNOWN")
        key, offset = _read_text(data, offset)
        reason_code, offset = decode_uvarint(data, offset)
        if reason_code not in _FUSION_CODE_REASONS: raise DSRValidationError("NATIVE_FUSION_REASON_UNKNOWN")
        candidate_count, offset = decode_uvarint(data, offset)
        candidates = []
        for _ in range(candidate_count):
            candidate_type, offset = decode_uvarint(data, offset)
            if candidate_type == 1:
                domain, offset = _read_text(data, offset)
                blob, offset = _read_blob(data, offset); semantic_value, used = _decode_semantic_value(blob, 0)
                if used != len(blob): raise DSRValidationError("NATIVE_FUSION_VALUE_TRAILING_DATA")
                effective_support, offset = _read_f64(data, offset)
                support_ratio, offset = _read_f64(data, offset)
                source_count, offset = decode_uvarint(data, offset)
                sources = []
                for _ in range(source_count):
                    source, offset = _read_text(data, offset); sources.append(source)
                candidates.append({
                    "variant": {"domain": domain, "value": semantic_value.to_dict()},
                    "effective_support": effective_support,
                    "support_ratio": support_ratio,
                    "sources": sources,
                })
            elif candidate_type == 2:
                polarity_code, offset = decode_uvarint(data, offset)
                if polarity_code not in (1, 2): raise DSRValidationError("NATIVE_FUSION_POLARITY_INVALID")
                support_ratio, offset = _read_f64(data, offset)
                candidates.append({"polarity": 1 if polarity_code == 1 else -1, "support_ratio": support_ratio})
            else:
                raise DSRValidationError("NATIVE_FUSION_CANDIDATE_TYPE_UNKNOWN")
        conflicts.append({
            "kind": _FUSION_CODE_KINDS[kind_code],
            "key": key,
            "reason": _FUSION_CODE_REASONS[reason_code],
            "candidates": candidates,
        })
    return {"fusion": {
        "schema": "isql.dsr-fusion-decision/v0.2",
        "algorithm": "weighted-agreement/v0.2",
        "identity": identity,
        "base_revision": base_revision,
        "base_hash": base_hash,
        "proposal_ids": proposal_ids,
        "axis_threshold": axis_threshold,
        "relation_threshold": relation_threshold,
        "axes": axes,
        "relations": relations,
        "negative_relations": negative_relations,
        "conflicts": conflicts,
    }}, offset


def _encode_payload(operation: str, payload: dict[str, Any]) -> bytes:
    out = bytearray()
    if operation == "set_context":
        _write_blob(out, encode_value(payload["context"]))
    elif operation == "upsert_axis":
        _write_blob(out, _encode_axis_dict(payload["axis"]))
    elif operation == "remove_axis":
        _write_text(out, payload["key"])
    elif operation in {"upsert_relation", "deny_relation", "retract_relation"}:
        _write_blob(out, _encode_relation_dict(payload["relation"]))
    elif operation == "remove_relation":
        _write_blob(out, _encode_relation_dict(payload.get("relation", payload)))
    elif operation == "upsert_projection":
        _write_blob(out, _encode_projection_dict(payload["projection"]))
    elif operation == "remove_projection":
        _write_text(out, payload["projection_id"])
    elif operation == "refresh_topology":
        methods = payload.get("methods", ["graph.components", "graph.cycle_rank"])
        out += encode_uvarint(len(methods))
        for method in methods:
            _write_text(out, method)
    elif operation == "upsert_topology_descriptor":
        _write_blob(out, _encode_topology_dict(payload["descriptor"]))
    elif operation == "remove_topology_descriptor":
        _write_text(out, payload["descriptor_id"])
    elif operation == "fuse_proposals":
        proposals = payload.get("proposals", [])
        out += encode_uvarint(len(proposals))
        for proposal in proposals:
            _write_blob(out, _encode_proposal_dict(proposal))
        _write_f64(out, float(payload.get("axis_threshold", 0.5)))
        _write_f64(out, float(payload.get("relation_threshold", 0.5)))
    else:
        raise DSRValidationError("NATIVE_EVENT_OPERATION_UNKNOWN")
    return bytes(out)


def _decode_payload(operation: str, data: bytes, offset: int) -> tuple[dict[str, Any], int]:
    if operation == "set_context":
        blob, offset = _read_blob(data, offset); value, used = decode_value(blob)
        if used != len(blob) or not isinstance(value, dict): raise DSRValidationError("NATIVE_CONTEXT_INVALID")
        return {"context": value}, offset
    if operation == "upsert_axis":
        blob, offset = _read_blob(data, offset); value, used = _decode_axis_dict(blob, 0)
        if used != len(blob): raise DSRValidationError("NATIVE_AXIS_TRAILING_DATA")
        return {"axis": value}, offset
    if operation == "remove_axis":
        value, offset = _read_text(data, offset); return {"key": value}, offset
    if operation in {"upsert_relation", "remove_relation", "deny_relation", "retract_relation"}:
        blob, offset = _read_blob(data, offset); value, used = _decode_relation_dict(blob, 0)
        if used != len(blob): raise DSRValidationError("NATIVE_RELATION_TRAILING_DATA")
        return ({"relation": value} if operation in {"upsert_relation", "deny_relation", "retract_relation"} else value), offset
    if operation == "upsert_projection":
        blob, offset = _read_blob(data, offset); value, used = _decode_projection_dict(blob, 0)
        if used != len(blob): raise DSRValidationError("NATIVE_PROJECTION_TRAILING_DATA")
        return {"projection": value}, offset
    if operation == "remove_projection":
        value, offset = _read_text(data, offset); return {"projection_id": value}, offset
    if operation == "refresh_topology":
        count, offset = decode_uvarint(data, offset); methods=[]
        for _ in range(count):
            value, offset = _read_text(data, offset); methods.append(value)
        return {"methods": methods}, offset
    if operation == "upsert_topology_descriptor":
        blob, offset = _read_blob(data, offset); value, used = _decode_topology_dict(blob, 0)
        if used != len(blob): raise DSRValidationError("NATIVE_TOPOLOGY_TRAILING_DATA")
        return {"descriptor": value}, offset
    if operation == "remove_topology_descriptor":
        value, offset = _read_text(data, offset); return {"descriptor_id": value}, offset
    if operation == "fuse_proposals":
        count, offset = decode_uvarint(data, offset)
        proposals = []
        for _ in range(count):
            blob, offset = _read_blob(data, offset)
            proposal, used = _decode_proposal_dict(blob, 0)
            if used != len(blob): raise DSRValidationError("NATIVE_PROPOSAL_TRAILING_DATA")
            proposals.append(proposal)
        axis_threshold, offset = _read_f64(data, offset)
        relation_threshold, offset = _read_f64(data, offset)
        return {"proposals": proposals, "axis_threshold": axis_threshold, "relation_threshold": relation_threshold}, offset
    raise DSRValidationError("NATIVE_EVENT_OPERATION_UNKNOWN")


def _encode_history_record(record: Any) -> bytes:
    if not isinstance(record, dict):
        raise DSRValidationError("NATIVE_HISTORY_RECORD_INVALID")
    event = record.get("event")
    if not isinstance(event, dict):
        raise DSRValidationError("NATIVE_HISTORY_EVENT_INVALID")
    operation = event.get("operation")
    if not isinstance(operation, str):
        raise DSRValidationError("NATIVE_HISTORY_OPERATION_INVALID")
    out = bytearray()
    out += _hash_bytes(record.get("previous_hash"))
    _write_text(out, event.get("event_id"))
    out += encode_uvarint(operation_opcode(operation))
    payload = event.get("payload", {})
    if not isinstance(payload, dict):
        raise DSRValidationError("NATIVE_HISTORY_PAYLOAD_INVALID")
    _write_blob(out, _encode_payload(operation, payload))
    out += encode_uvarint(event.get("base_revision"))
    out += _hash_bytes(event.get("previous_hash"))
    occurred_at = event.get("occurred_at")
    out.append(1 if occurred_at is not None else 0)
    if occurred_at is not None:
        _write_text(out, occurred_at)
    result = record.get("result")
    out.append(1 if result is not None else 0)
    if result is not None:
        _write_blob(out, _encode_fusion_result(result))
    return bytes(out)


def _decode_history_record(data: bytes, offset: int) -> tuple[dict[str, Any], int]:
    end = offset + 32
    if end > len(data): raise DSRValidationError("NATIVE_HISTORY_HASH_TRUNCATED")
    previous_hash = data[offset:end].hex(); offset=end
    event_id, offset = _read_text(data, offset)
    opcode, offset = decode_uvarint(data, offset)
    operation = operation_name(opcode)
    blob, offset = _read_blob(data, offset)
    payload, used = _decode_payload(operation, blob, 0)
    if used != len(blob): raise DSRValidationError("NATIVE_EVENT_PAYLOAD_TRAILING_DATA")
    base_revision, offset = decode_uvarint(data, offset)
    end = offset + 32
    if end > len(data): raise DSRValidationError("NATIVE_EVENT_HASH_TRUNCATED")
    event_previous_hash = data[offset:end].hex(); offset=end
    if offset >= len(data): raise DSRValidationError("NATIVE_EVENT_TIME_FLAG_TRUNCATED")
    has_time = data[offset]; offset += 1
    occurred_at = None
    if has_time == 1:
        occurred_at, offset = _read_text(data, offset)
    elif has_time != 0:
        raise DSRValidationError("NATIVE_EVENT_TIME_FLAG_INVALID")
    if offset >= len(data): raise DSRValidationError("NATIVE_HISTORY_RESULT_FLAG_TRUNCATED")
    has_result = data[offset]; offset += 1
    result = None
    if has_result == 1:
        blob, offset = _read_blob(data, offset); result, used = _decode_fusion_result(blob, 0)
        if used != len(blob): raise DSRValidationError("NATIVE_HISTORY_RESULT_INVALID")
    elif has_result != 0:
        raise DSRValidationError("NATIVE_HISTORY_RESULT_FLAG_INVALID")
    event = {
        "schema": "isql.dsr-event/v0.5",
        "event_id": event_id,
        "operation": operation,
        "payload": payload,
        "base_revision": base_revision,
        "previous_hash": event_previous_hash,
    }
    if occurred_at is not None:
        event["occurred_at"] = occurred_at
    record = {"event": event, "previous_hash": previous_hash}
    if result is not None:
        record["result"] = result
    return record, offset
