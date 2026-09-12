# RUN Auto-Build Audit (evidence only)

Generated: `2026-09-12T04:15:00.466133+00:00`

## Source-of-truth firewall

This audit uses **RUN tables only**. The finished Greensboro L5X was **not** read.
See `docs/SOURCE_OF_TRUTH_POLICY.md`.

## Why Auto Build reported ~37 / 3 / 20 / 31 / 0

- **Conveyors discovered/placed = 37**: plant-wide mechanical P-tags ≈ **284**, but Auto Build only imports controller-scoped belts (same Autogen IO-link rule). Rejected ≈ **448** (see rejection_reason_counts).
- **Auto connections ≈ 3**: only CONFIRMED + HIGH-CONFIDENCE geometric exit→entry mates are wired.
- **Ambiguous ≈ 20**: spatially near but multi-candidate / weak angle / outside high band — flagged, not auto-wired.
- **Disconnected ≈ many**: conveyors with no HIGH/CONFIRMED outbound or inbound wire.
- **Merges = 0**: geometric merge requires ≥2 auto-inbound mates; merge ASC hints are not yet applied as topology.
- **Motors linked ≈ 207 / VFD = 32**: Mtrchain supplies links; controller-scoped VFD* rows = **0**; M### contactor label is a **name heuristic** when Drive field empty.

## Conveyor inventory

| Bucket | Count |
|---|---:|
| All mechanical P-tags (unique) | 284 |
| Controller-scoped (imported) | 37 |
| Rejected | 448 |

Rejection reasons:

- `missing_io_link_to_controller`: 247
- `non_p_tag_mechanical_row`: 201

## Geometry assumption

**Status: ASSUMPTION** — X/Y = footprint center; Angle = flow direction deg CCW from +X; entry/exit = center ± Length/2 along angle

Evidence:

- Conveyor.asc provides X_cord, Y_cord, Angle, Length, Width numeric fields.
- Conveyor.asc does NOT document whether X/Y is center, infeed corner, or discharge.
- Infeed_Tangent / Discharge_Tangent / NoseOver exist but are not used by Auto Build today.
- No RUN field named entry_anchor/exit_anchor — anchors are INFERRED_GEOMETRY.

## Connections

Candidates: **23** (auto 3, ambiguous 20)

See `connection_evidence.json` for per-candidate distance/angle/type/confidence/reason.

## Motors / drives

Mtrchain.asc maps Motor_Name → Motor_Chained1..N. Chained entries are often P### conveyors (and sometimes PE tags). This is a Fortna motor-chain / latch control relationship, not proven physical ownership of a single drive for every chained conveyor. A motor listing two P-tags (e.g. M114→P114,P112) may be a control chain / accum group rather than one physical motor driving both belts.

Conveyor.asc contains 66 IO_Name VFD* rows plant-wide. For controller ORNCCP2, belongs_to_controller matched 0 VFD rows. If zero, Auto Build reporting VFD=0 for this controller is consistent with RUN scoping — VFDs may live on other masters (e.g. ORNCCP4/ORNCCP5) or only as print/OCR artifacts, not as this controller's Conveyor.asc VFD rows.

Auto Build currently labels M### as CONTACTOR/MOTOR STARTER when the name is not VFD*. The Drive column on sampled mechanical/motor rows is often empty. Therefore contactor classification is a NAME HEURISTIC (provenance DEFAULT/GENERIC_PATTERN), not a RUN Drive-field confirmation. Prefer UNKNOWN when Drive is empty if stricter policy is required later.

## Merges

Auto Build currently detects merges only from geometric inbound count (≥2 HIGH/CONFIRMED exit→entry mates to same discharge). Merge ASC hints are exported for audit but not yet consumed to create asMerge. With few auto-connections and many AMBIGUOUS mates, geometric merge count stays 0.

See `merge_evidence.json` for table contents.

## Artifacts

- `conveyor_inventory_audit.json`
- `connection_evidence.json`
- `motor_drive_audit.json`
- `merge_evidence.json`

No Auto Build algorithm changes in this pass.
