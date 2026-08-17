from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from .canonical import canonical_json, state_hash
from .errors import DSRValidationError
from .model import SemanticProjection, SemanticState, SpectrumAxis, TopologyDescriptor, TypedRelation

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_WIRE_RE = re.compile(r"^ISQL(?P<version>[1-9][0-9]*):(?P<domain>[A-Z]+):(?P<resolution>R[0-4]):(?P<control>[A-Z]+)(?P<payload>[0-9]+)$")


def _canonical_object(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def encode_decimal_payload(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise DSRValidationError("CORE_PAYLOAD_TEXT_REQUIRED")
    return "".join(f"{byte:03d}" for byte in value.encode("utf-8"))


def decode_decimal_payload(value: str) -> str:
    if not isinstance(value, str) or not value or not value.isascii() or not value.isdigit() or len(value) % 3:
        raise DSRValidationError("CORE_DECIMAL_PAYLOAD_INVALID")
    raw = bytearray()
    for idx in range(0, len(value), 3):
        byte = int(value[idx : idx + 3])
        if byte > 255:
            raise DSRValidationError("CORE_DECIMAL_PAYLOAD_BYTE_OUT_OF_RANGE")
        raw.append(byte)
    try:
        return bytes(raw).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DSRValidationError("CORE_DECIMAL_PAYLOAD_INVALID_UTF8") from exc


@dataclass(frozen=True, slots=True)
class SemanticSnapshot:
    identity: str
    axes: tuple[SpectrumAxis, ...] = ()
    relations: tuple[TypedRelation, ...] = ()
    topology: tuple[TopologyDescriptor, ...] = ()
    projections: tuple[SemanticProjection, ...] = ()

    SCHEMA = "isql.dsr-semantic-snapshot/v0.2"

    def __post_init__(self) -> None:
        if not isinstance(self.identity, str) or not self.identity.strip():
            raise DSRValidationError("SEMANTIC_SNAPSHOT_IDENTITY_REQUIRED")
        object.__setattr__(self, "identity", self.identity.strip())
        if not isinstance(self.axes, tuple) or not all(isinstance(x, SpectrumAxis) for x in self.axes):
            raise DSRValidationError("SEMANTIC_SNAPSHOT_AXES_INVALID")
        if len({x.key for x in self.axes}) != len(self.axes):
            raise DSRValidationError("SEMANTIC_SNAPSHOT_DUPLICATE_AXIS")
        object.__setattr__(self, "axes", tuple(sorted(self.axes, key=lambda x: x.key)))
        if not isinstance(self.relations, tuple) or not all(isinstance(x, TypedRelation) for x in self.relations):
            raise DSRValidationError("SEMANTIC_SNAPSHOT_RELATIONS_INVALID")
        if len({x.key for x in self.relations}) != len(self.relations):
            raise DSRValidationError("SEMANTIC_SNAPSHOT_DUPLICATE_RELATION")
        object.__setattr__(self, "relations", tuple(sorted(self.relations, key=lambda x: x.key)))
        if not isinstance(self.topology, tuple) or not all(isinstance(x, TopologyDescriptor) for x in self.topology):
            raise DSRValidationError("SEMANTIC_SNAPSHOT_TOPOLOGY_INVALID")
        if len({x.descriptor_id for x in self.topology}) != len(self.topology):
            raise DSRValidationError("SEMANTIC_SNAPSHOT_DUPLICATE_TOPOLOGY")
        object.__setattr__(self, "topology", tuple(sorted(self.topology, key=lambda x: x.descriptor_id)))
        if not isinstance(self.projections, tuple) or not all(isinstance(x, SemanticProjection) for x in self.projections):
            raise DSRValidationError("SEMANTIC_SNAPSHOT_PROJECTIONS_INVALID")
        if len({x.projection_id for x in self.projections}) != len(self.projections):
            raise DSRValidationError("SEMANTIC_SNAPSHOT_DUPLICATE_PROJECTION")
        object.__setattr__(self, "projections", tuple(sorted(self.projections, key=lambda x: x.projection_id)))

    @classmethod
    def from_state(cls, state: SemanticState) -> "SemanticSnapshot":
        return cls(
            identity=state.identity,
            axes=state.axes,
            relations=state.relations,
            topology=state.topology,
            projections=state.projections,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.SCHEMA,
            "identity": self.identity,
            "axes": [x.to_dict() for x in self.axes],
            "relations": [x.to_dict() for x in self.relations],
            "topology": [x.to_dict() for x in self.topology],
            "projections": [x.to_dict() for x in self.projections],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SemanticSnapshot":
        if not isinstance(value, Mapping):
            raise DSRValidationError("SEMANTIC_SNAPSHOT_MUST_BE_OBJECT")
        if value.get("schema") not in (None, cls.SCHEMA):
            raise DSRValidationError("INVALID_SEMANTIC_SNAPSHOT_SCHEMA")
        axes = value.get("axes", [])
        relations = value.get("relations", [])
        topology = value.get("topology", [])
        projections = value.get("projections", [])
        if not all(isinstance(x, list) for x in (axes, relations, topology, projections)):
            raise DSRValidationError("SEMANTIC_SNAPSHOT_COLLECTIONS_MUST_BE_LISTS")
        return cls(
            identity=value.get("identity"),
            axes=tuple(SpectrumAxis.from_dict(x) for x in axes),
            relations=tuple(TypedRelation.from_dict(x) for x in relations),
            topology=tuple(TopologyDescriptor.from_dict(x) for x in topology),
            projections=tuple(SemanticProjection.from_dict(x) for x in projections),
        )

    @property
    def canonical_json(self) -> str:
        return _canonical_object(self.to_dict())

    @property
    def semantic_hash(self) -> str:
        return _sha256_text(self.canonical_json)


@dataclass(frozen=True, slots=True)
class CoreDomainEnvelope:
    domain: str
    identity: str
    revision: int
    state_hash: str
    content_hash: str
    payload_json: str
    payload_digits: str
    dsr_schema: str
    resolution: str = "R2"
    control: str = "DSR"
    protocol_version: int = 1
    schema: str = "isql.dsr-core-domain-envelope/v0.2"

    def __post_init__(self) -> None:
        if self.domain not in {"SEM", "STATE"}:
            raise DSRValidationError("CORE_ENVELOPE_DOMAIN_INVALID")
        if self.resolution != "R2":
            raise DSRValidationError("CORE_ENVELOPE_RESOLUTION_MUST_BE_R2")
        if self.control != "DSR":
            raise DSRValidationError("CORE_ENVELOPE_CONTROL_MUST_BE_DSR")
        if self.protocol_version != 1:
            raise DSRValidationError("CORE_ENVELOPE_PROTOCOL_VERSION_INVALID")
        if self.schema != "isql.dsr-core-domain-envelope/v0.2":
            raise DSRValidationError("INVALID_CORE_ENVELOPE_SCHEMA")
        if not isinstance(self.identity, str) or not self.identity.strip():
            raise DSRValidationError("CORE_ENVELOPE_IDENTITY_REQUIRED")
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 0:
            raise DSRValidationError("CORE_ENVELOPE_REVISION_INVALID")
        for value, error in ((self.state_hash, "CORE_ENVELOPE_STATE_HASH_INVALID"), (self.content_hash, "CORE_ENVELOPE_CONTENT_HASH_INVALID")):
            if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
                raise DSRValidationError(error)
        if not isinstance(self.payload_json, str) or not self.payload_json:
            raise DSRValidationError("CORE_ENVELOPE_PAYLOAD_REQUIRED")
        expected_digits = encode_decimal_payload(self.payload_json)
        if self.payload_digits != expected_digits:
            raise DSRValidationError("CORE_ENVELOPE_DIGITS_MISMATCH")
        if not _WIRE_RE.fullmatch(self.wire):
            raise DSRValidationError("CORE_ENVELOPE_WIRE_INVALID")

        try:
            raw = json.loads(self.payload_json)
        except json.JSONDecodeError as exc:
            raise DSRValidationError("CORE_ENVELOPE_PAYLOAD_INVALID_JSON") from exc
        if not isinstance(raw, Mapping):
            raise DSRValidationError("CORE_ENVELOPE_PAYLOAD_MUST_BE_OBJECT")
        if self.domain == "STATE":
            if self.dsr_schema != SemanticState.SCHEMA:
                raise DSRValidationError("CORE_ENVELOPE_DSR_SCHEMA_MISMATCH")
            state = SemanticState.from_dict(raw)
            if state.identity != self.identity or state.revision != self.revision:
                raise DSRValidationError("CORE_ENVELOPE_STATE_METADATA_MISMATCH")
            expected_json = canonical_json(state)
            if expected_json != self.payload_json:
                raise DSRValidationError("CORE_ENVELOPE_PAYLOAD_NOT_CANONICAL")
            expected_hash = state_hash(state)
            if expected_hash != self.state_hash or expected_hash != self.content_hash:
                raise DSRValidationError("CORE_ENVELOPE_STATE_HASH_MISMATCH")
        else:
            if self.dsr_schema != SemanticSnapshot.SCHEMA:
                raise DSRValidationError("CORE_ENVELOPE_DSR_SCHEMA_MISMATCH")
            snapshot = SemanticSnapshot.from_dict(raw)
            if snapshot.identity != self.identity:
                raise DSRValidationError("CORE_ENVELOPE_SEMANTIC_IDENTITY_MISMATCH")
            if snapshot.canonical_json != self.payload_json:
                raise DSRValidationError("CORE_ENVELOPE_PAYLOAD_NOT_CANONICAL")
            if snapshot.semantic_hash != self.content_hash:
                raise DSRValidationError("CORE_ENVELOPE_CONTENT_HASH_MISMATCH")

    @property
    def wire(self) -> str:
        return f"ISQL{self.protocol_version}:{self.domain}:{self.resolution}:{self.control}{self.payload_digits}"

    def to_state(self) -> SemanticState:
        if self.domain != "STATE":
            raise DSRValidationError("CORE_ENVELOPE_NOT_STATE")
        raw = json.loads(decode_decimal_payload(self.payload_digits))
        assert isinstance(raw, Mapping)
        return SemanticState.from_dict(raw)

    def to_semantic_snapshot(self) -> SemanticSnapshot:
        if self.domain != "SEM":
            raise DSRValidationError("CORE_ENVELOPE_NOT_SEM")
        raw = json.loads(decode_decimal_payload(self.payload_digits))
        assert isinstance(raw, Mapping)
        return SemanticSnapshot.from_dict(raw)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "protocol_version": self.protocol_version,
            "domain": self.domain,
            "resolution": self.resolution,
            "control": self.control,
            "dsr_schema": self.dsr_schema,
            "identity": self.identity,
            "revision": self.revision,
            "state_hash": self.state_hash,
            "content_hash": self.content_hash,
            "payload_json": self.payload_json,
            "payload_digits": self.payload_digits,
            "wire": self.wire,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CoreDomainEnvelope":
        if not isinstance(value, Mapping):
            raise DSRValidationError("CORE_ENVELOPE_MUST_BE_OBJECT")
        return cls(
            domain=value.get("domain"),
            identity=value.get("identity"),
            revision=value.get("revision"),
            state_hash=value.get("state_hash"),
            content_hash=value.get("content_hash", value.get("state_hash")),
            payload_json=value.get("payload_json"),
            payload_digits=value.get("payload_digits"),
            dsr_schema=value.get("dsr_schema"),
            resolution=value.get("resolution", "R2"),
            control=value.get("control", "DSR"),
            protocol_version=value.get("protocol_version", 1),
            schema=value.get("schema", "isql.dsr-core-domain-envelope/v0.2"),
        )


CoreStateEnvelope = CoreDomainEnvelope


@dataclass(frozen=True, slots=True)
class CoreEnvelopeBundle:
    sem: CoreDomainEnvelope
    state: CoreDomainEnvelope

    def __post_init__(self) -> None:
        if self.sem.domain != "SEM" or self.state.domain != "STATE":
            raise DSRValidationError("CORE_BUNDLE_DOMAIN_MISMATCH")
        if self.sem.identity != self.state.identity or self.sem.revision != self.state.revision:
            raise DSRValidationError("CORE_BUNDLE_METADATA_MISMATCH")
        if self.sem.state_hash != self.state.state_hash:
            raise DSRValidationError("CORE_BUNDLE_STATE_HASH_MISMATCH")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "isql.dsr-core-bundle/v0.2",
            "sem": self.sem.to_dict(),
            "state": self.state.to_dict(),
        }


def to_core_sem_envelope(state: SemanticState) -> CoreDomainEnvelope:
    snapshot = SemanticSnapshot.from_state(state)
    payload_json = snapshot.canonical_json
    return CoreDomainEnvelope(
        domain="SEM",
        identity=state.identity,
        revision=state.revision,
        state_hash=state_hash(state),
        content_hash=snapshot.semantic_hash,
        payload_json=payload_json,
        payload_digits=encode_decimal_payload(payload_json),
        dsr_schema=SemanticSnapshot.SCHEMA,
    )


def to_core_state_envelope(state: SemanticState) -> CoreDomainEnvelope:
    payload_json = canonical_json(state)
    digest = state_hash(state)
    return CoreDomainEnvelope(
        domain="STATE",
        identity=state.identity,
        revision=state.revision,
        state_hash=digest,
        content_hash=digest,
        payload_json=payload_json,
        payload_digits=encode_decimal_payload(payload_json),
        dsr_schema=SemanticState.SCHEMA,
    )


def to_core_bundle(state: SemanticState) -> CoreEnvelopeBundle:
    return CoreEnvelopeBundle(sem=to_core_sem_envelope(state), state=to_core_state_envelope(state))


def decode_core_envelope(envelope: CoreDomainEnvelope) -> SemanticState | SemanticSnapshot:
    if envelope.domain == "STATE":
        return envelope.to_state()
    if envelope.domain == "SEM":
        return envelope.to_semantic_snapshot()
    raise DSRValidationError("CORE_ENVELOPE_DOMAIN_INVALID")

# ---- v0.3 AI-native bridge -------------------------------------------------


def encode_decimal_bytes(value: bytes) -> str:
    if not isinstance(value, (bytes, bytearray, memoryview)) or not value:
        raise DSRValidationError("NATIVE_CORE_PAYLOAD_BYTES_REQUIRED")
    return "".join(f"{byte:03d}" for byte in bytes(value))


def decode_decimal_bytes(value: str) -> bytes:
    if not isinstance(value, str) or not value or not value.isascii() or not value.isdigit() or len(value) % 3:
        raise DSRValidationError("NATIVE_CORE_DECIMAL_PAYLOAD_INVALID")
    raw = bytearray()
    for idx in range(0, len(value), 3):
        byte = int(value[idx:idx+3])
        if byte > 255:
            raise DSRValidationError("NATIVE_CORE_DECIMAL_BYTE_OUT_OF_RANGE")
        raw.append(byte)
    return bytes(raw)


@dataclass(frozen=True, slots=True)
class NativeCoreDomainEnvelope:
    domain: str
    identity: str
    revision: int
    state_hash: str
    content_hash: str
    payload_digits: str
    resolution: str = "R3"
    control: str = "DSRN"
    protocol_version: int = 1
    schema: str = "isql.dsr-native-core-envelope/v0.3"

    def __post_init__(self) -> None:
        from .native import decode_state, encode_state
        if self.domain not in {"SEM", "STATE"}:
            raise DSRValidationError("NATIVE_CORE_DOMAIN_INVALID")
        if self.resolution != "R3":
            raise DSRValidationError("NATIVE_CORE_RESOLUTION_INVALID")
        if self.control != "DSRN":
            raise DSRValidationError("NATIVE_CORE_CONTROL_INVALID")
        if self.protocol_version != 1:
            raise DSRValidationError("NATIVE_CORE_PROTOCOL_VERSION_INVALID")
        if self.schema != "isql.dsr-native-core-envelope/v0.3":
            raise DSRValidationError("NATIVE_CORE_SCHEMA_INVALID")
        if not isinstance(self.identity, str) or not self.identity.strip():
            raise DSRValidationError("NATIVE_CORE_IDENTITY_REQUIRED")
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 0:
            raise DSRValidationError("NATIVE_CORE_REVISION_INVALID")
        for value, error in (
            (self.state_hash, "NATIVE_CORE_STATE_HASH_INVALID"),
            (self.content_hash, "NATIVE_CORE_CONTENT_HASH_INVALID"),
        ):
            if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
                raise DSRValidationError(error)
        payload = decode_decimal_bytes(self.payload_digits)
        if hashlib.sha256(payload).hexdigest() != self.content_hash:
            raise DSRValidationError("NATIVE_CORE_CONTENT_HASH_MISMATCH")
        decoded = decode_state(payload)
        if decoded.identity != self.identity or decoded.revision != self.revision:
            raise DSRValidationError("NATIVE_CORE_METADATA_MISMATCH")
        if encode_state(decoded) != payload:
            raise DSRValidationError("NATIVE_CORE_PAYLOAD_NONCANONICAL")
        if self.domain == "STATE" and state_hash(decoded) != self.state_hash:
            raise DSRValidationError("NATIVE_CORE_STATE_HASH_MISMATCH")
        if not _WIRE_RE.fullmatch(self.wire):
            raise DSRValidationError("NATIVE_CORE_WIRE_INVALID")

    @property
    def wire(self) -> str:
        return f"ISQL{self.protocol_version}:{self.domain}:{self.resolution}:{self.control}{self.payload_digits}"

    def to_state(self) -> SemanticState:
        from .native import decode_state
        return decode_state(decode_decimal_bytes(self.payload_digits))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "protocol_version": self.protocol_version,
            "domain": self.domain,
            "resolution": self.resolution,
            "control": self.control,
            "identity": self.identity,
            "revision": self.revision,
            "state_hash": self.state_hash,
            "content_hash": self.content_hash,
            "payload_digits": self.payload_digits,
            "wire": self.wire,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "NativeCoreDomainEnvelope":
        if not isinstance(value, Mapping):
            raise DSRValidationError("NATIVE_CORE_ENVELOPE_MUST_BE_OBJECT")
        return cls(
            domain=value.get("domain"),
            identity=value.get("identity"),
            revision=value.get("revision"),
            state_hash=value.get("state_hash"),
            content_hash=value.get("content_hash"),
            payload_digits=value.get("payload_digits"),
            resolution=value.get("resolution", "R3"),
            control=value.get("control", "DSRN"),
            protocol_version=value.get("protocol_version", 1),
            schema=value.get("schema", "isql.dsr-native-core-envelope/v0.3"),
        )


@dataclass(frozen=True, slots=True)
class NativeCoreEnvelopeBundle:
    sem: NativeCoreDomainEnvelope
    state: NativeCoreDomainEnvelope

    def __post_init__(self) -> None:
        if self.sem.domain != "SEM" or self.state.domain != "STATE":
            raise DSRValidationError("NATIVE_CORE_BUNDLE_DOMAIN_MISMATCH")
        if self.sem.identity != self.state.identity or self.sem.revision != self.state.revision:
            raise DSRValidationError("NATIVE_CORE_BUNDLE_METADATA_MISMATCH")
        if self.sem.state_hash != self.state.state_hash:
            raise DSRValidationError("NATIVE_CORE_BUNDLE_STATE_HASH_MISMATCH")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "isql.dsr-native-core-bundle/v0.3",
            "sem": self.sem.to_dict(),
            "state": self.state.to_dict(),
        }


def _native_semantic_state(state: SemanticState) -> SemanticState:
    return SemanticState(
        identity=state.identity,
        revision=state.revision,
        context={},
        axes=state.axes,
        relations=state.relations,
        topology=state.topology,
        projections=state.projections,
        history=(),
    )


def to_native_core_state_envelope(state: SemanticState) -> NativeCoreDomainEnvelope:
    from .native import encode_state
    payload = encode_state(state)
    digest = state_hash(state)
    return NativeCoreDomainEnvelope(
        domain="STATE",
        identity=state.identity,
        revision=state.revision,
        state_hash=digest,
        content_hash=hashlib.sha256(payload).hexdigest(),
        payload_digits=encode_decimal_bytes(payload),
    )


def to_native_core_sem_envelope(state: SemanticState) -> NativeCoreDomainEnvelope:
    from .native import encode_state
    semantic = _native_semantic_state(state)
    payload = encode_state(semantic)
    return NativeCoreDomainEnvelope(
        domain="SEM",
        identity=state.identity,
        revision=state.revision,
        state_hash=state_hash(state),
        content_hash=hashlib.sha256(payload).hexdigest(),
        payload_digits=encode_decimal_bytes(payload),
    )


def to_native_core_bundle(state: SemanticState) -> NativeCoreEnvelopeBundle:
    return NativeCoreEnvelopeBundle(
        sem=to_native_core_sem_envelope(state),
        state=to_native_core_state_envelope(state),
    )
