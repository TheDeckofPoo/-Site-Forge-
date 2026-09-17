# Which Site Forge files to use

**Launch:** Desktop **Site Forge** shortcut → `C:\dev\worktree\FortnaPlus\desktop\Launch-SiteForge.bat`  
**Branch:** `feature/plc2-transport-fidelity`  
**Offline pack:** `exports/stabilization/README.md` (read if resuming without chat)

## PLC / Studio (open as NEW project — File → Open)

| File | Purpose |
|------|---------|
| `exports/current/{CONTROLLER}_{YYYY_MM_DD_HHMM}.L5X` | **Preferred** — timestamped engineer-facing L5X |
| `exports/current/ORNCCP2.L5X` | Latest from-json / CLI regenerate (may overwrite) |
| `exports/current/build_manifest.json` | Exact path + SHA256 + controller + RUN + `es_program` |
| `exports/current/LATEST.json` | Pointer to last UI export |

Do **not** look for `{CONTROLLER}_LATEST.L5X` — that duplicate is no longer written.  
Do **not** open random files under `exports/autogen/` history, `studio-validation`, or candidate folders unless debugging.

### PLC2 continuity snapshots (keep)

| File | Notes |
|------|--------|
| `ORNCCP2_2026_09_17_1106.L5X` | Curtis acceptance before ES shell |
| `ORNCCP2.L5X` | Post shell / punch-list / partial-build lineage |
| `autogen_input.json` | Effective INCLUDED model for regenerate |
| `autogen_report.json` / `.txt` | Last build report |

## Stabilization / offline handoff

| Path | Purpose |
|------|---------|
| `exports/stabilization/` | **Do not delete** — contracts, inventories, acceptance JSON |
| `exports/stabilization/partial_build_contract.md` | Incremental Build PLC rules |
| `exports/stabilization/python_script_inventory.md` | Script inventory (no cleanup yet) |

## Keep vs archive

**Engineer-facing**

- `exports/current/` — L5X + `build_manifest.json` (+ `LATEST.json` pointer)
- `exports/stabilization/` — offline continuity

**Diagnostics / history**

- `workspace/.internal/builds/{build_id}/`
- `exports/autogen/history/`
- `exports/transport-poc/` — research dumps (optional)

**Do not commit mass deletions** of old `exports/backups` / POC trees just to “clean up.” Inventory first (`exports/stabilization/python_script_inventory.md` pattern).

## After Build PLC

1. Read `exports/current/build_manifest.json` → `output_path`
2. Check `es_program.status` — `REVIEW_REQUIRED` is OK for partial Safety (shell)
3. Open **that exact** `.L5X` in Studio (File → Open as new project)
4. Site Forge **Open File Location** / **Copy Full Path** use the same manifest path

## Partial build reminder

Unassigned RUN equipment must remain **FOUND / REVIEW**, not silently GENERATED.  
Only **INCLUDED** conveyors/areas from Transport Apply + workbook `include` feed Autogen.
