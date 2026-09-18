# FortnaPlus Transport Coordinate Semantics — GATE 2

**Branch:** `feature/plc2-transport-fidelity`  
**Generated:** 2026-09-18  
**Calibration:** `greensboro-infeed-v1`  
**Scope:** Conveyor.asc physical geometry for Site Forge Transport Build (RUN/Physical mode)  
**CP1–CP4:** unchanged

---

## Semantic conclusion

| Topic | Conclusion | Confidence |
|-------|------------|------------|
| Field spellings | `X_cord` / `Y_cord` (NOT `X_coord`) | **PROVEN** (ASC header, mnu-schema, fortnaplus_tables) |
| X/Y meaning | **Infeed / ENTRY end** of the conveyor body — not footprint center, not discharge, not upper-left of AABB | **HIGH / PROVEN** |
| Angle | Flow direction at infeed, degrees **CCW from +X** | **HIGH** (non-curve) |
| Axis direction | RUN +X right, +Y “up” on plant prints; canvas applies **Y invert** | **PROVEN** in layout normalizer |
| Length | Full centerline body length from infeed along Angle | **HIGH** |
| Width | Cross-belt / frame width (drawing units) | **HIGH** |
| Inside_Radius | Inner radius of CURVE; Length=`-1` is sentinel on CURVE | **HIGH** |
| Infeed_Tangent / Discharge_Tangent | Tangent stub lengths (drawing units), not topology FKs | **HIGH** |
| Canvas transform sufficiency | `canvas = uniform_scale * RUN_XY + global_translation` **+ proven Y invert** is sufficient for RUN/Physical | **PROVEN** |
| Per-object scatter / laneSeparate / topology beautification | Must **not** be default in RUN/Physical — destroys proven relative XY | **PROVEN** (Gate 2 root cause) |

Binding references:

- [`docs/RUN_GEOMETRY_CALIBRATION.md`](../RUN_GEOMETRY_CALIBRATION.md)
- [`docs/LEGACY_LAYOUT_DATA_RESEARCH.md`](../LEGACY_LAYOUT_DATA_RESEARCH.md)
- [`docs/evidence/FORTNAPLUS_PARTS_MODEL.md`](FORTNAPLUS_PARTS_MODEL.md)
- Implementation: `tools/scripts/fortna_physical_geometry.py`, `fortna_geometry_authority.py`, `fortna_run_physical_layout.py`

---

## Evidence trace order

1. `fortna.mnu` / `project.mnu` / `artifacts/mnu-schema.json` / `tools/knowledge/fortnaplus_tables.json` — Parts_Menu → Conveyor; fields include `X_cord`, `Y_cord`, `Length`, `Width`, `Angle`, `Inside_Radius`.
2. `Conveyor.asc` schema header via `fortna_asc` — delimiter `~`; spelling confirmed `X_cord`/`Y_cord`.
3. Calibration + legacy layout research + Parts model (above) — infeed-origin model accepted; footprint-center rejected.
4. Geometry scripts — interpreter + authority + canvas normalizer.
5. Prior CP typed / stabilization artifacts (`exports/stabilization/transport_geometry_authority.json`) — consistent with infeed model.
6. PLC5 RUN `workspace/cp5-run/RUN/FORTNA/Conveyor.asc` — P500 cluster + curve neighbors.

---

## Linear / curve body model

### Linear

```
entry = (X_cord, Y_cord)
exit  = entry + Length · (cos(Angle°), sin(Angle°))
```

### Curve

```
p1   = entry + Infeed_Tangent · û(Angle)
R    = Inside_Radius + Width/2
arc  = 90° CW or CCW (mate-preferred; else CW)
exit = end_of_arc + Discharge_Tangent · û(Angle_out)
```

Raw RUN coordinates are never mutated for prettier screens.

---

## Y invert proof

`fortna_run_physical_layout._normalize_canvas`:

```
cx = pad + (x - min_x) * scale
cy = pad + (max_y - y) * scale
```

Comment in source: “Flip Y for screen coords (RUN Y often increases up on prints)”.

Authority `normalize_system(..., flip_y=True)` mirrors the same relative relationship: after uniform scale + Y flip, relative `dx' = scale·dx` and `dy' = −scale·dy`.

---

## Acceptance cluster (PLC5 RUN)

Source: `workspace/cp5-run/RUN/FORTNA/Conveyor.asc`

| Tag | Type | X_cord | Y_cord | Angle | Length | Width | Inside_Radius |
|-----|------|--------|--------|-------|--------|-------|---------------|
| P500 | STRAIGHT | 42166.667 | 56000.000 | 270 | 1200 | 500 | 0 |
| P534 | BELT | 43216.666 | 53958.334 | 90 | 2800 | 200 | 7.5 |
| P536 | ZEROPRESSURE | 43216.667 | 56758.334 | 90 | 4300 | 200 | 0 |
| P542 | ZEROPRESSURE | 42316.667 | 61058.333 | 270 | 3858.333 | 200 | 0 |
| P544 | BELT | 42316.666 | 57200.000 | 270 | 1200 | 200 | 0 |

Curve-connected neighbors in the same bbox: **P502**, **P532**, **P538**, **P540**.

### Source relative deltas (from P500)

| Tag | dx | dy |
|-----|----|----|
| P500 | 0.000 | 0.000 |
| P534 | 1049.999 | −2041.666 |
| P536 | 1050.000 | 758.334 |
| P542 | 150.000 | 5058.333 |
| P544 | 149.999 | 1200.000 |

### Infeed-model exit→entry gaps

| Pair | Gap (drawing units) |
|------|---------------------|
| P534 → P536 | **0.001** (abutment) |
| P542 → P544 | **0.001** (abutment) |
| P544 → P500 | 149.999 |

### After normalize `scale=0.05`, `translate=(100,100)`, `flip_y=True`

Relative deltas survive: `dx' = 0.05·dx`, `dy' = −0.05·dy` (Y invert). Source fields untouched.

---

## Root cause when relative XY was distorted

**Classification:** Presentation lane-separation applied **by default** in Transport Build.

| Factor | Detail |
|--------|--------|
| Default | `laneSeparate: true` + HTML checkbox `checked` |
| Mode | Even with `geometryAuthorityMode: 'run'` (RUN/Physical) |
| Mechanism | `computePresentationOffsets` applied PARALLEL_LANE_SEPARATION (88px), CLUSTER_SPREAD, merge fans, CONNECTED_RUN_MATE nudges **per object** |
| Frozen reuse bug | Non-zero `display_dx/dy` could be reused before the `!laneSeparate` early-return |
| Effect | Proven relative ratios destroyed on canvas (example: P534 raw canvas Δx 52.5 → 316.5 after fake 88px lane fan) |
| Not the cause | Missing RUN coordinates; infeed vs center model (already fixed under greensboro-infeed-v1) |

Site-specific `if name==P500` production branches: **none** (tests lock this).

---

## Geometry code changed?

**YES** — generic presentation transform defaults / RUN-fidelity gate only. No CP1–CP4 changes. No site-specific tag branches.

| File | Change |
|------|--------|
| `dashboard/transport-build.js` | Default `laneSeparate: false`; RUN/Physical zeros presentation offsets before frozen reuse; `getDisplayTransform` ignores offsets when laneSeparate OFF; mode switch to run clears scatter |
| `dashboard/index.html` | Lane-separate checkbox unchecked by default; title clarifies opt-in |
| `dashboard/transport-build-pass2.js` | Status text clarifies OFF preserves relative XY |
| `tools/scripts/test_fortna_geometry_authority.py` | Extended permanent tests for PLC5 cluster deltas, Y invert, UI default |

Physical interpreter (`fortna_physical_geometry.py`) and authority math (`normalize_system`) unchanged — already correct.

---

## Default engineering view contract (RUN/Physical)

```
RUN RAW GEOMETRY
  → PHYSICAL GEOMETRY INTERPRETER (infeed model)
  → CANVAS = uniform_scale * RUN_XY + global_translation + Y_invert
  → DISPLAY (laneSeparate OFF): identity presentation offsets
```

Opt-in Advanced “Separate stacked labels/bodies” may apply presentation offsets; it must never be silent default when proven XY exists.

---

## Permanent test

```
python tools/scripts/test_fortna_geometry_authority.py
```

Covers schema spelling, relative delta survival under normalize + Y invert (PLC5 P500 cluster), abutment gaps, UI default `laneSeparate: false`, no `if name==P500` production branches.

Machine-readable twin: [`exports/stabilization/fortnaplus_transport_coordinate_semantics.json`](../../exports/stabilization/fortnaplus_transport_coordinate_semantics.json)
