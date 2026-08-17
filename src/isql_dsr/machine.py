from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Any

from .errors import DSRValidationError
from .model import JSONValue, SemanticProjection, SemanticState, SpectrumAxis, TopologyDescriptor, TypedRelation
from .native import (
    decode_uvarint, decode_value, encode_uvarint, encode_value,
    _decode_semantic_value, _encode_semantic_value,
)
from .registry import NativeSymbolRegistry, SymbolNamespace


REGISTERED_STATE_MAGIC = bytes((0xD5, 0x51, 0xC1, 0x04))
REGISTERED_STATE_FORMAT_VERSION = 4


def _positive_ref(value: Any, error: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise DSRValidationError(error)
    return value


def _hash_hex(value: Any, error: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise DSRValidationError(error)
    return value


def _finite(value: Any, error: str) -> float:
    if isinstance(value, bool):
        raise DSRValidationError(error)
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise DSRValidationError(error) from exc
    if not math.isfinite(out):
        raise DSRValidationError(error)
    return out


@dataclass(frozen=True, slots=True)
class NativeAxis:
    key_ref: int
    domain_ref: int
    value: Any
    uncertainty: float = 0.0
    resolution: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "key_ref", _positive_ref(self.key_ref, "MACHINE_AXIS_KEY_REF_INVALID"))
        object.__setattr__(self, "domain_ref", _positive_ref(self.domain_ref, "MACHINE_AXIS_DOMAIN_REF_INVALID"))
        u = _finite(self.uncertainty, "MACHINE_AXIS_UNCERTAINTY_INVALID")
        if not 0.0 <= u <= 1.0:
            raise DSRValidationError("MACHINE_AXIS_UNCERTAINTY_INVALID")
        object.__setattr__(self, "uncertainty", u)
        if not isinstance(self.resolution, int) or isinstance(self.resolution, bool) or self.resolution < 0:
            raise DSRValidationError("MACHINE_AXIS_RESOLUTION_INVALID")


@dataclass(frozen=True, slots=True)
class NativeRelation:
    subject_ref: int
    predicate_ref: int
    object_ref: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_ref", _positive_ref(self.subject_ref, "MACHINE_RELATION_SUBJECT_REF_INVALID"))
        object.__setattr__(self, "predicate_ref", _positive_ref(self.predicate_ref, "MACHINE_RELATION_PREDICATE_REF_INVALID"))
        object.__setattr__(self, "object_ref", _positive_ref(self.object_ref, "MACHINE_RELATION_OBJECT_REF_INVALID"))

    @property
    def key(self) -> tuple[int, int, int]:
        return self.subject_ref, self.predicate_ref, self.object_ref


@dataclass(frozen=True, slots=True)
class NativeTopology:
    descriptor_ref: int
    method_ref: int
    basis_hash: str
    value: JSONValue
    confidence: float = 1.0
    parameters: dict[str, JSONValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "descriptor_ref", _positive_ref(self.descriptor_ref, "MACHINE_TOPOLOGY_DESCRIPTOR_REF_INVALID"))
        object.__setattr__(self, "method_ref", _positive_ref(self.method_ref, "MACHINE_TOPOLOGY_METHOD_REF_INVALID"))
        object.__setattr__(self, "basis_hash", _hash_hex(self.basis_hash, "MACHINE_TOPOLOGY_BASIS_HASH_INVALID"))
        c = _finite(self.confidence, "MACHINE_TOPOLOGY_CONFIDENCE_INVALID")
        if not 0.0 <= c <= 1.0:
            raise DSRValidationError("MACHINE_TOPOLOGY_CONFIDENCE_INVALID")
        object.__setattr__(self, "confidence", c)
        if self.parameters is None:
            object.__setattr__(self, "parameters", {})
        elif not isinstance(self.parameters, dict):
            raise DSRValidationError("MACHINE_TOPOLOGY_PARAMETERS_INVALID")


@dataclass(frozen=True, slots=True)
class NativeProjection:
    projection_ref: int
    media_type_ref: int
    payload: JSONValue

    def __post_init__(self) -> None:
        object.__setattr__(self, "projection_ref", _positive_ref(self.projection_ref, "MACHINE_PROJECTION_REF_INVALID"))
        object.__setattr__(self, "media_type_ref", _positive_ref(self.media_type_ref, "MACHINE_MEDIA_TYPE_REF_INVALID"))


@dataclass(frozen=True, slots=True)
class NativeSemanticState:
    registry_revision: int
    registry_hash: str
    identity_ref: int
    revision: int = 0
    context: tuple[tuple[int, JSONValue], ...] = ()
    axes: tuple[NativeAxis, ...] = ()
    relations: tuple[NativeRelation, ...] = ()
    topology: tuple[NativeTopology, ...] = ()
    projections: tuple[NativeProjection, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.registry_revision, int) or isinstance(self.registry_revision, bool) or self.registry_revision < 0:
            raise DSRValidationError("MACHINE_REGISTRY_REVISION_INVALID")
        object.__setattr__(self, "registry_hash", _hash_hex(self.registry_hash, "MACHINE_REGISTRY_HASH_INVALID"))
        object.__setattr__(self, "identity_ref", _positive_ref(self.identity_ref, "MACHINE_IDENTITY_REF_INVALID"))
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 0:
            raise DSRValidationError("MACHINE_REVISION_INVALID")
        context = tuple(sorted(self.context, key=lambda item: item[0]))
        if any(not isinstance(item, tuple) or len(item) != 2 for item in context):
            raise DSRValidationError("MACHINE_CONTEXT_INVALID")
        context_refs = [item[0] for item in context]
        if any(not isinstance(ref, int) or isinstance(ref, bool) or ref <= 0 for ref in context_refs):
            raise DSRValidationError("MACHINE_CONTEXT_REF_INVALID")
        if len(set(context_refs)) != len(context_refs):
            raise DSRValidationError("MACHINE_CONTEXT_DUPLICATE_REF")
        object.__setattr__(self, "context", context)
        if not all(isinstance(x, NativeAxis) for x in self.axes):
            raise DSRValidationError("MACHINE_AXES_INVALID")
        axes = tuple(sorted(self.axes, key=lambda x: x.key_ref))
        if len({x.key_ref for x in axes}) != len(axes):
            raise DSRValidationError("MACHINE_AXIS_DUPLICATE_KEY")
        object.__setattr__(self, "axes", axes)
        if not all(isinstance(x, NativeRelation) for x in self.relations):
            raise DSRValidationError("MACHINE_RELATIONS_INVALID")
        relations = tuple(sorted(self.relations, key=lambda x: x.key))
        if len({x.key for x in relations}) != len(relations):
            raise DSRValidationError("MACHINE_RELATION_DUPLICATE")
        object.__setattr__(self, "relations", relations)
        if not all(isinstance(x, NativeTopology) for x in self.topology):
            raise DSRValidationError("MACHINE_TOPOLOGY_INVALID")
        topology = tuple(sorted(self.topology, key=lambda x: x.descriptor_ref))
        if len({x.descriptor_ref for x in topology}) != len(topology):
            raise DSRValidationError("MACHINE_TOPOLOGY_DUPLICATE")
        object.__setattr__(self, "topology", topology)
        if not all(isinstance(x, NativeProjection) for x in self.projections):
            raise DSRValidationError("MACHINE_PROJECTIONS_INVALID")
        projections = tuple(sorted(self.projections, key=lambda x: x.projection_ref))
        if len({x.projection_ref for x in projections}) != len(projections):
            raise DSRValidationError("MACHINE_PROJECTION_DUPLICATE")
        object.__setattr__(self, "projections", projections)


def _ref(registry: NativeSymbolRegistry, namespace: SymbolNamespace, text: str) -> int:
    value = registry.lookup_text(namespace, text)
    if value is None:
        raise DSRValidationError("MACHINE_SYMBOL_MISSING")
    return value


def compile_registered_state(state: SemanticState, registry: NativeSymbolRegistry) -> NativeSemanticState:
    if not isinstance(state, SemanticState):
        raise TypeError("state must be SemanticState")
    if not isinstance(registry, NativeSymbolRegistry):
        raise TypeError("registry must be NativeSymbolRegistry")
    return NativeSemanticState(
        registry_revision=registry.revision,
        registry_hash=registry.prefix_hash(registry.revision),
        identity_ref=_ref(registry, SymbolNamespace.IDENTITY, state.identity),
        revision=state.revision,
        context=tuple((_ref(registry, SymbolNamespace.CONTEXT_KEY, key), value) for key, value in state.context.items()),
        axes=tuple(NativeAxis(
            _ref(registry, SymbolNamespace.AXIS_KEY, axis.key),
            _ref(registry, SymbolNamespace.AXIS_DOMAIN, axis.domain),
            axis.value,
            axis.uncertainty,
            axis.resolution,
        ) for axis in state.axes),
        relations=tuple(NativeRelation(
            _ref(registry, SymbolNamespace.ATOM, rel.subject),
            _ref(registry, SymbolNamespace.PREDICATE, rel.predicate),
            _ref(registry, SymbolNamespace.ATOM, rel.object),
        ) for rel in state.relations),
        topology=tuple(NativeTopology(
            _ref(registry, SymbolNamespace.TOPOLOGY_DESCRIPTOR, item.descriptor_id),
            _ref(registry, SymbolNamespace.TOPOLOGY_METHOD, item.method),
            item.basis_hash,
            item.value,
            item.confidence,
            item.parameters,
        ) for item in state.topology),
        projections=tuple(NativeProjection(
            _ref(registry, SymbolNamespace.PROJECTION_ID, item.projection_id),
            _ref(registry, SymbolNamespace.MEDIA_TYPE, item.media_type),
            item.payload,
        ) for item in state.projections),
    )


def _validate_registry_pin(state: NativeSemanticState, registry: NativeSymbolRegistry) -> None:
    if registry.revision < state.registry_revision:
        raise DSRValidationError("MACHINE_REGISTRY_TOO_OLD")
    if registry.prefix_hash(state.registry_revision) != state.registry_hash:
        raise DSRValidationError("MACHINE_REGISTRY_HASH_MISMATCH")


def inspect_registered_state(state: NativeSemanticState, registry: NativeSymbolRegistry) -> SemanticState:
    _validate_registry_pin(state, registry)
    return SemanticState(
        identity=registry.resolve_text(state.identity_ref, SymbolNamespace.IDENTITY),
        revision=state.revision,
        context={registry.resolve_text(ref, SymbolNamespace.CONTEXT_KEY): value for ref, value in state.context},
        axes=tuple(SpectrumAxis(
            registry.resolve_text(axis.key_ref, SymbolNamespace.AXIS_KEY),
            registry.resolve_text(axis.domain_ref, SymbolNamespace.AXIS_DOMAIN),
            axis.value,
            axis.uncertainty,
            axis.resolution,
        ) for axis in state.axes),
        relations=tuple(TypedRelation(
            registry.resolve_text(rel.subject_ref, SymbolNamespace.ATOM),
            registry.resolve_text(rel.predicate_ref, SymbolNamespace.PREDICATE),
            registry.resolve_text(rel.object_ref, SymbolNamespace.ATOM),
        ) for rel in state.relations),
        topology=tuple(TopologyDescriptor(
            registry.resolve_text(item.descriptor_ref, SymbolNamespace.TOPOLOGY_DESCRIPTOR),
            registry.resolve_text(item.method_ref, SymbolNamespace.TOPOLOGY_METHOD),
            item.basis_hash,
            item.value,
            item.confidence,
            item.parameters or {},
        ) for item in state.topology),
        projections=tuple(SemanticProjection(
            registry.resolve_text(item.projection_ref, SymbolNamespace.PROJECTION_ID),
            registry.resolve_text(item.media_type_ref, SymbolNamespace.MEDIA_TYPE),
            item.payload,
        ) for item in state.projections),
        history=(),
    )


def _write_blob(out: bytearray, data: bytes) -> None:
    out += encode_uvarint(len(data))
    out += data


def _read_blob(data: bytes, offset: int) -> tuple[bytes, int]:
    size, offset = decode_uvarint(data, offset)
    end = offset + size
    if end > len(data):
        raise DSRValidationError("MACHINE_BLOB_TRUNCATED")
    return data[offset:end], end


def _write_f64(out: bytearray, value: float) -> None:
    import struct
    out += struct.pack(">d", float(value))


def _read_f64(data: bytes, offset: int) -> tuple[float, int]:
    import struct
    end = offset + 8
    if end > len(data):
        raise DSRValidationError("MACHINE_FLOAT_TRUNCATED")
    value = struct.unpack(">d", data[offset:end])[0]
    if not math.isfinite(value):
        raise DSRValidationError("MACHINE_FLOAT_INVALID")
    return value, end


def encode_registered_state(state: NativeSemanticState) -> bytes:
    if not isinstance(state, NativeSemanticState):
        raise TypeError("encode_registered_state requires NativeSemanticState")
    out = bytearray(REGISTERED_STATE_MAGIC)
    out += encode_uvarint(REGISTERED_STATE_FORMAT_VERSION)
    out += encode_uvarint(state.registry_revision)
    out += bytes.fromhex(state.registry_hash)
    out += encode_uvarint(state.identity_ref)
    out += encode_uvarint(state.revision)
    out += encode_uvarint(len(state.context))
    for key_ref, value in state.context:
        out += encode_uvarint(key_ref)
        _write_blob(out, encode_value(value))
    out += encode_uvarint(len(state.axes))
    for axis in state.axes:
        out += encode_uvarint(axis.key_ref)
        out += encode_uvarint(axis.domain_ref)
        _write_blob(out, _encode_semantic_value(axis.value))
        _write_f64(out, axis.uncertainty)
        out += encode_uvarint(axis.resolution)
    out += encode_uvarint(len(state.relations))
    for rel in state.relations:
        out += encode_uvarint(rel.subject_ref)
        out += encode_uvarint(rel.predicate_ref)
        out += encode_uvarint(rel.object_ref)
    out += encode_uvarint(len(state.topology))
    for item in state.topology:
        out += encode_uvarint(item.descriptor_ref)
        out += encode_uvarint(item.method_ref)
        out += bytes.fromhex(item.basis_hash)
        _write_blob(out, encode_value(item.value))
        _write_f64(out, item.confidence)
        _write_blob(out, encode_value(item.parameters or {}))
    out += encode_uvarint(len(state.projections))
    for item in state.projections:
        out += encode_uvarint(item.projection_ref)
        out += encode_uvarint(item.media_type_ref)
        _write_blob(out, encode_value(item.payload))
    return bytes(out)


def _decode_unbound(data: bytes) -> NativeSemanticState:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise DSRValidationError("MACHINE_BYTES_REQUIRED")
    data = bytes(data)
    if not data.startswith(REGISTERED_STATE_MAGIC):
        raise DSRValidationError("MACHINE_MAGIC_INVALID")
    offset = len(REGISTERED_STATE_MAGIC)
    version, offset = decode_uvarint(data, offset)
    if version != REGISTERED_STATE_FORMAT_VERSION:
        raise DSRValidationError("MACHINE_VERSION_UNSUPPORTED")
    registry_revision, offset = decode_uvarint(data, offset)
    end = offset + 32
    if end > len(data):
        raise DSRValidationError("MACHINE_REGISTRY_HASH_TRUNCATED")
    registry_hash = data[offset:end].hex(); offset = end
    identity_ref, offset = decode_uvarint(data, offset)
    revision, offset = decode_uvarint(data, offset)
    context_count, offset = decode_uvarint(data, offset)
    context = []
    for _ in range(context_count):
        key_ref, offset = decode_uvarint(data, offset)
        blob, offset = _read_blob(data, offset)
        value, used = decode_value(blob)
        if used != len(blob):
            raise DSRValidationError("MACHINE_CONTEXT_TRAILING_DATA")
        context.append((key_ref, value))
    axis_count, offset = decode_uvarint(data, offset)
    axes = []
    for _ in range(axis_count):
        key_ref, offset = decode_uvarint(data, offset)
        domain_ref, offset = decode_uvarint(data, offset)
        blob, offset = _read_blob(data, offset)
        value, used = _decode_semantic_value(blob, 0)
        if used != len(blob):
            raise DSRValidationError("MACHINE_AXIS_VALUE_TRAILING_DATA")
        uncertainty, offset = _read_f64(data, offset)
        resolution, offset = decode_uvarint(data, offset)
        axes.append(NativeAxis(key_ref, domain_ref, value, uncertainty, resolution))
    relation_count, offset = decode_uvarint(data, offset)
    relations = []
    for _ in range(relation_count):
        s, offset = decode_uvarint(data, offset)
        p, offset = decode_uvarint(data, offset)
        o, offset = decode_uvarint(data, offset)
        relations.append(NativeRelation(s, p, o))
    topology_count, offset = decode_uvarint(data, offset)
    topology = []
    for _ in range(topology_count):
        descriptor_ref, offset = decode_uvarint(data, offset)
        method_ref, offset = decode_uvarint(data, offset)
        end = offset + 32
        if end > len(data):
            raise DSRValidationError("MACHINE_TOPOLOGY_HASH_TRUNCATED")
        basis_hash = data[offset:end].hex(); offset = end
        blob, offset = _read_blob(data, offset); value, used = decode_value(blob)
        if used != len(blob): raise DSRValidationError("MACHINE_TOPOLOGY_VALUE_TRAILING_DATA")
        confidence, offset = _read_f64(data, offset)
        blob, offset = _read_blob(data, offset); parameters, used = decode_value(blob)
        if used != len(blob) or not isinstance(parameters, dict):
            raise DSRValidationError("MACHINE_TOPOLOGY_PARAMETERS_INVALID")
        topology.append(NativeTopology(descriptor_ref, method_ref, basis_hash, value, confidence, parameters))
    projection_count, offset = decode_uvarint(data, offset)
    projections = []
    for _ in range(projection_count):
        projection_ref, offset = decode_uvarint(data, offset)
        media_type_ref, offset = decode_uvarint(data, offset)
        blob, offset = _read_blob(data, offset); payload, used = decode_value(blob)
        if used != len(blob): raise DSRValidationError("MACHINE_PROJECTION_TRAILING_DATA")
        projections.append(NativeProjection(projection_ref, media_type_ref, payload))
    if offset != len(data):
        raise DSRValidationError("MACHINE_TRAILING_DATA")
    state = NativeSemanticState(registry_revision, registry_hash, identity_ref, revision, tuple(context), tuple(axes), tuple(relations), tuple(topology), tuple(projections))
    if encode_registered_state(state) != data:
        raise DSRValidationError("MACHINE_NONCANONICAL")
    return state


def _validate_namespaces(state: NativeSemanticState, registry: NativeSymbolRegistry) -> None:
    registry.resolve(state.identity_ref, SymbolNamespace.IDENTITY)
    for ref, _ in state.context: registry.resolve(ref, SymbolNamespace.CONTEXT_KEY)
    for axis in state.axes:
        registry.resolve(axis.key_ref, SymbolNamespace.AXIS_KEY)
        registry.resolve(axis.domain_ref, SymbolNamespace.AXIS_DOMAIN)
    for rel in state.relations:
        registry.resolve(rel.subject_ref, SymbolNamespace.ATOM)
        registry.resolve(rel.predicate_ref, SymbolNamespace.PREDICATE)
        registry.resolve(rel.object_ref, SymbolNamespace.ATOM)
    for item in state.topology:
        registry.resolve(item.descriptor_ref, SymbolNamespace.TOPOLOGY_DESCRIPTOR)
        registry.resolve(item.method_ref, SymbolNamespace.TOPOLOGY_METHOD)
    for item in state.projections:
        registry.resolve(item.projection_ref, SymbolNamespace.PROJECTION_ID)
        registry.resolve(item.media_type_ref, SymbolNamespace.MEDIA_TYPE)


def decode_registered_state(data: bytes, registry: NativeSymbolRegistry) -> NativeSemanticState:
    state = _decode_unbound(data)
    _validate_registry_pin(state, registry)
    _validate_namespaces(state, registry)
    return state


def registered_state_hash(state: NativeSemanticState) -> str:
    return hashlib.sha256(encode_registered_state(state)).hexdigest()
