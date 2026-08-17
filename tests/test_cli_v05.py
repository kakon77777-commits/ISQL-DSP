import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from isql_dsr.events import TransitionEvent
from isql_dsr.model import PointValue, SemanticState, SpectrumAxis, TypedRelation


class CLIV05Tests(unittest.TestCase):
    def run_cli(self, args):
        from isql_dsr.cli import main
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(args)
        self.assertEqual(rc, 0)
        return json.loads(out.getvalue())

    @staticmethod
    def write_json(path, value):
        Path(path).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def test_branch_pack_and_merge(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            base = SemanticState(identity="obj:branch-cli")
            left_event = TransitionEvent.for_state(base, event_id="l1", operation="upsert_axis", payload={"axis": SpectrumAxis("risk", "ordinal", PointValue(3)).to_dict()})
            right_event = TransitionEvent.for_state(base, event_id="r1", operation="deny_relation", payload={"relation": TypedRelation("a", "supports", "b").to_dict()})
            base_json = td / "base.json"
            left_json = td / "left.json"
            right_json = td / "right.json"
            registry = td / "symbols.isqlr"
            base_native = td / "base.isqln"
            left_branch = td / "left.isqlb"
            right_branch = td / "right.isqlb"
            merged = td / "merged.isqln"
            self.write_json(base_json, base.to_dict())
            self.write_json(left_json, [left_event.to_dict()])
            self.write_json(right_json, [right_event.to_dict()])

            built = self.run_cli([
                "registry-build", "--state", str(base_json), "--events", str(left_json),
                "--out", str(registry), "--branch-id", "left", "--branch-id", "right"
            ])
            # extend same registry with right event identifiers
            self.run_cli([
                "registry-build", "--state", str(base_json), "--events", str(right_json),
                "--base-registry", str(registry), "--out", str(registry), "--branch-id", "left", "--branch-id", "right"
            ])
            self.assertGreaterEqual(built["revision"], 1)

            self.run_cli(["registered-pack", "--state", str(base_json), "--registry", str(registry), "--out", str(base_native)])
            left = self.run_cli(["branch-pack", "--branch-id", "left", "--genesis", str(base_json), "--events", str(left_json), "--registry", str(registry), "--out", str(left_branch)])
            right = self.run_cli(["branch-pack", "--branch-id", "right", "--genesis", str(base_json), "--events", str(right_json), "--registry", str(registry), "--out", str(right_branch)])
            self.assertEqual(left["schema"], "isql.dsr-branch-artifact/v0.5")
            self.assertEqual(right["records"], 1)

            result = self.run_cli([
                "branch-merge", "--base-native", str(base_native), "--branch", str(left_branch), "--branch", str(right_branch),
                "--registry", str(registry), "--out", str(merged)
            ])
            self.assertEqual(result["schema"], "isql.dsr-branch-merge-result/v0.5")
            self.assertEqual(result["conflicts"], [])
            inspected = self.run_cli(["registered-inspect", "--native", str(merged), "--registry", str(registry)])
            state = SemanticState.from_dict(inspected)
            self.assertEqual(state.axes[0].key, "risk")
            self.assertEqual(len(state.negative_relations), 1)


if __name__ == "__main__":
    unittest.main()
