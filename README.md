# ISQL-DSR Runtime v0.7.0

ISQL Dynamic Spectrum Runtime v0.7 extends the AI-native execution layer into a small guarded, capability-aware VM. Human-readable JSON remains an inspection/compiler boundary only.

## Canonical artifact family

- `.isqlr` — append-only shared machine symbol registry.
- `.isqln` — registered materialized native semantic state.
- `.isqle` — hash-chained native transition stream.
- `.isqlb` — causal branch artifact.
- `.isqlp` — native program artifact. v0.6 causal programs remain valid; v0.7 adds a VM program codec with state-slot bindings, guards, capabilities and CALL/RETURN.

## What v0.7 adds

1. **Numeric guards** evaluated directly on registered machine state.
2. **Capability/effect permission gates** before mutation.
3. **Synchronous native CALL/RETURN** with recursion-cycle rejection.
4. **Multi-state atomic transactions**: every bound state commits together or all states roll back.
5. **Exact and dynamic state-slot bindings**.
6. **Per-state transaction receipts** with base/final hashes and numeric call trace.
7. **Core `EXEC/R4/DSRV` transport** for v0.7 VM programs.

## Atomicity

For transaction state-set $S=(S_1,\ldots,S_n)$ and program $P$:

$$
\operatorname{Exec}(P,S)=S'
$$

is published only when all guards, capability checks, instructions and subprogram calls succeed. On any failure:

$$
\operatorname{PublishedStateSet}=S.
$$

No partially mutated state slot is published.

## Capability model

Capabilities are numeric bit masks. An instruction's required capability is canonical and derived from its machine effect. CALL additionally requires the VM call capability. A program may not declare fewer or extra direct capabilities than its instructions require.

## CLI

Execute a v0.7 program over one or more registered state slots:

```bash
isql-dsr vm-run --registry symbols.isqlr --program root.isqlp \
  --state 12=state-a.isqln --state 13=state-b.isqln \
  --callee child.isqlp --out-dir result
```

Export the program as a Core-compatible machine wire:

```bash
isql-dsr vm-bridge --registry symbols.isqlr --program root.isqlp \
  --state 12=state-a.isqln --state 13=state-b.isqln
```

The transport control is `EXEC/R4/DSRV`. `R4` is Core v0.4 transport compatibility, not the DSR version number.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

See `docs/NATIVE_VM_v0.7.md` for the native VM contract.
