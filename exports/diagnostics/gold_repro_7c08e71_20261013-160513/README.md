# Gold repro — Curtis live project @ 7c08e71

Captured **read-only** before P0 canonical cross-tab truth repair.
**Do not clear** Curtis project to recreate — this snapshot preserves the disagreement.

## Proven disagreement

| Surface | Observation |
|---|---|
| Safety Build | Area_Test1 / Area_Test1_ESZone1 · Assigned 4 · E-Stops 3 · ESLS 1 · members ESPB2,ESPB24,ESPB32,ESLS2 · survives Apply / tab / restart |
| Compile Hub after Refresh site config | Area READY · **E-Stops UNRESOLVED · ESLS UNRESOLVED** (false) |
| I/O & Prints Workbench | ~0 unresolved · SOURCE 100% · PHYSICAL 100% |
| Compile Hub Hardware | DETECTED REVIEW · 17 unresolved owners · 116/118 IO mapped |

## Authoritative artifacts in this snapshot

- `workspace/autogen_workbook.json` — `safety_build.zones[0]` with `eStops` / `eslsDevices`
- `workspace/io_canonical_escalation_snapshot.json` — FOREIGN_CONTROLLER / MSCRENOSHIP for Ship devices
- `plc2-safety/safety_model_MSCRENOPICK.json` — engineer-assigned locals; foreign stamped UNKNOWN_OWNER (defect)
- `workspace/active-meta.json` — MSCRENOPICK RUN identity
- `desktop/.runtime_build.json` — runtime provenance

## Regression

`tests/ui/test_compile_hub_safety_diagnostics.js` loads this workbook and asserts
Compile Hub diagnostics report **E-Stops: 3 RESOLVED · ESLS: 1 RESOLVED**.
