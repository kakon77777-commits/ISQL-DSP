# ISQL-DSR Runtime v0.9.0 — Release Notes

v0.9 adds machine-value computation and conditional control to the existing causal DAG VM without introducing a program counter or human-readable canonical control language.

## Added

- VM program payload format version 9.
- register guard metadata and predicate-register metadata on `VMInstruction`.
- `VM_OP_CONST`, `VM_OP_MOVE`.
- `VM_OP_ADD`, `VM_OP_SUB`, `VM_OP_MUL`, `VM_OP_DIV`.
- `VM_OP_EQ`, `VM_OP_LT`, `VM_OP_LE`.
- fail-closed initialized/equality register guards.
- skip-on-false boolean instruction predicates.
- scheduler hazards for guard/predicate/algebra register access.
- static `link_vm_programs()` DAG composition.
- CLI `vm-link`.

## Compatibility

- v0.7 VM `.isqlp` remains decodable.
- v0.8 VM `.isqlp` remains decodable.
- Core VM transport remains `EXEC/R4/DSRV`.
- inspection JSON remains non-canonical.

## Atomicity

Arithmetic type errors, divide-by-zero, failed register guards, invalid predicates, and linked-program validation errors never publish partial state or return registers.
