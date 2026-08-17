import json
import unittest

from isql_dsr.bridge import CoreStateEnvelope, to_core_state_envelope
from isql_dsr.canonical import canonical_json, state_hash
from isql_dsr.model import PointValue, SemanticState, SpectrumAxis


class BridgeTests(unittest.TestCase):
    def test_core_state_envelope_preserves_full_canonical_state(self):
        state = SemanticState(
            identity="isql:demo:alpha",
            revision=2,
            context={"language": "zh-Hant"},
            axes=(SpectrumAxis("priority", "ordinal", PointValue(3)),),
            history=({"note": "historical fixture"}, {"note": "second"}),
        )
        envelope = to_core_state_envelope(state)
        self.assertEqual(envelope.domain, "STATE")
        self.assertEqual(envelope.resolution, "R2")
        self.assertEqual(envelope.state_hash, state_hash(state))
        self.assertEqual(envelope.payload_json, canonical_json(state))
        self.assertEqual(envelope.to_state(), state)
        self.assertEqual(CoreStateEnvelope.from_dict(envelope.to_dict()), envelope)

    def test_envelope_payload_is_valid_utf8_json_and_not_registry_id_semantics(self):
        state = SemanticState(identity="isql:測試:alpha")
        envelope = to_core_state_envelope(state)
        parsed = json.loads(envelope.payload_json)
        self.assertEqual(parsed["identity"], state.identity)
        self.assertIn("axes", parsed)
        self.assertNotIn("semantic_registry_id", envelope.to_dict())


if __name__ == "__main__":
    unittest.main()
