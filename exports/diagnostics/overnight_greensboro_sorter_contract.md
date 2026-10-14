# Overnight Greensboro Sorter Contract (oracle only)

**Mission:** Phase 5 — structural oracle for Area_L3 + Sorter_Track  
**Policy:** Validation / evidence mapping only. Do **not** copy addresses, site constants, or finished-PLC names into production discovery.  
**Demo policy:** Tomorrow’s demo does **not** require full sorter PLC generation.  
**Status:** **SORTER PLC GENERATION — NOT YET QUALIFIED**

---

## Oracles used

| Role | Path | Notes |
|------|------|-------|
| PLC4 Autogen Excel | `C:\dev\Autogen Excel\2 PLC4\ORLY_Greensboro_NC_PLC4.L5X` | Mission path — has `Sorter_Track` + `CityCounter_Area_L3` |
| PLC5 Autogen Excel | `C:\dev\Autogen Excel\3 PLC5\7-9-26\ORLY_Greensboro_NC_PLC5.L5X` | Mission family — has `ShippingSorter_Area_Area_L3` (skeleton in this export) |
| PLC5 finished structural cross-check | `C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT\ORLY_Greensboro_NC_PLC5_RTfinished.L5X` | Pack-contract oracle only — confirms `Sorter_Track` + `ShippingSorter_Area_L3` routine **names/roles** |
| Existing pack contract | `config/program_packs/sorter_track_contract.json` | Phase 1 emit contract (already in repo) |
| Pack diff | `docs/evidence/PLC4_PLC5_SORTER_PROGRAM_PACK_DIFF.md` | Structural delta PLC4↔PLC5 |

No MSCRENOSHIP / Reno addresses were taken from these files.

---

## Architecture split (structural)

| Controller | Sorter tracking program | Area equipment program (L3) |
|------------|-------------------------|-----------------------------|
| PLC4 | `Sorter_Track` (15 routines) | Area L3 example: `CityCounter_Area_L3` |
| PLC5 | `Sorter_Track` (finished oracle; 17 routines incl. optional leaves) | `ShippingSorter_Area_L3` / Autogen name `ShippingSorter_Area_Area_L3` |

**Task class (from pack contract, not hardcoded into ship discovery):** tracking PERIODIC task schedules `Sorter_Track`. WCS is a **separate** optional pack (`WCS_Interface_TCP_IP`).

---

## Sorter_Track — routine → source evidence map

Structural roles only. Instance tags/counts expand from RUN SorterModel; timing values remain engineer/commissioning.

| Routine | Role | Source evidence required (generic) | Emit class |
|---------|------|------------------------------------|------------|
| `Main` | JSR scheduler | Routine set enabled by pack + optional leaves | REQUIRED_STANDARD |
| `Encoder` | Encoder speed / PPI | `Encoders.asc` (ticks/FPM/enable) + tracking conveyor enable path | REQUIRED_STANDARD / MODEL_EXPANDED |
| `Track_Pointer` | Track pointer AOI | Tracking path(s): encoder + conveyor chain | REQUIRED_STANDARD / MODEL_EXPANDED |
| `Track_Induct_Package` | Induct token | `Inpoints.asc` induct PE + induct conveyor | REQUIRED_STANDARD / MODEL_EXPANDED |
| `Track_Manual_Destination` | Manual dest | Manual-dest group / AOI binding | REQUIRED_STANDARD |
| `Scanner` | Scan / decision | ScanBoss + scan zone + scanner device tables (not “scanner ≡ sorter”) | REQUIRED_STANDARD |
| `Track_Package` | Package track / exit PE | Tracking PE path(s) | REQUIRED_STANDARD / MODEL_EXPANDED |
| `Track_Lost_Package` | Lost detect | Exit / lost PE path | REQUIRED_STANDARD / MODEL_EXPANDED |
| `Divert_Lane_Status` | Lane enable / full PE | `SrtZoneLane` + divert confirm PE | REQUIRED_STANDARD / MODEL_EXPANDED |
| `Track_Divert_Package` | Divert trigger cluster | Per-divert topology + output IO | REQUIRED_STANDARD / MODEL_EXPANDED |
| `Wave_Divert` | Wave divert AOI | Per physical divert output | REQUIRED_STANDARD / MODEL_EXPANDED |
| `Divert_Rate_Limit` | Rate limit | Per divert rate policy | REQUIRED_STANDARD / MODEL_EXPANDED |
| `Track_Divert_Confirm` | Confirm → often WCS-facing | Confirm PE / diverted lane status | REQUIRED_STANDARD |
| `Track_Offset_Find` | Offset find shells | Divert/offset PE pairs — **values NOT_SUPPORTED from RUN alone** | REQUIRED_STANDARD (shell) |
| `Response_Time` | Metrics / WCS response timing | Runtime metrics block | REQUIRED_STANDARD |
| `Gridlock_Prevention` | Optional leaf | Engineer policy (PLC5 finished) | OPTIONAL_STANDARD |
| `RT_Virtual_Enc` | Optional ST leaf | Virtual encoder policy (PLC5 finished) | OPTIONAL_STANDARD |

### PLC4 Autogen Excel inventory (evidence)

`Sorter_Track` routines observed:  
`Divert_Lane_Status`, `Divert_Rate_Limit`, `Encoder`, `Main`, `Response_Time`, `Scanner`, `Track_Divert_Confirm`, `Track_Divert_Package`, `Track_Induct_Package`, `Track_Lost_Package`, `Track_Manual_Destination`, `Track_Offset_Find`, `Track_Package`, `Track_Pointer`, `Wave_Divert`.

### PLC5 finished structural inventory (cross-check only)

Same core set **plus** `Gridlock_Prevention`, `RT_Virtual_Enc`.

---

## Area_L3 — routine → source evidence map

Area L3 is **equipment / area logic**, not Sorter_Track. It consumes transport/area identity, conveyors, PEs, control stations, and safety membership — not divert wave logic.

### PLC5 Autogen Excel — `ShippingSorter_Area_Area_L3`

| Routine | Observed in 7-9-26 Autogen export | Source evidence needed |
|---------|-----------------------------------|------------------------|
| `Main_Routine` | Present (body essentially empty in this export) | Area program shell / JSR host |

Sibling ShippingSorter area programs in the same Autogen PLC5 export (context, not all required for demo):  
`ShippingSorter_Area_Area_Fast`, `_Slow`, `_L1`, `_L2`, plus Safe/ES zone programs.

### PLC5 finished structural — `ShippingSorter_Area_L3`

Present as area equipment program family (`_Fast/_Slow/_L1/_L2/_L3`). Used only to confirm **program class exists** beside `Sorter_Track`.

### PLC4 Autogen Excel — `CityCounter_Area_L3` (Area_L3 pattern example)

| Routine | Source evidence needed (generic) |
|---------|----------------------------------|
| `Main_Routine` | Area scheduler |
| `Conv_Name` | Conveyor identity in area |
| `Conv_Track` / `Conv_Track_Offset` | Tracking conveyor + offset shells |
| `Induct_Token` | Induct token path |
| `Reason_Code` | Fault / reason reporting |
| `Scanner` | Area scanner interface (if present) |

**Rule:** Area_L3 evidence comes from transport/area discovery + equipment membership. It must **not** invent sorter divert outputs from area naming alone.

---

## What RUN must supply before generation can be truthful

For a ship sorter (equipment type **SORTER**):

1. Sorter identity (`Sorters.asc` + machine overlay) — exclude SCAN-only rows as the sorter  
2. App control / motor (`SrtAppControl.SorterCnvMtr`)  
3. Encoder parameters (`Encoders.asc`)  
4. Induct PE + tracking conveyor path (`Inpoints` + EnableBit→Mtrchain)  
5. Lane / divert topology (`SrtZoneLane` + `Outpoints`)  
6. Confirm PE per divert (`Outpoints.Verify I/O`)  
7. Optional: WCS topic map (`WCSEvents` / `MsgWCS`) — **interface emit still NOT_SUPPORTED**

Missing or soft (`MEM_` / `INVALID` / `FUTURE`) fields stay **REVIEW / UNKNOWN**.

---

## Generator qualification statement

| Capability | Status |
|------------|--------|
| Blind RUN discovery (inventory / model) | Supported (existing `fortna_sorter_discovery.py`) |
| Sorter_Track Phase 1 pack compiler | Exists (`fortna_sorter_pack_compiler.py`) — **not demo-qualified** for MSCRENOSHIP acceptance |
| ShippingSorter Area_L3 generation | **NOT_SUPPORTED** (gold pack / engineer wiring) |
| WCS_Interface_TCP_IP generation | **NOT_SUPPORTED** |
| Full divert IO PLC map generic emit | **NOT_SUPPORTED** |

### SORTER PLC GENERATION — NOT YET QUALIFIED

Demo should show **truthful discovery** (identity, motor, encoder, induct, lanes, divert IO, PE coverage, WCS detected, review counts). Do not claim Studio-ready sorter L5X acceptance from this overnight pass.

---

## Forbidden shortcuts (checked)

- No `if site == MSCRENOSHIP` production rules added  
- No Greensboro addresses/names copied into ship discovery  
- No scanner selected as sorter by name alone  
- No metric gaming by reclassifying FUTURE/MEM_ as resolved  
