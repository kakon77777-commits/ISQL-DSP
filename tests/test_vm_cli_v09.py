import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from isql_dsr.cli import main
from isql_dsr.machine import NativeSemanticState, encode_registered_state, registered_state_hash
from isql_dsr.model import PointValue
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace, encode_registry
from isql_dsr.vm import (
    BIND_EXACT,
    NativeVMProgram,
    VMInstruction,
    VMStateBinding,
    VM_OP_CONST,
    VM_OP_MUL,
    encode_register_binary_payload,
    encode_register_const_payload,
    encode_vm_program,
)


def fixture():
    r = NativeSymbolRegistry(); x = {}
    for ns, text, key in [
        (SymbolNamespace.PROGRAM_ID, 'program:module-a', 'pa'),
        (SymbolNamespace.PROGRAM_ID, 'program:module-b', 'pb'),
        (SymbolNamespace.PROGRAM_ID, 'program:linked', 'pl'),
        (SymbolNamespace.INSTRUCTION_ID, 'i:a', 'ia'),
        (SymbolNamespace.INSTRUCTION_ID, 'i:b', 'ib'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:v09', 'slot'),
        (SymbolNamespace.IDENTITY, 'state:v09', 'identity'),
        (SymbolNamespace.REGISTER_ID, 'r:x', 'x'),
        (SymbolNamespace.REGISTER_ID, 'r:y', 'y'),
        (SymbolNamespace.REGISTER_ID, 'r:z', 'z'),
    ]:
        r, x[key] = r.intern_text(ns, text)
    state = NativeSemanticState(r.revision, r.prefix_hash(), x['identity'], 0)
    bind = VMStateBinding(x['slot'], BIND_EXACT, state.revision, registered_state_hash(state))
    a = NativeVMProgram(
        r.revision, r.prefix_hash(), x['pa'], 0, (bind,),
        (VMInstruction(x['ia'], VM_OP_CONST, 0, 0, x['slot'], (), (), encode_register_const_payload(x['x'], PointValue(4))),),
    )
    b = NativeVMProgram(
        r.revision, r.prefix_hash(), x['pb'], 0, (bind,),
        (VMInstruction(x['ib'], VM_OP_MUL, 0, 0, x['slot'], (), (), encode_register_binary_payload(x['x'], x['y'], x['z'])),),
        (x['x'], x['y']), (x['z'],),
    )
    return r, x, state, a, b


class VMCLIV09Tests(unittest.TestCase):
    def test_vm_link_and_run_roundtrip(self):
        r, x, state, a, b = fixture()
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            reg = td/'r.isqlr'; reg.write_bytes(encode_registry(r))
            st = td/'s.isqln'; st.write_bytes(encode_registered_state(state))
            pa = td/'a.isqlp'; pa.write_bytes(encode_vm_program(a))
            pb = td/'b.isqlp'; pb.write_bytes(encode_vm_program(b))
            linked = td/'linked.isqlp'
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main([
                    'vm-link', '--registry', str(reg), '--program-ref', str(x['pl']),
                    '--module', str(pa), '--module', str(pb),
                    '--argument-register', str(x['y']), '--return-register', str(x['z']),
                    '--out', str(linked),
                ])
            self.assertEqual(rc, 0)
            meta = json.loads(buf.getvalue())
            self.assertEqual(meta['schema'], 'isql.dsr-vm-link-result/v0.9')
            self.assertTrue(linked.exists())
            out = td/'out'; buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main([
                    'vm-run', '--registry', str(reg), '--program', str(linked),
                    '--state', f"{x['slot']}={st}",
                    '--arg', f"{x['y']}={{\"kind\":\"point\",\"value\":3}}",
                    '--out-dir', str(out),
                ])
            self.assertEqual(rc, 0)
            result = json.loads(buf.getvalue())
            self.assertEqual(result['schema'], 'isql.dsr-vm-transaction-result/v0.9')
            self.assertEqual(result['returns'], [[x['z'], {'kind': 'point', 'value': 12}]])


if __name__ == '__main__': unittest.main()
