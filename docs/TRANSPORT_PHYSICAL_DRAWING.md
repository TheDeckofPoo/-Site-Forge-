# Transport Physical Drawing Pass

**Branch:** `feature/transport-physical-drawing`  
**Parent:** `feature/site-forge-integration-checkpoint`  
**Scope:** Presentation / schematic only — no PLC generation changes

---

## Goal

Make Transport Build produce a clean, recognizable physical conveyor schematic from RUN data so an engineer can compare it to a conveyor print and recognize major runs, curves, merges, and parallel lanes.

Not CAD-perfect.

---

## Changes

### 1. Canvas labels

- Default label = **P-tag only**
- Optional secondary line (close zoom / selected): motor or VFD identity
- **Removed** Area / ES / zone text from the canvas
- Missing Area/ES → small amber warning dot only (inspector still edits Area/ES)

### 2. Progressive disclosure

Overview prioritizes conveyor body + P-tag + flow tick.  
PE / encoder / Area / ES stay in inspector (and evidence/debug), not on the default canvas.

### 3. True curve geometry

- CURVE bodies use `Inside_Radius` + tangents + SVG `A` arcs (not rectangles)
- Curve stroke scaled so arc shape stays readable at site zoom
- Field `b` treated as **hypothesis** for absolute exit bearing:
  - mate-scored against default 90° CW/CCW
  - used only when neighbor mating prefers it
  - see `exports/layout-research/curve_validation.md` (confidence **MEDIUM**, not blind)

### 4. Connected-run display assembly

- Trustworthy physical wires can nudge display endpoints to mate (`CONNECTED_RUN_MATE`)
- Does **not** invent PLC downstream

### 5. Overlap handling

Classify before shifting:

| Class | Display action |
|-------|----------------|
| `CONNECTED_SERIAL` / `CURVE_ASSEMBLY` | Keep joined (no lane shove) |
| `PARALLEL` | Perpendicular lane separation |
| Merge feeds | Fan along discharge normal |

### 6. Firewall

Never mutate:

- raw RUN coordinates
- workbook topology
- engineer-entered downstream
- generated L5X inputs

Canonical Apply still excludes `display_*`, `pathCanvas`, `sourceX/Y`.

---

## Evidence

| Artifact | Role |
|----------|------|
| `exports/layout-research/curve_validation.json` | Per-curve interpretation scores |
| `exports/layout-research/curve_validation.md` | Human summary |
| `exports/layout-research/cp2_schematic_after.svg` | CP2 full schematic export |
| `exports/layout-research/cp4_schematic_after.svg` | CP4 smoke schematic |
| `tools/scripts/fortna_schematic_svg_export.py` | SVG exporter |

Human print screenshot = acceptance reference only (not generation input).

---

## Tests

- `test_transport_physical_drawing.py`
- `test_display_layout_offsets.py`
- `test_fortna_physical_geometry.py`
- `test_auto_build_physical_layout.py`
- `test_transport_physical_presentation.py`
- `test_cp4_compiler_pass2.py` (no regression)
