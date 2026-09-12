# CP2 Completion Gate — Greensboro ORNCCP2

**Generated (UTC):** 2026-09-12T04:58:14.438378+00:00
**Active RUN:** `workspace/active/RUN`
**Machine:** ORNCCP2
**Finished PLC (validation only):** `C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT\ORLY_GreensboroPLC2_NC_Finished.L5X`

## Policy

- Generation inputs: CP2 RUN + engineer Site Forge workbook + approved generic libraries only.
- Finished CP2 PLC is a **post-generation validation oracle** — never used to populate workbook/areas/E-stop mappings.
- No single overall accuracy score — **category scores only**.
- Do not invent affected-equipment mappings for E-stops.
- Do not discard physical equipment merely because one I/O mapping is missing.
- Do not arrange by P-number; do not alter RUN geometry.

## Artifact index

| File | Purpose |
|---|---|
| `exports/cp2-gate/io_inventory.json` | RUN-scoped I/O inventory |
| `exports/cp2-gate/equipment_inventory.json` | Equipment completeness + ownership confidence |
| `exports/cp2-gate/ownership_classification.json` | RUN-only EXACT CP2 ownership classes |
| `exports/cp2-gate/area_safety_inventory.json` | Areas / ES zones from workbook |
| `exports/cp2-gate/estop_inventory.json` | E-stop devices (no invented equipment maps) |
| `exports/cp2-gate/layout_metrics.json` | Physical layout + visual acceptance |
| `exports/cp2-gate/library_provenance.json` | Library / program provenance |
| `exports/cp2-gate/comparison_summary.json` | Category scores vs finished PLC |
| `exports/cp2-gate/generated/` | Autogen JSON reports for this gate (`.L5X` is gitignored — regenerate via orchestrator) |
| `exports/cp2-gate/compare/` | `fortna_l5x_compare` reports |

## Category scores (no overall score)

| Category | Verdict | Detail |
|---|---|---|
| IO coverage | **PARTIAL** | IO_MAP tag overlap 13/224 = 5.8%; EIP mapped 34/unmapped 202 |
| conveyor coverage | **FAIL** | 18/57 = 31.6% |
| area accuracy | **FAIL** | 0/18 = 0.0% |
| ES-zone accuracy | **FAIL** | 0/18 = 0.0% |
| downstream accuracy | **FAIL** | 4/18 = 22.2% |
| exit PE accuracy | **FAIL** | 4/18 = 22.2% |
| E-stop/safety coverage | **PARTIAL** | Device presence vs generated; affected-equipment not invented |
| program structure | **PARTIAL** | Structural program differences vs finished (validation only) |

| layout visualization (Curtis) | **CURTIS ACCEPTANCE REQUIRED** | Calibration `greensboro-infeed-v1` + physical schematic renderer shipped. Do **not** auto-PASS. Curtis must compare beside the print. |

### 1. I/O inventory: **PASS**

Scoped ORNCCP2 I/O points: **243** (DI 52, DO 191, PE 44, MS out 60, OL/aux 59, control stations 21, E-stop/safety 18, VFD 0). EIP mapped 34 / unmapped 202.

### 2. Equipment completeness: **PARTIAL**

RUN Autogen-scoped conveyors (PE/VFD-only historical path): **37**; workbook represented: **37**; EXACT ownership CP2_CONFIRMED: **59**; CP2_CANDIDATE: **4**; NOT_CP2: **147**; UNKNOWN: **74**; motors/MS 118, photoeyes 44, control stations 21, E-stops 18. Ownership uses RUN-only exact PE/motor/VFD + Mtrchain; equipment with missing I/O is retained.

#### Ownership findings (37 vs 57)

- **CP2_CONFIRMED = 59** via exact RUN device association (includes motors + Mtrchain).
- **Old Autogen-scoped count = 37** undercounted because untagged mechanical rows were linked from PE/VFD only — motors were omitted (the RUN scoping hole).
- **Finished PLC conveyor count = 57** is a **validation observation only**, not a generation target. Do not copy or force CONFIRMED to equal 57.
- Gap explanation: RUN scoping hole (motors omitted from Autogen link set) + naming granularity (finished lettered AOIs such as `P130A`–`P130E` / `P145A`–`E` are device evidence on parent mechanical `P130` / `P145` in RUN — lettered conveyors are **not invented** from finished PLC).
- Sample CONFIRMED: `P1000`, `P1001`, `P123`, `P124`, `P128`, `P130`, `P132`, `P145`, `P220`, `P220A`, `P309`, `P310`, …
- Sample CANDIDATE (cross-controller device evidence): `P215`, `P226`, `P229`, `P408`
- Artifact: `exports/cp2-gate/ownership_classification.json` (also embedded in `equipment_inventory.json`).
- Classifier CLI:
  ```
  python tools/scripts/fortna_cp2_ownership.py \
    --run-dir workspace/active/RUN --machine ORNCCP2 \
    --out exports/cp2-gate/ownership_classification.json
  ```

### 3. Areas and ES zones: **FAIL**

Workbook areas: `['ORNCCP2_Area']`; ES zones: `['ORNCCP2_ESZone1']`. Engineer-config-required rows: 0. Finished PLC area names (ModuleB/ModuleC/Trash) were **not** copied into workbook input. Post-generation structural compare is in `area_safety_inventory.json`.

### 4. E-stop inventory: **PARTIAL**

CP2 E-stop/safety devices from Conveyor.asc: **44**. Affected-equipment mappings are **not invented**. Missing area/zone/reset fields marked `ENGINEER CONFIGURATION REQUIRED`.

### 5. Physical layout metrics: **CURTIS ACCEPTANCE REQUIRED**

Placed **37**, unplaced 0, auto connections **9** (geometry confirmed **7** + high **2**), ambiguous 28, disconnected 21. Geometry inventory: **PASS** (calibration applied). Visualization gate: **CURTIS ACCEPTANCE REQUIRED** (do not auto-PASS).

#### Coordinate calibration (`greensboro-infeed-v1`)

See `docs/RUN_GEOMETRY_CALIBRATION.md`.

| Finding | Confidence |
|---------|------------|
| `X_cord`/`Y_cord` = **infeed/ENTRY end** (not footprint center) | **HIGH** |
| `Angle` = flow deg CCW from +X; `Length` = full centerline from infeed | **HIGH** |
| Prior center±L/2 model **rejected** (false 250–750u gaps; infeed yields 0) | **HIGH** |
| `CURVE` `Length=-1`; body from `Inside_Radius` + tangent stubs + 90° arc | **MEDIUM** |
| Tangents are stub lengths, not topology FKs | **HIGH** |

Finished PLC was **not** used to answer geometry questions. Print is visual acceptance only after the hypothesis.

#### Physical schematic renderer

Transport Build now separates:

- **Physical Equipment Model** — Site Model / RUN geometry → `#tb-schematic` continuous bodies
- **Graph / topology relationships** — wires / mates only when RUN-confirmed or engineer-set

Renderer supports **STRAIGHT / ZEROPRESSURE / BELT / CURVE / UNKNOWN**. Curves are arcs (not rotated rectangles). Site zoom labels are primarily **P-tags**. Motors / PE / Area / ES Zone stay in inspector / selection / prepared layers. Confirmed mates render as coinciding endpoints with **▶◀** (no Bezier). Unknown topology stays disconnected — overlap alone never creates a connection.

Layers prepared: Physical (full), Motors, Photoeyes, Area, Safety, Controller, Tracking (stubs).

#### Visual layout acceptance

| Criterion | Status |
|-----------|--------|
| Pre-fix Node-RED cards | **FAIL** (Curtis) |
| Compact-segment interim | **FAIL** (Curtis: still scattered labeled objects) |
| Schematic renderer implemented | **YES** |
| Browser / print recognition | **CURTIS ACCEPTANCE REQUIRED** |

**Do not mark this visual gate PASS automatically.**

Success means Curtis can look at Site Forge beside the Greensboro conveyor print and recognize major runs, curves, and relative arrangement — not CAD-perfect, but physically recognizable.

### 6. Library provenance: **PASS**

Confirmed use of OReilly_Library_v3.L5X, IO_MAP_Program.L5X, Sys_Program.L5X, System_Program.L5X, Slow_Flt_AOI.L5X under `tools/libraries/`. **No logic copied from finished Greensboro CP2 PLC into generation.**

### 7. Generate + backtest: **OK**

Workflow: `fortna_workbook.py build --merge-existing` → `fortna_autogen.py from-run` → `fortna_l5x_compare.py`. Category scores live in `exports/cp2-gate/comparison_summary.json`. Accuracy gaps are truthful baseline — not repaired by this gate.

## Orchestrator

```
python tools/scripts/fortna_cp2_completion_gate.py \
  --run-dir workspace/active/RUN --machine ORNCCP2 --out exports/cp2-gate
```
