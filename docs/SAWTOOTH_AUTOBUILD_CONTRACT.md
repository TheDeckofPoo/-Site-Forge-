# Sawtooth Autobuild Contract

## Import flow (no Discover button)

```
Import RUN/tar.gz
  → fortna_run_workspace_discover
  → discover_sawtooth (SawMerge/SawLane)
  → build_sawtooth_merge_model
  → site_model.sawtooth_merge_model + editors.sawtooth
  → applySiteModelToEditors (dashboard)
  → Sawtooth Merge Build tab already populated
  → engineer reviews unresolved
  → Confirm overrides → Autogen workbook
  → Build PLC may include Sawtooth_Merge pack
```

## CP4 acceptance (ORNCCP4)

| Check | Expected |
|-------|----------|
| Merges detected | 1 (`SAWTOOTH_MERGE`) |
| Lanes | 5 |
| Per lane conveyor | RUN Name token (e.g. `LANE_0_P219` → P219) |
| Per lane PE | SawLane.PhotoEyeIO |
| Per lane drive | SawLane.DisableIO (VFD*) |
| VFD bases preserved | 13 |
| Encoders preserved | 2 (ENC414 class on merge) |
| Collector | RUN_DERIVED P414 from VFD414_AUX |
| Unknowns | UNRESOLVED — not guessed |

Regression: `python tools/scripts/test_sawtooth_merge_model_cp4.py`

## UI contract

- Primary view: merge identity, lane cards (conveyor / PE / drive / slice / reserve / approach / collision)
- Advanced: collector jam PEs, track PE calibration, HMI timing (engineer CFG)
- DEV Prefill PLC4 demo hidden under DEV (not for acceptance)
- Reload from RUN reloads SiteModel mapping

## Firewall

- Finished PLC4 never read for population
- Transport Autogen compiler frozen (see `TRANSPORT_AUTOGEN_FROZEN.md`)
- Engineer outputs stay in `exports/current/` — Sawtooth debug under `exports/cp4-*` / `exports/run-discovery/`
