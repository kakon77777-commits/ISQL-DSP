from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .bridge import (
    to_core_bundle, to_core_sem_envelope, to_core_state_envelope,
    to_native_core_bundle, to_native_core_sem_envelope, to_native_core_state_envelope,
    to_registered_core_exec_envelope, to_registered_core_sem_envelope, to_registered_core_state_envelope,
)
from .canonical import state_hash
from .diff import diff_states
from .errors import DSRError
from .events import TransitionEvent
from .fusion import SemanticProposal
from .machine import (
    compile_registered_state, decode_registered_state, encode_registered_state,
    inspect_registered_state, registered_state_hash,
)
from .model import SemanticState
from .native import decode_state, encode_state
from .registry import (
    NativeSymbolRegistry, decode_registry, encode_registry, extend_registry_for_events,
    extend_registry_for_state, registry_hash,
)
from .runtime import apply_event, replay
from .stream import build_event_stream, decode_event_stream, encode_event_stream, replay_native_stream
from .topology import compute_topology_descriptors, topology_basis_hash
from .validation import validate_state


def _read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_state(path: str) -> SemanticState:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise ValueError("state JSON must be an object")
    return SemanticState.from_dict(raw)


def _read_events(path: str) -> list[TransitionEvent]:
    raw = _read_json(path)
    if not isinstance(raw, list):
        raise ValueError("events JSON must be an array")
    return [TransitionEvent.from_dict(x) for x in raw]


def _read_native(path: str) -> SemanticState:
    return decode_state(Path(path).read_bytes())


def _read_registry(path: str) -> NativeSymbolRegistry:
    return decode_registry(Path(path).read_bytes())


def _read_registered(path: str, registry: NativeSymbolRegistry):
    return decode_registered_state(Path(path).read_bytes(), registry)


def _read_stream(path: str, registry: NativeSymbolRegistry):
    return decode_event_stream(Path(path).read_bytes(), registry)


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="isql-dsr", description="ISQL Dynamic Spectrum Runtime v0.4 (registered AI-native state + native event stream)")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("new", help="Create a genesis inspection DSR state")
    sp.add_argument("--identity", required=True)
    sp.add_argument("--context-json", default="{}")

    sp = sub.add_parser("hash", help="Compute legacy v0.3 native SHA-256 state hash from inspection JSON")
    sp.add_argument("--state", required=True)

    sp = sub.add_parser("validate", help="Validate an inspection state; optionally replay its embedded history from genesis")
    sp.add_argument("--state", required=True)
    sp.add_argument("--genesis")

    sp = sub.add_parser("apply", help="Apply one inspection transition event")
    sp.add_argument("--state", required=True)
    sp.add_argument("--event", required=True)

    sp = sub.add_parser("replay", help="Replay an inspection JSON array of events from a genesis state")
    sp.add_argument("--genesis", required=True)
    sp.add_argument("--events", required=True)

    sp = sub.add_parser("diff", help="Compare two inspection states with the same identity")
    sp.add_argument("--left", required=True)
    sp.add_argument("--right", required=True)

    sp = sub.add_parser("topology", help="Compute topology descriptors from the current relation basis")
    sp.add_argument("--state", required=True)
    sp.add_argument("--methods", default="graph.components,graph.cycle_rank")

    sp = sub.add_parser("fuse", help="Fuse inspection multi-source semantic proposals and apply one atomic event")
    sp.add_argument("--state", required=True)
    sp.add_argument("--proposals", required=True)
    sp.add_argument("--event-id", required=True)
    sp.add_argument("--axis-threshold", type=float, default=0.5)
    sp.add_argument("--relation-threshold", type=float, default=0.5)
    sp.add_argument("--occurred-at")

    # v0.3 legacy native artifact commands remain available for migration.
    sp = sub.add_parser("native-pack", help="Compile inspection JSON to legacy v0.3 self-contained .isqln bytes")
    sp.add_argument("--state", required=True)
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("native-inspect", help="Project legacy v0.3 self-contained .isqln into inspection JSON")
    sp.add_argument("--native", required=True)

    sp = sub.add_parser("native-hash", help="Compute hash from legacy v0.3 self-contained .isqln")
    sp.add_argument("--native", required=True)

    sp = sub.add_parser("bridge", help="Legacy Core bridge: R3/DSRN for v0.3 native or R2/DSR for inspection JSON")
    source = sp.add_mutually_exclusive_group(required=True)
    source.add_argument("--state")
    source.add_argument("--native")
    sp.add_argument("--domain", choices=("sem", "state", "bundle"), default="state")

    # v0.4 registered machine path.
    sp = sub.add_parser("registry-build", help="Build/extend canonical .isqlr symbol registry from inspection state and optional events")
    sp.add_argument("--state", required=True)
    sp.add_argument("--events")
    sp.add_argument("--base-registry")
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("registered-pack", help="Compile inspection state into registry-bound canonical v0.4 .isqln")
    sp.add_argument("--state", required=True)
    sp.add_argument("--registry", required=True)
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("registered-inspect", help="Project registry-bound v0.4 .isqln into inspection JSON")
    sp.add_argument("--native", required=True)
    sp.add_argument("--registry", required=True)

    sp = sub.add_parser("registered-hash", help="Compute canonical v0.4 registered snapshot hash")
    sp.add_argument("--native", required=True)
    sp.add_argument("--registry", required=True)

    sp = sub.add_parser("stream-pack", help="Compile inspection event history into canonical v0.4 .isqle")
    sp.add_argument("--genesis", required=True)
    sp.add_argument("--events", required=True)
    sp.add_argument("--registry", required=True)
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("stream-replay", help="Replay canonical .isqle from registered genesis and emit final registered .isqln")
    sp.add_argument("--genesis-native", required=True)
    sp.add_argument("--stream", required=True)
    sp.add_argument("--registry", required=True)
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("bridge-r4", help="Export Core-parseable R4 registered state/semantic or native execution stream wire")
    sp.add_argument("--registry", required=True)
    sp.add_argument("--native")
    sp.add_argument("--stream")
    sp.add_argument("--genesis-native")
    sp.add_argument("--domain", choices=("sem", "state", "exec"), required=True)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "new":
            context = json.loads(args.context_json)
            if not isinstance(context, dict):
                raise ValueError("--context-json must decode to an object")
            _emit(SemanticState(identity=args.identity, context=context).to_dict())
            return 0

        if args.command == "hash":
            state = _read_state(args.state)
            _emit({"schema": "isql.dsr-hash/v0.3", "identity": state.identity, "revision": state.revision, "state_hash": state_hash(state)})
            return 0

        if args.command == "validate":
            state = _read_state(args.state)
            genesis = _read_state(args.genesis) if args.genesis else None
            _emit(validate_state(state, genesis=genesis).to_dict())
            return 0

        if args.command == "apply":
            state = _read_state(args.state)
            raw = _read_json(args.event)
            if not isinstance(raw, dict):
                raise ValueError("event JSON must be an object")
            event = TransitionEvent.from_dict(raw)
            result = apply_event(state, event)
            _emit({"schema": "isql.dsr-apply-result/v0.3", "previous_hash": result.previous_hash, "next_hash": result.next_hash, "state": result.state.to_dict()})
            return 0

        if args.command == "replay":
            _emit(replay(_read_state(args.genesis), _read_events(args.events)).to_dict())
            return 0

        if args.command == "diff":
            _emit(diff_states(_read_state(args.left), _read_state(args.right)).to_dict())
            return 0

        if args.command == "topology":
            state = _read_state(args.state)
            methods = tuple(x.strip() for x in args.methods.split(",") if x.strip())
            descriptors = compute_topology_descriptors(state, methods=methods)
            _emit({"schema": "isql.dsr-topology-result/v0.3", "identity": state.identity, "revision": state.revision, "basis_hash": topology_basis_hash(state), "descriptors": [x.to_dict() for x in descriptors]})
            return 0

        if args.command == "fuse":
            state = _read_state(args.state)
            raw = _read_json(args.proposals)
            if not isinstance(raw, list):
                raise ValueError("proposals JSON must be an array")
            proposals = [SemanticProposal.from_dict(x) for x in raw]
            event = TransitionEvent.for_state(
                state, event_id=args.event_id, operation="fuse_proposals",
                payload={"proposals": [x.to_dict() for x in proposals], "axis_threshold": args.axis_threshold, "relation_threshold": args.relation_threshold},
                occurred_at=args.occurred_at,
            )
            result = apply_event(state, event)
            fusion = result.state.history[-1]["result"]["fusion"]
            _emit({"schema": "isql.dsr-fuse-result/v0.3", "previous_hash": result.previous_hash, "next_hash": result.next_hash, "fusion": fusion, "state": result.state.to_dict()})
            return 0

        if args.command == "native-pack":
            state = _read_state(args.state)
            payload = encode_state(state)
            Path(args.out).write_bytes(payload)
            _emit({"schema": "isql.dsr-native-artifact/v0.3", "identity": state.identity, "revision": state.revision, "state_hash": state_hash(state), "bytes": len(payload), "path": str(Path(args.out))})
            return 0

        if args.command == "native-inspect":
            _emit(_read_native(args.native).to_dict())
            return 0

        if args.command == "native-hash":
            state = _read_native(args.native)
            _emit({"schema": "isql.dsr-native-hash/v0.3", "identity": state.identity, "revision": state.revision, "state_hash": state_hash(state)})
            return 0

        if args.command == "bridge":
            if args.native:
                state = _read_native(args.native)
                _emit((to_native_core_sem_envelope(state) if args.domain == "sem" else to_native_core_state_envelope(state) if args.domain == "state" else to_native_core_bundle(state)).to_dict())
            else:
                state = _read_state(args.state)
                _emit((to_core_sem_envelope(state) if args.domain == "sem" else to_core_state_envelope(state) if args.domain == "state" else to_core_bundle(state)).to_dict())
            return 0

        if args.command == "registry-build":
            base = _read_registry(args.base_registry) if args.base_registry else NativeSymbolRegistry()
            state = _read_state(args.state)
            registry = extend_registry_for_state(base, state)
            events = _read_events(args.events) if args.events else []
            if events:
                registry = extend_registry_for_events(registry, events)
            payload = encode_registry(registry)
            Path(args.out).write_bytes(payload)
            _emit({
                "schema": "isql.dsr-registry-artifact/v0.4",
                "revision": registry.revision,
                "registry_hash": registry_hash(registry),
                "prefix_hash": registry.prefix_hash(registry.revision),
                "bytes": len(payload),
                "path": str(Path(args.out)),
            })
            return 0

        if args.command == "registered-pack":
            registry = _read_registry(args.registry)
            state = compile_registered_state(_read_state(args.state), registry)
            payload = encode_registered_state(state)
            Path(args.out).write_bytes(payload)
            _emit({
                "schema": "isql.dsr-registered-artifact/v0.4",
                "identity_ref": state.identity_ref,
                "revision": state.revision,
                "registry_revision": state.registry_revision,
                "registry_hash": state.registry_hash,
                "state_hash": registered_state_hash(state),
                "bytes": len(payload),
                "path": str(Path(args.out)),
            })
            return 0

        if args.command == "registered-inspect":
            registry = _read_registry(args.registry)
            _emit(inspect_registered_state(_read_registered(args.native, registry), registry).to_dict())
            return 0

        if args.command == "registered-hash":
            registry = _read_registry(args.registry)
            state = _read_registered(args.native, registry)
            _emit({"schema": "isql.dsr-registered-hash/v0.4", "identity_ref": state.identity_ref, "revision": state.revision, "state_hash": registered_state_hash(state)})
            return 0

        if args.command == "stream-pack":
            registry = _read_registry(args.registry)
            stream = build_event_stream(_read_state(args.genesis), _read_events(args.events), registry)
            payload = encode_event_stream(stream)
            Path(args.out).write_bytes(payload)
            _emit({
                "schema": "isql.dsr-event-stream/v0.4",
                "registry_revision": stream.registry_revision,
                "registry_hash": stream.registry_hash,
                "genesis_hash": stream.genesis_hash,
                "records": len(stream.records),
                "final_hash": stream.records[-1].next_hash if stream.records else stream.genesis_hash,
                "bytes": len(payload),
                "path": str(Path(args.out)),
            })
            return 0

        if args.command == "stream-replay":
            registry = _read_registry(args.registry)
            genesis = _read_registered(args.genesis_native, registry)
            stream = _read_stream(args.stream, registry)
            final = replay_native_stream(genesis, stream, registry)
            payload = encode_registered_state(final)
            Path(args.out).write_bytes(payload)
            _emit({
                "schema": "isql.dsr-stream-replay-result/v0.4",
                "identity_ref": final.identity_ref,
                "revision": final.revision,
                "state_hash": registered_state_hash(final),
                "bytes": len(payload),
                "path": str(Path(args.out)),
            })
            return 0

        if args.command == "bridge-r4":
            registry = _read_registry(args.registry)
            if args.domain in {"sem", "state"}:
                if not args.native or args.stream:
                    raise ValueError("SEM/STATE R4 bridge requires --native and no --stream")
                state = _read_registered(args.native, registry)
                env = to_registered_core_sem_envelope(state) if args.domain == "sem" else to_registered_core_state_envelope(state)
            else:
                if not args.stream or not args.genesis_native or args.native:
                    raise ValueError("EXEC R4 bridge requires --stream and --genesis-native and no --native")
                stream = _read_stream(args.stream, registry)
                genesis = _read_registered(args.genesis_native, registry)
                env = to_registered_core_exec_envelope(stream, genesis)
            _emit(env.to_dict())
            return 0

        parser.error("unknown command")
        return 2
    except (DSRError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        return 2
