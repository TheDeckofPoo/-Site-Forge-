# Emergency Autogen Recovery — Studio Empty Organizer

**Date:** 2026-09-13  
**Broken head:** `11c51ed`  
**Symptom:** Studio opens `ORNCCP4` but Tags/Programs appear empty.

## Correction to prior validation

`ORNCCP4_2026_09_13_1517.L5X` embedded `Git=33d1b9a` — it does **not** prove `11c51ed` works.  
Hard rule: never validate a commit with an L5X whose embedded Git provenance mismatches the commit under test.

## Root cause (exact)

Not hollow XML / not empty workbook on the 1710/1754 builds.

1. **`Divert_CFG` → missing `Track_TestOffset`** after `_strip_udts_for_missing_aois()` dropped all `Track_*` UDTs when no `TRK_*` AOIs kept.
2. **`Sawtooth_Merge_Program.L5X`** ships Context tags typed `ST_*` / `SawMergeHMI_UDT` but **no DataType bodies** (Dependencies export). Those types were never merged into the controller L5X.

Studio validates DataTypes before Tags/Programs → **controller name kept, Tags/Programs discarded**.

Function: `fortna_autogen.py` → `_strip_udts_for_missing_aois` + missing Sawtooth datatype merge.

## Fix

1. Add `tools/libraries/programs/Sawtooth_Merge_DataTypes.L5X` (ST_* / SawMerge UDT fragment).
2. Load it whenever `Sawtooth_Merge` is included.
3. `_close_datatype_member_deps()` after AOI/UDT strip (drops `Divert_CFG`; treats `FBD_TIMER` as builtin).
4. Integrity fails BUILD if unresolved tag DataTypes / member deps remain, or Git provenance mismatches.

## Fresh output (pre-commit rebuild)

`exports/current/ORNCCP4_2026_09_13_1754.L5X` — rebuild after fix; re-run after commit so Git= matches HEAD.
