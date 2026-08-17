# ISQL-DSR Native Format v0.5

## Status

This document defines the canonical machine artifacts introduced or changed by ISQL-DSR Runtime v0.5. Human-readable JSON is an inspection/import projection only.

## Canonical artifacts

- `.isqlr` — append-only shared symbol registry.
- `.isqln` — registered materialized native state.
- `.isqle` — replayable native event stream.
- `.isqlb` — forked branch artifact containing branch identity plus one native event stream.

The canonical authority is the bytes of these artifacts, not JSON field names.

## Registered state v5

Magic:

`D5 51 C1 05`

Format version: `5`.

Ordered fields:

1. registry revision;
2. registry prefix hash;
3. identity ref;
4. state revision;
5. context ref/value pairs;
6. active axes;
7. positive relation triples;
8. negative relation triples;
9. topology descriptors;
10. projections.

Positive and negative relation sets are disjoint. A canonical state that contains the same relation triple in both sets is invalid.

For relation $r$ the machine state therefore has three possible epistemic statuses:

$$
\operatorname{status}(r)\in\{-1,0,+1\},
$$

where $+1$ is asserted, $-1$ is denied, and $0$ is currently unasserted/unknown.

## Event stream v5

Magic:

`D5 51 E1 05`

Format version: `5`.

The stream retains registry pin, genesis state hash, numeric event refs, numeric opcodes, native payloads and previous/next state hashes.

New v0.5 opcodes:

- `12` — deny relation;
- `13` — retract relation.

`deny_relation` moves a relation to the negative assertion set and removes the positive assertion if present.

`retract_relation` removes both positive and negative assertions. It is idempotent at the semantic level.

## Native executor

`apply_native_event()` operates directly on `NativeSemanticState`. Canonical replay does not require:

- `SemanticState` materialization;
- JSON inspection projection;
- human operation labels;
- `runtime.apply_event()`.

Topology refresh and weighted proposal fusion have native numeric implementations.

## Topology basis v5

Topology basis hashing is no longer JSON-dependent. It uses ordered length-framed symbol bytes from the registry:

$$
H_G
=
\operatorname{SHA256}
\left(
\operatorname{frame}(s_1,p_1,o_1)\Vert\cdots\Vert
\operatorname{frame}(s_n,p_n,o_n)
\right).
$$

This allows the native executor to reproduce the basis hash directly from machine refs plus the pinned registry, without constructing human-readable graph objects.

Negative relations do not count as active graph edges.

## Native fusion v5

Proposal axes and relation assertions are compiled into numeric refs before execution. Proposals may contain both positive and negative relation votes, but may not assert and deny the same relation internally.

For a relation $r$, native fusion computes positive and negative support separately. If both polarities cross the configured threshold, the base status is retained and a polarity conflict is emitted by the inspection-layer decision record.

## Branch artifact v5

Magic:

`D5 51 B7 05`

Fields:

1. format version;
2. branch ref from registry namespace `BRANCH_ID`;
3. base revision;
4. base registered-state hash;
5. embedded canonical `.isqle` stream.

A branch is valid only if its stream genesis hash equals its declared base hash.

## Native three-way branch merge

`merge_native_branches(base, branches, registry)` materializes each branch by native replay and compares numeric state components against the common base.

Conflict classes:

- `1` — axis conflict;
- `2` — relation-polarity conflict;
- `3` — context conflict;
- `4` — projection conflict.

Conflicts are explicit numeric machine objects. The merge never silently chooses one conflicting branch by input ordering.

Topology is invalidated whenever merged relation polarity changes the active positive graph.

## Registry addition

Namespace `14` is `BRANCH_ID`.

Registry cost remains side information and must be included in any compression accounting.

## Core compatibility

The existing external ISQL Core v0.4 parser currently exposes transport resolutions through `R4`. ISQL-DSR v0.5 therefore continues to use the established R4 bridge for registered state and execution transport when communicating with that parser.

`R4` in that envelope is a Core transport resolution, not the DSR package version.
