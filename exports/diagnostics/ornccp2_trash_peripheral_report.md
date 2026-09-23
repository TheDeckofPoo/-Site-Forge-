# ORNCCP2 Trash Area — Peripheral Fidelity Pass

## Scope

Nine conveyors in Site Forge `Trash_Zone` vs finished `ModuleC_Trash_Area`.

**Out of scope:** conveyor order, downstream sequence, LastConv topology.

## Findings (classified)

| # | Topic | Classification | Notes |
|---|--------|----------------|-------|
| 1 | `Conv_UDT.Type` Transport+MS | `LIBRARY_CONTRACT_UNKNOWN` / keep library+RUN | Library P3000:=3, P4000:=2. RUN Trash belts are STRAIGHT/BELT → code **3**. Finished Trash shows Type:=**2** (contradicts library+RUN). **Do not flip 3→2.** Engineer override may be needed later. |
| 2 | Fast_Conv PE roles | `FIXED_GENERICALLY` | Jam PE no longer fills Exit/Add; empty product → `NO_PE`. |
| 3 | PE_Logic Slow+Fast dual exec | `FIXED_GENERICALLY` | `Conv_PE` / `PE_Logic` Slow-only; Fast keeps `Full_PE` via `Conv_Full`. |
| 4 | Area Slow scaffold thin | `FIXED_GENERICALLY` (scaffold) + `ENGINEER_ASSIGNMENT_REQUIRED` (bodies) | Emit Area_Logic / Area_PI / Control_Station / Stacklight stubs per library Slow JSR chain. Bodies stay REVIEW until ownership proven. |
| 5 | Area parameter init | `FIXED_GENERICALLY` | L1 Area ST now emits library seven-member set (Start/Rst/Sil/AutoSil/JamRst/FltRst/EngMgmt). |
| 6 | Control Station logic | `ENGINEER_ASSIGNMENT_REQUIRED` | CS_UDT devices exist from I/O; Area ownership not proven from RUN → Slow Control_Station stub + L1 CS comment. |
| 7 | Stacklight | `ENGINEER_ASSIGNMENT_REQUIRED` | Slow Stacklight stub; no invented Area ownership of status IO. |
| 8 | PE timer init | `FIXED_GENERICALLY` | Init PE commissioning defaults + PETime/FullTime from `Init.*` when PE devices present. |
| 9 | MPS1006 vs P1006_MS | `LIBRARY_CONTRACT_UNKNOWN` / investigate | Library templates use `MPS3000`/`MPS4000`; production/oracle emit `P####_MS`. Finished Trash Slow_Flt using `MPS1006` is a **naming/role open question** — not changed. |
| 10 | PI area vs main area | `FIXED_GENERICALLY` (capability) | `ConveyorRow.pi_area` + confidence; Conv_PI packs honor distinct `pi_area` when set; else `FALLBACK_MAIN_AREA`. Topology membership not solved. |

## Evidence — Conv.Type

| Source | P1006 | P312 |
|--------|-------|------|
| RUN ASC Type | STRAIGHT | ZEROPRESSURE |
| Site Forge classify | 3 Transport+MS | 2 Accum+MS |
| Library preset | P3000:=3 | P4000:=2 |
| Finished oracle | **2** | **3** |

Finished vs library+RUN is inconsistent; Site Forge keeps library+RUN.

## MPS vs MS (item 9)

- Library sample motor tags: `MPS3000`, `MPS4000` (`Motor_Starter_UDT`)
- Production binder / Slow_Flt emit: `P{stem}_MS` via `NO_MS` clone
- Physical AUX I/O oracle: `P124_MS.I.Auxiliary_Forward`
- Finished Trash Slow_Flt operand `MPS1006` is **not** explained by RUN evidence yet → leave as open investigation; do not retarget Slow_Flt to MPS*.

## New engineer assignment surfaces

1. Area ↔ Control Station ownership  
2. Area ↔ Stacklight/status ownership  
3. Optional `pi_area` per conveyor (when PI membership ≠ logic Area)  
4. Optional Conv.Type override if site intentionally diverges from library codes  

## Tests

`tests/compiler/test_trash_peripheral_fidelity.py`
