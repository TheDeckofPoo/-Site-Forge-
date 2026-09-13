# Transportation Acceptance Checkpoint

**Status:** CURTIS VISUAL PASS — FREEZE  
**Commit baseline:** `8d44f9b` (and subsequent UI-only/Hardware/Sawtooth fixes that must not redesign Transport)  
**Date:** 2026-09-13

## Accepted — do not redesign

- Canonical `ConveyorSectionModel`
- Topology / upstream-downstream compiler semantics
- Physical Auto Build layout algorithm
- Conveyor schematic rendering
- Autogen transport Fast / Slow / L1 / L2 generation
- IO_MAP physical Configio resolver (semantic VFD_FLT member mapping may be audited, not replaced)

## Allowed follow-ons (this pass)

- Marquee screen↔world coordinate bugfix
- Area selection UX polish (already engineer metadata)
- Hardware/I/O workspace consuming **same** Configio/eipcfg model as IO_MAP
- Sawtooth Apply/debug (separate subsystem)
- De-emphasizing duplicate site-config conveyor table from normal workflow

## Regression note

Any change that alters Transport canvas topology placement or Fast_Conv generation requires explicit Curtis re-acceptance.
