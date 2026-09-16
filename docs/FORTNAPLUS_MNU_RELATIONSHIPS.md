# FortnaPlus `.mnu` Relationships (Site Forge interest)
Explicit cross-table name tokens from `DLIST` in the analyzed `fortna.mnu` + `project.mnu`. Similar equipment names are **not** evidence.

**Upgrade:** runtime-proven STATIC/DYNAMIC selection resolution is documented in
`docs/FORTNAPLUS_MNU_RUNTIME.md` and emitted by `tools/scripts/fortna_mnu_runtime.py`.
This file remains the earlier DLIST inventory snapshot.

Total DLIST name tokens: **2386** · resolved: **2342** · unresolved: **44**

## Site Forge-relevant definitions

| Name | Status | Notes |
|---|---|---|
| `Conveyor` | **PRESENT** | origins=['FORTNA']; fields=61; referencedBy=411 |
| `Mtrchain` | **PRESENT** | origins=['FORTNA']; fields=30; referencedBy=1 |
| `Convpath` | **PRESENT** | origins=['FORTNA']; fields=6; referencedBy=0 |
| `Configio` | **PRESENT** | origins=['FORTNA']; fields=12; referencedBy=2 |
| `FORTNADT` | **PRESENT** | origins=['FORTNA']; fields=16; referencedBy=0 |
| `EStop` | **PRESENT** | origins=['FORTNA']; fields=4; referencedBy=1 |
| `Jamcheck` | **PRESENT** | origins=['FORTNA']; fields=17; referencedBy=3 |
| `Jamzones` | **PRESENT** | origins=['FORTNA']; fields=14; referencedBy=6 |
| `MergeBoss` | **PRESENT** | origins=['FORTNA']; fields=12; referencedBy=2 |
| `MergeInputs` | **PRESENT** | origins=['FORTNA']; fields=36; referencedBy=2 |
| `MergeRoute` | **PRESENT** | origins=['FORTNA']; fields=9; referencedBy=6 |
| `Machine` | **PRESENT** | origins=['FORTNA']; fields=44; referencedBy=64 |
| `MsgMap` | **PRESENT** | origins=['FORTNA']; fields=22; referencedBy=6 |
| `Area` | **NOT_FOUND** | not present as MNUNAME and not named in DLIST |
| `Sorter` | **NOT_FOUND** | not present as MNUNAME and not named in DLIST |
| `Sawtooth` | **NOT_FOUND** | not present as MNUNAME and not named in DLIST |

### Related family names present as definitions
- Sorter/Srt*: `SorterSfgScrn`, `SorterUtil`, `Sorters`, `SrtAppControl`, `SrtBadGapCnfg`, `SrtCommMsgMatch`, `SrtDevice1`, `SrtDevice2`, `SrtDevice3`, `SrtDevice4`, `SrtDevice5`, `SrtHrtBeat`, `SrtInitNaList`, `SrtLaneNotAvail`, `SrtMsgUtil`, `SrtRndRobin`, `SrtScanBoss`, `SrtScanSts`, `SrtSimConfig`, `SrtTrack1`, `SrtTrack2`, `SrtTrack3`, `SrtTrack4`, `SrtTrack5`, `SrtTrkUtil`, `SrtZoneLane`, `SrtrSideTypes`, `SrtrStepTypes`, `SrtrUpdateParts`, `SrtrValTypes`, `SrtrWizardSteps`
- Saw*/Sawtooth: `SawLane`, `SawMenu`, `SawMerge`, `SawResvMode`, `SawState`

## Forward references (selected)

### `HeightWidth`
- `SensorType` → `SensorType` (origin=PROJECT, line=22)
- `PrintLine` → `PrintApplyLine` (origin=PROJECT, line=23)
- `BoxDetectIn` → `Conveyor` (origin=PROJECT, line=24)
- `TooShortIn` → `Conveyor` (origin=PROJECT, line=25)
- `Height1In` → `Conveyor` (origin=PROJECT, line=26)
- `Height2In` → `Conveyor` (origin=PROJECT, line=27)
- `LPNScanZone` → `ScnScanZone` (origin=PROJECT, line=46)
- `VerifyScanZone` → `ScnScanZone` (origin=PROJECT, line=47)

### `Mtrchain`
- `Motor_Ndx` → `Conveyor` (origin=FORTNA, line=1973)
- `Timer_Name` → `timemenu` (origin=FORTNA, line=1974)
- `Motor_Chained1` → `Conveyor` (origin=FORTNA, line=1976)
- `Motor_Chained2` → `Conveyor` (origin=FORTNA, line=1977)
- `Motor_Chained3` → `Conveyor` (origin=FORTNA, line=1978)
- `Motor_Chained4` → `Conveyor` (origin=FORTNA, line=1979)
- `Motor_Chained5` → `Conveyor` (origin=FORTNA, line=1980)
- `Motor_Chained6` → `Conveyor` (origin=FORTNA, line=1981)
- `Motor_Chained7` → `Conveyor` (origin=FORTNA, line=1982)
- `Motor_Chained8` → `Conveyor` (origin=FORTNA, line=1983)
- `Motor_Chained9` → `Conveyor` (origin=FORTNA, line=1984)
- `Motor_Chained10` → `Conveyor` (origin=FORTNA, line=1985)
- `Motor_Aux` → `Conveyor` (origin=FORTNA, line=1986)
- `RUN Timer_Name` → `timemenu` (origin=FORTNA, line=1987)
- `GoUntil` → `Conveyor` (origin=FORTNA, line=1988)
- `Enabled` → `Conveyor` (origin=FORTNA, line=1989)
- `Horn` → `horns` (origin=FORTNA, line=1990)
- `Heater Bit` → `Conveyor` (origin=FORTNA, line=1992)
- `Heater Error` → `Errors` (origin=FORTNA, line=1994)
- `Stop Zone` → `Jamzones` (origin=FORTNA, line=1997)

### `EStop`
- `Part` → `Conveyor` (origin=FORTNA, line=667)
- `Error` → `Errors` (origin=FORTNA, line=668)

### `MergeBoss`
- `Process` → `ProcType` (origin=FORTNA, line=1730)
- `Owner` → `Machine` (origin=FORTNA, line=1731)
- `OperableInput` → `Conveyor` (origin=FORTNA, line=1734)
- `SwitchDelayTimer` → `timemenu` (origin=FORTNA, line=1736)

### `MergeInputs`
- `MergeBoss` → `MergeBoss` (origin=FORTNA, line=1758)
- `MyTurn` → `MergeState` (origin=FORTNA, line=1760)
- `MergeRoute` → `MergeRoute` (origin=FORTNA, line=1763)
- `Presense` → `Conveyor` (origin=FORTNA, line=1766)
- `LaneReadyInput1` → `Conveyor` (origin=FORTNA, line=1767)
- `LaneReadyInput2` → `Conveyor` (origin=FORTNA, line=1768)
- `ReleaseIO` → `Conveyor` (origin=FORTNA, line=1769)
- `FullClearTimerName` → `timemenu` (origin=FORTNA, line=1772)
- `ClrTimerName` → `timemenu` (origin=FORTNA, line=1773)
- `RunTimerName` → `timemenu` (origin=FORTNA, line=1775)
- `LnClrTimerName` → `timemenu` (origin=FORTNA, line=1777)
- `RlsDelayTimerName` → `timemenu` (origin=FORTNA, line=1779)
- `InputDisabled` → `Conveyor` (origin=FORTNA, line=1782)
- `LatchOffTimer` → `timemenu` (origin=FORTNA, line=1785)
- `PitchTimerName` → `timemenu` (origin=FORTNA, line=1787)

### `Jamcheck`
- `Sensor_Name` → `Conveyor` (origin=FORTNA, line=1317)
- `Timer_Name` → `timemenu` (origin=FORTNA, line=1318)
- `Error_Name` → `Errors` (origin=FORTNA, line=1320)
- `Conveyor_Name` → `Conveyor` (origin=FORTNA, line=1321)
- `Zone` → `Jamzones` (origin=FORTNA, line=1322)
- `Jam_Owner` → `Machine` (origin=FORTNA, line=1323)
- `Motor Under Jam Eye` → `Conveyor` (origin=FORTNA, line=1325)
- `ClearJamSignal` → `Conveyor` (origin=FORTNA, line=1328)
- `L2_ClearJamSignal` → `Conveyor` (origin=FORTNA, line=1331)

### `Jamzones`
- `Latch Bit` → `Conveyor` (origin=FORTNA, line=1338)
- `Jammed Bit` → `Conveyor` (origin=FORTNA, line=1339)
- `Start Stop Timer` → `timemenu` (origin=FORTNA, line=1340)
- `Zone Owner ` → `Machine` (origin=FORTNA, line=1341)
- `Enable Bit` → `Conveyor` (origin=FORTNA, line=1342)
- `Start Button` → `Conveyor` (origin=FORTNA, line=1343)
- `Stop Button` → `Conveyor` (origin=FORTNA, line=1344)
- `Reset Button` → `Conveyor` (origin=FORTNA, line=1345)
- `StartStopZone` → `StartStopZones` (origin=FORTNA, line=1346)

### `Conveyor`
- `Device_Description` → `convdesc` (origin=FORTNA, line=507)
- `Part_Number` → `partnum` (origin=FORTNA, line=508)
- `IO_Module_Type` → `iomodule` (origin=FORTNA, line=509)
- `Contact_Type` → `contact` (origin=FORTNA, line=511)
- `Belt_Info` → `belt` (origin=FORTNA, line=514)
- `Type` → `convtype` (origin=FORTNA, line=521)
- `Font` → `fontmenu` (origin=FORTNA, line=526)
- `Trigger1` → `Trigrset` (origin=FORTNA, line=534)
- `Trigger2` → `Trigrset` (origin=FORTNA, line=535)
- `Trigger3` → `Trigrset` (origin=FORTNA, line=536)
- `Trigger4` → `Trigrset` (origin=FORTNA, line=537)
- `ProcNum` → `ProcType` (origin=FORTNA, line=538)
- `Machine_Name` → `Machine` (origin=FORTNA, line=540)
- `Default Colors` → `Convclr` (origin=FORTNA, line=557)

## Reverse lookup — `Conveyor`
Referenced by **411** field(s).

- `Accumulator.DischargeSSV` (origin=FORTNA, line=13)
- `Accumulator.SlugModeSSV` (origin=FORTNA, line=14)
- `Accumulator.SecondarySSV` (origin=FORTNA, line=15)
- `Accumulator.FullPE` (origin=FORTNA, line=16)
- `Accumulator.orControlByIO` (origin=FORTNA, line=25)
- `Accumulator.RunningAUX` (origin=FORTNA, line=28)
- `Animate.Conv` (origin=FORTNA, line=70)
- `Batches.BatchOUTPUT` (origin=FORTNA, line=228)
- `BeaconInfo.BeaconOutput` (origin=FORTNA, line=246)
- `BeaconTrigger.TriggerInput` (origin=FORTNA, line=268)
- `ChainOiler.ConvRunIO` (origin=FORTNA, line=361)
- `ChainOiler.OilerRunIO` (origin=FORTNA, line=362)
- `ChartMenu.Chart Conveyor Part` (origin=FORTNA, line=370)
- `ChartMenu.Chart Label Part` (origin=FORTNA, line=371)
- `CombBoss.Operable_Input` (origin=FORTNA, line=429)
- `CombLane.Presense_Eye` (origin=FORTNA, line=438)
- `CombLane.Analog_IO` (origin=FORTNA, line=439)
- `CombLane.Wide_Box` (origin=FORTNA, line=445)
- `CombLane.GoFast` (origin=FORTNA, line=450)
- `CombLane.GoSlow` (origin=FORTNA, line=451)
- `CombLane.GoStop` (origin=FORTNA, line=452)
- `CombLane.AccumSSV` (origin=FORTNA, line=454)
- `CombLane.EnableIO` (origin=FORTNA, line=455)
- `Convpath.Piece` (origin=FORTNA, line=566)
- `Convpath.PEname` (origin=FORTNA, line=570)
- `DbHistConfig.IOSignal` (origin=FORTNA, line=610)
- `EStop.Part` (origin=FORTNA, line=667)
- `Encoders.Encoder I/O` (origin=FORTNA, line=673)
- `Encoders.DupToMemBit` (origin=FORTNA, line=679)
- `Encoders.StoponError` (origin=FORTNA, line=683)
- `Encoders.EnableBit` (origin=FORTNA, line=684)
- `Encoders.NoSortonError` (origin=FORTNA, line=686)
- `Encoders.Failed` (origin=FORTNA, line=687)
- `EnergyTrigger.TriggerInput` (origin=FORTNA, line=706)
- `EnergyZone.ZoneRUN` (origin=FORTNA, line=716)
- `EnergyZone.StopZoneOutput` (origin=FORTNA, line=719)
- `Error_Log.LinkPart` (origin=FORTNA, line=737)
- `ErrorAnalysis.LinkPart` (origin=FORTNA, line=744)
- `ErrorCustom1.LinkPart` (origin=FORTNA, line=754)
- `ErrorCustom2.LinkPart` (origin=FORTNA, line=764)
- `ErrorStatus.LinkPart` (origin=FORTNA, line=778)
- `ErrorStatusLog.LinkPart` (origin=FORTNA, line=787)
- `Errors.LinkPart` (origin=FORTNA, line=796)
- `Errors.TrigIO` (origin=FORTNA, line=797)
- `Errors.ScrnIO` (origin=FORTNA, line=799)
- `Errors.WcsOutput` (origin=FORTNA, line=809)
- `FAILSAFE.INPUT` (origin=FORTNA, line=850)
- `FAILSAFE.OUTPUT` (origin=FORTNA, line=851)
- `FAILSAFE.UPS_INPUT` (origin=FORTNA, line=852)
- `FAILSAFE.MEMORY_OUT` (origin=FORTNA, line=855)
- `Fulljam.Sensor_Name` (origin=FORTNA, line=903)
- `Fulljam.Conveyor_Name` (origin=FORTNA, line=910)
- `Fulljam.Motor Under Jam Eye` (origin=FORTNA, line=911)
- `Fulljam.Response IO` (origin=FORTNA, line=912)
- `Fullline.Sensor_Name` (origin=FORTNA, line=924)
- `Fullline.Conveyor_Name` (origin=FORTNA, line=930)
- `Fullline.Response IO` (origin=FORTNA, line=932)
- `Fullline.Go Until` (origin=FORTNA, line=934)
- `Fullline.FullClearOutput` (origin=FORTNA, line=939)
- `GapCfg.ProductINPUT` (origin=FORTNA, line=950)
- `GapCfg.RunningINPUT` (origin=FORTNA, line=951)
- `GapCfg.StopOUTPUT` (origin=FORTNA, line=954)
- `GpxBelt.InductPE` (origin=FORTNA, line=970)
- `GpxBelt.VFD_EN` (origin=FORTNA, line=971)
- `GpxBelt.VFD_S1` (origin=FORTNA, line=972)
- `GpxBelt.VFD_S2` (origin=FORTNA, line=973)
- `GpxBelt.VFD_S3` (origin=FORTNA, line=974)
- `GpxBelt.DischargePE` (origin=FORTNA, line=975)
- `HSPusher.WatchOutput` (origin=FORTNA, line=1022)
- `HSPusher.PulseOutput` (origin=FORTNA, line=1023)
- `HistConfig.IOSignal` (origin=FORTNA, line=1051)
- `IOCard.ErrorOutput` (origin=FORTNA, line=1185)
- `Inpoints.Induct I/O Name` (origin=FORTNA, line=1294)
- `Jamcheck.Sensor_Name` (origin=FORTNA, line=1317)
- `Jamcheck.Conveyor_Name` (origin=FORTNA, line=1321)
- `Jamcheck.Motor Under Jam Eye` (origin=FORTNA, line=1325)
- `Jamcheck.ClearJamSignal` (origin=FORTNA, line=1328)
- `Jamcheck.L2_ClearJamSignal` (origin=FORTNA, line=1331)
- `Jamzones.Latch Bit` (origin=FORTNA, line=1338)
- `Jamzones.Jammed Bit` (origin=FORTNA, line=1339)
- … +331 more (see `artifacts/mnu-relationships.json`)

## Semantics caution
These edges are **schema name tokens from DLIST**, not proven runtime joins, not physical topology, and not PLC tag ownership.
