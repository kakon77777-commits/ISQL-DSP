# ISQL DSR v0.3 — AI Handoff

## Canonical rule

**The `.isqln` native binary state is canonical. JSON is not.**

Do not “simplify” the runtime by making human-readable JSON authoritative again.

## Read order

1. `docs/ISQL_Canonical_Anchor_v1.0_2026-08-17.md`
2. `docs/ISQL_DSR_Implementability_Revision_v0.1_2026-08-17.md`
3. `docs/NATIVE_FORMAT_v0.3.md`
4. `src/isql_dsr/native.py`
5. `src/isql_dsr/model.py`
6. `src/isql_dsr/runtime.py`
7. tests

## Invariants

- Identity is separate from mutable representation.
- Runtime is finite-active while the coordinate universe may grow without a fixed global maximum.
- Registry/reference IDs are not meaning.
- Canonical hash is SHA-256 over canonical native bytes.
- JSON/natural language/visual output is a projection or inspection interface.
- Known runtime operations must use numeric opcodes in canonical history.
- Fail closed on revision/hash mismatch.
- AI/model output is a proposal; deterministic runtime validation owns canonical state.
- Core `R3/DSRN` native wire must remain lossless for the state/profile it declares.
- Do not claim CEO convergence without stated mathematical assumptions.

## v0.3 implemented

- native typed primitive codec
- native semantic state codec
- native state hash authority
- numeric event opcodes
- fixed-layout fusion proposal/decision history
- native `.isqln` CLI artifacts
- inspection JSON projection
- native Core `SEM/R3` and `STATE/R3` digits-only wire
- legacy `R2/DSR` JSON bridge retained separately
- v0.2 topology and fusion behavior preserved

## Migration

Do not reuse v0.2 non-genesis previous-hash chains as v0.3. Rebuild them by replay so hashes are recomputed over native bytes.

## Recommended next frontier

v0.4 should move more semantic identifiers away from raw text toward explicit machine registries / symbol references, add typed/directed topology descriptors, negative relation proposals, branch/merge semantics, and a native event-stream artifact separate from materialized state snapshots.
