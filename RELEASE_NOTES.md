# ISQL Dynamic Spectrum Runtime v0.3.0 — Release Notes

## AI-native canonical-state transition

v0.3 changes the canonical source of truth from human-readable JSON to a deterministic typed binary representation.

### Added

- `.isqln` canonical native state format.
- Primitive numeric type tags and canonical variable-length integers.
- Fixed-layout native encoding for spectrum axes, relations, topology and projections.
- Numeric opcodes for transition operations.
- Fixed-layout fusion proposal and fusion-decision history.
- Native SHA-256 state hashing.
- `native-pack`, `native-inspect`, `native-hash` CLI commands.
- Core-native digits-only bridge using `SEM/R3:DSRN` and `STATE/R3:DSRN`.
- `docs/NATIVE_FORMAT_v0.3.md`.

### Changed

- JSON is now an inspection/import projection, not canonical storage.
- State and event schemas are v0.3.
- Proposal schema is v0.3; the weighted-agreement fusion algorithm remains algorithm version v0.2 because its decision rule did not change.
- v0.3 hash chains are intentionally incompatible with old v0.2 JSON-derived state hashes.

### Retained

- v0.2 topology descriptors.
- uncertainty-aware multi-source fusion.
- deterministic replay and validation.
- fail-closed revision/hash guards.
- legacy Core `R2/DSR` JSON bridge for compatibility.

### Not claimed

- Human unreadability is not itself a feature or proof of AI nativeness.
- Native bytes are not claimed to be optimal machine code.
- Raw semantic text values may still exist as semantic data.
- No universal semantic registry or universal HSO basis is claimed in v0.3.
