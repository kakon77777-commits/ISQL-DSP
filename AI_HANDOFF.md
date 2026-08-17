# AI_HANDOFF — ISQL-DSR Runtime v0.5.0

## Canonical rule

Do not promote JSON, Markdown, natural language or human-readable field names back into the canonical state layer.

Canonical artifacts are `.isqlr`, `.isqln`, `.isqle`, and `.isqlb`.

## Non-negotiable invariants

1. Registry refs are references, not meaning itself.
2. Registered state is bound to registry revision + prefix hash.
3. Positive and negative relation sets are disjoint.
4. `deny_relation` means explicit negative assertion; `retract_relation` means return to unasserted/unknown.
5. Canonical replay must use `apply_native_event()` and must not require `inspect_registered_state()` or `runtime.apply_event()`.
6. Native fusion and topology operate over numeric registered structures.
7. Branch merge must be deterministic under branch-order permutation.
8. Conflicts must be explicit; never resolve by whichever branch is processed first.
9. `.isqlb` does not mutate the registry. Branch IDs must already exist in `BRANCH_ID` namespace.
10. Compression/storage claims must count registry and decoder side information.
11. Core envelope `R4` is transport compatibility with Core v0.4, not DSR version identity.

## v0.5 canonical relation status

For relation triple $r$:

$$
\operatorname{status}(r)\in\{-1,0,+1\}.
$$

- `+1`: positive assertion.
- `-1`: negative assertion.
- `0`: no current assertion.

Do not collapse `-1` and `0`.

## Branch merge scope

v0.5 merges numeric context, axes, relation polarity and projections. Topology is invalidated when active positive relations change. Conflicting changes retain the base value/status and emit a machine conflict.

## Next plausible frontier

- Replayable merge commits as first-class native events.
- Causal/vector-clock branch metadata for distributed multi-agent streams.
- Native executable rules over SEM/STATE without inspection adapters.
- Registry sharding / distributed symbol reconciliation.
- Numeric topology operators beyond weak components/cycle rank.
