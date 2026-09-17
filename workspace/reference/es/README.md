# ES Program structural reference

`ES_Program_PLC5_structural.L5X` is a PLC5 **exported Program ES** used as a
**structural pattern** for Site Forge generation.

Canonical copy of this README also lives at `docs/es-reference/README.md`.
Offline Safety contract: `exports/stabilization/partial_build_contract.md`.

## Use as pattern — not as site data

Copy the architecture:

- Program `ES` / `Main_Routine`
- Task `P01_Safety_20ms` schedules Program `ES`
- Per zone (when members exist): `<Zone>_Safe_Logic`, `<Zone>_Safe_PI`
- `ES_SIL1_Cat1` per safety device
- `ES_PI20` aggregation with `NO_ESNULL` padding
- Reset / Silence / Tripped / Silenced_Tripped / ESPX_Not_OK mappings

Do **not** copy PLC5 site-specific zone names or device membership
(Redroom, ShippingSorter, ES500, CP5/6/7, …) into PLC2.

## Membership (PARTIAL BUILD)

1. RUN / physical I/O evidence (FOUND)
2. Engineer Safety Zone assignments (`safety_build.zones[].members`) — INCLUDED

**Never invent membership.** Unassigned devices → `REVIEW REQUIRED`, not SAFE.

Unresolved membership → fail-safe ES shell (NOP Main_Routine), `COMMISSIONING READY = NO`.
Project build of unrelated packs may continue.

See `tools/scripts/fortna_es_compiler.py` and `exports/stabilization/README.md`.
