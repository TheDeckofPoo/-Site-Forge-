# PLC5 Sorter Field Authority (Gate F)

**Generated:** `2026-09-18T04:05:17.335803+00:00`  
**Machine (discovery outcome):** `ORNCCP5`  
**PLC generation:** **NOT_STARTED**  

Authority classes: `PROVEN` / `DERIVED` / `REVIEW_REQUIRED` / `UNKNOWN`.
No finished-PLC L5X used as discovery input. No site-name production hardcodes.

## Fields

### 1. Sorter type

- **PRIMARY EVIDENCE:** none (no explicit type column)
- **SUPPORTING EVIDENCE:** Sorters.Name tokens are not proof
- **RELATIONSHIP PATH:** —
- **AUTHORITY:** `REVIEW_REQUIRED`
- **AUTOPOPULATE:** NO
- **ENGINEER ACTION:** Select shoe/popup/etc. in UI
- **WHY:** RUN has no authoritative sorter equipment-type field

### 2. Sorter/application identity

- **PRIMARY EVIDENCE:** Sorters.Sorter Name + SrtAppControl.Name
- **SUPPORTING EVIDENCE:** SrtZoneLane.AppSorter; Outpoints.Sorter
- **RELATIONSHIP PATH:** Sorters ‖ SrtAppControl; sections via Outpoints⋈SrtZoneLane
- **AUTHORITY:** `PROVEN`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** None when present
- **WHY:** Named active rows are PROVEN; multi-section-under-app is DERIVED via lane join

### 3. Transport Area association

- **PRIMARY EVIDENCE:** none
- **SUPPORTING EVIDENCE:** Machine / jamzone strings are not Area membership
- **RELATIONSHIP PATH:** —
- **AUTHORITY:** `UNKNOWN`
- **AUTOPOPULATE:** NO
- **ENGINEER ACTION:** Assign Transport area in UI
- **WHY:** No schema edge from sorter tables to Transport Areas

### 4. Induct conveyor

- **PRIMARY EVIDENCE:** Encoders.EnableBit → Mtrchain.Motor_Chained1
- **SUPPORTING EVIDENCE:** Inpoints proves PE only (no conveyor column)
- **RELATIONSHIP PATH:** Sorters.Encoder→Encoders.EnableBit→Mtrchain→Conveyor
- **AUTHORITY:** `DERIVED`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** Confirm if DERIVED; enter if UNKNOWN
- **WHY:** Same-section belt from VFD enable/aux pairing when Conveyor+Mtrchain verify both names

### 5. Induct PE

- **PRIMARY EVIDENCE:** Inpoints.Induct I/O Name
- **SUPPORTING EVIDENCE:** Inpoints.Sorter == Sorters.Sorter Name
- **RELATIONSHIP PATH:** Sorters → Inpoints
- **AUTHORITY:** `PROVEN`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** None when PROVEN
- **WHY:** Explicit Induct I/O Name on Inpoints

### 6. Induct encoder

- **PRIMARY EVIDENCE:** Sorters.Encoder ioName
- **SUPPORTING EVIDENCE:** Encoders row
- **RELATIONSHIP PATH:** Sorters → Encoders
- **AUTHORITY:** `PROVEN`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** None when PROVEN
- **WHY:** First/section encoder link is RUN-explicit

### 7. Tracking conveyor count

- **PRIMARY EVIDENCE:** count(active Sorters)
- **SUPPORTING EVIDENCE:** tracking_path length
- **RELATIONSHIP PATH:** Sorters active rows
- **AUTHORITY:** `DERIVED`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** Adjust only if engineer merges/splits sections
- **WHY:** One tracking section stub per active Sorters row

### 8. Tracking conveyor identities

- **PRIMARY EVIDENCE:** Mtrchain.Motor_Chained* via EnableBit
- **SUPPORTING EVIDENCE:** Conveyor.IO_Name existence check
- **RELATIONSHIP PATH:** Encoders.EnableBit → Mtrchain → Conveyor
- **AUTHORITY:** `DERIVED`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** Fill blanks; never trust ENC###≡P###
- **WHY:** resolved=5/5 ['P504', 'P506', 'P508', 'P509', 'P510']

### 9. Tracking conveyor ORDER

- **PRIMARY EVIDENCE:** Sorters.Data LowRec ascending
- **SUPPORTING EVIDENCE:** Mtrchain Motor_Aux chain (supporting)
- **RELATIONSHIP PATH:** Sorters.Data LowRec
- **AUTHORITY:** `DERIVED`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** Reorder only if buffer ranges are wrong for site intent
- **WHY:** Order from record-range allocation, not name suffixes

### 10. Tracking PE count

- **PRIMARY EVIDENCE:** count(Inpoints per Sorters)
- **SUPPORTING EVIDENCE:** tracking_path photoeye fills
- **RELATIONSHIP PATH:** Inpoints
- **AUTHORITY:** `DERIVED`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** Add extra PEs if needed
- **WHY:** resolved=5/5

### 11. Tracking PE identities

- **PRIMARY EVIDENCE:** Inpoints.Induct I/O Name
- **SUPPORTING EVIDENCE:** Conveyor Type=PHOTOCELL existence
- **RELATIONSHIP PATH:** Sorters → Inpoints
- **AUTHORITY:** `PROVEN`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** None when PROVEN
- **WHY:** ['PE504_I', 'PE506_I', 'PE508_I', 'PE509_I', 'PE510_I']

### 12. Tracking PE ORDER

- **PRIMARY EVIDENCE:** same as tracking section order
- **SUPPORTING EVIDENCE:** Inpoints.Induct Number
- **RELATIONSHIP PATH:** tracking_path sequence
- **AUTHORITY:** `DERIVED`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** Review if multiple inducts per section
- **WHY:** Follows section order from Data LowRec

### 13. Encoder per tracking section

- **PRIMARY EVIDENCE:** Sorters.Encoder ioName
- **SUPPORTING EVIDENCE:** Encoders.Ticks Per Foot / EnableBit
- **RELATIONSHIP PATH:** Sorters → Encoders
- **AUTHORITY:** `PROVEN`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** None when PROVEN
- **WHY:** ['ENC504', 'ENC506', 'ENC508', 'ENC509', 'ENC510']

### 14. Scan zone

- **PRIMARY EVIDENCE:** SrtScanBoss.ScanZone / ScnScanZone.Name
- **SUPPORTING EVIDENCE:** ScnScanZone.TrackingTable
- **RELATIONSHIP PATH:** SrtScanBoss → ScnScanZone
- **AUTHORITY:** `PROVEN`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** None when PROVEN
- **WHY:** Explicit scan zone names when tables populated

### 15. Scanner / scan boss

- **PRIMARY EVIDENCE:** SrtScanBoss + ScnScanDevice
- **SUPPORTING EVIDENCE:** AppSorter / ScanZone joins
- **RELATIONSHIP PATH:** SrtAppControl ← SrtScanBoss → ScnScanDevice
- **AUTHORITY:** `PROVEN`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** None when PROVEN
- **WHY:** bosses=1 devices=1

### 16. Divert count

- **PRIMARY EVIDENCE:** count(active SrtZoneLane)
- **SUPPORTING EVIDENCE:** Outpoints active rows
- **RELATIONSHIP PATH:** SrtZoneLane
- **AUTHORITY:** `PROVEN`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** None for topology count
- **WHY:** count=32

### 17. Divert/lane identities

- **PRIMARY EVIDENCE:** SrtZoneLane.Lane / Name
- **SUPPORTING EVIDENCE:** Outpoints.Outpoint Name
- **RELATIONSHIP PATH:** SrtZoneLane
- **AUTHORITY:** `PROVEN`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** None
- **WHY:** Topology PROVEN from SrtZoneLane

### 18. Host zones

- **PRIMARY EVIDENCE:** SrtZoneLane.HostZone
- **SUPPORTING EVIDENCE:** —
- **RELATIONSHIP PATH:** SrtZoneLane
- **AUTHORITY:** `PROVEN`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** None
- **WHY:** HostZone column is RUN-explicit

### 19. Divert physical output

- **PRIMARY EVIDENCE:** Outpoints.Outpoint I/O Name
- **SUPPORTING EVIDENCE:** SrtZoneLane.LaneEnableSignal (often INVALID)
- **RELATIONSHIP PATH:** SrtZoneLane.Lane == Outpoints.Outpoint Name
- **AUTHORITY:** `PROVEN`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** Supply IO when Outpoints also INVALID
- **WHY:** resolved=32/32 (LaneEnableSignal alone is not sufficient when INVALID)

### 20. Divert PE if applicable

- **PRIMARY EVIDENCE:** Outpoints.Verify I/O Name when valid
- **SUPPORTING EVIDENCE:** FullClearTimer name is hint only
- **RELATIONSHIP PATH:** Outpoints / SrtZoneLane timers
- **AUTHORITY:** `REVIEW_REQUIRED`
- **AUTOPOPULATE:** NO
- **ENGINEER ACTION:** Map confirm PE when Verify I/O INVALID
- **WHY:** Timer-name PE parsing is not treated as proof

### 21. Tracking distance/offset

- **PRIMARY EVIDENCE:** Outpoints.Outpoint Location (ticks) partial
- **SUPPORTING EVIDENCE:** no induct→divert offset field
- **RELATIONSHIP PATH:** Outpoints.Outpoint Location
- **AUTHORITY:** `REVIEW_REQUIRED`
- **AUTOPOPULATE:** NO
- **ENGINEER ACTION:** Enter track offsets / commissioning
- **WHY:** Locations are per-outpoint; global induct→divert offset not in RUN

### 22. Trigger window

- **PRIMARY EVIDENCE:** Sorters.TrigWndwTicks
- **SUPPORTING EVIDENCE:** —
- **RELATIONSHIP PATH:** Sorters
- **AUTHORITY:** `PROVEN`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** None when PROVEN
- **WHY:** Explicit TrigWndwTicks on Sorters

### 23. PPI / encoder scaling

- **PRIMARY EVIDENCE:** Encoders.Ticks Per Foot
- **SUPPORTING EVIDENCE:** Target FPM
- **RELATIONSHIP PATH:** Encoders
- **AUTHORITY:** `PROVEN`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** None when PROVEN
- **WHY:** Ticks Per Foot is RUN-explicit scale

### 24. Maximum cartons/buffer values

- **PRIMARY EVIDENCE:** Sorters.Max Cartons + Data/Buffer Low/HighRec
- **SUPPORTING EVIDENCE:** SortBuff/SortData row ranges
- **RELATIONSHIP PATH:** Sorters (+ SortBuff/SortData occupancy)
- **AUTHORITY:** `PROVEN`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** None when PROVEN
- **WHY:** Max Cartons and record ranges are explicit

### 25. Other Sorter_Track-critical params

- **PRIMARY EVIDENCE:** partial (msg tables, ErrConfig, TrackingTable)
- **SUPPORTING EVIDENCE:** gold pack constants are NOT used
- **RELATIONSHIP PATH:** SrtAppControl / ScnScanZone
- **AUTHORITY:** `REVIEW_REQUIRED`
- **AUTOPOPULATE:** NO
- **ENGINEER ACTION:** Commissioning + library path still required before PLC emit
- **WHY:** plc_generation stays NOT_STARTED; no hollow Sorter_Track

### Application structure (sections vs apps)

- **PRIMARY EVIDENCE:** SrtZoneLane.AppSorter + Outpoints.Sorter via Outpoint Name==Lane join; Sorters rows are tracking sections
- **SUPPORTING EVIDENCE:** apps=['SHIP_SORTER']
- **RELATIONSHIP PATH:** SrtZoneLane⋈Outpoints
- **AUTHORITY:** `DERIVED`
- **AUTOPOPULATE:** YES
- **ENGINEER ACTION:** Confirm multi-section application intent
- **WHY:** Multiple Sorters rows are tracking sections. App ownership of divert lanes is proven via SrtZoneLane.AppSorter; section ownership of those lanes is proven via Outpoints.Sorter on the same lane name — not from name tokens alone. Sections lacking Outpoints⋈ZoneLane joins stay listed as tracking sections only.

## Autofill coverage (Gate F rows)

- PROVEN: **14** / 26
- DERIVED: **7** / 26
- ENGINEER_REQUIRED: **4** / 26
- UNKNOWN: **1** / 26

