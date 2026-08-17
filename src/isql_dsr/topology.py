from __future__ import annotations

import hashlib
import json
from typing import Iterable

from .errors import DSRValidationError
from .model import SemanticState, TopologyDescriptor

_SUPPORTED_METHODS = {"graph.components", "graph.cycle_rank"}


def topology_basis_hash(state: SemanticState) -> str:
    payload = {
        "schema": "isql.dsr-topology-basis/v0.2",
        "relations": [relation.to_dict() for relation in state.relations],
    }
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


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
            parameters={"graph_mode": "weak-undirected-projection"},
        )
        for method in requested
    )
