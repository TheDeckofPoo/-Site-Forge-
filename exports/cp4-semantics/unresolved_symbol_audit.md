# Unresolved / Unmapped Sawtooth Symbol Audit

Generated: `2026-09-12T16:17:54.921607+00:00`
Finished PLC4 used: **False**
Audited: **72** (pass unmapped 69, reserve-eye extras 3)

## Resolution histogram

- `CONFIGURATION_REQUIRED`: **2**
- `ENGINEER_CONFIGURED`: **4**
- `GENERIC_LIBRARY_CONSTANT`: **6**
- `RUN_DERIVED_HIGH_CONFIDENCE`: **1**
- `RUN_EXPLICIT`: **19**
- `UNUSED_FOR_THIS_SITE`: **40**

## Policy

- Prefer RUN table evidence over heuristics
- Do **not** bind by similar tag numbers alone
- Finished PLC4 not consulted

## Symbols

### `EZPE127_F`

- **Datatype:** `PE_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `IF EZPE127_F.Full THEN`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[IF EZPE127_F.Full THEN ]]>`
- **Generic-library role:** lane_or_line_full_eye
- **Likely equipment/function:** Full-eye photoeye (pack leftover if absent from RUN)
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not map to EZPE217_F by digit similarity; Site LANE_0 full eye is EZPE217_F per ReserveTM
- **Confidence:** 0.85
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `EZPE127_F` in scanned RUN Fortna tables
- **Notes:** Gold-pack full eye without RUN device of same name

### `Enable_Merge1_Reserv`

- **Datatype:** `—`
- **Routines:** `Conv_Enc`
- **Instruction/context:**
  - `Conv_Enc`: `XIC(Enable_Merge2_Trk)XIC(Enable_Merge1_Reserv)JSR(RT_CollTrackMain,0);`
- **Generic-library role:** feature_enable_gate
- **Likely equipment/function:** Logic feature gate (not a field device)
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Set TRUE/FALSE per site feature (gap-store vs no-gap-store, reservation enable)
- **Confidence:** 0.85
- **Resolution:** `ENGINEER_CONFIGURED`
- **Evidence:**
  - LIBRARY: Main/feature gate referenced in routines: ['Conv_Enc']
- **Notes:** Pass classified as feature enable — not a RUN field device

### `Enable_Merge2_Trk`

- **Datatype:** `—`
- **Routines:** `Conv_Enc`
- **Instruction/context:**
  - `Conv_Enc`: `XIC(Enable_Merge2_Trk)[XIC(Use_GapStore_Belts) MOV(400,P414_SawMerge_HMI.ClctrSpeed_FPM) ,XIO(Use_GapStore_Belts) MOV(140,P414_SawMerge_HMI.ClctrSpeed_FPM) ];`
  - `Conv_Enc`: `XIC(Enable_Merge2_Trk)XIO(Use_GapStore_Belts)JSR(RT_DeltaDist_NoGapStore,0);`
  - `Conv_Enc`: `XIC(Enable_Merge2_Trk)XIO(Use_GapStore_Belts)JSR(RT_IO_Map_NoGapStore,0);`
- **Generic-library role:** feature_enable_gate
- **Likely equipment/function:** Logic feature gate (not a field device)
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Set TRUE/FALSE per site feature (gap-store vs no-gap-store, reservation enable)
- **Confidence:** 0.85
- **Resolution:** `ENGINEER_CONFIGURED`
- **Evidence:**
  - LIBRARY: Main/feature gate referenced in routines: ['Conv_Enc']
- **Notes:** Pass classified as feature enable — not a RUN field device

### `Enable_hold`

- **Datatype:** `—`
- **Routines:** —
- **Generic-library role:** feature_enable_gate
- **Likely equipment/function:** Logic feature gate (not a field device)
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Set TRUE/FALSE per site feature (gap-store vs no-gap-store, reservation enable)
- **Confidence:** 0.85
- **Resolution:** `ENGINEER_CONFIGURED`
- **Evidence:**
  - LIBRARY: Main/feature gate referenced in routines: []
- **Notes:** Pass classified as feature enable — not a RUN field device

### `MRG422_aoUNL_PT_CnvDeltaDist`

- **Datatype:** `—`
- **Routines:** `RT_DeltaDist_NoGapStore`
- **Instruction/context:**
  - `RT_DeltaDist_NoGapStore`: `AO_CnvDeltaDist(MRG422_aoUNL_PT_CnvDeltaDist[1],`
  - `RT_DeltaDist_NoGapStore`: `AO_CnvDeltaDist(MRG422_aoUNL_PT_CnvDeltaDist[2],`
  - `RT_DeltaDist_NoGapStore`: `AO_CnvDeltaDist(MRG422_aoUNL_PT_CnvDeltaDist[3],`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_astCollPeTrackCal`

- **Datatype:** `—`
- **Routines:** `RT_CollPeTrackCal`
- **Instruction/context:**
  - `RT_CollPeTrackCal`: `// PE offsets will be saved to "MRG422_astCollPeTrackCal[x].diPlsCntSave" and "MRG422_xCollTrackPE_OffsetCaptureArm" gets reset when process is completed`
  - `RT_CollPeTrackCal`: `<![CDATA[// PE offsets will be saved to "MRG422_astCollPeTrackCal[x].diPlsCntSave" and "MRG422_xCollTrackPE_OffsetCaptureArm" gets reset when process is completed]]>`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_astLaneClctrSlotResvCntrl`

- **Datatype:** `—`
- **Routines:** `SR_LaneCntrl`
- **Instruction/context:**
  - `SR_LaneCntrl`: `//Update slot length in "MRG422_astLaneClctrSlotResvCntrl"`
  - `SR_LaneCntrl`: `<![CDATA[ //Update slot length in "MRG422_astLaneClctrSlotResvCntrl"]]>`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_astLanePeTrackCal`

- **Datatype:** `—`
- **Routines:** `RT_CollTrackInit`, `RT_LaneOffsetFind`
- **Instruction/context:**
  - `RT_CollTrackInit`: `//M422_SawMerge_HMI.Lane[12].LaneOffset := MRG422_astLanePeTrackCal[12].diPlsCntSave + diCollPeTrackExitLocation + M422_SawMerge_HMI.Lane[12].LaneOffsetCorr;`
  - `RT_CollTrackInit`: `<![CDATA[//M422_SawMerge_HMI.Lane[12].LaneOffset := MRG422_astLanePeTrackCal[12].diPlsCntSave + diCollPeTrackExitLocation + M422_SawMerge_HMI.Lane[12].LaneOffsetCorr;]]>`
  - `RT_LaneOffsetFind`: `// PE offsets will be saved to "MRG422_astLanePeTrackCal[x].diPlsCntSave" and "MRG422_xLane_OffsetCaptureArm" gets reset when process is completed`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_astUNL_BFR_CnvCtrl`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `//MRG422_astUNL_BFR_CnvCtrl[1].xPE_BlockedEntr := // Not used`
  - `RT_IO_Map_NoGapStore`: `//MRG422_astUNL_BFR_CnvCtrl[1].xPE_BlockedExit := // Not used`
  - `RT_IO_Map_NoGapStore`: `//MRG422_astUNL_BFR_CnvCtrl[1].xCnvFaulted := M824_Conv.Flt.Flt;`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_astUNL_GPR_CnvCtrl`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG422_astUNL_GPR_CnvCtrl[1].xCnvRunning := M824_Conv.Running; // Gapper Conveyor Running Status`
  - `RT_IO_Map_NoGapStore`: `M824_Conv.Spd := MRG422_astUNL_GPR_CnvCtrl[1].rDesireSpeed_IPS * 5 / 1.5; //Gear ratio = 1.5`
  - `RT_IO_Map_NoGapStore`: `//MRG422_astUNL_GPR_CnvCtrl[1].xCnvFaulted := M824_Conv.Flt.Flt;`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_astUNL_PT_CnvCtrl`

- **Datatype:** `—`
- **Routines:** `RT_DeltaDist_NoGapStore`
- **Instruction/context:**
  - `RT_DeltaDist_NoGapStore`: `MRG422_astUNL_PT_CnvCtrl[1].rPrevSpd := MRG422_astUNL_PT_CnvCtrl[1].rCurrSpd;`
  - `RT_DeltaDist_NoGapStore`: `MRG422_astUNL_PT_CnvCtrl[1].rCurrSpd := 225/5;`
  - `RT_DeltaDist_NoGapStore`: `MRG422_astUNL_PT_CnvCtrl[1].rCurrSpd,`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_astUNL_Q1_CnvCtrl`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG422_astUNL_Q1_CnvCtrl[1].xCnvRunning := P2501_Conv.Running; // Gap&Store Conveyor Running Status`
  - `RT_IO_Map_NoGapStore`: `P2501_Conv.Spd := MRG422_astUNL_Q1_CnvCtrl[1].rDesireSpeed_IPS * 5; // Commanded Speed to run`
  - `RT_IO_Map_NoGapStore`: `//MRG422_astUNL_Q1_CnvCtrl[1].xCnvFaulted := P2501_Conv.Flt.Flt;`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_astUNL_Q2_CnvCtrl`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `P410_Conv.Spd := 225; //MRG422_astUNL_Q2_CnvCtrl[2].rDesireSpeed_IPS * 5 / 1.5; //1.5= Gear Ratio on gapper;`
  - `RT_IO_Map_NoGapStore`: `P118_Conv.Spd := 225; //MRG422_astUNL_Q2_CnvCtrl[3].rDesireSpeed_IPS * 5 / 1.5; //1.5= Gear Ratio on gapper;`
  - `RT_IO_Map_NoGapStore`: `P216_Conv.Spd := 225; //MRG422_astUNL_Q2_CnvCtrl[4].rDesireSpeed_IPS * 5 / 1.5; //1.5= Gear Ratio on gapper;`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_astUNL_SlugBldCtrl`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `//P422_SawMerge_HMI.Lane[MRG422_diHMI_LaneIdx].Disabled := MRG422_astUNL_SlugBldCtrl[MRG422_diHMI_LaneIdx].xLaneDisabled; //M422_SawMerge_HMI.Lane[MRG422_diHMI_LaneIdx].Disabled`
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_SlugBldCtrl[MRG414_diHMI_LaneIdx].xLaneFlowControlActive := 0; //MRG422_astUNL_SlugBldCtrl[MRG422_diHMI_LaneIdx].xLaneRunEnable AND NOT MRG422_astUNL_SlugBldCtrl[MRG422_diHMI_LaneIdx].xSlugReleasing_Q2;`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[//P422_SawMerge_HMI.Lane[MRG422_diHMI_LaneIdx].Disabled := MRG422_astUNL_SlugBldCtrl[MRG422_diHMI_LaneIdx].xLaneDisabled; //M422_SawMerge_HMI.Lane[MRG422_diHMI_LaneIdx].Disabled]]>`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_diHMI_LaneIdx`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `P414_SawMerge_HMI.Lane[MRG414_diHMI_LaneIdx].AcceptedSlugLength := MRG414_astLaneClctrSlotResvStat[MRG414_diHMI_LaneIdx].rSlotSizeInch; //M422_SawMerge_HMI.Lane[MRG422_diHMI_LaneIdx].AcceptedSlugLength`
  - `RT_IO_Map_NoGapStore`: `P414_SawMerge_HMI.Lane[MRG414_diHMI_LaneIdx].ReservedSlugLength := MRG414_astLaneClctrSlotResvStat[MRG414_diHMI_LaneIdx].rSlotSizeInch; //M422_SawMerge_HMI.Lane[MRG422_diHMI_LaneIdx].ReservedSlugLength`
  - `RT_IO_Map_NoGapStore`: `P414_SawMerge_HMI.Lane[MRG414_diHMI_LaneIdx].SlugTrackID := MRG414_astLaneClctrSlotResvStat[MRG414_diHMI_LaneIdx].diLanePkgSeqId; //M422_SawMerge_HMI.Lane[MRG422_diHMI_LaneIdx].SlugTrackID`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_diNoCartonGap`

- **Datatype:** `—`
- **Routines:** `SR_LaneCntrl`
- **Instruction/context:**
  - `SR_LaneCntrl`: `MRG414_diCollSlotDelStartIdx := MRG414_stLaneClctrSlotResvCntrl.diSlotStartLoc + MRG414_diCollUsableSlotSize; //MRG422_stLaneClctrSlotResvCntrl.diResvLaneLoc - MRG422_diNoCartonGap + MRG422_stUNL_SlugBldCfgTmp1.diQ2_SlugGapAdder;`
  - `SR_LaneCntrl`: ` MRG414_diCollUsableSlotSize; //MRG422_stLaneClctrSlotResvCntrl.diResvLaneLoc - MRG422_diNoCartonGap + MRG422_stUNL_SlugBldCfgTmp1.diQ2_SlugGapAdder;]]>`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_rFastTaskDeltaMilliSecs`

- **Datatype:** `—`
- **Routines:** `RT_DeltaDist_NoGapStore`
- **Instruction/context:**
  - `RT_DeltaDist_NoGapStore`: `MRG422_rFastTaskDeltaMilliSecs,`
  - `RT_DeltaDist_NoGapStore`: `MRG422_rFastTaskDeltaMilliSecs,`
  - `RT_DeltaDist_NoGapStore`: `MRG422_rFastTaskDeltaMilliSecs,`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_stLaneClctrSlotResvCntrl`

- **Datatype:** `—`
- **Routines:** `SR_LaneCntrl`
- **Instruction/context:**
  - `SR_LaneCntrl`: `MRG414_diCollSlotDelStartIdx := MRG414_stLaneClctrSlotResvCntrl.diSlotStartLoc + MRG414_diCollUsableSlotSize; //MRG422_stLaneClctrSlotResvCntrl.diResvLaneLoc - MRG422_diNoCartonGap + MRG422_stUNL_SlugBldCfgTmp1.diQ2_SlugGapAdder;`
  - `SR_LaneCntrl`: `MRG414_stLaneClctrSlotResvCntrl.diSlotStartLoc + MRG414_diCollUsableSlotSize; //MRG422_stLaneClctrSlotResvCntrl.diResvLaneLoc - MRG422_diNoCartonGap + MRG422_stUNL_SlugBldCfgTmp1.diQ2_SlugGapAdder;]]>`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_stUNL_Q2_CnvCtrl`

- **Datatype:** `—`
- **Routines:** `SR_LaneCntrl`
- **Instruction/context:**
  - `SR_LaneCntrl`: `IF MRG414_stUNL_SlugBldCtrlTmp1.xSlugAccepted_Q2 THEN //RJ modified //org-> stUNL_SlugBldCtrl.xSlugAccepted_Q2 THEN AND (MRG422_stUNL_Q2_CnvCtrl.rCurrSpd <= 0.0)`
  - `SR_LaneCntrl`: `<![CDATA[IF MRG414_stUNL_SlugBldCtrlTmp1.xSlugAccepted_Q2 THEN //RJ modified //org-> stUNL_SlugBldCtrl.xSlugAccepted_Q2 THEN AND (MRG422_stUNL_Q2_CnvCtrl.rCurrSpd <= 0.0)]]>`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_stUNL_SlugBldCfgTmp1`

- **Datatype:** `—`
- **Routines:** `SR_LaneCntrl`
- **Instruction/context:**
  - `SR_LaneCntrl`: `MRG414_diCollSlotDelStartIdx := MRG414_stLaneClctrSlotResvCntrl.diSlotStartLoc + MRG414_diCollUsableSlotSize; //MRG422_stLaneClctrSlotResvCntrl.diResvLaneLoc - MRG422_diNoCartonGap + MRG422_stUNL_SlugBldCfgTmp1.diQ2_SlugGapAdder;`
  - `SR_LaneCntrl`: `tSize; //MRG422_stLaneClctrSlotResvCntrl.diResvLaneLoc - MRG422_diNoCartonGap + MRG422_stUNL_SlugBldCfgTmp1.diQ2_SlugGapAdder;]]>`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_xCollTrackPE_OffsetCaptureArm`

- **Datatype:** `—`
- **Routines:** `RT_CollPeTrackCal`
- **Instruction/context:**
  - `RT_CollPeTrackCal`: `// First enable "MRG422_xLaneClctrPeCalibrate" then "MRG422_xCollTrackPE_OffsetCaptureArm"`
  - `RT_CollPeTrackCal`: `// PE offsets will be saved to "MRG422_astCollPeTrackCal[x].diPlsCntSave" and "MRG422_xCollTrackPE_OffsetCaptureArm" gets reset when process is completed`
  - `RT_CollPeTrackCal`: `<![CDATA[// First enable "MRG422_xLaneClctrPeCalibrate" then "MRG422_xCollTrackPE_OffsetCaptureArm"]]>`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_xLaneClctrPeCalibrate`

- **Datatype:** `—`
- **Routines:** `RT_CollPeTrackCal`, `RT_LaneOffsetFind`
- **Instruction/context:**
  - `RT_CollPeTrackCal`: `// First enable "MRG422_xLaneClctrPeCalibrate" then "MRG422_xCollTrackPE_OffsetCaptureArm"`
  - `RT_CollPeTrackCal`: `<![CDATA[// First enable "MRG422_xLaneClctrPeCalibrate" then "MRG422_xCollTrackPE_OffsetCaptureArm"]]>`
  - `RT_LaneOffsetFind`: `// First enable "MRG422_xLaneClctrPeCalibrate" then "MRG422_xLane_OffsetCaptureArm"`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG422_xLane_OffsetCaptureArm`

- **Datatype:** `—`
- **Routines:** `RT_LaneOffsetFind`
- **Instruction/context:**
  - `RT_LaneOffsetFind`: `// First enable "MRG422_xLaneClctrPeCalibrate" then "MRG422_xLane_OffsetCaptureArm"`
  - `RT_LaneOffsetFind`: `// PE offsets will be saved to "MRG422_astLanePeTrackCal[x].diPlsCntSave" and "MRG422_xLane_OffsetCaptureArm" gets reset when process is completed`
  - `RT_LaneOffsetFind`: `<![CDATA[// First enable "MRG422_xLaneClctrPeCalibrate" then "MRG422_xLane_OffsetCaptureArm"]]>`
- **Generic-library role:** gapstore_or_unload_path_merge_struct
- **Likely equipment/function:** Gold-pack gap-store / unload merge family (MRG422) — site collector is MRG414 family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Do not rename MRG422→MRG414 by digit heuristic; Leave gated behind Use_GapStore_Belts / Enable_* or omit from site emit
- **Confidence:** 0.8
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - LIBRARY: MRG422_* appears beside site collector MRG414_* in generic pack (gap-store/unload path)
  - PASS: Site SawMerge.MotorIO=VFD414_AUX → collector family MRG414, not 422
- **Notes:** Digit-similarity to other merge numbers is NOT accepted as binding evidence

### `MRG500_adiCollTrkArray_Freeze`

- **Datatype:** `—`
- **Routines:** `Conv_Enc`
- **Instruction/context:**
  - `Conv_Enc`: `//////////////////////////////////////// Debug: Freeze the Track Array Data to "MRG500_adiCollTrkArray_Freeze" "MRG500_astLaneClctrSlotResvCntrl_Freeze" ///////////////////////////////////////////////////////////////////////////////////////`
- **Generic-library role:** calibration_freeze_or_capture_helper
- **Likely equipment/function:** Gold-pack calibration/freeze helper family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Keep as pack helper tags unless site provides alternate calibration workflow
- **Confidence:** 0.75
- **Resolution:** `GENERIC_LIBRARY_CONSTANT`
- **Evidence:**
  - LIBRARY: MRG500_* used as calibration/freeze capture helpers in pack comments/routines

### `MRG500_astCollPeTrackCal`

- **Datatype:** `—`
- **Routines:** `Conv_Enc`
- **Instruction/context:**
  - `Conv_Enc`: `rate" then "MRG500_xCollTrackPE_OffsetCaptureArm". PE offsets will be saved to "MRG500_astCollPeTrackCal[x].diPlsCntSave" and "MRG500_xCollTrackPE_OffsetCaptureArm" gets reset when process is completed. /////////////////////////////////////`
  - `Conv_Enc`: `rate" then "MRG500_xCollTrackPE_OffsetCaptureArm". PE offsets will be saved to "MRG500_astCollPeTrackCal[x].diPlsCntSave" and "MRG500_xCollTrackPE_OffsetCaptureArm" gets reset when process is completed. /////////////////////////////////////`
- **Generic-library role:** calibration_freeze_or_capture_helper
- **Likely equipment/function:** Gold-pack calibration/freeze helper family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Keep as pack helper tags unless site provides alternate calibration workflow
- **Confidence:** 0.75
- **Resolution:** `GENERIC_LIBRARY_CONSTANT`
- **Evidence:**
  - LIBRARY: MRG500_* used as calibration/freeze capture helpers in pack comments/routines

### `MRG500_astLaneClctrSlotResvCntrl_Freeze`

- **Datatype:** `—`
- **Routines:** `Conv_Enc`
- **Instruction/context:**
  - `Conv_Enc`: `//////// Debug: Freeze the Track Array Data to "MRG500_adiCollTrkArray_Freeze" "MRG500_astLaneClctrSlotResvCntrl_Freeze" ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////`
- **Generic-library role:** calibration_freeze_or_capture_helper
- **Likely equipment/function:** Gold-pack calibration/freeze helper family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Keep as pack helper tags unless site provides alternate calibration workflow
- **Confidence:** 0.75
- **Resolution:** `GENERIC_LIBRARY_CONSTANT`
- **Evidence:**
  - LIBRARY: MRG500_* used as calibration/freeze capture helpers in pack comments/routines

### `MRG500_stCollLaneMrgCapture`

- **Datatype:** `—`
- **Routines:** `Conv_Enc`
- **Instruction/context:**
  - `Conv_Enc`: `eservation against actual slug position Refer to "RT_CollLaneMergeCapture" and (MRG500_stCollLaneMrgCapture.diLaneId, MRG500_stCollLaneMrgCapture.diDelta) /////////////////////////////////////////////////////////////////////////////////////`
- **Generic-library role:** calibration_freeze_or_capture_helper
- **Likely equipment/function:** Gold-pack calibration/freeze helper family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Keep as pack helper tags unless site provides alternate calibration workflow
- **Confidence:** 0.75
- **Resolution:** `GENERIC_LIBRARY_CONSTANT`
- **Evidence:**
  - LIBRARY: MRG500_* used as calibration/freeze capture helpers in pack comments/routines

### `MRG500_xCollTrackPE_OffsetCaptureArm`

- **Datatype:** `—`
- **Routines:** `Conv_Enc`
- **Instruction/context:**
  - `Conv_Enc`: `Refer to "RT_CollPeTrackCal". First enable "MRG500_xLaneClctrPeCalibrate" then "MRG500_xCollTrackPE_OffsetCaptureArm". PE offsets will be saved to "MRG500_astCollPeTrackCal[x].diPlsCntSave" and "MRG500_xCollTrackPE_OffsetCaptureArm" gets re`
  - `Conv_Enc`: `Refer to "RT_CollPeTrackCal". First enable "MRG500_xLaneClctrPeCalibrate" then "MRG500_xCollTrackPE_OffsetCaptureArm". PE offsets will be saved to "MRG500_astCollPeTrackCal[x].diPlsCntSave" and "MRG500_xCollTrackPE_OffsetCaptureArm" gets re`
- **Generic-library role:** calibration_freeze_or_capture_helper
- **Likely equipment/function:** Gold-pack calibration/freeze helper family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Keep as pack helper tags unless site provides alternate calibration workflow
- **Confidence:** 0.75
- **Resolution:** `GENERIC_LIBRARY_CONSTANT`
- **Evidence:**
  - LIBRARY: MRG500_* used as calibration/freeze capture helpers in pack comments/routines

### `MRG500_xLaneClctrPeCalibrate`

- **Datatype:** `—`
- **Routines:** `Conv_Enc`
- **Instruction/context:**
  - `Conv_Enc`: `//// Calibrate PEs on the Collector Refer to "RT_CollPeTrackCal". First enable "MRG500_xLaneClctrPeCalibrate" then "MRG500_xCollTrackPE_OffsetCaptureArm". PE offsets will be saved to "MRG500_astCollPeTrackCal[x].diPlsCntSave" and "MRG500_xC`
  - `Conv_Enc`: `//// Calibrate PEs on the Collector Refer to "RT_CollPeTrackCal". First enable "MRG500_xLaneClctrPeCalibrate" then "MRG500_xCollTrackPE_OffsetCaptureArm". PE offsets will be saved to "MRG500_astCollPeTrackCal[x].diPlsCntSave" and "MRG500_xC`
- **Generic-library role:** calibration_freeze_or_capture_helper
- **Likely equipment/function:** Gold-pack calibration/freeze helper family
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Keep as pack helper tags unless site provides alternate calibration workflow
- **Confidence:** 0.75
- **Resolution:** `GENERIC_LIBRARY_CONSTANT`
- **Evidence:**
  - LIBRARY: MRG500_* used as calibration/freeze capture helpers in pack comments/routines

### `P118_Conv`

- **Datatype:** `Conv_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_PT_CnvCtrl[3].xCnvRunning := P118_Conv.Running;`
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_Q2_CnvCtrl[3].xCnvRunning := P118_Conv.Running;`
  - `RT_IO_Map_NoGapStore`: `P118_Conv.Spd := 225; //MRG422_astUNL_Q2_CnvCtrl[3].rDesireSpeed_IPS * 5 / 1.5; //1.5= Gear Ratio on gapper;`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=P118)
- **Candidate RUN table(s)/field(s):**
  - `Conveyor.asc`.`IO_Name` = `P118` (row `P118`)
  - `Mtrchain.asc`.`Motor_Chained1` = `P118` (row ``)
- **Candidate binding(s):** Pack `P118_Conv` ↔ RUN conveyor `P118` (present in RUN; confirm sawtooth role)
- **Confidence:** 0.9
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - DISCOVERY: Token related to discovery inventory
  - RUN_EXPLICIT: Conveyor/token `P118` exists in RUN; pack UDT is `P118_Conv`
  - RUN `Conveyor.asc`.`IO_Name` = `P118` (row `P118`)
  - RUN `Mtrchain.asc`.`Motor_Chained1` = `P118` (row ``)

### `P120_Conv`

- **Datatype:** `Conv_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_MRG_CnvCtrl[3].xCnvRunning := P120_Conv.Running;`
  - `RT_IO_Map_NoGapStore`: `P120_Conv.Spd := MRG414_astUNL_MRG_CnvCtrl[3].rDesireSpeed_FPM;`
  - `RT_IO_Map_NoGapStore`: `P120_Conv.PI.Run_Hold := NOT (MRG414_astUNL_MRG_CnvCtrl[3].xInterlock_OUT AND MRG414_astUNL_MRG_CnvCtrl[3].rDesireSpeed_IPS > 0);`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=P120)
- **Candidate RUN table(s)/field(s):**
  - `Jamcheck.asc`.`Conveyor_Name` = `P120` (row `PE414B_J`)
  - `Conveyor.asc`.`IO_Name` = `P120` (row `P120`)
  - `Mtrchain.asc`.`Motor_Chained1` = `P120` (row ``)
- **Candidate binding(s):** Pack `P120_Conv` ↔ RUN conveyor `P120` (present in RUN; confirm sawtooth role)
- **Confidence:** 0.9
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - DISCOVERY: Token related to discovery inventory
  - RUN_EXPLICIT: Conveyor/token `P120` exists in RUN; pack UDT is `P120_Conv`
  - RUN `Jamcheck.asc`.`Conveyor_Name` = `P120` (row `PE414B_J`)
  - RUN `Conveyor.asc`.`IO_Name` = `P120` (row `P120`)
  - RUN `Mtrchain.asc`.`Motor_Chained1` = `P120` (row ``)

### `P1491_Conv`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG422_astUNL_Q1_CnvCtrl[4].xCnvRunning := P1491_Conv.Running;`
  - `RT_IO_Map_NoGapStore`: `P1491_Conv.Spd := MRG422_astUNL_Q1_CnvCtrl[4].rDesireSpeed_IPS * 5;`
  - `RT_IO_Map_NoGapStore`: `//MRG422_astUNL_Q1_CnvCtrl[4].xCnvFaulted := P1491_Conv.Flt.Flt;`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** Conveyor UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `P1491_Conv` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `P1492_Conv`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_SlugBldCtrl[4].xLaneMaintMode := P218_Conv.HMI.Manual OR P216_Conv.HMI.Manual; //If any conveyor in Manual Mode // OR P1492_Conv.HMI.Manual OR P1491_Conv.HMI.Manual`
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_SlugBldCtrl[5].xLaneMaintMode := P836_Conv.HMI.Manual OR P834_Conv.HMI.Manual; //If any conveyor in Manual Mode // OR P1492_Conv.HMI.Manual OR P1491_Conv.HMI.Manual`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_SlugBldCtrl[4].xLaneMaintMode := P218_Conv.HMI.Manual OR P216_Conv.HMI.Manual; //If any conveyor in Manual Mode // OR P1492_Conv.HMI.Manual OR P1491_Conv.HMI.Manual]]>`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** Conveyor UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `P1492_Conv` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `P216_Conv`

- **Datatype:** `Conv_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_PT_CnvCtrl[4].xCnvRunning := P216_Conv.Running;`
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_Q2_CnvCtrl[4].xCnvRunning := P216_Conv.Running;`
  - `RT_IO_Map_NoGapStore`: `P216_Conv.Spd := 225; //MRG422_astUNL_Q2_CnvCtrl[4].rDesireSpeed_IPS * 5 / 1.5; //1.5= Gear Ratio on gapper;`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=P216)
- **Candidate RUN table(s)/field(s):**
  - `Conveyor.asc`.`IO_Name` = `P216` (row `P216`)
  - `Mtrchain.asc`.`Motor_Chained1` = `P216` (row ``)
- **Candidate binding(s):** Pack `P216_Conv` ↔ RUN conveyor `P216` (present in RUN; confirm sawtooth role)
- **Confidence:** 0.9
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - DISCOVERY: Token related to discovery inventory
  - RUN_EXPLICIT: Conveyor/token `P216` exists in RUN; pack UDT is `P216_Conv`
  - RUN `Conveyor.asc`.`IO_Name` = `P216` (row `P216`)
  - RUN `Mtrchain.asc`.`Motor_Chained1` = `P216` (row ``)

### `P218_Conv`

- **Datatype:** `Conv_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_MRG_CnvCtrl[4].xCnvRunning := P218_Conv.Running;`
  - `RT_IO_Map_NoGapStore`: `P218_Conv.Spd := MRG414_astUNL_MRG_CnvCtrl[4].rDesireSpeed_FPM;`
  - `RT_IO_Map_NoGapStore`: `P218_Conv.PI.Run_Hold := NOT (MRG414_astUNL_MRG_CnvCtrl[4].xInterlock_OUT AND MRG414_astUNL_MRG_CnvCtrl[4].rDesireSpeed_IPS > 0);`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=P218)
- **Candidate RUN table(s)/field(s):**
  - `Jamcheck.asc`.`Conveyor_Name` = `P218` (row `PE414C_J`)
  - `Conveyor.asc`.`IO_Name` = `P218` (row `P218`)
  - `Mtrchain.asc`.`Motor_Chained1` = `P218` (row ``)
- **Candidate binding(s):** Pack `P218_Conv` ↔ RUN conveyor `P218` (present in RUN; confirm sawtooth role)
- **Confidence:** 0.9
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - DISCOVERY: Token related to discovery inventory
  - RUN_EXPLICIT: Conveyor/token `P218` exists in RUN; pack UDT is `P218_Conv`
  - RUN `Jamcheck.asc`.`Conveyor_Name` = `P218` (row `PE414C_J`)
  - RUN `Conveyor.asc`.`IO_Name` = `P218` (row `P218`)
  - RUN `Mtrchain.asc`.`Motor_Chained1` = `P218` (row ``)

### `P219A_Conv`

- **Datatype:** `Conv_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_MRG_CnvCtrl[1].xCnvRunning := P219A_Conv.Running; // Spur/Inject Conveyor Running Status`
  - `RT_IO_Map_NoGapStore`: `P219A_Conv.Spd := MRG414_astUNL_MRG_CnvCtrl[1].rDesireSpeed_FPM; // Commanded Speed to run`
  - `RT_IO_Map_NoGapStore`: `P219A_Conv.PI.Run_Hold := NOT (MRG414_astUNL_MRG_CnvCtrl[1].xInterlock_OUT AND MRG414_astUNL_MRG_CnvCtrl[1].rDesireSpeed_IPS > 0);`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=P219A)
- **Candidate RUN table(s)/field(s):**
  - `Jamcheck.asc`.`Conveyor_Name` = `P219A` (row `PE219A_J`)
  - `Conveyor.asc`.`IO_Name` = `P219A` (row `P219A`)
  - `Mtrchain.asc`.`Motor_Chained1` = `P219A` (row ``)
- **Candidate binding(s):** Pack `P219A_Conv` ↔ RUN conveyor `P219A` (present in RUN; confirm sawtooth role)
- **Confidence:** 0.9
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - DISCOVERY: Token related to discovery inventory
  - RUN_EXPLICIT: Conveyor/token `P219A` exists in RUN; pack UDT is `P219A_Conv`
  - RUN `Jamcheck.asc`.`Conveyor_Name` = `P219A` (row `PE219A_J`)
  - RUN `Conveyor.asc`.`IO_Name` = `P219A` (row `P219A`)
  - RUN `Mtrchain.asc`.`Motor_Chained1` = `P219A` (row ``)

### `P2426_Conv`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_SlugBldCtrl[1].xLaneMaintMode := P219A_Conv.HMI.Manual OR P219_Conv.HMI.Manual; //If any conveyor in Manual Mode // OR P2426_Conv.HMI.Manual OR P2501_Conv.HMI.Manual`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_SlugBldCtrl[1].xLaneMaintMode := P219A_Conv.HMI.Manual OR P219_Conv.HMI.Manual; //If any conveyor in Manual Mode // OR P2426_Conv.HMI.Manual OR P2501_Conv.HMI.Manual]]>`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** Conveyor UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `P2426_Conv` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `P2501_Conv`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG422_astUNL_Q1_CnvCtrl[1].xCnvRunning := P2501_Conv.Running; // Gap&Store Conveyor Running Status`
  - `RT_IO_Map_NoGapStore`: `P2501_Conv.Spd := MRG422_astUNL_Q1_CnvCtrl[1].rDesireSpeed_IPS * 5; // Commanded Speed to run`
  - `RT_IO_Map_NoGapStore`: `//MRG422_astUNL_Q1_CnvCtrl[1].xCnvFaulted := P2501_Conv.Flt.Flt;`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** Conveyor UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `P2501_Conv` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `P3451_Conv`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `//MRG422_astUNL_Q1_CnvCtrl[2].xCnvFaulted := P3451_Conv.Flt.Flt;`
  - `RT_IO_Map_NoGapStore`: `//MRG422_astUNL_Q1_CnvCtrl[2].xCnvRestartReq := NOT P3451_Conv.RestartTmr_DN;`
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_SlugBldCtrl[2].xLaneMaintMode := P412_Conv.HMI.Manual OR P410_Conv.HMI.Manual; //If any conveyor in Manual Mode // OR P3452_Conv.HMI.Manual OR P3451_Conv.HMI.Manual`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** Conveyor UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `P3451_Conv` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `P3452_Conv`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_SlugBldCtrl[2].xLaneMaintMode := P412_Conv.HMI.Manual OR P410_Conv.HMI.Manual; //If any conveyor in Manual Mode // OR P3452_Conv.HMI.Manual OR P3451_Conv.HMI.Manual`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_SlugBldCtrl[2].xLaneMaintMode := P412_Conv.HMI.Manual OR P410_Conv.HMI.Manual; //If any conveyor in Manual Mode // OR P3452_Conv.HMI.Manual OR P3451_Conv.HMI.Manual]]>`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** Conveyor UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `P3452_Conv` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `P410_Conv`

- **Datatype:** `Conv_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_PT_CnvCtrl[2].xCnvRunning := P410_Conv.Running;`
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_Q2_CnvCtrl[2].xCnvRunning := P410_Conv.Running;`
  - `RT_IO_Map_NoGapStore`: `P410_Conv.Spd := 225; //MRG422_astUNL_Q2_CnvCtrl[2].rDesireSpeed_IPS * 5 / 1.5; //1.5= Gear Ratio on gapper;`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=P410)
- **Candidate RUN table(s)/field(s):**
  - `Conveyor.asc`.`IO_Name` = `P410` (row `P410`)
  - `Mtrchain.asc`.`Motor_Chained1` = `P410` (row ``)
- **Candidate binding(s):** Pack `P410_Conv` ↔ RUN conveyor `P410` (present in RUN; confirm sawtooth role)
- **Confidence:** 0.9
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - DISCOVERY: Token related to discovery inventory
  - RUN_EXPLICIT: Conveyor/token `P410` exists in RUN; pack UDT is `P410_Conv`
  - RUN `Conveyor.asc`.`IO_Name` = `P410` (row `P410`)
  - RUN `Mtrchain.asc`.`Motor_Chained1` = `P410` (row ``)

### `P412_Conv`

- **Datatype:** `Conv_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_MRG_CnvCtrl[2].xCnvRunning := P412_Conv.Running;`
  - `RT_IO_Map_NoGapStore`: `P412_Conv.Spd := MRG414_astUNL_MRG_CnvCtrl[2].rDesireSpeed_FPM;`
  - `RT_IO_Map_NoGapStore`: `P412_Conv.PI.Run_Hold := NOT (MRG414_astUNL_MRG_CnvCtrl[2].xInterlock_OUT AND MRG414_astUNL_MRG_CnvCtrl[2].rDesireSpeed_IPS > 0);`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=P412)
- **Candidate RUN table(s)/field(s):**
  - `Jamcheck.asc`.`Conveyor_Name` = `P412` (row `PE414A_J`)
  - `Conveyor.asc`.`IO_Name` = `P412` (row `P412`)
  - `Mtrchain.asc`.`Motor_Chained1` = `P412` (row ``)
- **Candidate binding(s):** Pack `P412_Conv` ↔ RUN conveyor `P412` (present in RUN; confirm sawtooth role)
- **Confidence:** 0.9
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - DISCOVERY: Token related to discovery inventory
  - RUN_EXPLICIT: Conveyor/token `P412` exists in RUN; pack UDT is `P412_Conv`
  - RUN `Jamcheck.asc`.`Conveyor_Name` = `P412` (row `PE414A_J`)
  - RUN `Conveyor.asc`.`IO_Name` = `P412` (row `P412`)
  - RUN `Mtrchain.asc`.`Motor_Chained1` = `P412` (row ``)

### `P4131_Conv`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `//MRG422_astUNL_Q1_CnvCtrl[3].xCnvFaulted := P4131_Conv.Flt.Flt;`
  - `RT_IO_Map_NoGapStore`: `//MRG422_astUNL_Q1_CnvCtrl[3].xCnvRestartReq := NOT P4131_Conv.RestartTmr_DN;`
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_SlugBldCtrl[3].xLaneMaintMode := P120_Conv.HMI.Manual OR P118_Conv.HMI.Manual; //If any conveyor in Manual Mode // OR P4132_Conv.HMI.Manual OR P4131_Conv.HMI.Manual`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** Conveyor UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `P4131_Conv` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `P4132_Conv`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_SlugBldCtrl[3].xLaneMaintMode := P120_Conv.HMI.Manual OR P118_Conv.HMI.Manual; //If any conveyor in Manual Mode // OR P4132_Conv.HMI.Manual OR P4131_Conv.HMI.Manual`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_SlugBldCtrl[3].xLaneMaintMode := P120_Conv.HMI.Manual OR P118_Conv.HMI.Manual; //If any conveyor in Manual Mode // OR P4132_Conv.HMI.Manual OR P4131_Conv.HMI.Manual]]>`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** Conveyor UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `P4132_Conv` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `P418_Conv`

- **Datatype:** `Conv_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `P418_Conv.Spd := MRG414_stCollTrkSysCfg.rClctrSpd_FPM;`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[P418_Conv.Spd := MRG414_stCollTrkSysCfg.rClctrSpd_FPM;]]>`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=P418)
- **Candidate RUN table(s)/field(s):**
  - `Fullline.asc`.`Conveyor_Name` = `P418` (row `EZPE418_F`)
  - `Conveyor.asc`.`IO_Name` = `P418` (row `P418`)
  - `Mtrchain.asc`.`Motor_Chained1` = `P418` (row ``)
- **Candidate binding(s):** Pack `P418_Conv` ↔ RUN conveyor `P418` (present in RUN; confirm sawtooth role)
- **Confidence:** 0.9
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - DISCOVERY: Token related to discovery inventory
  - RUN_EXPLICIT: Conveyor/token `P418` exists in RUN; pack UDT is `P418_Conv`
  - RUN `Fullline.asc`.`Conveyor_Name` = `P418` (row `EZPE418_F`)
  - RUN `Conveyor.asc`.`IO_Name` = `P418` (row `P418`)
  - RUN `Mtrchain.asc`.`Motor_Chained1` = `P418` (row ``)

### `P422_SawMerge_HMI`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `//P422_SawMerge_HMI.Lane[MRG422_diHMI_LaneIdx].Disabled := MRG422_astUNL_SlugBldCtrl[MRG422_diHMI_LaneIdx].xLaneDisabled; //M422_SawMerge_HMI.Lane[MRG422_diHMI_LaneIdx].Disabled`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[//P422_SawMerge_HMI.Lane[MRG422_diHMI_LaneIdx].Disabled := MRG422_astUNL_SlugBldCtrl[MRG422_diHMI_LaneIdx].xLaneDisabled; //M422_SawMerge_HMI.Lane[MRG422_diHMI_LaneIdx].Disabled]]>`
- **Generic-library role:** sawtooth_hmi_faceplate
- **Likely equipment/function:** Unknown / pack-internal
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Relate to discovery token family for `P422_SawMerge_HMI`
- **Confidence:** 0.75
- **Resolution:** `RUN_DERIVED_HIGH_CONFIDENCE`
- **Evidence:**
  - DISCOVERY: Token related to discovery inventory

### `P834_Conv`

- **Datatype:** `Conv_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_PT_CnvCtrl[5].xCnvRunning := P834_Conv.Running;`
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_Q2_CnvCtrl[5].xCnvRunning := P834_Conv.Running;`
  - `RT_IO_Map_NoGapStore`: `P834_Conv.Spd := 225; //MRG422_astUNL_Q2_CnvCtrl[5].rDesireSpeed_IPS * 5 / 1.5; //1.5= Gear Ratio on gapper;`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=P834)
- **Candidate RUN table(s)/field(s):**
  - `Conveyor.asc`.`IO_Name` = `P834` (row `P834`)
  - `Mtrchain.asc`.`Motor_Chained1` = `P834` (row ``)
- **Candidate binding(s):** Pack `P834_Conv` ↔ RUN conveyor `P834` (present in RUN; confirm sawtooth role)
- **Confidence:** 0.9
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - DISCOVERY: Token related to discovery inventory
  - RUN_EXPLICIT: Conveyor/token `P834` exists in RUN; pack UDT is `P834_Conv`
  - RUN `Conveyor.asc`.`IO_Name` = `P834` (row `P834`)
  - RUN `Mtrchain.asc`.`Motor_Chained1` = `P834` (row ``)

### `P836_Conv`

- **Datatype:** `Conv_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_MRG_CnvCtrl[5].xCnvRunning := P836_Conv.Running;`
  - `RT_IO_Map_NoGapStore`: `P836_Conv.Spd := MRG414_astUNL_MRG_CnvCtrl[5].rDesireSpeed_FPM;`
  - `RT_IO_Map_NoGapStore`: `P836_Conv.PI.Run_Hold := NOT (MRG414_astUNL_MRG_CnvCtrl[5].xInterlock_OUT AND MRG414_astUNL_MRG_CnvCtrl[5].rDesireSpeed_IPS > 0);`
- **Generic-library role:** conveyor_udt
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=P836)
- **Candidate RUN table(s)/field(s):**
  - `Jamcheck.asc`.`Conveyor_Name` = `P836` (row `PE414D_J`)
  - `Conveyor.asc`.`IO_Name` = `P836` (row `P836`)
  - `Mtrchain.asc`.`Motor_Chained1` = `P836` (row ``)
- **Candidate binding(s):** Pack `P836_Conv` ↔ RUN conveyor `P836` (present in RUN; confirm sawtooth role)
- **Confidence:** 0.9
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - DISCOVERY: Token related to discovery inventory
  - RUN_EXPLICIT: Conveyor/token `P836` exists in RUN; pack UDT is `P836_Conv`
  - RUN `Jamcheck.asc`.`Conveyor_Name` = `P836` (row `PE414D_J`)
  - RUN `Conveyor.asc`.`IO_Name` = `P836` (row `P836`)
  - RUN `Mtrchain.asc`.`Motor_Chained1` = `P836` (row ``)

### `PE118_I`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_GPR_CnvCtrl[4].xPE_BlockedEntr := 0;//NOT(PE118_I.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_GPR_CnvCtrl[5].xPE_BlockedEntr := 0;//NOT(PE118_I.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_GPR_CnvCtrl[4].xPE_BlockedEntr := 0;//NOT(PE118_I.I.PE_Clear);]]>`
- **Generic-library role:** induct_or_intermediate_photoeye
- **Likely equipment/function:** Photoeye UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `PE118_I` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `PE1491_I`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_Q1_CnvCtrl[4].xPE_BlockedEntr := 0;//NOT(PE1491_I.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_Q1_CnvCtrl[5].xPE_BlockedEntr := 0;//NOT(PE1491_I.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_Q1_CnvCtrl[4].xPE_BlockedEntr := 0;//NOT(PE1491_I.I.PE_Clear);]]>`
- **Generic-library role:** induct_or_intermediate_photoeye
- **Likely equipment/function:** Photoeye UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `PE1491_I` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `PE1491_P`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_Q1_CnvCtrl[4].xPE_BlockedExit := 0;//NOT(PE1491_P.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_Q1_CnvCtrl[5].xPE_BlockedExit := 0;//NOT(PE1491_P.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_Q1_CnvCtrl[4].xPE_BlockedExit := 0;//NOT(PE1491_P.I.PE_Clear);]]>`
- **Generic-library role:** product_present_photoeye
- **Likely equipment/function:** Photoeye UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `PE1491_P` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `PE1492_I`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_Q2_CnvCtrl[4].xPE_BlockedEntr := 0;//NOT(PE1492_I.I.PE_Clear); // Entry PE on Staging Belt (Q2);`
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_Q2_CnvCtrl[5].xPE_BlockedEntr := 0;//NOT(PE1492_I.I.PE_Clear); // Entry PE on Staging Belt (Q2);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_Q2_CnvCtrl[4].xPE_BlockedEntr := 0;//NOT(PE1492_I.I.PE_Clear); // Entry PE on Staging Belt (Q2);]]>`
- **Generic-library role:** induct_or_intermediate_photoeye
- **Likely equipment/function:** Photoeye UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `PE1492_I` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `PE219A_J`

- **Datatype:** `PE_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astCollPe[1].xIsBlocked := NOT(PE219A_J.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astCollPe[1].xIsBlocked := NOT(PE219A_J.I.PE_Clear); ]]>`
- **Generic-library role:** collector_jam_photoeye
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=PE219A_J)
- **Candidate RUN table(s)/field(s):**
  - `Jamcheck.asc`.`Desc` = `PE219A_J` (row `PE219A_J`)
  - `Jamcheck.asc`.`Sensor_Name` = `PE219A_J` (row `PE219A_J`)
  - `Jamcheck.asc`.`Error_Name` = `PE219A_J` (row `PE219A_J`)
  - `Conveyor.asc`.`IO_Name` = `PE219A_J` (row `PE219A_J`)
  - `Errors.asc`.`ErrorName` = `PE219A_J` (row ``)
- **Candidate binding(s):** Exact RUN token `PE219A_J` exists — map pack tag to site IO/UDT of same name
- **Confidence:** 0.95
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - RUN `Jamcheck.asc`.`Desc` = `PE219A_J` (row `PE219A_J`)
  - RUN `Jamcheck.asc`.`Sensor_Name` = `PE219A_J` (row `PE219A_J`)
  - RUN `Jamcheck.asc`.`Error_Name` = `PE219A_J` (row `PE219A_J`)
  - RUN `Conveyor.asc`.`IO_Name` = `PE219A_J` (row `PE219A_J`)
  - RUN `Errors.asc`.`ErrorName` = `PE219A_J` (row ``)

### `PE2426_I`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_Q2_CnvCtrl[1].xPE_BlockedEntr := 0; // NOT(PE2426_I.I.PE_Clear); // Entry PE on Staging Belt (Q2)`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_Q2_CnvCtrl[1].xPE_BlockedEntr := 0; // NOT(PE2426_I.I.PE_Clear); // Entry PE on Staging Belt (Q2)]]>`
- **Generic-library role:** induct_or_intermediate_photoeye
- **Likely equipment/function:** Photoeye UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `PE2426_I` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `PE3451_I`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_Q1_CnvCtrl[2].xPE_BlockedEntr := 0;//NOT(PE3451_I.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_Q1_CnvCtrl[2].xPE_BlockedEntr := 0;//NOT(PE3451_I.I.PE_Clear);]]>`
- **Generic-library role:** induct_or_intermediate_photoeye
- **Likely equipment/function:** Photoeye UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `PE3451_I` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `PE3451_P`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_Q1_CnvCtrl[2].xPE_BlockedExit := 0;//NOT(PE3451_P.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_Q1_CnvCtrl[2].xPE_BlockedExit := 0;//NOT(PE3451_P.I.PE_Clear);]]>`
- **Generic-library role:** product_present_photoeye
- **Likely equipment/function:** Photoeye UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `PE3451_P` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `PE3452_I`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_Q2_CnvCtrl[2].xPE_BlockedEntr := 0;//NOT(PE3452_I.I.PE_Clear); // Entry PE on Staging Belt (Q2);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_Q2_CnvCtrl[2].xPE_BlockedEntr := 0;//NOT(PE3452_I.I.PE_Clear); // Entry PE on Staging Belt (Q2);]]>`
- **Generic-library role:** induct_or_intermediate_photoeye
- **Likely equipment/function:** Photoeye UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `PE3452_I` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `PE410_I`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_GPR_CnvCtrl[2].xPE_BlockedEntr := 0;//NOT(PE410_I.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_GPR_CnvCtrl[2].xPE_BlockedEntr := 0;//NOT(PE410_I.I.PE_Clear);]]>`
- **Generic-library role:** induct_or_intermediate_photoeye
- **Likely equipment/function:** Photoeye UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `PE410_I` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `PE4131_I`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_Q1_CnvCtrl[3].xPE_BlockedEntr := 0;//NOT(PE4131_I.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_Q1_CnvCtrl[3].xPE_BlockedEntr := 0;//NOT(PE4131_I.I.PE_Clear);]]>`
- **Generic-library role:** induct_or_intermediate_photoeye
- **Likely equipment/function:** Photoeye UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `PE4131_I` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `PE4131_P`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_Q1_CnvCtrl[3].xPE_BlockedExit := 0;//NOT(PE4131_P.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_Q1_CnvCtrl[3].xPE_BlockedExit := 0;//NOT(PE4131_P.I.PE_Clear);]]>`
- **Generic-library role:** product_present_photoeye
- **Likely equipment/function:** Photoeye UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `PE4131_P` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `PE4132_I`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_Q2_CnvCtrl[3].xPE_BlockedEntr := 0;//NOT(PE4132_I.I.PE_Clear); // Entry PE on Staging Belt (Q2);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_Q2_CnvCtrl[3].xPE_BlockedEntr := 0;//NOT(PE4132_I.I.PE_Clear); // Entry PE on Staging Belt (Q2);]]>`
- **Generic-library role:** induct_or_intermediate_photoeye
- **Likely equipment/function:** Photoeye UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Omit or leave unmapped — no RUN equipment of this name
- **Confidence:** 0.7
- **Resolution:** `UNUSED_FOR_THIS_SITE`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `PE4132_I` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `PE414A_J`

- **Datatype:** `PE_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astCollPe[2].xIsBlocked := NOT(PE414A_J.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astCollPe[2].xIsBlocked := NOT(PE414A_J.I.PE_Clear); ]]>`
- **Generic-library role:** collector_jam_photoeye
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=PE414A_J)
- **Candidate RUN table(s)/field(s):**
  - `Jamcheck.asc`.`Desc` = `PE414A_J` (row `PE414A_J`)
  - `Jamcheck.asc`.`Sensor_Name` = `PE414A_J` (row `PE414A_J`)
  - `Jamcheck.asc`.`Error_Name` = `PE414A_J` (row `PE414A_J`)
  - `Conveyor.asc`.`IO_Name` = `PE414A_J` (row `PE414A_J`)
  - `Errors.asc`.`ErrorName` = `PE414A_J` (row ``)
- **Candidate binding(s):** Exact RUN token `PE414A_J` exists — map pack tag to site IO/UDT of same name
- **Confidence:** 0.95
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - RUN `Jamcheck.asc`.`Desc` = `PE414A_J` (row `PE414A_J`)
  - RUN `Jamcheck.asc`.`Sensor_Name` = `PE414A_J` (row `PE414A_J`)
  - RUN `Jamcheck.asc`.`Error_Name` = `PE414A_J` (row `PE414A_J`)
  - RUN `Conveyor.asc`.`IO_Name` = `PE414A_J` (row `PE414A_J`)
  - RUN `Errors.asc`.`ErrorName` = `PE414A_J` (row ``)

### `PE414B_J`

- **Datatype:** `PE_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astCollPe[3].xIsBlocked := NOT(PE414B_J.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astCollPe[3].xIsBlocked := NOT(PE414B_J.I.PE_Clear); ]]>`
- **Generic-library role:** collector_jam_photoeye
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=PE414B_J)
- **Candidate RUN table(s)/field(s):**
  - `Jamcheck.asc`.`Desc` = `PE414B_J` (row `PE414B_J`)
  - `Jamcheck.asc`.`Sensor_Name` = `PE414B_J` (row `PE414B_J`)
  - `Jamcheck.asc`.`Error_Name` = `PE414B_J` (row `PE414B_J`)
  - `Conveyor.asc`.`IO_Name` = `PE414B_J` (row `PE414B_J`)
  - `Errors.asc`.`ErrorName` = `PE414B_J` (row ``)
- **Candidate binding(s):** Exact RUN token `PE414B_J` exists — map pack tag to site IO/UDT of same name
- **Confidence:** 0.95
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - RUN `Jamcheck.asc`.`Desc` = `PE414B_J` (row `PE414B_J`)
  - RUN `Jamcheck.asc`.`Sensor_Name` = `PE414B_J` (row `PE414B_J`)
  - RUN `Jamcheck.asc`.`Error_Name` = `PE414B_J` (row `PE414B_J`)
  - RUN `Conveyor.asc`.`IO_Name` = `PE414B_J` (row `PE414B_J`)
  - RUN `Errors.asc`.`ErrorName` = `PE414B_J` (row ``)

### `PE414C_J`

- **Datatype:** `PE_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astCollPe[4].xIsBlocked := NOT(PE414C_J.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astCollPe[4].xIsBlocked := NOT(PE414C_J.I.PE_Clear); ]]>`
- **Generic-library role:** collector_jam_photoeye
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=PE414C_J)
- **Candidate RUN table(s)/field(s):**
  - `Jamcheck.asc`.`Desc` = `PE414C_J` (row `PE414C_J`)
  - `Jamcheck.asc`.`Sensor_Name` = `PE414C_J` (row `PE414C_J`)
  - `Jamcheck.asc`.`Error_Name` = `PE414C_J` (row `PE414C_J`)
  - `Conveyor.asc`.`IO_Name` = `PE414C_J` (row `PE414C_J`)
  - `Errors.asc`.`ErrorName` = `PE414C_J` (row ``)
- **Candidate binding(s):** Exact RUN token `PE414C_J` exists — map pack tag to site IO/UDT of same name
- **Confidence:** 0.95
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - RUN `Jamcheck.asc`.`Desc` = `PE414C_J` (row `PE414C_J`)
  - RUN `Jamcheck.asc`.`Sensor_Name` = `PE414C_J` (row `PE414C_J`)
  - RUN `Jamcheck.asc`.`Error_Name` = `PE414C_J` (row `PE414C_J`)
  - RUN `Conveyor.asc`.`IO_Name` = `PE414C_J` (row `PE414C_J`)
  - RUN `Errors.asc`.`ErrorName` = `PE414C_J` (row ``)

### `PE414D_J`

- **Datatype:** `PE_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astCollPe[5].xIsBlocked := NOT(PE414D_J.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astCollPe[5].xIsBlocked := NOT(PE414D_J.I.PE_Clear); ]]>`
- **Generic-library role:** collector_jam_photoeye
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=PE414D_J)
- **Candidate RUN table(s)/field(s):**
  - `Jamcheck.asc`.`Desc` = `PE414D_J` (row `PE414D_J`)
  - `Jamcheck.asc`.`Sensor_Name` = `PE414D_J` (row `PE414D_J`)
  - `Jamcheck.asc`.`Error_Name` = `PE414D_J` (row `PE414D_J`)
  - `Conveyor.asc`.`IO_Name` = `PE414D_J` (row `PE414D_J`)
  - `Errors.asc`.`ErrorName` = `PE414D_J` (row ``)
- **Candidate binding(s):** Exact RUN token `PE414D_J` exists — map pack tag to site IO/UDT of same name
- **Confidence:** 0.95
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - RUN `Jamcheck.asc`.`Desc` = `PE414D_J` (row `PE414D_J`)
  - RUN `Jamcheck.asc`.`Sensor_Name` = `PE414D_J` (row `PE414D_J`)
  - RUN `Jamcheck.asc`.`Error_Name` = `PE414D_J` (row `PE414D_J`)
  - RUN `Conveyor.asc`.`IO_Name` = `PE414D_J` (row `PE414D_J`)
  - RUN `Errors.asc`.`ErrorName` = `PE414D_J` (row ``)

### `PE414_J`

- **Datatype:** `PE_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astCollPe[6].xIsBlocked := NOT(PE414_J.I.PE_Clear); // Last PE: Exit PE of the collector belt // Number of lanes + 1 // For this 5 lane setup`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astCollPe[6].xIsBlocked := NOT(PE414_J.I.PE_Clear); // Last PE: Exit PE of the collector belt // Number of lanes + 1 // For this 5 lane setup]]>`
- **Generic-library role:** collector_jam_photoeye
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=PE414_J)
- **Candidate RUN table(s)/field(s):**
  - `Jamcheck.asc`.`Desc` = `PE414_J` (row `PE414_J`)
  - `Jamcheck.asc`.`Sensor_Name` = `PE414_J` (row `PE414_J`)
  - `Jamcheck.asc`.`Error_Name` = `PE414_J` (row `PE414_J`)
  - `Conveyor.asc`.`IO_Name` = `PE414_J` (row `PE414_J`)
  - `Errors.asc`.`ErrorName` = `PE414_J` (row ``)
- **Candidate binding(s):** Exact RUN token `PE414_J` exists — map pack tag to site IO/UDT of same name
- **Confidence:** 0.95
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - RUN `Jamcheck.asc`.`Desc` = `PE414_J` (row `PE414_J`)
  - RUN `Jamcheck.asc`.`Sensor_Name` = `PE414_J` (row `PE414_J`)
  - RUN `Jamcheck.asc`.`Error_Name` = `PE414_J` (row `PE414_J`)
  - RUN `Conveyor.asc`.`IO_Name` = `PE414_J` (row `PE414_J`)
  - RUN `Errors.asc`.`ErrorName` = `PE414_J` (row ``)

### `PE418_I`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_GPR_CnvCtrl[3].xPE_BlockedEntr := 0;//NOT(PE418_I.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_GPR_CnvCtrl[3].xPE_BlockedEntr := 0;//NOT(PE418_I.I.PE_Clear);]]>`
- **Generic-library role:** induct_or_intermediate_photoeye
- **Likely equipment/function:** Photoeye UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Gold collector companion devices — confirm whether site collector train includes them via Conveyor.asc before binding
- **Confidence:** 0.55
- **Resolution:** `CONFIGURATION_REQUIRED`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `PE418_I` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `PE418_P`

- **Datatype:** `—`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `MRG414_astUNL_GPR_CnvCtrl[3].xPE_BlockedExit := 0;//NOT(PE418_P.I.PE_Clear);`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[MRG414_astUNL_GPR_CnvCtrl[3].xPE_BlockedExit := 0;//NOT(PE418_P.I.PE_Clear);]]>`
- **Generic-library role:** product_present_photoeye
- **Likely equipment/function:** Photoeye UDT instance in pack
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Gold collector companion devices — confirm whether site collector train includes them via Conveyor.asc before binding
- **Confidence:** 0.55
- **Resolution:** `CONFIGURATION_REQUIRED`
- **Evidence:**
  - NEGATIVE_RUN: No exact token hit for `PE418_P` in scanned RUN Fortna tables
- **Notes:** No RUN exact match; refusing digit-similarity binding (policy)

### `Use_GapStore_Belts`

- **Datatype:** `—`
- **Routines:** `Conv_Enc`
- **Instruction/context:**
  - `Conv_Enc`: `XIC(Enable_Merge2_Trk)[XIC(Use_GapStore_Belts) MOV(400,P414_SawMerge_HMI.ClctrSpeed_FPM) ,XIO(Use_GapStore_Belts) MOV(140,P414_SawMerge_HMI.ClctrSpeed_FPM) ];`
  - `Conv_Enc`: `XIC(Enable_Merge2_Trk)XIO(Use_GapStore_Belts)JSR(RT_DeltaDist_NoGapStore,0);`
  - `Conv_Enc`: `XIC(Enable_Merge2_Trk)XIO(Use_GapStore_Belts)JSR(RT_IO_Map_NoGapStore,0);`
- **Generic-library role:** feature_enable_gate
- **Likely equipment/function:** Logic feature gate (not a field device)
- **Candidate RUN table(s)/field(s):** —
- **Candidate binding(s):** Set TRUE/FALSE per site feature (gap-store vs no-gap-store, reservation enable)
- **Confidence:** 0.85
- **Resolution:** `ENGINEER_CONFIGURED`
- **Evidence:**
  - LIBRARY: Main/feature gate referenced in routines: ['Conv_Enc']
- **Notes:** Pass classified as feature enable — not a RUN field device

### `EZPE217_F`

- **Datatype:** `—`
- **Routines:** —
- **Generic-library role:** lane_or_line_full_eye
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=EZPE217_F)
- **Candidate RUN table(s)/field(s):**
  - `Fullline.asc`.`Desc` = `EZPE217_F` (row `EZPE217_F`)
  - `Fullline.asc`.`Sensor_Name` = `EZPE217_F` (row `EZPE217_F`)
  - `Conveyor.asc`.`IO_Name` = `EZPE217_F` (row `EZPE217_F`)
- **Candidate binding(s):** Add pack tag EZPE217_F (PE_UDT) and bind to site full eye on P217; Wire reservation logic to tmfcEZPE217_F / EZPE217_F.Full — do not use EZPE127_F
- **Confidence:** 0.95
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - RUN `Fullline.asc`.`Desc` = `EZPE217_F` (row `EZPE217_F`)
  - RUN `Fullline.asc`.`Sensor_Name` = `EZPE217_F` (row `EZPE217_F`)
  - RUN `Conveyor.asc`.`IO_Name` = `EZPE217_F` (row `EZPE217_F`)
  - RUN_EXPLICIT: SawLane.LANE_0_P219.ReserveTM=tmfcEZPE217_F; Conveyor+Fullline define EZPE217_F
- **Notes:** Symbol is RUN_EXPLICIT; pack absence makes emit CONFIGURATION_REQUIRED until tag added

### `EZPE212_F2`

- **Datatype:** `PE_UDT`
- **Routines:** `RT_IO_Map_NoGapStore`
- **Instruction/context:**
  - `RT_IO_Map_NoGapStore`: `IF EZPE212_F2.Full THEN`
  - `RT_IO_Map_NoGapStore`: `<![CDATA[IF EZPE212_F2.Full THEN ]]>`
- **Generic-library role:** lane_or_line_full_eye
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=EZPE212_F2)
- **Candidate RUN table(s)/field(s):**
  - `Fullline.asc`.`Desc` = `EZPE212_F2` (row `EZPE212_F2`)
  - `Fullline.asc`.`Sensor_Name` = `EZPE212_F2` (row `EZPE212_F2`)
  - `Fullline.asc`.`Error_Name` = `EZPE212_F2` (row `EZPE212_F2`)
  - `Conveyor.asc`.`IO_Name` = `EZPE212_F2` (row `EZPE212_F2`)
  - `Errors.asc`.`ErrorName` = `EZPE212_F2` (row ``)
- **Candidate binding(s):** RUN defines EZPE212_F2 (Fullline→P214; Conveyor 'FULL EYE ON P212 DOWNSTREAM OF P308 MERGE'); Pack SR_LaneCntrl uses EZPE212_F2.Full — confirm whether site Sawtooth reserve should stay on F2 or move to F1 per ReserveTM
- **Confidence:** 0.9
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - RUN `Fullline.asc`.`Desc` = `EZPE212_F2` (row `EZPE212_F2`)
  - RUN `Fullline.asc`.`Sensor_Name` = `EZPE212_F2` (row `EZPE212_F2`)
  - RUN `Fullline.asc`.`Error_Name` = `EZPE212_F2` (row `EZPE212_F2`)
  - RUN `Conveyor.asc`.`IO_Name` = `EZPE212_F2` (row `EZPE212_F2`)
  - RUN `Errors.asc`.`ErrorName` = `EZPE212_F2` (row ``)
  - CONFLICT: SawLane.ReserveTM=tmfcEZPE212_F1 vs pack/Fullline-P214 EZPE212_F2
- **Notes:** Device token is RUN_EXPLICIT; Equivalence to LANE_4 ReserveTM tmfcEZPE212_F1 is NOT proven — open CONFIGURATION_REQUIRED decision

### `EZPE212_F1`

- **Datatype:** `—`
- **Routines:** —
- **Generic-library role:** lane_or_line_full_eye
- **Likely equipment/function:** RUN device/token in Conveyor.asc.IO_Name (row=EZPE212_F1)
- **Candidate RUN table(s)/field(s):**
  - `Fullline.asc`.`Desc` = `EZPE212_F1` (row `EZPE212_F1`)
  - `Fullline.asc`.`Sensor_Name` = `EZPE212_F1` (row `EZPE212_F1`)
  - `Fullline.asc`.`Error_Name` = `EZPE212_F1` (row `EZPE212_F1`)
  - `Conveyor.asc`.`IO_Name` = `EZPE212_F1` (row `EZPE212_F1`)
  - `Errors.asc`.`ErrorName` = `EZPE212_F1` (row ``)
- **Candidate binding(s):** ReserveTM points at tmfcEZPE212_F1 — keep as reservation timer identity; Pack currently references EZPE212_F2 — engineer must confirm which eye is Sawtooth full/reserve
- **Confidence:** 0.95
- **Resolution:** `RUN_EXPLICIT`
- **Evidence:**
  - RUN `Fullline.asc`.`Desc` = `EZPE212_F1` (row `EZPE212_F1`)
  - RUN `Fullline.asc`.`Sensor_Name` = `EZPE212_F1` (row `EZPE212_F1`)
  - RUN `Fullline.asc`.`Error_Name` = `EZPE212_F1` (row `EZPE212_F1`)
  - RUN `Conveyor.asc`.`IO_Name` = `EZPE212_F1` (row `EZPE212_F1`)
  - RUN `Errors.asc`.`ErrorName` = `EZPE212_F1` (row ``)
- **Notes:** Presence of F1 in RUN is explicit; functional equivalence to pack F2 is NOT established; Sawtooth lane-full role vs Fullline/line-full role remains CONFIGURATION_REQUIRED
