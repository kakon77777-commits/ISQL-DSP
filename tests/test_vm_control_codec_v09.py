import unittest
from pathlib import Path

from isql_dsr.machine import NativeSemanticState, registered_state_hash
from isql_dsr.model import PointValue
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace
from isql_dsr.vm import (
    BIND_EXACT,
    NativeVMProgram,
    VMInstruction,
    VMStateBinding,
    VM_OP_RETURN,
    decode_vm_program,
    encode_vm_program,
    register_guard_initialized,
    register_guard_value_eq,
)


def fixture():
    r = NativeSymbolRegistry(); x = {}
    for ns, text, key in [
        (SymbolNamespace.PROGRAM_ID, 'program:v09-control', 'program'),
        (SymbolNamespace.INSTRUCTION_ID, 'instruction:return-v09', 'ret_i'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:v09', 'slot'),
        (SymbolNamespace.IDENTITY, 'state:v09', 'identity'),
        (SymbolNamespace.REGISTER_ID, 'register:guard', 'guard_reg'),
        (SymbolNamespace.REGISTER_ID, 'register:pred', 'pred_reg'),
    ]:
        r, x[key] = r.intern_text(ns, text)
    s = NativeSemanticState(r.revision, r.prefix_hash(), x['identity'], 0)
    return r, x, s


class VMControlCodecV09Tests(unittest.TestCase):
    def test_v09_instruction_roundtrips_register_guards_and_predicate(self):
        r, x, s = fixture()
        item = VMInstruction(
            x['ret_i'], VM_OP_RETURN, 0, 0, x['slot'], (), (), b'',
            (
                register_guard_initialized(x['guard_reg']),
                register_guard_value_eq(x['guard_reg'], PointValue(7)),
            ),
            x['pred_reg'], True,
        )
        p = NativeVMProgram(
            r.revision, r.prefix_hash(), x['program'], 0,
            (VMStateBinding(x['slot'], BIND_EXACT, s.revision, registered_state_hash(s)),),
            (item,),
        )
        raw = encode_vm_program(p)
        restored = decode_vm_program(raw, r)
        self.assertEqual(restored, p)
        self.assertEqual(encode_vm_program(restored), raw)

    def test_predicate_without_register_is_canonical_only_when_expected_true(self):
        r, x, _ = fixture()
        with self.assertRaisesRegex(Exception, 'VM_PREDICATE_EXPECTED_NONCANONICAL'):
            VMInstruction(x['ret_i'], VM_OP_RETURN, 0, 0, x['slot'], (), (), b'', (), 0, False)

    def test_legacy_v08_program_artifact_is_still_decodable(self):
        base = Path(__file__).resolve().parents[1] / 'examples' / 'v0.8'
        from isql_dsr.registry import decode_registry
        registry = decode_registry((base / 'symbols.isqlr').read_bytes())
        program = decode_vm_program((base / 'root-call.isqlp').read_bytes(), registry)
        self.assertTrue(program.argument_registers)
        self.assertTrue(program.return_registers)
        self.assertTrue(program.scoped_capabilities)
        self.assertTrue(all(not i.register_guards and i.predicate_register_ref == 0 for i in program.instructions))


if __name__ == '__main__':
    unittest.main()
