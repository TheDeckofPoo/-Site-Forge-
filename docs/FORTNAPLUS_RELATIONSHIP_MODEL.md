# FortnaPlus Relationship Model

Generated: `2026-09-12T19:04:17.678839+00:00`

## Edge types

| Type | Meaning |
|------|---------|
| `EXPLICIT_REFERENCE` | Field present on RUN header that names another table's identity |
| `DOCUMENTED_RELATIONSHIP` | Training docs describe the link (may mirror an explicit FK) |
| `DERIVED_RELATIONSHIP` | Inferred from naming/timer conventions evidenced in RUN (e.g. ReserveTM→Fullline) |
| `OPTIONAL_RELATIONSHIP` | Field exists but link is situational / often blank |
| `RUNTIME_DATA` | Queue/track slot references — not static topology |

**Nodes:** 40  
**Edges:** 156

## Graph edges

### EXPLICIT_REFERENCE

- `Conveyor` → `Conveyor` via `Motor` — Motor IO_Name in same table
- `Conveyor` → `Conveyor` via `Drive` — Drive / VFD IO_Name when present
- `Conveyor` → `Machine` via `Machine_Name`
- `FORTNADT` → `Machine` via `Machine`
- `IOCard` → `Machine` via `Machine`
- `Jamzones` → `StartStopZones` via `StartStopZone`
- `Jamcheck` → `Conveyor` via `Sensor_Name` — PHOTOCELL IO_Name
- `Jamcheck` → `Conveyor` via `Conveyor_Name`
- `Jamcheck` → `Jamzones` via `Zone`
- `Jamcheck` → `Conveyor` via `Motor Under Jam Eye` — Motor IO under jam PE
- `Fulljam` → `Conveyor` via `Sensor_Name`
- `Fulljam` → `Conveyor` via `Conveyor_Name`
- `Fulljam` → `Conveyor` via `Motor Under Jam Eye`
- `Fullline` → `Conveyor` via `Sensor_Name`
- `Fullline` → `Conveyor` via `Conveyor_Name`
- `Mtrchain` → `Conveyor` via `Motor_Name`
- `Mtrchain` → `Conveyor` via `Motor_Chained1`
- `Mtrchain` → `Conveyor` via `Motor_Chained2`
- `Mtrchain` → `Conveyor` via `Motor_Chained3`
- `Mtrchain` → `Conveyor` via `Motor_Chained4`
- `Mtrchain` → `Conveyor` via `Motor_Chained5`
- `Mtrchain` → `Conveyor` via `Motor_Chained6`
- `Mtrchain` → `Conveyor` via `Motor_Chained7`
- `Mtrchain` → `Conveyor` via `Motor_Chained8`
- `Mtrchain` → `Conveyor` via `Motor_Chained9`
- `Mtrchain` → `Conveyor` via `Motor_Chained10`
- `Mtrchain` → `Conveyor` via `Motor_Aux`
- `SawLane` → `SawMerge` via `SawMerge`
- `SawLane` → `Conveyor` via `PhotoEyeIO`
- `SawLane` → `Conveyor` via `DisableIO`
- `SawMerge` → `Conveyor` via `MotorIO`
- `SawMerge` → `Conveyor` via `ReserveIN`
- `HSSawLane` → `HSSawMerge` via `SawMerge`
- `HSSawLane` → `Conveyor` via `LanePE`
- `HSSawMerge` → `Conveyor` via `MergeRunIO`
- `HSSawMerge` → `Conveyor` via `MergeInduct`
- `HSSawMerge` → `Machine` via `ControlMachine`
- `HSSawParm` → `HSSawLane` via `SawLane`
- `HSSawSim` → `HSSawLane` via `SawLane`
- `Merges` → `Conveyor` via `Presense_Eye1`
- `Merges` → `Conveyor` via `Release_IO1`
- `Merges` → `Conveyor` via `Presense_Eye2`
- `Merges` → `Conveyor` via `Release_IO2`
- `SimpleMerge` → `Conveyor` via `MainLineRun`
- `SimpleMerge` → `Conveyor` via `LaneRun`
- `SimpleMerge` → `Conveyor` via `MainLinePresence`
- `SimpleMerge` → `Conveyor` via `LanePresence`
- `SimpleMerge` → `Machine` via `Machine`
- `MergeInputs` → `MergeBoss` via `MergeBoss`
- `MergeInputs` → `MergeRoute` via `MergeRoute`
- `MergeInputs` → `Conveyor` via `Presense`
- `MergeInputs` → `Conveyor` via `ReleaseIO`
- `MergeRoute` → `MergeInputs` via `MergeInputs`
- `ZipperMerge` → `Conveyor` via `MergeMtr`
- `ZipperMerge` → `Conveyor` via `MergeInduct`
- `ZipperMerge` → `Conveyor` via `MergeRunIO`
- `ZipperMerge` → `Machine` via `ControlMachine`
- `ZipperLane` → `ZipperMerge` via `ZipperMerge`
- `ZipperLane` → `Conveyor` via `AccumIO`
- `Sorters` → `Encoders` via `Encoder ioName`
- `Sorters` → `Machine` via `Machine`
- `SrtAppControl` → `Machine` via `ControlMachine`
- `SrtAppControl` → `Conveyor` via `SorterCnvMtr`
- `SrtScanBoss` → `SrtAppControl` via `AppSorter`
- `SrtZoneLane` → `SrtAppControl` via `AppSorter`
- `XfRouteTable` → `XfRouteBoss` via `BossRecord`
- `XfRouteBoss` → `Conveyor` via `XferCnvMtr`
- `MsgMap` → `Machine` via `Machine_Name`
- `Encoders` → `Conveyor` via `Encoder I/O`
- `Encoders` → `Conveyor` via `EnableBit`

### DOCUMENTED_RELATIONSHIP

- `Configio` → `IOCard` via `Interface` — Interface name ties to IOCard / adapter
- `IOCard` → `Configio` via `Name` — Configio.Interface / card binding
- `Jamzones` → `Jamcheck` via `Zone Name` — Jamcheck.Zone references this name
- `Jamcheck` → `Errors` via `Error_Name`
- `Fulljam` → `Errors` via `Error_Name`
- `Fullline` → `Errors` via `Error_Name`
- `StartStopZones` → `Jamzones` via `Zone Name` — Jamzones.StartStopZone → this name
- `EStop` → `Errors` via `Error`
- `SawMerge` → `SawLane` via `Name` — SawLane.SawMerge → this Name
- `HSSawLane` → `HSSawParm` via `Name` — HSSawParm.SawLane → lane
- `HSSawMerge` → `HSSawLane` via `Name`
- `HSSawState` → `HSSawLane` via `Name` — HSSawLane.pLaneState display vocabulary
- `MergeBoss` → `MergeInputs` via `Name`
- `ZipperMerge` → `ZipperLane` via `Name`
- `Sorters` → `SrtAppControl` via `Sorter Name`
- `Sorters` → `SrtZoneLane` via `Sorter Name`
- `SrtAppControl` → `Sorters` via `AvailAppSorter`
- `SrtAppControl` → `SrtScanBoss` via `Name`
- `XfRouteBoss` → `XfRouteTable` via `Name`
- `Machine` → `MsgMap` via `Machine_Name` — MsgMap.Machine_Name → this
- `Machine` → `Conveyor` via `Machine_Name`
- `Machine` → `IOCard` via `Machine_Name`
- `MsgMap` → `MsgWCS` via `Menu_Name` — WCS_EVENT often maps Menu_Name=MsgWCS
- `MsgTrack` → `MsgMap` via `Menu_Name` — Referenced from MsgMap when used
- `MsgWCS` → `MsgMap` via `Menu_Name`
- `WCSEvents` → `MsgWCS` via `WCSDestination`
- `Encoders` → `Sorters` via `Encoder Name` — Sorters.Encoder ioName
- `Jamzones` → `StartStopZones` via `StartStopZone` — Training: StartStopZones + Jamzones configured together
- `CombinedJamZones` → `Jamzones` via `JamEnableCombined` — Combined jam enable aggregates jam zones
- `SawLane` → `SawMerge` via `SawMerge` — Lane belongs to merge boss
- `HSSawLane` → `HSSawMerge` via `SawMerge` — HS lane belongs to HS merge

### DERIVED_RELATIONSHIP

- `Conveyor` → `Mtrchain` via `In Motor Chain` — Flag that motor participates in a chain
- `FORTNADT` → `Configio` via `HiBank` — Bank coordinates align with Configio
- `FORTNADT` → `Configio` via `LoBank`
- `Configio` → `Conveyor` via `Desc` — Often matches Conveyor IO_Name
- `Fullline` → `SawLane` via `Clr_Timer_Name` — SawLane.ReserveTM often references tmfc* clear timers
- `SawLane` → `Fullline` via `ReserveTM` — Often tmfc* clear timer from Fullline
- `MergeInputs` → `Fullline` via `FullClearTimerName`
- `ZipperLane` → `Fullline` via `FullClearTimer`
- `SrtZoneLane` → `Fullline` via `FullClearTimer`
- `MsgWCS` → `WCSEvents` via `Destination` — Topics align with WCSDestination
- `MsgMap` → `WCSEvents` via `Message_Name` — WCS_EVENT message name pairs with WCSEvents catalog

### OPTIONAL_RELATIONSHIP

- `Conveyor` → `IOCard` via `IO_Module_Type`
- `Conveyor` → `convtype` via `Type` — Lookup of conveyor type vocabulary
- `Configio` → `Machine` via `Process`
- `Jamzones` → `Encoders` via `Zone Name` — Encoders.Jamzone may match zone name
- `Fulljam` → `Conveyor` via `Response IO`
- `Fullline` → `Conveyor` via `Response IO`
- `Mtrchain` → `StartStopZones` via `Stop Zone`
- `EStop` → `Conveyor` via `Part` — Part may name related equipment when used
- `Convpath` → `Conveyor` via `PEname` — PE name when populated
- `Convpath` → `Conveyor` via `PE_at`
- `SawLane` → `Conveyor` via `LaneIN`
- `SawLane` → `Conveyor` via `EndOfWave_PE`
- `SawMerge` → `Sorters` via `Name` — Sorter name may match merge process
- `HSSawLane` → `SawMerge` via `SawMerge` — May reference classic merge name
- `HSSawParm` → `Conveyor` via `InputSignal`
- `MergeBoss` → `Machine` via `Owner`
- `MergeInputs` → `Conveyor` via `LaneReadyInput1`
- `MergeRoute` → `Conveyor` via `MergeOutputs`
- `ZipperLane` → `Conveyor` via `EnableIO`
- `ZipperLane` → `Conveyor` via `PreMergeInduct`
- `Sorters` → `Conveyor` via `DivertEnableIO`
- `SrtAppControl` → `MsgMap` via `CrrMsgTable`
- `SrtScanBoss` → `ScnScanZone` via `ScanZone`
- `SrtScanBoss` → `SrtZoneLane` via `Lane`
- `SrtZoneLane` → `Conveyor` via `LaneEnableSignal`
- `XfRouteTable` → `Conveyor` via `ErrorIO`
- `XfRouteBoss` → `ScnScanZone` via `ScanZone`
- `XfRouteBoss` → `MsgMap` via `CrrMsgTable`
- `MsgMap` → `MsgTrack` via `Menu_Name`
- `WCSEvents` → `Machine` via `WCSMachProc`
- `WCSEvents` → `MsgMap` via `EventName`
- `Encoders` → `Jamzones` via `Jamzone`
- `Conveyor` → `PeList` via `IO_Name` — PeList/PeDisplay reference conveyor records for PE status reporting

### RUNTIME_DATA

- `Convpath` → `Conveyor` via `Input` — Runtime path metrics — not static FK
- `Convpath` → `Conveyor` via `Output`
- `SrtZoneLane` → `SrtTrack1` via `Name` — SrtTrack*.SrtZoneLaneRec runtime link
- `SrtTrack` → `SrtAppControl` via `SrtAppRec`
- `SrtTrack` → `SrtZoneLane` via `SrtZoneLaneRec`
- `SrtTrack` → `SrtZoneLane` via `SorterLane`
- `SrtTrack` → `SrtScanBoss` via `ScanZoneID`
- `XfrTrack` → `XfRouteBoss` via `RouteBossRec`
- `XfrTrack` → `XfRouteTable` via `RouteTableRec`
- `XfrTrack` → `SrtAppControl` via `SrtAppRec`
- `Sorters` → `SrtTrack` via `Data LowRec,Data HighRec,Buffer LowRec,Buffer HighRec` — Sorter record ranges index into track/buffer menus

## Zone model summary

### EngineeringArea

PLC/generation area grouping for equipment. Often NOT present as a reliable RUN geometry/area table; may require ENGINEER_CONFIGURED_REQUIRED default Area_1.
- RUN tables: _none_
- Provenance: ENGINEER_CONFIGURED_REQUIRED when absent from RUN

### StartStopZone

Start/stop island with request flags and owners; referenced by Jamzones.
- RUN tables: `StartStopZones`, `Jamzones`
- Provenance: RUN_EXPLICIT

### EStopZone

E-stop circuit/device entries distinct from start/stop and jam zones.
- RUN tables: `EStop`
- Provenance: RUN_EXPLICIT when EStop.asc present

### JamZone

Jam ownership zone for Jamcheck / encoder jamzone / combined jam enables.
- RUN tables: `Jamzones`, `Jamcheck`, `CombinedJamZones`, `Fulljam`
- Provenance: RUN_EXPLICIT

### SorterTrackingZone

HostZone / ScanZoneID / XfrZoneID on track and zone-lane tables — logical host zones for sortation/transfer, not StartStop islands.
- RUN tables: `SrtZoneLane`, `SrtTrack`, `SrtScanBoss`, `XfrTrack`
- Provenance: RUN_EXPLICIT + RUNTIME_DATA

## Rules

- Do not invent fields absent from RUN headers.
- Convpath/Pathsets empty ⇒ no P→P topology claim.
- SrtTrack/XfrTrack/MsgWCS are runtime evidence, not divert maps.
- No Greensboro-specific relationship rules.
