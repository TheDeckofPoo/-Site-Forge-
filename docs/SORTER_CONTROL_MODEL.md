# Sorter Control Model

**Status:** Knowledge-layer control model (discovery / semantics)  
**Sources:** `FPC-Sorter-Control-Module` (training docs = semantics) + RUN sorter tables (facts)  
**Firewall:** Finished PLC is never generation input. Greensboro gold packs do not qualify as generic libraries.

Related: `docs/SORTER_COMPILER_MODEL.md`, `docs/SORTER_GENERATION_ROADMAP.md`, `exports/sorter-research/`.

---

## 1. Purpose

Describe how FortnaPlus **Sorter Control Module** tables relate, which are **static configuration** vs **runtime tracking**, and what Site Forge may discover vs generate.

| Layer | Responsibility |
|-------|----------------|
| Training docs | Semantics of tables / messages / behaviors |
| RUN ASC | Site facts (named rows, linkages, ownership) |
| SiteModel `sorters[]` | Discovery stubs (`generation_state=NOT_SUPPORTED` until roadmap says otherwise) |

---

## 2. Module activation (doc semantics)

Per FPC-Sorter-Control-Module, the sorter module is activated as batch jobs:

| Batch | Role |
|-------|------|
| `Srt App SERV` | Messages to/from WCS / CommCore |
| `Srt App CTRL` | Hardware control logic |
| `Srt Sim SORT` | Simulation features on SORT process |

Multiple sorters may be configured on a single Automation Controller.

---

## 3. Static configuration tables

These define the logical sorter entity and divert/scan topology. Discovery treats named rows as **static** evidence (`sorter_static`).

| Table | Role |
|-------|------|
| `Sorters.asc` | Sorter entity + encoder IO link |
| `SrtAppControl.asc` / App Sorter Configuration | Top-level sorter (CommCore interface, motor, error policy) |
| `SrtScanBoss.asc` | Scan zone boss / update points |
| `SrtZoneLane.asc` | Host zone ↔ lane assignment |
| `SrtLaneNotAvail.asc` | Lane-not-available / stop-or-reassign windows |
| `SrtBadGapCnfg.asc` | Bad-gap handling |
| `SrtRndRobin.asc` | Round-robin assignment |
| `SrtHrtBeat.asc` | Heartbeat / comm health |
| `SrtSimConfig.asc` | Simulation configuration |
| `SrtCommMsgMatch.asc` | Message match rules |
| `Encoders.asc` | Encoder scale / enable / jamzone (shared with sawtooth) |

**Doc semantics (SrtAppConfig highlights):**

- `ErrConfig` chooses stop-if-unavailable vs reassign/recirc behavior
- Message tables (`CrrMsgTable`, `DcmMsgTable`, `CsuMsgTable`, `CsmMsgTable`) should usually be dedicated per sorter for CRR/CSM
- `SorterCnvMtr` + `MtrACTION` allow stopping the sorter conveyor under lane-not-avail / scan-error policies
- `ControlMachine` scopes ownership to an AC

---

## 4. Runtime tracking tables

These are **carton slots / live state**, not static divert topology. Discovery tags them `sorter_runtime`.

| Table | Role |
|-------|------|
| `SrtTrack1..5.asc` | Named-slot carton track (ConfirmScan, ScanZoneID, SorterLane, …) |
| `XfrTrack.asc` | Transfer track slots |
| `MsgTrack.asc` | Tracking message queue (often empty) |
| `SrtScanSts.asc` | Scan status lookup / live status |

**Rule:** Runtime rows prove tracking activity; they do **not** by themselves define PLC divert output maps or induct conveyor chains (`divert_io_map`, `tracking_conveyor_chain` remain engineer-required gaps).

---

## 5. Messaging / WCS (inventory only)

| Table | Role |
|-------|------|
| `WCSEvents.asc` | Event → topic map |
| `MsgWCS.asc` | Outbound WCS queue |
| `MsgMap.asc` | Message menu binding (`WCS_EVENT` → `MsgWCS`) |

Message types (doc): CRR, CSM, CSU, DCM, RHS. PLC generation for WCS TCP endpoints is **NOT_SUPPORTED** until a complete generic library path exists.

---

## 6. Site Forge discovery mapping

| SiteModel field | Typical RUN evidence |
|-----------------|----------------------|
| `sorters[]` | `Sorters.asc` named rows (+ optional sorter-research integrate) |
| `encoders[]` | `Encoders.asc` when sawtooth/sorter path runs |
| `tracking_systems[]` / `wcs_interfaces[]` | Track / WCS tables with active rows |
| `subsystems.sorter.generation_state` | Always `NOT_SUPPORTED` in this knowledge layer |
| `sorter_table_classes` | Counts of static vs runtime active rows |

Activity classifier evidence kinds:

- `sorter_table` / `sorter_static` — configuration participation
- `sorter_runtime` — track/slot participation (weaker weight)

---

## 7. Explicit non-goals

- Do not invent divert IO maps from track slots
- Do not treat Greensboro `Sorter_Track_Program.L5X` as a generic compiler
- Do not mark sorter generation READY from discovery alone
- Do not require PE/lane naming conventions; RUN relationships win

---

## 8. Print & Apply adjacency

Print&Apply training docs (`docs/training/P&A Documents/`) describe labeling / transfer behaviors that may sit upstream or downstream of sorter flows. PASIM1 training RUN tar is a **binary/menu shell without ASC tables** — it validates fail-closed discovery, not sorter population.
