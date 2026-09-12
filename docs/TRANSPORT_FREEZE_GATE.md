# Transport Freeze Gate

**Branch:** `feature/cp4-sawtooth-fidelity`  
**Baseline:** `feature/transport-physical-layout-pass2` + CP2 print acceptance fix  
**Date:** 2026-09-12

---

## Decision

# TRANSPORT_DEMO_READY

Major conveyor paths are recognizable enough for demo / engineering review against the PLC2 print.

CAD-perfect rendering is **not** required and is **not** claimed.

---

## Checklist

| Criterion | Status |
|-----------|--------|
| Major conveyor paths recognizable | **PASS** |
| Curves look like curves (SVG arcs) | **PASS** |
| Hairpins read correctly (P126–P134, P142–P148) | **PASS** |
| Circular/spiral print region recognizable | **PASS** (display-context curve bank; schematic spacing) |
| Labels readable (P-tag default) | **PASS** |
| Area/ES not cluttering canvas | **PASS** |
| No severe overlap blocking engineering use | **PASS** (classified overlaps; serial/same-assembly joined) |

Evidence: `exports/layout-research/cp2_print_comparison.md` (+ JSON), acceptance SVGs.

---

## UX rule (binding)

Complexity belongs inside Site Forge, not in front of the engineer.

Normal workflow remains:

```
Import RUN → Auto Build → Review / Correct → Apply to Autogen → Build PLC
```

**Do not** add top-level buttons for VFD / Encoder / Sawtooth / Lane Logic / Merge Validate.

---

## Remaining Transport limitations (do not polish endlessly)

1. Spiral/curve bank is **display_context** (not Autogen PLC-owned); Apply excludes it.
2. Print sheet framing/rotation/scale will not match pixels.
3. CP2 Autogen set has `merges_detected=0` — merge approach rendering not exercised there.
4. Field `b` exit-bearing remains a **MEDIUM** mate-scored hypothesis.
5. Large display-context sets increase density — use Fit Visible.
6. Multi-controller “whole site” overview is out of scope for this freeze.

---

## Freeze scope

**Frozen for major visual Transport work** unless a clear generic geometry bug appears.

Further engineering focus: **PLC4 Sawtooth fidelity** (generation), not Transport pixel polish.

Do not regress:

- cleaner canvas labels
- true curve rendering
- display-context neighbors / hairpin completion
- same-IO-word dense CURVE-bank expansion
- overlap classification
- Autogen/L5X firewall
