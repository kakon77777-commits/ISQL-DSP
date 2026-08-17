# AI_HANDOFF — ISQL-DSR Runtime v0.6.0

## Canonical rule

Do not promote JSON, Markdown, natural language, receipt text, or human-readable field names into the canonical machine layer.

Canonical artifacts are `.isqlr`, `.isqln`, `.isqle`, `.isqlb`, and `.isqlp`.

## Non-negotiable invariants

1. Registry refs are references, not meaning itself.
2. Registered snapshots are bound to registry revision + prefix hash.
3. Positive and negative relation sets are disjoint.
4. Native replay and program execution must not require `SemanticState` materialization.
5. `.isqlp` instruction opcodes and effect masks are numeric and must agree exactly.
6. Program dependency graphs must be acyclic and closed over the program instruction set.
7. Program execution is atomic at publication boundary: failure returns the original base state.
8. A program is anchored to base revision + registered-state hash.
9. Program execution order is deterministic topological order with numeric ref tie-breaks.
10. `.isqlb` causal dependencies form a DAG. Missing dependencies and cycles fail closed.
11. Merge conflicts are emitted only among causally incomparable maximal changes; a dependent branch may supersede its ancestor.
12. `.isqlp` and `.isqlb` do not mutate the registry. Required refs must already exist.
13. Compression/storage claims must count registry, program, stream and decoder side information.
14. Core envelope `R4` is transport compatibility with Core v0.4, not DSR release identity.
15. `DSRE` means event-stream payload; `DSRP` means causal-program payload.

## v0.6 execution model

Program:

`base state + causal instruction DAG -> internal working states -> commit OR rollback`

A failed instruction may have predecessors that executed internally, but those intermediate states are never returned as the committed result.

Execution receipts are inspection outputs. They may contain a human-readable error code for debugging, but that string is not canonical machine state.

## Branch causality

`depends_on` is numeric causal metadata, not a human workflow note. During merge, only causally maximal changes participate in conflict selection. Two incomparable maximal branches that disagree still produce an explicit machine conflict.

## Next plausible frontier

- Conditional guards / preconditions encoded as native predicates.
- Reusable subprograms and call/return semantics.
- Program receipts as optional binary audit artifacts.
- Transaction groups across multiple identities/states.
- Capability/effect permissions and sandboxed operator sets.
- Distributed registry reconciliation and signed program provenance.
