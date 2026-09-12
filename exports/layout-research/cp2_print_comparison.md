# CP2 Print Visual Comparison

**Print role:** HUMAN VISUAL VALIDATION ONLY  
**Engineering source:** Current ORNCCP2 RUN (not the print)  
**Site Forge evidence:** Pass2 + acceptance fix (`cp2_schematic_after_acceptance.svg`)  
**Print file:** `exports/layout-research/cp2_print_reference.png` (Curtis attachment, red box)

---

## Overall verdict

**RECOGNIZABLE_BUT_IMPERFECT** — demo-usable for CP2 Autogen scope.

Major Autogen-owned paths (hairpins, straights, parallels, curves) are recognizable.  
The red-boxed concentric spiral on the print maps to the plant **P600/P700 curve bank**. That bank was initially **absent** from the ORNCCP2 Autogen graph (0/76). A **generic** same-IO-word dense CURVE-bank display-context expansion now places those records as `displayContext` (PLC ownership unchanged: still 35 owned).

| Region | Classification |
|--------|----------------|
| Red-box spiral / curve bank | Was `MISSING_EQUIPMENT` → after generic fix: **RECOGNIZABLE_BUT_IMPERFECT** |
| West hairpin P126–P134 | **MATCHES_WELL** |
| East hairpin P142–P148 | **MATCHES_WELL** |
| Long straight runs | **RECOGNIZABLE_BUT_IMPERFECT** |
| Parallel lanes | **RECOGNIZABLE_BUT_IMPERFECT** |
| Curve continuity (arcs) | **MATCHES_WELL** |
| Merge approaches | **UNKNOWN** (no Autogen merges_detected) |
| Labels / Area-ES clutter | **MATCHES_WELL** |

Machine-readable detail: `cp2_print_comparison.json`.

---

## Red-box spiral

**Print:** Concentric multi-loop curves with radial feeders (red rectangle).

**RUN identity (not from print coordinates):**  
Families `P600/P602/P610/P612/P700/P702/P704/P706/P708/P710/P720` (+ related). Composition = multiple CURVE records + straight/ZP tangents (`spiral_area_analysis.json`). Share `IO_Address_Word=6000` with CP2 Autogen equipment but are **not** in Autogen’s PE/VFD-linked conveyor set.

**Fix applied (generic):**  
When Autogen-owned equipment uses IO word W, dense CURVE arc-center clusters (≥5 curves, radius 5000u) on word W that are mostly outside Autogen ownership are pulled as **display_context**, plus endpoint mates. No Greensboro tag hard-coding. Apply still filters `displayContext`.

**After:** ~53 spiral-family tags / ~44 CURVE bodies appear on the CP2 canvas as dashed display-context. Spacing/framing vs print sheet remains schematic — not pixel-matched.

---

## Clear generic bugs

| Bug | Fix |
|-----|-----|
| Dense multi-CURVE banks on same IO word omitted from canvas despite being on the RUN | Same-IO-word curve-bank display-context expansion |

No site-specific exceptions. No print-derived topology.

---

## Evidence SVGs

| File | Content |
|------|---------|
| `cp2_print_reference.png` | Human print (red box) |
| `cp2_schematic_after_pass2.svg` | Before acceptance spiral fix |
| `cp2_schematic_after_acceptance.svg` | After spiral bank display-context |
| `cp2_spiral_region_after.svg` | Spiral/curve-bank crop |
| `cp2_hairpin_region_after.svg` | Hairpin crop |
