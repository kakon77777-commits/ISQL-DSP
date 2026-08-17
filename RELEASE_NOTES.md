# ISQL-DSR Runtime v0.2.0 Release Notes

Date: 2026-08-17

## New

- Added typed `TopologyDescriptor` objects.
- Added canonical relation-basis hashing.
- Added `graph.components` and `graph.cycle_rank` topology methods.
- Relation mutations now invalidate prior topology descriptors.
- Validation now detects stale topology descriptors without requiring history replay.
- Added fail-closed `SemanticProposal` objects for multi-model / multi-agent semantic input.
- Added deterministic `weighted-agreement/v0.2` fusion.
- Added explicit axis conflict records for tied or insufficient support.
- Fusion is now a first-class replayable transition event.
- Added semantic-only `SEM/R2` snapshots.
- Upgraded `STATE/R2` bridge to digits-only Core-compatible wire.
- Added `SEM + STATE` bridge bundle.
- Added CLI `topology`, `fuse`, and `bridge --domain` commands.

## Important interpretation

The decimal wire is a compatibility transport, not a compression result. Meaning remains in the DSR semantic object; a Core code is a transport/reference representation.

## Breaking schema change

- state: `isql.dsr-state/v0.2`
- event: `isql.dsr-event/v0.2`

Existing v0.1 history chains are not silently re-hashed. Keep them with the v0.1 runtime until an explicit migration profile is introduced.
