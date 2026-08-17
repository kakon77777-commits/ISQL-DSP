import json
from pathlib import Path
import tempfile
import unittest

from isql_dsr.bridge import decode_decimal_bytes, to_registered_core_vm_envelope
from isql_dsr.machine import NativeAxis, NativeSemanticState, encode_registered_state, registered_state_hash
from isql_dsr.model import PointValue
from isql_dsr.native import encode_uvarint, operation_opcode
from isql_dsr.program import EFFECT_AXIS
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace, encode_registry
from isql_dsr.vm import (
    BIND_EXACT, CAP_AXIS, NativeVMProgram, VMInstruction, VMStateBinding,
    decode_vm_program, encode_vm_program,
)


def fixture():
    r=NativeSymbolRegistry(); x={}
    for ns,text,key in [
        (SymbolNamespace.PROGRAM_ID,'vm:root','program'),
        (SymbolNamespace.INSTRUCTION_ID,'vm:i1','i1'),
        (SymbolNamespace.STATE_SLOT_ID,'slot:a','slot'),
        (SymbolNamespace.IDENTITY,'state:a','id'),
        (SymbolNamespace.AXIS_KEY,'risk','axis'),
        (SymbolNamespace.AXIS_DOMAIN,'ordinal','domain')]:
        r,x[key]=r.intern_text(ns,text)
    s=NativeSemanticState(r.revision,r.prefix_hash(),x['id'],0,
        axes=(NativeAxis(x['axis'],x['domain'],PointValue(1),0,1),))
    i=VMInstruction(x['i1'],operation_opcode('remove_axis'),EFFECT_AXIS,CAP_AXIS,x['slot'],(),(),encode_uvarint(x['axis']))
    p=NativeVMProgram(r.revision,r.prefix_hash(),x['program'],CAP_AXIS,
        (VMStateBinding(x['slot'],BIND_EXACT,s.revision,registered_state_hash(s)),),(i,))
    return r,x,s,p


class VMCLIBridgeV07Tests(unittest.TestCase):
    def test_vm_core_envelope_is_digits_only_dsrv(self):
        r,x,s,p=fixture()
        env=to_registered_core_vm_envelope(p,{x['slot']:s})
        self.assertEqual(env.domain,'EXEC')
        self.assertEqual(env.control,'DSRV')
        self.assertTrue(env.payload_digits.isdigit())
        self.assertEqual(decode_decimal_bytes(env.payload_digits),encode_vm_program(p))

    def test_vm_run_cli_executes_registered_state(self):
        r,x,s,p=fixture()
        with tempfile.TemporaryDirectory() as td:
            td=Path(td)
            (td/'r.isqlr').write_bytes(encode_registry(r))
            (td/'s.isqln').write_bytes(encode_registered_state(s))
            (td/'p.isqlp').write_bytes(encode_vm_program(p))
            out=td/'out'
            import contextlib, io
            from isql_dsr.cli import main
            buf=io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc=main(['vm-run','--registry',str(td/'r.isqlr'),'--program',str(td/'p.isqlp'),
                         '--state',f"{x['slot']}={td/'s.isqln'}",'--out-dir',str(out)])
            self.assertEqual(rc,0)
            payload=json.loads(buf.getvalue())
            self.assertEqual(payload['status'],1)
            self.assertTrue((out/f"{x['slot']}.isqln").exists())


if __name__=='__main__': unittest.main()
