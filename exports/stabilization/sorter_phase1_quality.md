# Sorter Phase-1 Quality + Cookie-Cutter Evidence

Parent: `da5e86da9dc849b77ef376e88dacf4151d54cec5`

## Gate O — 32 DestinationLanes vs 16 PhysicalDiverts / Track_Divert_UDT

| Metric | Value |
|--------|-------|
| Canonical SrtZoneLane rows (DestinationLane) | **32** |
| Unique Lane / HostZone / divert IO | **32** each |
| Unique `FullClearTimer` (PhysicalDivert key) | **16** (all size 2) |
| Unique SSV families | **16** (all size 2) |
| Unique `SrtZoneLane.Name` | **15** (14 pairs of 2 + 1 group of 4) |
| Gold pack `Track_Divert_UDT` tags (validation) | **16** |
| Phase-1 Wave_Divert rungs kept | **32** / pack 16 |

**Finding:** Shared `FullClearTimer` (+ corroborating SSV family / consecutive HostZones) maps 32 DestinationLanes → 16 PhysicalDivert mechanisms. `SrtZoneLane.Name` alone is insufficient (`NEW_510` has 4). Each DestinationLane still has a distinct SSV output. Finished oracle 16 validates after RUN discovery — not a discovery input. Do **not** hardcode `physical_diverts = lanes/2`.

**Classification:** `STRONGLY_SUPPORTED` — leave DestinationLane multiplicity **32** unchanged. Do not force 32→16 emit until library/schema elevates grouping to PROVEN.

See `docs/evidence/SORTER_LANE_PHYSICAL_DIVERT_MODEL.md` · `plc5_lane_divert_relationship.json` · `plc5_divert_confirm_pe_audit.json`.

## Structural classifications (Gate U)

See `sorter_phase1_quality.json` for full routine/tag/AOI/UDT table.

Highlights:

- **STANDARD_PROVEN:** Sorter_Track shell, Main JSR set, Track_*/Wave_Divert/Divert_* routines, Track_Divert_AOI/UDT types
- **MODEL_EXPANDED:** Wave_Divert & encoder/tracking multiplicity from RUN model; Build_Config
- **SITE_CONFIGURATION:** Module CommLoss bindings, scanner aliases, area program split
- **COMMISSIONING / ENGINEER_REQUIRED:** global tracking_offset, sorter_type, divert_pe when Verify I/O INVALID
- **CUSTOM / EXTERNAL:** WCS interface (not emitted)

## Cookie-cutter policy (Gate V)

Do not encode CUSTOM/UNKNOWN as mandatory pack logic.
Repeated architecture across PLC4/PLC5 is supporting evidence only — still require Fortna/RUN/library support before claiming universal STANDARD_PROVEN.
