from __future__ import annotations

from dataclasses import dataclass

from .errors import DSRValidationError
from .model import SemanticState, TypedRelation


@dataclass(frozen=True, slots=True)
class StateDiff:
    identity: str
    left_revision: int
    right_revision: int
    changed_context_keys: tuple[str, ...]
    added_axes: tuple[str, ...]
    removed_axes: tuple[str, ...]
    changed_axes: tuple[str, ...]
    added_relations: tuple[TypedRelation, ...]
    removed_relations: tuple[TypedRelation, ...]
    added_projections: tuple[str, ...]
    removed_projections: tuple[str, ...]
    changed_projections: tuple[str, ...]

    @property
    def empty(self) -> bool:
        return not any(
            (
                self.changed_context_keys,
                self.added_axes,
                self.removed_axes,
                self.changed_axes,
                self.added_relations,
                self.removed_relations,
                self.added_projections,
                self.removed_projections,
                self.changed_projections,
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "isql.dsr-diff/v0.1",
            "identity": self.identity,
            "left_revision": self.left_revision,
            "right_revision": self.right_revision,
            "changed_context_keys": list(self.changed_context_keys),
            "added_axes": list(self.added_axes),
            "removed_axes": list(self.removed_axes),
            "changed_axes": list(self.changed_axes),
            "added_relations": [x.to_dict() for x in self.added_relations],
            "removed_relations": [x.to_dict() for x in self.removed_relations],
            "added_projections": list(self.added_projections),
            "removed_projections": list(self.removed_projections),
            "changed_projections": list(self.changed_projections),
            "empty": self.empty,
        }


def diff_states(left: SemanticState, right: SemanticState) -> StateDiff:
    if left.identity != right.identity:
        raise DSRValidationError("DIFF_IDENTITY_MISMATCH")

    context_keys = sorted(set(left.context) | set(right.context))
    changed_context = tuple(k for k in context_keys if left.context.get(k) != right.context.get(k))

    left_axes = {x.key: x for x in left.axes}
    right_axes = {x.key: x for x in right.axes}
    added_axes = tuple(sorted(set(right_axes) - set(left_axes)))
    removed_axes = tuple(sorted(set(left_axes) - set(right_axes)))
    changed_axes = tuple(sorted(k for k in set(left_axes) & set(right_axes) if left_axes[k] != right_axes[k]))

    left_rel = {x.key: x for x in left.relations}
    right_rel = {x.key: x for x in right.relations}
    added_relations = tuple(right_rel[k] for k in sorted(set(right_rel) - set(left_rel)))
    removed_relations = tuple(left_rel[k] for k in sorted(set(left_rel) - set(right_rel)))

    left_proj = {x.projection_id: x for x in left.projections}
    right_proj = {x.projection_id: x for x in right.projections}
    added_projections = tuple(sorted(set(right_proj) - set(left_proj)))
    removed_projections = tuple(sorted(set(left_proj) - set(right_proj)))
    changed_projections = tuple(
        sorted(k for k in set(left_proj) & set(right_proj) if left_proj[k] != right_proj[k])
    )

    return StateDiff(
        identity=left.identity,
        left_revision=left.revision,
        right_revision=right.revision,
        changed_context_keys=changed_context,
        added_axes=added_axes,
        removed_axes=removed_axes,
        changed_axes=changed_axes,
        added_relations=added_relations,
        removed_relations=removed_relations,
        added_projections=added_projections,
        removed_projections=removed_projections,
        changed_projections=changed_projections,
    )
