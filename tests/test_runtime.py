import unittest

from isql_dsr.canonical import state_hash
from isql_dsr.errors import DSRExecutionError
from isql_dsr.events import TransitionEvent
from isql_dsr.model import (
    IntervalValue,
    PointValue,
    SemanticProjection,
    SemanticState,
    SpectrumAxis,
    TypedRelation,
)
from isql_dsr.runtime import apply_event, replay


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.genesis = SemanticState(identity="isql:demo:alpha", context={"language": "zh-Hant"})

    def event(self, event_id, operation, payload, state=None):
        return TransitionEvent.for_state(
            state or self.genesis,
            event_id=event_id,
            operation=operation,
            payload=payload,
        )

    def test_upsert_axis_increments_revision_and_records_hash_chain(self):
        event = self.event(
            "e1",
            "upsert_axis",
            {"axis": SpectrumAxis("certainty", "unit", IntervalValue(0.6, 0.9)).to_dict()},
        )
        result = apply_event(self.genesis, event)
        self.assertEqual(result.previous_hash, state_hash(self.genesis))
        self.assertEqual(result.state.revision, 1)
        self.assertEqual(result.state.axes[0].key, "certainty")
        self.assertEqual(result.next_hash, state_hash(result.state))
        self.assertEqual(result.state.history[-1]["event"]["event_id"], "e1")
        self.assertEqual(result.state.history[-1]["previous_hash"], state_hash(self.genesis))

    def test_context_relation_projection_and_removal_operations(self):
        events = []
        s = self.genesis
        specs = [
            ("e1", "set_context", {"context": {"language": "zh-Hant", "domain": "research"}}),
            ("e2", "upsert_axis", {"axis": SpectrumAxis("priority", "ordinal", PointValue(3)).to_dict()}),
            ("e3", "upsert_relation", {"relation": TypedRelation("alpha", "supports", "beta").to_dict()}),
            ("e4", "upsert_projection", {"projection": SemanticProjection("nl", "text/plain", "alpha supports beta").to_dict()}),
            ("e5", "remove_axis", {"key": "priority"}),
            ("e6", "remove_relation", {"subject": "alpha", "predicate": "supports", "object": "beta"}),
            ("e7", "remove_projection", {"projection_id": "nl"}),
        ]
        for event_id, operation, payload in specs:
            event = TransitionEvent.for_state(s, event_id=event_id, operation=operation, payload=payload)
            events.append(event)
            s = apply_event(s, event).state
        self.assertEqual(s.context["domain"], "research")
        self.assertEqual(s.axes, ())
        self.assertEqual(s.relations, ())
        self.assertEqual(s.projections, ())
        self.assertEqual(s.revision, 7)
        self.assertEqual(replay(self.genesis, events), s)

    def test_stale_event_fails_closed(self):
        event = self.event("e1", "set_context", {"context": {"x": 1}})
        first = apply_event(self.genesis, event).state
        with self.assertRaisesRegex(DSRExecutionError, "EVENT_BASE_REVISION_MISMATCH"):
            apply_event(first, event)


if __name__ == "__main__":
    unittest.main()
