# Transport Build POC report (2026-08-28T06:27:44.657948+00:00)

- Areas: **1**
- Conveyor nodes: **2**
- Merges: **1**
- Wires: **1**
- Devices: **1**
- Unbound conveyors: **0**
- Untagged devices: **0**

## Issues
- None

## Areas
### Transport_1
- Conveyors: 2, wires: 1
- Merge **Merge 2:1** lanes=2 AOI=`Merge_2to1` discharge=`P208`
  - in0: `P100`

## Next steps
1. Bind every conveyor node to a P### tag from the RUN.
1. Tag motors as M### / VFD### only; ENC* for encoders; PE*/EZPE* for eyes.
1. 2:1 merges → feed fortna_autogen merges_2to1 list (discharge + lanes).
1. Full L5X emit from this graph is Phase 2b (not this POC).
