# Sorter Divert Model

**Branch:** `feature/connectivity-sorter-closure`  
**Scope:** How RUN represents sorter section → divert/lane → destination → takeaway/confirm PE hints.  
**Policy:** Finished PLC5 is **validation only** — never generation input. Do not invent divert IO from digit-matching.

Companion artifacts: `exports/sorter-research/divert_map.json`, `track_offset_model.json`, `divert_readiness.json`, `token_model.json`.

---

## RUN representation

| Concept | RUN evidence | Notes |
|---------|--------------|-------|
| Sorter section | `Sorters.asc` | Named sorter + encoder IO (`Encoder ioName`), machine, max cartons |
| Divert / lane | `SrtZoneLane.asc` | Primary divert topology table |
| Destination | `SrtZoneLane.HostZone` | Host zone id assigned to the lane |
| Confirm PE hint | `SrtZoneLane.FullClearTimer` name | String-parsed PE hint — not proof |
| Takeaway hint | `SrtZoneLane.Lane` string | Embedded conveyor id hint — not proof |
| Divert output IO | *(absent in SrtZoneLane)* | Usually `CONFIGURATION_REQUIRED` |

---

## Primary table: `SrtZoneLane`

| Field | Role |
|-------|------|
| `Name` | Zone-lane identity |
| `AppSorter` | Owning app sorter (`SrtAppControl`) |
| `Lane` | Lane / takeaway string (hint source) |
| `HostZone` | Destination host zone |
| `FullClearTimer` | Full-line timer; PE hint source |
| `Enabled` | Active row gate |
| `RightSideDivert` | Side / shoe direction flag |

Optional related: `TwoSidedShoe`, `LaneEnableSignal`. Runtime `SrtTrack*` links prove tracking activity — they do **not** define divert output maps.

---

## Section / encoder: `Sorters.asc`

`Sorters.asc` supplies the sorter **section** entity and encoder binding used with divert rows:

- `Sorter Name` ↔ `SrtZoneLane.AppSorter` / app-control ownership
- `Encoder ioName` → `Encoders.asc` scale (`Ticks Per Foot`)

---

## Hints (confidence MEDIUM / LOW)

| Hint | Derived from | Confidence |
|------|--------------|------------|
| Confirm PE | `FullClearTimer` name patterns (`tmfcPE…`, `tmfcEZPE…`) | **MEDIUM** when a PE-like token parses; else **LOW** |
| Takeaway conveyor | `Lane` string tokens (`P508A1`, embedded section ids) | **MEDIUM** when a conveyor-like token parses; else **LOW** |

These are **hints**, not digit-matching proof. Do not promote to READY / GENERATED from naming alone.

---

## Divert output IO

`SrtZoneLane` does **not** carry an explicit divert output point. Divert output IO is therefore typically **`CONFIGURATION_REQUIRED`** until the engineer supplies the lane → output map.

Divert readiness inputs (sorter at speed, takeaway running/not-manual, fault, rate-limit clear) are likewise incomplete from RUN alone → readiness stays **CFG**.

---

## TrackOffsetModel

| Field | Status |
|-------|--------|
| `ticks_per_foot` | Known from `Encoders.asc` |
| `offset_counts` (induct → divert) | **Engineer / config required** — not an explicit RUN field |

Track offset generation state: **`CONFIGURATION_REQUIRED`**.

---

## Divert trigger

Divert **trigger** remains **`NOT_SUPPORTED`** until all of the following are proven on a generic library path:

1. Track offset (`offset_counts`)
2. Token model (schema modeled; UDT emit deferred)
3. Divert output IO map
4. Timing / readiness contract

Do not clone Greensboro `Sorter_Track_Program.L5X` as a generic compiler.

---

## Validation barrier

Finished PLC5 / gold packs may be used as **oracles only** after RUN-driven discovery and generation. They must not seed divert constants, IO maps, or Area/sorter names into generation.
