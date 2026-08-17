import unittest

from isql_dsr.machine import NativeAxis, NativeSemanticState
from isql_dsr.model import PointValue
from isql_dsr.native import encode_uvarint
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace
from isql_dsr.vm import (
    ALL_CAPABILITIES, BIND_DYNAMIC, CAP_CALL, EXECUTION_FAILED,
    NativeVMProgram, VMInstruction, VMStateBinding, VM_OP_CALL,
    execute_vm_transaction,
)

ZERO='0'*64


class VMSubprogramV07Tests(unittest.TestCase):
    def test_recursive_call_cycle_fails_closed(self):
        r=NativeSymbolRegistry(); refs={}
        for ns,text,key in [
            (SymbolNamespace.PROGRAM_ID,'p:a','pa'),(SymbolNamespace.PROGRAM_ID,'p:b','pb'),
            (SymbolNamespace.INSTRUCTION_ID,'i:a','ia'),(SymbolNamespace.INSTRUCTION_ID,'i:b','ib'),
            (SymbolNamespace.STATE_SLOT_ID,'slot:a','slot'),
            (SymbolNamespace.IDENTITY,'state:a','id'),
            (SymbolNamespace.AXIS_KEY,'risk','axis'),(SymbolNamespace.AXIS_DOMAIN,'ordinal','domain')]:
            r,refs[key]=r.intern_text(ns,text)
        s=NativeSemanticState(r.revision,r.prefix_hash(),refs['id'],0,
                              axes=(NativeAxis(refs['axis'],refs['domain'],PointValue(1),0,1),))
        a=NativeVMProgram(r.revision,r.prefix_hash(),refs['pa'],CAP_CALL,
            (VMStateBinding(refs['slot'],BIND_DYNAMIC,0,ZERO),),
            (VMInstruction(refs['ia'],VM_OP_CALL,0,CAP_CALL,refs['slot'],(),(),encode_uvarint(refs['pb'])),))
        b=NativeVMProgram(r.revision,r.prefix_hash(),refs['pb'],CAP_CALL,
            (VMStateBinding(refs['slot'],BIND_DYNAMIC,0,ZERO),),
            (VMInstruction(refs['ib'],VM_OP_CALL,0,CAP_CALL,refs['slot'],(),(),encode_uvarint(refs['pa'])),))
        result=execute_vm_transaction({refs['slot']:s},a,r,{refs['pa']:a,refs['pb']:b},ALL_CAPABILITIES)
        self.assertEqual(result.receipt.status,EXECUTION_FAILED)
        self.assertEqual(result.receipt.error_code,'VM_CALL_CYCLE')


if __name__=='__main__': unittest.main()
