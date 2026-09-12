# Sawtooth Merge — Routine Dependency Graph

Generated: `2026-09-12T16:17:55.081653+00:00`
Source: `C:\dev\worktree\FortnaPlus\tools\libraries\programs\Sawtooth_Merge_Program.L5X`
Program: **Sawtooth_Merge**
Main routine: **Main_Routine**
Routines: **20** · Tags: **208**

## Call graph (entry → …)

```
- Main_Routine
  - Conv_Enc
  - Conv_Fast
  - Conv_PE
  - RT_CollTrackMain
    - RT_CollLaneMergeCapture
    - RT_CollPeTrackCal
    - RT_CollResetCounts
    - RT_CollTrackHist
    - RT_CollTrackInit
    - RT_CollTrackResvMngr
      - SR_CollTrackChkSlot
      - SR_CollTrackClrSlot
      - SR_CollTrackRsrvSlot
      - SR_CollTrackSlotAtMrgPnt
      - SR_CollTrackSrchSlot
    - RT_LaneOffsetFind
    - SR_LaneCntrl
      - SR_CollTrackClrSlot
  - RT_DeltaDist_NoGapStore
  - RT_IO_Map_NoGapStore
```

## Routines

### `Conv_Enc` (RLL)

- **Purpose:** Encoder processing (RLL; pack may be empty stub)
- **Called by:** `Main_Routine`
- **Calls:** —
- **Logic units:** 0

### `Conv_Fast` (RLL)

- **Purpose:** Fast-task conveyor processing (RLL; pack may be empty stub)
- **Called by:** `Main_Routine`
- **Calls:** —
- **Logic units:** 0

### `Conv_PE` (RLL)

- **Purpose:** Photoeye / conveyor PE processing (RLL; pack may be empty stub)
- **Called by:** `Main_Routine`
- **Calls:** —
- **Logic units:** 0

### `Main_Routine` (RLL)

- **Purpose:** Program entry; schedules Conv_* and gated tracking/reservation JSRs
- **Called by:** —
- **Calls:** `Conv_Enc`, `Conv_Fast`, `Conv_PE`, `RT_CollTrackMain`, `RT_DeltaDist_NoGapStore`, `RT_IO_Map_NoGapStore`
- **Logic units:** 15
- **merge_structs:** `MRG414_stCollLaneMrgCapture`, `MRG414_stCollStatus`, `MRG414_xCollLaneMrgCaptureArm`, `MRG414_xCollResetCounts`, `MRG414_xCollTrackConfigured`, `MRG414_xCollTrackPE_OffsetCaptureArm`, `MRG414_xINIT`, `MRG414_xLaneClctrPeCalibrate`, `MRG414_xLaneClctrTrkAryFreeze`, `MRG414_xLaneClctrTrkHistorize`, `MRG414_xLaneOffsetFind`, `MRG414_xLane_OffsetCaptureArm`
- **Writes (sample):** `MRG414_stCollLaneMrgCapture`, `MRG414_stCollStatus`, `MRG414_xCollTrackConfigured`, `MRG414_xINIT`, `P414_SawMerge_HMI`
- **Reads (sample):** `MRG414_xCollLaneMrgCaptureArm`, `MRG414_xCollResetCounts`, `MRG414_xCollTrackPE_OffsetCaptureArm`, `MRG414_xLaneClctrPeCalibrate`, `MRG414_xLaneClctrTrkAryFreeze`, `MRG414_xLaneClctrTrkHistorize`, `MRG414_xLaneOffsetFind`, `MRG414_xLane_OffsetCaptureArm`
- **AOI/FB-like:** `NOP`

### `RT_CollLaneMergeCapture` (ST)

- **Purpose:** Capture lane-to-collector merge point offsets
- **Called by:** `RT_CollTrackMain`
- **Calls:** —
- **Logic units:** 61
- **merge_structs:** `MRG414_adiCollTrkArray`, `MRG414_adiCollTrkArray_Capture`, `MRG414_astCollPe`, `MRG414_astCollPeCfg`, `MRG414_diCollTrkPkgAryLastIdx`, `MRG414_diCollTrkPkgArySize`, `MRG414_diLaneID_Mod`, `MRG414_stCollLaneMrgCapture`, `MRG414_stCollTrkSysCfg`, `MRG414_xCollLaneMrgCaptureArm`
- **Writes (sample):** `MRG414_stCollLaneMrgCapture`, `MRG414_stCollTrkSysCfg`, `MRG414_xCollLaneMrgCaptureArm`
- **Reads (sample):** `MRG414_adiCollTrkArray`, `MRG414_adiCollTrkArray_Capture`, `MRG414_astCollPe`, `MRG414_astCollPeCfg`, `MRG414_diCollTrkPkgAryLastIdx`, `MRG414_diCollTrkPkgArySize`, `MRG414_diLaneID_Mod`

### `RT_CollPeTrackCal` (ST)

- **Purpose:** Collision / collector PE track calibration
- **Called by:** `RT_CollTrackMain`
- **Calls:** —
- **Logic units:** 63
- **merge_structs:** `MRG414_astCollPe`, `MRG414_astCollPeTrackCal`, `MRG414_c_xFALSE`, `MRG414_diCollCalPeIndex`, `MRG414_diCollDeltaEncCnt`, `MRG414_stCollTrkSysCfg`, `MRG414_xCollPeCalReset`, `MRG414_xCollTrackPE_OffsetCaptureArm`
- **Writes (sample):** `MRG414_diCollCalPeIndex`, `MRG414_xCollPeCalReset`, `MRG414_xCollTrackPE_OffsetCaptureArm`
- **Reads (sample):** `MRG414_astCollPe`, `MRG414_astCollPeTrackCal`, `MRG414_c_xFALSE`, `MRG414_diCollDeltaEncCnt`, `MRG414_stCollTrkSysCfg`

### `RT_CollResetCounts` (ST)

- **Purpose:** Reset collector tracking counters
- **Called by:** `RT_CollTrackMain`
- **Calls:** —
- **Logic units:** 23
- **merge_structs:** `MRG414_astLaneClctrSlotResCnts`, `MRG414_diLanecntsResetIdx`, `MRG414_stCollTrkSysCfg`, `MRG414_stLaneClctrSlotResvcnt_CLR`
- **Writes (sample):** `MRG414_diLanecntsResetIdx`
- **Reads (sample):** `MRG414_astLaneClctrSlotResCnts`, `MRG414_stCollTrkSysCfg`, `MRG414_stLaneClctrSlotResvcnt_CLR`

### `RT_CollTrackHist` (ST)

- **Purpose:** Collector tracking history maintenance
- **Called by:** `RT_CollTrackMain`
- **Calls:** —
- **Logic units:** 204
- **merge_structs:** `MRG414_adiCollTrkArray`, `MRG414_astCollHist`, `MRG414_astCollPeCfg`, `MRG414_c_xFALSE`, `MRG414_c_xTRUE`, `MRG414_diCollHistArrayErrCnt`, `MRG414_diCollHistPeIndex`, `MRG414_diCollHistPeLocation`, `MRG414_diCollTrkPkgArySize`, `MRG414_diLaneID_Mod`, `MRG414_stCollHistTmp`, `MRG414_stCollHistTmpZero`, `MRG414_stCollTrkSysCfg`, `MRG414_xResetCollHistogram`
- **Writes (sample):** `MRG414_diCollHistArrayErrCnt`, `MRG414_diCollHistPeIndex`, `MRG414_diCollHistPeLocation`, `MRG414_stCollHistTmp`, `MRG414_xResetCollHistogram`
- **Reads (sample):** `MRG414_adiCollTrkArray`, `MRG414_astCollHist`, `MRG414_astCollPeCfg`, `MRG414_c_xFALSE`, `MRG414_c_xTRUE`, `MRG414_diCollTrkPkgArySize`, `MRG414_diLaneID_Mod`, `MRG414_stCollHistTmpZero`, `MRG414_stCollTrkSysCfg`

### `RT_CollTrackInit` (ST)

- **Purpose:** Initialize collector tracking structures
- **Called by:** `RT_CollTrackMain`
- **Calls:** —
- **Logic units:** 307
- **merge_structs:** `MRG414_astCollPeCfg`, `MRG414_astCollPeTrackCal`, `MRG414_astLanePeTrackCal`, `MRG414_astUNL_SlugBldCfg`, `MRG414_c_xFALSE`, `MRG414_c_xTRUE`, `MRG414_diLaneID_Mod`, `MRG414_diLanePkgSeqId_Max`, `MRG414_stCollTrkSysCfg`, `MRG414_xLaneClctrTrkHistorize`
- **Writes (sample):** `MRG414_c_xFALSE`, `MRG414_c_xTRUE`, `MRG414_diLaneID_Mod`, `MRG414_diLanePkgSeqId_Max`, `MRG414_stCollTrkSysCfg`, `MRG414_xLaneClctrTrkHistorize`
- **Reads (sample):** `MRG414_astCollPeCfg`, `MRG414_astCollPeTrackCal`, `MRG414_astLanePeTrackCal`, `MRG414_astUNL_SlugBldCfg`, `P414_SawMerge_HMI`

### `RT_CollTrackMain` (ST)

- **Purpose:** Collector tracking main; inits hist/PE cal/lane merge capture/resv/lane control
- **Called by:** `Main_Routine`
- **Calls:** `RT_CollLaneMergeCapture`, `RT_CollPeTrackCal`, `RT_CollResetCounts`, `RT_CollTrackHist`, `RT_CollTrackInit`, `RT_CollTrackResvMngr`, `RT_LaneOffsetFind`, `SR_LaneCntrl`
- **Logic units:** 254
- **merge_structs:** `MRG414_FreezeIdx1`, `MRG414_adiCollTrkArray`, `MRG414_adiCollTrkArray_Freeze`, `MRG414_aoColl_01_CnvDeltaDist`, `MRG414_astCollPe`, `MRG414_astCollPeCfg`, `MRG414_astLaneClctrSlotResvCntrl`, `MRG414_astLaneClctrSlotResvCntrl_Clr`, `MRG414_astLaneClctrSlotResvCntrl_Freeze`, `MRG414_c_xFALSE`, `MRG414_c_xTRUE`, `MRG414_diClctrEncLane`, `MRG414_diCollDeltaEncCnt`, `MRG414_diCollDeltaEncCntMax`, `MRG414_diCollEncCntCopy`, `MRG414_diCollEncCntCurr`, `MRG414_diCollEncCntPrev`, `MRG414_diCollEncInconsistentCnt`, `MRG414_diCollEncShftIdx`, `MRG414_diCollPeIndex` …
- **Writes (sample):** `MRG414_FreezeIdx1`, `MRG414_diClctrEncLane`, `MRG414_diCollDeltaEncCnt`, `MRG414_diCollDeltaEncCntMax`, `MRG414_diCollEncCntCopy`, `MRG414_diCollEncCntCurr`, `MRG414_diCollEncCntPrev`, `MRG414_diCollEncInconsistentCnt`, `MRG414_diCollEncShftIdx`, `MRG414_diCollPeIndex`, `MRG414_diCollPeLocation`, `MRG414_diCollTrkPkgAryLastIdx`, `MRG414_diCollTrkPkgShiftSize`, `MRG414_di_LaneCntrlIdx`, `MRG414_rCollDeltaDist` …
- **Reads (sample):** `MRG414_adiCollTrkArray`, `MRG414_adiCollTrkArray_Freeze`, `MRG414_aoColl_01_CnvDeltaDist`, `MRG414_astCollPe`, `MRG414_astCollPeCfg`, `MRG414_astLaneClctrSlotResvCntrl`, `MRG414_astLaneClctrSlotResvCntrl_Clr`, `MRG414_astLaneClctrSlotResvCntrl_Freeze`, `MRG414_c_xFALSE`, `MRG414_c_xTRUE`, `MRG414_diCollTrkPkgArySize`, `MRG414_rCollSpdFeedback_IPS`, `MRG414_rFastTaskDeltaMilliSecs`, `MRG414_stCollTrkSysCfg`, `MRG414_xCollLaneMrgCaptureArm` …
- **AOI/FB-like:** `AO_CnvDeltaDist`

### `RT_CollTrackResvMngr` (ST)

- **Purpose:** Reservation manager — search/reserve/clear/check slots at merge point
- **Called by:** `RT_CollTrackMain`
- **Calls:** `SR_CollTrackChkSlot`, `SR_CollTrackClrSlot`, `SR_CollTrackRsrvSlot`, `SR_CollTrackSlotAtMrgPnt`, `SR_CollTrackSrchSlot`
- **Logic units:** 579
- **merge_structs:** `MRG414_astLaneClctrSlotResCnts`, `MRG414_astLaneClctrSlotResvCntrl`, `MRG414_astLaneClctrSlotResvStat`, `MRG414_c_xFALSE`, `MRG414_diClctrFltLaneIdx`, `MRG414_diClctrResvAtSlotLaneIdx`, `MRG414_diClctrResvMngIdx`, `MRG414_diClctrResvMngLaneIdx`, `MRG414_diClctrResvMngStrtIdx`, `MRG414_diClctrSchLane`, `MRG414_diClctrShiftIdx`, `MRG414_diClctrSlotCmpsdLaneIdx`, `MRG414_diClctrSlotInsert`, `MRG414_diClctrSlotOrdIdx`, `MRG414_diClctrSlotOrdIdxLim`, `MRG414_diClctrSlotSrchNum`, `MRG414_diCollAvgSlotSizePls`, `MRG414_diCollDeltaEncCnt`, `MRG414_diCollDnStrmFreeSearchLimitPls`, `MRG414_diCollLaneCompareMask` …
- **Writes (sample):** `MRG414_diClctrFltLaneIdx`, `MRG414_diClctrResvAtSlotLaneIdx`, `MRG414_diClctrResvMngIdx`, `MRG414_diClctrResvMngLaneIdx`, `MRG414_diClctrResvMngStrtIdx`, `MRG414_diClctrSchLane`, `MRG414_diClctrShiftIdx`, `MRG414_diClctrSlotCmpsdLaneIdx`, `MRG414_diClctrSlotInsert`, `MRG414_diClctrSlotOrdIdx`, `MRG414_diClctrSlotOrdIdxLim`, `MRG414_diClctrSlotSrchNum`, `MRG414_diCollAvgSlotSizePls`, `MRG414_diCollDnStrmFreeSearchLimitPls`, `MRG414_diCollLaneCompareMask` …
- **Reads (sample):** `MRG414_astLaneClctrSlotResCnts`, `MRG414_astLaneClctrSlotResvCntrl`, `MRG414_astLaneClctrSlotResvStat`, `MRG414_c_xFALSE`, `MRG414_diCollDeltaEncCnt`, `MRG414_diResvRqstOrderArySize`, `MRG414_o_diCollFndSlotLoc`, `MRG414_o_xCollChkSlotCmpsd`, `MRG414_o_xCollSlotAtMrg`, `MRG414_o_xCollSlotFnd`, `MRG414_o_xCollSlotPastMrg`, `MRG414_stCollTrkSysCfg`, `MRG414_stLaneClctrSlotResMngr`

### `RT_DeltaDist_NoGapStore` (ST)

- **Purpose:** Collector delta-distance tracking without gap-store belts
- **Called by:** `Main_Routine`
- **Calls:** —
- **Logic units:** 233
- **merge_structs:** `MRG414_aoUNL_MRG_CnvDeltaDist`, `MRG414_aoUNL_Q2_CnvDeltaDist`, `MRG414_astUNL_MRG_CnvCtrl`, `MRG414_astUNL_Q2_CnvCtrl`, `MRG414_rFastTaskDeltaMilliSecs`
- **Reads (sample):** `MRG414_aoUNL_MRG_CnvDeltaDist`, `MRG414_aoUNL_Q2_CnvDeltaDist`, `MRG414_astUNL_MRG_CnvCtrl`, `MRG414_astUNL_Q2_CnvCtrl`, `MRG414_rFastTaskDeltaMilliSecs`
- **AOI/FB-like:** `AO_CnvDeltaDist`

### `RT_IO_Map_NoGapStore` (ST)

- **Purpose:** IO mapping for no-gap-store collector path
- **Called by:** `Main_Routine`
- **Calls:** —
- **Logic units:** 471
- **lane_pe:** `PE118_P`, `PE216_P`, `PE219A_J`, `PE219_P`, `PE410_P`, `PE414A_J`, `PE414B_J`, `PE414C_J`, `PE414D_J`, `PE414_J`, `PE834_P`
- **full_eyes:** `EZPE116_F`, `EZPE127_F`, `EZPE212_F2`, `EZPE408_F`, `EZPE832_F`
- **conveyors:** `P118_Conv`, `P120_Conv`, `P216_Conv`, `P218_Conv`, `P219A_Conv`, `P219_Conv`, `P410_Conv`, `P412_Conv`, `P414_Conv`, `P418_Conv`, `P834_Conv`, `P836_Conv`
- **merge_structs:** `MRG414_Enable_NoCartonCheck`, `MRG414_astCollPe`, `MRG414_astLaneClctrSlotResvCntrl`, `MRG414_astLaneClctrSlotResvStat`, `MRG414_astUNL_BFR_CnvCtrl`, `MRG414_astUNL_GPR_CnvCtrl`, `MRG414_astUNL_MRG_CnvCtrl`, `MRG414_astUNL_PT_CnvCtrl`, `MRG414_astUNL_Q1_CnvCtrl`, `MRG414_astUNL_Q2_CnvCtrl`, `MRG414_astUNL_SlugBldCfg`, `MRG414_astUNL_SlugBldCtrl`, `MRG414_diHMI_LaneIdx`, `MRG414_diLaneEmptyPkg_Status`, `MRG414_diNoCartonGap`, `MRG414_rCollSpdFeedback_IPS`, `MRG414_rCollSpeed_IPS`, `MRG414_stCollStatus`, `MRG414_stCollTrkSysCfg`, `MRG414_xShiftUpstrmSlotsAfterNoCarton` …
- **Writes (sample):** `MRG414_Enable_NoCartonCheck`, `MRG414_diHMI_LaneIdx`, `MRG414_diNoCartonGap`, `MRG414_rCollSpdFeedback_IPS`, `MRG414_stCollStatus`, `MRG414_stCollTrkSysCfg`, `MRG414_xShiftUpstrmSlotsAfterNoCarton`, `MRG414_xSystemDrivesConfigured`, `MRG414_xUnloadLaneConfigured`, `P118_Conv`, `P120_Conv`, `P216_Conv`, `P218_Conv`, `P219A_Conv`, `P219_Conv` …
- **Reads (sample):** `EZPE116_F`, `EZPE127_F`, `EZPE212_F2`, `EZPE408_F`, `EZPE832_F`, `MRG414_astCollPe`, `MRG414_astLaneClctrSlotResvCntrl`, `MRG414_astLaneClctrSlotResvStat`, `MRG414_astUNL_BFR_CnvCtrl`, `MRG414_astUNL_GPR_CnvCtrl`, `MRG414_astUNL_MRG_CnvCtrl`, `MRG414_astUNL_PT_CnvCtrl`, `MRG414_astUNL_Q1_CnvCtrl`, `MRG414_astUNL_Q2_CnvCtrl`, `MRG414_astUNL_SlugBldCfg` …
- **Timers/counters tokens:** `tmrSlugReleased_Q2`

### `RT_LaneOffsetFind` (ST)

- **Purpose:** Find / apply lane PE offsets on collector
- **Called by:** `RT_CollTrackMain`
- **Calls:** —
- **Logic units:** 66
- **merge_structs:** `MRG414_astCollPe`, `MRG414_astLanePeTrackCal`, `MRG414_astUNL_Q2_CnvCtrl`, `MRG414_c_xFALSE`, `MRG414_c_xTRUE`, `MRG414_diCollDeltaEncCnt`, `MRG414_diLaneCalPeIndex`, `MRG414_stCollTrkSysCfg`, `MRG414_xLanePeCalReset`, `MRG414_xLane_OffsetCaptureArm`
- **Writes (sample):** `MRG414_diLaneCalPeIndex`, `MRG414_xLanePeCalReset`, `MRG414_xLane_OffsetCaptureArm`
- **Reads (sample):** `MRG414_astCollPe`, `MRG414_astLanePeTrackCal`, `MRG414_astUNL_Q2_CnvCtrl`, `MRG414_c_xFALSE`, `MRG414_c_xTRUE`, `MRG414_diCollDeltaEncCnt`, `MRG414_stCollTrkSysCfg`

### `SR_CollTrackChkSlot` (ST)

- **Purpose:** Validate reserved slot still valid
- **Called by:** `RT_CollTrackResvMngr`
- **Calls:** —
- **Logic units:** 83
- **merge_structs:** `MRG414_adiCollTrkArray`, `MRG414_diCollChkIdx`, `MRG414_diCollChkLaneTrkId`, `MRG414_diCollChkSize`, `MRG414_diCollTrkPkgAryLastIdx`, `MRG414_diCollTrkPkgArySize`, `MRG414_diLaneID_Mod`, `MRG414_i_diCollChkLaneId`, `MRG414_i_diCollChkSlotSize`, `MRG414_i_diCollChkStartIdx`, `MRG414_i_diCollChkTrkId`, `MRG414_o_xCollChkSlotCmpsd`
- **Writes (sample):** `MRG414_diCollChkIdx`, `MRG414_diCollChkLaneTrkId`, `MRG414_diCollChkSize`, `MRG414_o_xCollChkSlotCmpsd`
- **Reads (sample):** `MRG414_adiCollTrkArray`, `MRG414_diCollTrkPkgAryLastIdx`, `MRG414_diCollTrkPkgArySize`, `MRG414_diLaneID_Mod`, `MRG414_i_diCollChkLaneId`, `MRG414_i_diCollChkSlotSize`, `MRG414_i_diCollChkStartIdx`, `MRG414_i_diCollChkTrkId`

### `SR_CollTrackClrSlot` (ST)

- **Purpose:** Clear a reserved collector slot
- **Called by:** `RT_CollTrackResvMngr`, `SR_LaneCntrl`
- **Calls:** —
- **Logic units:** 56
- **merge_structs:** `MRG414_adiCollTrkArray`, `MRG414_diCollClrIdx`, `MRG414_diCollClrLaneTrkId`, `MRG414_diCollClrSize`, `MRG414_diCollTrkPkgAryLastIdx`, `MRG414_diCollTrkPkgArySize`, `MRG414_diLaneID_Mod`, `MRG414_i_diCollClrLaneId`, `MRG414_i_diCollClrSlotSize`, `MRG414_i_diCollClrStartIdx`, `MRG414_i_diCollClrTrkId`
- **Writes (sample):** `MRG414_diCollClrIdx`, `MRG414_diCollClrLaneTrkId`, `MRG414_diCollClrSize`
- **Reads (sample):** `MRG414_adiCollTrkArray`, `MRG414_diCollTrkPkgAryLastIdx`, `MRG414_diCollTrkPkgArySize`, `MRG414_diLaneID_Mod`, `MRG414_i_diCollClrLaneId`, `MRG414_i_diCollClrSlotSize`, `MRG414_i_diCollClrStartIdx`, `MRG414_i_diCollClrTrkId`

### `SR_CollTrackRsrvSlot` (ST)

- **Purpose:** Reserve a collector slot for a lane
- **Called by:** `RT_CollTrackResvMngr`
- **Calls:** —
- **Logic units:** 56
- **merge_structs:** `MRG414_adiCollTrkArray`, `MRG414_diCollRsrvIdx`, `MRG414_diCollRsrvLaneTrkId`, `MRG414_diCollRsrvSize`, `MRG414_diCollTrkPkgAryLastIdx`, `MRG414_diCollTrkPkgArySize`, `MRG414_diLaneID_Mod`, `MRG414_i_diCollRsrvLaneId`, `MRG414_i_diCollRsrvStartIdx`, `MRG414_i_diCollRsrvTrkId`, `MRG414_i_diCollRsvSlotSize`
- **Writes (sample):** `MRG414_diCollRsrvIdx`, `MRG414_diCollRsrvLaneTrkId`, `MRG414_diCollRsrvSize`
- **Reads (sample):** `MRG414_adiCollTrkArray`, `MRG414_diCollTrkPkgAryLastIdx`, `MRG414_diCollTrkPkgArySize`, `MRG414_diLaneID_Mod`, `MRG414_i_diCollRsrvLaneId`, `MRG414_i_diCollRsrvStartIdx`, `MRG414_i_diCollRsrvTrkId`, `MRG414_i_diCollRsvSlotSize`

### `SR_CollTrackSlotAtMrgPnt` (ST)

- **Purpose:** Evaluate slot arriving at merge point
- **Called by:** `RT_CollTrackResvMngr`
- **Calls:** —
- **Logic units:** 83
- **merge_structs:** `MRG414_adiCollTrkArray`, `MRG414_diCollMrgExtLaneTrkId`, `MRG414_diCollMrgLaneTrkId`, `MRG414_diCollTrkPkgArySize`, `MRG414_diLaneID_Mod`, `MRG414_i_diCollMrgLaneId`, `MRG414_i_diCollMrgSlotSize`, `MRG414_i_diCollMrgStartIdx`, `MRG414_i_diCollMrgStartOffset`, `MRG414_i_diCollMrgTrkId`, `MRG414_o_xCollSlotAtMrg`, `MRG414_o_xCollSlotPastMrg`
- **Writes (sample):** `MRG414_diCollMrgExtLaneTrkId`, `MRG414_diCollMrgLaneTrkId`, `MRG414_o_xCollSlotAtMrg`, `MRG414_o_xCollSlotPastMrg`
- **Reads (sample):** `MRG414_adiCollTrkArray`, `MRG414_diCollTrkPkgArySize`, `MRG414_diLaneID_Mod`, `MRG414_i_diCollMrgLaneId`, `MRG414_i_diCollMrgSlotSize`, `MRG414_i_diCollMrgStartIdx`, `MRG414_i_diCollMrgStartOffset`, `MRG414_i_diCollMrgTrkId`

### `SR_CollTrackSrchSlot` (ST)

- **Purpose:** Search free reservation slot on collector
- **Called by:** `RT_CollTrackResvMngr`
- **Calls:** —
- **Logic units:** 261
- **merge_structs:** `MRG414_adiCollTrkArray`, `MRG414_c_xTRUE`, `MRG414_diCollAvgSlotSizePls`, `MRG414_diCollDelaySlotSizePls`, `MRG414_diCollDnStrmFreeSearchLimitPls`, `MRG414_diCollDnStrmFreeSlotSizePls`, `MRG414_diCollDnStrmModSlotSizePls`, `MRG414_diCollDnStrmSrchIdx`, `MRG414_diCollDnStrmXtraSlotSizePls`, `MRG414_diCollFirsAvailLoc`, `MRG414_diCollLaneCompareMask`, `MRG414_diCollSrchCellEmptyCnt`, `MRG414_diCollSrchIdx`, `MRG414_diCollStartSrchIdx`, `MRG414_diCollTotalXtraSlotSizePls`, `MRG414_diCollTrkPkgAryLastIdx`, `MRG414_diCollTrkPkgArySize`, `MRG414_diCollUpStrmFreeSearchLimitPls`, `MRG414_diCollUpStrmFreeSlotSizePls`, `MRG414_diCollUpStrmSrchIdx` …
- **Writes (sample):** `MRG414_diCollDelaySlotSizePls`, `MRG414_diCollDnStrmFreeSlotSizePls`, `MRG414_diCollDnStrmModSlotSizePls`, `MRG414_diCollDnStrmSrchIdx`, `MRG414_diCollDnStrmXtraSlotSizePls`, `MRG414_diCollFirsAvailLoc`, `MRG414_diCollSrchCellEmptyCnt`, `MRG414_diCollSrchIdx`, `MRG414_diCollStartSrchIdx`, `MRG414_diCollTotalXtraSlotSizePls`, `MRG414_diCollUpStrmFreeSlotSizePls`, `MRG414_diCollUpStrmSrchIdx`, `MRG414_diCollUpStrmXtraSlotSizePls`, `MRG414_diLaneEmptyCnt`, `MRG414_o_diCollFndSlotLoc` …
- **Reads (sample):** `MRG414_adiCollTrkArray`, `MRG414_c_xTRUE`, `MRG414_diCollAvgSlotSizePls`, `MRG414_diCollDnStrmFreeSearchLimitPls`, `MRG414_diCollLaneCompareMask`, `MRG414_diCollTrkPkgAryLastIdx`, `MRG414_diCollTrkPkgArySize`, `MRG414_diCollUpStrmFreeSearchLimitPls`, `MRG414_diLaneEmptyPkg_Status`, `MRG414_i_diCollSrchSlotSizeReq`, `MRG414_i_diCollSrchStartIdx`, `MRG414_stCollTrkSysCfg`

### `SR_LaneCntrl` (ST)

- **Purpose:** Per-lane release / hold / slug-build control state machine
- **Called by:** `RT_CollTrackMain`
- **Calls:** `SR_CollTrackClrSlot`
- **Logic units:** 462
- **merge_structs:** `MRG414_Enable_NoCartonCheck`, `MRG414_adiCollTrkArray`, `MRG414_astLaneClctrSlotResvCntrl`, `MRG414_astLaneClctrSlotResvStat`, `MRG414_astUNL_MRG_CnvCtrl`, `MRG414_astUNL_PT_CnvCtrl`, `MRG414_astUNL_Q2_CnvCtrl`, `MRG414_astUNL_SlugBldCfg`, `MRG414_astUNL_SlugBldCtrl`, `MRG414_diCollClrSlotSizeToDel`, `MRG414_diCollSlotDelStartIdx`, `MRG414_diCollTrkPkgAryLastIdx`, `MRG414_diCollUsableSlotSize`, `MRG414_diLaneID_Mod`, `MRG414_diLanePkgSeqId_Max`, `MRG414_diNextUpStrmSlotEndLoc`, `MRG414_diNextUpStrmSlotLnID`, `MRG414_diNextUpStrmSlotPkgSeqID`, `MRG414_diNextUpStrmSlotResvLaneLoc`, `MRG414_diNextUpStrmSlotResvLen` …
- **Writes (sample):** `MRG414_diCollClrSlotSizeToDel`, `MRG414_diCollSlotDelStartIdx`, `MRG414_diCollUsableSlotSize`, `MRG414_diNextUpStrmSlotEndLoc`, `MRG414_diNextUpStrmSlotLnID`, `MRG414_diNextUpStrmSlotPkgSeqID`, `MRG414_diNextUpStrmSlotResvLaneLoc`, `MRG414_diNextUpStrmSlotResvLen`, `MRG414_diNextUpStrmSlotStartLoc`, `MRG414_diNextUpStrmSlotStartLocIdx`, `MRG414_diNextUpStrmSlotStartLocNew`, `MRG414_diNextUpStrmSlotTrkID`, `MRG414_diSlotSizePlsNew`, `MRG414_stLaneClctrSlotResvCntrl`, `MRG414_stLaneClctrSlotResvStat` …
- **Reads (sample):** `MRG414_Enable_NoCartonCheck`, `MRG414_adiCollTrkArray`, `MRG414_astLaneClctrSlotResvCntrl`, `MRG414_astLaneClctrSlotResvStat`, `MRG414_astUNL_MRG_CnvCtrl`, `MRG414_astUNL_PT_CnvCtrl`, `MRG414_astUNL_Q2_CnvCtrl`, `MRG414_astUNL_SlugBldCfg`, `MRG414_astUNL_SlugBldCtrl`, `MRG414_diCollTrkPkgAryLastIdx`, `MRG414_diLaneID_Mod`, `MRG414_diLanePkgSeqId_Max`, `MRG414_diNoCartonGap`, `MRG414_i_diUNL_LaneIdx`, `MRG414_stCollStatus` …
- **Timers/counters tokens:** `tmrSlugHalted_Q2`, `tmrSlugReleased_Q2`, `tmrStopped_Q2`
- **AOI/FB-like:** `TONR`

## Control-model seeds

- RUN SawState vocab: `ERROR`, `IDLE`, `HOLDING`, `WAITING`, `RELEASING`, `HANGING`
- RUN HSSawState vocab: `Stopped`, `Wait PE On`, `Wait Resrv`, `Feed Slow`, `Feed Fast`, `Wait PE Off Slow`, `Wait PE Off Fast`
- Main feature gates: `Enable_Merge1_Reserv`, `Enable_Merge2_Trk`, `Use_GapStore_Belts`
- Confidence: high for documented numeric modes; medium for RUN pState↔diLaneMode mapping

## Tag role summary

- **conveyor_udt** (12): `P118_Conv`, `P120_Conv`, `P216_Conv`, `P218_Conv`, `P219A_Conv`, `P219_Conv`, `P410_Conv`, `P412_Conv`, `P414_Conv`, `P418_Conv`, `P834_Conv`, `P836_Conv`
- **encoder_udt** (1): `P414_Enc`
- **full_eye_pe_udt** (5): `EZPE116_F`, `EZPE127_F`, `EZPE212_F2`, `EZPE408_F`, `EZPE832_F`
- **hmi** (1): `P414_SawMerge_HMI`
- **merge_control** (178): `MRG414_Enable_NoCartonCheck`, `MRG414_FreezeIdx1`, `MRG414_adiCollTrkArray`, `MRG414_adiCollTrkArray_Capture`, `MRG414_adiCollTrkArray_Freeze`, `MRG414_aoColl_01_CnvDeltaDist`, `MRG414_aoUNL_MRG_CnvDeltaDist`, `MRG414_aoUNL_Q2_CnvDeltaDist`, `MRG414_astCollHist`, `MRG414_astCollPe`, `MRG414_astCollPeCfg`, `MRG414_astCollPeTrackCal` …
- **photoeyes** (11): `PE118_P`, `PE216_P`, `PE219A_J`, `PE219_P`, `PE410_P`, `PE414A_J`, `PE414B_J`, `PE414C_J`, `PE414D_J`, `PE414_J`, `PE834_P`

Finished PLC4 was not used.
