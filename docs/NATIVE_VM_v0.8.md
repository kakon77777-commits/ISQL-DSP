# ISQL-DSR Native VM v0.8

## 1. Scope

v0.8 adds a machine register interface, state-scoped capability enforcement, cross-state value movement, multi-slot CALL argument/return transfer, and deterministic parallel scheduling. It does not create a new persistent artifact. The canonical VM artifact remains `.isqlp`.

## 2. Program form

A v0.8 VM program is modeled as:

$$
P=
(R,h,p,C,B,I,A,O,S),
$$

where:

- $R$ is registry revision;
- $h$ is registry prefix hash;
- $p$ is numeric program ref;
- $C$ is the program capability mask;
- $B$ is the state-binding tuple;
- $I$ is the instruction DAG;
- $A$ is the ordered argument-register tuple;
- $O$ is the ordered return-register tuple;
- $S$ is the canonical state-slot capability tuple.

The binary encoding uses numeric refs and typed payload bytes. The tuple above is explanatory notation only; field labels are not canonical payload strings.

## 3. Argument and return register contract

For argument registers $A=(a_1,\ldots,a_m)$, the caller must provide exactly one typed value per declared ref:

$$
\operatorname{dom}(\mathrm{args})=\{a_1,\ldots,a_m\}.
$$

The VM rejects both missing and undeclared root arguments.

For declared returns $O=(o_1,\ldots,o_n)$, success requires every $o_j$ to be initialized. Only those registers are projected out of the VM transaction.

## 4. Scoped capabilities

Each program has a global capability mask $C_g$ and a canonical local requirement mask $C_{P,s}$ per local state slot. At runtime the caller provides an actual grant $C_{R,s'}$ for each resolved state slot $s'$.

An instruction requiring $c_i$ may operate on resolved slot $s'$ only if:

$$
c_i\subseteq C_g,
$$

$$
c_i\subseteq C_{P,s},
$$

and

$$
c_i\subseteq C_{R,s'}.
$$

`CAP_AXIS_READ` and `CAP_AXIS` are intentionally distinct.

## 5. Native register dataflow

`LOAD_AXIS`:

$$
(S_s,k)\mapsto r_d.
$$

It reads the typed semantic value of axis key $k$ from state slot $s$ and writes it to destination register $r_d$.

`STORE_AXIS`:

$$
r_s\mapsto(S_d,k,D,u,\rho).
$$

It reads a typed semantic value from source register $r_s$ and materializes/replaces axis key $k$ in destination state slot $d$ with domain $D$, uncertainty $u$, and resolution $\rho$.

No natural-language intermediate representation is required.

## 6. Multi-slot CALL

A structured CALL payload contains:

$$
(c,\Lambda,A_c,O_c),
$$

where $c$ is the callee program ref, $\Lambda$ is the child-slot to caller-slot alias relation, $A_c$ is the caller argument-register list, and $O_c$ is the caller return-destination-register list.

Every dynamic callee binding must appear exactly once in $\Lambda$. Argument and return arities must match the callee declarations.

The callee receives a fresh register file. Caller values are copied into callee argument registers positionally. On successful RETURN, callee declared returns are copied into caller destination registers positionally.

## 7. Scheduling

Let $\prec$ be the program's explicit dependency relation. Ready instructions are considered in ascending numeric instruction-ref order. A batch is built greedily from ready instructions that do not conflict.

Conflict classes include:

1. CALL/RETURN synchronization barrier;
2. state write/write or state read/write conflict on the same resolved local slot;
3. register read-after-write;
4. register write-after-read;
5. register write-after-write.

The resulting batch sequence is deterministic:

$$
\mathcal B(P)=(B_1,\ldots,B_k).
$$

## 8. Parallel execution

For a non-singleton batch $B_j$, all worker computations read the same immutable batch-start state/register snapshot. Workers do not publish state directly.

The batch commits only if all workers succeed. Results then commit in ascending numeric instruction-ref order.

Therefore the intended invariant is:

$$
H(\operatorname{Exec}_{serial}(P,S))
=
H(\operatorname{Exec}_{parallel}(P,S)).
$$

Any worker failure aborts the batch and transaction.

## 9. Backward compatibility

The decoder accepts v0.7 VM program format. Legacy programs have empty argument/return declarations and inferred scoped capability rows. Encoding a newly constructed v0.8 program uses format version 8.

## 10. Transport

Core transport remains:

$$
\texttt{EXEC/R4/DSRV}.
$$

The `DSRV` payload is the exact `.isqlp` VM bytes encoded as digits-only transport data. Human-readable projections are not inserted into the envelope.
