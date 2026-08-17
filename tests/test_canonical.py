import unittest

from isql_dsr.canonical import canonical_bytes, canonical_json, state_hash
from isql_dsr.model import IntervalValue, PointValue, SemanticState, SpectrumAxis


class CanonicalTests(unittest.TestCase):
    def test_canonical_json_is_independent_of_axis_input_order(self):
        left = SemanticState(
            identity="isql:demo:alpha",
            axes=(
                SpectrumAxis("z", "unit", PointValue(1)),
                SpectrumAxis("a", "unit", IntervalValue(0.1, 0.2)),
            ),
        )
        right = SemanticState(
            identity="isql:demo:alpha",
            axes=tuple(reversed(left.axes)),
        )
        self.assertEqual(canonical_json(left), canonical_json(right))
        self.assertEqual(state_hash(left), state_hash(right))

    def test_canonical_bytes_are_native_and_hash_is_sha256_hex(self):
        state = SemanticState(identity="isql:測試:alpha")
        payload = canonical_bytes(state)
        self.assertNotEqual(payload, canonical_json(state).encode("utf-8"))
        self.assertRegex(state_hash(state), r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
