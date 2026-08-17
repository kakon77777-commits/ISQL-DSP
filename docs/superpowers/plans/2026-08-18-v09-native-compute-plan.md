# ISQL-DSR v0.9 Native Compute Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add typed register algebra, comparisons with predicated DAG branching, register guards, and static program linking while preserving v7/v8 program compatibility and atomic rollback.

**Architecture:** Extend `VMInstruction` with defaulted control metadata so old constructors remain valid. Encode the new metadata only in VM format v9. Add pure register opcodes to the existing VM executor and scheduler. Put static composition in a focused `linker.py` module.

**Tech Stack:** Python 3.11+, stdlib dataclasses, unittest, existing ISQL native codec.

## Global Constraints

- `.isqlp` remains the only persistent program artifact.
- Canonical program bytes contain numeric protocol fields, not human schema keys.
- v7/v8 `.isqlp` remain decodable.
- Core transport remains `EXEC/R4/DSRV`.
- Transaction failures publish the original states and no return registers.
- Tests are written and observed failing before production changes.

---

### Task 1: v9 instruction control codec

**Files:**
- Modify: `src/isql_dsr/vm.py`
- Test: `tests/test_vm_control_codec_v09.py`

**Interfaces:**
- Produces: `NativeRegisterGuard`, `register_guard_initialized`, `register_guard_value_eq`, v9 `VMInstruction.register_guards`, `predicate_register_ref`, `predicate_expected`.

- [ ] Write tests constructing v9 instructions with register guards/predicates and asserting encode/decode exactness plus v8 decode compatibility.
- [ ] Run the focused test and verify RED because the new types/fields do not exist.
- [ ] Implement numeric register-guard codec and v9 instruction trailer while retaining v7/v8 decode branches.
- [ ] Run focused and full tests; require green.

### Task 2: Typed register algebra

**Files:**
- Modify: `src/isql_dsr/vm.py`
- Test: `tests/test_vm_algebra_v09.py`

**Interfaces:**
- Produces opcodes `VM_OP_CONST`, `VM_OP_MOVE`, `VM_OP_ADD`, `VM_OP_SUB`, `VM_OP_MUL`, `VM_OP_DIV`, `VM_OP_EQ`, `VM_OP_LT`, `VM_OP_LE` and payload helpers.

- [ ] Write tests for int-preserving ADD, mixed numeric promotion, division-by-zero rollback, semantic EQ, and numeric comparison.
- [ ] Verify RED because the opcodes/helpers are missing.
- [ ] Implement payload codecs and pure register execution with strict semantic types.
- [ ] Update scheduler register read/write analysis.
- [ ] Run focused and full suites.

### Task 3: Register guards and predicated branching

**Files:**
- Modify: `src/isql_dsr/vm.py`
- Test: `tests/test_vm_branching_v09.py`

**Interfaces:**
- Consumes: comparison opcodes from Task 2.
- Produces: fail-closed register guard evaluation and skip-on-false predicate semantics.

- [ ] Write a compare -> true-path/false-path program and assert only the matching path mutates a register/state.
- [ ] Add tests proving guard false aborts, predicate missing/wrong-type aborts, and skipped instructions count as structurally completed dependencies.
- [ ] Verify RED.
- [ ] Implement evaluation before primitive execution; return an explicit skipped marker from batch workers.
- [ ] Include guard/predicate reads in hazard analysis.
- [ ] Run focused and full suites.

### Task 4: Static program linker

**Files:**
- Create: `src/isql_dsr/linker.py`
- Modify: `src/isql_dsr/__init__.py`
- Test: `tests/test_vm_linker_v09.py`

**Interfaces:**
- Produces: `link_vm_programs(registry, program_ref, modules, sequential=True, argument_registers=None, return_registers=None) -> NativeVMProgram`.

- [ ] Write tests linking two register modules, checking deterministic bytes, sequential causal edges, and execution equivalence to manual combined program.
- [ ] Add rejection tests for duplicate instruction refs, binding conflict, and registry mismatch.
- [ ] Verify RED because linker module is missing.
- [ ] Implement canonical merge; strip module RETURN instructions and connect module exits to next module entries in sequential mode.
- [ ] Export linker API and run full suite.

### Task 5: CLI, version, docs, release

**Files:**
- Modify: `src/isql_dsr/__init__.py`
- Modify: `src/isql_dsr/cli.py`
- Modify: `pyproject.toml`
- Create: `docs/NATIVE_VM_v0.9.md`
- Modify: `README.md`, `RELEASE_NOTES.md`, `AI_HANDOFF.md`
- Test: `tests/test_vm_cli_v09.py`

**Interfaces:**
- Produces v0.9 package metadata and examples.

- [ ] Add a CLI execution test using argument registers, arithmetic/comparison, predicated branch, and `--parallel` compatibility.
- [ ] Verify RED against v0.8 version/schema behavior.
- [ ] Update version strings and public exports, document machine semantics, and generate examples.
- [ ] Run source suite.
- [ ] Build wheel offline, install into a fresh venv without source `PYTHONPATH`, rerun full suite.
- [ ] Verify `EXEC/R4/DSRV` with real ISQL Core v0.4 `parse_code()`.
- [ ] Generate checksums and ZIP; extract ZIP and rerun checksum/source/wheel/Core gates.
