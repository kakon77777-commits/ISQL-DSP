import unittest

from isql_dsr.model import (
    CandidateSetValue,
    IntervalValue,
    PointValue,
    SemanticProjection,
    SemanticState,
    SpectrumAxis,
    TopologyDescriptor,
    TypedRelation,
)
from isql_dsr.native import decode_state, encode_state, native_state_hash
from isql_dsr.topology import topology_basis_hash


class NativeStateCodecTests(unittest.TestCase):
    def _state(self) -> SemanticState:
        base = SemanticState(
            identity="obj:α",
            revision=7,
            context={"mode": "machine", "level": 3},
            axes=(
                SpectrumAxis("zeta", "scalar", PointValue("opaque"), 0.2, 4),
                SpectrumAxis("beta", "range", IntervalValue(-1, 2.5), 0.1, 2),
                SpectrumAxis("alpha", "choice", CandidateSetValue(("x", 7, True)), 0.4, 1),
            ),
            relations=(
                TypedRelation("node:b", "supports", "node:c"),
                TypedRelation("node:a", "depends", "node:b"),
            ),
            projections=(
                SemanticProjection("p:1", "application/octet-stream", {"v": [3, 2, 1]}),
            ),
        )
        basis = topology_basis_hash(base)
        return SemanticState(
            identity=base.identity,
            revision=base.revision,
            context=base.context,
            axes=tuple(reversed(base.axes)),
            relations=tuple(reversed(base.relations)),
            topology=(TopologyDescriptor("graph.components", "graph.components", basis, 1),),
            projections=base.projections,
        )

    def test_equivalent_state_order_produces_identical_native_bytes(self):
        left = self._state()
        right = SemanticState.from_dict({
            **left.to_dict(),
            "context": {"level": 3, "mode": "machine"},
            "axes": list(reversed(left.to_dict()["axes"])),
            "relations": list(reversed(left.to_dict()["relations"])),
        })
        self.assertEqual(encode_state(left), encode_state(right))
        self.assertEqual(native_state_hash(left), native_state_hash(right))

    def test_native_bytes_do_not_serialize_json_schema_field_names(self):
        data = encode_state(self._state())
        for label in (b'"identity"', b'"axes"', b'"relations"', b'"topology"', b'"history"', b'"schema"'):
            self.assertNotIn(label, data)

    def test_native_state_round_trip_is_exact(self):
        state = self._state()
        encoded = encode_state(state)
        decoded = decode_state(encoded)
        self.assertEqual(state, decoded)
        self.assertEqual(encoded, encode_state(decoded))


if __name__ == "__main__":
    unittest.main()
