import unittest

from isql_dsr.errors import DSRValidationError
from isql_dsr.machine import NativeAxis, NativeSemanticState, registered_state_hash
from isql_dsr.model import PointValue
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace
from isql_dsr.vm import (
    BIND_DYNAMIC, BIND_EXACT, CAP_AXIS, CAP_AXIS_READ, CAP_CALL,
    EXECUTION_FAILED, EXECUTION_SUCCESS, NativeVMProgram, VMInstruction, VMStateBinding,
    VM_MAX_REPEAT, VM_OP_ADD, VM_OP_CONST, VM_OP_LOAD_AXIS, VM_OP_REPEAT_CALL, VM_OP_STORE_AXIS,
    encode_load_axis_payload, encode_register_binary_payload, encode_register_const_payload,
    encode_store_axis_payload, encode_vm_repeat_call_payload, execute_vm_transaction,
    guard_axis_value_eq,
)


def fixture(guard_store=False):
    r=NativeSymbolRegistry(); x={}
    rows=[
        (SymbolNamespace.PROGRAM_ID,'program:root-repeat','root'),(SymbolNamespace.PROGRAM_ID,'program:child-repeat','child'),
        (SymbolNamespace.STATE_SLOT_ID,'slot:root-repeat','slot'),(SymbolNamespace.STATE_SLOT_ID,'slot:child-repeat','child_slot'),
        (SymbolNamespace.IDENTITY,'state:repeat','identity'),(SymbolNamespace.AXIS_KEY,'counter','axis'),(SymbolNamespace.AXIS_DOMAIN,'integer','domain'),
        (SymbolNamespace.REGISTER_ID,'register:value','value'),(SymbolNamespace.REGISTER_ID,'register:one','one'),(SymbolNamespace.REGISTER_ID,'register:next','next'),
    ]
    for i in range(5): rows.append((SymbolNamespace.INSTRUCTION_ID,f'instruction:repeat:{i+1}',f'i{i+1}'))
    for ns,text,key in rows:r,x[key]=r.intern_text(ns,text)
    state=NativeSemanticState(r.revision,r.prefix_hash(),x['identity'],0,axes=(NativeAxis(x['axis'],x['domain'],PointValue(0),0.0,1),))
    load=VMInstruction(x['i2'],VM_OP_LOAD_AXIS,0,CAP_AXIS_READ,x['child_slot'],(),(),encode_load_axis_payload(x['axis'],x['value']))
    const=VMInstruction(x['i3'],VM_OP_CONST,0,0,x['child_slot'],(),(),encode_register_const_payload(x['one'],PointValue(1)))
    add=VMInstruction(x['i4'],VM_OP_ADD,0,0,x['child_slot'],(x['i2'],x['i3']),(),encode_register_binary_payload(x['value'],x['one'],x['next']))
    guards=(guard_axis_value_eq(x['axis'],PointValue(0)),) if guard_store else ()
    store=VMInstruction(x['i5'],VM_OP_STORE_AXIS,CAP_AXIS,CAP_AXIS,x['child_slot'],(x['i4'],),guards,encode_store_axis_payload(x['axis'],x['domain'],x['next'],0.0,1))
    child=NativeVMProgram(r.revision,r.prefix_hash(),x['child'],CAP_AXIS|CAP_AXIS_READ,(VMStateBinding(x['child_slot'],BIND_DYNAMIC),),(load,const,add,store))
    return r,x,state,child


def root_program(r,x,state,count):
    repeat=VMInstruction(x['i1'],VM_OP_REPEAT_CALL,0,CAP_CALL,x['slot'],(),(),encode_vm_repeat_call_payload(x['child'],count,((x['child_slot'],x['slot']),),(),()))
    return NativeVMProgram(r.revision,r.prefix_hash(),x['root'],CAP_CALL,(VMStateBinding(x['slot'],BIND_EXACT,state.revision,registered_state_hash(state)),),(repeat,))


class VMRepeatV10Tests(unittest.TestCase):
    def test_three_step_repeat_updates_state_deterministically(self):
        r,x,state,child=fixture()
        root=root_program(r,x,state,3)
        result=execute_vm_transaction({x['slot']:state},root,r,{x['child']:child})
        self.assertEqual(result.receipt.status,EXECUTION_SUCCESS)
        axis=next(a for a in result.states[x['slot']].axes if a.key_ref==x['axis'])
        self.assertEqual(axis.value,PointValue(3))
        self.assertEqual(sum(1 for program_ref,_ in result.receipt.execution_trace if program_ref==x['child']),12)

    def test_repeat_count_is_strictly_bounded(self):
        r,x,state,child=fixture()
        with self.assertRaisesRegex(DSRValidationError,'VM_REPEAT_COUNT_INVALID'):
            encode_vm_repeat_call_payload(x['child'],0,((x['child_slot'],x['slot']),),(),())
        with self.assertRaisesRegex(DSRValidationError,'VM_REPEAT_COUNT_INVALID'):
            encode_vm_repeat_call_payload(x['child'],VM_MAX_REPEAT+1,((x['child_slot'],x['slot']),),(),())

    def test_late_iteration_failure_rolls_back_every_prior_iteration(self):
        r,x,state,child=fixture(guard_store=True)
        root=root_program(r,x,state,2)
        result=execute_vm_transaction({x['slot']:state},root,r,{x['child']:child})
        self.assertEqual(result.receipt.status,EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code,'VM_GUARD_FAILED')
        self.assertEqual(registered_state_hash(result.states[x['slot']]),registered_state_hash(state))

if __name__=='__main__':unittest.main()
