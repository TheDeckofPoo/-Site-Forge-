# FortnaPlus Knowledge Layer — Report

**Branch:** `feature/fortnaplus-knowledge-layer`  
**Base:** `feature/run-driven-workspace`  
**Finished PLC4:** not used

---

## Acceptance gate

| Metric | Result |
|--------|--------|
| Training docs inventoried | **97–101** (corpus under `docs/training/`) |
| Critical/high deeply analyzed | **CRITICAL 7 + HIGH 15** (18 reviewed deep skims) |
| RUN tables documented | **30–40** in `tools/knowledge/fortnaplus_tables.json` |
| Relationships modeled | **101+** key / **156–804** graph edges (catalog vs expanded) |
| Active/stale classification improved | Cross-table scoring (Mtrchain, Jam/Full, Saw*, Sorter, I/O, StartStop) |
| PE semantic roles supported | full / jam / fulljam / detection / reserve / scan_trigger |
| Motor chain semantics supported | Mtrchain + Jamzone latch link (HIGH) |
| Operational zone types supported | Engineering Area, Start/Stop, E-Stop, Jam, Full/Jam, Sorter/Tracking (modeled) |
| Sawtooth model improvements | HSSaw* + classic Saw* documented; reservation/full-eye semantics linked to Fullline |
| Sorter discovered | Yes (entities, encoders, zones, WCS topics) |
| Sorter understood / modeled | Yes (`SORTER_CONTROL_MODEL.md`) |
| Sorter generatable | **0** full PLC path |
| Sorter still unsupported | Track/WCS/divert gold-pack generation |
| PASIM blind validation | **PASS** (incomplete tar fails closed; no Greensboro invent) |
| CP2 / CP4 / leakage | **PASS** |

---

## Biggest gaps

| Gap | Notes |
|-----|--------|
| Biggest remaining undocumented table | Site-specific PROJECT/* simulation tables; many LOW-relevance FPC modules not deep-modeled |
| Biggest remaining Sorter gap | No complete **generic** Rockwell sorter/tracking library path (gold packs ≠ generatable) |
| Biggest remaining Sawtooth gap | Pack full-eye slot vs ReserveTM upstream eye (F1/F2 / EZPE217) still engineer-confirm for AOI wiring |

---

## Product rule preserved

Site Forge does 80–95% of data entry from RUN + documented FortnaPlus semantics.  
Engineer fixes the uncertain 5–20%.  
**Never guess** that remainder.  

Workflow: Import RUN → Discover → Review/Correct → Build PLC.
