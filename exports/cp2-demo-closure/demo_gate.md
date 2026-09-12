# CP2 Demo Closure — Greensboro ORNCCP2

**Generated (UTC):** 2026-09-12T06:46:06.540602+00:00
**Active RUN:** `workspace\active\RUN`
**Machine:** ORNCCP2
**Generated L5X:** `exports\cp2-demo-closure\generated\OReillyGreensboro_ORNCCP2.L5X`

## Philosophy

| Source | Role |
|--------|------|
| **CURRENT RUN** | Generation source truth |
| **FINISHED PLC** | Validation observation only — never a target |

Do **not** repair gaps by copying finished PLC areas, ES zones, PE roles, or conveyor sets.

## Artifact index

| File | Purpose |
|---|---|
| `run_realization.json` | Mechanical conveyor realization status |
| `pe_realization.json` | Full_PE / PE_Logic provenance + evidence |
| `area_es_status.json` | Area / ES recoverability from RUN |
| `overlap_classification.json` | Physical geometry overlap classes |
| `remaining_work.json` | Engineering remaining-work counts |
| `demo_gate.md` | This narrative |
| `generated/` | Fresh Autogen L5X from RUN + workbook |

## Run realization

- RUN equipment discovered (Autogen ∪ CP2_CONFIRMED/CANDIDATE): **65**
- Site Forge supported: **65**
- Automatically realized: **31**
- Engineer confirmation required: **33**
- Unsupported: **0**
- Ignored: **1**

Finished PLC Fast_Conv=57 is a **validation observation**, not a realization target.

## PE realization

- Generated Full_PE calls: **11**
- Generated PE_Logic calls: **66**
- Insufficient RUN/engineer evidence flags: **38**
- Finished PLC observation (not a target): Full_PE **7**, PE_Logic **30**

## Area / ES status

- RUN Area/ES recoverability: **little**
- AREA REQUIRED: **65**
- ES ZONE REQUIRED: **65**
- `ORNCCP2_Imported_ESZone1` is **not** confirmed.

## Overlap classification

| Class | Count |
|---|---|
| SAME_PHYSICAL_EQUIPMENT | 0 |
| PARALLEL_EQUIPMENT | 1 |
| PARENT_CHILD | 0 |
| VALID_OVERLAP | 3 |
| SUSPECT_GEOMETRY | 0 |
| UNKNOWN | 9 |

## Remaining work

- 64 conveyors need topology
- 65 need Area
- 65 need ES Zone
- 19 PE roles need confirmation
- 0 unsupported equipment items

- Topology: **64**
- Area: **65**
- ES Zone: **65**
- PE role confirmations: **19**
- Unsupported equipment: **0**

## Generate workflow

```
fortna_workbook.py build --merge-existing  # RUN + engineer edits only
fortna_autogen.py from-run --workbook ... --library OReilly_Library_v3.L5X
```

No finished-PLC seeding.

## Orchestrator

```
python tools/scripts/fortna_cp2_demo_closure.py \
  --run-dir workspace/active/RUN --machine ORNCCP2 --out exports/cp2-demo-closure
```

## Autogen report snapshot

- conveyor_count: 37
- pe_logic_rungs: 44
- areas_summary: {'ORNCCP2_Area': 37}
