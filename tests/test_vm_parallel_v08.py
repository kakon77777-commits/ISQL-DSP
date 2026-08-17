import unittest

from isql_dsr.machine import NativeAxis, NativeSemanticState, registered_state_hash
from isql_dsr.model import PointValue
from isql_dsr.native import encode_uvarint, operation_opcode
from isql_dsr.program import EFFECT_AXIS
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace
from isql_dsr.vm import (
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
    VM_OP_STORE_AXIS,
    encode_load_axis_payload,
    encode_store_axis_payload,
    execute_vm_transaction,
    vm_execution_batches,
)


def fixture():
    r = NativeSymbolRegistry(); x = {}
    rows = [
        (SymbolNamespace.PROGRAM_ID, 'program:parallel', 'program'),
        (SymbolNamespace.PROGRAM_ID, 'program:callee', 'callee'),
        (SymbolNamespace.INSTRUCTION_ID, 'i:a', 'ia'),
        (SymbolNamespace.INSTRUCTION_ID, 'i:b', 'ib'),
        (SymbolNamespace.INSTRUCTION_ID, 'i:c', 'ic'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:a', 'sa'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:b', 'sb'),
        (SymbolNamespace.IDENTITY, 'state:a', 'ida'),
        (SymbolNamespace.IDENTITY, 'state:b', 'idb'),
        (SymbolNamespace.AXIS_KEY, 'risk', 'axis'),
        (SymbolNamespace.AXIS_KEY, 'missing', 'missing'),
        (SymbolNamespace.AXIS_DOMAIN, 'ordinal', 'domain'),
        (SymbolNamespace.REGISTER_ID, 'register:r', 'reg'),
    ]
    for ns, text, key in rows:
        r, x[key] = r.intern_text(ns, text)
    axis = NativeAxis(x['axis'], x['domain'], PointValue(5), 0.0, 1)
    a = NativeSemanticState(r.revision, r.prefix_hash(), x['ida'], 0, axes=(axis,))
    b = NativeSemanticState(r.revision, r.prefix_hash(), x['idb'], 0, axes=(axis,))
    return r, x, a, b


def remove_program(r, x, a, b, fail_b=False):
    ia = VMInstruction(x['ia'], operation_opcode('remove_axis'), EFFECT_AXIS, CAP_AXIS,
                       x['sa'], (), (), encode_uvarint(x['axis']))
    key_b = x['missing'] if fail_b else x['axis']
    ib = VMInstruction(x['ib'], operation_opcode('remove_axis'), EFFECT_AXIS, CAP_AXIS,
                       x['sb'], (), (), encode_uvarint(key_b))
    return NativeVMProgram(
        r.revision, r.prefix_hash(), x['program'], CAP_AXIS,
        (
            VMStateBinding(x['sa'], BIND_EXACT, a.revision, registered_state_hash(a)),
            VMStateBinding(x['sb'], BIND_EXACT, b.revision, registered_state_hash(b)),
        ),
        (ia, ib), (), (),
        (VMScopedCapability(x['sa'], CAP_AXIS), VMScopedCapability(x['sb'], CAP_AXIS)),
    )


class VMParallelV08Tests(unittest.TestCase):
    def test_independent_state_writes_share_a_batch(self):
        r, x, a, b = fixture()
        p = remove_program(r, x, a, b)
        self.assertEqual(vm_execution_batches(p), ((x['ia'], x['ib']),))

    def test_same_slot_writes_are_separated(self):
        r, x, a, b = fixture()
        ia = VMInstruction(x['ia'], operation_opcode('remove_axis'), EFFECT_AXIS, CAP_AXIS,
                           x['sa'], (), (), encode_uvarint(x['axis']))
        ib = VMInstruction(x['ib'], operation_opcode('remove_axis'), EFFECT_AXIS, CAP_AXIS,
                           x['sa'], (), (), encode_uvarint(x['missing']))
        p = NativeVMProgram(
            r.revision, r.prefix_hash(), x['program'], CAP_AXIS,
            (VMStateBinding(x['sa'], BIND_EXACT, a.revision, registered_state_hash(a)),),
            (ia, ib), (), (), (VMScopedCapability(x['sa'], CAP_AXIS),),
        )
        self.assertEqual(vm_execution_batches(p), ((x['ia'],), (x['ib'],)))

    def test_register_hazard_is_never_parallelized(self):
        r, x, a, b = fixture()
        load = VMInstruction(x['ia'], VM_OP_LOAD_AXIS, 0, CAP_AXIS_READ, x['sa'], (), (),
                             encode_load_axis_payload(x['axis'], x['reg']))
        store = VMInstruction(x['ib'], VM_OP_STORE_AXIS, CAP_AXIS, CAP_AXIS, x['sb'], (), (),
                              encode_store_axis_payload(x['axis'], x['domain'], x['reg'], 0.0, 1))
        p = NativeVMProgram(
            r.revision, r.prefix_hash(), x['program'], CAP_AXIS | CAP_AXIS_READ,
            (
                VMStateBinding(x['sa'], BIND_EXACT, a.revision, registered_state_hash(a)),
                VMStateBinding(x['sb'], BIND_EXACT, b.revision, registered_state_hash(b)),
            ),
            (load, store), (), (),
            (VMScopedCapability(x['sa'], CAP_AXIS_READ), VMScopedCapability(x['sb'], CAP_AXIS)),
        )
        batches = vm_execution_batches(p)
        self.assertEqual(len(batches), 2)
        self.assertNotEqual(set(batches[0]), {x['ia'], x['ib']})

    def test_call_is_always_a_singleton_batch(self):
        r, x, a, b = fixture()
        call = VMInstruction(x['ia'], VM_OP_CALL, 0, CAP_CALL, x['sa'], (), (), encode_uvarint(x['callee']))
        remove = VMInstruction(x['ib'], operation_opcode('remove_axis'), EFFECT_AXIS, CAP_AXIS,
                               x['sb'], (), (), encode_uvarint(x['axis']))
        p = NativeVMProgram(
            r.revision, r.prefix_hash(), x['program'], CAP_CALL | CAP_AXIS,
            (
                VMStateBinding(x['sa'], BIND_EXACT, a.revision, registered_state_hash(a)),
                VMStateBinding(x['sb'], BIND_EXACT, b.revision, registered_state_hash(b)),
            ), (call, remove), (), (),
            (VMScopedCapability(x['sa'], CAP_CALL), VMScopedCapability(x['sb'], CAP_AXIS)),
        )
        self.assertEqual(vm_execution_batches(p)[0], (x['ia'],))

    def test_parallel_and_serial_execution_are_bit_identical(self):
        r, x, a, b = fixture()
        p = remove_program(r, x, a, b)
        serial = execute_vm_transaction({x['sa']: a, x['sb']: b}, p, r, parallel=False)
        parallel = execute_vm_transaction({x['sa']: a, x['sb']: b}, p, r, parallel=True)
        self.assertEqual(serial.receipt.status, EXECUTION_SUCCESS)
        self.assertEqual(parallel.receipt.status, EXECUTION_SUCCESS)
        self.assertEqual(serial.receipt.final_hashes, parallel.receipt.final_hashes)
        self.assertEqual(serial.returns, parallel.returns)

    def test_parallel_worker_failure_rolls_back_entire_batch(self):
        r, x, a, b = fixture()
        p = remove_program(r, x, a, b, fail_b=True)
        result = execute_vm_transaction({x['sa']: a, x['sb']: b}, p, r, parallel=True)
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code, 'AXIS_NOT_FOUND')
        self.assertEqual(registered_state_hash(result.states[x['sa']]), registered_state_hash(a))
        self.assertEqual(registered_state_hash(result.states[x['sb']]), registered_state_hash(b))


if __name__ == '__main__': unittest.main()
