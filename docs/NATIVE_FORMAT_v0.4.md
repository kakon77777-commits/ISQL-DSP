# ISQL-DSR Native Format v0.4

## 1. Artifact model

v0.4 has three independent canonical binary artifact families.

```text
ISQLR: registry
ISQLN: registered snapshot
ISQLE: registered event stream
```

All integer fields use canonical unsigned varints unless otherwise stated. Hashes are raw 32-byte SHA-256 values in the binary representation.

## 2. `.isqlr` registry

Magic:

```text
D5 51 B1 04
```

Logical layout:

```text
magic
format_version = 4
entry_count
repeat entry_count:
    namespace_id
    payload_length
    payload_bytes
```

Symbol IDs are implicit, positive and one-based:

```text
symbol_id = entry_position + 1
```

The registry is append-only. A binding at an existing ID MUST NOT be rewritten.

The prefix hash at revision `r` is:

```text
SHA256(canonical encoding of entries [1..r])
```

This lets an artifact pinned to revision `r` be decoded by a newer registry only if that prefix is unchanged.

## 3. Namespaces

Protocol namespace codes in v0.4:

```text
1  IDENTITY
2  AXIS_KEY
3  AXIS_DOMAIN
4  ATOM
5  PREDICATE
6  TOPOLOGY_DESCRIPTOR
7  TOPOLOGY_METHOD
8  PROJECTION_ID
9  MEDIA_TYPE
10 EVENT_ID
11 SOURCE_ID
12 PROPOSAL_ID
13 CONTEXT_KEY
```

A numeric ID is valid only in the namespace expected by its field.

## 4. Registered `.isqln` snapshot

Magic:

```text
D5 51 C1 04
```

Header:

```text
format_version = 4
registry_revision
registry_prefix_hash[32]
identity_ref
state_revision
```

Body:

```text
context_count
    context_key_ref + typed_value
axis_count
    axis_key_ref + axis_domain_ref + semantic_value + uncertainty_f64 + resolution
relation_count
    subject_ref + predicate_ref + object_ref
topology_count
    descriptor_ref + method_ref + basis_hash[32] + value + confidence_f64 + parameters
projection_count
    projection_ref + media_type_ref + payload
```

There is intentionally **no history section** in the v0.4 registered snapshot.

Snapshot hash:

```text
SHA256(exact canonical registered .isqln bytes)
```

## 5. `.isqle` event stream

Magic:

```text
D5 51 E1 04
```

Header:

```text
format_version = 4
registry_revision
registry_prefix_hash[32]
genesis_registered_state_hash[32]
record_count
```

Each record:

```text
native_event_length
native_event_bytes
expected_next_registered_state_hash[32]
```

Native event:

```text
event_id_ref
operation_opcode
operation_payload_length
operation_payload_bytes
base_revision
previous_registered_state_hash[32]
has_timestamp
[timestamp_bytes]
```

Operation payloads use fixed layouts and registry refs; operation/schema field-name strings are not serialized.

Replay requires every record to satisfy:

```text
current_revision == event.base_revision
SHA256(current_registered_snapshot) == event.previous_hash
SHA256(replayed_next_snapshot) == record.next_hash
```

Any mismatch fails closed.

## 6. Human/inspection projection

Registry payloads can be resolved into inspection strings when required. That projection may be used by high-level semantic algorithms, debugging tools or human UIs.

It is not canonical authority.

## 7. Core R4 bridge

Registered snapshot transport:

```text
ISQL1:SEM:R4:DSRR<decimal bytes>
ISQL1:STATE:R4:DSRR<decimal bytes>
```

Native event stream transport:

```text
ISQL1:EXEC:R4:DSRE<decimal bytes>
```

The decimal transformation is transport encoding only. The underlying canonical objects remain the binary `.isqln` / `.isqle` payloads.

## 8. Side-information accounting

Any compression or density report MUST account for the registry separately:

```text
L_total = L(snapshot/event stream) + allocated share of L(registry) + required decoder/protocol cost
```

A small registered state does not imply that the registry is free.
