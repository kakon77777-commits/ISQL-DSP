import unittest

from isql_dsr import PointValue, SemanticState, SpectrumAxis, TransitionEvent, TypedRelation, apply_event
from isql_dsr.canonical import state_hash
from isql_dsr.fusion import SemanticProposal, fuse_proposals
from isql_dsr.validation import validate_state


class FusionTests(unittest.TestCase):
    def _base(self):
        return SemanticState(
            identity="demo:fusion",
            axes=(SpectrumAxis("risk", "ordinal", PointValue("unknown"), uncertainty=0.9),),
        )

    def _proposal(self, base, proposal_id, source_id, value, uncertainty, *, weight=1.0, relation=False):
        relations = (TypedRelation("risk", "affects", "deployment"),) if relation else ()
        return SemanticProposal.for_state(
            base,
            proposal_id=proposal_id,
            source_id=source_id,
            source_weight=weight,
            axes=(SpectrumAxis("risk", "ordinal", PointValue(value), uncertainty=uncertainty, resolution=2),),
            relations=relations,
        )

    def test_fusion_is_deterministic_under_proposal_reordering_and_uses_uncertainty(self):
        base = self._base()
        p1 = self._proposal(base, "p1", "model-a", "high", 0.1)
        p2 = self._proposal(base, "p2", "model-b", "high", 0.2)
        p3 = self._proposal(base, "p3", "model-c", "low", 0.1)
        a = fuse_proposals(base, [p1, p2, p3], axis_threshold=0.5)
        b = fuse_proposals(base, [p3, p1, p2], axis_threshold=0.5)
        self.assertEqual(a.to_dict(), b.to_dict())
        fused = {axis.key: axis for axis in a.axes}["risk"]
        self.assertEqual(fused.value, PointValue("high"))
        self.assertAlmostEqual(fused.uncertainty, 1.0 - (0.9 + 0.8) / 3.0)
        self.assertEqual(a.conflicts, ())

    def test_tied_disagreement_retains_base_axis_and_emits_conflict(self):
        base = self._base()
        p1 = self._proposal(base, "p1", "model-a", "high", 0.0)
        p2 = self._proposal(base, "p2", "model-b", "low", 0.0)
        result = fuse_proposals(base, [p1, p2], axis_threshold=0.5)
        fused = {axis.key: axis for axis in result.axes}["risk"]
        self.assertEqual(fused.value, PointValue("unknown"))
        self.assertEqual(len(result.conflicts), 1)
        self.assertEqual(result.conflicts[0].kind, "axis")
        self.assertEqual(result.conflicts[0].reason, "TIED_SUPPORT")

    def test_stale_proposal_fails_closed(self):
        base = self._base()
        proposal = SemanticProposal(
            proposal_id="stale",
            source_id="model-a",
            identity=base.identity,
            base_revision=base.revision,
            base_hash="0" * 64,
            source_weight=1.0,
            axes=(),
            relations=(),
        )
        with self.assertRaisesRegex(Exception, "PROPOSAL_BASE_HASH_MISMATCH"):
            fuse_proposals(base, [proposal])

    def test_fusion_event_is_replayable_and_records_decision(self):
        base = self._base()
        p1 = self._proposal(base, "p1", "model-a", "high", 0.1, relation=True)
        p2 = self._proposal(base, "p2", "model-b", "high", 0.1, relation=True)
        event = TransitionEvent.for_state(
            base,
            event_id="evt-fuse",
            operation="fuse_proposals",
            payload={
                "proposals": [p2.to_dict(), p1.to_dict()],
                "axis_threshold": 0.5,
                "relation_threshold": 0.5,
            },
        )
        result = apply_event(base, event)
        self.assertEqual(result.state.revision, 1)
        self.assertEqual(len(result.state.relations), 1)
        self.assertIn("result", result.state.history[-1])
        self.assertIn("fusion", result.state.history[-1]["result"])
        report = validate_state(result.state, genesis=base)
        self.assertTrue(report.valid, report.errors)


if __name__ == "__main__":
    unittest.main()
