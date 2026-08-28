# Transport Build POC report (2026-08-28T17:55:35.471533+00:00)

- Areas: **1**
- Conveyor nodes: **10**
- Merges: **1**
- Wires: **9**
- Devices: **14**
- Unbound conveyors: **5**
- Untagged devices: **0**
- Autogen merges_2to1 rows: **1**

## Issues
- Merge1: node Straight has no P### tag
- Merge1: node Straight has no P### tag
- Merge1: node 90° Left has no P### tag
- Merge1: node 90° Right has no P### tag
- Merge1: node 90° Left has no P### tag

## Areas
### Merge1
- Conveyors: 10, wires: 9
- Merge **Merge 2:1** lanes=2 AOI=`Merge_2to1` discharge=`P400`
  - in0: `P302`
  - in1: `P228`

## Autogen merges_2to1 (PLC2 shape)
- `P400` area=`Merge1` lanes=2 P302 + P228 → P400 hold=`runhold`

Fragment file: `transport_autogen_merges_20260828-175535.json`

## Next steps
1. Bind every conveyor node to a P### tag from the RUN.
1. Tag motors as M### / VFD### only; ENC* for encoders; PE*/EZPE* for eyes.
1. 2:1 merges → Autogen merges_2to1 (PLC2 runhold). Import fragment into PLC Autogen workbook.
1. Keep sealed Fast_Conv / Slow_* / Merge_2to1 AOIs; only wire call sites.
1. Full L5X emit from this graph is Phase 2b (IO map + transport focus).
