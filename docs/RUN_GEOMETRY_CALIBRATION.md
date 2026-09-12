# RUN Geometry Calibration — Greensboro

**Status:** Binding for physical schematic rendering  
**Version:** `greensboro-infeed-v1`  
**Date:** 2026-09-12  
**Scope:** Conveyor.asc geometry for Site Forge Transport Build  
**Finished PLC:** not used

---

## Selected transform

| RUN field | Meaning | Confidence |
|-----------|---------|------------|
| `X_cord`, `Y_cord` | **Infeed / ENTRY end** of the conveyor body (not footprint center) | **HIGH** |
| `Angle` | Flow direction at infeed, degrees **CCW from +X** | **HIGH** (non-curve) |
| `Length` | Full centerline body length from infeed along Angle | **HIGH** |
| `Width` | Cross-belt / frame width | **HIGH** |
| `Type` | `STRAIGHT` / `ZEROPRESSURE` / `BELT` / `CURVE` / … | **HIGH** |
| `Length = -1` on `CURVE` | Sentinel — do not use as body length | **HIGH** |
| `Inside_Radius` | Inner radius of curve | **HIGH** |
| `Infeed_Tangent`, `Discharge_Tangent` | Tangent **stub lengths** (drawing units), not topology FKs | **HIGH** |
| Curve sweep | Default **90°** when not otherwise encoded | **MEDIUM** |
| Curve turn (CW/CCW) | Prefer turn whose exit mates a neighbor entry; else CW | **MEDIUM** |
| Centerline radius | `Inside_Radius + Width/2` | **MEDIUM** |

### Linear body

```
entry = (X_cord, Y_cord)
exit  = entry + Length · (cos(Angle°), sin(Angle°))
```

### Curve body

```
p1   = entry + Infeed_Tangent · û(Angle)
R    = Inside_Radius + Width/2
arc  = 90° CW or CCW about center offset R from p1 along turn normal
p2   = end of arc
exit = p2 + Discharge_Tangent · û(Angle_out)
```

Screen canvas applies a uniform scale and **Y flip**; source RUN values are never mutated.

---

## Hypotheses rejected

| Hypothesis | Result |
|------------|--------|
| XY = footprint center; entry/exit = center ± Length/2 | **REJECTED** — true abutments showed 250–750u gaps; infeed model yields **0** |
| XY = discharge / exit end | **REJECTED** for straights (P312→P314 gap doubles) |
| Tangents are topology foreign keys | **REJECTED** — local geometry only |
| Tangents are absolute bearings | **REJECTED** — equal InT/OutT on turning curves |

---

## Validation (RUN-internal only)

Exact exit→entry distance **0** under infeed model:

- P312 → P314
- P320 → P322
- P136 → P138
- P102 exit = P104 (curve) XY
- P126 (CW curve) → P128 (plant-wide)

After enabling curve IR/tangent geometry on ORNCCP2 Autogen-scoped set: **all 37** conveyors have exit anchors; confirmed geometric mates rose from **1 → 7** (plus 2 high-confidence).

Engineering prints may be used **only after** this hypothesis for visual confirmation — never to invent topology or copy finished-PLC downstream.

---

## Prior incorrect model impact

Auto Build previously placed Node-RED cards / compact segments about a **false center**, so long runs looked short/misaligned and curves (`Length=-1`) had no body. That is the root cause of Curtis’s “scattered labeled objects” FAIL — not missing RUN coordinates.

Implementation: `tools/scripts/fortna_physical_geometry.py`  
Consumers: geometry investigate, physical layout Auto Build, Transport schematic renderer.

---

## Pass 2 additions (display only)

| Rule | Confidence | Notes |
|------|------------|-------|
| Field `b` as exit-bearing candidate | **MEDIUM** | Mate-scored against default 90°; never blind-bound (`curve_validation.md`) |
| Display-context neighbors | **HIGH** | Geometrically mated / arc-cluster segments complete hairpins on canvas; `displayContext=true` excluded from Apply |
| Hairpin / “spiral” print look | **HIGH** | Multiple CURVE + STRAIGHT/ZP assemblies (e.g. P126–P134, P142–P148); large P600/P700 curve bank is a separate multi-CURVE assembly, not a synthetic spiral glyph |
| SAME_PHYSICAL_ASSEMBLY | **HIGH** | Shared entry (P134/P136A, P148/P150A) — do not lane-separate |

Architecture remains:

```
RUN RAW GEOMETRY → PHYSICAL GEOMETRY INTERPRETER → DISPLAY GEOMETRY
```

Raw RUN coordinates are never mutated for prettier screens.
