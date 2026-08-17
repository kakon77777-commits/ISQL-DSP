import hashlib
import re
import unittest

from isql_dsr.bridge import (
    RegisteredCoreEnvelope,
    decode_decimal_bytes,
    to_registered_core_exec_envelope,
    to_registered_core_sem_envelope,
    to_registered_core_state_envelope,
)
from isql_dsr.events import TransitionEvent
from isql_dsr.machine import compile_registered_state, decode_registered_state, registered_state_hash
from isql_dsr.model import PointValue, SemanticState, SpectrumAxis
from isql_dsr.registry import NativeSymbolRegistry, extend_registry_for_events, extend_registry_for_state
from isql_dsr.stream import build_event_stream, decode_event_stream, encode_event_stream

CORE_RE = re.compile(r"^ISQL(?P<version>[1-9][0-9]*):(?P<domain>[A-Z]+):(?P<resolution>R[0-4]):(?P<control>[A-Z]+)(?P<payload>[0-9]+)$")


class RegisteredCoreBridgeV04Tests(unittest.TestCase):
    def _fixtures(self):
        genesis = SemanticState(identity="obj:r4", context={"mode": "machine"})
        event = TransitionEvent.for_state(
            genesis, event_id="e1", operation="upsert_axis",
            payload={"axis": SpectrumAxis("risk", "ordinal", PointValue(4), 0.1, 2).to_dict()},
        )
        registry = extend_registry_for_state(NativeSymbolRegistry(), genesis)
        registry = extend_registry_for_events(registry, (event,))
        machine = compile_registered_state(genesis, registry)
        stream = build_event_stream(genesis, (event,), registry)
        return genesis, registry, machine, stream

    def test_state_and_sem_are_r4_dsrr_and_lossless(self):
        _, registry, machine, _ = self._fixtures()
        state_env = to_registered_core_state_envelope(machine)
        sem_env = to_registered_core_sem_envelope(machine)
        self.assertEqual((state_env.domain, state_env.resolution, state_env.control), ("STATE", "R4", "DSRR"))
        self.assertEqual((sem_env.domain, sem_env.resolution, sem_env.control), ("SEM", "R4", "DSRR"))
        self.assertEqual(decode_registered_state(decode_decimal_bytes(state_env.payload_digits), registry), machine)
        semantic = decode_registered_state(decode_decimal_bytes(sem_env.payload_digits), registry)
        self.assertEqual(semantic.context, ())
        self.assertEqual(semantic.axes, machine.axes)
        for env in (state_env, sem_env):
            match = CORE_RE.fullmatch(env.wire)
            self.assertIsNotNone(match)
            self.assertEqual(match.group("resolution"), "R4")

    def test_exec_is_r4_dsre_and_carries_native_stream(self):
        _, registry, machine, stream = self._fixtures()
        env = to_registered_core_exec_envelope(stream, machine)
        self.assertEqual((env.domain, env.resolution, env.control), ("EXEC", "R4", "DSRE"))
        self.assertEqual(decode_event_stream(decode_decimal_bytes(env.payload_digits), registry), stream)
        self.assertEqual(env.state_hash, stream.records[-1].next_hash)
        self.assertEqual(env.content_hash, hashlib.sha256(encode_event_stream(stream)).hexdigest())
        self.assertIsNotNone(CORE_RE.fullmatch(env.wire))

    def test_envelope_tamper_is_rejected(self):
        _, _, machine, _ = self._fixtures()
        env = to_registered_core_state_envelope(machine)
        raw = env.to_dict()
        raw["payload_digits"] = ("255" if raw["payload_digits"][:3] != "255" else "254") + raw["payload_digits"][3:]
        with self.assertRaises(Exception):
            RegisteredCoreEnvelope.from_dict(raw)


if __name__ == "__main__":
    unittest.main()
