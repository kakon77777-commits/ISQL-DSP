import unittest

from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace


class ProgramRegistryV06Tests(unittest.TestCase):
    def test_program_and_instruction_ids_are_namespace_sensitive_and_append_only(self):
        registry = NativeSymbolRegistry()
        registry, program_ref = registry.intern_text(SymbolNamespace.PROGRAM_ID, "prog:alpha")
        registry, instruction_ref = registry.intern_text(SymbolNamespace.INSTRUCTION_ID, "prog:alpha")
        registry2, program_ref2 = registry.intern_text(SymbolNamespace.PROGRAM_ID, "prog:alpha")

        self.assertEqual(program_ref, 1)
        self.assertEqual(instruction_ref, 2)
        self.assertEqual(program_ref2, 1)
        self.assertEqual(registry2.revision, 2)
        self.assertEqual(registry.resolve_text(program_ref, SymbolNamespace.PROGRAM_ID), "prog:alpha")
        self.assertEqual(registry.resolve_text(instruction_ref, SymbolNamespace.INSTRUCTION_ID), "prog:alpha")


if __name__ == "__main__":
    unittest.main()
