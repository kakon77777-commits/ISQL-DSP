import unittest

from isql_dsr.machine import NativeAxis, NativeSemanticState, registered_state_hash
from isql_dsr.model import PointValue
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace
from isql_dsr.vm import (
    BIND_EXACT,
    CAP_AXIS,
    CAP_AXIS_READ,
    EXECUTION_FAILED,
    EXECUTION_SUCCESS,
    NativeVMProgram,
    VMInstruction,
    VMScopedCapability,
    VMStateBinding,
    VM_OP_LOAD_AXIS,
    VM_OP_RETURN,
    VM_OP_STORE_AXIS,
    encode_load_axis_payload,
    encode_store_axis_payload,
    execute_vm_transaction,
)


def fixture():
    r = NativeSymbolRegistry(); x = {}
    for ns, text, key in [
        (SymbolNamespace.PROGRAM_ID, 'program:cross-state', 'program'),
        (SymbolNamespace.INSTRUCTION_ID, 'instruction:load', 'load_i'),
        (SymbolNamespace.INSTRUCTION_ID, 'instruction:store', 'store_i'),
        (SymbolNamespace.INSTRUCTION_ID, 'instruction:return', 'return_i'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:a', 'slot_a'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:b', 'slot_b'),
        (SymbolNamespace.IDENTITY, 'state:a', 'id_a'),
        (SymbolNamespace.IDENTITY, 'state:b', 'id_b'),
        (SymbolNamespace.AXIS_KEY, 'risk', 'axis'),
        (SymbolNamespace.AXIS_DOMAIN, 'ordinal', 'domain'),
        (SymbolNamespace.REGISTER_ID, 'register:value', 'reg'),
    ]:
        r, x[key] = r.intern_text(ns, text)
    axis = NativeAxis(x['axis'], x['domain'], PointValue(5), 0.2, 3)
    a = NativeSemanticState(r.revision, r.prefix_hash(), x['id_a'], 0, axes=(axis,))
    b = NativeSemanticState(r.revision, r.prefix_hash(), x['id_b'], 0)
    return r, x, a, b


def cross_program(r, x, a, b):
    load = VMInstruction(
        x['load_i'], VM_OP_LOAD_AXIS, 0, CAP_AXIS_READ, x['slot_a'], (), (),
        encode_load_axis_payload(x['axis'], x['reg']),
    )
    store = VMInstruction(
        x['store_i'], VM_OP_STORE_AXIS, CAP_AXIS, CAP_AXIS, x['slot_b'], (x['load_i'],), (),
        encode_store_axis_payload(x['axis'], x['domain'], x['reg'], 0.1, 4),
    )
    ret = VMInstruction(x['return_i'], VM_OP_RETURN, 0, 0, x['slot_b'], (x['store_i'],), (), b'')
    return NativeVMProgram(
        r.revision, r.prefix_hash(), x['program'], CAP_AXIS_READ | CAP_AXIS,
        (
            VMStateBinding(x['slot_a'], BIND_EXACT, a.revision, registered_state_hash(a)),
            VMStateBinding(x['slot_b'], BIND_EXACT, b.revision, registered_state_hash(b)),
        ),
        (load, store, ret), (), (x['reg'],),
        (
            VMScopedCapability(x['slot_a'], CAP_AXIS_READ),
            VMScopedCapability(x['slot_b'], CAP_AXIS),
        ),
    )


class VMCrossStateV08Tests(unittest.TestCase):
    def test_load_from_a_store_to_b_and_return_register(self):
        r, x, a, b = fixture()
        p = cross_program(r, x, a, b)
        result = execute_vm_transaction(
            {x['slot_a']: a, x['slot_b']: b}, p, r,
            granted_scoped_capabilities={x['slot_a']: CAP_AXIS_READ, x['slot_b']: CAP_AXIS},
        )
        self.assertEqual(result.receipt.status, EXECUTION_SUCCESS)
        self.assertEqual(result.states[x['slot_a']].revision, 0)
        self.assertEqual(result.states[x['slot_b']].revision, 1)
        self.assertEqual(result.states[x['slot_b']].axes[0].value, PointValue(5))
        self.assertEqual(result.states[x['slot_b']].axes[0].uncertainty, 0.1)
        self.assertEqual(result.returns, ((x['reg'], PointValue(5)),))

    def test_read_only_scope_does_not_require_write_on_source(self):
        r, x, a, b = fixture()
        p = cross_program(r, x, a, b)
        result = execute_vm_transaction(
            {x['slot_a']: a, x['slot_b']: b}, p, r,
            granted_scoped_capabilities={x['slot_a']: CAP_AXIS_READ, x['slot_b']: CAP_AXIS},
        )
        self.assertEqual(result.receipt.status, EXECUTION_SUCCESS)
        self.assertEqual(registered_state_hash(result.states[x['slot_a']]), registered_state_hash(a))

    def test_destination_write_denial_rolls_back_both_states(self):
        r, x, a, b = fixture()
        p = cross_program(r, x, a, b)
        result = execute_vm_transaction(
            {x['slot_a']: a, x['slot_b']: b}, p, r,
            granted_scoped_capabilities={x['slot_a']: CAP_AXIS_READ, x['slot_b']: 0},
        )
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code, 'VM_SCOPED_CAPABILITY_DENIED')
        self.assertEqual(registered_state_hash(result.states[x['slot_a']]), registered_state_hash(a))
        self.assertEqual(registered_state_hash(result.states[x['slot_b']]), registered_state_hash(b))
        self.assertEqual(result.returns, ())

    def test_store_from_uninitialized_register_fails_atomically(self):
        r, x, a, b = fixture()
        store = VMInstruction(
            x['store_i'], VM_OP_STORE_AXIS, CAP_AXIS, CAP_AXIS, x['slot_b'], (), (),
            encode_store_axis_payload(x['axis'], x['domain'], x['reg'], 0.0, 1),
        )
        p = NativeVMProgram(
            r.revision, r.prefix_hash(), x['program'], CAP_AXIS,
            (VMStateBinding(x['slot_b'], BIND_EXACT, b.revision, registered_state_hash(b)),),
            (store,), (), (), (VMScopedCapability(x['slot_b'], CAP_AXIS),),
        )
        result = execute_vm_transaction(
            {x['slot_b']: b}, p, r,
            granted_scoped_capabilities={x['slot_b']: CAP_AXIS},
        )
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code, 'VM_REGISTER_UNINITIALIZED')
        self.assertEqual(registered_state_hash(result.states[x['slot_b']]), registered_state_hash(b))


if __name__ == '__main__': unittest.main()
