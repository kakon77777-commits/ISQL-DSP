import unittest

from isql_dsr.model import (
    PointValue, SemanticProjection, SemanticState, SpectrumAxis, TopologyDescriptor, TypedRelation,
)
from isql_dsr.registry import NativeSymbolRegistry, extend_registry_for_state
from isql_dsr.machine import (
    compile_registered_state,
    decode_registered_state,
    encode_registered_state,
    inspect_registered_state,
    registered_state_hash,
)
from isql_dsr.topology import topology_basis_hash


class RegisteredStateV04Tests(unittest.TestCase):
    def _inspection(self):
        base = SemanticState(
            identity="obj:native",
            revision=4,
            context={"mode": "machine", "priority": 7},
            axes=(SpectrumAxis("risk", "ordinal", PointValue("high"), 0.1, 2),),
            relations=(TypedRelation("risk", "affects", "deploy"),),
            projections=(SemanticProjection("p:raw", "application/octet-stream", [1, 2, 3]),),
        )
        return SemanticState(
            identity=base.identity,
            revision=base.revision,
            context=base.context,
            axes=base.axes,
            relations=base.relations,
            topology=(TopologyDescriptor("graph.components", "graph.components", topology_basis_hash(base), 1),),
            projections=base.projections,
        )

    def test_registered_snapshot_uses_numeric_refs_and_excludes_identifier_text(self):
        state = self._inspection()
        registry = extend_registry_for_state(NativeSymbolRegistry(), state)
        machine = compile_registered_state(state, registry)
        raw = encode_registered_state(machine)
        self.assertIsInstance(machine.identity_ref, int)
        for forbidden in (b"obj:native", b"risk", b"ordinal", b"affects", b"deploy", b"graph.components", b"p:raw", b"application/octet-stream"):
            self.assertNotIn(forbidden, raw)

    def test_registered_snapshot_round_trip_and_inspection_projection(self):
        state = self._inspection()
        registry = extend_registry_for_state(NativeSymbolRegistry(), state)
        machine = compile_registered_state(state, registry)
        raw = encode_registered_state(machine)
        decoded = decode_registered_state(raw, registry)
        self.assertEqual(machine, decoded)
        self.assertEqual(raw, encode_registered_state(decoded))
        inspected = inspect_registered_state(decoded, registry)
        self.assertEqual(state, inspected)
        self.assertEqual(registered_state_hash(machine), registered_state_hash(decoded))

    def test_newer_append_only_registry_can_decode_old_snapshot(self):
        state = self._inspection()
        registry = extend_registry_for_state(NativeSymbolRegistry(), state)
        machine = compile_registered_state(state, registry)
        raw = encode_registered_state(machine)
        newer, _ = registry.intern_text(4, "future-atom")
        decoded = decode_registered_state(raw, newer)
        self.assertEqual(machine, decoded)

    def test_wrong_registry_prefix_fails_closed(self):
        state = self._inspection()
        registry = extend_registry_for_state(NativeSymbolRegistry(), state)
        raw = encode_registered_state(compile_registered_state(state, registry))
        wrong = NativeSymbolRegistry()
        # Build the same number of entries with incompatible payloads.
        for idx, entry in enumerate(registry.entries, 1):
            wrong, _ = wrong.intern(entry.namespace, f"wrong-{idx}".encode())
        with self.assertRaises(Exception):
            decode_registered_state(raw, wrong)

    def test_equivalent_inspection_order_compiles_to_identical_bytes(self):
        state = self._inspection()
        other = SemanticState.from_dict({
            **state.to_dict(),
            "context": {"priority": 7, "mode": "machine"},
            "relations": list(reversed(state.to_dict()["relations"])),
            "axes": list(reversed(state.to_dict()["axes"])),
        })
        registry = extend_registry_for_state(NativeSymbolRegistry(), state)
        left = compile_registered_state(state, registry)
        right = compile_registered_state(other, registry)
        self.assertEqual(encode_registered_state(left), encode_registered_state(right))


if __name__ == "__main__":
    unittest.main()
