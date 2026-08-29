# Site Forge (FortnaPlus)

IPC → Rockwell recontrol toolkit: Electron dashboard + Python engines for PLC Autogen, Transport Build, I/O/print crosswalk, Ignition packs, and **Site Twin** gap-fill (PRISM + SpaceXAI).

## What lives here

| Path | Role |
|------|------|
| `dashboard/` | UI — I/O & Prints, **PLC Autogen** (+ Site Twin · Gaps), Transport Build, Ignition |
| `desktop/` | Electron shell (`Launch-SiteForge.bat` / desktop **Site Forge**) |
| `tools/scripts/` | Python engines (see below) |
| `tools/libraries/` | O'Reilly L5X library + program packs |
| `exports/` | Generated L5X / ignition / transport-poc / twin (**gitignored**) |
| `workspace/` | Active RUN, prints, stable `autogen_workbook.json` |

## Suite

| App | Path | Role |
|-----|------|------|
| **Site Forge** | this repo | Build PLC from RUN + Transport |
| **PRISM** | `C:\dev\worktree\PRISM` | Knowledge / vector search / site twin |
| **ARGUS** | `C:\dev\worktree\ARGUS` | Live PLC supervisor (PE chatter, tracking) |

## Local workflow

1. **I/O & Prints** → load `.tar.gz` (+ optional PDFs / OCR).
2. **Transport Build** → areas, bind P###, PE roles (P/J/F), merges → **Apply to Autogen**.
3. **Sorter Build** → choose **Shoe Sorter** or **Pop-Up Divert** → induct / tracking / diverts → **Save**.
4. **Sawtooth Merge** (optional) → collector / lanes / PEs (PLC4 pattern; RUN has `SawMerge.asc` / `SawLane.asc`) → **Save**.
5. **PLC Autogen** (compile hub) → program pack → review site config → **Export L5X Package**.
6. **Site Twin · Gaps** → Refresh / Search PRISM / Propose → Apply approved → Export again.
7. Open L5X in Studio yourself (Site Forge does not launch Studio).

**Nav note:** PLC Export and Ignition Build tabs are hidden (code kept). Design = Transport + Sorter + Sawtooth; compile = Autogen.

### Clear a conveyor tag
Clear P### on a Transport node → **Apply** → that belt leaves the Transport area in the next L5X (stubs removed; RUN tags restored to site area).

### Area Slow programs
`{Area}_Area_Slow` emits only **Conv_Flt / Conv_Jam / Conv_PE** (no empty Control_Station / Stacklight / Conv_PI scaffolds).

## Key Python scripts

| Script | Role |
|--------|------|
| `fortna_autogen.py` | RUN → L5X (Fast/Slow/Merge/IO_MAP/System) |
| `fortna_workbook.py` | Autogen workbook overlay + stubs |
| `fortna_transport_graph.py` | Transport Apply → areas / PE roles / merges |
| `fortna_prism_ingest.py` | Stage exports + **site twin** into PRISM |
| `fortna_prism_twin.py` | Load gaps · PRISM search · SpaceXAI propose · apply patches |

## SpaceXAI (Site Twin)

- Env: `XAI_API_KEY` (desktop / Python process — never in renderer)
- API: `https://api.x.ai/v1` · model `grok-4.5` (override with `XAI_MODEL`)
- Without a key, Propose still runs in **PRISM heuristic** mode

## Backups

- Code snapshot: `exports/backups/suite-*` and `fortnaplus-code-*.zip`
- Full worktree → `D:\WorktTree` via `C:\dev\worktree\Run-Backup-Now.ps1` (needs free space on D:)

## Git / GitHub

- Private repo recommended. Do not commit `node_modules`, RUN extracts, or full `exports/`.
- After clone: `cd desktop && npm install`, then launch Electron.

## Requirements

- Windows, Git, Node.js, Python 3.x  
- Optional: Studio 5000, Ignition, `FORTNA_PRISM_ROOT`, `XAI_API_KEY`
