from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from .errors import DSRExecutionError, DSRValidationError
from .machine import NativeAxis, NativeProjection, NativeRelation, NativeSemanticState, registered_state_hash
from .native import decode_uvarint, encode_uvarint, encode_value
from .registry import NativeSymbolRegistry, SymbolNamespace
from .stream import NativeEventStream, decode_event_stream, encode_event_stream, replay_native_stream

BRANCH_MAGIC = bytes((0xD5, 0x51, 0xB7, 0x05))
BRANCH_FORMAT_VERSION = 5

CONFLICT_AXIS = 1
CONFLICT_RELATION_POLARITY = 2
CONFLICT_CONTEXT = 3
CONFLICT_PROJECTION = 4


def _hash_hex(value: str, error: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise DSRValidationError(error)
    return value


def _write_blob(out: bytearray, raw: bytes) -> None:
    out += encode_uvarint(len(raw))
    out += raw


def _read_blob(data: bytes, offset: int) -> tuple[bytes, int]:
    size, offset = decode_uvarint(data, offset)
    end = offset + size
    if end > len(data):
        raise DSRValidationError("BRANCH_BLOB_TRUNCATED")
    return data[offset:end], end


@dataclass(frozen=True, slots=True)
class NativeBranch:
    branch_ref: int
    base_revision: int
    base_hash: str
    stream: NativeEventStream

    def __post_init__(self) -> None:
        if not isinstance(self.branch_ref, int) or isinstance(self.branch_ref, bool) or self.branch_ref <= 0:
            raise DSRValidationError("BRANCH_REF_INVALID")
        if not isinstance(self.base_revision, int) or isinstance(self.base_revision, bool) or self.base_revision < 0:
            raise DSRValidationError("BRANCH_BASE_REVISION_INVALID")
        object.__setattr__(self, "base_hash", _hash_hex(self.base_hash, "BRANCH_BASE_HASH_INVALID"))
        if not isinstance(self.stream, NativeEventStream):
            raise DSRValidationError("BRANCH_STREAM_INVALID")
        if self.stream.genesis_hash != self.base_hash:
            raise DSRValidationError("BRANCH_STREAM_BASE_HASH_MISMATCH")


@dataclass(frozen=True, slots=True)
class NativeMergeConflict:
    kind: int
    key: tuple[int, ...]
    branch_refs: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.kind not in {CONFLICT_AXIS, CONFLICT_RELATION_POLARITY, CONFLICT_CONTEXT, CONFLICT_PROJECTION}:
            raise DSRValidationError("BRANCH_CONFLICT_KIND_INVALID")
        if not isinstance(self.key, tuple) or not self.key or not all(isinstance(x, int) and x >= 0 for x in self.key):
            raise DSRValidationError("BRANCH_CONFLICT_KEY_INVALID")
        if not isinstance(self.branch_refs, tuple) or not self.branch_refs:
            raise DSRValidationError("BRANCH_CONFLICT_REFS_INVALID")
        object.__setattr__(self, "branch_refs", tuple(sorted(self.branch_refs)))


@dataclass(frozen=True, slots=True)
class NativeMergeResult:
    state: NativeSemanticState
    conflicts: tuple[NativeMergeConflict, ...]
    branch_refs: tuple[int, ...]


def encode_branch(branch: NativeBranch) -> bytes:
    if not isinstance(branch, NativeBranch):
        raise TypeError("encode_branch requires NativeBranch")
    out = bytearray(BRANCH_MAGIC)
    out += encode_uvarint(BRANCH_FORMAT_VERSION)
    out += encode_uvarint(branch.branch_ref)
    out += encode_uvarint(branch.base_revision)
    out += bytes.fromhex(branch.base_hash)
    _write_blob(out, encode_event_stream(branch.stream))
    return bytes(out)


def decode_branch(data: bytes, registry: NativeSymbolRegistry) -> NativeBranch:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise DSRValidationError("BRANCH_BYTES_REQUIRED")
    data = bytes(data)
    if not data.startswith(BRANCH_MAGIC):
        raise DSRValidationError("BRANCH_MAGIC_INVALID")
    offset = len(BRANCH_MAGIC)
    version, offset = decode_uvarint(data, offset)
    if version != BRANCH_FORMAT_VERSION:
        raise DSRValidationError("BRANCH_VERSION_UNSUPPORTED")
    branch_ref, offset = decode_uvarint(data, offset)
    registry.resolve(branch_ref, SymbolNamespace.BRANCH_ID)
    base_revision, offset = decode_uvarint(data, offset)
    end = offset + 32
    if end > len(data):
        raise DSRValidationError("BRANCH_BASE_HASH_TRUNCATED")
    base_hash = data[offset:end].hex(); offset = end
    blob, offset = _read_blob(data, offset)
    stream = decode_event_stream(blob, registry)
    if offset != len(data):
        raise DSRValidationError("BRANCH_TRAILING_DATA")
    branch = NativeBranch(branch_ref, base_revision, base_hash, stream)
    if encode_branch(branch) != data:
        raise DSRValidationError("BRANCH_NONCANONICAL")
    return branch


def _map_axes(state: NativeSemanticState) -> dict[int, NativeAxis]:
    return {x.key_ref: x for x in state.axes}


def _relation_status(state: NativeSemanticState) -> dict[tuple[int, int, int], int]:
    out = {x.key: 1 for x in state.relations}
    out.update({x.key: -1 for x in state.negative_relations})
    return out


def _changed_values(base_value, finals: list[tuple[int, object]]) -> list[tuple[int, object]]:
    return [(branch_ref, value) for branch_ref, value in finals if value != base_value]


def _context_map(state: NativeSemanticState) -> dict[int, object]:
    return dict(state.context)


def _projection_map(state: NativeSemanticState) -> dict[int, NativeProjection]:
    return {x.projection_ref: x for x in state.projections}


def _fingerprint(value: object) -> bytes:
    if isinstance(value, NativeProjection):
        return encode_uvarint(value.media_type_ref) + encode_value(value.payload)
    return encode_value(value)


def merge_native_branches(
    base: NativeSemanticState,
    branches: Iterable[NativeBranch],
    registry: NativeSymbolRegistry,
) -> NativeMergeResult:
    if not isinstance(base, NativeSemanticState):
        raise TypeError("base must be NativeSemanticState")
    ordered = tuple(sorted(tuple(branches), key=lambda b: b.branch_ref))
    if not ordered:
        raise DSRExecutionError("BRANCHES_REQUIRED")
    if len({b.branch_ref for b in ordered}) != len(ordered):
        raise DSRExecutionError("DUPLICATE_BRANCH_REF")
    base_hash = registered_state_hash(base)
    finals: list[tuple[NativeBranch, NativeSemanticState]] = []
    for branch in ordered:
        registry.resolve(branch.branch_ref, SymbolNamespace.BRANCH_ID)
        if branch.base_revision != base.revision or branch.base_hash != base_hash:
            raise DSRExecutionError("BRANCH_BASE_MISMATCH")
        finals.append((branch, replay_native_stream(base, branch.stream, registry)))

    conflicts: list[NativeMergeConflict] = []
    base_axes = _map_axes(base)
    result_axes = dict(base_axes)
    all_axis_keys = set(base_axes)
    for _, state in finals:
        all_axis_keys.update(_map_axes(state))
    for key in sorted(all_axis_keys):
        base_value = base_axes.get(key)
        rows = [(branch.branch_ref, _map_axes(state).get(key)) for branch, state in finals]
        changed = _changed_values(base_value, rows)
        distinct = {value for _, value in changed}
        if len(distinct) > 1:
            conflicts.append(NativeMergeConflict(CONFLICT_AXIS, (key,), tuple(ref for ref, _ in changed)))
            continue
        if changed:
            value = changed[0][1]
            if value is None:
                result_axes.pop(key, None)
            else:
                result_axes[key] = value

    base_context = _context_map(base)
    result_context = dict(base_context)
    all_context_keys = set(base_context)
    final_contexts = []
    for branch, state in finals:
        mapping = _context_map(state)
        final_contexts.append((branch, mapping))
        all_context_keys.update(mapping)
    missing = object()
    for key in sorted(all_context_keys):
        base_value = base_context.get(key, missing)
        rows = [(branch.branch_ref, mapping.get(key, missing)) for branch, mapping in final_contexts]
        changed = [(ref, value) for ref, value in rows if value != base_value]
        fingerprints = {_fingerprint(value) if value is not missing else b"\x00" for _, value in changed}
        if len(fingerprints) > 1:
            conflicts.append(NativeMergeConflict(CONFLICT_CONTEXT, (key,), tuple(ref for ref, _ in changed)))
            continue
        if changed:
            value = changed[0][1]
            if value is missing:
                result_context.pop(key, None)
            else:
                result_context[key] = value

    base_proj = _projection_map(base)
    result_proj = dict(base_proj)
    all_proj_keys = set(base_proj)
    final_projs = []
    for branch, state in finals:
        mapping = _projection_map(state)
        final_projs.append((branch, mapping))
        all_proj_keys.update(mapping)
    for key in sorted(all_proj_keys):
        base_value = base_proj.get(key, missing)
        rows = [(branch.branch_ref, mapping.get(key, missing)) for branch, mapping in final_projs]
        changed = [(ref, value) for ref, value in rows if value != base_value]
        fingerprints = {_fingerprint(value) if value is not missing else b"\x00" for _, value in changed}
        if len(fingerprints) > 1:
            conflicts.append(NativeMergeConflict(CONFLICT_PROJECTION, (key,), tuple(ref for ref, _ in changed)))
            continue
        if changed:
            value = changed[0][1]
            if value is missing:
                result_proj.pop(key, None)
            else:
                result_proj[key] = value

    base_status = _relation_status(base)
    result_status = dict(base_status)
    all_rel_keys = set(base_status)
    final_statuses = []
    for branch, state in finals:
        status = _relation_status(state)
        final_statuses.append((branch, status))
        all_rel_keys.update(status)
    for key in sorted(all_rel_keys):
        base_value = base_status.get(key, 0)
        rows = [(branch.branch_ref, status.get(key, 0)) for branch, status in final_statuses]
        changed = _changed_values(base_value, rows)
        distinct = {value for _, value in changed}
        if len(distinct) > 1:
            conflicts.append(NativeMergeConflict(CONFLICT_RELATION_POLARITY, key, tuple(ref for ref, _ in changed)))
            continue
        if changed:
            result_status[key] = changed[0][1]

    positives = tuple(NativeRelation(*key) for key, status in sorted(result_status.items()) if status == 1)
    negatives = tuple(NativeRelation(*key) for key, status in sorted(result_status.items()) if status == -1)
    changed_relations = positives != base.relations or negatives != base.negative_relations
    max_revision = max(state.revision for _, state in finals)
    merged = replace(
        base,
        revision=max_revision + 1,
        context=tuple(sorted(result_context.items(), key=lambda x: x[0])),
        axes=tuple(sorted(result_axes.values(), key=lambda a: a.key_ref)),
        relations=positives,
        negative_relations=negatives,
        projections=tuple(sorted(result_proj.values(), key=lambda x: x.projection_ref)),
        topology=() if changed_relations else base.topology,
    )
    return NativeMergeResult(merged, tuple(conflicts), tuple(b.branch_ref for b in ordered))
