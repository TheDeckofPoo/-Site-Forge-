# Which Site Forge files to use

**Launch:** Desktop **Site Forge** shortcut → `C:\dev\worktree\FortnaPlus\desktop\Launch-SiteForge.bat`  
**Branch:** `feature/plc2-transport-fidelity`

## PLC / Studio (open as NEW project — File → Open)

| File | Purpose |
|------|---------|
| `exports/autogen/ORNCCP2_LATEST.L5X` | **Use this** — current ORNCCP2 candidate |
| `exports/autogen/_studio_fix/OReillyGreensboro_ORNCCP2.L5X` | Same build + reports beside it |
| `exports/studio-validation/ORNCCP2_transport_fidelity_candidate.L5X` | Validation copy |

Do **not** open old timestamp folders under `exports/_archive/`.

## Keep vs archive

**Kept active**

- `exports/autogen/` (current + `_studio_fix`)
- `exports/plc2-fidelity/`
- `exports/studio-validation/`
- `exports/mscreno-aug28-regression/`
- `exports/run-discovery/`

**Compressed** (recoverable)

- `exports/_archive/old-exports-*.zip` — old campaign folders (foundation, io-truth, cp4/cp5, …)
- `exports/_archive/old-autogen-*.zip` — prior timestamped Autogen runs

## After Build PLC

Site Forge also writes a new timestamped folder under `exports/autogen/`. Prefer `ORNCCP2_LATEST.L5X` or the newest folder’s `.L5X` after each Build.
