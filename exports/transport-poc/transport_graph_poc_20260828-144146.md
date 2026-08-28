# Transport Build POC report (2026-08-28T14:41:46.467234+00:00)

- Areas: **2**
- Conveyor nodes: **7**
- Merges: **1**
- Wires: **5**
- Devices: **14**
- Unbound conveyors: **0**
- Untagged devices: **0**
- Autogen merges_2to1 rows: **1**

## Issues
- None

## Areas
### Transport_1
- Conveyors: 4, wires: 3
- Merge **Merge 2:1** lanes=2 AOI=`Merge_2to1` discharge=`P18`
  - in0: `P10`
  - in1: `P12`

### AREA After Merge
- Conveyors: 3, wires: 2

## Autogen merges_2to1 (PLC2 shape)
- `P18` area=`Transport_1` lanes=2 P10 + P12 → P18 hold=`runhold`

Fragment file: `transport_autogen_merges_20260828-144146.json`

## Next steps
1. Bind every conveyor node to a P### tag from the RUN.
1. Tag motors as M### / VFD### only; ENC* for encoders; PE*/EZPE* for eyes.
1. 2:1 merges → Autogen merges_2to1 (PLC2 runhold). Import fragment into PLC Autogen workbook.
1. Keep sealed Fast_Conv / Slow_* / Merge_2to1 AOIs; only wire call sites.
1. Full L5X emit from this graph is Phase 2b (IO map + transport focus).
