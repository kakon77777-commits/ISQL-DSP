import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from isql_dsr.cli import main
from isql_dsr.machine import NativeSemanticState, registered_state_hash
from isql_dsr.model import PointValue
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace, encode_registry
from isql_dsr.vm import BIND_EXACT, NativeVMProgram, VMInstruction, VMStateBinding, VM_OP_ADD, VM_OP_CONST, encode_register_binary_payload, encode_register_const_payload, encode_vm_program, decode_vm_program


class VMCLIV10Tests(unittest.TestCase):
    def test_vm_optimize_writes_smaller_equivalent_program(self):
        r=NativeSymbolRegistry();x={}
        rows=[(SymbolNamespace.PROGRAM_ID,'p','p'),(SymbolNamespace.STATE_SLOT_ID,'s','s'),(SymbolNamespace.IDENTITY,'id','id'),
              (SymbolNamespace.REGISTER_ID,'a','a'),(SymbolNamespace.REGISTER_ID,'b','b'),(SymbolNamespace.REGISTER_ID,'out','out')]
        for i in range(3): rows.append((SymbolNamespace.INSTRUCTION_ID,f'i{i}',f'i{i}'))
        for ns,text,key in rows:r,x[key]=r.intern_text(ns,text)
        state=NativeSemanticState(r.revision,r.prefix_hash(),x['id'],0)
        b=VMStateBinding(x['s'],BIND_EXACT,state.revision,registered_state_hash(state))
        i0=VMInstruction(x['i0'],VM_OP_CONST,0,0,x['s'],(),(),encode_register_const_payload(x['a'],PointValue(2)))
        i1=VMInstruction(x['i1'],VM_OP_CONST,0,0,x['s'],(),(),encode_register_const_payload(x['b'],PointValue(3)))
        i2=VMInstruction(x['i2'],VM_OP_ADD,0,0,x['s'],(x['i0'],x['i1']),(),encode_register_binary_payload(x['a'],x['b'],x['out']))
        program=NativeVMProgram(r.revision,r.prefix_hash(),x['p'],0,(b,),(i0,i1,i2),(),(x['out'],))
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); rp=td/'symbols.isqlr'; pp=td/'input.isqlp'; op=td/'output.isqlp'
            rp.write_bytes(encode_registry(r)); pp.write_bytes(encode_vm_program(program))
            buf=StringIO()
            with redirect_stdout(buf):
                rc=main(['vm-optimize','--registry',str(rp),'--program',str(pp),'--out',str(op)])
            self.assertEqual(rc,0)
            payload=json.loads(buf.getvalue())
            self.assertEqual(payload['schema'],'isql.dsr-vm-optimize-result/v1.0')
            optimized=decode_vm_program(op.read_bytes(),r)
            self.assertLess(len(optimized.instructions),len(program.instructions))

if __name__=='__main__':unittest.main()
