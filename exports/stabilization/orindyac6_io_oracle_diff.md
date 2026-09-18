# ORINDYAC6 I/O Oracle Diff (HardwareIOModel vs finished PLC)

Finished PLC is **validation oracle only**. No RUN relationships invented from it.

## GATE 0 — Provenance

| Field | Value |
|-------|-------|
| Runtime SHA | `cfa10d840dcaf9a9cc8bde3219441886b89dba97` |
| Machine | `ORINDYAC6` |
| Virgin RUN | `C:\dev\worktree\FortnaPlus\workspace\_virgin_orindy\RUN` |
| Virgin fingerprint (combined SHA256) | `de11189bb2a307d2422d1a736260df45f1e110424b7404e30cd083aa2a71d1d3` |
| Oracle path | `C:\Users\curtiskricke\Desktop\ORiellys Browns\PLC Progrms\ORLY_Brownsburg_IN_PLC6_TEST2.L5X` |
| Oracle size | `7867435` |
| Oracle SHA256 | `4cf7a6218ca1f2537849097b18899d1d59afc730452c49a5b45ba2f03ec32974` |
| Site Forge L5X (optional) | `C:\dev\worktree\FortnaPlus\exports\current\ORINDYAC6_2026_09_18_1448.L5X` size=5847303 sha256=`f12bd92c812280896c6a77685ab7a6e8976cc7ef9ae43e76255316db006d7a2b` |

### Virgin RUN fingerprint files

| Path | Size | SHA256 |
|------|------|--------|
| `project.cfg` | 352 | `90ecdd09c8d97ea3a4f39d9caf37fafaa09cbc410967d7e5b76ed4d2dd621a2c` |
| `info.cfg` | 112 | `be41a51bf4762ed17aefbd776ff8ed020d84be77e904947442e286c3685b9b46` |
| `identity.cfg` | 70 | `9c51268715d4274c4983ea454b7a74a79220677924d6ef504f504fcd17e3ee35` |
| `FORTNA/Configio.asc.ORINDYAC6` | 22001 | `4f78f1d517c75e90d19e833b95ef85d9b2c45d6d41663e0f3d0278df351130c4` |
| `FORTNA/Conveyor.asc` | 2137254 | `4082b2f49db1713f12cf89daddeb544fbf9ea34e6fc48db5b2a462446363d03f` |
| `PROJECT/EIPModules.asc.ORINDYAC6` | 78527 | `f5c95f3ed5301d8337d146b659b3a694f5612748c21a6639f3452e7c92261985` |
| `PROJECT/EIPAdapters.asc.ORINDYAC6` | 1127 | `0182b3b4cd44a1fdc633284bf24300b65c9618b1ab2676f5e40f29061ee79a86` |
| `PROJECT/EIPCSV.asc.ORINDYAC6` | 12613 | `d4b7fd8e9e819a113f3e96a12cbbd65f02e20991f05e421d4c45711fbccecdd8` |

## Adapter map (IP / order — generic)

| Site Forge | Finished | How | Detail |
|------------|----------|-----|--------|
| `T_1794_AENT_1` | `CP6RIO0` | ip | 192.168.1.51 |
| `T_1794_AENT_2` | `CP6RIO1` | ip | 192.168.1.52 |
| `T_1794_AENT_3` | `CP6RIO2` | ip | 192.168.1.53 |
| `T_1794_AENT_4` | `CP6RIO3` | ip | 192.168.1.54 |

## Totals

- Site Forge channels: **336**
- Finished IO_MAP channels: **384**
- Comparisons: **384**

| Classification | Count |
|----------------|------:|
| EXACT_MATCH | 12 |
| OWNER_MATCH_ENDPOINT_MISMATCH | 0 |
| ENDPOINT_MATCH_OWNER_MISMATCH | 0 |
| MISSING_SITEFORGE_OWNER | 0 |
| EXTRA_SITEFORGE_OWNER | 0 |
| FINISHED_PLACEHOLDER | 139 |
| ENGINEER_MODIFIED | 162 |
| AMBIGUOUS | 71 |
| NOT_COMPARABLE | 0 |

## Word 600.0–600.9 detail

**Confirm 600.0 → Data[0].0:** YES (assign_how=`configio_bank_match`, channel=`T_1794_AENT_1:I.Data[0].0`)

| Bit | SF channel | SF owner | Finished channel | Finished tag | Class |
|----:|------------|----------|------------------|--------------|-------|
| 0 | `T_1794_AENT_1:I.Data[0].0` | `6PBSTART` | `CP6RIO0:I.Data[0].0` | `CP6_ShippingSorter_Area_CS.I.Start_PB` | **EXACT_MATCH** |
| 1 | `T_1794_AENT_1:I.Data[0].1` | `6PBSTOP` | `CP6RIO0:I.Data[0].1` | `CP6_ShippingSorter_Area_CS.I.Stop_PB` | **EXACT_MATCH** |
| 2 | `T_1794_AENT_1:I.Data[0].2` | `6MCR1AUX` | `CP6RIO0:I.Data[0].2` | `CP6_MCR1.I.ES_OK` | **ENGINEER_MODIFIED** |
| 3 | `T_1794_AENT_1:I.Data[0].3` | `6ESR1AUX` | `CP6RIO0:I.Data[0].3` | `CP6_ESR1.I.ES_OK` | **ENGINEER_MODIFIED** |
| 4 | `T_1794_AENT_1:I.Data[0].4` | `6ESR2AUX` | `CP6RIO0:I.Data[0].4` | `CP6_ESR2.I.ES_OK` | **ENGINEER_MODIFIED** |
| 5 | `T_1794_AENT_1:I.Data[0].5` | `FIRE ALARM BYPASS MEM` | `CP6RIO0:I.Data[0].5` | `SSCP6` | **AMBIGUOUS** |
| 6 | `T_1794_AENT_1:I.Data[0].6` | `None` | `CP6RIO0:I.Data[0].6` | `NO_PointPlaceholder` | **FINISHED_PLACEHOLDER** |
| 7 | `T_1794_AENT_1:I.Data[0].7` | `None` | `CP6RIO0:I.Data[0].7` | `NO_PointPlaceholder` | **FINISHED_PLACEHOLDER** |
| 8 | `T_1794_AENT_1:I.Data[0].8` | `6ES` | `CP6RIO0:I.Data[0].8` | `CP6_ES.I.ES_OK` | **ENGINEER_MODIFIED** |
| 9 | `T_1794_AENT_1:I.Data[0].9` | `ES600` | `CP6RIO0:I.Data[0].9` | `ES600.I.ES_OK` | **ENGINEER_MODIFIED** |

## GATE 2 — What `Data[]` means

For **1794 Flex I/O**:

```
chassis slot S  (AENT head = slot 0)
Logix module Data image index = data_index_for_module(S)
                            = S − 1   when S > 0
```

`Data[n]` is the **Flex Logix image index**, not Configio.Bank and not Fortna Octal_Word.

- Rule: Data[n] = Flex Logix image index = data_index_for_module(slot) = slot-1 for 1794 when slot>0
- First bad transform: catalog_word_bank false name match used Bank trailing digit as module-name index → wrong slot/Data[2]
- Fix: configio_bank_match joins Configio.Bank ↔ EIPModules InputBank/OutputBank only

Word 600 Configio Desc `1794-IA16-600-4` must assign via `configio_bank_match` (Bank↔InputBank) → slot 1 → `T_1794_AENT_1:I.Data[0].*`. The false `catalog_word_bank` name match previously selected module `1794-IA16-4` at slot 3 → **Data[2]**.

## Classification legend

| Class | Meaning |
|-------|---------|
| EXACT_MATCH | Endpoint + owner (cookie-cutter / normalized) agree |
| OWNER_MATCH_ENDPOINT_MISMATCH | Owner equivalent; Data[]/adapter/bit disagree |
| ENDPOINT_MATCH_OWNER_MISMATCH | Same endpoint; owners disagree |
| MISSING_SITEFORGE_OWNER | Finished has real tag; HardwareIOModel lacks ASSIGNED owner |
| EXTRA_SITEFORGE_OWNER | HardwareIOModel ASSIGNED; finished placeholder or absent |
| FINISHED_PLACEHOLDER | Finished `NO_PointPlaceholder` (cookie-cutter unused fill) |
| ENGINEER_MODIFIED | Finished rung includes `_EMU_*` parallel (engineer overlay) |
| AMBIGUOUS | Owner equivalence unproven — both values retained |
| NOT_COMPARABLE | Adapter/endpoint outside discrete Flex IO_MAP compare |

