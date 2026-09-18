# StartStop / Jamzones → PLC Mapping (Gate L)

**Branch:** `feature/plc2-transport-fidelity`  
**Status:** Validation-oracle mapping only — **not** a compiler.  
**Oracles (Folder to GPT):**

| Controller | File (Curtis machine) | Class |
|------------|-----------------------|-------|
| PLC2 | `C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT\ORLY_GreensboroPLC2_NC_Finished.L5X` | VALIDATION ORACLE |
| PLC4 | `...\ORLY_Greensboro_NC_PLC4 finished.L5X` | VALIDATION ORACLE |
| PLC5 | `...\ORLY_Greensboro_NC_PLC5_RTfinished.L5X` | VALIDATION ORACLE |

Also mirrored when present: `workspace/validation/ORLY_GreensboroPLC2_NC_Finished.L5X`.

**Never** use these L5X files as discovery or generation inputs.

Site identities below (`ModuleB_Area`, `Sawtooth_Area`, `ENABLE_SAWTOOTH`, …) are **labeled validation-oracle examples**.

---

## Classification vocabulary

| Class | Meaning |
|-------|---------|
| **STANDARD_ARCHITECTURE** | Recurring Fortna library / Autogen shape across finished PLCs (UDT/AOI/program pattern) |
| **SITE_INSTANCE** | Concrete names, counts, wiring unique to a site/controller |
| **COMMISSIONING** | Presets, timers, anti-tie-down times, silences — tuned at site |
| **CUSTOM** | One-off logic not explained by standard packs |
| **UNKNOWN** | No safe mapping from FortnaPlus field → PLC member yet |

---

## FortnaPlus control objects → PLC structures

### StartStopZones

| FortnaPlus | PLC oracle structure | Class | Notes |
|------------|----------------------|-------|-------|
| `StartStopZones.Zone Name` | Engineering **Area_*** program family islands (`Area_*_Fast/_Slow/_L1/_L2`) loosely group equipment; **not 1:1 rename** | SITE_INSTANCE names; STANDARD_ARCHITECTURE program family | Docs already: StartStop ≠ Engineering Area; many-to-many possible |
| `StartReqFlag` / `StopReqFlag` | Area start/stop request path (`Area_UDT.Start` / `.Stop` / `.Run`; HMI Start/Stop) | STANDARD_ARCHITECTURE members; SITE_INSTANCE which zones map where | Flags are Fortna runtime; PLC exposes Area/CS bits |
| `State` / `WasState` | Area_PI `Run` / `Stop` / `Start` status bits | STANDARD_ARCHITECTURE | ZoneStates vocabulary stays in RUN |
| `StartOwnerCtl` / `StopOwnerCtl` | Cross-AC ownership / message propagation | UNKNOWN → often CUSTOM/COMMISSIONING | FPC: do not blindly distribute unique start/stop to all nodes |

**PLC2 oracle Area_UDT tags (examples):** `ModuleB_Area`, `ModuleC_Area`, `Trash_Area`.  
**PLC4 examples:** `Sawtooth_Area_*`, `CityCounter_Area_*`, `ModuleA_Area_*`.  
**PLC5 examples:** `ShippingSorter_Area_*`, `Redroom_Area_*`.

### Jamzones

| FortnaPlus field | PLC oracle structure | Class | Notes |
|------------------|----------------------|-------|-------|
| `Zone Name` | Conceptual jam/start-stop control zone; may align with Area Slow jam aggregation | SITE_INSTANCE | Not a Studio program name by itself |
| `Latch Bit` → Conveyor logical (often Type=INVALID) | Zone **running latch** ↔ `Area_UDT.Run` / motor-aux / chain latch path | STANDARD_ARCHITECTURE *role*; UNKNOWN exact BOOL emit | Fortna name e.g. `LATCH_SAWTOOTH` does **not** appear as same-named controller tag in PLC2/4/5 oracles scanned |
| `Jammed Bit` → Conveyor logical | `Area_PI.Jam` / per-conveyor `Conv_*.Jam` via **Slow_Jam** AOI | STANDARD_ARCHITECTURE | Encoded AOI `Slow_Jam` present in finished PLC2 |
| `Enable Bit` → Conveyor logical | `Area_HMI.Enable` + Combined enable (E-Stop/MCR/interlock AND) | STANDARD_ARCHITECTURE role; SITE_INSTANCE combine list | Training: CombinedJamZones / CombinedEnableBits |
| `Start Button` / `Stop Button` | `CS_UDT.Start_PB` / `Stop_PB` **or** memory Conveyor parts | STANDARD_ARCHITECTURE CS_UDT; SITE_INSTANCE which PB/MEM | Physical PB Type=PROXPART; MEM_* Type=INVALID logical |
| `Reset Button` | `Area_HMI.Jam_Reset` / `JamRestart_PB` / per-device reset | STANDARD_ARCHITECTURE | Field INVALID ⇒ no dedicated reset |
| `Start Stop Timer` → timemenu | Area timing members (`StartTime`, `JamRstTime`, …) + Slow path timers | COMMISSIONING presets; STANDARD_ARCHITECTURE timer slots | Fortna `tmStartStop_*` identities ≠ automatic Studio tag names |
| `Zone Owner ` → Machine | Which AC hosts the zone / owns IO | SITE_INSTANCE | Strong ownership signal with Configio/Machine_Name |
| `StartStopZone` → StartStopZones | Groups Jamzones under a start/stop island | PROVEN Fortna; PLC mapping via Area membership ENGINEER/REVIEW | |

### Jamcheck / Slow jam path

| FortnaPlus | PLC | Class |
|------------|-----|-------|
| Jamcheck sensor PE + timer + Zone | Per-conveyor **Slow_Jam** AOI instance; `Jam_Tmr` on jam UDTs | STANDARD_ARCHITECTURE |
| `ClearJamSignal` / L2 clear | Jam reset / clear paths on Conv / Area | SITE_INSTANCE / COMMISSIONING |
| Error_Name | Errors / fault annunciation | STANDARD_ARCHITECTURE when INITERRORS path used |

### Motor chain linkage (control, not geometry)

| FortnaPlus | PLC | Class |
|------------|-----|-------|
| Mtrchain latch/aux ↔ Jamzones Latch Bit | Motor starter aux / area run permissive | STANDARD_ARCHITECTURE *pattern* (training); SITE_INSTANCE wiring |
| Mtrchain `Stop Zone` → Jamzones | Chain stops with jam zone | PROVEN Fortna DLIST; PLC emit UNKNOWN until LogicalSignalModel wired |
| Frozen Transportation Mtrchain behavior | Do **not** rewrite this checkpoint | — |

---

## Standard PLC type members (oracle-proven shapes)

### `Area_HMI` (STANDARD_ARCHITECTURE)

`Enable`, `Reset`, `Silence`, `Start`, `Stop`, `Jam_Reset`, `Motor_Fault_Reset`

### `Area_PI` (STANDARD_ARCHITECTURE)

Includes `Jam`, `JamRst`, `Run`, `Start`, `Stop`, fault/silence/anti-tie-down bits

### `Area_UDT` (STANDARD_ARCHITECTURE)

`HMI`, `PI`, timing INTs (`StartTime`, `JamRstTime`, …), `Run`, `Start`, `Jam_Reset`, …

### `CS_UDT` / Control Station (STANDARD_ARCHITECTURE)

`Start_PB`, `Stop_PB`, `Rst_PB`, one-shots / anti-tie-down

### AOIs (STANDARD_ARCHITECTURE library)

| AOI | Role |
|-----|------|
| `Slow_Jam` | Per-equipment jam detect / latch path on Slow programs |
| `Fast_Conv` | Fast conveyor motion |
| `Slow_Flt` | Fault path (includes Jam_Reset members in library UDTs) |

### Programs (STANDARD_ARCHITECTURE family; SITE_INSTANCE names)

`Area_*_Fast`, `Area_*_Slow`, `Area_*_L1`, `Area_*_L2` (+ optional L3), `ES`, `IO_MAP`, `Sys`/`System`

---

## Critical non-mapping (avoid false fidelity)

1. **FortnaPlus logical Conveyor identities are not Studio tag names.**  
   Scanning PLC2/4/5 oracles for `Tag Name="ENABLE_*"` / `LATCH_*` / `JAM_*` / `tmStartStop_*` matching Jamzones selections returns **no** Fortna catalog twins — only unrelated `Enable_*` feature flags.  
   → Emission of LogicalSignalModel is **UNKNOWN / NOT_STARTED**, not “copy ENABLE_SAWTOOTH as a controller tag.”

2. **StartStopZones.Zone Name ≠ Area program name.**  
   Example: Fortna `SAWTOOTH, CITY, DANCE` vs PLC4 programs `Sawtooth_Area_*` + `CityCounter_Area_*` — related by engineering intent, not string equality.

3. **INVALID field value ≠ missing Area.** It means that **selection** is absent.

4. **Type=INVALID Conveyor row ≠ omit from mapping tables.** It may still be the Fortna selection target that the future compiler must retain as a named logical signal.

---

## Mapping summary matrix

| Concern | FortnaPlus authority | PLC oracle role | Pack consumer |
|---------|----------------------|-----------------|---------------|
| Start/stop island | StartStopZones + Jamzones.StartStopZone | Area_* family + Area_UDT | StartStopModel → Transport/Safety packs |
| Jam zone enable/latch/jam/buttons/timer/owner | Jamzones + Conveyor/timemenu/Machine | Area_HMI/PI, CS_UDT, Slow_Jam | JamZoneModel + LogicalSignalModel |
| Jam PE checks | Jamcheck | Slow_Jam / Conv jam | Transport Slow pack |
| Motor chain logical refs | Mtrchain (frozen behavior) | Motor starter / aux | Transport pack (existing) |
| Sorter/WCS | separate packs | Sorter_Track / WCS programs | MORE_EVIDENCE_REQUIRED / NOT_STARTED |

---

## Readiness

| Item | Verdict |
|------|---------|
| Architecture mapping doc | **DONE** (this file) |
| Exact BOOL/tag emit from Jamzones selections | **UNKNOWN / NOT_STARTED** |
| Sorter_Track / WCS compilers | **NOT_STARTED** / **MORE_EVIDENCE_REQUIRED** |
| Rewrite Mtrchain transport behavior | **FORBIDDEN** this checkpoint |

---

## Related

- [`LOGICAL_SIGNAL_MODEL.md`](LOGICAL_SIGNAL_MODEL.md)
- [`FORTNAPLUS_CONTROL_GRAPH.md`](FORTNAPLUS_CONTROL_GRAPH.md)
- [`../PLC_PROGRAM_PACK_ARCHITECTURE.md`](../PLC_PROGRAM_PACK_ARCHITECTURE.md)
- [`../PLC2_FORTNAPLUS_IO_SEMANTICS.md`](../PLC2_FORTNAPLUS_IO_SEMANTICS.md) § FPC-StartStopZones
- [`EXTERNAL_REFERENCE_MATERIALS.md`](EXTERNAL_REFERENCE_MATERIALS.md) — Folder to GPT paths
