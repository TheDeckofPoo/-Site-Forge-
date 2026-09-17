# FortnaPlus parsers, compilers & scripts

**Offline note:** Full classification of every `.py` under this folder is in  
`exports/stabilization/python_script_inventory.md` (+ `.json`).  
**Do not delete/consolidate scripts yet** — inventory only (Gate I / PL-10).

**Branch / handoff:** see repo root `README.md` and `exports/stabilization/README.md`.

These are the main **customer-facing extraction and compile scripts** in Site Forge.
Use this list when publishing to GitHub so the scrape/parse work is visible and credited.

## RUN / tar.gz (primary site data)

| Script | What it scrapes | Output |
|--------|-----------------|--------|
| **`fortna_asc.py`** | Fortna `.asc` table format (headers + rows) | Shared reader for all ASC tables |
| **`fortna_io_extract.py`** | `Conveyor.asc` I/O points, drawing page #, device class | PE/motor/VFD rows, bank.bit, print page |
| **`fortna_io_banks.py`** | Banks + **electrical PDF OCR** for VFD params | Bank inventory, VFD print #, PowerFlex tables |
| **`fortna_workbook.py`** | RUN → editable conveyor workbook | Area / TYPE / Exit PE; honors `include` flag |
| **`fortna_autogen.py`** | RUN + library L5X → Studio project | Programs, tags, **IO_MAP**, Flex modules, **ES shell** |
| **`fortna_es_compiler.py`** | Safety Zone IR → Program ES | Fail-safe shell or Safe_Logic/Safe_PI |
| **`fortna_studio_preflight.py`** | Static L5X structural check | Errors/warnings + `structural.safety` block |
| **`fortna_plc_export.py`** | RUN → Studio scaffold + Factory I/O | Tags CSV, L5X package, FIO scene |
| **`fortna_conveyor_section_model.py`** | Letter-motor / PE-SSV sections | Promote sections; **keep P{n} when bare M{n} exists** |

### IO_MAP sources (important)

| Source | When used | What it is |
|--------|-----------|------------|
| **RUN map (default)** | Always for new sites (ORDENCP4, etc.) | Built from `Conveyor.asc` Bank.Bit + `EIPCSV` → `CPxRIO…` |
| **Gold Excel IO_MAP** | Greensboro-style CP5/CP6/CP7 only | Finished Studio export merge. **Not** a general scraper. Auto-blocked when word map is CP1–CP4. |

**Identity rule:** `M220_AUX` ≠ `M220A_AUX`. Never strip alphabetic suffixes to establish ownership.  
Tests: `test_m220_aux_identity.py`, `test_iomap_duplicate_output_ownership.py`.

“Gold” in this repo means **reference / finished O'Reilly library artifacts** (L5X programs, sealed AOIs), not a separate product name.

## Partial build / Autogen contract

```
FOUND → CONFIGURED → INCLUDED → GENERATED
```

- `fortna_workbook.apply_workbook_to_input` skips `include=false` rows
- Transport Apply graph is the engineer INCLUDED set
- Unassigned Safety → ES shell + `REVIEW_REQUIRED` (not build-fatal)
- Fixture: `test_partial_build_acceptance.py`

## Electrical prints (VFD / PowerFlex)

| Landmark on the drawing (red boxes) | Parser hook |
|-------------------------------------|-------------|
| **VFD title** `VFD501B-2` + catalog `(25B-…)` | `_ocr_regions_for_vfd_ids`, `_normalize_vfd_id` |
| **POWERFLEX terminal block** | Page has PowerFlex table → spatial column split |
| **PAR # / PARAMETER NAME / PROGRAMMED VALUE** | `_PF_CODED_LINE` / `_PF_LINE` → `extract_vfd_params_from_text` |
| **Bottom title** `VFD WIRING – (VFD312, VFD412)` | `_vfd_ids_from_wiring_title` |

Entry points:

- `ocr_print_pdfs` / `attach_print_params_to_drives` in **`fortna_io_banks.py`**
- UI: Site Forge → I/O & Prints → OCR panels

## Ignition / HMI

| Script | What it builds |
|--------|----------------|
| **`fortna_ignition_build.py`** | Layout SVG, devices, **tags_import.json**, interactive test HTML |
| **`fortna_perspective_pack.py`** | Perspective project zip + Plant_Layout views |
| **`fortna_ignition_extract.py`** | Helpers for EIP / device maps |

## Transport Build

| Script / module | Role |
|-----------------|------|
| **`fortna_transport_graph.py`** | Areas + PE roles + merges → workbook Apply |
| **`dashboard/transport-build.js`** | Schematic UI — frozen layout after Area move; CURVE symbol |
| **`dashboard/transport-build-pass2.js`** | Multi-select Area move; Rebuild Layout unlocks offsets |
| **`test_transport_hit_geometry.py`** | Stale hitbox regression |
| **`test_transport_area_move_positions.py`** | Unaffected X/Y persistence after Area move |

## Decoder / CP stack (frozen)

| Layer | Do not rewrite |
|-------|----------------|
| CP1–CP4 | Schema / loader / graph / adapters — see `docs/REGRESSION_MANIFEST.md` |
| CP5A | Decoder → Transport integration |

## PRISM / knowledge corpus / Site Twin

| Script | Role |
|--------|------|
| **`fortna_prism_ingest.py`** | Dedupe + ingest exports; **`stage_twin`** → `twin/gaps.json` |
| **`fortna_prism_twin.py`** | Load gaps · PRISM search · SpaceXAI propose · apply workbook patches |
| **`fortna_prism_seed.py`** / **`fortna_prism_build.py`** | Seed L5X snippets for vector DB |

## Supporting

| Script | Role |
|--------|------|
| **`fortna_source_id.py`** | Archive stem, Studio-safe names |
| **`fortna_motor_logic.py`** / **`fortna_device_logic.py`** | Motor chains, MCR, PE roles |
| **`fortna_hardware_io_overrides.py`** | Engineer alias / mute persistence |
| **`apply_recipe.py`** | Intake tar.gz → active RUN + meta |
| **`validate_plc_export.py`** | Export package checks |

## Permanent tests (run before claiming PASS)

```bat
python tools\scripts\test_partial_build_acceptance.py
python tools\scripts\test_es_compiler.py
python tools\scripts\test_m220_aux_identity.py
python tools\scripts\test_transport_hit_geometry.py
python tools\scripts\test_transport_area_move_positions.py
python tools\scripts\test_hardware_io_overrides.py
```

## Suggested GitHub packaging

```
tools/scripts/
  README_PARSERS.md          ← this file
  fortna_io_banks.py         ← PDF OCR + banks
  fortna_io_extract.py
  fortna_autogen.py          ← L5X + RUN IO_MAP + ES
  fortna_es_compiler.py
  fortna_studio_preflight.py
  test_*.py                  ← permanent regressions
```

Full inventory (every file, callers, classification):  
`exports/stabilization/python_script_inventory.md`
