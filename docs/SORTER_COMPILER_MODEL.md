# Sorter Compiler Model — discovery foundation

**Branch:** `feature/run-driven-workspace`  
**Status:** Research / discovery only — **no sorter or WCS L5X generation in this pass**  
**Firewall:** Finished PLC4 / PLC5 L5X were **not** used as generation input  
**Primary RUN:** `workspace/cp4-run/RUN` (ORNCCP4)  
**Artifacts:** `exports/sorter-research/`

---

## 1. Purpose

Define a **generic `SorterModel`** and the discovery approach that feeds it, so a future sorter compiler can consume RUN-derived facts without inventing divert IO or Tracking/WCS wiring.

This document is the contract boundary between:

| Layer | Responsibility |
|-------|----------------|
| **Discovery** | Read RUN tables → inventory + subsystem skeleton |
| **Model** | Normalize RUN facts into `SorterModel` fields (provenance on every field) |
| **Generation** | Emit PLC only when a **complete generic library path** exists |

**Policy:** Tracking / WCS / Sorter_Track PLC generation is **`NOT_SUPPORTED`** until a complete generic library path exists. Greensboro gold packs (`Sorter_Track_Program.L5X`, `WCS_Interface_TCP_IP_Program.L5X`, `ShippingSorter_Area_L3_Program.L5X`) do **not** qualify — they are site-fixed patterns with optional token-rename / divert-limit configuration only.

---

## 2. Generic `SorterModel` fields

Every field carries `{ value, source, provenance }` where provenance is one of:

`RUN_EXPLICIT` | `RUN_DERIVED` | `ENGINEER_REQUIRED` | `UNKNOWN`

### 2.1 Identity

| Field | Meaning | Typical RUN source |
|-------|---------|-------------------|
| `machine` | Controller MACHINENAME | `project.cfg`, overlay suffix |
| `sorter_kind` | Coarse class (`shoe_sorter`, `sawtooth_plus_city_counter`, …) | Derived from `Sorters.asc` names |
| `sorters[]` | Named sorter entities | `Sorters.asc` / `.MACHINE` |
| `sorters[].encoder_io` | Linked encoder IO name | `Sorters.asc` `Encoder ioName` |

### 2.2 Encoders

| Field | Meaning | Typical RUN source |
|-------|---------|-------------------|
| `encoders[]` | Encoder devices | `Encoders.asc` |
| `encoders[].ticks_per_foot` | Scale | `Ticks Per Foot` |
| `encoders[].target_fpm` | Speed setpoint | `Target FPM` |
| `encoders[].enable_bit` | Enable / VFD aux | `EnableBit` |
| `encoders[].jamzone` | Associated jam / process zone | `Jamzone` |

### 2.3 Application / scan / lane topology

| Field | Meaning | Typical RUN source |
|-------|---------|-------------------|
| `app_controls[]` | App sorter control rows | `SrtAppControl.asc` |
| `scan_bosses[]` | Scan zone bosses | `SrtScanBoss.asc` |
| `zone_lanes[]` | Host zone ↔ lane assignment | `SrtZoneLane.asc` |
| `zone_lanes[].full_clear_timer` | Lane full PE timer | `FullClearTimer` |

### 2.4 Tracking runtime (not static topology)

| Field | Meaning | Typical RUN source |
|-------|---------|-------------------|
| `srt_tracks[1..5]` | Named-slot carton track tables | `SrtTrack1..5.asc` |
| `xfr_track` | Transfer track slots | `XfrTrack.asc` |
| `messaging.msg_track` | Tracking message queue | `MsgTrack.asc` (often empty) |

`SrtTrack*` / `XfrTrack*` are **runtime carton slots** (ConfirmScan, ScanZoneID, SorterLane). They prove tracking activity; they do **not** by themselves define PLC divert output maps or induct conveyor chains.

### 2.5 WCS messaging

| Field | Meaning | Typical RUN source |
|-------|---------|-------------------|
| `messaging.wcs_events` | Event → topic map | `WCSEvents.asc` |
| `messaging.msg_wcs` | Outbound WCS queue | `MsgWCS.asc` |
| (related) | Message menu binding | `MsgMap.asc` (`WCS_EVENT` → `MsgWCS`) |

### 2.6 Explicit gaps (engineer-required)

| Gap | Why |
|-----|-----|
| `divert_io_map` | RUN lacks a complete generic PLC divert-output map |
| `tracking_conveyor_chain` | Induct / tracking conveyor sequence not fully derivable from track slots |
| `wcs_tcp_endpoints` | Topics discovered; TCP peer/port wiring is configuration |

---

## 3. Discovery approach

### 3.1 Tooling

```text
python tools/scripts/fortna_sorter_discovery.py \
  --run-dir workspace/cp4-run/RUN \
  --machine ORNCCP4 \
  --out exports/sorter-research
```

Generic: no Greensboro hardcoding. Prefers `File.asc.MACHINE` overlays when present.

### 3.2 Table classes scanned

| Class | Examples |
|-------|----------|
| Sorter config | `Sorters`, `SrtAppControl`, `SrtScanBoss`, `SrtZoneLane`, `SrtHrtBeat`, `SrtRndRobin`, … |
| Encoders | `Encoders` |
| Track runtime | `SrtTrack1..5`, `XfrTrack`, `MsgTrack` |
| WCS / comm | `MsgWCS`, `WCSEvents`, `wcsAlarm`, `wcsSeverity`, `MsgMap` |
| Sort buffers | `SortBuff`, `SortData`, `LogSort` |
| Transfer route | `XfRouteBoss`, `XfRouteTable`, PROJECT `Xfr*` |
| Lane / merge (adjacent) | `MergeRoute`, `CombLane`, `ZipperLane`, `SawLane` |

### 3.3 Active-row rules

- Prefer meaningful `Name` / `Sorter Name` / `Encoder Name` / `EventName`
- Reject `N/A`, `INVALID`, `===…===` placeholders
- `MsgWCS`: Destination topic (`/topic/...`) counts as active even when MsgText blank
- Numeric empty slots in `SrtTrack*` are **not** active

### 3.4 CP4 vs CP2 (this site)

| Item | ORNCCP4 | ORNCCP2 |
|------|---------|---------|
| Active `Sorters` | 2 (`SAWTOOTH_MERGE`, `CITY_LANE`) | 0 |
| Active `Encoders` | 2 (`ENC414`, `ENC424`) | 0 |
| Active `SrtZoneLane` | 2 (City Counter / Straight) | 0 |
| Active `SrtTrack*` | 98 (slot 1) | 0 |
| `MsgTrack` | 0 bytes | 0 bytes |
| `MsgWCS` / `WCSEvents` | populated | populated (shared messaging) |

**Conclusion:** On Greensboro, sorter subsystem ownership is **ORNCCP4**. CP2 retains schemas and WCS traffic but not sorter entity configuration.

---

## 4. Generation boundary

```text
RUN tables
   │
   ▼
fortna_sorter_discovery.py
   │
   ├─ table_inventory.json          (DISCOVERED schemas + counts)
   ├─ subsystem_model.json          (MODELED SorterModel skeleton)
   └─ generation_support_matrix.json
          │
          ├─ DISCOVERED / MODELED     → safe to consume in compilers
          ├─ CONFIGURATION_REQUIRED   → AOI/stub reuse needs engineer input
          ├─ GENERATABLE              → (none for Tracking/WCS in this pass)
          └─ NOT_SUPPORTED            → do not emit Sorter_Track / WCS / ShippingSorter
```

### 4.1 Existing Site Forge code (inventory only)

| Asset | Role | Generic? |
|-------|------|----------|
| `tools/libraries/programs/Sorter_Track_Program.L5X` | Gold PLC5 Sorter_Track (~16 routines, TRK_* / Enc_*) | **No** (Greensboro-fixed) |
| `tools/libraries/programs/WCS_Interface_TCP_IP_Program.L5X` | Gold WCS TCP pack | **No** |
| `tools/libraries/programs/ShippingSorter_Area_L3_Program.L5X` | Gold shipping sorter L3 | **No** |
| `tools/libraries/TRK_Divert_WaveFunction_AOI.L5X` | Divert wave AOI | Reusable AOI; wiring still required |
| `tools/libraries/Enc_Routine_ST.L5X` | Encoder ST stub | Pattern only |
| `tools/scripts/fortna_sorter_build.py` | Divert-limit + token rename on gold pack | **Not** generic generation |
| `tools/scripts/fortna_mhs_sorter.py` | MHS FMS / Non-Con scaffolds | Not FortnaPlus RUN Sorter_Track |
| `fortna_autogen.py` pack merge | Optional include of gold packs | Must stay opt-in / non-silent |

### 4.2 What is **not** in scope for generation here

- Emitting fake / synthetic WCS or sorter L5X
- Reading finished PLC4 as a generation seed
- Silently auto-including `Sorter_Track` or `WCS_Interface_TCP_IP` from discovery alone
- Claiming `GENERATABLE` for Tracking/WCS without a complete generic library path

---

## 5. Reproduce

```text
python tools/scripts/fortna_sorter_discovery.py \
  --run-dir workspace/cp4-run/RUN --machine ORNCCP4 \
  --out exports/sorter-research

python tools/scripts/fortna_sorter_discovery.py \
  --run-dir workspace/active/RUN --machine ORNCCP2 \
  --out exports/sorter-research/cp2-comparison --subsystem-only
```

See also: `docs/CP4_BLIND_DISCOVERY.md` (`tracking_wcs.json`), `docs/GOLD_EQUIPMENT_TO_BUILD.md`, `docs/SORTER_BUILD_UI_REVERT.md`.

---

## 6. Headline (ORNCCP4 discovery)

| Item | Value |
|------|------:|
| Tables inventoried | ~98 |
| Tables with active rows | ~37 |
| Active sorters | 2 |
| Active encoders | 2 |
| Active zone lanes | 2 |
| SrtTrack active slots | 98 (Track1) |
| GENERATABLE capabilities | **0** |
| Tracking/WCS generation | **NOT_SUPPORTED** |
