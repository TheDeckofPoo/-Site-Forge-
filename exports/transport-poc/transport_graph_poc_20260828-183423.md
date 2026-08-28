# Transport Build POC report (2026-08-28T18:34:23.167979+00:00)

- Areas: **1**
- Conveyor nodes: **8**
- Merges: **1**
- Wires: **7**
- Devices: **15**
- Unbound conveyors: **7**
- Untagged devices: **0**
- Autogen merges_2to1 rows: **1**

## Issues
- Transport_2: node Straight has no P### tag
- Transport_2: node Straight has no P### tag
- Transport_2: node Straight has no P### tag
- Transport_2: node Straight has no P### tag
- Transport_2: node Straight has no P### tag
- Transport_2: node Straight has no P### tag
- Transport_2: node Straight has no P### tag

## Areas
### Transport_2
- Conveyors: 8, wires: 7
- Merge **Merge 2:1** lanes=2 AOI=`Merge_2to1` discharge=`P400`
  - in0: `Straight`
  - in1: `Straight`

## Autogen merges_2to1 (PLC2 shape)
- `P400` area=`Transport_2` lanes=2 Straight + Straight → P400 hold=`runhold`

Fragment file: `transport_autogen_merges_20260828-183423.json`

## Next steps
1. Bind every conveyor node to a P### tag from the RUN.
1. Tag motors as M### / VFD### only; ENC* for encoders; PE*/EZPE* for eyes.
1. 2:1 merges → Autogen merges_2to1 (PLC2 runhold). Import fragment into PLC Autogen workbook.
1. Keep sealed Fast_Conv / Slow_* / Merge_2to1 AOIs; only wire call sites.
1. Full L5X emit from this graph is Phase 2b (IO map + transport focus).
