import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from isql_dsr.bridge import decode_decimal_bytes, to_registered_core_vm_envelope
from isql_dsr.cli import main
from isql_dsr.machine import NativeSemanticState, encode_registered_state, registered_state_hash
from isql_dsr.model import PointValue
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace, encode_registry
from isql_dsr.vm import (
    BIND_EXACT,
    NativeVMProgram,
    VMInstruction,
    VMStateBinding,
    VM_OP_RETURN,
    encode_vm_program,
)


def fixture():
    r = NativeSymbolRegistry(); x = {}
    for ns, text, key in [
        (SymbolNamespace.PROGRAM_ID, 'vm:v08-root', 'program'),
        (SymbolNamespace.INSTRUCTION_ID, 'vm:return', 'return_i'),
        (SymbolNamespace.STATE_SLOT_ID, 'slot:a', 'slot'),
        (SymbolNamespace.IDENTITY, 'state:a', 'identity'),
        (SymbolNamespace.REGISTER_ID, 'register:arg', 'arg'),
    ]:
        r, x[key] = r.intern_text(ns, text)
    s = NativeSemanticState(r.revision, r.prefix_hash(), x['identity'], 0)
    ret = VMInstruction(x['return_i'], VM_OP_RETURN, 0, 0, x['slot'], (), (), b'')
    p = NativeVMProgram(
        r.revision, r.prefix_hash(), x['program'], 0,
        (VMStateBinding(x['slot'], BIND_EXACT, s.revision, registered_state_hash(s)),),
        (ret,), (x['arg'],), (x['arg'],),
    )
    return r, x, s, p


class VMCLIV08Tests(unittest.TestCase):
    def test_vm_run_accepts_numeric_argument_and_emits_return_projection(self):
        r, x, s, p = fixture()
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td/'r.isqlr').write_bytes(encode_registry(r))
            (td/'s.isqln').write_bytes(encode_registered_state(s))
            (td/'p.isqlp').write_bytes(encode_vm_program(p))
            out = td/'out'
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main([
                    'vm-run', '--registry', str(td/'r.isqlr'), '--program', str(td/'p.isqlp'),
                    '--state', f"{x['slot']}={td/'s.isqln'}",
                    '--arg', f"{x['arg']}={{\"kind\":\"point\",\"value\":42}}",
                    '--scope', f"{x['slot']}=0", '--parallel', '--out-dir', str(out),
                ])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload['schema'], 'isql.dsr-vm-transaction-result/v0.8')
            self.assertTrue(payload['parallel'])
            self.assertEqual(payload['returns'], [[x['arg'], {'kind': 'point', 'value': 42}]])

    def test_core_dsrv_bridge_still_wraps_exact_v08_program_bytes(self):
        r, x, s, p = fixture()
        env = to_registered_core_vm_envelope(p, {x['slot']: s})
        self.assertEqual(env.domain, 'EXEC')
        self.assertEqual(env.resolution, 'R4')
        self.assertEqual(env.control, 'DSRV')
        self.assertTrue(env.payload_digits.isdigit())
        self.assertEqual(decode_decimal_bytes(env.payload_digits), encode_vm_program(p))


if __name__ == '__main__': unittest.main()
