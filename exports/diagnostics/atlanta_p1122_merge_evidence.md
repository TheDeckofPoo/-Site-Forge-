# Atlanta P1122 Merge Evidence — Deterministic Only

**Site / machine:** MSCATL_CP3  
**RUN:** `workspace/_mscatl_peek/MSCATL_CP3/RUN`  
**Policy:** Do **not** classify from schematic appearance.

## Verdict

### **PROVEN MERGE**

P1122 is covered by a machine-scoped **SimpleMerge** row (`Merge1122Pic`). It is **not** a MergeBoss / MergeInputs / MergeRoute merge.

## Canonical merge model evidence

### SimpleMerge.asc.MSCATL_CP3 (primary)

| Field | Value |
|-------|-------|
| Name | `Merge1122Pic` |
| MainLineRun | `M1122AUX` |
| ClearTimer | `tmsmPE1120_P` |
| MainLinePresence | `PE1220_P` |
| LanePresence | `PE1120_P` |
| LaneRun | `VFD1120_EN` |
| Machine | `MSCATL_CP3` |
| pRun | `1` |

Table semantics (`fortna_build_table_knowledge.py`): *two-way simple merge — mainline vs lane presence/run with clear timer.*

### MergeBoss / MergeInputs / MergeRoute

Active MergeBoss rows on this machine:

- `3-1 Recirc Merge` (NumInputs=3) — pack recirc / P3012A family  
- `Merge 2310` (NumInputs=2)

**No** P1122 / Merge1122 identity appears in MergeBoss, MergeInputs, or MergeRoute.

## Supporting deterministic evidence

1. **Jamcheck.asc** — `PE1134_J` → conveyor `P1122`, area `PICK_LVL2_MERGE`, motor `M1122AUX`
2. **Mtrchain.asc** — `M1122` chained to `P1122`, latch `LATCH_PIC_LVL2_MERGE`, next `M1124AUX`
3. **Mtrchain.asc** — `VFD1120_EN` (P1120) and `VFD1220_EN` (P1220) both interlock to `M1122AUX`, matching SimpleMerge LaneRun / MainLinePresence sides

## Neighbor conveyor relations

| Tag | Geometry (X,Y,∠,L) | Relation |
|-----|--------------------|----------|
| P1120 | 29779.167, 150141.556, 90°, 1100 BELT | SimpleMerge lane side (`VFD1120_EN` / `PE1120_P`); geom candidate → P1122 HIGH |
| P1220 | 30279.167, 147768.532, 90°, 3547.9 BELT | SimpleMerge mainline presence (`PE1220_P`); geom candidate → P1122 AMBIGUOUS |
| P1122 | 30019.322, 151254.198, 90°, 1150×650 STRAIGHT | Merge bed / discharge of simple merge |
| P1124 | 29779.167, 152353.084, 90°, 1550 ZP | Downstream via Mtrchain; geom candidate from P1122 HIGH |

## What this is / is not

| Question | Answer |
|----------|--------|
| Is P1122 a proven merge? | **Yes — SimpleMerge** |
| Is it a MergeBoss 2:1 / 3:1? | **No** |
| Was verdict from appearance? | **No** |
| Does regen4 emit it as merges_2to1? | **No** (only P3012A_Merge); absence from autogen merges does not erase RUN SimpleMerge proof |

## Key snippets

```text
# SimpleMerge.asc.MSCATL_CP3
Merge1122Pic~M1122AUX~tmsmPE1120_P~PE1220_P~PE1120_P~VFD1120_EN~N~MSCATL_CP3~0~1~N~N~

# Jamcheck.asc
PE1134_J~...~P1122~PICK_LVL2_MERGE~MSCATL_CP3~0~M1122AUX~...

# Mtrchain.asc
M1122~...~P1122~...~LATCH_PIC_LVL2_MERGE~...~M1124AUX~...~M1122AUX~...
```
