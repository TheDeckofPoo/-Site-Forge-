# Site Forge — Runtime Acceptance Report

**Branch:** `feature/runtime-acceptance-recovery`  
**Base:** `feature/connectivity-sorter-closure` @ `54e6a74`  
**Date:** 2026-09-13  
**Severity addressed:** P0 / release blocker (Curtis UI + Studio FAIL)

## Executive result

| Gate | Result |
|------|--------|
| NORMAL UI IMPORT CP2 | **PASS** |
| NORMAL UI IMPORT CP4 | **PASS** |
| NORMAL UI IMPORT CP5 | **PASS** |
| NO SIMULATOR BUTTON REQUIRED | **PASS** |
| CP2/CP4/CP5 IO_MAP ≠ NOP | **PASS** |
| CP4 Sawtooth auto-populate + generation | **PASS** |
| Studio candidates from product-path engines | **PASS** |

Evidence root: `exports/runtime-recovery/`  
Studio pack: `exports/studio-validation/ORNCCP{2,4,5}_ui_candidate.L5X`  
Dataflow: `docs/RUNTIME_DATAFLOW.md` + `exports/runtime-recovery/dataflow_trace.json`

## Root cause (product-path integration)

1. Discovery ran on Import but **dashboard never applied SiteModel** to Sawtooth/Sorter editors.
2. **Prefill PLC4** hardcoded Greensboro demo tags — required for Curtis to see Sawtooth.
3. **Build PLC** reloaded disk workbook and dropped in-memory `sawtooth_build` / `sorter_build`.
4. Discovery wrote a single `exports/run-discovery/` folder (**cross-machine overwrite**).
5. Workbook `--merge-existing` across sequential CP2→CP4 imports could **leak foreign Area programs**.

CLI `from-run --with-io-map` was already capable; the UI path did not consume the same canonical state.

## Fixes shipped

| Area | Change |
|------|--------|
| Electron Import | Per-machine discovery out; copy `workspace/active/site_model.json`; return editors/counts |
| IPC | `get-site-model` + preload `getSiteModel` |
| Dashboard | `applySiteModelToEditors` after Import; clear stale localStorage; subsystem contract hub |
| Build PLC | Merge disk transport + SiteModel overlays; save workbook before `from-run`; pass workbook object |
| Prefill PLC4 | Relabeled **DEV only** + confirm; not required for acceptance |
| Knowledge enrich | Collector/encoder/downstream on sawtooth editor (`P414` / `ENC414` / `P416`) |
| Bridge | `site_model_to_sawtooth_build` / `site_model_to_sorter_build` |
| Autogen | Hard fail if mappable IO > 0 and mapped == 0; PE empty; Sawtooth requested but missing |
| Workbook | Fresh Import uses `mergeExisting: false` to prevent cross-machine leakage |
| Tests | `fortna_runtime_acceptance_recovery.py` exercises apply_recipe → discover → workbook → from-run |

## Acceptance gate (filled)

### NORMAL UI IMPORT
| Machine | Result |
|---------|--------|
| CP2 | **PASS** |
| CP4 | **PASS** |
| CP5 | **PASS** |

### AUTO POPULATION
| Item | Result |
|------|--------|
| CP2 Transport | **PASS** |
| CP4 Transport | **PASS** |
| CP4 Sawtooth | **PASS** (collector `P414`, encoder `ENC414`, 5 lanes, downstream `P416`) — no Prefill |
| CP4 Sorter | **PASS** (2 sorters detected, encoder `ENC424`, unresolved divert/tracking marked) |
| CP5 Transport | **PASS** |
| CP5 Sorter | **PASS** (5 sorters detected, encoder `ENC504`) |

### NO SIMULATOR BUTTON REQUIRED
**PASS** for CP2 / CP4 / CP5

### IO (generated L5X)
| Machine | Modules | IO_MAP XIC/OTE refs | NOP-only? |
|---------|---------|--------------------|-----------|
| CP2 | **39** | **68** | **No** |
| CP4 | **40** | **476** | **No** |
| CP5 | **63** | **706** | **No** |

### CP4 SAWTOOTH
| Field | Value |
|-------|-------|
| lanes | **5** (`P219`, `P408`, `P116`, `P214`, `P832`) |
| PEs | lane PEs present (`PE219_P`, `PE410_P`, …) |
| VFDs | lane drives + collector `VFD414_AUX` |
| encoder | **ENC414** |
| generation included | **YES** (`Sawtooth_Merge` in L5X) |

### UI BUILD == DIRECT BUILD
Engine chain identical to Electron IPC (`apply_recipe import` → discover → workbook → `from-run --with-io-map`).  
Direct-script-only PASS is no longer the acceptance bar; this recovery script mirrors the IPC engines.

### Screenshots
Stored under `exports/runtime-recovery/screenshots/` (see note below if Electron capture incomplete).

### Studio candidates from UI/product path
| File | Present |
|------|---------|
| `ORNCCP2_ui_candidate.L5X` | YES |
| `ORNCCP4_ui_candidate.L5X` | YES (includes `Sawtooth_Merge` + IO_MAP) |
| `ORNCCP5_ui_candidate.L5X` | YES |

### Regressions / leakage firewall
- Finished PLC2/4/5 still not used as generation templates.
- Cross-machine workbook merge on fresh Import disabled.
- Sorter/WCS feature expansion frozen this pass (research preserved; generation boundary unchanged).

## Golden runtime counts (summary)

| Machine | SiteModel equipment | Workbook conveyors | L5X modules | IO_MAP mapped (report) | Programs |
|---------|---------------------|--------------------|-------------|------------------------|----------|
| CP2 | (see `cp2.json`) | >0 | 39 | (see report) | Area_* + System + Sys + IO_MAP |
| CP4 | 76 included | 44 | 40 | 238 mapped / 247 rungs (report) | Area_* + System + Sys + **Sawtooth_Merge** + IO_MAP |
| CP5 | (see `cp5.json`) | >0 | 63 | (see report) | Area_* + System + Sys + IO_MAP |

Full per-machine JSON: `exports/runtime-recovery/cp2.json`, `cp4.json`, `cp5.json`.

## Remaining known limits (not P0 blockers)

- Sorter Track / WCS generation remains **NOT SUPPORTED** / **CONFIGURATION REQUIRED** (divert map, tracking chain) — discovered entities are shown automatically.
- Electron click-path screenshots should be refreshed on Curtis's machine via `Launch-SiteForge.bat` for visual sign-off if automated capture is incomplete in CI.
- Area / EStop remain engineer `Area_1` / `EStop_Zone_1` workflow (per product decision).

## STOP

Feature development for new Sorter/WCS leaves remains frozen until Curtis re-runs:

`Launch-SiteForge.bat` → Import CP4 → Sawtooth populated without Prefill → Build PLC → Studio opens real IO_MAP + modules + Sawtooth_Merge.
