from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Mapping, Any

from .canonical import state_hash
from .errors import DSRExecutionError
from .events import TransitionEvent
from .model import SemanticProjection, SemanticState, SpectrumAxis, TypedRelation


@dataclass(frozen=True, slots=True)
class AppliedTransition:
    state: SemanticState
    previous_hash: str
    next_hash: str


def _require_payload_object(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise DSRExecutionError(f"EVENT_{key.upper()}_REQUIRED")
    return value


def _replace_axis(state: SemanticState, axis: SpectrumAxis) -> tuple[SpectrumAxis, ...]:
    return tuple(x for x in state.axes if x.key != axis.key) + (axis,)


def _remove_axis(state: SemanticState, key: str) -> tuple[SpectrumAxis, ...]:
    out = tuple(x for x in state.axes if x.key != key)
    if len(out) == len(state.axes):
        raise DSRExecutionError("AXIS_NOT_FOUND")
    return out


def _replace_relation(state: SemanticState, relation: TypedRelation) -> tuple[TypedRelation, ...]:
    return tuple(x for x in state.relations if x.key != relation.key) + (relation,)


def _remove_relation(state: SemanticState, relation: TypedRelation) -> tuple[TypedRelation, ...]:
    out = tuple(x for x in state.relations if x.key != relation.key)
    if len(out) == len(state.relations):
        raise DSRExecutionError("RELATION_NOT_FOUND")
    return out


def _replace_projection(state: SemanticState, projection: SemanticProjection) -> tuple[SemanticProjection, ...]:
    return tuple(x for x in state.projections if x.projection_id != projection.projection_id) + (projection,)


def _remove_projection(state: SemanticState, projection_id: str) -> tuple[SemanticProjection, ...]:
    out = tuple(x for x in state.projections if x.projection_id != projection_id)
    if len(out) == len(state.projections):
        raise DSRExecutionError("PROJECTION_NOT_FOUND")
    return out


def apply_event(state: SemanticState, event: TransitionEvent) -> AppliedTransition:
    if event.base_revision != state.revision:
        raise DSRExecutionError("EVENT_BASE_REVISION_MISMATCH")
    previous_hash = state_hash(state)
    if event.previous_hash != previous_hash:
        raise DSRExecutionError("EVENT_PREVIOUS_HASH_MISMATCH")

    changes: dict[str, Any] = {}
    payload = event.payload

    if event.operation == "set_context":
        context = payload.get("context")
        if not isinstance(context, Mapping):
            raise DSRExecutionError("EVENT_CONTEXT_REQUIRED")
        changes["context"] = dict(context)
    elif event.operation == "upsert_axis":
        axis = SpectrumAxis.from_dict(_require_payload_object(payload, "axis"))
        changes["axes"] = _replace_axis(state, axis)
    elif event.operation == "remove_axis":
        key = payload.get("key")
        if not isinstance(key, str) or not key.strip():
            raise DSRExecutionError("EVENT_AXIS_KEY_REQUIRED")
        changes["axes"] = _remove_axis(state, key.strip())
    elif event.operation == "upsert_relation":
        relation = TypedRelation.from_dict(_require_payload_object(payload, "relation"))
        changes["relations"] = _replace_relation(state, relation)
    elif event.operation == "remove_relation":
        relation = TypedRelation.from_dict(payload)
        changes["relations"] = _remove_relation(state, relation)
    elif event.operation == "upsert_projection":
        projection = SemanticProjection.from_dict(_require_payload_object(payload, "projection"))
        changes["projections"] = _replace_projection(state, projection)
    elif event.operation == "remove_projection":
        projection_id = payload.get("projection_id")
        if not isinstance(projection_id, str) or not projection_id.strip():
            raise DSRExecutionError("EVENT_PROJECTION_ID_REQUIRED")
        changes["projections"] = _remove_projection(state, projection_id.strip())
    else:
        raise DSRExecutionError("UNKNOWN_EVENT_OPERATION")

    history_record = {
        "event": event.to_dict(),
        "previous_hash": previous_hash,
    }
    next_state = replace(
        state,
        revision=state.revision + 1,
        history=state.history + (history_record,),
        **changes,
    )
    next_hash = state_hash(next_state)
    return AppliedTransition(state=next_state, previous_hash=previous_hash, next_hash=next_hash)


def replay(genesis: SemanticState, events: Iterable[TransitionEvent]) -> SemanticState:
    state = genesis
    for event in events:
        state = apply_event(state, event).state
    return state
