import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from isql_dsr import PointValue, SemanticState, SpectrumAxis
from isql_dsr.fusion import SemanticProposal


class CLIV02Tests(unittest.TestCase):
    def _run(self, *args):
        proc = subprocess.run(
            [sys.executable, "-m", "isql_dsr", *args],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_topology_command_computes_builtin_descriptors(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "state.json"
            state = SemanticState(identity="demo:cli-topology")
            p.write_text(json.dumps(state.to_dict()), encoding="utf-8")
            out = self._run("topology", "--state", str(p), "--methods", "graph.components,graph.cycle_rank")
            self.assertEqual(out["schema"], "isql.dsr-topology-result/v0.3")
            self.assertEqual([x["descriptor_id"] for x in out["descriptors"]], ["graph.components", "graph.cycle_rank"])

    def test_fuse_command_applies_replayable_fusion_event(self):
        with tempfile.TemporaryDirectory() as td:
            base = SemanticState(
                identity="demo:cli-fusion",
                axes=(SpectrumAxis("risk", "ordinal", PointValue("unknown"), uncertainty=0.9),),
            )
            state_p = Path(td) / "state.json"
            state_p.write_text(json.dumps(base.to_dict()), encoding="utf-8")
            proposals = [
                SemanticProposal.for_state(
                    base,
                    proposal_id="p1",
                    source_id="model-a",
                    axes=(SpectrumAxis("risk", "ordinal", PointValue("high"), uncertainty=0.1),),
                ).to_dict(),
                SemanticProposal.for_state(
                    base,
                    proposal_id="p2",
                    source_id="model-b",
                    axes=(SpectrumAxis("risk", "ordinal", PointValue("high"), uncertainty=0.1),),
                ).to_dict(),
            ]
            proposals_p = Path(td) / "proposals.json"
            proposals_p.write_text(json.dumps(proposals), encoding="utf-8")
            out = self._run(
                "fuse",
                "--state", str(state_p),
                "--proposals", str(proposals_p),
                "--event-id", "evt-cli-fuse",
            )
            self.assertEqual(out["schema"], "isql.dsr-fuse-result/v0.3")
            self.assertEqual(out["state"]["revision"], 1)
            self.assertEqual(out["state"]["axes"][0]["value"]["value"], "high")
            self.assertEqual(out["fusion"]["proposal_ids"], ["p1", "p2"])

    def test_bridge_command_supports_sem_state_and_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "state.json"
            state = SemanticState(identity="demo:cli-bridge")
            p.write_text(json.dumps(state.to_dict()), encoding="utf-8")
            sem = self._run("bridge", "--state", str(p), "--domain", "sem")
            state_out = self._run("bridge", "--state", str(p), "--domain", "state")
            bundle = self._run("bridge", "--state", str(p), "--domain", "bundle")
            self.assertEqual(sem["domain"], "SEM")
            self.assertEqual(state_out["domain"], "STATE")
            self.assertEqual(bundle["schema"], "isql.dsr-core-bundle/v0.2")
            self.assertEqual(bundle["sem"]["domain"], "SEM")
            self.assertEqual(bundle["state"]["domain"], "STATE")


if __name__ == "__main__":
    unittest.main()
