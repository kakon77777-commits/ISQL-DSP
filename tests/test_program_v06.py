import unittest

from isql_dsr.errors import DSRValidationError
from isql_dsr.native import operation_opcode
from isql_dsr.program import (
    EFFECT_AXIS,
    EFFECT_RELATION,
    EFFECT_TOPOLOGY,
    NativeInstruction,
    NativeProgram,
    decode_program,
    encode_program,
    operator_effect_mask,
)
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace


class NativeProgramV06Tests(unittest.TestCase):
    def make_registry(self):
        registry = NativeSymbolRegistry()
        registry, program_ref = registry.intern_text(SymbolNamespace.PROGRAM_ID, "program:alpha")
        registry, i1 = registry.intern_text(SymbolNamespace.INSTRUCTION_ID, "i:1")
        registry, i2 = registry.intern_text(SymbolNamespace.INSTRUCTION_ID, "i:2")
        registry, i3 = registry.intern_text(SymbolNamespace.INSTRUCTION_ID, "i:3")
        return registry, program_ref, i1, i2, i3

    def make_program(self, reversed_input=False):
        registry, program_ref, i1, i2, i3 = self.make_registry()
        rows = (
            NativeInstruction(i1, operation_opcode("upsert_axis"), EFFECT_AXIS, (), b"axis-a"),
            NativeInstruction(i2, operation_opcode("upsert_relation"), EFFECT_RELATION | EFFECT_TOPOLOGY, (i1,), b"rel-b"),
            NativeInstruction(i3, operation_opcode("refresh_topology"), EFFECT_TOPOLOGY, (i2,), b"top-c"),
        )
        if reversed_input:
            rows = tuple(reversed(rows))
        return registry, NativeProgram(
            registry.revision,
            registry.prefix_hash(registry.revision),
            program_ref,
            7,
            "11" * 32,
            rows,
        )

    def test_program_round_trip_is_canonical_and_input_order_independent(self):
        registry, program = self.make_program(False)
        registry2, program2 = self.make_program(True)
        self.assertEqual(registry, registry2)
        raw = encode_program(program)
        self.assertEqual(raw, encode_program(program2))
        self.assertEqual(program, decode_program(raw, registry))
        self.assertEqual(raw, encode_program(decode_program(raw, registry)))

    def test_program_bytes_do_not_embed_human_schema_labels(self):
        _, program = self.make_program()
        raw = encode_program(program)
        for label in (
            b"program_ref", b"instruction_ref", b"depends_on", b"effect_mask",
            b"upsert_axis", b"upsert_relation", b"refresh_topology",
        ):
            self.assertNotIn(label, raw)

    def test_effect_mask_is_canonical_for_opcode(self):
        self.assertEqual(operator_effect_mask(operation_opcode("upsert_axis")), EFFECT_AXIS)
        self.assertEqual(
            operator_effect_mask(operation_opcode("upsert_relation")),
            EFFECT_RELATION | EFFECT_TOPOLOGY,
        )
        with self.assertRaisesRegex(DSRValidationError, "PROGRAM_EFFECT_MASK_MISMATCH"):
            NativeInstruction(
                1,
                operation_opcode("upsert_relation"),
                EFFECT_RELATION,
                (),
                b"x",
            )

    def test_program_rejects_unknown_dependency_and_cycles(self):
        registry, program_ref, i1, i2, i3 = self.make_registry()
        with self.assertRaisesRegex(DSRValidationError, "PROGRAM_DEPENDENCY_UNKNOWN"):
            NativeProgram(
                registry.revision, registry.prefix_hash(), program_ref, 0, "22" * 32,
                (NativeInstruction(i1, operation_opcode("upsert_axis"), EFFECT_AXIS, (999,), b"x"),),
            )
        with self.assertRaisesRegex(DSRValidationError, "PROGRAM_DEPENDENCY_CYCLE"):
            NativeProgram(
                registry.revision, registry.prefix_hash(), program_ref, 0, "22" * 32,
                (
                    NativeInstruction(i1, operation_opcode("upsert_axis"), EFFECT_AXIS, (i2,), b"x"),
                    NativeInstruction(i2, operation_opcode("upsert_axis"), EFFECT_AXIS, (i1,), b"y"),
                ),
            )


if __name__ == "__main__":
    unittest.main()
