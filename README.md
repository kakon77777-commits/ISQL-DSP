# ISQL Dynamic Spectrum Runtime v0.4.0

**Registered AI-native internal runtime. Human readability is projection-only.**

v0.4 splits the canonical machine layer into three artifacts:

```text
symbols.isqlr   append-only shared symbol space
state.isqln     registered materialized snapshot
events.isqle    registered replayable event stream
```

## Canonical authority

```text
Inspection / human source
        |
        v
Registry compiler ------------------------------+
        |                                        |
        v                                        v
  .isqlr shared symbols <---- refs ---- registered .isqln
        ^                                        ^
        |                                        |
        +------------- refs ---- .isqle --------+
```

The v0.4 canonical state does **not** repeatedly serialize identity strings, axis keys, axis domains, relation atoms/predicates, topology method names, projection IDs, event IDs, source IDs, or proposal IDs. Those values live once in the shared registry and are referenced by positive integer IDs.

JSON, Markdown, natural language and visualization remain optional inspection or import projections.

## What v0.4 adds

- append-only `.isqlr` machine symbol registry;
- namespaced numeric symbol references;
- stable registry revision and prefix hash;
- registry-bound v0.4 `.isqln` snapshots;
- snapshot hash over registered binary bytes;
- materialized snapshot no longer embeds history;
- independent `.isqle` native event stream;
- numeric operation opcodes in the stream;
- registered previous/next snapshot hash chain;
- deterministic native replay;
- Core R4 transport:
  - `SEM/R4:DSRR`
  - `STATE/R4:DSRR`
  - `EXEC/R4:DSRE`
- v0.3 self-contained binary format retained only as a migration/compatibility path.

## Why registry prefix hashes matter

A snapshot pins:

```text
registry_revision
registry_prefix_hash
```

A newer append-only registry may still decode an older snapshot if its prefix through the pinned revision is identical.

Therefore:

```text
old state + extended compatible registry -> valid
old state + rewritten registry prefix    -> fail closed
```

This allows a shared machine symbol universe to grow without invalidating every previous state.

## CLI: v0.4 machine path

Build a registry from a genesis state and events:

```bash
isql-dsr registry-build \
  --state examples/v0.4/genesis_inspection.json \
  --events examples/v0.4/events_inspection.json \
  --out symbols.isqlr
```

Compile registered snapshot:

```bash
isql-dsr registered-pack \
  --state examples/v0.4/genesis_inspection.json \
  --registry symbols.isqlr \
  --out genesis.isqln
```

Compile event stream:

```bash
isql-dsr stream-pack \
  --genesis examples/v0.4/genesis_inspection.json \
  --events examples/v0.4/events_inspection.json \
  --registry symbols.isqlr \
  --out history.isqle
```

Replay without embedding history into snapshots:

```bash
isql-dsr stream-replay \
  --genesis-native genesis.isqln \
  --stream history.isqle \
  --registry symbols.isqlr \
  --out final.isqln
```

Inspect only when needed:

```bash
isql-dsr registered-inspect --native final.isqln --registry symbols.isqlr
```

Core R4 state wire:

```bash
isql-dsr bridge-r4 --native final.isqln --registry symbols.isqlr --domain state
```

Core R4 execution wire:

```bash
isql-dsr bridge-r4 \
  --stream history.isqle \
  --genesis-native genesis.isqln \
  --registry symbols.isqlr \
  --domain exec
```

## AI-native rule

```text
Registry refs + Native Snapshot + Native Event Stream
                    |
                    +-> optional interpretation adapter
                              |
                              +-> optional human projection
```

An interpretation adapter may temporarily resolve symbols when a high-level algorithm needs them. That does not make the resolved human-readable representation canonical.

## Compatibility layers

- v0.4 canonical path: `.isqlr + registered .isqln + .isqle`.
- v0.3 compatibility path: self-contained `.isqln`, `R3/DSRN`.
- v0.2 compatibility path: inspection JSON, `R2/DSR`.

Never silently relabel one representation as another. Migrate by decode/replay/recompile.

See `docs/NATIVE_FORMAT_v0.4.md` and `AI_HANDOFF.md`.
