import unittest

from isql_dsr.branch import NativeBranch, decode_branch, encode_branch, merge_native_branches
from isql_dsr.canonical import state_hash
from isql_dsr.errors import DSRExecutionError
from isql_dsr.events import TransitionEvent
from isql_dsr.machine import compile_registered_state
from isql_dsr.model import PointValue, SemanticState, SpectrumAxis
from isql_dsr.registry import NativeSymbolRegistry, SymbolNamespace, extend_registry_for_events, extend_registry_for_state
from isql_dsr.stream import build_event_stream


def _registered_hash(state):
    from isql_dsr.machine import registered_state_hash
    return registered_state_hash(state)


class BranchCausalityV06Tests(unittest.TestCase):
    def _setup(self, values=(1, 2, 3)):
        base = SemanticState(identity="obj:branch-causal")
        events = []
        for index, value in enumerate(values, 1):
            events.append(TransitionEvent(
                event_id=f"e{index}",
                operation="upsert_axis",
                payload={"axis": SpectrumAxis("risk", "ordinal", PointValue(value)).to_dict()},
                base_revision=0,
                previous_hash=state_hash(base),
            ))
        reg = extend_registry_for_state(NativeSymbolRegistry(), base)
        for event in events:
            reg = extend_registry_for_events(reg, (event,))
        refs = []
        for name in ("a", "b", "c"):
            reg, ref = reg.intern_text(SymbolNamespace.BRANCH_ID, name)
            refs.append(ref)
        genesis = compile_registered_state(base, reg)
        streams = [build_event_stream(base, (event,), reg) for event in events]
        return base, reg, genesis, tuple(refs), tuple(streams)

    def test_branch_codec_preserves_causal_dependencies(self):
        _, reg, genesis, refs, streams = self._setup()
        a, b, _ = refs
        branch = NativeBranch(b, 0, _registered_hash(genesis), streams[1], (a,))
        raw = encode_branch(branch)
        self.assertEqual(decode_branch(raw, reg), branch)
        self.assertEqual(encode_branch(decode_branch(raw, reg)), raw)

    def test_merge_rejects_missing_dependencies_and_cycles(self):
        _, reg, genesis, refs, streams = self._setup()
        a, b, c = refs
        only_b = NativeBranch(b, 0, _registered_hash(genesis), streams[1], (a,))
        with self.assertRaisesRegex(DSRExecutionError, "BRANCH_DEPENDENCY_MISSING"):
            merge_native_branches(genesis, (only_b,), reg)

        ba = NativeBranch(a, 0, _registered_hash(genesis), streams[0], (b,))
        bb = NativeBranch(b, 0, _registered_hash(genesis), streams[1], (a,))
        with self.assertRaisesRegex(DSRExecutionError, "BRANCH_DEPENDENCY_CYCLE"):
            merge_native_branches(genesis, (ba, bb), reg)

    def test_causally_later_branch_overrides_ancestor_without_conflict(self):
        _, reg, genesis, refs, streams = self._setup((1, 2, 3))
        a, b, _ = refs
        ba = NativeBranch(a, 0, _registered_hash(genesis), streams[0])
        bb = NativeBranch(b, 0, _registered_hash(genesis), streams[1], (a,))
        result = merge_native_branches(genesis, (bb, ba), reg)
        self.assertEqual(result.conflicts, ())
        self.assertEqual(len(result.state.axes), 1)
        self.assertEqual(result.state.axes[0].value.to_dict(), PointValue(2).to_dict())

    def test_incomparable_maximal_branches_still_conflict(self):
        _, reg, genesis, refs, streams = self._setup((1, 2, 3))
        a, _, c = refs
        ba = NativeBranch(a, 0, _registered_hash(genesis), streams[0])
        bc = NativeBranch(c, 0, _registered_hash(genesis), streams[2])
        result = merge_native_branches(genesis, (ba, bc), reg)
        self.assertEqual(len(result.conflicts), 1)
        self.assertEqual(result.conflicts[0].kind, 1)
        self.assertEqual(set(result.conflicts[0].branch_refs), {a, c})


if __name__ == "__main__":
    unittest.main()
