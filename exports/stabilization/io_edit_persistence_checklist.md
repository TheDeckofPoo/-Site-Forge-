# PL-4 — I/O Edit Persistence Manual Acceptance Checklist

Status: **REVIEW_REQUIRED** for full Electron proof. Backend override persistence is covered by `test_hardware_io_overrides.py`.

## Contract

- PHYSICAL endpoint identity (`CPxRIOn:I/O.Data[s].b`) is **immutable**
- Engineer alias / spare name / Generate mute is metadata only
- Edits must survive: Enter, Tab, blur, render refresh, tab switch, Area switch, Apply, Apply to Autogen, save/reopen

## Automated coverage

| Case | Test |
|------|------|
| RUN source + engineer effective | `test_hardware_io_overrides.py` |
| Mute excludes from IO_MAP | same |
| Rename→revert purges stale name | same |
| Spare engineer name survives model rebuild | same |

## Mitigations in this build

1. Tab commits like Enter
2. `refreshHardwareIo()` skipped while `.hw-ch-name-input` focused
3. Pending edit snapshot + re-apply after model replace
4. `data-hw-dirty` marks in-progress typing

## Manual Electron checklist (Curtis)

1. Open Hardware/I/O → select a module with a SPARE bit
2. Name the spare → press **Enter** → confirm name sticks after table redraw
3. Rename another channel → press **Tab** → confirm commit before focus moves
4. Start typing a name → trigger Refresh / tab away and back → confirm pending value not wiped
5. Apply to Autogen → rebuild L5X → confirm engineer override still in workbook / IO_MAP comment
6. Confirm physical address string never changed when alias changed

If any step fails, leave status **REVIEW_REQUIRED** and capture the step number.
