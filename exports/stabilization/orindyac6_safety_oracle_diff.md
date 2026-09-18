# ORINDYAC6 Safety Oracle Diff (GATE 6)

Generated: `2026-09-18T19:12:26.422767+00:00`

## Sources

- **Virgin RUN:** `workspace/_virgin_orindy/RUN` (machine ORINDYAC6)
- **Finished oracle (validation ONLY):** `C:\Users\curtiskricke\Desktop\ORiellys Browns\PLC Progrms\ORLY_Brownsburg_IN_PLC6_TEST2.L5X`
- **Site Forge export:** `C:\dev\worktree\FortnaPlus\exports\current\ORINDYAC6_2026_09_18_1448.L5X`

## Policy

- No site-specific branches
- Do **not** copy ShippingSorter membership from finished PLC unless RUN proves it
- Do **not** invent Safety devices
- UNKNOWN membership → REVIEW_REQUIRED / fail-safe shell (omit_unresolved_safety available)

## Zone counts

| Side | Zones | Safe_Logic | Safe_PI | Main JSRs | ES_SIL1_Cat1 | ES_PI20 | NOP |
|------|------:|----------:|--------:|----------:|-------------:|--------:|----:|
| Oracle PLC6 | 2 | 2 | 2 | 4 | 44 | 5 | 0 |
| Site Forge | 0 | 0 | 0 | 0 | 0 | 0 | 2 |

### Oracle zones

`ShippingSorter_ESZone1`, `ShippingSorter_ESZone2`

### Site Forge zones

_(none — NOP shell)_

## Classifications

| Item | Classification | Note |
|------|----------------|------|
| Program ES present | `COOKIE_CUTTER_MATCH` | Both emit Program ES |
| ScheduledProgram ES | `COOKIE_CUTTER_MATCH` | Safety task schedules Program ES |
| Main_Routine JSR → *_Safe_Logic / *_Safe_PI | `SITE_FORGE_MISSING` | Oracle has per-zone JSRs. Current Site Forge ORINDYAC6 export is NOP shell because safety_build membership was empty at generate. |
| ES_SIL1_Cat1 AOI calls | `SITE_FORGE_MISSING` | Cookie-cutter: one ES_SIL1_Cat1 per zone member when membership proven/assigned |
| ES_PI20 AOI calls | `SITE_FORGE_MISSING` | Cookie-cutter: ES_PI20 aggregator per zone (pad NO_ESLS) |
| NOP-only Main_Routine shell | `SITE_FORGE_EXTRA` | Site Forge fail-safe shell when membership UNRESOLVED — correct for UNKNOWN, incorrect once PROVEN_RUN/ENGINEER_ASSIGNED members exist |
| Zone ShippingSorter_ESZone1 | `ENGINEER_MODIFICATION` | Finished PLC6 site zone — do NOT copy into virgin ORINDYAC6 unless RUN proves ShippingSorter membership |
| Zone ShippingSorter_ESZone2 | `ENGINEER_MODIFICATION` | Finished PLC6 site zone — do NOT copy into virgin ORINDYAC6 unless RUN proves ShippingSorter membership |
| Virgin RUN ORINDYAC6 zone shell | `RUN_UNKNOWN` | Virgin RUN discovers ORINDYAC6_ESZone1 with ENGINEER_REQUIRED membership. ShippingSorter zones are finished-PLC site engineering — not RUN-proven here. |

## Classification counts

- `COOKIE_CUTTER_MATCH`: 2
- `ENGINEER_MODIFICATION`: 2
- `RUN_UNKNOWN`: 1
- `SITE_FORGE_EXTRA`: 1
- `SITE_FORGE_MISSING`: 3

## GATE 4 root cause (zone disappearance)

Apply/reopen dropped runDiscovered/provenance on persisted safety_build zones; on session restart AS.runSafetyZones was empty so RUN shells were reclassified AUTO_DEFAULT and deleted, leaving only ENGINEER_CREATED.

## GATE 5 ES fidelity

emit_es_program emits real Safe_Logic/Safe_PI/JSR/ES_SIL1_Cat1/ES_PI20 when zones have PROVEN_RUN or ENGINEER_ASSIGNED members. Current ORINDYAC6 export is NOP shell because generate-time safety_build membership was empty (REVIEW_REQUIRED) — fail-safe, not cookie-cutter copy from finished PLC.

## Legend

- `COOKIE_CUTTER_MATCH` — structural pattern matches library/cookie-cutter ES
- `ENGINEER_MODIFICATION` — finished-site engineering (e.g. ShippingSorter) — not copied
- `RUN_UNKNOWN` — virgin RUN has no proven membership / site mapping
- `SITE_FORGE_MISSING` — expected cookie-cutter structure absent from emit
- `SITE_FORGE_EXTRA` — Site Forge artifact not in oracle (e.g. NOP shell)
