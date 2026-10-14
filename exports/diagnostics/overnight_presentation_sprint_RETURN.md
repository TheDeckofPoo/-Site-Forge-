# OVERNIGHT PRESENTATION SPRINT — RETURN

**MISSION:** SHIP SORTER + STANDARD AREA COMPLETION + NTP + UX  
**REPOSITORY:** https://github.com/TheDeckofPoo/-Site-Forge-  
**BRANCH:** `demo/reno-ship-sorter-readiness`  
**WORKTREE:** `C:\dev\worktree\FortnaPlus-demo-ship`

| Field | SHA |
|---|---|
| **START SHA** | `a935a22` |
| **DEMO SHA (FROZEN)** | `2b2e2a6` |
| **LATEST FOLLOW-UP SHA** | *(none yet — equals DEMO SHA)* |
| **PROD anton/mission-ready** | `a935a22` **UNTOUCHED** |

**DO NOT MERGE. DO NOT RETARGET CURTIS DESKTOP.**  
Preserved: `MSCRENOPICK_2026_10_13_1725.L5X` (prod candidate artifact).

---

## GREENSBORO CONTRACT VERSION NOTES

Authority: **CURRENT APPROVED LIBRARY (`OReilly_Library_v3`) WINS.**

| Contract | Result |
|---|---|
| CS_UDT / Enc_UDT / SKT_UDP_DATA | Match library |
| AOI_SNTP_QUERY / Slow_ControlStation / PE_Logic | Present in library |
| Comm_UDT | PLC4 layout differs → **library wins** |
| Area_UDT | PLC5 missing EngMgmt members → **library wins** |
| CommDiag_UDT | Finished PLC4 only; **absent from library** → do not transplant |
| Slow_Flt sig | Library/PLC4 vs older PLC2/5 → **library wins** |

Artifacts: `overnight_greensboro_contract_guard.md` / `.json`, `demo_greensboro_contract_guard.json`

---

## AREA ROUTINE BEFORE/AFTER

| Routine | Before (gold Pick) | After (demo rule) |
|---|---|---|
| Conv_PE | Missing | **Still omitted** — no `PE_Logic` binding / PE ownership evidence (no empty shell) |
| Conv_PI | Missing | **Still omitted** — no PI-writer Safety zone (PD-0003); no invented `{Area}_Safe` |
| Slow stack JSRs | Present | Unchanged scaffolding |

**Root cause:** evidence gates, not missing JSR names. Empty shells forbidden.

---

## CONTROL STATION BEFORE/AFTER

| Before | After |
|---|---|
| Control_Station duplicated Area_HMI Start/Reset/Silence/Run OTEs (dual writer with Area_Logic) | No CS_UDT → **REVIEW stub**; Area_Logic remains **single writer** |
| Slow_ControlStation(=0) hazard | When CS_UDT proven → emit `Slow_ControlStation(...)`; Area_PI aggregates CS `O_*` |

---

## SHIP SORTER EXPECTED/ACTUAL

| Field | Expected | Actual | Match |
|---|---|---|---|
| Equipment Type | SORTER | SORTER | YES |
| Sorter | SHIP SORTER | SHIP SORTER | YES |
| Area | SHIPSORTER | SHIPSORTER | YES |
| Motor | VFDS1 | VFDS1 | YES |
| Encoder | SHIP SORT / ENC_SHIP | SHIP SORT / ENC_SHIP | YES |
| Induct | PS1 @ PE60_I | PS1 @ PE60_I | YES |
| Lane count | 19 | 19 | YES |
| Physical divert count | 17 | 17 | YES |
| Resolved I/O (hard DO) | 14 | 14 | YES |
| PE coverage | 16/17 | 16/17 | YES |
| WCS | DETECTED | DETECTED | YES |
| Review count | 5 | 5 | YES |

**Not selected as sorter:** SHIP SCAN (scanner), SHIP SAWTOOTH (sawtooth merge).

Artifact: `exports/diagnostics/overnight_ship_sorter_discovery.json`

---

## SORTER GENERATOR STATUS

**SORTER PLC GENERATION — NOT YET QUALIFIED**

- Sorter_Track Phase 1 pack exists — not demo-qualified for MSCRENOSHIP  
- ShippingSorter Area_L3 generation: NOT_SUPPORTED  
- WCS PLC generation: **BLOCKED** (no approved generic WCS source; Hunter agrees)  
- Quarantine **not** lifted despite Greensboro 14-routine structural oracle  

---

## NTP BEFORE/AFTER

| Before | After |
|---|---|
| AOI present; gold deferred REVIEW; no SNTP_* scaffold | Generic scaffold: `SNTP_AOI_TAG` + `SNTP_SERVER_ADDRESS` + MSG tags + `AOI_SNTP_QUERY(...)` |
| | No server → **CONFIG_REQUIRED**, Enable_Instruction=0, empty address |
| | Site server from options / RUN `ntp.conf` only — **never** Greensboro IP |
| | `commissioning_ready=False` always until engineer enables |

Hunter: library has full generic NTP contract — independently confirmed; implemented as low-risk scaffold.

---

## DEVICE COMM VERDICT

**DO NOT IMPLEMENT** until all proven generically:

1. Approved 3-member `CommDiag_UDT` in library  
2. AOI_CommDiag instruction contract  
3. Group-header rung contract beyond Group1  
4. Module binding rules  

Current: Devices_Comm_Logic → **REVIEW_REQUIRED (PD-0029)** when CommDiag_UDT absent.  
Artifact: `overnight_device_comm_verdict.md`

---

## SPARE OUTPUT RESULT

**FIXED.** Shared `NO_PointPlaceholder` no longer energizes spare outputs.

- Spare inputs may still `OTE(NO_PointPlaceholder)` (documentation sink)  
- Spare outputs → documentation-only `NOP()` — no functional writer  

---

## TOPOLOGY/UX RESULT

- Area empty state: **CONVEYORS: N** explicit; zero-conveyor warning that Safety does not protect other Areas’ conveyors  
- No synthetic `AreaName_ESZone1` seed for empty Areas (`safetyStampForArea`)  
- Safety zone cards show CONVEYORS count + Area ref  
- Selected conveyor canonical card: Upstream / Downstream / Equipment / Motor / PE roles / Area / Safety Zone / Status  
- Topology table hides empty Motor/PE/PI columns when unused  

Toolbar: audit written (`overnight_toolbar_audit.md`); further demotion of Advanced/Developer controls = **post-DEMO follow-up** only.

---

## FILES (demo branch vs a935a22)

Key commits:

1. `8f98981` — contract guard + Control_Station single-writer + Area_PI  
2. `7f6e575` — NTP scaffold + spare-output safety  
3. `2b2e2a6` — **DEMO SHA** sorter UI + Area/topology UX + diagnostics + tests  

---

## TESTS

```
tests/compiler/test_demo_ntp_spare_safety.py
tests/compiler/test_demo_control_station_single_writer.py
tests/sorter/test_demo_ship_sorter_discovery.py
→ 13 passed
```

Full L5X regen matrix (SHIP / PICK / PACK + two unrelated RUNs): **not executed overnight** — unit/discovery evidence only. Punch-list for morning if Warden needs full regen.

---

## KNOWN LIMITS

- Conv_PE / Conv_PI still omitted without PE_Logic / PI-writer evidence  
- Sorter PLC generation not qualified  
- WCS / Device Comm / P2P generation blocked  
- MEM_/FUTURE divert rows remain REVIEW  
- Toolbar Advanced regrouping incomplete (audit only in DEMO SHA)  
- Task/IO_MAP scheduling audit (Hunter #6) **report-only, not changed**  
- Cross-site full pipeline regen pending  

---

## KNOWN REMAINING FAILURES

1. Sorter PLC generation not qualified  
2. Device Comm REVIEW_REQUIRED (CommDiag_UDT gap)  
3. Conv_PE/Conv_PI absent on Pick without evidence  
4. Full Phase 12 site regen not run  

**KNOWN REMAINING FAILURES:** as listed (not NONE)

---

## DEMO READY

**YES** — for truthful Ship sorter discovery/model/UI + NTP scaffold + spare safety + Area zero-conveyor clarity.

**WARDEN READY:** **NO** for sorter PLC generation / release acceptance.  
**YES** for independent review of DEMO SHA `2b2e2a6` discovery/UI/NTP/spare contracts.

---

## POST-DEMO FOLLOW-UP (allowed after freeze)

Isolated low-risk commits only:

- topology blank column polish  
- toolbar PRIMARY/ADVANCED regrouping  
- first-time-user polish  

Do **not** change Transport/Safety/I/O generation semantics unless a test proves P0.

**DEMO SHA remains fallback:** `2b2e2a6`
