# Sorter Canonical Model Report

**SORTER PLC GENERATION: NOT STARTED**  
**SORTER CANONICAL MODEL: foundation (PROVEN fields only)**

## Principle

```
RUN → decoder/evidence → SorterModel (PROVEN)
        → engineer review (REVIEW/UNKNOWN)
        → Apply Sorter
        → Autogen effective model
        → PLC later (not this checkpoint)
```

No disconnected Sorter-only island. Engineer edits authoritative. Unknown stays explicit.

## PROVEN fields (when overlay populated)

- `sorters[].name`, `machine`, `encoder_io`, track record ranges  
- `encoders[]` scale / enable when valid  
- `app_controls[]` names / msg tables; `sorter_cnv_mtr` only if not INVALID  
- `scan_bosses[]`, `zone_lanes[]` topology  
- runtime inventory counts (not divert maps)

## NOT in proven model

- divert_io_map, track_offset, induct chain, shoe/popup hardware, name-derived type class  
- gold `Sorter_Track_Program.L5X` constants  

## ORNCCP2

Active sorters: **[]** — schemas available, no entities. Generation stays NOT_SUPPORTED.

## Next checkpoint

Wire Apply Sorter persistence + Autogen only after evidence authority rows are accepted; do not emit hollow Sorter_Track.
