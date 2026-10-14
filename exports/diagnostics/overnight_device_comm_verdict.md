# Phase 8 — Device Comm Contract Verdict

**Date:** overnight presentation sprint  
**Branch:** `demo/reno-ship-sorter-readiness`  
**START SHA:** `a935a22`

## Verdict

**DO NOT IMPLEMENT CommDiag_UDT / live AOI_CommDiag group scheduling on this demo branch.**

Device Comms remains **REVIEW_REQUIRED** when `CommDiag_UDT` is absent from the approved generic library (`OReilly_Library_v3`).

## Evidence

Finished Greensboro PLC2 / PLC4 / PLC5 use:

| Element | Greensboro finished PLCs | Approved library (`OReilly_Library_v3`) |
|---|---|---|
| `CommDiag_UDT` | Present | **ABSENT** |
| `CommsDiag_GroupN` | Present | Clone-only if Group1 exists; no approved type |
| `AOI_CommDiag(...)` | Present | AOI may exist; InOut contract needs CommDiag_UDT |
| `GET_Firmware` / `GET_MACID` | Present | Support tags may exist |
| `MACID_Bytes` / `Firmware_Bytes` | Present | Support tags may exist |
| `DeviceInfo_Read` | Present | Support tags may exist |
| `NO_CommDev` | Present | Emit path can synthesize Comm_UDT stub |

Production emit path (`_build_sys_comm_program_xml`):

- `has_commdiag_udt = "CommDiag_UDT" in library_text`
- When false → Devices_Comm_Logic emits **NOP + REVIEW_REQUIRED (PD-0029)**
- Explicit comment: *never reconstruct finished-site CommDiag_UDT layout inline*

## Remaining gap (exact)

1. **Datatype contract** — `CommDiag_UDT` must be promoted into the approved generic library (layout owned by library authority, not transplanted from Greensboro binary UDT).
2. **AOI/instruction contract** — confirm `AOI_CommDiag` parameter order and LocalTags against library once datatype lands.
3. **Group scheduling** — `CommsDiag_GroupN.Index` / IndexMax / Init must have an approved generic template (not finished-site EQU/MOV cookie-cut).
4. **Module binding** — 4th AOI arg must remain MODULE name (never `*_Comm` Comm_UDT); needs generic module inventory binding rules already partially present.

Until all four are proven generically: **Device Comm = REVIEW_REQUIRED / deferred.**

## Forbidden shortcuts checked

- No Greensboro CommDiag_UDT binary transplant — **PASS**
- No fake green Device Comms without datatype — **PASS**
- No site-specific `if site == Greensboro` — **PASS**
