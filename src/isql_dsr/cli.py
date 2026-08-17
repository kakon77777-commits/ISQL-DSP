from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .bridge import to_core_bundle, to_core_sem_envelope, to_core_state_envelope
from .canonical import state_hash
from .diff import diff_states
from .errors import DSRError
from .events import TransitionEvent
from .fusion import SemanticProposal
from .model import SemanticState
from .runtime import apply_event, replay
from .topology import compute_topology_descriptors, topology_basis_hash
from .validation import validate_state


def _read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_state(path: str) -> SemanticState:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise ValueError("state JSON must be an object")
    return SemanticState.from_dict(raw)


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="isql-dsr", description="ISQL Dynamic Spectrum Runtime v0.2")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("new", help="Create a genesis DSR state")
    sp.add_argument("--identity", required=True)
    sp.add_argument("--context-json", default="{}")

    sp = sub.add_parser("hash", help="Compute canonical SHA-256 state hash")
    sp.add_argument("--state", required=True)

    sp = sub.add_parser("validate", help="Validate a state; optionally replay its history from genesis")
    sp.add_argument("--state", required=True)
    sp.add_argument("--genesis")

    sp = sub.add_parser("apply", help="Apply one fail-closed transition event")
    sp.add_argument("--state", required=True)
    sp.add_argument("--event", required=True)

    sp = sub.add_parser("replay", help="Replay a JSON array of events from a genesis state")
    sp.add_argument("--genesis", required=True)
    sp.add_argument("--events", required=True)

    sp = sub.add_parser("diff", help="Compare two states with the same identity")
    sp.add_argument("--left", required=True)
    sp.add_argument("--right", required=True)

    sp = sub.add_parser("topology", help="Compute topology descriptors from the current relation basis")
    sp.add_argument("--state", required=True)
    sp.add_argument("--methods", default="graph.components,graph.cycle_rank")

    sp = sub.add_parser("fuse", help="Fuse fail-closed multi-source semantic proposals and apply one atomic event")
    sp.add_argument("--state", required=True)
    sp.add_argument("--proposals", required=True)
    sp.add_argument("--event-id", required=True)
    sp.add_argument("--axis-threshold", type=float, default=0.5)
    sp.add_argument("--relation-threshold", type=float, default=0.5)
    sp.add_argument("--occurred-at")

    sp = sub.add_parser("bridge", help="Export Core-parseable SEM/R2 and/or STATE/R2 decimal wire envelope")
    sp.add_argument("--state", required=True)
    sp.add_argument("--domain", choices=("sem", "state", "bundle"), default="state")

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
            _emit({"schema": "isql.dsr-hash/v0.2", "identity": state.identity, "revision": state.revision, "state_hash": state_hash(state)})
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
            _emit({
                "schema": "isql.dsr-apply-result/v0.2",
                "previous_hash": result.previous_hash,
                "next_hash": result.next_hash,
                "state": result.state.to_dict(),
            })
            return 0

        if args.command == "replay":
            genesis = _read_state(args.genesis)
            raw = _read_json(args.events)
            if not isinstance(raw, list):
                raise ValueError("events JSON must be an array")
            events = [TransitionEvent.from_dict(x) for x in raw]
            _emit(replay(genesis, events).to_dict())
            return 0

        if args.command == "diff":
            _emit(diff_states(_read_state(args.left), _read_state(args.right)).to_dict())
            return 0

        if args.command == "topology":
            state = _read_state(args.state)
            methods = tuple(x.strip() for x in args.methods.split(",") if x.strip())
            descriptors = compute_topology_descriptors(state, methods=methods)
            _emit({
                "schema": "isql.dsr-topology-result/v0.2",
                "identity": state.identity,
                "revision": state.revision,
                "basis_hash": topology_basis_hash(state),
                "descriptors": [x.to_dict() for x in descriptors],
            })
            return 0

        if args.command == "fuse":
            state = _read_state(args.state)
            raw = _read_json(args.proposals)
            if not isinstance(raw, list):
                raise ValueError("proposals JSON must be an array")
            proposals = [SemanticProposal.from_dict(x) for x in raw]
            event = TransitionEvent.for_state(
                state,
                event_id=args.event_id,
                operation="fuse_proposals",
                payload={
                    "proposals": [x.to_dict() for x in proposals],
                    "axis_threshold": args.axis_threshold,
                    "relation_threshold": args.relation_threshold,
                },
                occurred_at=args.occurred_at,
            )
            result = apply_event(state, event)
            fusion = result.state.history[-1]["result"]["fusion"]
            _emit({
                "schema": "isql.dsr-fuse-result/v0.2",
                "previous_hash": result.previous_hash,
                "next_hash": result.next_hash,
                "fusion": fusion,
                "state": result.state.to_dict(),
            })
            return 0

        if args.command == "bridge":
            state = _read_state(args.state)
            if args.domain == "sem":
                _emit(to_core_sem_envelope(state).to_dict())
            elif args.domain == "state":
                _emit(to_core_state_envelope(state).to_dict())
            else:
                _emit(to_core_bundle(state).to_dict())
            return 0

        parser.error("unknown command")
        return 2
    except (DSRError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        return 2
