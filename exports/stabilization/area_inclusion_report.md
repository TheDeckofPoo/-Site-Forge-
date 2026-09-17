# PL-7 — Area Inclusion Report

Generated against current `exports/current/autogen_input.json` and workbook.

## Rule

Do **NOT** delete engineer-created Areas by naming heuristic (`test*`).
Only ACTIVE + INCLUDED Areas generate program packs per canonical model.

## Current Areas in autogen_input

| Area ID / name | Conveyors | Source (best evidence) | Engineer-created? | Included in compile? | Why |
|----------------|----------:|------------------------|-------------------|----------------------|-----|
| `ORNCCP2_Area` | 73 | Transport Apply / RUN default area | No (site default) | YES | Present in `areas[]` + conveyors.main_area |
| `test1` | 4 | Transport Build Area assignment (Curtis session) | YES (session Area) | YES | Present in `areas[]` + 4 conveyors assigned |

## Safety zones paired

| Zone | Area | Notes |
|------|------|-------|
| `ORNCCP2_ESZone1` | `ORNCCP2_Area` | Membership UNRESOLVED in last shell emit |
| `test1_ESZone1` | `test1` | Membership UNRESOLVED in last shell emit |

## Prior pollution note

Earlier build had `test11111_Area_*` packs — that was an engineer-created Area name from a prior session, not an automatic test fixture. Current input uses `test1` (4 conveyors: P138, P222, P404, P406).

## Compiler inclusion contract

`fortna_autogen` emits Area Fast/Slow/L1/L2 for every name in `AutogenInput.areas` that has conveyors. There is no `included=false` flag on those strings today — presence in `areas` **is** inclusion.

To exclude an Area from PLC generation: remove it from Transport Apply / autogen areas (or leave zero conveyors). Do not use name heuristics.
