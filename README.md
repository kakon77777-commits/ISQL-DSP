# ISQL-DSR Runtime v1.0.0

**AI-native dynamic spectral semantic runtime and computation architecture.**

v1.0 is the first release in this parallel internal line designated as a stable computation-architecture milestone. It preserves the canonical machine-first rule established in v0.3:

$$
\text{Machine Canonical First},
\qquad
\text{Human Projection Optional}.
$$

The canonical artifacts are still binary/native:

- `.isqlr` — shared append-only machine symbol registry;
- `.isqln` — registered materialized native state;
- `.isqle` — replayable native event stream;
- `.isqlb` — causal native branch;
- `.isqlp` — canonical native program / VM module.

JSON, Markdown, natural language, and diagrams are inspection or projection layers. They are not the canonical state/program source.

## v1.0 computation milestone

v1.0 adds five capabilities on top of v0.9 without introducing a program counter or arbitrary backward jump:

1. **Typed composite machine values** — `VectorValue` and numeric-field `RecordValue`.
2. **Register-local immutable containers** — vector pack/get/len and record pack/get/set.
3. **Native function signatures** — numeric argument/return type contracts encoded in `.isqlp` format version 10.
4. **Bounded iteration** — `REPEAT_CALL`, with a hard protocol cap `VM_MAX_REPEAT = 1024`.
5. **Semantics-preserving static optimizer** — conservative constant folding and dead unconditional-constant elimination.

The VM remains a causal DAG machine. Bounded repetition is represented as a finite synchronous subprogram operation, not as an unrestricted backward jump.

## Typed function boundary

A native program exposes a function signature:

$$
\Sigma(P)
=
(A_1:\tau_1,\ldots,A_m:\tau_m)
\rightarrow
(R_1:\rho_1,\ldots,R_n:\rho_n).
$$

Supported top-level machine type tags in v1.0 include `ANY`, `NULL`, `BOOL`, `INT`, `FLOAT`, `TEXT`, `INTERVAL`, `CANDIDATES`, `VECTOR`, and `RECORD`.

Type failure aborts the entire transaction. CALL arguments and callee returns are checked at the native boundary.

## Bounded iteration

`REPEAT_CALL` executes a subprogram a finite number of times inside one atomic transaction:

$$
S_0
\xrightarrow{P_c}
S_1
\xrightarrow{P_c}
\cdots
\xrightarrow{P_c}
S_k,
\qquad
1\le k\le1024.
$$

If iteration $j$ fails, the published state is still the original transaction base:

$$
S_{\mathrm{published}}=S_0.
$$

Unbounded recursion and arbitrary call cycles remain rejected.

## Optimizer

`optimize_vm_program()` is intentionally conservative. v1.0 folds scalar register operations only when all operands are statically known and only removes dead unconditional `CONST` instructions. It does not remove operations whose failure/guard behavior might be observable.

CLI:

```bash
isql-dsr vm-optimize \
  --registry symbols.isqlr \
  --program source.isqlp \
  --out optimized.isqlp
```

## Examples

`examples/v1.0/` contains:

- `composite.isqlp` — typed vector/record construction;
- `repeat-child.isqlp` and `repeat-root.isqlp` — four-step bounded native iteration;
- `repeat-final.isqln` — resulting state with counter value 4;
- `optimizer-source.isqlp` and `optimizer-optimized.isqlp` — equivalent programs reduced from three instructions to one;
- `symbols.isqlr` and `genesis.isqln`.

See `examples/v1.0/summary.json` for measured artifact sizes and leak checks.

## Test

Source tree:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Installed wheel tests must run without source-tree `PYTHONPATH`.

## Core compatibility

DSR VM programs continue to use the existing Core transport contract:

```text
ISQL1:EXEC:R4:DSRV:<digits-only-payload>
```

`R4` is the ISQL Core transport resolution. `DSRV` identifies the DSR VM payload family; it is not the DSR semantic/runtime version number.

## Historical continuity

The package includes the ISQL Canonical Anchor and implementability paper in `docs/`. The public/useful ISQL Core line and this internal AI-native DSR line remain deliberately parallel.
