from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Any, Iterable, Mapping

from .canonical import state_hash
from .errors import DSRValidationError
from .model import SpectrumAxis, TypedRelation, SemanticState, _text

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _weight(value: Any) -> float:
    if isinstance(value, bool):
        raise DSRValidationError("PROPOSAL_SOURCE_WEIGHT_OUT_OF_RANGE")
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise DSRValidationError("PROPOSAL_SOURCE_WEIGHT_OUT_OF_RANGE") from exc
    if not math.isfinite(out) or not (0.0 < out <= 1.0):
        raise DSRValidationError("PROPOSAL_SOURCE_WEIGHT_OUT_OF_RANGE")
    return out


def _threshold(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise DSRValidationError(f"{name}_OUT_OF_RANGE")
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise DSRValidationError(f"{name}_OUT_OF_RANGE") from exc
    if not math.isfinite(out) or not (0.0 <= out <= 1.0):
        raise DSRValidationError(f"{name}_OUT_OF_RANGE")
    return out


@dataclass(frozen=True, slots=True)
class SemanticProposal:
    proposal_id: str
    source_id: str
    identity: str
    base_revision: int
    base_hash: str
    source_weight: float = 1.0
    axes: tuple[SpectrumAxis, ...] = ()
    relations: tuple[TypedRelation, ...] = ()
    negative_relations: tuple[TypedRelation, ...] = ()
    produced_at: str | None = None

    SCHEMA = "isql.dsr-proposal/v0.3"
    LEGACY_SCHEMAS = {"isql.dsr-proposal/v0.2"}

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_id", _text(self.proposal_id, "PROPOSAL_ID_REQUIRED"))
        object.__setattr__(self, "source_id", _text(self.source_id, "PROPOSAL_SOURCE_ID_REQUIRED"))
        object.__setattr__(self, "identity", _text(self.identity, "PROPOSAL_IDENTITY_REQUIRED"))
        if not isinstance(self.base_revision, int) or isinstance(self.base_revision, bool) or self.base_revision < 0:
            raise DSRValidationError("PROPOSAL_BASE_REVISION_INVALID")
        if not isinstance(self.base_hash, str) or not _HASH_RE.fullmatch(self.base_hash):
            raise DSRValidationError("PROPOSAL_BASE_HASH_INVALID")
        object.__setattr__(self, "source_weight", _weight(self.source_weight))
        if not isinstance(self.axes, tuple) or not all(isinstance(x, SpectrumAxis) for x in self.axes):
            raise DSRValidationError("PROPOSAL_AXES_MUST_BE_AXIS_TUPLE")
        axis_keys = [x.key for x in self.axes]
        if len(set(axis_keys)) != len(axis_keys):
            raise DSRValidationError("PROPOSAL_DUPLICATE_AXIS_KEY")
        object.__setattr__(self, "axes", tuple(sorted(self.axes, key=lambda x: x.key)))
        if not isinstance(self.relations, tuple) or not all(isinstance(x, TypedRelation) for x in self.relations):
            raise DSRValidationError("PROPOSAL_RELATIONS_MUST_BE_RELATION_TUPLE")
        rel_keys = [x.key for x in self.relations]
        if len(set(rel_keys)) != len(rel_keys):
            raise DSRValidationError("PROPOSAL_DUPLICATE_RELATION")
        object.__setattr__(self, "relations", tuple(sorted(self.relations, key=lambda x: x.key)))
        if not isinstance(self.negative_relations, tuple) or not all(isinstance(x, TypedRelation) for x in self.negative_relations):
            raise DSRValidationError("PROPOSAL_NEGATIVE_RELATIONS_MUST_BE_RELATION_TUPLE")
        neg_keys = [x.key for x in self.negative_relations]
        if len(set(neg_keys)) != len(neg_keys):
            raise DSRValidationError("PROPOSAL_DUPLICATE_NEGATIVE_RELATION")
        if set(rel_keys) & set(neg_keys):
            raise DSRValidationError("PROPOSAL_RELATION_POLARITY_CONTRADICTION")
        object.__setattr__(self, "negative_relations", tuple(sorted(self.negative_relations, key=lambda x: x.key)))
        if self.produced_at is not None:
            object.__setattr__(self, "produced_at", _text(self.produced_at, "PROPOSAL_PRODUCED_AT_INVALID"))

    @classmethod
    def for_state(
        cls,
        state: SemanticState,
        *,
        proposal_id: str,
        source_id: str,
        source_weight: float = 1.0,
        axes: tuple[SpectrumAxis, ...] = (),
        relations: tuple[TypedRelation, ...] = (),
        negative_relations: tuple[TypedRelation, ...] = (),
        produced_at: str | None = None,
    ) -> "SemanticProposal":
        return cls(
            proposal_id=proposal_id,
            source_id=source_id,
            identity=state.identity,
            base_revision=state.revision,
            base_hash=state_hash(state),
            source_weight=source_weight,
            axes=axes,
            relations=relations,
            negative_relations=negative_relations,
            produced_at=produced_at,
        )

    def to_dict(self) -> dict[str, object]:
        out: dict[str, object] = {
            "schema": self.SCHEMA,
            "proposal_id": self.proposal_id,
            "source_id": self.source_id,
            "identity": self.identity,
            "base_revision": self.base_revision,
            "base_hash": self.base_hash,
            "source_weight": self.source_weight,
            "axes": [x.to_dict() for x in self.axes],
            "relations": [x.to_dict() for x in self.relations],
            "negative_relations": [x.to_dict() for x in self.negative_relations],
        }
        if self.produced_at is not None:
            out["produced_at"] = self.produced_at
        return out

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SemanticProposal":
        if not isinstance(value, Mapping):
            raise DSRValidationError("PROPOSAL_MUST_BE_OBJECT")
        if value.get("schema") not in (None, cls.SCHEMA, *cls.LEGACY_SCHEMAS):
            raise DSRValidationError("INVALID_PROPOSAL_SCHEMA")
        axes = value.get("axes", [])
        relations = value.get("relations", [])
        negative_relations = value.get("negative_relations", [])
        if not isinstance(axes, list) or not isinstance(relations, list) or not isinstance(negative_relations, list):
            raise DSRValidationError("PROPOSAL_COLLECTIONS_MUST_BE_LISTS")
        return cls(
            proposal_id=value.get("proposal_id"),
            source_id=value.get("source_id"),
            identity=value.get("identity"),
            base_revision=value.get("base_revision"),
            base_hash=value.get("base_hash"),
            source_weight=value.get("source_weight", 1.0),
            axes=tuple(SpectrumAxis.from_dict(x) for x in axes),
            relations=tuple(TypedRelation.from_dict(x) for x in relations),
            negative_relations=tuple(TypedRelation.from_dict(x) for x in negative_relations),
            produced_at=value.get("produced_at"),
        )


@dataclass(frozen=True, slots=True)
class FusionConflict:
    kind: str
    key: str
    reason: str
    candidates: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "key": self.key,
            "reason": self.reason,
            "candidates": list(self.candidates),
        }


@dataclass(frozen=True, slots=True)
class FusionDecision:
    identity: str
    base_revision: int
    base_hash: str
    proposal_ids: tuple[str, ...]
    axes: tuple[SpectrumAxis, ...]
    relations: tuple[TypedRelation, ...]
    negative_relations: tuple[TypedRelation, ...]
    conflicts: tuple[FusionConflict, ...]
    axis_threshold: float
    relation_threshold: float
    algorithm: str = "weighted-agreement/v0.2"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "isql.dsr-fusion-decision/v0.2",
            "algorithm": self.algorithm,
            "identity": self.identity,
            "base_revision": self.base_revision,
            "base_hash": self.base_hash,
            "proposal_ids": list(self.proposal_ids),
            "axis_threshold": self.axis_threshold,
            "relation_threshold": self.relation_threshold,
            "axes": [x.to_dict() for x in self.axes],
            "relations": [x.to_dict() for x in self.relations],
            "negative_relations": [x.to_dict() for x in self.negative_relations],
            "conflicts": [x.to_dict() for x in self.conflicts],
        }


def _axis_variant_key(axis: SpectrumAxis) -> str:
    payload = {"domain": axis.domain, "value": axis.value.to_dict()}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fuse_proposals(
    base_state: SemanticState,
    proposals: Iterable[SemanticProposal],
    *,
    axis_threshold: float = 0.5,
    relation_threshold: float = 0.5,
) -> FusionDecision:
    axis_threshold = _threshold(axis_threshold, "FUSION_AXIS_THRESHOLD")
    relation_threshold = _threshold(relation_threshold, "FUSION_RELATION_THRESHOLD")
    ordered = tuple(sorted(tuple(proposals), key=lambda p: (p.proposal_id, p.source_id)))
    if not ordered:
        raise DSRValidationError("FUSION_PROPOSALS_REQUIRED")
    expected_hash = state_hash(base_state)
    seen_ids: set[str] = set()
    for proposal in ordered:
        if not isinstance(proposal, SemanticProposal):
            raise DSRValidationError("FUSION_PROPOSAL_INVALID")
        if proposal.proposal_id in seen_ids:
            raise DSRValidationError("FUSION_DUPLICATE_PROPOSAL_ID")
        seen_ids.add(proposal.proposal_id)
        if proposal.identity != base_state.identity:
            raise DSRValidationError("PROPOSAL_IDENTITY_MISMATCH")
        if proposal.base_revision != base_state.revision:
            raise DSRValidationError("PROPOSAL_BASE_REVISION_MISMATCH")
        if proposal.base_hash != expected_hash:
            raise DSRValidationError("PROPOSAL_BASE_HASH_MISMATCH")

    total_weight = sum(p.source_weight for p in ordered)
    base_axes = {axis.key: axis for axis in base_state.axes}
    axis_groups: dict[str, list[tuple[SemanticProposal, SpectrumAxis]]] = {}
    for proposal in ordered:
        for axis in proposal.axes:
            axis_groups.setdefault(axis.key, []).append((proposal, axis))

    conflicts: list[FusionConflict] = []
    fused_axes = dict(base_axes)
    for key in sorted(axis_groups):
        variants: dict[str, list[tuple[SemanticProposal, SpectrumAxis]]] = {}
        for proposal, axis in axis_groups[key]:
            variants.setdefault(_axis_variant_key(axis), []).append((proposal, axis))
        scored: list[tuple[float, str, list[tuple[SemanticProposal, SpectrumAxis]]]] = []
        candidate_rows: list[dict[str, object]] = []
        for variant_key in sorted(variants):
            items = variants[variant_key]
            support = sum(p.source_weight * (1.0 - axis.uncertainty) for p, axis in items)
            scored.append((support, variant_key, items))
            candidate_rows.append({
                "variant": json.loads(variant_key),
                "effective_support": support,
                "support_ratio": support / total_weight,
                "sources": [p.source_id for p, _ in items],
            })
        scored.sort(key=lambda row: (-row[0], row[1]))
        best_support, _, winners = scored[0]
        tied = len(scored) > 1 and math.isclose(best_support, scored[1][0], rel_tol=0.0, abs_tol=1e-15)
        support_ratio = best_support / total_weight
        if tied or support_ratio < axis_threshold:
            conflicts.append(FusionConflict(
                kind="axis",
                key=key,
                reason="TIED_SUPPORT" if tied else "INSUFFICIENT_SUPPORT",
                candidates=tuple(candidate_rows),
            ))
            continue
        exemplar = winners[0][1]
        fused_axes[key] = SpectrumAxis(
            key=key,
            domain=exemplar.domain,
            value=exemplar.value,
            uncertainty=max(0.0, min(1.0, 1.0 - support_ratio)),
            resolution=max(axis.resolution for _, axis in winners),
        )

    positive_support: dict[tuple[str, str, str], float] = {}
    negative_support: dict[tuple[str, str, str], float] = {}
    relation_objects: dict[tuple[str, str, str], TypedRelation] = {}
    for proposal in ordered:
        for relation in proposal.relations:
            positive_support[relation.key] = positive_support.get(relation.key, 0.0) + proposal.source_weight
            relation_objects[relation.key] = relation
        for relation in proposal.negative_relations:
            negative_support[relation.key] = negative_support.get(relation.key, 0.0) + proposal.source_weight
            relation_objects[relation.key] = relation
    fused_relations = {relation.key: relation for relation in base_state.relations}
    fused_negative = {relation.key: relation for relation in base_state.negative_relations}
    for key in sorted(set(positive_support) | set(negative_support)):
        pos_ratio = positive_support.get(key, 0.0) / total_weight
        neg_ratio = negative_support.get(key, 0.0) / total_weight
        pos_ok = pos_ratio >= relation_threshold
        neg_ok = neg_ratio >= relation_threshold
        if pos_ok and neg_ok:
            conflicts.append(FusionConflict(
                kind="relation",
                key="|".join(key),
                reason="POLARITY_CONFLICT",
                candidates=(
                    {"polarity": 1, "support_ratio": pos_ratio},
                    {"polarity": -1, "support_ratio": neg_ratio},
                ),
            ))
            continue
        if pos_ok:
            fused_relations[key] = relation_objects[key]
            fused_negative.pop(key, None)
        elif neg_ok:
            fused_negative[key] = relation_objects[key]
            fused_relations.pop(key, None)

    return FusionDecision(
        identity=base_state.identity,
        base_revision=base_state.revision,
        base_hash=expected_hash,
        proposal_ids=tuple(p.proposal_id for p in ordered),
        axes=tuple(sorted(fused_axes.values(), key=lambda x: x.key)),
        relations=tuple(sorted(fused_relations.values(), key=lambda x: x.key)),
        negative_relations=tuple(sorted(fused_negative.values(), key=lambda x: x.key)),
        conflicts=tuple(conflicts),
        axis_threshold=axis_threshold,
        relation_threshold=relation_threshold,
    )
