# ORINDYAC6 field failure root causes (b1f5886 / 0123 L5X)

## Gate B — first Safety membership loss boundary

**Boundary:** `fortna_autogen.load_from_run` → `AutogenInput.safety_zones`

```python
safety_zones=[f"{a.replace('_Area', '')}_ESZone1" for a in areas]
```

This **auto-minted empty** shells:

- `Zone1_ESZone1`
- `ORINDYAC6_ESZone1`
- `Default_Area_ESZone1`

with conveyors but **members=[]**, independent of Curtis’s Safety Apply.

Even when UI assignments existed in memory, Autogen IR preferred these empty transport/area shells → ES NOP-only Main_Routine.

**Fix:** `safety_zones=[]` by default; zones/membership only from `workbook.safety_build` / engineer Apply.

**UI boundary (contributing):** Assign did not hard-upsert members into `AS.safety_build` before `buildClientModel`, so rebuild races could drop the engineer zone from the visible list.

**Fix:** mutateZone upserts members into `safety_build` before rebuild; never wipe non-empty members with empty overlay; categorized unassigned list; keep zone selected with confirmation status.

## Gate C — Sawtooth

Sawtooth pack included because overlay SawMerge/SawLane rows existed for the site and were Applied without requiring collector/lanes on **this machine’s** conveyors. Ordinary CP6 2→1 merges are unrelated.

**Fix:** machine-scoped inclusion gate; out-of-scope → strip from `include_programs`; provenance `why Sawtooth_Merge`.

## Gate D — Studio Data mismatch

`String_20.DATA` / `Barcode_String.DATA` declared as **SINT[N]** in DataType, but Decorated emitted `DataType="String_20"` / `Barcode_String`.

**Fix:** emit DATA as **SINT** with Dimensions per DataTypeDef (generic).
