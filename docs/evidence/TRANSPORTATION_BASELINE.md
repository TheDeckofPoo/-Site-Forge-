# Transportation Baseline

Generic Transportation semantics + ORNCCP2 freeze acceptance.

**Authoritative freeze artifact:** `exports/stabilization/transportation_freeze_report.md`  
**Reproduce:** `python tools/scripts/test_transportation_freeze.py` (53/53 when PLC2 RUN present)

---

## Architecture reminder

```
RUN Conveyor / MergeBoss / MergeInputs / Mtrchain / Jam*
  → decoder / CP4 adapters
  → Transport Build (engineer Areas)
  → Apply to Autogen
  → Area_*_Fast/Slow/L1/L2 programs
```

CURVE display polish is **presentation only** — does not mutate topology.

---

## ORNCCP2 freeze targets (four merges)

| MergeBoss | Type |
|-----------|------|
| `MERGE_406_3-1` | 3-1 |
| `MERGE_316_SPUR` | SPUR |
| `MERGE_400_2-1` | 2-1 |
| `MERGE_324_SPUR` | SPUR |

### MergeInputs

| Boss | Lanes |
|------|-------|
| MERGE_406_3-1 | LANE1_P404, LANE2_P138 |
| MERGE_316_SPUR | LANE1_P136, LANE2_P312 |
| MERGE_400_2-1 | LANE1_P242, LANE2_P150_2-1 |
| MERGE_324_SPUR | LANE1_P150_SPUR, LANE2_P320 |

### MERGE_316 chain (accepted)

- LANE1_P136 Presence `EZPE136_P1` ReleaseIO `SSVEZPE136_P1`
- LANE2_P312 Presence `PE314_P` ReleaseIO `M314`
- M314 → Motor_Ndx M314, Chained1 P314, Aux LATCH_MERGE_316, Enabled M136_AUX
- Physical: M314 → P314 → P316 CURVE

### MERGE_324 chain (accepted)

- Analogous M322 → P322 → P324 CURVE (see freeze report)

---

## Counts — resolve the 54 vs 600 discrepancy

| Metric | Authoritative freeze count | Alternate / raw | Definition |
|--------|---------------------------:|-----------------|------------|
| MergeBoss | **4** (required identities) | 5 including N/A row in some raw scans | Semantic active merges for regression |
| MergeInputs | **8** (lanes for four bosses) | 15 rows including N/A placeholders | Valid lane rows for four bosses |
| Jamcheck | **54** | **600** | **54** = CP4 jam adapter `jamcheckRecordsTouched` / semantic active; **600** = raw ASC row capacity including empty/INVALID template rows |
| Jamzones | **27** (freeze MD) / CP4 identities **17** | **100** raw | Prefer freeze MD + CP4 adapter notes; raw 100 is table capacity |
| Mtrchain | **176** | **400** raw | **176** = semantic entries used by freeze; 400 = raw ASC rows |
| CURVE | **69** | 69 | Conveyor.Type == CURVE |
| Conveyor | — | 6000 raw | Full ASC including unused template rows — **not** a freeze regression count |

**Authoritative for Transportation freeze regression:** the **semantic/active** counts in `transportation_freeze_report.md` (MergeBoss 4, MergeInputs 8, Jamcheck 54, Mtrchain 176, CURVE 69).

Raw ASC row counts are **schema capacity / dump size**, not acceptance targets.

---

## UI / selection (accepted behavior)

- Body + label + right-click selection  
- Hit geometry tracks visible geometry after Area moves  
- Presentation offsets freeze after initial layout (no musical chairs)  
- CURVE: symbolic oblong; display heading from RUN geometry or engineer angle override  

Reproduce: `test_transport_hit_geometry.py`, `test_transport_area_move_positions.py`, `test_live_canonical_handoff.py`
