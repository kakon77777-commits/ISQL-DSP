# ISQL-DSR Native VM v0.9

## Canonical rule

`.isqlp` remains the canonical native program artifact. v0.9 advances the VM payload format to version 9 but does not introduce a new persistent artifact family. Human-readable names remain registry / inspection projections.

## Register algebra

The v0.9 VM adds pure register instructions with zero state effect:

- `VM_OP_CONST`
- `VM_OP_MOVE`
- `VM_OP_ADD`
- `VM_OP_SUB`
- `VM_OP_MUL`
- `VM_OP_DIV`
- `VM_OP_EQ`
- `VM_OP_LT`
- `VM_OP_LE`

Registers continue to hold validated DSR semantic values. Numeric arithmetic is defined only on numeric `PointValue` values; booleans are not numeric.

For numeric points $x$ and $y$:

$$
egin{aligned}
	ext{ADD}(x,y)&=x+y,\\
	ext{SUB}(x,y)&=x-y,\\
	ext{MUL}(x,y)&=xy,\\
	ext{DIV}(x,y)&=x/y,
	ext{ with }y\neq0.
\end{aligned}
$$

Integer-only ADD/SUB/MUL preserve integer points. Mixed numeric arithmetic promotes to floating-point. DIV returns a floating-point point value.

`EQ` compares semantic values structurally. `LT` and `LE` require numeric points and return `PointValue(bool)`.

## Register guards

v0.9 separates instruction abort guards from conditional execution predicates.

A register guard is a fail-closed precondition:

- initialized register;
- register equals an encoded semantic value.

If a register guard fails, the complete VM transaction fails and publishes the original state set.

## Predicated DAG branching

A v0.9 instruction may carry an optional predicate register $p$ and expected boolean $b$.

$$
	ext{execute}(i)
\iff
p=	ext{PointValue}(b).
$$

If $p$ contains the opposite boolean, the instruction is skipped rather than failed. Missing or non-boolean predicate values fail closed.

Dependencies describe structural completion. A skipped instruction still satisfies dependency completion for downstream nodes, but it does not appear in the execution trace and creates no state/register mutation.

This provides native branching without adding a program counter or textual jump labels.

## Scheduler hazards

The scheduler includes register reads introduced by:

- arithmetic/comparison operands;
- register guards;
- predicate registers;
- existing LOAD/STORE/CALL interfaces.

Register writers conflict with dependent readers/writers, preserving deterministic serial/parallel equivalence.

## Static program linking

`link_vm_programs()` creates a new `NativeVMProgram` from existing DAG modules.

In sequential mode, if module $M_{k+1}$ has entry set $E_{k+1}$ and module $M_k$ has exit set $X_k$, the linker adds:

$$
orall e\in E_{k+1},
orall x\in X_k,
\quad x\prec e.
$$

Module-local RETURN instructions are stripped because the linked frame owns the resulting interface. Instruction refs must remain globally unique. Registry pins and state bindings must be compatible.

## Compatibility

- VM v7 `.isqlp` remains decodable.
- VM v8 `.isqlp` remains decodable.
- v9 instruction metadata defaults to no register guards and no predicate when decoding older artifacts.
- Core transport remains `EXEC/R4/DSRV`.
