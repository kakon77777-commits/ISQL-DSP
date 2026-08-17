import unittest

from isql_dsr.events import TransitionEvent
from isql_dsr.model import PointValue, SemanticState, SpectrumAxis
from isql_dsr.native import decode_state, encode_state, operation_name, operation_opcode
from isql_dsr.runtime import apply_event


class NativeEventCodecTests(unittest.TestCase):
    def test_operation_opcode_mapping_is_stable_and_reversible(self):
        operations = [
            "set_context", "upsert_axis", "remove_axis", "upsert_relation",
            "remove_relation", "upsert_projection", "remove_projection",
            "refresh_topology", "upsert_topology_descriptor",
            "remove_topology_descriptor", "fuse_proposals",
        ]
        codes = [operation_opcode(name) for name in operations]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(all(code > 0 for code in codes))
        self.assertEqual(operations, [operation_name(code) for code in codes])

    def test_history_uses_numeric_opcode_not_operation_or_schema_labels(self):
        base = SemanticState(identity="native:event")
        event = TransitionEvent.for_state(
            base,
            event_id="evt-1",
            operation="upsert_axis",
            payload={"axis": SpectrumAxis("risk", "ordinal", PointValue(7), 0.25, 2).to_dict()},
        )
        state = apply_event(base, event).state
        data = encode_state(state)
        for forbidden in (b"upsert_axis", b'"event"', b'"payload"', b'"previous_hash"', b'"base_revision"'):
            self.assertNotIn(forbidden, data)
        self.assertEqual(state, decode_state(data))

    def test_fusion_history_does_not_embed_proposal_or_decision_field_names(self):
        from isql_dsr.fusion import SemanticProposal
        base = SemanticState(identity="native:fusion", axes=(SpectrumAxis("risk", "ordinal", PointValue("unknown"), 0.9, 0),))
        proposals = [
            SemanticProposal.for_state(base, proposal_id="p1", source_id="m1", axes=(SpectrumAxis("risk", "ordinal", PointValue("high"), 0.1, 1),)),
            SemanticProposal.for_state(base, proposal_id="p2", source_id="m2", axes=(SpectrumAxis("risk", "ordinal", PointValue("high"), 0.1, 1),)),
        ]
        event = TransitionEvent.for_state(
            base, event_id="f1", operation="fuse_proposals",
            payload={"proposals": [p.to_dict() for p in proposals], "axis_threshold": 0.5, "relation_threshold": 0.5},
        )
        state = apply_event(base, event).state
        data = encode_state(state)
        for forbidden in (b"proposal_id", b"source_weight", b"axis_threshold", b"relation_threshold", b'"fusion"', b"effective_support", b"support_ratio"):
            self.assertNotIn(forbidden, data)
        self.assertEqual(state, decode_state(data))


if __name__ == "__main__":
    unittest.main()
