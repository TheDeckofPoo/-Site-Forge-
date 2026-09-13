# Site Forge — Runtime Dataflow (Import → Build PLC)

**Branch:** `feature/runtime-acceptance-recovery`  
**Purpose:** Document the *product* path Curtis exercises through Electron, and where data was being lost.

## Required product contract

```
IMPORT RUN
     ↓
AUTOMATIC DISCOVERY
     ↓
TRANSPORT AUTO-POPULATED
SAWTOOTH AUTO-POPULATED IF PRESENT
SORTER AUTO-POPULATED IF PRESENT
     ↓
ENGINEER REVIEW / CORRECT
     ↓
BUILD PLC
     ↓
SAME CANONICAL MODEL GENERATES L5X
```

No simulator / Prefill / demo button may be required to transfer discovered RUN information into an editor.

## Exact runtime chain

| Step | Component | Path / IPC |
|------|-----------|------------|
| 1 | Launch | `desktop/Launch-SiteForge.bat` → Electron |
| 2 | Import RUN | UI → `fortnaAPI.importRun(path)` → IPC `import-run` |
| 3 | Archive extract | `desktop/main.js` → `tools/scripts/apply_recipe.py import` |
| 4 | Active workspace | `workspace/active/RUN` + `workspace/active-meta.json` |
| 5 | Discovery | `fortna_run_workspace_discover.py --run-dir … --out exports/run-discovery/<MACHINE>` |
| 6 | SiteModel persist | `exports/run-discovery/<MACHINE>/site_model.json` **and** `workspace/active/site_model.json` |
| 7 | UI refresh | `importRunPackage` → workbook build → **`applySiteModelToEditors`** |
| 8 | Editor population | `editors.sawtooth` / `editors.sorter` / transport workbook rows |
| 9 | Canonical workbook | `workspace/autogen_workbook.json` includes `conveyors` + `sawtooth_build` + `sorter_build` |
| 10 | Build PLC | UI → `fortnaAPI.autogenGenerate` → IPC `autogen-generate` |
| 11 | L5X generator | `fortna_autogen.py from-run --with-io-map --workbook …` |
| 12 | Assertions | Fail closed if IO_MAP mapped=0 with mappable points, empty PE logic, missing Sawtooth when requested |

## Canonical model (one path)

| Artifact | Role |
|----------|------|
| `workspace/active/site_model.json` | Discovered SiteModel for the active RUN |
| `workspace/autogen_workbook.json` | Engineer-editable Autogen input (conveyors, areas, `sawtooth_build`, `sorter_build`) |
| Build PLC args | Always `from-run` + `--with-io-map` (unless IO checkbox off) + `--workbook` |

### Parallel paths bridged / demoted

| Legacy / parallel | Status |
|-------------------|--------|
| `localStorage` `fortna_sawtooth_build` / `fortna_sorter_build` | Cleared on fresh Import so demo state cannot override RUN |
| DEV Prefill PLC4 button | Remains for development only; labeled **DEV**; confirm dialog; **not** required for acceptance |
| `exports/run-discovery/site_model.json` (unscoped) | Still updated as latest pointer; primary writes are per-machine |
| Excel / VBA autogen | Legacy only; UI default is Python `from-run` |

## Where data was lost (Curtis FAIL root cause)

1. **Discovery ran but UI ignored SiteModel**  
   `import-run` returned `discovery`, but `importRunPackage` never applied `editors.sawtooth` / `editors.sorter` to dashboard state.

2. **Prefill PLC4 was a hardcoded Greensboro demo**  
   Engineers had to press it to see Sawtooth fields — discovery already knew lanes/collector/encoder.

3. **Build PLC reloaded disk workbook and dropped editor overlays**  
   Generate path loaded `autogen_workbook.json` from disk and passed `workbook: undefined`, wiping in-memory `sawtooth_build` / `sorter_build` that had never been saved.

4. **Cross-machine discovery overwrite**  
   Discovery always wrote `exports/run-discovery/` without a machine subdirectory, so CP2/CP4/CP5 stomped each other.

5. **Script-good ≠ UI-good**  
   CLI `from-run --with-io-map` could produce modules + IO_MAP rungs while the UI path emitted Transport-only / NOP IO_MAP when workbook/editor state diverged.

## Fixes on this branch

- Per-machine discovery out + copy to `workspace/active/site_model.json`
- IPC `get-site-model` + preload `getSiteModel`
- `applySiteModelToEditors` after Import (Sawtooth + Sorter auto-populate; packs auto-checked when ready)
- Generate merges disk transport with in-memory SiteModel overlays and saves before `from-run`
- Hard generation assertions in `fortna_autogen.py`
- `site_model_to_sawtooth_build` / `site_model_to_sorter_build` bridge helpers
- Runtime acceptance script exercising the same engines as Electron IPC

## Subsystem generation contract (UI)

Shown on PLC Autogen compile hub:

| Subsystem | States |
|-----------|--------|
| TRANSPORT | READY |
| IO | READY / BLOCKED |
| SAWTOOTH | READY / CONFIG REQUIRED / N/A |
| SORTER | PARTIAL / CONFIG REQUIRED / NOT SUPPORTED / N/A |
| WCS | NOT SUPPORTED |

## Verification

- Engine path: `python tools/scripts/fortna_runtime_acceptance_recovery.py`
- Product path: `desktop/Launch-SiteForge.bat` → Import CP2/CP4/CP5 → inspect tabs → Build PLC
- Evidence: `exports/runtime-recovery/`, `exports/studio-validation/*_ui_candidate.L5X`, `docs/RUNTIME_ACCEPTANCE_REPORT.md`
