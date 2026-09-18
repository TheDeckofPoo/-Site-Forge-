# Sorter Phase 1 Generation Report

**emitted:** `True`  
**plc_generation:** `PHASE1_GENERATED`  
**generated_at:** `2026-09-18T06:35:10.823355+00:00`

## Multiplicity (from model)

- encoders: **6**
- tracking: **5**
- diverts: **32**
- wave rungs kept: **32** / pack **16**

## Routines

Divert_Lane_Status, Divert_Rate_Limit, Encoder, Gridlock_Prevention, Main, Response_Time, Scanner, Track_Divert_Confirm, Track_Divert_Package, Track_Induct_Package, Track_Lost_Package, Track_Manual_Destination, Track_Offset_Find, Track_Package, Track_Pointer, Wave_Divert, Build_Config

## Severity

```json
{
  "FATAL_ERROR": [],
  "REVIEW_REQUIRED": [],
  "ENGINEER_REQUIRED": [
    "sorter_type"
  ],
  "OPTIONAL_UNRESOLVED": [
    "transport_area",
    "divert_confirm_pe",
    "global_track_offset"
  ],
  "WARNING": [
    "wcs_interface_external_not_emitted"
  ],
  "can_emit": true
}
```

## WCS boundary

WCS_INTERFACE_REQUIRED_EXTERNAL
