# CP4 Blind Discovery — ORNCCP4

**Status:** Discovery only — **no PLC generation**  
**Firewall:** Finished PLC4 L5X was **not** read  
**RUN:** `workspace/cp4-run/RUN` (from Greensboro ORNCCP4 tar; extract gitignored)  
**Artifacts:** `exports/cp4-discovery/`

---

## Scope

| In scope | Out of scope |
|----------|----------------|
| Sawtooth / VFD / encoder / tracking inventory | Sawtooth PLC generation |
| CP4 physical geometry inventory | Matching finished PLC4 counts |
| Provenance + leakage regression | Autogen workbook changes for CP4 |

Architecture/review may compare to finished PLC4 **after** this freeze.

---

## Headline counts

| Item | Count |
|------|------:|
| Mechanical equipment (CP4-linked) | 76 |
| VFD unique bases (explicit conveyor maps) | 13 |
| Sawtooth merges / lanes | 1 / 5 |
| Saw lanes with physical geometry | 5 / 5 |
| Encoders | 2 |
| Tracking tables with active rows | 3 |

Lane identity comes from explicit Name tokens (e.g. `LANE_0_P219` → `P219`) — **not** P-number order.

---

## Artifacts

| File | Contents |
|------|----------|
| `equipment.json` | CP4 mechanical inventory + geometry |
| `vfd.json` | VFD devices and explicit mappings |
| `sawtooth.json` | Merges + lanes |
| `encoders.json` | Encoder table + associations |
| `tracking_wcs.json` | MsgTrack / MsgWCS / SrtTrack / XfrTrack / WCSEvents |
| `layout_metrics.json` | Placement + connection candidates |
| `report.md` | Narrative summary |

Provenance codes: `RUN_EXPLICIT` | `RUN_INFERRED` | `ENGINEER_REQUIRED` | `UNKNOWN`

## Reproduce

```
python tools/scripts/fortna_cp4_discovery.py \
  --run-dir workspace/cp4-run/RUN --machine ORNCCP4 --out exports/cp4-discovery

python tools/scripts/test_cp4_discovery_no_leakage.py
```

## Related

- CP2 demo readiness / Fit Visible: `docs/CP2_COMPLETION_GATE.md`
- Geometry calibration: `docs/RUN_GEOMETRY_CALIBRATION.md`
