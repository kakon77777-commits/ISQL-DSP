# ISQL-DSR Runtime v0.7.0 — Release Notes

v0.7 turns the v0.6 causal program layer into a guarded capability-aware multi-state VM while preserving all previous canonical artifact families.

## Added

- v0.7 VM `.isqlp` codec (`vm.py`).
- `STATE_SLOT_ID` and `CAPABILITY_ID` registry namespaces.
- exact/dynamic state bindings.
- numeric state/axis/relation guards.
- capability gating derived from machine effects.
- synchronous CALL and terminal RETURN.
- recursive CALL cycle rejection.
- atomic transaction execution over multiple registered states.
- per-state base/final hashes and numeric execution/call trace receipts.
- `vm-run` and `vm-bridge` CLI commands.
- Core `EXEC/R4/DSRV` transport envelope.

## Compatibility

v0.6 `.isqlp` causal programs and `EXEC/R4/DSRP` remain supported. v0.7 VM programs use a distinct v7 binary magic/version under the same `.isqlp` artifact family.
