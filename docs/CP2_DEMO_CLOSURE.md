# CP2 Demo Closure — Evidence Pack Summary

**Generated (UTC):** 2026-09-12T06:46:06.541398+00:00  
**Branch intent:** demo-closure pack for `ORNCCP2` from CURRENT RUN  
**Active RUN:** `workspace\active\RUN`  
**Output:** `exports\cp2-demo-closure`

## Binding philosophy

- **CURRENT RUN** = generation source truth.
- **ENGINEER EDITS** = authoritative corrections.
- **FINISHED PLC** = validation observation only — never a target.
- Do not repair missing Area / ES / PE / topology from finished PLC.
- Do not treat `ORNCCP2_Imported_ESZone1` as confirmed.
- Do not downgrade RUN realization because an old PLC contained 57 conveyors.

## Transport Build demo UX (this branch)

Normal view = **clean schematic** (not geometry-debug).

Workflow strip:

`Import RUN → Auto Build → Review / Correct → Apply to Autogen → Build PLC`

| Control | Role |
|---------|------|
| **Fit** | Single primary fit of the visible working set |
| Fit All / Site / Area | Advanced / Fit menu only |
| Geometry debug / layers | **Advanced** only |
| **Apply to Autogen** | Persists **canonical** topology/Area/ES/PE only — presentation/debug excluded |
| **Build PLC** | Appears after Apply; opens PLC Autogen Export L5X |

Stacked bodies may get presentation-only lane separation; raw RUN coordinates are never modified.

## What this pack answers

1. Which RUN mechanical conveyors Site Forge automatically realizes vs needs engineer confirmation.
2. PE Full/Jam/Exit/Add provenance (RUN_EXPLICIT / RUN_DERIVED / ENGINEER_CONFIGURED / DEFAULT / UNKNOWN).
3. How little Area/ES is recoverable from RUN.
4. Physical overlap classes (no auto-spreading).
5. Remaining engineering work in plain terms.

## Headline numbers

| Metric | Value |
|---|---|
| RUN equipment discovered | 65 |
| Site Forge supported | 65 |
| Automatically realized | 31 |
| Engineer confirmation required | 33 |
| Unsupported | 0 |
| Ignored | 1 |
| Generated Full_PE | 11 |
| Generated PE_Logic | 66 |
| Finished Full_PE (observation only) | 7 |
| Finished PE_Logic (observation only) | 30 |
| AREA REQUIRED | 65 |
| ES ZONE REQUIRED | 65 |

## Remaining work

- **64 conveyors need topology**
- **65 need Area**
- **65 need ES Zone**
- **19 PE roles need confirmation**
- **0 unsupported equipment items**

- Topology: 64
- Area: 65
- ES Zone: 65
- PE roles: 19
- Unsupported: 0

## CLI

```
python tools/scripts/fortna_cp2_demo_closure.py \
  --run-dir workspace/active/RUN --machine ORNCCP2 --out exports/cp2-demo-closure
```

Fresh L5X: `exports\cp2-demo-closure\generated\OReillyGreensboro_ORNCCP2.L5X`

## Related

- `docs/CP2_COMPLETION_GATE.md` — broader completion-gate inventories
- `docs/SOURCE_OF_TRUTH_POLICY.md` — binding input / validation barrier
