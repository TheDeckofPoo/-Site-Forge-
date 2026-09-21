# Atlanta P3000–P3012 Floating Geometry — Evidence Only

**Site / machine:** MSCATL_CP3  
**RUN:** `workspace/_mscatl_peek/MSCATL_CP3/RUN`  
**Source table:** `FORTNA/Conveyor.asc`  
**Layout extract:** `workspace/_mscatl_peek/MSCATL_CP3/_run_physical_layout_tmp/`  
**Policy:** Do not invent belt path. Do not move. Classify from raw geometry evidence only.

## Overall classification

**LEGITIMATE_SHORT_CONVEYORS_SPATIALLY_ISOLATED**

All seven tags have complete usable conveyor-line geometry in RUN (`Length=200`, `Angle=90`, `Type=STRAIGHT`). They are **not** zero-length, **not** missing length/orientation, and **not** point-only. They sit in a tight Y-cluster ~8240 units north of their powered A-siblings, with `Width=400 > Length=200`, `Default Colors=GRAVITY`, `In Motor Chain=N`, no motors, and **zero** geometric connection candidates — which matches Curtis’s isolated upper-left stub/arrowhead appearance.

**Render directive:** short STRAIGHT segments at source coordinates. **DO NOT MOVE.** Functional role remains **REVIEW**.

## Diagnostic table

| Tag | X | Y | Orient° | Length | Width | Start → End | Source | Machine | Confidence | Classification |
|-----|---|---|---------|--------|-------|-------------|--------|---------|------------|----------------|
| P3000 | 55730.408 | 159286.607 | 90 | 200 | 400 | (55730.408,159286.607)→(55730.408,159486.607) | Conveyor.asc | MSCATL_CP3 (Machine_Name blank) | HIGH | short STRAIGHT, isolated; DO NOT MOVE |
| P3002 | 58530.408 | 159286.607 | 90 | 200 | 400 | (58530.408,159286.607)→(58530.408,159486.607) | Conveyor.asc | MSCATL_CP3 (Machine_Name blank) | HIGH | short STRAIGHT, isolated; DO NOT MOVE |
| P3004 | 63230.408 | 159286.605 | 90 | 200 | 400 | (63230.408,159286.605)→(63230.408,159486.605) | Conveyor.asc | MSCATL_CP3 (Machine_Name blank) | HIGH | short STRAIGHT, isolated; DO NOT MOVE |
| P3006 | 66030.408 | 159286.605 | 90 | 200 | 400 | (66030.408,159286.605)→(66030.408,159486.605) | Conveyor.asc | MSCATL_CP3 (Machine_Name blank) | HIGH | short STRAIGHT, isolated; DO NOT MOVE |
| P3008 | 70230.408 | 159286.605 | 90 | 200 | 400 | (70230.408,159286.605)→(70230.408,159486.605) | Conveyor.asc | MSCATL_CP3 (Machine_Name blank) | HIGH | short STRAIGHT, isolated; DO NOT MOVE |
| P3010 | 73030.408 | 159286.605 | 90 | 200 | 400 | (73030.408,159286.605)→(73030.408,159486.605) | Conveyor.asc | MSCATL_CP3 (Machine_Name blank) | HIGH | short STRAIGHT, isolated; DO NOT MOVE |
| P3012 | 75830.408 | 159286.605 | 90 | 200 | 400 | (75830.408,159286.605)→(75830.408,159486.605) | Conveyor.asc | MSCATL_CP3 (Machine_Name blank) | HIGH | short STRAIGHT, isolated; DO NOT MOVE |

## What was ruled out

| Hypothesis | Verdict | Evidence |
|------------|---------|----------|
| Zero-length | No | `Length=200` on every row |
| Missing length/orientation | No | Angle=90 and Length=200 present |
| Point / incomplete geometry | No | Valid 200-unit vertical path; `geometry_issues=[]` |
| Malformed render path | No | Layout extract path is move→line along +Y |
| Duplicate-secondary of A-siblings | No | Distinct `IO_Name` rows; A-siblings at different XY/Angle/Length |
| Coordinate-space mismatch | No | Same RUN X/Y space as A-line; just displaced in Y |

## Key raw evidence

Shared Conveyor.asc traits for P3000…P3012:

- `Type=STRAIGHT`, `Angle=90`, `Length=200`, `Width=400`
- `Default Colors=GRAVITY`, `In Motor Chain=N`, `NoseOver=Double Noseover`
- `Inside_Radius=Infeed_Tangent=Discharge_Tangent=1878` (filled but Type remains STRAIGHT)
- No motors; no connection candidates in `MSCATL_CP3_connection_candidates.json`

A-sibling contrast (example):

- `P3000A`: (75833.289, 151348.5), Angle=0, Length=7669.583, ZEROPRESSURE, motor M3000, `CONV_RUNNING`
- `P3012A` (distinct discharge row, not P3012): (73468.417, 151043.923), Length=1400, Width=850

MergeInputs presence names `PE3010_P` / `PE3006_P` / `PE3002_P` under boss `3-1 Recirc Merge` associate those photoeyes with the recirc merge; that does **not** authorize relocating P3000–P3012 geometry onto the A-line.

## Render instruction

Render each as a **short STRAIGHT** at source X/Y/orientation/length.  
If a future consumer cannot use Width>Length stubs, still keep the coordinate — do **not** invent a belt path and do **not** move onto A-siblings. Flag **REVIEW** for functional role only.
