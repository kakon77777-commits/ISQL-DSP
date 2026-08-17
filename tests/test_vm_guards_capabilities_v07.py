import unittest

from isql_dsr.machine import NativeAxis, NativeRelation, NativeSemanticState, registered_state_hash
from isql_dsr.model import PointValue
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace
from isql_dsr.vm import (
    CAP_AXIS, CAP_RELATION, GUARD_AXIS_ABSENT, GUARD_AXIS_PRESENT,
    NativeGuard, evaluate_guard, guard_axis_value_eq, guard_relation_status,
    guard_state_hash_eq,
)
from isql_dsr.native import encode_uvarint


def fixture():
    r = NativeSymbolRegistry(); refs = {}
    for ns, text, key in [
        (SymbolNamespace.IDENTITY, 'state:a', 'id'),
        (SymbolNamespace.AXIS_KEY, 'risk', 'axis'),
        (SymbolNamespace.AXIS_DOMAIN, 'ordinal', 'domain'),
        (SymbolNamespace.ATOM, 'A', 'a'),
        (SymbolNamespace.PREDICATE, 'supports', 'pred'),
        (SymbolNamespace.ATOM, 'B', 'b'),
    ]:
        r, refs[key] = r.intern_text(ns, text)
    s = NativeSemanticState(
        r.revision, r.prefix_hash(), refs['id'], 2,
        axes=(NativeAxis(refs['axis'], refs['domain'], PointValue(5), 0.1, 1),),
        relations=(NativeRelation(refs['a'], refs['pred'], refs['b']),),
    )
    return r, refs, s


class VMGuardsCapabilitiesV07Tests(unittest.TestCase):
    def test_axis_presence_and_absence_guards(self):
        r, refs, s = fixture()
        self.assertTrue(evaluate_guard(s, NativeGuard(GUARD_AXIS_PRESENT, encode_uvarint(refs['axis'])), r))
        self.assertFalse(evaluate_guard(s, NativeGuard(GUARD_AXIS_ABSENT, encode_uvarint(refs['axis'])), r))

    def test_axis_value_and_state_hash_guards(self):
        r, refs, s = fixture()
        self.assertTrue(evaluate_guard(s, guard_axis_value_eq(refs['axis'], PointValue(5)), r))
        self.assertFalse(evaluate_guard(s, guard_axis_value_eq(refs['axis'], PointValue(7)), r))
        self.assertTrue(evaluate_guard(s, guard_state_hash_eq(registered_state_hash(s)), r))

    def test_relation_polarity_guard(self):
        r, refs, s = fixture()
        self.assertTrue(evaluate_guard(s, guard_relation_status(refs['a'], refs['pred'], refs['b'], 1), r))
        self.assertFalse(evaluate_guard(s, guard_relation_status(refs['a'], refs['pred'], refs['b'], -1), r))

    def test_capability_bits_remain_distinct(self):
        self.assertNotEqual(CAP_AXIS, CAP_RELATION)
        self.assertEqual(CAP_AXIS & CAP_RELATION, 0)


if __name__ == '__main__': unittest.main()
