# Site Forge (FortnaPlus)

**IPC → Rockwell recontrol toolkit.** Electron dashboard + Python engines that turn Fortna (FPC / SortPlus) site RUN archives into Rockwell Studio 5000 **L5X**, optional Ignition packs, Factory I/O scenes, and **Site Twin** gap-fill via PRISM + SpaceXAI.

| Branding | Where you see it |
|----------|------------------|
| **Site Forge** | Window title, `Launch-SiteForge.bat`, Electron app id / userData (`%LOCALAPPDATA%\SiteForgeDashboard`) |
| **FortnaPlus** | Repo folder name, workspace file, some export names |

Site Forge does **not** launch Studio 5000 or Ignition Designer. It generates artifacts you open yourself.

---

## Suite peers

| App | Path | Role |
|-----|------|------|
| **Site Forge** | `C:\dev\worktree\FortnaPlus` | Build PLC / transport / sorter from RUN |
| **PRISM** | `C:\dev\worktree\PRISM` | Knowledge base, vector search, site twin context |
| **ARGUS** | `C:\dev\worktree\ARGUS` | Live PLC supervisor (PE chatter, tracking) — not in this repo |
| **EchoSite 3D** | `C:\dev\worktree\echo-site-3d` | Separate Godot virtual commissioning (Logix Echo) |

---

## Who this is for

- Controls / site engineers converting **Fortna FPC** sites to **Rockwell Logix**
- People who have site **RUN `.tar.gz`**, electrical **PDFs**, and gold **O'Reilly** L5X libraries
- Teams that want Transport / Sorter / Sawtooth **design** in a dashboard and a single **Autogen compile** to L5X

---

## Repository map

```
C:\dev\worktree\FortnaPlus\
├── README.md
├── FortnaPlus.code-workspace     # VS Code / Cursor workspace (display: Site Forge)
├── dashboard\                    # UI loaded by Electron
│   ├── index.html
│   ├── fortna-plus.js            # Main dashboard logic
│   └── transport-build.js        # Transport Build UI
├── desktop\                      # Electron shell
│   ├── main.js                   # IPC → Python engines
│   ├── preload.js                # window.fortnaAPI
│   ├── package.json
│   ├── Launch-SiteForge.bat      # Preferred launcher
│   ├── Launch-FortnaPlus.bat     # Legacy alias → same path
│   ├── Launch-Electron.ps1
│   └── assets\                   # Icons
├── tools\
│   ├── scripts\                  # Python engines (see below)
│   ├── libraries\                # O'Reilly L5X + program packs
│   ├── recipes\recipes.json      # RUN table surgery recipes
│   └── templates\                # Ignition / Factory I/O templates
├── workspace\                    # Active site data (do not commit extracts)
├── exports\                      # Generated artifacts (prefer gitignore)
├── docs\                         # Engineering notes + FPC training corpus
└── docs-index\                   # documents.json (from index_docs.py)
```

### `workspace/` (live site data)

| Path | Role |
|------|------|
| `workspace/active/` | Current RUN extract (**wiped** on every re-import) |
| `workspace/active-meta.json` | Archive path, machine, conveyors, device fingerprint |
| `workspace/autogen_workbook.json` | Stable Autogen workbook (**outside** `active/` so imports do not erase design) |
| `workspace/prints/` | Electrical PDFs by panel |
| `workspace/inbox/` | Drop `.tar.gz` archives here |
| `workspace/drawings/` | CAD/PDF for Ignition layout / OCR (`drawings/README.md`) |
| `workspace/reference/excel-autogen/` | Legacy Excel / ACD / L5X reference |
| `workspace/_reno_peek/` | Multi-controller Reno peek extracts |

### `exports/` (generated)

| Path | Role |
|------|------|
| `exports/autogen/` | Timestamped Autogen L5X + reports + equipment plans |
| `exports/plc/` | PLC Export packages (L5X, CSV, `.FACTORYIO`) |
| `exports/ignition-build/` | Layout SVG, tags, Perspective packs, `LATEST.json` |
| `exports/transport-poc/` | Transport graph Apply JSON/MD |
| `exports/twin/` | Site Twin artifacts (e.g. `last_propose.json`) |
| `exports/ocr-logs/` | VFD / OCR assign logs |
| `exports/backups/` | Code / suite snapshots |

### `tools/libraries/` (compile inputs)

- Default library: `OReilly_Library_v3.L5X`
- Program packs: `IO_MAP_Program.L5X`, `Sawtooth_Merge_Program.L5X`, `Sorter_Track_Program.L5X`, `Sys_Program.L5X`, `System_Program.L5X`, `ShippingSorter_Area_L3_Program.L5X`, `WCS_Interface_TCP_IP_Program.L5X`
- AOIs / helpers: `Slow_Flt_AOI.L5X`, `TRK_Divert_WaveFunction_AOI.L5X`, `Enc_Routine_ST.L5X`, …
- Excel heritage: `autogen_VBS_test.xlsm` + `vba_extract/`

---

## Install & launch

### Prerequisites

- Windows
- Git
- Node.js / npm
- Python 3.x (`py` preferred)
- Optional: Studio 5000, Ignition, `FORTNA_PRISM_ROOT`, `XAI_API_KEY` / `XAI_MODEL`

### First-time setup

```bat
cd C:\dev\worktree\FortnaPlus\desktop
npm install
```

### Daily launch

1. Run **`desktop\Launch-SiteForge.bat`** (or `Launch-FortnaPlus.bat` — same Electron app).
2. The bat calls `Launch-Electron.ps1`, which:
   - Checks npm / Python
   - On first run, builds `docs-index\documents.json` via `tools\scripts\index_docs.py`
   - Ensures the Electron binary
   - Runs `npm start` → loads `dashboard\index.html`

**Do not** open `dashboard\index.html` in a bare browser. The UI requires `window.fortnaAPI` from Electron preload.

---

## UI tour

### Visible tabs

| Tab | Purpose |
|-----|---------|
| **I/O & Prints** | Import RUN `.tar.gz`, OCR electrical PDFs, inspect I/O banks |
| **Transport Build** | Areas, bind P### conveyors, PE roles (P/J/F), merges → Apply to Autogen |
| **Sorter Build** | Shoe Sorter or Pop-Up Divert; induct / tracking / diverts → Save |
| **Sawtooth Merge** | Collector / lanes / PEs (PLC4 pattern) → Save |
| **PLC Autogen** | Compile hub: program pack, site config, **Export L5X**, Site Twin · Gaps |
| **Docs** | Search indexed training / engineering docs |
| **Workspace** | Paths, active RUN meta, workbook status |
| **Recipes** | RUN table surgery (clone device, add PE, …) |

### Hidden but present (code kept)

- **PLC Export** — L5X scaffold + Factory I/O under `exports/plc/`
- **Ignition Build** — layout / Perspective packs under `exports/ignition-build/`

**Mental model:** Transport + Sorter + Sawtooth = **design**. Autogen = **compile**.

---

## End-to-end workflows

### 1) Import a site RUN

1. **I/O & Prints** → import controller `.tar.gz` (or drop under `workspace/inbox/`).
2. Extract lands in `workspace/active/RUN` with Fortna ASC (`FORTNA\*.asc`, `PROJECT\*.asc`, `project.cfg`).
3. `workspace/active-meta.json` records archive / machine fingerprint.
4. Optional: select electrical PDFs → `workspace/prints/`; OCR via `fortna_io_banks.py`.

### 2) Design transport

1. **Transport Build** → define areas, bind P### belts, assign PE roles (Photoeye / Jam / Full), configure merges.
2. **Apply to Autogen** → patches `workspace/autogen_workbook.json` (`fortna_transport_graph.py`).
3. Clearing a P### tag on a node then Apply removes that belt from the Transport area on the next L5X (stubs removed; RUN tags restored to site area).

### 3) Sorter / Sawtooth (optional)

- **Sorter Build** → Shoe or Pop-Up Divert → Save (`fortna_sorter_build.py` + `Sorter_Track_Program.L5X`).
- **Sawtooth Merge** → collector / lanes / PEs when RUN has `SawMerge.asc` / `SawLane.asc` → packs `Sawtooth_Merge_Program.L5X` (see `docs/SAWTOOTH_MERGE.md`).

### 4) Compile Autogen L5X

1. **PLC Autogen** → choose program pack + review site config.
2. **Export L5X Package** → `exports/autogen/<timestamp>-…/` (L5X, CSVs, reports, equipment plan).
3. Open the newest folder in Studio 5000 yourself.

`{Area}_Area_Slow` programs emit only **Conv_Flt / Conv_Jam / Conv_PE** (no empty Control_Station / Stacklight / Conv_PI scaffolds).

### 5) Site Twin · Gaps (optional)

On the Autogen tab:

1. **Refresh** gaps from the current workbook / export.
2. **Search PRISM** for similar gold patterns.
3. **Propose** (SpaceXAI if `XAI_API_KEY` set; otherwise PRISM heuristic).
4. **Apply** approved patches to the **workbook only** — never silent L5X rewrites (`docs/SITE_TWIN.md`).
5. Export L5X again.

### 6) Ignition / Factory I/O (optional, tabs hidden)

- Ignition: IPC / CLI → `fortna_ignition_build.py` / `fortna_perspective_pack.py` → follow `exports/ignition-build/COPY_TO_IGNITION.txt`.
- Factory I/O: `fortna_plc_export.py` writes `.FACTORYIO` from `tools/templates/SDK_Write_Sample.FACTORYIO`.

### Multi-controller sites

Example: MSC Reno — one RUN tar **per controller** → one L5X each. See `docs/GOLD_EQUIPMENT_TO_BUILD.md`.

---

## Data flow

```
workspace/inbox/*.tar.gz
        │  import-run / apply_recipe
        ▼
workspace/active/RUN/   (+ active-meta.json)
        │
        ├─ OCR PDFs ──► workspace/prints/ ──► exports/ocr-logs/
        │
        ├─ fortna_workbook.py ──► workspace/autogen_workbook.json
        │         ▲
        │         │ Transport Apply / Twin patches / UI edits
        │
        ├─ fortna_autogen.py ──► exports/autogen/<ts>-<run>/
        │                              └─ optional fortna_prism_ingest → PRISM
        │
        ├─ fortna_plc_export.py ──► exports/plc/  (L5X + .FACTORYIO)
        │
        ├─ ignition build / perspective ──► exports/ignition-build/
        │                              └─ copy → Ignition data/projects/
        │
        └─ fortna_transport_graph ──► exports/transport-poc/
```

**Stability rule:** The Autogen workbook lives at `workspace/autogen_workbook.json` because `workspace/active/` is cleared on every RUN import (`desktop/main.js`).

---

## Key Python scripts (`tools/scripts/`)

Full parser inventory: `tools/scripts/README_PARSERS.md`.

| Script | Role |
|--------|------|
| `fortna_asc.py` | Parse/edit tilde-delimited Fortna `.asc` |
| `fortna_io_extract.py` | I/O points, layout, controller scoping from RUN |
| `fortna_io_banks.py` | Banks + electrical PDF OCR (VFD / PowerFlex) |
| `fortna_workbook.py` | RUN → editable Autogen workbook JSON |
| `fortna_autogen.py` | Workbook + library → Studio L5X (Excel VBA replacement) |
| `fortna_plc_export.py` | RUN → L5X scaffold + Factory I/O scene |
| `fortna_transport_graph.py` | Transport graph → workbook Apply / transport-poc |
| `fortna_sorter_build.py` | Configure `Sorter_Track_Program.L5X` from Sorter UI |
| `fortna_mhs_sorter.py` | MHS sorter guideline routine builders |
| `fortna_equipment_plan.py` | Inventory RUN → equipment plan for Autogen |
| `fortna_ignition_build.py` | Layout SVG, tags, devices, POC package |
| `fortna_perspective_pack.py` | Perspective project zip / Plant_Layout |
| `fortna_prism_ingest.py` | Stage exports / twin into PRISM |
| `fortna_prism_twin.py` | Gaps · PRISM search · SpaceXAI propose · apply |
| `fortna_source_id.py` | Archive stem, Studio-safe names |
| `fortna_motor_logic.py` | Motor chains, MCR |
| `fortna_device_logic.py` | Device-class ladder from I/O + motor chains |
| `apply_recipe.py` | Extract RUN + apply recipes |
| `index_docs.py` | Build `docs-index/documents.json` |
| `validate_plc_export.py` | Validate L5X + FACTORYIO artifacts |
| `_deploy_designer_safe_ignition.py` | Copy designer-safe project into Ignition |

---

## Docs & training

| Doc | Contents |
|-----|----------|
| `docs/SITE_TWIN.md` | Site Twin UI, files, AI patch rule |
| `docs/GOLD_EQUIPMENT_TO_BUILD.md` | PLC2/4/5 gold patterns → Site Forge actions |
| `docs/gold_plc245_inventory.json` | Machine-readable gold scan |
| `docs/PLC2_TRANSPORT_MERGE_INVENTORY.md` | Merge_2to1 call sites, hold modes |
| `docs/SAWTOOTH_MERGE.md` | PLC4 gold + RUN Asc tables + pack path |
| `docs/SORTER_BUILD_UI_REVERT.md` | Sorter UI history notes |
| `docs/training/` | FPC / P&A training docx corpora (zipped + extracted) |
| `workspace/drawings/README.md` | Where to put CAD/PDF for Ignition/OCR |
| `exports/ignition-build/COPY_TO_IGNITION.txt` | Deploy steps into Ignition |

---

## Environment variables

| Variable | Purpose |
|----------|---------|
| `XAI_API_KEY` | SpaceXAI for Site Twin Propose (desktop / Python — never in renderer) |
| `XAI_MODEL` | Override model (default `grok-4.5`) |
| `FORTNA_PRISM_ROOT` | Path to PRISM worktree for twin / ingest |

Without `XAI_API_KEY`, Propose still runs in **PRISM heuristic** mode.

API base: `https://api.x.ai/v1`.

---

## Typical daily workflow

1. Launch `desktop\Launch-SiteForge.bat`.
2. **I/O & Prints** → load today’s controller `.tar.gz` (+ PDFs / OCR if needed).
3. **Transport Build** → Apply to Autogen; **Sorter** / **Sawtooth** Save as needed.
4. **PLC Autogen** → Export L5X Package.
5. Optionally Site Twin gap-fill → Export again.
6. Open newest folder under `exports/autogen/` in Studio 5000.
7. If HMI work: run Ignition build/pack → follow `COPY_TO_IGNITION.txt`.

---

## Backups & Git

- Code snapshots: `exports/backups/suite-*` and `fortnaplus-code-*.zip`
- Full worktree backup script (needs free space on D:): `C:\dev\worktree\Run-Backup-Now.ps1`
- Prefer a **private** repo
- Do **not** commit `node_modules`, RUN extracts, or full `exports/`
- After clone: `cd desktop && npm install`, then launch Electron

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| “API missing — relaunch bat” | UI opened outside Electron; use `Launch-SiteForge.bat` |
| Python engines fail | Ensure `py` / `python` on PATH; re-run launcher |
| Electron / npm issues | `cd desktop && npm install`; check Node version |
| Docs search empty | Let first launch finish `index_docs.py`, or run it manually |
| Autogen design “lost” after import | Edits live in `workspace/autogen_workbook.json`, not under `active/` |
| Site Twin Propose weak | Set `XAI_API_KEY`; ensure PRISM root is set and ingested |

Electron user data: `%LOCALAPPDATA%\SiteForgeDashboard`.

---

## Requirements (summary)

- Windows, Git, Node.js, Python 3.x  
- Optional: Studio 5000, Ignition, PRISM, SpaceXAI key
