import unittest

from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace
from isql_dsr.vm import (
    BIND_DYNAMIC, BIND_EXACT, CAP_AXIS, CAP_CALL,
    GUARD_AXIS_PRESENT, NativeGuard, NativeVMProgram, VMInstruction, VMStateBinding,
    VM_OP_CALL, VM_OP_RETURN, decode_vm_program, encode_vm_program, vm_program_hash,
)
from isql_dsr.program import EFFECT_AXIS
from isql_dsr.native import operation_opcode, encode_uvarint
from isql_dsr.errors import DSRValidationError


ZERO = "0" * 64


def make_registry():
    r = NativeSymbolRegistry()
    refs = {}
    for ns, text, key in [
        (SymbolNamespace.PROGRAM_ID, "program:root", "program"),
        (SymbolNamespace.PROGRAM_ID, "program:child", "child"),
        (SymbolNamespace.INSTRUCTION_ID, "i:1", "i1"),
        (SymbolNamespace.INSTRUCTION_ID, "i:2", "i2"),
        (SymbolNamespace.STATE_SLOT_ID, "slot:a", "slot"),
        (SymbolNamespace.AXIS_KEY, "risk", "axis"),
    ]:
        r, refs[key] = r.intern_text(ns, text)
    return r, refs


class VMProgramV07Tests(unittest.TestCase):
    def test_vm_program_round_trip_is_canonical(self):
        registry, refs = make_registry()
        guard = NativeGuard(GUARD_AXIS_PRESENT, encode_uvarint(refs["axis"]))
        instr = VMInstruction(
            refs["i1"], operation_opcode("remove_axis"), EFFECT_AXIS, CAP_AXIS,
            refs["slot"], (), (guard,), encode_uvarint(refs["axis"]),
        )
        program = NativeVMProgram(
            registry.revision, registry.prefix_hash(), refs["program"], CAP_AXIS,
            (VMStateBinding(refs["slot"], BIND_EXACT, 3, "a" * 64),),
            (instr,),
        )
        raw = encode_vm_program(program)
        decoded = decode_vm_program(raw, registry)
        self.assertEqual(decoded, program)
        self.assertEqual(encode_vm_program(decoded), raw)
        self.assertEqual(len(vm_program_hash(program)), 64)
        for label in (b"program_ref", b"instruction_ref", b"depends_on", b"guards", b"capability"):
            self.assertNotIn(label, raw)

    def test_dynamic_binding_must_not_carry_exact_pin(self):
        registry, refs = make_registry()
        with self.assertRaises(DSRValidationError):
            VMStateBinding(refs["slot"], BIND_DYNAMIC, 1, "a" * 64)

    def test_call_and_return_have_machine_effect_contracts(self):
        registry, refs = make_registry()
        call = VMInstruction(refs["i1"], VM_OP_CALL, 0, CAP_CALL, refs["slot"], (), (), encode_uvarint(refs["child"]))
        ret = VMInstruction(refs["i2"], VM_OP_RETURN, 0, 0, refs["slot"], (refs["i1"],), (), b"")
        program = NativeVMProgram(
            registry.revision, registry.prefix_hash(), refs["program"], CAP_CALL,
            (VMStateBinding(refs["slot"], BIND_DYNAMIC, 0, ZERO),),
            (call, ret),
        )
        self.assertEqual(decode_vm_program(encode_vm_program(program), registry), program)

    def test_dependency_cycle_is_rejected(self):
        registry, refs = make_registry()
        i1 = VMInstruction(refs["i1"], VM_OP_RETURN, 0, 0, refs["slot"], (refs["i2"],), (), b"")
        i2 = VMInstruction(refs["i2"], VM_OP_RETURN, 0, 0, refs["slot"], (refs["i1"],), (), b"")
        with self.assertRaises(DSRValidationError):
            NativeVMProgram(registry.revision, registry.prefix_hash(), refs["program"], 0,
                            (VMStateBinding(refs["slot"], BIND_DYNAMIC, 0, ZERO),), (i1, i2))


if __name__ == "__main__":
    unittest.main()
