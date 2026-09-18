# Studio Import Precheck — plc5_sorter_hotbuild_fixed.L5X

Generated: `2026-09-18T06:54:23.149956+00:00`

- XML parses: **True**
- Static ok (no ERROR): **False**
- Studio import claimed: **False**
- SHA256: `86ba2bd982e2aa0997b262a51430612dc434b3a9dc2581dc78dc89fbe2cda24c`

## Counts

```json
{
  "errors": 8,
  "warnings": 1,
  "info": 1,
  "programs_with_main": 1,
  "programs_missing_main": 0,
  "tags": 295,
  "duplicate_tags": 0,
  "modules": 0,
  "programs": 1,
  "tasks": 0,
  "datatypes": 0,
  "controller_tags": 295
}
```

## Issues

- **WARNING** `datatypes`: DataTypes block missing
- **INFO** `modules`: No Module elements (may be OK for soft controller packs)
- **ERROR** `invalid_member_specifier`: PLC OPERAND ERROR Program:Sorter_Track Routine:Divert_Lane_Status Rung:51 XIC Operand:P504_AtSpeedExtraTimer.DN DataType:TIMER Invalid segment:DN
- **ERROR** `invalid_member_specifier`: PLC OPERAND ERROR Program:Sorter_Track Routine:Divert_Lane_Status Rung:52 XIC Operand:P506_AtSpeedExtraTimer.DN DataType:TIMER Invalid segment:DN
- **ERROR** `invalid_member_specifier`: PLC OPERAND ERROR Program:Sorter_Track Routine:Divert_Lane_Status Rung:53 XIC Operand:P508_AtSpeedExtraTimer.DN DataType:TIMER Invalid segment:DN
- **ERROR** `invalid_member_specifier`: PLC OPERAND ERROR Program:Sorter_Track Routine:Divert_Lane_Status Rung:54 XIC Operand:P509_AtSpeedExtraTimer.DN DataType:TIMER Invalid segment:DN
- **ERROR** `invalid_member_specifier`: PLC OPERAND ERROR Program:Sorter_Track Routine:Divert_Lane_Status Rung:55 XIC Operand:P510_AtSpeedExtraTimer.DN DataType:TIMER Invalid segment:DN
- **ERROR** `invalid_member_specifier`: PLC OPERAND ERROR Program:Sorter_Track Routine:Divert_Rate_Limit Rung:1 XIO Operand:Divert_Rate_Limit_Timer.DN DataType:TIMER Invalid segment:DN
- **ERROR** `invalid_member_specifier`: PLC OPERAND ERROR Program:Sorter_Track Routine:Scanner Rung:2 XIC Operand:SCN504:I.ConnectionFaulted DataType:— Invalid segment:SCN504
- **ERROR** `invalid_member_specifier`: PLC OPERAND ERROR Program:Sorter_Track Routine:Scanner Rung:4 XIC Operand:P504_Scanner_ResultsAvailable_Timer.DN DataType:TIMER Invalid segment:DN

## Curtis checklist

1. Open Studio 5000
2. Import / open this L5X
3. Note any import errors/warnings
4. Confirm controller opens
5. Do not treat this precheck as PASS until Curtis reports
