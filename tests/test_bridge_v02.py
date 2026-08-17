import json
import re
import unittest

from isql_dsr import PointValue, SemanticState, SpectrumAxis, TypedRelation
from isql_dsr.bridge import (
    CoreDomainEnvelope,
    SemanticSnapshot,
    decode_core_envelope,
    to_core_bundle,
    to_core_sem_envelope,
    to_core_state_envelope,
)
from isql_dsr.canonical import state_hash


CORE_RE = re.compile(r"^ISQL(?P<version>[1-9][0-9]*):(?P<domain>[A-Z]+):(?P<resolution>R[0-4]):(?P<control>[A-Z]+)(?P<payload>[0-9]+)$")


class BridgeV02Tests(unittest.TestCase):
    def _state(self):
        return SemanticState(
            identity="demo:bridge-v02",
            revision=1,
            context={"task": "deploy"},
            axes=(SpectrumAxis("risk", "ordinal", PointValue("high"), uncertainty=0.2),),
            relations=(TypedRelation("risk", "affects", "deployment"),),
            projections=(),
            history=({"note": "fixture"},),
        )

    def test_sem_envelope_excludes_context_and_history_but_preserves_semantics(self):
        state = self._state()
        envelope = to_core_sem_envelope(state)
        self.assertEqual(envelope.domain, "SEM")
        self.assertEqual(envelope.resolution, "R2")
        snapshot = decode_core_envelope(envelope)
        self.assertIsInstance(snapshot, SemanticSnapshot)
        payload = json.loads(envelope.payload_json)
        self.assertNotIn("context", payload)
        self.assertNotIn("history", payload)
        self.assertNotIn("revision", payload)
        self.assertEqual(snapshot.identity, state.identity)
        self.assertEqual(snapshot.axes, state.axes)
        self.assertEqual(snapshot.relations, state.relations)

    def test_state_envelope_is_lossless_and_both_wires_are_core_parseable_digits_only(self):
        state = self._state()
        bundle = to_core_bundle(state)
        for envelope, expected_domain in ((bundle.sem, "SEM"), (bundle.state, "STATE")):
            self.assertTrue(envelope.payload_digits.isascii())
            self.assertTrue(envelope.payload_digits.isdigit())
            self.assertEqual(len(envelope.payload_digits) % 3, 0)
            match = CORE_RE.fullmatch(envelope.wire)
            self.assertIsNotNone(match)
            self.assertEqual(match.group("domain"), expected_domain)
            self.assertEqual(match.group("payload"), envelope.payload_digits)
        self.assertEqual(decode_core_envelope(bundle.state), state)
        self.assertEqual(bundle.state.state_hash, state_hash(state))

    def test_envelope_round_trip_rejects_tampered_decimal_payload(self):
        state = self._state()
        envelope = to_core_state_envelope(state)
        raw = envelope.to_dict()
        raw["payload_digits"] = ("255" if envelope.payload_digits[:3] != "255" else "254") + envelope.payload_digits[3:]
        with self.assertRaisesRegex(Exception, "CORE_ENVELOPE_DIGITS_MISMATCH"):
            CoreDomainEnvelope.from_dict(raw)


if __name__ == "__main__":
    unittest.main()
