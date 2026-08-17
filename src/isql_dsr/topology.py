from __future__ import annotations

import hashlib
import json
from typing import Iterable

from .errors import DSRValidationError
from .model import SemanticState, TopologyDescriptor

_SUPPORTED_METHODS = {"graph.components", "graph.cycle_rank"}


def _put_blob(out: bytearray, raw: bytes) -> None:
    out += len(raw).to_bytes(8, "big")
    out += raw


def topology_basis_hash(state: SemanticState) -> str:
    """Relation-basis hash independent of JSON rendering.

    v0.5 hashes the ordered UTF-8 semantic symbols with explicit length
    framing. Native execution can reproduce the same hash from registry bytes
    without materializing a human-readable SemanticState.
    """
    out = bytearray(b"ISQL-TOPOLOGY-BASIS\x05")
    for relation in state.relations:
        _put_blob(out, relation.subject.encode("utf-8"))
        _put_blob(out, relation.predicate.encode("utf-8"))
        _put_blob(out, relation.object.encode("utf-8"))
    return hashlib.sha256(bytes(out)).hexdigest()


def _graph_stats(state: SemanticState) -> tuple[int, int, int]:
    nodes: set[str] = set()
    undirected_edges: set[tuple[str, str]] = set()
    adjacency: dict[str, set[str]] = {}
    for relation in state.relations:
        u, v = relation.subject, relation.object
        nodes.update((u, v))
        edge = tuple(sorted((u, v)))
        undirected_edges.add(edge)
        adjacency.setdefault(u, set()).add(v)
        adjacency.setdefault(v, set()).add(u)
    if not nodes:
        return 0, 0, 0
    components = 0
    remaining = set(nodes)
    while remaining:
        components += 1
        stack = [remaining.pop()]
        while stack:
            node = stack.pop()
            for neighbor in adjacency.get(node, ()):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
    edge_count = len(undirected_edges)
    cycle_rank = edge_count - len(nodes) + components
    return len(nodes), components, max(cycle_rank, 0)


def compute_topology_descriptors(
    state: SemanticState,
    *,
    methods: Iterable[str] = ("graph.components", "graph.cycle_rank"),
) -> tuple[TopologyDescriptor, ...]:
    requested = tuple(sorted(set(methods)))
    unknown = [method for method in requested if method not in _SUPPORTED_METHODS]
    if unknown:
        raise DSRValidationError(f"UNKNOWN_TOPOLOGY_METHOD:{unknown[0]}")
    _, components, cycle_rank = _graph_stats(state)
    values = {
        "graph.components": components,
        "graph.cycle_rank": cycle_rank,
    }
    basis = topology_basis_hash(state)
    return tuple(
        TopologyDescriptor(
            descriptor_id=method,
            method=method,
            basis_hash=basis,
            value=values[method],
            confidence=1.0,
            parameters={},
        )
        for method in requested
    )
