# ISQL-DSR v0.4 Native Symbol Space and Event Stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the v0.4 canonical machine path use an append-only numeric symbol registry plus independently replayable native event streams, so repeated semantic identifiers are referenced rather than embedded as human-readable strings in every state/event.

**Architecture:** Keep v0.3 `SemanticState` and JSON as inspection/import compatibility only. Add `.isqlr` registry artifacts with stable namespaced numeric references and prefix hashes; add a registered `.isqln` snapshot format whose semantic identifiers are integer refs pinned to an exact registry prefix; add `.isqle` event streams encoded with numeric opcodes and symbol refs. Native replay must reconstruct registered snapshots without JSON becoming canonical.

**Tech Stack:** Python 3.11+, stdlib dataclasses/hashlib/struct/argparse/unittest/setuptools only.

## Global Constraints

- Existing v0.3 package remains untouched; development occurs only in `ISQL_DSR_Runtime_v0.4.0`.
- Canonical machine artifacts are binary; JSON/Markdown are projections only.
- Registry is append-only and prefix-verifiable.
- Native state/event decoding fails closed on registry revision/hash mismatch.
- No network dependency is required for runtime or tests.
- TDD: every production feature requires a failing test first.

---

### Task 1: Append-only native symbol registry

**Files:**
- Create: `src/isql_dsr/registry.py`
- Create: `tests/test_registry_v04.py`

**Interfaces:**
- Produces: `NativeSymbolRegistry`, `SymbolEntry`, `SymbolNamespace`, `encode_registry`, `decode_registry`, `registry_hash`, `extend_registry_for_state`, `extend_registry_for_events`.

- [ ] Write tests for deterministic interning, namespace separation, append-only IDs, prefix validation, binary round-trip, and canonical sorted extension.
- [ ] Run tests and verify RED due to missing registry module.
- [ ] Implement immutable registry plus `.isqlr` codec.
- [ ] Run registry tests and full suite.

### Task 2: Registered AI-native snapshot

**Files:**
- Create: `src/isql_dsr/machine.py`
- Modify: `src/isql_dsr/native.py`
- Create: `tests/test_registered_state_v04.py`

**Interfaces:**
- Produces: `NativeSemanticState`, native component dataclasses, `compile_registered_state`, `inspect_registered_state`, `encode_registered_state`, `decode_registered_state`, `registered_state_hash`.

- [ ] Write tests showing high-frequency identifiers are absent from `.isqln`, refs are numeric, registry pin is enforced, equivalent state ordering yields identical bytes, and inspection round-trip preserves semantics excluding history.
- [ ] Verify RED.
- [ ] Implement machine state and registered snapshot codec.
- [ ] Run targeted and full tests.

### Task 3: Canonical native event stream

**Files:**
- Create: `src/isql_dsr/stream.py`
- Create: `tests/test_native_stream_v04.py`

**Interfaces:**
- Produces: `NativeTransitionEvent`, `NativeEventStream`, `compile_native_event`, `inspect_native_event`, `encode_event_stream`, `decode_event_stream`, `replay_native_stream`.

- [ ] Write tests for numeric event identifiers/opcodes, registry-pinned stream round-trip, event-chain next-hash verification, deterministic replay, tamper rejection, and absence of operation/schema labels.
- [ ] Verify RED.
- [ ] Implement event compiler/codec/replay.
- [ ] Run targeted and full tests.

### Task 4: Core R4/DSRR bridge and CLI

**Files:**
- Modify: `src/isql_dsr/bridge.py`
- Modify: `src/isql_dsr/cli.py`
- Modify: `src/isql_dsr/__init__.py`
- Create: `tests/test_registered_bridge_v04.py`
- Create: `tests/test_cli_v04.py`

**Interfaces:**
- Produces: Core `SEM/R4/DSRR`, `STATE/R4/DSRR`, and `EXEC/R4/DSRE` wires; CLI commands `registry-build`, `registered-pack`, `registered-inspect`, `stream-pack`, `stream-replay`, `bridge-r4`.

- [ ] Write failing bridge/CLI tests.
- [ ] Implement decimal binary envelopes that remain parseable by Core v0.4 `parse_code()`.
- [ ] Implement CLI workflows without making JSON canonical.
- [ ] Run full tests.

### Task 5: Release verification and package

**Files:**
- Modify: `pyproject.toml`, `README.md`, `AI_HANDOFF.md`, `RELEASE_NOTES.md`
- Create: `docs/NATIVE_FORMAT_v0.4.md`
- Create: `examples/v0.4/*`
- Regenerate: `validation/*`, `validation.json`, `CHECKSUMS.sha256`, `dist/*.whl`

- [ ] Update version/schema docs to v0.4.
- [ ] Generate registry/snapshot/stream/Core-wire end-to-end example.
- [ ] Run source suite.
- [ ] Build wheel offline with `--no-build-isolation`, install into a fresh venv, and run installed suite without `PYTHONPATH`.
- [ ] Validate Core v0.4 parser against R4 wires.
- [ ] Create ZIP, extract it, verify every checksum, and rerun the suite from extracted contents.
