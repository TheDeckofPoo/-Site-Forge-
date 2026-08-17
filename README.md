# Site Forge

IPC → Rockwell recontrol toolkit: Electron dashboard + Python engines for PLC Autogen, I/O/print crosswalk, and Ignition layout packs.

## What lives here

| Path | Role |
|------|------|
| `dashboard/` | UI (I/O & Prints, AutoGen workbook, Ignition) |
| `desktop/` | Electron shell (`Launch-SiteForge.bat`) |
| `tools/scripts/` | Python: `fortna_autogen.py`, `fortna_workbook.py`, ignition builders |
| `tools/libraries/` | O'Reilly L5X library + program packs + VBA extracts |
| `exports/` | Generated L5X / ignition folders (**gitignored** — rebuild locally) |
| `workspace/` | Active RUN extract, prints (**mostly gitignored**) |

## Local workflow

1. Load `.tar.gz` on **I/O & Prints** (optional PDFs / OCR).
2. **PLC Autogen** → Build workbook → edit dropdowns → Generate L5X.
3. **Ignition** → Build + deploy (timestamped folders under `exports/ignition-build/`).

## Git / GitHub

- **Private** GitHub repo recommended (site libraries + Fortna process knowledge).
- Do not commit `node_modules`, RUN extracts, or full `exports/` trees (see `.gitignore`).
- After clone: `cd desktop && npm install`, then launch Electron.

## Requirements

- Windows, Git, Node.js (for Electron), Python 3.x  
- Optional: Ignition gateway for HMI deploy, Studio 5000 for L5X open  
