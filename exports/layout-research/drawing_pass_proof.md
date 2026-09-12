# Physical drawing pass — generation firewall proof

**Date:** 2026-09-12  
**Branch:** `feature/transport-physical-drawing`

## Claim

This pass changes **presentation only**. It does not change:

- raw RUN coordinates
- workbook topology / engineer downstream
- generated L5X inputs (canonical Apply excludes display fields)

## Proofs run

| Check | Result |
|-------|--------|
| `test_source_truth_no_leakage.py` | PASS — Auto Build digest identical with/without finished L5X |
| `test_cp4_discovery_no_leakage.py` | PASS |
| `test_cp4_compiler_pass2.py` | PASS — 76/76 preserved |
| `test_auto_build_physical_layout.py` | PASS — 35 placed |
| `test_transport_physical_drawing.py` | PASS |
| `buildCanonicalApplyGraph` excludes `display_*` / `pathCanvas` / `sourceX` | PASS (static) |
| `computePresentationOffsets` does not assign `sourceX/Y` / `pathCanvas` | PASS (static) |

## CP2 graph fingerprint (topology + raw source XY/angle)

```
sha256[:16] = 596e5a269eb615ad
nodes = 35
```

(Recomputed from `exports/run-geometry/auto-build/transport_graph_from_run.json` after drawing-pass rebuild.)

## Visual evidence (SVG exports)

| File | Content |
|------|---------|
| `cp2_schematic_after.svg` | Full CP2 Autogen-scoped schematic |
| `cp2_dense_after.svg` | Dense region crop |
| `cp2_curves_after.svg` | Representative curves (arc paths) |
| `cp2_straights_after.svg` | Representative straights |
| `cp4_schematic_after.svg` | CP4 smoke (renderer does not break) |

Human conveyor-print screenshot remains the acceptance reference when provided — not generation input.

## Curve field `b`

See `curve_validation.md`. Hybrid mate-scored interpretation enabled in `fortna_physical_geometry.py` (MEDIUM confidence). Blind binding of `b` alone is **not** recommended.
