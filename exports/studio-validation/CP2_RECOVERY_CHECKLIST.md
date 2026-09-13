# CP2 Recovery — Curtis Studio Checklist

**File:** `exports/studio-validation/ORNCCP2_recovery_validation.L5X`  
**SHA256:** `df09fa9e410b1ec098bf013b314bc7ac85578cb7e9ff4f0c6e139b8e51f843ce`  
**Branch:** `feature/cp2-recovery-validation`

Static tooling does **not** equal Studio PASS. Please confirm visually:

- [ ] L5X imports
- [ ] Controller opens
- [ ] I/O tree populated
- [ ] remote adapters present (`T_1794_AENT_1` … `T_1794_AENT_5`, EN2T)
- [ ] child modules present (IA16 / IB16 / OA8I / OB16P under AENTs)
- [ ] slots/catalogs look correct
- [ ] IO_MAP contains real mappings (not empty / not NOP-only)
- [ ] PE mappings look correct (spot-check `PE215_J` ← `T_1794_AENT_1:I.Data[6].11`)
- [ ] motor / digital output mappings look correct (CP2 has few/no VFDs — check outputs like `WH310`)
- [ ] no NOP-only mapping routine

**Expected floor (locked baseline):** 39 modules · 27 word-map entries · 68 IO_MAP XIC/OTE refs.
