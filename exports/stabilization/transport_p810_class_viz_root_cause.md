# P810-class viz root cause — false physical join (Gate 4)

**Scope:** Cosmetic / visualization only. No I/O resolver rewrite. No P810 / ORINDYAC6 special-cases.  
**Acceptance example:** PLC2 RUN cluster around `P810` (vertical discharges `P808A/B/C` above horizontal belt `P810`).  
**Date:** 2026-09-18

---

## Symptom

Vertical discharge branches appear **connected into** a lower horizontal conveyor: the painted schematic reads as if `P808*` discharges onto `P810`, even though there is no proven physical mate.

---

## Evidence (generic class, P810 as example)

| Tag | Role | Canvas note |
|-----|------|-------------|
| `P808A/B/C` | Vertical belt discharges (angle 270°) | Exit tips sit ~4.2–4.7 canvas units above `P810` body |
| `P810` | Long horizontal belt (angle 0°) | Spans under all three tips |
| Wires | No `physical:true` wire `P808* → P810` | Only `ambiguousInbound` candidates |
| `P810 → P814` | `physical:false`, `confidence:PROVEN_CROSS_TABLE`, `provenance:mtrchain_timer` | Logical/control topology, not geometry mate |

Schematic stroke width is 12–22 px. Combined half-strokes (~12–22) **exceed** the ~4.4 unit centerline gap, so thick body paint merges into a false join even with zero drawn wire between them.

---

## Root cause (classified)

1. **RUN XY proximity without proven physical connection**  
   Discharge exits and the lower belt share plant coordinates that project nearly coincident on canvas. That is geometry coincidence, not a mate.

2. **Paint-merge of schematic strokes**  
   Body strokes are intentionally thick for readability. Near-miss tips paint as if continuous.

3. **Logical/control topology drawn like connectivity**  
   Mtrchain / merge proven edges are real topology but **not** physical EXIT▶◀ENTRY geometry. Painting them (or treating proximity as `CONNECTED_SERIAL`) implied a physical belt join.

### Connection class taxonomy (rendered)

| Class | Meaning | May paint physical join? |
|-------|---------|--------------------------|
| `PHYSICAL_GEOMETRY` | Confirmed/high-confidence physical mate | Yes |
| `PROVEN_TOPOLOGY` | Proven logical/control (mtrchain, merge, …) | **No** — topology helper only |
| `DERIVED_TOPOLOGY` | Derived / auto logical edge | **No** |
| `VISUAL_HELPER` | Temp rubber-band / helper | No |
| `UNKNOWN` | Unclassified | No physical join |

### Authority priority (physical-looking join)

`ENGINEER_OVERRIDE` > `PROVEN_RUN_GEOMETRY` > `PROVEN_PHYSICAL_RELATIONSHIP` > `DERIVED_TOPOLOGY` > `FALLBACK`

---

## Fix (viz only)

Implemented in `dashboard/transport-build.js` (+ CSS cues in `index.html`):

1. **`classifyRenderedConnection` / `mayDrawPhysicalJoin`** — wires classified; only `PHYSICAL_GEOMETRY` (or engineer override) may draw physical stubs / mate marks.
2. **Logical wires** — `PROVEN_TOPOLOGY` / `DERIVED_TOPOLOGY` use `tb-wire-topology` helper style; never `tb-physical`.
3. **`endpointNear` alone ≠ `CONNECTED_SERIAL`** — proximity without a proven physical wire is `NEAR_MISS_UNCONNECTED`.
4. **`falseAbutmentInsets`** — presentation tip inset when bodies abut without a proven physical wire, so strokes no longer paint-merge into a fake discharge join. Does **not** invent wires or mutate RUN XY / workbook topology.

Regression: `tools/scripts/test_transport_p810_class_viz.py`

---

## Non-goals

- No I/O resolver changes  
- No site-name / tag whitelist (`P810`, `ORINDYAC6`, …)  
- No auto graph-layout rewrite of RUN XY foundation  
