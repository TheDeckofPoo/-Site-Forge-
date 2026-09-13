# PLC2 Fidelity Audit — ORNCCP2 / Greensboro

**Generated:** 2026-09-13T05:29:09.652282+00:00
**Generated L5X:** `C:/Users/curtiskricke/SiteForge/exports/studio-validation/ORNCCP2_transport_fidelity_candidate.L5X`
**Finished oracle (validation only):** `C:/Users/curtiskricke/SiteForge/workspace/validation/ORLY_GreensboroPLC2_NC_Finished.L5X`

## Policy

- RUN tables are the generation source.
- Finished PLC2 is **validation only** — never a generation template.
- No hard-coded `if device == P123` rules (P123 reported as seed case only).

## I/O channel summary

| Metric | Count |
|--------|------:|
| Finished real inputs | 159 |
| Finished real outputs | 75 |
| Generated real inputs | 147 |
| Generated real outputs | 78 |
| False placeholders | 26 |
| EXACT | 324 |
| EQUIVALENT | 111 |
| WRONG_ADAPTER | 1 |
| WRONG_DEVICE | 32 |
| WRONG_MEMBER | 2 |
| WRONG_SLOT | 0 |
| WRONG_BIT | 0 |
| SHOULD_BE_PLACEHOLDER | 16 |
| RUN_UNRESOLVED | 0 |

## Controller scope

| Scope | Count |
|-------|------:|
| LOCAL | 59 |
| EXTERNAL_REFERENCE | 4 |
| OUT_OF_SCOPE | 147 |
| UNRESOLVED | 74 |

- LOCAL sample: P1000, P1001, P1002, P1004, P1005, P1006, P1007, P1008, P1010, P1011, P1014, P1015
- EXTERNAL_REFERENCE sample: P215, P226, P229, P408

## Device objects (LOCAL conveyors)

| Family | Generated among LOCAL |
|--------|----------------------:|
| Local conveyors | 59 |
| Conv | 59 |
| Conv_AOI | 59 |
| MS | 59 |
| VFD | 0 |
| PE | 29 |

## P123 seed case

| Object / routine | Status |
|-----------------|--------|
| Conv | PRESENT (gen=True) |
| Conv_AOI | PRESENT (gen=True) |
| MS | PRESENT (gen=True) |
| Fast | OK (gen=True) |
| Slow_Flt | OK (gen=True) |
| Slow_Jam | OK (gen=True) |
| L1 | OK (gen=True) |
| L2 | MISSING (gen=False) |

## Connectivity

- Required relationship checks: **206**
- Generated OK: **206**
- Generated missing: **None**
- Coverage: **1.0**

## Artifacts

- `exports/plc2-fidelity/channel_matrix.json`
- `exports/plc2-fidelity/false_placeholder_audit.json`
- `exports/plc2-fidelity/device_object_matrix.json`
- `exports/plc2-fidelity/routine_participation.json`
- `exports/plc2-fidelity/controller_scope.json`
- `exports/plc2-fidelity/connectivity_comparison.json`
- `exports/plc2-fidelity/electron_transport.png` (ControllerScope-filtered Auto Build source PNG)
- `exports/plc2-fidelity/transport_ui_scope.json`
- `exports/studio-validation/ORNCCP2_transport_fidelity_candidate.L5X`
- `docs/AUG28_AUTOGEN_FORENSICS.md`
- `docs/TRANSPORT_CONVEYOR_COMPILER_CONTRACT.md`
- `docs/TRANSPORT_REGRESSION_FORENSICS.md`

## FINAL REPORT

### TRANSPORT UI

| Metric | Value |
|--------|------:|
| raw Conveyor rows (plant ASC) | ~6000 |
| local displayed (Auto Build source) | 59 |
| external displayed | 1–4 |
| remote/site-wide displayed | 0 |

Electron Transport Build patches:
- clear `siteforge.transportBuild.v1` on RUN import
- Auto Build passes active machine → ControllerScope
- import filter + `drawSchematic` keep LOCAL + EXTERNAL_REFERENCE only

`electron_transport.png` is rendered from that filtered Auto Build graph (not a live Electron HWND capture). Curtis visual PASS still requires opening `desktop\Launch-SiteForge.bat` → Import ORNCCP2 → Auto Build.

### IO

| Metric | Value |
|--------|------:|
| real inputs | 147 |
| real outputs | 78 |
| false placeholders | 26 |
| wrong adapter | 1 (was 19) |
| wrong logical device | 32 (WRONG_DEVICE; prior taxonomy 67) |
| missing / RUN_UNRESOLVED | 0 |

### TRANSPORT OBJECTS

| Metric | Value |
|--------|------:|
| local conveyors | 59 |
| Conv objects generated | 59 |
| Conv_AOI generated | 59 |
| MS generated | 59 |
| VFD generated | 0 |
| PE generated | 29 |

Motor-link ownership recovery (`M###`/`M###_AUX` → `P###`) raised conveyor realization from 31 → 63 Autogen / 59 LOCAL-scoped.

### P123

| Item | Status |
|------|--------|
| Conv | YES |
| Conv_AOI | YES |
| MS | YES |
| Fast | YES |
| Slow | YES (Flt/Jam; Slow_PI scaffold still omitted when empty) |
| L1 | YES |
| L2 | NO (Conv_Speed still site-customize stub — no per-belt speed emit yet) |

### Historical recovery

| Item | Status |
|------|--------|
| historical transport implementation recovered | YES (MSCRENO Aug28 structural gates PASS; emitters intact) |
| UI-generated candidate | PARTIAL (CLI from-run candidate ready; Electron HWND capture pending Curtis) |
| ready for Curtis Studio acceptance | **NO** — false placeholders 26 remain; L2/Slow_PI thinner; Electron visual still needs live confirm |

Branch: `feature/plc2-transport-fidelity` (base `feature/plc2-configio-compiler`). No PLC4/PLC5/Sawtooth/Sorter/WCS changes.

