# MSCATL CP1/CP2/CP3 dialect comparison

| Machine | EIPModules nonzero | ASSIGNED | Unresolved | Bank state |
| --- | ---: | ---: | ---: | --- |
| MSCATL_CP1 | 39/39 | 842 | 0 | `ALL_NONZERO_RAW` |
| MSCATL_CP2 | 0/20 | 221 | 384 | `ALL_ZERO_RAW` |
| MSCATL_CP3 | 23/23 | 256 | 0 | `ALL_NONZERO_RAW` |

## Patterns (not site special-cases)

- **catalog_index_plus_bank**: 1794-IA16-N Desc + Configio.Bank ↔ EIPModules InputBank/OutputBank _(seen: MSCATL_CP3, MSCATL_CP2(after derivation))_
- **flex_zero_bank_effective_layout**: EIPModules IB/OB all 0; derive effective banks from InputAddress+sizes _(seen: MSCATL_CP2)_
- **rta_32pt_token_direct_span**: IB32DATA/OB32PDATA tokens; mid-span banks within DirectSize _(seen: MSCATL_CP1)_
