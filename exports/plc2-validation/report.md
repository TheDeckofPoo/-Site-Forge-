# PLC2 Validation — IO Channel + Transport Device Matrix

**Generated:** 2026-09-13T15:51:10.268577+00:00
**Current L5X:** `C:/dev/worktree/FortnaPlus/exports/current/ORNCCP2_LATEST.L5X`
**Finished oracle (validation only):** `C:/dev/worktree/FortnaPlus/workspace/validation/ORLY_GreensboroPLC2_NC_Finished.L5X`

## Policy

- RUN tables are the generation source.
- Finished PLC2 is **validation only** — never a generation template.
- This report classifies differences; it does not invent generation rules from finished.

## I/O channel classification counts

| Classification | Count |
|----------------|------:|
| EXACT | 331 |
| SEMANTIC_EQUIVALENT | 111 |
| FALSE_PLACEHOLDER | 26 |
| SHOULD_BE_PLACEHOLDER | 16 |
| WRONG_DEVICE | 26 |
| WRONG_MEMBER | 2 |
| WRONG_ADAPTER | 0 |
| WRONG_SLOT | 0 |
| WRONG_BIT | 0 |
| WRONG_DIRECTION | 0 |
| RUN_UNRESOLVED | 0 |

## I/O summary

| Metric | Count |
|--------|------:|
| Channels compared | 512 |
| Generated real I | 147 |
| Generated real O | 78 |
| Finished real I | 159 |
| Finished real O | 75 |
| Generated placeholders | 177 |
| Finished placeholders | 274 |

## Sample mismatches

| Channel | Class | Generated | Finished | RUN |
|---------|-------|-----------|----------|-----|
| `CP2RIO0:I.Data[1].7` | FALSE_PLACEHOLDER | `None` | `CP2_ES.I.ES_OK` | `2ES` |
| `CP2RIO0:I.Data[3].15` | SHOULD_BE_PLACEHOLDER | `P136_P1_MS.I.Auxiliary_Forward` | `None` | `None` |
| `CP2RIO0:I.Data[5].1` | WRONG_DEVICE | `P220A_MS.I.Auxiliary_Forward` | `P220_MS.I.Auxiliary_Forward` | `M220_AUX` |
| `CP2RIO0:I.Data[5].3` | SHOULD_BE_PLACEHOLDER | `P228_MS.I.Auxiliary_Forward` | `None` | `M228_AUX` |
| `CP2RIO0:I.Data[5].4` | SHOULD_BE_PLACEHOLDER | `P230_MS.I.Auxiliary_Forward` | `None` | `M230_AUX` |
| `CP2RIO0:I.Data[5].5` | SHOULD_BE_PLACEHOLDER | `P232_MS.I.Auxiliary_Forward` | `None` | `M232_AUX` |
| `CP2RIO0:I.Data[7].6` | FALSE_PLACEHOLDER | `None` | `CP8_P229_MS.I.Auxiliary_Forward` | `INT229` |
| `CP2RIO0:I.Data[7].8` | FALSE_PLACEHOLDER | `None` | `CP4_P408_MS.I.Auxiliary_Forward` | `None` |
| `CP2RIO0:I.Data[7].9` | FALSE_PLACEHOLDER | `None` | `CP3_P1014_MS.I.Auxiliary_Forward` | `None` |
| `CP2RIO0:O.Data[0].0` | FALSE_PLACEHOLDER | `None` | `CP2_CS.O.Start_PB_LT` | `2PBSTART_PLT` |
| `CP2RIO0:O.Data[0].1` | FALSE_PLACEHOLDER | `None` | `CP2_CS.O.Stop_PB_LT` | `2PBSTOP_PLT` |
| `CP2RIO0:O.Data[0].2` | WRONG_DEVICE | `T_2MCR1.I.ES_OK` | `CP2_MCR1_Power_On` | `2MCR1` |
| `CP2RIO0:O.Data[0].3` | WRONG_DEVICE | `T_2WH` | `CP2_WH.O.Horn` | `2WH` |
| `CP2RIO0:O.Data[0].7` | SHOULD_BE_PLACEHOLDER | `CP2_ES.I.ES_OK` | `None` | `None` |
| `CP2RIO0:O.Data[2].1` | WRONG_DEVICE | `P220A_Conv.O.Run` | `P220_Conv.O.Run` | `M220` |
| `CP2RIO0:O.Data[4].7` | SHOULD_BE_PLACEHOLDER | `P136_P1_Conv.O.Run` | `None` | `M136` |
| `CP2RIO0:O.Data[6].2` | SHOULD_BE_PLACEHOLDER | `P228_Conv.O.Run` | `None` | `M228` |
| `CP2RIO0:O.Data[6].3` | SHOULD_BE_PLACEHOLDER | `P230_Conv.O.Run` | `None` | `M230` |
| `CP2RIO0:O.Data[6].4` | SHOULD_BE_PLACEHOLDER | `P232_Conv.O.Run` | `None` | `M232` |
| `CP2RIO1:I.Data[0].4` | SHOULD_BE_PLACEHOLDER | `PE232_P.I.PE_Clear` | `None` | `PE232_P` |
| `CP2RIO1:I.Data[2].0` | FALSE_PLACEHOLDER | `None` | `EZPWS136.I.PS_OK` | `EZPWS136` |
| `CP2RIO1:I.Data[2].2` | FALSE_PLACEHOLDER | `None` | `EZPWS312.I.PS_OK` | `EZPWS312` |
| `CP2RIO1:I.Data[2].3` | FALSE_PLACEHOLDER | `None` | `EZPWS402.I.PS_OK` | `EZPWS402` |
| `CP2RIO1:I.Data[2].8` | FALSE_PLACEHOLDER | `None` | `P406_CS.I.Reset_PB` | `None` |
| `CP2RIO1:I.Data[2].9` | FALSE_PLACEHOLDER | `None` | `P1002_CS.I.Reset_PB` | `None` |

## Transport device matrix (Area names ignored)

- Local conveyors compared: **59**
- Fast_Conv next match / mismatch: **14** / **39**
- Fast_Conv type match / mismatch: **42** / **11**

| Family result | Count |
|---------------|------:|
| Conv_AOI_BOTH | 42 |
| Conv_AOI_FINISHED_ONLY | 1 |
| Conv_AOI_GENERATED_ONLY | 10 |
| Conv_AOI_NEITHER | 6 |
| Conv_BOTH | 42 |
| Conv_FINISHED_ONLY | 1 |
| Conv_GENERATED_ONLY | 10 |
| Conv_NEITHER | 6 |
| Fast_Conv_BOTH | 42 |
| Fast_Conv_FINISHED_ONLY | 1 |
| Fast_Conv_GENERATED_ONLY | 10 |
| Fast_Conv_NEITHER | 6 |
| MS_BOTH | 43 |
| MS_GENERATED_ONLY | 12 |
| MS_NEITHER | 4 |
| PE_BOTH | 27 |
| PE_GENERATED_ONLY | 2 |
| PE_NEITHER | 30 |

## Artifacts

- `exports/plc2-validation/io_channel_matrix.json`
- `exports/plc2-validation/transport_device_matrix.json`
- `exports/plc2-validation/report.md`

