# Sawtooth RUN Model

**Source of truth:** RUN/tar.gz tables + documented Fortna semantics + deterministic cross-table relationships.  
**Forbidden:** Finished PLC4 as generation input.

## Tables used (CP4 / generic)

| Table | Role |
|-------|------|
| `SawMerge.asc` (+ machine overlay) | Merge identity, MotorIO, ReserveIN, LaneEnableDelayTM, pSliceSeconds |
| `SawLane.asc` (+ overlay) | Lane Name → conveyor token, LaneNdx, PhotoEyeIO, DisableIO (VFD), ApproachUP, CollisionUP, LaneIN, SliceSeconds, ReserveSeconds, AllowedToRun, SawMerge link |
| `HSSawMerge` / `HSSawLane` / `HSSawParm` / `HSSawState` / `HSSawSim` | Inventoried; used when **active named rows** exist (CP4 overlay uses classic Saw*) |
| `Conveyor.asc` | VFD device rows, equipment existence for collector derivation |
| Encoder associations | ENC### matching VFD### digits / merge associations |
| `Mtrchain` / Fullline | Supporting relationships (collector downstream when proven) |

## Canonical artifact

Built on every RUN import by `fortna_sawtooth_merge_model.build_sawtooth_merge_model`:

- Attached to SiteModel as `sawtooth_merge_model`
- Editor shape as `editors.sawtooth` (`sawtooth_merge_model_v1`)
- UI status: `Sawtooth: 1 merge · 5 lanes` or `Not detected`

## Provenance

Every field carries:

`value`, `source_table`, `source_row_key`, `relationship_rule`, `provenance`

Allowed: `RUN_EXPLICIT` | `RUN_DERIVED` | `DOC_DEFINED` | `GENERIC_LIBRARY` | `ENGINEER_CONFIGURED` | `UNRESOLVED`

UNRESOLVED fields appear in the editor but must not invent PLC behavior.
