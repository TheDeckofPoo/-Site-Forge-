# PRESENTATION ADDENDUM — Curtis demo 2–3 PM ET

## RECOMMENDED DEMO SHA

**`9e5d470`**

### Why this SHA
Smallest exact candidate that includes:
1. NTP scaffold + spare-output safety (`7f6e575`)
2. Control_Station single-writer (`8f98981`)
3. Ship sorter discovery top card + Area CONVEYORS:0 (`2b2e2a6`)
4. Hub truthfulness: sorter never READY while NOT YET QUALIFIED (`9e5d470`)

**Fallback if tip regresses:** `2b2e2a6`  
**Prod untouched:** `anton/mission-ready` @ `a935a22`  
**DO NOT MERGE. DO NOT retarget Curtis desktop.**

Checkout for Curtis (manual):
```
git fetch origin
git switch demo/reno-ship-sorter-readiness
git checkout 9e5d470
```
Worktree already at: `C:\dev\worktree\FortnaPlus-demo-ship`

---

## DEMO READY

**YES** — for discovery/UI + NTP/spare/Area clarity demo.  
**NO** — for claiming full sorter PLC generation or WCS/Device Comm completeness.

---

## TOP 3 RISKS

1. **Sorter hub / pack language** — if an old workbook still has `plc_generation=PHASE1_SUPPORTED`, Clear/reload RUN before demo so NOT_YET_QUALIFIED policy wins.
2. **MEM_/FUTURE divert rows** — SHIP lane table shows REVIEW (expected). Narrate as truthful, not broken.
3. **Empty Area / Safety** — Area_Test1 with CONVEYORS:0 looks amber by design; do not “fix” by auto-binding conveyors mid-demo.

---

## CURTIS TEST STEPS

### A — PICK (negative sorter + Area/Control Station)
1. Load RUN: `workspace/_reno_peek/20260813-1132-MSCRENO-MSCRENOPICK-RUN/RUN`
2. Confirm **no SHIP SORTER** claimed as primary shipping sorter.
3. Transportation: create/select an Area with **0 conveyors** → see **CONVEYORS: 0** and Safety-does-not-protect-other-Areas note.
4. Optional: open Autogen System / NTP path → expect **CONFIG_REQUIRED** if no site NTP server (not commissioning-ready).

### B — SHIP (primary sorter discovery story)
1. Load RUN: `workspace/_reno_peek/20260813-1132-MSCRENO-MSCRENOSHIP-RUN/RUN`
2. Open **Sorter** tab → top card:
   - Equipment Type **SORTER**
   - Sorter **SHIP SORTER**, Area **SHIPSORTER**
   - Motor / Encoder / Induct populated
   - Lane / divert / I/O / PE / WCS / Review counts
   - Banner: **SORTER PLC GENERATION — NOT YET QUALIFIED**
3. Lane table: Lane / Destination / Divert / Output / Lane Eye / Status / Evidence — no mysterious blanks (UNKNOWN/REVIEW instead).
4. Compile hub pack evidence: Sorter_Track = **DETECTED — NOT YET QUALIFIED** (not INCLUDE READY). WCS = **BLOCKED**.
5. Confirm SHIP SCAN / SHIP SAWTOOTH are **not** the primary sorter identity.

### C — Third unrelated RUN (sibling control)
1. Load RUN: `workspace/_reno_peek/20260813-1132-MSCRENO-MSCRENOPACK-RUN/RUN`
2. Confirm site switches cleanly (no SHIP sorter residue stuck from prior session).
3. Spot-check Transport Area list + Safety zone CONVEYORS count still coherent.
4. Do **not** require sorter PLC generation success on PACK.

---

## DO NOT DEMO list

- Full **Sorter_Track / Area_L3 PLC generation** as “done”
- **WCS PLC generation**
- **Device Comm / CommDiag** live AOI emit
- Claiming **Conv_PE / Conv_PI** complete on Pick without PE_Logic / PI-writer evidence
- **Auto-binding** Safety from a zero-conveyor Area onto other Areas’ conveyors
- Promoting STAGING L5X / “100% READY” language
- Merging demo branch into prod / retargeting Curtis desktop mid-meeting
- Deep toolbar Advanced refactor mid-demo
- Greensboro address / NTP IP copy stories

---

## UI embarrassment checklist (mitigated on tip)

| Item | Status |
|---|---|
| Blank sorter fields | Mitigated — UNKNOWN/REVIEW |
| Sorter INCLUDE (READY) while unqualified | **Fixed on tip** |
| WCS “SiteModel supported” green | Softened → BLOCKED |
| CONVEYORS blank on empty Area | Mitigated — explicit 0 |
| Stale sorter PHASE1 from Apply | Mitigated — no promote over NOT_YET_QUALIFIED |
| Developer geom diag | Already under Advanced details |
