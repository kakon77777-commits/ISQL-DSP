import math
import unittest

from isql_dsr.native import decode_uvarint, decode_value, encode_uvarint, encode_value


class NativePrimitiveCodecTests(unittest.TestCase):
    def test_uvarint_round_trip_is_canonical(self):
        cases = [0, 1, 127, 128, 255, 300, 16384, 2**63 - 1]
        for value in cases:
            encoded = encode_uvarint(value)
            decoded, offset = decode_uvarint(encoded)
            self.assertEqual(value, decoded)
            self.assertEqual(len(encoded), offset)
            self.assertEqual(encoded, encode_uvarint(decoded))

    def test_typed_values_round_trip_and_maps_ignore_insertion_order(self):
        left = {
            "z": [None, False, True, -7, 9, 1.25, "光譜"],
            "a": {"nested": "value", "n": 3},
        }
        right = {
            "a": {"n": 3, "nested": "value"},
            "z": [None, False, True, -7, 9, 1.25, "光譜"],
        }
        encoded_left = encode_value(left)
        encoded_right = encode_value(right)
        self.assertEqual(encoded_left, encoded_right)
        decoded, offset = decode_value(encoded_left)
        self.assertEqual(left, decoded)
        self.assertEqual(len(encoded_left), offset)

    def test_nonfinite_float_is_rejected(self):
        for value in (math.inf, -math.inf, math.nan):
            with self.assertRaises(ValueError):
                encode_value(value)


if __name__ == "__main__":
    unittest.main()
