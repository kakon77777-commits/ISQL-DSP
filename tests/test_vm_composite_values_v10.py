import unittest

from isql_dsr.errors import DSRValidationError
from isql_dsr.model import PointValue, VectorValue, RecordValue
from isql_dsr.native import _encode_semantic_value, _decode_semantic_value
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace


class VMCompositeValuesV10Tests(unittest.TestCase):
    def test_vector_and_record_round_trip_recursively(self):
        value = RecordValue((
            (7, PointValue(3)),
            (11, VectorValue((PointValue(True), PointValue(9)))),
        ))
        raw = _encode_semantic_value(value)
        decoded, used = _decode_semantic_value(raw, 0)
        self.assertEqual(used, len(raw))
        self.assertEqual(decoded, value)

    def test_record_fields_are_canonicalized_by_numeric_ref(self):
        value = RecordValue(((9, PointValue('b')), (3, PointValue('a'))))
        self.assertEqual(tuple(ref for ref, _ in value.fields), (3, 9))
        raw1 = _encode_semantic_value(value)
        raw2 = _encode_semantic_value(RecordValue(((3, PointValue('a')), (9, PointValue('b')))))
        self.assertEqual(raw1, raw2)

    def test_record_rejects_duplicate_or_nonpositive_refs(self):
        with self.assertRaisesRegex(DSRValidationError, 'RECORD_FIELD_REF_DUPLICATE'):
            RecordValue(((3, PointValue(1)), (3, PointValue(2))))
        with self.assertRaisesRegex(DSRValidationError, 'RECORD_FIELD_REF_INVALID'):
            RecordValue(((0, PointValue(1)),))

    def test_field_namespace_is_distinct(self):
        reg = NativeSymbolRegistry()
        reg, field_ref = reg.intern_text(SymbolNamespace.FIELD_ID, 'field:x')
        reg, atom_ref = reg.intern_text(SymbolNamespace.ATOM, 'field:x')
        self.assertNotEqual(field_ref, atom_ref)
        self.assertEqual(reg.resolve_text(field_ref, SymbolNamespace.FIELD_ID), 'field:x')

    def test_scalar_encoding_is_unchanged_by_composite_support(self):
        raw = _encode_semantic_value(PointValue(42))
        decoded, used = _decode_semantic_value(raw, 0)
        self.assertEqual(decoded, PointValue(42))
        self.assertEqual(used, len(raw))


if __name__ == '__main__':
    unittest.main()
