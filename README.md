# ISQL-DSR Runtime v0.8.0

ISQL Dynamic Spectrum Runtime v0.8 extends the AI-native VM with register dataflow, state-scoped capabilities, multi-slot CALL arguments/returns, and deterministic parallel scheduling. Human-readable JSON and Markdown remain inspection/compiler boundaries only; canonical execution artifacts remain binary machine representations.

## Canonical artifact family

- `.isqlr` — append-only shared machine symbol registry.
- `.isqln` — registered materialized native semantic state.
- `.isqle` — hash-chained native transition stream.
- `.isqlb` — causal branch artifact.
- `.isqlp` — native program artifact. v0.8 keeps this artifact family and upgrades the VM payload format rather than creating another persistent format.

## What v0.8 adds

1. **Numeric program arguments and return registers.** Programs declare exact argument/return register refs; undeclared, missing, or uninitialized values fail closed.
2. **State-scoped capability grants.** A global mask remains an upper bound, while each actual state slot receives an explicit numeric capability mask.
3. **Cross-state native dataflow.** `LOAD_AXIS` reads a semantic value from one state into a machine register; `STORE_AXIS` writes a register value into another state.
4. **Multi-slot CALL/RETURN.** A callee can bind multiple dynamic state slots, receive positional argument registers, and return positional register values into caller registers.
5. **Deterministic parallel scheduling.** Independent instructions are compiled into hazard-free batches. Parallel execution computes a batch concurrently but commits results in canonical instruction-ref order.
6. **Legacy v0.7 `.isqlp` decoding.** v0.7 VM programs remain readable; new v0.8 fields default to empty/inferred values when decoding legacy programs.
7. **Core `EXEC/R4/DSRV` transport remains stable.** `R4` is the Core transport resolution; `DSRV` identifies the DSR VM payload family.

## Register contract

For program $P$ with declared argument register set $A_P$ and return register set $R_P$, execution accepts exactly the declared argument refs:

$$
\operatorname{dom}(\mathrm{args})=A_P.
$$

A successful transaction exposes only declared return registers, and each must be initialized:

$$
\forall r\in R_P,\quad r\in\operatorname{dom}(\mathcal R_{\mathrm{VM}}).
$$

Registers hold typed native semantic values, not human-readable variable names.

## State-scoped capability contract

Let $C_g$ be the global granted capability mask and $C_s$ the grant for actual state slot $s$. An instruction requiring capability $c_i$ on $s$ may execute only when:

$$
c_i\subseteq C_g\cap C_s.
$$

v0.8 separates axis read permission from axis mutation permission:

$$
\mathrm{CAP\_AXIS\_READ}\neq\mathrm{CAP\_AXIS}.
$$

This allows a program to read state $A$ and write state $B$ without granting write access to $A$.

## Cross-state dataflow

A typical native dataflow path is:

$$
S_A\xrightarrow{\mathrm{LOAD\_AXIS}}r
\xrightarrow{\mathrm{STORE\_AXIS}}S_B'.
$$

The semantic value remains a typed machine value in the register file. No inspection JSON conversion is required.

## Deterministic parallel execution

The scheduler computes batches from instruction dependencies plus state/register hazards. If two ready instructions are independent they may share a batch:

$$
B_k=(i_a,i_b,\ldots).
$$

Workers evaluate against the same batch-start immutable snapshot. No result is committed unless every worker in the batch succeeds. Successful results commit in numeric instruction-ref order, so:

$$
\operatorname{Hash}(\mathrm{Exec}_{serial}(P,S))
=
\operatorname{Hash}(\mathrm{Exec}_{parallel}(P,S)).
$$

Any worker failure rolls back the complete transaction.

## CLI

Run a v0.8 VM program with numeric register arguments and slot-scoped grants:

```bash
isql-dsr vm-run --registry symbols.isqlr --program root.isqlp \
  --state 12=state-a.isqln --state 13=state-b.isqln \
  --arg 41='{"kind":"point","value":9}' \
  --scope 12=768 --scope 13=1 \
  --callee child.isqlp --parallel --out-dir result
```

Export the exact `.isqlp` bytes through the existing Core-compatible VM envelope:

```bash
isql-dsr vm-bridge --registry symbols.isqlr --program root.isqlp \
  --state 12=state-a.isqln --state 13=state-b.isqln
```

The transport control remains `EXEC/R4/DSRV`.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -q
```

See `docs/NATIVE_VM_v0.8.md` for the native VM contract and `docs/superpowers/specs/2026-08-18-isql-dsr-v08-register-vm-design.md` for the design rationale.
