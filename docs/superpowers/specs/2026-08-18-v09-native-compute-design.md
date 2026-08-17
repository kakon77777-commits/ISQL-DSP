# ISQL-DSR v0.9 Native Compute Design

## Goal

Turn the v0.8 register-dataflow VM into a machine-value computation layer without introducing a program counter or human-readable canonical control language.

## Architecture

v0.9 keeps the causal instruction DAG. Native comparisons write boolean `PointValue` registers. Conditional control uses instruction predication: a false predicate skips an instruction, while a false register guard aborts the whole transaction. This preserves deterministic batching and atomic rollback.

The canonical `.isqlp` format advances to VM format version 9 while v7/v8 remain decodable. `VMInstruction` gains optional numeric register guards and an optional boolean predicate register; defaults preserve old constructors.

A static linker composes multiple `NativeVMProgram` DAG modules into a new `NativeVMProgram`. Module terminal RETURN instructions are removed, instruction refs must remain globally unique, bindings/capabilities are merged canonically, and sequential composition adds causal edges from prior module exits to next module entries.

## Register algebra

New register-only opcodes have zero state effect and zero capability requirement:

- CONST: semantic value -> register
- MOVE: register -> register
- ADD, SUB, MUL, DIV: numeric point algebra
- EQ: structural semantic-value equality -> boolean point
- LT, LE: numeric point comparison -> boolean point

Numeric rules:

- booleans are not numeric;
- int/int ADD/SUB/MUL preserves int;
- mixed numeric arithmetic promotes to float;
- DIV returns float and rejects zero divisor;
- LT/LE require numeric point values;
- EQ accepts any valid semantic value.

## Control semantics

Register guard types:

- initialized(register)
- equals(register, semantic_value)

A failed register guard aborts the transaction.

Instruction predicate:

- no predicate ref => unconditional;
- predicate ref must contain `PointValue(bool)`;
- matching expected boolean => execute;
- non-matching boolean => skip with no state/register mutation;
- missing/wrong-type predicate => fail closed.

Dependencies represent structural completion, so downstream instructions may depend on skipped instructions.

## Scheduler

Hazard analysis includes:

- register reads/writes of algebra/comparison opcodes;
- register guard reads;
- predicate register reads;
- existing LOAD/STORE/CALL register traffic.

Predicated instructions remain conservatively scheduled; v0.9 does not attempt proof that opposite predicates make same-state writes mutually exclusive.

## Linking

`link_vm_programs(...)` accepts modules pinned to the same registry prefix. It rejects:

- duplicate instruction refs;
- conflicting state bindings;
- registry-pin mismatch;
- unsupported call mapping across incompatible module assumptions.

For sequential mode, next-module entry instructions depend on all prior-module exit instructions. RETURN instructions are stripped because the linked frame itself owns returns.

## Compatibility

- v7 and v8 `.isqlp` decode exactly as before.
- Core wire remains `EXEC/R4/DSRV`; DSR VM payload version differentiates v9.
- JSON remains inspection only.
