# Hardware catalog (generic module definitions)

Reusable **catalog-number** metadata for Hardware/I/O Level B terminal layouts.

Site Forge must **never** invent site wiring. Level A always comes from RUN/Configio.

Each folder is named by exact catalog (e.g. `1794-IA16`) and may contain:

- `module.json` — channel count, direction, family, terminal labels
- optional future: geometry, approved pin diagram (static, not scraped)

Absence of a catalog entry → Level C: "Wiring information unavailable for this module."

## Offline / continuity

- Engineer aliases and Generate mute live in Hardware/I/O overrides — **physical endpoint identity is immutable**.
- Persistence checklist: `exports/stabilization/io_edit_persistence_checklist.md`
- I/O identity collisions (`M220_AUX` vs `M220A_AUX`): `docs/PLC2_IO_TRUTH_MODEL.md`, `tools/scripts/test_m220_aux_identity.py`
- Site Forge handoff index: `exports/stabilization/README.md`
