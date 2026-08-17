# ISQL-DSR Native Format v0.3

This document is an **inspection specification**. It describes the canonical binary format; the document itself is not canonical state.

## Design rule

Canonical state bytes contain a fixed structural layout rather than JSON field names. Human-readable schemas are reconstructed only by the inspection layer.

## Header

```text
4 bytes   magic: D5 51 A9 03
uvarint   native format version = 3
text      identity
uvarint   revision
blob      typed context value
```

`text` is `uvarint byte_length + UTF-8 data`. UTF-8 is used only for actual textual data/identifiers, not for field labels.

`blob` is `uvarint byte_length + bytes`.

## Primitive type tags

```text
0  null
1  false
2  true
3  signed integer (zig-zag + uvarint)
4  IEEE-754 float64, big-endian, finite only
5  UTF-8 text
6  list
7  canonical map
```

Map entries are sorted by raw UTF-8 key bytes. Maps are used for open semantic payloads such as context/projection data; fixed runtime schemas use fixed layouts instead.

## State sections

After the header, sections occur in fixed order and therefore do not need textual field names:

```text
axes_count
  axis*
relations_count
  relation*
topology_count
  descriptor*
projections_count
  projection*
history_count
  history_record*
```

### Axis

```text
text       key
text       domain
blob       semantic value
float64    uncertainty
uvarint    resolution
```

Semantic-value tags:

```text
0 point
1 interval
2 candidate set
```

### Relation

```text
text subject
text predicate
text object
```

### Topology descriptor

```text
text       descriptor_id
text       method
32 bytes   relation-basis SHA-256
blob       typed value
float64    confidence
blob       typed parameters
```

### Projection

```text
text projection_id
text media_type
blob typed payload
```

Projection payload can contain human language because it is semantic/projection data, not native schema metadata.

## Event opcodes

```text
1  set_context
2  upsert_axis
3  remove_axis
4  upsert_relation
5  remove_relation
6  upsert_projection
7  remove_projection
8  refresh_topology
9  upsert_topology_descriptor
10 remove_topology_descriptor
11 fuse_proposals
```

The operation string is reconstructed by the inspection/runtime API and is not serialized into native history.

## Fusion

Fusion proposals and fusion decisions have dedicated fixed layouts. Canonical bytes do not embed JSON keys such as `proposal_id`, `source_weight`, `axis_threshold`, `effective_support`, or `support_ratio`.

The weighted-agreement decision rule remains algorithm version `v0.2`; native serialization is format version `v0.3`.

## Canonical hash

```text
state_hash = SHA256(native_state_bytes)
```

JSON formatting, key order, whitespace and Markdown rendering have no authority over this hash.

## Core native transport

Native bytes are represented as three decimal digits per byte for compatibility with the current Core digits-only parser:

```text
ISQL1:SEM:R3:DSRN<decimal bytes>
ISQL1:STATE:R3:DSRN<decimal bytes>
```

This decimal representation is transport encoding, not the canonical in-memory representation. The canonical payload is the decoded native byte sequence.
