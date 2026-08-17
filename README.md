# ISQL Dynamic Spectrum Runtime v0.1.0

This is the **parallel internal runtime** for the dynamic-spectrum branch of ISQL. It does not replace ISQL Core Runtime v0.4 and does not reduce semantic meaning to registry integer IDs.

## What v0.1 implements

- Stable semantic-object identity separated from mutable representation.
- Finite-active spectrum axes with point, interval, and candidate-set values.
- Per-axis uncertainty and resolution.
- Typed relations.
- Multiple semantic projections.
- Context as first-class state.
- Fail-closed transition events using base revision plus previous state hash.
- Deterministic replay and semantic diff.
- Canonical UTF-8 JSON serialization and SHA-256 state hashes.
- Lossless `STATE/R2` envelope for transport toward ISQL Core without lossy remapping.

## What v0.1 deliberately does not claim

- Registry IDs are not meaning.
- No universal 12-dimensional ontology is assumed.
- No universal `0.78` fidelity constant is assumed.
- No claim that every semantic state has a unique fixed point.
- No claim that a finite symbol physically stores arbitrary infinite information.
- No LLM is required by the runtime.

## Install from source

```bash
python -m pip install .
```

Or run without installation:

```bash
PYTHONPATH=src python -m isql_dsr --help
```

## CLI

Create a genesis state:

```bash
isql-dsr new --identity isql:demo:alpha --context-json '{"language":"zh-Hant"}'
```

Compute canonical state hash:

```bash
isql-dsr hash --state examples/genesis.json
```

Apply one transition:

```bash
isql-dsr apply --state examples/genesis.json --event examples/event_upsert_axis.json
```

Replay an event array:

```bash
isql-dsr replay --genesis examples/genesis.json --events examples/events.json
```

Validate history by replay:

```bash
isql-dsr validate --state examples/final_state.json --genesis examples/genesis.json
```

Export a Core transport envelope:

```bash
isql-dsr bridge --state examples/final_state.json
```

## Core / DSR split

```text
ISQL Core v0.4
  identity / registry / codec / wire / recovery

ISQL DSR v0.1
  spectrum / relation / context / state / transition / projection
```

The bridge in this release is intentionally lossless. It transports canonical DSR state as a versioned `STATE/R2` envelope; it does not pretend the current Core spectral dictionary is the complete DSR semantic space.
