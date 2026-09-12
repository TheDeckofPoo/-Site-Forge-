# FortnaPlus Table Reference

Generated: `2026-09-12T19:04:18.009575+00:00`

## Source of truth

- **RUN ASC headers** = factual schema (fields that exist).
- **Training docs** = generic semantic knowledge (purpose, how tables relate).
- Finished PLC is **not** a source for this knowledge base.
- No site-specific hardcoding in knowledge rules.

Tables: **40**

## Families

### `Conveyor`

- **Subsystem:** transport_io
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/Conveyor.asc`
- **Purpose:** Primary plant equipment / device table: mechanical conveyors (STRAIGHT/CURVE/BELT/…), motors, photocells, beacons, and related I/O with geometry and controller ownership.
- **Row semantics:** One row per named IO_Name. Type discriminates device class (conveyor geometry vs MOTOR vs PHOTOCELL vs BEACON). Geometry fields apply to mechanical conveyors; Motor / Drive link ownership; Machine_Name scopes controller.
- **Identity fields:** `IO_Name`
- **Key fields:** `IO_Name`, `Type`, `Motor`, `Drive`, `Machine_Name`, `X_cord`, `Y_cord`, `Length`, `Width`, `Angle`, `IO_Address_Word`, `IO_Address_Bit`, `In Motor Chain`
- **Relationship fields:**
  - `Motor` → `Conveyor` (EXPLICIT_REFERENCE) — Motor IO_Name in same table
  - `Drive` → `Conveyor` (EXPLICIT_REFERENCE) — Drive / VFD IO_Name when present
  - `Machine_Name` → `Machine` (EXPLICIT_REFERENCE)
  - `In Motor Chain` → `Mtrchain` (DERIVED_RELATIONSHIP) — Flag that motor participates in a chain
  - `IO_Module_Type` → `IOCard` (OPTIONAL_RELATIONSHIP)
  - `Type` → `convtype` (OPTIONAL_RELATIONSHIP) — Lookup of conveyor type vocabulary
- **Active row rules:**
  - IO_Name present and not placeholder (N/A, INVALID, NONE, ===…===)
  - Type not INVALID (supporting; mechanical conveyors use CONVEYOR_TYPES)
- **Inactive row rules:**
  - IO_Name blank / placeholder
  - Type=INVALID with no usable identity
  - Rows only in old.Conveyor.asc* → HISTORICAL_OR_STALE
- **Optional feature rules:**
  - NoseOver / Infeed_Tangent / Discharge_Tangent are equipment features, not topology FKs
  - Disable I/O / Overide I/O optional force paths
- **Controller scope:** Prefer Conveyor.asc.<CONTROLLER> overlay when present; else base Conveyor.asc. Machine_Name further filters ownership; unknown ownership does not delete the row.
- **Generation implications:**
  - Mechanical conveyors (CONVEYOR_TYPES) feed Transport / area PLC generation when INCLUDED
  - PHOTOCELL rows seed PE logic; MOTOR/VFD rows seed motor chains and drives
  - Geometry alone does not prove conveyor successor topology
- **Document sources:**
  - FPC-ConveyorPartsManagement (FPC Documents 1/FPC-ConveyorPartsManagement.docx)
  - FPC-Photoeye-Status-Reporting (FPC-Docs 2/FPC-Photoeye-Status-Reporting.docx)
  - FPC-Motor-Speed-Control (FPC Documents 1/FPC-Motor-Speed-Control.docx)
  - FPC High-Speed Sawtooth Merge (docs/training/FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx)
  - FPC Motor Startup Chains (docs/training/FPC Documents 1/FPC-Motor-Startup-Chains.docx)
  - FPC Shifter And Sorter Configuration (docs/training/FPC Docs 3/FPC-Shifter-And-Sorter-Configuration.docx)
  - FPC Fulls, Jams and Fulljams (docs/training/FPC Documents 1/FPC-Fulls-Jams-Fulljams.docx)
  - FPC Start/Stop Zones (docs/training/FPC Docs 3/FPC-StartStopZones.docx)
  - FPC Gapping Modules (docs/training/FPC Documents 1/FPC-Gapping-Modules.docx)
  - FPC Disable Bits (docs/training/FPC Documents 1/FPC-Disable-Bits.docx)
  - FPC FastIO Configuration (docs/training/FPC Documents 1/FPC-FastIO-Configuration.docx)
  - FPC IOCard Interfaces (docs/training/FPC Documents 1/FPC-IOCard-Interfaces.docx)
  - FPC View I/O Screen and FORTNADT Table (docs/training/FPC Docs 3/FPC-The-ViewIO-Screen-and-FORTNADT-Table.docx)
  - FPC Motor Speed Control (docs/training/FPC Documents 1/FPC-Motor-Speed-Control.docx)
  - FPC Photoeye Status Reporting (docs/training/FPC-Docs 2/FPC-Photoeye-Status-Reporting.docx)
  - Unit Sorter Control Software V1 rev25 DDD (docs/training/FPC Docs 3/Unit Sorter Control Software V1 rev25 DDD.doc)
  - FPC Ctrl-F4 Table Distribution (docs/training/FPC Documents 1/FPC-Ctrl-F4-Table-Distribution.docx)
  - FPC New Transfers (docs/training/FPC Documents 1/FPC-New-Transfers.docx)
  - CombinedJamZones (docs/training/FPC Documents 1/CombinedJamZones.docx)
  - FPC INITERRORS Autogeneration for Jam Full EStop FullJam (docs/training/FPC Documents 1/FPC-INITERRORS-Autogeneration-for-Jam-Full-EStop-FullJam.docx)

### `FORTNADT`

- **Subsystem:** io_runtime
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/FORTNADT.asc`
- **Purpose:** Runtime bit/force state for View I/O — live forced-on/off and bank state per I/O point.
- **Row semantics:** Indexed parallel to I/O points (not a named equipment table). Tracks Bits_On_Off, Forced_On/Off, Inverted, bank, Machine, InOut.
- **Identity fields:** _none_
- **Key fields:** `Bits_On_Off`, `Forced_On`, `Forced_Off`, `Inverted`, `HiBank`, `LoBank`, `Machine`, `InOut`
- **Relationship fields:**
  - `Machine` → `Machine` (EXPLICIT_REFERENCE)
  - `HiBank` → `Configio` (DERIVED_RELATIONSHIP) — Bank coordinates align with Configio
  - `LoBank` → `Configio` (DERIVED_RELATIONSHIP)
- **Active row rules:**
  - Row slot corresponding to a configured Configio / Conveyor I/O point
- **Inactive row rules:**
  - Unused bank slots with no Configio mapping
- **Optional feature rules:**
  - Forced_On / Forced_Off are operator/debug overrides
- **Controller scope:** Machine column scopes which controller owns the bit image.
- **Generation implications:**
  - Not a PLC generation source table; HMI/runtime diagnostic only
- **Document sources:**
  - FPC-The-ViewIO-Screen-and-FORTNADT-Table (FPC Docs 3/FPC-The-ViewIO-Screen-and-FORTNADT-Table.docx)
  - FPC Disable Bits (docs/training/FPC Documents 1/FPC-Disable-Bits.docx)
  - FPC IOCard Interfaces (docs/training/FPC Documents 1/FPC-IOCard-Interfaces.docx)
  - FPC View I/O Screen and FORTNADT Table (docs/training/FPC Docs 3/FPC-The-ViewIO-Screen-and-FORTNADT-Table.docx)

### `Configio`

- **Subsystem:** io_map
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/Configio.asc`
- **Purpose:** I/O point configuration map: bank/word/bit, direction, interface, and process ownership.
- **Row semantics:** One configured I/O description per Desc (or bank/word coordinate).
- **Identity fields:** `Desc`
- **Key fields:** `Desc`, `Bank`, `Octal_Word`, `LoHi`, `In_Out`, `I_O_Type`, `Interface`, `Process`, `Status`
- **Relationship fields:**
  - `Interface` → `IOCard` (DOCUMENTED_RELATIONSHIP) — Interface name ties to IOCard / adapter
  - `Desc` → `Conveyor` (DERIVED_RELATIONSHIP) — Often matches Conveyor IO_Name
  - `Process` → `Machine` (OPTIONAL_RELATIONSHIP)
- **Active row rules:**
  - Desc present and not placeholder
  - Bank/Octal_Word assigned
- **Inactive row rules:**
  - Blank Desc with no bank assignment
- **Optional feature rules:**
  - Granularity / Countdown optional timing
- **Controller scope:** May appear as Configio.asc.<CONTROLLER>; overlay wins collisions.
- **Generation implications:**
  - Feeds IO_MAP / module addressing when generating PLC I/O
- **Document sources:**
  - FPC-IOCard-Interfaces (FPC Documents 1/FPC-IOCard-Interfaces.docx)
  - FPC-FastIO-Configuration (FPC Documents 1/FPC-FastIO-Configuration.docx)
  - FPC FastIO Configuration (docs/training/FPC Documents 1/FPC-FastIO-Configuration.docx)
  - FPC IOCard Interfaces (docs/training/FPC Documents 1/FPC-IOCard-Interfaces.docx)
  - FPC View I/O Screen and FORTNADT Table (docs/training/FPC Docs 3/FPC-The-ViewIO-Screen-and-FORTNADT-Table.docx)

### `IOCard`

- **Subsystem:** io_hardware
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/IOCard.asc`
- **Purpose:** Physical / logical I/O card and adapter inventory (RIO, EtherNet/IP ABS, Optomux, etc.).
- **Row semantics:** One row per named card/adapter with Type, ports, machine, and ABS network fields.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `Desc`, `Type`, `Machine`, `BasePort`, `ABS_IP`, `ABS_HostName`, `CardNode`, `Status`, `Process`
- **Relationship fields:**
  - `Machine` → `Machine` (EXPLICIT_REFERENCE)
  - `Name` → `Configio` (DOCUMENTED_RELATIONSHIP) — Configio.Interface / card binding
- **Active row rules:**
  - Name present and not placeholder
- **Inactive row rules:**
  - Blank Name
  - historical old.* copies
- **Optional feature rules:**
  - ABS_* fields apply to EtherNet/IP adapters only
  - ErrorOutput / ErrorACTION / ErrorBIT optional fault signaling
- **Controller scope:** Machine column + optional overlay files scope ownership.
- **Generation implications:**
  - Defines adapter inventory for I/O mapping; does not invent module catalog entries
- **Document sources:**
  - FPC-IOCard-Interfaces (FPC Documents 1/FPC-IOCard-Interfaces.docx)
  - FPC IOCard Interfaces (docs/training/FPC Documents 1/FPC-IOCard-Interfaces.docx)

### `Jamzones`

- **Subsystem:** area_safety
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/Jamzones.asc`
- **Purpose:** Jam / start-stop zone definitions linking request flags, buttons, and StartStopZones.
- **Row semantics:** One named Zone Name owning jam latch/jammed bits and optional StartStopZone link.
- **Identity fields:** `Zone Name`
- **Key fields:** `Zone Name`, `Start Request Flag`, `Stop Request Flag`, `Latch Bit`, `Jammed Bit`, `Enable Bit`, `StartStopZone`, `Zone Owner `, `Start Button`, `Stop Button`, `Reset Button`
- **Relationship fields:**
  - `StartStopZone` → `StartStopZones` (EXPLICIT_REFERENCE)
  - `Zone Name` → `Jamcheck` (DOCUMENTED_RELATIONSHIP) — Jamcheck.Zone references this name
  - `Zone Name` → `Encoders` (OPTIONAL_RELATIONSHIP) — Encoders.Jamzone may match zone name
- **Active row rules:**
  - Zone Name present and not placeholder
- **Inactive row rules:**
  - Blank Zone Name
  - old.Jamzones.asc* historical
- **Optional feature rules:**
  - JamEnableDontDelay optional start behavior
- **Controller scope:** Base + optional controller overlay; Zone Owner may name owning process.
- **Generation implications:**
  - Jam zone membership drives area safety / jam program grouping
- **Document sources:**
  - FPC-StartStopZones (FPC Docs 3/FPC-StartStopZones.docx)
  - FPC-Fulls-Jams-Fulljams (FPC Documents 1/FPC-Fulls-Jams-Fulljams.docx)
  - CombinedJamZones (docs/training/FPC Documents 1/CombinedJamZones.docx)
  - FPC Motor Startup Chains (docs/training/FPC Documents 1/FPC-Motor-Startup-Chains.docx)
  - FPC Shifter And Sorter Configuration (docs/training/FPC Docs 3/FPC-Shifter-And-Sorter-Configuration.docx)
  - FPC Fulls, Jams and Fulljams (docs/training/FPC Documents 1/FPC-Fulls-Jams-Fulljams.docx)
  - FPC Start/Stop Zones (docs/training/FPC Docs 3/FPC-StartStopZones.docx)
  - FPC Ctrl-F4 Table Distribution (docs/training/FPC Documents 1/FPC-Ctrl-F4-Table-Distribution.docx)

### `Jamcheck`

- **Subsystem:** area_safety
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/Jamcheck.asc`
- **Purpose:** Jam detection points: sensor PE, timer, error, conveyor, and jam zone ownership.
- **Row semantics:** One jam check per Desc/Sensor_Name linking a PE timer to Conveyor_Name and Zone.
- **Identity fields:** `Desc`, `Sensor_Name`
- **Key fields:** `Desc`, `Sensor_Name`, `Timer_Name`, `Timer_Preset`, `Error_Name`, `Conveyor_Name`, `Zone`, `Jam_Owner`, `Motor Under Jam Eye`
- **Relationship fields:**
  - `Sensor_Name` → `Conveyor` (EXPLICIT_REFERENCE) — PHOTOCELL IO_Name
  - `Conveyor_Name` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Zone` → `Jamzones` (EXPLICIT_REFERENCE)
  - `Motor Under Jam Eye` → `Conveyor` (EXPLICIT_REFERENCE) — Motor IO under jam PE
  - `Error_Name` → `Errors` (DOCUMENTED_RELATIONSHIP)
- **Active row rules:**
  - Sensor_Name or Desc present and not placeholder
  - Timer_Name assigned for armed jam checks
- **Inactive row rules:**
  - Blank Sensor_Name and Desc
  - old.Jamcheck.asc*
- **Optional feature rules:**
  - ClearErrorWithJam / ClearJamSignal / RequireL2Reset optional clear policy
- **Controller scope:** Overlay preferred; Jam_Owner may imply process/controller.
- **Generation implications:**
  - Generates jam timer / PE monitoring when INCLUDED
- **Document sources:**
  - FPC-Fulls-Jams-Fulljams (FPC Documents 1/FPC-Fulls-Jams-Fulljams.docx)
  - FPC-StartStopZones (FPC Docs 3/FPC-StartStopZones.docx)
  - FPC Fulls, Jams and Fulljams (docs/training/FPC Documents 1/FPC-Fulls-Jams-Fulljams.docx)
  - FPC Start/Stop Zones (docs/training/FPC Docs 3/FPC-StartStopZones.docx)
  - FPC Ctrl-F4 Table Distribution (docs/training/FPC Documents 1/FPC-Ctrl-F4-Table-Distribution.docx)

### `Fulljam`

- **Subsystem:** area_safety
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/Fulljam.asc`
- **Purpose:** Full-jam detection: sustained full condition that escalates to jam/error response.
- **Row semantics:** Named full-jam sensor with set/clear timers, conveyor, motor-under-eye, owner.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `Sensor_Name`, `Enabled`, `Timer_Name`, `Clr_Timer_Name`, `Error_Name`, `Conveyor_Name`, `Motor Under Jam Eye`, `Response IO`, `Owner`
- **Relationship fields:**
  - `Sensor_Name` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Conveyor_Name` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Motor Under Jam Eye` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Error_Name` → `Errors` (DOCUMENTED_RELATIONSHIP)
  - `Response IO` → `Conveyor` (OPTIONAL_RELATIONSHIP)
- **Active row rules:**
  - Name or Sensor_Name present
  - Enabled indicates armed when used
- **Inactive row rules:**
  - Blank Name and Sensor_Name
  - old.Fulljam.asc*
- **Optional feature rules:**
  - DisableBit / Invert / ReSound Horn optional
- **Controller scope:** Owner + overlay scope.
- **Generation implications:**
  - Full-jam logic pairs with Fullline clear timers; INITERRORS may autogen errors
- **Document sources:**
  - FPC-Fulls-Jams-Fulljams (FPC Documents 1/FPC-Fulls-Jams-Fulljams.docx)
  - FPC-INITERRORS-Autogeneration-for-Jam-Full-EStop-FullJam (FPC Documents 1/FPC-INITERRORS-Autogeneration-for-Jam-Full-EStop-FullJam.docx)
  - FPC Motor Startup Chains (docs/training/FPC Documents 1/FPC-Motor-Startup-Chains.docx)
  - FPC Fulls, Jams and Fulljams (docs/training/FPC Documents 1/FPC-Fulls-Jams-Fulljams.docx)
  - FPC Ctrl-F4 Table Distribution (docs/training/FPC Documents 1/FPC-Ctrl-F4-Table-Distribution.docx)

### `Fullline`

- **Subsystem:** area_safety
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/Fullline.asc`
- **Purpose:** Line-full / accumulation full detection with set/clear timers and response I/O.
- **Row semantics:** One full point per Desc/Sensor_Name; Clr_Timer_* used by sawtooth ReserveTM links.
- **Identity fields:** `Desc`, `Sensor_Name`
- **Key fields:** `Desc`, `Sensor_Name`, `Timer_Name`, `Clr_Timer_Name`, `Clr_Timer_Preset`, `Error_Name`, `Conveyor_Name`, `Response IO`, `DontFireResponse`, `FullClearOutput`
- **Relationship fields:**
  - `Sensor_Name` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Conveyor_Name` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Clr_Timer_Name` → `SawLane` (DERIVED_RELATIONSHIP) — SawLane.ReserveTM often references tmfc* clear timers
  - `Error_Name` → `Errors` (DOCUMENTED_RELATIONSHIP)
  - `Response IO` → `Conveyor` (OPTIONAL_RELATIONSHIP)
- **Active row rules:**
  - Sensor_Name or Desc present
  - Timer_Name assigned when armed
- **Inactive row rules:**
  - Blank identity
  - old.Fullline.asc*
- **Optional feature rules:**
  - DontFireResponse / NoGap / FullClear* optional behaviors
- **Controller scope:** Base + overlay; no Greensboro-specific rules.
- **Generation implications:**
  - Full PE timers feed accumulation and sawtooth reservation timing
- **Document sources:**
  - FPC-Fulls-Jams-Fulljams (FPC Documents 1/FPC-Fulls-Jams-Fulljams.docx)
  - FPC Merge Modules (docs/training/FPC Documents 1/FPC-Merge-Modules.docx)
  - FPC High-Speed Sawtooth Merge (docs/training/FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx)
  - FPC Motor Startup Chains (docs/training/FPC Documents 1/FPC-Motor-Startup-Chains.docx)
  - FPC Fulls, Jams and Fulljams (docs/training/FPC Documents 1/FPC-Fulls-Jams-Fulljams.docx)
  - FPC Gapping Modules (docs/training/FPC Documents 1/FPC-Gapping-Modules.docx)
  - FPC Disable Bits (docs/training/FPC Documents 1/FPC-Disable-Bits.docx)
  - FPC Ctrl-F4 Table Distribution (docs/training/FPC Documents 1/FPC-Ctrl-F4-Table-Distribution.docx)

### `Mtrchain`

- **Subsystem:** motor_control
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/Mtrchain.asc`
- **Purpose:** Motor startup chains: ordered downstream motors that start after a lead motor/timer.
- **Row semantics:** One chain head Motor_Name with Motor_Chained1..10 followers, aux, stop zone, heater options.
- **Identity fields:** `Motor_Name`
- **Key fields:** `Motor_Name`, `Motor_Ndx`, `Timer_Name`, `Timer_Preset`, `Motor_Chained1`, `Motor_Chained2`, `Motor_Aux`, `Enabled`, `Stop Zone`, `Horn`
- **Relationship fields:**
  - `Motor_Name` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Motor_Chained1` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Motor_Chained2` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Motor_Chained3` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Motor_Chained4` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Motor_Chained5` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Motor_Chained6` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Motor_Chained7` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Motor_Chained8` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Motor_Chained9` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Motor_Chained10` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Motor_Aux` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Stop Zone` → `StartStopZones` (OPTIONAL_RELATIONSHIP)
- **Active row rules:**
  - Motor_Name present and not placeholder
- **Inactive row rules:**
  - Blank Motor_Name
  - old.Mtrchain.asc*
- **Optional feature rules:**
  - Heater Bit / AutoSelectHtr optional
  - ForceAux / GoUntil optional runtime aids
- **Controller scope:** Overlay wins; chains may cross conveyors owned by one controller.
- **Generation implications:**
  - Explicit RUN motor topology for startup sequencing — prefer over P-number order
- **Document sources:**
  - FPC-Motor-Startup-Chains (FPC Documents 1/FPC-Motor-Startup-Chains.docx)
  - FPC Motor Startup Chains (docs/training/FPC Documents 1/FPC-Motor-Startup-Chains.docx)
  - FPC Start/Stop Zones (docs/training/FPC Docs 3/FPC-StartStopZones.docx)
  - FPC Ctrl-F4 Table Distribution (docs/training/FPC Documents 1/FPC-Ctrl-F4-Table-Distribution.docx)

### `StartStopZones`

- **Subsystem:** area_safety
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/StartStopZones.asc`
- **Purpose:** Start/stop zone state machine rows (request flags, owners) referenced by Jamzones.
- **Row semantics:** One Zone Name with StartReqFlag/StopReqFlag and owner controls.
- **Identity fields:** `Zone Name`
- **Key fields:** `Zone Name`, `StartReqFlag`, `StopReqFlag`, `State`, `StartOwnerCtl`, `StopOwnerCtl`
- **Relationship fields:**
  - `Zone Name` → `Jamzones` (DOCUMENTED_RELATIONSHIP) — Jamzones.StartStopZone → this name
- **Active row rules:**
  - Zone Name present and not placeholder
- **Inactive row rules:**
  - Blank Zone Name
  - old.StartStopZones.asc*
- **Controller scope:** Base + overlay; owners name controlling process bits.
- **Generation implications:**
  - Groups conveyors into start/stop islands for area PLC
- **Document sources:**
  - FPC-StartStopZones (FPC Docs 3/FPC-StartStopZones.docx)
  - FPC Start/Stop Zones (docs/training/FPC Docs 3/FPC-StartStopZones.docx)
  - FPC Ctrl-F4 Table Distribution (docs/training/FPC Documents 1/FPC-Ctrl-F4-Table-Distribution.docx)

### `EStop`

- **Subsystem:** area_safety
- **Confidence:** MEDIUM
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/EStop.asc`
- **Purpose:** E-stop device / circuit inventory (Desc/Part) with linked Error name.
- **Row semantics:** One E-stop Desc or Part entry; Error ties to Errors table when populated.
- **Identity fields:** `Desc`, `Part`
- **Key fields:** `Desc`, `Part`, `Error`
- **Relationship fields:**
  - `Error` → `Errors` (DOCUMENTED_RELATIONSHIP)
  - `Part` → `Conveyor` (OPTIONAL_RELATIONSHIP) — Part may name related equipment when used
- **Active row rules:**
  - Desc or Part present and not placeholder
- **Inactive row rules:**
  - Blank Desc and Part
  - old.EStop.asc*
- **Controller scope:** Present when site configures E-stop table; overlay optional.
- **Generation implications:**
  - E-stop zones are distinct from StartStop and Jam zones
  - INITERRORS may autogen related errors
- **Document sources:**
  - FPC-INITERRORS-Autogeneration-for-Jam-Full-EStop-FullJam (FPC Documents 1/FPC-INITERRORS-Autogeneration-for-Jam-Full-EStop-FullJam.docx)
  - FPC Ctrl-F4 Table Distribution (docs/training/FPC Documents 1/FPC-Ctrl-F4-Table-Distribution.docx)

### `Convpath`

- **Subsystem:** tracking
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/Convpath.asc`
- **Purpose:** Carton/piece path tracking slots (Piece + PE_at/PEname). Not a static conveyor successor graph.
- **Row semantics:** Slot rows for tracked pieces. On many RUNs rows are placeholders (Piece=INVALID, Input/Output=0) — do not treat as P→P topology.
- **Identity fields:** `Piece`
- **Key fields:** `Piece`, `Input`, `Output`, `PE_at`, `PEname`
- **Relationship fields:**
  - `PEname` → `Conveyor` (OPTIONAL_RELATIONSHIP) — PE name when populated
  - `PE_at` → `Conveyor` (OPTIONAL_RELATIONSHIP)
  - `Input` → `Conveyor` (RUNTIME_DATA) — Runtime path metrics — not static FK
  - `Output` → `Conveyor` (RUNTIME_DATA)
- **Active row rules:**
  - Piece present and not INVALID/placeholder
- **Inactive row rules:**
  - Piece=INVALID / blank
  - Input/Output zero placeholders
- **Controller scope:** Usually base-only shared tracking table.
- **Generation implications:**
  - Do not derive Transport topology from Convpath unless active named pieces exist
  - Physical topology remains engineer/geometry when Convpath unpopulated

### `SawLane`

- **Subsystem:** sawtooth
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/SawLane.asc`
- **Purpose:** Classic sawtooth merge lane configuration (PE, reserve timing, EOW, merge parent).
- **Row semantics:** One named lane linked to SawMerge with PhotoEyeIO, ReserveTM, slice timing, EOW I/O.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `SawMerge`, `PhotoEyeIO`, `DisableIO`, `SliceSeconds`, `ReserveWhen`, `ReserveSeconds`, `ReserveTM`, `AllowedToRun`, `LaneIN`, `ApproachUP`, `CollisionUP`, `pState`
- **Relationship fields:**
  - `SawMerge` → `SawMerge` (EXPLICIT_REFERENCE)
  - `PhotoEyeIO` → `Conveyor` (EXPLICIT_REFERENCE)
  - `DisableIO` → `Conveyor` (EXPLICIT_REFERENCE)
  - `ReserveTM` → `Fullline` (DERIVED_RELATIONSHIP) — Often tmfc* clear timer from Fullline
  - `LaneIN` → `Conveyor` (OPTIONAL_RELATIONSHIP)
  - `EndOfWave_PE` → `Conveyor` (OPTIONAL_RELATIONSHIP)
- **Active row rules:**
  - Name present and not placeholder
  - SawMerge linked for active lanes
- **Inactive row rules:**
  - Blank Name
  - AllowedToRun/explicit disable without merge link
- **Optional feature rules:**
  - EOW_* fields optional End-of-Wave feature
  - ReserveFLAG / ReserveRATE optional reservation modes
- **Controller scope:** Strongly controller-overlaid (SawLane.asc.<CONTROLLER>).
- **Generation implications:**
  - Active SawLane+SawMerge → sawtooth_merges discovery; library path still feature-gated
- **Document sources:**
  - FPC-Merge-Modules (FPC Documents 1/FPC-Merge-Modules.docx)
  - FPC-HighSpeedSawtoothMerge (FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx)
  - FPC Merge Modules (docs/training/FPC Documents 1/FPC-Merge-Modules.docx)
  - FPC High-Speed Sawtooth Merge (docs/training/FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx)

### `SawMerge`

- **Subsystem:** sawtooth
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/SawMerge.asc`
- **Purpose:** Classic sawtooth merge collector / boss (motor, reservation input, slice timing).
- **Row semantics:** One named merge with MotorIO, ReserveIN, LaneEnableDelayTM, live slice status.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `MotorIO`, `ReserveIN`, `LaneEnableDelayTM`, `pSliceSeconds`, `EOW_RelAllPB`, `EOW_AutoRel`
- **Relationship fields:**
  - `MotorIO` → `Conveyor` (EXPLICIT_REFERENCE)
  - `ReserveIN` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Name` → `SawLane` (DOCUMENTED_RELATIONSHIP) — SawLane.SawMerge → this Name
  - `Name` → `Sorters` (OPTIONAL_RELATIONSHIP) — Sorter name may match merge process
- **Active row rules:**
  - Name present
  - MotorIO or ReserveIN assigned for active merges
- **Inactive row rules:**
  - Blank Name
- **Optional feature rules:**
  - EOW_* optional
  - LogMe debug
- **Controller scope:** Controller overlay preferred.
- **Generation implications:**
  - Collector motor/enable path for sawtooth PLC when generation supported
- **Document sources:**
  - FPC-Merge-Modules (FPC Documents 1/FPC-Merge-Modules.docx)
  - FPC-HighSpeedSawtoothMerge (FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx)
  - FPC Merge Modules (docs/training/FPC Documents 1/FPC-Merge-Modules.docx)
  - FPC High-Speed Sawtooth Merge (docs/training/FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx)

### `HSSawLane`

- **Subsystem:** sawtooth_hs
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/HSSawLane.asc`
- **Purpose:** High-speed sawtooth lane FSM: slow/fast/accum I/O, LanePE, opportunistic feed, offsets.
- **Row semantics:** Named HS lane under HSSawMerge/SawMerge with LanePE and speed action bits.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `Enabled`, `SawMerge`, `LanePE`, `LaneSlow`, `LaneFast`, `AccumFast`, `Opportunistic`, `RunSlowOffset`, `StopFastOffset`, `RunFastOffset`, `pLaneState`
- **Relationship fields:**
  - `SawMerge` → `HSSawMerge` (EXPLICIT_REFERENCE)
  - `SawMerge` → `SawMerge` (OPTIONAL_RELATIONSHIP) — May reference classic merge name
  - `LanePE` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Name` → `HSSawParm` (DOCUMENTED_RELATIONSHIP) — HSSawParm.SawLane → lane
- **Active row rules:**
  - Name present
  - Enabled when site uses HS module
- **Inactive row rules:**
  - Blank Name
  - Enabled off with no I/O
- **Optional feature rules:**
  - Opportunistic / OpportunSingle optional feed modes
  - GapError / ResetGapError optional
- **Controller scope:** Often empty of active named rows even when table present.
- **Generation implications:**
  - HS path is optional upgrade over classic SawLane; only use when active rows exist
- **Document sources:**
  - FPC-HighSpeedSawtoothMerge (FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx)
  - FPC High-Speed Sawtooth Merge (docs/training/FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx)

### `HSSawMerge`

- **Subsystem:** sawtooth_hs
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/HSSawMerge.asc`
- **Purpose:** High-speed sawtooth merge boss: reservation creation, induct, encoder mode, control machine.
- **Row semantics:** Named HS merge with MergeRunIO, MergeInduct, TimeBasedEncoder, ControlMachine.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `CreateResrv`, `MergeRunIO`, `MergeInduct`, `TimeBasedEncoder`, `ControlMachine`, `pCurrentLane`
- **Relationship fields:**
  - `MergeRunIO` → `Conveyor` (EXPLICIT_REFERENCE)
  - `MergeInduct` → `Conveyor` (EXPLICIT_REFERENCE)
  - `ControlMachine` → `Machine` (EXPLICIT_REFERENCE)
  - `Name` → `HSSawLane` (DOCUMENTED_RELATIONSHIP)
- **Active row rules:**
  - Name present and not placeholder
- **Inactive row rules:**
  - Blank Name
- **Optional feature rules:**
  - pSimOn simulation
- **Controller scope:** ControlMachine scopes HS merge.
- **Generation implications:**
  - When active, upgrades sawtooth model beyond classic SawMerge fields
- **Document sources:**
  - FPC-HighSpeedSawtoothMerge (FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx)
  - FPC High-Speed Sawtooth Merge (docs/training/FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx)

### `HSSawParm`

- **Subsystem:** sawtooth_hs
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/HSSawParm.asc`
- **Purpose:** Per-lane HS parameters: reservation inches/spacing, slug gap, priority, speed, enable.
- **Row semantics:** Parameter set named and linked to SawLane.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `SawLane`, `Type`, `ResrvInches`, `ResrvTotal`, `ResrvSpacing`, `MaxCartonLen`, `SlugGap`, `Priority`, `LaneSpeed`, `Enable`
- **Relationship fields:**
  - `SawLane` → `HSSawLane` (EXPLICIT_REFERENCE)
  - `InputSignal` → `Conveyor` (OPTIONAL_RELATIONSHIP)
- **Active row rules:**
  - Name present
  - SawLane linked
  - Enable when used
- **Inactive row rules:**
  - Blank Name
- **Optional feature rules:**
  - Override optional
- **Controller scope:** Follows HS lane/merge controller scope.
- **Generation implications:**
  - Parameter source for HS reservation geometry
- **Document sources:**
  - FPC-HighSpeedSawtoothMerge (FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx)
  - FPC High-Speed Sawtooth Merge (docs/training/FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx)

### `HSSawState`

- **Subsystem:** sawtooth_hs
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/HSSawState.asc`
- **Purpose:** Lookup vocabulary for HS lane FSM state display names.
- **Row semantics:** One Name per state label (e.g. Stopped, Wait PE On, Feed Slow).
- **Identity fields:** _none_
- **Key fields:** _none in RUN headers_
- **Relationship fields:**
  - `Name` → `HSSawLane` (DOCUMENTED_RELATIONSHIP) — HSSawLane.pLaneState display vocabulary
- **Active row rules:**
  - Name present
- **Inactive row rules:**
  - Blank Name
- **Controller scope:** Shared lookup; not controller-overlaid typically.
- **Generation implications:**
  - Display/state labels only — not control logic source
- **Document sources:**
  - FPC-HighSpeedSawtoothMerge (FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx)

### `HSSawSim`

- **Subsystem:** sawtooth_hs
- **Confidence:** MEDIUM
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/HSSawSim.asc`
- **Purpose:** HS sawtooth simulation rows (create boxes, length/gap, force PE).
- **Row semantics:** Named sim profile linked to SawLane.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `EnableSrt`, `CreateBoxes`, `SawLane`, `LengthInches`, `GapInches`
- **Relationship fields:**
  - `SawLane` → `HSSawLane` (EXPLICIT_REFERENCE)
- **Active row rules:**
  - Name present
  - EnableSrt/CreateBoxes when simulating
- **Inactive row rules:**
  - Blank Name
- **Controller scope:** Test/sim only.
- **Generation implications:**
  - Simulation aid — not production PLC generation input
- **Document sources:**
  - FPC-HighSpeedSawtoothMerge (FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx)
  - FPC High-Speed Sawtooth Merge (docs/training/FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx)

### `Merges`

- **Subsystem:** merge_legacy
- **Confidence:** MEDIUM
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/Merges.asc`
- **Purpose:** Legacy multi-induct merge table (Presence/Release/Priority/timers per induct 1..5).
- **Row semantics:** One Merge Table Name with up to five induct columns.
- **Identity fields:** `Merge Table Name`
- **Key fields:** `Merge Table Name`, `Valid`, `Number of Inducts`, `Operable Input`, `Presense_Eye1`, `Release_IO1`, `Priority1`
- **Relationship fields:**
  - `Presense_Eye1` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Release_IO1` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Presense_Eye2` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Release_IO2` → `Conveyor` (EXPLICIT_REFERENCE)
- **Active row rules:**
  - Merge Table Name present
  - Valid when used
- **Inactive row rules:**
  - Blank name
- **Optional feature rules:**
  - Inducts 2..5 optional
- **Controller scope:** May be unused when MergeBoss/SimpleMerge preferred.
- **Generation implications:**
  - Legacy; prefer MergeBoss/Inputs/Route when present
- **Document sources:**
  - FPC-Merge-Modules (FPC Documents 1/FPC-Merge-Modules.docx)

### `SimpleMerge`

- **Subsystem:** merge
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/SimpleMerge.asc`
- **Purpose:** Two-way simple merge: mainline vs lane presence/run with clear timer.
- **Row semantics:** Named simple merge with MainLineRun, LaneRun, presence eyes, Machine.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `MainLineRun`, `ClearTimer`, `MainLinePresence`, `LanePresence`, `LaneRun`, `Machine`, `NoGap`
- **Relationship fields:**
  - `MainLineRun` → `Conveyor` (EXPLICIT_REFERENCE)
  - `LaneRun` → `Conveyor` (EXPLICIT_REFERENCE)
  - `MainLinePresence` → `Conveyor` (EXPLICIT_REFERENCE)
  - `LanePresence` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Machine` → `Machine` (EXPLICIT_REFERENCE)
- **Active row rules:**
  - Name present
  - MainLineRun or LaneRun assigned
- **Inactive row rules:**
  - Blank Name
- **Optional feature rules:**
  - DontFireLaneRun / NoGap / LaneGoto optional
- **Controller scope:** Machine scopes merge.
- **Generation implications:**
  - Simple merge PLC pattern when INCLUDED
- **Document sources:**
  - FPC-Merge-Modules (FPC Documents 1/FPC-Merge-Modules.docx)
  - FPC Merge Modules (docs/training/FPC Documents 1/FPC-Merge-Modules.docx)

### `MergeBoss`

- **Subsystem:** merge
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/MergeBoss.asc`
- **Purpose:** Multi-input merge boss: owns inputs count, operable input, switch delay.
- **Row semantics:** Named boss; MergeInputs rows reference MergeBoss name.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `Process`, `Owner`, `CurrInput`, `NumInputs`, `OperableInput`, `Valid`, `SwitchDelayTimer`
- **Relationship fields:**
  - `Name` → `MergeInputs` (DOCUMENTED_RELATIONSHIP)
  - `Owner` → `Machine` (OPTIONAL_RELATIONSHIP)
- **Active row rules:**
  - Name present
  - Valid when used
- **Inactive row rules:**
  - Blank Name
- **Optional feature rules:**
  - IsSwitchDelay optional
- **Controller scope:** Controller overlay common.
- **Generation implications:**
  - Parent of MergeInputs/Route graph
- **Document sources:**
  - FPC-Merge-Modules (FPC Documents 1/FPC-Merge-Modules.docx)
  - FPC Merge Modules (docs/training/FPC Documents 1/FPC-Merge-Modules.docx)

### `MergeInputs`

- **Subsystem:** merge
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/MergeInputs.asc`
- **Purpose:** Per-input lane under a MergeBoss: presence, release I/O, timers, MergeRoute link.
- **Row semantics:** Named input with MergeBoss FK and optional MergeRoute.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `MergeBoss`, `Valid`, `Index`, `MergeRoute`, `Presense`, `ReleaseIO`, `Priority`, `FullClearTimerName`, `RunTimerName`
- **Relationship fields:**
  - `MergeBoss` → `MergeBoss` (EXPLICIT_REFERENCE)
  - `MergeRoute` → `MergeRoute` (EXPLICIT_REFERENCE)
  - `Presense` → `Conveyor` (EXPLICIT_REFERENCE)
  - `ReleaseIO` → `Conveyor` (EXPLICIT_REFERENCE)
  - `LaneReadyInput1` → `Conveyor` (OPTIONAL_RELATIONSHIP)
  - `FullClearTimerName` → `Fullline` (DERIVED_RELATIONSHIP)
- **Active row rules:**
  - Name present
  - MergeBoss linked
  - Valid when used
- **Inactive row rules:**
  - Blank Name
- **Optional feature rules:**
  - LaneReadyInput2 / PitchTimer / RouteDisable optional
- **Controller scope:** Follows MergeBoss overlay.
- **Generation implications:**
  - Lane arbitration inputs for multi-merge
- **Document sources:**
  - FPC-Merge-Modules (FPC Documents 1/FPC-Merge-Modules.docx)
  - FPC Merge Modules (docs/training/FPC Documents 1/FPC-Merge-Modules.docx)

### `MergeRoute`

- **Subsystem:** merge
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/MergeRoute.asc`
- **Purpose:** Merge route binding inputs to outputs with busy/request/priority.
- **Row semantics:** Named route linking MergeInputs and MergeOutputs signals.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `MergeInputs`, `MergeOutputs`, `RouteBusy`, `RouteRequested`, `Priority`
- **Relationship fields:**
  - `MergeInputs` → `MergeInputs` (EXPLICIT_REFERENCE)
  - `MergeOutputs` → `Conveyor` (OPTIONAL_RELATIONSHIP)
- **Active row rules:**
  - Name present
- **Inactive row rules:**
  - Blank Name
- **Optional feature rules:**
  - OutDisabled / InvertOutDisable optional
- **Controller scope:** With merge boss overlay.
- **Generation implications:**
  - Route enable graph for multi-merge
- **Document sources:**
  - FPC-Merge-Modules (FPC Documents 1/FPC-Merge-Modules.docx)
  - FPC Merge Modules (docs/training/FPC Documents 1/FPC-Merge-Modules.docx)

### `ZipperMerge`

- **Subsystem:** merge_zipper
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/ZipperMerge.asc`
- **Purpose:** Zipper merge boss: turn-based reservation, merge motor, speed, induct.
- **Row semantics:** Named zipper merge with MergeMtr, MergeInduct, MergeRunIO, ControlMachine.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `MergeType`, `MergeInduct`, `MergeMtr`, `MergeRunIO`, `ControlMachine`, `MergeSpdFtPerMin`, `MergeTicksPerInch`, `GapType`
- **Relationship fields:**
  - `MergeMtr` → `Conveyor` (EXPLICIT_REFERENCE)
  - `MergeInduct` → `Conveyor` (EXPLICIT_REFERENCE)
  - `MergeRunIO` → `Conveyor` (EXPLICIT_REFERENCE)
  - `ControlMachine` → `Machine` (EXPLICIT_REFERENCE)
  - `Name` → `ZipperLane` (DOCUMENTED_RELATIONSHIP)
- **Active row rules:**
  - Name present
- **Inactive row rules:**
  - Blank Name
- **Optional feature rules:**
  - CreateResrvFlag / MergeJamUpdate optional
- **Controller scope:** ControlMachine scoped.
- **Generation implications:**
  - Distinct from sawtooth; only generate when Zipper* rows active
- **Document sources:**
  - FPC-Merge-Modules (FPC Documents 1/FPC-Merge-Modules.docx)
  - FPC Merge Modules (docs/training/FPC Documents 1/FPC-Merge-Modules.docx)

### `ZipperLane`

- **Subsystem:** merge_zipper
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/ZipperLane.asc`
- **Purpose:** Zipper lane under ZipperMerge: turns, reservation lengths, meter/pre speeds, accum I/O.
- **Row semantics:** Named lane with ZipperMerge FK and extensive meter/merge parameters.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `Enabled`, `ZipperMerge`, `Turns`, `ResrvLenInches`, `MeterSpdFtPerMin`, `AccumIO`, `FullClearTimer`, `PreMergeInduct`
- **Relationship fields:**
  - `ZipperMerge` → `ZipperMerge` (EXPLICIT_REFERENCE)
  - `AccumIO` → `Conveyor` (EXPLICIT_REFERENCE)
  - `EnableIO` → `Conveyor` (OPTIONAL_RELATIONSHIP)
  - `PreMergeInduct` → `Conveyor` (OPTIONAL_RELATIONSHIP)
  - `FullClearTimer` → `Fullline` (DERIVED_RELATIONSHIP)
- **Active row rules:**
  - Name present
  - Enabled when used
  - ZipperMerge linked
- **Inactive row rules:**
  - Blank Name
- **Optional feature rules:**
  - UseSpdFeedBack / AdjustForDrift optional
- **Controller scope:** Follows ZipperMerge ControlMachine.
- **Generation implications:**
  - Lane parameters for zipper merge generation
- **Document sources:**
  - FPC-Merge-Modules (FPC Documents 1/FPC-Merge-Modules.docx)
  - FPC Merge Modules (docs/training/FPC Documents 1/FPC-Merge-Modules.docx)
  - FPC Gapping Modules (docs/training/FPC Documents 1/FPC-Gapping-Modules.docx)
  - FPC Motor Speed Control (docs/training/FPC Documents 1/FPC-Motor-Speed-Control.docx)

### `Sorters`

- **Subsystem:** sorter
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/Sorters.asc`
- **Purpose:** Sorter entity definition: encoder binding, shift buffers, divert enable, machine.
- **Row semantics:** One Sorter Name with Encoder ioName/tmName and record-range cursors into track tables.
- **Identity fields:** `Sorter Name`
- **Key fields:** `Sorter Name`, `Encoder ioName`, `Encoder tmName`, `Encoder Type`, `Machine`, `Max Cartons`, `DivertEnableIO`, `Dump NDX`, `ShiftOnOff`
- **Relationship fields:**
  - `Encoder ioName` → `Encoders` (EXPLICIT_REFERENCE)
  - `Machine` → `Machine` (EXPLICIT_REFERENCE)
  - `DivertEnableIO` → `Conveyor` (OPTIONAL_RELATIONSHIP)
  - `Sorter Name` → `SrtAppControl` (DOCUMENTED_RELATIONSHIP)
  - `Sorter Name` → `SrtZoneLane` (DOCUMENTED_RELATIONSHIP)
- **Active row rules:**
  - Sorter Name present and not placeholder
- **Inactive row rules:**
  - Blank Sorter Name
- **Optional feature rules:**
  - RecircRate* optional recirculation management
  - Trig* window/trigger options
- **Controller scope:** Sorters.asc.<CONTROLLER> overlay preferred.
- **Generation implications:**
  - Discovery-only until complete generic sorter library path exists
  - Tracking/WCS generation NOT_SUPPORTED by policy
- **Document sources:**
  - FPC-Shifter-And-Sorter-Configuration (FPC Docs 3/FPC-Shifter-And-Sorter-Configuration.docx)
  - FPC-Sorter-Control-Module (FPC Docs 3/FPC-Sorter-Control-Module.docx)
  - FPC-SorterConfigurationChecklist (FPC Docs 3/FPC-SorterConfigurationChecklist.docx)
  - FPC Sorter Control Module (docs/training/FPC Docs 3/FPC-Sorter-Control-Module.docx)
  - FPC Shifter And Sorter Configuration (docs/training/FPC Docs 3/FPC-Shifter-And-Sorter-Configuration.docx)
  - Unit Sorter Control Software V1 rev25 DDD (docs/training/FPC Docs 3/Unit Sorter Control Software V1 rev25 DDD.doc)
  - FPC New Transfers (docs/training/FPC Documents 1/FPC-New-Transfers.docx)

### `SrtAppControl`

- **Subsystem:** sorter
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/SrtAppControl.asc`
- **Purpose:** Application sorter control: motor status, host msg tables, scan/data error signaling.
- **Row semantics:** Named app sorter control with ControlMachine and message table bindings.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `AvailAppSorter`, `ControlMachine`, `SorterCnvMtr`, `CrrMsgTable`, `DcmMsgTable`, `ErrConfig`, `LogLevel`
- **Relationship fields:**
  - `ControlMachine` → `Machine` (EXPLICIT_REFERENCE)
  - `SorterCnvMtr` → `Conveyor` (EXPLICIT_REFERENCE)
  - `AvailAppSorter` → `Sorters` (DOCUMENTED_RELATIONSHIP)
  - `CrrMsgTable` → `MsgMap` (OPTIONAL_RELATIONSHIP)
  - `Name` → `SrtScanBoss` (DOCUMENTED_RELATIONSHIP)
- **Active row rules:**
  - Name present
- **Inactive row rules:**
  - Blank Name
- **Optional feature rules:**
  - Second* msg tables optional tandem scanners
- **Controller scope:** ControlMachine scoped.
- **Generation implications:**
  - App control skeleton for sorter discovery
- **Document sources:**
  - FPC-Sorter-Control-Module (FPC Docs 3/FPC-Sorter-Control-Module.docx)
  - FPC Sorter Control Module (docs/training/FPC Docs 3/FPC-Sorter-Control-Module.docx)
  - FPC Sorter Configuration Checklist (docs/training/FPC Docs 3/FPC-SorterConfigurationChecklist.docx)

### `SrtScanBoss`

- **Subsystem:** sorter
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/SrtScanBoss.asc`
- **Purpose:** Scan zone boss: links AppSorter, ScanZone, update points, lane assignment hooks.
- **Row semantics:** Named scan boss under an AppSorter with scan error/conflict handling.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `AppSorter`, `ScanZone`, `AssignUpdatePt`, `Lane`, `SpcLane`, `TooLateUpdatePt`, `SendCRRUpdatePt`
- **Relationship fields:**
  - `AppSorter` → `SrtAppControl` (EXPLICIT_REFERENCE)
  - `ScanZone` → `ScnScanZone` (OPTIONAL_RELATIONSHIP)
  - `Lane` → `SrtZoneLane` (OPTIONAL_RELATIONSHIP)
- **Active row rules:**
  - Name present
  - AppSorter linked
- **Inactive row rules:**
  - Blank Name
- **Optional feature rules:**
  - Tote* / SecondScanZone optional
- **Controller scope:** Follows app sorter machine.
- **Generation implications:**
  - Scan assignment points — not divert IO map
- **Document sources:**
  - FPC-Sorter-Control-Module (FPC Docs 3/FPC-Sorter-Control-Module.docx)
  - FPC-Scanner-Control-Configuration (FPC Docs 3/FPC-Scanner-Control-Configuration.docx)
  - FPC Sorter Control Module (docs/training/FPC Docs 3/FPC-Sorter-Control-Module.docx)
  - FPC Scanner Control Configuration (docs/training/FPC Docs 3/FPC-Scanner-Control-Configuration.docx)
  - FPC Sorter Configuration Checklist (docs/training/FPC Docs 3/FPC-SorterConfigurationChecklist.docx)

### `SrtZoneLane`

- **Subsystem:** sorter
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/SrtZoneLane.asc`
- **Purpose:** Host zone → sorter lane assignment with full-clear timer and enable signals.
- **Row semantics:** Named zone-lane row under AppSorter with HostZone and Lane.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `Enabled`, `AppSorter`, `Lane`, `HostZone`, `FullClearTimer`, `LaneEnableSignal`, `RndRobinEnabled`
- **Relationship fields:**
  - `AppSorter` → `SrtAppControl` (EXPLICIT_REFERENCE)
  - `FullClearTimer` → `Fullline` (DERIVED_RELATIONSHIP)
  - `LaneEnableSignal` → `Conveyor` (OPTIONAL_RELATIONSHIP)
  - `Name` → `SrtTrack1` (RUNTIME_DATA) — SrtTrack*.SrtZoneLaneRec runtime link
- **Active row rules:**
  - Name present
  - Enabled when assigned
- **Inactive row rules:**
  - Blank Name
- **Optional feature rules:**
  - AssignIfFull / AssignLaneZero / TwoSidedShoe optional policies
- **Controller scope:** App sorter machine scope.
- **Generation implications:**
  - Static lane assignment; divert IO still engineer-required
- **Document sources:**
  - FPC-Sorter-Control-Module (FPC Docs 3/FPC-Sorter-Control-Module.docx)
  - FPC Sorter Control Module (docs/training/FPC Docs 3/FPC-Sorter-Control-Module.docx)
  - FPC Shifter And Sorter Configuration (docs/training/FPC Docs 3/FPC-Shifter-And-Sorter-Configuration.docx)
  - FPC Sorter Configuration Checklist (docs/training/FPC Docs 3/FPC-SorterConfigurationChecklist.docx)

### `SrtTrack`

- **Subsystem:** sorter_runtime
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/SrtTrack1.asc`
- **Purpose:** Runtime carton tracking slot tables SrtTrack1..5 — confirm scan, host zone, sorter lane, dimensions. Not static topology.
- **Row semantics:** Named-slot or indexed carton records with ConfirmScan, ScanZoneID, SorterLane, SrtAppRec. Numeric empty slots are inactive.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `ConfirmScan`, `HostZone`, `ScanZoneID`, `SorterLane`, `SrtAppRec`, `SrtZoneLaneRec`, `Status`, `Length`, `Width`, `Height`
- **Relationship fields:**
  - `SrtAppRec` → `SrtAppControl` (RUNTIME_DATA)
  - `SrtZoneLaneRec` → `SrtZoneLane` (RUNTIME_DATA)
  - `SorterLane` → `SrtZoneLane` (RUNTIME_DATA)
  - `ScanZoneID` → `SrtScanBoss` (RUNTIME_DATA)
- **Active row rules:**
  - Name present and not placeholder
  - ConfirmScan / HostZone / ScanZoneID evidence of live track slot
- **Inactive row rules:**
  - Blank/numeric-only empty slots
- **Optional feature rules:**
  - P&A verify fields (VerRF/VerSKU) optional
- **Controller scope:** Shared runtime menus; sized per sorter docs.
- **Generation implications:**
  - Proves tracking activity; does NOT define divert output maps
  - classification=RUNTIME_DATA
- **Document sources:**
  - FPC-Sorter-Control-Module (FPC Docs 3/FPC-Sorter-Control-Module.docx)
  - FPC-Scanner-Control-Configuration (FPC Docs 3/FPC-Scanner-Control-Configuration.docx)
  - FPC Sorter Control Module (docs/training/FPC Docs 3/FPC-Sorter-Control-Module.docx)
  - FPC Scanner Control Configuration (docs/training/FPC Docs 3/FPC-Scanner-Control-Configuration.docx)

### `XfrTrack`

- **Subsystem:** transfer_runtime
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/XfrTrack.asc`
- **Purpose:** Transfer tracking runtime slots (scan confirm, route boss/table rec, XfrZoneID).
- **Row semantics:** Parallel to SrtTrack for transfer path; RouteBossRec / RouteTableRec runtime links.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `ConfirmScan`, `HostZone`, `RouteBossRec`, `RouteTableRec`, `XfrZoneID`, `SorterLane`, `Status`
- **Relationship fields:**
  - `RouteBossRec` → `XfRouteBoss` (RUNTIME_DATA)
  - `RouteTableRec` → `XfRouteTable` (RUNTIME_DATA)
  - `SrtAppRec` → `SrtAppControl` (RUNTIME_DATA)
- **Active row rules:**
  - Name present with ConfirmScan/HostZone/route evidence
- **Inactive row rules:**
  - Empty slots
- **Optional feature rules:**
  - P&A verify flags optional
- **Controller scope:** Runtime shared.
- **Generation implications:**
  - RUNTIME_DATA — transfer divert maps still engineer/config
- **Document sources:**
  - FPC-New-Transfers (FPC Documents 1/FPC-New-Transfers.docx)
  - FPC-Transfer-Configuration-Example (FPC Docs 3/FPC-Transfer-Configuration-Example.docx)
  - FPC Scanner Control Configuration (docs/training/FPC Docs 3/FPC-Scanner-Control-Configuration.docx)
  - FPC New Transfers (docs/training/FPC Documents 1/FPC-New-Transfers.docx)

### `XfRouteTable`

- **Subsystem:** transfer
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/XfRouteTable.asc`
- **Purpose:** Transfer route table: host route string → Route under a BossRecord.
- **Row semantics:** Named route row with Enabled, BossRecord, HostRouteStr, error I/O.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `Enabled`, `BossRecord`, `HostRouteStr`, `Route`, `ErrorIO`, `MaximumErrors`
- **Relationship fields:**
  - `BossRecord` → `XfRouteBoss` (EXPLICIT_REFERENCE)
  - `ErrorIO` → `Conveyor` (OPTIONAL_RELATIONSHIP)
- **Active row rules:**
  - Name present
  - Enabled when used
- **Inactive row rules:**
  - Blank Name
- **Optional feature rules:**
  - DSRRequest / AutoResetCons optional
- **Controller scope:** Boss/machine scoped.
- **Generation implications:**
  - Static transfer routes — still not full divert PLC map
- **Document sources:**
  - FPC-New-Transfers (FPC Documents 1/FPC-New-Transfers.docx)
  - FPC New Transfers (docs/training/FPC Documents 1/FPC-New-Transfers.docx)

### `XfRouteBoss`

- **Subsystem:** transfer
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/XfRouteBoss.asc`
- **Purpose:** Transfer route boss: scan zone, msg tables, conveyor motor, error signaling.
- **Row semantics:** Named boss controlling transfer scan/route decisioning.
- **Identity fields:** `Name`
- **Key fields:** `Name`, `ScanZone`, `XferCnvMtr`, `CrrMsgTable`, `AvailTransfer`, `SystemRun`, `LogLevel`
- **Relationship fields:**
  - `XferCnvMtr` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Name` → `XfRouteTable` (DOCUMENTED_RELATIONSHIP)
  - `ScanZone` → `ScnScanZone` (OPTIONAL_RELATIONSHIP)
  - `CrrMsgTable` → `MsgMap` (OPTIONAL_RELATIONSHIP)
- **Active row rules:**
  - Name present
- **Inactive row rules:**
  - Blank Name
- **Optional feature rules:**
  - ToteSensor / RunNewXfr optional
- **Controller scope:** Process/machine via msg tables.
- **Generation implications:**
  - Transfer discovery skeleton
- **Document sources:**
  - FPC-New-Transfers (FPC Documents 1/FPC-New-Transfers.docx)
  - FPC Scanner Control Configuration (docs/training/FPC Docs 3/FPC-Scanner-Control-Configuration.docx)
  - FPC New Transfers (docs/training/FPC Documents 1/FPC-New-Transfers.docx)

### `Machine`

- **Subsystem:** communications
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/Machine.asc`
- **Purpose:** Communications endpoint inventory: controllers, hosts, scanners, protocols, ports.
- **Row semantics:** One Machine_Name with Connection_Type, Communication_Protocol, Machine_Port, Offline.
- **Identity fields:** `Machine_Name`
- **Key fields:** `Machine_Name`, `Status`, `Connection_Type`, `Communication_Protocol`, `Machine_Port`, `Offline`, `Process`, `FortnaMachine`, `LogLevel`
- **Relationship fields:**
  - `Machine_Name` → `MsgMap` (DOCUMENTED_RELATIONSHIP) — MsgMap.Machine_Name → this
  - `Machine_Name` → `Conveyor` (DOCUMENTED_RELATIONSHIP)
  - `Machine_Name` → `IOCard` (DOCUMENTED_RELATIONSHIP)
- **Active row rules:**
  - Machine_Name present
  - Offline not asserted for live endpoints
- **Inactive row rules:**
  - Blank Machine_Name
  - Offline=Y when confirmed down
- **Optional feature rules:**
  - Username/Password for TCP auth optional
- **Controller scope:** Machine table lists all peers; controller overlays on other tables filter by Machine_Name.
- **Generation implications:**
  - Defines peer inventory; TCP endpoints for WCS still may be engineer-required
- **Document sources:**
  - FPC-Machine-MsgMap-Configuraton (FPC Documents 1/FPC-Machine-MsgMap-Configuraton.docx)
  - FPC Sorter Control Module (docs/training/FPC Docs 3/FPC-Sorter-Control-Module.docx)
  - FPC Shifter And Sorter Configuration (docs/training/FPC Docs 3/FPC-Shifter-And-Sorter-Configuration.docx)
  - FPC Start/Stop Zones (docs/training/FPC Docs 3/FPC-StartStopZones.docx)
  - FPC FastIO Configuration (docs/training/FPC Documents 1/FPC-FastIO-Configuration.docx)
  - FPC IOCard Interfaces (docs/training/FPC Documents 1/FPC-IOCard-Interfaces.docx)
  - FPC Machine MsgMap Configuration (Configuraton spelling) (docs/training/FPC Documents 1/FPC-Machine-MsgMap-Configuraton.docx)
  - FPC Scanner Control Configuration (docs/training/FPC Docs 3/FPC-Scanner-Control-Configuration.docx)
  - FPC Sorter Configuration Checklist (docs/training/FPC Docs 3/FPC-SorterConfigurationChecklist.docx)
  - Unit Sorter Control Software V1 rev25 DDD (docs/training/FPC Docs 3/Unit Sorter Control Software V1 rev25 DDD.doc)
  - FPC Ctrl-F4 Table Distribution (docs/training/FPC Documents 1/FPC-Ctrl-F4-Table-Distribution.docx)
  - FPC New Transfers (docs/training/FPC Documents 1/FPC-New-Transfers.docx)

### `MsgMap`

- **Subsystem:** communications
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/MsgMap.asc`
- **Purpose:** Message map: binds Message_Name to Machine_Name, msg types, and Menu_Name queues.
- **Row semantics:** One Message_Name routing recv/send/ack types to a menu (e.g. MsgWCS).
- **Identity fields:** `Message_Name`
- **Key fields:** `Message_Name`, `Machine_Name`, `Recv_Msg_Type`, `Send_Msg_Type`, `Ack_Msg_Type`, `Menu_Name`, `Delimiter`
- **Relationship fields:**
  - `Machine_Name` → `Machine` (EXPLICIT_REFERENCE)
  - `Menu_Name` → `MsgWCS` (DOCUMENTED_RELATIONSHIP) — WCS_EVENT often maps Menu_Name=MsgWCS
  - `Menu_Name` → `MsgTrack` (OPTIONAL_RELATIONSHIP)
- **Active row rules:**
  - Message_Name present and not placeholder
- **Inactive row rules:**
  - Blank Message_Name
- **Optional feature rules:**
  - CheckFile / FieldLength optional framing
- **Controller scope:** MsgMap.asc.<CONTROLLER> overlay common.
- **Generation implications:**
  - Comm routing skeleton; not full WCS PLC
- **Document sources:**
  - FPC-Machine-MsgMap-Configuraton (FPC Documents 1/FPC-Machine-MsgMap-Configuraton.docx)
  - FPC Sorter Control Module (docs/training/FPC Docs 3/FPC-Sorter-Control-Module.docx)
  - FPC Machine MsgMap Configuration (Configuraton spelling) (docs/training/FPC Documents 1/FPC-Machine-MsgMap-Configuraton.docx)
  - FPC Scanner Control Configuration (docs/training/FPC Docs 3/FPC-Scanner-Control-Configuration.docx)
  - FPC Sorter Configuration Checklist (docs/training/FPC Docs 3/FPC-SorterConfigurationChecklist.docx)

### `MsgTrack`

- **Subsystem:** communications_runtime
- **Confidence:** LOW
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/MsgTrack.asc`
- **Purpose:** Tracking message outbound/inbound queue (runtime). Often empty on RUNs.
- **Row semantics:** Queue rows for tracking messages when the file is populated.
- **Schema note:** Header unavailable (empty or missing ASC). Semantics from docs/catalog only; no invented fields claimed as RUN-present.
- **Identity fields:** _none_
- **Key fields:** _none in RUN headers_
- **Relationship fields:**
  - `Menu_Name` → `MsgMap` (DOCUMENTED_RELATIONSHIP) — Referenced from MsgMap when used
- **Active row rules:**
  - Non-empty message payload / destination when file has schema
- **Inactive row rules:**
  - Empty file or all-blank rows
- **Controller scope:** Runtime queue; may be zero-byte on archive.
- **Generation implications:**
  - RUNTIME_DATA; absence is normal
- **Document sources:**
  - FPC-Sorter-Control-Module (FPC Docs 3/FPC-Sorter-Control-Module.docx)

### `MsgWCS`

- **Subsystem:** communications_runtime
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/MsgWCS.asc`
- **Purpose:** WCS outbound message queue: MsgText + Destination topic + tx status.
- **Row semantics:** Queue slots; Destination topic (/topic/…) counts as active even when MsgText blank.
- **Identity fields:** `Destination`
- **Key fields:** `MsgText`, `Destination`, `TxStat`, `DbKey`, `DbTime`
- **Relationship fields:**
  - `Destination` → `WCSEvents` (DERIVED_RELATIONSHIP) — Topics align with WCSDestination
  - `Menu_Name` → `MsgMap` (DOCUMENTED_RELATIONSHIP)
- **Active row rules:**
  - Destination present (topic path) OR MsgText present
- **Inactive row rules:**
  - Blank Destination and MsgText
- **Controller scope:** Shared queue; MsgMap selects owning machine.
- **Generation implications:**
  - Proves WCS messaging activity; TCP peer still configuration
  - RUNTIME_DATA classification
- **Document sources:**
  - FPC-Machine-MsgMap-Configuraton (FPC Documents 1/FPC-Machine-MsgMap-Configuraton.docx)

### `WCSEvents`

- **Subsystem:** communications
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/WCSEvents.asc`
- **Purpose:** Static WCS/NMS event → destination/category/service enable map.
- **Row semantics:** One EventName with WCSEnable/WCSDestination and optional NMS fields.
- **Identity fields:** `EventName`
- **Key fields:** `EventName`, `WCSEnable`, `WCSDestination`, `WCSCategory`, `WCSService`, `WCSMachProc`, `NMSEnable`
- **Relationship fields:**
  - `WCSDestination` → `MsgWCS` (DOCUMENTED_RELATIONSHIP)
  - `WCSMachProc` → `Machine` (OPTIONAL_RELATIONSHIP)
  - `EventName` → `MsgMap` (OPTIONAL_RELATIONSHIP)
- **Active row rules:**
  - EventName present
  - WCSEnable when event armed
- **Inactive row rules:**
  - Blank EventName
- **Optional feature rules:**
  - NMS* optional OpenNMS path
- **Controller scope:** Usually base shared; enable flags select live events.
- **Generation implications:**
  - Static event catalog for WCS interface discovery
- **Document sources:**
  - FPC-Machine-MsgMap-Configuraton (FPC Documents 1/FPC-Machine-MsgMap-Configuraton.docx)
  - FPC-OpenNMS-Configuration (FPC-Docs 2/FPC-OpenNMS-Configuration.docx)

### `Encoders`

- **Subsystem:** sorter
- **Confidence:** HIGH
- **Schema source:** `workspace/cp4-run/RUN/FORTNA/Encoders.asc`
- **Purpose:** Sorter/merge encoder devices: ticks/ft, target FPM, enable bit, jamzone.
- **Row semantics:** One Encoder Name with Encoder I/O, timing, speed limits, EnableBit, Jamzone.
- **Identity fields:** `Encoder Name`
- **Key fields:** `Encoder Name`, `Encoder I/O`, `Encoder Timer`, `Ticks Per Foot`, `Target FPM`, `EnableBit`, `Jamzone`, `Tolerance_FPM`, `StoponError`
- **Relationship fields:**
  - `Encoder I/O` → `Conveyor` (EXPLICIT_REFERENCE)
  - `EnableBit` → `Conveyor` (EXPLICIT_REFERENCE)
  - `Jamzone` → `Jamzones` (OPTIONAL_RELATIONSHIP)
  - `Encoder Name` → `Sorters` (DOCUMENTED_RELATIONSHIP) — Sorters.Encoder ioName
- **Active row rules:**
  - Encoder Name present and not placeholder
- **Inactive row rules:**
  - Blank Encoder Name
- **Optional feature rules:**
  - NoSortonError / NoSortOnSpeed optional sort inhibit
  - DupToMemBit optional
- **Controller scope:** Encoders.asc.<CONTROLLER> overlay preferred.
- **Generation implications:**
  - Encoder scale/speed seeds for sorter/sawtooth when generation supported
- **Document sources:**
  - FPC-Shifter-And-Sorter-Configuration (FPC Docs 3/FPC-Shifter-And-Sorter-Configuration.docx)
  - FPC-HighSpeedSawtoothMerge (FPC Documents 1/FPC-HighSpeedSawtoothMerge.docx)
  - FPC Shifter And Sorter Configuration (docs/training/FPC Docs 3/FPC-Shifter-And-Sorter-Configuration.docx)

