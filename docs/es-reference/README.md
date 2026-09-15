# ES Program structural reference

`ES_Program_PLC5_structural.L5X` is a PLC5 **exported Program ES** used as a
**structural pattern** for Site Forge generation.

## Use as pattern — not as site data

Copy the architecture:

- Program `ES` / Main_Routine
- Per zone: `<Zone>_Safe_Logic`, `<Zone>_Safe_PI`
- `ES_SIL1_Cat1` per safety device
- `ES_PI20` aggregation with `NO_ESNull` padding
- Reset / Silence / Tripped / Silenced_Tripped / ESPX_Not_OK mappings

Do **not** copy PLC5 site-specific zone names or device membership
(Redroom, ShippingSorter, ES500, CP5/6/7, …) into PLC2.

Membership for each project comes from:

1. RUN / physical I/O evidence
2. Engineer Safety Zone assignments (`safety_build.zones[].members`)

See `tools/scripts/fortna_es_compiler.py`.
