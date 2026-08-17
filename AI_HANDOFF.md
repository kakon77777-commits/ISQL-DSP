# ISQL DSR v0.1 — AI Handoff

## Read first

This package is the **parallel internal dynamic-spectrum runtime**. Do not merge its semantic model back into the ISQL Core v0.4 integer registry as if registry IDs were meaning.

Read in this order:

1. `docs/ISQL_Canonical_Anchor_v1.0_2026-08-17.md`
2. `docs/ISQL_DSR_Implementability_Revision_v0.1_2026-08-17.md`
3. `README.md`
4. `src/isql_dsr/model.py`
5. `src/isql_dsr/runtime.py`
6. tests

## Invariants that must survive later versions

- Identity is separate from mutable representation.
- Runtime state is finite-active even if the coordinate universe is unbounded over time.
- Registry/reference IDs are not semantic meaning.
- Context, relations, projections, and history are first-class state.
- Transition application is fail-closed on revision/hash mismatch.
- Canonical JSON round-trip must remain exact for the canonical object.
- AI/model analysis is a proposal; deterministic runtime validation owns canonical state.
- Any bridge to Core must declare what information it preserves or loses.

## v0.1 implemented

- point / interval / candidate-set spectral values
- finite-active axes with uncertainty + resolution
- typed relations
- projections
- context
- transition events
- replay
- semantic diff
- history validation
- canonical SHA-256 state hash
- lossless Core STATE/R2 envelope
- CLI

## Recommended v0.2 frontier

1. typed topology descriptors derived from relation structures
2. uncertainty-aware merge/fusion across multiple proposed semantic states
3. formal Core SEM/STATE packet bridge rather than opaque payload envelope
4. stronger event schemas and transition effect contracts
5. optional spectral-analysis profiles (Fourier/graph/ontology) behind explicit interfaces

Do not implement CEO fixed-point claims as unconditional behavior. A fixed-point or convergence certificate must name its assumptions and convergence criterion.
