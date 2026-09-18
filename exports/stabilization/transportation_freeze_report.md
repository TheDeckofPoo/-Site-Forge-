# Transportation Freeze Report (ORNCCP2)

- Generated: `2026-09-18T01:10:43.373956+00:00`
- Machine: `ORNCCP2`
- RUN: `C:\Users\curtiskricke\SiteForge\workspace\active\RUN`
- CP4 evidence source: `C:\dev\worktree\FortnaPlus\workspace\active\decoder\cp4-merge-active.json`
- Helpers: `fortna_plc2_merge_discovery`, `fortna_asc` / table merge, `fortna_semantics.merge` / `mtrchain` (when available)
- Policy: RUN-proven only — no invented merge identities or lanes

## Result

**PASS** — 53 passed / 0 failed

## Encoded freeze assertions

### MergeBoss identities
- `MERGE_406_3-1` (type `3-1`)
- `MERGE_316_SPUR` (type `SPUR`)
- `MERGE_400_2-1` (type `2-1`)
- `MERGE_324_SPUR` (type `SPUR`)

### MergeInputs lanes
- `MERGE_406_3-1`: `LANE1_P404`, `LANE2_P138`
- `MERGE_316_SPUR`: `LANE1_P136`, `LANE2_P312`
- `MERGE_400_2-1`: `LANE1_P242`, `LANE2_P150_2-1`
- `MERGE_324_SPUR`: `LANE1_P150_SPUR`, `LANE2_P320`

### MERGE_316 chain
- LANE1_P136 Presence `EZPE136_P1` ReleaseIO `SSVEZPE136_P1`
- LANE2_P312 Presence `PE314_P` ReleaseIO `M314`
- M314 Motor_Ndx `M314` Motor_Chained1 `P314` Motor_Aux `LATCH_MERGE_316` Enabled `M136_AUX`
- Physical chain `M314 -> P314 -> P316 CURVE`

### MERGE_324 chain (when evidence available)
- LANE1_P150_SPUR Presence `EZPE150_P1` ReleaseIO `SSVEZPE150_P1`
- LANE2_P320 Presence `PE322_P` ReleaseIO `M322`
- M322 Motor_Ndx `M322` Motor_Chained1 `P322` Motor_Aux `LATCH_MERGE_324`
- Physical chain `M322 -> P322 -> P324 CURVE`

## Counts

| Metric | Count |
|--------|------:|
| MergeBoss | 4 |
| MergeInputs | 8 |
| Jamcheck | 54 |
| Jamzones | 27 |
| Mtrchain | 176 |
| CURVE | 69 |
| Areas | 1 |
| review_unresolved | 0 |

Discovery classes: proven=`4` candidate=`0` unresolved=`0`
CP4 Jam adapter: jamcheckRecordsTouched=`54` jamzonesIdentities=`17`
CP4 Merge adapter: mergeBossObjects=`4` lanes=`8` byClass=`{'2-1': 1, '3-1': 1, 'SPUR': 2, 'UNKNOWN': 0}`
CP4 Mtrchain adapter: entries=`176` facts=`640`

## Observed MergeBoss / lanes

- `MERGE_406_3-1` class=`3-1` discovery=`PROVEN` lanes=['LANE1_P404', 'LANE2_P138']
- `MERGE_316_SPUR` class=`SPUR` discovery=`PROVEN` lanes=['LANE1_P136', 'LANE2_P312']
- `MERGE_400_2-1` class=`2-1` discovery=`PROVEN` lanes=['LANE1_P242', 'LANE2_P150_2-1']
- `MERGE_324_SPUR` class=`SPUR` discovery=`PROVEN` lanes=['LANE1_P150_SPUR', 'LANE2_P320']

## MERGE_316 evidence

- discovery inductLane=`P312` phys=`P314` next=`P316`
- Mtrchain M314 row: `{'Motor_Name': 'M314', 'Motor_Ndx': 'M314', 'Motor_Chained1': 'P314', 'Motor_Chained2': 'P316', 'Motor_Aux': 'LATCH_MERGE_316', 'Enabled': 'M136_AUX'}`
- Conveyor P316 Type: `CURVE`
- CP4 M314: ndx=`M314` aux=`LATCH_MERGE_316` enabled=`M136_AUX` chained1=`P314`
- CP4 merge proof status: `PROVEN`

## MERGE_324 evidence

- discovery inductLane=`P320` phys=`P322` next=`P324`
- Mtrchain M322 row: `{'Motor_Name': 'M322', 'Motor_Ndx': 'M322', 'Motor_Chained1': 'P322', 'Motor_Chained2': 'P324', 'Motor_Aux': 'LATCH_MERGE_324', 'Enabled': ''}`
- Conveyor P324 Type: `CURVE`

## Checks

- **PASS** mergeboss_asc:MERGE_406_3-1 — MERGE_316_SPUR,MERGE_324_SPUR,MERGE_400_2-1,MERGE_406_3-1
- **PASS** mergeboss_discovery:MERGE_406_3-1 — ['MERGE_316_SPUR', 'MERGE_324_SPUR', 'MERGE_400_2-1', 'MERGE_406_3-1']
- **PASS** mergeboss_asc:MERGE_316_SPUR — MERGE_316_SPUR,MERGE_324_SPUR,MERGE_400_2-1,MERGE_406_3-1
- **PASS** mergeboss_discovery:MERGE_316_SPUR — ['MERGE_316_SPUR', 'MERGE_324_SPUR', 'MERGE_400_2-1', 'MERGE_406_3-1']
- **PASS** mergeboss_asc:MERGE_400_2-1 — MERGE_316_SPUR,MERGE_324_SPUR,MERGE_400_2-1,MERGE_406_3-1
- **PASS** mergeboss_discovery:MERGE_400_2-1 — ['MERGE_316_SPUR', 'MERGE_324_SPUR', 'MERGE_400_2-1', 'MERGE_406_3-1']
- **PASS** mergeboss_asc:MERGE_324_SPUR — MERGE_316_SPUR,MERGE_324_SPUR,MERGE_400_2-1,MERGE_406_3-1
- **PASS** mergeboss_discovery:MERGE_324_SPUR — ['MERGE_316_SPUR', 'MERGE_324_SPUR', 'MERGE_400_2-1', 'MERGE_406_3-1']
- **PASS** merge_type:MERGE_406_3-1 — got=3-1
- **PASS** merge_type:MERGE_316_SPUR — got=SPUR
- **PASS** merge_type:MERGE_400_2-1 — got=2-1
- **PASS** merge_type:MERGE_324_SPUR — got=SPUR
- **PASS** mergeinputs:MERGE_406_3-1:LANE1 — ['LANE1_P404', 'LANE2_P138']
- **PASS** mergeinputs:MERGE_406_3-1:LANE2 — ['LANE1_P404', 'LANE2_P138']
- **PASS** mergeinputs:MERGE_316_SPUR:LANE1 — ['LANE1_P136', 'LANE2_P312']
- **PASS** mergeinputs:MERGE_316_SPUR:LANE2 — ['LANE1_P136', 'LANE2_P312']
- **PASS** mergeinputs:MERGE_400_2-1:LANE1 — ['LANE1_P242', 'LANE2_P150_2-1']
- **PASS** mergeinputs:MERGE_400_2-1:LANE2 — ['LANE1_P242', 'LANE2_P150_2-1']
- **PASS** mergeinputs:MERGE_324_SPUR:LANE1 — ['LANE1_P150_SPUR', 'LANE2_P320']
- **PASS** mergeinputs:MERGE_324_SPUR:LANE2 — ['LANE1_P150_SPUR', 'LANE2_P320']
- **PASS** merge316:LANE1_P136:presence — EZPE136_P1
- **PASS** merge316:LANE1_P136:release_io — SSVEZPE136_P1
- **PASS** merge316:LANE2_P312:presence — PE314_P
- **PASS** merge316:LANE2_P312:release_io — M314
- **PASS** m314:Motor_Ndx — M314
- **PASS** m314:Motor_Chained1 — P314
- **PASS** m314:Motor_Aux — LATCH_MERGE_316
- **PASS** m314:Enabled — M136_AUX
- **PASS** merge316:phys_chain_discovery — phys=P314 next=P316
- **PASS** merge316:phys_chain_mtrchain — {'Motor_Name': 'M314', 'Motor_Ndx': 'M314', 'Motor_Chained1': 'P314', 'Motor_Chained2': 'P316', 'Motor_Aux': 'LATCH_MERGE_316', 'Enabled': 'M136_AUX'}
- **PASS** merge316:p316_curve — CURVE
- **PASS** cp4_merge_boss:MERGE_406_3-1 — MERGE_316_SPUR,MERGE_324_SPUR,MERGE_400_2-1,MERGE_406_3-1
- **PASS** cp4_merge_boss:MERGE_316_SPUR — MERGE_316_SPUR,MERGE_324_SPUR,MERGE_400_2-1,MERGE_406_3-1
- **PASS** cp4_merge_boss:MERGE_400_2-1 — MERGE_316_SPUR,MERGE_324_SPUR,MERGE_400_2-1,MERGE_406_3-1
- **PASS** cp4_merge_boss:MERGE_324_SPUR — MERGE_316_SPUR,MERGE_324_SPUR,MERGE_400_2-1,MERGE_406_3-1
- **PASS** cp4_merge316_proof — PROVEN
- **PASS** cp4_m314_fields — {'ndx': 'M314', 'chained1': 'P314', 'aux': 'LATCH_MERGE_316', 'enabled': 'M136_AUX'}
- **PASS** merge324:LANE1_P150_SPUR:presence — EZPE150_P1
- **PASS** merge324:LANE1_P150_SPUR:release_io — SSVEZPE150_P1
- **PASS** merge324:LANE2_P320:presence — PE322_P
- **PASS** merge324:LANE2_P320:release_io — M322
- **PASS** m322:Motor_Ndx — M322
- **PASS** m322:Motor_Chained1 — P322
- **PASS** m322:Motor_Aux — LATCH_MERGE_324
- **PASS** merge324:phys_chain_discovery — phys=P322 next=P324
- **PASS** merge324:phys_chain_mtrchain — {'Motor_Name': 'M322', 'Motor_Ndx': 'M322', 'Motor_Chained1': 'P322', 'Motor_Chained2': 'P324', 'Motor_Aux': 'LATCH_MERGE_324', 'Enabled': ''}
- **PASS** merge324:p324_curve — CURVE
- **PASS** count:MergeBoss>=4 — 4
- **PASS** count:MergeInputs>=8 — 8
- **PASS** count:Mtrchain>0 — 176
- **PASS** count:Jamcheck>0 — 54
- **PASS** count:Jamzones>0 — 27
- **PASS** count:CURVE>0 — 69

## Notes

- Merge types SPUR / 2-1 / 3-1 are preserved from MergeBoss name tokens (`classify_merge_source`) and discovery `sourceClassification`.
- Physical chain M314→P314→P316 is Mtrchain Motor_Chained* + Conveyor.Type=CURVE; not an invented topology edge.
- `review_unresolved` aggregates site_model unresolved + discovery unresolved + CP4 adapter REVIEW/FAIL flags.
