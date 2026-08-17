from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .branch import NativeBranch, decode_branch, encode_branch, merge_native_branches
from .bridge import (
    to_core_bundle, to_core_sem_envelope, to_core_state_envelope,
    to_native_core_bundle, to_native_core_sem_envelope, to_native_core_state_envelope,
    to_registered_core_exec_envelope, to_registered_core_program_envelope, to_registered_core_vm_envelope,
    to_registered_core_sem_envelope, to_registered_core_state_envelope,
)
from .canonical import state_hash
from .diff import diff_states
from .errors import DSRError
from .events import TransitionEvent
from .fusion import SemanticProposal
from .linker import link_vm_programs
from .optimizer import optimize_vm_program
from .machine import (
    compile_registered_state, decode_registered_state, encode_registered_state,
    inspect_registered_state, registered_state_hash,
)
from .model import SemanticState, semantic_value_from_dict
from .native import decode_state, encode_state
from .registry import (
    NativeSymbolRegistry, SymbolNamespace, decode_registry, encode_registry, extend_registry_for_events,
    extend_registry_for_state, registry_hash,
)
from .runtime import apply_event, replay
from .program import decode_program, encode_program, execute_native_program, program_from_stream
from .vm import ALL_CAPABILITIES, decode_vm_program, encode_vm_program, execute_vm_transaction
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


def _read_program(path: str, registry: NativeSymbolRegistry):
    return decode_program(Path(path).read_bytes(), registry)


def _read_vm_program(path: str, registry: NativeSymbolRegistry):
    return decode_vm_program(Path(path).read_bytes(), registry)


def _parse_state_assignments(values: list[str], registry: NativeSymbolRegistry):
    states = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError("--state must use SLOT_REF=PATH")
        slot_text, path = raw.split("=", 1)
        slot_ref = int(slot_text)
        if slot_ref in states:
            raise ValueError("duplicate state slot")
        registry.resolve(slot_ref, SymbolNamespace.STATE_SLOT_ID)
        states[slot_ref] = _read_registered(path, registry)
    return states


def _parse_register_arguments(values: list[str], registry: NativeSymbolRegistry):
    arguments = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError("--arg must use REGISTER_REF=JSON")
        ref_text, payload = raw.split("=", 1)
        ref = int(ref_text)
        if ref in arguments:
            raise ValueError("duplicate register argument")
        registry.resolve(ref, SymbolNamespace.REGISTER_ID)
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError("--arg JSON must be a semantic-value object")
        arguments[ref] = semantic_value_from_dict(value)
    return arguments


def _parse_scoped_capabilities(values: list[str], registry: NativeSymbolRegistry):
    scopes = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError("--scope must use SLOT_REF=MASK")
        ref_text, mask_text = raw.split("=", 1)
        ref = int(ref_text); mask = int(mask_text)
        if ref in scopes:
            raise ValueError("duplicate scoped capability slot")
        registry.resolve(ref, SymbolNamespace.STATE_SLOT_ID)
        if mask < 0:
            raise ValueError("scoped capability mask must be nonnegative")
        scopes[ref] = mask
    return scopes


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="isql-dsr", description="ISQL Dynamic Spectrum Runtime v1.0 (typed composite machine values, bounded native computation, and optimizer)")
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

    # v0.5 registered machine path.
    sp = sub.add_parser("registry-build", help="Build/extend canonical .isqlr symbol registry from inspection state and optional events")
    sp.add_argument("--state", required=True)
    sp.add_argument("--events")
    sp.add_argument("--base-registry")
    sp.add_argument("--out", required=True)
    sp.add_argument("--branch-id", action="append", default=[])
    sp.add_argument("--program-id", action="append", default=[])
    sp.add_argument("--instruction-id", action="append", default=[])
    sp.add_argument("--state-slot-id", action="append", default=[])
    sp.add_argument("--capability-id", action="append", default=[])

    sp = sub.add_parser("registered-pack", help="Compile inspection state into registry-bound canonical v0.5 .isqln")
    sp.add_argument("--state", required=True)
    sp.add_argument("--registry", required=True)
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("registered-inspect", help="Project registry-bound v0.5 .isqln into inspection JSON")
    sp.add_argument("--native", required=True)
    sp.add_argument("--registry", required=True)

    sp = sub.add_parser("registered-hash", help="Compute canonical v0.5 registered snapshot hash")
    sp.add_argument("--native", required=True)
    sp.add_argument("--registry", required=True)

    sp = sub.add_parser("stream-pack", help="Compile inspection event history into canonical v0.5 .isqle")
    sp.add_argument("--genesis", required=True)
    sp.add_argument("--events", required=True)
    sp.add_argument("--registry", required=True)
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("stream-replay", help="Replay canonical .isqle from registered genesis and emit final registered .isqln")
    sp.add_argument("--genesis-native", required=True)
    sp.add_argument("--stream", required=True)
    sp.add_argument("--registry", required=True)
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("branch-pack", help="Compile one forked native branch artifact (.isqlb)")
    sp.add_argument("--branch-id", required=True)
    sp.add_argument("--genesis", required=True)
    sp.add_argument("--events", required=True)
    sp.add_argument("--registry", required=True)
    sp.add_argument("--depends-on", action="append", default=[])
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("branch-merge", help="Three-way merge native branch artifacts against one registered base")
    sp.add_argument("--base-native", required=True)
    sp.add_argument("--branch", action="append", required=True)
    sp.add_argument("--registry", required=True)
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("program-pack", help="Compile a native event stream into canonical causal .isqlp program")
    sp.add_argument("--registry", required=True)
    sp.add_argument("--genesis-native", required=True)
    sp.add_argument("--stream", required=True)
    sp.add_argument("--program-id", required=True)
    sp.add_argument("--instruction-id", action="append", required=True)
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("program-run", help="Execute canonical .isqlp atomically against one registered genesis")
    sp.add_argument("--registry", required=True)
    sp.add_argument("--genesis-native", required=True)
    sp.add_argument("--program", required=True)
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("program-bridge", help="Export Core-parseable EXEC/R4/DSRP wire for a canonical .isqlp program")
    sp.add_argument("--registry", required=True)
    sp.add_argument("--genesis-native", required=True)
    sp.add_argument("--program", required=True)

    sp = sub.add_parser("vm-link", help="Statically compose native v0.9 .isqlp DAG modules")
    sp.add_argument("--registry", required=True)
    sp.add_argument("--program-ref", type=int, required=True)
    sp.add_argument("--module", action="append", required=True)
    sp.add_argument("--argument-register", type=int, action="append", default=[])
    sp.add_argument("--return-register", type=int, action="append", default=[])
    sp.add_argument("--parallel-modules", action="store_true", help="preserve modules without adding sequential causal edges")
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("vm-optimize", help="Optimize a canonical native .isqlp program without executing it")
    sp.add_argument("--registry", required=True)
    sp.add_argument("--program", required=True)
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("vm-run", help="Execute v1.0 typed/composite register VM transaction across registered state slots")
    sp.add_argument("--registry", required=True)
    sp.add_argument("--program", required=True)
    sp.add_argument("--state", action="append", required=True, help="numeric SLOT_REF=PATH")
    sp.add_argument("--callee", action="append", default=[], help="additional .isqlp subprogram")
    sp.add_argument("--capabilities", type=int, default=ALL_CAPABILITIES)
    sp.add_argument("--scope", action="append", default=[], help="numeric SLOT_REF=CAPABILITY_MASK")
    sp.add_argument("--arg", action="append", default=[], help="numeric REGISTER_REF=SEMANTIC_VALUE_JSON")
    sp.add_argument("--parallel", action="store_true", help="execute hazard-free instruction batches concurrently")
    sp.add_argument("--out-dir", required=True)

    sp = sub.add_parser("vm-bridge", help="Export Core-parseable EXEC/R4/DSRV wire for a native VM program")
    sp.add_argument("--registry", required=True)
    sp.add_argument("--program", required=True)
    sp.add_argument("--state", action="append", required=True, help="numeric SLOT_REF=PATH")

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
            for branch_id in args.branch_id:
                registry, _ = registry.intern_text(SymbolNamespace.BRANCH_ID, branch_id)
            for program_id in args.program_id:
                registry, _ = registry.intern_text(SymbolNamespace.PROGRAM_ID, program_id)
            for instruction_id in args.instruction_id:
                registry, _ = registry.intern_text(SymbolNamespace.INSTRUCTION_ID, instruction_id)
            for state_slot_id in args.state_slot_id:
                registry, _ = registry.intern_text(SymbolNamespace.STATE_SLOT_ID, state_slot_id)
            for capability_id in args.capability_id:
                registry, _ = registry.intern_text(SymbolNamespace.CAPABILITY_ID, capability_id)
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
                "schema": "isql.dsr-registered-artifact/v0.5",
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
            _emit({"schema": "isql.dsr-registered-hash/v0.5", "identity_ref": state.identity_ref, "revision": state.revision, "state_hash": registered_state_hash(state)})
            return 0

        if args.command == "stream-pack":
            registry = _read_registry(args.registry)
            stream = build_event_stream(_read_state(args.genesis), _read_events(args.events), registry)
            payload = encode_event_stream(stream)
            Path(args.out).write_bytes(payload)
            _emit({
                "schema": "isql.dsr-event-stream/v0.5",
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
                "schema": "isql.dsr-stream-replay-result/v0.5",
                "identity_ref": final.identity_ref,
                "revision": final.revision,
                "state_hash": registered_state_hash(final),
                "bytes": len(payload),
                "path": str(Path(args.out)),
            })
            return 0

        if args.command == "branch-pack":
            registry = _read_registry(args.registry)
            branch_ref = registry.lookup_text(SymbolNamespace.BRANCH_ID, args.branch_id)
            if branch_ref is None:
                raise ValueError("branch id is not present in registry")
            genesis = _read_state(args.genesis)
            stream = build_event_stream(genesis, _read_events(args.events), registry)
            dependency_refs = []
            for dep_id in args.depends_on:
                dep_ref = registry.lookup_text(SymbolNamespace.BRANCH_ID, dep_id)
                if dep_ref is None:
                    raise ValueError(f"dependency branch id is not present in registry: {dep_id}")
                dependency_refs.append(dep_ref)
            branch = NativeBranch(branch_ref, genesis.revision, stream.genesis_hash, stream, tuple(dependency_refs))
            payload = encode_branch(branch)
            Path(args.out).write_bytes(payload)
            _emit({
                "schema": "isql.dsr-branch-artifact/v0.6",
                "branch_ref": branch.branch_ref,
                "depends_on": list(branch.depends_on),
                "base_revision": branch.base_revision,
                "base_hash": branch.base_hash,
                "records": len(branch.stream.records),
                "bytes": len(payload),
                "path": str(Path(args.out)),
            })
            return 0

        if args.command == "branch-merge":
            registry = _read_registry(args.registry)
            base = _read_registered(args.base_native, registry)
            branches = tuple(decode_branch(Path(path).read_bytes(), registry) for path in args.branch)
            result = merge_native_branches(base, branches, registry)
            payload = encode_registered_state(result.state)
            Path(args.out).write_bytes(payload)
            _emit({
                "schema": "isql.dsr-branch-merge-result/v0.6",
                "branch_refs": list(result.branch_refs),
                "revision": result.state.revision,
                "state_hash": registered_state_hash(result.state),
                "conflicts": [
                    {"kind": c.kind, "key": list(c.key), "branch_refs": list(c.branch_refs)}
                    for c in result.conflicts
                ],
                "bytes": len(payload),
                "path": str(Path(args.out)),
            })
            return 0

        if args.command == "program-pack":
            registry = _read_registry(args.registry)
            genesis = _read_registered(args.genesis_native, registry)
            stream = _read_stream(args.stream, registry)
            if stream.genesis_hash != registered_state_hash(genesis):
                raise ValueError("program stream genesis does not match registered genesis")
            program_ref = registry.lookup_text(SymbolNamespace.PROGRAM_ID, args.program_id)
            if program_ref is None:
                raise ValueError("program id is not present in registry")
            instruction_refs = []
            for instruction_id in args.instruction_id:
                ref = registry.lookup_text(SymbolNamespace.INSTRUCTION_ID, instruction_id)
                if ref is None:
                    raise ValueError(f"instruction id is not present in registry: {instruction_id}")
                instruction_refs.append(ref)
            program = program_from_stream(stream, registry, program_ref, tuple(instruction_refs))
            if program.base_revision != genesis.revision or program.base_hash != registered_state_hash(genesis):
                raise ValueError("program base does not match registered genesis")
            payload = encode_program(program)
            Path(args.out).write_bytes(payload)
            _emit({
                "schema": "isql.dsr-program-artifact/v0.6",
                "program_ref": program.program_ref,
                "base_revision": program.base_revision,
                "base_hash": program.base_hash,
                "instructions": len(program.instructions),
                "bytes": len(payload),
                "path": str(Path(args.out)),
            })
            return 0

        if args.command == "program-run":
            registry = _read_registry(args.registry)
            genesis = _read_registered(args.genesis_native, registry)
            program = _read_program(args.program, registry)
            result = execute_native_program(genesis, program, registry)
            payload = encode_registered_state(result.state)
            Path(args.out).write_bytes(payload)
            receipt = result.receipt
            _emit({
                "schema": "isql.dsr-program-execution-result/v0.6",
                "status": receipt.status,
                "program_ref": receipt.program_ref,
                "base_hash": receipt.base_hash,
                "final_hash": receipt.final_hash,
                "execution_order": list(receipt.execution_order),
                "failed_instruction_ref": receipt.failed_instruction_ref,
                "error_code": receipt.error_code,
                "rolled_back": receipt.status != 1,
                "bytes": len(payload),
                "path": str(Path(args.out)),
            })
            return 0

        if args.command == "program-bridge":
            registry = _read_registry(args.registry)
            genesis = _read_registered(args.genesis_native, registry)
            program = _read_program(args.program, registry)
            _emit(to_registered_core_program_envelope(program, genesis).to_dict())
            return 0

        if args.command == "vm-link":
            registry = _read_registry(args.registry)
            modules = tuple(_read_vm_program(path, registry) for path in args.module)
            linked = link_vm_programs(
                registry, args.program_ref, modules, sequential=not args.parallel_modules,
                argument_registers=tuple(args.argument_register),
                return_registers=tuple(args.return_register),
            )
            raw = encode_vm_program(linked)
            Path(args.out).write_bytes(raw)
            _emit({
                "schema": "isql.dsr-vm-link-result/v0.9",
                "program_ref": linked.program_ref,
                "module_count": len(modules),
                "instruction_count": len(linked.instructions),
                "sequential": not args.parallel_modules,
                "bytes": len(raw),
                "path": str(Path(args.out)),
            })
            return 0

        if args.command == "vm-optimize":
            registry = _read_registry(args.registry)
            program = _read_vm_program(args.program, registry)
            optimized = optimize_vm_program(program)
            raw = encode_vm_program(optimized)
            Path(args.out).write_bytes(raw)
            _emit({
                "schema": "isql.dsr-vm-optimize-result/v1.0",
                "program_ref": optimized.program_ref,
                "before_instructions": len(program.instructions),
                "after_instructions": len(optimized.instructions),
                "bytes": len(raw),
                "path": str(Path(args.out)),
            })
            return 0

        if args.command == "vm-run":
            registry = _read_registry(args.registry)
            program = _read_vm_program(args.program, registry)
            states = _parse_state_assignments(args.state, registry)
            library = {}
            for path in args.callee:
                callee = _read_vm_program(path, registry)
                library[callee.program_ref] = callee
            arguments = _parse_register_arguments(args.arg, registry)
            scopes = _parse_scoped_capabilities(args.scope, registry) if args.scope else None
            result = execute_vm_transaction(
                states, program, registry, library, args.capabilities,
                arguments=arguments, granted_scoped_capabilities=scopes, parallel=args.parallel,
            )
            out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
            outputs = {}
            for slot_ref, state in sorted(result.states.items()):
                path = out_dir / f"{slot_ref}.isqln"
                path.write_bytes(encode_registered_state(state))
                outputs[str(slot_ref)] = str(path)
            receipt = result.receipt
            _emit({
                "schema": "isql.dsr-vm-transaction-result/v0.9",
                "status": receipt.status,
                "program_ref": receipt.program_ref,
                "base_hashes": [list(x) for x in receipt.base_hashes],
                "final_hashes": [list(x) for x in receipt.final_hashes],
                "execution_trace": [list(x) for x in receipt.execution_trace],
                "failed_program_ref": receipt.failed_program_ref,
                "failed_instruction_ref": receipt.failed_instruction_ref,
                "error_code": receipt.error_code,
                "rolled_back": receipt.status != 1,
                "parallel": args.parallel,
                "returns": [[ref, value.to_dict()] for ref, value in result.returns],
                "outputs": outputs,
            })
            return 0

        if args.command == "vm-bridge":
            registry = _read_registry(args.registry)
            program = _read_vm_program(args.program, registry)
            states = _parse_state_assignments(args.state, registry)
            _emit(to_registered_core_vm_envelope(program, states).to_dict())
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
