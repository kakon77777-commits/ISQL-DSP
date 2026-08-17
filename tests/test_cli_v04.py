import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from isql_dsr.events import TransitionEvent
from isql_dsr.model import PointValue, SemanticState, SpectrumAxis


class CLIV04Tests(unittest.TestCase):
    def run_cli(self, args):
        from isql_dsr.cli import main
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(args)
        self.assertEqual(rc, 0)
        return json.loads(out.getvalue())

    def write_json(self, path, value):
        Path(path).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def test_registry_registered_snapshot_stream_replay_and_r4_bridge(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            genesis = SemanticState(identity="obj:cli-v4", context={"mode": "machine"})
            event = TransitionEvent.for_state(
                genesis, event_id="evt-1", operation="upsert_axis",
                payload={"axis": SpectrumAxis("risk", "ordinal", PointValue(5), 0.1, 2).to_dict()},
            )
            genesis_json = td / "genesis.json"
            events_json = td / "events.json"
            registry = td / "symbols.isqlr"
            genesis_native = td / "genesis.isqln"
            stream = td / "events.isqle"
            final_native = td / "final.isqln"
            self.write_json(genesis_json, genesis.to_dict())
            self.write_json(events_json, [event.to_dict()])

            built = self.run_cli([
                "registry-build", "--state", str(genesis_json), "--events", str(events_json), "--out", str(registry)
            ])
            self.assertEqual(built["schema"], "isql.dsr-registry-artifact/v0.4")
            self.assertTrue(registry.exists())

            packed = self.run_cli([
                "registered-pack", "--state", str(genesis_json), "--registry", str(registry), "--out", str(genesis_native)
            ])
            self.assertEqual(packed["schema"], "isql.dsr-registered-artifact/v0.5")
            self.assertTrue(genesis_native.exists())

            streamed = self.run_cli([
                "stream-pack", "--genesis", str(genesis_json), "--events", str(events_json), "--registry", str(registry), "--out", str(stream)
            ])
            self.assertEqual(streamed["records"], 1)
            self.assertTrue(stream.exists())

            replayed = self.run_cli([
                "stream-replay", "--genesis-native", str(genesis_native), "--stream", str(stream), "--registry", str(registry), "--out", str(final_native)
            ])
            self.assertEqual(replayed["revision"], 1)
            inspected = self.run_cli([
                "registered-inspect", "--native", str(final_native), "--registry", str(registry)
            ])
            final = SemanticState.from_dict(inspected)
            self.assertEqual(final.axes[0].key, "risk")
            self.assertEqual(final.history, ())

            state_wire = self.run_cli([
                "bridge-r4", "--native", str(final_native), "--registry", str(registry), "--domain", "state"
            ])
            self.assertEqual((state_wire["domain"], state_wire["resolution"], state_wire["control"]), ("STATE", "R4", "DSRR"))

            exec_wire = self.run_cli([
                "bridge-r4", "--stream", str(stream), "--genesis-native", str(genesis_native), "--registry", str(registry), "--domain", "exec"
            ])
            self.assertEqual((exec_wire["domain"], exec_wire["resolution"], exec_wire["control"]), ("EXEC", "R4", "DSRE"))


if __name__ == "__main__":
    unittest.main()
