import hashlib
import json
import unittest

from isql_dsr.canonical import canonical_bytes, canonical_json, inspection_json, state_hash
from isql_dsr.events import TransitionEvent
from isql_dsr.model import PointValue, SemanticState, SpectrumAxis
from isql_dsr.native import encode_state, native_state_hash
from isql_dsr.runtime import apply_event


class NativeAuthorityTests(unittest.TestCase):
    def test_native_bytes_are_authoritative_for_canonical_bytes_and_hash(self):
        state = SemanticState(identity="authority", context={"b": 2, "a": 1})
        native = encode_state(state)
        self.assertEqual(native, canonical_bytes(state))
        self.assertEqual(hashlib.sha256(native).hexdigest(), state_hash(state))
        self.assertEqual(native_state_hash(state), state_hash(state))
        self.assertNotEqual(native, inspection_json(state).encode("utf-8"))

    def test_inspection_json_is_reversible_but_not_hash_authority(self):
        state = SemanticState(identity="authority", axes=(SpectrumAxis("x", "n", PointValue(3)),))
        pretty = json.dumps(state.to_dict(), ensure_ascii=False, indent=4)
        restored = SemanticState.from_dict(json.loads(pretty))
        self.assertEqual(state_hash(state), state_hash(restored))
        self.assertEqual(canonical_json(state), inspection_json(state))

    def test_transition_hash_chain_uses_native_hash(self):
        base = SemanticState(identity="authority")
        event = TransitionEvent.for_state(base, event_id="e", operation="set_context", payload={"context": {"x": 1}})
        self.assertEqual(native_state_hash(base), event.previous_hash)
        result = apply_event(base, event)
        self.assertEqual(native_state_hash(result.state), result.next_hash)


if __name__ == "__main__":
    unittest.main()
