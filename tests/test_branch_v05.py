import unittest

from isql_dsr.branch import NativeBranch, merge_native_branches, encode_branch, decode_branch
from isql_dsr.canonical import state_hash
from isql_dsr.events import TransitionEvent
from isql_dsr.machine import compile_registered_state
from isql_dsr.model import PointValue, SemanticState, SpectrumAxis, TypedRelation
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace, extend_registry_for_events, extend_registry_for_state
from isql_dsr.stream import build_event_stream


class NativeBranchV05Tests(unittest.TestCase):
    def _registry_for(self, state, event_groups):
        reg = extend_registry_for_state(NativeSymbolRegistry(), state)
        for events in event_groups:
            reg = extend_registry_for_events(reg, events)
        reg, left_ref = reg.intern_text(SymbolNamespace.BRANCH_ID, "left")
        reg, right_ref = reg.intern_text(SymbolNamespace.BRANCH_ID, "right")
        return reg, left_ref, right_ref

    def test_branch_artifact_round_trip(self):
        base = SemanticState(identity="obj")
        event = TransitionEvent(event_id="e1", operation="upsert_axis", payload={"axis": SpectrumAxis("risk", "ordinal", PointValue(2)).to_dict()}, base_revision=0, previous_hash=state_hash(base))
        reg, left_ref, _ = self._registry_for(base, ((event,),))
        stream = build_event_stream(base, (event,), reg)
        branch = NativeBranch(left_ref, compile_registered_state(base, reg).revision, stream.genesis_hash, stream)
        raw = encode_branch(branch)
        self.assertEqual(decode_branch(raw, reg), branch)
        self.assertEqual(encode_branch(decode_branch(raw, reg)), raw)

    def test_disjoint_branches_merge_deterministically(self):
        base = SemanticState(identity="obj")
        left_event = TransitionEvent(event_id="l1", operation="upsert_axis", payload={"axis": SpectrumAxis("risk", "ordinal", PointValue(2)).to_dict()}, base_revision=0, previous_hash=state_hash(base))
        right_event = TransitionEvent(event_id="r1", operation="upsert_relation", payload={"relation": TypedRelation("a", "supports", "b").to_dict()}, base_revision=0, previous_hash=state_hash(base))
        reg, left_ref, right_ref = self._registry_for(base, ((left_event,), (right_event,)))
        genesis = compile_registered_state(base, reg)
        left = NativeBranch(left_ref, 0, genesis.registry_hash and genesis_hash(genesis), build_event_stream(base, (left_event,), reg))
        right = NativeBranch(right_ref, 0, genesis_hash(genesis), build_event_stream(base, (right_event,), reg))
        result1 = merge_native_branches(genesis, (left, right), reg)
        result2 = merge_native_branches(genesis, (right, left), reg)
        self.assertEqual(result1, result2)
        self.assertEqual(result1.conflicts, ())
        self.assertEqual(len(result1.state.axes), 1)
        self.assertEqual(len(result1.state.relations), 1)

    def test_conflicting_axis_updates_produce_machine_conflict(self):
        base = SemanticState(identity="obj")
        left_event = TransitionEvent(event_id="l1", operation="upsert_axis", payload={"axis": SpectrumAxis("risk", "ordinal", PointValue(2)).to_dict()}, base_revision=0, previous_hash=state_hash(base))
        right_event = TransitionEvent(event_id="r1", operation="upsert_axis", payload={"axis": SpectrumAxis("risk", "ordinal", PointValue(9)).to_dict()}, base_revision=0, previous_hash=state_hash(base))
        reg, left_ref, right_ref = self._registry_for(base, ((left_event,), (right_event,)))
        genesis = compile_registered_state(base, reg)
        left = NativeBranch(left_ref, 0, genesis_hash(genesis), build_event_stream(base, (left_event,), reg))
        right = NativeBranch(right_ref, 0, genesis_hash(genesis), build_event_stream(base, (right_event,), reg))
        result = merge_native_branches(genesis, (left, right), reg)
        self.assertEqual(len(result.conflicts), 1)
        self.assertEqual(result.conflicts[0].kind, 1)  # AXIS
        self.assertEqual(result.state.axes, ())

    def test_positive_vs_negative_relation_is_conflict(self):
        relation = TypedRelation("a", "supports", "b")
        base = SemanticState(identity="obj")
        pos = TransitionEvent(event_id="l1", operation="upsert_relation", payload={"relation": relation.to_dict()}, base_revision=0, previous_hash=state_hash(base))
        neg = TransitionEvent(event_id="r1", operation="deny_relation", payload={"relation": relation.to_dict()}, base_revision=0, previous_hash=state_hash(base))
        reg, left_ref, right_ref = self._registry_for(base, ((pos,), (neg,)))
        genesis = compile_registered_state(base, reg)
        left = NativeBranch(left_ref, 0, genesis_hash(genesis), build_event_stream(base, (pos,), reg))
        right = NativeBranch(right_ref, 0, genesis_hash(genesis), build_event_stream(base, (neg,), reg))
        result = merge_native_branches(genesis, (left, right), reg)
        self.assertEqual(len(result.conflicts), 1)
        self.assertEqual(result.conflicts[0].kind, 2)  # RELATION_POLARITY
        self.assertEqual(result.state.relations, ())
        self.assertEqual(result.state.negative_relations, ())


def genesis_hash(state):
    from isql_dsr.machine import registered_state_hash
    return registered_state_hash(state)


if __name__ == "__main__":
    unittest.main()
