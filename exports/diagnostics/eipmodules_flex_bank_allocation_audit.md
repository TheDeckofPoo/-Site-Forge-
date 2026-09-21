# 1794 FLEX EIPModules bank allocation audit

## Decision

**Production promotion JUSTIFIED** as *derived effective banks* when raw EIPModules IB/OB are uniformly zero.

Raw InputBank/OutputBank remain 0. Matching uses effective_* with provenance eipmodule_layout_from_size_slot / assign_how configio_bank_match_derived_from_eipmodule_layout.

## Algorithm (validated)

1. in_cursor = adapter.InputAddress; out_cursor = adapter.OutputAddress
2. Consume AENT head InputSize (default 4) before bridged cards
3. Each BRIDGED module in slot order:
   - if NoInputBanks != Y: effective_input_bank = in_cursor
   - always in_cursor += InputSize (OA8I still reserves input words)
   - if NoOutputBanks != Y: effective_output_bank = out_cursor
   - always out_cursor += OutputSize

## Supporting peeks (100% IB/OB match vs populated raw)

| Controller | Bridged match |
| --- | ---: |
| MSCATL_CP3 | 23/23 |
| ORNCCP2 | 32/32 |
| ORNCCP4 | 33/33 |
| ORNCCP5 | 53/53 |
| ORINDYAC6 | 24/24 |

## MSCATL_CP2 after promotion

- RAW physical claims: 605
- ASSIGNED: 221 (Flex discrete)
- physical_resolution_failure: 384 (PowerFlex700 words — honest REVIEW)
- GUI Flex module channels populated (no longer 0/n SPARE)

## Rejected

Naive catalog-inferred span without InputSize/NoInputBanks cursor rules → 60/77 counterexamples. Not promoted.
