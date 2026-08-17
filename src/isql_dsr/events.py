from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from .canonical import state_hash
from .errors import DSRValidationError
from .model import JSONValue, SemanticState, _json_value, _text

_ALLOWED_OPERATIONS = {
    "set_context",
    "upsert_axis",
    "remove_axis",
    "upsert_relation",
    "remove_relation",
    "upsert_projection",
    "remove_projection",
    "refresh_topology",
    "upsert_topology_descriptor",
    "remove_topology_descriptor",
    "fuse_proposals",
}
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class TransitionEvent:
    event_id: str
    operation: str
    payload: dict[str, JSONValue]
    base_revision: int
    previous_hash: str
    occurred_at: str | None = None

    SCHEMA = "isql.dsr-event/v0.2"

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _text(self.event_id, "EVENT_ID_REQUIRED"))
        operation = _text(self.operation, "EVENT_OPERATION_REQUIRED")
        if operation not in _ALLOWED_OPERATIONS:
            raise DSRValidationError("UNKNOWN_EVENT_OPERATION")
        object.__setattr__(self, "operation", operation)
        if not isinstance(self.payload, Mapping):
            raise DSRValidationError("EVENT_PAYLOAD_MUST_BE_OBJECT")
        payload = _json_value(dict(self.payload), "EVENT_PAYLOAD_NOT_JSON")
        assert isinstance(payload, dict)
        object.__setattr__(self, "payload", payload)
        if not isinstance(self.base_revision, int) or isinstance(self.base_revision, bool) or self.base_revision < 0:
            raise DSRValidationError("EVENT_BASE_REVISION_INVALID")
        if not isinstance(self.previous_hash, str) or not _HASH_RE.fullmatch(self.previous_hash):
            raise DSRValidationError("EVENT_PREVIOUS_HASH_INVALID")
        if self.occurred_at is not None:
            object.__setattr__(self, "occurred_at", _text(self.occurred_at, "EVENT_OCCURRED_AT_INVALID"))

    @classmethod
    def for_state(
        cls,
        state: SemanticState,
        *,
        event_id: str,
        operation: str,
        payload: Mapping[str, Any],
        occurred_at: str | None = None,
    ) -> "TransitionEvent":
        return cls(
            event_id=event_id,
            operation=operation,
            payload=dict(payload),
            base_revision=state.revision,
            previous_hash=state_hash(state),
            occurred_at=occurred_at,
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema": self.SCHEMA,
            "event_id": self.event_id,
            "operation": self.operation,
            "payload": self.payload,
            "base_revision": self.base_revision,
            "previous_hash": self.previous_hash,
        }
        if self.occurred_at is not None:
            out["occurred_at"] = self.occurred_at
        return out

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TransitionEvent":
        if not isinstance(value, Mapping):
            raise DSRValidationError("EVENT_MUST_BE_OBJECT")
        if value.get("schema") not in (None, cls.SCHEMA):
            raise DSRValidationError("INVALID_EVENT_SCHEMA")
        payload = value.get("payload", {})
        if not isinstance(payload, Mapping):
            raise DSRValidationError("EVENT_PAYLOAD_MUST_BE_OBJECT")
        return cls(
            event_id=value.get("event_id"),
            operation=value.get("operation"),
            payload=dict(payload),
            base_revision=value.get("base_revision"),
            previous_hash=value.get("previous_hash"),
            occurred_at=value.get("occurred_at"),
        )
