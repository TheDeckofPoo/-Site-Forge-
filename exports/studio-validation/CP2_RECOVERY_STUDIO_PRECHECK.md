# Studio Import Precheck — ORNCCP2_recovery_validation.L5X

Generated: `2026-09-13T02:31:04.312375+00:00`

- XML parses: **True**
- Static ok (no ERROR): **True**
- Studio import claimed: **False**
- SHA256: `df09fa9e410b1ec098bf013b314bc7ac85578cb7e9ff4f0c6e139b8e51f843ce`

## Counts

```json
{
  "errors": 0,
  "warnings": 7,
  "info": 0,
  "programs_with_main": 0,
  "programs_missing_main": 7,
  "tags": 574,
  "duplicate_tags": 0,
  "modules": 39
}
```

## Issues

- **WARNING** `missing_main_routine`: Program ORNCCP2_Area_Slow has no Main routine
- **WARNING** `missing_main_routine`: Program ORNCCP2_Area_Fast has no Main routine
- **WARNING** `missing_main_routine`: Program ORNCCP2_Area_L1 has no Main routine
- **WARNING** `missing_main_routine`: Program ORNCCP2_Area_L2 has no Main routine
- **WARNING** `missing_main_routine`: Program System has no Main routine
- **WARNING** `missing_main_routine`: Program Sys has no Main routine
- **WARNING** `missing_main_routine`: Program IO_MAP has no Main routine

## Curtis checklist

1. Open Studio 5000
2. Import / open this L5X
3. Note any import errors/warnings
4. Confirm controller opens
5. Do not treat this precheck as PASS until Curtis reports
