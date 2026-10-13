# High-byte address normalization — overnight audit

**BASE SHA:** `a935a22`  
**Evidence:** gold `physical_io_map.csv` (151 rows, 114 mapped Y)

## Generator / map

- Notes consistently carry `raw_bit` / `canonical_bit` / `half=low|high` / `alt=AENTR*:*.Data[slot].bit`
- Emit path uses `_fortna_bit_to_data_bit` → `normalize_fortna_word_bit` (no silent octal)
- Example high-half: `EZPE44_F` raw_bit=14 → canonical_bit=12 → `AENTR3:2:I.Data.4`
- Example CL17: Bank1011.12 → `AENTR3:O.Data[10].2` (matches Relay oracle)

## UI (~51 cases)

Not re-probed end-to-end in browser this overnight (desktop frozen).  
Generator canonical endpoint matches map `module_data_ref` / `alt=` form.

**Status:** **GENERATOR_CANONICAL_OK** for gold build map.  
**Remaining:** explicit UI join regression for the historical ~51 display cases on a non-Curtis desktop session.

## Classification

| Layer | Status |
|---|---|
| physical_io_map canonical byte/bit | OK (114 Y rows with half/canonical notes) |
| IO_MAP OTE endpoints | OK for mapped devices (CL17 proven) |
| UI display parity | NEEDS_UI_SESSION (not overnight) |
