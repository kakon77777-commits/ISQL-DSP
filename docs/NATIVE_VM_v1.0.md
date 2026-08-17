# ISQL-DSR Native VM v1.0

## 1. Machine value algebra

The v1.0 semantic value set is:

$$
\mathcal V
=
\mathcal V_{point}
\cup
\mathcal V_{interval}
\cup
\mathcal V_{candidates}
\cup
\mathcal V_{vector}
\cup
\mathcal V_{record}.
$$

A vector is an immutable ordered tuple:

$$
V=(v_0,\ldots,v_{n-1}).
$$

A record is an immutable finite map represented canonically by strictly increasing numeric field refs:

$$
R=((f_1,v_1),\ldots,(f_n,v_n)),
\qquad
f_1<\cdots<f_n.
$$

Human field labels are shared-registry side information, not embedded record schema strings.

## 2. Function signatures

Each program has a signature:

$$
\Sigma(P)=A\rightarrow R.
$$

Argument and return interfaces remain ordered register refs; v1.0 additionally associates one numeric machine type tag with each interface register.

Legacy program versions are interpreted with `TYPE_ANY`.

## 3. Container operators

Vector operations:

- `VECTOR_PACK`;
- `VECTOR_GET`;
- `VECTOR_LEN`.

Record operations:

- `RECORD_PACK`;
- `RECORD_GET`;
- `RECORD_SET`.

`RECORD_SET` returns a new record value; it never mutates an existing register-local record in place.

## 4. Bounded repetition

`REPEAT_CALL` is synchronous and finite. The operation belongs to the same transaction as the caller. It may repeatedly transform state and feed CALL returns back into caller registers between iterations.

The protocol bound is:

$$
\mathrm{VM\_MAX\_REPEAT}=1024.
$$

Any iteration failure aborts the root transaction.

## 5. Static optimizer

For program $P$, the optimizer constructs $O(P)$ and targets:

$$
\operatorname{Obs}(P,S,A)
=
\operatorname{Obs}(O(P),S,A),
$$

where observable behavior includes final native state hashes, declared return values, and transaction failure semantics.

v1.0 deliberately implements a subset that can be defended conservatively:

- scalar constant folding;
- dead unconditional-constant elimination;
- causal dependency bridging after eliminated instructions.

The optimizer does not execute the program.

## 6. Transport

The program remains a `.isqlp` artifact and Core transport remains:

```text
EXEC / R4 / DSRV
```

No new human-readable canonical program representation is introduced in v1.0.
