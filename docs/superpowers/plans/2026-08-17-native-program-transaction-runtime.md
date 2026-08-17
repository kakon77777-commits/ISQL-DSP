# ISQL-DSR v0.6 Native Program + Transaction Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `EXEC` from replayable event streams to causal, atomic machine programs while preserving numeric canonical artifacts and deterministic rollback semantics.

**Architecture:** Add a new canonical `.isqlp` program artifact containing numeric instruction refs, opcodes, effect masks, causal dependencies, and native payloads. Programs execute directly against `NativeSemanticState` through the existing numeric operation semantics, in deterministic topological order, with functional atomic rollback: no partial state is published on failure. Branches gain numeric dependency metadata so concurrent merge can distinguish causal precedence from true conflict. Legacy `.isqle` remains supported as the lower-level event-stream format.

**Tech Stack:** Python 3.11+, standard library only, `unittest`, existing ISQL-DSR native codecs/registry/Core bridge.

## Global Constraints

- Canonical machine artifacts MUST NOT require human-readable schema labels.
- JSON/Markdown/natural-language representations remain inspection projections only.
- Existing v0.5 `.isqlr/.isqln/.isqle/.isqlb` semantics remain available in the v0.5 release; v0.6 may introduce new format versions in its own package.
- Production feature changes follow RED → GREEN TDD.
- All execution is deterministic under canonical ordering.
- Failed programs MUST return the original base state unchanged.
- Side-information accounting MUST continue to include registry bytes.

---

### Task 1: Program and instruction registry namespaces

**Files:**
- Modify: `src/isql_dsr/registry.py`
- Modify: `src/isql_dsr/__init__.py`
- Test: `tests/test_program_v06.py`

**Interfaces:**
- Produces `SymbolNamespace.PROGRAM_ID`, `SymbolNamespace.INSTRUCTION_ID`.
- Existing registry prefix-hash semantics remain unchanged.

- [ ] Write failing tests that intern program/instruction IDs and prove namespace sensitivity.
- [ ] Run the focused tests and confirm RED.
- [ ] Add numeric namespaces without changing existing namespace values.
- [ ] Run focused and full tests.

### Task 2: Canonical `.isqlp` causal program artifact

**Files:**
- Create: `src/isql_dsr/program.py`
- Modify: `src/isql_dsr/__init__.py`
- Test: `tests/test_program_v06.py`

**Interfaces:**
- `NativeInstruction(instruction_ref:int, opcode:int, effect_mask:int, depends_on:tuple[int,...], payload:bytes)`
- `NativeProgram(registry_revision:int, registry_hash:str, program_ref:int, base_revision:int, base_hash:str, instructions:tuple[NativeInstruction,...])`
- `encode_program(program)->bytes`
- `decode_program(data, registry)->NativeProgram`
- `operator_effect_mask(opcode)->int`

- [ ] Write failing round-trip/canonical-order tests.
- [ ] Write failing tests proving program bytes omit human schema labels.
- [ ] Write failing tests for dependency cycles, unknown dependencies, duplicate instruction refs, and tampered effect masks.
- [ ] Implement minimal canonical codec and validation.
- [ ] Run focused and full tests.

### Task 3: Atomic native program executor and receipt

**Files:**
- Modify: `src/isql_dsr/stream.py`
- Modify: `src/isql_dsr/program.py`
- Test: `tests/test_program_execution_v06.py`

**Interfaces:**
- Refactor operation semantics into `apply_native_operation(state, opcode, payload, registry)` for direct program use.
- Preserve `apply_native_event()` as hash-chain validation + delegation.
- `ProgramExecutionReceipt(status:int, program_ref:int, base_hash:str, final_hash:str, execution_order:tuple[int,...], failed_instruction_ref:int=0, error_code:str="")`
- `ProgramExecutionResult(state:NativeSemanticState, receipt:ProgramExecutionReceipt)`
- `execute_native_program(base, program, registry)->ProgramExecutionResult`

- [ ] Write failing deterministic topological-order test.
- [ ] Write failing atomic rollback test where instruction 1 is valid and instruction 2 fails.
- [ ] Write failing base hash/revision/registry mismatch tests.
- [ ] Refactor existing native operation executor without behavior change.
- [ ] Implement atomic execution over immutable working states; on failure return original base state.
- [ ] Run focused and full tests.

### Task 4: Branch causal dependencies

**Files:**
- Modify: `src/isql_dsr/branch.py`
- Test: `tests/test_branch_causality_v06.py`

**Interfaces:**
- Extend `NativeBranch` with `depends_on: tuple[int,...] = ()`.
- v0.6 branch codec stores dependency refs canonically.
- `merge_native_branches()` rejects missing dependencies/cycles.
- For conflicting changes, a unique causally maximal branch overrides its ancestors; conflicts remain only among incomparable maximal branches.

- [ ] Write failing codec round-trip test with dependencies.
- [ ] Write failing missing-dependency and dependency-cycle tests.
- [ ] Write failing causal override test: branch B depends on A and overrides A without conflict.
- [ ] Write failing incomparable-branches test preserving conflict behavior.
- [ ] Implement dependency DAG validation and maximal-branch merge selection.
- [ ] Run focused and full tests.

### Task 5: Core EXEC program bridge + CLI

**Files:**
- Modify: `src/isql_dsr/bridge.py`
- Modify: `src/isql_dsr/cli.py`
- Modify: `src/isql_dsr/__init__.py`
- Test: `tests/test_program_bridge_cli_v06.py`

**Interfaces:**
- Add a program Core envelope using `EXEC/R4/DSRP` while keeping stream `EXEC/R4/DSRE`.
- `to_registered_core_program_envelope(program, genesis)` encodes raw `.isqlp` bytes as digits-only payload.
- CLI commands:
  - `program-pack --registry ... --genesis ... --stream ... --program-id ... --out ...`
  - `program-run --registry ... --genesis ... --program ... --out ...`
  - `program-bridge --registry ... --genesis ... --program ...`

- [ ] Write failing bridge parser/round-trip tests.
- [ ] Write failing CLI pack/run tests.
- [ ] Implement bridge and CLI.
- [ ] Run focused and full tests.

### Task 6: Release, examples, validation, packaging

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `AI_HANDOFF.md`
- Modify: `RELEASE_NOTES.md`
- Create: `docs/NATIVE_FORMAT_v0.6.md`
- Create: `examples/v0.6/*`
- Regenerate: `validation/*`, `validation.json`, `CHECKSUMS.sha256`, `dist/*.whl`

**Interfaces:**
- Release version `0.6.0`.
- Example includes `.isqlr`, `.isqln`, `.isqle`, `.isqlb`, `.isqlp`, success receipt projection, rollback receipt projection.

- [ ] Generate deterministic example program with causal instruction DAG.
- [ ] Demonstrate successful atomic execution and failed atomic rollback.
- [ ] Report registry/program/snapshot/stream byte costs separately.
- [ ] Run full source suite.
- [ ] Build wheel offline with `--no-build-isolation`.
- [ ] Install wheel into fresh venv with `PYTHONPATH` cleared and rerun full suite.
- [ ] Validate `EXEC/R4/DSRP` with the real ISQL Core v0.4 `parse_code()`.
- [ ] Generate checksums, ZIP, extract ZIP, verify every checksum, rerun source and installed-wheel suites from extracted package.
