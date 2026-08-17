# AI_HANDOFF — ISQL-DSR Runtime v0.2.0

This is the **internal dynamic-semantic** ISQL line. Do not collapse it back into the public ISQL Core registry representation.

## Non-negotiable invariants

1. `identity != representation != projection != reconstruction`.
2. Registry IDs / Core wire payloads are references or transport encodings, never identical to meaning.
3. Every state-changing event is fail-closed on `base_revision` and `previous_hash`.
4. Topology descriptors must bind to the exact current relation-basis hash.
5. Relation changes invalidate topology descriptors.
6. AI/model semantic output is a proposal, not canonical truth.
7. Fusion must remain deterministic under proposal input reordering.
8. Full STATE bridge must be lossless.
9. SEM bridge intentionally excludes context/history and transports semantic structure only.
10. Do not claim the decimal bridge is compression.

## v0.2 completed

- finite-active spectrum values
- typed relations
- topology descriptors + basis integrity
- two built-in topology descriptors
- replayable context/axis/relation/projection/topology transitions
- uncertainty-aware deterministic proposal fusion
- explicit conflicts
- state diff including topology changes
- replay validation
- Core-parsable SEM/R2 and STATE/R2 digits-only wires
- CLI and end-to-end examples

## Natural next frontier

v0.3 should deepen **Topology and Flow**, not add decorative encodings. Candidate work:

- directed / typed graph descriptor profiles
- persistent-homology adapter with explicit construction parameters
- topology stability tests under bounded relation perturbations
- negative/retract relation proposals in fusion
- projection-level provenance and validator contracts
- semantic merge across divergent state branches
- compact numeric bridge replacing fixed-width decimal bytes while preserving exact reconstruction

Read `docs/ISQL_Canonical_Anchor_v1.0_2026-08-17.md` before making architecture-level changes.
