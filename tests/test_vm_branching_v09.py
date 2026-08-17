import unittest

from isql_dsr.machine import NativeSemanticState, registered_state_hash
from isql_dsr.model import PointValue
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace
from isql_dsr.vm import (
    BIND_EXACT,
    EXECUTION_FAILED,
    EXECUTION_SUCCESS,
    NativeVMProgram,
    VMInstruction,
    VMStateBinding,
    VM_OP_CONST,
    VM_OP_LT,
    encode_register_binary_payload,
    encode_register_const_payload,
    execute_vm_transaction,
    register_guard_initialized,
    register_guard_value_eq,
    vm_execution_batches,
)


def fixture():
    r = NativeSymbolRegistry(); x = {}
    rows = [
        (SymbolNamespace.PROGRAM_ID, 'program:branch-v09', 'program'),
        (SymbolNamespace.INSTRUCTION_ID, 'i:cmp', 'cmp_i'),
        (SymbolNamespace.INSTRUCTION_ID, 'i:true', 'true_i'),
        (SymbolNamespace.INSTRUCTION_ID, 'i:false', 'false_i'),
        (SymbolNamespace.INSTRUCTION_ID, 'i:after', 'after_i'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:v09', 'slot'),
        (SymbolNamespace.IDENTITY, 'state:v09', 'identity'),
        (SymbolNamespace.REGISTER_ID, 'r:left', 'left'),
        (SymbolNamespace.REGISTER_ID, 'r:right', 'right'),
        (SymbolNamespace.REGISTER_ID, 'r:cond', 'cond'),
        (SymbolNamespace.REGISTER_ID, 'r:out', 'out'),
        (SymbolNamespace.REGISTER_ID, 'r:after', 'after'),
        (SymbolNamespace.REGISTER_ID, 'r:missing', 'missing'),
    ]
    for ns, text, key in rows:
        r, x[key] = r.intern_text(ns, text)
    state = NativeSemanticState(r.revision, r.prefix_hash(), x['identity'], 0)
    return r, x, state


def branch_program(r, x, state):
    cmp_i = VMInstruction(
        x['cmp_i'], VM_OP_LT, 0, 0, x['slot'], (), (),
        encode_register_binary_payload(x['left'], x['right'], x['cond']),
    )
    true_i = VMInstruction(
        x['true_i'], VM_OP_CONST, 0, 0, x['slot'], (x['cmp_i'],), (),
        encode_register_const_payload(x['out'], PointValue(10)), (), x['cond'], True,
    )
    false_i = VMInstruction(
        x['false_i'], VM_OP_CONST, 0, 0, x['slot'], (x['cmp_i'],), (),
        encode_register_const_payload(x['out'], PointValue(20)), (), x['cond'], False,
    )
    return NativeVMProgram(
        r.revision, r.prefix_hash(), x['program'], 0,
        (VMStateBinding(x['slot'], BIND_EXACT, state.revision, registered_state_hash(state)),),
        (cmp_i, true_i, false_i), (x['left'], x['right']), (x['out'],),
    )


class VMBranchingV09Tests(unittest.TestCase):
    def test_boolean_predicate_selects_true_or_false_path(self):
        r, x, state = fixture(); p = branch_program(r, x, state)
        result = execute_vm_transaction(
            {x['slot']: state}, p, r,
            arguments={x['left']: PointValue(2), x['right']: PointValue(3)},
        )
        self.assertEqual(result.receipt.status, EXECUTION_SUCCESS)
        self.assertEqual(result.returns, ((x['out'], PointValue(10)),))
        result = execute_vm_transaction(
            {x['slot']: state}, p, r,
            arguments={x['left']: PointValue(5), x['right']: PointValue(3)},
        )
        self.assertEqual(result.returns, ((x['out'], PointValue(20)),))

    def test_predicate_register_missing_fails_closed(self):
        r, x, state = fixture()
        item = VMInstruction(
            x['true_i'], VM_OP_CONST, 0, 0, x['slot'], (), (),
            encode_register_const_payload(x['out'], PointValue(1)), (), x['missing'], True,
        )
        p = NativeVMProgram(
            r.revision, r.prefix_hash(), x['program'], 0,
            (VMStateBinding(x['slot'], BIND_EXACT, state.revision, registered_state_hash(state)),),
            (item,), (), (x['out'],),
        )
        result = execute_vm_transaction({x['slot']: state}, p, r)
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code, 'VM_PREDICATE_REGISTER_UNINITIALIZED')

    def test_predicate_register_must_be_boolean_point(self):
        r, x, state = fixture()
        item = VMInstruction(
            x['true_i'], VM_OP_CONST, 0, 0, x['slot'], (), (),
            encode_register_const_payload(x['out'], PointValue(1)), (), x['left'], True,
        )
        p = NativeVMProgram(
            r.revision, r.prefix_hash(), x['program'], 0,
            (VMStateBinding(x['slot'], BIND_EXACT, state.revision, registered_state_hash(state)),),
            (item,), (x['left'],), (x['out'],),
        )
        result = execute_vm_transaction({x['slot']: state}, p, r, arguments={x['left']: PointValue(7)})
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code, 'VM_PREDICATE_BOOL_REQUIRED')

    def test_register_guard_false_aborts_transaction(self):
        r, x, state = fixture()
        item = VMInstruction(
            x['true_i'], VM_OP_CONST, 0, 0, x['slot'], (), (),
            encode_register_const_payload(x['out'], PointValue(1)),
            (register_guard_value_eq(x['left'], PointValue(9)),),
        )
        p = NativeVMProgram(
            r.revision, r.prefix_hash(), x['program'], 0,
            (VMStateBinding(x['slot'], BIND_EXACT, state.revision, registered_state_hash(state)),),
            (item,), (x['left'],), (x['out'],),
        )
        result = execute_vm_transaction({x['slot']: state}, p, r, arguments={x['left']: PointValue(8)})
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code, 'VM_REGISTER_GUARD_FAILED')
        self.assertEqual(result.returns, ())

    def test_skipped_instruction_still_completes_structural_dependency(self):
        r, x, state = fixture()
        # Condition is false, so true_i is skipped. after_i depends on true_i but is unconditional.
        true_i = VMInstruction(
            x['true_i'], VM_OP_CONST, 0, 0, x['slot'], (), (),
            encode_register_const_payload(x['out'], PointValue(10)), (), x['left'], True,
        )
        after_i = VMInstruction(
            x['after_i'], VM_OP_CONST, 0, 0, x['slot'], (x['true_i'],), (),
            encode_register_const_payload(x['after'], PointValue(99)),
        )
        p = NativeVMProgram(
            r.revision, r.prefix_hash(), x['program'], 0,
            (VMStateBinding(x['slot'], BIND_EXACT, state.revision, registered_state_hash(state)),),
            (true_i, after_i), (x['left'],), (x['after'],),
        )
        result = execute_vm_transaction({x['slot']: state}, p, r, arguments={x['left']: PointValue(False)})
        self.assertEqual(result.receipt.status, EXECUTION_SUCCESS)
        self.assertEqual(result.returns, ((x['after'], PointValue(99)),))
        self.assertNotIn((x['program'], x['true_i']), result.receipt.execution_trace)
        self.assertIn((x['program'], x['after_i']), result.receipt.execution_trace)

    def test_predicate_and_register_guard_reads_are_scheduler_hazards(self):
        r, x, state = fixture()
        writer = VMInstruction(
            x['cmp_i'], VM_OP_CONST, 0, 0, x['slot'], (), (),
            encode_register_const_payload(x['cond'], PointValue(True)),
        )
        predicated = VMInstruction(
            x['true_i'], VM_OP_CONST, 0, 0, x['slot'], (), (),
            encode_register_const_payload(x['out'], PointValue(1)),
            (register_guard_initialized(x['cond']),), x['cond'], True,
        )
        p = NativeVMProgram(
            r.revision, r.prefix_hash(), x['program'], 0,
            (VMStateBinding(x['slot'], BIND_EXACT, state.revision, registered_state_hash(state)),),
            (writer, predicated), (), (x['out'],),
        )
        self.assertEqual(len(vm_execution_batches(p)), 2)


if __name__ == '__main__': unittest.main()
