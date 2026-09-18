# PLC5 Sorter Deep Autofill

**Generated:** `2026-09-18T04:05:17.337630+00:00`  
**Machine (discovery outcome):** `ORNCCP5`  
**PLC generation:** **NOT_STARTED**  

## Counts

| Item | Value |
|------|------:|
| Sorters discovered | **5** |
| Applications | 1 |
| Tracking sections | 5 |
| Encoders | 5 |
| Induct conveyor | `P504` (DERIVED) |
| Induct PE | `PE504_I` (PROVEN) |
| Tracking conveyors resolved | **5** / 5 |
| Tracking PEs resolved | **5** / 5 |
| Tracking order | `DERIVED` |
| Scan bosses | 1 |
| Scan zones | 1 |
| Divert topology rows | **32** |
| Divert outputs resolved | **32** |
| Divert PEs resolved (distinct Verify I/O) | **0** |

## Autofill coverage (Gate F)

- **14 / 26 PROVEN**
- **7 / 26 DERIVED**
- **4 / 26 ENGINEER_REQUIRED**
- **1 / 26 UNKNOWN**

### PROVEN fields

- 2. Sorter/application identity
- 5. Induct PE
- 6. Induct encoder
- 11. Tracking PE identities
- 13. Encoder per tracking section
- 14. Scan zone
- 15. Scanner / scan boss
- 16. Divert count
- 17. Divert/lane identities
- 18. Host zones
- 19. Divert physical output
- 22. Trigger window
- 23. PPI / encoder scaling
- 24. Maximum cartons/buffer values

### DERIVED fields

- 4. Induct conveyor
- 7. Tracking conveyor count
- 8. Tracking conveyor identities
- 9. Tracking conveyor ORDER
- 10. Tracking PE count
- 12. Tracking PE ORDER
- Application structure (sections vs apps)

### ENGINEER_REQUIRED fields

- 1. Sorter type
- 20. Divert PE if applicable
- 21. Tracking distance/offset
- 25. Other Sorter_Track-critical params

### UNKNOWN fields

- 3. Transport Area association

## Still blank / why

- **Sorter type:** no RUN type column — engineer selects pattern.
- **Transport Area:** no schema edge sorter→Areas.
- **Track offset (global):** Outpoint Location is per-lane ticks only.
- **Divert confirm PE:** FullClearTimer names are hints; Verify I/O often mirrors divert solenoid (not counted as PE).
- **ENC→conveyor:** never by numeric suffix; only EnableBit→Mtrchain when both motor names exist as Conveyor IO.

## Apply merge (Gate N)

dashboard fortna-plus.js Apply Sorter merges workbook like Safety: preserves conveyors/areas/safety_build/sawtooth_build; residual duplication remains vs safety-build.js / transport Apply helpers (documented for later centralization — Gate N).

## Blocks Sorter_Track compiler

- sorter_type (REVIEW)
- transport_area (UNKNOWN)
- global induct→divert track offset (REVIEW)
- commissioning / library path incomplete
- plc_generation NOT_STARTED by policy

