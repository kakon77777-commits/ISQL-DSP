# ISQL-DSR v0.8 Register VM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add machine-native arguments/returns, state-scoped capabilities, cross-state register dataflow, and deterministic parallel scheduling to the existing `.isqlp` VM.

**Architecture:** Extend `NativeVMProgram` to VM format v8 while preserving the existing artifact family and Core `EXEC/R4/DSRV` bridge. Use semantic-value registers plus explicit state-slot capability rows; compile the instruction DAG into deterministic hazard-free batches and execute independent batch members concurrently with ordered commit.

**Tech Stack:** Python 3.11+, stdlib `dataclasses`, `concurrent.futures`, existing ISQL native codec/registry/runtime, `unittest`.

## Global Constraints

- Canonical source of truth remains machine-native bytes, never JSON.
- No new persistent artifact extension is introduced.
- Existing v0.7 behaviors remain valid when new v0.8 fields are empty/defaulted.
- Core transport remains `EXEC/R4/DSRV`.
- All production changes follow RED → GREEN TDD.
- This delivery directory is not a Git repository, so commit steps are recorded but not executable here.

---

### Task 1: Register namespace and v0.8 program codec

**Files:**
- Modify: `src/isql_dsr/registry.py`
- Modify: `src/isql_dsr/vm.py`
- Test: `tests/test_vm_register_codec_v08.py`

**Interfaces:**
- Produces: `SymbolNamespace.REGISTER_ID`, `VMScopedCapability`, v0.8 `NativeVMProgram.argument_registers`, `return_registers`, `scoped_capabilities`, and v7-compatible decoding.

- [ ] Write failing tests that register refs are namespace-sensitive, v0.8 program binary round-trips, duplicate argument/return regs fail, scoped capability rows are canonical, and human schema labels do not appear in bytes.
- [ ] Run `PYTHONPATH=src python -m unittest tests.test_vm_register_codec_v08 -v` and confirm RED because v0.8 types/fields do not exist.
- [ ] Implement the minimal registry namespace and VM v8 codec, including legacy v7 decode.
- [ ] Re-run the focused test and then `PYTHONPATH=src python -m unittest discover -s tests -q`.

### Task 2: Root arguments and return registers

**Files:**
- Modify: `src/isql_dsr/vm.py`
- Test: `tests/test_vm_register_runtime_v08.py`

**Interfaces:**
- Produces: `execute_vm_transaction(..., arguments=...)` and `VMTransactionResult.returns`.

- [ ] Write failing tests that root arguments populate declared registers, missing/extra arguments fail atomically, and declared return registers are exposed only on success.
- [ ] Run focused tests and verify RED.
- [ ] Add semantic register validation and transaction-local register file.
- [ ] Run focused and full suites.

### Task 3: Cross-state LOAD/STORE and scoped capabilities

**Files:**
- Modify: `src/isql_dsr/vm.py`
- Test: `tests/test_vm_cross_state_v08.py`

**Interfaces:**
- Produces: `VM_OP_LOAD_AXIS`, `VM_OP_STORE_AXIS`, `CAP_AXIS_READ`, payload helpers, and `granted_scoped_capabilities`.

- [ ] Write failing tests for load A→register→store B, read-only scoped access, denied destination write, and rollback on an uninitialized source register.
- [ ] Verify RED.
- [ ] Implement numeric payload codecs, state-scoped authorization, and register-aware execution.
- [ ] Run focused and full suites.

### Task 4: Multi-slot CALL argument/return mapping

**Files:**
- Modify: `src/isql_dsr/vm.py`
- Test: `tests/test_vm_call_registers_v08.py`

**Interfaces:**
- Produces: v0.8 CALL payload helpers and synchronous multi-binding register-aware CALL/RETURN.

- [ ] Write failing tests for a two-slot dynamic callee, positional argument passing, return copying, mapping mismatch failure, and full rollback after late callee failure.
- [ ] Verify RED.
- [ ] Implement CALL v0.8 payload encode/decode and child frame register/state alias mapping.
- [ ] Run focused and full suites.

### Task 5: Deterministic parallel scheduling

**Files:**
- Modify: `src/isql_dsr/vm.py`
- Test: `tests/test_vm_parallel_v08.py`

**Interfaces:**
- Produces: `vm_execution_batches(program)` and `execute_vm_transaction(..., parallel=True)`.

- [ ] Write failing tests that independent state writes share a batch, same-slot writes are separated, register hazards are separated, CALL is singleton, parallel and serial execution yield identical state hashes/returns, and a worker failure rolls back all states.
- [ ] Verify RED.
- [ ] Implement hazard analysis and thread-pool execution over immutable batch-start snapshots with ordered commit.
- [ ] Run focused and full suites.

### Task 6: CLI, bridge, docs, and release verification

**Files:**
- Modify: `src/isql_dsr/cli.py`
- Modify: `src/isql_dsr/__init__.py`
- Modify: `pyproject.toml`
- Create: `docs/NATIVE_VM_v0.8.md`
- Modify: `README.md`
- Modify: `AI_HANDOFF.md`
- Modify: `RELEASE_NOTES.md`
- Test: `tests/test_vm_cli_v08.py`

**Interfaces:**
- Produces: v0.8 package metadata and CLI execution with numeric register arguments while retaining `EXEC/R4/DSRV` Core bridge.

- [ ] Write CLI tests for argument input, return output, parallel execution flag, and DSRV bridge compatibility.
- [ ] Verify RED, implement minimal CLI/API exports, and run full source suite.
- [ ] Build wheel offline with `python -m build --wheel --no-isolation` or equivalent available command.
- [ ] Install wheel into a fresh venv with source tree removed from `PYTHONPATH`; run the complete test suite.
- [ ] Verify final DSRV wire with the actual ISQL Core v0.4 `parse_code()` and exact `to_wire()` round-trip.
- [ ] Generate examples, validation metadata, SHA-256 checksums, ZIP, unzip it, re-check all checksums, rerun source tests, and reinstall the ZIP-contained wheel into a second fresh venv.
