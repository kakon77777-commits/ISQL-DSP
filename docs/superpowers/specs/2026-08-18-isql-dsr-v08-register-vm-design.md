# ISQL-DSR v0.8 Register VM Design

## Goal

Extend the v0.7 guarded multi-state VM into a register-based AI-native dataflow VM without introducing a new persistent artifact. `.isqlp` remains canonical; human-readable JSON remains inspection-only.

## Design decision

Use a typed semantic register file rather than a stack VM or a separate transaction language. Registers are numeric registry references in a new `REGISTER_ID` namespace. Programs declare positional argument registers and return registers; subprogram CALL maps caller registers and state slots to callee registers and dynamic state bindings.

## Program model

A v0.8 program adds:

- `argument_registers: tuple[int, ...]`
- `return_registers: tuple[int, ...]`
- `scoped_capabilities: tuple[VMScopedCapability, ...]`

The existing global `capability_mask` remains as an upper bound. Each bound state slot also has an exact per-slot capability mask. Runtime authorization requires both global and state-scoped permission.

The program wire format version becomes 8. Decoder accepts legacy v7 programs and maps them to empty argument/return registers plus inferred scoped capability rows; legacy binary remains importable but v0.8 encoding is canonical for newly emitted programs.

## Register values

Registers hold existing ISQL semantic values supported by `_encode_semantic_value` / `_decode_semantic_value`; no human field names are stored in canonical `.isqlp`. Root arguments are supplied by numeric register ref. A successful transaction returns the root program's declared return register values.

## New VM operations

- `VM_OP_LOAD_AXIS = 1101`: read an axis semantic value from a source state slot into a destination register. Requires `CAP_AXIS_READ` and has no state write effect.
- `VM_OP_STORE_AXIS = 1102`: write a register semantic value to an axis on a destination state slot using numeric key/domain refs plus uncertainty/resolution metadata. Requires existing `CAP_AXIS` write permission and has `EFFECT_AXIS`.

This creates true cross-state dataflow: load from slot A into a register, then store to slot B.

## CALL / RETURN

CALL v0.8 payload contains:

1. callee program ref;
2. child-slot to caller-slot alias pairs;
3. caller argument register refs in positional order;
4. caller destination registers for callee return values.

A callee may have multiple dynamic state bindings. Its declared argument registers receive copied caller values; its declared return registers are copied back on successful return. CALL is synchronous and preserves atomic transaction semantics.

## State-scoped capability model

Introduce `VMScopedCapability(slot_ref, capability_mask)` and runtime `granted_scoped_capabilities`.

Authorization condition for an instruction on actual slot `s` is:

`required_capabilities ⊆ global_grant ∩ scoped_grant[s]`.

`CAP_AXIS_READ` is distinct from `CAP_AXIS` write permission. This permits read-only access to a state without granting mutation capability.

## Deterministic parallel scheduler

Add `vm_execution_batches(program)`.

A batch may contain instructions that:

- are simultaneously dependency-ready;
- do not contain CALL/RETURN;
- do not write the same state slot;
- do not have register RAW/WAR/WAW hazards;
- do not mix a state write with any other access to the same slot.

Independent batch instructions execute concurrently using a thread pool over immutable batch-start snapshots. Their produced state/register deltas are committed in ascending instruction-ref order. Therefore scheduling is parallel but observable results remain deterministic.

CALL and RETURN are singleton sequential batches.

## Failure semantics

Any guard failure, missing argument, uninitialized register, capability denial, CALL mapping mismatch, call cycle, instruction failure, or parallel worker failure aborts the whole multi-state transaction. Published states and returns revert to the original transaction boundary; no partial register output is exposed.

## Compatibility

- `.isqlr/.isqln/.isqle/.isqlb/.isqlp` remain the artifact family.
- Core transport remains `EXEC/R4/DSRV`; v0.8 is an internal VM-format revision, not a Core resolution change.
- v0.7 API behavior with no registers and unrestricted scoped grants remains valid.
