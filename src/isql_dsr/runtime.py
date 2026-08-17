from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Mapping, Any

from .canonical import state_hash
from .errors import DSRExecutionError, DSRValidationError
from .events import TransitionEvent
from .topology import compute_topology_descriptors, topology_basis_hash
from .fusion import SemanticProposal, fuse_proposals
from .model import SemanticProjection, SemanticState, SpectrumAxis, TopologyDescriptor, TypedRelation


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


def _replace_topology_descriptor(state: SemanticState, descriptor: TopologyDescriptor) -> tuple[TopologyDescriptor, ...]:
    return tuple(x for x in state.topology if x.descriptor_id != descriptor.descriptor_id) + (descriptor,)


def _remove_topology_descriptor(state: SemanticState, descriptor_id: str) -> tuple[TopologyDescriptor, ...]:
    out = tuple(x for x in state.topology if x.descriptor_id != descriptor_id)
    if len(out) == len(state.topology):
        raise DSRExecutionError("TOPOLOGY_DESCRIPTOR_NOT_FOUND")
    return out


def apply_event(state: SemanticState, event: TransitionEvent) -> AppliedTransition:
    if event.base_revision != state.revision:
        raise DSRExecutionError("EVENT_BASE_REVISION_MISMATCH")
    previous_hash = state_hash(state)
    if event.previous_hash != previous_hash:
        raise DSRExecutionError("EVENT_PREVIOUS_HASH_MISMATCH")

    changes: dict[str, Any] = {}
    history_result: dict[str, Any] | None = None
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
        changes["topology"] = ()
    elif event.operation == "remove_relation":
        relation = TypedRelation.from_dict(payload)
        changes["relations"] = _remove_relation(state, relation)
        changes["topology"] = ()
    elif event.operation == "refresh_topology":
        methods = payload.get("methods", ["graph.components", "graph.cycle_rank"])
        if not isinstance(methods, list) or not all(isinstance(x, str) and x.strip() for x in methods):
            raise DSRExecutionError("EVENT_TOPOLOGY_METHODS_INVALID")
        try:
            changes["topology"] = compute_topology_descriptors(state, methods=tuple(x.strip() for x in methods))
        except DSRValidationError as exc:
            raise DSRExecutionError(str(exc)) from exc
    elif event.operation == "upsert_topology_descriptor":
        descriptor = TopologyDescriptor.from_dict(_require_payload_object(payload, "descriptor"))
        if descriptor.basis_hash != topology_basis_hash(state):
            raise DSRExecutionError("TOPOLOGY_BASIS_HASH_MISMATCH")
        changes["topology"] = _replace_topology_descriptor(state, descriptor)
    elif event.operation == "remove_topology_descriptor":
        descriptor_id = payload.get("descriptor_id")
        if not isinstance(descriptor_id, str) or not descriptor_id.strip():
            raise DSRExecutionError("EVENT_TOPOLOGY_DESCRIPTOR_ID_REQUIRED")
        changes["topology"] = _remove_topology_descriptor(state, descriptor_id.strip())
    elif event.operation == "fuse_proposals":
        raw_proposals = payload.get("proposals")
        if not isinstance(raw_proposals, list):
            raise DSRExecutionError("EVENT_FUSION_PROPOSALS_REQUIRED")
        try:
            proposals = tuple(SemanticProposal.from_dict(x) for x in raw_proposals)
            decision = fuse_proposals(
                state,
                proposals,
                axis_threshold=payload.get("axis_threshold", 0.5),
                relation_threshold=payload.get("relation_threshold", 0.5),
            )
        except DSRValidationError as exc:
            raise DSRExecutionError(str(exc)) from exc
        changes["axes"] = decision.axes
        changes["relations"] = decision.relations
        if decision.relations != state.relations:
            changes["topology"] = ()
        history_result = {"fusion": decision.to_dict()}
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
    if history_result is not None:
        history_record["result"] = history_result
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
