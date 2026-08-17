# ISQL Dynamic Spectrum Runtime v0.4.0 — Release Notes

## Registered machine-space transition

v0.4 moves repeated semantic identifiers out of individual snapshots/events and into a shared append-only machine symbol space.

### Added

- `.isqlr` append-only namespaced symbol registry.
- Stable positive integer symbol references.
- Registry revision and prefix-hash verification.
- Registered v0.4 `.isqln` snapshot format.
- Snapshot canonical hash over registry-bound native bytes.
- `.isqle` canonical native event-stream format.
- Event-stream previous/next registered snapshot hash chain.
- Deterministic stream replay.
- Registry-aware CLI commands:
  - `registry-build`
  - `registered-pack`
  - `registered-inspect`
  - `registered-hash`
  - `stream-pack`
  - `stream-replay`
  - `bridge-r4`
- Core R4 transport:
  - `SEM/R4:DSRR`
  - `STATE/R4:DSRR`
  - `EXEC/R4:DSRE`
- `docs/NATIVE_FORMAT_v0.4.md`.

### Changed

- Transition history is no longer canonicalized inside v0.4 materialized snapshots.
- Repeated semantic identifiers are encoded as registry refs rather than duplicated UTF-8 strings in each artifact.
- The shared registry becomes explicit side information and its cost can be accounted for independently.
- v0.3 `.isqln` remains supported as a compatibility artifact but is not the v0.4 canonical form.

### Preserved

- finite-active spectra;
- typed relations;
- topology descriptors;
- uncertainty-aware fusion;
- fail-closed event semantics;
- v0.3 and v0.2 compatibility bridges.

### Explicit non-claims

- v0.4 does not claim a universal semantic vocabulary.
- integer symbol IDs are not meanings.
- registry lookup is not claimed to solve synonymy/polysemy by itself.
- the current interpretation adapter is not claimed to be final machine-native execution.
- registry size and synchronization cost must be included in any compression claim.
