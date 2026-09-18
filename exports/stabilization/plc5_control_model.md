# FortnaPlus Control Model Report

**Machine:** `ORNCCP5`  
**Generated:** `2026-09-18T06:11:01.313030+00:00`  
**PLC generation:** `NOT_STARTED`

## Counts

- Conveyor catalog classified: **1428**
- Class counts: `{"LOGICAL_SIGNAL": 231, "UNKNOWN": 2, "PHYSICAL_EQUIPMENT": 849, "PHYSICAL_OUTPUT": 130, "PHYSICAL_INPUT": 216}`
- StartStop zones: **8**
- Jam zones: **27**
- Logical signals: **231** (referenced **78**)
- Control graph nodes/edges: **313** / **229**

## Jam coverage

`{"unresolved_references": 0, "absent_references": 14, "logical_signal_references": 105, "physicalish_references": 43}`

## Referenced logical sample

CP5_CP6_PBSTART, CP5_CP6_PBSTOP, ENABLE_2CR1_LANES, ENABLE_2CR2_ACCUM, ENABLE_3CR1_LANES, ENABLE_3CR2_ACCUM, ENABLE_5CR2_REDROOM, ENABLE_BIN_MOD, ENABLE_CP1_ACCUM, ENABLE_CP4_ACCUM, ENABLE_CP8_BM_MRGE, ENABLE_MERGE_720, ENABLE_SAWTOOTH, ENABLE_SHIP_SORTER, ENABLE_TRASH, INT-TC, INT408, INT818, JAM_2CR1_LANES, JAM_2CR2_ACCUM

## Invariants

- LogicalSignal.physicalEndpoint is null
- Field INVALID remains ABSENT_REFERENCE
- Conveyor.Type=INVALID does not discard named referenceable objects
- Frozen Transportation Mtrchain topology proofs unchanged
