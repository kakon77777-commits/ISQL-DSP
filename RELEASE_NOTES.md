# ISQL Dynamic Spectrum Runtime v0.1.0 — Release Notes

## First parallel internal runtime

This release intentionally does **not** modify or replace ISQL Core Runtime v0.4.

### Implemented

- Canonical dynamic semantic state with stable identity.
- Finite-active spectrum axes.
- Point, interval, and candidate-set spectral values.
- Per-axis uncertainty and resolution.
- Typed semantic relations.
- Multiple semantic projections.
- Context as state.
- Fail-closed transition events with revision and previous-hash guards.
- Deterministic replay with history/provenance records.
- Semantic state diff.
- Replay-based history validation.
- Canonical UTF-8 JSON and SHA-256 state hash.
- Lossless ISQL Core `STATE/R2` transport envelope.
- CLI: `new`, `hash`, `validate`, `apply`, `replay`, `diff`, `bridge`.
- Self-contained examples and theory anchor documents.

### Deliberately deferred

- Learned/AI semantic analyzers.
- Automatic axis induction or ontology evolution.
- Probabilistic distributions beyond point/interval/candidate values.
- Topological descriptors beyond the current relation structure.
- CEO operator implementation and convergence certificates.
- Direct compilation into Core v0.4 spectral integer registry.
- EXEC semantics.

The next logical version is v0.2: typed topology descriptors + uncertainty-aware merge/fusion + a formal Core SEM/STATE packet bridge.
