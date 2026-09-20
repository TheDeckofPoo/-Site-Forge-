# Atlanta Field-Stabilization Pass

**Baseline:** `29f3d48`  
**Field L5X evidence (validation only):** `exports/current/MSCATL_CP3_2026_09_20_1706.L5X`

## Root causes

### Safety assignment loss
GUI showed ENGINEER ASSIGNED≈13 for `Area_1_Test_ESZone1`, but Autogen consumed
`safety_build.source = "transport_engineer"` with `members: []`.

Disappearance boundary: **live/draft Safety members → persisted Autogen handoff**.

Causes:
1. Generate path preferred hollow `mem.safety_build` over draft/`autogenState.safety_build`.
2. Apply Safety rebuilt the client model before snapshotting members.
3. Transport Apply reload could re-authoritize a hollow shell.

ES compiler behaved correctly given empty members (NOP shell).

### P3012A loss
Discovery + `merges_2to1` kept `P3012A` (`lanes: 3`).  
Autogen emit skipped `if lane_n > 2: continue` — generalized handoff bug, not Atlanta special-case.

## Fixes (this pass)
- Safety prefer/draft/parity gate + Apply snapshot/verify confirmation
- Safety document-style scroll, required-role panel, category grouping retained
- I/O: UNCLAIMED/SPARE ≠ UNRESOLVED OWNER; OW8 → 7/8; Spare map checkbox semantics
- Transport Lite: thicker ordinary belts + ~2× merge girth; far-zoom label LOD
- Autogen: emit N≥2 merges; preserve lettered discharge identity (`P3012A_Merge`)
- Qual runner: stringify dict details; isolation leak boolean polarity

## Atlanta backend still green
- 3 racks / 23 slotted / 0 unplaced
- 256/256 PROVEN / 0 needs_resolution / conservation PASS

## GUI launch
```powershell
cd C:\dev\worktree\FortnaPlus\desktop
.\Launch-SiteForge.bat
```

Then Curtis: Clear/reload Atlanta → Apply Safety → verify persistence banner → Build PLC → inspect ES + P3012A.
Then STOP for virgin site manual test.
