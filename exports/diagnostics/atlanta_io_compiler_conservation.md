# Atlanta I/O compiler conservation (identity sets)

**Machine:** `MSCATL_CP3`

Identity-set comparison of the **256 ASSIGNED** GUI/PWR claims against field L5X (before) and `atlanta_io_fix_regen4` (after). Counts alone are insufficient — every claim is keyed by `claim_id` / `(io_name, word, bit)` / PWR channel.

## Summary

| Metric | Value |
| --- | ---: |
| ASSIGNED claims | 256 |
| Before named (field L5X rungs) | 67 |
| Before named claim_ids matched | 67 |
| After named (fix regen4) | 255 |
| After specialized | 149 |
| After generic_bool | 106 |
| After placeholders (channel fill) | 49 |
| Lost claims | 0 |
| Intentional mute | 1 (SPARE70207) |
| Recovered claim_ids (after − before) | 188 |
| Field named on wrong PWR channel | 60 |

### Headline

- **before:** ~67 named (55 specialized + 12 generic_bool); 237 placeholders
- **after:** 255 named (149 specialized + 106 generic_bool); 49 placeholders
- **lost_claims:** 0
- **muted/intentional:** SPARE70207

## Root cause

configio_desc_evidence gate blocked PhysicalWordResolver merge into autogen io_word_map. Atlanta Configio Descs are catalog-index forms (e.g. 1794-IA16-5) that PWR resolves, but the prior panel-catalog/node evidence gate skipped the merge. Claimed endpoints then fell through to NO_PointPlaceholder fill (~189/256).

**Fix:** Always merge PhysicalWordResolver when Configio + eipcfg exist (fortna_autogen.load_from_run). Supplement Conveyor.asc io_points with Hardware-GUI claim ledger. Spare-name filter excludes SPARE70207 only.

Code refs:
- `tools/scripts/fortna_autogen.py (PWR merge; claim ledger inject; spare filter)`
- `tools/scripts/fortna_physical_word_resolver.py (configio_desc_evidence / resolve)`
- `exports/ai-io/MSCATL_CP3_MSCATL_CP3/raw_claims.json (256 ASSIGNED)`

## Method

- Claim authority: 256 deterministic_disposition=ASSIGNED rows from raw_claims.json (GUI/PWR claim ledger). Field L5X is validation-only.
- Physical authority: PhysicalWordResolver.resolve(word, bit) against RUN Configio+eipcfg
- Before identity: CP_I/CP_O named rungs in field L5X matched to claims by Bank{word}.{bit} comment only (field often used wrong Data[n]; channel fallback would mis-attribute). PWR-channel occupancy recorded separately.
- After identity: CP_I/CP_O named rungs in atlanta_io_fix_regen4 L5X matched by PWR channel, else Bank{word}.{bit}
- Intentional exclusion: io_name contains SPARE (engineer spare naming) — SPARE70207 only among 256

## Artifacts

- **run_dir:** `workspace/_mscatl_peek/MSCATL_CP3/RUN`
- **raw_claims:** `exports/ai-io/MSCATL_CP3_MSCATL_CP3/raw_claims.json`
- **field_l5x:** `exports/current/MSCATL_CP3_2026_09_20_2137.L5X`
- **fix_regen:** `exports/diagnostics/atlanta_io_fix_regen4`
- **fix_l5x:** `exports/diagnostics/atlanta_io_fix_regen4/MSCATL_CP3.L5X`
- **autogen_report:** `exports/diagnostics/atlanta_io_fix_regen4/autogen_report.json`
- **physical_io_map_csv:** `exports/diagnostics/atlanta_io_fix_regen4/physical_io_map.csv`
- **rio_inventory:** `exports/diagnostics/atlanta_io_fix_regen4/rio_inventory.json`

## Per-rack reconciliation

| RIO | claims | before_named | emitted | specialized | generic_bool | intentional | lost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `T_1794_AENT_1` | 121 | 29 | 120 | 64 | 56 | 1 | 0 |
| `T_1794_AENT_2` | 67 | 19 | 67 | 35 | 32 | 0 | 0 |
| `T_1794_AENT_3` | 68 | 19 | 68 | 50 | 18 | 0 | 0 |

## Per-module reconciliation

| RIO | slot | type | claims | before_named | emitted | spec | generic | mute | lost |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `T_1794_AENT_1` | 0 | `1794-IA16` | 16 | 13 | 16 | 16 | 0 | 0 | 0 |
| `T_1794_AENT_1` | 1 | `1794-IA16` | 16 | 16 | 16 | 16 | 0 | 0 | 0 |
| `T_1794_AENT_1` | 2 | `1794-IA16` | 16 | 0 | 15 | 10 | 5 | 1 | 0 |
| `T_1794_AENT_1` | 3 | `1794-IA16` | 16 | 0 | 16 | 0 | 16 | 0 | 0 |
| `T_1794_AENT_1` | 4 | `1794-IA16` | 14 | 0 | 14 | 0 | 14 | 0 | 0 |
| `T_1794_AENT_1` | 5 | `1794-IA16` | 13 | 0 | 13 | 13 | 0 | 0 | 0 |
| `T_1794_AENT_1` | 6 | `1794-IA16` | 16 | 0 | 16 | 4 | 12 | 0 | 0 |
| `T_1794_AENT_1` | 7 | `1794-IA16` | 14 | 0 | 14 | 5 | 9 | 0 | 0 |
| `T_1794_AENT_2` | 0 | `1794-IA16` | 15 | 0 | 15 | 0 | 15 | 0 | 0 |
| `T_1794_AENT_2` | 1 | `1794-OA8I` | 6 | 3 | 6 | 5 | 1 | 0 | 0 |
| `T_1794_AENT_2` | 2 | `1794-OA8I` | 8 | 8 | 8 | 8 | 0 | 0 | 0 |
| `T_1794_AENT_2` | 3 | `1794-OA8I` | 8 | 8 | 8 | 8 | 0 | 0 | 0 |
| `T_1794_AENT_2` | 4 | `1794-OA8I` | 8 | 0 | 8 | 7 | 1 | 0 | 0 |
| `T_1794_AENT_2` | 5 | `1794-OA8I` | 8 | 0 | 8 | 6 | 2 | 0 | 0 |
| `T_1794_AENT_2` | 6 | `1794-OA8I` | 8 | 0 | 8 | 1 | 7 | 0 | 0 |
| `T_1794_AENT_2` | 7 | `1794-OA8I` | 6 | 0 | 6 | 0 | 6 | 0 | 0 |
| `T_1794_AENT_3` | 0 | `1794-OA8I` | 7 | 7 | 7 | 0 | 7 | 0 | 0 |
| `T_1794_AENT_3` | 1 | `1794-IB16` | 16 | 0 | 16 | 14 | 2 | 0 | 0 |
| `T_1794_AENT_3` | 2 | `1794-IB16` | 12 | 12 | 12 | 7 | 5 | 0 | 0 |
| `T_1794_AENT_3` | 3 | `1794-OB16P` | 9 | 0 | 9 | 9 | 0 | 0 | 0 |
| `T_1794_AENT_3` | 4 | `1794-OB16P` | 7 | 0 | 7 | 7 | 0 | 0 | 0 |
| `T_1794_AENT_3` | 5 | `1794-OW8` | 7 | 0 | 7 | 5 | 2 | 0 | 0 |
| `T_1794_AENT_3` | 6 | `1794-IB16` | 10 | 0 | 10 | 8 | 2 | 0 | 0 |

## Intentional mute

| claim_id | name | physical_address | reason |
| --- | --- | --- | --- |
| `cl_19f1c75c6806cd90` | `SPARE70207` | `T_1794_AENT_1:I.Data[2].7` | engineer_spare_name_contains_SPARE — excluded from named IO_MAP (not unclaimed capacity); channel filled as NO_PointPlaceholder |

## Identity-set checks

- lost_claim_ids: `[]`
- still_missing_non_spare: `[]`
- lost_from_before: `[]`
- intentional_mute ids: `['cl_19f1c75c6806cd90']`
- recovered sample (first 40 of 188):

```
cl_0007f3ea3ad8e6f6, cl_002d74ed8211cd58, cl_006888a7ef751dd9, cl_00e5a0cd4a9f8477, cl_02185cf449415f98, cl_025fb7eb9ee4291a, cl_02ebaac269d7c367, cl_083cd74cad48fb84, cl_0e362294c3d73f74, cl_0ecd1505e04c00e5, cl_0edb01e382b544c6, cl_10044640772efd30, cl_102a3f75e0d9c279, cl_1031b8f33f9df0f3, cl_1098133902b47c6f, cl_10df5796130d8cac, cl_110d73909cd93c29, cl_12132a5fcae3d8cf, cl_14e6e1d764f30f6c, cl_190e30e4791be1e2, cl_1a6e6ca9dbf7598d, cl_1b7ed65bf52e593b, cl_1eef6c7b6c99661a, cl_205d8fabf3925ee1, cl_209d47da5d196a2e, cl_21dd03bb822998b8, cl_2319a90dfeda4621, cl_27086f5351c91a60, cl_279b7881863cd448, cl_304deedcb983f1bf, cl_305fae68f012df9b, cl_32a1a6a814ecd8aa, cl_331a7096bbd73522, cl_353599a5c2b49922, cl_357d18c79e322c06, cl_361aaf582457342c, cl_3692a1cc0b5a4d5d, cl_37eaea864a3d02d0, cl_3876136944b7dcd0, cl_393817bb42b3762a
```

## Gaps / coverage notes

- Claims with PWR channel: **256** / 256
- Claims with final IO_MAP row: **256** / 256
- Non-spare claims missing final IO_MAP row: **0** `[]`
- Field named on wrong PWR channel: **60** — 60/67 before-named claims had Bank{word}.{bit} named rungs on a physical channel that does not match current PWR (EIP bank join without resolver).
- physical_io_map.csv is Conveyor-extract scoped (mapped Y≈233); claim ledger + PWR supplements raise named IO_MAP to 255.
- Field note: Field L5X used for before validation counts only — never as discovery parent. Some named field rungs bound wrong Data[n] (EIP bank join without PWR).
- Coverage OK (256 accounted, 0 lost): **True**

## Claim rows

Full per-claim table (256 rows) is in the JSON under `claims[]` with fields: `physical_address`, `run_logical_name`, `direction`, `resolution_confidence`, `compiler_semantic_target`, `final_io_map_target`, `emitted_or_dropped`, `reason`.

### Sample recovered claims (were placeholder / absent in field)

| name | word.bit | physical | final target | kind |
| --- | --- | --- | --- | --- |
| `ESLS2300L` | 702.1 | `T_1794_AENT_1:I.Data[2].1` | `ESLS2300L.I.ES_OK` | specialized |
| `ESLS2300R` | 702.2 | `T_1794_AENT_1:I.Data[2].2` | `ESLS2300R.I.ES_OK` | specialized |
| `M1000AUX` | 702.13 | `T_1794_AENT_1:I.Data[2].11` | `M1000AUX` | generic_bool |
| `M1004AUX` | 702.14 | `T_1794_AENT_1:I.Data[2].12` | `M1004AUX` | generic_bool |
| `M1008AUX` | 702.15 | `T_1794_AENT_1:I.Data[2].13` | `M1008AUX` | generic_bool |
| `M1012AUX` | 702.16 | `T_1794_AENT_1:I.Data[2].14` | `M1012AUX` | generic_bool |
| `M1018AUX` | 702.17 | `T_1794_AENT_1:I.Data[2].15` | `M1018AUX` | generic_bool |
| `M1114AUX` | 703.5 | `T_1794_AENT_1:I.Data[3].5` | `M1114AUX` | generic_bool |
| `M1208AUX` | 703.13 | `T_1794_AENT_1:I.Data[3].11` | `M1208AUX` | generic_bool |
| `M1224AUX` | 703.16 | `T_1794_AENT_1:I.Data[3].14` | `M1224AUX` | generic_bool |
| `M14AUX` | 704.11 | `T_1794_AENT_1:I.Data[4].9` | `M14AUX` | generic_bool |
| `PE1134_J` | 705.6 | `T_1794_AENT_1:I.Data[5].6` | `PE1134_J.I.PE_Clear` | specialized |
| `EZPWS1012` | 706.4 | `T_1794_AENT_1:I.Data[6].4` | `EZPWS1012` | generic_bool |
| `EZPE13_F` | 707.3 | `T_1794_AENT_1:I.Data[7].3` | `EZPE13_F.I.PE_Clear` | specialized |
| `EZPE14_F` | 707.4 | `T_1794_AENT_1:I.Data[7].4` | `EZPE14_F.I.PE_Clear` | specialized |

