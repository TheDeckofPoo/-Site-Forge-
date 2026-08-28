# Transport Build POC report (2026-08-28T07:06:31.021687+00:00)

- Areas: **2**
- Conveyor nodes: **4**
- Merges: **1**
- Wires: **3**
- Devices: **8**
- Unbound conveyors: **0**
- Untagged devices: **0**
- Autogen merges_2to1 rows: **1**

## Issues
- None

## Areas
### Transport_1
- Conveyors: 4, wires: 3
- Merge **Merge 2:1** lanes=2 AOI=`Merge_2to1` discharge=`P13`
  - in0: `P11`
  - in1: `P12`

### Transport_2
- Conveyors: 0, wires: 0

## Autogen merges_2to1 (PLC2 shape)
- `P13` area=`Transport_1` lanes=2 P11 + P12 → P13 hold=`runhold`

Fragment file: `transport_autogen_merges_20260828-070631.json`

## Next steps
1. Bind every conveyor node to a P### tag from the RUN.
1. Tag motors as M### / VFD### only; ENC* for encoders; PE*/EZPE* for eyes.
1. 2:1 merges → Autogen merges_2to1 (PLC2 runhold). Import fragment into PLC Autogen workbook.
1. Keep sealed Fast_Conv / Slow_* / Merge_2to1 AOIs; only wire call sites.
1. Full L5X emit from this graph is Phase 2b (IO map + transport focus).
