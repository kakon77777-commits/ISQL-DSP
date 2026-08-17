from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import math
import struct
from typing import Any, Iterable

from .canonical import state_hash
from .errors import DSRExecutionError, DSRValidationError
from .events import TransitionEvent
from .fusion import SemanticProposal
from .machine import (
    NativeAxis, NativeProjection, NativeRelation, NativeSemanticState, NativeTopology,
    compile_registered_state, inspect_registered_state, registered_state_hash,
)
from .model import SemanticProjection, SemanticState, SpectrumAxis, TopologyDescriptor, TypedRelation
from .native import (
    decode_uvarint, decode_value, encode_uvarint, encode_value,
    operation_name, operation_opcode, _decode_semantic_value, _encode_semantic_value,
)
from .registry import NativeSymbolRegistry, SymbolNamespace
from .runtime import apply_event


STREAM_MAGIC = bytes((0xD5, 0x51, 0xE1, 0x05))
STREAM_FORMAT_VERSION = 5


def _hash_hex(value: Any, error: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise DSRValidationError(error)
    return value


def _positive(value: Any, error: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise DSRValidationError(error)
    return value


def _write_blob(out: bytearray, data: bytes) -> None:
    out += encode_uvarint(len(data)); out += data


def _read_blob(data: bytes, offset: int) -> tuple[bytes, int]:
    size, offset = decode_uvarint(data, offset)
    end = offset + size
    if end > len(data):
        raise DSRValidationError("STREAM_BLOB_TRUNCATED")
    return data[offset:end], end


def _write_f64(out: bytearray, value: float) -> None:
    value = float(value)
    if not math.isfinite(value):
        raise DSRValidationError("STREAM_FLOAT_INVALID")
    out += struct.pack(">d", value)


def _read_f64(data: bytes, offset: int) -> tuple[float, int]:
    end = offset + 8
    if end > len(data):
        raise DSRValidationError("STREAM_FLOAT_TRUNCATED")
    value = struct.unpack(">d", data[offset:end])[0]
    if not math.isfinite(value):
        raise DSRValidationError("STREAM_FLOAT_INVALID")
    return value, end


def _ref(registry: NativeSymbolRegistry, ns: SymbolNamespace, text: str) -> int:
    value = registry.lookup_text(ns, text)
    if value is None:
        raise DSRValidationError("STREAM_SYMBOL_MISSING")
    return value


def _encode_axis(axis: NativeAxis) -> bytes:
    out = bytearray()
    out += encode_uvarint(axis.key_ref)
    out += encode_uvarint(axis.domain_ref)
    _write_blob(out, _encode_semantic_value(axis.value))
    _write_f64(out, axis.uncertainty)
    out += encode_uvarint(axis.resolution)
    return bytes(out)


def _decode_axis(data: bytes, offset: int) -> tuple[NativeAxis, int]:
    key_ref, offset = decode_uvarint(data, offset)
    domain_ref, offset = decode_uvarint(data, offset)
    blob, offset = _read_blob(data, offset)
    value, used = _decode_semantic_value(blob, 0)
    if used != len(blob):
        raise DSRValidationError("STREAM_AXIS_VALUE_TRAILING_DATA")
    uncertainty, offset = _read_f64(data, offset)
    resolution, offset = decode_uvarint(data, offset)
    return NativeAxis(key_ref, domain_ref, value, uncertainty, resolution), offset


def _axis_from_inspection(axis: SpectrumAxis, registry: NativeSymbolRegistry) -> NativeAxis:
    return NativeAxis(
        _ref(registry, SymbolNamespace.AXIS_KEY, axis.key),
        _ref(registry, SymbolNamespace.AXIS_DOMAIN, axis.domain),
        axis.value, axis.uncertainty, axis.resolution,
    )


def _axis_to_inspection(axis: NativeAxis, registry: NativeSymbolRegistry) -> SpectrumAxis:
    return SpectrumAxis(
        registry.resolve_text(axis.key_ref, SymbolNamespace.AXIS_KEY),
        registry.resolve_text(axis.domain_ref, SymbolNamespace.AXIS_DOMAIN),
        axis.value, axis.uncertainty, axis.resolution,
    )


def _encode_relation(rel: NativeRelation) -> bytes:
    return encode_uvarint(rel.subject_ref) + encode_uvarint(rel.predicate_ref) + encode_uvarint(rel.object_ref)


def _decode_relation(data: bytes, offset: int) -> tuple[NativeRelation, int]:
    s, offset = decode_uvarint(data, offset)
    p, offset = decode_uvarint(data, offset)
    o, offset = decode_uvarint(data, offset)
    return NativeRelation(s, p, o), offset


def _relation_from_inspection(rel: TypedRelation, registry: NativeSymbolRegistry) -> NativeRelation:
    return NativeRelation(
        _ref(registry, SymbolNamespace.ATOM, rel.subject),
        _ref(registry, SymbolNamespace.PREDICATE, rel.predicate),
        _ref(registry, SymbolNamespace.ATOM, rel.object),
    )


def _relation_to_inspection(rel: NativeRelation, registry: NativeSymbolRegistry) -> TypedRelation:
    return TypedRelation(
        registry.resolve_text(rel.subject_ref, SymbolNamespace.ATOM),
        registry.resolve_text(rel.predicate_ref, SymbolNamespace.PREDICATE),
        registry.resolve_text(rel.object_ref, SymbolNamespace.ATOM),
    )


def _encode_projection(item: NativeProjection) -> bytes:
    out = bytearray()
    out += encode_uvarint(item.projection_ref)
    out += encode_uvarint(item.media_type_ref)
    _write_blob(out, encode_value(item.payload))
    return bytes(out)


def _decode_projection(data: bytes, offset: int) -> tuple[NativeProjection, int]:
    p, offset = decode_uvarint(data, offset)
    m, offset = decode_uvarint(data, offset)
    blob, offset = _read_blob(data, offset); payload, used = decode_value(blob)
    if used != len(blob): raise DSRValidationError("STREAM_PROJECTION_TRAILING_DATA")
    return NativeProjection(p, m, payload), offset


def _projection_from_inspection(item: SemanticProjection, registry: NativeSymbolRegistry) -> NativeProjection:
    return NativeProjection(
        _ref(registry, SymbolNamespace.PROJECTION_ID, item.projection_id),
        _ref(registry, SymbolNamespace.MEDIA_TYPE, item.media_type),
        item.payload,
    )


def _projection_to_inspection(item: NativeProjection, registry: NativeSymbolRegistry) -> SemanticProjection:
    return SemanticProjection(
        registry.resolve_text(item.projection_ref, SymbolNamespace.PROJECTION_ID),
        registry.resolve_text(item.media_type_ref, SymbolNamespace.MEDIA_TYPE),
        item.payload,
    )


def _encode_topology(item: NativeTopology) -> bytes:
    out = bytearray()
    out += encode_uvarint(item.descriptor_ref)
    out += encode_uvarint(item.method_ref)
    out += bytes.fromhex(item.basis_hash)
    _write_blob(out, encode_value(item.value))
    _write_f64(out, item.confidence)
    _write_blob(out, encode_value(item.parameters or {}))
    return bytes(out)


def _decode_topology(data: bytes, offset: int) -> tuple[NativeTopology, int]:
    d, offset = decode_uvarint(data, offset)
    m, offset = decode_uvarint(data, offset)
    end = offset + 32
    if end > len(data): raise DSRValidationError("STREAM_TOPOLOGY_HASH_TRUNCATED")
    basis = data[offset:end].hex(); offset = end
    blob, offset = _read_blob(data, offset); value, used = decode_value(blob)
    if used != len(blob): raise DSRValidationError("STREAM_TOPOLOGY_VALUE_TRAILING_DATA")
    confidence, offset = _read_f64(data, offset)
    blob, offset = _read_blob(data, offset); parameters, used = decode_value(blob)
    if used != len(blob) or not isinstance(parameters, dict): raise DSRValidationError("STREAM_TOPOLOGY_PARAMETERS_INVALID")
    return NativeTopology(d, m, basis, value, confidence, parameters), offset


def _topology_from_inspection(item: TopologyDescriptor, registry: NativeSymbolRegistry) -> NativeTopology:
    return NativeTopology(
        _ref(registry, SymbolNamespace.TOPOLOGY_DESCRIPTOR, item.descriptor_id),
        _ref(registry, SymbolNamespace.TOPOLOGY_METHOD, item.method),
        item.basis_hash, item.value, item.confidence, item.parameters,
    )


def _topology_to_inspection(item: NativeTopology, registry: NativeSymbolRegistry) -> TopologyDescriptor:
    return TopologyDescriptor(
        registry.resolve_text(item.descriptor_ref, SymbolNamespace.TOPOLOGY_DESCRIPTOR),
        registry.resolve_text(item.method_ref, SymbolNamespace.TOPOLOGY_METHOD),
        item.basis_hash, item.value, item.confidence, item.parameters or {},
    )


@dataclass(frozen=True, slots=True)
class NativeProposal:
    proposal_ref: int
    source_ref: int
    identity_ref: int
    base_revision: int
    base_hash: str
    source_weight: float
    axes: tuple[NativeAxis, ...] = ()
    relations: tuple[NativeRelation, ...] = ()
    negative_relations: tuple[NativeRelation, ...] = ()
    produced_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_ref", _positive(self.proposal_ref, "STREAM_PROPOSAL_REF_INVALID"))
        object.__setattr__(self, "source_ref", _positive(self.source_ref, "STREAM_SOURCE_REF_INVALID"))
        object.__setattr__(self, "identity_ref", _positive(self.identity_ref, "STREAM_IDENTITY_REF_INVALID"))
        if not isinstance(self.base_revision, int) or isinstance(self.base_revision, bool) or self.base_revision < 0:
            raise DSRValidationError("STREAM_PROPOSAL_BASE_REVISION_INVALID")
        object.__setattr__(self, "base_hash", _hash_hex(self.base_hash, "STREAM_PROPOSAL_BASE_HASH_INVALID"))
        w = float(self.source_weight)
        if not math.isfinite(w) or w <= 0:
            raise DSRValidationError("STREAM_PROPOSAL_WEIGHT_INVALID")
        object.__setattr__(self, "source_weight", w)
        object.__setattr__(self, "axes", tuple(sorted(self.axes, key=lambda x: x.key_ref)))
        object.__setattr__(self, "relations", tuple(sorted(self.relations, key=lambda x: x.key)))
        object.__setattr__(self, "negative_relations", tuple(sorted(self.negative_relations, key=lambda x: x.key)))
        if {x.key for x in self.relations} & {x.key for x in self.negative_relations}:
            raise DSRValidationError("STREAM_PROPOSAL_RELATION_POLARITY_CONTRADICTION")


def _proposal_from_inspection(proposal: SemanticProposal, registry: NativeSymbolRegistry, native_base_hash: str) -> NativeProposal:
    return NativeProposal(
        _ref(registry, SymbolNamespace.PROPOSAL_ID, proposal.proposal_id),
        _ref(registry, SymbolNamespace.SOURCE_ID, proposal.source_id),
        _ref(registry, SymbolNamespace.IDENTITY, proposal.identity),
        proposal.base_revision,
        native_base_hash,
        proposal.source_weight,
        tuple(_axis_from_inspection(x, registry) for x in proposal.axes),
        tuple(_relation_from_inspection(x, registry) for x in proposal.relations),
        tuple(_relation_from_inspection(x, registry) for x in proposal.negative_relations),
        proposal.produced_at,
    )


def _proposal_to_inspection(proposal: NativeProposal, registry: NativeSymbolRegistry, inspection_base_hash: str) -> SemanticProposal:
    return SemanticProposal(
        proposal_id=registry.resolve_text(proposal.proposal_ref, SymbolNamespace.PROPOSAL_ID),
        source_id=registry.resolve_text(proposal.source_ref, SymbolNamespace.SOURCE_ID),
        identity=registry.resolve_text(proposal.identity_ref, SymbolNamespace.IDENTITY),
        base_revision=proposal.base_revision,
        base_hash=inspection_base_hash,
        source_weight=proposal.source_weight,
        axes=tuple(_axis_to_inspection(x, registry) for x in proposal.axes),
        relations=tuple(_relation_to_inspection(x, registry) for x in proposal.relations),
        negative_relations=tuple(_relation_to_inspection(x, registry) for x in proposal.negative_relations),
        produced_at=proposal.produced_at,
    )


def _encode_proposal(proposal: NativeProposal) -> bytes:
    out = bytearray()
    out += encode_uvarint(proposal.proposal_ref)
    out += encode_uvarint(proposal.source_ref)
    out += encode_uvarint(proposal.identity_ref)
    out += encode_uvarint(proposal.base_revision)
    out += bytes.fromhex(proposal.base_hash)
    _write_f64(out, proposal.source_weight)
    out += encode_uvarint(len(proposal.axes))
    for axis in proposal.axes: _write_blob(out, _encode_axis(axis))
    out += encode_uvarint(len(proposal.relations))
    for rel in proposal.relations: _write_blob(out, _encode_relation(rel))
    out += encode_uvarint(len(proposal.negative_relations))
    for rel in proposal.negative_relations: _write_blob(out, _encode_relation(rel))
    out.append(1 if proposal.produced_at is not None else 0)
    if proposal.produced_at is not None:
        raw = proposal.produced_at.encode("utf-8"); _write_blob(out, raw)
    return bytes(out)


def _decode_proposal(data: bytes, offset: int) -> tuple[NativeProposal, int]:
    proposal_ref, offset = decode_uvarint(data, offset)
    source_ref, offset = decode_uvarint(data, offset)
    identity_ref, offset = decode_uvarint(data, offset)
    base_revision, offset = decode_uvarint(data, offset)
    end = offset + 32
    if end > len(data): raise DSRValidationError("STREAM_PROPOSAL_HASH_TRUNCATED")
    base_hash = data[offset:end].hex(); offset = end
    source_weight, offset = _read_f64(data, offset)
    count, offset = decode_uvarint(data, offset); axes=[]
    for _ in range(count):
        blob, offset = _read_blob(data, offset); axis, used = _decode_axis(blob, 0)
        if used != len(blob): raise DSRValidationError("STREAM_PROPOSAL_AXIS_TRAILING_DATA")
        axes.append(axis)
    count, offset = decode_uvarint(data, offset); relations=[]
    for _ in range(count):
        blob, offset = _read_blob(data, offset); rel, used = _decode_relation(blob, 0)
        if used != len(blob): raise DSRValidationError("STREAM_PROPOSAL_RELATION_TRAILING_DATA")
        relations.append(rel)
    count, offset = decode_uvarint(data, offset); negative_relations=[]
    for _ in range(count):
        blob, offset = _read_blob(data, offset); rel, used = _decode_relation(blob, 0)
        if used != len(blob): raise DSRValidationError("STREAM_PROPOSAL_NEGATIVE_RELATION_TRAILING_DATA")
        negative_relations.append(rel)
    if offset >= len(data): raise DSRValidationError("STREAM_PROPOSAL_TIME_FLAG_TRUNCATED")
    flag=data[offset]; offset += 1; produced_at=None
    if flag == 1:
        blob, offset = _read_blob(data, offset)
        try: produced_at = blob.decode("utf-8")
        except UnicodeDecodeError as exc: raise DSRValidationError("STREAM_PROPOSAL_TIME_INVALID") from exc
    elif flag != 0: raise DSRValidationError("STREAM_PROPOSAL_TIME_FLAG_INVALID")
    return NativeProposal(proposal_ref, source_ref, identity_ref, base_revision, base_hash, source_weight, tuple(axes), tuple(relations), tuple(negative_relations), produced_at), offset


def _compile_payload(event: TransitionEvent, base: NativeSemanticState, registry: NativeSymbolRegistry) -> bytes:
    op = event.operation; p = event.payload; out = bytearray()
    if op == "set_context":
        context = p.get("context")
        if not isinstance(context, dict): raise DSRValidationError("STREAM_CONTEXT_INVALID")
        rows = sorted((_ref(registry, SymbolNamespace.CONTEXT_KEY, key), value) for key, value in context.items())
        out += encode_uvarint(len(rows))
        for ref, value in rows:
            out += encode_uvarint(ref); _write_blob(out, encode_value(value))
    elif op == "upsert_axis":
        _write_blob(out, _encode_axis(_axis_from_inspection(SpectrumAxis.from_dict(p["axis"]), registry)))
    elif op == "remove_axis":
        out += encode_uvarint(_ref(registry, SymbolNamespace.AXIS_KEY, p["key"]))
    elif op in {"upsert_relation", "remove_relation", "deny_relation", "retract_relation"}:
        raw = p.get("relation", p)
        _write_blob(out, _encode_relation(_relation_from_inspection(TypedRelation.from_dict(raw), registry)))
    elif op == "upsert_projection":
        _write_blob(out, _encode_projection(_projection_from_inspection(SemanticProjection.from_dict(p["projection"]), registry)))
    elif op == "remove_projection":
        out += encode_uvarint(_ref(registry, SymbolNamespace.PROJECTION_ID, p["projection_id"]))
    elif op == "refresh_topology":
        methods = p.get("methods", ["graph.components", "graph.cycle_rank"])
        out += encode_uvarint(len(methods))
        for method in methods: out += encode_uvarint(_ref(registry, SymbolNamespace.TOPOLOGY_METHOD, method))
    elif op == "upsert_topology_descriptor":
        _write_blob(out, _encode_topology(_topology_from_inspection(TopologyDescriptor.from_dict(p["descriptor"]), registry)))
    elif op == "remove_topology_descriptor":
        out += encode_uvarint(_ref(registry, SymbolNamespace.TOPOLOGY_DESCRIPTOR, p["descriptor_id"]))
    elif op == "fuse_proposals":
        proposals = [SemanticProposal.from_dict(x) for x in p.get("proposals", [])]
        out += encode_uvarint(len(proposals))
        native_base_hash = registered_state_hash(base)
        for proposal in proposals:
            _write_blob(out, _encode_proposal(_proposal_from_inspection(proposal, registry, native_base_hash)))
        _write_f64(out, p.get("axis_threshold", 0.5)); _write_f64(out, p.get("relation_threshold", 0.5))
    else:
        raise DSRValidationError("STREAM_OPERATION_UNSUPPORTED")
    return bytes(out)


def _inspect_payload(op: str, payload: bytes, registry: NativeSymbolRegistry, inspection_base_hash: str) -> dict[str, Any]:
    offset=0
    if op == "set_context":
        count, offset = decode_uvarint(payload, offset); context={}
        for _ in range(count):
            ref, offset = decode_uvarint(payload, offset)
            blob, offset = _read_blob(payload, offset); value, used = decode_value(blob)
            if used != len(blob): raise DSRValidationError("STREAM_CONTEXT_TRAILING_DATA")
            context[registry.resolve_text(ref, SymbolNamespace.CONTEXT_KEY)] = value
        result={"context": context}
    elif op == "upsert_axis":
        blob, offset = _read_blob(payload, offset); axis, used = _decode_axis(blob,0)
        if used != len(blob): raise DSRValidationError("STREAM_AXIS_TRAILING_DATA")
        result={"axis": _axis_to_inspection(axis,registry).to_dict()}
    elif op == "remove_axis":
        ref, offset=decode_uvarint(payload,offset); result={"key": registry.resolve_text(ref,SymbolNamespace.AXIS_KEY)}
    elif op in {"upsert_relation", "remove_relation", "deny_relation", "retract_relation"}:
        blob, offset=_read_blob(payload,offset); rel,used=_decode_relation(blob,0)
        if used != len(blob): raise DSRValidationError("STREAM_RELATION_TRAILING_DATA")
        rel_dict=_relation_to_inspection(rel,registry).to_dict(); result={"relation":rel_dict} if op in {"upsert_relation", "deny_relation", "retract_relation"} else rel_dict
    elif op == "upsert_projection":
        blob, offset=_read_blob(payload,offset); item,used=_decode_projection(blob,0)
        if used != len(blob): raise DSRValidationError("STREAM_PROJECTION_TRAILING_DATA")
        result={"projection":_projection_to_inspection(item,registry).to_dict()}
    elif op == "remove_projection":
        ref,offset=decode_uvarint(payload,offset); result={"projection_id":registry.resolve_text(ref,SymbolNamespace.PROJECTION_ID)}
    elif op == "refresh_topology":
        count,offset=decode_uvarint(payload,offset); methods=[]
        for _ in range(count):
            ref,offset=decode_uvarint(payload,offset); methods.append(registry.resolve_text(ref,SymbolNamespace.TOPOLOGY_METHOD))
        result={"methods":methods}
    elif op == "upsert_topology_descriptor":
        blob,offset=_read_blob(payload,offset); item,used=_decode_topology(blob,0)
        if used != len(blob): raise DSRValidationError("STREAM_TOPOLOGY_TRAILING_DATA")
        result={"descriptor":_topology_to_inspection(item,registry).to_dict()}
    elif op == "remove_topology_descriptor":
        ref,offset=decode_uvarint(payload,offset); result={"descriptor_id":registry.resolve_text(ref,SymbolNamespace.TOPOLOGY_DESCRIPTOR)}
    elif op == "fuse_proposals":
        count,offset=decode_uvarint(payload,offset); proposals=[]
        for _ in range(count):
            blob,offset=_read_blob(payload,offset); proposal,used=_decode_proposal(blob,0)
            if used != len(blob): raise DSRValidationError("STREAM_PROPOSAL_TRAILING_DATA")
            proposals.append(_proposal_to_inspection(proposal,registry,inspection_base_hash).to_dict())
        axis_threshold,offset=_read_f64(payload,offset); relation_threshold,offset=_read_f64(payload,offset)
        result={"proposals":proposals,"axis_threshold":axis_threshold,"relation_threshold":relation_threshold}
    else:
        raise DSRValidationError("STREAM_OPERATION_UNSUPPORTED")
    if offset != len(payload): raise DSRValidationError("STREAM_PAYLOAD_TRAILING_DATA")
    return result


@dataclass(frozen=True, slots=True)
class NativeTransitionEvent:
    event_id_ref: int
    opcode: int
    payload: bytes
    base_revision: int
    previous_hash: str
    occurred_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id_ref", _positive(self.event_id_ref, "STREAM_EVENT_ID_REF_INVALID"))
        if not isinstance(self.opcode, int) or isinstance(self.opcode, bool) or self.opcode <= 0:
            raise DSRValidationError("STREAM_OPCODE_INVALID")
        operation_name(self.opcode)
        if not isinstance(self.payload, (bytes, bytearray, memoryview)):
            raise DSRValidationError("STREAM_PAYLOAD_BYTES_REQUIRED")
        object.__setattr__(self, "payload", bytes(self.payload))
        if not isinstance(self.base_revision, int) or isinstance(self.base_revision, bool) or self.base_revision < 0:
            raise DSRValidationError("STREAM_BASE_REVISION_INVALID")
        object.__setattr__(self, "previous_hash", _hash_hex(self.previous_hash, "STREAM_PREVIOUS_HASH_INVALID"))
        if self.occurred_at is not None and (not isinstance(self.occurred_at, str) or not self.occurred_at):
            raise DSRValidationError("STREAM_OCCURRED_AT_INVALID")


@dataclass(frozen=True, slots=True)
class NativeStreamRecord:
    event: NativeTransitionEvent
    next_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.event, NativeTransitionEvent): raise DSRValidationError("STREAM_RECORD_EVENT_INVALID")
        object.__setattr__(self, "next_hash", _hash_hex(self.next_hash, "STREAM_NEXT_HASH_INVALID"))


@dataclass(frozen=True, slots=True)
class NativeEventStream:
    registry_revision: int
    registry_hash: str
    genesis_hash: str
    records: tuple[NativeStreamRecord, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.registry_revision,int) or isinstance(self.registry_revision,bool) or self.registry_revision<0:
            raise DSRValidationError("STREAM_REGISTRY_REVISION_INVALID")
        object.__setattr__(self,"registry_hash",_hash_hex(self.registry_hash,"STREAM_REGISTRY_HASH_INVALID"))
        object.__setattr__(self,"genesis_hash",_hash_hex(self.genesis_hash,"STREAM_GENESIS_HASH_INVALID"))
        if not isinstance(self.records,tuple) or not all(isinstance(x,NativeStreamRecord) for x in self.records):
            raise DSRValidationError("STREAM_RECORDS_INVALID")


def compile_native_event(event: TransitionEvent, base: NativeSemanticState, registry: NativeSymbolRegistry) -> NativeTransitionEvent:
    if event.base_revision != base.revision:
        raise DSRValidationError("STREAM_EVENT_BASE_REVISION_MISMATCH")
    return NativeTransitionEvent(
        event_id_ref=_ref(registry, SymbolNamespace.EVENT_ID, event.event_id),
        opcode=operation_opcode(event.operation),
        payload=_compile_payload(event, base, registry),
        base_revision=base.revision,
        previous_hash=registered_state_hash(base),
        occurred_at=event.occurred_at,
    )


def inspect_native_event(event: NativeTransitionEvent, registry: NativeSymbolRegistry, base: SemanticState) -> TransitionEvent:
    registry.resolve(event.event_id_ref, SymbolNamespace.EVENT_ID)
    op=operation_name(event.opcode)
    payload=_inspect_payload(op,event.payload,registry,state_hash(base))
    return TransitionEvent(
        event_id=registry.resolve_text(event.event_id_ref,SymbolNamespace.EVENT_ID),
        operation=op,
        payload=payload,
        base_revision=base.revision,
        previous_hash=state_hash(base),
        occurred_at=event.occurred_at,
    )


def _encode_event(event: NativeTransitionEvent) -> bytes:
    out=bytearray()
    out += encode_uvarint(event.event_id_ref)
    out += encode_uvarint(event.opcode)
    _write_blob(out,event.payload)
    out += encode_uvarint(event.base_revision)
    out += bytes.fromhex(event.previous_hash)
    out.append(1 if event.occurred_at is not None else 0)
    if event.occurred_at is not None: _write_blob(out,event.occurred_at.encode("utf-8"))
    return bytes(out)


def _decode_event(data: bytes, offset: int) -> tuple[NativeTransitionEvent,int]:
    event_id_ref,offset=decode_uvarint(data,offset)
    opcode,offset=decode_uvarint(data,offset)
    payload,offset=_read_blob(data,offset)
    base_revision,offset=decode_uvarint(data,offset)
    end=offset+32
    if end>len(data): raise DSRValidationError("STREAM_EVENT_HASH_TRUNCATED")
    previous_hash=data[offset:end].hex(); offset=end
    if offset>=len(data): raise DSRValidationError("STREAM_EVENT_TIME_FLAG_TRUNCATED")
    flag=data[offset]; offset+=1; occurred_at=None
    if flag==1:
        blob,offset=_read_blob(data,offset)
        try: occurred_at=blob.decode("utf-8")
        except UnicodeDecodeError as exc: raise DSRValidationError("STREAM_EVENT_TIME_INVALID") from exc
    elif flag!=0: raise DSRValidationError("STREAM_EVENT_TIME_FLAG_INVALID")
    return NativeTransitionEvent(event_id_ref,opcode,payload,base_revision,previous_hash,occurred_at),offset


def encode_event_stream(stream: NativeEventStream) -> bytes:
    out=bytearray(STREAM_MAGIC)
    out += encode_uvarint(STREAM_FORMAT_VERSION)
    out += encode_uvarint(stream.registry_revision)
    out += bytes.fromhex(stream.registry_hash)
    out += bytes.fromhex(stream.genesis_hash)
    out += encode_uvarint(len(stream.records))
    for record in stream.records:
        _write_blob(out,_encode_event(record.event)); out += bytes.fromhex(record.next_hash)
    return bytes(out)


def decode_event_stream(data: bytes, registry: NativeSymbolRegistry) -> NativeEventStream:
    if not isinstance(data,(bytes,bytearray,memoryview)): raise DSRValidationError("STREAM_BYTES_REQUIRED")
    data=bytes(data)
    if not data.startswith(STREAM_MAGIC): raise DSRValidationError("STREAM_MAGIC_INVALID")
    offset=len(STREAM_MAGIC)
    version,offset=decode_uvarint(data,offset)
    if version!=STREAM_FORMAT_VERSION: raise DSRValidationError("STREAM_VERSION_UNSUPPORTED")
    registry_revision,offset=decode_uvarint(data,offset)
    end=offset+32
    if end>len(data): raise DSRValidationError("STREAM_REGISTRY_HASH_TRUNCATED")
    registry_hash=data[offset:end].hex(); offset=end
    if registry.revision<registry_revision: raise DSRValidationError("STREAM_REGISTRY_TOO_OLD")
    if registry.prefix_hash(registry_revision)!=registry_hash: raise DSRValidationError("STREAM_REGISTRY_HASH_MISMATCH")
    end=offset+32
    if end>len(data): raise DSRValidationError("STREAM_GENESIS_HASH_TRUNCATED")
    genesis_hash=data[offset:end].hex(); offset=end
    count,offset=decode_uvarint(data,offset); records=[]
    for _ in range(count):
        blob,offset=_read_blob(data,offset); event,used=_decode_event(blob,0)
        if used!=len(blob): raise DSRValidationError("STREAM_EVENT_TRAILING_DATA")
        registry.resolve(event.event_id_ref,SymbolNamespace.EVENT_ID)
        end=offset+32
        if end>len(data): raise DSRValidationError("STREAM_NEXT_HASH_TRUNCATED")
        next_hash=data[offset:end].hex(); offset=end
        records.append(NativeStreamRecord(event,next_hash))
    if offset!=len(data): raise DSRValidationError("STREAM_TRAILING_DATA")
    stream=NativeEventStream(registry_revision,registry_hash,genesis_hash,tuple(records))
    if encode_event_stream(stream)!=data: raise DSRValidationError("STREAM_NONCANONICAL")
    return stream



def _native_topology_basis_hash(state: NativeSemanticState, registry: NativeSymbolRegistry) -> str:
    out = bytearray(b"ISQL-TOPOLOGY-BASIS\x05")
    for rel in state.relations:
        for ref, ns in (
            (rel.subject_ref, SymbolNamespace.ATOM),
            (rel.predicate_ref, SymbolNamespace.PREDICATE),
            (rel.object_ref, SymbolNamespace.ATOM),
        ):
            raw = registry.resolve(ref, ns)
            out += len(raw).to_bytes(8, "big")
            out += raw
    return hashlib.sha256(bytes(out)).hexdigest()


def _native_graph_stats(state: NativeSemanticState) -> tuple[int, int, int]:
    nodes: set[int] = set()
    edges: set[tuple[int, int]] = set()
    adjacency: dict[int, set[int]] = {}
    for rel in state.relations:
        u, v = rel.subject_ref, rel.object_ref
        nodes.update((u, v))
        edge = (u, v) if u <= v else (v, u)
        edges.add(edge)
        adjacency.setdefault(u, set()).add(v)
        adjacency.setdefault(v, set()).add(u)
    if not nodes:
        return 0, 0, 0
    remaining = set(nodes)
    components = 0
    while remaining:
        components += 1
        stack = [remaining.pop()]
        while stack:
            node = stack.pop()
            for neighbor in adjacency.get(node, ()):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
    cycle_rank = len(edges) - len(nodes) + components
    return len(nodes), components, max(cycle_rank, 0)


def _compute_native_topology(state: NativeSemanticState, method_refs: tuple[int, ...], registry: NativeSymbolRegistry) -> tuple[NativeTopology, ...]:
    _, components, cycle_rank = _native_graph_stats(state)
    basis = _native_topology_basis_hash(state, registry)
    out: list[NativeTopology] = []
    for method_ref in sorted(set(method_refs)):
        method = registry.resolve(method_ref, SymbolNamespace.TOPOLOGY_METHOD)
        if method == b"graph.components":
            value = components
        elif method == b"graph.cycle_rank":
            value = cycle_rank
        else:
            raise DSRExecutionError("UNKNOWN_TOPOLOGY_METHOD")
        descriptor_ref = registry.lookup(SymbolNamespace.TOPOLOGY_DESCRIPTOR, method)
        if descriptor_ref is None:
            raise DSRExecutionError("TOPOLOGY_DESCRIPTOR_SYMBOL_MISSING")
        out.append(NativeTopology(descriptor_ref, method_ref, basis, value, 1.0, {}))
    return tuple(out)


def _native_axis_variant(axis: NativeAxis) -> tuple[int, bytes]:
    return axis.domain_ref, _encode_semantic_value(axis.value)


def _fuse_native_proposals(
    state: NativeSemanticState,
    proposals: tuple[NativeProposal, ...],
    axis_threshold: float,
    relation_threshold: float,
) -> NativeSemanticState:
    if not proposals:
        raise DSRExecutionError("FUSION_PROPOSALS_REQUIRED")
    if not 0.0 <= axis_threshold <= 1.0 or not 0.0 <= relation_threshold <= 1.0:
        raise DSRExecutionError("FUSION_THRESHOLD_OUT_OF_RANGE")
    base_hash = registered_state_hash(state)
    ordered = tuple(sorted(proposals, key=lambda p: (p.proposal_ref, p.source_ref)))
    if len({p.proposal_ref for p in ordered}) != len(ordered):
        raise DSRExecutionError("FUSION_DUPLICATE_PROPOSAL")
    for proposal in ordered:
        if proposal.identity_ref != state.identity_ref:
            raise DSRExecutionError("PROPOSAL_IDENTITY_MISMATCH")
        if proposal.base_revision != state.revision:
            raise DSRExecutionError("PROPOSAL_BASE_REVISION_MISMATCH")
        if proposal.base_hash != base_hash:
            raise DSRExecutionError("PROPOSAL_BASE_HASH_MISMATCH")
    total_weight = sum(p.source_weight for p in ordered)
    fused_axes = {a.key_ref: a for a in state.axes}
    groups: dict[int, list[tuple[NativeProposal, NativeAxis]]] = {}
    for proposal in ordered:
        for axis in proposal.axes:
            groups.setdefault(axis.key_ref, []).append((proposal, axis))
    for key_ref in sorted(groups):
        variants: dict[tuple[int, bytes], list[tuple[NativeProposal, NativeAxis]]] = {}
        for proposal, axis in groups[key_ref]:
            variants.setdefault(_native_axis_variant(axis), []).append((proposal, axis))
        scored = []
        for variant_key, rows in variants.items():
            support = sum(p.source_weight * (1.0 - axis.uncertainty) for p, axis in rows)
            scored.append((support, variant_key, rows))
        scored.sort(key=lambda row: (-row[0], row[1]))
        best_support, _, winners = scored[0]
        tied = len(scored) > 1 and math.isclose(best_support, scored[1][0], rel_tol=0.0, abs_tol=1e-15)
        ratio = best_support / total_weight
        if tied or ratio < axis_threshold:
            continue
        exemplar = winners[0][1]
        fused_axes[key_ref] = NativeAxis(
            exemplar.key_ref,
            exemplar.domain_ref,
            exemplar.value,
            max(0.0, min(1.0, 1.0 - ratio)),
            max(axis.resolution for _, axis in winners),
        )
    positive_support: dict[tuple[int, int, int], float] = {}
    negative_support: dict[tuple[int, int, int], float] = {}
    rel_obj: dict[tuple[int, int, int], NativeRelation] = {}
    for proposal in ordered:
        for rel in proposal.relations:
            positive_support[rel.key] = positive_support.get(rel.key, 0.0) + proposal.source_weight
            rel_obj[rel.key] = rel
        for rel in proposal.negative_relations:
            negative_support[rel.key] = negative_support.get(rel.key, 0.0) + proposal.source_weight
            rel_obj[rel.key] = rel
    positives = {rel.key: rel for rel in state.relations}
    negatives = {rel.key: rel for rel in state.negative_relations}
    for key in sorted(set(positive_support) | set(negative_support)):
        pos_ratio = positive_support.get(key, 0.0) / total_weight
        neg_ratio = negative_support.get(key, 0.0) / total_weight
        pos_ok = pos_ratio >= relation_threshold
        neg_ok = neg_ratio >= relation_threshold
        if pos_ok and neg_ok:
            continue
        if pos_ok:
            positives[key] = rel_obj[key]
            negatives.pop(key, None)
        elif neg_ok:
            negatives[key] = rel_obj[key]
            positives.pop(key, None)
    new_relations = tuple(sorted(positives.values(), key=lambda r: r.key))
    topology = state.topology if new_relations == state.relations else ()
    return replace(
        state,
        axes=tuple(sorted(fused_axes.values(), key=lambda a: a.key_ref)),
        relations=new_relations,
        negative_relations=tuple(sorted(negatives.values(), key=lambda r: r.key)),
        topology=topology,
    )


def _decode_relation_payload(payload: bytes) -> NativeRelation:
    blob, offset = _read_blob(payload, 0)
    rel, used = _decode_relation(blob, 0)
    if used != len(blob) or offset != len(payload):
        raise DSRExecutionError("STREAM_RELATION_PAYLOAD_INVALID")
    return rel


def apply_native_event(state: NativeSemanticState, event: NativeTransitionEvent, registry: NativeSymbolRegistry) -> NativeSemanticState:
    """Execute a transition directly on registered numeric state.

    This is the v0.5 canonical executor. It never materializes SemanticState.
    """
    if event.base_revision != state.revision:
        raise DSRExecutionError("STREAM_EVENT_BASE_REVISION_MISMATCH")
    if event.previous_hash != registered_state_hash(state):
        raise DSRExecutionError("STREAM_EVENT_PREVIOUS_HASH_MISMATCH")
    op = operation_name(event.opcode)
    payload = event.payload
    changes: dict[str, Any] = {}

    if op == "set_context":
        offset = 0
        count, offset = decode_uvarint(payload, offset)
        rows = []
        for _ in range(count):
            ref, offset = decode_uvarint(payload, offset)
            registry.resolve(ref, SymbolNamespace.CONTEXT_KEY)
            blob, offset = _read_blob(payload, offset)
            value, used = decode_value(blob)
            if used != len(blob):
                raise DSRExecutionError("STREAM_CONTEXT_VALUE_INVALID")
            rows.append((ref, value))
        if offset != len(payload):
            raise DSRExecutionError("STREAM_PAYLOAD_TRAILING_DATA")
        changes["context"] = tuple(rows)
    elif op == "upsert_axis":
        blob, offset = _read_blob(payload, 0)
        axis, used = _decode_axis(blob, 0)
        if used != len(blob) or offset != len(payload):
            raise DSRExecutionError("STREAM_AXIS_PAYLOAD_INVALID")
        changes["axes"] = tuple(a for a in state.axes if a.key_ref != axis.key_ref) + (axis,)
    elif op == "remove_axis":
        key_ref, offset = decode_uvarint(payload, 0)
        if offset != len(payload):
            raise DSRExecutionError("STREAM_PAYLOAD_TRAILING_DATA")
        axes = tuple(a for a in state.axes if a.key_ref != key_ref)
        if len(axes) == len(state.axes):
            raise DSRExecutionError("AXIS_NOT_FOUND")
        changes["axes"] = axes
    elif op in {"upsert_relation", "remove_relation", "deny_relation", "retract_relation"}:
        rel = _decode_relation_payload(payload)
        positives = {r.key: r for r in state.relations}
        negatives = {r.key: r for r in state.negative_relations}
        if op == "upsert_relation":
            positives[rel.key] = rel
            negatives.pop(rel.key, None)
        elif op == "remove_relation":
            if rel.key not in positives:
                raise DSRExecutionError("RELATION_NOT_FOUND")
            positives.pop(rel.key)
        elif op == "deny_relation":
            positives.pop(rel.key, None)
            negatives[rel.key] = rel
        else:
            positives.pop(rel.key, None)
            negatives.pop(rel.key, None)
        changes["relations"] = tuple(sorted(positives.values(), key=lambda r: r.key))
        changes["negative_relations"] = tuple(sorted(negatives.values(), key=lambda r: r.key))
        changes["topology"] = ()
    elif op == "upsert_projection":
        blob, offset = _read_blob(payload, 0)
        item, used = _decode_projection(blob, 0)
        if used != len(blob) or offset != len(payload):
            raise DSRExecutionError("STREAM_PROJECTION_PAYLOAD_INVALID")
        changes["projections"] = tuple(x for x in state.projections if x.projection_ref != item.projection_ref) + (item,)
    elif op == "remove_projection":
        ref, offset = decode_uvarint(payload, 0)
        if offset != len(payload):
            raise DSRExecutionError("STREAM_PAYLOAD_TRAILING_DATA")
        rows = tuple(x for x in state.projections if x.projection_ref != ref)
        if len(rows) == len(state.projections):
            raise DSRExecutionError("PROJECTION_NOT_FOUND")
        changes["projections"] = rows
    elif op == "refresh_topology":
        offset = 0
        count, offset = decode_uvarint(payload, offset)
        refs = []
        for _ in range(count):
            ref, offset = decode_uvarint(payload, offset)
            registry.resolve(ref, SymbolNamespace.TOPOLOGY_METHOD)
            refs.append(ref)
        if offset != len(payload):
            raise DSRExecutionError("STREAM_PAYLOAD_TRAILING_DATA")
        changes["topology"] = _compute_native_topology(state, tuple(refs), registry)
    elif op == "upsert_topology_descriptor":
        blob, offset = _read_blob(payload, 0)
        item, used = _decode_topology(blob, 0)
        if used != len(blob) or offset != len(payload):
            raise DSRExecutionError("STREAM_TOPOLOGY_PAYLOAD_INVALID")
        if item.basis_hash != _native_topology_basis_hash(state, registry):
            raise DSRExecutionError("TOPOLOGY_BASIS_HASH_MISMATCH")
        changes["topology"] = tuple(x for x in state.topology if x.descriptor_ref != item.descriptor_ref) + (item,)
    elif op == "remove_topology_descriptor":
        ref, offset = decode_uvarint(payload, 0)
        if offset != len(payload):
            raise DSRExecutionError("STREAM_PAYLOAD_TRAILING_DATA")
        rows = tuple(x for x in state.topology if x.descriptor_ref != ref)
        if len(rows) == len(state.topology):
            raise DSRExecutionError("TOPOLOGY_DESCRIPTOR_NOT_FOUND")
        changes["topology"] = rows
    elif op == "fuse_proposals":
        offset = 0
        count, offset = decode_uvarint(payload, offset)
        proposals = []
        for _ in range(count):
            blob, offset = _read_blob(payload, offset)
            proposal, used = _decode_proposal(blob, 0)
            if used != len(blob):
                raise DSRExecutionError("STREAM_PROPOSAL_PAYLOAD_INVALID")
            proposals.append(proposal)
        axis_threshold, offset = _read_f64(payload, offset)
        relation_threshold, offset = _read_f64(payload, offset)
        if offset != len(payload):
            raise DSRExecutionError("STREAM_PAYLOAD_TRAILING_DATA")
        fused = _fuse_native_proposals(state, tuple(proposals), axis_threshold, relation_threshold)
        changes.update({
            "axes": fused.axes,
            "relations": fused.relations,
            "negative_relations": fused.negative_relations,
            "topology": fused.topology,
        })
    else:
        raise DSRExecutionError("STREAM_OPERATION_UNSUPPORTED")

    return replace(state, revision=state.revision + 1, **changes)

def build_event_stream(genesis: SemanticState, events: Iterable[TransitionEvent], registry: NativeSymbolRegistry) -> NativeEventStream:
    current_semantic=genesis
    current_machine=compile_registered_state(genesis,registry)
    genesis_hash=registered_state_hash(current_machine)
    records=[]
    for event in events:
        # Source inspection events are accepted only at the compiler boundary.
        if event.base_revision != current_semantic.revision or event.previous_hash != state_hash(current_semantic):
            raise DSRExecutionError("STREAM_SOURCE_EVENT_CHAIN_MISMATCH")
        native_event=compile_native_event(event,current_machine,registry)
        next_machine=apply_native_event(current_machine,native_event,registry)
        records.append(NativeStreamRecord(native_event,registered_state_hash(next_machine)))
        current_semantic=apply_event(current_semantic,event).state
        current_machine=next_machine
    return NativeEventStream(registry.revision,registry.prefix_hash(registry.revision),genesis_hash,tuple(records))


def replay_native_stream(genesis: NativeSemanticState, stream: NativeEventStream, registry: NativeSymbolRegistry) -> NativeSemanticState:
    if registry.revision<stream.registry_revision or registry.prefix_hash(stream.registry_revision)!=stream.registry_hash:
        raise DSRExecutionError("STREAM_REGISTRY_MISMATCH")
    current=genesis
    if registered_state_hash(current)!=stream.genesis_hash:
        raise DSRExecutionError("STREAM_GENESIS_HASH_MISMATCH")
    for record in stream.records:
        if record.event.base_revision!=current.revision:
            raise DSRExecutionError("STREAM_EVENT_BASE_REVISION_MISMATCH")
        if record.event.previous_hash!=registered_state_hash(current):
            raise DSRExecutionError("STREAM_EVENT_PREVIOUS_HASH_MISMATCH")
        next_machine=apply_native_event(current,record.event,registry)
        if registered_state_hash(next_machine)!=record.next_hash:
            raise DSRExecutionError("STREAM_RECORD_NEXT_HASH_MISMATCH")
        current=next_machine
    return current
