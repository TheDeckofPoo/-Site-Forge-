# Sorter Evidence Inventory (Gates H / I)

**Branch:** `feature/plc2-transport-fidelity`  
**Scope:** Archaeology / discovery only — no Sorter PLC generation; CP1–CP4 not modified.  
**Firewall:** Finished PLC L5X and Greensboro gold packs are **validation oracles only**.

Primary tooling: `tools/scripts/fortna_sorter_discovery.py`, `tools/knowledge/fortnaplus_tables.json`.

---

## Cross-site snapshot

| Site | Active Sorters | Notes |
|------|---------------:|-------|
| ORNCCP2 | **0** | Overlay empty; schemas + WCS present |
| ORNCCP4 | **2** | `SAWTOOTH_MERGE`, `CITY_LANE` — divert IO still incomplete |
| ORNCCP5 | **5** | Ship sorters; motor sometimes RUN-explicit (`VFD504_EN`) |

## Identity / type

| Fact | Primary | Class |
|------|---------|-------|
| Existence | `Sorters.Sorter Name` (active) | STATIC / PROVEN when present |
| Identity | `Sorters` + `Machine` | STATIC |
| Encoder | `Sorters.Encoder ioName` → `Encoders` | STATIC |
| App control | `SrtAppControl` | STATIC |
| Scan topology | `SrtScanBoss` | STATIC |
| Divert lanes | `SrtZoneLane` (Lane, HostZone, Enabled) | STATIC (assignment only) |
| Coarse type (shoe/ship/saw) | name tokens | DERIVED → **REVIEW_REQUIRED** |

## Input / divert / motors / PE / I/O / timing

| Concern | Class | Proven? |
|---------|-------|---------|
| Induct conveyor chain | UNKNOWN / REVIEW | No complete generic chain |
| Divert lane assignment | STATIC | Yes (topology) |
| Divert **output IO** | REVIEW_REQUIRED | Often INVALID in RUN |
| Motors (`SorterCnvMtr`) | STATIC when valid | Site-dependent |
| Confirm PE | DERIVED hint from timers | Not sole proof |
| Track offset counts | UNKNOWN | No RUN field |
| Runtime tracks `SrtTrack*` | DYNAMIC | Activity ≠ divert map |

## Class counts (fact buckets)

| Class | Count |
|-------|------:|
| STATIC | 18 |
| DYNAMIC | 12 |
| DERIVED | 4 |
| REVIEW_REQUIRED | 8 |
| UNKNOWN | 5 |

## SORTER PLC GENERATION

**NOT STARTED** — model foundation only. Divert trigger / Sorter_Track emit remain NOT_SUPPORTED until generic library path exists.
