import unittest

from isql_dsr.events import TransitionEvent
from isql_dsr.machine import compile_registered_state, registered_state_hash
from isql_dsr.model import PointValue, SemanticState, SpectrumAxis, TypedRelation
from isql_dsr.native import encode_uvarint, operation_opcode
from isql_dsr.program import (
    EFFECT_AXIS,
    EXECUTION_FAILED,
    EXECUTION_SUCCESS,
    NativeInstruction,
    NativeProgram,
    execute_native_program,
    operator_effect_mask,
    program_from_stream,
)
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace, extend_registry_for_events, extend_registry_for_state
from isql_dsr.runtime import apply_event
from isql_dsr.stream import build_event_stream, replay_native_stream


class ProgramExecutionV06Tests(unittest.TestCase):
    def build_chain(self):
        base = SemanticState(identity="obj:program")
        events = []
        state = base
        specs = (
            ("e1", "upsert_axis", {"axis": SpectrumAxis("risk", "ordinal", PointValue(2), 0.1, 1).to_dict()}),
            ("e2", "upsert_relation", {"relation": TypedRelation("risk", "supports", "deploy").to_dict()}),
            ("e3", "refresh_topology", {"methods": ["graph.components"]}),
        )
        for event_id, operation, payload in specs:
            event = TransitionEvent.for_state(state, event_id=event_id, operation=operation, payload=payload)
            events.append(event)
            state = apply_event(state, event).state

        registry = extend_registry_for_state(NativeSymbolRegistry(), base)
        registry = extend_registry_for_events(registry, events)
        registry, program_ref = registry.intern_text(SymbolNamespace.PROGRAM_ID, "program:chain")
        refs = []
        for name in ("i1", "i2", "i3"):
            registry, ref = registry.intern_text(SymbolNamespace.INSTRUCTION_ID, name)
            refs.append(ref)
        stream = build_event_stream(base, events, registry)
        genesis = compile_registered_state(base, registry)
        program = program_from_stream(stream, registry, program_ref, refs)
        return registry, genesis, stream, program, tuple(refs)

    def test_program_executes_in_deterministic_causal_order_and_matches_stream_result(self):
        registry, genesis, stream, program, refs = self.build_chain()
        result = execute_native_program(genesis, program, registry)
        expected = replay_native_stream(genesis, stream, registry)
        self.assertEqual(result.receipt.status, EXECUTION_SUCCESS)
        self.assertEqual(result.receipt.execution_order, refs)
        self.assertEqual(result.state, expected)
        self.assertEqual(result.receipt.final_hash, registered_state_hash(expected))
        self.assertEqual(result.receipt.failed_instruction_ref, 0)

    def test_failed_program_rolls_back_all_prior_instruction_effects(self):
        base = SemanticState(identity="obj:rollback")
        valid_event = TransitionEvent.for_state(
            base,
            event_id="e1",
            operation="upsert_axis",
            payload={"axis": SpectrumAxis("risk", "ordinal", PointValue(9), 0.2, 1).to_dict()},
        )
        registry = extend_registry_for_state(NativeSymbolRegistry(), base)
        registry = extend_registry_for_events(registry, (valid_event,))
        registry, missing_ref = registry.intern_text(SymbolNamespace.AXIS_KEY, "missing")
        registry, program_ref = registry.intern_text(SymbolNamespace.PROGRAM_ID, "program:rollback")
        registry, i1 = registry.intern_text(SymbolNamespace.INSTRUCTION_ID, "r1")
        registry, i2 = registry.intern_text(SymbolNamespace.INSTRUCTION_ID, "r2")
        genesis = compile_registered_state(base, registry)
        stream = build_event_stream(base, (valid_event,), registry)
        first = stream.records[0].event
        program = NativeProgram(
            registry.revision,
            registry.prefix_hash(),
            program_ref,
            genesis.revision,
            registered_state_hash(genesis),
            (
                NativeInstruction(i1, first.opcode, operator_effect_mask(first.opcode), (), first.payload),
                NativeInstruction(i2, operation_opcode("remove_axis"), EFFECT_AXIS, (i1,), encode_uvarint(missing_ref)),
            ),
        )
        result = execute_native_program(genesis, program, registry)
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(result.state, genesis)
        self.assertEqual(result.receipt.final_hash, registered_state_hash(genesis))
        self.assertEqual(result.receipt.execution_order, (i1,))
        self.assertEqual(result.receipt.failed_instruction_ref, i2)
        self.assertEqual(result.receipt.error_code, "AXIS_NOT_FOUND")

    def test_program_base_or_registry_mismatch_fails_without_execution(self):
        registry, genesis, _, program, _ = self.build_chain()
        bad = NativeProgram(
            program.registry_revision,
            program.registry_hash,
            program.program_ref,
            program.base_revision + 1,
            program.base_hash,
            program.instructions,
        )
        result = execute_native_program(genesis, bad, registry)
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(result.state, genesis)
        self.assertEqual(result.receipt.execution_order, ())
        self.assertEqual(result.receipt.error_code, "PROGRAM_BASE_REVISION_MISMATCH")


if __name__ == "__main__":
    unittest.main()
