# Transport Build POC report (2026-08-28T15:38:05.017835+00:00)

- Areas: **2**
- Conveyor nodes: **6**
- Merges: **1**
- Wires: **4**
- Devices: **9**
- Unbound conveyors: **1**
- Untagged devices: **0**
- Autogen merges_2to1 rows: **1**

## Issues
- Transport_1: node Straight has no P### tag

## Areas
### Transport_1
- Conveyors: 4, wires: 3
- Merge **Merge 2:1** lanes=2 AOI=`Merge_2to1` discharge=`P15`
  - in0: `P40`
  - in1: `P48`

### area2
- Conveyors: 2, wires: 1

## Autogen merges_2to1 (PLC2 shape)
- `P15` area=`Transport_1` lanes=2 P40 + P48 → P15 hold=`runhold`

Fragment file: `transport_autogen_merges_20260828-153805.json`

## Next steps
1. Bind every conveyor node to a P### tag from the RUN.
1. Tag motors as M### / VFD### only; ENC* for encoders; PE*/EZPE* for eyes.
1. 2:1 merges → Autogen merges_2to1 (PLC2 runhold). Import fragment into PLC Autogen workbook.
1. Keep sealed Fast_Conv / Slow_* / Merge_2to1 AOIs; only wire call sites.
1. Full L5X emit from this graph is Phase 2b (IO map + transport focus).
