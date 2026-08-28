# Transport Build POC report (2026-08-28T18:02:58.477957+00:00)

- Areas: **1**
- Conveyor nodes: **6**
- Merges: **1**
- Wires: **5**
- Devices: **7**
- Unbound conveyors: **2**
- Untagged devices: **0**
- Autogen merges_2to1 rows: **1**

## Issues
- Transport_2: node Merge 2:1 has no P### tag
- Transport_2: node Straight has no P### tag

## Areas
### Transport_2
- Conveyors: 6, wires: 5
- Merge **Merge 2:1** lanes=2 AOI=`Merge_2to1` discharge=`None`
  - in0: `P600`
  - in1: `P20A`

## Autogen merges_2to1 (PLC2 shape)
- `Merge_2:1` area=`Transport_2` lanes=2 P600 + P20A → Merge_2:1 hold=`runhold`

Fragment file: `transport_autogen_merges_20260828-180258.json`

## Next steps
1. Bind every conveyor node to a P### tag from the RUN.
1. Tag motors as M### / VFD### only; ENC* for encoders; PE*/EZPE* for eyes.
1. 2:1 merges → Autogen merges_2to1 (PLC2 runhold). Import fragment into PLC Autogen workbook.
1. Keep sealed Fast_Conv / Slow_* / Merge_2to1 AOIs; only wire call sites.
1. Full L5X emit from this graph is Phase 2b (IO map + transport focus).
