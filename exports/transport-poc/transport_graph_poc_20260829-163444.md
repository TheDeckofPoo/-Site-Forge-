# Transport Build POC report (2026-08-29T16:34:44.655292+00:00)

- Areas: **1**
- Conveyor nodes: **6**
- Merges: **1**
- Wires: **5**
- Devices: **12**
- Unbound conveyors: **0**
- Untagged devices: **0**
- Autogen merges_2to1 rows: **1**

## Issues
- Transport_1: 'Transport_1_C1' is not a P### conveyor tag
- Transport_1: 'Transport_1_C2' is not a P### conveyor tag
- Transport_1: 'Transport_1_C3' is not a P### conveyor tag
- Transport_1: 'Transport_1_C4' is not a P### conveyor tag
- Transport_1: 'Transport_1_C5' is not a P### conveyor tag
- Transport_1: 'Transport_1_C6' is not a P### conveyor tag

## Areas
### Transport_1
- Conveyors: 6, wires: 5
- Merge **Merge 2:1** lanes=2 AOI=`Merge_2to1` discharge=`Transport_1_C4`
  - in1: `Transport_1_C2`
  - in0: `Transport_1_C3`

## Autogen merges_2to1 (PLC2 shape)
- `Transport_1_C4` area=`Transport_1` lanes=2 Transport_1_C3 + Transport_1_C2 → Transport_1_C4 hold=`runhold`

Fragment file: `transport_autogen_merges_20260829-163444.json`

## Next steps
1. Bind every conveyor node to a P### tag from the RUN.
1. Tag motors as M### / VFD### only; ENC* for encoders; PE*/EZPE* for eyes.
1. 2:1 merges → Autogen merges_2to1 (PLC2 runhold). Import fragment into PLC Autogen workbook.
1. Keep sealed Fast_Conv / Slow_* / Merge_2to1 AOIs; only wire call sites.
1. Full L5X emit from this graph is Phase 2b (IO map + transport focus).
