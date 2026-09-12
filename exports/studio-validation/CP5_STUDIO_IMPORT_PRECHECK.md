# Studio Import Precheck — ORNCCP5_candidate_v2.L5X

Generated: `2026-09-12T23:10:47.454124+00:00`

- XML parses: **True**
- Static ok (no ERROR): **True**
- Studio import claimed: **False**
- SHA256: `27c5a003f8f5f9fb2e402057a39f7572d1e47cafc957ca9102deea86a6c9d99e`

## Counts

```json
{
  "errors": 0,
  "warnings": 6,
  "info": 0,
  "programs_with_main": 0,
  "programs_missing_main": 6,
  "tags": 727,
  "duplicate_tags": 0,
  "modules": 63
}
```

## Issues

- **WARNING** `missing_main_routine`: Program ORNCCP5_Area_Slow has no Main routine
- **WARNING** `missing_main_routine`: Program ORNCCP5_Area_Fast has no Main routine
- **WARNING** `missing_main_routine`: Program ORNCCP5_Area_L1 has no Main routine
- **WARNING** `missing_main_routine`: Program ORNCCP5_Area_L2 has no Main routine
- **WARNING** `missing_main_routine`: Program Sys has no Main routine
- **WARNING** `missing_main_routine`: Program IO_MAP has no Main routine

## Curtis checklist

1. Open Studio 5000
2. Import / open this L5X
3. Note any import errors/warnings
4. Confirm controller opens
5. Do not treat this precheck as PASS until Curtis reports
