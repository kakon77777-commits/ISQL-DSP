from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from .canonical import canonical_json, state_hash
from .errors import DSRValidationError
from .model import SemanticState


@dataclass(frozen=True, slots=True)
class CoreStateEnvelope:
    identity: str
    revision: int
    state_hash: str
    payload_json: str
    domain: str = "STATE"
    resolution: str = "R2"
    schema: str = "isql.dsr-core-state-envelope/v0.1"
    dsr_schema: str = SemanticState.SCHEMA

    def __post_init__(self) -> None:
        if self.domain != "STATE":
            raise DSRValidationError("CORE_ENVELOPE_DOMAIN_MUST_BE_STATE")
        if self.resolution != "R2":
            raise DSRValidationError("CORE_ENVELOPE_RESOLUTION_MUST_BE_R2")
        if self.schema != "isql.dsr-core-state-envelope/v0.1":
            raise DSRValidationError("INVALID_CORE_ENVELOPE_SCHEMA")
        if self.dsr_schema != SemanticState.SCHEMA:
            raise DSRValidationError("CORE_ENVELOPE_DSR_SCHEMA_MISMATCH")
        if not isinstance(self.payload_json, str) or not self.payload_json:
            raise DSRValidationError("CORE_ENVELOPE_PAYLOAD_REQUIRED")
        state = self.to_state(validate_hash=False)
        if state.identity != self.identity:
            raise DSRValidationError("CORE_ENVELOPE_IDENTITY_MISMATCH")
        if state.revision != self.revision:
            raise DSRValidationError("CORE_ENVELOPE_REVISION_MISMATCH")
        if state_hash(state) != self.state_hash:
            raise DSRValidationError("CORE_ENVELOPE_STATE_HASH_MISMATCH")
        if canonical_json(state) != self.payload_json:
            raise DSRValidationError("CORE_ENVELOPE_PAYLOAD_NOT_CANONICAL")

    def to_state(self, *, validate_hash: bool = True) -> SemanticState:
        try:
            raw = json.loads(self.payload_json)
        except json.JSONDecodeError as exc:
            raise DSRValidationError("CORE_ENVELOPE_PAYLOAD_INVALID_JSON") from exc
        if not isinstance(raw, Mapping):
            raise DSRValidationError("CORE_ENVELOPE_PAYLOAD_MUST_BE_OBJECT")
        state = SemanticState.from_dict(raw)
        if validate_hash and state_hash(state) != self.state_hash:
            raise DSRValidationError("CORE_ENVELOPE_STATE_HASH_MISMATCH")
        return state

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "domain": self.domain,
            "resolution": self.resolution,
            "dsr_schema": self.dsr_schema,
            "identity": self.identity,
            "revision": self.revision,
            "state_hash": self.state_hash,
            "payload_json": self.payload_json,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CoreStateEnvelope":
        if not isinstance(value, Mapping):
            raise DSRValidationError("CORE_ENVELOPE_MUST_BE_OBJECT")
        return cls(
            identity=value.get("identity"),
            revision=value.get("revision"),
            state_hash=value.get("state_hash"),
            payload_json=value.get("payload_json"),
            domain=value.get("domain", "STATE"),
            resolution=value.get("resolution", "R2"),
            schema=value.get("schema", "isql.dsr-core-state-envelope/v0.1"),
            dsr_schema=value.get("dsr_schema", SemanticState.SCHEMA),
        )


def to_core_state_envelope(state: SemanticState) -> CoreStateEnvelope:
    return CoreStateEnvelope(
        identity=state.identity,
        revision=state.revision,
        state_hash=state_hash(state),
        payload_json=canonical_json(state),
    )
