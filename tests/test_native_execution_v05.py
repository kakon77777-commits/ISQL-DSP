import unittest
from unittest.mock import patch

from isql_dsr.events import TransitionEvent
from isql_dsr.machine import compile_registered_state, inspect_registered_state, NativeRelation
from isql_dsr.model import SemanticState, TypedRelation
from isql_dsr.registry import NativeSymbolRegistry, extend_registry_for_events, extend_registry_for_state
from isql_dsr.stream import build_event_stream, replay_native_stream
from isql_dsr.canonical import state_hash


class NativeExecutionV05Tests(unittest.TestCase):
    def _base(self):
        relation = TypedRelation("a", "supports", "b")
        state = SemanticState(identity="obj", relations=(relation,))
        deny = TransitionEvent(
            event_id="e-deny", operation="deny_relation",
            payload={"relation": relation.to_dict()},
            base_revision=0, previous_hash=state_hash(state),
        )
        registry = extend_registry_for_state(NativeSymbolRegistry(), state)
        registry = extend_registry_for_events(registry, (deny,))
        return state, relation, deny, registry

    def test_deny_relation_moves_relation_to_negative_set(self):
        state, relation, deny, registry = self._base()
        stream = build_event_stream(state, (deny,), registry)
        native = replay_native_stream(compile_registered_state(state, registry), stream, registry)
        self.assertEqual(native.relations, ())
        self.assertEqual(len(native.negative_relations), 1)
        inspected = inspect_registered_state(native, registry)
        self.assertEqual(inspected.negative_relations, (relation,))

    def test_retract_relation_clears_positive_or_negative_assertion_idempotently(self):
        state, relation, deny, registry = self._base()
        first_stream = build_event_stream(state, (deny,), registry)
        denied_native = replay_native_stream(compile_registered_state(state, registry), first_stream, registry)
        denied = inspect_registered_state(denied_native, registry)
        retract = TransitionEvent(
            event_id="e-retract", operation="retract_relation",
            payload={"relation": relation.to_dict()},
            base_revision=denied.revision, previous_hash=state_hash(denied),
        )
        registry = extend_registry_for_events(registry, (retract,))
        stream = build_event_stream(denied, (retract,), registry)
        final = replay_native_stream(compile_registered_state(denied, registry), stream, registry)
        self.assertEqual(final.relations, ())
        self.assertEqual(final.negative_relations, ())

    def test_replay_no_longer_depends_on_inspection_runtime(self):
        state, _, deny, registry = self._base()
        stream = build_event_stream(state, (deny,), registry)
        genesis = compile_registered_state(state, registry)
        with patch("isql_dsr.stream.inspect_registered_state", side_effect=AssertionError("inspection forbidden")), \
             patch("isql_dsr.stream.apply_event", side_effect=AssertionError("semantic runtime forbidden")):
            final = replay_native_stream(genesis, stream, registry)
        self.assertEqual(len(final.negative_relations), 1)

    def test_native_topology_refresh_runs_without_semantic_adapter(self):
        relation = TypedRelation("a", "p", "b")
        state = SemanticState(identity="obj", relations=(relation,))
        refresh = TransitionEvent(
            event_id="e-top", operation="refresh_topology",
            payload={"methods": ["graph.components", "graph.cycle_rank"]},
            base_revision=0, previous_hash=state_hash(state),
        )
        registry = extend_registry_for_state(NativeSymbolRegistry(), state)
        registry = extend_registry_for_events(registry, (refresh,))
        stream = build_event_stream(state, (refresh,), registry)
        with patch("isql_dsr.stream.inspect_registered_state", side_effect=AssertionError), \
             patch("isql_dsr.stream.apply_event", side_effect=AssertionError):
            final = replay_native_stream(compile_registered_state(state, registry), stream, registry)
        values = sorted(x.value for x in final.topology)
        self.assertEqual(values, [0, 1])


if __name__ == "__main__":
    unittest.main()

class NativeFusionV05Tests(unittest.TestCase):
    def test_native_fusion_replay_runs_without_semantic_adapter(self):
        from isql_dsr.fusion import SemanticProposal
        from isql_dsr.model import PointValue, SpectrumAxis
        base = SemanticState(identity="fusion-native", axes=(SpectrumAxis("risk", "ordinal", PointValue("unknown"), 0.9, 0),))
        p1 = SemanticProposal.for_state(base, proposal_id="p1", source_id="m1", source_weight=1.0, axes=(SpectrumAxis("risk", "ordinal", PointValue("high"), 0.1, 2),))
        p2 = SemanticProposal.for_state(base, proposal_id="p2", source_id="m2", source_weight=1.0, axes=(SpectrumAxis("risk", "ordinal", PointValue("high"), 0.2, 3),))
        event = TransitionEvent.for_state(base, event_id="f1", operation="fuse_proposals", payload={"proposals": [p1.to_dict(), p2.to_dict()]})
        registry = extend_registry_for_state(NativeSymbolRegistry(), base)
        registry = extend_registry_for_events(registry, (event,))
        stream = build_event_stream(base, (event,), registry)
        with patch("isql_dsr.stream.inspect_registered_state", side_effect=AssertionError), \
             patch("isql_dsr.stream.apply_event", side_effect=AssertionError):
            final = replay_native_stream(compile_registered_state(base, registry), stream, registry)
        self.assertEqual(final.axes[0].resolution, 3)
        self.assertLess(final.axes[0].uncertainty, 0.2)
