from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import hashlib
from typing import Iterable, Any

from .errors import DSRValidationError


REGISTRY_MAGIC = bytes((0xD5, 0x51, 0xB1, 0x04))
REGISTRY_FORMAT_VERSION = 4


class SymbolNamespace(IntEnum):
    IDENTITY = 1
    AXIS_KEY = 2
    AXIS_DOMAIN = 3
    ATOM = 4
    PREDICATE = 5
    TOPOLOGY_DESCRIPTOR = 6
    TOPOLOGY_METHOD = 7
    PROJECTION_ID = 8
    MEDIA_TYPE = 9
    EVENT_ID = 10
    SOURCE_ID = 11
    PROPOSAL_ID = 12
    CONTEXT_KEY = 13
    BRANCH_ID = 14
    PROGRAM_ID = 15
    INSTRUCTION_ID = 16


def _uvarint(value: int) -> bytes:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DSRValidationError("REGISTRY_UVARINT_INVALID")
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _read_uvarint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    start = offset
    while offset < len(data):
        b = data[offset]
        offset += 1
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            if data[start:offset] != _uvarint(value):
                raise DSRValidationError("REGISTRY_UVARINT_NONCANONICAL")
            return value, offset
        shift += 7
        if shift > 70:
            raise DSRValidationError("REGISTRY_UVARINT_TOO_LARGE")
    raise DSRValidationError("REGISTRY_UVARINT_TRUNCATED")


@dataclass(frozen=True, slots=True)
class SymbolEntry:
    namespace: SymbolNamespace
    payload: bytes

    def __post_init__(self) -> None:
        try:
            ns = SymbolNamespace(int(self.namespace))
        except (TypeError, ValueError) as exc:
            raise DSRValidationError("REGISTRY_NAMESPACE_INVALID") from exc
        object.__setattr__(self, "namespace", ns)
        if not isinstance(self.payload, (bytes, bytearray, memoryview)):
            raise DSRValidationError("REGISTRY_PAYLOAD_BYTES_REQUIRED")
        raw = bytes(self.payload)
        if not raw:
            raise DSRValidationError("REGISTRY_PAYLOAD_EMPTY")
        object.__setattr__(self, "payload", raw)


@dataclass(frozen=True, slots=True)
class NativeSymbolRegistry:
    entries: tuple[SymbolEntry, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple) or not all(isinstance(x, SymbolEntry) for x in self.entries):
            raise DSRValidationError("REGISTRY_ENTRIES_INVALID")
        seen: set[tuple[int, bytes]] = set()
        for entry in self.entries:
            key = (int(entry.namespace), entry.payload)
            if key in seen:
                raise DSRValidationError("REGISTRY_DUPLICATE_ENTRY")
            seen.add(key)

    @property
    def revision(self) -> int:
        return len(self.entries)

    def lookup(self, namespace: SymbolNamespace, payload: bytes) -> int | None:
        ns = SymbolNamespace(int(namespace))
        raw = bytes(payload)
        for idx, entry in enumerate(self.entries, 1):
            if entry.namespace == ns and entry.payload == raw:
                return idx
        return None

    def lookup_text(self, namespace: SymbolNamespace, text: str) -> int | None:
        if not isinstance(text, str):
            raise DSRValidationError("REGISTRY_TEXT_REQUIRED")
        return self.lookup(namespace, text.encode("utf-8"))

    def intern(self, namespace: SymbolNamespace, payload: bytes) -> tuple["NativeSymbolRegistry", int]:
        ns = SymbolNamespace(int(namespace))
        raw = bytes(payload)
        existing = self.lookup(ns, raw)
        if existing is not None:
            return self, existing
        entry = SymbolEntry(ns, raw)
        return NativeSymbolRegistry(self.entries + (entry,)), self.revision + 1

    def intern_text(self, namespace: SymbolNamespace, text: str) -> tuple["NativeSymbolRegistry", int]:
        if not isinstance(text, str) or not text:
            raise DSRValidationError("REGISTRY_TEXT_REQUIRED")
        return self.intern(namespace, text.encode("utf-8"))

    def resolve(self, symbol_id: int, namespace: SymbolNamespace | None = None) -> bytes:
        if not isinstance(symbol_id, int) or isinstance(symbol_id, bool) or symbol_id <= 0 or symbol_id > self.revision:
            raise DSRValidationError("REGISTRY_SYMBOL_ID_INVALID")
        entry = self.entries[symbol_id - 1]
        if namespace is not None and entry.namespace != SymbolNamespace(int(namespace)):
            raise DSRValidationError("REGISTRY_NAMESPACE_MISMATCH")
        return entry.payload

    def resolve_text(self, symbol_id: int, namespace: SymbolNamespace | None = None) -> str:
        raw = self.resolve(symbol_id, namespace)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DSRValidationError("REGISTRY_SYMBOL_NOT_UTF8") from exc

    def prefix_hash(self, revision: int | None = None) -> str:
        if revision is None:
            revision = self.revision
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0 or revision > self.revision:
            raise DSRValidationError("REGISTRY_REVISION_INVALID")
        return hashlib.sha256(_encode_entries(self.entries[:revision])).hexdigest()

    def verify_prefix(self, revision: int, expected_hash: str) -> bool:
        return self.prefix_hash(revision) == expected_hash


def _encode_entries(entries: tuple[SymbolEntry, ...]) -> bytes:
    out = bytearray(REGISTRY_MAGIC)
    out += _uvarint(REGISTRY_FORMAT_VERSION)
    out += _uvarint(len(entries))
    for entry in entries:
        out += _uvarint(int(entry.namespace))
        out += _uvarint(len(entry.payload))
        out += entry.payload
    return bytes(out)


def encode_registry(registry: NativeSymbolRegistry) -> bytes:
    if not isinstance(registry, NativeSymbolRegistry):
        raise TypeError("encode_registry requires NativeSymbolRegistry")
    return _encode_entries(registry.entries)


def decode_registry(data: bytes) -> NativeSymbolRegistry:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise DSRValidationError("REGISTRY_BYTES_REQUIRED")
    data = bytes(data)
    if not data.startswith(REGISTRY_MAGIC):
        raise DSRValidationError("REGISTRY_MAGIC_INVALID")
    offset = len(REGISTRY_MAGIC)
    version, offset = _read_uvarint(data, offset)
    if version != REGISTRY_FORMAT_VERSION:
        raise DSRValidationError("REGISTRY_VERSION_UNSUPPORTED")
    count, offset = _read_uvarint(data, offset)
    entries: list[SymbolEntry] = []
    for _ in range(count):
        ns_value, offset = _read_uvarint(data, offset)
        try:
            ns = SymbolNamespace(ns_value)
        except ValueError as exc:
            raise DSRValidationError("REGISTRY_NAMESPACE_INVALID") from exc
        length, offset = _read_uvarint(data, offset)
        end = offset + length
        if end > len(data):
            raise DSRValidationError("REGISTRY_PAYLOAD_TRUNCATED")
        entries.append(SymbolEntry(ns, data[offset:end]))
        offset = end
    if offset != len(data):
        raise DSRValidationError("REGISTRY_TRAILING_DATA")
    registry = NativeSymbolRegistry(tuple(entries))
    if encode_registry(registry) != data:
        raise DSRValidationError("REGISTRY_NONCANONICAL")
    return registry


def registry_hash(registry: NativeSymbolRegistry) -> str:
    return hashlib.sha256(encode_registry(registry)).hexdigest()


def _add_text(pairs: set[tuple[SymbolNamespace, bytes]], namespace: SymbolNamespace, value: Any) -> None:
    if isinstance(value, str) and value:
        pairs.add((namespace, value.encode("utf-8")))


def _collect_axis(pairs: set[tuple[SymbolNamespace, bytes]], axis: Any) -> None:
    from .model import SpectrumAxis
    if not isinstance(axis, SpectrumAxis):
        axis = SpectrumAxis.from_dict(axis)
    _add_text(pairs, SymbolNamespace.AXIS_KEY, axis.key)
    _add_text(pairs, SymbolNamespace.AXIS_DOMAIN, axis.domain)


def _collect_relation(pairs: set[tuple[SymbolNamespace, bytes]], relation: Any) -> None:
    from .model import TypedRelation
    if not isinstance(relation, TypedRelation):
        relation = TypedRelation.from_dict(relation)
    _add_text(pairs, SymbolNamespace.ATOM, relation.subject)
    _add_text(pairs, SymbolNamespace.PREDICATE, relation.predicate)
    _add_text(pairs, SymbolNamespace.ATOM, relation.object)


def _collect_projection(pairs: set[tuple[SymbolNamespace, bytes]], projection: Any) -> None:
    from .model import SemanticProjection
    if not isinstance(projection, SemanticProjection):
        projection = SemanticProjection.from_dict(projection)
    _add_text(pairs, SymbolNamespace.PROJECTION_ID, projection.projection_id)
    _add_text(pairs, SymbolNamespace.MEDIA_TYPE, projection.media_type)


def _collect_topology(pairs: set[tuple[SymbolNamespace, bytes]], descriptor: Any) -> None:
    from .model import TopologyDescriptor
    if not isinstance(descriptor, TopologyDescriptor):
        descriptor = TopologyDescriptor.from_dict(descriptor)
    _add_text(pairs, SymbolNamespace.TOPOLOGY_DESCRIPTOR, descriptor.descriptor_id)
    _add_text(pairs, SymbolNamespace.TOPOLOGY_METHOD, descriptor.method)


def _extend(registry: NativeSymbolRegistry, pairs: set[tuple[SymbolNamespace, bytes]]) -> NativeSymbolRegistry:
    missing = [(ns, payload) for ns, payload in pairs if registry.lookup(ns, payload) is None]
    missing.sort(key=lambda item: (int(item[0]), item[1]))
    out = registry
    for ns, payload in missing:
        out, _ = out.intern(ns, payload)
    return out


def extend_registry_for_state(registry: NativeSymbolRegistry, state: Any) -> NativeSymbolRegistry:
    from .model import SemanticState
    if not isinstance(registry, NativeSymbolRegistry):
        raise TypeError("registry must be NativeSymbolRegistry")
    if not isinstance(state, SemanticState):
        raise TypeError("state must be SemanticState")
    pairs: set[tuple[SymbolNamespace, bytes]] = set()
    _add_text(pairs, SymbolNamespace.IDENTITY, state.identity)
    for key in state.context:
        _add_text(pairs, SymbolNamespace.CONTEXT_KEY, key)
    for axis in state.axes:
        _collect_axis(pairs, axis)
    for relation in state.relations:
        _collect_relation(pairs, relation)
    for relation in state.negative_relations:
        _collect_relation(pairs, relation)
    for descriptor in state.topology:
        _collect_topology(pairs, descriptor)
    for projection in state.projections:
        _collect_projection(pairs, projection)
    return _extend(registry, pairs)


def extend_registry_for_events(registry: NativeSymbolRegistry, events: Iterable[Any]) -> NativeSymbolRegistry:
    from .events import TransitionEvent
    from .fusion import SemanticProposal
    pairs: set[tuple[SymbolNamespace, bytes]] = set()
    for event in events:
        if not isinstance(event, TransitionEvent):
            raise TypeError("events must contain TransitionEvent")
        _add_text(pairs, SymbolNamespace.EVENT_ID, event.event_id)
        p = event.payload
        op = event.operation
        if op == "set_context":
            context = p.get("context", {})
            if isinstance(context, dict):
                for key in context:
                    _add_text(pairs, SymbolNamespace.CONTEXT_KEY, key)
        elif op == "upsert_axis":
            _collect_axis(pairs, p.get("axis"))
        elif op == "remove_axis":
            _add_text(pairs, SymbolNamespace.AXIS_KEY, p.get("key"))
        elif op in {"upsert_relation", "remove_relation", "deny_relation", "retract_relation"}:
            _collect_relation(pairs, p.get("relation", p))
        elif op == "upsert_projection":
            _collect_projection(pairs, p.get("projection"))
        elif op == "remove_projection":
            _add_text(pairs, SymbolNamespace.PROJECTION_ID, p.get("projection_id"))
        elif op == "refresh_topology":
            for method in p.get("methods", ("graph.components", "graph.cycle_rank")):
                _add_text(pairs, SymbolNamespace.TOPOLOGY_METHOD, method)
                # Built-in topology refresh currently emits descriptor_id == method.
                # Pre-register the generated descriptor so replay can materialize
                # the next registered snapshot without mutating the registry.
                _add_text(pairs, SymbolNamespace.TOPOLOGY_DESCRIPTOR, method)
        elif op == "upsert_topology_descriptor":
            _collect_topology(pairs, p.get("descriptor"))
        elif op == "remove_topology_descriptor":
            _add_text(pairs, SymbolNamespace.TOPOLOGY_DESCRIPTOR, p.get("descriptor_id"))
        elif op == "fuse_proposals":
            for raw in p.get("proposals", ()):
                proposal = raw if isinstance(raw, SemanticProposal) else SemanticProposal.from_dict(raw)
                _add_text(pairs, SymbolNamespace.PROPOSAL_ID, proposal.proposal_id)
                _add_text(pairs, SymbolNamespace.SOURCE_ID, proposal.source_id)
                _add_text(pairs, SymbolNamespace.IDENTITY, proposal.identity)
                for axis in proposal.axes:
                    _collect_axis(pairs, axis)
                for relation in proposal.relations:
                    _collect_relation(pairs, relation)
                for relation in proposal.negative_relations:
                    _collect_relation(pairs, relation)
    return _extend(registry, pairs)
