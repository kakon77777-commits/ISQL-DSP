import unittest

from isql_dsr.events import TransitionEvent
from isql_dsr.machine import compile_registered_state, registered_state_hash
from isql_dsr.model import PointValue, SemanticState, SpectrumAxis, TypedRelation
from isql_dsr.registry import NativeSymbolRegistry, extend_registry_for_events, extend_registry_for_state
from isql_dsr.runtime import apply_event
from isql_dsr.stream import (
    build_event_stream,
    decode_event_stream,
    encode_event_stream,
    replay_native_stream,
)


class NativeEventStreamV04Tests(unittest.TestCase):
    def _chain(self):
        genesis = SemanticState(identity="obj:stream")
        e1 = TransitionEvent.for_state(
            genesis,
            event_id="evt-axis",
            operation="upsert_axis",
            payload={"axis": SpectrumAxis("risk", "ordinal", PointValue(3), 0.1, 1).to_dict()},
        )
        s1 = apply_event(genesis, e1).state
        e2 = TransitionEvent.for_state(
            s1,
            event_id="evt-rel",
            operation="upsert_relation",
            payload={"relation": TypedRelation("risk", "affects", "deploy").to_dict()},
        )
        s2 = apply_event(s1, e2).state
        registry = extend_registry_for_state(NativeSymbolRegistry(), genesis)
        registry = extend_registry_for_events(registry, (e1, e2))
        return genesis, (e1, e2), s2, registry

    def test_stream_round_trip_and_replay_matches_final_registered_snapshot(self):
        genesis, events, final, registry = self._chain()
        stream = build_event_stream(genesis, events, registry)
        raw = encode_event_stream(stream)
        decoded = decode_event_stream(raw, registry)
        self.assertEqual(stream, decoded)
        self.assertEqual(raw, encode_event_stream(decoded))
        machine_genesis = compile_registered_state(genesis, registry)
        replayed = replay_native_stream(machine_genesis, decoded, registry)
        expected = compile_registered_state(final, registry)
        self.assertEqual(registered_state_hash(expected), registered_state_hash(replayed))
        self.assertEqual(expected.revision, replayed.revision)

    def test_stream_does_not_repeat_semantic_identifier_or_operation_labels(self):
        genesis, events, _, registry = self._chain()
        raw = encode_event_stream(build_event_stream(genesis, events, registry))
        for forbidden in (b"obj:stream", b"evt-axis", b"evt-rel", b"risk", b"ordinal", b"affects", b"deploy", b"upsert_axis", b"upsert_relation", b"payload", b"previous_hash"):
            self.assertNotIn(forbidden, raw)

    def test_stream_registry_prefix_mismatch_fails_closed(self):
        genesis, events, _, registry = self._chain()
        raw = encode_event_stream(build_event_stream(genesis, events, registry))
        wrong = NativeSymbolRegistry()
        for idx, entry in enumerate(registry.entries, 1):
            wrong, _ = wrong.intern(entry.namespace, f"wrong-{idx}".encode())
        with self.assertRaises(Exception):
            decode_event_stream(raw, wrong)

    def test_tampered_record_next_hash_is_rejected_on_replay(self):
        genesis, events, _, registry = self._chain()
        stream = build_event_stream(genesis, events, registry)
        first = stream.records[0]
        tampered_hash = ("00" if first.next_hash[:2] != "00" else "01") + first.next_hash[2:]
        tampered = type(stream)(
            registry_revision=stream.registry_revision,
            registry_hash=stream.registry_hash,
            genesis_hash=stream.genesis_hash,
            records=(type(first)(first.event, tampered_hash),) + stream.records[1:],
        )
        with self.assertRaises(Exception):
            replay_native_stream(compile_registered_state(genesis, registry), tampered, registry)

    def test_stream_replays_fusion_and_topology_operations(self):
        from isql_dsr.fusion import SemanticProposal
        genesis = SemanticState(
            identity="obj:complex-stream",
            axes=(SpectrumAxis("risk", "ordinal", PointValue("unknown"), 0.9, 0),),
        )
        proposals = [
            SemanticProposal.for_state(
                genesis, proposal_id="p1", source_id="m1",
                axes=(SpectrumAxis("risk", "ordinal", PointValue("high"), 0.1, 1),),
                relations=(TypedRelation("risk", "affects", "deploy"),),
            ),
            SemanticProposal.for_state(
                genesis, proposal_id="p2", source_id="m2",
                axes=(SpectrumAxis("risk", "ordinal", PointValue("high"), 0.2, 2),),
                relations=(TypedRelation("risk", "affects", "deploy"),),
            ),
        ]
        e1 = TransitionEvent.for_state(
            genesis, event_id="fuse-1", operation="fuse_proposals",
            payload={"proposals": [x.to_dict() for x in proposals], "axis_threshold": 0.5, "relation_threshold": 0.5},
        )
        s1 = apply_event(genesis, e1).state
        e2 = TransitionEvent.for_state(
            s1, event_id="topo-1", operation="refresh_topology",
            payload={"methods": ["graph.components", "graph.cycle_rank"]},
        )
        final = apply_event(s1, e2).state
        registry = extend_registry_for_state(NativeSymbolRegistry(), genesis)
        registry = extend_registry_for_events(registry, (e1, e2))
        stream = build_event_stream(genesis, (e1, e2), registry)
        replayed = replay_native_stream(compile_registered_state(genesis, registry), stream, registry)
        self.assertEqual(compile_registered_state(final, registry), replayed)
        self.assertEqual(replayed.revision, 2)
        self.assertEqual(len(replayed.topology), 2)

    def test_materialized_history_is_not_embedded_in_registered_snapshot(self):
        genesis, events, final, registry = self._chain()
        stream = build_event_stream(genesis, events, registry)
        replayed = replay_native_stream(compile_registered_state(genesis, registry), stream, registry)
        final_without_history = SemanticState.from_dict({**final.to_dict(), "history": []})
        expected = compile_registered_state(final_without_history, registry)
        self.assertEqual(expected, replayed)


if __name__ == "__main__":
    unittest.main()
