from __future__ import annotations

from dataclasses import replace

from .errors import DSRExecutionError, DSRValidationError
from .vm import (
    NativeVMProgram,
    VMInstruction,
    VM_OP_ADD,
    VM_OP_CONST,
    VM_OP_DIV,
    VM_OP_EQ,
    VM_OP_LE,
    VM_OP_LT,
    VM_OP_MOVE,
    VM_OP_MUL,
    VM_OP_SUB,
    _decode_register_binary_payload,
    _decode_register_const_payload,
    _decode_register_move_payload,
    _execute_register_binary,
    _instruction_register_access,
    encode_register_const_payload,
    vm_execution_order,
)

_FOLDABLE_BINARY = frozenset({VM_OP_ADD, VM_OP_SUB, VM_OP_MUL, VM_OP_DIV, VM_OP_EQ, VM_OP_LT, VM_OP_LE})


def _uncontrolled(item: VMInstruction) -> bool:
    return not item.guards and not item.register_guards and item.predicate_register_ref == 0


def _constant_fold(program: NativeVMProgram) -> tuple[VMInstruction, ...]:
    by_ref = {item.instruction_ref: item for item in program.instructions}
    constants: dict[int, object] = {}
    out: dict[int, VMInstruction] = {}
    for ref in vm_execution_order(program):
        item = by_ref[ref]
        folded = item
        reads, writes = _instruction_register_access(item)
        if _uncontrolled(item) and item.opcode == VM_OP_CONST:
            destination, value = _decode_register_const_payload(item.payload)
            constants[destination] = value
        elif _uncontrolled(item) and item.opcode == VM_OP_MOVE:
            source, destination = _decode_register_move_payload(item.payload)
            if source in constants:
                value = constants[source]
                folded = replace(item, opcode=VM_OP_CONST, payload=encode_register_const_payload(destination, value))
                constants[destination] = value
            else:
                constants.pop(destination, None)
        elif _uncontrolled(item) and item.opcode in _FOLDABLE_BINARY:
            left, right, destination = _decode_register_binary_payload(item.payload)
            if left in constants and right in constants:
                try:
                    value = _execute_register_binary(item.opcode, constants[left], constants[right])
                except (DSRExecutionError, DSRValidationError):
                    constants.pop(destination, None)
                else:
                    folded = replace(item, opcode=VM_OP_CONST, payload=encode_register_const_payload(destination, value))
                    constants[destination] = value
            else:
                constants.pop(destination, None)
        else:
            for register_ref in writes:
                constants.pop(register_ref, None)
        out[ref] = folded
    return tuple(out[item.instruction_ref] for item in program.instructions)


def _remove_dead_constants(program: NativeVMProgram, items: tuple[VMInstruction, ...]) -> tuple[VMInstruction, ...]:
    producers: dict[int, set[int]] = {}
    reads_by_instruction: dict[int, set[int]] = {}
    for item in items:
        reads, writes = _instruction_register_access(item)
        reads_by_instruction[item.instruction_ref] = reads
        for register_ref in writes:
            producers.setdefault(register_ref, set()).add(item.instruction_ref)

    live: set[int] = set()
    return_refs = set(program.return_registers)
    for item in items:
        _, writes = _instruction_register_access(item)
        if item.effect_mask != 0 or item.opcode != VM_OP_CONST or not _uncontrolled(item) or writes & return_refs:
            live.add(item.instruction_ref)

    changed = True
    while changed:
        changed = False
        for instruction_ref in tuple(live):
            for register_ref in reads_by_instruction[instruction_ref]:
                for producer_ref in producers.get(register_ref, ()):
                    if producer_ref not in live:
                        live.add(producer_ref)
                        changed = True

    removable = {item.instruction_ref for item in items if item.instruction_ref not in live and item.opcode == VM_OP_CONST and _uncontrolled(item)}
    if not removable:
        return items

    by_ref = {item.instruction_ref: item for item in items}
    memo: dict[int, set[int]] = {}

    def bridge(ref: int, trail: frozenset[int] = frozenset()) -> set[int]:
        if ref not in removable:
            return {ref}
        if ref in memo:
            return set(memo[ref])
        if ref in trail:
            raise DSRValidationError("VM_OPTIMIZER_DEPENDENCY_CYCLE")
        result: set[int] = set()
        for dep in by_ref[ref].depends_on:
            result.update(bridge(dep, trail | {ref}))
        memo[ref] = set(result)
        return result

    kept = []
    for item in items:
        if item.instruction_ref in removable:
            continue
        deps: set[int] = set()
        for dep in item.depends_on:
            deps.update(bridge(dep))
        kept.append(replace(item, depends_on=tuple(sorted(deps))))
    return tuple(kept)


def optimize_vm_program(program: NativeVMProgram) -> NativeVMProgram:
    """Return a deterministic semantics-preserving optimized native VM program.

    v1.0 deliberately uses conservative passes: constant folding is limited to
    statically known scalar register operations, and dead-code elimination only
    removes dead unconditional CONST instructions.
    """
    if not isinstance(program, NativeVMProgram):
        raise TypeError("program must be NativeVMProgram")
    folded = _constant_fold(program)
    kept = _remove_dead_constants(program, folded)
    capability_mask = 0
    for item in kept:
        capability_mask |= item.required_capabilities
    return NativeVMProgram(
        program.registry_revision,
        program.registry_hash,
        program.program_ref,
        capability_mask,
        program.bindings,
        kept,
        program.argument_registers,
        program.return_registers,
        signature=program.signature,
    )
