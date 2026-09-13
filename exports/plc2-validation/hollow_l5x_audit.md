# Hollow CP4 L5X Audit

**Branch:** `feature/plc2-transport-fidelity`  
**Date:** 2026-09-13  
**Scope:** Root-cause of perceived hollow L5X + export UX / integrity fixes.

## Verdict

**Latest engineer L5X is NOT hollow.**

| Artifact | Result |
|----------|--------|
| `exports/current/ORNCCP4_2026_09_13_1517.L5X` | ~3.48 MB · 8 programs · 31 Module · 838 tags · **69 P###_Conv** · Fast/Slow/L1/L2 · IO_MAP |
| Programs | `ORNCCP4_Area_Slow`, `ORNCCP4_Area_Fast`, `ORNCCP4_Area_L1`, `ORNCCP4_Area_L2`, `System`, `Sys`, `Sawtooth_Merge`, `IO_MAP` |
| Build input | 70 conveyors from RUN (`load_from_run`); report conveyor_count=70 |

Structurally hollow comparison artifact (diagnostic only):  
`exports/studio-validation/ORNCCP4_knowledge_driven_candidate.L5X` (~692 KB · 2 modules · 76 tags).

## Root cause of perceived hollow

1. **Export UX clutter** — `exports/current` held multiple timestamped L5Xs **plus** `{controller}_LATEST.L5X` (byte-duplicate of the newest). Engineers / Open Output Folder landed on the folder, not the exact file named in `build_manifest.json`.
2. **Empty disk workbook risk** — `workspace/autogen_workbook.json` can be cleared (`conveyors:[]`) while active RUN is also cleared. A Build without in-memory workbook / without a loaded RUN can emit a hollow project. Empty workbook alone does **not** wipe RUN conveyors (`apply_workbook_to_input` short-circuits on empty rows), but the combination of cleared RUN + empty workbook is dangerous.
3. **Open File Location** previously opened `exports/current` generically; without a prominent absolute path, the wrong L5X was easy to open in Studio.

## Fixes applied

| Area | Change |
|------|--------|
| `fortna_autogen.py` | **Stop writing** `{controller}_LATEST.L5X`. After integrity-pass write, `cleanup_exports_current_for_controller` keeps only the new timestamped L5X + matching `.manifest.json`; preserves `build_manifest.json` + `LATEST.json`. |
| README | `exports/autogen/README_CURRENT_OUTPUT.txt` instructs: open the single timestamped L5X named in `build_manifest.json` — no physical `_LATEST.L5X`. |
| Integrity | Post-write `validate_l5x_output_integrity`: size, RSLogix/Controller/Tags/Programs/Tasks, P###_Conv vs conveyor model, Module count vs hardware model, IO_MAP Program when enabled. Fail closed with explicit messages; does **not** patch L5X. |
| Stage audit | `report.build_stage_audit`: `run_or_workbook_conveyors → generated_conveyors → l5x_p_conv_tags` and `expected_modules → l5x_module_count`. |
| Empty workbook | `from-run`: if workbook has 0 conveyors but RUN has conveyors, keep/restore RUN; if workbook overlay zeros transport while RUN had devices → hard fail. |
| UI | Open Output Folder → `exports/current`. Open File Location / Copy Full Path prefer exact `autogenState.lastL5x` (manifest `output_path`), refuse `_LATEST`. BUILD SUCCESS card shows absolute L5X path. |
| Test | `tools/scripts/test_export_current_single_l5x.py` |

## Boundary counts (audit snapshot)

```
run_or_workbook_conveyors (70 from RUN build) → generated_conveyors (70) → l5x_p_conv_tags (69)
expected_modules (~33 io_module_count) → l5x_module_count (31)
```

## Engineer rule

After Build PLC, open **only** the absolute path on the BUILD SUCCESS card / `build_manifest.json` → `output_path`. Do not hunt for `_LATEST.L5X`.
