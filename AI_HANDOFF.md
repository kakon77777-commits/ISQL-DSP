# AI_HANDOFF — ISQL-DSR Runtime v1.0.0

## Read this first

This is the **internal AI-native parallel implementation** of ISQL-DSR. Do not redesign it around human readability.

Canonical authority order:

1. `.isqlr` shared machine registry;
2. `.isqln` registered native state;
3. `.isqle` native transition stream;
4. `.isqlb` native causal branch;
5. `.isqlp` native program.

JSON/Markdown/text are inspection or documentation projections only.

## Invariants that must not be broken

- Registry IDs are stable references, never identical to meaning.
- Identity and representation remain separate.
- Canonical state/program hashes derive from native bytes, not rendered JSON.
- Existing registry prefix hashes remain valid after append-only extension.
- VM transactions publish all-or-nothing.
- Program execution remains deterministic under serial and supported parallel scheduling.
- CALL cycles remain fail-closed.
- No unbounded iteration/recursion may enter the canonical VM without an explicit finite resource bound.
- Core transport grammar remains independent of DSR release numbering.

## v1.0 machine-value layer

Semantic values now include:

- point;
- interval;
- candidate set;
- vector;
- numeric-field record.

Record field names belong in `.isqlr` under `FIELD_ID`; canonical records contain only numeric field refs.

## v1.0 function contract

Program format 10 encodes top-level argument and return type tags. Legacy v7/v8/v9 programs decode with `TYPE_ANY` signatures.

Do not silently coerce BOOL to INT. Do not silently coerce arbitrary semantic values across signature boundaries.

## v1.0 bounded iteration

`REPEAT_CALL` is a finite subprogram-repetition primitive. Its count must satisfy:

$$
1\le k\le1024.
$$

This is not permission to add unrestricted JMP or backward edges. Any failure in any iteration rolls back the whole root transaction.

## v1.0 optimizer

The optimizer is not allowed to optimize by intuition. It may only apply transformations whose observable transaction semantics are preserved.

Current intentional conservatism:

- fold scalar register operations only with statically known operands;
- remove dead unconditional CONST instructions;
- preserve or bridge causal dependencies after removal;
- do not erase runtime error paths that are not statically discharged.

## Next research frontier

Potential post-v1.0 work should be treated as a new design phase rather than automatic version churn. Candidates include richer structural typing, verified cost/resource types, machine-level optimizer proofs, and native inter-agent program exchange benchmarks.
