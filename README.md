# ISQL Dynamic Spectrum Runtime v0.2.0

ISQL-DSR is the internal dynamic-semantic runtime line of ISQL. It is intentionally separate from the public/transport-oriented ISQL Core Runtime.

v0.2 makes the **Topology** part of the historical Symbol–Topology–Flow design operational and adds deterministic, uncertainty-aware multi-source semantic fusion.

## What v0.2 adds

- `SemanticState` schema `isql.dsr-state/v0.2`
- finite-active spectral axes: point / interval / candidate-set
- typed relation graph
- typed topology descriptors bound to a canonical relation-basis SHA-256
- built-in topology methods:
  - `graph.components`
  - `graph.cycle_rank`
- relation changes automatically invalidate topology descriptors
- validation rejects stale topology descriptors even without replay history
- `SemanticProposal` with source weight, base revision, and base state hash
- deterministic uncertainty-aware proposal fusion
- explicit fusion conflicts instead of silent winner selection on ties / weak support
- fusion is a replayable history event
- `SEM/R2` semantic snapshot bridge
- `STATE/R2` exact state bridge
- Core v0.4-compatible digits-only wires using fixed-width decimal UTF-8 byte encoding
- CLI commands: `topology`, `fuse`, and multi-domain `bridge`

## Core invariant

Registry IDs and transport codes are references. They are **not** meaning.

DSR keeps the semantic object explicit. Core bridging happens only after a DSR state or semantic snapshot has been canonicalized.

## Install

```bash
python -m pip install dist/isql_dsr_runtime-0.2.0-py3-none-any.whl
```

Or run from source:

```bash
PYTHONPATH=src python -m isql_dsr --help
```

## CLI

Create a state:

```bash
isql-dsr new --identity demo:alpha --context-json '{"task":"deployment-review"}'
```

Validate:

```bash
isql-dsr validate --state examples/v0.2/final_state.json --genesis examples/v0.2/genesis.json
```

Compute topology directly:

```bash
isql-dsr topology --state examples/v0.2/pre_fusion_state.json
```

Fuse proposals atomically:

```bash
isql-dsr fuse \
  --state examples/v0.2/pre_fusion_state.json \
  --proposals examples/v0.2/proposals.json \
  --event-id evt-demo-fusion
```

Export Core-compatible numeric envelopes:

```bash
isql-dsr bridge --state examples/v0.2/final_state.json --domain sem
isql-dsr bridge --state examples/v0.2/final_state.json --domain state
isql-dsr bridge --state examples/v0.2/final_state.json --domain bundle
```

## Topology semantics

Every `TopologyDescriptor` contains a `basis_hash`. For v0.2, the basis is the canonical sorted typed-relation graph. If relations change, old descriptors are removed by the runtime. If an externally edited file tries to retain a descriptor with the wrong basis hash, validation fails.

The built-in `graph.components` and `graph.cycle_rank` methods use a weak undirected projection of typed relations. They are deliberately simple first descriptors, not a claim that these two numbers exhaust semantic topology.

## Fusion semantics

Every proposal is fail-closed against:

- `identity`
- `base_revision`
- `base_hash`

For an axis proposal, effective support is:

```text
source_weight * (1 - axis_uncertainty)
```

Winner support is divided by total source weight. If the best variants tie, or support is below the configured threshold, DSR keeps the base axis and records a conflict. Accepted relations use weighted support over the full proposal set.

The algorithm is `weighted-agreement/v0.2` and sorts proposals before aggregation, so input ordering cannot change a valid result.

## Core numeric wire

v0.2 encodes each UTF-8 byte of canonical JSON as exactly three decimal digits (`000`–`255`). Therefore a wire has the Core v0.4 shape:

```text
ISQL1:SEM:R2:DSR<digits>
ISQL1:STATE:R2:DSR<digits>
```

This is a **compatibility bridge**, not a compression claim. Its purpose is to prove that full DSR SEM/STATE payloads can cross the current Core digits-only grammar without losing semantic structure. A later compact numeric codec can replace this profile without changing the DSR object model.

## Schema compatibility

v0.2 deliberately bumps the DSR state/event schemas. Non-genesis v0.1 history chains should remain with the v0.1 runtime unless explicitly migrated and re-hashed. v0.1 is preserved as a separate immutable release.

## Files

- `src/isql_dsr/model.py` — semantic value/state models
- `src/isql_dsr/topology.py` — relation-basis hashing and topology computation
- `src/isql_dsr/fusion.py` — proposal and fusion contracts
- `src/isql_dsr/events.py` — fail-closed events
- `src/isql_dsr/runtime.py` — state transition application/replay
- `src/isql_dsr/bridge.py` — SEM/STATE numeric Core bridge
- `src/isql_dsr/validation.py` — integrity and replay validation
- `src/isql_dsr/diff.py` — semantic/topology state diff
- `src/isql_dsr/cli.py` — command line application
- `docs/` — theory anchors and implementation plan
- `examples/v0.2/` — deterministic end-to-end fixtures
- `tests/` — source/install test suite
