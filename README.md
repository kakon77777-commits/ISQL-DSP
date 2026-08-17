# ISQL-DSR Runtime v0.6.0

ISQL Dynamic Spectrum Runtime v0.6 is an **AI-native causal execution runtime**. Human-readable JSON is not canonical storage and is not required by the execution core.

## Canonical authority

The machine path is:

`.isqlr -> .isqln + .isqle + .isqlp + .isqlb -> native execution / merge`

- `.isqlr`: append-only shared machine symbol space.
- `.isqln`: registry-bound materialized machine state.
- `.isqle`: hash-chained native event stream.
- `.isqlb`: native branch/fork artifact with causal branch dependencies.
- `.isqlp`: causal native program containing numeric instruction refs, opcodes, effect masks, dependency refs, and native payloads.

JSON, Markdown, natural-language explanations and execution receipts are inspection projections. They are not canonical state authority.

## What v0.6 adds

- Canonical `.isqlp` program artifacts.
- Numeric program/instruction registry namespaces.
- Operator effect masks.
- Instruction dependency DAGs.
- Deterministic topological execution.
- Atomic program execution with functional rollback.
- Program execution receipts as non-canonical inspection output.
- Branch-to-branch causal dependency metadata.
- Causal merge precedence: a causally later branch can supersede an ancestor without being misclassified as concurrent conflict.
- `EXEC/R4/DSRP` Core transport for native programs.
- CLI `program-pack`, `program-run`, `program-bridge`.

## Atomic execution

A program is anchored to one base snapshot by revision and registered-state hash. Instructions execute on an internal immutable working state. If any instruction fails, the externally returned state is the original base state.

A successful program returns the committed final machine state. A failed program returns a receipt naming the failed instruction ref and an inspection error code, while the canonical base state remains unchanged.

## Causal programs

Each instruction declares numeric dependencies. Execution order is a deterministic topological order with instruction-ref tie breaking. Cycles, unknown dependencies, duplicate refs and incorrect effect masks fail closed.

## Core compatibility

The supplied ISQL Core v0.4 parser accepts transport resolutions `R0-R4`. Therefore program transport uses:

`ISQL1:EXEC:R4:DSRP<digits>`

`R4` is the Core transport resolution, not the DSR release number. `DSRP` identifies the program payload. Existing native event streams remain `EXEC/R4/DSRE`.

## CLI examples

Build a registry with program/instruction refs:

```bash
isql-dsr registry-build --state genesis.json --events events.json \
  --program-id deploy-program \
  --instruction-id deploy-1 --instruction-id deploy-2 \
  --out symbols.isqlr
```

Compile state and stream:

```bash
isql-dsr registered-pack --state genesis.json --registry symbols.isqlr --out genesis.isqln
isql-dsr stream-pack --genesis genesis.json --events events.json \
  --registry symbols.isqlr --out history.isqle
```

Compile a causal program:

```bash
isql-dsr program-pack --registry symbols.isqlr \
  --genesis-native genesis.isqln --stream history.isqle \
  --program-id deploy-program \
  --instruction-id deploy-1 --instruction-id deploy-2 \
  --out deploy.isqlp
```

Execute atomically:

```bash
isql-dsr program-run --registry symbols.isqlr \
  --genesis-native genesis.isqln --program deploy.isqlp \
  --out final.isqln
```

Export Core wire:

```bash
isql-dsr program-bridge --registry symbols.isqlr \
  --genesis-native genesis.isqln --program deploy.isqlp
```

Causal branch:

```bash
isql-dsr branch-pack --branch-id review --depends-on research \
  --genesis genesis.json --events review.json \
  --registry symbols.isqlr --out review.isqlb
```

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

See `docs/NATIVE_FORMAT_v0.6.md` for the byte-level program and causal branch contract.
