import unittest

from isql_dsr.machine import NativeAxis, NativeSemanticState, registered_state_hash
from isql_dsr.model import PointValue
from isql_dsr.native import encode_uvarint, operation_opcode
from isql_dsr.optimizer import optimize_vm_program
from isql_dsr.program import EFFECT_AXIS
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace
from isql_dsr.vm import (
    BIND_EXACT, CAP_AXIS, CAP_AXIS_READ, EXECUTION_SUCCESS,
    NativeVMProgram, VMInstruction, VMStateBinding,
    VM_OP_ADD, VM_OP_CONST, VM_OP_LOAD_AXIS, VM_OP_STORE_AXIS,
    encode_load_axis_payload, encode_register_binary_payload, encode_register_const_payload,
    encode_store_axis_payload, execute_vm_transaction,
)


def fixture():
    r=NativeSymbolRegistry();x={}
    rows=[
        (SymbolNamespace.PROGRAM_ID,'program:optimizer','program'),(SymbolNamespace.STATE_SLOT_ID,'slot:optimizer','slot'),(SymbolNamespace.IDENTITY,'state:optimizer','identity'),
        (SymbolNamespace.AXIS_KEY,'a','axis_a'),(SymbolNamespace.AXIS_KEY,'b','axis_b'),(SymbolNamespace.AXIS_DOMAIN,'integer','domain'),
        (SymbolNamespace.REGISTER_ID,'register:r1','r1'),(SymbolNamespace.REGISTER_ID,'register:r2','r2'),(SymbolNamespace.REGISTER_ID,'register:r3','r3'),
    ]
    for i in range(6):rows.append((SymbolNamespace.INSTRUCTION_ID,f'instruction:opt:{i+1}',f'i{i+1}'))
    for ns,text,key in rows:r,x[key]=r.intern_text(ns,text)
    axes=(NativeAxis(x['axis_a'],x['domain'],PointValue(10),0.0,1),NativeAxis(x['axis_b'],x['domain'],PointValue(20),0.0,1))
    state=NativeSemanticState(r.revision,r.prefix_hash(),x['identity'],0,axes=axes)
    b=VMStateBinding(x['slot'],BIND_EXACT,state.revision,registered_state_hash(state))
    return r,x,state,b


class VMOptimizerV10Tests(unittest.TestCase):
    def test_constant_fold_and_dead_eliminate_to_one_const(self):
        r,x,state,b=fixture()
        c1=VMInstruction(x['i1'],VM_OP_CONST,0,0,x['slot'],(),(),encode_register_const_payload(x['r1'],PointValue(2)))
        c2=VMInstruction(x['i2'],VM_OP_CONST,0,0,x['slot'],(),(),encode_register_const_payload(x['r2'],PointValue(3)))
        add=VMInstruction(x['i3'],VM_OP_ADD,0,0,x['slot'],(x['i1'],x['i2']),(),encode_register_binary_payload(x['r1'],x['r2'],x['r3']))
        p=NativeVMProgram(r.revision,r.prefix_hash(),x['program'],0,(b,),(c1,c2,add),(),(x['r3'],))
        q=optimize_vm_program(p)
        self.assertEqual(len(q.instructions),1)
        self.assertEqual(q.instructions[0].instruction_ref,x['i3'])
        self.assertEqual(q.instructions[0].opcode,VM_OP_CONST)
        result=execute_vm_transaction({x['slot']:state},q,r)
        self.assertEqual(result.returns,((x['r3'],PointValue(5)),))

    def test_dependency_cleanup_bridges_removed_pure_instruction(self):
        r,x,state,b=fixture()
        remove_a=VMInstruction(x['i1'],operation_opcode('remove_axis'),EFFECT_AXIS,CAP_AXIS,x['slot'],(),(),encode_uvarint(x['axis_a']))
        dead=VMInstruction(x['i2'],VM_OP_CONST,0,0,x['slot'],(x['i1'],),(),encode_register_const_payload(x['r1'],PointValue(99)))
        remove_b=VMInstruction(x['i3'],operation_opcode('remove_axis'),EFFECT_AXIS,CAP_AXIS,x['slot'],(x['i2'],),(),encode_uvarint(x['axis_b']))
        p=NativeVMProgram(r.revision,r.prefix_hash(),x['program'],CAP_AXIS,(b,),(remove_a,dead,remove_b))
        q=optimize_vm_program(p)
        self.assertEqual(tuple(i.instruction_ref for i in q.instructions),(x['i1'],x['i3']))
        self.assertEqual(q.instructions[1].depends_on,(x['i1'],))

    def test_optimized_and_original_state_and_return_semantics_match(self):
        r,x,state,b=fixture()
        c1=VMInstruction(x['i1'],VM_OP_CONST,0,0,x['slot'],(),(),encode_register_const_payload(x['r1'],PointValue(4)))
        c2=VMInstruction(x['i2'],VM_OP_CONST,0,0,x['slot'],(),(),encode_register_const_payload(x['r2'],PointValue(6)))
        add=VMInstruction(x['i3'],VM_OP_ADD,0,0,x['slot'],(x['i1'],x['i2']),(),encode_register_binary_payload(x['r1'],x['r2'],x['r3']))
        store=VMInstruction(x['i4'],VM_OP_STORE_AXIS,CAP_AXIS,CAP_AXIS,x['slot'],(x['i3'],),(),encode_store_axis_payload(x['axis_a'],x['domain'],x['r3'],0.0,1))
        p=NativeVMProgram(r.revision,r.prefix_hash(),x['program'],CAP_AXIS,(b,),(c1,c2,add,store),(),(x['r3'],))
        q=optimize_vm_program(p)
        left=execute_vm_transaction({x['slot']:state},p,r)
        right=execute_vm_transaction({x['slot']:state},q,r)
        self.assertEqual(left.receipt.status,EXECUTION_SUCCESS)
        self.assertEqual(right.receipt.status,EXECUTION_SUCCESS)
        self.assertEqual(left.receipt.final_hashes,right.receipt.final_hashes)
        self.assertEqual(left.returns,right.returns)

    def test_load_dependent_add_is_not_constant_folded(self):
        r,x,state,b=fixture()
        load=VMInstruction(x['i1'],VM_OP_LOAD_AXIS,0,CAP_AXIS_READ,x['slot'],(),(),encode_load_axis_payload(x['axis_a'],x['r1']))
        const=VMInstruction(x['i2'],VM_OP_CONST,0,0,x['slot'],(),(),encode_register_const_payload(x['r2'],PointValue(1)))
        add=VMInstruction(x['i3'],VM_OP_ADD,0,0,x['slot'],(x['i1'],x['i2']),(),encode_register_binary_payload(x['r1'],x['r2'],x['r3']))
        p=NativeVMProgram(r.revision,r.prefix_hash(),x['program'],CAP_AXIS_READ,(b,),(load,const,add),(),(x['r3'],))
        q=optimize_vm_program(p)
        self.assertTrue(any(i.opcode==VM_OP_ADD for i in q.instructions))

if __name__=='__main__':unittest.main()
