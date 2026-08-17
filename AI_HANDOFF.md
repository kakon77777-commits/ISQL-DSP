# AI_HANDOFF — ISQL-DSR Runtime v0.8.0

## Canonical rule

Do not promote JSON, Markdown, natural-language labels, debug names, argument names, permission names, or inspection field names into the canonical machine layer. `.isqlr/.isqln/.isqle/.isqlb/.isqlp` are canonical binary artifacts. Human-readable content is an optional projection.

## v0.8 invariants

1. v0.7 VM `.isqlp` programs remain decodable. v0.8 uses VM program format version 8 under the same artifact family.
2. Program arguments and return values are addressed by numeric refs in `REGISTER_ID`.
3. Argument sets are exact: missing or undeclared arguments fail before commit.
4. Only declared return registers may escape a successful transaction; every declared return register must be initialized.
5. `CAP_AXIS_READ` is distinct from `CAP_AXIS` mutation permission.
6. Global capability masks are upper bounds; actual state-slot grants are checked separately.
7. `LOAD_AXIS` is a native read and `STORE_AXIS` is a native write. Neither requires conversion to `SemanticState` or inspection JSON.
8. Structured CALL maps every dynamic callee state slot to a caller state slot by numeric alias rows.
9. CALL argument registers and return registers are positional machine interfaces; callee register files are isolated from caller register files except for explicit argument/return transfer.
10. CALL/RETURN are synchronization barriers for the v0.8 scheduler.
11. Parallel batches are deterministic and hazard-free. State write/write and register RAW/WAR/WAW hazards may not execute in the same batch.
12. A batch commits only after all workers succeed; a worker failure rolls back the entire transaction.
13. Serial and parallel execution of the same deterministic program/state set must produce identical final registered-state hashes and return values.
14. `EXEC/R4/DSRV` remains the Core transport envelope. `R4` is Core resolution, not DSR version.
15. Registry, decoder, program, and other side information must be counted in compression/cost claims.

## Current machine register model

Registers contain validated DSR semantic values such as point, interval, or candidate-set values. Registers are not strings and do not require human variable names.

## Current native dataflow operations

- `VM_OP_LOAD_AXIS = 1101`: state axis value -> destination register.
- `VM_OP_STORE_AXIS = 1102`: source register -> state axis value.

## Current scheduler model

`vm_execution_batches(program)` derives deterministic batches from causal dependencies plus state/register hazards. Parallel execution uses a worker pool for batch computation and canonical instruction-ref ordering for commit.

## Next frontier

Do not add features merely for readability. Plausible v0.9 directions are machine-value arithmetic/comparison operators, register-level guards, typed register schemas, program composition/linking, persistent deterministic execution attestations, or a lower-level native bytecode dispatch table. Choose only after a concrete AI-native use case requires them.
