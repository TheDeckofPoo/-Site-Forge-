# Greensboro PLC2 IO Oracle Compare

- Generated: `2026-09-23T16:47:39.292685+00:00`
- Oracle: `C:\dev\worktree\FortnaPlus\workspace\validation\ORLY_GreensboroPLC2_NC_Finished.L5X`
- RUN: `C:\dev\worktree\FortnaPlus\workspace\_plc2_run_peek\RUN`
- Site Forge source (equipment_binding): `C:\dev\worktree\FortnaPlus\workspace\_plc2_run_peek\RUN`
- physical_io_map: `C:\dev\worktree\FortnaPlus\workspace\.internal\builds\20260921-091558\physical_io_map.csv`

## Counts by class

| Class | Count |
|---|---:|
| `MATCH` | 170 |
| `SITE_FORGE_WRONG_DEVICE` | 50 |
| `SITE_FORGE_WRONG_UDT` | 0 |
| `SITE_FORGE_WRONG_MEMBER` | 4 |
| `SITE_FORGE_WRONG_ENDPOINT` | 4 |
| `ORACLE_ADDS_INFO` | 10 |
| `REVIEW_REQUIRED` | 0 |

Compared oracle mappings: **238**
Site Forge-only endpoints (not in oracle): **11**

## Counts by UDT family

| UDT family | Class breakdown |
|---|---|
| `AirPressure_Switch_UDT` | MATCH=2 |
| `BOOL` | ORACLE_ADDS_INFO=1, SITE_FORGE_WRONG_DEVICE=2 |
| `CS_UDT` | MATCH=4, ORACLE_ADDS_INFO=7, SITE_FORGE_WRONG_DEVICE=4, SITE_FORGE_WRONG_ENDPOINT=4, SITE_FORGE_WRONG_MEMBER=4 |
| `Conv_UDT` | MATCH=53, SITE_FORGE_WRONG_DEVICE=10 |
| `ES_UDT` | MATCH=30, SITE_FORGE_WRONG_DEVICE=12 |
| `Motor_Starter_UDT` | MATCH=53, ORACLE_ADDS_INFO=2, SITE_FORGE_WRONG_DEVICE=4 |
| `PE_UDT` | MATCH=22, SITE_FORGE_WRONG_DEVICE=15 |
| `PE_UDT?` | SITE_FORGE_WRONG_DEVICE=3 |
| `PS_UDT` | MATCH=6 |

## Sample oracle mappings

### ES406
- `CP2RIO0:I.Data[1].8` → `ES406.I.ES_OK` (ES_UDT) [CP_I]

### PE
- `CP2RIO1:I.Data[0].0` → `PE126_JF.I.PE_Clear` (PE_UDT) [CP_I]
- `CP2RIO1:I.Data[0].1` → `PE134_JF.I.PE_Clear` (PE_UDT) [CP_I]
- `CP2RIO1:I.Data[0].2` → `PE138_P.I.PE_Clear` (PE_UDT) [CP_I]
- `CP2RIO1:I.Data[0].3` → `PE226_JF.I.PE_Clear` (PE_UDT) [CP_I]
- `CP2RIO1:I.Data[0].5` → `PE314_P.I.PE_Clear` (PE_UDT) [CP_I]
- `CP2RIO1:I.Data[0].6` → `PE316_J.I.PE_Clear` (PE_UDT) [CP_I]
- `CP2RIO1:I.Data[0].7` → `PE404_P.I.PE_Clear` (PE_UDT) [CP_I]
- `CP2RIO1:I.Data[0].8` → `PE406_J.I.PE_Clear` (PE_UDT) [CP_I]

### MS
- `CP2RIO0:I.Data[3].7` → `P124_MS.I.Auxiliary_Forward` (Motor_Starter_UDT) [CP_I]
- `CP2RIO0:I.Data[3].8` → `P128_MS.I.Auxiliary_Forward` (Motor_Starter_UDT) [CP_I]
- `CP2RIO0:I.Data[3].9` → `P130A_MS.I.Auxiliary_Forward` (Motor_Starter_UDT) [CP_I]
- `CP2RIO0:I.Data[3].10` → `P130B_MS.I.Auxiliary_Forward` (Motor_Starter_UDT) [CP_I]
- `CP2RIO0:I.Data[3].11` → `P130C_MS.I.Auxiliary_Forward` (Motor_Starter_UDT) [CP_I]
- `CP2RIO0:I.Data[3].12` → `P130D_MS.I.Auxiliary_Forward` (Motor_Starter_UDT) [CP_I]
- `CP2RIO0:I.Data[3].13` → `P130E_MS.I.Auxiliary_Forward` (Motor_Starter_UDT) [CP_I]
- `CP2RIO0:I.Data[3].14` → `P132_MS.I.Auxiliary_Forward` (Motor_Starter_UDT) [CP_I]

### PS
- `CP2RIO1:I.Data[2].0` → `EZPWS136.I.PS_OK` (PS_UDT) [CP_I]
- `CP2RIO1:I.Data[2].2` → `EZPWS312.I.PS_OK` (PS_UDT) [CP_I]
- `CP2RIO1:I.Data[2].3` → `EZPWS402.I.PS_OK` (PS_UDT) [CP_I]
- `CP2RIO1:I.Data[2].12` → `PS312.I.Pressure_OK` (AirPressure_Switch_UDT) [CP_I]
- `CP3RIO1:I.Data[4].7` → `PS320.I.Pressure_OK` (AirPressure_Switch_UDT) [CP_I]
- `CP3RIO1:I.Data[4].11` → `EZPWS150.I.PS_OK` (PS_UDT) [CP_I]
- `CP3RIO1:I.Data[4].12` → `EZPWS242.I.PS_OK` (PS_UDT) [CP_I]
- `CP3RIO1:I.Data[4].13` → `EZPWS320.I.PS_OK` (PS_UDT) [CP_I]

### Conv
- `CP2RIO0:O.Data[2].0` → `P124_Conv.O.Run` (Conv_UDT) [CP_O]
- `CP2RIO0:O.Data[2].1` → `P220_Conv.O.Run` (Conv_UDT) [CP_O]
- `CP2RIO0:O.Data[2].2` → `P310_Conv.O.Run` (Conv_UDT) [CP_O]
- `CP2RIO0:O.Data[2].3` → `P312_Conv.O.Run` (Conv_UDT) [CP_O]
- `CP2RIO0:O.Data[2].4` → `P123_Conv.O.Run` (Conv_UDT) [CP_O]
- `CP2RIO0:O.Data[2].5` → `P220A_Conv.O.Run` (Conv_UDT) [CP_O]
- `CP2RIO0:O.Data[2].6` → `P309_Conv.O.Run` (Conv_UDT) [CP_O]
- `CP2RIO0:O.Data[4].0` → `P128_Conv.O.Run` (Conv_UDT) [CP_O]

## Mismatch samples

- **SITE_FORGE_WRONG_DEVICE** `CP2RIO0:I.Data[1].2`: oracle `CP2_MCR1.I.ES_OK` (ES_UDT) vs SF `2MCR1_AUX.I.ES_OK` (ES_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP2RIO0:I.Data[1].3`: oracle `CP2_ESR1.I.ES_OK` (ES_UDT) vs SF `2ESR1_AUX.I.ES_OK` (ES_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP2RIO0:I.Data[1].4`: oracle `CP2_ESR2.I.ES_OK` (ES_UDT) vs SF `2ESR2_AUX.I.ES_OK` (ES_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP2RIO0:I.Data[1].5`: oracle `CP2_ESR3.I.ES_OK` (ES_UDT) vs SF `2ESR3_AUX.I.ES_OK` (ES_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP2RIO0:I.Data[1].7`: oracle `CP2_ES.I.ES_OK` (ES_UDT) vs SF `2ES.I.ES_OK` (ES_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP2RIO0:I.Data[3].15`: oracle `P136_1_MS.I.Auxiliary_Forward` (Motor_Starter_UDT) vs SF `P136_MS.I.Auxiliary_Forward` (Motor_Starter_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP2RIO0:I.Data[7].6`: oracle `CP8_P229_MS.I.Auxiliary_Forward` (Motor_Starter_UDT) vs SF `INT229` (—)
- **ORACLE_ADDS_INFO** `CP2RIO0:I.Data[7].8`: oracle `CP4_P408_MS.I.Auxiliary_Forward` (Motor_Starter_UDT) vs SF `—` (—)
- **ORACLE_ADDS_INFO** `CP2RIO0:I.Data[7].9`: oracle `CP3_P1014_MS.I.Auxiliary_Forward` (Motor_Starter_UDT) vs SF `—` (—)
- **ORACLE_ADDS_INFO** `CP2RIO1:I.Data[2].8`: oracle `P406_CS.I.Reset_PB` (CS_UDT) vs SF `—` (—)
- **ORACLE_ADDS_INFO** `CP2RIO1:I.Data[2].9`: oracle `P1002_CS.I.Reset_PB` (CS_UDT) vs SF `—` (—)
- **SITE_FORGE_WRONG_DEVICE** `CP2RIO1:I.Data[4].0`: oracle `PE136_F1.I.PE_Clear` (PE_UDT) vs SF `EZPE136_F1.I.PE_Clear` (PE_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP2RIO1:I.Data[4].1`: oracle `PE136_F2.I.PE_Clear` (PE_UDT) vs SF `EZPE136_F2.I.PE_Clear` (PE_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP2RIO1:I.Data[4].3`: oracle `PE312_F.I.PE_Clear` (PE_UDT) vs SF `EZPE312_F.I.PE_Clear` (PE_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP2RIO1:I.Data[4].4`: oracle `PE408_F.I.PE_Clear` () vs SF `EZPE408_F.I.PE_Clear` (PE_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP2RIO1:I.Data[4].5`: oracle `PE136_P1.I.PE_Clear` (PE_UDT) vs SF `EZPE136_P1.I.PE_Clear` (PE_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP2RIO1:I.Data[4].6`: oracle `PE136_P2.I.PE_Clear` (PE_UDT) vs SF `EZPE136_P2.I.PE_Clear` (PE_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP2RIO1:I.Data[4].8`: oracle `PE312_P.I.PE_Clear` (PE_UDT) vs SF `EZPE312_P.I.PE_Clear` (PE_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP2RIO1:I.Data[4].9`: oracle `PE402_P.I.PE_Clear` (PE_UDT) vs SF `EZPE402_P.I.PE_Clear` (PE_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP2RIO1:I.Data[4].10`: oracle `PE229_F.I.PE_Clear` () vs SF `EZPE229_F.I.PE_Clear` (PE_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP3RIO0:I.Data[1].2`: oracle `CP3_MCR1.I.ES_OK` (ES_UDT) vs SF `3MCR1_AUX.I.ES_OK` (ES_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP3RIO0:I.Data[1].3`: oracle `CP3_ESR1.I.ES_OK` (ES_UDT) vs SF `3ESR1_AUX.I.ES_OK` (ES_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP3RIO0:I.Data[1].4`: oracle `CP3_ESR2.I.ES_OK` (ES_UDT) vs SF `3ESR2_AUX.I.ES_OK` (ES_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP3RIO0:I.Data[1].5`: oracle `CP3_ESR3.I.ES_OK` (ES_UDT) vs SF `3ESR3_AUX.I.ES_OK` (ES_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP3RIO0:I.Data[1].6`: oracle `CP3_ESR4.I.ES_OK` (ES_UDT) vs SF `3ESR4_AUX.I.ES_OK` (ES_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP3RIO0:I.Data[1].7`: oracle `CP3_ESR5.I.ES_OK` (ES_UDT) vs SF `3ESR5_AUX.I.ES_OK` (ES_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP3RIO0:I.Data[1].8`: oracle `CP3_ES.I.ES_OK` (ES_UDT) vs SF `3ES.I.ES_OK` (ES_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP3RIO0:I.Data[5].8`: oracle `P150_P1_MS.I.Auxiliary_Forward` (Motor_Starter_UDT) vs SF `P150_MS.I.Auxiliary_Forward` (Motor_Starter_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP3RIO1:I.Data[0].8`: oracle `P402_MS.I.Auxiliary_Forward` (Motor_Starter_UDT) vs SF `INT402` (—)
- **ORACLE_ADDS_INFO** `CP3RIO1:I.Data[0].9`: oracle `Trash_Compactor_Running` (BOOL) vs SF `—` (—)
- **ORACLE_ADDS_INFO** `CP3RIO1:I.Data[4].0`: oracle `P400_CS.I.Reset_PB` (CS_UDT) vs SF `—` (—)
- **ORACLE_ADDS_INFO** `CP3RIO1:I.Data[4].1`: oracle `P1008_CS.I.Reset_PB` (CS_UDT) vs SF `—` (—)
- **ORACLE_ADDS_INFO** `CP3RIO1:I.Data[4].2`: oracle `P1014_CS.I.Reset_PB` (CS_UDT) vs SF `—` (—)
- **SITE_FORGE_WRONG_DEVICE** `CP3RIO1:I.Data[6].0`: oracle `P1018_CS.I.Start_PB` (CS_UDT) vs SF `PBSTART1018` (—)
- **SITE_FORGE_WRONG_DEVICE** `CP3RIO1:I.Data[6].1`: oracle `P1018_CS.I.Stop_PB` (CS_UDT) vs SF `PBSTOP1018` (—)
- **SITE_FORGE_WRONG_DEVICE** `CP3RIO2:I.Data[1].0`: oracle `PE150_F1.I.PE_Clear` (PE_UDT) vs SF `EZPE150_F1.I.PE_Clear` (PE_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP3RIO2:I.Data[1].1`: oracle `PE150_F2.I.PE_Clear` (PE_UDT) vs SF `EZPE150_F2.I.PE_Clear` (PE_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP3RIO2:I.Data[1].2`: oracle `PE242_F.I.PE_Clear` (PE_UDT) vs SF `EZPE242_F.I.PE_Clear` (PE_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP3RIO2:I.Data[1].3`: oracle `PE320_F.I.PE_Clear` (PE_UDT) vs SF `EZPE320_F.I.PE_Clear` (PE_UDT)
- **SITE_FORGE_WRONG_DEVICE** `CP3RIO2:I.Data[1].4`: oracle `PE402_F.I.PE_Clear` () vs SF `EZPE402_F.I.PE_Clear` (PE_UDT)

_Diagnostics only. Finished L5X is validation authority; do not feed into fortna_autogen / equipment_binding._
