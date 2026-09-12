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

| layout visualization (Curtis) | **FAIL** | PRE-FIX card UI FAIL (Curtis screenshot). POST-FIX compact-segment / Fit Site code **present** on this branch; browser verification **pending**. RUN geometry preserved. |

### 1. I/O inventory: **PASS**

Scoped ORNCCP2 I/O points: **243** (DI 52, DO 191, PE 44, MS out 60, OL/aux 59, control stations 21, E-stop/safety 18, VFD 0). EIP mapped 34 / unmapped 202.

### 2. Equipment completeness: **PARTIAL**

RUN conveyors expected: **37**; workbook represented: **37**; HIGH-confidence CP2: **31**; AMBIGUOUS may-belong: **13**; motors/MS 118, photoeyes 44, control stations 21, E-stops 18. Ownership confidence is flagged; equipment with missing I/O is retained.

### 3. Areas and ES zones: **FAIL**

Workbook areas: `['ORNCCP2_Area']`; ES zones: `['ORNCCP2_ESZone1']`. Engineer-config-required rows: 0. Finished PLC area names (ModuleB/ModuleC/Trash) were **not** copied into workbook input. Post-generation structural compare is in `area_safety_inventory.json`.

### 4. E-stop inventory: **PARTIAL**

CP2 E-stop/safety devices from Conveyor.asc: **44**. Affected-equipment mappings are **not invented**. Missing area/zone/reset fields marked `ENGINEER CONFIGURATION REQUIRED`.

### 5. Physical layout metrics: **FAIL**

Placed 37, unplaced 0, high-confidence connections 3, ambiguous 20, manual required 85. Geometry inventory: **PASS**. Visualization gate: **FAIL**.

#### Visual layout acceptance (Curtis Auto Build)

Curtis Auto Build screenshot acceptance is **FAIL**: equipment is placed but bunched; physical runs are not recognizable (Node-RED cards); cards/labels excessively overlap; P-tags are unreadable when overlapped; connected mates show as long bezier curves between cards; disconnected/ambiguous state is only partially obvious.

- Pre-fix card UI: **FAIL**
- Post-fix presentation code (`.tb-seg` / Fit Site): **PRESENT**
- Browser verification: PENDING

Underlying RUN geometry is preserved (not rearranged by P-number). Visualization gate reflects Curtis Auto Build FAIL. PRE-FIX FAIL / POST-FIX code present but browser verification pending.

**Presentation correction on this branch (not a geometry rewrite):** Transport Build now draws Auto-Built equipment as compact oriented segments (`.tb-seg`) with ENTRY◀ / EXIT▶ mating anchors, Fit Site / Fit Area framing, Ctrl+wheel zoom, and zoom-dependent detail. Source RUN `X/Y/Angle/Length/Width` are not modified to pass the screenshot. Curtis’s screenshot remains the authoritative **FAIL** for the pre-fix card presentation; re-verify in desktop after Auto Build From RUN before flipping the visual gate.

The screenshot from Curtis is real engineering acceptance evidence: the current Auto Build technically places equipment, but the presentation is not yet acceptable as a physical site-layout view. Treat that as a FAIL for the current CP2 layout-visualization gate, while preserving the underlying RUN geometry for investigation.

### 6. Library provenance: **PASS**

Confirmed use of OReilly_Library_v3.L5X, IO_MAP_Program.L5X, Sys_Program.L5X, System_Program.L5X, Slow_Flt_AOI.L5X under `tools/libraries/`. **No logic copied from finished Greensboro CP2 PLC into generation.**

### 7. Generate + backtest: **OK**

Workflow: `fortna_workbook.py build --merge-existing` → `fortna_autogen.py from-run` → `fortna_l5x_compare.py`. Category scores live in `exports/cp2-gate/comparison_summary.json`. Accuracy gaps are truthful baseline — not repaired by this gate.

## Orchestrator

```
python tools/scripts/fortna_cp2_completion_gate.py \
  --run-dir workspace/active/RUN --machine ORNCCP2 --out exports/cp2-gate
```
