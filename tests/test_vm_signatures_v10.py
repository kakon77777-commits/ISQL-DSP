import unittest

from isql_dsr.machine import NativeSemanticState, registered_state_hash
from isql_dsr.model import PointValue, VectorValue
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace
from isql_dsr.vm import (
    BIND_DYNAMIC, BIND_EXACT, CAP_CALL, EXECUTION_FAILED, EXECUTION_SUCCESS,
    TYPE_ANY, TYPE_INT, TYPE_TEXT, TYPE_VECTOR,
    NativeVMProgram, VMFunctionSignature, VMInstruction, VMRegisterSpec, VMStateBinding,
    VM_OP_CALL, VM_OP_CONST, VM_OP_MOVE,
    _encode_vm_program_v9, decode_vm_program, encode_vm_call_payload,
    encode_register_const_payload, encode_register_move_payload, encode_vm_program,
    execute_vm_transaction,
)


def fixture():
    r=NativeSymbolRegistry(); x={}
    rows=[
        (SymbolNamespace.PROGRAM_ID,'program:root','root'),(SymbolNamespace.PROGRAM_ID,'program:child','child'),
        (SymbolNamespace.INSTRUCTION_ID,'instruction:one','i1'),(SymbolNamespace.INSTRUCTION_ID,'instruction:two','i2'),
        (SymbolNamespace.STATE_SLOT_ID,'slot:root','slot'),(SymbolNamespace.STATE_SLOT_ID,'slot:child','child_slot'),
        (SymbolNamespace.IDENTITY,'state:sig','identity'),
        (SymbolNamespace.REGISTER_ID,'register:arg','arg'),(SymbolNamespace.REGISTER_ID,'register:out','out'),
        (SymbolNamespace.REGISTER_ID,'register:child-arg','carg'),(SymbolNamespace.REGISTER_ID,'register:child-out','cout'),
    ]
    for ns,text,key in rows:r,x[key]=r.intern_text(ns,text)
    state=NativeSemanticState(r.revision,r.prefix_hash(),x['identity'],0)
    return r,x,state


class VMSignaturesV10Tests(unittest.TestCase):
    def test_v10_signature_round_trip(self):
        r,x,state=fixture()
        item=VMInstruction(x['i1'],VM_OP_MOVE,0,0,x['slot'],(),(),encode_register_move_payload(x['arg'],x['out']))
        sig=VMFunctionSignature((VMRegisterSpec(x['arg'],TYPE_INT),),(VMRegisterSpec(x['out'],TYPE_INT),))
        p=NativeVMProgram(r.revision,r.prefix_hash(),x['root'],0,(VMStateBinding(x['slot'],BIND_EXACT,state.revision,registered_state_hash(state)),),(item,),(x['arg'],),(x['out'],),signature=sig)
        raw=encode_vm_program(p)
        q=decode_vm_program(raw,r)
        self.assertEqual(q.signature,sig)
        self.assertEqual(encode_vm_program(q),raw)

    def test_root_argument_type_mismatch_fails_atomically(self):
        r,x,state=fixture()
        item=VMInstruction(x['i1'],VM_OP_MOVE,0,0,x['slot'],(),(),encode_register_move_payload(x['arg'],x['out']))
        sig=VMFunctionSignature((VMRegisterSpec(x['arg'],TYPE_INT),),(VMRegisterSpec(x['out'],TYPE_INT),))
        p=NativeVMProgram(r.revision,r.prefix_hash(),x['root'],0,(VMStateBinding(x['slot'],BIND_EXACT,state.revision,registered_state_hash(state)),),(item,),(x['arg'],),(x['out'],),signature=sig)
        result=execute_vm_transaction({x['slot']:state},p,r,arguments={x['arg']:PointValue('not-int')})
        self.assertEqual(result.receipt.status,EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code,'VM_ARGUMENT_TYPE_MISMATCH')

    def test_root_return_type_mismatch_rolls_back(self):
        r,x,state=fixture()
        item=VMInstruction(x['i1'],VM_OP_CONST,0,0,x['slot'],(),(),encode_register_const_payload(x['out'],PointValue('text')))
        sig=VMFunctionSignature((),(VMRegisterSpec(x['out'],TYPE_INT),))
        p=NativeVMProgram(r.revision,r.prefix_hash(),x['root'],0,(VMStateBinding(x['slot'],BIND_EXACT,state.revision,registered_state_hash(state)),),(item,),(),(x['out'],),signature=sig)
        result=execute_vm_transaction({x['slot']:state},p,r)
        self.assertEqual(result.receipt.status,EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code,'VM_RETURN_TYPE_MISMATCH')

    def test_call_argument_type_mismatch_fails_entire_transaction(self):
        r,x,state=fixture()
        child_move=VMInstruction(x['i2'],VM_OP_MOVE,0,0,x['child_slot'],(),(),encode_register_move_payload(x['carg'],x['cout']))
        child_sig=VMFunctionSignature((VMRegisterSpec(x['carg'],TYPE_INT),),(VMRegisterSpec(x['cout'],TYPE_INT),))
        child=NativeVMProgram(r.revision,r.prefix_hash(),x['child'],0,(VMStateBinding(x['child_slot'],BIND_DYNAMIC),),(child_move,),(x['carg'],),(x['cout'],),signature=child_sig)
        call=VMInstruction(x['i1'],VM_OP_CALL,0,CAP_CALL,x['slot'],(),(),encode_vm_call_payload(x['child'],((x['child_slot'],x['slot']),),(x['arg'],),(x['out'],)))
        root_sig=VMFunctionSignature((VMRegisterSpec(x['arg'],TYPE_TEXT),),(VMRegisterSpec(x['out'],TYPE_INT),))
        root=NativeVMProgram(r.revision,r.prefix_hash(),x['root'],CAP_CALL,(VMStateBinding(x['slot'],BIND_EXACT,state.revision,registered_state_hash(state)),),(call,),(x['arg'],),(x['out'],),signature=root_sig)
        result=execute_vm_transaction({x['slot']:state},root,r,{x['child']:child},arguments={x['arg']:PointValue('x')})
        self.assertEqual(result.receipt.status,EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code,'VM_CALL_ARGUMENT_TYPE_MISMATCH')

    def test_legacy_v9_decode_gets_any_signature(self):
        r,x,state=fixture()
        item=VMInstruction(x['i1'],VM_OP_MOVE,0,0,x['slot'],(),(),encode_register_move_payload(x['arg'],x['out']))
        p=NativeVMProgram(r.revision,r.prefix_hash(),x['root'],0,(VMStateBinding(x['slot'],BIND_EXACT,state.revision,registered_state_hash(state)),),(item,),(x['arg'],),(x['out'],))
        legacy=_encode_vm_program_v9(p)
        q=decode_vm_program(legacy,r)
        self.assertEqual(tuple(s.type_tag for s in q.signature.arguments),(TYPE_ANY,))
        self.assertEqual(tuple(s.type_tag for s in q.signature.returns),(TYPE_ANY,))

if __name__=='__main__':unittest.main()
