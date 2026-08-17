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
    VM_OP_RETURN,
    execute_vm_transaction,
)


def fixture():
    r = NativeSymbolRegistry(); x = {}
    for ns, text, key in [
        (SymbolNamespace.PROGRAM_ID, 'program:root-v08', 'program'),
        (SymbolNamespace.INSTRUCTION_ID, 'instruction:return', 'ret_i'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:a', 'slot'),
        (SymbolNamespace.IDENTITY, 'state:a', 'identity'),
        (SymbolNamespace.REGISTER_ID, 'register:arg', 'arg'),
        (SymbolNamespace.REGISTER_ID, 'register:return', 'ret'),
        (SymbolNamespace.REGISTER_ID, 'register:extra', 'extra'),
    ]:
        r, x[key] = r.intern_text(ns, text)
    state = NativeSemanticState(r.revision, r.prefix_hash(), x['identity'], 0)
    return r, x, state


def program(r, x, state, same_register=False):
    ret_reg = x['arg'] if same_register else x['ret']
    instruction = VMInstruction(x['ret_i'], VM_OP_RETURN, 0, 0, x['slot'], (), (), b'')
    return NativeVMProgram(
        r.revision, r.prefix_hash(), x['program'], 0,
        (VMStateBinding(x['slot'], BIND_EXACT, state.revision, registered_state_hash(state)),),
        (instruction,),
        (x['arg'],),
        (ret_reg,),
    )


class VMRegisterRuntimeV08Tests(unittest.TestCase):
    def test_root_argument_can_be_returned_without_human_projection(self):
        r, x, state = fixture()
        p = program(r, x, state, same_register=True)
        value = PointValue(7)
        result = execute_vm_transaction({x['slot']: state}, p, r, arguments={x['arg']: value})
        self.assertEqual(result.receipt.status, EXECUTION_SUCCESS)
        self.assertEqual(result.returns, ((x['arg'], value),))
        self.assertEqual(registered_state_hash(result.states[x['slot']]), registered_state_hash(state))

    def test_missing_argument_fails_atomically_and_exposes_no_returns(self):
        r, x, state = fixture()
        p = program(r, x, state, same_register=True)
        result = execute_vm_transaction({x['slot']: state}, p, r, arguments={})
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code, 'VM_ARGUMENT_MISSING')
        self.assertEqual(result.returns, ())
        self.assertEqual(registered_state_hash(result.states[x['slot']]), registered_state_hash(state))

    def test_undeclared_argument_fails_atomically(self):
        r, x, state = fixture()
        p = program(r, x, state, same_register=True)
        result = execute_vm_transaction(
            {x['slot']: state}, p, r,
            arguments={x['arg']: PointValue(1), x['extra']: PointValue(2)},
        )
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code, 'VM_ARGUMENT_UNDECLARED')
        self.assertEqual(result.returns, ())

    def test_uninitialized_declared_return_fails_and_rolls_back(self):
        r, x, state = fixture()
        p = program(r, x, state, same_register=False)
        result = execute_vm_transaction({x['slot']: state}, p, r, arguments={x['arg']: PointValue(1)})
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code, 'VM_RETURN_REGISTER_UNINITIALIZED')
        self.assertEqual(result.returns, ())
        self.assertEqual(registered_state_hash(result.states[x['slot']]), registered_state_hash(state))


if __name__ == '__main__': unittest.main()
