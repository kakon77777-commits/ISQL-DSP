# AI_HANDOFF — ISQL-DSR Runtime v0.9.0

## Canonical rule

Do not promote JSON, Markdown, textual variable names, jump labels, debug names, or human-facing schemas into the canonical machine layer. `.isqlr/.isqln/.isqle/.isqlb/.isqlp` remain canonical binary artifacts.

## v0.9 invariants

1. VM program payload format version 9 is current; v7 and v8 programs remain decodable.
2. Registers store validated DSR semantic values, not human variable strings.
3. Numeric algebra accepts numeric `PointValue` only; booleans are not numeric.
4. ADD/SUB/MUL preserve integer points only when both operands are integer points; mixed numeric operations promote to float. DIV returns float and rejects zero divisor.
5. EQ is structural semantic-value equality. LT/LE require numeric points and produce boolean point values.
6. Register guards are fail-closed transaction preconditions.
7. Predicate registers are conditional execution controls: opposite boolean means skip, not failure.
8. Missing or non-boolean predicate registers fail closed.
9. Skipped instructions satisfy structural DAG dependency completion but do not enter execution trace or mutate state/registers.
10. Register guards and predicates participate in scheduler hazard analysis.
11. Static linking preserves numeric instruction refs; duplicate refs, registry mismatches, and conflicting bindings are rejected.
12. Sequential linking adds causal edges between prior-module exits and next-module entries. Module RETURN instructions are removed because the linked frame owns the return interface.
13. Existing transaction atomicity, state-scoped capability, CALL/RETURN, and deterministic parallel guarantees remain in force.
14. Core transport remains `EXEC/R4/DSRV`; `R4` is Core resolution, not DSR version.
15. Registry/decoder/program side information must remain included in any compression-cost claim.

## Current native compute opcodes

- CONST = 1201
- MOVE = 1202
- ADD = 1211
- SUB = 1212
- MUL = 1213
- DIV = 1214
- EQ = 1221
- LT = 1222
- LE = 1223

## Control model

Do not replace predicated DAG control with textual labels merely for readability. v0.9 intentionally keeps causal DAG scheduling:

$$
	ext{comparison}
\to
	ext{boolean register}
\to
	ext{predicated instruction set}.
$$

A future version may add richer typed register schemas or more algebra only if a concrete machine-native use case requires them.
