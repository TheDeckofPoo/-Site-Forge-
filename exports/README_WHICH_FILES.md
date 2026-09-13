# Which Site Forge files to use

**Launch:** Desktop **Site Forge** shortcut → `C:\dev\worktree\FortnaPlus\desktop\Launch-SiteForge.bat`  
**Branch:** `feature/plc2-transport-fidelity`

## PLC / Studio (open as NEW project — File → Open)

| File | Purpose |
|------|---------|
| `exports/current/{CONTROLLER}_{YYYY_MM_DD_HHMM}.L5X` | **Use this** — single engineer-facing L5X for the current build |
| `exports/current/build_manifest.json` | Exact path + SHA256 + controller + RUN provenance |

Do **not** look for `{CONTROLLER}_LATEST.L5X` — that duplicate is no longer written.  
Do **not** open random files under `exports/autogen/` history, `studio-validation`, or candidate folders unless debugging.

## Keep vs archive

**Engineer-facing**

- `exports/current/` — one timestamped L5X + `build_manifest.json` (+ `LATEST.json` pointer)

**Diagnostics / history**

- `workspace/.internal/builds/{build_id}/`
- `exports/autogen/history/`

## After Build PLC

1. Read `exports/current/build_manifest.json` → `output_path`
2. Open **that exact** `.L5X` in Studio (File → Open as new project)
3. Site Forge **Open File Location** / **Copy Full Path** use the same manifest path
