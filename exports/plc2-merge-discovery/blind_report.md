# PLC2 Blind 2:1 Merge Discovery

- Generated: `2026-09-15T06:05:50.785113+00:00`
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
- sourceClassification: `3-1`
- mainLane (logical): `P404`
- inductLane (logical): `P138`
- mainPhysicalRelease: `P404`
- inductPhysicalRelease: `P138`
- inductNext: `None`
- mergeSection1/2/3: `P404` / `P138` / `None`
- downstream: `P406`
- PEs: main=`PE404_P` induct=`PE138_P` jam=`PE406_J`
- area: `None` zone=`3-1 MERGE`
- lane[0] `LANE1_P404`: logical=`P404` presence=`PE404_P` ReleaseIO=`M404` phys=`P404` Next=`None` (—) timer=`tmM406` latch=`M406_AUX`
- lane[1] `LANE2_P138`: logical=`P138` presence=`PE138_P` ReleaseIO=`M138` phys=`P138` Next=`None` (—) timer=`tmM406` latch=`M406_AUX`
- evidence chain (24 facts):
  - `mergeboss`: {"name": "MERGE_406_3-1", "num_inputs": 2, "operable_input": "M406_AUX", "owner": "ORNCCP2", "source_classification": "3-1", "table": "MergeBoss.asc", "valid": "Y"}
  - `mergeinputs_presense`: {"lane": "LANE1_P404", "presense": "PE404_P", "section": "P404", "table": "MergeInputs.asc"}
  - `mergeinputs_releaseio`: {"lane": "LANE1_P404", "release_io": "M404", "section": "P404", "table": "MergeInputs.asc"}
  - `mergeinputs_timer`: {"lane": "LANE1_P404", "sections": ["P402"], "table": "MergeInputs.asc"}
  - `mergeinputs_lane_name`: {"lane": "LANE1_P404", "section": "P404", "table": "MergeInputs.asc"}
  - `mtrchain_merge_ssv`: {"boss_number": "406", "sections": ["P406"], "table": "Mtrchain.asc"}
  - `lane_section_resolution`: {"lane": "LANE1_P404", "score": [5, 3, 0], "section": "P404", "source_count": 3, "sources": ["mergeinputs_lane_name", "mergeinputs_presense", "mergeinputs_releaseio"]}
  - `mergeroute`: {"merge_inputs": "LANE1_P404", "name": "LANE1_P404", "table": "MergeRoute.asc"}
  - `release_io_mtrchain`: {"latch_aux": "M406_AUX", "motor_chained1": "P404", "motor_chained2": "SSVEZPE402_P", "next_conveyor": null, "physical_release_conveyor": "P404", "release_io": "M404", "rule": "ReleaseIO \u2192 Mtrchain.Motor_Name \u2192 Motor_Chained1=physical conveyor; Motor_Chained2=Next when P-tag", "table": "Mtrchain.asc", "timer": "tmM406"}
  - `mergeinputs_presense`: {"lane": "LANE2_P138", "presense": "PE138_P", "section": "P138", "table": "MergeInputs.asc"}
  - `mergeinputs_releaseio`: {"lane": "LANE2_P138", "release_io": "M138", "section": "P138", "table": "MergeInputs.asc"}
  - `mergeinputs_timer`: {"lane": "LANE2_P138", "sections": ["P136", "P136_P2"], "table": "MergeInputs.asc"}

### `MERGE_316_SPUR` — **PROVEN** (HIGH)

- type: `Merge_2to1`
- sourceClassification: `SPUR`
- mainLane (logical): `P136_P1`
- inductLane (logical): `P312`
- mainPhysicalRelease: `P136_P1`
- inductPhysicalRelease: `P314`
- inductNext: `P316`
- mergeSection1/2/3: `P136_P1` / `P312` / `P316`
- downstream: `P136_P2`
- PEs: main=`EZPE136_P1` induct=`PE314_P` jam=`PE316_J`
- area: `None` zone=`MERGE 316`
- lane[0] `LANE1_P136`: logical=`P136_P1` presence=`EZPE136_P1` ReleaseIO=`SSVEZPE136_P1` phys=`P136_P1` Next=`None` (—) timer=`None` latch=`None`
- lane[1] `LANE2_P312`: logical=`P312` presence=`PE314_P` ReleaseIO=`M314` phys=`P314` Next=`P316` (CURVE) timer=`tmLATCH_MERGE_316_A` latch=`LATCH_MERGE_316`
- evidence chain (26 facts):
  - `mergeboss`: {"name": "MERGE_316_SPUR", "num_inputs": 2, "operable_input": "ENABLE_MERGEBOSS_316", "owner": "ORNCCP2", "source_classification": "SPUR", "table": "MergeBoss.asc", "valid": "Y"}
  - `mergeinputs_presense`: {"lane": "LANE1_P136", "presense": "EZPE136_P1", "section": "P136_P1", "table": "MergeInputs.asc"}
  - `mergeinputs_releaseio`: {"lane": "LANE1_P136", "release_io": "SSVEZPE136_P1", "section": "P136_P1", "table": "MergeInputs.asc"}
  - `mergeinputs_timer`: {"lane": "LANE1_P136", "sections": ["P136", "P136_P1"], "table": "MergeInputs.asc"}
  - `mergeinputs_lane_name`: {"lane": "LANE1_P136", "section": "P136", "table": "MergeInputs.asc"}
  - `mtrchain_merge_ssv`: {"boss_number": "316", "sections": ["P136", "P136_P1", "P312", "P314", "P316"], "table": "Mtrchain.asc"}
  - `lane_section_resolution`: {"lane": "LANE1_P136", "score": [7, 4, 1], "section": "P136_P1", "source_count": 4, "sources": ["mergeinputs_presense", "mergeinputs_releaseio", "mergeinputs_timer", "mtrchain_merge_ssv"]}
  - `mergeroute`: {"merge_inputs": "LANE1_P136", "name": "LANE1_P136", "table": "MergeRoute.asc"}
  - `release_io_ssv_or_pe`: {"note": "ReleaseIO is SSV/PE \u2014 no Mtrchain Motor_Chained1/Next path", "release_io": "SSVEZPE136_P1", "section_from_name": "P136_P1", "table": "MergeInputs.asc"}
  - `mergeinputs_presense`: {"lane": "LANE2_P312", "presense": "PE314_P", "section": "P314", "table": "MergeInputs.asc"}
  - `mergeinputs_releaseio`: {"lane": "LANE2_P312", "release_io": "M314", "section": "P314", "table": "MergeInputs.asc"}
  - `mergeinputs_timer`: {"lane": "LANE2_P312", "sections": ["P312"], "table": "MergeInputs.asc"}

### `MERGE_400_2-1` — **PROVEN** (HIGH)

- type: `Merge_2to1`
- sourceClassification: `2-1`
- mainLane (logical): `P242`
- inductLane (logical): `P150_P2`
- mainPhysicalRelease: `P242`
- inductPhysicalRelease: `P150_P2`
- inductNext: `None`
- mergeSection1/2/3: `P242` / `P150_P2` / `None`
- downstream: `P400`
- PEs: main=`EZPE242_P` induct=`EZPE150_P2` jam=`PE400_J`
- area: `None` zone=`2-1 MERGE`
- lane[0] `LANE1_P242`: logical=`P242` presence=`EZPE242_P` ReleaseIO=`SSVEZPE242_P` phys=`P242` Next=`None` (—) timer=`None` latch=`None`
- lane[1] `LANE2_P150_2-1`: logical=`P150_P2` presence=`EZPE150_P2` ReleaseIO=`SSVEZPE150_P2` phys=`P150_P2` Next=`None` (—) timer=`None` latch=`None`
- evidence chain (25 facts):
  - `mergeboss`: {"name": "MERGE_400_2-1", "num_inputs": 2, "operable_input": "M400_AUX", "owner": "ORNCCP2", "source_classification": "2-1", "table": "MergeBoss.asc", "valid": "Y"}
  - `mergeinputs_presense`: {"lane": "LANE1_P242", "presense": "EZPE242_P", "section": "P242", "table": "MergeInputs.asc"}
  - `mergeinputs_releaseio`: {"lane": "LANE1_P242", "release_io": "SSVEZPE242_P", "section": "P242", "table": "MergeInputs.asc"}
  - `mergeinputs_timer`: {"lane": "LANE1_P242", "sections": ["P242"], "table": "MergeInputs.asc"}
  - `mergeinputs_lane_name`: {"lane": "LANE1_P242", "section": "P242", "table": "MergeInputs.asc"}
  - `mtrchain_merge_ssv`: {"boss_number": "400", "sections": ["P150_P2", "P242", "P400"], "table": "Mtrchain.asc"}
  - `lane_section_resolution`: {"lane": "LANE1_P242", "score": [10, 5, 0], "section": "P242", "source_count": 5, "sources": ["mergeinputs_lane_name", "mergeinputs_presense", "mergeinputs_releaseio", "mergeinputs_timer", "mtrchain_merge_ssv"]}
  - `mergeroute`: {"merge_inputs": "LANE1_P242", "name": "LANE1_P242", "table": "MergeRoute.asc"}
  - `release_io_ssv_or_pe`: {"note": "ReleaseIO is SSV/PE \u2014 no Mtrchain Motor_Chained1/Next path", "release_io": "SSVEZPE242_P", "section_from_name": "P242", "table": "MergeInputs.asc"}
  - `mergeinputs_presense`: {"lane": "LANE2_P150_2-1", "presense": "EZPE150_P2", "section": "P150_P2", "table": "MergeInputs.asc"}
  - `mergeinputs_releaseio`: {"lane": "LANE2_P150_2-1", "release_io": "SSVEZPE150_P2", "section": "P150_P2", "table": "MergeInputs.asc"}
  - `mergeinputs_timer`: {"lane": "LANE2_P150_2-1", "sections": ["P150", "P150_P2"], "table": "MergeInputs.asc"}

### `MERGE_324_SPUR` — **PROVEN** (HIGH)

- type: `Merge_2to1`
- sourceClassification: `SPUR`
- mainLane (logical): `P150_P1`
- inductLane (logical): `P320`
- mainPhysicalRelease: `P150_P1`
- inductPhysicalRelease: `P322`
- inductNext: `P324`
- mergeSection1/2/3: `P150_P1` / `P320` / `P324`
- downstream: `P150_P2`
- PEs: main=`EZPE150_P1` induct=`PE322_P` jam=`PE324_J`
- area: `None` zone=`MERGE 324`
- lane[0] `LANE1_P150_SPUR`: logical=`P150_P1` presence=`EZPE150_P1` ReleaseIO=`SSVEZPE150_P1` phys=`P150_P1` Next=`None` (—) timer=`None` latch=`None`
- lane[1] `LANE2_P320`: logical=`P320` presence=`PE322_P` ReleaseIO=`M322` phys=`P322` Next=`P324` (CURVE) timer=`tmLATCH_MERGE_324_A` latch=`LATCH_MERGE_324`
- evidence chain (26 facts):
  - `mergeboss`: {"name": "MERGE_324_SPUR", "num_inputs": 2, "operable_input": "ENABLE_MERGEBOSS_324", "owner": "ORNCCP2", "source_classification": "SPUR", "table": "MergeBoss.asc", "valid": "Y"}
  - `mergeinputs_presense`: {"lane": "LANE1_P150_SPUR", "presense": "EZPE150_P1", "section": "P150_P1", "table": "MergeInputs.asc"}
  - `mergeinputs_releaseio`: {"lane": "LANE1_P150_SPUR", "release_io": "SSVEZPE150_P1", "section": "P150_P1", "table": "MergeInputs.asc"}
  - `mergeinputs_timer`: {"lane": "LANE1_P150_SPUR", "sections": ["P150", "P150_P1"], "table": "MergeInputs.asc"}
  - `mergeinputs_lane_name`: {"lane": "LANE1_P150_SPUR", "section": "P150", "table": "MergeInputs.asc"}
  - `mtrchain_merge_ssv`: {"boss_number": "324", "sections": ["P150", "P150_P1", "P320", "P322", "P324"], "table": "Mtrchain.asc"}
  - `lane_section_resolution`: {"lane": "LANE1_P150_SPUR", "score": [7, 4, 1], "section": "P150_P1", "source_count": 4, "sources": ["mergeinputs_presense", "mergeinputs_releaseio", "mergeinputs_timer", "mtrchain_merge_ssv"]}
  - `mergeroute`: {"merge_inputs": "LANE1_P150_SPUR", "name": "LANE1_P150_SPUR", "table": "MergeRoute.asc"}
  - `release_io_ssv_or_pe`: {"note": "ReleaseIO is SSV/PE \u2014 no Mtrchain Motor_Chained1/Next path", "release_io": "SSVEZPE150_P1", "section_from_name": "P150_P1", "table": "MergeInputs.asc"}
  - `mergeinputs_presense`: {"lane": "LANE2_P320", "presense": "PE322_P", "section": "P322", "table": "MergeInputs.asc"}
  - `mergeinputs_releaseio`: {"lane": "LANE2_P320", "release_io": "M322", "section": "P322", "table": "MergeInputs.asc"}
  - `mergeinputs_timer`: {"lane": "LANE2_P320", "sections": ["P320"], "table": "MergeInputs.asc"}

## Firewall

- finished_l5x_read: `False`
- hardcoded_merge_names: `False`
- tables_read: Conveyor, MergeBoss, MergeInputs, MergeRoute, MergeRunOutputs, Mtrchain, Jamcheck, Fulljam, Fullline, Configio, FORTNADT, Stop

STOP — discovery artifact only; no AOI/L5X generation.
