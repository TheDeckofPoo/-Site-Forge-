# Site Forge — Permanent Regression Manifest

Index of accepted layers and critical fixtures. Not a rewrite of architecture docs.

## Accepted layers

| Layer | Commit | Role |
|-------|--------|------|
| CP1 | `bedcb7a` | Fortna `.mnu` schema / archaeology foundation |
| CP2 | `83dc7bb` | Runtime typed loader |
| CP3 | `d43abd6` | Graph / relationships |
| CP4 | `e426152` | Adapters / semantic evidence |
| CP5A | `9ec550a` | Decoder → RUN import + Transportation |
| Stabilization | `58fb309` → punch-list lineage | Transport hit/layout, Safety ES shell, I/O identity |

**Do not rewrite CP1–CP4.**

## Site fixtures

| Site | Controller | Notes |
|------|------------|-------|
| PLC2 | ORNCCP2 | Primary commissioning site |
| PLC4 | ORNCCP4 | Series architecture reference |
| PLC5 | ORNCCP5 | Series architecture reference |

Finished PLC files are **validation oracles only** — never copy site-specific config into discovery.

## Permanent commands (representative)

```text
python tools/scripts/test_fortna_mnu_schema.py
python tools/scripts/test_fortna_run_loader.py
python tools/scripts/test_fortna_mnu_runtime.py
python tools/scripts/test_cp4_bundle.py
python tools/scripts/test_cp5a_integration.py
python tools/scripts/test_transport_hit_geometry.py
python tools/scripts/test_transport_area_move_positions.py
python tools/scripts/test_m220_aux_identity.py
python tools/scripts/test_iomap_duplicate_output_ownership.py
python tools/scripts/test_hardware_io_overrides.py
python tools/scripts/test_es_compiler.py
python tools/scripts/test_safety_model.py
python tools/scripts/test_partial_build_acceptance.py
python tools/scripts/fortna_studio_preflight.py exports/current/ORNCCP2.L5X
```

## Partial build contract

See `exports/stabilization/partial_build_contract.md`.

Incremental commissioning is first-class: FOUND≠INCLUDED≠GENERATED; REVIEW does not block Build PLC; ERROR on INCLUDED content does.

## Critical fixtures

### Transportation

| Fixture | Expectation |
|---------|-------------|
| P404 selection | Body + label selectable after layout |
| P136 selection | Same; CURVE/assembly neighbors do not steal hits |
| Area move persistence | Unaffected nodes keep X/Y + display offsets (PL-1) |
| CURVE placeholder | UNKNOWN-orientation diagonal symbol; conveyor weight (PL-2) |

### I/O identity

| Fixture | Expectation |
|---------|-------------|
| M220_AUX | Exact identity → `P220_MS.I.Auxiliary_Forward` when P220 present |
| M220A_AUX | Exact identity → `P220A_MS.I.Auxiliary_Forward` |
| Never collapse | Bare M220 must not map onto lettered P220A |
| P220A_MS duplicate OTE | Preflight ERROR if two writers; no arbitrary winner |

### Safety

| Identity | Class |
|----------|-------|
| CP2_MCR1, CP3_MCR1, T_2MCR1, T_3MCR1 | MCR |
| CP2_ES, CP2_ESR1–3 | E-Stop / ESR |
| CP3_ES, CP3_ESR1–5 | E-Stop / ESR |

Membership must be engineer/proven — never inferred from CP2/CP3/T_2 name tokens.

Safety shell: Program ES + `P01_Safety_20ms` + Main_Routine NOP is **STRUCTURE READY / MEMBERSHIP REVIEW / COMMISSIONING READY = NO**.
