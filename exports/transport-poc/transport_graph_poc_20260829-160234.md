# Transport Build POC report (2026-08-29T16:02:34.336258+00:00)

- Areas: **1**
- Conveyor nodes: **4**
- Merges: **0**
- Wires: **3**
- Devices: **9**
- Unbound conveyors: **0**
- Untagged devices: **0**
- Autogen merges_2to1 rows: **0**

## Issues
- None

## Areas
### Transport_1
- Conveyors: 4, wires: 3

## Autogen merges_2to1 (PLC2 shape)
- (none yet — drop a Merge and wire two entrances)

Fragment file: `transport_autogen_merges_20260829-160234.json`

## Next steps
1. Bind every conveyor node to a P### tag from the RUN.
1. Tag motors as M### / VFD### only; ENC* for encoders; PE*/EZPE* for eyes.
1. 2:1 merges → Autogen merges_2to1 (PLC2 runhold). Import fragment into PLC Autogen workbook.
1. Keep sealed Fast_Conv / Slow_* / Merge_2to1 AOIs; only wire call sites.
1. Full L5X emit from this graph is Phase 2b (IO map + transport focus).
