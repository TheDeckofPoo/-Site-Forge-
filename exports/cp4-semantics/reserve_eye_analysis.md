# Reserve Eye Analysis (Sawtooth)

Generated: `2026-09-12T16:17:54.917035+00:00`

Pack EZPE tags: `EZPE116_F`, `EZPE127_F`, `EZPE212_F2`, `EZPE408_F`, `EZPE832_F`

## LANE_0_P219 — ReserveTM → EZPE217_F (no pack counterpart)

- **ReserveTM:** `tmfcEZPE217_F`
- **Extracted:** `EZPE217_F`
- **Pass full_eye_ezpe:** `EZPE217_F` (CONFIGURATION REQUIRED)
- **Pack has EZPE217_F:** False
- **Conveyor.asc:** `{'IO_Name': 'EZPE217_F', 'General_Description': 'FULL EYE ON P217', 'Type': 'PHOTOCELL', 'Machine_Name': 'ORNCCP4'}`
- **Fullline.asc:** `{'Desc': 'EZPE217_F', 'Sensor_Name': 'EZPE217_F', 'Timer_Name': 'tmEZPE217_F', 'Timer_Preset': '3.000', 'Clr_Timer_Name': 'tmfcEZPE217_F', 'Clr_Timer_Preset': '10.000', 'Error_Name': 'PE217_F', 'Conveyor_Name': 'P217', 'DontFireResponse': 'N', 'Response IO': 'M215', 'Invert': 'N', 'Go Until': 'INVALID', 'ReSound Horn': 'N/A', 'NoGap': 'N', 'Status': 'N', 'Sent': '0', 'FullClearOutput': 'INVALID', 'FullClearACTION': 'N/A', 'FullClearBIT': '0'}`
- **Pack usage:** RT_IO_Map_NoGapStore: IF EZPE127_F.Full THEN MRG414_astUNL_SlugBldCtrl[1].rQ1_SlugLength_Q := HMI Lane[1].ReleaseLengthFull ELSE ReleaseLength. This is slug-release-length selection when Use_GapStore_Belts=0 — not automatically the same mechanism as RUN SawLane.ReserveTM.

### RUN hits
- `EZPE217_F`:
  - `Fullline.asc`.`Desc` (row `EZPE217_F`)
  - `Fullline.asc`.`Sensor_Name` (row `EZPE217_F`)
  - `Conveyor.asc`.`IO_Name` (row `EZPE217_F`)
- `tmfcEZPE217_F`:
  - `SawLane.asc.ORNCCP4`.`ReserveTM` (row `LANE_0_P219`)
  - `Fullline.asc`.`Clr_Timer_Name` (row `EZPE217_F`)
  - `timemenu.asc`.`Timer_Name` (row ``)
- `tmEZPE217_F`:
  - `Fullline.asc`.`Timer_Name` (row `EZPE217_F`)
  - `timemenu.asc`.`Timer_Name` (row ``)
- `PE217_F`:
  - `Fullline.asc`.`Error_Name` (row `EZPE217_F`)
  - `Errors.asc`.`ErrorName` (row ``)
  - `Errors.asc`.`Description` (row ``)
- `P217`:
  - `Fullline.asc`.`Conveyor_Name` (row `EZPE217_F`)
  - `Conveyor.asc`.`IO_Name` (row `P217`)
  - `Mtrchain.asc`.`Motor_Chained1` (row ``)
- `P219`:
  - `Conveyor.asc`.`IO_Name` (row `P219`)
  - `Mtrchain.asc`.`Motor_Chained1` (row ``)

### Finding

RUN SawLane.ReserveTM explicitly names tmfcEZPE217_F for LANE_0_P219. Conveyor.asc and Fullline.asc both define EZPE217_F (FULL EYE ON P217 / Fullline→P217). Generic pack has NO EZPE217_F tag; it does have EZPE127_F used as Lane[1] full eye in RT_IO_Map_NoGapStore (different equipment — do NOT equate by digits). Pass marked CONFIGURATION REQUIRED because pack lacks counterpart — site symbol itself is RUN_EXPLICIT.

### Resolution guidance

- **run_symbol_EZPE217_F:** RUN_EXPLICIT
- **pack_binding:** CONFIGURATION_REQUIRED — add/bind EZPE217_F into site program; replace Lane[1] EZPE127_F.Full reference; do not substitute by digit rename alone
- **do_not:** Do not rename EZPE127_F → EZPE217_F by digit similarity without confirming both ReserveTM and slug-length roles
- **Confidence:** 0.95

## LANE_4_P214 — ReserveTM EZPE212_F1 vs pack EZPE212_F2

- **ReserveTM:** `tmfcEZPE212_F1`
- **Extracted from ReserveTM:** `EZPE212_F1`
- **Pass full_eye_ezpe:** `EZPE212_F2` (RUN_DERIVED)
- **Pack has F1:** False · **F2:** True
- **Fullline F1:** `{'Desc': 'EZPE212_F1', 'Sensor_Name': 'EZPE212_F1', 'Timer_Name': 'tmEZPE212_F1', 'Timer_Preset': '5.000', 'Clr_Timer_Name': 'tmfcEZPE212_F1', 'Clr_Timer_Preset': '10.000', 'Error_Name': 'EZPE212_F1', 'Conveyor_Name': 'P212', 'DontFireResponse': 'N', 'Response IO': 'M206', 'Invert': 'N', 'Go Until': 'INVALID', 'ReSound Horn': 'N/A', 'NoGap': 'N', 'Status': 'N', 'Sent': '0', 'FullClearOutput': 'INVALID', 'FullClearACTION': 'N/A', 'FullClearBIT': '0'}`
- **Fullline F2:** `{'Desc': 'EZPE212_F2', 'Sensor_Name': 'EZPE212_F2', 'Timer_Name': 'tmEZPE212_F2', 'Timer_Preset': '5.000', 'Clr_Timer_Name': 'tmfcEZPE212_F2', 'Clr_Timer_Preset': '10.000', 'Error_Name': 'EZPE212_F2', 'Conveyor_Name': 'P214', 'DontFireResponse': 'N', 'Response IO': 'M306', 'Invert': 'N', 'Go Until': 'INVALID', 'ReSound Horn': 'N/A', 'NoGap': 'N', 'Status': 'N', 'Sent': '0', 'FullClearOutput': 'INVALID', 'FullClearACTION': 'N/A', 'FullClearBIT': '0'}`
- **Conveyor F1:** `{'IO_Name': 'EZPE212_F1', 'General_Description': 'FULL EYE DETECTION ON P212', 'Type': 'PHOTOCELL', 'Machine_Name': 'ORNCCP4'}`
- **Conveyor F2:** `{'IO_Name': 'EZPE212_F2', 'General_Description': 'FULL EYE ON P212 DOWNSTREAM OF P308 MERGE', 'Type': 'PHOTOCELL', 'Machine_Name': 'ORNCCP4'}`
- **Pack usage:** RT_IO_Map_NoGapStore: IF EZPE212_F2.Full THEN MRG414_astUNL_SlugBldCtrl[4].rQ1_SlugLength_Q := HMI Lane[4].ReleaseLengthFull ELSE ReleaseLength. Pack role here is slug-release-length selection (no gap-store path).

### RUN hits
- `EZPE212_F1`:
  - `Fullline.asc`.`Desc` (row `EZPE212_F1`)
  - `Fullline.asc`.`Sensor_Name` (row `EZPE212_F1`)
  - `Fullline.asc`.`Error_Name` (row `EZPE212_F1`)
  - `Conveyor.asc`.`IO_Name` (row `EZPE212_F1`)
  - `Errors.asc`.`ErrorName` (row ``)
- `EZPE212_F2`:
  - `Fullline.asc`.`Desc` (row `EZPE212_F2`)
  - `Fullline.asc`.`Sensor_Name` (row `EZPE212_F2`)
  - `Fullline.asc`.`Error_Name` (row `EZPE212_F2`)
  - `Conveyor.asc`.`IO_Name` (row `EZPE212_F2`)
  - `Errors.asc`.`ErrorName` (row ``)
- `tmfcEZPE212_F1`:
  - `SawLane.asc.ORNCCP4`.`ReserveTM` (row `LANE_4_P214`)
  - `Fullline.asc`.`Clr_Timer_Name` (row `EZPE212_F1`)
  - `MergeInputs.asc.ORNCCP4`.`FullClearTimerName` (row `LANE1_P212`)
  - `timemenu.asc`.`Timer_Name` (row ``)
- `tmfcEZPE212_F2`:
  - `Fullline.asc`.`Clr_Timer_Name` (row `EZPE212_F2`)
  - `Trigrset.asc.ORNCCP4`.`loc` (row ``)
  - `Trigrset.asc.ORNCCP4`.`loc3` (row ``)
  - `timemenu.asc`.`Timer_Name` (row ``)
- `tmEZPE212_F1`:
  - `Fullline.asc`.`Timer_Name` (row `EZPE212_F1`)
  - `timemenu.asc`.`Timer_Name` (row ``)
- `tmEZPE212_F2`:
  - `Fullline.asc`.`Timer_Name` (row `EZPE212_F2`)
  - `timemenu.asc`.`Timer_Name` (row ``)
- `P212`:
  - `Fullline.asc`.`Conveyor_Name` (row `EZPE212_F1`)
  - `Conveyor.asc`.`IO_Name` (row `P212`)
  - `Mtrchain.asc`.`Motor_Chained1` (row ``)
- `P214`:
  - `Fullline.asc`.`Conveyor_Name` (row `EZPE212_F2`)
  - `Conveyor.asc`.`IO_Name` (row `P214`)
  - `Mtrchain.asc`.`Motor_Chained1` (row ``)

### Finding

CONFLICT — do not auto-resolve. SawLane LANE_4_P214.ReserveTM=tmfcEZPE212_F1 (explicit reservation timer → EZPE212_F1). Fullline associates EZPE212_F1.Conveyor_Name=P212 and EZPE212_F2.Conveyor_Name=P214. Conveyor descriptions: F1='FULL EYE DETECTION ON P212'; F2='FULL EYE ON P212 DOWNSTREAM OF P308 MERGE'. Errors: F1='LANE FULL AT BIN MOD A ACCUM'; F2='LANE 1/2 FULL AT BIN MOD A ACCUM'. Generic pack declares/uses EZPE212_F2.Full for Lane[4] slug length in RT_IO_Map_NoGapStore. Prior pass fuzzy-mapped F1→F2 (RUN_DERIVED) — ReserveTM identity and pack Full-eye role are not proven to be the same sensor.

### Resolution guidance

- **reserve_timer_symbol:** RUN_EXPLICIT tmfcEZPE212_F1 / EZPE212_F1
- **pack_slug_length_full_eye:** EZPE212_F2 (library)
- **fullline_conveyor_for_F2:** P214 (sawtooth lane conveyor name)
- **fullline_conveyor_for_F1:** P212
- **recommended_audit_resolution:** CONFIGURATION_REQUIRED
- **do_not:** Do not rename F1↔F2 to force pack match; engineer must confirm ReserveTM eye vs slug-length Full eye (may differ)
- **Confidence:** 0.9

## Other lane reserve eyes

- `LANE_0_P219`: ReserveTM=`tmfcEZPE217_F` → `EZPE217_F` (CONFIGURATION REQUIRED); pack_has=False
- `LANE_1_P408`: ReserveTM=`tmfcEZPE408_F` → `EZPE408_F` (RUN_EXPLICIT); pack_has=True
- `LANE_3_P116`: ReserveTM=`tmfcEZPE116_F` → `EZPE116_F` (RUN_EXPLICIT); pack_has=True
- `LANE_4_P214`: ReserveTM=`tmfcEZPE212_F1` → `EZPE212_F2` (RUN_DERIVED); pack_has=True
- `LANE_5_P832`: ReserveTM=`tmfcEZPE832_F` → `EZPE832_F` (RUN_EXPLICIT); pack_has=True

Searched: SawLane, SawMerge, HSSaw*, Fulljam, Fullline, Jamcheck, Jamzones, CombinedJamZones, Conveyor, MergeInputs, Mtrchain, Errors, Logic, Trigrset.

No guessing / no rename-to-match-library performed.
