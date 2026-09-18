# Site Forge — Launch Runtime Provenance

**Branch:** `feature/plc2-transport-fidelity`  
**Purpose:** Document every launcher path so engineers never run a stale worktree by accident.  
**Blind rule:** Launchers + dashboard + desktop only (this checkout).

---

## Recommended entry (tracks this checkout)

| Item | Value |
|------|-------|
| **Bat** | `C:\Dev\worktree\FortnaPlus\desktop\Launch-SiteForge.bat` |
| **Resolution** | `cd /d "%~dp0"` then `Launch-Electron.ps1` next to the bat |
| **CWD at Electron start** | `…\FortnaPlus\desktop` |
| **Executable** | `npm start` → `electron .` → `desktop\node_modules\electron\dist\electron.exe` |
| **Main** | `desktop\main.js` |
| **REPO_ROOT** | `path.join(__dirname, '..')` → FortnaPlus repo root |
| **Dashboard** | `REPO_ROOT\dashboard\index.html` (via `win.loadFile`) |
| **Python** | First of `py` / `python` / `python3` on PATH (also recorded in provenance) |
| **Compiler scripts** | `REPO_ROOT\tools\scripts\` |
| **Worktree / branch** | Whatever git reports from this repo root |

`desktop\Launch-FortnaPlus.bat` is a **legacy alias** with the same body as `Launch-SiteForge.bat`.

---

## Parent launcher (sibling layout)

| Item | Value |
|------|-------|
| **Bat** | `C:\Dev\worktree\Launch-FortnaPlus.bat` |
| **Resolution (fixed)** | `cd /d "%~dp0FortnaPlus\desktop"` — sibling of the bat’s folder |
| **Effect** | Tracks the FortnaPlus folder next to the bat (this worktree when bat lives in `C:\Dev\worktree\`) |
| **Stale-worktree risk** | **NO** after fix (was **YES** when hardcoded to `C:\dev\worktree\FortnaPlus\desktop`) |

Still prefer `FortnaPlus\desktop\Launch-SiteForge.bat` when working inside a named checkout.

---

## Chain: bat → ps1 → npm → Electron → dashboard

```
Launch-SiteForge.bat  (%~dp0 = desktop\)
  → Launch-Electron.ps1
       cwd = desktop\
       repoRoot = parent of desktop\
       writes desktop\.runtime_build.json  (git rev-parse + optional python collector)
       npm start
         → electron .
              main.js  REPO_ROOT = join(__dirname, '..')
              loadFile(REPO_ROOT/dashboard/index.html)
              IPC get-runtime-provenance / runtime-feature-self-check
```

---

## Runtime provenance fields (Help → Runtime)

Visible in the Help drawer **Runtime** section and title-bar SHA chip (`#sf-runtime-sha`):

| Field | Source |
|-------|--------|
| Git SHA / short SHA | `git rev-parse` from REPO_ROOT, else `desktop/.runtime_build.json` |
| Branch | `git rev-parse --abbrev-ref HEAD` |
| Build/start timestamp | App start ISO time (`startedAt`) |
| Repo / source root | git toplevel / REPO_ROOT |
| Dashboard source | `…/dashboard/index.html` |
| Python / compiler source | interpreter path + `tools/scripts` |
| Mode | `dev` or `packaged` (`app.isPackaged`) |
| Executable / CWD | `process.execPath` / `process.cwd()` |

**Copy Runtime Info** (`#sf-help-copy-runtime`) copies provenance JSON + last diagnostics to the clipboard.

Collector: `tools/scripts/fortna_runtime_provenance.py`  
Fallback file: `desktop/.runtime_build.json` (gitignored; written at launch).

---

## Gate 2 — Feature self-check (Help → Diagnostics)

Exercises **live functions** (not source-string greps):

| Check | How |
|-------|-----|
| Help drawer | `#sf-help-drawer` + `#btn-sf-help` present |
| I/O ownership renderer | `hwChannelEndpointLabel({ owner_state: 'UNRESOLVED_OWNER' })` → `"UNRESOLVED OWNER"` |
| VFD symbol classifier | `classifyDevice('VFD500A')` → `vfd`; `P100` → `conveyor` |
| IO_MAP classifier (python) | `classify_cp_io_operand(...)` → `NETWORK_DEVICE_STATUS` via IPC |

Window API: `window.SiteForgeDiagnostics` (`classifyDevice`, `hwChannelEndpointLabel`, `runFeatureSelfCheck`).

---

## Exact normal-launch path

```
C:\Dev\worktree\FortnaPlus\desktop\Launch-SiteForge.bat
```

Equivalent parent entry (after relative fix):

```
C:\Dev\worktree\Launch-FortnaPlus.bat
  → %~dp0FortnaPlus\desktop\Launch-Electron.ps1
```
