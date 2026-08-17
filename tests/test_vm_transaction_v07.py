import unittest

from isql_dsr.machine import NativeAxis, NativeSemanticState, registered_state_hash
from isql_dsr.model import PointValue
from isql_dsr.native import encode_uvarint, operation_opcode
from isql_dsr.program import EFFECT_AXIS
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace
from isql_dsr.vm import (
    ALL_CAPABILITIES, BIND_DYNAMIC, BIND_EXACT, CAP_AXIS, CAP_CALL,
    EXECUTION_FAILED, EXECUTION_SUCCESS, GUARD_AXIS_ABSENT, GUARD_AXIS_PRESENT,
    NativeGuard, NativeVMProgram, VMInstruction, VMStateBinding,
    VM_OP_CALL, VM_OP_RETURN, execute_vm_transaction,
)

ZERO = '0' * 64


def setup_fixture():
    r = NativeSymbolRegistry(); refs = {}
    items = [
        (SymbolNamespace.PROGRAM_ID, 'program:root', 'root'),
        (SymbolNamespace.PROGRAM_ID, 'program:child', 'child'),
        (SymbolNamespace.INSTRUCTION_ID, 'root:call', 'root_call'),
        (SymbolNamespace.INSTRUCTION_ID, 'root:remove-b', 'root_remove'),
        (SymbolNamespace.INSTRUCTION_ID, 'child:remove-a', 'child_remove'),
        (SymbolNamespace.INSTRUCTION_ID, 'child:return', 'child_return'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:a', 'slot_a'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:b', 'slot_b'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:callee', 'slot_callee'),
        (SymbolNamespace.IDENTITY, 'state:a', 'id_a'),
        (SymbolNamespace.IDENTITY, 'state:b', 'id_b'),
        (SymbolNamespace.AXIS_KEY, 'risk', 'axis'),
        (SymbolNamespace.AXIS_DOMAIN, 'ordinal', 'domain'),
    ]
    for ns, text, key in items:
        r, refs[key] = r.intern_text(ns, text)
    axis = NativeAxis(refs['axis'], refs['domain'], PointValue(5), 0.0, 1)
    a = NativeSemanticState(r.revision, r.prefix_hash(), refs['id_a'], 0, axes=(axis,))
    b = NativeSemanticState(r.revision, r.prefix_hash(), refs['id_b'], 0, axes=(axis,))
    return r, refs, a, b


def child_program(r, x):
    remove = VMInstruction(x['child_remove'], operation_opcode('remove_axis'), EFFECT_AXIS, CAP_AXIS,
                           x['slot_callee'], (), (), encode_uvarint(x['axis']))
    ret = VMInstruction(x['child_return'], VM_OP_RETURN, 0, 0, x['slot_callee'],
                        (x['child_remove'],), (), b'')
    return NativeVMProgram(r.revision, r.prefix_hash(), x['child'], CAP_AXIS,
        (VMStateBinding(x['slot_callee'], BIND_DYNAMIC, 0, ZERO),), (remove, ret))


def root_program(r, x, a, b, guard_type=GUARD_AXIS_PRESENT):
    call = VMInstruction(x['root_call'], VM_OP_CALL, 0, CAP_CALL, x['slot_a'], (), (), encode_uvarint(x['child']))
    guard = NativeGuard(guard_type, encode_uvarint(x['axis']))
    remove_b = VMInstruction(x['root_remove'], operation_opcode('remove_axis'), EFFECT_AXIS, CAP_AXIS,
                             x['slot_b'], (x['root_call'],), (guard,), encode_uvarint(x['axis']))
    return NativeVMProgram(r.revision, r.prefix_hash(), x['root'], CAP_CALL | CAP_AXIS,
        (
            VMStateBinding(x['slot_a'], BIND_EXACT, a.revision, registered_state_hash(a)),
            VMStateBinding(x['slot_b'], BIND_EXACT, b.revision, registered_state_hash(b)),
        ), (call, remove_b))


class VMTransactionV07Tests(unittest.TestCase):
    def test_two_state_transaction_commits_only_after_subprogram_and_root_succeed(self):
        r, x, a, b = setup_fixture()
        child = child_program(r, x)
        root = root_program(r, x, a, b)
        result = execute_vm_transaction(
            {x['slot_a']: a, x['slot_b']: b}, root, r, {x['child']: child}, ALL_CAPABILITIES
        )
        self.assertEqual(result.receipt.status, EXECUTION_SUCCESS)
        self.assertEqual(result.states[x['slot_a']].axes, ())
        self.assertEqual(result.states[x['slot_b']].axes, ())
        self.assertEqual(result.states[x['slot_a']].revision, 1)
        self.assertEqual(result.states[x['slot_b']].revision, 1)
        self.assertEqual(result.receipt.base_hashes[0][0], x['slot_a'])
        self.assertIn((x['child'], x['child_remove']), result.receipt.execution_trace)

    def test_late_guard_failure_rolls_back_both_states(self):
        r, x, a, b = setup_fixture()
        child = child_program(r, x)
        root = root_program(r, x, a, b, GUARD_AXIS_ABSENT)
        result = execute_vm_transaction(
            {x['slot_a']: a, x['slot_b']: b}, root, r, {x['child']: child}, ALL_CAPABILITIES
        )
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(registered_state_hash(result.states[x['slot_a']]), registered_state_hash(a))
        self.assertEqual(registered_state_hash(result.states[x['slot_b']]), registered_state_hash(b))
        self.assertEqual(result.receipt.error_code, 'VM_GUARD_FAILED')

    def test_missing_call_capability_rolls_back_without_executing(self):
        r, x, a, b = setup_fixture()
        child = child_program(r, x)
        root = root_program(r, x, a, b)
        result = execute_vm_transaction(
            {x['slot_a']: a, x['slot_b']: b}, root, r, {x['child']: child}, CAP_AXIS
        )
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code, 'VM_CAPABILITY_DENIED')
        self.assertEqual(result.receipt.execution_trace, ())
        self.assertEqual(registered_state_hash(result.states[x['slot_a']]), registered_state_hash(a))


if __name__ == '__main__': unittest.main()
