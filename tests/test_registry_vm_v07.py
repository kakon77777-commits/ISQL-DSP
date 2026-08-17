import unittest

from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace


class RegistryVMV07Tests(unittest.TestCase):
    def test_state_slot_and_capability_namespaces_are_distinct(self):
        registry = NativeSymbolRegistry()
        registry, slot_ref = registry.intern_text(SymbolNamespace.STATE_SLOT_ID, "slot:primary")
        registry, cap_ref = registry.intern_text(SymbolNamespace.CAPABILITY_ID, "cap:axis")
        self.assertNotEqual(slot_ref, cap_ref)
        self.assertEqual(registry.resolve_text(slot_ref, SymbolNamespace.STATE_SLOT_ID), "slot:primary")
        self.assertEqual(registry.resolve_text(cap_ref, SymbolNamespace.CAPABILITY_ID), "cap:axis")
        with self.assertRaises(Exception):
            registry.resolve(slot_ref, SymbolNamespace.CAPABILITY_ID)


if __name__ == "__main__":
    unittest.main()
