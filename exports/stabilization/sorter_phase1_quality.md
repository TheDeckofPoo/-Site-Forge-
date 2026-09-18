# Sorter Phase-1 Quality + Cookie-Cutter Evidence

Parent: `da5e86da9dc849b77ef376e88dacf4151d54cec5`

## Gate O — 32 SrtZoneLane vs 16 Track_Divert_UDT

| Metric | Value |
|--------|-------|
| Canonical SrtZoneLane rows | **32** |
| Unique Lane / HostZone / divert IO | **32** each |
| Unique `SrtZoneLane.Name` | **15** (14 pairs of 2 + 1 group of 4) |
| Gold pack `Track_Divert_UDT` tags | **16** |
| Phase-1 Wave_Divert rungs kept | **32** / pack 16 |

**Finding:** Name groups (e.g. `ADD-ON_2_3`) strongly suggest dual-sided destination families, but each row still has a distinct physical SSV output. Greensboro pack 16 is site cookie-cutter multiplicity, not a proven fold of ORNCCP5's 32 lane enables.

**Classification:** `UNKNOWN` — leave canonical **32** unchanged. Do not force 32→16 in Phase 1.

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
