import unittest

from isql_dsr import SemanticState, TransitionEvent, TypedRelation, apply_event, state_hash
from isql_dsr.model import TopologyDescriptor
from isql_dsr.topology import compute_topology_descriptors, topology_basis_hash


class TopologyTests(unittest.TestCase):
    def _state(self):
        return SemanticState(
            identity="demo:topology",
            relations=(
                TypedRelation("A", "linked", "B"),
                TypedRelation("B", "linked", "C"),
                TypedRelation("C", "linked", "A"),
                TypedRelation("D", "linked", "E"),
            ),
        )

    def test_builtin_descriptors_are_deterministic_and_bound_to_relation_basis(self):
        state = self._state()
        basis = topology_basis_hash(state)
        descriptors = compute_topology_descriptors(
            state,
            methods=("graph.cycle_rank", "graph.components"),
        )
        self.assertEqual([x.descriptor_id for x in descriptors], ["graph.components", "graph.cycle_rank"])
        values = {x.descriptor_id: x.value for x in descriptors}
        self.assertEqual(values["graph.components"], 2)
        self.assertEqual(values["graph.cycle_rank"], 1)
        self.assertTrue(all(x.basis_hash == basis for x in descriptors))
        self.assertTrue(all(x.confidence == 1.0 for x in descriptors))

    def test_descriptor_round_trip_and_state_order_are_canonical(self):
        state = self._state()
        basis = topology_basis_hash(state)
        a = TopologyDescriptor("z.custom", "custom", basis, {"score": 2}, confidence=0.8)
        b = TopologyDescriptor("a.custom", "custom", basis, [1, 2, 3], confidence=0.7)
        rebuilt = SemanticState.from_dict(SemanticState(identity=state.identity, topology=(a, b)).to_dict())
        self.assertEqual([x.descriptor_id for x in rebuilt.topology], ["a.custom", "z.custom"])
        self.assertEqual(rebuilt.topology[0], b)

    def test_refresh_topology_event_is_replayable_and_relation_change_invalidates_descriptors(self):
        state = self._state()
        refresh = TransitionEvent.for_state(
            state,
            event_id="evt-topology",
            operation="refresh_topology",
            payload={"methods": ["graph.components", "graph.cycle_rank"]},
        )
        refreshed = apply_event(state, refresh).state
        self.assertEqual(len(refreshed.topology), 2)

        add_relation = TransitionEvent.for_state(
            refreshed,
            event_id="evt-rel",
            operation="upsert_relation",
            payload={"relation": {"subject": "E", "predicate": "linked", "object": "A"}},
        )
        changed = apply_event(refreshed, add_relation).state
        self.assertEqual(changed.topology, ())
        self.assertNotEqual(state_hash(refreshed), state_hash(changed))

    def test_custom_descriptor_rejects_wrong_basis_hash(self):
        state = self._state()
        event = TransitionEvent.for_state(
            state,
            event_id="evt-custom-topology",
            operation="upsert_topology_descriptor",
            payload={
                "descriptor": {
                    "descriptor_id": "custom.score",
                    "method": "custom",
                    "basis_hash": "0" * 64,
                    "value": 7,
                    "confidence": 0.9,
                    "parameters": {},
                }
            },
        )
        with self.assertRaisesRegex(Exception, "TOPOLOGY_BASIS_HASH_MISMATCH"):
            apply_event(state, event)

    def test_validation_rejects_stale_topology_basis_even_without_genesis(self):
        from isql_dsr.validation import validate_state
        state = self._state()
        bad = TopologyDescriptor("custom.score", "custom", "0" * 64, 1)
        tampered = SemanticState(identity=state.identity, relations=state.relations, topology=(bad,))
        report = validate_state(tampered)
        self.assertFalse(report.valid)
        self.assertIn("TOPOLOGY_BASIS_HASH_MISMATCH:custom.score", report.errors)


if __name__ == "__main__":
    unittest.main()
