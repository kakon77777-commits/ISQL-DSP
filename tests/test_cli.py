import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from isql_dsr.canonical import state_hash
from isql_dsr.events import TransitionEvent
from isql_dsr.model import PointValue, SemanticState, SpectrumAxis


class CLITests(unittest.TestCase):
    def run_cli(self, args):
        from isql_dsr.cli import main
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(args)
        self.assertEqual(rc, 0)
        return json.loads(buf.getvalue())

    def write_json(self, path, obj):
        Path(path).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def test_new_and_hash_commands(self):
        with tempfile.TemporaryDirectory() as td:
            result = self.run_cli(["new", "--identity", "isql:測試:alpha", "--context-json", '{"language":"zh-Hant"}'])
            self.assertEqual(result["identity"], "isql:測試:alpha")
            state = SemanticState.from_dict(result)
            path = Path(td) / "state.json"
            self.write_json(path, result)
            hashed = self.run_cli(["hash", "--state", str(path)])
            self.assertEqual(hashed["state_hash"], state_hash(state))

    def test_apply_replay_and_bridge_commands(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            genesis = SemanticState(identity="isql:demo:alpha")
            event = TransitionEvent.for_state(
                genesis,
                event_id="e1",
                operation="upsert_axis",
                payload={"axis": SpectrumAxis("priority", "ordinal", PointValue(3)).to_dict()},
            )
            genesis_path = td / "genesis.json"
            event_path = td / "event.json"
            events_path = td / "events.json"
            self.write_json(genesis_path, genesis.to_dict())
            self.write_json(event_path, event.to_dict())
            self.write_json(events_path, [event.to_dict()])

            applied = self.run_cli(["apply", "--state", str(genesis_path), "--event", str(event_path)])
            final = SemanticState.from_dict(applied["state"])
            self.assertEqual(final.revision, 1)
            self.assertEqual(final.axes[0].key, "priority")

            replayed = self.run_cli(["replay", "--genesis", str(genesis_path), "--events", str(events_path)])
            self.assertEqual(SemanticState.from_dict(replayed), final)

            final_path = td / "final.json"
            self.write_json(final_path, final.to_dict())
            bridged = self.run_cli(["bridge", "--state", str(final_path)])
            self.assertEqual(bridged["domain"], "STATE")
            self.assertEqual(bridged["state_hash"], state_hash(final))


if __name__ == "__main__":
    unittest.main()
