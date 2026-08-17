# ISQL-DSR Runtime v0.9.0

ISQL Dynamic Spectrum Runtime v0.9 turns the register-dataflow VM into a native machine-value compute layer. It adds typed register algebra, semantic comparison, predicated DAG branching, fail-closed register guards, and static program linking while preserving the existing AI-native artifact family.

## Canonical artifact family

- `.isqlr` — append-only shared machine symbol registry.
- `.isqln` — registered materialized native semantic state.
- `.isqle` — hash-chained native transition stream.
- `.isqlb` — causal branch artifact.
- `.isqlp` — native VM program artifact.

JSON, Markdown, CLI summaries, debug names, and natural language remain inspection/projection layers only.

## What v0.9 adds

1. **Typed register algebra.** Native CONST/MOVE/ADD/SUB/MUL/DIV operate directly on machine semantic values.
2. **Native comparison.** EQ/LT/LE write boolean `PointValue` results into registers.
3. **Predicated DAG branching.** Instructions can execute or skip based on a boolean register without introducing a textual jump/program counter.
4. **Register-level guards.** Initialized/equality guards abort the whole transaction when a machine precondition fails.
5. **Static program linking.** `link_vm_programs()` and CLI `vm-link` compose multiple `.isqlp` DAG modules into one canonical program.
6. **Scheduler-aware control flow.** Predicate and guard register reads participate in RAW/WAR/WAW hazard analysis.
7. **v7/v8 VM compatibility.** Older VM program payloads remain decodable.
8. **Stable Core transport.** VM programs continue to use `EXEC/R4/DSRV`.

## Algebra contract

For numeric point values $x$ and $y$:

$$
egin{aligned}
	ext{ADD}(x,y)&=x+y,\\
	ext{SUB}(x,y)&=x-y,\\
	ext{MUL}(x,y)&=xy,\\
	ext{DIV}(x,y)&=x/y,
	ext{ where }y\neq0.
\end{aligned}
$$

Booleans are not treated as integers. EQ may compare any valid semantic value structurally; LT/LE require numeric point values.

## Branching contract

Comparison can write a boolean register:

$$
r_c=	ext{LT}(r_a,r_b).
$$

Two downstream instructions can use opposite predicates on $r_c$. A false predicate is a skip, not a transaction error. A missing or non-boolean predicate fails closed.

A register guard is different: guard failure means the instruction's machine precondition is violated, so the complete transaction rolls back.

## Linking

Sequentially link modules:

```bash
isql-dsr vm-link --registry symbols.isqlr --program-ref 31 \
  --module normalize.isqlp --module decide.isqlp \
  --argument-register 42 --return-register 45 \
  --out linked.isqlp
```

Run the linked program using the existing native VM path:

```bash
isql-dsr vm-run --registry symbols.isqlr --program linked.isqlp \
  --state 12=state.isqln \
  --arg 42='{"kind":"point","value":9}' \
  --out-dir result
```

## Verification

```bash
PYTHONPATH=src python -m unittest discover -s tests -q
```

See `docs/NATIVE_VM_v0.9.md` for the machine contract.
