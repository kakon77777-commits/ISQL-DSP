from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .errors import DSRValidationError
from .registry import NativeSymbolRegistry, SymbolNamespace
from .vm import NativeVMProgram, VMInstruction, VM_OP_RETURN


def _module_body(program: NativeVMProgram) -> tuple[VMInstruction, ...]:
    return tuple(item for item in program.instructions if item.opcode != VM_OP_RETURN)


def _entry_refs(items: tuple[VMInstruction, ...]) -> tuple[int, ...]:
    refs = {item.instruction_ref for item in items}
    return tuple(sorted(item.instruction_ref for item in items if not (set(item.depends_on) & refs)))


def _exit_refs(items: tuple[VMInstruction, ...]) -> tuple[int, ...]:
    depended = {dep for item in items for dep in item.depends_on}
    return tuple(sorted(item.instruction_ref for item in items if item.instruction_ref not in depended))


def link_vm_programs(
    registry: NativeSymbolRegistry,
    program_ref: int,
    modules: Iterable[NativeVMProgram],
    *,
    sequential: bool = True,
    argument_registers: tuple[int, ...] | None = None,
    return_registers: tuple[int, ...] | None = None,
) -> NativeVMProgram:
    """Statically compose native DAG modules into one canonical VM program.

    Module RETURN instructions are frame-local terminators and are stripped. In sequential
    mode, each next module entry depends on every exit of the preceding non-empty module.
    """
    if not isinstance(registry, NativeSymbolRegistry):
        raise TypeError("registry must be NativeSymbolRegistry")
    if not isinstance(sequential, bool):
        raise DSRValidationError("VM_LINK_SEQUENTIAL_FLAG_INVALID")
    try:
        registry.resolve(program_ref, SymbolNamespace.PROGRAM_ID)
    except Exception as exc:
        raise DSRValidationError("VM_LINK_PROGRAM_REF_INVALID") from exc

    rows = tuple(modules)
    if not rows or not all(isinstance(module, NativeVMProgram) for module in rows):
        raise DSRValidationError("VM_LINK_MODULES_INVALID")

    pin = (rows[0].registry_revision, rows[0].registry_hash)
    if registry.revision < pin[0] or registry.prefix_hash(pin[0]) != pin[1]:
        raise DSRValidationError("VM_LINK_REGISTRY_MISMATCH")
    for module in rows[1:]:
        if (module.registry_revision, module.registry_hash) != pin:
            raise DSRValidationError("VM_LINK_REGISTRY_MISMATCH")

    binding_map = {}
    for module in rows:
        for binding in module.bindings:
            prior = binding_map.get(binding.slot_ref)
            if prior is not None and prior != binding:
                raise DSRValidationError("VM_LINK_BINDING_CONFLICT")
            binding_map[binding.slot_ref] = binding

    bodies = [_module_body(module) for module in rows]
    seen: set[int] = set()
    for body in bodies:
        for item in body:
            if item.instruction_ref in seen:
                raise DSRValidationError("VM_LINK_INSTRUCTION_DUPLICATE")
            seen.add(item.instruction_ref)

    linked: list[VMInstruction] = []
    previous_exits: tuple[int, ...] = ()
    for body in bodies:
        current = list(body)
        if sequential and previous_exits and current:
            entries = set(_entry_refs(tuple(current)))
            current = [
                replace(item, depends_on=tuple(sorted(set(item.depends_on) | set(previous_exits))))
                if item.instruction_ref in entries else item
                for item in current
            ]
        linked.extend(current)
        if current:
            previous_exits = _exit_refs(tuple(current))

    if argument_registers is None:
        argument_registers = tuple(sorted({ref for module in rows for ref in module.argument_registers}))
    if return_registers is None:
        return_registers = tuple(sorted({ref for module in rows for ref in module.return_registers}))
    if not isinstance(argument_registers, tuple) or not isinstance(return_registers, tuple):
        raise DSRValidationError("VM_LINK_REGISTER_INTERFACE_INVALID")
    for ref in argument_registers + return_registers:
        try:
            registry.resolve(ref, SymbolNamespace.REGISTER_ID)
        except Exception as exc:
            raise DSRValidationError("VM_LINK_REGISTER_INTERFACE_INVALID") from exc

    capability_mask = 0
    for item in linked:
        capability_mask |= item.required_capabilities

    return NativeVMProgram(
        pin[0], pin[1], program_ref, capability_mask,
        tuple(binding_map[ref] for ref in sorted(binding_map)),
        tuple(linked), argument_registers, return_registers,
    )
