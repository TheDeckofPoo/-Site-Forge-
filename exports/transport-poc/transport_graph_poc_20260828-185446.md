# Transport Build POC report (2026-08-28T18:54:46.995884+00:00)

- Areas: **2**
- Conveyor nodes: **8**
- Merges: **1**
- Wires: **7**
- Devices: **15**
- Unbound conveyors: **0**
- Untagged devices: **0**
- Autogen merges_2to1 rows: **1**

## Issues
- MERGE5: 'MERGE5_C1' is not a P### conveyor tag
- MERGE5: 'MERGE5_C2' is not a P### conveyor tag
- MERGE5: 'MERGE5_C3' is not a P### conveyor tag
- MERGE5: 'MERGE5_C4' is not a P### conveyor tag
- MERGE5: 'MERGE5_C5' is not a P### conveyor tag
- MERGE5: 'MERGE5_C6' is not a P### conveyor tag
- MERGE5: 'MERGE5_C7' is not a P### conveyor tag

## Areas
### Transport_1
- Conveyors: 0, wires: 0

### MERGE5
- Conveyors: 8, wires: 7
- Merge **Merge 2:1** lanes=2 AOI=`Merge_2to1` discharge=`P400`
  - in1: `MERGE5_C3`
  - in0: `MERGE5_C1`

## Autogen merges_2to1 (PLC2 shape)
- `P400` area=`MERGE5` lanes=2 MERGE5_C1 + MERGE5_C3 → P400 hold=`runhold`

Fragment file: `transport_autogen_merges_20260828-185446.json`

## Next steps
1. Bind every conveyor node to a P### tag from the RUN.
1. Tag motors as M### / VFD### only; ENC* for encoders; PE*/EZPE* for eyes.
1. 2:1 merges → Autogen merges_2to1 (PLC2 runhold). Import fragment into PLC Autogen workbook.
1. Keep sealed Fast_Conv / Slow_* / Merge_2to1 AOIs; only wire call sites.
1. Full L5X emit from this graph is Phase 2b (IO map + transport focus).
