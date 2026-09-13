# Studio Import Fixes — ORNCCP2

## Root cause of Curtis's 26-error log

The L5X opened was from:

`C:\dev\worktree\FortnaPlus\exports\autogen\20260913-014903-...`

That tree was on **`feature/runtime-acceptance-recovery`** (old), not
`feature/plc2-transport-fidelity`. Line numbers matched the Configio-era
generator (Address=8 with Bus Size=8, AOI_SNTP_QUERY, module-name Comm_UDT tags).

## Generator fixes (this branch)

| Studio error | Fix |
|--------------|-----|
| Chassis size exceeds allowable / ParentModule not found | **1794-AENT max Bus Size is 8.** Remap eipcfg 1..8 slots → Port Address **0..7** (match finished PLC). Never bump Bus Size above 8. |
| Slot out of range (`Address=8` with Bus Size 8) | Same remap — valid Addresses are 0..7 only |
| AOI_SNTP_QUERY missing dependency / SNTP_AOI_TAG | Keep SNTP AOI only when `AOI_TIME_ADD` + `AOI_TIME_DIFFERENCE` exist; otherwise omit SNTP tags/AOI |
| NO_PS invalid L5K structure | Emit Decorated `<Structure DataType="PS_UDT"/>` only |
| Data type mismatch on `CP2RIO*` / `PLC2_ENET1` | CommDiag uses `*_Comm` Comm_UDT names — never collide with module tag names |
| SNTP_MSG_* ConnectionPath missing | Omitted with incomplete SNTP pack |
| ConfigTag L5K mismatch on child cards | Strip ConfigTag blobs; Studio recreates catalog defaults |

## Transport full-site residual

- Store key bumped to `siteforge.transportBuild.v2` (invalidates plant-wide v1 saves)
- `load()` filters to LOCAL + EXTERNAL_REFERENCE and drops huge unscoped canvases
- RUN import clears v1 + v2

## I/O counts

Real CP_I / CP_O in the fixed candidate (not placeholders):

- **CP_I real ≈ 147**
- **CP_O real ≈ 78**

Finished oracle is ~209 / ~125 real map rungs — not 300/300. If Studio showed ~14/27 after a failed import, that was partial import from the 26 errors, not the generator's true map size.

## How to validate

1. Close all Site Forge / Electron windows
2. Launch from updated FortnaPlus: `C:\dev\worktree\FortnaPlus\desktop\Launch-SiteForge.bat`
3. Import ORNCCP2 RUN → Auto Build (should be controller-scoped)
4. Build PLC → open the **new** `exports\autogen\<timestamp>-…\*.L5X` in Studio as **File → Open**
