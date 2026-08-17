import unittest

from isql_dsr.linker import link_vm_programs
from isql_dsr.machine import NativeSemanticState, registered_state_hash
from isql_dsr.model import PointValue
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace
from isql_dsr.vm import (
    BIND_EXACT,
    EXECUTION_SUCCESS,
    NativeVMProgram,
    VMInstruction,
    VMStateBinding,
    VM_OP_ADD,
    VM_OP_CONST,
    VM_OP_MUL,
    VM_OP_RETURN,
    encode_register_binary_payload,
    encode_register_const_payload,
    encode_vm_program,
    execute_vm_transaction,
)


def fixture():
    r = NativeSymbolRegistry(); x = {}
    rows = [
        (SymbolNamespace.PROGRAM_ID, 'program:module-a', 'pa'),
        (SymbolNamespace.PROGRAM_ID, 'program:module-b', 'pb'),
        (SymbolNamespace.PROGRAM_ID, 'program:linked', 'pl'),
        (SymbolNamespace.INSTRUCTION_ID, 'i:const-a', 'ia'),
        (SymbolNamespace.INSTRUCTION_ID, 'i:return-a', 'ira'),
        (SymbolNamespace.INSTRUCTION_ID, 'i:mul-b', 'ib'),
        (SymbolNamespace.INSTRUCTION_ID, 'i:return-b', 'irb'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:v09', 'slot'),
        (SymbolNamespace.IDENTITY, 'state:v09', 'identity'),
        (SymbolNamespace.REGISTER_ID, 'r:x', 'x'),
        (SymbolNamespace.REGISTER_ID, 'r:y', 'y'),
        (SymbolNamespace.REGISTER_ID, 'r:z', 'z'),
    ]
    for ns, text, key in rows:
        r, x[key] = r.intern_text(ns, text)
    s = NativeSemanticState(r.revision, r.prefix_hash(), x['identity'], 0)
    bind = VMStateBinding(x['slot'], BIND_EXACT, s.revision, registered_state_hash(s))
    a = NativeVMProgram(
        r.revision, r.prefix_hash(), x['pa'], 0, (bind,),
        (
            VMInstruction(x['ia'], VM_OP_CONST, 0, 0, x['slot'], (), (), encode_register_const_payload(x['x'], PointValue(4))),
            VMInstruction(x['ira'], VM_OP_RETURN, 0, 0, x['slot'], (x['ia'],), (), b''),
        ), (), (x['x'],),
    )
    b = NativeVMProgram(
        r.revision, r.prefix_hash(), x['pb'], 0, (bind,),
        (
            VMInstruction(x['ib'], VM_OP_MUL, 0, 0, x['slot'], (), (), encode_register_binary_payload(x['x'], x['y'], x['z'])),
            VMInstruction(x['irb'], VM_OP_RETURN, 0, 0, x['slot'], (x['ib'],), (), b''),
        ), (x['x'], x['y']), (x['z'],),
    )
    return r, x, s, a, b


class VMLinkerV09Tests(unittest.TestCase):
    def test_sequential_link_adds_causal_edge_and_executes_as_one_program(self):
        r, x, state, a, b = fixture()
        linked = link_vm_programs(
            r, x['pl'], (a, b), sequential=True,
            argument_registers=(x['y'],), return_registers=(x['z'],),
        )
        self.assertEqual(len(linked.instructions), 2)  # module RETURNs are stripped
        b_item = next(i for i in linked.instructions if i.instruction_ref == x['ib'])
        self.assertIn(x['ia'], b_item.depends_on)
        result = execute_vm_transaction(
            {x['slot']: state}, linked, r,
            arguments={x['y']: PointValue(3)},
        )
        self.assertEqual(result.receipt.status, EXECUTION_SUCCESS)
        self.assertEqual(result.returns, ((x['z'], PointValue(12)),))

    def test_linking_is_deterministic(self):
        r, x, _, a, b = fixture()
        left = link_vm_programs(r, x['pl'], (a, b), sequential=True, argument_registers=(x['y'],), return_registers=(x['z'],))
        right = link_vm_programs(r, x['pl'], (a, b), sequential=True, argument_registers=(x['y'],), return_registers=(x['z'],))
        self.assertEqual(encode_vm_program(left), encode_vm_program(right))

    def test_duplicate_instruction_ref_is_rejected(self):
        r, x, state, a, _ = fixture()
        bind = VMStateBinding(x['slot'], BIND_EXACT, state.revision, registered_state_hash(state))
        dup = NativeVMProgram(
            r.revision, r.prefix_hash(), x['pb'], 0, (bind,),
            (VMInstruction(x['ia'], VM_OP_CONST, 0, 0, x['slot'], (), (), encode_register_const_payload(x['z'], PointValue(1))),),
        )
        with self.assertRaisesRegex(Exception, 'VM_LINK_INSTRUCTION_DUPLICATE'):
            link_vm_programs(r, x['pl'], (a, dup))

    def test_binding_conflict_is_rejected(self):
        r, x, state, a, _ = fixture()
        changed = NativeSemanticState(r.revision, r.prefix_hash(), x['identity'], 1)
        bind = VMStateBinding(x['slot'], BIND_EXACT, changed.revision, registered_state_hash(changed))
        other = NativeVMProgram(
            r.revision, r.prefix_hash(), x['pb'], 0, (bind,),
            (VMInstruction(x['ib'], VM_OP_CONST, 0, 0, x['slot'], (), (), encode_register_const_payload(x['z'], PointValue(1))),),
        )
        with self.assertRaisesRegex(Exception, 'VM_LINK_BINDING_CONFLICT'):
            link_vm_programs(r, x['pl'], (a, other))

    def test_registry_pin_mismatch_is_rejected(self):
        r, x, _, a, b = fixture()
        r2, _ = r.intern_text(SymbolNamespace.REGISTER_ID, 'r:new')
        b2 = NativeVMProgram(r2.revision, r2.prefix_hash(), b.program_ref, b.capability_mask, b.bindings, b.instructions, b.argument_registers, b.return_registers)
        with self.assertRaisesRegex(Exception, 'VM_LINK_REGISTRY_MISMATCH'):
            link_vm_programs(r2, x['pl'], (a, b2))


if __name__ == '__main__': unittest.main()
