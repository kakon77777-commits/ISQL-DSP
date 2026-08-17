import unittest

from isql_dsr.machine import NativeSemanticState, registered_state_hash
from isql_dsr.model import PointValue, VectorValue, RecordValue
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace
from isql_dsr.vm import (
    BIND_EXACT, EXECUTION_FAILED, EXECUTION_SUCCESS,
    NativeVMProgram, VMInstruction, VMStateBinding,
    VM_OP_CONST, VM_OP_MOVE,
    VM_OP_VECTOR_PACK, VM_OP_VECTOR_GET, VM_OP_VECTOR_LEN,
    VM_OP_RECORD_PACK, VM_OP_RECORD_GET, VM_OP_RECORD_SET,
    encode_register_const_payload, encode_register_move_payload,
    encode_vector_pack_payload, encode_vector_get_payload, encode_vector_len_payload,
    encode_record_pack_payload, encode_record_get_payload, encode_record_set_payload,
    execute_vm_transaction, vm_execution_batches,
)


def fixture(extra_instruction_count=8):
    r = NativeSymbolRegistry(); x = {}
    rows = [
        (SymbolNamespace.PROGRAM_ID, 'program:containers-v10', 'program'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:v10', 'slot'),
        (SymbolNamespace.IDENTITY, 'state:v10', 'identity'),
        (SymbolNamespace.FIELD_ID, 'field:a', 'fa'),
        (SymbolNamespace.FIELD_ID, 'field:b', 'fb'),
    ]
    for name in ('a','b','c','vec','idx','out','len','rec','rec2','tmp'):
        rows.append((SymbolNamespace.REGISTER_ID, f'register:{name}', name))
    for i in range(extra_instruction_count):
        rows.append((SymbolNamespace.INSTRUCTION_ID, f'instruction:{i+1}', f'i{i+1}'))
    for ns, text, key in rows:
        r, x[key] = r.intern_text(ns, text)
    state = NativeSemanticState(r.revision, r.prefix_hash(), x['identity'], 0)
    binding = VMStateBinding(x['slot'], BIND_EXACT, state.revision, registered_state_hash(state))
    return r, x, state, binding


def program(r, x, binding, items, args=(), returns=()):
    return NativeVMProgram(r.revision, r.prefix_hash(), x['program'], 0, (binding,), tuple(items), tuple(args), tuple(returns))


class VMContainersV10Tests(unittest.TestCase):
    def test_vector_pack_get_and_len(self):
        r,x,state,b = fixture()
        pack = VMInstruction(x['i1'], VM_OP_VECTOR_PACK,0,0,x['slot'],(),(), encode_vector_pack_payload((x['a'],x['b']),x['vec']))
        idx = VMInstruction(x['i2'], VM_OP_CONST,0,0,x['slot'],(x['i1'],),(), encode_register_const_payload(x['idx'], PointValue(1)))
        get = VMInstruction(x['i3'], VM_OP_VECTOR_GET,0,0,x['slot'],(x['i2'],),(), encode_vector_get_payload(x['vec'],x['idx'],x['out']))
        length = VMInstruction(x['i4'], VM_OP_VECTOR_LEN,0,0,x['slot'],(x['i1'],),(), encode_vector_len_payload(x['vec'],x['len']))
        p=program(r,x,b,(pack,idx,get,length),(x['a'],x['b']),(x['vec'],x['out'],x['len']))
        result=execute_vm_transaction({x['slot']:state},p,r,arguments={x['a']:PointValue(7),x['b']:PointValue(9)})
        self.assertEqual(result.receipt.status, EXECUTION_SUCCESS)
        self.assertEqual(dict(result.returns)[x['vec']], VectorValue((PointValue(7),PointValue(9))))
        self.assertEqual(dict(result.returns)[x['out']], PointValue(9))
        self.assertEqual(dict(result.returns)[x['len']], PointValue(2))

    def test_vector_get_out_of_range_fails_atomically(self):
        r,x,state,b=fixture()
        pack=VMInstruction(x['i1'],VM_OP_VECTOR_PACK,0,0,x['slot'],(),(),encode_vector_pack_payload((x['a'],),x['vec']))
        idx=VMInstruction(x['i2'],VM_OP_CONST,0,0,x['slot'],(x['i1'],),(),encode_register_const_payload(x['idx'],PointValue(2)))
        get=VMInstruction(x['i3'],VM_OP_VECTOR_GET,0,0,x['slot'],(x['i2'],),(),encode_vector_get_payload(x['vec'],x['idx'],x['out']))
        p=program(r,x,b,(pack,idx,get),(x['a'],),(x['out'],))
        result=execute_vm_transaction({x['slot']:state},p,r,arguments={x['a']:PointValue(1)})
        self.assertEqual(result.receipt.status, EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code,'VM_VECTOR_INDEX_OUT_OF_RANGE')

    def test_record_pack_get_set_is_immutable(self):
        r,x,state,b=fixture()
        pack=VMInstruction(x['i1'],VM_OP_RECORD_PACK,0,0,x['slot'],(),(),encode_record_pack_payload(((x['fb'],x['b']),(x['fa'],x['a'])),x['rec']))
        get_a=VMInstruction(x['i2'],VM_OP_RECORD_GET,0,0,x['slot'],(x['i1'],),(),encode_record_get_payload(x['rec'],x['fa'],x['out']))
        set_b=VMInstruction(x['i3'],VM_OP_RECORD_SET,0,0,x['slot'],(x['i1'],),(),encode_record_set_payload(x['rec'],x['fb'],x['c'],x['rec2']))
        get_b=VMInstruction(x['i4'],VM_OP_RECORD_GET,0,0,x['slot'],(x['i3'],),(),encode_record_get_payload(x['rec2'],x['fb'],x['tmp']))
        p=program(r,x,b,(pack,get_a,set_b,get_b),(x['a'],x['b'],x['c']),(x['rec'],x['rec2'],x['out'],x['tmp']))
        result=execute_vm_transaction({x['slot']:state},p,r,arguments={x['a']:PointValue(1),x['b']:PointValue(2),x['c']:PointValue(8)})
        self.assertEqual(result.receipt.status,EXECUTION_SUCCESS)
        ret=dict(result.returns)
        self.assertEqual(ret[x['rec']], RecordValue(((x['fa'],PointValue(1)),(x['fb'],PointValue(2)))))
        self.assertEqual(ret[x['rec2']], RecordValue(((x['fa'],PointValue(1)),(x['fb'],PointValue(8)))))
        self.assertEqual(ret[x['out']],PointValue(1))
        self.assertEqual(ret[x['tmp']],PointValue(8))

    def test_record_missing_field_fails(self):
        r,x,state,b=fixture()
        pack=VMInstruction(x['i1'],VM_OP_RECORD_PACK,0,0,x['slot'],(),(),encode_record_pack_payload(((x['fa'],x['a']),),x['rec']))
        get=VMInstruction(x['i2'],VM_OP_RECORD_GET,0,0,x['slot'],(x['i1'],),(),encode_record_get_payload(x['rec'],x['fb'],x['out']))
        p=program(r,x,b,(pack,get),(x['a'],),(x['out'],))
        result=execute_vm_transaction({x['slot']:state},p,r,arguments={x['a']:PointValue(1)})
        self.assertEqual(result.receipt.status,EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code,'VM_RECORD_FIELD_MISSING')

    def test_scheduler_separates_container_register_hazard(self):
        r,x,state,b=fixture()
        pack=VMInstruction(x['i1'],VM_OP_VECTOR_PACK,0,0,x['slot'],(),(),encode_vector_pack_payload((x['a'],),x['vec']))
        move=VMInstruction(x['i2'],VM_OP_MOVE,0,0,x['slot'],(),(),encode_register_move_payload(x['vec'],x['out']))
        p=program(r,x,b,(pack,move),(x['a'],),(x['out'],))
        self.assertEqual(len(vm_execution_batches(p)),2)

if __name__=='__main__': unittest.main()
