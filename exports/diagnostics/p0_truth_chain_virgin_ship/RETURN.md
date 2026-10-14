# P0 TRUTH CHAIN + MSCRENOSHIP BUILD READINESS — RETURN

## MISSION
P0 Truth Chain + MSCRENOSHIP Build Readiness (Parts 1–7 + LHF + semantic completeness)

## REPOSITORY
https://github.com/TheDeckofPoo/-Site-Forge-.git  
Worktree: `C:\dev\worktree\FortnaPlus-demo-ship`

## BRANCH
`demo/reno-ship-sorter-readiness`

## START SHA
`46f73e4418bacd14a8441dd641ae996b2df5c946`  
(hotfix underneath: `bc0bb0b`)

## FINAL SHA
_(filled after commit/push)_

---

## FIRST DIVERGENCE (each repaired defect)

| Defect | FIRST DIVERGENCE | Repair |
|---|---|---|
| Soft site_model identity | `fortna_run_workspace_discover.site_model_identity_matches` + `desktop/main.js readActiveSiteModelOrFail` accepted when fingerprint/controller missing | Missing identity → REJECT |
| Stale sorter UI cache | `applySiteModelToEditors` returned on model reject without wiping `workbook.sorter_build` | `invalidateStaleSorterDisplay` |
| Pick Area dual identity | `fortna_workbook.apply_workbook_to_input` stamped `Area_Test1` beside provisional `MSCRENOPICK_Area` without migrating conveyors | `_unify_provisional_area_identity` + PD-0003 plc_symbol join |
| SHIP scanners 0 vs 7 | `fortna_run_workspace_discover` nested scanners under sorter_model/editors only | Promote to `site_dict["scanners"]` + counts |
| API key false-unavailable | `ai-io-check-api` called `--check-api` without project context; argparse required run-dir/machine | Pass active project context; optional args for check-api |
| NTP CONFIG contract | Enable_Instruction=0 only | Explicit `NTP_Configured` BOOL + `XIC(NTP_Configured)` gate |

---

## SITE_MODEL_AUTHORITY_CHAIN
```
active-meta (machine + run_fingerprint + run_dir)
  → workspace/active/site_model.json ONLY
  → site_model_identity_matches / readActiveSiteModelOrFail
  → REJECT if missing controller / missing fingerprint / mismatch
  → NEVER unscoped exports/run-discovery/site_model.json
  → NEVER newest-file / repo fallback / prior site model
```

## SORTER_AUTHORITY_CHAIN
```
checked active site_model
  → sorter_model / editors.sorter
  → sorterBuildFromSiteModel
  → autogenState.sorter + workbook.sorter_build
If model rejected/unavailable:
  → invalidateStaleSorterDisplay
  → 0 sorter objects / cards / lanes / encoders / scanners / commissioning items
  → UI: "SORTER DISCOVERY UNAVAILABLE / FAILED" (not "No sorters discovered")
```

## PICK_AREA_IDENTITY_CHAIN
```
BEFORE:
  RUN seed → MSCRENOPICK_Area (conveyor.main_area ×N)
  Engineer Safety → Area_Test1 + Area_Test1_ESZone1
  apply_workbook → BOTH peer strings in inp.areas
  PD-0003 lookup Area_Test1 vs MSCRENOPICK_Area → miss → 29× Fast_Conv WITHHELD

AFTER:
  display_name=Area_Test1
  canonical_area_id=area_Area_Test1
  plc_symbol=Area_Test1
  provisional MSCRENOPICK_Area conveyors migrate → Area_Test1
  safety_zone → Area_Test1_ESZone1 (same canonical Area only)
  PD-0003 joins on plc_symbol / aliases
  PD-0003 NOT bypassed
```

## SHIP_SCANNER_EVIDENCE
```
RUN FORTNA/ScnScanDevice.asc.MSCRENOSHIP → 7 PROVEN
fortna_sorter_discovery → sorter_model.scanners=7
PROMOTE → site_model.scanners=7 / counts.scanners=7
Names: SHIPSCAN1, TOTESCAN1, TOTESCAN2, SHIPSCALE, SHIPSCAN2, TOTESCAN3, TOTESCAN4
No Reno hard-coding. No Greensboro residue.
```

## API_STATUS_FIX
```
main.js ai-io-check-api → --check-api --run-dir <ACTIVE RUN> --machine <meta>
fortna_ai_io_analyze.py → --run-dir/--machine optional only with --check-api
valid key → AVAILABLE; missing → correct unavailable reason
validation not weakened
```

---

## VIRGIN SHIP RESULT

| Field | Value |
|---|---|
| IMPORT | **PASS** (identity OK, fingerprint present) |
| SORTER DISCOVERY | **PASS** (detected; scanners=7; encoders=1; sorters=3) |
| PLC ARTIFACT GENERATED (normal) | **NO** |
| BLOCKING GATE (normal) | Safety configuration required — 18 Safety devices, 0 assigned to operational zones |
| PLC ARTIFACT GENERATED (Safe Partial + ack) | **YES** — `MSCRENOSHIP.L5X` 1,570,659 bytes |
| STRUCTURAL AUDIT | generate disposition `CURRENT_ATTEMPT_SUCCESS` / build_status=`PARTIAL`; auditor API needs manifest (see punch-list) |
| SORTER_TRACK GENERATED | **NO** (quarantine preserved; not forced) |
| COMMISSIONING READY | **NO** |

Active identity:
- machine/controller: MSCRENOSHIP
- run_fingerprint: `ff4cd44f23d3d5cc74d0049a4427f08577244ebcf342378b98d6c5c202429d12`

Counts (checked model): equipment_included=65, encoders=1, scanners=7, sorters=3, photoeyes=91, motors=80

---

## LOW_HANGING_FRUIT_COMPLETED
- NTP AOI_SNTP_QUERY scaffold + **NTP_Configured=0 gate** + Enable_Instruction=0
- System_Logic FUNCTIONAL
- Pulse / TimeStamp FUNCTIONAL
- Area_Logic / Area_PI / Control_Station / Conv_Jam / Conv_Flt / Conv_PE structure
- Stacklight Area→Stack_Light UDT writers
- Spare-output isolation (no XIC(NO_PointPlaceholder)OTE(spare_out))

## LOW_HANGING_FRUIT_WITHHELD
- Device Comm live AOI_CommDiag — **CommDiag_UDT absent** from approved library → NOP + REVIEW
- NTP commissioning_ready — engineer must set NTP_Configured + server + ENET
- Physical Stacklight I/O mapping — PRESENT_BUT_INERT consumers
- Conv_PI — absent on virgin SHIP (no PI-writer Safety zone)
- Sorter_Track — NOT_YET_QUALIFIED quarantine preserved
- WCS / P2P site-specific values

## LIBRARY_FINGERPRINT_USED
`tools/libraries/OReilly_Library_v3.L5X`  
SHA256 prefix: `d33dee8b803d1e6f` (full: `D33DEE8B803D1E6F51472C5655DBC02F5167675424550CE2F086450EAA1D25B2`)

## GREENSBORO_PATTERNS_REFERENCED
Read-only structural only: System/NTP/Pulse/TimeStamp/Area/Stacklight recurring shape.  
**NOT copied:** I/O addresses, device names, Safety membership, encoder/scanner names, IP/NTP server, WCS, P2P.

## ACTIVE_RUN_FACTS_USED
MSCRENOSHIP RUN only — ScnScanDevice scanners, equipment/encoders counts, ntp.conf presence for server path (no Greensboro IP).

## STACKLIGHT_REFERENCE_CONTRACT
Library `Stack_Light` UDT (Horn/Red/Blue/Green/Amber). Gold/library Stacklight routine often NOP.  
Autogen writes Area.Run/Stop → `.O.Green/.Red/.Amber`.

## RENO_STACKLIGHT_ACTUAL
`MSCRENOSHIP_Area_Stacklight.O.{Green,Red,Amber}` written from Area status.

## MISSING_CONNECTIONS
No proven physical output map / HMI pack / AOI consumer for Stack_Light bits.

## SAFE_GENERIC_FIXES
Keep UDT writers; classify PRESENT_BUT_INERT until consumer proven. Do not invent beacon addresses.

---

## ROUTINE COMPLETENESS MATRIX (Safe Partial SHIP)
35 routines — status counts: FUNCTIONAL=20, PRESENT_BUT_INERT=14, FUNCTIONAL_BUT_CONFIG_REQUIRED=1  
Full JSON: `exports/diagnostics/p0_truth_chain_virgin_ship/routine_matrix.json`

Notable:
| PROGRAM | ROUTINE | STATUS | REASON |
|---|---|---|---|
| System | NTP | FUNCTIONAL_BUT_CONFIG_REQUIRED | NTP_Configured=0 gate |
| PLC_Fast | Pulse | FUNCTIONAL | |
| PLC_Fast | TimeStamp | FUNCTIONAL | |
| System | System_Logic | FUNCTIONAL | |
| MSCRENOSHIP_Area_Slow | Stacklight | PRESENT_BUT_INERT | UDT bits, no consumer |
| System | Devices_Comm_Logic | PRESENT_BUT_INERT (NOP+REVIEW) | CommDiag_UDT missing |
| MSCRENOSHIP_Area_Fast | Conv_PE | FUNCTIONAL | |
| — | Conv_PI | NOT PRESENT | no PI-writer zone on virgin |

---

## FILES CHANGED
- `tools/scripts/fortna_run_workspace_discover.py` — identity fail-closed; scanner promotion; counts
- `tools/scripts/fortna_area_symbol.py` — provisional helper; lookup keys
- `tools/scripts/fortna_workbook.py` — unify provisional→engineer Area
- `tools/scripts/fortna_autogen.py` — PD-0003 plc_symbol bind; NTP_Configured gate
- `tools/scripts/fortna_ai_io_analyze.py` — check-api project context
- `desktop/main.js` — identity reject; API check context
- `dashboard/fortna-plus.js` — sorter invalidate; discovery-fail UI; RUN LOADED gate; encoder/scanner from model
- `tests/acceptance/test_p0_truth_chain_identity_sorter_area.py` — new
- `tests/acceptance/test_p0_ship_discovery_site_model_isolation.py` — scanner top-level
- `tests/compiler/test_demo_ntp_spare_safety.py` — NTP_Configured expectations
- diagnostics under `exports/diagnostics/p0_truth_chain_virgin_ship/`

## FORBIDDEN SHORTCUT CHECK
**PASS** — no invented physical facts; no Greensboro copy; sorter quarantine kept; no L5X direct patch; no merge; no desktop retarget; PD-0003 not bypassed; CommDiag not faked.

## TESTS RUN
`tests/acceptance/test_p0_truth_chain_identity_sorter_area.py`  
`tests/acceptance/test_p0_ship_discovery_site_model_isolation.py`  
`tests/compiler/test_demo_ntp_spare_safety.py`  
→ **34 passed** (plus scanner top-level addition)

## TARGET-SITE RESULT
MSCRENOSHIP: identity PASS; scanners 7; sorter discovery PASS; normal PLC blocked on Safety assignment; Safe Partial L5X emitted; Sorter_Track not generated.

## REGRESSION-SITE RESULTS
PICK Area unify unit-tested (Area_Test1). Full Pick virgin re-gen not re-run in this mission (punch-list: Warden should exercise Pick Area_Test1 Fast_Conv closure on gold workbook).

## KNOWN REMAINING FAILURES
1. Normal (non-partial) SHIP generate blocked until Safety devices assigned to operational zones
2. Device Comm WITHHELD — CommDiag_UDT absent from approved library
3. Stacklight PRESENT_BUT_INERT — no physical/HMI consumer
4. Conv_PI absent on virgin SHIP without PI-writer Safety zone
5. Sorter_Track remains NOT_YET_QUALIFIED
6. Auditor CLI invoked without manifest in diagnostic harness (generate already audited disposition)

## NEW PUNCH-LIST ITEMS DISCOVERED
1. Wire `audit_l5x(path, manifest)` into virgin diagnostic harness with build_manifest
2. PLC_Init emitted as ST / empty rung-text — matrix under-classifies ST bodies
3. Devices_Comm_Logic should surface status REVIEW_REQUIRED/WITHHELD explicitly in UI compile hub
4. Pick gold workbook end-to-end Fast_Conv closure proof for Warden

## WARDEN READY
**YES** — for independent qualification of truth-chain repairs + Safe Partial SHIP structure.  
Not a release acceptance. COMMISSIONING READY = NO. Sorter_Track quarantine intact. No merge. No desktop retarget.
