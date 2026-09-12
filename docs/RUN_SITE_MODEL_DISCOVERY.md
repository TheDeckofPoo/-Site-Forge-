# RUN Site Model Discovery Pass 1

Generated: `2026-09-12T04:34:07.599132+00:00`
RUN: `workspace\active\RUN`

## Source-of-truth firewall

Finished PLC and prints were **not** used to populate this model.
See `docs/SOURCE_OF_TRUTH_POLICY.md`.

## Canonical model

```
SiteModel
  equipment[]      # physical conveyors — one row per P-tag, plant-wide
  devices[]        # motors / PEs / VFDs from Conveyor.asc
  relationships[]  # reserved (Convpath empty; geometry/manual later)
  controllers[]    # ownership metadata map
  areas[]          # not reliably available from RUN geometry tables
  geometry[]       # embedded on equipment with provenance
```

Controller ownership is **metadata**, not a filter that deletes equipment.

## Inventory counts

| Metric | Count |
|---|---:|
| Total unique mechanical conveyors | 284 |
| With XY | 284 |
| With angle | 284 |
| With length | 228 |
| With width | 284 |
| Controller ownership HIGH | 173 |
| Controller AMBIGUOUS | 13 |
| Controller UNKNOWN / none | 98 |

## Convpath investigation (highest priority)

NO — On this RUN, Convpath.asc does not encode ordered conveyor topology. All 1000 rows are placeholders (Piece=INVALID, Input/Output=0.000). Zero P→P edges were found. Pathsets.asc likewise has no real Pth1..Pth10 conveyor sequences. Therefore a sequence like P132→P134→P136→P138 cannot be derived from Convpath without geometry inference or engineer input.

**What Convpath appears to be:** 
A tracking / piece-path slot table (Piece + PE_at/PEname) intended for carton tracking along a path, not a static conveyor-to-conveyor downstream graph. In this archive it is unpopulated.

- Rows: 1000
- P→P edges found: **0**
- Placeholder rows: 0

Therefore a sequence such as `P132 → P134 → P136 → P138` **cannot** be derived from
Convpath on this archive without geometry inference or engineer configuration.

## Geometry

Entry/exit anchors remain **`INFERRED_GEOMETRY`** (center ± Length/2 assumption).

- `Infeed_Tangent` / `Discharge_Tangent`: present especially on CURVE/BELT; look like
  local curve geometry parameters, **not** foreign keys to adjacent conveyors.
- `NoseOver`: occasional equipment feature (`Double Noseover`), not topology.

## Controllers

Controllers observed/linked: ORNCCP2, ORNCCP4, ORNCCP5

See `controller_map.json`. Unknown ownership does **not** remove the conveyor from the site model.

## Headline question

**Can the RUN describe physical conveyor topology directly, or are we still forced to infer topology from geometry/manual engineering?**

**Answer: Still forced to infer / engineer.**

This RUN provides a strong **physical equipment + geometry inventory** (hundreds of P-tags with XY/angle/length)
and useful **control relationships** (Mtrchain, jam/full, merge boss/inputs), but it does **not** provide a
populated static conveyor successor graph (Convpath/Pathsets empty). Physical topology therefore remains:

1. `INFERRED_GEOMETRY` (exit→entry mating), and/or
2. **ENGINEER**-entered Transport Build connections,

not a direct RUN path table export.

## Artifacts

- `site_model_inventory.json`
- `controller_map.json`
- `table_relationships.json`
- `convpath_analysis.json`

No Auto Build production topology changes in this pass.
