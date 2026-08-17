# AI_HANDOFF — ISQL-DSR Runtime v0.7.0

## Canonical rule

Do not promote JSON, Markdown, natural-language labels or inspection field names into the canonical machine layer. `.isqlr/.isqln/.isqle/.isqlb/.isqlp` are canonical artifacts.

## v0.7 invariants

1. v0.6 native programs remain valid; v0.7 VM programs are an additional `.isqlp` codec.
2. VM state slots are numeric registry refs in `STATE_SLOT_ID`.
3. Guards are evaluated directly against `NativeSemanticState`; no inspection-state conversion is required.
4. Every instruction has an exact canonical effect mask and required capability mask.
5. Missing capabilities fail before publishing state mutations.
6. Root multi-state bindings may be exact; synchronous callees must currently use one dynamic binding.
7. CALL is synchronous. Recursive call cycles fail closed.
8. RETURN is terminal and may not have downstream instructions.
9. A multi-state transaction publishes every resulting slot together or returns the original state-set unchanged.
10. Transaction receipts are runtime outputs, not a new canonical persistence format in v0.7.
11. Core `R4` remains transport resolution. `DSRV` identifies the v0.7 VM payload family.
12. Registry/decoder side information must be counted in compression claims.

## Current guard family

- state-hash equality;
- axis present;
- axis absent;
- axis semantic-value equality;
- relation polarity equality in $\{-1,0,+1\}$.

## Current capability family

Context, axis, relation, projection, topology and CALL capabilities are numeric bit masks. Do not replace them with human-readable permission strings in canonical programs.

## Next frontier

- explicit value-return registers / arguments between subprograms;
- capability tokens scoped to state slots or object subsets;
- cross-state read/write operators;
- deterministic scheduling for parallel independent instructions;
- persistent transaction receipts / attestations only if an actual use case requires them.
