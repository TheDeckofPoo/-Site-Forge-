# P0 DEMO HOTFIX — SHIP DISCOVERY CRASH + STALE SITE_MODEL

**BASE:** `9e5d470` (`demo/reno-ship-sorter-readiness`)  
**PROD:** `anton/mission-ready` @ `a935a22` UNTOUCHED  
**DO NOT MERGE. DO NOT RETARGET CURTIS DESKTOP.**

## FIRST DIVERGENCE

`fortna_run_workspace_discover.apply_cross_table_evidence`  
building a `set` of evidence keys:

```python
seen = {(e.get("kind"), e.get("detail"), e.get("table")) for e in evid}
```

## ROOT CAUSE

| | |
|---|---|
| **Expected** | `detail` hashable (str/None) OR key builder freezes nested structures |
| **Actual** | `detail` is a **dict** (encoder association, e.g. `encoder_enable_vfd` → VFDS1) |
| **Source field** | `_encoders_from_discovery`: `evid.append({..., "detail": a})` where `a` is association dict |
| **Why SHIP** | SHIP has sawtooth + encoder `SHIP SORT` with VFD association dicts |
| **Why Pick** | No encoder association dict evidence on the merge path → never hits unhashable set |

After crash, `get-site-model` fell back to unscoped `exports/run-discovery/site_model.json` (**ORNCCP5 / Greensboro** → `504_BELT`, `506_SHIP_SORTER`, …).

## OLD FALLBACK PATH

```
workspace/active/site_model.json  (missing after failed discovery)
  → exports/run-discovery/site_model.json   ← UN SCOPED, OTHER SITE
```

## NEW AUTHORITY RULE

1. Authority = `workspace/active/site_model.json` **only**
2. Must match active-meta: site/controller + run_fingerprint (+ run_dir when present)
3. Discovery failure → **delete** active site_model; return `SITE MODEL UNAVAILABLE / DISCOVERY FAILED`
4. **Never** fall back to unscoped `exports/run-discovery/site_model.json`
5. Successful discovery writes identity block onto site_model and stamps active-meta fingerprint

## FILES CHANGED

- `tools/scripts/fortna_run_workspace_discover.py` — hashable evidence keys + identity metadata
- `desktop/main.js` — fail-closed `get-site-model`; clear active model on discovery failure
- `dashboard/fortna-plus.js` — surface UNAVAILABLE to editors
- `tests/acceptance/test_p0_ship_discovery_site_model_isolation.py`

## SHIP ACTUAL INVENTORY

See `exports/diagnostics/p0_ship_discovery_hotfix/SHIP_ACTUAL_INVENTORY.json`

| Field | Actual |
|---|---|
| Sorter count | 3 |
| Canonical IDs | SHIP SCAN, SHIP SORTER, SHIP SAWTOOTH |
| Primary | SHIP SORTER |
| Area | SHIPSORTER |
| Encoder(s) | SHIP SORT (`ENC_SHIP` token present in model) |
| Induct | PS1 @ PE60_I / SHIP SORT |
| Lanes / diverts | 19 / 19 |
| Scanners | 7 |
| Sawtooth | 1 (SHIP_SAW) |
| Greensboro hits | **NONE** |

## SITE-SWITCH MATRIX

| Order | Result |
|---|---|
| fresh → SHIP | SHIP SORTER; no Greensboro |
| fresh → PICK → SHIP | invariant SHIP |
| fresh → PACK → SHIP | invariant SHIP |
| fresh → SHIP → PICK | Pick sorter-negative |
| fresh → SHIP → PACK | Pack has no SHIP SORTER |

## TESTS

`tests/acceptance/test_p0_ship_discovery_site_model_isolation.py` → **14 passed**

## WARDEN READY

**YES** — for this P0 isolation/hotfix scope (discovery + site_model authority).  
Sorter PLC generation remains **NOT YET QUALIFIED** (unchanged quarantine).
