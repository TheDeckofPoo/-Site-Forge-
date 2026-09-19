# FortnaPlus parsers, compilers & scripts

Production and core implementation live in **`tools/scripts/`**.

| Location | Purpose |
|----------|---------|
| `tools/scripts/` | Site Forge runtime, decoder, semantics, compilers |
| `tools/diagnostics/` | Reusable developer diagnostics (not Electron entrypoints) |
| `tests/` | Permanent unit / regression / acceptance tests |

Full machine inventory (historical + cleanup):  
`exports/stabilization/python_script_inventory.md`,  
`exports/stabilization/script_cleanup_manifest.json`,  
`docs/SCRIPT_CLEANUP.md`.

**Do not** commit `_tmp_*` or `_emergency_*` under `tools/scripts/`.  
**Do not** add new `test_*.py` here — use `tests/<area>/`.

---

## Production entrypoints (`desktop/main.js`)

| Script | Role |
|--------|------|
| `fortna_run_workspace_discover.py` | RUN import / workspace discovery |
| `fortna_autogen.py` | PLC autogen compiler |
| `fortna_safety_model.py` | Safety Build backend |
| `fortna_transport_graph.py` | Transport Build backend |
| `fortna_hardware_io_model.py` | Hardware / I/O model |
| `fortna_io_banks.py` | I/O banks + print OCR |
| `fortna_workbook.py` | Conveyor workbook |
| `fortna_plc_export.py` | PLC export package |
| `fortna_ignition_build.py` | Ignition build |
| `fortna_perspective_pack.py` | Perspective pack |
| `fortna_prism_ingest.py` / `fortna_prism_twin.py` | PRISM twin |
| `fortna_cp5a_orchestrator.py` / `fortna_cp5a_transport_mapper.py` | CP5a orchestration |
| `fortna_run_physical_layout.py` | Physical layout |
| `fortna_runtime_provenance.py` | Runtime provenance |
| `apply_recipe.py` | Recipe apply |
| `index_docs.py` | Documentation index |
| `_deploy_designer_safe_ignition.py` | Safe Ignition deploy |
| `fix_ignition_project_attrs.py` | Ignition project attrs |

---

## Core architecture (keep in `tools/scripts/`)

### Decoder / RUN model
`fortna_asc.py`, `fortna_run_loader.py`, `fortna_mnu_schema.py`, `fortna_mnu_runtime.py`,  
`fortna_site_model.py`, `fortna_schema_ir.py`, `fortna_fortna_table_resolver.py`,  
`fortna_machine_closure.py`, `fortna_io_extract.py`, `fortna_equipment_plan.py`,  
`fortna_cp4_discovery.py`, `fortna_identity.py`, `fortna_reference_resolver.py`

### Semantics / Safety / Transport / Sorter
`fortna_estop_model.py`, `fortna_es_compiler.py`, `fortna_safety_model.py`,  
`fortna_conveyor_section_model.py`, `fortna_transport_graph.py`,  
`fortna_plc2_merge_discovery.py`, `fortna_sawtooth_*`, `fortna_sorter_*`,  
`fortna_semantics/` package

### Compiler / L5X
`fortna_autogen.py`, `fortna_cp4_pass1.py`, `fortna_cp4_pass2.py`,  
`fortna_l5x_structured_data.py`, `fortna_l5x_studio_structure.py`,  
`fortna_studio_preflight.py`, `fortna_operand_validator.py`,  
`fortna_autogen_provenance.py`

### Hardware / I/O
`fortna_hardware_family.py`, `fortna_hardware_io_model.py`,  
`fortna_hardware_io_overrides.py`, `fortna_physical_word_resolver.py`

Diagnostics that are **imported** by acceptance gates (e.g. `fortna_l5x_compare.py`)
remain here intentionally.

---

## Tests

```text
tests/
  decoder/      RUN / MNU / ASC / identity
  semantics/    CP4 packs, Sawtooth, activity
  compiler/     L5X / autogen / ES
  safety/       Safety UI + membership
  transport/    Transport + native merge
  io/           Hardware I/O + IO_MAP
  sorter/       Sorter / divert / CP5
  acceptance/   Gates, firewall, provenance
  regression/   Misc permanent regressions
```

Run from repo root, for example:

```bash
python tests/decoder/test_fortna_asc_native_shadow.py
python tests/safety/test_estop_part_ownership.py
python tests/transport/test_native_merge_discovery.py
```

---

## Diagnostics

Reusable manual tools: `tools/diagnostics/`.

Examples: `diagnose_plc2_merge_pipeline.py`, `fortna_io_channel_trace.py`,  
`fortna_plc2_fidelity_audit.py`.

---

## Partial build / Autogen contract

```
FOUND → CONFIGURED → INCLUDED → GENERATED
```

- `fortna_workbook.apply_workbook_to_input` skips `include=false` rows
- Transport Apply graph is the engineer INCLUDED set
- Unassigned Safety → ES shell + `REVIEW_REQUIRED` (not build-fatal)
- Fixture: `tests/compiler/test_partial_build_acceptance.py`

## Identity rule

`M220_AUX` ≠ `M220A_AUX`. Never strip alphabetic suffixes to establish ownership.  
Tests: `tests/compiler/test_m220_aux_identity.py`, `tests/io/test_iomap_duplicate_output_ownership.py`.
