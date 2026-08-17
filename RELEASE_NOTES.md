# ISQL-DSR Runtime v1.0.0 Release Notes

## Status

First stable computation-architecture milestone for the internal AI-native ISQL-DSR line.

## Added

- `VectorValue` and `RecordValue` native semantic values.
- Registry namespace `FIELD_ID` for numeric record-field identity.
- Native vector register operations: pack, get, length.
- Native record register operations: pack, get, immutable set.
- Program-format version 10 with typed argument/return signatures.
- Strict native machine type validation at root and CALL boundaries.
- `REPEAT_CALL` bounded subprogram iteration with `VM_MAX_REPEAT = 1024`.
- Static optimizer API `optimize_vm_program()`.
- CLI `vm-optimize`.
- v1.0 examples and native computation design/plan documents.

## Compatibility

- v7, v8, and v9 `.isqlp` program decoders remain supported.
- Legacy programs receive implicit `TYPE_ANY` function signatures.
- Existing `vm-run` and `vm-link` inspection response schema labels remain unchanged for compatibility.
- Core bridge remains `EXEC/R4/DSRV`.

## Safety / semantic boundaries

- No arbitrary backward jump.
- No unbounded loop or recursive call cycle.
- Repeat count is encoded canonically and hard-bounded.
- Optimizer is deliberately conservative and must preserve transaction-visible failure/state/return semantics.
- Human-readable formats remain projection layers, not canonical program/state sources.
