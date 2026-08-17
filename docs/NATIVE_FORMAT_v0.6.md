# ISQL-DSR Native Format v0.6

## Artifact family

- `.isqlr` — shared append-only symbol registry.
- `.isqln` — registered materialized state.
- `.isqle` — native event stream.
- `.isqlb` — native branch artifact.
- `.isqlp` — causal native program.

Human-readable inspection projections are outside canonical authority.

## Program magic and version

Program bytes begin with four magic bytes:

`D5 51 E1 06`

followed by canonical unsigned varint format version `6`.

## Program layout

Fields appear in fixed order:

1. magic
2. format version
3. registry revision
4. 32-byte registry prefix hash
5. program ref
6. base revision
7. 32-byte base registered-state hash
8. instruction count
9. length-framed instruction records

No human field names are encoded.

## Instruction layout

Each instruction contains:

1. instruction ref
2. numeric opcode
3. numeric effect mask
4. dependency count
5. sorted dependency instruction refs
6. length-framed native payload

Program instructions are canonicalized by instruction ref. Dependency lists are sorted and unique.

## Effect masks

- bit 0: context
- bit 1: axis
- bit 2: relation
- bit 3: projection
- bit 4: topology

The mask is derived from opcode and is not advisory metadata. A mismatched mask is invalid.

Relation operators include topology effect because relation changes invalidate relation-basis topology descriptors. Fusion includes axis + relation + topology effects.

## Causal execution

The instruction graph must be a DAG. Execution uses deterministic topological ordering; when multiple instructions are ready, lower numeric instruction ref executes first.

The program is anchored to base revision and base registered-state hash.

## Atomic publication

Program execution may construct immutable intermediate working states. A successful execution publishes the final state. If an instruction fails, the returned state is the original base state.

The inspection receipt contains:

- numeric status
- program ref
- base/final hashes
- successful execution order
- failed instruction ref
- optional human-readable debug error code

The receipt is not canonical state.

## Branch format v6

Branch magic advances to:

`D5 51 B7 06`

After branch ref, the artifact stores a dependency count and sorted numeric branch refs before base revision/hash and the embedded native event stream.

Dependencies form a DAG over the branch set supplied to merge.

## Causal merge rule

For a changed field, consider only causally maximal changed branches. Ancestor values are superseded by descendants. If multiple incomparable maximal branches disagree, emit an explicit conflict and retain base semantics for that field.

## Core transport

Program transport is:

`ISQL1:EXEC:R4:DSRP<decimal-digits>`

Payload digits are the decimal transport encoding of raw `.isqlp` bytes.

`R4` is constrained by the supplied Core v0.4 parser grammar. `DSRP` distinguishes program bytes from `DSRE` event-stream bytes.
