import unittest

from isql_dsr.errors import DSRValidationError
from isql_dsr.model import (
    CandidateSetValue,
    IntervalValue,
    PointValue,
    SemanticProjection,
    SemanticState,
    SpectrumAxis,
    TypedRelation,
)


class ValueModelTests(unittest.TestCase):
    def test_point_interval_and_candidates_have_typed_dicts(self):
        self.assertEqual(PointValue(0.5).to_dict(), {"kind": "point", "value": 0.5})
        self.assertEqual(
            IntervalValue(0.2, 0.8).to_dict(),
            {"kind": "interval", "lower": 0.2, "upper": 0.8},
        )
        self.assertEqual(
            CandidateSetValue(("a", "b")).to_dict(),
            {"kind": "candidates", "values": ["a", "b"]},
        )

    def test_interval_rejects_reverse_bounds(self):
        with self.assertRaisesRegex(DSRValidationError, "INTERVAL_LOWER_GT_UPPER"):
            IntervalValue(2, 1)

    def test_candidates_reject_duplicates(self):
        with self.assertRaisesRegex(DSRValidationError, "CANDIDATE_VALUES_MUST_BE_UNIQUE"):
            CandidateSetValue(("a", "a"))


class SemanticStateTests(unittest.TestCase):
    def _state(self):
        return SemanticState(
            identity="isql:demo:alpha",
            revision=0,
            context={"language": "zh-Hant", "domain": "demo"},
            axes=(
                SpectrumAxis("certainty", "unit", IntervalValue(0.6, 0.9), uncertainty=0.1, resolution=2),
                SpectrumAxis("priority", "ordinal", PointValue(3), uncertainty=0.0, resolution=1),
            ),
            relations=(TypedRelation("alpha", "supports", "beta"),),
            projections=(SemanticProjection("natural-language", "text/plain", "alpha supports beta"),),
            history=(),
        )

    def test_state_normalizes_order_deterministically(self):
        state = self._state()
        self.assertEqual([x.key for x in state.axes], ["certainty", "priority"])
        self.assertEqual([x.projection_id for x in state.projections], ["natural-language"])

    def test_state_rejects_duplicate_axis_keys(self):
        with self.assertRaisesRegex(DSRValidationError, "DUPLICATE_AXIS_KEY"):
            SemanticState(
                identity="isql:demo:alpha",
                axes=(
                    SpectrumAxis("x", "unit", PointValue(1)),
                    SpectrumAxis("x", "unit", PointValue(2)),
                ),
            )

    def test_state_round_trips_via_dict(self):
        state = self._state()
        restored = SemanticState.from_dict(state.to_dict())
        self.assertEqual(restored, state)


if __name__ == "__main__":
    unittest.main()
