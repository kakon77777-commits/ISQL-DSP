import unittest

from isql_dsr.machine import NativeAxis, NativeSemanticState, registered_state_hash
from isql_dsr.model import PointValue
from isql_dsr.native import encode_uvarint, operation_opcode
from isql_dsr.program import EFFECT_AXIS
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace
from isql_dsr.vm import (
    BIND_DYNAMIC,
    BIND_EXACT,
    CAP_AXIS,
    CAP_AXIS_READ,
    CAP_CALL,
    EXECUTION_FAILED,
    EXECUTION_SUCCESS,
    NativeVMProgram,
    VMInstruction,
    VMScopedCapability,
    VMStateBinding,
    VM_OP_CALL,
    VM_OP_LOAD_AXIS,
    VM_OP_RETURN,
    VM_OP_STORE_AXIS,
    encode_load_axis_payload,
    encode_store_axis_payload,
    encode_vm_call_payload,
    execute_vm_transaction,
)

ZERO = '0' * 64


def fixture():
    r = NativeSymbolRegistry(); x = {}
    rows = [
        (SymbolNamespace.PROGRAM_ID, 'program:root', 'root'),
        (SymbolNamespace.PROGRAM_ID, 'program:child', 'child'),
        (SymbolNamespace.INSTRUCTION_ID, 'root:call', 'root_call'),
        (SymbolNamespace.INSTRUCTION_ID, 'child:load', 'child_load'),
        (SymbolNamespace.INSTRUCTION_ID, 'child:store', 'child_store'),
        (SymbolNamespace.INSTRUCTION_ID, 'child:fail', 'child_fail'),
        (SymbolNamespace.INSTRUCTION_ID, 'child:return', 'child_return'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:a', 'slot_a'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:b', 'slot_b'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:child-a', 'child_a'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:child-b', 'child_b'),
        (SymbolNamespace.IDENTITY, 'state:a', 'id_a'),
        (SymbolNamespace.IDENTITY, 'state:b', 'id_b'),
        (SymbolNamespace.AXIS_KEY, 'risk', 'axis'),
        (SymbolNamespace.AXIS_KEY, 'missing', 'missing_axis'),
        (SymbolNamespace.AXIS_DOMAIN, 'ordinal', 'domain'),
        (SymbolNamespace.REGISTER_ID, 'register:root-arg', 'root_arg'),
        (SymbolNamespace.REGISTER_ID, 'register:root-ret', 'root_ret'),
        (SymbolNamespace.REGISTER_ID, 'register:child-arg', 'child_arg'),
        (SymbolNamespace.REGISTER_ID, 'register:child-ret', 'child_ret'),
    ]
    for ns, text, key in rows:
        r, x[key] = r.intern_text(ns, text)
    axis = NativeAxis(x['axis'], x['domain'], PointValue(5), 0.0, 1)
    a = NativeSemanticState(r.revision, r.prefix_hash(), x['id_a'], 0, axes=(axis,))
    b = NativeSemanticState(r.revision, r.prefix_hash(), x['id_b'], 0)
    return r, x, a, b


def child_program(r, x, fail_late=False):
    load = VMInstruction(
        x['child_load'], VM_OP_LOAD_AXIS, 0, CAP_AXIS_READ, x['child_a'], (), (),
        encode_load_axis_payload(x['axis'], x['child_ret']),
    )
    store = VMInstruction(
        x['child_store'], VM_OP_STORE_AXIS, CAP_AXIS, CAP_AXIS, x['child_b'], (x['child_load'],), (),
        encode_store_axis_payload(x['axis'], x['domain'], x['child_arg'], 0.0, 2),
    )
    rows = [load, store]
    last = x['child_store']
    if fail_late:
        failure = VMInstruction(
            x['child_fail'], operation_opcode('remove_axis'), EFFECT_AXIS, CAP_AXIS,
            x['child_b'], (x['child_store'],), (), encode_uvarint(x['missing_axis']),
        )
        rows.append(failure); last = x['child_fail']
    ret = VMInstruction(x['child_return'], VM_OP_RETURN, 0, 0, x['child_b'], (last,), (), b'')
    rows.append(ret)
    return NativeVMProgram(
        r.revision, r.prefix_hash(), x['child'], CAP_AXIS_READ | CAP_AXIS,
        (
            VMStateBinding(x['child_a'], BIND_DYNAMIC, 0, ZERO),
            VMStateBinding(x['child_b'], BIND_DYNAMIC, 0, ZERO),
        ),
        tuple(rows), (x['child_arg'],), (x['child_ret'],),
        (
            VMScopedCapability(x['child_a'], CAP_AXIS_READ),
            VMScopedCapability(x['child_b'], CAP_AXIS),
        ),
    )


def root_program(r, x, a, b, malformed=False):
    aliases = ((x['child_a'], x['slot_a']),) if malformed else (
        (x['child_a'], x['slot_a']), (x['child_b'], x['slot_b'])
    )
    payload = encode_vm_call_payload(
        x['child'], aliases, (x['root_arg'],), (x['root_ret'],)
    )
    call = VMInstruction(x['root_call'], VM_OP_CALL, 0, CAP_CALL, x['slot_a'], (), (), payload)
    return NativeVMProgram(
        r.revision, r.prefix_hash(), x['root'], CAP_CALL,
        (
            VMStateBinding(x['slot_a'], BIND_EXACT, a.revision, registered_state_hash(a)),
            VMStateBinding(x['slot_b'], BIND_EXACT, b.revision, registered_state_hash(b)),
        ),
        (call,), (x['root_arg'],), (x['root_ret'],),
        (
            VMScopedCapability(x['slot_a'], CAP_CALL),
            VMScopedCapability(x['slot_b'], 0),
        ),
    )


class VMCallRegistersV08Tests(unittest.TestCase):
    def test_multi_slot_call_passes_arguments_and_returns(self):
        r, x, a, b = fixture()
        child = child_program(r, x)
        root = root_program(r, x, a, b)
        result = execute_vm_transaction(
            {x['slot_a']: a, x['slot_b']: b}, root, r,
            {x['child']: child},
            arguments={x['root_arg']: PointValue(9)},
            granted_scoped_capabilities={
                x['slot_a']: CAP_CALL | CAP_AXIS_READ,
                x['slot_b']: CAP_AXIS,
            },
        )
        self.assertEqual(result.receipt.status, EXECUTION_SUCCESS)
        self.assertEqual(result.states[x['slot_b']].axes[0].value, PointValue(9))
        self.assertEqual(result.returns, ((x['root_ret'], PointValue(5)),))

    def test_call_mapping_mismatch_fails_without_mutation(self):
        r, x, a, b = fixture()
        child = child_program(r, x)
        root = root_program(r, x, a, b, malformed=True)
        result = execute_vm_transaction(
            {x['slot_a']: a, x['slot_b']: b}, root, r,
            {x['child']: child},
            arguments={x['root_arg']: PointValue(9)},
            granted_scoped_capabilities={x['slot_a']: CAP_CALL | CAP_AXIS_READ, x['slot_b']: CAP_AXIS},
        )
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code, 'VM_CALL_MAPPING_INVALID')
        self.assertEqual(registered_state_hash(result.states[x['slot_a']]), registered_state_hash(a))
        self.assertEqual(registered_state_hash(result.states[x['slot_b']]), registered_state_hash(b))

    def test_late_callee_failure_rolls_back_all_slots_and_returns(self):
        r, x, a, b = fixture()
        child = child_program(r, x, fail_late=True)
        root = root_program(r, x, a, b)
        result = execute_vm_transaction(
            {x['slot_a']: a, x['slot_b']: b}, root, r,
            {x['child']: child},
            arguments={x['root_arg']: PointValue(9)},
            granted_scoped_capabilities={x['slot_a']: CAP_CALL | CAP_AXIS_READ, x['slot_b']: CAP_AXIS},
        )
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code, 'AXIS_NOT_FOUND')
        self.assertEqual(result.returns, ())
        self.assertEqual(registered_state_hash(result.states[x['slot_a']]), registered_state_hash(a))
        self.assertEqual(registered_state_hash(result.states[x['slot_b']]), registered_state_hash(b))


if __name__ == '__main__': unittest.main()
