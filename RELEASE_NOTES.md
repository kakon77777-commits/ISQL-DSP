# ISQL-DSR Runtime v0.5.0 Release Notes

## Theme: Native Execution Semantics

v0.5 moves execution below the inspection layer. Canonical stream replay now mutates registered numeric state directly.

### Added

- `NativeSemanticState.negative_relations`.
- `deny_relation` opcode 12.
- `retract_relation` opcode 13.
- Direct `apply_native_event()` executor.
- Native topology basis and graph operators.
- Native weighted fusion without `SemanticState` materialization.
- Positive/negative relation voting in fusion.
- `.isqlb` branch artifact.
- Deterministic numeric three-way branch merge.
- Machine conflict codes.
- `BRANCH_ID` registry namespace.
- CLI `branch-pack` and `branch-merge`.

### Changed

- Registered state format is v5.
- Event stream format is v5.
- Topology basis hash is length-framed symbol-byte based rather than JSON based.
- Built-in topology descriptors no longer carry human-readable `graph_mode` parameters in canonical state.
- Inspection event schema advances to v0.5.

### Invariant

Canonical replay does not require a human-readable intermediate representation.

### Compatibility

The existing Core R4 transport envelope is retained for interoperability with the supplied ISQL Core v0.4 parser. R4 is the Core transport resolution and is not the DSR release number.
