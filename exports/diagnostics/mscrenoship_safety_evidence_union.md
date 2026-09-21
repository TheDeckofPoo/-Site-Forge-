# MSCRENOSHIP Safety evidence UNION

**Machine:** `MSCRENOSHIP`  
**RUN:** `C:\dev\worktree\FortnaPlus\workspace\_reno_peek\20260813-1132-MSCRENO-MSCRENOSHIP-RUN\RUN`

## Early-return bug

- **Real:** `True`
- **Location:** `dashboard/safety-build.js loadDevicesFromRun`
- **Before:** Returned after first successful buildSafetyModel even when inventory was ESTOP/ESLS-only, skipping Hardware I/O classification UNION.
- **Fix:** UNION all sources (SafetyModel + listDevices + Hardware I/O); wipe on Load/Clear; never serve previous-machine cached model.

## Counts by role

| Role | Before | After |
|------|--------|-------|
| ESTOP | 13 | 13 |
| ESLS | 5 | 5 |
| ESR | 0 | 0 |
| MCR | 0 | 0 |
| CS | 0 | 0 |
| total | 18 | 18 |

- **MCR recovered:** 0
- **ESR recovered:** 0
- **foreign_stale:** 0 (required 0 on clean RUN)

## Source UNION counts

- `estop`: 18
- `conveyor`: 17
- `claim_ledger`: 17
- `hardware_io_role`: 0
- `hardware_io_name`: 0
- `hardware_io_channel`: 17
- `configio`: 17

## MCR provenance

No current-site MCR/ESR for MSCRENOSHIP. Hardware I/O `unresolved_named_points` still lists PACK-owned `13MCR*` / `14MCR*` / `13ESR1_AUX` — correctly **excluded** from the current-site UNION.

Excluded foreign unresolved:
- `13MCR1` (MCR)
- `14MCR1` (MCR)
- `13ESR1_AUX` (ESR)
- `13MCR1_AUX` (MCR)
- `14MCR1_AUX` (MCR)
- `14MCR1_R1_AUX` (MCR)
- `14MCR1_R2_AUX` (MCR)

Grouping demo (stem + AUX + T_ alias → one device):

```json
{
  "id": "13MCR1",
  "name": "13MCR1",
  "kind": "MCR",
  "stem": "13MCR1",
  "groupKey": "MCR:13MCR1",
  "signals": [
    {
      "name": "13MCR1",
      "role": "PRIMARY",
      "kind": "MCR",
      "physicalEndpoint": "",
      "sources": [],
      "evidence": []
    },
    {
      "name": "13MCR1_AUX",
      "role": "AUX",
      "kind": "MCR",
      "physicalEndpoint": "",
      "sources": [],
      "evidence": []
    },
    {
      "name": "T_13MCR1",
      "role": "PRIMARY",
      "kind": "MCR",
      "physicalEndpoint": "",
      "sources": [],
      "evidence": []
    },
    {
      "name": "T_13MCR1_AUX",
      "role": "AUX",
      "kind": "MCR",
      "physicalEndpoint": "",
      "sources": [],
      "evidence": []
    }
  ],
  "signalNames": [
    "13MCR1",
    "13MCR1_AUX",
    "T_13MCR1",
    "T_13MCR1_AUX"
  ],
  "status": "GROUPED",
  "origin": "AUTO_RUN_PROVEN",
  "sources": []
}
```

