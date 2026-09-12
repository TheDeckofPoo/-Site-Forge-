# CP4 Blind Discovery — ORNCCP4

**Branch:** `feature/cp4-blind-discovery`  
**Status:** Discovery only — **no sawtooth / CP4 PLC generation**  
**Firewall:** Finished PLC4 L5X was **not** read  
**RUN:** `workspace/cp4-run/RUN` (Greensboro ORNCCP4 tar; extract gitignored)  
**Artifacts:** `exports/cp4-discovery/`

---

## Philosophy

- CURRENT RUN = production source truth  
- Finished PLC4 = validation/reference only (architecture review may compare later)  
- Do not invent Area/ES or lane identity from P-number order  

Provenance on relationships: `RUN_EXPLICIT` | `RUN_DERIVED` | `ENGINEER_CONFIGURED` | `UNKNOWN`

---

## Headline counts

| Item | Count |
|------|------:|
| Physical / mechanical conveyors (CP4-linked) | 76 |
| Placed (geometry) | 76 |
| VFD unique bases / device rows | 13 / 32 |
| Explicit VFD→conveyor maps | 13 |
| Encoders | 2 |
| Sawtooth merges | 1 (`SAWTOOTH_MERGE`) |
| Sawtooth lanes | 5 (all with conveyor + PE + drive) |
| Tracking tables with active rows | 3 |
| Unknowns (Area/ES engineer-required) | 1 category |

Lane identity from Name tokens (e.g. `LANE_0_P219` → `P219`) — not LaneNdx / P-order.

---

## Deliverables

| File | Contents |
|------|----------|
| `site_model.json` | Canonical CP4 Site Model (conveyors, sawtooth, VFDs, encoders, relationships) |
| `equipment.json` | Detailed equipment inventory |
| `vfd.json` | VFD devices + mappings |
| `sawtooth.json` | Merges + lanes + timing |
| `encoders.json` | Encoder table + associations |
| `tracking_wcs.json` | MsgTrack / MsgWCS / SrtTrack / XfrTrack / WCSEvents |
| `unknowns.json` | Gaps (Area/ES, unmapped items) |
| `layout_metrics.json` | Placement / connection candidates |
| `report.md` | Narrative |

## Reproduce

```
python tools/scripts/fortna_cp4_discovery.py \
  --run-dir workspace/cp4-run/RUN --machine ORNCCP4 --out exports/cp4-discovery

python tools/scripts/test_cp4_discovery_no_leakage.py
```

Leakage test must PASS with finished PLC4 present / absent / renamed.

## CP2 freeze (same tip)

Transport workflow preserved:

Import RUN → Auto Build → Review / Correct → Apply to Autogen → Build PLC

Demo blockers addressed on this branch:

- **PE ROLE REQUIRED** when RUN suffix evidence is insufficient (no silent Exit/Jam/Full)
- Engineer can select **JAM / FULL / EXIT / ADD / OTHER / NONE**
- Autogen apply emits only RUN-explicit or engineer-confirmed PE roles
- Bulk **Apply Area / ES** for selected conveyor runs (does not invent Area/ES)

## Out of scope

- Sawtooth PLC generation  
- Matching finished PLC4 conveyor counts  
- Inferring Area/ES from RUN to reduce manual work  
