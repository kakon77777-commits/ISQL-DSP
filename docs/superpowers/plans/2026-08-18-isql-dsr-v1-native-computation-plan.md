# ISQL-DSR v1.0 Native Computation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add typed composite values, register-local containers, function signatures, bounded iteration, and semantics-preserving optimization to the native DAG VM.

**Architecture:** Extend the existing v0.9 binary contract rather than introducing a new artifact or program-counter VM. New functionality remains numeric, deterministic, transaction-atomic, and backward compatible with legacy program versions.

**Tech Stack:** Python 3.11+, standard library only, `unittest`, existing ISQL-DSR native codec/VM.

## Global Constraints

- `.isqlp` remains canonical program format.
- Core transport remains `EXEC/R4/DSRV`.
- v0.9 programs remain decodable.
- No unbounded loop or recursion.
- No human schema strings in canonical machine artifacts.
- TDD: every production behavior starts with a failing test.

---

### Task 1: Composite semantic values

**Files:**
- Modify: `src/isql_dsr/model.py`
- Modify: `src/isql_dsr/native.py`
- Modify: `src/isql_dsr/registry.py`
- Test: `tests/test_vm_composite_values_v10.py`

**Interfaces:**
- Produces: `VectorValue`, `RecordValue`, `SymbolNamespace.FIELD_ID`, recursive native semantic-value encode/decode support.

- [ ] Write tests that construct nested vectors/records, round-trip through native codec, reject duplicate/nonpositive record field refs, and keep v0.9 scalar values unchanged.
- [ ] Run the new test file and verify RED because composite classes/tags do not exist.
- [ ] Implement immutable composite values and native tags with canonical field ordering.
- [ ] Run the test file and full suite; require green.

### Task 2: Register-local container instructions

**Files:**
- Modify: `src/isql_dsr/vm.py`
- Test: `tests/test_vm_containers_v10.py`

**Interfaces:**
- Produces: vector pack/get/len and record pack/get/set payload helpers/opcodes and runtime behavior.

- [ ] Write failing tests for vector/record operations, out-of-range/missing-field errors, immutable record update, and scheduler register hazards.
- [ ] Verify RED.
- [ ] Implement payload codecs, validation, register access analysis, and primitive execution.
- [ ] Run new tests and full suite; require green.

### Task 3: Native typed function signatures

**Files:**
- Modify: `src/isql_dsr/vm.py`
- Modify: `src/isql_dsr/linker.py`
- Test: `tests/test_vm_signatures_v10.py`

**Interfaces:**
- Produces: machine type constants, `VMRegisterSpec`, `VMFunctionSignature`, format-v10 signature encoding/decoding and runtime/CALL checks.

- [ ] Write failing tests for v10 signature round-trip, root argument mismatch, callee argument mismatch, return mismatch, and legacy v9 decode as `TYPE_ANY`.
- [ ] Verify RED.
- [ ] Implement signature codec and type checker.
- [ ] Integrate root/CALL/RETURN validation and linker signature preservation.
- [ ] Run new tests and full suite; require green.

### Task 4: Bounded subprogram iteration

**Files:**
- Modify: `src/isql_dsr/vm.py`
- Test: `tests/test_vm_repeat_v10.py`

**Interfaces:**
- Produces: `VM_OP_REPEAT_CALL`, `VM_MAX_REPEAT`, repeat payload codec, synchronous bounded iteration semantics.

- [ ] Write failing tests for three-step iteration, zero/excessive count rejection, deterministic trace, and late-iteration rollback.
- [ ] Verify RED.
- [ ] Implement payload codec and execution with hard iteration cap.
- [ ] Run new tests and full suite; require green.

### Task 5: Static native optimizer

**Files:**
- Create: `src/isql_dsr/optimizer.py`
- Modify: `src/isql_dsr/__init__.py`
- Modify: `src/isql_dsr/cli.py`
- Test: `tests/test_vm_optimizer_v10.py`

**Interfaces:**
- Produces: `optimize_vm_program(program) -> NativeVMProgram`, CLI `vm-optimize`.

- [ ] Write failing tests for constant folding, dead pure-register elimination, dependency cleanup, state/return semantic equivalence, and no folding across impure instructions.
- [ ] Verify RED.
- [ ] Implement liveness analysis and deterministic constant folding.
- [ ] Add CLI optimizer entrypoint.
- [ ] Run new tests and full suite; require green.

### Task 6: v1.0 release and independent verification

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/isql_dsr/__init__.py`
- Modify: `README.md`
- Modify: `RELEASE_NOTES.md`
- Modify: `AI_HANDOFF.md`
- Create: `docs/NATIVE_VM_v1.0.md`
- Create: `examples/v1.0/*`
- Regenerate: `validation/*`, `validation.json`, `CHECKSUMS.sha256`, `dist/*.whl`

**Interfaces:**
- Produces: validated v1.0 package and ZIP.

- [ ] Run full source suite with `PYTHONPATH=src`.
- [ ] Build wheel offline with `pip wheel --no-build-isolation --no-deps`.
- [ ] Install wheel in a new venv and run full suite with source path absent.
- [ ] Generate composite/signature/repeat/optimizer examples.
- [ ] Verify true Core v0.4 `parse_code()` accepts `EXEC/R4/DSRV` and exact round-trips.
- [ ] Generate SHA-256 manifest and ZIP.
- [ ] Extract final ZIP to a fresh directory and independently re-run checksums, source tests, installed-wheel tests, and Core parser test.
