import unittest

from isql_dsr.machine import NativeSemanticState, registered_state_hash
from isql_dsr.model import IntervalValue, PointValue
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace
from isql_dsr.vm import (
    BIND_EXACT,
    EXECUTION_FAILED,
    EXECUTION_SUCCESS,
    NativeVMProgram,
    VMInstruction,
    VMStateBinding,
    VM_OP_ADD,
    VM_OP_CONST,
    VM_OP_DIV,
    VM_OP_EQ,
    VM_OP_LE,
    VM_OP_LT,
    VM_OP_MOVE,
    VM_OP_MUL,
    VM_OP_SUB,
    encode_register_binary_payload,
    encode_register_const_payload,
    encode_register_move_payload,
    execute_vm_transaction,
)


def fixture():
    r = NativeSymbolRegistry(); x = {}
    rows = [
        (SymbolNamespace.PROGRAM_ID, 'program:algebra-v09', 'program'),
        (SymbolNamespace.INSTRUCTION_ID, 'instruction:op-v09', 'i'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:v09', 'slot'),
        (SymbolNamespace.IDENTITY, 'state:v09', 'identity'),
        (SymbolNamespace.REGISTER_ID, 'register:left', 'left'),
        (SymbolNamespace.REGISTER_ID, 'register:right', 'right'),
        (SymbolNamespace.REGISTER_ID, 'register:out', 'out'),
    ]
    for ns, text, key in rows:
        r, x[key] = r.intern_text(ns, text)
    state = NativeSemanticState(r.revision, r.prefix_hash(), x['identity'], 0)
    return r, x, state


def run_op(opcode, left, right):
    r, x, state = fixture()
    item = VMInstruction(
        x['i'], opcode, 0, 0, x['slot'], (), (),
        encode_register_binary_payload(x['left'], x['right'], x['out']),
    )
    p = NativeVMProgram(
        r.revision, r.prefix_hash(), x['program'], 0,
        (VMStateBinding(x['slot'], BIND_EXACT, state.revision, registered_state_hash(state)),),
        (item,), (x['left'], x['right']), (x['out'],),
    )
    return execute_vm_transaction(
        {x['slot']: state}, p, r,
        arguments={x['left']: left, x['right']: right},
    ), x


class VMAlgebraV09Tests(unittest.TestCase):
    def test_const_and_move_use_native_semantic_values(self):
        r, x, state = fixture()
        # Need a second instruction ref and register for a canonical two-step program.
        r, i2 = r.intern_text(SymbolNamespace.INSTRUCTION_ID, 'instruction:move-v09')
        r, moved = r.intern_text(SymbolNamespace.REGISTER_ID, 'register:moved')
        state = NativeSemanticState(r.revision, r.prefix_hash(), x['identity'], 0)
        const = VMInstruction(
            x['i'], VM_OP_CONST, 0, 0, x['slot'], (), (),
            encode_register_const_payload(x['out'], PointValue(11)),
        )
        move = VMInstruction(
            i2, VM_OP_MOVE, 0, 0, x['slot'], (x['i'],), (),
            encode_register_move_payload(x['out'], moved),
        )
        p = NativeVMProgram(
            r.revision, r.prefix_hash(), x['program'], 0,
            (VMStateBinding(x['slot'], BIND_EXACT, state.revision, registered_state_hash(state)),),
            (const, move), (), (moved,),
        )
        result = execute_vm_transaction({x['slot']: state}, p, r)
        self.assertEqual(result.receipt.status, EXECUTION_SUCCESS)
        self.assertEqual(result.returns, ((moved, PointValue(11)),))

    def test_integer_addition_preserves_integer_point(self):
        result, x = run_op(VM_OP_ADD, PointValue(2), PointValue(3))
        self.assertEqual(result.receipt.status, EXECUTION_SUCCESS)
        self.assertEqual(result.returns, ((x['out'], PointValue(5)),))

    def test_mixed_numeric_multiplication_promotes_to_float(self):
        result, x = run_op(VM_OP_MUL, PointValue(2), PointValue(1.5))
        self.assertEqual(result.returns, ((x['out'], PointValue(3.0)),))

    def test_subtraction_and_division(self):
        result, x = run_op(VM_OP_SUB, PointValue(8), PointValue(3))
        self.assertEqual(result.returns, ((x['out'], PointValue(5)),))
        result, x = run_op(VM_OP_DIV, PointValue(7), PointValue(2))
        self.assertEqual(result.returns, ((x['out'], PointValue(3.5)),))

    def test_division_by_zero_rolls_back(self):
        result, _ = run_op(VM_OP_DIV, PointValue(7), PointValue(0))
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code, 'VM_DIVISION_BY_ZERO')
        self.assertEqual(result.returns, ())

    def test_bool_is_not_numeric(self):
        result, _ = run_op(VM_OP_ADD, PointValue(True), PointValue(1))
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code, 'VM_NUMERIC_TYPE_REQUIRED')

    def test_semantic_equality_can_compare_non_numeric_values(self):
        result, x = run_op(VM_OP_EQ, IntervalValue(1, 2), IntervalValue(1, 2))
        self.assertEqual(result.returns, ((x['out'], PointValue(True)),))

    def test_numeric_comparisons_return_boolean_points(self):
        result, x = run_op(VM_OP_LT, PointValue(2), PointValue(3.0))
        self.assertEqual(result.returns, ((x['out'], PointValue(True)),))
        result, x = run_op(VM_OP_LE, PointValue(3), PointValue(3))
        self.assertEqual(result.returns, ((x['out'], PointValue(True)),))


if __name__ == '__main__': unittest.main()
