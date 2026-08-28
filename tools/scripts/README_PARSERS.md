# FortnaPlus parsers & scrapers (credit / GitHub inventory)

These are the main **customer-facing extraction scripts** in FortnaPlus.
Use this list when publishing to GitHub so the scrape/parse work is visible and credited.

## RUN / tar.gz (primary site data)

| Script | What it scrapes | Output |
|--------|-----------------|--------|
| **`fortna_asc.py`** | Fortna `.asc` table format (headers + rows) | Shared reader for all ASC tables |
| **`fortna_io_extract.py`** | `Conveyor.asc` I/O points, drawing page #, device class | PE/motor/VFD rows, bank.bit, print page |
| **`fortna_io_banks.py`** | Banks + **electrical PDF OCR** for VFD params | Bank inventory, VFD print #, PowerFlex tables |
| **`fortna_workbook.py`** | RUN → editable conveyor workbook | Area / TYPE / Exit PE dropdowns (Inputdata replacement) |
| **`fortna_autogen.py`** | RUN + library L5X → Studio project | Programs, tags, **IO_MAP**, Flex modules |
| **`fortna_plc_export.py`** | RUN → Studio scaffold + Factory I/O | Tags CSV, L5X package, FIO scene |

### IO_MAP sources (important)

| Source | When used | What it is |
|--------|-----------|------------|
| **RUN map (default)** | Always for new sites (ORDENCP4, etc.) | Built from `Conveyor.asc` Bank.Bit + `EIPCSV` → `CP1RIO…CP4RIO` |
| **Gold Excel IO_MAP** | Greensboro-style CP5/CP6/CP7 only | Finished Studio export `tools/libraries/programs/IO_MAP_Program.L5X` merged in. **Not** a general scraper — a site-specific gold program. Auto-blocked when this site’s word map is CP1–CP4. |

“Gold” in this repo means **reference / finished O'Reilly library artifacts** (L5X programs, sealed AOIs), not a separate product name.

## Electrical prints (VFD / PowerFlex)

| Landmark on the drawing (red boxes) | Parser hook |
|-------------------------------------|-------------|
| **VFD title** `VFD501B-2` + catalog `(25B-…)` | `_ocr_regions_for_vfd_ids`, `_normalize_vfd_id` |
| **POWERFLEX terminal block** | Page has PowerFlex table → spatial column split |
| **PAR # / PARAMETER NAME / PROGRAMMED VALUE** | `_PF_CODED_LINE` / `_PF_LINE` → `extract_vfd_params_from_text` |
| **Bottom title** `VFD WIRING – (VFD312, VFD412)` | `_vfd_ids_from_wiring_title` |

Entry points:

- `ocr_print_pdfs` / `attach_print_params_to_drives` in **`fortna_io_banks.py`**
- UI: FortnaPlus → I/O & Prints → OCR panels

## Ignition / HMI

| Script | What it builds |
|--------|----------------|
| **`fortna_ignition_build.py`** | Layout SVG, devices, **tags_import.json**, interactive test HTML |
| **`fortna_perspective_pack.py`** | Perspective project zip + Plant_Layout views |
| **`fortna_ignition_extract.py`** | Helpers for EIP / device maps |

## Transport Build

| Script | Role |
|--------|------|
| **`fortna_transport_graph.py`** | Areas + PE roles (P/J/F) + merges → workbook Apply; clear P### removes Transport emit |

## PRISM / knowledge corpus / Site Twin

| Script | Role |
|--------|------|
| **`fortna_prism_ingest.py`** | Dedupe + ingest exports; **`stage_twin`** → `twin/gaps.json` |
| **`fortna_prism_twin.py`** | Load gaps · PRISM search · SpaceXAI propose · apply workbook patches |
| **`fortna_prism_seed.py`** / **`fortna_prism_build.py`** | Seed L5X snippets for vector DB |

Site Forge UI: **PLC Autogen → Site Twin · Gaps** (Refresh / Search PRISM / Propose gap-fill).

## Supporting

| Script | Role |
|--------|------|
| **`fortna_source_id.py`** | Archive stem, Studio-safe names (`OReillyDC27_ORDENCP4`) |
| **`fortna_motor_logic.py`** / **`fortna_device_logic.py`** | Motor chains, MCR, PE roles |
| **`apply_recipe.py`** | Intake tar.gz → active RUN + meta |
| **`validate_plc_export.py`** | Export package checks |

## Suggested GitHub packaging

```
tools/scripts/
  README_PARSERS.md          ← this file
  fortna_io_banks.py         ← PDF OCR + banks (star)
  fortna_io_extract.py
  fortna_autogen.py          ← L5X + RUN IO_MAP
  fortna_workbook.py
  fortna_ignition_build.py
  fortna_perspective_pack.py
  fortna_plc_export.py
  fortna_asc.py
  fortna_source_id.py
  …
tools/libraries/
  OReilly_Library_v3.L5X     ← sealed AOIs + gold reference
  programs/
    IO_MAP_Program.L5X       ← gold Excel IO_MAP (Greensboro)
    Sys_Program.L5X
    …
```

Credit line example:

> FortnaPlus site parsers by Curtis Kricke / xAI-assisted FortnaPlus tooling —  
> RUN ASC extract, Flex EIP word map, PowerFlex print OCR, Studio L5X autogen, Ignition Perspective pack.

---

*Generated for FortnaPlus worktree. Keep this file in the repo when you push to GitHub.*
