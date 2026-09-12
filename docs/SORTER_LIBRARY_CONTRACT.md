# Sorter Library Contract (Capability Leaves)

**Branch:** `feature/integration-hardening`  
**Policy:** Capability-by-capability contracts only. No `Sorter_Track` monolith emit. Greensboro gold packs are **not** generic libraries. Finished PLC names are never generation rules.

Companion artifacts: `exports/integration-hardening/sorter_leaves_*.json`, `docs/SORTER_COMPILER_MODEL.md`, `docs/SORTER_GENERATION_ROADMAP.md`.

Reusable-with-config libraries (not full sorter programs):

| Asset | Role |
|-------|------|
| `tools/libraries/Enc_Routine_ST.L5X` | Encoder ST stub — site tags / scale required |
| `tools/libraries/TRK_Divert_WaveFunction_AOI.L5X` | Divert wave AOI — lane/IO map + timing still engineer-required |

**Default rule:** Divert **trigger** stays `NOT_SUPPORTED` until a full generic timing/IO contract exists. Do not clone `Sorter_Track_Program.L5X`.

---

## Legend

| Field | Meaning |
|-------|---------|
| **State** | Default capability disposition (`GENERATED` / `MODELED` / `CONFIGURATION_REQUIRED` / `NOT_SUPPORTED`) |
| **AOI / program** | Generic library unit (never a finished site program) |
| **UDT** | Datatype / constant surface when present |
| **RUN fields** | Tables / columns that may feed the leaf |
| **Relationships** | Equipment / messaging links the leaf expects |
| **Optional / engineer** | Config the engineer may supply; gaps that block emit |
| **Outputs** | What generation may emit when state allows |

---

## Capability contracts

### 1. Encoder / speed — default `GENERATED` (when `Encoders.asc` active)

| | |
|--|--|
| **AOI / program** | `Enc_Routine_ST.L5X` + encoder controller tags |
| **UDT** | Optional `ENC_*` tags |
| **RUN fields** | `Encoders.Encoder Name`, Encoder I/O, Ticks Per Foot, Target FPM |
| **Relationships** | `sorter.encoder_io` ↔ `Encoders.asc` |
| **Optional / engineer** | Calculated FPM; enable/reset wiring when missing |
| **Outputs** | Encoder controller tags; optional enable/reset stubs |

### 2. Induct detection — default `GENERATED` (when scan/PE evidence exists)

| | |
|--|--|
| **AOI / program** | None required (structure tags) |
| **UDT** | — |
| **RUN fields** | `ScnScanDevice`, `SrtScanBoss`, Conveyor PE |
| **Relationships** | scanner → scan_zone; PE role `SCAN_TRIGGER` / `DETECTION` |
| **Optional / engineer** | Induct PE confirmation when ambiguous |
| **Outputs** | Induct structure tags |

### 3. Token creation — default `MODELED`

| | |
|--|--|
| **AOI / program** | — |
| **UDT** | — |
| **RUN fields** | `SrtTrack*` runtime slots (not equipment topology) |
| **Relationships** | — |
| **Optional / engineer** | Tracking slot sizing |
| **Outputs** | None until a generic track-token path exists |

Runtime track rows prove activity; they do **not** define divert IO maps.

### 4. Scanner association — default `GENERATED` (when scan devices present)

| | |
|--|--|
| **AOI / program** | — |
| **UDT** | — |
| **RUN fields** | `ScnScanDevice.Name`, ScanZone, ScanType, Machine |
| **Relationships** | Machine serial / TCP peer |
| **Optional / engineer** | — |
| **Outputs** | Scanner device tags; scan zone tags |

### 5. Track offset — default `NOT_SUPPORTED`

| | |
|--|--|
| **AOI / program** | — |
| **UDT** | — |
| **RUN fields** | — (no complete generic RUN→offset map) |
| **Relationships** | — |
| **Optional / engineer** | Encoder counts between induct and divert |
| **Outputs** | — |

### 6. Route request — default `CONFIGURATION_REQUIRED`

| | |
|--|--|
| **AOI / program** | — |
| **UDT** | — |
| **RUN fields** | `XfRouteBoss`, `XfRouteTable`, `MsgMap` |
| **Relationships** | WCS peer |
| **Optional / engineer** | Destination map |
| **Outputs** | — until destination map confirmed |

### 7. Route / destination response — default `NOT_SUPPORTED`

| | |
|--|--|
| **AOI / program** | — |
| **UDT** | — |
| **RUN fields** | `MsgWCS`, `WCSEvents` (inventory only) |
| **Relationships** | — |
| **Optional / engineer** | Full WCS response contract |
| **Outputs** | — |

### 8. Divert readiness — default `CONFIGURATION_REQUIRED`

| | |
|--|--|
| **AOI / program** | `TRK_Divert_WaveFunction_AOI.L5X` (config model only) |
| **UDT** | — |
| **RUN fields** | `SrtZoneLane`, `Sorters` |
| **Relationships** | Lane PE; lane conveyor |
| **Optional / engineer** | Wave parameters; **lane → divert map (required)** |
| **Outputs** | Divert configuration model (not trigger logic) |

### 9. Divert trigger — default `NOT_SUPPORTED`

| | |
|--|--|
| **AOI / program** | `TRK_Divert_WaveFunction_AOI.L5X` referenced but **not** auto-wired |
| **UDT** | — |
| **RUN fields** | — |
| **Relationships** | — |
| **Optional / engineer** | Full divert timing / IO contract |
| **Outputs** | — |

Stays `NOT_SUPPORTED` until a complete generic contract exists. Do not emit from gold `Sorter_Track`.

### 10. Divert confirmation — default `NOT_SUPPORTED`

| | |
|--|--|
| **AOI / program** | — |
| **UDT** | — |
| **RUN fields** | — |
| **Relationships** | — |
| **Optional / engineer** | Confirm PE / host ack contract |
| **Outputs** | — |

### 11. Divert rate limiting — default `NOT_SUPPORTED`

| | |
|--|--|
| **AOI / program** | — |
| **UDT** | — |
| **RUN fields** | — |
| **Relationships** | — |
| **Optional / engineer** | Rate / gap policy |
| **Outputs** | — |

### 12. Recirculation — default `NOT_SUPPORTED`

| | |
|--|--|
| **AOI / program** | — |
| **UDT** | — |
| **RUN fields** | — |
| **Relationships** | — |
| **Optional / engineer** | Recirc lane / ErrConfig policy wiring |
| **Outputs** | — |

### 13. Reason code — default `GENERATED`

| | |
|--|--|
| **AOI / program** | — |
| **UDT** | Reason-code constants |
| **RUN fields** | `Srt*` status vocab when present |
| **Relationships** | — |
| **Optional / engineer** | — |
| **Outputs** | Reason-code DINT / constant tags |

### 14. WCS event reporting — default `MODELED`

| | |
|--|--|
| **AOI / program** | — (no WCS program emit) |
| **UDT** | — |
| **RUN fields** | `WCSEvents`, `MsgWCS` |
| **Relationships** | MsgMap topic binding |
| **Optional / engineer** | TCP peer / port (configuration) |
| **Outputs** | Inventory / model only — PLC generation `NOT_SUPPORTED` |

---

## Explicit non-goals

- No `Sorter_Track` / `WCS_Interface_TCP_IP` / shipping-sorter L3 monolith generation
- No inventing divert IO from `SrtTrack*` slots
- No finished-PLC sorter or Area names as generation rules
- Do not mark divert trigger `GENERATED` from AOI presence alone
