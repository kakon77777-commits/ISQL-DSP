# ISQL-DSR Runtime v0.5.0

ISQL Dynamic Spectrum Runtime v0.5 is an **AI-native machine-state runtime**. Human-readable JSON is not canonical storage.

## Canonical authority

The machine path is:

`.isqlr -> .isqln + .isqle -> .isqlb -> native merge/execution`

- `.isqlr`: append-only shared machine symbol space.
- `.isqln`: registry-bound materialized state.
- `.isqle`: hash-chained native execution stream.
- `.isqlb`: branch/fork artifact.

JSON, Markdown and natural-language explanations are optional inspection projections.

## What v0.5 adds

- Direct native executor: replay no longer translates machine state back to `SemanticState`.
- Positive / negative relation polarity.
- `deny_relation` and `retract_relation` native opcodes.
- Negative relation voting in multi-source fusion.
- Numeric topology computation directly over registered relations.
- `.isqlb` branch artifacts.
- Deterministic native three-way branch merge.
- Explicit machine conflicts for axis, relation polarity, context and projection collisions.
- Branch CLI commands.

## Relation semantics

A relation triple can be positive, negative, or unasserted. Positive and negative copies of the same triple may not coexist in one canonical state.

`deny_relation` sets negative polarity. `retract_relation` removes either polarity and returns the relation to unknown/unasserted state.

## CLI examples

Build a registry including branch IDs:

```bash
isql-dsr registry-build --state genesis.json --events events.json \
  --branch-id left --branch-id right --out symbols.isqlr
```

Pack a registered state:

```bash
isql-dsr registered-pack --state genesis.json --registry symbols.isqlr --out genesis.isqln
```

Pack branch streams:

```bash
isql-dsr branch-pack --branch-id left --genesis genesis.json --events left.json \
  --registry symbols.isqlr --out left.isqlb
```

Merge branches:

```bash
isql-dsr branch-merge --base-native genesis.isqln \
  --branch left.isqlb --branch right.isqlb \
  --registry symbols.isqlr --out merged.isqln
```

Inspect only when needed:

```bash
isql-dsr registered-inspect --native merged.isqln --registry symbols.isqlr
```

## Legacy layers

v0.1-v0.4 remain separate release artifacts. Legacy JSON, R2 and R3 commands are kept for migration/inspection compatibility but are not the v0.5 canonical authority.

The R4 Core envelope remains a transport-compatibility layer because the supplied Core v0.4 parser recognizes R0-R4. It does not mean this package is DSR v0.4.

## Tests

Run from source:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

See `docs/NATIVE_FORMAT_v0.5.md` for the byte-level contract.
