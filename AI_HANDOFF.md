# ISQL DSR v0.4 — AI Handoff

## Canonical rule

**The v0.4 canonical machine state is the tuple of a registry-bound `.isqln` snapshot plus its compatible `.isqlr` registry prefix. Evolution history is canonicalized separately as `.isqle`.**

Do not make JSON authoritative again.

## Read order

1. `docs/ISQL_Canonical_Anchor_v1.0_2026-08-17.md`
2. `docs/ISQL_DSR_Implementability_Revision_v0.1_2026-08-17.md`
3. `docs/NATIVE_FORMAT_v0.4.md`
4. `src/isql_dsr/registry.py`
5. `src/isql_dsr/machine.py`
6. `src/isql_dsr/stream.py`
7. `src/isql_dsr/bridge.py`
8. tests

## Non-negotiable invariants

- Human readability is not a canonical-layer requirement.
- Registry ID is a reference, not meaning.
- Registry is append-only; existing ID -> payload bindings must never be rewritten.
- Snapshot and stream pin a registry revision plus prefix hash.
- A newer compatible registry may decode an older artifact only when the pinned prefix hash matches.
- Registered `.isqln` stores numeric references for repeated semantic identifiers.
- `.isqln` is materialized state; `.isqle` is evolution history. Do not merge them back by default.
- Operation names are numeric opcodes in canonical event streams.
- Fail closed on registry, revision, previous-hash, next-hash or payload-integrity mismatch.
- JSON / natural language / visual layouts are inspection/import projections only.
- High-level algorithms may use an interpretation adapter when needed; the adapter output is never promoted to canonical authority merely for convenience.
- AI/model output remains proposal input. Deterministic runtime rules own canonical transitions.

## v0.4 artifacts

### `.isqlr`
Append-only namespaced machine symbol registry.

### `.isqln`
Registered materialized snapshot. Contains registry pin and numeric refs. Does not contain transition history.

### `.isqle`
Registered native event stream. Contains numeric event IDs/opcodes, operation-specific numeric layouts, and registered snapshot hash chaining.

## Core bridge

- `SEM/R4/DSRR`: registered semantic snapshot with context removed.
- `STATE/R4/DSRR`: full registered snapshot.
- `EXEC/R4/DSRE`: registered native event stream.

Legacy `R3/DSRN` and `R2/DSR` remain separate compatibility paths.

## Important v0.4 limitation

The deterministic replay engine currently resolves registered symbols into the established inspection-domain runtime for selected high-level semantics such as topology/fusion, then recompiles the result to registered native state. This is an **interpretation adapter**, not canonical storage. A future version may move more high-level operators directly onto numeric machine structures.

## Recommended next frontier

- native negative relation assertions / retractions;
- branch and merge event streams;
- directly numeric topology operators;
- online registry-growth events and distributed registry reconciliation;
- binary semantic values beyond JSON-compatible scalar/container payloads;
- machine-native execution operators in `EXEC` rather than only replay transport.
