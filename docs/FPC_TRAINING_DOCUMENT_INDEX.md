# FPC Training Document Index

Generated: `2026-09-12T19:02:09Z`

## Corpus

Roots under `docs/training/`:
- `FPC Documents 1/` — 41 documents
- `FPC-Docs 2/` — 7 documents
- `FPC Docs 3/` — 33 documents
- `P&A Documents/` — 16 documents

Zip archives present:
- `docs/training/FPC Docs 3.zip` (5116413 bytes)
- `docs/training/FPC Documents 1.zip` (8117348 bytes)
- `docs/training/FPC-Docs 2.zip` (2021004 bytes)
- `docs/training/P&A Documents.zip` (20922683 bytes)

Also present (not counted as a training document): `docs/training/P&A Documents/PASIM1-RUN.tar.gz` (16617894 bytes).

## Summary

- **Total documents:** 97
- **CRITICAL:** 7
- **HIGH:** 15
- **Reviewed (deep skim):** 18
- **Missing priority docs:** none

Relevance breakdown:
- CRITICAL: 7
- HIGH: 15
- MEDIUM: 40
- LOW: 35

## CRITICAL / HIGH

Priority docs marked `reviewed=yes` were deep-skimmed; other HIGH rows come from filename/heuristics plus light docx skim.

| Relevance | Reviewed | Title | File | Subsystem | Gen | Tables (sample) |
|---|---|---|---|---|---|---|
| CRITICAL | yes | FPC Merge Modules | `docs/training/FPC Documents 1/FPC-Merge-Modules.docx` | merge | PLC_GEN | SimpleMerge, MergeBoss, MergeInputs, MergeRoute, MergeNotBusy, MergeRunOutputs, MergeStopOutputs, SawMerge, … |
| CRITICAL | yes | FPC High-Speed Sawtooth Merge | `docs/training/FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx` | merge/sawtooth | PLC_GEN | HSSawMerge, HSSawLane, HSSawParm, HSSawSim, SawLane, SawMerge, Fullline, Inpoints, … |
| CRITICAL | yes | FPC Motor Startup Chains | `docs/training/FPC Documents 1/FPC-Motor-Startup-Chains.docx` | motors | PLC_GEN | Mtrchain, Conveyor, Convclr, Jamzones, Fulljam, Fullline, Errors |
| CRITICAL | yes | FPC Sorter Control Module | `docs/training/FPC Docs 3/FPC-Sorter-Control-Module.docx` | sorter | PLC_GEN | Sorters, SrtAppControl, SrtScanBoss, SrtZoneLane, SrtBadGapCnfg, SrtLaneNotAvail, SrtRndRobin, SrtTrack1, … |
| CRITICAL | yes | FPC Shifter And Sorter Configuration | `docs/training/FPC Docs 3/FPC-Shifter-And-Sorter-Configuration.docx` | sorter/shifter | PLC_GEN | Sorters, SortBuff, SortData, SrtBadGapCnfg, SrtZoneLane, ScnScanDevice, Conveyor, Encoders, … |
| CRITICAL | yes | FPC Fulls, Jams and Fulljams | `docs/training/FPC Documents 1/FPC-Fulls-Jams-Fulljams.docx` | zones/full_jam | PLC_GEN | Fullline, Jamcheck, Fulljam, Jamzones, Conveyor, Errors, Batches |
| CRITICAL | yes | FPC Start/Stop Zones | `docs/training/FPC Docs 3/FPC-StartStopZones.docx` | zones/safety | PLC_GEN | StartStopZones, Jamzones, Jamcheck, CombinedJamZones, CombinedEnableBits, Mtrchain, Conveyor, Errors, … |
| HIGH | yes | FPC Gapping Modules | `docs/training/FPC Documents 1/FPC-Gapping-Modules.docx` | gapping | PLC_GEN | NewGapper, NewGapperStates, ZprTickGapper, ZprGapperZone, ServoGapper, CapacityIO, CapacityBoss, CapacityGapCtrl, … |
| HIGH | no | FPC Disable Bits | `docs/training/FPC Documents 1/FPC-Disable-Bits.docx` | io | IO | Conveyor, FORTNADT, Fullline, scanstat |
| HIGH | yes | FPC FastIO Configuration | `docs/training/FPC Documents 1/FPC-FastIO-Configuration.docx` | io | IO | FastIO, Configio, Conveyor, Machine |
| HIGH | yes | FPC IOCard Interfaces | `docs/training/FPC Documents 1/FPC-IOCard-Interfaces.docx` | io | IO | IOCard, IOCardResp, Configio, FORTNADT, ABS_CARD_INFO, KTX_RIO_ADAPTERS, KTX_RAM, Conveyor, … |
| HIGH | yes | FPC View I/O Screen and FORTNADT Table | `docs/training/FPC Docs 3/FPC-The-ViewIO-Screen-and-FORTNADT-Table.docx` | io/ui | IO | FORTNADT, Configio, Conveyor, FastIO, flagmnu |
| HIGH | yes | FPC Machine MsgMap Configuration (Configuraton spelling) | `docs/training/FPC Documents 1/FPC-Machine-MsgMap-Configuraton.docx` | messaging | SITE_MODEL | Machine, MsgMap, Connect, Protocol, AsciiMnu, RecvStat, SendStat, MsgCR1, … |
| HIGH | yes | FPC Motor Speed Control | `docs/training/FPC Documents 1/FPC-Motor-Speed-Control.docx` | motors | PLC_GEN | SpdControl, Conveyor, ZipperLane |
| HIGH | yes | FPC Photoeye Status Reporting | `docs/training/FPC-Docs 2/FPC-Photoeye-Status-Reporting.docx` | photoeye | IO | PeList, PeDisplay, Batches, Conveyor |
| HIGH | yes | FPC Scanner Control Configuration | `docs/training/FPC Docs 3/FPC-Scanner-Control-Configuration.docx` | scanner | PLC_GEN | Scanners, ScnScanDevice, ScnScanZone, ScnDeviceErrIO, ScnZoneErrIO, SrtScanBoss, SrtTrack1, MsgMap, … |
| HIGH | yes | FPC Sorter Configuration Checklist | `docs/training/FPC Docs 3/FPC-SorterConfigurationChecklist.docx` | sorter | PLC_GEN | Batches, SrtAppControl, ScnScanZone, ScnScanDevice, SrtScanBoss, Machine, MsgMap, SrtZoneLane, … |
| HIGH | yes | Unit Sorter Control Software V1 rev25 DDD | `docs/training/FPC Docs 3/Unit Sorter Control Software V1 rev25 DDD.doc` | sorter/unit_sorter | PLC_GEN | SortData, Sorters, Groups, Machine, Outpoints, Conveyor, UnitScanBoss, UnitSrtAppCtrl, … |
| HIGH | yes | FPC Ctrl-F4 Table Distribution | `docs/training/FPC Documents 1/FPC-Ctrl-F4-Table-Distribution.docx` | table_distribution | SITE_MODEL | Conveyor, Mtrchain, StartStopZones, Jamzones, Jamcheck, Fullline, Fulljam, EStop, … |
| HIGH | no | FPC New Transfers | `docs/training/FPC Documents 1/FPC-New-Transfers.docx` | transfer | PLC_GEN | ConfigXfgScrn, Conveyor, Errors, HistConfig, Machine, MenuColumn, MsgCR1, MsgXDC1, … |
| HIGH | no | CombinedJamZones | `docs/training/FPC Documents 1/CombinedJamZones.docx` | zones | PLC_GEN | CombinedEnableBits, CombinedJamZones, Conveyor |
| HIGH | no | FPC INITERRORS Autogeneration for Jam Full EStop FullJam | `docs/training/FPC Documents 1/FPC-INITERRORS-Autogeneration-for-Jam-Full-EStop-FullJam.docx` | zones | PLC_GEN | Conveyor, Errors, flagmenu |

## Full inventory

| Rel | Type | Gen | Subsystem | Title | File | Reviewed | Tables |
|---|---|---|---|---|---|---|---|
| CRITICAL | module_ref | PLC_GEN | merge | FPC Merge Modules | `docs/training/FPC Documents 1/FPC-Merge-Modules.docx` | yes | SimpleMerge, MergeBoss, MergeInputs, MergeRoute, MergeNotBusy, MergeRunOutputs, … |
| CRITICAL | module_ref | PLC_GEN | merge/sawtooth | FPC High-Speed Sawtooth Merge | `docs/training/FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx` | yes | HSSawMerge, HSSawLane, HSSawParm, HSSawSim, SawLane, SawMerge, … |
| CRITICAL | module_ref | PLC_GEN | motors | FPC Motor Startup Chains | `docs/training/FPC Documents 1/FPC-Motor-Startup-Chains.docx` | yes | Mtrchain, Conveyor, Convclr, Jamzones, Fulljam, Fullline, … |
| CRITICAL | module_ref | PLC_GEN | sorter | FPC Sorter Control Module | `docs/training/FPC Docs 3/FPC-Sorter-Control-Module.docx` | yes | Sorters, SrtAppControl, SrtScanBoss, SrtZoneLane, SrtBadGapCnfg, SrtLaneNotAvail, … |
| CRITICAL | howto | PLC_GEN | sorter/shifter | FPC Shifter And Sorter Configuration | `docs/training/FPC Docs 3/FPC-Shifter-And-Sorter-Configuration.docx` | yes | Sorters, SortBuff, SortData, SrtBadGapCnfg, SrtZoneLane, ScnScanDevice, … |
| CRITICAL | module_ref | PLC_GEN | zones/full_jam | FPC Fulls, Jams and Fulljams | `docs/training/FPC Documents 1/FPC-Fulls-Jams-Fulljams.docx` | yes | Fullline, Jamcheck, Fulljam, Jamzones, Conveyor, Errors, … |
| CRITICAL | module_ref | PLC_GEN | zones/safety | FPC Start/Stop Zones | `docs/training/FPC Docs 3/FPC-StartStopZones.docx` | yes | StartStopZones, Jamzones, Jamcheck, CombinedJamZones, CombinedEnableBits, Mtrchain, … |
| HIGH | module_ref | PLC_GEN | gapping | FPC Gapping Modules | `docs/training/FPC Documents 1/FPC-Gapping-Modules.docx` | yes | NewGapper, NewGapperStates, ZprTickGapper, ZprGapperZone, ServoGapper, CapacityIO, … |
| HIGH | module_ref | IO | io | FPC Disable Bits | `docs/training/FPC Documents 1/FPC-Disable-Bits.docx` | no | Conveyor, FORTNADT, Fullline, scanstat |
| HIGH | howto | IO | io | FPC FastIO Configuration | `docs/training/FPC Documents 1/FPC-FastIO-Configuration.docx` | yes | FastIO, Configio, Conveyor, Machine |
| HIGH | module_ref | IO | io | FPC IOCard Interfaces | `docs/training/FPC Documents 1/FPC-IOCard-Interfaces.docx` | yes | IOCard, IOCardResp, Configio, FORTNADT, ABS_CARD_INFO, KTX_RIO_ADAPTERS, … |
| HIGH | howto | IO | io/ui | FPC View I/O Screen and FORTNADT Table | `docs/training/FPC Docs 3/FPC-The-ViewIO-Screen-and-FORTNADT-Table.docx` | yes | FORTNADT, Configio, Conveyor, FastIO, flagmnu |
| HIGH | howto | SITE_MODEL | messaging | FPC Machine MsgMap Configuration (Configuraton spelling) | `docs/training/FPC Documents 1/FPC-Machine-MsgMap-Configuraton.docx` | yes | Machine, MsgMap, Connect, Protocol, AsciiMnu, RecvStat, … |
| HIGH | module_ref | PLC_GEN | motors | FPC Motor Speed Control | `docs/training/FPC Documents 1/FPC-Motor-Speed-Control.docx` | yes | SpdControl, Conveyor, ZipperLane |
| HIGH | module_ref | IO | photoeye | FPC Photoeye Status Reporting | `docs/training/FPC-Docs 2/FPC-Photoeye-Status-Reporting.docx` | yes | PeList, PeDisplay, Batches, Conveyor |
| HIGH | module_ref | PLC_GEN | scanner | FPC Scanner Control Configuration | `docs/training/FPC Docs 3/FPC-Scanner-Control-Configuration.docx` | yes | Scanners, ScnScanDevice, ScnScanZone, ScnDeviceErrIO, ScnZoneErrIO, SrtScanBoss, … |
| HIGH | checklist | PLC_GEN | sorter | FPC Sorter Configuration Checklist | `docs/training/FPC Docs 3/FPC-SorterConfigurationChecklist.docx` | yes | Batches, SrtAppControl, ScnScanZone, ScnScanDevice, SrtScanBoss, Machine, … |
| HIGH | ddd | PLC_GEN | sorter/unit_sorter | Unit Sorter Control Software V1 rev25 DDD | `docs/training/FPC Docs 3/Unit Sorter Control Software V1 rev25 DDD.doc` | yes | SortData, Sorters, Groups, Machine, Outpoints, Conveyor, … |
| HIGH | procedure | SITE_MODEL | table_distribution | FPC Ctrl-F4 Table Distribution | `docs/training/FPC Documents 1/FPC-Ctrl-F4-Table-Distribution.docx` | yes | Conveyor, Mtrchain, StartStopZones, Jamzones, Jamcheck, Fullline, … |
| HIGH | module_ref | PLC_GEN | transfer | FPC New Transfers | `docs/training/FPC Documents 1/FPC-New-Transfers.docx` | no | ConfigXfgScrn, Conveyor, Errors, HistConfig, Machine, MenuColumn, … |
| HIGH | other | PLC_GEN | zones | CombinedJamZones | `docs/training/FPC Documents 1/CombinedJamZones.docx` | no | CombinedEnableBits, CombinedJamZones, Conveyor |
| HIGH | module_ref | PLC_GEN | zones | FPC INITERRORS Autogeneration for Jam Full EStop FullJam | `docs/training/FPC Documents 1/FPC-INITERRORS-Autogeneration-for-Jam-Full-EStop-FullJam.docx` | no | Conveyor, Errors, flagmenu |
| MEDIUM | module_ref | PLC_GEN | aux_controls | FPC Timers | `docs/training/FPC Docs 3/FPC-Timers.docx` | no | Machine, Supply, TIMElist |
| MEDIUM | module_ref | PLC_GEN | aux_controls | FPC Trigger Configuration | `docs/training/FPC Docs 3/FPC-Trigger-Configuration.docx` | no | Combos, Conveyor, Fullline, Jamcheck, Machine, Mtrchain, … |
| MEDIUM | module_ref | PLC_GEN | aux_controls | BeaconConfiguration | `docs/training/FPC Documents 1/BeaconConfiguration.docx` | no | Beacon, BeaconInfo, BeaconPattern, BeaconSimConfig, BeaconTrigger, Machine, … |
| MEDIUM | module_ref | PLC_GEN | aux_controls | CounterConfiguration | `docs/training/FPC Documents 1/CounterConfiguration.docx` | no | BeaconTrigger, Conveyor, CounterInfo, Counters, CounterTrigger |
| MEDIUM | module_ref | PLC_GEN | aux_controls | FPC HornControlModule | `docs/training/FPC Documents 1/FPC-HornControlModule.docx` | no |  |
| MEDIUM | module_ref | PLC_GEN | gapping | FPC ServoGapOptimizer | `docs/training/FPC Docs 3/FPC-ServoGapOptimizer.docx` | no | Encoders, GapOptSim, ServoGapOpt, SortData, Sorters |
| MEDIUM | module_ref | PLC_GEN | general | FPC SpecialFlags | `docs/training/FPC Docs 3/FPC-SpecialFlags.docx` | no | flagmenu, SpecialFlags |
| MEDIUM | module_ref | PLC_GEN | general | FPC StarTech Serial Port Configuration | `docs/training/FPC Docs 3/FPC-StarTech-Serial-Port-Configuration.docx` | no |  |
| MEDIUM | module_ref | PLC_GEN | general | AnalogCardModule | `docs/training/FPC Documents 1/AnalogCardModule.docx` | no | AnalogOutputs, Configio, Configuration, Errors, ServoGapper, VoltRange, … |
| MEDIUM | other | PLC_GEN | general | AutomationControllerHousekeeping | `docs/training/FPC Documents 1/AutomationControllerHousekeeping.docx` | no | Error_Log, Errors, EventLog, HouseKeep |
| MEDIUM | module_ref | PLC_GEN | general | ChainStretchModule | `docs/training/FPC Documents 1/ChainStretchModule.docx` | no | ChainStretch, Conveyor |
| MEDIUM | module_ref | PLC_GEN | general | Parts Database | `docs/training/FPC Documents 1/FPC-ConveyorPartsManagement.docx` | no | BeaconInfo, ButtonFontZoom, Colorset, ColorsGUI, Convclr, Conveyor, … |
| MEDIUM | module_ref | PLC_GEN | general | FPC EV10 Connections | `docs/training/FPC Documents 1/FPC-EV10-Connections.docx` | no | Conveyor, Errors, Errsever, LogLevel, Machine, MsgMap, … |
| MEDIUM | module_ref | PLC_GEN | general | FPC EndOfWaveModule | `docs/training/FPC Documents 1/FPC-EndOfWaveModule.docx` | no | Conveyor, Errors, procnames, SawLane, SawMerge |
| MEDIUM | module_ref | PLC_GEN | general | FPC Errors Configuration | `docs/training/FPC Documents 1/FPC-Errors-Configuration.docx` | no | Colorset, Error_Log, Errors, Errsever, Errsugt, Fulljam, … |
| MEDIUM | module_ref | PLC_GEN | general | FPC EtherNetIP Error Rate | `docs/training/FPC Documents 1/FPC-EtherNetIP-Error-Rate.xlsx` | no |  |
| MEDIUM | module_ref | PLC_GEN | general | FortnaPlus machine control software runs on QNX, a real-time operating system.  It is used to control the conveyor hardware.  User interface capabilities include: | `docs/training/FPC Documents 1/FPC-InchStoreModule.docx` | no | Conveyor, HSSawLane, InchStore |
| MEDIUM | module_ref | PLC_GEN | general | FPC Missing Pin Detection | `docs/training/FPC Documents 1/FPC-Missing-Pin-Detection.docx` | no | Errors, Errsugt, Machine, MissingPin |
| MEDIUM | module_ref | PLC_GEN | general | FPC PackLift Module | `docs/training/FPC-Docs 2/FPC-PackLift-Module.docx` | no | Errors, Machine, PackLiftConfig, PackLiftControl, PackLiftStates, Utilities |
| MEDIUM | module_ref | PLC_GEN | general | FPC RatePoints | `docs/training/FPC-Docs 2/FPC-RatePoints.docx` | no | Errors, RateCount, SawLane |
| MEDIUM | module_ref | PLC_GEN | general | FPC RemoteAuthorization | `docs/training/FPC-Docs 2/FPC-RemoteAuthorization.docx` | no | Connect, LogLevel, Machine, MenuMenu, MsgMap, Protocol, … |
| MEDIUM | other | SITE_MODEL | messaging | PC to PC Communications | `docs/training/FPC Docs 3/PC to PC Communications.doc` | no | HistData, Machine, MsgMap, RequestList |
| MEDIUM | other | SITE_MODEL | messaging | FPCMSG DSM DestinationStatusMessage | `docs/training/FPC Documents 1/FPCMSG-DSM-DestinationStatusMessage.docx` | no | DsmArea, DsmDest, DsmMsg, DsmStatus, Fullline, Machine, … |
| MEDIUM | other | SITE_MODEL | messaging | FPCMSG DSR DestinationStatusRequest | `docs/training/FPC Documents 1/FPCMSG-DSR-DestinationStatusRequest.docx` | no | Connect, DSRConfig, Sorters, SrtZoneLane, XfRouteTable |
| MEDIUM | other | SITE_MODEL | messaging | FPCMSG RHS RequestHostStatus | `docs/training/FPC Documents 1/FPCMSG-RHS-RequestHostStatus.docx` | no | Errors, Machine, MsgCR1, MsgGP1, MsgGP4, MsgMap, … |
| MEDIUM | checklist | PLC_GEN | print_apply | FPC PNA ConfigurationChecklist | `docs/training/P&A Documents/FPC-PNA-ConfigurationChecklist.docx` | no | AsciiMnu, Boss, Convert, Conveyor, CrrMsg, CsuMsg, … |
| MEDIUM | module_ref | PLC_GEN | print_apply | FPC PNA Print Apply Configuration | `docs/training/P&A Documents/FPC-PNA-Print-Apply-Configuration.docx` | no | BADREAD, Conveyor, Errors, FORTNADT, HeightWidth, LabelTemplates, … |
| MEDIUM | module_ref | PLC_GEN | print_apply | FPC PNA Transfer PrintAndApply | `docs/training/P&A Documents/FPC-PNA-Transfer-PrintAndApply.docx` | no | Configio, Conveyor, Errors, flagmenu, LabelTemplates, Machine, … |
| MEDIUM | module_ref | PLC_GEN | print_apply | FPC PNA ZebraPrinterConfiguration | `docs/training/P&A Documents/FPC-PNA-ZebraPrinterConfiguration.docx` | no | Machine |
| MEDIUM | module_ref | PLC_GEN | print_apply | Scanner Box Dimensions Configuration | `docs/training/P&A Documents/Scanner Box Dimensions Configuration.doc` | no | Conveyor, Errors, Line, Machine, MsgCR1, MsgDC1, … |
| MEDIUM | module_ref | PLC_GEN | scanner | FPC Scanner Stats History Module | `docs/training/FPC Docs 3/FPC-Scanner-Stats-History-Module.docx` | no | Conveyor, DbHistConfig, DbHistData, DbHistSummary, HistBoss, HistConfig, … |
| MEDIUM | simulation | PLC_GEN | scanner | FPC Transfer Scan Simulation | `docs/training/FPC Docs 3/FPC-Transfer-Scan-Simulation.docx` | no | ScnScanDevice, XfRouteBoss, XfRouteTable, XfrSimScans1, XfrSimScans5, XfSimConfig |
| MEDIUM | example | PLC_GEN | scanner | Scan TestPlan V1.0 | `docs/training/FPC Docs 3/Scan_TestPlan V1.0.doc` | no | Device, ScnScanDevice, ScnScanZone, SrtDevice1, SrtTrack1, XfrDevice, … |
| MEDIUM | other | PLC_GEN | scanner | FortnaPlus Scanner Statistics Configuration | `docs/training/FPC Docs 3/Setting_up_Scanner_Statistics_in_FPC_-_Display.docx` | no | Machine |
| MEDIUM | example | PLC_GEN | sorter | FPC Sorter Test Setup | `docs/training/FPC Docs 3/FPC-Sorter-Test-Setup.docx` | no | History, Machine, MsgMap, MsgTST, Protocol, Scanners, … |
| MEDIUM | module_ref | PLC_GEN | sorter | High Speed Pusher Configuration | `docs/training/FPC Docs 3/High Speed Pusher Configuration.doc` | no | HSPusher |
| MEDIUM | example | PLC_GEN | sorter | Sorter Design Example 20150908 | `docs/training/FPC Docs 3/Sorter Design Example 20150908.docx` | no |  |
| MEDIUM | simulation | PLC_GEN | sorter | FortnaPlus Sorter Simulation Guide | `docs/training/FPC Docs 3/Sorter Scan Simulation V1.2.docx` | no | History, SrtSimConfig |
| MEDIUM | example | PLC_GEN | transfer | FPC Transfer Configuration Example | `docs/training/FPC Docs 3/FPC-Transfer-Configuration-Example.docx` | no | Conveyor, CrrMsg, CsuMsg, DcmMsg, Fullline, LogLevel, … |
| MEDIUM | example | PLC_GEN | transfer | FPC Transfer Test Examples | `docs/training/FPC Docs 3/FPC-Transfer-Test-Examples.docx` | no | Conveyor, LogLevel, Machine, XfrBoss, XfrCfgDelayTmr, XfrCfgInput, … |
| LOW | module_ref | NONE | general | Log Search Module | `docs/training/FPC Docs 3/Log Search Module.doc` | no |  |
| LOW | module_ref | NONE | general | Pick to Light Configuration | `docs/training/FPC Docs 3/Pick to Light Configuration.doc` | no | Machine |
| LOW | module_ref | NONE | general | Preventive Maintenance Summary Module | `docs/training/FPC Docs 3/Preventive Maintenance Summary Module.doc` | no | PMEvents, Send |
| LOW | module_ref | NONE | general | Rel 10 Modules (Module List) | `docs/training/FPC Docs 3/Rel 10 Modules (Module List).docx` | no | Beacon, Conveyor, Jamcheck, Merges, Output, Pattern, … |
| LOW | other | UI_ONLY | general | SendConvImage | `docs/training/FPC Docs 3/SendConvImage.txt` | no | ScreenCapture |
| LOW | other | NONE | general | CarouselDetailDesign V1.0 (BCC) | `docs/training/FPC Documents 1/CarouselDetailDesign V1.0 (BCC).doc` | no | Beat, Configuration, Connect, Errors, Machine, MsgMap, … |
| LOW | other | UI_ONLY | general | ConvPhs2Png Setup | `docs/training/FPC Documents 1/ConvPhs2Png_Setup.txt` | no | ScreenCapture |
| LOW | other | NONE | general | EthernetIP HMS Support 20140626 | `docs/training/FPC Documents 1/EthernetIP_HMS_Support_20140626.docx` | no |  |
| LOW | module_ref | UI_ONLY | general | FortnaPlus has two distinct table types based on where the data is stored.  For most purposes, this distinction does not matter, but when using the search features, it is important to understand the difference.  In-memory tables are searched using C-language string comparisons.  Database tables are searched using SQL queries.  In-memory tables will always show all records, with each “find” operation taking you to the next matching row.  Database table searches will show only the rows that match.  Database tables will potentially contain data from all ACs in the system, not just the local AC, unlike in-memory tables. | `docs/training/FPC Documents 1/FPC-Advanced-Search-Feature.docx` | no | Error_Log, ErrorAnalysis, ErrorCustom1, ErrorCustom2, ErrorStatus, ErrorStatusLog, … |
| LOW | procedure | NONE | general | FPC InstallSystemFiles | `docs/training/FPC Documents 1/FPC-InstallSystemFiles.docx` | no |  |
| LOW | module_ref | NONE | integrations | FPC Data Export Module | `docs/training/FPC Documents 1/FPC-Data-Export-Module.docx` | no | Error_Log, ErrorAnalysis, Errors, ErrorStatusLog, HistData, Machine, … |
| LOW | module_ref | NONE | integrations | FortnaPlus accesses the MySQL database via ODBC.  Which database, and which user and password is defined in /etc/odbc.ini.  SERVER = localhost is the default, and refers to "this machine".  FortnaPlus requires access to two databases to function: fortna and information_schema.  Two others are defined in odbc.ini: test and myodbc3.  When changing odbc.ini to use a database on a remote machine, change all four entries to reference the desired SERVER by IP address for best results. | `docs/training/FPC Documents 1/FPC-MySQL-Database-Information.docx` | no | Conveyor, Error_Log, EventLog, Machine |
| LOW | module_ref | UI_ONLY | integrations | FPC OpenNMS Configuration | `docs/training/FPC-Docs 2/FPC-OpenNMS-Configuration.docx` | no | Machine, MsgNMS, WCSEvents |
| LOW | module_ref | NONE | integrations | FPC REST API | `docs/training/FPC-Docs 2/FPC-REST-API.docx` | no | Conveyor, LogLevel, Machine, Protocol, wcsSeverity, ZoneStates |
| LOW | other | NONE | power_energy | Power Roll Accumulation   Rel8.6M | `docs/training/FPC Docs 3/Power_Roll_Accumulation_-_Rel8.6M.doc` | no | Conveyor, Machine |
| LOW | module_ref | NONE | power_energy | FPC EnergyManagement | `docs/training/FPC Documents 1/FPC-EnergyManagement.docx` | no | EnergyTrigger, EnergyZone, Outpoints |
| LOW | module_ref | NONE | power_energy | FPC PowerFailUPSConfiguration | `docs/training/FPC-Docs 2/FPC-PowerFailUPSConfiguration.docx` | no | EventLog, UPSMenu |
| LOW | other | NONE | print_apply | Block Diagram | `docs/training/P&A Documents/Block Diagram.doc` | no | Header, Template |
| LOW | module_ref | NONE | print_apply | FPC PNA Label Accuracy Spreadsheet | `docs/training/P&A Documents/FPC-PNA-Label-Accuracy-Spreadsheet.xlsx` | no |  |
| LOW | module_ref | NONE | print_apply | FPC PNA Operators Screen | `docs/training/P&A Documents/FPC-PNA-Operators-Screen.docx` | no |  |
| LOW | module_ref | NONE | print_apply | FPC PNA PrintApplyFallback | `docs/training/P&A Documents/FPC-PNA-PrintApplyFallback.docx` | no | PrintApplyFallback |
| LOW | simulation | NONE | print_apply | FPC PNA PrintApplySimulation | `docs/training/P&A Documents/FPC-PNA-PrintApplySimulation.docx` | no | Connect, Conveyor, DeviceTrk, HeightWidth, Inpoints, LabelTemplates, … |
| LOW | example | NONE | print_apply | FPC PNA TestPlan Sorter | `docs/training/P&A Documents/FPC-PNA-TestPlan-Sorter.docx` | no | ConfigHistScrn, Configio, Connect, Conveyor, Errors, HeightWidth, … |
| LOW | module_ref | NONE | print_apply | FPC PNA ZebraPrintEngineAutomaticDisconnect | `docs/training/P&A Documents/FPC-PNA-ZebraPrintEngineAutomaticDisconnect.docx` | no |  |
| LOW | ddd | NONE | print_apply | FRD PrintApplyFallback20110518 | `docs/training/P&A Documents/FRD_PrintApplyFallback20110518.docx` | no | ctrlprocnames |
| LOW | ddd | NONE | print_apply | InkJet IDD20121217 | `docs/training/P&A Documents/InkJet_IDD20121217.docx` | no |  |
| LOW | other | NONE | print_apply | Print Apply McKesson Issues 20140605 | `docs/training/P&A Documents/Print Apply McKesson Issues 20140605.docx` | no |  |
| LOW | other | NONE | print_apply | PrintApplyDesign (Conv Design Layout) | `docs/training/P&A Documents/PrintApplyDesign (Conv Design Layout).docx` | no |  |
| LOW | ddd | HISTORICAL | sorter | Unit Sorter Control Software V1 rev24 DDD | `docs/training/FPC Docs 3/Unit Sorter Control Software V1 rev24 DDD.doc` | no | Assign, Assigned, Beat, Chute, ChuteChgDelay, Configuration, … |
| LOW | module_ref | HISTORICAL | transfer | FPC Old Transfers | `docs/training/FPC Documents 1/FPC-Old-Transfers.docx` | no | Connect, Conveyor, Errors, HistConfig, Machine, MsgMap, … |
| LOW | procedure | UI_ONLY | ui_admin | FPC Security Upgrade Procedure | `docs/training/FPC Docs 3/FPC-Security-Upgrade-Procedure.docx` | no | MenuMenu, procnames |
| LOW | howto | UI_ONLY | ui_admin | FPC SettingSecurityAccessRoles | `docs/training/FPC Docs 3/FPC-SettingSecurityAccessRoles.docx` | no | Animate, BuildTest, Conveyor, DbHistConfig, DbHistData, Encoders, … |
| LOW | module_ref | UI_ONLY | ui_admin | FPC TranslationManagement | `docs/training/FPC Docs 3/FPC-TranslationManagement.docx` | no | History, Machine, Merges |
| LOW | module_ref | UI_ONLY | ui_admin | FPC MenuPad | `docs/training/FPC Documents 1/FPC-MenuPad.docx` | no | Errors, MenuPad |
| LOW | module_ref | UI_ONLY | ui_admin | FPC OnScreenButtons | `docs/training/FPC Documents 1/FPC-OnScreenButtons.docx` | no | ButtonFontZoom, Conveyor, flagmenu, Flags, Layerson |

## Notes

- `tables_mentioned` prefers exact ASC-like names from documents; validated against `workspace/active/RUN/FORTNA` when present.
- Office lock files (`~$*`) are excluded.
- Rebuild: `python tools/scripts/fortna_fpc_document_inventory.py`
