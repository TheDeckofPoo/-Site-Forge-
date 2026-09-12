# Transport Physical Layout Pass 2 — Before / After

**Branch:** `feature/transport-physical-layout-pass2`  
**Parent:** `feature/transport-physical-drawing`  
**Scope:** Presentation / Auto Build physical layout only — no PLC generation changes

---

## Acceptance question

Can a controls engineer look at Site Forge and the engineering print and recognize the same conveyor arrangement (runs, curves, merges, spacing)?

Not: are the pixels identical?

Curtis will supply the PLC2 print screenshot at review. Repo electrical `CP2.pdf` pages are **not** the mechanical layout reference. The site layout PDF was contrast-enhanced for research but is faint; human screenshot remains authoritative for acceptance.

---

## What was wrong (BEFORE)

1. **Canvas clutter** — Area/ES text painted on every conveyor (fixed in drawing pass; kept clean here).
2. **Incomplete physical assemblies** — Autogen ownership placed only **35** CP2 conveyors. Intermediate CURVE/STRAIGHT segments of hairpin U-turns were omitted (`P128/P130/P132`, `P144/P145/P146`), so curves looked like disconnected stubs piled on long ZP runs (`P136A`, `P150A`).
3. **Overlap treated as spacing** — Blind lane offsets shoved connected/serial and same-assembly equipment apart.
4. **Curves** — Arc paths existed but stroke/context made hairpins unrecognizable without their middle segments.

Evidence snapshot: `cp2_schematic_before_pass2.svg` (35-node Autogen-only graph from Pass 1 drawing tip).

---

## What changed (AFTER)

### Display-context expansion (presentation only)

Auto Build still **owns** the same Autogen PLC set (**35**), but now also places geometrically mated **display_context** neighbors so physical runs/hairpins are complete on the canvas.

| Metric (ORNCCP2) | Before | After |
|------------------|--------|-------|
| Nodes placed | 35 | **65** (35 owned + 30 display_context) |
| Hairpin P126…P134 complete? | No (missing P128/P130/P132) | **Yes** |
| Hairpin P142…P148 complete? | No (missing P144/P145/P146) | **Yes** |
| Apply / workbook includes display_context? | n/a | **No** (filtered in `buildCanonicalApplyGraph`) |

Display-context bodies render with dashed stroke (`tb-display-context`) so engineers can see continuity without confusing PLC ownership.

### Overlap classes (no generic shove)

`CONNECTED_SERIAL` · `CURVE_ASSEMBLY` · `SAME_PHYSICAL_ASSEMBLY` · `PARALLEL_CONVEYOR` · `DIFFERENT_LAYER` · `VALID_PHYSICAL_OVERLAP` · `UNKNOWN`

Only **parallel** stacks get presentation lane separation (`display_dx/dy/lane/reason`). Serial / curve / same-assembly stay joined.

### Curves

Still true SVG arcs from `Inside_Radius` + tangents; field `b` remains mate-scored hypothesis (see `curve_validation.md`).

### Physical runs

`physical_runs.json` — endpoint+heading runs for the placed set (**18** runs). Not PLC topology.

---

## Spiral / circular region — RUN truth

From `spiral_area_analysis.json` (plant-wide mechanical Conveyor.asc):

### A) CP2 dense hairpins (what Auto Build must show for ORNCCP2)

Composition: **curve + straight/ZP tangent assemblies** (not a spiral glyph).

| Assembly | Core curves | Completing segments (often display_context) |
|----------|-------------|-----------------------------------------------|
| West hairpin | P126, P130, P134 | P128, P132 + shared-entry ZP P136A |
| East hairpin | P142, P145, P148 | P144, P146 + shared-entry ZP P150A |

Shared entry of P134 with P136A (and P148 with P150A) is **SAME_PHYSICAL_ASSEMBLY** evidence — do not lane-separate them.

### B) Large site spiral / curve bank (P600 / P700 family)

Best plant-wide candidate: **19 CURVE + adjacent straights/ZP/BELT**, families including `P600`, `P700`, `P508`, …  
Composition: **multiple_CURVE_records** + curve_plus_straight; layers mostly `0`; not nested concentric.  
**Largely outside ORNCCP2 Autogen ownership** — appears when the owning controller/RUN scope includes those tags. Pass2 does **not** invent a spiral symbol; it renders those CURVE records with the same generic arc rules when present.

Confidence: **HIGH** that the print’s circular look is assembled from multiple CURVE (+ tangent) records, not a special Type.

---

## Evidence files

| File | Role |
|------|------|
| `cp2_schematic_before_pass2.svg` | Before (Autogen-only) |
| `cp2_schematic_after_pass2.svg` | After (owned + display_context) |
| `cp4_schematic_after_pass2.svg` | CP4 smoke — must not break |
| `spiral_area_analysis.json` | Circular/spiral RUN mapping |
| `physical_runs.json` | Display runs |
| `curve_validation.json` | Curve field interpretations |
| `overlap_clusters.json` | Overlap research |
| `drawing_pass_proof.md` | Firewall notes (prior) |

---

## Data safety

Unchanged by design:

- raw RUN coordinates
- Autogen ownership set used for PLC Apply
- engineer topology / Area / ES / PE when applying
- generated L5X inputs

`displayContext` nodes are excluded from canonical Apply.
