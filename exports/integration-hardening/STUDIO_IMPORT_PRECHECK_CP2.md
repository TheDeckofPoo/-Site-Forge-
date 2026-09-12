# Studio Import Precheck — ORNCCP2_knowledge_driven_candidate.L5X

Generated: `2026-09-12T22:05:39.503799+00:00`

- XML parses: **True**
- Static ok (no ERROR): **True**
- Studio import claimed: **False**
- SHA256: `c809fec9665c3bb51963f072480e3b5397a7402e39da977b159029b9767e2359`

## Counts

```json
{
  "errors": 0,
  "warnings": 6,
  "info": 0,
  "programs_with_main": 0,
  "programs_missing_main": 6,
  "tags": 76,
  "duplicate_tags": 0,
  "modules": 2
}
```

## Issues

- **WARNING** `missing_main_routine`: Program Area_1_Area_Slow has no Main routine
- **WARNING** `missing_main_routine`: Program Area_1_Area_Fast has no Main routine
- **WARNING** `missing_main_routine`: Program Area_1_Area_L1 has no Main routine
- **WARNING** `missing_main_routine`: Program Area_1_Area_L2 has no Main routine
- **WARNING** `missing_main_routine`: Program Sys has no Main routine
- **WARNING** `missing_main_routine`: Program IO_MAP has no Main routine

## Curtis checklist

1. Open Studio 5000
2. Import / open this L5X
3. Note any import errors/warnings
4. Confirm controller opens
5. Do not treat this precheck as PASS until Curtis reports
