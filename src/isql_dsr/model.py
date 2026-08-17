from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, TypeAlias

from .errors import DSRValidationError

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


def _text(value: Any, error: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DSRValidationError(error)
    return value.strip()


def _json_scalar(value: Any, error: str) -> JSONScalar:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise DSRValidationError(error)


def _json_value(value: Any, error: str) -> JSONValue:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DSRValidationError(error)
        return value
    if isinstance(value, list):
        return [_json_value(x, error) for x in value]
    if isinstance(value, tuple):
        return [_json_value(x, error) for x in value]
    if isinstance(value, Mapping):
        out: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise DSRValidationError(error)
            out[key] = _json_value(item, error)
        return out
    raise DSRValidationError(error)


def _scalar_identity(value: JSONScalar) -> tuple[str, str]:
    return type(value).__name__, repr(value)


@dataclass(frozen=True, slots=True)
class PointValue:
    value: JSONScalar

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _json_scalar(self.value, "POINT_VALUE_MUST_BE_JSON_SCALAR"))

    def to_dict(self) -> dict[str, JSONValue]:
        return {"kind": "point", "value": self.value}


@dataclass(frozen=True, slots=True)
class IntervalValue:
    lower: float
    upper: float

    def __post_init__(self) -> None:
        if isinstance(self.lower, bool) or isinstance(self.upper, bool):
            raise DSRValidationError("INTERVAL_BOUNDS_MUST_BE_FINITE_NUMBERS")
        try:
            lower = float(self.lower)
            upper = float(self.upper)
        except (TypeError, ValueError) as exc:
            raise DSRValidationError("INTERVAL_BOUNDS_MUST_BE_FINITE_NUMBERS") from exc
        if not math.isfinite(lower) or not math.isfinite(upper):
            raise DSRValidationError("INTERVAL_BOUNDS_MUST_BE_FINITE_NUMBERS")
        if lower > upper:
            raise DSRValidationError("INTERVAL_LOWER_GT_UPPER")
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)

    def to_dict(self) -> dict[str, JSONValue]:
        return {"kind": "interval", "lower": self.lower, "upper": self.upper}


@dataclass(frozen=True, slots=True)
class CandidateSetValue:
    values: tuple[JSONScalar, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.values, tuple) or not self.values:
            raise DSRValidationError("CANDIDATE_VALUES_MUST_BE_NONEMPTY_TUPLE")
        cleaned = tuple(_json_scalar(x, "CANDIDATE_VALUE_MUST_BE_JSON_SCALAR") for x in self.values)
        ids = [_scalar_identity(x) for x in cleaned]
        if len(set(ids)) != len(ids):
            raise DSRValidationError("CANDIDATE_VALUES_MUST_BE_UNIQUE")
        object.__setattr__(self, "values", cleaned)

    def to_dict(self) -> dict[str, JSONValue]:
        return {"kind": "candidates", "values": list(self.values)}


@dataclass(frozen=True, slots=True)
class VectorValue:
    items: tuple["SemanticValue", ...]

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            raise DSRValidationError("VECTOR_ITEMS_MUST_BE_TUPLE")
        if not all(isinstance(x, (PointValue, IntervalValue, CandidateSetValue, VectorValue, RecordValue)) for x in self.items):
            raise DSRValidationError("VECTOR_ITEM_INVALID")

    def to_dict(self) -> dict[str, JSONValue]:
        return {"kind": "vector", "items": [x.to_dict() for x in self.items]}


@dataclass(frozen=True, slots=True)
class RecordValue:
    fields: tuple[tuple[int, "SemanticValue"], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.fields, tuple):
            raise DSRValidationError("RECORD_FIELDS_MUST_BE_TUPLE")
        cleaned = []
        seen = set()
        for row in self.fields:
            if not isinstance(row, tuple) or len(row) != 2:
                raise DSRValidationError("RECORD_FIELD_INVALID")
            ref, value = row
            if not isinstance(ref, int) or isinstance(ref, bool) or ref <= 0:
                raise DSRValidationError("RECORD_FIELD_REF_INVALID")
            if ref in seen:
                raise DSRValidationError("RECORD_FIELD_REF_DUPLICATE")
            if not isinstance(value, (PointValue, IntervalValue, CandidateSetValue, VectorValue, RecordValue)):
                raise DSRValidationError("RECORD_FIELD_VALUE_INVALID")
            seen.add(ref)
            cleaned.append((ref, value))
        object.__setattr__(self, "fields", tuple(sorted(cleaned, key=lambda row: row[0])))

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "kind": "record",
            "fields": [{"ref": ref, "value": value.to_dict()} for ref, value in self.fields],
        }


SemanticValue: TypeAlias = PointValue | IntervalValue | CandidateSetValue | VectorValue | RecordValue


def semantic_value_from_dict(value: Mapping[str, Any]) -> SemanticValue:
    if not isinstance(value, Mapping):
        raise DSRValidationError("AXIS_VALUE_MUST_BE_OBJECT")
    kind = value.get("kind")
    if kind == "point":
        return PointValue(value.get("value"))
    if kind == "interval":
        return IntervalValue(value.get("lower"), value.get("upper"))
    if kind == "candidates":
        raw = value.get("values")
        if not isinstance(raw, list):
            raise DSRValidationError("CANDIDATE_VALUES_MUST_BE_LIST")
        return CandidateSetValue(tuple(raw))
    if kind == "vector":
        raw = value.get("items")
        if not isinstance(raw, list):
            raise DSRValidationError("VECTOR_ITEMS_MUST_BE_LIST")
        return VectorValue(tuple(semantic_value_from_dict(x) for x in raw))
    if kind == "record":
        raw = value.get("fields")
        if not isinstance(raw, list):
            raise DSRValidationError("RECORD_FIELDS_MUST_BE_LIST")
        rows = []
        for row in raw:
            if not isinstance(row, Mapping):
                raise DSRValidationError("RECORD_FIELD_MUST_BE_OBJECT")
            rows.append((row.get("ref"), semantic_value_from_dict(row.get("value"))))
        return RecordValue(tuple(rows))
    raise DSRValidationError("UNKNOWN_AXIS_VALUE_KIND")


@dataclass(frozen=True, slots=True)
class SpectrumAxis:
    key: str
    domain: str
    value: SemanticValue
    uncertainty: float = 0.0
    resolution: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _text(self.key, "AXIS_KEY_REQUIRED"))
        object.__setattr__(self, "domain", _text(self.domain, "AXIS_DOMAIN_REQUIRED"))
        if not isinstance(self.value, (PointValue, IntervalValue, CandidateSetValue, VectorValue, RecordValue)):
            raise DSRValidationError("AXIS_VALUE_INVALID")
        if isinstance(self.uncertainty, bool):
            raise DSRValidationError("AXIS_UNCERTAINTY_OUT_OF_RANGE")
        try:
            uncertainty = float(self.uncertainty)
        except (TypeError, ValueError) as exc:
            raise DSRValidationError("AXIS_UNCERTAINTY_OUT_OF_RANGE") from exc
        if not math.isfinite(uncertainty) or not (0.0 <= uncertainty <= 1.0):
            raise DSRValidationError("AXIS_UNCERTAINTY_OUT_OF_RANGE")
        if not isinstance(self.resolution, int) or isinstance(self.resolution, bool) or self.resolution < 0:
            raise DSRValidationError("AXIS_RESOLUTION_MUST_BE_NONNEGATIVE_INT")
        object.__setattr__(self, "uncertainty", uncertainty)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "domain": self.domain,
            "value": self.value.to_dict(),
            "uncertainty": self.uncertainty,
            "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SpectrumAxis":
        if not isinstance(value, Mapping):
            raise DSRValidationError("AXIS_MUST_BE_OBJECT")
        raw_value = value.get("value")
        if not isinstance(raw_value, Mapping):
            raise DSRValidationError("AXIS_VALUE_MUST_BE_OBJECT")
        return cls(
            key=value.get("key"),
            domain=value.get("domain"),
            value=semantic_value_from_dict(raw_value),
            uncertainty=value.get("uncertainty", 0.0),
            resolution=value.get("resolution", 0),
        )


@dataclass(frozen=True, slots=True)
class TypedRelation:
    subject: str
    predicate: str
    object: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject", _text(self.subject, "RELATION_SUBJECT_REQUIRED"))
        object.__setattr__(self, "predicate", _text(self.predicate, "RELATION_PREDICATE_REQUIRED"))
        object.__setattr__(self, "object", _text(self.object, "RELATION_OBJECT_REQUIRED"))

    @property
    def key(self) -> tuple[str, str, str]:
        return self.subject, self.predicate, self.object

    def to_dict(self) -> dict[str, str]:
        return {"subject": self.subject, "predicate": self.predicate, "object": self.object}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TypedRelation":
        if not isinstance(value, Mapping):
            raise DSRValidationError("RELATION_MUST_BE_OBJECT")
        return cls(value.get("subject"), value.get("predicate"), value.get("object"))


@dataclass(frozen=True, slots=True)
class TopologyDescriptor:
    descriptor_id: str
    method: str
    basis_hash: str
    value: JSONValue
    confidence: float = 1.0
    parameters: dict[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "descriptor_id", _text(self.descriptor_id, "TOPOLOGY_DESCRIPTOR_ID_REQUIRED"))
        object.__setattr__(self, "method", _text(self.method, "TOPOLOGY_METHOD_REQUIRED"))
        if not isinstance(self.basis_hash, str) or len(self.basis_hash) != 64 or any(c not in "0123456789abcdef" for c in self.basis_hash):
            raise DSRValidationError("TOPOLOGY_BASIS_HASH_INVALID")
        object.__setattr__(self, "value", _json_value(self.value, "TOPOLOGY_VALUE_NOT_JSON"))
        if isinstance(self.confidence, bool):
            raise DSRValidationError("TOPOLOGY_CONFIDENCE_OUT_OF_RANGE")
        try:
            confidence = float(self.confidence)
        except (TypeError, ValueError) as exc:
            raise DSRValidationError("TOPOLOGY_CONFIDENCE_OUT_OF_RANGE") from exc
        if not math.isfinite(confidence) or not (0.0 <= confidence <= 1.0):
            raise DSRValidationError("TOPOLOGY_CONFIDENCE_OUT_OF_RANGE")
        object.__setattr__(self, "confidence", confidence)
        if not isinstance(self.parameters, Mapping):
            raise DSRValidationError("TOPOLOGY_PARAMETERS_MUST_BE_OBJECT")
        parameters = _json_value(dict(self.parameters), "TOPOLOGY_PARAMETERS_NOT_JSON")
        assert isinstance(parameters, dict)
        object.__setattr__(self, "parameters", parameters)

    def to_dict(self) -> dict[str, Any]:
        return {
            "descriptor_id": self.descriptor_id,
            "method": self.method,
            "basis_hash": self.basis_hash,
            "value": self.value,
            "confidence": self.confidence,
            "parameters": self.parameters,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TopologyDescriptor":
        if not isinstance(value, Mapping):
            raise DSRValidationError("TOPOLOGY_DESCRIPTOR_MUST_BE_OBJECT")
        parameters = value.get("parameters", {})
        if not isinstance(parameters, Mapping):
            raise DSRValidationError("TOPOLOGY_PARAMETERS_MUST_BE_OBJECT")
        return cls(
            descriptor_id=value.get("descriptor_id"),
            method=value.get("method"),
            basis_hash=value.get("basis_hash"),
            value=value.get("value"),
            confidence=value.get("confidence", 1.0),
            parameters=dict(parameters),
        )


@dataclass(frozen=True, slots=True)
class SemanticProjection:
    projection_id: str
    media_type: str
    payload: JSONValue

    def __post_init__(self) -> None:
        object.__setattr__(self, "projection_id", _text(self.projection_id, "PROJECTION_ID_REQUIRED"))
        object.__setattr__(self, "media_type", _text(self.media_type, "PROJECTION_MEDIA_TYPE_REQUIRED"))
        object.__setattr__(self, "payload", _json_value(self.payload, "PROJECTION_PAYLOAD_NOT_JSON"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "projection_id": self.projection_id,
            "media_type": self.media_type,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SemanticProjection":
        if not isinstance(value, Mapping):
            raise DSRValidationError("PROJECTION_MUST_BE_OBJECT")
        return cls(value.get("projection_id"), value.get("media_type"), value.get("payload"))


@dataclass(frozen=True, slots=True)
class SemanticState:
    identity: str
    revision: int = 0
    context: dict[str, JSONValue] = field(default_factory=dict)
    axes: tuple[SpectrumAxis, ...] = ()
    relations: tuple[TypedRelation, ...] = ()
    topology: tuple[TopologyDescriptor, ...] = ()
    projections: tuple[SemanticProjection, ...] = ()
    history: tuple[dict[str, JSONValue], ...] = ()
    negative_relations: tuple[TypedRelation, ...] = ()

    SCHEMA = "isql.dsr-state/v0.3"
    LEGACY_SCHEMAS = {"isql.dsr-state/v0.2"}

    def __post_init__(self) -> None:
        object.__setattr__(self, "identity", _text(self.identity, "STATE_IDENTITY_REQUIRED"))
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 0:
            raise DSRValidationError("STATE_REVISION_MUST_BE_NONNEGATIVE_INT")
        if not isinstance(self.context, Mapping):
            raise DSRValidationError("STATE_CONTEXT_MUST_BE_OBJECT")
        context = _json_value(dict(self.context), "STATE_CONTEXT_NOT_JSON")
        assert isinstance(context, dict)
        object.__setattr__(self, "context", context)

        if not isinstance(self.axes, tuple) or not all(isinstance(x, SpectrumAxis) for x in self.axes):
            raise DSRValidationError("STATE_AXES_MUST_BE_AXIS_TUPLE")
        axis_keys = [x.key for x in self.axes]
        if len(set(axis_keys)) != len(axis_keys):
            raise DSRValidationError("DUPLICATE_AXIS_KEY")
        object.__setattr__(self, "axes", tuple(sorted(self.axes, key=lambda x: x.key)))

        if not isinstance(self.relations, tuple) or not all(isinstance(x, TypedRelation) for x in self.relations):
            raise DSRValidationError("STATE_RELATIONS_MUST_BE_RELATION_TUPLE")
        rel_keys = [x.key for x in self.relations]
        if len(set(rel_keys)) != len(rel_keys):
            raise DSRValidationError("DUPLICATE_RELATION")
        object.__setattr__(self, "relations", tuple(sorted(self.relations, key=lambda x: x.key)))

        if not isinstance(self.negative_relations, tuple) or not all(isinstance(x, TypedRelation) for x in self.negative_relations):
            raise DSRValidationError("STATE_NEGATIVE_RELATIONS_MUST_BE_RELATION_TUPLE")
        neg_keys = [x.key for x in self.negative_relations]
        if len(set(neg_keys)) != len(neg_keys):
            raise DSRValidationError("DUPLICATE_NEGATIVE_RELATION")
        if set(rel_keys) & set(neg_keys):
            raise DSRValidationError("RELATION_POLARITY_CONTRADICTION")
        object.__setattr__(self, "negative_relations", tuple(sorted(self.negative_relations, key=lambda x: x.key)))

        if not isinstance(self.topology, tuple) or not all(isinstance(x, TopologyDescriptor) for x in self.topology):
            raise DSRValidationError("STATE_TOPOLOGY_MUST_BE_DESCRIPTOR_TUPLE")
        topology_ids = [x.descriptor_id for x in self.topology]
        if len(set(topology_ids)) != len(topology_ids):
            raise DSRValidationError("DUPLICATE_TOPOLOGY_DESCRIPTOR_ID")
        object.__setattr__(self, "topology", tuple(sorted(self.topology, key=lambda x: x.descriptor_id)))

        if not isinstance(self.projections, tuple) or not all(isinstance(x, SemanticProjection) for x in self.projections):
            raise DSRValidationError("STATE_PROJECTIONS_MUST_BE_PROJECTION_TUPLE")
        projection_ids = [x.projection_id for x in self.projections]
        if len(set(projection_ids)) != len(projection_ids):
            raise DSRValidationError("DUPLICATE_PROJECTION_ID")
        object.__setattr__(self, "projections", tuple(sorted(self.projections, key=lambda x: x.projection_id)))

        if not isinstance(self.history, tuple):
            raise DSRValidationError("STATE_HISTORY_MUST_BE_TUPLE")
        normalized_history: list[dict[str, JSONValue]] = []
        for item in self.history:
            if not isinstance(item, Mapping):
                raise DSRValidationError("STATE_HISTORY_ITEM_MUST_BE_OBJECT")
            normalized = _json_value(dict(item), "STATE_HISTORY_NOT_JSON")
            assert isinstance(normalized, dict)
            normalized_history.append(normalized)
        object.__setattr__(self, "history", tuple(normalized_history))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.SCHEMA,
            "identity": self.identity,
            "revision": self.revision,
            "context": self.context,
            "axes": [x.to_dict() for x in self.axes],
            "relations": [x.to_dict() for x in self.relations],
            "negative_relations": [x.to_dict() for x in self.negative_relations],
            "topology": [x.to_dict() for x in self.topology],
            "projections": [x.to_dict() for x in self.projections],
            "history": list(self.history),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SemanticState":
        if not isinstance(value, Mapping):
            raise DSRValidationError("STATE_MUST_BE_OBJECT")
        if value.get("schema") not in (None, cls.SCHEMA, *cls.LEGACY_SCHEMAS):
            raise DSRValidationError("INVALID_STATE_SCHEMA")
        axes = value.get("axes", [])
        relations = value.get("relations", [])
        negative_relations = value.get("negative_relations", [])
        topology = value.get("topology", [])
        projections = value.get("projections", [])
        history = value.get("history", [])
        if not all(isinstance(x, list) for x in (axes, relations, negative_relations, topology, projections, history)):
            raise DSRValidationError("STATE_COLLECTIONS_MUST_BE_LISTS")
        context = value.get("context", {})
        if not isinstance(context, Mapping):
            raise DSRValidationError("STATE_CONTEXT_MUST_BE_OBJECT")
        return cls(
            identity=value.get("identity"),
            revision=value.get("revision", 0),
            context=dict(context),
            axes=tuple(SpectrumAxis.from_dict(x) for x in axes),
            relations=tuple(TypedRelation.from_dict(x) for x in relations),
            negative_relations=tuple(TypedRelation.from_dict(x) for x in negative_relations),
            topology=tuple(TopologyDescriptor.from_dict(x) for x in topology),
            projections=tuple(SemanticProjection.from_dict(x) for x in projections),
            history=tuple(dict(x) for x in history),
        )
