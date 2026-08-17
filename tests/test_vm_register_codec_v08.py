import unittest
from pathlib import Path

from isql_dsr.errors import DSRValidationError
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace, decode_registry
from isql_dsr.vm import (
    BIND_DYNAMIC,
    CAP_AXIS,
    NativeVMProgram,
    VMInstruction,
    VMScopedCapability,
    VMStateBinding,
    decode_vm_program,
    encode_vm_program,
)
from isql_dsr.native import encode_uvarint, operation_opcode
from isql_dsr.program import EFFECT_AXIS

ZERO = "0" * 64


def fixture():
    r = NativeSymbolRegistry(); x = {}
    rows = [
        (SymbolNamespace.PROGRAM_ID, "program:v08", "program"),
        (SymbolNamespace.INSTRUCTION_ID, "instruction:1", "i1"),
        (SymbolNamespace.STATE_SLOT_ID, "slot:a", "slot"),
        (SymbolNamespace.AXIS_KEY, "risk", "axis"),
        (SymbolNamespace.REGISTER_ID, "register:arg0", "arg"),
        (SymbolNamespace.REGISTER_ID, "register:return0", "ret"),
    ]
    for ns, text, key in rows:
        r, x[key] = r.intern_text(ns, text)
    return r, x


class VMRegisterCodecV08Tests(unittest.TestCase):
    def test_register_namespace_is_distinct(self):
        r = NativeSymbolRegistry()
        r, atom = r.intern_text(SymbolNamespace.ATOM, "x")
        r, reg = r.intern_text(SymbolNamespace.REGISTER_ID, "x")
        self.assertNotEqual(atom, reg)
        self.assertEqual(r.resolve_text(reg, SymbolNamespace.REGISTER_ID), "x")
        with self.assertRaises(DSRValidationError):
            r.resolve(reg, SymbolNamespace.ATOM)

    def test_v08_program_round_trip_carries_registers_and_scoped_capabilities(self):
        r, x = fixture()
        instr = VMInstruction(
            x["i1"], operation_opcode("remove_axis"), EFFECT_AXIS, CAP_AXIS,
            x["slot"], (), (), encode_uvarint(x["axis"]),
        )
        program = NativeVMProgram(
            r.revision, r.prefix_hash(), x["program"], CAP_AXIS,
            (VMStateBinding(x["slot"], BIND_DYNAMIC, 0, ZERO),),
            (instr,),
            (x["arg"],),
            (x["ret"],),
            (VMScopedCapability(x["slot"], CAP_AXIS),),
        )
        raw = encode_vm_program(program)
        decoded = decode_vm_program(raw, r)
        self.assertEqual(decoded, program)
        self.assertEqual(encode_vm_program(decoded), raw)
        for label in (b"argument_registers", b"return_registers", b"scoped_capabilities", b"register"):
            self.assertNotIn(label, raw)

    def test_duplicate_register_declaration_is_rejected(self):
        r, x = fixture()
        instr = VMInstruction(
            x["i1"], operation_opcode("remove_axis"), EFFECT_AXIS, CAP_AXIS,
            x["slot"], (), (), encode_uvarint(x["axis"]),
        )
        with self.assertRaises(DSRValidationError):
            NativeVMProgram(
                r.revision, r.prefix_hash(), x["program"], CAP_AXIS,
                (VMStateBinding(x["slot"], BIND_DYNAMIC, 0, ZERO),),
                (instr,), (x["arg"], x["arg"]), (), (),
            )

    def test_noncanonical_scoped_capability_is_rejected(self):
        r, x = fixture()
        instr = VMInstruction(
            x["i1"], operation_opcode("remove_axis"), EFFECT_AXIS, CAP_AXIS,
            x["slot"], (), (), encode_uvarint(x["axis"]),
        )
        with self.assertRaises(DSRValidationError):
            NativeVMProgram(
                r.revision, r.prefix_hash(), x["program"], CAP_AXIS,
                (VMStateBinding(x["slot"], BIND_DYNAMIC, 0, ZERO),),
                (instr,), (), (), (VMScopedCapability(x["slot"], 0),),
            )

    def test_legacy_v07_program_can_still_be_decoded(self):
        base = Path(__file__).resolve().parents[1] / "examples" / "v0.7"
        registry = decode_registry((base / "symbols.isqlr").read_bytes())
        program = decode_vm_program((base / "root-commit.isqlp").read_bytes(), registry)
        self.assertEqual(program.argument_registers, ())
        self.assertEqual(program.return_registers, ())
        self.assertTrue(program.scoped_capabilities)


if __name__ == "__main__":
    unittest.main()
