import unittest

from isql_dsr.events import TransitionEvent
from isql_dsr.model import PointValue, SemanticState, SpectrumAxis, TypedRelation
from isql_dsr.registry import (
    NativeSymbolRegistry,
    SymbolNamespace,
    decode_registry,
    encode_registry,
    extend_registry_for_events,
    extend_registry_for_state,
    registry_hash,
)


class NativeRegistryV04Tests(unittest.TestCase):
    def test_intern_is_append_only_and_namespace_sensitive(self):
        r0 = NativeSymbolRegistry()
        r1, a = r0.intern(SymbolNamespace.ATOM, b"risk")
        r2, b = r1.intern(SymbolNamespace.PREDICATE, b"risk")
        r3, a2 = r2.intern(SymbolNamespace.ATOM, b"risk")
        self.assertEqual(a, 1)
        self.assertEqual(b, 2)
        self.assertEqual(a2, 1)
        self.assertEqual(r1.resolve(a, SymbolNamespace.ATOM), b"risk")
        self.assertEqual(r3.revision, 2)
        self.assertEqual(r1.prefix_hash(1), r3.prefix_hash(1))

    def test_registry_binary_round_trip_is_exact(self):
        registry = NativeSymbolRegistry()
        for namespace, value in (
            (SymbolNamespace.IDENTITY, "obj:α"),
            (SymbolNamespace.AXIS_KEY, "risk"),
            (SymbolNamespace.AXIS_DOMAIN, "ordinal"),
        ):
            registry, _ = registry.intern_text(namespace, value)
        raw = encode_registry(registry)
        decoded = decode_registry(raw)
        self.assertEqual(registry, decoded)
        self.assertEqual(raw, encode_registry(decoded))
        self.assertEqual(registry_hash(registry), registry_hash(decoded))

    def test_state_extension_is_deterministic_and_covers_identifiers(self):
        state = SemanticState(
            identity="obj:x",
            context={"mode": "machine"},
            axes=(SpectrumAxis("risk", "ordinal", PointValue("high"), 0.1, 1),),
            relations=(TypedRelation("risk", "affects", "deploy"),),
        )
        left = extend_registry_for_state(NativeSymbolRegistry(), state)
        right = extend_registry_for_state(NativeSymbolRegistry(), SemanticState.from_dict({
            **state.to_dict(),
            "context": {"mode": "machine"},
            "relations": list(reversed(state.to_dict()["relations"])),
        }))
        self.assertEqual(left, right)
        self.assertIsNotNone(left.lookup_text(SymbolNamespace.IDENTITY, "obj:x"))
        self.assertIsNotNone(left.lookup_text(SymbolNamespace.CONTEXT_KEY, "mode"))
        self.assertIsNotNone(left.lookup_text(SymbolNamespace.AXIS_KEY, "risk"))
        self.assertIsNotNone(left.lookup_text(SymbolNamespace.AXIS_DOMAIN, "ordinal"))
        self.assertIsNotNone(left.lookup_text(SymbolNamespace.ATOM, "deploy"))
        self.assertIsNotNone(left.lookup_text(SymbolNamespace.PREDICATE, "affects"))

    def test_event_extension_adds_event_and_payload_symbols(self):
        base = SemanticState(identity="obj:e")
        event = TransitionEvent.for_state(
            base,
            event_id="evt-1",
            operation="upsert_axis",
            payload={"axis": SpectrumAxis("risk", "ordinal", PointValue(3), 0.2, 1).to_dict()},
        )
        registry = extend_registry_for_state(NativeSymbolRegistry(), base)
        extended = extend_registry_for_events(registry, (event,))
        self.assertIsNotNone(extended.lookup_text(SymbolNamespace.EVENT_ID, "evt-1"))
        self.assertIsNotNone(extended.lookup_text(SymbolNamespace.AXIS_KEY, "risk"))
        self.assertIsNotNone(extended.lookup_text(SymbolNamespace.AXIS_DOMAIN, "ordinal"))
        self.assertEqual(registry.prefix_hash(registry.revision), extended.prefix_hash(registry.revision))


if __name__ == "__main__":
    unittest.main()
