# Native VM v0.7

## Program object

A v0.7 VM program is canonically represented as:

$$
P=(R,h,p,C,B,I),
$$

where $R$ is registry revision, $h$ is the registry prefix hash, $p$ is the numeric program ref, $C$ is the exact direct capability mask, $B$ is the state-binding set, and $I$ is the causal instruction DAG.

## State bindings

An exact binding pins a numeric state slot to revision/hash. A dynamic binding has no base pin and is used for the current single-state synchronous subprogram calling convention.

## Instruction

Each instruction contains only machine fields:

$$
i=(r,o,e,c,s,D,G,payload),
$$

with instruction ref $r$, opcode $o$, effect mask $e$, required capability mask $c$, target slot $s$, causal dependencies $D$, guards $G$, and native payload.

## Guards

Current numeric guard opcodes test state hash, axis presence/absence, axis semantic value, and relation polarity. Guard failure aborts the enclosing transaction.

## CALL / RETURN

CALL resolves a numeric program ref and executes it synchronously on the caller instruction's target state slot. v0.7 callees use one dynamic state binding. RETURN terminates a program frame. Recursive program-ref cycles are rejected.

## Atomic multi-state execution

Execution works over a working copy of a mapping:

$$
\{s_1\mapsto S_1,\ldots,s_n\mapsto S_n\}.
$$

If every frame succeeds, all working states are published. Any validation, capability, guard, native operator or subcall error returns the original mapping bit-for-bit.

## Transport

The current ISQL Core v0.4 grammar accepts resolutions only through R4, therefore VM programs use:

`ISQL1:EXEC:R4:DSRV<digits>`

where `<digits>` is the decimal-byte encoding of the canonical v0.7 VM program bytes.
