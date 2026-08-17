# ISQL Dynamic Spectrum Runtime v0.3.0

**AI-native parallel internal runtime.** This branch does not optimize the canonical state for human readability.

## Canonical authority

v0.3 changes the source of truth:

```text
v0.1-v0.2 development model:
SemanticState -> canonical JSON -> SHA-256

v0.3 AI-native model:
SemanticState -> typed native bytes (.isqln) -> SHA-256
                         |
                         +-> optional inspection JSON
```

The canonical artifact is a deterministic, typed, versioned binary state. JSON, Markdown, natural language, graphs, and future EML renderings are projections or inspection formats.

Human-readable field names are not serialized as native schema labels. Known transition operations use numeric opcodes. Fusion proposals and fusion decisions use fixed numeric layouts rather than embedding their JSON field names in the canonical byte stream.

## What v0.3 implements

- All v0.2 finite-active spectrum, topology, uncertainty-aware fusion, replay and validation behavior.
- AI-native binary state format `NATIVE_FORMAT_VERSION = 3`.
- Canonical hash over native bytes, not JSON.
- Canonical map ordering and typed primitive codec.
- Numeric transition opcodes.
- Numeric-layout fusion proposal and decision history.
- `.isqln` canonical state artifacts.
- Optional inspection JSON projection.
- Legacy JSON `R2/DSR` bridge retained for compatibility.
- Native Core bridge:
  - `SEM/R3:DSRN`
  - `STATE/R3:DSRN`
- Digits-only Core transport of native bytes.

## CLI

Compile inspection JSON into canonical native state:

```bash
isql-dsr native-pack \
  --state examples/v0.3/final_inspection.json \
  --out state.isqln
```

Inspect native state when a human-readable/debug view is needed:

```bash
isql-dsr native-inspect --native state.isqln
```

Hash the canonical native state:

```bash
isql-dsr native-hash --native state.isqln
```

Bridge native state directly to Core:

```bash
isql-dsr bridge --native state.isqln --domain bundle
```

The older JSON inspection route is still available:

```bash
isql-dsr bridge --state final_inspection.json --domain state
```

That route is explicitly legacy `R2/DSR`, not the v0.3 canonical transport.

## AI-native rule

The design rule is:

```text
Native State -> Native Operations -> Native State
      |
      +-> Interpretation Projection (optional)
              |
              +-> Human Projection (optional)
```

“AI-native” does not mean deliberately obscure. It means the lowest layer is selected for deterministic machine composition, typing, versioning and verification rather than human readability.

## Core / DSR split

```text
ISQL Core v0.4
  address / registry / parser / transport / recovery

ISQL DSR v0.3
  native state / spectrum / topology / flow / fusion / replay
```

## Important migration boundary

v0.2 history chains were hashed from the v0.2 canonical JSON representation. v0.3 history chains are hashed from native bytes. Therefore a non-genesis v0.2 state must not be silently relabeled as v0.3 history.

History-free/genesis inspection states can be compiled with `native-pack`. Historical v0.2 chains should be migrated by replaying the source events under v0.3 so that all previous/next hashes are regenerated from native state bytes.

See `docs/NATIVE_FORMAT_v0.3.md` and `AI_HANDOFF.md`.
