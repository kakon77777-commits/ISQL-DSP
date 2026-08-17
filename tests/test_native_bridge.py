import hashlib
import re
import unittest

from isql_dsr.bridge import (
    NativeCoreDomainEnvelope,
    decode_decimal_bytes,
    encode_decimal_bytes,
    to_native_core_bundle,
    to_native_core_sem_envelope,
    to_native_core_state_envelope,
)
from isql_dsr.canonical import state_hash
from isql_dsr.model import PointValue, SemanticState, SpectrumAxis, TypedRelation
from isql_dsr.native import encode_state

CORE_RE = re.compile(r"^ISQL(?P<version>[1-9][0-9]*):(?P<domain>[A-Z]+):(?P<resolution>R[0-4]):(?P<control>[A-Z]+)(?P<payload>[0-9]+)$")


class NativeBridgeTests(unittest.TestCase):
    def _state(self):
        return SemanticState(
            identity="native:bridge",
            revision=3,
            context={"machine": True},
            axes=(SpectrumAxis("risk", "ordinal", PointValue(4), 0.1, 2),),
            relations=(TypedRelation("risk", "affects", "deploy"),),
        )

    def test_decimal_bytes_round_trip(self):
        raw = bytes(range(0, 256, 17))
        digits = encode_decimal_bytes(raw)
        self.assertTrue(digits.isascii() and digits.isdigit())
        self.assertEqual(raw, decode_decimal_bytes(digits))

    def test_state_native_wire_is_r3_dsrn_and_lossless(self):
        state = self._state()
        envelope = to_native_core_state_envelope(state)
        self.assertEqual(envelope.domain, "STATE")
        self.assertEqual(envelope.resolution, "R3")
        self.assertEqual(envelope.control, "DSRN")
        self.assertEqual(envelope.state_hash, state_hash(state))
        self.assertEqual(decode_decimal_bytes(envelope.payload_digits), encode_state(state))
        self.assertEqual(envelope.to_state(), state)
        match = CORE_RE.fullmatch(envelope.wire)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("domain"), "STATE")
        self.assertEqual(match.group("resolution"), "R3")
        self.assertEqual(match.group("control"), "DSRN")

    def test_sem_native_wire_excludes_context_and_history(self):
        state = self._state()
        envelope = to_native_core_sem_envelope(state)
        semantic = envelope.to_state()
        self.assertEqual(semantic.identity, state.identity)
        self.assertEqual(semantic.revision, state.revision)
        self.assertEqual(semantic.axes, state.axes)
        self.assertEqual(semantic.relations, state.relations)
        self.assertEqual(semantic.context, {})
        self.assertEqual(semantic.history, ())
        self.assertEqual(envelope.content_hash, hashlib.sha256(encode_state(semantic)).hexdigest())

    def test_bundle_and_tamper_rejection(self):
        state = self._state()
        bundle = to_native_core_bundle(state)
        self.assertEqual(bundle.sem.domain, "SEM")
        self.assertEqual(bundle.state.domain, "STATE")
        raw = bundle.state.to_dict()
        raw["payload_digits"] = ("255" if raw["payload_digits"][:3] != "255" else "254") + raw["payload_digits"][3:]
        with self.assertRaises(Exception):
            NativeCoreDomainEnvelope.from_dict(raw)


if __name__ == "__main__":
    unittest.main()
