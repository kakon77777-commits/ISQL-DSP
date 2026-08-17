# ISQL-DSR v0.3 AI-Native State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make deterministic typed binary/native state the canonical source of truth while demoting JSON and human-readable output to optional inspection projections.

**Architecture:** Keep the Python `SemanticState` object model as an in-memory API, but define a field-name-free, versioned native binary codec with fixed numeric section tags, scalar tags, and event opcodes. State identity/hash, replay chaining, and the new Core bridge use native bytes. JSON remains a reversible inspection projection only. The v0.2 directory remains unchanged; v0.3 has explicit migration/import boundaries.

**Tech Stack:** Python 3.11+ standard library only (`dataclasses`, `struct`, `hashlib`, `json`, `argparse`, `unittest`, `zipfile`).

## Global Constraints

- Canonical state is native binary, not JSON/Markdown/natural language.
- Native format is deterministic, typed, versioned, self-delimiting, and round-trippable.
- Schema fields and operations use numeric tags/opcodes; do not serialize human-facing field names into canonical native bytes.
- Human-readable JSON is an inspection projection and must never determine canonical state hash.
- No `unicode_escape` round-trip; UTF-8 text values are encoded as UTF-8 bytes only when text is actual semantic data.
- Existing v0.2 release directory remains untouched.
- Core compatibility must be preserved through a digits-only `SEM/STATE` wire profile using native payload bytes.
- TDD: every production behavior begins with a failing test.

---

### Task 1: Native primitive codec

**Files:**
- Create: `src/isql_dsr/native.py`
- Test: `tests/test_native_primitives.py`

**Interfaces:**
- Produces: `encode_uvarint(int) -> bytes`, `decode_uvarint(bytes, offset=0) -> tuple[int,int]`, `encode_value(JSONValue) -> bytes`, `decode_value(bytes, offset=0) -> tuple[JSONValue,int]`.

- [ ] Write tests for canonical uvarints, signed integers, finite float64, UTF-8 strings, lists, and maps independent of insertion order.
- [ ] Run tests and observe missing-module / missing-symbol failure.
- [ ] Implement minimal typed primitive codec using numeric tags.
- [ ] Re-run tests and keep them green.

### Task 2: Native semantic state codec

**Files:**
- Modify: `src/isql_dsr/native.py`
- Modify: `src/isql_dsr/model.py`
- Test: `tests/test_native_state.py`

**Interfaces:**
- Produces: `encode_state(SemanticState) -> bytes`, `decode_state(bytes) -> SemanticState`, `native_state_hash(SemanticState) -> str`.

- [ ] Write a failing test showing equivalent states with different input ordering produce identical bytes.
- [ ] Write a failing test showing native bytes contain no JSON field labels such as `identity`, `axes`, `relations`, `history`.
- [ ] Write a failing exact native round-trip test covering all v0.2 value/graph/topology/projection/history types.
- [ ] Implement numeric section layout, fixed magic/version, and model schema v0.3.
- [ ] Verify all tests pass.

### Task 3: Native event opcodes and canonical history

**Files:**
- Modify: `src/isql_dsr/native.py`
- Modify: `src/isql_dsr/events.py`
- Test: `tests/test_native_events.py`

**Interfaces:**
- Produces: `operation_opcode(str) -> int`, `operation_name(int) -> str`; native history encoding uses opcodes for known operations.

- [ ] Write failing tests proving operation names are absent from canonical native bytes while replay still round-trips.
- [ ] Add stable numeric opcodes for all v0.2 transition operations.
- [ ] Encode/decode history records using opcodes without changing runtime inspection shape.
- [ ] Verify replay tests pass.

### Task 4: Make native bytes authoritative

**Files:**
- Modify: `src/isql_dsr/canonical.py`
- Modify: `src/isql_dsr/runtime.py`
- Modify: `src/isql_dsr/validation.py`
- Test: `tests/test_native_authority.py`

**Interfaces:**
- `state_hash(state)` becomes SHA-256 of native state bytes.
- `inspection_json(state)` is explicitly non-authoritative.

- [ ] Write failing test that JSON formatting/order changes cannot alter canonical hash.
- [ ] Write failing test that history previous/next hashes are derived from native bytes.
- [ ] Switch canonical hashing and validation to native codec.
- [ ] Verify full suite.

### Task 5: AI-native Core bridge

**Files:**
- Modify: `src/isql_dsr/bridge.py`
- Test: `tests/test_native_bridge.py`

**Interfaces:**
- Produces Core parseable `SEM/R3` and `STATE/R3` digits-only wires with control `DSRN` and native payload bytes.
- Preserve optional legacy v0.2 inspection bridge functions under explicit legacy names if needed.

- [ ] Write failing tests for digits-only native wire and Core v0.4 parser-compatible envelope shape.
- [ ] Implement byte-to-decimal transport without JSON payload dependence.
- [ ] Verify native wire decodes back to semantic/state objects.

### Task 6: Inspection-only CLI

**Files:**
- Modify: `src/isql_dsr/cli.py`
- Modify: `src/isql_dsr/__init__.py`
- Test: `tests/test_cli_v03.py`

**Interfaces:**
- `native-pack --state <inspection.json> --out <file.isqln>`
- `native-inspect --native <file.isqln>`
- `native-hash --native <file.isqln>`
- `bridge --native <file.isqln> --domain sem|state|bundle`

- [ ] Write failing CLI tests.
- [ ] Implement commands so JSON is explicitly import/inspection rather than canonical storage.
- [ ] Verify CLI and full suite.

### Task 7: Release examples and verification

**Files:**
- Create/Modify: `examples/v0.3/*`
- Modify: `README.md`
- Modify: `AI_HANDOFF.md`
- Modify: `RELEASE_NOTES.md`
- Modify: `pyproject.toml`
- Create: `validation/*`, `validation.json`, `CHECKSUMS.sha256`, `dist/isql_dsr_runtime-0.3.0-py3-none-any.whl`

**Interfaces:**
- Deliver a native `.isqln` state file plus optional inspection JSON and native Core wires.

- [ ] Generate a native end-to-end example from a v0.3 state.
- [ ] Run source-tree full tests.
- [ ] Build wheel and install into a fresh venv.
- [ ] Run installed full tests and CLI smoke test without `PYTHONPATH=src`.
- [ ] Verify Core v0.4 parser accepts native SEM/STATE wires.
- [ ] Build final ZIP, extract it, verify checksums, and re-run tests from extracted content.
