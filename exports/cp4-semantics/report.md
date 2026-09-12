# CP4 Sawtooth Semantics Compile

Generated: 2026-09-12T16:21:52.228604+00:00
Finished PLC4 used: **NO**
Pass: `cp4-sawtooth-semantics`

## Inputs
- Discovery: `exports/cp4-discovery` (immutable)
- RUN: `workspace/cp4-run/RUN`
- Generic libraries under `tools/libraries/`
- Prior fidelity parameterized program for placeholder audit

## Outputs
- Controller L5X: `C:\dev\worktree\FortnaPlus\exports\cp4-semantics\generated\OReillyGreensboro_ORNCCP4.L5X`
- Parameterized program: `C:\dev\worktree\FortnaPlus\exports\cp4-semantics\generated\Sawtooth_Merge_Parameterized.L5X`
- Semantic model: `semantic_model.json`
- Maps: `merge_signal_map.json`, `encoder_semantics.json`, `vfd_semantics.json`
- Placeholder audit: `placeholder_audit.json` / `placeholder_audit_after.json`
- Validation: `validation_report.json`
- Content digest: `4d12a537312397d4404a67896cd321266a37abef5e0f1da0a01e6b9a679a7c45`

## Resolution counts
| Bucket | Count |
|--------|------:|
| Resolved RUN (incl. RUN_DERIVED) | 69 |
| Resolved library / documentation | 1 |
| CONFIGURATION REQUIRED | 301 |
| UNKNOWN | 0 |
| UNSUPPORTED | 1 |

## Placeholder NOP before → after
- Before (prior generation Sawtooth Conv_* NOP rungs): **12**
- After (Sawtooth Conv_* NOP remaining): **1**
- CAN_GENERATE_REAL_LOGIC applied: **11**

## Semantic decisions
- Lanes: **5** — indices preserved; `LANE_3_P116` → `PE118_P` / `VFD118_EN`
- ENC414: SAWTOOTH_COLLECTOR (real enable/reset logic)
- ENC424: CITY COUNTER — **DOCUMENTATION_ONLY** (not forced into Sawtooth)
- Conv_PE / Conv_Fast: real XIO/XIC → `SawSem_*` where RUN PE evidence exists
- Full Fast_Conv AOI rewrite: **UNSUPPORTED** (area/downstream CONFIG REQUIRED)
- Tracking/WCS: **GENERATION NOT YET SUPPORTED**
- Pack rename applied: `EZPE127_F` → `EZPE217_F` (RUN_DERIVED via Fullline+ReserveTM)

## Validation
- ok: **True**

## Genericity
- Synthetic fixture ok: **True**

## Sidecars
- Integrated sidecar: `unresolved_symbol_audit.json` (145123 bytes)
- Integrated sidecar: `unresolved_symbol_audit.md` (80278 bytes)
- Integrated sidecar: `reserve_eye_analysis.md` (8070 bytes)
- Integrated sidecar: `reserve_eye_analysis.json` (14958 bytes)

## Reserve / full-eye analysis (sidecar)
See `reserve_eye_analysis.md` / `.json`. Semantics compile applies EZPE127_F→EZPE217_F as RUN_DERIVED when Fullline+ReserveTM agree; keeps LANE_4 F1/F2 paired roles without blind rename.

## Parallel unresolved symbol audit
- File: `unresolved_symbol_audit.json` / `.md`
- Symbol rows: **72**
- Histogram: `{"CONFIGURATION_REQUIRED": 2, "ENGINEER_CONFIGURED": 4, "GENERIC_LIBRARY_CONSTANT": 6, "RUN_DERIVED_HIGH_CONFIDENCE": 1, "RUN_EXPLICIT": 19, "UNUSED_FOR_THIS_SITE": 40}`
- Reserve-eye summary keys: `['EZPE217_F', 'EZPE212_F1_vs_F2']`

### Sample
- `EZPE127_F`: UNUSED_FOR_THIS_SITE
- `Enable_Merge1_Reserv`: ENGINEER_CONFIGURED
- `Enable_Merge2_Trk`: ENGINEER_CONFIGURED
- `Enable_hold`: ENGINEER_CONFIGURED
- `MRG422_aoUNL_PT_CnvDeltaDist`: UNUSED_FOR_THIS_SITE
- `MRG422_astCollPeTrackCal`: UNUSED_FOR_THIS_SITE
- `MRG422_astLaneClctrSlotResvCntrl`: UNUSED_FOR_THIS_SITE
- `MRG422_astLanePeTrackCal`: UNUSED_FOR_THIS_SITE
- `MRG422_astUNL_BFR_CnvCtrl`: UNUSED_FOR_THIS_SITE
- `MRG422_astUNL_GPR_CnvCtrl`: UNUSED_FOR_THIS_SITE
- `MRG422_astUNL_PT_CnvCtrl`: UNUSED_FOR_THIS_SITE
- `MRG422_astUNL_Q1_CnvCtrl`: UNUSED_FOR_THIS_SITE

## Biggest remaining uncertainty
LANE_0 full-eye gold slot EZPE127_F→EZPE217_F is RUN_DERIVED (Fullline-backed) but pack AOI wiring for upstream-P217 vs lane-P219 still needs engineer confirm; LANE_4 paired F1/F2 reserve-clear vs lane-full-eye dual roles; full Fast_Conv AOI rewrite remains unsupported without area/downstream config.

## Tests
- `test_cp4_sawtooth_semantics.py`: PASS
- `test_cp4_sawtooth_fidelity.py`: PASS (kept green)

## UI
No Transport polish. No commit/push from this pass.
