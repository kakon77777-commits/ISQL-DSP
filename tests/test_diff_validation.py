import unittest

from isql_dsr.diff import diff_states
from isql_dsr.events import TransitionEvent
from isql_dsr.model import PointValue, SemanticProjection, SemanticState, SpectrumAxis, TypedRelation
from isql_dsr.runtime import apply_event
from isql_dsr.validation import validate_state


class DiffTests(unittest.TestCase):
    def test_diff_reports_semantic_changes_by_identity(self):
        left = SemanticState(
            identity="isql:demo:alpha",
            context={"domain": "a", "same": 1},
            axes=(
                SpectrumAxis("changed", "unit", PointValue(1)),
                SpectrumAxis("removed", "unit", PointValue(2)),
            ),
            relations=(TypedRelation("a", "r", "b"),),
            projections=(SemanticProjection("p", "text/plain", "old"),),
        )
        right = SemanticState(
            identity="isql:demo:alpha",
            revision=1,
            context={"domain": "b", "same": 1, "new": True},
            axes=(
                SpectrumAxis("changed", "unit", PointValue(9)),
                SpectrumAxis("added", "unit", PointValue(3)),
            ),
            relations=(TypedRelation("a", "r2", "c"),),
            projections=(SemanticProjection("p", "text/plain", "new"), SemanticProjection("q", "application/json", {"x": 1})),
        )
        diff = diff_states(left, right)
        self.assertEqual(diff.added_axes, ("added",))
        self.assertEqual(diff.removed_axes, ("removed",))
        self.assertEqual(diff.changed_axes, ("changed",))
        self.assertEqual(diff.changed_context_keys, ("domain", "new"))
        self.assertEqual(len(diff.added_relations), 1)
        self.assertEqual(len(diff.removed_relations), 1)
        self.assertEqual(diff.added_projections, ("q",))
        self.assertEqual(diff.changed_projections, ("p",))


class ValidationTests(unittest.TestCase):
    def test_validate_state_replays_history_from_genesis(self):
        genesis = SemanticState(identity="isql:demo:alpha")
        e1 = TransitionEvent.for_state(
            genesis,
            event_id="e1",
            operation="upsert_axis",
            payload={"axis": SpectrumAxis("x", "unit", PointValue(1)).to_dict()},
        )
        s1 = apply_event(genesis, e1).state
        e2 = TransitionEvent.for_state(
            s1,
            event_id="e2",
            operation="set_context",
            payload={"context": {"domain": "demo"}},
        )
        final = apply_event(s1, e2).state
        report = validate_state(final, genesis=genesis)
        self.assertTrue(report.valid)
        self.assertEqual(report.checked_history_records, 2)
        self.assertEqual(report.errors, ())

    def test_validate_state_detects_tampered_history(self):
        genesis = SemanticState(identity="isql:demo:alpha")
        event = TransitionEvent.for_state(
            genesis,
            event_id="e1",
            operation="set_context",
            payload={"context": {"x": 1}},
        )
        final = apply_event(genesis, event).state
        history = list(final.history)
        history[0] = dict(history[0])
        history[0]["previous_hash"] = "0" * 64
        tampered = SemanticState(
            identity=final.identity,
            revision=final.revision,
            context=final.context,
            axes=final.axes,
            relations=final.relations,
            projections=final.projections,
            history=tuple(history),
        )
        report = validate_state(tampered, genesis=genesis)
        self.assertFalse(report.valid)
        self.assertIn("HISTORY_PREVIOUS_HASH_MISMATCH_AT_0", report.errors)


if __name__ == "__main__":
    unittest.main()
