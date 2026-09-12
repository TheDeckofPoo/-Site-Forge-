## Spiral / circular assembly (RUN analysis)

Generated from plant-wide `Conveyor.asc` via `tools/scripts/fortna_spiral_area_analysis.py`.  
RUN coordinates were **not** modified. Finished PLC was **not** used. **No spiral symbol was invented.**

### Best CP2 candidate — shipping-sorter spiral exit bank

| Field | Value |
|-------|-------|
| Confidence | **HIGH** |
| Composition | `multiple_CURVE_records` + `curve_plus_straight` + lettered lane bank |
| Region | y≈53.3k–60.5k, x≈48.1k–102.7k (CP2 print divert / spiral-exit dense area) |
| Autogen coverage | **0 / 76** cluster members (explains missing spiral on Autogen-scoped canvas) |

**Core CURVE records (spiral exits):**  
`P700A`, `P700B`, `P700C`, `P600C`–`P600E`, `P600F`–`P600K`, `P600M`–`P600P`, `P720`  
(shared Angle≈270°, IR≈258.3, elev≈1850, field `b`=190 → ~80° mate-scored sweeps)

**Adjacent bank members (same letter lanes):**  
`P602*` (ZP), `P610*`/`P612*` (STRAIGHT), `P702*` (BELT incline), `P704*`/`P706*`/`P708*`/`P710*`

**Evidence**
- 13+ aligned lettered `CURVE` exits at the same Y/angle/IR (not one nested multi-turn body)
- `Errors.asc` labels PE608* as **“LANE FULL AT SPIRAL EXIT TO LANES …”** next to this bank
- Aggregate |sweep| ≈ 1570° across the clustered curves
- Current Autogen Transport graph (~35 tags) includes **none** of these members

### What RUN does *not* contain

- No concentric nested CURVE stack (shared arc center, increasing radii) that would redraw the print’s multi-turn spiral graphic
- No `P608*` mechanical conveyor rows (only PE/Errors references)
- `TRIANG` rows are SSV/solenoid labels, not spiral body geometry
- Elevation changes exist on belts/inclines but are unused in planar `fortna_physical_geometry` paths

### Secondary note (Autogen dense crop)

A separate curve+straight cluster around `P126`/`P134`/`P142`/`P148`… sits in the Autogen-scoped dense SVG crop. That is a normal turning corridor, **not** the shipping-sorter spiral bank above.

### Artifacts

- `exports/layout-research/spiral_area_analysis.json`
- `exports/layout-research/physical_runs.json`
- `exports/layout-research/overlap_clusters.json` (classes include `CONNECTED_SERIAL`, `CURVE_ASSEMBLY`, …)
