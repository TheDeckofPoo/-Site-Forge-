# PLC2 Blind 2:1 Merge Discovery

- Generated: `2026-09-14T04:39:45.035599+00:00`
- Machine: `ORNCCP2`
- RUN: `C:\dev\worktree\FortnaPlus\workspace\_plc2_run_peek\RUN`
- Source: RUN tables only — MergeBoss/MergeInputs/MergeRoute/Mtrchain/Jamcheck/Fulljam/Fullline/Conveyor; finished PLC L5X not read

## Counts

| Class | Count |
|-------|------:|
| PROVEN | 4 |
| CANDIDATE | 0 |
| UNRESOLVED | 0 |
| Total | 4 |
| Topology indegree==2 | 2 |

## Merges

### `MERGE_406_3-1` — **PROVEN** (HIGH)

- type: `Merge_2to1`
- mainLane: `P404`
- inductLane: `P138`
- mergeSection1/2/3: `P404` / `P138` / `None`
- downstream: `P406`
- PEs: main=`PE404_P` induct=`PE138_P` jam=`PE406_J`
- area: `None` zone=`3-1 MERGE`
- evidence chain (22 facts):
  - `mergeboss`: {"name": "MERGE_406_3-1", "num_inputs": 2, "operable_input": "M406_AUX", "owner": "ORNCCP2", "table": "MergeBoss.asc", "valid": "Y"}
  - `mergeinputs_presense`: {"lane": "LANE1_P404", "presense": "PE404_P", "section": "P404", "table": "MergeInputs.asc"}
  - `mergeinputs_releaseio`: {"lane": "LANE1_P404", "release_io": "M404", "section": "P404", "table": "MergeInputs.asc"}
  - `mergeinputs_timer`: {"lane": "LANE1_P404", "sections": ["P402"], "table": "MergeInputs.asc"}
  - `mergeinputs_lane_name`: {"lane": "LANE1_P404", "section": "P404", "table": "MergeInputs.asc"}
  - `mtrchain_merge_ssv`: {"boss_number": "406", "sections": ["P406"], "table": "Mtrchain.asc"}
  - `lane_section_resolution`: {"lane": "LANE1_P404", "score": [5, 3, 0], "section": "P404", "source_count": 3, "sources": ["mergeinputs_lane_name", "mergeinputs_presense", "mergeinputs_releaseio"]}
  - `mergeroute`: {"merge_inputs": "LANE1_P404", "name": "LANE1_P404", "table": "MergeRoute.asc"}
  - `mergeinputs_presense`: {"lane": "LANE2_P138", "presense": "PE138_P", "section": "P138", "table": "MergeInputs.asc"}
  - `mergeinputs_releaseio`: {"lane": "LANE2_P138", "release_io": "M138", "section": "P138", "table": "MergeInputs.asc"}
  - `mergeinputs_timer`: {"lane": "LANE2_P138", "sections": ["P136", "P136_P2"], "table": "MergeInputs.asc"}
  - `mergeinputs_lane_name`: {"lane": "LANE2_P138", "section": "P138", "table": "MergeInputs.asc"}

### `MERGE_316_SPUR` — **PROVEN** (HIGH)

- type: `Merge_2to1`
- mainLane: `P136_P1`
- inductLane: `P312`
- mergeSection1/2/3: `P136_P1` / `P312` / `P316`
- downstream: `P136_P2`
- PEs: main=`EZPE136_P1` induct=`PE314_P` jam=`PE316_J`
- area: `None` zone=`MERGE 316`
- evidence chain (23 facts):
  - `mergeboss`: {"name": "MERGE_316_SPUR", "num_inputs": 2, "operable_input": "ENABLE_MERGEBOSS_316", "owner": "ORNCCP2", "table": "MergeBoss.asc", "valid": "Y"}
  - `mergeinputs_presense`: {"lane": "LANE1_P136", "presense": "EZPE136_P1", "section": "P136_P1", "table": "MergeInputs.asc"}
  - `mergeinputs_releaseio`: {"lane": "LANE1_P136", "release_io": "SSVEZPE136_P1", "section": "P136_P1", "table": "MergeInputs.asc"}
  - `mergeinputs_timer`: {"lane": "LANE1_P136", "sections": ["P136", "P136_P1"], "table": "MergeInputs.asc"}
  - `mergeinputs_lane_name`: {"lane": "LANE1_P136", "section": "P136", "table": "MergeInputs.asc"}
  - `mtrchain_merge_ssv`: {"boss_number": "316", "sections": ["P136", "P136_P1", "P312", "P314", "P316"], "table": "Mtrchain.asc"}
  - `lane_section_resolution`: {"lane": "LANE1_P136", "score": [7, 4, 1], "section": "P136_P1", "source_count": 4, "sources": ["mergeinputs_presense", "mergeinputs_releaseio", "mergeinputs_timer", "mtrchain_merge_ssv"]}
  - `mergeroute`: {"merge_inputs": "LANE1_P136", "name": "LANE1_P136", "table": "MergeRoute.asc"}
  - `mergeinputs_presense`: {"lane": "LANE2_P312", "presense": "PE314_P", "section": "P314", "table": "MergeInputs.asc"}
  - `mergeinputs_releaseio`: {"lane": "LANE2_P312", "release_io": "M314", "section": "P314", "table": "MergeInputs.asc"}
  - `mergeinputs_timer`: {"lane": "LANE2_P312", "sections": ["P312"], "table": "MergeInputs.asc"}
  - `mergeinputs_lane_name`: {"lane": "LANE2_P312", "section": "P312", "table": "MergeInputs.asc"}

### `MERGE_400_2-1` — **PROVEN** (HIGH)

- type: `Merge_2to1`
- mainLane: `P242`
- inductLane: `P150_P2`
- mergeSection1/2/3: `P242` / `P150_P2` / `None`
- downstream: `P400`
- PEs: main=`EZPE242_P` induct=`EZPE150_P2` jam=`PE400_J`
- area: `None` zone=`2-1 MERGE`
- evidence chain (23 facts):
  - `mergeboss`: {"name": "MERGE_400_2-1", "num_inputs": 2, "operable_input": "M400_AUX", "owner": "ORNCCP2", "table": "MergeBoss.asc", "valid": "Y"}
  - `mergeinputs_presense`: {"lane": "LANE1_P242", "presense": "EZPE242_P", "section": "P242", "table": "MergeInputs.asc"}
  - `mergeinputs_releaseio`: {"lane": "LANE1_P242", "release_io": "SSVEZPE242_P", "section": "P242", "table": "MergeInputs.asc"}
  - `mergeinputs_timer`: {"lane": "LANE1_P242", "sections": ["P242"], "table": "MergeInputs.asc"}
  - `mergeinputs_lane_name`: {"lane": "LANE1_P242", "section": "P242", "table": "MergeInputs.asc"}
  - `mtrchain_merge_ssv`: {"boss_number": "400", "sections": ["P150_P2", "P242", "P400"], "table": "Mtrchain.asc"}
  - `lane_section_resolution`: {"lane": "LANE1_P242", "score": [10, 5, 0], "section": "P242", "source_count": 5, "sources": ["mergeinputs_lane_name", "mergeinputs_presense", "mergeinputs_releaseio", "mergeinputs_timer", "mtrchain_merge_ssv"]}
  - `mergeroute`: {"merge_inputs": "LANE1_P242", "name": "LANE1_P242", "table": "MergeRoute.asc"}
  - `mergeinputs_presense`: {"lane": "LANE2_P150_2-1", "presense": "EZPE150_P2", "section": "P150_P2", "table": "MergeInputs.asc"}
  - `mergeinputs_releaseio`: {"lane": "LANE2_P150_2-1", "release_io": "SSVEZPE150_P2", "section": "P150_P2", "table": "MergeInputs.asc"}
  - `mergeinputs_timer`: {"lane": "LANE2_P150_2-1", "sections": ["P150", "P150_P2"], "table": "MergeInputs.asc"}
  - `mergeinputs_lane_name`: {"lane": "LANE2_P150_2-1", "section": "P150", "table": "MergeInputs.asc"}

### `MERGE_324_SPUR` — **PROVEN** (HIGH)

- type: `Merge_2to1`
- mainLane: `P150_P1`
- inductLane: `P320`
- mergeSection1/2/3: `P150_P1` / `P320` / `P324`
- downstream: `P150_P2`
- PEs: main=`EZPE150_P1` induct=`PE322_P` jam=`PE324_J`
- area: `None` zone=`MERGE 324`
- evidence chain (23 facts):
  - `mergeboss`: {"name": "MERGE_324_SPUR", "num_inputs": 2, "operable_input": "ENABLE_MERGEBOSS_324", "owner": "ORNCCP2", "table": "MergeBoss.asc", "valid": "Y"}
  - `mergeinputs_presense`: {"lane": "LANE1_P150_SPUR", "presense": "EZPE150_P1", "section": "P150_P1", "table": "MergeInputs.asc"}
  - `mergeinputs_releaseio`: {"lane": "LANE1_P150_SPUR", "release_io": "SSVEZPE150_P1", "section": "P150_P1", "table": "MergeInputs.asc"}
  - `mergeinputs_timer`: {"lane": "LANE1_P150_SPUR", "sections": ["P150", "P150_P1"], "table": "MergeInputs.asc"}
  - `mergeinputs_lane_name`: {"lane": "LANE1_P150_SPUR", "section": "P150", "table": "MergeInputs.asc"}
  - `mtrchain_merge_ssv`: {"boss_number": "324", "sections": ["P150", "P150_P1", "P320", "P322", "P324"], "table": "Mtrchain.asc"}
  - `lane_section_resolution`: {"lane": "LANE1_P150_SPUR", "score": [7, 4, 1], "section": "P150_P1", "source_count": 4, "sources": ["mergeinputs_presense", "mergeinputs_releaseio", "mergeinputs_timer", "mtrchain_merge_ssv"]}
  - `mergeroute`: {"merge_inputs": "LANE1_P150_SPUR", "name": "LANE1_P150_SPUR", "table": "MergeRoute.asc"}
  - `mergeinputs_presense`: {"lane": "LANE2_P320", "presense": "PE322_P", "section": "P322", "table": "MergeInputs.asc"}
  - `mergeinputs_releaseio`: {"lane": "LANE2_P320", "release_io": "M322", "section": "P322", "table": "MergeInputs.asc"}
  - `mergeinputs_timer`: {"lane": "LANE2_P320", "sections": ["P320"], "table": "MergeInputs.asc"}
  - `mergeinputs_lane_name`: {"lane": "LANE2_P320", "section": "P320", "table": "MergeInputs.asc"}

## Firewall

- finished_l5x_read: `False`
- hardcoded_merge_names: `False`
- tables_read: Conveyor, MergeBoss, MergeInputs, MergeRoute, MergeRunOutputs, Mtrchain, Jamcheck, Fulljam, Fullline, Configio, FORTNADT, Stop

STOP — discovery artifact only; no AOI/L5X generation.
