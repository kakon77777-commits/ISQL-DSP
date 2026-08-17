# ISQL-DSR Runtime v0.6.0 Release Notes

## Theme: Causal Native Programs and Atomic Transactions

v0.6 upgrades EXEC from replayable native events to composable machine programs.

### Added

- `PROGRAM_ID` registry namespace.
- `INSTRUCTION_ID` registry namespace.
- `.isqlp` canonical program artifact.
- `NativeInstruction` and `NativeProgram`.
- Numeric operator effect masks.
- Causal instruction dependency DAG validation.
- Deterministic topological program execution.
- Atomic rollback semantics.
- `ProgramExecutionReceipt` inspection result.
- `NativeBranch.depends_on` causal metadata.
- Causal branch precedence in native merge.
- `EXEC/R4/DSRP` Core program envelope.
- CLI program pack/run/bridge commands.

### Changed

- Branch artifact format advances to v6.
- Branch CLI inspection schema advances to v0.6.
- Branch merge inspection schema advances to v0.6.
- Native event operator implementation is factored into `apply_native_operation()` so event replay and program execution share one numeric execution core.

### Preserved

- `.isqle` remains the canonical low-level event stream.
- `EXEC/R4/DSRE` remains available for event-stream transport.
- Registry prefix hashes remain append-only compatible.
- Human-readable JSON remains non-canonical.

### Compatibility note

The supplied ISQL Core v0.4 parser only accepts `R0-R4`; therefore `.isqlp` uses `EXEC/R4/DSRP`, not a fictitious `R5` transport resolution.
