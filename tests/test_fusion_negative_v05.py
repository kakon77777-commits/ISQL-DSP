import unittest
from unittest.mock import patch

from isql_dsr.canonical import state_hash
from isql_dsr.events import TransitionEvent
from isql_dsr.fusion import SemanticProposal
from isql_dsr.machine import compile_registered_state
from isql_dsr.model import SemanticState, TypedRelation
from isql_dsr.registry import NativeSymbolRegistry, extend_registry_for_events, extend_registry_for_state
from isql_dsr.stream import build_event_stream, replay_native_stream


class NegativeFusionV05Tests(unittest.TestCase):
    def test_majority_negative_relation_vote_materializes_negative_assertion(self):
        relation = TypedRelation("a", "supports", "b")
        base = SemanticState(identity="fusion-neg", relations=(relation,))
        p1 = SemanticProposal.for_state(base, proposal_id="p1", source_id="m1", negative_relations=(relation,))
        p2 = SemanticProposal.for_state(base, proposal_id="p2", source_id="m2", negative_relations=(relation,))
        p3 = SemanticProposal.for_state(base, proposal_id="p3", source_id="m3")
        event = TransitionEvent.for_state(base, event_id="f-neg", operation="fuse_proposals", payload={"proposals": [p1.to_dict(), p2.to_dict(), p3.to_dict()], "relation_threshold": 0.5})
        registry = extend_registry_for_state(NativeSymbolRegistry(), base)
        registry = extend_registry_for_events(registry, (event,))
        stream = build_event_stream(base, (event,), registry)
        with patch("isql_dsr.stream.inspect_registered_state", side_effect=AssertionError), patch("isql_dsr.stream.apply_event", side_effect=AssertionError):
            final = replay_native_stream(compile_registered_state(base, registry), stream, registry)
        self.assertEqual(final.relations, ())
        self.assertEqual(len(final.negative_relations), 1)

    def test_equal_positive_negative_votes_keep_base_and_report_conflict_in_inspection_runtime(self):
        from isql_dsr.runtime import apply_event
        relation = TypedRelation("a", "supports", "b")
        base = SemanticState(identity="fusion-conflict")
        pos = SemanticProposal.for_state(base, proposal_id="p1", source_id="m1", relations=(relation,))
        neg = SemanticProposal.for_state(base, proposal_id="p2", source_id="m2", negative_relations=(relation,))
        event = TransitionEvent.for_state(base, event_id="f-conflict", operation="fuse_proposals", payload={"proposals": [pos.to_dict(), neg.to_dict()], "relation_threshold": 0.5})
        result = apply_event(base, event).state
        decision = result.history[-1]["result"]["fusion"]
        self.assertEqual(result.relations, ())
        self.assertEqual(result.negative_relations, ())
        self.assertEqual(decision["conflicts"][0]["reason"], "POLARITY_CONFLICT")


if __name__ == "__main__":
    unittest.main()
