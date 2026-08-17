# ISQL-DSR Runtime v0.8.0 — Release Notes

v0.8 extends the guarded multi-state VM into a register-based, state-scoped, cross-state dataflow runtime with deterministic parallel scheduling. It keeps the existing canonical artifact family and Core transport contract.

## Added

- `REGISTER_ID` registry namespace.
- VM program format version 8 with declared argument registers, return registers, and scoped capability rows.
- exact root argument validation and explicit return-register projection.
- `CAP_AXIS_READ` as a read-only capability distinct from axis mutation.
- `VM_OP_LOAD_AXIS` and `VM_OP_STORE_AXIS` native cross-state dataflow.
- structured multi-slot CALL aliases.
- positional CALL argument and return-register transfer.
- isolated callee register files.
- deterministic `vm_execution_batches()` scheduler.
- register RAW/WAR/WAW and state write hazard detection.
- optional parallel batch execution with canonical ordered commit.
- CLI `vm-run --arg`, `--scope`, and `--parallel` support.

## Atomicity and determinism

No program, CALL, batch, or worker may publish a partial transaction. A failed batch returns the original state-set. For deterministic native operations, serial and parallel execution are required to produce identical final state hashes.

## Compatibility

- v0.7 VM `.isqlp` artifacts remain decodable.
- v0.6 causal programs remain supported by their existing program codec.
- Core transport remains `EXEC/R4/DSRV` for the VM family.
- Human-readable JSON remains inspection/compiler output, not canonical state or program source.
