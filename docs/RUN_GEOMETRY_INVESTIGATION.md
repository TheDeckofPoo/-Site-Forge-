# RUN Geometry Investigation

Generated: `2026-09-11T21:01:54.311886+00:00`
RUN: `workspace\active\RUN`
Controller/machine scope: `ORNCCP2`

## Headline question

**Can this RUN reconstruct a useful first-pass physical layout without using the PDF?**

**Answer (USEFUL_FIRST_PASS):** YES — with caveats. Greensboro RUN Conveyor.asc provides usable X/Y/Angle/Length/Width for the controller-scoped mechanical conveyors, enough for a useful first-pass physical layout sketch and high-confidence geometric connection candidates. It is NOT sufficient alone for complete Autogen topology: area/safety zones, many finished-PLC conveyors, and reliable merge/downstream semantics still require engineer confirmation (and prints when available).

## Counts

| Metric | Count |
|---|---:|
| Conveyors discovered (mechanical P###) | 37 |
| Usable X/Y | 37 |
| Usable angle | 37 |
| Usable length/width | 29 |
| Motors discovered (Conveyor.asc MOTOR/VFD rows) | 118 |
| Motor↔conveyor links via Mtrchain | 34 |
| VFD classified (motor links) | 0 |
| Contactor/MS classified | 34 |
| Unknown/mixed drive | 3 |
| Multiple-motor conveyors | 0 |
| Motors driving multiple conveyors (Mtrchain fan-out) | 38 |
| Photoeyes scoped to controller | 44 |
| Merge table hints | 8 |
| Connection candidates (total geometric) | 23 |
| CONFIRMED connections | 1 |
| HIGH-CONFIDENCE CANDIDATE | 2 |
| AMBIGUOUS connections | 20 |
| Conveyors without strong outbound geometric link (approx unknown) | 34 |

## Fields recovered from Conveyor.asc

Present and used:

- `IO_Name` (P-tag)
- `X_cord`, `Y_cord`, `Width`, `Length`, `Angle`
- `Type` (STRAIGHT / CURVE / TRIANG / BELT / …)
- `Part_Number`, `Device_Description`, `IO_Module_Type`
- `Electrical Drawing Page No.`
- `Infeed_Elevation`, `Discharge_Elevation`
- `In Motor Chain`
- `IO_Address_Word` / bit (controller scoping)

Present but weak/empty on this controller sample:

- `Motor` column on mechanical rows (empty — association comes from **Mtrchain.asc**)
- `Drive` column (empty on sampled ORNCCP2 mechanical rows)

## Related RUN evidence

### Motors / drives

- `Mtrchain.asc`: `Motor_Name` → `Motor_Chained1..N` (often P###). Supports **multiple conveyors per motor chain** and inverse multi-motor lookup.
- VFD vs contactor: primarily from motor tag naming (`VFD*` vs `M*`) plus optional Drive field; many VFDs may be absent as Conveyor.asc Type=MOTOR rows.
- One conveyor ≠ one motor is supported by the data model; this sample’s multi-motor conveyor count is reported above.

### Photoeyes

- PHOTOCELL rows in Conveyor.asc scoped by controller.
- Association to conveyors here is **name-based only** (e.g. PE138_P → P138) — not geometric mating.

### Merges / adjacency

- `MergeInputs.asc.<machine>` can mention lane names / presence PEs / merge boss names.
- `Merges.asc` on this RUN was largely empty/invalid placeholders.
- Geometric exit→entry matching is the primary adjacency experiment in this pass.

### Area / safety zone

- Not trustworthy from Conveyor.asc geometry fields alone for this controller.
- Remain workbook / Transport Build / engineer-defined (see Autogen area-safety fidelity work).

## Geometry model assumptions

(X,Y)=footprint center; Angle=flow direction deg CCW from +X; entry/exit at ±Length/2 along angle. CURVE/TRIANG lower confidence.

**Critical rule:** numerical P-tag order is never treated as physical adjacency.

## Connection classification

| Class | Meaning |
|---|---|
| CONFIRMED | Exit≈entry within ~0.75×min(width) (or 300u) and angle Δ≤15° |
| HIGH-CONFIDENCE CANDIDATE | Within ~2×width (or 750u) and angle Δ≤30° |
| AMBIGUOUS | Spatially close but angle mismatch, or multiple inbound candidates |
| UNKNOWN | No geometric partner under thresholds |

Sample high-confidence / confirmed (up to 15):

- `P312 → P314` CONFIRMED dist=250.0 angΔ=0.0
- `P320 → P322` HIGH-CONFIDENCE CANDIDATE dist=350.0 angΔ=0.0
- `P138 → P404` HIGH-CONFIDENCE CANDIDATE dist=690.461 angΔ=0.0

## Desired future PhysicalConveyor model (feasibility)

Feasible fields from RUN today:

```
PhysicalConveyor
  identity          ← IO_Name P###
  equipment_type    ← Type
  geometry          ← X/Y/Angle/Length/Width (+ elevations)
  entry_anchor     ← derived (assumption-based)
  exit_anchor(s)    ← derived (curves TBD)
  motors[]          ← Mtrchain (+ future Drive/VFD classification)
  photoeyes[]       ← name association now; geometry later
  connections[]     ← geometric candidates + engineer confirm
```

Physical connections should eventually be mating entry/exit anchors, not generic graph wires.

## Artifacts

- `exports\run-geometry\greensboro_equipment.json`
- `exports\run-geometry\greensboro_connection_candidates.json`
- `exports\run-geometry\ORNCCP2_equipment.csv`
- `exports\run-geometry\ORNCCP2_layout_preview.svg` (diagnostic preview only)

## Out of scope

- No Transport Build UI changes
- No Autogen changes
- No PDF parsing
- No hardcoded Greensboro production behavior
