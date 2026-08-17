from __future__ import annotations

import json
from pathlib import Path

from isql_dsr.branch import NativeBranch, encode_branch, merge_native_branches
from isql_dsr.bridge import to_registered_core_program_envelope
from isql_dsr.canonical import state_hash
from isql_dsr.events import TransitionEvent
from isql_dsr.machine import compile_registered_state, encode_registered_state, inspect_registered_state, registered_state_hash
from isql_dsr.model import PointValue, SemanticState, SpectrumAxis, TypedRelation
from isql_dsr.native import encode_uvarint, operation_opcode
from isql_dsr.program import (
    EFFECT_AXIS,
    NativeInstruction,
    NativeProgram,
    encode_program,
    execute_native_program,
    operator_effect_mask,
    program_from_stream,
)
from isql_dsr.registry import (
    NativeSymbolRegistry,
    SymbolNamespace,
    encode_registry,
    extend_registry_for_events,
    extend_registry_for_state,
)
from isql_dsr.runtime import apply_event
from isql_dsr.stream import build_event_stream, encode_event_stream


HERE = Path(__file__).resolve().parent


def dump(name: str, value) -> None:
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def receipt_dict(receipt):
    return {
        "status": receipt.status,
        "program_ref": receipt.program_ref,
        "base_hash": receipt.base_hash,
        "final_hash": receipt.final_hash,
        "execution_order": list(receipt.execution_order),
        "failed_instruction_ref": receipt.failed_instruction_ref,
        "error_code": receipt.error_code,
    }


def make_event(state: SemanticState, event_id: str, operation: str, payload: dict) -> TransitionEvent:
    return TransitionEvent.for_state(state, event_id=event_id, operation=operation, payload=payload)


def main() -> None:
    base = SemanticState(identity="agent:deploy-runtime", context={"mode": "native"})

    main_events = []
    semantic = base
    specs = (
        ("main-1", "upsert_axis", {"axis": SpectrumAxis("risk", "ordinal", PointValue(2), 0.1, 1).to_dict()}),
        ("main-2", "upsert_relation", {"relation": TypedRelation("plan", "supports", "deploy").to_dict()}),
        ("main-3", "refresh_topology", {"methods": ["graph.components"]}),
    )
    for event_id, operation, payload in specs:
        event = make_event(semantic, event_id, operation, payload)
        main_events.append(event)
        semantic = apply_event(semantic, event).state

    research_event = TransitionEvent(
        event_id="branch-research",
        operation="upsert_axis",
        payload={"axis": SpectrumAxis("risk", "ordinal", PointValue(3), 0.1, 2).to_dict()},
        base_revision=0,
        previous_hash=state_hash(base),
    )
    review_event = TransitionEvent(
        event_id="branch-review",
        operation="upsert_axis",
        payload={"axis": SpectrumAxis("risk", "ordinal", PointValue(5), 0.05, 3).to_dict()},
        base_revision=0,
        previous_hash=state_hash(base),
    )
    parallel_event = TransitionEvent(
        event_id="branch-parallel",
        operation="upsert_axis",
        payload={"axis": SpectrumAxis("risk", "ordinal", PointValue(9), 0.1, 2).to_dict()},
        base_revision=0,
        previous_hash=state_hash(base),
    )

    registry = extend_registry_for_state(NativeSymbolRegistry(), base)
    for group in (tuple(main_events), (research_event,), (review_event,), (parallel_event,)):
        registry = extend_registry_for_events(registry, group)

    branch_refs = {}
    for name in ("research", "review", "parallel"):
        registry, branch_refs[name] = registry.intern_text(SymbolNamespace.BRANCH_ID, name)

    program_refs = {}
    for name in ("deploy-program", "rollback-program"):
        registry, program_refs[name] = registry.intern_text(SymbolNamespace.PROGRAM_ID, name)

    instruction_refs = {}
    for name in ("p1", "p2", "p3", "rb1", "rb2"):
        registry, instruction_refs[name] = registry.intern_text(SymbolNamespace.INSTRUCTION_ID, name)

    registry, missing_axis_ref = registry.intern_text(SymbolNamespace.AXIS_KEY, "missing-axis")

    registry_bytes = encode_registry(registry)
    (HERE / "symbols.isqlr").write_bytes(registry_bytes)

    genesis = compile_registered_state(base, registry)
    genesis_bytes = encode_registered_state(genesis)
    (HERE / "genesis.isqln").write_bytes(genesis_bytes)
    dump("genesis.inspection.json", inspect_registered_state(genesis, registry).to_dict())

    stream = build_event_stream(base, main_events, registry)
    stream_bytes = encode_event_stream(stream)
    (HERE / "history.isqle").write_bytes(stream_bytes)

    program = program_from_stream(
        stream,
        registry,
        program_refs["deploy-program"],
        (instruction_refs["p1"], instruction_refs["p2"], instruction_refs["p3"]),
    )
    program_bytes = encode_program(program)
    (HERE / "deploy.isqlp").write_bytes(program_bytes)
    success = execute_native_program(genesis, program, registry)
    success_bytes = encode_registered_state(success.state)
    (HERE / "deploy-final.isqln").write_bytes(success_bytes)
    dump("deploy-receipt.json", receipt_dict(success.receipt))
    dump("deploy-final.inspection.json", inspect_registered_state(success.state, registry).to_dict())

    first = stream.records[0].event
    rollback_program = NativeProgram(
        registry.revision,
        registry.prefix_hash(registry.revision),
        program_refs["rollback-program"],
        genesis.revision,
        registered_state_hash(genesis),
        (
            NativeInstruction(
                instruction_refs["rb1"], first.opcode, operator_effect_mask(first.opcode), (), first.payload
            ),
            NativeInstruction(
                instruction_refs["rb2"], operation_opcode("remove_axis"), EFFECT_AXIS,
                (instruction_refs["rb1"],), encode_uvarint(missing_axis_ref)
            ),
        ),
    )
    rollback_bytes = encode_program(rollback_program)
    (HERE / "rollback.isqlp").write_bytes(rollback_bytes)
    rollback = execute_native_program(genesis, rollback_program, registry)
    rollback_state_bytes = encode_registered_state(rollback.state)
    (HERE / "rollback-result.isqln").write_bytes(rollback_state_bytes)
    dump("rollback-receipt.json", receipt_dict(rollback.receipt))

    research_stream = build_event_stream(base, (research_event,), registry)
    review_stream = build_event_stream(base, (review_event,), registry)
    parallel_stream = build_event_stream(base, (parallel_event,), registry)
    research = NativeBranch(branch_refs["research"], 0, registered_state_hash(genesis), research_stream)
    review = NativeBranch(branch_refs["review"], 0, registered_state_hash(genesis), review_stream, (branch_refs["research"],))
    parallel = NativeBranch(branch_refs["parallel"], 0, registered_state_hash(genesis), parallel_stream)
    for name, branch in (("research", research), ("review", review), ("parallel", parallel)):
        (HERE / f"{name}.isqlb").write_bytes(encode_branch(branch))

    causal_merge = merge_native_branches(genesis, (review, research), registry)
    (HERE / "causal-merged.isqln").write_bytes(encode_registered_state(causal_merge.state))
    dump("causal-merge.inspection.json", {
        "conflicts": [
            {"kind": c.kind, "key": list(c.key), "branch_refs": list(c.branch_refs)}
            for c in causal_merge.conflicts
        ],
        "state": inspect_registered_state(causal_merge.state, registry).to_dict(),
    })

    concurrent_merge = merge_native_branches(genesis, (research, parallel), registry)
    dump("concurrent-conflict.json", {
        "conflicts": [
            {"kind": c.kind, "key": list(c.key), "branch_refs": list(c.branch_refs)}
            for c in concurrent_merge.conflicts
        ],
        "state_hash": registered_state_hash(concurrent_merge.state),
    })

    core_program = to_registered_core_program_envelope(program, genesis)
    dump("core-program-envelope.json", core_program.to_dict())

    canonical_files = [
        "genesis.isqln", "history.isqle", "deploy.isqlp", "deploy-final.isqln",
        "rollback.isqlp", "rollback-result.isqln", "research.isqlb", "review.isqlb",
        "parallel.isqlb", "causal-merged.isqln",
    ]
    labels = [b"risk", b"ordinal", b"supports", b"deploy", b"graph.components", b"program_ref", b"instruction_ref", b"depends_on"]
    leaks = {}
    for filename in canonical_files:
        raw = (HERE / filename).read_bytes()
        leaks[filename] = [label.decode("ascii") for label in labels if label in raw]

    summary = {
        "schema": "isql.dsr-v0.6-example-summary/v0.6",
        "registry_revision": registry.revision,
        "registry_bytes": len(registry_bytes),
        "genesis_bytes": len(genesis_bytes),
        "stream_bytes": len(stream_bytes),
        "program_bytes": len(program_bytes),
        "program_final_bytes": len(success_bytes),
        "rollback_program_bytes": len(rollback_bytes),
        "rollback_result_bytes": len(rollback_state_bytes),
        "rollback_exact_base": rollback_state_bytes == genesis_bytes,
        "success_status": success.receipt.status,
        "rollback_status": rollback.receipt.status,
        "causal_merge_conflicts": len(causal_merge.conflicts),
        "causal_merge_risk": inspect_registered_state(causal_merge.state, registry).axes[0].value.to_dict(),
        "concurrent_conflicts": len(concurrent_merge.conflicts),
        "core_program_wire_prefix": core_program.wire[:20],
        "identifier_leaks": leaks,
    }
    dump("summary.json", summary)


if __name__ == "__main__":
    main()
