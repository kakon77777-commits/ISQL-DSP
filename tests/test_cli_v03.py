import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from isql_dsr.model import PointValue, SemanticState, SpectrumAxis
from isql_dsr.native import decode_state, encode_state


class CLIV03Tests(unittest.TestCase):
    def _run(self, *args):
        proc = subprocess.run(
            [sys.executable, "-m", "isql_dsr", *args],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_native_pack_inspect_and_hash(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            state = SemanticState(identity="native:cli", axes=(SpectrumAxis("x", "n", PointValue(9)),))
            src = td / "inspection.json"
            native = td / "state.isqln"
            src.write_text(json.dumps(state.to_dict(), ensure_ascii=False), encoding="utf-8")

            packed = self._run("native-pack", "--state", str(src), "--out", str(native))
            self.assertEqual(packed["schema"], "isql.dsr-native-artifact/v0.3")
            self.assertTrue(native.exists())
            self.assertEqual(native.read_bytes(), encode_state(state))

            inspected = self._run("native-inspect", "--native", str(native))
            self.assertEqual(SemanticState.from_dict(inspected), state)

            hashed = self._run("native-hash", "--native", str(native))
            self.assertEqual(hashed["state_hash"], packed["state_hash"])
            self.assertEqual(decode_state(native.read_bytes()), state)

    def test_bridge_accepts_native_artifact_and_emits_r3_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            state = SemanticState(identity="native:cli-bridge")
            native = td / "state.isqln"
            native.write_bytes(encode_state(state))
            bundle = self._run("bridge", "--native", str(native), "--domain", "bundle")
            self.assertEqual(bundle["schema"], "isql.dsr-native-core-bundle/v0.3")
            self.assertEqual(bundle["sem"]["resolution"], "R3")
            self.assertEqual(bundle["state"]["control"], "DSRN")


if __name__ == "__main__":
    unittest.main()
