from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .canonical import state_hash
from .events import TransitionEvent
from .model import SemanticState
from .runtime import apply_event


@dataclass(frozen=True, slots=True)
class ValidationReport:
    valid: bool
    errors: tuple[str, ...]
    checked_history_records: int
    state_hash: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "isql.dsr-validation/v0.1",
            "valid": self.valid,
            "errors": list(self.errors),
            "checked_history_records": self.checked_history_records,
            "state_hash": self.state_hash,
        }


def validate_state(state: SemanticState, *, genesis: SemanticState | None = None) -> ValidationReport:
    errors: list[str] = []
    checked = 0

    if genesis is not None:
        if genesis.identity != state.identity:
            errors.append("GENESIS_IDENTITY_MISMATCH")
        if genesis.revision + len(state.history) != state.revision:
            errors.append("REVISION_HISTORY_LENGTH_MISMATCH")

        current = genesis
        for idx, record in enumerate(state.history):
            checked += 1
            if not isinstance(record, Mapping):
                errors.append(f"HISTORY_RECORD_INVALID_AT_{idx}")
                break
            expected_previous = state_hash(current)
            if record.get("previous_hash") != expected_previous:
                errors.append(f"HISTORY_PREVIOUS_HASH_MISMATCH_AT_{idx}")
            event_raw = record.get("event")
            if not isinstance(event_raw, Mapping):
                errors.append(f"HISTORY_EVENT_MISSING_AT_{idx}")
                break
            try:
                event = TransitionEvent.from_dict(event_raw)
            except Exception as exc:
                errors.append(f"HISTORY_EVENT_INVALID_AT_{idx}:{type(exc).__name__}")
                break
            if event.previous_hash != expected_previous:
                errors.append(f"EVENT_PREVIOUS_HASH_MISMATCH_AT_{idx}")
            if event.base_revision != current.revision:
                errors.append(f"EVENT_BASE_REVISION_MISMATCH_AT_{idx}")
            try:
                current = apply_event(current, event).state
            except Exception as exc:
                errors.append(f"HISTORY_REPLAY_FAILED_AT_{idx}:{type(exc).__name__}")
                break

        if current.to_dict() != state.to_dict():
            errors.append("REPLAYED_STATE_MISMATCH")

    return ValidationReport(
        valid=not errors,
        errors=tuple(errors),
        checked_history_records=checked,
        state_hash=state_hash(state),
    )
