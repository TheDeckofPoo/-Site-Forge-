# Gate 2 — Word 600 physical translation (ORINDYAC6)

**Runtime lineage:** cfa10d8 + this differential fix  
**Finished PLC:** validation oracle only (`ORLY_Brownsburg_IN_PLC6_TEST2.L5X`)  
**Finished PLC not used to invent RUN relationships.**

## What Data[] means (Fortna / Logix)

For **1794 Flex I/O**:

```
chassis slot S (AENT head = 0)
Logix module Data image index = S − 1   when S > 0
```

Proven in `fortna_hardware_family.data_index_for_module` / Site Forge family scheme.  
`Data[n]` is the **adapter image word / Logix data index**, not Configio.Bank and not Fortna Octal_Word.

## Trace (after fix)

| Fortna Word.Bit | Configio Desc | Configio.Bank | EIPModules InputBank | Slot | Data[n].bit | Finished oracle |
|-----------------|---------------|---------------|----------------------|------|-------------|-----------------|
| 600.0 | 1794-IA16-600-4 | 4 | 4 | 1 | **I.Data[0].0** | CP6RIO0:I.Data[0].0 |
| 600.2 | (same word) | 4 | 4 | 1 | **I.Data[0].2** | CP6RIO0:I.Data[0].2 |
| 600.8 | High half same module | 4→Low bank match | 4 | 1 | **I.Data[0].8** | CP6RIO0:I.Data[0].8 |

## First bad transformation (before fix)

| Stage | Value |
|-------|-------|
| Configio Desc | `1794-IA16-600-4` |
| Bug | `parse_configio_catalog_word_bank` set `module_name = "1794-IA16-4"` using **Bank=4** |
| Name match | eipcfg module **named** `1794-IA16-4` at **slot 3** |
| Data index | slot−1 → **Data[2]** |
| Finished | first IA16 is **Data[0]** (slot 1, InputBank 4) |

**Root cause file:** `fortna_physical_word_resolver.py`  
**Generic rule:** For `catalog_word_bank` Desc, trailing digits are **EIPModules bank**, not eipcfg module-name index. Assign exclusively via `Configio.Bank ↔ InputBank/OutputBank`. Never promote that form into `parsed.module_name` for name matching.

## Assign how after fix

`configio_bank_match` → slot 1 → `T_1794_AENT_1:I.Data[0].*`
