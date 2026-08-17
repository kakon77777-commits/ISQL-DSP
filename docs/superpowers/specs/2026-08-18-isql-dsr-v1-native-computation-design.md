# ISQL-DSR v1.0 Native Computation Architecture Design

## Goal

Complete the first stable AI-native computation layer without abandoning the causal DAG VM. v1.0 adds typed composite machine values, register-local immutable containers, statically typed program signatures, bounded subprogram iteration with explicit termination caps, and a semantics-preserving machine optimizer.

## Canonical constraints

- `.isqlp` remains the only persisted program artifact.
- Human-readable JSON/text remains inspection only.
- v0.9 programs remain decodable.
- No arbitrary backward jump or unbounded recursion.
- All new control remains fail-closed and transaction-atomic.
- Parallel execution remains deterministic.
- Core transport remains `EXEC/R4/DSRV`.

## 1. Composite machine values

Extend `SemanticValue` with two immutable machine-native values:

- `VectorValue(items)` — ordered tuple of semantic values.
- `RecordValue(fields)` — sorted tuple of `(field_ref, semantic_value)` pairs with positive numeric field refs.

Add `FIELD_ID` to the shared native symbol registry. Record field names exist only in `.isqlr`; `.isqlp/.isqln` store refs.

Native semantic codec gains explicit numeric tags for vector and record. Recursive nesting is supported with a bounded decode-depth guard to prevent malformed resource-exhaustion inputs.

## 2. Register-local containers

Add native opcodes:

- `VECTOR_PACK`: source registers -> immutable `VectorValue`.
- `VECTOR_GET`: vector + integer index register -> element.
- `VECTOR_LEN`: vector -> integer point.
- `RECORD_PACK`: `(field_ref, source_register)` pairs -> immutable `RecordValue`.
- `RECORD_GET`: record + field_ref -> value.
- `RECORD_SET`: record + field_ref + source register -> new immutable record.

The scheduler treats source registers as reads and destination registers as writes. Container mutation never mutates an object in place.

## 3. Native function signatures

Introduce numeric machine type tags and `VMRegisterSpec(register_ref, type_tag)`. A `VMFunctionSignature` contains ordered argument specs and return specs.

v1.0 programs encode signatures in program format version 10. Existing v7/v8/v9 programs decode with implicit `TYPE_ANY` signatures.

Runtime validates root arguments, CALL argument transfer, callee returns, and root returns against signatures. Type mismatch aborts the whole transaction.

## 4. Bounded iteration

Add `VM_OP_REPEAT_CALL`. Its payload contains:

- callee program ref;
- slot alias map;
- argument register map;
- return register map;
- fixed positive iteration count.

A protocol constant `VM_MAX_REPEAT = 1024` bounds iteration. Each iteration is a synchronous subprogram call in the same transaction. Call cycles remain forbidden except through `REPEAT_CALL` itself, whose finite count provides the termination bound. Any iteration failure rolls back every state to the transaction base.

## 5. Machine optimizer

Add a pure static optimizer that produces another canonical `NativeVMProgram` and never executes a program.

v1.0 optimization passes:

1. constant folding for scalar algebra/comparisons where all inputs are prior constants;
2. dead register-computation elimination for pure register instructions whose outputs do not reach a return, state write, guard/predicate, CALL/REPEAT_CALL argument, or another live instruction;
3. dependency cleanup after removal.

Optimizer must preserve program signature, bindings, registry pin, capabilities, and observable state/return semantics. Tests compare original and optimized results and require identical final registered-state hashes and return values.

## 6. Release criteria

- all v0.9 tests remain green;
- new v1.0 TDD tests cover codec, type errors, containers, repeat bounds/rollback, optimizer equivalence;
- source and fresh-wheel suites pass without source `PYTHONPATH` for installed-wheel testing;
- true ISQL Core v0.4 parser accepts `EXEC/R4/DSRV` and exact-round-trips;
- final ZIP is checksum-verified after extraction.
