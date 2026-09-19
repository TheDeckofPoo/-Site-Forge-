# Safety × Sorter Integration Trace

**Field fail:** `ORINDYAC6_2026_09_19_1027.L5X`  
**Prior pass:** `ORINDYAC6_2026_09_19_0905.L5X` (12 members → Safe_Logic/Safe_PI)

## First failed boundary

`dashboard/fortna-plus.js` — Sorter Apply workbook merge (~L7525):

```js
safety_build: mem.safety_build || disk.safety_build || null,
```

## Root cause

1. **Dual state:** `safety-build.js` writes `window.autogenState`; Sorter Apply reads lexical `autogenState` still holding Transport’s hollow shell (`source: transport_engineer`, `members: []`).
2. **Truthy hollow wins:** empty-member `mem.safety_build` beats disk Safety Apply (`appliedAt` + 12 members).
3. **Landmine:** `fortna_transport_graph.py` can overwrite `wb.safety_build` with Transport shells.

ES compiler correctly refuse-to-invent → fail-safe shell.

## Fix plan

- Unify `window.autogenState = autogenState`
- Sorter Apply: `_unionSafetyBuild` / prefer appliedAt + members
- Transport: never replace zones with members/appliedAt
- Stable `source_id` for zones
- Default/Unassigned never operational
- Area_L3 full divert-family remap
- Qualification runner detects CROSS_SUBSYSTEM_STATE_REGRESSION
